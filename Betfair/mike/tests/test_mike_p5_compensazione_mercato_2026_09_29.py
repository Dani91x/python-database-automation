"""PIANO MIKE 29/09, pacchetto P5, blocco 1 (M3.4): i conti del mercato 4,5
si fanno PER MERCATO e non per selezione.

La copertura come BANCA Under 4,5 e la sua chiusura come BANCA Over 4,5 stanno
su due selezioni dello STESSO mercato a due esiti. Contati selezione per
selezione sembrano due posizioni aperte; contati per mercato sono una posizione
chiusa. Questi test provano ogni punto del motore che doveva passare al
mercato; ognuno ha la sua mutazione (vedi il referto MIKE_P5_1.md).

Numeri d'esempio del piano (lettura A scelta dall'utente): punta Under 3,5
10,00 a 1,50; banca Under 4,5 12,63 a 1,18 (rischio 2,27); chiusura della
copertura con banca Over 4,5 0,71 a 21 (esito -1,56 / -1,57).

I finti sono gli oggetti veri dell'engine (Leg, Book, Snapshot, MatchCtx) e,
per il conto, ordini con le chiavi di ``omega_market`` (snake_case).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S

KO = 1_700_000_000.0
PAR = C.merge_params(None)
COMM = 0.05


def gamba(role: str, market: str, selection: str, side: str, prezzo: float,
          abbinato: float, *, ref: str, status: str = "open",
          size: Optional[float] = None) -> E.Leg:
    return E.Leg(role=role, market=market, selection=selection, side=side,
                 price=prezzo, size=abbinato if size is None else size,
                 matched=abbinato, avg_price=prezzo if abbinato > 0 else None,
                 ref=ref, status=status, placed_at=KO)


def ingresso() -> E.Leg:
    return gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 10.0,
                 ref="under_entry-0-1")


def copertura_banca(abbinato: float = 12.63, status: str = "open",
                    ref: str = "over_cover-0-3") -> E.Leg:
    return gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.18, abbinato,
                 ref=ref, status=status, size=12.63)


def chiusura_banca_over() -> E.Leg:
    return gamba("over_close", E.MARKET_OU45, E.SEL_OVER, "lay", 21.0, 0.71,
                 ref="over_close-0-4")


# ---------------------------------------------------------------------------
# exposure: la gamba sull'altra selezione pesa rovesciata
# ---------------------------------------------------------------------------
def test_exposure_conta_la_banca_sull_altra_selezione_rovesciata():
    legs = [copertura_banca()]
    # dall'Under: banca 12,63 a 1,18 -> se vince -2,2734, se perde +12,63
    assert E.exposure(legs, E.MARKET_OU45, E.SEL_UNDER) == (-2.2734, 12.63)
    # dall'Over: la stessa posizione vista dall'altro lato
    assert E.exposure(legs, E.MARKET_OU45, E.SEL_OVER) == (12.63, -2.2734)
    # la punta Over 4,5 di oggi vista dall'Under: stessa posizione, rovesciata
    punta = gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 6.6, 2.26,
                  ref="over_cover-0-3")
    assert E.exposure([punta], E.MARKET_OU45, E.SEL_UNDER) == (-2.26, round(2.26 * 5.6, 4))


def test_exposure_con_gambe_su_una_sola_selezione_e_quella_di_prima():
    punta = gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 6.6, 2.26,
                  ref="over_cover-0-3")
    assert E.exposure([ingresso(), punta], E.MARKET_OU45, E.SEL_OVER) == (
        round(2.26 * 5.6, 4), -2.26)
    assert E.exposure([ingresso(), punta], E.MARKET_OU35, E.SEL_UNDER) == (5.0, -10.0)


# ---------------------------------------------------------------------------
# test 2 del progetto: copertura banca + chiusura banca Over = mercato piatto
# ---------------------------------------------------------------------------
def test_copertura_banca_chiusa_dalla_banca_over_lascia_il_mercato_piatto():
    legs = [copertura_banca(), chiusura_banca_over()]
    assert E.open_selections(legs) == []
    bloccato = E.locked_pnl(legs, COMM)
    assert bloccato is not None and abs(bloccato - (-1.57)) < 0.011
    # una sola riga per il mercato, nessuna posizione da chiudere
    assert E.posizione_per_selezione(legs, {}, COMM) == []


def test_dopo_la_chiusura_il_cash_out_non_disfa_la_chiusura():
    """Con la chiusura riuscita non deve uscire nessun ordine sul mercato 4,5:
    per selezione ne sarebbero usciti due (una punta Under e una punta Over)."""
    legs = [ingresso(), copertura_banca(), chiusura_banca_over()]
    books = {
        (E.MARKET_OU35, E.SEL_UNDER): E.Book(best_back=1.30, back_size=500.0,
                                             best_lay=1.31, lay_size=500.0),
        (E.MARKET_OU45, E.SEL_UNDER): E.Book(best_back=1.05, back_size=500.0,
                                             best_lay=1.06, lay_size=500.0),
        (E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=20.0, back_size=500.0,
                                            best_lay=21.0, lay_size=500.0),
    }
    cv = E.cashout_value(legs, books, COMM)
    assert set(cv.plans) == {(E.MARKET_OU35, E.SEL_UNDER)}


# ---------------------------------------------------------------------------
# una chiave per mercato e la chiusura come BANCA Over (M3.3)
# ---------------------------------------------------------------------------
def test_copertura_banca_aperta_si_chiude_bancando_l_over():
    legs = [ingresso(), copertura_banca()]
    assert E.open_selections(legs) == [(E.MARKET_OU35, E.SEL_UNDER),
                                       (E.MARKET_OU45, E.SEL_OVER)]
    books = {
        (E.MARKET_OU35, E.SEL_UNDER): E.Book(best_back=1.30, back_size=500.0,
                                             best_lay=1.31, lay_size=500.0),
        # 01/10: Over 4,5 a 12,5 (era 21). A 21 la banca valeva 0,71, sotto il
        # minimo commerciale della banca (1,00): oggi non parte. A 12,5 vale
        # 1,19: la regola provata qui (si chiude BANCANDO l'Over, M3.3) e' la stessa.
        (E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=12.0, back_size=500.0,
                                            best_lay=12.5, lay_size=500.0),
    }
    cv = E.cashout_value(legs, books, COMM)
    piano = cv.plans[(E.MARKET_OU45, E.SEL_OVER)]
    assert piano.side == "lay" and piano.price == 12.5 and piano.size == 1.19
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs)
    azioni = E._close_actions(ctx, cv, PAR)
    over = [a for a in azioni if a.market == E.MARKET_OU45]
    assert [(a.role, a.selection, a.side, a.size) for a in over] == [
        ("over_close", E.SEL_OVER, "lay", 1.19)]


def test_residuo_corto_di_una_chiusura_resta_sulla_sua_selezione_come_prima():
    """Forma di oggi: punta Over chiusa da una banca Over un po' piu' grande. Il
    residuo corto resta sull'Over (nessun ordine nuovo nato da un centesimo)."""
    punta = gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 6.6, 2.26,
                  ref="over_cover-0-3")
    banca = gamba("over_close", E.MARKET_OU45, E.SEL_OVER, "lay", 21.0, 0.72,
                  ref="over_close-0-4")
    w, l = E.exposure([punta, banca], E.MARKET_OU45, E.SEL_OVER)
    assert w - l < -E._FLAT_EPS           # corto sull'Over
    assert E.open_selections([punta, banca]) == [(E.MARKET_OU45, E.SEL_OVER)]


# ---------------------------------------------------------------------------
# test 3 del progetto: rientro dopo la copertura-banca
# ---------------------------------------------------------------------------
def _snap_rientro() -> E.Snapshot:
    books = {
        (E.MARKET_OU35, E.SEL_UNDER): E.Book(best_back=1.30, back_size=500.0,
                                             best_lay=1.31, lay_size=500.0,
                                             inplay=True),
        (E.MARKET_OU45, E.SEL_UNDER): E.Book(best_back=1.30, back_size=500.0,
                                             best_lay=1.31, lay_size=500.0,
                                             inplay=True),
        (E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=4.0, back_size=500.0,
                                            best_lay=4.1, lay_size=500.0,
                                            inplay=True),
    }
    return E.Snapshot(now=KO + 1800, ko_at=KO, books=books, inplay=True, minute=30,
                      goals=1, feed_fresh=True, order_fresh=True)


def test_rientro_dopo_la_copertura_banca_green_sul_solo_rientro():
    rientro = gamba("reentry", E.MARKET_OU45, E.SEL_UNDER, "back", 1.30, 10.0,
                    ref="reentry-0-5")
    ctx = E.MatchCtx(state="REENTRY_PENDING",
                     legs=[copertura_banca(), chiusura_banca_over(), rientro])
    d = E._decide_reentry_pending(ctx, _snap_rientro(), PAR, COMM)
    assert d.state == "REENTRY_OPEN"
    assert len(d.actions) == 1
    a = d.actions[0]
    assert (a.role, a.selection, a.side) == ("reentry_green", E.SEL_UNDER, "lay")
    # dimensionata sul rientro (13,00 di sbilancio) piu' il resto di
    # arrotondamento della chiusura (0,0066): mai sulla banca della copertura
    target = E.green_target(1.30, int(PAR["reentry_green_ticks"]))
    assert a.size == round(13.0066 / target, 2)
    # abbinata la green: nessuna banca Over nuda, il mercato e' piatto su ogni totale
    green = gamba("reentry_green", E.MARKET_OU45, E.SEL_UNDER, "lay", a.price, a.size,
                  ref="reentry_green-0-6")
    dist = E.net_pnl_by_total(ctx.legs + [green], COMM)
    assert max(dist.values()) - min(dist.values()) < 0.05
    assert E.open_selections(ctx.legs + [green]) == []


# ---------------------------------------------------------------------------
# test 4 del progetto: closes_ref per ruolo sull'intero mercato
# ---------------------------------------------------------------------------
def test_la_chiusura_banca_over_sa_quale_copertura_chiude():
    cop = copertura_banca()
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[ingresso(), cop])
    d = E.Decision("LIVE_CLOSING", [E.Action(kind="place", role="over_close",
                                             market=E.MARKET_OU45, selection=E.SEL_OVER,
                                             side="lay", price=21.0, size=0.71)], "x")
    nuove = E.apply_decision(ctx, d, KO + 10)
    assert nuove[0].closes_ref == cop.ref


def test_la_green_del_rientro_chiude_il_rientro_non_la_copertura():
    cop = copertura_banca()
    rientro = gamba("reentry", E.MARKET_OU45, E.SEL_UNDER, "back", 1.30, 10.0,
                    ref="reentry-0-5")
    legs = [ingresso(), cop, chiusura_banca_over(), rientro]
    assert E.opening_ref(legs, E.MARKET_OU45, E.SEL_UNDER, "reentry_green") == "reentry-0-5"
    assert E.opening_ref(legs, E.MARKET_OU45, E.SEL_OVER, "over_close") == cop.ref
    assert E.opening_ref(legs, E.MARKET_OU35, E.SEL_UNDER, "under_close") == "under_entry-0-1"


# ---------------------------------------------------------------------------
# test 5 del progetto: capitale impegnato
# ---------------------------------------------------------------------------
def test_capitale_impegnato_conta_il_rischio_della_banca():
    assert E.invested([ingresso(), copertura_banca()]) == 12.27
    cicli = E.riepilogo_cicli([ingresso(), copertura_banca()], COMM)
    assert cicli[0]["stake"] == 12.27 and cicli[0]["prezzo_ingresso"] == 1.5


def test_liability_room_usa_il_capitale_impegnato():
    ctx = E.MatchCtx(legs=[ingresso(), copertura_banca()])
    assert E.liability_room(ctx, dict(PAR, max_liability_per_match=20.0)) == pytest.approx(7.73)


# ---------------------------------------------------------------------------
# test 8 del progetto: copertura in volo sul MERCATO
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("stato", ["pending", E.STATUS_RECONCILE])
def test_punta_over_vecchia_in_volo_ferma_la_banca_under_nuova(stato):
    vecchia = gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 6.6, 0.0,
                    ref="over_cover-0-3", status=stato, size=2.26)
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", legs=[ingresso(), vecchia])
    nuova = E.Action(kind="place", role="over_cover", market=E.MARKET_OU45,
                     selection=E.SEL_UNDER, side="lay", price=1.20, size=12.63)
    d = E.Decision("LIVE_COVER_PENDING",
                   [E.Action(kind="cancel", ref=vecchia.ref, role="over_cover"), nuova],
                   "riprezzo")
    fuori = E._mai_sovracopertura(ctx, d)
    assert [a.kind for a in fuori.actions] == ["cancel"]


# ---------------------------------------------------------------------------
# test 9 del progetto: UNA banca per mercato
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("stato", ["pending", E.STATUS_RECONCILE])
def test_banca_over_di_chiusura_aspetta_la_banca_under_in_volo(stato):
    ctx = E.MatchCtx(state="LIVE_COVERED",
                     legs=[ingresso(), copertura_banca(abbinato=6.0, status=stato)])
    chiusura = E.Action(kind="place", role="over_close", market=E.MARKET_OU45,
                        selection=E.SEL_OVER, side="lay", price=21.0, size=0.34)
    fuori = E._una_sola_lay(ctx, E.Decision("LIVE_CLOSING", [chiusura], "cash out"))
    assert [a for a in fuori.actions if a.kind == "place"] == []
    assert fuori.state == "LIVE_COVERED"


def test_chiusura_manuale_aspetta_la_banca_under_a_esito_ignoto():
    """Cash out dell'utente: la banca Over che annulla la copertura non parte
    mentre la banca Under della copertura e' a esito ignoto (mai due banche sullo
    stesso mercato)."""
    ignota = copertura_banca(abbinato=12.63, status=E.STATUS_RECONCILE)
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[ignota], flatten_pending=True)
    s = _snap_rientro()
    d = E._decide_flatten(ctx, s, PAR)
    assert [a for a in d.actions if a.kind == "place"] == []
    assert "mai due lay a mercato" in d.reason


def test_la_chiusura_annulla_la_copertura_viva_sull_altra_selezione():
    viva = copertura_banca(abbinato=6.0, status="pending")
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[ingresso(), viva])
    # 01/10: Over 4,5 a 7 (era 21). A 21 la banca di chiusura valeva 0,34, sotto
    # il minimo della banca (1,00): oggi non parte (``engine.via_ordine``) e con
    # lei non parte l'annullo. A 7 vale 1,01: la regola provata qui (si annulla la
    # copertura viva prima di chiudere) resta la stessa.
    books = {
        (E.MARKET_OU35, E.SEL_UNDER): E.Book(best_back=1.30, back_size=500.0,
                                             best_lay=1.31, lay_size=500.0),
        (E.MARKET_OU45, E.SEL_OVER): E.Book(best_back=6.8, back_size=500.0,
                                            best_lay=7.0, lay_size=500.0),
    }
    cv = E.cashout_value(ctx.legs, books, COMM)
    azioni = E._close_actions(ctx, cv, PAR)
    assert any(a.kind == "cancel" and a.ref == viva.ref for a in azioni)


# ---------------------------------------------------------------------------
# test 13 del progetto: il conto controlla la selezione Under 4,5
# ---------------------------------------------------------------------------
class _DbFinto:
    def __init__(self) -> None:
        self.log_scritti: List[tuple] = []

    def trades_for_event(self, event_id: str, **_kw) -> List[dict]:
        return []

    def log(self, kind: str, payload: dict, event_id: Optional[str] = None) -> None:
        self.log_scritti.append((kind, dict(payload)))


def _ordine(*, ref: str, side: str, abbinato: float, market_id: str,
            selection_id: int, prezzo: float, bet_id: str) -> Dict[str, Any]:
    return {
        "bet_id": bet_id, "market_id": market_id, "selection_id": selection_id,
        "side": side, "status": "EXECUTION_COMPLETE", "size_matched": abbinato,
        "avg_price_matched": prezzo, "size_remaining": 0.0,
        "customer_order_ref": ref, "size_cancelled": 0.0, "size_lapsed": 0.0,
        "size_voided": 0.0, "matched_date": "2026-09-29T19:00:00Z",
        "placed_date": "2026-09-29T18:59:00Z", "price_requested": prezzo,
        "size_requested": abbinato, "average_price_matched": prezzo,
    }


class _MercatoConto:
    def __init__(self, morti: List[dict]) -> None:
        self.morti = morti
        self.letture: List[str] = []

    def list_account_orders(self, market_id: str) -> List[dict]:
        self.letture.append(f"vivi:{market_id}")
        return []

    def list_account_cleared_orders(self, market_id: str) -> List[dict]:
        self.letture.append(f"morti:{market_id}")
        return [o for o in self.morti if str(o["market_id"]) == str(market_id)]

    def cancel_order_live(self, bet_id: str, market_id: str, size_reduction=None):
        from Betfair.omega.omega_market import CancelResult
        return CancelResult(ok=True, status="SUCCESS", bet_id=str(bet_id),
                            size_cancelled=0.0, error_code=None, riletto=True,
                            size_matched=0.0, avg_price_matched=None,
                            size_remaining=0.0, raw={})


def test_il_conto_controlla_la_banca_under_della_copertura(monkeypatch):
    """L'utente chiude la copertura dal sito (punta Under 4,5 12,63): con la
    chiave del mercato sull'Over (atteso 0) l'Under non si controllava mai."""
    monkeypatch.setattr(S, "_trade_row_for_leg", lambda db, eid, leg, cache=None: None)
    S._CONTO_LETTO_A.clear()
    ev = {"event_id": "E1", "event_name": "A v B", "state": "LIVE_COVERED",
          "markets": {E.MARKET_OU35: {"market_id": "1.35"},
                      E.MARKET_OU45: {"market_id": "1.45"}}}
    extra = {"selections": {f"{E.MARKET_OU35}|{E.SEL_UNDER}": 47999,
                            f"{E.MARKET_OU45}|{E.SEL_UNDER}": 1222344,
                            f"{E.MARKET_OU45}|{E.SEL_OVER}": 1222345}}
    mercato = _MercatoConto(morti=[
        _ordine(ref="under_entry-0-1", side="back", abbinato=10.0, market_id="1.35",
                selection_id=47999, prezzo=1.5, bet_id="B1"),
        _ordine(ref="over_cover-0-3", side="lay", abbinato=12.63, market_id="1.45",
                selection_id=1222344, prezzo=1.18, bet_id="B2"),
        _ordine(ref="utente-1", side="back", abbinato=12.63, market_id="1.45",
                selection_id=1222344, prezzo=1.06, bet_id="U1"),
    ])
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[ingresso(), copertura_banca()])
    db = _DbFinto()
    try:
        chiuso = S._sorveglia_posizione_di_conto(
            db=db, market=mercato, ctx=ctx, ev=ev, extra=extra, params=PAR,
            mode="live", now_ts=KO + 1000.0)
    finally:
        S._CONTO_LETTO_A.clear()
    assert chiuso is True and ctx.chiuso_dall_utente is True
    sel = [d for k, p in db.log_scritti if k == "chiuso_dall_utente" for d in p["selezioni"]]
    assert [(d["mercato"], d["selezione"], d["atteso"]) for d in sel] == [
        (E.MARKET_OU45, E.SEL_UNDER, -12.63)]


def test_selezioni_da_sorvegliare_forma_di_oggi_invariata():
    punta = gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 6.6, 2.26,
                  ref="over_cover-0-3")
    assert E.selezioni_da_sorvegliare([ingresso(), punta]) == [
        (E.MARKET_OU35, E.SEL_UNDER), (E.MARKET_OU45, E.SEL_OVER)]
