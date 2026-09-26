"""E2E FASE 3 sessione B (26/09) — Direzione: ricalcolo INDIPENDENTE in Python di ogni carta del cruscotto
(direzione = argmax Poisson con ripiego ML->TacticAI->API, affidabilita' dalla pagella con shrinkage K=50
lega->globale, Wilson 95%, lift = affid - base globale, concordanza, quota da analytics_bets) a partire
dalle RIGHE (fixture_predictions, direction_pagella, analytics_bets) e confronto con la RPC get_direction.
SOLA LETTURA: GET su tabelle; POST solo su /rpc/get_direction (funzione STABLE: non puo' scrivere).
Uso: python verifica_direzione.py <fixture_id,...>
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]


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


E = _env()
H = {'apikey': E['SUPABASE_SERVICE_ROLE_KEY'], 'Authorization': 'Bearer ' + E['SUPABASE_SERVICE_ROLE_KEY']}
U = E['SUPABASE_URL'] + '/rest/v1/'


def get(t, p):
    r = requests.get(U + t, headers=H, params=p, timeout=60); r.raise_for_status(); return r.json()


def rpc_stable(name, args):
    assert name in ('get_direction',), 'solo RPC STABLE di lettura'
    r = requests.post(U + 'rpc/' + name, headers=H, json=args, timeout=60); r.raise_for_status(); return r.json()


MAP = [('1x2', 'H', 'H', 'target_1x2', 'H', 'ft', 'home'), ('1x2', 'D', 'D', 'target_1x2', 'D', 'ft', 'draw'),
       ('1x2', 'A', 'A', 'target_1x2', 'A', 'ft', 'away'), ('ht_1x2', 'H', 'H', 'target_ht_1x2', 'H', 'ht', 'home'),
       ('ht_1x2', 'D', 'D', 'target_ht_1x2', 'D', 'ht', 'draw'), ('ht_1x2', 'A', 'A', 'target_ht_1x2', 'A', 'ht', 'away'),
       ('over_1_5', 'Over', 'True', 'target_over_1_5', 'True', 'ft', 'over_1_5'), ('over_1_5', 'Under', 'False', 'target_over_1_5', 'False', 'ft', 'under_1_5'),
       ('over_2_5', 'Over', 'True', 'target_over_2_5', 'True', 'ft', 'over_2_5'), ('over_2_5', 'Under', 'False', 'target_over_2_5', 'False', 'ft', 'under_2_5'),
       ('over_3_5', 'Over', 'True', 'target_over_3_5', 'True', 'ft', 'over_3_5'), ('over_3_5', 'Under', 'False', 'target_over_3_5', 'False', 'ft', 'under_3_5'),
       ('btts', 'Yes', 'True', 'target_btts', 'True', 'ft', 'btts_yes'), ('btts', 'No', 'False', 'target_btts', 'False', 'ft', 'btts_no'),
       ('first_half_over_0_5', 'Over', 'True', 'target_ht_over_0_5', 'True', 'ht', 'over_0_5'),
       ('first_half_over_0_5', 'Under', 'False', 'target_ht_over_0_5', 'False', 'ht', 'under_0_5')]


def bucket(p):
    if p is None: return None
    return '<.30' if p < .3 else '.30-.40' if p < .4 else '.40-.50' if p < .5 else '.50-.60' if p < .6 else '.60-.70' if p < .7 else '>.70'


def jl(v):
    return json.loads(v) if isinstance(v, str) else v


def argmax(d):
    items = [(s, v) for s, v in d.items() if v is not None]
    if not items: return None
    return sorted(items, key=lambda t: (-t[1], t[0]))[0][0]


def ricalcola(fid: int) -> dict:
    fp = get('fixture_predictions', {'select': 'league_id,db_json_analisi,model_predictions_json,tactical_engine_json,home_team_name,away_team_name,advice,under_over_line', 'fixture_id': f'eq.{fid}'})[0]
    dj, mp, tj = jl(fp['db_json_analisi']) or {}, jl(fp['model_predictions_json']) or {}, jl(fp['tactical_engine_json']) or {}
    home, away = fp['home_team_name'], fp['away_team_name']
    adv = re.sub(r'\s+and\s+[+-][0-9.]+\s+goals\s*$', '', re.sub(r'^Combo\s+', '', fp.get('advice') or '')).strip()
    api1x2 = None
    if adv.lower().startswith('winner : '):
        w = adv[9:].strip(); api1x2 = 'H' if w == home else 'A' if w == away else None
    elif adv.lower().startswith('double chance : '):
        a, _, b = adv[16:].partition(' or '); a, b = a.strip(), b.strip()
        if a == 'draw': api1x2 = '1X' if b == home else 'X2' if b == away else None
        elif b == 'draw': api1x2 = '1X' if a == home else 'X2' if a == away else None
    uol = (fp.get('under_over_line') or '').strip()
    uo_dir = 'Over' if uol.startswith('+') else 'Under' if uol.startswith('-') else None
    try: uo_line = float(re.sub(r'[^0-9.]', '', uol)) if re.sub(r'[^0-9.]', '', uol) else None
    except ValueError: uo_line = None
    pm = dj.get('markets_calibrated') or {}
    rows = {}
    for mk, sel, pk, mt, mc, sc, tk in MAP:
        pmk = pm.get(mk) if pm.get(mk) is not None else (dj.get('markets') or {}).get(mk)
        pp = (pmk or {}).get(pk)
        mlp = ((mp.get('targets') or {}).get(mt) or {}).get(mc)
        tap = (tj.get('markets') or {}).get(tk) if sc == 'ft' else (tj.get('markets_ht') or {}).get(tk)
        rows.setdefault(mk, {})[sel] = (None if pp is None else float(pp), None if mlp is None else float(mlp), None if tap is None else float(tap))
    pag = get('direction_pagella', {'select': 'league_id,market,selection,prob_bucket,n,hit_rate,base_rate', 'engine': 'eq.poisson', 'league_id': f'in.(0,{fp["league_id"]})'})
    P = {(r['league_id'], r['market'], r['selection'], r['prob_bucket']): r for r in pag}
    ab = get('analytics_bets', {'select': 'market,selection,odds_betfair,odds_book', 'fixture_id': f'eq.{fid}'})
    out = {}
    for mk, sels in rows.items():
        pd = argmax({s: v[0] for s, v in sels.items()}); md = argmax({s: v[1] for s, v in sels.items()}); td = argmax({s: v[2] for s, v in sels.items()})
        api = api1x2 if mk == '1x2' else (uo_dir if mk in ('over_1_5', 'over_2_5', 'over_3_5') and uo_line == float(mk[5] + '.5') else None)
        d = pd or md or td or api
        if d is None: continue
        p = sels.get(d, (None,))[0] if d in sels else None
        b = bucket(p)
        g = P.get((0, mk, d, b)); l = P.get((fp['league_id'], mk, d, b))
        K, z = 50, 1.96
        aff = neff = None; scope = None
        if l is not None and g is not None:
            aff = (l['n'] * l['hit_rate'] + K * g['hit_rate']) / (l['n'] + K); neff = l['n'] + K; scope = 'lega'
        elif g is not None:
            aff = g['hit_rate']; neff = g['n']; scope = 'globale'
        wl = wh = lift = None
        if aff is not None and neff:
            wc = (aff + z * z / (2 * neff)) / (1 + z * z / neff)
            ww = z * math.sqrt(aff * (1 - aff) / neff + z * z / (4 * neff * neff)) / (1 + z * z / neff)
            wl, wh = max(0, wc - ww), min(1, wc + ww)
            lift = aff - g['base_rate'] if g else None
        odds = next((float(x['odds_betfair'] if x['odds_betfair'] is not None else x['odds_book']) for x in ab if x['market'] == mk and x['selection'] == d and (x['odds_betfair'] is not None or x['odds_book'] is not None)), None)
        conc = [n for n, x in (('poisson', pd), ('ml', md), ('tacticai', td), ('api', api)) if x == d]
        tot = sum(1 for x in (any(v[0] is not None for v in sels.values()), any(v[1] is not None for v in sels.values()), any(v[2] is not None for v in sels.values()), api is not None) if x)
        out[mk] = {'direction': d, 'affidabilita': None if aff is None else round(aff, 4), 'wilson_low': None if wl is None else round(wl, 4),
                   'wilson_high': None if wh is None else round(wh, 4), 'n': None if neff is None else round(neff), 'lift': None if lift is None else round(lift, 4),
                   'base': None if g is None else round(g['base_rate'], 4), 'odds': odds, 'scope': scope, 'concordi': conc, 'motori_totali': tot}
    return out


def main():
    res = {}
    for fid in sys.argv[1].split(','):
        mine = ricalcola(int(fid))
        rpc = rpc_stable('get_direction', {'p_fixture_id': int(fid)})
        diffs = []
        rm = {m['market']: m for m in rpc.get('markets') or []}
        for mk in sorted(set(mine) | set(rm)):
            a, b = mine.get(mk), rm.get(mk)
            if a is None or b is None:
                diffs.append((mk, 'presenza', a is not None, b is not None)); continue
            for k in ('direction', 'affidabilita', 'wilson_low', 'wilson_high', 'n', 'lift', 'odds', 'scope', 'concordi', 'motori_totali'):
                va, vb = a.get(k), b.get(k)
                if isinstance(va, float) or isinstance(vb, float):
                    if va is None or vb is None or abs(float(va) - float(vb)) > 1e-4: diffs.append((mk, k, va, vb))
                elif (sorted(va) if isinstance(va, list) else va) != (sorted(vb) if isinstance(vb, list) else vb):
                    diffs.append((mk, k, va, vb))
        res[fid] = {'mercati_ricalcolati': len(mine), 'mercati_rpc': len(rm), 'poisson_present': rpc.get('poisson_present'),
                    'ordine_rpc': [m['market'] for m in rpc.get('markets') or []], 'scarti': diffs, 'ricalcolo': mine}
    print(json.dumps(res, indent=1, default=str))


if __name__ == '__main__':
    main()
