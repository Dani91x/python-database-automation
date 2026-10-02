"""PIANO MIKE 29/09, P5 blocco 4: i controlli del banco ricalibrati per la
copertura come BANCA Under 4,5 (E2, J6, S2) e il controllo nuovo J5B (una sola
banca per MERCATO sul 4,5). Ogni controllo si prova in tutte e due le
direzioni: tace sul comportamento giusto, parla su quello sbagliato, e ha un
caso (sollecitato) quando deve averlo.

Finti: oggetti veri dell'engine; ``CERT.verifica`` vero.
"""
from __future__ import annotations

from typing import Dict, Optional

from Betfair.mike import certificazione as CERT
from Betfair.mike import config as C
from Betfair.mike import engine as E

KO = 1_800_000_000.0


def params(**over):
    p = C.merge_params(None)
    p["cover_form"] = E.COVER_LAY_U45
    p.update(over)
    return p


def gamba(role, market, selection, side, prezzo, abbinato, *, ref, status="open",
          size: Optional[float] = None) -> E.Leg:
    return E.Leg(role=role, market=market, selection=selection, side=side, price=prezzo,
                 size=abbinato if size is None else size, matched=abbinato,
                 avg_price=prezzo if abbinato > 0 else None, ref=ref, status=status,
                 placed_at=KO)


def ingresso():
    return gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 10.0,
                 ref="under_entry-0-1")


def libro(bb, bl, status="OPEN"):
    return E.Book(best_back=bb, back_size=500.0, best_lay=bl, lay_size=500.0,
                  status=status, inplay=True)


def foto(u45_status="OPEN", o45_status="OPEN"):
    books = {(E.MARKET_OU35, E.SEL_UNDER): libro(1.45, 1.46),
             (E.MARKET_OU45, E.SEL_UNDER): libro(1.17, 1.18, u45_status),
             (E.MARKET_OU45, E.SEL_OVER): libro(6.6, 6.8, o45_status)}
    return E.Snapshot(now=KO + 1200, ko_at=KO, books=books, inplay=True, minute=20,
                      goals=0, feed_fresh=True, order_fresh=True)


def banca(size, price=1.20):
    return E.Action(kind="place", role="over_cover", market=E.MARKET_OU45,
                    selection=E.SEL_UNDER, side="lay", price=price, size=size)


def _viola(ctx, d, codice, p=None, snap=None):
    sollecitati: Dict[str, int] = {}
    v = CERT.verifica(ctx, snap or foto(), d, p or params(), sollecitati)
    return sollecitati.get(codice, 0), [x for x in v if x.codice == codice]


# ---------------------------------------------------------------------------
# E2 sulla banca: verifica l'IMPORTO (12,63), non solo il tetto
# ---------------------------------------------------------------------------
def test_E2_banca_giusta_tace_con_un_caso():
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()])
    n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [banca(12.63)], "cop"), "E2")
    assert n == 1 and v == []


def test_E2_banca_sbagliata_parla():
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()])
    for sbagliata in (12.00, 13.50, 2.26):           # lettura B, gonfiata, forma di prima
        n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [banca(sbagliata)], "cop"), "E2")
        assert n == 1 and len(v) == 1, sbagliata
        assert "12.63" in v[0].dettaglio


def test_E2_banca_ridotta_dal_tetto_e_giusta():
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()])
    n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [banca(10.0)], "cop"), "E2",
                  p=params(max_liability_per_match=12.0))
    assert n == 1 and v == []
    # senza tetto la stessa banca ridotta e' un errore
    n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [banca(10.0)], "cop"), "E2")
    assert len(v) == 1
    # con un tetto che NON la tiene fuori (spazio 10 > rischio 2,53) e' un errore
    n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [banca(10.0)], "cop"), "E2",
                  p=params(max_liability_per_match=20.0))
    assert len(v) == 1


# ---------------------------------------------------------------------------
# J6 sulla banca: il residuo e' quello della banca, non della punta
# ---------------------------------------------------------------------------
def test_J6_banca_intera_tace():
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()])
    n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [banca(12.63)], "cop"), "J6")
    assert n == 1 and v == []


def test_J6_banca_oltre_il_residuo_e_sovracopertura():
    gia = gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.18, 9.47,
                ref="over_cover-0-2")
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso(), gia])
    n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [banca(12.63)], "cop"), "J6")
    assert n == 1 and len(v) == 1 and "residuo previsto di 3.16" in v[0].dettaglio


# ---------------------------------------------------------------------------
# S2 sul libro della copertura: con la banca e' l'Under 4,5
# ---------------------------------------------------------------------------
def test_S2_banca_su_under_sospeso_parla():
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()])
    n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [banca(12.63)], "cop"), "S2",
                  snap=foto(u45_status="SUSPENDED"))
    assert n == 1 and len(v) == 1 and "Under 4.5" in v[0].dettaglio


def test_S2_il_caso_segue_la_forma_scelta_senza_ordini():
    """Senza ordini ne' gambe di copertura il libro e' quello della forma scelta:
    banca -> l'Under 4,5 sospeso e' un caso; punta -> no."""
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()])
    n, _v = _viola(ctx, E.Decision("LIVE_UNCOVERED", [], "attesa"), "S2",
                   snap=foto(u45_status="SUSPENDED"))
    assert n == 1
    n2, _v2 = _viola(ctx, E.Decision("LIVE_UNCOVERED", [], "attesa"), "S2",
                     p=params(cover_form=E.COVER_BACK_O45), snap=foto(u45_status="SUSPENDED"))
    assert n2 == 0


def test_S2_l_ordine_proposto_decide_il_libro():
    """Forma scelta = punta, ma l'ordine proposto e' una banca Under (per esempio
    appena dopo un cambio di forma): conta il libro dell'ORDINE."""
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()])
    n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [banca(12.63)], "cop"), "S2",
                  p=params(cover_form=E.COVER_BACK_O45), snap=foto(u45_status="SUSPENDED"))
    assert n == 1 and len(v) == 1


def test_S2_banca_con_over_sospeso_ma_under_aperto_non_e_un_caso():
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()])
    n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [banca(12.63)], "cop"), "S2",
                  snap=foto(o45_status="SUSPENDED"))
    assert n == 0 and v == []


# ---------------------------------------------------------------------------
# J5B: una sola banca per MERCATO sul 4,5
# ---------------------------------------------------------------------------
def test_J5B_banca_over_mentre_la_banca_under_e_in_volo():
    viva = gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.20, 0.0,
                 ref="over_cover-0-2", status="pending", size=12.63)
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[ingresso(), viva])
    chiusura = E.Action(kind="place", role="over_close", market=E.MARKET_OU45,
                        selection=E.SEL_OVER, side="lay", price=21.0, size=0.71)
    n, v = _viola(ctx, E.Decision("LIVE_CLOSING", [chiusura], "cash out"), "J5B")
    assert n == 1 and len(v) == 1
    n5, v5 = _viola(ctx, E.Decision("LIVE_CLOSING", [chiusura], "cash out"), "J5")
    assert v5 == []                    # J5 guarda la selezione: qui non vedeva niente


def test_J5B_due_banche_in_volo_sulle_due_selezioni():
    a = gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.20, 0.0,
              ref="over_cover-0-2", status="pending", size=12.63)
    b = gamba("over_close", E.MARKET_OU45, E.SEL_OVER, "lay", 21.0, 0.0,
              ref="over_close-0-3", status=E.STATUS_RECONCILE, size=0.71)
    ctx = E.MatchCtx(state="LIVE_CLOSING", legs=[ingresso(), a, b])
    n, v = _viola(ctx, E.Decision("LIVE_CLOSING", [], "attesa"), "J5B")
    assert n == 1 and len(v) == 1


def test_chiusura_manuale_in_gioco_aspetta_la_riapertura():
    """Reperto dello scenario `cashout-dopo-copertura` (C3 x3): il cash out
    dell'utente in gioco piazzava la chiusura anche a mercato SOSPESO. Ora si
    aspetta; alla riapertura la chiusura parte (punta Under 4,5, decisione 12
    dell'utente del 02/10; prima banca Over, M3.3)."""
    cop = gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.18, 12.63,
                ref="over_cover-0-2")
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[cop], flatten_pending=True)
    d = E._decide_flatten(ctx, foto(u45_status="SUSPENDED", o45_status="SUSPENDED"), params())
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.state == "LIVE_COVERED" and "attendo la riapertura" in d.reason
    d2 = E._decide_flatten(ctx, foto(), params())
    # 02/10 (decisione 12 dell'utente, supera M3.3): la chiusura della
    # copertura-banca e' la PUNTA Under 4,5 di serie (prima: banca Over)
    assert [(a.role, a.selection, a.side) for a in d2.actions if a.kind == "place"] == [
        ("manual_close", E.SEL_UNDER, "back")]


def test_J5B_tace_con_una_banca_sola_e_senza_banche_sul_4_5():
    viva = gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.20, 0.0,
                 ref="over_cover-0-2", status="pending", size=12.63)
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", legs=[ingresso(), viva])
    n, v = _viola(ctx, E.Decision("LIVE_COVER_PENDING", [], "attesa"), "J5B")
    assert n == 1 and v == []
    n0, v0 = _viola(E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()]),
                    E.Decision("LIVE_UNCOVERED", [], "attesa"), "J5B")
    assert n0 == 0 and v0 == []
