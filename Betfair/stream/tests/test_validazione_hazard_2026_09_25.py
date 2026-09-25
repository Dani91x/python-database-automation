"""Banco di validazione dell'Atlante Hazard (25/09/2026): trasformazioni di
stato, verita' a 2'/3', recupero, metriche, lettore finto di A0, forza pre-partita.

Nessuna rete, nessun DB. I finti hanno le chiavi e i tipi VERI:
  matches      = ``raccogli.COLONNE_MATCH_BANCO`` (COLONNE_MATCH + status_elapsed,
                 extra, p1, p2 dal raw_json)
  match_events = ``COLONNE_GOL`` + player_id
  coverage     = league_id, season_year, fixtures_events
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pytest

from Betfair.stream.scalper import genera_atlante as G
from Betfair.stream.scalper.validazione_hazard import candidati as CA
from Betfair.stream.scalper.validazione_hazard import metriche as ME
from Betfair.stream.scalper.validazione_hazard import raccogli as RA
from Betfair.stream.scalper.validazione_hazard.dati import (Partita, costruisci_partite, lati_gol,
                                                            posizione)
from Betfair.stream.scalper.validazione_hazard.forza import lambda_prepartita
from Betfair.stream.scalper.validazione_hazard.produzione import LettoreCache, atlante_a0, predici_a0
from Betfair.stream.scalper.validazione_hazard.stati import stati_partita, tabella_stati


# ---------------------------------------------------------------- finti
def _match(fid: int, gh: int, ga: int, *, lid: int = 39, season: int = 2024, home: int = 1,
           away: int = 2, extra: Optional[int] = None, status: str = "FT",
           date: str = "2024-09-01T15:00:00+00:00") -> Dict[str, Any]:
    return {"fixture_id": fid, "league_id": lid, "season_year": season, "fixture_date": date,
            "status_short": status, "home_team_id": home, "home_team_name": f"T{home}",
            "away_team_id": away, "away_team_name": f"T{away}", "goals_home": gh, "goals_away": ga,
            "halftime_home": 0, "halftime_away": 0, "status_elapsed": 90, "extra": extra,
            "p1": 1723834800, "p2": 1723838400}


_EID = [1000]


def _ev(fid: int, team: int, minute: int, extra: Optional[int] = None, *, etype: str = "Goal",
        detail: str = "Normal Goal", lid: int = 39, season: int = 2024) -> Dict[str, Any]:
    _EID[0] += 1
    return {"id": _EID[0], "fixture_id": fid, "league_id": lid, "season_year": season,
            "team_id": team, "event_type": etype, "detail": detail, "minute": minute,
            "minute_extra": extra, "player_id": 7}


def _cov(lid: int = 39, seasons=(2023, 2024, 2025)) -> List[Dict[str, Any]]:
    return [{"league_id": lid, "season_year": s, "fixtures_events": True} for s in seasons]


def test_colonne_finti_uguali_al_raccoglitore():
    """Il finto di matches porta ESATTAMENTE le colonne che il raccoglitore chiede."""
    chieste = [c.split(":")[0] for c in RA.COLONNE_MATCH_BANCO.split(",")]
    assert sorted(chieste) == sorted(_match(1, 0, 0).keys())
    ev = [c for c in (G.COLONNE_GOL + ",player_id").split(",")]
    assert sorted(ev) == sorted(_ev(1, 1, 10).keys())


# ---------------------------------------------------------------- posizioni
@pytest.mark.parametrize("m,e,atteso", [
    (1, None, (1, 1)), (45, None, (1, 45)), (45, 2, (1, 47)), (46, None, (2, 1)),
    (90, None, (2, 45)), (90, 3, (2, 48)), (93, None, (2, 48)), (0, None, (1, 1)),
    (44, 1, (1, 44)),      # extra su un minuto non di fine tempo: ignorato
])
def test_posizione(m, e, atteso):
    assert posizione(m, e) == atteso


def test_posizione_minuto_assente():
    assert posizione(None, 2) is None


# ---------------------------------------------------------------- partite
def _partite(matches, eventi, cov=None):
    P, res = costruisci_partite(matches, eventi, cov if cov is not None else _cov())
    return P, res


def test_partita_gol_recupero_rossi_e_durate():
    m = _match(1, 2, 1, extra=6)
    ev = [_ev(1, 1, 45, 2), _ev(1, 2, 60), _ev(1, 1, 90, 4),
          _ev(1, 2, 30, etype="Card", detail="Red Card"),
          _ev(1, 1, 90, 7, etype="subst", detail="Substitution 5"),     # oltre l'extra: d2 = 7
          _ev(1, 2, 45, 3, etype="Card", detail="Yellow Card"),        # evento NON gol al 45+3
          _ev(1, 1, 45, 5, etype="Goal", detail="Missed Penalty")]     # non e' un gol, non e' vivo
    P, _ = _partite([m], ev)
    assert len(P) == 1
    p = P[0]
    assert p.gol == [(1, 47, "h"), (2, 15, "a"), (2, 49, "h")]
    assert p.rossi == [(1, 30, "a")]
    assert p.d2 == 7
    assert p.s1_vivo == 3


def test_extra_assente_o_sporco_d2_ignoto():
    # la terza partita (con gol ed eventi) tiene la stagione sopra la copertura del 60%
    P, _ = _partite([_match(1, 0, 0, extra=None), _match(2, 0, 0, extra=86), _match(3, 1, 0, extra=4)],
                    [_ev(1, 1, 10, etype="Card", detail="Yellow Card"),
                     _ev(2, 1, 10, etype="Card", detail="Yellow Card"), _ev(3, 1, 10)])
    assert [p.d2 for p in P] == [None, None, 4]


def test_stagione_prima_del_2024_niente_recupero_1T():
    m = _match(1, 0, 0, season=2023, extra=5)
    P, _ = _partite([m, _match(2, 1, 0, season=2023)],
                    [_ev(1, 1, 45, 3, etype="Card", detail="Yellow Card", season=2023),
                     _ev(2, 1, 10, season=2023)])
    assert P[0].s1_vivo == 0 and P[0].eventi_recupero is False


def test_regola_copertura_della_produzione():
    """Stagione con eventi su meno del 60% delle partite con gol: saltata (come bootstrap)."""
    ms = [_match(i, 1, 0) for i in range(1, 6)]
    ev = [_ev(1, 1, 10), _ev(2, 1, 10)]              # 2 su 5 = 40%
    P, res = _partite(ms, ev)
    assert P == [] and "39-2024" in res["stagioni_saltate_copertura"]
    ev += [_ev(3, 1, 10)]                            # 3 su 5 = 60%: entra
    P, _ = _partite(ms, ev)
    assert len(P) == 3                               # le 2 senza eventi: gol_diversi_dal_punteggio


def test_stagione_senza_flag_eventi_esclusa():
    P, res = _partite([_match(1, 1, 0)], [_ev(1, 1, 10)], cov=_cov(seasons=(2023,)))
    assert P == [] and [39, 2024] in res["stagioni_senza_eventi_coverage"]


def test_lati_gol_come_sequenza_partita_con_autogol():
    """Autogol registrato col team di chi l'ha segnato: stessa correzione della produzione."""
    m = _match(1, 1, 1)
    rows = [_ev(1, 1, 20), _ev(1, 1, 70, detail="Own Goal")]
    seq, motivo = G.sequenza_partita(m, rows)
    assert motivo == "ok"
    lati = lati_gol(m, rows)
    assert sorted([min(90, max(1, r["minute"])), l] for r, l in lati) == sorted(seq["goals"])
    assert [l for _, l in lati] == ["h", "a"]


def test_recupero_registrato_per_blocco_lega_mese():
    """Reperto 25/09 (stagione 2025 europea): gol di fine tempo senza extra."""
    from Betfair.stream.scalper.validazione_hazard.dati import recupero_registrato
    ms = [_match(i, 1, 0, date=f"2025-{9 if i < 10 else 3:02d}-10T15:00:00+00:00", season=2025)
          for i in range(20)]
    ev = [_ev(i, 1, 90, None if i < 10 else 3, season=2025) for i in range(20)]
    ok = recupero_registrato(ms, ev)
    assert [ok[i] for i in range(20)] == [False] * 10 + [True] * 10
    # blocco con pochi gol di fine tempo: si giudica sulla stagione (qui 10/20 = 0,5 -> no)
    ms.append(_match(99, 1, 0, date="2025-11-10T15:00:00+00:00", season=2025))
    ev.append(_ev(99, 1, 20, season=2025))
    assert recupero_registrato(ms, ev)[99] is False


# ---------------------------------------------------------------- stati e verita'
def _p(gol, rossi=(), d2=None, s1=0, season=2024) -> Partita:
    return Partita(fixture_id=1, league_id=39, season=season, date="2024-09-01", home_id=1, away_id=2,
                   home_name="A", away_name="B", ft=(0, 0), gol=list(gol), rossi=list(rossi), d2=d2,
                   s1_vivo=s1, eventi_recupero=season >= 2024)


def _riga(S, tempo, t):
    i = np.flatnonzero((S["tempo"] == tempo) & (S["t"] == t))
    assert i.size == 1
    return {k: int(v[i[0]]) for k, v in S.items()}


def test_verita_finestra_non_attraversa_l_intervallo():
    """Gol al 45+2 nella finestra di chi guarda al 44'; gol al 46' (2T) NO."""
    S = stati_partita(_p([(1, 47, "h"), (2, 1, "a")]), 0)
    r = _riga(S, 1, 44)
    assert r["y3"] == 1 and r["y2"] == 0          # 45+2 = posizione 47 = 44+3
    r = _riga(S, 1, 43)
    assert r["y3"] == 0                           # 44..46: il gol e' al 47
    S2 = stati_partita(_p([(2, 1, "a")]), 0)
    assert _riga(S2, 1, 44)["y3"] == 0            # il 46' e' nell'altro tempo
    assert _riga(S2, 2, 0)["y2"] == 1 and _riga(S2, 2, 0)["g1"] == 1


def test_stati_a_rischio_e_conteggi():
    S = stati_partita(_p([(1, 10, "h"), (2, 48, "a")], rossi=[(2, 5, "a")], d2=6, s1=2), 3)
    assert int(((S["tempo"] == 1) & (S["stop"] == 1)).sum()) == 2      # s1_vivo
    assert int(((S["tempo"] == 2) & (S["stop"] == 1)).sum()) == 6      # d2
    assert int((S["stop"] == 0).sum()) == 90
    r = _riga(S, 1, 10)
    assert (r["gh"], r["ga"]) == (1, 0)           # gol con posizione <= t
    assert _riga(S, 1, 9)["gh"] == 0
    r = _riga(S, 2, 47)                           # 90+2
    assert r["m_live"] == 92 and r["j"] == 2 and r["y2"] == 1 and r["ga"] == 0
    assert _riga(S, 2, 48)["ga"] == 1
    assert _riga(S, 2, 4)["ra"] == 0 and _riga(S, 2, 5)["ra"] == 1
    assert _riga(S, 1, 46)["m_live"] == 46        # recupero 1T: minuto live 45+j
    assert (S["mi"] == 3).all()


def test_minuti_dall_ultimo_gol():
    S = stati_partita(_p([(1, 10, "h")]), 0)
    assert _riga(S, 1, 9)["dal_gol"] == 99
    assert _riga(S, 1, 10)["dal_gol"] == 0
    assert _riga(S, 2, 5)["dal_gol"] == 40        # 45+5 - 10


def test_verita_col_metodo_dell_atlante_sui_minuti_regolari_lontani_dai_bordi():
    """Lontano dai bordi dei tempi la verita' del banco e' quella del generatore
    (``aggiungi_partita``: gol in (m, m+k]), minuto per minuto."""
    gol = [(1, 12, "h"), (1, 30, "a"), (2, 10, "h"), (2, 33, "h")]
    S = stati_partita(_p(gol), 0)
    minuti = [g[1] + 45 * (g[0] - 1) for g in gol]
    for tempo, t in [(1, x) for x in range(0, 42)] + [(2, x) for x in range(0, 42)]:
        m = t + 45 * (tempo - 1)
        r = _riga(S, tempo, t)
        assert r["y3"] == int(any(m < x <= m + 3 for x in minuti))
        assert r["y2"] == int(any(m < x <= m + 2 for x in minuti))


# ---------------------------------------------------------------- metriche
def test_logloss_brier_valori_noti():
    p = np.array([0.1, 0.9, 0.5])
    y = np.array([0, 1, 1])
    assert np.allclose(ME.logloss_vett(p, y), [-np.log(0.9), -np.log(0.9), -np.log(0.5)])
    assert np.allclose(ME.brier_vett(p, y), [0.01, 0.01, 0.25])


def test_auc_contro_sklearn_con_pareggi():
    from sklearn.metrics import roc_auc_score
    rng = np.random.default_rng(1)
    p = np.round(rng.random(500), 1)
    y = (rng.random(500) < p).astype(int)
    assert ME.auc(p, y) == pytest.approx(roc_auc_score(y, p), abs=1e-12)


def test_calibrazione_ed_ece():
    p = np.array([0.1] * 10 + [0.5] * 10)
    y = np.array([0] * 9 + [1] + [1] * 5 + [0] * 5)
    tab = ME.calibrazione(p, y, confini=[0.0, 0.3, 1.0])
    assert [(r["n"], r["osservata"]) for r in tab] == [(10, 0.1), (10, 0.5)]
    assert ME.errore_calibrazione(tab) == pytest.approx(0.0)


def test_bootstrap_per_partita():
    w = ME.ricampioni(50, 300)
    assert w.shape == (300, 50) and np.allclose(w.sum(1), 50)
    somme = np.arange(50, dtype=float)
    cnt = np.ones(50)
    stima, lo, hi = ME.ic_media(somme, cnt, w)
    assert stima == pytest.approx(24.5) and lo < stima < hi


# ---------------------------------------------------------------- A0 via produzione
def _dataset_a0():
    ms, ev = [], []
    rng = np.random.default_rng(7)
    fid = 1
    for s in (2023, 2024):
        for i in range(320):
            gh, ga = int(rng.integers(0, 3)), int(rng.integers(0, 3))
            ms.append(_match(fid, gh, ga, season=s, home=1 + i % 10, away=11 + i % 10))
            for _ in range(gh):
                ev.append(_ev(fid, 1 + i % 10, int(rng.integers(1, 91)), season=s))
            for _ in range(ga):
                ev.append(_ev(fid, 11 + i % 10, int(rng.integers(1, 91)), season=s))
            fid += 1
    return ms, ev


def test_lettore_cache_rifiuta_filtri_ignoti():
    L = LettoreCache([], [])
    with pytest.raises(ValueError):
        L.get("matches", {"league_id": "eq.1", "season_year": "eq.2024", "status_short": "eq.FT"})
    with pytest.raises(ValueError):
        L.get("standings", {})


def test_lettore_cache_filtra_come_postgrest():
    """Stessi filtri del vero: eq su lega/stagione, in su fixture_id, eq su event_type."""
    ms = [_match(1, 1, 0), _match(2, 0, 0, season=2023)]
    ev = [_ev(1, 1, 10), _ev(1, 2, 30, etype="Card", detail="Red Card"), _ev(2, 1, 5, etype="subst")]
    L = LettoreCache(ms, ev)
    assert [m["fixture_id"] for m in L.tutte("matches", {"league_id": "eq.39", "season_year": "eq.2024"},
                                              chiave="fixture_id")] == [1]
    righe = L.tutte("match_events", {"fixture_id": "in.(1,2)", "event_type": "eq.Goal"}, chiave="id")
    assert [(r["fixture_id"], r["event_type"]) for r in righe] == [(1, "Goal")]
    assert len(L.get("match_events", {"fixture_id": "in.(1,2)"})) == 3


def test_a0_col_lettore_cache_uguale_ai_conteggi_diretti():
    """A0 = bootstrap+assembla di produzione sul lettore finto: celle identiche
    a quelle di aggiungi_partita chiamato a mano sulle stesse partite."""
    ms, ev = _dataset_a0()
    atlas, stati = atlante_a0(LettoreCache(ms, ev), {39: [2023, 2024]})
    atteso = G.stato_lega_vuoto(39)
    for m in ms:
        seq, motivo = G.sequenza_partita(m, [e for e in ev if e["fixture_id"] == m["fixture_id"]])
        if seq:
            G.aggiungi_partita(atteso, seq)
    assert stati["39"]["cells"] == atteso["cells"]
    assert stati["39"]["n_fixtures"] == atteso["n_fixtures"] > 600


def test_predici_a0_usa_consulta_atlante_e_minuti_live():
    ms, ev = _dataset_a0()
    atlas, _ = atlante_a0(LettoreCache(ms, ev), {39: [2023, 2024]})
    P, _ = _partite(ms, ev)
    S = tabella_stati(P)
    idx = np.flatnonzero((S["tempo"] == 2) & (S["t"] == 40))[:5]
    pr = predici_a0(atlas, S, idx, P)
    for n, i in enumerate(idx):
        g = str(min(int(S["gh"][i] + S["ga"][i]), 3)).replace("3", "3+")
        cella = atlas["by_league"]["39"]["grid"]["85-90"][g]
        assert pr["p3"][n] == pytest.approx(cella["p_goal_next_3min"])
        assert pr["p2"][n] == pytest.approx(cella["p_goal_next_2min"])


# ---------------------------------------------------------------- famiglia A
def test_hazard_mult():
    p = np.array([0.1, 0.5])
    assert np.allclose(CA.hazard_mult(p, np.array([1.0, 1.0])), p)
    assert np.allclose(CA.hazard_mult(p, np.array([2.0, 2.0])), 1 - (1 - p) ** 2)


def _mod_recupero(r: float, pi: np.ndarray) -> CA.ModelloA:
    mod = CA.ModelloA(conf=CA.ConfA(), leghe=np.array([39]))
    mod.r_lega = np.full((1, CA.NG), r)
    mod.info["r_globale_per_gk"] = [r] * CA.NG
    mod.pi_lega = pi[None, :]
    mod.pi_pool = pi
    return mod


def test_recupero_distribuzione_media_oracolo():
    """D = 5 con certezza, r = 0.05/min: al 90+3 restano 2 minuti."""
    pi = np.zeros(CA.D_MAX + 1)
    pi[5] = 1.0
    mod = _mod_recupero(0.05, pi)
    li, gk, dk = np.array([0]), np.array([0]), np.array([2])
    for modo in ("distribuzione", "media"):
        p = CA._prevedi_recupero2(mod, li, gk, dk, np.array([3]), 3, modo)
        assert p[0] == pytest.approx(1 - np.exp(-0.05 * 2))
    p = CA._prevedi_recupero2(mod, li, gk, dk, np.array([0]), 3, "distribuzione")
    assert p[0] == pytest.approx(1 - np.exp(-0.05 * 3))
    p = CA._prevedi_recupero2(mod, li, gk, dk, np.array([3]), 3, "oracolo", np.array([9]))
    assert p[0] == pytest.approx(1 - np.exp(-0.05 * 3))
    # oracolo: recupero vero 5', al 90+3 restano 2 minuti
    p = CA._prevedi_recupero2(mod, li, gk, dk, np.array([3]), 3, "oracolo", np.array([5]))
    assert p[0] == pytest.approx(1 - np.exp(-0.05 * 2))


def test_media_condizionata_su_partita_viva():
    """D = 2 o 8 a meta', al 90+4: la media CONDIZIONATA del resto e' 4' (non 1')."""
    pi = np.zeros(CA.D_MAX + 1)
    pi[2] = pi[8] = 0.5
    mod = _mod_recupero(0.1, pi)
    p = CA._prevedi_recupero2(mod, np.array([0]), np.array([1]), np.array([2]), np.array([4]), 3, "media")
    assert p[0] == pytest.approx(1 - np.exp(-0.1 * 3))
    p = CA._prevedi_recupero2(mod, np.array([0]), np.array([1]), np.array([2]), np.array([7]), 3, "media")
    assert p[0] == pytest.approx(1 - np.exp(-0.1 * 1))


def test_recupero_condiziona_su_partita_viva():
    """D = 2 o 8 a meta': al 90+4 la partita e' viva, quindi D = 8 (4 minuti)."""
    pi = np.zeros(CA.D_MAX + 1)
    pi[2] = pi[8] = 0.5
    mod = _mod_recupero(0.1, pi)
    p = CA._prevedi_recupero2(mod, np.array([0]), np.array([1]), np.array([2]), np.array([4]), 3)
    assert p[0] == pytest.approx(1 - np.exp(-0.3))
    p = CA._prevedi_recupero2(mod, np.array([0]), np.array([1]), np.array([2]), np.array([0]), 3)
    atteso = 1 - (0.5 * np.exp(-0.1 * 2) + 0.5 * np.exp(-0.1 * 3))
    assert p[0] == pytest.approx(atteso)


def _sintetico(n=1500, seme=3, rate_rec=0.03):
    """Partite sintetiche con tasso di gol noto (0.03/min) e recupero 2T di 6'."""
    rng = np.random.default_rng(seme)
    P = []
    for i in range(n):
        gol = []
        for h in (1, 2):
            for t in range(1, 46):
                if rng.random() < 0.028:
                    gol.append((h, t, "h" if rng.random() < 0.55 else "a"))
        for j in range(1, 7):
            if rng.random() < rate_rec:
                gol.append((2, 45 + j, "h"))
        p = Partita(fixture_id=i, league_id=39, season=2023 + (i % 2), date="2024-01-01", home_id=1,
                    away_id=2, home_name="A", away_name="B", ft=(0, 0), gol=sorted(gol), d2=6,
                    s1_vivo=0, eventi_recupero=True)
        P.append(p)
    return P


def test_a1_ritrova_tassi_noti_nel_recupero():
    P = _sintetico()
    S = tabella_stati(P)
    idx = np.arange(S["y3"].size)
    lam = np.full(len(P), 2.5)[S["mi"]]
    mod = CA.addestra_a(CA.ConfA(k=10.0), S, idx, np.array([39]), lam, 2025)
    assert mod.info["durata_media_pool"] == pytest.approx(6.0)
    r = np.array(mod.info["r_globale_per_gk"])
    assert np.average(r, weights=np.bincount(np.minimum(S["gh"] + S["ga"], 3)[S["stop"] == 1],
                                             minlength=4)) == pytest.approx(0.03, abs=0.006)
    pr = CA.prevedi_a(mod, S, idx, lam)
    reg = S["stop"] == 0
    assert pr["p3"][reg].mean() == pytest.approx(S["y3"][reg].mean(), abs=0.004)


def test_pesi_stagione():
    w = CA.pesi_stagione(np.array([2025, 2023, 2021]), 2025, 2.0)
    assert np.allclose(w, [1.0, 0.5, 0.25])
    assert np.allclose(CA.pesi_stagione(np.array([2020]), 2025, None), [1.0])


def test_celle_tempo():
    S = {"stop": np.array([0, 0, 1, 1, 1, 1]), "tempo": np.array([1, 2, 1, 2, 2, 2]),
         "j": np.array([0, 0, 3, 0, 7, 12]), "m_live": np.array([44, 89, 48, 90, 97, 102])}
    tc = CA.cella_tempo(S, np.arange(6))
    assert tc.tolist() == [8, 17, CA.TC_REC1, CA.TC_REC2, CA.TC_REC2 + 6, CA.TC_REC2 + 7]


# ---------------------------------------------------------------- forza pre-partita
def test_forza_non_sbircia_il_risultato():
    base = [Partita(fixture_id=i, league_id=39, season=2024, date=f"2024-01-{i + 1:02d}", home_id=i % 2 + 1,
                    away_id=2 - i % 2, home_name=None, away_name=None, ft=(1, 1)) for i in range(6)]
    lam1 = lambda_prepartita(base)
    base[3].ft = (7, 0)
    lam2 = lambda_prepartita(base)
    for i in range(4):
        assert lam1[i][:2] == lam2[i][:2]      # fino alla partita stessa: identici
    assert lam1[4][:2] != lam2[4][:2]           # dopo: il risultato conta
