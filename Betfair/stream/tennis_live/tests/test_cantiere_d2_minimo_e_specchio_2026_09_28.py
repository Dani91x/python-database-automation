"""CANTIERE D2 (28/09): APERTURA TENNIS AL MINIMO e PAPER SPECCHIO DEL LIVE.

Ordini dell'utente (28/09, testuali):
  * aperture tennis sotto il minimo rifiutate: "porta al limite minimo accettato";
  * "deve essere lo specchio per tutti i bot": paper = live.

Si prova, con le classi VERE (motore ordini + esecutore tennis + worker tennis
+ flumine del banco dell'iscrizione a caldo; bot tennis istanziati da
``tennis_runner._instantiate_bot``):

1. la regola pura ``trading.submin.porta_al_minimo_apertura`` (minimo .it
   dalla documentazione ufficiale Betfair: BACK 2,00, LAY 0,50);
2. canale (Safe tennis): un'APERTURA sotto il minimo parte AL minimo, FOK
   compreso, e l'evento lo DICE (``portata_al_minimo``); una CHIUSURA non si
   gonfia mai; sopra il minimo nulla cambia;
3. canale: PAPER e LIVE consegnano a flumine lo STESSO ordine (size, prezzo,
   tempo di validita'), cambia solo il client;
4. canale: l'evento porta il customerOrderRef VERO di Betfair (R-2);
5. calcio intoccato: ``live_order_worker`` non dichiara la regola;
6. bot tennis: PAPER con le stesse blindature del LIVE; un ingresso FLB sotto
   il minimo parte al minimo nel blotter simulato (prima: 1,50 EUR riempiti
   in paper, rifiutati in live).

Nessuna rete: in LIVE il ``place_order`` del mercato e' una SPIA che registra
cio' che flumine riceverebbe e non chiama Betfair.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from Betfair.stream import live_order_worker as LOW
from Betfair.stream import modo_ordini as MO
from Betfair.stream.tennis_live import esecutore_tennis as ET
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_live.tests.test_motore_ordini_tennis_2026_09_25 import (  # noqa: F401
    Motore,
    _latenza_flumine_rimessa,
    _ordine_nel_blotter,
    ambiente,
)
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    _banco,
    _control,
    _follow,
    banchi,
    db,
)
from Betfair.stream.trading.submin import place_min_size, porta_al_minimo_apertura


# ===========================================================================
# 1. la regola pura
# ===========================================================================
# minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50
@pytest.mark.parametrize("lato,chiesto,atteso", [
    ("back", 0.72, 1.0), ("back", 0.01, 1.0), ("back", 0.999, 1.0),
    ("back", 1.0, 1.0), ("back", 1.22, 1.22), ("back", 2.37, 2.37), ("back", 50.0, 50.0),
    ("lay", 0.3, 1.0), ("lay", 0.49, 1.0), ("lay", 0.5, 1.0), ("lay", 1.2, 1.2),
])
def test_porta_al_minimo_solo_verso_l_alto_e_solo_fino_al_minimo(lato, chiesto, atteso):
    assert porta_al_minimo_apertura("it", lato, chiesto) == atteso


def test_il_minimo_e_quello_della_giurisdizione():
    # documentazione ufficiale Betfair, "Italian Exchange Specific Bet Rules"
    # minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50
    assert place_min_size("it", "back") == 1.0
    assert place_min_size("it", "lay") == 1.0


# ===========================================================================
# 2-4. canale del runner tennis (Safe tennis)
# ===========================================================================
def _eventi(m: Motore, ref: str) -> List[Dict[str, Any]]:
    return [x["d"] for x in m.canale.messaggi
            if x.get("t") == "order" and x["d"].get("ref") == ref]


def test_apertura_lay_sotto_il_minimo_parte_al_minimo_con_il_fok(db, banchi, ambiente):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    m = Motore(b, ambiente)
    cmd = m.manda(side="LAY", price=2.1, size=0.3, time_in_force="FILL_OR_KILL")
    assert m.ack(cmd["ref"])["accettato"] is True
    o = _ordine_nel_blotter(b)[-1]
    assert o.order_type.size == 1.0       # minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50
    assert o.order_type.time_in_force == "FILL_OR_KILL"      # FOK conservato
    ev = _eventi(m, cmd["ref"])[0]
    assert ev["fase"] == "inviato"
    assert ev["portata_al_minimo"] == {"chiesto": 0.3, "piazzato": 1.0}
    assert ev["size"] == 1.0
    assert not m.motore._submin                              # nessun place-and-trim


def test_apertura_sopra_il_minimo_non_cambia(db, banchi, ambiente):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    m = Motore(b, ambiente)
    cmd = m.manda(side="BACK", price=2.0, size=2.5)
    o = _ordine_nel_blotter(b)[-1]
    assert o.order_type.size == 2.5
    assert "portata_al_minimo" not in _eventi(m, cmd["ref"])[0]


def test_chiusura_sotto_il_minimo_non_si_gonfia_mai(db, banchi, ambiente):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    m = Motore(b, ambiente)
    # una posizione abbinata da ridurre (la riduzione si VERIFICA sul blotter)
    m.manda(side="LAY", price=2.1, size=4.0)
    o = _ordine_nel_blotter(b)[-1]
    o.simulated.matched = [[0, 2.1, 4.0]]
    o.simulated.size_matched = 4.0
    o.simulated.average_price_matched = 2.1
    cmd = m.manda(side="BACK", price=2.0, size=1.2, reduces_liability=True)
    assert m.ack(cmd["ref"])["accettato"] is True
    o2 = _ordine_nel_blotter(b)[-1]
    assert o2 is not o and o2.order_type.size == 1.2
    assert "portata_al_minimo" not in _eventi(m, cmd["ref"])[0]


def test_paper_e_live_consegnano_a_flumine_lo_stesso_ordine(db, banchi, ambiente,
                                                           monkeypatch):
    """Runner LIVE (client reale + paper affiancato): lo STESSO comando in paper
    e in live arriva a flumine con la stessa size (portata al minimo), stesso
    prezzo, stesso FOK. Cambia solo il client. In LIVE nessuna chiamata a
    Betfair: il ``place_order`` e' una spia."""
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "LIVE")
    b = _banco(db, banchi, [_follow("101")], mode="LIVE")
    b.book("101")
    Mercato = type(b.fw.markets.markets["1.101"])
    vero = Mercato.place_order
    visti: List[Dict[str, Any]] = []

    def _spia(self, order, *a, **k):
        cl = k.get("client")
        visti.append({"size": order.order_type.size, "price": order.order_type.price,
                      "tif": order.order_type.time_in_force, "side": order.side,
                      "client": cl})
        if cl is b.client:           # il client REALE: mai verso Betfair nei test
            return True
        return vero(self, order, *a, **k)
    monkeypatch.setattr(Mercato, "place_order", _spia)
    m = Motore(b, ambiente)
    # minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50
    cp = m.manda(mode="paper", side="BACK", price=2.0, size=0.72,
                 time_in_force="FILL_OR_KILL")
    # 04/10 (cantiere tetto tennis): il live parte solo con «Ordini reali» LIVE
    # scelto in questo avvio (qui dichiarato come fa il banco); prima bastava il tetto
    with MO.dichiara_per_banco("live"):
        cl = m.manda(mode="live", side="BACK", price=2.0, size=0.72,
                     time_in_force="FILL_OR_KILL")
    assert m.ack(cp["ref"])["accettato"] and m.ack(cl["ref"])["accettato"]
    assert len(visti) == 2
    paper, live = visti
    assert paper["client"] is b.client_paper and live["client"] is b.client
    for k in ("size", "price", "tif", "side"):
        assert paper[k] == live[k], k
    assert paper["size"] == 1.0
    assert _eventi(m, cp["ref"])[0]["portata_al_minimo"] == \
        _eventi(m, cl["ref"])[0]["portata_al_minimo"] == {"chiesto": 0.72, "piazzato": 1.0}


def test_l_evento_porta_il_customer_order_ref_vero_di_betfair(db, banchi, ambiente):
    """R-2 (25/09): l'ordine nato da un comando va a Betfair col cor di flumine
    (``<name_hash><sep><order.id>``), non col ref dell'attore. L'evento ora lo
    porta: l'attore puo' ritrovare l'ordine su Betfair per ref."""
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    m = Motore(b, ambiente)
    cmd = m.manda()
    o = _ordine_nel_blotter(b)[-1]
    ev = _eventi(m, cmd["ref"])[0]
    assert ev["cor"] == o.customer_order_ref
    assert ev["cor"] != cmd["ref"] and not ev["cor"].startswith("awtq")
    # lo stesso cor del diario write-ahead (una sola verita')
    ordine = [r for r in m.diario() if r["tipo"] == "ordine"][-1]
    assert ordine["cor"] == ev["cor"]


def test_rifiuto_senza_ordine_non_inventa_un_cor(db, banchi, ambiente):
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    m = Motore(b, ambiente)
    cmd = m.manda(azione="cashout_event")
    ev = _eventi(m, cmd["ref"])[0]
    assert ev["fase"] == "rifiutato" and "cor" not in ev


# ===========================================================================
# 5. calcio intoccato
# ===========================================================================
def test_il_calcio_non_dichiara_la_regola_del_minimo():
    """La regola vive SOLO nell'esecutore tennis: il calcio resta col
    place-and-trim (decisione dell'utente del 24/09, invariata)."""
    assert not hasattr(LOW, "_apertura_al_minimo")
    # minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50
    assert ET._apertura_al_minimo("back", 0.72) == 1.0
    assert ET._apertura_al_minimo("lay", 0.2) == 1.0


# ===========================================================================
# 6. bot tennis: paper con le blindature del live
# ===========================================================================
@pytest.mark.parametrize("bot", ["tennis_flb", "tennis_pro", "tennis_swing",
                                 "tennis_scalper"])
def test_paper_ha_le_stesse_blindature_del_live(bot):
    from betfairlightweight.filters import streaming_market_data_filter

    df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)

    def _mk(mode: str) -> Any:
        ctl = {"stake": 2.0, "dry_run": False, "params": {},
               "mode": "live" if mode == "LIVE" else "paper"}
        return TR._instantiate_bot(bot, ctl, "1.100", {"A": 11, "B": 22},
                                   lambda *a, **k: None, df, mode)
    p, lv = _mk("PAPER"), _mk("LIVE")
    for attr in ("live_min_bet", "size_step", "live"):
        if hasattr(lv, attr):
            assert getattr(p, attr) == getattr(lv, attr), (bot, attr)


def test_ingresso_flb_sotto_il_minimo_nel_paper_parte_al_minimo(db, banchi):
    """Il bot FLB in PAPER, ingresso da 1,50 EUR: nel blotter simulato parte
    2,00 EUR, come partirebbe in LIVE (prima: 1,50 riempito in paper, rifiutato
    in live)."""
    db.controls = [_control("101", "tennis_flb", status="running")]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    flb = b.session.hosted[("101", "tennis_flb")]
    assert flb.live is True
    market = b.fw.markets.markets["1.101"]
    # minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50: ingresso 0,70 -> 1,00
    o = flb._place(market, 11, "BACK", 2.0, 0.7)
    assert o is not None and o.order_type.size == 1.0
    # la copertura sotto il minimo: 28/09 (seconda consegna) ESATTA, mai
    # gonfiata (regola permanente dell'utente sulle chiusure): 0,20 col
    # place-and-trim, parcheggio legale da 2,00 a quota non abbinabile
    # 04/10 (decisione 1 dell'utente): una copertura sotto 0,50 non e' piazzabile da
    # nessuna via (floor di legge del place-and-trim): niente ordine, la dichiara
    # il bot. Fra 0,50 e 1,00 (banca sotto il minimo diretto): place-and-trim.
    assert flb._place(market, 11, "LAY", 2.1, 0.2, copertura=True) is None
    c = flb._place(market, 11, "LAY", 2.1, 0.6, copertura=True)
    assert c is not None and c.order_type.size == 0.6
    assert c.diretto is None and c.sequenza is not None


# ===========================================================================
# 7. commissione del paper = commissione di Betfair (vincite NETTE del mercato)
# ===========================================================================
def _regola(ordini: List[Any]) -> List[Dict[str, Any]]:
    """Il giro VERO dello specchio bot (``_reconcile_bots``) a mercato chiuso,
    coi finti del test del P&L (chiavi e tipi di flumine)."""
    from Betfair.stream.tennis_live import tennis_live_order_worker as OW
    from Betfair.stream.tennis_live.tests import test_specchio_pnl_ref_2026_09_17 as P

    strat = object()
    market = P._Market(chiuso=True)                 # marketBaseRate 5 -> 5%
    market.blotter = P._Blotter(ordini)
    scritte: List[Dict[str, Any]] = []
    vero = OW.tennis_db.upsert_tennis_order
    OW.tennis_db.upsert_tennis_order = lambda row: scritte.append(dict(row))
    try:
        OW._reconcile_bots(P._Session(market, strat), P._Flumine(market), {})
    finally:
        OW.tennis_db.upsert_tennis_order = vero
    return scritte


def test_commissione_sul_netto_del_mercato_non_ordine_per_ordine():
    """Green-up: back +10,00 e lay -9,00 sullo stesso mercato = netto +1,00.
    Betfair: 5% di 1,00 = 0,05. Prima il paper pagava 5% di 10,00 = 0,50."""
    from Betfair.stream.tennis_live.tests.test_specchio_pnl_ref_2026_09_17 import _ordine

    righe = _regola([_ordine(bet_id="1", side="BACK", profit=10.0),
                     _ordine(bet_id="2", side="LAY", profit=-9.0)])
    assert len(righe) == 2
    assert sum(r["commission"] for r in righe) == pytest.approx(0.05)


def test_mercato_in_perdita_netta_nessuna_commissione():
    from Betfair.stream.tennis_live.tests.test_specchio_pnl_ref_2026_09_17 import _ordine

    righe = _regola([_ordine(bet_id="1", side="BACK", profit=3.0),
                     _ordine(bet_id="2", side="LAY", profit=-5.0)])
    assert [r["commission"] for r in righe] == [0.0, 0.0]


def test_un_solo_ordine_in_utile_paga_come_prima():
    from Betfair.stream.tennis_live.tests.test_specchio_pnl_ref_2026_09_17 import _ordine

    righe = _regola([_ordine(bet_id="1", profit=2.0)])
    assert righe[0]["commission"] == pytest.approx(0.10)


# ===========================================================================
# 8. il tetto di partite armate conta SOLO la modalita' del bot (par.7.21)
# ===========================================================================
def _ponte_con_riga(mode_bot: str, mode_riga: str, tetto: int = 1):
    from Betfair.stream.tennis_live import auto_mode as AM
    from Betfair.stream.tennis_live import tennis_bot_service as S
    from Betfair.stream.tennis_live.tests import test_tennis_auto_mode_2026_09_25 as T

    riga = T._control("5")
    riga["mode"] = mode_riga
    db = T._Db([T._servizio(mode=mode_bot, params={AM.CHIAVE_TETTO: tetto})],
               controls=[riga], follows=[T._follow("5", origine="auto")],
               feed=[T._feed("5", open_min=-10), T._feed("1", open_min=-90)])
    S.riconcilia_interruttori(db)
    return db


@pytest.fixture
def _ponte_pulito(monkeypatch):
    from Betfair.stream.tennis_live import auto_mode as AM
    from Betfair.stream.tennis_live import tennis_bot_service as S

    monkeypatch.setattr(S._GUARDIA_AVVIO, "attiva", False)
    S._ORIGINE_ASSENTE["dal"] = None
    monkeypatch.delenv(AM.ENV_TETTO, raising=False)
    yield
    S._ORIGINE_ASSENTE["dal"] = None


def test_partita_paper_non_occupa_il_tetto_del_live(_ponte_pulito):
    """Bot in LIVE col tetto 1; la partita 5 e' ancora armata in PAPER (riga
    viva di prima): il posto live e' LIBERO -> si arma la 1. La riga paper
    della 5 non si riscrive (mai cambiare modalita' a una riga viva)."""
    db = _ponte_con_riga("live", "paper")
    assert [r["event_id"] for r in db.armati] == ["1"]
    assert all(r["mode"] == "live" for r in db.armati)


def test_partita_live_non_occupa_il_tetto_del_paper(_ponte_pulito):
    db = _ponte_con_riga("paper", "live")
    assert [r["event_id"] for r in db.armati] == ["1"]
    assert all(r["mode"] == "paper" for r in db.armati)


def test_stessa_modalita_il_tetto_conta_come_prima(_ponte_pulito):
    db = _ponte_con_riga("paper", "paper")
    assert db.armati == [], "tetto 1 gia' occupato dalla 5 (stessa modalita')"


def test_riga_viva_dell_altra_modalita_non_si_riscrive(_ponte_pulito):
    """Tetto 2, bot LIVE, partita 5 armata in PAPER: posti liberi per il live,
    ma la riga paper della 5 NON diventa live (mai cambiare modalita' a una
    riga viva): si arma solo la 1."""
    db = _ponte_con_riga("live", "paper", tetto=2)
    assert [r["event_id"] for r in db.armati] == ["1"]
