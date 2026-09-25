"""IL LOOP DEL `taker` — 531 volte la stessa uscita, 3 ordini a mercato (16/09).

LA SCENA, ricostruita sul banco dalla registrazione vera 35674515 (COMPLETE,
`python -m Betfair.stream.backtest.certifica mike 35674515 --scenari taker`):

    19'  1-0 -> 2-0   il re-ingresso Under 4.5 si abbina a 1,76
    19'               il motore appoggia la green del re-ingresso: lay 10,11 @ 1,75
    19'               `pre_exit_mode='taker'` -> la gamba NON e' una resting, passa
                      da `execute_place`, che chiede al book: best_lay 1,80 > 1,75.
                      Nessun ordine nasce. `no_fill`. La gamba muore 'cancelled'
                      PRIMA che venga scritta la riga di riserva.
    19' -> 38'        il motore torna in REENTRY_OPEN, non vede nessuna green viva,
                      e rifa la STESSA IDENTICA domanda. 531 volte di fila, una al
                      secondo, fino a fine registrazione.

    referto: 560 gambe proposte, 3 ordini piazzati (187x), P1/P2/P3 tutte rosse.

LA RADICE, in una riga: **il rifiuto del mercato non tornava indietro.** La riga
di `mike_trades` non veniva scritta (l'ordine non e' mai partito), quindi il
freno anti-duplicato del 15/09 — che guarda le righe 'pending' — non aveva
niente da trovare; e il `ctx` non conservava nessuna traccia del tentativo, per
cui `green is None or not green.is_live` era vero a ogni giro.

Il ramo FRATELLO lo faceva gia' giusto: `_decide_ko_green` guarda la gamba
precedente, vede che non e' entrata e aspetta `ko_green_retry_s` — e infatti
sulla stessa partita fa 27 tentativi, non 531. La differenza fra 27 e 531 e'
tutta li'.

CHE COSA NON CAMBIA: prezzi, soglie, quando si esce, quante gambe la spec
prevede. La Costituzione prevede UNA lay di re-ingresso che resta sul book fino
a fine gara (§3 Fase 6) e UNA green per ciclo pre-match (§3 Fase 1). Il motore
finalmente lo rispetta. In `resting` — cioe' in produzione — non cambia nulla:
li' la gamba resta viva sul book e questo ramo non scatta mai.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import feed as F
from Betfair.mike import service as S
from Betfair.safe_strategy import execution as X
from Betfair.stream.backtest.banco_comune import DbMemoria


# ---------------------------------------------------------------------------
# il banco minimo: il DB in memoria del banco comune e l'EventInfo VERA
# ---------------------------------------------------------------------------
EVENTO = "35674515"
ORA = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)


def info_vera() -> F.EventInfo:
    """La `EventInfo` di produzione, non un doppio: e' la classe che
    `execute_place` interroga per mercato, selezione e nome."""
    return F.EventInfo(
        event_id=EVENTO, event_name="Shanghai Port v Qingdao West Coast",
        home="Shanghai Port", away="Qingdao West Coast", competition="Chinese Super League",
        ko_at=ORA.timestamp() + 3600.0, open_date=None,
        markets={E.MARKET_OU35: "1.245111111", E.MARKET_OU45: "1.245222222"},
        selections={(E.MARKET_OU35, E.SEL_UNDER): 47973, (E.MARKET_OU35, E.SEL_OVER): 47972,
                    (E.MARKET_OU45, E.SEL_UNDER): 48901, (E.MARKET_OU45, E.SEL_OVER): 48900})


def db_vuoto() -> DbMemoria:
    return DbMemoria({"status": "running", "mode": "paper", "params": {}})


def esito_abbinato(**kw: Any) -> X.PlaceOutcome:
    """Un esito VERO di `execution.place` (non un dizionario scritto a mano):
    e' la superficie su cui il 15/09 si sono rotte cinque cose."""
    base = dict(status="open", price=1.76, size=10.0, bet_id="B-1",
                fill_note="paper_fill", size_requested=10.0, size_remaining=0.0,
                avg_price_matched=1.76)
    base.update(kw)
    return X.PlaceOutcome(**base)


def params_taker(**kw: Any) -> Dict[str, Any]:
    # 25/09 sera: default di produzione ora False (manuale); questa suite
    # testa altro, nasce con le uscite automatiche come sempre.
    p = dict(C.merge_params(None))
    p["pre_exit_mode"] = "taker"
    p["uscite_automatiche"] = True
    p.update(kw)
    return p


# ---------------------------------------------------------------------------
# il giro del servizio, ridotto all'osso ma con le funzioni VERE
# ---------------------------------------------------------------------------
def giro(*, db: Any, ctx: E.MatchCtx, snap: E.Snapshot, params: Dict[str, Any],
         proposte: List[str], mode: str = "paper") -> E.Decision:
    """decide -> apply_decision -> execute_place, come in `service._run_event`."""
    d = E.decide(ctx, snap, params)
    for a in d.actions:
        if a.kind == "place":
            proposte.append(str(a.role))
    for leg in E.apply_decision(ctx, d, snap.now):
        S.execute_place(db=db, market=SimpleNamespace(), info=info_vera(), leg=leg,
                        book=snap.book(leg.market, leg.selection), mode=mode,
                        params=params, now=ORA, dry=False, minute=snap.minute,
                        score="2-0", feed_fresh=True, ctx=ctx)
    return d


def snap_reentry(now: float, *, best_lay_u45: float = 1.80) -> E.Snapshot:
    """Il mercato del 19': Under 4.5 back 1,76 / lay 1,80. Il target della green
    appoggiata (1,75) NON e' disponibile: e' il caso che ha prodotto il loop."""
    return E.Snapshot(
        now=now, ko_at=ORA.timestamp() - 1200.0,
        books={
            (E.MARKET_OU45, E.SEL_UNDER): E.Book(
                status="OPEN", best_back=1.76, back_size=500.0,
                best_lay=best_lay_u45, lay_size=500.0, inplay=True),
            (E.MARKET_OU45, E.SEL_OVER): E.Book(
                status="OPEN", best_back=2.30, back_size=500.0,
                best_lay=2.36, lay_size=500.0, inplay=True),
            (E.MARKET_OU35, E.SEL_UNDER): E.Book(
                status="OPEN", best_back=1.30, back_size=500.0,
                best_lay=1.33, lay_size=500.0, inplay=True),
        },
        inplay=True, minute=19, goals=1, feed_fresh=True, order_fresh=True,
        market_status="OPEN")


def ctx_flat_pronto_al_reingresso() -> E.MatchCtx:
    """FLAT dopo un ciclo chiuso in profitto: e' lo stato da cui la Fase 6
    fa partire il re-ingresso."""
    return E.MatchCtx(state="FLAT", cycle_no=0, entry_price_initial=1.60,
                      reentry_allowed=True, reentry_done=False)


# ===========================================================================
# 1. LA RIPRODUZIONE — 531 riproposizioni
# ===========================================================================
@pytest.mark.parametrize("giri", [600])
def test_la_green_del_reingresso_non_si_ripropone_a_ogni_giro(giri: int):
    """IL TEST DEL LOOP. Sul codice del 15/09 questo conta ~599 proposte di
    `reentry_green` contro UN solo ordine a mercato (il re-ingresso).
    La Costituzione, Fase 6, ne prevede UNA."""
    db, ctx = db_vuoto(), ctx_flat_pronto_al_reingresso()
    params = params_taker()
    proposte: List[str] = []
    orig, X.place = X.place, lambda **kw: esito_abbinato(size=float(kw["size"]),
                                                         price=float(kw["price"]))
    try:
        for i in range(giri):
            giro(db=db, ctx=ctx, snap=snap_reentry(1000.0 + i), params=params,
                 proposte=proposte)
    finally:
        X.place = orig

    assert proposte.count("reentry") == 1, "il re-ingresso e' UNO per partita (Fase 6)"
    n = proposte.count("reentry_green")
    assert n == 1, (
        f"la green del re-ingresso e' stata proposta {n} volte in {giri} giri. "
        f"La Fase 6 ne prevede UNA, appoggiata, che resta sul book fino a fine "
        f"gara: il resto e' riproposizione (531 volte sulla registrazione vera)")


def test_il_rifiuto_del_mercato_arriva_al_ctx():
    """La radice, isolata: `execute_place` rifiuta e il `ctx` se lo ricorda.
    Senza questo passaggio il motore non ha modo di sapere che ha gia' chiesto."""
    db, ctx = db_vuoto(), ctx_flat_pronto_al_reingresso()
    params = params_taker()
    proposte: List[str] = []
    orig, X.place = X.place, lambda **kw: esito_abbinato(size=float(kw["size"]),
                                                         price=float(kw["price"]))
    try:
        for i in range(3):
            giro(db=db, ctx=ctx, snap=snap_reentry(1000.0 + i), params=params,
                 proposte=proposte)
    finally:
        X.place = orig

    chiave = E.chiave_richiesta("reentry_green", 0, E.MARKET_OU45, E.SEL_UNDER, "lay", False)
    assert chiave in ctx.rifiuti, (
        "il rifiuto del mercato non e' arrivato al ctx: e' il dialogo mancante")
    assert "prezzo non disponibile" in str(ctx.rifiuti[chiave]["motivo"])
    assert "no_fill" in db.kinds()


def test_il_motore_DICE_perche_non_ripropone():
    """Un ordine che non parte deve dire perche': senza il motivo, «nessuna
    azione» e «non ci ho provato» in UI sono la stessa cosa."""
    db, ctx = db_vuoto(), ctx_flat_pronto_al_reingresso()
    params = params_taker()
    proposte: List[str] = []
    ultima: Optional[E.Decision] = None
    orig, X.place = X.place, lambda **kw: esito_abbinato(size=float(kw["size"]),
                                                         price=float(kw["price"]))
    try:
        for i in range(5):
            ultima = giro(db=db, ctx=ctx, snap=snap_reentry(1000.0 + i), params=params,
                          proposte=proposte)
    finally:
        X.place = orig

    assert ultima is not None and not ultima.actions
    assert "gia' rifiutata a mercato" in ultima.reason, ultima.reason


# ===========================================================================
# 2. IL FRENO NON DEVE SPEGNERE NIENTE DI LEGITTIMO
# ===========================================================================
def test_una_richiesta_DIVERSA_si_fa(monkeypatch):
    """Se cambia il prezzo (il book si e' mosso) o la size (fill parziale) la
    domanda e' NUOVA: si fa. Altrimenti il freno diventerebbe una regola di
    strategia, e le regole non si toccano."""
    ctx = E.MatchCtx(state="REENTRY_OPEN", cycle_no=0)
    gamba = E.Leg(role="reentry_green", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                  side="lay", price=1.75, size=10.11, ref="reentry_green-0-2",
                  status="cancelled")
    E.registra_rifiuto(ctx, gamba, "prezzo non disponibile (1.8)")

    identica = E._place("reentry_green", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.75, 10.11)
    assert E.tentativo_gia_rifiutato(ctx, identica) is not None

    altro_prezzo = E._place("reentry_green", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.74, 10.11)
    assert E.tentativo_gia_rifiutato(ctx, altro_prezzo) is None, (
        "il book si e' mosso: e' una domanda nuova")

    altra_size = E._place("reentry_green", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.75, 6.00)
    assert E.tentativo_gia_rifiutato(ctx, altra_size) is None, (
        "la posizione e' cambiata (fill parziale): e' una domanda nuova")

    altro_ciclo = E.MatchCtx(state="PRE_OPEN", cycle_no=1, rifiuti=dict(ctx.rifiuti))
    assert E.tentativo_gia_rifiutato(altro_ciclo, identica) is None, (
        "un ciclo nuovo riparte pulito: la spec prevede una green PER CICLO")


def test_un_esito_IGNOTO_non_e_un_rifiuto():
    """§4.11 — una gamba a esito ignoto non si da' mai per rifiutata: li' comanda
    la riconciliazione, e frenare il motore su un ordine che POTREBBE essere vivo
    e' un'altra cosa (e la fa gia' `_strip_openings`)."""
    db = db_vuoto()
    ctx = E.MatchCtx(state="REENTRY_OPEN", cycle_no=0)
    leg = E.Leg(role="reentry_green", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                side="lay", price=1.80, size=10.11, ref="reentry_green-0-2")
    book = E.Book(status="OPEN", best_back=1.76, back_size=500.0,
                  best_lay=1.80, lay_size=500.0, inplay=True)
    orig = X.place
    X.place = lambda **kw: X.PlaceOutcome(
        status="pending", price=None, size=0.0, bet_id=None,
        fill_note="place_exception_reconciling: timeout")
    try:
        esito = S.execute_place(db=db, market=SimpleNamespace(), info=info_vera(), leg=leg,
                                book=book, mode="live", params=params_taker(), now=ORA,
                                dry=False, ctx=ctx)
    finally:
        X.place = orig

    assert esito == "pending_reconcile" and leg.needs_reconcile
    assert ctx.rifiuti == {}, "un esito ignoto non e' un rifiuto"


def test_in_resting_non_cambia_niente():
    """In produzione (`pre_exit_mode='resting'`) la green resta VIVA sul book: il
    ramo che riproponeva non viene nemmeno raggiunto, e nessun rifiuto viene
    registrato. Se questo test diventa rosso, la produzione e' cambiata."""
    ctx = E.MatchCtx(state="REENTRY_OPEN", cycle_no=0)
    viva = E.Leg(role="reentry_green", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                 side="lay", price=1.75, size=10.11, ref="reentry_green-0-2",
                 status="pending")
    ingresso = E.Leg(role="reentry", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                     side="back", price=1.76, size=10.0, matched=10.0,
                     avg_price=1.76, ref="reentry-0-1", status="open")
    ctx.legs = [ingresso, viva]
    d = E.decide(ctx, snap_reentry(1000.0), C.merge_params(None))
    assert not d.actions and "green sul book" in d.reason


# ===========================================================================
# 3. IL RAMO TAKER DI PRE_OPEN (matrice C.10)
# ===========================================================================
def snap_pre_open(now: float, *, best_lay: float) -> E.Snapshot:
    return E.Snapshot(
        now=now, ko_at=now + 3600.0,
        books={
            (E.MARKET_OU35, E.SEL_UNDER): E.Book(
                status="OPEN", best_back=best_lay - 0.02, back_size=500.0,
                best_lay=best_lay, lay_size=500.0),
            (E.MARKET_OU35, E.SEL_OVER): E.Book(
                status="OPEN", best_back=3.00, back_size=500.0,
                best_lay=3.10, lay_size=500.0),
        },
        inplay=False, feed_fresh=True, order_fresh=True, market_status="OPEN")


def ctx_pre_open() -> E.MatchCtx:
    """Posizione pre-match aperta: BACK Under 3.5 da 10 EUR abbinato a 1,60."""
    ctx = E.MatchCtx(state="PRE_OPEN", cycle_no=0, entry_price_initial=1.60)
    ctx.legs = [E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                      side="back", price=1.60, size=10.0, matched=10.0, avg_price=1.60,
                      ref="under_entry-0-1", status="open")]
    ctx.seq = 1
    return ctx


def test_pre_open_taker_non_riemette_la_stessa_uscita_a_ogni_ciclo():
    """C.10: «il ramo taker di PRE_OPEN riemette la stessa uscita a ogni ciclo
    senza contatore ne' freno». Qui il rifiuto arriva da Betfair (FOK ucciso):
    la spec TACE su questo caso, quindi fail-closed — una proposta per gamba."""
    db, ctx = db_vuoto(), ctx_pre_open()
    params = params_taker()
    proposte: List[str] = []
    orig = X.place
    X.place = lambda **kw: X.PlaceOutcome(
        status="error", price=None, size=0.0, bet_id=None,
        fill_note="rifiutato", error_code="BET_TAKEN_OR_LAPSED")
    try:
        for i in range(200):
            giro(db=db, ctx=ctx, snap=snap_pre_open(1000.0 + i, best_lay=1.56),
                 params=params, proposte=proposte, mode="live")
    finally:
        X.place = orig

    n = proposte.count("under_green")
    assert n == 1, (
        f"il ramo taker di PRE_OPEN ha riemesso la stessa uscita {n} volte: la "
        f"Fase 1 prevede UNA green per ciclo")
    assert "place_rifiutato" in db.kinds(), "il codice di Betfair va scritto"


def test_pre_open_taker_riprova_quando_il_book_si_muove():
    """Il contrario deve restare vero: se il prezzo cambia, la domanda e' nuova
    e si rifa. Senza questo il freno sarebbe una modifica di strategia."""
    db, ctx = db_vuoto(), ctx_pre_open()
    params = params_taker()
    proposte: List[str] = []
    orig = X.place
    X.place = lambda **kw: X.PlaceOutcome(
        status="error", price=None, size=0.0, bet_id=None,
        fill_note="rifiutato", error_code="BET_TAKEN_OR_LAPSED")
    try:
        for i, lay in enumerate((1.56, 1.56, 1.55, 1.55, 1.54)):
            giro(db=db, ctx=ctx, snap=snap_pre_open(1000.0 + i, best_lay=lay),
                 params=params, proposte=proposte, mode="live")
    finally:
        X.place = orig

    assert proposte.count("under_green") == 3, (
        "tre prezzi diversi = tre domande diverse: tutte e tre si fanno")


# ===========================================================================
# 4. IL RIFIUTO SOPRAVVIVE AL RIAVVIO (difetto 19 del catalogo)
# ===========================================================================
def test_il_rifiuto_sopravvive_al_riavvio():
    """`pre_ko` viveva solo in RAM e al riavvio base e punta restavano spente per
    ore. Un freno che vive solo in RAM ricomincerebbe a riproporre a ogni
    riavvio del servizio: va nella riga di `mike_events`."""
    ctx = E.MatchCtx(state="REENTRY_OPEN", cycle_no=0)
    gamba = E.Leg(role="reentry_green", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                  side="lay", price=1.75, size=10.11, ref="reentry_green-0-2",
                  status="cancelled")
    E.registra_rifiuto(ctx, gamba, "prezzo non disponibile (1.8)")

    riga = S._row_from_ctx({"event_id": EVENTO}, ctx, {})
    assert "rifiuti" in (riga.get("ctx") or {}), "il rifiuto non viene salvato"
    riletto = S._ctx_from_row({**riga, "state": ctx.state, "cycle_no": 0})
    identica = E._place("reentry_green", E.MARKET_OU45, E.SEL_UNDER, "lay", 1.75, 10.11)
    assert E.tentativo_gia_rifiutato(riletto, identica) is not None, (
        "dopo il riavvio il motore ha dimenticato il rifiuto e ricomincia")


def test_un_ciclo_archiviato_spurga_i_suoi_rifiuti():
    """La memoria non deve crescere: la riga di `mike_events` e' gia' arrivata a
    60 KB una volta, e da li' e' venuto lo statement timeout del 13/09."""
    ctx = E.MatchCtx(state="PRE_OPEN", cycle_no=0)
    gamba = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                  side="lay", price=1.58, size=10.13, ref="under_green-0-2",
                  status="cancelled")
    E.registra_rifiuto(ctx, gamba, "prezzo non disponibile (1.6)")
    assert ctx.rifiuti

    E.apply_decision(ctx, E.Decision("WATCH", [], "ciclo chiuso",
                                     updates={"cycle_no": 1, "_archive_legs": True}), 2000.0)
    assert ctx.rifiuti == {}, "i rifiuti del ciclo chiuso restano attaccati"
