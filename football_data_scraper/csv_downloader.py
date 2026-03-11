"""
Scarica il CSV grezzo da football-data.co.uk per una specifica lega/stagione.
Restituisce un DataFrame con TUTTE le colonne originali, non filtrate.
"""
from __future__ import annotations

import logging
import pandas as pd
from typing import Optional
from urllib.error import HTTPError, URLError

from .league_mapping import build_csv_url, get_league_info

logger = logging.getLogger(__name__)

# Colonne obbligatorie per poter procedere con il matching
REQUIRED_COLS = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}

# Alias per normalizzare nomi colonna variabili nei CSV più vecchi
COLUMN_ALIASES = {
    "Home":     "HomeTeam",
    "Away":     "AwayTeam",
    "HG":       "FTHG",
    "AG":       "FTAG",
    "Result":   "FTR",
    "Res":      "FTR",
}


def download_csv(league_id: int, season_year: int) -> Optional[pd.DataFrame]:
    """
    Scarica il CSV di football-data.co.uk per la stagione indicata.

    Returns:
        DataFrame con tutte le colonne originali, oppure None se non disponibile.
        Le colonne di base sono normalizzate (alias risolti).
        Sono presenti SOLO righe con Date e FTR non-null (partite giocate).
    """
    url = build_csv_url(league_id, season_year)
    info = get_league_info(league_id)
    logger.info("Scarico CSV %s stagione %d/%d da: %s",
                info["name"], season_year, season_year + 1, url)

    try:
        df = pd.read_csv(url, on_bad_lines="skip")
    except HTTPError as e:
        logger.warning("HTTP %s — CSV non disponibile per %s %d/%d",
                       e.code, info["name"], season_year, season_year + 1)
        return None
    except URLError as e:
        logger.warning("URLError scaricando %s: %s", url, e)
        return None
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(url, encoding="latin1", on_bad_lines="skip")
        except Exception as e:
            logger.error("Errore decodifica CSV %s: %s", url, e)
            return None
    except Exception as e:
        logger.error("Errore generico scaricando %s: %s", url, e)
        return None

    if df is None or df.empty:
        logger.warning("CSV vuoto per %s %d/%d", info["name"], season_year, season_year + 1)
        return None

    # Rimuovi colonne completamente vuote (comuni nei CSV football-data)
    df = df.dropna(axis=1, how="all")

    # Risolvi alias colonne (colonna "Home" → "HomeTeam", ecc.)
    df = df.rename(columns=COLUMN_ALIASES)

    # Verifica colonne obbligatorie
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        logger.error("CSV %s %d/%d manca delle colonne obbligatorie: %s",
                     info["name"], season_year, season_year + 1, missing)
        return None

    # Aggiungi colonna Season
    df["Season"] = season_year

    # Rimuovi righe senza data o senza risultato (partite non giocate/future)
    df = df.dropna(subset=["Date", "FTR"])
    df = df[df["FTR"].isin(["H", "D", "A"])]

    # Normalizza colonne numeriche gol
    df["FTHG"] = pd.to_numeric(df["FTHG"], errors="coerce")
    df["FTAG"] = pd.to_numeric(df["FTAG"], errors="coerce")
    df = df.dropna(subset=["FTHG", "FTAG"])
    df["FTHG"] = df["FTHG"].astype(int)
    df["FTAG"] = df["FTAG"].astype(int)

    # Normalizza Date in formato YYYY-MM-DD
    df["date_parsed"] = pd.to_datetime(
        df["Date"], dayfirst=True, format="mixed", errors="coerce"
    )
    invalid_dates = df["date_parsed"].isna().sum()
    if invalid_dates > 0:
        logger.warning("%d righe con data non parsabile nel CSV %s %d/%d — rimosse",
                       invalid_dates, info["name"], season_year, season_year + 1)
    df = df.dropna(subset=["date_parsed"])
    df["date_iso"] = df["date_parsed"].dt.strftime("%Y-%m-%d")

    logger.info("CSV %s %d/%d: %d partite scaricate, %d colonne totali",
                info["name"], season_year, season_year + 1,
                len(df), len(df.columns))

    return df.reset_index(drop=True)
