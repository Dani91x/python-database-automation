"""Integrazione W1-G1 + W1-C1 (09/10): contratto del FINTO contro il VERO.

Il finto ``_ArchivioMemoria`` dei test della porta (``test_c1_porta.py``) e l'``ArchivioLocale``
VERO di W1-G1 (``Betfair/nucleo/dati/archivio.py``, su una cartella temporanea) eseguono lo
STESSO copione di operazioni; ogni passo registra il risultato (in JSON, come lo vede il
chiamante) o il TIPO dell'eccezione, e i due elenchi devono essere identici. Copre: riga
assente, fusione delle colonne, transizione (riga assente = False, colonna ``status`` o
configurata), tipi (bool, None, float, NaN, liste, dizionari, tuple, testo non ASCII, interi
grandi, datetime), chiave intera contro testo, chiave mancante, tabella non registrata,
archivio chiuso (con l'ordine dei controlli del vero), guasti del disco (scrittura in coda,
transizione che ASPETTA il disco), lettore guasto.

Il finto non ha capacita' che il vero non ha: ogni attributo pubblico del finto esiste nel
vero, salvo gli interruttori di prova (``INTERRUTTORI``), che anche ``_ArchivioVero`` ha; i
metodi del protocollo hanno la STESSA firma.

Questo file NON usa la fixture ``archivio_parametrico`` (ogni test costruisce i due archivi).
"""
from __future__ import annotations

import inspect
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, List, Tuple

import pytest

from Betfair.nucleo.dati import archivio as ARCH
from Betfair.nucleo.dati.archivio import ArchivioLocale
from Betfair.nucleo.dati.contratto import Archivio
from Betfair.nucleo.ordini import porta as PT
from Betfair.nucleo.ordini.tests.test_c1_porta import _ArchivioMemoria, _ArchivioVero

REF, SEQ = PT.TABELLA_REF, PT.TABELLA_SEQ
#: gli interruttori di prova: NON sono capacita' del vero, li hanno sia il finto sia _ArchivioVero
INTERRUTTORI = frozenset({"guasto_lettura", "guasto_scrittura", "ritardo_lettura_s", "letture",
                          "tabelle", "colonna_stato"})

Passo = Tuple[str, Callable[[], Any]]


def _esito(fn: Callable[[], Any]) -> Tuple[str, str]:
    """('ok', JSON del risultato) o ('errore', tipo dell'eccezione)."""
    try:
        valore = fn()
    except Exception as exc:  # noqa: BLE001 - il tipo e' il dato confrontato
        return "errore", type(exc).__name__
    return "ok", json.dumps(valore, sort_keys=True, default=str)


def _copione(a: Any) -> List[Passo]:
    quando = datetime(2025, 10, 9, 10, 0, tzinfo=timezone.utc)
    return [
        ("leggi assente", lambda: a.leggi(REF, {"ref": "safe-1"})),
        ("transizione su riga assente", lambda: a.transizione(REF, {"ref": "safe-1"}, "", "x")),
        ("scrivi", lambda: a.scrivi(REF, {"ref": "safe-1", "status": "aperto", "seq": 1,
                                          "accettato": True, "motivo": None, "ts_ms": 1})),
        ("leggi", lambda: a.leggi(REF, {"ref": "safe-1"})),
        ("scrivi parziale", lambda: a.scrivi(REF, {"ref": "safe-1", "motivo": "m"})),
        ("leggi fusa", lambda: a.leggi(REF, {"ref": "safe-1"})),
        ("leggi con colonne in piu' nella chiave", lambda: a.leggi(REF, {"ref": "safe-1", "seq": 9})),
        ("transizione da sbagliato", lambda: a.transizione(REF, {"ref": "safe-1"}, "altro", "chiuso")),
        ("transizione", lambda: a.transizione(REF, {"ref": "safe-1"}, "aperto", "chiuso")),
        ("transizione ripetuta", lambda: a.transizione(REF, {"ref": "safe-1"}, "aperto", "chiuso")),
        ("leggi dopo transizione", lambda: a.leggi(REF, {"ref": "safe-1"})),
        ("scrivi tipi", lambda: a.scrivi(REF, {
            "ref": "safe-2", "f": 1.5, "n": None, "b": False, "l": [1, "a", {"x": 2}], "d": {"k": [True]},
            "t": (1, 2), "u": "perchè €", "grande": 2 ** 53 + 1, "nan": float("nan")})),
        ("leggi tipi", lambda: a.leggi(REF, {"ref": "safe-2"})),
        ("scrivi datetime", lambda: a.scrivi(REF, {"ref": "safe-3", "quando": quando})),
        ("leggi datetime", lambda: a.leggi(REF, {"ref": "safe-3"})),
        ("scrivi chiave intera", lambda: a.scrivi(REF, {"ref": 7, "x": 1})),
        ("leggi chiave testo", lambda: a.leggi(REF, {"ref": "7"})),
        ("leggi chiave intera", lambda: a.leggi(REF, {"ref": 7})),
        ("scrivi senza chiave", lambda: a.scrivi(REF, {"attore": "safe"})),
        ("leggi senza chiave", lambda: a.leggi(REF, {})),
        ("transizione senza chiave", lambda: a.transizione(REF, {}, "a", "b")),
        ("scrivi non registrata", lambda: a.scrivi("tabella_mai_dichiarata", {"id": 1})),
        ("leggi non registrata", lambda: a.leggi("tabella_mai_dichiarata", {"id": 1})),
        ("transizione non registrata", lambda: a.transizione("tabella_mai_dichiarata", {"id": 1}, "a", "b")),
        ("scrivi seq", lambda: a.scrivi(SEQ, {"chiave": "seq", "fino_a": 1000})),
        ("scrivi seq di nuovo", lambda: a.scrivi(SEQ, {"chiave": "seq", "fino_a": 2000})),
        ("leggi seq", lambda: a.leggi(SEQ, {"chiave": "seq"})),
        ("scrivi senza colonna di stato", lambda: a.scrivi(REF, {"ref": "safe-4"})),
        ("transizione senza colonna di stato", lambda: a.transizione(REF, {"ref": "safe-4"}, "", "x")),
        ("chiudi", lambda: a.chiudi()),
        ("aperto", lambda: a.aperto),
        ("leggi a chiuso", lambda: a.leggi(REF, {"ref": "safe-1"})),
        ("scrivi a chiuso", lambda: a.scrivi(REF, {"ref": "safe-9"})),
        ("transizione a chiuso", lambda: a.transizione(REF, {"ref": "safe-1"}, "chiuso", "x")),
        ("scrivi non registrata a chiuso", lambda: a.scrivi("tabella_mai_dichiarata", {"id": 1})),
        ("leggi non registrata a chiuso", lambda: a.leggi("tabella_mai_dichiarata", {"id": 1})),
        ("scrivi senza chiave a chiuso", lambda: a.scrivi(REF, {"attore": "safe"})),
        ("transizione senza chiave a chiuso", lambda: a.transizione(REF, {}, "a", "b")),
        ("chiudi di nuovo", lambda: a.chiudi()),
    ]


def _vero(tmp: Path, nome: str = "contratto", colonna_stato: str = "status") -> _ArchivioVero:
    a = _ArchivioVero(nome, base=tmp, colonna_stato=colonna_stato)
    a.apri()
    return a


def _esegui(a: Any, passi: List[Passo]) -> List[Tuple[str, str, str]]:
    return [(nome, *_esito(fn)) for nome, fn in passi]


def test_finto_e_vero_danno_le_stesse_risposte_sullo_stesso_copione(tmp_path: Path) -> None:
    finto = _ArchivioMemoria()
    vero = _vero(tmp_path)
    try:
        attesi = _esegui(vero, _copione(vero))
    finally:
        vero.chiudi()
    ottenuti = _esegui(finto, _copione(finto))
    differenze = [(v, f) for v, f in zip(attesi, ottenuti) if v != f]
    assert differenze == [] and len(attesi) == len(ottenuti), differenze
    # il copione tocca davvero i casi (non e' un confronto di soli None)
    assert ("transizione su riga assente", "ok", "false") in attesi
    assert ("transizione", "ok", "true") in attesi
    assert ("leggi a chiuso", "errore", "ArchivioChiuso") in attesi
    assert ("scrivi non registrata", "errore", "KeyError") in attesi


def test_finto_e_vero_con_la_colonna_di_stato_configurata(tmp_path: Path) -> None:
    def copione(a: Any) -> List[Passo]:
        return [
            ("scrivi", lambda: a.scrivi(REF, {"ref": "r", "stato": "x", "status": "y"})),
            ("transizione su status", lambda: a.transizione(REF, {"ref": "r"}, "y", "z")),
            ("transizione su stato", lambda: a.transizione(REF, {"ref": "r"}, "x", "z")),
            ("leggi", lambda: a.leggi(REF, {"ref": "r"})),
        ]

    vero = _vero(tmp_path, colonna_stato="stato")
    try:
        attesi = _esegui(vero, copione(vero))
    finally:
        vero.chiudi()
    assert attesi[1:3] == [("transizione su status", "ok", "false"), ("transizione su stato", "ok", "true")]
    finto = _ArchivioMemoria(colonna_stato="stato")
    assert _esegui(finto, copione(finto)) == attesi


def test_finto_e_vero_col_disco_guasto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Disco che rifiuta i commit: ``scrivi`` NON solleva e ``leggi`` vede la riga in coda;
    ``transizione`` (sincrona) ASPETTA il disco: dopo 0,3 s e' ancora ferma, al ritorno del
    disco da' l'esito vero. Lettore guasto: ``leggi`` solleva l'errore di SQLite, ``scrivi``
    no. Stessi esiti per finto e vero."""
    monkeypatch.setattr(ARCH, "ATTESA_RITENTO_BASE_S", 0.01)

    def prova(a: Any) -> List[Any]:
        out: List[Any] = []
        a.scrivi(REF, {"ref": "safe-g", "status": "aperto"})
        a.guasto_scrittura = True
        out.append(_esito(lambda: a.scrivi(REF, {"ref": "safe-g", "motivo": "in coda"})))
        out.append(_esito(lambda: a.leggi(REF, {"ref": "safe-g"})))
        esito: List[Any] = []
        t = threading.Thread(target=lambda: esito.append(
            _esito(lambda: a.transizione(REF, {"ref": "safe-g"}, "aperto", "chiuso"))), daemon=True)
        t.start()
        time.sleep(0.3)
        out.append(("ferma col disco guasto", t.is_alive()))
        a.guasto_scrittura = False
        t.join(10.0)
        out.append(("torna", not t.is_alive(), esito))
        a.guasto_lettura = True
        out.append(_esito(lambda: a.leggi(REF, {"ref": "safe-g"})))
        out.append(_esito(lambda: a.scrivi(REF, {"ref": "safe-h"})))
        a.guasto_lettura = False
        out.append(_esito(lambda: a.leggi(REF, {"ref": "safe-g"})))
        return out

    vero = _vero(tmp_path)
    try:
        attesi = prova(vero)
    finally:
        vero.guasto_scrittura = vero.guasto_lettura = False
        vero.chiudi(timeout_s=10.0)
    assert attesi[2] == ("ferma col disco guasto", True)
    assert attesi[3] == ("torna", True, [("ok", "true")])
    assert attesi[4] == ("errore", "OperationalError")
    assert prova(_ArchivioMemoria()) == attesi


def test_il_finto_aspetta_la_transizione_quanto_il_vero() -> None:
    """Col disco guasto oltre l'attesa il vero rinuncia a un lavoro non partito
    (``_esegui_sincrono``, ``timeout_s`` di serie): il finto ha la stessa attesa."""
    atteso = inspect.signature(ArchivioLocale._esegui_sincrono).parameters["timeout_s"].default
    assert _ArchivioMemoria._attesa_transizione_s == atteso
    a = _ArchivioMemoria()
    a._attesa_transizione_s = 0.05
    a.scrivi(REF, {"ref": "safe-t", "status": "aperto"})
    a.guasto_scrittura = True
    with pytest.raises(TimeoutError):
        a.transizione(REF, {"ref": "safe-t"}, "aperto", "chiuso")
    a.guasto_scrittura = False
    assert a.leggi(REF, {"ref": "safe-t"})["status"] == "aperto"      # non eseguita


def _pubblici(obj: Any) -> set[str]:
    return {n for n in dir(obj) if not n.startswith("_")}


def test_il_finto_non_ha_capacita_che_il_vero_non_ha(tmp_path: Path) -> None:
    finto = _ArchivioMemoria()
    vero = ArchivioLocale("capacita", {}, base=tmp_path)            # non aperto: nessun thread
    prova = _ArchivioVero("capacita-2", base=tmp_path)
    in_piu = _pubblici(finto) - _pubblici(vero) - INTERRUTTORI
    assert in_piu == set(), f"il finto sa fare cio' che il vero non sa: {sorted(in_piu)}"
    assert INTERRUTTORI <= _pubblici(prova), sorted(INTERRUTTORI - _pubblici(prova))
    for nome in ("leggi", "scrivi", "transizione", "chiudi"):
        f = inspect.signature(getattr(_ArchivioMemoria, nome))
        v = inspect.signature(getattr(ArchivioLocale, nome))
        assert [(p.name, p.kind, p.default) for p in f.parameters.values()] == \
            [(p.name, p.kind, p.default) for p in v.parameters.values()], nome
    for nome in ("leggi", "scrivi", "transizione"):                      # il protocollo Archivio
        assert hasattr(Archivio, nome)
    assert type(finto.cartella) is type(vero.cartella)                   # noqa: E721 - stesso tipo
