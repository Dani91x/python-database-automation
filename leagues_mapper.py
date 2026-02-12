# leagues_mapper.py
# FIX PAGINAZIONE + GESTIONE DUPLICATI + RIEPILOGO FINALE

import time
from typing import List, Dict, Any, Optional, Set, Tuple

from api_client import APIFootballClient
from db_client import get_supabase_client


# =========================================================
# DB helpers
# =========================================================

def get_existing_league_season_pairs() -> Set[Tuple[int, int]]:
    """
    Carica TUTTE le coppie (league_id, season_year) esistenti nel DB.
    Usa .range(0, 9999) per superare il limite di default (1000 righe).
    """
    sb = get_supabase_client()
    pairs: Set[Tuple[int, int]] = set()

    try:
        res = (
            sb.table("api_coverage_by_season")
            .select("league_id,season_year")
            .range(0, 9999)
            .execute()
        )
    except Exception as e:
        print("[DB] ❌ Errore lettura coppie esistenti:", e)
        return pairs

    data = getattr(res, "data", None) or []
    for item in data:
        try:
            pairs.add((item["league_id"], item["season_year"]))
        except KeyError:
            continue

    print(f"📌 Coppie (league_id, season_year) già presenti nel DB: {len(pairs)}")
    return pairs


# =========================================================
# Mapping helpers
# =========================================================

def clean_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalizza le chiavi rimuovendo eventuali spazi."""
    return {k.strip(): v for k, v in row.items()}


def map_leagues_to_coverage_rows(api_json: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Estrae tutte le leghe + stagioni dal JSON /leagues.
    Ritorna una lista di righe pronte per api_coverage_by_season.
    """
    rows: List[Dict[str, Any]] = []

    if not api_json:
        print("❌ API JSON None, stop mapping.")
        return rows

    response = api_json.get("response") or []
    if not response:
        print("❌ JSON /leagues senza campo 'response' o vuoto.")
        return rows

    for entry in response:
        league = entry.get("league") or {}
        country = entry.get("country") or {}
        seasons = entry.get("seasons") or []

        league_id = league.get("id")
        if league_id is None:
            print("⚠️ Lega senza league.id, skip.")
            continue

        league_name = league.get("name")
        country_name = country.get("name")

        for s in seasons:
            year = s.get("year")
            if year is None:
                print(f"⚠️ Season senza year per league_id={league_id}, skip.")
                continue

            coverage = s.get("coverage") or {}
            fixtures = coverage.get("fixtures") or {}

            row: Dict[str, Any] = {
                "league_id": league_id,
                "league_name": league_name,
                "country_name": country_name,
                "season_year": year,

                "season_start": s.get("start"),
                "season_end": s.get("end"),
                "current": s.get("current", False),

                # coverage fixtures
                "fixtures_events": fixtures.get("events", False),
                "fixtures_lineups": fixtures.get("lineups", False),
                "fixtures_statistics_fixtures": fixtures.get("statistics_fixtures", False),
                "fixtures_statistics_players": fixtures.get("statistics_players", False),

                # coverage aggregati
                "standings": coverage.get("standings", False),
                "players": coverage.get("players", False),
                "top_scorers": coverage.get("top_scorers", False),
                "top_assists": coverage.get("top_assists", False),
                "top_cards": coverage.get("top_cards", False),
                "injuries": coverage.get("injuries", False),
                "predictions": coverage.get("predictions", False),
                "odds": coverage.get("odds", False),
            }

            rows.append(clean_keys(row))

    print(f"📌 Totale righe (lega+stagione) estratte da API: {len(rows)}")
    return rows


# =========================================================
# Upsert logic (SAFE / IDPOTENTE)
# =========================================================

def upsert_coverage_rows(rows: List[Dict[str, Any]]) -> None:
    """
    Inserisce SOLO le righe mancanti in api_coverage_by_season.
    - Nessuna delete
    - Nessuna sovrascrittura
    - Chunk safe
    """
    sb = get_supabase_client()

    if not rows:
        print("❌ Nessuna riga da processare, stop.")
        return

    existing_pairs = get_existing_league_season_pairs()

    unique_json_pairs: Set[Tuple[int, int]] = set()
    filtered_rows: List[Dict[str, Any]] = []

    skipped_db_dupes = 0
    skipped_json_dupes = 0

    for r in rows:
        pair = (r["league_id"], r["season_year"])

        if pair in existing_pairs:
            skipped_db_dupes += 1
            continue

        if pair in unique_json_pairs:
            skipped_json_dupes += 1
            continue

        unique_json_pairs.add(pair)
        filtered_rows.append(r)

    # =========================
    # LOG DI PRE-INSERIMENTO
    # =========================
    print("==============================================")
    print("📊 RIEPILOGO PRE-UPSERT")
    print(f"   Totale righe da API:           {len(rows)}")
    print(f"   Già presenti nel DB (skip):    {skipped_db_dupes}")
    print(f"   Duplicate interne API (skip):  {skipped_json_dupes}")
    print(f"   NUOVE righe da inserire:       {len(filtered_rows)}")
    print("==============================================")

    if not filtered_rows:
        print("✅ Nessuna nuova lega/stagione da inserire. DB già allineato.")
        return

    CHUNK = 500
    inserted_total = 0
    batch_errors = 0

    for i in range(0, len(filtered_rows), CHUNK):
        chunk = filtered_rows[i : i + CHUNK]
        batch_index = (i // CHUNK) + 1

        try:
            sb.table("api_coverage_by_season").upsert(chunk).execute()
            inserted_total += len(chunk)
            print(f"✅ Upsert batch {batch_index} OK (righe: {len(chunk)})")
        except Exception as e:
            batch_errors += 1
            msg = str(e)
            if "duplicate key value violates unique constraint" in msg:
                print(f"⚠️ Duplicate residuo batch {batch_index}, ignorato.")
            else:
                print(f"❌ Errore batch {batch_index} NON previsto:", msg)

        time.sleep(0.2)

    # =========================
    # LOG DI RIEPILOGO FINALE
    # =========================
    print("==============================================")
    print("🏁 RIEPILOGO FINALE COVERAGE LEAGUES")
    print(f"   Righe inserite correttamente:  {inserted_total}")
    print(f"   Batch con errori:              {batch_errors}")
    print("   Operazione completata senza cancellazioni.")
    print("==============================================")


# =========================================================
# Orchestratore
# =========================================================

def run_full_leagues_backfill_mapping() -> None:
    print("==============================================")
    print("🚀 AVVIO AGGIORNAMENTO COVERAGE /leagues")
    print("==============================================")

    client = APIFootballClient()
    data = client.get_leagues()

    rows = map_leagues_to_coverage_rows(data)
    upsert_coverage_rows(rows)

    print("🏁 SCRIPT COMPLETATO")


if __name__ == "__main__":
    run_full_leagues_backfill_mapping()
