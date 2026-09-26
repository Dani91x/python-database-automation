"""E2E FASE 3 sessione B (26/09) — ricalcolo INDIPENDENTE dei motori per partita, SOLA LETTURA.

Legge `fixture_predictions` via PostgREST (GET, service role del .env della radice: nessuna scrittura
possibile da questo script: solo requests.get). Ricalcola:
  * Poisson: griglia DC con le funzioni di PRODUZIONE (`_build_score_grid`, `_dc_tau` di
    Prediction/today_predictions_backfill.py) dalle lambda e dal rho salvati → mercati FT; ibrido 1T dai
    dettagli; calibrazione con `PoissonCalibrator` (legge poisson_calibration, sola lettura) sui mercati
    grezzi salvati → confronto con `markets_calibrated`.
  * TacticAI: `score_matrix`/`markets_from_matrix`/`top_correct_scores`/`expected_goals` di
    tactical_engine/dixon_coles.py dalle lambda e dal rho (clamp `rho_bounds(TAU_MIN)`) → confronto col payload;
    coerenza interna di markets_ht (somma 1X2, under = 1 − over, nessun negativo).
  * ML: somma delle classi = 1 per target, classe prevista = argmax, coerenza col registro.
Uso: python verifica_modelli.py <fixture_id,...>  (stampa JSON)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[2]          # worktree
MAIN = ROOT.parents[2] if (ROOT.parent.name == 'worktrees') else ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'Prediction'))


def _env() -> dict:
    for base in (ROOT, *ROOT.parents):
        p = base / '.env'
        if p.exists():
            d = {}
            for line in p.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    d[k.strip()] = v.strip().strip('"').strip("'")
            if d.get('SUPABASE_URL') and d.get('SUPABASE_SERVICE_ROLE_KEY'):
                return d
    raise SystemExit('.env non trovato')


ENV = _env()
H = {'apikey': ENV['SUPABASE_SERVICE_ROLE_KEY'], 'Authorization': 'Bearer ' + ENV['SUPABASE_SERVICE_ROLE_KEY']}


def get(table: str, params: dict) -> list:
    r = requests.get(f"{ENV['SUPABASE_URL']}/rest/v1/{table}", headers=H, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


from today_predictions_backfill import _build_score_grid, _dc_tau, get_league_rho  # noqa: E402  (produzione)
from tactical_engine.dixon_coles import score_matrix, markets_from_matrix, top_correct_scores, expected_goals, rho_bounds  # noqa: E402
from tactical_engine import model as te_model  # noqa: E402


def poisson_check(j: dict) -> dict:
    inp = j.get('inputs') or {}
    lh, la, rho = inp.get('lambda_home'), inp.get('lambda_away'), inp.get('dc_rho')
    out = {'model': j.get('model'), 'generated_at': j.get('generated_at'), 'calibrated_at': j.get('calibrated_at'),
           'calibration_source': j.get('calibration_source'), 'lambda_home': lh, 'lambda_away': la, 'dc_rho': rho,
           'rho_file_ora': get_league_rho(j.get('league_id'))}
    if lh is None or la is None or rho is None:
        out['errore'] = 'input mancanti'
        return out
    g = _build_score_grid(lh, la, 10)
    for a in (0, 1):
        for b in (0, 1):
            g[a, b] *= _dc_tau(a, b, lh, la, rho=rho)
    g = g / g.sum()
    hg = np.arange(11).reshape(-1, 1); ag = np.arange(11).reshape(1, -1); t = hg + ag
    ph, pd, pa = g[hg > ag].sum(), g[hg == ag].sum(), g[hg < ag].sum(); s = ph + pd + pa
    rec = {'1x2': {'H': ph / s, 'D': pd / s, 'A': pa / s},
           'over_1_5': {'True': g[t >= 2].sum()}, 'over_2_5': {'True': g[t >= 3].sum()},
           'over_3_5': {'True': g[t >= 4].sum()}, 'btts': {'True': g[(hg > 0) & (ag > 0)].sum()}}
    m = j.get('markets') or {}
    diffs = {}
    for mk, sel in rec.items():
        for k, v in sel.items():
            st = (m.get(mk) or {}).get(k)
            diffs[f'{mk}.{k}'] = None if st is None else round(abs(float(st) - float(v)), 5)
        if mk != '1x2':
            st_t, st_f = (m.get(mk) or {}).get('True'), (m.get(mk) or {}).get('False')
            if st_t is not None and st_f is not None:
                diffs[f'{mk}.somma'] = round(abs(st_t + st_f - 1), 5)
    x = m.get('1x2') or {}
    if x:
        diffs['1x2.somma'] = round(abs(sum(float(v) for v in x.values()) - 1), 5)
    fh = (m.get('first_half_over_0_5') or {})
    det = fh.get('details') or {}
    if det:
        hyb = det['w_freq'] * det['freq'] + (1 - det['w_freq']) * det['poisson']
        diffs['1T.ibrido'] = round(abs(hyb - fh['True']), 5)
        diffs['1T.somma'] = round(abs(fh['True'] + fh['False'] - 1), 5)
    ht = m.get('ht_1x2') or {}
    if ht:
        diffs['ht_1x2.somma'] = round(abs(sum(float(v) for v in ht.values()) - 1), 5)
        # HT: lambda_ht = lambda * ht_ratio (ratio salvato a 3 decimali)
        rh, ra = inp.get('ht_ratio_home'), inp.get('ht_ratio_away')
        if rh is not None and ra is not None:
            lhh, lah = lh * rh, la * ra
            gh = _build_score_grid(lhh, lah, 4)
            for a in (0, 1):
                for b in (0, 1):
                    gh[a, b] *= _dc_tau(a, b, lhh, lah, rho=rho)
            gh = gh / gh.sum()
            h4 = np.arange(5).reshape(-1, 1); a4 = np.arange(5).reshape(1, -1)
            q = [gh[h4 > a4].sum(), gh[h4 == a4].sum(), gh[h4 < a4].sum()]; sq = sum(q)
            for k, v in zip('HDA', q):
                diffs[f'ht_1x2.{k}'] = round(abs(ht[k] - v / sq), 5)
            diffs['1T.poisson_vs_griglia'] = round(abs(det.get('poisson', 0) - (1 - gh[0, 0])), 5) if det else None
    out['scarti'] = diffs
    out['scarto_max'] = max([v for v in diffs.values() if v is not None] or [0])
    # calibrazione rifatta ora
    try:
        from poisson_calibrator import PoissonCalibrator
        cal = PoissonCalibrator()
        recal = cal.calibrate_markets(m, j.get('league_id'))
        mc = j.get('markets_calibrated') or {}
        cd = {}
        for mk, sel in recal.items():
            for k, v in (sel or {}).items():
                if k == 'details' or not isinstance(v, (int, float)):
                    continue
                st = (mc.get(mk) or {}).get(k)
                cd[f'{mk}.{k}'] = None if st is None else round(abs(float(st) - float(v)), 5)
        out['calibrazione_fonte_ora'] = cal.source
        out['calibrazione_scarti'] = cd
        out['calibrazione_scarto_max'] = max([v for v in cd.values() if v is not None] or [0])
        for mk, sel in mc.items():
            vals = [v for k, v in (sel or {}).items() if isinstance(v, (int, float))]
            if vals:
                out.setdefault('calibrati_somme', {})[mk] = round(sum(vals), 5)
    except Exception as e:  # noqa: BLE001
        out['calibrazione_errore'] = str(e)
    return out


def tactical_check(j: dict) -> dict:
    lh, la = j.get('lambda_home'), j.get('lambda_away')
    rho = (j.get('training') or {}).get('rho')
    out = {'engine_version': j.get('engine_version'), 'generated_at': j.get('generated_at'), 'lambda_home': lh,
           'lambda_away': la, 'rho': rho}
    m = j.get('markets') or {}
    neg = {k: v for k, v in m.items() if isinstance(v, (int, float)) and (v < 0 or v > 1)}
    neg_ht = {k: v for k, v in (j.get('markets_ht') or {}).items() if isinstance(v, (int, float)) and (v < 0 or v > 1)}
    out['fuori_0_1_ft'] = neg
    out['fuori_0_1_ht'] = neg_ht
    if lh and la and rho is not None:
        lo, hi = rho_bounds(lh, la, te_model.TAU_MIN)
        r = min(max(rho, lo), hi)
        g = score_matrix(lh, la, r, 10)
        rec = markets_from_matrix(g)
        out['rho_eff'] = r
        out['scarti_ft'] = {k: round(abs(float(m[k]) - v), 4) for k, v in rec.items() if k in m}
        out['scarto_max_ft'] = max(out['scarti_ft'].values() or [0])
        eg = expected_goals(g)
        out['exp_goals_scarto'] = [round(abs(eg[0] - j.get('exp_goals_home', 0)), 3), round(abs(eg[1] - j.get('exp_goals_away', 0)), 3)]
        ts = top_correct_scores(g, 5)
        out['top_scores_ricalcolo'] = [(x, y, round(p, 4)) for x, y, p in ts]
        out['top_scores_payload'] = [(t['h'], t['a'], t['p']) for t in (j.get('top_scores') or [])]
    for nome, mm in (('ft', m), ('ht', j.get('markets_ht') or {})):
        if mm:
            out[f'somma_1x2_{nome}'] = round(mm.get('home', 0) + mm.get('draw', 0) + mm.get('away', 0), 4)
            out[f'u+o_0_5_{nome}'] = round(mm.get('under_0_5', 0) + mm.get('over_0_5', 0), 4)
    return out


def ml_check(j: dict) -> dict:
    t = j.get('targets') or {}
    out = {'model_name': j.get('model_name'), 'generated_at': j.get('generated_at'), 'n_targets': len(t)}
    bad = {}
    for k, cl in t.items():
        vals = {c: v for c, v in (cl or {}).items() if isinstance(v, (int, float))}
        s = sum(vals.values())
        if abs(s - 1) > 0.002 or any(v < 0 or v > 1 for v in vals.values()):
            bad[k] = round(s, 4)
    out['target_somma_non_1'] = bad
    ag = j.get('ensemble_agreement') or {}
    mism = {}
    for k, a in ag.items():
        cl = t.get(k) or {}
        if cl and a.get('predicted_class') is not None:
            am = max(cl, key=lambda c: cl[c])
            if str(am) != str(a.get('predicted_class')):
                mism[k] = [a.get('predicted_class'), am]
    out['classe_prevista_non_argmax'] = mism
    out['chiavi'] = sorted(j.keys())
    return out


def main() -> None:
    ids = sys.argv[1].split(',')
    rows = get('fixture_predictions', {'select': 'fixture_id,league_id,db_json_analisi,tactical_engine_json,model_predictions_json',
                                       'fixture_id': f'in.({",".join(ids)})'})
    res = {}
    for r in rows:
        d = {}
        for col, fn in (('db_json_analisi', poisson_check), ('tactical_engine_json', tactical_check), ('model_predictions_json', ml_check)):
            j = r.get(col)
            if isinstance(j, str):
                try:
                    j = json.loads(j)
                except Exception:  # noqa: BLE001
                    j = None
            d[col] = fn(j) if isinstance(j, dict) else None
        res[r['fixture_id']] = d
    print(json.dumps(res, indent=1, default=float))


if __name__ == '__main__':
    main()
