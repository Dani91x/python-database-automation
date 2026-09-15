"""IL LOOP DELLE CHIUSURE — 60 righe `under_close` in pochi minuti (15/09, sera).

Trinec v Mlada Boleslav, Mike in live. Il monitor mostrava sette ordini veri
identici da 0,20 € e un capitale impegnato che saliva. Su Betfair, in realta',
**non era arrivato niente**: sessanta righe `pending` nel database e zero
ordini a mercato. L'opposto esatto del loop del mattino, stessa radice.

LA RADICE, per la quinta volta in un giorno: **un dato scritto in un posto e
letto in un altro.**

`execution.place` riconosce una gamba di chiusura cosi':

    is_closing = bool(meta.get("cashout") or meta.get("closes_trade_id"))

Mike scriveva `closes_trade_id` nella COLONNA della riga e passava a `X.place`
il solo `row["meta"]`, che quella chiave non l'ha mai contenuta. Per chi
eseguiva, **nessuna chiusura di Mike era una chiusura.** Due conseguenze:

  1. `sotto_minimo = ... and not is_closing` restava vero → una chiusura da
     0,20 € finiva nel **place-and-trim** invece di essere piazzata diretta. Il
     parcheggio della lay (il minimo a 1,01) su una selezione dove abbiamo gia'
     un back RIDUCE la liability, e Betfair lo misura con la banda del
     profit-ratio (`live_order_build.INVALID_PROFIT_RATIO_MIN/MAX`, −20%/+25%):
     **rifiutato**. Ogni singolo giro.
  2. `blocco = None if is_closing else _live_brake()` — il freno live si
     applicava anche alle USCITE. Col freno attivo una posizione aperta non si
     sarebbe potuta chiudere: l'opposto della protezione, e `execution.place`
     lo scrive a chiare lettere nel suo commento.

E IL MOLTIPLICATORE: il freno anti-duplicato del mattino stava solo sulla lay
appoggiata. Le gambe di chiusura passano da `execute_place`, dove non c'era
niente: ogni giro la riga restava 'pending' e il motore ne creava una nuova col
`seq` successivo — `under_close-0-4`, `-5`, … fino a `-62`.

Safe e Omega mettono `closes_trade_id` NEL META da sempre
(`execution.close_position`). Mike era l'unico fuori riga.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.safe_strategy import execution as X


# ---------------------------------------------------------------------------
# doppi
# ---------------------------------------------------------------------------
class DbFinto:
    def __init__(self, righe: Optional[List[dict]] = None) -> None:
        self.righe = list(righe or [])
        self.log_righe: List[tuple] = []
        self._id = 4820

    def trades_for_event(self, _event_id, **_kw) -> List[dict]:
        return list(self.righe)

    def insert_trade(self, row, **_kw) -> int:
        self._id += 1
        self.righe.append({**row, "id": self._id})
        return self._id

    def update_trade(self, trade_id, **campi) -> None:
        for r in self.righe:
            if r.get("id") == trade_id:
                r.update(campi)

    def log(self, kind, payload=None, event_id=None) -> None:
        self.log_righe.append((kind, payload or {}))

    def kinds(self) -> List[str]:
        return [k for k, _ in self.log_righe]


class InfoFinta:
    event_id = "36066505"
    event_name = "Trinec v Mlada Boleslav"
    competition = None
    ko_at = 0.0

    def market_id(self, _m: str) -> str:
        return "1.262441713"

    def selection_id(self, _m: str, _s: str) -> int:
        return 1222344

    def selection_name(self, _m: str, _s: str) -> str:
        return "Under 3.5 Goals"


def gamba(**kw: Any) -> E.Leg:
    """La gamba del loop: `under_close`, lay, 0,20 € — sotto il minimo .it."""
    base = dict(ref="under_close-0-38", role="under_close", market=E.MARKET_OU35,
                selection=E.SEL_UNDER, side="lay", price=1.90, size=0.20,
                status="pending")
    base.update(kw)
    return E.Leg(**base)


def book_aperto() -> E.Book:
    return E.Book(status="OPEN", best_back=1.92, back_size=50.0,
                  best_lay=1.90, lay_size=50.0)


def riga_in_volo(**kw: Any) -> Dict[str, Any]:
    base = {"id": 4884, "role": "under_close", "cycle_no": 0, "side": "lay",
            "status": "pending", "signal_key": "under_close-0-61",
            "closes_trade_id": 4821, "meta": {"leg_ref": "under_close-0-61"}}
    base.update(kw)
    return base


def piazza(db, market, leg, *, closes=4821, mode="live"):
    return S.execute_place(db=db, market=market, info=InfoFinta(), leg=leg,
                           book=book_aperto(), mode=mode, params=C.merge_params(None),
                           now=1000.0, dry=False, minute=70, score="1-1",
                           closes_trade_id=closes, close_reason="profit")


# ===========================================================================
# 1. «QUESTA GAMBA CHIUDE» ARRIVA A CHI ESEGUE
# ===========================================================================
def test_la_chiusura_si_dichiara_a_chi_esegue():
    """LA RADICE. Senza questa chiave chi esegue non sa che e' una chiusura, e
    da li' scendono il place-and-trim sbagliato e il freno applicato a
    un'uscita."""
    visto: Dict[str, Any] = {}

    def finto_place(**kw):
        visto.update(kw)
        return X.PlaceOutcome("open", 1.90, 0.20, "B1", "live_rest:EXECUTION_COMPLETE")

    db = DbFinto()
    leg = gamba()
    orig, X.place = X.place, finto_place
    S.X = X
    try:
        piazza(db, SimpleNamespace(), leg)
    finally:
        X.place = orig

    meta = visto.get("meta") or {}
    assert meta.get("closes_trade_id") == 4821, (
        "chi esegue non sa che questa gamba CHIUDE: finira' nel place-and-trim "
        "e prendera' il freno delle aperture")
    assert bool(meta.get("cashout") or meta.get("closes_trade_id")), (
        "e' la formula esatta con cui `execution.place` calcola `is_closing`")


def test_una_APERTURA_non_si_dichiara_chiusura():
    """Il contrario deve restare vero, o un'apertura scavalcherebbe il freno
    live e il minimo di giurisdizione."""
    visto: Dict[str, Any] = {}

    def finto_place(**kw):
        visto.update(kw)
        return X.PlaceOutcome("open", 1.90, 5.0, "B1", "live_rest:EXECUTION_COMPLETE")

    db = DbFinto()
    leg = gamba(role="under_entry", ref="under_entry-0-1", size=5.0)
    orig, X.place = X.place, finto_place
    S.X = X
    try:
        piazza(db, SimpleNamespace(), leg, closes=None)
    finally:
        X.place = orig

    meta = visto.get("meta") or {}
    assert not meta.get("closes_trade_id"), "un'apertura non chiude niente"


def test_una_chiusura_SENZA_numero_di_riga_resta_una_chiusura():
    """La colonna puo' mancare (migrazione non applicata). Il RUOLO lo sappiamo
    sempre: una gamba di chiusura e' una chiusura anche senza riferimento."""
    visto: Dict[str, Any] = {}

    def finto_place(**kw):
        visto.update(kw)
        return X.PlaceOutcome("open", 1.90, 0.20, "B1", "live_rest:EXECUTION_COMPLETE")

    db = DbFinto()
    orig, X.place = X.place, finto_place
    S.X = X
    try:
        piazza(db, SimpleNamespace(), gamba(), closes=None)
    finally:
        X.place = orig

    assert bool((visto.get("meta") or {}).get("closes_trade_id")), (
        "senza colonna la chiusura veniva trattata come un'apertura")


def test_execution_riconosce_davvero_il_meta_che_mike_manda():
    """Il contratto, contro la funzione VERA: se `execution.place` cambiasse il
    modo di riconoscere una chiusura, questo test lo direbbe qui."""
    import inspect
    src = inspect.getsource(X.place)
    assert 'meta.get("closes_trade_id")' in src, (
        "`execution.place` non riconosce piu' le chiusure da `meta.closes_trade_id`: "
        "Mike gliela manda li'")
    assert "not is_closing" in src, (
        "`sotto_minimo` non esclude piu' le chiusure: una chiusura sotto il minimo "
        "tornerebbe nel place-and-trim, che Betfair rifiuta (INVALID_PROFIT_RATIO)")


# ===========================================================================
# 2. IL FRENO SULLE GAMBE DI CHIUSURA — il moltiplicatore
# ===========================================================================
def test_NON_si_piazza_una_seconda_gamba_di_chiusura():
    """Il caso del 15/09 sera, riprodotto: con una gia' 'pending', nessun altro
    ordine parte. E' il freno del mattino, portato dove mancava."""
    piazzati: List[dict] = []

    def finto_place(**kw):
        piazzati.append(kw)
        return X.PlaceOutcome("open", 1.90, 0.20, "B1", "live_rest:EXECUTION_COMPLETE")

    db = DbFinto([riga_in_volo()])
    leg = gamba(ref="under_close-0-62")
    orig, X.place = X.place, finto_place
    S.X = X
    try:
        esito = piazza(db, SimpleNamespace(), leg)
    finally:
        X.place = orig

    assert piazzati == [], "ha piazzato una seconda chiusura identica"
    assert esito == "cancelled" and leg.status == "cancelled"
    assert "place_saltato" in db.kinds()


def test_il_freno_DICHIARA_quale_riga_era_gia_in_volo():
    db = DbFinto([riga_in_volo(rid=4884)])
    orig, X.place = X.place, lambda **kw: X.PlaceOutcome("error", None, 0.0, None, "x")
    S.X = X
    try:
        piazza(db, SimpleNamespace(), gamba(ref="under_close-0-62"))
    finally:
        X.place = orig
    _k, p = next((k, p) for k, p in db.log_righe if k == "place_saltato")
    assert p.get("gia_in_volo") == 4884 and p.get("critical") is True


def test_il_freno_NON_tocca_la_copertura_a_tranche():
    """`over_cover` entra in DUE tranche: stesso ruolo, stesso ciclo, stesso
    lato. Frenarla spegnerebbe la seconda meta' della copertura — cioe'
    altererebbe la strategia, che e' l'unica cosa che non si fa mai."""
    piazzati: List[dict] = []

    def finto_place(**kw):
        piazzati.append(kw)
        return X.PlaceOutcome("open", 2.0, 1.0, "B1", "live_rest:EXECUTION_COMPLETE")

    db = DbFinto([riga_in_volo(role="over_cover", signal_key="over_cover-0-1")])
    # prezzo dentro il best del book finto (back a 1,92): qui si misura il
    # freno, non la regola del prezzo taker.
    leg = gamba(role="over_cover", ref="over_cover-0-2", market=E.MARKET_OU45,
                selection=E.SEL_OVER, side="back", size=1.0, price=1.90)
    orig, X.place = X.place, finto_place
    S.X = X
    try:
        piazza(db, SimpleNamespace(), leg, closes=None)
    finally:
        X.place = orig

    assert len(piazzati) == 1, "la seconda tranche di copertura e' stata frenata"


def test_una_riga_gia_CHIUSA_non_frena_il_ciclo_dopo():
    """Il freno guarda solo le righe 'pending': una chiusura gia' abbinata o
    gia' annullata non deve impedire la chiusura del ciclo successivo."""
    for stato in ("open", "cancelled", "error", "void", "won", "lost"):
        piazzati: List[dict] = []

        def finto_place(**kw):
            piazzati.append(kw)
            return X.PlaceOutcome("open", 1.90, 0.20, "B1", "live_rest:x")

        db = DbFinto([riga_in_volo(status=stato)])
        orig, X.place = X.place, finto_place
        S.X = X
        try:
            piazza(db, SimpleNamespace(), gamba(ref="under_close-0-62"))
        finally:
            X.place = orig
        assert len(piazzati) == 1, f"stato '{stato}' ha frenato una chiusura legittima"


def test_righe_illeggibili_NON_si_piazza():
    """FAIL-CLOSED, come il freno del mattino: se non si riesce a leggere le
    righe non sappiamo se ce n'e' gia' una in volo, e nel dubbio non parte
    nessun ordine reale."""
    class DbRotto(DbFinto):
        def trades_for_event(self, _event_id, **_kw):
            raise RuntimeError("503 dal database")

    piazzati: List[dict] = []
    orig, X.place = X.place, lambda **kw: piazzati.append(kw)
    S.X = X
    try:
        esito = piazza(DbRotto(), SimpleNamespace(), gamba())
    finally:
        X.place = orig

    assert piazzati == [], "ha piazzato un ordine reale senza poter leggere le righe"
    assert esito == "cancelled"
