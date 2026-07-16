"""THETA SCALPER (theta_bot.ThetaStrategy) + fix infra 15/07 — logica pura.

Coperture:
  1. ATLANTE: bucket/chiavi, catena squadre→lega→globale, fail-closed.
  2. COPPIA ATOMICA: theta_pair (green spalmato sui 2 esiti a -1 tick).
  3. SEMAFORO: spara solo con TUTTI i gate verdi; ogni gate blocca da solo
     (hazard, quiete, zone 40-45/80-90, prezzo, spread, liquidita', linea).
  4. CICLO: fill → green IMMEDIATO ai prezzi REALI; verde accreditato col
     net reale; close parziale → flatten (mai doppio conteggio).
  5. SCRATCH su publish_time; POST-GOL (sospensione → flatten al riprezzo).
  6. KILL-SWITCH: max colpi/partita, stop-loss theta evento.
  7. CONFERME MANUALI: bus, entry confermata/scaduta, protezione eseguita
     COMUNQUE a timeout (mai posizione nuda).
  8. FIX BUG 1 (sniper): close parziale non accredita; contabilita' a delta.
  9. FIX BUG 2 (service): riga 'stopping' chiusa solo se davvero zombie.
 10. FIX BUG 3 (session): sweep cancel d'emergenza sui mercati.
 11. PRESET S4 (16/07): default 'classico' = C7, 'overshoot' = C17;
     i parametri espliciti vincono sempre sul preset.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from flumine.order.order import OrderStatus

from Betfair.stream.scalper.sniper_bot import SniperStrategy
from Betfair.stream.scalper.theta_bot import (
    ThetaConfirmBus,
    ThetaStrategy,
    hazard_bucket,
    hazard_goals_key,
    hazard_lookup,
    in_red_zone,
    theta_pair,
)

KO = dt.datetime(2026, 7, 15, 20, 0, 0)
KO_MS = KO.replace(tzinfo=dt.timezone.utc).timestamp() * 1000.0
_BUCKETS = [f"{i * 5}-{i * 5 + 5}" for i in range(18)]


# ------------------------------------------------------------------- fakes
class _FakeMarket:
    market_id = "1.234"

    def __init__(self):
        self.orders = []
        self.cancelled = []

    def place_order(self, order):
        self.orders.append(order)

    def cancel_order(self, order, size_reduction=None):
        self.cancelled.append(order)


class _FakeOrder:
    def __init__(self, side, price=1.85, size=25.0, size_matched=0.0,
                 avg=0.0, live=False, selection_id=101):
        self.side = side
        self.selection_id = selection_id
        self.size_matched = size_matched
        self.average_price_matched = avg
        self.size_remaining = max(0.0, size - size_matched) if live else 0.0
        self.status = (OrderStatus.EXECUTABLE if live
                       else OrderStatus.EXECUTION_COMPLETE)
        self.order_type = SimpleNamespace(price=price, size=size)


def _cell(p):
    return {"p_goal_next_3min": p, "p_goal_next_2min": p * 0.7, "n": 500}


def _atlas(p_global=0.05, p_league=0.06, team_att=0.05, side=0.05):
    grid = {b: {g: _cell(p_league) for g in ("0", "1", "2", "3+")}
            for b in _BUCKETS}
    glob = {b: {g: _cell(p_global) for g in ("0", "1", "2", "3+")}
            for b in _BUCKETS}
    team = lambda name: {  # noqa: E731 - fixture compatta
        "team_name": name, "league_id": 40, "n_matches": 30,
        "att_goals_per_match_by_bucket": {b: team_att for b in _BUCKETS},
        "def_goals_per_match_by_bucket": {b: side for b in _BUCKETS},
    }
    return {
        "meta": {},
        "global": glob,
        "by_league": {"40": {
            "meta": {"side_rate_per_bucket": {b: side for b in _BUCKETS}},
            "grid": grid}},
        "by_team": {"1": team("Alpha"), "2": team("Beta")},
    }


def _book(pt_s, bb=1.85, bl=1.86, sb=100.0, sl=100.0, inplay=True,
          mtype="OVER_UNDER_25", status="OPEN", mid="1.234"):
    ex = SimpleNamespace(
        available_to_back=[{"price": bb, "size": sb}],
        available_to_lay=[{"price": bl, "size": sl}],
    )
    runner = SimpleNamespace(selection_id=101, status="ACTIVE", ex=ex)
    md = SimpleNamespace(
        market_type=mtype, market_time=KO,
        runners=[SimpleNamespace(selection_id=101, sort_priority=1),
                 SimpleNamespace(selection_id=102, sort_priority=2)],
    )
    return SimpleNamespace(
        market_id=mid, status=status, inplay=inplay,
        publish_time_epoch=KO_MS + pt_s * 1000.0,
        market_definition=md, runners=[runner],
    )


def _strategy(goals=0, minute=20.0, **over):
    tp = {
        "stake": 25.0, "dry_run": False, "atlas": _atlas(),
        "league_id": 40, "home_team": "Alpha", "away_team": "Beta",
        "runner_names": {("1.234", 101): "Under 2.5 Goals"},
    }
    tp.update(over)
    events = []
    s = ThetaStrategy(market_filter={}, theta_params=tp,
                      event_sink=lambda k, p: events.append((k, p)))
    s._test_events = events
    if goals is not None:
        s.set_goals(goals)
    if minute is not None:
        s.live_minute = float(minute)
    return s


# --------------------------------------------------------------- 1. atlante
def test_hazard_bucket_e_goals_key():
    assert hazard_bucket(0) == "0-5"
    assert hazard_bucket(20.9) == "20-25"
    assert hazard_bucket(89) == "85-90"
    assert hazard_bucket(95) == "85-90"        # clamp recupero
    assert hazard_goals_key(0) == "0"
    assert hazard_goals_key(2) == "2"
    assert hazard_goals_key(5) == "3+"


def test_hazard_lookup_catena_squadre_lega_globale():
    atlas = _atlas(team_att=0.10)   # squadre offensive: f_att=2
    # SQUADRE: f_att=2, f_def=1 su entrambi i lati -> M=2 ->
    # P = 1-(1-0.06)^2 = 0.1164
    p, src = hazard_lookup(atlas, 20, 0, 40, "Alpha", "Beta")
    assert src == "team"
    assert p == pytest.approx(1.0 - 0.94 ** 2)
    # una squadra ignota -> fallback DICHIARATO alla lega
    p, src = hazard_lookup(atlas, 20, 0, 40, "Alpha", "Sconosciuta FC")
    assert (p, src) == (pytest.approx(0.06), "league")
    # lega fuori Atlante -> globale
    p, src = hazard_lookup(atlas, 20, 0, 999, "Alpha", "Beta")
    assert (p, src) == (pytest.approx(0.05), "global")
    # Atlante assente -> ROSSO (fail-closed)
    assert hazard_lookup(None, 20, 0) == (None, "none")


# ---------------------------------------------------------------- 2. coppia
def test_theta_pair_green_spalmato():
    pair = theta_pair(25.0, 1.86)
    assert pair is not None
    assert pair["entry_price"] == pytest.approx(1.86)
    assert pair["exit_price"] == pytest.approx(1.85)
    # lay = stake * pe / px ; profitto IDENTICO sui due esiti
    size = 25.0 * 1.86 / 1.85
    assert pair["exit_size"] == pytest.approx(round(size, 2))
    win_after = 25.0 * 0.86 - size * 0.85
    lose_after = size - 25.0
    assert win_after == pytest.approx(lose_after)
    assert pair["locked"] == pytest.approx(round(win_after, 4), abs=1e-4)
    # al fondo della ladder la coppia non esiste -> None (non si entra)
    assert theta_pair(25.0, 1.01) is None


def test_zone_rosse():
    assert in_red_zone(None) is True          # orologio ignoto = fail-closed
    assert in_red_zone(20.0) is False
    assert in_red_zone(42.0) is True          # 40-45 (recupero 1T incluso)
    assert in_red_zone(46.5) is False
    assert in_red_zone(85.0) is True          # 80-90+ (recupero incluso)
    assert in_red_zone(93.0) is True


# -------------------------------------------------------------- 3. semaforo
def test_semaforo_verde_spara_back_al_best():
    s = _strategy()
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200))
    assert len(mkt.orders) == 1
    o = mkt.orders[0]
    assert o.side == "BACK"
    assert o.order_type.price == pytest.approx(1.85)
    assert o.order_type.size == pytest.approx(25.0)
    assert s.stats["shots"] == 1


@pytest.mark.parametrize("over,book_kw", [
    ({"hazard_max": 0.01}, {}),                       # hazard sopra soglia
    ({}, {"bb": 3.60, "bl": 3.65}),                   # prezzo fuori range
    ({}, {"bb": 1.85, "bl": 1.89}),                   # spread > 2 tick
    ({}, {"sb": 10.0}),                               # liquidita' back < 20
    ({}, {"inplay": False}),                          # pre-match
    ({}, {"mtype": "OVER_UNDER_35"}),                 # linea NON target
])
def test_gate_blocca(over, book_kw):
    s = _strategy(**over)
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200, **book_kw))
    assert mkt.orders == []


def test_zona_rossa_blocca():
    for minute in (42.0, 85.0):
        s = _strategy(minute=minute)
        mkt = _FakeMarket()
        s.process_market_book(mkt, _book(1200))
        assert mkt.orders == []


def test_quiete_semaforo_evento_blocca():
    s = _strategy()
    s.risk_sem = SimpleNamespace(entries_halted=lambda now: True)
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200))
    assert mkt.orders == []


def test_punteggio_ignoto_blocca():
    # senza punteggio la LINEA e' ignota: fail-closed, nessun ingresso
    s = _strategy(goals=None)
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200))
    assert mkt.orders == []


def test_linea_segue_i_gol():
    s = _strategy(goals=1)
    assert s._target_line() == "OVER_UNDER_35"
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200, mtype="OVER_UNDER_25"))
    assert mkt.orders == []                       # vecchia linea: non spara
    s.process_market_book(mkt, _book(1210, mtype="OVER_UNDER_35"))
    assert len(mkt.orders) == 1                   # nuova linea: spara


def test_dry_run_emette_solo_trigger():
    s = _strategy(dry_run=True)
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200))
    assert mkt.orders == []
    assert s.stats["dry_fires"] == 1
    assert any(k == "theta_dry_fire" for k, _ in s._test_events)


# ----------------------------------------------------------------- 4. ciclo
def test_fill_green_immediato_a_meno_1_tick():
    s = _strategy()
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    pos.entries = [_FakeOrder("BACK", price=1.85, size_matched=25.0, avg=1.85)]
    s.process_market_book(mkt, _book(1300))
    assert pos.close is not None
    assert pos.close.side == "LAY"
    assert pos.close.order_type.price == pytest.approx(1.84)
    # size compute_green dal MATCHED REALE: 25*1.85/1.84
    assert pos.close.order_type.size == pytest.approx(
        round(25.0 * 1.85 / 1.84, 2))


def test_verde_accreditato_col_net_reale():
    s = _strategy()
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    pos.entries = [_FakeOrder("BACK", price=1.85, size_matched=25.0, avg=1.85)]
    s.process_market_book(mkt, _book(1300))
    size = pos.close.order_type.size
    pos.close = _FakeOrder("LAY", price=1.84, size=size,
                           size_matched=size, avg=1.84)
    # close_locked TEORICO sabotato apposta: NON deve contare nulla
    pos.close_locked = 99.0
    s.process_market_book(mkt, _book(1310, bb=1.84, bl=1.85))
    nw = 25.0 * 0.85 - size * 0.84
    nl = size - 25.0
    assert s.stats["greens"] == 1
    assert s.stats["pnl_locked"] == pytest.approx(min(nw, nl))
    assert pos.entries == [] and pos.close is None


def test_close_parziale_non_accredita_e_flattena():
    s = _strategy()
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    pos.entries = [_FakeOrder("BACK", price=1.85, size_matched=25.0, avg=1.85)]
    pos.entry_fill_pt = KO_MS + 1290_000.0
    # close morta ma matchata SOLO a meta' (LAPSE a sospensione-gol)
    pos.close = _FakeOrder("LAY", price=1.84, size=25.14,
                           size_matched=10.0, avg=1.84)
    s.process_market_book(mkt, _book(1300))
    assert s.stats["greens"] == 0
    assert s.stats["pnl_locked"] == pytest.approx(0.0)
    assert pos.flattening is True
    assert any(k == "theta_close_partial" for k, _ in s._test_events)


def test_entry_ttl_cancella_bid_stantio():
    """Entry NON fillata oltre entry_ttl_s -> cancellata, slot riarmabile
    (un bid stantio al best e' adverse selection pura)."""
    s = _strategy(entry_ttl_s=60.0)
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    live = _FakeOrder("BACK", price=1.85, size=25.0, live=True)
    pos.entries = [live]
    pos.entry_placed_pt = KO_MS + 1200_000.0
    # a +30s resta viva (dentro il TTL)
    s.process_market_book(mkt, _book(1230))
    assert pos.entries == [live]
    # a +61s: cancel; l'ordine muore senza matched -> slot libero
    s.process_market_book(mkt, _book(1261))
    assert live in mkt.cancelled
    live.status = OrderStatus.EXECUTION_COMPLETE
    live.size_remaining = 0.0
    s.process_market_book(mkt, _book(1262))
    assert pos.entries == []
    assert any(k == "theta_entry_ttl" for k, _ in s._test_events)


# --------------------------------------------------------- 5. scratch/postgol
def test_scratch_su_publish_time():
    s = _strategy(scratch_s=240.0)
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    pos.entries = [_FakeOrder("BACK", price=1.85, size_matched=25.0, avg=1.85)]
    pos.entry_fill_pt = KO_MS + 1200_000.0
    # a +239s NON scatta (piazza solo la close)
    s.process_market_book(mkt, _book(1200 + 239))
    assert pos.flattening is False
    # a +241s scatta: flatten
    s.process_market_book(mkt, _book(1200 + 241))
    assert pos.flattening is True
    assert s.stats["scratches"] == 1


def test_postgol_manuale_cancella_close_stale_subito():
    """FIX S6.1: in confirm_mode al post-gol la close resting e' al prezzo
    PRE-gol (irraggiungibile dopo il riprezzo = copertura FINTA) → si
    cancella SUBITO + telemetria theta_exposed_awaiting; la protezione a
    conferma/timeout resta INVARIATA."""
    s = _strategy(confirm_mode=True)
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    pos.entries = [_FakeOrder("BACK", price=1.85, size_matched=25.0, avg=1.85)]
    pos.entry_fill_pt = KO_MS + 1290_000.0
    close = _FakeOrder("LAY", price=1.84, size=25.14, live=True)
    pos.close = close
    # sospensione in-play (gol)
    assert s.check_market_book(mkt, _book(1300, status="SUSPENDED")) is False
    assert "1.234" in s._postgol_mids
    # riapertura al riprezzo: close stale CANCELLATA al primo tick, la
    # protezione resta in attesa di conferma (proposta sul bus)
    s.process_market_book(mkt, _book(1305, bb=1.60, bl=1.61))
    assert close in mkt.cancelled                      # copertura finta rimossa
    assert pos.flattening is False                     # protezione in attesa
    assert s.stats["proposals"] == 1
    assert any(k == "theta_exposed_awaiting" for k, _ in s._test_events)
    # a TTL scaduto la protezione parte COMUNQUE (comportamento invariato)
    close.status = OrderStatus.EXECUTION_COMPLETE
    close.size_remaining = 0.0
    s.process_market_book(mkt, _book(1305 + 61, bb=1.60, bl=1.61))
    assert pos.flattening is True
    assert s.stats["postgol_closes"] == 1
    assert s.stats["confirm_timeouts"] == 1


def test_postgol_auto_niente_evento_exposed():
    """In AUTO la protezione parte nello stesso tick: nessuna finestra
    scoperta → nessun theta_exposed_awaiting (niente falsi allarmi)."""
    s = _strategy()
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    pos.entries = [_FakeOrder("BACK", price=1.85, size_matched=25.0, avg=1.85)]
    pos.entry_fill_pt = KO_MS + 1290_000.0
    pos.close = _FakeOrder("LAY", price=1.84, size=25.14, live=True)
    assert s.check_market_book(mkt, _book(1300, status="SUSPENDED")) is False
    s.process_market_book(mkt, _book(1305, bb=1.60, bl=1.61))
    assert pos.flattening is True
    assert not any(k == "theta_exposed_awaiting" for k, _ in s._test_events)


def test_theta_pos_campi_dichiarati():
    """FIX S6.3: entry_placed_pt/pending_protect DICHIARATI su _ThetaPos
    (niente attributi dinamici: a prova di futuro slots=True)."""
    import dataclasses

    from Betfair.stream.scalper.theta_bot import _ThetaPos

    s = _strategy()
    pos = s._p("1.234", 101)
    assert isinstance(pos, _ThetaPos)
    names = {f.name for f in dataclasses.fields(pos)}
    assert {"entry_placed_pt", "pending_protect"} <= names
    assert pos.entry_placed_pt is None
    assert pos.pending_protect is None


def test_postgol_chiude_al_riprezzo():
    s = _strategy()
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    pos.entries = [_FakeOrder("BACK", price=1.85, size_matched=25.0, avg=1.85)]
    pos.entry_fill_pt = KO_MS + 1290_000.0
    # sospensione in-play (gol) vista da check_market_book
    assert s.check_market_book(mkt, _book(1300, status="SUSPENDED")) is False
    assert "1.234" in s._postgol_mids
    # alla riapertura: chiusura al riprezzo via flatten
    s.process_market_book(mkt, _book(1330, bb=1.60, bl=1.61))
    assert pos.flattening is True
    assert s.stats["postgol_closes"] == 1
    assert "1.234" not in s._postgol_mids or pos.flattening


# ------------------------------------------------------------ 6. kill-switch
def test_max_colpi_partita():
    s = _strategy(max_shots=10)
    s.stats["shots"] = 10
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200))
    assert mkt.orders == []


def test_stop_loss_theta_evento():
    s = _strategy(loss_cap=5.0)
    s.stats["pnl_locked"] = -5.5
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200))
    assert mkt.orders == []
    assert s._event_done is True


# --------------------------------------------------------------- 7. conferme
def test_bus_ciclo_completo():
    bus = ThetaConfirmBus()
    pid = bus.propose("entry", {"price": 1.85}, 1_000_000.0, 60.0)
    assert bus.check(pid, 1_000_100.0) == "awaiting"
    unsent = bus.take_unsent()
    assert len(unsent) == 1 and unsent[0]["kind"] == "entry"
    assert bus.take_unsent() == []                    # una volta sola
    bus.attach_db_id(pid, 77)
    assert bus.awaiting_db() == [(pid, 77)]
    bus.apply_db_status(pid, "confirmed")
    assert bus.check(pid, 1_010_000.0) == "confirmed"
    bus.finalize(pid)
    assert bus.take_dirty() == [(77, "executed")]
    # timeout: oltre la deadline 'awaiting' diventa 'expired' (autorita' bot)
    pid2 = bus.propose("scratch", {}, 1_000_000.0, 60.0)
    assert bus.check(pid2, 1_000_000.0 + 61_000.0) == "expired"
    assert (None, "expired") in bus.take_dirty()


def test_conferma_entry_confermata_spara_a_prezzi_freschi():
    s = _strategy(confirm_mode=True)
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200))
    assert mkt.orders == []                            # solo PROPOSTA
    assert s.stats["proposals"] == 1
    pid = s._entry_prop
    s.confirm_bus.apply_db_status(pid, "confirmed")
    # conferma = via-libera: il fuoco usa il book CORRENTE (prezzo fresco)
    s.process_market_book(mkt, _book(1210, bb=1.84, bl=1.85))
    assert len(mkt.orders) == 1
    assert mkt.orders[0].order_type.price == pytest.approx(1.84)


def test_conferma_entry_scaduta_si_scarta():
    s = _strategy(confirm_mode=True)
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200))
    assert s._entry_prop is not None
    # oltre il TTL (60s): entry SCARTATA, nessun ordine, cooldown attivo
    s.process_market_book(mkt, _book(1200 + 61))
    assert mkt.orders == []
    assert s.stats["confirm_timeouts"] == 1
    s.process_market_book(mkt, _book(1200 + 70))       # dentro il cooldown
    assert s.stats["proposals"] == 1                   # niente ri-proposta


def test_conferma_protezione_timeout_esegue_comunque():
    """MAI posizione nuda: scratch proposto, nessuna risposta -> a TTL
    scaduto la protezione parte lo stesso."""
    s = _strategy(confirm_mode=True, scratch_s=240.0)
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    pos.entries = [_FakeOrder("BACK", price=1.85, size_matched=25.0, avg=1.85)]
    pos.entry_fill_pt = KO_MS + 1200_000.0
    s.process_market_book(mkt, _book(1200 + 241))      # propone lo scratch
    assert pos.flattening is False
    assert s.stats["proposals"] == 1
    s.process_market_book(mkt, _book(1200 + 260))      # in attesa
    assert pos.flattening is False
    s.process_market_book(mkt, _book(1200 + 241 + 61))  # TTL scaduto
    assert pos.flattening is True
    assert s.stats["confirm_timeouts"] == 1
    assert s.stats["scratches"] == 1


def test_conferma_protezione_reject_esegue_comunque():
    s = _strategy(confirm_mode=True, scratch_s=240.0)
    mkt = _FakeMarket()
    pos = s._p("1.234", 101)
    pos.entries = [_FakeOrder("BACK", price=1.85, size_matched=25.0, avg=1.85)]
    pos.entry_fill_pt = KO_MS + 1200_000.0
    s.process_market_book(mkt, _book(1200 + 241))
    s.confirm_bus.apply_db_status(getattr(pos, "pending_protect"), "rejected")
    s.process_market_book(mkt, _book(1200 + 250))
    assert pos.flattening is True                      # protezione NON negoziabile
    assert any(k == "theta_protect_override" for k, _ in s._test_events)


# ----------------------------------------------- 8. FIX BUG 1 (sniper) + delta
def _sniper_book(pt_s, bb=3.40, bl=3.45, sb=200.0):
    ex = SimpleNamespace(
        available_to_back=[{"price": bb, "size": sb}],
        available_to_lay=[{"price": bl, "size": 300.0}],
    )
    runner = SimpleNamespace(selection_id=1221385, status="ACTIVE", ex=ex)
    md = SimpleNamespace(
        market_type="OVER_UNDER_15", market_time=KO,
        runners=[SimpleNamespace(selection_id=1221385, sort_priority=1)],
    )
    return SimpleNamespace(
        market_id="1.234", status="OPEN", inplay=True,
        publish_time_epoch=KO_MS + pt_s * 1000.0,
        market_definition=md, runners=[runner],
    )


def test_bug1_sniper_close_parziale_non_accredita():
    """Regressione bug 1: close PARZIALE a sospensione-gol -> niente verde
    (prima si accreditava il close_locked TEORICO pieno: doppio conteggio)."""
    s = SniperStrategy(market_filter={},
                       sniper_params={"stake": 10.0, "min_size": 50.0})
    mkt = _FakeMarket()
    pos = s._p("1.234", 1221385)
    pos.entries = [_FakeOrder("BACK", price=3.40, size=10.0,
                              size_matched=10.0, avg=3.40,
                              selection_id=1221385)]
    pos.entry_fill_pt = KO_MS + 600_000.0
    pos.close = _FakeOrder("LAY", price=3.35, size=10.15,
                           size_matched=4.0, avg=3.35, selection_id=1221385)
    pos.close_locked = 0.149                            # il teorico NON conta
    s.process_market_book(mkt, _sniper_book(650))
    assert s.stats["greens"] == 0
    assert s.stats["pnl_locked"] == pytest.approx(0.0)
    assert pos.flattening is True


def test_bug1_contabilita_a_delta_multi_ciclo():
    """Gli ordini restano tracciati tra i cicli (anti-orfani): il flatten del
    ciclo 2 deve contabilizzare SOLO il delta, mai il cumulato."""
    s = SniperStrategy(market_filter={},
                       sniper_params={"stake": 10.0, "min_size": 50.0})
    mkt = _FakeMarket()
    pos = s._p("1.234", 1221385)
    # ciclo 1 equalizzato: back 5@3.45 + lay 5.07@3.40 -> min(nw,nl)=0.07
    pos.flatten_orders = [
        _FakeOrder("BACK", price=3.45, size=5.0, size_matched=5.0,
                   avg=3.45, selection_id=1221385),
        _FakeOrder("LAY", price=3.40, size=5.07, size_matched=5.07,
                   avg=3.40, selection_id=1221385),
    ]
    pos.flattening = True
    s._drive_flatten(mkt, pos, 3.40, 3.45, KO_MS)
    p1 = s.stats["pnl_locked"]
    assert p1 == pytest.approx(0.07)
    # ciclo 2 equalizzato AGGIUNTO agli stessi flatten_orders
    pos.flatten_orders += [
        _FakeOrder("BACK", price=3.40, size=10.0, size_matched=10.0,
                   avg=3.40, selection_id=1221385),
        _FakeOrder("LAY", price=3.35, size=10.15, size_matched=10.15,
                   avg=3.35, selection_id=1221385),
    ]
    pos.flattening = True
    s._drive_flatten(mkt, pos, 3.35, 3.40, KO_MS)
    # delta ciclo 2 = min cumulato - gia' contabilizzato (NON il cumulato)
    assert s.stats["pnl_locked"] == pytest.approx(0.22, abs=0.005)
    assert s.stats["pnl_locked"] < 2 * 0.22             # niente doppio conteggio


# --------------------------------------------------- 9. FIX BUG 2 (service)
def test_bug2_stopping_zombie():
    from Betfair.stream.scalper.scalper_service import _stopping_zombie

    now = dt.datetime.now(dt.timezone.utc)
    fresh = (now - dt.timedelta(seconds=5)).isoformat()
    stale = (now - dt.timedelta(seconds=600)).isoformat()
    # heartbeat FRESCO: la sessione e' viva altrove (post-restart) -> NON zombie
    assert _stopping_zombie({"heartbeat_at": fresh}) is False
    # heartbeat fermo o assente -> zombie: la riga si puo' chiudere
    assert _stopping_zombie({"heartbeat_at": stale}) is True
    assert _stopping_zombie({}) is True


# ------------------------------------------------------------- 11. preset S4
def test_default_classico_c7():
    """Il default e' la cella C7 della griglia S4 (EV− su 26 raw: gira in
    paper per raccolta dati, non per profitto)."""
    s = _strategy()
    assert s.theta_preset == "classico"
    assert s.theta_entry_windows == ((0.0, 35.0), (46.0, 70.0))
    assert s.theta_max_goals == 1
    assert s.scratch_s == pytest.approx(120.0)
    assert s.theta_line_offset == 2
    assert s.theta_entry_mode == "maker"
    assert s.theta_green_ticks == 1
    assert s.theta_postgol_wait_s == pytest.approx(0.0)
    assert s.hazard_max == pytest.approx(0.085)
    assert s.theta_overshoot_only is False


def test_preset_overshoot_c17():
    """'overshoot' = cella C17 (unica pista EV+, n=15<40: da campionare)."""
    s = _strategy(preset="overshoot")
    assert s.theta_preset == "overshoot"
    assert s.theta_overshoot_only is True
    assert s.theta_overshoot_min_s == pytest.approx(30.0)
    assert s.theta_overshoot_max_s == pytest.approx(90.0)
    assert s.scratch_s == pytest.approx(240.0)
    assert s.hazard_max == pytest.approx(0.10)
    assert s.theta_line_offset == 2
    assert s.theta_green_ticks == 1
    # MAKER = identita' della cella certificata C17 (review 16/07: mai
    # cambiare silenziosamente una cella campionata; il taker e' del cecchino)
    assert s.theta_entry_mode == "maker"
    assert s.theta_entry_windows is None
    assert s.theta_max_goals is None


def test_preset_override_esplicito_vince():
    s = _strategy(preset="overshoot", scratch_s=60.0, hazard_max=0.05)
    assert s.scratch_s == pytest.approx(60.0)
    assert s.hazard_max == pytest.approx(0.05)
    # preset ignoto -> fallback dichiarato al classico
    s2 = _strategy(preset="boh")
    assert s2.theta_preset == "classico"
    assert s2.scratch_s == pytest.approx(120.0)


def test_default_c7_finestre_e_max_gol_bloccano():
    # minuto 72: fuori finestra (46,70) ma NON zona rossa -> rosso
    s = _strategy(minute=72.0)
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200))
    assert mkt.orders == []
    # 2 gol correnti: oltre max_goals=1 -> rosso (anche sulla linea target)
    s = _strategy(goals=2)
    mkt = _FakeMarket()
    s.process_market_book(mkt, _book(1200, mtype="OVER_UNDER_45"))
    assert mkt.orders == []


def test_preset_overshoot_finestra_post_gol():
    """Overshoot: si entra SOLO 30-90s dopo un gol (quiete OFF by-design)."""
    s = _strategy(preset="overshoot")
    mkt = _FakeMarket()
    # nessun gol visto -> mai ingresso
    s.process_market_book(mkt, _book(1200))
    assert mkt.orders == []
    # gol al 1210s (ancora temporale della finestra)
    s._now_ms = KO_MS + 1210_000.0
    s.set_goals(1)
    # a +10s dal gol: sotto overshoot_min_s -> rosso
    s.process_market_book(mkt, _book(1220, mtype="OVER_UNDER_35"))
    assert mkt.orders == []
    # a +60s: dentro [30,90] -> fuoco ANCHE col semaforo quiete rosso
    s.risk_sem = SimpleNamespace(entries_halted=lambda now: True)
    s.process_market_book(mkt, _book(1270, mtype="OVER_UNDER_35"))
    assert len(mkt.orders) == 1
    assert mkt.orders[0].side == "BACK"


# ------------------------------------------- 12. FIX S6.2 (atlas → sessione)
def test_atlas_assente_o_corrotto_non_uccide_la_sessione(tmp_path):
    """FIX S6.2: Atlante assente/corrotto → None + log 'theta NON armato';
    NESSUNA eccezione risale a run_session (prima mandava in error l'intera
    sessione, disarmando anche sniper/maker: ora theta_mode si spegne e le
    altre strategie si armano comunque)."""
    from Betfair.stream.scalper.scalper_session import _theta_atlas_or_none

    logs = []

    class _Db:
        def log(self, ev, kind, payload):
            logs.append((ev, kind, payload))

    # file ASSENTE → None, nessun raise
    assert _theta_atlas_or_none(_Db(), "E1",
                                str(tmp_path / "manca.json")) is None
    # file CORROTTO → None, nessun raise
    bad = tmp_path / "rotto.json"
    bad.write_text("{non-json", encoding="utf-8")
    assert _theta_atlas_or_none(_Db(), "E1", str(bad)) is None
    assert len(logs) == 2
    assert all(kind == "warn" for _ev, kind, _p in logs)
    assert all("theta NON armato" in p["msg"] for _ev, _k, p in logs)
    # file VALIDO → atlas caricato (il theta si arma normalmente)
    good = tmp_path / "ok.json"
    good.write_text('{"global": {}}', encoding="utf-8")
    assert _theta_atlas_or_none(_Db(), "E1", str(good)) == {"global": {}}


# --------------------------------------------------- 10. FIX BUG 3 (session)
def test_bug3_sweep_cancel():
    from Betfair.stream.scalper.scalper_session import _sweep_cancel

    calls = []

    def _cancel(market_id=None):
        calls.append(market_id)
        if market_id == "1.666":
            raise RuntimeError("boom")

    trading = SimpleNamespace(
        betting=SimpleNamespace(cancel_orders=_cancel))
    out = _sweep_cancel(trading, ["1.111", "1.666", "1.222"])
    assert calls == ["1.111", "1.666", "1.222"]         # prova su TUTTI
    assert out["ok"] == ["1.111", "1.222"]
    assert len(out["ko"]) == 1 and out["ko"][0]["market_id"] == "1.666"
