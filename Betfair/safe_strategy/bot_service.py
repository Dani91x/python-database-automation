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
    # CERT. 14/09 — MODALITA' PER STRATEGIA. Serve a certificare una strategia
    # sul campo senza trascinare a soldi veri quelle ancora in verifica:
    # l'interruttore del servizio e' uno solo, e senza questa mappa accendere il
    # tennis accendeva anche le tre varianti del calcio.
    # Mappa PARZIALE: una strategia non nominata eredita il ``mode`` del control,
    # quindi una configurazione vecchia si comporta esattamente come prima.
    # REGOLA NON NEGOZIABILE: il ``mode`` del control e' un TETTO, non un default
    # scavalcabile. Con il servizio in PAPER nessuna mappa puo' far uscire soldi
    # veri — la conferma LIVE resta l'unico ingresso al denaro vero, e un
    # parametro non deve poterla aggirare.
    "strategy_modes": {},
    # CERT. 14/09 — CANCELLETTO DI APPROVAZIONE SULLE CHIUSURE DEL TENNIS.
    # Ordine dell'utente: le aperture restano automatiche, le chiusure gliele
    # si PROPONE e le approva lui dalla Control Room.
    # Nasce SPENTO. Non e' un'attenuazione dell'ordine: acceso, ogni chiusura
    # del tennis — compresa l'uscita OBBLIGATORIA del manuale — resta ferma
    # finche' un essere umano non la promuove. Accenderlo prima che la pagina
    # sappia mostrare le proposte vorrebbe dire fermare le chiusure senza che
    # nessuno le veda: si accende quando c'e' chi guarda.
    "tennis_exit_approval": False,
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
    # Omega (L-audit "chiavi Omega usate dal codice condiviso" + M-31).
    "execution_mode": "auto",           # 'auto' = coda quando possibile, 'rest' = solo REST
    "omega_live_via_flumine": True,     # nome della chiave del gate condiviso
    "paper_fill_ttl_s": 45,             # quasi-FOK del paper: poi cancel del residuo
    "live_fill_deadline_s": 20,         # oltre: riconciliazione REST / revoca
    # Minimo di GIURISDIZIONE, valore INFORMATIVO (CERT. 13/09).
    # Non e' piu' una soglia di RIFIUTO: sotto questa cifra l'ordine non viene
    # scartato, si usa il place-and-trim (parcheggio -> taglio -> riprezzo), che
    # scende fino a 0,01 EUR. Serve alla UI per dire all'utente da dove in giu'
    # il servizio cambia tecnica. La soglia che il codice usa DAVVERO per
    # scegliere il percorso e' ``execution._min_size_live(side)``, che conosce il
    # lato (il minimo .it e' BACK 2,00 / LAY 0,50) ed e' un FATTO dell'exchange,
    # non una preferenza. L'unico pavimento vero e' ``execution.ABS_MIN_SIZE``.
    "min_stake": 2.0,
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
    # ``strategy_modes``: mappa parziale strategia -> "paper"/"live". Le chiavi
    # ignote e i valori non validi cadono (prudenza), la mappa VUOTA e' legittima
    # e vuol dire "vale il ``mode`` del control per tutti", cioe' il comportamento
    # di sempre.
    out["strategy_modes"] = normalize_strategy_modes(out.get("strategy_modes"))
    out["tennis_exit_approval"] = bool(out.get("tennis_exit_approval"))
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


def normalize_strategy_modes(raw: Any) -> dict[str, str]:
    """Mappa PARZIALE strategia -> ``"paper"`` | ``"live"``, in ordine stabile.

    Si scarta tutto quello che non si capisce: chiave non fra ``_STRATEGIES``,
    valore diverso da paper/live. Una configurazione sporca non deve poter
    spostare soldi, e il silenzio qui e' prudente per costruzione — una chiave
    caduta significa "eredita il ``mode`` del control", che in paper vuol dire
    paper.

    La mappa **vuota** e' legittima e vuol dire "vale il ``mode`` del control per
    tutti": e' il comportamento di sempre, ed e' il default.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k in _STRATEGIES:
        v = str(raw.get(k) or "").lower()
        if v in ("paper", "live"):
            out[k] = v
    return out


def modalita_di_strategia(strategy: str, mode: str, params: dict[str, Any]) -> str:
    """Modalita' con cui la strategia ``strategy`` deve PIAZZARE in questo ciclo.

    DUE REGOLE, e insieme non lasciano scoperta nessuna direzione:

    1. Il ``mode`` del servizio e' un TETTO: in paper si resta in paper, sempre.
       Cosi' la conferma LIVE resta l'unico ingresso ai soldi veri e nessun
       parametro salvato settimane prima puo' aggirarla.
    2. **I SOLDI VERI SI RAGGIUNGONO SOLO SCRIVENDOLO, MAI EREDITANDOLO.** Con
       il servizio in LIVE, una voce assente o illeggibile vale **paper**.

    La seconda regola e' arrivata dopo la prima, e corregge un errore vero:
    avevo scritto che "la direzione dell'errore e' sempre verso la prudenza",
    ma lo era solo a servizio in paper. Per mandare in live UNA strategia il
    servizio DEVE essere armato in live — ed e' esattamente li' che una mappa
    incompleta o sporca avrebbe mandato a spendere soldi veri le strategie che
    nessuno aveva nominato. La prudenza non puo' dipendere dallo stato in cui
    ci si trova: o vale sempre, o non e' prudenza.

    Costo accettato: una configurazione vecchia che arma il servizio in live
    senza nominare niente non manda piu' niente in live. E' un'aspettativa che
    conviene rompere una volta, rumorosamente (vedi ``_avvisa_ereditarieta``),
    invece di onorarla in silenzio con i soldi di qualcun altro.
    """
    if str(mode).lower() != "live":
        return "paper"
    scelto = str((params.get("strategy_modes") or {}).get(str(strategy)) or "").lower()
    return "live" if scelto == "live" else "paper"


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
    # CERT. 14/09 — la mappa delle modalita' va DICHIARATA alla UI: e' quella
    # che decide da quale strategia escono soldi veri, ed e' l'unica cosa che
    # non si puo' lasciare dedurre da chi guarda lo schermo.
    out["strategy_modes"] = dict(resolved.get("strategy_modes") or {})
    # se il cancelletto e' spento la pagina deve dirlo: altrimenti l'utente
    # crede di avere il controllo delle chiusure e non ce l'ha.
    out["tennis_exit_approval"] = bool(resolved.get("tennis_exit_approval"))
    # CERT. 14/09 — LO STAKE DELLE 4 STRATEGIE DEL MANUALE, che qui non c'era.
    # `stake.backSize` e' l'importo con cui entrano TENNIS e PUNTA (che puntano)
    # e `stake.laySize` quello di BASE ed ESATTO (che bancano): e' l'importo che
    # muove i soldi veri, e non compariva fra i valori effettivi. Quindi la
    # pagina non poteva dire con che stake sta operando il bot — e un valore
    # scritto male ripiega in silenzio su 2,00 € senza che nessuno lo veda.
    # E' l'opposto della "manopola inerte": un valore che conta ed e' invisibile.
    # NON confondere con `risk.model_stake`, che e' di un ALTRO motore (le
    # opportunita' di modello, `strategy='model'`).
    out["stake"] = dict(resolved.get("stake") or {})
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
def _riserva_mai_piazzata(tr: dict[str, Any]) -> bool:
    """Riga ancora nella fase di RISERVA e senza alcun segno di esecuzione.

    ``phase == 'reserved'`` e' scritto da ``_reserve_row`` e viene sostituito
    appena il place produce un esito (``meta.fill``) o entra in coda
    (``flumine_client_ref``). Se e' ancora li' e non c'e' nient'altro, l'ordine
    non e' mai partito."""
    meta = tr.get("meta") or {}
    if str(meta.get("phase") or "") != "reserved":
        return False
    return not (meta.get("fill") or tr.get("bet_id")
                or meta.get("flumine_client_ref") or meta.get("flumine_request_id"))


def reconcile_pending(*, market, db, now: datetime) -> int:
    try:
        pendings = list(db.list_trades("pending") or [])
    except Exception as ex:  # noqa: BLE001
        _log(db, "reconcile_error", {"reason": "list_failed", "err": str(ex)[:160]})
        _PENDING_CICLO.clear()
        return 0
    # le righe 'pending' di QUESTO giro restano a disposizione di chi ne ha
    # bisogno piu' avanti nello stesso ciclo (la guardia "un solo lato ESATTO"),
    # invece di rileggere la stessa identica query pochi millisecondi dopo:
    # regola del progetto, nessuna lettura duplicata per giro.
    _PENDING_CICLO["ts"] = now.timestamp()
    _PENDING_CICLO["rows"] = pendings
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
            elif _riserva_mai_piazzata(tr):
                # CERT. 13/09 — riserva PAPER rimasta a meta': la riga esiste
                # (``phase='reserved'``) ma non c'e' nessun marcatore di
                # esecuzione — ne' ``meta.fill``, ne' ``bet_id``, ne' marcatori
                # di coda. Vuol dire che il processo e' morto FRA l'insert e il
                # place: nessun ordine, nemmeno simulato, e' mai partito.
                # Confermarla "al prezzo della riserva" creava una posizione
                # paper INVENTATA, che il live non avrebbe mai avuto — e i
                # numeri del paper non possono valere come prova se contengono
                # posizioni che non sono mai esistite. In live lo stesso caso
                # finisce in 'free'/'error': stessa severita'.
                _terminal_error(db, tr, reason="reconcile_paper_mai_piazzata", now=now,
                                extra={"how": "paper"})
                _log(db, "reconciled_error", {"trade_id": tr.get("id"),
                                              "event_id": tr.get("event_id"),
                                              "reason": "reconcile_paper_mai_piazzata",
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
                why = str(d.get("reason") or "reconcile_orphan_old")
                _terminal_error(db, tr, reason=why, now=now,
                                extra={"bet_id_seen": tr.get("bet_id")} if tr.get("bet_id") else None)
                _log(db, "reconciled_error", {"trade_id": tr.get("id"),
                                              "event_id": tr.get("event_id"),
                                              "reason": why})
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
    remaining = float(st.get("size_remaining") or 0.0)
    if matched > 0 and remaining <= 0:
        return {"action": "confirm", "price": float(st.get("avg_price_matched") or tr.get("price") or 0.0),
                "size": matched, "bet_id": str(bet_id)}
    if matched <= 0 and remaining <= 0:
        # 12/09: ordine CONOSCIUTO da Betfair ma MORTO senza fill (FOK ucciso,
        # LAPSED/CANCELLED): prima tornava 'keep' e la riga restava 'pending'
        # per sempre (esposizione contata, segnale bloccato). Esito CERTO
        # negativo -> 'error' terminale con la traccia del bet_id.
        return {"action": "error", "reason": "reconcile_ordine_senza_fill"}
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
    # H-19 (12/09): UNA ``listMarketBook`` per ciclo per TUTTI i mercati da
    # regolare (``read_markets``, blocchi da 40), non una per posizione. Il
    # feed decide QUANDO vale la pena chiamare Betfair; la cadenza per mercato
    # (10 s) resta; il budget per ciclo conta le CHIAMATE, non i mercati.
    todo: list[dict] = []
    for tr in parents:
        row = rows_by_event.get(str(tr.get("event_id")))
        if not _settlement_needs_rest(tr, row, now_ts):
            continue
        todo.append(tr)
    snaps = _read_markets_batch(market, todo, now_ts)
    for tr in todo:
        try:
            mid = str(tr.get("market_id") or "")
            if mid not in snaps:
                continue           # non letto in questo ciclo (cadenza/budget/rete)
            snap = snaps[mid]
            if snap is None:
                _market_missing(db, tr, now_ts)
                continue
            _market_seen(mid)
            if not snap.closed:
                continue
            comm = _commission_rate(tr.get("commission"), fallback_commission)
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
                comm = _commission_rate(c.get("commission"), fallback_commission)
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
    return market.read_market(_cs_of(tr))


def _cs_of(tr: dict[str, Any]):
    return _real_market.CorrectScoreMarket(
        market_id=str(tr.get("market_id")), event_id=str(tr.get("event_id")),
        event_name=tr.get("event_name") or "", market_start_time=None, runner_names={},
    )


def _read_markets_batch(market, trades: list[dict[str, Any]],
                        now_ts: float) -> dict[str, Any]:
    """{market_id: MarketSnapshot | None} dei mercati delle posizioni ``trades``
    che passano la cadenza REST (``REST_MIN_INTERVAL_S`` per mercato).

    Con ``market.read_markets`` (omega_market): UNA ``listMarketBook`` per
    blocco di 40 mercati e UNA unita' di budget per blocco. Un mercato assente
    dalla risposta (blocco KO di rete) NON compare nel risultato: non e' un
    mercato sparito, si rilegge al ciclo dopo. Senza ``read_markets`` (fake o
    client vecchio): una lettura per mercato dentro il budget di ``rest_gate``.
    Le eccezioni di una singola lettura restano fuori dal risultato."""
    out: dict[str, Any] = {}
    if not trades:
        return out
    by_mid: dict[str, dict[str, Any]] = {}
    for tr in trades:
        mid = str(tr.get("market_id") or "")
        if mid and mid not in by_mid:
            by_mid[mid] = tr
    batch = getattr(market, "read_markets", None)
    if not callable(batch):
        for mid, tr in by_mid.items():
            if not rest_gate(mid, now_ts):
                continue
            try:
                out[mid] = _read_market(market, tr)
            except Exception as ex:  # noqa: BLE001 — lettura KO: non e' un mercato sparito
                logger.warning("[safe.bot] read_market KO %s: %s", mid, str(ex)[:120])
        return out
    st = _REST_STATE
    if float(st.get("cycle_ts") or 0.0) != now_ts:
        st["cycle_ts"] = now_ts
        st["used"] = 0
    last: dict = st.setdefault("last", {})
    due = [mid for mid in by_mid
           if last.get(mid) is None or now_ts - float(last[mid]) >= REST_MIN_INTERVAL_S]
    if not due:
        return out
    for i in range(0, len(due), 40):
        if int(st.get("used") or 0) >= REST_BUDGET_PER_CYCLE:
            break
        chunk = due[i:i + 40]
        st["used"] = int(st.get("used") or 0) + 1
        for mid in chunk:
            last[mid] = now_ts
        try:
            res = batch([_cs_of(by_mid[m]) for m in chunk]) or {}
        except Exception as ex:  # noqa: BLE001
            logger.warning("[safe.bot] read_markets KO: %s", str(ex)[:120])
            continue
        for mid in chunk:
            if mid in res:
                out[mid] = res[mid]
    return out


def _commission_rate(value: Any, fallback: float) -> float:
    """Aliquota della POSIZIONE come FRAZIONE (0,05). La colonna ``commission``
    porta la frazione (``commission_pct``/100); un valore > 1 e' una percentuale
    scritta per errore (5 = 5 %) e NON deve diventare 100 % (12/09: prima
    ``_commission_of`` la clampava a 1,0 e il netto delle uscite andava a zero)."""
    if value is None:
        c = _f(fallback, 0.05)
    else:
        c = _f(value, fallback)
        if c > 1.0:
            c = c / 100.0
    return min(1.0, max(0.0, c))


# ---------------------------------------------------------------------------
# (c) richieste della UI — SEMPRE, anche a bot fermo
# ---------------------------------------------------------------------------
# Eta' massima di una richiesta manuale ancora eseguibile. Oltre, si scarta con
# un motivo parlante invece di piazzare in ritardo su un mercato cambiato.
_REQUEST_MAX_AGE_S = 120.0


def _request_age_s(row: dict[str, Any], now: datetime) -> Optional[float]:
    """Secondi trascorsi dalla creazione della richiesta; None se non databile
    (una richiesta senza data NON viene scartata: meglio eseguirla che perderla
    per un campo mancante)."""
    raw = row.get("created_at") or row.get("requested_at") or row.get("ts")
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (now - ts).total_seconds())


#: I ``kind`` ammessi in CORSIA PREFERENZIALE.
#:
#: Solo ``cashout``: e' l'unico su cui il trader ha appena cliccato per
#: bloccare un profitto o una perdita, riduce l'esposizione e non ha bisogno
#: del contesto di rischio (i cap valgono sulle APERTURE).
#:
#: ``cancel`` NON c'e' (review 15/09): annulla una RISERVA, cioe' una riga il
#: cui ordine potrebbe essere gia' partito, e la sua difesa si regge su campi
#: (``bet_id``, marker flumine) che scrivono le fasi di riconciliazione. Non
#: e' urgente come una chiusura e sta benissimo nella passata completa, dove
#: quelle fasi hanno gia' detto la verita' sulla riga.
CHIUSURE = ("cashout",)


def process_requests(*, db, market, rows_by_event: dict[str, dict],
                     params: dict[str, Any], now: datetime,
                     risk_ctx: Optional[dict] = None,
                     control_mode: str = "", degradato: bool = False,
                     solo_chiusure: bool = False) -> int:
    """Esegue la coda delle richieste della UI.

    ``solo_chiusure`` = CORSIA PREFERENZIALE (cert. 14/09). Misurato dal vivo
    sulla richiesta #10: fra il clic del trader e l'ordine partito passavano
    **4,2 secondi nostri**, spesi ad aspettare che il ciclo arrivasse al punto
    (c) dopo coda flumine, riconciliazione, settlement, contesto di rischio,
    cecita' del feed e combo rotte — tutte fasi che possono chiamare Betfair.
    Con questa modalita' le CHIUSURE si eseguono prima di tutto il resto.

    Le APERTURE restano dove sono, e non e' una svista: un piazzamento ha
    bisogno del contesto di rischio condiviso del ciclo, perche' due aperture
    nello stesso giro devono vedersi a vicenda per rispettare i cap. Una
    chiusura no: non esiste un cap che una chiusura possa sfondare.
    """
    stale = getattr(db, "fail_stale_processing", None)
    if callable(stale) and not solo_chiusure:
        # una sola volta per ciclo: la passata veloce non ripaga la query
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
        kind = str(r.get("kind") or "")
        # La passata veloce lascia le altre richieste ESATTAMENTE come sono:
        # niente 'processing', o la passata completa non le vedrebbe piu' e
        # resterebbero appese fino allo scadere del timeout.
        if solo_chiusure and kind not in CHIUSURE:
            continue
        try:
            db.set_request_status(r["id"], "processing")
        except Exception:  # noqa: BLE001
            continue
        payload = r.get("payload") or {}
        # CERT. 13/09 — una richiesta VECCHIA non si esegue: si scarta.
        # ``fail_stale_processing`` copriva solo lo stato 'processing'; una
        # 'pending' non scadeva MAI, quindi una richiesta creata ore prima (a
        # servizio spento) veniva eseguita al primo avvio utile, su quote di
        # un'altra partita e magari in una modalita' diversa da quella attiva.
        eta = _request_age_s(r, now)
        if eta is not None and eta > _REQUEST_MAX_AGE_S:
            db.set_request_status(r["id"], "error", {
                "message": f"rifiutato: richiesta di {int(eta // 60)} minuti fa, "
                           f"troppo vecchia per essere eseguita adesso",
                "reason": "richiesta_scaduta", "age_s": round(eta, 1)})
            _log(db, "skip", {"reason": "richiesta_scaduta", "origin": "manual",
                              "kind": kind, "age_s": round(eta, 1)})
            n += 1
            continue
        try:
            if kind == "place" and degradato:
                # CERT. 13/09 (review) — la modalita' con cui validare la
                # richiesta arriverebbe dalla CACHE, e la cache puo' essere
                # vecchia: l'utente potrebbe aver accodato un LIVE e poi essere
                # tornato in PAPER mentre il DB smetteva di rispondere. Un
                # piazzamento si rimanda; una CHIUSURA no, quella deve passare
                # sempre (mai una posizione senza via d'uscita).
                res = {"rejected": "stato del servizio non verificabile",
                       "message": "rifiutato: il servizio non riesce a leggere il "
                                  "proprio stato, riprova fra poco"}
                _log(db, "skip", {"reason": "control_non_verificabile", "origin": "manual"})
            elif kind == "place":
                res = _request_place(db=db, market=market, rows_by_event=rows_by_event,
                                     payload=payload, params=params, now=now,
                                     risk_ctx=risk_ctx, control_mode=control_mode)
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
    'error' guasto.

    ⚠️ 15/09 — `attendi` e' l'unico esito che NON chiude la richiesta: la
    riporta in coda perche' la condizione si risolve da sola al giro dopo
    (tipicamente una riserva ancora da riconciliare). Chiuderla come rifiuto
    buttava via l'approvazione del trader con un motivo che poteva essere
    falso."""
    if res.get("attendi"):
        return "pending"
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
                   now: datetime, risk_ctx: Optional[dict] = None,
                   control_mode: str = "") -> dict:
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
    # CERT. 13/09 — SEPARAZIONE NETTA PAPER/LIVE: la modalita' del payload e' una
    # ASSERZIONE DEL CLIENT, non un comando. L'autorita' e' ``control.mode``.
    # Difetto chiuso qui: l'utente accodava "Piazza (LIVE)" e subito dopo toccava
    # PAPER sul toggle; il bot leggeva la richiesta al ciclo successivo e
    # piazzava SOLDI VERI mentre lo schermo diceva "nessun denaro reale".
    # Le richieste ``pending`` non avevano nemmeno una scadenza: una richiesta
    # LIVE creata ore prima, a servizio spento, veniva eseguita all'avvio
    # successivo qualunque fosse la modalita' corrente.
    if control_mode and mode != str(control_mode).lower():
        _log(db, "skip", {"event_id": event_id, "origin": "manual",
                          "reason": "modalita_non_corrispondente",
                          "richiesta": mode, "attiva": str(control_mode).lower()})
        return {"rejected": f"modalita' non corrispondente: richiesta {mode}, "
                            f"attiva {str(control_mode).lower()}",
                "message": f"rifiutato: la richiesta era in {mode.upper()} ma il "
                           f"servizio e' in {str(control_mode).upper()}"}
    try:
        price = float(payload.get("price"))
        size = float(payload.get("size"))
    except (TypeError, ValueError):
        return {"error": "price/size non numerici"}
    if price <= 1.0 or size <= 0:
        return {"error": "price/size fuori range"}
    # CERTIFICAZIONE 12/09 — FRESCHEZZA DEL FEED anche sul MANUALE.
    # L'automatico la controlla (``_row_is_fresh``), il manuale no: una richiesta
    # accodata con lo scanner fermo veniva eseguita su quote vecchie (in paper
    # riempiva, in live il FOK sarebbe morto a vuoto). La UI oggi spegne i
    # bottoni, ma il DB-as-bus accetta richieste da qualunque altra via: la
    # barriera deve stare QUI, non solo a schermo.
    row_feed = (rows_by_event or {}).get(event_id)
    if not _row_is_fresh(row_feed, now.timestamp(), _scanner_ts(db, now.timestamp())):
        motivo = _stale_reason(row_feed)
        _log(db, "skip", {"event_id": event_id, "reason": motivo, "origin": "manual",
                          "market_id": market_id, "selection_id": selection_id})
        return {"error": motivo}

    # idempotenza del MANUALE: la UI può reinviare la stessa richiesta (retry,
    # doppio click): con la stessa chiave non si piazza due volte.
    idem = str(payload.get("idempotency_key") or "").strip() or None
    if idem:
        dup = _trade_by_idempotency_key(db, idem, mode=mode)
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
    risk_ctx = risk_ctx if risk_ctx is not None else build_risk_ctx(db, now, params, mode=mode)
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
    # la ladder del book REST e' quella del LAY: per un BACK non vale (12/09:
    # prima veniva passata a prescindere dal lato e il paper camminava livelli
    # del lato sbagliato); il livello del feed lo costruisce _execute.
    out = _execute(db=db, market=market, trade_id=trade_id, row=row, params=params,
                   now=now, best_size=best_size,
                   ladder=((prices or {}).get("lay_ladder") or ()) if side == "lay" else (),
                   feed_prices=prices)
    if out.status == "error":
        return {"error": "non_eseguito", "detail": out.fill_note, "trade_id": trade_id}
    return {"ok": True, "trade_id": trade_id, "status": out.status,
            "price": out.price, "size": out.size,
            "pending_fill": out.status == "pending"}


def _traded_keys(db, mode: Optional[str] = None) -> set[tuple[str, str]]:
    """(event_id, signal_key) gia' presi dall'automatico NELLA MODALITA' data.

    CERT. 13/09 — senza il filtro, il passaggio da paper a live era una trappola
    silenziosa: tutti i segnali gia' "tradati" in prova risultavano occupati e
    il bot con i soldi veri non entrava su NIENTE di quello che aveva appena
    collaudato. L'accessor vecchio (senza parametro) viene comunque accettato:
    si degrada al comportamento di prima invece di rompere il bot."""
    fn = getattr(db, "traded_signal_keys", None)
    if not callable(fn):
        return set()
    try:
        return set(fn(mode=mode) or set())
    except TypeError:      # accessor senza il parametro (fake dei test, versioni vecchie)
        return set(fn() or set())


def _trade_by_idempotency_key(db, key: str,
                              mode: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Trade NON in errore con ``meta.idempotency_key == key`` (accessor del db
    se c'è, altrimenti scansione delle righe).

    Il dedupe e' PER MODALITA' (13/09): la stessa chiave usata in paper non deve
    far rispondere "gia' fatto" a un clic in LIVE (la UI direbbe "eseguito" e
    non ci sarebbe nessun ordine vero)."""
    m = str(mode or "").lower() or None
    fn = getattr(db, "trade_by_idempotency_key", None)
    if callable(fn):
        try:
            return fn(key, mode=m)
        except TypeError:      # accessor vecchio senza il parametro
            found = fn(key)
            if found is None or m is None:
                return found
            return found if str(found.get("mode") or "live").lower() == m else None
    for t in db.list_trades() or []:
        if str(t.get("status")) == "error":
            continue
        if m is not None and str(t.get("mode") or "live").lower() != m:
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
    # 12/09: lo stato della riga si dichiara PRIMA di provare (prima una
    # 'hedged' o una riserva 'pending' finivano in 'error' generico
    # "trade_non_aperto:<stato>" senza spiegazione per l'utente).
    status = str(trade.get("status") or "")
    if status == "pending":
        # ⚠️ REVIEW 15/09 — QUESTO RIFIUTO ERA TERMINALE, e con un motivo che
        # poteva essere FALSO. Una riga 'pending' non e' per forza «non
        # abbinata»: puo' essere appena stata abbinata e non ancora
        # riconciliata. Chiudere la richiesta come 'rejected' buttava via
        # l'approvazione del trader, che doveva accorgersene e ricliccare.
        #
        # Una riserva si risolve da sola al giro dopo: la richiesta RESTA in
        # attesa e ci riprova, invece di morire. Se e' davvero vecchia ci
        # pensa il controllo di scadenza gia' in testa a `process_requests`.
        return {"attendi": "riserva non ancora risolta", "trade_id": int(tid),
                "message": "in attesa: l'ordine di apertura non e' ancora "
                           "risolto, la chiusura parte appena lo e'"}
    if status != "open":
        why = {"hedged": "posizione gia' coperta per intero: nulla da chiudere",
               }.get(status, f"la riga non e' una posizione aperta (stato {status})")
        return {"rejected": f"stato {status}", "trade_id": int(tid),
                "message": f"rifiutato: {why}"}
    amount = payload.get("amount")
    fraction = payload.get("fraction", 1.0)
    # 12/09: importo/frazione VALIDATI qui (la UI puo' mandare 0, negativi o
    # testo): frazione in (0, 1], importo > 0 — mai una chiusura "vuota" o
    # con segno sbagliato passata alla matematica del green-up.
    try:
        fraction_f = float(fraction) if fraction is not None else 1.0
        amount_f = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        return {"rejected": "importo o frazione non numerici", "trade_id": int(tid),
                "message": "rifiutato: importo o frazione non numerici"}
    if not (0.0 < fraction_f <= 1.0) or fraction_f != fraction_f:
        return {"rejected": f"frazione fuori da (0,1]: {fraction}", "trade_id": int(tid),
                "message": "rifiutato: la frazione da chiudere deve essere fra 0 e 1"}
    if amount_f is not None and (amount_f <= 0.0 or amount_f != amount_f):
        return {"rejected": f"importo non valido: {amount}", "trade_id": int(tid),
                "message": "rifiutato: l'importo da chiudere deve essere positivo"}
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
                                                         _scanner_ts(db, now.timestamp()))
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
                        amount=amount_f, fraction=fraction_f,
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
_SCANNER_TS_CACHE: dict[str, Any] = {"cycle_ts": None, "value": None}


def _scanner_ts(db, cycle_ts: Optional[float] = None) -> Optional[float]:
    """Epoch dell'heartbeat dello scanner (None se non esposto/illeggibile).

    12/09 — MEMOIZZATO per ciclo (``cycle_ts`` = ``now.timestamp()``): lo stesso
    heartbeat serve a segnali, opportunita', combo, anomalie, uscite e richieste
    manuali. Senza memo erano una SELECT per PARTITA a ogni giro (2 s)."""
    if cycle_ts is not None and _SCANNER_TS_CACHE.get("cycle_ts") == cycle_ts:
        return _SCANNER_TS_CACHE.get("value")
    fn = getattr(db, "scanner_status", None)
    value: Optional[float] = None
    if callable(fn):
        try:
            row = fn()
        except Exception as ex:  # noqa: BLE001
            logger.debug("[safe.bot] scanner_status KO: %s", str(ex)[:120])
            row = None
        if isinstance(row, dict):
            value = XE.parse_ts(row.get("updated_at"))
    if cycle_ts is not None:
        _SCANNER_TS_CACHE["cycle_ts"] = cycle_ts
        _SCANNER_TS_CACHE["value"] = value
    return value


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
# cadenza dei ricontrolli in 'waiting_price' (solo feed, nessuna REST) e
# diradamento del log 'exit_wait' relativo (1, 2, 3, poi uno ogni 12 ~ 1/min)
WAITING_PRICE_RETRY_S = float(XE.RETRY_BACKOFF_S[0])
WAITING_PRICE_LOG_EVERY = 12
# CERTIFICAZIONE 12/09 — la CADENZA dell'attesa prezzo vive in memoria, non sul
# DB: ``last_wait_at``/``wait_attempts`` cambiano a OGNI giro, quindi scriverli
# nel meta faceva una lettura + una scrittura ogni 5 s per ogni posizione senza
# prezzo opposto, per sempre (su questo progetto l'esaurimento dell'IO Supabase
# e' gia' successo). Sul DB si scrive solo quando cambia qualcosa che l'utente
# deve vedere (primi tentativi, cambio di motivo/errore, o una volta ogni
# WAITING_PRICE_LOG_EVERY). Perso al riavvio: si riparte con un ricontrollo
# subito, che e' il comportamento prudente.
_EXIT_WAIT_AT: dict[int, float] = {}


def _exit_due(trade: dict[str, Any], now_ts: float,
              decision: Optional[XE.ExitDecision] = None) -> bool:
    """True se l'invio dell'uscita è dovuto ORA.

    Il backoff (``meta.exit.next_retry_at``) frena i RITENTATIVI della stessa
    decisione; una decisione URGENTE nuova (perdita, rosso, obbligo tennis) lo
    scavalca: aspettare 5 minuti per chiudere una posizione che sta perdendo
    non è un ritentativo, è un danno."""
    st = exit_state(trade)
    if decision is not None and decision.kind in URGENT_EXIT_KINDS:
        if str(st.get("kind") or "") not in URGENT_EXIT_KINDS:
            return True   # regola NUOVA e urgente: si invia subito
    nxt = XE.parse_ts(st.get("next_retry_at"))
    if nxt is None or now_ts >= nxt:
        return True
    # 12/09: 'waiting_price' (nessun prezzo opposto nel feed) NON e' un
    # fallimento dell'invio: ricontrollare costa una lettura del feed, non una
    # chiamata a Betfair. Un backoff fino a 300 s su una posizione che sta
    # PERDENDO era un danno: la cadenza e' il primo gradino (5 s), sempre.
    if str(st.get("state") or "") == "waiting_price":
        # cadenza dalla memoria di processo (niente scritture); il valore sul
        # meta resta come ripiego dopo un riavvio del servizio
        try:
            tid = int(trade.get("id"))
        except (TypeError, ValueError):
            tid = None
        last = _EXIT_WAIT_AT.get(tid) if tid is not None else None
        if last is None:
            last = XE.parse_ts(st.get("last_wait_at"))
        return last is None or now_ts - last >= WAITING_PRICE_RETRY_S
    return False


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
    scanner_ts = _scanner_ts(db, now_ts)
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
            # CERT. 13/09 — CECITA' PARZIALE: la riga c'e' ma il DATO che serve
            # a decidere no. ``XE.decide`` torna None sia quando "non c'e' nulla
            # da fare" sia quando il punteggio (calcio) o i game (tennis) non
            # sono nel payload: nel secondo caso NESSUNA regola gira — niente
            # uscita a tempo, niente uscita in perdita — e finora non compariva
            # nemmeno un log. Una posizione poteva andare a settlement con la
            # responsabilita' intera e nello storico non c'era traccia del
            # perche'. La guardia esistente (``note_feed_blind``) copriva solo
            # la riga ASSENTE dal feed, non la riga presente e muta.
            # una proposta viva su una condizione che NON REGGE PIU' e' una
            # bugia sotto gli occhi di chi deve decidere: decade, col motivo.
            # Va qui, nel ramo "nessuna uscita da fare": metterla dopo
            # `_pulisci_dato_mancante` la cancellerebbe a ogni ciclo proprio
            # mentre la condizione regge, cioe' ucciderebbe la proposta viva.
            _decadi_proposta(db, trade, meta, "la condizione di uscita non regge piu'")
            _nota_dato_mancante(db, trade, meta, payload, now, now_ts)
            return False
        _pulisci_dato_mancante(db, trade, meta)
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
    # CERT. 14/09 — CANCELLETTO DI APPROVAZIONE (SOLO TENNIS, SOLO CHIUSURE).
    # Qui l'uscita e' matura e passerebbe a mercato. Col cancelletto acceso si
    # PROPONE invece di eseguire, e non parte niente.
    # Il RESIDUO non ripassa di qui: l'utente ha gia' approvato QUELLA chiusura,
    # e il residuo la sta solo finendo — richiedere una seconda approvazione
    # lascerebbe mezza posizione scoperta in attesa di un clic.
    if (residual is None
            and bool(params.get("tennis_exit_approval"))
            and str(trade.get("strategy") or "") == "tennis"
            and _proponi_chiusura(db=db, trade=trade, meta=meta, decision=decision,
                                  prices=prices, payload=payload, params=params,
                                  row=row, now=now)):
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
            err = str(res.get("error") or "")
            if err in ("chiusura_in_corso", "posizione_gia_chiusa") or \
                    err.startswith("trade_non_aperto"):
                # 12/09: una gamba GIA' in chiusura (o coperta) non e' un
                # fallimento critico: la sua chiusura e' in volo o fatta.
                _log(db, "exit_wait", {"trade_id": leg.get("id"),
                                       "combo_id": (leg.get("meta") or {}).get("combo_id"),
                                       "wait": err, "kind": "mandatory",
                                       "reason": "combo_solidale"})
                continue
            _log(db, "exit_failed", {"reason": "combo_gamba_non_chiusa",
                                     "trade_id": leg.get("id"),
                                     "combo_id": (leg.get("meta") or {}).get("combo_id"),
                                     "err": err, "detail": res.get("detail"),
                                     "critical": True})
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
    fallback = min(1.0, max(0.0, _f(params.get("commission_pct"), 5.0) / 100.0))
    return _commission_rate(trade.get("commission"), fallback)


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
    # CERTIFICAZIONE 12/09 — MODELLO CIECO NEL RECUPERO.
    # Oltre il 90'+recupero i tassi residui tornano il pavimento e il book
    # dichiara P = 99,8% PIATTA fino al 120': non perche' l'esito sia certo,
    # ma perche' e' finita la tabella. Qui la P finisce anche SOTTO GLI OCCHI
    # dell'utente (meta.exit_hold.p_lose, KPI, tooltip della tabella): restituire
    # None fa ripiegare il chiamante sulla probabilita' IMPLICITA DEL MERCATO,
    # che nel recupero e' l'unica fonte onesta. La DECISIONE di uscire e' gia'
    # protetta a valle in exits.py: qui si protegge il NUMERO MOSTRATO.
    try:
        opp = opp_mod or _import_opportunity_module()
        if opp is not None and getattr(opp, "model_is_blind", None) is not None:
            if opp.model_is_blind(payload.get("minute")):
                return None
    except Exception:  # noqa: BLE001 — mai per un controllo di sicurezza
        pass
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
    # CERT. 13/09 — UN SOLO modello di probabilita' per il tennis.
    # Qui si chiamava ``estimate_holds(0, 0, 0, 0)``, che con zero game e zero
    # break legge "nessun break subito" e ALZA il prior di hold a 0,792 invece
    # di 0,75. Un hold piu' alto rende il break piu' decisivo e GONFIA la
    # P(vittoria) del leader. Il difetto era gia' stato corretto il 12/09 in
    # ``tennis_opportunity._holds`` ma non era stato riportato qui — e questa e'
    # la funzione che alimenta il gate a modello delle USCITE. Misurato su 1 set
    # + 4-2: 0,9311 qui contro 0,9038 del modello corretto, cioe' P(perdita)
    # 0,069 contro 0,096 con un tetto di rischio a 0,10: la stessa posizione
    # risultava "dentro il tetto" o "al limite" a seconda di quale delle due
    # funzioni la guardava. In piu' qui mancava il rischio di RITIRO, che nel
    # tennis e' l'unico modo di perdere tutto lo stake.
    # Si usa quindi il modello vero, con questo calcolo come ripiego.
    p = _p_tennis_dal_modello(payload, side)
    if p is not None:
        return p
    ha, hb = estimate_holds(0, 0, 0, 0)
    best_of = _best_of(payload, (s1, s2))
    # servizio ignoto: media fra "serve A" e "serve B"
    p = 0.5 * (p_match(sa, sb, ga, gb, True, ha, hb, best_of)
               + p_match(sa, sb, ga, gb, False, ha, hb, best_of))
    return round(min(1.0, max(0.0, float(p))), 4)


def _p_tennis_dal_modello(payload: dict[str, Any], side: str) -> Optional[float]:
    """P(vittoria) dal modello tennis del progetto (prior corretto + rischio di
    ritiro), o None se il modulo non e' disponibile o non sa rispondere."""
    mod = _import_optional("tennis_opportunity")
    if mod is None:
        return None
    try:
        modello = getattr(mod, "TennisOpportunityModel")()
        p = modello.p_win(payload, side)
    except Exception as ex:  # noqa: BLE001 — si ripiega sul calcolo locale
        logger.debug("[safe.bot] modello tennis non utilizzabile: %s", str(ex)[:120])
        return None
    if p is None:
        return None
    try:
        return round(min(1.0, max(0.0, float(p))), 4)
    except (TypeError, ValueError):
        return None


def _conti_di_chiusura(db, trade: dict[str, Any], prices: dict[str, Any],
                       params: dict[str, Any]) -> dict[str, Any]:
    """Quanto vale CHIUDERE adesso e quanto vale TENERE, al netto della
    commissione. Matematica pura dei soldi, estratta da ``_model_gate`` perche'
    la usa anche la PROPOSTA di chiusura: due copie della stessa formula sono
    due formule che prima o poi divergono, e qui divergerebbero sui numeri che
    l'utente guarda per decidere.

    - ``locked``: P&L bloccato se si chiude ORA (None = piano non calcolabile)
    - ``hold_profit``: P&L se si tiene e la posizione va a buon fine
    - ``loss_if_lose``: quanto si perde se va male (positivo)
    """
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
    return {
        "legs": legs,
        "locked": XE.net_of_commission(locked, comm),
        "hold_profit": float(XE.net_of_commission(exp_lose if is_lay else exp_win, comm) or 0.0),
        "loss_if_lose": max(0.0, -float(exp_win if is_lay else exp_lose)),
        "is_lay": is_lay,
    }


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
    conti = _conti_di_chiusura(db, trade, prices, params)
    legs = conti["legs"]
    is_lay = conti["is_lay"]
    locked = conti["locked"]
    hold_profit = conti["hold_profit"]
    loss_if_lose = conti["loss_if_lose"]
    p_sel, source = _p_selection_wins(db=db, trade=trade, payload=payload, prices=prices,
                                      meta=meta, params=params, now=now, opp_mod=opp_mod,
                                      opps_state=opps_state)
    p_lose = None if p_sel is None else round(p_sel if is_lay else 1.0 - p_sel, 4)
    action, why = XE.decide_time_exit(p_lose, locked, hold_profit, trade.get("size"), xp,
                                      loss_if_lose=loss_if_lose)
    # CERT. 14/09 — UN TAKE PROFIT DEVE PORTARE A CASA UN PROFITTO.
    # La decisione a modello confronta VALORI ATTESI, quindi poteva accettare
    # una chiusura con il bloccato NEGATIVO (se l'alternativa sembrava peggio).
    # Su un incasso volontario al game successivo non ha senso: se il P&L
    # bloccato non e' almeno ``tennis_take_profit_min_eur`` al netto della
    # commissione, non si incassa e si continua. Le uscite in PERDITA e quella
    # OBBLIGATORIA non passano di qui (non sono in PROFIT_KINDS) e restano
    # intoccate: lo stop loss non e' mai condizionato al profitto.
    if (action == "exit" and decision.kind == "profit"
            and str(trade.get("strategy") or "") == "tennis"):
        minimo = _f(xp.get("tennis_take_profit_min_eur"), 0.01)
        if locked is None or float(locked) < minimo - 1e-9:
            action = "hold"
            quanto = "un importo non calcolabile" if locked is None else XE._eur(locked)
            why = f"incasso rifiutato: bloccherebbe {quanto} invece di almeno {XE._eur(minimo)}"
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


# stessa cadenza dell'allarme di feed cieco: un log ogni 60 s per posizione
_DATO_MANCANTE_LOG: dict[int, float] = {}


def _dato_che_manca(trade: dict[str, Any], payload: Optional[dict[str, Any]]) -> Optional[str]:
    """Quale dato indispensabile alle uscite manca nel payload, o None.

    Calcio: senza punteggio non gira nessuna regola (perdita, profitto, tempo).
    Tennis: senza set/game non gira l'uscita obbligatoria."""
    if not isinstance(payload, dict):
        return "riga_senza_payload"
    sport = str(trade.get("sport") or "calcio")
    if sport == "tennis":
        if not isinstance(payload.get("sets"), dict) or not isinstance(payload.get("games"), dict):
            return "punteggio_tennis_assente"
        return None
    sh, sa = payload.get("score_home"), payload.get("score_away")
    if isinstance(sh, bool) or isinstance(sa, bool)             or not isinstance(sh, (int, float)) or not isinstance(sa, (int, float)):
        return "punteggio_assente"
    if not isinstance(payload.get("minute"), (int, float)) or isinstance(payload.get("minute"), bool):
        return "minuto_assente"
    return None


def _nota_dato_mancante(db, trade: dict[str, Any], meta: dict[str, Any],
                        payload: Optional[dict[str, Any]], now: datetime, now_ts: float) -> None:
    """Segnala che la posizione e' viva ma il feed non porta il dato per decidere."""
    # CERT. 13/09 (review) — le righe PRE-KO non hanno ne' punteggio ne' minuto
    # PER NATURA (il feed pubblica anche gli eventi non iniziati, ramo O/U di
    # Mike). Allarmare su quelle sarebbe un allarme critico continuo per un dato
    # che non deve esserci. E' la stessa guardia gia' applicata alla riga
    # ASSENTE (``is_blind_relevant``), qui mancava.
    if isinstance(payload, dict) and payload.get("inplay") is not True:
        return
    if not is_blind_relevant(trade, {}):
        return
    motivo = _dato_che_manca(trade, payload)
    if motivo is None:
        # il dato e' tornato: si toglie il marcatore anche quando non c'e'
        # nessuna decisione da prendere (prima si puliva solo insieme a
        # un'uscita, quindi una posizione tranquilla restava marcata "cieca")
        _pulisci_dato_mancante(db, trade, meta)
        return
    tid = int(trade.get("id") or 0)
    if not meta.get("dato_mancante_da"):
        meta = {**meta, "dato_mancante_da": now.isoformat()}
        try:
            db.update_trade(tid, meta=meta)
            trade["meta"] = meta
        except Exception:  # noqa: BLE001
            pass
    last = _DATO_MANCANTE_LOG.get(tid)
    if last is not None and now_ts - last < FEED_BLIND_LOG_EVERY_S:
        return
    _DATO_MANCANTE_LOG[tid] = now_ts
    da = XE.parse_ts((trade.get("meta") or {}).get("dato_mancante_da"))
    _log(db, "feed_blind", {"trade_id": tid, "event_id": trade.get("event_id"),
                            "event_name": trade.get("event_name"),
                            "reason": motivo, "critical": True,
                            "da_s": round(now_ts - da, 1) if da else None,
                            "effetto": "nessuna regola di uscita puo' girare su "
                                       "questa posizione finche' il dato manca"})


def _pulisci_dato_mancante(db, trade: dict[str, Any], meta: dict[str, Any]) -> None:
    """Il dato e' tornato: si toglie il marcatore."""
    if not meta.get("dato_mancante_da"):
        return
    tid = int(trade.get("id") or 0)
    _DATO_MANCANTE_LOG.pop(tid, None)
    nuovo = {k: v for k, v in meta.items() if k != "dato_mancante_da"}
    try:
        db.update_trade(tid, meta=nuovo)
        trade["meta"] = nuovo
    except Exception:  # noqa: BLE001
        pass


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


# CERT. 14/09 — CANCELLETTO DI APPROVAZIONE SULLE CHIUSURE DEL TENNIS.
# Marker sulla riga del trade: senza, per sapere se esiste gia' una proposta
# viva servirebbe una query per trade per ciclo.
PROPOSTA_KEY = "exit_proposal"
# istante dell'ultima lettura del feed da parte del bot (t2 della catena)
_LETTURA_FEED: dict[str, float] = {"ms": 0.0}
# uscite per cui non approvare COSTA: sono quelle che il manuale dichiara
# obbligatorie o urgenti. La proposta le marca cosi' la pagina puo' urlarle.
_USCITE_URGENTI = ("loss", "mandatory", "red_card")
# Ogni quanto si ricontrolla che la proposta sia ANCORA in attesa di firma.
# E' anche l'intervallo minimo fra una proposta ignorata e la successiva: un
# INTERVALLO, non un blocco. L'utente ha deciso che le proposte ignorate «devono
# ripresentarsi all'occasione successiva», e senza questo ricontrollo il
# marcatore sulla riga restava valorizzato per sempre — una sola proposta per
# posizione, e chi ignorava una volta restava senza bottone.
_RICONTROLLO_PROPOSTA_S = 20.0
# Quando si RIPROPONE una chiusura che l'utente ha ignorato. Decisione
# dell'utente: «se rifiuto, riproporre quando cambia qualcosa IN BENE O MALE».
# Non a tempo fisso — sarebbe una raffica che si impara a ignorare — e non una
# volta sola: su un CAMBIAMENTO, in una direzione o nell'altra.
_RIPROPOSTA_TICK = 2        # il prezzo di chiusura si e' mosso di almeno N tick
_RIPROPOSTA_EUR = 0.10      # ...oppure il P&L bloccabile e' cambiato di almeno tanto


def _cambiamento_sostanziale(rifiutata: dict[str, Any], prezzo: Optional[float],
                             punteggio: Optional[str], locked: Optional[float],
                             side: str) -> Optional[str]:
    """La situazione e' DIVERSA da quella che l'utente ha gia' visto e scartato?

    Ritorna il motivo (da mostrare in pagina) oppure None. «Diverso» vale in
    entrambe le direzioni: se ignoro a −0,32 € e dieci minuti dopo la stessa
    uscita costa −1,08, quella e' una situazione nuova e va rivista. Ma anche il
    contrario — se nel frattempo e' migliorata, l'utente vuole saperlo.
    """
    if str(punteggio or "") != str(rifiutata.get("score") or ""):
        return "il punteggio e' cambiato"
    vecchio_eur, nuovo_eur = rifiutata.get("locked"), locked
    if isinstance(vecchio_eur, (int, float)) and isinstance(nuovo_eur, (int, float)):
        if abs(float(nuovo_eur) - float(vecchio_eur)) >= _RIPROPOSTA_EUR - 1e-9:
            verso = "migliorato" if float(nuovo_eur) > float(vecchio_eur) else "peggiorato"
            return f"il P&L bloccabile e' {verso}"
    passi = X.scorrimento(rifiutata.get("price"), prezzo, side)
    if passi is not None and abs(int(passi)) >= _RIPROPOSTA_TICK:
        return "il prezzo di chiusura si e' mosso"
    return None


def _catena_dei_tempi(feed_row: Optional[dict[str, Any]],
                      now: Optional[datetime] = None) -> dict[str, Any]:
    """t0..t3 di un'APERTURA, dal prezzo alla decisione.

    Sono i quattro istanti che stanno PRIMA dell'ordine; t4/t5/t6 (invio,
    risposta di Betfair, fill) li scrive ``execution.place``, che e' l'unico
    posto che li conosce. Uniti sulla riga del trade danno la catena intera.

    Tutto in millisecondi di orologio del mondo, perche' vanno confrontati con
    istanti che vengono dal feed e da Betfair, non da questo processo.

    ``now`` e' accettato per compatibilita' con i chiamanti ma NON si usa piu'
    per t3: l'istante della decisione e' adesso, non l'inizio del ciclo."""
    p = (feed_row or {}).get("payload") or {}
    t0 = p.get("odds_ts_ms")
    t1 = None
    upd = (feed_row or {}).get("updated_at")
    if upd:
        try:
            t1 = round(datetime.fromisoformat(str(upd).replace("Z", "+00:00")).timestamp() * 1000.0, 1)
        except (TypeError, ValueError):
            t1 = None
    t2 = _LETTURA_FEED["ms"] or None
    # CERT. 14/09 — t3 e' l'istante in cui si DECIDE, e si prende ADESSO.
    #
    # Prima qui c'era ``now``, cioe' l'istante in cui e' COMINCIATO il ciclo:
    # un momento che precede persino la lettura del feed. Ne uscivano tre bugie
    # in fila, tutte a nostro favore:
    #   · t3 risultava PRIMA di t2 (misurato: 216, 238, 282 ms prima), quindi
    #     il salto «bot -> decisione» era negativo e la Control Room lo mostrava
    #     come «—»: un pezzo di catena che non si poteva guardare;
    #   · «feed -> bot» si prendeva anche il tempo della lettura del feed;
    #   · ``prezzo_to_decisione_ms`` fermava il cronometro prima che il bot
    #     avesse in mano la riga, e faceva sembrare la catena piu' corta di
    #     quanto sia (sul trade #287: 3,2 s dichiarati contro 4,7 s reali).
    # Un cronometro che sbaglia a nostro favore e' peggio di nessun cronometro.
    t3 = round(time.time() * 1000.0, 1)
    tempi: dict[str, Any] = {
        "t0_quote_ms": t0 if isinstance(t0, (int, float)) and not isinstance(t0, bool) else None,
        "t1_feed_ms": t1, "t2_letto_ms": t2, "t3_deciso_ms": t3,
    }
    # i due tratti che interessano davvero, gia' calcolati: chi legge la riga
    # non deve rifare sottrazioni per sapere dove se ne e' andato il tempo.
    if tempi["t0_quote_ms"] is not None:
        tempi["prezzo_to_decisione_ms"] = round(t3 - float(tempi["t0_quote_ms"]), 1)
    if t1 is not None and t2:
        tempi["feed_to_bot_ms"] = round(float(t2) - t1, 1)
    return {"tempi": tempi}


def _proponi_chiusura(*, db, trade: dict[str, Any], meta: dict[str, Any],
                      decision: XE.ExitDecision, prices: dict[str, Any],
                      payload: dict[str, Any], params: dict[str, Any],
                      row: Optional[dict[str, Any]], now: datetime) -> bool:
    """Scrive (o aggiorna) la PROPOSTA di chiusura invece di mandare l'ordine.

    Ritorna True se la proposta esiste: il chiamante allora NON invia niente.
    Ritorna False se la scrittura non e' riuscita — e in quel caso il chiamante
    procede come sempre. E' la direzione giusta del ripiego: il guasto di una
    tabella di proposte non puo' lasciare una posizione aperta senza uscita,
    che e' la cosa che costa davvero. La pagina lo vede lo stesso, perche'
    l'uscita finisce nel log come tutte le altre.
    """
    prima = (meta.get(PROPOSTA_KEY) or {}) if isinstance(meta.get(PROPOSTA_KEY), dict) else {}
    size_ora = _f(trade.get("size"), None)
    # SOSTANZA della proposta: il motivo dell'uscita e quanto c'e' da chiudere.
    # Il PREZZO non e' sostanza: la pagina lo pesca vivo dal feed di scansione
    # (che le arriva in push) usando market_id + selection_id + lato. Riscrivere
    # la riga a ogni giro per aggiornare un prezzo che la pagina ha gia' sarebbe
    # traffico inutile su un database che a settembre e' gia' andato giu' una
    # volta per esaurimento di I/O.
    sostanza = (str(decision.kind), str(decision.reason), size_ora)
    invariata = (int(prima.get("request_id") or 0) > 0
                 and tuple(prima.get("sostanza") or ()) == sostanza)
    if invariata:
        # CERT. 14/09 — IL MARCATORE NON BASTA A DIRE CHE LA PROPOSTA E' VIVA.
        # Prima si usciva qui e basta: se nel frattempo l'utente aveva IGNORATO
        # la proposta (richiesta -> 'rejected'), il marcatore restava sulla riga
        # e non ne nasceva mai piu' una. Chi ignorava una volta si ritrovava
        # senza bottone su una posizione aperta, mentre il prezzo si muoveva
        # contro. Ogni ``_RICONTROLLO_PROPOSTA_S`` si va a VEDERE se e' ancora
        # in attesa di firma, invece di dedurlo da un campo scritto tempo prima.
        eta = now.timestamp() - (XE.parse_ts(prima.get("ts")) or 0.0)
        if eta < _RICONTROLLO_PROPOSTA_S:
            return True      # ricontrollata da poco: nessuna lettura, nessuna scrittura
        try:
            viva = db.proposta_di_chiusura_viva(int(trade["id"]))
        except Exception:  # noqa: BLE001 — nel dubbio si RIPROPONE: una proposta
            viva = None     # in piu' non costa, una in meno lascia senza uscita
        if viva is not None:
            # ancora in attesa di firma: si rinfresca solo il marcatore, la
            # richiesta non si riscrive (il prezzo vivo lo pesca la pagina)
            nuovo = {**meta, PROPOSTA_KEY: {**prima, "ts": now.isoformat()}}
            db.update_trade(int(trade["id"]), meta=nuovo)
            trade["meta"] = nuovo
            return True
        # IGNORATA (o finita in errore). Non si ripropone subito e nemmeno a
        # tempo: si ripropone quando la SITUAZIONE e' cambiata, in bene o in
        # male. Alla prima volta si fotografa cio' che l'utente ha scartato.
        sit_ora = XE.situation(trade, payload)
        conti_ora = _conti_di_chiusura(db, trade, prices, params)
        lato_ora = "lay" if str(trade.get("side") or "").lower() == "back" else "back"
        prezzo_ora_ = _f(prices.get(lato_ora), None)
        rifiutata = prima.get("rifiutata")
        if not isinstance(rifiutata, dict):
            rifiutata = {"price": prezzo_ora_, "score": sit_ora.get("score"),
                         "locked": conti_ora["locked"], "ts": now.isoformat()}
            nuovo = {**meta, PROPOSTA_KEY: {**prima, "ts": now.isoformat(),
                                            "rifiutata": rifiutata}}
            db.update_trade(int(trade["id"]), meta=nuovo)
            trade["meta"] = nuovo
            return True      # scartata adesso: si aspetta che cambi qualcosa
        perche = _cambiamento_sostanziale(rifiutata, prezzo_ora_, sit_ora.get("score"),
                                          conti_ora["locked"], lato_ora)
        if perche is None:
            nuovo = {**meta, PROPOSTA_KEY: {**prima, "ts": now.isoformat()}}
            db.update_trade(int(trade["id"]), meta=nuovo)
            trade["meta"] = nuovo
            return True      # tutto come l'aveva vista: non si insiste
        # qualcosa e' cambiato: si ricomincia, col prezzo di ADESSO
        prima = {**prima, "riproposta_perche": perche}
    sit = XE.situation(trade, payload)
    conti = _conti_di_chiusura(db, trade, prices, params)
    # l'istante della DECISIONE si conserva: se lo si rinfrescasse, la latenza
    # misurata sarebbe sempre ~zero e il numero direbbe il contrario del vero.
    decided_at = str(prima.get("decided_at") or now.isoformat())
    back, lay = _f(prices.get("back"), None), _f(prices.get("lay"), None)
    # per chiudere si attraversa lo spread: chi ha un BACK aperto chiude LAYando
    lato_chiusura = "lay" if str(trade.get("side") or "").lower() == "back" else "back"
    prezzo_ora = lay if lato_chiusura == "lay" else back
    corpo = {
        "trade_id": int(trade["id"]),
        "event_id": trade.get("event_id"),
        "event_name": trade.get("event_name"),
        "sport": trade.get("sport"),
        "strategy": trade.get("strategy"),
        "selection_name": trade.get("selection_name"),
        "market_id": trade.get("market_id"),
        "market_type": trade.get("market_type"),
        # stessa selezione dell'apertura: si chiude scommettendo il lato
        # OPPOSTO sulla STESSA selezione. Insieme a market_id e side e' la
        # chiave con cui la pagina pesca il prezzo vivo dal feed.
        "selection_id": trade.get("selection_id"),
        # lato e prezzo DELL'ORDINE DI CHIUSURA, non dell'apertura: e' quello
        # che verrebbe piazzato premendo APPROVA
        "side": lato_chiusura,
        # CHIAVE con cui la pagina pesca il PREZZO VIVO dal feed di scansione:
        # market_id + selection_id + lato. Il prezzo qui sotto e' la
        # FOTOGRAFIA al momento della decisione, e serve a due cose — sapere su
        # cosa il bot ha deciso, e misurare lo scostamento. Non e' il prezzo su
        # cui si piazza: quello lo guarda l'utente, vivo, un istante prima.
        "price_at_decision": prezzo_ora,
        "size_available_at_decision": _f(prices.get(f"{lato_chiusura}_size"), None),
        "entry_side": str(trade.get("side") or "").lower(),
        "entry_price": _f(trade.get("price"), None),
        "size": _f(trade.get("size"), None),
        # CODICI, non testo: la frase in italiano vive in UN solo posto
        # (`frontend/safeActivity.ts`: `safeExitKindLabel` / `safeReasonLabel`)
        # e la Control Room riusa quella. Tradurre anche qui vorrebbe dire due
        # tabelle che prima o poi dicono due cose diverse della stessa uscita.
        "exit_kind": decision.kind,
        "exit_reason": decision.reason,
        "urgente": decision.kind in _USCITE_URGENTI,
        "minute": sit.get("minute"),
        "score": sit.get("score"),
        # quanto vale chiudere ORA e quanto vale tenere, al netto della
        # commissione: sono i due numeri su cui si decide
        "locked_at_decision": conti["locked"],
        "hold_profit": conti["hold_profit"],
        "loss_if_lose": conti["loss_if_lose"],
        "mode": str(trade.get("mode") or "paper"),
        "feed_updated_at": (row or {}).get("updated_at"),
        # t2: quando il bot ha avuto in mano questa riga. Con t0 (odds_ts_ms) e
        # t1 (updated_at del feed) si vede DOVE va il tempo prima ancora che il
        # bot decida — che e' meta' della catena, e la meta' che nessuno guarda.
        "t2_letto_ms": _LETTURA_FEED["ms"] or None,
        # eta' del PREZZO su cui si opererebbe (non dello scritto sul feed):
        # e' il numero che conta prima di piazzare
        "odds_ts_ms": payload.get("odds_ts_ms"),
        # CERT. 14/09 — I DUE ISTANTI CHE RENDONO MISURABILE LA LATENZA.
        # `decided_at` NON si rinfresca a ogni aggiornamento della proposta: e'
        # il momento in cui la regola del manuale e' scattata, e resta fermo.
        # `proposed_at` invece e' l'ultimo aggiornamento. La differenza fra
        # `decided_at` e il piazzamento e' la latenza vera di una chiusura
        # approvata a mano — che e' quella che l'utente vuole vedere.
        "decided_at": decided_at,
        "proposed_at": now.isoformat(),
        # perche' questa chiusura si ripresenta dopo che l'utente l'aveva
        # ignorata: la pagina deve dirlo, o sembra insistenza invece che una
        # situazione nuova.
        **({"riproposta_perche": prima["riproposta_perche"]}
           if prima.get("riproposta_perche") else {}),
    }
    try:
        rid = db.scrivi_proposta_di_chiusura(int(trade["id"]), corpo)
    except Exception as ex:  # noqa: BLE001
        _log(db, "error", {"reason": "proposta_chiusura_fallita",
                           "trade_id": trade.get("id"), "err": str(ex)[:160],
                           "critical": True})
        return False
    if not rid:
        return False
    nuovo = {**meta, PROPOSTA_KEY: {"request_id": int(rid), "ts": now.isoformat(),
                                    "decided_at": decided_at,
                                    "sostanza": list(sostanza),
                                    "kind": decision.kind}}
    db.update_trade(int(trade["id"]), meta=nuovo)
    trade["meta"] = nuovo
    _log(db, "exit_hold", {"reason": "in_attesa_di_approvazione",
                           "trade_id": trade.get("id"), "request_id": int(rid),
                           "exit_kind": decision.kind, "exit_reason": decision.reason,
                           "critical": bool(corpo["urgente"])})
    return True


def _decadi_proposta(db, trade: dict[str, Any], meta: dict[str, Any], motivo: str) -> None:
    """La condizione di uscita non regge piu': la proposta viva decade.

    Si guarda il MARKER sulla riga, non il database: senza, servirebbe una
    query per trade a ogni ciclo per una cosa che quasi sempre non c'e'."""
    if not isinstance(meta.get(PROPOSTA_KEY), dict):
        return
    try:
        db.chiudi_proposta(int(trade["id"]), motivo)
    except Exception as ex:  # noqa: BLE001 — non e' money-critical
        logger.warning("[safe.bot] decadenza proposta KO (trade %s): %s",
                       trade.get("id"), str(ex)[:120])
    nuovo = {k: v for k, v in meta.items() if k != PROPOSTA_KEY}
    db.update_trade(int(trade["id"]), meta=nuovo)
    trade["meta"] = nuovo


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
        # 12/09: il ricontrollo del prezzo e' a cadenza FISSA (WAITING_PRICE_RETRY_S,
        # vedi _exit_due), non col backoff lungo: ``next_retry_at`` resta per la
        # UI; ``last_wait_at`` guida la cadenza; il log si dirada.
        try:
            _EXIT_WAIT_AT[int(trade["id"])] = now.timestamp()
        except (TypeError, ValueError, KeyError):
            pass
        prev_exit = (trade.get("meta") or meta or {}).get(EXIT_KEY) or {}
        cambiato = (str(prev_exit.get("state") or "") != "waiting_price"
                    or str(prev_exit.get("kind") or "") != str(decision.kind)
                    or str(prev_exit.get("reason") or "") != str(decision.reason)
                    or str(prev_exit.get("last_error") or "") != str(err))
        if cambiato or waits <= 3 or waits % WAITING_PRICE_LOG_EVERY == 0:
            _write_exit_state(db, trade, trade.get("meta") or meta, state="waiting_price",
                              kind=decision.kind, reason=decision.reason,
                              last_error=err, wait_attempts=waits,
                              last_wait_at=now.isoformat(),
                              next_retry_at=_iso_in(now, WAITING_PRICE_RETRY_S))
        if waits <= 3 or waits % WAITING_PRICE_LOG_EVERY == 0:
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


def _paper_ladder(side: str, feed_prices: Optional[dict[str, Any]],
                  best_size: Optional[float] = None) -> Optional[tuple]:
    """Livello di libro per il fill PAPER dal feed: ((prezzo abbinabile, size)).

    12/09 (paper = live senza soldi): ``omega_engine.paper_fill`` senza ladder
    riempie TUTTA la size AL PREZZO RICHIESTO, qualunque sia il libro. Con un
    livello reale del feed un LAY a P si abbina solo se P >= miglior lay
    disponibile (e AL prezzo del libro, come Betfair), un BACK solo se
    P <= miglior back; la size e' cappata alla liquidita' del feed. Prezzo del
    lato ASSENTE nel feed = in live il FOK muore -> livello a size 0 (nessun
    fill). ``feed_prices`` None (nessuna riga) -> None: il chiamante decide.

    LIQUIDITA': prima la size del livello, poi ``best_size`` dichiarata dal
    chiamante (la stessa che il segnale/opportunita' ha visto sul book). Se
    NESSUNA delle due e' nota il livello vale 0: chi non sa quanto c'e' sul
    book non ottiene fill (stessa regola di ``paper_fill``, mai fill regalati)."""
    if not isinstance(feed_prices, dict):
        return None
    px = _f(feed_prices.get(side), 0.0)
    if px <= 1.0:
        return ((0.0, 0.0),)
    avail = feed_prices.get(f"{side}_size")
    if avail is None:
        avail = best_size
    if avail is None:
        return ((px, 0.0),)
    return ((px, max(0.0, _f(avail, 0.0))),)


def _execute(*, db, market, trade_id: int, row: dict[str, Any], params: dict,
             now: datetime, best_size: Optional[float], ladder: Any,
             feed_prices: Optional[dict[str, Any]] = None) -> X.PlaceOutcome:
    """Esegue la riga riservata e la porta a 'open'/'error' (o la lascia
    'pending' se il fill arriva dalla coda flumine).

    12/09 — guardie di APERTURA comuni a tutti i percorsi (segnali, opportunita',
    anomalie, combo, manuale):
      • size sotto il minimo ASSOLUTO dell'exchange (0,01 €) = errore parlante;
        fra 0,01 € e il minimo di giurisdizione si usa il place-and-trim, non si
        rifiuta (13/09: prima il rifiuto era a 2 € e rendeva irraggiungibile la
        macchina sotto-minimo, in aperta violazione della regola "qualsiasi
        importo e' piazzabile fino al centesimo");
      • fill PAPER sul libro del feed (``_paper_ladder``): prezzo abbinabile e
        liquidita' reali, mai "al prezzo richiesto qualunque sia il mercato".
        Senza prezzi del feed (``feed_prices`` None) in paper non si simula
        nulla: errore ``paper_prezzi_non_disponibili``."""
    side = str(row["side"])
    mode = str(row["mode"])
    try:
        size = float(row["size"])
    except (TypeError, ValueError):
        size = 0.0
    # CERT. 13/09 — il minimo di giurisdizione NON e' piu' un rifiuto qui.
    # Su Betfair QUALSIASI importo e' piazzabile fino a 0,01 EUR con la tecnica
    # place-and-trim (parcheggio a quota non abbinabile -> cancel parziale ->
    # replace alla quota reale), che in questo progetto e' gia' implementata e
    # collegata (``stream/trading/submin.py`` per la coda,
    # ``omega_market.place_submin_live`` per il REST). Rifiutando qui, PRIMA di
    # ``X.place``, quella macchina non veniva MAI raggiunta su un'apertura: uno
    # stake di 1,00 EUR finiva in errore ``size_sotto_minimo_betfair`` e dopo 3
    # tentativi il segnale era morto per tutta la partita.
    # Resta un solo pavimento: quello dell'exchange, 0,01 EUR. Quale dei due
    # percorsi usare (place normale o place-and-trim) lo decide ``X.place``,
    # che conosce anche il LATO (il minimo .it e' BACK 2,00 / LAY 0,50).
    if size < X.ABS_MIN_SIZE - 1e-9:
        _place_fail(db, trade_id, row, f"size_sotto_il_minimo_assoluto:{size:.2f}", now, params)
        return X.PlaceOutcome("error", None, 0.0, None,
                              f"size_sotto_il_minimo_assoluto:{size:.2f}")
    if mode == "paper" and not ladder:
        lvl = _paper_ladder(side, feed_prices, best_size)
        if lvl is None:
            _place_fail(db, trade_id, row, "paper_prezzi_non_disponibili", now, params)
            return X.PlaceOutcome("error", None, 0.0, None, "paper_prezzi_non_disponibili")
        ladder = lvl
    out = X.place(
        db=db, market=market, mode=mode, event_id=str(row["event_id"]),
        market_id=str(row["market_id"]), selection_id=int(row["selection_id"]),
        side=side, price=row["price"], size=row["size"],
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
        # CERT. 14/09 — t4/t5/t6 DELL'APERTURA: i due istanti attorno alla
        # chiamata a Betfair e il momento del fill. Con t0..t3 che il piazzamento
        # ha gia' scritto nel meta della riserva, la riga porta la catena INTERA
        # dal prezzo all'abbinamento — che e' la condizione 2 dell'utente.
        if out.esecuzione:
            meta["esecuzione"] = out.esecuzione
            meta["t6_fill_ms"] = round(time.time() * 1000.0, 1)
            t3 = ((meta.get("tempi") or {}).get("t3_deciso_ms")
                  if isinstance(meta.get("tempi"), dict) else None)
            t5 = out.esecuzione.get("t5_risposta")
            if isinstance(t3, (int, float)) and isinstance(t5, (int, float)):
                # il tratto che l'utente chiama "latenza del bot": da quando ha
                # deciso a quando Betfair ha risposto.
                meta["tempi"] = {**(meta.get("tempi") or {}),
                                 "decisione_to_risposta_ms": round(float(t5) - float(t3), 1)}
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

# CERTIFICAZIONE 12/09 — NOMI DELLE PARTITE PER L'ATTIVITA'.
# Il servizio scriveva solo l'``event_id`` nei log: nella scheda Attivita' il
# trader leggeva "NON ENTRATO 36050104 · spread_anomalo" e non sapeva di quale
# partita si parlasse (la UI provava a risolverlo dalle righe caricate, ma un
# evento uscito dal feed tornava a essere un numero). Il nome ce l'ha il feed:
# lo si registra UNA volta per ciclo e lo si allega a ogni riga di attivita'.
# Mappa di processo con tetto: nessuna scrittura in piu' sul DB.
_EVENT_NAMES: dict[str, str] = {}
_EVENT_NAMES_MAX = 800


def remember_event_names(rows: Any) -> None:
    """Memorizza event_id -> nome leggibile dalle righe del feed unico."""
    if not isinstance(rows, (list, tuple)):
        return
    for r in rows:
        if not isinstance(r, dict):
            continue
        eid = str(r.get("event_id") or "")
        if not eid:
            continue
        pl = r.get("payload") if isinstance(r.get("payload"), dict) else {}
        name = str(pl.get("event_name") or "").strip()
        if not name:
            home, away = str(pl.get("home") or "").strip(), str(pl.get("away") or "").strip()
            name = f"{home} v {away}".strip(" v") if (home or away) else ""
        if name:
            _EVENT_NAMES[eid] = name
    if len(_EVENT_NAMES) > _EVENT_NAMES_MAX:      # tetto: mai crescita illimitata
        for k in list(_EVENT_NAMES)[:len(_EVENT_NAMES) - _EVENT_NAMES_MAX]:
            _EVENT_NAMES.pop(k, None)


def event_name_for(event_id: Any) -> Optional[str]:
    return _EVENT_NAMES.get(str(event_id or "")) or None


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
def _agg_recente(mode: Optional[str], now_ts: float) -> Optional[dict[str, float]]:
    """Ultimi aggregati letti bene, se non piu' vecchi di ``_AGG_TTL_S``."""
    voce = _AGG_ULTIMO_BUONO.get(str(mode or "*"))
    if voce is None:
        return None
    ts, agg = voce
    return agg if (now_ts - ts) <= _AGG_TTL_S else None


# righe 'pending' lette da ``reconcile_pending`` in questo ciclo (nessuna
# lettura duplicata: è la regola del progetto sulle chiamate al DB)
_PENDING_CICLO: dict[str, Any] = {}
_PENDING_CICLO_TTL_S = 5.0


def _pending_esatto(db, now_ts: Optional[float] = None) -> list[dict[str, Any]]:
    """Riserve della variante ESATTO ancora 'pending' (ordine in volo).

    Servono alla guardia "un solo lato Altro risultato per partita": fra un
    ciclo e l'altro la riga vive in 'pending' e ``open_trades`` non la
    restituisce. Riusa le righe gia' lette da ``reconcile_pending`` nello stesso
    giro; solo se non ci sono (o sono vecchie) rilegge. Best-effort: se fallisce,
    la guardia si limita alle posizioni gia' aperte, come prima."""
    righe: Any = None
    ts = _PENDING_CICLO.get("ts")
    if ts is not None and (now_ts is None or abs(float(now_ts) - float(ts)) <= _PENDING_CICLO_TTL_S):
        righe = _PENDING_CICLO.get("rows")
    if righe is None:
        try:
            righe = db.list_trades("pending") or []
        except Exception:  # noqa: BLE001 - mai fatale
            return []
    return [t for t in righe
            if isinstance(t, dict)
            and str(t.get("strategy") or "") == "esatto"
            and not t.get("closes_trade_id")]


# Ultimi aggregati LETTI BENE, per modalita', con il momento della lettura.
# CERT. 13/09 (review): senza questa copia, con il DB che va in timeout il bot
# smetteva di entrare ad OGNI ciclo e, peggio, scriveva un'attivita' critica ogni
# 2 secondi sullo stesso DB in ginocchio (~1800 righe l'ora).
_AGG_ULTIMO_BUONO: dict[str, tuple[float, dict[str, float]]] = {}
# Entro questo tempo si continua a valutare i cap sui numeri appena precedenti:
# la responsabilita' del giorno puo' solo essere SOTTOSTIMATA, e la si compensa
# con le riserve del ciclo (``_risk_commit``). Oltre, si blocca davvero.
_AGG_TTL_S = 120.0
_AGG_LOG_OGNI_S = 60.0
_AGG_LOG_TS: dict[str, float] = {}


def _risk_ctx_cieco(db, open_: list, ex: Exception,
                    open_all: Optional[list] = None,
                    mode: Optional[str] = None,
                    now_ts: Optional[float] = None) -> dict[str, Any]:
    """Contesto di rischio NON UTILIZZABILE: si conoscono le posizioni vive ma
    non i numeri della giornata. ``unavailable`` blocca i NUOVI ingressi (le
    uscite e il settlement continuano: mai lasciare una posizione nuda)."""
    logger.warning("[safe.bot] aggregates KO: %s — nessun nuovo ingresso in questo ciclo",
                   str(ex)[:160])
    # il log e' throttlato: l'allarme serve, non l'inondazione
    chiave = str(mode or "*")
    ora = float(now_ts or 0.0)
    ultimo = _AGG_LOG_TS.get(chiave)
    if ultimo is None or ora - ultimo >= _AGG_LOG_OGNI_S:
        _AGG_LOG_TS[chiave] = ora
        _log(db, "error", {"reason": "aggregati_non_leggibili", "critical": True,
                           "err": str(ex)[:160],
                           "effetto": "nuovi ingressi sospesi: senza i numeri della "
                                      "giornata i cap di rischio non sono verificabili"})
    return {"open": open_, "open_all": open_all if open_all is not None else open_,
            "realized_today": 0.0, "day_liability": 0.0,
            "day_liability_model": 0.0, "agg": {}, "unavailable": True}


def build_risk_ctx(db, now: datetime, params: dict[str, Any],
                   mode: Optional[str] = None) -> dict[str, Any]:
    """{open: posizioni vive (no gambe di chiusura), realized_today, day_liability,
    day_liability_model, agg}: UNA lettura per ciclo, aggiornata in memoria a
    ogni riserva riuscita (``_risk_commit``). Letture KO → fail-closed: contesto
    'bloccante' (loss stop finto) per non piazzare al buio.

    CERT. 13/09 — ``mode`` SEPARA i budget di rischio. Prima i cap erano ciechi
    alla modalita': ``daily_liability_cap`` veniva consumato da liability FINTE
    e bloccava i trade veri; ``daily_loss_stop`` sommava paper e live, cosi' una
    giornata paper negativa fermava il live e — verso piu' pericoloso — i
    profitti paper potevano mascherare perdite vere e tenere aperto il rubinetto
    oltre la soglia. I soldi finti non devono toccare il budget dei soldi veri."""
    try:
        # CERT. 13/09 (review) — UNA lettura, DUE liste.
        # Il filtro di modalita' serve ai CAP DI RISCHIO e ai numeri a schermo,
        # NON alla protezione delle posizioni. Filtrando qui e passando la lista
        # filtrata a ``process_exits`` si era creato un difetto peggiore di
        # quello che si voleva chiudere: con ``control.mode='paper'`` una
        # posizione LIVE aperta smetteva di essere gestita — niente uscita in
        # perdita, niente uscita obbligatoria, niente rosso — e arrivava al
        # settlement con la responsabilita' intera. Una posizione viva si
        # protegge SEMPRE, qualunque sia la modalita' del servizio.
        tutte = db.open_trades() or []
        open_all = [t for t in tutte if not t.get("closes_trade_id")]
        m = str(mode).lower() if mode else None
        open_ = ([t for t in open_all if str(t.get("mode") or "live").lower() == m]
                 if m else list(open_all))
    except Exception as ex:  # noqa: BLE001
        _log(db, "error", {"reason": "open_count_failed", "err": str(ex)[:160]})
        return {"open": [], "open_all": [], "realized_today": 0.0, "day_liability": 0.0,
                "day_liability_model": 0.0, "agg": {}, "unavailable": True}
    try:
        agg = dict(db.aggregates(mode=mode) or {})
    except TypeError:          # accessor vecchio senza il parametro
        try:
            agg = dict(db.aggregates() or {})
        except Exception as ex:      # noqa: BLE001
            return _risk_ctx_cieco(db, open_, ex, open_all, mode, now.timestamp())
    except Exception as ex:  # noqa: BLE001
        # Prima di bloccare: se abbiamo una lettura buona recentissima la si
        # riusa. I numeri possono solo essere piu' BASSI del vero (le riserve
        # del ciclo li alzano via ``_risk_commit``), quindi e' conservativo.
        recente = _agg_recente(mode, now.timestamp())
        if recente is not None:
            agg = dict(recente)
            return {"open": open_, "open_all": open_all,
                    "pending_esatto": _pending_esatto(db, now.timestamp()),
                    "realized_today": float(agg.get("realized_today", 0.0) or 0.0),
                    "day_liability": float(agg.get("day_liability", 0.0) or 0.0),
                    "day_liability_model": float(agg.get("day_liability_model", 0.0) or 0.0),
                    "agg": agg, "agg_stantio": True}
        # CERT. 13/09 — FAIL-CLOSED anche qui. Prima si proseguiva con ``agg={}``
        # e succedeva questo, in silenzio: ``realized_today`` = 0 -> il fermo
        # per perdita giornaliera si DISATTIVA; ``day_liability`` = 0 -> il cap
        # giornaliero di responsabilita' e quello dei trade di modello
        # RIPARTONO DA ZERO. Cioe': ogni volta che la lettura degli aggregati
        # falliva (e oggi il DB va in timeout di continuo) il bot perdeva tutte
        # le sue barriere di rischio proprio mentre era in difficolta'.
        # Il docstring dichiarava gia' "letture KO -> fail-closed": ora e' vero.
        return _risk_ctx_cieco(db, open_, ex, open_all, mode, now.timestamp())
    if agg:
        _AGG_ULTIMO_BUONO[str(mode or "*")] = (now.timestamp(), dict(agg))
        _AGG_LOG_TS.pop(str(mode or "*"), None)
    return {"open": open_, "open_all": open_all,
            "pending_esatto": _pending_esatto(db, now.timestamp()),
            "realized_today": float(agg.get("realized_today", 0.0) or 0.0),
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


_EREDITA_LOG: dict[str, float] = {"ts": 0.0}
_EREDITA_OGNI_S = 300.0


def _avvisa_ereditarieta(db, params: dict[str, Any], mode: str, now: datetime) -> None:
    """Con il servizio in LIVE, dice quali strategie ABILITATE non hanno una
    modalita' scritta e quindi restano in paper.

    Serve a rompere RUMOROSAMENTE l'aspettativa "armo il servizio e va tutto
    live". Romperla in silenzio sarebbe peggio che non romperla: l'utente
    crederebbe di star operando con soldi veri su quattro strategie mentre ne
    opera una, e se ne accorgerebbe dai numeri a fine giornata.
    """
    if str(mode).lower() != "live":
        return
    mappa = params.get("strategy_modes") or {}
    mute = [v for v in (params.get("variants") or [])
            if str(mappa.get(str(v)) or "").lower() not in ("paper", "live")]
    if not mute:
        return
    ora = now.timestamp()
    if ora - float(_EREDITA_LOG["ts"]) < _EREDITA_OGNI_S:
        return
    _EREDITA_LOG["ts"] = ora
    _log(db, "diagnosi", {
        "reason": "modalita_non_dichiarata",
        "strategie": list(mute),
        "nota": "servizio in LIVE: queste strategie NON hanno una modalita' "
                "scritta e restano in PAPER. I soldi veri si raggiungono solo "
                "scrivendo 'live' nella scheda parametri, mai per eredita'.",
    })


# la copertura del dato di controllo si misura una volta ogni tanto, non a ogni giro
_COPERTURA_LOG = {"ts": 0.0}
_COPERTURA_OGNI_S = 300.0


def _log_copertura_controllo(db, engine, params: dict[str, Any], now: datetime) -> None:
    """Scrive quante partite in corso hanno il dato di CONTROLLO del gioco.

    La condizione di controllo che la specifica chiede per BASE, ESATTO e PUNTA
    e' implementata ma SPENTA di default (``requireControl``). Accenderla su un
    dato che non arriva spegnerebbe in silenzio tre strategie su quattro — e'
    esattamente cosi' che BASE e PUNTA sono rimaste ferme per giorni con il
    riferimento pre-KO. Questa riga serve a sapere, prima di accendere, se il
    dato c'e' davvero e su quante partite."""
    fn = getattr(engine, "control_data_coverage", None)
    if not callable(fn):
        return
    ora = now.timestamp()
    if ora - float(_COPERTURA_LOG["ts"]) < _COPERTURA_OGNI_S:
        return
    try:
        cop = fn() or {}
    except Exception:  # noqa: BLE001 - una misura non ferma il bot
        return
    tot = int(cop.get("con_dato", 0)) + int(cop.get("senza_dato", 0))
    if tot <= 0:
        return
    _COPERTURA_LOG["ts"] = ora
    _log(db, "diagnosi", {
        "reason": "copertura_controllo_gioco",
        "con_dato": cop.get("con_dato"), "senza_dato": cop.get("senza_dato"),
        "percentuale": round(100.0 * int(cop.get("con_dato", 0)) / tot, 1),
        "attivo": bool((params.get("base") or {}).get("requireControl")),
        "nota": "condizione di controllo del gioco: copertura del dato IPS "
                "(corner/cartellini). Si accende solo se la copertura e' alta.",
    })


def _log_pre_match_missing(db, engine, params: dict[str, Any], now: datetime) -> None:
    """Scrive nell'attivita' le partite in corso senza riferimento 1X2 pre-KO.

    Sono quelle su cui BASE e PUNTA non possono scattare (``favorite_side``
    torna None -> check ``ok=None`` -> stato "nd" -> candidato scartato). Prima
    sparivano in silenzio ed era impossibile capire perche' il bot usasse solo
    la variante ESATTO. Throttlato come ogni altro scarto
    (``skip_log_interval_s``), quindi non allaga il feed."""
    fn = getattr(engine, "pre_match_missing_events", None)
    if not callable(fn):
        return
    try:
        manca = fn() or []
    except Exception:  # noqa: BLE001 - una diagnosi non puo' fermare il bot
        return
    for ev in manca:
        _log_skip(db, now, params, {
            "event_id": str(ev.get("event_id") or ""),
            "event_name": ev.get("event_name"),
            "minute": ev.get("minute"),
            "reason": "pre_ko_assente",
        })


def _rossi_al_piazzamento(feed_row: Any) -> dict[str, Any]:
    """``{"red_home": n, "red_away": n}`` dal feed, o ``{}`` se il dato manca.

    Finisce nel ``meta`` della riserva e diventa la BASE dei rossi per le
    uscite: solo un cartellino ARRIVATO DOPO l'ingresso deve far uscire."""
    payload = (feed_row or {}).get("payload") if isinstance(feed_row, dict) else None
    if not isinstance(payload, dict):
        return {}
    rh, ra = payload.get("red_home"), payload.get("red_away")
    if isinstance(rh, bool) or isinstance(ra, bool):
        return {}
    if not isinstance(rh, (int, float)) or not isinstance(ra, (int, float)):
        return {}
    return {"red_home": int(rh), "red_away": int(ra)}


def _esatto_gia_su_evento(risk_ctx: dict[str, Any], event_id: Any) -> bool:
    """C'e' gia' una posizione VIVA della variante ESATTO su questa partita?

    Il motore valuta la variante su entrambi i lati e a punteggio pari (0-0,
    1-1) o 1-0 passano tutti e due: senza questo controllo si banca due volte lo
    stesso mercato, con il doppio della responsabilita' e lo stesso profitto."""
    eid = str(event_id or "")
    # CERT. 13/09 (review) — anche i PENDING.
    # ``risk_ctx["open"]`` viene da ``open_trades``, che ritorna solo
    # 'open'/'hedged'. In LIVE via coda il fill richiede almeno un ciclo: la
    # riga del primo lato resta 'pending' e al ciclo dopo la guardia non la
    # vedeva -> il secondo lato passava. Il difetto si manifestava proprio dove
    # costa (soldi veri), mentre in paper il fill immediato lo nascondeva.
    # ``_risk_commit`` aggiunge la riserva al contesto, quindi i due lati dello
    # STESSO ciclo erano gia' coperti: il buco era fra un ciclo e l'altro.
    for t in (risk_ctx.get("open_all") or risk_ctx.get("open") or []):
        if not isinstance(t, dict):
            continue
        if str(t.get("event_id") or "") != eid:
            continue
        if str(t.get("strategy") or "") != "esatto":
            continue
        if t.get("closes_trade_id"):
            continue
        return True
    return bool(_esatto_pending_su_evento(risk_ctx, eid))


def _esatto_pending_su_evento(risk_ctx: dict[str, Any], eid: str) -> bool:
    """Riserve ESATTO ancora in volo ('pending') sulla stessa partita."""
    for t in (risk_ctx.get("pending_esatto") or []):
        if isinstance(t, dict) and str(t.get("event_id") or "") == eid:
            return True
    return False


def scan_and_place(*, db, market, engine, rows: list[dict], params: dict,
                   mode: str, now: datetime, risk_ctx: Optional[dict] = None,
                   scanner_ts: Optional[float] = None,
                   scanner_ts_known: bool = False) -> "tuple[int, int]":
    """(piazzati, segnali_attivi). Un segnale già tradato non si ripiazza (I1
    per (event_id, signal_key)); le barriere di rischio sono le stesse del
    manuale più il motore ``risk`` (gate prima della riserva)."""
    # ⚠️ 15/09 — il motivo del blocco vale per UN giro: si riazzera qui, o la
    # pagina continuerebbe a mostrare un freno che non c'è più.
    _BLOCCO.update({"motivo": None, "tetto": None, "aperte": None})
    if engine is None:
        return 0, 0
    try:
        signals = list(engine.evaluate(rows) or [])
    except Exception as ex:  # noqa: BLE001 — motore rotto: nessun piazzamento
        _log(db, "error", {"reason": "engine_failed", "err": str(ex)[:160]})
        return 0, 0
    # CERT. 13/09 — DIRE perche' BASE e PUNTA non escono. Senza il riferimento
    # 1X2 pre-KO quelle due varianti finiscono in stato "nd" e vengono scartate
    # PRIMA di diventare segnali: nessuna riga di attivita', nessun motivo a
    # schermo, e l'utente vede solo ESATTO (l'unica che non usa il pre-KO).
    # Va scritto qui, prima dell'uscita anticipata su "nessun segnale".
    _log_pre_match_missing(db, engine, params, now)
    _log_copertura_controllo(db, engine, params, now)
    _avvisa_ereditarieta(db, params, mode, now)
    if not signals:
        return 0, 0
    try:
        traded = set(_traded_keys(db, mode))
    except Exception as ex:  # noqa: BLE001 — FAIL-CLOSED: senza idempotenza NON si piazza
        _log(db, "error", {"reason": "traded_keys_failed", "err": str(ex)[:160]})
        return 0, len(signals)
    if risk_ctx is None:
        risk_ctx = build_risk_ctx(db, now, params, mode=mode)
    if risk_ctx.get("unavailable"):
        return 0, len(signals)
    open_n = len(risk_ctx.get("open") or [])

    # CERT. 14/09 — MODALITA' PER VARIANTE. In un ciclo LIVE le varianti fuori da
    # ``live_variants`` piazzano in PAPER. Cap, idempotenza e conteggi restano
    # SEPARATI per modalita': se il tetto di responsabilita' del live venisse
    # consumato da posizioni finte (o viceversa) il limite che protegge i soldi
    # veri sarebbe sbagliato — ed e' proprio il difetto che la separazione
    # paper/live del 13/09 era nata per chiudere.

    _ctx_per_modalita: dict[str, dict] = {str(mode): risk_ctx}
    _traded_per_modalita: dict[str, set] = {str(mode): traded}
    _placed_per_modalita: dict[str, int] = {}

    def _modalita_di(variante: str) -> str:
        return modalita_di_strategia(variante, mode, params)

    def _ctx_di(m: str) -> Optional[dict]:
        """Contesto di rischio della modalita' ``m``, letto una volta per ciclo.
        ``None`` = lettura KO: in quella modalita' non si piazza (fail-closed),
        ma l'altra continua a lavorare."""
        if m not in _ctx_per_modalita:
            c = build_risk_ctx(db, now, params, mode=m)
            _ctx_per_modalita[m] = c
        c = _ctx_per_modalita[m]
        return None if c.get("unavailable") else c

    def _traded_di(m: str) -> Optional[set]:
        if m not in _traded_per_modalita:
            try:
                _traded_per_modalita[m] = set(_traded_keys(db, m))
            except Exception as ex:  # noqa: BLE001 — senza idempotenza NON si piazza
                _log(db, "error", {"reason": "traded_keys_failed",
                                   "mode": m, "err": str(ex)[:160]})
                _traded_per_modalita[m] = None   # type: ignore[assignment]
        return _traded_per_modalita[m]

    variants = {str(v) for v in (params.get("variants") or [])}
    max_open = int(params.get("max_open_trades") or 0)
    cap = float(params.get("max_liability_per_trade") or 0.0)
    factor = float(params.get("min_size_available_factor") or 0.0)
    commission = float(params.get("commission_pct", 5.0)) / 100.0
    max_spread = float(params.get("max_spread_ratio") or 1.6)
    rows_by_event = {str(r.get("event_id")): r for r in rows if isinstance(r, dict)
                     and r.get("event_id")}
    now_ts = now.timestamp()
    if not scanner_ts_known:
        scanner_ts = _scanner_ts(db, now_ts)
    placed = 0
    for s in signals:
        key = _sig(s, "key")
        event_id = _sig(s, "event_id")
        if not key or not event_id:
            continue
        variant = str(_sig(s, "variant") or "")
        if variants and variant not in variants:
            # era l'UNICO scarto senza log: la UI prometteva "perche' NON e'
            # entrato" e su questo caso non aveva niente da leggere
            _log_skip(db, now, params, {"event_id": str(event_id), "signal_key": str(key),
                                        "strategy": variant,
                                        "reason": "variante_non_abilitata"})
            continue
        # da qui in poi la MODALITA' e' quella della variante, non del servizio
        mode_s = _modalita_di(variant)
        traded_s = _traded_di(mode_s)
        if traded_s is None:
            continue                      # idempotenza illeggibile: non si piazza
        if (str(event_id), str(key)) in traded_s:
            continue
        risk_ctx_s = _ctx_di(mode_s)
        if risk_ctx_s is None:
            continue                      # rischio illeggibile in quella modalita'
        open_n_s = len(risk_ctx_s.get("open") or [])
        # CERT. 13/09 — UN SOLO lato "Altro risultato" per partita.
        # Il motore valuta la variante ESATTO su ENTRAMBI i lati (casa e ospite)
        # e a 0-0, 1-0 e 1-1 passano tutti e due il filtro "al massimo 1 gol":
        # nascono due segnali con chiavi diverse (``ev:esatto:home:1-1`` e
        # ``ev:esatto:away:1-1``) e il bot bancava DUE volte lo stesso mercato.
        # Numeri reali: due lay a 35 e 34 con stake 2 EUR = 134 EUR di
        # responsabilita' sulla stessa partita per 4 EUR lordi di profitto
        # massimo, e ne' ``per_event_liability_cap`` ne' ``per_event_max_trades``
        # lo fermavano. Il manuale parla di UNA squadra da bancare, al singolare.
        if variant == "esatto" and _esatto_gia_su_evento(risk_ctx_s, event_id):
            _log_skip(db, now, params, {"event_id": str(event_id), "signal_key": str(key),
                                        "strategy": variant,
                                        "reason": "esatto_lato_gia_aperto"})
            continue
        # 12/09: mai un ingresso su una riga del feed NON FRESCA (scanner fermo
        # o partita non riscritta da >120 s): il paper riempirebbe a quote
        # vecchie, il live manderebbe un FOK a vuoto.
        feed_row = rows_by_event.get(str(event_id))
        if not _row_is_fresh(feed_row, now_ts, scanner_ts):
            _log_skip(db, now, params, {"event_id": str(event_id), "signal_key": str(key),
                                        "reason": _stale_reason(feed_row)})
            continue
        # H-21: budget dei ritentativi dopo un rifiuto dell'exchange
        blocked_place = place_allowed(db, now, params, event_id, key)
        if blocked_place:
            if blocked_place == "place_exhausted":
                _log_skip(db, now, params, {"event_id": str(event_id),
                                            "signal_key": str(key),
                                            "reason": blocked_place})
            continue
        if max_open and (open_n_s + _placed_per_modalita.get(mode_s, 0)) >= max_open:
            _log_skip(db, now, params, {"event_id": str(event_id), "signal_key": str(key),
                                       "reason": "max_open_trades"})
            # ⚠️ 15/09 — e lo si DICE anche in pagina, non solo nel registro
            # degli scarti: il trader guarda la Control Room, non i log.
            aperte_ora = open_n_s + _placed_per_modalita.get(mode_s, 0)
            _BLOCCO.update({
                "motivo": (f"tetto operazioni aperte raggiunto: {aperte_ora} "
                           f"su {max_open} in {mode_s}"),
                "tetto": int(max_open), "aperte": int(aperte_ora),
            })
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
            # CERT. 12/09 — due cose diverse avevano la STESSA etichetta. Con un
            # lato del book assente il rapporto non e' calcolabile e scrivere
            # "spread anomalo · rapporto n/d" dice al trader una cosa che non e'
            # stata misurata. Il motivo vero e' che meta' del book non c'e'.
            # CERT. 14/09 — ...ma diceva sempre "senza lato BACK anche quando a
            # mancare era il LAY. ``spread_ratio`` torna None in DUE casi, e
            # l'etichetta ne nominava uno solo: su un leader a 1,01-1,02 e'
            # normale che nessuno offra di bancare, e il messaggio accusava il
            # lato sbagliato proprio nel caso centrale della strategia tennis.
            # Misurato su 142 scarti: 40 senza back, 4 senza lay, 98 con
            # entrambi e rapporto alto. Pochi, ma nominare il lato sbagliato
            # manda a cercare il guasto dove non c'e'.
            if ratio is not None:
                motivo = "spread_anomalo"
            elif (feed_prices or {}).get("back") in (None, 0):
                motivo = "book_senza_lato_back"
            else:
                motivo = "book_senza_lato_lay"
            _log_skip(db, now, params, {"event_id": str(event_id), "signal_key": str(key),
                                        "reason": motivo,
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
        if _risk_gate(db, now, params, risk_ctx_s,
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
            selection_name=_sig(s, "selection_name"), side=side, mode=mode_s,
            price=price, size=size, liability=liability, commission=commission,
            minute=_sig(s, "minute"), score=_sig(s, "score"),
            origin="auto", signal_key=str(key),
            meta={"variant": variant, "headline": _sig(s, "headline"),
                  "checks": _sig(s, "checks"),
                  "first_seen_ts": _sig(s, "first_seen_ts"),
                  # CERT. 14/09 — LA CATENA DEI TEMPI SULL'APERTURA.
                  # La condizione dell'utente e' «la latenza dai dati di Betfair
                  # alle decisioni del bot»: quella si misura DOVE LA DECISIONE
                  # NASCE, cioe' qui. L'avevo messa solo sulle chiusure, dove
                  # serve per un'altra cosa (il tempo fra la proposta e la firma
                  # dell'utente), e sull'entrata non restava un solo istante.
                  #   t0 = quando Betfair ha cambiato il prezzo
                  #   t1 = quando il feed ha scritto la riga
                  #   t2 = quando il bot l'ha letta
                  #   t3 = adesso: la decisione e' presa e si sta piazzando
                  **_catena_dei_tempi(feed_row, now),
                  # CERT. 13/09 — CARTELLINI ROSSI AL MOMENTO DELL'INGRESSO.
                  # Le uscite usavano come base la PRIMA osservazione utile del
                  # tracciamento: se il feed iniziava a pubblicare i rossi dopo
                  # l'apertura, un rosso preso nel frattempo finiva nella base e
                  # la regola "rosso alla favorita -> esci" non scattava mai.
                  **_rossi_al_piazzamento(feed_row)},
        )
        try:
            trade_id = db.insert_trade(row)  # RISERVA: l'unique index fa da lock
        except Exception as ex:  # noqa: BLE001 — conflitto = già riservato altrove
            _log_skip(db, now, params, {"event_id": str(event_id), "signal_key": str(key),
                                       "reason": "already_reserved", "err": str(ex)[:120]})
            traded_s.add((str(event_id), str(key)))
            continue
        if not trade_id:
            continue
        traded_s.add((str(event_id), str(key)))
        _risk_commit(risk_ctx_s, {**row, "id": trade_id})
        out = _execute(db=db, market=market, trade_id=trade_id, row=row, params=params,
                       now=now, best_size=avail, ladder=(), feed_prices=feed_prices)
        if out.status != "error":
            placed += 1
            _placed_per_modalita[mode_s] = _placed_per_modalita.get(mode_s, 0) + 1
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
                          risk_ctx: Optional[dict] = None,
                          scanner_ts: Optional[float] = None,
                          scanner_ts_known: bool = False) -> dict[str, int]:
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
    # 12/09: l'heartbeat dello scanner si legge UNA volta per ciclo e si passa a
    # tutte le partite (prima ogni _auto_trade_opps/_auto_trade_combos faceva la
    # sua SELECT: con 100 in-play erano 100 letture ogni 2 s).
    if not scanner_ts_known:
        scanner_ts = _scanner_ts(db, now_ts)
        scanner_ts_known = True
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
                    sport="tennis", kind="tennis", risk_ctx=risk_ctx,
                    scanner_ts=scanner_ts, scanner_ts_known=scanner_ts_known)
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
                rows_by_event=rows_by_event or {}, risk_ctx=risk_ctx,
                scanner_ts=scanner_ts, scanner_ts_known=scanner_ts_known)
        if kinds.get("combo") and combos:
            out["traded"] += _auto_trade_combos(
                db=db, market=market, payload=payload, event_id=event_id, combos=combos,
                params=params, mode=mode, now=now, rows_by_event=rows_by_event or {},
                risk_ctx=risk_ctx,
                scanner_ts=scanner_ts, scanner_ts_known=scanner_ts_known)
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
                     risk_ctx: Optional[dict] = None,
                     scanner_ts: Optional[float] = None,
                     scanner_ts_known: bool = False) -> int:
    """Tratta le opportunità che superano confidenza+edge minimi (strategia
    'model', tipo in ``meta.kind``; tennis: stake ``risk.model_stake``).
    DISATTIVO per default: si accende solo da parametri. Gate ``risk`` prima
    della riserva. 12/09: riga del feed FRESCA obbligatoria."""
    min_conf = float(params.get("opps_min_confidence") or 0.0)
    min_edge = float(params.get("opps_min_edge") or 0.0)
    stake = float(params.get("opps_stake") or 0.0) if kind == "model" \
        else float(RK.risk_params(params).get("model_stake") or 0.0)
    cap = float(params.get("max_liability_per_trade") or 0.0)
    commission = float(params.get("commission_pct", 5.0)) / 100.0
    if stake <= 0:
        return 0
    if not scanner_ts_known:
        scanner_ts = _scanner_ts(db, now.timestamp())
    feed_row = (rows_by_event or {}).get(str(event_id))
    if not _row_is_fresh(feed_row, now.timestamp(), scanner_ts):
        _log_skip(db, now, params, {"event_id": event_id, "signal_key": f"{kind}:*",
                                    "reason": _stale_reason(feed_row)})
        return 0
    try:
        traded = set(_traded_keys(db, mode))
    except Exception:  # noqa: BLE001 — FAIL-CLOSED
        return 0
    if risk_ctx is None:
        risk_ctx = build_risk_ctx(db, now, params, mode=mode)
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
            side=side, mode=modalita_di_strategia("model", mode, params),
            price=price, size=stake, liability=liability,
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
                       now=now, best_size=avail, ladder=(),
                       feed_prices=_feed_prices_of(rows_by_event, event_id, row))
        if out.status != "error":
            n += 1
    return n


def _feed_prices_of(rows_by_event: Optional[dict], event_id: str,
                    row: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Prezzi della selezione della riga riservata dal feed (per il fill paper)."""
    try:
        return prices_from_row((rows_by_event or {}).get(str(event_id)),
                               market_type=str(row.get("market_type") or ""),
                               selection_id=int(row.get("selection_id") or 0),
                               market_id=row.get("market_id"))
    except (TypeError, ValueError):
        return None


def _row_is_fresh(row: Optional[dict[str, Any]], now_ts: float,
                  scanner_ts: Optional[float]) -> bool:
    """12/09: nessun piazzamento AUTOMATICO su una riga del feed non fresca
    (``exits.feed_is_fresh``: ≤ 20 s o scanner vivo, mai oltre 120 s). Il
    motore e i modelli non guardano ``updated_at``: con lo scanner fermo i
    segnali restavano 'attivi' e il paper riempiva a quote vecchie (live: FOK
    a vuoto). Riga assente = non fresca."""
    return isinstance(row, dict) and XE.feed_is_fresh(row, now_ts, scanner_ts)


def _stale_reason(row: Optional[dict[str, Any]]) -> str:
    """Motivo dello scarto per FRESCHEZZA, distinto per l'operatore: la partita
    NON e' nel feed (lo scanner non la sta seguendo) oppure c'e' ma le sue quote
    sono vecchie. Due guasti diversi, due interventi diversi."""
    return "feed_non_fresco" if isinstance(row, dict) else "feed_assente"


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


def _combo_market_type(legs: list, leg_stakes: list) -> str:
    """``market_type`` della gamba con la responsabilita' piu' grande.

    Serve al gate di rischio per valutare la CORRELAZIONE: due posizioni sullo
    stesso mercato si sommano per intero, su mercati diversi pesano meno. Con
    l'etichetta "COMBO" nessuna posizione risultava mai correlata."""
    peggiore, mt = -1.0, ""
    for leg, stake in zip(legs or [], leg_stakes or []):
        if not isinstance(leg, dict):
            continue
        try:
            liab = X.liability_of(str(leg.get("side") or ""), float(stake),
                                  float(leg.get("price") or 0.0))
        except (TypeError, ValueError):
            continue
        if liab > peggiore:
            peggiore, mt = liab, str(leg.get("market_type") or "")
    return mt or "COMBO"


def _auto_trade_combos(*, db, market, payload: dict, event_id: str, combos: list,
                       params: dict, mode: str, now: datetime, rows_by_event: dict,
                       risk_ctx: Optional[dict] = None,
                       scanner_ts: Optional[float] = None,
                       scanner_ts_known: bool = False) -> int:
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
    # CERT. 13/09 — come per le aperture singole: il pavimento e' quello
    # ASSOLUTO dell'exchange, non il minimo di giurisdizione. Una gamba da
    # 1,20 EUR e' piazzabile col place-and-trim, quindi non deve piu' far
    # scartare l'intera combo.
    min_stake = X.ABS_MIN_SIZE
    if stake <= 0:
        return 0
    if not scanner_ts_known:
        scanner_ts = _scanner_ts(db, now.timestamp())
    feed_row = (rows_by_event or {}).get(str(event_id))
    if not _row_is_fresh(feed_row, now.timestamp(), scanner_ts):
        _log_skip(db, now, params, {"event_id": event_id, "signal_key": "combo:*",
                                    "reason": _stale_reason(feed_row)})
        return 0
    try:
        traded = set(_traded_keys(db, mode))
    except Exception:  # noqa: BLE001
        return 0
    if risk_ctx is None:
        risk_ctx = build_risk_ctx(db, now, params, mode=mode)
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
        # CERTIFICAZIONE 12/09 — SI ESEGUONO GLI STAKE VERIFICATI.
        # Prima la gamba veniva ricalcolata da ``stake_ratio`` e ri-arrotondata
        # al centesimo: su una quota alta mezzo centesimo vale piu' del profitto
        # bloccato, quindi il lock CERTIFICATO da combos.py non era quello
        # eseguito e il "rischio zero" poteva uscire negativo. Ora si parte
        # dagli stake pubblicati (gia' verificati anche contro il ri-arrotondamento)
        # e li si scala sul totale voluto.
        # ``book_supports_min`` = il book regge la combinazione al totale MINIMO.
        # Se non lo regge NESSUNO stake la rende intera: si salta. Se invece lo
        # regge, si controlla soltanto che il totale che stiamo per usare superi
        # ``min_total_stake`` (il flag ``executable_whole`` riguarda gli stake
        # PUBBLICATI, che sono quasi sempre piu' bassi del nostro totale: usarlo
        # come veto scartava anche le combinazioni buone).
        if c.get("book_supports_min") is False:
            _log_skip(db, now, params, {"event_id": event_id, "signal_key": keys[0],
                                        "reason": "combo_book_non_regge_il_minimo",
                                        "min_total_stake": c.get("min_total_stake")})
            continue
        want_total = round(float(stake) * len(legs), 2)
        min_total = _f(c.get("min_total_stake"), 0.0)
        if min_total > 0 and want_total + 1e-9 < min_total:
            _log_skip(db, now, params, {"event_id": event_id, "signal_key": keys[0],
                                        "reason": "combo_totale_sotto_minimo",
                                        "size": want_total, "min_stake": min_total})
            continue
        base_total = _f(c.get("total_stake"), 0.0)
        published = [_f(l.get("stake"), 0.0) for l in legs]
        if base_total > 0 and all(s > 0 for s in published):
            scale = want_total / base_total
            leg_stakes = [round(s * scale, 2) for s in published]
        else:   # combo senza stake pubblicati (contratto vecchio): ripiego sui ratio
            ratios = [_f(l.get("stake_ratio"), 0.0) for l in legs]
            if any(r <= 0 for r in ratios) or abs(sum(ratios) - 1.0) > 0.05:
                ratios = [1.0 / len(legs)] * len(legs)
            leg_stakes = [round(want_total * r, 2) for r in ratios]
        for leg, key, leg_stake in zip(legs, keys, leg_stakes):
            side = str(leg.get("side") or "").lower()
            try:
                price = float(leg.get("price"))
                sid = int(leg.get("selection_id"))
            except (TypeError, ValueError):
                ok = False
                break
            if side not in ("back", "lay") or price <= 1.0 or not leg.get("market_id")                     or leg_stake <= 0:
                ok = False
                break
            # Una gamba non piazzabile fa fallire _execute DOPO che le altre
            # sono gia' state piazzate -> combo rotta e posizione nuda da
            # svolgere. "Tutte o nessuna" si decide PRIMA della riserva, non
            # davanti al rifiuto dell'exchange. Dal 13/09 la soglia e' il
            # pavimento assoluto (0,01 EUR): sotto il minimo di giurisdizione
            # ci pensa il place-and-trim.
            if leg_stake < min_stake - 1e-9:
                _log_skip(db, now, params, {"event_id": event_id, "signal_key": key,
                                            "reason": "combo_gamba_sotto_minimo",
                                            "size": leg_stake, "min_stake": min_stake})
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
                selection_name=leg.get("selection_name"), side=side,
                mode=modalita_di_strategia("model", mode, params), price=price,
                size=leg_stake, liability=liab, commission=commission, minute=payload.get("minute"),
                score=_score_of(payload, "calcio"), origin="auto", signal_key=key,
                meta={**_model_meta(leg, "combo", side), "combo_id": cid,
                      "combo_legs": len(legs), "combo_rationale": c.get("rationale")}))
        if not ok:
            continue
        # CERT. 13/09 — il gate di rischio deve vedere il mercato VERO delle
        # gambe, non l'etichetta "COMBO". ``risk.event_exposure`` confronta
        # ``market_type`` per decidere se una posizione e' CORRELATA (stesso
        # mercato = pesa 100%) o no (pesa ``correlated_cap``, 0,7). Nessuna
        # posizione ha mai ``market_type == "COMBO"``, quindi TUTTE risultavano
        # non correlate e pesavano il 70%: con un cap per evento di 150 EUR si
        # arrivava a ~179 EUR reali sullo stesso mercato, cioe' il 19% oltre.
        # Si usa il mercato della gamba piu' pesante: e' quello che determina
        # davvero la correlazione dell'esposizione.
        mt_combo = _combo_market_type(legs, leg_stakes)
        if _risk_gate(db, now, params, risk_ctx,
                      {"event_id": event_id, "market_type": mt_combo,
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
                           now=now, best_size=row.get("size"), ladder=(),
                           feed_prices=_feed_prices_of(rows_by_event, event_id, row))
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
                      risk_ctx: Optional[dict] = None,
                      scanner_ts: Optional[float] = None,
                      scanner_ts_known: bool = False) -> dict[str, int]:
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
        # 12/09: il CECCHINO non spara su quote vecchie. Il gate ``odds_ts_ms``
        # non basta: al primo giro dopo un riavvio ``seen_ts`` e' vuoto e una
        # riga ferma da minuti verrebbe valutata come nuova. Stessa regola dei
        # segnali/opportunita'/combo (``_row_is_fresh``).
        if not scanner_ts_known:
            scanner_ts = _scanner_ts(db, now_ts)
            scanner_ts_known = True
        if not _row_is_fresh(row, now_ts, scanner_ts):
            _log_skip(db, now, params, {"event_id": event_id, "signal_key": "anomaly:*",
                                        "reason": _stale_reason(row)})
            continue
        if traded is None:
            try:
                traded = set(_traded_keys(db, mode))
            except Exception:  # noqa: BLE001 — FAIL-CLOSED
                return out
        if risk_ctx is None:
            risk_ctx = build_risk_ctx(db, now, params, mode=mode)
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
            # NB: ``res_row`` (riserva), non ``row`` (riga del FEED di questa
            # partita): schiacciarla qui dentro renderebbe cieco ogni controllo
            # sul feed a valle del ciclo delle anomalie.
            res_row = _reserve_row(
                event_id=event_id, event_name=payload.get("event_name"), sport="calcio",
                strategy="model", market_id=mid, market_type=mt, selection_id=sid,
                selection_name=o.get("selection_name"), side=side,
                mode=modalita_di_strategia("model", mode, params), price=price,
                size=stake, liability=liability, commission=commission,
                minute=payload.get("minute"), score=_score_of(payload, "calcio"),
                origin="auto", signal_key=key,
                meta={**_model_meta(o, "anomaly", side), "sniper": True,
                      "anomaly_type": o.get("anomaly_type") or o.get("type")})
            try:
                trade_id = db.insert_trade(res_row)
            except Exception:  # noqa: BLE001
                dedupe[dkey] = now_ts
                continue
            if not trade_id:
                continue
            dedupe[dkey] = now_ts
            traded.add((event_id, key))
            _risk_commit(risk_ctx, {**res_row, "id": trade_id})
            res = _execute(db=db, market=market, trade_id=trade_id, row=res_row, params=params,
                           now=now, best_size=o.get("size_available"), ladder=(),
                           feed_prices=_feed_prices_of(rows_by_event, event_id, res_row))
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
# Ultimo ``safe_strategy_control`` letto con successo. Serve a far girare le
# fasi di PROTEZIONE (riconciliazione, settlement, uscite) anche quando il DB non
# risponde: senza, un'indisponibilita' di Supabase lasciava le posizioni aperte
# senza nessuno che le guardasse.
_LAST_CONTROL: dict[str, Any] = {}
#: Posizioni aperte viste dall'ultimo ciclo. Serve SOLO a decidere se vale la
#: pena sbirciare la coda mentre si aspetta: a banco vuoto non c'e' niente da
#: chiudere, quindi non parte nessuna query in piu'.
_APERTE: dict[str, int] = {"n": 0}

# ⚠️ 15/09 — PERCHE' IL BOT NON APRE, scritto dove il trader lo legge.
# Un bot acceso che non piazza e non dice perche' e' indistinguibile da un bot
# rotto: e' successo con Mike, fermato da un tetto pieno senza che in pagina ci
# fosse una parola. Qui si tiene il motivo dell'ULTIMO giro, e le statistiche lo
# pubblicano. Non decide niente: serve solo a dirlo.
_BLOCCO: dict[str, Any] = {"motivo": None, "tetto": None, "aperte": None}


def _cadenza_battito(params: Optional[dict]) -> float:
    """Ogni QUANTI SECONDI, nel caso peggiore, questo servizio batte.

    ⚠️ 15/09 — la pagina giudicava la vitalita' dei bot con una costante scritta
    nel frontend. Era una SECONDA VERITA': se qui il passo si allarga, il
    frontend non lo sa e continua a misurare col metro vecchio — o chiama morto
    un bot vivo, o (peggio) chiama vivo un bot morto. La cadenza la dichiara
    CHI BATTE.

    Safe scrive stato e battito a ogni giro, quindi la cadenza e' il passo del
    ciclo: ``poll_interval_s``.
    """
    try:
        v = float((params or {}).get("poll_interval_s") or 2.0)
    except (TypeError, ValueError):
        v = 2.0
    # un passo nullo o negativo e' un valore ROTTO, non un passo velocissimo:
    # si torna a quello di serie, non al pavimento (dichiarare 1 s per un ciclo
    # che gira ogni 2 farebbe lampeggiare «lento» a ogni giro regolare).
    if v <= 0.0:
        v = 2.0
    return round(max(1.0, v), 1)
# Oltre questo tempo l'ultimo control noto non e' piu' una base accettabile:
# i parametri possono essere cambiati (soglie di uscita, commissione, tentativi)
# proprio perche' l'utente stava reagendo a qualcosa. Si continua comunque a
# proteggere le posizioni, ma lo si DICE, forte, una volta al minuto.
_CONTROL_CACHE_MAX_AGE_S = 600.0


def run_once(*, db=_real_db, market=_real_market, engine=None, opp_model=None,
             opp_mod: Any = None, engine_mod: Any = None,
             now: Optional[datetime] = None,
             opps_state: Optional[dict] = None,
             extra_mods: Optional[dict] = None) -> dict[str, Any]:
    now = now or _now()
    # CERT. 13/09 — il control illeggibile NON deve piu' portarsi via l'intero
    # ciclo. Prima si usciva subito, quindi con il DB in difficolta' non giravano
    # nemmeno ``reconcile_pending``, ``settle_open`` e ``process_exits``: le
    # posizioni APERTE restavano senza uscite e senza settlement per tutta la
    # durata del disservizio. E' l'opposto della regola dichiarata del modulo
    # ("SEMPRE, anche a bot fermo: mai posizioni nude").
    # Adesso si riparte dall'ULTIMO control noto e si degrada in sicurezza: le
    # fasi di PROTEZIONE girano, i NUOVI INGRESSI no (``unavailable`` nel
    # contesto di rischio li blocca comunque, perche' i cap non sono verificabili).
    control_degradato = False
    try:
        control = db.read_control()
    except Exception as ex:  # noqa: BLE001
        control = _LAST_CONTROL.get("value")
        if control is None:
            logger.warning("[safe.bot] read_control KO e nessun control in cache: %s",
                           str(ex)[:160])
            return {"skipped": "control_unreadable"}
        control_degradato = True
        eta = now.timestamp() - float(_LAST_CONTROL.get("ts") or 0.0)
        logger.warning("[safe.bot] read_control KO (%s): ciclo in PROTEZIONE con "
                       "l'ultimo stato noto di %.0fs fa — niente nuovi ingressi",
                       str(ex)[:120], eta)
        if eta > _CONTROL_CACHE_MAX_AGE_S:
            _log(db, "error", {"reason": "control_illeggibile_da_troppo", "critical": True,
                               "eta_s": round(eta, 1), "err": str(ex)[:160],
                               "effetto": "si protegge con parametri vecchi di "
                                          f"{int(eta // 60)} minuti: verificare il DB"})
    if control is None:
        return {"skipped": "no_control"}
    if not control_degradato:
        _LAST_CONTROL["value"] = dict(control)
        _LAST_CONTROL["ts"] = now.timestamp()
    status = str(control.get("status") or "idle")
    mode = str(control.get("mode") or "paper")
    if mode not in ("paper", "live"):
        mode = "paper"
    set_log_mode(mode)   # ogni riga di attivita' di questo ciclo nasce etichettata
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
    # CERT. 14/09 — t2 DELLA CATENA DEI TEMPI: l'istante in cui il bot ha in
    # mano la riga. Fra t1 (il feed l'ha scritta) e t2 c'e' il ritardo del
    # database piu' la cadenza del ciclo, che e' un pezzo di latenza invisibile
    # a chiunque guardi solo l'eta' delle quote.
    _LETTURA_FEED["ms"] = round(time.time() * 1000.0, 1)
    rows_by_event = {str(r.get("event_id")): r for r in rows if r.get("event_id")}
    # nomi delle partite per l'ATTIVITA' (cert. 12/09): il feed ce li ha, i log
    # no — senza questo il trader legge "NON ENTRATO 36050104" e non sa di che
    # partita si parli. Costo: nessuna lettura in piu'.
    remember_event_names(rows)

    # (a) coda flumine — SEMPRE (anche a bot fermo: mai posizioni nude)
    n_polled = poll_flumine(db=db, params=params, now=now, market=market)
    # (a-bis) pending SENZA marker flumine (esito REST ignoto) → stato reale Betfair
    n_reconciled = reconcile_pending(market=market, db=db, now=now)

    # (a-ter) CORSIA PREFERENZIALE DELLE CHIUSURE — cert. 14/09, corretta 15/09.
    #
    # Quando il trader clicca «chiudi», il prezzo che ha visto sulla scheda vive
    # sul mercato, non sul nostro orologio: ogni decimo speso qui e' un decimo
    # in cui quel prezzo puo' andarsene. Prima questa fase stava al punto (c),
    # dopo settlement, contesto di rischio, cecita' del feed e combo rotte: 4,2
    # secondi misurati sulla richiesta #10, tutti nostri e tutti invisibili.
    #
    # ⚠️ MA NON PUO' STARE PRIMA DI (a) E (a-bis), e la review l'ha trovato:
    # `poll_flumine` e `reconcile_pending` sono esattamente le fasi che rendono
    # VERO lo stato di una riga. Messa davanti a loro, questa corsia agiva su
    # righe stantie, e su soldi veri:
    #   · `cancel` cancellava una riserva il cui ordine era GIA' a mercato —
    #     `_request_cancel` si difende guardando `bet_id`/`flumine_client_ref`,
    #     ma quei campi li scrive proprio il poll che non era ancora girato:
    #     la riga spariva dal database mentre l'ordine viveva su Betfair;
    #   · `cashout` su una riga appena abbinata la vedeva ancora 'pending' e
    #     rifiutava IN MODO TERMINALE con un motivo falso («riserva non ancora
    #     abbinata»), buttando via l'approvazione del trader.
    #
    # Le due fasi che la precedono sono anche le piu' brevi quando non c'e'
    # niente da riconciliare, che e' il caso normale. Il guadagno resta quasi
    # intero; la correttezza torna piena.
    #
    # Le APERTURE restano al punto (c), dove hanno il contesto di rischio
    # condiviso che serve ai cap.
    n_req_veloci = process_requests(db=db, market=market, rows_by_event=rows_by_event,
                                    params=params, now=now, risk_ctx=None,
                                    control_mode=mode, degradato=control_degradato,
                                    solo_chiusure=True)
    # (b) settlement — SEMPRE
    n_settled = settle_open(params=params, market=market, db=db, now=now,
                            rows_by_event=rows_by_event)

    # budget dei ritentativi di piazzamento: recupero dopo un riavvio (H-21)
    seed_place_attempts(db, now.timestamp())

    # contesto di RISCHIO del ciclo (una lettura: posizioni vive + aggregati)
    risk_ctx = build_risk_ctx(db, now, params, mode=mode)
    if control_degradato:
        # stato del bot non verificato in questo ciclo (control illeggibile):
        # si proteggono le posizioni esistenti — riconciliazione, settlement,
        # uscite — ma non si apre NIENTE di nuovo.
        risk_ctx = {**risk_ctx, "unavailable": True}

    # (b-bis) H-18: posizioni vive senza riga nel feed = cecità, mai silenzio
    # ``open_all``: la cecita' del feed e' un allarme su QUALUNQUE posizione viva,
    # non solo su quelle della modalita' attiva (review 13/09).
    n_blind = check_feed_blind(db, risk_ctx.get("open_all") or [], rows_by_event, now)

    # (b-ter) H6: gambe di COMBO rotte il cui fill è appena stato confermato
    # dalla coda → si svolgono subito (mai una posizione nuda per un ciclo)
    n_unwound = unwind_incomplete_combos(
        db=db, market=market, rows_by_event=rows_by_event, params=params, now=now,
        open_rows=risk_ctx.get("open_all") if not risk_ctx.get("unavailable") else None)

    # (c) richieste della UI — SEMPRE
    n_requests = n_req_veloci + process_requests(
        db=db, market=market, rows_by_event=rows_by_event,
        params=params, now=now, risk_ctx=risk_ctx,
        control_mode=mode, degradato=control_degradato)

    # (c-bis) uscite automatiche — SEMPRE (posizioni già aperte), prima dei nuovi ingressi
    n_exits = process_exits(db=db, market=market, rows_by_event=rows_by_event,
                            params=params, now=now, opp_mod=opp_mod,
                            opps_state=opps_state,
                            # M1: le posizioni vive sono già state lette per il
                            # contesto di rischio: una SELECT, non tre.
                            # CERT. 13/09 (review) — qui va ``open_all``, NON la
                            # lista filtrata per modalita': una posizione LIVE
                            # aperta deve continuare a essere gestita anche
                            # quando il servizio e' passato a PAPER. Con la
                            # lista filtrata smetteva di avere uscite e
                            # arrivava al settlement con la responsabilita'
                            # intera — un difetto peggiore di quello che il
                            # filtro voleva chiudere.
                            open_rows=risk_ctx.get("open_all")
                            if not risk_ctx.get("unavailable") else None)

    if status == "stopping":
        try:
            db.set_control(status="stopped", stopped_at=now.isoformat())
            _log(db, "stop", {})
        except Exception:  # noqa: BLE001
            pass
        status = "stopped"

    # (d) segnali automatici — SOLO se in esecuzione E con lo stato VERIFICATO.
    # CERT. 13/09: in un ciclo DEGRADATO (control illeggibile, si lavora con
    # l'ultimo stato noto) non si apre NIENTE di nuovo, nemmeno se la copia in
    # cache diceva "running": l'utente potrebbe aver premuto STOP o cambiato i
    # parametri proprio mentre il DB non risponde, e noi non lo sapremmo. Le
    # fasi di protezione (riconciliazione, settlement, uscite) girano comunque:
    # una posizione aperta non deve mai restare senza nessuno che la guardi.
    running = status == "running" and not control_degradato
    n_placed = n_signals = 0
    if running:
        n_placed, n_signals = scan_and_place(db=db, market=market, engine=engine,
                                             rows=rows, params=params, mode=mode,
                                             now=now, risk_ctx=risk_ctx)

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
            # stessa modalita' del ciclo: i numeri a schermo non mescolano mai
            # posizioni finte e vere (13/09)
            agg = db.aggregates(mode=mode)
        except TypeError:      # accessor vecchio senza il parametro
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
        # ── QUELLO CHE IL BOT DECIDE, SCRITTO (15/09) ────────────────────────
        # Un trader non deve dedurre perché il bot non apre: deve leggerlo.
        "motivo_blocco": _BLOCCO.get("motivo"),
        "tetto_partite": _BLOCCO.get("tetto"),
        "partite_esposte": _BLOCCO.get("aperte"),
        # con che passo si ripete questo battito: la pagina deve giudicare la
        # vitalità con la cadenza VERA del servizio, non con una costante
        # scritta nel frontend (che sarebbe una seconda verità).
        "cadenza_battito_s": _cadenza_battito(params),
        # FERMARE toglie le APERTURE, non le uscite: coperture, cash out e
        # regolamento continuano. Il pulsante deve dirlo, o promette una cosa
        # che non fa.
        "stop_ferma_solo_aperture": True,
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
    # LO SCHERMO PRIMA DEL DISCO (14/09). Spingere sul socket locale non costa
    # un byte di IO, quindi si fa SEMPRE e per primo: se la scrittura su
    # ``safe_strategy_control`` fallisse o fosse lenta, il trader vedrebbe
    # comunque i numeri di questo giro. La scrittura resta e resta obbligatoria:
    # il socket e' un'accelerazione, non una sostituzione.
    # Quante posizioni ci sono da chiudere: decide se l'attesa del prossimo
    # ciclo va sorvegliata (vedi ``_attesa_interrompibile``).
    #
    # ⚠️ REVIEW 15/09 — QUI C'ERA `stats["trades_open"]`, che viene da
    # ``aggregates(mode=mode)`` ed e' filtrato sulla MODALITA' DEL SERVIZIO.
    # Con il servizio in paper e posizioni LIVE ancora aperte — la situazione
    # del 14/09 dopo che la modalita' e' tornata a paper — quel numero valeva
    # zero e la corsia veloce si spegneva proprio sui soldi veri: il clic del
    # trader sull'unica posizione che rischia denaro aspettava il ciclo pieno.
    # Si contano TUTTE le posizioni vive, in qualunque modalita'.
    _aperte_tutte = risk_ctx.get("open_all") if isinstance(risk_ctx, dict) else None
    _APERTE["n"] = (len(_aperte_tutte) if isinstance(_aperte_tutte, list)
                    else int(stats.get("trades_open") or 0))
    _pubblica_stato(stats, now.isoformat())
    try:
        db.set_control(stats=stats, heartbeat_at=now.isoformat())
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.bot] set_control KO: %s", str(ex)[:160])
    return {"status": status, "placed": n_placed, "settled": n_settled,
            "requests": n_requests, "polled": n_polled, "reconciled": n_reconciled,
            "exits": n_exits, "signals": n_signals, "opportunities": opps,
            "anomalies": anomalies, "blind": n_blind, "unwound": n_unwound,
            "stats": stats}


# MODALITA' del ciclo in corso, per etichettare l'attivita' nel punto UNICO di
# scrittura. CERT. 13/09: solo 4 dei ~63 punti di log portavano ``mode``; tutti
# gli altri (scarti, blocchi di rischio, attese, uscite trattenute, errori di
# settlement, feed cieco) finivano nello storico senza dire se riguardavano
# soldi veri o finti — e a posteriori era impossibile verificare alcunche'.
_LOG_MODE: dict[str, str] = {"value": ""}


_CICLO_IN_ERRORE = {"value": False}


def _segnala_errore_di_ciclo(ex: Exception) -> None:
    """Scrive l'errore sul control, una sola volta finche' dura."""
    if _CICLO_IN_ERRORE["value"]:
        return
    try:
        _real_db.set_control(error=f"{type(ex).__name__}: {str(ex)[:180]}")
        _CICLO_IN_ERRORE["value"] = True
    except Exception:  # noqa: BLE001 — se non si puo' scrivere, pazienza: c'e' il log
        pass


def _pulisci_errore_di_ciclo() -> None:
    """Primo ciclo riuscito dopo un errore: si toglie la bandiera."""
    if not _CICLO_IN_ERRORE["value"]:
        return
    try:
        _real_db.set_control(error=None)
    except Exception:  # noqa: BLE001
        return
    _CICLO_IN_ERRORE["value"] = False


def set_log_mode(mode: str) -> None:
    """Dichiara la modalita' del ciclo: la usa ``_log`` come etichetta."""
    m = str(mode or "").strip().lower()
    _LOG_MODE["value"] = m if m in ("paper", "live") else ""


def _log(db, kind: str, payload: dict[str, Any]) -> None:
    # CERTIFICAZIONE 12/09 — ogni riga di attivita' porta il NOME della partita
    # quando lo conosciamo (vedi ``remember_event_names``): nella scheda
    # Attivita' il trader deve leggere "Daegu Fc - Yongin FC", non "36050104".
    # Qui, nel punto unico di scrittura, cosi' vale per TUTTI i kind.
    try:
        if isinstance(payload, dict) and payload.get("event_id") and not payload.get("event_name"):
            nm = event_name_for(payload.get("event_id"))
            if nm:
                payload = {**payload, "event_name": nm}
        # etichetta PAPER/LIVE su OGNI riga: chi scrive un payload con il suo
        # ``mode`` (place, exit, flumine_enqueue) resta padrone del proprio.
        if isinstance(payload, dict) and not payload.get("mode") and _LOG_MODE["value"]:
            payload = {**payload, "mode": _LOG_MODE["value"]}
    except Exception:  # noqa: BLE001 — mai per un'etichetta
        pass
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


# ===========================================================================
# IL CANALE LOCALE VERSO LO SCHERMO (14/09/2026)
# ===========================================================================
# Porta 47335, accanto a 47331 (calcio), 47332 (tennis), 47333 (Mike) e 47334
# (Omega). Un canale PER BOT e non uno condiviso: quello del runner accetta
# comandi ordine, e non va allargato per farci passare dati di visualizzazione.
_PORTA_CANALE = 47335


def _avvia_canale() -> None:
    """Accende il canale locale. Non solleva MAI: senza canale il bot lavora."""
    import os

    from Betfair.stream import local_channel as _lc

    try:
        porta = int((os.environ.get("SAFE_LOCAL_WS_PORT") or "").strip() or _PORTA_CANALE)
    except ValueError:
        porta = _PORTA_CANALE
    try:
        ch = _lc.start_channel(porta, "safe", solo_lettura=True)
        if ch is None:
            logger.warning("[safe.bot] canale locale NON attivo su %d (porta occupata?): "
                           "la pagina continuera' a leggere dal database.", porta)
    except Exception as ex:  # noqa: BLE001 — il canale e' opzionale, sempre
        logger.warning("[safe.bot] canale locale KO: %s", str(ex)[:160])


def _pubblica_stato(stats: dict, now_iso: str) -> None:
    """Spinge i numeri di testata sullo schermo. No-op senza app collegata.

    E' lo STESSO oggetto che va in ``set_control``: schermo e database non
    possono divergere perche' non sono due calcoli, e' uno solo.
    """
    from Betfair.stream import local_channel as _lc

    try:
        _lc.publish("safe_stato", {"stats": stats, "last_cycle": now_iso})
    except Exception as ex:  # noqa: BLE001 — mostrare non deve mai fermare il bot
        logger.debug("[safe.bot] publish stato KO: %s", str(ex)[:120])


#: Ogni quanto si sbircia la coda mentre si aspetta il prossimo ciclo.
#: Vale SOLO quando ci sono posizioni aperte, cioe' quando un clic e'
#: davvero possibile: a banco vuoto non parte nemmeno una query in piu'.
_SBIRCIATA_S = 0.25
#: L'ultima richiesta per cui si e' gia' anticipato il ciclo. Senza questo, una
#: richiesta che per qualunque motivo non riuscisse a uscire dallo stato
#: 'pending' farebbe svegliare il bot a ogni sbirciata: un ciclo completo ogni
#: 250 ms contro il database. E' la forma esatta del guasto del 13/09 (budget
#: IO esaurito), e va resa impossibile, non improbabile.
_SVEGLIA_FATTA: dict[str, int] = {"req_id": 0}


def _attesa_interrompibile(interval: float, aperte: int) -> bool:
    """Dorme fino a ``interval``, ma si sveglia appena arriva una richiesta.

    Il ciclo a 2 secondi e' giusto per il lavoro di fondo e va lasciato com'e':
    e' la cadenza con cui il DB regge (13/09, budget IO esaurito). Ma un clic
    del trader non e' lavoro di fondo — e farlo aspettare in media un secondo
    prima ancora di COMINCIARE e' un secondo regalato al mercato.

    Con almeno una posizione aperta si sbircia la coda ogni 250 ms con la query
    piu' piccola possibile (una riga, un indice) e si rientra subito nel ciclo.
    Senza posizioni aperte non c'e' niente da chiudere, quindi si dorme e basta:
    zero letture in piu'. Ritorna True se si e' usciti in anticipo.
    """
    if aperte <= 0 or interval <= _SBIRCIATA_S:
        time.sleep(max(interval, 0.0))
        return False
    scaduta = time.monotonic() + interval
    while True:
        restante = scaduta - time.monotonic()
        if restante <= 0:
            return False
        time.sleep(min(_SBIRCIATA_S, restante))
        try:
            righe = _real_db.pending_requests(limit=1) or []
        except Exception as ex:  # noqa: BLE001 — sbirciare non deve mai fermare il bot
            # ⚠️ REVIEW 15/09 — QUI C'ERA `return False`, e accorciava l'attesa.
            # Uscire dal sonno fa ripartire SUBITO il ciclo completo: con il
            # database in difficolta' (che e' la ragione per cui la sbirciata
            # fallisce) si passava da un ciclo ogni 2 s a uno ogni 250 ms, cioe'
            # otto volte il carico proprio mentre il DB e' in ginocchio. E' il
            # guasto del 13/09 riprodotto dalla sua stessa difesa.
            # Adesso si smette di sbirciare e si finisce di dormire.
            logger.debug("[safe.bot] sbirciata coda KO, resto in attesa: %s", str(ex)[:120])
            restante = scaduta - time.monotonic()
            if restante > 0:
                time.sleep(restante)
            return False
        if not righe:
            continue
        rid = int(righe[0].get("id") or 0)
        if rid and rid == _SVEGLIA_FATTA["req_id"]:
            # gia' anticipato per questa richiesta e sta ancora li': il ciclo
            # normale se ne occupera'. Si dorme, non si martella.
            continue
        _SVEGLIA_FATTA["req_id"] = rid
        return True


def main() -> None:
    from Betfair.stream.single_instance import acquire_single_instance_lock

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    lock = acquire_single_instance_lock(_SINGLE_INSTANCE_PORT, "safe-bot")
    logger.info("[safe.bot] servizio avviato (lock %s)", _SINGLE_INSTANCE_PORT)
    _avvia_canale()
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
                    _real_db.log("error", {"reason": "cycle_exception", "err": str(ex)[:200],
                                           "critical": True})
                except Exception:  # noqa: BLE001
                    pass
                # CERT. 13/09 — lo si DICE anche sul control. La colonna ``error``
                # e lo stato 'error' esistono dallo schema iniziale e non venivano
                # scritti da nessuno: un ciclo che esplodeva a ripetizione lasciava
                # la dashboard con un tranquillo "in esecuzione". Chi guarda deve
                # vedere che il servizio non sta lavorando.
                _segnala_errore_di_ciclo(ex)
            else:
                _pulisci_errore_di_ciclo()
            # l'attesa si interrompe appena il trader clicca: il ciclo dopo
            # parte dalla corsia preferenziale delle chiusure.
            if _attesa_interrompibile(max(interval, 1.0), _APERTE.get("n", 0)):
                logger.info("[safe.bot] richiesta in coda: ciclo anticipato")
    finally:
        try:
            lock.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
