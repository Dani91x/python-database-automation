"""Atlante Hazard v4 COLLEGATO (25/09/2026 sera, ordine dell'utente "D2: COLLEGALO!").

Cosa si prova (nessuna rete, nessun DB):
  1. PARITA' col banco: stesse righe del DB -> generatore di produzione
     (bootstrap + assembla, lettore PostgREST finto) e motore a domanda ->
     ``consulta_atlante_v4`` col tempo, contro il candidato validato
     (``candidati`` A1+A2 emivita 3, senza forza) sulle partite del banco
     (``dati.costruisci_partite``): stessi p, stato per stato, <= 1e-6.
  2. Generatore: ``raw_json->fixture->status->extra`` e ``minute_extra``
     popolano il blocco v4 (durate, recupero noto); stagione senza minute_extra
     -> non affidabile (reperto 6); incrementale coi conteggi cumulati;
     stato di prima (senza v4) mai completato a pezzi: si ricalcola.
  3. Feed -> tempo 1T/2T sui record IPS VERI (copiati dalle registrazioni
     ``_live_raw``, chiavi identiche).
  4. Consumatori: Safe ``_hazard_check`` e Mike ``live_frame`` usano il v4 e lo
     dicono; senza v4 -> v3 dichiarato; soglie/decisioni invariate; lambda
     della fixture MAI passati.
I finti hanno le chiavi e i tipi del vero: righe di ``matches`` con
``raw_json`` (API-Football), eventi con le ``COLONNE_GOL`` + ``player_id``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

import numpy as np
import pytest

from Betfair.stream.scalper import atlante_a_domanda as AD
from Betfair.stream.scalper import atlante_v4 as V4
from Betfair.stream.scalper import genera_atlante as G
from Betfair.stream.scalper.validazione_hazard import candidati as CA
from Betfair.stream.scalper.validazione_hazard import raccogli as RA
from Betfair.stream.scalper.validazione_hazard.dati import costruisci_partite
from Betfair.stream.scalper.validazione_hazard.stati import tabella_stati
from Betfair.stream.tests.test_atlante_a_domanda_2026_09_25 import (T0, DBFinto, _cov, _fp,  # noqa: F401
                                                                    _motore, cartella)
from Betfair.stream.tests.test_genera_atlante_2026_09_24 import LettoreFinto, seleziona

ADESSO = "2026-09-25T20:00:00+00:00"
LEGHE = (39, 140, 835)
STAGIONI = (2021, 2022, 2023, 2024)

# record IPS VERI (payload del sidecar punteggi, ``_live_raw/35674515`` e
# ``_live_raw/35833626``; ``score`` ridotto a nome e punteggio)
IPS_1T_REC_47 = {"eventTypeId": 1, "eventId": 35674515,
                 "score": {"home": {"name": "Qingdao Hainiu", "score": "3"},
                           "away": {"name": "Yunnan Yukun", "score": "2"}},
                 "timeElapsed": 47, "elapsedRegularTime": 45, "elapsedAddedTime": 2, "hasSets": False,
                 "timeElapsedSeconds": 8, "fullTimeElapsed": {"hour": 0, "min": 0, "sec": 0},
                 "matchStatus": "KickOff"}
IPS_2T_REC_93 = {"eventTypeId": 1, "eventId": 35674515,
                 "score": {"home": {"name": "Qingdao Hainiu", "score": "4"},
                           "away": {"name": "Yunnan Yukun", "score": "2"}},
                 "timeElapsed": 93, "elapsedRegularTime": 90, "elapsedAddedTime": 3, "hasSets": False,
                 "timeElapsedSeconds": 16, "fullTimeElapsed": {"hour": 0, "min": 0, "sec": 0},
                 "matchStatus": "SecondHalfKickOff"}
IPS_INTERVALLO_56 = {"eventTypeId": 1, "eventId": 35674515,
                     "score": {"home": {"name": "Qingdao Hainiu", "score": "4"},
                               "away": {"name": "Yunnan Yukun", "score": "2"}},
                     "timeElapsed": 56, "elapsedRegularTime": 45, "hasSets": False,
                     "timeElapsedSeconds": 0, "fullTimeElapsed": {"hour": 0, "min": 0, "sec": 0},
                     "matchStatus": "FirstHalfEnd"}
IPS_VECCHIO_88 = {"eventTypeId": 1, "eventId": 35833626,
                  "score": {"home": {"name": "Mainz", "score": "2"}, "away": {"name": "Kaiserslautern",
                                                                            "score": "0"}},
                  "timeElapsed": 88, "elapsedRegularTime": 35, "hasSets": False, "timeElapsedSeconds": 47,
                  "fullTimeElapsed": {"hour": 0, "min": 0, "sec": 0}, "matchStatus": "KickOff"}


def _ips(base: Dict[str, Any], **over: Any) -> Dict[str, Any]:
    d = json.loads(json.dumps(base))
    d.update(over)
    return d


# --------------------------------------------------------------- righe DB
def _minuto(tempo: int, pos: int):
    """(minute, minute_extra) di API-Football per la posizione nel tempo."""
    base = 0 if tempo == 1 else 45
    if pos <= 45:
        return base + pos, None
    return base + 45, pos - 45


def _riga_match(fid: int, lid: int, season: int, gh: int, ga: int, extra: Optional[int],
                data: str = "2023-10-01T15:00:00+00:00") -> Dict[str, Any]:
    """Riga di ``matches`` con le colonne vere (quelle che generatore e banco
    leggono) e ``raw_json`` come lo salva ``fixtures_backfill`` (API-Football)."""
    return {"fixture_id": fid, "league_id": lid, "season_year": season, "fixture_date": data,
            "status_short": "FT", "status_elapsed": 90, "home_team_id": 1, "home_team_name": "Casa",
            "away_team_id": 2, "away_team_name": "Ospite", "goals_home": gh, "goals_away": ga,
            "halftime_home": 0, "halftime_away": 0,
            "raw_json": {"fixture": {"id": fid, "periods": {"first": 1, "second": 2},
                                     "status": {"long": "Match Finished", "short": "FT", "elapsed": 90,
                                                "extra": extra}}}}


def _riga_gol(eid: int, fid: int, lid: int, season: int, team: int, minute: int,
              extra: Optional[int]) -> Dict[str, Any]:
    return {"id": eid, "fixture_id": fid, "league_id": lid, "season_year": season, "team_id": team,
            "event_type": "Goal", "detail": "Normal Goal", "minute": minute, "minute_extra": extra,
            "player_id": 7}


def _righe_db(seme: int = 5, n: int = 1400, stagioni=STAGIONI) -> Dict[str, List[Dict[str, Any]]]:
    rng = np.random.default_rng(seme)
    matches, eventi = [], []
    eid = 1
    for i in range(n):
        fid = 100000 + i
        lid = (39, 140)[i % 2] if i % 11 else 835          # la 835 resta sotto le 300 partite
        season = stagioni[(i // 3) % len(stagioni)]      # ogni lega in ogni stagione
        gol = []
        for h in (1, 2):
            for t in range(1, 46):
                if rng.random() < 0.027 + 0.004 * (lid == 140):
                    gol.append((h, t, 1 if rng.random() < 0.55 else 2))
        for j in (1, 2):                                   # gol nel recupero del 1T
            if rng.random() < 0.03:
                gol.append((1, 45 + j, 1))
        d2 = int(rng.integers(3, 10)) if i % 5 else None   # durata del 2T non nota (come < 2024)
        for j in range(1, (d2 or 4) + 1):
            if rng.random() < 0.035:
                gol.append((2, 45 + j, 2))
        gh = sum(1 for g in gol if g[2] == 1)
        ga = len(gol) - gh
        matches.append(_riga_match(fid, lid, season, gh, ga, d2))
        for h, pos, team in gol:
            mi, ex = _minuto(h, pos)
            eventi.append(_riga_gol(eid, fid, lid, season, team, mi, ex))
            eid += 1
    cov = [{"league_id": l, "season_year": s, "fixtures_events": True} for l in LEGHE for s in stagioni]
    return {"matches": matches, "match_events": eventi, "coverage": cov}


def _genera(righe: Dict[str, List[Dict[str, Any]]], stagioni=STAGIONI) -> Dict[str, Any]:
    """Il generatore VERO (bootstrap + assembla) su un PostgREST finto."""
    lettore = LettoreFinto({"matches": righe["matches"], "match_events": righe["match_events"]})
    stati: Dict[str, Dict[str, Any]] = {}
    for lid in LEGHE:
        G.bootstrap(lettore, stati, [lid], list(stagioni), {}, ADESSO)
    return {"atlas": G.assembla(stati, generated_at=ADESSO), "stati": stati, "lettore": lettore}


@pytest.fixture(scope="module")
def banco_e_generatore():
    righe = _righe_db()
    gen = _genera(righe)
    # il BANCO: le righe come le restituisce la select del raccoglitore
    m_banco = [seleziona(m, RA.COLONNE_MATCH_BANCO) for m in righe["matches"]]
    partite, _ = costruisci_partite(m_banco, righe["match_events"], righe["coverage"], stagione_max=2025)
    S = tabella_stati(partite)
    idx = np.arange(S["y3"].size)
    gol_tot = np.array([float(sum(p.ft)) for p in partite])[S["mi"]]
    zero = np.zeros(S["y3"].size)
    conf = CA.ConfA(nome="A*", emivita=V4.EMIVITA, forza=False)
    mod = CA.addestra_a(conf, S, idx, np.array(sorted({p.league_id for p in partite})), zero, 2025, gol_tot)
    atteso = CA.prevedi_a(mod, S, idx, zero)
    return {"righe": righe, "gen": gen, "partite": partite, "S": S, "atteso": atteso}


# ------------------------------------------------ 1) PARITA' col banco
def test_parita_generatore_collegato_col_candidato_validato(banco_e_generatore):
    """Stesse righe del DB: il generatore di produzione (col tempo passato
    come lo passano i consumatori) da' gli STESSI p del candidato validato."""
    b = banco_e_generatore
    atlas = b["gen"]["atlas"]
    S, atteso = b["S"], b["atteso"]
    assert "v4" in atlas and atlas["v4"]["meta"]["stagione_rif"] == 2025
    # stesse partite contate (v3, v4 e banco)
    n_v4 = sum(atlas["v4"]["by_league"][str(l)]["n_fixtures"] for l in LEGHE)
    assert n_v4 == len(b["partite"]) == sum(b["gen"]["stati"][str(l)]["n_fixtures"] for l in LEGHE)
    solo_v4 = {"meta": atlas["meta"], "v4": atlas["v4"]}
    rng = np.random.default_rng(3)
    regolari = np.flatnonzero(S["stop"] == 0)
    rec2 = np.flatnonzero((S["stop"] == 1) & (S["tempo"] == 2))
    assert rec2.size > 300
    campione = np.concatenate([rng.choice(regolari, 2500, replace=False), rec2[:600]])
    diff = 0.0
    for i in campione:
        c = V4.consulta_atlante_v4(solo_v4, int(S["m_live"][i]), int(S["gh"][i] + S["ga"][i]), int(S["lega"][i]),
                                   tempo=int(S["tempo"][i]))
        assert c["versione"] == "v4"
        diff = max(diff, abs(c["p_3min"] - atteso["p3"][i]), abs(c["p_2min"] - atteso["p2"][i]))
    assert diff <= 1e-6, diff


def test_parita_motore_a_domanda_uguale_al_generatore(banco_e_generatore, cartella):
    """Il motore a domanda (select vera con l'alias raw_json, coverage, a
    blocchi) scrive nel file live lo STESSO blocco v4 del generatore."""
    righe = banco_e_generatore["righe"]
    db = DBFinto({"fixture_predictions": [_fp(900000 + l, l, T0 + 3600) for l in LEGHE],
                  "api_coverage_by_season": [_cov(l, s, True) for l in LEGHE for s in STAGIONI],
                  "matches": righe["matches"], "match_events": righe["match_events"]})
    m = _motore(db, cartella, [T0])
    r = m.ciclo()
    assert r["preparate"] == {str(l): "calcolata" for l in LEGHE}
    live = json.load(open(cartella["live"], encoding="utf-8"))
    gen_v4 = banco_e_generatore["gen"]["atlas"]["v4"]
    assert live["v4"]["by_league"] == gen_v4["by_league"]
    assert live["v4"]["global"] == gen_v4["global"]
    # la select delle partite porta la durata del recupero (alias PostgREST)
    assert all("extra:raw_json->fixture->status->extra" in p["select"] for p in db.chiamate_a("matches"))


def test_globale_v4_non_solido_lega_piccola_sul_v3_dichiarato(banco_e_generatore):
    """1.400 partite < 10.000: globale v4 NON solido. La lega grande resta v4
    (stesso p della vista pura), la piccola (835, < 300) va sul v3 e lo dice."""
    atlas = banco_e_generatore["gen"]["atlas"]
    assert atlas["v4"]["meta"]["globale_solido"] is False
    puro = {"meta": atlas["meta"], "v4": atlas["v4"]}
    c = V4.consulta_atlante_v4(atlas, 60, 1, 39, tempo=2)
    assert c["versione"] == "v4" and c["p"] == V4.consulta_atlante_v4(puro, 60, 1, 39, tempo=2)["p"]
    c = V4.consulta_atlante_v4(atlas, 60, 1, 835, tempo=2)
    assert c["versione"] == "v3" and "atlante v3: recupero non modellato (lega 835" in c["nota"]
    assert c["p"] is not None


# --------------------------------------------------------- 2) generatore
def test_generatore_popola_il_v4_da_status_extra_e_minute_extra(banco_e_generatore):
    stati = banco_e_generatore["gen"]["stati"]
    v4 = stati["39"]["v4"]
    assert "fixtures" not in v4                      # nessuna seconda lista di fixture_id
    blk = v4["stagioni"]["2023"]
    assert blk["durate"] and sum(blk["durate"].values()) > 0
    assert all(isinstance(x, int) for x in blk["celle"][:50])
    assert all(v4["affidabile"][str(s)] is True for s in STAGIONI)
    con, tot = v4["quota_extra"]["2023"]
    assert tot > 0 and con / tot >= 0.6
    atl = banco_e_generatore["gen"]["atlas"]["v4"]
    assert atl["meta"]["recupero_2T_noto"] is True and atl["by_league"]["39"]["pi_durata"]
    # stessa partita: le sue durate vengono da raw_json.fixture.status.extra
    m0 = next(m for m in banco_e_generatore["righe"]["matches"] if m["league_id"] == 39
              and m["raw_json"]["fixture"]["status"]["extra"])
    assert G.sequenza_partita(seleziona(m0, G.COLONNE_MATCH), [])[1] in ("ok", "gol_diversi_dal_punteggio")
    assert seleziona(m0, G.COLONNE_MATCH)["extra"] == m0["raw_json"]["fixture"]["status"]["extra"]


def _lega_con_stagione_senza_extra() -> Dict[str, List[Dict[str, Any]]]:
    """Lega 39: 2024 registra il recupero dei gol, 2025 NO (gol al 90' senza
    minute_extra, come i dati europei 2025-26 del reperto 6)."""
    matches, eventi = [], []
    eid = 1
    for i in range(12):
        for season, extra in ((2024, 2), (2025, None)):
            fid = 5000 + i * 10 + (season - 2024)
            matches.append(_riga_match(fid, 39, season, 1, 0, 6))
            eventi.append(_riga_gol(eid, fid, 39, season, 1, 90, extra))
            eid += 1
    return {"matches": matches, "match_events": eventi}


def test_stagione_senza_minute_extra_non_affidabile_nel_bootstrap():
    righe = _lega_con_stagione_senza_extra()
    stati: Dict[str, Dict[str, Any]] = {}
    G.bootstrap(LettoreFinto(righe), stati, [39], [2024, 2025], {}, ADESSO)
    v4 = stati["39"]["v4"]
    assert v4["affidabile"] == {"2024": True, "2025": False}
    assert v4["quota_extra"] == {"2024": [12, 12], "2025": [0, 12]}
    c24 = np.asarray(v4["stagioni"]["2024"]["celle"]).reshape(V4.NT, V4.NG, 3)
    c25 = np.asarray(v4["stagioni"]["2025"]["celle"]).reshape(V4.NT, V4.NG, 3)
    assert c24[:, :, 0].sum() == 12 * 96 and c25[:, :, 0].sum() == 12 * 84
    assert v4["stagioni"]["2025"]["durate"] == {} and v4["stagioni"]["2024"]["durate"] == {"6": 12}


def test_incrementale_motore_aggiunge_al_v4_coi_conteggi_cumulati(cartella):
    """Partite nuove finite: entrano nel v4 come nel v3 (stesse righe, nessuna
    lettura in piu'); la stagione 2025 resta non affidabile dai conteggi
    cumulati; un secondo giro non conta due volte."""
    righe = _lega_con_stagione_senza_extra()
    nuove = [_riga_match(9001, 39, 2025, 1, 0, 5, data="2026-09-25T09:00:00+00:00"),
             _riga_match(9002, 39, 2025, 0, 1, 7, data="2026-09-25T09:00:00+00:00")]
    gol_nuovi = [_riga_gol(8001, 9001, 39, 2025, 1, 90, None), _riga_gol(8002, 9002, 39, 2025, 2, 30, None)]
    db = DBFinto({"fixture_predictions": [_fp(9001, 39, T0 - 3 * 3600), _fp(9002, 39, T0 - 3 * 3600)],
                  "api_coverage_by_season": [_cov(39, 2024, True), _cov(39, 2025, True)],
                  "matches": righe["matches"] + nuove, "match_events": righe["match_events"] + gol_nuovi})
    # le due partite nuove non devono entrare dal bootstrap: stagione 2025 del
    # bootstrap = solo le 12 vecchie (le nuove si aggiungono al DB dopo)
    db.tabelle["matches"] = righe["matches"]
    db.tabelle["match_events"] = righe["match_events"]
    ora = [T0]
    m = _motore(db, cartella, ora)
    m.ciclo()
    v4 = m.leghe["39"]["v4"]
    assert v4["stagioni"]["2025"]["n_fixtures"] == 12
    db.tabelle["matches"] = righe["matches"] + nuove
    db.tabelle["match_events"] = righe["match_events"] + gol_nuovi
    n_ev = len(db.chiamate_a("match_events"))
    ora[0] = T0 + 3700                               # oltre la pausa di 60' delle partite in attesa
    r = m.ciclo()
    assert r["incrementale"]["aggiunte"] == 2
    v4 = m.leghe["39"]["v4"]
    assert v4["stagioni"]["2025"]["n_fixtures"] == 14 == m.leghe["39"]["n_fixtures"] - 12
    assert v4["quota_extra"]["2025"] == [0, 13] and v4["affidabile"]["2025"] is False
    c25 = np.asarray(v4["stagioni"]["2025"]["celle"]).reshape(V4.NT, V4.NG, 3)
    assert c25[:, :, 0].sum() == 14 * 84             # anche le nuove: solo t <= 41
    assert len(db.chiamate_a("match_events")) - n_ev == 1   # i soli gol del blocco (nessuno 0-0)
    ora[0] = T0 + 7400
    m.ciclo()
    assert m.leghe["39"]["v4"]["stagioni"]["2025"]["n_fixtures"] == 14


def test_stato_senza_v4_non_si_adotta_si_ricalcola_e_intanto_v3_dichiarato(cartella):
    righe = _lega_con_stagione_senza_extra()
    stati: Dict[str, Dict[str, Any]] = {}
    G.bootstrap(LettoreFinto(righe), stati, [39], [2024, 2025], {}, ADESSO)
    vecchio = json.loads(json.dumps(stati["39"]))
    vecchio.pop("v4")                                 # stato scritto prima del collegamento
    # consultazione nel frattempo: la lega e' solo nel v3 -> v3, DICHIARATO
    altra = _genera(_righe_db(n=300, stagioni=(2024,)), stagioni=(2024,))["stati"]
    atl = G.assembla({"39": vecchio, "140": altra["140"]}, generated_at=ADESSO)
    assert "39" not in atl["v4"]["by_league"]
    c = V4.consulta_atlante_v4(atl, 60, 1, 39, tempo=2)
    assert c["versione"] == "v3" and "(lega 39 non ancora nel v4)" in c["nota"]
    # il DB ha la riga vecchia (senza v4): NON si adotta, la lega si ricalcola
    fixtures = vecchio.pop("fixtures")
    db = DBFinto({"fixture_predictions": [_fp(9901, 39, T0 + 3600)],
                  "api_coverage_by_season": [_cov(39, 2024, True), _cov(39, 2025, True)],
                  "matches": righe["matches"], "match_events": righe["match_events"],
                  "hazard_atlas_leghe": [{"league_id": 39, "stato": vecchio, "fixtures": fixtures}]})
    m = _motore(db, cartella, [T0])
    assert m.prepara_lega("39", T0) == "calcolata"
    assert isinstance(m.leghe["39"].get("v4"), dict)
    # stato locale vecchio (file) -> la lega osservata si ricalcola come nuova
    m2 = _motore(db, cartella, [T0])
    m2._caricato = True
    m2.leghe = {"39": dict(vecchio, fixtures=fixtures)}
    r = m2.ciclo()
    assert r["preparate"] == {"39": "calcolata"} and m2._ha_v4("39")


def test_assembla_v4_senza_leghe_affidabili_nessun_nan():
    gen = _genera(_righe_db(n=120, stagioni=(2024,)), stagioni=(2024,))
    blk = gen["atlas"]["v4"]
    assert blk["meta"]["n_leghe_affidabili"] == 0 and blk["meta"]["globale_solido"] is False
    assert np.all(np.isfinite(np.asarray(blk["global"]["p3"], dtype=float)))
    assert all(not v["affidabile"] for v in blk["by_league"].values())


def test_omega_h2h_invariato_col_v4(banco_e_generatore):
    stati = banco_e_generatore["gen"]["stati"]
    senza = {k: {kk: vv for kk, vv in v.items() if kk != "v4"} for k, v in stati.items()}
    a = G.assembla(stati, generated_at=ADESSO)
    b = G.assembla(senza, generated_at=ADESSO)
    assert "v4" in a and "v4" not in b
    for k in ("global", "by_league", "by_team", "h2h_hint"):
        assert a[k] == b[k]


def test_workflow_notturno_installa_numpy_prima_del_generatore():
    radice = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    testo = open(os.path.join(radice, ".github", "workflows", "hazard_atlas.yml"), encoding="utf-8").read()
    i_pip = testo.find('pip install --disable-pip-version-check "numpy')
    assert 0 <= i_pip < testo.find("python -m Betfair.stream.scalper.genera_atlante")


# ------------------------------------------------------ 3) feed -> tempo
@pytest.mark.parametrize("raw,minuto,atteso", [
    (IPS_1T_REC_47, 47, 1),                          # recupero 1T: minuto CUMULATO 45+2
    (_ips(IPS_1T_REC_47, timeElapsed=30, elapsedRegularTime=30, elapsedAddedTime=None), 30, 1),
    (IPS_INTERVALLO_56, 56, 1),                      # intervallo: il minuto continua a contare
    # intervallo lungo: oltre 45+15 il minuto IPS continua (45 -> 56 misurato in 13'); resta tempo 1
    (_ips(IPS_INTERVALLO_56, timeElapsed=63), 63, 1),
    (_ips(IPS_2T_REC_93, timeElapsed=45, elapsedRegularTime=45, elapsedAddedTime=None), 45, 2),
    (_ips(IPS_2T_REC_93, timeElapsed=47, elapsedRegularTime=47, elapsedAddedTime=None), 47, 2),
    (IPS_2T_REC_93, 93, 2),
    (IPS_VECCHIO_88, 88, None),                      # stato vecchio: non si crede al 'KickOff'
    (_ips(IPS_1T_REC_47, matchStatus=None), 47, 1),  # niente stato: 45 + recupero dichiarato
    (_ips(IPS_2T_REC_93, matchStatus="Finished"), 93, 2),
    (None, 47, None), (None, 30, 1), (None, 93, 2),
])
def test_tempo_dai_record_ips_veri(raw, minuto, atteso):
    assert V4.tempo_da_stato_ips(raw, minuto) == atteso
    assert V4.tempo_da_payload({"minute": minuto, "score_raw": raw}) == atteso


def test_minuto_46_del_recupero_1T_non_e_la_ripresa(banco_e_generatore):
    atlas = banco_e_generatore["gen"]["atlas"]
    t = V4.tempo_da_payload({"minute": 47, "score_raw": IPS_1T_REC_47})
    c = V4.consulta_atlante_v4(atlas, 47, 1, 39, tempo=t)
    assert c["fase"] == "recupero_1T"
    assert c["p"] == V4.consulta_atlante_v4(atlas, 44, 1, 39, tempo=1)["p"]      # cella 40-45
    assert c["p"] != V4.consulta_atlante_v4(atlas, 47, 1, 39, tempo=2)["p"]      # non la ripresa


# ------------------------------------------------------ 4) consumatori
def _atlante_safe(banco_e_generatore, con_v4: bool = True) -> Dict[str, Any]:
    atl = json.loads(json.dumps(banco_e_generatore["gen"]["atlas"]))
    if not con_v4:
        atl.pop("v4")
    return atl


def _safe(payload, atlas):
    from Betfair.safe_strategy.opportunity import OpportunityModel, resolve_lambdas
    lam = resolve_lambdas(payload, fixture=None)
    om = OpportunityModel(atlas=atlas)
    return om, om._hazard_check(payload, lambdas=(lam[0], lam[1]), league_id=39,
                                minute=int(payload["minute"]))


def _decisione_attesa(om, hz):
    div = hz["divergence"]
    if div > float(om.params["hazard_drop"]):
        return (True, 0.0)
    return (False, 0.5 if div > float(om.params["hazard_warn"]) else 1.0)


@pytest.mark.parametrize("minuto,ips,goals,fase", [
    (65, _ips(IPS_2T_REC_93, timeElapsed=65, elapsedRegularTime=65, elapsedAddedTime=None), (1, 1), "regolare"),
    (93, IPS_2T_REC_93, (1, 1), "recupero_2T"),
    (47, IPS_1T_REC_47, (1, 1), "recupero_1T"),
])
def test_safe_usa_il_v4_col_tempo_e_lo_dichiara(banco_e_generatore, minuto, ips, goals, fase):
    from Betfair.safe_strategy.tests.test_opportunity import payload_1_1_65
    p = payload_1_1_65(minute=minuto, score_home=goals[0], score_away=goals[1], score_raw=ips)
    atlas = _atlante_safe(banco_e_generatore)
    om, hz = _safe(p, atlas)
    atteso = V4.consulta_atlante_v4(atlas, minuto, sum(goals), 39, tempo=V4.tempo_da_payload(p))
    assert atteso["versione"] == "v4" and atteso["fase"] == fase
    assert hz["p_atlas"] == pytest.approx(atteso["p"], abs=1e-12)
    assert hz["versione"] == "v4" and hz["fase"] == fase
    assert f"atlante v4, {fase}" in hz["note"]
    if fase == "recupero_2T":
        assert hz["recupero_atteso_min"] is not None and "recupero atteso ancora" in hz["note"]
    # nessuna forza dai lambda della fixture: il p e' quello SENZA lambda
    assert atteso["forza"]["usata"] is False
    # soglie e decisione INVARIATE: drop/penalty seguono warn/drop sul dato nuovo
    assert (hz["drop"], hz["penalty"]) == _decisione_attesa(om, hz)


def test_safe_senza_v4_ripiega_sul_v3_e_lo_dichiara(banco_e_generatore):
    from Betfair.safe_strategy.tests.test_opportunity import payload_1_1_65
    from Betfair.stream.scalper.hazard_atlas import consulta_atlante
    p = payload_1_1_65(score_raw=_ips(IPS_2T_REC_93, timeElapsed=65, elapsedRegularTime=65,
                                      elapsedAddedTime=None))
    atlas = _atlante_safe(banco_e_generatore, con_v4=False)
    om, hz = _safe(p, atlas)
    v3 = consulta_atlante(atlas, 65, 2, 39, home_team=p["home"], away_team=p["away"])
    assert hz["p_atlas"] == pytest.approx(v3["p"]) and hz["versione"] == "v3"
    assert "atlante v3: recupero non modellato (blocco v4 assente)" in hz["note"]
    assert (hz["drop"], hz["penalty"]) == _decisione_attesa(om, hz)


def test_mike_live_frame_usa_il_v4_col_tempo(banco_e_generatore):
    from Betfair.mike import dossier as D
    atlas = _atlante_safe(banco_e_generatore)
    out = D.live_frame({"league_id": 39}, minute=93, score_home=1, score_away=0, atlas=atlas,
                       payload={"minute": 93, "score_raw": IPS_2T_REC_93})
    c = V4.consulta_atlante_v4(atlas, 93, 1, 39, tempo=2)
    assert out["hazard_atlas"] == round(c["p"], 4) and out["hazard_versione"] == "v4"
    assert out["hazard_fase"] == "recupero_2T" and out["hazard_recupero_atteso_min"] is not None
    assert out["hazard_nota"].startswith("storico v4 ")
    # la regola di Mike non cambia: hazard = combine_hazard(atlante, modello, pressione)
    assert out["hazard"] == D.combine_hazard(out["hazard_atlas"], out["hazard_model"], out["pressure"])
    out1 = D.live_frame({"league_id": 39}, minute=47, score_home=1, score_away=0, atlas=atlas,
                        payload={"minute": 47, "score_raw": IPS_1T_REC_47})
    assert out1["hazard_fase"] == "recupero_1T"
    assert out1["hazard_atlas"] == round(V4.consulta_atlante_v4(atlas, 44, 1, 39, tempo=1)["p"], 4)


def test_mike_senza_v4_ripiego_v3_dichiarato(banco_e_generatore):
    from Betfair.mike import dossier as D
    from Betfair.stream.scalper.hazard_atlas import consulta_atlante
    atlas = _atlante_safe(banco_e_generatore, con_v4=False)
    out = D.live_frame({"league_id": 39}, minute=66, score_home=1, score_away=1, atlas=atlas)
    assert out["hazard_atlas"] == round(consulta_atlante(atlas, 66, 2, 39)["p"], 4)
    assert out["hazard_versione"] == "v3"
    assert out["hazard_nota"].endswith("[atlante v3: recupero non modellato (blocco v4 assente)]")


def test_mike_recupero_atteso_e_volatile():
    from Betfair.mike import service as S
    assert "hazard_recupero_atteso_min" in S._LIVE_VOLATILI
    assert "hazard_versione" not in S._LIVE_VOLATILI and "hazard_fase" not in S._LIVE_VOLATILI


def test_consultazione_non_carica_flumine_ne_scipy():
    """Il processo del feed consulta l'atlante: niente flumine (incidente del
    17/09) e niente scipy (serve solo al banco)."""
    radice = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    codice = ("import sys, json; from Betfair.stream.scalper import atlante_v4 as V4;"
              "V4.consulta_atlante_v4({'meta': {}, 'global': {}}, 60, 1, 39, tempo=2);"
              "print(json.dumps(['flumine' in sys.modules, 'scipy' in sys.modules]))")
    r = subprocess.run([sys.executable, "-c", codice], cwd=radice, capture_output=True, text=True,
                       timeout=120, env=dict(os.environ, PYTHONPATH=radice))
    assert r.returncode == 0, r.stderr[-2000:]
    assert json.loads(r.stdout.strip().splitlines()[-1]) == [False, False]
