"""Sonda di COSTO dell'atlante v4 collegato (nessuna rete, nessun DB).

Misura, su righe sintetiche con le colonne vere (una lega da 10 stagioni x 380
partite, come una lega grande del motore a domanda):
  * bootstrap di UNA lega: generatore con il v4 contro lo stesso senza il v4
    (``aggiungi_v4`` spento), ms per lega e per partita;
  * assemblaggio (G.assembla) con e senza il blocco v4, su 1 e su 20 leghe;
  * consultazione ``consulta_atlante_v4`` (ms);
  * byte: risposta di ``matches`` con/senza la colonna ``extra`` (JSON come lo
    manda PostgREST), stato v4 per lega (jsonb), blocco v4 per lega nel file live.
Uso: python AUDIT_2026-09-25/sonde/costo_v4_collegato.py
"""
from __future__ import annotations

import json
import os
import sys
import time

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, RADICE)

import numpy as np  # noqa: E402

from Betfair.stream.scalper import atlante_v4 as V4  # noqa: E402
from Betfair.stream.scalper import genera_atlante as G  # noqa: E402
from Betfair.stream.tests.test_atlante_v4_collegato_2026_09_25 import (_minuto, _riga_gol,  # noqa: E402
                                                                        _riga_match)
from Betfair.stream.tests.test_genera_atlante_2026_09_24 import LettoreFinto, seleziona  # noqa: E402

STAGIONI = list(range(2016, 2026))
PER_STAGIONE = 380


def righe_lega(lid: int, seme: int):
    rng = np.random.default_rng(seme)
    m, e = [], []
    eid = lid * 10_000_000
    fid = lid * 1_000_000
    for s in STAGIONI:
        for _ in range(PER_STAGIONE):
            fid += 1
            gol = []
            for h in (1, 2):
                for t in range(1, 46):
                    if rng.random() < 0.029:
                        gol.append((h, t, 1 if rng.random() < 0.55 else 2))
            d2 = int(rng.integers(3, 10)) if s >= 2024 else None
            for j in range(1, (d2 or 4) + 1):
                if rng.random() < 0.035:
                    gol.append((2, 45 + j, 2))
            gh = sum(1 for g in gol if g[2] == 1)
            m.append(_riga_match(fid, lid, s, gh, len(gol) - gh, d2))
            for h, pos, team in gol:
                mi, ex = _minuto(h, pos)
                eid += 1
                e.append(_riga_gol(eid, fid, lid, s, team, mi, ex))
    return m, e


def bootstrap(m, e, lid, con_v4: bool):
    originale = G.aggiungi_v4
    if not con_v4:
        G.aggiungi_v4 = lambda *a, **k: False
    try:
        stati = {}
        t0 = time.perf_counter()
        G.bootstrap(LettoreFinto({"matches": m, "match_events": e}), stati, [lid], STAGIONI, {},
                    "2026-09-25T20:00:00+00:00")
        return stati, time.perf_counter() - t0
    finally:
        G.aggiungi_v4 = originale


def main() -> None:
    m, e = righe_lega(39, 1)
    n = len(m)
    tempi = {True: [], False: []}
    for _ in range(3):
        for flag in (False, True):
            _, dt = bootstrap(m, e, 39, flag)
            tempi[flag].append(dt)
    st_v4, _ = bootstrap(m, e, 39, True)
    t_senza, t_con = min(tempi[False]), min(tempi[True])
    print(f"partite {n}, gol {len(e)}")
    print(f"bootstrap lega (10 stagioni): senza v4 {t_senza * 1000:.0f} ms, con v4 {t_con * 1000:.0f} ms, "
          f"v4 = +{(t_con - t_senza) * 1000:.0f} ms (+{(t_con - t_senza) / n * 1000:.3f} ms a partita)")
    # righe/byte della risposta di matches
    col_prima = G.COLONNE_MATCH.replace(",extra:raw_json->fixture->status->extra", "")
    b_prima = len(json.dumps([seleziona(r, col_prima) for r in m], separators=(",", ":")))
    b_dopo = len(json.dumps([seleziona(r, G.COLONNE_MATCH) for r in m], separators=(",", ":")))
    print(f"matches: righe {n} = {n} (invariate); byte risposta {b_prima} -> {b_dopo} "
          f"(+{b_dopo - b_prima}, +{(b_dopo - b_prima) / n:.1f} byte a riga, "
          f"+{(b_dopo / b_prima - 1) * 100:.1f}%)")
    stato = st_v4["39"]
    v4_b = len(json.dumps(stato["v4"], separators=(",", ":")))
    v3_b = len(json.dumps({k: v for k, v in stato.items() if k not in ("v4", "fixtures")}, separators=(",", ":")))
    fx_b = len(json.dumps(stato["fixtures"], separators=(",", ":")))
    print(f"stato lega: v3 {v3_b} B + fixtures {fx_b} B; v4 {v4_b} B "
          f"({v4_b / len(STAGIONI):.0f} B a stagione)")
    # assemblaggio: 1 lega e 20 leghe (stati copiati con id diversi)
    for k in (1, 20):
        stati = {}
        for i in range(k):
            c = json.loads(json.dumps(stato))
            c["league_id"] = 1000 + i
            stati[str(1000 + i)] = c
        senza = {l: {kk: vv for kk, vv in s.items() if kk != "v4"} for l, s in stati.items()}
        ts, tc = [], []
        for _ in range(3):
            t0 = time.perf_counter()
            G.assembla(senza, generated_at="2026-09-25T20:00:00+00:00")
            ts.append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            atl = G.assembla(stati, generated_at="2026-09-25T20:00:00+00:00")
            tc.append(time.perf_counter() - t0)
        blk = len(json.dumps(atl["v4"]["by_league"]["1000"], separators=(",", ":")))
        tot = len(json.dumps(atl, separators=(",", ":")))
        tot_senza = len(json.dumps(G.assembla(senza, generated_at="x"), separators=(",", ":")))
        print(f"assembla {k} leghe: senza v4 {min(ts) * 1000:.1f} ms, con v4 {min(tc) * 1000:.1f} ms; "
              f"blocco v4 per lega {blk} B; file live {tot_senza} -> {tot} B")
    t0 = time.perf_counter()
    for i in range(2000):
        V4.consulta_atlante_v4(atl, 60 + i % 40, i % 4, 1000, tempo=2)
    print(f"consulta_atlante_v4: {(time.perf_counter() - t0) / 2000 * 1000:.3f} ms")


if __name__ == "__main__":
    main()
