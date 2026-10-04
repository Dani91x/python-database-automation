"""PIANO MIKE 29/09, pacchetto P5, blocco 2: la copertura come BANCA Under 4,5
(M3.1), il cuscinetto rovesciato (M3.2), la chiusura sotto 0,50 (M3.3), un
ordine solo senza rincorrere i resti (M3.5), l'interruttore ``cover_form``.
Piu' la correzione di un difetto gia' presente: il resto di arrotondamento di
una chiusura sul mercato 4,5 non tiene piu' la partita ferma
(``tolleranza_piatto_ou45``).

Numeri del piano (lettura A): punta Under 3,5 10,00 a 1,50 -> banca Under 4,5
12,63; a 1,18 rischio 2,27; esiti +2,48 / -12,27 / +2,00; limite 1,20. Due
tranche su 15 EUR: 9,47 e 9,48. Ogni test ha la sua mutazione
(``AUDIT_2026-09-29/mike_p5/falsifica_mike_p5_2.py``).

Finti: gli oggetti veri dell'engine (Leg, Book, Snapshot, MatchCtx, Decision).
"""
from __future__ import annotations

from typing import Optional

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E

KO = 1_800_000_000.0
COMM = 0.05


def params(**over):
    p = C.merge_params(None)
    p["uscite_automatiche"] = True
    p["cover_form"] = E.COVER_LAY_U45
    p["cover_policy"] = "immediate"
    p.update(over)
    return p


def gamba(role, market, selection, side, prezzo, abbinato, *, ref, status="open",
          size: Optional[float] = None) -> E.Leg:
    return E.Leg(role=role, market=market, selection=selection, side=side, price=prezzo,
                 size=abbinato if size is None else size, matched=abbinato,
                 avg_price=prezzo if abbinato > 0 else None, ref=ref, status=status,
                 placed_at=KO)


def ingresso(stake=10.0, prezzo=1.50, ruolo="under_entry", ref="under_entry-0-1"):
    return gamba(ruolo, E.MARKET_OU35, E.SEL_UNDER, "back", prezzo, stake, ref=ref)


def libro(bb, bl, bs=500.0, ls=500.0, status="OPEN"):
    return E.Book(best_back=bb, back_size=bs, best_lay=bl, lay_size=ls, status=status,
                  inplay=True)


def fotografia(now=KO + 1200, *, u45=True, u45_book=None, o45_book=None, goals=0,
               minute=20):
    books = {(E.MARKET_OU35, E.SEL_UNDER): libro(1.45, 1.46)}
    if u45:
        books[(E.MARKET_OU45, E.SEL_UNDER)] = u45_book or libro(1.17, 1.18)
    books[(E.MARKET_OU45, E.SEL_OVER)] = o45_book or libro(6.6, 6.8)
    return E.Snapshot(now=now, ko_at=KO, books=books, inplay=True, minute=minute,
                      goals=goals, feed_fresh=True, order_fresh=True)


def scoperta(*legs, **kw):
    return E.MatchCtx(state="LIVE_UNCOVERED", entry_price_initial=1.50,
                      legs=list(legs) or [ingresso()], **kw)


# ---------------------------------------------------------------------------
# test 1 e 6: esempio guida e cuscinetto
# ---------------------------------------------------------------------------
def test_esempio_guida_banca_under45_12_63_e_esiti():
    ctx = scoperta()
    d = E.decide(ctx, fotografia(), params())
    assert d.state == "LIVE_COVER_PENDING"
    [a] = [x for x in d.actions if x.kind == "place"]
    assert (a.role, a.market, a.selection, a.side) == ("over_cover", E.MARKET_OU45,
                                                       E.SEL_UNDER, "lay")
    assert a.size == 12.63
    # abbinata al miglior prezzo 1,18 (Betfair abbina al meglio sotto il limite)
    legs = ctx.legs + [gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.18, 12.63,
                             ref="over_cover-0-2")]
    dist = E.net_pnl_by_total(legs, COMM)
    assert (dist[3], dist[4], dist[5]) == (2.48, -12.27, 2.0)
    assert round(12.63 * 0.18, 2) == 2.27


def test_cuscinetto_due_tick_SOPRA_il_miglior_prezzo_di_banca():
    d = E.decide(scoperta(), fotografia(), params())
    [a] = [x for x in d.actions if x.kind == "place"]
    assert a.price == 1.20
    assert d.telemetry["cover"]["price_limite"] == 1.20
    assert d.telemetry["cover"]["rischio_al_limite"] == 2.53
    assert E.cover_place_price_lay(1.18, params(cover_place_at_ticks=0)) == 1.18


# ---------------------------------------------------------------------------
# test 7: due tranche su 15 EUR
# ---------------------------------------------------------------------------
def test_due_tranche_9_47_e_9_48():
    legs = [ingresso(), ingresso(5.0, 1.95, "under_second", "under_second-0-2")]
    ctx = scoperta(*legs, cover_stage=1, early_goal_at=KO + 600)
    d = E.decide(ctx, fotografia(now=KO + 1200, goals=1), params())
    [a] = [x for x in d.actions if x.kind == "place"]
    assert a.size == 9.47 and d.updates.get("cover_stage") == 1
    # prima tranche abbinata a 1,18; la seconda si ricalcola dai fill
    ctx.legs.append(gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.18, 9.47,
                          ref="over_cover-0-3"))
    ctx.state, ctx.cover_stage = "LIVE_UNCOVERED", 3
    d2 = E.decide(ctx, fotografia(now=KO + 1500, goals=1), params())
    [b] = [x for x in d2.actions if x.kind == "place"]
    assert b.size == 9.48


# ---------------------------------------------------------------------------
# test 10: M3.5, niente secondo ordine per un resto sotto 0,50
# ---------------------------------------------------------------------------
def test_resto_sotto_0_50_si_considera_coperto_senza_secondo_ordine():
    parziale = gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.18, 12.30,
                     ref="over_cover-0-2", size=12.63)
    ctx = scoperta(ingresso(), parziale)
    d = E.decide(ctx, fotografia(), params())
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.state == "LIVE_COVERED"
    assert d.telemetry["cover_resto_sotto_minimo"]["resto"] == 0.33


def test_riprezzo_con_resto_sotto_0_50_annulla_e_non_ripiazza():
    viva = gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.20, 12.30,
                 ref="over_cover-0-2", status="pending", size=12.63)
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", legs=[ingresso(), viva])
    d = E.decide(ctx, fotografia(now=KO + 5000), params())
    assert [a.kind for a in d.actions] == ["cancel"]
    assert d.state == "LIVE_COVERED"


def test_riprezzo_della_banca_ripiazza_il_residuo_al_limite_nuovo():
    viva = gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.20, 0.0,
                 ref="over_cover-0-2", status="pending", size=12.63)
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", legs=[ingresso(), viva])
    d = E._decide_cover_pending(ctx, fotografia(now=KO + 5000,
                                                u45_book=libro(1.20, 1.21)), params(), COMM)
    assert [a.kind for a in d.actions] == ["cancel", "place"]
    nuova = d.actions[1]
    assert (nuova.selection, nuova.side, nuova.size, nuova.price) == (E.SEL_UNDER, "lay",
                                                                      12.63, 1.23)


# ---------------------------------------------------------------------------
# test 11: libro Under 4,5 assente o senza prezzo di banca
# ---------------------------------------------------------------------------
def _under35_non_in_profitto(s):
    """04/10: Under 3,5 NON in profitto (banca = prezzo d'ingresso 1,50). Con la regola
    nuova, a copertura non eseguibile e Under 3,5 in profitto di 2 tick, Mike chiude
    l'Under (test dedicato): qui si prova l'ATTESA."""
    s.books[(E.MARKET_OU35, E.SEL_UNDER)] = libro(1.49, 1.50)
    return s


def test_libro_under45_assente_si_aspetta_col_motivo():
    d = E.decide(scoperta(), _under35_non_in_profitto(fotografia(u45=False)), params())
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.state == "LIVE_UNCOVERED" and "libro Under 4.5 assente" in d.reason


def test_nessun_prezzo_di_banca_sull_under45_si_aspetta():
    d = E.decide(scoperta(), _under35_non_in_profitto(fotografia(u45_book=libro(1.17, None))),
                 params())
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.telemetry["cover_wait"]["reason"] == "nessun_prezzo_lay_under45"


# ---------------------------------------------------------------------------
# liquidita' (regola dell'utente: tutto l'importo al miglior prezzo) e tetto
# ---------------------------------------------------------------------------
def test_liquidita_sotto_l_importo_al_miglior_prezzo_si_aspetta():
    d = E.decide(scoperta(),
                 _under35_non_in_profitto(fotografia(u45_book=libro(1.17, 1.18, ls=12.0))),
                 params())
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.telemetry["cover_wait"]["reason"] == "liquidita"


def test_tetto_per_partita_conta_il_rischio_non_l_importo():
    d = E.decide(scoperta(), fotografia(), params(max_liability_per_match=12.0))
    [a] = [x for x in d.actions if x.kind == "place"]
    assert a.size == 10.0          # spazio 2,00 / (1,20 - 1)
    # spazio 3,00: il rischio al limite (2,53) ci sta, l'importo (12,63) no:
    # conta il rischio, la banca resta intera
    d2 = E.decide(scoperta(), fotografia(), params(max_liability_per_match=13.0))
    [b] = [x for x in d2.actions if x.kind == "place"]
    assert b.size == 12.63


def test_la_banca_non_si_legalizza_come_una_puntata():
    d = E.decide(scoperta(), fotografia(), params(exact_sizes=False))
    [a] = [x for x in d.actions if x.kind == "place"]
    assert a.size == 12.63         # non 13,00 (passi da 0,50 solo per le puntate)


# ---------------------------------------------------------------------------
# test 12: interruttore sulla forma di prima = ordine identico a oggi
# ---------------------------------------------------------------------------
def test_interruttore_back_over45_ordine_identico_alla_forma_di_prima():
    ctx = scoperta(ingresso(20.0))
    s = fotografia(o45_book=libro(9.0, 9.2, bs=50))
    d_vecchia = E.decide(ctx, s, params(cover_form=E.COVER_BACK_O45))
    p_serie = params()
    p_serie.pop("cover_form")
    d_serie = E.decide(ctx, s, dict(p_serie, cover_form=C.merge_params(None)["cover_form"]))
    [a] = [x for x in d_vecchia.actions if x.kind == "place"]
    assert (a.selection, a.side) == (E.SEL_OVER, "back")
    assert a.price == float(E.ticks_away(9.0, -2))
    # 04/10 (regola delle punte .it): 3,16 esatto -> parte 3,00 (multiplo di 0,50 per
    # difetto); prima il test pretendeva il centesimo
    assert round(E.cover_size(20, 9.0, 0.05, 1.2), 2) == 3.16 and a.size == 3.00
    # di serie (dal blocco 5) la forma e' la BANCA Under 4,5
    [b] = [x for x in d_serie.actions if x.kind == "place"]
    assert (b.selection, b.side) == (E.SEL_UNDER, "lay")
    assert C.DEFAULTS["cover_form"] == E.COVER_LAY_U45


# ---------------------------------------------------------------------------
# M3.3: chiusura della copertura-banca sotto 0,50
# ---------------------------------------------------------------------------
def _cop_10_20():
    return gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.20, 10.20,
                 ref="over_cover-0-2")


def test_banca_over_sotto_0_50_diventa_puntata_under_se_piazzabile():
    legs = [_cop_10_20()]
    books = {(E.MARKET_OU45, E.SEL_OVER): libro(48.0, 50.0),
             (E.MARKET_OU45, E.SEL_UNDER): libro(1.02, 1.03)}
    cv = E.cashout_value(legs, books, COMM)
    assert cv.plans[(E.MARKET_OU45, E.SEL_OVER)].size == 0.24
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs)
    [a] = [x for x in E._close_actions(ctx, cv, params()) if x.kind == "place"]
    assert (a.role, a.selection, a.side, a.size, a.price) == ("over_close", E.SEL_UNDER,
                                                             "back", 12.0, 1.02)


def test_banca_over_sotto_0_50_diventa_puntata_under_a_multiplo_per_difetto():
    """Fino al 01/10 qui la chiusura restava la BANCA Over 0,24 perche' la
    puntata Under (11,88) non era multipla di 0,50. Ashdod v Maccabi Herzliya
    (LIVE, 01/10): quella banca Betfair la rifiuta (INVALID_BET_SIZE). 04/10
    (Umea, regola delle punte dell'utente; era
    ``..._anche_non_multipla_di_0_50`` con 11,88 al centesimo): resta la puntata,
    ma parte al multiplo di 0,50 per DIFETTO, 11,50; i 0,38 li dichiara il
    controllo di piatto."""
    legs = [_cop_10_20()]
    books = {(E.MARKET_OU45, E.SEL_OVER): libro(48.0, 50.0),
             (E.MARKET_OU45, E.SEL_UNDER): libro(1.03, 1.04)}
    cv = E.cashout_value(legs, books, COMM)
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs)
    [a] = [x for x in E._close_actions(ctx, cv, params()) if x.kind == "place"]
    assert (a.selection, a.side, a.size, a.price) == (E.SEL_UNDER, "back", 11.50, 1.03)


def test_riprezzo_della_chiusura_resta_puntata_a_multiplo():
    """La chiusura partita come puntata Under 12,00 non si abbina; al riprezzo la
    puntata e' 11,88. Fino al 01/10 (non multiplo di 0,50) si tornava alla banca
    Over 0,24, che Betfair .it rifiuta: resta la puntata. 04/10 (era
    ``..._resta_puntata_al_centesimo``): parte 11,50, multiplo di 0,50 per difetto."""
    ferma = gamba("over_close", E.MARKET_OU45, E.SEL_UNDER, "back", 1.02, 0.0,
                  ref="over_close-0-3", status="pending", size=12.0)
    ctx = E.MatchCtx(state="LIVE_CLOSING", legs=[_cop_10_20(), ferma], close_reason="profit")
    s = fotografia(now=KO + 5000, u45_book=libro(1.03, 1.04), o45_book=libro(48.0, 50.0))
    d = E._decide_closing(ctx, s, params(), COMM)
    assert [a.kind for a in d.actions] == ["cancel", "place"]
    nuova = d.actions[1]
    assert (nuova.role, nuova.selection, nuova.side, nuova.size) == ("over_close", E.SEL_UNDER,
                                                                     "back", 11.50)


def test_forma_di_prima_ripiego_solo_sotto_la_soglia_incerta_della_banca():
    """Fino al 01/10 la forma di prima non aveva ripiego. Dal 01/10 (minimo della
    banca incerto sotto 1,00, ricerca del coordinatore) la banca Over 0,24 diventa
    la puntata Under equivalente; una banca da 1,00 in su resta la banca."""
    punta = gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 6.0, 2.0,
                  ref="over_cover-0-2")
    books = {(E.MARKET_OU45, E.SEL_OVER): libro(48.0, 50.0),
             (E.MARKET_OU45, E.SEL_UNDER): libro(1.02, 1.03)}
    cv = E.cashout_value([punta], books, COMM)
    altra, piano = cv.ripieghi[(E.MARKET_OU45, E.SEL_OVER)]
    assert (altra, piano.side, piano.size, piano.price) == (E.SEL_UNDER, "back", 11.76, 1.02)
    books[(E.MARKET_OU45, E.SEL_OVER)] = libro(9.0, 10.0)      # banca 1,20
    assert E.cashout_value([punta], books, COMM).ripieghi == {}


# ---------------------------------------------------------------------------
# difetto gia' presente: resto di arrotondamento della chiusura (coordinatore,
# condizioni 1-3). p = 21, tolleranza 0,105 di sbilancio (0,005 di banca).
# ---------------------------------------------------------------------------
def _coperta_e_chiusa(*puntate):
    legs = [gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", p, s,
                  ref=f"over_cover-0-{i}") for i, (s, p) in enumerate(puntate, start=2)]
    legs.append(gamba("over_close", E.MARKET_OU45, E.SEL_OVER, "lay", 21.0, 0.71,
                      ref="over_close-0-9"))
    return legs


def test_resto_sotto_mezzo_centesimo_di_banca_e_piatto_e_si_scrive():
    legs = _coperta_e_chiusa((2.0, 6.6), (0.30, 6.0))       # sbilancio 0,09 = 0,0043 di banca
    w, l = E.exposure(legs, E.MARKET_OU45, E.SEL_OVER)
    assert round(w - l, 4) == 0.09
    assert E.open_selections(legs) == []
    assert E.locked_pnl(legs, COMM) is not None
    ctx = E.MatchCtx(state="LIVE_CLOSING", legs=legs, close_reason="profit")
    d = E._decide_closing(ctx, fotografia(o45_book=libro(20.0, 21.0)), params(), COMM)
    assert d.state == "FLAT"
    r = d.telemetry["residuo_non_piazzabile"]
    assert r["sbilancio"] == 0.09 and r["tolleranza"] == 0.105


def test_resto_da_0_006_di_banca_NON_e_piatto_e_si_dichiara_chiusura_parziale():
    """Il resto (sbilancio 0,138) NON e' piatto, come prima. Fino al 01/10 partiva
    la banca Over da 0,01, che Betfair .it rifiuta per taglia (Ashdod v Maccabi
    Herzliya, LIVE): oggi non parte, e la partita non si dichiara «chiusa»:
    LIVE_CLOSING, chiusura parziale, proposta all'utente con l'ordine esatto."""
    legs = _coperta_e_chiusa((2.28, 6.6))                    # sbilancio 0,138 = 0,0066 di banca
    assert E.open_selections(legs) == [(E.MARKET_OU45, E.SEL_OVER)]
    ctx = E.MatchCtx(state="LIVE_CLOSING", legs=legs, close_reason="profit")
    d = E.decide(ctx, fotografia(o45_book=libro(20.0, 21.0)), params())
    assert [x for x in d.actions if x.kind == "place"] == []
    assert d.state == "LIVE_CLOSING" and d.reason.startswith("chiusura parziale")
    [o] = d.updates["uscita_proposta"]["ordini"]
    assert (o["selezione"], o["lato"], o["size"], o["prezzo"], o["piazzabile"]) == (
        E.SEL_OVER, "lay", 0.01, 21.0, False)


def test_due_selezioni_lunghe_sull_over_chiave_over_e_chiusura_banca_over():
    """Richiesto dal coordinatore (mutazione Q5 sopravvissuta al blocco 1):
    punta Over della forma di prima abbinata + banca Under del rientro abbinata
    in parte -> la posizione netta e' LUNGA sull'Over: chiave Over, chiusura
    come BANCA sull'Over."""
    legs = [gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 6.6, 2.26,
                  ref="over_cover-0-2"),
            gamba("reentry_green", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.30, 1.0,
                  ref="reentry_green-0-4")]
    assert E.open_selections(legs) == [(E.MARKET_OU45, E.SEL_OVER)]
    books = {(E.MARKET_OU45, E.SEL_OVER): libro(6.4, 6.6),
             (E.MARKET_OU45, E.SEL_UNDER): libro(1.17, 1.18)}
    cv = E.cashout_value(legs, books, COMM)
    piano = cv.plans[(E.MARKET_OU45, E.SEL_OVER)]
    assert piano.side == "lay" and piano.price == 6.6


def test_sul_3_5_il_piatto_resta_il_centesimo():
    legs = [ingresso(), gamba("under_close", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.50, 9.99,
                              ref="under_close-0-2")]
    assert E.open_selections(legs) == [(E.MARKET_OU35, E.SEL_UNDER)]
