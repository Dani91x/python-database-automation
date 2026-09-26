# Prediction/today_predictions_backfill.py

from __future__ import annotations

import argparse
import logging
import sys
import json
import os
import random
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
import math
from typing import Any, Callable, Dict, List, Optional, Tuple, Set, TypeVar

import numpy as np
from scipy.stats import poisson

# ----------------------------------------------------------
# Ensure project root is on sys.path so absolute imports work
# even when running this file from the Prediction/ folder.
# ----------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api_client import APIFootballClient  # noqa: E402
from db_client import get_supabase_client  # noqa: E402
from logger import flush_api_log  # noqa: E402

# Logging (coerente con la codebase: fallback logging)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ==============================
# Helpers
# ==============================

def _parse_percent_to_float(value: Any) -> Optional[float]:
    """
    Converte "35%" -> 35.0
    Ritorna None se non convertibile.
    """
    if value is None:
        return None
    try:
        s = str(value).strip()
        if not s:
            return None
        s = s.replace("%", "").strip()
        if not s:
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def _safe_get(d: Any, path: List[str]) -> Any:
    """
    Safe get su dict annidati: se qualcosa manca ritorna None.
    """
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
        if cur is None:
            return None
    return cur


# ==============================
# Accesso DB resiliente (statement_timeout 57014 e affini)
# ==============================
#
# Il ruolo PostgREST ha statement_timeout = 8 s: su questa tabella (righe JSON da
# ~14 KB e molti indici) un upsert/update puo' essere abortito dal server con
# SQLSTATE 57014. Fino a oggi un solo 57014 sull'UPDATE delle odds risaliva fino
# a main() e uccideva l'INTERO run, lasciando senza predizioni tutte le fixture
# successive. Qui c'e' UN SOLO punto d'ingresso per le chiamate al DB:
#   - ritenta SOLO gli errori transitori (57014, PGRST002, 502/503/504, timeout e
#     errori di connessione HTTP), con backoff esponenziale + jitter;
#   - NON ritenta mai gli errori logici (violazioni di vincoli, 4xx di validazione):
#     rifallirebbero identici e mascherebbero il problema vero;
#   - non ingoia nulla: l'ultima eccezione risale SEMPRE al chiamante.

_T = TypeVar("_T")

# Codici (SQLSTATE / PostgREST / HTTP) considerati transitori.
_TRANSIENT_DB_CODES = frozenset({"57014", "PGRST002", "502", "503", "504"})

# Nomi di eccezioni httpx/urllib3 considerati transitori.
_TRANSIENT_EXC_NAMES = (
    "readtimeout",
    "readerror",
    "writetimeout",
    "connecttimeout",
    "connecterror",
    "connectionerror",
    "pooltimeout",
    "remoteprotocolerror",
)

# Marcatori testuali (minuscolo) di errori transitori.
_TRANSIENT_DB_MARKERS = (
    "statement timeout",
    "canceling statement due to",
    "pgrst002",
    "connection reset",
    "connection aborted",
    "server disconnected",
    "timed out",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
)

_MAX_CAUSE_DEPTH = 8  # difensivo: catene __cause__/__context__ cicliche

# Retry: 6 tentativi totali, backoff 1, 2, 4, 8, 16 s (tetto 20 s) con jitter +/-30%.
_DB_RETRY_ATTEMPTS = 6
# Sui blocchi multi-riga bastano meno tentativi: il recupero vero e' il
# dimezzamento del blocco (_DeferredWriter._upsert_rows), non l'insistere.
_DB_RETRY_ATTEMPTS_BATCH = 3
_DB_RETRY_BASE_DELAY = 1.0
_DB_RETRY_MAX_DELAY = 20.0

# FRENI del DB. Se il DB e' davvero in difficolta' il run non deve ne' restare
# appeso per ore ne' martellare il database con centinaia di richieste
# destinate a fallire. Scatta il primo dei tre che si esaurisce; quando uno
# scatta si smette di ritentare E di dimezzare i blocchi, ma NON si ingoia
# nulla: tutto finisce in _RUN_FAILURES e il processo esce != 0.
# FINESTRA SCORREVOLE (23/09, revisore A - P1): i tre freni misurano un
# periodo di guai CONTINUI. Ogni chiamata riuscita li azzera
# (_azzera_freno_dopo_successo): prima la scadenza di parete, armata al primo
# retry del processo, non veniva mai azzerata, e un solo 57014 al minuto 1
# spegneva i retry e il secondo giro per tutto il resto del run (41-82 min).
# PARACADUTE ASSOLUTO (23/09, rimando del coordinatore): la finestra
# scorrevole da sola lascia un buco. Un guasto persistente sulle sole odds,
# con le analisi che riescono, azzererebbe il freno a ogni fixture: 6
# tentativi (~31 s di attese) PER fixture per tutto il run. Il quarto freno
# conta le richieste fallite di TUTTO il processo e NON si azzera mai (ne'
# dopo un successo, ne' al secondo giro): solo all'avvio del processo
# (_reset_totale_processo). Scattato, vale come gli altri tre.
_DB_RETRY_BUDGET_S = 600.0        # somma delle attese dall'ultimo successo
_DB_RETRY_DEADLINE_S = 900.0      # PARETE dal primo retry dopo l'ultimo successo (15 minuti)
_DB_MAX_FAILED_REQUESTS = 60      # richieste fallite CONSECUTIVE (dall'ultimo successo)
_DB_MAX_FAILED_REQUESTS_TOTALE = 300  # richieste fallite TOTALI nel processo (50 fixture x 6)

_DB_RETRY_SPENT_S = 0.0
_DB_RETRY_DEADLINE_AT: Optional[float] = None
_DB_FAILED_REQUESTS = 0
_DB_FAILED_REQUESTS_TOTALE = 0


def _db_monotonic() -> float:
    """Orologio di parete monotono (isolato per poter essere sostituito nei test)."""
    return time.monotonic()


def _reset_retry_budget() -> None:
    """Azzera i tre freni (all'avvio, dopo ogni successo, al secondo giro)."""
    global _DB_RETRY_SPENT_S, _DB_RETRY_DEADLINE_AT, _DB_FAILED_REQUESTS  # noqa: PLW0603
    _DB_RETRY_SPENT_S = 0.0
    _DB_RETRY_DEADLINE_AT = None
    _DB_FAILED_REQUESTS = 0


def _reset_totale_processo() -> None:
    """Azzera il paracadute assoluto: SOLO all'avvio del processo (main)."""
    global _DB_FAILED_REQUESTS_TOTALE  # noqa: PLW0603
    _DB_FAILED_REQUESTS_TOTALE = 0


def _azzera_freno_dopo_successo() -> None:
    """Una chiamata al DB e' riuscita: la finestra di guai si chiude.

    Azzera scadenza di parete, attese spese e richieste fallite, cosi' un
    errore isolato piu' avanti nel run ha di nuovo i suoi retry.
    """
    _reset_retry_budget()


def _db_retry_exhausted() -> Optional[str]:
    """Motivo per cui non si deve piu' ritentare, oppure None se si puo'."""
    if _DB_FAILED_REQUESTS_TOTALE >= _DB_MAX_FAILED_REQUESTS_TOTALE:
        return ("richieste fallite totali nel processo >= %d (paracadute assoluto)"
                % _DB_MAX_FAILED_REQUESTS_TOTALE)
    if _DB_FAILED_REQUESTS >= _DB_MAX_FAILED_REQUESTS:
        return "limite di richieste fallite raggiunto (%d)" % _DB_MAX_FAILED_REQUESTS
    if _DB_RETRY_SPENT_S >= _DB_RETRY_BUDGET_S:
        return "budget di attesa esaurito (%.0fs)" % _DB_RETRY_BUDGET_S
    if _DB_RETRY_DEADLINE_AT is not None and _db_monotonic() >= _DB_RETRY_DEADLINE_AT:
        return "scadenza di parete superata (%.0fs)" % _DB_RETRY_DEADLINE_S
    return None


def _db_sleep(seconds: float) -> None:
    """Attesa tra due tentativi (isolata per poter essere sostituita nei test)."""
    time.sleep(seconds)


def _is_transient_db_error(exc: BaseException) -> bool:
    """True SOLO per gli errori DB/rete ritentabili (vedi elenco sopra).

    Percorre anche la catena delle cause: httpx incapsula spesso l'errore reale.
    """
    seen = 0
    current: Optional[BaseException] = exc
    while current is not None and seen < _MAX_CAUSE_DEPTH:
        code = getattr(current, "code", None)
        if code is not None and str(code).strip().upper() in _TRANSIENT_DB_CODES:
            return True

        status = getattr(getattr(current, "response", None), "status_code", None)
        if status in (502, 503, 504):
            return True

        if type(current).__name__.lower() in _TRANSIENT_EXC_NAMES:
            return True

        try:
            text = str(current).lower()
        except Exception:  # noqa: BLE001 - __str__ esotici
            text = ""
        if any(marker in text for marker in _TRANSIENT_DB_MARKERS):
            return True

        nxt = current.__cause__ if current.__cause__ is not None else current.__context__
        current = nxt if nxt is not current else None
        seen += 1
    return False


def _db_execute(
    fn: Callable[[], _T],
    *,
    what: str,
    attempts: Optional[int] = None,
) -> _T:
    """Esegue una chiamata al DB ritentando SOLO gli errori transitori.

    ``attempts=None`` legge _DB_RETRY_ATTEMPTS A RUNTIME, cosi' la costante
    resta regolabile (e falsificabile nei test). ``what`` serve solo al log.
    L'ultima eccezione viene ri-sollevata: decide il chiamante se registrarla
    in _RUN_FAILURES o lasciarla propagare.
    """
    global _DB_RETRY_SPENT_S, _DB_RETRY_DEADLINE_AT, _DB_FAILED_REQUESTS  # noqa: PLW0603
    global _DB_FAILED_REQUESTS_TOTALE  # noqa: PLW0603
    total = max(1, int(attempts if attempts is not None else _DB_RETRY_ATTEMPTS))
    for attempt in range(1, total + 1):
        try:
            risultato = fn()
        except Exception as exc:  # noqa: BLE001 - filtrato subito sotto
            _DB_FAILED_REQUESTS += 1
            _DB_FAILED_REQUESTS_TOTALE += 1   # paracadute: mai azzerato nel processo
            if attempt >= total or not _is_transient_db_error(exc):
                raise
            motivo = _db_retry_exhausted()
            if motivo is not None:
                logger.error("Freno DB attivo (%s): %s NON ritentato.", motivo, what)
                raise
            if _DB_RETRY_DEADLINE_AT is None:
                _DB_RETRY_DEADLINE_AT = _db_monotonic() + _DB_RETRY_DEADLINE_S
            delay = min(_DB_RETRY_MAX_DELAY, _DB_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
            delay *= 0.7 + random.random() * 0.6  # jitter +/-30%
            logger.warning(
                "DB transitorio su %s (tentativo %s/%s): %s - ritento tra %.1fs",
                what, attempt, total, str(exc)[:200], delay,
            )
            _DB_RETRY_SPENT_S += delay
            _db_sleep(delay)
        else:
            _azzera_freno_dopo_successo()
            return risultato
    raise RuntimeError("unreachable")  # pragma: no cover - difensivo


# ------------------------------------------------------------------
# Registro delle anomalie NON recuperate (nessun errore ingoiato in silenzio)
# ------------------------------------------------------------------
# Ci finisce tutto cio' che, dopo i retry, non e' stato possibile fare:
#   - "prediction(...)" / "odds" / "analisi" : scrittura persa;
#   - "coverage-read" / "coverage-read-odds" : copertura non leggibile, quindi
#     la fixture NON e' stata toccata (scrivere 'no_coverage' sarebbe FALSO);
#   - "analisi-calcolo" / "calibrazione"     : dato non prodotto o non calibrato.
# Niente di tutto cio' ferma il run: le altre fixture vengono comunque
# elaborate. A fine run il riepilogo elenca ogni voce e main() esce con codice
# != 0, cosi' il workflow e' rosso e l'anomalia e' visibile.

_RUN_FAILURES: List[Dict[str, Any]] = []

# Oltre questo numero di voci si smette di loggarle una per una (un DB giu'
# produrrebbe migliaia di righe identiche): resta il contatore, e il riepilogo
# finale stampa comunque TUTTI gli id.
_MAX_FAILURE_LOG_LINES = 50


def _reset_failures() -> None:
    """Azzera il registro (una volta per processo, all'avvio di main)."""
    _RUN_FAILURES.clear()


def _record_failure(
    fixture_id: Any,
    operation: str,
    exc: BaseException,
    payload: Optional[Dict[str, Any]] = None,
    manuale: bool = False,
) -> None:
    """Registra un'anomalia non recuperata e la rende visibile nel log.

    ``payload`` (opzionale) conserva la riga da riscrivere, cosi' il secondo
    giro di fine run puo' ritentarla (_retry_failed_post_ops).
    ``manuale`` marca le anomalie che un semplice rilancio NON recupera.
    """
    _RUN_FAILURES.append({
        "fixture_id": fixture_id,
        "operation": operation,
        "error": str(exc)[:500],
        "payload": payload,
        "manuale": bool(manuale),
    })
    quante = len(_RUN_FAILURES)
    if quante <= _MAX_FAILURE_LOG_LINES:
        logger.error(
            "ANOMALIA NON RECUPERATA fixture_id=%s operazione=%s: %s",
            fixture_id, operation, str(exc)[:500],
        )
        if quante == _MAX_FAILURE_LOG_LINES:
            logger.error(
                "... oltre %s anomalie: le successive non vengono piu' loggate una "
                "per una, l'elenco completo e' nel riepilogo finale.",
                _MAX_FAILURE_LOG_LINES,
            )
    elif quante % 100 == 0:
        logger.error("... anomalie accumulate finora: %s", quante)


def _log_failures_summary(target_date: str) -> int:
    """Stampa il riepilogo delle anomalie. Ritorna quante ne sono rimaste."""
    if not _RUN_FAILURES:
        return 0
    logger.error(
        "ANOMALIE NON RECUPERATE per %s: %s (dati MANCANTI o NON PRODOTTI)",
        target_date, len(_RUN_FAILURES),
    )
    for item in _RUN_FAILURES:
        logger.error(
            "   - fixture_id=%s operazione=%s errore=%s",
            item.get("fixture_id"), item.get("operation"), item.get("error"),
        )

    manuali = [v for v in _RUN_FAILURES if v.get("manuale")]
    if manuali:
        logger.error(
            "DA RECUPERARE A MANO (%s): la riga di prediction e' gia' scritta come "
            "status='ok', quindi il rilancio sulla stessa data le SALTA.",
            len(manuali),
        )
        for item in manuali:
            logger.error(
                "   - DA RECUPERARE A MANO: fixture_id=%s, operazione=%s",
                item.get("fixture_id"), item.get("operation"),
            )
    return len(_RUN_FAILURES)


def _retry_failed_post_ops() -> int:
    """Secondo giro sulle sole post_ops (odds/analisi) rimaste indietro.

    Serve perche' a quel punto la riga di prediction della fixture e' gia' su
    DB con status='ok' e ht_predictions valorizzato: il prefetch del RILANCIO
    la salterebbe per sempre, lasciando `raw_json_odds` NULL in eterno. Qui si
    ritenta una volta sola, con gli stessi retry e sotto gli stessi freni di
    _db_execute. Cio' che riesce ESCE dal registro; cio' che resta va nel
    riepilogo come "DA RECUPERARE A MANO". Ritorna quante ne ha recuperate.
    """
    ripetibili = [v for v in _RUN_FAILURES if v.get("payload")]
    if not ripetibili:
        return 0

    # Freno PROPRIO del secondo giro: non eredita quello del run (P1, 23/09).
    # Da qui in poi i tre freni contano solo i guai di questo giro.
    _reset_retry_budget()
    motivo = _db_retry_exhausted()
    if motivo is not None:
        logger.error(
            "Secondo giro sulle scritture post-prediction SALTATO (%s): "
            "%s voci restano da recuperare.", motivo, len(ripetibili),
        )
        return 0

    logger.info(
        "Secondo giro: ritento %s scritture post-prediction rimaste indietro.",
        len(ripetibili),
    )
    sb = get_supabase_client()
    recuperate: Set[int] = set()
    for voce in ripetibili:
        motivo = _db_retry_exhausted()
        if motivo is not None:
            # Guai continui DENTRO il secondo giro: si smette, niente
            # martellamento; le voci non tentate restano nel registro.
            logger.error(
                "Secondo giro interrotto (%s): le voci rimaste restano da recuperare.", motivo,
            )
            break
        fixture_id = voce.get("fixture_id")
        riga = (voce.get("payload") or {}).get("row")
        if not riga:
            continue
        try:
            resp = _db_execute(
                lambda: sb.table("fixture_predictions").update(riga).eq("fixture_id", fixture_id).execute(),
                what="secondo giro %s fixture_id=%s" % (voce.get("operation"), fixture_id),
            )
        except Exception as e:  # noqa: BLE001 - resta nel registro
            voce["error"] = str(e)[:500]
            logger.error(
                "Secondo giro fallito fixture_id=%s (%s): %s",
                fixture_id, voce.get("operation"), str(e)[:200],
            )
            continue
        if not getattr(resp, "data", None):
            logger.warning(
                "Secondo giro: nessuna riga fixture_predictions per fixture_id=%s (%s)",
                fixture_id, voce.get("operation"),
            )
            continue
        recuperate.add(id(voce))
        logger.info(
            "Secondo giro: recuperata fixture_id=%s (%s)", fixture_id, voce.get("operation")
        )

    if recuperate:
        _RUN_FAILURES[:] = [v for v in _RUN_FAILURES if id(v) not in recuperate]
    return len(recuperate)


class CoverageReadError(Exception):
    """api_coverage_by_season non leggibile per (lega, stagione) dopo i retry.

    NON si degrada mai a 'nessuna copertura': quel valore finirebbe sul DB come
    status='no_coverage', indistinguibile da un'assenza VERA di copertura, cioe'
    un dato FALSO. Chi chiama salta la fixture senza scrivere nulla.
    """

    def __init__(self, campo: str, league_id: Any, season_year: Any, cause: BaseException) -> None:
        super().__init__(
            "coverage '%s' non leggibile per league_id=%s season=%s: %s"
            % (campo, league_id, season_year, cause)
        )
        self.campo = campo
        self.league_id = league_id
        self.season_year = season_year
        self.cause = cause


def _fetch_all_table(
    table: str,
    columns: str,
    filters: Optional[List[Tuple[str, str, Any]]] = None,
    page_size: int = 1000,
) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    offset = 0
    results: List[Dict[str, Any]] = []

    while True:
        query = sb.table(table).select(columns)
        if filters:
            for op, col, val in filters:
                if op == "eq":
                    query = query.eq(col, val)
                elif op == "gte":
                    query = query.gte(col, val)
                elif op == "lt":
                    query = query.lt(col, val)
                elif op == "in":
                    query = query.in_(col, val)
                else:
                    raise ValueError(f"Unsupported filter op: {op}")

        resp = _db_execute(
            lambda: query.range(offset, offset + page_size - 1).execute(),
            what="select %s offset=%s" % (table, offset),
        )
        data = getattr(resp, "data", None) or []
        results.extend(data)
        if len(data) < page_size:
            break
        offset += page_size

    return results


# ==============================
# API helpers
# ==============================

def fetch_fixtures_for_date(api: APIFootballClient, target_date: str) -> List[Dict[str, Any]]:
    """
    Chiama /fixtures?date=YYYY-MM-DD e ritorna data["response"] (lista).
    """
    logger.info("📡 Chiamata API /fixtures?date=%s (UTC)", target_date)
    data = api.call("/fixtures", params={"date": target_date})
    if not data:
        logger.warning("⚠️ Nessun dato ricevuto da /fixtures per date=%s", target_date)
        return []

    resp = data.get("response") or []
    logger.info("📌 Fixtures trovate per date=%s: %s", target_date, len(resp))
    return resp


# ==============================
# Helper per il logging / DB
# ==============================

def setup_logger() -> logging.Logger:
    return logger  # modulo-level logger definito sopra
    
# --- CACHE BLACKLIST DINAMICA ---
_TOXIC_LEAGUES_CACHE: Optional[Set[int]] = None

def get_league_trust_scores() -> Dict[int, float]:
    """
    Calcola il Trust Score per ogni lega degli ultimi 90 giorni.
    Usa le quote reali da raw_json_odds per calcolare il Profit Factor,
    poi mappa PF → Trust con interpolazione lineare continua (0.2–1.2).
    
    Genera league_trust_scores.json con scrittura atomica.
    Ritorna dict {league_id: trust_score}.
    """
    import tempfile as _tempfile
    
    logger.info("Calcolo Trust Scores per lega (ultimi 90 giorni)...")
    sb = get_supabase_client()
    
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    
    # 1. Fetch match finiti degli ultimi 90 giorni
    matches = []
    offset = 0
    page_size = 1000
    while True:
        resp = _db_execute(
            lambda: sb.table("matches")
            .select("fixture_id, league_id, goals_home, goals_away, halftime_home, halftime_away")
            .in_("status_short", ["FT", "AET", "PEN"])
            .gte("fixture_date", cutoff_date)
            .range(offset, offset + page_size - 1)
            .execute(),
            what="select matches trust_scores offset=%s" % offset,
        )
        batch = getattr(resp, "data", []) or []
        matches.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    
    if not matches:
        logger.info("Nessun match negli ultimi 90 giorni — trust scores vuoti.")
        return {}
    
    match_dict = {m["fixture_id"]: m for m in matches}
    match_ids = list(match_dict.keys())
    
    # 2. Fetch predictions con ht_predictions (per Elite) e raw_json_odds
    elite_with_odds = []
    for i in range(0, len(match_ids), 500):
        batch = match_ids[i:i+500]
        p_res = _db_execute(
            lambda: sb.table("fixture_predictions")
            .select("fixture_id, ht_predictions, raw_json_odds")
            .in_("fixture_id", batch)
            .execute(),
            what="select fixture_predictions trust_scores (%s id)" % len(batch),
        )
        for p in getattr(p_res, "data", []) or []:
            ht = p.get("ht_predictions")
            if not ht:
                continue
            if isinstance(ht, str):
                try:
                    ht = json.loads(ht)
                except (json.JSONDecodeError, TypeError):
                    continue
            if ht.get("is_elite", False):
                elite_with_odds.append(p)
    
    # 3. Parse odds da raw_json_odds (struttura API-Football)
    def _parse_apifootball_odds(raw):
        if not isinstance(raw, dict):
            return None
        bookmakers = raw.get("bookmakers", [])
        if not bookmakers:
            return None
        bets = bookmakers[0].get("bets", [])
        odds = {}
        for bet in bets:
            name = bet.get("name", "")
            vals = {}
            for v in bet.get("values", []):
                if v.get("odd"):
                    try:
                        vals[v["value"]] = float(v["odd"])
                    except (ValueError, TypeError):
                        pass
            if name == "Goals Over/Under First Half":
                odds["HT05"] = vals.get("Over 0.5")
        return odds if odds else None
    
    # 4. Calcola Profit Factor per lega
    # PF = Gross Profit / Gross Loss (simulazione su HT Over 0.5 con quote reali)
    league_stats = {}  # league_id -> {"gross_profit": float, "gross_loss": float}
    
    for p in elite_with_odds:
        fix_id = p["fixture_id"]
        m = match_dict.get(fix_id)
        if not m:
            continue
        
        _raw_lid = m.get("league_id")
        if _raw_lid is None:
            continue
        l_id = int(_raw_lid)
        
        # Parse odds reali
        raw_odds = p.get("raw_json_odds")
        parsed = _parse_apifootball_odds(raw_odds)
        
        # Se non ci sono odds reali, usa quota fissa 1.35 come fallback
        if parsed and parsed.get("HT05"):
            quota = parsed["HT05"]
        else:
            quota = 1.35
        
        # Risultato HT
        hth = m.get("halftime_home")
        hta = m.get("halftime_away")
        if hth is None or hta is None:
            continue
        
        goals_ht = int(hth) + int(hta)
        is_win = goals_ht > 0
        
        if l_id not in league_stats:
            league_stats[l_id] = {"gross_profit": 0.0, "gross_loss": 0.0, "total": 0}
        
        league_stats[l_id]["total"] += 1
        if is_win:
            league_stats[l_id]["gross_profit"] += (quota - 1.0)  # profitto netto
        else:
            league_stats[l_id]["gross_loss"] += 1.0  # perso lo stake
    
    # 5. Calcola Trust Score con mapping continuo
    # PF = gross_profit / gross_loss (se gross_loss > 0)
    # Mapping lineare: PF 0.3 → trust 0.2, PF 1.0 → trust 1.0, PF >= 1.5 → trust 1.2
    trust_scores = {}
    for l_id, stats in league_stats.items():
        if stats["total"] < 5:  # troppo pochi match per giudicare
            trust_scores[l_id] = 1.0
            continue
        
        gp = stats["gross_profit"]
        gl = stats["gross_loss"]
        
        if gl <= 0:
            pf = 2.0  # nessuna perdita = massima fiducia
        else:
            pf = gp / gl
        
        # Mapping continuo: PF 0.3→0.2, PF 1.0→1.0, capped a 1.2
        trust = min(1.2, max(0.2, 0.2 + (pf - 0.3) * (0.8 / 0.7)))
        trust_scores[l_id] = round(trust, 3)
    
    logger.info(f"Trust Scores calcolati per {len(trust_scores)} leghe.")
    
    # 6. Scrivi league_trust_scores.json (atomico)
    base_dir = Path(__file__).resolve().parent.parent
    target_path = base_dir / "league_trust_scores.json"
    output = {
        "scores": {str(k): v for k, v in trust_scores.items()},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": 90,
        "leagues_analyzed": len(trust_scores),
    }
    tmp_path = None
    try:
        fd, tmp_path = _tempfile.mkstemp(suffix=".tmp", dir=str(base_dir))
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
            json.dump(output, tmp_f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(target_path))
        logger.info(f"✅ league_trust_scores.json generato ({len(trust_scores)} leghe)")
    except Exception as e:
        logger.error(f"❌ Errore scrittura league_trust_scores.json: {e}")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    
    return trust_scores


def get_toxic_leagues() -> Set[int]:
    """
    Wrapper retrocompatibile: leghe con trust < 0.3 sono considerate "toxic".
    Ricalcola dinamicamente la blacklist usando get_league_trust_scores().
    """
    global _TOXIC_LEAGUES_CACHE
    if _TOXIC_LEAGUES_CACHE is not None:
        return _TOXIC_LEAGUES_CACHE
    
    trust_scores = get_league_trust_scores()
    toxic_set = {int(lid) for lid, trust in trust_scores.items() if trust < 0.3}
    
    logger.info(f"Blacklist Dinamica: {len(toxic_set)} leghe non profittevoli (trust < 0.3).")
    _TOXIC_LEAGUES_CACHE = toxic_set
    return _TOXIC_LEAGUES_CACHE



# ==============================
# Coverage helper
# ==============================

def predictions_coverage_true(
    league_id: int,
    season_year: int,
    cache: Dict[Tuple[int, int], bool],
) -> bool:
    """
    Legge da api_coverage_by_season la colonna 'predictions' per (league_id, season_year).
    Cache per evitare query ripetute.

    Tre casi distinti:
      (a) riga presente  -> True/False secondo la colonna;
      (b) riga ASSENTE   -> False (maybe_single() ritorna None: copertura
          davvero mancante, e' l'unico 'no_coverage' legittimo);
      (c) ERRORE di lettura dopo i retry -> CoverageReadError. NON si degrada a
          False e NON si memoizza: 'no_coverage' sarebbe un dato FALSO.
    """
    key = (league_id, season_year)
    if key in cache:
        return cache[key]

    sb = get_supabase_client()
    try:
        resp = _db_execute(
            lambda: sb.table("api_coverage_by_season")
            .select("predictions")
            .eq("league_id", league_id)
            .eq("season_year", season_year)
            .maybe_single()
            .execute(),
            what="select coverage predictions league_id=%s season=%s" % (league_id, season_year),
        )
    except Exception as e:
        logger.error(
            "❌ Errore nel leggere coverage predictions (league_id=%s season=%s): %s",
            league_id, season_year, e
        )
        raise CoverageReadError("predictions", league_id, season_year, e) from e

    # (b) maybe_single() su 0 righe ritorna None -> {} -> False, come sempre.
    row = getattr(resp, "data", None) or {}
    flag = bool(row.get("predictions"))
    cache[key] = flag
    return flag


def odds_coverage_true(
    league_id: int,
    season_year: int,
    cache: Dict[Tuple[int, int], bool],
) -> bool:
    """
    Legge da api_coverage_by_season la colonna 'odds' per (league_id, season_year).
    Cache per evitare query ripetute.

    Stessi tre casi di predictions_coverage_true: un errore di lettura NON
    diventa False (scriverebbe raw_json_odds=NULL, cioe' "niente quote" quando
    in realta' non lo sappiamo) ma solleva CoverageReadError.
    """
    key = (league_id, season_year)
    if key in cache:
        return cache[key]

    sb = get_supabase_client()
    try:
        resp = _db_execute(
            lambda: sb.table("api_coverage_by_season")
            .select("odds")
            .eq("league_id", league_id)
            .eq("season_year", season_year)
            .maybe_single()
            .execute(),
            what="select coverage odds league_id=%s season=%s" % (league_id, season_year),
        )
    except Exception as e:
        # 406 can happen if column doesn't exist or view doesn't expose it
        logger.error(
            "❌ Errore nel leggere coverage odds (league_id=%s season=%s): %s",
            league_id, season_year, e
        )
        raise CoverageReadError("odds", league_id, season_year, e) from e

    # (b) maybe_single() su 0 righe ritorna None -> {} -> False, come sempre.
    row = getattr(resp, "data", None) or {}
    flag = bool(row.get("odds"))
    cache[key] = flag
    return flag


# ==============================
# Odds helper
# ==============================

def fetch_odds_for_league_season(
    api: APIFootballClient,
    league_id: int,
    season_year: int,
    cache: Dict[Tuple[int, int], Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Chiama /odds?league=...&season=...&bookmaker=3 con paginazione completa.
    Raccoglie tutte le pagine e le unisce in un unico dict con chiave "response".
    Mette in cache per (league_id, season_year).
    """
    key = (league_id, season_year)
    if key in cache:
        return cache[key]

    all_responses: List[Dict[str, Any]] = []
    page = 1

    while True:
        logger.info(
            "📡 Chiamata API /odds?league=%s&season=%s&bookmaker=3&page=%s",
            league_id, season_year, page,
        )
        data = api.call(
            "/odds",
            params={
                "league": str(league_id),
                "season": str(season_year),
                "bookmaker": "3",
                "page": str(page),
            },
        )
        if not data:
            break

        batch = data.get("response") or []
        all_responses.extend(batch)

        paging = data.get("paging") or {}
        current = int(paging.get("current", 1))
        total = int(paging.get("total", 1))

        logger.info(
            "   /odds lega=%s stagione=%s pagina %s/%s → %s fixture ricevute (totale: %s)",
            league_id, season_year, current, total, len(batch), len(all_responses),
        )

        if current >= total or not batch:
            break
        page += 1

    merged = {"response": all_responses}
    cache[key] = merged
    return merged


def extract_odds_for_fixture(odds_json: Dict[str, Any], fixture_id: int) -> Optional[Dict[str, Any]]:
    """
    Estrae l'oggetto odds per fixture_id dalla risposta /odds.
    """
    if not odds_json:
        return None
    resp_list = odds_json.get("response") or []
    for item in resp_list:
        fixture = item.get("fixture") or {}
        if fixture.get("id") == fixture_id:
            return item
    return None


def _build_odds_row(raw_json_odds: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Costruisce la riga di UPDATE per le odds (stessi campi/valori di sempre)."""
    return {
        "raw_json_odds": raw_json_odds,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def upsert_odds_row(fixture_id: int, raw_json_odds: Optional[Dict[str, Any]]) -> None:
    """
    Salva le odds grezze in fixture_predictions.raw_json_odds.
    Non tocca gli altri campi.
    """
    sb = get_supabase_client()
    row = _build_odds_row(raw_json_odds)
    resp = _db_execute(
        lambda: sb.table("fixture_predictions").update(row).eq("fixture_id", fixture_id).execute(),
        what="update odds fixture_id=%s" % fixture_id,
    )
    updated = getattr(resp, "data", None)
    if not updated:
        logger.warning("⚠️ Nessuna riga fixture_predictions trovata per fixture_id=%s (odds non salvate)", fixture_id)


_POISSON_CAL = None


def _poisson_cal():
    """Lazy-singleton del calibratore Poisson (carica i fattori una volta per run)."""
    global _POISSON_CAL
    if _POISSON_CAL is None:
        try:
            from poisson_calibrator import PoissonCalibrator
            _POISSON_CAL = PoissonCalibrator()
            logger.info("PoissonCalibrator pronto (sorgente=%s)", _POISSON_CAL.source)
        except Exception as e:  # non bloccare la pipeline se il modulo non e' disponibile
            logger.warning("PoissonCalibrator non disponibile: %s", e)
            _POISSON_CAL = False  # sentinella: non riprovare a ogni fixture
    return _POISSON_CAL or None


def _build_analysis_row(fixture_id: int, db_json_analisi: Optional[Dict[str, Any]], ht_predictions: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Costruisce la riga di UPDATE per analisi + HT (calibrazione inclusa).
    Estratta da upsert_analysis_data: stessi campi, stessi valori, stessi
    timestamp calcolati al momento della chiamata.
    """
    # Calibrazione Poisson CENTRALIZZATA: arricchisce db_json_analisi con markets_calibrated
    # (coerente con l'ML gia' calibrato nel DB) cosi' ogni partita nasce gia' calibrata.
    # ADDITIVO e NON-FATALE: il grezzo `markets` resta INTATTO (serve al calibratore settimanale).
    if isinstance(db_json_analisi, dict) and db_json_analisi.get("model") == "poisson_xg_hybrid_dc":
        markets = db_json_analisi.get("markets")
        cal = _poisson_cal()
        if cal is not None and isinstance(markets, dict):
            try:
                db_json_analisi = dict(db_json_analisi)
                db_json_analisi["markets_calibrated"] = cal.calibrate_markets(
                    markets, db_json_analisi.get("league_id"))
                db_json_analisi["calibrated_at"] = datetime.now(timezone.utc).isoformat()
                db_json_analisi["calibration_source"] = cal.source
            except Exception as e:
                logger.warning("calibrazione markets fallita fixture_id=%s: %s", fixture_id, e)
                _record_failure(fixture_id, "calibrazione", e)

    return {
        "db_json_analisi": db_json_analisi,
        "ht_predictions": ht_predictions,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def upsert_analysis_data(fixture_id: int, db_json_analisi: Optional[Dict[str, Any]], ht_predictions: Optional[Dict[str, Any]]) -> None:
    """
    Salva sia l'analisi completa che quella specifica per l'HT.
    """
    sb = get_supabase_client()
    row = _build_analysis_row(fixture_id, db_json_analisi, ht_predictions)
    resp = _db_execute(
        lambda: sb.table("fixture_predictions").update(row).eq("fixture_id", fixture_id).execute(),
        what="update analisi fixture_id=%s" % fixture_id,
    )
    updated = getattr(resp, "data", None)
    if not updated:
        logger.warning("Nessuna riga fixture_predictions trovata per fixture_id=%s (dati non salvati)", fixture_id)


# ==============================
# NEW: Skip helper (no API call if already OK)
# ==============================

def prediction_already_done(fixture_id: int) -> bool:
    """
    Ritorna True se in fixture_predictions esiste già una riga per fixture_id
    con status='ok' E ht_predictions non è nullo. In quel caso skippiamo la chiamata.
    """
    sb = get_supabase_client()
    try:
        resp = _db_execute(
            lambda: sb.table("fixture_predictions")
            .select("fixture_id,status,ht_predictions")
            .eq("fixture_id", fixture_id)
            .maybe_single()
            .execute(),
            what="select prediction_already_done fixture_id=%s" % fixture_id,
        )
        row = getattr(resp, "data", None) or None
        if not row:
            return False
        if row.get("status") != "ok":
            return False
        if row.get("ht_predictions") is None:
            return False
        return True
    except Exception as e:
        # Se il check fallisce, NON blocchiamo: meglio chiamare l'API che perdere dati
        logger.warning("⚠️ Errore check prediction_already_done fixture_id=%s: %s", fixture_id, e)
        return False


def prefetch_predictions_done(fixture_ids: List[int]) -> Set[int]:
    """
    Versione BATCH di prediction_already_done: una query (a chunk da 200 id,
    per non superare i limiti di lunghezza URL di PostgREST) invece di una
    SELECT per fixture.

    La condizione e' la STESSA di prediction_already_done (riga esistente per
    fixture_id con status='ok' E ht_predictions non nullo) ma e' applicata dal
    SERVER, e si seleziona il solo `fixture_id`: prima si scaricavano i JSON
    pesanti di `ht_predictions` per 200 fixture solo per controllare che non
    fossero nulli (decine di MB per run, e un ottimo modo per prendersi un
    57014 sulla lettura).

    Fail-open come l'originale: se un chunk fallisce, le sue fixture NON
    entrano nel set (=> verranno riprocessate, meglio chiamare l'API che
    perdere dati). A differenza di prima pero' l'errore NON viene ingoiato:
    finisce nel registro e il processo esce != 0.
    """
    done: Set[int] = set()
    if not fixture_ids:
        return done

    sb = get_supabase_client()
    chunk_size = 200
    for i in range(0, len(fixture_ids), chunk_size):
        chunk = fixture_ids[i : i + chunk_size]
        try:
            resp = _db_execute(
                lambda: sb.table("fixture_predictions")
                .select("fixture_id")
                .in_("fixture_id", chunk)
                .eq("status", "ok")
                .not_.is_("ht_predictions", "null")
                .execute(),
                what="select prefetch predictions (%s id)" % len(chunk),
            )
            for row in getattr(resp, "data", None) or []:
                fid = row.get("fixture_id")
                if fid is not None:
                    done.add(int(fid))
        except Exception as e:
            logger.warning(
                "⚠️ Errore prefetch prediction_already_done (chunk %s..%s): %s",
                chunk[0], chunk[-1], e
            )
            # Fail-open invariato (le 200 fixture vengono rielaborate), ma
            # l'anomalia resta visibile: il run esce != 0.
            _record_failure("%s..%s" % (chunk[0], chunk[-1]), "prefetch", e)
    return done


# ==============================
# Mapping fixture context
# ==============================

def extract_fixture_context(fx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Estrae i campi base da una fixture (risposta /fixtures).
    Ritorna None se fixture_id / league_id / season_year non sono validi.
    """
    fixture = fx.get("fixture") or {}
    league = fx.get("league") or {}
    teams = fx.get("teams") or {}

    home = teams.get("home") or {}
    away = teams.get("away") or {}

    fixture_id = fixture.get("id")
    league_id = league.get("id")
    season_year = league.get("season")

    if fixture_id is None or league_id is None or season_year is None:
        return None

    return {
        "fixture_id": int(fixture_id),
        "league_id": int(league_id),
        "league_name": league.get("name"),
        "season_year": int(season_year),

        # ISO string (API-Football fornisce tipicamente +00:00 / UTC)
        "fixture_date": fixture.get("date"),

        "home_team_id": int(home["id"]) if home.get("id") is not None else None,
        "home_team_name": home.get("name"),
        "away_team_id": int(away["id"]) if away.get("id") is not None else None,
        "away_team_name": away.get("name"),
    }


# ==============================
# DB analysis (Poisson/xG)
# ==============================

def _to_float(v: Any) -> Optional[float]:
    """Coerce a DB value to float, tolerating numeric strings and None.
    Some Supabase/PostgREST drivers return numeric columns as strings; summing
    those with the built-in sum() would CONCATENATE instead of adding and
    silently corrupt every goal-based statistic. Returns None when the value is
    missing or non-numeric so callers can apply their own missing-data policy."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _poisson_prob(lmbda: float, k: int) -> float:
    """Scalar Poisson PMF backed by scipy (no factorial/exp overflow risk).
    Preserves the historical contract lmbda <= 0 -> 0.0 (the legacy hand-rolled
    implementation returned 0.0 for non-positive lambda; scipy would return 1.0
    at k=0).  In practice lambdas are always floored > 0, so this guard is a
    safety net only and does not change live output."""
    if lmbda <= 0:
        return 0.0
    return float(poisson.pmf(k, lmbda))


def _build_score_grid(lambda_home: float, lambda_away: float, max_goals: int) -> np.ndarray:
    """Vectorized independent-Poisson score grid (rows = home goals 0..max_goals,
    cols = away goals 0..max_goals) via scipy PMF + numpy outer product.
    Numerically identical to the nested-loop _poisson_prob build to ~1e-15,
    but without per-cell factorial/exp evaluation (removes overflow risk).
    Returns the RAW independent grid; Dixon-Coles tau correction and
    normalisation are applied by the caller."""
    ks = np.arange(0, max_goals + 1)
    p_home = poisson.pmf(ks, lambda_home) if lambda_home > 0 else np.zeros(max_goals + 1)
    p_away = poisson.pmf(ks, lambda_away) if lambda_away > 0 else np.zeros(max_goals + 1)
    return np.outer(p_home, p_away)


# Dixon-Coles correlation parameter.
# Negative value: 0-0 and 1-1 occur MORE often than independent Poisson predicts;
# 1-0 and 0-1 occur LESS often.  Literature range: ρ ∈ [−0.20, −0.08].
# We use the original Dixon & Coles (1997) estimate as the GLOBAL FALLBACK: ρ = −0.13.
DC_RHO: float = -0.13

# Per-league ρ overrides (#11). Estimated offline by generate_dc_rho.py via a
# 1-parameter profile-likelihood MLE on the four low-score cells (held marginals
# = the engine's own per-fixture lambdas), shrunk toward DC_RHO for low-N leagues
# and clamped to the literature-plausible band. The engine loads them read-only;
# a missing file or missing league transparently falls back to DC_RHO.
_DC_RHO_BY_LEAGUE_CACHE: Optional[Dict[int, float]] = None
# Safety band: refuse any stored value outside the plausible Dixon-Coles range so
# a corrupted/over-fit estimate can never push tau into a degenerate regime.
DC_RHO_MIN: float = -0.25
DC_RHO_MAX: float = 0.05


def get_league_rho(league_id: Optional[int]) -> float:
    """Return the per-league Dixon-Coles ρ, falling back to the global DC_RHO.
    Reads dc_rho_by_league.json once and caches it. Any stored value outside
    [DC_RHO_MIN, DC_RHO_MAX] is ignored in favour of DC_RHO (defensive)."""
    global _DC_RHO_BY_LEAGUE_CACHE
    if _DC_RHO_BY_LEAGUE_CACHE is None:
        loaded: Dict[int, float] = {}
        path = PROJECT_ROOT / "dc_rho_by_league.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for k, v in (raw.get("rho_by_league") or {}).items():
                try:
                    loaded[int(k)] = float(v)
                except (TypeError, ValueError):
                    continue
            logger.info(f"Loaded per-league Dixon-Coles ρ for {len(loaded)} leagues.")
        except FileNotFoundError:
            logger.debug("dc_rho_by_league.json not found — using global DC_RHO for all leagues.")
        except Exception as e:  # noqa: BLE001 — never let a bad file break predictions
            logger.warning(f"Could not load dc_rho_by_league.json ({e}); using global DC_RHO.")
        _DC_RHO_BY_LEAGUE_CACHE = loaded

    if league_id is None:
        return DC_RHO
    rho = _DC_RHO_BY_LEAGUE_CACHE.get(int(league_id))
    if rho is None or not (DC_RHO_MIN <= rho <= DC_RHO_MAX):
        return DC_RHO
    return rho


def _dc_tau(hg: int, ag: int, lh: float, la: float, rho: float = DC_RHO) -> float:
    """Dixon-Coles correction factor for the four low-scoring score cells.
    Adjusts the joint-independence assumption for (0,0), (1,0), (0,1), (1,1).
    All other score combinations return 1.0 (no adjustment).
    Tau is floored at 0.0: with |rho|=0.13 this only triggers above lambda ~7.7,
    unreachable in normal football data, but the guard is kept for safety."""
    if hg == 0 and ag == 0:
        return 1.0 - lh * la * rho          # always > 1 when rho < 0
    if hg == 1 and ag == 0:
        return max(0.0, 1.0 + la * rho)     # negative if la > 1/|rho| ≈ 7.7
    if hg == 0 and ag == 1:
        return max(0.0, 1.0 + lh * rho)     # negative if lh > 1/|rho| ≈ 7.7
    if hg == 1 and ag == 1:
        return 1.0 - rho                     # always 1.13 when rho = -0.13
    return 1.0


def _build_match_cache(
    league_id: int,
    season_year: int,
    cache: Dict[Tuple[int, int], Dict[str, Any]],
) -> Dict[str, Any]:
    key = (league_id, season_year)
    if key in cache:
        return cache[key]

    cols = (
        "fixture_id,fixture_date,home_team_id,away_team_id,"
        "goals_home,goals_away,halftime_home,halftime_away,status_short"
    )
    filters = [("eq", "league_id", league_id), ("eq", "season_year", season_year)]
    rows = _fetch_all_table("matches", cols, filters, page_size=1000)

    played = []
    for r in rows:
        if str(r.get("status_short") or "").upper() not in {"FT", "AET", "PEN"}:
            continue
        # Coerce goals to float up-front: numeric-string DB values would break
        # every downstream sum()/mean (concatenation instead of addition).
        gh = _to_float(r.get("goals_home"))
        ga = _to_float(r.get("goals_away"))
        # Exclude finished fixtures with missing/non-numeric FT goals: coercing
        # None to 0 (the old behaviour) biases per-team and league averages down.
        if gh is None or ga is None:
            continue
        r["goals_home"] = gh
        r["goals_away"] = ga
        # Halftime may legitimately be missing; keep float-or-None.
        r["halftime_home"] = _to_float(r.get("halftime_home"))
        r["halftime_away"] = _to_float(r.get("halftime_away"))
        played.append(r)

    team_hist: Dict[int, List[Dict[str, Any]]] = {}
    for m in played:
        fixture_date = m.get("fixture_date")
        home_id = m.get("home_team_id")
        away_id = m.get("away_team_id")
        goals_home = m.get("goals_home")
        goals_away = m.get("goals_away")
        ht_home = m.get("halftime_home")
        ht_away = m.get("halftime_away")

        if home_id is not None:
            team_hist.setdefault(int(home_id), []).append(
                {
                    "fixture_id": m.get("fixture_id"),
                    "fixture_date": fixture_date,
                    "team_id": int(home_id),
                    # opponent_id lets us derive xG-conceded (xGA) as the
                    # opponent's xG in the SAME fixture (no native xGA needed).
                    "opponent_id": int(away_id) if away_id is not None else None,
                    "goals_for": goals_home,
                    "goals_against": goals_away,
                    "halftime_for": ht_home,
                    "is_home": True,
                }
            )
        if away_id is not None:
            team_hist.setdefault(int(away_id), []).append(
                {
                    "fixture_id": m.get("fixture_id"),
                    "fixture_date": fixture_date,
                    "team_id": int(away_id),
                    "opponent_id": int(home_id) if home_id is not None else None,
                    "goals_for": goals_away,
                    "goals_against": goals_home,
                    "halftime_for": ht_away,
                    "is_home": False,
                }
            )

    for team_id, lst in team_hist.items():
        lst.sort(key=lambda x: x.get("fixture_date") or "")

    total_matches = len(played)
    if total_matches > 0:
        # played rows are guaranteed to have non-None goals_home/goals_away.
        league_home_avg = sum(m["goals_home"] for m in played) / total_matches
        league_away_avg = sum(m["goals_away"] for m in played) / total_matches
        league_total_avg = league_home_avg + league_away_avg
    else:
        league_home_avg = 1.2
        league_away_avg = 1.0
        league_total_avg = 2.2

    cache[key] = {
        "played": played,
        "team_hist": team_hist,
        "league_home_avg": league_home_avg,
        "league_away_avg": league_away_avg,
        "league_total_avg": league_total_avg,
    }
    return cache[key]


def _build_xg_cache(
    league_id: int,
    season_year: int,
    cache: Dict[Tuple[int, int], Dict[Tuple[int, int], float]],
    fixture_ids: List[int],
) -> Dict[Tuple[int, int], float]:
    key = (league_id, season_year)
    if key in cache:
        return cache[key]

    xg_map: Dict[Tuple[int, int], float] = {}
    if not fixture_ids:
        cache[key] = xg_map
        return xg_map

    # Accumulate all 'expected_goals' rows per (fixture, team) then aggregate by
    # mean. EXACT stat_type match (was substring 'expected'/'xg' + max() dedupe):
    # this prevents a future 'expected_goals_against' row from corrupting the
    # attack proxy, and mean is robust to duplicate rows (max would pick an
    # arbitrary inflated value).
    accum: Dict[Tuple[int, int], List[float]] = {}
    for i in range(0, len(fixture_ids), 500):
        chunk = fixture_ids[i : i + 500]
        rows = _fetch_all_table(
            "match_team_stats",
            "fixture_id,team_id,stat_type,value_numeric",
            filters=[("eq", "league_id", league_id), ("eq", "season_year", season_year), ("in", "fixture_id", chunk)],
            page_size=1000,
        )
        for r in rows:
            st = str(r.get("stat_type") or "").strip().lower()
            if st != "expected_goals":
                continue
            try:
                val_f = float(r.get("value_numeric"))
            except (ValueError, TypeError):
                continue
            fx_id = r.get("fixture_id")
            tm_id = r.get("team_id")
            if fx_id is None or tm_id is None:
                continue
            key2 = (int(fx_id), int(tm_id))
            accum.setdefault(key2, []).append(val_f)

    for key2, vals in accum.items():
        xg_map[key2] = sum(vals) / len(vals)

    cache[key] = xg_map
    return xg_map


def _window_stats(team_matches: List[Dict[str, Any]], n: int, xg_map: Dict[Tuple[int, int], float]) -> Dict[str, Any]:
    if not team_matches:
        return {"gf_avg": None, "ga_avg": None, "xg_avg": None, "xga_avg": None,
                "n_used": 0, "xg_used": 0, "xga_used": 0}

    recent = team_matches[-n:]
    # goals_for/against are already float-coerced in _build_match_cache, but
    # guard again here so a stray non-numeric value drops out instead of
    # poisoning the mean.
    gf = [v for m in recent if (v := _to_float(m.get("goals_for"))) is not None]
    ga = [v for m in recent if (v := _to_float(m.get("goals_against"))) is not None]
    xg_vals = []   # xG generated BY this team   (attack proxy)
    xga_vals = []  # xG conceded by this team = opponent's xG same fixture (defense proxy)
    for m in recent:
        fx_id = m.get("fixture_id")
        team_id = m.get("team_id")
        opp_id = m.get("opponent_id")
        if fx_id is None:
            continue
        if team_id is not None:
            val = xg_map.get((int(fx_id), int(team_id)))
            if val is not None:
                xg_vals.append(val)
        if opp_id is not None:
            oval = xg_map.get((int(fx_id), int(opp_id)))
            if oval is not None:
                xga_vals.append(oval)

    return {
        "gf_avg": sum(gf) / len(gf) if gf else None,
        "ga_avg": sum(ga) / len(ga) if ga else None,
        "xg_avg": sum(xg_vals) / len(xg_vals) if xg_vals else None,
        "xga_avg": sum(xga_vals) / len(xga_vals) if xga_vals else None,
        "n_used": len(recent),
        "xg_used": len(xg_vals),
        "xga_used": len(xga_vals),
    }


def _blend_windows(stats5: Dict[str, Any], stats10: Dict[str, Any], stats15: Dict[str, Any], weights: Dict[int, float]) -> Dict[str, Any]:
    def _blend(key: str) -> Optional[float]:
        parts = []
        for n, st in [(5, stats5), (10, stats10), (15, stats15)]:
            val = st.get(key)
            if val is not None:
                parts.append((weights[n], val))
        if not parts:
            return None
        total_w = sum(w for w, _ in parts)
        return sum(w * v for w, v in parts) / total_w  # renormalize for missing windows

    return {
        "gf_blend": _blend("gf_avg"),
        "ga_blend": _blend("ga_avg"),
        "xg_blend": _blend("xg_avg"),
        "xga_blend": _blend("xga_avg"),
    }


def compute_db_json_analisi(
    ctx: Dict[str, Any],
    match_cache: Dict[Tuple[int, int], Dict[str, Any]],
    xg_cache: Dict[Tuple[int, int], Dict[Tuple[int, int], float]],
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    fixture_id = ctx.get("fixture_id")
    league_id = ctx.get("league_id")
    season_year = ctx.get("season_year")
    fixture_date = ctx.get("fixture_date")
    home_team_id = ctx.get("home_team_id")
    away_team_id = ctx.get("away_team_id")

    if not all([fixture_id, league_id, season_year, fixture_date, home_team_id, away_team_id]):
        return None

    cache = _build_match_cache(int(league_id), int(season_year), match_cache)
    team_hist = cache["team_hist"]
    league_home_avg = cache["league_home_avg"]
    league_away_avg = cache["league_away_avg"]
    league_total_avg = cache["league_total_avg"]

    fixture_ids = [m.get("fixture_id") for m in cache["played"] if m.get("fixture_id") is not None]
    xg_map = _build_xg_cache(int(league_id), int(season_year), xg_cache, fixture_ids)

    # League xG baselines over the SAME played-set used for the goals baselines.
    # The xG term must be shrunk/normalised against a league xG average, not the
    # league GOALS average (xG and realised goals differ systematically). When
    # the league has no xG coverage, fall back to the goals baseline so a neutral
    # team still yields coefficient ~1.0 and behaviour degrades gracefully.
    home_xg_samples: List[float] = []
    away_xg_samples: List[float] = []
    for _m in cache["played"]:
        _fx = _m.get("fixture_id")
        _hid = _m.get("home_team_id")
        _aid = _m.get("away_team_id")
        if _fx is not None and _hid is not None:
            _hv = xg_map.get((int(_fx), int(_hid)))
            if _hv is not None:
                home_xg_samples.append(_hv)
        if _fx is not None and _aid is not None:
            _av = xg_map.get((int(_fx), int(_aid)))
            if _av is not None:
                away_xg_samples.append(_av)
    league_home_xg_avg = (
        sum(home_xg_samples) / len(home_xg_samples) if home_xg_samples else league_home_avg
    )
    league_away_xg_avg = (
        sum(away_xg_samples) / len(away_xg_samples) if away_xg_samples else league_away_avg
    )
    # Guard against a degenerate all-zero xG baseline (division by zero in the
    # attack term); fall back to the goals baseline which is always > 0 here.
    if league_home_xg_avg <= 0:
        league_home_xg_avg = league_home_avg
    if league_away_xg_avg <= 0:
        league_away_xg_avg = league_away_avg

    def _before_date(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [m for m in matches if m.get("fixture_date") and m["fixture_date"] < fixture_date]

    home_matches = _before_date(team_hist.get(int(home_team_id), []))
    away_matches = _before_date(team_hist.get(int(away_team_id), []))

    # Context-specific lists: home team's matches played at home, away team's matches played away.
    # Used to compute attack/defense in the correct situational context rather than mixing venues.
    home_home = [m for m in home_matches if m.get("is_home") is True]
    away_away = [m for m in away_matches if m.get("is_home") is False]

    # Overall blended windows (all matches) for the MIN_MATCHES data-sufficiency check
    # and as fallback when context-specific data is too sparse.
    stats5_h = _window_stats(home_matches, 5, xg_map)
    stats10_h = _window_stats(home_matches, 10, xg_map)
    stats15_h = _window_stats(home_matches, 15, xg_map)
    stats5_a = _window_stats(away_matches, 5, xg_map)
    stats10_a = _window_stats(away_matches, 10, xg_map)
    stats15_a = _window_stats(away_matches, 15, xg_map)

    weights = {5: 0.5, 10: 0.3, 15: 0.2}
    blend_h = _blend_windows(stats5_h, stats10_h, stats15_h, weights)
    blend_a = _blend_windows(stats5_a, stats10_a, stats15_a, weights)

    # Context-specific blended windows — fall back to all-match blend when < 3 games available.
    # With k_shrink=8 and n<3, the prior dominates (>73% weight), making split vs fallback
    # differences negligible; 3 is therefore an appropriate minimum to justify the split.
    MIN_CTX = 3
    if len(home_home) >= MIN_CTX:
        ctx5_h  = _window_stats(home_home, 5,  xg_map)
        ctx10_h = _window_stats(home_home, 10, xg_map)
        ctx15_h = _window_stats(home_home, 15, xg_map)
        ctx_blend_h = _blend_windows(ctx5_h, ctx10_h, ctx15_h, weights)
        ctx_n_h = ctx15_h.get("n_used", 0)
    else:
        ctx_blend_h = blend_h
        ctx_n_h = stats15_h.get("n_used", 0)

    if len(away_away) >= MIN_CTX:
        ctx5_a  = _window_stats(away_away, 5,  xg_map)
        ctx10_a = _window_stats(away_away, 10, xg_map)
        ctx15_a = _window_stats(away_away, 15, xg_map)
        ctx_blend_a = _blend_windows(ctx5_a, ctx10_a, ctx15_a, weights)
        ctx_n_a = ctx15_a.get("n_used", 0)
    else:
        ctx_blend_a = blend_a
        ctx_n_a = stats15_a.get("n_used", 0)

    k_shrink = 8.0
    eta_goals = 0.6

    def _shrink(raw: Optional[float], n_used: int, prior: float) -> float:
        base = prior if raw is None else raw
        return ((k_shrink * prior) + (base * max(n_used, 1))) / (k_shrink + max(n_used, 1))

    home_n_used = stats15_h.get("n_used", 0)
    away_n_used = stats15_a.get("n_used", 0)

    # Minimum data guard: with fewer than 3 matches the shrinkage pulls so strongly
    # toward the league prior that the estimate adds no information over the base rate.
    # Return None to signal "insufficient data" rather than a near-random Poisson estimate.
    MIN_MATCHES_FOR_POISSON = 5  # soglia per generare stime Poisson; money_management usa 8 per scommettere
    if home_n_used < MIN_MATCHES_FOR_POISSON or away_n_used < MIN_MATCHES_FOR_POISSON:
        logger.debug(
            f"Fixture {fixture_id}: insufficient data (home={home_n_used}, away={away_n_used} "
            f"< {MIN_MATCHES_FOR_POISSON}) — skipping Poisson estimate"
        )
        return None

    # Correct normalisation for each statistic:
    #   gf_h  = home team goals scored AT HOME   → prior & normaliser = league_home_avg
    #   ga_h  = home team goals conceded AT HOME  → these are goals scored BY visitors
    #                                               → prior & normaliser = league_away_avg
    #   gf_a  = away team goals scored AWAY       → prior & normaliser = league_away_avg
    #   ga_a  = away team goals conceded AWAY     → these are goals scored BY hosting teams
    #                                               → prior & normaliser = league_home_avg
    gf_h = _shrink(ctx_blend_h.get("gf_blend"), ctx_n_h, league_home_avg)
    ga_h = _shrink(ctx_blend_h.get("ga_blend"), ctx_n_h, league_away_avg)
    gf_a = _shrink(ctx_blend_a.get("gf_blend"), ctx_n_a, league_away_avg)
    ga_a = _shrink(ctx_blend_a.get("ga_blend"), ctx_n_a, league_home_avg)

    # xG (attack) and xGA (defense) are shrunk toward the league xG baseline on
    # the SAME scale as the statistic being shrunk.
    #   xg_h  = home team xG generated AT HOME      → baseline = league_home_xg_avg
    #   xg_a  = away team xG generated AWAY         → baseline = league_away_xg_avg
    #   xga_h = home team xG CONCEDED at home = visitors' xG → baseline = league_away_xg_avg
    #   xga_a = away team xG CONCEDED away  = hosts' xG      → baseline = league_home_xg_avg
    xg_h  = _shrink(ctx_blend_h.get("xg_blend"),  ctx_n_h, league_home_xg_avg)
    xg_a  = _shrink(ctx_blend_a.get("xg_blend"),  ctx_n_a, league_away_xg_avg)
    xga_h = _shrink(ctx_blend_h.get("xga_blend"), ctx_n_h, league_away_xg_avg)
    xga_a = _shrink(ctx_blend_a.get("xga_blend"), ctx_n_a, league_home_xg_avg)

    # Availability of the xG/xGA term per team/side. When a stat has NO xG sample
    # backing it, _shrink() returns the prior and its ratio would collapse to an
    # uninformative 1.0 — silently dampening the (informative) goals signal toward
    # neutral. Policy (user-confirmed): if xG is missing, use ONLY goals (no blend).
    xg_h_ok  = ctx_blend_h.get("xg_blend")  is not None
    xg_a_ok  = ctx_blend_a.get("xg_blend")  is not None
    xga_h_ok = ctx_blend_h.get("xga_blend") is not None
    xga_a_ok = ctx_blend_a.get("xga_blend") is not None

    def _coef(goals_ratio: float, xg_ratio: Optional[float]) -> float:
        """Blend a goals ratio with an xG ratio (both dimensionless, centred at
        1.0 on their own league scale). If the xG ratio is unavailable, fall back
        to goals only (effective eta=1.0) instead of blending against a neutral
        1.0 — which would otherwise shrink a real signal toward the mean."""
        if xg_ratio is None:
            return goals_ratio
        return (eta_goals * goals_ratio) + ((1.0 - eta_goals) * xg_ratio)

    home_attack = _coef(gf_h / league_home_avg, (xg_h  / league_home_xg_avg) if xg_h_ok  else None)
    away_attack = _coef(gf_a / league_away_avg, (xg_a  / league_away_xg_avg) if xg_a_ok  else None)
    home_def    = _coef(ga_h / league_away_avg, (xga_h / league_away_xg_avg) if xga_h_ok else None)
    away_def    = _coef(ga_a / league_home_avg, (xga_a / league_home_xg_avg) if xga_a_ok else None)

    lambda_home = max(0.05, league_home_avg * home_attack * away_def)
    lambda_away = max(0.05, league_away_avg * away_attack * home_def)

    # Telemetry (#2): persisted in db_json_analisi.inputs so coverage of the xG
    # blend is queryable per-league straight from the stored JSON / sheet.
    if not (xg_h_ok or xg_a_ok or xga_h_ok or xga_a_ok):
        logger.debug(
            f"Fixture {fixture_id}: no xG/xGA coverage — lambda computed on goals only"
        )

    # Score grid truncated at 10 goals (was 6): recovers truncated tail mass
    # before renormalisation. Vectorized independent-Poisson grid + Dixon-Coles
    # tau correction on the four low-scoring cells, then renormalise as before.
    # Per-league Dixon-Coles correlation (#11): estimated offline, falls back to
    # the global DC_RHO when no league-specific value is available. The SAME rho
    # is reused for the half-time grid below so FT and HT stay internally coherent.
    rho_league = get_league_rho(league_id)

    max_goals = 10
    grid = _build_score_grid(lambda_home, lambda_away, max_goals)
    for hg in (0, 1):
        for ag in (0, 1):
            grid[hg, ag] *= _dc_tau(hg, ag, lambda_home, lambda_away, rho=rho_league)

    total_p = float(grid.sum()) or 1.0
    grid = grid / total_p

    hg_idx = np.arange(max_goals + 1).reshape(-1, 1)
    ag_idx = np.arange(max_goals + 1).reshape(1, -1)
    tot_idx = hg_idx + ag_idx

    p_home = float(grid[hg_idx > ag_idx].sum())
    p_draw = float(grid[hg_idx == ag_idx].sum())
    p_away = float(grid[hg_idx < ag_idx].sum())
    # (#15) Enforce a proper 1X2 distribution. The three masks already partition
    # the normalised grid so the sum is 1.0 up to float error; renormalise so the
    # stored probabilities sum to exactly 1 (no 0.9999/1.0001 leakage downstream).
    _x2_tot = p_home + p_draw + p_away
    if _x2_tot > 0:
        p_home /= _x2_tot
        p_draw /= _x2_tot
        p_away /= _x2_tot
    p_over15 = float(grid[tot_idx >= 2].sum())
    p_under15 = 1.0 - p_over15
    p_over25 = float(grid[tot_idx >= 3].sum())
    p_under25 = 1.0 - p_over25
    p_over35 = float(grid[tot_idx >= 4].sum())
    p_under35 = 1.0 - p_over35
    p_btts = float(grid[(hg_idx > 0) & (ag_idx > 0)].sum())
    p_btts_no = 1.0 - p_btts

    def _compute_ht_ratio(matches: List[Dict[str, Any]], prior: float = 0.45, k: int = 12) -> float:
        """Frazione empirica di gol segnata nel primo tempo.
        Bayesian shrinkage verso prior=0.45 con forza k=12 gol.
        Cap [0.25, 0.65] per evitare estremi da piccoli campioni.
        Ritorna prior se nessun match ha dati HT validi."""
        total_gf = 0
        total_ht = 0
        valid = 0
        for m in matches[-15:]:
            gf = m.get("goals_for")
            ht = m.get("halftime_for")
            if gf is None or ht is None:
                continue  # dato HT mancante — non distorcere il ratio
            gf_int = int(float(gf))
            ht_int = int(float(ht))
            if gf_int < 0 or ht_int < 0 or ht_int > gf_int:
                continue  # dato impossibile o corrotto
            total_gf += gf_int
            total_ht += ht_int
            valid += 1
        if valid == 0:
            return prior  # nessun dato HT valido: usa prior invece di distorcere
        if total_gf == 0:
            return prior  # tutte le partite finite 0-0: nessuna info sul ratio, usa prior
        shrunk = (k * prior + total_ht) / (k + total_gf)
        return max(0.25, min(0.65, shrunk))

    # --- HT 1X2 via matrice separata (ratio HT/FT data-driven per squadra) ---
    # Nessun fallback a home_matches/away_matches: mantenere coerenza contestuale
    # con i lambda. Con pochi/nessun dato, lo shrinkage converge al prior 0.45.
    ht_ratio_h = _compute_ht_ratio(home_home)
    ht_ratio_a = _compute_ht_ratio(away_away)
    lambda_ht_home = lambda_home * ht_ratio_h
    lambda_ht_away = lambda_away * ht_ratio_a
    max_goals_ht = 4
    ht_grid = _build_score_grid(lambda_ht_home, lambda_ht_away, max_goals_ht)
    for _hg in (0, 1):
        for _ag in (0, 1):
            ht_grid[_hg, _ag] *= _dc_tau(_hg, _ag, lambda_ht_home, lambda_ht_away, rho=rho_league)
    _ht_total = float(ht_grid.sum()) or 1.0
    ht_grid = ht_grid / _ht_total
    _ht_hg = np.arange(max_goals_ht + 1).reshape(-1, 1)
    _ht_ag = np.arange(max_goals_ht + 1).reshape(1, -1)
    p_ht_home = float(ht_grid[_ht_hg > _ht_ag].sum())
    p_ht_draw = float(ht_grid[_ht_hg == _ht_ag].sum())
    p_ht_away = float(ht_grid[_ht_hg < _ht_ag].sum())
    # (#15) Renormalise HT 1X2 to sum to exactly 1 (same rationale as FT 1X2).
    _ht2_tot = p_ht_home + p_ht_draw + p_ht_away
    if _ht2_tot > 0:
        p_ht_home /= _ht2_tot
        p_ht_draw /= _ht2_tot
        p_ht_away /= _ht2_tot

    # (#4) Probability a team scores in the 1st half, with Beta-Binomial shrinkage
    # toward 0.5 (strength HT_GOAL_K matches) — consistent with the shrinkage used
    # everywhere else in the engine. Returns (prob, n_valid) so the hybrid blend
    # below can weight by how much data backs the empirical estimate.
    HT_GOAL_PRIOR = 0.5
    HT_GOAL_K = 5  # in matches

    def _team_p_goal_1h(matches: List[Dict[str, Any]]) -> Tuple[float, int]:
        recent = matches[-15:] if matches else []
        flags = []
        for m in recent:
            ht = m.get("halftime_for")
            if ht is None:
                continue
            flags.append(1 if ht > 0 else 0)
        n = len(flags)
        if n == 0:
            return HT_GOAL_PRIOR, 0
        shrunk = (HT_GOAL_K * HT_GOAL_PRIOR + sum(flags)) / (HT_GOAL_K + n)
        return shrunk, n

    # Coerenza contestuale: stessa lista usata per _compute_ht_ratio (home_home / away_away).
    p_home_1h, n_home_1h = _team_p_goal_1h(home_home)
    p_away_1h, n_away_1h = _team_p_goal_1h(away_away)
    p_goal_1h_freq = 1.0 - ((1 - p_home_1h) * (1 - p_away_1h))

    # --- HYBRID HT MODEL (#9 + #8) ---
    # (#9) Poisson term = P(>=1 goal in 1H) = 1 - P(0-0 at HT) taken from the SAME
    # Dixon-Coles-corrected HT grid used for ht_1x2 (coherent). The old term
    # 1 - exp(-lambda_1h) was the INDEPENDENT-Poisson P(0-0) and ignored the DC
    # correction, slightly overstating Over 0.5 1H.
    lambda_1h = lambda_home * ht_ratio_h + lambda_away * ht_ratio_a  # reported for diagnostics only
    p_goal_1h_poisson = 1.0 - float(ht_grid[0, 0])
    # (#8) Reliability-weighted blend instead of a fixed 50/50: trust the empirical
    # frequency in proportion to how much HT data backs it. n_eff is the MEAN of
    # the two sides' valid-match counts: the freq estimate combines both teams, so
    # one team lacking data shouldn't discard the other's observations (a min()
    # would). n_eff -> 0 only in the true cold-start (both teams without HT data),
    # where the blend leans fully on the model-based Poisson term; with full data
    # (both ~15) w_freq -> 0.6.
    K_HT_BLEND = 10.0
    n_eff = (n_home_1h + n_away_1h) / 2.0
    w_freq = n_eff / (n_eff + K_HT_BLEND)
    p_hybrid_1h = w_freq * p_goal_1h_freq + (1.0 - w_freq) * p_goal_1h_poisson
    # -----------------------

    analysis = {
        "model": "poisson_xg_hybrid_dc",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "league_id": int(league_id),
        "season_year": int(season_year),
        "fixture_id": int(fixture_id),
        "inputs": {
            "lambda_home": round(lambda_home, 4),
            "lambda_away": round(lambda_away, 4),
            "lambda_1h_tot": round(lambda_1h, 4),
            "league_home_avg": round(league_home_avg, 4),
            "league_away_avg": round(league_away_avg, 4),
            "league_total_avg": round(league_total_avg, 4),
            "league_home_xg_avg": round(league_home_xg_avg, 4),
            "league_away_xg_avg": round(league_away_xg_avg, 4),
            "home_matches_used": int(home_n_used),
            "away_matches_used": int(away_n_used),
            "home_xg_covered": int(stats15_h.get("xg_used", 0)),
            "away_xg_covered": int(stats15_a.get("xg_used", 0)),
            "home_xga_covered": int(stats15_h.get("xga_used", 0)),
            "away_xga_covered": int(stats15_a.get("xga_used", 0)),
            # Telemetry (#2): True when at least one xG/xGA term informed lambda;
            # False means lambda was computed on goals only (no xG coverage).
            "xg_blend_active": bool(xg_h_ok or xg_a_ok or xga_h_ok or xga_a_ok),
            "ht_ratio_home": round(ht_ratio_h, 3),
            "ht_ratio_away": round(ht_ratio_a, 3),
            "dc_rho": round(rho_league, 4),
        },
        "markets": {
            "1x2": {"H": round(p_home, 4), "D": round(p_draw, 4), "A": round(p_away, 4)},
            "over_1_5": {"True": round(p_over15, 4), "False": round(p_under15, 4)},
            "over_2_5": {"True": round(p_over25, 4), "False": round(p_under25, 4)},
            "over_3_5": {"True": round(p_over35, 4), "False": round(p_under35, 4)},
            "btts": {"True": round(p_btts, 4), "False": round(p_btts_no, 4)},
            "first_half_over_0_5": {
                "True": round(p_hybrid_1h, 4),
                "False": round(1.0 - p_hybrid_1h, 4),
                "details": {
                    "freq": round(p_goal_1h_freq, 4),
                    "poisson": round(p_goal_1h_poisson, 4),
                    "w_freq": round(w_freq, 4)
                }
            },
            "ht_1x2": {"H": round(p_ht_home, 4), "D": round(p_ht_draw, 4), "A": round(p_ht_away, 4)},
        },
        "coverage": {
            "windows_used": {
                "home": {"5": int(stats5_h.get("n_used", 0)), "10": int(stats10_h.get("n_used", 0)), "15": int(stats15_h.get("n_used", 0))},
                "away": {"5": int(stats5_a.get("n_used", 0)), "10": int(stats10_a.get("n_used", 0)), "15": int(stats15_a.get("n_used", 0))},
            },
            "xg_used": {"home": int(stats15_h.get("xg_used", 0)), "away": int(stats15_a.get("xg_used", 0))},
        },
    }
    
    # --- DYNAMIC BLACKLIST CHECK ---
    toxic_leagues = get_toxic_leagues()
    
    is_elite = False
    if int(league_id) not in toxic_leagues:
        # Il Filtro Trifecta: Freq >= 75%, Poisson >= 75%, Match Lambda >= 2.70
        is_elite = (p_goal_1h_freq >= 0.75 and 
                    p_goal_1h_poisson >= 0.75 and 
                    (lambda_home + lambda_away) >= 2.70)
    
    ht_pred = {
        "hybrid_prob": round(p_hybrid_1h, 4),
        "lambda_1h": round(lambda_1h, 4),
        "is_elite": is_elite,
        "details": {
            "freq": round(p_goal_1h_freq, 4),
            "poisson": round(p_goal_1h_poisson, 4),
            "w_freq": round(w_freq, 4)
        }
    }

    return analysis, ht_pred


# ==============================
# Mapping predictions → promoted + flat_summary
# ==============================

def build_promoted_and_summary(pred_obj: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    pred_obj è tipicamente data["response"][0] dell'endpoint /predictions.

    Ritorna:
      - promoted: campi in colonne (dashboard immediate)
      - summary: JSONB piatto con chiavi utili (flat_summary)
    """
    promoted: Dict[str, Any] = {}
    summary: Dict[str, Any] = {}

    predictions = pred_obj.get("predictions") or {}

    # winner
    winner = predictions.get("winner") or {}
    promoted["winner_team_id"] = winner.get("id")
    promoted["winner_name"] = winner.get("name")
    promoted["winner_comment"] = winner.get("comment")

    # core
    promoted["win_or_draw"] = predictions.get("win_or_draw")
    promoted["under_over_line"] = predictions.get("under_over")
    promoted["advice"] = predictions.get("advice")

    goals = predictions.get("goals") or {}
    promoted["goals_home_line"] = goals.get("home")
    promoted["goals_away_line"] = goals.get("away")

    percent = predictions.get("percent") or {}
    promoted["percent_home"] = _parse_percent_to_float(percent.get("home"))
    promoted["percent_draw"] = _parse_percent_to_float(percent.get("draw"))
    promoted["percent_away"] = _parse_percent_to_float(percent.get("away"))

    # flat_summary (chiavi utili e immediate)
    summary["prediction_advice"] = promoted["advice"]
    summary["prediction_under_over"] = promoted["under_over_line"]
    summary["prediction_win_or_draw"] = promoted["win_or_draw"]

    summary["winner_name"] = promoted["winner_name"]
    summary["winner_comment"] = promoted["winner_comment"]

    summary["percent_home"] = promoted["percent_home"]
    summary["percent_draw"] = promoted["percent_draw"]
    summary["percent_away"] = promoted["percent_away"]

    # teams last_5 (molto utile)
    summary["home_last5_form"] = _safe_get(pred_obj, ["teams", "home", "last_5", "form"])
    summary["away_last5_form"] = _safe_get(pred_obj, ["teams", "away", "last_5", "form"])
    summary["home_last5_att"] = _safe_get(pred_obj, ["teams", "home", "last_5", "att"])
    summary["away_last5_att"] = _safe_get(pred_obj, ["teams", "away", "last_5", "att"])
    summary["home_last5_def"] = _safe_get(pred_obj, ["teams", "home", "last_5", "def"])
    summary["away_last5_def"] = _safe_get(pred_obj, ["teams", "away", "last_5", "def"])

    summary["home_last5_goals_for_avg"] = _safe_get(pred_obj, ["teams", "home", "last_5", "goals", "for", "average"])
    summary["away_last5_goals_for_avg"] = _safe_get(pred_obj, ["teams", "away", "last_5", "goals", "for", "average"])
    summary["home_last5_goals_against_avg"] = _safe_get(pred_obj, ["teams", "home", "last_5", "goals", "against", "average"])
    summary["away_last5_goals_against_avg"] = _safe_get(pred_obj, ["teams", "away", "last_5", "goals", "against", "average"])

    # comparison (utile per dashboard)
    comparison = pred_obj.get("comparison") or {}
    summary["comparison_form_home"] = _safe_get(comparison, ["form", "home"])
    summary["comparison_form_away"] = _safe_get(comparison, ["form", "away"])
    summary["comparison_goals_home"] = _safe_get(comparison, ["goals", "home"])
    summary["comparison_goals_away"] = _safe_get(comparison, ["goals", "away"])
    summary["comparison_total_home"] = _safe_get(comparison, ["total", "home"])
    summary["comparison_total_away"] = _safe_get(comparison, ["total", "away"])

    return promoted, summary


# ==============================
# DB upsert
# ==============================

def upsert_prediction_row(row: Dict[str, Any]) -> None:
    sb = get_supabase_client()
    _db_execute(
        lambda: sb.table("fixture_predictions").upsert(row, on_conflict="fixture_id").execute(),
        what="upsert fixture_predictions fixture_id=%s" % row.get("fixture_id"),
    )


# ==============================
# Deferred writer (batch upsert predizioni)
# ==============================

# Chiavi di contesto presenti in ogni riga di fixture_predictions (da extract_fixture_context).
_CTX_KEYS: Tuple[str, ...] = (
    "fixture_id", "league_id", "league_name", "season_year", "fixture_date",
    "home_team_id", "home_team_name", "away_team_id", "away_team_name",
)

# Campi "promoted" azzerati nei rami no_coverage/empty/error (identici al loop).
_PROMOTED_NULL_KEYS: Tuple[str, ...] = (
    "winner_team_id", "winner_name", "winner_comment", "win_or_draw", "advice",
    "percent_home", "percent_draw", "percent_away",
    "under_over_line", "goals_home_line", "goals_away_line",
)


def _error_row_from_ctx(ctx: Dict[str, Any], now_iso: str, exc: BaseException) -> Dict[str, Any]:
    """Riga status='error' IDENTICA (stesse chiavi, stessi valori) a quella che
    il ramo `except` del loop principale costruisce a mano."""
    err_row: Dict[str, Any] = dict(ctx)
    err_row["status"] = "error"
    err_row["error_message"] = str(exc)[:500]
    err_row["raw_json"] = None
    err_row["flat_summary"] = None
    for k in _PROMOTED_NULL_KEYS:
        err_row[k] = None
    err_row["updated_at"] = now_iso
    return err_row


def _error_row_from_ok_row(row: Dict[str, Any], exc: Exception) -> Dict[str, Any]:
    """
    Replica ESATTA della riga costruita dal ramo `except` del loop principale
    quando la scrittura di una riga status='ok' fallisce: stessa fixture,
    status='error', promoted azzerati, stesso raw_json e stesso updated_at.
    """
    err_row: Dict[str, Any] = {k: row.get(k) for k in _CTX_KEYS}
    err_row["status"] = "error"
    err_row["error_message"] = str(exc)[:500]
    err_row["raw_json"] = row.get("raw_json")
    err_row["flat_summary"] = None
    for k in _PROMOTED_NULL_KEYS:
        err_row[k] = None
    err_row["updated_at"] = row.get("updated_at")
    return err_row


def _group_rows_by_keys(rows: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    PostgREST richiede chiavi uniformi in un insert/upsert bulk: raggruppa le
    righe per insieme di chiavi preservando l'ordine di accodamento.
    (In pratica tutte le righe del loop hanno lo stesso insieme di chiavi,
    quindi il risultato e' quasi sempre un unico gruppo.)
    """
    groups: Dict[frozenset, List[Dict[str, Any]]] = {}
    order: List[frozenset] = []
    for row in rows:
        key = frozenset(row.keys())
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    return [groups[k] for k in order]


# Righe per richiesta nell'upsert di odds/analisi (_write_post_ops). Ogni
# riga porta raw_json + raw_json_odds + db_json_analisi, quindi e' piu'
# pesante di una riga di prediction: blocchi piu' piccoli di chunk_size per
# restare lontani dallo statement_timeout. Se un blocco non passa comunque,
# viene dimezzato come quelli delle predizioni.
_POST_OPS_CHUNK_SIZE = 25


def _segna_confermate(confermate: Optional[Set[int]], rows: List[Dict[str, Any]]) -> None:
    """Annota i fixture_id delle righe di prediction scritte tali e quali."""
    if confermate is None:
        return
    for riga in rows:
        fid = riga.get("fixture_id")
        if fid is not None:
            confermate.add(int(fid))


class _DeferredWriter:
    """
    Accumula le scritture del loop principale e le esegue a blocchi per
    ridurre i round-trip verso Supabase, A PARITA' di valori scritti:

    - le righe di fixture_predictions (upsert on_conflict=fixture_id) vengono
      scritte in UN upsert batch per blocco; se il batch fallisce anche dopo i
      retry viene DIMEZZATO fino alla singola riga, replicando su quest'ultima
      la semantica per-fixture odierna;
    - odds e analisi vengono scritte DOPO l'upsert delle predizioni del
      blocco (ordine per fixture prediction -> odds -> analysis invariato).
      Per le fixture la cui riga di prediction e' stata APPENA scritta tale e
      quale in questo flush, odds e analisi viaggiano in upsert a blocchi
      (vedi _write_post_ops): riga = riga di prediction + colonne delle
      UPDATE, applicate nello stesso ordine. Per tutte le altre (riga non
      confermata, riscritta come 'error', assente) resta la UPDATE singola di
      sempre. I payload sono costruiti al momento dell'accodamento, quindi i
      VALORI (timestamp inclusi) sono identici al percorso storico.

    Nota: se la stessa fixture viene ri-accodata prima del flush (caso
    duplicati / ramo ok->error), si flusha prima, preservando l'ordine di
    scrittura odierno.

    Nessuna scrittura puo' piu' interrompere il run: cio' che non si recupera
    nemmeno dopo i retry finisce in _RUN_FAILURES (riepilogo a fine run +
    exit code != 0 da main()).
    """

    # 25 righe (~5s a 0,2s/riga): sotto lo statement_timeout PostgREST di 8s.
    # Prima era 100 (~20s): andava in 57014 anche a DB poco carico (run
    # 35837269470), e persino il dimezzamento a 50 restava sopra la soglia.
    # 25 e' la stessa dimensione gia' scelta per i blocchi uniti delle
    # post_ops (_POST_OPS_CHUNK_SIZE).
    def __init__(self, chunk_size: int = 25) -> None:
        self.chunk_size = chunk_size
        self._pred_rows: List[Dict[str, Any]] = []
        self._post_ops: List[Tuple[str, int, Dict[str, Any]]] = []  # (kind, fixture_id, row)
        self._pending_fixture_ids: Set[int] = set()

    def queue_prediction(self, row: Dict[str, Any]) -> None:
        fid = row.get("fixture_id")
        if fid is not None and int(fid) in self._pending_fixture_ids:
            # Stessa fixture gia' in coda: flush per mantenere l'ordine di
            # scrittura odierno (la seconda scrittura sovrascrive la prima).
            self.flush()
        self._pred_rows.append(row)
        if fid is not None:
            self._pending_fixture_ids.add(int(fid))

    def queue_odds(self, fixture_id: int, row: Dict[str, Any]) -> None:
        self._post_ops.append(("odds", fixture_id, row))

    def queue_analysis(self, fixture_id: int, row: Dict[str, Any]) -> None:
        self._post_ops.append(("analysis", fixture_id, row))

    def maybe_flush(self) -> None:
        if len(self._pred_rows) >= self.chunk_size:
            self.flush()

    def flush(self) -> None:
        pred_rows = self._pred_rows
        post_ops = self._post_ops
        self._pred_rows = []
        self._post_ops = []
        self._pending_fixture_ids = set()

        if not pred_rows and not post_ops:
            return

        sb = get_supabase_client()

        # 1) Predizioni: upsert batch con retry; se il batch non passa lo si
        #    dimezza fino alla singola riga (vedi _upsert_rows). `confermate`
        #    raccoglie le fixture la cui riga e' stata scritta TALE E QUALE.
        confermate: Set[int] = set()
        for group in _group_rows_by_keys(pred_rows):
            self._upsert_rows(sb, group, confermate)

        # 2) Odds e analisi (per ogni fixture: dopo la sua riga di prediction).
        self._write_post_ops(sb, pred_rows, post_ops, confermate)

    # ------------------------------------------------------------------
    # Odds e analisi: upsert a blocchi dove e' equivalente, UPDATE altrove
    # ------------------------------------------------------------------

    def _write_post_ops(
        self,
        sb: Any,
        pred_rows: List[Dict[str, Any]],
        post_ops: List[Tuple[str, int, Dict[str, Any]]],
        confermate: Set[int],
    ) -> None:
        """Scrive odds e analisi con MENO richieste e gli STESSI dati.

        Prima: una UPDATE ... eq(fixture_id) per ogni post_op (2 round-trip per
        fixture). Ora, per una fixture F la cui riga di prediction R e' stata
        appena scritta TALE E QUALE in questo flush (F in `confermate`), la
        sequenza storica

            upsert(R) ; update(odds) where F ; update(analisi) where F

        lascia sulla riga: le colonne di R, poi quelle delle due UPDATE nello
        stesso ordine (updated_at = quello dell'ultima), e tutte le ALTRE
        colonne intatte. Un upsert on_conflict=fixture_id (merge-duplicates)
        della riga U = R | odds | analisi (dict.update nello stesso ordine)
        scrive ESATTAMENTE le stesse colonne con gli stessi valori e lascia
        intatte le altre. Si reinvia R per intero, e NON le sole colonne delle
        UPDATE, perche' Postgres controlla i NOT NULL della riga proposta
        (es. status) PRIMA di risolvere il conflitto: una riga monca verrebbe
        rifiutata anche con la riga gia' presente. R pero' e' appena passata,
        quindi U li soddisfa; e la riga esiste gia', quindi l'upsert non puo'
        inserire una riga monca.

        Restano sulla UPDATE singola di sempre (stesso codice, stessi log,
        stesso registro): le post_ops di fixture senza riga di prediction nel
        flush, con la riga non confermata (fallita o riscritta come 'error'),
        o presenti piu' volte; e, come ricaduta, quelle di un blocco che non
        passa nemmeno alla riga singola o che si ferma per il freno DB.
        """
        if not post_ops:
            return

        conteggio: Dict[int, int] = {}
        for row in pred_rows:
            fid = row.get("fixture_id")
            if fid is not None:
                conteggio[int(fid)] = conteggio.get(int(fid), 0) + 1
        righe_pred: Dict[int, Dict[str, Any]] = {}
        for row in pred_rows:
            fid = row.get("fixture_id")
            if fid is None:
                continue
            chiave = int(fid)
            if conteggio.get(chiave) == 1 and chiave in confermate:
                righe_pred[chiave] = row

        unite: Dict[int, Dict[str, Any]] = {}
        ops_per_fixture: Dict[int, List[Tuple[str, int, Dict[str, Any]]]] = {}
        singole: List[Tuple[str, int, Dict[str, Any]]] = []
        for kind, fixture_id, row in post_ops:
            chiave = int(fixture_id) if fixture_id is not None else None
            if chiave is None or chiave not in righe_pred:
                # GUARDIA: nessuna riga appena scritta -> UPDATE di sempre
                # (su riga assente non scrive nulla: mai un insert monco).
                singole.append((kind, fixture_id, row))
                continue
            if chiave not in unite:
                unite[chiave] = dict(righe_pred[chiave])
                ops_per_fixture[chiave] = []
            unite[chiave].update(row)
            ops_per_fixture[chiave].append((kind, fixture_id, row))

        for group in _group_rows_by_keys(list(unite.values())):
            for i in range(0, len(group), _POST_OPS_CHUNK_SIZE):
                self._upsert_post_ops(sb, group[i:i + _POST_OPS_CHUNK_SIZE], ops_per_fixture)

        for kind, fixture_id, row in singole:
            self._update_post_op(sb, kind, fixture_id, row)

    def _upsert_post_ops(
        self,
        sb: Any,
        rows: List[Dict[str, Any]],
        ops_per_fixture: Dict[int, List[Tuple[str, int, Dict[str, Any]]]],
    ) -> None:
        """Upsert di un blocco di righe unite (prediction + odds + analisi).

        Stessa scala di _upsert_rows: retry, poi DIMEZZAMENTO fino alla riga
        singola. Se la riga singola non passa, o il freno DB e' attivo, le
        post_ops delle fixture coinvolte ricadono sulla UPDATE di sempre
        (_update_post_op): stessi retry, stesso registro, stesso payload per
        il secondo giro, esattamente come prima di questo intervento.
        """
        if not rows:
            return

        def _ricaduta(blocco: List[Dict[str, Any]]) -> None:
            for riga in blocco:
                for kind, fixture_id, row in ops_per_fixture.get(int(riga["fixture_id"]), []):
                    self._update_post_op(sb, kind, fixture_id, row)

        if len(rows) == 1:
            fixture_id = rows[0].get("fixture_id")
            try:
                _db_execute(
                    lambda: sb.table("fixture_predictions").upsert(rows[0], on_conflict="fixture_id").execute(),
                    what="upsert odds/analisi fixture_id=%s" % fixture_id,
                )
                return
            except Exception as e:  # noqa: BLE001 - ricaduta sulla UPDATE di sempre
                logger.warning(
                    "Upsert odds/analisi fixture_id=%s fallito (%s): ricado sulle UPDATE singole.",
                    fixture_id, str(e)[:200],
                )
            _ricaduta(rows)
            return

        try:
            _db_execute(
                lambda: sb.table("fixture_predictions").upsert(rows, on_conflict="fixture_id").execute(),
                what="upsert odds/analisi (%s righe)" % len(rows),
                attempts=_DB_RETRY_ATTEMPTS_BATCH,
            )
            return
        except Exception as batch_err:  # noqa: BLE001 - si dimezza sotto
            logger.warning(
                "Upsert odds/analisi a blocco fallito (%s righe): %s - ritento a blocchi piu' piccoli.",
                len(rows), str(batch_err)[:200],
            )

        motivo = _db_retry_exhausted()
        if motivo is not None:
            # Freno attivo: niente dimezzamento. Si torna alle UPDATE di
            # sempre, che sotto il freno fanno un solo tentativo ciascuna e
            # registrano cio' che non passa (come prima di questo intervento).
            logger.error(
                "Freno DB attivo (%s): blocco odds/analisi di %s righe NON dimezzato, "
                "ricado sulle UPDATE singole.", motivo, len(rows),
            )
            _ricaduta(rows)
            return

        half = len(rows) // 2
        self._upsert_post_ops(sb, rows[:half], ops_per_fixture)
        self._upsert_post_ops(sb, rows[half:], ops_per_fixture)

    def _update_post_op(self, sb: Any, kind: str, fixture_id: int, row: Dict[str, Any]) -> None:
        """UPDATE singola di odds o analisi: il percorso storico, invariato."""
        if kind == "odds":
            try:
                resp = _db_execute(
                    lambda: sb.table("fixture_predictions").update(row).eq("fixture_id", fixture_id).execute(),
                    what="update odds fixture_id=%s" % fixture_id,
                )
                if not getattr(resp, "data", None):
                    logger.warning("⚠️ Nessuna riga fixture_predictions trovata per fixture_id=%s (odds non salvate)", fixture_id)
            except Exception as e:
                # Prima un solo 57014 qui risaliva fino a main() e uccideva
                # il run intero: ora la fixture viene registrata e tutte le
                # altre vengono comunque scritte. La riga viene conservata:
                # il secondo giro di fine run la ritenta, perche' un
                # semplice rilancio NON la recupererebbe (la prediction e'
                # gia' 'ok', il prefetch la salta).
                _record_failure(fixture_id, "odds", e,
                                payload={"kind": "odds", "row": row}, manuale=True)
        else:
            # Come il blocco try/except del loop attorno a upsert_analysis_data:
            # un errore di scrittura dell'analisi NON blocca le altre fixture.
            try:
                resp = _db_execute(
                    lambda: sb.table("fixture_predictions").update(row).eq("fixture_id", fixture_id).execute(),
                    what="update analisi fixture_id=%s" % fixture_id,
                )
                if not getattr(resp, "data", None):
                    logger.warning("Nessuna riga fixture_predictions trovata per fixture_id=%s (dati non salvati)", fixture_id)
            except Exception as e:
                logger.warning("db_json_analisi failed fixture_id=%s: %s", fixture_id, e)
                # Conservata per il secondo giro come le odds. Qui pero'
                # ht_predictions resta NULL, quindi il rilancio riprende
                # comunque la fixture: non e' "da recuperare a mano".
                _record_failure(fixture_id, "analisi", e,
                                payload={"kind": "analysis", "row": row})

    # ------------------------------------------------------------------
    # Scrittura delle righe di prediction: batch -> meta' -> riga singola
    # ------------------------------------------------------------------

    def _upsert_rows(
        self,
        sb: Any,
        rows: List[Dict[str, Any]],
        confermate: Optional[Set[int]] = None,
        _primo_livello: bool = True,
    ) -> None:
        """Upsert di un blocco di righe, con retry sugli errori transitori.

        Se il blocco non passa nemmeno dopo i retry viene DIMEZZATO e i due
        mezzi ritentati (blocchi piu' piccoli costano meno di 8 s di
        statement_timeout), fino alla singola riga. Ogni tentativo scrive gli
        STESSI valori con lo stesso on_conflict: e' idempotente, un blocco
        gia' passato in parte non crea duplicati.

        ``confermate`` (se dato) riceve i fixture_id delle righe scritte TALE
        E QUALE (non quelle riscritte come 'error' ne' quelle perse).

        ``_primo_livello`` (uso interno, non passare dal chiamante esterno)
        distingue il blocco appena arrivato da flush() dai suoi discendenti
        gia' dimezzati: vedi il commento sul freno qui sotto.
        """
        if not rows:
            return
        if len(rows) == 1:
            self._upsert_single(sb, rows[0], confermate)
            return

        try:
            _db_execute(
                lambda: sb.table("fixture_predictions").upsert(rows, on_conflict="fixture_id").execute(),
                what="upsert fixture_predictions (%s righe)" % len(rows),
                attempts=_DB_RETRY_ATTEMPTS_BATCH,
            )
            _segna_confermate(confermate, rows)
            return
        except Exception as batch_err:
            logger.warning(
                "⚠️ Upsert batch fixture_predictions fallito (%s righe): %s — ritento a blocchi piu' piccoli.",
                len(rows), batch_err,
            )
            # Python cancella `batch_err` all'uscita dell'except: va conservato.
            errore = batch_err

        # Freno: a DB in ginocchio il dimezzamento ricorsivo genererebbe
        # centinaia di richieste destinate a fallire. Si smette qui e il
        # blocco viene registrato come perso (nulla di ingoiato: exit != 0).
        # ECCEZIONE: il blocco appena arrivato da flush() (_primo_livello)
        # ha SEMPRE diritto ad almeno un dimezzamento, anche se il freno e'
        # gia' attivo per l'esaurimento di un blocco precedente nello stesso
        # run. Senza questa eccezione un freno scattato a meta' giornata
        # perderebbe INTERO ogni blocco successivo (anche uno da 25 righe,
        # 5s, che probabilmente passerebbe dimezzato a 12+13) senza mai
        # provare a rimpicciolirlo. Solo un discendente che ha GIA' avuto la
        # sua occasione (_primo_livello=False) si arrende subito, come prima.
        motivo = _db_retry_exhausted()
        if motivo is not None and not _primo_livello:
            logger.error(
                "Freno DB attivo (%s): blocco di %s righe NON dimezzato, "
                "registrato come perso.", motivo, len(rows),
            )
            for riga in rows:
                _record_failure(
                    riga.get("fixture_id"),
                    "prediction(%s)" % riga.get("status"),
                    errore,
                )
            return
        if motivo is not None:
            logger.warning(
                "Freno DB attivo (%s) ma il blocco di %s righe non ha ancora "
                "avuto un dimezzamento: si prova UNA volta prima di arrendersi.",
                motivo, len(rows),
            )

        half = len(rows) // 2
        self._upsert_rows(sb, rows[:half], confermate, _primo_livello=False)
        self._upsert_rows(sb, rows[half:], confermate, _primo_livello=False)

    def _upsert_single(
        self,
        sb: Any,
        row: Dict[str, Any],
        confermate: Optional[Set[int]] = None,
    ) -> None:
        """Upsert di UNA riga con retry; semantica per-fixture invariata."""
        fixture_id = row.get("fixture_id")
        try:
            _db_execute(
                lambda: sb.table("fixture_predictions").upsert(row, on_conflict="fixture_id").execute(),
                what="upsert fixture_predictions fixture_id=%s" % fixture_id,
            )
            _segna_confermate(confermate, [row])
            return
        except Exception as e:
            if row.get("status") != "ok":
                # Prima un errore di scrittura nei rami no_coverage/empty/error
                # propagava e fermava il run: ora si registra e si prosegue.
                _record_failure(fixture_id, "prediction(%s)" % row.get("status"), e)
                return

            # Ramo ok: semantica odierna invariata - la fixture viene riscritta
            # con status='error'. I dati della predizione restano comunque
            # PERSI, quindi la fixture entra lo stesso nel registro.
            logger.exception("❌ error fixture_id=%s: %s", fixture_id, e)
            _record_failure(fixture_id, "prediction(ok)", e)
            err_row = _error_row_from_ok_row(row, e)
            try:
                _db_execute(
                    lambda: sb.table("fixture_predictions").upsert(err_row, on_conflict="fixture_id").execute(),
                    what="upsert riga di errore fixture_id=%s" % fixture_id,
                )
            except Exception as e2:
                _record_failure(fixture_id, "prediction(error_row)", e2)


# ==============================
# Runner
# ==============================

def _queue_odds_for_fixture(
    writer: "_DeferredWriter",
    api: APIFootballClient,
    fixture_id: int,
    league_id: int,
    season_year: int,
    odds_coverage_cache: Dict[Tuple[int, int], bool],
    odds_cache: Dict[Tuple[int, int], Dict[str, Any]],
) -> None:
    """Accoda le odds della fixture: identica ai 4 rami del loop di prima.

    Se la coverage delle odds non e' leggibile propaga CoverageReadError senza
    accodare nulla: raw_json_odds=NULL sarebbe un dato falso.
    """
    if odds_coverage_true(league_id, season_year, odds_coverage_cache):
        odds_json = fetch_odds_for_league_season(api, league_id, season_year, odds_cache)
        odds_item = extract_odds_for_fixture(odds_json, fixture_id)
        writer.queue_odds(fixture_id, _build_odds_row(odds_item))
        logger.info("💾 odds salvate per fixture_id=%s (league_id=%s season=%s)", fixture_id, league_id, season_year)
    else:
        writer.queue_odds(fixture_id, _build_odds_row(None))
        logger.info("⏭️ odds no_coverage fixture_id=%s (league_id=%s season=%s)", fixture_id, league_id, season_year)


def run_for_date(target_date: str) -> None:
    # Reset cache blacklist per ogni run: evita blacklist stantia in processi multi-data
    global _TOXIC_LEAGUES_CACHE
    _TOXIC_LEAGUES_CACHE = None

    api = APIFootballClient()
    fixtures = fetch_fixtures_for_date(api, target_date)

    if not fixtures:
        logger.info("✅ Nessuna fixture per %s. Fine.", target_date)
        return

    coverage_cache: Dict[Tuple[int, int], bool] = {}
    odds_coverage_cache: Dict[Tuple[int, int], bool] = {}
    odds_cache: Dict[Tuple[int, int], Dict[str, Any]] = {}
    match_cache: Dict[Tuple[int, int], Dict[str, Any]] = {}
    xg_cache: Dict[Tuple[int, int], Dict[Tuple[int, int], float]] = {}

    ok_count = 0
    empty_count = 0
    no_cov_count = 0
    err_count = 0
    skipped_count = 0
    skipped_existing_count = 0
    coverage_unreadable_count = 0  # fixture NON toccate: coverage illeggibile

    # ✅ PREFETCH BATCH: una query (a chunk) al posto di ~1 SELECT per fixture.
    # Stessa condizione di prediction_already_done (status='ok' E ht_predictions
    # non nullo). Il set viene aggiornato dopo ogni scrittura "ok" del loop per
    # replicare il comportamento del check per-fixture anche su eventuali
    # fixture duplicate nella stessa run.
    all_fixture_ids: List[int] = []
    for _fx in fixtures:
        _fid = (_fx.get("fixture") or {}).get("id")
        if _fid is not None:
            all_fixture_ids.append(int(_fid))
    done_fixture_ids = prefetch_predictions_done(all_fixture_ids)

    # Writer differito: batcha gli upsert di fixture_predictions a blocchi,
    # mantenendo per ogni fixture l'ordine prediction -> odds -> analysis.
    # chunk_size = default di _DeferredWriter (25 righe, vedi li' il motivo).
    writer = _DeferredWriter()

    try:
        for fx in fixtures:
            # Flush a blocchi: sicuro qui perche' tra un'iterazione e l'altra
            # non ci sono scritture "a meta'" per una singola fixture.
            writer.maybe_flush()

            ctx = extract_fixture_context(fx)
            if ctx is None:
                skipped_count += 1
                logger.warning("⚠️ Fixture con dati incompleti (no fixture_id/league_id/season), skip.")
                continue

            fixture_id = ctx["fixture_id"]
            league_id = ctx["league_id"]
            season_year = ctx["season_year"]

            # ✅ SKIP se già fatto (status='ok') — check sul set prefetchato
            if fixture_id in done_fixture_ids:
                skipped_existing_count += 1
                logger.info("⏭️ skip fixture_id=%s (prediction già presente: status=ok)", fixture_id)
                continue

            now_iso = datetime.now(timezone.utc).isoformat()

            # Coverage check
            try:
                has_predictions = predictions_coverage_true(league_id, season_year, coverage_cache)
            except CoverageReadError as e:
                # La copertura non si e' potuta leggere: la fixture NON viene
                # toccata. Scrivere 'no_coverage' qui sarebbe un dato FALSO,
                # indistinguibile da un'assenza vera di copertura. Non avendo
                # scritto alcuno status, il rilancio sulla stessa data la
                # riprende (il prefetch salta solo gli status='ok').
                coverage_unreadable_count += 1
                _record_failure(fixture_id, "coverage-read", e)
                continue

            if not has_predictions:
                row = {
                    **ctx,
                    "status": "no_coverage",
                    "error_message": None,

                    "raw_json": None,
                    "flat_summary": None,

                    "winner_team_id": None,
                    "winner_name": None,
                    "winner_comment": None,
                    "win_or_draw": None,
                    "advice": None,
                    "percent_home": None,
                    "percent_draw": None,
                    "percent_away": None,
                    "under_over_line": None,
                    "goals_home_line": None,
                    "goals_away_line": None,

                    "updated_at": now_iso,
                }
                writer.queue_prediction(row)
                no_cov_count += 1
                logger.info("⏭️ no_coverage fixture_id=%s (league_id=%s season=%s)", fixture_id, league_id, season_year)
                # dopo prediction, inserisco odds per questo fixture
                try:
                    _queue_odds_for_fixture(writer, api, fixture_id, league_id,
                                            season_year, odds_coverage_cache, odds_cache)
                except CoverageReadError as e:
                    # Coverage odds illeggibile: NON si scrive raw_json_odds=NULL.
                    _record_failure(fixture_id, "coverage-read-odds", e)
                except Exception as e:
                    # Errore dell'API-Football sulle quote (rete, 429, JSON
                    # malformato): prima risaliva fuori dal for e uccideva il
                    # run. La riga di prediction e' gia' accodata, quindi la
                    # fixture prosegue e l'anomalia resta visibile.
                    _record_failure(fixture_id, "odds-fetch", e)

                # db_json_analisi (sempre)
                try:
                    res = compute_db_json_analisi(ctx, match_cache, xg_cache)
                    if res:
                        analysis_json, ht_pred = res
                        writer.queue_analysis(fixture_id, _build_analysis_row(fixture_id, analysis_json, ht_pred))
                except Exception as e:
                    logger.warning("db_json_analisi failed fixture_id=%s: %s", fixture_id, e)
                    _record_failure(fixture_id, "analisi-calcolo", e)
                continue

            # Call predictions
            logger.info("🔮 /predictions fixture_id=%s", fixture_id)
            try:
                data = api.call("/predictions", params={"fixture": str(fixture_id)})
            except Exception as e:
                # Prima un errore dell'API-Football qui (rete, 429, JSON
                # malformato) risaliva fuori dal for e UCCIDEVA il run: tutte
                # le fixture successive restavano senza predizioni. Ora la
                # fixture prende la semantica di errore GIA' esistente per
                # questo ramo (status='error', promoted azzerati) e il run
                # prosegue. status != 'ok' => il rilancio la riprende.
                writer.queue_prediction(_error_row_from_ctx(ctx, now_iso, e))
                err_count += 1
                logger.exception("❌ error fixture_id=%s: %s", fixture_id, e)
                _record_failure(fixture_id, "predictions-fetch", e)
                continue

            resp_list = (data or {}).get("response") or []

            if not data or len(resp_list) == 0:
                row = {
                    **ctx,
                    "status": "empty",
                    "error_message": None,

                    "raw_json": data if data else None,
                    "flat_summary": None,

                    "winner_team_id": None,
                    "winner_name": None,
                    "winner_comment": None,
                    "win_or_draw": None,
                    "advice": None,
                    "percent_home": None,
                    "percent_draw": None,
                    "percent_away": None,
                    "under_over_line": None,
                    "goals_home_line": None,
                    "goals_away_line": None,

                    "updated_at": now_iso,
                }
                writer.queue_prediction(row)
                empty_count += 1
                logger.warning("⚠️ empty fixture_id=%s", fixture_id)
                # dopo prediction, inserisco odds per questo fixture
                try:
                    _queue_odds_for_fixture(writer, api, fixture_id, league_id,
                                            season_year, odds_coverage_cache, odds_cache)
                except CoverageReadError as e:
                    # Coverage odds illeggibile: NON si scrive raw_json_odds=NULL.
                    _record_failure(fixture_id, "coverage-read-odds", e)
                except Exception as e:
                    # Errore dell'API-Football sulle quote (rete, 429, JSON
                    # malformato): prima risaliva fuori dal for e uccideva il
                    # run. La riga di prediction e' gia' accodata, quindi la
                    # fixture prosegue e l'anomalia resta visibile.
                    _record_failure(fixture_id, "odds-fetch", e)

                # db_json_analisi (sempre)
                try:
                    res = compute_db_json_analisi(ctx, match_cache, xg_cache)
                    if res:
                        analysis_json, ht_pred = res
                        writer.queue_analysis(fixture_id, _build_analysis_row(fixture_id, analysis_json, ht_pred))
                except Exception as e:
                    logger.warning("db_json_analisi failed fixture_id=%s: %s", fixture_id, e)
                    _record_failure(fixture_id, "analisi-calcolo", e)
                continue

            try:
                pred_obj = resp_list[0]
                promoted, summary = build_promoted_and_summary(pred_obj)

                row = {
                    **ctx,
                    "status": "ok",
                    "error_message": None,

                    "raw_json": data,
                    "flat_summary": summary,

                    **promoted,

                    "updated_at": now_iso,
                }
                writer.queue_prediction(row)
                ok_count += 1
                logger.info("✅ ok fixture_id=%s", fixture_id)

                # dopo prediction, inserisco odds per questo fixture
                try:
                    _queue_odds_for_fixture(writer, api, fixture_id, league_id,
                                            season_year, odds_coverage_cache, odds_cache)
                except CoverageReadError as e:
                    # Coverage odds illeggibile: NON si scrive raw_json_odds=NULL.
                    _record_failure(fixture_id, "coverage-read-odds", e)

                # db_json_analisi (sempre)
                try:
                    res = compute_db_json_analisi(ctx, match_cache, xg_cache)
                    if res:
                        analysis_json, ht_pred = res
                        writer.queue_analysis(fixture_id, _build_analysis_row(fixture_id, analysis_json, ht_pred))
                        # Da questo momento la fixture soddisfa la condizione di
                        # prediction_already_done (status='ok' + ht_predictions):
                        # aggiorna il set per eventuali ri-controlli nella stessa run.
                        done_fixture_ids.add(fixture_id)
                except Exception as e:
                    logger.warning("db_json_analisi failed fixture_id=%s: %s", fixture_id, e)
                    _record_failure(fixture_id, "analisi-calcolo", e)

            except Exception as e:
                row = {
                    **ctx,
                    "status": "error",
                    "error_message": str(e)[:500],

                    "raw_json": data if data else None,
                    "flat_summary": None,

                    "winner_team_id": None,
                    "winner_name": None,
                    "winner_comment": None,
                    "win_or_draw": None,
                    "advice": None,
                    "percent_home": None,
                    "percent_draw": None,
                    "percent_away": None,
                    "under_over_line": None,
                    "goals_home_line": None,
                    "goals_away_line": None,

                    "updated_at": now_iso,
                }
                writer.queue_prediction(row)
                err_count += 1
                logger.exception("❌ error fixture_id=%s: %s", fixture_id, e)

                # dopo prediction (errore), inserisco odds per questo fixture
                try:
                    _queue_odds_for_fixture(writer, api, fixture_id, league_id,
                                            season_year, odds_coverage_cache, odds_cache)
                except CoverageReadError as e:
                    # Coverage odds illeggibile: NON si scrive raw_json_odds=NULL.
                    _record_failure(fixture_id, "coverage-read-odds", e)
                except Exception as e:
                    # Errore dell'API-Football sulle quote (rete, 429, JSON
                    # malformato): prima risaliva fuori dal for e uccideva il
                    # run. La riga di prediction e' gia' accodata, quindi la
                    # fixture prosegue e l'anomalia resta visibile.
                    _record_failure(fixture_id, "odds-fetch", e)

                # db_json_analisi (sempre)
                try:
                    res = compute_db_json_analisi(ctx, match_cache, xg_cache)
                    if res:
                        analysis_json, ht_pred = res
                        writer.queue_analysis(fixture_id, _build_analysis_row(fixture_id, analysis_json, ht_pred))
                except Exception as e:
                    logger.warning("db_json_analisi failed fixture_id=%s: %s", fixture_id, e)
                    _record_failure(fixture_id, "analisi-calcolo", e)
    finally:
        # Flush finale garantito: anche se la run si interrompe, quanto gia'
        # accodato viene scritto (oggi a quel punto sarebbe gia' su DB).
        writer.flush()

    # SECONDO GIRO sulle sole scritture post-prediction rimaste indietro
    # (odds/analisi): la loro fixture ha gia' la prediction 'ok' a DB, quindi
    # il rilancio di domani la salterebbe e le odds resterebbero NULL per
    # sempre. Va fatto PRIMA del riepilogo, cosi' il riepilogo dice il vero.
    _retry_failed_post_ops()

    logger.info(
        "🏁 RIEPILOGO %s → ok=%s empty=%s no_coverage=%s error=%s skipped=%s skipped_existing=%s",
        target_date, ok_count, empty_count, no_cov_count, err_count, skipped_count, skipped_existing_count
    )

    if coverage_unreadable_count:
        logger.error(
            "Fixture NON elaborate per coverage illeggibile: %s "
            "(nessuno status scritto: il rilancio sulla stessa data le recupera)",
            coverage_unreadable_count,
        )

    # Anomalie non recuperate: elenco esplicito (main() esce != 0).
    _log_failures_summary(target_date)

    # --- SECONDO MOTORE: ML ensemble, aggiunta ADDITIVA e NON-FATALE ---
    # Popola `model_predictions_json` per le partite del giorno (come Poisson->
    # db_json_analisi). Gira DOPO il loop principale, così le righe fixture_predictions
    # esistono già (predict_fixture le rilegge). NESSUNA quota Betfair (live_odds=None):
    # gira interamente in cloud. Avvolto in try/except: un errore NON impatta gli altri motori.
    try:
        import os as _os
        import sys as _sys
        _aieng = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "Ai Engine")
        if _aieng not in _sys.path:
            _sys.path.append(_aieng)
        from ai_engine.serving_batch import run_for_date as _ml_run
        _ml_res = _ml_run(target_date)
        logger.info("🤖 ml_engine %s → %s", target_date, _ml_res)
    except Exception as e:  # noqa: BLE001
        logger.warning("ml_engine non eseguito per %s: %s", target_date, e)

    # --- TERZO MOTORE: Tactical Engine (GSG), aggiunta ADDITIVA e NON-FATALE ---
    # Scrive le predizioni del nuovo motore nella colonna `tactical_engine_json`
    # della STESSA tabella fixture_predictions (come Poisson->db_json_analisi e
    # ML->model_predictions_json). Gira sulle stesse partite del giorno appena
    # processate. Avvolto in try/except: un suo errore NON impatta il motore principale.
    try:
        from tactical_engine.serving import run_for_date as _tactical_run
        _te_res = _tactical_run(target_date)
        logger.info("🧠 tactical_engine %s → %s", target_date, _te_res)
    except Exception as e:  # noqa: BLE001
        logger.warning("tactical_engine non eseguito per %s: %s", target_date, e)

    # 26/09 (FIX-B, KO9): ESITO REALE sui payload TacticAI delle partite FINITE degli
    # ultimi giorni (prima "actual" restava sempre NULL: il blocco "Esito reale (90')"
    # della UI non compariva mai). Stesso job, subito dopo il motore; NON-FATALE.
    try:
        from tactical_engine.serving import run_esiti_reali as _tactical_esiti
        _te_esiti = _tactical_esiti(target_date)
        logger.info("tactical_engine esiti reali %s -> %s", target_date, _te_esiti)
    except Exception as e:  # noqa: BLE001
        logger.warning("tactical_engine esiti reali non scritti per %s: %s", target_date, e)

    # Flush esplicito del buffer di log API (oltre alla garanzia atexit):
    # non solleva mai eccezioni verso il chiamante.
    flush_api_log()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        help="Data YYYY-MM-DD (default: oggi in UTC)",
        default=None
    )
    args = parser.parse_args()

    target_date = args.date or datetime.now(timezone.utc).date().isoformat()
    _reset_failures()
    _reset_retry_budget()
    _reset_totale_processo()
    run_for_date(target_date)

    # Nessun successo dichiarato con dati mancanti: se resta anche una sola
    # anomalia non recuperata il processo esce in errore (workflow rosso).
    if _RUN_FAILURES:
        logger.error(
            "Uscita con codice 1: %s anomalie non recuperate su %s.",
            len(_RUN_FAILURES), target_date,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
