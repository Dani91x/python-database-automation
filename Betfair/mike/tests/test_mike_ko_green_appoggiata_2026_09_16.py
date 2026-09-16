"""L'USCITA AL FISCHIO E' UNA LAY APPOGGIATA (ordine dell'utente, 16/09/2026).

«Mettiamola appoggiata allora, cosi' risparmiamo una marea di chiamate;
attenzione pero': quella gamba, se il mercato si sospende per qualsiasi motivo,
Betfair cancella quell'ordine; il bot deve saperlo e appena riapre il mercato
verificare cosa e' successo (gol estremamente precoci).»

Modifica di STRATEGIA ordinata dall'utente, l'unica ammessa. Qui si difendono
quattro cose, e servono tutte e quattro:

  1. `ko_green` e' appoggiata in OGNI modalita' (`pre_exit_mode` non la governa
     piu') e NON si ri-presenta piu' a ritmo: `ko_green_retry_s` non ha effetto;
  2. si appoggia SOLO a mercato aperto E in gioco — al fischio Betfair sospende
     e fa scadere (LAPSE) gli ordini non abbinati;
  3. a ogni riapertura dopo una sospensione l'ordine si RILEGGE da Betfair, e le
     quattro reazioni (vivo / scaduto / abbinato / abbinato in parte) sono tutte
     dichiarate; l'esito ignoto va in riconciliazione, mai una gamba nuova;
  4. la finestra `ko_green_window_s` non scorre mentre non si puo' appoggiare.

I finti parlano con le chiavi del vero: `PlaceResult` e' quello di
`omega_market`, gli ordini hanno le chiavi in snake_case che
`omega_market.list_current_orders` produce (`size_matched`, `size_remaining`,
`size_lapsed`, `size_cancelled`, `customer_order_ref`), `Book`/`Snapshot`/`Leg`
sono quelli dell'engine.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from Betfair.mike import certificazione as CERT
from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.omega.omega_market import PlaceResult


KO = 1_700_000_000.0


# ---------------------------------------------------------------------------
# i finti, con le chiavi del vero
# ---------------------------------------------------------------------------
def ordine_betfair(*, bet_id: str = "B1", ref: str = "mike-t1", stato: str = "EXECUTABLE",
                   abbinato: float = 0.0, residuo: float = 10.14,
                   scaduto: float = 0.0, annullato: float = 0.0,
                   prezzo_medio: Optional[float] = None) -> Dict[str, Any]:
    """UN ordine come lo restituisce `omega_market.list_current_orders`: chiavi
    in snake_case, MAI camelCase (il 15/09 la grafia sbagliata e' costata 32
    ordini veri in loop)."""
    return {
        "bet_id": bet_id, "market_id": "1.234", "selection_id": 47999, "side": "lay",
        "status": stato, "size_matched": abbinato, "avg_price_matched": prezzo_medio,
        "size_remaining": residuo, "customer_order_ref": ref,
        "size_cancelled": annullato, "size_lapsed": scaduto, "size_voided": 0.0,
        "matched_date": "2026-09-16T13:00:00Z", "placed_date": "2026-09-16T12:59:00Z",
        "price_requested": 1.48, "size_requested": 10.14,
        "average_price_matched": prezzo_medio,
    }


class MercatoFinto:
    """Il mercato risponde come `omega_market`: liste normalizzate in snake_case
    e `order_state_by_bet_id` con la forma vera (`found` + i numeri)."""

    def __init__(self, *, correnti: Optional[List[dict]] = None,
                 per_bet_id: Optional[Dict[str, dict]] = None,
                 esplode_correnti: bool = False) -> None:
        self.correnti = list(correnti or [])
        self.per_bet_id = dict(per_bet_id or {})
        self.esplode_correnti = esplode_correnti
        self.piazzati: List[dict] = []
        self.letture: List[str] = []

    def place_order_live(self, **kw: Any) -> PlaceResult:
        self.piazzati.append(dict(kw))
        return PlaceResult(ok=True, order_status="EXECUTABLE", bet_id="B1",
                           size_matched=0.0, avg_price_matched=None, raw={})

    def list_current_orders(self) -> List[dict]:
        if self.esplode_correnti:
            raise RuntimeError("rete giu'")
        self.letture.append("correnti")
        return list(self.correnti)

    def order_state_by_bet_id(self, bet_id: str) -> dict:
        self.letture.append(f"bet:{bet_id}")
        return dict(self.per_bet_id.get(str(bet_id)) or {"found": False})


class DbFinto:
    def __init__(self) -> None:
        self.righe: List[dict] = []
        self.log_scritti: List[tuple] = []
        self.aggiornate: List[dict] = []

    def trades_for_event(self, event_id: str, **_kw) -> List[dict]:
        return list(self.righe)

    def log(self, kind: str, payload: dict, event_id: Optional[str] = None) -> None:
        self.log_scritti.append((kind, dict(payload)))

    def kinds(self) -> List[str]:
        return [k for k, _ in self.log_scritti]

    def payload(self, kind: str) -> Dict[str, Any]:
        for k, p in self.log_scritti:
            if k == kind:
                return p
        raise AssertionError(f"nessuna attivita' '{kind}' fra {self.kinds()}")

    def insert_trade(self, row: dict) -> int:
        r = dict(row, id=len(self.righe) + 1)
        self.righe.append(r)
        return int(r["id"])

    def update_trade(self, tid: int, **kw: Any) -> None:
        self.aggiornate.append(dict(kw, id=tid))


@pytest.fixture(autouse=True)
def _riga_finta(monkeypatch):
    """La riga di `mike_trades` della gamba, con il `bet_id` che Betfair ci ha
    dato: e' con quello che si rilegge l'ordine."""
    monkeypatch.setattr(
        S, "_trade_row_for_leg",
        lambda db, eid, leg, cache=None: {
            "id": 1, "meta": {}, "status": "pending", "bet_id": "B1", "mode": "live",
            "signal_key": leg.ref, "market_id": "1.234", "selection_id": 47999})


def gamba_uscita(**kw: Any) -> E.Leg:
    base = dict(role="ko_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                price=1.48, size=10.14, ref="ko_green-0-3", status="pending",
                placed_at=KO + 1.0)
    base.update(kw)
    return E.Leg(**base)


def book(bb: Optional[float] = 1.50, *, status: str = "OPEN", inplay: bool = True) -> E.Book:
    return E.Book(best_back=bb, back_size=200.0, best_lay=(bb or 1.5) + 0.02, lay_size=200.0,
                  status=status, inplay=inplay)


def snap(now: float, *, u35: Optional[E.Book] = None, o45: Optional[E.Book] = None,
         goals: int = 0, minute: int = 1) -> E.Snapshot:
    books = {(E.MARKET_OU35, E.SEL_UNDER): u35 if u35 is not None else book()}
    books[(E.MARKET_OU45, E.SEL_OVER)] = o45 if o45 is not None else book(8.0)
    return E.Snapshot(now=now, ko_at=KO, books=books, inplay=True, minute=minute,
                      goals=goals, feed_fresh=True, order_fresh=True)


def ctx_in_uscita(*, gambe: Optional[List[E.Leg]] = None, live_since: float = KO) -> E.MatchCtx:
    """Posizione Under 3.5 abbinata pre-match e partita gia' in gioco."""
    ingresso = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                     side="back", price=1.50, size=10.0, matched=10.0, avg_price=1.50,
                     ref="under_entry-0-1", status="open", placed_at=KO - 600)
    ctx = E.MatchCtx(state="LIVE_KO_GREEN", legs=[ingresso] + list(gambe or []),
                     live_since=live_since, ko_goals=0)
    return ctx


PAR = C.merge_params({"ko_green_retry_s": 60})


# ===========================================================================
# 1. APPOGGIATA IN OGNI MODALITA' (falsificazione: rimetti il taker)
# ===========================================================================
def test_ko_green_e_appoggiata_in_taker_E_in_resting():
    """FALSIFICA la vecchia regola: con `pre_exit_mode='taker'` l'uscita al
    fischio era un ordine a mercato ri-presentato a ritmo. Adesso e' appoggiata
    in ogni modalita' — se qualcuno rimette il vincolo, questo test e' rosso."""
    leg = gamba_uscita()
    for modo in ("taker", "resting"):
        assert S._is_resting_leg(leg, C.merge_params({"pre_exit_mode": modo})) is True, modo


def test_gli_altri_green_restano_governati_dal_parametro():
    """Non e' un cambio generale: `under_green` e `reentry_green` non si toccano."""
    for ruolo in ("under_green", "reentry_green"):
        leg = gamba_uscita(role=ruolo, ref=f"{ruolo}-0-2")
        assert S._is_resting_leg(leg, C.merge_params({"pre_exit_mode": "resting"})) is True
        assert S._is_resting_leg(leg, C.merge_params({"pre_exit_mode": "taker"})) is False


def test_in_live_con_la_valvola_spenta_ko_green_resta_appoggiata():
    """`live_resting_enabled=False` riporta al taker `under_green`, MAI l'uscita
    al fischio: quella e' appoggiata per ordine dell'utente."""
    p = S._params_for(C.merge_params({"pre_exit_mode": "resting",
                                      "live_resting_enabled": False}), True, "live")
    assert p["pre_exit_mode"] == "taker"
    assert S._is_resting_leg(gamba_uscita(), p) is True
    assert S._is_resting_leg(gamba_uscita(role="under_green", ref="under_green-0-2"), p) is False


# ===========================================================================
# 2. IL RITMO NON ESISTE PIU'
# ===========================================================================
def test_ko_green_retry_s_non_ha_piu_effetto():
    """FALSIFICA la ri-presentazione: la gamba precedente e' morta UN SECONDO fa
    e `ko_green_retry_s` vale 60. Con il vecchio ramo il motore avrebbe detto
    «ritento fra poco»; adesso appoggia SUBITO una gamba nuova."""
    morta = gamba_uscita(status="cancelled", matched=0.0, placed_at=KO + 10.0)
    ctx = ctx_in_uscita(gambe=[morta])
    d = E.decide(ctx, snap(KO + 11.0), PAR)
    posati = [a for a in d.actions if a.kind == "place" and a.role == "ko_green"]
    assert len(posati) == 1, d.reason
    assert posati[0].side == "lay"
    assert d.state == "LIVE_KO_GREEN"


def test_la_certificazione_non_dichiara_piu_nessun_ritmo():
    """P1/P3: la ri-presentazione di `ko_green` non e' piu' una regola prevista.
    Se ricompare e' una violazione, e il verdetto deve dirlo."""
    assert "ko_green" not in CERT.RITMI_DICHIARATI


def test_con_una_uscita_a_esito_IGNOTO_non_si_appoggia_niente():
    """J2/J4 — il reperto del banco su 35674515: «nuova ko_green mentre
    ko_green-0-3 e' a esito IGNOTO». Una gamba `pending_reconcile` puo' essere
    viva su Betfair: finche' non si sa, non se ne appoggia un'altra."""
    ignota = gamba_uscita(status=E.STATUS_RECONCILE, matched=0.0)
    ctx = ctx_in_uscita(gambe=[ignota])
    d = E.decide(ctx, snap(KO + 60.0), PAR)
    assert [a for a in d.actions if a.kind == "place"] == []
    assert [a for a in d.actions if a.kind == "cancel"] == []
    assert d.state == "LIVE_KO_GREEN"
    assert "ignoto" in d.reason


def test_una_uscita_viva_non_si_ripropone():
    """L'ordine e' sul book allo stesso prezzo e alla stessa size: non si tocca."""
    viva = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[viva])
    d = E.decide(ctx, snap(KO + 30.0), PAR)
    assert [a for a in d.actions if a.kind == "place"] == []


# ===========================================================================
# 3. SOLO A MERCATO APERTO E IN GIOCO
# ===========================================================================
def test_non_si_appoggia_a_mercato_sospeso():
    ctx = ctx_in_uscita()
    d = E.decide(ctx, snap(KO + 5.0, u35=book(1.50, status="SUSPENDED")), PAR)
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.state == "LIVE_KO_GREEN"
    assert "riapertura" in d.reason


def test_non_si_appoggia_a_mercato_aperto_ma_non_in_gioco():
    """Al fischio Betfair sospende per il passaggio in gioco e fa scadere gli
    ordini non abbinati: appoggiare prima dell'in-play significa vederla morire
    nello stesso istante."""
    ctx = ctx_in_uscita()
    d = E.decide(ctx, snap(KO + 5.0, u35=book(1.50, inplay=False)), PAR)
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.state == "LIVE_KO_GREEN"
    assert "in gioco" in d.reason


def test_a_mercato_chiuso_si_passa_alla_copertura():
    ctx = ctx_in_uscita()
    d = E.decide(ctx, snap(KO + 5.0, u35=book(1.50, status="CLOSED")), PAR)
    assert d.state == "LIVE_UNCOVERED"


# ===========================================================================
# 4. LA FINESTRA NON SCORRE SE NON SI PUO' APPOGGIARE
# ===========================================================================
def test_la_finestra_non_scorre_a_mercato_sospeso():
    ctx = ctx_in_uscita()
    oltre = KO + float(PAR["ko_green_window_s"]) + 60.0
    assert E.finestra_uscita_scaduta(
        ctx, snap(oltre, u35=book(1.50, status="SUSPENDED")), PAR) is False
    assert E.finestra_uscita_scaduta(ctx, snap(oltre), PAR) is True


def test_la_finestra_non_scorre_a_mercato_non_in_gioco():
    ctx = ctx_in_uscita()
    oltre = KO + float(PAR["ko_green_window_s"]) + 60.0
    assert E.finestra_uscita_scaduta(
        ctx, snap(oltre, u35=book(1.50, inplay=False)), PAR) is False


# ===========================================================================
# 5. LA CONSAPEVOLEZZA ALLA RIAPERTURA — le quattro reazioni
# ===========================================================================
def _sospendi_e_riapri(*, mercato: MercatoFinto, ctx: E.MatchCtx,
                       ora: float = KO + 120.0) -> DbFinto:
    """Il mercato sospende (con la lay appoggiata viva) e poi riapre."""
    db = DbFinto()
    ev = {"event_id": "E1"}
    S._sorveglia_sospensione(db=db, market=mercato, ctx=ctx,
                             snap=snap(ora, u35=book(1.50, status="SUSPENDED")),
                             params=PAR, mode="live", now_ts=ora, ev=ev)
    S._sorveglia_sospensione(db=db, market=mercato, ctx=ctx, snap=snap(ora + 5.0),
                             params=PAR, mode="live", now_ts=ora + 5.0, ev=ev)
    return db


def test_la_sospensione_con_una_gamba_viva_si_annota_nel_ctx():
    ctx = ctx_in_uscita(gambe=[gamba_uscita()])
    db = DbFinto()
    S._sorveglia_sospensione(db=db, market=MercatoFinto(), ctx=ctx,
                             snap=snap(KO + 100.0, u35=book(1.50, status="SUSPENDED")),
                             params=PAR, mode="live", now_ts=KO + 100.0,
                             ev={"event_id": "E1"})
    assert ctx.riapertura is not None
    assert ctx.riapertura["refs"] == ["ko_green-0-3"]
    assert ctx.riapertura["letto"] is False
    assert "mercato_sospeso" in db.kinds()


def test_a_riapertura_con_ordine_VIVO_nessuna_gamba_nuova():
    """(a) — l'ordine e' ancora sul book: resta, e il motore non ne crea un altro."""
    leg = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[leg])
    mk = MercatoFinto(correnti=[ordine_betfair(residuo=10.14)])
    db = _sospendi_e_riapri(mercato=mk, ctx=ctx)
    assert ctx.riapertura["letto"] is True
    assert ctx.riapertura["esiti"]["ko_green-0-3"] == "vivo"
    assert leg.is_live and leg.matched == 0.0
    assert "ordine_scaduto_alla_sospensione" not in db.kinds()
    d = E.decide(ctx, snap(KO + 130.0), PAR)
    assert [a for a in d.actions if a.kind == "place"] == []


def test_a_riapertura_con_ordine_SCADUTO_attivita_e_ri_appoggio():
    """(b) — Betfair l'ha fatto scadere: si dichiara con i numeri, la gamba si
    chiude COME TALE e il motore ne appoggia UNA nuova (finestra aperta)."""
    leg = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[leg])
    mk = MercatoFinto(per_bet_id={"B1": {"found": True, "size_matched": 0.0,
                                         "avg_price_matched": None, "size_remaining": 0.0,
                                         "matched_date": None,
                                         "placed_date": "2026-09-16T12:59:00Z"}})
    db = _sospendi_e_riapri(mercato=mk, ctx=ctx)
    p = db.payload("ordine_scaduto_alla_sospensione")
    assert p["leg"] == "ko_green-0-3" and p["role"] == "ko_green"
    assert p["size_requested"] == 10.14 and p["size_matched"] == 0.0
    assert p["critical"] is True
    # la gamba e' chiusa come scaduta: non e' viva, non ha abbinato, e la riga
    # porta il motivo per esteso (nessuna migrazione: lo status resta 'error')
    assert leg.status == "cancelled" and leg.matched == 0.0
    assert db.aggiornate and db.aggiornate[-1]["meta"]["reason"] == "lapsed_alla_sospensione"
    # ...e il motore ri-appoggia UNA gamba sola
    d = E.decide(ctx, snap(KO + 130.0), PAR)
    posati = [a for a in d.actions if a.kind == "place" and a.role == "ko_green"]
    assert len(posati) == 1


def test_a_riapertura_con_ordine_SCADUTO_e_finestra_chiusa_si_copre():
    """(b) con la finestra gia' scaduta: il piano successivo e' la copertura."""
    leg = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[leg])
    mk = MercatoFinto(per_bet_id={"B1": {"found": True, "size_matched": 0.0,
                                         "avg_price_matched": None, "size_remaining": 0.0}})
    oltre = KO + float(PAR["ko_green_window_s"]) + 30.0
    _sospendi_e_riapri(mercato=mk, ctx=ctx, ora=oltre)
    assert leg.status == "cancelled"
    d = E.decide(ctx, snap(oltre + 10.0), PAR)
    assert d.state == "LIVE_UNCOVERED"
    assert [a for a in d.actions if a.kind == "place" and a.role == "ko_green"] == []


def test_a_riapertura_con_ordine_ABBINATO_e_una_posizione():
    """(c) — si e' abbinato durante la sospensione: e' una posizione vera, col
    prezzo medio di Betfair, e il ciclo prosegue."""
    leg = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[leg])
    mk = MercatoFinto(per_bet_id={"B1": {"found": True, "size_matched": 10.14,
                                         "avg_price_matched": 1.47, "size_remaining": 0.0,
                                         "matched_date": "2026-09-16T13:00:01Z"}})
    db = _sospendi_e_riapri(mercato=mk, ctx=ctx)
    assert leg.status == "open" and leg.matched == 10.14 and leg.avg_price == 1.47
    assert "ordine_scaduto_alla_sospensione" not in db.kinds()
    assert db.payload("rilettura_alla_riapertura")["esito"] == "abbinato"


def test_a_riapertura_con_ordine_ABBINATO_IN_PARTE():
    """(d) — la parte abbinata e' posizione; il residuo e' scaduto e si dichiara
    con i suoi numeri, come in (b) ma per la sola parte residua."""
    leg = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[leg])
    mk = MercatoFinto(correnti=[ordine_betfair(stato="EXECUTION_COMPLETE", abbinato=4.0,
                                               residuo=0.0, scaduto=6.14,
                                               prezzo_medio=1.47)])
    db = _sospendi_e_riapri(mercato=mk, ctx=ctx)
    p = db.payload("ordine_scaduto_alla_sospensione")
    assert p["esito"] == "parziale"
    assert p["size_matched"] == 4.0 and p["size_lapsed"] == 6.14
    assert leg.matched == 4.0 and leg.avg_price == 1.47 and leg.status == "open"
    assert db.aggiornate[-1]["size"] == 4.0


def test_a_riapertura_con_esito_IGNOTO_si_riconcilia():
    """Betfair non sa dire che fine ha fatto: `pending_reconcile`, MAI una gamba
    nuova su un dubbio (§4.11)."""
    leg = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[leg])
    mk = MercatoFinto(per_bet_id={"B1": {"found": False}})
    db = _sospendi_e_riapri(mercato=mk, ctx=ctx)
    assert leg.status == E.STATUS_RECONCILE
    assert "reconcile_pending" in db.kinds()
    assert ctx.riapertura["esiti"]["ko_green-0-3"] == "ignoto"


def test_se_betfair_non_risponde_la_rilettura_NON_e_avvenuta():
    """MAI dare per vivo un ordine senza rilettura: se la rete cade si riprova
    al giro dopo e `letto` resta False."""
    leg = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[leg])
    mk = MercatoFinto(esplode_correnti=True)
    _sospendi_e_riapri(mercato=mk, ctx=ctx)
    assert ctx.riapertura["letto"] is False
    assert leg.is_live


def test_in_paper_non_si_chiede_niente_a_betfair():
    """In paper nessun ordine reale esiste: la simulazione lo tiene sul book, e
    lo si DICHIARA invece di fingere una lettura."""
    leg = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[leg])
    mk = MercatoFinto()
    db = DbFinto()
    ev = {"event_id": "E1"}
    S._sorveglia_sospensione(db=db, market=mk, ctx=ctx,
                             snap=snap(KO + 100.0, u35=book(1.50, status="SUSPENDED")),
                             params=PAR, mode="paper", now_ts=KO + 100.0, ev=ev)
    S._sorveglia_sospensione(db=db, market=mk, ctx=ctx, snap=snap(KO + 105.0),
                             params=PAR, mode="paper", now_ts=KO + 105.0, ev=ev)
    assert mk.letture == []
    assert ctx.riapertura["esiti"]["ko_green-0-3"] == "paper"


# ===========================================================================
# 6. IL CONTROLLO R1 DELLA CERTIFICAZIONE (falsificazione: togli la rilettura)
# ===========================================================================
def _viola(ctx: E.MatchCtx, s: E.Snapshot) -> List[str]:
    d = E.Decision(state=ctx.state, actions=[], reason="")
    return [v.codice for v in CERT.verifica(ctx, s, d, PAR)]


def test_R1_e_rosso_se_alla_riapertura_nessuno_ha_riletto():
    """FALSIFICAZIONE: e' lo stato in cui si trova il bot se si toglie la
    rilettura — mercato riaperto, gamba data per viva, nessuno ha chiesto."""
    ctx = ctx_in_uscita(gambe=[gamba_uscita()])
    ctx.riapertura = {"ts": KO + 100.0, "refs": ["ko_green-0-3"], "letto": False, "esiti": {}}
    assert "R1" in _viola(ctx, snap(KO + 130.0))


def test_R1_e_verde_dopo_la_rilettura():
    ctx = ctx_in_uscita(gambe=[gamba_uscita()])
    ctx.riapertura = {"ts": KO + 100.0, "refs": ["ko_green-0-3"], "letto": True,
                      "letto_ts": KO + 105.0, "esiti": {"ko_green-0-3": "vivo"}}
    assert "R1" not in _viola(ctx, snap(KO + 130.0))


def test_R1_non_accusa_mentre_il_mercato_e_ancora_sospeso():
    ctx = ctx_in_uscita(gambe=[gamba_uscita()])
    ctx.riapertura = {"ts": KO + 100.0, "refs": ["ko_green-0-3"], "letto": False, "esiti": {}}
    assert "R1" not in _viola(ctx, snap(KO + 110.0, u35=book(1.50, status="SUSPENDED")))


def test_R1_e_sollecitato_solo_quando_c_e_stata_una_sospensione():
    """`quando=`: un controllo che non ha mai avuto un caso non e' una garanzia.
    Senza sospensione R1 non deve nemmeno essere contato."""
    ctx = ctx_in_uscita(gambe=[gamba_uscita()])
    sollecitati: Dict[str, int] = {}
    CERT.verifica(ctx, snap(KO + 30.0), E.Decision(state=ctx.state, actions=[], reason=""),
                  PAR, sollecitati=sollecitati)
    assert "R1" not in sollecitati
    ctx.riapertura = {"ts": KO + 100.0, "refs": ["ko_green-0-3"], "letto": True, "esiti": {}}
    CERT.verifica(ctx, snap(KO + 130.0), E.Decision(state=ctx.state, actions=[], reason=""),
                  PAR, sollecitati=sollecitati)
    assert sollecitati.get("R1") == 1


# ===========================================================================
# 7. LA MEMORIA SOPRAVVIVE AL RIAVVIO
# ===========================================================================
def test_la_riapertura_e_persistita_nello_stato_della_partita():
    """Un riavvio in mezzo alla sospensione non deve far dimenticare che c'e'
    una rilettura da fare."""
    assert "riapertura" in S._CTX_FIELDS
    ctx = ctx_in_uscita(gambe=[gamba_uscita()])
    ctx.riapertura = {"ts": KO, "refs": ["ko_green-0-3"], "letto": False, "esiti": {}}
    riga = S._row_from_ctx({"event_id": "E1", "ctx": {}}, ctx, {})
    assert riga["ctx"]["riapertura"]["refs"] == ["ko_green-0-3"]


# ===========================================================================
# 8. MAI DUE LAY A MERCATO (ordine dell'utente, 16/09 h16:15)
# ===========================================================================
# «Non devono mai esserci 2 lay a mercato, se si abbinano siamo scoperti!!!»
# La posizione di Mike e' un BACK: due lay abbinate la ribaltano in netto LAY,
# cioe' scoperta. Un ramo che sostituisce una lay emette SOLO l'annullamento;
# la nuova arriva al giro dopo, e solo se la vecchia non e' piu' viva.
def _conferma_annulli(ctx: E.MatchCtx, d: E.Decision) -> None:
    """Betfair ha CONFERMATO: e' cio' che fa `service._mark_trade_cancelled`
    quando `cancel_esito` torna confermato (la parte abbinata resta posizione)."""
    for a in d.actions:
        if a.kind != "cancel":
            continue
        for l in ctx.legs:
            if l.ref == a.ref and l.is_live:
                l.status = "open" if l.matched > 0 else "cancelled"


def test_sostituire_una_lay_viva_emette_SOLO_l_annullamento():
    """FALSIFICA il vecchio comportamento: `cancel` + `place` nello stesso giro.
    Il reperto e' del replay su 35777617 (J2: nuova ko_green mentre
    ko_green-0-3 e' ancora viva, abbinato 8,15/10,14)."""
    viva = gamba_uscita(matched=8.15, avg_price=1.48)     # la size del piano cambia
    ctx = ctx_in_uscita(gambe=[viva])
    d = E.decide(ctx, snap(KO + 30.0), PAR)
    assert [a.kind for a in d.actions] == ["cancel"]
    assert d.actions[0].ref == "ko_green-0-3"
    assert "mai due lay a mercato" in d.reason


def test_con_l_annullamento_CONFERMATO_la_nuova_lay_arriva_al_giro_dopo():
    """...e dimensionata sulla posizione REALE di quel momento.

    Qui la posizione cresce (si abbina il residuo PERSIST a 1,60): la vecchia
    uscita e' al prezzo sbagliato, si annulla, e al giro dopo — con
    l'annullamento confermato — se ne appoggia UNA nuova sulla media vera.
    Il caso «parziale prima del cancel -> la nuova copre solo il residuo» e'
    difeso su una chiusura vera da
    `test_mike_engine.test_closing_retry_includes_partially_matched_leg`.
    """
    viva = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[viva])
    secondo = E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                    side="back", price=1.60, size=10.0, matched=10.0, avg_price=1.60,
                    ref="under_last-0-2", status="open", placed_at=KO - 60)
    ctx.legs.append(secondo)                       # media 1,55: l'uscita va rifatta
    d1 = E.decide(ctx, snap(KO + 30.0, u35=book(1.55)), PAR)
    assert [a.kind for a in d1.actions] == ["cancel"]
    E.apply_decision(ctx, d1, KO + 30.0)
    _conferma_annulli(ctx, d1)
    assert viva.status == "cancelled"
    d2 = E.decide(ctx, snap(KO + 31.0, u35=book(1.55)), PAR)
    posati = [a for a in d2.actions if a.kind == "place"]
    assert len(posati) == 1 and posati[0].side == "lay"
    assert float(posati[0].price) == pytest.approx(1.53)   # 2 tick sotto la media 1,55
    w, l = E.exposure(ctx.legs, E.MARKET_OU35, E.SEL_UNDER)
    assert float(posati[0].size) == pytest.approx(round((w - l) / 1.53, 2), abs=0.02)


def test_con_l_annullamento_IGNOTO_nessuna_lay_nuova():
    """Esito ignoto = la vecchia potrebbe essere viva su Betfair: non se ne
    appoggia una seconda, si aspetta la riconciliazione."""
    ignota = gamba_uscita(status=E.STATUS_RECONCILE, matched=0.0)
    ctx = ctx_in_uscita(gambe=[ignota])
    d = E.decide(ctx, snap(KO + 60.0), PAR)
    assert [a for a in d.actions if a.kind == "place"] == []


def test_con_l_annullamento_FALLITO_nessuna_lay_nuova_e_si_ritenta():
    """L'annullamento non e' confermato: la gamba resta VIVA. Nessuna lay nuova,
    e al giro dopo si richiede l'annullamento."""
    viva = gamba_uscita(matched=8.15, avg_price=1.48)
    ctx = ctx_in_uscita(gambe=[viva])
    d1 = E.decide(ctx, snap(KO + 30.0), PAR)
    E.apply_decision(ctx, d1, KO + 30.0)
    # NESSUNA conferma da Betfair: la gamba resta 'pending'
    assert viva.is_live
    d2 = E.decide(ctx, snap(KO + 31.0), PAR)
    assert [a for a in d2.actions if a.kind == "place"] == []
    assert [a.kind for a in d2.actions] == ["cancel"]


def test_J5_e_rosso_su_due_lay_in_volo_sulla_stessa_selezione():
    una = gamba_uscita(ref="ko_green-0-3")
    due = gamba_uscita(role="under_green", ref="under_green-0-2")
    ctx = ctx_in_uscita(gambe=[una, due])
    assert "J5" in _viola(ctx, snap(KO + 30.0))


def test_J5_e_rosso_anche_se_le_due_lay_vivono_un_solo_giro():
    """FALSIFICAZIONE del fix: se si rimette `cancel` + `place` nello stesso
    giro, J5 lo vede. L'annullamento emesso non e' un annullamento confermato."""
    viva = gamba_uscita()
    ctx = ctx_in_uscita(gambe=[viva])
    d = E.Decision(state="LIVE_KO_GREEN", actions=[
        E.Action(kind="cancel", ref=viva.ref, role=viva.role, market=viva.market,
                 selection=viva.selection),
        E.Action(kind="place", role="ko_green", market=E.MARKET_OU35,
                 selection=E.SEL_UNDER, side="lay", price=1.47, size=5.0),
    ], reason="riprezzo")
    codici = [v.codice for v in CERT.verifica(ctx, snap(KO + 30.0), d, PAR)]
    assert "J5" in codici


def test_J5_non_accusa_una_lay_sola():
    ctx = ctx_in_uscita(gambe=[gamba_uscita()])
    assert "J5" not in _viola(ctx, snap(KO + 30.0))


def test_J5_non_e_sollecitato_senza_nessuna_lay_in_volo():
    ctx = ctx_in_uscita()
    sollecitati: Dict[str, int] = {}
    CERT.verifica(ctx, snap(KO + 30.0), E.Decision(state=ctx.state, actions=[], reason=""),
                  PAR, sollecitati=sollecitati)
    assert "J5" not in sollecitati


# ===========================================================================
# 9. IL CASH-OUT GLOBALE DELL'UTENTE (ordine dell'utente, 16/09 h18:20)
# ===========================================================================
# «Il bot gestisce le sue operazioni; UNICO CASO e' quando io chiudo manualmente
# TUTTE le operazioni (cash-out globale della partita): al successivo controllo
# lo capisce e NON FA ALTRO.»
def _ctx_chiuso_dall_utente(inplay: bool = True) -> E.MatchCtx:
    """Lo stato in cui il motore porta la partita dopo un cash-out manuale
    completato (`engine._decide_flatten`), con la posizione gia' chiusa."""
    chiusa = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                   side="back", price=1.50, size=10.0, matched=10.0, avg_price=1.50,
                   ref="under_entry-0-1", status="open", placed_at=KO - 600, archived=True)
    return E.MatchCtx(state="FLAT" if inplay else "WATCH", legs=[chiusa],
                      close_reason="manual", no_reentry=True, reentry_allowed=False,
                      reentry_done=True, flatten_pending=False, live_since=KO, ko_goals=0)


def test_dopo_il_cashout_globale_il_motore_non_apre_piu_niente():
    """Giro successivo, con tutte le condizioni di re-ingresso soddisfatte
    (1 gol, 20', quota buona): il bot NON riapre."""
    ctx = _ctx_chiuso_dall_utente()
    books = {(E.MARKET_OU35, E.SEL_UNDER): book(1.80),
             (E.MARKET_OU45, E.SEL_OVER): book(8.0),
             (E.MARKET_OU45, E.SEL_UNDER): book(1.70)}
    s = E.Snapshot(now=KO + 1200.0, ko_at=KO, books=books, inplay=True, minute=20,
                   goals=1, feed_fresh=True, order_fresh=True)
    d = E.decide(ctx, s, PAR)
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.state == "FLAT"


def test_dopo_il_cashout_globale_pre_KO_non_si_rientra():
    ctx = _ctx_chiuso_dall_utente(inplay=False)
    s = E.Snapshot(now=KO - 3600.0, ko_at=KO, feed_fresh=True, order_fresh=True,
                   books={(E.MARKET_OU35, E.SEL_UNDER): book(1.50, inplay=False)},
                   inplay=False, minute=None, goals=0)
    d = E.decide(ctx, s, PAR)
    assert [a for a in d.actions if a.kind == "place"] == []
    assert d.state == "WATCH"


def test_la_chiusura_manuale_in_gioco_accende_no_reentry():
    """⚠️ Prima del 16/09 `no_reentry` si accendeva SOLO pre-match: in gioco il
    divieto era implicito (`reentry_done`). Adesso e' DETTO, e vale per tutto."""
    chiusa = E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                   side="back", price=1.50, size=10.0, matched=0.0,
                   ref="under_entry-0-1", status="cancelled", placed_at=KO - 600)
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[chiusa], flatten_pending=True,
                     live_since=KO, ko_goals=0)
    s = E.Snapshot(now=KO + 600.0, ko_at=KO, inplay=True, minute=10, goals=0,
                   feed_fresh=True, order_fresh=True,
                   books={(E.MARKET_OU35, E.SEL_UNDER): book(1.60),
                          (E.MARKET_OU45, E.SEL_OVER): book(8.0)})
    d = E.decide(ctx, s, PAR)
    assert d.state == "FLAT" and d.updates.get("no_reentry") is True
    assert d.updates.get("reentry_done") is True
    assert "chiuso_dall_utente" in d.telemetry


def test_R2_e_rosso_se_il_bot_riapre_dopo_il_cashout_globale():
    """FALSIFICAZIONE: si mostra al controllo una decisione che riapre."""
    ctx = _ctx_chiuso_dall_utente()
    d = E.Decision(state="REENTRY_PENDING", actions=[
        E.Action(kind="place", role="reentry", market=E.MARKET_OU45,
                 selection=E.SEL_UNDER, side="back", price=1.70, size=10.0)],
        reason="re-ingresso")
    codici = [v.codice for v in CERT.verifica(ctx, snap(KO + 1200.0), d, PAR)]
    assert "R2" in codici


def test_R2_lascia_passare_le_CHIUSURE():
    """Niente che protegge puo' impedire di chiudere: se un residuo si abbina,
    il bot deve poterlo chiudere anche dopo il cash-out dell'utente."""
    ctx = _ctx_chiuso_dall_utente()
    d = E.Decision(state="LIVE_CLOSING", actions=[
        E.Action(kind="place", role="under_close", market=E.MARKET_OU35,
                 selection=E.SEL_UNDER, side="lay", price=1.60, size=3.0)],
        reason="chiusura residuo")
    codici = [v.codice for v in CERT.verifica(ctx, snap(KO + 1200.0), d, PAR)]
    assert "R2" not in codici


def test_R2_non_e_sollecitato_senza_cashout_dell_utente():
    ctx = ctx_in_uscita(gambe=[gamba_uscita()])
    sollecitati: Dict[str, int] = {}
    CERT.verifica(ctx, snap(KO + 30.0), E.Decision(state=ctx.state, actions=[], reason=""),
                  PAR, sollecitati=sollecitati)
    assert "R2" not in sollecitati
    ctx2 = _ctx_chiuso_dall_utente()
    CERT.verifica(ctx2, snap(KO + 1200.0), E.Decision(state="FLAT", actions=[], reason=""),
                  PAR, sollecitati=sollecitati)
    assert sollecitati.get("R2") == 1
