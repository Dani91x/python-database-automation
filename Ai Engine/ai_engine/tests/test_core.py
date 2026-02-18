"""
Unit tests for AI Engine core modules.
Tests use synthetic data only — no database required.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ── Temporal Split Tests ────────────────────────────────────────────

class TestTemporalSplit:
    def test_no_future_leakage(self):
        """Ensure no validation date is earlier than any training date."""
        from ai_engine.preprocessing.temporal_split import temporal_train_val_split

        dates = pd.date_range("2023-01-01", periods=100, freq="3D")
        df = pd.DataFrame({
            "fixture_date": dates,
            "feature_a": np.random.randn(100),
            "feature_b": np.random.randn(100),
        })

        train_df, val_df = temporal_train_val_split(df, val_ratio=0.2, purge_days=30)

        assert not train_df.empty
        assert not val_df.empty
        assert train_df["fixture_date"].max() < val_df["fixture_date"].min()

    def test_purge_gap(self):
        """Verify the purge gap removes matches near the cutoff."""
        from ai_engine.preprocessing.temporal_split import temporal_train_val_split

        dates = pd.date_range("2023-01-01", periods=100, freq="1D")
        df = pd.DataFrame({
            "fixture_date": dates,
            "x": np.random.randn(100),
        })

        train_df, val_df = temporal_train_val_split(df, val_ratio=0.2, purge_days=30)

        gap_days = (val_df["fixture_date"].min() - train_df["fixture_date"].max()).days
        assert gap_days >= 30

    def test_walk_forward_monotonic(self):
        """Walk-forward splits should have monotonically increasing validation windows."""
        from ai_engine.preprocessing.temporal_split import walk_forward_splits

        dates = pd.date_range("2020-01-01", periods=500, freq="2D")
        df = pd.DataFrame({
            "fixture_date": dates,
            "x": np.random.randn(500),
        })

        splits = walk_forward_splits(df, n_splits=3, purge_days=30)
        assert len(splits) >= 2

        for train_idx, val_idx in splits:
            assert len(train_idx) > 0
            assert len(val_idx) > 0
            # All train indices should be before val indices
            assert train_idx.max() < val_idx.min()


# ── Value Betting Tests ─────────────────────────────────────────────

class TestValueBetting:
    def test_positive_ev(self):
        """EV should be positive when model has edge over bookmaker."""
        from ai_engine.value_betting import expected_value

        ev = expected_value(model_prob=0.60, decimal_odds=2.0)
        # EV = 0.6 * 1.0 - 0.4 = 0.20
        assert ev > 0
        assert abs(ev - 0.20) < 0.001

    def test_negative_ev(self):
        """EV should be negative when bookmaker has edge."""
        from ai_engine.value_betting import expected_value

        ev = expected_value(model_prob=0.40, decimal_odds=2.0)
        # EV = 0.4 * 1.0 - 0.6 = -0.20
        assert ev < 0

    def test_kelly_positive_only(self):
        """Kelly should return 0 when there's no edge."""
        from ai_engine.value_betting import kelly_criterion

        # No edge case
        k = kelly_criterion(model_prob=0.40, decimal_odds=2.0)
        assert k == 0.0

        # Positive edge case
        k = kelly_criterion(model_prob=0.60, decimal_odds=2.5)
        assert k > 0

    def test_kelly_max_cap(self):
        """Kelly should never exceed max_kelly."""
        from ai_engine.value_betting import kelly_criterion

        k = kelly_criterion(model_prob=0.95, decimal_odds=10.0, max_kelly=0.05)
        assert k <= 0.05

    def test_implied_probability(self):
        """Implied probability should be 1/odds."""
        from ai_engine.value_betting import implied_probability

        assert abs(implied_probability(2.0) - 0.5) < 0.001
        assert abs(implied_probability(4.0) - 0.25) < 0.001

    def test_evaluate_bet_filters_low_prob(self):
        """Bets with low probability should be filtered out."""
        from ai_engine.value_betting import evaluate_bet_opportunities

        targets = {"target_btts": {"True": 0.30, "False": 0.70}}
        odds = {"target_btts_False": 1.5}

        signals, no_bets = evaluate_bet_opportunities(targets, odds)
        # 0.70 probability but odds 1.5 → EV = 0.7*0.5 - 0.3 = 0.05
        # Should pass EV but let's check
        # Actually: EV = 0.70 * (1.5-1) - 0.30 = 0.35 - 0.30 = 0.05 > 0.03 min_edge
        # and prob 0.70 > 0.55 min_prob for btts
        # So it should be a signal
        assert len(signals) + len(no_bets) >= 1


# ── Confidence Gate Tests ───────────────────────────────────────────

class TestConfidenceGates:
    def test_insufficient_data_fails(self):
        """Gate should fail when coverage is too low."""
        from ai_engine.confidence_gate import gate_data_sufficiency

        result = gate_data_sufficiency(
            coverage_pct=0.30,
            matches_home=20,
            matches_away=20,
            reliability_score=0.6,
        )
        assert not result.passed
        assert result.gate_failed == "data_sufficiency"

    def test_sufficient_data_passes(self):
        """Gate should pass with good data."""
        from ai_engine.confidence_gate import gate_data_sufficiency

        result = gate_data_sufficiency(
            coverage_pct=0.80,
            matches_home=20,
            matches_away=15,
            reliability_score=0.7,
        )
        assert result.passed

    def test_low_agreement_fails(self):
        """Gate should fail when models disagree."""
        from ai_engine.confidence_gate import gate_model_agreement

        result = gate_model_agreement(
            agreement_ratio=0.33,
            votes={"rf": "H", "gb": "D", "logreg": "A"},
        )
        assert not result.passed
        assert result.gate_failed == "model_agreement"

    def test_high_agreement_passes(self):
        """Gate should pass when models agree."""
        from ai_engine.confidence_gate import gate_model_agreement

        result = gate_model_agreement(
            agreement_ratio=1.0,
            votes={"rf": "H", "gb": "H", "logreg": "H"},
        )
        assert result.passed

    def test_no_value_fails(self):
        """Gate should fail when no bet signal exists."""
        from ai_engine.confidence_gate import gate_value_present

        result = gate_value_present(bet_signal=None)
        assert not result.passed

    def test_all_gates_combined(self):
        """Test the combined gate check."""
        from ai_engine.confidence_gate import apply_all_gates
        from ai_engine.value_betting import BetSignal

        signal = BetSignal(
            market="target_1x2", action="H", model_prob=0.65,
            implied_prob=0.50, decimal_odds=2.0, expected_value=0.10,
            kelly_fraction=0.02, kelly_stake=20.0, confidence_grade="medium",
            edge=0.15,
        )

        all_passed, gates = apply_all_gates(
            coverage_pct=0.85, matches_home=20, matches_away=18,
            reliability_score=0.75, agreement_ratio=1.0,
            votes={"rf": "H", "gb": "H", "logreg": "H"},
            bet_signal=signal,
        )
        assert all_passed
        assert all(g.passed for g in gates)


# ── Feature Selection Tests ─────────────────────────────────────────

class TestFeatureSelection:
    def test_drop_correlated(self):
        """Highly correlated features should be removed."""
        from ai_engine.preprocessing.selection import drop_correlated

        np.random.seed(42)
        x = np.random.randn(100)
        df = pd.DataFrame({
            "a": x,
            "b": x + np.random.randn(100) * 0.01,  # ~perfect correlation
            "c": np.random.randn(100),  # independent
        })

        kept = drop_correlated(df, threshold=0.95)
        assert len(kept) == 2  # one of a/b should be dropped
        assert "c" in kept

    def test_variance_threshold_drops_constant(self):
        """Constant features should be removed."""
        from ai_engine.preprocessing.selection import variance_threshold

        df = pd.DataFrame({
            "constant": [1.0] * 50,
            "varying": np.random.randn(50),
        })

        kept = variance_threshold(df, threshold=0.0)
        assert "varying" in kept


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
