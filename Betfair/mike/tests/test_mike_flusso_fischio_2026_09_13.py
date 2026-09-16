"""Flusso di Mike DAL FISCHIO D'INIZIO (specifica utente del 13/09/2026).

Nessuna rete, nessun DB. File ASCII-only (console Windows cp1252).

Che cosa deve fare il bot
-------------------------
La gamba Under 3.5 abbinata nel pre-match e non chiusa entra in gioco cosi'
com'e': la persistenza riguarda solo l'ineseguito, una posizione gia' abbinata
non viene toccata dal passaggio in-play. Da li' le strade sono tre, e una sola
si realizza.

  STRADA A  L'ordine opposto, appoggiato a 2 tick di profitto dal nostro punto
            di ingresso e tenuto 3 minuti dal fischio, si abbina: profitto
            bloccato, NESSUNA copertura comprata, capitale libero.

  STRADA B  I 3 minuti scadono senza gol e senza abbinamento: si annulla
            l'ordine e si compra la copertura PIENA sull'Over 4.5.

  STRADA C  Arriva un gol dentro i 3 minuti mentre siamo ancora scoperti e non
            usciti: si annulla l'ordine di uscita, si entra una SECONDA volta
            sull'Under 3.5 con meta' dello stake al miglior prezzo disponibile,
            poi ci si copre in due tempi -- il 50% due minuti dopo il gol, il
            resto tre minuti dopo che la prima tranche si e' abbinata.

Il punto piu' delicato, e il motivo per cui questi test esistono: la SECONDA
tranche non e' "l'altra meta' dello stesso importo". Le quote dell'Over 4.5 si
muovono, quindi il residuo va ricalcolato sul prezzo di quel momento e su quanto
la prima tranche ha gia' garantito. Se l'Over sale (nessun altro gol) la seconda
meta' costa meno; se scende costa di piu'; in entrambi i casi la protezione
totale resta quella dichiarata da ``cover_profit_factor``.
"""
from __future__ import annotations

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from test_mike_engine import conferma_annulli

KO = 1_800_000_000.0
COMM = 0.05


# ---------------------------------------------------------------------------
# Impalcatura
# ---------------------------------------------------------------------------
def params(**over):
    p = C.merge_params(None)
    p.update(over)
    return p


def book(bb, bs=100.0, bl=None, ls=100.0, status="OPEN", inplay=False):
    if bl is None:
        bl = E.ticks_away(bb, 1)
    return E.Book(best_back=bb, back_size=bs, best_lay=bl, lay_size=ls,
                  status=status, inplay=inplay)


def snap(now, *, u35=None, o45=None, inplay=True, minute=None, goals=0,
         last_goal_ts=None, hazard=None, p4_market=None, market_status="OPEN",
         p_total_model=None, p_total_emp=None):
    books = {}
    if u35 is not None:
        books[(E.MARKET_OU35, E.SEL_UNDER)] = u35
    if o45 is not None:
        books[(E.MARKET_OU45, E.SEL_OVER)] = o45
    return E.Snapshot(now=now, ko_at=KO, books=books, inplay=inplay, minute=minute,
                      goals=goals, last_goal_ts=last_goal_ts, hazard=hazard,
                      p4_market=p4_market, market_status=market_status,
                      p_total_model=p_total_model, p_total_emp=p_total_emp)


def fill(leg, size=None, price=None):
    leg.matched = float(size if size is not None else leg.size)
    leg.avg_price = float(price if price is not None else leg.price)
    leg.status = "open"
    return leg


def posizione_portata_in_gioco(stake=10.0, prezzo=1.50):
    """Contesto realistico: una gamba Under 3.5 abbinata prima del fischio.

    E' esattamente il caso della specifica: l'ultimo ingresso del pre-match
    (quello a 10 minuti dal calcio d'inizio) resta a mercato e va in gioco.
    """
    ctx = E.MatchCtx(state="PRE_OPEN")
    leg = E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                price=prezzo, size=stake, ref="e1", persistence="PERSIST")
    fill(leg)
    ctx.legs.append(leg)
    return ctx


def al_fischio(ctx, p, *, prezzo_u35=1.50, now=KO + 1.0):
    """Passaggio in gioco + primo giro in LIVE_KO_GREEN.

    Sono due decisioni: la prima porta lo stato in gioco e fa partire gli
    orologi, la seconda appoggia l'ordine di uscita. Fra le due passa mezzo
    secondo di ciclo, irrilevante su una finestra di tre minuti.
    """
    s = snap(now, u35=book(prezzo_u35, inplay=True), minute=0, goals=0)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    s2 = snap(now + 0.5, u35=book(prezzo_u35, inplay=True), minute=0, goals=0)
    d = E.decide(ctx, s2, p)
    E.apply_decision(ctx, d, s2.now)
    return d


# ---------------------------------------------------------------------------
# Passaggio in gioco
# ---------------------------------------------------------------------------
def test_al_fischio_si_appoggia_l_uscita_a_due_tick_dal_nostro_ingresso():
    ctx, p = posizione_portata_in_gioco(10.0, 1.50), params()
    d = al_fischio(ctx, p)
    assert d.state == "LIVE_KO_GREEN"
    place = [a for a in d.actions if a.kind == "place"]
    assert len(place) == 1
    a = place[0]
    assert (a.role, a.market, a.selection, a.side) == ("ko_green", E.MARKET_OU35, E.SEL_UNDER, "lay")
    # 2 tick SOTTO 1.50 (passo 0.01 sotto quota 2): 1.48
    assert a.price == pytest.approx(1.48)
    # l'orologio della finestra parte dal fischio VISTO, non dal ko_at di calendario
    assert ctx.live_since == KO + 1.0 and ctx.ko_goals == 0


def test_il_prezzo_di_uscita_segue_il_nostro_ingresso_non_il_mercato():
    """Il riferimento e' il NOSTRO punto di ingresso: un mercato gia' sceso non
    fa piazzare piu' in basso (si abbinerebbe meglio da solo, essendo un limite)."""
    ctx, p = posizione_portata_in_gioco(10.0, 1.60), params()
    d = al_fischio(ctx, p, prezzo_u35=1.40)
    a = [x for x in d.actions if x.kind == "place"][0]
    assert a.price == pytest.approx(1.58)      # 2 tick sotto 1.60, non sotto 1.40


def test_l_uscita_si_riallinea_se_la_posizione_cambia():
    """Se il residuo PERSIST si abbina dopo il fischio la media cambia: l'ordine
    di uscita va rifatto sul nuovo prezzo, altrimenti chiuderebbe al prezzo sbagliato."""
    ctx, p = posizione_portata_in_gioco(10.0, 1.50), params()
    al_fischio(ctx, p)
    # arriva un secondo fill a 1.60: media 1.55
    extra = E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                  price=1.60, size=10.0, ref="e2")
    ctx.legs.append(fill(extra))
    s = snap(KO + 20, u35=book(1.55, inplay=True), minute=0, goals=0)
    d = E.decide(ctx, s, p)
    # 16/09 (ordine dell'utente): «non devono mai esserci 2 lay a mercato».
    # La vecchia uscita si ANNULLA e basta; la nuova si appoggia al giro dopo,
    # quando l'annullamento e' CONFERMATO da Betfair.
    assert [a.kind for a in d.actions] == ["cancel"]
    E.apply_decision(ctx, d, s.now)
    conferma_annulli(ctx, d)
    d = E.decide(ctx, s, p)
    assert [a.kind for a in d.actions] == ["place"]
    assert d.actions[0].price == pytest.approx(1.53)     # 2 tick sotto la media 1.55


def test_uscita_disattivata_va_dritta_alla_copertura():
    ctx = posizione_portata_in_gioco(10.0, 1.50)
    p = params(ko_green_enabled=False)
    s = snap(KO + 1, u35=book(1.50, inplay=True), o45=book(8.0), minute=0, goals=0)
    d = E.decide(ctx, s, p)
    assert d.state in ("LIVE_UNCOVERED", "LIVE_COVER_PENDING")


# ---------------------------------------------------------------------------
# STRADA A - si esce in profitto, nessuna copertura
# ---------------------------------------------------------------------------
def test_strada_A_uscita_abbinata_chiude_la_posizione_senza_coprire():
    ctx, p = posizione_portata_in_gioco(10.0, 1.50), params()
    al_fischio(ctx, p)
    uscita = [l for l in ctx.legs if l.role == "ko_green"][-1]
    fill(uscita)
    s = snap(KO + 60, u35=book(1.47, inplay=True), o45=book(8.0), minute=1, goals=0)
    d = E.decide(ctx, s, p)
    assert d.state == "FLAT"
    # NESSUN ordine di copertura: il capitale e' libero
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.telemetry["ko_green"]["esito"] == "abbinata"
    # profitto reale bloccato su entrambi gli esiti
    bloccato = E.locked_pnl(ctx.legs, COMM)
    assert bloccato is not None and bloccato > 0
    assert bloccato == pytest.approx(10.0 * (1.50 / 1.48 - 1.0), abs=0.02)


def test_strada_A_non_riapre_niente_al_giro_dopo():
    ctx, p = posizione_portata_in_gioco(10.0, 1.50), params()
    al_fischio(ctx, p)
    fill([l for l in ctx.legs if l.role == "ko_green"][-1])
    s = snap(KO + 60, u35=book(1.47, inplay=True), o45=book(8.0), minute=1, goals=0)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    d2 = E.decide(ctx, snap(KO + 90, u35=book(1.47, inplay=True), o45=book(8.0),
                            minute=1, goals=0), p)
    assert d2.state == "FLAT" and [a for a in d2.actions if a.kind == "place"] == []


def test_strada_A_fill_parziale_copre_solo_il_residuo():
    """Meta' uscita abbinata: resta esposizione, quindi si copre -- ma sul residuo,
    non sullo stake pieno (``under_liability`` e' gia' al netto della lay abbinata)."""
    ctx, p = posizione_portata_in_gioco(10.0, 1.50), params()
    al_fischio(ctx, p)
    uscita = [l for l in ctx.legs if l.role == "ko_green"][-1]
    uscita.matched = round(uscita.size / 2.0, 2)
    uscita.avg_price = uscita.price
    uscita.status = "open"
    d = E.decide(ctx, snap(KO + 60, u35=book(1.47, inplay=True), o45=book(8.0),
                           minute=1, goals=0), p)
    assert d.state in ("LIVE_UNCOVERED", "LIVE_COVER_PENDING")
    assert E.under_liability(ctx.legs) < 10.0


# ---------------------------------------------------------------------------
# STRADA B - finestra scaduta senza gol: copertura piena
# ---------------------------------------------------------------------------
def test_strada_B_finestra_scaduta_annulla_e_compra_la_copertura_piena():
    ctx, p = posizione_portata_in_gioco(10.0, 1.50), params()
    al_fischio(ctx, p)
    uscita = [l for l in ctx.legs if l.role == "ko_green"][-1]
    # 3 minuti esatti dal fischio, ordine mai abbinato
    s = snap(KO + 1 + 180, u35=book(1.52, inplay=True), o45=book(8.0), minute=3, goals=0)
    d = E.decide(ctx, s, p)
    assert any(a.kind == "cancel" and a.ref == uscita.ref for a in d.actions)
    assert d.state == "LIVE_UNCOVERED" and d.updates.get("cover_forced") is True
    assert d.telemetry["ko_green"]["esito"] == "scaduta"
    # il giro successivo compra davvero
    E.apply_decision(ctx, d, s.now)
    uscita.status = "cancelled"
    d2 = E.decide(ctx, snap(KO + 185, u35=book(1.52, inplay=True), o45=book(8.0),
                            minute=3, goals=0), p)
    assert d2.state == "LIVE_COVER_PENDING"
    cop = [a for a in d2.actions if a.kind == "place"][0]
    assert (cop.role, cop.market, cop.selection, cop.side) == \
        ("over_cover", E.MARKET_OU45, E.SEL_OVER, "back")
    # copertura PIENA sui 10 EUR di rischio: 12 / (7 * 0.95)
    assert d2.telemetry["cover"]["x"] == pytest.approx(12.0 / (7.0 * 0.95), abs=0.01)
    assert d2.telemetry["cover"]["stage"] == 0


def test_strada_B_un_secondo_prima_della_scadenza_non_si_muove():
    ctx, p = posizione_portata_in_gioco(10.0, 1.50), params()
    al_fischio(ctx, p)
    d = E.decide(ctx, snap(KO + 1 + 179, u35=book(1.52, inplay=True), o45=book(8.0),
                           minute=2, goals=0), p)
    assert d.state == "LIVE_KO_GREEN"
    assert [a for a in d.actions if a.kind == "cancel"] == []


def test_strada_B_la_copertura_ordinata_non_passa_dall_attesa_intelligente():
    """Senza ``cover_forced`` ``cover_timing`` potrebbe decidere di ASPETTARE
    (0 gol, minuto basso, hazard e P(4) bassi): la finestra scaduta e' un ordine
    esplicito dell'utente, non una valutazione da rifare."""
    ctx = posizione_portata_in_gioco(10.0, 1.50)
    p = params(cover_good_price=50.0, cover_wait_min_gain_pct=0.0)
    al_fischio(ctx, p)
    s = snap(KO + 181, u35=book(1.52, inplay=True), o45=book(5.0), minute=3, goals=0,
             hazard=0.01, p4_market=0.05)
    d = E.decide(ctx, s, p)
    E.apply_decision(ctx, d, s.now)
    for l in ctx.legs:
        if l.role == "ko_green":
            l.status = "cancelled"
    d2 = E.decide(ctx, snap(KO + 185, u35=book(1.52, inplay=True), o45=book(5.0),
                            minute=3, goals=0, hazard=0.01, p4_market=0.05), p)
    assert d2.state == "LIVE_COVER_PENDING", d2.reason


# ---------------------------------------------------------------------------
# STRADA C - gol precoce: seconda puntata e copertura a tranche
# ---------------------------------------------------------------------------
def dopo_il_gol(stake=10.0, prezzo=1.50, t_gol=KO + 120.0):
    """Contesto: gol al 2', ordine di uscita annullato, si passa alla seconda puntata."""
    ctx, p = posizione_portata_in_gioco(stake, prezzo), params()
    al_fischio(ctx, p)
    s = snap(t_gol, u35=book(1.95, inplay=True), o45=book(8.0), minute=2, goals=1,
             last_goal_ts=t_gol)
    d = E.decide(ctx, s, p)
    E.apply_decision(ctx, d, s.now)
    for l in ctx.legs:
        if l.role == "ko_green" and l.status == "pending":
            l.status = "cancelled"
    return ctx, p, d


def test_strada_C_il_gol_annulla_l_uscita_e_apre_la_seconda_puntata():
    ctx, p, d = dopo_il_gol()
    assert d.state == "LIVE_SECOND_ENTRY"
    assert any(a.kind == "cancel" and a.role == "ko_green" for a in d.actions)
    assert d.telemetry["ko_green"]["esito"] == "gol"
    assert ctx.early_goal_at == KO + 120.0


def test_strada_C_seconda_puntata_meta_stake_al_miglior_prezzo():
    ctx, p, _ = dopo_il_gol()
    s = snap(KO + 122, u35=book(1.95, inplay=True), o45=book(8.0), minute=2, goals=1,
             last_goal_ts=KO + 120)
    d = E.decide(ctx, s, p)
    a = [x for x in d.actions if x.kind == "place"][0]
    assert (a.role, a.side, a.selection) == ("under_second", "back", E.SEL_UNDER)
    assert a.size == pytest.approx(5.0)        # 50% di 10
    assert a.price == pytest.approx(1.95)      # miglior prezzo disponibile


def test_strada_C_la_seconda_puntata_alza_la_quota_media():
    """Esempio della specifica: 10 EUR a 1,50 + 5 EUR a 1,95 = 15 a 1,65."""
    ctx, p, _ = dopo_il_gol()
    s = snap(KO + 122, u35=book(1.95, inplay=True), o45=book(8.0), minute=2, goals=1,
             last_goal_ts=KO + 120)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    fill([l for l in ctx.legs if l.role == "under_second"][-1])
    S, media = E.position(ctx.legs, E.MARKET_OU35, E.SEL_UNDER, E.UNDER_ROLES)
    assert S == pytest.approx(15.0)
    assert media == pytest.approx(1.65, abs=0.005)
    # vincendo si incassa di piu' che con la sola prima puntata
    assert 15.0 * (1.65 - 1.0) == pytest.approx(9.75, abs=0.02)


def test_strada_C_mai_due_seconde_puntate():
    ctx, p, _ = dopo_il_gol()
    s = snap(KO + 122, u35=book(1.95, inplay=True), o45=book(8.0), minute=2, goals=1,
             last_goal_ts=KO + 120)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    fill([l for l in ctx.legs if l.role == "under_second"][-1])
    s2 = snap(KO + 130, u35=book(1.95, inplay=True), o45=book(8.0), minute=2, goals=1,
              last_goal_ts=KO + 120)
    d2 = E.decide(ctx, s2, p)
    E.apply_decision(ctx, d2, s2.now)
    assert ctx.second_entry_done is True
    assert len([l for l in ctx.legs if l.role == "under_second"]) == 1
    # un secondo gol non ne apre un'altra
    d3 = E.decide(ctx, snap(KO + 400, u35=book(2.60, inplay=True), o45=book(4.0),
                            minute=6, goals=2, last_goal_ts=KO + 390), p)
    assert d3.state != "LIVE_SECOND_ENTRY"


def test_strada_C_la_seconda_puntata_non_ritarda_la_copertura():
    """Se non si abbina entro l'attesa prevista si annulla e si copre lo stesso:
    restare scoperti per inseguire un fill e' il rischio pieno."""
    ctx, p, _ = dopo_il_gol()
    s = snap(KO + 122, u35=book(1.95, inplay=True), o45=book(8.0), minute=2, goals=1,
             last_goal_ts=KO + 120)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    seconda = [l for l in ctx.legs if l.role == "under_second"][-1]
    assert seconda.status == "pending"
    d = E.decide(ctx, snap(KO + 120 + 120, u35=book(1.95, inplay=True), o45=book(8.0),
                           minute=4, goals=1, last_goal_ts=KO + 120), p)
    assert any(a.kind == "cancel" and a.ref == seconda.ref for a in d.actions)
    assert d.state == "LIVE_UNCOVERED"
    assert d.updates["cover_stage"] == 0        # nessuna tranche: copertura piena


# ---------------------------------------------------------------------------
# STRADA C - le due tranche di copertura
# ---------------------------------------------------------------------------
def con_seconda_puntata_abbinata(prezzo_secondo=1.95):
    ctx, p, _ = dopo_il_gol()
    s = snap(KO + 122, u35=book(prezzo_secondo, inplay=True), o45=book(8.0), minute=2,
             goals=1, last_goal_ts=KO + 120)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    fill([l for l in ctx.legs if l.role == "under_second"][-1])
    s2 = snap(KO + 124, u35=book(prezzo_secondo, inplay=True), o45=book(8.0), minute=2,
              goals=1, last_goal_ts=KO + 120)
    d2 = E.decide(ctx, s2, p)
    E.apply_decision(ctx, d2, s2.now)
    return ctx, p, d2


def test_prima_tranche_non_prima_dei_due_minuti_dal_gol():
    ctx, p, d = con_seconda_puntata_abbinata()
    assert d.state == "LIVE_UNCOVERED" and ctx.cover_stage == 1
    # 119 secondi dal gol: ancora nulla
    d1 = E.decide(ctx, snap(KO + 120 + 119, u35=book(1.95, inplay=True), o45=book(8.0),
                            minute=4, goals=1, last_goal_ts=KO + 120), p)
    assert [a for a in d1.actions if a.kind == "place"] == []
    assert d1.telemetry["cover_staged"]["stage"] == 1


def test_prima_tranche_compra_meta_copertura_al_minuto_giusto():
    """Over a 4,00: la meta' esatta vale 3,16 EUR, sopra il minimo piazzabile,
    quindi la divisione in due tempi si fa davvero."""
    ctx, p, _ = con_seconda_puntata_abbinata()
    s = snap(KO + 120 + 120, u35=book(1.95, inplay=True), o45=book(4.0), minute=4,
             goals=1, last_goal_ts=KO + 120)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVER_PENDING"
    tele = d.telemetry["cover"]
    # rischio 15 EUR, obiettivo 1.2 * 15 = 18 lordi con 5+ gol; meta' a quota 4.00
    pieno = 18.0 / (3.0 * 0.95)
    assert tele["x_pieno"] == pytest.approx(pieno, abs=0.01)
    assert tele["x"] == pytest.approx(pieno / 2.0, abs=0.01)
    assert tele["x"] == pytest.approx(3.16, abs=0.02)
    assert tele["stage"] == 1 and tele["split_declassato"] is False


def test_la_divisione_si_fa_a_qualunque_quota():
    """Il vecchio limite (meta' copertura sotto i 2,00 EUR di Betfair) NON esiste
    piu': col place-and-trim si piazza qualunque cifra fino al centesimo, quindi
    la divisione in due tempi si fa sempre. Prima si fermava sopra quota 5,74,
    cioe' quasi sempre."""
    liab, fattore, c = 15.0, 1.2, 0.05
    for quota in (3.0, 5.0, 5.8, 8.0, 12.0, 30.0, 100.0):
        x = E.cover_residual(liab, quota, c, fattore, 0.0)
        frazione, declassato = E.frazione_copertura(1, params(), x)
        assert (frazione, declassato) == (pytest.approx(0.5), False), quota
        assert round(x * frazione, 2) >= E.SUBMIN_FLOOR


def test_con_importi_esatti_spenti_la_divisione_si_ferma_al_minimo():
    """Se dalla UI si spengono gli "importi esatti", gli ordini tornano
    legalizzati al minimo .it: li' dividere avrebbe senso solo se ciascuna meta'
    ci arriva da sola, altrimenti si comprerebbe Over di troppo su ENTRAMBE. In
    quel caso non si divide."""
    p = params(exact_sizes=False)
    liab, fattore, c = 15.0, 1.2, 0.05
    frazione, declassato = E.frazione_copertura(
        1, p, E.cover_residual(liab, 4.0, c, fattore, 0.0))
    assert (frazione, declassato) == (pytest.approx(0.5), False)
    frazione, declassato = E.frazione_copertura(
        1, p, E.cover_residual(liab, 8.0, c, fattore, 0.0))
    assert (frazione, declassato) == (pytest.approx(1.0), True)


def test_finestra_uscita_parte_dal_terzo_gol():
    """13/09, richiesta dell'utente: la regola di uscita in perdita HT/2T parte
    dal TERZO gol, non dal secondo. Con due gol la partita non e' compromessa --
    ne servono altri due per perdere l'Under 3.5 -- e chiudere li' e' prematuro."""
    p = params()
    assert p["ht_loss_goals_min"] == 3 and p["ht_loss_goals_max"] == 4
    assert E.loss_exit_ok(-2.0, 24.0, 25.0, goals=2, gmin=3, gmax=4) is False
    assert E.loss_exit_ok(-2.0, 24.0, 25.0, goals=3, gmin=3, gmax=4) is True
    assert E.loss_exit_ok(-2.0, 24.0, 25.0, goals=4, gmin=3, gmax=4) is True
    assert E.loss_exit_ok(-2.0, 24.0, 25.0, goals=5, gmin=3, gmax=4) is False


def test_seconda_tranche_si_ricalcola_sulla_quota_del_momento():
    """IL PUNTO CHIAVE: la seconda tranche NON e' l'altra meta' dello stesso
    importo. Con l'Over salito da 8,00 a 11,00 la seconda parte costa meno, e la
    protezione totale resta quella dichiarata."""
    ctx, p, _ = con_seconda_puntata_abbinata()
    s = snap(KO + 240, u35=book(1.95, inplay=True), o45=book(4.0), minute=4, goals=1,
             last_goal_ts=KO + 120)
    d = E.decide(ctx, s, p)
    E.apply_decision(ctx, d, s.now)
    prima = [l for l in ctx.legs if l.role == "over_cover"][-1]
    fill(prima)
    # abbinata: si passa da LIVE_COVERED (uscite GLOBALI) e parte l'attesa
    s2 = snap(KO + 245, u35=book(1.95, inplay=True), o45=book(4.0), minute=4, goals=1)
    d2 = E.decide(ctx, s2, p)
    E.apply_decision(ctx, d2, s2.now)
    assert d2.state == "LIVE_COVERED" and ctx.cover_stage == 2
    assert ctx.cover_stage1_at == KO + 245

    # 179 s dopo: ancora niente
    d3 = E.decide(ctx, snap(KO + 245 + 179, u35=book(1.95, inplay=True), o45=book(6.0),
                            minute=7, goals=1), p)
    assert d3.state == "LIVE_COVERED"

    # 180 s dopo: si completa, con l'Over salito a 6.00
    s4 = snap(KO + 245 + 180, u35=book(1.95, inplay=True), o45=book(6.0), minute=7, goals=1)
    d4 = E.decide(ctx, s4, p)
    assert d4.state == "LIVE_UNCOVERED" and d4.updates["cover_stage"] == 3
    E.apply_decision(ctx, d4, s4.now)
    d5 = E.decide(ctx, snap(KO + 245 + 181, u35=book(1.95, inplay=True), o45=book(6.0),
                            minute=7, goals=1), p)
    assert d5.state == "LIVE_COVER_PENDING"
    seconda = d5.telemetry["cover"]["x"]
    # residuo a 6.00 dato quanto la prima ha gia' garantito: NON l'altra meta' di 3,16
    garantito = prima.matched * (prima.fill_price - 1.0) * (1.0 - COMM)
    atteso = (1.2 * 15.0 - garantito) / (5.0 * 0.95)
    assert seconda == pytest.approx(atteso, abs=0.01)
    assert seconda < 3.16 - 0.10        # l'Over e' salito: costa meno
    assert d5.telemetry["cover"]["stage"] == 3
    # e la protezione complessiva resta quella dichiarata
    totale = garantito + seconda * (6.0 - 1.0) * (1.0 - COMM)
    assert totale == pytest.approx(1.2 * 15.0, abs=0.02)


@pytest.mark.parametrize("prezzo_poi,piu_caro", [(5.0, True), (6.5, True), (8.0, False),
                                                 (11.0, False), (15.0, False)])
def test_la_protezione_totale_regge_a_qualunque_quota_della_seconda_tranche(prezzo_poi, piu_caro):
    """A 15 EUR di rischio, con qualunque quota alla seconda tranche, la somma
    delle due coperture garantisce comunque il 120% del rischio con 5+ gol."""
    liab, fattore = 15.0, 1.2
    x1 = (fattore * liab / 2.0) / ((8.0 - 1.0) * (1.0 - COMM))
    garantito = x1 * (8.0 - 1.0) * (1.0 - COMM)
    x2 = E.cover_residual(liab, prezzo_poi, COMM, fattore, garantito)
    totale = garantito + x2 * (prezzo_poi - 1.0) * (1.0 - COMM)
    assert totale == pytest.approx(fattore * liab, abs=0.01)
    assert ((x1 + x2) > 2.71) is piu_caro


def test_la_tranche_sotto_il_minimo_si_piazza_lo_stesso():
    """Il caso che prima bloccava tutto: meta' copertura = 1,35 EUR, sotto i 2,00
    di Betfair. Col place-and-trim si piazza per quello che vale."""
    ctx, p, _ = con_seconda_puntata_abbinata()
    # Over a 8,00 -- il caso TIPICO pochi minuti dopo un gol precoce: la meta'
    # esatta vale 1,35 EUR. Prima non era piazzabile e si copriva tutto in una
    # volta; col place-and-trim 1,35 e' un ordine valido e la divisione si fa.
    s = snap(KO + 240, u35=book(1.95, inplay=True), o45=book(8.0), minute=4, goals=1,
             last_goal_ts=KO + 120)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVER_PENDING"
    tele = d.telemetry["cover"]
    assert tele["split_declassato"] is False
    assert tele["frazione"] == pytest.approx(0.5)
    assert d.updates["cover_stage"] == 1        # la seconda tranche arrivera'
    assert tele["x_pieno"] == pytest.approx(18.0 / (7.0 * 0.95), abs=0.01)
    assert tele["x"] == pytest.approx(1.35, abs=0.02)
    # e l'ordine piazzato porta l'importo ESATTO, non il minimo gonfiato
    ordine = [a for a in d.actions if a.kind == "place"][0]
    assert ordine.size == pytest.approx(1.35, abs=0.02)


def test_split_attivo_quando_la_tranche_e_piazzabile():
    """Simmetrico del precedente: con l'Over basso la meta' supera il minimo e
    la divisione in due tempi si fa davvero."""
    ctx, p, _ = con_seconda_puntata_abbinata()
    d = E.decide(ctx, snap(KO + 240, u35=book(1.95, inplay=True), o45=book(4.5),
                           minute=4, goals=1, last_goal_ts=KO + 120), p)
    tele = d.telemetry["cover"]
    assert tele["split_declassato"] is False and tele["frazione"] == pytest.approx(0.5)
    assert tele["x"] == pytest.approx(9.0 / (3.5 * 0.95), abs=0.01)


def test_il_riprezzo_della_prima_tranche_resta_sulla_frazione():
    """Riprezzando, la prima tranche non deve comprare la copertura PIENA:
    altrimenti la seconda non avrebbe piu' ragione di esistere."""
    ctx, p, _ = con_seconda_puntata_abbinata()
    s = snap(KO + 240, u35=book(1.95, inplay=True), o45=book(4.0), minute=4, goals=1,
             last_goal_ts=KO + 120)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    gamba = [l for l in ctx.legs if l.role == "over_cover"][-1]
    assert gamba.status == "pending"
    s2 = snap(KO + 240 + float(p["close_retry_s"]) + 1,
              u35=book(1.95, inplay=True), o45=book(4.0), minute=5, goals=1)
    d = E.decide(ctx, s2, p)
    # ORDINE DELL'UTENTE 16/09 SERA — MAI SOVRACOPERTURA: in questo giro esce
    # SOLO l'annullamento; la tranche nuova al giro dopo, ad annullamento
    # CONFERMATO, dimensionata sulla copertura reale.
    assert [a.kind for a in d.actions] == ["cancel"]
    gamba.status = "cancelled"
    E.apply_decision(ctx, E.decide(ctx, s2, p), s2.now)
    d = E.decide(ctx, s2, p)
    place = [a for a in d.actions if a.kind == "place"]
    assert place and place[0].size == pytest.approx(9.0 / (3.0 * 0.95), abs=0.02)


# ---------------------------------------------------------------------------
# Uscite GLOBALI appena entrambe le gambe sono a mercato
# ---------------------------------------------------------------------------
def test_fra_le_due_tranche_valgono_le_uscite_globali_non_la_singola_gamba():
    """Richiesta esplicita dell'utente: con Under 3.5 e Over 4.5 entrambi a
    mercato la decisione e' sulla POSIZIONE intera. Se il cash-out globale
    arriva a soglia si chiude tutto, e la seconda tranche non si compra piu'."""
    ctx, p, _ = con_seconda_puntata_abbinata()
    s = snap(KO + 240, u35=book(1.95, inplay=True), o45=book(4.0), minute=4, goals=1,
             last_goal_ts=KO + 120)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    fill([l for l in ctx.legs if l.role == "over_cover"][-1])
    s2 = snap(KO + 245, u35=book(1.95, inplay=True), o45=book(4.0), minute=4, goals=1)
    E.apply_decision(ctx, E.decide(ctx, s2, p), s2.now)
    assert ctx.cover_stage == 2
    # l'Under crolla a 1.20: la posizione globale e' ampiamente in profitto
    s3 = snap(KO + 300, u35=book(1.20, inplay=True), o45=book(4.0), minute=5, goals=1)
    d3 = E.decide(ctx, s3, p)
    assert d3.state == "LIVE_CLOSING"
    assert d3.updates["close_reason"] == "profit"
    # le chiusure toccano ENTRAMBE le selezioni, non solo la gamba Under
    mercati = {(a.market, a.selection) for a in d3.actions if a.kind == "place"}
    assert (E.MARKET_OU35, E.SEL_UNDER) in mercati
    assert (E.MARKET_OU45, E.SEL_OVER) in mercati


def test_la_chiusura_globale_ha_la_precedenza_sulla_seconda_tranche():
    """Anche con l'attesa gia' scaduta: se si chiude tutto non c'e' piu' niente
    da coprire."""
    ctx, p, _ = con_seconda_puntata_abbinata()
    s = snap(KO + 240, u35=book(1.95, inplay=True), o45=book(4.0), minute=4, goals=1,
             last_goal_ts=KO + 120)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    fill([l for l in ctx.legs if l.role == "over_cover"][-1])
    s2 = snap(KO + 245, u35=book(1.95, inplay=True), o45=book(4.0), minute=4, goals=1)
    E.apply_decision(ctx, E.decide(ctx, s2, p), s2.now)
    d = E.decide(ctx, snap(KO + 245 + 500, u35=book(1.20, inplay=True), o45=book(4.0),
                           minute=12, goals=1), p)
    assert d.state == "LIVE_CLOSING"


# ---------------------------------------------------------------------------
# Robustezza
# ---------------------------------------------------------------------------
def test_feed_muto_al_fischio_non_inventa_gol():
    """Senza baseline dei gol la strada C non parte: meglio perdere la seconda
    puntata che aprirla su un gol che non c'e' stato."""
    ctx = posizione_portata_in_gioco(10.0, 1.50)
    p = params()
    s = E.Snapshot(now=KO + 1, ko_at=KO, books={(E.MARKET_OU35, E.SEL_UNDER): book(1.50, inplay=True)},
                   inplay=True, minute=0, goals=None)
    d = E.decide(ctx, s, p)
    E.apply_decision(ctx, d, s.now)
    assert ctx.ko_goals is None
    assert E.gol_dopo_il_fischio(ctx, snap(KO + 60, goals=1)) is False
    # appena il feed parla, la baseline si fissa e da li' si conta
    s2 = snap(KO + 30, u35=book(1.50, inplay=True), minute=0, goals=0)
    E.apply_decision(ctx, E.decide(ctx, s2, p), s2.now)
    assert ctx.ko_goals == 0
    assert E.gol_dopo_il_fischio(ctx, snap(KO + 60, goals=1)) is True


def test_riavvio_a_meta_strada_non_lascia_la_partita_scoperta():
    """Se il momento del gol si perde (contesto ripreso male) la copertura a
    tranche non ha piu' un orologio: si copre in una volta invece di aspettare
    un'attesa che non finisce mai."""
    ctx, p, _ = con_seconda_puntata_abbinata()
    ctx.early_goal_at = None
    d = E.decide(ctx, snap(KO + 300, u35=book(1.95, inplay=True), o45=book(4.0),
                           minute=5, goals=1), p)
    assert d.state == "LIVE_COVER_PENDING"
    assert d.telemetry["cover"]["frazione"] == pytest.approx(1.0)


def test_i_timer_sopravvivono_al_riavvio_del_servizio():
    """I campi nuovi devono stare nella lista di quelli persistiti, altrimenti un
    riavvio a meta' partita perde finestra, baseline e stato della copertura."""
    from Betfair.mike import service as S
    for campo in ("live_since", "ko_goals", "early_goal_at", "second_entry_done",
                  "cover_stage", "cover_stage1_at", "cover_forced"):
        assert campo in S._CTX_FIELDS, campo
        assert hasattr(E.MatchCtx(), campo), campo


def test_ordine_a_esito_ignoto_blocca_la_seconda_puntata():
    """H8: con una gamba a esito IGNOTO non si aprono posizioni nuove."""
    ctx, p, _ = dopo_il_gol()
    ctx.legs.append(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                          side="back", price=1.5, size=5.0, ref="x9",
                          status=E.STATUS_RECONCILE))
    d = E.decide(ctx, snap(KO + 122, u35=book(1.95, inplay=True), o45=book(8.0),
                           minute=2, goals=1, last_goal_ts=KO + 120), p)
    assert [a for a in d.actions if a.kind == "place" and a.role == "under_second"] == []


def test_la_seconda_puntata_rispetta_il_cap_di_capitale_per_partita():
    ctx, p, _ = dopo_il_gol()
    p["max_liability_per_match"] = 10.0        # gia' tutto impegnato
    d = E.decide(ctx, snap(KO + 122, u35=book(1.95, inplay=True), o45=book(8.0),
                           minute=2, goals=1, last_goal_ts=KO + 120), p)
    assert [a for a in d.actions if a.role == "under_second"] == []
    assert d.state == "LIVE_UNCOVERED" and d.updates["cover_forced"] is True


def test_liquidita_insufficiente_non_piazza_la_seconda_puntata():
    ctx, p, _ = dopo_il_gol()
    d = E.decide(ctx, snap(KO + 122, u35=book(1.95, bs=1.0, inplay=True), o45=book(8.0),
                           minute=2, goals=1, last_goal_ts=KO + 120), p)
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.state == "LIVE_SECOND_ENTRY"


def test_mercato_chiuso_batte_qualunque_fase_del_flusso():
    ctx, p, _ = dopo_il_gol()
    d = E.decide(ctx, snap(KO + 3000, market_status="CLOSED", minute=50, goals=1), p)
    assert d.state == "SETTLING"


def test_troppi_gol_niente_copertura_e_stato_pulito():
    """Oltre ``cover_max_goals`` la copertura non ha piu' senso: si esce dalla
    logica a tranche senza lasciare stati appesi."""
    ctx, p, _ = con_seconda_puntata_abbinata()
    d = E.decide(ctx, snap(KO + 400, u35=book(3.5, inplay=True), o45=book(2.5),
                           minute=6, goals=3, last_goal_ts=KO + 390), p)
    assert d.state == "LIVE_COVERED"
    assert d.updates["cover_skipped"] is True
    assert d.updates["cover_stage"] == 0 and d.updates["cover_forced"] is False


def test_la_seconda_puntata_conta_nel_capitale_investito():
    ctx, p, _ = con_seconda_puntata_abbinata()
    assert E.invested(ctx.legs) == pytest.approx(15.0)
    assert E.under_liability(ctx.legs) == pytest.approx(15.0)


def test_l_uscita_al_fischio_e_marcata_come_greenup_nello_storico():
    assert E.exit_kind_for("ko_green", None) == "greenup"
    assert "ko_green" in E.CLOSING_ROLES and "under_second" in E.OPENING_ROLES


# ---------------------------------------------------------------------------
# Percorso LIVE: nessun fill simulato, nessuna zavorra di log
# ---------------------------------------------------------------------------
def test_in_live_l_uscita_appoggiata_e_LA_STESSA_del_paper():
    """14/09 — l'uscita appoggiata in live è CABLATA, e la strada A avviene anche
    su soldi veri: stesso lato, stesso prezzo, stessa size del paper.

    Prima di oggi ``_live_exit_override`` forzava 'taker' e questa strada non
    accadeva mai in live: il paper certificava un comportamento che il live non
    eseguiva. L'invariante che resta, e che non è negoziabile, è un'altra: in
    live l'abbinamento non si SIMULA mai — si legge dal book ordini di Betfair.
    """
    from Betfair.mike import service as S
    gamba = E.Leg(role="ko_green", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                  side="lay", price=1.48, size=10.14, ref="k1")
    # ⚠️ 16/09 (ordine dell'utente, §15.6): `ko_green` e' appoggiata in OGNI
    # modalita' — `pre_exit_mode` non la governa piu'. Restano governate dal
    # parametro le altre due lay di green.
    assert S._is_resting_leg(gamba, params(pre_exit_mode="resting")) is True
    assert S._is_resting_leg(gamba, params(pre_exit_mode="taker")) is True
    altra = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                  side="lay", price=1.48, size=10.14, ref="g1")
    assert S._is_resting_leg(altra, params(pre_exit_mode="taker")) is False
    # la modalità della partita NON dirotta più l'uscita: live == paper
    assert S._live_exit_override(params(), "live")["pre_exit_mode"] == "resting"
    # ma la valvola, spenta di proposito, riporta al comportamento di prima
    # (per `under_green`: l'uscita al fischio resta appoggiata comunque)
    spenta = dict(params(), live_resting_enabled=False)
    assert S._live_exit_override(spenta, "live")["pre_exit_mode"] == "taker"
    assert S._is_resting_leg(gamba, S._live_exit_override(spenta, "live")) is True


def test_l_ordine_non_si_ripresenta_piu_a_ritmo():
    """⚠️ 16/09 — SOSTITUISCE `test_in_live_l_ordine_si_ripresenta_a_ritmo...`.

    Ordine dell'utente: «mettiamola appoggiata allora, cosi' risparmiamo una
    marea di chiamate». La ri-presentazione ogni `ko_green_retry_s` era il modo
    di simulare un ordine appoggiato sul percorso taker, e costava 25-32
    chiamate REST per una sola uscita. Adesso la lay e' appoggiata in ogni
    modalita': se la gamba precedente e' morta davvero se ne appoggia UNA nuova
    SUBITO, senza aspettare nessun ritmo."""
    ctx, p = posizione_portata_in_gioco(10.0, 1.50), params(pre_exit_mode="taker",
                                                            ko_green_retry_s=60)
    al_fischio(ctx, p)
    uscita = [l for l in ctx.legs if l.role == "ko_green"][-1]
    uscita.status = "cancelled"        # morta (rifiuto, o LAPSE alla sospensione)
    d1 = E.decide(ctx, snap(KO + 3, u35=book(1.50, inplay=True), minute=0, goals=0), p)
    place = [a for a in d1.actions if a.kind == "place"]
    assert len(place) == 1 and place[0].price == pytest.approx(1.48)
    assert d1.state == "LIVE_KO_GREEN"


def test_mai_due_lay_vive_sull_under_3_5():
    """Un doppio abbinamento ribalterebbe la posizione da back netto a lay netto:
    finche' la lay del ciclo pre-match non e' davvero annullata non se ne appoggia
    un'altra."""
    ctx, p = posizione_portata_in_gioco(10.0, 1.50), params()
    residua = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                    side="lay", price=1.48, size=10.14, ref="g0", status="pending")
    ctx.legs.append(residua)
    s = snap(KO + 1, u35=book(1.50, inplay=True), minute=0, goals=0)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    s2 = snap(KO + 1.5, u35=book(1.50, inplay=True), minute=0, goals=0)
    d = E.decide(ctx, s2, p)
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.state == "LIVE_KO_GREEN"
    # appena l'annullamento e' confermato, l'ordine parte
    residua.status = "cancelled"
    d2 = E.decide(ctx, snap(KO + 2, u35=book(1.50, inplay=True), minute=0, goals=0), p)
    assert [a for a in d2.actions if a.kind == "place" and a.role == "ko_green"]


def test_la_finestra_scade_anche_se_l_ordine_non_e_mai_entrato():
    """Caso live: il prezzo non arriva mai, ogni tentativo muore. Allo scadere si
    copre lo stesso -- non si resta scoperti a inseguire un fill."""
    ctx, p = posizione_portata_in_gioco(10.0, 1.50), params(pre_exit_mode="taker")
    al_fischio(ctx, p)
    for l in ctx.legs:
        if l.role == "ko_green":
            l.status = "cancelled"
    d = E.decide(ctx, snap(KO + 200, u35=book(1.55, inplay=True), o45=book(8.0),
                           minute=3, goals=0), p)
    assert d.state == "LIVE_UNCOVERED" and d.updates["cover_forced"] is True


# ---------------------------------------------------------------------------
# Una partita senza esposizione non puo' finire "DA SISTEMARE"
# ---------------------------------------------------------------------------
def test_senza_posizioni_il_punteggio_finale_non_serve():
    """Caso vero del 13/09 (FC Maardu v Tallinna Kalev): la finestra pre-match si
    e' chiusa senza nessun ingresso, a mercato chiuso il book non era piu'
    leggibile e la scheda e' finita in ERRORE -- una partita da sistemare a mano
    su cui non era successo niente. Il punteggio serve solo se il P&L DIPENDE dal
    punteggio."""
    assert E.pnl_indipendente_dal_risultato([], COMM) == 0.0


def test_con_soli_cicli_chiusi_il_conto_e_gia_noto():
    """Ingresso e uscita si compensano: il risultato e' lo stesso su 0 gol come
    su 8, quindi non c'e' niente da aspettare."""
    legs = [E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                  price=1.50, size=10.0, matched=10.0, avg_price=1.50, ref="a"),
            E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                  price=1.48, size=10.14, matched=10.14, avg_price=1.48, ref="b")]
    netto = E.pnl_indipendente_dal_risultato(legs, COMM)
    assert netto is not None and netto == pytest.approx(0.13, abs=0.02)
    for totale in range(0, 9):
        assert E.settle_legs(legs, totale, COMM).net == pytest.approx(netto, abs=0.02)


def test_con_una_posizione_aperta_il_punteggio_serve_davvero():
    """Qui invece il risultato cambia tutto: nessuna scorciatoia, si aspetta."""
    legs = [E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                  price=1.50, size=10.0, matched=10.0, avg_price=1.50, ref="a")]
    assert E.pnl_indipendente_dal_risultato(legs, COMM) is None
