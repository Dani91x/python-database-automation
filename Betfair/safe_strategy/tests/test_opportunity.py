"""Test del motore OPPORTUNITA' (Betfair/safe_strategy/opportunity.py).

Tutto PURO: nessuna rete, nessun DB, orologio e Atlante Hazard iniettati.
"""
from __future__ import annotations

import json

import pytest

from Betfair.safe_strategy.opportunity import (
    DEFAULT_OPP_PARAMS,
    OpportunityModel,
    ht_ratio_from_fixture,
    resolve_lambdas,
)

PRE_KO = {"home": 2.0, "draw": 3.4, "away": 4.0}


# ---------------------------------------------------------------- helper dati
def _sel(sid, name, back=None, lay=None, back_size=None, lay_size=None, status="ACTIVE"):
    return {
        "selection_id": sid, "name": name, "runner_status": status,
        "back": back, "lay": lay, "back_size": back_size, "lay_size": lay_size,
    }


def payload_1_1_65(**over) -> dict:
    """Payload realistico: 1-1 al 65', Over/Under 7.5 quotato 1.10/1.12 con size."""
    base = {
        "event_name": "Nord FC v Sud FC",
        "home": "Nord FC", "away": "Sud FC",
        "inplay": True,
        "minute": 65,
        "score_home": 1, "score_away": 1,
        "red_home": 0, "red_away": 0,
        "pre_ko": dict(PRE_KO),
        "mo_market_id": "1.100",
        "mo_status": "OPEN",
        "odds": {
            "home": {"back": 2.7, "lay": 2.74, "back_size": 300.0, "lay_size": 250.0,
                     "selection_id": 11},
            "draw": {"back": 2.1, "lay": 2.12, "back_size": 400.0, "lay_size": 300.0,
                     "selection_id": 33},
            "away": {"back": 6.4, "lay": 6.6, "back_size": 120.0, "lay_size": 90.0,
                     "selection_id": 22},
        },
        "ou": [{
            "market_id": "1.777", "status": "OPEN", "market_type": "OVER_UNDER_75",
            "line": 7.5, "ts_ms": 1_000_000_000_000,
            "selections": [
                _sel(901, "Over 7.5", back=9.0, lay=12.0, back_size=15.0, lay_size=8.0),
                _sel(902, "Under 7.5", back=1.10, lay=1.12, back_size=120.0, lay_size=90.0),
            ],
        }],
        "timeline": [{"update_id": 1, "type": "GOAL", "minute": 12},
                     {"update_id": 2, "type": "GOAL", "minute": 40}],
    }
    base.update(over)
    return base


NOW = 1_000_000_010.0        # 10 s dopo il ts_ms dei blocchi: prezzo fresco


def _lam(payload):
    got = resolve_lambdas(payload, fixture=None)
    assert got is not None
    return (got[0], got[1]), got[2]


def _eval(model: OpportunityModel, payload: dict, now_ts: float = NOW):
    lam, league = _lam(payload)
    return model.evaluate(payload, sport="calcio", lambdas=lam, league_id=league, now_ts=now_ts)


# ------------------------------------------------------------------- λ
def test_resolve_lambdas_fixture_ha_la_precedenza():
    fixture = {"inputs": {"lambda_home": 1.9, "lambda_away": 0.8, "league_id": 135,
                          "ht_ratio_home": 0.44, "ht_ratio_away": 0.47}}
    got = resolve_lambdas(payload_1_1_65(), fixture=fixture)
    assert got == (1.9, 0.8, 135, "fixture")
    assert ht_ratio_from_fixture(fixture) == (0.44, 0.47)


def test_resolve_lambdas_fallback_pre_ko_e_none():
    got = resolve_lambdas(payload_1_1_65(), fixture=None)
    assert got is not None and got[3] == "pre_ko"
    assert got[0] > 0 and got[1] > 0 and got[0] > got[1]   # favorita in casa
    # nessun pre_ko e nessuna fixture: nessun modello possibile
    assert resolve_lambdas({"pre_ko": None}, fixture=None) is None
    assert resolve_lambdas({}, fixture={"inputs": {"lambda_home": 0}}) is None
    assert ht_ratio_from_fixture(None) is None


# ---------------------------------------------------------------- book: sanity
def test_book_esiti_gia_decisi_sono_esatti():
    m = OpportunityModel()
    lam, _ = _lam(payload_1_1_65())
    b = m.book(payload_1_1_65(), lambdas=lam, league_id=None)
    # 1-1 al 65': 2 gol gia' fatti
    assert b["over_1_5"] == 1.0 and b["under_1_5"] == 0.0
    assert b["over_0_5"] == 1.0 and b["under_0_5"] == 0.0
    assert b["btts_yes"] == 1.0 and b["btts_no"] == 0.0
    # 0-1: Under 0.5 e' gia' perso, Gol/NoGol ancora aperto
    p2 = payload_1_1_65(score_home=0, score_away=1)
    b2 = m.book(p2, lambdas=lam, league_id=None)
    assert b2["under_0_5"] == 0.0 and b2["over_0_5"] == 1.0
    assert 0.0 < b2["btts_yes"] < 1.0


def test_book_ogni_mercato_somma_a_uno():
    m = OpportunityModel()
    lam, _ = _lam(payload_1_1_65())
    b = m.book(payload_1_1_65(minute=20), lambdas=lam, league_id=None)
    assert b["home"] + b["draw"] + b["away"] == pytest.approx(1.0, abs=1e-9)
    assert b["ht_home"] + b["ht_draw"] + b["ht_away"] == pytest.approx(1.0, abs=1e-9)
    for line in DEFAULT_OPP_PARAMS["ou_lines"]:
        k = str(float(line)).replace(".", "_")
        assert b[f"over_{k}"] + b[f"under_{k}"] == pytest.approx(1.0, abs=1e-9)
    assert b["btts_yes"] + b["btts_no"] == pytest.approx(1.0, abs=1e-9)
    # CORRECT SCORE: celle 0-3 + i tre aggregati "Any Other" = 1
    cells = sum(v for k, v in b.items()
                if k.startswith("cs_") and not k.startswith("cs_any"))
    aggr = b["cs_any_other_home"] + b["cs_any_other_away"] + b["cs_any_other_draw"]
    assert cells + aggr == pytest.approx(1.0, abs=1e-9)
    # HALF TIME SCORE: celle + "Any Unquoted" = 1
    hts = sum(v for k, v in b.items()
              if k.startswith("hts_") and not k.startswith("hts_any"))
    assert hts + b["hts_any_unquoted"] == pytest.approx(1.0, abs=1e-9)


def test_book_monotono_nel_minuto():
    """A punteggio fermo, piu' il tempo passa piu' l'Under diventa probabile."""
    m = OpportunityModel()
    lam, _ = _lam(payload_1_1_65())
    prev = -1.0
    for minute in (10, 30, 50, 70, 85):
        b = m.book(payload_1_1_65(minute=minute), lambdas=lam, league_id=None)
        assert b["under_2_5"] > prev
        prev = b["under_2_5"]
    # e il 1X2 del primo tempo sparisce dopo il 45' (mercato regolato)
    assert "ht_home" not in m.book(payload_1_1_65(minute=60), lambdas=lam, league_id=None)


def test_book_i_rossi_spostano_le_probabilita():
    m = OpportunityModel()
    lam, _ = _lam(payload_1_1_65())
    base = m.book(payload_1_1_65(minute=50), lambdas=lam, league_id=None)
    rosso = m.book(payload_1_1_65(minute=50, red_home=1), lambdas=lam, league_id=None)
    assert rosso["home"] < base["home"]


# ------------------------------------------------------ evaluate: caso reale
def test_evaluate_trova_il_back_reale_under_75():
    m = OpportunityModel()
    opps = _eval(m, payload_1_1_65())
    under = [o for o in opps if o["selection_name"] == "Under 7.5"]
    assert len(under) == 1
    o = under[0]
    assert o["side"] == "back"
    assert o["market_type"] == "OVER_UNDER" and o["line"] == 7.5
    assert o["market_id"] == "1.777" and o["selection_id"] == 902
    assert o["price"] == 1.10 and o["size_available"] == 120.0
    assert o["p_model"] > 0.999
    assert o["edge"] == pytest.approx(o["p_model"] - 1 / 1.10, abs=1e-6)
    assert o["edge"] > DEFAULT_OPP_PARAMS["min_edge"]
    assert o["ev"] > 0.0 and 0.0 < o["confidence"] <= 1.0
    assert o["minute"] == 65 and o["score"] == "1-1"
    # de-vig sui runner dello stesso mercato: p_implied < 1/quota grezza
    assert o["p_implied"] < 1 / 1.10
    assert o["rationale"].startswith("Under 7.5 @1.10 sul 1-1 al 65':")
    assert "P(<=7 gol)=99.9%" in o["rationale"]
    assert "120 EUR abbinabili" in o["rationale"]
    assert o["rationale"].isascii()      # console Windows cp1252


def test_evaluate_trova_il_lay_sullimpossibile():
    """Over 7.5 all'1-1 al 65' e' quasi impossibile: lay a quota bassa = valore."""
    p = payload_1_1_65()
    p["ou"][0]["selections"][0] = _sel(901, "Over 7.5", back=2.5, lay=2.6,
                                       back_size=50.0, lay_size=200.0)
    opps = _eval(OpportunityModel(), p)
    lays = [o for o in opps if o["side"] == "lay" and o["selection_name"] == "Over 7.5"]
    assert len(lays) == 1
    o = lays[0]
    assert o["price"] == 2.6 and o["size_available"] == 200.0
    assert o["edge"] == pytest.approx(1 / 2.6 - o["p_model"], abs=1e-6)
    assert o["rationale"].startswith("LAY Over 7.5 @2.60 sul 1-1 al 65':")


def test_evaluate_lay_rifiuta_quota_troppo_alta():
    p = payload_1_1_65()
    p["ou"][0]["selections"][0] = _sel(901, "Over 7.5", back=20.0, lay=21.0,
                                       back_size=50.0, lay_size=200.0)
    opps = _eval(OpportunityModel(), p)
    assert not [o for o in opps if o["side"] == "lay"]   # oltre max_lay_price


# ------------------------------------------------------------- gate: liquidita
def test_gate_liquidita():
    p = payload_1_1_65()
    p["ou"][0]["selections"][1]["back_size"] = 5.0     # sotto min_size
    assert not [o for o in _eval(OpportunityModel(), p) if o["selection_name"] == "Under 7.5"]
    # con una soglia piu' bassa la stessa situazione e' di nuovo un'opportunita'
    m = OpportunityModel({"min_size": 1.0})
    assert [o for o in _eval(m, p) if o["selection_name"] == "Under 7.5"]


def test_gate_mercato_non_open_e_runner_non_attivo():
    p = payload_1_1_65()
    p["ou"][0]["status"] = "SUSPENDED"
    assert not [o for o in _eval(OpportunityModel(), p) if o["market_id"] == "1.777"]
    p2 = payload_1_1_65()
    p2["ou"][0]["selections"][1]["runner_status"] = "REMOVED"
    assert not [o for o in _eval(OpportunityModel(), p2) if o["selection_id"] == 902]


def test_gate_non_inplay_e_dati_mancanti():
    m = OpportunityModel()
    assert _eval(m, payload_1_1_65(inplay=False)) == []
    assert _eval(m, payload_1_1_65(minute=None)) == []
    assert _eval(m, payload_1_1_65(score_home=None)) == []


# ------------------------------------------------------------ gate: cooldown
def test_gate_cooldown_post_gol():
    m = OpportunityModel()
    # gol al 64': al 65' sono passati 60 s < 90 s di cooldown -> silenzio
    p = payload_1_1_65(timeline=[{"update_id": 3, "type": "GOAL", "minute": 64}])
    assert _eval(m, p) == []
    # gol al 63': 120 s > 90 s -> si torna a segnalare
    p2 = payload_1_1_65(timeline=[{"update_id": 3, "type": "GOAL", "minute": 63}])
    assert _eval(m, p2)
    # un tentativo non e' un gol
    p3 = payload_1_1_65(timeline=[{"update_id": 3, "type": "GOAL_ATTEMPT", "minute": 65}])
    assert _eval(m, p3)
    # cooldown disattivabile
    assert _eval(OpportunityModel({"post_goal_cooldown_s": 0.0}), p)


def test_cooldown_usa_il_timestamp_quando_c_e():
    m = OpportunityModel()
    p = payload_1_1_65(timeline=[{"type": "GOAL", "minute": 10,
                                  "ts_ms": int((NOW - 5) * 1000)}])
    assert _eval(m, p) == []


# -------------------------------------------------------------- gate: hazard
def _atlas(p_next: float) -> dict:
    """Atlante finto col solo livello globale per il bucket 65-70, 2 gol."""
    return {"global": {"65-70": {"2": {"p_goal_next_3min": p_next, "n": 1000}}}}


def _model_hazard(payload) -> float:
    from Betfair.stream.engine.live_engine_pro import event_goal_hazard
    lam, league = _lam(payload)
    h = event_goal_hazard(
        score_home=payload["score_home"], score_away=payload["score_away"],
        minute=payload["minute"], prematch_lambda_home=lam[0],
        prematch_lambda_away=lam[1], league_id=league, horizon_min=3.0,
    )
    assert h is not None
    return float(h["p_next"])


def test_hazard_coerente_non_penalizza():
    p = payload_1_1_65()
    m = OpportunityModel(atlas=_atlas(_model_hazard(p)))
    o = [x for x in _eval(m, p) if x["selection_name"] == "Under 7.5"][0]
    assert "hazard coerente con l'atlante" in o["rationale"]


def test_hazard_divergente_dimezza_la_confidenza():
    p = payload_1_1_65()
    base = [x for x in _eval(OpportunityModel(atlas=_atlas(_model_hazard(p))), p)
            if x["selection_name"] == "Under 7.5"][0]
    # atlante = modello/1.4 -> divergenza 40% (tra warn 30% e drop 60%)
    warn = OpportunityModel(atlas=_atlas(_model_hazard(p) / 1.4))
    o = [x for x in _eval(warn, p) if x["selection_name"] == "Under 7.5"][0]
    assert o["confidence"] == pytest.approx(base["confidence"] / 2, abs=1e-3)
    assert "hazard divergente dall'atlante" in o["rationale"]


def test_hazard_troppo_divergente_scarta_tutto():
    p = payload_1_1_65()
    drop = OpportunityModel(atlas=_atlas(_model_hazard(p) / 2.0))   # divergenza 100%
    assert _eval(drop, p) == []


def test_senza_atlante_il_controincrocio_e_dichiarato():
    o = [x for x in _eval(OpportunityModel(), payload_1_1_65())
         if x["selection_name"] == "Under 7.5"][0]
    assert "atlante assente" in o["rationale"]


# ------------------------------------------------------ lambda di default
def test_lambda_di_default_penalizzano_la_confidenza():
    """Senza fonte pre-match il bot usa lambda generici: la confidenza va
    moltiplicata per default_lambda_confidence e la rationale lo dichiara."""
    assert DEFAULT_OPP_PARAMS["default_lambda_confidence"] == pytest.approx(0.6)
    p = payload_1_1_65()
    lam, league = _lam(p)
    m = OpportunityModel()
    base = [x for x in m.evaluate(p, sport="calcio", lambdas=lam, league_id=league, now_ts=NOW)
            if x["selection_name"] == "Under 7.5"][0]
    dflt = [x for x in m.evaluate(p, sport="calcio", lambdas=lam, league_id=league, now_ts=NOW,
                                  lambda_source="default")
            if x["selection_name"] == "Under 7.5"][0]
    assert dflt["confidence"] == pytest.approx(base["confidence"] * 0.6, abs=1e-3)
    assert "lambda di default" in dflt["rationale"]
    assert "lambda di default" not in base["rationale"]
    # penalita' configurabile
    m2 = OpportunityModel({"default_lambda_confidence": 0.3})
    d2 = [x for x in m2.evaluate(p, sport="calcio", lambdas=lam, league_id=league, now_ts=NOW,
                                 lambda_source="default")
          if x["selection_name"] == "Under 7.5"][0]
    assert d2["confidence"] == pytest.approx(base["confidence"] * 0.3, abs=1e-3)


# ------------------------------------------------------------------- de-vig
def test_devig_moltiplicativo_sui_runner_del_mercato():
    m = OpportunityModel()
    runners = [{"back": 2.0}, {"back": 2.0}]           # overround 100% -> 50/50
    got = m._devig(runners)
    assert sorted(got.values()) == pytest.approx([0.5, 0.5])
    runners = [{"back": 1.5}, {"back": 2.5}]           # 0.6667+0.4 = 1.0667
    got = list(m._devig(runners).values())
    assert sum(got) == pytest.approx(1.0)
    assert got[0] == pytest.approx((1 / 1.5) / (1 / 1.5 + 1 / 2.5))
    # un solo prezzo valido: niente da normalizzare
    assert list(m._devig([{"back": 4.0}, {"back": None}]).values()) == pytest.approx([0.25])
    assert m._devig([{"back": None}]) == {}


# ----------------------------------------------------------- freschezza prezzo
def test_prezzo_stantio_abbassa_la_confidenza_e_poi_taglia():
    m = OpportunityModel()
    p = payload_1_1_65()
    fresh = [o for o in _eval(m, p, NOW) if o["selection_name"] == "Under 7.5"][0]
    stale = [o for o in _eval(m, p, NOW + 30) if o["selection_name"] == "Under 7.5"][0]
    dead = [o for o in _eval(m, p, NOW + 300) if o["selection_name"] == "Under 7.5"][0]
    assert fresh["confidence"] > stale["confidence"] > dead["confidence"]


# ------------------------------------------------------------ ranking e tetto
def test_ranking_per_ev_per_confidenza_e_tetto():
    """Molte linee quotate: l'ordine e' ev*confidenza decrescente, il tetto tiene."""
    p = payload_1_1_65()
    p["ou"] = [
        {"market_id": f"1.{700 + i}", "status": "OPEN", "line": line,
         "market_type": "OVER_UNDER", "ts_ms": 1_000_000_000_000,
         "selections": [
             _sel(1000 + i, f"Over {line}", back=9.0, lay=3.0, back_size=300.0, lay_size=300.0),
             _sel(2000 + i, f"Under {line}", back=1.05 + 0.01 * i, lay=1.30,
                  back_size=500.0, lay_size=500.0),
         ]}
        for i, line in enumerate((2.5, 3.5, 4.5, 5.5, 6.5, 7.5))
    ]
    # soglie larghe: qui interessa l'ORDINE e il TETTO, non la selettivita'
    larghe = {"min_prob_back": 0.5, "max_prob_lay": 0.5}
    tutte = _eval(OpportunityModel({**larghe, "max_per_event": 100}), p)
    assert len(tutte) > DEFAULT_OPP_PARAMS["max_per_event"]
    scores = [o["ev"] * o["confidence"] for o in tutte]
    assert scores == sorted(scores, reverse=True)
    tagliate = _eval(OpportunityModel(larghe), p)
    assert len(tagliate) == DEFAULT_OPP_PARAMS["max_per_event"]
    assert tagliate == tutte[: DEFAULT_OPP_PARAMS["max_per_event"]]
    tre = _eval(OpportunityModel({**larghe, "max_per_event": 3}), p)
    assert tre == tutte[:3]


# ------------------------------------------------------- altri mercati del feed
def test_mercati_btts_ht_result_cs_vengono_prezzati():
    p = payload_1_1_65(minute=30, score_home=0, score_away=0, timeline=[])
    p["btts"] = {"market_id": "1.800", "status": "OPEN",
                 "market_type": "BOTH_TEAMS_TO_SCORE", "ts_ms": 1_000_000_000_000,
                 "selections": [_sel(1, "Yes", back=2.5, lay=2.6, back_size=200.0, lay_size=200.0),
                                _sel(2, "No", back=1.6, lay=1.65, back_size=200.0, lay_size=200.0)]}
    p["ht_result"] = {"market_id": "1.801", "status": "OPEN",
                      "market_type": "HALF_TIME", "ts_ms": 1_000_000_000_000,
                      "selections": [
                          _sel(11, "Nord FC", back=6.0, lay=6.2, back_size=100.0, lay_size=100.0),
                          _sel(22, "Sud FC", back=12.0, lay=13.0, back_size=100.0, lay_size=100.0),
                          _sel(33, "The Draw", back=1.35, lay=1.37, back_size=400.0, lay_size=400.0),
                      ]}
    p["cs"] = {"market_id": "1.802", "status": "OPEN", "ts_ms": 1_000_000_000_000,
               "selections": [
                   _sel(41, "0 - 0", back=3.5, lay=3.6, back_size=200.0, lay_size=200.0),
                   _sel(42, "3 - 3", back=2.2, lay=2.3, back_size=200.0, lay_size=200.0),
                   _sel(43, "Any Other Home Win", back=15.0, lay=16.0,
                        back_size=200.0, lay_size=200.0),
               ]}
    opps = _eval(OpportunityModel(), p)
    tipi = {o["market_type"] for o in opps}
    # il 3-3 a 2.30 lay al 30' sullo 0-0 e' un lay quasi certo: deve uscire
    assert "CORRECT_SCORE" in tipi
    tremi = [o for o in opps if o["selection_name"] == "3 - 3"]
    assert tremi and tremi[0]["side"] == "lay"
    # il mercato HALF_TIME sparisce dopo il 45'
    p2 = dict(p, minute=60)
    assert not [o for o in _eval(OpportunityModel(), p2) if o["market_type"] == "HALF_TIME"]


def test_match_odds_dal_blocco_odds_storico():
    """Il 1X2 usa il blocco `odds` di sempre (nessuna chiave nuova richiesta)."""
    p = payload_1_1_65(minute=88, score_home=3, score_away=0)
    p["odds"]["home"] = {"back": 1.06, "lay": 1.08, "back_size": 900.0,
                         "lay_size": 500.0, "selection_id": 11}
    opps = [o for o in _eval(OpportunityModel(), p) if o["market_type"] == "MATCH_ODDS"]
    casa = [o for o in opps if o["selection_name"] == "Nord FC"]
    assert len(casa) == 1
    assert casa[0]["side"] == "back" and casa[0]["market_id"] == "1.100"
    assert casa[0]["selection_id"] == 11 and casa[0]["p_model"] > 0.98
    # sul 3-0 all'88' il pareggio e' un lay quasi gratis: c'e' anche quello
    pari = [o for o in opps if o["selection_name"] == "The Draw"]
    assert pari and pari[0]["side"] == "lay"


# --------------------------------------------------------------- casi vuoti
def test_tennis_e_dati_assenti_non_producono_nulla():
    m = OpportunityModel()
    assert m.evaluate({"inplay": True, "minute": 30}, sport="tennis",
                      lambdas=(1.4, 1.1), league_id=None, now_ts=NOW) == []
    # niente pre_ko: resolve_lambdas -> None -> nessuna valutazione, nessuna eccezione
    senza = payload_1_1_65(pre_ko=None)
    assert resolve_lambdas(senza, fixture=None) is None
    assert m.evaluate(senza, sport="calcio", lambdas=None, league_id=None, now_ts=NOW) == []
    assert m.evaluate(senza, sport="calcio", lambdas=(0.0, 1.0), league_id=None,
                      now_ts=NOW) == []
    assert m.evaluate(None, sport="calcio", lambdas=(1.4, 1.1), league_id=None,
                      now_ts=NOW) == []


def test_payload_senza_mercati_non_esplode():
    m = OpportunityModel()
    nudo = {"inplay": True, "minute": 70, "score_home": 1, "score_away": 0,
            "pre_ko": dict(PRE_KO)}
    assert _eval(m, nudo) == []


# ======================================================================
# tools/validate_opportunity.py — affidabilita' sulle registrazioni
# ======================================================================
from Betfair.safe_strategy.tools import validate_opportunity as V  # noqa: E402


def _write_recording(tmp_path, event_id="99", *, goals_at=(20, 70), final=(2, 0)):
    """Registrazione sintetica nel formato reale di `_live_raw/<evento>/`."""
    d = tmp_path / event_id
    d.mkdir()
    rows = []
    sh = sa = 0
    for minute in range(0, 91):
        if minute == goals_at[0]:
            sh = 1
        if minute == goals_at[1]:
            sh = final[0]
            sa = final[1]
        rows.append({"ts_ms": 1_700_000_000_000 + minute * 60_000, "minute": minute,
                     "score_home": sh, "score_away": sa})
    (d / f"{event_id}.scores.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    raw = [
        {"op": "mcm", "mc": [{"id": "1.1", "marketDefinition": {
            "marketType": "MATCH_ODDS", "inPlay": False,
            "runners": [{"id": 1, "sortPriority": 1}, {"id": 2, "sortPriority": 2},
                        {"id": 3, "sortPriority": 3}]},
            "rc": [{"id": 1, "atb": [[1.90, 100.0], [1.80, 50.0]]},
                   {"id": 2, "atb": [[4.20, 100.0]]},
                   {"id": 3, "atb": [[3.50, 100.0]]}]}]},
        # il best back di casa sale a 2.00, poi quel livello viene tolto (size 0)
        {"op": "mcm", "mc": [{"id": "1.1", "rc": [{"id": 1, "atb": [[2.00, 30.0]]}]}]},
        {"op": "mcm", "mc": [{"id": "1.1", "rc": [{"id": 1, "atb": [[2.00, 0.0]]}]}]},
        {"op": "mcm", "mc": [{"id": "1.1", "marketDefinition": {
            "marketType": "MATCH_ODDS", "inPlay": True, "runners": []}}]},
        # dopo il kickoff i prezzi non contano piu': non devono entrare nel pre-KO
        {"op": "mcm", "mc": [{"id": "1.1", "rc": [{"id": 1, "atb": [[9.99, 500.0]]}]}]},
    ]
    (d / f"{event_id}.raw.jsonl").write_text(
        "\n".join(json.dumps(r) for r in raw), encoding="utf-8")
    return str(tmp_path)


def test_validate_carica_punteggi_e_congela_il_pre_ko(tmp_path):
    data_dir = _write_recording(tmp_path)
    scores = V.load_scores(data_dir, "99")
    assert len(scores) == 91 and scores[0][1] == 0 and scores[-1][2:] == (2, 0)
    assert V.load_scores(data_dir, "inesistente") == []
    pre = V.prematch_1x2(data_dir, "99")
    assert pre == {"home": 1.90, "away": 4.20, "draw": 3.50}   # 2.00 rimosso, 9.99 in-play
    assert V.available_events(data_dir) == ["99"]


def test_validate_esiti_reali():
    assert V.realised("home", 2, 0) == 1 and V.realised("home", 0, 1) == 0
    assert V.realised("draw", 1, 1) == 1
    assert V.realised("away", 0, 1) == 1
    assert V.realised("btts_yes", 2, 0) == 0 and V.realised("btts_yes", 2, 1) == 1
    assert V.realised("over_1_5", 2, 0) == 1 and V.realised("over_2_5", 2, 0) == 0
    assert V.realised("over_7_5", 5, 3) == 1
    assert V.realised("mercato_ignoto", 1, 1) is None


def test_validate_replay_e_tabella_di_affidabilita(tmp_path):
    data_dir = _write_recording(tmp_path)
    samples = V.replay_event(data_dir, "99", step_min=5)
    assert samples, "il replay deve produrre campioni dalle quote pre-KO"
    minuti = sorted({s.minute for s in samples})
    assert minuti == list(range(0, 90, 5))
    # esito reale coerente col risultato finale 2-0 (non con lo stato del minuto)
    assert {s.outcome for s in samples if s.market == "home"} == {1}
    assert {s.outcome for s in samples if s.market == "draw"} == {0}
    assert {s.outcome for s in samples if s.market == "btts_yes"} == {0}
    assert {s.outcome for s in samples if s.market == "over_1_5"} == {1}
    assert {s.outcome for s in samples if s.market == "over_2_5"} == {0}
    # la probabilita' di 'home' cresce col tempo (2-0 dal 70')
    per_minuto = {s.minute: s.p_model for s in samples if s.market == "home"}
    assert per_minuto[85] > per_minuto[50] > per_minuto[0]

    rows = V.reliability(samples, bucket_min=45)
    assert {r.bucket for r in rows} == {"0-45", "45-90"}
    for r in rows:
        assert r.n > 0
        assert r.error == pytest.approx(r.p_mean - r.realised_rate, abs=1e-12)
        assert 0.0 <= r.brier <= 1.0
    table = V.format_table(rows)
    assert table.isascii() and "mercato" in table and "brier" in table


def test_validate_senza_dati_non_esplode(tmp_path):
    assert V.replay_event(str(tmp_path), "nessuno") == []
    assert V.prematch_1x2(str(tmp_path), "nessuno") is None
    assert V.available_events(str(tmp_path / "boh")) == []
    # punteggi presenti ma nessuna quota pre-KO: niente λ -> nessun campione
    d = tmp_path / "77"
    d.mkdir()
    (d / "77.scores.jsonl").write_text(
        json.dumps({"ts_ms": 1, "minute": 10, "score_home": 0, "score_away": 0}),
        encoding="utf-8")
    assert V.replay_event(str(tmp_path), "77") == []
    # con i λ passati a mano invece funziona
    assert V.replay_event(str(tmp_path), "77", lambdas=(1.4, 1.1))


def test_validate_main_su_registrazione_sintetica(tmp_path, capsys):
    data_dir = _write_recording(tmp_path)
    csv = tmp_path / "out.csv"
    rc = V.main(["--data-dir", data_dir, "--event", "99", "--bucket", "45",
                 "--step", "5", "--csv", str(csv)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.isascii() and "Brier medio" in out
    assert csv.read_text(encoding="utf-8").startswith("mercato,fascia,n,")
    assert V.main(["--data-dir", str(tmp_path / "vuoto")]) == 1
