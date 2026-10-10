"""W1-A2 - decisione 12 dell'utente (10/10/2026): "massima velocita'" del ladder.

La cadenza DI SERIE del ladder nuovo verso la UI e' 20 ms per mercato, scritta qui
LETTERALMENTE (non letta dal modulo): la costante, il default del costruttore, lo
stato del ladder costruito senza parametri e il comportamento sull'orologio finto.
Nessuna variabile d'ambiente di oggi la riporta a 200 ms (``LIVE_LADDER_CANALE_MS``
/``TENNIS_LADDER_CANALE_MS`` sono del ``ladder_worker`` di oggi, ``config_stream.py:74``);
la cadenza del DB (``*_LADDER_PUBLISH_SEC``, 2 s) resta com'e'.
Falsificazione: mutazioni C1..C4 in ``ARCHITETTURA_2026-10/ondata1/W1-A2/falsifica.py``.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import inspect

import pytest

from Betfair.nucleo.betfair import ladder as L

from .test_a2_ladder import MID, Libri, Orologio, _meta

#: la decisione dell'utente, scritta a mano: NON importata dal modulo
CADENZA_DI_SERIE_MS = 20

#: le variabili di oggi che, nel worker vecchio, fissano 200 ms o la cadenza del DB
AMBIENTE_DI_OGGI_A_200 = {
    "LIVE_LADDER_CANALE_MS": "200",
    "TENNIS_LADDER_CANALE_MS": "200",
}


def test_costante_di_serie_20_ms():
    assert L.INTERVALLO_MIN_MS == 20


def test_default_del_costruttore_20_ms():
    parametro = inspect.signature(L.LadderEvento.__init__).parameters["intervallo_min_ms"]
    assert parametro.default == CADENZA_DI_SERIE_MS


@pytest.mark.parametrize("sport", ["calcio", "tennis"])
@pytest.mark.parametrize("ambiente", [{}, AMBIENTE_DI_OGGI_A_200], ids=["vuoto", "canale_200"])
def test_ladder_costruito_di_serie_pubblica_a_20_ms_e_db_resta_a_2_s(sport, ambiente, monkeypatch):
    for chiave, valore in ambiente.items():           # anche nell'ambiente VERO del processo
        monkeypatch.setenv(chiave, valore)
    profilo = L.profilo_ladder(sport, ambiente)
    lad = L.LadderEvento(profilo, meta=_meta, pubblica=lambda t, r: None, orologio=Orologio())
    assert lad.stato()["intervallo_min_ms"] == CADENZA_DI_SERIE_MS
    assert profilo.db_sec == 2.0                       # LADDER_PUBLISH_SEC di oggi, invariato
    # il profilo non porta nessuna cadenza della UI: nessun campo che possa valere 200
    assert {f for f in vars(profilo)} == {"sport", "profondita", "livelli_max", "livelli_wom",
                                          "db_sec", "chiusura"}


def test_due_cambi_a_25_ms_due_pubblicazioni_a_10_ms_una_alla_scadenza_dei_20():
    """Sull'orologio finto: a 25 ms di distanza ogni cambio esce subito; a 10 ms il secondo
    aspetta la fine dei 20 ms dall'ultima pubblicazione (non 200)."""
    lb = Libri()
    pubblicate: list = []
    ora = Orologio()
    lad = L.LadderEvento(L.profilo_ladder("calcio", AMBIENTE_DI_OGGI_A_200), meta=_meta,
                         pubblica=lambda t, r: pubblicate.append(r), orologio=ora)
    lad.consumatore(lb.immagine())
    assert lad.esegui_scaduti() is None and len(pubblicate) == 1
    ora.t += 0.025
    lad.consumatore(lb.prezzo(1.5, 10.0))
    assert lad.esegui_scaduti() is None and len(pubblicate) == 2      # subito: 25 > 20 ms
    ora.t += 0.010
    lad.consumatore(lb.prezzo(1.6, 3.0))
    prossima = lad.esegui_scaduti()
    assert len(pubblicate) == 2
    assert prossima == pytest.approx(ora.t - 0.010 + CADENZA_DI_SERIE_MS / 1000.0)
    ora.t = prossima
    assert lad.esegui_scaduti() is None and len(pubblicate) == 3
    assert pubblicate[-1]["market_id"] == MID
