"""W3b (08/10) - LO SCALPER CALCIO SA SUBITO DEGLI ORDINI ESTERNI (sito, app).

Ordine dell'utente: "quando intervengo io dal sito o dall'app su un'operazione dei
bot, i bot lo sanno e non fanno altro", "nel minor tempo possibile".

Tutto con oggetti VERI dove esistono:
  * ``Flumine`` VERO con ``BetfairClient`` VERO (nessun login: il costruttore non
    tocca la rete), il suo ``_process_current_orders`` e ``CurrentOrdersEvent``;
  * la cache VERA dello stream ordini (``OrderBookCache``) e gli ordini del bot
    creati DA FLUMINE dal messaggio dello stream (``create_order_from_current``:
    il ref ``name_hash-id`` della strategia);
  * l'osservatore VERO del runner calcio (``esiti_ordini_canale``), montato dalla
    funzione della sessione (``scalper_session.installa_ordini_esterni``).
L'unico punto sostituito e' ``Market.cancel_order`` (il confine con la rete:
un annullo vero partirebbe verso Betfair): si REGISTRA.

Ogni test e' falsificato (referto ``AUDIT_2026-10-08/W3B_CONSAPEVOLEZZA_FLUMINE.md``).
ASCII-only.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest

from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.tennis_scalper import ordini_esterni as OE

MERCATO = "1.200"
ALTRO = "1.201"
SEL = 47999
#: l'istante dei messaggi: l'orologio VERO (il produttore timbra ``ricevuto_ms``
#: con ``time.time``, come in produzione)
PT = int(time.time() * 1000)


def _ora() -> int:
    return int(time.time() * 1000)


def _strategia(nome: str = "SCmaker35760084") -> Any:
    from flumine import BaseStrategy

    class _S(BaseStrategy):
        def check_market_book(self, market: Any, market_book: Any) -> bool:  # noqa: ARG002
            return True

        def process_market_book(self, market: Any, market_book: Any) -> None:  # noqa: ARG002
            return None

    return _S(market_filter={}, name=nome)


def _client(paper: bool) -> Any:
    from betfairlightweight import APIClient
    from flumine import clients

    return clients.BetfairClient(APIClient("u", "p", app_key="k"), paper_trade=paper,
                                 order_stream=True)


def _uo(bet_id: str, *, side: str, sm: float, rfo: Any, rfs: Any, stato: str = "EC",
        p: float = 1.5, pd: Any = None, sr: float = 0.0) -> Dict[str, Any]:
    """Un ordine nella grafia dello STREAM di Betfair (``uo``). ``pd`` di serie:
    piazzato ADESSO (dopo l'accensione della sorveglianza)."""
    if pd is None:
        pd = _ora() + 1
    return {"id": bet_id, "p": p, "s": sm + sr, "side": side, "status": stato, "pt": "L",
            "ot": "L", "pd": pd, "md": pd + 500, "avp": p if sm > 0 else None, "sm": sm,
            "sr": sr, "sl": 0.0, "sc": 0.0, "sv": 0.0, "rfo": rfo, "rfs": rfs}


def _evento(client: Any, uo: List[Dict[str, Any]], *, market_id: str = MERCATO,
            pt: int = PT) -> Any:
    from betfairlightweight.streaming.cache import OrderBookCache
    from flumine.events.events import CurrentOrdersEvent

    cache = OrderBookCache(market_id, pt, False)
    cache.update_cache({"id": market_id, "orc": [{"id": SEL, "uo": uo}]}, pt)
    co = cache.create_resource(0)
    co.client = client
    return CurrentOrdersEvent([co])


class _Risposta:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _Query:
    """Il builder di supabase-py (``table().select().eq().in_().execute()``):
    filtri veri sulle righe in memoria; ``giu`` = ogni lettura solleva."""

    def __init__(self, sb: "_SbFinto", nome: str) -> None:
        self.sb, self.nome, self.filtri = sb, nome, []

    def select(self, *_a: Any, **_k: Any) -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self.filtri.append((col, {str(val)}))
        return self

    def in_(self, col: str, vals: Any) -> "_Query":
        self.filtri.append((col, {str(v) for v in vals}))
        return self

    def execute(self) -> _Risposta:
        self.sb.letture += 1
        if self.sb.giu:
            raise ConnectionError("DB irraggiungibile")
        return _Risposta([dict(r) for r in self.sb.tabelle.get(self.nome, [])
                          if all(str(r.get(c)) in v for c, v in self.filtri)])


class _SbFinto:
    def __init__(self, tabelle: Any = None, giu: bool = False) -> None:
        self.tabelle = dict(tabelle or {})
        self.giu = giu
        self.letture = 0

    def table(self, nome: str) -> _Query:
        return _Query(self, nome)


def _conferma_su(sb: _SbFinto) -> OE.ConfermaBot:
    """La verifica di PRODUZIONE (regola VERA di W2, ``_proprietari_bot``) sul DB
    in memoria, sincrona (nessun thread nei test)."""
    from Betfair.stream import live_order_worker as LOW

    return OE.ConfermaBot(lambda ids: LOW._proprietari_bot(sb, ids), in_thread=False)


class _Banco:
    """Flumine VERO + strategia VERA + sorveglianza montata dalla sessione, con la
    verifica "del bot / fuori bot" sul DB in memoria (vuoto = nessun bot)."""

    def __init__(self, monkeypatch: Any, *, paper: bool = False,
                 mercati=(MERCATO,), tabelle: Any = None, db_giu: bool = False,
                 conferma: Any = None) -> None:
        from flumine import Flumine
        from flumine.markets.market import Market

        self.annullati: List[str] = []
        banco = self

        def _cancel(market: Any, order: Any, size_reduction: Any = None,
                    force: bool = False) -> bool:
            banco.annullati.append(str(order.bet_id))
            return True

        monkeypatch.setattr(Market, "cancel_order", _cancel)
        self.client = _client(paper)
        self.fw = Flumine(client=self.client)
        self.s = _strategia()
        self.fw.add_strategy(self.s)
        self.diario: List[tuple] = []
        self.sb = _SbFinto(tabelle, giu=db_giu)
        self.conferma = conferma if conferma is not None else _conferma_su(self.sb)
        self.esterni = SS.installa_ordini_esterni(
            self.fw, [self.s, None], session_paper=paper, event_id="E1",
            sink=lambda k, p: self.diario.append((k, p)), adesso_ms=_ora,
            mercati_sessione=list(mercati), conferma=self.conferma)

    def kinds(self) -> List[str]:
        return [k for k, _p in self.diario]

    def proprio(self, bet_id: str, n: int, *, sm: float, sr: float = 0.0,
                stato: str = "E") -> Dict[str, Any]:
        return _uo(bet_id, side="B", sm=sm, sr=sr, stato=stato,
                   rfo="%s-%d" % (self.s.name_hash, n), rfs=self.s.name[:15])

    def stream(self, uo: List[Dict[str, Any]], **kw: Any) -> None:
        self.fw._process_current_orders(_evento(self.client, uo, **kw))


# ===========================================================================
# 1. IL MONTAGGIO
# ===========================================================================
def test_in_live_la_sessione_monta_l_osservatore_sul_suo_flumine(monkeypatch):
    b = _Banco(monkeypatch)
    assert b.esterni is not None and b.esterni.montato is True
    assert b.fw._conto_osservato is True
    assert b.s._ordini_esterni is b.esterni


def test_in_prova_niente_identico_a_prima(monkeypatch):
    """Paper: nessuna sorveglianza, ``check_market_book`` e' quello della classe."""
    b = _Banco(monkeypatch, paper=True)
    assert b.esterni is None
    assert "check_market_book" not in vars(b.s)
    assert not getattr(b.fw, "_conto_osservato", False)


def test_interruttore_spento_identico_a_prima(monkeypatch):
    monkeypatch.setenv(OE.ENV, "0")
    b = _Banco(monkeypatch)
    assert b.esterni is None
    assert "check_market_book" not in vars(b.s)
    assert not getattr(b.fw, "_conto_osservato", False)


# ===========================================================================
# 2. GLI ORDINI DEL BOT NON SONO ESTERNI
# ===========================================================================
def test_gli_ordini_del_bot_dallo_stream_non_sono_un_intervento(monkeypatch):
    b = _Banco(monkeypatch)
    b.stream([b.proprio("B1", 1, sm=5.0, sr=20.0)])
    blotter = b.fw.markets.markets[MERCATO].blotter
    assert [o.bet_id for o in blotter.strategy_orders(b.s)] == ["B1"], \
        "flumine crea l'ordine del bot dal ref dello stream"
    assert b.esterni.intervento is None
    assert b.esterni.conti[OE.PROPRIO] == 1 and b.esterni.conti[OE.UTENTE] == 0
    assert b.s.check_market_book(None, None) is True
    assert b.annullati == []


def test_gli_ordini_di_un_altro_bot_non_sono_un_intervento(monkeypatch):
    """Mike (ref ``mike-t1``, strategia ``mike``), Omega, un comando del motore."""
    b = _Banco(monkeypatch)
    b.stream([b.proprio("B1", 1, sm=5.0, sr=20.0),
              _uo("M1", side="L", sm=10.0, rfo="mike-t1", rfs="mike"),
              _uo("O1", side="L", sm=10.0, rfo="omega-t9", rfs=None),
              _uo("S1", side="L", sm=10.0, rfo=None, rfs="safe")])
    assert b.esterni.intervento is None
    assert b.esterni.conti[OE.BOT] == 3


# ===========================================================================
# 3. L'ORDINE DELL'UTENTE SUL MERCATO DEL BOT: STOP SUBITO
# ===========================================================================
def test_ordine_dal_sito_abbinato_ferma_la_sessione_al_messaggio(monkeypatch):
    b = _Banco(monkeypatch)
    b.stream([b.proprio("B1", 1, sm=5.0, sr=20.0)])
    b.stream([b.proprio("B1", 1, sm=5.0, sr=20.0),
              _uo("U1", side="L", sm=4.0, rfo=None, rfs=None, p=1.45)],
             pt=PT + 1000)
    ev = b.esterni.intervento
    assert ev is not None, "l'ordine dal sito abbinato sul mercato del bot e' un intervento"
    assert ev["dove"] == "sito" and ev["market_id"] == MERCATO and ev["bet_id"] == "U1"
    assert ev["abbinato_nuovo"] == 4.0 and ev["modo"] == "live"
    assert ev["fonte"] == OE.FONTE_STREAM
    assert ev["latenza_ms"] is not None and 0 <= ev["latenza_ms"] < 1000
    # il bot non decide piu' e i suoi vivi sono annullati, nello STESSO messaggio
    assert b.s.check_market_book(None, None) is False
    assert getattr(b.s, "_fermo_per_intervento", False) is True, \
        "fermato per istanza, non solo dall'involucro della sorveglianza"
    assert b.annullati == ["B1"]
    assert b.kinds() == [OE.KIND_VERIFICA, OE.KIND], "prima la verifica, poi lo stop"


def test_ordine_manuale_dell_app_e_un_intervento(monkeypatch):
    b = _Banco(monkeypatch)
    b.stream([b.proprio("B1", 1, sm=5.0),
              _uo("A1", side="L", sm=3.0, rfo="abcdef0123456-77", rfs="live")])
    assert b.esterni.intervento is not None
    assert b.esterni.intervento["dove"] == "app"


def test_ordine_dell_utente_non_abbinato_non_e_ancora_un_intervento(monkeypatch):
    b = _Banco(monkeypatch)
    b.stream([b.proprio("B1", 1, sm=5.0),
              _uo("U1", side="L", sm=0.0, sr=4.0, stato="E", rfo=None, rfs=None)])
    assert b.esterni.intervento is None
    b.stream([b.proprio("B1", 1, sm=5.0),
              _uo("U1", side="L", sm=1.0, sr=3.0, stato="E", rfo=None, rfs=None)],
             pt=PT + 2000)
    assert b.esterni.intervento is not None and b.esterni.intervento["abbinato_nuovo"] == 1.0


def test_ordine_dell_utente_su_un_altro_mercato_nulla_cambia(monkeypatch):
    b = _Banco(monkeypatch)
    b.stream([b.proprio("B1", 1, sm=5.0, sr=20.0)])
    b.stream([_uo("U1", side="L", sm=4.0, rfo=None, rfs=None)], market_id=ALTRO)
    assert b.esterni.intervento is None
    assert b.esterni.conti["fuori_dal_bot"] == 1
    assert b.s.check_market_book(None, None) is True
    assert b.annullati == []


def test_ordine_dell_utente_su_un_mercato_della_sessione_senza_ordini_del_bot(monkeypatch):
    """Il catalogo della sessione e' del bot anche prima del suo primo ordine:
    il bot non entra mai sopra una posizione dell'utente."""
    b = _Banco(monkeypatch, mercati=(MERCATO, ALTRO))
    b.stream([_uo("U1", side="L", sm=4.0, rfo=None, rfs=None)], market_id=ALTRO)
    assert b.esterni.intervento is not None


def test_ordine_dell_utente_di_prima_dell_accensione_conta_solo_per_il_nuovo(monkeypatch):
    b = _Banco(monkeypatch)
    vecchio = PT - 3_600_000
    b.stream([b.proprio("B1", 1, sm=5.0),
              _uo("U0", side="L", sm=10.0, sr=5.0, stato="E", rfo=None, rfs=None,
                  pd=vecchio)])
    assert b.esterni.intervento is None, "l'immagine iniziale dello stream non e' un intervento"
    b.stream([b.proprio("B1", 1, sm=5.0),
              _uo("U0", side="L", sm=12.0, sr=3.0, stato="E", rfo=None, rfs=None,
                  pd=vecchio)], pt=PT + 5000)
    assert b.esterni.intervento is not None
    assert b.esterni.intervento["abbinato_nuovo"] == 2.0


def test_il_client_paper_affiancato_non_porta_ordini_alla_sorveglianza(monkeypatch):
    """Lo stream del client SIMULATO non e' il conto: il produttore lo scarta."""
    b = _Banco(monkeypatch)
    paper = _client(paper=True)
    b.fw._process_current_orders(_evento(paper, [_uo("U1", side="L", sm=4.0, rfo=None,
                                                      rfs=None)]))
    assert b.esterni.intervento is None
    assert b.esterni.conti["valutazioni"] == 0


def test_una_volta_sola(monkeypatch):
    b = _Banco(monkeypatch)
    b.stream([b.proprio("B1", 1, sm=5.0, sr=20.0),
              _uo("U1", side="L", sm=4.0, rfo=None, rfs=None)])
    primo = b.esterni.intervento
    b.stream([b.proprio("B1", 1, sm=5.0, sr=20.0),
              _uo("U1", side="L", sm=4.0, rfo=None, rfs=None),
              _uo("U2", side="B", sm=2.0, rfo=None, rfs=None)], pt=PT + 9000)
    assert b.esterni.intervento is primo
    assert b.kinds() == [OE.KIND_VERIFICA, OE.KIND], "prima la verifica, poi lo stop"
    assert b.annullati == ["B1"]


# ===========================================================================
# 3-bis. SECONDO GIRO: "del bot / fuori bot" sul DB (regola di W2)
# ===========================================================================
#: l'ordine di Omega dalla CODA del runner calcio: stesso customerStrategyRef del
#: terminale manuale ('live'), ref di flumine della strategia del runner
def _omega_dalla_coda(sm: float = 4.0) -> Dict[str, Any]:
    return _uo("O1", side="L", sm=sm, rfo="abcdef0123456-5", rfs="live")


#: la riga della coda del runner con quel bet_id, colonne di
#: ``betfair_live_order_requests`` lette da ``_proprietari_bot``
_CODA_OMEGA = {"betfair_live_order_requests": [
    {"bet_id": "O1", "client_ref": "omega-t9", "mode": "live",
     "params": {"source": "omega", "trade_id": 9}}]}


def test_ordine_di_omega_dalla_coda_sulla_stessa_selezione_nessuno_stop(monkeypatch):
    b = _Banco(monkeypatch, tabelle=_CODA_OMEGA)
    b.stream([b.proprio("B1", 1, sm=5.0, sr=20.0), _omega_dalla_coda()])
    assert b.esterni.intervento is None, "un ordine di un altro bot non e' l'utente"
    assert not b.esterni.sospesa(MERCATO, SEL), "verifica fatta: sospensione rilasciata"
    assert b.s.check_market_book(None, None) is True
    assert b.annullati == []
    assert b.kinds() == [OE.KIND_VERIFICA, OE.KIND_DI_UN_BOT]
    assert b.esterni.verifiche[0]["motivo"].startswith("bot:coda")
    assert b.esterni.conti["bot_dal_db"] == 0 and b.esterni.in_verifica() == 0


def test_ordine_di_omega_registrato_nella_sua_tabella_nessuno_stop(monkeypatch):
    b = _Banco(monkeypatch, tabelle={"omega_trades": [{"bet_id": "O1", "mode": "live"}]})
    b.stream([_omega_dalla_coda()])
    assert b.esterni.intervento is None
    assert b.esterni.verifiche[0]["motivo"] == "bot:tabella:omega_trades"


def test_ordine_manuale_dell_app_senza_riga_di_bot_e_uno_stop(monkeypatch):
    """Stessi riferimenti di Omega dalla coda, ma il DB non lo conosce: e' l'utente."""
    b = _Banco(monkeypatch, tabelle={"betfair_live_order_requests": [
        {"bet_id": "O1", "client_ref": "awlq77", "mode": "live", "params": {}}]})
    b.stream([b.proprio("B1", 1, sm=5.0, sr=20.0), _omega_dalla_coda()])
    ev = b.esterni.intervento
    assert ev is not None and ev["dove"] == "app"
    assert ev["verifica"]["esito"] == OE.FUORI_BOT
    assert b.annullati == ["B1"]


def test_db_giu_resta_sospeso_nessun_ordine_nuovo_sulla_selezione(monkeypatch):
    from flumine.exceptions import ControlError
    from flumine.order.orderpackage import OrderPackageType
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    b = _Banco(monkeypatch, db_giu=True)
    b.stream([b.proprio("B1", 1, sm=5.0, sr=20.0),
              _uo("U1", side="L", sm=4.0, rfo=None, rfs=None)])
    assert b.esterni.intervento is None, "mai uno stop al buio"
    assert b.esterni.sospesa(MERCATO, SEL)
    assert b.s.check_market_book(None, None) is True, "sospeso, non fermo"
    for _ in range(5):                       # piu' book: un solo avviso
        b.s.check_market_book(None, None)
    assert b.kinds() == [OE.KIND_VERIFICA, OE.KIND_NON_VERIFICABILE]
    assert b.sb.letture == 1, "una lettura (poi si riprova dopo RIPROVA_DB_S)"
    # il controllo di flumine: nessun ordine NUOVO del bot su quella selezione...
    ctrl = [c for c in b.fw.trading_controls if getattr(c, "NAME", "") == "ORDINI_ESTERNI"]
    assert len(ctrl) == 1
    o = Trade(MERCATO, SEL, 0.0, b.s).create_order(
        side="BACK", order_type=LimitOrder(price=2.0, size=2.0))
    with pytest.raises(ControlError):
        ctrl[0](o, OrderPackageType.PLACE)
    assert o.status.name == "VIOLATION"
    # ...gli annulli passano, e le altre selezioni pure
    o2 = Trade(MERCATO, SEL + 1, 0.0, b.s).create_order(
        side="BACK", order_type=LimitOrder(price=2.0, size=2.0))
    ctrl[0](o2, OrderPackageType.PLACE)
    ctrl[0](o, OrderPackageType.CANCEL)


def test_db_che_torna_decide(monkeypatch):
    """Dopo il DB giu' la verifica si ripete (qui subito: riprova 0) e decide."""
    sb = _SbFinto(giu=True)
    from Betfair.stream import live_order_worker as LOW

    conferma = OE.ConfermaBot(lambda ids: LOW._proprietari_bot(sb, ids), in_thread=False,
                              riprova_s=0.0)
    b = _Banco(monkeypatch, conferma=conferma)
    b.stream([_uo("U1", side="L", sm=4.0, rfo=None, rfs=None)])
    assert b.esterni.intervento is None and b.esterni.sospesa(MERCATO, SEL)
    sb.giu = False
    b.s.check_market_book(None, None)
    assert b.esterni.intervento is not None
    assert b.esterni.intervento["verifica"]["esito"] == OE.FUORI_BOT


def test_una_lettura_per_bet_id_mai_nel_giro_caldo(monkeypatch):
    b = _Banco(monkeypatch, tabelle=_CODA_OMEGA)
    for i in range(6):
        b.stream([_omega_dalla_coda(sm=4.0 + i)], pt=PT + 1000 * i)
        b.s.check_market_book(None, None)
    assert b.conferma.letture == 1, "un bet_id, una lettura del DB (cache)"
    assert b.sb.letture == 5, "le 5 select di _proprietari_bot, una volta"


def test_verifica_di_produzione_in_un_thread_sveglia_flumine(monkeypatch):
    """``conferma_dei_bot`` (produzione): la lettura gira in un thread suo e mette
    nella coda di flumine l'evento che fa decidere nel thread di flumine."""
    import time as _t

    from flumine.events.events import CustomEvent

    db = type("Db", (), {})()
    db.sb = _SbFinto()
    b = _Banco(monkeypatch, conferma=OE.ConfermaBot(lambda ids: {}, in_thread=False))
    reg = b.esterni.registro
    prod = SS.conferma_dei_bot(db, b.fw, reg)
    b.esterni._conferma = prod
    b.stream([_uo("U1", side="L", sm=4.0, rfo=None, rfs=None)])
    fine = _t.time() + 5
    while _t.time() < fine and prod.esito("U1") is None:
        _t.sleep(0.01)
    assert prod.esito("U1") == OE.FUORI_BOT
    ev = None
    while not b.fw.handler_queue.empty():
        x = b.fw.handler_queue.get_nowait()
        if isinstance(x, CustomEvent):
            ev = x
    assert ev is not None, "la sveglia nella coda di flumine"
    assert b.esterni.intervento is None
    ev.callback(b.fw, ev)                    # come _process_custom_event
    assert b.esterni.intervento is not None
    assert b.esterni.intervento["verifica"]["esito"] == OE.FUORI_BOT


def _sorveglianza(modo: str, chiamate: List[dict]) -> OE.Sorveglianza:
    return OE.Sorveglianza(
        nome="t", modo=modo, rif_manuali=(OE.RIF_MANUALE_CALCIO,), prefissi=("mike-t",),
        identita=OE.Identita([]), bet_ids_propri=set, mercati_del_bot=lambda: {MERCATO},
        al_intervento=chiamate.append, adesso_ms=_ora, inizio_ms=_ora() - 1000)


def _riga_utente(bet_id: str = "U1", sm: float = 4.0) -> Dict[str, Any]:
    return {"betId": bet_id, "marketId": MERCATO, "selectionId": SEL, "side": "LAY",
            "sizeMatched": sm, "averagePriceMatched": 1.5, "placedDate": _ora() + 1,
            "customerStrategyRef": None, "customerOrderRef": None}


def test_la_sorveglianza_reagisce_una_volta_sola_anche_chiamata_di_nuovo():
    chiamate: List[dict] = []
    s = _sorveglianza("live", chiamate)
    assert s.valuta_righe([_riga_utente()], fonte=OE.FONTE_STREAM) is not None
    assert s.valuta_righe([_riga_utente("U2", 6.0)], fonte=OE.FONTE_STREAM) is None
    assert len(chiamate) == 1 and s.intervento["bet_id"] == "U1"


def test_il_registro_non_manda_lo_stream_alle_sorveglianze_paper():
    """Paper e live mai mescolati, anche se una sorveglianza paper finisse nel
    registro del framework: lo stream del conto reale e' solo per le live."""
    from Betfair.stream import esiti_ordini_canale as EO

    reg = OE.Registro()
    chiamate: List[dict] = []
    paper = reg.aggiungi(_sorveglianza("paper", chiamate))
    payload = {"market_id": MERCATO, "ordini": [_riga_utente()], "fonte": EO.FONTE_CONTO,
               "ricevuto_ms": _ora(), "publish_time_ms": _ora(), "snap": False}
    assert reg.ricevi_conto(EO.TOPIC_CONTO, payload) == 0
    assert paper.intervento is None and chiamate == []
    live = reg.aggiungi(_sorveglianza("live", chiamate))
    payload["publish_time_ms"] = _ora() + 10
    assert reg.ricevi_conto(EO.TOPIC_CONTO, payload) == 1
    assert live.intervento is not None and paper.intervento is None
    assert reg.ricevi_conto("order", payload) == 0, "solo il topic del conto"


# ===========================================================================
# 4. LA SESSIONE: causa di arresto, stato finale (sorgente)
# ===========================================================================
def test_intervento_e_una_causa_di_arresto_con_annullo_e_dichiarazione():
    assert SS.CAUSA_INTERVENTO in SS.CAUSE_ARRESTO


def test_la_sessione_esce_stopped_senza_force_flat_e_col_marcatore():
    import inspect

    src = inspect.getsource(SS.run_session)
    i = src.index("if esterni is not None and esterni.intervento is not None:")
    blocco = src[i:src.index("break", i)]
    assert "stopped_by_ui = True" in blocco and "CAUSA_INTERVENTO" in blocco
    assert "_force_flat_all" not in blocco, "nessuna copertura dopo l'intervento"
    # il controllo dell'intervento viene PRIMA di ogni altra via d'uscita del battito
    assert i < src.index("status, params_vivi = db.control_stato_e_params(ev)")
    assert "CAUSA_INTERVENTO: {" in src


def test_contratto_dei_riferimenti_manuali():
    from Betfair.stream import live_order_worker as LOW
    from Betfair.stream.tennis_live import tennis_live_order_worker as TW
    from Betfair.stream.trading import esposizione_fuori_bot as EFB

    assert OE.RIF_MANUALE_CALCIO == LOW.CUSTOMER_STRATEGY_REF == EFB.STRATEGIA_MANUALE_APP
    assert OE.RIF_MANUALE_TENNIS == TW.CUSTOMER_STRATEGY_REF


@pytest.mark.parametrize("valore,atteso", [(None, True), ("", True), ("1", True),
                                           ("0", False), ("off", False), ("FALSE", False)])
def test_interruttore(monkeypatch, valore, atteso):
    if valore is None:
        monkeypatch.delenv(OE.ENV, raising=False)
    else:
        monkeypatch.setenv(OE.ENV, valore)
    assert OE.acceso() is atteso
