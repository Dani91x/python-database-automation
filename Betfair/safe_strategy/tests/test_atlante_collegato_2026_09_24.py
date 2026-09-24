"""ATLANTE HAZARD COLLEGATO a Safe (24/09/2026, ordine dell'utente).

In Control Room la proposta diceva "hazard non verificato (atlante assente)":
``OpportunityModel._hazard_check`` era scritto ma MORTO, perche'
``bot_service._build_model`` costruiva il modello senza atlante. Qui si
certifica che:

  * il bot costruisce il modello con il FORNITORE dell'atlante condiviso
    (``selezione.atlante``), e con l'atlante la nota dice modello, storico,
    divergenza, fonte ed eta' ("atlante del GG/MM, n partite");
  * una lega assente nell'atlante e' dichiarata "lega non coperta" (non
    "atlante assente") e il confronto va sullo storico globale;
  * senza nessun file il comportamento e' quello di prima;
  * sotto ``hazard_warn`` le proposte sono IDENTICHE (prezzo, lato, EV,
    confidenza) a quelle senza atlante: cambia solo la frase;
  * l'atlante condiviso si RICARICA quando il file cambia sul disco, e un
    file rotto non butta quello buono gia' in memoria.

I finti hanno le chiavi del vero (``hazard_atlas_v2.json``: meta.generated_at,
meta.n_fixtures_used, global[bucket][gol]{p_goal_next_3min, n},
by_league[str(id)]{meta, grid}).
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any, Dict

import pytest

from Betfair.safe_strategy import selezione as SEL
from Betfair.safe_strategy.opportunity import OpportunityModel, resolve_lambdas
from Betfair.safe_strategy.tests.test_opportunity import NOW, payload_1_1_65
from Betfair.stream.scalper import hazard_atlas as HA

LEGA = 39


def _lam(payload: dict):
    got = resolve_lambdas(payload, fixture=None)
    assert got is not None
    return (got[0], got[1])


def _model_hazard(payload: dict, league_id: Any) -> float:
    from Betfair.stream.engine.live_engine_pro import event_goal_hazard
    lam = _lam(payload)
    h = event_goal_hazard(
        score_home=payload["score_home"], score_away=payload["score_away"],
        minute=payload["minute"], prematch_lambda_home=lam[0],
        prematch_lambda_away=lam[1], league_id=league_id, horizon_min=3.0,
    )
    assert h is not None
    return float(h["p_next"])


def _cella(p: float) -> Dict[str, Any]:
    return {"p_goal_next_3min": round(p, 6), "p_goal_next_2min": round(p * 0.66, 6), "n": 5000}


def _atlante(p_lega: float, p_globale: float, generated_at: str = "2026-09-24T02:00:00+00:00",
             n: int = 61234) -> Dict[str, Any]:
    """Atlante con le chiavi del vero: bucket 65-70, stato 2 gol (1-1 al 65')."""
    return {
        "meta": {"name": "hazard_atlas_v3", "generated_at": generated_at, "n_fixtures_used": n},
        "global": {"65-70": {"2": _cella(p_globale)}},
        "by_league": {str(LEGA): {
            "meta": {"league_name": "Premier League", "n_fixtures": 3800,
                     "side_rate_per_bucket": {"65-70": 0.07}},
            "grid": {"65-70": {"2": _cella(p_lega)}},
        }},
        "by_team": {},
        "h2h_hint": {},
    }


def _eval(model: OpportunityModel, payload: dict, league_id: Any):
    return model.evaluate(payload, sport="calcio", lambdas=_lam(payload),
                          league_id=league_id, now_ts=NOW)


def _under(opps):
    return [x for x in opps if x["selection_name"] == "Under 7.5"][0]


# --------------------------------------------------- nota e fonte valorizzate
def test_con_atlante_la_nota_dice_modello_storico_divergenza_fonte_eta():
    p = payload_1_1_65()
    pm = _model_hazard(p, LEGA)
    atl = _atlante(p_lega=pm * 1.10, p_globale=pm * 3.0)       # divergenza ~9%
    m = OpportunityModel(atlas=atl)
    hz = m._hazard_check(p, lambdas=_lam(p), league_id=LEGA, minute=65)
    assert hz["source"] == "league"
    assert hz["divergence"] == pytest.approx(abs(pm - pm * 1.10) / (pm * 1.10), rel=1e-6)
    assert hz["penalty"] == 1.0 and hz["drop"] is False
    assert "hazard coerente con l'atlante (verificato: modello" in hz["note"]
    assert f"vs storico {pm * 1.10 * 100:.1f}%" in hz["note"]
    assert "[league]" in hz["note"] and "divergenza 9%" in hz["note"]
    assert "atlante del 24/09, 61234 partite" in hz["note"]
    assert "non verificato" not in hz["note"] and "lega non coperta" not in hz["note"]
    o = _under(_eval(m, p, LEGA))
    assert "verificato: modello" in o["rationale"]
    assert "atlante assente" not in o["rationale"]


def test_divergenza_tra_warn_e_drop_dimezza_e_lo_dice_con_i_numeri():
    p = payload_1_1_65()
    pm = _model_hazard(p, LEGA)
    base = _under(_eval(OpportunityModel(atlas=_atlante(pm, pm)), p, LEGA))
    warn = OpportunityModel(atlas=_atlante(pm / 1.4, pm))       # divergenza 40%
    o = _under(_eval(warn, p, LEGA))
    assert o["confidence"] == pytest.approx(base["confidence"] / 2, abs=1e-3)
    assert "hazard divergente dall'atlante (modello" in o["rationale"]
    assert "divergenza 40%" in o["rationale"] and "confidenza dimezzata" in o["rationale"]


def test_lega_non_coperta_dichiarata_e_confronto_sul_globale():
    p = payload_1_1_65()
    pm = _model_hazard(p, 999)
    m = OpportunityModel(atlas=_atlante(p_lega=pm * 5, p_globale=pm))
    hz = m._hazard_check(p, lambdas=_lam(p), league_id=999, minute=65)
    assert hz["source"] == "global"
    assert hz["note"].startswith("atlante: lega non coperta (999)")
    assert "storico globale" in hz["note"] and "atlante assente" not in hz["note"]
    assert hz["penalty"] == 1.0                     # globale coerente: nessuna penalita'
    # lega sconosciuta (fixture non abbinata): stessa dichiarazione
    hz2 = m._hazard_check(p, lambdas=_lam(p), league_id=None, minute=65)
    assert hz2["note"].startswith("atlante: lega non coperta (n/d)")


def test_atlante_senza_cella_per_lo_stato_non_e_atlante_assente():
    p = payload_1_1_65()
    atl = _atlante(0.1, 0.1)
    atl["global"] = {}
    atl["by_league"] = {}
    hz = OpportunityModel(atlas=atl)._hazard_check(p, lambdas=_lam(p), league_id=LEGA, minute=65)
    assert hz["source"] == "none" and hz["penalty"] == 1.0
    assert "nessun dato storico per lo stato" in hz["note"]
    assert "atlante assente" not in hz["note"]


# ---------------------------------------------- parita' sotto hazard_warn
def test_parita_delle_proposte_sotto_hazard_warn():
    """Con divergenza sotto warn il collegamento NON cambia le proposte:
    stessi mercati, lati, prezzi, EV, confidenze. Cambia solo la frase."""
    p = payload_1_1_65()
    pm = _model_hazard(p, LEGA)
    senza = _eval(OpportunityModel(), p, LEGA)
    con = _eval(OpportunityModel(atlas=_atlante(pm * 1.2, pm)), p, LEGA)   # 17% < 30%
    assert senza, "il payload deve produrre proposte"
    chiavi = ("market_id", "selection_id", "side", "price", "size", "p_model", "edge", "ev",
              "confidence")
    assert [tuple(o.get(k) for k in chiavi) for o in senza] == \
           [tuple(o.get(k) for k in chiavi) for o in con]
    assert all("atlante assente" in o["rationale"] for o in senza)
    assert all("verificato" in o["rationale"] for o in con)


# ------------------------------------------------ il bot passa l'atlante
@pytest.fixture()
def atlante_isolato(tmp_path, monkeypatch):
    """Cache condivisa e percorsi puntati su una cartella temporanea."""
    live = tmp_path / "hazard_atlas_live.json"
    v2 = tmp_path / "hazard_atlas_v2.json"
    monkeypatch.setattr(HA, "ATLAS_LIVE_PATH", str(live))
    monkeypatch.setattr(HA, "ATLAS_V2_PATH", str(v2))
    monkeypatch.setattr(HA, "MTIME_CHECK_S", 0.0)
    SEL.reset_cache()
    yield live, v2
    SEL.reset_cache()


def _scrivi(path, atl: dict, mtime: float) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(atl, fh)
    os.utime(path, (mtime, mtime))


def test_bot_service_costruisce_il_modello_con_il_fornitore_dell_atlante(atlante_isolato):
    from Betfair.safe_strategy import bot_service as BS
    from Betfair.safe_strategy import opportunity as OP
    live, v2 = atlante_isolato
    p = payload_1_1_65()
    pm = _model_hazard(p, LEGA)
    _scrivi(v2, _atlante(pm, pm), 1_700_000_000)
    m = BS._build_model(OP, {})
    assert m.atlas is SEL.atlante                # il fornitore, non una copia
    hz = m._hazard_check(p, lambdas=_lam(p), league_id=LEGA, minute=65)
    assert hz["source"] == "league" and "verificato" in hz["note"]


def test_senza_file_il_comportamento_e_quello_di_prima(atlante_isolato):
    from Betfair.safe_strategy import bot_service as BS
    from Betfair.safe_strategy import opportunity as OP
    p = payload_1_1_65()
    m = BS._build_model(OP, {})
    hz = m._hazard_check(p, lambdas=_lam(p), league_id=LEGA, minute=65)
    assert hz == {"ok": True, "drop": False, "penalty": 1.0,
                  "note": "hazard non verificato (atlante assente)",
                  "divergence": None, "source": "none"}
    ref = _eval(OpportunityModel(), p, LEGA)
    assert _eval(m, p, LEGA) == ref


# ------------------------------------------------------------- ricarica
def test_atlante_si_ricarica_quando_il_file_cambia(atlante_isolato):
    live, v2 = atlante_isolato
    _scrivi(v2, _atlante(0.05, 0.05, generated_at="2026-07-15T14:13:40+00:00", n=54009),
            1_700_000_000)
    a1 = SEL.atlante()
    assert a1["meta"]["n_fixtures_used"] == 54009
    assert SEL.atlante() is a1                   # stesso file: stessa istanza
    # compare il LIVE (rigenerato): ha la precedenza sul v2
    _scrivi(live, _atlante(0.06, 0.06, n=60000), 1_700_000_100)
    a2 = SEL.atlante()
    assert a2 is not a1 and a2["meta"]["n_fixtures_used"] == 60000
    # il live viene riscritto: nuovo mtime -> nuova istanza
    _scrivi(live, _atlante(0.07, 0.07, n=61000), 1_700_000_200)
    a3 = SEL.atlante()
    assert a3["meta"]["n_fixtures_used"] == 61000
    # scrittura a meta' (JSON rotto): si tiene l'ultimo buono
    with open(live, "w", encoding="utf-8") as fh:
        fh.write('{"meta": {"generated_at": "2026-09-2')
    os.utime(live, (1_700_000_300, 1_700_000_300))
    assert SEL.atlante() is a3
    # il modello del bot vede il nuovo atlante SENZA essere ricostruito
    from Betfair.safe_strategy import bot_service as BS
    from Betfair.safe_strategy import opportunity as OP
    m = BS._build_model(OP, {})
    _scrivi(live, _atlante(0.08, 0.08, n=62000), 1_700_000_400)
    p = payload_1_1_65()
    hz = m._hazard_check(p, lambdas=_lam(p), league_id=LEGA, minute=65)
    assert "62000 partite" in hz["note"]


def test_cache_non_rilegge_prima_del_controllo_mtime(atlante_isolato, monkeypatch):
    live, v2 = atlante_isolato
    monkeypatch.setattr(HA, "MTIME_CHECK_S", 3600.0)
    _scrivi(v2, _atlante(0.05, 0.05, n=1), 1_700_000_000)
    a1 = HA.atlante_condiviso()
    _scrivi(v2, _atlante(0.05, 0.05, n=2), 1_700_000_500)
    assert HA.atlante_condiviso() is a1          # dentro la finestra: nessun os.stat
    assert HA.atlante_condiviso(forza=True)["meta"]["n_fixtures_used"] == 2


# --------------------------------------------------------- eta' dichiarata
def test_eta_dichiarata_fresco_vecchio_senza_data():
    adesso = dt.datetime(2026, 9, 24, 18, 0, tzinfo=dt.timezone.utc)
    vecchio = {"meta": {"generated_at": "2026-07-15T14:13:40.525778+00:00",
                        "n_fixtures_used": 54009}}
    assert HA.etichetta_atlante(vecchio, adesso) == \
        "atlante del 15/07, 54009 partite, VECCHIO: 71 giorni"
    fresco = {"meta": {"generated_at": "2026-09-24T02:00:00+00:00", "n_fixtures_used": 61234}}
    assert HA.etichetta_atlante(fresco, adesso) == "atlante del 24/09, 61234 partite"
    assert HA.eta_atlante(fresco, adesso)["vecchio"] is False
    # al limite: 3 giorni esatti non e' vecchio, 3 giorni e un'ora si'
    limite = {"meta": {"generated_at": "2026-09-21T18:00:00+00:00", "n_fixtures_used": 5}}
    assert "VECCHIO" not in HA.etichetta_atlante(limite, adesso)
    oltre = {"meta": {"generated_at": "2026-09-21T17:00:00+00:00", "n_fixtures_used": 5}}
    assert "VECCHIO: 3 giorni" in HA.etichetta_atlante(oltre, adesso)
    assert HA.etichetta_atlante({"meta": {}}, adesso) == \
        "atlante senza data, partite n/d, VECCHIO: eta' ignota"


def test_l_atlante_vero_committato_e_dichiarato_vecchio():
    """Il v2 in repo e' del 15/07: la nota lo deve dire, non spacciarlo per fresco."""
    with open(os.path.join(os.path.dirname(HA.__file__), "..", "..", "omega", "data",
                           "hazard_atlas_v2.json"), encoding="utf-8") as fh:
        vero = json.load(fh)
    adesso = dt.datetime(2026, 9, 24, tzinfo=dt.timezone.utc)
    assert HA.etichetta_atlante(vero, adesso).startswith("atlante del 15/07, 54009 partite, VECCHIO")
