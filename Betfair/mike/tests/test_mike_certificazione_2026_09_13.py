"""CERTIFICAZIONE 13/09/2026 — i difetti trovati, e la prova che non tornano.

Nessuna rete, nessun DB. File ASCII-only (console Windows cp1252).

Ogni test qui nasce da un controesempio ESEGUITO durante la certificazione che
ha preceduto il passaggio in produzione, non da un'ipotesi. Accanto a ognuno c'e'
la conseguenza misurata in euro: e' quella che il test impedisce di rivedere.
"""
from __future__ import annotations

import math

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E

KO = 1_800_000_000.0
COMM = 0.05


def params(**o):
    p = C.merge_params(None)
    p.update(o)
    return p


def book(bb, bs=500.0, bl=None, ls=500.0, inplay=True, status="OPEN"):
    if bl is None:
        bl = E.ticks_away(bb, 1)
    return E.Book(best_back=bb, back_size=bs, best_lay=bl, lay_size=ls,
                  status=status, inplay=inplay)


def snap(now=KO + 600, u35=None, o45=None, u45=None, inplay=True, minute=10, goals=0,
         stato="OPEN", finale=None, gol_ts=None, model=None):
    b = {}
    if u35 is not None:
        b[(E.MARKET_OU35, E.SEL_UNDER)] = u35
    if o45 is not None:
        b[(E.MARKET_OU45, E.SEL_OVER)] = o45
    if u45 is not None:
        b[(E.MARKET_OU45, E.SEL_UNDER)] = u45
    return E.Snapshot(now=now, ko_at=KO, books=b, inplay=inplay, minute=minute, goals=goals,
                      market_status=stato, final_total=finale, last_goal_ts=gol_ts,
                      model_probs=model)


def gamba(role, mkt, sel, side, price, size, matched=None, **kw):
    l = E.Leg(role=role, market=mkt, selection=sel, side=side, price=price, size=size, **kw)
    if matched is None:
        matched = size
    if matched > 0:
        l.matched, l.avg_price = float(matched), float(price)
        if l.status == "pending":
            l.status = "open"
    return l


# ===========================================================================
# 1 — MAI due ordini vivi nella stessa direzione sulla stessa selezione
# ===========================================================================
class TestDoppiaLaySullaStessaSelezione:
    """Misurato: -9,39 EUR su 10 di stake, e sull'esito PIU' probabile.

    Il caso reale: la lay di green-up del ciclo pre-match ha gia' ricevuto il
    cancel, ma l'exchange non l'ha ancora confermato. Il cash-out appoggia la
    sua lay di chiusura. Se abbinano ENTRAMBE, 22,23 EUR di lay contro 10 di
    back: la posizione si ribalta da back netto a lay netto.
    """

    def ctx_con_lay_viva(self):
        c = E.MatchCtx(state="LIVE_COVERED", cycle_no=1, entry_price_initial=2.00)
        c.legs.append(gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 2.00, 10.0, ref="e1"))
        c.legs.append(gamba("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.90, 10.53,
                            matched=0, ref="g1", status="pending"))
        c.legs.append(gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.00, 1.50, ref="c1"))
        return c

    def test_la_chiusura_annulla_prima_le_lay_gia_vive(self):
        ctx = self.ctx_con_lay_viva()
        s = snap(u35=book(1.70, bl=1.71), o45=book(8.0, bl=8.2))
        d = E.decide(ctx, s, params())
        assert d.state == "LIVE_CLOSING"
        annullate = [a.ref for a in d.actions if a.kind == "cancel"]
        assert "g1" in annullate, "la lay viva deve essere annullata PRIMA di appoggiarne un'altra"
        # e l'annullamento viene prima del piazzamento
        kinds = [a.kind for a in d.actions]
        assert kinds.index("cancel") < kinds.index("place")

    def test_quanto_costerebbe_il_doppio_abbinamento(self):
        """Il numero che giustifica la guardia: si misura, non si immagina."""
        ctx = self.ctx_con_lay_viva()
        solo_chiusura = list(ctx.legs)
        solo_chiusura[1] = gamba("under_close", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.71, 11.70,
                                 ref="x1")
        atteso = E.net_pnl_by_total(solo_chiusura, COMM)[0]
        doppia = list(ctx.legs)
        doppia[1] = gamba("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.90, 10.53, ref="g1")
        doppia.append(gamba("under_close", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.71, 11.70, ref="x1"))
        disastro = E.net_pnl_by_total(doppia, COMM)[0]
        assert atteso > 0 and disastro < 0
        assert atteso - disastro > 9.0, "la guardia vale quasi uno stake intero"

    def test_gli_ordini_vivi_si_leggono_per_selezione(self):
        ctx = self.ctx_con_lay_viva()
        vive = E.ordini_vivi_su(ctx, E.MARKET_OU35, E.SEL_UNDER)
        assert [l.ref for l in vive] == ["g1"]
        assert E.ordini_vivi_su(ctx, E.MARKET_OU35, E.SEL_UNDER, escludi=("under_green",)) == []
        assert E.ordini_vivi_su(ctx, E.MARKET_OU45, E.SEL_OVER) == []


# ===========================================================================
# 2 — un ordine a esito IGNOTO non si regola e non si archivia
# ===========================================================================
class TestOrdineAEsitoIgnoto:
    """Misurato: `settled_pnl` sbagliato di 133 EUR su un cover da 20.

    ``settle_legs`` conta solo l'abbinato: una gamba che POTREBBE essere viva su
    Betfair esce "void 0,00". Il regolamento quindi dichiara un numero falso, e
    lo stop giornaliero e lo storico ci credono.
    """

    def ctx_ignoto(self):
        c = E.MatchCtx(state="SETTLING", cycle_no=0)
        c.legs.append(gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 10.0, ref="e1"))
        c.legs.append(gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 20.0,
                            matched=0, ref="r1", status=E.STATUS_RECONCILE))
        return c

    def test_il_regolamento_si_ferma_e_lo_dichiara(self):
        ctx = self.ctx_ignoto()
        d = E.decide(ctx, snap(stato="CLOSED", finale=6), params())
        assert d.state == "SETTLING"
        assert "esito ignoto" in d.reason
        assert d.telemetry["settle_bloccato"]["critical"] is True
        assert d.telemetry["settle_bloccato"]["gambe"] == ["r1"]

    def test_senza_la_guardia_il_conto_sarebbe_falso(self):
        """Quanto vale il difetto: la stessa posizione, con e senza l'ordine."""
        ctx = self.ctx_ignoto()
        dichiarato = E.settle_legs(ctx.legs, 6, COMM).net
        reali = [l for l in ctx.legs[:1]] + [
            gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 20.0, ref="r1")]
        se_abbinato = E.settle_legs(reali, 6, COMM).net
        assert abs(se_abbinato - dichiarato) > 100.0

    def test_ne_si_archivia_la_partita_a_zero(self):
        """`pnl_indipendente_dal_risultato` diceva 0,00 e il servizio chiudeva la
        scheda: una posizione forse VIVA data per inesistente."""
        ctx = self.ctx_ignoto()
        assert E.pnl_indipendente_dal_risultato(ctx.legs, COMM) is None
        # senza la gamba ignota resta il comportamento buono
        assert E.pnl_indipendente_dal_risultato([], COMM) == 0.0

    def test_il_rischio_dell_ordine_ignoto_e_dichiarato_per_INTERO(self):
        """Un solo centesimo gia' abbinato NASCONDEVA il resto: 99 EUR su 100
        dichiarati zero rischio."""
        parziale = [gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 100.0,
                          matched=1.0, ref="p1", status=E.STATUS_RECONCILE)]
        assert E.event_liability(parziale, COMM) == pytest.approx(100.0, abs=0.01)
        nulla = [gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 100.0,
                       matched=0, ref="p2", status=E.STATUS_RECONCILE)]
        assert E.event_liability(nulla, COMM) == pytest.approx(100.0, abs=0.01)


# ===========================================================================
# 3 — se l'apertura viene tolta, lo STATO non avanza
# ===========================================================================
class TestAperturaTolta:
    """Misurato: 13,50 EUR su 20 di stake con 5+ gol, e senza nessun allarme.

    Con un ordine a esito ignoto la seconda tranche di copertura veniva tolta,
    ma lo stato passava lo stesso a "copertura in corso". Al giro dopo il motore
    trovava la PRIMA tranche (abbinata) e concludeva "copertura abbinata",
    azzerando la fase: il residuo non veniva mai comprato.
    """

    def test_lo_stato_resta_quello_di_prima(self):
        d = E.Decision("LIVE_COVER_PENDING", [
            E.Action(kind="place", role="over_cover", market=E.MARKET_OU45,
                     selection=E.SEL_OVER, side="back", price=8.0, size=2.0)],
            "seconda tranche", updates={"cover_stage": 3})
        potata = E._strip_openings(d, "ordine ignoto", "LIVE_UNCOVERED")
        assert potata.state == "LIVE_UNCOVERED", "senza ordini da piazzare lo stato NON avanza"
        assert potata.actions == []
        assert potata.updates == {}, "e nemmeno gli aggiornamenti di stato"

    def test_ma_le_chiusure_fanno_avanzare_lo_stato(self):
        """Chiudere RIDUCE il rischio: quella strada resta sempre aperta."""
        d = E.Decision("LIVE_CLOSING", [
            E.Action(kind="place", role="over_cover", market=E.MARKET_OU45,
                     selection=E.SEL_OVER, side="back", price=8.0, size=2.0),
            E.Action(kind="place", role="under_close", market=E.MARKET_OU35,
                     selection=E.SEL_UNDER, side="lay", price=1.4, size=11.0)],
            "chiudo", updates={"close_reason": "profit"})
        potata = E._strip_openings(d, "ordine ignoto", "LIVE_COVERED")
        assert potata.state == "LIVE_CLOSING"
        assert [a.role for a in potata.actions] == ["under_close"]
        assert potata.updates["close_reason"] == "profit"

    def test_niente_da_potare_niente_da_cambiare(self):
        d = E.Decision("LIVE_COVERED", [], "tengo")
        assert E._strip_openings(d, "x", "ALTRO") is d


# ===========================================================================
# 5 — la seconda tranche parte anche senza l'orologio
# ===========================================================================
def test_seconda_tranche_senza_orologio_parte_subito():
    """Senza ``cover_stage1_at`` la condizione non si avverava MAI e la partita
    restava coperta a meta' fino al fischio finale."""
    ctx = E.MatchCtx(state="LIVE_COVERED", cycle_no=1, cover_stage=2, cover_stage1_at=None,
                     entry_price_initial=1.50)
    ctx.legs.append(gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 15.0, ref="e1"))
    ctx.legs.append(gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 8.0, 0.90, ref="c1"))
    d = E.decide(ctx, snap(u35=book(1.60, bl=1.61), o45=book(8.0, bl=8.2), goals=1), params())
    assert d.state == "LIVE_UNCOVERED"
    assert d.updates["cover_stage"] == 3


# ===========================================================================
# 6 — il flatten non archivia una posizione ancora esposta
# ===========================================================================
def test_flatten_non_archivia_una_perdita_gia_certa():
    """Misurato: 30 EUR di perdita certa spariti dalla liability, e il tetto per
    partita che si riapriva per un capitale che non c'era.

    Con 4 gol l'Under 3.5 e' perso e sparisce dal filtro delle selezioni "ancora
    in gioco", ma la gamba e' a mercato e la perdita e' reale.
    """
    ctx = E.MatchCtx(state="LIVE_COVERED", flatten_pending=True, cycle_no=0)
    ctx.legs.append(gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 30.0, ref="e1"))
    d = E.decide(ctx, snap(goals=4, u35=None, o45=None), params())
    assert d.state == "FLAT"
    assert "_archive_legs" not in d.updates, "archiviarla farebbe sparire 30 EUR di perdita certa"
    E.apply_decision(ctx, d, KO + 600)
    assert all(not l.archived for l in ctx.legs)
    assert E.invested(ctx.legs) == pytest.approx(30.0)


# ===========================================================================
# 7 — la copertura ordinata aspetta comunque il riprezzo dopo il gol
# ===========================================================================
def test_la_copertura_ordinata_non_compra_nei_secondi_del_gol():
    """Misurato: 3,16 EUR invece di ~2,10 su 10 di stake. Nei secondi del gol la
    quota dell'Over crolla: comprare li' paga il differenziale pieno."""
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", cycle_no=1, cover_forced=True,
                     entry_price_initial=1.50, live_since=KO + 1, ko_goals=0)
    ctx.legs.append(gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 10.0, ref="e1"))
    p = params()
    subito = snap(now=KO + 305, u35=book(1.95), o45=book(5.0), minute=5, goals=1,
                  gol_ts=KO + 300)
    d = E.decide(ctx, subito, p)
    assert d.state == "LIVE_UNCOVERED", "nei primi 45 s dal gol non si compra"
    dopo = snap(now=KO + 350, u35=book(1.95), o45=book(7.0), minute=5, goals=1, gol_ts=KO + 300)
    d2 = E.decide(ctx, dopo, p)
    assert d2.state == "LIVE_COVER_PENDING"


# ===========================================================================
# 8 e 9 — numeri che non devono mai diventare quote o scarti
# ===========================================================================
def test_una_probabilita_rotta_non_diventa_una_quota():
    """``NaN <= 0`` e' False e ``min(1000, NaN)`` da' 1000: una probabilita'
    rotta faceva sembrare la selezione MORTA, e il cash-out intelligente
    chiudeva in anticipo su un valore atteso inventato."""
    books = {(E.MARKET_OU35, E.SEL_UNDER): book(1.5),
             (E.MARKET_OU45, E.SEL_OVER): book(5.0)}
    for rotto in (float("nan"), float("inf"), -0.2, 0.0, 1.5, None, "molto"):
        probs = {"u35_now": rotto, "u35_goal": 0.5, "o45_now": 0.2, "o45_goal": 0.3}
        assert E.projected_books(books, probs, "goal") is None, rotto
    buone = {"u35_now": 0.8, "u35_goal": 0.5, "o45_now": 0.2, "o45_goal": 0.3}
    proiettati = E.projected_books(books, buone, "goal")
    assert proiettati is not None
    for bk in proiettati.values():
        assert math.isfinite(float(bk.best_back))

    assert E._prob_utilizzabile(0.5) is True
    assert E._prob_utilizzabile(1.0) is True
    for cattivo in (float("nan"), 0.0, -1, 1.0001, None, "x"):
        assert E._prob_utilizzabile(cattivo) is False, cattivo


def test_le_celle_del_cash_out_sommano_al_totale():
    """Chi somma con gli occhi deve trovare il numero dichiarato, al centesimo."""
    legs = [gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.53, 13.37, ref="a"),
            gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 7.77, 2.11, ref="b"),
            gamba("reentry", E.MARKET_OU45, E.SEL_UNDER, "back", 1.39, 3.33, ref="c")]
    books = {(E.MARKET_OU35, E.SEL_UNDER): book(1.31, bl=1.32),
             (E.MARKET_OU45, E.SEL_OVER): book(9.4, bl=9.6),
             (E.MARKET_OU45, E.SEL_UNDER): book(1.11, bl=1.12)}
    cv = E.cashout_value(legs, books, COMM, 0, goals=1)
    assert round(sum(cv.per_selection_net.values()), 2) == pytest.approx(cv.net, abs=0.001)
