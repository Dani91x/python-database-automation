"""Note a video PRIMA/DOPO la forza (dati sintetici dei test, nessun DB).

Safe ``_hazard_check`` e Mike ``live_frame`` sullo stesso atlante generato dal
generatore vero (lega 39, 16 squadre, 4 stagioni), 65' 1-1 e 93' 1-0, senza e
con gli id squadra. Stampa anche le differenze massime di parita' col banco.
Uso: python AUDIT_2026-09-25/sonde/esempi_note_forza.py
"""
from __future__ import annotations

import os
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, RADICE)
for k, v in (("SUPABASE_URL", "http://127.0.0.1:9"), ("SUPABASE_SERVICE_ROLE_KEY", "x"), ("SUPABASE_KEY", "x")):
    os.environ.setdefault(k, v)

import numpy as np  # noqa: E402

from Betfair.stream.scalper import atlante_v4 as V4  # noqa: E402
from Betfair.stream.scalper.validazione_hazard import candidati as CA  # noqa: E402
from Betfair.stream.tests import test_atlante_v4_forza_id_squadra_2026_09_25 as T  # noqa: E402


def main() -> None:
    righe = T._righe_forza()
    stati = T._bootstrap(righe)
    atlas0 = T.G.assembla(stati, generated_at=T.ADESSO)
    partite = T._partite_banco(righe)
    lam = T._lam_banco(partite)
    S = T.tabella_stati(partite)
    idx = np.arange(S["y3"].size)
    lh = np.array([lam[p.fixture_id][0] for p in partite])[S["mi"]]
    la = np.array([lam[p.fixture_id][1] for p in partite])[S["mi"]]
    gt = np.array([float(sum(p.ft)) for p in partite])[S["mi"]]
    mod = CA.addestra_a(CA.ConfA(nome="A*", emivita=V4.EMIVITA, forza=True), S, idx,
                        np.array(sorted({p.league_id for p in partite})), lh + la, 2025, gt)
    atlas = T._con_beta(atlas0, mod.beta)
    out = [f"beta stimato dal banco su questi dati: {mod.beta}"]
    # parita' (tutti gli stati regolari + recupero 2T della lega 39, due coppie)
    dl = dp = 0.0
    n = 0
    for lid, ts in T.SQUADRE.items():
        fz = atlas["v4"]["by_league"][str(lid)]["forza"]
        for h, a in ((ts[0], ts[1]), (ts[3], ts[9]), (ts[12], ts[4])):
            lb = T._prossima(partite, lid, h, a)
            lp = V4.lambda_da_forza(fz, h, a)[:2]
            dl = max(dl, abs(lb[0] - lp[0]), abs(lb[1] - lp[1]))
            sel = np.flatnonzero((S["lega"] == lid) & ((S["stop"] == 0) | (S["tempo"] == 2)))[::7]
            at = CA.prevedi_a(mod, S, sel, np.full(S["y3"].size, lb[0] + lb[1]))
            for k, i in enumerate(sel):
                c = V4.consulta_atlante_v4(atlas, int(S["m_live"][i]), int(S["gh"][i] + S["ga"][i]), lid,
                                           tempo=int(S["tempo"][i]), home_id=h, away_id=a)
                dp = max(dp, abs(c["p_3min"] - at["p3"][k]), abs(c["p_2min"] - at["p2"][k]))
                n += 1
    out.append(f"parita' col banco: lambda max diff {dl:.2e}; p (2' e 3') max diff {dp:.2e} su {n} stati")
    from Betfair.mike import dossier as D
    from Betfair.safe_strategy.opportunity import OpportunityModel, resolve_lambdas
    from Betfair.safe_strategy.tests.test_opportunity import payload_1_1_65
    ips = T._ips(T.IPS_2T_REC_93, timeElapsed=65, elapsedRegularTime=65, elapsedAddedTime=None)
    p = payload_1_1_65(score_raw=ips)
    lm = resolve_lambdas(p, fixture=None)
    om = OpportunityModel(atlas=atlas)
    for nome, pay in (("Safe prima (senza id)", p),
                      ("Safe dopo (id 1004-1011)", dict(p, home_team_id=1004, away_team_id=1011))):
        hz = om._hazard_check(pay, lambdas=(lm[0], lm[1]), league_id=39, minute=65)
        out.append(f"{nome}: p_atlas {hz['p_atlas']:.4f} drop={hz['drop']} penalty={hz['penalty']}\n  > {hz['note']}")
    for nome, dos in (("Mike prima (dossier senza id)", {"league_id": 39}),
                      ("Mike dopo (dossier con id)", {"league_id": 39, "home_team_id": 1004,
                                                      "away_team_id": 1011})):
        # 80' (i dati sintetici non hanno gol nel recupero: al 93' il v4 da' 0)
        fr = D.live_frame(dos, minute=80, score_home=1, score_away=0, atlas=atlas,
                          payload={"minute": 80, "score_raw": T._ips(T.IPS_2T_REC_93, timeElapsed=80,
                                   elapsedRegularTime=80, elapsedAddedTime=None)})
        out.append(f"{nome}: hazard_atlas {fr['hazard_atlas']}\n  > {fr['hazard_nota']}")
    testo = "\n".join(out)
    print(testo)
    with open(os.path.join(os.path.dirname(__file__), "esempi_note_forza.txt"), "w", encoding="utf-8") as fh:
        fh.write(testo + "\n")


if __name__ == "__main__":
    main()
