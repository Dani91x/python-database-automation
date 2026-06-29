"""
odds_http.py — micro-endpoint HTTP LOCALE per il pulsante "Aggiorna quote" della
watchlist. Riusa il processo del runner live (sempre acceso) senza toccarne il
loop flumine: un ThreadingHTTPServer su 127.0.0.1 in un thread daemon.

Solo stdlib (http.server), nessuna dipendenza aggiuntiva. Espone:
    POST /refresh-odds   body JSON {"fixture_id": <int>}  (o ?fixture_id=<int>)
        → chiama Betfair/odds_refresh.refresh_fixture_odds e ritorna l'esito JSON.

SICUREZZA: bind SOLO su 127.0.0.1 (mai 0.0.0.0). È uno strumento personale locale:
il browser dell'utente gira sulla stessa macchina del runner. CORS permissivo per
consentire la fetch dalla web-app; l'endpoint accetta solo il refresh per fixture.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

ODDS_HTTP_HOST = os.getenv("LIVE_ODDS_HTTP_HOST", "127.0.0.1")
ODDS_HTTP_PORT = int(os.getenv("LIVE_ODDS_HTTP_PORT", "8787"))
_MAX_BODY_BYTES = 65_536   # 64 KB: tetto difensivo alla lettura del corpo richiesta
if ODDS_HTTP_HOST not in ("127.0.0.1", "::1", "localhost"):
    # binding non-loopback: il server diventa raggiungibile dalla rete → assicurarsi
    # che sia intenzionale (di norma deve restare locale).
    logger.warning("[odds-http] LIVE_ODDS_HTTP_HOST='%s': binding NON loopback, esposto in rete.", ODDS_HTTP_HOST)

# Origini browser autorizzate a chiamare l'endpoint (difesa CSRF: un sito qualsiasi
# aperto nel browser NON deve poter triggerare chiamate Betfair sotto le credenziali
# locali). Default: porte di sviluppo Vite/локali. In produzione (web-app hostata)
# impostare ODDS_HTTP_ALLOWED_ORIGINS=https://<tuo-dominio> (lista separata da virgole).
_DEFAULT_ALLOWED_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"
ALLOWED_ORIGINS = {
    o.strip() for o in os.getenv("ODDS_HTTP_ALLOWED_ORIGINS", _DEFAULT_ALLOWED_ORIGINS).split(",") if o.strip()
}


class _Handler(BaseHTTPRequestHandler):
    server_version = "OddsRefresh/1.0"

    # --- helper risposta ---
    def _allow_origin(self) -> Optional[str]:
        """Ritorna l'Origin della richiesta SE è in allowlist, altrimenti None."""
        origin = self.headers.get("Origin")
        return origin if origin and origin in ALLOWED_ORIGINS else None

    def _cors(self) -> None:
        # Riflette l'Origin SOLO se autorizzato (mai '*'): il browser blocca la
        # lettura della risposta dalle origini non in allowlist.
        allow = self._allow_origin()
        if allow:
            self.send_header("Access-Control-Allow-Origin", allow)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_fixture_id(self, parsed) -> object:
        """fixture_id da query string oppure da body JSON. None se assente/illeggibile."""
        qs = parse_qs(parsed.query)
        if qs.get("fixture_id"):
            return qs["fixture_id"][0]
        try:
            length = min(int(self.headers.get("Content-Length") or 0), _MAX_BODY_BYTES)
            if length > 0:
                raw = self.rfile.read(length)
                body = json.loads(raw or b"{}")
                if isinstance(body, dict):
                    return body.get("fixture_id")
        except (ValueError, json.JSONDecodeError):
            return None
        return None

    def _read_json_body(self) -> dict:
        """Corpo JSON della richiesta come dict ({} se assente/illeggibile). Limita la
        lettura a _MAX_BODY_BYTES (anti-abuso da client locale)."""
        try:
            length = min(int(self.headers.get("Content-Length") or 0), _MAX_BODY_BYTES)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            body = json.loads(raw or b"{}")
            return body if isinstance(body, dict) else {}
        except (ValueError, json.JSONDecodeError):
            return {}

    # --- preflight CORS ---
    def do_OPTIONS(self) -> None:  # noqa: N802 - nome richiesto da BaseHTTPRequestHandler
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        # Difesa CSRF: se la richiesta arriva da un browser (header Origin presente)
        # e l'origine NON è in allowlist, RIFIUTA prima di toccare Betfair. Così un
        # sito malevolo non può nemmeno innescare il side-effect (chiamate REST).
        # I client non-browser (es. curl) non inviano Origin → consentiti.
        origin = self.headers.get("Origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            self._json(403, {"ok": False, "error": "origine non autorizzata"})
            return

        parsed = urlparse(self.path)
        if parsed.path == "/refresh-odds":
            self._handle_refresh(parsed)
            return
        if parsed.path == "/place-order":
            self._handle_place_order()
            return
        self._json(404, {"ok": False, "error": "endpoint non trovato"})

    def _handle_refresh(self, parsed) -> None:
        raw_fid = self._read_fixture_id(parsed)
        try:
            fixture_id = int(raw_fid)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "fixture_id mancante o non valido"})
            return

        # import lazy: il modulo è caricabile anche dove odds_refresh non serve.
        from Betfair.odds_refresh import refresh_fixture_odds, BetfairLimitHit
        try:
            result = refresh_fixture_odds(fixture_id)
        except BetfairLimitHit as ex:
            self._json(429, {"ok": False, "fixture_id": fixture_id,
                             "error": "limite Betfair raggiunto (riprova tra poco)",
                             "detail": str(ex)[:140]})
            return
        except Exception:  # noqa: BLE001 - dettaglio solo nel log, mai nel body
            logger.exception("[odds-http] refresh fixture %s fallito", fixture_id)
            self._json(500, {"ok": False, "fixture_id": fixture_id, "error": "errore interno del runner (vedi log)"})
            return

        self._json(200, result)

    def _handle_place_order(self) -> None:
        """POST /place-order — piazza UN ordine reale (money-critical)."""
        body = self._read_json_body()

        def _opt_float(v):
            if v is None or v == "":
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        try:
            fixture_id = int(body.get("fixture_id"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            self._json(400, {"ok": False, "error": "fixture_id mancante o non valido"})
            return
        market = body.get("market")
        selection = body.get("selection")
        side = body.get("side")
        if not market or not selection or not side:
            self._json(400, {"ok": False, "error": "market/selection/side obbligatori"})
            return
        price = _opt_float(body.get("price"))
        if price is None:
            self._json(400, {"ok": False, "error": "price mancante o non valido"})
            return
        # cap OBBLIGATORIO lato server (tripwire anti-errore): vale anche per client
        # non-browser che bypassano la UI.
        max_stake = _opt_float(body.get("max_stake"))
        if max_stake is None or max_stake <= 0:
            self._json(400, {"ok": False, "error": "cap massimo stake (max_stake) obbligatorio e > 0"})
            return

        from Betfair.order_exec import place_order, OrderBusy
        from Betfair.odds_refresh import BetfairLimitHit
        try:
            result = place_order(
                fixture_id, str(market), str(selection), str(side), price,
                size=_opt_float(body.get("size")),
                liability=_opt_float(body.get("liability")),
                persistence=str(body.get("persistence") or "LAPSE"),
                fill_or_kill=bool(body.get("fill_or_kill")),
                min_fill_size=_opt_float(body.get("min_fill_size")),
                max_stake=max_stake,
            )
        except OrderBusy as ex:
            self._json(503, {"ok": False, "error": str(ex)[:160]})
            return
        except BetfairLimitHit as ex:
            self._json(429, {"ok": False, "error": "limite Betfair raggiunto (riprova tra poco)",
                             "detail": str(ex)[:140]})
            return
        except ValueError as ex:
            # errore di validazione input (stake/tick/mercato non disponibile, ...):
            # i ValueError sono messaggi nostri, sicuri da mostrare.
            self._json(400, {"ok": False, "error": str(ex)[:200]})
            return
        except Exception:  # noqa: BLE001 - dettaglio solo nel log, mai nel body
            logger.exception("[odds-http] place-order fixture %s fallito", fixture_id)
            self._json(500, {"ok": False, "error": "errore interno del runner (vedi log)"})
            return

        self._json(200, result)

    # silenzia il logging riga-per-riga di BaseHTTPRequestHandler su stderr.
    def log_message(self, *args) -> None:  # noqa: ARG002 - override: parametri ignorati di proposito
        return


def start_odds_http_server():
    """Avvia il server in un thread daemon. Ritorna l'istanza server, o None se la
    porta è occupata (in tal caso l'endpoint è solo non disponibile: il runner
    prosegue normale)."""
    try:
        srv = ThreadingHTTPServer((ODDS_HTTP_HOST, ODDS_HTTP_PORT), _Handler)
    except OSError as ex:
        logger.warning("[odds-http] avvio su %s:%s fallito (%s) — 'Aggiorna quote' non disponibile",
                       ODDS_HTTP_HOST, ODDS_HTTP_PORT, ex)
        return None
    thread = threading.Thread(target=srv.serve_forever, name="odds-http", daemon=True)
    thread.start()
    logger.info("[odds-http] in ascolto su http://%s:%s/refresh-odds", ODDS_HTTP_HOST, ODDS_HTTP_PORT)
    return srv
