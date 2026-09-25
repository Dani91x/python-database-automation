"""P(0-0) negativa nel Tactical Engine (25/09/2026): dominio di rho di Dixon-Coles.

Reperto: 17 righe di fixture_predictions con markets.under_0_5 < 0 (P(0-0) < 0,
over_0_5 > 1). Causa: nel fit la tau era vincolata > 0 solo sulle partite OSSERVATE
0-0/0-1/1-0/1-1 (model.py, maschere m00..m11 + `tau <= 1e-9`); nessun vincolo sulle
coppie che il modello PREVEDE. Con rho > 0 e una coppia a lambda alte mai finita 0-0
nello storico, tau(0,0) = 1 - lh*la*rho < 0 in previsione.

Dixon & Coles (1997), sez. 4.1: tau e' una correzione valida solo se
    max(-1/lambda, -1/mu) <= rho <= min(1/(lambda*mu), 1)
per ogni partita a cui il modello si applica. Il fit ora rispetta il dominio su TUTTE
le coppie ordinate della lega (secondo stadio vincolato, solo se il primo lo viola);
predict proietta rho nel dominio della coppia (identita' dopo il fit vincolato).

I dati sono SINTETICI: il DB vero non e' accessibile ai test.
"""
from __future__ import annotations

import dataclasses
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tactical_engine import model as M  # noqa: E402
from tactical_engine.dixon_coles import (  # noqa: E402
    MatchScoreline, dc_tau, markets_from_matrix, rho_bounds, score_matrix,
)
from tactical_engine.model import DixonColesModel  # noqa: E402

RIDGE = 0.08  # = serving.RIDGE (non importato: serving importa db_client)


def _lega_poche_x00(seed: int, n: int = 12, gpp: int = 4, spread: float = 0.55,
                    const: float = 0.25, gamma: float = 0.25, drop: float = 0.6):
    """Lega con MENO 0-0 e 1-1 di quanto dica il Poisson (rho stimato > 0) e forze
    disperse: esistono coppie a lambda alte che non finiscono mai 0-0."""
    rng = np.random.default_rng(seed)
    att = rng.normal(0, spread, n); att -= att.mean()
    de = rng.normal(0, spread, n); de -= de.mean()
    ms = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            lh = math.exp(const + att[i] - de[j] + gamma)
            la = math.exp(const + att[j] - de[i])
            for _ in range(gpp):
                while True:
                    x, y = int(rng.poisson(lh)), int(rng.poisson(la))
                    if (x, y) in ((0, 0), (1, 1)) and rng.random() < drop:
                        continue
                    break
                ms.append(MatchScoreline(i + 1, j + 1, x, y))
    return ms


def _lega_normale(seed: int, n: int = 12, gpp: int = 4, rho: float = -0.05):
    """Lega realistica: lambda fra ~0,8 e ~2,5, rho negativo tipico (DC 1997: -0,13)."""
    rng = np.random.default_rng(seed)
    att = rng.normal(0, 0.22, n); att -= att.mean()
    de = rng.normal(0, 0.22, n); de -= de.mean()
    const, gamma = 0.20, 0.25
    ms = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            lh = math.exp(const + att[i] - de[j] + gamma)
            la = math.exp(const + att[j] - de[i])
            p = score_matrix(lh, la, rho, 10).ravel()
            for _ in range(gpp):
                k = int(rng.choice(p.size, p=p))
                ms.append(MatchScoreline(i + 1, j + 1, k // 11, k % 11))
    return ms


def _tutte_le_coppie(m: DixonColesModel, neutral: bool):
    f = m.fit_
    for h in f.teams:
        for a in f.teams:
            if h != a:
                yield h, a, m.predict(h, a, neutral=neutral)


def _griglia_valida(p: dict) -> None:
    g = p["grid"]
    assert float(g.min()) >= 0.0, f"cella negativa {g.min()}"
    assert abs(float(g.sum()) - 1.0) <= 1e-9, f"somma griglia {g.sum()}"
    mk = p["markets"]
    assert 0.0 <= mk["under_0_5"] <= 1.0 and 0.0 <= mk["over_0_5"] <= 1.0, mk["under_0_5"]
    for k, v in mk.items():
        assert -1e-12 <= v <= 1.0 + 1e-12, (k, v)


# ------------------------------------------------------------- dominio di rho

def test_rho_bounds_formula_dixon_coles():
    lh, la = 2.5, 1.6
    lo, hi = rho_bounds(lh, la)
    assert lo == pytest.approx(-1.0 / 2.5) and hi == pytest.approx(1.0 / (2.5 * 1.6))
    # sul bordo le tau sono esattamente 0 (tau(0,0) in hi, tau(0,1) in lo)
    assert dc_tau(0, 0, lh, la, hi) == pytest.approx(0.0, abs=1e-12)
    assert dc_tau(0, 1, lh, la, lo) == pytest.approx(0.0, abs=1e-12)
    # con il margine tutte e quattro restano >= tau_min
    lo, hi = rho_bounds(lh, la, 1e-3)
    for r in (lo, hi):
        assert min(dc_tau(x, y, lh, la, r) for x in (0, 1) for y in (0, 1)) >= 1e-3 - 1e-12
    # lambda piccole: il vincolo 1 - rho > 0 domina
    assert rho_bounds(0.5, 0.5)[1] == pytest.approx(1.0)


def test_limiti_su_tutte_le_coppie_coincidono_con_la_forza_bruta():
    rng = np.random.default_rng(3)
    att = rng.normal(0, 0.5, 9); de = rng.normal(0, 0.5, 9); c, g = 0.3, 0.2
    lo, hi = M._rho_limits_all_pairs(att, de, c, g, tau_min=0.0)
    lo_b, hi_b = -M.RHO_BOX, M.RHO_BOX
    for i in range(9):
        for j in range(9):
            if i != j:
                l1, h1 = rho_bounds(math.exp(c + att[i] - de[j] + g), math.exp(c + att[j] - de[i]))
                lo_b, hi_b = max(lo_b, l1), min(hi_b, h1)
    assert lo == pytest.approx(lo_b, rel=1e-12) and hi == pytest.approx(hi_b, rel=1e-12)


# ------------------------------------------------------------- il reperto

@pytest.mark.parametrize("seed", [0, 2])
def test_nessuna_p00_negativa_su_nessuna_coppia_prevedibile(seed):
    """Lega che, col fit vincolato solo sulle celle osservate, dava under_0_5 < 0
    (MISURATO prima del fix: seed 0 -> -0.00097 su 6-3, seed 2 -> -0.00208 su 1-6)."""
    ms = _lega_poche_x00(seed)
    m = DixonColesModel(max_goals=10, half_life_days=0.0, ridge=RIDGE)
    f = m.fit(ms)
    # 1) nessuna griglia prevista non valida (col modello di prima: cella 0-0 < 0)
    for neutral in (False, True):
        for _, _, p in _tutte_le_coppie(m, neutral):
            _griglia_valida(p)
    # 2) il test sollecita davvero la condizione (catalogo 7 n. 29): il primo stadio
    #    violava il dominio e il secondo e' entrato
    assert getattr(f, "rho_constraint_active", False), "dataset che non espone il difetto"
    for neutral in (False, True):
        for h, a, p in _tutte_le_coppie(m, neutral):
            lh, la = p["lambda_home"], p["lambda_away"]
            lo, hi = rho_bounds(lh, la, M.TAU_MIN)
            # rho del FIT gia' nel dominio (a meno della virgola mobile): la
            # proiezione in predict non e' cio' che rende valida la griglia
            assert lo - 1e-12 <= f.rho <= hi + 1e-12, (h, a, f.rho, lo, hi)


def test_predict_garantisce_tau_positiva_anche_con_rho_fuori_dominio():
    """Difesa in profondita': FitResult costruito a mano con rho al bordo del box."""
    ms = _lega_poche_x00(0)
    m = DixonColesModel(max_goals=10, half_life_days=0.0, ridge=RIDGE)
    m.fit(ms)
    m.fit_ = dataclasses.replace(m.fit_, rho=M.RHO_BOX)
    proiettate = 0
    for _, _, p in _tutte_le_coppie(m, False):
        _griglia_valida(p)
        proiettate += p["rho_effective"] < M.RHO_BOX
    assert proiettate > 0


# ------------------------------------------------------------- partite normali

@pytest.mark.parametrize("seed", [11, 12, 13])
def test_partite_normali_invariate(seed, monkeypatch):
    """Lega realistica (lambda 0,8-2,5): rho gia' nel dominio -> stesso fit e stesse
    probabilita' del modello di prima (differenza < 1e-6; attesa 0 esatto).
    Il modello di prima si ottiene togliendo le due aggiunte (limiti illimitati)."""
    ms = _lega_normale(seed)
    nuovo = DixonColesModel(max_goals=10, half_life_days=0.0, ridge=RIDGE)
    fn = nuovo.fit(ms)
    assert not fn.rho_constraint_active and fn.rho == fn.rho_unconstrained

    monkeypatch.setattr(M, "_rho_limits_all_pairs", lambda *a, **k: (-math.inf, math.inf))
    monkeypatch.setattr(M, "rho_bounds", lambda *a, **k: (-math.inf, math.inf))
    vecchio = DixonColesModel(max_goals=10, half_life_days=0.0, ridge=RIDGE)
    fv = vecchio.fit(ms)
    assert fv.rho == fn.rho
    diff = 0.0
    lam = []
    for h in fn.teams:
        for a in fn.teams:
            if h == a:
                continue
            pn, pv = nuovo.predict(h, a), vecchio.predict(h, a)
            lam += [pn["lambda_home"], pn["lambda_away"]]
            diff = max(diff, float(np.abs(pn["grid"] - pv["grid"]).max()),
                       max(abs(pn["markets"][k] - pv["markets"][k]) for k in pn["markets"]))
    assert diff < 1e-6, diff
    # regime realistico: lambda stimate centrate nella fascia 0,8-2,5
    assert 0.8 <= float(np.percentile(lam, 10)) and float(np.percentile(lam, 90)) <= 2.5,         (min(lam), max(lam))


def test_markets_da_griglia_valida_restano_in_0_1():
    g = score_matrix(3.2, 2.1, rho_bounds(3.2, 2.1, M.TAU_MIN)[1], 10)
    mk = markets_from_matrix(g)
    assert 0.0 <= mk["under_0_5"] <= 1.0
