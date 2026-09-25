"""UNA risottoscrizione a caldo per calcio e tennis (25/09).

Prima: ``auto_follow.SottoscrittoreStream.applica`` (calcio) e
``tennis_live.iscrizione_a_caldo.sottoscrivi`` (tennis) erano due copie dello
stesso meccanismo. Ora entrambi passano da ``sottoscrizione_a_caldo.sottoscrivi``.
Qui si prova che:

* i due runner chiamano la STESSA funzione (identita' dei nomi del tennis,
  spia sul modulo condiviso per il calcio);
* a parita' di stato, i due producono lo STESSO ``marketSubscription`` sulla
  connessione (``BetfairStream`` di betfairlightweight VERO, socket finto che
  registra), lo stesso ``stream_id`` e lo stesso filtro canonico su stream e
  strategie;
* le regole sono le stesse (mai vuoto, mai oltre 200, stream giu' = NonPronto,
  errore d'invio = id vecchio rimesso).
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from betfairlightweight.streaming.betfairstream import BetfairStream
from flumine import BaseStrategy
from flumine.streams.marketstream import MarketStream

from Betfair.stream import auto_follow as AF
from Betfair.stream import sottoscrizione_a_caldo as SC
from Betfair.stream.tennis_live import iscrizione_a_caldo as IAC


class _Socket:
    def __init__(self) -> None:
        self.inviati: List[Dict[str, Any]] = []

    def sendall(self, dati: bytes) -> None:
        self.inviati.append(json.loads(dati.decode("utf-8").strip()))


def _stream(nome: str):
    filtro0 = {"marketIds": ["1.1"]}
    dati = {"fields": ["EX_BEST_OFFERS", "EX_MARKET_DEF"], "ladderLevels": 3}
    st = MarketStream(flumine=None, stream_id=10000, market_filter=filtro0,
                      market_data_filter=dati, streaming_timeout=None, conflate_ms=None)
    bs = BetfairStream(10000, st._listener, "k", "t", 1.0, 1024, None)
    st._stream = bs
    bs._running = True
    bs._socket = _Socket()
    st.stream_id = bs.subscribe_to_markets(market_filter=filtro0, market_data_filter=dati)
    strat = BaseStrategy(market_filter=filtro0, name=nome)
    strat.streams.append(st)
    fw = SimpleNamespace(streams=[st], strategies=[strat])
    return fw, st, bs, strat


def test_i_due_runner_usano_la_stessa_funzione(monkeypatch):
    # tennis: i nomi di iscrizione_a_caldo SONO quelli del modulo condiviso
    assert IAC.sottoscrivi is SC.sottoscrivi
    assert IAC.stream_di_mercato is SC.stream_di_mercato
    assert IAC.filtro_mercati is SC.filtro_mercati
    assert IAC.mercati_dello_stream is SC.mercati_dello_stream
    assert IAC.NonPronto is SC.NonPronto is AF.NonPronto
    assert IAC.LIMITE_BETFAIR_MERCATI == AF.LIMITE_BETFAIR_MERCATI == SC.LIMITE_BETFAIR_MERCATI
    # calcio: SottoscrittoreStream.applica passa dal modulo condiviso
    chiamate = []
    monkeypatch.setattr(SC, "sottoscrivi",
                        lambda fw, st, ids: chiamate.append((fw, st, list(ids))) or 42)
    fw, st, _bs, _s = _stream("unica_spia")
    assert AF.SottoscrittoreStream().applica(fw, ["1.3", "1.2"]) == 42
    assert chiamate == [(fw, st, ["1.3", "1.2"])]


def test_parita_del_marketsubscription_calcio_e_tennis():
    fw_c, st_c, bs_c, strat_c = _stream("unica_calcio")
    fw_t, st_t, bs_t, strat_t = _stream("unica_tennis")
    nuovo_c = AF.SottoscrittoreStream().applica(fw_c, ["1.3", "1.2"])
    nuovo_t = IAC.sottoscrivi(fw_t, IAC.stream_di_mercato(fw_t), ["1.3", "1.2"])
    msg_c, msg_t = bs_c._socket.inviati[-1], bs_t._socket.inviati[-1]
    assert msg_c == msg_t
    assert msg_c["op"] == "marketSubscription" and msg_c["id"] == nuovo_c == nuovo_t == 10002
    assert msg_c["marketFilter"] == {"marketIds": ["1.2", "1.3"]}
    assert msg_c["initialClk"] is None                     # immagine piena
    for st, strat in ((st_c, strat_c), (st_t, strat_t)):
        assert st.stream_id == 10002 and strat.stream_ids == [10002]
        assert st.market_filter == strat.market_filter == {"marketIds": ["1.2", "1.3"]}
        assert st._listener.stream_unique_id == 10002
    assert IAC.mercati_dello_stream(st_t) == ["1.2", "1.3"]


@pytest.mark.parametrize("chi", ["calcio", "tennis"])
def test_stesse_regole_per_i_due_runner(chi):
    fw, st, bs, _s = _stream("unica_regole_" + chi)

    def applica(ids):
        if chi == "calcio":
            return AF.SottoscrittoreStream().applica(fw, ids)
        return IAC.sottoscrivi(fw, IAC.stream_di_mercato(fw), ids)
    with pytest.raises(ValueError):
        applica([])
    with pytest.raises(ValueError):
        applica(["1.%d" % i for i in range(201)])
    bs._running = False
    with pytest.raises(SC.NonPronto):
        applica(["1.2"])
    assert len(bs._socket.inviati) == 1 and st.stream_id == 10001
    # errore d'invio: l'id vecchio torna al suo posto, filtro invariato
    bs._running = True

    def _rotto(**_k):
        raise ConnectionError("socket giu'")
    bs.subscribe_to_markets = _rotto
    with pytest.raises(ConnectionError):
        applica(["1.2"])
    assert st.stream_id == 10001 and st.market_filter == {"marketIds": ["1.1"]}
