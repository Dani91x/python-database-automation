"""Test delle regole di USCITA automatica (exits: track + decide), modulo puro.

Una regola per test, secondo il manuale operativo. File ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import exits as XE

T0 = 1_000_000.0
P = XE.merge_exit_params(None)


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------
def _trade(strategy="base", side="lay", selection_id=8, score="1-0",
           market_type="MATCH_ODDS", **kw):
    row = {"id": 1, "event_id": "1.1", "strategy": strategy, "side": side,
           "selection_id": selection_id, "market_type": market_type,
           "score_at_entry": score, "minute_at_entry": 56, "origin": "auto",
           "status": "open", "meta": {}}
    row.update(kw)
    return row


def _calcio(minute=60, sh=1, sa=0, red_home=0, red_away=0, mo_status="OPEN"):
    """Feed calcio: casa = selezione 7, ospite = selezione 8, favorita = casa."""
    return {"inplay": True, "minute": minute, "score_home": sh, "score_away": sa,
            "red_home": red_home, "red_away": red_away, "mo_status": mo_status,
            "odds": {"home": {"selection_id": 7, "back": 1.5, "lay": 1.52},
                     "draw": {"selection_id": 9, "back": 4.0, "lay": 4.2},
                     "away": {"selection_id": 8, "back": 9.0, "lay": 9.5}},
            "cs": {"market_id": "cs1", "status": "OPEN",
                   "any_other_home": {"selection_id": 501, "back": 20.0, "lay": 22.0},
                   "any_other_away": {"selection_id": 502, "back": 40.0, "lay": 44.0}}}


def _tennis(sets=(1, 0), games=(4, 2)):
    """Feed tennis: p1 = selezione 11, p2 = selezione 12."""
    return {"inplay": True, "mo_status": "OPEN",
            "sets": {"p1": sets[0], "p2": sets[1]},
            "games": {"p1": games[0], "p2": games[1]},
            "odds": {"p1": {"selection_id": 11, "back": 1.3, "lay": 1.32},
                     "p2": {"selection_id": 12, "back": 4.0, "lay": 4.4}}}


def _step(trade, feeds, params=P, t0=T0, step=2.0):
    """Applica in sequenza i feed (un ciclo ciascuno); ritorna (meta, decisione)."""
    meta = dict(trade.get("meta") or {})
    dec = None
    now = t0
    for f in feeds:
        meta = XE.track({**trade, "meta": meta}, f, now)
        dec = XE.decide(trade, f, meta, now, params)
        now += step
    return meta, dec


# ---------------------------------------------------------------------------
# parametri e parsing
# ---------------------------------------------------------------------------
def test_parametri_default_e_merge_con_clamp():
    assert P["enabled"] is True
    assert P["base_exit_minute"] == 80 and P["esatto_exit_minute"] == 72
    assert P["punta_exit_minute"] == 83 and P["loss_settle_delay_s"] == 30
    assert P["red_card_fav_exit"] is True and P["exit_max_retries"] == 3
    assert P["tennis_take_profit_next_game"] is True
    assert P["tennis_exit_on_lost_game"] is False
    m = XE.merge_exit_params({"base_exit_minute": "82", "loss_settle_delay_s": -5,
                              "exit_max_retries": 0, "enabled": "false", "ignota": 1})
    assert m["base_exit_minute"] == 82 and m["loss_settle_delay_s"] == 0.0
    assert m["exit_max_retries"] == 1 and m["enabled"] is False
    assert "ignota" not in m
    assert XE.exit_params({"exits": {"punta_exit_minute": 85}})["punta_exit_minute"] == 85
    assert XE.exit_params({})["punta_exit_minute"] == 83


def test_parsing_punteggi():
    assert XE.parse_calcio_score("1-0") == (1, 0)
    assert XE.parse_calcio_score("2 - 1") == (2, 1)
    assert XE.parse_calcio_score(None) is None and XE.parse_calcio_score("?-?") is None
    assert XE.parse_tennis_score("set 1-0 \u00b7 game 4-2") == ((1, 0), (4, 2))
    assert XE.parse_tennis_score("set 0-1") == ((0, 1), None)


def test_lato_posizione_per_strategia():
    f = _calcio()
    assert XE.position_side(_trade("base", "lay", 8), f) == "home", "lay ospite -> favorita casa"
    assert XE.position_side(_trade("punta", "back", 7, "2-0"), f) == "home"
    assert XE.position_side(_trade("esatto", "lay", 502, market_type="CORRECT_SCORE"), f) == "away"
    assert XE.position_side(_trade("tennis", "back", 12, "set 0-1 \u00b7 game 1-3"),
                            _tennis()) == "p2"
    # senza selezioni nel feed: dal punteggio d'ingresso / chiave del segnale
    assert XE.position_side(_trade("base", "lay", 8, "0-2"), {}) == "away"
    assert XE.position_side(_trade("esatto", "lay", 0, signal_key="1.1:esatto:home:1-0",
                                   market_type="CORRECT_SCORE"), {}) == "home"
    assert XE.position_side(_trade("esatto", "lay", 0, selection_name="Altro risultato Ospite",
                                   market_type="CORRECT_SCORE"), {}) == "away"
    assert XE.position_side(_trade("tennis", "back", 0, "set 1-0 \u00b7 game 2-2"), {}) == "p1"
    assert XE.position_side(_trade("base", "lay", 8, "1-1"), {}) is None


def test_feed_fresco_e_mercato_aperto():
    row = {"updated_at": T0 - 5}
    assert XE.feed_is_fresh(row, T0)
    assert not XE.feed_is_fresh({"updated_at": T0 - 60}, T0)
    assert XE.feed_is_fresh({"updated_at": T0 - 60}, T0, scanner_ts=T0 - 3), "scanner vivo"
    assert not XE.feed_is_fresh(None, T0, scanner_ts=T0)
    assert XE.market_open(_trade(), _calcio(mo_status="SUSPENDED")) is False
    assert XE.market_open(_trade("esatto", market_type="CORRECT_SCORE"), _calcio()) is True
    assert XE.market_open(_trade(), {}) is None


# ---------------------------------------------------------------------------
# BASE
# ---------------------------------------------------------------------------
def test_base_profit_quando_la_favorita_segna_ancora():
    meta, dec = _step(_trade("base"), [_calcio(60, 1, 0), _calcio(66, 2, 0)])
    assert dec is not None and dec.kind == "profit"
    assert meta["exit_track"]["goals_since_entry_home"] == 1
    assert dec.not_before_ts == pytest.approx(T0 + 2.0 + 30.0), "dopo l'assestamento"


def test_base_time_al_minuto_80_senza_altri_gol():
    _, dec = _step(_trade("base"), [_calcio(60), _calcio(79)])
    assert dec is None
    _, dec = _step(_trade("base"), [_calcio(60), _calcio(80)])
    assert dec is not None and dec.kind == "time" and dec.not_before_ts == 0.0
    custom = XE.merge_exit_params({"base_exit_minute": 83})
    _, dec = _step(_trade("base"), [_calcio(60), _calcio(82)], params=custom)
    assert dec is None


def test_base_loss_al_pareggio_con_ritardo_di_assestamento():
    meta, dec = _step(_trade("base"), [_calcio(60, 1, 0), _calcio(70, 1, 1)])
    assert dec is not None and dec.kind == "loss"
    assert meta["exit_track"]["last_goal_ts"] == T0 + 2.0
    assert dec.not_before_ts == T0 + 2.0 + 30.0
    # il ritardo e' parametrico
    fast = XE.merge_exit_params({"loss_settle_delay_s": 20})
    _, dec = _step(_trade("base"), [_calcio(60, 1, 0), _calcio(70, 1, 1)], params=fast)
    assert dec.not_before_ts == T0 + 2.0 + 20.0


def test_base_loss_ha_la_precedenza_e_il_sorpasso_e_loss():
    _, dec = _step(_trade("base"), [_calcio(60, 1, 0), _calcio(70, 1, 2)])
    assert dec.kind == "loss"
    # pareggio poi nuovo vantaggio della favorita: la decisione segue lo stato corrente
    _, dec = _step(_trade("base"), [_calcio(60, 1, 0), _calcio(70, 1, 1), _calcio(75, 2, 1)])
    assert dec.kind == "profit"


def test_base_rosso_alla_favorita_esce_alla_sfavorita_no():
    meta, dec = _step(_trade("base"), [_calcio(60), _calcio(65, red_home=1)])
    assert dec is not None and dec.kind == "red_card"
    assert dec.not_before_ts == T0 + 2.0 + 30.0
    _, dec = _step(_trade("base"), [_calcio(60), _calcio(65, red_away=1)])
    assert dec is None, "rosso alla sfavorita: nessuna azione"
    off = XE.merge_exit_params({"red_card_fav_exit": False})
    _, dec = _step(_trade("base"), [_calcio(60), _calcio(65, red_home=1)], params=off)
    assert dec is None
    # rosso gia' presente all'ingresso: non e' un evento nuovo
    _, dec = _step(_trade("base"), [_calcio(60, red_home=1), _calcio(65, red_home=1)])
    assert dec is None


# ---------------------------------------------------------------------------
# ESATTO
# ---------------------------------------------------------------------------
def _esatto(sel=501, score="1-0"):
    return _trade("esatto", "lay", sel, score, market_type="CORRECT_SCORE")


def test_esatto_time_al_minuto_72_se_il_lato_bancato_non_ha_segnato():
    _, dec = _step(_esatto(), [_calcio(50), _calcio(71)])
    assert dec is None
    _, dec = _step(_esatto(), [_calcio(50), _calcio(72)])
    assert dec.kind == "time"
    # un gol dell'ALTRO lato non tocca la posizione
    _, dec = _step(_esatto(), [_calcio(50, 1, 0), _calcio(60, 1, 1)])
    assert dec is None


def test_esatto_loss_quando_il_lato_bancato_segna():
    meta, dec = _step(_esatto(), [_calcio(50, 1, 0), _calcio(60, 2, 0)])
    assert dec.kind == "loss" and dec.not_before_ts == T0 + 2.0 + 30.0
    assert meta["exit_track"]["side"] == "home"
    # lato ospite bancato: e' il gol dell'ospite a far uscire
    _, dec = _step(_esatto(502, "0-1"), [_calcio(50, 0, 1), _calcio(60, 1, 1)])
    assert dec is None
    _, dec = _step(_esatto(502, "0-1"), [_calcio(50, 0, 1), _calcio(60, 0, 2)])
    assert dec.kind == "loss"


# ---------------------------------------------------------------------------
# PUNTA
# ---------------------------------------------------------------------------
def _punta(score="2-0"):
    return _trade("punta", "back", 7, score)


def test_punta_profit_quando_la_favorita_segna_ancora():
    _, dec = _step(_punta(), [_calcio(68, 2, 0), _calcio(75, 3, 0)])
    assert dec.kind == "profit" and dec.not_before_ts == T0 + 2.0 + 30.0


def test_punta_time_al_minuto_83():
    _, dec = _step(_punta(), [_calcio(68, 2, 0), _calcio(82, 2, 0)])
    assert dec is None
    _, dec = _step(_punta(), [_calcio(68, 2, 0), _calcio(83, 2, 0)])
    assert dec.kind == "time"


def test_punta_loss_appena_la_favorita_subisce_anche_se_resta_avanti():
    _, dec = _step(_punta(), [_calcio(68, 2, 0), _calcio(75, 2, 1)])
    assert dec.kind == "loss" and dec.not_before_ts == T0 + 2.0 + 30.0
    # il rosso alla favorita NON e' una regola della variante punta
    _, dec = _step(_punta(), [_calcio(68, 2, 0), _calcio(75, 2, 0, red_home=1)])
    assert dec is None


# ---------------------------------------------------------------------------
# TENNIS
# ---------------------------------------------------------------------------
def _tt(score="set 1-0 \u00b7 game 4-2", sel=11):
    return _trade("tennis", "back", sel, score)


def test_tennis_profit_quando_il_leader_vince_il_game_successivo():
    meta, dec = _step(_tt(), [_tennis((1, 0), (4, 2)), _tennis((1, 0), (5, 2))])
    assert dec.kind == "profit" and dec.not_before_ts == 0.0
    tr = meta["exit_track"]
    assert tr["games_won"] == 1 and tr["games_lost"] == 0 and tr["last_game"] == "won"
    hold = XE.merge_exit_params({"tennis_take_profit_next_game": False})
    _, dec = _step(_tt(), [_tennis((1, 0), (4, 2)), _tennis((1, 0), (5, 2))], params=hold)
    assert dec is None, "hold fino alla fine"


def test_tennis_loss_su_game_perso_solo_se_abilitata():
    meta, dec = _step(_tt(), [_tennis((1, 0), (4, 2)), _tennis((1, 0), (4, 3))])
    assert dec is None
    assert meta["exit_track"]["consecutive_lost"] == 1
    on = XE.merge_exit_params({"tennis_exit_on_lost_game": True})
    _, dec = _step(_tt(), [_tennis((1, 0), (4, 2)), _tennis((1, 0), (4, 3))], params=on)
    assert dec.kind == "loss"


def test_tennis_uscita_obbligatoria_due_game_persi_di_fila_e_parita():
    feeds = [_tennis((1, 0), (4, 2)), _tennis((1, 0), (4, 3)), _tennis((1, 0), (4, 4))]
    meta, dec = _step(_tt(), feeds)
    assert dec.kind == "mandatory"
    assert meta["exit_track"]["consecutive_lost"] == 2 and meta["exit_track"]["games_level"]
    # due persi di fila ma NON in parita' (5-2 -> 5-3 -> 5-4): nessun obbligo
    feeds = [_tennis((1, 0), (5, 2)), _tennis((1, 0), (5, 3)), _tennis((1, 0), (5, 4))]
    _, dec = _step(_tt("set 1-0 \u00b7 game 5-2"), feeds)
    assert dec is None
    # parita' ma game persi NON consecutivi (2-1 -> 2-2 -> 3-2 -> 3-3): un game
    # vinto in mezzo azzera la serie; take-profit spento per isolare la regola
    hold = XE.merge_exit_params({"tennis_take_profit_next_game": False})
    feeds = [_tennis((1, 0), (2, 1)), _tennis((1, 0), (2, 2)), _tennis((1, 0), (3, 2)),
             _tennis((1, 0), (3, 3))]
    meta, dec = _step(_tt("set 1-0 \u00b7 game 2-1"), feeds, params=hold)
    assert dec is None and meta["exit_track"]["consecutive_lost"] == 1
    # l'obbligo vince anche sul take-profit spento e sul leader p2
    feeds = [_tennis((0, 1), (2, 4)), _tennis((0, 1), (3, 4)), _tennis((0, 1), (4, 4))]
    _, dec = _step(_tt("set 0-1 \u00b7 game 2-4", sel=12), feeds, params=hold)
    assert dec.kind == "mandatory"


def test_tennis_cambio_set_azzera_il_conteggio_dei_game():
    hold = XE.merge_exit_params({"tennis_take_profit_next_game": False})
    # il leader perde l'ultimo game del set (5-6 -> set perso), poi 0-0: niente obbligo
    feeds = [_tennis((1, 0), (5, 5)), _tennis((1, 0), (5, 6)), _tennis((1, 1), (0, 0))]
    meta, dec = _step(_tt("set 1-0 \u00b7 game 5-5"), feeds, params=hold)
    tr = meta["exit_track"]
    assert tr["consecutive_lost"] == 0 and tr["set_index"] == 2
    assert tr["games_lost"] == 2 and tr["last_game"] == "lost"
    assert dec is None
    # il leader chiude il set (5-2 -> 6-2): e' un game vinto -> profit
    feeds = [_tennis((1, 0), (5, 2)), _tennis((2, 0), (0, 0))]
    meta, dec = _step(_tt("set 1-0 \u00b7 game 5-2"), feeds)
    assert dec.kind == "profit" and meta["exit_track"]["games_won"] == 1


def test_tennis_ripresa_dopo_riavvio_parte_dal_punteggio_di_ingresso():
    """Bot riavviato dopo l'ingresso: il primo feed osservato e' gia' 5-2 e il
    game in piu' rispetto all'ingresso (4-2) conta come vinto."""
    _, dec = _step(_tt(), [_tennis((1, 0), (5, 2))])
    assert dec.kind == "profit"


# ---------------------------------------------------------------------------
# generali
# ---------------------------------------------------------------------------
def test_disabilitato_o_strategia_esclusa_non_decide_mai():
    off = XE.merge_exit_params({"enabled": False})
    _, dec = _step(_trade("base"), [_calcio(60), _calcio(85, 2, 0)], params=off)
    assert dec is None
    for strat in ("model", "manual"):
        _, dec = _step(_trade(strat), [_calcio(60), _calcio(85, 1, 1)])
        assert dec is None


def test_track_idempotente_e_senza_dati_non_decide():
    t = _trade("base")
    m1 = XE.track(t, _calcio(60), T0)
    m2 = XE.track({**t, "meta": m1}, _calcio(60), T0 + 2)
    assert m1 == m2, "stesso feed -> stesso tracciamento (write-on-change)"
    # feed senza punteggio: nessuna decisione (mai inventare)
    _, dec = _step(_trade("base"), [{"minute": 85}])
    assert dec is None
    assert XE.decide(_trade("base"), {}, {}, T0, P) is None


def test_situazione_per_il_log():
    assert XE.situation(_trade("base"), _calcio(77, 2, 1)) == {"minute": 77, "score": "2-1"}
    assert XE.situation(_tt(), _tennis((1, 0), (4, 3))) == {
        "minute": None, "score": "set 1-0 \u00b7 game 4-3"}


# ---------------------------------------------------------------------------
# decisione a MODELLO per le uscite in profitto (pura)
# ---------------------------------------------------------------------------
def test_decide_time_exit_caso_trade_12_e_soglie():
    # trade 12: lay 2@60, chiusura -4.0, P(perdita) 0.1% -> HOLD margine ampio
    assert XE.decide_time_exit(0.001, -4.0, 2.0, 2.0, P, loss_if_lose=118.0) == (
        "hold", "margine ampio: P(perdita)=0.1%, tengo fino al settlement")
    # rischio oltre il cap -> EXIT
    act, why = XE.decide_time_exit(0.15, -4.0, 2.0, 2.0, P, loss_if_lose=118.0)
    assert act == "exit" and why.startswith("rischio alto: P(perdita)=15.0% >= 10%")
    # profitto bloccato -> EXIT sempre, anche con rischio alto
    act, why = XE.decide_time_exit(0.5, 0.3, 2.0, 2.0, P, loss_if_lose=118.0)
    assert act == "exit" and why == "profitto bloccato +0,30 €: esco"
    assert XE.decide_time_exit(0.001, 0.0, 2.0, 2.0, P)[0] == "exit"
    # zona intermedia: EV(tengo) = 0.95*2 - 0.05*118 = -4.0
    act, why = XE.decide_time_exit(0.05, -4.0, 2.0, 2.0, P, loss_if_lose=118.0)
    assert act == "exit" and why.startswith("tenere non rende: EV(tengo)=-4,00")
    act, why = XE.decide_time_exit(0.05, -6.0, 2.0, 2.0, P, loss_if_lose=118.0)
    assert act == "hold" and why.startswith("EV(tengo)=-4,00 € > bloccato -6,00")
    assert XE.ev_hold(0.05, 2.0, 118.0) == -4.0
    # P ignota e chiusura in perdita -> HOLD (fail-closed)
    assert XE.decide_time_exit(None, -1.0, 2.0, 2.0, P)[0] == "hold"
    # loss_if_lose assente = caso back (perdita = stake)
    act, _ = XE.decide_time_exit(0.05, -1.0, 4.0, 10.0, P)   # EV = 3.8-0.5 = 3.3
    assert act == "hold"
    custom = XE.merge_exit_params({"hold_max_risk": 0.2, "ev_margin": 3})
    assert XE.decide_time_exit(0.15, -4.0, 2.0, 2.0, custom, loss_if_lose=118.0)[0] == "hold"
    assert XE.decide_time_exit(0.3, -6.0, 2.0, 2.0,
                               XE.merge_exit_params({"risk_cap": 0.5, "ev_margin": 3}),
                               loss_if_lose=118.0)[0] == "exit", "-6 >= EV(-34.4)-3"


def test_testi_ui_e_mappa_kind():
    assert XE.EXIT_KIND_UI["mandatory"] == "forced" and XE.EXIT_KIND_UI["red_card"] == "red_card"
    assert XE.reason_text("time", "minuto_80_senza_altri_gol") == "Uscita a tempo al 80': green-up"
    assert XE.reason_text("profit", "favorita_segna_ancora") == "La favorita ha segnato ancora: green-up"
    assert XE.reason_text("loss", "sconosciuto_x") == "Sconosciuto x"
    m = XE.merge_exit_params({"hold_max_risk": -1, "risk_cap": 2, "ev_margin": -5})
    assert m["hold_max_risk"] == 0.0 and m["risk_cap"] == 1.0 and m["ev_margin"] == 0.0
    assert XE.spread_ratio({"back": 20.0, "lay": 60.0}) == 3.0
    assert XE.spread_ratio({"back": None, "lay": 60.0}) is None
    assert XE.spread_ratio({"back": 1.0, "lay": 1.01}) is None


# ---------------------------------------------------------------------------
# TRADE DI MODELLO: parametri, linea decisa, situazione, decide_model
# ---------------------------------------------------------------------------
def _model(market_type="OVER_UNDER_25", selection_name="Under 2.5 Goals", side="back",
           sport="calcio", **kw):
    kw.setdefault("selection_id", 47973)
    return _trade(strategy="model", side=side, market_type=market_type,
                  selection_name=selection_name, sport=sport, **kw)


def test_parametri_modello_default_e_clamp():
    assert P["model_exit_p_lose"] == 0.10 and P["model_take_profit_frac"] == 0.8
    assert P["model_free_cashout_p_lose"] == 0.005
    m = XE.merge_exit_params({"model_exit_p_lose": 5, "model_take_profit_frac": -1,
                              "model_free_cashout_p_lose": 0.02})
    assert m["model_exit_p_lose"] == 1.0 and m["model_take_profit_frac"] == 0.0
    assert m["model_free_cashout_p_lose"] == 0.02
    assert XE.MODEL_STRATEGIES == ("model",) and "model" not in XE.EXIT_STRATEGIES


def test_linea_decisa_contro():
    under = _model()
    assert XE.line_decided_against(under, 2, 1) is True
    assert XE.line_decided_against(under, 1, 1) is False
    assert XE.line_decided_against(under, None, 1) is False
    over = _model(selection_name="Over 2.5 Goals")
    assert XE.line_decided_against(over, 2, 1) is False          # decisa A FAVORE
    assert XE.line_decided_against(_model(selection_name="Over 2.5 Goals", side="lay"), 2, 1) is True
    assert XE.line_decided_against(_model(selection_name="Under 2.5 Goals", side="lay"), 2, 1) is False
    # linea da meta.line (market_type generico 'OVER_UNDER')
    t = _model(market_type="OVER_UNDER", selection_name="Under", meta={"line": 1.5})
    assert XE.ou_line(t) == 1.5 and XE.line_decided_against(t, 1, 1) is True
    assert XE.ou_line(_model(market_type="OVER_UNDER", selection_name="Under 3.5 Goals")) == 3.5
    assert XE.line_decided_against(_model(market_type="OVER_UNDER", selection_name="Under"), 5, 5) is False
    # BTTS
    assert XE.line_decided_against(_model("BOTH_TEAMS_TO_SCORE", "No"), 1, 1) is True
    assert XE.line_decided_against(_model("BOTH_TEAMS_TO_SCORE", "Yes"), 1, 1) is False
    assert XE.line_decided_against(_model("BOTH_TEAMS_TO_SCORE", "Yes", side="lay"), 1, 1) is True
    assert XE.line_decided_against(_model("BOTH_TEAMS_TO_SCORE", "No"), 1, 0) is False
    # Correct Score puntato superato; il lay e "altro risultato" mai
    assert XE.line_decided_against(_model("CORRECT_SCORE", "1 - 0"), 2, 0) is True
    assert XE.line_decided_against(_model("CORRECT_SCORE", "1 - 0"), 1, 0) is False
    assert XE.line_decided_against(_model("CORRECT_SCORE", "1 - 0", side="lay"), 2, 0) is False
    assert XE.line_decided_against(_model("CORRECT_SCORE", "Any Other Home Win"), 5, 0) is False
    # Match Odds: mai prima del fischio finale
    assert XE.line_decided_against(_model("MATCH_ODDS", "Home"), 0, 5) is False


def test_situazione_modello_calcio_gol_e_rosso():
    t = _model("MATCH_ODDS", "Away", side="lay", selection_id=8, score="1-0")
    meta, _ = _step(t, [_calcio(60, 1, 0)])
    sit = XE.model_situation(t, meta, _calcio(60, 1, 0), P)
    assert sit == {"adverse_event": None, "not_before_ts": 0.0, "decided_against": False}
    meta, _ = _step(t, [_calcio(60, 1, 0), _calcio(66, 1, 1)])
    sit = XE.model_situation(t, meta, _calcio(66, 1, 1), P)
    assert sit["adverse_event"] == "gol" and sit["not_before_ts"] == T0 + 2.0 + 30.0
    meta, _ = _step(t, [_calcio(60, 1, 0), _calcio(66, 1, 0, red_home=1)])
    sit = XE.model_situation(t, meta, _calcio(66, 1, 0, red_home=1), P)
    assert sit["adverse_event"] == "rosso" and sit["not_before_ts"] == T0 + 32.0
    # linea decisa: anche senza gol "dopo l'ingresso" nel tracciamento
    u = _model(score="2-1")
    meta, _ = _step(u, [_calcio(70, 2, 1)])
    assert XE.model_situation(u, meta, _calcio(70, 2, 1), P)["decided_against"] is True


def test_situazione_modello_tennis_due_game_o_set():
    # back del giocatore 1 (sel 11): tracciato per SPORT (strategia 'model')
    t = _model("MATCH_ODDS", "P1", sport="tennis", score="set 1-0 . game 4-2")
    t["selection_id"] = 11
    meta, _ = _step(t, [_tennis((1, 0), (4, 2)), _tennis((1, 0), (4, 3)), _tennis((1, 0), (4, 4))])
    assert meta["exit_track"]["side"] == "p1" and meta["exit_track"]["consecutive_lost"] == 2
    assert XE.model_situation(t, meta, _tennis((1, 0), (4, 4)), P)["adverse_event"] == "due_game_persi_di_fila"
    meta, _ = _step(t, [_tennis((1, 0), (4, 2)), _tennis((1, 1), (0, 0))])
    assert XE.model_situation(t, meta, _tennis((1, 1), (0, 0)), P)["adverse_event"] == "set_perso"
    # lay dell'avversario (sel 12) = stessa posizione "p1 deve vincere"
    lay = _model("MATCH_ODDS", "P2", side="lay", sport="tennis", score="set 1-0 . game 4-2")
    lay["selection_id"] = 12
    meta, _ = _step(lay, [_tennis((1, 0), (4, 2))])
    assert meta["exit_track"]["side"] == "p1"
    # game vinto: nessun evento avverso
    meta, _ = _step(t, [_tennis((1, 0), (4, 2)), _tennis((1, 0), (5, 2))])
    assert XE.model_situation(t, meta, _tennis((1, 0), (5, 2)), P)["adverse_event"] is None
    assert XE.situation(t, _tennis((1, 0), (5, 2)))["score"] == "set 1-0 \u00b7 game 5-2"


def _sit(adverse=None, nb=0.0, decided=False):
    return {"adverse_event": adverse, "not_before_ts": nb, "decided_against": decided}


def test_decide_model_evento_avverso():
    d = XE.decide_model(p_lose=0.2, p_lose_entry=0.05, locked=-1.0, max_profit=10.0,
                        situation=_sit("gol", 123.0), params=P)
    assert d == XE.ExitDecision("loss", "gol_avverso", 123.0)
    # sotto soglia: si tiene
    assert XE.decide_model(p_lose=0.08, p_lose_entry=0.05, locked=-1.0, max_profit=10.0,
                           situation=_sit("gol"), params=P) is None
    # il gol ha AIUTATO (p_lose scesa rispetto all'ingresso): si tiene
    assert XE.decide_model(p_lose=0.3, p_lose_entry=0.45, locked=-1.0, max_profit=10.0,
                           situation=_sit("gol"), params=P) is None
    # ingresso ignoto: basta la soglia
    assert XE.decide_model(p_lose=0.3, p_lose_entry=None, locked=-1.0, max_profit=10.0,
                           situation=_sit("gol"), params=P).reason == "gol_avverso"
    # rosso -> kind red_card; p_lose ignota -> nessuna uscita per evento
    assert XE.decide_model(p_lose=0.5, p_lose_entry=0.1, locked=-1.0, max_profit=10.0,
                           situation=_sit("rosso", 9.0), params=P) == XE.ExitDecision("red_card", "rosso_avverso", 9.0)
    assert XE.decide_model(p_lose=None, p_lose_entry=0.1, locked=-1.0, max_profit=10.0,
                           situation=_sit("gol"), params=P) is None
    # linea decisa contro: prima di tutto, anche se il P&L bloccato fosse buono
    assert XE.decide_model(p_lose=1.0, p_lose_entry=0.1, locked=9.0, max_profit=10.0,
                           situation=_sit(decided=True, nb=5.0), params=P) == XE.ExitDecision("loss", "linea_decisa_contro", 5.0)
    # tennis: incondizionata e immediata
    assert XE.decide_model(p_lose=0.01, p_lose_entry=0.2, locked=-1.0, max_profit=10.0,
                           situation=_sit("due_game_persi_di_fila"), params=P) == XE.ExitDecision("loss", "due_game_persi_di_fila", 0.0)
    assert XE.decide_model(p_lose=None, p_lose_entry=None, locked=None, max_profit=None,
                           situation=_sit("set_perso"), params=P).reason == "set_perso"


def test_decide_model_take_profit_e_cashout_quasi_gratis():
    tp = XE.decide_model(p_lose=0.1, p_lose_entry=0.1, locked=8.0, max_profit=10.0,
                         situation=_sit(), params=P)
    assert tp == XE.ExitDecision("profit", "take_profit_modello", 0.0)
    assert XE.decide_model(p_lose=0.1, p_lose_entry=0.1, locked=7.9, max_profit=10.0,
                           situation=_sit(), params=P) is None
    # cash-out quasi gratis: P(perdita) <= 0.5% e bloccato >= 0
    fc = XE.decide_model(p_lose=0.004, p_lose_entry=0.1, locked=0.1, max_profit=10.0,
                         situation=_sit(), params=P)
    assert fc == XE.ExitDecision("profit", "cashout_quasi_gratis", 0.0)
    assert XE.decide_model(p_lose=0.004, p_lose_entry=0.1, locked=-0.1, max_profit=10.0,
                           situation=_sit(), params=P) is None
    assert XE.decide_model(p_lose=0.006, p_lose_entry=0.1, locked=0.1, max_profit=10.0,
                           situation=_sit(), params=P) is None
    # senza numeri: si tiene; frazione 0 = take profit disattivo
    assert XE.decide_model(p_lose=None, p_lose_entry=None, locked=None, max_profit=None,
                           situation=_sit(), params=P) is None
    assert XE.decide_model(p_lose=0.1, p_lose_entry=0.1, locked=10.0, max_profit=10.0,
                           situation=_sit(), params=XE.merge_exit_params({"model_take_profit_frac": 0})) is None
    # testi UI
    assert XE.reason_text("loss", "gol_avverso").startswith("Gol avverso")
    assert XE.reason_text("profit", "take_profit_modello") == "Take profit del modello: profitto bloccato"
    assert XE.reason_text("loss", "linea_decisa_contro").startswith("La linea tradata")
