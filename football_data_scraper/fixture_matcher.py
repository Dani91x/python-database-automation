"""
Abbina ogni riga CSV del football-data a un fixture_id nel database.

Strategia di matching (in ordine):
  1. Chiave primaria ESATTA: league_id + season_year + fixture_date + goals_home + goals_away
  2. Se trovati 0 o >1 risultati → tiebreaker con nome squadra (fuzzy match)
  3. Se ancora ambiguo o non trovato → skip con log di audit

La tabella di riferimento è `fixture_predictions` che contiene:
  fixture_id, league_id, season_year, fixture_date, home_team_name, away_team_name,
  result_home_goals, result_away_goals
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Soglia minima di similarità nome squadra per accettare il tiebreaker (caso multi-candidato)
TEAM_NAME_SIMILARITY_THRESHOLD = 0.60

# Soglia ridotta per il caso 1-solo-candidato: data+score è già univoco,
# basta escludere errori grossolani (es. squadre completamente diverse).
# Permette abbreviazioni tipo "Man City"↔"Manchester City" (sim≈0.43).
TEAM_NAME_SIMILARITY_THRESHOLD_UNIQUE = 0.30

# Prefissi/suffissi comuni da rimuovere prima del fuzzy match
_STRIP_TOKENS = re.compile(
    r"\b(AC|AS|AFC|FC|SC|SS|SL|US|CF|ACD|RC|RCD|CD|SD|UD|CE|SE|"
    r"Calcio|Football|Club|City|United|Town|Rovers|Wanderers|Athletic|Atletico)\b",
    flags=re.IGNORECASE,
)


def _normalize_team(name: str) -> str:
    """Normalizza il nome squadra per il confronto fuzzy."""
    if not isinstance(name, str):
        return ""
    n = _STRIP_TOKENS.sub("", name)
    n = re.sub(r"\s+", " ", n).strip().lower()
    return n


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize_team(a), _normalize_team(b)).ratio()


def _team_names_match(
    csv_home: str, csv_away: str,
    db_home: str, db_away: str,
    threshold: float = TEAM_NAME_SIMILARITY_THRESHOLD,
) -> bool:
    """True se home e away matchano entrambi sopra la soglia."""
    home_ok = _similarity(csv_home, db_home) >= threshold
    away_ok = _similarity(csv_away, db_away) >= threshold
    return home_ok and away_ok


# ─────────────────────────────────────────────────────────────────────────────
# Caricamento fixture dal DB
# ─────────────────────────────────────────────────────────────────────────────

def load_fixtures_for_league(
    league_id: int,
    seasons: Optional[List[int]] = None,
) -> pd.DataFrame:
    """
    Carica dalla tabella `matches` tutti i record completati (status_short='FT')
    per la lega specificata. Se `seasons` è fornito, filtra solo quelle stagioni.

    Usa `matches` (non fixture_predictions) perché contiene lo storico completo
    delle partite giocate con goals_home / goals_away e team names/ids.

    Returns:
        DataFrame con colonne:
          fixture_id, league_id, season_year, fixture_date (YYYY-MM-DD),
          home_team_id, away_team_id, home_team_name, away_team_name,
          goals_home, goals_away
    """
    import sys, os
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from db_client import get_supabase_client

    sb = get_supabase_client()
    COLS = (
        "fixture_id,league_id,season_year,fixture_date,"
        "home_team_id,away_team_id,home_team_name,away_team_name,"
        "goals_home,goals_away"
    )

    all_rows: List[Dict[str, Any]] = []
    page_size = 1000

    if seasons:
        for season_year in seasons:
            offset = 0
            while True:
                resp = (
                    sb.table("matches")
                    .select(COLS)
                    .eq("league_id", league_id)
                    .eq("season_year", season_year)
                    .eq("status_short", "FT")
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                chunk = getattr(resp, "data", None) or []
                all_rows.extend(chunk)
                if len(chunk) < page_size:
                    break
                offset += page_size
    else:
        offset = 0
        while True:
            resp = (
                sb.table("matches")
                .select(COLS)
                .eq("league_id", league_id)
                .eq("status_short", "FT")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            chunk = getattr(resp, "data", None) or []
            all_rows.extend(chunk)
            if len(chunk) < page_size:
                break
            offset += page_size

    if not all_rows:
        logger.warning("Nessuna fixture trovata nel DB per league_id=%d", league_id)
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["goals_home"] = pd.to_numeric(df["goals_home"], errors="coerce")
    df["goals_away"] = pd.to_numeric(df["goals_away"], errors="coerce")
    df = df.dropna(subset=["goals_home", "goals_away"])
    df["goals_home"] = df["goals_home"].astype(int)
    df["goals_away"] = df["goals_away"].astype(int)

    # Normalizza fixture_date a YYYY-MM-DD
    df["fixture_date"] = pd.to_datetime(
        df["fixture_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["fixture_date"])

    logger.info("Caricate %d fixture dal DB per league_id=%d", len(df), league_id)
    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Matching
# ─────────────────────────────────────────────────────────────────────────────

def match_csv_to_fixtures(
    csv_df: pd.DataFrame,
    fixtures_df: pd.DataFrame,
    season_year: int,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Abbina ogni riga del CSV a un fixture_id.

    Returns:
        matched_df : subset del csv_df con colonna aggiuntiva 'fixture_id',
                     'home_team_id', 'away_team_id' (per match_team_stats)
        audit_log  : lista di dict con dettaglio di ogni riga (matched/not/ambiguous)
    """
    if fixtures_df.empty or csv_df.empty:
        return pd.DataFrame(), []

    # Indice del DB: (season_year, fixture_date, goals_home, goals_away) → lista fixture
    db_index: Dict[Tuple, List[Dict]] = {}
    season_fixtures = fixtures_df[fixtures_df["season_year"] == season_year]

    for _, row in season_fixtures.iterrows():
        key = (
            int(row["season_year"]),
            str(row["fixture_date"]),
            int(row["goals_home"]),
            int(row["goals_away"]),
        )
        db_index.setdefault(key, []).append(row.to_dict())

    matched_rows: List[Dict] = []
    audit_log: List[Dict[str, Any]] = []

    for _, csv_row in csv_df.iterrows():
        date_iso = csv_row.get("date_iso")
        hg = int(csv_row.get("FTHG", -1))
        ag = int(csv_row.get("FTAG", -1))
        csv_home = str(csv_row.get("HomeTeam", ""))
        csv_away = str(csv_row.get("AwayTeam", ""))

        key = (season_year, date_iso, hg, ag)
        candidates = db_index.get(key, [])

        fixture_id = None
        home_team_id = None
        away_team_id = None
        match_status = "not_found"
        match_note = ""

        if len(candidates) == 1:
            # Caso ideale: match univoco su data+score
            c = candidates[0]
            sim_home = _similarity(csv_home, c["home_team_name"] or "")
            sim_away = _similarity(csv_away, c["away_team_name"] or "")
            # Con un solo candidato la chiave data+score è già fortemente univoca.
            # Usiamo una soglia ridotta (0.30) per bloccare solo errori grossolani
            # (squadre completamente diverse), accettando abbreviazioni tipo
            # "Man City"↔"Manchester City" (sim≈0.43) o "PSG"↔"Paris SG".
            if sim_home >= TEAM_NAME_SIMILARITY_THRESHOLD_UNIQUE and sim_away >= TEAM_NAME_SIMILARITY_THRESHOLD_UNIQUE:
                fixture_id = c["fixture_id"]
                home_team_id = c["home_team_id"]
                away_team_id = c["away_team_id"]
                match_status = "matched"
                # Segnala se i nomi sono abbreviati (sotto la soglia standard)
                if sim_home < TEAM_NAME_SIMILARITY_THRESHOLD or sim_away < TEAM_NAME_SIMILARITY_THRESHOLD:
                    match_note = (
                        f"abbrev: csv='{csv_home}'↔db='{c['home_team_name']}'(sim={sim_home:.2f}) "
                        f"csv='{csv_away}'↔db='{c['away_team_name']}'(sim={sim_away:.2f})"
                    )
                else:
                    match_note = f"sim_home={sim_home:.2f} sim_away={sim_away:.2f}"
            else:
                # Score univoco ma nomi completamente diversi — possibile errore di data
                match_status = "name_mismatch"
                match_note = (
                    f"csv='{csv_home}' vs db='{c['home_team_name']}' (sim={sim_home:.2f}), "
                    f"csv='{csv_away}' vs db='{c['away_team_name']}' (sim={sim_away:.2f})"
                )

        elif len(candidates) > 1:
            # Caso ambiguo: stesso score+data, serve tiebreaker nome squadra
            best: Optional[Dict] = None
            best_score = 0.0
            ambiguous_candidates = []
            for c in candidates:
                sh = _similarity(csv_home, c["home_team_name"] or "")
                sa = _similarity(csv_away, c["away_team_name"] or "")
                combined = (sh + sa) / 2.0
                ambiguous_candidates.append((combined, c))
                if combined > best_score:
                    best_score = combined
                    best = c

            if best and best_score >= TEAM_NAME_SIMILARITY_THRESHOLD:
                # Verifica che non ci siano due candidati con score molto simile (tie reale)
                top_two = sorted(ambiguous_candidates, key=lambda x: x[0], reverse=True)
                if len(top_two) >= 2 and (top_two[0][0] - top_two[1][0]) < 0.15:
                    match_status = "ambiguous_tie"
                    match_note = (
                        f"{len(candidates)} candidati, top score={top_two[0][0]:.2f} "
                        f"vs secondo={top_two[1][0]:.2f} — troppo vicini, skip"
                    )
                else:
                    fixture_id = best["fixture_id"]
                    home_team_id = best["home_team_id"]
                    away_team_id = best["away_team_id"]
                    match_status = "matched_tiebreaker"
                    match_note = f"{len(candidates)} candidati, risolto con nome (score={best_score:.2f})"
            else:
                match_status = "ambiguous_no_winner"
                match_note = f"{len(candidates)} candidati, nessun nome sopra soglia {TEAM_NAME_SIMILARITY_THRESHOLD}"

        else:
            match_status = "not_found"
            match_note = f"Nessuna partita in DB per key={key}"

        audit_entry = {
            "season_year": season_year,
            "date_iso": date_iso,
            "csv_home": csv_home,
            "csv_away": csv_away,
            "goals": f"{hg}-{ag}",
            "fixture_id": fixture_id,
            "status": match_status,
            "note": match_note,
        }
        audit_log.append(audit_entry)

        if fixture_id is not None:
            row_dict = csv_row.to_dict()
            row_dict["fixture_id"] = fixture_id
            row_dict["home_team_id"] = home_team_id
            row_dict["away_team_id"] = away_team_id
            matched_rows.append(row_dict)

    matched_df = pd.DataFrame(matched_rows) if matched_rows else pd.DataFrame()

    n_matched = sum(1 for a in audit_log if a["fixture_id"] is not None)
    n_total = len(audit_log)
    logger.info(
        "Stagione %d: %d/%d righe CSV abbinate a fixture_id (%.1f%%)",
        season_year, n_matched, n_total,
        100.0 * n_matched / n_total if n_total else 0,
    )

    return matched_df, audit_log
