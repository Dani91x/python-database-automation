"""W1-B - correzioni dopo la TERZA revisione (di ``e330fdb5``): la coda delle consegne.

1. disiscrivi durante una consegna: nessuna callback dopo che ``disiscrivi()`` e' tornata;
2. coda limitata: STATI coalescenti per partita, EVENTI mai scartati, avviso oltre il tetto;
3. ``ferma`` non scarta la coda; la coda si svuota anche a un giro senza partite;
4. mutanti M1 (flag non rilasciato su ``BaseException``) e M3 (LIFO).
Le prove del revisore (``scratchpad/rev_w1b3/test_coda_rev3.py``, ``test_c_bis.py``)
sono qui con nomi miei, adeguate alla coalescenza degli stati (punto 2).
"""
from __future__ import annotations

import logging
import threading
import time
import tracemalloc
from typing import Any, Dict, List, Mapping, Sequence

import pytest

from Betfair.nucleo.stato_partita import servizio as S
from Betfair.nucleo.stato_partita.tests.test_b_servizio import FonteInMemoria, T0, _busta_riga


def _srv() -> "tuple[S.ServizioStatoPartita, FonteInMemoria]":
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0)
    srv.segui(["7"])
    return srv, fonte


def _giro(srv: S.ServizioStatoPartita, fonte: FonteInMemoria, minuto: int, gol: tuple = (0, 0)) -> Any:
    fonte.buste["7"] = _busta_riga("7", minuto=minuto, gol=gol)
    return srv.aggiorna()


class _FonteContatore:
    """Ogni lettura un minuto nuovo; gol che salgono ogni ``ogni_gol`` letture."""

    nome = "contatore"

    def __init__(self, ogni_gol: int = 0) -> None:
        self.n = 0
        self.ogni_gol = ogni_gol

    def gol(self) -> int:
        return self.n // self.ogni_gol if self.ogni_gol else 0

    def leggi(self, ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        self.n += 1
        return {"7": _busta_riga("7", minuto=self.n, gol=(self.gol(), 0))}


def _blocca(srv: S.ServizioStatoPartita) -> "tuple[threading.Event, threading.Event, threading.Thread]":
    """Un iscritto che si ferma nella PRIMA consegna finche' il test non lo libera;
    il primo giro gira in un thread a parte (il consegnatore bloccato)."""
    dentro, via = threading.Event(), threading.Event()
    primo = [True]

    def bloccante(st: Any) -> None:
        if primo[0]:
            primo[0] = False
            dentro.set()
            via.wait(30)

    srv.iscrivi(bloccante)
    t = threading.Thread(target=srv.aggiorna, daemon=True)
    t.start()
    assert dentro.wait(5)
    return dentro, via, t


# ---------------------------------------------------------------------------
# 1. disiscrivi
# ---------------------------------------------------------------------------
def test_disiscritto_con_una_voce_in_coda_non_la_riceve() -> None:
    """La prova del revisore: b si disiscrive mentre il suo 2' e' in coda."""
    srv, fonte = _srv()
    dentro, via = threading.Event(), threading.Event()
    visti_b: List[int] = []
    srv.iscrivi(lambda st: (dentro.set(), via.wait(10)) if st.minuto == 1 else None)
    via_b = srv.iscrivi(lambda st: visti_b.append(st.minuto))
    t = threading.Thread(target=lambda: _giro(srv, fonte, 1), daemon=True)
    t.start()
    assert dentro.wait(5)
    _giro(srv, fonte, 2)                     # in coda con b fra i destinatari
    via_b()                                  # disiscrivi() torna PRIMA della consegna del 2'
    via.set()
    t.join(5)
    assert visti_b == []                     # nemmeno l'1': b viene dopo a, che era fermo


def test_nuovo_iscritto_non_riceve_le_voci_calcolate_prima() -> None:
    srv, fonte = _srv()
    dentro, via = threading.Event(), threading.Event()
    srv.iscrivi(lambda st: (dentro.set(), via.wait(10)) if st.minuto == 1 else None)
    t = threading.Thread(target=lambda: _giro(srv, fonte, 1), daemon=True)
    t.start()
    assert dentro.wait(5)
    _giro(srv, fonte, 2)                     # calcolato PRIMA che c si iscriva
    visti_c: List[int] = []
    srv.iscrivi(lambda st: visti_c.append(st.minuto))
    _giro(srv, fonte, 3)                     # calcolato dopo: coalesce il 2' (c riceve il 3')
    via.set()
    t.join(5)
    assert visti_c == [3]


def test_nuovo_iscritto_agli_eventi_non_riceve_il_gol_di_prima() -> None:
    """Un evento (mai coalescente) calcolato PRIMA dell'iscrizione non arriva al
    nuovo iscritto; arriva a chi era iscritto al calcolo."""
    srv, fonte = _srv()
    dentro, via = threading.Event(), threading.Event()
    srv.iscrivi(lambda st: (dentro.set(), via.wait(10)) if st.minuto == 1 else None)
    vecchio: List[str] = []
    srv.iscrivi_eventi(lambda e: vecchio.append(type(e).__name__))
    t = threading.Thread(target=lambda: _giro(srv, fonte, 1), daemon=True)
    t.start()
    assert dentro.wait(5)
    _giro(srv, fonte, 2, gol=(1, 0))         # GolSegnato calcolato prima di c
    nuovo: List[str] = []
    srv.iscrivi_eventi(lambda e: nuovo.append(type(e).__name__))
    _giro(srv, fonte, 3, gol=(1, 0))
    via.set()
    t.join(5)
    assert "GolSegnato" in vecchio and "GolSegnato" not in nuovo
    assert nuovo == ["StatoCambiato"]


# ---------------------------------------------------------------------------
# 2. coda limitata
# ---------------------------------------------------------------------------
def test_callback_bloccata_mille_giri_memoria_limitata_eventi_tutti() -> None:
    fonte = _FonteContatore(ogni_gol=100)
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0)
    srv.segui(["7"])
    eventi: List[Any] = []
    srv.iscrivi_eventi(eventi.append)
    _, via, t = _blocca(srv)
    tracemalloc.start()
    prima = tracemalloc.take_snapshot()
    for _ in range(1000):
        srv.aggiorna()
    dopo = tracemalloc.take_snapshot()
    tracemalloc.stop()
    crescita = sum(x.size_diff for x in dopo.compare_to(prima, "filename"))
    stato = srv.stato_servizio()
    # in coda: 1 stato + 1 StatoCambiato coalescenti + i 10 gol (mai scartati)
    assert stato["coda"] <= 12 and stato["coda_max"] <= 13
    assert stato["stati_coalescati"] >= 1900
    assert crescita < 200_000, crescita                      # 1,8 KB/giro prima: ~1,8 MB
    via.set()
    t.join(10)
    gol = [e for e in eventi if isinstance(e, S.GolSegnato)]
    assert [e.dopo for e in gol] == [(i, 0) for i in range(1, 11)]   # tutti, in ordine
    assert srv.stato("7").minuto == fonte.n == 1001 and srv.stato_servizio()["coda"] == 0
    cambi = [e for e in eventi if isinstance(e, S.StatoCambiato)]
    # UN StatoCambiato coalescente: dal primo "prima" non consegnato (nessuno: era il
    # primo stato) all'ultimo "dopo"
    assert len(cambi) == 1 and cambi[0].prima is None and cambi[0].dopo.minuto == 1001


def test_oltre_il_tetto_avviso_col_nome_della_callback(caplog: pytest.LogCaptureFixture) -> None:
    fonte = _FonteContatore(ogni_gol=1)                      # un gol a ogni giro: eventi veri
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0)
    srv.segui(["7"])
    srv.tetto_coda = 5
    srv.iscrivi_eventi(lambda e: None)
    _, via, t = _blocca(srv)
    with caplog.at_level(logging.WARNING):
        for _ in range(20):
            srv.aggiorna()
    stato = srv.stato_servizio()
    assert stato["coda_oltre_tetto"] >= 10 and stato["coda"] > 5
    assert "bloccante" in (stato["callback_in_corso"] or "")
    assert caplog.text.count("oltre il tetto") == 1 and "bloccante" in caplog.text
    via.set()
    t.join(10)
    assert srv.stato_servizio()["coda"] == 0


def test_due_thread_con_callback_lenta_tornano_subito() -> None:
    """Prova del revisore (a): mentre il consegnatore e' fermo in una callback, altri
    due ``aggiorna`` tornano subito; gli stati in coda si coalescono (1' poi 3')."""
    srv, fonte = _srv()
    visti: List[int] = []
    dentro, via = threading.Event(), threading.Event()

    def lenta(st: Any) -> None:
        visti.append(st.minuto)
        if st.minuto == 1:
            dentro.set()
            via.wait(10)

    srv.iscrivi(lenta)
    t1 = threading.Thread(target=lambda: _giro(srv, fonte, 1), daemon=True)
    t1.start()
    assert dentro.wait(5)
    altri = [threading.Thread(target=lambda m=m: _giro(srv, fonte, m), daemon=True) for m in (2, 3)]
    for t in altri:
        t.start()
        t.join(3)
    assert all(not t.is_alive() for t in altri)
    assert visti == [1] and srv.stato_servizio()["coda"] == 1
    via.set()
    t1.join(5)
    assert visti == [1, 3] and srv.stato("7").minuto == 3


def test_ordine_di_calcolo_con_otto_thread() -> None:
    """Prova del revisore (stress): 8 thread x 40 giri. Gli stati consegnati sono
    una sotto-sequenza CRESCENTE di quelli calcolati e finiscono con l'ultimo; i
    gol arrivano tutti, in ordine (M3: una coda LIFO li rovescia)."""
    fonte = _FonteContatore(ogni_gol=7)
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0)
    srv.segui(["7"])
    visti: List[int] = []
    gol: List[tuple] = []
    srv.iscrivi(lambda st: (time.sleep(0.0005), visti.append(st.minuto)))
    srv.iscrivi_eventi(lambda e: gol.append(e.dopo) if isinstance(e, S.GolSegnato) else None)

    def lavoro() -> None:
        for _ in range(40):
            srv.aggiorna()

    ts = [threading.Thread(target=lavoro, daemon=True) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(60)
    assert all(not t.is_alive() for t in ts)
    assert srv.stato_servizio()["coda"] == 0 and srv._consegnatore is None
    assert visti == sorted(set(visti)) and visti[-1] == fonte.n == 320
    assert gol == [(i, 0) for i in range(1, 320 // 7 + 1)]


# ---------------------------------------------------------------------------
# 3. ferma non scarta la coda; giro senza partite svuota la coda
# ---------------------------------------------------------------------------
def test_ferma_non_scarta_la_coda() -> None:
    """Prova del revisore (c): il thread del giro e' il consegnatore, bloccato in
    una callback; altri giri accodano; ``ferma`` non scarta: alla ripresa il
    thread consegna la coda e poi esce."""
    fonte = _FonteContatore()
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0, nome="b-ferma-coda")
    srv.segui(["7"])
    visti: List[int] = []
    dentro, via = threading.Event(), threading.Event()

    def lenta(st: Any) -> None:
        visti.append(st.minuto)
        if st.minuto == 1:
            dentro.set()
            via.wait(10)

    srv.iscrivi(lenta)
    srv.avvia(0.05)
    filo = srv._giro_vivo.thread
    assert dentro.wait(5)
    srv.aggiorna()
    srv.aggiorna()
    assert srv.stato_servizio()["coda"] == 1                      # 2' e 3' coalescenti
    esito: List[bool] = []
    t = threading.Thread(target=lambda: esito.append(srv.ferma(0.3)), daemon=True)
    t.start()
    t.join(3)
    assert esito == [False]
    via.set()
    filo.join(5)
    assert not filo.is_alive()
    assert visti == [1, 3] and srv.stato_servizio()["coda"] == 0


def test_base_exception_rilascia_il_consegnatore() -> None:
    """Prova del revisore (b), M1: una ``BaseException`` in una callback esce da
    ``aggiorna`` ma libera il consegnatore: il giro dopo consegna di nuovo."""
    srv, fonte = _srv()
    visti: List[int] = []

    def interrompe(st: Any) -> None:
        if st.minuto == 1:
            raise KeyboardInterrupt()
        visti.append(st.minuto)

    srv.iscrivi(interrompe)
    with pytest.raises(KeyboardInterrupt):
        _giro(srv, fonte, 1)
    assert srv._consegnatore is None and srv.stato_servizio()["callback_in_corso"] is None
    _giro(srv, fonte, 2)
    assert visti == [2]


def test_coda_rimasta_si_svuota_anche_senza_partite() -> None:
    """Dopo una ``BaseException`` restano voci in coda (gli eventi del giro). Un
    ``aggiorna`` con ``segui`` vuoto (ritorno anticipato) le consegna lo stesso."""
    srv, fonte = _srv()
    eventi: List[str] = []
    srv.iscrivi(lambda st: (_ for _ in ()).throw(KeyboardInterrupt()))
    srv.iscrivi_eventi(lambda e: eventi.append(type(e).__name__))
    with pytest.raises(KeyboardInterrupt):
        _giro(srv, fonte, 1)
    assert eventi == [] and srv.stato_servizio()["coda"] == 1
    srv.segui([])
    srv.aggiorna()
    assert eventi == ["StatoCambiato"] and srv.stato_servizio()["coda"] == 0


def test_coda_rimasta_si_svuota_anche_con_la_fonte_giu() -> None:
    srv, fonte = _srv()
    eventi: List[str] = []
    srv.iscrivi(lambda st: (_ for _ in ()).throw(KeyboardInterrupt()))
    srv.iscrivi_eventi(lambda e: eventi.append(type(e).__name__))
    with pytest.raises(KeyboardInterrupt):
        _giro(srv, fonte, 1)
    fonte.guasto = RuntimeError("fonte giu'")
    srv.aggiorna()
    assert eventi == ["StatoCambiato"] and srv.errori_fonte == 1


def test_stato_servizio_contatori() -> None:
    srv, fonte = _srv()
    srv.iscrivi(lambda st: None)
    _giro(srv, fonte, 1)
    stato = srv.stato_servizio()
    assert stato["coda"] == 0 and stato["giri"] == 1 and stato["seguiti"] == 1
    assert stato["tetto_coda"] == S.TETTO_CODA and stato["callback_in_corso"] is None
