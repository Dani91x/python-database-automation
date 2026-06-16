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

# Cutoff: campagna NUOVA METODOLOGIA CERTIFICATA (storico pieno + NO leak
# standings + 28 target completi + ELO allineato train/predict) dal 2026-06-16.
# Alzato a 2026-06-16T08:00Z perche' i run da cron del 15-16/06 avevano addestrato
# con SOLE 3 stagioni (fallback workflow errato) E con il leak standings: quei
# modelli, pur avendo trained_at>=2026-06-15, sono CONTAMINATI e vanno rifatti.
# 08:00Z e' successivo all'ultimo modello vecchio (06:40Z del 16/06) e precedente
# al lancio della campagna corretta => TUTTE le leghe risultano da riaddestrare,
# e i modelli prodotti dalla nuova campagna (trained_at>08:00Z) restano freschi
# fino a convergenza (da_fare=0).
DEFAULT_CUTOFF = "2026-06-16T08:00:00+00:00"

# Soglia minima di partite per considerare addestrabile una lega. REGOLA UTENTE
# (2026-06-15): si esclude SOLO chi ha <50 partite GIOCATE COMPLESSIVE in TUTTE le
# stagioni disponibili (non piu' "ultime 3 stagioni"). Tutto il resto va addestrato.
DEFAULT_MIN_MATCHES = 50
DEFAULT_LAST_N = 3  # mantenuto per retrocompat firma; l'eleggibilita' usa il TOTALE

# BLACKLIST: leghe che superano il filtro match-count (>=50 partite nelle ultime N
# stagioni) ma che il training NON riesce comunque ad addestrare (0 modelli),
# perche' le partite sono troppo vecchie / strutturalmente inadatte (es. play-off
# conclusi da oltre un anno, qualificazioni giovanili sporadiche). Senza questa
# lista il planner le ri-proporrebbe ad OGNI run all'infinito, impedendo alla
# campagna di convergere davvero a "0 da fare". Estendibile a runtime via env
# RETRAIN_BLACKLIST="id1,id2,...". Verificate sul campo (0 modelli prodotti
# ripetutamente): vedi audit 2026-06-14.
# REGOLA UTENTE 2026-06-15: l'UNICO criterio di esclusione e' <50 partite totali.
# Niente blacklist per "dati vecchi": con lo storico pieno si addestra comunque.
# Resta solo l'override additivo via env RETRAIN_BLACKLIST (per emergenze manuali).
DEFAULT_BLACKLIST = frozenset()

_PAGE = 1000


def _load_blacklist() -> frozenset:
    """Blacklist effettiva = default + eventuale override additivo da env."""
    extra = os.environ.get("RETRAIN_BLACKLIST", "")
    ids = set(DEFAULT_BLACKLIST)
    for tok in extra.split(","):
        tok = tok.strip()
        if tok.isdigit():
            ids.add(int(tok))
    return frozenset(ids)


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


def _matches_total(seasons_counts: Dict[int, int]) -> int:
    """Somma matches_count di TUTTE le stagioni disponibili (per lega).
    REGOLA UTENTE 2026-06-15: l'eleggibilita' usa il totale storico, non le ultime N.
    Cosi' si addestra ogni lega con la massima profondita' di dati."""
    return sum(int(v or 0) for v in seasons_counts.values())


def _load_eligible_leagues() -> Optional[List[int]]:
    """Universo leghe GROUND-TRUTH dalla tabella `matches` (lista committata in
    training_eligible_leagues.json, rigenerata con _count_played_by_league.py).
    Sostituisce season_backfill_state, che risultava NON aggiornato/incompleto
    (2026-06-15): perdeva leghe realmente presenti in matches. La lista contiene
    SOLO le leghe con >=50 partite giocate totali (regola d'esclusione). Ritorna
    None se il file manca (fallback su season_backfill_state)."""
    import json
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "training_eligible_leagues.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ids = [int(x) for x in data.get("eligible_league_ids", [])]
        return ids or None
    except (OSError, ValueError, TypeError):
        return None


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

    # UNIVERSO LEGHE: ground-truth dalla tabella `matches` (lista committata).
    # NON si usa piu' season_backfill_state come fonte (incompleto/non aggiornato:
    # 2026-06-15). La lista e' gia' pre-filtrata a >=50 partite giocate totali.
    season_counts: Dict[int, Dict[int, int]] = defaultdict(dict)
    eligible_ids = _load_eligible_leagues()
    if eligible_ids is not None:
        universe = sorted(set(eligible_ids))
        _prefiltered = True
    else:
        # Fallback retrocompat: universo + matches_count da season_backfill_state.
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
        _prefiltered = False

    latest: Dict[int, datetime] = {}
    for r in _all_pages("ai_model_registry", "league_id,trained_at"):
        lid = int(r["league_id"])
        d = _parse_ts(r.get("trained_at"))
        if d and (lid not in latest or d > latest[lid]):
            latest[lid] = d

    blacklist = _load_blacklist()

    missing: List[int] = []
    stale: List[int] = []
    skipped_no_data: List[int] = []
    blacklisted: List[int] = []
    fresh = 0
    for lid in universe:
        if lid in blacklist:
            # Solo override manuale via env (default vuoto).
            blacklisted.append(lid)
            continue
        # REGOLA UTENTE 2026-06-15: unico filtro = >=50 partite GIOCATE TOTALI.
        # Con la lista ground-truth (_prefiltered) l'esclusione e' gia' applicata;
        # nel fallback season_backfill_state la si calcola dal totale storico.
        if not _prefiltered and _matches_total(season_counts.get(lid, {})) < min_matches:
            skipped_no_data.append(lid)
            continue
        if lid not in latest:
            missing.append(lid)          # mai addestrata
        elif latest[lid] < cutoff_dt:
            stale.append(lid)            # vecchia metodologia => rifai con storico pieno
        else:
            fresh += 1                   # gia' addestrata con la nuova metodologia

    # Prima le mancanti, poi le stale dalla piu' vecchia: priorita' al lavoro
    # mai fatto, poi al refresh del leaked-era.
    stale.sort(key=lambda l: latest[l])
    todo = missing + stale

    return {
        "todo": todo,
        "missing": missing,
        "stale": stale,
        "skipped_no_data": skipped_no_data,
        "blacklisted": blacklisted,
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
        f"blacklist={len(plan['blacklisted'])} | "
        f"cutoff={plan['cutoff']}"
    )
    print(f"[PLANNER] prime 30 da fare: {plan['todo'][:30]}")
