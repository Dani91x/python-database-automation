"""BANCO 30/09 - L'ANNULLO SUL CANALE SI CONFERMA COME LO CONFERMA BETFAIR.

Reperto (revisione M1, ``AUDIT_2026-09-30/replay/mike_tutti_G_bot.txt``): in
OGNI replay di Mike sul trasporto canale compariva "annullo NON confermato ->
riconciliazione" (21 righe in 23 scenari, 1 in ``base``). Catena misurata:
  * il client VERO (``PortaCanale``) manda il ``cancel`` sul ``WsBanco``; il
    ``MotoreOrdini`` VERO lo accetta (ack) e ``live_order_worker._dispatch``
    chiama ``Market.cancel_order`` di flumine: l'ordine va in ``CANCELLING`` e
    il pacchetto CANCEL entra in ``handler_queue`` (``simulated_delay`` =
    ``config.cancel_latency``, 0,17 s);
  * ``execution._annulla_via_canale`` aspetta l'esito (``attendi_esito_bet``,
    3 s di orologio da parete). Nel banco il thread del bot E' il thread del
    replay: mentre il bot aspetta non arriva nessun book, flumine non esegue il
    pacchetto (``_check_pending_packages`` gira solo all'arrivo di un book di
    quel mercato), lo specchio non vede niente -> ``None`` = esito IGNOTO.
  * Nel runner VERO (paper) l'annullo si esegue da solo dopo ``cancel_latency``
    sul book corrente (``SimulatedExecution.handler`` -> thread pool ->
    ``execute_cancel``) e lo ``SimulatedOrderStream`` (0,25 s) lo porta allo
    specchio: il bot lo legge confermato ben dentro i 3 s.

La correzione e' nel BANCO (``PortaBanco.attendi_esecuzione``): dopo un
``cancel`` sul canale il banco fa scorrere il tempo di mercato che Betfair
impiega per un annullo (``cancel_latency``, la stessa regola della coda:
``MotoreReplay.attendi_esecuzione``), flumine lo esegue sul book di quel
momento e lo specchio lo racconta. Il bot non e' toccato.

Tutto con oggetti VERI: registrazione vera 35760084, ``FlumineSimulation`` +
``MotoreReplay`` del banco (``trasporto_rapido.BancoRapido``), ``PortaBanco`` e
``MotoreOrdini`` veri, client VERO di Mike (``PortaCanale`` +
``mike.porta_ordini.VistaMike``), funzione di produzione
``safe_strategy.execution.annulla_su_betfair``. ASCII-only.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List

import pytest

from Betfair.mike import porta_ordini as MPO
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as SPO
from Betfair.stream.backtest import banco_comune as B
from Betfair.stream.backtest import trasporto as TRA

EVENTO = "35760084"


def _cartella_registrazioni() -> str:
    candidati = [os.getenv("LIVE_STREAM_DATA_DIR") or ""]
    radice = Path(__file__).resolve().parents[3]
    candidati += [str(radice / "_live_raw"), str(radice.parents[2] / "_live_raw")]
    for c in candidati:
        if c and os.path.exists(os.path.join(c, EVENTO, "%s.raw.jsonl" % EVENTO)):
            return c
    return ""


pytestmark = pytest.mark.skipif(not _cartella_registrazioni(),
                                reason="registrazione 35760084 assente su questa macchina")


def _banco_con_lay_appoggiata():
    """Banco rapido sul primo MATCH_ODDS aperto pre-partita, porta di Mike sul
    canale e UNA lay appoggiata (LAPSE, niente FOK, quota 1,01: non si abbina)
    mandata dalla vista VERA di Mike. Ritorna (banco, ref, evento dell'ordine)."""
    from Betfair.stream.backtest import trasporto_rapido as TRR

    b = TRR.BancoRapido("mike", EVENTO, _cartella_registrazioni())
    b.__enter__()
    assert b.trova_match_odds(), "nessun MATCH_ODDS aperto nella registrazione"
    b.monta_porta()
    sel = b.quota("lay")[0]
    comando = SPO.costruisci_comando(
        ref="mike-t1", attore="mike", azione="place", mode="paper",
        market_id=b.market_id, selection_id=sel, side="LAY", price=1.01, size=2.0,
        persistence="LAPSE", origine={"tabella": "mike_trades", "id": 1})
    ack = MPO.VistaMike(b.client, appoggiata=True).invia(comando)
    assert ack.arrivato and ack.accettato, ack
    b.pompa(2.0)
    assert b.attendi(lambda: (b.client.esiti("mike-t1") or {}).get("bet_id"), 3.0)
    ev = b.client.esiti("mike-t1")
    assert float(ev["size_remaining"]) == 2.0 and float(ev["size_matched"]) == 0.0, ev
    return b, "mike-t1", ev


def _chiudi(b: Any) -> None:
    b.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# 1. il difetto e la correzione: l'annullo sul canale del banco e' CONFERMATO
# ---------------------------------------------------------------------------
def test_annullo_paper_sul_canale_confermato_e_riletto():
    """Rottura minima: togliere l'attesa dell'annullo in
    ``PortaBanco._dal_socket`` -> ``annulla_su_betfair`` torna ``None`` dopo
    3 s (esito ignoto: la gamba di Mike andrebbe in riconciliazione)."""
    from flumine import config

    b, ref, ev = _banco_con_lay_appoggiata()
    try:
        ora_prima = b.motore._ora_mercato
        t0 = time.monotonic()
        ann = X.annulla_su_betfair(None, bet_id=str(ev["bet_id"]), market_id=b.market_id,
                                   porta=MPO.VistaMike(b.client), mode="paper")
        durata = time.monotonic() - t0
        assert ann is not None, "annullo a esito IGNOTO (il banco non l'ha eseguito)"
        assert ann.ok is True and ann.riletto is True, ann
        assert ann.size_cancelled == 2.0 and ann.size_remaining == 0.0
        assert ann.size_matched == 0.0
        assert durata < 2.0, "il bot non deve consumare i 3 s dell'attesa: %.2f s" % durata
        # il tempo di mercato e' scorso come per Betfair: almeno cancel_latency
        trascorso = (b.motore._ora_mercato - ora_prima).total_seconds()
        assert trascorso >= float(config.cancel_latency), trascorso
        # l'evento del runner: terminale, annullato, size_cancelled vera
        fine = b.client.esiti(ref)
        assert fine["fase"] == "annullato" and float(fine["size_cancelled"]) == 2.0, fine
        # nessun REST: l'annullo paper e' passato SOLO dal canale
        assert [r for r in b.rest if r["azione"] == "cancel"] == []
        # la coda di flumine non ha piu' pacchetti di quel mercato
        assert not [p for p in b.quadro.handler_queue
                    if str(p.market_id) == b.market_id]
    finally:
        _chiudi(b)


def test_annullo_rifiutato_da_flumine_resta_non_confermato():
    """L'attesa non inventa conferme: se al momento dell'annullo il mercato NON
    e' aperto, flumine risponde FAILURE ``ERROR_IN_ORDER``
    (``simulatedorder.py:286-292``, la risposta di Betfair) e l'ordine resta
    vivo: il bot NON deve leggerlo annullato (esito ignoto -> riconciliazione,
    fail-closed come in produzione). Il ``cancel`` usato e' quello VERO di
    flumine, chiamato col book del momento reso SOSPESO. Rottura minima: in
    ``_attendi_annulli`` dichiarare l'ordine annullato (``size_cancelled`` a
    mano) -> diventa verde il falso e questo test rosso."""
    b, ref, ev = _banco_con_lay_appoggiata()
    try:
        ordine = next(iter(b.pb.ordini_visti.values()))
        vero = ordine.simulated.cancel

        def _cancel_a_mercato_sospeso(market_book: Any) -> Any:
            return vero(SimpleNamespace(status="SUSPENDED"))

        ordine.simulated.cancel = _cancel_a_mercato_sospeso
        ann = X.annulla_su_betfair(None, bet_id=str(ev["bet_id"]), market_id=b.market_id,
                                   porta=MPO.VistaMike(b.client), mode="paper")
        assert ann is None or not ann.ok, ann
        assert float(ordine.size_remaining) == 2.0, "l'ordine e' ancora vivo"
        assert (b.client.esiti(ref) or {}).get("fase") != "annullato"
    finally:
        _chiudi(b)


# ---------------------------------------------------------------------------
# 2. produzione (paper vero): il runner esegue l'annullo SENZA un book nuovo
# ---------------------------------------------------------------------------
def test_in_produzione_paper_l_annullo_si_conferma_senza_book_nuovi(monkeypatch):
    """La via del runner VERO in paper: il runner e' un ``Flumine`` LIVE
    (``BaseFlumine.process_order_package``, ``baseflumine.py:217-219``: il
    pacchetto va SUBITO a ``execution.handler``, non in una coda che aspetta il
    book dopo come in ``FlumineSimulation.process_order_package``,
    ``simulation.py:153-155``) e il suo client ha ``paper_trade``
    (``runner.py``: ``BetfairClient(paper_trade=True, order_stream=True)``),
    quindi ``SimulatedExecution.handler`` esegue l'annullo sul thread pool dopo
    ``cancel_latency`` sul book CORRENTE (``simulatedexecution.py:27-28,55-70``)
    e lo ``SimulatedOrderStream`` ogni ``order_streaming_timeout`` (0,25 s)
    porta gli ordini allo specchio (``simulatedorderstream.py:28-35``).
    Qui: quelle due righe di flumine LIVE al posto di quelle della simulazione
    (stesso codice, preso dalla classe), l'attesa del banco SPENTA (nessun book
    passa), e un filo che ogni 0,25 s fa lo specchio come lo stream ordini
    simulato. Il bot deve leggere l'annullo confermato entro i suoi 3 s.
    Rottura minima: fermare il filo dello stream ordini -> ``None``."""
    import types

    from flumine.baseflumine import BaseFlumine

    b, ref, ev = _banco_con_lay_appoggiata()
    ferma = threading.Event()
    try:
        b.pb.attendi_esecuzione = None               # nessun aiuto del banco
        cliente = b.quadro.clients.get_default()
        monkeypatch.setattr(cliente, "paper_trade", True)
        monkeypatch.setattr(b.quadro, "process_order_package",
                            types.MethodType(BaseFlumine.process_order_package, b.quadro))
        book_prima = b.motore.pompati, b.motore._ora_mercato

        def _stream_ordini() -> None:
            while not ferma.wait(0.25):
                b.pb._sporco = True
                b.pb.aggiorna()

        filo = threading.Thread(target=_stream_ordini, daemon=True)
        filo.start()
        t0 = time.monotonic()
        ann = X.annulla_su_betfair(None, bet_id=str(ev["bet_id"]), market_id=b.market_id,
                                   porta=MPO.VistaMike(b.client), mode="paper")
        durata = time.monotonic() - t0
        assert ann is not None and ann.ok and ann.riletto, ann
        assert ann.size_cancelled == 2.0
        assert durata < 2.0, durata
        # nessun book e' passato: l'annullo non ha avuto bisogno del mercato
        assert (b.motore.pompati, b.motore._ora_mercato) == book_prima
    finally:
        ferma.set()
        _chiudi(b)


# ---------------------------------------------------------------------------
# 3. il replay monta l'attesa; fuori dal replay la porta resta com'era
# ---------------------------------------------------------------------------
def test_il_montaggio_del_canale_aggancia_l_attesa_del_motore_del_replay():
    """``trasporto._monta_canale`` (la strada VERA del replay) aggancia alla
    porta del banco l'attesa del ``MotoreReplay`` VERO. Rottura minima: non
    agganciarla -> ``attendi_esecuzione`` None nel replay (difetto M1)."""
    from flumine import FlumineSimulation

    quadro = FlumineSimulation(client=B.cliente_simulato())
    motore = B.MotoreReplay(quadro)
    mercato = B.MercatoFlumine(SimpleNamespace(mercati={}))
    strategia = SimpleNamespace(mercato=mercato, mode="paper",
                                process_market_book=lambda market, market_book: None)
    with TRA.contesto("mike", "canale") as st:
        TRA.su_esegui(motore, strategia)
        pb = st["porta_banco"]
        assert pb.attendi_esecuzione == motore.attendi_esecuzione


def test_porta_banco_senza_motore_del_replay_non_attende():
    """Una ``PortaBanco`` fuori dal replay (test unitari del motore) non ha
    l'attesa: comportamento identico a prima."""
    from flumine import FlumineSimulation

    from Betfair.stream.backtest.porta_banco import PortaBanco

    quadro = FlumineSimulation(client=B.cliente_simulato())
    pb = PortaBanco(quadro, SimpleNamespace(), attore="mike")
    assert pb.attendi_esecuzione is None


def test_attesa_solo_annulli_non_aspetta_il_bet_delay_di_un_place_in_volo():
    """``MotoreReplay.attendi_esecuzione(mid, tipi=(CANCEL,))``: aspetta SOLO i
    pacchetti CANCEL di quel mercato; un PLACE in volo (bet delay) sullo stesso
    mercato resta in coda e si esegue quando tocca (al book suo). Rottura
    minima: ignorare ``tipi`` -> la chiamata non torna finche' il PLACE non e'
    eseguito (il bot fermo per il bet delay)."""
    from flumine.order.orderpackage import OrderPackageType

    pacchi: List[Any] = []

    class _Pacco:
        def __init__(self, tipo: Any, ritardo: float) -> None:
            self.market_id = "1.1"
            self.package_type = tipo
            self.simulated_delay = ritardo
            self.elapsed_seconds = 0.0

    eseguiti: List[Any] = []
    quadro = SimpleNamespace(handler_queue=pacchi)
    motore = B.MotoreReplay.__new__(B.MotoreReplay)
    motore.quadro = quadro
    motore.pompati = 0
    motore.senza_futuro = 0
    motore.su_book = None
    place = _Pacco(OrderPackageType.PLACE, 5.17)
    cancel = _Pacco(OrderPackageType.CANCEL, 0.17)
    pacchi.extend([place, cancel])
    libri = iter(range(3))

    def _prossimo() -> Any:
        return next(libri, None)

    def _a_flumine(_mb: Any) -> tuple:
        for p in pacchi:
            p.elapsed_seconds += 0.1
        return None, False

    def _esegui_adesso(lista: Any) -> None:
        for p in list(lista):
            eseguiti.append(p.package_type)
            pacchi.remove(p)

    motore._prossimo = _prossimo
    motore._a_flumine = _a_flumine
    motore._esegui_adesso = _esegui_adesso
    passati = motore.attendi_esecuzione("1.1", tipi=(OrderPackageType.CANCEL,))
    assert eseguiti == [OrderPackageType.CANCEL]
    assert pacchi == [place], "il PLACE in volo resta in coda"
    assert passati == 2
