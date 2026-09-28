"""D1-bis (28/09) - IL FRENO DELLA COPERTURA SCATTA ANCHE QUANDO L'ORDINE PASSA DAL RUNNER.

Reperto del coordinatore: ``certifica mike 35760084 --scenari copertura-rifiutata
--trasporto canale`` -> KO S3 x4 («coperture gia' RIFIUTATE e il bot ne piazza
un'altra»), S1 x0 (freno MAI scattato). Stesso scenario sul trasporto coda: OK.

Causa: il conteggio del rifiuto (``engine.registra_rifiuto_copertura``) stava
solo nel ramo SINCRONO di ``service.execute_place`` (esito nella risposta REST).
Il PAPER di Mike dal 29/09 passa dal runner e l'esito arriva dopo, letto da
``_segui_ordini_paper_su_runner``: li' il FOK non abbinato chiudeva la gamba
(``_rifiutata`` + ``no_fill``) senza contare -> copertura ripresentata
all'infinito, il 17/09 in paper.

Finti: runner finto sul protocollo VERO (``runner_finto``: validazione, ack ed
eventi ``order`` di produzione, fase da ``motore_ordini.fase_da_riga`` sulle
chiavi di ``CHIAVI_SPECCHIO``), ``DbMemoria`` del banco, ``EventInfo``/``Book``
di produzione, ``PlaceResult`` vero di ``omega_market`` per il live.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import EVENTO, db_vuoto, info_vera
from Betfair.omega.omega_market import PlaceResult
from Betfair.safe_strategy import execution as X
from Betfair.stream import motore_ordini as MO

ORA = datetime(2026, 9, 28, 16, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freni_aperti(monkeypatch):
    monkeypatch.setattr(X, "_freno_aperture", lambda: None)
    monkeypatch.setattr(X, "_live_brake", lambda: None)
    monkeypatch.setattr(S, "_freno_aperture_rest", lambda: None)
    monkeypatch.setattr(S, "mike_live_abilitato", lambda: True)

    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)


def _params(**kw: Any) -> Dict[str, Any]:
    p = dict(C.merge_params(None))
    p.update(kw)
    return p


def _book() -> E.Book:
    return E.Book(status="OPEN", best_back=1.53, back_size=100.0, best_lay=1.55,
                  lay_size=100.0, inplay=True)


def _gamba(n: int, role: str = "over_cover") -> E.Leg:
    if role == "over_cover":
        return E.Leg(role=role, market=E.MARKET_OU45, selection=E.SEL_OVER, side="back",
                     price=1.52, size=3.0, ref=f"over_cover-0-{n}", cycle_no=0,
                     placed_at=ORA.timestamp() + n)
    return E.Leg(role=role, market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                 price=1.52, size=3.0, ref=f"{role}-0-{n}", cycle_no=0,
                 placed_at=ORA.timestamp() + n)


def _piazza(db, ctx: E.MatchCtx, leg: E.Leg, mode: str, market: Any, params, n: int) -> str:
    ctx.legs.append(leg)
    return S.execute_place(db=db, market=market, info=info_vera(), leg=leg, book=_book(),
                           mode=mode, params=params, now=ORA + timedelta(seconds=20 * n),
                           dry=False, feed_fresh=True, ctx=ctx)


def _conteggio(ctx: E.MatchCtx) -> int:
    return int((ctx.cover_rifiuti or {}).get("conteggio") or 0)


def _attivita(db, kind: str, reason: Optional[str] = None) -> List[Dict[str, Any]]:
    return [p for k, p, _e in db.attivita
            if k == kind and (reason is None or p.get("reason") == reason)]


# ---------------------------------------------------------------------------
# 1. il FOK della copertura non abbinato sul RUNNER si conta, e il freno scatta
# ---------------------------------------------------------------------------
def test_fok_copertura_non_abbinato_sul_runner_conta_e_fa_scattare_il_freno(runner):
    runner.rifiuta_fok = True
    db = db_vuoto()
    ctx = E.MatchCtx(legs=[])
    par = _params(cover_rifiuti_max=3)
    for n in (1, 2, 3):
        leg = _gamba(n)
        esito = _piazza(db, ctx, leg, "paper", SimpleNamespace(), par, n)
        assert esito == "cancelled" and leg.status == "cancelled"
        # l'evento del runner e' quello VERO: fase calcolata da motore_ordini
        e = runner.esiti(runner.comandi[-1]["ref"])
        assert e["fase"] == "annullato" and MO.fase_da_riga(e) == "annullato"
        assert _conteggio(ctx) == n, f"rifiuto {n} della copertura non contato"
    fermo = E.copertura_bloccata(ctx)
    assert fermo is not None, "tre FOK non abbinati e il freno NON e' scattato"
    # stesso argomento che il sincrono da' per lo stesso esito: nessun codice di
    # Betfair (l'evento non lo porta), il motivo scritto sulla riga
    assert fermo["error_code"] == "runner_annullato"
    bloccate = _attivita(db, "error", "copertura_bloccata")
    assert len(bloccate) == 1 and bloccate[0]["conteggio"] == 3 and bloccate[0]["max"] == 3
    # e a freno scattato la quarta copertura non parte nemmeno
    comandi_prima = len(runner.comandi)
    leg4 = _gamba(4)
    assert _piazza(db, ctx, leg4, "paper", SimpleNamespace(), par, 4) == "cancelled"
    assert len(runner.comandi) == comandi_prima, "a freno scattato e' partito un ordine"


def test_scadenza_sul_runner_conta_col_suo_motivo(runner):
    """``scaduto`` (LAPSE / BET_TAKEN_OR_LAPSED in flumine) e ``annullato``
    (FOK ucciso) sono esiti diversi: codici diversi, come in live
    ``live_not_matched:EXPIRED`` e ``...:<codice>``."""
    runner.trattieni = True
    db = db_vuoto()
    ctx = E.MatchCtx(legs=[])
    par = _params(cover_rifiuti_max=3)
    leg = _gamba(1)
    ctx.legs.append(leg)
    # il taker parte e resta in attesa (esito non ancora arrivato)
    runner.rifiuta_fok = False
    S.execute_place(db=db, market=SimpleNamespace(), info=info_vera(), leg=leg, book=_book(),
                    mode="paper", params=par, now=ORA, dry=False, feed_fresh=True, ctx=ctx)
    assert leg.status == "pending" and _conteggio(ctx) == 0
    ref = runner.comandi[-1]["ref"]
    # il finto abbina subito i FOK: qui l'ordine NON si e' abbinato e il runner
    # lo dichiara scaduto (size_lapsed), l'unico evento che esce
    runner._trattenuti.clear()
    riga = runner.ordine(ref)
    riga.update({"size_matched": 0.0, "size_remaining": riga["size"],
                 "average_price_matched": 0.0, "status": "EXECUTABLE"})
    runner.trattieni = False
    runner.scadi(ref)
    assert runner.esiti(ref)["fase"] == "scaduto"
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp() + 5, params=par)
    assert leg.status == "cancelled"
    assert (ctx.cover_rifiuti or {}).get("error_code") == "runner_scaduto"
    assert _conteggio(ctx) == 1


# ---------------------------------------------------------------------------
# 2. lo STESSO evento terminale riletto non si conta due volte
# ---------------------------------------------------------------------------
def test_lo_stesso_evento_terminale_riletto_non_si_conta_due_volte(runner):
    runner.rifiuta_fok = True
    db = db_vuoto()
    ctx = E.MatchCtx(legs=[])
    par = _params(cover_rifiuti_max=3)
    leg = _gamba(1)
    _piazza(db, ctx, leg, "paper", SimpleNamespace(), par, 1)
    assert _conteggio(ctx) == 1
    # la gamba torna «viva» (ctx ripreso da prima dell'esito, es. riavvio): il
    # runner ripete lo STESSO evento (stesso seq); la riga lo ha gia' applicato
    seq = int(runner.esiti(runner.comandi[-1]["ref"])["seq"])
    assert int(db.trades_for_event(EVENTO)[-1]["meta"]["canale_seq"]) == seq
    for giro in (1, 2, 3):
        leg.status = "pending"
        S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                        now_ts=ORA.timestamp() + 20 * giro, params=par)
        assert leg.status == "cancelled"
    assert _conteggio(ctx) == 1, "un solo rifiuto contato piu' volte: freno falso"
    assert E.copertura_bloccata(ctx) is None


# ---------------------------------------------------------------------------
# 3. solo la COPERTURA si conta: le altre gambe mai
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ruolo", ["under_entry", "reentry"])
def test_fok_non_abbinato_di_un_altra_gamba_non_tocca_il_freno(runner, ruolo):
    runner.rifiuta_fok = True
    db = db_vuoto()
    ctx = E.MatchCtx(legs=[])
    par = _params(cover_rifiuti_max=1)
    leg = _gamba(1, role=ruolo)
    assert _piazza(db, ctx, leg, "paper", SimpleNamespace(), par, 1) == "cancelled"
    assert leg.status == "cancelled"
    assert _conteggio(ctx) == 0 and E.copertura_bloccata(ctx) is None
    assert _attivita(db, "error", "copertura_bloccata") == []


# ---------------------------------------------------------------------------
# 4. il ramo SINCRONO (live) usa la stessa funzione: codice di Betfair passato
# ---------------------------------------------------------------------------
def _mercato_live(risultati: List[PlaceResult]) -> SimpleNamespace:
    def place_order_live(**_kw):
        return risultati.pop(0)
    return SimpleNamespace(place_order_live=place_order_live)


def test_sincrono_rifiuto_col_codice_conta_per_codice_e_scrive_place_rifiutato():
    db = db_vuoto()
    ctx = E.MatchCtx(legs=[])
    par = _params(cover_rifiuti_max=2)
    rifiuto = dict(ok=False, order_status="EXPIRED", bet_id=None, size_matched=0.0,
                   avg_price_matched=None, raw={}, error_code="INVALID_BET_SIZE")
    mercato = _mercato_live([PlaceResult(**rifiuto), PlaceResult(**rifiuto)])
    for n in (1, 2):
        assert _piazza(db, ctx, _gamba(n), "live", mercato, par, n) == "cancelled"
    fermo = E.copertura_bloccata(ctx)
    assert fermo is not None and fermo["error_code"] == "INVALID_BET_SIZE"
    righe = [p for p in _attivita(db, "place_rifiutato") if p.get("leg")]
    assert [p["conteggio"] for p in righe] == [1, 2]
    assert all(p["error_code"] == "INVALID_BET_SIZE" and p["max"] == 2 for p in righe)
    assert len(_attivita(db, "error", "copertura_bloccata")) == 1


# ---------------------------------------------------------------------------
# 6. la porta di Mike e il contratto del place-and-trim (INTERFACES.md,
#    «Place-and-trim: contratto del modulo UNICO»): la porta NON e' un secondo
#    place-and-trim. Sotto il minimo passa il comando cosi' com'e' (niente FOK,
#    importo al centesimo, niente chiavi della sequenza): la macchina e' quella
#    del worker dentro il motore.
# ---------------------------------------------------------------------------
def test_porta_di_mike_sotto_il_minimo_non_aggiunge_fok_ne_tocca_l_importo():
    from Betfair.mike import porta_ordini as MP
    from Betfair.safe_strategy import porta_ordini as PO

    c = PO.costruisci_comando(ref="mike-t41", attore="mike", azione="place", mode="paper",
                              market_id="1.259475534", selection_id=1222346, side="back",
                              price=3.9, size=1.26, persistence="LAPSE",
                              max_eta_ms=PO.MAX_ETA_MS, origine={"tabella": "x", "id": 41},
                              time_in_force=None, reduces_liability=False)
    d = MP.adatta_comando(c)
    assert d["time_in_force"] is None, "FOK sotto il minimo: il motore rifiuta la sequenza"
    assert (d["size"], d["price"]) == (1.26, 3.9), "importo o quota ritoccati dalla porta"
    assert set(d) == set(PO.CHIAVI_COMANDO), "chiavi fuori protocollo: niente sequenza in casa"
    # sopra il minimo il FOK scelto da execution resta
    c2 = dict(c, size=3.0, time_in_force=PO.FOK)
    assert MP.adatta_comando(c2)["time_in_force"] == PO.FOK


# ---------------------------------------------------------------------------
# 5. PARITA': lo stesso esito (FOK senza controparte) da' la stessa dinamica
#    del freno in live (REST, sincrono) e in paper (runner, asincrono)
# ---------------------------------------------------------------------------
def test_parita_live_paper_fok_senza_controparte_stessa_dinamica_del_freno(runner):
    par = _params(cover_rifiuti_max=3)
    fok_ucciso = dict(ok=True, order_status="EXPIRED", bet_id="B1", size_matched=0.0,
                      avg_price_matched=None, raw={})
    db_l, ctx_l = db_vuoto(), E.MatchCtx(legs=[])
    mercato = _mercato_live([PlaceResult(**fok_ucciso) for _ in range(3)])
    live = []
    for n in (1, 2, 3):
        _piazza(db_l, ctx_l, _gamba(n), "live", mercato, par, n)
        live.append((_conteggio(ctx_l), bool(E.copertura_bloccata(ctx_l))))
    runner.rifiuta_fok = True
    db_p, ctx_p = db_vuoto(), E.MatchCtx(legs=[])
    paper = []
    for n in (1, 2, 3):
        _piazza(db_p, ctx_p, _gamba(n), "paper", SimpleNamespace(), par, n)
        paper.append((_conteggio(ctx_p), bool(E.copertura_bloccata(ctx_p))))
    assert live == [(1, False), (2, False), (3, True)]
    assert paper == live, f"paper {paper} diverso dal live {live}"
    assert len(_attivita(db_l, "error", "copertura_bloccata")) == 1
    assert len(_attivita(db_p, "error", "copertura_bloccata")) == 1
