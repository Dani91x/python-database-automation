"""CECCHINO (spec utente 16/07) — i 3 momenti del theta in un bot solo.

Coperture:
  STEP 1 (pre-match PERSIST): finestra KO-5', ordine PERSIST, una sola
    finestra per partita, escalation taker a KO-3.5', target ADATTIVO al
    fischio (profitto→gained+bonus / loss→1 tick), timeout adattivo Atlante,
    sospensione del turn in-play (0-0) NON è un gol, gol vero → flat,
    timeout → flat, verde accreditato col net reale.
  STEP 2+3 (combo): ingresso quiete come il classico E ingresso overshoot
    post-gol che bypassa finestre/quiete/max_goals, entry TAKER, scratch
    accorciato se l'Atlante teme il secondo gol rapido.
  FILO ROSSO: presi target_greens verdi il bot si ferma per la partita.

Riusa le fixture della suite theta 15/07 (stesso harness book/strategy).
"""
from __future__ import annotations

import pytest
from flumine.order.order import OrderStatus

from Betfair.stream.scalper.theta_bot import (
    THETA_PRESETS,
    prematch_exit_ticks,
    prematch_timeout_s,
)
from Betfair.stream.tests.test_theta_bot_2026_07_15 import (
    KO_MS,
    _FakeMarket,
    _FakeOrder,
    _book,
    _strategy,
)


# ------------------------------------------------------------------ preset
def test_preset_cecchino_configura_i_tre_step():
    p = THETA_PRESETS["cecchino"]
    assert p["prematch"] is True                 # STEP 1
    assert p["overshoot_combo"] is True          # STEP 2+3 nella stessa sessione
    assert p["overshoot_only"] is False
    assert p["target_greens"] == 3               # filo rosso
    s = _strategy(preset="cecchino")
    assert s.theta_preset == "cecchino"
    assert s.theta_prematch is True
    assert s.theta_overshoot_combo is True
    assert s.theta_target_greens == 3


# ------------------------------------------------- STEP 1: funzioni pure
def test_prematch_exit_ticks_adattivo():
    # in LOSS o pari al KO → ci si accontenta di 1 tick
    assert prematch_exit_ticks(1.90, 1.95) == 1
    assert prematch_exit_ticks(1.90, 1.90) == 1
    assert prematch_exit_ticks(1.90, None) == 1
    # in PROFITTO → tick guadagnati + bonus (default 2)
    assert prematch_exit_ticks(1.90, 1.87) == 3 + 2
    assert prematch_exit_ticks(1.90, 1.89, bonus_ticks=2) == 1 + 2
    assert prematch_exit_ticks(1.90, 1.87, bonus_ticks=0) == 3


def test_prematch_timeout_steps_atlante():
    assert prematch_timeout_s(0.04) == 300.0
    assert prematch_timeout_s(0.07) == 240.0
    assert prematch_timeout_s(0.10) == 180.0
    assert prematch_timeout_s(0.20) == 120.0
    assert prematch_timeout_s(None) == 120.0     # atlante muto = prudenza


# ------------------------------------------------- STEP 1: fuoco pre-match
def test_prematch_fire_persist_dentro_la_finestra():
    s = _strategy(goals=None, minute=None, preset="cecchino")
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(-240, inplay=False))   # KO-4'
    assert len(mkt.orders) == 1
    o = mkt.orders[0]
    assert o.side == "BACK"
    assert o.order_type.persistence_type == "PERSIST"       # regge il turn in-play
    assert o.order_type.price == pytest.approx(1.85)
    pos = s._p("1.234", 101)
    assert pos.prematch is True
    assert s.stats["prematch_shots"] == 1
    # UNA sola finestra per partita: nessun secondo fuoco
    pos.entries = []
    pos.prematch = False
    s.process_market_book(mkt, _book(-230, inplay=False))
    assert len(mkt.orders) == 1


def test_prematch_fuori_finestra_non_spara():
    s = _strategy(goals=None, minute=None, preset="cecchino")
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(-360, inplay=False))   # KO-6': troppo presto
    assert mkt.orders == []
    assert s._prematch_done is False


def test_prematch_dry_annuncia_e_basta():
    s = _strategy(goals=None, minute=None, preset="cecchino", dry_run=True)
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(-240, inplay=False))
    assert mkt.orders == []
    assert s._prematch_done is True
    assert any(k == "theta_prematch_dry" for k, _ in s._test_events)


def test_prematch_escalation_taker_in_due_fasi():
    # review 16/07: MAI cancel+place nello stesso tick (doppio fill) e il
    # take vero e' un limite SOTTO il best back (matcha al disponibile),
    # non al best lay (che resterebbe maker sopra il book)
    s = _strategy(goals=None, minute=None, preset="cecchino")
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    live = _FakeOrder("BACK", price=1.85, size=25.0, live=True)
    pos.entries = [live]
    pos.prematch = True
    s._prematch_done = True
    # FASE 1 a KO-3'20" (200s <= take_s 210): SOLO il cancel, nessun ordine
    s.process_market_book(mkt, _book(-200, inplay=False, bb=1.85, bl=1.86))
    assert live in mkt.cancelled
    assert pos.prematch_taken is True
    assert mkt.orders == []
    # cancel NON ancora confermato: ancora nessun ordine
    s.process_market_book(mkt, _book(-195, inplay=False, bb=1.85, bl=1.86))
    assert mkt.orders == []
    # FASE 2: ordine morto senza matched → taker SOTTO il best back
    live.status = OrderStatus.EXECUTION_COMPLETE
    live.size_remaining = 0.0
    s.process_market_book(mkt, _book(-190, inplay=False, bb=1.85, bl=1.86))
    assert len(mkt.orders) == 1
    o = mkt.orders[0]
    assert o.order_type.price == pytest.approx(1.82)   # bb − 3 tick: take vero
    assert o.order_type.persistence_type == "PERSIST"
    assert pos.prematch_take_placed is True
    # idempotente: nessun secondo taker
    s.process_market_book(mkt, _book(-185, inplay=False, bb=1.85, bl=1.86))
    assert len(mkt.orders) == 1


def test_prematch_escalation_fill_durante_il_cancel_non_raddoppia():
    # il maker si riempie MENTRE il cancel e' in volo: niente secondo ordine
    s = _strategy(goals=None, minute=None, preset="cecchino")
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    live = _FakeOrder("BACK", price=1.85, size=25.0, live=True)
    pos.entries = [live]
    pos.prematch = True
    s._prematch_done = True
    s.process_market_book(mkt, _book(-200, inplay=False))   # fase 1: cancel
    live.status = OrderStatus.EXECUTION_COMPLETE
    live.size_remaining = 0.0
    live.size_matched = 25.0                                 # fillato nel frattempo
    live.average_price_matched = 1.85
    s.process_market_book(mkt, _book(-195, inplay=False))
    assert mkt.orders == []                                  # NESSUN raddoppio
    assert pos.prematch_take_placed is False


def test_prematch_force_flat_pre_ko_cancella_e_non_riarma():
    # review 16/07: il kill-switch vale ANCHE pre-KO — il PERSIST resting si
    # cancella e l'escalation NON piazza ordini nuovi dopo lo stop
    s = _strategy(goals=None, minute=None, preset="cecchino")
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    live = _FakeOrder("BACK", price=1.85, size=25.0, live=True)
    pos.entries = [live]
    pos.prematch = True
    s._prematch_done = True
    s.force_flat = True
    s.process_market_book(mkt, _book(-200, inplay=False))
    assert live in mkt.cancelled
    assert mkt.orders == []                  # niente escalation dopo lo stop
    live.status = OrderStatus.EXECUTION_COMPLETE
    live.size_remaining = 0.0
    s.process_market_book(mkt, _book(-195, inplay=False))
    assert pos.entries == [] and pos.prematch is False


# ---------------------------------------------- STEP 1: al KO e in-play
def _prematch_pos(s, entry=1.90, matched=25.0):
    pos = s._p("1.234", 101)
    pos.entries = [_FakeOrder("BACK", price=entry, size=matched,
                              size_matched=matched, avg=entry)]
    pos.prematch = True
    s._prematch_done = True
    return pos


def test_prematch_target_adattivo_in_profitto():
    s = _strategy(goals=0, minute=1.0, preset="cecchino")
    mkt = _FakeMarket()
    pos = _prematch_pos(s, entry=1.90)
    # al KO la quota e' GIA' scesa a 1.87 (3 tick): target = 3+2 sotto 1.90
    s.process_market_book(mkt, _book(5, bb=1.87, bl=1.88))
    assert pos.prematch_exit_placed is True
    assert pos.close is not None
    assert pos.close.order_type.price == pytest.approx(1.85)
    # deadline ADATTIVA armata SUBITO col fill: hazard fixture 0.06 → 240s
    assert pos.prematch_deadline_ms == pytest.approx(KO_MS + 240_000.0)
    dl = [p for k, p in s._test_events if k == "theta_prematch_deadline"]
    assert dl and dl[0]["timeout_s"] == 240.0
    plan = [p for k, p in s._test_events if k == "theta_prematch_exit_plan"]
    assert plan and plan[0]["target_ticks"] == 5


def test_prematch_target_1_tick_in_loss():
    s = _strategy(goals=0, minute=1.0, preset="cecchino")
    mkt = _FakeMarket()
    pos = _prematch_pos(s, entry=1.90)
    # al KO la quota e' SALITA (loss): ci si accontenta di 1 tick da 1.90
    s.process_market_book(mkt, _book(5, bb=1.95, bl=1.96))
    assert pos.close is not None
    assert pos.close.order_type.price == pytest.approx(1.89)


def test_prematch_sospensione_del_turn_inplay_non_e_gol():
    s = _strategy(goals=0, minute=1.0, preset="cecchino")
    mkt = _FakeMarket()
    pos = _prematch_pos(s)
    pos.prematch_exit_placed = True
    pos.prematch_deadline_ms = KO_MS + 240_000.0
    s._postgol_mids.add("1.234")           # sospensione vista al turn in-play
    s.process_market_book(mkt, _book(10, bb=1.89, bl=1.90))
    assert pos.flattening is False          # punteggio 0-0: NON era un gol
    assert "1.234" not in s._postgol_mids


def test_prematch_gol_vero_flat_al_riprezzo():
    s = _strategy(goals=0, minute=1.0, preset="cecchino")
    mkt = _FakeMarket()
    pos = _prematch_pos(s)
    pos.prematch_exit_placed = True
    pos.prematch_deadline_ms = KO_MS + 240_000.0
    s.process_market_book(mkt, _book(10, bb=1.89, bl=1.90))  # ancora 0-0
    s.set_goals(1)                                            # GOL vero
    s._postgol_mids.add("1.234")
    s.process_market_book(mkt, _book(40, bb=2.30, bl=2.34))
    assert pos.flattening is True
    assert s.stats["postgol_closes"] == 1


def test_prematch_timeout_esposizione_flat():
    s = _strategy(goals=0, minute=3.0, preset="cecchino")
    mkt = _FakeMarket()
    pos = _prematch_pos(s)
    pos.prematch_exit_placed = True
    pos.prematch_deadline_ms = KO_MS + 120_000.0
    s.process_market_book(mkt, _book(119, bb=1.89, bl=1.90))
    assert pos.flattening is False           # dentro la finestra
    s.process_market_book(mkt, _book(125, bb=1.89, bl=1.90))
    assert pos.flattening is True            # esposizione massima: fuori
    assert s.stats["prematch_scratches"] == 1


def test_prematch_verde_accreditato_net_reale():
    s = _strategy(goals=0, minute=2.0, preset="cecchino")
    mkt = _FakeMarket()
    pos = _prematch_pos(s, entry=1.90, matched=25.0)
    pos.prematch_exit_placed = True
    pos.prematch_deadline_ms = KO_MS + 240_000.0
    size = round(25.0 * 1.90 / 1.85, 2)
    pos.close = _FakeOrder("LAY", price=1.85, size=size,
                           size_matched=size, avg=1.85)
    s.process_market_book(mkt, _book(60, bb=1.85, bl=1.86))
    nw = 25.0 * 0.90 - size * 0.85
    nl = size - 25.0
    assert s.stats["greens"] == 1
    assert s.stats["prematch_greens"] == 1
    assert s.stats["pnl_locked"] == pytest.approx(min(nw, nl))
    assert pos.prematch is False and pos.close is None


def test_prematch_unfilled_al_ko_niente_inseguimenti():
    s = _strategy(goals=0, minute=1.0, preset="cecchino")
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    live = _FakeOrder("BACK", price=1.85, size=25.0, live=True)  # MAI fillata
    pos.entries = [live]
    pos.prematch = True
    s._prematch_done = True
    s.process_market_book(mkt, _book(5))
    assert live in mkt.cancelled
    live.status = OrderStatus.EXECUTION_COMPLETE
    live.size_remaining = 0.0
    s.process_market_book(mkt, _book(8))
    assert pos.entries == [] and pos.prematch is False
    assert any(k == "theta_prematch_unfilled" for k, _ in s._test_events)


# ------------------------------------------------- STEP 2+3: combo cecchino
def test_combo_quiete_entra_come_il_classico():
    s = _strategy(goals=0, minute=20.0, preset="cecchino")
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200))
    assert len(mkt.orders) == 1              # quiete: maker al best
    assert mkt.orders[0].order_type.price == pytest.approx(1.85)


def test_combo_overshoot_bypassa_quiete_finestre_e_max_goals():
    # gol al 72' (fuori dalle finestre quiete 0-35/46-70), semaforo quiete
    # CHIUSO: l'ingresso overshoot passa lo stesso (compra il riprezzo)
    s = _strategy(goals=0, minute=72.0, preset="cecchino")
    s.risk_sem = __import__("types").SimpleNamespace(
        entries_halted=lambda now: True)
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(4300, mtype="OVER_UNDER_25"))  # arma _now_ms
    assert mkt.orders == []                  # quiete halted + fuori finestra
    s.set_goals(1)                           # GOL → linea diventa OU_35
    s._runner_names[("1.234", 101)] = "Under 3.5 Goals"
    s.process_market_book(
        mkt, _book(4360, mtype="OVER_UNDER_35", bb=1.85, bl=1.86))  # +60s
    assert len(mkt.orders) == 1
    o = mkt.orders[0]
    # STEP 3: TAKER sulla liquidita' (limite sotto il best: matcha subito)
    assert o.order_type.price == pytest.approx(1.82)
    pos = s._p("1.234", 101)
    # hazard fixture 0.06 NON > fast_hazard 0.06 → scratch overshoot pieno
    assert pos.scratch_override_s == pytest.approx(240.0)


def test_combo_overshoot_scratch_corto_se_secondo_gol_probabile():
    from Betfair.stream.tests.test_theta_bot_2026_07_15 import _atlas
    # minuto 72 (fuori finestre quiete) + semaforo quiete chiuso: l'unico
    # ingresso possibile e' l'overshoot — con hazard alto lo scratch e' corto
    s = _strategy(goals=0, minute=72.0, preset="cecchino",
                  atlas=_atlas(p_league=0.08), hazard_max=0.12)
    s.risk_sem = __import__("types").SimpleNamespace(
        entries_halted=lambda now: True)
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(4300, mtype="OVER_UNDER_25"))
    assert mkt.orders == []
    s.set_goals(1)
    s._runner_names[("1.234", 101)] = "Under 3.5 Goals"
    s.process_market_book(
        mkt, _book(4360, mtype="OVER_UNDER_35", bb=1.85, bl=1.86))
    assert len(mkt.orders) == 1
    pos = s._p("1.234", 101)
    # hazard 0.08 > fast_hazard 0.06 → l'Atlante teme il 2° gol: scratch 120s
    assert pos.scratch_override_s == pytest.approx(120.0)


def test_overshoot_preset_resta_maker_certificato():
    # review 16/07: la cella certificata C17 NON si cambia in silenzio —
    # il taker "caccia liquidita'" e' un override per-ingresso del CECCHINO
    assert THETA_PRESETS["overshoot"]["entry_mode"] == "maker"


def test_prematch_gol_fail_closed_feed_in_ritardo():
    # review 16/07: sospensione DOPO la grace del KO con punteggio ancora
    # 0-0 (feed lento) o IGNOTO → si flattena comunque (mai fidarsi del
    # silenzio del feed con una posizione aperta)
    s = _strategy(goals=0, minute=2.0, preset="cecchino")
    mkt = _FakeMarket()
    pos = _prematch_pos(s)
    pos.prematch_exit_placed = True
    pos.prematch_deadline_ms = KO_MS + 300_000.0
    s._postgol_mids.add("1.234")
    # 120s dopo il KO: fuori dalla grace del turn in-play → FLAT
    s.process_market_book(mkt, _book(120, bb=2.10, bl=2.14))
    assert pos.flattening is True
    assert s.stats["postgol_closes"] == 1


def test_prematch_close_lapsata_si_ripiazza():
    # review 16/07: close LAPSE morta senza matched (sospensione ignorata)
    # → il piano si ripiazza al book successivo (mai posizione senza uscita)
    s = _strategy(goals=0, minute=1.0, preset="cecchino")
    mkt = _FakeMarket()
    pos = _prematch_pos(s, entry=1.90)
    pos.prematch_exit_placed = True
    pos.prematch_deadline_ms = KO_MS + 240_000.0
    pos.close = _FakeOrder("LAY", price=1.85, size=25.68,
                           size_matched=0.0, live=False)   # morta, 0 matched
    s.process_market_book(mkt, _book(20, bb=1.89, bl=1.90))
    assert any(k == "theta_prematch_close_dead" for k, _ in s._test_events)
    assert pos.close is not None                     # RIPIAZZATA
    # target RICALCOLATO fresco: bb 1.89 < ingresso 1.90 = profitto di 1
    # tick → 1+bonus(2) = 3 tick sotto 1.90
    assert pos.close.order_type.price == pytest.approx(1.87)


# --------------------------------------------------- filo rosso del cecchino
def test_target_greens_ferma_il_cecchino():
    s = _strategy(goals=0, minute=20.0, preset="cecchino")
    assert s.theta_target_greens == 3
    s.stats["greens"] = 2
    s._check_target_greens()
    assert s._event_done is False            # 2 verdi: si continua
    s.stats["greens"] = 3
    s._check_target_greens()
    assert s._event_done is True             # 3 verdi: stop partita
    assert s.stats["target_greens_hits"] == 1
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200))
    assert mkt.orders == []                  # nessun nuovo ingresso


def test_prematch_reset_dopo_timeout_i_cicli_standard_non_ci_ricadono():
    # BUG backtest 16/07: senza reset del flag, dopo il flatten da timeout i
    # cicli standard successivi sullo stesso runner finivano nel gestore
    # pre-match (deadline gia' scaduta) → flatten immediato a ripetizione.
    s = _strategy(goals=0, minute=3.0, preset="cecchino")
    mkt = _FakeMarket()
    pos = _prematch_pos(s)
    pos.prematch_exit_placed = True
    pos.prematch_deadline_ms = KO_MS + 100_000.0
    s.process_market_book(mkt, _book(120, bb=1.89, bl=1.90))  # timeout → flat
    assert pos.flattening is True
    assert pos.prematch is False                    # ciclo pre-match CHIUSO
    assert pos.prematch_deadline_ms is None
    # nuovo ciclo standard sulla stessa posizione: NON passa dal pre-match
    pos.flattening = False
    pos.flatten_orders = []
    pos.entries = [_FakeOrder("BACK", price=1.85, size_matched=25.0, avg=1.85)]
    pos.entry_fill_pt = KO_MS + 1_210_000.0
    s.process_market_book(mkt, _book(1220, bb=1.85, bl=1.86))
    assert pos.flattening is False                  # niente flatten spurio
    assert pos.close is not None                    # green standard piazzato
    assert s.stats["prematch_scratches"] == 1       # contatore NON gonfiato
