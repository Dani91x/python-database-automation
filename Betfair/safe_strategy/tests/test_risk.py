"""Test del motore di RISCHIO (risk.py), modulo puro. File ASCII-only."""
from __future__ import annotations

from datetime import datetime, timezone

from Betfair.safe_strategy import risk as RK

P = {"max_open_trades": 20, "risk": RK.merge_risk_params(None)}


def _t(event_id="1.1", market_type="MATCH_ODDS", liability=10.0, status="open", **kw):
    row = {"event_id": event_id, "market_type": market_type, "liability": liability,
           "status": status, "strategy": "base"}
    row.update(kw)
    return row


def _cand(event_id="1.1", market_type="MATCH_ODDS", liability=10.0, strategy="base"):
    return {"event_id": event_id, "market_type": market_type, "liability": liability,
            "strategy": strategy}


def _params(**risk):
    return {"max_open_trades": 20, "risk": RK.merge_risk_params(risk)}


# ---------------------------------------------------------------------------
# parametri
# ---------------------------------------------------------------------------
def test_default_e_clamp_dei_parametri():
    d = RK.merge_risk_params(None)
    assert d["daily_liability_cap"] == 500 and d["per_event_liability_cap"] == 150
    assert d["per_event_max_trades"] == 3 and d["max_open_trades"] is None
    assert d["correlated_cap"] == 0.7 and d["daily_loss_stop"] == -50
    assert d["model_stake"] == 5 and d["model_daily_liability_cap"] == 150
    m = RK.merge_risk_params({"daily_liability_cap": -5, "correlated_cap": 3,
                              "daily_loss_stop": 20, "per_event_max_trades": -1,
                              "max_open_trades": 7, "sconosciuta": 1, "model_stake": "x"})
    assert m["daily_liability_cap"] == 0.0 and m["correlated_cap"] == 1.0
    # review H2: il SEGNO del loss stop si interpreta (20 = "fermati a -20"),
    # non si azzera: clamparlo a 0 SPEGNEVA lo stop perdite in silenzio
    assert m["daily_loss_stop"] == -20.0 and m["per_event_max_trades"] == 0
    assert RK.merge_risk_params({"daily_loss_stop": 0})["daily_loss_stop"] == 0.0
    assert RK.merge_risk_params({"daily_loss_stop": -30})["daily_loss_stop"] == -30.0
    assert m["max_open_trades"] == 7 and m["model_stake"] == 5.0
    assert "sconosciuta" not in m
    # max_open_trades None -> quello del bot
    assert RK.risk_params({"max_open_trades": 12})["max_open_trades"] == 12
    assert RK.risk_params({"max_open_trades": 12, "risk": {"max_open_trades": 3}})["max_open_trades"] == 3


def test_giornata_operativa_europe_rome():
    # estate (CEST, UTC+2): 10/09 20:00 UTC -> mezzanotte locale = 09/09 22:00 UTC
    s = RK.operating_day_start(datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc))
    assert s == datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc)
    # dopo la mezzanotte locale (23:30 UTC = 01:30 locali dell'11/09)
    s = RK.operating_day_start(datetime(2026, 9, 10, 23, 30, tzinfo=timezone.utc))
    assert s == datetime(2026, 9, 10, 22, 0, tzinfo=timezone.utc)
    # inverno (CET, UTC+1)
    s = RK.operating_day_start(datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc))
    assert s == datetime(2026, 1, 14, 23, 0, tzinfo=timezone.utc)
    # riserva senza tzdata: stessa risposta
    assert RK._rome_offset(datetime(2026, 9, 10, 20, tzinfo=timezone.utc)).total_seconds() == 7200
    assert RK._rome_offset(datetime(2026, 1, 15, 12, tzinfo=timezone.utc)).total_seconds() == 3600


# ---------------------------------------------------------------------------
# regole
# ---------------------------------------------------------------------------
def test_loss_stop_giornaliero_blocca_i_nuovi_ingressi_ma_non_il_manuale():
    assert RK.check([], _cand(), -50.0, P) == (False, "daily_loss_stop")
    assert RK.check([], _cand(), -49.99, P) == (True, None)
    assert RK.loss_stop_active(-60, P) and not RK.loss_stop_active(-10, P)
    # manuale (soft): il loss stop non si applica
    assert RK.check([], _cand(), -500.0, P, soft=True) == (True, None)
    # 0 = disattivo
    assert RK.check([], _cand(), -999.0, _params(daily_loss_stop=0)) == (True, None)


def test_max_open_trades_e_posizioni_per_evento():
    open_ = [_t(event_id=str(i)) for i in range(20)]
    assert RK.check(open_, _cand("9.9"), 0.0, P) == (False, "max_open_trades")
    assert RK.check(open_, _cand("9.9"), 0.0, P, soft=True)[0] is True
    # 3 posizioni sullo stesso evento: la quarta e' bloccata, un altro evento passa
    same = [_t(market_type=m, liability=5.0) for m in ("MATCH_ODDS", "CORRECT_SCORE", "OVER_UNDER_25")]
    assert RK.check(same, _cand("1.1", "BOTH_TEAMS_TO_SCORE", 5.0), 0.0, P) == (False, "per_event_max_trades")
    assert RK.check(same, _cand("2.2", "MATCH_ODDS", 5.0), 0.0, P) == (True, None)
    # le gambe di chiusura e le righe regolate non contano
    legs = same + [_t(closes_trade_id=1), _t(status="won"), _t(status="error")]
    assert RK.event_count(legs, "1.1") == 3 and RK.open_count(legs) == 3


def test_cap_liability_per_evento_correlata():
    # stesso mercato conta al 100%: 100 + 60 = 160 > 150
    open_ = [_t(market_type="MATCH_ODDS", liability=100.0)]
    assert RK.check(open_, _cand(market_type="MATCH_ODDS", liability=60.0), 0.0, P) == (False, "per_event_liability_cap")
    # mercato diverso pesa 0.7: 70 + 60 = 130 <= 150
    assert RK.check(open_, _cand(market_type="CORRECT_SCORE", liability=60.0), 0.0, P) == (True, None)
    assert RK.event_exposure(open_, "1.1", "CORRECT_SCORE", 0.7) == 70.0
    # peso 1.0: torna 160 -> bloccato; anche il manuale rispetta il cap per evento
    assert RK.check(open_, _cand(market_type="CORRECT_SCORE", liability=60.0), 0.0,
                    _params(correlated_cap=1.0)) == (False, "per_event_liability_cap")
    assert RK.check(open_, _cand(market_type="MATCH_ODDS", liability=60.0), 0.0, P, soft=True) == (False, "per_event_liability_cap")
    # altro evento: esposizione zero
    assert RK.check(open_, _cand("2.2", "MATCH_ODDS", 149.0), 0.0, P) == (True, None)


def test_cap_liability_giornaliera_totale_e_di_modello():
    assert RK.check([], _cand(liability=30.0), 0.0, P, day_liability=480.0) == (False, "daily_liability_cap")
    assert RK.check([], _cand(liability=20.0), 0.0, P, day_liability=480.0) == (True, None)
    assert RK.check([], _cand(liability=30.0), 0.0, P, day_liability=480.0, soft=True) == (False, "daily_liability_cap")
    # cap dei soli trade di modello: 148 + 5 > 150 -> bloccato; un segnale 'base' passa
    assert RK.check([], _cand(liability=5.0, strategy="model"), 0.0, P,
                    day_liability_model=148.0) == (False, "model_daily_liability_cap")
    assert RK.check([], _cand(liability=5.0, strategy="base"), 0.0, P,
                    day_liability_model=148.0) == (True, None)
    # cap a 0 = disattivi
    p0 = _params(daily_liability_cap=0, model_daily_liability_cap=0, per_event_liability_cap=0)
    assert RK.check([], _cand(liability=9999.0, strategy="model"), 0.0, p0,
                    day_liability=9999.0, day_liability_model=9999.0) == (True, None)


def test_ordine_dei_motivi_e_candidato_incompleto():
    open_ = [_t(liability=200.0)]
    # loss stop vince su tutto
    assert RK.check(open_, _cand(liability=50.0), -100.0, P, day_liability=1000.0)[1] == "daily_loss_stop"
    # liability assente = 0: passano solo i conteggi
    assert RK.check([], {"event_id": "1.1"}, 0.0, P) == (True, None)
