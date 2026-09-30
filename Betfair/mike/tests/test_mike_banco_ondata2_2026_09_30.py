"""BANCO DI MIKE, ONDATA 2 (30/09): i controlli che non si sollecitavano mai.

Revisione critica del 30/09 (``AUDIT_2026-09-30/REVISIONE_CRITICA_MIKE_29_09.md``),
punti A1, A6, A7, M2, M8 e BASSO. Qui le prove UNITARIE dei controlli nuovi o
riscritti; i casi sulla registrazione vera stanno nei referti dei replay
(``AUDIT_2026-09-30/BANCO_MIKE_ONDATA_2.md``).

  * G2 sul NUMERO: una chiusura che parte da uno stato non di chiusura e blocca
    un netto NEGATIVO senza la firma valida della STESSA chiave, dello STESSO
    motivo e non scaduta e' una violazione, qualunque motivo scriva il motore
    (un motivo ``profit`` su una chiusura in perdita non la salva piu'). La
    mutazione B-5 della revisione (G2 senza il confronto della chiave) qui e'
    ROSSA: ``test_g2_firma_di_un_altra_chiave_parla``.
  * G4, la firma ESEGUITA: dopo una firma valida gli ordini di chiusura
    arrivano al mercato entro ``FIRMA_ESEGUITA_ENTRO_S`` secondi di mercato.
  * E2 della forma di serie (punta Over 4,5): parametri VERI (``commission_pct``,
    ``cover_profit_factor``) e violazione anche per una copertura piu' piccola
    del dovuto senza tetto.
  * B7: al segno dei 10 minuti, da piatto e con tutte le condizioni d'ingresso
    vere, l'ultimo ingresso AVVIENE.
  * RG1: il P&L e l'esito per riga scritti da Mike al regolamento coincidono
    con quelli del banco.

Finti: le classi VERE del motore (``MatchCtx``, ``Leg``, ``Snapshot``, ``Book``,
``Decision``, ``Action``), i parametri da ``config.merge_params``; le righe di
``mike_trades`` hanno le colonne vere (``id``, ``bet_id``, ``status``, ``pnl``,
``meta.pnl_gross``). ASCII-only.
"""
from __future__ import annotations

from typing import Dict

import pytest

from Betfair.mike import certificazione as CERT
from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike.tests.test_mike_engine import (KO, _live_covered, book, fill, params,
                                                 snap)


def _perdita_ht():
    """2 gol all'intervallo: uscita in perdita tollerata (motore vero)."""
    return snap(KO + 46 * 60, u35=book(2.20, bl=2.24, inplay=True),
                o45=book(6.0, bl=6.2, inplay=True), inplay=True, minute=45, goals=2,
                ht_active=True)


def _cashout_in_profitto():
    return snap(KO + 30 * 60, u35=book(1.30, bl=1.31, inplay=True),
                o45=book(12.0, bl=12.5, inplay=True), inplay=True, minute=30, goals=0)


def _viola(ctx, s, d, p, codice):
    sollecitati: Dict[str, int] = {}
    v = CERT.verifica(ctx, s, d, p, sollecitati)
    return sollecitati.get(codice, 0), [x for x in v if x.codice == codice]


def _uscita_in_perdita_vera():
    """La decisione del motore VERO in automatico (uscita in perdita con ordini),
    giudicata poi con l'interruttore su manuale."""
    ctx, pa = _live_covered()
    d = E.decide(ctx, _perdita_ht(), pa)
    assert [a.role for a in d.actions if a.kind == "place"], d.reason
    assert str(d.updates.get("close_reason") or "").startswith("loss")
    return ctx, d, dict(pa, uscite_automatiche=False)


def _firma(ctx, d, *, chiave="chiusura|c0", motivo=None, at=None):
    ctx.uscita_proposta = {"chiave": "chiusura|c0",
                           "close_reason": d.updates["close_reason"] if motivo is None else motivo}
    ctx.uscita_approvata = {"chiave": chiave,
                            "at": (_perdita_ht().now - 5.0) if at is None else at}


# ===========================================================================
# G2 sul NUMERO
# ===========================================================================
def test_g2_uscita_in_perdita_senza_firma_parla_col_suo_numero():
    ctx, d, pm = _uscita_in_perdita_vera()
    valore = CERT.valore_uscita(ctx, _perdita_ht(), d, pm)
    assert valore is not None and valore < -0.05, valore
    n, v = _viola(ctx, _perdita_ht(), d, pm, "G2")
    assert n == 1 and len(v) == 1
    assert "senza la sua firma" in v[0].dettaglio


def test_g2_motivo_profit_su_una_chiusura_in_perdita_non_la_salva():
    """Il motore che classifica male (motivo ``profit`` su una chiusura che
    blocca un negativo) non passa piu' muto: il controllo guarda il numero."""
    ctx, d, pm = _uscita_in_perdita_vera()
    d.updates["close_reason"] = "profit"
    n, v = _viola(ctx, _perdita_ht(), d, pm, "G2")
    assert n == 1 and len(v) == 1, v


def test_g2_con_la_sua_firma_tace():
    ctx, d, pm = _uscita_in_perdita_vera()
    _firma(ctx, d)
    n, v = _viola(ctx, _perdita_ht(), d, pm, "G2")
    assert n == 1 and v == []


def test_g2_firma_di_un_altra_chiave_parla():
    """Mutazione B-5 della revisione del 30/09: la firma porta la chiave di
    un'altra uscita (``chiusura|c1``), la proposta viva quella di questa. Se il
    controllo non confronta la chiave della firma con quella della proposta,
    questo test diventa ROSSO."""
    ctx, d, pm = _uscita_in_perdita_vera()
    _firma(ctx, d, chiave="chiusura|c1")
    n, v = _viola(ctx, _perdita_ht(), d, pm, "G2")
    assert n == 1 and len(v) == 1


def test_g2_proposta_e_firma_di_un_altra_categoria_parla():
    """Firma e proposta concordi fra loro ma su un'ALTRA uscita (banca al
    fischio): la chiusura di adesso non e' quella firmata."""
    ctx, d, pm = _uscita_in_perdita_vera()
    ctx.uscita_proposta = {"chiave": "ko_green|c0",
                           "close_reason": d.updates["close_reason"]}
    ctx.uscita_approvata = {"chiave": "ko_green|c0", "at": _perdita_ht().now - 5.0}
    n, v = _viola(ctx, _perdita_ht(), d, pm, "G2")
    assert n == 1 and len(v) == 1


def test_g2_firma_su_un_altro_motivo_parla():
    ctx, d, pm = _uscita_in_perdita_vera()
    _firma(ctx, d, motivo="loss_2t")
    n, v = _viola(ctx, _perdita_ht(), d, pm, "G2")
    assert n == 1 and len(v) == 1


def test_g2_firma_scaduta_parla():
    ctx, d, pm = _uscita_in_perdita_vera()
    _firma(ctx, d, at=_perdita_ht().now - E.APPROVAZIONE_TTL_S - 1.0)
    n, v = _viola(ctx, _perdita_ht(), d, pm, "G2")
    assert n == 1 and len(v) == 1


def test_g2_uscite_automatiche_ha_il_caso_e_tace():
    ctx, d, pm = _uscita_in_perdita_vera()
    pa = dict(pm, uscite_automatiche=True)
    n, v = _viola(ctx, _perdita_ht(), d, pa, "G2")
    assert n == 1 and v == []


def test_g2_uscita_in_profitto_non_e_un_caso():
    ctx, p = _live_covered()
    p["uscite_automatiche"] = False
    s = _cashout_in_profitto()
    d = E.decide(ctx, s, p)
    assert [a.role for a in d.actions if a.kind == "place"], d.reason
    assert CERT.valore_uscita(ctx, s, d, p) > 0
    n, v = _viola(ctx, s, d, p, "G2")
    assert n == 0 and v == []


def test_g2_chiusura_manuale_dell_utente_non_e_un_caso():
    """Il cash out dell'utente E' la sua firma (``flatten_pending``)."""
    ctx, d, pm = _uscita_in_perdita_vera()
    ctx.flatten_pending = True
    n, v = _viola(ctx, _perdita_ht(), d, pm, "G2")
    assert n == 0 and v == []


def test_g2_riprezzo_di_un_uscita_gia_in_corso_non_e_un_caso():
    ctx, d, pm = _uscita_in_perdita_vera()
    ctx.state = "LIVE_CLOSING"
    n, v = _viola(ctx, _perdita_ht(), d, pm, "G2")
    assert n == 0 and v == []


def test_g2_tetto_di_perdita_parla_sempre():
    ctx, pa = _live_covered()
    d = E.Decision("LIVE_CLOSING", [E.Action(kind="place", role="under_close",
                                             market=E.MARKET_OU35, selection=E.SEL_UNDER,
                                             side="lay", price=2.24, size=13.4)],
                   "cap perdita evento: -3.00", {"close_reason": "loss_cap"})
    n, v = _viola(ctx, _perdita_ht(), d, pa, "G2")
    assert n == 1 and len(v) == 1 and "M4.5" in v[0].dettaglio


def _rientro_aperto(prezzo_ora: float):
    """Rientro aperto: punta Under 4,5 abbinata a 3,00; libro a ``prezzo_ora``."""
    ctx = E.MatchCtx(state="REENTRY_OPEN")
    ctx.legs.append(fill(E.Leg(role="reentry", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                               side="back", price=3.0, size=5.0, ref="reentry-0-5")))
    s = snap(KO + 40 * 60, u45=book(prezzo_ora, bl=E.ticks_away(prezzo_ora, 1), inplay=True),
             inplay=True, minute=40, goals=1)
    size = round(5.0 * 3.0 / E.ticks_away(prezzo_ora, 1), 2)
    d = E.Decision("REENTRY_GREEN_PENDING",
                   [E.Action(kind="place", role="reentry_green", market=E.MARKET_OU45,
                             selection=E.SEL_UNDER, side="lay",
                             price=E.ticks_away(prezzo_ora, 1), size=size)],
                   "rientro: chiusura a tempo", {"close_reason": "reentry_time"})
    return ctx, s, d


def test_g2_chiusura_a_tempo_del_rientro_in_profitto_senza_firma_e_lecita():
    """Decisione dell'utente (30/09, consegna del delegato del bot): la chiusura
    a tempo del rientro (``reentry_time``) parte DA SOLA quando chiude in
    profitto. Il vecchio G2 la dava sempre in perdita dal motivo: sul numero
    non e' un caso."""
    p = params(uscite_automatiche=False)
    ctx, s, d = _rientro_aperto(2.0)          # la quota e' scesa: profitto
    assert CERT.valore_uscita(ctx, s, d, p) > 0
    n, v = _viola(ctx, s, d, p, "G2")
    assert n == 0 and v == []


def test_g2_chiusura_a_tempo_del_rientro_in_perdita_senza_firma_parla():
    p = params(uscite_automatiche=False)
    ctx, s, d = _rientro_aperto(4.5)          # la quota e' salita: perdita
    assert CERT.valore_uscita(ctx, s, d, p) < 0
    n, v = _viola(ctx, s, d, p, "G2")
    assert n == 1 and len(v) == 1


def test_valore_uscita_banca_al_fischio_in_profitto():
    """La banca a +2 tick sull'Under abbinato a 1,50 blocca un profitto."""
    ctx = E.MatchCtx(state="LIVE_KO_GREEN")
    ctx.legs.append(fill(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="back", price=1.50, size=10.0, ref="under_entry-0-1")))
    s = snap(KO + 60, u35=book(1.46, bl=1.47, inplay=True), inplay=True, minute=1, goals=0)
    d = E.Decision("LIVE_KO_GREEN", [E.Action(kind="place", role="ko_green",
                                              market=E.MARKET_OU35, selection=E.SEL_UNDER,
                                              side="lay", price=1.46, size=10.27)], "ko")
    assert CERT.valore_uscita(ctx, s, d, params()) > 0


# ===========================================================================
# G4: la firma ESEGUITA
# ===========================================================================
def test_g4_firma_eseguita_in_tempo_tace():
    sf = CERT.SorveglianzaFirme()
    sol: Dict[str, int] = {}
    sf.firma("chiusura|c0", 1000.0)
    sf.esecuzione(1002.0)
    assert sf.giro(1004.0, proposta_viva=False, firma_viva=False, sollecitati=sol) == []
    sf.ordine(1007.0, "1.2", "lay")
    assert sf.giro(1008.0, proposta_viva=False, firma_viva=False, sollecitati=sol) == []
    assert sf.giro(1000.0 + 10 * CERT.FIRMA_ESEGUITA_ENTRO_S, proposta_viva=False,
                   firma_viva=False, sollecitati=sol) == []
    assert sol.get("G4", 0) >= 1
    assert sf.eseguite == 1 and sf.violate == 0


def test_g4_firma_consumata_senza_ordini_parla():
    """E' il difetto C1 del 29/09: la firma passa il cancello, il servizio
    rifiuta la chiusura (``no_fill feed_stantio``) e al mercato non arriva niente."""
    sf = CERT.SorveglianzaFirme()
    sol: Dict[str, int] = {}
    sf.firma("chiusura|c0", 1000.0)
    sf.esecuzione(1002.0)
    assert sf.giro(1030.0, proposta_viva=False, firma_viva=False, sollecitati=sol) == []
    v = sf.giro(1002.0 + CERT.FIRMA_ESEGUITA_ENTRO_S + 1.0, proposta_viva=False,
                firma_viva=False, sollecitati=sol)
    assert len(v) == 1 and v[0].codice == "G4"
    # una volta sola per firma
    assert sf.giro(2000.0, proposta_viva=False, firma_viva=False, sollecitati=sol) == []


def test_g4_firma_ignorata_parla():
    sf = CERT.SorveglianzaFirme()
    sf.firma("chiusura|c0", 1000.0)
    v = sf.giro(1000.0 + CERT.FIRMA_ESEGUITA_ENTRO_S + 1.0, proposta_viva=True,
                firma_viva=True, sollecitati={})
    assert len(v) == 1 and "mai eseguita" in v[0].dettaglio


def test_g4_proposta_decaduta_non_e_una_violazione():
    sf = CERT.SorveglianzaFirme()
    sf.firma("chiusura|c0", 1000.0)
    assert sf.giro(1004.0, proposta_viva=False, firma_viva=False, sollecitati={}) == []
    assert sf.giro(1000.0 + 5 * CERT.FIRMA_ESEGUITA_ENTRO_S, proposta_viva=False,
                   firma_viva=False, sollecitati={}) == []
    assert sf.decadute == 1 and sf.violate == 0


def test_g4_un_ordine_di_prima_della_firma_non_conta():
    sf = CERT.SorveglianzaFirme()
    sf.ordine(999.0, "1.2", "lay")
    sf.firma("chiusura|c0", 1000.0)
    sf.esecuzione(1001.0)
    v = sf.giro(1001.0 + CERT.FIRMA_ESEGUITA_ENTRO_S + 1.0, proposta_viva=False,
                firma_viva=False, sollecitati={})
    assert len(v) == 1


# ===========================================================================
# E2 della forma di serie (punta Over 4,5)
# ===========================================================================
def _uncovered(p):
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", entry_price_initial=1.50)
    ctx.legs.append(fill(E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="back", price=1.50, size=20.0, persistence="PERSIST")))
    return ctx


def _snap_cover(prezzo=9.0):
    return snap(KO + 20 * 60, u35=book(1.35, inplay=True), o45=book(prezzo, bs=500, inplay=True),
                inplay=True, minute=20, goals=0, hazard=0.05, p4_market=0.12)


def _punta(size, prezzo=8.6):
    return E.Action(kind="place", role="over_cover", market=E.MARKET_OU45,
                    selection=E.SEL_OVER, side="back", price=prezzo, size=size)


def _dovuta(p, prezzo=9.0):
    c = C.commission_rate(p)
    return round(E.cover_residual(20.0, prezzo, c, float(p["cover_profit_factor"]), 0.0), 2)


def test_e2_punta_del_motore_vero_tace():
    p = params(cover_form=E.COVER_BACK_O45)
    ctx = _uncovered(p)
    s = _snap_cover()
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVER_PENDING"
    n, v = _viola(ctx, s, d, p, "E2")
    assert n == 1 and v == []


def test_e2_punta_piu_piccola_senza_tetto_parla():
    p = params(cover_form=E.COVER_BACK_O45, max_liability_per_match=0.0)
    ctx = _uncovered(p)
    for frazione in (0.5, 0.9):
        size = round(_dovuta(p) * frazione, 2)
        n, v = _viola(ctx, _snap_cover(), E.Decision("LIVE_COVER_PENDING", [_punta(size)], "c"),
                      p, "E2")
        assert n == 1 and len(v) == 1, size


def test_e2_punta_ridotta_dal_tetto_tace():
    p = params(cover_form=E.COVER_BACK_O45)
    ctx = _uncovered(p)
    room = E.liability_room(ctx, p)
    if room == float("inf") or room > _dovuta(p):
        p = params(cover_form=E.COVER_BACK_O45, max_liability_per_match=21.0)
        room = E.liability_room(ctx, p)
    assert room < _dovuta(p)
    n, v = _viola(ctx, _snap_cover(), E.Decision("LIVE_COVER_PENDING",
                                                 [_punta(round(room, 2))], "c"), p, "E2")
    assert n == 1 and v == []


def test_e2_punta_legge_la_commissione_vera():
    """Prima leggeva ``params['commission']`` (inesistente): valeva sempre il 5 %.
    Con la commissione al 2 % la copertura dimensionata al 5 % e' sbagliata."""
    p2 = params(cover_form=E.COVER_BACK_O45, commission_pct=2.0)
    p5 = params(cover_form=E.COVER_BACK_O45)
    ctx = _uncovered(p2)
    giusta_al_5 = _dovuta(p5)
    assert abs(giusta_al_5 - _dovuta(p2)) > 0.05
    n, v = _viola(ctx, _snap_cover(), E.Decision("LIVE_COVER_PENDING", [_punta(giusta_al_5)], "c"),
                  p2, "E2")
    assert n == 1 and len(v) == 1
    n, v = _viola(ctx, _snap_cover(), E.Decision("LIVE_COVER_PENDING", [_punta(_dovuta(p2))], "c"),
                  p2, "E2")
    assert n == 1 and v == []


def test_e2_punta_legge_il_fattore_vero():
    p = params(cover_form=E.COVER_BACK_O45, cover_profit_factor=1.5)
    ctx = _uncovered(p)
    al_12 = _dovuta(params(cover_form=E.COVER_BACK_O45))
    n, v = _viola(ctx, _snap_cover(), E.Decision("LIVE_COVER_PENDING", [_punta(al_12)], "c"),
                  p, "E2")
    assert n == 1 and len(v) == 1


def test_e2_punta_gonfiata_parla():
    p = params(cover_form=E.COVER_BACK_O45)
    ctx = _uncovered(p)
    n, v = _viola(ctx, _snap_cover(), E.Decision("LIVE_COVER_PENDING",
                                                 [_punta(round(_dovuta(p) * 1.6, 2))], "c"),
                  p, "E2")
    assert n == 1 and len(v) == 1


# ===========================================================================
# B7: l'ultimo ingresso AVVIENE da piatto al segno
# ===========================================================================
def _al_segno(p, **over):
    s = snap(KO - float(p["pre_last_entry_min"]) * 60.0 + 30.0, u35=book(1.50, bl=1.51))
    return s


def test_b7_da_piatto_col_libro_buono_l_ingresso_nasce_e_tace():
    p = params()
    ctx = E.MatchCtx(state="WATCH")
    s = _al_segno(p)
    d = E.decide(ctx, s, p)
    assert [a.role for a in d.actions if a.kind == "place"] == ["under_entry"], d.reason
    n, v = _viola(ctx, s, d, p, "B7")
    assert n == 1 and v == []


def test_b7_da_piatto_senza_ingresso_parla():
    p = params()
    ctx = E.MatchCtx(state="WATCH")
    s = _al_segno(p)
    d = E.Decision("HOLD", [], "ultimo ingresso: nessun ingresso fino al fischio")
    n, v = _viola(ctx, s, d, p, "B7")
    assert n == 1 and len(v) == 1


@pytest.mark.parametrize("caso", ["non_piatto", "libro_fuori_banda", "gia_valutato",
                                  "bot_fermo", "prima_del_segno", "stantio"])
def test_b7_senza_le_condizioni_non_e_un_caso(caso):
    p = params()
    ctx = E.MatchCtx(state="WATCH")
    s = _al_segno(p)
    if caso == "non_piatto":
        ctx.state = "PRE_OPEN"
    elif caso == "libro_fuori_banda":
        s = snap(s.now, u35=book(float(p["pre_entry_price_max"]) + 0.5))
    elif caso == "gia_valutato":
        ctx.legs.append(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                              side="back", price=1.5, size=10.0, ref="under_entry-0-1",
                              status="cancelled", placed_at=s.now - 5.0))
    elif caso == "bot_fermo":
        p = params(pre_enabled=False)
    elif caso == "prima_del_segno":
        s = snap(KO - float(p["pre_last_entry_min"]) * 60.0 - 60.0, u35=book(1.50, bl=1.51))
    elif caso == "stantio":
        s = snap(s.now, u35=book(1.50, bl=1.51), feed_fresh=False)
    d = E.Decision("HOLD", [], "x")
    n, v = _viola(ctx, s, d, p, "B7")
    assert n == 0 and v == []


# ===========================================================================
# RG1: il regolamento di Mike contro quello del banco
# ===========================================================================
def _riga(i, bet, stato, pnl, lordo):
    return {"id": i, "bet_id": bet, "status": stato, "pnl": pnl, "size": 10.0,
            "meta": {"pnl_gross": lordo}}


def test_rg1_regolamento_uguale_tace():
    righe = [_riga(1, "b1", "lost", -10.0, -10.0), _riga(2, "b2", "won", 7.12, 7.5)]
    esiti = {"b1": {"esito": "lost", "lordo": -10.0}, "b2": {"esito": "won", "lordo": 7.5}}
    sol: Dict[str, int] = {}
    v = CERT.confronta_regolamento("SETTLED", -2.88, righe, esiti, -2.88, sol)
    assert v == [] and sol.get("RG1") == 1


@pytest.mark.parametrize("guasto", ["pnl_partita", "esito_riga", "lordo_riga", "riga_aperta"])
def test_rg1_differenza_parla(guasto):
    righe = [_riga(1, "b1", "lost", -10.0, -10.0), _riga(2, "b2", "won", 7.12, 7.5)]
    esiti = {"b1": {"esito": "lost", "lordo": -10.0}, "b2": {"esito": "won", "lordo": 7.5}}
    pnl = -2.88
    if guasto == "pnl_partita":
        pnl = -2.50
    elif guasto == "esito_riga":
        righe[1]["status"] = "lost"
    elif guasto == "lordo_riga":
        righe[1]["meta"]["pnl_gross"] = 9.0
    elif guasto == "riga_aperta":
        righe[1]["status"] = "open"
    v = CERT.confronta_regolamento("SETTLED", pnl, righe, esiti, -2.88, {})
    assert len(v) >= 1 and all(x.codice == "RG1" for x in v)


def test_rg1_riga_error_mai_abbinata_vale_void():
    righe = [_riga(1, "b1", "lost", -10.0, -10.0), _riga(3, "b3", "error", 0.0, None)]
    esiti = {"b1": {"esito": "lost", "lordo": -10.0}, "b3": {"esito": "void", "lordo": 0.0}}
    assert CERT.confronta_regolamento("SETTLED", -10.0, righe, esiti, -10.0, {}) == []
    righe[1]["pnl"] = -3.0          # una riga 'error' con P&L e' un'altra cosa
    assert len(CERT.confronta_regolamento("SETTLED", -10.0, righe, esiti, -10.0, {})) == 1


def test_rg1_partita_non_regolata_non_e_un_caso():
    sol: Dict[str, int] = {}
    assert CERT.confronta_regolamento("LIVE_COVERED", None, [], {}, -2.0, sol) == []
    assert not sol.get("RG1")


@pytest.mark.parametrize("terminale", E.TERMINAL_STATES)
def test_a2_falsificato_decisione_da_stato_terminale(terminale):
    """A2 e' la seconda linea di difesa (il servizio non chiama ``decide`` su
    uno stato terminale): la sua falsificazione, dichiarata nel referto, e' qui.
    Una decisione con azioni da uno stato terminale e' ROSSA; senza azioni tace."""
    ctx = E.MatchCtx(state=terminale)
    s = snap(KO + 7200, inplay=True, minute=90, goals=4)
    d = E.Decision(terminale, [E.Action(kind="place", role="under_close", market=E.MARKET_OU35,
                                        selection=E.SEL_UNDER, side="lay", price=1.5,
                                        size=2.0)], "fuori regola")
    n, v = _viola(ctx, s, d, params(), "A2")
    assert n == 1 and len(v) == 1
    n, v = _viola(ctx, s, E.Decision(terminale, [], "terminale"), params(), "A2")
    assert n == 1 and v == []


def test_elenco_stati_e_quello_del_motore():
    assert tuple(CERT.elenco_stati()) == E.STATES
    assert CERT.stati_mai_visti(["WATCH", "SETTLED"]) == [s for s in E.STATES
                                                          if s not in ("WATCH", "SETTLED")]
