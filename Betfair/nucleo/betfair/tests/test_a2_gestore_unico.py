"""W1-A2 - decisioni 8 e 13 dell'utente (10/10/2026): UN gestore dei flussi e UNO stream
ordini per tutta l'app, mai connessioni doppie.

``GestoreFlussi`` serve piu' consumatori (bot, ladder, scanner) con il registro delle
richieste (``richiedi_mercati``/``rilascia_mercati``): si sottoscrive l'UNIONE, al massimo
200 mercati per connessione. ``FlussoOrdiniContoBetfair`` serve piu' consumatori su UNA
connessione. Tutto sulla catena VERA di betfairlightweight contro il server finto TLS
(``test_a2_finti``). Falsificazione: mutazioni G1..G7 in
``ARCHITETTURA_2026-10/ondata1/W1-A2/falsifica.py``.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Set

import pytest

from Betfair.nucleo.betfair import flusso as F
from Betfair.nucleo.betfair import flusso_ordini_conto as FOC
from Betfair.nucleo.betfair import profili as P
from Betfair.nucleo.betfair.contratto import FlussoMercato, OrdineDalConto

from .test_a2_finti import SessioneFinta, attendi, conforme, server_stream  # noqa: F401
from .test_a2_flusso import CAMBIO, _ids, _risposta_immagine
from .test_a2_flusso_ordini_conto import PT0, mercato, runner, uo

#: il profilo del gestore unico nel test: 200 mercati per connessione (il limite Betfair)
AMBIENTE_200 = {"AUTO_FOLLOW_TETTO_MERCATI": "200"}
CONSUMATORI = ("bot", "ladder", "scanner")


def _gestore(ambiente: Dict[str, str]) -> F.GestoreFlussi:
    from Betfair.stream.valuta import CambioGbpEur

    return F.GestoreFlussi(SessioneFinta(), P.profilo("runner_calcio", ambiente),
                           cambio=CambioGbpEur(fisso=CAMBIO))


class _Raccolta:
    """Un consumatore: i market_id dei book ricevuti (thread di consegna)."""

    def __init__(self) -> None:
        self.mercati: Set[str] = set()
        self._lock = threading.Lock()

    def __call__(self, libro: Any) -> None:
        with self._lock:
            self.mercati.add(str(libro.market_id))

    def visti(self) -> Set[str]:
        with self._lock:
            return set(self.mercati)


def _ultime_sottoscrizioni(srv: Any) -> Dict[int, List[str]]:
    """Connessione del server -> i mercati della sua ULTIMA marketSubscription."""
    out: Dict[int, List[str]] = {}
    for n, m in srv.sottoscrizioni:
        if m.get("op") == "marketSubscription":
            out[n] = list(m["marketFilter"]["marketIds"])
    return out


def test_conforme_al_contratto_anche_con_la_richiesta():
    assert conforme(F.GestoreFlussi, FlussoMercato) == []


def test_tre_consumatori_sugli_stessi_300_mercati_due_connessioni_200_e_100_non_sei(server_stream):
    srv = server_stream(_risposta_immagine)
    g = _gestore(AMBIENTE_200)
    assert g.per_conn == 200
    raccolte = {chi: _Raccolta() for chi in CONSUMATORI}
    trecento = _ids(0, 300)
    try:
        for chi in CONSUMATORI:
            g.aggiungi_consumatore(raccolte[chi], richiesta=chi)
            assert g.richiedi_mercati(chi, trecento) == set()
        assert attendi(lambda: all(r.visti() == set(trecento) for r in raccolte.values()))
        assert srv.connessioni == 2                                  # 200 + 100, non 6
        ultime = _ultime_sottoscrizioni(srv)
        assert sorted(len(v) for v in ultime.values()) == [100, 200]
        assert sorted(x for v in ultime.values() for x in v) == trecento   # nessun doppione
        # il 2o e il 3o consumatore non mandano nulla a Betfair: l'unione non e' cambiata
        assert len(srv.sottoscrizioni_di("marketSubscription")) == 2
        st = g.stato()
        assert st["connessioni_di_mercato"] == 2
        assert (st["mercati_richiesti_somma"], st["mercati_unione"]) == (900, 300)
        assert st["richieste"] == {"bot": 300, "ladder": 300, "scanner": 300}
    finally:
        g.ferma()


def test_oggi_un_gestore_per_consumatore_apre_sei_connessioni(server_stream):
    """Il confronto: il modello di oggi (ogni processo il suo stream) sugli stessi 300
    mercati apre 3 x 2 = 6 connessioni (le 10 per app key finiscono presto)."""
    srv = server_stream(_risposta_immagine)
    gestori = [_gestore(AMBIENTE_200) for _ in CONSUMATORI]
    try:
        for g in gestori:
            assert g.imposta_mercati(_ids(0, 300)) == set()
        assert attendi(lambda: srv.connessioni == 6)
    finally:
        for g in gestori:
            g.ferma()


def test_richieste_diverse_unione_filtro_per_consumatore_e_rilascio(server_stream):
    srv = server_stream(_risposta_immagine)
    g = _gestore(AMBIENTE_200)
    voluti = {"bot": set(_ids(0, 150)), "ladder": set(_ids(100, 250)), "scanner": set(_ids(200, 300))}
    raccolte = {chi: _Raccolta() for chi in CONSUMATORI}
    tutti = _Raccolta()
    try:
        g.aggiungi_consumatore(tutti)
        for chi in CONSUMATORI:
            g.aggiungi_consumatore(raccolte[chi], richiesta=chi)
            assert g.richiedi_mercati(chi, voluti[chi]) == set()
        assert attendi(lambda: tutti.visti() == set(_ids(0, 300)))
        assert srv.connessioni == 2
        # ogni consumatore riceve SOLO i mercati della sua richiesta
        assert attendi(lambda: all(raccolte[c].visti() == voluti[c] for c in CONSUMATORI))
        # la richiesta diretta (imposta_mercati) e' un consumatore in piu': NON toglie i loro
        assert g.imposta_mercati(_ids(290, 310)) == set()
        assert g.stato()["mercati_unione"] == 310
        assert attendi(lambda: g.stato_flusso("1.000309") == "vivo")
        assert g.stato_flusso("1.000005") == "vivo"
        # il ladder rilascia: escono solo i mercati che nessun altro chiede (150..199)
        g.rilascia_mercati("ladder")
        g.rilascia_mercati(F.RICHIESTA_DIRETTA)
        assert set(g.richieste()) == {"bot", "scanner"}
        assert g.stato_flusso("1.000170") == "assente"
        for mid in ("1.000120", "1.000220", "1.000000", "1.000299"):
            assert g.stato_flusso(mid) != "assente", mid
        unione = voluti["bot"] | voluti["scanner"]
        # a Betfair e' arrivata la sottoscrizione SOSTITUTIVA con l'insieme senza il ladder
        assert attendi(lambda: set(x for v in _ultime_sottoscrizioni(srv).values() for x in v) == unione)
        piani = set().union(*(c.piano for c in g._vive()))
        assert piani == unione
        assert srv.connessioni == 2                                  # nessuna connessione in piu'
        # tutti rilasciano: nessuna connessione resta aperta (mai una sottoscrizione vuota)
        g.rilascia_mercati("bot")
        g.rilascia_mercati("scanner")
        assert g._vive() == [] and g.stato()["connessioni_di_mercato"] == 0
        assert g.stato_flusso("1.000005") == "assente" and g.book("1.000005") is None
        assert all(len(m["marketFilter"]["marketIds"]) > 0
                   for m in srv.sottoscrizioni_di("marketSubscription"))
    finally:
        g.ferma()


def test_capacita_piena_i_fuori_sono_del_consumatore_che_non_entra(server_stream):
    srv = server_stream(_risposta_immagine)
    g = _gestore({**AMBIENTE_200, "RUNNER_CALCIO_STREAM_CONNS": "1"})
    try:
        assert g.richiedi_mercati("bot", _ids(0, 150)) == set()
        fuori = g.richiedi_mercati("scanner", _ids(150, 250))
        assert fuori == set(_ids(200, 250))                          # 50 non entrano
        assert g.richiedi_mercati("ladder", _ids(0, 10)) == set()    # gia' coperti: nessun posto in piu'
        assert attendi(lambda: g.stato()["conti"]["book"] >= 200)
        assert srv.connessioni == 1
    finally:
        g.ferma()


def test_richieste_concorrenti_l_ultimo_piano_vede_tutte_le_richieste(server_stream):
    srv = server_stream(_risposta_immagine)
    g = _gestore(AMBIENTE_200)
    finali = {"bot": set(_ids(0, 120)), "ladder": set(_ids(60, 180)), "scanner": set(_ids(150, 330))}
    barriera = threading.Barrier(3)

    def _consumatore(chi: str) -> None:
        barriera.wait()
        for k in range(6):                       # richieste che cambiano, poi quella finale
            g.richiedi_mercati(chi, _ids(400 + 10 * k, 410 + 10 * k))
        g.richiedi_mercati(chi, finali[chi])

    try:
        fili = [threading.Thread(target=_consumatore, args=(c,)) for c in CONSUMATORI]
        for f in fili:
            f.start()
        for f in fili:
            f.join(30)
        unione = set().union(*finali.values())
        assert set().union(*(c.piano for c in g._vive())) == unione
        assert attendi(lambda: all(g.stato_flusso(m) == "vivo" for m in unione), 20)
        assert g.stato_flusso("1.000405") == "assente"
        # i mercati restano sulla connessione dove sono (mai spostati): 2 o 3 connessioni,
        # ognuna entro 200, nessuna oltre il tetto del profilo
        assert 2 <= len(g._vive()) <= 3 and srv.connessioni <= 3
        assert all(0 < len(c.piano) <= 200 for c in g._vive())
    finally:
        g.ferma()


def test_filtro_fisso_e_richiesta_insieme_rifiutati():
    g = _gestore(AMBIENTE_200)
    with pytest.raises(ValueError):
        g.aggiungi_consumatore(lambda b: None, mercati={"1.1"}, richiesta="bot")
    with pytest.raises(ValueError):
        g.richiedi_mercati("", _ids(0, 3))


# ---------------------------------------------------------------------------
# UNO stream ordini per tutta l'app (decisione 13)
# ---------------------------------------------------------------------------
def test_tre_consumatori_degli_ordini_una_sola_connessione(server_stream):
    def risposta(n: int, m: Dict[str, Any], k: int) -> List[Any]:
        return [{"op": "ocm", "initialClk": "I", "clk": "C", "pt": PT0, "ct": "SUB_IMAGE",
                 "oc": [mercato("1.000001", [runner(19, [uo("1", rfs="mike_live")])], full=True),
                        mercato("1.000002", [runner(22, [uo("2")])], full=True)]}]
    srv = server_stream(risposta)
    f = FOC.FlussoOrdiniContoBetfair(SessioneFinta())
    ladder: List[str] = []
    libro: List[str] = []
    salute: List[str] = []
    f.aggiungi_consumatore(lambda o: ladder.append(o.bet_id), mercati={"1.000002"})
    f.aggiungi_consumatore(lambda o: libro.append(o.bet_id))
    f.avvia()
    f.avvia()                                     # idempotente: nessuna seconda connessione
    try:
        assert attendi(lambda: sorted(libro) == ["1", "2"])
        # un consumatore che arriva DOPO: legge lo stato da ``ordini()``, riceve i cambi dopo
        f.aggiungi_consumatore(lambda o: salute.append(o.bet_id))
        assert sorted(o.bet_id for o in f.ordini()) == ["1", "2"]
        assert all(isinstance(o, OrdineDalConto) for o in f.ordini())
        srv.manda(1, {"op": "ocm", "clk": "C2", "pt": PT0 + 10,
                      "oc": [mercato("1.000002", [runner(22, [uo("2", sm=10.0, sr=0.0, status="EC")])])]})
        assert attendi(lambda: salute == ["2"])
        assert ladder == ["2", "2"]
        assert srv.connessioni == 1
        assert len(srv.sottoscrizioni_di("orderSubscription")) == 1
        assert f.stato()["consumatori"] == 3
    finally:
        f.ferma()
