# Prediction/today_predictions_backfill.py

from __future__ import annotations

import argparse
import logging
import sys
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
import math
from typing import Any, Dict, List, Optional, Tuple, Set

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

        resp = query.range(offset, offset + page_size - 1).execute()
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
        resp = sb.table("matches") \
            .select("fixture_id, league_id, goals_home, goals_away, halftime_home, halftime_away") \
            .in_("status_short", ["FT", "AET", "PEN"]) \
            .gte("fixture_date", cutoff_date) \
            .range(offset, offset + page_size - 1) \
            .execute()
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
        p_res = sb.table("fixture_predictions") \
            .select("fixture_id, ht_predictions, raw_json_odds") \
            .in_("fixture_id", batch) \
            .execute()
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


def odds_coverage_true(
    league_id: int,
    season_year: int,
    cache: Dict[Tuple[int, int], bool],
) -> bool:
    """
    Legge da api_coverage_by_season la colonna 'odds' per (league_id, season_year).
    Cache per evitare query ripetute.
    """
    key = (league_id, season_year)
    if key in cache:
        return cache[key]

    sb = get_supabase_client()
    try:
        resp = (
            sb.table("api_coverage_by_season")
            .select("odds")
            .eq("league_id", league_id)
            .eq("season_year", season_year)
            .maybe_single()
            .execute()
        )
        row = getattr(resp, "data", None) or {}
        flag = bool(row.get("odds"))
    except Exception as e:
        # 406 can happen if column doesn't exist or view doesn't expose it
        logger.error(
            "❌ Errore nel leggere coverage odds (league_id=%s season=%s): %s",
            league_id, season_year, e
        )
        flag = False

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


def upsert_odds_row(fixture_id: int, raw_json_odds: Optional[Dict[str, Any]]) -> None:
    """
    Salva le odds grezze in fixture_predictions.raw_json_odds.
    Non tocca gli altri campi.
    """
    sb = get_supabase_client()
    row = {
        "raw_json_odds": raw_json_odds,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = sb.table("fixture_predictions").update(row).eq("fixture_id", fixture_id).execute()
    updated = getattr(resp, "data", None)
    if not updated:
        logger.warning("⚠️ Nessuna riga fixture_predictions trovata per fixture_id=%s (odds non salvate)", fixture_id)


def upsert_analysis_data(fixture_id: int, db_json_analisi: Optional[Dict[str, Any]], ht_predictions: Optional[Dict[str, Any]]) -> None:
    """
    Salva sia l'analisi completa che quella specifica per l'HT.
    """
    sb = get_supabase_client()
    row = {
        "db_json_analisi": db_json_analisi,
        "ht_predictions": ht_predictions,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = sb.table("fixture_predictions").update(row).eq("fixture_id", fixture_id).execute()
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
        resp = (
            sb.table("fixture_predictions")
            .select("fixture_id,status,ht_predictions")
            .eq("fixture_id", fixture_id)
            .maybe_single()
            .execute()
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

def _poisson_prob(lmbda: float, k: int) -> float:
    if lmbda <= 0:
        return 0.0
    return math.exp(-lmbda) * (lmbda ** k) / math.factorial(k)


# Dixon-Coles correlation parameter.
# Negative value: 0-0 and 1-1 occur MORE often than independent Poisson predicts;
# 1-0 and 0-1 occur LESS often.  Literature range: ρ ∈ [−0.20, −0.08].
# We use the original Dixon & Coles (1997) estimate: ρ = −0.13.
DC_RHO: float = -0.13


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
        if str(r.get("status_short") or "").upper() in {"FT", "AET", "PEN"}:
            played.append(r)

    team_hist: Dict[int, List[Dict[str, Any]]] = {}
    for m in played:
        fixture_date = m.get("fixture_date")
        home_id = m.get("home_team_id")
        away_id = m.get("away_team_id")
        goals_home = m.get("goals_home") or 0
        goals_away = m.get("goals_away") or 0
        ht_home = m.get("halftime_home")
        ht_away = m.get("halftime_away")

        if home_id is not None:
            team_hist.setdefault(int(home_id), []).append(
                {
                    "fixture_id": m.get("fixture_id"),
                    "fixture_date": fixture_date,
                    "team_id": int(home_id),
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
        league_home_avg = sum((m.get("goals_home") or 0) for m in played) / total_matches
        league_away_avg = sum((m.get("goals_away") or 0) for m in played) / total_matches
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

    for i in range(0, len(fixture_ids), 500):
        chunk = fixture_ids[i : i + 500]
        rows = _fetch_all_table(
            "match_team_stats",
            "fixture_id,team_id,stat_type,value_numeric",
            filters=[("eq", "league_id", league_id), ("eq", "season_year", season_year), ("in", "fixture_id", chunk)],
            page_size=1000,
        )
        for r in rows:
            st = str(r.get("stat_type") or "").lower()
            if "expected" in st or "xg" in st:
                key2 = (int(r.get("fixture_id")), int(r.get("team_id")))
                val = r.get("value_numeric")
                try:
                    val_f = float(val)
                except Exception:
                    continue
                prev = xg_map.get(key2)
                if prev is None or val_f > prev:
                    xg_map[key2] = val_f

    cache[key] = xg_map
    return xg_map


def _window_stats(team_matches: List[Dict[str, Any]], n: int, xg_map: Dict[Tuple[int, int], float]) -> Dict[str, Optional[float]]:
    if not team_matches:
        return {"gf_avg": None, "ga_avg": None, "xg_avg": None, "n_used": 0}

    recent = team_matches[-n:]
    gf = [m.get("goals_for", 0) for m in recent]
    ga = [m.get("goals_against", 0) for m in recent]
    xg_vals = []
    for m in recent:
        fx_id = m.get("fixture_id")
        team_id = m.get("team_id")
        if fx_id is None or team_id is None:
            continue
        val = xg_map.get((int(fx_id), int(team_id)))
        if val is not None:
            xg_vals.append(val)

    return {
        "gf_avg": sum(gf) / len(gf) if gf else None,
        "ga_avg": sum(ga) / len(ga) if ga else None,
        "xg_avg": sum(xg_vals) / len(xg_vals) if xg_vals else None,
        "n_used": len(recent),
        "xg_used": len(xg_vals),
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
    }


def compute_db_json_analisi(
    ctx: Dict[str, Any],
    match_cache: Dict[Tuple[int, int], Dict[str, Any]],
    xg_cache: Dict[Tuple[int, int], Dict[Tuple[int, int], float]],
) -> Optional[Dict[str, Any]]:
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

    xg_h = _shrink(ctx_blend_h.get("xg_blend"), ctx_n_h, league_home_avg)
    xg_a = _shrink(ctx_blend_a.get("xg_blend"), ctx_n_a, league_away_avg)

    # Attack and defense coefficients normalised to their respective league baselines.
    # Neutral team (averages exactly the league) yields coefficient = 1.0 in all cases.
    home_attack = ((eta_goals * gf_h) + ((1 - eta_goals) * xg_h)) / league_home_avg
    away_attack = ((eta_goals * gf_a) + ((1 - eta_goals) * xg_a)) / league_away_avg
    home_def    = ga_h / league_away_avg   # goals visitors score against home team / league away avg
    away_def    = ga_a / league_home_avg   # goals home opponents score against away team / league home avg

    lambda_home = max(0.05, league_home_avg * home_attack * away_def)
    lambda_away = max(0.05, league_away_avg * away_attack * home_def)

    max_goals = 6
    probs = []
    for hg in range(0, max_goals + 1):
        p_h = _poisson_prob(lambda_home, hg)
        for ag in range(0, max_goals + 1):
            tau = _dc_tau(hg, ag, lambda_home, lambda_away)
            p = p_h * _poisson_prob(lambda_away, ag) * tau
            probs.append((hg, ag, p))

    total_p = sum(p for _, _, p in probs) or 1.0
    probs = [(hg, ag, p / total_p) for hg, ag, p in probs]

    p_home = sum(p for hg, ag, p in probs if hg > ag)
    p_draw = sum(p for hg, ag, p in probs if hg == ag)
    p_away = sum(p for hg, ag, p in probs if hg < ag)
    p_over15 = sum(p for hg, ag, p in probs if (hg + ag) >= 2)
    p_under15 = 1.0 - p_over15
    p_over25 = sum(p for hg, ag, p in probs if (hg + ag) >= 3)
    p_under25 = 1.0 - p_over25
    p_over35 = sum(p for hg, ag, p in probs if (hg + ag) >= 4)
    p_under35 = 1.0 - p_over35
    p_btts = sum(p for hg, ag, p in probs if hg > 0 and ag > 0)
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
    ht_probs = []
    for _hg in range(0, max_goals_ht + 1):
        _p_h = _poisson_prob(lambda_ht_home, _hg)
        for _ag in range(0, max_goals_ht + 1):
            _tau = _dc_tau(_hg, _ag, lambda_ht_home, lambda_ht_away)
            _p = _p_h * _poisson_prob(lambda_ht_away, _ag) * _tau
            ht_probs.append((_hg, _ag, _p))
    _ht_total = sum(p for _, _, p in ht_probs) or 1.0
    ht_probs = [(_hg, _ag, p / _ht_total) for _hg, _ag, p in ht_probs]
    p_ht_home = sum(p for _hg, _ag, p in ht_probs if _hg > _ag)
    p_ht_draw = sum(p for _hg, _ag, p in ht_probs if _hg == _ag)
    p_ht_away = sum(p for _hg, _ag, p in ht_probs if _hg < _ag)

    def _team_p_goal_1h(matches: List[Dict[str, Any]]) -> float:
        if not matches:
            return 0.5
        recent = matches[-15:]
        flags = []
        for m in recent:
            ht = m.get("halftime_for")
            if ht is None:
                continue
            flags.append(1 if ht > 0 else 0)
        if not flags:
            return 0.5
        return sum(flags) / len(flags)

    # Coerenza contestuale: stessa lista usata per _compute_ht_ratio (home_home / away_away).
    # Se la lista contestuale è troppo corta, _team_p_goal_1h ritorna il prior 0.5
    # tramite il proprio guard (flags vuoto → return 0.5).
    p_home_1h = _team_p_goal_1h(home_home)
    p_away_1h = _team_p_goal_1h(away_away)
    p_goal_1h_freq = 1.0 - ((1 - p_home_1h) * (1 - p_away_1h))

    # --- HYBRID HT MODEL ---
    lambda_1h = lambda_home * ht_ratio_h + lambda_away * ht_ratio_a
    p_goal_1h_poisson = 1.0 - math.exp(-lambda_1h)
    p_hybrid_1h = (p_goal_1h_freq + p_goal_1h_poisson) / 2.0
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
            "home_matches_used": int(home_n_used),
            "away_matches_used": int(away_n_used),
            "home_xg_covered": int(stats15_h.get("xg_used", 0)),
            "away_xg_covered": int(stats15_a.get("xg_used", 0)),
            "ht_ratio_home": round(ht_ratio_h, 3),
            "ht_ratio_away": round(ht_ratio_a, 3),
            "dc_rho": DC_RHO,
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
                    "poisson": round(p_goal_1h_poisson, 4)
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
            "poisson": round(p_goal_1h_poisson, 4)
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
    sb.table("fixture_predictions").upsert(row, on_conflict="fixture_id").execute()


# ==============================
# Runner
# ==============================

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
            # dopo prediction, inserisco odds per questo fixture
            if odds_coverage_true(league_id, season_year, odds_coverage_cache):
                odds_json = fetch_odds_for_league_season(api, league_id, season_year, odds_cache)
                odds_item = extract_odds_for_fixture(odds_json, fixture_id)
                upsert_odds_row(fixture_id, odds_item)
                logger.info("💾 odds salvate per fixture_id=%s (league_id=%s season=%s)", fixture_id, league_id, season_year)
            else:
                upsert_odds_row(fixture_id, None)
                logger.info("⏭️ odds no_coverage fixture_id=%s (league_id=%s season=%s)", fixture_id, league_id, season_year)

            # db_json_analisi (sempre)
            try:
                res = compute_db_json_analisi(ctx, match_cache, xg_cache)
                if res:
                    analysis_json, ht_pred = res
                    upsert_analysis_data(fixture_id, analysis_json, ht_pred)
            except Exception as e:
                logger.warning("db_json_analisi failed fixture_id=%s: %s", fixture_id, e)
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
            # dopo prediction, inserisco odds per questo fixture
            if odds_coverage_true(league_id, season_year, odds_coverage_cache):
                odds_json = fetch_odds_for_league_season(api, league_id, season_year, odds_cache)
                odds_item = extract_odds_for_fixture(odds_json, fixture_id)
                upsert_odds_row(fixture_id, odds_item)
                logger.info("💾 odds salvate per fixture_id=%s (league_id=%s season=%s)", fixture_id, league_id, season_year)
            else:
                upsert_odds_row(fixture_id, None)
                logger.info("⏭️ odds no_coverage fixture_id=%s (league_id=%s season=%s)", fixture_id, league_id, season_year)

            # db_json_analisi (sempre)
            try:
                res = compute_db_json_analisi(ctx, match_cache, xg_cache)
                if res:
                    analysis_json, ht_pred = res
                    upsert_analysis_data(fixture_id, analysis_json, ht_pred)
            except Exception as e:
                logger.warning("db_json_analisi failed fixture_id=%s: %s", fixture_id, e)
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

            # dopo prediction, inserisco odds per questo fixture
            if odds_coverage_true(league_id, season_year, odds_coverage_cache):
                odds_json = fetch_odds_for_league_season(api, league_id, season_year, odds_cache)
                odds_item = extract_odds_for_fixture(odds_json, fixture_id)
                upsert_odds_row(fixture_id, odds_item)
                logger.info("💾 odds salvate per fixture_id=%s (league_id=%s season=%s)", fixture_id, league_id, season_year)
            else:
                upsert_odds_row(fixture_id, None)
                logger.info("⏭️ odds no_coverage fixture_id=%s (league_id=%s season=%s)", fixture_id, league_id, season_year)

            # db_json_analisi (sempre)
            try:
                res = compute_db_json_analisi(ctx, match_cache, xg_cache)
                if res:
                    analysis_json, ht_pred = res
                    upsert_analysis_data(fixture_id, analysis_json, ht_pred)
            except Exception as e:
                logger.warning("db_json_analisi failed fixture_id=%s: %s", fixture_id, e)

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

            # dopo prediction (errore), inserisco odds per questo fixture
            if odds_coverage_true(league_id, season_year, odds_coverage_cache):
                odds_json = fetch_odds_for_league_season(api, league_id, season_year, odds_cache)
                odds_item = extract_odds_for_fixture(odds_json, fixture_id)
                upsert_odds_row(fixture_id, odds_item)
                logger.info("💾 odds salvate per fixture_id=%s (league_id=%s season=%s)", fixture_id, league_id, season_year)
            else:
                upsert_odds_row(fixture_id, None)
                logger.info("⏭️ odds no_coverage fixture_id=%s (league_id=%s season=%s)", fixture_id, league_id, season_year)

            # db_json_analisi (sempre)
            try:
                res = compute_db_json_analisi(ctx, match_cache, xg_cache)
                if res:
                    analysis_json, ht_pred = res
                    upsert_analysis_data(fixture_id, analysis_json, ht_pred)
            except Exception as e:
                logger.warning("db_json_analisi failed fixture_id=%s: %s", fixture_id, e)

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
