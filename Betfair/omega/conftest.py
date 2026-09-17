"""Ogni test di Omega parte da un servizio che non si ricorda niente.

Due cose, entrambe necessarie.

1) STATO DI PROCESSO. Il servizio tiene in memoria il budget dei tentativi per
   gamba, il dedup dei log, i cicli "ciechi" del green-up e la cache del fit di
   mercato: i test usano gli stessi ``event_id`` fra file diversi, e senza
   azzerarli un test erediterebbe lo stato del precedente.

2) LE CACHE DEL RESPIRO (§18, 13/09). Dal 13/09 il servizio tiene in memoria le
   righe del feed, l'eta' dello scanner, gli aggregati e gli insiemi di quello
   che ha gia' fatto, per non massacrare il database
   (``omega_service.svuota_le_cache``). Sono variabili di MODULO: senza
   azzerarle un test erediterebbe la copia del precedente e gli assert
   diventerebbero casuali.

   E le cadenze vanno anche SPENTE di default. Quasi tutti i test simulano piu'
   cicli consecutivi nello STESSO istante (``now`` costruito a mano), cosa che
   nella realta' non succede mai: con le cache accese il secondo giro
   rileggerebbe la copia in memoria e il test misurerebbe la cache invece del
   comportamento che vuole misurare. Chi vuole provare le cache lo fa apposta,
   accendendole — vedi ``test_omega_respiro_db_2026_09_13.py``.
"""
from __future__ import annotations

import pytest

# i parametri che governano il respiro: nei test valgono ZERO (nessuna cache,
# nessuna fase saltata), cioe' esattamente il comportamento di prima del 13/09
_CHIAVI_CADENZA = (
    "feed_cache_s",
    "scanner_status_cache_s",
    "aggregates_cache_s",
    "sets_cache_s",
    "results_every_s",
    "missions_every_s",
    "events_refresh_s",
    "idle_stats_s",
    "idle_cycle_s",
    # 16/09 (R9): ogni quanto si rilegge la POSIZIONE DI CONTO su Betfair. E'
    # una cadenza come le altre, e nei test vale zero: chi vuole provarla la
    # accende apposta (test_omega_chiuso_dall_utente_2026_09_16).
    "conto_every_s",
)


@pytest.fixture(autouse=True)
def _reset_omega_process_state():
    from Betfair.omega import omega_config as C
    from Betfair.omega import omega_service as S

    for name in ("_LEG_RETRY", "_SKIP_SEEN", "_BLIND_CYCLES", "_MARKET_FIT_CACHE"):
        d = getattr(S, name, None)
        if isinstance(d, dict):
            d.clear()
    originali = {k: C.DEFAULTS[k] for k in _CHIAVI_CADENZA if k in C.DEFAULTS}
    for k in originali:
        C.DEFAULTS[k] = 0.0
    # 3) L'INTERRUTTORE DEL MOTORE (17/09). In PRODUZIONE il default e' passato a
    #    `strategy_version=3` (decisione del coordinatore sui dati). La suite
    #    storica di Omega e' scritta per il motore v2 — due mercati, size dal
    #    target di giornata, green-up automatico — e senza questo pin ogni suo
    #    test misurerebbe un motore che non e' quello che sta collaudando.
    #    Qui si PINNA a 2: i test di V3 lo mettono a 3 APPOSTA, e il default VERO
    #    di produzione resta verificato su `omega_config._SPEC` (che questa
    #    fixture non tocca) dal contratto della UI.
    originali["strategy_version"] = C.DEFAULTS["strategy_version"]
    C.DEFAULTS["strategy_version"] = 2
    S.svuota_le_cache()
    try:
        yield
    finally:
        C.DEFAULTS.update(originali)
        S.svuota_le_cache()
