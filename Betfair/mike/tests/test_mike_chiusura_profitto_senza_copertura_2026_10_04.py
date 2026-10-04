"""04/10/2026 - SECONDA CONDIZIONE DELL'UTENTE: quando Mike non puo' coprirsi ed e'
in attesa, controlla se l'Under 3,5 si puo' chiudere IN PROFITTO.

Testuale: «quando non si puo' coprire ed e' in attesa, controlla SE UNDER 3.5 puo'
essere chiuso in profitto, SE SI, chiude (minimo 2 tick) e se chiusura confermata,
nessuna copertura e' necessaria, SE UNDER 3.5 non e' in profitto, continua a
controllare se e' possibile la copertura».

Confermato con lui:
  * vale SOLO quando la copertura non si puo' eseguire (prezzo fuori regola, libro
    Under 4,5 vuoto o senza prezzo, liquidita' insufficiente), NON nell'attesa
    programmata;
  * «2 tick di profitto»: la banca dell'Under 3,5 e' ad almeno 2 tick sotto il
    prezzo d'ingresso (ingresso 1,41 -> 1,39 o meno);
  * importo = quello che lascia lo stesso profitto qualunque sia il finale;
  * parte da sola (e' un'uscita in profitto);
  * chiusura mandata ma non abbinata = non confermata: si resta scoperti e si
    rifanno i due controlli.

Finti: gli oggetti veri dell'engine (Leg, Book, Snapshot, MatchCtx, Decision).
"""
from __future__ import annotations

from typing import Optional

from Betfair.mike import config as C
from Betfair.mike import engine as E

KO = 1_800_000_000.0
ADESSO = KO + 600


def params(**over):
    p = C.merge_params(None)          # uscite MANUALI di serie: la chiusura in profitto parte lo stesso
    p["cover_form"] = E.COVER_LAY_U45
    p["cover_policy"] = "immediate"
    p.update(over)
    return p


def ingresso(stake=5.0, prezzo=1.41) -> E.Leg:
    return E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                 price=prezzo, size=stake, matched=stake, avg_price=prezzo,
                 ref="under_entry-0-1", status="open", placed_at=KO - 600)


def libro(bb: Optional[float], bl: Optional[float], bs=500.0, ls=500.0) -> E.Book:
    return E.Book(best_back=bb, back_size=bs, best_lay=bl, lay_size=ls, status="OPEN",
                  inplay=True)


LIBRO_U45_VUOTO = libro(1.05, 18.5)          # Antofagasta: copertura fuori prezzo
LIBRO_U45_NORMALE = libro(1.20, 1.21)


def fotografia(banca_u35: float, *, u45: E.Book = LIBRO_U45_VUOTO, now=ADESSO, goals=0,
               liquidita_u35=500.0) -> E.Snapshot:
    books = {(E.MARKET_OU35, E.SEL_UNDER): libro(round(banca_u35 - 0.01, 2), banca_u35,
                                                 ls=liquidita_u35),
             (E.MARKET_OU45, E.SEL_UNDER): u45,
             (E.MARKET_OU45, E.SEL_OVER): libro(15.0, 16.0)}
    return E.Snapshot(now=now, ko_at=KO, books=books, inplay=True, minute=10, goals=goals,
                      feed_fresh=True, order_fresh=True)


def scoperta(*altre: E.Leg) -> E.MatchCtx:
    return E.MatchCtx(state="LIVE_UNCOVERED", entry_price_initial=1.41,
                      legs=[ingresso(), *altre], live_since=KO, ko_goals=0)


def piazzati(d: E.Decision, ruolo: str):
    return [a for a in d.actions if a.kind == "place" and a.role == ruolo]


def chiusura(*, matched: float, status: str, size=5.07, prezzo=1.39, at=ADESSO - 2) -> E.Leg:
    return E.Leg(role="under_close", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                 price=prezzo, size=size, matched=matched,
                 avg_price=prezzo if matched > 0 else None,
                 ref="under_close-0-5", status=status, placed_at=at)


# ---------------------------------------------------------------------------
# 1. non copribile + Under 3,5 in profitto di 2 tick: CHIUDE
# ---------------------------------------------------------------------------
def test_non_copribile_e_under35_a_2_tick_chiude_5_07_a_1_39():
    d = E.decide(scoperta(), fotografia(1.39), params())
    assert piazzati(d, "over_cover") == []
    (a,) = piazzati(d, "under_close")
    assert (a.market, a.selection, a.side) == (E.MARKET_OU35, E.SEL_UNDER, "lay")
    assert (a.price, a.size) == (1.39, 5.07)
    assert d.state == "LIVE_UNCOVERED"          # confermata solo quando e' abbinata


def test_piu_profitto_importo_che_pareggia_i_due_finali():
    d = E.decide(scoperta(), fotografia(1.36), params())
    (a,) = piazzati(d, "under_close")
    assert (a.price, a.size) == (1.36, 5.18)    # 5,00 x 1,41 / 1,36
    # stesso profitto, al centesimo dell'arrotondamento dell'importo, con Under
    # vinto (2,05 - 5,18 x 0,36 = 0,19) e perso (5,18 - 5,00 = 0,18)
    vinto, perso = 5.0 * 0.41 - a.size * (a.price - 1.0), a.size - 5.0
    assert abs(vinto - perso) <= 0.011 and round(perso, 2) == 0.18


def test_dopo_un_gol_chiude_e_non_apre_niente_di_nuovo():
    ctx = scoperta()
    d = E.decide(ctx, fotografia(1.39, goals=1), params())
    assert [a.role for a in d.actions if a.kind == "place"] == ["under_close"]
    assert d.state == "LIVE_UNCOVERED"


# ---------------------------------------------------------------------------
# 2. Under 3,5 NON in profitto di almeno 2 tick: non chiude, continua ad aspettare
# ---------------------------------------------------------------------------
def test_un_solo_tick_o_in_perdita_non_chiude():
    for banca in (1.40, 1.41, 1.45):
        d = E.decide(scoperta(), fotografia(banca), params())
        assert d.state == "LIVE_UNCOVERED", banca
        assert [a for a in d.actions if a.kind == "place"] == [], banca
        assert d.telemetry["cover_wait"]["reason"] == E.COVER_FUORI_PREZZO


def test_liquidita_insufficiente_sull_under35_non_chiude():
    d = E.decide(scoperta(), fotografia(1.39, liquidita_u35=3.0), params())
    assert [a for a in d.actions if a.kind == "place"] == []


# ---------------------------------------------------------------------------
# 3. se la copertura SI PUO' fare, si copre come sempre (anche con l'Under in profitto)
# ---------------------------------------------------------------------------
def test_copertura_possibile_copre_e_non_chiude():
    d = E.decide(scoperta(), fotografia(1.39, u45=LIBRO_U45_NORMALE), params())
    assert d.state == "LIVE_COVER_PENDING"
    assert piazzati(d, "under_close") == []
    (a,) = piazzati(d, "over_cover")
    assert a.size == 6.32


def test_attesa_programmata_non_e_non_copribile():
    """L'attesa in cui Mike aspetta apposta il momento migliore non ha un motivo
    di «copertura non eseguibile»: la chiusura in profitto non scatta."""
    programmata = E.Decision("LIVE_UNCOVERED", [], "attendo per coprire",
                             telemetry={"cover_wait": {"minute": 10, "goals": 0}})
    assert E._chiusura_in_profitto_se_non_copribile(scoperta(), fotografia(1.36), params(),
                                                    programmata) is None
    for motivo in ("liquidita", "libro_under45_assente", "nessun_prezzo_lay_under45",
                   E.COVER_FUORI_PREZZO):
        non_eseguibile = E.Decision("LIVE_UNCOVERED", [], "copertura: ...",
                                    telemetry={"cover_wait": {"reason": motivo}})
        d = E._chiusura_in_profitto_se_non_copribile(scoperta(), fotografia(1.36), params(),
                                                     non_eseguibile)
        assert d is not None and piazzati(d, "under_close"), motivo


# ---------------------------------------------------------------------------
# 4. chiusura CONFERMATA (abbinata): partita chiusa, nessuna copertura
# ---------------------------------------------------------------------------
def test_chiusura_abbinata_partita_chiusa_senza_copertura():
    ctx = scoperta(chiusura(matched=5.07, status="open"))
    d = E.decide(ctx, fotografia(1.39), params())
    assert d.state == "FLAT"
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.updates.get("close_reason") == "profit"
    assert "senza copertura" in d.reason


# ---------------------------------------------------------------------------
# 5. chiusura NON confermata: si resta scoperti e si rifanno i controlli
# ---------------------------------------------------------------------------
def test_chiusura_ancora_sul_libro_si_ritira():
    viva = chiusura(matched=0.0, status="pending")
    d = E.decide(scoperta(viva), fotografia(1.41), params())
    assert d.state == "LIVE_UNCOVERED"
    assert [(a.kind, a.ref) for a in d.actions] == [("cancel", viva.ref)]


def test_chiusura_non_abbinata_si_torna_ai_due_controlli():
    andata_a_vuoto = chiusura(matched=0.0, status="cancelled", at=ADESSO - 60)
    # la copertura e' tornata possibile: si copre
    d = E.decide(scoperta(andata_a_vuoto), fotografia(1.41, u45=LIBRO_U45_NORMALE), params())
    assert d.state == "LIVE_COVER_PENDING" and piazzati(d, "over_cover")
    # la copertura non e' possibile e l'Under e' di nuovo in profitto: richiude
    d2 = E.decide(scoperta(andata_a_vuoto), fotografia(1.39), params())
    assert piazzati(d2, "under_close")


def test_non_si_riprova_prima_di_close_retry_s():
    p = params()
    appena = chiusura(matched=0.0, status="cancelled", at=ADESSO - 1)
    d = E.decide(scoperta(appena), fotografia(1.39), p)
    assert [a for a in d.actions if a.kind == "place"] == []
    dopo = chiusura(matched=0.0, status="cancelled", at=ADESSO - float(p["close_retry_s"]) - 1)
    d2 = E.decide(scoperta(dopo), fotografia(1.39), p)
    assert piazzati(d2, "under_close")
