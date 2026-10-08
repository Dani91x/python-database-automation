"""P4 BLOCCO 1 (29/09) - MIKE SA COM'E' FINITO OGNI SUO ORDINE.

Ordine dell'utente: «MIKE deve assicurarsi che tutti gli ordini da lui gestiti
siano abbinati, chiusi, loggati. Se il lay non si abbina deve saperlo; in live
ci possono essere sospensioni che cancellano i nostri ordini LAPSE, ovviamente
deve saperlo». Piano `PIANO_MODIFICHE_MIKE_2026-09-29.md`, punti M6.2, M6.3, M8.3.

  M6.2 - lo sportello di PRODUZIONE (`_RealMarket`) rilegge un ordine per
         `betId`. Prima non aveva `order_state_by_bet_id` (il finto del banco
         si'): un ordine uscito dai correnti era sempre «ignoto /
         mercato_senza_lettura». Qui il vero `omega_market.order_state_by_bet_id`
         gira su un client finto che risponde con le chiavi GREZZE di Betfair
         (`betId`, `sizeMatched`, `sizeSettled`, `priceMatched`...).
  M6.3 - la sospensione si legge dal mercato DOVE STA l'ordine appoggiato (la
         banca del rientro vive sull'Under 4.5), non solo dall'Under 3.5.
  M8.3 - un fermo NOSTRO (freno, modo ordini, runner giu') non conta fra i
         rifiuti del mercato della copertura; tolto il fermo, la copertura
         riparte da sola.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from Betfair.mike import certificazione as CERT
from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_ko_green_appoggiata_2026_09_16 import (
    KO, DbFinto, MercatoFinto, book, ctx_in_uscita, gamba_uscita, snap)
from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import ORA, db_vuoto, info_vera
from Betfair.omega import omega_market as OM
from Betfair.omega.omega_market import PlaceResult

PAR = C.merge_params({"ko_green_retry_s": 60})


@pytest.fixture(autouse=True)
def _riga_finta(monkeypatch):
    """La riga della gamba con il `bet_id` dato da Betfair (come nel test
    della ko_green appoggiata)."""
    monkeypatch.setattr(
        S, "_trade_row_for_leg",
        lambda db, eid, leg, cache=None: {
            "id": 1, "meta": {}, "status": "pending", "bet_id": "B1", "mode": "live",
            "signal_key": leg.ref, "market_id": "1.234", "selection_id": 47999})


# ---------------------------------------------------------------------------
# il client Betfair finto: risponde alle STESSE chiamate con le chiavi GREZZE
# ---------------------------------------------------------------------------
class ClientBetfair:
    """`betting_rpc` di betfairlightweight come lo usa `omega_market`:
    listCurrentOrders per `betIds`, listClearedOrders per `betStatus`."""

    def __init__(self, *, correnti: Optional[List[dict]] = None,
                 regolati: Optional[Dict[str, List[dict]]] = None,
                 esplode: bool = False) -> None:
        self.correnti = list(correnti or [])
        self.regolati = dict(regolati or {})
        self.esplode = esplode
        self.chiamate: List[tuple] = []

    def list_current_orders(self, customer_strategy_refs=None, **_k) -> dict:
        self.chiamate.append(("list_current_orders", tuple(customer_strategy_refs or ())))
        return {"currentOrders": []}      # fuori dai correnti della strategia

    def betting_rpc(self, metodo: str, parametri: dict) -> dict:
        self.chiamate.append((metodo, dict(parametri)))
        if self.esplode:
            raise RuntimeError("rete giu'")
        if metodo.endswith("listCurrentOrders"):
            return {"currentOrders": [o for o in self.correnti
                                      if str(o.get("betId")) in parametri.get("betIds", [])]}
        if metodo.endswith("listClearedOrders"):
            return {"clearedOrders": list(self.regolati.get(parametri.get("betStatus"), []))}
        raise AssertionError(metodo)


def _collega(monkeypatch, client: ClientBetfair) -> None:
    monkeypatch.setattr(OM, "call", lambda fn: fn(client))


def regolato(*, stato: str, regolato_eur: float, prezzo: Optional[float] = None) -> dict:
    """Un `ClearedOrderSummary` con le chiavi di Betfair (camelCase)."""
    return {"betId": "B1", "marketId": "1.234", "selectionId": 47999, "side": "LAY",
            "betStatus": stato, "sizeSettled": regolato_eur, "priceMatched": prezzo,
            "priceRequested": 1.48, "placedDate": "2026-09-29T12:59:00.000Z",
            "lastMatchedDate": None, "settledDate": "2026-09-29T13:02:00.000Z"}


def corrente(*, abbinato: float, residuo: float, stato: str = "EXECUTABLE") -> dict:
    """Un `CurrentOrderSummary` con le chiavi di Betfair (camelCase)."""
    return {"betId": "B1", "marketId": "1.234", "selectionId": 47999, "side": "LAY",
            "status": stato, "sizeMatched": abbinato, "sizeRemaining": residuo,
            "averagePriceMatched": 1.48 if abbinato else 0.0,
            "placedDate": "2026-09-29T12:59:00.000Z", "matchedDate": None}


# ===========================================================================
# M6.2 - LO SPORTELLO DI PRODUZIONE RILEGGE PER BET_ID
# ===========================================================================
def test_lo_sportello_di_produzione_espone_la_lettura_per_bet_id():
    assert callable(getattr(S._real_market, "order_state_by_bet_id", None))


def test_stesse_chiavi_del_finto_del_banco(monkeypatch):
    """Il finto del banco (`banco_comune.MercatoFlumine.order_state_by_bet_id`)
    dichiara le chiavi del vero: ordine vivo trovato fra i correnti -> stesso
    insieme di chiavi e stessi tipi."""
    _collega(monkeypatch, ClientBetfair(correnti=[corrente(abbinato=4.0, residuo=6.14)]))
    st = S._real_market.order_state_by_bet_id("B1")
    # 02/10 (riconciliazione tradotti): il vero e il gemello del banco riportano anche i
    # termini CHIESTI (selection_id, side, price_requested, size_requested).
    # 08/10 (W3a): e chi l'ha tolto dal mercato (``sizeCancelled``/``sizeLapsed``)
    assert set(st) == {"found", "size_matched", "avg_price_matched", "size_remaining",
                       "matched_date", "placed_date",
                       "selection_id", "side", "price_requested", "size_requested",
                       "size_cancelled", "size_lapsed"}
    assert st["found"] is True and isinstance(st["size_matched"], float)
    assert isinstance(st["size_remaining"], float)


@pytest.mark.parametrize("client,esito", [
    # cancellato da Betfair alla sospensione (LAPSE), niente abbinato
    (lambda: ClientBetfair(regolati={"LAPSED": [regolato(stato="LAPSED", regolato_eur=0.0)]}),
     "scaduto"),
    # abbinato per intero prima di uscire dai correnti
    (lambda: ClientBetfair(regolati={"SETTLED": [regolato(stato="SETTLED", regolato_eur=10.14,
                                                          prezzo=1.47)]}), "abbinato"),
    # abbinato in parte, il resto scaduto
    (lambda: ClientBetfair(regolati={"LAPSED": [regolato(stato="LAPSED", regolato_eur=4.0,
                                                         prezzo=1.48)]}), "parziale"),
    # ancora vivo (fuori dalla lista della strategia ma vivo per bet_id)
    (lambda: ClientBetfair(correnti=[corrente(abbinato=0.0, residuo=10.14)]), "vivo"),
    # Betfair non lo conosce: ignoto -> riconciliazione, mai indovinato
    (lambda: ClientBetfair(), "ignoto"),
])
def test_rilettura_alla_riapertura_con_lo_sportello_vero(monkeypatch, client, esito):
    _collega(monkeypatch, client())
    leg = gamba_uscita()
    got = S._rileggi_ordine_appoggiato(db=DbFinto(), market=S._real_market, leg=leg,
                                       ev={"event_id": "E1"})
    assert got is not None
    assert got[0] == esito, got
    if esito == "ignoto":
        assert got[1].get("reason") == "betfair_non_lo_conosce"


def test_rete_giu_non_si_decide(monkeypatch):
    _collega(monkeypatch, ClientBetfair(esplode=True))
    leg = gamba_uscita()
    got = S._rileggi_per_bet_id(market=S._real_market, leg=leg,
                                riga={"bet_id": "B1"}, eid="E1")
    assert got is None


def test_sospensione_e_riapertura_in_live_dice_cancellata_da_betfair(monkeypatch):
    """Il criterio di accettazione del piano: con lo sportello di produzione la
    banca appoggiata cancellata alla sospensione risulta «scaduta» (cancellata
    da Betfair), non «esito ignoto»; la gamba si chiude e il motore ne
    riappoggia una alla riapertura."""
    _collega(monkeypatch, ClientBetfair(regolati={"LAPSED": [regolato(stato="LAPSED",
                                                                      regolato_eur=0.0)]}))
    leg = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[leg])
    db = DbFinto()
    ev = {"event_id": "E1"}
    S._sorveglia_sospensione(db=db, market=S._real_market, ctx=ctx,
                             snap=snap(KO + 120.0, u35=book(1.50, status="SUSPENDED")),
                             params=PAR, mode="live", now_ts=KO + 120.0, ev=ev)
    S._sorveglia_sospensione(db=db, market=S._real_market, ctx=ctx, snap=snap(KO + 125.0),
                             params=PAR, mode="live", now_ts=KO + 125.0, ev=ev)
    assert ctx.riapertura["esiti"]["ko_green-0-3"] == "scaduto"
    assert leg.status == "cancelled"
    assert "ordine_scaduto_alla_sospensione" in db.kinds()
    assert "reconcile_pending" not in db.kinds()
    d = E.decide(ctx, snap(KO + 130.0), PAR)
    assert [a.role for a in d.actions if a.kind == "place"] == ["ko_green"]


def test_ordine_uscito_dai_correnti_senza_sospensione_si_rilegge_per_bet_id():
    """Il passaggio in gioco (o una sospensione che il feed non ha fatto in
    tempo a mostrare) fa scadere la lay appoggiata: prima era subito
    `pending_reconcile` («resting_uscito_dagli_ordini_vivi»), poi «mai
    piazzata». Ora si rilegge per bet_id e l'esito certo si applica."""
    leg = gamba_uscita()
    mk = MercatoFinto(per_bet_id={"B1": {"found": True, "size_matched": 0.0,
                                         "avg_price_matched": None, "size_remaining": 0.0,
                                         "matched_date": None, "placed_date": None}})
    db = DbFinto()
    S._segui_resting_live(db=db, market=mk, leg=leg, extra={}, params=PAR,
                          now_ts=KO + 10.0, ev={"event_id": "E1"})
    assert leg.status == "cancelled"
    p = db.payload("ordine_scaduto_alla_sospensione")
    assert p["fonte"] == "fuori_dai_correnti" and p["size_matched"] == 0.0
    assert "reconcile_pending" not in db.kinds()


def test_ordine_uscito_dai_correnti_e_sconosciuto_resta_in_riconciliazione():
    """Se Betfair non sa dire niente la regola di sempre: riconciliazione."""
    leg = gamba_uscita()
    db = DbFinto()
    S._segui_resting_live(db=db, market=MercatoFinto(), leg=leg, extra={}, params=PAR,
                          now_ts=KO + 10.0, ev={"event_id": "E1"})
    assert leg.status == E.STATUS_RECONCILE
    assert "reconcile_pending" in db.kinds()


# ===========================================================================
# M6.3 - LA SOSPENSIONE DAL MERCATO GIUSTO
# ===========================================================================
def banca_rientro(**kw: Any) -> E.Leg:
    base = dict(role="reentry_green", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                side="lay", price=1.75, size=10.11, ref="reentry_green-0-9",
                status="pending", placed_at=KO + 1000.0)
    base.update(kw)
    return E.Leg(**base)


def snap45(now: float, *, u35: str = "OPEN", u45: str = "OPEN") -> E.Snapshot:
    books = {(E.MARKET_OU35, E.SEL_UNDER): book(1.50, status=u35),
             (E.MARKET_OU45, E.SEL_OVER): book(8.0, status=u45),
             (E.MARKET_OU45, E.SEL_UNDER): book(1.76, status=u45)}
    return E.Snapshot(now=now, ko_at=KO, books=books, inplay=True, minute=20, goals=1,
                      feed_fresh=True, order_fresh=True)


PAR_RESTING = C.merge_params({"pre_exit_mode": "resting"})


def test_banca_del_rientro_sospesa_sul_4_5_si_annota():
    """Mercato 4,5 sospeso, 3,5 aperto: prima nessuna annotazione (si leggeva
    solo il 3,5) e la banca del rientro veniva data per viva."""
    leg = banca_rientro()
    ctx = E.MatchCtx(state="REENTRY_OPEN", legs=[leg])
    db = DbFinto()
    S._sorveglia_sospensione(db=db, market=MercatoFinto(), ctx=ctx,
                             snap=snap45(KO + 2000.0, u45="SUSPENDED"),
                             params=PAR_RESTING, mode="live", now_ts=KO + 2000.0,
                             ev={"event_id": "E1"})
    assert ctx.riapertura and ctx.riapertura["refs"] == ["reentry_green-0-9"]
    assert db.payload("mercato_sospeso")["mercati"] == [E.MARKET_OU45]


def test_banca_del_rientro_si_rilegge_alla_riapertura_del_4_5():
    leg = banca_rientro()
    ctx = E.MatchCtx(state="REENTRY_OPEN", legs=[leg])
    mk = MercatoFinto(per_bet_id={"B1": {"found": True, "size_matched": 0.0,
                                         "avg_price_matched": None, "size_remaining": 0.0}})
    db = DbFinto()
    ev = {"event_id": "E1"}
    S._sorveglia_sospensione(db=db, market=mk, ctx=ctx, snap=snap45(KO + 2000.0, u45="SUSPENDED"),
                             params=PAR_RESTING, mode="live", now_ts=KO + 2000.0, ev=ev)
    # 3,5 riaperto ma 4,5 ancora sospeso: NON si legge
    S._sorveglia_sospensione(db=db, market=mk, ctx=ctx, snap=snap45(KO + 2003.0, u45="SUSPENDED"),
                             params=PAR_RESTING, mode="live", now_ts=KO + 2003.0, ev=ev)
    assert ctx.riapertura["letto"] is False and leg.is_live
    S._sorveglia_sospensione(db=db, market=mk, ctx=ctx, snap=snap45(KO + 2010.0),
                             params=PAR_RESTING, mode="live", now_ts=KO + 2010.0, ev=ev)
    assert ctx.riapertura["letto"] is True
    assert ctx.riapertura["esiti"]["reentry_green-0-9"] == "scaduto"
    assert leg.status == "cancelled"


def test_sospensione_del_3_5_non_tocca_la_banca_del_4_5_aperto():
    """Prima: 3,5 sospeso = TUTTE le appoggiate annotate, anche quella sul 4,5
    aperto (che poi `_segui_resting_live` non seguiva piu')."""
    leg = banca_rientro()
    ctx = E.MatchCtx(state="REENTRY_OPEN", legs=[leg])
    db = DbFinto()
    S._sorveglia_sospensione(db=db, market=MercatoFinto(), ctx=ctx,
                             snap=snap45(KO + 2000.0, u35="SUSPENDED"),
                             params=PAR_RESTING, mode="live", now_ts=KO + 2000.0,
                             ev={"event_id": "E1"})
    assert ctx.riapertura is None
    assert "mercato_sospeso" not in db.kinds()


def test_il_controllo_R1_guarda_il_mercato_della_gamba():
    """R1 (certificazione): con la banca del rientro annotata e il 4,5 ancora
    sospeso non c'e' niente da rileggere, anche se il 3,5 e' aperto."""
    leg = banca_rientro()
    ctx = E.MatchCtx(state="REENTRY_OPEN", legs=[leg],
                     riapertura={"ts": KO, "refs": [leg.ref], "letto": False, "esiti": {}})
    d = E.Decision("REENTRY_OPEN", [], "x")
    assert CERT._r1(ctx, snap45(KO + 5.0, u45="SUSPENDED"), d, PAR_RESTING) is None
    assert CERT._r1(ctx, snap45(KO + 5.0), d, PAR_RESTING) is not None


# ===========================================================================
# M8.3 - UN FERMO NOSTRO NON E' UN RIFIUTO DEL MERCATO
# ===========================================================================
@pytest.fixture
def _live(monkeypatch):
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


def _mercato_live(ordini: List[Dict[str, Any]], *, abbina: bool = True) -> SimpleNamespace:
    def place_order_live(**kw):
        ordini.append(kw)
        if not abbina:
            return PlaceResult(ok=False, order_status="EXPIRED", bet_id=None, size_matched=0.0,
                               avg_price_matched=None, raw={}, size_requested=float(kw["size"]),
                               price_requested=float(kw["price"]), size_remaining=0.0,
                               size_cancelled=float(kw["size"]), error_code=None,
                               betfair_updated_at=None)
        return PlaceResult(ok=True, order_status="EXECUTION_COMPLETE", bet_id="B9",
                           size_matched=float(kw["size"]), avg_price_matched=float(kw["price"]),
                           raw={}, size_requested=float(kw["size"]),
                           price_requested=float(kw["price"]), size_remaining=0.0,
                           size_cancelled=0.0, error_code=None, betfair_updated_at=None)
    return SimpleNamespace(place_order_live=place_order_live)


def _copertura(n: int) -> E.Leg:
    return E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER, side="back",
                 price=4.0, size=3.0, ref=f"over_cover-0-{n}", placed_at=ORA.timestamp())


def _prova_copertura(db, ctx, mercato, n: int) -> str:
    bk = E.Book(best_back=4.0, back_size=50.0, best_lay=4.1, lay_size=50.0,
                status="OPEN", inplay=True)
    leg = _copertura(n)
    ctx.legs.append(leg)
    return S.execute_place(db=db, market=mercato, info=info_vera(), leg=leg, book=bk,
                           mode="live", params=C.merge_params({"cover_rifiuti_max": 3}),
                           now=ORA, dry=False, feed_fresh=True, ctx=ctx)


def test_tre_fermi_nostri_non_bloccano_la_copertura(monkeypatch, _live):
    monkeypatch.setenv("LIVE_ORDER_MODE", "OFF")
    db, ctx = db_vuoto(), E.MatchCtx(state="LIVE_UNCOVERED")
    ordini: List[Dict[str, Any]] = []
    for n in range(1, 4):
        ctx.aperture_ferme = None          # tre episodi di fermo distinti
        assert _prova_copertura(db, ctx, _mercato_live(ordini), n) == "cancelled"
    assert ordini == []
    assert E.copertura_bloccata(ctx) is None, ctx.cover_rifiuti
    assert int((ctx.cover_rifiuti or {}).get("conteggio") or 0) == 0
    assert ctx.rifiuti == {}
    assert ctx.aperture_ferme and ctx.aperture_ferme["motivo"].startswith("live_order_mode")
    # tolto il fermo: la causa si rilegge, le aperture ripartono e la copertura
    # parte da sola (nessun «Riprendi»)
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    S._aggiorna_aperture_ferme(db, ctx, "live", info_vera().event_id)
    assert ctx.aperture_ferme is None
    assert _prova_copertura(db, ctx, _mercato_live(ordini), 4) == "open"
    assert len(ordini) == 1


def test_i_rifiuti_del_mercato_contano_ancora(monkeypatch, _live):
    """L'altra direzione: tre «no» VERI del mercato fermano la copertura come
    prima (freno del 17/09 invariato)."""
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    db, ctx = db_vuoto(), E.MatchCtx(state="LIVE_UNCOVERED")
    ordini: List[Dict[str, Any]] = []
    for n in range(1, 4):
        _prova_copertura(db, ctx, _mercato_live(ordini, abbina=False), n)
    assert len(ordini) == 3
    assert E.copertura_bloccata(ctx) is not None


# ===========================================================================
# M8.13 - RITIRATO DA NOI / RIFIUTATO / CANCELLATO DA BETFAIR, per nome
# ===========================================================================
# Lo `status` della riga resta 'error' (vincolo CHECK di `mike_trades` e la
# pagina lo legge): la distinzione sta in `meta.esito_ordine`.
class MercatoAnnulla:
    """`cancel_order_live` come `omega_market`: `CancelResult` vero."""

    def cancel_order_live(self, bet_id: str, market_id: str, size_reduction=None):
        from Betfair.omega.omega_market import CancelResult

        return CancelResult(ok=True, status="SUCCESS", bet_id=str(bet_id),
                            size_cancelled=10.14, error_code=None, riletto=True,
                            size_matched=0.0, avg_price_matched=None,
                            size_remaining=0.0, raw={})


def test_un_ritiro_nostro_riuscito_si_chiama_ritirato_da_noi():
    db = DbFinto()
    leg = gamba_uscita()
    esito = S._mark_trade_cancelled(db, "E1", leg, "cancelled_by_engine", market=MercatoAnnulla())
    assert esito == "cancelled"
    ultima = db.aggiornate[-1]
    assert ultima["status"] == "error"                  # lo status NON cambia
    assert ultima["meta"]["esito_ordine"] == "ritirato_da_noi"
    assert ultima["meta"]["reason"] == "cancelled_by_engine"


def test_la_scadenza_alla_sospensione_si_chiama_cancellato_da_betfair():
    db = DbFinto()
    leg = gamba_uscita()
    S._applica_esito_riapertura(db=db, event_id="E1", leg=leg, esito="scaduto",
                                numeri={"size_matched": 0.0, "avg_price_matched": None,
                                        "lapse_status_reason_code": "MKT_SUSPENDED"})
    meta = db.aggiornate[-1]["meta"]
    assert meta["esito_ordine"] == "cancellato_da_betfair"
    assert meta["lapse_status_reason_code"] == "MKT_SUSPENDED"


@pytest.mark.parametrize("modo,risposta,atteso", [
    ("LIVE", dict(ok=False, order_status="EXPIRED", error_code=None), "non_abbinato_fok"),
    ("LIVE", dict(ok=False, order_status="EXPIRED", error_code="INVALID_BET_SIZE"), "rifiutato"),
    ("OFF", None, "fermato_da_noi"),
])
def test_un_ordine_che_non_nasce_dice_perche(monkeypatch, _live, modo, risposta, atteso):
    monkeypatch.setenv("LIVE_ORDER_MODE", modo)

    def place_order_live(**kw):
        return PlaceResult(bet_id=None, size_matched=0.0, avg_price_matched=None, raw={},
                           size_requested=float(kw["size"]), price_requested=float(kw["price"]),
                           size_remaining=0.0, size_cancelled=float(kw["size"]),
                           betfair_updated_at=None, **risposta)
    db, ctx = db_vuoto(), E.MatchCtx(state="LIVE_UNCOVERED")
    assert _prova_copertura(db, ctx, SimpleNamespace(place_order_live=place_order_live), 1) \
        == "cancelled"
    riga = db.trades_for_event(info_vera().event_id)[-1]
    assert riga["status"] == "error"
    assert riga["meta"]["esito_ordine"] == atteso


# ===========================================================================
# M8.14 - IL MOTIVO DELLA DECADENZA DICHIARATO DA BETFAIR
# ===========================================================================
def test_il_motivo_della_decadenza_si_legge_in_entrambe_le_grafie():
    leg = gamba_uscita()
    for chiave in ("lapseStatusReasonCode", "lapse_status_reason_code"):
        _e, numeri = S._classifica_ordine(leg, {"size_matched": 0.0, "size_remaining": 0.0,
                                                "size_lapsed": 10.14, chiave: "MKT_SUSPENDED"})
        assert numeri["lapse_status_reason_code"] == "MKT_SUSPENDED"
    _e, numeri = S._classifica_ordine(leg, {"size_matched": 0.0, "size_remaining": 0.0})
    assert numeri["lapse_status_reason_code"] is None     # vuoto se manca, mai inventato


def test_scenario_fermo_copertura_registrato_nel_banco():
    from Betfair.mike.tools import replay_registrazioni as R
    assert R.SCENARIO_FERMO_COPERTURA in R.SCENARI_DESCRITTI
