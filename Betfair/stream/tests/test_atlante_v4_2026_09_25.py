"""Atlante Hazard v4 (modulo vincente del banco, NON collegato): dalle righe del
DB allo stato grezzo per stagione, assemblaggio, consultazione in live.

Finti con le chiavi VERE (``raccogli.COLONNE_MATCH_BANCO``, ``COLONNE_GOL``).
Il test centrale e' la PARITA' col candidato validato: stesse partite ->
``atlante_v4`` e ``candidati`` (A1+A2+A5) danno gli stessi numeri, stato per stato.
"""
from __future__ import annotations

import numpy as np
import pytest

from Betfair.stream.scalper import atlante_v4 as V4
from Betfair.stream.scalper import genera_atlante as G
from Betfair.stream.scalper.validazione_hazard import candidati as CA
from Betfair.stream.scalper.validazione_hazard.dati import Partita
from Betfair.stream.scalper.validazione_hazard.stati import tabella_stati


def _match(fid, gh, ga, *, extra=None, season=2024, lid=39):
    return {"fixture_id": fid, "league_id": lid, "season_year": season,
            "fixture_date": "2024-09-01T15:00:00+00:00", "status_short": "FT", "home_team_id": 1,
            "home_team_name": "A", "away_team_id": 2, "away_team_name": "B", "goals_home": gh,
            "goals_away": ga, "halftime_home": 0, "halftime_away": 0, "status_elapsed": 90,
            "extra": extra, "p1": 1, "p2": 2}


def _ev(eid, fid, team, minute, extra=None, etype="Goal", detail="Normal Goal"):
    return {"id": eid, "fixture_id": fid, "league_id": 39, "season_year": 2024, "team_id": team,
            "event_type": etype, "detail": detail, "minute": minute, "minute_extra": extra, "player_id": 1}


def test_partita_v4_accetta_come_la_produzione():
    p, motivo = V4.partita_v4(_match(1, 1, 0, extra=5), [_ev(1, 1, 1, 90, 3)])
    assert motivo == "ok" and p.gol == [(2, 48, "h")] and p.d2 == 5
    p, _ = V4.partita_v4(_match(9, 1, 0, extra=2), [_ev(9, 9, 1, 90, 3)])
    assert p.d2 == 3               # un gol al 90+3 prova che il recupero e' durato almeno 3'
    p, motivo = V4.partita_v4(_match(2, 2, 0), [_ev(2, 2, 1, 10)])
    assert p is None and motivo == G.sequenza_partita(_match(2, 2, 0), [_ev(2, 2, 1, 10)])[1]
    p, _ = V4.partita_v4(_match(3, 0, 0, extra=4), [_ev(3, 3, 1, 45, 3, "Card", "Yellow Card")],
                         eventi_recupero=True)
    assert p.s1_vivo == 3
    p, _ = V4.partita_v4(_match(4, 0, 0, extra=4), [_ev(4, 4, 1, 45, 3, "Card", "Yellow Card")])
    assert p.s1_vivo == 0          # senza gli eventi in recupero letti: ripiego


def test_aggiungi_idempotente():
    st = V4.stato_lega_v4_vuoto(39)
    p, _ = V4.partita_v4(_match(1, 1, 0, extra=5), [_ev(1, 1, 1, 30)])
    assert V4.aggiungi_partita_v4(st, p) is True
    assert V4.aggiungi_partita_v4(st, p) is False
    blk = st["stagioni"]["2024"]
    assert blk["n_fixtures"] == 1 and blk["gol"] == 1 and blk["durate"] == {"5": 1}
    c = np.asarray(blk["celle"]).reshape(V4.NT, V4.NG, 3)
    assert c[:, :, 0].sum() == 90 + 5          # 90 minuti regolari + 5 di recupero 2T


def _sintetico(seme=5, n=1400):
    rng = np.random.default_rng(seme)
    P = []
    for i in range(n):
        lid = (39, 140)[i % 2] if i % 11 else 835       # la 835 resta sotto le 300 partite
        gol = []
        for h in (1, 2):
            for t in range(1, 46):
                if rng.random() < 0.027 + 0.004 * (lid == 140):
                    gol.append((h, t, "h" if rng.random() < 0.55 else "a"))
        d2 = int(rng.integers(3, 10)) if i % 5 else None
        for j in range(1, (d2 or 0) + 1):
            if rng.random() < 0.035:
                gol.append((2, 45 + j, "a"))
        s1 = int(rng.integers(0, 4))
        P.append(Partita(fixture_id=i, league_id=lid, season=2021 + i % 4, date="2024-01-01", home_id=1,
                         away_id=2, home_name="A", away_name="B",
                         ft=(sum(1 for g in gol if g[2] == "h"), sum(1 for g in gol if g[2] == "a")),
                         gol=sorted(gol), d2=d2, s1_vivo=s1, eventi_recupero=True))
    return P


@pytest.mark.parametrize("forza", [False, True])
def test_parita_modulo_col_candidato_validato(forza):
    """Stesse partite -> stessi numeri di candidati (A1+A2[emivita 3]+A5)."""
    P = _sintetico()
    S = tabella_stati(P)
    idx = np.arange(S["y3"].size)
    rng = np.random.default_rng(1)
    lam_m = rng.uniform(1.8, 3.6, size=(len(P), 2))
    lh, la = lam_m[S["mi"], 0], lam_m[S["mi"], 1]
    gol_tot = np.array([float(sum(p.ft)) for p in P])[S["mi"]]
    conf = CA.ConfA(nome="A*", emivita=3.0, forza=forza)
    leghe = np.array(sorted({p.league_id for p in P}))
    mod = CA.addestra_a(conf, S, idx, leghe, lh + la, 2025, gol_tot)
    atteso = CA.prevedi_a(mod, S, idx, lh + la)
    stati = {}
    for p in P:
        V4.aggiungi_partita_v4(stati.setdefault(str(p.league_id), V4.stato_lega_v4_vuoto(p.league_id)), p)
    beta = mod.beta if forza else {2: 0.0, 3: 0.0}
    blocco = V4.assembla_v4(stati, generated_at="2026-09-25T00:00:00+00:00", stagione_rif=2025, emivita=3.0,
                            beta=beta)
    atlas = {"meta": {"generated_at": "2026-09-25T00:00:00+00:00"}, "v4": blocco}
    campione = np.random.default_rng(2).choice(idx, 3000, replace=False)
    campione = np.concatenate([campione, np.flatnonzero(S["stop"] == 1)[:400]])
    for i in campione:
        c = V4.consulta_atlante_v4(atlas, int(S["m_live"][i]), int(S["gh"][i] + S["ga"][i]), int(S["lega"][i]),
                                   tempo=int(S["tempo"][i]), usa_cella_recupero_1t=True,
                                   lambda_home=float(lh[i]) if forza else None,
                                   lambda_away=float(la[i]) if forza else None)
        assert c["p_3min"] == pytest.approx(atteso["p3"][i], abs=2e-6)
        assert c["p_2min"] == pytest.approx(atteso["p2"][i], abs=2e-6)


def _atlas_semplice():
    P = _sintetico(n=700)
    stati = {}
    for p in P:
        V4.aggiungi_partita_v4(stati.setdefault(str(p.league_id), V4.stato_lega_v4_vuoto(p.league_id)), p)
    blocco = V4.assembla_v4(stati, generated_at="2026-09-25T00:00:00+00:00", stagione_rif=2025)
    return {"meta": {"generated_at": "2026-09-25T00:00:00+00:00", "n_fixtures_used": 700}, "v4": blocco}


def test_fasi_della_consultazione():
    atlas = _atlas_semplice()
    c = V4.consulta_atlante_v4(atlas, 93, 1, 39)
    assert c["fase"] == "recupero_2T" and c["recupero_atteso_min"] is not None
    c = V4.consulta_atlante_v4(atlas, 47, 1, 39, tempo=1)
    assert c["fase"] == "recupero_1T"
    # default: cella 40-45 della lega (la cella propria non e' validata)
    assert c["p"] == pytest.approx(V4.consulta_atlante_v4(atlas, 42, 1, 39)["p"])
    propria = V4.consulta_atlante_v4(atlas, 47, 1, 39, tempo=1, usa_cella_recupero_1t=True)
    assert propria["p"] != pytest.approx(c["p"])
    c = V4.consulta_atlante_v4(atlas, 47, 1, 39)
    assert c["fase"] == "regolare"          # senza tempo un 47' e' ripresa, come il v3
    c = V4.consulta_atlante_v4(atlas, 30, 0, 99999)
    assert c["fonte"] == "global" and c["p"] is not None


def test_recupero_2T_scende_col_tempo_giocato():
    atlas = _atlas_semplice()
    ps = [V4.consulta_atlante_v4(atlas, 90 + j, 1, 39)["p_3min"] for j in range(0, 10)]
    assert all(a >= b - 1e-12 for a, b in zip(ps, ps[1:]))
    assert ps[-1] < ps[0]


def test_forza_dichiarata_e_monotona():
    atlas = _atlas_semplice()
    senza = V4.consulta_atlante_v4(atlas, 60, 1, 39)
    # 25/09 notte: la forza non usata dichiara il MOTIVO (id squadra assenti)
    assert senza["forza"] == {"moltiplicatore": 1.0, "usata": False, "motivo": "id squadra assenti"}
    basso = V4.consulta_atlante_v4(atlas, 60, 1, 39, lambda_home=0.8, lambda_away=0.7)
    alto = V4.consulta_atlante_v4(atlas, 60, 1, 39, lambda_home=2.2, lambda_away=1.8)
    assert basso["forza"]["usata"] and alto["p"] > senza["p"] > basso["p"]
    assert "forza x" in alto["nota"]


def test_chiavi_come_consulta_atlante_e_ripiego_v3():
    from Betfair.stream.scalper.hazard_atlas import consulta_atlante
    atlas = _atlas_semplice()
    c = V4.consulta_atlante_v4(atlas, 60, 1, 39)
    chiavi_v3 = set(consulta_atlante(atlas, 60, 1, 39).keys())
    assert chiavi_v3 <= set(c.keys())
    solo_v3 = {"meta": {}, "global": {"60-65": {"1": {"p_goal_next_3min": 0.1, "p_goal_next_2min": 0.07,
                                                       "n": 100}}}}
    r = V4.consulta_atlante_v4(solo_v3, 62, 1, 39)
    assert r["versione"] == "v3" and r["p"] == 0.1


def test_ripieghi_dichiarati_senza_dati_di_recupero():
    """Senza durate del recupero (stagioni < 2024) e senza recupero 1T noto:
    recupero 2T = cella 85-90 della lega, recupero 1T = cella 40-45, dichiarati."""
    P = _sintetico(n=700)
    for p in P:
        p.d2, p.s1_vivo = None, 0
    stati = {}
    for p in P:
        V4.aggiungi_partita_v4(stati.setdefault(str(p.league_id), V4.stato_lega_v4_vuoto(p.league_id)), p)
    blocco = V4.assembla_v4(stati, generated_at="2026-09-25T00:00:00+00:00", stagione_rif=2025)
    atlas = {"meta": {"generated_at": "2026-09-25T00:00:00+00:00"}, "v4": blocco}
    assert blocco["meta"]["recupero_2T_noto"] is False
    assert ["90+0", "85-90"] in blocco["meta"]["ripieghi"] and ["45+", "40-45"] in blocco["meta"]["ripieghi"]
    for g in range(4):
        assert V4.consulta_atlante_v4(atlas, 93, g, 39)["p"] == pytest.approx(
            V4.consulta_atlante_v4(atlas, 87, g, 39)["p"])
        assert V4.consulta_atlante_v4(atlas, 46, g, 39, tempo=1)["p"] == pytest.approx(
            V4.consulta_atlante_v4(atlas, 42, g, 39)["p"])


def test_stagione_senza_recupero_registrato():
    """Reperto 25/09: gol di fine tempo senza minute_extra quasi sempre -> stagione
    non affidabile per la fine dei tempi; si contano solo gli stati t <= 41."""
    buoni = [_ev(i, i, 1, 90, 2) for i in range(8)] + [_ev(100, 100, 1, 90)]
    cattivi = [_ev(i, i, 1, 90) for i in range(8)] + [_ev(100, 100, 1, 45, 1)]
    assert V4.stagione_recupero_affidabile(buoni) is True
    assert V4.stagione_recupero_affidabile(cattivi) is False
    assert V4.stagione_recupero_affidabile(cattivi[:3]) is True       # troppo pochi per giudicare
    p, _ = V4.partita_v4(_match(1, 1, 0, extra=6), [_ev(1, 1, 1, 90)])
    st_ok, st_ko = V4.stato_lega_v4_vuoto(39), V4.stato_lega_v4_vuoto(39)
    V4.aggiungi_partita_v4(st_ok, p)
    V4.aggiungi_partita_v4(st_ko, p, recupero_affidabile=False)
    c_ok = np.asarray(st_ok["stagioni"]["2024"]["celle"]).reshape(V4.NT, V4.NG, 3)
    c_ko = np.asarray(st_ko["stagioni"]["2024"]["celle"]).reshape(V4.NT, V4.NG, 3)
    assert c_ok[:, :, 0].sum() == 96 and c_ko[:, :, 0].sum() == 84      # 2 x 42 stati
    assert c_ko[17, :, 0].sum() == 2 and c_ko[8, :, 0].sum() == 2        # solo t=40,41 del bucket
    assert st_ko["stagioni"]["2024"]["durate"] == {} and st_ko["stagioni"]["2024"]["n_fixtures"] == 1


def test_mai_eccezioni():
    rotto = {"meta": {}, "v4": {"meta": {}, "global": {}, "by_league": {"39": {"p3": "x"}}}}
    c = V4.consulta_atlante_v4(rotto, 60, 1, 39)
    assert c["p"] is None and "illeggibile" in c["nota"]
