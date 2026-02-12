# Prediction/today_predictions_backfill.py

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ----------------------------------------------------------
# Ensure project root is on sys.path so absolute imports work
# even when running this file from the Prediction/ folder.
# ----------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api_client import APIFootballClient  # noqa: E402
from db_client import get_supabase_client  # noqa: E402

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
    """
    key = (league_id, season_year)
    if key in cache:
        return cache[key]

    sb = get_supabase_client()
    try:
        resp = (
            sb.table("api_coverage_by_season")
            .select("predictions")
            .eq("league_id", league_id)
            .eq("season_year", season_year)
            .maybe_single()
            .execute()
        )
        row = getattr(resp, "data", None) or {}
        flag = bool(row.get("predictions"))
    except Exception as e:
        logger.error(
            "❌ Errore nel leggere coverage predictions (league_id=%s season=%s): %s",
            league_id, season_year, e
        )
        flag = False

    cache[key] = flag
    return flag


# ==============================
# NEW: Skip helper (no API call if already OK)
# ==============================

def prediction_already_done(fixture_id: int) -> bool:
    """
    Ritorna True se in fixture_predictions esiste già una riga per fixture_id
    con status='ok'. In quel caso skippiamo la chiamata API /predictions.
    """
    sb = get_supabase_client()
    try:
        resp = (
            sb.table("fixture_predictions")
            .select("fixture_id,status")
            .eq("fixture_id", fixture_id)
            .maybe_single()
            .execute()
        )
        row = getattr(resp, "data", None) or None
        if not row:
            return False
        return row.get("status") == "ok"
    except Exception as e:
        # Se il check fallisce, NON blocchiamo: meglio chiamare l'API che perdere dati
        logger.warning("⚠️ Errore check prediction_already_done fixture_id=%s: %s", fixture_id, e)
        return False


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
    sb.table("fixture_predictions").upsert(row, on_conflict="fixture_id").execute()


# ==============================
# Runner
# ==============================

def run_for_date(target_date: str) -> None:
    api = APIFootballClient()
    fixtures = fetch_fixtures_for_date(api, target_date)

    if not fixtures:
        logger.info("✅ Nessuna fixture per %s. Fine.", target_date)
        return

    coverage_cache: Dict[Tuple[int, int], bool] = {}

    ok_count = 0
    empty_count = 0
    no_cov_count = 0
    err_count = 0
    skipped_count = 0
    skipped_existing_count = 0

    for fx in fixtures:
        ctx = extract_fixture_context(fx)
        if ctx is None:
            skipped_count += 1
            logger.warning("⚠️ Fixture con dati incompleti (no fixture_id/league_id/season), skip.")
            continue

        fixture_id = ctx["fixture_id"]
        league_id = ctx["league_id"]
        season_year = ctx["season_year"]

        # ✅ SKIP se già fatto (status='ok')
        if prediction_already_done(fixture_id):
            skipped_existing_count += 1
            logger.info("⏭️ skip fixture_id=%s (prediction già presente: status=ok)", fixture_id)
            continue

        now_iso = datetime.now(timezone.utc).isoformat()

        # Coverage check
        has_predictions = predictions_coverage_true(league_id, season_year, coverage_cache)

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
            upsert_prediction_row(row)
            no_cov_count += 1
            logger.info("⏭️ no_coverage fixture_id=%s (league_id=%s season=%s)", fixture_id, league_id, season_year)
            continue

        # Call predictions
        logger.info("🔮 /predictions fixture_id=%s", fixture_id)
        data = api.call("/predictions", params={"fixture": str(fixture_id)})

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
            upsert_prediction_row(row)
            empty_count += 1
            logger.warning("⚠️ empty fixture_id=%s", fixture_id)
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
            upsert_prediction_row(row)
            ok_count += 1
            logger.info("✅ ok fixture_id=%s", fixture_id)

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
            upsert_prediction_row(row)
            err_count += 1
            logger.exception("❌ error fixture_id=%s: %s", fixture_id, e)

    logger.info(
        "🏁 RIEPILOGO %s → ok=%s empty=%s no_coverage=%s error=%s skipped=%s skipped_existing=%s",
        target_date, ok_count, empty_count, no_cov_count, err_count, skipped_count, skipped_existing_count
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        help="Data YYYY-MM-DD (default: oggi in UTC)",
        default=None
    )
    args = parser.parse_args()

    target_date = args.date or datetime.now(timezone.utc).date().isoformat()
    run_for_date(target_date)


if __name__ == "__main__":
    main()
