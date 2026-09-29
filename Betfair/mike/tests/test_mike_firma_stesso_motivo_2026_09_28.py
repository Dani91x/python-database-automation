"""CANTIERE N (28/09/2026) - Mike: una firma vale per l'uscita FIRMATA, non per
un'altra uscita della stessa categoria.

Reperto dell'audit: la chiave della proposta e' ``categoria|cN`` (``chiave_uscita``)
e non contiene il motivo. Una firma su un cash out IN PROFITTO (categoria
"chiusura", ``close_reason='profit'``) restava valida 120 s e, se nel frattempo la
strategia decideva un'uscita IN PERDITA della stessa categoria (``loss_ht``), il
gate la eseguiva: l'utente aveva approvato un'altra cosa.

Regola di oggi: "approvata, l'ordine parte ... solo se la condizione vale
ancora". Adesso la firma passa solo se il ``close_reason`` della decisione di
adesso e' quello della proposta firmata; altrimenti nasce la proposta nuova e la
firma vecchia si cancella. Test sul gate VERO (``engine.gate_uscite``) con le
classi vere del motore. File ASCII-only.
"""
from __future__ import annotations

from Betfair.mike import engine as E
from Betfair.mike.tests.test_mike_engine import params

NOW = 1_800_000_000.0


def _snap() -> E.Snapshot:
    return E.Snapshot(now=NOW, ko_at=NOW - 1800, books={}, inplay=True, minute=30, goals=1)


def _chiusura(close_reason: str) -> E.Decision:
    return E.Decision(
        "LIVE_CLOSING",
        [E.Action("place", role="under_close", market="U35", selection="Under 3.5",
                  side="lay", price=2.0, size=5.0)],
        "chiusura " + close_reason,
        {"close_reason": close_reason}, {"cashout": {"net": -1.0}})


def _ctx_firmato(close_reason_firmato: str) -> E.MatchCtx:
    ctx = E.MatchCtx()
    ctx.state = "LIVE_COVERED"
    chiave = E.chiave_uscita(ctx, "chiusura")
    ctx.uscita_proposta = {"chiave": chiave, "categoria": "chiusura",
                           "close_reason": close_reason_firmato}
    ctx.uscita_approvata = {"chiave": chiave, "at": NOW - 5}
    return ctx


def test_firma_sulla_stessa_uscita_passa():
    p = params(uscite_automatiche=False)
    d = E.gate_uscite(_ctx_firmato("profit"), _chiusura("profit"), _snap(), p)
    assert [a.role for a in d.actions if a.kind == "place"] == ["under_close"]
    assert d.updates["uscita_approvata"] is None


def test_firma_in_profitto_non_esegue_un_uscita_in_perdita():
    p = params(uscite_automatiche=False)
    d = E.gate_uscite(_ctx_firmato("profit"), _chiusura("loss_ht"), _snap(), p)
    assert [a for a in d.actions if a.kind == "place"] == [], "ha chiuso in perdita con la firma sbagliata"
    assert d.updates["uscita_proposta"]["close_reason"] == "loss_ht"
    assert d.updates["uscita_approvata"] is None, "la firma vecchia deve cadere"


def test_firma_senza_proposta_non_esegue_niente():
    """29/09 (verifica del coordinatore): una firma presente senza la sua
    proposta (es. contesto ripreso dopo un riavvio con la sola firma) non dice
    che cosa e' stato approvato: non esegue, nasce la proposta nuova."""
    p = params(uscite_automatiche=False)
    ctx = E.MatchCtx()
    ctx.state = "LIVE_COVERED"
    ctx.uscita_proposta = None
    ctx.uscita_approvata = {"chiave": E.chiave_uscita(ctx, "chiusura"), "at": NOW - 5}
    d = E.gate_uscite(ctx, _chiusura("profit"), _snap(), p)
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.updates["uscita_proposta"]["close_reason"] == "profit"
    assert d.updates["uscita_approvata"] is None
