"""PAPER E LIVE MAI SOMMATI nel runner tennis (reperto B2, cantiere tetto tennis, 04/10).

Prima: ordini a mano (ladder) e comandi del motore (Safe tennis) vivevano TUTTI sotto
l'UNICA capture della partita, qualunque fosse la modalita'. In flumine il blotter e'
per strategia (``blotter.get_exposures(strategy, ...)``): con il runner LIVE green-up,
cash-out, verifica ``reduces_liability`` del motore e specchio posizioni avrebbero
SOMMATO le gambe paper e quelle reali (catalogo §7.21).

Ora (``tennis_runner.capture_degli_ordini``): una strategia degli ordini PER
MODALITA' (la live con nome suo, stesso stream), ``_capture_strategy(.., mode)``,
``esecutore_tennis.CaptureDiModo``.

Classi VERE: ``Flumine`` con i client di ``build_order_client`` (LIVE: client reale
+ client paper affiancato), capture ``_make_capture``, ``Trade``/``LimitOrder``/
``Blotter`` di flumine, esecuzione SIMULATA di flumine per il green-up paper.
NESSUN ordine reale viene eseguito: le posizioni live sono ordini gia' abbinati
scritti nel blotter (come ``Banco.posizione``), mai mandati a un client.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest
from betfairlightweight.resources.bettingresources import CurrentOrder
from flumine.controls import ControlError
from flumine.order.orderpackage import OrderPackageType
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.stream.tennis_live import esecutore_tennis as ET
from Betfair.stream.tennis_live import guardie_tennis as GT
from Betfair.stream.tennis_live import tennis_live_order_worker as TW
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_esatte_2026_09_28 import (  # noqa: F401
    esecuzione_sincrona,
)
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    _banco,
    _follow,
    banchi,
    db,
)

MID = "1.101"


class _DbPosizioni:
    """``tennis_db`` del worker: stesse firme usate dallo specchio posizioni."""

    def __init__(self) -> None:
        self.posizioni: List[Dict[str, Any]] = []

    def upsert_tennis_position(self, riga: Dict[str, Any]) -> None:
        self.posizioni.append(dict(riga))

    def upsert_tennis_order(self, riga: Dict[str, Any]) -> None:  # noqa: ARG002
        return None


def _runner_live(db, banchi) -> Any:
    """Il runner LIVE come dopo la build: capture dei book + strategie degli ordini
    per modalita' (``capture_degli_ordini``, la funzione della build)."""
    b = _banco(db, banchi, [_follow("101")], mode="LIVE")
    per = TR.capture_degli_ordini(b.cap, "LIVE", b.df, [MID])
    b.fw.add_strategy(per["live"])
    b.session.capture_ordini = per
    b.book("101")
    return b


def _abbinato(b: Any, strat: Any, client: Any, lato: str, prezzo: float, size: float) -> Any:
    """Un ordine ABBINATO nel blotter VERO sotto ``strat`` col ``client`` dato
    (mai eseguito: nessuna chiamata a nessun client)."""
    market = b.fw.markets.markets[MID]
    o = Trade(MID, 11, 0, strat).create_order(lato, LimitOrder(prezzo, size))
    o.update_client(client)
    if GT.is_client_paper(client):
        o.simulated.matched = [[0, prezzo, size]]
        o.simulated.size_matched = size
        o.simulated.average_price_matched = prezzo
    else:
        # ordine REALE: l'abbinato lo dice Betfair (``listCurrentOrders`` / order
        # stream) -> ``CurrentOrder`` VERO di betfairlightweight, chiavi del vero
        o.responses.current_order = CurrentOrder(
            betId="2%011d" % (len(market.blotter) + 1), averagePriceMatched=prezzo,
            bspLiability=0.0, handicap=0.0, marketId=MID, orderType="LIMIT",
            persistenceType="LAPSE", placedDate="2026-10-04T10:00:00.000Z",
            selectionId=11, side=lato, sizeCancelled=0.0, sizeLapsed=0.0,
            sizeMatched=size, sizeRemaining=0.0, sizeVoided=0.0,
            status="EXECUTION_COMPLETE", priceSize={"price": prezzo, "size": size})
    o.execution_complete()
    market.blotter[o.id] = o
    return o


def _posizioni_miste(b: Any) -> None:
    """Paper: BACK 10 @2,00 (simulato). Live: LAY 4 @3,00 (reale)."""
    per = b.session.capture_ordini
    _abbinato(b, per["paper"], b.client_paper, "BACK", 2.0, 10.0)
    _abbinato(b, per["live"], b.client, "LAY", 3.0, 4.0)


# --------------------------------------------------------------------------- build
def test_build_live_due_strategie_distinte_stesso_stream(db, banchi):
    b = _runner_live(db, banchi)
    per = b.session.capture_ordini
    assert set(per) == {"paper", "live"}
    assert per["paper"] is b.cap and per["live"] is not b.cap
    assert per["live"].name == TR.NOME_CAPTURE_LIVE != per["paper"].name
    assert per["paper"]._tennis_modalita_esecuzione == "PAPER"
    assert per["live"]._tennis_modalita_esecuzione == "LIVE"
    # stesso stream: zero connessioni in piu'
    assert set(per["live"].stream_ids) == set(b.cap.stream_ids)
    # la live non legge i book (zero lavoro per book), la capture si'
    assert per["live"].check_market_book(None, None) is False
    assert b.cap.check_market_book(None, None) is True


def test_build_paper_una_sola_strategia():
    cap = TR._make_capture(MID, "*", market_ids=[MID])
    per = TR.capture_degli_ordini(cap, "PAPER", None, [MID])
    assert per == {"paper": cap}
    assert cap._tennis_modalita_esecuzione == "PAPER"


def test_reset_streams_dimentica_le_strategie_degli_ordini():
    s = TR.TennisLiveSession(trading=None)
    s.capture_ordini = {"paper": object(), "live": object()}
    s.reset_streams()
    assert s.capture_ordini == {}


# --------------------------------------------------------------------------- esposizioni
def test_esposizioni_per_modalita_mai_sommate(db, banchi):
    b = _runner_live(db, banchi)
    _posizioni_miste(b)
    market = b.fw.markets.markets[MID]
    sp = TW._capture_strategy(b.session, MID, "paper")
    sl = TW._capture_strategy(b.session, MID, "live")
    wp, lp = TW._read_matched_exposures(market, sp, 11, 0.0)
    wl, ll = TW._read_matched_exposures(market, sl, 11, 0.0)
    assert (wp, lp) == pytest.approx((10.0, -10.0))      # solo la gamba paper
    assert (wl, ll) == pytest.approx((-8.0, 4.0))        # solo la gamba reale


def test_motore_legge_solo_la_modalita_del_comando(db, banchi):
    """La verifica ``reduces_liability`` del motore (``_riduzione_verificata``)
    passa da ``_strategy_for_mode`` + ``_read_matched_exposures`` dell'esecutore."""
    b = _runner_live(db, banchi)
    _posizioni_miste(b)
    market = b.fw.markets.markets[MID]
    sl = ET._strategy_for_mode(b.session, "live")
    sp = ET._strategy_for_mode(b.session, "paper")
    assert isinstance(sl, ET.CaptureDiModo) and sl.mode == "live"
    assert ET._read_matched_exposures(b.fw, market, sl, 11, 0.0) == pytest.approx((-8.0, 4.0))
    assert ET._read_matched_exposures(b.fw, market, sp, 11, 0.0) == pytest.approx((10.0, -10.0))


def test_strategia_della_modalita_assente_rifiutata_mai_l_altra(db, banchi):
    """Sessione con la sola strategia paper (runner PAPER): una riga 'live' non
    ripiega MAI sulla capture paper."""
    b = _banco(db, banchi, [_follow("101")], mode="PAPER")
    b.session.capture_ordini = TR.capture_degli_ordini(b.cap, "PAPER", b.df, [MID])
    b.book("101")
    assert TW._capture_strategy(b.session, MID, "live") is None
    with pytest.raises(ValueError, match="strategy_assente"):
        ET._strategy_for_mode(b.session, "live")
    cmd = {"action": "place", "mode": "live", "market_id": MID, "selection_id": 11,
           "handicap": 0.0, "side": "back", "price": 2.0, "size": 2.0, "liability": None,
           "persistence": "LAPSE", "params": {}, "time_in_force": None}
    with pytest.raises(ValueError, match="nessuna strategy"):
        TW._do_place(b.fw, b.session, cmd, "awtq1")


def test_green_up_paper_chiude_solo_la_gamba_paper(db, banchi, esecuzione_sincrona,
                                                   monkeypatch):
    """Green-up dal ladder in prova con una posizione reale aperta sulla stessa
    selezione: l'hedge si calcola SOLO sulla gamba paper e va sul client paper."""
    monkeypatch.setattr(TW, "_tempi_on", lambda: False)
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "LIVE")   # il tetto del runner del banco
    b = _runner_live(db, banchi)
    _posizioni_miste(b)
    cmd = TW.parse_order_payload({"payload": {"action": "greenup", "mode": "paper",
                                              "market_id": MID, "selection_id": 11}})
    res = TW._do_greenup(b.fw, b.session, cmd, "awtq9")
    assert res["ok"] is True
    rec = b.session.tracked_orders["awtq9"]
    o = rec["order"]
    assert o.trade.strategy is b.session.capture_ordini["paper"]
    assert GT.is_client_paper(o.client)
    # paper: W=+10, L=-10, best lay 2,10 -> lay 10*2/2,10 = 9,52 (mai la gamba reale)
    assert o.side == "LAY"
    assert float(o.order_type.size) == pytest.approx(9.52, abs=0.01)


def test_specchio_posizioni_una_riga_per_modalita(db, banchi, monkeypatch):
    b = _runner_live(db, banchi)
    _posizioni_miste(b)
    d = _DbPosizioni()
    monkeypatch.setattr(TW, "tennis_db", d)
    TW.positions_worker({}, b.fw, session=b.session)
    per_modo = {r["mode"]: r for r in d.posizioni}
    assert set(per_modo) == {"paper", "live"}
    assert per_modo["paper"]["matched_if_win"] == pytest.approx(10.0)
    assert per_modo["live"]["matched_if_win"] == pytest.approx(-8.0)


def test_terza_rete_ordine_paper_sul_client_reale_rifiutato(db, banchi):
    """La capture paper porta la sua modalita': ``ControlloModalitaBotTennis``
    rifiuta DENTRO flumine un suo ordine sul client REALE (e viceversa)."""
    b = _runner_live(db, banchi)
    per = b.session.capture_ordini
    ctl = GT.ControlloModalitaBotTennis(b.fw)
    o = Trade(MID, 11, 0, per["paper"]).create_order("BACK", LimitOrder(2.0, 2.0))
    o.update_client(b.client)
    with pytest.raises(ControlError):
        ctl._validate(o, OrderPackageType.PLACE)
    o2 = Trade(MID, 11, 0, per["live"]).create_order("BACK", LimitOrder(2.0, 2.0))
    o2.update_client(b.client_paper)
    with pytest.raises(ControlError):
        ctl._validate(o2, OrderPackageType.PLACE)
    o3 = Trade(MID, 11, 0, per["live"]).create_order("BACK", LimitOrder(2.0, 2.0))
    o3.update_client(b.client)
    ctl._validate(o3, OrderPackageType.PLACE)   # il reale sul reale passa
