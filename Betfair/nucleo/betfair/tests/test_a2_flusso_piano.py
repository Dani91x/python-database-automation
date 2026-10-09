"""W1-A2 - PARITA' del piano delle connessioni e del budget con ``frammenti_mercato.py``.

``flusso.piano_connessioni`` e ``flusso.connessioni_concesse`` sono riscritte
(regola 3 del brief comune: il pezzo sta in un file da 665 righe legato a
flumine) e qui confrontate con le funzioni di OGGI, importate:
``frammenti_mercato.pianifica`` e ``GestoreFrammenti.massimo_adesso`` (+ il
``motivo_limite`` che la UI mostra), su griglie di mercati e di connessioni.
Il budget passa anche dai listener VERI dei due mondi (``FrammentoListener`` di
oggi, ``ListenerFlusso`` nuovo) alimentati con lo stesso messaggio ``status`` di
Betfair: stesso ``connectionsAvailable`` letto, anche lo 0.
"""
from __future__ import annotations

import json
import random
import types
from typing import Any, List, Optional, Set

import pytest

from Betfair.nucleo.betfair import flusso as F
from Betfair.nucleo.betfair import profili as P
from Betfair.stream import frammenti_mercato as FR

from .test_a2_finti import SessioneFinta


def _ids(a: int, b: int) -> List[str]:
    return ["1.%06d" % i for i in range(a, b)]


def _griglia(seme: int):
    rnd = random.Random(seme)
    universo = _ids(0, 900)
    for _ in range(400):
        n_att = rnd.randint(0, 4)
        attuali: List[Set[str]] = []
        liberi = list(universo)
        rnd.shuffle(liberi)
        for _k in range(n_att):
            quanti = rnd.choice([0, 1, 5, 50, 179, 180, 200])
            attuali.append(set(liberi[:quanti]))
            liberi = liberi[quanti:]
        gia = sorted(set().union(*attuali)) if attuali else []
        voluti = set(rnd.sample(gia, k=rnd.randint(0, len(gia)))) if gia else set()
        voluti |= set(rnd.sample(universo, k=rnd.choice([0, 1, 30, 181, 400, 700])))
        per_conn = rnd.choice([1, 7, 150, 180, 200, 250])
        max_conn = rnd.choice([1, 2, 3, 4, 10])
        yield attuali, voluti, per_conn, max_conn


@pytest.mark.parametrize("seme", [1, 2, 3, 4, 5])
def test_piano_identico_a_frammenti_mercato_su_griglie(seme):
    casi = 0
    for attuali, voluti, per_conn, max_conn in _griglia(seme):
        vecchio = FR.pianifica([set(a) for a in attuali], list(voluti), per_conn, max_conn)
        nuovo = F.piano_connessioni([set(a) for a in attuali], list(voluti), per_conn, max_conn)
        assert (nuovo.bersagli, nuovo.nuovi, nuovo.fuori) == \
            (vecchio.bersagli, vecchio.nuovi, vecchio.fuori), (attuali, voluti, per_conn, max_conn)
        for blocco in nuovo.nuovi:              # connessioni nuove: mai oltre il tetto ne' 200
            assert 0 < len(blocco) <= min(max(per_conn, 1), P.LIMITE_BETFAIR_MERCATI)
        casi += 1
    assert casi == 400


def test_casi_limite_del_piano():
    for attuali, voluti in [([], []), ([set()], ["1.1"]), ([{"1.1"}], []),
                            ([{"1.1"}, {"1.2"}], ["1.2"]), ([set(_ids(0, 200))], _ids(0, 201))]:
        for per_conn, max_conn in [(180, 3), (200, 1), (0, 0), (500, 12)]:
            v = FR.pianifica([set(a) for a in attuali], voluti, per_conn, max_conn)
            n = F.piano_connessioni([set(a) for a in attuali], voluti, per_conn, max_conn)
            assert (n.bersagli, n.nuovi, n.fuori) == (v.bersagli, v.nuovi, v.fuori)


def _status(disponibili: Optional[int]) -> str:
    d = {"op": "status", "id": 1, "statusCode": "SUCCESS", "connectionClosed": False}
    if disponibili is not None:
        d["connectionsAvailable"] = disponibili
    return json.dumps(d)


class _Orologio:
    def __init__(self) -> None:
        self.t = 10_000.0

    def __call__(self) -> float:
        return self.t


@pytest.mark.parametrize("riserva", [0, 1, 2])
@pytest.mark.parametrize("max_conn", [1, 3, 4])
def test_budget_identico_a_gestore_frammenti(riserva, max_conn, monkeypatch):
    """Stessi listener alimentati con lo stesso ``status``: stesse connessioni
    concesse e stesso ``motivo_limite`` (testo mostrato in UI)."""
    orologio = _Orologio()
    for aperte in range(0, 5):
        for disp in [None, 0, 1, 2, 3, 9]:
            for pausa in [None, 10.0, 299.0, 301.0]:
                # oggi: GestoreFrammenti con frammenti finti che portano listener VERI
                vecchi = []
                for _k in range(aperte):
                    li = FR.FrammentoListener(max_latency=None)
                    li.on_data(_status(disp))
                    vecchi.append(types.SimpleNamespace(_listener=li))
                g = FR.GestoreFrammenti(per_conn=180, max_conn=max_conn, riserva=riserva,
                                        orologio=orologio)
                monkeypatch.setattr(FR.GestoreFrammenti, "frammenti",
                                    staticmethod(lambda fw, _v=vecchi: list(_v)))
                if pausa is not None:
                    g._rifiuto_mono = orologio.t - pausa
                    g.ultimo_rifiuto = "MAX_CONNECTION_LIMIT_EXCEEDED"
                atteso = (g.massimo_adesso(object()), g.motivo_limite)
                # nuovo: GestoreFlussi con connessioni (non avviate) e listener VERI
                prof = P.profilo("runner_calcio", {"RUNNER_CALCIO_STREAM_CONNS": str(max_conn),
                                                   "RUNNER_CALCIO_STREAM_RISERVA": str(riserva)})
                nuovo = F.GestoreFlussi(SessioneFinta(), prof, orologio=orologio)
                for k in range(aperte):
                    c = F._Connessione(nuovo, k + 1, {"1.%d" % k})
                    c.listener.on_data(_status(disp))
                    nuovo._connessioni.append(c)
                if pausa is not None:
                    nuovo._rifiuto_mono = orologio.t - pausa
                    nuovo.ultimo_rifiuto = "MAX_CONNECTION_LIMIT_EXCEEDED"
                assert (nuovo.massimo_adesso(), nuovo.motivo_limite) == atteso, \
                    (aperte, disp, pausa, riserva, max_conn)


def test_vince_l_ultimo_connections_available_letto():
    orologio = _Orologio()
    prof = P.profilo("runner_calcio", {})
    g = F.GestoreFlussi(SessioneFinta(), prof, orologio=orologio)
    a, b = F._Connessione(g, 1, {"1.1"}), F._Connessione(g, 2, {"1.2"})
    g._connessioni = [a, b]
    b.listener.on_data(_status(5))
    orologio.t += 1
    a.listener.on_data(_status(1))          # piu' recente: 1 <= riserva 1
    assert g._disponibili() == 1
    assert g.massimo_adesso() == 2           # le aperte, non di piu'
    orologio.t += 1
    b.listener.on_data(_status(0))           # lo 0 si tiene (bfl lo perderebbe)
    assert g._disponibili() == 0
    assert b.listener.connections_available == 5     # la libreria ha perso lo 0
