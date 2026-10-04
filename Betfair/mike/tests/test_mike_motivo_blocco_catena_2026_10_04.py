"""04/10/2026 - MIKE: le aperture ferme per una causa che non e' il mercato si
DICONO sulla riga del bot (``stats.motivo_blocco``).

D1-quater (29/09) ferma gia' le aperture una volta per partita (``ctx.aperture_ferme``,
UN CRITICAL, nessun tentativo) e le riprende quando la causa sparisce; ma
``stats.motivo_blocco`` riportava solo il tetto partite: in Control Room Mike
«acceso in soldi veri» taceva. Qui SOLO la pubblicazione: la condotta non cambia.
Il ``ctx.aperture_ferme`` e' quello VERO scritto da ``_ferma_aperture`` nel flusso
del test D1-quater (``engine.decide`` / ``execute_place`` / ``execution._live_brake``).
"""
from __future__ import annotations

from typing import Any, Dict, List

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_aperture_ferme_d1quater_2026_09_29 import (  # noqa: F401
    _ambiente, _giro, _mercato_live, _snap,
)
from Betfair.mike.tests.test_mike_engine import params
from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import db_vuoto


def _riga_evento(ctx: E.MatchCtx) -> Dict[str, Any]:
    """La riga di ``tracked`` come la scrive il servizio (``_row_from_ctx``)."""
    return S._row_from_ctx({"event_id": "E1", "ctx": {}}, ctx, {})


def test_nessuna_partita_ferma_nessun_motivo():
    assert S.motivo_aperture_ferme({}) is None
    assert S.motivo_aperture_ferme({"E1": _riga_evento(E.MatchCtx())}) is None


def test_run_once_pubblica_il_motivo_nelle_stats(monkeypatch):
    """Il giro VERO (``run_once``) scrive il motivo in ``stats.motivo_blocco``
    per una partita seguita con le aperture ferme (riga con ``ctx`` vero)."""
    from Betfair.mike.tests.test_mike_audit_2026_09_11 import NOW, live_event
    from Betfair.mike.tests.test_mike_service import FakeDB, FakeMarket, run

    monkeypatch.setenv("LIVE_ORDER_MODE", "OFF")          # la causa resta
    db = FakeDB(params={"stake": 10})
    db.events["E1"] = live_event([], state_="WATCH", mode="live", ctx={
        "seen_inplay": True,
        "aperture_ferme": {"motivo": "live_order_mode_non_live:OFF", "mode": "live",
                           "dal": NOW.timestamp() - 60}})
    res = run(db, FakeMarket(), NOW, [])
    assert "aperture in soldi veri FERME su 1 partita" in str(res["stats"]["motivo_blocco"])


def test_ordini_reali_off_il_motivo_arriva_sulla_riga(monkeypatch):
    monkeypatch.setenv("LIVE_ORDER_MODE", "OFF")
    db, ctx, p = db_vuoto(), E.MatchCtx(), params()
    ordini: List[Dict[str, Any]] = []
    for i in range(3):
        _giro(db, ctx, _snap(i), p, _mercato_live(ordini), [])
    assert ordini == [] and ctx.aperture_ferme
    motivo = S.motivo_aperture_ferme({"E1": _riga_evento(ctx), "E2": _riga_evento(ctx)})
    assert motivo.startswith("aperture in soldi veri FERME su 2 partite")
    assert "«Ordini reali»" in motivo and "le chiusure non si fermano" in motivo
    # il tetto e le aperture ferme insieme: tutti e due detti, mai uno nascosto
    insieme = S._unisci_motivi("tetto partite raggiunto: 3 su 3 in live", motivo)
    assert insieme.startswith("tetto partite raggiunto") and motivo in insieme
    assert S._unisci_motivi(None, None) is None
    # la causa sparisce: le aperture ripartono, il motivo sparisce, l'ordine VERO parte
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    for i in range(3, 6):
        _giro(db, ctx, _snap(i), p, _mercato_live(ordini), [])
    assert ctx.aperture_ferme is None and len(ordini) == 1
    assert S.motivo_aperture_ferme({"E1": _riga_evento(ctx)}) is None
