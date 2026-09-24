"""24/09 - IL P&L REALE DA BETFAIR (ordini dell'utente 9 e 10).

Sotto test, con finti che hanno le IDENTICHE chiavi del vero
(``betfairlightweight.resources.bettingresources.ClearedOrder``: attributi
snake_case ``bet_id``, ``market_id``, ``selection_id``, ``profit``,
``commission``, ``settled_date``, ``bet_outcome``, ``price_matched``,
``size_settled``, ``customer_order_ref``, ``customer_strategy_ref``,
``event_type_id``; a livello ORDINE Betfair NON manda ``commission``, quindi
nel finto e' None; a livello MERCATO si):

  * il netto di un ordine = profit(BET) - quota della commissione del
    MERCATO (fonte ufficiale: profit e' lordo, commission solo per MARKET);
  * attribuzione per bet_id, in subordine per customerOrderRef, MAI per
    customerStrategyRef (nota del coordinatore 24/09);
  * manuale sito = nessuna nostra riga con quel bet_id;
  * il paper non si tocca mai (solo righe mode='live');
  * la giornata e' quella di Roma (settledDateRange);
  * nessuna chiamata REST in piu' dove prima ce n'era una.

Nessuna rete, nessun DB vero.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.db as dbmod
import Betfair.stream.reconcile_worker as rw
from Betfair.stream.tests.test_reconcile_worker import (  # noqa: F401 - fixture riusata
    _FakeBetting, _FakeSb, _chiamate_ordini, _riga, _session, env,
)


def _bet(bet_id: str, profit: float, *, market_id: str = "1.500",
         oref: Optional[str] = None, sref: Optional[str] = None,
         event_type_id: str = "1",
         settled: Optional[datetime] = None) -> Any:
    """``ClearedOrder`` a livello ORDINE come lo da' betfairlightweight:
    ``commission`` None (Betfair non la manda per BET, roll-up ufficiale)."""
    return SimpleNamespace(
        bet_id=bet_id, bet_count=1, bet_outcome="WON" if profit > 0 else "LOST",
        market_id=market_id, selection_id=47972, event_id="35000001",
        event_type_id=event_type_id, side="BACK", price_matched=2.0,
        size_settled=2.0, profit=profit, commission=None,
        customer_order_ref=oref, customer_strategy_ref=sref,
        settled_date=settled or datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc),
    )


def _mercato(market_id: str, profit: float, commission: Optional[float], n: int) -> Any:
    """``ClearedOrder`` a livello MERCATO (groupBy=MARKET): porta commission."""
    return SimpleNamespace(market_id=market_id, profit=profit, commission=commission,
                           bet_count=n, event_id="35000001", event_type_id="1")


# ---------------------------------------------------------------------------
# 1) netto = profit - quota della commissione DEL MERCATO
# ---------------------------------------------------------------------------
def test_commissione_ripartita_sui_profit_positivi_somma_esatta():
    ordini = [_bet("1", 10.0), _bet("2", 5.0), _bet("3", -4.0)]
    comm = rw.commissioni_per_ordine(ordini, [_mercato("1.500", 11.0, 0.55, 3)])
    assert comm == {"1": 0.37, "2": 0.18, "3": 0.0}
    assert round(sum(comm.values()), 2) == 0.55


def test_commissione_del_mercato_illeggibile_nessun_netto():
    ordini = [_bet("1", 10.0)]
    assert rw.commissioni_per_ordine(ordini, [_mercato("1.500", 10.0, None, 1)]) == {"1": None}
    # mercato assente dai gruppi: idem, mai uno zero inventato
    assert rw.commissioni_per_ordine(ordini, []) == {"1": None}


def test_netto_reale_scritto_sulla_riga_e_mai_il_lordo(env):
    """Il P&L scritto sulla riga del bot e' profit - commissione del mercato.
    FALSIFICAZIONE: scrivere il profit lordo (o leggere la commission del
    livello ORDINE, che Betfair non manda) fa diventare rosso questo test."""
    _riga(env, "omega_trades", id=7, bet_id="30")
    betting = _FakeBetting(cleared_pages=[[_bet("30", 2.0)]],
                           market_groups=[_mercato("1.500", 2.0, 0.10, 1)])
    rw._sync_manual_pnl(_session(betting=betting))
    assert env["riga_writes"] == [("omega_trades", "7", {
        "pnl_betfair": 1.90, "commissione_betfair": 0.10,
        "pnl_betfair_settled_at": "2026-09-24T15:00:00+00:00",
    })]
    reale = env["pnl_reale_writes"][0]
    assert reale["netto"] == 1.90 and reale["lordo"] == 2.0 and reale["commissione"] == 0.10
    assert reale["per_fonte"]["omega"]["netto"] == 1.90


def test_ordine_senza_commissione_di_mercato_resta_stimato(env):
    """Commissione del mercato illeggibile: la riga NON riceve un P&L reale
    (resta quello calcolato, marcato stimato in pagina) e il totale reale non
    lo conta; il caso e' contato (``senza_commissione``)."""
    _riga(env, "mike_trades", id=4, bet_id="40")
    betting = _FakeBetting(cleared_pages=[[_bet("40", 3.0)]],
                           market_groups=[_mercato("1.500", 3.0, None, 1)])
    rw._sync_manual_pnl(_session(betting=betting))
    assert env["riga_writes"] == []
    reale = env["pnl_reale_writes"][0]
    assert reale["ordini"] == 0 and reale["netto"] == 0.0 and reale["senza_commissione"] == 1
    assert reale["bet_ids"] == []


# ---------------------------------------------------------------------------
# 2) di chi e': bet_id, poi customerOrderRef, MAI customerStrategyRef
# ---------------------------------------------------------------------------
def test_attribuzione_per_bet_id_prima_del_ref(env):
    """bet_id sulla riga di Mike, ref che punterebbe a Omega: vince il bet_id.
    FALSIFICAZIONE: invertire l'ordine (ref prima del bet_id) -> rosso."""
    _riga(env, "mike_trades", id=3, bet_id="50")
    _riga(env, "omega_trades", id=5, bet_id=None)
    betting = _FakeBetting(cleared_pages=[[_bet("50", 1.0, oref="omega-t5", sref="omega")]],
                           market_groups=[_mercato("1.500", 1.0, 0.0, 1)])
    rw._sync_manual_pnl(_session(betting=betting))
    assert [(t, i) for t, i, _c in env["riga_writes"]] == [("mike_trades", "3")]
    assert env["pnl_reale_writes"][0]["per_fonte"]["mike"]["ordini"] == 1


def test_in_subordine_customer_order_ref_se_la_riga_esiste(env):
    """Nessuna riga con quel bet_id (per esempio un bet_id nuovo dopo un
    replace): il ref ``safe-t9`` porta alla riga 9 di Safe, che esiste.
    E' Safe anche se il ref di STRATEGIA dice 'omega' (oggi Safe piazza con
    il ref di strategia di Omega): FALSIFICAZIONE, decidere per strategy ref
    -> la voce diventa 'omega' -> rosso."""
    _riga(env, "safe_strategy_trades", id=9, bet_id="vecchio")
    betting = _FakeBetting(cleared_pages=[[_bet("51", 2.0, oref="safe-t9", sref="omega",
                                                 event_type_id="2")]],
                           market_groups=[_mercato("1.500", 2.0, 0.1, 1)])
    rw._sync_manual_pnl(_session(betting=betting))
    assert [(t, i) for t, i, _c in env["riga_writes"]] == [("safe_strategy_trades", "9")]
    pf = env["pnl_reale_writes"][0]["per_fonte"]
    assert pf["safe_tennis"]["ordini"] == 1        # sport dall'eventTypeId (2 = tennis)
    assert pf["omega"]["ordini"] == 0


def test_manuale_sito_e_chi_non_ha_una_nostra_riga(env):
    """Nessuna riga con quel bet_id in NESSUNA delle 5 tabelle -> sito. Una
    riga ``betfair_live_orders`` con source='account' e' la COPIA di un
    ordine del sito trovato sul conto: non e' nostra."""
    _riga(env, "betfair_live_orders", id=70, bet_id="60", source="account")
    betting = _FakeBetting(cleared_pages=[[_bet("60", -2.0), _bet("61", 5.0)]],
                           market_groups=[_mercato("1.500", 3.0, 0.15, 2)])
    rw._sync_manual_pnl(_session(betting=betting))
    assert env["riga_writes"] == []
    pf = env["pnl_reale_writes"][0]["per_fonte"]
    assert pf["manuale_sito"]["ordini"] == 2
    assert pf["manuale_sito"]["netto"] == round(-2.0 + 5.0 - 0.15, 2)
    w = env["manual_pnl_writes"][0]
    assert w["pnl_eur"] == 2.85 and w["is_net"] is True


def test_paper_mai_toccato_e_mai_contato_come_nostro(env):
    """Una riga PAPER con lo stesso bet_id non e' una nostra riga reale (il
    paper su Betfair non esiste): la lettura filtra mode='live'. Nessuna
    scrittura sulla riga paper."""
    _riga(env, "omega_trades", id=8, bet_id="80", mode="paper")
    betting = _FakeBetting(cleared_pages=[[_bet("80", 1.0)]],
                           market_groups=[_mercato("1.500", 1.0, 0.05, 1)])
    rw._sync_manual_pnl(_session(betting=betting))
    assert env["riga_writes"] == []
    assert env["pnl_reale_writes"][0]["per_fonte"]["manuale_sito"]["ordini"] == 1


def test_voci_dei_mirror_tennis_e_calcio(env):
    """tennis_live_orders: source 'manual' = ladder dell'app, un bot_key = bot
    tennis; betfair_live_orders: 'runner' = app, 'bot:*' = altri bot."""
    _riga(env, "tennis_live_orders", id=1, bet_id="91", source="manual")
    _riga(env, "tennis_live_orders", id=2, bet_id="92", source="tennis_scalper")
    _riga(env, "betfair_live_orders", id=3, bet_id="93", source="runner")
    _riga(env, "betfair_live_orders", id=4, bet_id="94", source="bot:scalper")
    betting = _FakeBetting(cleared_pages=[[
        _bet("91", 1.0, event_type_id="2"), _bet("92", 2.0, event_type_id="2", market_id="1.6"),
        _bet("93", 3.0, market_id="1.7"), _bet("94", 4.0, market_id="1.8"),
    ]], market_groups=[_mercato("1.500", 1.0, 0.0, 1), _mercato("1.6", 2.0, 0.0, 1),
                       _mercato("1.7", 3.0, 0.0, 1), _mercato("1.8", 4.0, 0.0, 1)])
    rw._sync_manual_pnl(_session(betting=betting))
    pf = env["pnl_reale_writes"][0]["per_fonte"]
    assert pf["manuale_app"]["netto"] == 4.0          # 91 + 93
    assert pf["bot_tennis"]["netto"] == 2.0
    assert pf["altri_bot"]["netto"] == 4.0
    reale = env["pnl_reale_writes"][0]
    assert reale["netto"] == round(sum(v["netto"] for v in pf.values()), 2) == 10.0


# ---------------------------------------------------------------------------
# 3) giornata di Roma, KO, write-on-change
# ---------------------------------------------------------------------------
def test_finestra_e_la_giornata_di_roma(env, monkeypatch):
    """Le due letture (MERCATO e ORDINE) chiedono i regolati della giornata
    di ROMA: 24/09 00:00 Roma = 23/09 22:00 UTC. FALSIFICAZIONE: finestra in
    UTC, o del giorno prima (un regolato di ieri contato oggi) -> rosso."""
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(rw, "_now_local",
                        lambda: datetime(2026, 9, 24, 0, 30, tzinfo=ZoneInfo("Europe/Rome")))
    betting = _FakeBetting(cleared_pages=[[]])
    rw._sync_manual_pnl(_session(betting=betting))
    assert len(betting.cleared_calls) == 2
    for c in betting.cleared_calls:
        rng = c["settled_date_range"]
        assert rng["from"].startswith("2026-09-23T22:00:00")
        assert rng["to"].startswith("2026-09-24T22:00:00")
    assert env["pnl_reale_writes"][0]["day"] == "2026-09-24"


def test_lettura_db_ko_nessuna_scrittura_e_si_ritenta(env, monkeypatch):
    """Una lettura dei proprietari KO non deve MAI produrre un 'sito' dedotto
    dal guasto: niente scritture, firma non avanzata."""
    def _boom() -> Any:
        raise RuntimeError("DB giu'")

    monkeypatch.setattr(rw, "_client_db", _boom)
    betting = _FakeBetting(cleared_pages=[[_bet("1", 1.0)]],
                           market_groups=[_mercato("1.500", 1.0, 0.05, 1)])
    rw._sync_manual_pnl(_session(betting=betting))
    assert env["manual_pnl_writes"] == [] and env["pnl_reale_writes"] == []
    assert rw._LAST_MERCATI_SIG is None


def test_riga_scritta_una_volta_sola_e_letture_solo_per_bet_nuovi(env):
    _riga(env, "omega_trades", id=7, bet_id="30")
    betting = _FakeBetting(cleared_pages=[[_bet("30", 2.0)]],
                           market_groups=[_mercato("1.500", 2.0, 0.1, 1)])
    s = _session(betting=betting)
    rw._sync_manual_pnl(s)
    letture = sum(t.reads for t in env["sb"].bot_tables.values()) + env["sb"].orders.reads
    assert letture == 1                     # trovato in omega_trades: le altre non servono
    # un secondo mercato si regola: si rilegge per ORDINE, ma il 30 e' gia' noto
    betting.cleared_pages = [[_bet("30", 2.0), _bet("31", -1.0, market_id="1.9")]]
    betting.market_groups = [_mercato("1.500", 2.0, 0.1, 1), _mercato("1.9", -1.0, 0.0, 1)]
    rw._MERCATI_CACHE["ts"] = None
    rw._sync_manual_pnl(s)
    assert len(env["riga_writes"]) == 1     # riga 7 invariata: nessuna riscrittura
    letture2 = sum(t.reads for t in env["sb"].bot_tables.values()) + env["sb"].orders.reads
    assert letture2 == 1 + 5                # solo per il bet 31 (sito: cercato in tutte e 5)


# ---------------------------------------------------------------------------
# 4) chiamate REST: la lettura per MERCATO si riusa, quella per ORDINE solo
#    se qualcosa si e' regolato
# ---------------------------------------------------------------------------
def test_live_sync_cleared_e_giro_regolati_condividono_la_lettura_per_mercato(env, monkeypatch):
    """In LIVE ``_sync_cleared`` legge i mercati a ogni giro (come prima): il
    giro di rete dei regolati subito dopo la RIUSA (nessuna seconda chiamata
    per MERCATO). FALSIFICAZIONE: niente cache -> 2 letture -> rosso."""
    clock = {"t": 5000.0}
    monkeypatch.setattr(rw.time, "monotonic", lambda: clock["t"])
    betting = _FakeBetting(cleared_pages=[[_bet("1", 1.0)]],
                           market_groups=[_mercato("1.500", 1.0, 0.05, 1)])
    s = _session(betting=betting)
    rw._sync_cleared(s, _FakeSb())
    clock["t"] += 10.0
    rw._run_manual_pnl_if_due(s)            # giro di rete (non forzato)
    mercato = [c for c in betting.cleared_calls if c.get("group_by") == "MARKET"]
    assert len(mercato) == 1
    assert len(_chiamate_ordini(betting)) == 1


def test_sync_cleared_non_legge_lo_specchio_se_non_c_e_niente_da_scrivere(env):
    """24/09: la mappa mercato->evento (lettura DB fino a 1000 righe) si fa
    solo se c'e' un mercato da scrivere: a mercati invariati, zero letture."""
    betting = _FakeBetting(cleared_groups=[SimpleNamespace(market_id="1.2", profit=1.0,
                                                           bet_count=1)])
    s = _session(betting=betting)
    sb = _FakeSb()
    rw._sync_cleared(s, sb)
    assert sb.orders.reads == 1
    rw._sync_cleared(s, sb)                 # invariato
    assert sb.orders.reads == 1


# ---------------------------------------------------------------------------
# 5) db: solo le colonne nuove, solo righe live
# ---------------------------------------------------------------------------
class _SbRegistra:
    def __init__(self) -> None:
        self.calls: List[Any] = []

    def table(self, name: str) -> "_SbRegistra":
        self.calls.append(("table", name))
        return self

    def update(self, payload: Dict[str, Any]) -> "_SbRegistra":
        self.calls.append(("update", dict(payload)))
        return self

    def upsert(self, payload: Dict[str, Any], on_conflict: Optional[str] = None) -> "_SbRegistra":
        self.calls.append(("upsert", dict(payload), on_conflict))
        return self

    def eq(self, k: str, v: Any) -> "_SbRegistra":
        self.calls.append(("eq", k, v))
        return self

    def execute(self) -> Any:
        return SimpleNamespace(data=[])


def test_db_update_pnl_betfair_solo_righe_live_e_solo_colonne_nuove(monkeypatch):
    sb = _SbRegistra()
    monkeypatch.setattr(dbmod, "get_supabase_client", lambda: sb)
    dbmod.update_pnl_betfair("omega_trades", "7", {"pnl_betfair": 1.9,
                                                   "commissione_betfair": 0.1,
                                                   "pnl_betfair_settled_at": None})
    assert ("eq", "mode", "live") in sb.calls and ("eq", "id", "7") in sb.calls
    with pytest.raises(ValueError):
        dbmod.update_pnl_betfair("omega_trades", "7", {"pnl": 5.0})       # mai il pnl del bot
    with pytest.raises(ValueError):
        dbmod.update_pnl_betfair("omega_control", "1", {"pnl_betfair": 1.0})


def test_db_upsert_pnl_reale_scrive_solo_la_sua_colonna(monkeypatch):
    sb = _SbRegistra()
    monkeypatch.setattr(dbmod, "get_supabase_client", lambda: sb)
    dbmod.upsert_live_account_pnl_reale({"day": "2026-09-24", "netto": 1.0})
    up = [c for c in sb.calls if c[0] == "upsert"][0]
    assert up[1] == {"id": 1, "pnl_reale_oggi": {"day": "2026-09-24", "netto": 1.0}}
    assert up[2] == "id"
