"""Verifica INDIPENDENTE del coordinatore sul cantiere N (28/09/2026) - Mike.

Reperto: ``engine._stessa_uscita_firmata`` risponde "si'" quando la proposta
firmata non c'e' piu' (``ctx.uscita_proposta is None``). La proposta sparisce
ogni volta che per un giro la strategia non vuole uscire (``_decadi``), ma la
firma (``ctx.uscita_approvata``) resta valida per 120 s. Al giro dopo una
decisione con la STESSA chiave (``categoria|cN``) e un ALTRO motivo passa con la
firma vecchia: l'utente ha approvato un cash out in profitto e il bot chiude in
perdita.

Regola dell'utente: in manuale OGNI uscita e' una proposta coi numeri che lui
approva. Una firma senza la sua proposta non dice che cosa e' stato approvato:
non deve eseguire niente. Test sul gate VERO con le classi vere del motore.
File ASCII-only.
"""
from __future__ import annotations

from Betfair.mike import engine as E
from Betfair.mike.tests.test_mike_engine import params

NOW = 1_800_000_000.0


def _snap(now: float = NOW) -> E.Snapshot:
    return E.Snapshot(now=now, ko_at=NOW - 1800, books={}, inplay=True, minute=30, goals=1)


def _chiusura(close_reason: str) -> E.Decision:
    return E.Decision(
        "LIVE_CLOSING",
        [E.Action("place", role="under_close", market="U35", selection="Under 3.5",
                  side="lay", price=2.0, size=5.0)],
        "chiusura " + close_reason,
        {"close_reason": close_reason}, {"cashout": {"net": -1.0}})


def _tengo() -> E.Decision:
    return E.Decision("LIVE_COVERED", [], "tengo", {}, {})


def _applica(ctx: E.MatchCtx, d: E.Decision) -> None:
    """Quello che il servizio fa degli ``updates`` del gate sui due campi che
    contano qui (stesse chiavi del contesto vero)."""
    for k in ("uscita_proposta", "uscita_approvata"):
        if k in d.updates:
            setattr(ctx, k, d.updates[k])


def test_firma_rimasta_dopo_la_decadenza_non_esegue_un_altra_uscita() -> None:
    p = params(uscite_automatiche=False)
    ctx = E.MatchCtx()
    ctx.state = "LIVE_COVERED"
    # giro 1: la strategia vuole chiudere IN PROFITTO -> nasce la proposta
    d1 = E.gate_uscite(ctx, _chiusura("profit"), _snap(NOW), p)
    assert [a for a in d1.actions if a.kind == "place"] == []
    _applica(ctx, d1)
    assert ctx.uscita_proposta["close_reason"] == "profit"
    # l'utente firma QUELLA proposta
    ctx.uscita_approvata = {"chiave": ctx.uscita_proposta["chiave"], "at": NOW + 1}
    # giro 2: per un giro la strategia non vuole uscire -> la proposta decade
    d2 = E.gate_uscite(ctx, _tengo(), _snap(NOW + 2), p)
    _applica(ctx, d2)
    assert ctx.uscita_proposta is None
    # giro 3: stessa categoria, motivo IN PERDITA, firma ancora dentro i 120 s
    d3 = E.gate_uscite(ctx, _chiusura("loss_ht"), _snap(NOW + 10), p)
    piazzati = [a for a in d3.actions if a.kind == "place"]
    assert piazzati == [], (
        "chiusura IN PERDITA eseguita con la firma data a una proposta IN "
        "PROFITTO che non esiste piu'")
    assert d3.updates.get("uscita_proposta", {}).get("close_reason") == "loss_ht"


def test_la_decadenza_della_proposta_porta_via_la_firma() -> None:
    p = params(uscite_automatiche=False)
    ctx = E.MatchCtx()
    ctx.state = "LIVE_COVERED"
    d1 = E.gate_uscite(ctx, _chiusura("profit"), _snap(NOW), p)
    _applica(ctx, d1)
    ctx.uscita_approvata = {"chiave": ctx.uscita_proposta["chiave"], "at": NOW + 1}
    d2 = E.gate_uscite(ctx, _tengo(), _snap(NOW + 2), p)
    _applica(ctx, d2)
    assert ctx.uscita_approvata is None, (
        "la proposta e' decaduta ma la firma resta: firma senza proposta")
