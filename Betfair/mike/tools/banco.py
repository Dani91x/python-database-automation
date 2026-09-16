"""IL BANCO DI PROVA DI MIKE — adesso e' il BANCO COMUNE, non un doppione.

`DbMemoria` e `MercatoFlumine` sono nati qui per Mike, ma la stessa coppia
serve identica a Omega, a Safe calcio e a Safe tennis: sono stati spostati in
`Betfair/stream/backtest/banco_comune.py`, insieme allo SCANNER VERO alimentato
dai book di flumine. Questo modulo resta come porta d'ingresso storica di Mike e
non duplica una riga.

Perche' il banco vive sotto `Betfair/stream/backtest/` e non sotto
`Betfair/safe_strategy/tools/`: il banco importa `flumine`, e importare flumine
RITOCCA `betfairlightweight` per tutto il processo
(`flumine/__init__.py`: `bettingresources.RunnerBookEX = EX`). Il processo dello
scanner di produzione non deve MAI importare flumine, altrimenti i suoi ladder
diventano dizionari e `scanner.best_price` (`levels[0].price`) leggerebbe None
in silenzio. `Betfair/stream/backtest/` e' gia' la casa del replay flumine
(`run_backtest.py`, `sim_strategy.py`): li' il vincolo e' rispettato per
costruzione.

LIMITI DEL BANCO: dichiarati in testa a `banco_comune.py` (catalogo assente e
nomi sintetizzati, nessun tetto di scanner, minimo di giurisdizione, bet delay
in-play, stop giornaliero e tetto partite che vivono in `run_once`, nessun
errore di rete).

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from ...stream.backtest.banco_comune import (  # noqa: F401
    DbMemoria,
    EsitoReplay,
    MercatoFlumine,
    ScannerReplay,
    carica_punteggi,
    libro_di_produzione,
    nomi_dal_punteggio,
    replay_evento,
)

__all__ = [
    "DbMemoria",
    "EsitoReplay",
    "MercatoFlumine",
    "ScannerReplay",
    "carica_punteggi",
    "libro_di_produzione",
    "nomi_dal_punteggio",
    "replay_evento",
]
