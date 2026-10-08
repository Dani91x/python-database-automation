"""30/09 - MIKE VEDE LA CHIUSURA DELL'UTENTE DALLO STREAM ORDINI, non dopo 30 s.

Fatto del 30/09 (live, 36130526 Vsetin-Bohemians): l'utente chiude la posizione
di Mike dal sito Betfair verso le 15:30:45, Mike se ne accorge alle 15:32:13
(``chiuso_dall_utente``, R3): la posizione di conto si rileggeva via REST al piu'
ogni ``reconcile_every_s`` (30 s). Da oggi il runner LIVE pubblica sul canale gli
ordini del conto che lo stream ordini gli porta (``esiti_ordini_canale``, topic
``conto``) e Mike, al primo giro dopo la fotografia nuova, calcola il verdetto
con la STESSA aritmetica (``service._verdetto_di_conto``) e, se la posizione non
e' piu' intera, rilegge SUBITO la REST, che conferma e decide.

I finti parlano come il vero:
  * la fotografia del canale esce dalla cache VERA dello stream ordini di
    ``betfairlightweight`` (messaggio ``oc`` nella grafia di Betfair) e dal
    produttore VERO del runner (``payload_conto``), serializzata come la
    serializza ``local_channel`` e incassata dal client VERO (``ClientEsiti``);
  * la REST e' ``MercatoConto`` del test del 16/09 (le chiavi di
    ``omega_market.list_current_orders_account``).

Ogni test nuovo e' stato FALSIFICATO: mutazioni nel referto
``AUDIT_2026-09-30/MIKE_CHIUSURA_UTENTE_TEMPO_REALE.md``. ASCII-only.
"""
from __future__ import annotations

import json
import socket
import time
from typing import Any, Dict, List, Optional

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_conto_e_sovracopertura_2026_09_16 import (
    KO,
    MERCATO_35,
    SEL_UNDER_35,
    DbFinto,
    MercatoConto,
    evento,
    gamba_ingresso,
    ordine_conto,
)
from Betfair.stream import esiti_ordini_canale as EO

#: la cadenza VERA della REST (i test di Mike la azzerano di serie in conftest)
PAR = dict(C.merge_params(None), reconcile_every_s=30.0)
MIKE_BACK = ordine_conto(ref="mike-t1", side="back", abbinato=10.0, bet_id="B1")
LAY_UTENTE = ordine_conto(ref=None, side="lay", abbinato=10.0, bet_id="U1", prezzo=1.45)


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    """La riga di ``mike_trades`` della gamba (ref di piazzamento ``mike-t1``) e le
    memorie del conto azzerate fra un test e l'altro."""
    monkeypatch.setattr(
        S, "_trade_row_for_leg",
        lambda db, eid, leg, cache=None: {
            "id": 1, "meta": {}, "status": "open", "bet_id": "B1", "mode": "live",
            "signal_key": leg.ref, "market_id": MERCATO_35,
            "selection_id": SEL_UNDER_35})
    S._CONTO_LETTO_A.clear()
    S.installa_conto_canale(None)
    yield
    S._CONTO_LETTO_A.clear()
    S.installa_conto_canale(None)


# ---------------------------------------------------------------------------
# il runner, VERO: stream ordini -> payload -> canale -> client di Mike
# ---------------------------------------------------------------------------
def _uo(bet_id: str, *, side: str, sm: float, rfo: Any, rfs: Any,
        p: float = 1.5) -> Dict[str, Any]:
    return {"id": bet_id, "p": p, "s": sm, "side": side, "status": "EC", "pt": "L",
            "ot": "L", "pd": 1_700_000_000_000, "md": 1_700_000_000_500, "avp": p,
            "sm": sm, "sr": 0.0, "sl": 0.0, "sc": 0.0, "sv": 0.0, "rfo": rfo, "rfs": rfs}


UO_MIKE = _uo("B1", side="B", sm=10.0, rfo="mike-t1", rfs="mike")
UO_UTENTE = _uo("U1", side="L", sm=10.0, rfo=None, rfs=None, p=1.45)


def _dal_runner(client_mike: EO.ClientEsiti, uo: List[Dict[str, Any]], *,
                ricevuto_ms: int, publish_time_ms: int = 1_700_000_001_000) -> None:
    """Il runner LIVE riceve dallo stream ordini questi ``uo`` sul mercato 3,5 e
    li pubblica; il client di Mike li incassa (come dal socket)."""
    from betfairlightweight.streaming.cache import OrderBookCache
    from types import SimpleNamespace

    cache = OrderBookCache(MERCATO_35, publish_time_ms, False)
    cache.update_cache({"id": MERCATO_35, "orc": [{"id": SEL_UNDER_35, "uo": uo}]},
                       publish_time_ms)
    co = cache.create_resource(0)
    co.client = SimpleNamespace(paper_trade=False)     # il client REALE del runner
    testi: List[str] = []
    n = EO.pubblica_conto_da_evento(
        SimpleNamespace(event=[co]),
        lambda t, d: testi.append(json.dumps({"t": t, "d": d}, default=str)),
        adesso_ms=ricevuto_ms)
    assert n == 1
    for testo in testi:
        assert client_mike.incassa(testo) is True


def _mike_col_canale() -> EO.ClientEsiti:
    memoria = EO.MemoriaConto()
    S.installa_conto_canale(memoria)
    return EO.ClientEsiti(memoria, topic=EO.TOPIC_CONTO, porta_ws=1)


def _giro(mercato: Any, ctx: E.MatchCtx, now: float, *, db: Optional[DbFinto] = None,
          mode: str = "live") -> bool:
    return S._sorveglia_posizione_di_conto(
        db=db or DbFinto(), market=mercato, ctx=ctx, ev=evento(),
        extra=dict(evento()["ctx"]), params=PAR, mode=mode, now_ts=now)


# ===========================================================================
# 1. LA CHIUSURA DAL SITO SI VEDE AL GIRO DOPO, NON DOPO LA CADENZA
# ===========================================================================
def test_la_chiusura_dal_sito_si_vede_al_primo_giro_dopo_lo_stream():
    client = _mike_col_canale()
    db = DbFinto()
    mercato = MercatoConto(morti=[dict(MIKE_BACK)])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    t0 = KO + 1000.0
    assert _giro(mercato, ctx, t0, db=db) is False           # REST a cadenza: intatta
    letture = len(mercato.letture)
    # l'utente chiude dal sito: il conto lo sa, lo stream ordini lo porta
    mercato.morti.append(dict(LAY_UTENTE))
    _dal_runner(client, [UO_MIKE, UO_UTENTE], ricevuto_ms=int((t0 + 0.4) * 1000))
    # giro successivo, un secondo dopo: la cadenza (30 s) NON e' passata
    assert _giro(mercato, ctx, t0 + 1.0, db=db) is True
    assert ctx.chiuso_dall_utente is True and ctx.no_reentry is True
    assert len(mercato.letture) == letture + 2, "la REST riletta SUBITO, a conferma"
    p = db.payload("chiuso_dall_utente")
    assert p["dove"] == "fuori dall'app (stream ordini)"
    assert p["conferma"] == "posizione di conto riletta via REST"
    assert p["segnale"]["verdetto_dal_canale"] == "chiusa"
    assert p["latenza_ms"]["dal_runner"] == 600
    assert p["selezioni"][0]["netto_di_conto"] == 0.0


def test_senza_canale_la_stessa_chiusura_aspetta_la_cadenza_come_prima():
    """Il fatto del 30/09 riprodotto: senza canale il giro dopo NON la vede;
    la vede la REST alla cadenza (``reconcile_every_s``), con ``dove`` di sempre."""
    db = DbFinto()
    mercato = MercatoConto(morti=[dict(MIKE_BACK)])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    t0 = KO + 1000.0
    assert _giro(mercato, ctx, t0, db=db) is False
    mercato.morti.append(dict(LAY_UTENTE))
    letture = len(mercato.letture)
    assert _giro(mercato, ctx, t0 + 1.0, db=db) is False
    assert len(mercato.letture) == letture
    assert _giro(mercato, ctx, t0 + 31.0, db=db) is True
    assert db.payload("chiuso_dall_utente")["dove"] == "fuori dall'app"


# ===========================================================================
# 2. NESSUN FALSO ALLARME
# ===========================================================================
def test_un_ordine_del_bot_sullo_stream_non_fa_rileggere_niente():
    client = _mike_col_canale()
    mercato = MercatoConto(morti=[dict(MIKE_BACK)])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    t0 = KO + 1000.0
    _giro(mercato, ctx, t0)
    letture = len(mercato.letture)
    _dal_runner(client, [UO_MIKE], ricevuto_ms=int((t0 + 0.2) * 1000))
    assert _giro(mercato, ctx, t0 + 1.0) is False
    assert len(mercato.letture) == letture, "posizione intera: nessuna REST fuori cadenza"
    assert ctx.chiuso_dall_utente is False


def test_il_canale_dice_chiusa_ma_il_conto_no_vince_il_conto():
    """Lo stream conosce solo gli ordini visti dalla sua iscrizione: un back
    dell'utente di PRIMA non c'e'. Col solo canale la posizione sembrerebbe
    chiusa (10 - 10); il conto vero (con il back da 10 dell'utente) dice che la
    posizione di Mike e' ancora tutta viva. Mike non si spegne."""
    client = _mike_col_canale()
    db = DbFinto()
    back_utente_vecchio = ordine_conto(ref=None, side="back", abbinato=10.0, bet_id="U0")
    mercato = MercatoConto(morti=[dict(MIKE_BACK), back_utente_vecchio])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    t0 = KO + 1000.0
    _giro(mercato, ctx, t0, db=db)
    mercato.morti.append(dict(LAY_UTENTE))
    _dal_runner(client, [UO_MIKE, UO_UTENTE], ricevuto_ms=int((t0 + 0.3) * 1000))
    assert _giro(mercato, ctx, t0 + 1.0, db=db) is False
    assert ctx.chiuso_dall_utente is False
    assert "chiuso_dall_utente" not in db.kinds()
    nc = [p for k, p in db.log_scritti
          if k == "posizione_di_conto" and p.get("verdetto") == "canale_non_confermato"]
    assert len(nc) == 1 and nc[0]["segnale"]["verdetto_dal_canale"] == "chiusa"


def test_in_PAPER_il_canale_del_conto_non_conta():
    client = _mike_col_canale()
    mercato = MercatoConto(morti=[dict(MIKE_BACK), dict(LAY_UTENTE)])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    _dal_runner(client, [UO_MIKE, UO_UTENTE], ricevuto_ms=1)
    assert _giro(mercato, ctx, KO + 1000.0, mode="paper") is False
    assert mercato.letture == [] and ctx.chiuso_dall_utente is False


# ===========================================================================
# 3. FAIL-CLOSED: rete giu' alla conferma, fotografia gia' vista
# ===========================================================================
def test_la_rete_giu_alla_conferma_non_decide_e_riprova_al_giro_dopo():
    client = _mike_col_canale()
    db = DbFinto()
    mercato = MercatoConto(morti=[dict(MIKE_BACK)])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    t0 = KO + 1000.0
    _giro(mercato, ctx, t0, db=db)
    mercato.morti.append(dict(LAY_UTENTE))
    _dal_runner(client, [UO_MIKE, UO_UTENTE], ricevuto_ms=int((t0 + 0.5) * 1000))
    mercato.esplode = True
    assert _giro(mercato, ctx, t0 + 1.0, db=db) is False
    assert ctx.chiuso_dall_utente is False, "senza la conferma del conto non si decide"
    assert "E1" in S._CONTO_SEGNALE, "il segnale resta in attesa di conferma"
    mercato.esplode = False
    assert _giro(mercato, ctx, t0 + 2.0, db=db) is True
    assert db.payload("chiuso_dall_utente")["dove"] == "fuori dall'app (stream ordini)"
    assert db.payload("chiuso_dall_utente")["latenza_ms"]["dal_runner"] == 1500


def test_la_stessa_fotografia_non_fa_rileggere_la_REST_due_volte():
    """Il canale segnala una riduzione PARZIALE che la REST NON conferma (il
    conto ha un back dell'utente di prima dell'iscrizione dello stream: la
    posizione di Mike e' intera). Al giro dopo, senza fotografie nuove,
    nessuna REST fuori cadenza.

    08/10 (W3a): prima questo test usava una riduzione parziale CONFERMATA e
    asseriva che Mike continuasse; dall'ordine dell'utente dell'08/10 una
    riduzione parziale confermata FERMA Mike (vedi
    ``test_mike_w3a_consapevolezza_2026_10_08.py``). La proprieta' provata qui
    (una fotografia gia' giudicata non fa rileggere la REST) resta la stessa."""
    client = _mike_col_canale()
    db = DbFinto()
    back_utente_vecchio = ordine_conto(ref=None, side="back", abbinato=4.0, bet_id="U0")
    mercato = MercatoConto(morti=[dict(MIKE_BACK), back_utente_vecchio])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    t0 = KO + 1000.0
    _giro(mercato, ctx, t0, db=db)
    parziale = ordine_conto(ref=None, side="lay", abbinato=4.0, bet_id="U1")
    mercato.morti.append(parziale)
    _dal_runner(client, [UO_MIKE, _uo("U1", side="L", sm=4.0, rfo=None, rfs=None)],
                ricevuto_ms=int((t0 + 0.5) * 1000))
    letture = len(mercato.letture)
    assert _giro(mercato, ctx, t0 + 1.0, db=db) is False
    assert len(mercato.letture) == letture + 2
    assert db.payload("posizione_di_conto")["verdetto"] == "canale_non_confermato"
    assert _giro(mercato, ctx, t0 + 2.0, db=db) is False
    assert len(mercato.letture) == letture + 2, "nessuna fotografia nuova: niente REST"


def test_lo_snap_ripetuto_dello_stream_non_fa_rileggere_la_REST():
    """flumine rifa' la fotografia di ogni mercato aperto ogni 3 s quando ha
    ordini vivi (``OrderStream.handle_output``, ``SNAP_DELTA``): la STESSA
    riduzione parziale ripubblicata (versione nuova, stesso contenuto) non deve
    far rileggere la REST a ogni snap. Una riduzione DIVERSA si'.

    08/10 (W3a): il conto ha un back dell'utente di PRIMA dell'iscrizione dello
    stream (4,00), cosi' la prima riduzione (4) NON e' confermata dalla REST e
    Mike resta acceso: dall'08/10 una riduzione parziale confermata lo ferma, e
    la proprieta' degli snap ripetuti va provata su un Mike ancora acceso."""
    client = _mike_col_canale()
    db = DbFinto()
    mercato = MercatoConto(morti=[dict(MIKE_BACK),
                                  ordine_conto(ref=None, side="back", abbinato=4.0,
                                               bet_id="U0")])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    t0 = KO + 1000.0
    _giro(mercato, ctx, t0, db=db)
    mercato.morti.append(ordine_conto(ref=None, side="lay", abbinato=4.0, bet_id="U1"))
    uo = [UO_MIKE, _uo("U1", side="L", sm=4.0, rfo=None, rfs=None)]
    _dal_runner(client, uo, ricevuto_ms=int((t0 + 0.5) * 1000))
    _giro(mercato, ctx, t0 + 1.0, db=db)
    letture = len(mercato.letture)
    for i in range(3):                       # tre snap identici, 3 s l'uno dall'altro
        _dal_runner(client, uo, ricevuto_ms=int((t0 + 3.0 * (i + 1)) * 1000))
        assert _giro(mercato, ctx, t0 + 3.0 * (i + 1) + 0.5, db=db) is False
    assert len(mercato.letture) == letture, "snap identici: nessuna REST fuori cadenza"
    # l'utente riduce ancora (da 4 a 6): situazione nuova -> REST subito
    mercato.morti[-1] = ordine_conto(ref=None, side="lay", abbinato=6.0, bet_id="U1")
    _dal_runner(client, [UO_MIKE, _uo("U1", side="L", sm=6.0, rfo=None, rfs=None)],
                ricevuto_ms=int((t0 + 12.0) * 1000))
    _giro(mercato, ctx, t0 + 12.5, db=db)
    assert len(mercato.letture) == letture + 2


def test_gambe_di_mike_fuori_dalla_fotografia_ma_ordine_altrui_si_rilegge_la_REST():
    """Il runner e' ripartito dopo gli ordini di Mike: nella fotografia c'e' solo
    la lay dell'utente. Il canale non sa confrontare ('da_confrontare'): la REST
    si rilegge subito e decide lei."""
    client = _mike_col_canale()
    db = DbFinto()
    mercato = MercatoConto(morti=[dict(MIKE_BACK)])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
    t0 = KO + 1000.0
    _giro(mercato, ctx, t0, db=db)
    mercato.morti.append(dict(LAY_UTENTE))
    _dal_runner(client, [UO_UTENTE], ricevuto_ms=int((t0 + 0.5) * 1000))
    assert _giro(mercato, ctx, t0 + 1.0, db=db) is True
    p = db.payload("chiuso_dall_utente")
    assert p["segnale"]["verdetto_dal_canale"] == "da_confrontare"
    assert not [x for k, x in db.log_scritti
                if k == "posizione_di_conto" and x.get("verdetto") == "gambe_non_ritrovate"], \
        "la REST ritrova le gambe: nessuna riconciliazione dichiarata"


def test_senza_posizione_aperta_il_canale_non_fa_leggere_niente():
    client = _mike_col_canale()
    mercato = MercatoConto(morti=[dict(LAY_UTENTE)])
    ctx = E.MatchCtx(state="WATCH", legs=[])
    _dal_runner(client, [UO_UTENTE], ricevuto_ms=1)
    assert _giro(mercato, ctx, KO + 1000.0) is False
    assert mercato.letture == []


def test_lazzeramento_del_banco_svuota_la_memoria_del_conto():
    client = _mike_col_canale()
    _dal_runner(client, [UO_MIKE], ricevuto_ms=1)
    S._CONTO_VISTO["E1|1.35"] = 3
    azzerati = S.azzera_cache_di_processo()
    assert "_CONTO_CANALE" in azzerati and "_CONTO_VISTO" in azzerati
    assert S._CONTO_CANALE["memoria"].mercato(MERCATO_35) is None
    assert S._CONTO_VISTO == {}


def test_linterruttore_spegne_il_lettore(monkeypatch):
    monkeypatch.setenv(S.ENV_MIKE_CONTO_CANALE, "0")
    assert S.avvia_conto_dal_canale() is False
    assert S._CONTO_CANALE["client"] is None and S._CONTO_CANALE["memoria"] is None


# ===========================================================================
# 4. DAL CAPO ALLA CODA: flumine vero, canale vero, client vero di Mike
# ===========================================================================
def _porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _aspetta(cond, secondi: float = 5.0) -> bool:
    fine = time.time() + secondi
    while time.time() < fine:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


def test_capo_coda_dallo_stream_del_runner_al_verdetto_di_mike(monkeypatch):
    from betfairlightweight import APIClient
    from betfairlightweight.streaming.cache import OrderBookCache
    from flumine import Flumine, clients
    from flumine.events.events import CurrentOrdersEvent

    from Betfair.stream import local_channel as LC
    from Betfair.stream.engine.live_trading_strategy import LiveTradingStrategy

    porta = _porta_libera()
    ch = LC.LocalChannel(porta, "calcio")
    assert ch.start()
    monkeypatch.setattr(LC, "_CHANNEL", ch)               # il canale del runner
    monkeypatch.setenv("LIVE_LOCAL_WS_PORT", str(porta))
    monkeypatch.delenv(S.ENV_MIKE_CONTO_CANALE, raising=False)
    monkeypatch.setitem(S._CONTO_CANALE, "client", None)
    # il runner LIVE: flumine vero, strategia LIVE vera, montata da ``start``
    client = clients.BetfairClient(APIClient("u", "p", app_key="k"), paper_trade=False,
                                   order_stream=True)
    fw = Flumine(client=client)
    LiveTradingStrategy(market_filter={}, mode="live").start(fw)
    # Mike accende il suo lettore (il client VERO, thread e socket veri)
    assert S.avvia_conto_dal_canale() is True
    lettore = S._CONTO_CANALE["client"]
    try:
        assert _aspetta(lambda: lettore.collegato and ch._n_clients == 1)
        db = DbFinto()
        mercato = MercatoConto(morti=[dict(MIKE_BACK)])
        ctx = E.MatchCtx(state="LIVE_COVERED", legs=[gamba_ingresso()])
        adesso = time.time()
        _giro(mercato, ctx, adesso, db=db)
        mercato.morti.append(dict(LAY_UTENTE))
        cache = OrderBookCache(MERCATO_35, int(adesso * 1000), False)
        cache.update_cache({"id": MERCATO_35, "orc": [{"id": SEL_UNDER_35,
                                                       "uo": [UO_MIKE, UO_UTENTE]}]},
                           int(adesso * 1000))
        co = cache.create_resource(0)
        co.client = client
        t0 = time.time()
        fw._process_current_orders(CurrentOrdersEvent([co]))    # lo stream ordini
        memoria = S._CONTO_CANALE["memoria"]
        assert _aspetta(lambda: memoria.mercato(MERCATO_35) is not None, 5.0)
        # il giro di Mike subito dopo l'arrivo (in produzione: il giro successivo)
        assert _giro(mercato, ctx, time.time(), db=db) is True
        ms = (time.time() - t0) * 1000.0
        p = db.payload("chiuso_dall_utente")
        assert p["dove"] == "fuori dall'app (stream ordini)"
        assert 0 <= p["latenza_ms"]["dal_runner"] < 1000
        assert ms < 1000.0, "dallo stream al verdetto: %.1f ms" % ms
    finally:
        lettore.ferma()
        S._CONTO_CANALE["client"] = None


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
