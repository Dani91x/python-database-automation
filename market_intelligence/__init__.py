"""
market_intelligence — Analisi edge su quote, ML e xG

Uso rapido:
    from market_intelligence.edge_scorer import EdgeScorer
    scorer = EdgeScorer()
    result = scorer.score(fixture_id=1234567)
    scorer.print_scorecard(result)

Fasi di setup (eseguire una volta, poi rieseguire dopo aggiornamenti DB):
    python -m market_intelligence.pipeline --all
"""
from market_intelligence.edge_scorer import EdgeScorer, score_fixture_from_row
from market_intelligence.audit import run_audit
from market_intelligence.calibration import run_calibration
from market_intelligence.signals import run_signals

__all__ = [
    "EdgeScorer",
    "score_fixture_from_row",
    "run_audit",
    "run_calibration",
    "run_signals",
]
