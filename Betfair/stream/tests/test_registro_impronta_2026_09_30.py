"""IMPRONTA DEL REFERTO PER TUTTI I BOT (banco, 30/09/2026).

``certifica.impronta`` fa lo sha1 dei file in ``moduli_produzione`` piu' i
controlli. Fino al 29/09 Omega, le quattro Safe, lo scalper calcio e i bot
tennis avevano UN solo modulo: cambiando il motore l'impronta restava uguale e
due referti di codice diverso sembravano dello stesso codice.

Contratto (stesso stile di ``Betfair/mike/tests/test_mike_p5_4b_2026_09_29.py``,
esteso alla chiusura TRANSITIVA degli import):

  A. ogni modulo elencato nel registro esiste come file;
  B. ogni modulo del pacchetto del bot raggiunto dagli import del servizio di
     produzione (anche dentro le funzioni, anche per nome come gli opzionali
     della Safe) sta nei ``moduli_produzione`` della scheda;
  C. l'impronta conta tutti i file e cambia se cambia un modulo che NON e' il
     servizio (copia in una cartella temporanea).

Finti: nessuno; registro vero, sorgenti veri.
"""
from __future__ import annotations

import ast
import os
from typing import Dict, List, Set, Tuple

import pytest

from Betfair.stream.backtest import registro_bot as REG

_RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# bot -> (servizio di produzione, pacchetti del bot)
_SERVIZI: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "mike": ("Betfair.mike.service", ("Betfair.mike",)),
    "omega": ("Betfair.omega.omega_service", ("Betfair.omega",)),
    "safe_base": ("Betfair.safe_strategy.bot_service", ("Betfair.safe_strategy",)),
    "safe_esatto": ("Betfair.safe_strategy.bot_service", ("Betfair.safe_strategy",)),
    "safe_punta": ("Betfair.safe_strategy.bot_service", ("Betfair.safe_strategy",)),
    "safe_tennis": ("Betfair.safe_strategy.bot_service", ("Betfair.safe_strategy",)),
    "scalper_calcio": ("Betfair.stream.scalper.scalper_service", ("Betfair.stream.scalper",)),
    "tennis_scalper": ("Betfair.stream.tennis_live.tennis_runner",
                       ("Betfair.stream.tennis_live", "Betfair.stream.tennis_scalper")),
    "tennis_pro": ("Betfair.stream.tennis_live.tennis_runner",
                   ("Betfair.stream.tennis_live", "Betfair.stream.tennis_scalper")),
    "tennis_flb": ("Betfair.stream.tennis_live.tennis_runner",
                   ("Betfair.stream.tennis_live", "Betfair.stream.tennis_scalper")),
    "tennis_swing": ("Betfair.stream.tennis_live.tennis_runner",
                     ("Betfair.stream.tennis_live", "Betfair.stream.tennis_scalper")),
}


def _file_di(modulo: str) -> str:
    return os.path.join(_RADICE, *modulo.split(".")) + ".py"


def _esiste(modulo: str) -> bool:
    return os.path.isfile(_file_di(modulo))


def _nomi_importati(modulo: str, albero: ast.AST) -> List[str]:
    """Tutti i nomi assoluti che un modulo importa (``from . import x`` da'
    sia il pacchetto sia ``pacchetto.x``: chi non e' un file si scarta dopo)."""
    fuori: List[str] = []
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.ImportFrom):
            if nodo.level:
                parti = modulo.split(".")[:-nodo.level]
                base = ".".join(parti + ([nodo.module] if nodo.module else []))
            else:
                base = nodo.module or ""
            fuori.append(base)
            fuori.extend(f"{base}.{a.name}" for a in nodo.names)
        elif isinstance(nodo, ast.Import):
            fuori.extend(a.name for a in nodo.names)
        elif isinstance(nodo, ast.Assign):
            # import PER NOME: ``OPTIONAL_MODULES = ("anomaly", ...)`` della Safe,
            # caricati con ``importlib.import_module(f"<pacchetto>.{name}")``
            nomi = [t.id for t in nodo.targets if isinstance(t, ast.Name)]
            if "OPTIONAL_MODULES" in nomi and isinstance(nodo.value, ast.Tuple):
                pacchetto = modulo.rsplit(".", 1)[0]
                fuori.extend(f"{pacchetto}.{c.value}" for c in nodo.value.elts
                             if isinstance(c, ast.Constant) and isinstance(c.value, str))
    return fuori


def _chiusura(servizio: str, pacchetti: Tuple[str, ...]) -> Set[str]:
    visti: Set[str] = set()
    coda = [servizio]
    while coda:
        m = coda.pop()
        if m in visti:
            continue
        visti.add(m)
        with open(_file_di(m), encoding="utf-8") as fh:
            albero = ast.parse(fh.read())
        for nome in _nomi_importati(m, albero):
            if any(nome == p or nome.startswith(p + ".") for p in pacchetti) and _esiste(nome):
                coda.append(nome)
    return visti


def test_ogni_bot_del_registro_ha_il_suo_servizio_qui():
    """Un bot nuovo nel registro senza riga qui non sfugge al contratto."""
    assert set(_SERVIZI) == set(REG.REGISTRO)


@pytest.mark.parametrize("nome", sorted(_SERVIZI))
def test_ogni_modulo_elencato_esiste(nome):
    scheda = REG.bot(nome)
    assert len(set(scheda.moduli_produzione)) == len(scheda.moduli_produzione), "doppioni"
    mancanti = [m for m in scheda.moduli_produzione if not _esiste(m)]
    assert mancanti == [], f"{nome}: moduli elencati che non esistono: {mancanti}"


@pytest.mark.parametrize("nome", sorted(_SERVIZI))
def test_ogni_modulo_importato_dal_servizio_e_nell_impronta(nome):
    servizio, pacchetti = _SERVIZI[nome]
    scheda = REG.bot(nome)
    chiusura = _chiusura(servizio, pacchetti)
    assert servizio in scheda.moduli_produzione
    # il test guarda davvero qualcosa: oltre al servizio c'e' almeno il motore
    assert len(chiusura) >= 5, f"{nome}: chiusura sospetta {sorted(chiusura)}"
    mancanti = sorted(chiusura - set(scheda.moduli_produzione))
    assert mancanti == [], f"{nome}: moduli fuori dall'impronta del referto: {mancanti}"


def test_la_chiusura_segue_gli_import_per_nome_della_safe():
    """I moduli opzionali della Safe (importati per nome) sono nella chiusura."""
    chiusura = _chiusura("Betfair.safe_strategy.bot_service", ("Betfair.safe_strategy",))
    assert {"Betfair.safe_strategy.combos",
            "Betfair.safe_strategy.tennis_opportunity"} <= chiusura
    # lo scanner di produzione NON e' del bot: non ci deve finire
    assert "Betfair.safe_strategy.service" not in chiusura


@pytest.mark.parametrize("nome", sorted(_SERVIZI))
def test_l_impronta_cambia_se_cambia_un_modulo_che_non_e_il_servizio(nome, monkeypatch, tmp_path):
    from Betfair.stream.backtest import certifica as CE

    scheda = REG.bot(nome)
    servizio = _SERVIZI[nome][0]
    monkeypatch.chdir(_RADICE)
    prima = CE.impronta(scheda)["codice_bot"]
    attesi = len(scheda.moduli_produzione) + 1
    assert prima.endswith(f"({attesi} file)"), prima
    # l'ULTIMO modulo elencato che non e' il servizio: e' cambiato solo lui
    toccato = [m for m in scheda.moduli_produzione if m != servizio][-1]
    for m in list(scheda.moduli_produzione) + [scheda.controlli]:
        rel = os.path.join(*m.split(".")) + ".py"
        with open(os.path.join(_RADICE, rel), "rb") as fh:
            testo = fh.read()
        if m == toccato:
            testo += b"\n# modulo cambiato\n"
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(testo)
    monkeypatch.chdir(tmp_path)
    dopo = CE.impronta(scheda)["codice_bot"]
    assert dopo.endswith(f"({attesi} file)"), dopo
    assert prima != dopo, f"{nome}: l'impronta non vede il cambio di {toccato}"
