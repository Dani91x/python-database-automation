"""W1-B - il servizio dello stato partita (``servizio.py``).

Contratto ``StatoPartitaService`` (segui/stato/iscrivi), eventi, ciclo di vita
del thread (``avvia``/``ferma``), ``osserva_book`` sui ``MarketBook`` VERI della
registrazione, e il giro completo sul sidecar vero di 35760084 e 35797769 con la
fonte del banco (``FonteRegistrazione`` su ``carica_punteggi``).
"""
from __future__ import annotations

import datetime as dt
import gzip
import inspect
import json
import os
import shutil
import threading
import time
from typing import Any, Dict, List, Mapping, Sequence

import pytest

from Betfair.nucleo.stato_partita import contratto as K
from Betfair.nucleo.stato_partita import servizio as S
from Betfair.nucleo.stato_partita.adattatori.lettura import lettura
from Betfair.nucleo.stato_partita.adattatori.registrazione import FonteRegistrazione
from Betfair.stream import flusso_prezzi as FP
from Betfair.stream.scores.betfair_inplay import parse_score_dict

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
REGISTRAZIONI = os.path.join(RADICE, "registrazioni_banco")
T0 = 1_782_837_600.0


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).isoformat()


class FonteInMemoria:
    """Una ``FonteStato`` che restituisce le buste che il test le da'
    (la stessa forma di ``adattatori/lettura.py``)."""

    nome = "memoria"

    def __init__(self) -> None:
        self.buste: Dict[str, Mapping[str, Any]] = {}
        self.letture = 0
        self.guasto: Exception | None = None

    def leggi(self, event_ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        self.letture += 1
        if self.guasto is not None:
            raise self.guasto
        return {e: self.buste[e] for e in event_ids if e in self.buste}


def _busta_riga(eid: str, *, minuto: int, gol: tuple, vivo: bool = True, status: str = "KickOff",
                eta_s: float = 1.0) -> Mapping[str, Any]:
    raw = {"timeElapsed": minuto, "matchStatus": status,
           "score": {"home": {"score": str(gol[0])}, "away": {"score": str(gol[1])}}}
    riga = {"event_id": eid, "sport": "calcio", "updated_at": _iso(T0 - eta_s),
            "payload": {"minute": minuto, "score_home": gol[0], "score_away": gol[1],
                        "red_home": 0, "red_away": 0, "score_raw": raw, "inplay": True,
                        "mo_market_id": "1.1",
                        "flusso": {"vivo": vivo, "motivo": None if vivo else FP.MOTIVO_INTERROTTO,
                                   "dal_ms": int((T0 - 50) * 1000), "mercati_fermi": []}}}
    stato = {"flusso": {"calcolato_ms": int(T0 * 1000), "eventi_fermi": {}}}
    return lettura(fonte="ips_scanner", trasporto="db", sport="calcio", riga=riga,
                   scanner_s=2.0, stato_scanner=stato)


def test_rispetta_il_contratto() -> None:
    for nome in ("stato", "segui", "iscrivi"):
        firma_c = inspect.signature(getattr(K.StatoPartitaService, nome))
        firma_s = inspect.signature(getattr(S.ServizioStatoPartita, nome))
        assert list(firma_c.parameters) == list(firma_s.parameters), nome
    for cls in ("FonteIpsScanner", "FonteIpsRunner"):
        from Betfair.nucleo.stato_partita.adattatori import ips

        assert list(inspect.signature(getattr(ips, cls).leggi).parameters) == ["self", "event_ids"]


def test_segui_stato_iscrivi_ed_eventi() -> None:
    fonte = FonteInMemoria()
    ora = [T0]
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: ora[0])
    stati: List[K.StatoPartita] = []
    eventi: List[Any] = []
    via = srv.iscrivi(stati.append)
    srv.iscrivi_eventi(eventi.append)
    assert srv.aggiorna() == [] and fonte.letture == 0      # nessuna partita seguita: nessuna lettura
    srv.segui(["7", "8"])
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0))
    srv.aggiorna()
    st = srv.stato("7")
    assert st is not None and st.fonte == "ips_scanner" and srv.stato("8") is None
    assert (st.minuto, st.gol, st.fase, st.tempo) == (10, (0, 0), "1t", 1)
    assert st.eta.riga_s == pytest.approx(1.0) and st.eta.punteggio_s == pytest.approx(4.0)
    assert st.eta.scanner_s == 2.0
    assert st.prezzi_vivi == FP.valuta(fonte.buste["7"]["riga"]["payload"],
                                       fonte.buste["7"]["stato_scanner"], "7", None, int(T0 * 1000))
    assert [type(e).__name__ for e in eventi] == ["StatoCambiato"] and len(stati) == 1
    srv.aggiorna()                                            # niente di nuovo: nessuna sveglia
    ora[0] = T0 + 5.0
    srv.aggiorna()                                            # solo il tempo passa: le eta' crescono
    assert len(eventi) == 1 and len(stati) == 1
    assert srv.stato("7").eta.riga_s == pytest.approx(6.0)    # ...e lo stato le porta aggiornate
    ora[0] = T0
    fonte.buste["7"] = _busta_riga("7", minuto=11, gol=(1, 0))
    srv.aggiorna()
    assert [type(e).__name__ for e in eventi[1:]] == ["StatoCambiato", "GolSegnato"]
    assert eventi[2].prima == (0, 0) and eventi[2].dopo == (1, 0)
    fonte.buste["7"] = _busta_riga("7", minuto=46, gol=(1, 0), status="FirstHalfEnd", vivo=False)
    srv.aggiorna()
    nomi = [type(e).__name__ for e in eventi[3:]]
    assert nomi == ["StatoCambiato", "FaseCambiata", "FlussoInterrotto"]
    assert eventi[4].prima == "1t" and eventi[4].dopo == "intervallo"
    assert eventi[5].esito.vivo is False and eventi[5].esito.motivo == FP.MOTIVO_INTERROTTO
    fonte.buste["7"] = _busta_riga("7", minuto=46, gol=(0, 0), status="FirstHalfEnd", vivo=True)
    srv.aggiorna()                                            # gol annullato: nessun GolSegnato
    assert [type(e).__name__ for e in eventi[6:]] == ["StatoCambiato", "FlussoRipreso"]
    via()
    fonte.buste["7"] = _busta_riga("7", minuto=50, gol=(0, 0), status="SecondHalfKickOff")
    srv.aggiorna()
    assert len(stati) == 4                                    # disiscritto: niente piu' per lui
    srv.segui(["8"])
    assert srv.stato("7") is None and srv.seguiti() == ["8"]  # chi esce viene dimenticato


def test_iscritto_che_solleva_non_ferma_gli_altri(caplog: pytest.LogCaptureFixture) -> None:
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0)
    srv.segui(["7"])
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0))
    ricevuti: List[Any] = []

    def rotto(_st: Any) -> None:
        raise ValueError("iscritto rotto")

    srv.iscrivi(rotto)
    srv.iscrivi(ricevuti.append)
    srv.aggiorna()
    assert len(ricevuti) == 1 and srv.errori_callback == 1
    assert "iscritto rotto" in caplog.text


def test_fonte_guasta_non_cancella_lo_stato(caplog: pytest.LogCaptureFixture) -> None:
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0)
    srv.segui(["7"])
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0))
    srv.aggiorna()
    fonte.guasto = RuntimeError("DB giu'")
    assert srv.aggiorna() == [] and srv.errori_fonte == 1
    assert srv.stato("7").minuto == 10 and "DB giu'" in caplog.text
    fonte.guasto = None
    fonte.buste.clear()
    srv.aggiorna()
    assert srv.stato("7").minuto == 10                        # nessun dato: resta l'ultimo


def test_prezzi_vivi_per_i_mercati_della_decisione() -> None:
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0)
    srv.segui(["7"])
    busta = _busta_riga("7", minuto=10, gol=(0, 0))
    busta["riga"]["payload"]["flusso"]["mercati_fermi"] = ["1.9"]
    fonte.buste["7"] = busta
    assert srv.prezzi_vivi("7") is FP.NON_NOTO               # nessuna lettura ancora
    srv.aggiorna()
    payload, stato = busta["riga"]["payload"], busta["stato_scanner"]
    adesso = int(T0 * 1000)
    for mercati in (None, ["1.1"], ["1.1", "1.9"], ["1.9"]):
        assert srv.prezzi_vivi("7", mercati) == FP.valuta(payload, stato, "7", mercati, adesso)
        assert srv.prezzi_vivi("7", mercati) == FP.valuta(payload, stato, None, mercati, adesso)
    assert srv.prezzi_vivi("7", ["1.9"]).motivo == FP.MOTIVO_MERCATO_FERMO


def _libri_veri(event_id: str, massimo: int) -> List[Any]:
    from betfairlightweight.streaming import StreamListener

    path = os.path.join(REGISTRAZIONI, event_id, f"{event_id}.raw.jsonl.gz")
    ascolto = StreamListener(max_latency=None, lightweight=False)
    ascolto.register_stream(0, "marketSubscription")
    libri: List[Any] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for i, riga in enumerate(fh):
            if i >= massimo:
                break
            msg = json.loads(riga)
            msg["id"] = 0
            ascolto.on_data(json.dumps(msg))
            ids = [m["id"] for m in msg.get("mc") or []]
            if ids:
                libri.extend(ascolto.stream.snap(market_ids=ids))
    return libri


def test_osserva_book_ko_e_in_gioco_dai_book_veri() -> None:
    """KO dalla ``market_definition`` (cache per mercato) e "in gioco" con la
    regola del runner calcio, per una fonte senza riga (IPS diretto)."""
    libri = _libri_veri("35760084", 30653)
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: T0)
    srv.segui(["35760084"])
    raw = {"timeElapsed": 5, "matchStatus": "KickOff"}
    fonte.buste["35760084"] = lettura(fonte="ips_diretto", trasporto="http", sport="calcio",
                                      grezzo=raw)
    visti_in_gioco = set()
    ultimi: Dict[str, Any] = {}       # arbitro: l'ultimo book di ogni mercato (runner.py:358-363)
    for i, mb in enumerate(libri):
        srv.osserva_book("35760084", mb)
        ultimi[mb.market_id] = mb
        if i % 20 and i != len(libri) - 1:
            continue
        srv.aggiorna()
        st = srv.stato("35760084")
        atteso = any(bool(b.inplay) and b.status != "CLOSED" for b in ultimi.values())
        visti_in_gioco.add(st.in_gioco)
        assert st.in_gioco == atteso
    ko = dt.datetime(2026, 6, 30, 16, 0, tzinfo=dt.timezone.utc).timestamp() * 1000
    assert srv.stato("35760084").ko_ms == int(ko)
    assert visti_in_gioco == {False, True}
    assert srv.stato("35760084").fonte == "ips_diretto"
    srv.osserva_book("altro", libri[0])                       # non seguita: ignorata
    assert srv.stato("altro") is None


def test_avvia_ferma_e_sveglia() -> None:
    fonte = FonteInMemoria()
    srv = S.ServizioStatoPartita(fonte, nome="stato-partita-test")
    srv.segui(["7"])
    fonte.buste["7"] = _busta_riga("7", minuto=10, gol=(0, 0))
    prima = threading.active_count()
    srv.avvia(periodo_s=30.0)
    srv.avvia(periodo_s=30.0)                                 # seconda volta: niente thread in piu'
    assert srv.vivo and threading.active_count() == prima + 1
    limite = time.monotonic() + 5.0
    while fonte.letture < 1 and time.monotonic() < limite:
        time.sleep(0.01)
    letture = fonte.letture
    srv.sveglia()                                             # giro subito, non fra 30 s
    while fonte.letture == letture and time.monotonic() < limite:
        time.sleep(0.01)
    assert fonte.letture > letture
    srv.ferma()
    assert not srv.vivo and threading.active_count() == prima
    srv.ferma()                                               # idempotente


def _sidecar_in(base: Any, ev: str) -> None:
    (base / ev).mkdir()
    with gzip.open(os.path.join(REGISTRAZIONI, ev, f"{ev}.scores.jsonl.gz"), "rb") as a, \
            open(base / ev / f"{ev}.scores.jsonl", "wb") as b:
        shutil.copyfileobj(a, b)


@pytest.mark.parametrize("ev,gol,fasi", [
    ("35760084", 4, [("pre", "1t"), ("1t", "intervallo"), ("intervallo", "2t"), ("2t", "finita")]),
    ("35797769", 3, [("pre", "1t"), ("1t", "intervallo"), ("intervallo", "2t"), ("2t", "finita")]),
])
def test_giro_sul_sidecar_vero(tmp_path: Any, ev: str, gol: int, fasi: List[tuple]) -> None:
    """Il servizio sul sidecar vero, record per record: ogni stato = parser di
    oggi; gol e fasi come nella partita; ``punteggio_s`` = istante + 3 s."""
    _sidecar_in(tmp_path, ev)
    fonte = FonteRegistrazione(str(tmp_path), ev)
    fonte.apri()
    ora = [0.0]
    srv = S.ServizioStatoPartita(fonte, orologio_s=lambda: ora[0])
    srv.segui([ev])
    eventi: List[Any] = []
    srv.iscrivi_eventi(eventi.append)
    for ts, rec in fonte.record:
        fonte.posiziona(ts)
        ora[0] = ts / 1000.0 + 0.5
        srv.aggiorna()
        st = srv.stato(ev)
        snap = parse_score_dict(ev, rec)
        assert (st.minuto, st.fonte) == (snap.minute, "registrazione")
        assert st.eta.riga_s == pytest.approx(0.5, abs=1e-3)
        assert st.eta.punteggio_s == pytest.approx(3.5, abs=1e-3)
        assert st.prezzi_vivi is FP.NON_NOTO                  # il sidecar non porta prezzi
    assert sum(isinstance(e, S.GolSegnato) for e in eventi) == gol
    assert [(e.prima, e.dopo) for e in eventi if isinstance(e, S.FaseCambiata)] == fasi
