"""BANCO 08/10 (cantiere 15) - LA RIVALUTAZIONE DI CAMBIO NON E' UNO SCAMBIO.

Reperto: 35797769, MATCH_ODDS 1.259819674, messaggio delle 17:00:06.704 UTC (riga
1725 del raw). Il `tradedVolume` di TUTTI i livelli scambiati della sel 22 (da
1,64 a 1,72), della 58805 e della 29578 cresce dello STESSO fattore (x1,0000852,
scarto <= 0,008 per livello): e' il ricalcolo orario del cumulato al cambio nuovo
(lo stesso succede alle 18:00, 20:00, 21:00 col segno meno), non uno scambio. La
regola del mercato che attraversa (`banco_comune`, 6-quater) lo prendeva per
scambi a 1,67 e 1,64 e abbinava BACK 1,66, LAY 1,65 e BACK 4,20 dello scalper:
da li' il percorso nuovo e il KO di `chiusura-abbinata-in-parte`.

Oggetti VERI come in `test_banco_attraversa_2026_10_08.py` (stessa scena:
`FlumineSimulation` + `SimulatedMiddleware` + `MotoreReplay`, `MarketBook` di
betfairlightweight, `tradedVolume` CUMULATIVO) e il RAW VERO del banco
(`registrazioni_banco/35797769`). ASCII-only.
"""
from __future__ import annotations

import gzip
import json
import os
from typing import Any, Dict, List, Tuple

import pytest

from Betfair.stream.backtest import banco_comune as B
from Betfair.stream.tests.test_banco_attraversa_2026_10_08 import _book, _gira, _ms

RADICE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
RAW_35797769 = os.path.join(RADICE, "registrazioni_banco", "35797769",
                            "35797769.raw.jsonl.gz")
RIGA_RIVALUTAZIONE = 1725
MO = "1.259819674"

# il cumulato della sel 22 PRIMA della riga 1725 (dal raw, vedi il test sul raw)
# e i nove livelli che la riga riscrive: tutti x1,0000852
PRIMA_22 = [(1.64, 9474.69), (1.65, 44104.76), (1.66, 47192.01), (1.67, 13296.22),
            (1.68, 36968.01), (1.69, 36499.56), (1.7, 63473.00), (1.71, 41147.07),
            (1.72, 1616.14)]
DOPO_22 = [(1.64, 9475.50), (1.65, 44108.52), (1.66, 47196.03), (1.67, 13297.35),
           (1.68, 36971.16), (1.69, 36502.67), (1.7, 63478.41), (1.71, 41150.58),
           (1.72, 1616.28)]


def _delta(prima: List[Tuple[float, float]], dopo: List[Tuple[float, float]]
           ) -> Tuple[Dict[float, float], List[Dict[str, float]]]:
    """Il delta come lo calcola flumine (`RunnerAnalytics._calculate_traded`: solo
    i positivi, i livelli nuovi per intero) e il cumulato corrente."""
    p = dict(prima)
    traded = {}
    for prezzo, v in dopo:
        if prezzo in p:
            if v - p[prezzo] > 0:
                traded[prezzo] = round(v - p[prezzo], 2)
        else:
            traded[prezzo] = v
    return traded, [{"price": x, "size": v} for x, v in dopo]


# ---------------------------------------------------------------------------
# la funzione pura
# ---------------------------------------------------------------------------
def test_rivalutazione_del_reperto_non_e_uno_scambio():
    traded, tv = _delta(PRIMA_22, DOPO_22)
    assert len(traded) == 9 and round(sum(traded.values()), 2) == 25.04
    assert B.scambi_veri(traded, tv) == {}


def test_rivalutazione_con_uno_scambio_vero_nello_stesso_messaggio():
    """Uno scambio VERO di 7,00 a 1,67 arrivato insieme alla rivalutazione: resta
    (solo lui, al netto della parte proporzionale)."""
    dopo = [(p, round(v + (7.0 if p == 1.67 else 0.0), 2)) for p, v in DOPO_22]
    traded, tv = _delta(PRIMA_22, dopo)
    veri = B.scambi_veri(traded, tv)
    assert list(veri) == [1.67]
    assert veri[1.67] == pytest.approx(7.0, abs=0.02)


def test_livello_nuovo_e_sempre_scambio_vero():
    dopo = DOPO_22 + [(1.73, 4.0)]
    traded, tv = _delta(PRIMA_22, dopo)
    assert B.scambi_veri(traded, tv) == {1.73: 4.0}


def test_scambi_veri_su_piu_livelli_non_proporzionali_restano():
    """Uno sweep vero su tre livelli (importi non proporzionali al cumulato):
    nessuna rivalutazione, il delta torna intero."""
    dopo = [(p, round(v + {1.64: 30.0, 1.65: 2.0, 1.66: 11.0}.get(p, 0.0), 2))
            for p, v in PRIMA_22]
    traded, tv = _delta(PRIMA_22, dopo)
    assert traded == {1.64: 30.0, 1.65: 2.0, 1.66: 11.0}
    assert B.scambi_veri(traded, tv) == traded


def test_meno_di_tre_livelli_resta_scambio():
    """Con 1-2 livelli una rivalutazione non si distingue da uno scambio: resta
    scambio (limite dichiarato, prudente verso il modello di prima)."""
    prima = PRIMA_22[:2]
    dopo = DOPO_22[:2]
    traded, tv = _delta(prima, dopo)
    assert B.scambi_veri(traded, tv) == traded


def test_interruttore_spento_e_la_via_di_prima(monkeypatch):
    monkeypatch.setattr(B, "RIVALUTAZIONE_IGNORATA", False)
    traded, tv = _delta(PRIMA_22, DOPO_22)
    assert B.scambi_veri(traded, tv) is traded


# ---------------------------------------------------------------------------
# il RAW vero: la riga 1725 e' una rivalutazione, una riga con scambio vero no
# ---------------------------------------------------------------------------
def _cumulati_fino_a(riga: int) -> Tuple[Dict[Tuple[str, int], Dict[float, float]], Dict[str, Any]]:
    stato: Dict[Tuple[str, int], Dict[float, float]] = {}
    with gzip.open(RAW_35797769, "rt") as f:
        for i, linea in enumerate(f):
            d = json.loads(linea)
            if i == riga:
                return stato, d
            for mc in d.get("mc") or []:
                if mc.get("img"):
                    for k in [k for k in stato if k[0] == mc.get("id")]:
                        stato.pop(k)
                for rc in mc.get("rc") or []:
                    st = stato.setdefault((mc.get("id"), rc.get("id")), {})
                    for p, v in rc.get("trd") or []:
                        if v == 0:
                            st.pop(p, None)
                        else:
                            st[p] = v
    raise AssertionError("riga %d assente" % riga)


@pytest.mark.skipif(not os.path.exists(RAW_35797769), reason="registrazione del banco assente")
def test_raw_17_00_06_704_e_una_rivalutazione_su_tre_selezioni():
    stato, d = _cumulati_fino_a(RIGA_RIVALUTAZIONE)
    assert d["pt"] == 1783702806704                      # 17:00:06.704 UTC
    viste = 0
    for mc in d["mc"]:
        assert mc["id"] == MO
        for rc in mc["rc"]:
            if not rc.get("trd"):
                continue
            prima = sorted(stato.get((MO, rc["id"]), {}).items())
            dopo_d = dict(prima)
            dopo_d.update({p: v for p, v in rc["trd"]})
            traded, tv = _delta(prima, sorted(dopo_d.items()))
            assert len(traded) >= 5, (rc["id"], traded)
            assert B.scambi_veri(traded, tv) == {}, (rc["id"], traded)
            viste += 1
    assert viste == 3                                    # 22, 58805, 29578
    # i due cumulati del test puro sono quelli del raw
    assert [(p, v) for p, v in sorted(stato[(MO, 22)].items())
            if 1.64 <= p <= 1.72] == PRIMA_22


@pytest.mark.skipif(not os.path.exists(RAW_35797769), reason="registrazione del banco assente")
def test_raw_scambio_vero_a_un_livello_resta():
    """Riga 1704 (16:59:43.155): un solo livello (1,66) scambiato davvero. Il
    delta resta intero."""
    stato, d = _cumulati_fino_a(1704)
    rc = [r for mc in d["mc"] if mc["id"] == MO for r in mc["rc"] if r["id"] == 22][0]
    prima = sorted(stato[(MO, 22)].items())
    dopo_d = dict(prima)
    dopo_d.update({p: v for p, v in rc["trd"]})
    traded, tv = _delta(prima, sorted(dopo_d.items()))
    assert list(traded) == [1.66] and traded[1.66] > 0
    assert B.scambi_veri(traded, tv) == traded


# ---------------------------------------------------------------------------
# nel motore: la regola del mercato che attraversa non abbina su una rivalutazione
# ---------------------------------------------------------------------------
def _libro(t: float, tv: List[Tuple[float, float]]) -> Any:
    # le quote del maker del reperto stanno DENTRO lo spread (punta 1,66 sotto la
    # miglior banca 1,67, banca 1,65 sopra la miglior punta 1,64): a riposo
    return _book(t, atb=[(1.64, 500.0), (1.63, 800.0)], atl=[(1.67, 400.0)], tv=tv)


def _libri(dopo: List[Tuple[float, float]]) -> Tuple[Any, List[Any]]:
    primo = _libro(0, PRIMA_22)
    libri = [_libro(t, PRIMA_22) for t in (1, 2, 3, 4, 5, 6, 8)]
    libri.append(_libro(10, dopo))
    return primo, libri


@pytest.mark.parametrize("lato, prezzo", [("BACK", 1.66), ("LAY", 1.65)])
def test_motore_rivalutazione_non_abbina_per_attraversamento(lato, prezzo):
    """Le due gambe dello scalper del reperto (BACK 1,66 e LAY 1,65, 25,00): sul
    book della rivalutazione NON sono abbinate per attraversamento."""
    primo, libri = _libri(DOPO_22)
    ordine, sc = _gira(primo, libri, lato, prezzo, 25.0)
    assert sc.motore.fill_attraversati == [], sc.motore.fill_attraversati
    assert sc.motore.rivalutazioni_ignorate >= 1


@pytest.mark.parametrize("lato, prezzo", [("BACK", 1.66), ("LAY", 1.65)])
def test_motore_senza_la_correzione_abbinava(lato, prezzo, monkeypatch):
    """La via di prima (interruttore spento): e' il reperto, l'ordine abbinato per
    intero al suo prezzo all'istante della rivalutazione."""
    monkeypatch.setattr(B, "RIVALUTAZIONE_IGNORATA", False)
    primo, libri = _libri(DOPO_22)
    ordine, sc = _gira(primo, libri, lato, prezzo, 25.0)
    assert [(v["side"], v["prezzo"], v["ms"]) for v in sc.motore.fill_attraversati] \
        == [(lato, prezzo, _ms(10))]
    # abbinata tutta, al suo prezzo (la parte non data dall'attraversamento e'
    # quella che la coda di flumine prende dal delta al SUO prezzo: limite
    # dichiarato, la coda non e' toccata dal cantiere 15)
    assert ordine.size_matched == 25.0 and ordine.average_price_matched == prezzo


def test_motore_scambio_vero_insieme_alla_rivalutazione_abbina():
    """Rivalutazione + scambio VERO a 1,67 nello stesso book: la BACK 1,66 e'
    attraversata davvero e si abbina (la correzione non nasconde gli scambi)."""
    dopo = [(p, round(v + (7.0 if p == 1.67 else 0.0), 2)) for p, v in DOPO_22]
    primo, libri = _libri(dopo)
    ordine, sc = _gira(primo, libri, "BACK", 1.66, 25.0)
    assert [(v["side"], v["prezzo"], v["prezzo_oltre"]) for v in sc.motore.fill_attraversati] \
        == [("BACK", 1.66, 1.67)]
    assert ordine.size_matched == 25.0
