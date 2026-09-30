"""IL P&L REALE DEL CONTO (ordine dell'utente, 30/09).

"IL PNL DEVE ESSERE REALE CON TUTTO QUELLO CHE FANNO I BOT E IO MANUALMENTE!
ANCHE SE REGOLO LE LORO OPERAZIONI!!!"

Caso vero del 30/09 (live): partita 36130526 FC Vsetin v Bohemians 1905, righe
``mike_trades`` 5087 (punta Under 3,5 5,00 @ 2,12), 5088 (banca 5,10 @ 2,08 mai
piazzata), 5089 (banca 1,00 @ 2,08 abbinata in parte, resto annullato), 5090
(banca Under 4,5 5,05 @ 1,48); alle 15:31 l'utente ha chiuso dal SITO con
ordini suoi. Prima Mike regolava SOLO i suoi ordini, col calcolo interno.

Finti: le righe sono quelle lette dal DB in sola lettura (id 5087-5090, chiavi
e tipi identici, ``event_id`` e mercati veri); gli ordini dell'UTENTE sono
quelli VERI dello specchio ``betfair_live_orders`` (sola lettura, source
'account', ``client_order_ref`` ``ext<bet>``): 445039002079 punta Over 3,5 4,34
@ 1,92, 445039002080 punta Over 3,5 0,09 @ 1,92 (chiesta a 1,91), 445039090782
punta Under 4,5 5,18 @ 1,44. Le scommesse regolate hanno la forma di
``omega_market._riga_regolata`` (``listClearedOrders`` normalizzato), i mercati
quella di ``service._RealMarket.list_account_cleared_markets``
(``groupBy=MARKET``). La partita alle 16:09 era al 39' (1 gol): il risultato
e' SUPPOSTO (3 gol, e 5 gol nel caso a parte); profit e commissioni sono
calcolati a mano con la regola di Betfair, nessuna chiamata a Betfair dai test.

Conti a mano, 3 gol (Under 3,5 e Under 4,5 vincenti; commissione del 5 % sul
netto vincente del MERCATO del CONTO, al centesimo):
  OU35 Mike: +5,60 (punta 5 @ 2,12) -1,08 (banca 1,00 @ 2,08)  = +4,52
  OU45 Mike: -2,42 (banca 5,05 @ 1,48: 5,05 x 0,48 = 2,424)
  OU35 utente: -4,34 -0,09 (punte Over perdenti)                = -4,43
  OU45 utente: +2,28 (punta Under 4,5 5,18 x 0,44 = 2,279)
  * solo Mike:   OU35 commissione 0,23 -> Mike +1,87 (= calcolo interno)
  * con l'utente: OU35 del conto +0,09 -> commissione 0,00 (0,0045); OU45 -0,14
    -> 0 -> Mike +2,10, utente -2,15, partita (conto) -0,05.
    Il calcolo interno di Mike (+1,87) DIFFERISCE: vince Betfair, lo dice il
    diario (la chiusura dell'utente sullo stesso mercato azzera la commissione).
"""
from __future__ import annotations

import copy
from datetime import timedelta
from typing import Any, Dict, List

import pytest

from Betfair.mike import engine as E
from Betfair.mike import regolato_conto as RC
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, run

EID = "36130526"
M35 = "1.263075928"
M45 = "1.263075925"
U35, O35, U45, O45 = 1222344, 1222345, 1222347, 1222346
SEL = {"OU35|UNDER": U35, "OU35|OVER": O35, "OU45|UNDER": U45, "OU45|OVER": O45}
BET_UTENTE = "445039002079"


@pytest.fixture(autouse=True)
def _nessun_db_vero(monkeypatch):
    monkeypatch.setattr(S, "_freno_aperture_rest", lambda: None)
    monkeypatch.setattr(S.X, "_freno_aperture", lambda: None)

    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)
    S._CONTO_LETTO_A.clear()


# --- le righe VERE (DB, sola lettura, 30/09 pomeriggio) ---------------------
RIGHE_VERE: List[Dict[str, Any]] = [
    {"id": 5087, "event_id": EID, "event_name": "FC Vsetin v Bohemians 1905", "sport": "calcio",
     "strategy": "under_entry", "role": "under_entry", "cycle_no": 0, "persistence": "LAPSE",
     "market_id": M35, "market_type": "OVER_UNDER_35", "selection_id": U35,
     "selection_name": "Under 3.5 Goals", "side": "back", "mode": "live", "price": 2.12,
     "size": 5.0, "liability": 5.0, "commission": 0.05, "minute_at_entry": None,
     "score_at_entry": None, "status": "open", "pnl": 0.0, "bet_id": "445036594830",
     "placed_at": "2026-09-30T13:05:26.139189+00:00", "settled_at": None, "origin": "auto",
     "closes_trade_id": None, "signal_key": "under_entry-0-2",
     "meta": {"fill": "live_rest:EXECUTION_COMPLETE", "final": False, "phase": "open",
              "leg_ref": "under_entry-0-2"},
     "size_requested": 5.0, "size_matched": 5.0, "size_remaining": 0.0,
     "avg_price_matched": 2.12, "betfair_updated_at": "2026-09-30T13:05:26+00:00",
     "pnl_betfair": None, "commissione_betfair": None, "pnl_betfair_settled_at": None},
    {"id": 5088, "event_id": EID, "event_name": "FC Vsetin v Bohemians 1905", "sport": "calcio",
     "strategy": "under_green", "role": "under_green", "cycle_no": 0, "persistence": "LAPSE",
     "market_id": M35, "market_type": "OVER_UNDER_35", "selection_id": U35,
     "selection_name": "Under 3.5 Goals", "side": "lay", "mode": "live", "price": 2.08,
     "size": 5.1, "liability": 5.51, "commission": 0.05, "minute_at_entry": None,
     "score_at_entry": None, "status": "error", "pnl": 0.0, "bet_id": "445036597047",
     "placed_at": "2026-09-30T13:05:27.839881+00:00", "settled_at": None, "origin": "auto",
     "closes_trade_id": 5087, "signal_key": "under_green-0-3",
     "meta": {"fill": "live_resting_piazzato", "final": False, "phase": "cancelled",
              "reason": "reconciled_not_placed", "leg_ref": "under_green-0-3",
              "exit_kind": "greenup", "closes_ref": "under_entry-0-2", "reconciled": True,
              "exit_reason": "under_green"},
     "size_requested": 5.1, "size_matched": 0.0, "size_remaining": 5.1,
     "avg_price_matched": None, "betfair_updated_at": "2026-09-30T13:05:27+00:00",
     "pnl_betfair": None, "commissione_betfair": None, "pnl_betfair_settled_at": None},
    {"id": 5089, "event_id": EID, "event_name": "FC Vsetin v Bohemians 1905", "sport": "calcio",
     "strategy": "ko_green", "role": "ko_green", "cycle_no": 0, "persistence": "LAPSE",
     "market_id": M35, "market_type": "OVER_UNDER_35", "selection_id": U35,
     "selection_name": "Under 3.5 Goals", "side": "lay", "mode": "live", "price": 2.08,
     "size": 1.0, "liability": 5.51, "commission": 0.05, "minute_at_entry": 0,
     "score_at_entry": "0-0", "status": "open", "pnl": 0.0, "bet_id": "445038902107",
     "placed_at": "2026-09-30T13:30:03.827439+00:00", "settled_at": None, "origin": "auto",
     "closes_trade_id": 5087, "signal_key": "ko_green-0-4",
     "meta": {"fill": "live_resting", "final": False, "phase": "cancelled",
              "reason": "cancelled_by_engine", "leg_ref": "ko_green-0-4", "exit_kind": "greenup",
              "closes_ref": "under_entry-0-2", "exit_reason": "ko_green",
              "esito_ordine": "ritirato_da_noi"},
     "size_requested": 5.1, "size_matched": 1.0, "size_remaining": 0.0,
     "avg_price_matched": 2.08, "betfair_updated_at": "2026-09-30T13:30:30+00:00",
     "pnl_betfair": None, "commissione_betfair": None, "pnl_betfair_settled_at": None},
    {"id": 5090, "event_id": EID, "event_name": "FC Vsetin v Bohemians 1905", "sport": "calcio",
     "strategy": "over_cover", "role": "over_cover", "cycle_no": 0, "persistence": "LAPSE",
     "market_id": M45, "market_type": "OVER_UNDER_45", "selection_id": U45,
     "selection_name": "Under 4.5 Goals", "side": "lay", "mode": "live", "price": 1.48,
     "size": 5.05, "liability": 2.42, "commission": 0.05, "minute_at_entry": 0,
     "score_at_entry": "0-0", "status": "open", "pnl": 0.0, "bet_id": "445038952708",
     "placed_at": "2026-09-30T13:30:35.117123+00:00", "settled_at": None, "origin": "auto",
     "closes_trade_id": None, "signal_key": "over_cover-0-5",
     "meta": {"fill": "live_rest:EXECUTION_COMPLETE", "final": False, "phase": "open",
              "leg_ref": "over_cover-0-5", "cover_form": "lay_under45"},
     "size_requested": 5.05, "size_matched": 5.05, "size_remaining": 0.0,
     "avg_price_matched": 1.48, "betfair_updated_at": "2026-09-30T13:30:35+00:00",
     "pnl_betfair": None, "commissione_betfair": None, "pnl_betfair_settled_at": None},
]


def _gambe() -> List[E.Leg]:
    def g(ref, role, market, sel, side, size, matched, prezzo, status, closes=None):
        return E.Leg(role=role, market=market, selection=sel, side=side, price=prezzo,
                     size=size, matched=matched, avg_price=prezzo if matched > 0 else None,
                     ref=ref, status=status, closes_ref=closes)
    return [
        g("under_entry-0-2", "under_entry", E.MARKET_OU35, E.SEL_UNDER, "back", 5.0, 5.0, 2.12, "open"),
        g("under_green-0-3", "under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 5.1, 0.0, 2.08,
          "cancelled", "under_entry-0-2"),
        g("ko_green-0-4", "ko_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 5.1, 1.0, 2.08,
          "cancelled", "under_entry-0-2"),
        g("over_cover-0-5", "over_cover", E.MARKET_OU45, E.SEL_UNDER, "lay", 5.05, 5.05, 1.48, "open"),
    ]


def _libro(mid, vincente, sids):
    """Come ``omega_market.read_book`` su un mercato CHIUSO."""
    return {"market_id": mid, "status": "CLOSED", "inplay": False,
            "runners": [{"selection_id": s, "status": "WINNER" if s == vincente else "LOSER",
                         "name": "?", "lay_price": None, "lay_size": 0.0, "back_price": None,
                         "back_size": 0.0, "lay_ladder": []} for s in sids]}


def _regolata(bet, mid, sid, side, size, prezzo, profit, outcome, ref):
    """Una scommessa regolata come ``omega_market._riga_regolata``."""
    return {"bet_id": bet, "market_id": mid, "selection_id": sid, "side": side,
            "size_settled": size, "size_matched": size, "size_remaining": 0.0,
            "price": prezzo, "avg_price_matched": prezzo, "profit": profit,
            "commission": None, "bet_outcome": outcome, "customer_order_ref": ref}


REGOLATE_MIKE = [
    _regolata("445036594830", M35, U35, "back", 5.0, 2.12, 5.6, "WON", "mike-t5087"),
    _regolata("445038902107", M35, U35, "lay", 1.0, 2.08, -1.08, "LOST", "ko_green-0-4"),
    _regolata("445038952708", M45, U45, "lay", 5.05, 1.48, -2.42, "LOST", "mike-t5090"),
]
#: gli ordini VERI dell'utente dal sito (``betfair_live_orders``, source 'account')
REGOLATE_UTENTE = [
    _regolata(BET_UTENTE, M35, O35, "back", 4.34, 1.92, -4.34, "LOST", None),
    _regolata("445039002080", M35, O35, "back", 0.09, 1.92, -0.09, "LOST", None),
    _regolata("445039090782", M45, U45, "back", 5.18, 1.44, 2.28, "WON", None),
]
REGOLATA_UTENTE = REGOLATE_UTENTE[0]


def _gruppi_di(regolate: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """``listClearedOrders`` per MERCATO, calcolato come Betfair: lordo del
    CONTO sul mercato e commissione del 5 % sul netto vincente, al centesimo."""
    out = []
    for mid in (M35, M45):
        lordo = round(sum(o["profit"] for o in regolate if o["market_id"] == mid), 2)
        out.append({"market_id": mid, "profit": lordo,
                    "commission": round(0.05 * lordo, 2) if lordo > 0 else 0.0,
                    "bet_count": sum(1 for o in regolate if o["market_id"] == mid),
                    "settled_date": "2026-09-30T15:55:00.000Z"})
    return out


def _gruppi(con_utente: bool) -> List[Dict[str, Any]]:
    return _gruppi_di(REGOLATE_MIKE + (REGOLATE_UTENTE if con_utente else []))


class MercatoConto(FakeMarket):
    """Lo sportello di produzione (``service._RealMarket``) con le due letture
    del regolato del conto."""

    def __init__(self, regolate, gruppi):
        super().__init__()
        self.regolate = list(regolate)
        self.gruppi = list(gruppi)
        self.letture_b: List[str] = []
        self.letture_m: List[List[str]] = []
        self.guasto = False
        # 3 gol: Under 3,5 vince, Under 4,5 vince
        self.books = {M35: _libro(M35, U35, (U35, O35)), M45: _libro(M45, U45, (U45, O45))}

    def list_account_cleared_bets(self, market_ids, stato="SETTLED"):
        self.letture_b.append((tuple(market_ids), stato))
        if self.guasto:
            raise RuntimeError("Betfair: timeout")
        if stato != "SETTLED":
            return []
        return [dict(o) for o in self.regolate if o["market_id"] in set(market_ids)]

    def chiamate(self):
        return len(self.letture_b) + len(self.letture_m)

    def list_account_cleared_markets(self, market_ids):
        self.letture_m.append(list(market_ids))
        return [dict(g) for g in self.gruppi if g["market_id"] in set(market_ids)]


def _scenario(regolate, gruppi, mode="live"):
    import dataclasses

    db = FakeDB(mode=mode, params={"stake": 5})
    db.events[EID] = {
        "event_id": EID, "event_name": "FC Vsetin v Bohemians 1905", "state": "LIVE_COVERED",
        "cycle_no": 0, "entry_price_initial": 2.12,
        "markets": {"OU35": {"market_id": M35}, "OU45": {"market_id": M45}},
        "positions": [dataclasses.asdict(l) for l in _gambe()], "dossier": {}, "live": {},
        "mode": mode, "ko_at": (NOW - timedelta(hours=4)).isoformat(),
        "ctx": {"seen_inplay": True, "selections": SEL, "chiuso_dall_utente": True,
                "no_reentry": True, "reentry_done": True}}
    righe = copy.deepcopy(RIGHE_VERE)
    for r in righe:
        r["mode"] = mode
    db.trades = righe
    db._id = 6000
    return db, MercatoConto(regolate, gruppi)


def _ev(db):
    return db.events[EID]


def _riga(db, key):
    return next((t for t in db.trades if t.get("signal_key") == key), None)


# ===========================================================================
def test_solo_ordini_di_mike_regolato_uguale_interno_nessuna_differenza():
    db, mk = _scenario(REGOLATE_MIKE, _gruppi(False))
    run(db, mk, NOW, [])
    ev = _ev(db)
    assert ev["state"] == "SETTLED"
    assert ev["settled_pnl"] == pytest.approx(1.87, abs=1e-9)
    assert _riga(db, "under_entry-0-2")["pnl"] == pytest.approx(5.37)   # 5,60 - 0,23
    assert _riga(db, "ko_green-0-4")["pnl"] == pytest.approx(-1.08)
    assert _riga(db, "over_cover-0-5")["pnl"] == pytest.approx(-2.42)
    for key in ("under_entry-0-2", "ko_green-0-4", "over_cover-0-5"):
        r = _riga(db, key)
        assert r["meta"]["pnl_fonte"] == "betfair"
        assert r["pnl_betfair"] == r["pnl"]
    assert "pnl_differenza_betfair" not in db.kinds()
    assert not any(RC.e_riga_utente(t) for t in db.trades)
    settled = next(p for k, p, _e in db.activity if k == "settled")
    assert settled["pnl_fonte"] == "betfair" and settled["pnl_utente"] == 0.0
    assert ev["ctx"]["pnl_conto"]["conto"] == pytest.approx(1.87)
    # H4: la somma delle righe fa il P&L della partita
    assert round(sum(float(t.get("pnl") or 0) for t in db.trades), 2) == pytest.approx(1.87)


def test_ordine_dell_utente_entra_nel_conto_della_partita_e_vince_betfair():
    db, mk = _scenario(REGOLATE_MIKE + REGOLATE_UTENTE, _gruppi(True))
    run(db, mk, NOW, [])
    ev = _ev(db)
    assert ev["state"] == "SETTLED"
    # il P&L della partita = TUTTO il conto sui mercati di Mike
    assert ev["settled_pnl"] == pytest.approx(-0.05, abs=1e-9)
    u = _riga(db, "utente-" + BET_UTENTE)
    assert u is not None, "la riga dell'utente non e' stata scritta"
    # chiavi e tipi delle righe vere
    assert set(RIGHE_VERE[0]) - set(u) <= {"id", "placed_at", "betfair_updated_at"}
    assert (u["role"], u["strategy"], u["origin"], u["mode"], u["side"]) == \
        ("utente", "manual_close", "manual", "live", "back")
    assert u["bet_id"] == BET_UTENTE and u["status"] == "lost"
    assert u["pnl"] == pytest.approx(-4.34) and u["pnl_betfair"] == pytest.approx(-4.34)
    assert u["closes_trade_id"] == 5087          # dentro la posizione, non un ciclo nuovo
    assert u["market_type"] == "OVER_UNDER_35" and u["selection_name"] == "Over 3.5 Goals"
    assert u["meta"]["fonte"] == "utente" and u["meta"]["pnl_fonte"] == "betfair"
    u45 = _riga(db, "utente-445039090782")
    assert (u45["status"], u45["pnl"], u45["closes_trade_id"], u45["selection_name"]) == \
        ("won", pytest.approx(2.28), 5090, "Under 4.5 Goals")
    assert sum(1 for t in db.trades if RC.e_riga_utente(t)) == 3
    # Mike: commissione ZERO sul mercato del conto (+0,09 -> 0,0045): +2,10, non +1,87
    assert _riga(db, "under_entry-0-2")["pnl"] == pytest.approx(5.6)
    assert _riga(db, "under_entry-0-2")["meta"]["pnl_interno"] == pytest.approx(5.37)
    diff = next(p for k, p, _e in db.activity if k == "pnl_differenza_betfair")
    assert diff["interno_mike"] == pytest.approx(1.87) and diff["betfair_mike"] == pytest.approx(2.1)
    assert diff["vince"] == "betfair"
    assert "ordini_utente_nel_conto" in db.kinds()
    pc = ev["ctx"]["pnl_conto"]
    assert (pc["mike"], pc["utente"], pc["conto"], pc["ordini_utente"]) == \
        (pytest.approx(2.1), pytest.approx(-2.15), pytest.approx(-0.05), 3)
    assert round(sum(float(t.get("pnl") or 0) for t in db.trades), 2) == pytest.approx(-0.05)


def test_cinque_gol_il_conto_e_quasi_piatto_come_la_chiusura_dell_utente():
    """Stessi ordini, 5 gol (Over 3,5 e Over 4,5 vincenti): Mike -4,00 +5,05 =
    +1,05 (interno +0,80: commissione 0,25 sul solo 4,5 di Mike), utente
    +3,99 +0,08 -5,18 = -1,11, conto -0,06."""
    def rov(o, profit, esito):
        return {**o, "profit": profit, "bet_outcome": esito}
    mike = [rov(REGOLATE_MIKE[0], -5.0, "LOST"), rov(REGOLATE_MIKE[1], 1.0, "WON"),
            rov(REGOLATE_MIKE[2], 5.05, "WON")]
    utente = [rov(REGOLATE_UTENTE[0], 3.99, "WON"), rov(REGOLATE_UTENTE[1], 0.08, "WON"),
              rov(REGOLATE_UTENTE[2], -5.18, "LOST")]
    db, mk = _scenario(mike + utente, _gruppi_di(mike + utente))
    mk.books = {M35: _libro(M35, O35, (U35, O35)), M45: _libro(M45, O45, (U45, O45))}
    run(db, mk, NOW, [])
    ev = _ev(db)
    assert ev["state"] == "SETTLED"
    pc = ev["ctx"]["pnl_conto"]
    assert (pc["mike"], pc["utente"], pc["conto"], pc["interno_mike"]) == \
        (pytest.approx(1.05), pytest.approx(-1.11), pytest.approx(-0.06), pytest.approx(0.8))
    assert ev["settled_pnl"] == pytest.approx(-0.06)


def test_regolato_non_ancora_disponibile_si_aspetta_in_settling_poi_si_regola():
    db, mk = _scenario([], [])
    run(db, mk, NOW, [])
    ev = _ev(db)
    assert ev["state"] == "SETTLING", "regolamento cieco: Betfair non aveva ancora regolato"
    assert {t["status"] for t in db.trades if t["id"] != 5088} == {"open"}
    att = next(p for k, p, _e in db.activity if k == "attesa_regolato_betfair")
    assert set(att["mancano"]) == {"445036594830", "445038902107", "445038952708"}
    n = len(mk.letture_b)
    # entro il minuto nessuna nuova lettura REST
    run(db, mk, NOW + timedelta(seconds=40), [])
    assert len(mk.letture_b) == n and _ev(db)["state"] == "SETTLING"
    # Betfair regola: al giro dopo l'attesa si regola coi suoi numeri
    mk.regolate = REGOLATE_MIKE + REGOLATE_UTENTE
    mk.gruppi = _gruppi(True)
    run(db, mk, NOW + timedelta(seconds=130), [])
    assert _ev(db)["state"] == "SETTLED"
    assert _ev(db)["settled_pnl"] == pytest.approx(-0.05)


def test_commissione_del_mercato_non_letta_si_aspetta():
    db, mk = _scenario(REGOLATE_MIKE, [g for g in _gruppi(False) if g["market_id"] != M35])
    run(db, mk, NOW, [])
    assert _ev(db)["state"] == "SETTLING"
    att = next(p for k, p, _e in db.activity if k == "attesa_regolato_betfair")
    assert att["mancano"] == [M35]


def test_lettura_fallita_si_aspetta_e_non_si_regola():
    db, mk = _scenario(REGOLATE_MIKE, _gruppi(False))
    mk.guasto = True
    run(db, mk, NOW, [])
    assert _ev(db)["state"] == "SETTLING"
    assert {t["status"] for t in db.trades if t["id"] != 5088} == {"open"}


def test_paper_regola_col_calcolo_interno_e_non_legge_il_conto():
    db, mk = _scenario(REGOLATE_MIKE + REGOLATE_UTENTE, _gruppi(True), mode="paper")
    run(db, mk, NOW, [])
    ev = _ev(db)
    assert ev["state"] == "SETTLED"
    assert mk.letture_b == [] and mk.letture_m == []
    assert ev["settled_pnl"] == pytest.approx(1.87)
    assert not any(RC.e_riga_utente(t) for t in db.trades)
    assert "pnl_fonte" not in (_riga(db, "under_entry-0-2")["meta"] or {})
    assert "pnl_conto" not in (ev.get("ctx") or {})


def test_ordine_di_un_altro_bot_non_e_dell_utente():
    altro = _regolata("445042222222", M45, U45, "back", 2.0, 1.3, 0.6, "WON", "omega-t77")
    gruppi = _gruppi(False)
    gruppi[1] = {**gruppi[1], "profit": round(-2.42 + 0.6, 2)}
    db, mk = _scenario(REGOLATE_MIKE + [altro], gruppi)
    run(db, mk, NOW, [])
    assert _ev(db)["state"] == "SETTLED"
    assert _riga(db, "utente-445042222222") is None
    assert _ev(db)["ctx"]["pnl_conto"]["altri_bot_esclusi"] == 1
    assert _ev(db)["settled_pnl"] == pytest.approx(1.87)


def test_riregolare_non_duplica_la_riga_utente():
    db, mk = _scenario(REGOLATE_MIKE + REGOLATE_UTENTE, _gruppi(True))
    run(db, mk, NOW, [])
    ctx = S._ctx_from_row(_ev(db), db)
    conto = RC.componi_regolato(db.trades, mk.regolate, mk.gruppi, [M35, M45])
    assert conto["pronto"]
    S._settle_trades(db, EID, ctx, {"per_leg": []}, {}, conto=conto, extra={})
    assert sum(1 for t in db.trades if t.get("signal_key") == "utente-" + BET_UTENTE) == 1


def test_una_riga_utente_non_diventa_mai_una_gamba_di_mike():
    u = RC.riga_utente({"bet_id": BET_UTENTE, "market_id": M35, "selection_id": O35,
                        "side": "back", "price": 1.92, "size": 4.34, "lordo": -4.34,
                        "commissione": 0.0, "netto": -4.34, "esito": "lost"},
                       ev={"event_id": EID, "event_name": "x"}, righe=copy.deepcopy(RIGHE_VERE),
                       commission_rate=0.05, settled_at=NOW.isoformat(),
                       nomi=RC.nomi_da_selezioni(SEL))
    u = {**u, "id": 7000, "status": "pending"}
    # la riga dice abbastanza per diventare una gamba (mercato, selezione,
    # lato): e' la guardia che lo impedisce, non la mancanza di dati
    assert u["selection_name"] == "Over 3.5 Goals" and u["market_type"] == "OVER_UNDER_35"
    assert S._gamba_dalla_riga({**u, "role": "under_entry", "meta": {},
                                "signal_key": "under_entry-9-9"}, None) is not None
    assert S._gamba_dalla_riga(u, None) is None


def test_scommessa_di_mike_creduta_non_eseguita_la_regola_betfair():
    """Riga 5088 'error' (``reconciled_not_placed``) ma Betfair dice che e'
    stata abbinata e regolata: vince Betfair, la riga prende esito e P&L."""
    abbinata = _regolata("445036597047", M35, U35, "lay", 5.1, 2.08, -5.51, "LOST", "under_green-0-3")
    gruppi = _gruppi(False)
    gruppi[0] = {**gruppi[0], "profit": round(4.52 - 5.51, 2), "commission": 0.0}
    db, mk = _scenario(REGOLATE_MIKE + [abbinata], gruppi)
    run(db, mk, NOW, [])
    r = _riga(db, "under_green-0-3")
    assert r["status"] == "lost" and r["pnl"] == pytest.approx(-5.51)
    assert r["meta"]["corretto_da_betfair"] is True
    assert _ev(db)["settled_pnl"] == pytest.approx(round(5.6 - 1.08 - 2.42 - 5.51, 2))
    assert "pnl_differenza_betfair" in db.kinds()


def test_componi_non_pronto_senza_le_scommesse_di_mike():
    esito = RC.componi_regolato(copy.deepcopy(RIGHE_VERE), REGOLATE_MIKE[:2], _gruppi(False),
                                [M35, M45])
    assert esito["pronto"] is False and esito["mancano"] == ["445038952708"]


def test_il_runner_non_attribuisce_a_mike_l_ordine_dell_utente():
    """``reconcile_worker._proprietari``: la riga 'utente' in ``mike_trades``
    non fa diventare "mike" l'ordine dell'utente (resta "manuale_sito")."""
    from types import SimpleNamespace

    from Betfair.stream import reconcile_worker as RW

    tabelle = {"mike_trades": [{"id": 7001, "bet_id": BET_UTENTE, "role": "utente"},
                               {"id": 5087, "bet_id": "445036594830", "role": "under_entry"}]}

    class Q:
        def __init__(self, nome):
            self.nome = nome
            self.ids: List[str] = []

        def select(self, *_a):
            return self

        def eq(self, *_a):
            return self

        def in_(self, _col, ids):
            self.ids = list(ids)
            return self

        def execute(self):
            righe = [r for r in tabelle.get(self.nome, []) if str(r.get("bet_id")) in self.ids]
            return SimpleNamespace(data=righe)

    class Sb:
        def table(self, nome):
            return Q(nome)

    RW._PROPRIETARIO_BET.clear()
    ordini = [SimpleNamespace(bet_id=BET_UTENTE, customer_order_ref=None,
                              customer_strategy_ref=None, event_type_id="1"),
              SimpleNamespace(bet_id="445036594830", customer_order_ref="mike-t5087",
                              customer_strategy_ref="mike", event_type_id="1")]
    RW._proprietari(Sb(), ordini, "2026-09-30")
    assert RW._PROPRIETARIO_BET[BET_UTENTE] is None
    assert RW._PROPRIETARIO_BET["445036594830"][0] == "mike_trades"
    RW._PROPRIETARIO_BET.clear()


# ===========================================================================
# LA RIGA "UTENTE" NATA DAL SEGNALE IN TEMPO REALE (topic ``conto``)
# ===========================================================================
def _corrente(bet, mid, sid, side, matched, prezzo, ref=None, remaining=0.0):
    """Un ordine del messaggio ``conto`` (camelCase di ``listCurrentOrders``),
    normalizzato con la funzione VERA di ``omega_market``."""
    from Betfair.omega import omega_market as OM

    return OM._riga_corrente({
        "betId": bet, "marketId": mid, "selectionId": sid, "side": side, "handicap": 0.0,
        "status": "EXECUTION_COMPLETE" if remaining <= 0 else "EXECUTABLE",
        "orderType": "LIMIT", "persistenceType": "LAPSE", "sizeMatched": matched,
        "sizeRemaining": remaining, "sizeCancelled": 0.0, "sizeLapsed": 0.0, "sizeVoided": 0.0,
        "averagePriceMatched": prezzo, "priceSize": {"price": prezzo, "size": matched + remaining},
        "customerOrderRef": ref, "placedDate": "2026-09-30T13:32:01.000Z"})


def test_riga_utente_in_corso_dal_segnale_e_poi_regolata_senza_doppioni():
    from Betfair.mike import db as MDB

    db, mk = _scenario(REGOLATE_MIKE + REGOLATE_UTENTE, _gruppi(True))
    ev = db.events[EID]
    ctx = S._ctx_from_row(ev, db)
    extra = dict(ev["ctx"])
    o = _corrente("445039090782", M45, U45, "BACK", 5.18, 1.44)
    assert S.scrivi_riga_utente_in_corso(db=db, ev=ev, ctx=ctx, extra=extra, params={},
                                         ordine=o, strategy_ref=None) is True
    u = _riga(db, "utente-445039090782")
    assert (u["status"], u["pnl"], u["closes_trade_id"], u["meta"]["pnl_fonte"]) == \
        ("open", 0.0, 5090, "in_corso")
    assert u["selection_name"] == "Under 4.5 Goals" and u["side"] == "back"
    # ripetuto: nessun doppione, nessuna scrittura
    assert S.scrivi_riga_utente_in_corso(db=db, ev=ev, ctx=ctx, extra=extra, params={},
                                         ordine=o) is False
    # non e' una posizione APERTA del bot (e' una chiusura): non conta fra le aperte
    agg = MDB.aggregate_rows(db.trades)
    assert agg["open_count"] == 2          # 5087 e 5090 del bot, non la riga utente
    # il regolamento AGGIORNA la stessa riga coi numeri di Betfair
    run(db, mk, NOW, [])
    assert sum(1 for t in db.trades if t.get("signal_key") == "utente-445039090782") == 1
    u = _riga(db, "utente-445039090782")
    assert (u["status"], u["pnl"], u["meta"]["pnl_fonte"]) == ("won", pytest.approx(2.28), "betfair")
    assert _ev(db)["settled_pnl"] == pytest.approx(-0.05)


def test_il_segnale_non_scrive_righe_utente_per_ordini_di_mike_o_di_altri_bot():
    db, _mk = _scenario(REGOLATE_MIKE, _gruppi(False))
    ev = db.events[EID]
    ctx = S._ctx_from_row(ev, db)
    di_mike = _corrente("445038952708", M45, U45, "LAY", 5.05, 1.48, ref="mike-t5090")
    altro = _corrente("445042222222", M45, U45, "BACK", 2.0, 1.3, ref="omega-t77")
    app_bot = _corrente("445042222223", M45, U45, "BACK", 2.0, 1.3, ref="x1")
    non_abbinato = _corrente("445042222224", M35, O35, "BACK", 0.0, 1.9, remaining=3.0)
    for o, sref in ((di_mike, "mike"), (altro, None), (app_bot, "scalper"), (non_abbinato, None)):
        assert S.scrivi_riga_utente_in_corso(db=db, ev=ev, ctx=ctx, extra={}, params={},
                                             ordine=o, strategy_ref=sref) is False
    assert not any(RC.e_riga_utente(t) for t in db.trades)
    # paper: mai
    ev_p = {**ev, "mode": "paper"}
    assert S.scrivi_riga_utente_in_corso(
        db=db, ev=ev_p, ctx=ctx, extra={}, params={},
        ordine=_corrente("445039090782", M45, U45, "BACK", 5.18, 1.44)) is False


# ===========================================================================
# VINCOLO DELL'UTENTE (30/09): "non voglio spammare i server Betfair"
# ===========================================================================
def test_una_lettura_per_partita_due_chiamate_rest():
    """Regolato gia' disponibile: DUE chiamate in tutto (le scommesse SETTLED
    dei due mercati insieme + la commissione per mercato), e nessuna dopo."""
    db, mk = _scenario(REGOLATE_MIKE + REGOLATE_UTENTE, _gruppi(True))
    run(db, mk, NOW, [])
    assert _ev(db)["state"] == "SETTLED"
    assert mk.letture_b == [((M35, M45), "SETTLED")] and mk.letture_m == [[M35, M45]]
    assert _ev(db)["ctx"]["pnl_conto"]["chiamate_rest"] == 2
    run(db, mk, NOW + timedelta(minutes=10), [])
    assert mk.chiamate() == 2, "partita regolata: nessuna chiamata in piu'"


def test_attesa_lenta_e_con_tetto_poi_stima_dichiarata(monkeypatch):
    """Betfair non regola mai: le letture si diradano (1, 2, 4, 8, 15 minuti)
    e dopo il TETTO si regola col calcolo interno DICHIARATO stima."""
    monkeypatch.setattr(S, "_CONTO_TENTATIVI_MAX", 4)
    db, mk = _scenario([], [])
    t = NOW
    istanti = []
    for _ in range(40):
        prima = mk.chiamate()
        run(db, mk, t, [])
        if mk.chiamate() > prima:
            istanti.append((t - NOW).total_seconds())
        if _ev(db)["state"] == "SETTLED":
            break
        t += timedelta(seconds=30)
    assert _ev(db)["state"] == "SETTLED"
    assert len(istanti) == 4, istanti                    # il tetto
    passi = [b - a for a, b in zip(istanti, istanti[1:])]
    assert passi[0] >= 60 and passi[1] >= 120 and passi[2] >= 240, passi
    # tentativi 1-2: solo SETTLED (Betfair non ha regolato niente); 3-4: anche VOIDED
    assert mk.chiamate() == 1 + 1 + 2 + 2
    assert _ev(db)["ctx"]["pnl_conto"]["fonte"] == "stima"
    assert _riga(db, "under_entry-0-2")["meta"]["pnl_fonte"] == "stima"
    ult = [p for k, p, _e in db.activity if k == "attesa_regolato_betfair"][-1]
    assert ult["tetto"] is True and ult["critical"] is True


def test_il_banco_parla_come_la_produzione_sulle_regolate():
    """``MercatoFlumine.list_account_cleared_bets`` ha le chiavi di
    ``omega_market._riga_regolata`` (difetto 27 del catalogo)."""
    from pathlib import Path

    from Betfair.omega import omega_market as OM

    vero = OM._riga_regolata({"betId": "1", "marketId": "1.2", "selectionId": 3, "side": "LAY",
                              "sizeSettled": 2.0, "priceMatched": 2.1, "profit": -2.2,
                              "betOutcome": "LOST", "customerOrderRef": None})
    assert set(vero) == {"bet_id", "market_id", "selection_id", "side", "size_settled",
                         "size_matched", "size_remaining", "price", "avg_price_matched",
                         "profit", "commission", "bet_outcome", "customer_order_ref"}
    # il sorgente del banco letto dal file (importarlo costa flumine: 20 s)
    testo = (Path(__file__).resolve().parents[2] / "stream" / "backtest"
             / "banco_comune.py").read_text(encoding="utf-8")
    ini = testo.index("    def list_account_cleared_bets(")
    src = testo[ini:testo.index("\n    def ", ini + 10)]
    for k in vero:
        assert f'"{k}"' in src, f"chiave {k} assente dal banco"
