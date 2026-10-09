"""W1-A2 - ``ladder.LadderEvento``: coalescenza, canale senza client, DB nel suo thread, chiusure.

I book sono ``MarketBook`` VERI: messaggi ``mcm`` della registrazione 35760084
passati al listener vero (``test_a2_finti.libri_registrazione``) o costruiti con
lo stesso ``StreamListener`` da messaggi nel formato ufficiale.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Dict, List, Optional

import pytest
from betfairlightweight.streaming.listener import StreamListener

from Betfair.nucleo.betfair import ladder as L
from Betfair.stream.recorder import serialize_book

from .test_a2_finti import attendi, prima_immagine

MID = "1.259475523"


class Orologio:
    def __init__(self, t: float = 100.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _modello() -> Dict[str, Any]:
    for m in prima_immagine("35760084")["mc"]:
        if m["marketDefinition"]["marketType"] == "MATCH_ODDS":
            return m
    raise AssertionError


class Libri:
    """MarketBook veri da messaggi mcm (listener vero), per un mercato."""

    def __init__(self) -> None:
        self.coda: "queue.Queue[List[Any]]" = queue.Queue()
        self.li = StreamListener(output_queue=self.coda, max_latency=None)
        self.li.register_stream(0, "marketSubscription")
        self.modello = _modello()
        self.sel = self.modello["marketDefinition"]["runners"][0]["id"]
        self.pt = 1782831952415

    def _uno(self, d: Dict[str, Any]) -> Any:
        self.li.on_data(json.dumps(d))
        return self.coda.get_nowait()[-1]

    def immagine(self) -> Any:
        m = dict(self.modello, id=MID)
        return self._uno({"op": "mcm", "pt": self.pt, "clk": "1", "ct": "SUB_IMAGE", "mc": [m]})

    def prezzo(self, prezzo: float, size: float) -> Any:
        self.pt += 7
        return self._uno({"op": "mcm", "pt": self.pt, "clk": "x",
                          "mc": [{"id": MID, "rc": [{"atb": [[prezzo, size]], "id": self.sel}]}]})

    def stato(self, stato: str) -> Any:
        self.pt += 7
        md = dict(self.modello["marketDefinition"], status=stato)
        return self._uno({"op": "mcm", "pt": self.pt, "clk": "y",
                          "mc": [{"id": MID, "marketDefinition": md}]})


def _meta(mid: str) -> Optional[L.MetaLadder]:
    return L.MetaLadder("35760084", "MATCH_ODDS", "Esito finale", {}) if mid == MID else None


def _ladder(sport: str = "calcio", **kw: Any):
    pubblicate: List[Dict[str, Any]] = []
    orologio = kw.pop("orologio", Orologio())
    lad = L.LadderEvento(L.profilo_ladder(sport, {}), meta=_meta,
                         pubblica=lambda t, r: pubblicate.append(r), orologio=orologio, **kw)
    return lad, pubblicate, orologio


def test_coalescenza_20ms_vince_l_ultimo_book():
    lb = Libri()
    lad, pub, ora = _ladder()
    lad.consumatore(lb.immagine())
    assert lad.esegui_scaduti() is None and len(pub) == 1
    ora.t += 0.005
    lad.consumatore(lb.prezzo(1.5, 10.0))
    ora.t += 0.005
    lad.consumatore(lb.prezzo(1.6, 3.0))          # fuso col precedente
    prossima = lad.esegui_scaduti()
    assert len(pub) == 1 and prossima == pytest.approx(100.020)
    ora.t = prossima
    assert lad.esegui_scaduti() is None
    assert len(pub) == 2 and lad.conti["fusi"] == 1
    prezzi = [lv[0] for s in pub[-1]["ladder"]["selections"] if s["selection_id"] == lb.sel
              for lv in s["back"]]
    assert 1.6 in prezzi and 1.5 in prezzi         # stato completo del book piu' recente
    assert lad.stato()["attesa_ms_max"] == pytest.approx(15.0)


def test_book_invariato_non_ripubblica_e_stato_entra_nella_firma():
    lb = Libri()
    lad, pub, ora = _ladder()
    b = lb.immagine()
    lad.consumatore(b)
    lad.esegui_scaduti()
    ora.t += 1
    lad.push_a_ogni_cambio(MID)                    # stesso oggetto: nessun cambio
    lad.esegui_scaduti()
    assert len(pub) == 1 and lad.conti["invariati"] == 1
    ora.t += 1
    lad.consumatore(lb.stato("SUSPENDED"))
    lad.esegui_scaduti()
    assert [r["status"] for r in pub] == ["OPEN", "SUSPENDED"]
    assert pub[1]["ladder"]["updated_ms"] > pub[0]["ladder"]["updated_ms"]


@pytest.mark.parametrize("sport,atteso_runner", [("calcio", "ultimo"), ("tennis", "chiuso")])
def test_chiusura_come_oggi_per_sport(sport, atteso_runner):
    """calcio: l'ultimo book noto marcato CLOSED (``recorder.py:220-225``);
    tennis: il book chiuso serializzato e marcato CLOSED (``tennis_runner.py:433-458``)."""
    lb = Libri()
    lad, pub, ora = _ladder(sport)
    aperto = lb.immagine()
    lad.consumatore(aperto)
    lad.esegui_scaduti()
    ora.t += 1
    chiuso = lb.stato("CLOSED")
    lad.consumatore(chiuso)
    lad.esegui_scaduti()
    assert pub[-1]["status"] == "CLOSED"
    # stesso contenuto (calcio) o stesso pt: updated_ms deve comunque crescere,
    # o la UI scarterebbe la riga (``piuFresca``)
    assert pub[-1]["ladder"]["updated_ms"] > pub[-2]["ladder"]["updated_ms"]
    if atteso_runner == "ultimo":
        atteso = serialize_book(aperto, 10)
    else:
        atteso = serialize_book(chiuso, 10)
    atteso["status"] = "CLOSED"
    assert pub[-1]["ladder"]["selections"] == L.payload_ladder(atteso, {}, 10, 3)["selections"]


def test_calcio_senza_book_prima_della_chiusura_non_pubblica():
    lb = Libri()
    lb.immagine()
    lad, pub, _ = _ladder("calcio")
    lad.consumatore(lb.stato("CLOSED"))
    lad.esegui_scaduti()
    assert pub == [] and lad.snapshot(MID) == {}


def test_canale_senza_client_poi_client_nuovo_riceve_tutto():
    lb = Libri()
    attivo = {"v": False}
    lad, pub, ora = _ladder(canale_attivo=lambda: attivo["v"])
    lad.consumatore(lb.immagine())
    lad.esegui_scaduti()
    assert pub == [] and lad.conti["senza_client"] == 1
    attivo["v"] = True
    ora.t += 1
    lad.esegui_scaduti()                            # nessun push: il client nuovo riceve
    assert len(pub) == 1 and pub[0]["market_id"] == MID


def test_meta_none_fuori_ladder_e_snapshot_stesso_schema():
    lb = Libri()
    lad, pub, _ = _ladder()
    b = lb.immagine()
    lad.consumatore(b)
    lad.esegui_scaduti()
    snap = lad.snapshot(MID)
    assert list(snap) == ["event_id", "market_id", "market_type", "market_name", "status", "ladder"]
    assert list(snap["ladder"]) == ["updated_ms", "selections"]
    assert snap == pub[0]
    assert lad.snapshot("1.999") == {}


def test_db_nel_suo_thread_write_on_change_e_ritento_su_errore():
    lb = Libri()
    righe: List[Dict[str, Any]] = []
    errori = {"n": 1}

    def scrivi(r: Dict[str, Any]) -> None:
        if errori["n"]:
            errori["n"] -= 1
            raise RuntimeError("supabase giu'")
        righe.append(r)
    lad, pub, _ = _ladder(scrivi_db=scrivi)
    lad.consumatore(lb.immagine())
    assert lad.esegui_db() == 0 and lad.conti["db_errori"] == 1     # fallita: si ritenta
    assert lad.esegui_db() == 1 and lad.esegui_db() == 0            # poi write-on-change
    lad.consumatore(lb.prezzo(1.4, 2.0))
    assert lad.esegui_db() == 1 and len(righe) == 2


def test_thread_vero_pubblica_e_si_ferma():
    lb = Libri()
    righe: List[Dict[str, Any]] = []
    pub: List[Dict[str, Any]] = []
    marcate: List[Dict[str, Any]] = []

    def marca(r: Dict[str, Any], libro: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(r, pt=libro.get("pt"))
        marcate.append(out)
        return out
    prof = L.ProfiloLadder("calcio", 10, 10, 3, 0.05, "marca_ultimo")
    lad = L.LadderEvento(prof, meta=_meta, pubblica=lambda t, r: pub.append(r),
                         scrivi_db=righe.append, marca_canale=marca)
    lad.avvia()
    try:
        def spingi() -> None:
            lad.consumatore(lb.immagine())
            for i in range(30):
                lad.consumatore(lb.prezzo(1.3 + i / 100.0, 1.0 + i))
                time.sleep(0.002)
        t = threading.Thread(target=spingi)
        t.start()
        t.join()
        assert attendi(lambda: pub and pub[-1]["ladder"]["selections"] == lad.snapshot(MID)["ladder"]["selections"])
        assert attendi(lambda: righe and righe[-1] == lad.snapshot(MID))
        assert "pt" in pub[-1] and "pt" not in righe[-1]      # la marca solo sul canale
        assert len(pub) < 31                                    # fusione a 20 ms
        assert lad.stato()["thread_vivo"]
    finally:
        lad.ferma()
    assert not [x for x in threading.enumerate() if x.name.startswith("ladder-") and x.is_alive()]


def test_sorgente_esterna_legge_l_ultimo_book_del_flusso():
    """Con ``sorgente`` (``FlussoMercato.book``) il ladder legge il book al momento
    della pubblicazione: il push porta solo il ``market_id``."""
    lb = Libri()
    corrente: Dict[str, Any] = {}
    lad, pub, ora = _ladder(sorgente=corrente.get)
    corrente[MID] = lb.immagine()
    lad.push_a_ogni_cambio(MID)
    corrente[MID] = lb.prezzo(1.7, 9.0)
    lad.esegui_scaduti()
    assert len(pub) == 1
    atteso = L.payload_ladder(serialize_book(corrente[MID], 10), {}, 10, 3)
    assert pub[0]["ladder"]["selections"] == atteso["selections"]


def test_profilo_ladder_valori_e_errori():
    assert L.profilo_ladder("calcio", {}) == L.ProfiloLadder("calcio", 10, 10, 3, 2.0, "marca_ultimo")
    assert L.profilo_ladder("tennis", {"TENNIS_LADDER_DEPTH": "4"}).livelli_max == 4
    with pytest.raises(ValueError):
        L.profilo_ladder("basket")  # type: ignore[arg-type]
