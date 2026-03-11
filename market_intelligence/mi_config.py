"""
mi_config.py — Market Intelligence configuration
Tutti i parametri tunable in un posto solo. Non contiene logica.
"""
from pathlib import Path

# -- Paths ------------------------------------------------------------------
ROOT         = Path(__file__).parent
CACHE_DIR    = ROOT / "cache"
REGISTRY_FILE       = CACHE_DIR / "league_registry.json"
CALIBRATION_FILE    = CACHE_DIR / "calibration_tables.json"
SIGNAL_WEIGHTS_FILE = CACHE_DIR / "signal_weights.json"

# -- League qualification ----------------------------------------------------
# NOTA: Soglie basse perche il DB e ancora in popolamento.
# Aumentare progressivamente man mano che crescono i dati storici.
# Target finale: MIN_MATCHES_CALIBRATION=200, MIN_BRACKET_SAMPLES=30
MIN_MATCHES_CALIBRATION = 10   # min partite con odds+risultato per qualificarsi
MIN_BRACKET_SAMPLES     = 5    # min campioni per fascia per fidarsi della calibrazione
MIN_MATCHES_SIGNAL      = 10   # min partite per validare un segnale

# -- Odds brackets (half-open: [low, high)) ---------------------------------
# Piu fine nella zona 1.20-2.80 dove c'e la maggior densita di scommesse
ODDS_BRACKETS = [
    (1.01, 1.30),
    (1.30, 1.55),
    (1.55, 1.80),
    (1.80, 2.20),
    (2.20, 2.80),
    (2.80, 3.80),
    (3.80, 6.00),
    (6.00, 15.00),
]

# -- Mercati da analizzare ---------------------------------------------------
# Ogni mercato: nome nel bookie (API-Football) -> label valore -> chiave ML -> result_fn
MARKETS = {
    "1x2_H":     {"bet_name": "Match Winner",     "value": "Home",      "ml_market": "1x2",      "ml_key": "H",     "result_fn": "home_win"},
    "1x2_D":     {"bet_name": "Match Winner",     "value": "Draw",      "ml_market": "1x2",      "ml_key": "D",     "result_fn": "draw"},
    "1x2_A":     {"bet_name": "Match Winner",     "value": "Away",      "ml_market": "1x2",      "ml_key": "A",     "result_fn": "away_win"},
    "over_2_5":  {"bet_name": "Goals Over/Under", "value": "Over 2.5",  "ml_market": "over_2_5", "ml_key": "True",  "result_fn": "over25"},
    "under_2_5": {"bet_name": "Goals Over/Under", "value": "Under 2.5", "ml_market": "over_2_5", "ml_key": "False", "result_fn": "under25"},
    "btts_yes":  {"bet_name": "Both Teams Score", "value": "Yes",       "ml_market": "btts",     "ml_key": "True",  "result_fn": "btts_yes"},
    "btts_no":   {"bet_name": "Both Teams Score", "value": "No",        "ml_market": "btts",     "ml_key": "False", "result_fn": "btts_no"},
}

# -- Signal weights (default, overridden da signal_weights.json se trusted) -
DEFAULT_WEIGHT_ML_DIV  = 0.55
DEFAULT_WEIGHT_XG      = 0.45

# ML divergence signal
ML_DIV_MIN_EDGE    = 0.03   # divergenza minima |ml - implied| per registrare segnale
ML_DIV_MIN_SAMPLE  = 40     # campioni minimi per fidarsi del segnale ML

# xG signal
XG_MIN_COVERAGE    = 0.30   # copertura minima xG sulle partite qualificate
XG_MIN_SAMPLE      = 30     # campioni minimi per fidarsi del segnale xG

# -- Edge scorer -------------------------------------------------------------
MIN_COMPOSITE_EDGE  = 0.02  # sotto questa soglia -> edge = 0.0 (nessun segnale)
CACHE_MAX_AGE_HOURS = 48    # warn se cache piu vecchia di N ore
