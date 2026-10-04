"""01/10/2026 - LA CHIUSURA DELLA COPERTURA-BANCA SOTTO IL MINIMO (Mike LIVE).

Fatto vero: FC Ashdod v Maccabi Herzliya (evento 36134689). Punta Under 3,5
5,00 @ 1,54 + copertura «banca Under 4,5» 6,32 @ 1,23. Alle 19:07:01 il motore
decide la chiusura in profitto e manda due ordini: la banca Under 3,5 6,21 @
1,24 (abbinata) e la BANCA Over 4,5 0,43 @ 18 (rifiutata da Betfair:
INVALID_BET_SIZE). 21 tentativi identici in 24 s, poi «chiuso (profit)» con la
banca Under 4,5 ancora a mercato. L'utente ha chiuso a mano con una PUNTATA
Under 4,5 da 7,47 @ 1,03 (abbinata: Betfair .it accetta la puntata da 2,00 al
centesimo).

Numeri dei test (brief del coordinatore): libri Under 4,5 1,03 / 1,04, Over 4,5
26 / 36, Under 3,5 1,14 / 1,16.

  (a) la chiusura del 4,5 e' una PUNTATA Under 4,5 7,55 @ 1,03, mai una banca
      sotto 0,50 (green-up esatto: 6,32 x 1,23 / 1,03 = 7,5472 -> 7,55; i 7,47
      dell'utente sono il green-up a 1,04: 7,7736 / 1,04 = 7,4746);
  (b) con tutte le chiusure abbinate il risultato bloccato e' il cash out (+-0,01);
  (c) rifiuto INVALID_BET_SIZE -> nessun secondo ordine identico ne' sullo stesso
      strumento; mai FLAT «chiuso»; CRITICAL + proposta con l'ordine esatto;
  (d) ``close_retry_s`` rispettato anche dopo un rifiuto (orologio finto);
  (e) forma di prima e chiusure sopra il minimo IDENTICHE al motore di master
      (numeri calcolati col motore di ``ebfab2a``);
  (A) guardia unica del minimo per ogni ruolo; (B) controllo di piatto.

Finti: gli oggetti veri dell'engine (Leg, Book, Snapshot, MatchCtx, Decision) e,
per il servizio, ``PlaceResult`` vero di ``omega_market`` e il DB in memoria
della suite (``db_vuoto``)."""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Optional

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import ORA, db_vuoto, info_vera
from Betfair.mike.tests.test_mike_p4_ordini_2026_09_29 import _live  # noqa: F401 (fixture)
from Betfair.omega.omega_market import PlaceResult

KO = 1_800_000_000.0
COMM = 0.05
T0 = KO + 4000.0          # l'istante della decisione di chiusura


def params(**over):
    p = C.merge_params(None)
    p["uscite_automatiche"] = True
    p["cover_form"] = E.COVER_LAY_U45
    p.update(over)
    return p


def gamba(role, market, selection, side, prezzo, abbinato, *, ref, status="open",
          size: Optional[float] = None, placed_at: float = KO) -> E.Leg:
    return E.Leg(role=role, market=market, selection=selection, side=side, price=prezzo,
                 size=abbinato if size is None else size, matched=abbinato,
                 avg_price=prezzo if abbinato > 0 else None, ref=ref, status=status,
                 placed_at=placed_at)


def libro(bb, bl, bs=500.0, ls=500.0, status="OPEN"):
    return E.Book(best_back=bb, back_size=bs, best_lay=bl, lay_size=ls, status=status,
                  inplay=True)


def libri(u35=(1.14, 1.16), u45=(1.03, 1.04), o45=(26.0, 36.0)):
    return {(E.MARKET_OU35, E.SEL_UNDER): libro(*u35),
            (E.MARKET_OU45, E.SEL_UNDER): libro(*u45),
            (E.MARKET_OU45, E.SEL_OVER): libro(*o45)}


def foto(now=T0, **kw):
    return E.Snapshot(now=now, ko_at=KO, books=libri(**kw), inplay=True, minute=67, goals=2,
                      feed_fresh=True, order_fresh=True)


def ingresso():
    return gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.54, 5.0,
                 ref="under_entry-0-1")


def copertura():
    return gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.23, 6.32,
                 ref="over_cover-0-4")


def chiusura_35():
    """La banca Under 3,5 abbinata alle 19:07:01 (6,21 @ 1,24)."""
    return gamba("under_close", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.24, 6.21,
                 ref="under_close-0-5", placed_at=T0)


def banca_rifiutata(n: int, placed_at: float = T0) -> E.Leg:
    """Una delle banche Over 4,5 0,43 @ 18 rifiutate (riga 'error', mai abbinata)."""
    return gamba("over_close", E.MARKET_OU45, E.SEL_OVER, "lay", 18.0, 0.0,
                 ref=f"over_close-0-{n}", status="cancelled", size=0.43, placed_at=placed_at)


def in_chiusura(*altre, attempts=0) -> E.MatchCtx:
    return E.MatchCtx(state="LIVE_CLOSING", legs=[ingresso(), copertura(), chiusura_35(), *altre],
                      close_reason="profit", attempts=attempts)


def rifiuta(ctx: E.MatchCtx, leg: E.Leg, codice: str = "INVALID_BET_SIZE") -> None:
    """Il rifiuto come lo scrive il servizio (``execute_place`` -> ``_rifiutata``)."""
    S._rifiutata(ctx, leg, f"rifiutata da Betfair ({codice})")


def piazzamenti(d):
    return [a for a in d.actions if a.kind == "place"]


# ===========================================================================
# (a) lo strumento giusto: PUNTATA Under 4,5 al centesimo, mai banca < 0,50
# ===========================================================================
def test_a_la_chiusura_del_45_e_una_puntata_under_7_55_a_1_03():
    legs = [ingresso(), copertura()]
    cv = E.cashout_value(legs, libri(), COMM)
    banca = cv.plans[(E.MARKET_OU45, E.SEL_OVER)]
    assert (banca.side, banca.size, banca.price) == ("lay", 0.22, 36.0)   # impossibile
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs)
    acts = piazzamenti(SimpleNamespace(actions=E._close_actions(ctx, cv, params())))
    # 04/10 (Umea, regola delle punte dell'utente): il green-up esatto 7,55 parte al
    # multiplo di 0,50 per DIFETTO, 7,50 (prima il test pretendeva 7,55 al centesimo)
    assert [(a.role, a.market, a.selection, a.side, a.size, a.price) for a in acts] == [
        ("under_close", E.MARKET_OU35, E.SEL_UNDER, "lay", 6.64, 1.16),
        ("over_close", E.MARKET_OU45, E.SEL_UNDER, "back", 7.50, 1.03)]
    assert cv.ripieghi[(E.MARKET_OU45, E.SEL_OVER)][1].size == 7.55     # il piano esatto
    # green-up esatto della banca Under 4,5: responsabilita' + importo / prezzo
    assert round(6.32 * 1.23 / 1.03, 4) == 7.5472
    # i 7,47 dell'utente sono il green-up allo scatto sopra (1,04)
    assert round(6.32 * 1.23 / 1.04, 2) == 7.47
    assert all(not (a.side == "lay" and a.size < 0.5) for a in acts)


def test_a_i_numeri_delle_19_07_riproducono_la_banca_rifiutata():
    """Fedelta': coi prezzi delle 19:07 (Over 4,5 a 18) il piano della banca e'
    proprio 0,43 @ 18, l'ordine rifiutato. Il motore corretto non la manda."""
    legs = [ingresso(), copertura(), chiusura_35()]
    cv = E.cashout_value(legs, libri(o45=(17.0, 18.0), u45=(1.06, 1.07)), COMM)
    banca = cv.plans[(E.MARKET_OU45, E.SEL_OVER)]
    assert (banca.side, banca.size, banca.price) == ("lay", 0.43, 18.0)
    altra, puntata = cv.ripieghi[(E.MARKET_OU45, E.SEL_OVER)]
    assert (altra, puntata.side, puntata.size, puntata.price) == (E.SEL_UNDER, "back", 7.33, 1.06)


def test_a_la_puntata_non_deve_essere_multipla_di_0_50():
    """Il vincolo vecchio (multiplo di 0,50) tolto: 7,55 non e' multiplo."""
    legs = [ingresso(), copertura()]
    piano = E.cashout_value(legs, libri(), COMM).plans[(E.MARKET_OU45, E.SEL_OVER)]
    rip = E.ripiego_chiusura_sotto_minimo(legs, (E.MARKET_OU45, E.SEL_OVER), piano, libri())
    assert rip is not None and rip[1].size == 7.55


@pytest.mark.parametrize("o45,atteso", [
    ((9.5, 10.0), ("over_close", E.SEL_UNDER, "back")),   # banca 0,78: sotto 1,00, puntata
    # 02/10 (decisione 12 dell'utente, supera M3.3): anche con la banca da 1,05
    # la chiusura della copertura-banca e' la PUNTA Under 4,5 di serie
    ((7.0, 7.4), ("over_close", E.SEL_UNDER, "back")),
])
def test_a_banca_fra_0_50_e_1_00_preferisce_la_puntata(o45, atteso):
    """Sotto 1,00 la banca non e' piazzabile: la puntata equivalente. Dal 02/10
    (decisione 12 dell'utente) con la copertura-banca la puntata e' di serie a
    ogni importo: il caso della banca da 1,05 ora e' una puntata."""
    legs = [ingresso(), copertura()]
    books = libri(o45=o45, u45=(1.11, 1.12) if o45[1] == 10.0 else (1.15, 1.16))
    cv = E.cashout_value(legs, books, COMM)
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs)
    [a] = [x for x in E._close_actions(ctx, cv, params())
           if x.kind == "place" and x.market == E.MARKET_OU45]
    assert (a.role, a.selection, a.side) == atteso
    assert E.via_ordine(a.role, a.side, a.size) == E.VIA_DIRETTA


def test_a_puntata_sotto_il_minimo_nessun_ripiego_e_nessun_ordine():
    """Copertura piccola: banca Over 0,02 e puntata Under 0,60, entrambe sotto
    il minimo (1,00 come 2,00). La chiusura non passa dal place-and-trim
    (chiusure dirette in ``execution.place``): non parte nessun ordine impossibile."""
    legs = [gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.23, 0.50,
                  ref="over_cover-0-4")]
    cv = E.cashout_value(legs, libri(), COMM)
    assert cv.ripieghi == {}
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs)
    assert piazzamenti(SimpleNamespace(actions=E._close_actions(ctx, cv, params()))) == []


# ===========================================================================
# (b) il risultato bloccato e' il cash out dichiarato
# ===========================================================================
def test_b_tutte_le_chiusure_abbinate_bloccano_il_cash_out():
    legs = [ingresso(), copertura()]
    cv = E.cashout_value(legs, libri(), COMM)
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=list(legs))
    for i, a in enumerate(x for x in E._close_actions(ctx, cv, params()) if x.kind == "place"):
        legs.append(gamba(a.role, a.market, a.selection, a.side, a.price, a.size,
                          ref=f"{a.role}-0-{9 + i}"))
    dist = E.net_pnl_by_total(legs, COMM)
    # 04/10 (regola delle punte .it): la punta Under 4,5 parte 7,50 invece di 7,55; i
    # 0,05 non piazzabili lasciano uno sbilancio di ~0,05 (prima <= 0,01, piatto)
    assert max(dist.values()) - min(dist.values()) <= 0.06
    assert cv.net == 0.33
    # il residuo NON e' dimenticato: Mike non si dichiara chiuso, lo dichiara
    ctx2 = E.MatchCtx(state="LIVE_CLOSING", legs=legs, close_reason="profit")
    d = E.decide(ctx2, foto(), params())
    assert d.state == "LIVE_CLOSING" and d.reason.startswith("chiusura parziale")
    assert d.telemetry["chiusura_parziale"]["critical"] is True
    assert [a for a in d.actions if a.kind == "place"] == []


# ===========================================================================
# (B) il controllo di piatto: il caso di oggi finisce in «chiusura parziale»
# ===========================================================================
def test_B_ashdod_tentativi_esauriti_chiusura_parziale_mai_chiuso_profit():
    """Lo stato del motore alle 19:07:25: 3,5 chiuso, 21 banche Over rifiutate,
    tentativi esauriti. Master: FLAT «chiuso (profit)». Ora: LIVE_CLOSING,
    chiusura parziale, proposta «punta Under 4,5 7,55 @ 1,03», avviso CRITICAL."""
    rifiutate = [banca_rifiutata(n) for n in range(6, 27)]
    ctx = in_chiusura(*rifiutate, attempts=20)
    for leg in rifiutate:
        rifiuta(ctx, leg)
    d = E.decide(ctx, foto(now=T0 + 24), params())
    assert d.state == "LIVE_CLOSING"
    assert "chiuso (" not in d.reason and "profit" not in d.reason
    assert d.reason.startswith("chiusura parziale: residuo scoperto su OU45/UNDER punta 7.55 @ 1.03")
    assert piazzamenti(d) == []                                 # tentativi esauriti: si ferma
    prop = d.updates["uscita_proposta"]
    assert prop["residuo_scoperto"] is True and prop["categoria"] == E.CATEGORIA_RESIDUO
    [o] = prop["ordini"]
    assert (o["mercato"], o["selezione"], o["lato"], o["size"], o["prezzo"], o["piazzabile"]) == (
        E.MARKET_OU45, E.SEL_UNDER, "back", 7.55, 1.03, True)
    avviso = d.telemetry["chiusura_parziale"]
    assert avviso["critical"] is True and avviso["perche"] == "tentativi esauriti (20)"
    assert "attempts" not in d.updates                         # i tentativi restano esauriti


def test_B_al_giro_dopo_resta_la_stessa_proposta_senza_un_secondo_avviso():
    rifiutate = [banca_rifiutata(n) for n in range(6, 27)]
    ctx = in_chiusura(*rifiutate, attempts=20)
    for leg in rifiutate:
        rifiuta(ctx, leg)
    d1 = E.decide(ctx, foto(now=T0 + 24), params())
    E.apply_decision(ctx, d1, T0 + 24)
    d2 = E.decide(ctx, foto(now=T0 + 25), params())
    assert d2.state == "LIVE_CLOSING" and d2.reason == d1.reason
    assert d2.updates["uscita_proposta"] is ctx.uscita_proposta
    assert "chiusura_parziale" not in d2.telemetry and "uscita_proposta" not in d2.telemetry
    # e non «decade» a ogni giro per rinascere subito (una riga di attivita' al secondo)
    assert "uscita_proposta_decaduta" not in d2.telemetry


def test_B_stesso_episodio_ordine_cambiato_nessun_secondo_avviso():
    """Il libro si muove e l'ordine proposto cambia strumento: la proposta si
    aggiorna, l'avviso CRITICAL resta quello dell'inizio (nel banco il libro
    dell'Under 4,5 che va e viene ne produceva 54 in una partita)."""
    ctx = in_chiusura(attempts=20)
    o1 = [{"mercato": E.MARKET_OU45, "selezione": E.SEL_UNDER, "lato": "back", "piazzabile": True}]
    o2 = [{"mercato": E.MARKET_OU45, "selezione": E.SEL_OVER, "lato": "lay", "piazzabile": False}]
    p1, nuova1 = E._proposta_residuo(ctx, foto(), o1, [], "m", "FLAT", None)
    ctx.uscita_proposta = p1
    p2, nuova2 = E._proposta_residuo(ctx, foto(), o2, [], "m", "FLAT", None)
    assert nuova1 is True and nuova2 is False and p2["ordini"] == o2
    assert p2["decided_at"] == p1["decided_at"]


def test_B_residuo_chiuso_a_mano_la_proposta_decade_e_la_partita_e_piatta():
    rifiutate = [banca_rifiutata(n) for n in range(6, 27)]
    ctx = in_chiusura(*rifiutate, attempts=20)
    for leg in rifiutate:
        rifiuta(ctx, leg)
    E.apply_decision(ctx, E.decide(ctx, foto(now=T0 + 24), params()), T0 + 24)
    # «Chiudi» dell'utente: la puntata Under 4,5 7,55 @ 1,03 abbinata
    ctx.legs.append(gamba("manual_close", E.MARKET_OU45, E.SEL_UNDER, "back", 1.03, 7.55,
                          ref="manual_close-0-30", placed_at=T0 + 200))
    d = E.decide(ctx, foto(now=T0 + 230), params())
    assert d.state == "FLAT" and d.updates["uscita_proposta"] is None
    assert d.telemetry["uscita_proposta_decaduta"]["chiave"] == f"{E.CATEGORIA_RESIDUO}|c0"


def test_B_chiudi_dell_utente_sotto_il_minimo_lo_dice_e_propone_l_ordine():
    """«Chiudi» (flatten) quando l'ordine che chiude e' sotto il minimo: non
    parte, la partita non si dichiara chiusa ne' «senza prezzi», e la proposta
    dice l'ordine esatto. Punta Over 0,15 @ 5,10, Over a 50: banca 0,02 e puntata
    Under equivalente 0,75 @ 1,02, tutte e due sotto il minimo (1,00 come 2,00)."""
    over = gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 5.10, 0.15, ref="over_cover-0-2")
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[ingresso(), chiusura_35(), over],
                     flatten_pending=True)
    d = E.decide(ctx, foto(o45=(48.0, 50.0), u45=(1.02, 1.03)), params(cover_form=E.COVER_BACK_O45))
    assert piazzamenti(d) == [] and d.state == "LIVE_COVERED"
    assert "sotto il minimo Betfair .it" in d.reason and "prezzi non disponibili" not in d.reason
    assert d.updates["uscita_proposta"]["residuo_scoperto"] is True
    assert d.telemetry["chiusura_parziale"]["critical"] is True
    # nessuno strumento piazzabile: le due scelte dell'utente (guida italiana)
    assert d.updates["uscita_proposta"]["alternative"] == [
        "lasciare il residuo fino al regolamento",
        "aumentare la posizione di un importo minimo e poi chiudere tutto"]


# ===========================================================================
# (c) rifiuto per taglia: cambio strumento o stop, mai lo stesso ordine
# ===========================================================================
def test_c_dopo_il_rifiuto_della_banca_si_cambia_strumento():
    """La banca Over rifiutata per taglia: al tentativo dopo parte la PUNTATA
    Under (un altro strumento), non una seconda banca."""
    rifiutata = banca_rifiutata(6)
    ctx = in_chiusura(rifiutata, attempts=1)
    rifiuta(ctx, rifiutata)
    d = E.decide(ctx, foto(now=T0 + 10), params())
    [a] = piazzamenti(d)
    # 04/10: 7,55 -> 7,50 (punta a multiplo di 0,50 per difetto)
    assert (a.role, a.selection, a.side, a.size, a.price) == ("over_close", E.SEL_UNDER,
                                                             "back", 7.50, 1.03)


def test_c_stesso_strumento_rifiutato_per_taglia_non_si_ripropone_a_nessun_importo(
        monkeypatch, _live):
    """Il servizio VERO piazza la puntata Under; Betfair (finto con il
    ``PlaceResult`` vero) la rifiuta INVALID_BET_SIZE. Il motore non la rifa'
    (ne' identica ne' con un altro importo), la banca Over 0,22 e' sotto il
    minimo: nessun ordine, LIVE_CLOSING, chiusura parziale, proposta, CRITICAL."""
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    chiamate = []

    def place_order_live(**kw):
        chiamate.append(kw)
        return PlaceResult(ok=False, order_status="EXPIRED", bet_id=None, size_matched=0.0,
                           avg_price_matched=None, raw={}, size_requested=float(kw["size"]),
                           price_requested=float(kw["price"]), size_remaining=0.0,
                           size_cancelled=float(kw["size"]), error_code="INVALID_BET_SIZE",
                           betfair_updated_at=None)
    ctx = in_chiusura(attempts=1)
    d = E.decide(ctx, foto(now=T0 + 10), params())
    [leg] = E.apply_decision(ctx, d, T0 + 10)
    # 04/10: 7,55 -> 7,50 (punta a multiplo di 0,50 per difetto)
    assert (leg.selection, leg.side, leg.size) == (E.SEL_UNDER, "back", 7.50)
    db = db_vuoto()
    esito = S.execute_place(db=db, market=SimpleNamespace(place_order_live=place_order_live),
                            info=info_vera(), leg=leg, book=libri()[(E.MARKET_OU45, E.SEL_UNDER)],
                            mode="live", params=params(), now=ORA, dry=False, feed_fresh=True,
                            ctx=ctx)
    assert esito == "cancelled" and len(chiamate) == 1
    # il book si muove di un centesimo d'importo: stesso strumento, nuovo importo
    for dt, u45 in ((20, (1.03, 1.04)), (40, (1.02, 1.03)), (60, (1.04, 1.05))):
        d = E.decide(ctx, foto(now=T0 + dt, u45=u45), params())
        assert piazzamenti(d) == [], (dt, d.reason)
        assert d.state == "LIVE_CLOSING" and d.reason.startswith("chiusura parziale")
        E.apply_decision(ctx, d, T0 + dt)
    [o] = ctx.uscita_proposta["ordini"]
    assert (o["selezione"], o["lato"], o["piazzabile"]) == (E.SEL_UNDER, "back", True)


@pytest.mark.parametrize("codice", ["INVALID_BET_SIZE", "SOTTO_MINIMO_NON_PIAZZABILE"])
def test_c_rifiuto_per_taglia_di_betfair_o_del_runner_blocca_lo_strumento(codice):
    """Il runner (01/10) traduce da se' gli ordini sotto minimo e, se non c'e'
    via, rifiuta con SOTTO_MINIMO_NON_PIAZZABILE: come INVALID_BET_SIZE, lo stesso
    strumento non si ritenta (a nessun importo)."""
    puntata = gamba("over_close", E.MARKET_OU45, E.SEL_UNDER, "back", 1.03, 0.0,
                    ref="over_close-0-6", status="cancelled", size=7.55, placed_at=T0)
    ctx = in_chiusura(puntata, attempts=1)
    rifiuta(ctx, puntata, codice)
    prova = E._place("over_close", E.MARKET_OU45, E.SEL_UNDER, "back", 1.04, 7.40)
    assert E.chiusura_gia_rifiutata(ctx, prova) is not None


def test_c_il_servizio_scrive_l_avviso_critico_e_la_riga(caplog):
    rifiutate = [banca_rifiutata(n) for n in range(6, 27)]
    ctx = in_chiusura(*rifiutate, attempts=20)
    for leg in rifiutate:
        rifiuta(ctx, leg)
    d = E.decide(ctx, foto(now=T0 + 24), params())
    db = db_vuoto()
    with caplog.at_level(logging.CRITICAL, logger="mike.service"):
        S._registra_avvisi_esecuzione(db, d, ctx, "36134689")
    righe = [(k, p) for k, p, _e in db.attivita if k == "chiusura_parziale"]
    assert len(righe) == 1 and righe[0][1]["critical"] is True
    assert righe[0][1]["state"] == "LIVE_CLOSING"
    assert any(r.levelno == logging.CRITICAL and "chiusura parziale" in r.getMessage()
               for r in caplog.records)


def test_c_la_proposta_del_residuo_non_si_approva():
    rifiutate = [banca_rifiutata(n) for n in range(6, 27)]
    ctx = in_chiusura(*rifiutate, attempts=20)
    for leg in rifiutate:
        rifiuta(ctx, leg)
    d = E.decide(ctx, foto(now=T0 + 24), params())
    E.apply_decision(ctx, d, T0 + 24)
    ev = {"event_id": "36134689", "state": ctx.state, "ctx": {}}
    ctx_row = S._row_from_ctx(ev, ctx, {})
    db = db_vuoto()
    res = S._request_approva_uscita(db, ctx_row, {"36134689": ctx_row}, "36134689",
                                    {"chiave": ctx.uscita_proposta["chiave"]},
                                    ORA)
    assert res["code"] == "proposta_non_approvabile" and not res.get("ok")
    assert "proposta_non_approvabile" in S._REJECT_CODES


# ===========================================================================
# (d) il ritmo dei tentativi: close_retry_s anche dopo un rifiuto
# ===========================================================================
def test_d_dopo_un_rifiuto_si_aspetta_close_retry_s():
    rifiutata = banca_rifiutata(6, placed_at=T0)
    ctx = in_chiusura(rifiutata, attempts=1)
    rifiuta(ctx, rifiutata)
    p = params(close_retry_s=10)
    for dt in (1, 3, 9.9):
        d = E.decide(ctx, foto(now=T0 + dt), p)
        assert piazzamenti(d) == [], dt
        assert d.state == "LIVE_CLOSING" and "prossimo tentativo fra" in d.reason
        assert "uscita_proposta" not in d.updates
    d = E.decide(ctx, foto(now=T0 + 10), p)
    assert len(piazzamenti(d)) == 1 and d.updates["attempts"] == 2


def test_d_fok_non_abbinato_si_ritenta_uguale_dopo_close_retry_s_e_non_e_chiusura_parziale():
    """Un FOK non abbinato non e' un rifiuto per taglia: la stessa puntata si
    ritenta dopo close_retry_s (prima no), e intanto non si dichiara nessun
    residuo scoperto (nessun avviso CRITICAL a ogni FOK mancato)."""
    puntata = gamba("over_close", E.MARKET_OU45, E.SEL_UNDER, "back", 1.03, 0.0,
                    ref="over_close-0-6", status="cancelled", size=7.55, placed_at=T0)
    ctx = in_chiusura(puntata, attempts=1)
    S._rifiutata(ctx, puntata, "FOK non abbinato (scaduto)")
    d = E.decide(ctx, foto(now=T0 + 5), params(close_retry_s=10))
    assert piazzamenti(d) == [] and "prossimo tentativo fra" in d.reason
    assert "chiusura_parziale" not in d.telemetry and "uscita_proposta" not in d.updates
    d = E.decide(ctx, foto(now=T0 + 10), params(close_retry_s=10))
    [a] = piazzamenti(d)
    # 04/10: 7,55 -> 7,50 (punta a multiplo di 0,50 per difetto)
    assert (a.selection, a.side, a.size, a.price) == (E.SEL_UNDER, "back", 7.50, 1.03)


def test_d_ventuno_rifiuti_in_24_secondi_non_possono_piu_accadere():
    """Riproduzione del loop: un giro al secondo per 24 s dopo la decisione. Gli
    ordini emessi sono al massimo uno ogni close_retry_s (qui: 3 in 24 s, e
    nessuno identico a un rifiutato)."""
    ctx = in_chiusura(attempts=0)
    p = params(close_retry_s=10)
    emessi = []
    for dt in range(0, 25):
        now = T0 + dt
        d = E.decide(ctx, foto(now=now), p)
        nuove = E.apply_decision(ctx, d, now)
        for leg in nuove:
            emessi.append((now, leg.selection, leg.side, leg.size))
            leg.status = "cancelled"          # Betfair: rifiutata
            rifiuta(ctx, leg)
    assert len(emessi) <= 3, emessi
    tempi = [t for t, *_ in emessi]
    assert all(b - a >= 10 for a, b in zip(tempi, tempi[1:])), tempi
    assert len({e[1:] for e in emessi}) == len(emessi)          # mai lo stesso ordine


# ===========================================================================
# (e) non regressione: numeri del motore di master (ebfab2a)
# ===========================================================================
def test_e_banca_di_chiusura_sopra_il_minimo_diventa_la_puntata_decisione_12():
    """Copertura-banca, Over 4,5 a 4,2 / 4,3 (prezzi del cash out di
    ``cashout-dopo-copertura`` del 30/09). Master: banca Over 1,81 @ 4,3, cash out
    0,27. 02/10 - DECISIONE 12 DELL'UTENTE (supera M3.3): la chiusura della
    copertura-banca e' la PUNTA Under 4,5 di serie anche con la banca sopra il
    minimo: green-up sull'Under a 1,30 = (6,32 x 1,23) / 1,30 = 7,7736 / 1,30 =
    5,98. Il cash out vale la puntata che parte (decisione 14): 0,26 (la banca a
    4,3 valeva 0,27: il libro dell'Under a 1,30 e' di poco peggiore del 1/(1-1/4,3)
    = 1,3030 implicito). La banca Under 3,5 resta identica a master."""
    legs = [gamba("under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 1.80, 5.0,
                  ref="under_entry-0-1"), copertura()]
    books = libri(u35=(1.80, 1.82), u45=(1.30, 1.31), o45=(4.2, 4.3))
    cv = E.cashout_value(legs, books, COMM)
    assert cv.plans[(E.MARKET_OU45, E.SEL_OVER)].size == 1.81     # banca piazzabile...
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs)
    got = [(a.role, a.selection, a.side, a.size, a.price)
           for a in E._close_actions(ctx, cv, params()) if a.kind == "place"]
    # 04/10 (regola delle punte .it): la punta 5,98 parte 5,50 (multiplo di 0,50 per
    # difetto); prima il test pretendeva 5,98 e la posizione piatta entro 0,01
    assert got == [("under_close", E.SEL_UNDER, "lay", 4.95, 1.82),
                   ("over_close", E.SEL_UNDER, "back", 5.50, 1.3)]   # ...ma parte la punta
    assert round(6.32 * 1.23 / 1.30, 2) == 5.98
    assert cv.net == 0.26
    for i, (role, sel, side, size, price) in enumerate(got):
        mk = E.MARKET_OU35 if role == "under_close" else E.MARKET_OU45
        legs.append(gamba(role, mk, sel, side, price, size, ref=f"{role}-0-{9 + i}"))
    # residuo 0,48 di punta Under non piazzato: lo sbilancio resta e si dichiara
    ctx2 = E.MatchCtx(state="LIVE_CLOSING", legs=legs, close_reason="profit")
    d = E.decide(ctx2, foto(u35=(1.80, 1.82), u45=(1.30, 1.31), o45=(4.2, 4.3)), params())
    assert d.state == "LIVE_CLOSING" and d.reason.startswith("chiusura parziale")


def test_e_copertura_banca_con_puntata_sotto_minimo_resta_la_banca():
    """Decisione 12: la punta di serie, ma solo se e' piazzabile. Banca Under 4,5
    0,90 @ 3,0, Over 1,50 / 1,52, Under 2,9 / 3,0: la puntata Under sarebbe 0,93
    (sotto 1,00), la banca Over 1,78 @ 1,52 e' piazzabile: parte la banca."""
    legs = [gamba("over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 3.0, 0.9,
                  ref="over_cover-0-4")]
    books = libri(u45=(2.9, 3.0), o45=(1.5, 1.52))
    cv = E.cashout_value(legs, books, COMM)
    assert cv.ripieghi == {}
    eq = E.puntata_equivalente(legs, (E.MARKET_OU45, E.SEL_OVER), books)
    assert eq is not None and eq[1].size == 0.93
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs)
    got = [(a.role, a.selection, a.side, a.size, a.price)
           for a in E._close_actions(ctx, cv, params()) if a.kind == "place"]
    assert got == [("over_close", E.SEL_OVER, "lay", 1.78, 1.52)]


def test_e_forma_di_prima_identica_a_master():
    """Punta Over 4,5 1,30 @ 5,4 (forma ``back_over45``), Over a 4,2 / 4,3:
    banca Over 1,63 @ 4,3, nessun ripiego, come master."""
    legs = [ingresso(), gamba("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 5.4, 1.30,
                              ref="over_cover-0-2")]
    books = libri(u35=(1.30, 1.31), u45=(1.30, 1.31), o45=(4.2, 4.3))
    cv = E.cashout_value(legs, books, COMM)
    assert cv.ripieghi == {}
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=legs)
    got = [(a.role, a.selection, a.side, a.size, a.price)
           for a in E._close_actions(ctx, cv, params(cover_form=E.COVER_BACK_O45))
           if a.kind == "place"]
    assert got == [("under_close", E.SEL_UNDER, "lay", 5.88, 1.31),
                   ("over_close", E.SEL_OVER, "lay", 1.63, 4.3)]
    assert cv.net == 1.15                                        # come master


# ===========================================================================
# (A) la guardia unica del minimo, per ogni ruolo
# ===========================================================================
@pytest.mark.parametrize("ruolo", E.ROLES)
@pytest.mark.parametrize("lato,size", [("lay", 0.99), ("lay", 0.50), ("back", 0.99), ("lay", 0.01),
                                       ("back", 0.01)])
def test_A_ogni_ruolo_sotto_minimo_ha_una_via_e_mai_un_ordine_impossibile(ruolo, lato, size):
    via = E.via_ordine(ruolo, lato, size, params())
    if ruolo in E.CLOSING_ROLES or lato == "lay" or size < E.SUBMIN_IMPORTO_FINALE_MIN:
        # chiusure dirette, BANCHE sotto 1,00 e importi sotto l'importo finale minimo
        # del place-and-trim (0,50): non partono
        assert via == E.VIA_NON_SI_MANDA
    else:
        assert via == E.VIA_SUBMIN                  # punta d'apertura 0,50-0,99: place-and-trim
    assert E.via_ordine(ruolo, lato, E.minimo_listino(lato), params()) == E.VIA_DIRETTA


@pytest.mark.parametrize("ruolo", E.CLOSING_ROLES)
def test_A_la_guardia_toglie_l_ordine_impossibile_da_ogni_decisione(ruolo):
    """Un ramo qualunque che emettesse una chiusura sotto il minimo: la guardia
    la toglie, la ricorda come rifiuto, avvisa una volta e propone l'ordine."""
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[ingresso(), copertura()])
    mercato, sel = (E.MARKET_OU45, E.SEL_OVER) if ruolo != "under_green" else (
        E.MARKET_OU35, E.SEL_UNDER)
    d = E.Decision("LIVE_CLOSING", [E._place(ruolo, mercato, sel, "lay", 18.0, 0.43)], "prova")
    out = E._guardia_minimo_listino(ctx, d, foto(), params())
    assert piazzamenti(out) == []
    assert out.state == ctx.state                   # niente da piazzare: lo stato non avanza
    assert out.telemetry["ordine_sotto_minimo"]["critical"] is True
    assert out.updates["uscita_proposta"]["residuo_scoperto"] is True
    E.apply_decision(ctx, out, T0)
    again = E._guardia_minimo_listino(ctx, d, foto(), params())
    assert "ordine_sotto_minimo" not in again.telemetry    # una riga per episodio


@pytest.mark.parametrize("ruolo", E.OPENING_ROLES)
def test_A_le_aperture_sotto_minimo_passano_dal_place_and_trim(ruolo):
    """Una PUNTA d'apertura sotto 2,00 passa dal place-and-trim (parcheggio a 2,00);
    una BANCA d'apertura sotto 1,00 no (la guardia la toglie, vincolo 01/10)."""
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[ingresso()])
    d = E.Decision("PRE_ENTRY_PENDING", [E._place(ruolo, E.MARKET_OU35, E.SEL_UNDER, "back",
                                                  1.54, 1.50)], "prova")
    assert E._guardia_minimo_listino(ctx, d, foto(), params()) is d
    banca = E.Decision("LIVE_COVER_PENDING", [E._place(ruolo, E.MARKET_OU45, E.SEL_UNDER, "lay",
                                                       1.23, 0.80)], "prova")
    assert piazzamenti(E._guardia_minimo_listino(ctx, banca, foto(), params())) == []


def test_uscita_in_perdita_con_ordini_sotto_minimo_resta_una_proposta_da_firmare():
    """Reperto del banco (`copertura-rifiutata-legacy`): l'uscita a modello IN
    PERDITA i cui ordini sono stati tolti perche' sotto il minimo passava il
    cancello delle uscite manuali (nessun ordine = nessuna categoria) e al giro
    dopo partiva senza firma. Resta una proposta da firmare; a uscite
    automatiche passa."""
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[ingresso(), copertura()])
    d = E.Decision("LIVE_CLOSING", [], "uscita a modello (2t): chiudere vale piu' di tenere",
                   updates={"close_reason": "loss_2t", "attempts": 0})
    out = E.gate_uscite(ctx, d, foto(), params(uscite_automatiche=False))
    assert out.state == "LIVE_COVERED" and "close_reason" not in out.updates
    assert out.updates["uscita_proposta"]["categoria"] == "chiusura"
    assert E.gate_uscite(ctx, d, foto(), params(uscite_automatiche=True)).state == "LIVE_CLOSING"


def test_controlli_del_banco_L1_L2_vedono_il_difetto_di_oggi():
    """I controlli di condotta nuovi del banco (``certificazione``): L1 vede la
    banca di chiusura 0,43 (l'ordine di oggi), L2 vede il «chiuso (profit)» con la
    banca Under 4,5 ancora a mercato. Sulla decisione corretta tacciono."""
    from Betfair.mike import certificazione as CERT
    ctx = in_chiusura(attempts=20)
    s = foto(now=T0 + 24)
    oggi = E.Decision("LIVE_CLOSING", [E._place("over_close", E.MARKET_OU45, E.SEL_OVER,
                                                "lay", 18.0, 0.43)], "chiusura residuo")
    assert "sotto il minimo" in CERT._l1(ctx, s, oggi, params())
    falso = E.Decision("FLAT", [], "chiuso (profit)")
    assert "esposizione viva" in CERT._l2(ctx, s, falso, params())
    vero = E.decide(ctx, s, params())
    assert CERT._l1(ctx, s, vero, params()) is None and CERT._l2(ctx, s, vero, params()) is None


def test_A_i_minimi_vengono_dalla_fonte_unica_del_repo():
    """Ordine dell'utente del 01/10: punta 1,00 e banca 1,00, al centesimo, nessun
    passo, da ``Betfair/stream/trading/minimi_it.py`` (lo stesso modulo del runner)."""
    from Betfair.stream.trading import minimi_it as M
    assert (M.IT_MIN_BACK, M.IT_MIN_LAY, M.IT_FLOOR_LEGGE, M.SUBMIN_IMPORTO_FINALE_MIN) == (
        1.00, 1.00, 0.50, 0.50)
    assert E.minimo_listino("back") == E.IT_BACK_MIN == M.IT_MIN_BACK
    assert E.minimo_listino("lay") == E.IT_LAY_MIN == M.IT_MIN_LAY
    assert E.IT_BACK_STEP == 0.01                     # nessun passo da 0,50
    assert E.legalize_back_size(7.47, "ceil") == (7.47, 0.0)
    assert E.legalize_back_size(0.73, "ceil")[0] == 1.00
