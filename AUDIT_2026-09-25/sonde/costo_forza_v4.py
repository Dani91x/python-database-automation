"""Sonda di COSTO della forza pre-partita nel v4 (A* completo, 25/09/2026 notte).

Nessuna rete, nessun DB. Righe sintetiche con le colonne vere: una lega grande
(20 squadre, 10 stagioni x 380 partite, girone doppio, fixture_id mescolati).
Misura:
  * bootstrap di UNA lega (generatore vero) con la forza contro lo stesso con
    ``aggiungi_forza`` spento: ms per lega e per partita;
  * byte: forza nello stato grezzo della lega (jsonb di hazard_atlas_leghe) e
    nel blocco v4 del file live; file live con 20 leghe con/senza forza;
  * assemblaggio (G.assembla) 20 leghe con/senza forza;
  * consultazione ``consulta_atlante_v4`` con e senza id squadra (ms).
Letture dal DB: nessuna in piu' (la forza si calcola dalle stesse righe gia'
lette per il v3/v4; il conteggio delle richieste del lettore finto lo prova).
Uso (radice del worktree): python AUDIT_2026-09-25/sonde/costo_forza_v4.py
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, RADICE)
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

from Betfair.stream.scalper import atlante_v4 as V4  # noqa: E402
from Betfair.stream.scalper import genera_atlante as G  # noqa: E402
from Betfair.stream.tests.test_atlante_v4_forza_id_squadra_2026_09_25 import _righe_forza  # noqa: E402
from Betfair.stream.tests.test_genera_atlante_2026_09_24 import LettoreFinto  # noqa: E402

STAGIONI = tuple(range(2016, 2026))
ADESSO = "2026-09-25T22:00:00+00:00"


def bootstrap(righe, con_forza: bool):
    originale = V4.aggiungi_forza
    if not con_forza:
        V4.aggiungi_forza = lambda *a, **k: False
    try:
        lettore = LettoreFinto({"matches": righe["matches"], "match_events": righe["match_events"]})
        stati = {}
        t0 = time.perf_counter()
        G.bootstrap(lettore, stati, [39], list(STAGIONI), {}, ADESSO)
        return stati, time.perf_counter() - t0, lettore.n_richieste
    finally:
        V4.aggiungi_forza = originale


def main() -> None:
    righe = _righe_forza(seme=1, stagioni=STAGIONI, leghe={39: list(range(1001, 1021))})
    n = len(righe["matches"])
    tempi = {True: [], False: []}
    richieste = {}
    for _ in range(3):
        for flag in (False, True):
            stati, dt, nr = bootstrap(righe, flag)
            tempi[flag].append(dt)
            richieste[flag] = nr
            if flag:
                con = stati
    t_senza, t_con = min(tempi[False]), min(tempi[True])
    fz = con["39"]["v4"]["forza"]
    righe_out = [f"partite {n}, squadre {len(fz['squadre'])}, forza n={fz['n']} fuori_ordine={fz['fuori_ordine']}",
                 f"bootstrap lega (10 stagioni): senza forza {t_senza * 1000:.0f} ms, con forza "
                 f"{t_con * 1000:.0f} ms, forza = {(t_con - t_senza) * 1000:+.0f} ms "
                 f"({(t_con - t_senza) * 1000 / n:+.4f} ms a partita; rumore di misura dello stesso ordine)",
                 f"richieste al DB (lettore finto): senza forza {richieste[False]}, con forza {richieste[True]}"]
    # costo PURO della forza (il bootstrap e' dominato da stati_partita e dal rumore):
    # le stesse 3.800 partite applicate da capo, ordinamento compreso
    gol = {}
    for e in righe["match_events"]:
        if e["event_type"] == "Goal":
            gol.setdefault(e["fixture_id"], []).append(e)
    from Betfair.stream.tests.test_genera_atlante_2026_09_24 import seleziona
    partite = [V4.partita_v4(seleziona(m, G.COLONNE_MATCH), gol.get(m["fixture_id"], []))[0]
               for m in righe["matches"]]
    best = 1e9
    for _ in range(5):
        v4 = {"forza": V4.forza_vuota()}
        coda = [(v4, p) for p in partite]
        t0 = time.perf_counter()
        V4.applica_coda_forza(coda)
        best = min(best, time.perf_counter() - t0)
    righe_out.append(f"forza pura: {best * 1000:.1f} ms per {len(partite)} partite "
                     f"({best * 1e6 / len(partite):.1f} us a partita, ordinamento compreso)")
    b_stato = len(json.dumps(fz, separators=(",", ":")))
    b_v4 = len(json.dumps(con["39"]["v4"], separators=(",", ":")))
    righe_out.append(f"stato grezzo: forza {b_stato} B su stato v4 {b_v4} B")
    atl = G.assembla(con, generated_at=ADESSO)
    b_blk = len(json.dumps(atl["v4"]["by_league"]["39"]["forza"], separators=(",", ":")))
    righe_out.append(f"file live: forza per lega {b_blk} B (20 squadre)")
    # 20 leghe: stesse righe, id di lega diversi
    venti = {}
    for k in range(20):
        st = copy.deepcopy(con["39"])
        st["league_id"] = 1000 + k
        venti[str(1000 + k)] = st
    senza = copy.deepcopy(venti)
    for st in senza.values():
        st["v4"]["forza"] = V4.forza_vuota()
    tt = {}
    for nome, stati in (("senza", senza), ("con", venti)):
        best = 1e9
        for _ in range(5):
            t0 = time.perf_counter()
            a = G.assembla(stati, generated_at=ADESSO)
            best = min(best, time.perf_counter() - t0)
        tt[nome] = (best, len(json.dumps(a, separators=(",", ":"))))
    righe_out.append(f"assembla 20 leghe: senza forza {tt['senza'][0] * 1000:.1f} ms, con forza "
                     f"{tt['con'][0] * 1000:.1f} ms; file live {tt['senza'][1]} -> {tt['con'][1]} B")
    atl1 = {"meta": atl["meta"], "v4": atl["v4"]}
    for nome, kw in (("senza id", {}), ("con id", {"home_id": 1001, "away_id": 1002})):
        t0 = time.perf_counter()
        for _ in range(2000):
            V4.consulta_atlante_v4(atl1, 63, 1, 39, tempo=2, **kw)
        righe_out.append(f"consulta_atlante_v4 {nome}: {(time.perf_counter() - t0) / 2000 * 1000:.4f} ms")
    testo = "\n".join(righe_out)
    print(testo)
    with open(os.path.join(os.path.dirname(__file__), "costo_forza_v4_esito.txt"), "w", encoding="utf-8") as fh:
        fh.write(testo + "\n")


if __name__ == "__main__":
    main()
