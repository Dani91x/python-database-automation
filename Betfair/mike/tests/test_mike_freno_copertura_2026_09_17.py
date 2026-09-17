"""IL FRENO DELLA COPERTURA E LO STATO DEL MERCATO (17/09/2026, reperto 25).

IL FATTO, dal vivo, con soldi veri. Bnei Yehuda v Maccabi Herzliya, evento
36077571: Under 3.5 back 5,00 EUR a 1.44 abbinata alle 17:16:03. La copertura
Over 4.5 (1,21-1,37 EUR a 5.4-5.9, sotto il minimo .it, quindi place-and-trim)
e' stata RIFIUTATA **104 volte di fila**, una ogni ~5 secondi dalle 17:16 alle
18:13, sempre con lo stesso codice ``CANCELLED_NOT_PLACED``, stato della gamba
``LIVE_UNCOVERED``. Ogni giro: riga in `error`, `skip`, e il ciclo dopo ne
riservava una NUOVA.

Perche' nessun freno esistente la vedeva:
  * ``engine.tentativo_gia_rifiutato`` (16/09) confronta anche PREZZO e SIZE, e
    la copertura li ricalcola a ogni giro sul book che si muove: ogni tentativo
    era formalmente una domanda nuova;
  * ``service._gia_appoggiata`` (15/09) frena solo le gambe di CHIUSURA
    (``E.CLOSING_ROLES``), e ``over_cover`` non e' una chiusura.

DUE ORDINI DELL'UTENTE, eseguiti qui:
  3. freno FAIL-CLOSED sui rifiuti identici ripetuti (N tentativi poi stop della
     gamba + avviso critico), rispetto dei limiti di chiamata di Betfair;
  5. il bot dev'essere informato dei cambi di stato del mercato (SOSPESO /
     APERTO / CHIUSO) DURANTE la copertura.

La strategia NON e' toccata: stessa formula della copertura, stesse due tranche,
stessi prezzi, stesse soglie. Cambia solo quante volte e con che ritmo si
RITENTA una richiesta che il mercato respinge, e che il bot lo dica.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import feed as F
from Betfair.mike import service as S
from Betfair.safe_strategy.execution import PlaceOutcome
from Betfair.mike.tests.test_mike_feed import payload
from Betfair.mike.tests.test_mike_service import FakeDB, FakeMarket
from test_mike_engine import KO, book, fill, params, snap

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# impalcature
# ---------------------------------------------------------------------------
def _ctx_scoperto(stake: float = 20.0) -> E.MatchCtx:
    """Posizione Under 3.5 aperta e ancora scoperta: e' lo stato in cui vive la
    copertura Over 4.5, ed e' quello dell'evento 36077571."""
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", entry_price_initial=1.50)
    ctx.legs.append(fill(E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="back", price=1.50, size=stake, persistence="PERSIST")))
    return ctx


def _snap_copre(now=KO + 20 * 60, *, o45_status="OPEN", o45=True):
    """Istante in cui il motore COPRE (quota Over gia' buona, nessun motivo di
    attendere): cosi' l'unico motivo per non piazzare e' quello che si sta
    misurando."""
    return snap(now, u35=book(1.35, inplay=True),
                o45=(book(9.0, bs=50, inplay=True, status=o45_status) if o45 else None),
                inplay=True, minute=20, goals=0, hazard=0.05, p4_market=0.12)


def _place_cop(d: E.Decision) -> List[E.Action]:
    return [a for a in d.actions if a.kind == "place" and a.role == "over_cover"]


def _rifiuta(ctx: E.MatchCtx, p: Dict[str, Any], codice: str, *, quante: int = 1,
            t0: float = KO) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for i in range(quante):
        out = E.registra_rifiuto_copertura(ctx, error_code=codice, motivo=f"live_rifiutato:{codice}",
                                           ref=f"over_cover-0-{i + 1}", now=t0 + i, params=p)
    return out


# ===========================================================================
# 1. IL CONTEGGIO DEI RIFIUTI — la cifra che mancava
# ===========================================================================
def test_i_rifiuti_identici_si_contano_e_alla_soglia_la_copertura_si_ferma():
    """104 volte lo stesso codice: alla terza (default) ci si ferma."""
    p = params(cover_rifiuti_max=3)
    ctx = _ctx_scoperto()

    primo = _rifiuta(ctx, p, "CANCELLED_NOT_PLACED")
    assert primo["conteggio"] == 1 and primo["bloccata"] is False
    assert E.copertura_bloccata(ctx) is None

    secondo = _rifiuta(ctx, p, "CANCELLED_NOT_PLACED", quante=1, t0=KO + 10)
    assert secondo["conteggio"] == 2 and secondo["bloccata"] is False

    terzo = _rifiuta(ctx, p, "CANCELLED_NOT_PLACED", quante=1, t0=KO + 20)
    assert terzo["conteggio"] == 3 and terzo["bloccata"] is True
    assert terzo["stato"] == E.COVER_BLOCCATA == "LIVE_COVER_BLOCKED"
    fermo = E.copertura_bloccata(ctx)
    assert fermo is not None and fermo["error_code"] == "CANCELLED_NOT_PLACED"
    assert fermo["conteggio"] == 3 and fermo["max"] == 3


def test_un_codice_DIVERSO_azzera_il_conteggio_e_riapre_un_tentativo():
    """Un codice nuovo e' una notizia nuova: INSUFFICIENT_FUNDS dopo due
    CANCELLED_NOT_PLACED non e' il terzo rifiuto della stessa cosa."""
    p = params(cover_rifiuti_max=3)
    ctx = _ctx_scoperto()
    _rifiuta(ctx, p, "CANCELLED_NOT_PLACED", quante=2)
    nuovo = _rifiuta(ctx, p, "INSUFFICIENT_FUNDS", t0=KO + 30)
    assert nuovo["conteggio"] == 1 and nuovo["bloccata"] is False
    assert E.copertura_bloccata(ctx) is None


def test_senza_codice_il_rifiuto_si_conta_lo_stesso():
    """Betfair puo' rifiutare senza codice: «senza_codice» e' un codice come un
    altro, altrimenti il caso peggiore sarebbe l'unico senza freno."""
    p = params(cover_rifiuti_max=2)
    ctx = _ctx_scoperto()
    E.registra_rifiuto_copertura(ctx, error_code=None, motivo="", ref="over_cover-0-1",
                                 now=KO, params=p)
    r = E.registra_rifiuto_copertura(ctx, error_code=None, motivo="", ref="over_cover-0-2",
                                     now=KO + 20, params=p)
    assert r["error_code"] == "senza_codice" and r["bloccata"] is True


# ===========================================================================
# 2. IL FRENO NELLA DECISIONE — nessun ordine nuovo, mai
# ===========================================================================
def test_a_copertura_bloccata_il_motore_NON_emette_piu_nessuna_copertura():
    p = params(cover_rifiuti_max=3, cover_retry_min_s=1)
    ctx = _ctx_scoperto()
    s = _snap_copre()

    # prima del freno la copertura parte (altrimenti il test non proverebbe niente)
    assert _place_cop(E.decide(ctx, s, p)), "senza freno la copertura deve partire"

    _rifiuta(ctx, p, "CANCELLED_NOT_PLACED", quante=3)
    d = E.decide(ctx, s, p)
    assert _place_cop(d) == [], "copertura bloccata: nessun ordine nuovo"
    assert d.state == "LIVE_UNCOVERED", "lo stato deve dire la verita': scoperti"
    assert "FERMATA" in d.reason and "CANCELLED_NOT_PLACED" in d.reason
    assert d.telemetry["cover_wait"]["reason"] == "copertura_bloccata"
    assert d.telemetry["cover_wait"]["conteggio"] == 3


def test_a_copertura_bloccata_lo_stato_NON_avanza_a_COVER_PENDING():
    """Se lo stato avanzasse, il giro dopo il bot aspetterebbe il fill di un
    ordine che non esiste: e' il difetto 17 del catalogo (attesa eterna)."""
    p = params(cover_rifiuti_max=1)
    ctx = _ctx_scoperto()
    _rifiuta(ctx, p, "CANCELLED_NOT_PLACED")
    d = E.decide(ctx, _snap_copre(), p)
    E.apply_decision(ctx, d, _snap_copre().now)
    assert ctx.state == "LIVE_UNCOVERED"


def test_il_freno_NON_ferma_le_USCITE_ne_le_CHIUSURE():
    """15/09: il freno live applicato alle uscite avrebbe lasciato una posizione
    a sanguinare senza via di fuga. Qui il freno tocca SOLO ``over_cover``: si
    prova sulla guardia stessa, con una decisione che porta di tutto."""
    p = params(cover_rifiuti_max=1)
    ctx = _ctx_scoperto()
    _rifiuta(ctx, p, "CANCELLED_NOT_PLACED")
    assert E.copertura_bloccata(ctx) is not None

    mista = E.Decision("LIVE_COVER_PENDING", [
        E.Action(kind="place", role="under_close", market=E.MARKET_OU35,
                 selection=E.SEL_UNDER, side="lay", price=1.30, size=5.0),
        E.Action(kind="place", role="ko_green", market=E.MARKET_OU35,
                 selection=E.SEL_UNDER, side="lay", price=1.48, size=5.0),
        E.Action(kind="cancel", role="under_last", ref="under_last-0-1"),
        E.Action(kind="place", role="over_cover", market=E.MARKET_OU45,
                 selection=E.SEL_OVER, side="back", price=9.0, size=4.0),
    ], "prova")
    d = E._freno_copertura(ctx, mista, _snap_copre(), p)
    ruoli = [(a.kind, a.role) for a in d.actions]
    assert ("place", "over_cover") not in ruoli
    assert ("place", "under_close") in ruoli and ("place", "ko_green") in ruoli
    assert ("cancel", "under_last") in ruoli


def test_con_la_copertura_bloccata_il_cash_out_globale_parte_lo_stesso():
    """La prova sul ramo vero: posizione COPERTA e in profitto, freno armato."""
    p = params(cover_rifiuti_max=1, cashout_profit_pct=0.5)
    ctx = _ctx_scoperto()
    ctx.state = "LIVE_COVERED"
    ctx.legs.append(fill(E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                               side="back", price=9.0, size=4.0, ref="over_cover-0-1")))
    _rifiuta(ctx, p, "CANCELLED_NOT_PLACED")
    assert E.copertura_bloccata(ctx) is not None
    s = snap(KO + 20 * 60, u35=book(1.20, inplay=True), o45=book(12.0, bs=50, inplay=True),
             u45=book(1.05, bs=50, inplay=True), inplay=True, minute=20, goals=0,
             hazard=0.05, p4_market=0.12)
    d = E.decide(ctx, s, p)
    uscite = [a for a in d.actions if a.kind == "place" and a.role in E.CLOSING_ROLES]
    assert uscite, "la copertura bloccata non deve poter bloccare un'uscita"


def test_riprendi_dell_utente_riapre_la_copertura():
    p = params(cover_rifiuti_max=1, cover_retry_min_s=1)
    ctx = _ctx_scoperto()
    _rifiuta(ctx, p, "CANCELLED_NOT_PLACED", t0=KO - 3600)
    assert _place_cop(E.decide(ctx, _snap_copre(), p)) == []
    prima = E.sblocca_copertura(ctx)
    assert prima is not None and prima["conteggio"] == 1
    assert E.copertura_bloccata(ctx) is None
    assert _place_cop(E.decide(ctx, _snap_copre(), p)), "dopo Riprendi la copertura riparte"


# ===========================================================================
# 3. IL RITMO MINIMO — 104 tentativi in un'ora sono anche un limite Betfair
# ===========================================================================
def test_fra_due_tentativi_di_copertura_passa_almeno_cover_retry_min_s():
    p = params(cover_retry_min_s=15)
    ctx = _ctx_scoperto()
    s = _snap_copre()
    assert _place_cop(E.decide(ctx, s, p)), "il primo tentativo deve partire"

    E.segna_tentativo_copertura(ctx, s.now)
    d = E.decide(ctx, s, p)
    assert _place_cop(d) == [], "5 s dopo non si ritenta: il bet delay e' 5 s"
    assert d.telemetry["cover_wait"]["reason"] == "ritmo_minimo"
    assert E.attesa_ritento_copertura(ctx, s, p) == pytest.approx(15.0, abs=0.01)

    dopo = _snap_copre(now=s.now + 14.0)
    assert _place_cop(E.decide(ctx, dopo, p)) == [], "14 s non bastano"
    dopo = _snap_copre(now=s.now + 15.5)
    assert _place_cop(E.decide(ctx, dopo, p)), "passato il ritmo minimo si ritenta"


def test_il_ritmo_minimo_non_consuma_i_tentativi_del_riprezzo():
    """``attempts`` governa ``close_max_attempts``: un tentativo che non e' mai
    partito non deve consumarlo (altrimenti il freno esaurirebbe il riprezzo)."""
    p = params(cover_retry_min_s=60, close_retry_s=1)
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", entry_price_initial=1.50, attempts=0)
    ctx.legs.append(fill(E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="back", price=1.50, size=20.0)))
    cop = E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER, side="back",
                price=6.0, size=4.0, ref="over_cover-0-1", status="pending",
                placed_at=KO + 10 * 60)
    ctx.legs.append(cop)
    E.segna_tentativo_copertura(ctx, KO + 10 * 60)
    d = E.decide(ctx, _snap_copre(now=KO + 10 * 60 + 30), p)
    assert d.updates.get("attempts") is None
    assert [a for a in d.actions if a.role == "over_cover"] == [], (
        "niente riprezzo: ne' l'annullo ne' il piazzamento")


def test_a_freno_scattato_il_riprezzo_NON_annulla_la_copertura_gia_sul_book():
    """Annullare senza poter ripiazzare lascerebbe la posizione ANCORA PIU'
    scoperta: il freno toglie la coppia cancel+place, non mezza coppia."""
    p = params(cover_rifiuti_max=1, close_retry_s=1)
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", entry_price_initial=1.50)
    ctx.legs.append(fill(E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="back", price=1.50, size=20.0)))
    ctx.legs.append(E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                          side="back", price=6.0, size=4.0, ref="over_cover-0-1",
                          status="pending", placed_at=KO + 10 * 60))
    _rifiuta(ctx, p, "CANCELLED_NOT_PLACED", t0=KO - 3600)
    d = E.decide(ctx, _snap_copre(now=KO + 10 * 60 + 30), p)
    assert [a for a in d.actions if a.role == "over_cover"] == []
    assert d.state == "LIVE_COVER_PENDING", "la copertura vecchia e' ancora sul book"


# ===========================================================================
# 4. LO STATO DEL MERCATO DURANTE LA COPERTURA (ordine 5)
# ===========================================================================
def test_a_mercato_Over45_SOSPESO_la_copertura_non_parte_e_si_ASPETTA():
    p = params()
    ctx = _ctx_scoperto()
    d = E.decide(ctx, _snap_copre(o45_status="SUSPENDED"), p)
    assert _place_cop(d) == []
    assert d.state == "LIVE_UNCOVERED", "sospeso non e' chiuso: si aspetta"
    assert "sospeso" in d.reason
    assert d.telemetry["cover_wait"]["reason"] == "mercato_non_aperto"
    assert d.telemetry["cover_wait"]["stato_mercato"] == E.STATO_SOSPESO


@pytest.mark.parametrize("stato", ["CLOSED", "INACTIVE", "", "QUALCOSA_DI_NUOVO"])
def test_nessun_place_di_copertura_se_il_mercato_non_e_APERTO(stato):
    """Fail-closed: chiuso, non attivo e IGNOTO valgono tutti «non adesso»."""
    d = E.decide(_ctx_scoperto(), _snap_copre(o45_status=stato), params())
    assert _place_cop(d) == [], stato


def test_senza_il_book_Over45_la_copertura_non_parte():
    """Nessuna notizia non e' una buona notizia: ``stato_mercato(None)`` e'
    IGNOTO, mai «aperto»."""
    d = E.decide(_ctx_scoperto(), _snap_copre(o45=False), params())
    assert _place_cop(d) == []


def test_alla_RIAPERTURA_la_copertura_riparte_da_dove_era_rimasta():
    p = params()
    ctx = _ctx_scoperto()
    assert _place_cop(E.decide(ctx, _snap_copre(o45_status="SUSPENDED"), p)) == []
    d = E.decide(ctx, _snap_copre(o45_status="OPEN"), p)
    assert _place_cop(d), "riaperto: la copertura riprende"
    assert d.state == "LIVE_COVER_PENDING"


def test_a_mercato_sospeso_il_RIPREZZO_non_annulla_e_non_ripiazza():
    """Il riprezzo di ``_decide_cover_pending`` non guardava il mercato: il
    cancel sarebbe partito e il place no."""
    p = params(close_retry_s=1)
    ctx = E.MatchCtx(state="LIVE_COVER_PENDING", entry_price_initial=1.50)
    ctx.legs.append(fill(E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="back", price=1.50, size=20.0)))
    ctx.legs.append(E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                          side="back", price=6.0, size=4.0, ref="over_cover-0-1",
                          status="pending", placed_at=KO + 10 * 60))
    d = E.decide(ctx, _snap_copre(now=KO + 10 * 60 + 30, o45_status="SUSPENDED"), p)
    assert d.actions == [], "a mercato sospeso non si annulla e non si ripiazza"
    assert d.state == "LIVE_COVER_PENDING" and "sospeso" in d.reason


# ===========================================================================
# 5. IL SERVIZIO — dove il rifiuto arriva davvero
# ===========================================================================
def _info():
    return F.event_info("E1", payload(inplay=True, minute=20, sh=1, sa=0))


def _gamba_cop(size=1.21, price=5.4):
    return E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER, side="back",
                 price=price, size=size, ref="over_cover-0-1")


def _book_over(status="OPEN"):
    return E.Book(best_back=5.4, back_size=50.0, best_lay=5.6, lay_size=50.0,
                  status=status, inplay=True)


def _rifiuto_vero(codice="CANCELLED_NOT_PLACED") -> PlaceOutcome:
    """L'esito COSTRUITO COME LO COSTRUISCE LA PRODUZIONE
    (``execution.place``, ramo ``PlaceRifiutato``): stesso tipo, stessi campi,
    stessa grafia di ``fill_note``. Un finto con altre chiavi certificherebbe il
    difetto invece del comportamento (catalogo §7.27)."""
    return PlaceOutcome("error", None, 0.0, None, f"live_rifiutato:{codice}",
                        size_requested=1.21, size_remaining=0.0, error_code=codice)


_NIENTE = object()      # «non passato», che e' diverso da «book assente»


def _esegui(db, ctx, leg, *, market=None, book=_NIENTE, mode="live", p=None, now=NOW):
    return S.execute_place(db=db, market=market or FakeMarket(), info=_info(), leg=leg,
                           book=(_book_over() if book is _NIENTE else book), mode=mode,
                           params=p or C.merge_params({"cover_rifiuti_max": 3}),
                           now=now, dry=False, minute=20, score="1-0", ctx=ctx)


def test_il_rifiuto_di_betfair_sulla_copertura_si_CONTA_e_alla_soglia_BLOCCA(monkeypatch):
    chiamate: List[str] = []

    def finta_place(**kw):
        chiamate.append(str(kw.get("client_ref")))
        return _rifiuto_vero()

    monkeypatch.setattr(S.X, "place", finta_place)
    db = FakeDB(mode="live")
    ctx = _ctx_scoperto()
    p = C.merge_params({"cover_rifiuti_max": 3})

    for i in range(3):
        leg = _gamba_cop()
        leg.ref = f"over_cover-0-{i + 1}"
        assert _esegui(db, ctx, leg, p=p, now=NOW + timedelta(seconds=30 * i)) == "cancelled"

    assert len(chiamate) == 3, "i primi tre tentativi partono davvero"
    fermo = E.copertura_bloccata(ctx)
    assert fermo is not None and fermo["conteggio"] == 3
    assert fermo["error_code"] == "CANCELLED_NOT_PLACED"

    # la NOTIZIA: critica, con il codice e il CONTEGGIO
    rifiuti = [pl for k, pl, _ in db.activity if k == "place_rifiutato"]
    assert rifiuti and rifiuti[-1]["error_code"] == "CANCELLED_NOT_PLACED"
    assert rifiuti[-1]["conteggio"] == 3 and rifiuti[-1]["critical"] is True
    bloccata = [pl for k, pl, _ in db.activity
                if k == "error" and pl.get("reason") == "copertura_bloccata"]
    assert len(bloccata) == 1, "il freno che scatta si dice UNA volta, e forte"
    assert bloccata[0]["critical"] is True and bloccata[0]["conteggio"] == 3
    assert bloccata[0]["stato_freno"] == E.COVER_BLOCCATA


def test_a_copertura_bloccata_execute_place_non_tocca_nemmeno_la_rete(monkeypatch):
    """Fail-closed, seconda barriera: se un percorso qualunque arrivasse qui con
    una copertura mentre il freno e' scattato, nessun ordine parte."""
    chiamate: List[str] = []
    monkeypatch.setattr(S.X, "place",
                        lambda **kw: chiamate.append("place") or _rifiuto_vero())
    db = FakeDB(mode="live")
    ctx = _ctx_scoperto()
    p = C.merge_params({"cover_rifiuti_max": 1})
    E.registra_rifiuto_copertura(ctx, error_code="CANCELLED_NOT_PLACED", motivo="",
                                 ref="over_cover-0-1", now=NOW.timestamp(), params=p)

    esito = _esegui(db, ctx, _gamba_cop(), p=p)
    assert esito == "cancelled" and chiamate == []
    saltati = [pl for k, pl, _ in db.activity
               if k == "skip" and pl.get("reason") == "copertura_bloccata"]
    assert saltati and saltati[0]["critical"] is True
    assert not db.trades, "nessuna riga riservata per un ordine che non parte"


def test_con_la_copertura_bloccata_le_USCITE_passano_lo_stesso(monkeypatch):
    """La verifica esplicita chiesta dall'utente: il freno riguarda SOLO
    l'ingresso/copertura, mai le uscite (memoria del 15/09)."""
    partite: List[str] = []

    def finta_place(**kw):
        partite.append(str(kw.get("client_ref")))
        return PlaceOutcome("open", 1.30, 5.0, "bet-1", "live_matched",
                            size_requested=5.0, size_remaining=0.0)

    monkeypatch.setattr(S.X, "place", finta_place)
    db = FakeDB(mode="live")
    ctx = _ctx_scoperto()
    p = C.merge_params({"cover_rifiuti_max": 1})
    E.registra_rifiuto_copertura(ctx, error_code="CANCELLED_NOT_PLACED", motivo="",
                                 ref="over_cover-0-1", now=NOW.timestamp(), params=p)
    assert E.copertura_bloccata(ctx) is not None

    uscita = E.Leg(role="under_close", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                   side="lay", price=1.30, size=5.0, ref="under_close-0-9")
    book_u35 = E.Book(best_back=1.28, back_size=50.0, best_lay=1.30, lay_size=50.0,
                      status="OPEN", inplay=True)
    assert _esegui(db, ctx, uscita, book=book_u35, p=p) == "open"
    assert partite, "un'uscita non deve MAI essere frenata dal freno della copertura"


def test_execute_place_non_piazza_a_mercato_non_OPEN(monkeypatch):
    chiamate: List[str] = []
    monkeypatch.setattr(S.X, "place",
                        lambda **kw: chiamate.append("place") or _rifiuto_vero())
    db = FakeDB(mode="live")
    ctx = _ctx_scoperto()
    for stato, atteso in (("SUSPENDED", E.STATO_SOSPESO), ("CLOSED", E.STATO_CHIUSO),
                          ("INACTIVE", E.STATO_CHIUSO), ("BOH", E.STATO_IGNOTO)):
        leg = _gamba_cop()
        assert _esegui(db, ctx, leg, book=_book_over(stato)) == "cancelled", stato
        salti = [pl for k, pl, _ in db.activity if k == "skip"]
        assert salti[-1]["stato_mercato"] == atteso, stato
    # e senza book non si piazza affatto (IGNOTO)
    assert _esegui(db, ctx, _gamba_cop(), book=None) == "cancelled"
    assert chiamate == [], "nessun ordine puo' partire a mercato non aperto"
    assert not db.trades


def test_il_tentativo_di_copertura_fa_partire_l_orologio_del_ritmo(monkeypatch):
    monkeypatch.setattr(S.X, "place", lambda **kw: _rifiuto_vero())
    db = FakeDB(mode="live")
    ctx = _ctx_scoperto()
    _esegui(db, ctx, _gamba_cop())
    assert ctx.cover_rifiuti is not None
    assert ctx.cover_rifiuti["ultimo_ts"] == pytest.approx(NOW.timestamp(), abs=0.01)


def test_l_orologio_del_ritmo_parte_anche_quando_la_copertura_VA_A_BUON_FINE(monkeypatch):
    """⚠️ TROVATO DALLA FALSIFICAZIONE (M10). Il test qui sopra non bastava:
    su un RIFIUTO l'orologio lo scrive anche ``registra_rifiuto_copertura``,
    quindi spegnere ``segna_tentativo_copertura`` restava verde. Il ritmo pero'
    deve valere fra DUE TENTATIVI qualunque — una copertura abbinata e la
    tranche successiva comprese — perche' e' il tentativo, non l'esito, che
    consuma una chiamata a Betfair e un bet delay."""
    monkeypatch.setattr(S.X, "place", lambda **kw: PlaceOutcome(
        "open", 5.4, 1.21, "bet-9", "live_matched", size_requested=1.21, size_remaining=0.0))
    db = FakeDB(mode="live")
    ctx = _ctx_scoperto()
    assert _esegui(db, ctx, _gamba_cop()) == "open"
    assert ctx.cover_rifiuti is not None, (
        "l'orologio del ritmo minimo deve partire anche su un piazzamento riuscito")
    assert ctx.cover_rifiuti["ultimo_ts"] == pytest.approx(NOW.timestamp(), abs=0.01)
    assert ctx.cover_rifiuti["conteggio"] == 0 and ctx.cover_rifiuti["bloccata"] is False
    # e il freno NON e' scattato: un piazzamento riuscito non e' un rifiuto
    assert E.copertura_bloccata(ctx) is None
    p = C.merge_params({"cover_retry_min_s": 15})
    assert E.attesa_ritento_copertura(
        ctx, _snap_copre(now=NOW.timestamp() + 5.0), p) == pytest.approx(10.0, abs=0.01)


# ===========================================================================
# 6. LE TRANSIZIONI DI STATO DEL MERCATO, DETTE UNA VOLTA SOLA
# ===========================================================================
def _ev():
    return {"event_id": "E1", "markets": {E.MARKET_OU35: {"market_id": "1.35"},
                                          E.MARKET_OU45: {"market_id": "1.45"}}}


def _guarda(db, ctx, *, stato="OPEN", o45=True, t=KO):
    S._sorveglia_mercato_copertura(db=db, ctx=ctx, snap=_snap_copre(now=t, o45_status=stato,
                                                                   o45=o45),
                                   now_ts=t, ev=_ev())


def test_la_sospensione_del_mercato_della_copertura_si_dice_UNA_volta():
    db = FakeDB()
    ctx = _ctx_scoperto()
    _guarda(db, ctx)                                  # prima lettura, tutto regolare
    assert db.kinds() == [], "un mercato aperto non e' una notizia"

    _guarda(db, ctx, stato="SUSPENDED", t=KO + 5)
    sosp = [pl for k, pl, _ in db.activity if k == "mercato_sospeso"]
    assert len(sosp) == 1
    assert sosp[0]["stato"] == E.STATO_SOSPESO and sosp[0]["mercato"] == E.MARKET_OU45
    assert sosp[0]["market_id"] == "1.45" and sosp[0]["critical"] is True
    assert sosp[0]["fase"] == "copertura"

    _guarda(db, ctx, stato="SUSPENDED", t=KO + 10)     # ancora sospeso: niente di nuovo
    _guarda(db, ctx, stato="SUSPENDED", t=KO + 15)
    assert len([k for k, _, _ in db.activity if k == "mercato_sospeso"]) == 1, (
        "una riga per TRANSIZIONE, non una per giro: sono 104 righe l'ora")


def test_la_riapertura_del_mercato_della_copertura_e_una_notizia():
    db = FakeDB()
    ctx = _ctx_scoperto()
    _guarda(db, ctx, stato="SUSPENDED")
    _guarda(db, ctx, stato="OPEN", t=KO + 20)
    riap = [pl for k, pl, _ in db.activity
            if k == "skip" and pl.get("reason") == "mercato_riaperto"]
    assert len(riap) == 1 and riap[0]["stato"] == E.STATO_APERTO
    assert riap[0]["mercato"] == E.MARKET_OU45


def test_il_book_che_SPARISCE_vale_come_non_aperto():
    """Difetto 9 del catalogo: il dato assente letto come zero. Qui l'assenza e'
    IGNOTO, ed e' una notizia critica come la sospensione."""
    db = FakeDB()
    ctx = _ctx_scoperto()
    _guarda(db, ctx)
    _guarda(db, ctx, o45=False, t=KO + 5)
    sosp = [pl for k, pl, _ in db.activity if k == "mercato_sospeso"]
    assert len(sosp) == 1 and sosp[0]["stato"] == E.STATO_IGNOTO


def test_fuori_dalla_copertura_lo_stato_dell_over45_non_si_sorveglia():
    """Rumore inutile: se non c'e' nessuna copertura da fare, una sospensione
    dell'Over 4.5 non riguarda nessun ordine di Mike."""
    db = FakeDB()
    ctx = _ctx_scoperto()
    ctx.state = "PRE_OPEN"
    ctx.legs = [l for l in ctx.legs if l.role != "over_cover"]
    _guarda(db, ctx, stato="SUSPENDED")
    assert db.kinds() == []


# ===========================================================================
# 7. PERSISTENZA E RIAVVIO — difetto 19 del catalogo
# ===========================================================================
def test_il_freno_e_lo_stato_del_mercato_sopravvivono_al_riavvio():
    p = params(cover_rifiuti_max=2)
    ctx = _ctx_scoperto()
    _rifiuta(ctx, p, "CANCELLED_NOT_PLACED", quante=2)
    ctx.cover_mercato = {"stato": E.STATO_SOSPESO, "ts": KO}

    riga = S._row_from_ctx({"event_id": "E1"}, ctx, {})
    rinato = S._ctx_from_row(riga)

    fermo = E.copertura_bloccata(rinato)
    assert fermo is not None and fermo["conteggio"] == 2
    assert fermo["error_code"] == "CANCELLED_NOT_PLACED"
    assert rinato.cover_mercato == {"stato": E.STATO_SOSPESO, "ts": KO}
    assert "cover_rifiuti" in S._CTX_FIELDS and "cover_mercato" in S._CTX_FIELDS


# ===========================================================================
# 8. L'INTERVENTO UMANO — «Riprendi» dalla UI
# ===========================================================================
def test_riprendi_dalla_UI_sblocca_la_copertura():
    p = C.merge_params({"cover_rifiuti_max": 1})
    ctx = _ctx_scoperto()
    E.registra_rifiuto_copertura(ctx, error_code="CANCELLED_NOT_PLACED", motivo="",
                                 ref="over_cover-0-1", now=NOW.timestamp(), params=p)
    riga = S._row_from_ctx({"event_id": "E1", "state": ctx.state}, ctx, {})

    db = FakeDB()
    db.events["E1"] = riga
    req = {"id": 1, "kind": "resume_event", "payload": {"event_id": "E1"}, "status": "pending"}
    db.requests.append(req)
    S.process_requests(db=db, market=FakeMarket(), events={"E1": riga},
                       rows_by_event={}, params=p, now=NOW, dry=False)

    assert req["result"]["ok"] is True
    rinato = S._ctx_from_row(db.events["E1"])
    assert E.copertura_bloccata(rinato) is None, "l'utente ha riaperto la copertura"
    ripresa = [pl for k, pl, _ in db.activity if k == "resume_event"]
    assert ripresa and ripresa[0]["copertura_sbloccata"]["conteggio"] == 1


# ===========================================================================
# 9. I DUE PARAMETRI NUOVI — whitelist, limiti, clamp
# ===========================================================================
def test_i_due_parametri_nuovi_sono_in_whitelist_coi_loro_limiti():
    assert C.PARAM_SPEC["cover_rifiuti_max"] == (3, int, 1, 20, None)
    assert C.PARAM_SPEC["cover_retry_min_s"] == (15, int, 1, 300, None)
    p = C.merge_params({"cover_rifiuti_max": 999, "cover_retry_min_s": 0})
    assert p["cover_rifiuti_max"] == 20 and p["cover_retry_min_s"] == 1
    p = C.merge_params(None)
    assert p["cover_rifiuti_max"] == 3 and p["cover_retry_min_s"] == 15
