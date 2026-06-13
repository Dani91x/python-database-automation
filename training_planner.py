"""training_planner.py — Selezione gentile (poche query bulk) di quali leghe
(ri)addestrare, SENZA una query-per-lega: fondamentale per non stressare l'I/O
del DB (istanza Nano).

REGOLA DI SELEZIONE (terminante):
    Una lega va addestrata se:
      - MISSING : non ha alcun modello in ai_model_registry
                  E ha abbastanza partite per essere addestrabile
                  (>= RETRAIN_MIN_MATCHES nelle ultime last_n stagioni), OPPURE
      - STALE   : ha gia' un modello ma il piu' recente e' anteriore a
                  RETRAIN_FRESH_CUTOFF (vecchio/leaked-era/danneggiato).
    Il filtro match-count sui MISSING evita di ritentare all'infinito le leghe
    senza dati (che producono 0 modelli): cosi' la campagna CONVERGE davvero a
    "0 da fare". Le STALE entrano sempre: avevano gia' un modello => addestrabili.

COSTO I/O: 2 query paginate totali (season_backfill_state + ai_model_registry),
indipendentemente dal numero di leghe; del primo si legge solo matches_count via
JSON path (payload minimo). Mai si tocca la tabella `matches`. Con gli indici di
sql/perf_indexes.sql sono letture leggere anche su Nano.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from db_client import get_supabase_client

# Cutoff di default: la campagna "sana" parte dal 2026-06-12. Tutto cio' che e'
# stato addestrato PRIMA va rifatto una volta (vecchio/leaked-era/danneggiato).
DEFAULT_CUTOFF = "2026-06-12"

# Soglia minima di partite (somma ultime N stagioni) per considerare addestrabile
# una lega MANCANTE. Sotto, il training darebbe 0 modelli: la si esclude per far
# convergere la campagna. Tarata bassa: esclude solo i casi chiaramente senza dati.
DEFAULT_MIN_MATCHES = 50
DEFAULT_LAST_N = 3

_PAGE = 1000


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _all_pages(table: str, columns: str, page: int = _PAGE) -> List[Dict]:
    """Scarica TUTTE le righe paginando (Supabase tronca a 1000 per richiesta)."""
    sb = get_supabase_client()
    out: List[Dict] = []
    offset = 0
    while True:
        resp = sb.table(table).select(columns).range(offset, offset + page - 1).execute()
        rows = getattr(resp, "data", None) or []
        out.extend(rows)
        if len(rows) < page:
            break
        offset += page
    return out


def _matches_last_n(seasons_counts: Dict[int, int], last_n: int) -> int:
    """Somma matches_count delle ultime ``last_n`` stagioni (per lega)."""
    recent = sorted(seasons_counts.keys(), reverse=True)[:last_n]
    return sum(int(seasons_counts.get(s, 0) or 0) for s in recent)


def select_leagues_to_train(
    cutoff: Optional[str] = None,
    min_matches: Optional[int] = None,
    last_n: Optional[int] = None,
) -> Dict:
    """Ritorna il piano di lavoro. Chiavi:
    todo (list[int], mancanti-addestrabili + stale ordinate), missing, stale,
    skipped_no_data, fresh_count, universe, cutoff.
    """
    cutoff = cutoff or os.environ.get("RETRAIN_FRESH_CUTOFF", DEFAULT_CUTOFF)
    cutoff_dt = _parse_ts(cutoff) or _parse_ts(DEFAULT_CUTOFF)
    if min_matches is None:
        min_matches = int(os.environ.get("RETRAIN_MIN_MATCHES", DEFAULT_MIN_MATCHES))
    if last_n is None:
        last_n = int(os.environ.get("RETRAIN_LAST_N_SEASONS", DEFAULT_LAST_N))

    # Universe + matches_count per (lega, stagione) — solo il JSON path, payload minimo.
    season_counts: Dict[int, Dict[int, int]] = defaultdict(dict)
    universe_set = set()
    for r in _all_pages(
        "season_backfill_state",
        "league_id,season_year,matches_count:stats_json->fixtures->>matches_count",
    ):
        lid = r.get("league_id")
        if lid is None:
            continue
        lid = int(lid)
        universe_set.add(lid)
        sy = r.get("season_year")
        try:
            mc = int(r.get("matches_count") or 0)
        except (ValueError, TypeError):
            mc = 0
        if sy is not None:
            season_counts[lid][int(sy)] = mc
    universe = sorted(universe_set)

    latest: Dict[int, datetime] = {}
    for r in _all_pages("ai_model_registry", "league_id,trained_at"):
        lid = int(r["league_id"])
        d = _parse_ts(r.get("trained_at"))
        if d and (lid not in latest or d > latest[lid]):
            latest[lid] = d

    missing: List[int] = []
    stale: List[int] = []
    skipped_no_data: List[int] = []
    fresh = 0
    for lid in universe:
        if lid not in latest:
            # MANCANTE: includi solo se ha abbastanza dati per addestrare.
            if _matches_last_n(season_counts.get(lid, {}), last_n) >= min_matches:
                missing.append(lid)
            else:
                skipped_no_data.append(lid)
        elif latest[lid] < cutoff_dt:
            stale.append(lid)
        else:
            fresh += 1

    # Prima le mancanti, poi le stale dalla piu' vecchia: priorita' al lavoro
    # mai fatto, poi al refresh del leaked-era.
    stale.sort(key=lambda l: latest[l])
    todo = missing + stale

    return {
        "todo": todo,
        "missing": missing,
        "stale": stale,
        "skipped_no_data": skipped_no_data,
        "fresh_count": fresh,
        "universe": len(universe),
        "cutoff": cutoff,
        "min_matches": min_matches,
    }


if __name__ == "__main__":
    plan = select_leagues_to_train()
    print(
        f"[PLANNER] universe={plan['universe']} | da_fare={len(plan['todo'])} "
        f"(missing={len(plan['missing'])}, stale={len(plan['stale'])}) | "
        f"gia_fresche={plan['fresh_count']} | "
        f"escluse_senza_dati={len(plan['skipped_no_data'])} (<{plan['min_matches']} match) | "
        f"cutoff={plan['cutoff']}"
    )
    print(f"[PLANNER] prime 30 da fare: {plan['todo'][:30]}")
