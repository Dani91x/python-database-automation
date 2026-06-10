# Prediction/backfill_historical_analysis.py
#
# Backfill di ht_predictions per il pregresso storico.
# Usa compute_db_json_analisi da today_predictions_backfill.py — stessa funzione,
# stesso modello (poisson_xg_hybrid_dc), stesso formato output.
# Scrive SOLO ht_predictions; db_json_analisi è gestito da AGGIORNA_CAMPO_db_json_analisi.py.

import logging
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db_client import get_supabase_client
from Prediction.today_predictions_backfill import compute_db_json_analisi  # noqa: E402

# Logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


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
                elif op == "is":
                    query = query.is_(col, val)
                else:
                    raise ValueError(f"Unsupported filter op: {op}")

        resp = query.range(offset, offset + page_size - 1).execute()
        data = getattr(resp, "data", None) or []
        results.extend(data)
        if len(data) < page_size:
            break
        offset += page_size

    return results


# ==============================
# Backfill Logic
# ==============================

def run_backfill(limit: Optional[int] = None, league_id_filter: Optional[int] = None):
    sb = get_supabase_client()

    # Solo fixture concluse: questo è il backfill del PREGRESSO storico.
    # Senza questo filtro si scriverebbero ht_predictions anche su fixture non
    # ancora giocate (gestite invece dal percorso live today_predictions_backfill).
    # Stesso filtro usato da AGGIORNA_CAMPO_db_json_analisi.py.
    filters = [
        ("in", "result_status_short", ["FT", "AET", "PEN"]),
        ("is", "ht_predictions", "null"),
    ]
    if league_id_filter:
        filters.append(("eq", "league_id", league_id_filter))

    cols = "fixture_id,league_id,season_year,fixture_date,home_team_id,away_team_id"
    rows = _fetch_all_table("fixture_predictions", cols, filters=filters, page_size=1000)

    if limit:
        rows = rows[:limit]

    if not rows:
        logger.info("✅ Nessuna fixture da aggiornare. Fine.")
        return

    logger.info(f"📊 Trovate {len(rows)} fixture da processare.")

    groups: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for r in rows:
        key = (int(r["league_id"]), int(r["season_year"]))
        groups.setdefault(key, []).append(r)

    match_cache: Dict[Tuple[int, int], Dict[str, Any]] = {}
    xg_cache: Dict[Tuple[int, int], Dict[Tuple[int, int], float]] = {}

    total_processed = 0
    for (l_id, s_year), group in groups.items():
        logger.info(f"🚀 Inizio raggruppamento: Lega {l_id} | Stagione {s_year} ({len(group)} fixture)")

        for fixture_row in group:
            try:
                ctx = {
                    "fixture_id": int(fixture_row["fixture_id"]),
                    "league_id":  int(fixture_row["league_id"]),
                    "season_year": int(fixture_row["season_year"]),
                    "fixture_date": fixture_row["fixture_date"],
                    "home_team_id": int(fixture_row["home_team_id"]) if fixture_row["home_team_id"] else None,
                    "away_team_id": int(fixture_row["away_team_id"]) if fixture_row["away_team_id"] else None,
                }

                res_data = compute_db_json_analisi(ctx, match_cache, xg_cache)
                if res_data:
                    _analysis, ht_pred = res_data
                    sb.table("fixture_predictions").update({
                        "ht_predictions": ht_pred,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("fixture_id", ctx["fixture_id"]).execute()

                    total_processed += 1
                    if total_processed % 10 == 0:
                        logger.info(f"✅ Processate {total_processed} fixture...")

            except Exception as e:
                logger.error(f"❌ Errore critico fixture_id {fixture_row.get('fixture_id')}: {e}")
                if hasattr(e, 'details'):
                    logger.error(f"Dettagli: {e.details}")
                if hasattr(e, 'message'):
                    logger.error(f"Messaggio: {e.message}")

    logger.info(f"🏁 Backfill completato! Totale fixture elaborate: {total_processed}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backfill storico ht_predictions")
    parser.add_argument("--limit", type=int, help="Limita il numero totale di fixture da processare")
    parser.add_argument("--league", type=int, help="Filtra per una specifica league_id")
    args = parser.parse_args()

    run_backfill(limit=args.limit, league_id_filter=args.league)
