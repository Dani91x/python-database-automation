"""db.py — scritture Supabase dello scanner Safe Strategy (service_role).

Pattern del repo (Betfair/stream/db.py): upsert IDEMPOTENTI, best-effort con
log; se la migrazione safe_strategy_scan.sql non è applicata il servizio NON
muore — warning una-tantum e si continua (modalità di fatto dry).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db_client import get_supabase_client


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

logger = logging.getLogger(__name__)

_MISSING_TABLE_WARNED = False

# event_id per SELECT nella rilettura del pre_ko (URL della query: mai troppo lunga)
_PRE_KO_CHUNK = 40


def _warn_missing_table(exc: Exception) -> None:
    global _MISSING_TABLE_WARNED  # noqa: PLW0603 - log una-tantum
    if not _MISSING_TABLE_WARNED:
        _MISSING_TABLE_WARNED = True
        logger.warning(
            "[safe-scan] tabella safe_strategy_scan non disponibile: migrazione "
            "migrations/safe_strategy_scan.sql non applicata? Lo scanner continua "
            "senza scrivere (il frontend non vedrà nulla finché non la applichi). "
            "Dettaglio: %s",
            str(exc)[:160],
        )


def _is_missing_table(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "does not exist" in msg or "42p01" in msg or "pgrst205" in msg or "could not find" in msg


def list_scan_event_ids() -> Optional[List[str]]:
    """event_id presenti in tabella (per la pulizia delle righe orfane di
    istanze precedenti); None se la lettura fallisce."""
    sb = get_supabase_client()
    try:
        res = sb.table("safe_strategy_scan").select("event_id").execute()
        return [str(r["event_id"]) for r in (getattr(res, "data", None) or []) if r.get("event_id")]
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            _warn_missing_table(e)
        else:
            logger.warning("[safe-scan] lettura event_id KO: %s", str(e)[:160])
        return None


def load_scan_pre_ko(event_ids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
    """Riferimenti 1X2 pre-KO gia' salvati, per gli event_id richiesti.

    Perche' esiste (CERT. 13/09, causa radice di "base e punta non scattano
    mai"): ``pre_ko`` viveva SOLO nella RAM dello scanner. ``freeze_pre_ko`` lo
    cattura solo PRIMA del calcio d'inizio e lo congela al primo tick in-play;
    a ogni riavvio del servizio (chiusura dell'app, crash + watchdog, modifica
    al codice) lo stato si azzerava e, per tutte le partite gia' in corso, il
    riferimento non poteva piu' nascere. Senza ``pre_ko`` non c'e' ``pre_match``,
    senza ``pre_match`` ``favorite_side`` torna None e i check di BASE e PUNTA
    escono ``ok=None`` -> stato "nd" -> scartate in silenzio. ESATTO non usa
    ``pre_ko`` in nessun punto: era l'unica a sopravvivere.

    Il dato era gia' sul DB (``safe_strategy_scan.payload.pre_ko``): era il
    codice stesso a distruggerlo, riscrivendo la riga con None al primo publish
    dopo il riavvio. Qui lo si rilegge.

    Lettura MIRATA (mai tutta la tabella: il payload e' grosso e la SELECT piena
    va in timeout) e a BLOCCHI, con la sola proiezione ``payload->pre_ko``.
    Best-effort come tutto il modulo: su errore torna quello che ha raccolto.
    """
    out: Dict[str, Optional[Dict[str, Any]]] = {}
    ids = [str(e) for e in (event_ids or []) if e]
    if not ids:
        return out
    sb = get_supabase_client()
    for i in range(0, len(ids), _PRE_KO_CHUNK):
        chunk = ids[i:i + _PRE_KO_CHUNK]
        try:
            res = (
                sb.table("safe_strategy_scan")
                .select("event_id,payload->pre_ko")
                .in_("event_id", chunk)
                .execute()
            )
        except Exception as e:  # noqa: BLE001 - mai fatale: si continua senza
            if _is_missing_table(e):
                _warn_missing_table(e)
            else:
                logger.warning("[safe-scan] rilettura pre_ko KO: %s", str(e)[:160])
            # si torna cio' che si e' raccolto: i blocchi NON interrogati non
            # compaiono nel risultato, quindi il chiamante li ritenta (review 13/09)
            return out
        # ogni evento del blocco entra nel risultato, anche quando il
        # riferimento non c'e': "cercato e non trovato" e' un esito, e non va
        # confuso con "non ancora cercato"
        trovati = {str(r.get("event_id") or ""): r.get("pre_ko")
                   for r in (getattr(res, "data", None) or [])}
        for eid in chunk:
            pre = trovati.get(eid)
            out[eid] = dict(pre) if is_usable_pre_ko(pre) else None
    return out


def is_usable_pre_ko(pre: Any) -> bool:
    """Tripla 1X2 completa e numerica: la STESSA condizione che ``engine`` usa
    per costruire ``pre_match``. Un riferimento parziale non serve a nulla e non
    deve essere reidratato (meglio None, cosi' ``freeze_pre_ko`` puo' ancora
    catturarlo se la partita non e' ancora iniziata)."""
    if not isinstance(pre, dict):
        return False
    for k in ("home", "draw", "away"):
        v = pre.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        if not (v > 1.0):
            return False
    return True


def upsert_scan_rows(rows: List[Dict[str, Any]]) -> bool:
    """Upsert delle righe evento (on_conflict event_id). True se scritte."""
    if not rows:
        return True
    sb = get_supabase_client()
    try:
        sb.table("safe_strategy_scan").upsert(rows, on_conflict="event_id").execute()
        return True
    except Exception as e:  # noqa: BLE001 - best-effort, mai uccidere lo scanner
        if _is_missing_table(e):
            _warn_missing_table(e)
        else:
            logger.warning("[safe-scan] upsert righe KO: %s", str(e)[:160])
        return False


def delete_scan_rows(event_ids: List[str]) -> None:
    if not event_ids:
        return
    sb = get_supabase_client()
    try:
        sb.table("safe_strategy_scan").delete().in_("event_id", event_ids).execute()
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            _warn_missing_table(e)
        else:
            logger.warning("[safe-scan] delete righe KO: %s", str(e)[:160])


def upsert_status(payload: Dict[str, Any]) -> None:
    sb = get_supabase_client()
    try:
        # updated_at ESPLICITO (bug visto dal vivo 09/09): il DEFAULT now() vale
        # solo all'INSERT — l'upsert aggiornava il payload ma lasciava la data
        # della prima riga (02/09) → la UI diceva "scanner non attivo, heartbeat
        # 575530s fa" con lo scanner vivo.
        sb.table("safe_strategy_status").upsert(
            {"id": "scanner", "payload": payload, "updated_at": _now_iso()}, on_conflict="id"
        ).execute()
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            _warn_missing_table(e)
        else:
            logger.warning("[safe-scan] upsert status KO: %s", str(e)[:160])


_MIKE_TERMINAL_STATES = ("SETTLED", "ERROR", "SKIPPED")


_MIKE_IDLE_STATES = ("WATCH", "IDLE_LIVE")
# stati delle gambe che rappresentano un IMPEGNO reale (ordine vivo o posizione)
_MIKE_LIVE_LEG_STATUS = ("pending", "pending_reconcile", "open")


def _mike_has_exposure(row: dict) -> bool:
    """True se la partita ha DAVVERO qualcosa da proteggere: uno stato operativo
    (non WATCH/IDLE_LIVE) oppure almeno una gamba con un ordine vivo o una
    posizione abbinata. H4 (review): esentare anche le partite in sola
    osservazione regalava le quote di ~10 mercati a testa a partite senza un
    euro sopra."""
    state = str(row.get("state") or "")
    if state in _MIKE_TERMINAL_STATES:
        return False
    for leg in row.get("positions") or []:
        if not isinstance(leg, dict):
            continue
        if str(leg.get("status") or "") in _MIKE_LIVE_LEG_STATUS and not leg.get("archived"):
            return True
        try:
            if float(leg.get("matched") or 0.0) > 0 and not leg.get("archived"):
                return True
        except (TypeError, ValueError):
            continue
    return state not in _MIKE_IDLE_STATES


def _mike_exposure(row: dict) -> float:
    """Quanto denaro Mike ha DAVVERO sopra questa partita.

    Somma le gambe con un ordine vivo o una posizione abbinata, prendendo la
    grandezza piu' grande fra ``liability`` e ``matched``/``size``: serve solo a
    ORDINARE, non a fare conti, quindi si sbaglia per eccesso invece che per
    difetto (una partita non deve mai finire in coda per un campo mancante)."""
    tot = 0.0
    for leg in row.get("positions") or []:
        if not isinstance(leg, dict) or leg.get("archived"):
            continue
        if str(leg.get("status") or "") not in _MIKE_LIVE_LEG_STATUS:
            try:
                if float(leg.get("matched") or 0.0) <= 0:
                    continue
            except (TypeError, ValueError):
                continue
        peso = 0.0
        for campo in ("liability", "matched", "size"):
            try:
                peso = max(peso, abs(float(leg.get(campo) or 0.0)))
            except (TypeError, ValueError):
                continue
        tot += peso
    return tot


def list_mike_followed_event_ids() -> Optional[List[str]]:
    """event_id delle partite di Mike con ESPOSIZIONE (ordini vivi o posizione).

    Servono allo scanner per esentarle dal tetto dei 20 eventi del motore
    opportunità (audit 11/09 C1): una posizione aperta senza le sue linee O/U nel
    feed è senza copertura, senza cash out e senza uscita. Le partite in sola
    osservazione (WATCH/IDLE_LIVE senza gambe) NON sono esenti: non hanno nulla
    da proteggere e peserebbero sul pool stream per niente (H4).
    None se la lettura fallisce (tabella assente = Mike mai installato)."""
    try:
        sb = get_supabase_client()
        res = (
            sb.table("mike_events")
            .select("event_id,state,positions")
            .not_.in_("state", list(_MIKE_TERMINAL_STATES))
            .execute()
        )
        righe = [r for r in (getattr(res, "data", None) or [])
                 if r.get("event_id") and _mike_has_exposure(r)]
        # CERT. 13/09 — ORDINE PER SOLDI A RISCHIO, decrescente.
        # La lista viene TRONCATA a valle (tetto ``MIKE_MAX_FOLLOWED``) e prima
        # il taglio seguiva l'ordine dei candidati dello scanner, cioe' "minuti
        # piu' avanzati per primi": cadevano le partite APPENA INIZIATE, che
        # sono esattamente quelle dove la copertura Over 4.5 serve di piu'.
        # Il tetto non si puo' togliere (pesa sul pool dello stream), ma chi
        # resta fuori dev'essere chi ha MENO denaro sopra, mai il contrario.
        righe.sort(key=lambda r: _mike_exposure(r), reverse=True)
        return [str(r["event_id"]) for r in righe]
    except Exception as e:  # noqa: BLE001 - best effort, mai fatale
        if not _is_missing_table(e):
            logger.warning("[safe-scan] lettura mike_events KO: %s", str(e)[:160])
        return None
