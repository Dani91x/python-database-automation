# -*- coding: utf-8 -*-
"""T3 (17/09) — consapevolezza completa degli ordini, tre reperti chiusi qui:

- O-5/R-C1: ``reconcile_pending`` confermava i pending LIVE/PAPER senza mai
  dichiarare ``size_remaining``/``betfair_updated_at`` (restavano None anche
  quando Betfair — o la riconciliazione stessa — lo sapeva). Stesso buco in
  ``_flumine_confirm`` (paper e live via coda) e nel fill istantaneo paper
  legacy di ``_place_one``.
- R-J3: il ref STORICO per-evento (``omega-<event_id>``, pre §16 review C1)
  in ``candidate_customer_refs`` colludeva fra le DUE GAMBE di una stessa
  partita (``ht_cs``/``ft_cs``, stesso event_id): un ordine Betfair superstite
  con quel vecchio ref poteva confermare la gamba sbagliata.
- R-J6: ``place_parziale`` non scattava mai fuori dal place REST diretto in
  LIVE — un fill PARZIALE via paper legacy o via coda flumine (paper/live)
  restava muto, il trader non vedeva il residuo.

I finti usano le CHIAVI VERE: gli ordini correnti/regolati hanno le chiavi che
``omega_market._riga_corrente``/``_riga_regolata`` producono davvero
(snake_case: ``size_matched``, ``size_remaining``, ``avg_price_matched``,
``bet_id``, ``customer_order_ref``, ``matched_date``, ``placed_date``); le
righe ``omega_trades`` hanno le colonne vere di
``trades_consapevolezza_ordine_2026-09-16.sql``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Betfair.omega import certificazione as CERT
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as M
from Betfair.omega import omega_service as S

NOW = datetime(2026, 9, 17, 16, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fakes minimi (stesso stile di test_omega_service.py)
# ---------------------------------------------------------------------------
class FakeDB:
    def __init__(self):
        self.trades: list[dict] = []
        self.activity: list[tuple[str, dict]] = []

    def log(self, kind, payload=None):
        self.activity.append((kind, payload or {}))

    def insert_trade(self, trade):
        row = dict(trade)
        row["id"] = len(self.trades) + 1
        row.setdefault("placed_at", NOW.isoformat())
        self.trades.append(row)
        return row["id"]

    def update_trade(self, trade_id, **fields):
        for t in self.trades:
            if t["id"] == trade_id:
                t.update(fields)

    def delete_trade(self, trade_id):
        self.trades = [t for t in self.trades if t["id"] != trade_id]

    def list_trades(self, status=None):
        return [t for t in self.trades if status is None or t["status"] == status]

    def get_trade(self, trade_id):
        return next((t for t in self.trades if t["id"] == int(trade_id)), None)

    def attivita(self, kind):
        return [p for k, p in self.activity if k == kind]


class FakeMarket:
    """Solo cio' che serve a ``reconcile_pending``."""
    def __init__(self, current=None, cleared=None):
        self.current = current or []
        self.cleared = cleared or []

    def list_current_orders(self, strategy_ref="omega"):
        return self.current

    def list_cleared_orders(self, strategy_ref="omega", market_ids=None, lookback_hours=72):
        return self.cleared


def _pending(mode="live", **over):
    row = {"id": 1, "event_id": "1.100", "market_id": "m1", "selection_id": 4,
           "side": "lay", "mode": mode, "price": 110, "size": 5, "liability": 545,
           "status": "pending", "placed_at": NOW.isoformat(),
           "meta": {"requested_size": 5}}
    row.update(over)
    return row


def _ordine_corrente(**over):
    """Chiavi VERE di ``omega_market._riga_corrente`` (lette dal codice sorgente
    riga per riga, non a memoria)."""
    o = {"bet_id": "bX", "market_id": "m1", "selection_id": 4, "side": "lay",
         "status": "EXECUTION_COMPLETE", "size_matched": 5.0,
         "avg_price_matched": 110.0, "size_remaining": 0.0,
         "customer_order_ref": "omega-t1", "size_cancelled": 0.0,
         "size_lapsed": 0.0, "size_voided": 0.0,
         "matched_date": "2026-09-17T15:59:58+00:00",
         "placed_date": "2026-09-17T15:59:50+00:00",
         "price_requested": 110.0, "size_requested": 5.0,
         "average_price_matched": 110.0}
    o.update(over)
    return o


def _ordine_regolato(**over):
    """Chiavi VERE di ``omega_market._riga_regolata``."""
    o = {"bet_id": "bY", "market_id": "m1", "selection_id": 4, "side": "lay",
         "size_settled": 3.0, "size_matched": 3.0, "size_remaining": 0.0,
         "price": 110.0, "avg_price_matched": 110.0, "profit": 0.0,
         "bet_outcome": None, "customer_order_ref": "omega-t1"}
    o.update(over)
    return o


# ---------------------------------------------------------------------------
# R-C1 — size_remaining / betfair_updated_at DICHIARATI alla conferma
# ---------------------------------------------------------------------------
def test_r_c1_reconcile_live_size_remaining_e_istante_dichiarati():
    """Ordine corrente COMPLETO (K7-style): la conferma porta il residuo VERO
    (0.0, non None) e l'istante di Betfair (matched_date), non l'ora del
    processo."""
    db = FakeDB()
    db.trades = [_pending(mode="live")]
    market = FakeMarket(current=[_ordine_corrente()])
    n = S.reconcile_pending(market=market, db=db, now=NOW)
    assert n == 1
    t = db.trades[0]
    assert t["status"] == "open"
    assert t["size_remaining"] == 0.0            # prima: None, sempre
    assert t["betfair_updated_at"] == "2026-09-17T15:59:58+00:00"


def test_r_c1_reconcile_live_cleared_parziale_residuo_dichiarato_zero():
    """Ordine REGOLATO con settled (3.0) SOTTO il chiesto (meta.requested_size
    5.0, catalogo K6): il residuo non e' piu' None — e' 0.0 (niente resta VIVO
    sul book, l'ordine e' chiuso), e la riga NON diventa una falsa violazione
    K6 (K6 accetta qualunque size_remaining dichiarato, anche 0)."""
    db = FakeDB()
    db.trades = [_pending(mode="live", meta={"requested_size": 5.0})]
    market = FakeMarket(current=[], cleared=[_ordine_regolato(size_settled=3.0,
                                                              size_matched=3.0)])
    S.reconcile_pending(market=market, db=db, now=NOW)
    t = db.trades[0]
    assert t["status"] == "open"
    assert t["size"] == 3.0
    assert t["size_remaining"] == 0.0             # dichiarato, non None
    viol = CERT.verifica_consapevolezza(
        [{"id": t["id"], "event_id": t["event_id"], "market_id": t["market_id"],
          "selection_id": t["selection_id"], "side": "lay", "price": t["price"],
          "size": t["size"], "status": "open", "bet_id": t["bet_id"],
          "meta": t["meta"]}],
        {"omega-t1": _ordine_corrente(size_matched=3.0, size_remaining=0.0,
                                      status="EXECUTION_COMPLETE")}, set())
    assert "K6" not in {v.codice for v in viol}


def test_r_c1_reconcile_paper_size_remaining_e_istante_dichiarati():
    db = FakeDB()
    db.trades = [_pending(mode="paper")]
    market = FakeMarket()
    S.reconcile_pending(market=market, db=db, now=NOW)
    t = db.trades[0]
    assert t["status"] == "open"
    assert t["size_remaining"] == 0.0
    assert t["betfair_updated_at"] == NOW.isoformat()


def test_r_c1_mirror_fill_porta_residuo_e_istante():
    """``_mirror_fill`` (chiusa su master il 17/09, K7 la certifica lato
    colonna) restituisce ANCHE residuo e istante dello specchio, non solo
    abbinato/prezzo/stato: 5-tupla, non 3. Qui si verifica solo la lettura
    pura della funzione (K7 verifica invece che il valore arrivi sulla
    COLONNA e non resti nel solo meta — controllo complementare, non
    ridondante: vedi CHECKPOINT_T3)."""
    mirror = {"size_matched": 4.0, "average_price_matched": 108.0,
             "status": "EXECUTION_COMPLETE", "size_remaining": 0.0,
             "matched_at": "2026-09-17T15:58:00+00:00",
             "updated_at": "2026-09-17T15:58:05+00:00"}
    matched, avg, status, remaining, istante = S._mirror_fill(mirror, None)
    assert (matched, avg, status, remaining) == (4.0, 108.0, "EXECUTION_COMPLETE", 0.0)
    assert istante == "2026-09-17T15:58:00+00:00"     # matched_at, l'istante VERO


def test_r_c1_flumine_confirm_dichiara_residuo_e_istante_se_forniti():
    """La CATENA fino alla colonna: se il chiamante passa residuo/istante
    (come fanno ora i 5 punti di poll, dal tuple di ``_mirror_fill``),
    ``_flumine_confirm`` li scrive nel meta e ``_confirm_open_trade`` li porta
    sulla colonna."""
    db = FakeDB()
    db.trades = [_pending(mode="paper", size=5.0, meta={"requested_size": 5.0})]
    tr = db.trades[0]
    S._flumine_confirm(tr, db=db, matched=5.0, avg=109.5, bet_id="bZ",
                       min_stake=2.0, mode="paper", size_remaining=0.0,
                       betfair_updated_at="2026-09-17T15:57:00+00:00")
    t = db.trades[0]
    assert t["status"] == "open"
    assert t["size_remaining"] == 0.0
    assert t["betfair_updated_at"] == "2026-09-17T15:57:00+00:00"


# ---------------------------------------------------------------------------
# R-J6 — place_parziale sollecitato ANCHE fuori dal REST diretto in LIVE
# ---------------------------------------------------------------------------
def test_r_j6_flumine_confirm_logga_place_parziale_su_fill_sotto_il_chiesto():
    db = FakeDB()
    db.trades = [_pending(mode="paper", size=7.01, meta={"requested_size": 7.01})]
    tr = db.trades[0]
    S._flumine_confirm(tr, db=db, matched=4.20, avg=65.0, bet_id="bP",
                       min_stake=2.0, mode="paper")
    parziali = db.attivita("place_parziale")
    assert len(parziali) == 1, "R-J6: place_parziale non loggato su un fill flumine parziale"
    p = parziali[0]
    assert p["size_requested"] == 7.01
    assert p["size_matched"] == 4.2
    assert p["size_remaining"] == 0.0


def test_r_j6_flumine_confirm_pieno_non_logga_place_parziale():
    """Falso positivo da evitare: un fill COMPLETO non e' un parziale."""
    db = FakeDB()
    db.trades = [_pending(mode="paper", size=5.0, meta={"requested_size": 5.0})]
    tr = db.trades[0]
    S._flumine_confirm(tr, db=db, matched=5.0, avg=110.0, bet_id="bF",
                       min_stake=2.0, mode="paper")
    assert not db.attivita("place_parziale")


def test_r_j6_paper_legacy_place_one_parziale_logga_place_parziale():
    """Fill istantaneo paper (nessuna coda flumine configurata: gate chiuso di
    default, percorso legacy) con ladder SOTTO la size chiesta: il residuo
    (mai piazzato, nessun ordine resta a mercato) va dichiarato."""
    ev = M.EventInfo("1.200", "Casa vs Ospite", NOW - timedelta(minutes=40))
    cs = M.CorrectScoreMarket(market_id="m-1.200", event_id="1.200",
                              event_name="Casa vs Ospite",
                              market_start_time=NOW - timedelta(minutes=40),
                              runner_names={3: "2 - 1"})
    sel = E.Selection(selection_id=3, name="2 - 1", price=75.0, lay_size_available=50.0)
    runner = E.ScoreRunner(3, "2 - 1", lay_price=75.0, lay_size=50.0,
                           lay_ladder=((75.0, 3.0),))          # SOLO 3.0 disponibili in ladder
    snapshot = M.MarketSnapshot(status="OPEN", inplay=True, closed=False,
                                winner_selection_id=None, voided=False,
                                runners=[runner])
    db = FakeDB()
    did = S._place_one(ev=ev, cs=cs, sel=sel, snapshot=snapshot, size=7.01,
                       price=75.0, target=7.01, minute=10, score_str="2 - 1",
                       mode="paper", commission=0.05, market=FakeMarket(), db=db,
                       now=NOW, requested_size=7.01,
                       params={"execution_mode": "auto"})
    assert did == 1
    t = db.trades[0]
    assert t["status"] == "open"
    assert t["size"] == 3.0                       # abbinato = ladder disponibile
    parziali = db.attivita("place_parziale")
    assert len(parziali) == 1, "R-J6: place_parziale non loggato sul fill paper legacy parziale"
    assert parziali[0]["size_requested"] == 7.01
    assert parziali[0]["size_matched"] == 3.0
    assert t["meta"]["size_remaining"] == 0.0     # nessun ordine resta vivo


def test_r_j6_paper_legacy_place_one_pieno_non_logga_place_parziale():
    ev = M.EventInfo("1.201", "Casa vs Ospite", NOW - timedelta(minutes=40))
    cs = M.CorrectScoreMarket(market_id="m-1.201", event_id="1.201",
                              event_name="Casa vs Ospite",
                              market_start_time=NOW - timedelta(minutes=40),
                              runner_names={3: "2 - 1"})
    sel = E.Selection(selection_id=3, name="2 - 1", price=75.0, lay_size_available=50.0)
    runner = E.ScoreRunner(3, "2 - 1", lay_price=75.0, lay_size=50.0,
                           lay_ladder=((75.0, 50.0),))
    snapshot = M.MarketSnapshot(status="OPEN", inplay=True, closed=False,
                                winner_selection_id=None, voided=False,
                                runners=[runner])
    db = FakeDB()
    did = S._place_one(ev=ev, cs=cs, sel=sel, snapshot=snapshot, size=5.0,
                       price=75.0, target=5.0, minute=10, score_str="2 - 1",
                       mode="paper", commission=0.05, market=FakeMarket(), db=db,
                       now=NOW, requested_size=5.0,
                       params={"execution_mode": "auto"})
    assert did == 1
    assert not db.attivita("place_parziale")
    assert db.trades[0]["meta"]["size_remaining"] == 0.0


# ---------------------------------------------------------------------------
# R-J3 — il ref storico per-evento non collude fra le gambe di una partita
# ---------------------------------------------------------------------------
def _gamba(id_, phase, event_id="1.300"):
    return {"id": id_, "event_id": event_id, "market_id": "m1", "selection_id": 4,
           "side": "lay", "origin": "auto", "phase": phase, "closes_trade_id": None}


def test_r_j3_ref_storico_assente_per_gambe_con_fase():
    """Due gambe della STESSA partita (ht_cs, ft_cs): nessuna delle due porta
    piu' il ref storico per-evento fra i candidati — solo il proprio
    ``omega-t<id>``."""
    g1 = _gamba(11, "ht_cs")
    g2 = _gamba(12, "ft_cs")
    assert E.candidate_customer_refs(g1) == ["omega-t11"]
    assert E.candidate_customer_refs(g2) == ["omega-t12"]


def test_r_j3_ordine_storico_superstite_non_confonde_le_gambe():
    """FALSIFICAZIONE del reperto: un vecchio ordine Betfair con
    ``customer_order_ref='omega-1.300'`` (pre per-gamba) non deve confermare
    NE' la gamba ht_cs NE' la ft_cs — 'keep'/'error' per entrambe secondo
    l'eta', mai 'confirm' sul ref sbagliato."""
    g1 = {**_gamba(11, "ht_cs"), "price": 65.0, "placed_at": NOW.isoformat()}
    g2 = {**_gamba(12, "ft_cs"), "price": 70.0, "placed_at": NOW.isoformat()}
    ordine_storico = _ordine_corrente(customer_order_ref="omega-1.300",
                                      size_matched=2.0, size_remaining=0.0,
                                      status="EXECUTION_COMPLETE")
    d1 = E.reconcile_decision(g1, [ordine_storico], [], NOW.isoformat())
    d2 = E.reconcile_decision(g2, [ordine_storico], [], NOW.isoformat())
    assert d1["action"] != "confirm", d1
    assert d2["action"] != "confirm", d2


def test_r_j3_trade_senza_fase_ritrova_ancora_il_ref_storico():
    """Compatibilita': un trade v1 (senza ``phase``, engine 'single') per un
    evento con AL PIU' una gamba resta riconciliabile dal ref storico — non si
    e' rotto nulla per il motore vecchio."""
    g = {"id": 21, "event_id": "1.301", "market_id": "m1", "selection_id": 4,
        "side": "lay", "origin": "auto", "phase": None, "closes_trade_id": None,
        "price": 65.0, "placed_at": NOW.isoformat()}
    ordine = _ordine_corrente(customer_order_ref="omega-1.301", size_matched=5.0,
                              size_remaining=0.0, status="EXECUTION_COMPLETE")
    d = E.reconcile_decision(g, [ordine], [], NOW.isoformat())
    assert d["action"] == "confirm"
    assert d["size"] == 5.0
