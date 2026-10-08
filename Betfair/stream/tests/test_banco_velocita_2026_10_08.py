"""Cantiere 11 (08/10/2026) - velocita' del banco SENZA controllare di meno.

Ogni struttura resa piu' rapida ha qui il suo test di EQUIVALENZA con la via di
prima (PROCESSO_STANDARD_BOT par. 6.9):

* ``valuta._livelli``: il livello ``dict`` di flumine si converte senza passare
  da ``_nuovo_livello`` -> stesso risultato, livello per livello, su ogni forma;
* ``banco_comune._livelli_di_produzione``: il ``dict`` di flumine si legge senza
  ``_offer_price``/``_offer_size`` -> stessi ``.price``/``.size``;
* ``validate_recordings.scan_raw``: la passata sul raw si ricorda per file ->
  stesso ``RawScan`` della lettura vera, rilettura se il file cambia, copia
  indipendente a ogni chiamata.
"""
from __future__ import annotations

import dataclasses
import json
import os

import pytest

from Betfair.stream import valuta as V
from Betfair.stream.backtest import banco_comune as BC
from Betfair.stream.backtest.sim_strategy import _offer_price, _offer_size
from Betfair.stream.tools import validate_recordings as VR

R = V.CAMBIO_RIPIEGO


class _DictFiglio(dict):
    """Una sottoclasse di dict: deve restare sulla via di prima."""


def _via_di_prima(livelli, r):
    """`valuta._livelli` com'era fino al 07/10 (riferimento dell'equivalenza)."""
    if livelli is None or isinstance(livelli, V._LivelliEur):
        return livelli
    return V._LivelliEur(V._nuovo_livello(x, r) for x in livelli)


def _forme():
    from betfairlightweight.resources.bettingresources import PriceSize

    return [
        [],
        [{"price": 1.5, "size": 10.0}],
        [{"price": 2.02, "size": 0.01}, {"price": 2.04, "size": 123456.789}],
        [{"price": 3.0, "size": None}],                      # size assente: copia e basta
        [{"price": 3.0}],                                     # chiave mancante
        [{"size": 7, "price": 1.01, "extra": "x"}],           # ordine e chiavi diverse
        [{"price": 1.9, "size": "12.5"}],                     # size testo (float lo legge)
        [{"price": "1.5", "size": 2}, {"price": 3, "size": 4}],   # prezzo testo e interi
        [_DictFiglio(price=1.2, size=3.0)],                   # sottoclasse: via di prima
        [[1.5, 10.0], (2.0, 5.5), [3.0]],                     # liste e tuple grezze
        [PriceSize(1.7, 44.4), PriceSize(1.8, None)],         # PriceSize
        [{"price": 1.5, "size": 10.0}, [2.0, 3.0], PriceSize(2.2, 1.0)],   # misti
    ]


@pytest.mark.parametrize("indice", range(len(_forme())))
def test_livelli_veloce_identico_alla_via_di_prima(indice):
    a = _forme()[indice]
    b = _forme()[indice]
    nuovo = V._livelli(a, R)
    prima = _via_di_prima(b, R)
    assert type(nuovo) is V._LivelliEur
    assert len(nuovo) == len(prima)
    for x, y in zip(nuovo, prima):
        assert type(x) is type(y)
        if isinstance(x, dict):
            assert list(x.items()) == list(y.items())     # stesse chiavi, stesso ordine
        elif isinstance(x, (list, tuple)):
            assert list(x) == list(y)
        else:
            assert (x.price, x.size) == (y.price, y.size)


def test_livelli_veloce_non_tocca_l_originale_e_copia():
    orig = [{"price": 1.5, "size": 10.0}]
    out = V._livelli(orig, R)
    assert orig == [{"price": 1.5, "size": 10.0}]
    assert out[0] is not orig[0]
    assert out[0]["size"] == round(10.0 * R, 2)


def test_livelli_veloce_idempotente_e_none():
    assert V._livelli(None, R) is None
    una = V._livelli([{"price": 2.0, "size": 100.0}], R)
    assert V._livelli(una, R) is una


def test_livelli_su_un_libro_vero_identici(tmp_path):
    """Sul percorso vero (`converti_libro` di un MarketBook di flumine costruito
    da righe di stream): stessi livelli della via di prima, campo per campo."""
    from flumine import FlumineSimulation  # noqa: F401 - patch di EX (dict)
    from betfairlightweight.resources.bettingresources import MarketBook

    def libro():
        return MarketBook(**{
            "marketId": "1.1", "isMarketDataDelayed": False, "status": "OPEN",
            "betDelay": 0, "bspReconciled": False, "complete": True, "inplay": False,
            "numberOfWinners": 1, "numberOfRunners": 2, "numberOfActiveRunners": 2,
            "totalMatched": 1000.0, "totalAvailable": 10.0, "crossMatching": True,
            "runnersVoidable": False, "version": 1,
            "runners": [{
                "selectionId": 1, "handicap": 0, "status": "ACTIVE", "totalMatched": 50.0,
                "ex": {"availableToBack": [{"price": 1.5, "size": 10.0}, {"price": 1.49, "size": 3.33}],
                       "availableToLay": [{"price": 1.52, "size": 7.77}],
                       "tradedVolume": [{"price": 1.5, "size": 1234.56}, {"price": 1.51, "size": 0.01}]},
            }],
        })

    a, b = libro(), libro()
    V.converti_libro(a, V.CambioGbpEur(fisso=R))
    rb = b.runners[0]
    rb.ex.available_to_back = _via_di_prima(rb.ex.available_to_back, R)
    rb.ex.available_to_lay = _via_di_prima(rb.ex.available_to_lay, R)
    rb.ex.traded_volume = _via_di_prima(rb.ex.traded_volume, R)
    ra = a.runners[0]
    for campo in ("available_to_back", "available_to_lay", "traded_volume"):
        assert getattr(ra.ex, campo) == getattr(rb.ex, campo), campo


@pytest.mark.parametrize("indice", range(len(_forme())))
def test_livelli_di_produzione_identici(indice):
    for liv_a, liv in zip(BC._livelli_di_produzione(_forme()[indice]), _forme()[indice]):
        attesi = (_offer_price(liv), _offer_size(liv))
        assert (liv_a.price, liv_a.size) == attesi
        # anche il TIPO (2 == 2.0 in Python: l'uguaglianza da sola non basta)
        assert (type(liv_a.price), type(liv_a.size)) == tuple(type(x) for x in attesi)


def test_livelli_di_produzione_none_e_vuoto():
    assert BC._livelli_di_produzione(None) == []
    assert BC._livelli_di_produzione([]) == []


# ---------------------------------------------------------------------------
# scan_raw ricordato
# ---------------------------------------------------------------------------
def _scrivi_raw(p, righe):
    with open(p, "w", encoding="utf-8") as fh:
        for r in righe:
            fh.write((r if isinstance(r, str) else json.dumps(r)) + "\n")


def _righe(n, pt0=1_700_000_000_000):
    out = [{"op": "mcm", "pt": pt0, "mc": [{"id": "1.1", "marketDefinition": {
        "openDate": "2023-11-14T22:13:20.000Z", "marketType": "MATCH_ODDS",
        "eventTypeId": "1", "status": "OPEN", "inPlay": False}}]}]
    for i in range(1, n):
        out.append({"op": "mcm", "pt": pt0 + i * 1000 + (120_000 if i == 5 else 0), "mc": []})
    out.append("non e' json")
    return out


@pytest.fixture(autouse=True)
def _memoria_pulita():
    VR._MEMORIA_SCAN.clear()
    yield
    VR._MEMORIA_SCAN.clear()


def test_scan_ricordato_identico_alla_lettura_vera(tmp_path):
    p = str(tmp_path / "1.raw.jsonl")
    _scrivi_raw(p, _righe(20))
    vero = VR._scan_raw_lettura(p)
    primo = VR.scan_raw(p)
    secondo = VR.scan_raw(p)           # dalla memoria
    assert dataclasses.asdict(primo) == dataclasses.asdict(vero)
    assert dataclasses.asdict(secondo) == dataclasses.asdict(vero)
    assert vero.gaps and vero.bad_lines == 1   # il caso prova davvero qualcosa


def test_scan_ricordato_e_una_copia(tmp_path):
    p = str(tmp_path / "1.raw.jsonl")
    _scrivi_raw(p, _righe(20))
    for _ in range(3):                  # la prima e' la lettura, le altre la memoria
        a = VR.scan_raw(p)
        assert (0, 1) not in a.gaps and a.n_lines == 20
        a.gaps.append((0, 1))
        a.n_lines = -1


def test_scan_si_rilegge_se_il_file_cambia(tmp_path):
    p = str(tmp_path / "1.raw.jsonl")
    _scrivi_raw(p, _righe(20))
    a = VR.scan_raw(p)
    _scrivi_raw(p, _righe(40))          # il registratore ha scritto ancora
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    b = VR.scan_raw(p)
    assert b.n_lines == 40 and a.n_lines == 20
    assert dataclasses.asdict(b) == dataclasses.asdict(VR._scan_raw_lettura(p))


def test_scan_soglia_diversa_e_un_altra_passata(tmp_path):
    p = str(tmp_path / "1.raw.jsonl")
    _scrivi_raw(p, _righe(20))
    assert VR.scan_raw(p, gap_threshold_s=60.0).gaps
    assert not VR.scan_raw(p, gap_threshold_s=1000.0).gaps


def test_scan_file_assente_si_rompe_come_prima(tmp_path):
    with pytest.raises(OSError):
        VR.scan_raw(str(tmp_path / "manca.raw.jsonl"))


# ---------------------------------------------------------------------------
# il confronto dei referti (prima/dopo, --worker 1 / --worker N)
# ---------------------------------------------------------------------------
_REFERTO_W1 = """BOT: omega | spec: x
SCENARI: base, paper

OK  1 [base]  tick=10 decisioni=  2 azioni=   0 stati=running [COMPLETE]
      nota: chiamate al mercato: list_today_football_events x444
      tempo: 1 [base] 12.2s (12.2 s) | 39662 tick/s
OK  1 [paper]  tick=10 decisioni=  2 azioni=   0 stati=running [COMPLETE]
CRITICAL:omega.service:[omega] avviso
      tempo: 1 [paper] 11.8s (11.8 s) | 41057 tick/s

ESITO: 2 partite senza violazioni, 0 con violazioni, 0 senza decisioni
TEMPO TOTALE: 24.0s (24.0 s) su 2 replay | obiettivo 300 s, tetto 600 s (CERTIFICA_TETTO_S)
"""

_REFERTO_W3 = """BOT: omega | spec: x
SCENARI: base, paper

worker: 3 su 4 core fisici (un processo per coppia evento x scenario, 2 coppie; il referto resta nello stesso ordine)

CRITICAL:omega.service:[omega] avviso
WARNING:flumine.controls:altro
OK  1 [base]  tick=10 decisioni=  2 azioni=   0 stati=running [COMPLETE]
      nota: chiamate al mercato: list_today_football_events x444
      tempo: 1 [base] 5.0s (5.0 s) | 2 tick/s
OK  1 [paper]  tick=10 decisioni=  2 azioni=   0 stati=running [COMPLETE]
      tempo: 1 [paper] 5.1s (5.1 s) | 2 tick/s

MEMORIA: picco per worker 150-170 MB (media 160 MB su 2 repliche)

ESITO: 2 partite senza violazioni, 0 con violazioni, 0 senza decisioni
TEMPO TOTALE: 5.1s (5.1 s) su 2 replay | obiettivo 300 s, tetto 600 s (CERTIFICA_TETTO_S)
"""


def test_confronto_worker_1_e_3_identici_tolte_solo_le_righe_dichiarate():
    from Betfair.stream.backtest.tools import confronta_referti as CR

    assert CR.differenze(_REFERTO_W1, _REFERTO_W3) == []


def test_confronto_vede_ogni_numero_diverso():
    """FALSIFICAZIONE: un numero del bot cambiato e' una riga diversa, anche se
    la riga sta fra righe di log o di tempo."""
    from Betfair.stream.backtest.tools import confronta_referti as CR

    for vecchio, nuovo in (("x444", "x438"), ("decisioni=  2", "decisioni=  3"),
                           ("ESITO: 2 partite", "ESITO: 1 partite")):
        diff = CR.differenze(_REFERTO_W1, _REFERTO_W3.replace(vecchio, nuovo, 1))
        assert [r for r in diff if r[:1] in "+-"], vecchio
    # una nota in piu' o in meno e' una riga diversa
    diff = CR.differenze(_REFERTO_W1, _REFERTO_W3.replace(
        "      nota: chiamate", "      nota: in piu'\n      nota: chiamate", 1))
    assert "+      nota: in piu'" in diff


def test_confronto_exit_code(tmp_path):
    from Betfair.stream.backtest.tools import confronta_referti as CR

    a, b, c = tmp_path / "a.txt", tmp_path / "b.txt", tmp_path / "c.txt"
    a.write_text(_REFERTO_W1, encoding="utf-8")
    b.write_text(_REFERTO_W3, encoding="utf-8")
    c.write_text(_REFERTO_W3.replace("x444", "x438"), encoding="utf-8")
    assert CR.main([str(a), str(b)]) == 0
    assert CR.main([str(a), str(c)]) == 1
