"""D1 (28/09) - MIKE: LA RISERVA CON LA RISPOSTA PERSA.

Difetto (``AUDIT_2026-09-25/FIX_C_RESILIENZA_RETE_2026-09-26.md`` §7 punto 3):
``_insert_trade_row`` puo' sollevare DOPO che il server ha scritto la riga
(timeout sulla risposta). La gamba diventa 'cancelled' (``reserve_failed``), la
riga 'pending' resta nel database e nessuno la chiude: ``_gia_appoggiata`` la
vede come «gamba gia' in volo» e blocca PER SEMPRE (fail-closed) il green-up o
la copertura dello stesso ruolo e ciclo. Se poi la gamba viene potata
(``prune_dead_legs``) la riga diventa un'orfana che in live resta 'pending'.

Atteso: la riga si riconcilia con la fonte vera dell'ordine (paper: nessun
ordine simulato puo' esistere -> chiusa come non eseguita; live: Betfair per
bet_id / ``mike-t<id>`` / ref storico), il ruolo torna libero, mai una seconda
copertura, mai una copertura bloccata per sempre. Stesso codice in paper e live.

Parita' (stessa consegna): il freno anti-doppione della lay appoggiata vale
anche in PAPER (prima solo in live); un ``insert_trade`` senza id non manda
mai un ordine col ref ``leg.ref`` (15/09).

I finti parlano come il vero: ``insert_trade`` torna l'ID (int), gli ordini
hanno le chiavi snake_case di ``omega_market.list_current_orders``, la rete
giu' e' ``httpx.ReadTimeout``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import httpx
import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_service import NOW as NOW_S, FakeDB, FakeMarket, legs, run
from Betfair.omega.omega_market import PlaceResult

NOW = datetime(2026, 9, 28, 14, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _nessun_accesso_al_db_vero(monkeypatch):
    """Il freno condiviso (``controls.motivo_kill_switch``) legge il database
    vero: qui non e' l'oggetto del test, e nessun test tocca la produzione."""
    monkeypatch.setattr(S.X, "_freno_aperture", lambda: None)
    monkeypatch.setattr(S.X, "_live_brake", lambda: None)
    monkeypatch.setattr(S, "_freno_aperture_rest", lambda: None)

    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)
VECCHIO = "2026-09-28T13:40:00+00:00"          # oltre RECON_GRACE_S
EID = "36066505"


# ===========================================================================
# A. PAPER, ciclo intero (run_once), con il banco di test_mike_service
# ===========================================================================
class DbRispostaPersa(FakeDB):
    """``insert_trade`` che SCRIVE la riga e poi perde la risposta (una volta)
    per il ruolo indicato: e' il timeout PostgREST dopo il commit."""

    def __init__(self, *a: Any, perdi_su: Optional[str] = None, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.perdi_su = perdi_su

    def insert_trade(self, trade):
        rid = super().insert_trade(trade)
        if self.perdi_su and trade.get("strategy") == self.perdi_su:
            self.perdi_su = None
            raise httpx.ReadTimeout("The read operation timed out")
        return rid


def _green_pending(db) -> List[dict]:
    return [t for t in db.trades if t.get("strategy") == "under_green"
            and t.get("status") == "pending"]


def _fino_al_green_perso(db, mk):
    run(db, mk, NOW_S, [row(payload())])                               # ingresso abbinato
    db.perdi_su = "under_green"
    run(db, mk, NOW_S + timedelta(seconds=2), [row(payload())])       # riserva persa
    orfana = [t for t in db.trades if t.get("strategy") == "under_green"]
    assert len(orfana) == 1 and orfana[0]["status"] == "pending", "precondizione"
    g = [l for l in legs(db) if l["role"] == "under_green"]
    assert g and g[-1]["status"] == "cancelled", "precondizione: gamba annullata"
    return orfana[0]


def test_paper_la_riserva_persa_NON_blocca_il_green_up_per_sempre():
    db, mk = DbRispostaPersa(params={"stake": 10}), FakeMarket()
    orfana = _fino_al_green_perso(db, mk)

    run(db, mk, NOW_S + timedelta(seconds=4), [row(payload())])

    assert orfana["status"] == "error", "la riga orfana resta pending: ruolo bloccato"
    assert orfana["meta"]["reason"] == "reconciled_not_placed"
    assert orfana["meta"]["riserva_orfana"] == "gamba_annullata"
    vivi = _green_pending(db)
    assert len(vivi) == 1 and vivi[0]["id"] != orfana["id"], "il green-up torna disponibile"
    assert any(k == "reconcile_pending" and p.get("reason") == "riserva_orfana"
               for k, p, _ in db.activity)


def test_paper_con_la_riserva_orfana_ancora_in_volo_NON_nasce_una_seconda_riga():
    """Riconciliazione non ancora dovuta (cadenza di produzione 30 s): come in
    live, la riga in attesa frena una seconda lay dello stesso ruolo e ciclo."""
    db, mk = DbRispostaPersa(params={"stake": 10, "reconcile_every_s": 600}), FakeMarket()
    _fino_al_green_perso(db, mk)

    run(db, mk, NOW_S + timedelta(seconds=4), [row(payload())])

    assert len(_green_pending(db)) == 1, "paper piu' generoso del live: due righe"
    assert any(k == "place_saltato" and p.get("reason") == "gamba_gia_appoggiata"
               for k, p, _ in db.activity)


# ===========================================================================
# B. LIVE (e paper per parita'), a livello di riconciliazione
# ===========================================================================
def ordine(**kw: Any) -> Dict[str, Any]:
    """Un ordine come ``omega_market.list_current_orders()``: snake_case."""
    base = {"bet_id": "B1", "customer_order_ref": "mike-t1", "market_id": "1.262445982",
            "selection_id": 1222344, "side": "lay", "status": "EXECUTABLE",
            "size_matched": 0.0, "size_remaining": 5.05, "avg_price_matched": None}
    base.update(kw)
    return base


class DbRighe:
    def __init__(self, righe: List[dict]) -> None:
        self.righe = list(righe)
        self.log_righe: List[tuple] = []
        self._id = max([int(r["id"]) for r in righe] or [0])

    def trades_for_event(self, _event_id, **_kw) -> List[dict]:
        return list(self.righe)

    def insert_trade(self, row, **_kw):
        self._id += 1
        self.righe.append({**row, "id": self._id})
        return self._id

    def update_trade(self, trade_id, **campi):
        for r in self.righe:
            if r.get("id") == trade_id:
                r.update(campi)

    def log(self, kind, payload=None, event_id=None):
        self.log_righe.append((kind, payload or {}))

    def kinds(self) -> List[str]:
        return [k for k, _ in self.log_righe]


class Mercato:
    def __init__(self, correnti=None, regolati=None, giu=False) -> None:
        self.correnti, self.regolati, self.giu = list(correnti or []), list(regolati or []), giu
        self.letture = 0
        self.piazzati: List[dict] = []

    def list_current_orders(self):
        self.letture += 1
        if self.giu:
            raise httpx.ConnectTimeout("timed out")
        return list(self.correnti)

    def list_cleared_orders(self):
        if self.giu:
            raise httpx.ConnectTimeout("timed out")
        return list(self.regolati)

    def place_order_live(self, **kw):
        self.piazzati.append(dict(kw))
        return PlaceResult(ok=True, order_status="EXECUTABLE", bet_id="B9",
                           size_matched=0.0, avg_price_matched=None, raw={})


class Info:
    event_id = EID
    event_name = "Trinec v Mlada Boleslav"
    complete = True

    def market_id(self, _m):
        return "1.262445982"

    def selection_id(self, _m, s):
        return 1222344 if s == E.SEL_UNDER else 1222345

    def selection_name(self, _m, s):
        return "Under 3.5 Goals" if s == E.SEL_UNDER else "Over 3.5 Goals"


def riga_orfana(mode="live", **kw) -> Dict[str, Any]:
    """La riga scritta dal server mentre la risposta si perdeva: 'pending',
    ``phase='reserved'``, nessun bet_id."""
    base = {"id": 1, "event_id": EID, "signal_key": "under_green-0-2", "role": "under_green",
            "strategy": "under_green", "cycle_no": 0, "side": "lay", "status": "pending",
            "mode": mode, "bet_id": None, "market_id": "1.262445982", "selection_id": 1222344,
            "market_type": "OVER_UNDER_35", "selection_name": "Under 3.5 Goals",
            "price": 1.43, "size": 5.05, "persistence": "LAPSE", "placed_at": VECCHIO,
            "closes_trade_id": 99,
            "meta": {"phase": "reserved", "leg_ref": "under_green-0-2", "final": False}}
    base.update(kw)
    return base


def gamba(**kw: Any) -> E.Leg:
    base = dict(ref="under_green-0-2", role="under_green", market=E.MARKET_OU35,
                selection=E.SEL_UNDER, side="lay", price=1.43, size=5.05,
                status="cancelled", cycle_no=0)
    base.update(kw)
    return E.Leg(**base)


def giro(db, mk, ctx, mode):
    """Le due fasi del ciclo, nell'ordine di ``_run_event``."""
    S._reconcile_trades(db, EID, ctx, Info(), mode, {}, None, None)
    S._reconcile_unknown(db, mk, EID, ctx, mode, NOW)


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_ordine_ASSENTE_la_riga_si_chiude_e_il_ruolo_torna_libero(mode):
    db, mk = DbRighe([riga_orfana(mode)]), Mercato()
    ctx = E.MatchCtx(legs=[gamba()])
    assert S._gia_appoggiata(db, EID, gamba(ref="under_green-0-7")) is not None, "precondizione"

    giro(db, mk, ctx, mode)

    assert db.righe[0]["status"] == "error"
    assert db.righe[0]["meta"]["reason"] == "reconciled_not_placed"
    assert ctx.legs[0].status == "cancelled"
    assert S._gia_appoggiata(db, EID, gamba(ref="under_green-0-7")) is None
    assert mk.letture == (1 if mode == "live" else 0), "in paper Betfair non si interroga"


def test_live_ordine_ESISTENTE_e_abbinato_si_AGGANCIA():
    """La riga era stata scritta e l'ordine era partito (processo morto prima
    di confermare): la posizione vera torna visibile, nessun secondo ordine."""
    db = DbRighe([riga_orfana()])
    mk = Mercato(correnti=[ordine(size_matched=5.05, size_remaining=0.0,
                                  avg_price_matched=1.42, status="EXECUTION_COMPLETE")])
    ctx = E.MatchCtx(legs=[gamba()])

    giro(db, mk, ctx, "live")

    assert ctx.legs[0].status == "open" and ctx.legs[0].matched == pytest.approx(5.05)
    assert db.righe[0]["status"] == "open"
    assert mk.piazzati == []


def test_live_ordine_VIVO_non_abbinato_si_aspetta_senza_liberare():
    db = DbRighe([riga_orfana()])
    mk = Mercato(correnti=[ordine()])
    ctx = E.MatchCtx(legs=[gamba()])

    giro(db, mk, ctx, "live")

    assert db.righe[0]["status"] == "pending"
    assert ctx.legs[0].status == E.STATUS_RECONCILE
    assert S._gia_appoggiata(db, EID, gamba(ref="under_green-0-7")) is not None


def test_live_betfair_giu_resta_in_verifica_e_si_risolve_al_rientro():
    db = DbRighe([riga_orfana()])
    mk = Mercato(giu=True)
    ctx = E.MatchCtx(legs=[gamba()])

    giro(db, mk, ctx, "live")
    assert db.righe[0]["status"] == "pending" and ctx.legs[0].status == E.STATUS_RECONCILE

    mk.giu = False
    giro(db, mk, ctx, "live")
    assert db.righe[0]["status"] == "error" and ctx.legs[0].status == "cancelled"


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_riga_senza_gamba_POTATA_viene_ricostruita_e_riconciliata(mode):
    """La gamba annullata e' stata potata (``prune_dead_legs``): la riga di
    chiusura 'pending' restava senza gamba, saltata dalla regola delle orfane
    (``closes_trade_id``) e quindi pending per sempre."""
    db, mk = DbRighe([riga_orfana(mode)]), Mercato()
    ctx = E.MatchCtx(legs=[])

    giro(db, mk, ctx, mode)

    assert db.righe[0]["status"] == "error"
    assert db.righe[0]["meta"]["riserva_orfana"] == "gamba_ricostruita"
    assert [l.ref for l in ctx.legs] == ["under_green-0-2"]
    assert ctx.legs[0].status == "cancelled"
    assert S._gia_appoggiata(db, EID, gamba(ref="under_green-0-7")) is None


def test_una_gamba_VIVA_con_la_sua_riga_pending_non_si_tocca():
    """Cintura: la riga pending di una gamba viva (lay appoggiata sul book) e'
    il caso normale, non un'orfana."""
    db, mk = DbRighe([riga_orfana()]), Mercato()
    ctx = E.MatchCtx(legs=[gamba(status="pending")])

    giro(db, mk, ctx, "live")

    assert db.righe[0]["status"] == "pending" and ctx.legs[0].status == "pending"
    assert "riserva_orfana" not in (db.righe[0]["meta"] or {})
    assert mk.letture == 0


def test_lo_specchio_non_combacia_se_una_riga_aperta_ha_la_gamba_annullata():
    ctx = E.MatchCtx(legs=[gamba()])
    assert S._mirror_is_aligned(ctx, {EID: {"under_green-0-2"}}, EID) is False
    assert S._mirror_is_aligned(ctx, {EID: set()}, EID) is True


# ===========================================================================
# C. insert_trade SENZA id: nessun ordine (mai col ref ``leg.ref``)
# ===========================================================================
class DbSenzaId(DbRighe):
    def insert_trade(self, row, **_kw):
        super().insert_trade(row)
        return None


def test_lay_appoggiata_live_senza_id_di_riserva_NON_parte():
    db, mk = DbSenzaId([]), Mercato()
    g = gamba(status="pending")
    S._piazza_resting_live(db=db, market=mk, info=Info(), leg=g, mode="live", params={},
                           minuto=None, score=None, chiude=99, motivo=None,
                           ev={"event_id": EID})
    assert mk.piazzati == [], "ordine partito col ref leg.ref, irriconoscibile"
    assert g.status == "cancelled"
    assert "reserve_failed" in [p.get("reason") for k, p in db.log_righe if k == "error"]


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_execute_place_senza_id_di_riserva_non_esplode_e_non_piazza(mode, monkeypatch):
    chiamate: List[dict] = []
    monkeypatch.setattr(S.X, "place", lambda **kw: chiamate.append(kw))
    db = DbSenzaId([])
    g = gamba(ref="under_close-0-3", role="under_close", side="lay", status="pending")
    esito = S.execute_place(db=db, market=Mercato(), info=Info(), leg=g,
                            book=E.Book(best_back=1.42, best_lay=1.43, back_size=50.0,
                                        lay_size=50.0, status="OPEN"),
                            mode=mode, params={}, now=NOW, dry=False)
    assert esito == "cancelled" and chiamate == []
