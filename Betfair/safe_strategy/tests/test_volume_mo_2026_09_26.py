# -*- coding: utf-8 -*-
"""26/09 (F-8, test e2e FASE 3) - «vol. 0,00 €» su 16/17 partite in gioco.

Lo stream dello scanner non porta il volume (fields EX_BEST_OFFERS +
EX_MARKET_DEF, niente EX_TRADED_VOL): betfairlightweight lascia
``MarketBook.total_matched = 0``. Quello zero finiva in
``payload.mo_total_matched`` e la Control Room stampava «vol. 0,00 €» mentre
il ladder del runner diceva «Matched €559».

Regola corretta: uno ZERO dallo stream non e' una misura -> non sovrascrive
il valore noto (REST), e senza valore noto resta ``None`` (a video «—»,
campo nascosto). Il REST scrive il suo valore, anche 0.

Book = ``MarketBook`` VERO di betfairlightweight (costruttore dei test del
canale scanner, ``test_canale_scanner_al_ms_2026_09_18``).

FALSIFICAZIONE (26/09): rimettendo
``ev["mo_total_matched"] = scanner.num_or_none(getattr(book, "total_matched", None))``
i primi due test diventano rossi (0.0 al posto di None / di 559.65).
"""
from __future__ import annotations

from Betfair.safe_strategy.tests.test_canale_scanner_al_ms_2026_09_18 import (
    CON_PREZZI, PT1, book, scanner_di_prova)


def test_zero_dallo_stream_non_e_un_volume():
    scan = scanner_di_prova()
    scan._apply_market_book(book("1.200", CON_PREZZI, total_matched=0.0, publish_time_ms=PT1),
                            dallo_stream=True)
    assert scan.events["c1"]["mo_total_matched"] is None


def test_lo_stream_non_cancella_il_volume_letto_dal_rest():
    scan = scanner_di_prova()
    scan._apply_market_book(book("1.200", CON_PREZZI, total_matched=559.65), dallo_stream=False)
    assert scan.events["c1"]["mo_total_matched"] == 559.65
    scan._apply_market_book(book("1.200", CON_PREZZI, total_matched=0.0, publish_time_ms=PT1),
                            dallo_stream=True)
    assert scan.events["c1"]["mo_total_matched"] == 559.65


def test_il_rest_scrive_il_suo_valore_anche_zero():
    scan = scanner_di_prova()
    scan._apply_market_book(book("1.200", CON_PREZZI, total_matched=0.0), dallo_stream=False)
    assert scan.events["c1"]["mo_total_matched"] == 0.0
    # e uno stream che un giorno portasse ``tv`` scrive il suo
    scan._apply_market_book(book("1.200", CON_PREZZI, total_matched=1200.0, publish_time_ms=PT1),
                            dallo_stream=True)
    assert scan.events["c1"]["mo_total_matched"] == 1200.0
