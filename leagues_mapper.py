# leagues_mapper.py
# FIX PAGINAZIONE + GESTIONE DUPLICATI + RIEPILOGO FINALE
# 25/09/2026: AGGIORNA anche i flag delle righe esistenti (stagioni vive) e
# legge le coppie esistenti a pagine (niente piu' tetto di 10.000).

import time
from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Set, Tuple

from api_client import APIFootballClient
from db_client import get_supabase_client


# 25/09/2026 - colonne confrontate/aggiornate sulle righe ESISTENTI (mai inserted_at).
CAMPI_AGGIORNABILI = (
    "season_start", "season_end", "current",
    "fixtures_events", "fixtures_lineups", "fixtures_statistics_fixtures",
    "fixtures_statistics_players", "standings", "players", "top_scorers",
    "top_assists", "top_cards", "injuries", "predictions", "odds",
)
PAGINA = 1000                 # max-rows di PostgREST su Supabase
FINESTRA_AGGIORNAMENTO_GIORNI = 30


# =========================================================
# DB helpers
# =========================================================

def get_existing_coverage_rows() -> Dict[Tuple[int, int], Dict[str, Any]]:
    """
    Carica TUTTE le righe (league_id, season_year) esistenti con i campi
    aggiornabili, a PAGINE da 1000 fino all'esaurimento (25/09/2026: prima
    .range(0, 9999) = massimo 10.000 coppie; oggi ~8.700, saturazione in ~8 mesi
    e le coppie oltre sarebbero sembrate "nuove").
    Qualunque errore -> RuntimeError (mai un insieme vuoto che fa reinserire tutto).
    """
    sb = get_supabase_client()
    righe: Dict[Tuple[int, int], Dict[str, Any]] = {}
    colonne = "league_id,season_year," + ",".join(CAMPI_AGGIORNABILI)
    inizio = 0
    while True:
        try:
            res = (
                sb.table("api_coverage_by_season")
                .select(colonne)
                .order("league_id")
                .order("season_year")
                .range(inizio, inizio + PAGINA - 1)
                .execute()
            )
        except Exception as e:
            # 25/09/2026: prima ritornava l'insieme VUOTO e si tentava di reinserire
            # TUTTE le ~8.700 coppie (duplicati "ignorati"): run verde senza lavoro.
            print("[DB] Errore lettura coppie esistenti:", e)
            raise RuntimeError(f"lettura api_coverage_by_season fallita (offset {inizio}): {e}") from e
        data = getattr(res, "data", None) or []
        for item in data:
            try:
                righe[(item["league_id"], item["season_year"])] = item
            except KeyError:
                continue
        if len(data) < PAGINA:
            break
        inizio += PAGINA

    print(f"Coppie (league_id, season_year) gia' presenti nel DB: {len(righe)}")
    return righe


def get_existing_league_season_pairs() -> Set[Tuple[int, int]]:
    """Compatibilita': l'insieme delle coppie esistenti (paginato)."""
    return set(get_existing_coverage_rows())


def _normalizza(campo: str, valore: Any) -> Any:
    if campo in ("season_start", "season_end"):
        return str(valore)[:10] if valore else None
    return bool(valore)


def differenze(riga_db: Dict[str, Any], riga_api: Dict[str, Any]) -> Dict[str, Any]:
    """Campi aggiornabili che differiscono: {campo: valore_API}."""
    out: Dict[str, Any] = {}
    for campo in CAMPI_AGGIORNABILI:
        if _normalizza(campo, riga_db.get(campo)) != _normalizza(campo, riga_api.get(campo)):
            out[campo] = riga_api.get(campo)
    return out


def in_finestra_aggiornamento(riga_db: Dict[str, Any], riga_api: Dict[str, Any],
                              oggi: Optional[date] = None) -> bool:
    """
    Si aggiornano le stagioni "vive": current=True secondo l'API o secondo il DB
    (cosi' una stagione che finisce passa a current=False), oppure con fine
    stagione >= oggi - 30 giorni. Motivo della finestra: API-Football accende i
    flag di coverage (events/lineups/statistics/odds) a stagione INIZIATA e puo'
    ritoccarli nelle settimane finali; le stagioni chiuse da oltre un mese non
    cambiano piu' e non vale la pena riscriverle ogni giorno.
    """
    oggi = oggi or datetime.now(timezone.utc).date()
    if riga_api.get("current") or riga_db.get("current"):
        return True
    fine = riga_api.get("season_end") or riga_db.get("season_end")
    try:
        return date.fromisoformat(str(fine)[:10]) >= oggi - timedelta(days=FINESTRA_AGGIORNAMENTO_GIORNI)
    except (TypeError, ValueError):
        return False


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
        print("API JSON None, stop mapping.")
        return rows

    response = api_json.get("response") or []
    if not response:
        print("JSON /leagues senza campo 'response' o vuoto.")
        return rows

    for entry in response:
        league = entry.get("league") or {}
        country = entry.get("country") or {}
        seasons = entry.get("seasons") or []

        league_id = league.get("id")
        if league_id is None:
            print("Lega senza league.id, skip.")
            continue

        league_name = league.get("name")
        country_name = country.get("name")

        for s in seasons:
            year = s.get("year")
            if year is None:
                print(f"Season senza year per league_id={league_id}, skip.")
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

    print(f"Totale righe (lega+stagione) estratte da API: {len(rows)}")
    return rows


# =========================================================
# Insert (nuove) + update (vive cambiate): SAFE / IDEMPOTENTE
# =========================================================

def upsert_coverage_rows(rows: List[Dict[str, Any]]) -> int:
    """
    (a) Inserisce le righe mancanti in api_coverage_by_season (come prima:
        nessuna delete, chunk da 500, duplicati residui tollerati).
    (b) 25/09/2026: AGGIORNA le righe esistenti nella finestra "viva"
        (in_finestra_aggiornamento) i cui flag/date/current differiscono
        dall'API: prima una riga scritta a luglio con i flag False restava False
        per sempre (135/2026). Solo i campi cambiati + updated_at; inserted_at
        MAI toccato. Un UPDATE per riga (filtro league_id + season_year): non
        dipende da un vincolo unico su (league_id, season_year).
    Ritorna il numero di errori NON previsti (0 = tutto ok).
    """
    sb = get_supabase_client()

    if not rows:
        print("Nessuna riga da processare, stop.")
        return 0

    esistenti = get_existing_coverage_rows()

    unique_json_pairs: Set[Tuple[int, int]] = set()
    filtered_rows: List[Dict[str, Any]] = []
    da_aggiornare: List[Tuple[Tuple[int, int], Dict[str, Any]]] = []

    skipped_db_dupes = 0
    skipped_json_dupes = 0
    invariate = 0
    fuori_finestra = 0

    for r in rows:
        pair = (r["league_id"], r["season_year"])

        if pair in unique_json_pairs:
            skipped_json_dupes += 1
            continue
        unique_json_pairs.add(pair)

        if pair in esistenti:
            skipped_db_dupes += 1
            riga_db = esistenti[pair]
            if not in_finestra_aggiornamento(riga_db, r):
                fuori_finestra += 1
                continue
            diff = differenze(riga_db, r)
            if diff:
                da_aggiornare.append((pair, diff))
            else:
                invariate += 1
            continue

        filtered_rows.append(r)

    # =========================
    # LOG DI PRE-INSERIMENTO
    # =========================
    print("==============================================")
    print("RIEPILOGO PRE-UPSERT")
    print(f"   Totale righe da API:           {len(rows)}")
    print(f"   Gia' presenti nel DB:          {skipped_db_dupes}")
    print(f"     - da aggiornare (cambiate):  {len(da_aggiornare)}")
    print(f"     - invariate (finestra viva): {invariate}")
    print(f"     - fuori finestra (chiuse):   {fuori_finestra}")
    print(f"   Duplicate interne API (skip):  {skipped_json_dupes}")
    print(f"   NUOVE righe da inserire:       {len(filtered_rows)}")
    print("==============================================")

    CHUNK = 500
    inserted_total = 0
    batch_errors = 0
    duplicate_residui = 0

    for i in range(0, len(filtered_rows), CHUNK):
        chunk = filtered_rows[i : i + CHUNK]
        batch_index = (i // CHUNK) + 1

        try:
            sb.table("api_coverage_by_season").upsert(chunk).execute()
            inserted_total += len(chunk)
            print(f"Upsert batch {batch_index} OK (righe: {len(chunk)})")
        except Exception as e:
            batch_errors += 1
            msg = str(e)
            if "duplicate key value violates unique constraint" in msg:
                duplicate_residui += 1
                print(f"Duplicate residuo batch {batch_index}, ignorato.")
            else:
                print(f"Errore batch {batch_index} NON previsto:", msg)

        time.sleep(0.2)

    aggiornate = 0
    errori_update = 0
    adesso = datetime.now(timezone.utc).isoformat()
    for (lid, sy), diff in da_aggiornare:
        prima = {k: esistenti[(lid, sy)].get(k) for k in diff}
        try:
            (
                sb.table("api_coverage_by_season")
                .update({**diff, "updated_at": adesso})
                .eq("league_id", lid)
                .eq("season_year", sy)
                .execute()
            )
            aggiornate += 1
            print(f"AGGIORNATA lega {lid} stagione {sy}: "
                  + ", ".join(f"{k} {prima[k]} -> {v}" for k, v in diff.items()))
        except Exception as e:
            errori_update += 1
            print(f"Errore UPDATE lega {lid} stagione {sy} NON previsto: {e}")

    # =========================
    # LOG DI RIEPILOGO FINALE
    # =========================
    print("==============================================")
    print("RIEPILOGO FINALE COVERAGE LEAGUES")
    print(f"   Inserite:                      {inserted_total}")
    print(f"   Aggiornate:                    {aggiornate}")
    print(f"   Invariate:                     {invariate + fuori_finestra}")
    print(f"   Batch insert con errori:       {batch_errors}")
    print(f"   Update con errori:             {errori_update}")
    print("   Operazione completata senza cancellazioni.")
    print("==============================================")
    return batch_errors - duplicate_residui + errori_update


# =========================================================
# Orchestratore
# =========================================================

def run_full_leagues_backfill_mapping() -> None:
    print("==============================================")
    print("AVVIO AGGIORNAMENTO COVERAGE /leagues")
    print("==============================================")

    client = APIFootballClient()
    data = client.get_leagues()

    rows = map_leagues_to_coverage_rows(data)
    # 25/09/2026 - FALLIMENTO RUMOROSO: APIFootballClient.call ritorna {} su
    # qualunque errore e i batch in errore erano solo stampati: il run chiudeva
    # VERDE anche senza aver fatto nulla. Ora exit != 0 in entrambi i casi.
    if not rows:
        raise SystemExit("LEAGUES MAPPER FALLITO: /leagues vuoto o in errore (vedi log [API]).")
    errori = upsert_coverage_rows(rows)
    if errori:
        raise SystemExit(f"LEAGUES MAPPER FALLITO: {errori} batch in errore NON previsto (vedi log).")

    print("SCRIPT COMPLETATO")


if __name__ == "__main__":
    run_full_leagues_backfill_mapping()
