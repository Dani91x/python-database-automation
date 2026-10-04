"""04/10/2026 - LA COPERTURA PARTE SOLO A UN PREZZO COERENTE (ordine dell'utente).

Incidente: Antofagasta v CSD Rangers (36140993), punta Under 3,5 5,00 a 1,41. Il
libro dell'Under 4,5 era quasi vuoto (offerte in banca a 3,0 e poi a 18,5 contro
un valore intorno a 1,2): Mike ha mandato la copertura a 3,1 (rischio 13,27) e poi
tre volte a 19,5 / 19,0 (rischio 116,92 per coprire 5,00). Betfair le ha
rifiutate; con i fondi sul conto sarebbero passate.

REGOLA (testuale dell'utente): la copertura parte SOLO se la quota a cui Mike
banca l'Under 4,5 (il suo prezzo limite) e' MINORE - non minore o uguale - della
quota di banca dell'Under 3,5 in quello stesso momento. Altrimenti nessun
ordine: resta in attesa, avvisa UNA volta, ricontrolla a ogni giro. Quota
dell'Under 3,5 non leggibile = nessun confronto possibile = aspetta.
Tutto il resto della copertura (momento, importo, tranche, liquidita') invariato.

Finti: gli oggetti veri dell'engine (Leg, Book, Snapshot, MatchCtx, Decision).
"""
from __future__ import annotations

from typing import Any, Optional

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S

KO = 1_800_000_000.0


def params(**over):
    p = C.merge_params(None)
    p["uscite_automatiche"] = True
    p["cover_form"] = E.COVER_LAY_U45
    p["cover_policy"] = "immediate"
    p.update(over)
    return p


def ingresso(stake=5.0, prezzo=1.41) -> E.Leg:
    return E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                 price=prezzo, size=stake, matched=stake, avg_price=prezzo,
                 ref="under_entry-0-1", status="open", placed_at=KO)


def libro(bb: Optional[float], bl: Optional[float], bs=500.0, ls=500.0) -> E.Book:
    return E.Book(best_back=bb, back_size=bs, best_lay=bl, lay_size=ls, status="OPEN",
                  inplay=True)


def fotografia(*, u35: Optional[E.Book], u45: E.Book, now=KO + 180) -> E.Snapshot:
    books = {(E.MARKET_OU45, E.SEL_UNDER): u45,
             (E.MARKET_OU45, E.SEL_OVER): libro(15.0, 16.0)}
    if u35 is not None:
        books[(E.MARKET_OU35, E.SEL_UNDER)] = u35
    return E.Snapshot(now=now, ko_at=KO, books=books, inplay=True, minute=3, goals=0,
                      feed_fresh=True, order_fresh=True)


def scoperta() -> E.MatchCtx:
    return E.MatchCtx(state="LIVE_UNCOVERED", entry_price_initial=1.41, legs=[ingresso()])


def ordini_di_copertura(d: E.Decision):
    return [a for a in d.actions if getattr(a, "role", None) == "over_cover"]


# ---------------------------------------------------------------------------
# 1. quote normali: la copertura parte ESATTAMENTE come prima
# ---------------------------------------------------------------------------
def test_quote_normali_la_copertura_parte_come_prima():
    d = E.decide(scoperta(), fotografia(u35=libro(1.40, 1.41), u45=libro(1.20, 1.21)), params())
    assert d.state == "LIVE_COVER_PENDING"
    (a,) = ordini_di_copertura(d)
    assert (a.market, a.selection, a.side) == (E.MARKET_OU45, E.SEL_UNDER, "lay")
    assert a.size == 6.32                                   # 5,00 x 1,2 / 0,95
    assert a.price == E.cover_place_price_lay(1.21, params())   # limite di sempre (+2 tick)
    assert a.price < 1.41


# ---------------------------------------------------------------------------
# 2. il caso di Antofagasta: banca Under 4,5 a 3,0 / 18,5 con l'Under 3,5 a 1,41
# ---------------------------------------------------------------------------
def test_antofagasta_quota_maggiore_nessun_ordine_e_attesa_dichiarata():
    for miglior_banca_u45 in (3.0, 18.5):
        d = E.decide(scoperta(), fotografia(u35=libro(1.40, 1.41),
                                            u45=libro(1.05, miglior_banca_u45)), params())
        assert d.state == "LIVE_UNCOVERED", miglior_banca_u45
        assert ordini_di_copertura(d) == [], "nessun ordine di copertura deve partire"
        att = d.telemetry["cover_wait"]
        assert att["reason"] == E.COVER_FUORI_PREZZO
        assert att["price_lay_u35"] == 1.41
        assert att["price_lay_u45"] == miglior_banca_u45
        assert att["price_limite"] == E.cover_place_price_lay(miglior_banca_u45, params())
        assert "Under 4.5" in d.reason and "Under 3.5" in d.reason


# ---------------------------------------------------------------------------
# 3. MINORE, non minore o uguale: a quote uguali NON parte; un tick sotto parte
# ---------------------------------------------------------------------------
def test_quote_uguali_non_parte_un_tick_sotto_parte():
    p = params()
    # miglior banca Under 4,5 tale che il prezzo limite sia ESATTAMENTE 1,41
    assert E.cover_place_price_lay(1.39, p) == 1.41
    uguale = E.decide(scoperta(), fotografia(u35=libro(1.40, 1.41), u45=libro(1.38, 1.39)), p)
    assert uguale.state == "LIVE_UNCOVERED"
    assert ordini_di_copertura(uguale) == []
    assert uguale.telemetry["cover_wait"]["reason"] == E.COVER_FUORI_PREZZO

    assert E.cover_place_price_lay(1.38, p) == 1.40
    sotto = E.decide(scoperta(), fotografia(u35=libro(1.40, 1.41), u45=libro(1.37, 1.38)), p)
    assert sotto.state == "LIVE_COVER_PENDING"
    (a,) = ordini_di_copertura(sotto)
    assert a.price == 1.40 and a.size == 6.32


# ---------------------------------------------------------------------------
# 4. il libro torna normale al giro dopo: la copertura parte
# ---------------------------------------------------------------------------
def test_il_libro_torna_normale_e_la_copertura_parte():
    ctx = scoperta()
    p = params()
    primo = E.decide(ctx, fotografia(u35=libro(1.40, 1.41), u45=libro(1.05, 18.5)), p)
    assert primo.state == "LIVE_UNCOVERED" and ordini_di_copertura(primo) == []
    secondo = E.decide(ctx, fotografia(u35=libro(1.40, 1.41), u45=libro(1.20, 1.21),
                                       now=KO + 182), p)
    assert secondo.state == "LIVE_COVER_PENDING"
    (a,) = ordini_di_copertura(secondo)
    assert a.size == 6.32 and a.price < 1.41


# ---------------------------------------------------------------------------
# 5. quota di banca dell'Under 3,5 non leggibile: nessun confronto, si aspetta
# ---------------------------------------------------------------------------
def test_under35_non_leggibile_si_aspetta():
    for u35 in (None, libro(1.40, None)):
        d = E.decide(scoperta(), fotografia(u35=u35, u45=libro(1.20, 1.21)), params())
        assert d.state == "LIVE_UNCOVERED"
        assert ordini_di_copertura(d) == []
        assert d.telemetry["cover_wait"]["reason"] == E.COVER_U35_NON_LEGGIBILE


# ---------------------------------------------------------------------------
# 6. l'avviso critico: UNA volta per episodio, di nuovo al prossimo episodio
# ---------------------------------------------------------------------------
class _DbFinto:
    """Stessa firma del vero ``db.log(kind, payload, event_id)``."""

    def __init__(self) -> None:
        self.righe: list[tuple[str, dict[str, Any], Any]] = []

    def log(self, kind: str, payload: dict[str, Any], event_id: Any = None) -> None:
        self.righe.append((kind, dict(payload), event_id))


def test_avviso_critico_una_volta_per_episodio():
    db = _DbFinto()
    extra: dict[str, Any] = {}
    fuori = {"reason": E.COVER_FUORI_PREZZO, "price_lay_u45": 18.5, "price_limite": 19.5,
             "price_lay_u35": 1.41}
    for _ in range(5):                       # cinque giri di fila nello stesso episodio
        S._avvisa_copertura_fuori_prezzo(db, extra, fuori, "36140993")
    assert len(db.righe) == 1
    kind, payload, eid = db.righe[0]
    assert kind == "error" and eid == "36140993"
    assert payload["reason"] == E.COVER_FUORI_PREZZO and payload["critical"] is True
    assert payload["price_limite"] == 19.5 and payload["price_lay_u35"] == 1.41
    assert "19.5" in payload["nota"] and "1.41" in payload["nota"]

    # l'episodio finisce (attesa per un altro motivo, o copertura partita) ...
    S._avvisa_copertura_fuori_prezzo(db, extra, {"reason": "liquidita"}, "36140993")
    assert len(db.righe) == 1
    # ... e a un episodio nuovo l'avviso esce di nuovo, una volta
    S._avvisa_copertura_fuori_prezzo(db, extra, fuori, "36140993")
    S._avvisa_copertura_fuori_prezzo(db, extra, fuori, "36140993")
    assert len(db.righe) == 2


# ---------------------------------------------------------------------------
# 7. l'ALTRA porta: il riprezzo di una copertura gia' sul libro. Stessa regola.
# ---------------------------------------------------------------------------
def _copertura_sul_libro() -> E.Leg:
    return E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_UNDER, side="lay",
                 price=1.20, size=6.32, matched=0.0, avg_price=None,
                 ref="over_cover-0-4", status="pending", placed_at=KO + 180)


def _in_attesa_di_abbinamento(leg: E.Leg) -> E.MatchCtx:
    return E.MatchCtx(state="LIVE_COVER_PENDING", entry_price_initial=1.41,
                      legs=[ingresso(), leg])


def test_riprezzo_a_quote_normali_resta_quello_di_prima():
    leg = _copertura_sul_libro()
    p = params()
    d = E._riprezzo_copertura_banca(_in_attesa_di_abbinamento(leg),
                                    fotografia(u35=libro(1.40, 1.41), u45=libro(1.24, 1.25)),
                                    p, 0.05, leg)
    assert d.state == "LIVE_COVER_PENDING"
    assert [a.kind for a in d.actions] == ["cancel", "place"]
    nuovo = d.actions[1]
    assert (nuovo.role, nuovo.side, nuovo.size) == ("over_cover", "lay", 6.32)
    assert nuovo.price == E.cover_place_price_lay(1.25, p) and nuovo.price < 1.41


def test_riprezzo_fuori_prezzo_non_parte_e_l_ordine_resta_dov_e():
    leg = _copertura_sul_libro()
    for miglior_banca_u45 in (3.0, 18.5, 1.39):          # 1,39 + 2 tick = 1,41: uguale
        d = E._riprezzo_copertura_banca(
            _in_attesa_di_abbinamento(leg),
            fotografia(u35=libro(1.40, 1.41), u45=libro(1.05, miglior_banca_u45)),
            params(), 0.05, leg)
        assert d.state == "LIVE_COVER_PENDING", miglior_banca_u45
        assert d.actions == [], "ne' annullo ne' ordine nuovo"
        assert d.telemetry["cover_wait"]["reason"] == E.COVER_FUORI_PREZZO
        assert d.telemetry["cover_wait"]["price_lay_u35"] == 1.41


def test_riprezzo_con_under35_non_leggibile_non_parte():
    leg = _copertura_sul_libro()
    d = E._riprezzo_copertura_banca(_in_attesa_di_abbinamento(leg),
                                    fotografia(u35=None, u45=libro(1.24, 1.25)),
                                    params(), 0.05, leg)
    assert d.state == "LIVE_COVER_PENDING" and d.actions == []
    assert d.telemetry["cover_wait"]["reason"] == E.COVER_U35_NON_LEGGIBILE


def test_nessun_altro_punto_del_motore_crea_una_copertura_senza_la_regola():
    """Contratto sul sorgente: OGNI funzione che crea un ordine ``over_cover``
    (banca Under 4,5 o punta Over 4,5, primo piazzamento o riprezzo) contiene la
    regola. Se domani nasce una porta in piu' senza la regola, questo test
    diventa rosso."""
    import inspect
    import re

    sorgente = inspect.getsource(E)
    funzioni = re.split(r"\n(?=def )", sorgente)
    con_copertura = [f for f in funzioni if '_place("over_cover"' in f]
    assert len(con_copertura) == 4, [f.split("(")[0] for f in con_copertura]
    for f in con_copertura:
        nome = f.split("(")[0]
        if '_place("over_cover", MARKET_OU45, SEL_UNDER, "lay"' in f:
            assert "if float(q_lim) >= float(q35) - _EPS:" in f, nome
            assert "COVER_FUORI_PREZZO" in f and "COVER_U35_NON_LEGGIBILE" in f, nome
        else:
            assert '_place("over_cover", MARKET_OU45, SEL_OVER, "back"' in f, nome
            assert "_punta_over45_fuori_prezzo(snap, " in f, nome


# ---------------------------------------------------------------------------
# 8. la forma di prima (PUNTA Over 4,5): stessa regola, sul prezzo equivalente.
#    Puntare l'Over 4,5 a P = bancare l'Under 4,5 a P/(P-1).
# ---------------------------------------------------------------------------
def params_punta(**over):
    return params(cover_form=E.COVER_BACK_O45, **over)


def scoperta_50() -> E.MatchCtx:
    """Punta Under 3,5 da 50,00: la copertura in punta sull'Over viene 5,00 (sopra il
    minimo, dentro il tetto di sovracopertura)."""
    return E.MatchCtx(state="LIVE_UNCOVERED", entry_price_initial=1.41,
                      legs=[ingresso(stake=50.0)])


def foto_over(over_punta: float, *, u35=libro(1.40, 1.41), now=KO + 180) -> E.Snapshot:
    books = {(E.MARKET_OU45, E.SEL_OVER): libro(over_punta, over_punta + 1.0),
             (E.MARKET_OU45, E.SEL_UNDER): libro(1.05, 1.07)}
    if u35 is not None:
        books[(E.MARKET_OU35, E.SEL_UNDER)] = u35
    return E.Snapshot(now=now, ko_at=KO, books=books, inplay=True, minute=3, goals=0,
                      feed_fresh=True, order_fresh=True)


def test_equivalenza_punta_over_banca_under():
    assert E.banca_under45_equivalente(16) == 1.0667
    assert E.banca_under45_equivalente(1.06) == 17.6667
    assert E.banca_under45_equivalente(1.0) is None and E.banca_under45_equivalente(None) is None


def test_forma_punta_over_a_quote_normali_parte_come_prima():
    d = E.decide(scoperta_50(), foto_over(15.0), params_punta())
    assert d.state == "LIVE_COVER_PENDING"
    (a,) = ordini_di_copertura(d)
    assert (a.market, a.selection, a.side) == (E.MARKET_OU45, E.SEL_OVER, "back")
    assert a.price == E.cover_place_price(15.0, params_punta())


def test_forma_punta_over_fuori_prezzo_non_parte():
    # Over 4,5 a 1,06 = banca Under 4,5 a 17,67: lo stesso libro vuoto di Antofagasta
    d = E.decide(scoperta_50(), foto_over(1.06), params_punta())
    assert d.state == "LIVE_UNCOVERED"
    assert ordini_di_copertura(d) == []
    att = d.telemetry["cover_wait"]
    assert att["reason"] == E.COVER_FUORI_PREZZO and att["price_lay_u35"] == 1.41
    assert att["price_limite"] >= 1.41


def test_forma_punta_over_con_under35_non_leggibile_aspetta():
    d = E.decide(scoperta_50(), foto_over(15.0, u35=None), params_punta())
    assert d.state == "LIVE_UNCOVERED" and ordini_di_copertura(d) == []
    assert d.telemetry["cover_wait"]["reason"] == E.COVER_U35_NON_LEGGIBILE


def _punta_over_sul_libro() -> E.Leg:
    return E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER, side="back",
                 price=14.0, size=5.0, matched=0.0, avg_price=None,
                 ref="over_cover-0-4", status="pending", placed_at=KO + 100)


def test_forma_punta_over_riprezzo_fuori_prezzo_non_parte():
    leg = _punta_over_sul_libro()
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", entry_price_initial=1.41,
                     legs=[ingresso(stake=50.0), leg])
    normale = E.decide(ctx, foto_over(15.0, now=KO + 180), params_punta())
    # a quote normali il riprezzo parte come prima: prima l'annullo, il nuovo ordine
    # dopo la conferma (guardia «mai sovracopertura», gia' esistente)
    assert [a.kind for a in normale.actions] == ["cancel"], normale.reason
    assert "riprezzo" in normale.reason
    fuori = E.decide(ctx, foto_over(1.06, now=KO + 180), params_punta())
    assert fuori.state == "LIVE_COVER_PENDING" and fuori.actions == []
    assert fuori.telemetry["cover_wait"]["reason"] == E.COVER_FUORI_PREZZO


def test_il_servizio_chiama_l_avviso_quando_registra_l_attesa_della_copertura():
    """Contratto sul sorgente: il giro vero del servizio (``_run_event``), nel punto
    in cui registra ``cover_wait``, chiama l'avviso. Senza questa riga la regola
    fermerebbe l'ordine ma il trader non lo saprebbe."""
    import inspect

    sorgente = inspect.getsource(S._run_event)
    assert '_avvisa_copertura_fuori_prezzo(db, extra, v, ev["event_id"])' in sorgente


def test_forma_punta_over_minore_non_minore_o_uguale():
    """Punta Over 4,5 a 2,00 = banca Under 4,5 a 2,00: con la banca dell'Under 3,5 a
    2,00 (uguale) NON parte; a 2,02 (l'equivalente e' minore) parte."""
    uguale = foto_over(15.0, u35=libro(1.98, 2.00))
    assert E._punta_over45_fuori_prezzo(uguale, 2.0) == (E.COVER_FUORI_PREZZO, 2.0, 2.0)
    minore = foto_over(15.0, u35=libro(2.00, 2.02))
    assert E._punta_over45_fuori_prezzo(minore, 2.0) is None
