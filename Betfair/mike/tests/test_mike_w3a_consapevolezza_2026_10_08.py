"""08/10 (W3a) - MIKE SA SUBITO DEGLI INTERVENTI DELL'UTENTE, IN LIVE E IN PROVA.

Ordine dell'utente (08/10, testuale): «QUANDO INTERVENGO IO DA QUELLA PAGINA O
DAL SITO O MANUALMENTE SU UN'OPERAZIONE DEI BOT, I BOT LO SANNO E NON FANNO
ALTRO».

  1. RIDUZIONE PARZIALE dall'esterno = intervento dell'utente: stesse
     conseguenze della chiusura (prima: si dichiarava e Mike continuava, e una
     sua chiusura poteva rovesciare la copertura dell'utente);
  2. la lay APPOGGIATA di Mike ANNULLATA dal sito non e' una scadenza: niente
     ri-appoggio, la partita si ferma (prima: letta come scaduta, il motore la
     ri-appoggiava). Il taglio del place-and-trim NON e' un annullo esterno;
  3. PAPER = SPECCHIO DEL LIVE: un ordine MANUALE dell'app sul runner paper
     (fotografia del blotter paper, ``conto_paper``) ferma Mike in prova come
     l'ordine dal sito lo ferma in live; paper e live mai mescolati; senza
     canale tutto come prima.

I finti parlano come il vero: la fotografia LIVE esce dalla cache VERA dello
stream ordini di betfairlightweight (``_dal_runner`` del test del 30/09), quella
PAPER dal produttore VERO del runner (``payload_conto_paper``) su ordini con gli
attributi di ``BetfairOrder``; la REST per bet_id e' il VERO
``omega_market.order_state_by_bet_id`` su un client con le chiavi GREZZE di
Betfair (``ClientBetfair`` del test P4). ASCII-only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_conto_dal_canale_2026_09_30 import (
    MIKE_BACK, PAR, UO_MIKE, _dal_runner, _mike_col_canale, _uo)
from Betfair.mike.tests.test_mike_conto_e_sovracopertura_2026_09_16 import (
    KO, MERCATO_35, SEL_UNDER_35, DbFinto, MercatoConto, evento, gamba_ingresso,
    ordine_conto)
from Betfair.omega import omega_market as OM
from Betfair.stream import esiti_ordini_canale as EO


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    """La riga della gamba d'ingresso (``mike-t1``, bet_id B1) e le memorie del
    conto azzerate fra un test e l'altro."""
    monkeypatch.setattr(
        S, "_trade_row_for_leg",
        lambda db, eid, leg, cache=None: {
            "id": 1, "meta": {}, "status": "open", "bet_id": "B1",
            "mode": _MODO["riga"], "signal_key": leg.ref, "market_id": MERCATO_35,
            "selection_id": SEL_UNDER_35})
    S._CONTO_LETTO_A.clear()
    S._ANNULLI_ESTERNI.clear()
    S._MERCATI_CONTO.clear()
    S.installa_conto_canale(None)
    yield
    S._CONTO_LETTO_A.clear()
    S._ANNULLI_ESTERNI.clear()
    S._MERCATI_CONTO.clear()
    S.installa_conto_canale(None)
    _MODO["riga"] = "live"


_MODO = {"riga": "live"}


def _giro(mercato: Any, ctx: E.MatchCtx, now: float, *, db: DbFinto,
          mode: str = "live") -> bool:
    return S._sorveglia_posizione_di_conto(
        db=db, market=mercato, ctx=ctx, ev=evento(), extra=dict(evento()["ctx"]),
        params=PAR, mode=mode, now_ts=now)


# ===========================================================================
# 1. RIDUZIONE PARZIALE = INTERVENTO DELL'UTENTE
# ===========================================================================
def test_la_riduzione_parziale_dal_sito_ferma_mike_al_primo_giro_dopo_il_canale():
    client = _mike_col_canale()
    db = DbFinto()
    mercato = MercatoConto(morti=[dict(MIKE_BACK)])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    t0 = KO + 1000.0
    assert _giro(mercato, ctx, t0, db=db) is False
    letture = len(mercato.letture)
    mercato.morti.append(ordine_conto(ref=None, side="lay", abbinato=4.0, bet_id="U1"))
    _dal_runner(client, [UO_MIKE, _uo("U1", side="L", sm=4.0, rfo=None, rfs=None)],
                ricevuto_ms=int((t0 + 0.3) * 1000))
    assert _giro(mercato, ctx, t0 + 1.0, db=db) is True
    assert len(mercato.letture) == letture + 2, "la REST riletta SUBITO, a conferma"
    assert ctx.chiuso_dall_utente is True and ctx.no_reentry is True
    p = db.payload("chiuso_dall_utente")
    assert p["come"] == "ridotta" and p["dove"] == "fuori dall'app (stream ordini)"
    assert p["selezioni"][0]["verdetto"] == "ridotta_dall_utente"
    assert p["selezioni"][0]["ancora_viva"] == 6.0
    assert p["latenza_ms"]["dal_runner"] == 700


def test_la_riduzione_parziale_senza_canale_si_vede_alla_cadenza():
    db = DbFinto()
    mercato = MercatoConto(morti=[dict(MIKE_BACK)])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    t0 = KO + 1000.0
    _giro(mercato, ctx, t0, db=db)
    mercato.morti.append(ordine_conto(ref=None, side="lay", abbinato=4.0, bet_id="U1"))
    assert _giro(mercato, ctx, t0 + 1.0, db=db) is False      # cadenza 30 s
    assert _giro(mercato, ctx, t0 + 31.0, db=db) is True
    p = db.payload("chiuso_dall_utente")
    assert p["come"] == "ridotta" and p["dove"] == "fuori dall'app"


# ===========================================================================
# 2. L'APPOGGIATA ANNULLATA DAL SITO: NESSUN RI-APPOGGIO
# ===========================================================================
def _ordine_riletto(**kw: Any) -> Dict[str, Any]:
    grezzo = {"betId": "B1", "marketId": "1.234", "selectionId": 47999, "side": "LAY",
              "status": "EXECUTION_COMPLETE", "sizeMatched": 0.0, "sizeRemaining": 0.0,
              "sizeCancelled": 0.0, "sizeLapsed": 0.0, "averagePriceMatched": 0.0,
              "priceSize": {"price": 1.48, "size": 10.14}}
    grezzo.update(kw)
    return OM._riga_corrente(grezzo)


def test_classifica_annullato_dal_sito_non_scaduto():
    from Betfair.mike.tests.test_mike_ko_green_appoggiata_2026_09_16 import gamba_uscita

    leg = gamba_uscita()
    esito, numeri = S._classifica_ordine(leg, _ordine_riletto(sizeCancelled=10.14))
    assert esito == S._ESITO_ANNULLATO and numeri["size_piazzata"] == 10.14
    # la scadenza resta scadenza
    esito, _n = S._classifica_ordine(leg, _ordine_riletto(sizeLapsed=10.14))
    assert esito == S._ESITO_SCADUTO


def test_il_taglio_del_place_and_trim_non_e_un_annullo_esterno():
    """Banca da 0,70: si piazza 1,00 e Mike ne annulla 0,30 (place-and-trim).
    ``size_cancelled`` 0,30 e' il SUO taglio, non l'utente."""
    from Betfair.mike.tests.test_mike_ko_green_appoggiata_2026_09_16 import gamba_uscita

    leg = gamba_uscita(size=0.70)
    o = _ordine_riletto(status="EXECUTABLE", sizeCancelled=0.30, sizeRemaining=0.70,
                        priceSize={"price": 1.48, "size": 1.00})
    assert S._classifica_ordine(leg, o)[0] == S._ESITO_VIVO
    # e se poi scade, e' una scadenza
    o = _ordine_riletto(sizeCancelled=0.30, sizeLapsed=0.70,
                        priceSize={"price": 1.48, "size": 1.00})
    assert S._classifica_ordine(leg, o)[0] == S._ESITO_SCADUTO


def test_appoggiata_annullata_dal_sito_alla_riapertura_ferma_mike_e_non_si_riappoggia(
        monkeypatch):
    """Il caso del brief: la lay appoggiata di Mike annullata DAL SITO durante la
    sospensione. Lo sportello VERO per bet_id la trova fra i regolati CANCELLED con
    ``sizeCancelled``: e' un annullo dell'utente, la partita si ferma PRIMA della
    decisione e il motore non ri-appoggia (prima: «scaduto» -> ko_green di nuovo)."""
    from Betfair.mike.tests.test_mike_ko_green_appoggiata_2026_09_16 import (
        DbFinto as DbK, book, ctx_in_uscita, gamba_uscita, snap)
    from Betfair.mike.tests.test_mike_p4_ordini_2026_09_29 import (
        PAR as PAR_P4, ClientBetfair, _collega, regolato)

    annullato = dict(regolato(stato="CANCELLED", regolato_eur=0.0), sizeCancelled=10.14)
    _collega(monkeypatch, ClientBetfair(regolati={"CANCELLED": [annullato]}))
    leg = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[leg])
    db = DbK()
    ev = {"event_id": "E1"}
    S._sorveglia_sospensione(db=db, market=S._real_market, ctx=ctx,
                             snap=snap(KO + 120.0, u35=book(1.50, status="SUSPENDED")),
                             params=PAR_P4, mode="live", now_ts=KO + 120.0, ev=ev)
    S._sorveglia_sospensione(db=db, market=S._real_market, ctx=ctx, snap=snap(KO + 125.0),
                             params=PAR_P4, mode="live", now_ts=KO + 125.0, ev=ev)
    assert ctx.riapertura["esiti"]["ko_green-0-3"] == S._ESITO_ANNULLATO
    assert "ordine_scaduto_alla_sospensione" not in db.kinds()
    assert leg.status == "cancelled"
    # stesso giro, prima della decisione: la sorveglianza del conto ferma la partita
    assert S._sorveglia_posizione_di_conto(
        db=db, market=S._real_market, ctx=ctx, ev=ev, extra={}, params=PAR_P4,
        mode="live", now_ts=KO + 125.0) is True
    assert ctx.chiuso_dall_utente is True and ctx.no_reentry is True
    p = db.payload("chiuso_dall_utente")
    assert p["come"] == "annullata" and p["dove"] == "fuori dall'app"
    d = E.decide(ctx, snap(KO + 130.0), PAR_P4)
    assert [a for a in d.actions if a.kind == "place"] == [], "nessun ri-appoggio"


def test_appoggiata_ridotta_dal_sito_mentre_e_viva_ferma_mike(monkeypatch):
    """L'utente toglie dal sito PARTE della lay ancora viva (sizeCancelled > 0,
    residuo vivo): ``_segui_resting_live`` lo vede fra i correnti, la partita si
    ferma e la gamba viva viene annullata (stesse conseguenze della chiusura)."""
    from Betfair.mike.tests.test_mike_ko_green_appoggiata_2026_09_16 import (
        DbFinto as DbK, MercatoFinto, ctx_in_uscita, gamba_uscita, ordine_betfair)

    # la riga della lay appoggiata: 'pending' col bet_id (come nel test del 16/09)
    monkeypatch.setattr(
        S, "_trade_row_for_leg",
        lambda db, eid, leg, cache=None: {
            "id": 1, "meta": {}, "status": "pending", "bet_id": "B1", "mode": "live",
            "signal_key": leg.ref, "market_id": "1.234", "selection_id": 47999})
    leg = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[leg])
    db = DbK()
    mk = MercatoFinto(correnti=[ordine_betfair(residuo=4.14, annullato=6.0)])
    S._segui_resting_live(db=db, market=mk, leg=leg, extra={}, params=PAR,
                          now_ts=KO + 10.0, ev={"event_id": "E1"})
    assert S._ANNULLI_ESTERNI["E1"]["annullato_da_altri"] == 6.0
    assert S._sorveglia_posizione_di_conto(
        db=db, market=mk, ctx=ctx, ev={"event_id": "E1"}, extra={}, params=PAR,
        mode="live", now_ts=KO + 10.0) is True
    assert ctx.chiuso_dall_utente is True
    assert "cancel_richiesto" in db.kinds(), "la gamba ancora viva si annulla"


# ===========================================================================
# 3. PAPER = SPECCHIO DEL LIVE (ordine manuale dell'app sul runner paper)
# ===========================================================================
def _ordine_paper(bet_id: str, *, side: str, abbinato: float, ref: str) -> Any:
    """Un ordine del blotter della strategia paper, con gli attributi di
    ``flumine.order.order.BetfairOrder``."""
    from flumine.order.order import OrderStatus
    from flumine.order.ordertype import LimitOrder

    return SimpleNamespace(
        bet_id=bet_id, market_id=MERCATO_35, selection_id=SEL_UNDER_35, handicap=0.0,
        side=side, status=OrderStatus.EXECUTION_COMPLETE,
        order_type=LimitOrder(1.5, abbinato, persistence_type="LAPSE"),
        size_matched=abbinato, size_remaining=0.0, size_cancelled=0.0, size_lapsed=0.0,
        size_voided=0.0, average_price_matched=1.5,
        context={"customer_order_ref": ref}, notes={"customer_order_ref": ref},
        customer_order_ref="hash", responses=SimpleNamespace(
            date_time_placed=datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)))


def _dal_runner_paper(client: EO.ClientEsiti, ordini: List[Any], ms: int) -> None:
    """Il runner PAPER pubblica il blotter del mercato (produttore VERO) e il
    client di Mike lo incassa come dal socket."""
    testi: List[str] = []
    assert EO.pubblica_conto_paper(MERCATO_35, ordini,
                                   lambda t, d: testi.append(json.dumps({"t": t, "d": d})),
                                   adesso_ms=ms)
    for t in testi:
        assert client.incassa(t) is True


def _client_tutti() -> EO.ClientEsiti:
    memoria = EO.MemoriaConto()
    S.installa_conto_canale(memoria)
    return EO.ClientEsiti(memoria, topic=EO.TOPIC_CONTO_TUTTI, porta_ws=1)


BOT_PAPER = dict(bet_id="B1", side="BACK", abbinato=10.0, ref="awlq101")


def test_in_PAPER_lordine_manuale_dellapp_ferma_mike_senza_REST():
    _MODO["riga"] = "paper"
    client = _client_tutti()
    db = DbFinto()
    mercato = MercatoConto(morti=[])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    t0 = KO + 1000.0
    _dal_runner_paper(client, [_ordine_paper(**BOT_PAPER)], int(t0 * 1000))
    assert _giro(mercato, ctx, t0, db=db, mode="paper") is False   # intera
    _dal_runner_paper(client, [_ordine_paper(**BOT_PAPER),
                               _ordine_paper("U1", side="LAY", abbinato=10.0, ref="awlq102")],
                      int((t0 + 0.2) * 1000))
    assert _giro(mercato, ctx, t0 + 1.0, db=db, mode="paper") is True
    assert mercato.letture == [], "in paper nessuna REST: decide il blotter del runner"
    assert ctx.chiuso_dall_utente is True and ctx.no_reentry is True
    p = db.payload("chiuso_dall_utente")
    assert p["come"] == "chiusa" and p["dove"] == "dall'app (ordine manuale sul runner paper)"
    assert p["conferma"].startswith("blotter paper") and p["latenza_ms"]["dal_runner"] == 800


def test_in_PAPER_anche_la_riduzione_parziale_dellapp_ferma_mike():
    _MODO["riga"] = "paper"
    client = _client_tutti()
    db = DbFinto()
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    _dal_runner_paper(client, [_ordine_paper(**BOT_PAPER),
                               _ordine_paper("U1", side="LAY", abbinato=3.0, ref="awlq102")],
                      int((KO + 1000.0) * 1000))
    assert _giro(MercatoConto(), ctx, KO + 1001.0, db=db, mode="paper") is True
    assert db.payload("chiuso_dall_utente")["come"] == "ridotta"


def test_in_PAPER_runner_riavviato_le_gambe_non_si_ritrovano_e_non_si_decide():
    """Il blotter del runner riavviato non ha l'ordine di Mike: c'e' solo quello
    manuale. Non si sa confrontare: in paper non c'e' altro da rileggere, quindi
    NIENTE decisione (conservativo, come le gambe non ritrovate del live)."""
    _MODO["riga"] = "paper"
    client = _client_tutti()
    db = DbFinto()
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    _dal_runner_paper(client, [_ordine_paper("U1", side="LAY", abbinato=10.0,
                                             ref="awlq102")], int((KO + 1000.0) * 1000))
    assert _giro(MercatoConto(), ctx, KO + 1001.0, db=db, mode="paper") is False
    assert ctx.chiuso_dall_utente is False


def test_paper_e_live_non_si_mescolano():
    """Una fotografia PAPER che dice «chiusa» non tocca Mike in LIVE (ne' fa
    rileggere la REST); una fotografia LIVE non tocca Mike in PAPER."""
    client = _client_tutti()
    db = DbFinto()
    mercato = MercatoConto(morti=[dict(MIKE_BACK)])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    t0 = KO + 1000.0
    _giro(mercato, ctx, t0, db=db)
    letture = len(mercato.letture)
    _dal_runner_paper(client, [_ordine_paper(**BOT_PAPER),
                               _ordine_paper("U1", side="LAY", abbinato=10.0, ref="awlq102")],
                      int((t0 + 0.2) * 1000))
    assert _giro(mercato, ctx, t0 + 1.0, db=db) is False
    assert len(mercato.letture) == letture and ctx.chiuso_dall_utente is False
    # e al contrario: Mike in PAPER con la sola fotografia LIVE della chiusura
    _MODO["riga"] = "paper"
    S.installa_conto_canale(None)
    client = _client_tutti()
    ctx2 = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    _dal_runner(client, [UO_MIKE, _uo("U1", side="L", sm=10.0, rfo=None, rfs=None)],
                ricevuto_ms=int((t0 + 2.0) * 1000))
    assert _giro(MercatoConto(), ctx2, t0 + 3.0, db=DbFinto(), mode="paper") is False
    assert ctx2.chiuso_dall_utente is False


def test_senza_canale_in_PAPER_tutto_come_prima():
    _MODO["riga"] = "paper"
    db = DbFinto()
    mercato = MercatoConto(morti=[dict(MIKE_BACK), ordine_conto(ref=None, side="lay",
                                                                abbinato=10.0, bet_id="U1")])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    assert _giro(mercato, ctx, KO + 1000.0, db=db, mode="paper") is False
    assert mercato.letture == [] and db.log_scritti == []


def test_la_sveglia_del_conto_si_alza_solo_sui_mercati_di_mike():
    """La dormita del ciclo si interrompe solo per una fotografia NUOVA su un
    mercato dove Mike ha una posizione (``_MERCATI_CONTO``, solo memoria)."""
    client = _mike_col_canale()
    db = DbFinto()
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    _giro(MercatoConto(morti=[dict(MIKE_BACK)]), ctx, KO + 1000.0, db=db)
    assert S._MERCATI_CONTO == {"E1": {MERCATO_35}}
    S._CONTO.sveglia.clear()
    _dal_runner(client, [UO_MIKE], ricevuto_ms=1)
    assert S._CONTO.sveglia_alzata() is True
    _dal_runner(client, [UO_MIKE], ricevuto_ms=2)       # stesso contenuto
    assert S._CONTO.sveglia_alzata() is False


# ===========================================================================
# 4. REPERTO W2 (coordinatore, 08/10): il verdetto in ESPOSIZIONE, non in size
# ===========================================================================
def _sorveglia_rest(morti: List[Dict[str, Any]], *, legs=None) -> tuple:
    db = DbFinto()
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs or [gamba_ingresso()])
    esito = _giro(MercatoConto(morti=morti), ctx, KO + 1000.0, db=db)
    return esito, ctx, db


def test_green_up_dellutente_su_un_suo_ordine_non_tocca_mike_esempio_1():
    """Mike back 10 @1,50; dal sito l'utente punta 5 @1,50 e lo copre con una
    lay 5,36 @1,40 (green-up SUO). Netto in size 9,64: prima «ridotta» (e da
    oggi lo stop). In esposizione la parte dell'utente e' piatta: Mike intero."""
    esito, ctx, db = _sorveglia_rest([
        dict(MIKE_BACK),
        ordine_conto(ref=None, side="back", abbinato=5.0, bet_id="U1", prezzo=1.50),
        ordine_conto(ref=None, side="lay", abbinato=5.36, bet_id="U2", prezzo=1.40)])
    assert esito is False and ctx.chiuso_dall_utente is False
    assert "chiuso_dall_utente" not in db.kinds()


def test_green_up_dellutente_su_un_suo_ordine_non_tocca_mike_esempio_2():
    """Mike back 2; dal sito back 10 @5,0 coperto con lay 33,33 @1,50. Netto in
    size -21,33: prima «chiusa» e Mike abbandonava la sua posizione."""
    leg = gamba_ingresso()
    leg.size, leg.matched = 2.0, 2.0
    esito, ctx, db = _sorveglia_rest([
        ordine_conto(ref="mike-t1", side="back", abbinato=2.0, bet_id="B1"),
        ordine_conto(ref=None, side="back", abbinato=10.0, bet_id="U1", prezzo=5.0),
        ordine_conto(ref=None, side="lay", abbinato=33.33, bet_id="U2", prezzo=1.50)],
        legs=[leg])
    assert esito is False and ctx.chiuso_dall_utente is False


def test_la_chiusura_vera_a_un_prezzo_diverso_resta_chiusa():
    """L'utente chiude la posizione di Mike con una lay 10 @1,45 (pari size, prezzo
    diverso): resta «chiusa», in esposizione (metro dichiarato)."""
    esito, ctx, db = _sorveglia_rest([
        dict(MIKE_BACK), ordine_conto(ref=None, side="lay", abbinato=10.0, bet_id="U1",
                                      prezzo=1.45)])
    assert esito is True
    p = db.payload("chiuso_dall_utente")
    assert p["come"] == "chiusa" and p["selezioni"][0]["metro"] == "esposizione"


def test_senza_prezzo_medio_si_resta_sullaritmetica_in_size():
    """Un abbinato altrui senza prezzo medio: mai un prezzo inventato, si usa la
    size di prima (e qui la size dice ridotta)."""
    altrui = ordine_conto(ref=None, side="lay", abbinato=4.0, bet_id="U1")
    altrui["avg_price_matched"] = None
    altrui["average_price_matched"] = None
    esito, ctx, db = _sorveglia_rest([dict(MIKE_BACK), altrui])
    assert esito is True
    p = db.payload("chiuso_dall_utente")
    assert p["come"] == "ridotta" and p["selezioni"][0]["metro"] == "size"


# ===========================================================================
# 5. SECONDA TAPPA (coordinatore, 08/10): l'ordine di un ALTRO bot non e'
#    dell'utente; DB illeggibile -> nessun verdetto, nessun ordine nuovo
# ===========================================================================
class DbConProprietari(DbFinto):
    """``DbFinto`` + la lettura dei proprietari con la firma VERA
    (``proprietari_bot_conto(bet_ids, modo)`` di ``mike/db.py``): bet_id -> motivo
    per gli ordini dei bot."""

    def __init__(self, dei_bot: Dict[str, str] = None, *, giu: bool = False) -> None:
        super().__init__()
        self.dei_bot = dict(dei_bot or {})
        self.giu = giu
        self.letture_proprietari: List[tuple] = []

    def proprietari_bot_conto(self, bet_ids: List[str], modo: str = "live") -> Dict[str, str]:
        self.letture_proprietari.append((tuple(bet_ids), modo))
        if self.giu:
            raise RuntimeError("DB giu'")
        return {b: m for b, m in self.dei_bot.items() if b in bet_ids}


@pytest.fixture
def _conto_pulito(monkeypatch):
    S._CONTO.azzera()
    monkeypatch.setattr(S._CONTO.proprietari, "_riprova_s", 0.0)
    yield
    S._CONTO.azzera()


def _lay_che_chiude(bet_id: str, *, ref: Any, csr: Any) -> Dict[str, Any]:
    """Un LAY 10 @1,45 sulla selezione di Mike: se fosse dell'utente CHIUDEREBBE
    la posizione di Mike (back 10 @1,50)."""
    return ordine_conto(ref=ref, side="lay", abbinato=10.0, bet_id=bet_id, prezzo=1.45,
                        csr=csr)


def test_ordine_di_omega_sulla_selezione_di_mike_non_lo_ferma(_conto_pulito):
    """Riconosciuto dai RIFERIMENTI (strategia ``omega``, ref ``omega-t9``): nessuna
    lettura del DB, nessun verdetto, Mike continua."""
    db = DbConProprietari()
    mercato = MercatoConto(morti=[dict(MIKE_BACK),
                                  _lay_che_chiude("O9", ref="omega-t9", csr="omega")])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    assert _giro(mercato, ctx, KO + 1000.0, db=db) is False
    assert ctx.chiuso_dall_utente is False and "chiuso_dall_utente" not in db.kinds()
    assert db.letture_proprietari == []


def test_ordine_di_un_altro_bot_dalla_coda_lo_dice_il_DB_e_mike_continua(_conto_pulito):
    """Strategia 'live' e ref del runner (``awlq``): i riferimenti non bastano, il DB
    (riga della coda del runner di Omega) dice che e' di un bot. UNA lettura per
    bet_id: al giro dopo l'esito e' in memoria."""
    db = DbConProprietari({"Q1": "coda:omega-t9"})
    mercato = MercatoConto(morti=[dict(MIKE_BACK),
                                  _lay_che_chiude("Q1", ref="awlq55", csr="live")])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    assert _giro(mercato, ctx, KO + 1000.0, db=db) is False
    assert _giro(mercato, ctx, KO + 1031.0, db=db) is False
    assert ctx.chiuso_dall_utente is False
    assert db.letture_proprietari == [(("Q1",), "live")]


def test_ordine_manuale_dell_app_ferma_mike(_conto_pulito):
    """Lo stesso ordine dalla coda del runner, ma del DESKTOP (il DB non lo dice di
    un bot): e' l'utente, Mike si ferma."""
    db = DbConProprietari({})
    mercato = MercatoConto(morti=[dict(MIKE_BACK),
                                  _lay_che_chiude("Q2", ref="awlq56", csr="live")])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    assert _giro(mercato, ctx, KO + 1000.0, db=db) is True
    assert db.payload("chiuso_dall_utente")["come"] == "chiusa"


def test_DB_giu_nessun_verdetto_nessun_ordine_nuovo_poi_riprende(_conto_pulito):
    db = DbConProprietari({}, giu=True)
    mercato = MercatoConto(morti=[dict(MIKE_BACK),
                                  _lay_che_chiude("Q3", ref="awlq57", csr="live")])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    eid = str(evento()["event_id"])
    assert _giro(mercato, ctx, KO + 1000.0, db=db) is False
    assert ctx.chiuso_dall_utente is False, "nessun verdetto al buio"
    assert list(S._CONTO.in_verifica(eid)) == [f"{MERCATO_35}:{SEL_UNDER_35}"]
    p = [pl for k, pl in db.log_scritti if k == "posizione_di_conto"
         and pl.get("verdetto") == "in_verifica"]
    assert p and p[0]["ordini_ignoti"] == ["Q3"] and "DB giu'" in p[0]["errore"]
    # nessun ordine nuovo: la decisione perde i piazzamenti, restano gli annulli
    d = E.Decision("LIVE_COVERED", [E.Action(kind="place", role="under_close"),
                                    E.Action(kind="cancel", ref="x")], "motore")
    fermo = S._ferma_piazzamenti_in_verifica(d, ctx=ctx, eid=eid, db=db, extra={},
                                             params=PAR, now_ts=KO + 1000.0)
    assert [a.kind for a in fermo.actions] == ["cancel"] and fermo.state == "LIVE_COVERED"
    # il DB torna: al giro della cadenza si sa che e' dell'utente -> Mike si ferma
    db.giu = False
    assert _giro(mercato, ctx, KO + 1031.0, db=db) is True
    assert S._CONTO.in_verifica(eid) == {}
    assert db.payload("chiuso_dall_utente")["come"] == "chiusa"


def test_senza_verifica_la_decisione_non_si_tocca(_conto_pulito):
    d = E.Decision("LIVE_COVERED", [E.Action(kind="place", role="under_close")], "motore")
    assert S._ferma_piazzamenti_in_verifica(
        d, ctx=E.MatchCtx(state="LIVE_COVERED"), eid="E1", db=DbFinto(), extra={},
        params=PAR, now_ts=KO) is d


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
