"""Esempi PRIMA/DOPO (dati sintetici del test di collegamento): p v3 contro v4
per stato, e le note di Safe e Mike. Nessuna rete. Uso: python esempi_note_v4.py"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from Betfair.mike import dossier as D  # noqa: E402
from Betfair.safe_strategy.tests.test_opportunity import payload_1_1_65  # noqa: E402
from Betfair.stream.scalper import atlante_v4 as V4  # noqa: E402
from Betfair.stream.scalper.hazard_atlas import consulta_atlante  # noqa: E402
from Betfair.stream.tests import test_atlante_v4_collegato_2026_09_25 as T  # noqa: E402

gen = T._genera(T._righe_db())
atl = gen["atlas"]
senza = {k: v for k, v in atl.items() if k != "v4"}
print("stato | v3 (ieri, consulta_atlante) | v4 (oggi)")
for m, t, g in [(65, 2, 2), (87, 2, 1), (93, 2, 1), (97, 2, 1), (47, 1, 1)]:
    a = consulta_atlante(atl, m, g, 39)["p"]
    b = V4.consulta_atlante_v4(atl, m, g, 39, tempo=t)
    print(f"{m}' tempo {t} gol {g}: v3 {a:.4f} | v4 {b['p']:.4f} fase {b['fase']} "
          f"recupero atteso {b['recupero_atteso_min']}")
for nome, a in (("PRIMA (senza v4)", senza), ("DOPO (v4)", atl)):
    p = payload_1_1_65(minute=93, score_raw=T.IPS_2T_REC_93)
    om, hz = T._safe(p, a)
    print("Safe", nome, ":", hz["note"])
    out = D.live_frame({"league_id": 39}, minute=93, score_home=1, score_away=0, atlas=a,
                       payload={"minute": 93, "score_raw": T.IPS_2T_REC_93})
    print("Mike", nome, ":", out["hazard_nota"], "| hazard_atlas", out["hazard_atlas"])
