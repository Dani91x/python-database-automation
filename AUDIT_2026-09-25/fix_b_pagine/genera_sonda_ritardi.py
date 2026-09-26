"""Genera la SELECT equivalente al corpo NUOVO di get_market_delays (migrazione
analytics_rpc_veloci_2026-09-26.sql, sezione 10) con i parametri sostituiti da
letterali, per confrontarla in SOLA LETTURA sul DB vero con la funzione in
produzione:  select md5(public.get_market_delays(...)::text) = md5((<sonda>)::text)

Uso: python genera_sonda_ritardi.py LEGA MERCATO TARGET MODO [LAST_N] [STAGIONE]
Stampa la SQL su stdout. Nessuna connessione al DB.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HT = ('ovpt', 'unpt', 'ggpt', 'ggst', 'pf1x', 'pf2x', 'pfx1', 'pfx2', 'pt1', 'ptx', 'pt2')


def sonda(lega: int, mercato: str, target, modo: str, last_n=None, stagione=None,
          file: str = 'migrations/analytics_rpc_veloci_2026-09-26.sql') -> str:
    t = (REPO / file).read_text(encoding='utf-8').replace('\r\n', '\n')
    i = t.index('create or replace function public.get_market_delays(')
    t = t[i:]
    q0 = t.index('    with scope as (')
    q1 = t.index('    into v_result', q0)
    q2 = t.index('    from derived d, scope_stats ss, over_under ou;', q1)
    q = t[q0:q1] + t[q1 + len('    into v_result\n'):q2] + '    from derived d, scope_stats ss, over_under ou'
    lit = lambda v, typ: f'null::{typ}' if v is None else (f"'{v}'::{typ}" if typ == 'text' else f'{v}::{typ}')
    line = sge = reh = rea = None
    if mercato == 're':
        reh, rea = (int(x) for x in target.split('-'))
    elif mercato == 'sge':
        sge = int(target)
    elif mercato in ('over', 'under', 'ovpt', 'unpt'):
        line = target
    sub = {
        'p_league_id': lit(lega, 'integer'), 'p_market': lit(mercato, 'text'),
        'p_target': lit(target, 'text'), 'p_mode': lit(modo, 'text'),
        'p_last_n': lit(last_n, 'integer'), 'p_season_year': lit(stagione, 'integer'),
        'v_line': lit(line, 'numeric'), 'v_sge': lit(sge, 'integer'),
        'v_re_h': lit(reh, 'integer'), 'v_re_a': lit(rea, 'integer'),
        'v_uses_ht': 'true' if mercato in HT else 'false',
    }
    q = re.sub(r'--[^\n]*', '', q)   # via i commenti (contengono apostrofi)
    for k, v in sub.items():
        q = re.sub(rf'\b{k}\b', v, q)
    return '(' + q + ')'


if __name__ == '__main__':
    a = sys.argv[1:]
    lega, mercato, target, modo = int(a[0]), a[1], (None if a[2] == '-' else a[2]), a[3]
    last_n = int(a[4]) if len(a) > 4 and a[4] != '-' else None
    stagione = int(a[5]) if len(a) > 5 and a[5] != '-' else None
    args = ", ".join([str(lega), f"'{mercato}'", 'null' if target is None else f"'{target}'", f"'{modo}'",
                      str(last_n) if last_n else 'null', str(stagione) if stagione else 'null'])
    print(f"select md5(public.get_market_delays({args})::text) as vecchia,\n"
          f"       md5({sonda(lega, mercato, target, modo, last_n, stagione)}::text) as nuova")
