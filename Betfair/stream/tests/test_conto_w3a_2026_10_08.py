"""08/10 (W3a) - LA SORVEGLIANZA DEL CONTO, UNA PER TUTTI I BOT, E IL CONTO PAPER.

Ordine dell'utente (08/10): «I bot devono essere al corrente degli ordini
esterni [...] I BOT DEVONO ESSERE AGGIORNATI NEL MINOR TEMPO POSSIBILE SULLE
OPERAZIONI FATTE DA APP O DA SITO». Il paper e' lo SPECCHIO del live.

Cosa provano questi test (modulo ``esiti_ordini_canale`` e runner):
  1. la memoria tiene paper e live SEPARATI anche sullo stesso mercato;
  2. il client accetta i due topic e rifiuta una fotografia che dice il
     contrario del suo topic (paper sul topic live e viceversa);
  3. la SVEGLIA: solo una fotografia dal CONTENUTO nuovo, solo su un mercato
     che interessa al bot; lo snap ripetuto non sveglia;
  4. la dormita svegliabile rispetta il pavimento;
  5. la fotografia PAPER esce dagli ordini flumine con la grafia di
     ``listCurrentOrders`` e passa per il normalizzatore VERO della REST;
  6. la strategia PAPER del runner la pubblica (write-on-change); la LIVE no.

I finti hanno le chiavi e i tipi del vero: gli ordini del blotter paper sono
oggetti con gli STESSI attributi di ``flumine.order.order.BetfairOrder``
(``order_type`` e' un ``LimitOrder`` vero, ``status`` un ``OrderStatus`` vero),
e un test usa un ``BetfairOrder`` vero. ASCII-only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.omega import omega_market as OM
from Betfair.stream import esiti_ordini_canale as EO
from Betfair.stream import local_channel as LC
from Betfair.stream.engine import live_trading_strategy as LTS

MERCATO = "1.300"
SEL = 47972


def _ordine_flumine(bet_id: str, *, side: str = "LAY", stato: str = "EXECUTION_COMPLETE",
                    abbinato: float = 5.0, residuo: float = 0.0, annullato: float = 0.0,
                    prezzo: float = 1.5, size: float = 5.0, ref: str = "awlq7",
                    market_id: str = MERCATO) -> Any:
    """Un ordine del blotter paper con gli attributi di ``BetfairOrder``."""
    from flumine.order.order import OrderStatus
    from flumine.order.ordertype import LimitOrder

    return SimpleNamespace(
        bet_id=bet_id, market_id=market_id, selection_id=SEL, handicap=0.0,
        side=side, status=OrderStatus[stato],
        order_type=LimitOrder(prezzo, size, persistence_type="LAPSE"),
        size_matched=abbinato, size_remaining=residuo, size_cancelled=annullato,
        size_lapsed=0.0, size_voided=0.0,
        average_price_matched=prezzo if abbinato else 0.0,
        context={"customer_order_ref": ref}, notes={"customer_order_ref": ref},
        customer_order_ref="hash-%s" % bet_id,
        responses=SimpleNamespace(date_time_placed=datetime(2026, 10, 8, 12, 0,
                                                             tzinfo=timezone.utc)))


def _foto(market_id: str = MERCATO, *, ordini: List[Dict[str, Any]] = None,
          pt: int = 1000, modo: Any = None) -> Dict[str, Any]:
    p = {"market_id": market_id, "ordini": list(ordini or []), "ricevuto_ms": pt,
         "publish_time_ms": pt}
    if modo is not None:
        p["modo"] = modo
    return p


def _uo(bet_id: str, sm: float, stato: str = "EXECUTION_COMPLETE") -> Dict[str, Any]:
    return {"betId": bet_id, "status": stato, "sizeMatched": sm, "sizeRemaining": 0.0}


# ===========================================================================
# 1. PAPER E LIVE MAI MISCHIATI
# ===========================================================================
def test_memoria_tiene_paper_e_live_separati_sullo_stesso_mercato():
    m = EO.MemoriaConto()
    assert m.ricevi(_foto(ordini=[_uo("L1", 5.0)], modo="live")) is True
    assert m.ricevi(_foto(ordini=[_uo("P1", 3.0)], modo="paper")) is True
    live = m.mercato(MERCATO)
    paper = m.mercato(MERCATO, EO.MODO_PAPER)
    assert [o["betId"] for o in live["ordini"]] == ["L1"] and live["modo"] == "live"
    assert [o["betId"] for o in paper["ordini"]] == ["P1"] and paper["modo"] == "paper"
    # una fotografia SENZA modo e' quella del runner LIVE del 30/09
    assert m.ricevi(_foto(ordini=[_uo("L2", 1.0)], pt=2000)) is True
    assert [o["betId"] for o in m.mercato(MERCATO)["ordini"]] == ["L2"]
    assert [o["betId"] for o in m.mercato(MERCATO, "paper")["ordini"]] == ["P1"]


def test_il_client_rifiuta_la_fotografia_che_contraddice_il_suo_topic():
    m = EO.MemoriaConto()
    c = EO.ClientEsiti(m, topic=EO.TOPIC_CONTO_TUTTI, porta_ws=1)
    assert c.url.endswith("/lettore/conto,conto_paper")
    # paper sul topic LIVE: fuori
    assert c.incassa(json.dumps({"t": "conto", "d": _foto(modo="paper")})) is False
    # live (o senza modo) sul topic PAPER: fuori
    assert c.incassa(json.dumps({"t": "conto_paper", "d": _foto(modo="live")})) is False
    assert c.incassa(json.dumps({"t": "conto_paper", "d": _foto()})) is False
    assert m.stato()["tenute"] == 0
    # le due giuste entrano, ognuna nel suo modo
    assert c.incassa(json.dumps({"t": "conto", "d": _foto(ordini=[_uo("L", 1.0)])})) is True
    assert c.incassa(json.dumps({"t": "conto_paper",
                                 "d": _foto(ordini=[_uo("P", 1.0)], modo="paper")})) is True
    assert m.mercato(MERCATO)["ordini"][0]["betId"] == "L"
    assert m.mercato(MERCATO, "paper")["ordini"][0]["betId"] == "P"


def test_il_client_del_30_09_sul_solo_topic_conto_non_vede_il_paper():
    m = EO.MemoriaConto()
    c = EO.ClientEsiti(m, topic=EO.TOPIC_CONTO, porta_ws=1)
    assert c.incassa(json.dumps({"t": "conto_paper",
                                 "d": _foto(modo="paper")})) is False
    assert m.stato()["ricevute"] == 0


def test_la_sorveglianza_separa_le_versioni_paper_e_live():
    sc = EO.SorveglianzaConto("prova", "PROVA_CONTO_CANALE")
    m = EO.MemoriaConto()
    sc.installa(m)
    m.ricevi(_foto(ordini=[_uo("L1", 5.0)]))
    f, nuove = sc.fotografie("E1", [MERCATO], modo=EO.MODO_PAPER)
    assert f == {} and nuove is False, "una fotografia LIVE non e' mai paper"
    f, nuove = sc.fotografie("E1", [MERCATO])
    assert nuove is True and f[MERCATO]["ordini"][0]["betId"] == "L1"
    f, nuove = sc.fotografie("E1", [MERCATO])
    assert nuove is False, "la stessa versione non e' nuova due volte"


# ===========================================================================
# 2. LA SVEGLIA: solo contenuto nuovo, solo mercati che interessano
# ===========================================================================
def test_la_sveglia_si_alza_solo_per_un_contenuto_nuovo_su_un_mercato_seguito():
    sc = EO.SorveglianzaConto("prova", "PROVA_CONTO_CANALE")
    seguiti = {MERCATO}
    sc.interessa(lambda mid, modo: mid in seguiti)
    altre: List[tuple] = []
    sc.su_sveglia(lambda mid, modo: altre.append((mid, modo)))
    m = EO.MemoriaConto()
    sc.installa(m)
    m.ricevi(_foto(ordini=[_uo("B1", 5.0)], pt=1))
    assert sc.sveglia_alzata() is True and altre == [(MERCATO, "live")]
    # lo snap ripetuto (stesso contenuto, istante nuovo) NON sveglia
    m.ricevi(_foto(ordini=[_uo("B1", 5.0)], pt=2))
    assert sc.sveglia_alzata() is False
    # un ordine nuovo (l'utente dal sito) sveglia
    m.ricevi(_foto(ordini=[_uo("B1", 5.0), _uo("U1", 5.0)], pt=3))
    assert sc.sveglia_alzata() is True
    # un mercato che il bot NON segue non sveglia
    m.ricevi(_foto("1.999", ordini=[_uo("X", 1.0)], pt=4))
    assert sc.sveglia_alzata() is False
    assert sc.conti["fotografie_cambiate"] == 3 and sc.conti["sveglie"] == 2


def test_la_dormita_si_interrompe_alla_sveglia_ma_rispetta_il_pavimento():
    sc = EO.SorveglianzaConto("prova", "PROVA_CONTO_CANALE")
    orologio = {"t": 0.0}
    dormite: List[float] = []
    sc.sveglia.set()
    svegliato = sc.dormi(10.0, minimo_s=1.0, adesso=lambda: orologio["t"],
                         dormi=lambda s: dormite.append(s))
    assert svegliato is True and dormite == [1.0], "mai prima del pavimento"
    assert sc.sveglia.is_set() is False
    # senza sveglia e' la dormita di sempre (wait fino in fondo)
    assert sc.dormi(0.01, minimo_s=1.0) is False


def test_lo_stato_di_processo_si_azzera_per_il_banco():
    sc = EO.SorveglianzaConto("prova", "PROVA_CONTO_CANALE")
    m = EO.MemoriaConto()
    sc.installa(m)
    m.ricevi(_foto(ordini=[_uo("B1", 5.0)]))
    sc.fotografie("E1", [MERCATO])
    sc.firma_ripetuta("E1", ("chiusa",))
    fatti = sc.azzera()
    assert set(fatti) == {"visto", "firma", "memoria"}
    assert m.mercato(MERCATO) is None and sc.sveglia.is_set() is False


def test_linterruttore_spegne_il_lettore(monkeypatch):
    monkeypatch.setenv("PROVA_CONTO_CANALE", "0")
    sc = EO.SorveglianzaConto("prova", "PROVA_CONTO_CANALE")
    assert sc.avvia() is False and sc.attivo() is False


# ===========================================================================
# 3. LA FOTOGRAFIA PAPER: grafia di listCurrentOrders, normalizzatore VERO
# ===========================================================================
def test_la_fotografia_paper_parla_come_la_REST():
    vivo = _ordine_flumine("P1", side="LAY", stato="EXECUTABLE", abbinato=2.0,
                           residuo=3.0, ref="awlq11")
    morto = _ordine_flumine("P2", side="BACK", abbinato=5.0, ref="awlq12")
    senza_bet = _ordine_flumine("", ref="awlq13")
    altro_mercato = _ordine_flumine("P3", market_id="1.999")
    p = EO.payload_conto_paper(MERCATO, [vivo, morto, senza_bet, altro_mercato],
                               ricevuto_ms=1_700_000_000_000)
    assert p["modo"] == "paper" and p["fonte"] == "blotter_paper"
    assert p["publish_time_ms"] == 1_700_000_000_000
    per_id = {o["betId"]: o for o in p["ordini"]}
    assert set(per_id) == {"P1", "P2"}, "senza bet_id o di un altro mercato: fuori"
    # le STESSE chiavi della fotografia LIVE del 30/09
    chiavi_live = {c for c, _s in EO._CAMPI_ORDINE_CONTO} | {"priceSize"}
    assert set(per_id["P1"]) == chiavi_live
    assert per_id["P1"]["status"] == "EXECUTABLE" and per_id["P2"]["status"] == "EXECUTION_COMPLETE"
    assert per_id["P1"]["customerOrderRef"] == "awlq11"
    json.dumps({"t": EO.TOPIC_CONTO_PAPER, "d": p})   # viaggia sul canale
    # passata per il normalizzatore VERO della REST
    r = OM._riga_corrente(per_id["P1"])
    assert r["side"] == "lay" and r["size_matched"] == 2.0 and r["size_remaining"] == 3.0
    assert r["bet_id"] == "P1" and r["selection_id"] == SEL and r["size_requested"] == 5.0


def test_la_fotografia_paper_legge_un_BetfairOrder_vero():
    from flumine import BaseStrategy
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    class _S(BaseStrategy):
        def check_market_book(self, *a):
            return False

        def process_market_book(self, *a):
            return None

    t = Trade(market_id=MERCATO, selection_id=SEL, handicap=0, strategy=_S(market_filter={}))
    o = t.create_order(side="LAY", order_type=LimitOrder(1.5, 4.0, persistence_type="LAPSE"))
    o.context["customer_order_ref"] = "awlq99"
    o.bet_id = "R1"
    o.executable()
    r = EO.ordine_paper_del_conto(o)
    assert r["betId"] == "R1" and r["side"] == "LAY" and r["customerOrderRef"] == "awlq99"
    assert r["status"] == "EXECUTABLE" and r["sizeRemaining"] == 4.0
    assert r["priceSize"] == {"price": 1.5, "size": 4.0}


def test_con_ref_del_bot_riconosce_i_suoi_per_bet_id():
    righe = [OM._riga_corrente({"betId": "B1", "customerOrderRef": "awlq1", "side": "LAY"}),
             OM._riga_corrente({"betId": "U1", "customerOrderRef": "awlq2", "side": "BACK"})]
    out = EO.con_ref_del_bot(righe, {"B1": "safe-t5"})
    assert [r["customer_order_ref"] for r in out] == ["safe-t5", "awlq2"]
    assert righe[0]["customer_order_ref"] == "awlq1", "le righe di partenza non si toccano"


# ===========================================================================
# 4. IL RUNNER: la strategia PAPER pubblica, la LIVE no
# ===========================================================================
class _Blotter:
    def __init__(self, ordini: List[Any]) -> None:
        self.ordini = ordini

    def strategy_orders(self, _strategia: Any) -> List[Any]:
        return list(self.ordini)

    def get_exposures(self, *_a: Any) -> Dict[str, float]:
        return {}

    def selection_exposure(self, *_a: Any) -> float:
        return 0.0

    def strategy_selection_orders(self, *_a: Any, **_k: Any) -> List[Any]:
        return []


class _Db:
    def upsert_live_order(self, _r: Any) -> None:
        pass

    def upsert_live_position(self, _r: Any) -> None:
        pass

    def find_live_order_ref(self, *_a: Any) -> None:
        return None


def _strategia(monkeypatch, mode: str):
    pubblicati: List[tuple] = []
    monkeypatch.setattr(LC, "publish", lambda t, d: pubblicati.append((t, d)))
    monkeypatch.setattr(LTS, "_db", lambda: _Db())
    s = LTS.LiveTradingStrategy(market_filter={}, mode=mode, name="W3A-%s" % mode)
    return s, pubblicati


def test_la_strategia_PAPER_pubblica_il_conto_paper_solo_quando_cambia(monkeypatch):
    s, pubblicati = _strategia(monkeypatch, "paper")
    bot = _ordine_flumine("B1", side="BACK", abbinato=5.0, ref="awlq1")
    mercato = SimpleNamespace(market_id=MERCATO, event_id="E", blotter=_Blotter([bot]),
                              market_catalogue=None)
    s.process_orders(mercato, [bot])
    assert [t for t, _d in pubblicati] == ["conto_paper"]
    assert pubblicati[0][1]["modo"] == "paper"
    s.process_orders(mercato, [bot])                 # niente di nuovo
    assert len(pubblicati) == 1
    # l'utente piazza a mano dall'app (ladder del runner paper)
    manuale = _ordine_flumine("U1", side="LAY", abbinato=5.0, ref="awlq2")
    mercato.blotter.ordini.append(manuale)
    s.process_orders(mercato, [manuale])
    assert len(pubblicati) == 2
    assert {o["betId"] for o in pubblicati[1][1]["ordini"]} == {"B1", "U1"}


def test_la_strategia_LIVE_non_pubblica_il_conto_paper(monkeypatch):
    s, pubblicati = _strategia(monkeypatch, "live")
    o = _ordine_flumine("B1", ref="awlq1")
    mercato = SimpleNamespace(market_id=MERCATO, event_id="E", blotter=_Blotter([o]),
                              market_catalogue=None)
    s.process_orders(mercato, [o])
    assert all(t != "conto_paper" for t, _d in pubblicati)


def test_una_pubblicazione_paper_che_esplode_non_ferma_lo_specchio(monkeypatch):
    s, _pubblicati = _strategia(monkeypatch, "paper")

    class _Rotto(_Blotter):
        def strategy_orders(self, _s: Any) -> List[Any]:
            raise RuntimeError("blotter rotto")

    o = _ordine_flumine("B1", ref="awlq1")
    mercato = SimpleNamespace(market_id=MERCATO, event_id="E", blotter=_Rotto([o]),
                              market_catalogue=None)
    s.process_orders(mercato, [o])          # non solleva


# ===========================================================================
# SECONDA TAPPA (coordinatore, 08/10): di chi e' un ordine altrui
# ===========================================================================
def _riga(bet_id: str, *, side: str = "back", sm: float = 2.0, prezzo: float = 26.0,
          cor: Any = None, csr: Any = None) -> Dict[str, Any]:
    """Una riga normalizzata dal normalizzatore VERO (``_riga_corrente``)."""
    grezzo = {"betId": bet_id, "marketId": MERCATO, "selectionId": SEL,
              "side": side.upper(), "status": "EXECUTION_COMPLETE", "sizeMatched": sm,
              "averagePriceMatched": prezzo, "sizeRemaining": 0.0,
              "priceSize": {"price": prezzo, "size": sm}}
    if cor is not None:
        grezzo["customerOrderRef"] = cor
    if csr is not None:
        grezzo["customerStrategyRef"] = csr
    return OM._riga_corrente(grezzo)


class _Lettore:
    def __init__(self, dei_bot: Dict[str, str] = None, giu: bool = False) -> None:
        self.dei_bot = dict(dei_bot or {})
        self.giu = giu
        self.chiamate: List[tuple] = []

    def __call__(self, bet_ids: List[str], modo: str) -> Dict[str, str]:
        self.chiamate.append((tuple(bet_ids), modo))
        if self.giu:
            raise RuntimeError("DB giu'")
        return {b: m for b, m in self.dei_bot.items() if b in bet_ids}


def test_la_riga_normalizzata_porta_la_strategia_dell_ordine():
    assert _riga("1", csr="omega")["customer_strategy_ref"] == "omega"
    assert _riga("2")["customer_strategy_ref"] is None


def test_proprietari_riferimenti_poi_DB_una_volta_per_bet_id():
    p = EO.ProprietariConto(riprova_s=30.0, orologio=lambda: 0.0)
    leggi = _Lettore({"Q1": "tabella:omega_trades"})
    righe = [_riga("O1", csr="omega", cor="omega-t1"),       # riferimenti: bot
             _riga("S1", cor="safe-t4"),                     # riferimenti: bot
             _riga("Q1", csr="live", cor="awlq1"),           # DB: bot
             _riga("U1"),                                    # DB: utente (sito)
             _riga("Z1", sm=0.0)]                            # senza abbinato: nessuna domanda
    c = p.classifica(righe, leggi=leggi, modo="live")
    assert sorted(a["bet_id"] for a in c["altri_bot"]) == ["O1", "Q1", "S1"]
    assert [r["bet_id"] for r in c["tenute"]] == ["Z1", "U1"]
    assert c["ignoti"] == [] and c["errore"] is None
    assert leggi.chiamate == [(("Q1", "U1"), "live")]
    p.classifica(righe, leggi=leggi, modo="live")
    assert len(leggi.chiamate) == 1, "esiti in memoria: nessuna seconda lettura"
    # paper e live mai sulla stessa memoria
    p.classifica(righe, leggi=leggi, modo="paper")
    assert leggi.chiamate[-1] == (("Q1", "U1"), "paper")


def test_proprietari_DB_giu_ignoti_e_si_ritenta_dopo_il_respiro():
    ora = {"t": 0.0}
    p = EO.ProprietariConto(riprova_s=30.0, orologio=lambda: ora["t"])
    leggi = _Lettore({}, giu=True)
    c = p.classifica([_riga("U1")], leggi=leggi, modo="live")
    assert c["ignoti"] == ["U1"] and c["tenute"] == [] and "DB giu'" in c["errore"]
    ora["t"] = 10.0
    c = p.classifica([_riga("U1")], leggi=leggi, modo="live")
    assert c["ignoti"] == ["U1"] and len(leggi.chiamate) == 1, "nessun martello sul DB"
    leggi.giu = False
    ora["t"] = 31.0
    c = p.classifica([_riga("U1")], leggi=leggi, modo="live")
    assert c["ignoti"] == [] and [r["bet_id"] for r in c["tenute"]] == ["U1"]


def test_proprietari_senza_lettura_contano_i_soli_riferimenti():
    p = EO.ProprietariConto()
    c = p.classifica([_riga("O1", csr="omega"), _riga("U1")], leggi=None, modo="live")
    assert [a["bet_id"] for a in c["altri_bot"]] == ["O1"]
    assert [r["bet_id"] for r in c["tenute"]] == ["U1"] and c["ignoti"] == []
    assert EO.lettore_proprietari(SimpleNamespace()) is None


def test_separa_altrui_e_la_verifica():
    s = EO.SorveglianzaConto("prova", "X")
    parti = s.separa_altrui([_riga("B1", cor="mio-1"), _riga("O1", csr="omega"),
                             _riga("U1")], del_bot=lambda r: r["customer_order_ref"] == "mio-1",
                            leggi=_Lettore({}), modo="live")
    assert [r["bet_id"] for r in parti["bot"]] == ["B1"]
    assert [r["bet_id"] for r in parti["altrui"]] == ["U1"]
    assert [a["bet_id"] for a in parti["altri_bot"]] == ["O1"]
    assert s.metti_in_verifica("E1", "m:1", {"x": 1}) is True
    assert s.metti_in_verifica("E1", "m:1", {"x": 1}) is False
    assert s.eventi_in_verifica() == {"E1"}
    assert s.togli_verifica("E1", "m:1") is True and s.eventi_in_verifica() == set()
    s.metti_in_verifica("E2", "m:2", {})
    assert "verifica" in s.azzera() and s.eventi_in_verifica() == set()


class _SbFinto:
    """Le tabelle con le colonne vere; ``table().select().eq().in_().execute()``."""

    def __init__(self, tabelle: Dict[str, List[Dict[str, Any]]]) -> None:
        self.tabelle = tabelle

    def table(self, nome: str) -> Any:
        sb, filtri = self, []

        class _Q:
            def select(self, *_a: Any) -> Any:
                return self

            def eq(self, k: str, v: Any) -> Any:
                filtri.append((k, [v]))
                return self

            def in_(self, k: str, v: List[Any]) -> Any:
                filtri.append((k, [str(x) for x in v]))
                return self

            def execute(self) -> Any:
                righe = [r for r in sb.tabelle.get(nome, [])
                         if all(str(r.get(k)) in [str(x) for x in vs] for k, vs in filtri)]
                return SimpleNamespace(data=righe)
        return _Q()


def test_proprietari_bot_del_DB_rispetta_il_modo():
    from Betfair.stream.trading import esposizione_fuori_bot as EFB

    sb = _SbFinto({
        "omega_trades": [{"bet_id": "P1", "mode": "paper"}, {"bet_id": "L1", "mode": "live"}],
        "betfair_live_orders": [{"bet_id": "M1", "mode": "paper", "source": "runner"}],
        "betfair_live_order_requests": [
            {"bet_id": "C1", "mode": "paper", "client_ref": "safe-t9", "params": {}}]})
    assert EFB.proprietari_bot(sb, ["P1", "L1", "M1", "C1"], mode="paper") == {
        "P1": "tabella:omega_trades", "C1": "coda:safe-t9"}
    assert EFB.proprietari_bot(sb, ["P1", "L1", "M1", "C1"]) == {"L1": "tabella:omega_trades"}


def test_un_verdetto_per_tutti_ripiego_in_size_identico_a_prima():
    # dati completi: esposizione
    v = EO.verdetto_posizione(atteso=10.0, conto_size=0.0,
                              righe_bot=[{"side": "back", "size_matched": 10.0,
                                          "avg_price_matched": 1.5}],
                              righe_altrui=[{"side": "lay", "size_matched": 10.0,
                                             "avg_price_matched": 1.45}], eps=0.05)
    assert (v["verdetto"], v["metro"]) == ("chiusa", "esposizione")
    # un abbinato senza prezzo: la size di sempre (formula ``vivo`` del 16/09)
    for conto, atteso_v in ((10.0, "intera"), (6.0, "ridotta"), (0.0, "chiusa")):
        v = EO.verdetto_posizione(atteso=10.0, conto_size=conto,
                                  righe_bot=[{"side": "back", "size_matched": 10.0}],
                                  righe_altrui=[], eps=0.05)
        assert (v["verdetto"], v["metro"], v["vivo"]) == (atteso_v, "size",
                                                          EO.vivo_in_size(10.0, conto))


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
