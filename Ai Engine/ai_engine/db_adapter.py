from __future__ import annotations

import inspect as _inspect
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import db_client as _db_client
from db_client import get_supabase_client

import random as _random
import time as _time

logger = logging.getLogger(__name__)

# Tentativi e attese: piu' tentativi (il DB Supabase e' su istanza piccola e il
# ruolo PostgREST ha statement_timeout = 8 s) con attesa crescente + jitter, cosi'
# due letture che falliscono insieme non ripartono in sincrono.
_MAX_RETRIES = 6
_RETRY_BACKOFF = 2.0  # secondi, raddoppia a ogni tentativo
_RETRY_MAX_WAIT = 30.0  # tetto all'attesa singola
_MIN_PAGE_SIZE = 50  # sotto questa soglia la pagina non si dimezza piu'

# Codici che valgono un nuovo tentativo: timeout di statement, PostgREST che non
# risponde, gateway. Gli errori LOGICI (colonna inesistente, filtro non valido,
# violazioni) NON sono qui: devono emergere subito.
_TRANSIENT_CODES = frozenset({
    "57014",     # canceling statement due to statement timeout
    "57P01",     # admin shutdown
    "53300",     # too many connections
    "08000", "08003", "08006",  # connessione persa
    "40001", "40P01",           # serialization failure / deadlock
    "PGRST001", "PGRST002",     # PostgREST non ha lo schema / DB non raggiungibile
    "502", "503", "504", "408", "429",
})
_TRANSIENT_TEXT = (
    "statement timeout",
    "canceling statement",
    "timed out",
    "timeout",
    "connection",
    "server disconnected",
    "remote end closed",
    "bad gateway",
    "service unavailable",
    "gateway time-out",
    "temporarily unavailable",
)
_TRANSIENT_EXC_NAMES = (
    "timeout",
    "connecterror",
    "connectionerror",
    "remoteprotocolerror",
    "readerror",
    "networkerror",
    "protocolerror",
)
_TIMEOUT_TEXT = ("statement timeout", "canceling statement")


class RispostaSenzaDati(RuntimeError):
    """PostgREST ha risposto senza corpo: anomalia, NON 'fine dei dati'.

    Una lista vuota e' fine dei dati; ``resp.data is None`` no: prima veniva
    trattato come vuoto e la paginazione si fermava in silenzio.
    """


# match_odds (~92M righe, ~4.300 righe per fixture): blocco di fixture piccolo +
# ordine deterministico (fixture_id, id). Misure in sola lettura, lega 141:
# - CON filtro sui mercati (retrain/serving) ~375 righe utili per fixture: blocco
#   da 20 = ~7,5k righe, offset massimo ~7k, pagina peggiore ~1,6 s.
# - SENZA filtro (backtest) ~4.300 righe per fixture: con blocco da 20 l'offset
#   arriva a ~86k e l'ORDER BY diventa caro (misurato dal revisore: offset 20.000
#   = 5,2 s contro 1,48 s senza ordine). Con blocco da 5 l'offset massimo e' ~21k
#   e la pagina peggiore misurata (EXPLAIN ANALYZE, offset 20.000, a caldo) e'
#   436 ms contro 7,5 ms senza ordine: l'ordine NON e' gratuito a offset profondo,
#   ma resta lontanissimo dagli 8 s dello statement_timeout.
_ODDS_CHUNK_SIZE = 20
_ODDS_CHUNK_SIZE_SENZA_FILTRO = 5
_ODDS_PAGE_SIZE = 1000

# Ordine deterministico per la paginazione a offset: senza ORDER BY il DB puo'
# restituire la stessa riga in due pagine e saltarne un'altra (il 20/09
# fixture_predictions aveva 999 righe in un giorno: il primo sabato pieno supera
# la pagina da 1000). Chiavi verificate sul DB (pg_indexes, 21/09):
#   match_odds/match_events/match_team_stats/match_player_stats -> pkey(id) +
#       indice su fixture_id: (fixture_id, id) = Incremental Sort, misurato su
#       match_events 200 fixture: 2,6 ms con ordine contro 101 ms senza.
#   fixture_predictions -> pkey UNICA (fixture_id): quicksort di ~1000 righe, ~1 ms.
#   matches -> indice unico matches_fixture_unique (fixture_id) e indice
#       (league_id, season_year, fixture_id): ORDER BY fixture_id NON aggiunge
#       nessun nodo Sort (misurato: Index Scan puro).
#   standings -> pkey(id); il vincolo (league_id, season_year, standing_group,
#       team_id) NON e' utilizzabile perche' standing_group ammette NULL (in un
#       indice unico i NULL non collidono): si usa `id`, quicksort di 22 righe.
# Una tabella non elencata resta esattamente come prima (nessun ORDER BY).
_ORDINE_PER_TABELLA: Dict[str, Tuple[str, ...]] = {
    "match_odds": ("fixture_id", "id"),
    "match_events": ("fixture_id", "id"),
    "match_team_stats": ("fixture_id", "id"),
    "match_player_stats": ("fixture_id", "id"),
    "fixture_predictions": ("fixture_id",),
    "matches": ("fixture_id",),
    "standings": ("id",),
}

# Pagina "appresa" dopo un timeout: resta valida per le letture successive della
# STESSA tabella nello stesso processo, altrimenti ogni blocco ripagherebbe il
# timeout per riscoprire che la pagina e' troppo grande. Non scende mai sotto
# _MIN_PAGE_SIZE e non sale mai da sola (il processo di retrain e' breve).
_PAGINA_APPRESA: Dict[str, int] = {}


def _azzera_pagine_apprese() -> None:
    """Dimentica le pagine ridotte dai timeout (usata dai test)."""
    _PAGINA_APPRESA.clear()


def _chunked(items: List[Any], size: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _error_code(exc: BaseException) -> str:
    """Codice dell'errore PostgREST ('57014', 'PGRST002', ...) se presente."""
    code = getattr(exc, "code", None)
    if code is None:
        args = getattr(exc, "args", ())
        if args and isinstance(args[0], dict):
            code = args[0].get("code")
    return "" if code is None else str(code)


def _error_text(exc: BaseException) -> str:
    """Testo dell'errore, str() + repr().

    L'APIError di postgrest 2.28 li scrive diversi: str() da' il dict grezzo
    ({'message': ..., 'code': '57014', ...}), repr() da' "Error 57014:\\nMessage: ...".
    Servono entrambi perche' altre librerie mettono il dettaglio solo in uno.
    """
    return f"{exc!r} {exc}".lower()


def _is_timeout_error(exc: BaseException) -> bool:
    """True solo per il timeout di statement (57014): la pagina va rimpicciolita."""
    if _error_code(exc) == "57014":
        return True
    text = _error_text(exc)
    return any(t in text for t in _TIMEOUT_TEXT)


def _is_transient_error(exc: BaseException) -> bool:
    """True se vale la pena riprovare. Un errore logico ritorna False e propaga."""
    if isinstance(exc, RispostaSenzaDati):
        return True
    if isinstance(exc, (ValueError, TypeError, KeyError, AttributeError)):
        return False
    if _error_code(exc) in _TRANSIENT_CODES:
        return True
    name = type(exc).__name__.lower()
    if any(n in name for n in _TRANSIENT_EXC_NAMES):
        return True
    text = _error_text(exc)
    return any(t in text for t in _TRANSIENT_TEXT)


def _retry_wait(attempt: int) -> float:
    """Attesa crescente con jitter (attempt parte da 1)."""
    base = min(_RETRY_BACKOFF * (2 ** (attempt - 1)), _RETRY_MAX_WAIT)
    return base * (0.5 + _random.random() * 0.5)


def _chiudi_client(client: Any) -> None:
    """Chiude le connessioni httpx del client che stiamo buttando.

    In postgrest 2.28 ``aclose()`` e' SINCRONA (fa session.close()): senza questa
    chiamata il pool del client scartato resterebbe aperto fino alla garbage
    collection. Se la libreria cambia (metodo assente o diventato asincrono) non
    si chiude nulla: e' una pulizia, non deve mai far fallire la lettura.
    """
    chiudi = getattr(getattr(client, "postgrest", None), "aclose", None)
    if not callable(chiudi) or _inspect.iscoroutinefunction(chiudi):
        return
    try:
        chiudi()
    except Exception as exc:  # pulizia best-effort, l'errore vero e' un altro
        logger.debug("chiusura client fallita: %r", exc)


def _renew_client() -> Any:
    """Ricostruisce il client del thread.

    ``db_client`` tiene un client per thread in cache: dopo un errore di rete il
    pool httpx va chiuso e buttato, altrimenti il tentativo seguente riparte con
    la stessa connessione rotta.
    """
    tls = getattr(_db_client, "_TLS", None)
    if tls is not None:
        vecchio = getattr(tls, "client", None)
        if vecchio is not None:
            _chiudi_client(vecchio)
        tls.client = None
    return get_supabase_client()


def _apply_filters(query: Any, filters: Optional[List[Tuple[str, str, Any]]]) -> Any:
    if not filters:
        return query
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
    return query


def _build_query(
    sb: Any,
    table: str,
    columns: str,
    filters: Optional[List[Tuple[str, str, Any]]],
    order: Optional[Sequence[str]] = None,
) -> Any:
    query = sb.table(table).select(columns)
    query = _apply_filters(query, filters)
    if order:
        for col in order:
            query = query.order(col, desc=False)
    return query


def _fetch_all(
    table: str,
    columns: str,
    filters: Optional[List[Tuple[str, str, Any]]] = None,
    page_size: int = 1000,
    order: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch all rows from a table with optional filters.
    Filters are tuples (op, column, value), e.g. ("eq", "league_id", 39).

    ``order`` e' una lista di colonne crescenti: serve a rendere DETERMINISTICA la
    paginazione a offset (senza ORDER BY il DB puo' restituire la stessa riga in
    due pagine e saltarne un'altra). Se non viene passato si usa l'ordine noto
    della tabella (``_ORDINE_PER_TABELLA``). Il set di righe non cambia, cambia
    solo l'ordine in cui arriva: un consumatore che tiene "la prima riga" per
    chiave ora ne ha una deterministica (vedi la nota su backtest.py sotto
    ``fetch_related_by_fixture_ids``).

    Ritenta solo gli errori transitori (timeout 57014, PostgREST giu', rete,
    risposta senza corpo) con attesa crescente + jitter; sul 57014 dimezza anche
    la pagina. Se i tentativi finiscono l'eccezione PROPAGA: mai un risultato
    parziale dichiarato completo.
    """
    sb = get_supabase_client()
    offset = 0
    if order is None:
        order = _ORDINE_PER_TABELLA.get(table)
    cur_page = max(1, int(page_size))
    appresa = _PAGINA_APPRESA.get(table)
    if appresa is not None and appresa < cur_page:
        cur_page = appresa
    results: List[Dict[str, Any]] = []

    while True:
        attempt = 0
        while True:
            try:
                query = _build_query(sb, table, columns, filters, order)
                resp = query.range(offset, offset + cur_page - 1).execute()
                data = getattr(resp, "data", None)
                if data is None:
                    raise RispostaSenzaDati(
                        f"{table}: risposta senza dati (offset={offset}, page={cur_page})"
                    )
                break
            except Exception as e:
                attempt += 1
                if attempt >= _MAX_RETRIES or not _is_transient_error(e):
                    raise
                if _is_timeout_error(e) and cur_page > _MIN_PAGE_SIZE:
                    new_page = max(_MIN_PAGE_SIZE, cur_page // 2)
                    logger.warning("[db_adapter] Timeout su %s (offset=%s): pagina %s -> %s",
                                   table, offset, cur_page, new_page)
                    cur_page = new_page
                    _PAGINA_APPRESA[table] = min(_PAGINA_APPRESA.get(table, new_page), new_page)
                wait = _retry_wait(attempt)
                logger.warning("[db_adapter] Retry %s/%s for %s (offset=%s, page=%s): %r "
                               "- waiting %.1fs", attempt, _MAX_RETRIES - 1, table, offset,
                               cur_page, e, wait)
                _time.sleep(wait)
                sb = _renew_client()

        results.extend(data)
        if len(data) < cur_page:
            break
        offset += len(data)

    return results


def fetch_fixtures_for_date(target_date: date) -> List[Dict[str, Any]]:
    start = datetime.combine(target_date, datetime.min.time()).isoformat()
    end = (datetime.combine(target_date, datetime.min.time()) + timedelta(days=1)).isoformat()

    columns = (
        "fixture_id,league_id,season_year,fixture_date,home_team_id,home_team_name,"
        "away_team_id,away_team_name,goals_home,goals_away,halftime_home,halftime_away,"
        "fulltime_home,fulltime_away,extratime_home,extratime_away,penalty_home,penalty_away,"
        "status_short,status_long,status_elapsed,venue_name,venue_city"
    )
    # Use fixture_predictions as daily source of fixtures
    fp_columns = (
        "fixture_id,league_id,league_name,season_year,fixture_date,home_team_id,home_team_name,"
        "away_team_id,away_team_name,status,goals_home_line,goals_away_line,under_over_line,"
        "percent_home,percent_draw,percent_away,win_or_draw,advice,winner_team_id,winner_name,"
        "raw_json_odds,raw_json"
    )
    filters = [("gte", "fixture_date", start), ("lt", "fixture_date", end)]
    return _fetch_all("fixture_predictions", fp_columns, filters)


def fetch_matches_for_league_seasons(
    league_seasons: List[Tuple[int, int]]
) -> List[Dict[str, Any]]:
    columns = (
        "fixture_id,league_id,season_year,fixture_date,home_team_id,home_team_name,"
        "away_team_id,away_team_name,goals_home,goals_away"
    )
    results: List[Dict[str, Any]] = []
    for league_id, season_year in league_seasons:
        filters = [("eq", "league_id", league_id), ("eq", "season_year", season_year)]
        results.extend(_fetch_all("matches", columns, filters))
    return results


def fetch_matches_full_for_league_seasons(
    league_seasons: List[Tuple[int, int]]
) -> List[Dict[str, Any]]:
    columns = (
        "fixture_id,league_id,season_year,fixture_date,home_team_id,home_team_name,"
        "away_team_id,away_team_name,goals_home,goals_away,halftime_home,halftime_away,"
        "fulltime_home,fulltime_away,extratime_home,extratime_away,penalty_home,penalty_away"
    )
    results: List[Dict[str, Any]] = []
    for league_id, season_year in league_seasons:
        filters = [("eq", "league_id", league_id), ("eq", "season_year", season_year)]
        results.extend(_fetch_all("matches", columns, filters))
    return results


def fetch_related_by_fixture_ids(
    table: str,
    fixture_ids: List[int],
    columns: str,
    extra_filters: Optional[List[Tuple[str, str, Any]]] = None,
    page_size: int = 1000,
    chunk_size: int = 1000,
) -> List[Dict[str, Any]]:
    """Legge le righe collegate a una lista di fixture, a blocchi.

    ``match_odds`` ha ~92M righe (~4.300 per fixture, di cui solo ~9% passa il
    filtro sui mercati): con blocchi da 200 fixture le pagine a offset alto
    dovevano scorrere centinaia di migliaia di righe e sforavano lo
    statement_timeout di 8 s (57014). Blocchi piccoli tengono l'offset basso, e
    l'ORDER BY (fixture_id, id) rende la paginazione deterministica. L'ordine NON
    e' gratuito a offset profondo (misure in ``_ODDS_CHUNK_SIZE``), per questo il
    blocco e' piu' piccolo quando non c'e' il filtro sui mercati.

    DIVERGENZA NOTA (da portare all'utente, non corretta qui): con l'ORDER BY
    cambia QUALE riga arriva per prima. ``ai_engine/backtest.py::_fetch_odds_by_fixture``
    tiene la prima riga per (mercato, label) - prima era una riga arbitraria
    (ordine fisico), ora e' deterministicamente quella con `id` piu' basso, cioe'
    lo snapshot piu' vecchio. Riguarda solo il backtest: retrain e serving
    aggregano (mediana/somma) e non dipendono dall'ordine.
    """
    if not fixture_ids:
        return []
    results: List[Dict[str, Any]] = []
    if table == "match_odds":
        # blocchi piccoli: l'offset residuo dentro il blocco e' innocuo
        page_size = min(page_size, _ODDS_PAGE_SIZE)
        massimo = _ODDS_CHUNK_SIZE if extra_filters else _ODDS_CHUNK_SIZE_SENZA_FILTRO
        chunk_size = min(chunk_size, massimo)
    for chunk in _chunked(fixture_ids, chunk_size):
        filters = [("in", "fixture_id", chunk)]
        if extra_filters:
            filters.extend(extra_filters)
        results.extend(_fetch_all(table, columns, filters, page_size=page_size))
    return results


def fetch_standings_by_league_seasons(
    league_seasons: List[Tuple[int, int]]
) -> List[Dict[str, Any]]:
    columns = (
        "league_id,season_year,team_id,team_name,rank,played,win,draw,lose,"
        "goals_for,goals_against,goals_diff,points,form,standing_group,description"
    )
    results: List[Dict[str, Any]] = []
    for league_id, season_year in league_seasons:
        filters = [("eq", "league_id", league_id), ("eq", "season_year", season_year)]
        results.extend(_fetch_all("standings", columns, filters))
    return results


def fetch_seasons_for_league(league_id: int) -> List[int]:
    sb = get_supabase_client()
    resp = (
        sb.table("matches")
        .select("season_year")
        .eq("league_id", league_id)
        .order("season_year", desc=False)
        .execute()
    )
    data = getattr(resp, "data", None) or []
    seasons = sorted({int(r.get("season_year")) for r in data if r.get("season_year") is not None})
    return seasons


def fetch_fixture_prediction_by_id(fixture_id: int) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    resp = (
        sb.table("fixture_predictions")
        .select(
            "fixture_id,league_id,league_name,season_year,fixture_date,home_team_id,home_team_name,"
            "away_team_id,away_team_name,status,goals_home_line,goals_away_line,under_over_line,"
            "percent_home,percent_draw,percent_away,win_or_draw,advice,winner_team_id,winner_name,"
            "raw_json_odds"
        )
        .eq("fixture_id", fixture_id)
        .execute()
    )
    return getattr(resp, "data", None) or []
