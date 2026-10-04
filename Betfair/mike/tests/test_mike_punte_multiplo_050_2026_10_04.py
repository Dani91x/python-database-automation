"""04/10/2026 - MIKE: OGNI PUNTA DA 1,00 IN SU ESCE A MULTIPLO DI 0,50 (PER DIFETTO).

Fatto vero (Umea FC v Hammarby TFF, LIVE, soldi veri): punta Under 3,5 5,00 @1,52
(riga 5161), copertura banca Under 4,5 6,32 @1,23 (5166), chiusura banca Under 3,5 6,23
@1,22 abbinata (5169), chiusura della copertura PUNTA Under 4,5 7,27 @1,07 (5170) ->
``INVALID_BET_SIZE``, percorso REST. La copertura e' rimasta aperta, l'utente ha chiuso
a mano.

Regola dell'utente: da 1,00 in su la punta parte SOLO a multiplo di 0,50; decisione
«DIFETTO» (7,27 -> 7,00). Il residuo (0,27) non si dimentica: lo dichiara
``_controllo_di_piatto`` con la proposta all'utente, UN avviso per episodio, nessun
tentativo ripetuto.

Cosa certifica:
  (a) ``punta_a_multiplo`` e ``_place`` (l'unico punto dove nasce una punta di Mike);
  (b) i numeri di Umea: la chiusura della copertura e' PUNTA Under 4,5 7,00 @1,07;
  (c) strada REST diretta di Mike in LIVE (``service.execute_place`` VERO col
      ``PlaceResult`` VERO di ``omega_market``): parte 7,00; abbinata -> residuo 0,27
      dichiarato UNA volta, mai «chiuso», nessun ordine nuovo nei giri dopo;
  (d) chiusura RIFIUTATA per qualunque motivo: mai FLAT con la posizione aperta, il
      controllo di piatto scatta e l'avviso critico e' UNO (anche la riga del servizio);
  (e) il controllo di condotta L3 del banco: rosso su una punta >= 1,00 non multipla,
      zitto sulla decisione vera del motore.

Finti: oggetti veri dell'engine (Leg, Book, Snapshot, MatchCtx, Decision), servizio
vero, ``PlaceResult`` vero, DB in memoria della suite (``db_vuoto``). Nessuna rete.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.mike import certificazione as CERT
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_chiusura_copertura_2026_10_01 import (
    COMM,
    KO,
    gamba,
    libro,
    params,
)
from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import ORA, db_vuoto, info_vera
from Betfair.mike.tests.test_mike_p4_ordini_2026_09_29 import _live  # noqa: F401 (fixture)
from Betfair.omega.omega_market import PlaceResult

T0 = KO + 4200.0


def libri_umea(u45=(1.07, 1.08)):
    return {(E.MARKET_OU35, E.SEL_UNDER): libro(1.20, 1.22),
            (E.MARKET_OU45, E.SEL_UNDER): libro(*u45),
            (E.MARKET_OU45, E.SEL_OVER): libro(13.0, 15.0)}


def foto_umea(now=T0, **kw):
    return E.Snapshot(now=now, ko_at=KO, books=libri_umea(**kw), inplay=True, minute=70,
                      goals=2, feed_fresh=True, order_fresh=True)


def gambe_umea() -> List[E.Leg]:
    return [gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.52, 5.00,
                  ref="under_entry-0-1"),
            gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.23, 6.32,
                  ref="over_cover-0-4"),
            gamba("under_close", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.22, 6.23,
                  ref="under_close-0-5", placed_at=T0 - 30)]


def ctx_umea(attempts: int = 0) -> E.MatchCtx:
    return E.MatchCtx(state="LIVE_CLOSING", legs=gambe_umea(), close_reason="profit",
                      attempts=attempts)


def piazzamenti(d) -> List[E.Action]:
    return [a for a in d.actions if a.kind == "place"]


def _mercato(chiamate: List[Dict[str, Any]], *, codice: Any = None) -> SimpleNamespace:
    """``place_order_live`` col ``PlaceResult`` VERO: FOK abbinato per intero, oppure
    rifiutato col codice di Betfair (``ok=False``)."""
    def place_order_live(**kw: Any) -> PlaceResult:
        chiamate.append(kw)
        if codice is None:
            return PlaceResult(ok=True, order_status="EXECUTION_COMPLETE", bet_id="B-7",
                               size_matched=float(kw["size"]),
                               avg_price_matched=float(kw["price"]), raw={},
                               size_requested=float(kw["size"]),
                               price_requested=float(kw["price"]), size_remaining=0.0,
                               error_code=None, betfair_updated_at=None)
        return PlaceResult(ok=False, order_status="EXPIRED", bet_id=None, size_matched=0.0,
                           avg_price_matched=None, raw={}, size_requested=float(kw["size"]),
                           price_requested=float(kw["price"]), size_remaining=0.0,
                           size_cancelled=float(kw["size"]), error_code=codice,
                           betfair_updated_at=None)
    return SimpleNamespace(place_order_live=place_order_live)


def _esegui(ctx: E.MatchCtx, d: E.Decision, now: float, mercato: Any, db: Any) -> List[str]:
    esiti = []
    for leg in E.apply_decision(ctx, d, now):
        esiti.append(S.execute_place(db=db, market=mercato, info=info_vera(), leg=leg,
                                     book=libri_umea()[(leg.market, leg.selection)],
                                     mode="live", params=params(), now=ORA, dry=False,
                                     feed_fresh=True, ctx=ctx))
    return esiti


# ===========================================================================
# (a) la regola in Mike
# ===========================================================================
@pytest.mark.parametrize("chiesto,parte,residuo", [
    (7.27, 7.00, 0.27), (7.47, 7.00, 0.47), (7.50, 7.50, 0.0), (1.00, 1.00, 0.0),
    (1.35, 1.00, 0.35), (11.88, 11.50, 0.38), (0.73, 0.73, 0.0), (0.40, 0.40, 0.0)])
def test_a_punta_a_multiplo(chiesto, parte, residuo):
    assert E.punta_a_multiplo(chiesto) == (parte, residuo)


def test_a_place_arrotonda_solo_le_punte_e_lo_scrive_nella_nota():
    p = E._place("over_close", E.MARKET_OU45, E.SEL_UNDER, "back", 1.07, 7.27, note="x")
    assert p.size == 7.00 and p.note.startswith("x; punta 7.27 -> 7.00")
    assert "residuo 0.27" in p.note
    banca = E._place("under_close", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.22, 6.23)
    assert banca.size == 6.23 and banca.note == ""
    piccola = E._place("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.52, 0.73)
    assert piccola.size == 0.73                       # sotto 1,00: place-and-trim, invariata
    assert E.via_ordine("under_entry", "back", piccola.size, params()) == E.VIA_SUBMIN


# ===========================================================================
# (b) i numeri di Umea
# ===========================================================================
def test_b_umea_la_chiusura_della_copertura_parte_7_00():
    ctx = ctx_umea()
    cv = E.cashout_value(ctx.legs, libri_umea(), COMM)
    _sel, piano = cv.ripieghi[(E.MARKET_OU45, E.SEL_OVER)]
    assert (piano.side, piano.size, piano.price) == ("back", 7.27, 1.07)   # il piano esatto
    d = E.decide(ctx, foto_umea(), params())
    [a] = piazzamenti(d)
    assert (a.role, a.market, a.selection, a.side, a.size, a.price) == (
        "over_close", E.MARKET_OU45, E.SEL_UNDER, "back", 7.00, 1.07)
    assert CERT._l3(ctx, foto_umea(), d, params()) is None


# ===========================================================================
# (c) strada REST di Mike in live: abbinata 7,00 -> residuo dichiarato UNA volta
# ===========================================================================
def test_c_rest_live_parte_7_00_residuo_dichiarato_una_volta_nessun_ritento(
        monkeypatch, _live):
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    chiamate: List[Dict[str, Any]] = []
    mercato = _mercato(chiamate)
    db = db_vuoto()
    ctx = ctx_umea()
    d = E.decide(ctx, foto_umea(), params())
    assert _esegui(ctx, d, T0, mercato, db) == ["open"]
    assert [round(float(k["size"]), 2) for k in chiamate] == [7.00]      # mai 7,27
    avvisi = 0
    for dt in range(1, 121):
        d = E.decide(ctx, foto_umea(now=T0 + dt), params())
        assert piazzamenti(d) == [], (dt, d.reason)          # nessun tentativo ripetuto
        assert d.state != "FLAT", (dt, d.reason)            # mai «chiuso» col residuo
        if "chiusura_parziale" in d.telemetry:
            avvisi += 1
            S._registra_avvisi_esecuzione(db, d, ctx, "36140000")
        E.apply_decision(ctx, d, T0 + dt)
    assert avvisi == 1
    assert len(chiamate) == 1
    assert ctx.state == "LIVE_CLOSING" and ctx.uscita_proposta["residuo_scoperto"] is True
    assert ctx.reentry_done is True and ctx.reentry_allowed is False      # decisione 13
    righe = [p for k, p, _e in db.attivita if k == "chiusura_parziale"]
    assert len(righe) == 1 and righe[0]["critical"] is True
    # lo sbilancio e' quello dei 0,27 non piazzati (0,27 x 1,07 = 0,29 circa)
    w, l = E.exposure(ctx.legs, E.MARKET_OU45, E.SEL_UNDER)
    assert abs(w - l) == pytest.approx(0.27 * 1.07, abs=0.01)


# ===========================================================================
# (d) chiusura RIFIUTATA, qualunque motivo: mai chiuso, un avviso
# ===========================================================================
@pytest.mark.parametrize("codice", ["INVALID_BET_SIZE", "INSUFFICIENT_FUNDS", "ERROR_IN_ORDER",
                                    "BET_TAKEN_OR_LAPSED"])
def test_d_rest_live_chiusura_rifiutata_mai_chiuso_e_un_avviso(monkeypatch, _live, codice):
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    chiamate: List[Dict[str, Any]] = []
    mercato = _mercato(chiamate, codice=codice)
    db = db_vuoto()
    p = params(close_max_attempts=3, close_retry_s=10)
    ctx = ctx_umea()
    avvisi = 0
    for dt in range(0, 200):
        now = T0 + dt
        d = E.decide(ctx, foto_umea(now=now), p)
        aperta = bool(E.live_open_selections(ctx.legs, 2))
        assert not (aperta and d.state == "FLAT"), (dt, d.reason)
        if "chiusura_parziale" in d.telemetry:
            avvisi += 1
            S._registra_avvisi_esecuzione(db, d, ctx, "36140000")
        for leg in E.apply_decision(ctx, d, now):
            S.execute_place(db=db, market=mercato, info=info_vera(), leg=leg,
                            book=libri_umea()[(leg.market, leg.selection)], mode="live",
                            params=p, now=ORA, dry=False, feed_fresh=True, ctx=ctx)
    assert chiamate, "nessun tentativo di chiusura"
    assert all(round(float(k["size"]), 2) == 7.00 for k in chiamate)
    if codice == "INVALID_BET_SIZE":
        assert len(chiamate) == 1                     # lo strumento non si ripropone
    else:
        assert len(chiamate) <= 3                     # al piu' close_max_attempts
    tempi = sorted({round(float(l.placed_at), 1) for l in ctx.legs if l.role == "over_close"})
    assert all(b - a >= 10 for a, b in zip(tempi, tempi[1:])), tempi
    assert avvisi == 1
    assert ctx.state == "LIVE_CLOSING" and ctx.uscita_proposta["residuo_scoperto"] is True
    righe = [q for k, q, _e in db.attivita if k == "chiusura_parziale"]
    assert len(righe) == 1


# ===========================================================================
# (e) il controllo del banco L3
# ===========================================================================
def test_e_l3_rosso_su_punta_non_multipla_zitto_altrimenti():
    ctx = ctx_umea()
    s = foto_umea()
    fuori = E.Action(kind="place", role="over_close", market=E.MARKET_OU45,
                     selection=E.SEL_UNDER, side="back", price=1.07, size=7.27)
    assert "non multipla di 0,50" in CERT._l3(ctx, s, E.Decision("LIVE_CLOSING", [fuori]), params())
    for lato, size in (("back", 7.00), ("back", 0.73), ("lay", 6.23), ("lay", 6.32)):
        a = E.Action(kind="place", role="over_close", market=E.MARKET_OU45,
                     selection=E.SEL_UNDER, side=lato, price=1.07, size=size)
        assert CERT._l3(ctx, s, E.Decision("LIVE_CLOSING", [a]), params()) is None
    # registrato fra i controlli del banco
    assert "L3" in {r[0] for r in CERT._REGISTRO}
