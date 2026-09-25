"""Atlante v4 A* COMPLETO: forza pre-partita dagli id squadra (25/09/2026 notte).

Ordine dell'utente ("D2: collegalo" = A* completo). Cosa si prova (nessuna
rete, nessun DB vero):
  1. PARITA' col banco: stesse righe del DB -> generatore di produzione
     (bootstrap + assembla, lettore PostgREST finto) -> ``consulta_atlante_v4``
     con gli id squadra, contro il candidato validato A* (``candidati`` A1+A2
     emivita 3 + A5 forza, coi lambda del proxy ``forza.lambda_prepartita``):
     stessi lambda e stessi p (<= 1e-6) sulla PROSSIMA partita fra due squadre.
  2. Incrementale (generatore a lotti e motore a domanda): stessi rating del
     bootstrap intero, ordine cronologico anche se il DB legge per fixture_id,
     nessun doppio conteggio; partita vecchia fuori ordine saltata e contata;
     stato v4 senza forza non adottato (si ricalcola).
  3. Consumatori: Safe (id dalla fixture abbinata o dalla finestra GIA' in
     cache, nel payload che arriva a ``_hazard_check``; zero letture in piu') e
     Mike (id dalla stessa riga di fixture_predictions nel dossier); forza
     usata e dichiarata, "forza non usata: id squadra assenti" senza id; gli id
     non arrivano al ripiego v3; soglie/decisioni invariate.
I finti hanno le chiavi e i tipi del vero: righe ``matches`` con ``raw_json``
(API-Football) e le colonne vere; righe fixture con le colonne che
``omega_db.fixtures_for_window`` seleziona; tupla di ``get_fixture_prematch_lambdas``.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pytest

from Betfair.stream.scalper import atlante_v4 as V4
from Betfair.stream.scalper import genera_atlante as G
from Betfair.stream.scalper.validazione_hazard import candidati as CA
from Betfair.stream.scalper.validazione_hazard import raccogli as RA
from Betfair.stream.scalper.validazione_hazard.dati import Partita, costruisci_partite
from Betfair.stream.scalper.validazione_hazard.forza import lambda_prepartita
from Betfair.stream.scalper.validazione_hazard.stati import tabella_stati
from Betfair.stream.tests.test_atlante_a_domanda_2026_09_25 import (T0, DBFinto, _cov, _fp,  # noqa: F401
                                                                    _motore, cartella)
from Betfair.stream.tests.test_atlante_v4_collegato_2026_09_25 import IPS_2T_REC_93, _ips
from Betfair.stream.tests.test_genera_atlante_2026_09_24 import LettoreFinto, seleziona

ADESSO = "2026-09-25T22:00:00+00:00"
SQUADRE = {39: list(range(1001, 1017)), 140: list(range(2001, 2017))}   # id API-Football DISGIUNTI
STAGIONI = (2021, 2022, 2023, 2024)
MINUTI_GOL = [m for m in range(1, 90) if m != 45]


# --------------------------------------------------------------- righe DB
def _riga_match(fid: int, lid: int, season: int, hid: int, aid: int, gh: int, ga: int,
                extra: Optional[int], data: str) -> Dict[str, Any]:
    """Riga di ``matches`` con le colonne vere e ``raw_json`` di API-Football."""
    return {"fixture_id": fid, "league_id": lid, "season_year": season, "fixture_date": data,
            "status_short": "FT", "status_elapsed": 90, "home_team_id": hid,
            "home_team_name": f"Squadra {hid}", "away_team_id": aid, "away_team_name": f"Squadra {aid}",
            "goals_home": gh, "goals_away": ga, "halftime_home": 0, "halftime_away": 0,
            "raw_json": {"fixture": {"id": fid, "periods": {"first": 1, "second": 2},
                                     "status": {"long": "Match Finished", "short": "FT", "elapsed": 90,
                                                "extra": extra}},
                         "teams": {"home": {"id": hid, "name": f"Squadra {hid}"},
                                   "away": {"id": aid, "name": f"Squadra {aid}"}}}}


def _riga_evento(eid: int, fid: int, lid: int, season: int, team: int, minute: int,
                 tipo: str = "Goal", detail: str = "Normal Goal") -> Dict[str, Any]:
    return {"id": eid, "fixture_id": fid, "league_id": lid, "season_year": season, "team_id": team,
            "event_type": tipo, "detail": detail, "minute": minute, "minute_extra": None,
            "player_id": 7}


def _righe_forza(seme: int = 11, stagioni=STAGIONI, leghe=SQUADRE) -> Dict[str, List[Dict[str, Any]]]:
    """Leghe a girone: squadre con forze VERE diverse (i gol le rivelano),
    date in ordine di giornata ma fixture_id MESCOLATI (il DB legge per
    fixture_id: l'ordine cronologico lo deve ricostruire il generatore).
    Ogni partita ha un giallo (evento non-gol: l'incrementale del generatore
    trova la partita dagli eventi, anche gli 0-0). Id evento crescenti per
    stagione (la filigrana dell'incrementale separa le stagioni)."""
    rng = np.random.default_rng(seme)
    att = {t: rng.normal(0, 0.3) for ts in leghe.values() for t in ts}
    dif = {t: rng.normal(0, 0.25) for ts in leghe.values() for t in ts}
    matches: List[Dict[str, Any]] = []
    eventi: List[Dict[str, Any]] = []
    eid = 1
    for s in stagioni:
        per_stagione = []
        for lid, ts in leghe.items():
            giorno = date(s, 8, 1) + timedelta(days=int(lid == 140))
            coppie = [(h, a) for h in ts for a in ts if h != a]
            rng.shuffle(coppie)
            for k, (h, a) in enumerate(coppie):
                d = giorno + timedelta(days=7 * (k // 8))
                per_stagione.append((lid, h, a, d))
        fids = rng.permutation(len(per_stagione)) + 100000 + 1000 * (s - 2000)
        for (lid, h, a, d), fid in zip(per_stagione, fids):
            gh = int(rng.poisson(1.45 * np.exp(att[h] + dif[a])))
            ga = int(rng.poisson(1.15 * np.exp(att[a] + dif[h])))
            d2 = int(rng.integers(3, 10))
            matches.append(_riga_match(int(fid), lid, s, h, a, gh, ga, d2, f"{d.isoformat()}T15:00:00+00:00"))
            for team, n in ((h, gh), (a, ga)):
                for _ in range(n):
                    # niente gol al 45'/90' (senza minute_extra la stagione sarebbe "recupero
                    # non registrato", reperto 6: regola della produzione che il banco non ha)
                    mi = int(rng.choice(MINUTI_GOL))
                    eventi.append(_riga_evento(eid, int(fid), lid, s, team, mi))
                    eid += 1
            eventi.append(_riga_evento(eid, int(fid), lid, s, h, 30, "Card", "Yellow Card"))
            eid += 1
    cov = [{"league_id": l, "season_year": s, "fixtures_events": True} for l in leghe for s in stagioni]
    return {"matches": matches, "match_events": eventi, "coverage": cov}


def _solo_gol(righe):
    return [e for e in righe["match_events"] if e["event_type"] == "Goal"]


def _bootstrap(righe, stagioni=STAGIONI, leghe=tuple(SQUADRE)) -> Dict[str, Dict[str, Any]]:
    lettore = LettoreFinto({"matches": righe["matches"], "match_events": righe["match_events"]})
    stati: Dict[str, Dict[str, Any]] = {}
    for lid in leghe:
        G.bootstrap(lettore, stati, [lid], list(stagioni), {}, ADESSO)
    return stati


def _partite_banco(righe):
    m_banco = [seleziona(m, RA.COLONNE_MATCH_BANCO) for m in righe["matches"]]
    partite, _ = costruisci_partite(m_banco, righe["match_events"], righe["coverage"], stagione_max=2025)
    return partite


def _lam_banco(partite):
    # valori LETTERALI del banco (risultati_validazione.json forza.scelta, corsa
    # COMPLETA 25/09: AUDIT_2026-09-25/LIVE_MARKET_TYPES_E_BETA.md), non le
    # costanti di produzione
    return lambda_prepartita(partite, eta=0.015, rientro=1.0, alfa_lega=0.01)


def _prossima(partite, lid, h, a):
    """lambda del BANCO per la prossima partita h-a (dopo tutto lo storico)."""
    nuova = Partita(fixture_id=9_999_999, league_id=lid, season=2025, date="2025-12-31", home_id=h,
                    away_id=a, home_name=None, away_name=None, ft=(0, 0))
    return _lam_banco(partite + [nuova])[9_999_999][:2]


@pytest.fixture(scope="module")
def banco():
    righe = _righe_forza()
    stati = _bootstrap(righe)
    atlas = G.assembla(stati, generated_at=ADESSO)
    partite = _partite_banco(righe)
    lam = _lam_banco(partite)
    S = tabella_stati(partite)
    idx = np.arange(S["y3"].size)
    lh = np.array([lam[p.fixture_id][0] for p in partite])[S["mi"]]
    la = np.array([lam[p.fixture_id][1] for p in partite])[S["mi"]]
    gol_tot = np.array([float(sum(p.ft)) for p in partite])[S["mi"]]
    leghe = np.array(sorted({p.league_id for p in partite}))
    mod = CA.addestra_a(CA.ConfA(nome="A*", emivita=V4.EMIVITA, forza=True), S, idx, leghe, lh + la, 2025,
                        gol_tot)
    return {"righe": righe, "stati": stati, "atlas": atlas, "partite": partite, "S": S, "mod": mod}


def _con_beta(atlas, beta) -> Dict[str, Any]:
    """Il blocco v4 del generatore col beta stimato dal banco su QUESTI dati
    (in produzione beta e' ``BETA_DEFAULT``, stimato dal banco sul DB vero)."""
    a = json.loads(json.dumps(atlas))
    a["v4"]["meta"]["beta"] = {str(k): float(v) for k, v in beta.items()}
    return {"meta": a["meta"], "v4": a["v4"]}


# ------------------------------------------------ 1) PARITA' col banco
def test_parita_lambda_forza_col_proxy_del_banco(banco):
    """I rating nel blocco v4 danno, per la prossima partita fra due squadre,
    gli STESSI lambda di ``forza.lambda_prepartita`` del banco."""
    blocco = banco["atlas"]["v4"]["by_league"]
    diff = 0.0
    for lid, ts in SQUADRE.items():
        fz = blocco[str(lid)]["forza"]
        assert fz["n"] == sum(1 for p in banco["partite"] if p.league_id == lid) == 4 * 240
        assert set(fz["squadre"]) == {str(t) for t in ts}
        for h, a in ((ts[0], ts[1]), (ts[5], ts[2]), (ts[-1], ts[3]), (ts[7], ts[-2])):
            lb = _prossima(banco["partite"], lid, h, a)
            lp = V4.lambda_da_forza(fz, h, a)[:2]
            diff = max(diff, abs(lb[0] - lp[0]), abs(lb[1] - lp[1]))
    assert diff <= 1e-6, diff
    # lo STATO grezzo (non arrotondato) e' identico al banco al bit
    st = banco["stati"]["39"]["v4"]["forza"]
    lb = _prossima(banco["partite"], 39, 1001, 1002)
    assert V4.lambda_da_forza(st, 1001, 1002)[:2] == pytest.approx(lb, abs=1e-12)


def test_parita_p_astar_col_candidato_validato(banco):
    """Stessi stati, stessa prossima partita: ``consulta_atlante_v4`` con gli
    id squadra = A* del banco (A1+A2+A5 coi lambda del proxy), <= 1e-6."""
    S, mod = banco["S"], banco["mod"]
    assert mod.beta[2] > 0 and mod.beta[3] > 0
    atlas = _con_beta(banco["atlas"], mod.beta)
    rng = np.random.default_rng(4)
    diff = 0.0
    usate = 0
    for lid, ts in SQUADRE.items():
        h, a = ts[3], ts[9]
        lh, la = _prossima(banco["partite"], lid, h, a)
        lam_tot = np.full(S["y3"].size, lh + la)
        reg = np.flatnonzero((S["lega"] == lid) & (S["stop"] == 0))
        rec2 = np.flatnonzero((S["lega"] == lid) & (S["stop"] == 1) & (S["tempo"] == 2))
        assert rec2.size > 100
        sel = np.concatenate([rng.choice(reg, 700, replace=False), rec2[:200]])
        atteso = CA.prevedi_a(mod, S, sel, lam_tot)
        for n, i in enumerate(sel):
            c = V4.consulta_atlante_v4(atlas, int(S["m_live"][i]), int(S["gh"][i] + S["ga"][i]), lid,
                                       tempo=int(S["tempo"][i]), home_id=h, away_id=a)
            assert c["versione"] == "v4" and c["forza"]["usata"] and c["forza"]["fonte"] == "poisson_elo"
            usate += 1
            diff = max(diff, abs(c["p_3min"] - atteso["p3"][n]), abs(c["p_2min"] - atteso["p2"][n]))
    assert usate == 1800
    assert diff <= 1e-6, diff


def test_forza_cambia_il_p_e_senza_id_e_A1_A2(banco):
    """Con la forza il p si muove (squadre forti > deboli); senza id e' il
    p di A1+A2 e la nota lo dice."""
    atlas = _con_beta(banco["atlas"], banco["mod"].beta)
    fz = atlas["v4"]["by_league"]["39"]["forza"]
    # partite "da gol": attacco alto (log_att) E difesa che concede (log_dif alto)
    ordine = sorted(SQUADRE[39], key=lambda t: fz["squadre"][str(t)][0] + fz["squadre"][str(t)][1])
    debole, forte = ordine[0], ordine[-1]
    senza = V4.consulta_atlante_v4(atlas, 60, 1, 39, tempo=2)
    alto = V4.consulta_atlante_v4(atlas, 60, 1, 39, tempo=2, home_id=forte, away_id=ordine[-2])
    basso = V4.consulta_atlante_v4(atlas, 60, 1, 39, tempo=2, home_id=debole, away_id=ordine[1])
    assert alto["p"] > senza["p"] > basso["p"]
    assert senza["forza"] == {"moltiplicatore": 1.0, "usata": False, "motivo": "id squadra assenti"}
    assert "storico v4 (A1+A2)" in senza["nota"] and "forza non usata: id squadra assenti" in senza["nota"]
    assert "storico v4 (A*)" in alto["nota"]
    casa = alto["forza"]["casa"]
    tr = alto["forza"]["trasferta"]
    testo = f"forza usata: casa {casa:.2f} / trasferta {tr:.2f}".replace(".", ",")
    assert V4.testo_forza(alto) == testo and testo in alto["nota"]
    # casa/trasferta = lambda / gol medi casa-trasferta della lega (mu del Poisson-Elo)
    mu = fz["mu"]
    assert casa == pytest.approx(alto["forza"]["lambda_casa"] / mu[0], abs=1e-3)
    assert tr == pytest.approx(alto["forza"]["lambda_trasferta"] / mu[1], abs=1e-3)
    assert V4.etichetta_versione(alto) == "atlante v4 (A*)"
    assert V4.etichetta_versione(senza) == "atlante v4 (A1+A2)"


def test_motivi_della_forza_non_usata(banco):
    atlas = _con_beta(banco["atlas"], banco["mod"].beta)
    # lega fuori dal v4: niente forze (e nessuna eccezione)
    c = V4.consulta_atlante_v4(atlas, 60, 1, 999, tempo=2, home_id=1001, away_id=1002)
    assert c["forza"]["usata"] is False and c["forza"]["motivo"] == "lega non nel v4: forze squadra assenti"
    # lega del v4 senza forze (stato di prima)
    senza_fz = json.loads(json.dumps(atlas))
    senza_fz["v4"]["by_league"]["39"]["forza"] = None
    c = V4.consulta_atlante_v4(senza_fz, 60, 1, 39, tempo=2, home_id=1001, away_id=1002)
    assert c["forza"]["motivo"] == "forze squadra della lega non ancora calcolate"
    assert c["p"] == V4.consulta_atlante_v4(atlas, 60, 1, 39, tempo=2)["p"]
    # un solo id: non basta
    c = V4.consulta_atlante_v4(atlas, 60, 1, 39, tempo=2, home_id=1001, away_id=None)
    assert c["forza"]["usata"] is False and "id squadra assenti" in c["nota"]
    # squadra mai vista nella lega (neopromossa): rating neutro come nel banco, DICHIARATO
    c = V4.consulta_atlante_v4(atlas, 60, 1, 39, tempo=2, home_id=777777, away_id=1002)
    lb = _prossima(banco["partite"], 39, 777777, 1002)
    assert c["forza"]["usata"] and c["forza"]["senza_storico"] == ["casa"]
    assert c["forza"]["lambda_casa"] == pytest.approx(lb[0], abs=1e-4)
    assert "casa senza storico in lega: neutra" in c["nota"]


def test_id_squadra_non_arrivano_al_ripiego_v3(banco):
    """Il livello squadre del v3 peggiora le previsioni (referto, A0_squadre):
    gli id li consuma il v4, il ripiego v3 resta quello di ieri."""
    from Betfair.stream.scalper.hazard_atlas import consulta_atlante
    atl = json.loads(json.dumps(banco["atlas"]))
    atl.pop("v4")
    con_id = consulta_atlante(atl, 60, 1, 39, home_id=1001, away_id=1002)
    assert con_id["fonte"] == "team"                  # il v3 CON gli id userebbe le squadre
    c = V4.consulta_atlante_v4(atl, 60, 1, 39, tempo=2, home_id=1001, away_id=1002)
    assert c["versione"] == "v3" and c["fonte"] == "league"
    assert c["p"] == consulta_atlante(atl, 60, 1, 39)["p"]
    assert c["forza"] == {"moltiplicatore": 1.0, "usata": False, "motivo": "ripiego sul v3"}
    # secondo ramo del ripiego (falsificazione F9, giro 1 VERDE): blocco v4 presente
    # ma lega 39 non ancora nel v4 -> v3 per la lega, sempre SENZA gli id
    parz = json.loads(json.dumps(banco["atlas"]))
    parz["v4"]["by_league"].pop("39")
    c = V4.consulta_atlante_v4(parz, 60, 1, 39, tempo=2, home_id=1001, away_id=1002)
    assert c["versione"] == "v3" and c["ripiego_v3"] == "lega 39 non ancora nel v4"
    assert c["fonte"] == "league" and c["p"] == consulta_atlante(parz, 60, 1, 39)["p"]


# ------------------------------------------ 2) incrementale e ordine
def _forza(stati, lid="39"):
    return stati[lid]["v4"]["forza"]


def test_incrementale_generatore_a_lotti_uguale_al_bootstrap_e_idempotente():
    """2021-2023 dal bootstrap, 2024 dall'incrementale (eventi id > filigrana,
    lotti da 37 fixture_id MESCOLATI rispetto alle date): stessi rating del
    bootstrap intero; un secondo giro non conta nulla due volte."""
    righe = _righe_forza(seme=3)
    intero = _bootstrap(righe)
    vecchie = [m for m in righe["matches"] if m["season_year"] <= 2023]
    fid_v = {m["fixture_id"] for m in vecchie}
    ev_v = [e for e in righe["match_events"] if e["fixture_id"] in fid_v]
    stati = _bootstrap({"matches": vecchie, "match_events": ev_v}, stagioni=(2021, 2022, 2023))
    wm = max(e["id"] for e in ev_v)
    lettore = LettoreFinto({"matches": righe["matches"], "match_events": righe["match_events"]})
    nuova, conti, toccate = G.incrementale(lettore, stati, wm, {}, ADESSO, lotto=37)
    assert conti["aggiunte"] == 2 * 240 and sorted(toccate) == ["140", "39"]
    for lid in ("39", "140"):
        a, b = _forza(stati, lid), _forza(intero, lid)
        assert a["n"] == b["n"] and a["fuori_ordine"] == 0 and a["ultima"] == b["ultima"]
        assert a["mu"] == pytest.approx(b["mu"], abs=1e-12)
        for t, v in b["squadre"].items():
            assert a["squadre"][t][:2] == pytest.approx(v[:2], abs=1e-12)
    prima = json.dumps(_forza(stati))
    _, conti2, _ = G.incrementale(lettore, stati, wm, {}, ADESSO, lotto=37)
    assert conti2["aggiunte"] == 0 and conti2["gia_contate"] == 2 * 240
    assert json.dumps(_forza(stati)) == prima          # nessun doppio conteggio


class _LettoreCheSiRompe(LettoreFinto):
    """Il DB cade alla N-esima lettura di ``matches`` (ritentativi esauriti)."""

    def __init__(self, tabelle, rompi_a: int):
        super().__init__(tabelle)
        self.rompi_a, self.n_matches = rompi_a, 0

    def get(self, table, params):
        if table == "matches":
            self.n_matches += 1
            if self.n_matches >= self.rompi_a:
                raise RuntimeError("DB giu'")
        return super().get(table, params)


def test_incrementale_che_si_rompe_non_perde_la_forza_delle_partite_contate():
    """Un lotto contato nel v3/v4 entra nei rating anche se il lotto dopo cade."""
    righe = _righe_forza(seme=3, leghe={39: SQUADRE[39]})
    vecchie = [m for m in righe["matches"] if m["season_year"] <= 2023]
    fid_v = {m["fixture_id"] for m in vecchie}
    ev_v = [e for e in righe["match_events"] if e["fixture_id"] in fid_v]
    stati = _bootstrap({"matches": vecchie, "match_events": ev_v}, stagioni=(2021, 2022, 2023), leghe=(39,))
    n0 = _forza(stati)["n"]
    lettore = _LettoreCheSiRompe({"matches": righe["matches"], "match_events": righe["match_events"]}, 2)
    with pytest.raises(RuntimeError):
        G.incrementale(lettore, stati, max(e["id"] for e in ev_v), {}, ADESSO, lotto=37)
    contate = stati["39"]["v4"]["stagioni"]["2024"]["n_fixtures"]
    assert contate > 0 and _forza(stati)["n"] == n0 + contate


def test_bootstrap_ordina_per_data_non_per_fixture_id():
    """Il DB restituisce la stagione per fixture_id; i rating seguono la DATA
    (poi il fixture_id), come il banco."""
    righe = _righe_forza(seme=5, stagioni=(2023,), leghe={39: SQUADRE[39]})
    stati = _bootstrap(righe, stagioni=(2023,), leghe=(39,))
    fz = _forza(stati)
    assert fz["fuori_ordine"] == 0 and fz["n"] == 240
    ultima = max((m["fixture_date"][:10], m["fixture_id"]) for m in righe["matches"])
    assert fz["ultima"] == [ultima[0], ultima[1]]
    # applicate per fixture_id (l'ordine di lettura) i rating sarebbero diversi
    v4 = {"forza": V4.forza_vuota()}
    for m in sorted(righe["matches"], key=lambda r: r["fixture_id"]):
        p, _ = V4.partita_v4(seleziona(m, G.COLONNE_MATCH),
                             [e for e in _solo_gol(righe) if e["fixture_id"] == m["fixture_id"]])
        V4.aggiungi_forza(v4, p)
    assert v4["forza"]["fuori_ordine"] > 0
    assert v4["forza"]["squadre"]["1001"][0] != pytest.approx(fz["squadre"]["1001"][0], abs=1e-9)


def test_partita_fuori_ordine_recente_applicata_vecchia_saltata():
    v4 = {"forza": V4.forza_vuota()}

    def _p(fid, d, h=1, a=2, s=2025):
        return Partita(fixture_id=fid, league_id=39, season=s, date=d, home_id=h, away_id=a,
                       home_name=None, away_name=None, ft=(2, 1))
    assert V4.aggiungi_forza(v4, _p(10, "2025-10-20"))
    assert V4.aggiungi_forza(v4, _p(11, "2025-10-05", 3, 4))            # 15 gg indietro: applicata
    fz = v4["forza"]
    assert fz["fuori_ordine"] == 1 and fz["saltate"] == 0 and fz["n"] == 2
    assert fz["ultima"] == ["2025-10-20", 10]
    prima = json.dumps(fz)
    assert not V4.aggiungi_forza(v4, _p(12, "2024-03-01", 5, 6, 2023))  # stagione vecchia: saltata
    assert fz["saltate"] == 1 and fz["fuori_ordine"] == 2
    dopo = json.loads(json.dumps(fz))
    dopo["fuori_ordine"], dopo["saltate"] = 1, 0
    assert json.dumps(dopo) == prima                                    # rating e mu intatti
    # stato v4 SENZA forza (di prima): non si completa a pezzi
    assert V4.aggiungi_forza({"stagioni": {}}, _p(13, "2025-10-21")) is False


def test_motore_a_domanda_incrementale_aggiorna_la_forza_come_il_bootstrap(cartella):
    """Il motore a domanda: lega calcolata dal DB, poi partite nuove finite
    nella finestra -> rating aggiornati come se il bootstrap le avesse viste;
    un giro dopo, nessun doppio conteggio."""
    righe = _righe_forza(seme=7, stagioni=(2023, 2024), leghe={39: SQUADRE[39]})
    ko ="2026-09-25T09:00:00+00:00"
    nuove = [_riga_match(9102, 39, 2025, 1001, 1002, 2, 0, 5, ko),
             _riga_match(9101, 39, 2025, 1003, 1004, 1, 1, 6, ko),
             _riga_match(9100, 39, 2025, 1005, 1006, 0, 0, 7, ko)]
    ev_nuovi = [_riga_evento(900001, 9102, 39, 2025, 1001, 10), _riga_evento(900002, 9102, 39, 2025, 1001, 70),
                _riga_evento(900003, 9101, 39, 2025, 1003, 20), _riga_evento(900004, 9101, 39, 2025, 1004, 80),
                _riga_evento(900005, 9100, 39, 2025, 1005, 33, "Card", "Yellow Card")]
    db = DBFinto({"fixture_predictions": [_fp(f, 39, T0 - 3 * 3600) for f in (9100, 9101, 9102)],
                  "api_coverage_by_season": [_cov(39, s, True) for s in (2023, 2024, 2025)],
                  "matches": list(righe["matches"]), "match_events": list(righe["match_events"])})
    ora = [T0]
    m = _motore(db, cartella, ora)
    m.ciclo()
    assert m._ha_v4("39") and m.leghe["39"]["v4"]["forza"]["n"] == 2 * 240
    db.tabelle["matches"] = righe["matches"] + nuove
    db.tabelle["match_events"] = righe["match_events"] + ev_nuovi
    ora[0] = T0 + 3700
    r = m.ciclo()
    assert r["incrementale"]["aggiunte"] == 3
    fz = m.leghe["39"]["v4"]["forza"]
    atteso = _bootstrap({"matches": righe["matches"] + nuove, "match_events": righe["match_events"] + ev_nuovi},
                        stagioni=(2023, 2024, 2025), leghe=(39,))
    fa = _forza(atteso)
    assert fz["n"] == fa["n"] == 2 * 240 + 3 and fz["ultima"] == fa["ultima"] == ["2026-09-25", 9102]
    for t, v in fa["squadre"].items():
        assert fz["squadre"][t][:2] == pytest.approx(v[:2], abs=1e-12)
    live = json.load(open(cartella["live"], encoding="utf-8"))
    assert live["v4"]["by_league"]["39"]["forza"]["n"] == 2 * 240 + 3
    ora[0] = T0 + 7400
    m.ciclo()
    assert m.leghe["39"]["v4"]["forza"]["n"] == 2 * 240 + 3


def test_stato_v4_senza_forza_non_si_adotta_si_ricalcola(cartella):
    righe = _righe_forza(seme=9, stagioni=(2024,), leghe={39: SQUADRE[39]})
    stati = _bootstrap(righe, stagioni=(2024,), leghe=(39,))
    vecchio = json.loads(json.dumps(stati["39"]))
    vecchio["v4"].pop("forza")                       # stato v4 scritto fra 1ba167e e oggi
    fixtures = vecchio.pop("fixtures")
    db = DBFinto({"fixture_predictions": [_fp(9901, 39, T0 + 3600)],
                  "api_coverage_by_season": [_cov(39, 2024, True)],
                  "matches": righe["matches"], "match_events": righe["match_events"],
                  "hazard_atlas_leghe": [{"league_id": 39, "stato": vecchio, "fixtures": fixtures}]})
    m = _motore(db, cartella, [T0])
    assert m.prepara_lega("39", T0) == "calcolata"
    assert m.leghe["39"]["v4"]["forza"]["n"] == 240
    m2 = _motore(db, cartella, [T0])
    m2._caricato = True
    m2.leghe = {"39": dict(vecchio, fixtures=fixtures)}
    assert not m2._ha_v4("39")
    assert m2.ciclo()["preparate"] == {"39": "calcolata"} and m2._ha_v4("39")
    # nel frattempo un v4 senza forza non si rompe: forza dichiarata assente
    G.aggiungi_v4(vecchio, seleziona(righe["matches"][0], G.COLONNE_MATCH), [])
    assert "forza" not in vecchio["v4"]
    atl = G.assembla({"39": dict(vecchio, fixtures=fixtures)}, generated_at=ADESSO)
    assert atl["v4"]["by_league"]["39"]["forza"] is None


def test_blocco_forza_nel_file_live_piccolo(banco):
    """Costo nel file live: la forza di una lega da 16 squadre sta sotto i 2 KB."""
    fz = banco["atlas"]["v4"]["by_league"]["39"]["forza"]
    assert len(json.dumps(fz)) < 2048
    assert banco["atlas"]["v4"]["meta"]["forza"]["n_leghe_con_forza"] == 2
    assert banco["atlas"]["v4"]["meta"]["forza"]["eta"] == V4.FORZA_ETA == 0.015


# ------------------------------------------------------ 3) consumatori
def _fixture_row(fid, lid, hid, aid, home, away, ko):
    """Riga come ``omega_db.fixtures_for_window`` (stesse colonne della select)."""
    return {"fixture_id": fid, "home_team_name": home, "away_team_name": away, "fixture_date": ko,
            "league_id": lid, "home_team_id": hid, "away_team_id": aid}


def test_safe_hazard_check_usa_gli_id_del_payload(banco):
    from Betfair.safe_strategy.opportunity import OpportunityModel, resolve_lambdas
    from Betfair.safe_strategy.tests.test_opportunity import payload_1_1_65
    atlas = _con_beta(banco["atlas"], banco["mod"].beta)
    ips = _ips(IPS_2T_REC_93, timeElapsed=65, elapsedRegularTime=65, elapsedAddedTime=None)
    p = payload_1_1_65(score_raw=ips)
    lam = resolve_lambdas(p, fixture=None)
    om = OpportunityModel(atlas=atlas)
    senza = om._hazard_check(p, lambdas=(lam[0], lam[1]), league_id=39, minute=65)
    con = om._hazard_check(dict(p, home_team_id=1004, away_team_id=1011), lambdas=(lam[0], lam[1]),
                           league_id=39, minute=65)
    c = V4.consulta_atlante_v4(atlas, 65, 2, 39, tempo=2, home_id=1004, away_id=1011)
    assert con["p_atlas"] == pytest.approx(c["p"], abs=1e-12) and con["forza"]["usata"]
    assert con["p_atlas"] != senza["p_atlas"]
    assert f"atlante v4 (A*), regolare, {V4.testo_forza(c)}" in con["note"]
    assert "forza usata: casa " in con["note"]
    assert "atlante v4 (A1+A2), regolare, forza non usata: id squadra assenti" in senza["note"]
    for hz in (con, senza):                            # soglie e decisione INVARIATE
        div = hz["divergence"]
        atteso = (True, 0.0) if div > float(om.params["hazard_drop"]) else \
            (False, 0.5 if div > float(om.params["hazard_warn"]) else 1.0)
        assert (hz["drop"], hz["penalty"]) == atteso


class _Cattura:
    """Finto OpportunityModel: firma di ``evaluate`` IDENTICA al banco
    (``proposte_modello.ModelloCalcioReplay``), conserva il payload ricevuto."""

    def __init__(self):
        self.payloads: List[dict] = []

    def evaluate(self, payload: dict, *, sport: str, lambdas, league_id, now_ts: float,
                 ht_ratio=None, lambda_source=None) -> List[dict]:
        self.payloads.append(payload)
        return []


def _safe_giro(monkeypatch, db, omega, state):
    from Betfair.safe_strategy import bot_service as S
    from Betfair.safe_strategy import opportunity as O
    from Betfair.safe_strategy.tests.test_bot_service import _run
    monkeypatch.setattr(S, "_omega_service", lambda: omega)
    state["last_ts"] = 0.0
    model = _Cattura()
    _run(db, engine=None, opp_model=model, opp_mod=O, opps_state=state)
    return model


def test_safe_id_dalla_fixture_abbinata_nel_payload_senza_toccare_il_feed(monkeypatch):
    from Betfair.safe_strategy.tests.test_bot_service import NOW, LambdaDB, OmegaStub, _inplay_row
    db = LambdaDB(status="stopped")
    db.scan_rows = [_inplay_row()]
    ko = (NOW - timedelta(hours=1)).isoformat()
    db.fixtures = [_fixture_row(501, 667, 4410, 4411, "Slavia Praha U19", "Sparta Praha U19", ko)]
    db.analyses[501] = {"inputs": {"lambda_home": 1.6, "lambda_away": 1.2, "league_id": 667}}
    state: Dict[str, Any] = {"last_ts": 0.0, "hashes": {}}
    model = _safe_giro(monkeypatch, db, OmegaStub(None), state)
    assert model.payloads[-1]["home_team_id"] == 4410 and model.payloads[-1]["away_team_id"] == 4411
    assert "home_team_id" not in db.scan_rows[0]["payload"]          # la riga del feed resta com'e'
    lam = state["lambdas"]["1.1"]
    assert (lam["home_team_id"], lam["away_team_id"], lam["source"]) == (4410, 4411, "fixture_match")
    assert db.window_calls == 1
    # la riga abbinata porta gli id da sola (non serve il secondo abbinamento)
    from Betfair.safe_strategy import bot_service as S
    from Betfair.safe_strategy import opportunity as O
    r = S._lambdas_from_fixture(db, db.fixtures[0], O)
    assert (r["home_team_id"], r["away_team_id"]) == (4410, 4411)
    assert S._ids_squadra({"home_team_id": "12", "away_team_id": None}) == {"home_team_id": 12,
                                                                           "away_team_id": None}


def test_safe_catena_omega_id_dalla_finestra_gia_in_cache_zero_letture(monkeypatch):
    from Betfair.safe_strategy.tests.test_bot_service import NOW, LambdaDB, OmegaStub, _inplay_row
    ko = (NOW - timedelta(hours=1)).isoformat()
    righe = [_fixture_row(501, 667, 4410, 4411, "Slavia Praha U19", "Sparta Praha U19", ko)]
    # (a) finestra gia' letta (da un altro evento): id abbinati, nessuna lettura
    db = LambdaDB(status="stopped")
    db.scan_rows = [_inplay_row()]
    state: Dict[str, Any] = {"last_ts": 0.0, "hashes": {}, "fixtures": {"ts": 0.0, "rows": righe}}
    model = _safe_giro(monkeypatch, db, OmegaStub((1.7, 0.9, 667, "fixture")), state)
    assert model.payloads[-1]["home_team_id"] == 4410 and db.window_calls == 0
    # (b) finestra mai letta: id assenti (dichiarato dall'atlante), NESSUNA lettura in piu'
    db = LambdaDB(status="stopped")
    db.scan_rows = [_inplay_row()]
    db.fixtures = righe
    state = {"last_ts": 0.0, "hashes": {}}
    model = _safe_giro(monkeypatch, db, OmegaStub((1.7, 0.9, 667, "fixture")), state)
    assert "home_team_id" not in model.payloads[-1] and db.window_calls == 0
    assert state["lambdas"]["1.1"]["home_team_id"] is None
    # (c) fixture di un'ALTRA lega: gli id non si usano
    db = LambdaDB(status="stopped")
    db.scan_rows = [_inplay_row()]
    state = {"last_ts": 0.0, "hashes": {}, "fixtures": {"ts": 0.0, "rows": righe}}
    model = _safe_giro(monkeypatch, db, OmegaStub((1.7, 0.9, 135, "fixture")), state)
    assert "home_team_id" not in model.payloads[-1]


class _SB:
    """Finto client supabase (catena table/select/eq/limit/execute)."""

    def __init__(self, riga):
        self.riga, self.select_viste = riga, []

    def table(self, nome):
        assert nome == "fixture_predictions"
        return self

    def select(self, colonne):
        self.select_viste.append(colonne)
        self._col = colonne.split(",")
        return self

    def eq(self, *a):
        return self

    def limit(self, *a):
        return self

    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=[{k: self.riga.get(k) for k in self._col}])


def test_stream_db_id_squadra_nella_stessa_richiesta(monkeypatch):
    from Betfair.stream import db as SDB
    riga = {"league_id": 39, "tactical_engine_json": None, "home_team_id": 1001, "away_team_id": 1002,
            "db_json_analisi": {"inputs": {"lambda_home": 1.5, "lambda_away": 1.1}}}
    sb = _SB(riga)
    monkeypatch.setattr(SDB, "get_supabase_client", lambda: sb)
    assert SDB.get_fixture_prematch_lambdas(77) == (1.5, 1.1, 39)          # Omega/runner: invariato
    assert sb.select_viste[-1] == "league_id,tactical_engine_json,db_json_analisi"
    assert SDB.get_fixture_prematch_lambdas(77, con_squadre=True) == (1.5, 1.1, 39, 1001, 1002)
    assert sb.select_viste[-1] == "league_id,tactical_engine_json,db_json_analisi,home_team_id,away_team_id"
    assert len(sb.select_viste) == 2                                       # una richiesta per chiamata


class _MikeDB:
    """Finto db di Mike: stesse funzioni del modulo ``Betfair/mike/db.py``."""

    def __init__(self, lam):
        self.lam = lam

    def fixture_id_for_event(self, event_id):
        return 555

    def fixture_lambdas(self, fid):
        return self.lam

    def fixture_analysis(self, fid):
        return {"inputs": {"dc_rho": -0.1}}


def test_mike_dossier_porta_gli_id_e_live_frame_accende_la_forza(banco, monkeypatch):
    from Betfair.mike import db as MDB
    from Betfair.mike import dossier as D
    from Betfair.stream import db as SDB
    # il vero ``mike.db.fixture_lambdas`` chiede gli id nella stessa richiesta
    visti = []
    monkeypatch.setattr(SDB, "get_fixture_prematch_lambdas",
                        lambda fid, **kw: visti.append(kw) or (1.5, 1.1, 39, 1004, 1011))
    assert MDB.fixture_lambdas(555) == (1.5, 1.1, 39, 1004, 1011) and visti == [{"con_squadre": True}]
    dos = D.build_prematch("1.2", _MikeDB((1.5, 1.1, 39, 1004, 1011)))
    assert (dos["home_team_id"], dos["away_team_id"], dos["league_id"]) == (1004, 1011, 39)
    vecchio = D.build_prematch("1.2", _MikeDB((1.5, 1.1, 39)))           # tupla di 3: id assenti
    assert vecchio["home_team_id"] is None and vecchio["lambda_home"] == 1.5
    atlas = _con_beta(banco["atlas"], banco["mod"].beta)
    out = D.live_frame(dos, minute=93, score_home=1, score_away=0, atlas=atlas,
                       payload={"minute": 93, "score_raw": IPS_2T_REC_93})
    c = V4.consulta_atlante_v4(atlas, 93, 1, 39, tempo=2, home_id=1004, away_id=1011)
    assert c["forza"]["usata"] and out["hazard_atlas"] == round(c["p"], 4)
    assert "storico v4 (A*)" in out["hazard_nota"] and "forza usata: casa " in out["hazard_nota"]
    assert out["hazard"] == D.combine_hazard(out["hazard_atlas"], out["hazard_model"], out["pressure"])
    out0 = D.live_frame(vecchio, minute=93, score_home=1, score_away=0, atlas=atlas,
                        payload={"minute": 93, "score_raw": IPS_2T_REC_93})
    assert "forza non usata: id squadra assenti" in out0["hazard_nota"]
    assert out0["hazard_atlas"] == round(V4.consulta_atlante_v4(atlas, 93, 1, 39, tempo=2)["p"], 4)


def test_mike_ripiego_v3_non_usa_gli_id_del_dossier(banco):
    from Betfair.mike import dossier as D
    from Betfair.stream.scalper.hazard_atlas import consulta_atlante
    atl = json.loads(json.dumps(banco["atlas"]))
    atl.pop("v4")
    out = D.live_frame({"league_id": 39, "home_team_id": 1001, "away_team_id": 1002}, minute=60,
                       score_home=1, score_away=0, atlas=atl)
    assert out["hazard_versione"] == "v3" and out["hazard_source"] == "league"
    assert out["hazard_atlas"] == round(consulta_atlante(atl, 60, 1, 39)["p"], 4)
