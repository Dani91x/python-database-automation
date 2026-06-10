"""
READ-ONLY data loader per lega. Carica matches (risultati) + match_odds (1X2 e OU2.5)
per una lega, con paginazione. Nessuna scrittura.

Espone:
  load_matches(league_id) -> pd.DataFrame
  load_odds(league_id, market_key) -> pd.DataFrame (long: fixture_id, bookmaker_name, label, odd_value)
  build_odds_wide(odds_df) -> pivot per fixture con colonne tipo Avg_Home, PinnacleC_Home, Max_Home...
"""
from __future__ import annotations
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_client import get_supabase_client  # noqa: E402

_c = get_supabase_client()
PAGE = 1000

# bookmaker che useremo (consenso + sharp + best price), apertura e chiusura
ODDS_BOOKMAKERS = [
    "Average", "Average_closing",
    "Pinnacle", "Pinnacle_closing",
    "Maximum", "Maximum_closing",
    "Bet365", "Bet365_closing",
]


def _paginate(query_builder):
    """Esegue una query paginata e ritorna lista di dict."""
    out, start = [], 0
    while True:
        resp = query_builder().range(start, start + PAGE - 1).execute()
        rows = resp.data or []
        out.extend(rows)
        if len(rows) < PAGE:
            break
        start += PAGE
    return out


def load_matches(league_id: int) -> pd.DataFrame:
    rows = _paginate(lambda: _c.table("matches").select(
        "fixture_id,league_id,season_year,fixture_date,home_team_id,away_team_id,"
        "home_team_name,away_team_name,goals_home,goals_away,halftime_home,halftime_away,status_short"
    ).eq("league_id", league_id).order("fixture_date"))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df[df["status_short"].isin(["FT", "AET", "PEN"])].copy()
    df["fixture_date"] = pd.to_datetime(df["fixture_date"], utc=True)
    for col in ["goals_home", "goals_away", "halftime_home", "halftime_away"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["goals_home", "goals_away"]).sort_values("fixture_date").reset_index(drop=True)
    return df


def load_odds(league_id: int, market_key: str = "1", seasons: list | None = None) -> pd.DataFrame:
    """Carica odds per lega. Itera per stagione per evitare statement timeout sul server."""
    if seasons is None:
        seasons = list(range(2008, 2027))
    all_rows = []
    for yr in seasons:
        try:
            rows = _paginate(lambda yr=yr: _c.table("match_odds").select(
                "fixture_id,bookmaker_name,label,odd_value,market_key"
            ).eq("league_id", league_id).eq("season_year", yr).eq("market_key", market_key)
                .in_("bookmaker_name", ODDS_BOOKMAKERS))
            all_rows.extend(rows)
        except Exception:
            # fallback: salta la stagione problematica
            continue
    df = pd.DataFrame(all_rows)
    if not df.empty:
        df["odd_value"] = pd.to_numeric(df["odd_value"], errors="coerce")
    return df


# ── Caching locale (read-only verso il DB; salva copie su disco) ───────────
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def get_league_data(league_id: int, market_keys=("1", "5"), refresh: bool = False):
    """Ritorna (matches_df, {market_key: odds_wide_df}) con cache su disco."""
    mpath = os.path.join(CACHE_DIR, f"matches_{league_id}.pkl")
    if refresh or not os.path.exists(mpath):
        m = load_matches(league_id)
        m.to_pickle(mpath)
    else:
        m = pd.read_pickle(mpath)
    odds = {}
    for mk in market_keys:
        opath = os.path.join(CACHE_DIR, f"odds_{league_id}_{mk}.pkl")
        if refresh or not os.path.exists(opath):
            w = build_odds_wide(load_odds(league_id, mk))
            w.to_pickle(opath)
        else:
            w = pd.read_pickle(opath)
        odds[mk] = w
    return m, odds


def build_odds_wide(odds_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot: una riga per fixture, colonne <bookmaker>__<label>."""
    if odds_df.empty:
        return pd.DataFrame()
    odds_df = odds_df.dropna(subset=["odd_value"])
    odds_df = odds_df[(odds_df["odd_value"] > 1.0) & (odds_df["odd_value"] < 1000)]
    # se duplicati (più snapshot), prendi il primo
    odds_df = odds_df.drop_duplicates(subset=["fixture_id", "bookmaker_name", "label"])
    wide = odds_df.pivot_table(
        index="fixture_id", columns=["bookmaker_name", "label"],
        values="odd_value", aggfunc="first"
    )
    wide.columns = [f"{b}__{l}" for b, l in wide.columns]
    return wide.reset_index()


if __name__ == "__main__":
    # Coverage check su leghe principali
    LEAGUES = {39: "Premier", 40: "Championship", 78: "Bundesliga", 135: "Serie A",
               140: "La Liga", 61: "Ligue 1", 88: "Eredivisie", 94: "Primeira",
               203: "Super Lig", 144: "Jupiler", 71: "Brasileirao", 128: "Argentina"}
    print(f"{'lega':<14}{'matches':>9}{'odds1x2_fx':>12}{'AvgC_H':>9}{'PinC_H':>9}{'Max_H':>9}{'span':>22}")
    for lid, name in LEAGUES.items():
        try:
            m = load_matches(lid)
            o = load_odds(lid, "1")
            w = build_odds_wide(o)
            n_avgc = w["Average_closing__Home"].notna().sum() if (not w.empty and "Average_closing__Home" in w) else 0
            n_pinc = w["Pinnacle_closing__Home"].notna().sum() if (not w.empty and "Pinnacle_closing__Home" in w) else 0
            n_max = w["Maximum__Home"].notna().sum() if (not w.empty and "Maximum__Home" in w) else 0
            span = ""
            if not m.empty:
                span = f"{m['season_year'].min()}-{m['season_year'].max()}"
            print(f"{name:<14}{len(m):>9}{(0 if w.empty else len(w)):>12}{n_avgc:>9}{n_pinc:>9}{n_max:>9}{span:>22}")
        except Exception as e:
            print(f"{name:<14} ERR {e}")
