"""P4 BLOCCO 4 (29/09) - i test che mancavano, trovati dalle mutazioni del
coordinatore (W4c, W5b, W11, W13, W14). Il codice era gia' giusto: qui si prova
che, se lo si rompe in quei punti, qualcosa diventa rosso.

Finti con le chiavi vere: righe di `mike_trades` (FakeDB), ordini come
`omega_market` (snake_case), il runner finto sul protocollo vero del canale
(`runner_finto`), la posizione di conto come `_RealMarket.list_account_*`.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_p4_conti_dati_2026_09_29 import (  # noqa: F401
    KO, MercatoOrdini, _ctx_con_uscita, _evento, _giro, _ingresso,
    _libro_illeggibile_da_ore, _pulito, _riga, ordine)
from Betfair.mike.tests.test_mike_service import NOW, FakeDB


# ===========================================================================
# W4c - snapshot non costruibile: gli ordini si seguono lo stesso
# ===========================================================================
def test_snapshot_non_costruibile_la_lay_appoggiata_si_segue_lo_stesso():
    db = FakeDB(mode="live")
    ctx = _ctx_con_uscita()
    _riga(db, ctx.legs[0], status="open", bet_id="B0")
    _riga(db, ctx.legs[1], status="pending")
    p = payload(ko=KO, inplay=True, minute=30, sh=0, sa=0)
    p["open_date"] = None                     # niente calcio d'inizio: snapshot impossibile
    mk = MercatoOrdini([ordine(abbinato=10.14, residuo=0.0, stato="EXECUTION_COMPLETE")])
    ev = _evento(ctx)
    _giro(db, mk, ev, row(p))
    assert any(k == "feed_line_missing" and pl.get("reason") == "snapshot_non_costruibile"
               for k, pl, _e in db.activity)
    assert mk.letture >= 1, "la lay appoggiata non e' stata seguita"
    uscita = [x for x in ev["positions"] if x["ref"] == "ko_green-0-3"][0]
    assert uscita["status"] == "open" and uscita["matched"] == pytest.approx(10.14)


# ===========================================================================
# W5b - ramo «risultato indipendente»: righe non scritte = si ritenta
# ===========================================================================
class DbScritturaRotta(FakeDB):
    """La scrittura del regolamento (update con `pnl`) fallisce, come un
    PostgREST in timeout; tutto il resto funziona."""

    def update_trade(self, trade_id, **fields):
        if "pnl" in fields:
            raise RuntimeError("The read operation timed out")
        return super().update_trade(trade_id, **fields)


def test_righe_non_scritte_la_partita_non_diventa_settled_e_si_ritenta():
    ingresso = _ingresso()
    ingresso.archived = True
    green = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                  price=1.50, size=10.0, matched=10.0, avg_price=1.50, ref="under_green-0-2",
                  status="open", archived=True, closes_ref="under_entry-0-1")
    ctx = E.MatchCtx(state="WATCH", legs=[ingresso, green], cycle_no=1)
    db = DbScritturaRotta(mode="live")
    _riga(db, ingresso, status="open", bet_id="B0")
    _riga(db, green, status="open", bet_id="B1")
    ev, r = _libro_illeggibile_da_ore(ctx, db)
    stati = []
    for i in range(S._SETTLE_ROWS_MAX_TRIES):
        _giro(db, MercatoOrdini([]), ev, r, ora=NOW + timedelta(minutes=i))
        stati.append(ev["state"])
    # i primi tentativi: mai SETTLED con righe non scritte, si ritenta
    assert stati[:-1] == ["SETTLING"] * (S._SETTLE_ROWS_MAX_TRIES - 1), stati
    retry = [p for k, p, _e in db.activity if k == "error" and p.get("reason") == "settle_rows_retry"]
    assert len(retry) == S._SETTLE_ROWS_MAX_TRIES - 1
    # dopo i tentativi massimi si chiude GRIDANDO (come negli altri due rami)
    assert stati[-1] == "SETTLED"
    assert any(k == "error" and p.get("reason") == "settle_rows_failed" and p.get("critical")
               for k, p, _e in db.activity)


# ===========================================================================
# W11 - l'episodio di lettura fallita e' stato di PROCESSO
# ===========================================================================
def test_azzera_cache_di_processo_chiude_l_episodio_di_lettura_fallita():
    S._avvisa_feed_non_letto(FakeDB(), NOW.timestamp())
    assert S._feed_non_letto() is True
    S.azzera_cache_di_processo()
    assert S._feed_non_letto() is False


# ===========================================================================
# W13 - PAPER, riga assente: l'esito del runner si legge lo stesso
# ===========================================================================
def test_paper_riga_assente_l_esito_del_runner_si_legge(runner):
    db = FakeDB(mode="paper")
    ctx = _ctx_con_uscita()
    _riga(db, ctx.legs[0], status="open", bet_id="B0", mode="paper")
    r = _riga(db, ctx.legs[1], status="pending", bet_id=None, mode="paper")
    ref = f"mike-t{r['id']}"
    db.update_trade(r["id"], meta={**r["meta"], "canale_ref": ref,
                                   "canale_inviato_at": NOW.isoformat()})
    # l'ordine vero sul book del runner (comando col protocollo di produzione)
    runner._piazza({"ref": ref, "mode": "paper", "market_id": "1.35",
                    "selection_id": 1222344, "side": "LAY", "price": 1.48, "size": 10.14,
                    "persistence": "LAPSE", "time_in_force": None})
    runner.abbina(ref)
    ev = _evento(ctx, mode="paper")
    _giro(db, MercatoOrdini([]), ev, None, mode="paper")
    uscita = [x for x in ev["positions"] if x["ref"] == "ko_green-0-3"][0]
    assert uscita["status"] == "open" and uscita["matched"] == pytest.approx(10.14)
    assert db.get_trade(r["id"])["status"] == "open"


# ===========================================================================
# W14 - LIVE, riga assente: la chiusura fuori dall'app si vede lo stesso
# ===========================================================================
class MercatoConto(MercatoOrdini):
    """La posizione di CONTO come `_RealMarket.list_account_orders` e
    `list_account_cleared_orders` (ordini di chiunque, snake_case)."""

    def __init__(self, vivi: List[Dict[str, Any]]) -> None:
        super().__init__([])
        self.vivi = vivi
        self.conto_letto = 0

    def list_account_orders(self, market_id: str) -> List[Dict[str, Any]]:
        self.conto_letto += 1
        return [o for o in self.vivi if o["market_id"] == str(market_id)]

    def list_account_cleared_orders(self, market_id: str) -> List[Dict[str, Any]]:
        return []


def _ordine_conto(*, ref: str, side: str, size: float) -> Dict[str, Any]:
    return {"bet_id": f"B-{ref}", "market_id": "1.35", "selection_id": 1222344, "side": side,
            "status": "EXECUTION_COMPLETE", "size_matched": size, "avg_price_matched": 1.50,
            "size_remaining": 0.0, "customer_order_ref": ref, "size_cancelled": 0.0,
            "size_lapsed": 0.0, "size_voided": 0.0}


def test_live_riga_assente_la_chiusura_fuori_app_si_vede():
    db = FakeDB(mode="live")
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", legs=[_ingresso()], live_since=KO.timestamp(),
                     ko_goals=0)
    _riga(db, ctx.legs[0], status="open", bet_id="B0")
    mk = MercatoConto([_ordine_conto(ref="under_entry-0-1", side="back", size=10.0),
                       _ordine_conto(ref="dal-sito", side="lay", size=10.0)])
    ev = _evento(ctx)
    _giro(db, mk, ev, None)
    assert mk.conto_letto >= 1, "posizione di conto non letta con la riga assente"
    assert ev["ctx"]["chiuso_dall_utente"] is True
    assert "chiuso_dall_utente" in db.kinds()
