"""PoC World Cup (lega 1): fit, forze, certificazione counterfactual,
validazione out-of-sample, report parlanti.  python tactical_engine/run_worldcup.py
"""
from __future__ import annotations

import copy
import math
import os
import sys
from typing import Dict, List

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tactical_engine.data_loader import load_league  # noqa: E402
from tactical_engine.model import DixonColesModel  # noqa: E402
from tactical_engine.report import build_match_report, pct  # noqa: E402

LEAGUE_ID = 1
NEUTRAL = True  # i Mondiali si giocano in campo neutro


def _outcome(m) -> str:
    if m.home_goals > m.away_goals:
        return "home"
    return "draw" if m.home_goals == m.away_goals else "away"


def base_rates(matches) -> Dict[str, float]:
    """Frequenze 1X2 osservate (per la baseline 'no-model')."""
    c = {"home": 0.0, "draw": 0.0, "away": 0.0}
    for m in matches:
        c[_outcome(m)] += 1
    n = sum(c.values()) or 1.0
    return {k: v / n for k, v in c.items()}


def logloss_1x2(model: DixonColesModel, matches, train_base: Dict[str, float]) -> Dict:
    """Log-loss medio 1X2 out-of-sample vs baseline ONESTA = frequenze del TRAINING
    (NON del test: usare il test sarebbe sbirciare il risultato)."""
    eps = 1e-15
    rows = []
    skipped = 0
    for m in matches:
        try:
            p = model.predict(m.home_id, m.away_id, neutral=NEUTRAL)["markets"]
        except KeyError:
            skipped += 1
            continue
        rows.append((p, _outcome(m)))
    if not rows:
        return {"n": 0, "skipped": skipped}
    model_ll = -np.mean([math.log(max(p[o], eps)) for p, o in rows])
    base_ll = -np.mean([math.log(max(train_base[o], eps)) for _, o in rows])
    return {"n": len(rows), "skipped": skipped, "model_logloss": model_ll,
            "baseline_logloss": base_ll, "improvement": base_ll - model_ll}


def counterfactual_checks(model: DixonColesModel, names) -> Dict[str, str]:
    """Cond.4: test causali. Restituisce righe parlanti."""
    f = model.fit_
    out: Dict[str, str] = {}

    # 1) campo neutro: h forzato a 0 (corretto per i Mondiali, no vantaggio-campo)
    out["home_adv"] = (f"vantaggio-campo h={f.home_adv:+.3f} "
                       f"({'OK = 0 forzato (campo neutro)' if abs(f.home_adv) < 1e-9 else f'={f.home_adv:+.3f}'})")

    # 2) indebolendo l'attacco della squadra piu' forte, P(vittoria) DEVE scendere
    strengths = model.strength_table()
    top = strengths[0]["team_id"]
    # avversario di forza mediana
    mid = strengths[len(strengths) // 2]["team_id"]
    p_before = model.predict(top, mid, neutral=NEUTRAL)["markets"]["home"]
    weak = copy.deepcopy(model)
    i = weak._idx[top]
    weak.fit_.attack[i] = weak.fit_.attack.min()  # attacco al minimo
    p_after = weak.predict(top, mid, neutral=NEUTRAL)["markets"]["home"]
    ok = p_after < p_before - 1e-6
    out["weaken_attack"] = (f"indebolisco attacco {names.get(top, top)}: "
                            f"P(vittoria) {pct(p_before)} -> {pct(p_after)} "
                            f"{'OK scende (coerente)' if ok else 'FAIL non scende'}")

    # 3) rinforzando la difesa dell'avversario, P(over 2.5) DEVE scendere
    o_before = model.predict(top, mid, neutral=NEUTRAL)["markets"]["over_2_5"]
    strong = copy.deepcopy(model)
    j = strong._idx[mid]
    strong.fit_.defense[j] = strong.fit_.defense.max()  # difesa al massimo
    o_after = strong.predict(top, mid, neutral=NEUTRAL)["markets"]["over_2_5"]
    ok2 = o_after < o_before - 1e-6
    out["strengthen_defense"] = (f"rinforzo difesa {names.get(mid, mid)}: "
                                 f"P(Over2.5) {pct(o_before)} -> {pct(o_after)} "
                                 f"{'OK scende (coerente)' if ok2 else 'FAIL non scende'}")
    return out


def main() -> int:
    print("Carico dati World Cup (lega 1)...")
    ft_m, ft_d, ht_m, ht_d, names = load_league(LEAGUE_ID)
    print(f"scoreline 90': {len(ft_m)} | scoreline HT: {len(ht_m)} | squadre: {len(names)}")

    # half_life lungo: i Mondiali distano 4 anni, servono piu' edizioni per avere segnale.
    # ridge piu' forte: 133 parametri su ~124 partite effettive -> shrinkage necessario.
    # fit_home_adv=False: campo neutro, nessun vantaggio-campo (corretto per i Mondiali).
    model = DixonColesModel(max_goals=10, half_life_days=2200.0, ridge=0.15)
    fit = model.fit(ft_m, dates=ft_d, fit_home_adv=False)
    print(f"\nFIT 90': converged={fit.converged} n={fit.n_matches} eff={fit.eff_matches:.1f} "
          f"const={fit.const:.3f} h={fit.home_adv:+.3f} rho={fit.rho:+.3f}")

    ht_model = DixonColesModel(max_goals=8, half_life_days=2200.0, ridge=0.15)
    ht_model.fit(ht_m, dates=ht_d, fit_home_adv=False)

    # ---- tabella forze ----
    st = model.strength_table()
    print("\n=== FORZE INFERITE (top 10) ===")
    print(f"{'squadra':18} {'att':>6} {'def':>6}")
    for r in st[:10]:
        print(f"{names.get(r['team_id'], r['team_id'])[:18]:18} {r['att']:6.2f} {r['def_factor']:6.2f}")
    print("...")
    for r in st[-3:]:
        print(f"{names.get(r['team_id'], r['team_id'])[:18]:18} {r['att']:6.2f} {r['def_factor']:6.2f}")

    # ---- counterfactual ----
    print("\n=== CERTIFICAZIONE COUNTERFACTUAL ===")
    cf = counterfactual_checks(model, names)
    for v in cf.values():
        print("  " + v)

    # ---- validazione out-of-sample: train<=2018, test=2022 ----
    print("\n=== VALIDAZIONE OUT-OF-SAMPLE (train<=2018, test=2022) ===")
    ft_train, dt_train, _, _, _ = load_league(LEAGUE_ID, season_max=2018)
    # test = partite 2022 (le ricarico filtrando per data: stagione 2022)
    all_m, all_d, _, _, _ = load_league(LEAGUE_ID)
    test = [m for m, d in zip(all_m, all_d) if d.year in (2022, 2023)]
    val_model = DixonColesModel(max_goals=10, half_life_days=2200.0, ridge=0.15)
    val_model.fit(ft_train, dates=dt_train, fit_home_adv=False)
    res = logloss_1x2(val_model, test, base_rates(ft_train))
    if res.get("n"):
        print(f"  partite test: {res['n']} (saltate per squadra mai vista: {res['skipped']})")
        print(f"  log-loss modello:   {res['model_logloss']:.4f}")
        print(f"  log-loss baseline:  {res['baseline_logloss']:.4f}")
        print(f"  miglioramento:      {res['improvement']:+.4f} "
              f"({'OK modello batte baseline' if res['improvement'] > 0 else 'modello NON batte baseline'})")
    else:
        print("  test insufficiente:", res)

    # ---- report parlanti su alcune partite (sul modello full) ----
    print("\n=== REPORT PARLANTI (esempi, campo neutro) ===")
    examples = [(st[0]["team_id"], st[len(st) // 2]["team_id"]),
                (st[1]["team_id"], st[2]["team_id"]),
                (st[len(st) // 2]["team_id"], st[-2]["team_id"])]
    for h, a in examples:
        pf = model.predict(h, a, neutral=NEUTRAL)
        ph = ht_model.predict(h, a, neutral=NEUTRAL) if (h in ht_model._idx and a in ht_model._idx) else None
        print(build_match_report(pf, ph, names))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
