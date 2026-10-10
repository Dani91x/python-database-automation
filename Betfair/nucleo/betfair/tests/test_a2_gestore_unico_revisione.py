"""W1-A2 - gestore unico: le prove della revisione indipendente di 2d38504f (riscritte qui).

Casi che ``test_a2_gestore_unico`` non copre:
* una risottoscrizione di un piano VECCHIO che arriva alla connessione DOPO quella
  del piano nuovo non vince (deterministico: il thread A e' fermato dentro
  ``_Connessione.risottoscrivi`` finche' B non ha finito). Rossa con la mutazione R6
  (``_generazione`` non incrementata in ``_applica_richieste``);
* i mercati rimasti fuori per capacita' entrano DA SOLI quando un altro consumatore
  rilascia (restano nel registro);
* capacita' piena su 9 connessioni (1.800 mercati): i fuori sono dichiarati;
* consumatori calcio e tennis legati alla loro richiesta: nessuno vede i book dell'altro,
  la richiesta diretta vuota non riceve nulla;
* stress: 5 thread x 50 cambi di richiesta (anche rilasci) partiti insieme: registro,
  piani, nessun doppione fra connessioni, ultime sottoscrizioni viste dal server.

Libreria vera contro il server finto TLS (``test_a2_finti``).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import random
import threading
from typing import Any, Dict, List, Set

import pytest

from Betfair.nucleo.betfair import flusso as F

from .test_a2_finti import attendi, server_stream  # noqa: F401
from .test_a2_flusso import _ids, _risposta_immagine
from .test_a2_gestore_unico import AMBIENTE_200, _gestore, _Raccolta, _ultime_sottoscrizioni


def test_risottoscrizione_di_un_piano_vecchio_arrivata_dopo_non_vince(server_stream):
    srv = server_stream(_risposta_immagine)
    g = _gestore(AMBIENTE_200)
    reale = F._Connessione.risottoscrivi
    sblocca_a = threading.Event()
    a_ferma = threading.Event()

    def lenta(self: Any, mercati: Set[str], generazione: Any = None) -> bool:
        if threading.current_thread().name == "piano-A":
            a_ferma.set()
            assert sblocca_a.wait(20)
        return reale(self, mercati, generazione)

    try:
        assert g.richiedi_mercati("base", _ids(0, 10)) == set()
        assert attendi(lambda: g.stato_flusso("1.000005") == "vivo")
        F._Connessione.risottoscrivi = lenta
        a = threading.Thread(target=lambda: g.richiedi_mercati("base", _ids(0, 20)), name="piano-A")
        a.start()
        assert a_ferma.wait(10)                      # A ha pianificato ed e' fermo prima della rete
        b = threading.Thread(target=lambda: g.richiedi_mercati("base", _ids(0, 30)), name="piano-B")
        b.start()
        b.join(20)
        assert not b.is_alive()
        sblocca_a.set()
        a.join(20)
        assert not a.is_alive()
        F._Connessione.risottoscrivi = reale
        assert set().union(*(c.piano for c in g._vive())) == set(_ids(0, 30))
        assert set().union(*(c.mercati for c in g._vive())) == set(_ids(0, 30))
        # l'ultima sottoscrizione arrivata a Betfair e' quella del piano nuovo (A non ha mandato)
        assert attendi(lambda: set(_ultime_sottoscrizioni(srv).get(1, [])) == set(_ids(0, 30)))
        assert [len(m["marketFilter"]["marketIds"]) for m in srv.sottoscrizioni_di("marketSubscription")] == [10, 30]
    finally:
        F._Connessione.risottoscrivi = reale
        sblocca_a.set()
        g.ferma()


def test_i_fuori_entrano_da_soli_quando_un_altro_rilascia(server_stream):
    server_stream(_risposta_immagine)
    g = _gestore({**AMBIENTE_200, "RUNNER_CALCIO_STREAM_CONNS": "1"})
    try:
        assert g.richiedi_mercati("a", _ids(0, 200)) == set()
        assert g.richiedi_mercati("b", _ids(200, 230)) == set(_ids(200, 230))
        assert g.stato_flusso("1.000210") == "assente"
        g.rilascia_mercati("a")                      # b non richiama: e' gia' nel registro
        assert set().union(*(c.piano for c in g._vive())) == set(_ids(200, 230))
        assert attendi(lambda: g.stato_flusso("1.000210") == "vivo")
    finally:
        g.ferma()


def test_capacita_piena_su_nove_connessioni_dichiara_i_fuori(server_stream):
    server_stream(_risposta_immagine)
    g = _gestore({**AMBIENTE_200, "RUNNER_CALCIO_STREAM_CONNS": "9"})
    try:
        fuori_a = g.richiedi_mercati("a", _ids(0, 1850))
        assert fuori_a == set(_ids(1800, 1850))
        fuori_b = g.richiedi_mercati("b", _ids(1790, 1910))        # 10 gia' coperti, 110 nuovi
        assert fuori_b == set(_ids(1800, 1910))
        assert g.stato()["mercati_unione"] == 1910
        piani = [c.piano for c in g._vive()]
        assert len(piani) == 9 and sum(len(p) for p in piani) == 1800
    finally:
        g.ferma()


def test_consumatori_calcio_e_tennis_non_si_vedono(server_stream):
    server_stream(_risposta_immagine)
    g = _gestore(AMBIENTE_200)
    calcio, tennis, diretto, tutti = _Raccolta(), _Raccolta(), _Raccolta(), _Raccolta()
    try:
        g.aggiungi_consumatore(calcio, richiesta="calcio")
        g.aggiungi_consumatore(tennis, richiesta="tennis")
        g.aggiungi_consumatore(diretto, richiesta=F.RICHIESTA_DIRETTA)
        g.aggiungi_consumatore(tutti)
        g.richiedi_mercati("calcio", _ids(0, 20))
        g.richiedi_mercati("tennis", _ids(100, 120))
        assert attendi(lambda: calcio.visti() == set(_ids(0, 20)) and tennis.visti() == set(_ids(100, 120)))
        # il consumatore senza filtro ha visto tutti e 40: la consegna di quei book e' finita
        assert attendi(lambda: tutti.visti() == set(_ids(0, 20)) | set(_ids(100, 120)))
        assert calcio.visti() == set(_ids(0, 20)) and tennis.visti() == set(_ids(100, 120))
        assert diretto.visti() == set()
        g.rilascia_mercati("tennis")
        g.richiedi_mercati("calcio", _ids(0, 30))
        assert attendi(lambda: calcio.visti() == set(_ids(0, 30)))
        assert attendi(lambda: set(_ids(20, 30)) <= tutti.visti())
        assert not (calcio.visti() & set(_ids(100, 120)))
        assert tennis.visti() == set(_ids(100, 120))
    finally:
        g.ferma()


@pytest.mark.parametrize("giro", range(2))
def test_stress_cinque_thread_per_cinquanta_cambi(server_stream, giro):
    srv = server_stream(_risposta_immagine)
    g = _gestore(AMBIENTE_200)
    n = 5
    finale: Dict[str, Set[str]] = {}
    errori: List[str] = []
    barriera = threading.Barrier(n)

    def lavora(i: int) -> None:
        rnd = random.Random(1000 + i + 100 * giro)
        chi = "c%d" % i
        try:
            barriera.wait()
            for _ in range(50):
                a = rnd.randrange(0, 400)
                if rnd.random() < 0.3:
                    g.rilascia_mercati(chi)
                    finale[chi] = set()
                else:
                    ins = set(_ids(a, a + rnd.randrange(1, 60)))
                    g.richiedi_mercati(chi, ins)
                    finale[chi] = ins
            if i == 4:                                 # l'ultimo rilascia, gli altri chiedono
                g.rilascia_mercati(chi)
                finale[chi] = set()
            else:
                ins = set(_ids(i * 70, i * 70 + 90))
                g.richiedi_mercati(chi, ins)
                finale[chi] = ins
        except Exception as e:  # noqa: BLE001 - registrato e asserito sotto
            errori.append(repr(e))

    try:
        fili = [threading.Thread(target=lavora, args=(i,)) for i in range(n)]
        for f in fili:
            f.start()
        for f in fili:
            f.join(60)
        assert not [f for f in fili if f.is_alive()] and not errori, errori
        unione = set().union(*finale.values())
        assert {c: set(m) for c, m in g.richieste().items()} == {c: m for c, m in finale.items() if m}
        piani = [set(c.piano) for c in g._vive()]
        assert set().union(*piani) == unione
        assert sum(len(p) for p in piani) == len(unione), "doppioni fra connessioni"
        assert all(len(p) <= 200 for p in piani)
        assert attendi(lambda: all(p in [set(v) for v in _ultime_sottoscrizioni(srv).values()]
                                   for p in piani), 20)
    finally:
        g.ferma()
