"""BANCO 30/09 - le due prove che mancavano sul controllo E2 (copertura come
BANCA Under 4,5), dalle mutazioni del coordinatore del 29/09
(``AUDIT_2026-09-29/mutazioni_coordinatore/mutazioni_coordinatore_mike_p5_4.py``):

  * T2 - "banca senza Under abbinato non vista" (``if liab <= 0`` -> ``if False``)
    era SOPRAVVISSUTA: nessun test metteva una banca di copertura davanti a una
    posizione Under 3,5 nulla. Con la mutazione E2 parla lo stesso, ma dice una
    cosa FALSA ("diversa dall'importo previsto 0.0"): il referto deve citare la
    causa vera (PROCESSO_STANDARD_BOT par. 6.8, violazioni con la regola
    citata). I test qui sotto la chiedono per nome, in tre forme reali;
  * T3 - "banca piu' piccola accettata anche senza tetto" (tolto
    ``spazio != float("inf")``) e' una mutazione EQUIVALENTE: senza tetto
    ``liability_room`` vale ``inf`` e la clausola successiva
    ``x*(q-1) > spazio + 0.011`` e' falsa per ogni x finito, quindi il ramo di
    tolleranza non si apre comunque. Il comportamento (banca ridotta senza tetto
    = violazione) e' gia' inchiodato da
    ``test_mike_p5_banco_2026_09_29.test_E2_banca_ridotta_dal_tetto_e_giusta``;
    qui lo si riprova su tutte le tranche e quote tipiche, e il test diventa
    ROSSO se la tolleranza si apre senza tetto (mutazione T3-bis del referto:
    ``spazio != float("inf")`` -> ``True`` e confronto senza ``spazio``).

Finti: oggetti veri dell'engine; ``CERT.verifica`` vero; aiuti di
``test_mike_p5_banco_2026_09_29`` (stesse gambe, stessi libri). ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.mike import engine as E
from Betfair.mike.tests.test_mike_p5_banco_2026_09_29 import (_viola, banca, gamba, ingresso,
                                                             params)

_CAUSA = "senza nessun Under abbinato"


def _posizioni_nulle():
    """Tre modi reali di avere l'Under 3,5 a zero: nessuna gamba; ingresso
    chiesto e non abbinato; ingresso abbinato e poi chiuso per intero (green)."""
    pendente = gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 0.0,
                     ref="under_entry-0-1", status="pending", size=10.0)
    chiusura = gamba("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.50, 10.0,
                     ref="under_green-0-2")
    return {"nessuna_gamba": [], "ingresso_non_abbinato": [pendente],
            "ingresso_chiuso": [ingresso(), chiusura]}


@pytest.mark.parametrize("caso", sorted(_posizioni_nulle()))
def test_E2_banca_senza_under_abbinato_parla_e_dice_perche(caso):
    legs = _posizioni_nulle()[caso]
    assert E.under_liability(legs) == 0.0, "precondizione: nessuna liability Under"
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=legs)
    n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [banca(12.63)], "cop"), "E2")
    assert n == 1 and len(v) == 1, (caso, v)
    assert _CAUSA in v[0].dettaglio, v[0].dettaglio


@pytest.mark.parametrize("prezzo", (1.05, 1.20, 1.50, 3.00))
@pytest.mark.parametrize("frazione_di_x", (0.25, 0.5, 0.99))
def test_E2_banca_piu_piccola_senza_tetto_e_sempre_un_errore(prezzo, frazione_di_x):
    """Senza tetto per partita nessuna banca piu' piccola dell'importo previsto
    (12,63 con 10 EUR di Under a 1,50) e' tollerata, a nessuna quota."""
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()])
    p = params(max_liability_per_match=0.0)
    assert E.liability_room(ctx, p) == float("inf")
    piccola = round(12.63 * frazione_di_x, 2)
    n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [banca(piccola, price=prezzo)],
                                  "cop"), "E2", p=p)
    assert n == 1 and len(v) == 1, (piccola, prezzo)
    assert "12.63" in v[0].dettaglio
