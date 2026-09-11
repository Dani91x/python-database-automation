"""bot_service — supervisore/loop del BOT della sezione SAFE STRATEGY.

Un unico processo locale (lock 127.0.0.1:47318) che, come ``omega_service``:
  a) risolve i 'pending' in attesa dell'esito dalla coda flumine (paper e live);
  b) regola i trade aperti/hedged al settlement del mercato;
  c) esegue SEMPRE le richieste della UI (place / cashout / cancel), anche a bot
     fermo — fermare il bot blocca i NUOVI ingressi automatici, non la gestione
     delle posizioni già aperte;
  c-bis) applica SEMPRE le regole di USCITA automatica (``exits``: profit/time/
     loss/rosso/obbligo tennis) ai trade 'open' di origine 'auto' delle 4
     strategie, chiudendoli a mercato con ``execution.close_trade``;
  d) se ``status='running'``, valuta i segnali del motore Safe Strategy sul FEED
     UNICO (``safe_strategy_scan``) e piazza con pattern RESERVE-FIRST;
  e) calcola le OPPORTUNITÀ di modello per la UI (throttled) — fuse con le
     ANOMALIE (``anomaly``), le COMBO (``combos``) e le opportunità TENNIS
     (``tennis_opportunity``), moduli opzionali importati in modo guardato — e,
     solo se esplicitamente abilitato per tipo, le tratta; le anomalie sono
     valutate a OGNI ciclo (cecchino) sulle righe con quote cambiate;
  f) scrive stats + heartbeat.

RISCHIO: ogni piazzamento (segnali, modello, anomalie, combo, tennis) passa da
``risk.check`` PRIMA della riserva (loss stop giornaliero, cap per evento e
giornata, posizioni per evento); le richieste manuali della UI hanno il solo
controllo "morbido" dei cap. Un blocco produce il log 'risk_block' (deduplicato).

MODALITÀ: il ``mode`` viene SEMPRE dal control (toggle PAPER/LIVE + conferma
della UI, come Omega). Nessun percorso qui promuove un paper a live.

Fail-closed ovunque: qualunque errore viene loggato e il loop continua.
Testabilità: ``run_once`` accetta ``db``/``market``/``engine``/``opportunity``
iniettati → ciclo verificabile con fake, senza Betfair né Supabase.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from Betfair.omega import omega_market as _real_market
from Betfair.safe_strategy import bot_db as _real_db
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import exits as XE
from Betfair.safe_strategy import risk as RK

logger = logging.getLogger("safe.bot")

_SINGLE_INSTANCE_PORT = 47318  # omega=47313, tennis=47312, safe bot=47318

# strategie ammesse in colonna (CHECK del DB): mai valori liberi.
_STRATEGIES = ("base", "esatto", "punta", "tennis", "model", "manual")

# Parametri di DEFAULT del bot (fusi con quelli del motore via merge_params).
DEFAULT_PARAMS: dict[str, Any] = {
    "poll_interval_s": 2,
    "commission_pct": 5,
    "variants": ["base", "esatto", "punta", "tennis"],
    "max_open_trades": 20,
    "max_liability_per_trade": 300,
    "min_size_available_factor": 1.0,
    "opps_interval_s": 10,
    "auto_trade_opportunities": False,
    # tipi aggiuntivi di opportunità (moduli opzionali): tutti SPENTI per default
    "auto_trade_anomalies": False,
    "auto_trade_combos": False,
    "auto_trade_tennis": False,
    "opps_min_confidence": 0.7,
    "opps_min_edge": 0.03,
    "opps_stake": 5,
    # H-21: budget di ritentativi del PIAZZAMENTO automatico rifiutato
    # dall'exchange (FOK ucciso, liquidita' sparita): oltre questo la chiave del
    # segnale e' chiusa per la partita (log 'place_exhausted'), con backoff
    # crescente fra un tentativo e il successivo (exits.RETRY_BACKOFF_S).
    "place_max_attempts": 3,
    # log 'skip' del piazzamento: una volta per (segnale, motivo), poi solo al
    # cambio di motivo o dopo questo intervallo (anti-spam dell'activity log)
    "skip_log_interval_s": 300,
    # GATE SPREAD all'ingresso: lay/back della selezione dal feed oltre questo
    # rapporto (o back assente) = mercato non tradabile → segnale scartato
    "max_spread_ratio": 1.6,
    # ESECUZIONE via coda flumine: chiavi lette dal codice CONDIVISO con Omega
    # (``omega_service._flumine_gate`` / ``poll_flumine_pending``). Prima non
    # erano dichiarate qui e la Safe Strategy ereditava in silenzio i default di
    # Omega — compreso ``min_stake`` 0,50 € invece del minimo REALE Betfair di
    # 2 € (L-audit "chiavi Omega usate dal codice condiviso" + M-31).
    "execution_mode": "auto",           # 'auto' = coda quando possibile, 'rest' = solo REST
    "omega_live_via_flumine": True,     # nome della chiave del gate condiviso
    "paper_fill_ttl_s": 45,             # quasi-FOK del paper: poi cancel del residuo
    "live_fill_deadline_s": 20,         # oltre: riconciliazione REST / revoca
    "min_stake": 2.0,                   # minimo REALE Betfair (M-31)
    # regole di uscita automatica (sezione fusa in profondità: exits.merge_exit_params)
    "exits": dict(XE.DEFAULT_EXIT_PARAMS),
    # motore di rischio di tutti i piazzamenti (sezione fusa: risk.merge_risk_params)
    "risk": dict(RK.DEFAULT_RISK_PARAMS),
}


# ---------------------------------------------------------------------------
# Import GUARDATI dei moduli scritti dagli altri cantieri: se mancano, il
# servizio parte lo stesso (log esplicito) e si limita a ciò che sa fare.
# ---------------------------------------------------------------------------
def _import_engine_module() -> Any:
    try:
        from Betfair.safe_strategy import engine as _eng

        return _eng
    except ImportError as ex:
        logger.error("[safe.bot] motore segnali NON disponibile (%s): il bot NON "
                     "piazzera' segnali automatici finche' Betfair/safe_strategy/"
                     "engine.py non e' presente.", str(ex)[:160])
        return None


def _import_opportunity_module() -> Any:
    try:
        from Betfair.safe_strategy import opportunity as _opp

        return _opp
    except ImportError as ex:
        logger.warning("[safe.bot] modulo opportunita' NON disponibile (%s): "
                       "sezione opportunita' disattivata.", str(ex)[:160])
        return None


_OPTIONAL_MODS: dict[str, Any] = {}
OPTIONAL_MODULES = ("anomaly", "combos", "tennis_opportunity")


def _import_optional(name: str) -> Any:
    """Modulo opzionale ``Betfair.safe_strategy.<name>`` (anomaly / combos /
    tennis_opportunity): None se assente — il bot lavora senza (log una volta)."""
    if name in _OPTIONAL_MODS:
        return _OPTIONAL_MODS[name]
    try:
        import importlib

        mod = importlib.import_module(f"Betfair.safe_strategy.{name}")
    except Exception as ex:  # noqa: BLE001 — assente o rotto: si va avanti senza
        logger.info("[safe.bot] modulo opzionale '%s' non disponibile: %s", name, str(ex)[:120])
        mod = None
    _OPTIONAL_MODS[name] = mod
    return mod


def _extra_mods(extra: Optional[dict]) -> dict[str, Any]:
    """{'anomaly','combos','tennis'}: iniettati (test) o importati in modo guardato."""
    if isinstance(extra, dict):
        return {"anomaly": extra.get("anomaly"), "combos": extra.get("combos"),
                "tennis": extra.get("tennis")}
    return {"anomaly": _import_optional("anomaly"), "combos": _import_optional("combos"),
            "tennis": _import_optional("tennis_opportunity")}


def _omega_service() -> Any:
    try:
        from Betfair.omega import omega_service as _os

        return _os
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] omega_service non importabile: %s", str(ex)[:160])
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Parametri
# ---------------------------------------------------------------------------
def resolve_params(raw: Optional[dict[str, Any]], engine_mod: Any = None) -> dict[str, Any]:
    """Default motore + default bot + override utente (l'utente ha l'ultima parola),
    con CLAMP sulle chiavi money-critical."""
    raw = dict(raw or {})
    out: dict[str, Any] = {}
    eng_defaults = getattr(engine_mod, "DEFAULT_PARAMS", None) if engine_mod else None
    if isinstance(eng_defaults, dict):
        out.update(eng_defaults)
    out.update(DEFAULT_PARAMS)
    merge = getattr(engine_mod, "merge_params", None) if engine_mod else None
    handled: set[str] = set()
    if callable(merge):
        try:
            merged = merge(raw)
            if isinstance(merged, dict):
                out.update(merged)
                # le SEZIONI del motore (base/esatto/punta/tennis/stake) sono già
                # fuse in profondità da merge_params: ri-applicarci sopra il raw
                # grezzo sostituirebbe la sezione completa con quella parziale.
                handled = set(eng_defaults or {})
        except Exception as ex:  # noqa: BLE001 — motore rotto: si usa il raw grezzo
            logger.warning("[safe.bot] merge_params KO: %s", str(ex)[:160])
    for k, v in raw.items():
        if k not in handled:
            out[k] = v
    out["poll_interval_s"] = max(1.0, _f(out.get("poll_interval_s"), 2.0))
    out["commission_pct"] = min(20.0, max(0.0, _f(out.get("commission_pct"), 5.0)))
    out["max_open_trades"] = max(0, int(_f(out.get("max_open_trades"), 20)))
    out["max_liability_per_trade"] = max(0.0, _f(out.get("max_liability_per_trade"), 300.0))
    out["min_size_available_factor"] = max(0.0, _f(out.get("min_size_available_factor"), 1.0))
    out["opps_interval_s"] = max(1.0, _f(out.get("opps_interval_s"), 10.0))
    out["opps_stake"] = max(0.0, _f(out.get("opps_stake"), 5.0))
    out["skip_log_interval_s"] = max(0.0, _f(out.get("skip_log_interval_s"), 300.0))
    out["max_spread_ratio"] = max(1.0, _f(out.get("max_spread_ratio"), 1.6))
    out["place_max_attempts"] = int(min(20, max(1, _f(out.get("place_max_attempts"), 3))))
    # chiavi dell'esecuzione condivisa con Omega: clamp esplicito (mai lasciare
    # che un valore assurdo dal DB arrivi al codice della coda)
    out["execution_mode"] = "rest" if str(out.get("execution_mode") or "auto") == "rest" else "auto"
    out["omega_live_via_flumine"] = bool(out.get("omega_live_via_flumine"))
    out["paper_fill_ttl_s"] = int(min(600, max(5, _f(out.get("paper_fill_ttl_s"), 45))))
    out["live_fill_deadline_s"] = int(min(300, max(5, _f(out.get("live_fill_deadline_s"), 20))))
    out["min_stake"] = min(1000.0, max(0.0, _f(out.get("min_stake"), 2.0)))
    # M-32: soglie delle opportunita' SEMPRE numeriche e nel loro dominio —
    # un valore non numerico sul DB spegneva il bot senza dirlo.
    out["opps_min_confidence"] = min(1.0, max(0.0, _f(out.get("opps_min_confidence"), 0.7)))
    out["opps_min_edge"] = min(1.0, max(-1.0, _f(out.get("opps_min_edge"), 0.03)))
    # H-14: 'variants' deve essere una LISTA NON VUOTA di varianti valide; una
    # lista vuota (o con soli valori ignoti) spegneva il bot in silenzio mentre
    # la UI mostrava 4 strategie attive → si torna ai default.
    out["variants"] = normalize_variants(out.get("variants"))
    # ``exits`` parziale dell'utente → sezione completa (default + override + clamp)
    out["exits"] = XE.merge_exit_params(raw.get("exits"))
    out["risk"] = RK.merge_risk_params(raw.get("risk"))
    for k in ("auto_trade_opportunities", "auto_trade_anomalies", "auto_trade_combos",
              "auto_trade_tennis"):
        out[k] = bool(out.get(k))
    return out


def _f(v: Any, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f else default  # NaN → default


# varianti ammesse nel campo ``variants`` (le 4 strategie del manuale)
VALID_VARIANTS = ("base", "esatto", "punta", "tennis")


def normalize_variants(raw: Any) -> list[str]:
    """Lista di varianti VALIDE e non vuota (H-14): default se il DB porta
    ``[]``, un non-elenco o solo valori ignoti."""
    if isinstance(raw, (list, tuple, set)):
        keep = [str(v) for v in raw if str(v) in VALID_VARIANTS]
        # ordine stabile del manuale (non quello casuale di un set)
        if keep:
            return [v for v in VALID_VARIANTS if v in keep]
    return list(DEFAULT_PARAMS["variants"])


# chiavi money-critical su cui la UI mostra un numero: se il servizio le CLAMPA
# in memoria, il DB va riallineato o l'utente legge un valore che non è in uso
# (H-15: daily_loss_stop=50 → 0 = stop spento, ma la scheda mostrava 50).
_SCALAR_PARAM_KEYS = ("poll_interval_s", "commission_pct", "max_open_trades",
                      "max_liability_per_trade", "min_size_available_factor",
                      "opps_interval_s", "opps_stake", "skip_log_interval_s",
                      "max_spread_ratio", "place_max_attempts",
                      "opps_min_confidence", "opps_min_edge",
                      "paper_fill_ttl_s", "live_fill_deadline_s", "min_stake")


def params_effective(resolved: dict[str, Any]) -> dict[str, Any]:
    """I valori REALMENTE in uso (clampati/normalizzati) da esporre alla UI."""
    out: dict[str, Any] = {k: resolved.get(k) for k in _SCALAR_PARAM_KEYS}
    out["variants"] = list(resolved.get("variants") or [])
    out["execution_mode"] = resolved.get("execution_mode")
    for k in ("auto_trade_opportunities", "auto_trade_anomalies",
              "auto_trade_combos", "auto_trade_tennis", "omega_live_via_flumine"):
        out[k] = bool(resolved.get(k))
    out["exits"] = dict(resolved.get("exits") or {})
    out["risk"] = dict(resolved.get("risk") or {})
    return out


def params_corrections(raw: Optional[dict[str, Any]],
                       resolved: dict[str, Any]) -> dict[str, Any]:
    """Chiavi presenti nel control il cui valore EFFETTIVO differisce da quello
    scritto (o non valido): {chiave: {'stored','effective'}}. Solo le chiavi che
    l'utente ha davvero messo sul DB — mai i default del motore."""
    raw = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {}
    for k in _SCALAR_PARAM_KEYS:
        if k not in raw:
            continue
        eff, stored = resolved.get(k), raw.get(k)
        if stored == eff:
            continue                      # identico: nessuna correzione
        try:
            same = (stored is not None and eff is not None
                    and abs(float(stored) - float(eff)) < 1e-9)
        except (TypeError, ValueError):
            same = False
        if not same:
            out[k] = {"stored": stored, "effective": eff}
    if "variants" in raw and list(raw.get("variants") or []) != list(resolved.get("variants") or []):
        out["variants"] = {"stored": raw.get("variants"),
                           "effective": list(resolved.get("variants") or [])}
    for sec, merge in (("exits", XE.merge_exit_params), ("risk", RK.merge_risk_params)):
        src = raw.get(sec)
        if not isinstance(src, dict):
            continue
        eff = merge(src)
        diff = {}
        for k, v in src.items():
            if k not in eff:
                continue
            if v == eff[k]:
                continue                  # identico (anche None o bool)
            try:
                if v is not None and eff[k] is not None \
                        and abs(float(v) - float(eff[k])) < 1e-9:
                    continue
            except (TypeError, ValueError):
                pass
            diff[k] = {"stored": v, "effective": eff[k]}
        if diff:
            out[sec] = diff
    return out


# Chiavi che il servizio NON riscrive MAI sul DB (review H2): un clamp che
# diventa persistente DISTRUGGE l'intenzione dell'utente e la sua impostazione.
# ``daily_loss_stop: 50`` clampato a 0 e salvato = stop perdite SPENTO PER
# SEMPRE. Queste si correggono solo IN MEMORIA e si mostrano in
# ``params_effective`` + attività ``params_clamped``.
_NEVER_PERSIST = frozenset({"daily_loss_stop", "daily_liability_cap",
                            "per_event_liability_cap", "model_daily_liability_cap",
                            "model_stake", "max_liability_per_trade",
                            "commission_pct", "min_stake", "opps_stake"})


def normalize_control_params(db, raw: Optional[dict[str, Any]],
                             resolved: dict[str, Any], now: datetime) -> dict[str, Any]:
    """H-14/H-15: rende VISIBILE la differenza fra ciò che c'è sul DB e ciò che
    è davvero in uso, e normalizza sul DB SOLO ciò che è strutturalmente
    invalido e non money-critical (tipicamente ``variants: []`` → default).

    Attività: ``params_invalid`` (valore non utilizzabile: varianti azzerate,
    testo al posto di un numero) e ``params_clamped`` (valore valido ma fuori
    scala: il servizio usa il clamp e lo dice, senza toccare il DB).
    Idempotente. Ritorna le correzioni rilevate."""
    corr = params_corrections(raw, resolved)
    if not corr:
        return {}
    invalid: dict[str, Any] = {}
    clamped: dict[str, Any] = {}
    for k, v in corr.items():
        if k in ("exits", "risk"):
            for kk, vv in v.items():
                bucket = invalid if _is_invalid_value(vv.get("stored")) else clamped
                bucket.setdefault(k, {})[kk] = vv
        elif k == "variants" or _is_invalid_value(v.get("stored")):
            invalid[k] = v
        else:
            clamped[k] = v
    # sul DB si riscrive SOLO l'invalido non money-critical (H2)
    patched = dict(raw or {})
    persisted: list[str] = []
    for k, v in invalid.items():
        if k in ("exits", "risk"):
            sec = dict(patched.get(k) or {})
            for kk, vv in v.items():
                if kk in _NEVER_PERSIST:
                    continue
                sec[kk] = vv["effective"]
                persisted.append(f"{k}.{kk}")
            patched[k] = sec
        elif k not in _NEVER_PERSIST:
            patched[k] = v["effective"]
            persisted.append(k)
    if persisted:
        try:
            db.set_control(params=patched)
        except Exception as ex:  # noqa: BLE001 — mai fermare il ciclo per i parametri
            _log(db, "error", {"reason": "params_normalize_failed", "err": str(ex)[:160]})
    if invalid:
        _log(db, "params_invalid", {"keys": sorted(invalid), "corrections": invalid,
                                    "persisted": sorted(persisted),
                                    "ts": now.isoformat()})
    if clamped:
        _log(db, "params_clamped", {"keys": sorted(clamped), "corrections": clamped,
                                    "persisted": [], "ts": now.isoformat()})
    return corr


def _is_invalid_value(stored: Any) -> bool:
    """Valore NON utilizzabile (non un numero e non un booleano): è un errore di
    inserimento, non una scala sbagliata."""
    if isinstance(stored, bool):
        return False
    return not isinstance(stored, (int, float))


# ---------------------------------------------------------------------------
# Prezzi dal FEED UNICO (una SELECT per ciclo, condivisa da tutte le fasi)
# ---------------------------------------------------------------------------
# blocchi del feed (formato unico dello scanner: {market_id, selections[...]})
# indicizzati per market_type; ``ou`` è una LISTA (una voce per linea).
_FEED_BLOCK_BY_TYPE = {
    "CORRECT_SCORE": "cs", "HALF_TIME_SCORE": "ht",
    "BOTH_TEAMS_TO_SCORE": "btts", "HALF_TIME": "ht_result",
}
_FEED_BLOCK_KEYS = ("cs", "ht", "btts", "ht_result")


def prices_from_row(row: Optional[dict[str, Any]], *, market_type: str,
                    selection_id: int,
                    market_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    """{'back','back_size','lay','lay_size'} della selezione dal payload del feed.

    MATCH_ODDS → blocco ``odds`` (home/draw/away o p1/p2, ognuno col proprio
    selection_id). Gli altri mercati → blocchi a formato unico ``cs``/``ht``/
    ``btts``/``ht_result`` e la lista ``ou`` (una voce per linea), scelti per
    market_type e — se noto — per ``market_id`` (un trade di modello su O/U
    2.5 deve leggere la SUA linea). None se la selezione non è nel feed
    (→ fallback REST).
    """
    payload = (row or {}).get("payload")
    if not isinstance(payload, dict):
        return None
    mt = str(market_type or "").upper()
    mid = str(market_id) if market_id else None
    if mt == "MATCH_ODDS":
        odds = payload.get("odds")
        if not isinstance(odds, dict):
            return None
        for side_block in odds.values():
            if not isinstance(side_block, dict):
                continue
            if side_block.get("selection_id") is not None and \
                    int(side_block["selection_id"]) == int(selection_id):
                return _price_block(side_block)
        return None
    blocks: list[Any] = []
    key = _FEED_BLOCK_BY_TYPE.get(mt)
    if key:
        blocks.append(payload.get(key))
    if mt.startswith("OVER_UNDER"):
        blocks.extend(payload.get("ou") or [])
    if mid:  # il market_id è la chiave più forte: qualunque blocco che lo porti
        blocks.extend(payload.get(k) for k in _FEED_BLOCK_KEYS)
        blocks.extend(payload.get("ou") or [])
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        if mid and blk.get("market_id") and str(blk["market_id"]) != mid:
            continue
        for sel in blk.get("selections") or []:
            if isinstance(sel, dict) and sel.get("selection_id") is not None and \
                    int(sel["selection_id"]) == int(selection_id):
                return _price_block(sel)
    return None


def _price_block(src: dict[str, Any]) -> dict[str, Any]:
    return {
        "back": src.get("back"), "back_size": src.get("back_size"),
        "lay": src.get("lay"), "lay_size": src.get("lay_size"),
    }


# ---------------------------------------------------------------------------
# H-19 — BUDGET delle chiamate REST a Betfair. La fonte dei prezzi e' il FEED
# dello scanner (``safe_strategy_scan``): il REST e' solo un ripiego, con
# cadenza minima per mercato e un tetto per ciclo. Prima c'era una
# ``listMarketBook``/``read_market`` per posizione aperta OGNI 2 s.
# ---------------------------------------------------------------------------
REST_MIN_INTERVAL_S = 10.0     # mai due REST sullo stesso mercato piu' vicine
REST_BUDGET_PER_CYCLE = 8      # tetto duro di chiamate REST per ciclo
_REST_STATE: dict[str, Any] = {"last": {}, "cycle_ts": 0.0, "used": 0}


def rest_gate(market_id: Any, now_ts: float, *,
              state: Optional[dict] = None) -> bool:
    """True se una chiamata REST su ``market_id`` e' consentita ORA (e la
    contabilizza). Fail-closed sul budget: meglio aspettare il feed."""
    st = state if state is not None else _REST_STATE
    if float(st.get("cycle_ts") or 0.0) != now_ts:
        st["cycle_ts"] = now_ts
        st["used"] = 0
    last: dict = st.setdefault("last", {})
    key = str(market_id or "")
    prev = last.get(key)
    if prev is not None and now_ts - float(prev) < REST_MIN_INTERVAL_S:
        return False
    if int(st.get("used") or 0) >= REST_BUDGET_PER_CYCLE:
        return False
    st["used"] = int(st.get("used") or 0) + 1
    last[key] = now_ts
    for k in [k for k, v in last.items() if now_ts - float(v) > 3600.0]:
        last.pop(k, None)
    return True


def prices_for(*, market, rows_by_event: dict[str, dict], event_id: str,
               market_id: str, market_type: str, selection_id: int,
               allow_rest: bool = True,
               rest_now_ts: Optional[float] = None) -> Optional[dict[str, Any]]:
    """Prezzi dal feed; se assenti, FALLBACK REST (read_book) — mai decidere
    una chiusura/piazzamento su prezzi inventati.

    ``allow_rest=False`` → solo feed. ``rest_now_ts`` valorizzato → il REST
    passa dal ``rest_gate`` (H-19: cadenza ≥ 10 s per mercato, tetto per ciclo);
    budget esaurito → None. Le azioni MANUALI dell'utente non passano dal gate
    (sono una sola, non un ciclo): chiamano senza ``rest_now_ts``."""
    p = prices_from_row(rows_by_event.get(str(event_id)), market_type=market_type,
                        selection_id=selection_id, market_id=market_id)
    if p and (p.get("back") or p.get("lay")):
        return p
    if not allow_rest:
        return None
    if rest_now_ts is not None and not rest_gate(market_id, rest_now_ts):
        logger.debug("[safe.bot] REST non consentita ora su %s (budget/cadenza)", market_id)
        return None
    try:
        book = market.read_book(str(market_id), {})
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] read_book KO %s: %s", market_id, str(ex)[:160])
        return None
    if not book:
        return None
    if str(book.get("status") or "OPEN").upper() != "OPEN":
        return None
    for r in book.get("runners") or []:
        if int(r.get("selection_id") or -1) == int(selection_id):
            return {"back": r.get("back_price"), "back_size": r.get("back_size"),
                    "lay": r.get("lay_price"), "lay_size": r.get("lay_size"),
                    "lay_ladder": r.get("lay_ladder") or ()}
    return None


# ---------------------------------------------------------------------------
# (a) coda flumine — riuso del poll di Omega (stesso contratto di coda)
# ---------------------------------------------------------------------------
def poll_flumine(*, db, params: dict[str, Any], now: datetime, market=None) -> int:
    os_mod = _omega_service()
    if os_mod is None:
        return 0
    try:
        return int(os_mod.poll_flumine_pending(db=db, params=params, now=now, market=market) or 0)
    except Exception as ex:  # noqa: BLE001 — mai fermare il ciclo
        _log(db, "error", {"reason": "flumine_poll_failed", "err": str(ex)[:160]})
        return 0


# ---------------------------------------------------------------------------
# (a-bis) riconciliazione dei 'pending' SENZA marker flumine (port di
# omega_service.reconcile_pending su bot_db): esito REST ignoto / conferma DB
# fallita → si legge lo stato REALE su Betfair. Mai un fill reale non tracciato.
# ---------------------------------------------------------------------------
def reconcile_pending(*, market, db, now: datetime) -> int:
    try:
        pendings = list(db.list_trades("pending") or [])
    except Exception as ex:  # noqa: BLE001
        _log(db, "reconcile_error", {"reason": "list_failed", "err": str(ex)[:160]})
        return 0
    legacy = [t for t in pendings if not X.has_flumine_marker(t)]
    if not legacy:
        return 0
    n = 0
    # PAPER: nessun ordine reale.
    #  • riga marcata ``place_exception_reconciling``: il fill simulato e'
    #    ESPLOSO, quindi NON e' mai avvenuto → 'error' terminale (L-10: prima
    #    veniva confermata come se fosse stata abbinata al prezzo della riserva,
    #    inventando una posizione paper che il live non avrebbe avuto);
    #  • riga senza alcun marker (storica): si conferma coi dati della riserva.
    for tr in [t for t in legacy if str(t.get("mode")) == "paper"]:
        try:
            if X.is_reconciling(tr):
                _terminal_error(db, tr, reason="reconcile_paper_senza_fill", now=now,
                                extra={"how": "paper"})
                _log(db, "reconciled_error", {"trade_id": tr.get("id"),
                                              "event_id": tr.get("event_id"),
                                              "reason": "reconcile_paper_senza_fill",
                                              "how": "paper"})
                _sync_parent_of(db, tr, now)
            else:
                _reconcile_confirm(db, tr, price=float(tr.get("price") or 0.0),
                                   size=float(tr.get("size") or 0.0), bet_id=None,
                                   how="paper", now=now)
            n += 1
        except Exception as ex:  # noqa: BLE001
            _log(db, "reconcile_error", {"trade_id": tr.get("id"), "err": str(ex)[:160]})
    # FAIL-SAFE: tutto ciò che non è esplicitamente 'paper' si verifica su Betfair.
    live = [t for t in legacy if str(t.get("mode")) != "paper"]
    if not live:
        return n
    list_cur = getattr(market, "list_current_orders", None)
    list_clr = getattr(market, "list_cleared_orders", None)
    if not (callable(list_cur) and callable(list_clr)):
        _log(db, "reconcile_error", {"reason": "market_senza_list_orders",
                                     "pending_ids": [t.get("id") for t in live]})
        return n
    try:
        current = list_cur() or []
        cleared = list_clr() or []
    except Exception as ex:  # noqa: BLE001 — senza dati NON si decide
        _log(db, "reconcile_error", {"reason": "fetch_failed", "err": str(ex)[:160]})
        return n
    for tr in live:
        try:
            d = _reconcile_by_bet_id(market, tr)
            if d is None:
                d = X.reconcile_decision(tr, current, cleared, now.isoformat(),
                                         ref=f"safe-t{tr['id']}"[:32])
            act = d.get("action")
            if act == "confirm":
                _reconcile_confirm(db, tr, price=float(d["price"]), size=float(d["size"]),
                                   bet_id=d.get("bet_id"), how="live", now=now)
                n += 1
            elif act == "free":
                if X.is_reconciling(tr):
                    # C-03: la riconciliazione DEVE concludersi. Nessun ordine
                    # trovato su Betfair per una riga il cui place e' andato a
                    # esito ignoto: si chiude in 'error' TERMINALE con la traccia
                    # (mai una cancellazione muta di una riga che poteva avere
                    # un ordine reale).
                    _terminal_error(db, tr, reason="reconcile_ordine_assente", now=now,
                                    extra={"how": "live"})
                    _log(db, "reconciled_error", {"trade_id": tr.get("id"),
                                                  "event_id": tr.get("event_id"),
                                                  "reason": "reconcile_ordine_assente",
                                                  "how": "live"})
                else:
                    db.delete_trade(int(tr["id"]))
                    _log(db, "reconciled_free", {"trade_id": tr.get("id"),
                                                 "event_id": tr.get("event_id")})
                _sync_parent_of(db, tr, now)
                n += 1
            elif act == "error":
                _terminal_error(db, tr, reason="reconcile_orphan_old", now=now)
                _log(db, "reconciled_error", {"trade_id": tr.get("id"),
                                              "event_id": tr.get("event_id"),
                                              "reason": "reconcile_orphan_old"})
                _sync_parent_of(db, tr, now)
                n += 1
            # 'keep' → ordine reale non ancora matchato / troppo fresco: non toccare
        except Exception as ex:  # noqa: BLE001
            _log(db, "reconcile_error", {"trade_id": tr.get("id"), "err": str(ex)[:160]})
    return n


def _terminal_error(db, tr: dict[str, Any], *, reason: str, now: datetime,
                    extra: Optional[dict[str, Any]] = None) -> None:
    """Porta una riga in 'error' TERMINALE (M-05): meta CONSERVATO (L-09),
    ``error_final=True`` e ``settled_at`` valorizzato — così la riga non resta
    "in corso per sempre" negli aggregati e nello storico."""
    meta = {**(tr.get("meta") or {}), "reason": reason, "error_final": True,
            "error_at": now.isoformat(), **(extra or {})}
    try:
        db.update_trade(int(tr["id"]), status="error", settled_at=now.isoformat(),
                        meta=meta)
        tr["status"] = "error"
        tr["meta"] = meta
    except Exception as ex:  # noqa: BLE001
        _log(db, "error", {"reason": "terminal_error_failed", "trade_id": tr.get("id"),
                           "err": str(ex)[:160]})


def _reconcile_by_bet_id(market, tr: dict[str, Any]) -> Optional[dict]:
    """Se la riga porta già un bet_id, lo stato per betId è la chiave certa."""
    bet_id = tr.get("bet_id")
    fn = getattr(market, "order_state_by_bet_id", None)
    if not bet_id or not callable(fn):
        return None
    st = fn(str(bet_id))  # solleva su rete KO → il chiamante non decide
    if not st or not st.get("found"):
        return None
    matched = float(st.get("size_matched") or 0.0)
    if matched > 0 and float(st.get("size_remaining") or 0.0) <= 0:
        return {"action": "confirm", "price": float(st.get("avg_price_matched") or tr.get("price") or 0.0),
                "size": matched, "bet_id": str(bet_id)}
    return {"action": "keep"}


def _reconcile_confirm(db, tr: dict[str, Any], *, price: float, size: float,
                       bet_id: Optional[str], how: str, now: datetime) -> None:
    side = str(tr.get("side") or "back")
    meta = {**(tr.get("meta") or {}), "reconciled": how}
    meta.pop("phase", None)
    meta.pop("reason", None)
    db.update_trade(int(tr["id"]), status="open", price=price, size=round(size, 2),
                    liability=X.liability_of(side, size, price), bet_id=bet_id, meta=meta)
    _log(db, "reconciled_open", {"trade_id": tr.get("id"), "event_id": tr.get("event_id"),
                                 "bet_id": bet_id, "how": how, "size": round(size, 2),
                                 "price": price})
    _sync_parent_of(db, tr, now)


def _sync_parent_of(db, closing: dict[str, Any], now: datetime) -> None:
    """Se la riga risolta è una gamba di CHIUSURA, riallinea l'apertura
    (hedged_size/residuo/'hedged') sull'insieme reale delle sue chiusure."""
    pid = closing.get("closes_trade_id")
    if not pid:
        return
    try:
        parent = db.get_trade(int(pid))
        if not parent or str(parent.get("status")) not in ("open", "hedged"):
            return
        legs = db.closing_trades_for([int(pid)]) or []
        X.apply_hedge_state(db, parent, legs, now)
    except Exception as ex:  # noqa: BLE001
        _log(db, "error", {"reason": "sync_parent_failed", "trade_id": pid,
                           "err": str(ex)[:160]})


# ---------------------------------------------------------------------------
# (b) settlement (comprese le posizioni chiuse a mercato, in tutto o in parte)
# ---------------------------------------------------------------------------
MARKET_MISSING_LOG_EVERY_S = 300.0   # M-25: né silenzio né flood
MARKET_MISSING_MIN_FAILS = 3         # M11: 3 letture consecutive KO, non una
_MARKET_MISSING: dict[str, float] = {}


def _settlement_needs_rest(trade: dict[str, Any], row: Optional[dict],
                           now_ts: float) -> bool:
    """H-19: serve una lettura REST del mercato per decidere il settlement?

    NO se il FEED dice che il mercato della posizione è ancora APERTO e la
    partita è viva: un mercato aperto non si regola, la REST non aggiunge
    nulla. SÌ negli altri casi (evento fuori dal feed, mercato sospeso/chiuso,
    stato ignoto), e comunque con la cadenza/budget di ``rest_gate``."""
    if isinstance(row, dict):
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if XE.feed_is_fresh(row, now_ts) and XE.market_open(trade, payload) is True \
                and payload.get("inplay"):
            return False
    return True


def settle_open(*, params: dict[str, Any], market, db, now: datetime,
                rows_by_event: Optional[dict[str, dict]] = None) -> int:
    try:
        rows = list(db.open_trades() or [])
    except Exception as ex:  # noqa: BLE001
        _log(db, "error", {"reason": "open_trades_failed", "err": str(ex)[:160]})
        return 0
    if not rows:
        return 0
    rows_by_event = rows_by_event or {}
    now_ts = now.timestamp()
    parents = [r for r in rows if not r.get("closes_trade_id")]
    closing_rows = [r for r in rows if r.get("closes_trade_id")]
    parent_ids = {int(r["id"]) for r in parents}
    # chiusure di TUTTE le aperture vive (open/hedged), non solo delle 'hedged':
    # un'apertura con una chiusura confermata si regola SEMPRE in coppia.
    closings: dict[int, list[dict]] = {}
    if parent_ids:
        try:
            for c in db.closing_trades_for(sorted(parent_ids)) or []:
                closings.setdefault(int(c.get("closes_trade_id") or 0), []).append(c)
        except Exception as ex:  # noqa: BLE001 — senza le chiusure NON si regola
            _log(db, "error", {"reason": "closing_trades_failed", "err": str(ex)[:160]})
            return 0
    sync_hedges(db, parents, closings, now)
    fallback_commission = float(params.get("commission_pct", 5.0)) / 100.0
    settled = 0
    for tr in parents:
        try:
            row = rows_by_event.get(str(tr.get("event_id")))
            # H-19: il feed decide QUANDO vale la pena chiamare Betfair
            if not _settlement_needs_rest(tr, row, now_ts):
                continue
            if not rest_gate(tr.get("market_id"), now_ts):
                continue
            snap = _read_market(market, tr)
            if snap is None:
                _market_missing(db, tr, now_ts)
                continue
            _market_seen(str(tr.get("market_id") or ""))
            if not snap.closed:
                continue
            comm = tr.get("commission")
            comm = float(comm) if comm is not None else fallback_commission
            if X.settle_position(db=db, trade=tr, closings=closings.get(int(tr["id"]), []),
                                 snap=snap, commission=comm, now=now):
                settled += 1
        except Exception as ex:  # noqa: BLE001 — una riga rotta non blocca le altre
            _log(db, "settle_error", {"trade_id": tr.get("id"), "err": str(ex)[:160]})
            continue
    # gambe di chiusura ORFANE: apertura già regolata (ciclo interrotto tra le
    # due scritture) → si regolano con l'esito dedotto dall'apertura.
    # M-33: le SORELLE (altre chiusure della stessa apertura, es. parziale +
    # residuo) entrano nel netto e nel già-scritto, altrimenti la commissione
    # e il P&L dell'orfana sarebbero calcolati su una coppia incompleta.
    orphans_by_parent: dict[int, list[dict]] = {}
    for c in closing_rows:
        pid = int(c.get("closes_trade_id") or 0)
        if pid and pid not in parent_ids:
            orphans_by_parent.setdefault(pid, []).append(c)
    for pid, orphans in orphans_by_parent.items():
        try:
            parent = db.get_trade(pid)
            if not parent or str(parent.get("status")) not in ("won", "lost", "void"):
                continue
            try:
                all_legs = [x for x in (db.closing_trades_for([pid]) or [])
                            if str(x.get("status")) != "error"]
            except Exception:  # noqa: BLE001 — senza le sorelle si usa il noto
                all_legs = list(orphans)
            for i, c in enumerate(orphans):
                cid = int(c.get("id") or 0)
                # M9: dopo ogni orfana regolata le SORELLE cambiano (la
                # precedente è ora 'won'/'lost' col suo pnl): si rilegge, o la
                # seconda orfana userebbe un netto e un già-scritto vecchi.
                if i > 0:
                    try:
                        all_legs = [x for x in (db.closing_trades_for([pid]) or [])
                                    if str(x.get("status")) != "error"]
                    except Exception:  # noqa: BLE001
                        pass
                # sorelle = ogni ALTRA chiusura della stessa apertura (quelle già
                # regolate entrano nel netto: le filtra settle_orphan_closing)
                siblings = [s for s in all_legs if int(s.get("id") or 0) != cid]
                comm = c.get("commission")
                comm = float(comm) if comm is not None else fallback_commission
                if X.settle_orphan_closing(db=db, closing=c, parent=parent,
                                           commission=comm, now=now,
                                           siblings=siblings):
                    settled += 1
        except Exception as ex:  # noqa: BLE001
            _log(db, "settle_error", {"trade_id": pid, "err": str(ex)[:160]})
    return settled


def _market_seen(market_id: str) -> None:
    """La lettura è andata a buon fine: azzera i fallimenti consecutivi."""
    _MARKET_MISSING.pop(market_id, None)
    _MARKET_MISSING.pop(f"n:{market_id}", None)
    _MARKET_MISSING.pop(f"log:{market_id}", None)


def _market_missing(db, tr: dict[str, Any], now_ts: float) -> None:
    """M-25: mercato SPARITO al settlement — né silenzio né flood.

    M11: si marca e si logga solo dopo ``MARKET_MISSING_MIN_FAILS`` letture
    consecutive fallite: una singola eccezione di rete non è un mercato
    sparito, e marcare la riga per un timeout è un falso allarme. Poi
    ``market_missing`` alla prima volta e ogni 5 minuti, con
    ``meta.market_missing_since`` sulla riga."""
    mid = str(tr.get("market_id") or "")
    fails = int(_MARKET_MISSING.get(f"n:{mid}") or 0) + 1
    _MARKET_MISSING[f"n:{mid}"] = fails
    if fails < MARKET_MISSING_MIN_FAILS:
        return
    first = _MARKET_MISSING.get(mid)
    if first is None:
        _MARKET_MISSING[mid] = now_ts
        meta = {**(tr.get("meta") or {}),
                "market_missing_since": datetime.fromtimestamp(now_ts, timezone.utc).isoformat()}
        try:
            db.update_trade(int(tr["id"]), meta=meta)
            tr["meta"] = meta
        except Exception:  # noqa: BLE001
            pass
    last = _MARKET_MISSING.get(f"log:{mid}")
    if last is not None and now_ts - float(last) < MARKET_MISSING_LOG_EVERY_S:
        return
    _MARKET_MISSING[f"log:{mid}"] = now_ts
    _log(db, "market_missing", {"trade_id": tr.get("id"), "event_id": tr.get("event_id"),
                                "market_id": mid, "fails": fails,
                                "since_s": round(now_ts - float(_MARKET_MISSING.get(mid) or now_ts), 1)})


def sync_hedges(db, parents: list[dict[str, Any]], closings: dict[int, list[dict]],
                now: datetime) -> int:
    """Riallinea le aperture 'open' con chiusure (fill flumine confermato dal
    poll, riconciliazione, chiusura andata in errore) → hedged_size/residuo,
    'hedged' a residuo nullo. Scrive solo se cambia qualcosa."""
    n = 0
    for tr in parents:
        if str(tr.get("status")) != "open":
            continue
        legs = closings.get(int(tr["id"]), [])
        if not legs and not X.has_closing_marker(tr):
            continue
        try:
            before = (tr.get("status"), dict(tr.get("meta") or {}))
            X.apply_hedge_state(db, tr, legs, now)
            if (tr.get("status"), tr.get("meta")) != before:
                n += 1
        except Exception as ex:  # noqa: BLE001
            _log(db, "error", {"reason": "sync_hedge_failed", "trade_id": tr.get("id"),
                               "err": str(ex)[:160]})
    return n


def _read_market(market, tr: dict[str, Any]):
    cs = _real_market.CorrectScoreMarket(
        market_id=str(tr.get("market_id")), event_id=str(tr.get("event_id")),
        event_name=tr.get("event_name") or "", market_start_time=None, runner_names={},
    )
    return market.read_market(cs)


# ---------------------------------------------------------------------------
# (c) richieste della UI — SEMPRE, anche a bot fermo
# ---------------------------------------------------------------------------
def process_requests(*, db, market, rows_by_event: dict[str, dict],
                     params: dict[str, Any], now: datetime,
                     risk_ctx: Optional[dict] = None) -> int:
    stale = getattr(db, "fail_stale_processing", None)
    if callable(stale):
        try:
            stale()
        except Exception as ex:  # noqa: BLE001
            logger.debug("[safe.bot] fail_stale_processing KO: %s", str(ex)[:120])
    try:
        reqs = db.pending_requests()
    except Exception as ex:  # noqa: BLE001
        _log(db, "error", {"reason": "pending_requests_failed", "err": str(ex)[:160]})
        return 0
    n = 0
    for r in reqs or []:
        try:
            db.set_request_status(r["id"], "processing")
        except Exception:  # noqa: BLE001
            continue
        kind = str(r.get("kind") or "")
        payload = r.get("payload") or {}
        try:
            if kind == "place":
                res = _request_place(db=db, market=market, rows_by_event=rows_by_event,
                                     payload=payload, params=params, now=now,
                                     risk_ctx=risk_ctx)
            elif kind == "cashout":
                res = _request_cashout(db=db, market=market, rows_by_event=rows_by_event,
                                       payload=payload, params=params, now=now)
            elif kind == "cancel":
                res = _request_cancel(db=db, payload=payload, now=now)
            else:
                res = {"error": f"kind_sconosciuto:{kind}"}
            db.set_request_status(r["id"], _request_state(res), _request_result(res))
        except Exception as ex:  # noqa: BLE001
            try:
                db.set_request_status(r["id"], "error",
                                      {"message": f"errore del servizio: {str(ex)[:160]}",
                                       "err": str(ex)[:200]})
            except Exception:  # noqa: BLE001
                pass
        n += 1
    return n


def _request_state(res: dict[str, Any]) -> str:
    """Stato con cui si CHIUDE la richiesta della UI (M-21): 'done' eseguita,
    'rejected' rifiutata dal servizio (non un guasto: la UI mostra il perché),
    'error' guasto."""
    if res.get("rejected"):
        return "rejected"
    return "error" if res.get("error") else "done"


def _request_result(res: dict[str, Any]) -> dict[str, Any]:
    """``result`` della richiesta con un ``message`` sempre presente e in
    ITALIANO: la UI deve poter mostrare l'esito senza tradurre codici."""
    out = dict(res)
    if not out.get("message"):
        if out.get("rejected"):
            out["message"] = f"rifiutato: {out.get('rejected')}"
        elif out.get("error"):
            detail = out.get("detail") or out.get("reason")
            out["message"] = f"non eseguito: {out['error']}" + (f" ({detail})" if detail else "")
        else:
            out["message"] = "eseguito"
    return out


# Richiesta MANUALE: strategie e tipi di opportunita' ammessi nel payload della
# UI. Tutto il resto viene normalizzato a "manual" / ignorato (mai fidarsi del
# client su una riga che muove soldi).
_MANUAL_STRATEGIES = ("manual", "model")
_MANUAL_OPP_KINDS = ("model", "anomaly", "combo", "tennis")


def _request_place(*, db, market, rows_by_event, payload: dict, params: dict,
                   now: datetime, risk_ctx: Optional[dict] = None) -> dict:
    """Piazzamento MANUALE dalla UI: reserve-first, stesse barriere dell'automatico
    più il controllo MORBIDO del rischio (solo i cap di esposizione)."""
    event_id = str(payload.get("event_id") or "")
    market_id = str(payload.get("market_id") or "")
    market_type = str(payload.get("market_type") or "").upper()
    sel = payload.get("selection_id")
    if not event_id or not market_id or not market_type or sel is None:
        return {"error": "payload_incompleto"}
    selection_id = int(sel)
    side = str(payload.get("side") or "").lower()
    if side not in ("back", "lay"):
        return {"error": f"side_non_valido:{side}"}
    # LIVE solo se ESPLICITO nel payload (toggle+conferma della UI): mai default.
    mode = str(payload.get("mode") or "paper").lower()
    if mode not in ("paper", "live"):
        return {"error": f"mode_non_valido:{mode}"}
    try:
        price = float(payload.get("price"))
        size = float(payload.get("size"))
    except (TypeError, ValueError):
        return {"error": "price/size non numerici"}
    if price <= 1.0 or size <= 0:
        return {"error": "price/size fuori range"}
    # idempotenza del MANUALE: la UI può reinviare la stessa richiesta (retry,
    # doppio click): con la stessa chiave non si piazza due volte.
    idem = str(payload.get("idempotency_key") or "").strip() or None
    if idem:
        dup = _trade_by_idempotency_key(db, idem)
        if dup is not None:
            return {"ok": True, "deduplicated": True, "trade_id": dup.get("id"),
                    "status": dup.get("status"), "idempotency_key": idem}

    # piazzamento MANUALE: il REST è consentito senza budget (una sola azione
    # dell'utente, non un ciclo) — L1: il gate è cablato qui, non nel default.
    prices = prices_for(market=market, rows_by_event=rows_by_event, event_id=event_id,
                        market_id=market_id, market_type=market_type,
                        selection_id=selection_id, allow_rest=True)
    best_size = (prices or {}).get(f"{side}_size")
    liability = X.liability_of(side, size, price)
    cap = float(params.get("max_liability_per_trade") or 0.0)
    if cap > 0 and liability > cap:
        return {"error": "max_liability_per_trade_superato", "liability": liability}
    risk_ctx = risk_ctx if risk_ctx is not None else build_risk_ctx(db, now, params)
    blocked = _risk_gate(db, now, params, risk_ctx,
                         {"event_id": event_id, "market_type": market_type,
                          "liability": liability,
                          "strategy": str(payload.get("strategy") or "manual").lower()},
                         soft=True, signal_key=f"manual:{market_id}:{selection_id}:{side}")
    if blocked:
        return {"error": "risk_block", "reason": blocked, "liability": liability}

    meta: dict[str, Any] = {"manual": True}
    if idem:
        meta["idempotency_key"] = idem
    # Contratto con la UI (certificazione 11/09): "Investi" dalle OPPORTUNITA'
    # manda strategy='model' + kind ('model'|'anomaly'|'combo'|'tennis') e, per
    # le combinazioni, le coordinate della gamba. Prima l'handler li buttava:
    # la riga nasceva strategy='manual' senza meta.kind, quindi la tabella
    # mostrava "MANUALE" al posto del badge del tipo (ANOMALIA / COMBINAZIONE /
    # MODELLO / TENNIS), niente P(perdita) d'ingresso e nessun legame fra le
    # gambe della stessa combinazione. Il rischio NON cambia: le richieste
    # manuali passano dal gate MORBIDO (risk.check soft=True), che non guarda
    # la strategia.
    strategy = str(payload.get("strategy") or "manual").lower()
    if strategy not in _MANUAL_STRATEGIES:
        strategy = "manual"
    kind = str(payload.get("kind") or "").lower()
    if strategy == "model" and kind in _MANUAL_OPP_KINDS:
        meta["kind"] = kind
        if kind == "anomaly" and payload.get("rule"):
            meta["rule"] = str(payload.get("rule"))
        if kind == "combo":
            for src, dst in (("combo", "combo"), ("combo_leg", "combo_leg"),
                             ("combo_legs", "combo_legs"),
                             ("combo_total_stake", "combo_total_stake")):
                if payload.get(src) is not None:
                    meta[dst] = payload.get(src)
    row = _reserve_row(
        event_id=event_id, event_name=payload.get("event_name"),
        sport=str(payload.get("sport") or "calcio"),
        strategy=strategy, market_id=market_id, market_type=market_type,
        selection_id=selection_id, selection_name=payload.get("selection_name"),
        side=side, mode=mode, price=price, size=size, liability=liability,
        commission=float(params.get("commission_pct", 5.0)) / 100.0,
        minute=payload.get("minute"), score=payload.get("score"),
        origin="manual", signal_key=None, meta=meta,
    )
    try:
        trade_id = db.insert_trade(row)
    except Exception as ex:  # noqa: BLE001
        return {"error": "riserva_fallita", "detail": str(ex)[:160]}
    if not trade_id:
        return {"error": "riserva_senza_id"}
    _risk_commit(risk_ctx, {**row, "id": trade_id})
    out = _execute(db=db, market=market, trade_id=trade_id, row=row, params=params,
                   now=now, best_size=best_size,
                   ladder=(prices or {}).get("lay_ladder") or ())
    if out.status == "error":
        return {"error": "non_eseguito", "detail": out.fill_note, "trade_id": trade_id}
    return {"ok": True, "trade_id": trade_id, "status": out.status,
            "price": out.price, "size": out.size,
            "pending_fill": out.status == "pending"}


def _trade_by_idempotency_key(db, key: str) -> Optional[dict[str, Any]]:
    """Trade NON in errore con ``meta.idempotency_key == key`` (accessor del db
    se c'è, altrimenti scansione delle righe)."""
    fn = getattr(db, "trade_by_idempotency_key", None)
    if callable(fn):
        return fn(key)
    for t in db.list_trades() or []:
        if str(t.get("status")) == "error":
            continue
        if str((t.get("meta") or {}).get("idempotency_key") or "") == key:
            return t
    return None


def _request_cashout(*, db, market, rows_by_event, payload: dict, params: dict,
                     now: datetime) -> dict:
    tid = payload.get("trade_id")
    if tid is None:
        return {"error": "trade_id_mancante"}
    try:
        trade = db.get_trade(int(tid))
    except Exception as ex:  # noqa: BLE001
        return {"error": "lettura_trade_fallita", "detail": str(ex)[:160]}
    if not trade:
        return {"error": "trade_inesistente"}
    if X.is_reconciling(trade):
        # C-03/coerenza: su una riga a esito ignoto non si chiude nulla
        return {"rejected": "in riconciliazione", "trade_id": int(tid),
                "message": "rifiutato: in riconciliazione (esito dell'ordine ancora ignoto)"}
    amount = payload.get("amount")
    fraction = payload.get("fraction", 1.0)
    # L-15: il MANUALE ha le stesse guardie dell'automatico — mercato SOSPESO
    # (rifiuto: a mercato sospeso non si abbina nulla) e quote NON FRESCHE.
    # H5: sul feed stantio NON si rifiuta subito — si legge il book REST (è un
    # clic dell'utente, non un loop: nessun budget) e si rifiuta solo se manca
    # anche quello. ``result.source`` dice da dove vengono i prezzi usati.
    row = rows_by_event.get(str(trade.get("event_id")))
    payload_feed = (row or {}).get("payload") if isinstance(row, dict) else None
    if isinstance(payload_feed, dict) and XE.market_open(trade, payload_feed) is False:
        return {"rejected": "mercato sospeso", "trade_id": int(tid),
                "message": "rifiutato: mercato sospeso, riprova appena riapre"}
    feed_ok = isinstance(row, dict) and XE.feed_is_fresh(row, now.timestamp(),
                                                         _scanner_ts(db))
    source = "feed"
    prices = None
    if feed_ok:
        prices = prices_for(market=market, rows_by_event=rows_by_event,
                            event_id=str(trade.get("event_id")),
                            market_id=str(trade.get("market_id")),
                            market_type=str(trade.get("market_type") or ""),
                            selection_id=int(trade.get("selection_id") or 0),
                            allow_rest=False)
    if not prices:
        source = "rest"
        prices = _book_prices(market=market, trade=trade)
    if not prices:
        if not feed_ok:
            return {"rejected": "quote non disponibili", "trade_id": int(tid),
                    "message": "rifiutato: quote non aggiornate (feed fermo) e book "
                               "Betfair non leggibile, riprova"}
        return {"error": "prezzi_non_disponibili"}
    # la gamba di chiusura eredita sport/mercato/selezione dell'apertura: senza,
    # la riga resterebbe senza market_type e la UI non saprebbe cosa mostrare.
    extra = {"sport": trade.get("sport") or "calcio",
             "strategy": trade.get("strategy") or "manual",
             "market_type": trade.get("market_type"),
             "selection_name": trade.get("selection_name"),
             "minute_at_entry": trade.get("minute_at_entry"),
             "score_at_entry": trade.get("score_at_entry")}
    # H-01: la gamba di chiusura MANUALE nasce con exit_kind='manual'
    # (la UI mostra "Cash out", non un'uscita automatica inventata).
    res = X.close_trade(db=db, market=market, trade=trade, prices=prices,
                        amount=float(amount) if amount is not None else None,
                        fraction=float(fraction) if fraction is not None else 1.0,
                        mode=str(trade.get("mode") or "paper"), now=now,
                        params=params, origin="manual", table_prefix="safe",
                        extra_row=extra, exit_kind="manual",
                        exit_reason="Cash out manuale dalla dashboard")
    res["source"] = source            # H5: 'feed' | 'rest'
    if res.get("ok"):
        # M-06: anche sull'APERTURA, così un parziale resta riconoscibile e la
        # UI sa che il residuo e' ancora chiudibile.
        _stamp_exit_on_parent(db, trade, "manual", "Cash out manuale dalla dashboard")
        res.setdefault("message", "cash out eseguito"
                       + (" (quote dal book Betfair)" if source == "rest" else ""))
    return res


def _book_prices(*, market, trade: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Prezzi della selezione dal BOOK REST (ripiego del manuale, H5): nessun
    budget — è un'azione dell'utente, non un ciclo. None se il mercato non è
    leggibile o non è aperto."""
    try:
        book = market.read_book(str(trade.get("market_id") or ""), {})
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] read_book manuale KO %s: %s",
                       trade.get("market_id"), str(ex)[:160])
        return None
    if not book or str(book.get("status") or "OPEN").upper() != "OPEN":
        return None
    sid = int(trade.get("selection_id") or 0)
    for r in book.get("runners") or []:
        if int(r.get("selection_id") or -1) == sid:
            return {"back": r.get("back_price"), "back_size": r.get("back_size"),
                    "lay": r.get("lay_price"), "lay_size": r.get("lay_size"),
                    "lay_ladder": r.get("lay_ladder") or ()}
    return None


def _stamp_exit_on_parent(db, trade: dict[str, Any], kind: str, reason: str) -> None:
    """``meta.exit_kind``/``exit_reason`` sull'apertura (contratto H-01)."""
    try:
        cur = db.get_trade(int(trade["id"])) or trade
        meta = {**(cur.get("meta") or {}), "exit_kind": kind, "exit_reason": reason}
        db.update_trade(int(trade["id"]), meta=meta)
        trade["meta"] = meta
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] exit_kind sull'apertura %s KO: %s",
                       trade.get("id"), str(ex)[:120])


def _request_cancel(*, db, payload: dict, now: Optional[datetime] = None) -> dict:
    """Annulla una RISERVA ancora 'pending' e senza ordine a mercato.

    Se l'ordine esiste (bet_id o marker flumine) NON si tocca nulla: lo risolve
    il poll — annullare qui lascerebbe un ordine reale non tracciato.

    C-03: una riga in RICONCILIAZIONE (``place_exception_reconciling``: esito
    del place IGNOTO, l'ordine reale può essere vivo) è VIETATA al cancel. Il
    servizio risponde 'in riconciliazione' e la risolve ``reconcile_pending``
    contro lo stato reale su Betfair. Cancellarla qui significava perdere di
    vista una posizione reale."""
    tid = payload.get("trade_id")
    if tid is None:
        return {"error": "trade_id_mancante"}
    trade = db.get_trade(int(tid))
    if not trade:
        return {"error": "trade_inesistente"}
    if str(trade.get("status")) != "pending":
        return {"rejected": f"non annullabile: stato {trade.get('status')}",
                "trade_id": int(tid),
                "message": f"rifiutato: la riga non e' una riserva (stato {trade.get('status')})"}
    meta = trade.get("meta") or {}
    if X.is_reconciling(trade):
        _log(db, "cancel_rejected", {"trade_id": int(tid), "event_id": trade.get("event_id"),
                                     "reason": "in_riconciliazione"})
        return {"rejected": "in riconciliazione", "trade_id": int(tid),
                "message": "rifiutato: in riconciliazione (esito dell'ordine ancora "
                           "ignoto, lo risolve il servizio contro Betfair)"}
    if trade.get("bet_id") or meta.get("flumine_client_ref") or meta.get("flumine_request_id"):
        return {"rejected": "ordine gia' a mercato", "trade_id": int(tid),
                "message": "rifiutato: l'ordine e' gia' a mercato (lo risolve il poll)"}
    db.delete_trade(int(tid))
    _log(db, "cancel", {"trade_id": int(tid), "event_id": trade.get("event_id")})
    return {"ok": True, "trade_id": int(tid), "message": "riserva annullata"}


# ---------------------------------------------------------------------------
# (c-bis) USCITE automatiche — SEMPRE (anche a bot fermo: gestione posizioni)
# ---------------------------------------------------------------------------
def _scanner_ts(db) -> Optional[float]:
    """Epoch dell'heartbeat dello scanner (None se non esposto/illeggibile)."""
    fn = getattr(db, "scanner_status", None)
    if not callable(fn):
        return None
    try:
        row = fn()
    except Exception as ex:  # noqa: BLE001
        logger.debug("[safe.bot] scanner_status KO: %s", str(ex)[:120])
        return None
    return XE.parse_ts((row or {}).get("updated_at")) if isinstance(row, dict) else None


def _residual_of(trade: dict[str, Any]) -> Optional[float]:
    """Residuo ancora aperto (stake d'apertura) dal sync dell'hedge; None = ignoto."""
    meta = trade.get("meta") or {}
    if meta.get("hedge_pending_ids"):
        return None   # gamba di chiusura in sospeso: residuo non conoscibile → guardia
    if meta.get("residual_size") is None:
        return None
    try:
        return float(meta["residual_size"])
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# H-05/H-17/C-04 — STATO dell'uscita: ``meta.exit`` = {state, attempts,
# last_error, next_retry_at, residual_attempts}. Nessuno stato è TERMINALE:
# una liability viva va coperta, e si ritenta con backoff crescente finché il
# mercato è aperto. 'failed' NON significa "smetto": significa "ho superato il
# budget veloce, continuo col backoff lungo e lo dico alla UI".
# ---------------------------------------------------------------------------
EXIT_KEY = "exit"
EXIT_STATES = ("retrying", "failed", "waiting_price", "done")


def exit_state(trade: dict[str, Any]) -> dict[str, Any]:
    st = (trade.get("meta") or {}).get(EXIT_KEY)
    return dict(st) if isinstance(st, dict) else {}


# uscite che NON aspettano il backoff di un tentativo precedente: perdono
# soldi ogni secondo (H4) — il backoff è pensato per i ritentativi, non per
# rimandare una NUOVA regola peggiorativa.
URGENT_EXIT_KINDS = ("loss", "red_card", "mandatory")


def _exit_due(trade: dict[str, Any], now_ts: float,
              decision: Optional[XE.ExitDecision] = None) -> bool:
    """True se l'invio dell'uscita è dovuto ORA.

    Il backoff (``meta.exit.next_retry_at``) frena i RITENTATIVI della stessa
    decisione; una decisione URGENTE nuova (perdita, rosso, obbligo tennis) lo
    scavalca: aspettare 5 minuti per chiudere una posizione che sta perdendo
    non è un ritentativo, è un danno."""
    if decision is not None and decision.kind in URGENT_EXIT_KINDS:
        st = exit_state(trade)
        if str(st.get("kind") or "") not in URGENT_EXIT_KINDS:
            return True   # regola NUOVA e urgente: si invia subito
    nxt = XE.parse_ts(exit_state(trade).get("next_retry_at"))
    return nxt is None or now_ts >= nxt


def _exit_candidates(open_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trade 'open' (non 'hedged', non gambe di chiusura), origine 'auto',
    strategia con regole di uscita e: uscita non ancora inviata, OPPURE inviata
    ma con RESIDUO (chiusura cappata dalla liquidità) e nessuna gamba 'pending'.

    Un'uscita FALLITA non esce più dall'elenco (H-05/H-17). Il BACKOFF NON
    filtra qui (review H4): il TRACCIAMENTO del feed (gol, rossi, game) deve
    girare a ogni ciclo per ogni posizione viva, altrimenti si perdono i
    passaggi (``last_goal_ts``, ``consecutive_lost``) e la decisione successiva
    nasce su dati incompleti. Il backoff si applica solo all'INVIO."""
    out: list[dict[str, Any]] = []
    for t in open_rows or []:
        if str(t.get("status")) != "open" or t.get("closes_trade_id"):
            continue
        if str(t.get("origin") or "") != "auto":
            continue
        if str(t.get("strategy") or "") not in XE.EXIT_STRATEGIES + XE.MODEL_STRATEGIES:
            continue
        req = (t.get("meta") or {}).get(XE.REQUEST_KEY)
        if isinstance(req, dict) and req.get("sent"):
            res = _residual_of(t)
            if res is None or res < XE.RESIDUAL_EPS:
                continue
        out.append(t)
    return out


def process_exits(*, db, market, rows_by_event: dict[str, dict], params: dict[str, Any],
                  now: datetime, opp_mod: Any = None,
                  opps_state: Optional[dict] = None,
                  open_rows: Optional[list[dict[str, Any]]] = None) -> int:
    """Traccia il feed per ogni posizione automatica e chiude quelle per cui
    vale una regola di uscita. Ritorna il numero di chiusure INVIATE.

    USCITE IN PROFITTO (a tempo / take-profit) con P&L bloccato < 0: decisione
    a MODELLO (``exits.decide_time_exit``) sulla probabilità residua di perdere
    la posizione (calcio: ``OpportunityModel.book``; tennis: ``p_match``;
    riserva: probabilità implicita del feed) — si TIENE quando il margine è
    ampio, log 'exit_hold' + ``meta.exit_hold`` per la UI, ricontrollo ogni
    ciclo. Le uscite in PERDITA restano incondizionate.

    Mai due uscite sulla stessa posizione (``meta.exit_requested``); una
    chiusura fallita si ritenta al ciclo successivo fino a ``exit_max_retries``,
    poi log 'error' e stop. Feed non fresco (riga > 20 s e scanner muto) o
    mercato sospeso → si aspetta, senza consumare tentativi.

    RESIDUO: se la chiusura è stata cappata dalla liquidità (fill parziale,
    ``meta.residual_size`` ≥ 0.01) la si ritenta sul residuo ogni
    ``residual_retry_s`` fino a ``residual_max_attempts`` (poi log 'error'),
    MAI mentre una gamba di chiusura è 'pending'."""
    xp = XE.exit_params(params)
    if not xp.get("enabled", True):
        return 0
    now_ts = now.timestamp()
    try:
        # M1: le posizioni vive arrivano dal contesto del ciclo (una sola
        # SELECT), non una lettura per fase e una per gamba di combo.
        rows = open_rows if open_rows is not None else (db.open_trades() or [])
        candidates = _exit_candidates(rows)
    except Exception as ex:  # noqa: BLE001
        _log(db, "error", {"reason": "exit_candidates_failed", "err": str(ex)[:160]})
        return 0
    if not candidates:
        return 0
    scanner_ts = _scanner_ts(db)
    sent = 0
    for tr in candidates:
        try:
            if _process_exit_one(db=db, market=market, trade=tr,
                                 row=rows_by_event.get(str(tr.get("event_id"))),
                                 params=params, xp=xp, now=now, now_ts=now_ts,
                                 scanner_ts=scanner_ts, opp_mod=opp_mod,
                                 opps_state=opps_state, open_rows=rows):
                sent += 1
        except Exception as ex:  # noqa: BLE001 — una posizione rotta non blocca le altre
            _log(db, "error", {"reason": "exit_failed", "trade_id": tr.get("id"),
                               "err": str(ex)[:160]})
    return sent


def _process_exit_one(*, db, market, trade: dict[str, Any], row: Optional[dict],
                      params: dict[str, Any], xp: dict[str, Any], now: datetime,
                      now_ts: float, scanner_ts: Optional[float],
                      opp_mod: Any = None, opps_state: Optional[dict] = None,
                      open_rows: Optional[list[dict[str, Any]]] = None) -> bool:
    if not isinstance(row, dict):
        # H-18: posizione VIVA senza riga nel feed = cecità. Mai silenzio
        # (tranne le pre-KO, che legittimamente non stanno nel feed in-play: M2).
        if is_blind_relevant(trade, {}):
            note_feed_blind(db, trade, now, now_ts)
        return False   # ci pensa il settlement
    clear_feed_blind(db, trade)
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    old_meta = dict(trade.get("meta") or {})
    meta = XE.track(trade, payload, now_ts)
    if meta.get(XE.TRACK_KEY) != old_meta.get(XE.TRACK_KEY):
        db.update_trade(int(trade["id"]), meta=meta)   # write-on-change
        trade["meta"] = meta
    req = meta.get(XE.REQUEST_KEY) if isinstance(meta.get(XE.REQUEST_KEY), dict) else None
    residual: Optional[float] = None
    is_model = str(trade.get("strategy") or "") in XE.MODEL_STRATEGIES
    if req and req.get("sent"):
        # RESIDUO di un'uscita già decisa e inviata (fill cappato): la regola è
        # già stata applicata, si chiude il residuo con cooldown e cap propri
        residual = _residual_of(trade)
        if residual is None or residual < XE.RESIDUAL_EPS:
            return False
        n = int(req.get("residual_attempts") or 0)
        cap = int(xp.get("residual_max_attempts") or 0)
        exhausted = n >= cap
        if exhausted and not req.get("residual_exhausted"):
            # H-17: il cap NON è terminale — si passa al backoff lungo e lo si
            # dice una volta (prima la liability residua restava scoperta).
            _persist_exit_request(db, trade, {**req, "residual_exhausted": True})
            _write_exit_state(db, trade, meta, state="failed",
                              last_error="residual_exhausted",
                              next_retry_at=_iso_in(now, XE.retry_backoff_s(n - cap + 1)))
            _log(db, "exit_failed", {"reason": "exit_residual_exhausted",
                                     "trade_id": trade.get("id"), "residual": residual,
                                     "attempts": n, "critical": True,
                                     "note": "si continua col backoff lungo"})
            return False
        # cooldown: veloce dentro il budget, backoff crescente oltre
        wait_s = float(xp.get("residual_retry_s") or 20.0) if not exhausted \
            else XE.retry_backoff_s(n - cap + 1)
        last = XE.parse_ts(req.get("last_attempt_ts"))
        if last is not None and now_ts - last < wait_s:
            return False   # cooldown fra un tentativo sul residuo e il successivo
        decision = XE.ExitDecision(str(req.get("kind") or "time"),
                                   str(req.get("reason") or "residuo"), 0.0)
    elif is_model:
        decision = None   # trade di MODELLO: si decide sui prezzi (dopo le guardie)
    else:
        decision = XE.decide(trade, payload, meta, now_ts, xp)
        if decision is None:
            return False
        if now_ts < float(decision.not_before_ts or 0.0):
            return False   # assestamento post-evento: si aspetta
    if not XE.feed_is_fresh(row, now_ts, scanner_ts):
        if decision is not None:
            _exit_wait(db, trade, meta, decision, "feed_non_fresco")
        return False
    if XE.market_open(trade, payload) is False:
        if decision is not None:
            _exit_wait(db, trade, meta, decision, "mercato_sospeso")
        return False
    prices = prices_from_row(row, market_type=str(trade.get("market_type") or ""),
                             selection_id=int(trade.get("selection_id") or 0),
                             market_id=trade.get("market_id"))
    if not prices or not (prices.get("back") or prices.get("lay")):
        if decision is not None:
            _exit_wait(db, trade, meta, decision, "prezzi_non_nel_feed")
        return False
    if decision is None:
        decision, info = _decide_model_exit(db=db, trade=trade, meta=meta, prices=prices,
                                            payload=payload, params=params, xp=xp, now=now,
                                            opp_mod=opp_mod, opps_state=opps_state)
        if decision is None:
            # HOLD di un trade di MODELLO: meta.exit_hold per la UI ("In attesa" con
            # P(perdita) corrente), write-on-change come _model_gate (review 11/09 M3:
            # prima la scheda parametri lo prometteva ma non veniva mai scritto)
            _write_model_hold(db, trade, meta, info, now)
            return False
        if isinstance(meta.get(HOLD_KEY), dict):
            _write_meta_key(db, trade, meta, HOLD_KEY, None)   # si esce: niente più attesa
        if now_ts < float(decision.not_before_ts or 0.0):
            _exit_wait(db, trade, meta, decision, "assestamento_post_evento")
            return False
    else:
        hold, info = _model_gate(db=db, trade=trade, meta=meta, decision=decision,
                                 prices=prices, payload=payload, params=params, xp=xp,
                                 now=now, opp_mod=opp_mod, opps_state=opps_state)
        if hold:
            return False   # uscita in profitto che bloccherebbe una perdita: si tiene
    # H4: il BACKOFF si applica QUI, all'invio — dopo il tracciamento e la
    # decisione. Una regola urgente NUOVA (perdita/rosso/obbligo) non aspetta
    # il backoff di un tentativo precedente.
    if not _exit_due(trade, now_ts, decision):
        return False
    # H-20: una gamba di COMBO non si chiude da sola — o la combo intera o
    # niente. Senza i prezzi di TUTTE le gambe vive si aspetta.
    siblings = combo_siblings(db, trade, open_rows=open_rows)
    if siblings:
        sib_prices = _combo_leg_prices(siblings, rows_by_event=None, row=row)
        if sib_prices is None:
            _exit_wait(db, trade, meta, decision, "combo_prezzi_incompleti")
            return False
    sent = _send_exit(db=db, market=market, trade=trade, meta=meta, decision=decision,
                      prices=prices, payload=payload, params=params, xp=xp, now=now,
                      residual=residual, model_info=info)
    if sent and siblings:
        _close_combo_siblings(db=db, market=market, legs=siblings,
                              prices_by_id=sib_prices or {}, params=params, now=now,
                              reason="combo: chiusura solidale della combinazione")
    return sent


def _combo_leg_prices(legs: list[dict[str, Any]], *, rows_by_event: Optional[dict],
                      row: Optional[dict]) -> Optional[dict[int, dict[str, Any]]]:
    """{id gamba: prezzi dal feed} per TUTTE le gambe; None se ne manca una
    (le gambe di una combo stanno sullo stesso evento: stessa riga del feed)."""
    out: dict[int, dict[str, Any]] = {}
    for leg in legs:
        src = row
        if src is None and rows_by_event is not None:
            src = rows_by_event.get(str(leg.get("event_id")))
        p = prices_from_row(src, market_type=str(leg.get("market_type") or ""),
                            selection_id=int(leg.get("selection_id") or 0),
                            market_id=leg.get("market_id"))
        if not p or not (p.get("back") or p.get("lay")):
            return None
        out[int(leg.get("id") or 0)] = p
    return out


def _close_combo_siblings(*, db, market, legs: list[dict[str, Any]],
                          prices_by_id: dict[int, dict[str, Any]],
                          params: dict[str, Any], now: datetime, reason: str) -> int:
    """Chiude le altre gambe della combo con uscita 'forced' (H-20)."""
    n = 0
    for leg in legs:
        prices = prices_by_id.get(int(leg.get("id") or 0))
        if not prices:
            continue
        extra = {"sport": leg.get("sport") or "calcio",
                 "strategy": leg.get("strategy") or "model",
                 "market_type": leg.get("market_type"),
                 "selection_name": leg.get("selection_name"),
                 "minute_at_entry": leg.get("minute_at_entry"),
                 "score_at_entry": leg.get("score_at_entry")}
        try:
            res = X.close_trade(db=db, market=market, trade=leg, prices=prices,
                                amount=None, fraction=1.0,
                                mode=str(leg.get("mode") or "paper"), now=now,
                                params=params, origin="auto", table_prefix="safe",
                                extra_row=extra, exit_kind="forced", exit_reason=reason)
        except Exception as ex:  # noqa: BLE001
            res = {"error": "exception", "detail": str(ex)[:160]}
        if res.get("error"):
            _log(db, "exit_failed", {"reason": "combo_gamba_non_chiusa",
                                     "trade_id": leg.get("id"),
                                     "combo_id": (leg.get("meta") or {}).get("combo_id"),
                                     "err": res.get("error"), "critical": True})
            continue
        _stamp_exit_on_parent(db, leg, "forced", reason)
        _log(db, "exit", {"trade_id": leg.get("id"), "event_id": leg.get("event_id"),
                          "exit_kind": "forced", "exit_reason": reason,
                          "kind": "mandatory", "reason": "combo_solidale",
                          "closing_trade_id": res.get("closing_trade_id"),
                          "side": res.get("side"), "price": res.get("price"),
                          "size": res.get("size"), "locked_pnl": res.get("locked_pnl"),
                          "strategy": leg.get("strategy"), "mode": leg.get("mode")})
        n += 1
    return n


# ---------------------------------------------------------------------------
# decisione a MODELLO per le uscite in profitto (a tempo / take-profit)
# ---------------------------------------------------------------------------
OPPS_ROW_TTL_S = 2 * 3600.0       # riga opportunità non riscritta da 2 h = partita finita
OPPS_PURGE_EVERY_S = 300.0         # pulizia al massimo ogni 5 minuti
HOLD_KEY = "exit_hold"            # meta.exit_hold = {reason, p_lose, source, locked, ev_hold, ts}
_HOLD_REWRITE_S = 30.0            # riscrittura di meta.exit_hold a motivo invariato
_EXIT_MODEL: dict[str, Any] = {"model": None, "mod": None}


def _exit_model(opp_mod: Any, params: dict[str, Any]) -> Any:
    """OpportunityModel condiviso (cache del book per stato+λ): uno per processo."""
    if opp_mod is None:
        opp_mod = _import_opportunity_module()
    if opp_mod is None:
        return None
    if _EXIT_MODEL["model"] is None or _EXIT_MODEL["mod"] is not opp_mod:
        try:
            _EXIT_MODEL["model"] = opp_mod.OpportunityModel(params)
            _EXIT_MODEL["mod"] = opp_mod
        except Exception as ex:  # noqa: BLE001
            logger.warning("[safe.bot] OpportunityModel KO: %s", str(ex)[:120])
            return None
    return _EXIT_MODEL["model"]


def _commission_of(trade: dict[str, Any], params: dict[str, Any]) -> float:
    """Aliquota di commissione della POSIZIONE: quella fissata al piazzamento
    (colonna ``commission``), altrimenti il parametro corrente."""
    c = trade.get("commission")
    if c is not None:
        return min(1.0, max(0.0, _f(c, 0.0)))
    return min(1.0, max(0.0, _f(params.get("commission_pct"), 5.0) / 100.0))


def _market_implied_p_sel(trade: dict[str, Any], prices: dict[str, Any]) -> Optional[float]:
    """P(selezione vince) implicita dal feed, dal lato CONSERVATIVO per la
    posizione: lay → 1/back (back < lay → P più alta); back → 1/lay."""
    side = str(trade.get("side") or "").lower()
    px = _f(prices.get("back" if side == "lay" else "lay"), 0.0)
    return round(1.0 / px, 4) if px > 1.0 else None


def _p_selection_wins(*, db, trade: dict[str, Any], payload: dict[str, Any],
                      prices: dict[str, Any], meta: dict[str, Any],
                      params: dict[str, Any], now: datetime, opp_mod: Any,
                      opps_state: Optional[dict]) -> tuple[Optional[float], str]:
    """(P(la selezione della posizione VINCE al settlement), fonte).

    calcio → ``OpportunityModel.book`` sullo stato live (λ pre-match dalla
    catena del bot); chiavi 'home|draw|away' (Match Odds) e
    'cs_any_other_home|away' (Correct Score "Altro risultato").
    tennis → ``tennis_winprob.p_match`` dal punteggio (hold stimati, servizio
    ignoto → media dei due casi). Riserva: probabilità implicita del feed
    ('market'). None se nemmeno quella è calcolabile."""
    tr = meta.get(XE.TRACK_KEY) or {}
    side = tr.get("side") or XE.position_side(trade, payload)
    try:
        if XE.is_tennis(trade):
            p = _p_tennis(payload, side)
            if p is not None:
                return p, "model"
        else:
            p = _p_calcio(db=db, trade=trade, payload=payload, side=side, params=params,
                          now=now, opp_mod=opp_mod, opps_state=opps_state)
            if p is not None:
                return p, "model"
    except Exception as ex:  # noqa: BLE001 — modello KO: riserva di mercato
        logger.warning("[safe.bot] modello P(vince) KO (trade %s): %s",
                       trade.get("id"), str(ex)[:120])
    p = _market_implied_p_sel(trade, prices)
    return (p, "market") if p is not None else (None, "none")


def _p_calcio(*, db, trade: dict[str, Any], payload: dict[str, Any], side: Optional[str],
              params: dict[str, Any], now: datetime, opp_mod: Any,
              opps_state: Optional[dict]) -> Optional[float]:
    model = _exit_model(opp_mod, params)
    if model is None or payload.get("score_home") is None or payload.get("score_away") is None:
        return None
    key = _prob_key_for_trade(trade, payload, side)
    if not key:
        return None
    state = opps_state if opps_state is not None else _OPPS_STATE
    lam = resolve_event_lambdas(db=db, event_id=str(trade.get("event_id")), payload=payload,
                                opp_mod=opp_mod or _import_opportunity_module(), now=now,
                                state=state)
    book = model.book(payload, lambdas=lam["lambdas"], league_id=lam.get("league_id"),
                      ht_ratio=lam.get("ht_ratio"))
    p = book.get(key)
    return round(min(1.0, max(0.0, float(p))), 4) if p is not None else None


_HOME_KEY_RE = re.compile(r"casa|home", re.IGNORECASE)
_AWAY_KEY_RE = re.compile(r"ospite|away", re.IGNORECASE)
_DRAW_KEY_RE = re.compile(r"draw|pareggio", re.IGNORECASE)
_ANY_OTHER_KEY_RE = re.compile(r"any\s*other|altro", re.IGNORECASE)
_ANY_UNQ_KEY_RE = re.compile(r"any\s*(other|unquoted)", re.IGNORECASE)


def _prob_key_for_trade(trade: dict[str, Any], payload: dict[str, Any],
                        side: Optional[str]) -> Optional[str]:
    """Chiave del ``book`` (P che la SELEZIONE della posizione vinca) dal
    mercato/selezione del trade: Match Odds → home|draw|away; CS → cs_H_A /
    cs_any_other_*; O/U → over_X_Y|under_X_Y; BTTS → btts_yes|no; HT 1X2 →
    ht_*; HT score → hts_*. None se non mappabile (→ riserva di mercato)."""
    mt = str(trade.get("market_type") or "").upper()
    strategy = str(trade.get("strategy") or "")
    name = str(trade.get("selection_name") or "")
    if mt == "MATCH_ODDS":
        # la selezione della posizione: base = sfavorita (lay), punta = favorita (back)
        sel_side = XE._side_by_selection(payload.get("odds"), trade.get("selection_id"),
                                         ("home", "draw", "away"))
        if sel_side is None and side in ("home", "away"):
            sel_side = ("away" if side == "home" else "home") if strategy == "base" else side
        return sel_side
    if mt in ("CORRECT_SCORE", "HALF_TIME_SCORE"):
        prefix = "cs_" if mt == "CORRECT_SCORE" else "hts_"
        if strategy == "esatto" and side in ("home", "away"):
            return f"cs_any_other_{side}"
        sc = XE.parse_calcio_score(name)
        if sc is not None and not _ANY_OTHER_KEY_RE.search(name):
            return f"{prefix}{sc[0]}_{sc[1]}"
        if prefix == "hts_" and _ANY_UNQ_KEY_RE.search(name):
            return "hts_any_unquoted"
        if _ANY_OTHER_KEY_RE.search(name):
            if _HOME_KEY_RE.search(name):
                return "cs_any_other_home"
            if _AWAY_KEY_RE.search(name):
                return "cs_any_other_away"
            if _DRAW_KEY_RE.search(name):
                return "cs_any_other_draw"
        return None
    if mt.startswith("OVER_UNDER"):
        line = XE.ou_line(trade)
        if line is None:
            return None
        k = str(float(line)).replace(".", "_")
        if XE._UNDER_RE.search(name):
            return f"under_{k}"
        if XE._OVER_RE.search(name):
            return f"over_{k}"
        return None
    if mt == "BOTH_TEAMS_TO_SCORE":
        if XE._YES_RE.match(name):
            return "btts_yes"
        if XE._NO_RE.match(name):
            return "btts_no"
        return None
    if mt == "HALF_TIME":
        if _DRAW_KEY_RE.search(name):
            return "ht_draw"
        home, away = _event_teams(payload)
        low = name.strip().lower()
        if home and low == str(home).strip().lower():
            return "ht_home"
        if away and low == str(away).strip().lower():
            return "ht_away"
        if _HOME_KEY_RE.search(name):
            return "ht_home"
        if _AWAY_KEY_RE.search(name):
            return "ht_away"
        return None
    return None


def _decide_model_exit(*, db, trade: dict[str, Any], meta: dict[str, Any],
                       prices: dict[str, Any], payload: dict[str, Any],
                       params: dict[str, Any], xp: dict[str, Any], now: datetime,
                       opp_mod: Any, opps_state: Optional[dict]
                       ) -> "tuple[Optional[XE.ExitDecision], dict[str, Any]]":
    """Decisione per un trade di MODELLO (strategia 'model': modello, anomalia,
    combo, tennis): P(perdita) ricalcolata (modello → riserva di mercato), P&L
    bloccato e profitto massimo al netto delle gambe già fillate, poi la regola
    pura ``exits.decide_model``. Ritorna (decisione | None, numeri)."""
    locked: Optional[float] = None
    legs = X.known_closings(db, trade) or []
    try:
        plan = X.close_plan(trade, best_back=_f(prices.get("back"), 0.0) or None,
                            best_lay=_f(prices.get("lay"), 0.0) or None,
                            fraction=1.0, closings=legs)
        if plan.actionable:
            locked = X.locked_pnl(trade, plan)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] close_plan KO (trade %s): %s", trade.get("id"), str(ex)[:120])
    exp_win, exp_lose = X.net_exposures(trade, legs)
    is_lay = str(trade.get("side") or "").lower() == "lay"
    # M-27: la decisione a modello confronta importi NETTI di commissione —
    # un profitto lordo di 1,00 in mano vale 0,95 e cambia il verdetto.
    comm = _commission_of(trade, params)
    locked = XE.net_of_commission(locked, comm)
    max_profit = float(XE.net_of_commission(exp_lose if is_lay else exp_win, comm) or 0.0)
    loss_if_lose = max(0.0, -float(exp_win if is_lay else exp_lose))
    p_sel, source = _p_selection_wins(db=db, trade=trade, payload=payload, prices=prices,
                                      meta=meta, params=params, now=now, opp_mod=opp_mod,
                                      opps_state=opps_state)
    p_lose = None if p_sel is None else round(p_sel if is_lay else 1.0 - p_sel, 4)
    p_entry = meta.get("p_lose_entry")
    p_entry = float(p_entry) if isinstance(p_entry, (int, float)) else None
    sit = XE.model_situation(trade, meta, payload, xp)
    decision = XE.decide_model(p_lose=p_lose, p_lose_entry=p_entry, locked=locked,
                               max_profit=max_profit, situation=sit, params=xp)
    info = {"p_lose": p_lose, "source": source, "locked": locked,
            "ev_hold": None if p_lose is None else XE.ev_hold(p_lose, max_profit, loss_if_lose),
            "hold_profit": round(max_profit, 2), "loss_if_lose": round(loss_if_lose, 2),
            "p_lose_entry": p_entry, "adverse_event": sit.get("adverse_event"),
            "decided_against": sit.get("decided_against"),
            "decision": "exit" if decision else "hold",
            "why": (f"{decision.kind}:{decision.reason}" if decision
                    else "modello: nessuna regola attiva, tengo")}
    return decision, info


def _best_of(payload: dict[str, Any], sets: "tuple[int, int]") -> int:
    """Formato del match (L-12): la stessa euristica del modello tennis
    (``tennis_opportunity.detect_best_of``: forzatura, set già giocati, keyword
    Slam maschile) invece del solo "3 set giocati = bo5" — un bo5 all'1-0
    veniva valutato come bo3 e la P(vittoria) era sbagliata."""
    mod = _import_optional("tennis_opportunity")
    fn = getattr(mod, "detect_best_of", None) if mod else None
    if callable(fn):
        try:
            params = dict(getattr(mod, "DEFAULT_TENNIS_OPP_PARAMS", None) or {})
            return int(fn(payload.get("competition"), sets, params))
        except Exception as ex:  # noqa: BLE001
            logger.debug("[safe.bot] detect_best_of KO: %s", str(ex)[:120])
    return 5 if (sets[0] + sets[1]) >= 3 else 3


def _p_tennis(payload: dict[str, Any], side: Optional[str]) -> Optional[float]:
    if side not in ("p1", "p2"):
        return None
    sets, games = payload.get("sets"), payload.get("games")
    if not isinstance(sets, dict) or not isinstance(games, dict):
        return None
    try:
        s1, s2 = int(sets["p1"]), int(sets["p2"])
        g1, g2 = int(games["p1"]), int(games["p2"])
    except (KeyError, TypeError, ValueError):
        return None
    from Betfair.stream.tennis_scalper.tennis_winprob import estimate_holds, p_match

    # A = il giocatore puntato; break non noti dal feed → hold dal prior
    if side == "p1":
        sa, sb, ga, gb = s1, s2, g1, g2
    else:
        sa, sb, ga, gb = s2, s1, g2, g1
    ha, hb = estimate_holds(0, 0, 0, 0)
    best_of = _best_of(payload, (s1, s2))
    # servizio ignoto: media fra "serve A" e "serve B"
    p = 0.5 * (p_match(sa, sb, ga, gb, True, ha, hb, best_of)
               + p_match(sa, sb, ga, gb, False, ha, hb, best_of))
    return round(min(1.0, max(0.0, float(p))), 4)


def _model_gate(*, db, trade: dict[str, Any], meta: dict[str, Any],
                decision: XE.ExitDecision, prices: dict[str, Any], payload: dict[str, Any],
                params: dict[str, Any], xp: dict[str, Any], now: datetime,
                opp_mod: Any, opps_state: Optional[dict]) -> tuple[bool, dict[str, Any]]:
    """(tenere?, numeri usati). Solo per le uscite in PROFITTO (time/profit);
    le uscite in perdita passano senza gate. Il P&L bloccato e le esposizioni
    sono al netto delle gambe già fillate (vale anche per il residuo).
    HOLD → log 'exit_hold' una volta per motivo + ``meta.exit_hold`` per la UI
    (riscritto al cambio motivo o ogni 30 s); EXIT → ``meta.exit_hold`` rimosso.
    Un HOLD non blocca mai una successiva uscita in perdita (non gated)."""
    if decision.kind not in XE.PROFIT_KINDS:
        return False, {}
    locked: Optional[float] = None
    legs = X.known_closings(db, trade) or []
    try:
        plan = X.close_plan(trade, best_back=_f(prices.get("back"), 0.0) or None,
                            best_lay=_f(prices.get("lay"), 0.0) or None,
                            fraction=1.0, closings=legs)
        if plan.actionable:
            locked = X.locked_pnl(trade, plan)
    except Exception as ex:  # noqa: BLE001 — senza P&L calcolabile si tiene
        logger.warning("[safe.bot] close_plan KO (trade %s): %s", trade.get("id"), str(ex)[:120])
    exp_win, exp_lose = X.net_exposures(trade, legs)   # P&L se la selezione vince / perde
    is_lay = str(trade.get("side") or "").lower() == "lay"
    comm = _commission_of(trade, params)               # M-27: tutto al NETTO
    locked = XE.net_of_commission(locked, comm)
    hold_profit = float(XE.net_of_commission(exp_lose if is_lay else exp_win, comm) or 0.0)
    loss_if_lose = max(0.0, -float(exp_win if is_lay else exp_lose))
    p_sel, source = _p_selection_wins(db=db, trade=trade, payload=payload, prices=prices,
                                      meta=meta, params=params, now=now, opp_mod=opp_mod,
                                      opps_state=opps_state)
    p_lose = None if p_sel is None else round(p_sel if is_lay else 1.0 - p_sel, 4)
    action, why = XE.decide_time_exit(p_lose, locked, hold_profit, trade.get("size"), xp,
                                      loss_if_lose=loss_if_lose)
    info = {"p_lose": p_lose, "source": source, "locked": locked,
            "ev_hold": None if p_lose is None else XE.ev_hold(p_lose, hold_profit, loss_if_lose),
            "hold_profit": round(hold_profit, 2), "loss_if_lose": round(loss_if_lose, 2),
            "decision": action, "why": why}
    prev = meta.get(HOLD_KEY) if isinstance(meta.get(HOLD_KEY), dict) else None
    if action == "exit":
        if prev is not None:
            _write_meta_key(db, trade, meta, HOLD_KEY, None)
        return False, info
    code = XE.hold_code(why)
    hold = {"reason": why, "code": code, "kind": decision.kind,
            "exit_reason": decision.reason,
            "p_lose": p_lose, "source": source, "locked": locked, "ev_hold": info["ev_hold"],
            "ts": now.isoformat()}
    # M-28: il confronto è sul CODICE (motivo senza numeri): il testo contiene
    # P(perdita) e EV, che cambiano a ogni tick → prima si riscriveva sempre.
    changed = prev is None or XE.hold_code(prev.get("code") or prev.get("reason")) != code
    last_ts = XE.parse_ts((prev or {}).get("ts"))
    if changed or last_ts is None or now.timestamp() - last_ts >= _HOLD_REWRITE_S:
        _write_meta_key(db, trade, meta, HOLD_KEY, hold)
    if changed:
        _log(db, "exit_hold", {"trade_id": trade.get("id"), "event_id": trade.get("event_id"),
                               "kind": decision.kind, "reason": decision.reason,
                               "msg": why, **{k: info[k] for k in
                                              ("p_lose", "source", "locked", "ev_hold",
                                               "hold_profit", "loss_if_lose")},
                               "back": prices.get("back"), "lay": prices.get("lay")})
    return True, info


def _write_model_hold(db, trade: dict[str, Any], meta: dict[str, Any],
                      info: dict[str, Any], now: datetime) -> None:
    """meta.exit_hold di un trade di MODELLO tenuto aperto (stesso contratto del
    gate delle 4 strategie: reason, kind, p_lose, source, locked, ev_hold, ts).
    Riscritto solo al cambio di motivo o ogni _HOLD_REWRITE_S; log 'exit_hold'
    una volta per motivo."""
    why = str(info.get("why") or "modello: tengo")
    prev = meta.get(HOLD_KEY) if isinstance(meta.get(HOLD_KEY), dict) else None
    code = XE.hold_code(why)
    hold = {"reason": why, "code": code, "kind": "model", "p_lose": info.get("p_lose"),
            "source": info.get("source"), "locked": info.get("locked"),
            "ev_hold": info.get("ev_hold"), "ts": now.isoformat()}
    changed = prev is None or XE.hold_code(prev.get("code") or prev.get("reason")) != code
    last_ts = XE.parse_ts((prev or {}).get("ts"))
    if changed or last_ts is None or now.timestamp() - last_ts >= _HOLD_REWRITE_S:
        _write_meta_key(db, trade, meta, HOLD_KEY, hold)
    if changed:
        _log(db, "exit_hold", {"trade_id": trade.get("id"), "event_id": trade.get("event_id"),
                               "kind": "model", "reason": why, "msg": why,
                               **{k: info.get(k) for k in ("p_lose", "source", "locked", "ev_hold",
                                                           "hold_profit", "loss_if_lose")}})


def _write_meta_key(db, trade: dict[str, Any], meta: dict[str, Any], key: str,
                    value: Any) -> None:
    """Scrive (o rimuove, value=None) una chiave del meta della riga."""
    new_meta = {k: v for k, v in meta.items() if k != key}
    if value is not None:
        new_meta[key] = value
    try:
        db.update_trade(int(trade["id"]), meta=new_meta)
        trade["meta"] = new_meta
        meta.clear()
        meta.update(new_meta)
    except Exception:  # noqa: BLE001
        pass


def _iso_in(now: datetime, seconds: float) -> str:
    return (now + timedelta(seconds=max(0.0, float(seconds)))).isoformat()


def _write_exit_state(db, trade: dict[str, Any], meta: dict[str, Any],
                      **upd: Any) -> dict[str, Any]:
    """Aggiorna (merge) ``meta.exit`` — lo stato dell'uscita per la UI.

    M1: NESSUNA rilettura in più. ``_persist_exit_request`` e ``close_trade``
    aggiornano ``trade['meta']`` in memoria dopo aver scritto, quindi lo
    snapshot locale è già quello corrente; si rilegge SOLO se il meta locale è
    vuoto (caso limite di una riga appena passata di mano)."""
    live_meta = dict(trade.get("meta") or {})
    if not live_meta:
        fn = getattr(db, "get_trade", None)
        if callable(fn):
            try:
                live_meta = dict((fn(int(trade["id"])) or {}).get("meta") or {})
            except Exception:  # noqa: BLE001
                live_meta = {}
    cur = live_meta.get(EXIT_KEY)
    st = dict(cur) if isinstance(cur, dict) else {}
    st.update(upd)
    if st == cur:
        return st
    new_meta = {**live_meta, EXIT_KEY: st}
    try:
        db.update_trade(int(trade["id"]), meta=new_meta)
        trade["meta"] = new_meta
        meta.clear()
        meta.update(new_meta)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] stato uscita KO (trade %s): %s",
                       trade.get("id"), str(ex)[:120])
    return st


# H-18 — CECITÀ del feed: posizione viva e nessuna riga dell'evento.
FEED_BLIND_LOG_EVERY_S = 60.0
_FEED_BLIND_LOG: dict[int, float] = {}


def is_blind_relevant(trade: dict[str, Any], rows_by_event: dict[str, dict]) -> bool:
    """La cecità è un ALLARME solo per una posizione che dovrebbe essere nel
    feed ADESSO (M2).

    NON è un allarme per una posizione PRE-KO: lo scanner segue gli in-play,
    quindi una scommessa piazzata prima del calcio d'inizio legittimamente non
    ha riga (``meta.pre_ko``/``minute_at_entry`` assente e nessun tracciamento
    in-play mai visto)."""
    meta = trade.get("meta") or {}
    if meta.get("pre_ko") or meta.get("prematch"):
        return False
    tr = meta.get(XE.TRACK_KEY)
    if isinstance(tr, dict) and (tr.get("minute") is not None
                                 or tr.get("last_home") is not None
                                 or tr.get("last_games") is not None):
        return True   # la partita l'abbiamo VISTA in gioco: ora sparita = allarme
    if trade.get("minute_at_entry") is not None:
        return True   # entrata in-play
    if str(trade.get("sport") or "") == "tennis" and trade.get("score_at_entry"):
        return True
    # mai vista nel feed e nessun segno di in-play: pre-KO, si tace
    return False


def note_feed_blind(db, trade: dict[str, Any], now: datetime, now_ts: float) -> None:
    """``meta.blind_since`` + attività ``feed_blind`` (una volta, poi ogni 60 s).

    M1: ``blind_since`` si scrive UNA volta sola (non una update per ciclo)."""
    tid = int(trade.get("id") or 0)
    meta = dict(trade.get("meta") or {})
    if not meta.get("blind_since"):
        meta["blind_since"] = now.isoformat()
        try:
            db.update_trade(tid, meta=meta)
            trade["meta"] = meta
        except Exception:  # noqa: BLE001
            pass
    last = _FEED_BLIND_LOG.get(tid)
    if last is not None and now_ts - last < FEED_BLIND_LOG_EVERY_S:
        return
    _FEED_BLIND_LOG[tid] = now_ts
    since = XE.parse_ts(meta.get("blind_since"))
    _log(db, "feed_blind", {"trade_id": tid, "event_id": trade.get("event_id"),
                            "event_name": trade.get("event_name"),
                            "market_id": trade.get("market_id"),
                            "blind_since": meta.get("blind_since"),
                            "blind_for_s": round(now_ts - since, 1) if since else None,
                            "critical": True})


def clear_feed_blind(db, trade: dict[str, Any]) -> None:
    """La riga del feed è tornata: via ``meta.blind_since``."""
    meta = dict(trade.get("meta") or {})
    if not meta.get("blind_since"):
        return
    _FEED_BLIND_LOG.pop(int(trade.get("id") or 0), None)
    meta.pop("blind_since", None)
    try:
        db.update_trade(int(trade["id"]), meta=meta)
        trade["meta"] = meta
        _log(db, "feed_back", {"trade_id": trade.get("id"),
                               "event_id": trade.get("event_id")})
    except Exception:  # noqa: BLE001
        pass


def check_feed_blind(db, open_rows: list[dict[str, Any]],
                     rows_by_event: dict[str, dict], now: datetime) -> int:
    """H-18 su TUTTE le posizioni vive (anche manuali e di modello): quante
    sono cieche in questo ciclo. Le posizioni PRE-KO non contano (M2)."""
    now_ts = now.timestamp()
    blind = 0
    for t in open_rows or []:
        if t.get("closes_trade_id") or str(t.get("status")) not in ("open", "hedged"):
            continue
        row = rows_by_event.get(str(t.get("event_id")))
        if isinstance(row, dict):
            clear_feed_blind(db, t)
            continue
        if not is_blind_relevant(t, rows_by_event):
            continue
        note_feed_blind(db, t, now, now_ts)
        blind += 1
    return blind


# ---------------------------------------------------------------------------
# H-20 — COMBO: tutto o niente ANCHE dopo il fill.
# ---------------------------------------------------------------------------
def combo_siblings(db, trade: dict[str, Any],
                   open_rows: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """Altre gambe VIVE della stessa combo (``meta.combo_id``).

    M1: usa le posizioni GIÀ lette per il ciclo; legge dal DB solo se non le
    riceve (prima era una SELECT per ogni candidato di combo)."""
    cid = (trade.get("meta") or {}).get("combo_id")
    if not cid:
        return []
    if open_rows is None:
        try:
            open_rows = db.open_trades() or []
        except Exception:  # noqa: BLE001
            return []
    rows = open_rows
    out = []
    for t in rows:
        if t.get("closes_trade_id") or int(t.get("id") or 0) == int(trade.get("id") or 0):
            continue
        if str((t.get("meta") or {}).get("combo_id") or "") != str(cid):
            continue
        if str(t.get("status")) != "open":
            continue
        out.append(t)
    return out


def _exit_wait(db, trade: dict[str, Any], meta: dict[str, Any], decision: XE.ExitDecision,
               why: str) -> None:
    """Log 'exit_wait' solo al CAMBIO di motivo (niente rumore a ogni ciclo)."""
    tr = meta.get(XE.TRACK_KEY) or {}
    if tr.get("wait_reason") == why:
        return
    tr = {**tr, "wait_reason": why}
    meta = {**meta, XE.TRACK_KEY: tr}
    try:
        db.update_trade(int(trade["id"]), meta=meta)
        trade["meta"] = meta
    except Exception:  # noqa: BLE001
        pass
    _log(db, "exit_wait", {"trade_id": trade.get("id"), "kind": decision.kind,
                           "reason": decision.reason, "wait": why})


def _send_exit(*, db, market, trade: dict[str, Any], meta: dict[str, Any],
               decision: XE.ExitDecision, prices: dict[str, Any], payload: dict,
               params: dict[str, Any], xp: dict[str, Any], now: datetime,
               residual: Optional[float] = None,
               model_info: Optional[dict[str, Any]] = None) -> bool:
    """Invia la chiusura. ``residual`` valorizzato = tentativo sul RESIDUO di
    un'uscita già inviata (contatore/cap separati: residual_attempts).
    ``model_info`` = numeri della decisione a modello (solo uscite in profitto),
    riportati nel log 'exit'."""
    model_info = model_info or {}
    sit = XE.situation(trade, payload)
    prev = meta.get(XE.REQUEST_KEY) if isinstance(meta.get(XE.REQUEST_KEY), dict) else {}
    on_residual = residual is not None
    if on_residual:
        r_attempts = int(prev.get("residual_attempts") or 0) + 1
        attempts = int(prev.get("attempts") or 1)
        req = {**prev, "residual_attempts": r_attempts, "residual_before": residual,
               "last_attempt_ts": now.isoformat()}
    else:
        r_attempts = 0
        attempts = int(prev.get("attempts") or 0) + 1
        req = {"kind": decision.kind, "reason": decision.reason, "ts": now.isoformat(),
               "minute": sit["minute"], "score": sit["score"], "attempts": attempts,
               "last_attempt_ts": now.isoformat(), "sent": False, "failed": False}
    meta = {**meta, XE.REQUEST_KEY: req}
    meta[XE.TRACK_KEY] = {k: v for k, v in (meta.get(XE.TRACK_KEY) or {}).items()
                          if k != "wait_reason"}
    # il marker si scrive PRIMA dell'ordine: un crash tra ordine e conferma non
    # deve mai produrre una seconda chiusura (close_trade blocca comunque con
    # una chiusura 'pending' della stessa apertura)
    db.update_trade(int(trade["id"]), meta=meta)
    trade["meta"] = meta
    extra = {"sport": trade.get("sport") or "calcio",
             "strategy": trade.get("strategy") or "manual",
             "market_type": trade.get("market_type"),
             "selection_name": trade.get("selection_name"),
             "minute_at_entry": trade.get("minute_at_entry"),
             "score_at_entry": trade.get("score_at_entry")}
    try:
        res = X.close_trade(db=db, market=market, trade=trade, prices=prices,
                            amount=None, fraction=1.0,
                            mode=str(trade.get("mode") or "paper"), now=now,
                            params=params, origin="auto", table_prefix="safe",
                            extra_row=extra)
    except Exception as ex:  # noqa: BLE001
        res = {"error": "exception", "detail": str(ex)[:160]}
    err = res.get("error")
    if err == "chiusura_in_corso":
        # un cash-out (manuale o fill flumine) è già in volo: non è un fallimento,
        # si riguarda al prossimo ciclo senza consumare tentativi
        if on_residual:
            req.update({"residual_attempts": r_attempts - 1})
        else:
            req.update({"attempts": attempts - 1})
        _persist_exit_request(db, trade, req)
        return False
    if err == "niente_da_chiudere":
        # C-04: NON è terminale. Nessun prezzo opposto utilizzabile ORA: si
        # aspetta e si RITENTA con backoff, per sempre finché il mercato è
        # aperto (prima l'uscita risultava "inviata" e la liability restava
        # piena fino al settlement).
        if on_residual:
            req.update({"residual_attempts": r_attempts - 1})
        else:
            req.update({"attempts": attempts - 1})
        waits = int((meta.get(EXIT_KEY) or {}).get("wait_attempts") or 0) + 1
        req.update({"note": err})
        _persist_exit_request(db, trade, req)
        _write_exit_state(db, trade, trade.get("meta") or meta, state="waiting_price",
                          kind=decision.kind, reason=decision.reason,
                          last_error=err, wait_attempts=waits,
                          next_retry_at=_iso_in(now, XE.retry_backoff_s(waits)))
        _log(db, "exit_wait", {"trade_id": trade.get("id"), "kind": decision.kind,
                               "reason": decision.reason, "wait": "niente_da_chiudere",
                               "attempt": waits, "note": res.get("note")})
        return False
    if err == "posizione_gia_chiusa" or \
            (isinstance(err, str) and err.startswith("trade_non_aperto")):
        req.update({"sent": True, "note": err})
        _persist_exit_request(db, trade, req)
        _write_exit_state(db, trade, trade.get("meta") or meta, state="done",
                          last_error=None, next_retry_at=None)
        return False
    if err:
        if on_residual:
            # il fallimento sul residuo conta nel SUO cap: si ritenta dopo il cooldown
            req.update({"last_error": err, "detail": res.get("detail")})
            _persist_exit_request(db, trade, req)
            _write_exit_state(db, trade, trade.get("meta") or meta, state="retrying",
                              kind=decision.kind, reason=decision.reason,
                              last_error=err, residual_attempts=r_attempts,
                              next_retry_at=None)
            _log(db, "exit_retry", {"trade_id": trade.get("id"), "kind": decision.kind,
                                    "reason": decision.reason, "residual": residual,
                                    "residual_attempt": r_attempts, "err": err})
            return False
        failed = attempts >= int(xp.get("exit_max_retries") or 3)
        # H-05/H-17: 'failed' è uno stato VISIBILE, non la fine — il prossimo
        # tentativo è già programmato col backoff crescente.
        req.update({"failed": failed, "last_error": err, "detail": res.get("detail")})
        _persist_exit_request(db, trade, req)
        _write_exit_state(db, trade, trade.get("meta") or meta,
                          state="failed" if failed else "retrying",
                          kind=decision.kind, reason=decision.reason,
                          attempts=attempts, last_error=err,
                          next_retry_at=_iso_in(now, XE.retry_backoff_s(attempts)))
        if failed:
            _log(db, "exit_failed", {"reason": "exit_failed", "trade_id": trade.get("id"),
                                     "kind": decision.kind, "exit_reason": decision.reason,
                                     "attempts": attempts, "err": err, "critical": True,
                                     "next_retry_at": _iso_in(now, XE.retry_backoff_s(attempts)),
                                     "detail": res.get("detail")})
        else:
            _log(db, "exit_retry", {"trade_id": trade.get("id"), "kind": decision.kind,
                                    "reason": decision.reason, "attempts": attempts,
                                    "err": err,
                                    "next_retry_at": _iso_in(now, XE.retry_backoff_s(attempts))})
        return False
    residual_after = res.get("residual_size")
    req.update({"sent": True, "closing_trade_id": res.get("closing_trade_id"),
                "price": res.get("price"), "size": res.get("size"),
                "pending_fill": bool(res.get("pending_fill")),
                "residual_after": residual_after})
    req.pop("last_error", None)
    req.pop("detail", None)
    # contratto UI (ExitBadge): exit_kind/exit_reason su apertura E gamba di
    # chiusura. H-01: una chiusura integrale che BLOCCA un profitto è un
    # GREEN-UP ('greenup'), non un generico 'profit'.
    lock = res.get("locked_pnl")
    if lock is None:
        lock = res.get("planned_lock")
    # M3: "integrale" = chiusura dell'INTERA posizione (fraction 1.0), non
    # "residuo già a zero". Con la coda flumine il fill arriva dopo
    # (``pending_fill``), quindi ``residual_size`` è ancora pieno: in live un
    # green-up finiva marcato 'profit'.
    integral = not on_residual and (bool(res.get("pending_fill"))
                                    or float(res.get("residual_size") or 0.0) <= XE.RESIDUAL_EPS)
    ui_kind = XE.ui_exit_kind(decision.kind, locked=lock, integral=integral)
    ui_reason = XE.reason_text(decision.kind, decision.reason)
    _persist_exit_request(db, trade, req, extra={"exit_kind": ui_kind,
                                                 "exit_reason": ui_reason})
    _write_exit_state(db, trade, trade.get("meta") or meta, state="done",
                      kind=decision.kind, reason=decision.reason,
                      last_error=None, next_retry_at=None)
    _stamp_closing_leg(db, res.get("closing_trade_id"), ui_kind, ui_reason)
    _log(db, "exit", {"trade_id": trade.get("id"), "event_id": trade.get("event_id"),
                      "exit_kind": ui_kind, "exit_reason": ui_reason,
                      "p_lose": model_info.get("p_lose"), "p_source": model_info.get("source"),
                      "ev_hold": model_info.get("ev_hold"), "model_why": model_info.get("why"),
                      "strategy": trade.get("strategy"), "mode": trade.get("mode"),
                      "reason": decision.reason, "kind": decision.kind,
                      "minute": sit["minute"], "score": sit["score"],
                      "closing_trade_id": res.get("closing_trade_id"),
                      "side": res.get("side"), "price": res.get("price"),
                      "size": res.get("size"), "locked_pnl": res.get("locked_pnl"),
                      "pending_fill": bool(res.get("pending_fill")),
                      # tentativo n. (1 = prima chiusura) e residuo prima/dopo
                      "attempt": 1 + r_attempts,
                      "residual_before": residual if on_residual else None,
                      "residual_after": residual_after,
                      "hedged_size": res.get("hedged_size")})
    return True


def _persist_exit_request(db, trade: dict[str, Any], req: dict[str, Any],
                          extra: Optional[dict[str, Any]] = None) -> None:
    """Riscrive ``meta.exit_requested`` (+ ``extra``, es. exit_kind/exit_reason)
    leggendo il meta CORRENTE della riga: close_trade ha già aggiornato la
    stessa riga (cashout_at, hedge…). A uscita inviata ``meta.exit_hold`` sparisce."""
    try:
        cur = db.get_trade(int(trade["id"])) or trade
    except Exception:  # noqa: BLE001
        cur = trade
    meta = {**(cur.get("meta") or {}), XE.REQUEST_KEY: req, **(extra or {})}
    if req.get("sent"):
        meta.pop(HOLD_KEY, None)
    try:
        db.update_trade(int(trade["id"]), meta=meta)
        trade["meta"] = meta
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] persistenza exit_requested KO (trade %s): %s",
                       trade.get("id"), str(ex)[:120])


def _stamp_closing_leg(db, closing_id: Any, ui_kind: str, ui_reason: str) -> None:
    """exit_kind/exit_reason anche sulla gamba di chiusura creata da close_trade
    (che scrive il proprio meta: si aggiorna la riga subito dopo)."""
    if closing_id is None:
        return
    try:
        leg = db.get_trade(int(closing_id))
        if not leg:
            return
        db.update_trade(int(closing_id), meta={**(leg.get("meta") or {}),
                                               "exit_kind": ui_kind,
                                               "exit_reason": ui_reason})
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] exit_kind sulla chiusura %s KO: %s", closing_id, str(ex)[:120])


# ---------------------------------------------------------------------------
# (d) segnali del motore → piazzamento automatico (reserve-first)
# ---------------------------------------------------------------------------
def _reserve_row(*, event_id, event_name, sport, strategy, market_id, market_type,
                 selection_id, selection_name, side, mode, price, size, liability,
                 commission, minute, score, origin, signal_key,
                 meta: Optional[dict] = None) -> dict[str, Any]:
    return {
        "event_id": str(event_id),
        "event_name": event_name,
        "sport": sport if sport in ("calcio", "tennis") else "calcio",
        "strategy": strategy if strategy in _STRATEGIES else "base",
        "market_id": str(market_id) if market_id else None,
        "market_type": market_type,
        "selection_id": int(selection_id),
        "selection_name": selection_name,
        "side": side,
        "mode": mode,
        "price": price,
        "size": size,
        "liability": liability,
        "commission": commission,
        "minute_at_entry": int(minute) if isinstance(minute, (int, float)) else None,
        "score_at_entry": str(score) if score is not None else None,
        "status": "pending",
        "pnl": 0.0,
        "origin": origin,
        "signal_key": signal_key,
        "meta": {"phase": "reserved", **(meta or {})},
    }


def _execute(*, db, market, trade_id: int, row: dict[str, Any], params: dict,
             now: datetime, best_size: Optional[float], ladder: Any) -> X.PlaceOutcome:
    """Esegue la riga riservata e la porta a 'open'/'error' (o la lascia
    'pending' se il fill arriva dalla coda flumine)."""
    out = X.place(
        db=db, market=market, mode=str(row["mode"]), event_id=str(row["event_id"]),
        market_id=str(row["market_id"]), selection_id=int(row["selection_id"]),
        side=str(row["side"]), price=row["price"], size=row["size"],
        best_size=best_size, ladder=ladder, client_ref=f"safe-t{trade_id}",
        trade_id=int(trade_id), meta=dict(row.get("meta") or {}), now=now,
        params=params,
    )
    if out.status == "pending":
        # coda flumine o esito REST ignoto: la riga resta 'pending' coi suoi
        # marker (li scrive place) → poll/reconcile la risolvono. MAI 'error'.
        _log(db, "place_pending", {"trade_id": trade_id, "event_id": row["event_id"],
                                   "mode": row["mode"], "note": out.fill_note})
    elif out.status == "open":
        # il meta della riserva (variant, idempotency_key, manual...) si CONSERVA
        meta = {k: v for k, v in (row.get("meta") or {}).items() if k != "phase"}
        meta["fill"] = out.fill_note
        try:
            db.update_trade(trade_id, status="open", price=out.price, size=out.size,
                            liability=X.liability_of(str(row["side"]), out.size,
                                                     out.price or 0.0),
                            bet_id=out.bet_id, meta=meta)
        except Exception as ex:  # noqa: BLE001 — ordine eseguito, riga non confermata
            logger.critical("[safe.bot] conferma DB FALLITA (trade %s, mode %s): %s",
                            trade_id, row.get("mode"), str(ex)[:160])
            _log(db, "confirm_failed", {"trade_id": trade_id, "bet_id": out.bet_id,
                                        "critical": row.get("mode") == "live"})
        _log(db, "place", {"trade_id": trade_id, "event_id": row["event_id"],
                           "side": row["side"], "price": out.price, "size": out.size,
                           "mode": row["mode"], "strategy": row.get("strategy")})
    elif out.status == "error":
        _place_fail(db, trade_id, row, out.fill_note, now, params)
    return out


# ---------------------------------------------------------------------------
# H-21 — BUDGET dei ritentativi del piazzamento AUTOMATICO rifiutato.
# Senza, un FOK ucciso dall'exchange tornava a essere ripiazzato ogni 2 s
# (la riga 'error' esce da traded_signal_keys → il segnale si ripresenta).
# ---------------------------------------------------------------------------
_PLACE_ATTEMPTS: dict[tuple[str, str], dict[str, Any]] = {}
_PLACE_SEED: dict[str, float] = {"ts": 0.0}
_PLACE_SEED_EVERY_S = 300.0


def _place_key(event_id: Any, signal_key: Any) -> tuple[str, str]:
    return (str(event_id or ""), str(signal_key or ""))


def seed_place_attempts(db, now_ts: float) -> None:
    """Riempie il budget in memoria dalle righe 'error' col marker ``meta.place``
    (sopravvive al riavvio del servizio). Al massimo ogni 5 minuti."""
    if now_ts - float(_PLACE_SEED.get("ts") or 0.0) < _PLACE_SEED_EVERY_S:
        return
    _PLACE_SEED["ts"] = now_ts
    fn = getattr(db, "place_attempts", None)
    if not callable(fn):
        return
    try:
        rows = fn() or {}
    except Exception as ex:  # noqa: BLE001
        logger.debug("[safe.bot] place_attempts KO: %s", str(ex)[:120])
        return
    for key, st in rows.items():
        cur = _PLACE_ATTEMPTS.get(tuple(key))
        if cur is not None and int(cur.get("attempts") or 0) >= int(st.get("attempts") or 0):
            continue
        last = XE.parse_ts(st.get("last_ts")) or now_ts
        _PLACE_ATTEMPTS[tuple(key)] = {
            "attempts": int(st.get("attempts") or 0), "last_ts": last,
            "final": bool(st.get("final")),
            "next_ts": last + XE.retry_backoff_s(st.get("attempts")),
        }


def place_allowed(db, now, params: dict[str, Any], event_id: Any,
                  signal_key: Any) -> Optional[str]:
    """None se il piazzamento è consentito; altrimenti il motivo del blocco
    ('place_exhausted' oltre il budget, 'place_backoff' durante l'attesa)."""
    st = _PLACE_ATTEMPTS.get(_place_key(event_id, signal_key))
    if not st:
        return None
    if st.get("final"):
        return "place_exhausted"
    now_ts = now.timestamp() if isinstance(now, datetime) else float(now)
    nxt = st.get("next_ts")
    if nxt is not None and now_ts < float(nxt):
        return "place_backoff"
    return None


def _place_fail(db, trade_id: int, row: dict[str, Any], err: str, now: datetime,
                params: dict[str, Any]) -> None:
    """Riga in 'error' TERMINALE col marker ``meta.place`` (attempts/last_error/
    next_retry_at/final) e attività ``place_retry`` / ``place_exhausted``.
    Il meta della riserva viene CONSERVATO (L-09: prima era sovrascritto)."""
    key = _place_key(row.get("event_id"), row.get("signal_key"))
    st = _PLACE_ATTEMPTS.setdefault(key, {"attempts": 0})
    st["attempts"] = int(st.get("attempts") or 0) + 1
    st["last_ts"] = now.timestamp()
    maxn = int(params.get("place_max_attempts") or 3)
    final = st["attempts"] >= maxn
    st["final"] = final
    st["next_ts"] = now.timestamp() + XE.retry_backoff_s(st["attempts"])
    place_meta = {"attempts": st["attempts"], "last_error": err,
                  "last_ts": now.isoformat(), "final": final,
                  "next_retry_at": _iso_in(now, XE.retry_backoff_s(st["attempts"]))}
    meta = {k: v for k, v in (row.get("meta") or {}).items() if k != "phase"}
    meta.update({"reason": err, "error_final": True, "place": place_meta})
    try:
        db.update_trade(trade_id, status="error", settled_at=now.isoformat(), meta=meta)
    except Exception:  # noqa: BLE001
        pass
    payload = {"trade_id": trade_id, "event_id": row.get("event_id"),
               "signal_key": row.get("signal_key"), "reason": err,
               "attempts": st["attempts"], "max_attempts": maxn,
               "next_retry_at": place_meta["next_retry_at"],
               "strategy": row.get("strategy"), "mode": row.get("mode")}
    if final:
        _log(db, "place_exhausted", {**payload, "critical": row.get("mode") == "live"})
    else:
        _log(db, "place_retry", payload)
    # compatibilità: la UI/e i log storici leggono 'skip' per il motivo
    _log(db, "skip", {"trade_id": trade_id, "event_id": row.get("event_id"),
                      "reason": err})


def _sig(signal: Any, name: str, default: Any = None) -> Any:
    if isinstance(signal, dict):
        return signal.get(name, default)
    return getattr(signal, name, default)


# dedupe dei log 'skip': {(event_id, signal_key): {"reason", "logged_ts", "seen_ts"}}
_SKIP_LOG_STATE: dict[tuple[str, str], dict[str, Any]] = {}
_SKIP_LOG_PRUNE_S = 600.0


def _log_skip(db, now: datetime, params: dict[str, Any], payload: dict[str, Any],
              kind: str = "skip") -> bool:
    """Log 'skip' (o ``kind``, es. 'risk_block') deduplicato per (kind, event_id,
    signal_key): si scrive alla prima occorrenza, al CAMBIO di motivo, o dopo
    ``skip_log_interval_s`` con lo stesso motivo. Le chiavi non viste da 10 min
    vengono eliminate. Ritorna True se il log è stato scritto."""
    key = (str(payload.get("event_id") or ""),
           str(payload.get("signal_key") or "") + ("" if kind == "skip" else f"|{kind}"))
    reason = str(payload.get("reason") or "")
    now_ts = now.timestamp()
    every = float(params.get("skip_log_interval_s") or 0.0)
    st = _SKIP_LOG_STATE
    for k in [k for k, v in st.items() if now_ts - float(v.get("seen_ts") or 0.0) > _SKIP_LOG_PRUNE_S]:
        st.pop(k, None)
    prev = st.get(key)
    write = (prev is None or prev.get("reason") != reason
             or now_ts - float(prev.get("logged_ts") or 0.0) >= every)
    if write:
        st[key] = {"reason": reason, "logged_ts": now_ts, "seen_ts": now_ts}
        _log(db, kind, payload)
    else:
        prev["seen_ts"] = now_ts
    return write


# ---------------------------------------------------------------------------
# RISCHIO: contesto di ciclo + gate prima di ogni riserva
# ---------------------------------------------------------------------------
def build_risk_ctx(db, now: datetime, params: dict[str, Any]) -> dict[str, Any]:
    """{open: posizioni vive (no gambe di chiusura), realized_today, day_liability,
    day_liability_model, agg}: UNA lettura per ciclo, aggiornata in memoria a
    ogni riserva riuscita (``_risk_commit``). Letture KO → fail-closed: contesto
    'bloccante' (loss stop finto) per non piazzare al buio."""
    try:
        open_ = [t for t in db.open_trades() or [] if not t.get("closes_trade_id")]
    except Exception as ex:  # noqa: BLE001
        _log(db, "error", {"reason": "open_count_failed", "err": str(ex)[:160]})
        return {"open": [], "realized_today": 0.0, "day_liability": 0.0,
                "day_liability_model": 0.0, "agg": {}, "unavailable": True}
    try:
        agg = dict(db.aggregates() or {})
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] aggregates KO: %s", str(ex)[:160])
        agg = {}
    return {"open": open_, "realized_today": float(agg.get("realized_today", 0.0) or 0.0),
            "day_liability": float(agg.get("day_liability", 0.0) or 0.0),
            "day_liability_model": float(agg.get("day_liability_model", 0.0) or 0.0),
            "agg": agg}


def _risk_gate(db, now: datetime, params: dict[str, Any], ctx: dict[str, Any],
               candidate: dict[str, Any], *, soft: bool = False,
               signal_key: str = "") -> Optional[str]:
    """None se il piazzamento passa, altrimenti il motivo (loggato 'risk_block'
    deduplicato per segnale e motivo)."""
    if ctx.get("unavailable"):
        reason: Optional[str] = "stato_rischio_non_leggibile"
    else:
        ok, reason = RK.check(ctx.get("open") or [], candidate, ctx.get("realized_today"),
                              params, day_liability=ctx.get("day_liability"),
                              day_liability_model=ctx.get("day_liability_model"), soft=soft)
        if ok:
            return None
    _log_skip(db, now, params, {"event_id": str(candidate.get("event_id") or ""),
                                "signal_key": signal_key, "reason": reason,
                                "strategy": candidate.get("strategy"),
                                "market_type": candidate.get("market_type"),
                                "liability": candidate.get("liability"),
                                "realized_today": ctx.get("realized_today"),
                                "day_liability": ctx.get("day_liability"),
                                "soft": soft}, kind="risk_block")
    return reason


def _risk_commit(ctx: Optional[dict[str, Any]], row: dict[str, Any]) -> None:
    """Riserva riuscita: la posizione conta SUBITO nel contesto del ciclo."""
    if not isinstance(ctx, dict):
        return
    ctx.setdefault("open", []).append(row)
    liab = max(0.0, _f(row.get("liability"), 0.0))
    ctx["day_liability"] = float(ctx.get("day_liability") or 0.0) + liab
    if str(row.get("strategy") or "") in RK.MODEL_STRATEGIES:
        ctx["day_liability_model"] = float(ctx.get("day_liability_model") or 0.0) + liab


def scan_and_place(*, db, market, engine, rows: list[dict], params: dict,
                   mode: str, now: datetime, risk_ctx: Optional[dict] = None) -> "tuple[int, int]":
    """(piazzati, segnali_attivi). Un segnale già tradato non si ripiazza (I1
    per (event_id, signal_key)); le barriere di rischio sono le stesse del
    manuale più il motore ``risk`` (gate prima della riserva)."""
    if engine is None:
        return 0, 0
    try:
        signals = list(engine.evaluate(rows) or [])
    except Exception as ex:  # noqa: BLE001 — motore rotto: nessun piazzamento
        _log(db, "error", {"reason": "engine_failed", "err": str(ex)[:160]})
        return 0, 0
    if not signals:
        return 0, 0
    try:
        traded = set(db.traded_signal_keys() or set())
    except Exception as ex:  # noqa: BLE001 — FAIL-CLOSED: senza idempotenza NON si piazza
        _log(db, "error", {"reason": "traded_keys_failed", "err": str(ex)[:160]})
        return 0, len(signals)
    if risk_ctx is None:
        risk_ctx = build_risk_ctx(db, now, params)
    if risk_ctx.get("unavailable"):
        return 0, len(signals)
    open_n = len(risk_ctx.get("open") or [])

    variants = {str(v) for v in (params.get("variants") or [])}
    max_open = int(params.get("max_open_trades") or 0)
    cap = float(params.get("max_liability_per_trade") or 0.0)
    factor = float(params.get("min_size_available_factor") or 0.0)
    commission = float(params.get("commission_pct", 5.0)) / 100.0
    max_spread = float(params.get("max_spread_ratio") or 1.6)
    rows_by_event = {str(r.get("event_id")): r for r in rows if isinstance(r, dict)
                     and r.get("event_id")}
    placed = 0
    for s in signals:
        key = _sig(s, "key")
        event_id = _sig(s, "event_id")
        if not key or not event_id:
            continue
        if (str(event_id), str(key)) in traded:
            continue
        variant = str(_sig(s, "variant") or "")
        if variants and variant not in variants:
            continue
        # H-21: budget dei ritentativi dopo un rifiuto dell'exchange
        blocked_place = place_allowed(db, now, params, event_id, key)
        if blocked_place:
            if blocked_place == "place_exhausted":
                _log_skip(db, now, params, {"event_id": str(event_id),
                                            "signal_key": str(key),
                                            "reason": blocked_place})
            continue
        if max_open and (open_n + placed) >= max_open:
            _log_skip(db, now, params, {"event_id": str(event_id), "signal_key": str(key),
                                       "reason": "max_open_trades"})
            break
        side = str(_sig(s, "side") or "").lower()
        if side not in ("back", "lay"):
            continue
        # MAI piazzare senza mercato/selezione: selection 0 = perdita certa al
        # settlement (stessa validazione del manuale).
        market_id = _sig(s, "market_id")
        sel = _sig(s, "selection_id")
        try:
            selection_id = int(sel) if sel is not None else None
        except (TypeError, ValueError):
            selection_id = None
        if not market_id or selection_id is None:
            _log_skip(db, now, params, {"event_id": str(event_id), "signal_key": str(key),
                                       "reason": "market_o_selezione_mancante",
                                       "market_id": market_id, "selection_id": sel})
            continue
        try:
            price = float(_sig(s, "price"))
            size = float(_sig(s, "size"))
        except (TypeError, ValueError):
            continue
        if price <= 1.0 or size <= 0:
            continue
        # GATE SPREAD: back/lay REALI della selezione dal feed unico; back assente
        # o lay/back > max_spread_ratio = mercato illiquido/anomalo → mai entrare
        feed_prices = prices_from_row(rows_by_event.get(str(event_id)),
                                      market_type=str(_sig(s, "market_type") or ""),
                                      selection_id=selection_id, market_id=str(market_id))
        ratio = XE.spread_ratio(feed_prices)
        if ratio is None or ratio > max_spread:
            _log_skip(db, now, params, {"event_id": str(event_id), "signal_key": str(key),
                                        "reason": "spread_anomalo",
                                        "back": (feed_prices or {}).get("back"),
                                        "lay": (feed_prices or {}).get("lay"),
                                        "spread_ratio": ratio, "max_spread_ratio": max_spread})
            continue
        avail = _sig(s, "size_available")
        if avail is not None and factor > 0:
            try:
                if float(avail) < size * factor:
                    _log_skip(db, now, params, {"event_id": str(event_id), "signal_key": str(key),
                                               "reason": "liquidita_insufficiente",
                                               "available": float(avail), "size": size})
                    continue
            except (TypeError, ValueError):
                continue
        liability = X.liability_of(side, size, price)
        if cap > 0 and liability > cap:
            _log_skip(db, now, params, {"event_id": str(event_id), "signal_key": str(key),
                                       "reason": "max_liability_per_trade", "liability": liability})
            continue
        if _risk_gate(db, now, params, risk_ctx,
                      {"event_id": str(event_id), "market_type": _sig(s, "market_type"),
                       "liability": liability, "strategy": variant},
                      signal_key=str(key)):
            continue
        row = _reserve_row(
            event_id=str(event_id), event_name=_sig(s, "event_name"),
            sport=str(_sig(s, "sport") or "calcio"),
            strategy=variant if variant in _STRATEGIES else "base",
            market_id=str(market_id), market_type=_sig(s, "market_type"),
            selection_id=selection_id,
            selection_name=_sig(s, "selection_name"), side=side, mode=mode,
            price=price, size=size, liability=liability, commission=commission,
            minute=_sig(s, "minute"), score=_sig(s, "score"),
            origin="auto", signal_key=str(key),
            meta={"variant": variant, "headline": _sig(s, "headline"),
                  "checks": _sig(s, "checks"),
                  "first_seen_ts": _sig(s, "first_seen_ts")},
        )
        try:
            trade_id = db.insert_trade(row)  # RISERVA: l'unique index fa da lock
        except Exception as ex:  # noqa: BLE001 — conflitto = già riservato altrove
            _log_skip(db, now, params, {"event_id": str(event_id), "signal_key": str(key),
                                       "reason": "already_reserved", "err": str(ex)[:120]})
            traded.add((str(event_id), str(key)))
            continue
        if not trade_id:
            continue
        traded.add((str(event_id), str(key)))
        _risk_commit(risk_ctx, {**row, "id": trade_id})
        out = _execute(db=db, market=market, trade_id=trade_id, row=row, params=params,
                       now=now, best_size=avail, ladder=())
        if out.status != "error":
            placed += 1
    return placed, len(signals)


# ---------------------------------------------------------------------------
# (e) OPPORTUNITÀ di modello (write-on-change, throttled)
# ---------------------------------------------------------------------------
_OPPS_STATE: dict[str, Any] = {"last_ts": 0.0, "hashes": {}}

# ---------------------------------------------------------------------------
# λ PRE-MATCH: catena robusta per evento (fail-closed, mai blocca il loop).
#   1. Omega: omega_service._prematch_lambdas (omega_events → fixture → pre-KO)
#   2. fixture abbinata per NOMI+kickoff (fixture_predictions, ±6h)
#   3. quote 1X2 pre-KO congelate dallo scanner (opportunity.resolve_lambdas)
#   4. default competition-agnostic (il modello penalizza la confidenza)
# Difetto live 10/09: ``payload.pre_ko`` e' None per ogni partita gia' in-play
# all'avvio dello scanner → resolve_lambdas → None → opps sempre vuote.
# ---------------------------------------------------------------------------
DEFAULT_LAMBDAS: tuple[float, float] = (1.35, 1.15)
DEFAULT_LAMBDA_RETRY_S = 300.0      # i 'default'/'pre_ko' si riprovano (la fixture puo' arrivare dopo)
LAMBDA_TTL_S = 3600.0               # L-14: TTL anche delle fonti buone (1 h)
_LAMBDA_CACHE_MAX = 2000
_FIXTURES_TTL_S = 600.0             # finestra fixture riletta ogni 10 min (una query, non una per evento)
_FIXTURE_WINDOW_H = 6               # ±6h attorno al kickoff dell'evento
_FUZZY_MIN = 0.75
_STRIP_TOKENS = frozenset({
    "fc", "sk", "ac", "as", "sc", "cf", "afc", "cd", "sd", "ud", "fk", "nk", "kf",
    "club", "utd", "united", "u17", "u18", "u19", "u20", "u21", "u23", "women",
    "w", "ii", "b", "reserves", "res", "team",
})


def _parse_iso(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _norm_team(name: Any) -> list[str]:
    """Token normalizzati: minuscolo, senza accenti/punteggiatura/sigle (fc, u19...)."""
    if not name:
        return []
    txt = "".join(c for c in unicodedata.normalize("NFD", str(name))
                  if unicodedata.category(c) != "Mn").lower()
    toks = [t for t in re.split(r"[^a-z0-9]+", txt) if t and t not in _STRIP_TOKENS]
    return sorted(toks)


def _team_sim(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    overlap = len(set(a) & set(b)) / float(len(set(a) | set(b)))
    ratio = difflib.SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    return max(overlap, ratio)


def _fuzzy_fixture(home: Any, away: Any, fixtures: list[dict]) -> Optional[dict]:
    """Matcher di RISERVA (difflib): entrambi i lati >= 0.75, diretto o invertito;
    vince il punteggio piu' alto. None se nessuna fixture supera la soglia."""
    nh, na = _norm_team(home), _norm_team(away)
    if not nh or not na:
        return None
    best, best_score = None, 0.0
    for fx in fixtures or []:
        fh, fa = _norm_team(fx.get("home_team_name")), _norm_team(fx.get("away_team_name"))
        direct = min(_team_sim(nh, fh), _team_sim(na, fa))
        inverted = min(_team_sim(nh, fa), _team_sim(na, fh))
        score = max(direct, inverted)
        if score >= _FUZZY_MIN and score > best_score:
            best, best_score = fx, score
    return best


def _event_teams(payload: dict) -> "tuple[Optional[str], Optional[str]]":
    home, away = payload.get("home"), payload.get("away")
    if home and away:
        return str(home), str(away)
    name = str(payload.get("event_name") or "")
    for sep in (" v ", " vs ", " @ "):
        if sep in name:
            a, b = name.split(sep, 1)
            return (a.strip() or None), (b.strip() or None)
    return None, None


def _fixtures_window(db, now: datetime, st: dict) -> list[dict]:
    """Fixture del giorno (cache 10 min): una query condivisa da tutti gli eventi."""
    cache = st.get("fixtures")
    if isinstance(cache, dict) and now.timestamp() - float(cache.get("ts") or 0.0) < _FIXTURES_TTL_S:
        return cache.get("rows") or []
    fn = getattr(db, "fixtures_for_window", None)
    rows: list[dict] = []
    if callable(fn):
        try:
            lo = (now - timedelta(hours=12)).isoformat()
            hi = (now + timedelta(hours=12)).isoformat()
            rows = [r for r in (fn(lo, hi) or []) if isinstance(r, dict)]
        except Exception as ex:  # noqa: BLE001
            logger.debug("[safe.bot] fixtures_for_window KO: %s", str(ex)[:120])
            rows = []
    st["fixtures"] = {"ts": now.timestamp(), "rows": rows}
    return rows


def _match_fixture(payload: dict, fixtures: list[dict]) -> Optional[dict]:
    """Fixture dell'evento per nomi squadra + kickoff (±6h). Prima il matcher
    money-critical dello stack (betfair_match.resolve_matches, lo stesso di
    Omega), poi il fuzzy difflib di riserva."""
    home, away = _event_teams(payload)
    if not home or not away or not fixtures:
        return None
    ko = _parse_iso(payload.get("open_date"))
    if ko is not None:
        window = []
        for fx in fixtures:
            fdt = _parse_iso(fx.get("fixture_date"))
            if fdt is None or abs((fdt - ko).total_seconds()) <= _FIXTURE_WINDOW_H * 3600:
                window.append(fx)
        fixtures = window
    if not fixtures:
        return None
    try:
        from Betfair.betfair_match import load_name_map, resolve_matches

        ev = {"id": str(payload.get("event_id") or "ev"), "name": f"{home} v {away}",
              "openDate": ko.isoformat() if ko else None}
        matched, _ = resolve_matches([ev], fixtures, name_map=load_name_map(),
                                     time_tolerance_min=_FIXTURE_WINDOW_H * 60)
        if matched:
            return matched[0].get("fixture")
    except Exception as ex:  # noqa: BLE001 — thefuzz assente o matcher rotto: riserva
        logger.debug("[safe.bot] resolve_matches KO: %s", str(ex)[:120])
    return _fuzzy_fixture(home, away, fixtures)


def _lambdas_from_fixture(db, fixture: dict, opp_mod: Any) -> Optional[dict]:
    fid = fixture.get("fixture_id")
    fa_fn = getattr(db, "fixture_analysis", None)
    if fid is None or not callable(fa_fn):
        return None
    analysis = fa_fn(int(fid))
    if not isinstance(analysis, dict):
        return None
    res = opp_mod.resolve_lambdas({}, fixture=analysis)   # solo inputs.lambda_*, mai pre_ko
    if not res or res[3] != "fixture":
        return None
    league_id = res[2] if res[2] is not None else fixture.get("league_id")
    ht = getattr(opp_mod, "ht_ratio_from_fixture", None)
    return {"lambdas": (float(res[0]), float(res[1])),
            "league_id": int(league_id) if league_id is not None else None,
            "source": "fixture_match",
            "ht_ratio": ht(analysis) if callable(ht) else None,
            "fixture_id": int(fid)}


def resolve_event_lambdas(*, db, event_id: str, payload: dict, opp_mod: Any,
                          now: datetime, state: dict) -> dict[str, Any]:
    """{'lambdas', 'league_id', 'source', 'ht_ratio', 'ts'} — MAI None: l'ultimo
    anello e' il default. Cache per event_id (i λ pre-match non cambiano durante
    la partita); i 'default' si riprovano ogni DEFAULT_LAMBDA_RETRY_S."""
    cache: dict = state.setdefault("lambdas", {})
    now_ts = now.timestamp()
    hit = cache.get(event_id)
    if hit:
        age = now_ts - float(hit.get("ts") or 0.0)
        weak = str(hit.get("source") or "") in ("default", "pre_ko")
        # L-14: TTL anche per le fonti "buone" (la fixture può arrivare dopo, e
        # una λ di ripiego non deve vivere quanto la partita)
        if age < (DEFAULT_LAMBDA_RETRY_S if weak else LAMBDA_TTL_S):
            return hit
    out: Optional[dict] = None
    # 1) catena di Omega (omega_events → fixture del DB → pre-KO)
    try:
        fn = getattr(_omega_service(), "_prematch_lambdas", None)
        res = fn(db, event_id, payload) if callable(fn) else None
        if res and res[0] and res[1]:
            out = {"lambdas": (float(res[0]), float(res[1])),
                   "league_id": res[2] if len(res) > 2 else None,
                   "source": str(res[3]) if len(res) > 3 and res[3] else "omega",
                   "ht_ratio": None}
    except Exception as ex:  # noqa: BLE001
        logger.debug("[safe.bot] λ omega KO %s: %s", event_id, str(ex)[:120])
    # 2) fixture abbinata per nomi + kickoff
    if out is None:
        try:
            fx = _match_fixture(payload, _fixtures_window(db, now, state))
            if fx:
                out = _lambdas_from_fixture(db, fx, opp_mod)
        except Exception as ex:  # noqa: BLE001
            logger.debug("[safe.bot] λ fixture_match KO %s: %s", event_id, str(ex)[:120])
    # 3) quote 1X2 pre-KO congelate dallo scanner
    if out is None:
        try:
            resolve = getattr(opp_mod, "resolve_lambdas", None)
            res = resolve(payload, fixture=None) if callable(resolve) else None
            if res:
                out = {"lambdas": (float(res[0]), float(res[1])),
                       "league_id": res[2] if len(res) > 2 else None,
                       "source": str(res[3]) if len(res) > 3 else "pre_ko", "ht_ratio": None}
        except Exception as ex:  # noqa: BLE001
            logger.debug("[safe.bot] λ pre_ko KO %s: %s", event_id, str(ex)[:120])
    # 4) default: il modello penalizza la confidenza (default_lambda_confidence)
    if out is None:
        out = {"lambdas": DEFAULT_LAMBDAS, "league_id": None, "source": "default",
               "ht_ratio": None}
        if hit is None:
            logger.info("[safe.bot] λ di default per %s (%s): nessuna fonte pre-match",
                        event_id, payload.get("event_name"))
    out["ts"] = now_ts
    if len(cache) >= _LAMBDA_CACHE_MAX:
        cache.clear()
    cache[event_id] = out
    return out


def _hash(obj: Any) -> str:
    try:
        blob = json.dumps(obj, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = repr(obj)
    return hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()


def _ev_conf(o: Any) -> float:
    try:
        return float(o.get("ev") or 0.0) * float(o.get("confidence") or 0.0)
    except (TypeError, ValueError, AttributeError):
        return 0.0


def _tag(opps: Any, kind: str) -> list[dict]:
    """Lista di dict con ``kind`` valorizzato (gli elementi non-dict si scartano)."""
    out: list[dict] = []
    for o in opps or []:
        if isinstance(o, dict):
            o = dict(o)
            o.setdefault("kind", kind)
            out.append(o)
    return out


def _tennis_model(mod: Any, params: dict[str, Any], st: dict[str, Any]) -> Any:
    """TennisOpportunityModel(params) condiviso nello stato (uno per processo)."""
    if mod is None:
        return None
    cached = st.get("tennis_model")
    if cached is not None and st.get("tennis_mod") is mod:
        return cached
    try:
        m = mod.TennisOpportunityModel(params)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] TennisOpportunityModel KO: %s", str(ex)[:120])
        return None
    st["tennis_model"], st["tennis_mod"] = m, mod
    return m


def _book_for(db, model: Any, opp_mod: Any, event_id: str, payload: dict, now: datetime,
              st: dict[str, Any]) -> "tuple[Optional[dict], dict]":
    """(book del modello sullo stato live, λ risolte); book None se KO."""
    try:
        lam = resolve_event_lambdas(db=db, event_id=event_id, payload=payload,
                                    opp_mod=opp_mod, now=now, state=st)
    except Exception as ex:  # noqa: BLE001
        logger.debug("[safe.bot] resolve_event_lambdas KO %s: %s", event_id, str(ex)[:120])
        lam = {"lambdas": DEFAULT_LAMBDAS, "league_id": None, "source": "default",
               "ht_ratio": None}
    try:
        book = model.book(payload, lambdas=lam["lambdas"], league_id=lam.get("league_id"),
                          ht_ratio=lam.get("ht_ratio"))
    except Exception as ex:  # noqa: BLE001
        logger.debug("[safe.bot] book KO %s: %s", event_id, str(ex)[:120])
        book = None
    return (book if isinstance(book, dict) else None), lam


def process_opportunities(*, db, market, rows: list[dict], params: dict, model: Any,
                          opp_mod: Any, mode: str, now: datetime,
                          state: Optional[dict] = None,
                          auto_trade: bool = False,
                          rows_by_event: Optional[dict] = None,
                          extra: Optional[dict] = None,
                          auto_trade_kinds: Optional[dict] = None,
                          risk_ctx: Optional[dict] = None) -> dict[str, int]:
    """Calcola le opportunità sugli in-play (calcio: modello + combo + anomalie
    dell'ultimo cecchino; tennis: modello tennis) e le pubblica (write-on-change),
    ogni ``opps_interval_s``. ``opps`` di ogni evento = tutti i tipi fusi e
    ordinati per ev·confidenza, ciascuno con ``kind`` (model|anomaly|combo|tennis).
    Auto-trading per tipo (``auto_trade_kinds``): model (=``auto_trade``), combo
    (tutte le gambe o nessuna), tennis. Ritorna {'events': n, 'written': n,
    'traded': n}; i conteggi per tipo restano in ``state['counts']``."""
    out = {"events": 0, "written": 0, "traded": 0}
    st = state if state is not None else _OPPS_STATE
    mods = _extra_mods(extra)
    kinds = dict(auto_trade_kinds or {})
    kinds.setdefault("model", auto_trade)
    tennis_model = _tennis_model(mods.get("tennis"), params, st)
    if model is None or opp_mod is None:
        if tennis_model is None:
            return out
    every = float(params.get("opps_interval_s") or 10.0)
    now_ts = now.timestamp()
    if now_ts - float(st.get("last_ts") or 0.0) < every:
        return out
    st["last_ts"] = now_ts
    hashes = st.setdefault("hashes", {})
    counts = {"model": 0, "anomaly": 0, "combo": 0, "tennis": 0}
    to_write: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        sport = str(row.get("sport") or "")
        payload = row.get("payload")
        if not isinstance(payload, dict) or not payload.get("inplay"):
            continue
        event_id = str(row.get("event_id") or "")
        if not event_id:
            continue
        if sport == "tennis":
            if tennis_model is None:
                continue
            try:
                t_opps = _tag(tennis_model.evaluate(payload, now_ts), "tennis")
            except Exception as ex:  # noqa: BLE001
                _log(db, "error", {"reason": "tennis_opportunity_failed", "event_id": event_id,
                                   "err": str(ex)[:160]})
                continue
            out["events"] += 1
            counts["tennis"] += len(t_opps)
            # contratto UI: `kinds` ha SEMPRE le stesse quattro chiavi, su
            # ogni sport (prima le righe tennis non lo scrivevano affatto e la
            # riga calcio non aveva `tennis`: conteggi non confrontabili).
            body = {"event_name": payload.get("event_name"), "sets": payload.get("sets"),
                    "games": payload.get("games"), "opportunities": t_opps,
                    "kinds": {"model": 0, "anomaly": 0, "combo": 0,
                              "tennis": len(t_opps)}}
            h = _hash(body)
            if hashes.get(event_id) != h:
                hashes[event_id] = h
                to_write.append({"event_id": event_id, "sport": "tennis",
                                 "payload": body, "updated_at": now.isoformat()})
            if kinds.get("tennis") and t_opps:
                out["traded"] += _auto_trade_opps(
                    db=db, market=market, payload=payload, event_id=event_id, opps=t_opps,
                    params=params, mode=mode, now=now, rows_by_event=rows_by_event or {},
                    sport="tennis", kind="tennis", risk_ctx=risk_ctx)
            continue
        if sport != "calcio" or model is None or opp_mod is None:
            continue
        out["events"] += 1
        seen.add(event_id)
        try:
            lam = resolve_event_lambdas(db=db, event_id=event_id, payload=payload,
                                        opp_mod=opp_mod, now=now, state=st)
        except Exception as ex:  # noqa: BLE001 — la catena e' gia' fail-closed: cintura
            logger.debug("[safe.bot] resolve_event_lambdas KO %s: %s", event_id, str(ex)[:120])
            lam = {"lambdas": DEFAULT_LAMBDAS, "league_id": None, "source": "default",
                   "ht_ratio": None}
        lambdas, league_id, source = lam["lambdas"], lam.get("league_id"), lam.get("source")
        try:
            opps = list(model.evaluate(payload, sport="calcio", lambdas=lambdas,
                                       league_id=league_id, now_ts=now_ts,
                                       lambda_source=source,
                                       ht_ratio=lam.get("ht_ratio")) or [])
        except Exception as ex:  # noqa: BLE001 — un evento rotto non ferma gli altri
            _log(db, "error", {"reason": "opportunity_failed", "event_id": event_id,
                               "err": str(ex)[:160]})
            continue
        opps = _tag(opps, "model")
        counts["model"] += len(opps)
        combos: list[dict] = []
        if mods.get("combos") is not None:
            book, _lam = _book_for(db, model, opp_mod, event_id, payload, now, st)
            if book is not None:
                try:
                    combos = _tag(mods["combos"].find_combos(payload, book, params=params), "combo")
                except Exception as ex:  # noqa: BLE001
                    _log(db, "error", {"reason": "combos_failed", "event_id": event_id,
                                       "err": str(ex)[:160]})
        anomalies = _tag((st.get("anomalies") or {}).get(event_id), "anomaly")
        counts["combo"] += len(combos)
        counts["anomaly"] += len(anomalies)
        merged = sorted(opps + anomalies + combos, key=_ev_conf, reverse=True)
        body = {"event_name": payload.get("event_name"),
                "minute": payload.get("minute"),
                "score_home": payload.get("score_home"),
                "score_away": payload.get("score_away"),
                "league_id": league_id,
                "source": source,
                "lambdas": [lambdas[0], lambdas[1]],
                "opportunities": merged,
                "kinds": {"model": len(opps), "anomaly": len(anomalies),
                          "combo": len(combos), "tennis": 0}}
        h = _hash(body)
        if hashes.get(event_id) != h:
            hashes[event_id] = h
            to_write.append({"event_id": event_id, "sport": "calcio",
                             "payload": body, "updated_at": now.isoformat()})
        if kinds.get("model") and opps:
            out["traded"] += _auto_trade_opps(
                db=db, market=market, payload=payload, event_id=event_id, opps=opps,
                params=params, mode=mode, now=now,
                rows_by_event=rows_by_event or {}, risk_ctx=risk_ctx)
        if kinds.get("combo") and combos:
            out["traded"] += _auto_trade_combos(
                db=db, market=market, payload=payload, event_id=event_id, combos=combos,
                params=params, mode=mode, now=now, rows_by_event=rows_by_event or {},
                risk_ctx=risk_ctx)
    st["counts"] = counts
    if to_write:
        try:
            db.upsert_opportunities(to_write)
            out["written"] = len(to_write)
        except Exception as ex:  # noqa: BLE001
            _log(db, "error", {"reason": "opps_write_failed", "err": str(ex)[:160]})
    # righe di partite FINITE (non riscritte da OPPS_ROW_TTL_S): via dalla tabella,
    # al massimo una volta ogni OPPS_PURGE_EVERY_S — il passato non è un'opportunità
    purge_fn = getattr(db, "purge_opportunities", None)
    last_purge = float(st.get("last_purge_ts") or 0.0)
    if callable(purge_fn) and now.timestamp() - last_purge >= OPPS_PURGE_EVERY_S:
        st["last_purge_ts"] = now.timestamp()
        try:
            purge_fn((now - timedelta(seconds=OPPS_ROW_TTL_S)).isoformat())
        except Exception as ex:  # noqa: BLE001
            _log(db, "error", {"reason": "opps_purge_failed", "err": str(ex)[:160]})
    # la cache λ vive quanto la partita: via gli eventi usciti dal feed
    # (solo se il feed ha risposto: un feed vuoto per errore non svuota la cache)
    if rows:
        lam_cache = st.get("lambdas")
        if isinstance(lam_cache, dict):
            for eid in [k for k in lam_cache if k not in seen]:
                lam_cache.pop(eid, None)
    return out


def _p_lose_entry(o: dict, side: str) -> Optional[float]:
    """P(perdita) all'ingresso dal p_model dell'opportunità (riferimento della
    regola 'evento avverso' delle uscite a modello)."""
    p = o.get("p_model")
    if not isinstance(p, (int, float)) or isinstance(p, bool):
        return None
    p = min(1.0, max(0.0, float(p)))
    return round(p if side == "lay" else 1.0 - p, 4)


def _model_meta(o: dict, kind: str, side: str) -> dict[str, Any]:
    return {"kind": kind, "p_model": o.get("p_model"), "p_implied": o.get("p_implied"),
            "edge": o.get("edge"), "ev": o.get("ev"), "confidence": o.get("confidence"),
            "rationale": o.get("rationale"), "line": o.get("line"),
            "p_lose_entry": _p_lose_entry(o, side)}


def _score_of(payload: dict, sport: str) -> Optional[str]:
    if sport == "tennis":
        sets, games = payload.get("sets") or {}, payload.get("games") or {}
        if isinstance(sets, dict) and sets.get("p1") is not None:
            s = f"set {sets.get('p1')}-{sets.get('p2')}"
            if isinstance(games, dict) and games.get("p1") is not None:
                s += f" · game {games.get('p1')}-{games.get('p2')}"
            return s
        return None
    if payload.get("score_home") is None:
        return None
    return f"{payload.get('score_home')}-{payload.get('score_away')}"


def _auto_trade_opps(*, db, market, payload: dict, event_id: str, opps: list,
                     params: dict, mode: str, now: datetime,
                     rows_by_event: dict, sport: str = "calcio", kind: str = "model",
                     risk_ctx: Optional[dict] = None) -> int:
    """Tratta le opportunità che superano confidenza+edge minimi (strategia
    'model', tipo in ``meta.kind``; tennis: stake ``risk.model_stake``).
    DISATTIVO per default: si accende solo da parametri. Gate ``risk`` prima
    della riserva."""
    min_conf = float(params.get("opps_min_confidence") or 0.0)
    min_edge = float(params.get("opps_min_edge") or 0.0)
    stake = float(params.get("opps_stake") or 0.0) if kind == "model" \
        else float(RK.risk_params(params).get("model_stake") or 0.0)
    cap = float(params.get("max_liability_per_trade") or 0.0)
    commission = float(params.get("commission_pct", 5.0)) / 100.0
    if stake <= 0:
        return 0
    try:
        traded = set(db.traded_signal_keys() or set())
    except Exception:  # noqa: BLE001 — FAIL-CLOSED
        return 0
    if risk_ctx is None:
        risk_ctx = build_risk_ctx(db, now, params)
    n = 0
    for o in opps:
        if not isinstance(o, dict):
            continue
        try:
            if float(o.get("confidence") or 0.0) < min_conf:
                continue
            if float(o.get("edge") or 0.0) < min_edge:
                continue
            price = float(o.get("price"))
            selection_id = int(o.get("selection_id"))
        except (TypeError, ValueError):
            continue
        side = str(o.get("side") or "").lower()
        if side not in ("back", "lay") or price <= 1.0:
            continue
        market_type = str(o.get("market_type") or "")
        key = f"{kind}:{market_type}:{selection_id}:{side}"
        if (event_id, key) in traded:
            continue
        if place_allowed(db, now, params, event_id, key):
            continue   # H-21: budget esaurito / backoff in corso
        if not o.get("market_id"):
            _log_skip(db, now, params, {"event_id": event_id, "signal_key": key,
                                       "reason": "market_o_selezione_mancante"})
            continue
        avail = o.get("size_available")
        liability = X.liability_of(side, stake, price)
        if cap > 0 and liability > cap:
            continue
        if _risk_gate(db, now, params, risk_ctx,
                      {"event_id": event_id, "market_type": market_type,
                       "liability": liability, "strategy": "model"}, signal_key=key):
            continue
        row = _reserve_row(
            event_id=event_id, event_name=payload.get("event_name"), sport=sport,
            strategy="model", market_id=o.get("market_id"), market_type=market_type,
            selection_id=selection_id, selection_name=o.get("selection_name"),
            side=side, mode=mode, price=price, size=stake, liability=liability,
            commission=commission, minute=payload.get("minute"),
            score=_score_of(payload, sport),
            origin="auto", signal_key=key, meta=_model_meta(o, kind, side),
        )
        try:
            trade_id = db.insert_trade(row)
        except Exception:  # noqa: BLE001 — già riservata
            traded.add((event_id, key))
            continue
        if not trade_id:
            continue
        traded.add((event_id, key))
        _risk_commit(risk_ctx, {**row, "id": trade_id})
        out = _execute(db=db, market=market, trade_id=trade_id, row=row, params=params,
                       now=now, best_size=avail, ladder=())
        if out.status != "error":
            n += 1
    return n


# ---------------------------------------------------------------------------
# COMBO: tutte le gambe o nessuna
# ---------------------------------------------------------------------------
def _leg_matchable(leg: dict, stake: float, rows_by_event: dict, event_id: str) -> bool:
    """Gamba abbinabile in paper: prezzo > 1 e liquidità (size_available
    dell'opportunità o del feed) ≥ stake."""
    try:
        price = float(leg.get("price"))
    except (TypeError, ValueError):
        return False
    if price <= 1.0:
        return False
    side = str(leg.get("side") or "").lower()
    avail = leg.get("size_available")
    if avail is None:
        try:
            p = prices_from_row(rows_by_event.get(str(event_id)),
                                market_type=str(leg.get("market_type") or ""),
                                selection_id=int(leg.get("selection_id")),
                                market_id=leg.get("market_id"))
        except (TypeError, ValueError):
            p = None
        avail = (p or {}).get(f"{side}_size")
    try:
        return float(avail) >= stake
    except (TypeError, ValueError):
        return False


def _auto_trade_combos(*, db, market, payload: dict, event_id: str, combos: list,
                       params: dict, mode: str, now: datetime, rows_by_event: dict,
                       risk_ctx: Optional[dict] = None) -> int:
    """Piazza ogni combo con TUTTE le gambe o NESSUNA: soglie su confidenza/edge
    della combo, gate ``risk`` sulla liability complessiva, riserva di tutte le
    gambe (una qualunque fallita → le riserve fatte si liberano), in paper una
    gamba non abbinabile → combo saltata. STAKE: ``risk.model_stake`` per gamba
    in media, ripartito secondo le proporzioni di dutching della combo
    (``stake_ratio``: gamba = model_stake × n_gambe × ratio; senza ratio, uguale
    per tutte). Ritorna il numero di combo piazzate."""
    min_conf = float(params.get("opps_min_confidence") or 0.0)
    min_edge = float(params.get("opps_min_edge") or 0.0)
    stake = float(RK.risk_params(params).get("model_stake") or 0.0)
    cap = float(params.get("max_liability_per_trade") or 0.0)
    commission = float(params.get("commission_pct", 5.0)) / 100.0
    if stake <= 0:
        return 0
    try:
        traded = set(db.traded_signal_keys() or set())
    except Exception:  # noqa: BLE001
        return 0
    if risk_ctx is None:
        risk_ctx = build_risk_ctx(db, now, params)
    n = 0
    for c in combos:
        if not isinstance(c, dict):
            continue
        legs = [l for l in (c.get("legs") or []) if isinstance(l, dict)]
        if len(legs) < 2:
            continue
        try:
            if float(c.get("confidence") or 0.0) < min_conf or float(c.get("edge") or 0.0) < min_edge:
                continue
        except (TypeError, ValueError):
            continue
        cid = str(c.get("id") or _hash([(l.get("market_id"), l.get("selection_id"), l.get("side"))
                                        for l in legs])[:12])
        keys = [f"combo:{cid}:{i}" for i in range(len(legs))]
        if any((event_id, k) in traded for k in keys):
            continue
        if any(place_allowed(db, now, params, event_id, k) for k in keys):
            continue   # H-21: una gamba ha esaurito il budget → combo ferma
        rows: list[dict] = []
        total_liab = 0.0
        ok = True
        ratios = [_f(l.get("stake_ratio"), 0.0) for l in legs]
        if any(r <= 0 for r in ratios) or abs(sum(ratios) - 1.0) > 0.05:
            ratios = [1.0 / len(legs)] * len(legs)
        for leg, key, ratio in zip(legs, keys, ratios):
            side = str(leg.get("side") or "").lower()
            leg_stake = round(stake * len(legs) * ratio, 2)
            try:
                price = float(leg.get("price"))
                sid = int(leg.get("selection_id"))
            except (TypeError, ValueError):
                ok = False
                break
            if side not in ("back", "lay") or price <= 1.0 or not leg.get("market_id")                     or leg_stake <= 0:
                ok = False
                break
            if mode == "paper" and not _leg_matchable(leg, leg_stake, rows_by_event, event_id):
                _log_skip(db, now, params, {"event_id": event_id, "signal_key": key,
                                           "reason": "combo_gamba_non_abbinabile"})
                ok = False
                break
            liab = X.liability_of(side, leg_stake, price)
            if cap > 0 and liab > cap:
                ok = False
                break
            total_liab += liab
            rows.append(_reserve_row(
                event_id=event_id, event_name=payload.get("event_name"), sport="calcio",
                strategy="model", market_id=leg.get("market_id"),
                market_type=str(leg.get("market_type") or ""), selection_id=sid,
                selection_name=leg.get("selection_name"), side=side, mode=mode, price=price,
                size=leg_stake, liability=liab, commission=commission, minute=payload.get("minute"),
                score=_score_of(payload, "calcio"), origin="auto", signal_key=key,
                meta={**_model_meta(leg, "combo", side), "combo_id": cid,
                      "combo_legs": len(legs), "combo_rationale": c.get("rationale")}))
        if not ok:
            continue
        if _risk_gate(db, now, params, risk_ctx,
                      {"event_id": event_id, "market_type": "COMBO",
                       "liability": round(total_liab, 2), "strategy": "model"},
                      signal_key=f"combo:{cid}"):
            continue
        ids: list[int] = []
        for row in rows:
            try:
                tid = db.insert_trade(row)
            except Exception:  # noqa: BLE001
                tid = None
            if not tid:
                break
            ids.append(int(tid))
        if len(ids) != len(rows):
            for tid in ids:   # tutte o nessuna: si liberano le riserve fatte
                try:
                    db.delete_trade(tid)
                except Exception:  # noqa: BLE001
                    pass
            _log_skip(db, now, params, {"event_id": event_id, "signal_key": f"combo:{cid}",
                                       "reason": "combo_riserva_incompleta"})
            for k in keys:
                traded.add((event_id, k))
            continue
        for k in keys:
            traded.add((event_id, k))
        placed_legs = 0
        live_ids: list[int] = []
        filled_ids: list[int] = []
        for row, tid in zip(rows, ids):
            _risk_commit(risk_ctx, {**row, "id": tid})
            out = _execute(db=db, market=market, trade_id=tid, row=row, params=params,
                           now=now, best_size=row.get("size"), ladder=())
            if out.status != "error":
                placed_legs += 1
                live_ids.append(int(tid))
                if out.status == "open":
                    filled_ids.append(int(tid))
        if placed_legs == len(rows):
            n += 1
        elif placed_legs:
            # H-20: tutto-o-niente ANCHE dopo il fill — una gamba in errore con
            # un'altra viva lascia una posizione NUDA: si chiude subito quella
            # già abbinata e si MARCA quella in coda (H6: il fill arriva dopo,
            # la svolge ``unwind_incomplete_combos`` appena è confermato).
            pending_ids = [i for i in live_ids if i not in filled_ids]
            _mark_combo_incomplete(db, live_ids, cid)
            _log(db, "combo_incomplete", {"event_id": event_id, "combo_id": cid,
                                          "placed": placed_legs, "legs": len(rows),
                                          "filled_ids": filled_ids,
                                          "pending_ids": pending_ids, "critical": True})
            _unwind_combo(db=db, market=market, ids=filled_ids,
                          rows_by_event=rows_by_event, event_id=event_id,
                          params=params, now=now)
    return n


COMBO_INCOMPLETE_KEY = "combo_incomplete"


def _mark_combo_incomplete(db, ids: list[int], combo_id: str) -> None:
    """``meta.combo_incomplete=True`` su ogni gamba viva di una combo rotta:
    il marker sopravvive al riavvio e alla coda (H6)."""
    for tid in ids:
        try:
            leg = db.get_trade(int(tid))
            if not leg or str(leg.get("status")) in ("error", "won", "lost", "void"):
                continue
            db.update_trade(int(tid), meta={**(leg.get("meta") or {}),
                                            COMBO_INCOMPLETE_KEY: True,
                                            "combo_id": combo_id})
        except Exception as ex:  # noqa: BLE001
            logger.warning("[safe.bot] marker combo_incomplete %s KO: %s", tid, str(ex)[:120])


def unwind_incomplete_combos(*, db, market, rows_by_event: dict, params: dict,
                             now: datetime,
                             open_rows: Optional[list[dict[str, Any]]] = None) -> int:
    """H6 — svolge le gambe di combo ROTTE appena il loro fill è confermato.

    Una gamba accodata su flumine diventa 'open' uno o più cicli dopo: senza
    questo passaggio la posizione NUDA di una combo incompleta restava aperta
    (in live, soldi veri scoperti). Gira a OGNI ciclo, anche a bot fermo."""
    rows = open_rows if open_rows is not None else _safe_open_trades(db)
    todo = [t for t in rows or []
            if (t.get("meta") or {}).get(COMBO_INCOMPLETE_KEY)
            and str(t.get("status")) == "open"
            and not t.get("closes_trade_id")
            and not X.has_closing_marker(t)]
    if not todo:
        return 0
    return _unwind_combo(db=db, market=market, ids=[int(t["id"]) for t in todo],
                         rows_by_event=rows_by_event, event_id="", params=params,
                         now=now)


def _safe_open_trades(db) -> list[dict[str, Any]]:
    try:
        return list(db.open_trades() or [])
    except Exception:  # noqa: BLE001
        return []


def _unwind_combo(*, db, market, ids: list[int], rows_by_event: dict, event_id: str,
                  params: dict, now: datetime) -> int:
    """Chiude le gambe FILLATE di una combo rimasta incompleta (uscita 'forced',
    motivo "combo incompleta"). Un fallimento qui è CRITICO e va loggato: resta
    una posizione scoperta che il ciclo successivo riprende."""
    closed = 0
    for tid in ids:
        try:
            leg = db.get_trade(int(tid))
        except Exception:  # noqa: BLE001
            leg = None
        if not leg or str(leg.get("status")) != "open":
            continue
        prices = prices_from_row(rows_by_event.get(str(leg.get("event_id") or event_id)),
                                 market_type=str(leg.get("market_type") or ""),
                                 selection_id=int(leg.get("selection_id") or 0),
                                 market_id=leg.get("market_id"))
        if not prices or not (prices.get("back") or prices.get("lay")):
            _log(db, "exit_failed", {"reason": "combo_incompleta_senza_prezzi",
                                     "trade_id": tid, "critical": True})
            continue
        if _close_combo_siblings(db=db, market=market, legs=[leg],
                                 prices_by_id={int(tid): prices}, params=params,
                                 now=now, reason="combo incompleta: gamba chiusa subito"):
            closed += 1
    return closed


# ---------------------------------------------------------------------------
# ANOMALIE: cecchino a OGNI ciclo (righe con quote cambiate), FOK, dedupe 120 s
# ---------------------------------------------------------------------------
ANOMALY_DEDUPE_S = 120.0


def _anomaly_recent(traded: set, event_id: str, prefix: str, now_ts: float) -> bool:
    """Chiave 'anomaly:...:<epoch>' già tradata negli ultimi ANOMALY_DEDUPE_S
    (regge anche al riavvio: il dedupe in memoria si perde, il DB no)."""
    for eid, k in traded:
        if eid != event_id or not str(k).startswith(prefix):
            continue
        try:
            ts = float(str(k)[len(prefix):])
        except ValueError:
            continue
        if now_ts - ts < ANOMALY_DEDUPE_S:
            return True
    return False


def process_anomalies(*, db, market, rows: list[dict], params: dict, model: Any,
                      opp_mod: Any, anomaly_mod: Any, mode: str, now: datetime,
                      state: Optional[dict] = None, auto_trade: bool = False,
                      rows_by_event: Optional[dict] = None,
                      risk_ctx: Optional[dict] = None) -> dict[str, int]:
    """Valuta ``anomaly.detect(payload, book, params=)`` per ogni in-play calcio
    il cui ``odds_ts_ms`` è cambiato dall'ultima valutazione (ogni ciclo, non
    sulla cadenza delle opportunità); l'ultimo esito per evento resta in
    ``state['anomalies']`` (la UI lo vede fuso nelle opportunità). Con
    ``auto_trade``: piazzamento IMMEDIATO come cecchino (FOK di execution.place),
    stake ``risk.model_stake``, dedupe per (evento, mercato, selezione, lato)
    per 120 s. Ritorna {'events','found','traded'}."""
    out = {"events": 0, "found": 0, "traded": 0}
    if anomaly_mod is None or model is None or opp_mod is None:
        return out
    st = state if state is not None else _OPPS_STATE
    seen_ts = st.setdefault("anomaly_ts", {})
    found_by_event = st.setdefault("anomalies", {})
    dedupe = st.setdefault("anomaly_dedupe", {})
    now_ts = now.timestamp()
    for k in [k for k, v in dedupe.items() if now_ts - float(v) >= ANOMALY_DEDUPE_S]:
        dedupe.pop(k, None)
    stake = float(RK.risk_params(params).get("model_stake") or 0.0)
    cap = float(params.get("max_liability_per_trade") or 0.0)
    commission = float(params.get("commission_pct", 5.0)) / 100.0
    traded: Optional[set] = None
    live_ids: set[str] = set()
    for row in rows:
        if str(row.get("sport") or "") != "calcio":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict) or not payload.get("inplay"):
            continue
        event_id = str(row.get("event_id") or "")
        if not event_id:
            continue
        live_ids.add(event_id)
        ts = payload.get("odds_ts_ms")
        if ts is not None and seen_ts.get(event_id) == ts:
            continue
        seen_ts[event_id] = ts
        out["events"] += 1
        book, _lam = _book_for(db, model, opp_mod, event_id, payload, now, st)
        if book is None:
            continue
        try:
            found = _tag(anomaly_mod.detect(payload, book, params=params), "anomaly")
        except Exception as ex:  # noqa: BLE001
            _log(db, "error", {"reason": "anomaly_failed", "event_id": event_id,
                               "err": str(ex)[:160]})
            continue
        found_by_event[event_id] = found
        out["found"] += len(found)
        if not auto_trade or not found or stake <= 0:
            continue
        if traded is None:
            try:
                traded = set(db.traded_signal_keys() or set())
            except Exception:  # noqa: BLE001 — FAIL-CLOSED
                return out
        if risk_ctx is None:
            risk_ctx = build_risk_ctx(db, now, params)
        for o in found:
            try:
                price = float(o.get("price"))
                sid = int(o.get("selection_id"))
            except (TypeError, ValueError):
                continue
            side = str(o.get("side") or "").lower()
            mt = str(o.get("market_type") or "")
            mid = o.get("market_id")
            if side not in ("back", "lay") or price <= 1.0 or not mid:
                continue
            dkey = (event_id, str(mid), sid, side)
            prefix = f"anomaly:{mt}:{sid}:{side}:"
            if dkey in dedupe or _anomaly_recent(traded, event_id, prefix, now_ts):
                continue
            liability = X.liability_of(side, stake, price)
            if cap > 0 and liability > cap:
                continue
            key = f"{prefix}{int(now_ts)}"
            if _risk_gate(db, now, params, risk_ctx,
                          {"event_id": event_id, "market_type": mt,
                           "liability": liability, "strategy": "model"}, signal_key=key):
                continue
            row = _reserve_row(
                event_id=event_id, event_name=payload.get("event_name"), sport="calcio",
                strategy="model", market_id=mid, market_type=mt, selection_id=sid,
                selection_name=o.get("selection_name"), side=side, mode=mode, price=price,
                size=stake, liability=liability, commission=commission,
                minute=payload.get("minute"), score=_score_of(payload, "calcio"),
                origin="auto", signal_key=key,
                meta={**_model_meta(o, "anomaly", side), "sniper": True,
                      "anomaly_type": o.get("anomaly_type") or o.get("type")})
            try:
                trade_id = db.insert_trade(row)
            except Exception:  # noqa: BLE001
                dedupe[dkey] = now_ts
                continue
            if not trade_id:
                continue
            dedupe[dkey] = now_ts
            traded.add((event_id, key))
            _risk_commit(risk_ctx, {**row, "id": trade_id})
            res = _execute(db=db, market=market, trade_id=trade_id, row=row, params=params,
                           now=now, best_size=o.get("size_available"), ladder=())
            if res.status != "error":
                out["traded"] += 1
    if rows:
        for eid in [k for k in list(found_by_event) if k not in live_ids]:
            found_by_event.pop(eid, None)
            seen_ts.pop(eid, None)
    return out


# ---------------------------------------------------------------------------
# CICLO
# ---------------------------------------------------------------------------
def run_once(*, db=_real_db, market=_real_market, engine=None, opp_model=None,
             opp_mod: Any = None, engine_mod: Any = None,
             now: Optional[datetime] = None,
             opps_state: Optional[dict] = None,
             extra_mods: Optional[dict] = None) -> dict[str, Any]:
    now = now or _now()
    try:
        control = db.read_control()
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] read_control KO: %s", str(ex)[:160])
        return {"skipped": "control_unreadable"}
    if control is None:
        return {"skipped": "no_control"}
    status = str(control.get("status") or "idle")
    mode = str(control.get("mode") or "paper")
    if mode not in ("paper", "live"):
        mode = "paper"
    raw_params = control.get("params")
    params = resolve_params(raw_params, engine_mod=engine_mod)
    # H-14/H-15: i valori CLAMPATI/normalizzati tornano sul DB (la scheda
    # parametri deve mostrare quello che è davvero in uso) + attività.
    normalize_control_params(db, raw_params, params, now)

    # feed unico: UNA sola lettura per ciclo, condivisa da TUTTE le fasi —
    # letta per PRIMA perché anche il settlement la usa per decidere se vale la
    # pena chiamare Betfair (H-19).
    try:
        rows = list(db.fetch_scan_rows() or [])
    except Exception as ex:  # noqa: BLE001
        _log(db, "error", {"reason": "feed_failed", "err": str(ex)[:160]})
        rows = []
    rows_by_event = {str(r.get("event_id")): r for r in rows if r.get("event_id")}

    # (a) coda flumine — SEMPRE (anche a bot fermo: mai posizioni nude)
    n_polled = poll_flumine(db=db, params=params, now=now, market=market)
    # (a-bis) pending SENZA marker flumine (esito REST ignoto) → stato reale Betfair
    n_reconciled = reconcile_pending(market=market, db=db, now=now)
    # (b) settlement — SEMPRE
    n_settled = settle_open(params=params, market=market, db=db, now=now,
                            rows_by_event=rows_by_event)

    # budget dei ritentativi di piazzamento: recupero dopo un riavvio (H-21)
    seed_place_attempts(db, now.timestamp())

    # contesto di RISCHIO del ciclo (una lettura: posizioni vive + aggregati)
    risk_ctx = build_risk_ctx(db, now, params)

    # (b-bis) H-18: posizioni vive senza riga nel feed = cecità, mai silenzio
    n_blind = check_feed_blind(db, risk_ctx.get("open") or [], rows_by_event, now)

    # (b-ter) H6: gambe di COMBO rotte il cui fill è appena stato confermato
    # dalla coda → si svolgono subito (mai una posizione nuda per un ciclo)
    n_unwound = unwind_incomplete_combos(
        db=db, market=market, rows_by_event=rows_by_event, params=params, now=now,
        open_rows=risk_ctx.get("open") if not risk_ctx.get("unavailable") else None)

    # (c) richieste della UI — SEMPRE
    n_requests = process_requests(db=db, market=market, rows_by_event=rows_by_event,
                                  params=params, now=now, risk_ctx=risk_ctx)

    # (c-bis) uscite automatiche — SEMPRE (posizioni già aperte), prima dei nuovi ingressi
    n_exits = process_exits(db=db, market=market, rows_by_event=rows_by_event,
                            params=params, now=now, opp_mod=opp_mod,
                            opps_state=opps_state,
                            # M1: le posizioni vive sono già state lette per il
                            # contesto di rischio: una SELECT, non tre
                            open_rows=risk_ctx.get("open")
                            if not risk_ctx.get("unavailable") else None)

    if status == "stopping":
        try:
            db.set_control(status="stopped", stopped_at=now.isoformat())
            _log(db, "stop", {})
        except Exception:  # noqa: BLE001
            pass
        status = "stopped"

    # (d) segnali automatici — SOLO se in esecuzione
    n_placed = n_signals = 0
    if status == "running":
        n_placed, n_signals = scan_and_place(db=db, market=market, engine=engine,
                                             rows=rows, params=params, mode=mode,
                                             now=now, risk_ctx=risk_ctx)

    running = status == "running"
    mods = _extra_mods(extra_mods)
    # (d-bis) ANOMALIE: cecchino a ogni ciclo sulle righe con quote cambiate
    anomalies = process_anomalies(
        db=db, market=market, rows=rows, params=params, model=opp_model, opp_mod=opp_mod,
        anomaly_mod=mods.get("anomaly"), mode=mode, now=now, state=opps_state,
        auto_trade=bool(params.get("auto_trade_anomalies")) and running,
        rows_by_event=rows_by_event, risk_ctx=risk_ctx)

    # (e) opportunità (modello + combo + anomalie + tennis; auto-trading per tipo)
    opps = process_opportunities(
        db=db, market=market, rows=rows, params=params, model=opp_model,
        opp_mod=opp_mod, mode=mode, now=now, state=opps_state,
        auto_trade=bool(params.get("auto_trade_opportunities")) and running,
        rows_by_event=rows_by_event, extra=mods,
        auto_trade_kinds={"combo": bool(params.get("auto_trade_combos")) and running,
                          "tennis": bool(params.get("auto_trade_tennis")) and running},
        risk_ctx=risk_ctx,
    )

    # (f) stats + heartbeat (gli aggregati del contesto di rischio si riusano se
    # dopo la loro lettura non è cambiato nulla: una sola SELECT per ciclo)
    changed = bool(n_requests or n_exits or n_placed or opps.get("traded")
                   or anomalies.get("traded") or risk_ctx.get("unavailable"))
    if not changed and risk_ctx.get("agg"):
        agg = risk_ctx["agg"]
    else:
        try:
            agg = db.aggregates()
        except Exception as ex:  # noqa: BLE001
            logger.warning("[safe.bot] aggregates KO: %s", str(ex)[:160])
            agg = {}
    rp = RK.risk_params(params)
    counts = dict((opps_state if opps_state is not None else _OPPS_STATE).get("counts") or {})
    # C-01: TUTTI i numeri della giornata vengono dagli stessi aggregati, con la
    # GIORNATA = giorno di PIAZZAMENTO (Europe/Rome). Un numero solo per giorno.
    stats = {
        "events_total": len(rows),
        "signals_active": n_signals,
        "trades_open": int(agg.get("open_count", 0)),
        "open_liability": round(float(agg.get("open_liability", 0.0)), 2),
        "reconciling_liability": round(float(agg.get("reconciling_liability", 0.0) or 0.0), 2),
        "realized_today": round(float(agg.get("realized_today", 0.0)), 2),
        "realized_total": round(float(agg.get("realized_total", 0.0)), 2),
        "won_today": int(agg.get("won_today", 0) or 0),
        "lost_today": int(agg.get("lost_today", 0) or 0),
        "legs_today": int(agg.get("legs_today", 0) or 0),
        "events_today": int(agg.get("events_today", 0) or 0),
        "feed_blind": n_blind,
        "last_cycle": now.isoformat(),
        "risk": {"daily_liability": round(float(agg.get("day_liability", 0.0) or 0.0), 2),
                 "daily_cap": float(rp.get("daily_liability_cap") or 0.0),
                 "reconciling_liability": round(float(agg.get("reconciling_liability", 0.0) or 0.0), 2),
                 "loss_stop_active": RK.loss_stop_active(agg.get("realized_today", 0.0), params),
                 "daily_loss_stop": float(rp.get("daily_loss_stop") or 0.0)},
        "opps": {"model": int(counts.get("model", 0)), "anomaly": int(counts.get("anomaly", 0)),
                 "combo": int(counts.get("combo", 0)), "tennis": int(counts.get("tennis", 0))},
        # H-15: i parametri REALMENTE in uso (clampati), per la scheda parametri
        "params_effective": params_effective(params),
    }
    try:
        db.set_control(stats=stats, heartbeat_at=now.isoformat())
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] set_control KO: %s", str(ex)[:160])
    return {"status": status, "placed": n_placed, "settled": n_settled,
            "requests": n_requests, "polled": n_polled, "reconciled": n_reconciled,
            "exits": n_exits, "signals": n_signals, "opportunities": opps,
            "anomalies": anomalies, "blind": n_blind, "unwound": n_unwound,
            "stats": stats}


def _log(db, kind: str, payload: dict[str, Any]) -> None:
    try:
        db.log(kind, payload)
    except Exception:  # noqa: BLE001 — il log non ferma mai il trading
        pass


# ---------------------------------------------------------------------------
# Loop principale
# ---------------------------------------------------------------------------
def params_signature(params: dict[str, Any]) -> str:
    """Firma dei parametri EFFETTIVI: se cambia, i modelli si ricostruiscono a
    caldo (M-30: "Salva" non aggiornava OpportunityModel/TennisOpportunityModel,
    servivano un riavvio e nessuno lo sapeva)."""
    return _hash(params)


def _build_engine(engine_mod: Any, params: dict) -> Any:
    if engine_mod is None:
        return None
    try:
        return engine_mod.SafeEngine(params)
    except Exception as ex:  # noqa: BLE001
        logger.error("[safe.bot] costruzione motore KO: %s", str(ex)[:200])
        return None


def _build_model(opp_mod: Any, params: dict) -> Any:
    if opp_mod is None:
        return None
    try:
        return opp_mod.OpportunityModel(params)
    except Exception as ex:  # noqa: BLE001
        logger.error("[safe.bot] costruzione modello opportunita' KO: %s", str(ex)[:200])
        return None


def main() -> None:
    from Betfair.stream.single_instance import acquire_single_instance_lock

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    lock = acquire_single_instance_lock(_SINGLE_INSTANCE_PORT, "safe-bot")
    logger.info("[safe.bot] servizio avviato (lock %s)", _SINGLE_INSTANCE_PORT)
    engine_mod = _import_engine_module()
    opp_mod = _import_opportunity_module()
    engine = model = None
    params_sig: Optional[str] = None
    try:
        while True:
            interval = 2.0
            try:
                ctrl = _real_db.read_control() or {}
                params = resolve_params(ctrl.get("params"), engine_mod=engine_mod)
                interval = float(params.get("poll_interval_s") or 2.0)
                # M-30: "Salva" dei parametri → i MODELLI si ricostruiscono a
                # caldo (prima OpportunityModel/TennisOpportunityModel nascevano
                # una volta e ignoravano ogni modifica fino al riavvio).
                sig = params_signature(params)
                if params_sig is not None and sig != params_sig:
                    logger.info("[safe.bot] parametri cambiati: ricostruisco i modelli")
                    engine = model = None
                    _EXIT_MODEL["model"] = None
                    _OPPS_STATE.pop("tennis_model", None)
                    _OPPS_STATE.pop("tennis_mod", None)
                params_sig = sig
                if engine is None:
                    engine = _build_engine(engine_mod, params)
                elif hasattr(engine, "update_params"):
                    try:
                        engine.update_params(params)
                    except Exception as ex:  # noqa: BLE001
                        logger.warning("[safe.bot] update_params KO: %s", str(ex)[:160])
                if model is None:
                    model = _build_model(opp_mod, params)
                res = run_once(engine=engine, opp_model=model, opp_mod=opp_mod,
                               engine_mod=engine_mod)
                if res.get("placed") or res.get("settled") or res.get("requests") \
                        or res.get("exits"):
                    logger.info("[safe.bot] ciclo: %s",
                                {k: res[k] for k in ("placed", "settled", "requests", "exits")
                                 if k in res})
            except KeyboardInterrupt:
                logger.info("[safe.bot] interrotto")
                break
            except Exception as ex:  # noqa: BLE001 — il loop non deve morire
                logger.exception("[safe.bot] errore di ciclo: %s", str(ex)[:200])
                try:
                    _real_db.log("error", {"reason": "cycle_exception", "err": str(ex)[:200]})
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(max(interval, 1.0))
    finally:
        try:
            lock.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
