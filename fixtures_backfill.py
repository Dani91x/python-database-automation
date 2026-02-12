# fixtures_backfill.py
import time
from typing import Any, Dict, List, Optional

from api_client import APIFootballClient
from db_client import get_supabase_client


def map_fixture_to_row(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Mappa un singolo elemento della response /fixtures in una riga per la tabella matches.
    Gestisce chiavi mancanti e valori null.
    """
    fixture = entry.get("fixture") or {}
    league = entry.get("league") or {}
    teams = entry.get("teams") or {}
    goals = entry.get("goals") or {}
    score = entry.get("score") or {}

    fixture_id = fixture.get("id")
    league_id = league.get("id")
    season_year = league.get("season")

    if fixture_id is None or league_id is None or season_year is None:
        print(f"⚠️ fixture senza id/league/season, skip → raw: {entry}")
        return None

    # fixture info
    fixture_date = fixture.get("date")
    venue = fixture.get("venue") or {}
    venue_name = venue.get("name")
    venue_city = venue.get("city")

    status = fixture.get("status") or {}
    status_short = status.get("short")
    status_long = status.get("long")
    status_elapsed = status.get("elapsed")

    # teams
    home = teams.get("home") or {}
    away = teams.get("away") or {}

    home_team_id = home.get("id")
    home_team_name = home.get("name")
    away_team_id = away.get("id")
    away_team_name = away.get("name")

    # goals
    goals_home = goals.get("home")
    goals_away = goals.get("away")

    # detailed scores
    ht = score.get("halftime") or {}
    ft = score.get("fulltime") or {}
    et = score.get("extratime") or {}
    pen = score.get("penalty") or {}

    row: Dict[str, Any] = {
        "fixture_id": fixture_id,
        "league_id": league_id,
        "season_year": season_year,

        "fixture_date": fixture_date,
        "venue_name": venue_name,
        "venue_city": venue_city,
        "status_short": status_short,
        "status_long": status_long,
        "status_elapsed": status_elapsed,

        "home_team_id": home_team_id,
        "home_team_name": home_team_name,
        "away_team_id": away_team_id,
        "away_team_name": away_team_name,

        "goals_home": goals_home,
        "goals_away": goals_away,

        "halftime_home": ht.get("home"),
        "halftime_away": ht.get("away"),
        "fulltime_home": ft.get("home"),
        "fulltime_away": ft.get("away"),
        "extratime_home": et.get("home"),
        "extratime_away": et.get("away"),
        "penalty_home": pen.get("home"),
        "penalty_away": pen.get("away"),

        # salviamo anche il raw completo per debug / futuri usi
        "raw_json": entry,
    }

    return row


def fetch_fixtures_for_season(league_id: int, season_year: int) -> List[Dict[str, Any]]:
    """
    Chiama l'endpoint /fixtures per una specifica lega+stagione
    e ritorna la lista completa degli elementi 'response'.
    """
    client = APIFootballClient()
    params = {
        "league": league_id,
        "season": season_year,
    }

    print(f"📡 Chiamata API /fixtures per league={league_id}, season={season_year} ...")
    data = client.call("/fixtures", params=params)

    if not data:
        print("❌ Nessun dato ricevuto da /fixtures (JSON vuoto o errore).")
        return []

    response = data.get("response") or []
    print(f"📌 Fixtures ricevute da API: {len(response)}")
    return response


def upsert_matches(rows: List[Dict[str, Any]]) -> None:
    """
    Inserisce le righe nella tabella matches.
    Gestisce duplicati su fixture_id senza bloccare tutto.
    """
    if not rows:
        print("❌ Nessuna riga da inserire in matches.")
        return

    sb = get_supabase_client()
    CHUNK = 200  # chunk più piccoli per sicurezza

    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        print(f"💾 Scrittura chunk matches {i//CHUNK + 1} (righe: {len(chunk)}) ...")
        try:
            # Proviamo upsert: se la libreria/REST gestisce merge, ok;
            # se salta fuori un duplicate key, lo intercettiamo sotto.
            sb.table("matches").upsert(chunk, on_conflict="fixture_id").execute()
            print(f"✅ upsert matches batch {i//CHUNK + 1} completato.")
        except Exception as e:
            msg = str(e)
            if "duplicate key value violates unique constraint" in msg:
                print(f"⚠️ Duplicate matches su fixture_id in batch {i//CHUNK + 1}, ignoro e continuo.")
                continue
            else:
                print(f"❌ Errore imprevisto durante upsert matches batch {i//CHUNK + 1}: {msg}")

        time.sleep(0.2)

    print("🚀 Inserimento fixtures in matches completato.")


def backfill_fixtures_for_league_season(league_id: int, season_year: int) -> None:
    """
    Flusso completo:
    1. chiama /fixtures?league=&season=
    2. mappa ogni elemento in una riga matches
    3. salva nel DB con upsert sicuro
    """
    fixtures_json = fetch_fixtures_for_season(league_id, season_year)

    if not fixtures_json:
        print("❌ Nessuna fixture da mappare, stop.")
        return

    rows: List[Dict[str, Any]] = []
    skipped = 0

    for entry in fixtures_json:
        row = map_fixture_to_row(entry)
        if row is None:
            skipped += 1
            continue
        rows.append(row)

    print(f"📌 Totale fixtures mappate in righe matches: {len(rows)} (skippate: {skipped})")

    upsert_matches(rows)


def ask_and_run_cli():
    """
    Piccola CLI per testare il backfill da terminale:
    chiede league_id e season_year, con default intelligenti.
    """
    print("=== Backfill Fixtures per League+Season ===")
    league_in = input("➡️  Inserisci league_id (default 4 - Euro Championship): ").strip()
    season_in = input("➡️  Inserisci season_year (default 2016): ").strip()

    if not league_in:
        league_id = 4
    else:
        try:
            league_id = int(league_in)
        except ValueError:
            print("❌ league_id non valido, deve essere un intero.")
            return

    if not season_in:
        season_year = 2016
    else:
        try:
            season_year = int(season_in)
        except ValueError:
            print("❌ season_year non valido, deve essere un intero.")
            return

    print(f"\n▶️ Avvio backfill fixtures per league_id={league_id}, season_year={season_year}\n")
    backfill_fixtures_for_league_season(league_id, season_year)


if __name__ == "__main__":
    ask_and_run_cli()
