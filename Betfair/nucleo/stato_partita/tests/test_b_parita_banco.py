"""W1-B - parita' PER TICK sullo SCANNER VERO del banco comune (marcatore ``cert``).

La catena e' quella del banco (``banco_comune.replay_evento``): registrazione
NATIVA -> flumine -> ``MarketBook`` -> ``Scanner._apply_market_book`` VERO ->
``build_rows`` VERA -> riga di ``safe_strategy_scan`` in memoria, con i punteggi
del sidecar iniettati da ``apply_score_state`` all'istante di ricezione
(ritardo di produzione IPS gia' nel ``ts_ms``, PSB par. 6.1). Il "servizio"
del banco qui e' PASSIVO: non decide niente, fotografa riga, ora e stato del
flusso a ogni giro (cadenza del banco, 1 s di tempo di mercato).

Su OGNI giro con la riga, il servizio nuovo (``FonteIpsScanner`` su una
``ScanRowCache`` VERA che legge la tabella del banco) deve dare:
  * minuto/gol/rossi = quelli della riga che i bot leggono; tempo =
    ``tempo_da_payload``; fase = ``mission_phase`` come ``_ht_ancora_in_gioco``;
  * ``prezzi_vivi`` = ``flusso_prezzi.valuta`` per lo stesso istante (anche con
    i mercati di una decisione: MATCH_ODDS + Correct Score, forma di Safe/Omega);
  * ``eta.punteggio_s`` = ``ScanFeedScoreProvider.score_age_sec`` e
    ``eta.riga_s`` = ``row_age_sec`` allo stesso istante.
Lo stato dello scanner (``safe_strategy_status``) e' la riga che lo scanner
scrive col blocco ``flusso`` di quell'istante (``Scanner.flusso_istantanea``).

Durata: ~30 s (35760084) + ~90 s (35797769) su questa macchina.
"""
from __future__ import annotations

import datetime as dt
import gzip
import os
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple

import pytest

from Betfair.nucleo.stato_partita import calcolo as C
from Betfair.nucleo.stato_partita.adattatori.ips import FonteIpsScanner
from Betfair.nucleo.stato_partita.servizio import ServizioStatoPartita
from Betfair.omega import omega_engine as E
from Betfair.stream import flusso_prezzi as FP
from Betfair.stream.scalper import atlante_v4 as A
from Betfair.stream.scores import scan_feed as SF
from Betfair.stream.scores.betfair_inplay import BetfairInPlayProvider, parse_score_dict

pytestmark = pytest.mark.cert

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
REGISTRAZIONI = os.path.join(RADICE, "registrazioni_banco")
ORA_FISSA = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)

#: numeri attesi (misurati il 09/10/2026, commit base 559a96df): un banco che
#: cambia cadenza o tabella cambia questi numeri e il test lo dice
ATTESI = {"35760084": {"giri_con_riga": 6076}, "35797769": {"giri_con_riga": 11720}}


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).isoformat()


@pytest.fixture(scope="module")
def cartella(tmp_path_factory: pytest.TempPathFactory) -> str:
    base = tmp_path_factory.mktemp("live_raw_b")
    for ev in ATTESI:
        (base / ev).mkdir()
        for nome in os.listdir(os.path.join(REGISTRAZIONI, ev)):
            src = os.path.join(REGISTRAZIONI, ev, nome)
            if nome.endswith(".gz"):
                with gzip.open(src, "rb") as a, open(base / ev / nome[:-3], "wb") as b:
                    shutil.copyfileobj(a, b)
            else:
                shutil.copy(src, base / ev / nome)
    return str(base)


def _giri(cartella: str, ev: str) -> List[Tuple[float, Optional[Dict[str, Any]], Dict[str, Any]]]:
    """(ora del giro, riga della tabella, stato dello scanner) a ogni giro."""
    from Betfair.stream.backtest import banco_comune as BC

    giri: List[Tuple[float, Optional[Dict[str, Any]], Dict[str, Any]]] = []

    def passivo(*, db: Any, market: Any, now: dt.datetime, row: Any, banco: Any,
                strategia: Any) -> None:
        giri.append((now.timestamp(), row, {"flusso": dict(banco.scan.flusso_istantanea)}))

    esito = BC.replay_evento(event_id=ev, cartella=cartella, servizio=passivo)
    assert not esito.errori, esito.errori
    return giri


@pytest.mark.parametrize("ev", list(ATTESI))
def test_parita_per_tick_sullo_scanner_vero(cartella: str, ev: str,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    giri = _giri(cartella, ev)
    corrente: Dict[str, Any] = {}
    cache = SF.ScanRowCache(ttl_sec=0.0, fetch=lambda ids: [corrente["riga"]],
                            fetch_status=lambda: corrente["stato"])
    srv = ServizioStatoPartita(FonteIpsScanner(cache), orologio_s=lambda: corrente["ora"])
    srv.segui([ev])
    vecchio = SF.ScanFeedScoreProvider(BetfairInPlayProvider(None), cache=cache)
    conti = {"giri_con_riga": 0, "esiti_fermi": 0, "minuto_riga_diverso_da_score_raw": 0,
             "fase_tempo_discordi": 0, "con_score_raw": 0}
    for ora, riga, stato_flusso in giri:
        if riga is None:
            continue
        conti["giri_con_riga"] += 1
        stato = {"id": "scanner", "payload": stato_flusso, "updated_at": _iso(ora)}
        corrente.update(riga=riga, stato=stato, ora=ora)
        monkeypatch.setattr(time, "time", lambda: ora)
        srv.aggiorna()
        st = srv.stato(ev)
        p = riga["payload"]
        raw = p.get("score_raw") if isinstance(p.get("score_raw"), dict) else None
        adesso_ms = int(ora * 1000)
        # numeri della riga
        assert st.minuto == p.get("minute")
        assert st.gol == C.coppia(p.get("score_home"), p.get("score_away"))
        assert st.rossi == C.coppia(p.get("red_home"), p.get("red_away"))
        assert st.in_gioco is (p.get("inplay") is True)
        assert st.tempo == A.tempo_da_payload(p)
        assert C.fase_come_omega(st.fase) == E.mission_phase(
            status=raw.get("matchStatus") if raw else None, minute=p.get("minute"),
            kickoff=None, now=ORA_FISSA)
        # condizione 11
        atteso = FP.valuta(p, stato_flusso, ev, None, adesso_ms)
        assert st.prezzi_vivi == atteso
        mercati = [p.get("mo_market_id")] + [b.get("market_id") for b in (p.get("cs"),)
                                             if isinstance(b, dict)]
        mercati = [m for m in mercati if m]
        assert srv.prezzi_vivi(ev, mercati) == FP.valuta(p, stato_flusso, None, mercati, adesso_ms)
        conti["esiti_fermi"] += 0 if atteso.vivo else 1
        # eta'
        assert st.eta.punteggio_s == vecchio.score_age_sec(ev)
        assert st.eta.riga_s == SF.row_age_sec(riga, ora)
        assert st.eta.scanner_s == cache.scanner_age_sec() == 0.0
        # misure per il referto (non asserzioni di parita')
        if raw is not None:
            conti["con_score_raw"] += 1
            if parse_score_dict(ev, raw).minute != p.get("minute"):
                conti["minuto_riga_diverso_da_score_raw"] += 1
        if st.fase in ("1t", "intervallo") and st.tempo != 1 or \
                st.fase in ("2t", "supplementari") and st.tempo != 2:
            conti["fase_tempo_discordi"] += 1
    print(f"\nPARITA_TICK {ev} {conti}")
    assert conti["giri_con_riga"] == ATTESI[ev]["giri_con_riga"]
    assert conti["esiti_fermi"] > 0          # la condizione 11 e' stata sollecitata anche "ferma"
