"""Test del calibratore (Betfair/safe_strategy/calibration.py): puro."""
from __future__ import annotations

import json
import random

import pytest

from Betfair.safe_strategy import calibration as C
from Betfair.safe_strategy.calibration import CalSample, Calibrator


def _samples(n: int, *, family: str = "ou_line", minute: int = 70, seed: int = 1,
             bias: float = 0.15, event_prefix: str = "e") -> list:
    """Modello OTTIMISTA: dichiara p, la realta' e' p - bias (clampata)."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        p = rng.uniform(0.05, 0.98)
        real = max(0.0, min(1.0, p - bias))
        out.append(CalSample(family, minute, p, int(rng.random() < real), f"{event_prefix}{i % 8}"))
    return out


# ------------------------------------------------------------------ utilita'
def test_bucket_of_e_family_of_market():
    assert C.bucket_of(0) == "0-15" and C.bucket_of(14) == "0-15"
    assert C.bucket_of(15) == "15-30" and C.bucket_of(44) == "30-45"
    assert C.bucket_of(45) == "45-60" and C.bucket_of(89) == "75-90"
    assert C.bucket_of(90) == "75-90" and C.bucket_of(97) == "75-90"   # recupero
    assert C.bucket_of(None) == "0-15" and C.bucket_of(-3) == "0-15"
    assert C.family_of_market("MATCH_ODDS") == "mo"
    assert C.family_of_market("OVER_UNDER_75") == "ou_line"
    assert C.family_of_market("OVER_UNDER") == "ou_line"      # spec del modello
    assert C.family_of_market("BOTH_TEAMS_TO_SCORE") == "btts"
    assert C.family_of_market("HALF_TIME") == "ht"
    assert C.family_of_market("CORRECT_SCORE", "cs_any_other_home") == "cs_any_other"
    assert C.family_of_market("CORRECT_SCORE", "cs_1_1") == "cs_cell"
    assert C.family_of_market("HALF_TIME_SCORE", "hts_0_0") == "hts_cell"
    assert C.family_of_market("DOUBLE_CHANCE") is None


def test_pav_isotonic_pesato():
    ys = C._pav([0.1, 0.3, 0.5, 0.7], [0.2, 0.5, 0.4, 0.9], [1, 1, 1, 1])
    assert ys == pytest.approx([0.2, 0.45, 0.45, 0.9])
    assert all(a <= b + 1e-12 for a, b in zip(ys, ys[1:]))


# ------------------------------------------------------------------- fit
def test_small_n_passthrough():
    data = C.fit_calibration(_samples(20), min_n=50)
    cal = Calibrator.from_dict(data)
    assert cal.empty
    for p in (0.1, 0.5, 0.93):
        assert cal.apply(p, "ou_line", 70) == p
    assert cal.lookup("ou_line", 70) == (False, 20)


def test_fit_corregge_un_modello_ottimista_e_resta_monotono():
    samples = _samples(3000, bias=0.15)
    data = C.fit_calibration(samples, min_n=50, shrink_n=50)
    cal = Calibrator.from_dict(data)
    assert not cal.empty
    applied, n = cal.lookup("ou_line", 70)
    assert applied and n == 3000
    # il modello dichiarava troppo: la calibrata scende
    assert cal.apply(0.9, "ou_line", 70) < 0.9
    assert cal.apply(0.5, "ou_line", 70) < 0.5
    # monotona su una griglia fitta
    grid = [i / 200 for i in range(1, 200)]
    ys = [cal.apply(p, "ou_line", 70) for p in grid]
    assert all(a <= b + 1e-12 for a, b in zip(ys, ys[1:]))
    # mai oltre (0,1); certezze intatte
    assert all(0.0 < y < 1.0 for y in ys)
    assert cal.apply(0.0, "ou_line", 70) == 0.0 and cal.apply(1.0, "ou_line", 70) == 1.0
    # famiglia/fascia senza tabella: identita'
    assert cal.apply(0.9, "mo", 70) == 0.9
    assert cal.apply(0.9, "ou_line", 10) == 0.9
    meta = data["meta"]
    assert meta["brier_after"] < meta["brier_before"]
    assert meta["ece_after"] < meta["ece_before"]
    assert meta["brier_cv_after"] < meta["brier_cv_before"]   # 2-fold per evento
    assert meta["n_events"] == 8 and meta["n_samples"] == 3000


def test_shrinkage_verso_identita_con_pochi_campioni_per_bin():
    # 60 campioni (tabella applicata) tutti in bin diversi e ~7 per bin:
    # la correzione deve restare vicina all'identita' (peso identita' = 50)
    rng = random.Random(3)
    samples = [CalSample("mo", 20, p := rng.uniform(0.05, 0.95), int(rng.random() < 0.2), "e")
               for _ in range(60)]
    cal = Calibrator.from_dict(C.fit_calibration(samples, min_n=50, shrink_n=50))
    assert cal.lookup("mo", 20)[0]
    for p in (0.3, 0.6, 0.9):
        assert abs(cal.apply(p, "mo", 20) - p) < 0.25
    # con shrinkage enorme e' praticamente identita'
    cal2 = Calibrator.from_dict(C.fit_calibration(samples, min_n=50, shrink_n=1e9))
    for p in (0.3, 0.6, 0.9):
        assert abs(cal2.apply(p, "mo", 20) - p) < 1e-3


def test_reliability_table_e_format():
    rows = C.reliability_table(_samples(500))
    assert rows and all(r["family"] == "ou_line" and r["bucket"] == "60-75" for r in rows)
    assert sum(r["n"] for r in rows) == 500
    txt = C.format_reliability(rows)
    assert "famiglia" in txt and txt.isascii()


# ------------------------------------------------------------- load / save
def test_save_load_roundtrip_e_info(tmp_path):
    data = C.fit_calibration(_samples(800))
    path = tmp_path / "cal.json"
    Calibrator.from_dict(data).save(str(path))
    cal = Calibrator.load(str(path))
    assert cal.path == str(path)
    assert cal.apply(0.8, "ou_line", 70) == pytest.approx(
        Calibrator.from_dict(data).apply(0.8, "ou_line", 70))
    info = cal.info()
    assert info["loaded"] and info["tables_applied"] == 1 and info["n_samples"] == 800
    assert "ou_line|60-75" in info["applied"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 1 and "tables" in raw and "meta" in raw


def test_load_file_assente_o_rotto_e_identita(tmp_path):
    cal = Calibrator.load(str(tmp_path / "manca.json"))
    assert cal.empty and cal.apply(0.7, "mo", 10) == 0.7
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert Calibrator.load(str(bad)).empty


def test_apply_input_strani():
    cal = Calibrator.from_dict(C.fit_calibration(_samples(800)))
    assert cal.apply(float("nan"), "ou_line", 70) != cal.apply(0.5, "ou_line", 70)
    assert cal.apply("x", "ou_line", 70) == "x"
    assert cal.apply(0.5, None, 70) == 0.5


# Soglie storiche per i test di meccanica (in produzione: lay spenti, back >=95%, edge 3%).
import pytest as _pytest
from Betfair.safe_strategy import opportunity as _opp_mod


@_pytest.fixture(autouse=True)
def _legacy_thresholds(monkeypatch):
    for k, v in {"min_edge": 0.02, "min_prob_back": 0.85, "max_prob_lay": 0.15}.items():
        monkeypatch.setitem(_opp_mod.DEFAULT_OPP_PARAMS, k, v)
