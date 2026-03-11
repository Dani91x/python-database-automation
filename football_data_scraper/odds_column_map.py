"""
Mapping esaustivo: colonna CSV football-data → (bookmaker_name, market_name, label, market_key).

market_key è il campo numerico usato da API-Football per lo stesso mercato.
Questo permette coerenza nella tabella match_odds tra le due sorgenti.

NOTA: non tutte le colonne sono presenti in ogni stagione/lega.
Il downloader scarica il CSV grezzo e poi questo mapping viene applicato
solo sulle colonne effettivamente presenti.
"""
from typing import Dict, Tuple

# (bookmaker_name, market_name, label, market_key)
OddsColDef = Tuple[str, str, str, str]

# ─────────────────────────────────────────────────────────────────────────────
# MATCH WINNER (1X2) — quote di apertura
# ─────────────────────────────────────────────────────────────────────────────
COLS_1X2_OPENING: Dict[str, OddsColDef] = {
    "B365H": ("Bet365",       "Match Winner", "Home", "1"),
    "B365D": ("Bet365",       "Match Winner", "Draw", "1"),
    "B365A": ("Bet365",       "Match Winner", "Away", "1"),
    "BWH":   ("BW",           "Match Winner", "Home", "1"),
    "BWD":   ("BW",           "Match Winner", "Draw", "1"),
    "BWA":   ("BW",           "Match Winner", "Away", "1"),
    "GBH":   ("Gamebookers",  "Match Winner", "Home", "1"),
    "GBD":   ("Gamebookers",  "Match Winner", "Draw", "1"),
    "GBA":   ("Gamebookers",  "Match Winner", "Away", "1"),
    "IWH":   ("IW",           "Match Winner", "Home", "1"),
    "IWD":   ("IW",           "Match Winner", "Draw", "1"),
    "IWA":   ("IW",           "Match Winner", "Away", "1"),
    "LBH":   ("Ladbrokes",    "Match Winner", "Home", "1"),
    "LBD":   ("Ladbrokes",    "Match Winner", "Draw", "1"),
    "LBA":   ("Ladbrokes",    "Match Winner", "Away", "1"),
    "PSH":   ("Pinnacle",     "Match Winner", "Home", "1"),
    "PSD":   ("Pinnacle",     "Match Winner", "Draw", "1"),
    "PSA":   ("Pinnacle",     "Match Winner", "Away", "1"),
    # Alias colonna Pinnacle usato in alcuni CSV
    "PH":    ("Pinnacle",     "Match Winner", "Home", "1"),
    "PD":    ("Pinnacle",     "Match Winner", "Draw", "1"),
    "PA":    ("Pinnacle",     "Match Winner", "Away", "1"),
    "SBH":   ("Stan James",   "Match Winner", "Home", "1"),
    "SBD":   ("Stan James",   "Match Winner", "Draw", "1"),
    "SBA":   ("Stan James",   "Match Winner", "Away", "1"),
    "SJH":   ("Stan James",   "Match Winner", "Home", "1"),
    "SJD":   ("Stan James",   "Match Winner", "Draw", "1"),
    "SJA":   ("Stan James",   "Match Winner", "Away", "1"),
    "SOH":   ("Sporting Odds","Match Winner", "Home", "1"),
    "SOD":   ("Sporting Odds","Match Winner", "Draw", "1"),
    "SOA":   ("Sporting Odds","Match Winner", "Away", "1"),
    "SYH":   ("Stanleybet",   "Match Winner", "Home", "1"),
    "SYD":   ("Stanleybet",   "Match Winner", "Draw", "1"),
    "SYA":   ("Stanleybet",   "Match Winner", "Away", "1"),
    "VCH":   ("VC Bet",       "Match Winner", "Home", "1"),
    "VCD":   ("VC Bet",       "Match Winner", "Draw", "1"),
    "VCA":   ("VC Bet",       "Match Winner", "Away", "1"),
    "WHH":   ("William Hill", "Match Winner", "Home", "1"),
    "WHD":   ("William Hill", "Match Winner", "Draw", "1"),
    "WHA":   ("William Hill", "Match Winner", "Away", "1"),
    "MaxH":  ("Maximum",      "Match Winner", "Home", "1"),
    "MaxD":  ("Maximum",      "Match Winner", "Draw", "1"),
    "MaxA":  ("Maximum",      "Match Winner", "Away", "1"),
    "AvgH":  ("Average",      "Match Winner", "Home", "1"),
    "AvgD":  ("Average",      "Match Winner", "Draw", "1"),
    "AvgA":  ("Average",      "Match Winner", "Away", "1"),
}

# ─────────────────────────────────────────────────────────────────────────────
# MATCH WINNER (1X2) — quote di chiusura (closing odds)
# Stesso market_name, bookmaker_name suffissato con "_closing"
# ─────────────────────────────────────────────────────────────────────────────
COLS_1X2_CLOSING: Dict[str, OddsColDef] = {
    "B365CH": ("Bet365_closing",       "Match Winner", "Home", "1"),
    "B365CD": ("Bet365_closing",       "Match Winner", "Draw", "1"),
    "B365CA": ("Bet365_closing",       "Match Winner", "Away", "1"),
    "BWCH":   ("BW_closing",           "Match Winner", "Home", "1"),
    "BWCD":   ("BW_closing",           "Match Winner", "Draw", "1"),
    "BWCA":   ("BW_closing",           "Match Winner", "Away", "1"),
    "GBCH":   ("Gamebookers_closing",  "Match Winner", "Home", "1"),
    "GBCD":   ("Gamebookers_closing",  "Match Winner", "Draw", "1"),
    "GBCA":   ("Gamebookers_closing",  "Match Winner", "Away", "1"),
    "IWCH":   ("IW_closing",           "Match Winner", "Home", "1"),
    "IWCD":   ("IW_closing",           "Match Winner", "Draw", "1"),
    "IWCA":   ("IW_closing",           "Match Winner", "Away", "1"),
    "LBCH":   ("Ladbrokes_closing",    "Match Winner", "Home", "1"),
    "LBCD":   ("Ladbrokes_closing",    "Match Winner", "Draw", "1"),
    "LBCA":   ("Ladbrokes_closing",    "Match Winner", "Away", "1"),
    "PSCH":   ("Pinnacle_closing",     "Match Winner", "Home", "1"),
    "PSCD":   ("Pinnacle_closing",     "Match Winner", "Draw", "1"),
    "PSCA":   ("Pinnacle_closing",     "Match Winner", "Away", "1"),
    "WHCH":   ("William Hill_closing", "Match Winner", "Home", "1"),
    "WHCD":   ("William Hill_closing", "Match Winner", "Draw", "1"),
    "WHCA":   ("William Hill_closing", "Match Winner", "Away", "1"),
    "VCCH":   ("VC Bet_closing",       "Match Winner", "Home", "1"),
    "VCCD":   ("VC Bet_closing",       "Match Winner", "Draw", "1"),
    "VCCA":   ("VC Bet_closing",       "Match Winner", "Away", "1"),
    "MaxCH":  ("Maximum_closing",      "Match Winner", "Home", "1"),
    "MaxCD":  ("Maximum_closing",      "Match Winner", "Draw", "1"),
    "MaxCA":  ("Maximum_closing",      "Match Winner", "Away", "1"),
    "AvgCH":  ("Average_closing",      "Match Winner", "Home", "1"),
    "AvgCD":  ("Average_closing",      "Match Winner", "Draw", "1"),
    "AvgCA":  ("Average_closing",      "Match Winner", "Away", "1"),
}

# ─────────────────────────────────────────────────────────────────────────────
# GOALS OVER/UNDER 2.5 — apertura
# ─────────────────────────────────────────────────────────────────────────────
COLS_OU25_OPENING: Dict[str, OddsColDef] = {
    "B365>2.5": ("Bet365",   "Goals Over/Under", "Over 2.5",  "5"),
    "B365<2.5": ("Bet365",   "Goals Over/Under", "Under 2.5", "5"),
    "BW>2.5":   ("BW",       "Goals Over/Under", "Over 2.5",  "5"),
    "BW<2.5":   ("BW",       "Goals Over/Under", "Under 2.5", "5"),
    "GB>2.5":   ("Gamebookers","Goals Over/Under","Over 2.5", "5"),
    "GB<2.5":   ("Gamebookers","Goals Over/Under","Under 2.5","5"),
    "P>2.5":    ("Pinnacle", "Goals Over/Under", "Over 2.5",  "5"),
    "P<2.5":    ("Pinnacle", "Goals Over/Under", "Under 2.5", "5"),
    "Max>2.5":  ("Maximum",  "Goals Over/Under", "Over 2.5",  "5"),
    "Max<2.5":  ("Maximum",  "Goals Over/Under", "Under 2.5", "5"),
    "Avg>2.5":  ("Average",  "Goals Over/Under", "Over 2.5",  "5"),
    "Avg<2.5":  ("Average",  "Goals Over/Under", "Under 2.5", "5"),
}

# ─────────────────────────────────────────────────────────────────────────────
# GOALS OVER/UNDER 2.5 — chiusura
# ─────────────────────────────────────────────────────────────────────────────
COLS_OU25_CLOSING: Dict[str, OddsColDef] = {
    "B365C>2.5": ("Bet365_closing",   "Goals Over/Under", "Over 2.5",  "5"),
    "B365C<2.5": ("Bet365_closing",   "Goals Over/Under", "Under 2.5", "5"),
    "PC>2.5":    ("Pinnacle_closing", "Goals Over/Under", "Over 2.5",  "5"),
    "PC<2.5":    ("Pinnacle_closing", "Goals Over/Under", "Under 2.5", "5"),
    "MaxC>2.5":  ("Maximum_closing",  "Goals Over/Under", "Over 2.5",  "5"),
    "MaxC<2.5":  ("Maximum_closing",  "Goals Over/Under", "Under 2.5", "5"),
    "AvgC>2.5":  ("Average_closing",  "Goals Over/Under", "Over 2.5",  "5"),
    "AvgC<2.5":  ("Average_closing",  "Goals Over/Under", "Under 2.5", "5"),
}

# ─────────────────────────────────────────────────────────────────────────────
# BOTH TEAMS TO SCORE (BTTS)
# ─────────────────────────────────────────────────────────────────────────────
COLS_BTTS: Dict[str, OddsColDef] = {
    "B365BH": ("Bet365",   "Both Teams Score", "Yes", "8"),
    "B365BA": ("Bet365",   "Both Teams Score", "No",  "8"),
    "MaxBH":  ("Maximum",  "Both Teams Score", "Yes", "8"),
    "MaxBA":  ("Maximum",  "Both Teams Score", "No",  "8"),
    "AvgBH":  ("Average",  "Both Teams Score", "Yes", "8"),
    "AvgBA":  ("Average",  "Both Teams Score", "No",  "8"),
}

# ─────────────────────────────────────────────────────────────────────────────
# MERGE: tutte le colonne odds conosciute
# ─────────────────────────────────────────────────────────────────────────────
ALL_ODDS_COLS: Dict[str, OddsColDef] = {
    **COLS_1X2_OPENING,
    **COLS_1X2_CLOSING,
    **COLS_OU25_OPENING,
    **COLS_OU25_CLOSING,
    **COLS_BTTS,
}

# ─────────────────────────────────────────────────────────────────────────────
# STATISTICHE (per match_team_stats)
# Mapping: colonna CSV → (side: "home"|"away", stat_type API-Football)
# ─────────────────────────────────────────────────────────────────────────────
STATS_COLS: Dict[str, Tuple[str, str]] = {
    "HST":  ("home", "Shots on Goal"),      # shots on target home
    "AST":  ("away", "Shots on Goal"),      # shots on target away
    "HS":   ("home", "Total Shots"),
    "AS":   ("away", "Total Shots"),
    "HC":   ("home", "Corner Kicks"),
    "AC":   ("away", "Corner Kicks"),
    "HF":   ("home", "Fouls"),
    "AF":   ("away", "Fouls"),
    "HY":   ("home", "Yellow Cards"),
    "AY":   ("away", "Yellow Cards"),
    "HR":   ("home", "Red Cards"),
    "AR":   ("away", "Red Cards"),
}
