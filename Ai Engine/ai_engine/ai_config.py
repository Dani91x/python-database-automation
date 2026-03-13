from __future__ import annotations

from datetime import timezone


TIMEZONE = timezone.utc

# Use multiple windows for form features.
FORM_WINDOWS = [5, 10, 15]

# Odds markets of interest
ODDS_LINES = [1.5, 2.5, 3.5]

ODDS_LABELS_1X2 = {
    "home": {"home", "1", "1x2_1"},
    "draw": {"draw", "x", "1x2_x"},
    "away": {"away", "2", "1x2_2"},
}

ODDS_LABELS_BTTS = {
    "yes": {"yes", "btts_yes", "both teams to score - yes"},
    "no": {"no", "btts_no", "both teams to score - no"},
}

# Report location (local only)
REPORT_DIR = "Ai Engine/reports"

