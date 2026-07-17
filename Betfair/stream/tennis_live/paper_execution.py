"""paper_execution.py — SimulatedExecution con betDelay FRESCO (fix GAP-5).

PROBLEMA (GAP-5 del certificato di fedeltà paper, flumine 2.13.11):
``bet_delay`` è SNAPSHOTTATO alla creazione del package
(``execution/transaction.py:266`` → congelato in ``order/orderpackage.py:56``).
Se il mercato cambia regime tra decisione ed esecuzione (pre-off→in-play, o
betDelay diverso dopo una sospensione) il paper dorme il delay VECCHIO — spesso
0 — e filla PIÙ VELOCE del reale, proprio negli scenari post-gol/post-
sospensione dove il delay conta di più. Il demo deve essere lo specchio della
realtà: l'exchange applica il betDelay vigente ALL'ARRIVO dell'ordine, non
quello di quando l'abbiamo deciso.

FIX (solo NOSTRO codice, zero modifiche a site-packages): questa subclass
ri-legge ``market_book.bet_delay`` corrente dal framework al momento
dell'esecuzione del package (il market book è tenuto aggiornato dallo stream:
ogni marketDefinition change aggiorna ``betDelay``, betfairlightweight
``streaming/cache.py:241,319``) e aggiorna il package PRIMA dello sleep di
``SimulatedExecution.execute_place/execute_replace``
(``execution/simulatedexecution.py:35-36,109-112``).

WIRING: usare ``install_fresh_delay_execution(framework)`` DOPO aver costruito
``Flumine(client=...)`` (client paper). Sostituisce ``framework.
simulated_execution`` e ri-aggancia i client che la puntavano: così il
``__exit__`` di flumine (``baseflumine.py:525``) spegne il thread-pool GIUSTO a
ogni restart. NB: NON usare ``execution_cls=`` sul client — flumine non farebbe
mai lo shutdown di quell'istanza custom (leak di thread-pool a ogni rebuild).

Riusabile anche dal paper dello scalper calcio (stesso wiring in
scalper_session.py — fuori da questo cantiere, da cablare a parte).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from flumine.execution.simulatedexecution import SimulatedExecution

logger = logging.getLogger(__name__)


class FreshDelaySimulatedExecution(SimulatedExecution):
    """SimulatedExecution che ri-legge il betDelay CORRENTE prima di dormirlo.

    Solo place/replace usano il betDelay (cancel/update dormono le sole latenze
    di config): sono gli unici due punti da correggere.
    """

    def execute_place(
        self, order_package: Any, http_session: Optional[requests.Session]
    ) -> None:
        self._refresh_bet_delay(order_package)
        super().execute_place(order_package, http_session)

    def execute_replace(
        self, order_package: Any, http_session: Optional[requests.Session]
    ) -> None:
        self._refresh_bet_delay(order_package)
        super().execute_replace(order_package, http_session)

    def _refresh_bet_delay(self, order_package: Any) -> None:
        """Allinea ``order_package.bet_delay`` al market book CORRENTE.

        Best-effort e FAIL-SAFE: se il mercato/book non è leggibile si tiene lo
        snapshot originale (comportamento flumine invariato) — mai rompere
        l'esecuzione per il refresh del delay.
        """
        try:
            market = self.flumine.markets.markets.get(order_package.market_id)
        except Exception:  # noqa: BLE001 - markets non leggibile: snapshot invariato
            return
        market_book = getattr(market, "market_book", None)
        current = getattr(market_book, "bet_delay", None)
        if current is None:
            return
        try:
            current = int(current)
        except (TypeError, ValueError):
            return
        stale = order_package.bet_delay
        if current == stale:
            return
        order_package.bet_delay = current
        try:
            # coerenza con orderpackage.simulated_delay (usato da terzi/logging)
            order_package.simulated_delay = order_package.calc_simulated_delay()
        except Exception:  # noqa: BLE001 - solo coerenza informativa
            pass
        logger.info(
            "[paper-exec] betDelay stantio aggiornato %s -> %s (market %s): "
            "il paper dorme il delay VIGENTE come farebbe l'exchange (fix GAP-5).",
            stale, current, order_package.market_id,
        )


def install_fresh_delay_execution(framework: Any) -> FreshDelaySimulatedExecution:
    """Installa ``FreshDelaySimulatedExecution`` su un framework flumine.

    Sostituisce ``framework.simulated_execution`` (così ``__exit__`` ne fa lo
    shutdown a fine run) e ri-aggancia ogni client che puntava all'istanza
    originale (i client paper ricevono ``flumine.simulated_execution`` in
    ``clients/baseclient.py:83-84``). Idempotente.
    """
    stale = framework.simulated_execution
    if isinstance(stale, FreshDelaySimulatedExecution):
        return stale
    fresh = FreshDelaySimulatedExecution(framework)
    framework.simulated_execution = fresh
    for client in framework.clients:
        if getattr(client, "execution", None) is stale:
            client.execution = fresh
    return fresh
