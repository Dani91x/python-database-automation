"""PIANO MIKE 29/09, P5 blocco 5: i GEMELLI nella forma banca (valore di serie)
dei test della forma di prima fissati su ``back_over45``. Stesse regole, stesso
motore: freno fail-closed dopo i rifiuti, ritmo minimo fra due tentativi, prima
tranche a meta', copertura ordinata dal flusso che non aspetta.

Finti: oggetti veri dell'engine; ``_rifiuta`` del file del freno (stessa strada
del servizio: ``registra_rifiuto_copertura``).
"""
from __future__ import annotations

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike.tests.test_mike_freno_copertura_2026_09_17 import _rifiuta

KO = 1_800_000_000.0


def params(**over):
    p = C.merge_params(None)
    p["uscite_automatiche"] = True
    p.update(over)
    return p


def _ctx(stake=20.0, **kw):
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", entry_price_initial=1.50, **kw)
    ctx.legs.append(E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                          side="back", price=1.50, size=stake, matched=stake, avg_price=1.50,
                          status="open", persistence="PERSIST", ref="under_last-0-1"))
    return ctx


def libro(bb, bl):
    return E.Book(best_back=bb, back_size=500.0, best_lay=bl, lay_size=500.0,
                  status="OPEN", inplay=True)


def _snap(now=KO + 20 * 60, goals=0, minute=20, over=9.0):
    books = {(E.MARKET_OU35, E.SEL_UNDER): libro(1.35, 1.36),
             (E.MARKET_OU45, E.SEL_UNDER): libro(1.10, 1.11),
             (E.MARKET_OU45, E.SEL_OVER): libro(over, over + 0.4)}
    return E.Snapshot(now=now, ko_at=KO, books=books, inplay=True, minute=minute,
                      goals=goals, feed_fresh=True, order_fresh=True, hazard=0.05,
                      p4_market=0.12)


def _banche(d):
    return [a for a in d.actions if a.kind == "place" and a.role == "over_cover"]


def test_di_serie_la_copertura_e_la_banca():
    assert C.DEFAULTS["cover_form"] == E.COVER_LAY_U45
    [a] = _banche(E.decide(_ctx(), _snap(), params()))
    assert (a.selection, a.side, a.size) == (E.SEL_UNDER, "lay", round(20 * 1.2 / 0.95, 2))


def test_gemello_freno_banca_bloccata_nessun_ordine():
    p = params(cover_rifiuti_max=3, cover_retry_min_s=1)
    ctx = _ctx()
    s = _snap()
    assert _banche(E.decide(ctx, s, p)), "senza freno la banca deve partire"
    _rifiuta(ctx, p, "CANCELLED_NOT_PLACED", quante=3)
    d = E.decide(ctx, s, p)
    assert _banche(d) == [] and d.state == "LIVE_UNCOVERED"
    assert d.telemetry["cover_wait"]["reason"] == "copertura_bloccata"


def test_gemello_ritmo_minimo_fra_due_banche():
    p = params(cover_retry_min_s=15)
    ctx = _ctx()
    s = _snap()
    assert _banche(E.decide(ctx, s, p))
    E.segna_tentativo_copertura(ctx, s.now)
    d = E.decide(ctx, s, p)
    assert _banche(d) == [] and d.telemetry["cover_wait"]["reason"] == "ritmo_minimo"
    assert _banche(E.decide(ctx, _snap(now=s.now + 15.5), p))


def test_gemello_prima_tranche_a_meta():
    ctx = _ctx(cover_stage=1, early_goal_at=KO + 60)
    d = E.decide(ctx, _snap(now=KO + 60 + 200, goals=1, minute=5), params())
    [a] = _banche(d)
    assert a.size == round(20 * 1.2 / 0.95 * 0.5, 2) and d.updates.get("cover_stage") == 1


@pytest.mark.parametrize("forzata", [True, False])
def test_gemello_copertura_ordinata_non_aspetta(forzata):
    """Minuto 5, 0 gol, hazard basso: l'attesa intelligente direbbe "aspetta";
    la copertura ORDINATA dal flusso (finestra di uscita scaduta) parte subito."""
    p = params(cover_policy="auto")
    ctx = _ctx(cover_forced=forzata)
    d = E.decide(ctx, _snap(minute=5, over=6.0), p)       # quota Over non ancora "buona"
    if forzata:
        assert [(a.selection, a.side) for a in _banche(d)] == [(E.SEL_UNDER, "lay")]
    else:
        assert _banche(d) == [] and d.reason == "attendo per coprire"
