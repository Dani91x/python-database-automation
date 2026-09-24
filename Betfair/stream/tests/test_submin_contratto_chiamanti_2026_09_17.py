"""Contratto del modulo UNICO del place-and-trim (17/09/2026).

Regola: gli ordini SOTTO il minimo di giurisdizione nascono SOLO dal nucleo
unico (`Betfair/stream/trading/submin.py`) attraverso i suoi due adattatori:

  * REST    -> `Betfair/omega/omega_market.py::place_submin_live`
  * flumine -> `start_submin` / `advance_submin`

Questo test si rompe se qualcuno:
  a) fa passare il percorso REST da una sequenza scritta a mano invece che dal
     nucleo (`pianifica_submin`);
  b) aggiunge un chiamante del place-and-trim senza registrarlo qui (cosi' chi
     lo aggiunge e' costretto a leggere il contratto in
     `Betfair/stream/trading/INTERFACES.md`).
"""
from __future__ import annotations

import pathlib
import re

import pytest

from Betfair.omega import omega_market as M
from Betfair.stream.trading import submin as S


_RADICE = pathlib.Path(__file__).resolve().parents[3]

# Chiamanti LEGITTIMI del place-and-trim, fuori dai test (censimento 17/09).
_CHIAMANTI_ATTESI = {
    "Betfair/mike/engine.py",
    "Betfair/mike/service.py",
    "Betfair/omega/omega_market.py",
    "Betfair/omega/tools/replay_registrazioni.py",
    "Betfair/safe_strategy/bot_service.py",
    "Betfair/safe_strategy/certificazione.py",
    "Betfair/safe_strategy/execution.py",
    "Betfair/safe_strategy/tools/replay_registrazioni.py",
    "Betfair/stream/backtest/banco_comune.py",
    "Betfair/stream/live_order_worker.py",
    # 24/09 (estensione 3, decisione dell'utente): il motore ordini verifica la
    # percorribilita' con ``start_submin`` (puro) e poi usa la macchina DEL
    # WORKER (``_start_submin``/``_advance_submin_row``): nessuna copia.
    "Betfair/stream/motore_ordini.py",
    "Betfair/stream/scalper/scalper_bot.py",
    "Betfair/stream/scalper/sniper_bot.py",
    "Betfair/stream/scalper_lab/scalper_bot_base.py",
    "Betfair/stream/tennis_scalper/tennis_scalper_bot.py",
    "Betfair/stream/trading/submin.py",
}

_PAROLE = re.compile(r"place_submin_live|start_submin|advance_submin")


def test_il_percorso_rest_passa_dal_nucleo_unico():
    # niente copia della sequenza: il REST usa la STESSA funzione pura del flumine
    assert M._SUBMIN is S
    sorgente = pathlib.Path(M.__file__).read_text(encoding="utf-8")
    assert "_SUBMIN.pianifica_submin(" in sorgente
    assert "_SUBMIN.esito_istruzione(" in sorgente


def test_le_firme_pubbliche_restano_compatibili():
    import inspect
    par = inspect.signature(M.place_submin_live).parameters
    for atteso in ("market_id", "selection_id", "price", "size", "event_id",
                   "side", "customer_ref", "fill_or_kill"):
        assert atteso in par, atteso
    # i due nuovi sono OPZIONALI: i chiamanti storici non cambiano
    assert par["best_back"].default is None
    assert par["best_lay"].default is None


def test_nessun_chiamante_nuovo_non_registrato():
    trovati = set()
    for f in (_RADICE / "Betfair").rglob("*.py"):
        rel = f.relative_to(_RADICE).as_posix()
        if "/tests/" in rel or pathlib.Path(rel).name.startswith("test_"):
            continue
        try:
            testo = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:  # pragma: no cover - file illeggibile
            continue
        if _PAROLE.search(testo):
            trovati.add(rel)
    nuovi = trovati - _CHIAMANTI_ATTESI
    assert not nuovi, (
        "chiamanti del place-and-trim NON registrati: %s. Leggere il contratto in "
        "Betfair/stream/trading/INTERFACES.md e aggiungerli qui." % sorted(nuovi))


def test_la_marca_submin_e_completa():
    piano = S.pianifica_submin(side="back", target_price=5.9, target_size=0.79,
                               jurisdiction="it", best_back=5.4)
    marca = S.marca_submin(piano, bet_id="bet-1")
    for chiave in ("park_price", "park_size", "trimmed_from", "target_size",
                   "target_price", "size_reduction", "park_mode", "steps"):
        assert chiave in marca, chiave
    # il banco deve poter distinguere TRIMMATO da PIAZZATO sotto minimo
    assert marca["trimmed_from"] == 2.00 and marca["target_size"] == 0.79
    assert marca["steps"] == ["place", "cancel"]


@pytest.mark.parametrize("side,minimo", [("back", 2.00), ("lay", 0.50)])
def test_minimi_it_dalla_tabella_non_da_costanti_sparse(side, minimo):
    assert S.place_min_size("it", side) == minimo
