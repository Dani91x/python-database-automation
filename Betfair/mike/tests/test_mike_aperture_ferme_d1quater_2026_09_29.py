"""D1-quater (29/09) - UN'APERTURA RIFIUTATA PER UNA CAUSA CHE NON E' IL MERCATO
SI DICE UNA VOLTA E SI ASPETTA CHE LA CAUSA CAMBI.

Reperto del coordinatore (replay Mike 35760084, trasporto coda, tetto del modo
ordini OFF): ``under_entry back 3.0 @ 1.76`` riproposta 94 volte di fila (P1),
254 gambe ``under_entry`` nel ciclo 0 (P2), 254 righe ``mike_trades`` in
``error`` con ``live_order_mode_non_live:OFF``. WATCH -> PRE_ENTRY_PENDING ->
rifiuto -> WATCH -> di nuovo, a ogni giro: la forma del loop del 15/09.

Ora: al primo rifiuto non di mercato (freno, modo ordini, runner giu') il
servizio scrive ``ctx.aperture_ferme``; il motore toglie le APERTURE finche'
c'e' (uscite e chiusure no); a ogni giro il servizio rilegge la causa e, se non
c'e' piu', le aperture ripartono (detto una volta).

Funzioni vere: ``engine.decide``, ``apply_decision``, ``service.execute_place``,
``execution.place`` con il suo ``_live_brake`` (il tetto del modo ordini viene
dall'ambiente, come in produzione); il mercato live finto conta gli ordini.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_engine import DENTRO_FINESTRA, book, params, snap
from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import ORA, db_vuoto, info_vera
from Betfair.omega.omega_market import PlaceResult
from Betfair.safe_strategy import execution as X


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)
    monkeypatch.setattr(S, "mike_live_abilitato", lambda: True)
    monkeypatch.setattr(S, "_freno_aperture_rest", lambda: None)
    from Betfair.stream import modo_ordini as _mo
    from Betfair.stream.trading import controls as _ctl
    monkeypatch.setitem(_ctl._SETTINGS_CACHE, "data", {"kill_switch": False})
    monkeypatch.setitem(_ctl._SETTINGS_CACHE, "ts", float("inf"))
    monkeypatch.setenv("LIVE_KILL_SWITCH", "false")
    with _mo.dichiara_per_banco("LIVE", kill=False):
        yield


def _mercato_live(ordini: List[Dict[str, Any]]) -> SimpleNamespace:
    def place_order_live(**kw):
        ordini.append(kw)
        return PlaceResult(ok=True, order_status="EXECUTION_COMPLETE", bet_id="B1",
                           size_matched=float(kw["size"]), avg_price_matched=float(kw["price"]),
                           raw={}, size_requested=float(kw["size"]),
                           price_requested=float(kw["price"]), size_remaining=0.0,
                           size_cancelled=0.0, error_code=None, betfair_updated_at=None)
    return SimpleNamespace(place_order_live=place_order_live)


def _giro(db, ctx, s, p, mercato, proposte) -> None:
    """``_run_event`` ridotto all'osso: stessa sequenza (causa riletta, decide,
    apply, execute_place)."""
    S._aggiorna_aperture_ferme(db, ctx, "live", info_vera().event_id)
    d = E.decide(ctx, s, p)
    proposte.extend(a.role for a in d.actions if a.kind == "place")
    for leg in E.apply_decision(ctx, d, s.now):
        S.execute_place(db=db, market=mercato, info=info_vera(), leg=leg,
                        book=s.book(leg.market, leg.selection), mode="live", params=p,
                        now=ORA, dry=False, feed_fresh=True, ctx=ctx)


def _snap(i: int):
    return snap(DENTRO_FINESTRA + i, u35=book(1.50, bs=50.0))


def test_modo_ordini_off_l_apertura_non_si_ripropone_a_ogni_giro(monkeypatch):
    monkeypatch.setenv("LIVE_ORDER_MODE", "OFF")
    db, ctx, p = db_vuoto(), E.MatchCtx(), params()
    ordini: List[Dict[str, Any]] = []
    proposte: List[str] = []
    for i in range(60):
        _giro(db, ctx, _snap(i), p, _mercato_live(ordini), proposte)
    assert ordini == []
    assert proposte.count("under_entry") == 1, (
        f"under_entry proposta {proposte.count('under_entry')} volte in 60 giri col "
        f"modo ordini OFF: e' il loop del 15/09")
    righe = [t for t in db.trades_for_event(info_vera().event_id)]
    assert len(righe) == 1 and righe[0]["status"] == "error"
    ferme = [p_ for k, p_, _e in db.attivita
             if k == "skip" and p_.get("aperture_ferme")]
    assert len(ferme) == 1 and ferme[0]["reason"] == "live_order_mode_non_live:OFF"
    assert ctx.aperture_ferme and ctx.aperture_ferme["motivo"].startswith("live_order_mode")


def test_la_causa_sparisce_e_le_aperture_ripartono(monkeypatch):
    monkeypatch.setenv("LIVE_ORDER_MODE", "OFF")
    db, ctx, p = db_vuoto(), E.MatchCtx(), params()
    ordini: List[Dict[str, Any]] = []
    proposte: List[str] = []
    for i in range(5):
        _giro(db, ctx, _snap(i), p, _mercato_live(ordini), proposte)
    assert ordini == [] and ctx.aperture_ferme
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")          # l'utente riapre
    for i in range(5, 8):
        _giro(db, ctx, _snap(i), p, _mercato_live(ordini), proposte)
    assert ctx.aperture_ferme is None
    assert len(ordini) == 1 and ordini[0]["side"] == "back"
    assert [p_.get("reason") for k, p_, _e in db.attivita
            if k == "state"].count("aperture_riprese") == 1


def test_un_no_del_mercato_non_ferma_le_aperture(monkeypatch):
    """Il FOK non abbinato e' un «no» del MERCATO: nessun fermo generale (resta
    la regola di sempre, ``ctx.rifiuti`` sulla stessa identica domanda)."""
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    db, ctx, p = db_vuoto(), E.MatchCtx(), params()

    def place_order_live(**kw):
        return PlaceResult(ok=False, order_status="EXPIRED", bet_id=None, size_matched=0.0,
                           avg_price_matched=None, raw={}, size_requested=float(kw["size"]),
                           price_requested=float(kw["price"]), size_remaining=0.0,
                           size_cancelled=float(kw["size"]), error_code=None,
                           betfair_updated_at=None)
    _giro(db, ctx, _snap(0), p, SimpleNamespace(place_order_live=place_order_live), [])
    assert ctx.aperture_ferme is None


def test_le_chiusure_passano_con_le_aperture_ferme():
    d = E.Decision("LIVE_KO_GREEN", [
        E.Action(kind="place", role="under_entry", market=E.MARKET_OU35,
                 selection=E.SEL_UNDER, side="back", price=1.5, size=10.0),
        E.Action(kind="place", role="ko_green", market=E.MARKET_OU35,
                 selection=E.SEL_UNDER, side="lay", price=1.4, size=10.0)], "x")
    out = E._strip_openings(d, "aperture ferme", "IDLE_LIVE")
    assert [a.role for a in out.actions] == ["ko_green"]


def test_aperture_ferme_sopravvivono_al_riavvio():
    assert "aperture_ferme" in S._CTX_FIELDS


@pytest.mark.parametrize("nota,atteso", [
    ("live_order_mode_non_live:OFF", True), ("live_kill_switch_attivo", True),
    ("db_kill_switch_attivo", True), ("kill_switch_illeggibile", True),
    ("freni_live_non_letti", True), ("paper_senza_runner:gate", True),
    ("canale_giu:apertura_non_inviata", True),
    ("live_not_matched:EXPIRED", False), ("live_rifiutato:INVALID_BET_SIZE", False),
    ("runner_annullato", False), ("prezzo_non_disponibile", False)])
def test_classificazione_dei_motivi(nota, atteso):
    assert S._rifiuto_non_di_mercato(nota) is atteso
