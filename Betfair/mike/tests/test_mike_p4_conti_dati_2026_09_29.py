"""P4 BLOCCO 2 (29/09) - CONTI E DATI: M8.6, M8.7, M8.8, M8.9.

  M8.6 - partita regolata = TUTTE le sue righe regolate (anche nel ramo
         «risultato indipendente dal punteggio»); in ERROR le righe aperte si
         marcano «da regolare», mai con un P&L inventato.
  M8.7 - una lettura del feed fallita NON e' una partita sparita: si ritenta,
         si avvisa UNA volta, e nessun orologio di assenza parte.
  M8.8 - la sorveglianza degli ordini gira SEMPRE, anche con la riga assente o
         i dati incompleti.
  M8.9 - paper e live separati anche nei cumulativi del ripiego degli aggregati.

Finti con le chiavi vere: righe di `mike_trades` (id, event_id, signal_key,
status, mode, bet_id, meta), ordini come `omega_market.list_current_orders`
(snake_case), errori PostgREST col testo vero.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

import pytest

from Betfair.mike import config as C
from Betfair.mike import db as MDB
from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_service import NOW, FakeDB

KO = NOW - timedelta(minutes=30)          # partita in gioco da mezz'ora


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)
    S.svuota_le_cache()
    S.azzera_cache_di_processo()
    MDB._AGG_RPC.clear()
    MDB._TOTALS.clear()
    yield
    S.svuota_le_cache()
    S.azzera_cache_di_processo()
    MDB._AGG_RPC.clear()
    MDB._TOTALS.clear()


# ---------------------------------------------------------------------------
# la partita e le sue righe, con le chiavi vere
# ---------------------------------------------------------------------------
def _evento(ctx: E.MatchCtx, *, mode: str = "live", extra: Optional[dict] = None) -> dict:
    ev = {"event_id": "E1", "event_name": "Roma v Lazio", "state": ctx.state, "mode": mode,
          "ko_at": KO.isoformat(), "competition": "Serie A",
          "markets": {E.MARKET_OU35: {"market_id": "1.35"}, E.MARKET_OU45: {"market_id": "1.45"}},
          "dossier": {}, "live": {},
          "ctx": {"selections": {f"{E.MARKET_OU35}|{E.SEL_UNDER}": 1222344,
                                 f"{E.MARKET_OU35}|{E.SEL_OVER}": 1222345,
                                 f"{E.MARKET_OU45}|{E.SEL_UNDER}": 1222347,
                                 f"{E.MARKET_OU45}|{E.SEL_OVER}": 1222346},
                  "seen_inplay": True, **(extra or {})}}
    ev.update(S._row_from_ctx(ev, ctx, ev["ctx"]))
    return ev


def _riga(db: FakeDB, leg: E.Leg, *, status: str, bet_id: Optional[str] = "B1",
          mode: str = "live") -> dict:
    tid = db.insert_trade({"event_id": "E1", "signal_key": leg.ref, "role": leg.role,
                           "strategy": leg.role, "status": status, "mode": mode,
                           "side": leg.side, "price": leg.price, "size": leg.size,
                           "market_id": "1.35", "selection_id": 1222344,
                           "cycle_no": leg.cycle_no, "bet_id": bet_id, "commission": 0.05,
                           "meta": {"phase": "open" if status == "open" else "reserved"}})
    return db.get_trade(tid)


def _giro(db, mk, ev, riga, *, ora=NOW, mode="live"):
    return S._run_event(db=db, market=mk, ev=ev, row=riga, params=C.merge_params(None),
                        mode=mode, now=ora, scanner_age=0.0, atlas=None, dry=False)


def ordine(*, abbinato: float, residuo: float, stato: str) -> dict:
    """Come `omega_market.list_current_orders` (snake_case)."""
    return {"bet_id": "B1", "market_id": "1.35", "selection_id": 1222344, "side": "lay",
            "status": stato, "size_matched": abbinato, "avg_price_matched": 1.48,
            "size_remaining": residuo, "customer_order_ref": "mike-t1",
            "size_cancelled": 0.0, "size_lapsed": 0.0, "size_voided": 0.0,
            "matched_date": "2026-09-12T11:59:00Z", "placed_date": "2026-09-12T11:58:00Z",
            "price_requested": 1.48, "size_requested": 10.14,
            "average_price_matched": 1.48}


class MercatoOrdini:
    """Sportello live: ordini correnti letti, nessun libro REST atteso."""

    def __init__(self, correnti: List[dict]) -> None:
        self.correnti = correnti
        self.letture = 0
        self.libri: List[str] = []

    def list_current_orders(self) -> List[dict]:
        self.letture += 1
        return list(self.correnti)

    def read_book(self, market_id, names):
        self.libri.append(str(market_id))
        return None


def _uscita_appoggiata() -> E.Leg:
    return E.Leg(role="ko_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                 price=1.48, size=10.14, ref="ko_green-0-3", status="pending",
                 placed_at=NOW.timestamp() - 30)


def _ingresso() -> E.Leg:
    return E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
                 price=1.50, size=10.0, matched=10.0, avg_price=1.50, ref="under_entry-0-1",
                 status="open", placed_at=KO.timestamp() - 600)


# ===========================================================================
# M8.8 - LA SORVEGLIANZA GIRA SEMPRE
# ===========================================================================
def _ctx_con_uscita() -> E.MatchCtx:
    return E.MatchCtx(state="LIVE_KO_GREEN", legs=[_ingresso(), _uscita_appoggiata()],
                      live_since=KO.timestamp(), ko_goals=0)


def test_riga_assente_la_lay_appoggiata_si_segue_lo_stesso():
    """Riga del feed assente da poco (sotto i 10 minuti): prima il giro usciva
    subito e l'abbinamento della lay appoggiata restava sconosciuto."""
    db = FakeDB(mode="live")
    ctx = _ctx_con_uscita()
    _riga(db, ctx.legs[0], status="open", bet_id="B0")
    _riga(db, ctx.legs[1], status="pending")
    mk = MercatoOrdini([ordine(abbinato=10.14, residuo=0.0, stato="EXECUTION_COMPLETE")])
    ev = _evento(ctx)
    _giro(db, mk, ev, None)
    assert mk.letture >= 1, "la lay appoggiata non e' stata seguita"
    uscita = [p for p in ev["positions"] if p["ref"] == "ko_green-0-3"][0]
    assert uscita["status"] == "open" and uscita["matched"] == pytest.approx(10.14)
    assert "fill_resting" in db.kinds()
    assert mk.libri == []                     # nessun regolamento partito


def test_dati_incompleti_la_lay_appoggiata_si_segue_lo_stesso():
    """Riga presente ma con una sola linea (la 4,5 manca): prima nessuna
    sorveglianza."""
    db = FakeDB(mode="live")
    ctx = _ctx_con_uscita()
    _riga(db, ctx.legs[0], status="open", bet_id="B0")
    _riga(db, ctx.legs[1], status="pending")
    p = payload(ko=KO, inplay=True, minute=30, sh=0, sa=0)
    p["ou"] = p["ou"][:1]                     # solo l'Under/Over 3,5
    mk = MercatoOrdini([ordine(abbinato=10.14, residuo=0.0, stato="EXECUTION_COMPLETE")])
    ev = _evento(ctx)
    _giro(db, mk, ev, row(p))
    assert mk.letture >= 1
    uscita = [x for x in ev["positions"] if x["ref"] == "ko_green-0-3"][0]
    assert uscita["status"] == "open"


# ===========================================================================
# M8.7 - UNA LETTURA FALLITA NON E' UNA PARTITA SPARITA
# ===========================================================================
def test_la_lettura_del_feed_fallita_torna_None(monkeypatch):
    def _giu(*_a, **_k):
        raise RuntimeError("The read operation timed out")
    monkeypatch.setattr(MDB, "_sb", _giu)
    assert MDB.fetch_scan_rows() is None


class DbFeedRotto(FakeDB):
    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.rotto = False

    def fetch_scan_rows(self):
        return None if self.rotto else list(self.scan_rows)


def test_lettura_fallita_si_tiene_l_ultima_lista_e_si_avvisa_una_volta():
    db = DbFeedRotto()
    db.scan_rows = [row(payload())]
    par = {"feed_cache_s": 0.0}
    righe, _f = S._righe_del_feed(db, par, NOW.timestamp())
    assert len(righe) == 1
    db.rotto = True
    for i in range(1, 5):
        righe, _f = S._righe_del_feed(db, par, NOW.timestamp() + i)
        assert len(righe) == 1, "la partita e' sparita per una lettura fallita"
    errori = [p for k, p, _e in db.activity if k == "error"]
    assert [p["reason"] for p in errori] == ["lettura_feed_fallita"]
    db.rotto = False
    S._righe_del_feed(db, par, NOW.timestamp() + 10)
    riprese = [p for k, p, _e in db.activity if k == "skip"
               and p.get("reason") == "lettura_feed_ripresa"]
    assert len(riprese) == 1


def test_con_la_lettura_rotta_nessun_regolamento_dopo_dieci_minuti():
    """Prima: 10 minuti di letture fallite = partita «assente» = regolamento
    via REST. Ora: nessun orologio d'assenza finche' la lettura fallisce."""
    db = DbFeedRotto(mode="live")
    S._avvisa_feed_non_letto(db, NOW.timestamp())          # episodio aperto
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[_ingresso()], live_since=KO.timestamp(),
                     ko_goals=0)
    _riga(db, ctx.legs[0], status="open", bet_id="B0")
    mk = MercatoOrdini([])
    ev = _evento(ctx)
    for minuti in (0, 5, 11, 20):
        _giro(db, mk, ev, None, ora=NOW + timedelta(minutes=minuti))
    assert mk.libri == [], "regolamento partito su una lettura fallita"
    assert ev["state"] == "LIVE_UNCOVERED"
    assert "row_missing_since" not in (ev.get("ctx") or {})


# ===========================================================================
# M8.9 - PAPER E LIVE SEPARATI ANCHE NEI CUMULATIVI DEL RIPIEGO
# ===========================================================================
def _rpc_mancante(*_a, **_k):
    raise RuntimeError("{'code': 'PGRST202', 'message': 'Could not find the function "
                       "public.get_mike_aggregates(p_mode) in the schema cache'}")


def _righe_modi():
    ts = NOW.isoformat()
    return [{"id": 1, "event_id": "A", "status": "lost", "pnl": -80.0, "mode": "paper",
             "placed_at": ts, "settled_at": ts},
            {"id": 2, "event_id": "B", "status": "won", "pnl": 3.0, "mode": "live",
             "placed_at": ts, "settled_at": ts}]


def test_i_cumulativi_del_ripiego_sono_per_modalita(monkeypatch):
    monkeypatch.setattr(MDB, "_sb", _rpc_mancante)
    monkeypatch.setattr(MDB, "live_trades", lambda since=None: _righe_modi())
    monkeypatch.setattr(MDB, "all_trades", lambda *a, **k: _righe_modi())
    live = MDB.aggregates(NOW, mode="live")
    paper = MDB.aggregates(NOW, mode="paper")
    assert live["realized_total"] == 3.0 and live["won"] == 1 and live["lost"] == 0
    assert paper["realized_total"] == -80.0 and paper["won"] == 0 and paper["lost"] == 1


# ===========================================================================
# M6.3 (richiesta del coordinatore, verifica del blocco 1): una sospensione
# annotata NON si legge finche' il mercato DELLA GAMBA annotata non e' aperto,
# anche quando la gamba non e' piu' fra le appoggiate vive.
# ===========================================================================
class MercatoCheNonSiLegge:
    """Se Mike prova a rileggere, il test lo vede (chiavi di omega_market)."""

    def __init__(self) -> None:
        self.letture: List[str] = []

    def list_current_orders(self) -> List[dict]:
        self.letture.append("correnti")
        return []

    def order_state_by_bet_id(self, bet_id: str) -> dict:
        self.letture.append(f"bet:{bet_id}")
        return {"found": False}


def _libro(status: str) -> E.Book:
    return E.Book(best_back=1.50, back_size=100.0, best_lay=1.52, lay_size=100.0,
                  status=status, inplay=True)


def _snap_mercati(u35: str, u45: str) -> E.Snapshot:
    return E.Snapshot(now=NOW.timestamp(), ko_at=KO.timestamp(),
                      books={(E.MARKET_OU35, E.SEL_UNDER): _libro(u35),
                             (E.MARKET_OU45, E.SEL_OVER): _libro(u45),
                             (E.MARKET_OU45, E.SEL_UNDER): _libro(u45)},
                      inplay=True, minute=20, goals=1, feed_fresh=True, order_fresh=True)


def _sorveglia(ctx, snap, mk, db) -> None:
    S._sorveglia_sospensione(db=db, market=mk, ctx=ctx, snap=snap,
                             params=C.merge_params({"pre_exit_mode": "resting"}),
                             mode="live", now_ts=NOW.timestamp(), ev={"event_id": "E1"})


@pytest.mark.parametrize("gamba,u35,u45", [
    # 1. uscita al fischio passata a esito ignoto, Under 3,5 ancora SOSPESO
    ("ko_green", "SUSPENDED", "OPEN"),
    # 2. stessa cosa col mercato CHIUSO
    ("ko_green", "CLOSED", "OPEN"),
    # 3. banca del rientro sull'Under 4,5 ancora sospeso, Under 3,5 gia' riaperto
    ("reentry_green", "OPEN", "SUSPENDED"),
])
def test_annotata_non_piu_viva_non_si_legge_a_mercato_non_aperto(gamba, u35, u45):
    mercato = E.MARKET_OU35 if gamba == "ko_green" else E.MARKET_OU45
    leg = E.Leg(role=gamba, market=mercato, selection=E.SEL_UNDER, side="lay", price=1.48,
                size=10.14, ref=f"{gamba}-0-3", status=E.STATUS_RECONCILE,
                placed_at=NOW.timestamp() - 60)
    ctx = E.MatchCtx(state="LIVE_KO_GREEN", legs=[_ingresso(), leg],
                     riapertura={"ts": NOW.timestamp() - 30, "refs": [leg.ref],
                                 "letto": False, "esiti": {}})
    db, mk = FakeDB(mode="live"), MercatoCheNonSiLegge()
    _sorveglia(ctx, _snap_mercati(u35, u45), mk, db)
    assert ctx.riapertura["letto"] is False
    assert ctx.riapertura["esiti"] == {}
    assert mk.letture == []
    assert "rilettura_alla_riapertura" not in db.kinds()
    # ...e quando il mercato DELLA GAMBA riapre la memoria si chiude (la gamba
    # non e' piu' viva: la segue la riconciliazione, come prima)
    _sorveglia(ctx, _snap_mercati("OPEN", "OPEN"), mk, db)
    assert ctx.riapertura["letto"] is True
    assert ctx.riapertura["esiti"] == {leg.ref: "gamba_non_piu_viva"}


# ===========================================================================
# M8.6 - PARTITA REGOLATA = TUTTE LE RIGHE REGOLATE
# ===========================================================================
def _libro_illeggibile_da_ore(ctx: E.MatchCtx, db: FakeDB):
    """Mercato chiuso nel feed, libro REST illeggibile, prima lettura di
    regolamento oltre le 2 ore fa, punteggio mai visto."""
    ev = _evento(ctx, extra={"seen_inplay": False,
                             "settle_first_ts": NOW.timestamp() - 3 * 3600})
    p = payload(ko=KO, status="CLOSED")
    return ev, row(p)


def test_regolata_senza_punteggio_regola_anche_le_righe():
    """Ciclo chiuso in green (risultato indipendente dal punteggio): prima la
    partita diventava SETTLED e le righe restavano 'open' per sempre."""
    ingresso = _ingresso()
    ingresso.archived = True
    # stessa quota e stessa size: il conto e' identico con qualunque risultato
    green = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                  price=1.50, size=10.0, matched=10.0, avg_price=1.50, ref="under_green-0-2",
                  status="open", archived=True, closes_ref="under_entry-0-1")
    ctx = E.MatchCtx(state="WATCH", legs=[ingresso, green], cycle_no=1)
    db = FakeDB(mode="live")
    _riga(db, ingresso, status="open", bet_id="B0")
    _riga(db, green, status="open", bet_id="B1")
    ev, r = _libro_illeggibile_da_ore(ctx, db)
    _giro(db, MercatoOrdini([]), ev, r)
    assert ev["state"] == "SETTLED"
    stati = sorted(t["status"] for t in db.trades)
    assert all(s in ("won", "lost", "void") for s in stati), stati
    assert round(sum(float(t["pnl"]) for t in db.trades), 2) == pytest.approx(
        float(ev["settled_pnl"]), abs=0.01)
    assert all(t["meta"].get("settle_reason") == "risultato_indipendente_dal_punteggio"
               for t in db.trades)


def test_regolamento_non_determinabile_marca_le_righe_aperte():
    """Posizione aperta (il conto dipende dal risultato) e risultato illeggibile:
    ERROR, ma le righe aperte portano «regolamento non determinabile» e il log
    le elenca. Nessun P&L inventato: lo status resta quello che era."""
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[_ingresso()], live_since=KO.timestamp())
    db = FakeDB(mode="live")
    _riga(db, ctx.legs[0], status="open", bet_id="B0")
    ev, r = _libro_illeggibile_da_ore(ctx, db)
    _giro(db, MercatoOrdini([]), ev, r)
    assert ev["state"] == "ERROR"
    assert db.trades[0]["status"] == "open"
    assert db.trades[0]["meta"].get("regolamento") == "non_determinabile"
    err = [p for k, p, _e in db.activity if k == "error" and p.get("reason") == "settle_timeout"]
    assert err and err[0]["righe_da_regolare"] == [db.trades[0]["id"]]
