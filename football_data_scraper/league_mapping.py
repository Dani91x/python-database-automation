"""
Mapping tra league_id (API-Football) e dati football-data.co.uk.
"""
from typing import Dict, Any

# Struttura per ogni lega:
#   fd_code        : codice CSV su football-data.co.uk
#   fd_start_year  : prima stagione disponibile su football-data (anno di inizio stagione)
#   category       : "main" = ha colonne AvgH/AvgD/AvgA + bookmaker individuali
#                    "extra" = ha solo AvgCH/AvgCD/AvgCA (URL diverso: /new/)
#   url_template   : URL del CSV. {season_code} = es. "2324" per 2023/24
LEAGUE_MAP: Dict[int, Dict[str, Any]] = {

    # ── INGHILTERRA ──────────────────────────────────────────────────────────
    39: {
        "name": "Premier League",
        "country": "England",
        "fd_code": "E0",
        "fd_start_year": 1993,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/E0.csv",
    },
    40: {
        "name": "Championship",
        "country": "England",
        "fd_code": "E1",
        "fd_start_year": 1993,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/E1.csv",
    },
    41: {
        "name": "League One",
        "country": "England",
        "fd_code": "E2",
        "fd_start_year": 1993,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/E2.csv",
    },
    42: {
        "name": "League Two",
        "country": "England",
        "fd_code": "E3",
        "fd_start_year": 1993,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/E3.csv",
    },
    43: {
        "name": "National League",
        "country": "England",
        "fd_code": "EC",
        "fd_start_year": 2005,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/EC.csv",
    },

    # ── GERMANIA ─────────────────────────────────────────────────────────────
    78: {
        "name": "Bundesliga",
        "country": "Germany",
        "fd_code": "D1",
        "fd_start_year": 1993,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/D1.csv",
    },
    79: {
        "name": "2. Bundesliga",
        "country": "Germany",
        "fd_code": "D2",
        "fd_start_year": 1993,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/D2.csv",
    },

    # ── ITALIA ───────────────────────────────────────────────────────────────
    135: {
        "name": "Serie A",
        "country": "Italy",
        "fd_code": "I1",
        "fd_start_year": 1993,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/I1.csv",
    },
    136: {
        "name": "Serie B",
        "country": "Italy",
        "fd_code": "I2",
        "fd_start_year": 2004,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/I2.csv",
    },

    # ── SPAGNA ───────────────────────────────────────────────────────────────
    140: {
        "name": "La Liga",
        "country": "Spain",
        "fd_code": "SP1",
        "fd_start_year": 1993,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/SP1.csv",
    },

    # ── FRANCIA ──────────────────────────────────────────────────────────────
    61: {
        "name": "Ligue 1",
        "country": "France",
        "fd_code": "F1",
        "fd_start_year": 1993,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/F1.csv",
    },
    62: {
        "name": "Ligue 2",
        "country": "France",
        "fd_code": "F2",
        "fd_start_year": 2014,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/F2.csv",
    },

    # ── OLANDA ───────────────────────────────────────────────────────────────
    88: {
        "name": "Eredivisie",
        "country": "Netherlands",
        "fd_code": "N1",
        "fd_start_year": 1993,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/N1.csv",
    },

    # ── PORTOGALLO ───────────────────────────────────────────────────────────
    94: {
        "name": "Primeira Liga",
        "country": "Portugal",
        "fd_code": "P1",
        "fd_start_year": 1994,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/P1.csv",
    },

    # ── BELGIO ───────────────────────────────────────────────────────────────
    144: {
        "name": "Belgian Pro League",
        "country": "Belgium",
        "fd_code": "B1",
        "fd_start_year": 1995,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/B1.csv",
    },

    # ── TURCHIA ──────────────────────────────────────────────────────────────
    203: {
        "name": "Super Lig",
        "country": "Turkey",
        "fd_code": "T1",
        "fd_start_year": 1994,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/T1.csv",
    },

    # ── GRECIA ───────────────────────────────────────────────────────────────
    197: {
        "name": "Super League",
        "country": "Greece",
        "fd_code": "G1",
        "fd_start_year": 1994,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/G1.csv",
    },

    # ── SCOZIA ───────────────────────────────────────────────────────────────
    179: {
        "name": "Premiership",
        "country": "Scotland",
        "fd_code": "SC0",
        "fd_start_year": 1994,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/SC0.csv",
    },
    180: {
        "name": "Championship",
        "country": "Scotland",
        "fd_code": "SC1",
        "fd_start_year": 1994,
        "category": "main",
        "url_template": "https://www.football-data.co.uk/mmz4281/{season_code}/SC1.csv",
    },
}


def get_league_info(league_id: int) -> Dict[str, Any]:
    if league_id not in LEAGUE_MAP:
        raise ValueError(
            f"League {league_id} non presente in LEAGUE_MAP. "
            f"Aggiungila prima di procedere."
        )
    return LEAGUE_MAP[league_id]


def build_csv_url(league_id: int, season_year: int) -> str:
    """Costruisce l'URL del CSV per la stagione (season_year, season_year+1)."""
    info = get_league_info(league_id)
    yy1 = str(season_year)[-2:].zfill(2)
    yy2 = str(season_year + 1)[-2:].zfill(2)
    season_code = f"{yy1}{yy2}"
    return info["url_template"].format(season_code=season_code)
