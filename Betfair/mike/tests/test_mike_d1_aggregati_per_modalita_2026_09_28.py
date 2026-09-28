"""D1 (28/09) - MIKE: I NUMERI CHE DECIDONO CONTANO SOLO LA MODALITA' ATTIVA.

Catalogo §7.21 (tetto partite che conta paper e live insieme; P&L che somma
paper e live), riaperto dal cantiere Omega il 28/09. In Mike:
  * lo stop di giornata legge ``db.aggregates``: la RPC e' per modalita'
    (``mike_aggregati_per_modalita_2026-09-13.sql``, applicata), ma il RIPIEGO
    sommava paper e live, e ci si finiva per sempre al primo errore qualunque
    (anche un timeout);
  * la copia in memoria degli aggregati non sapeva di che modalita' fosse;
  * il tetto che ARMA nuove partite contava le partite di entrambe le modalita'.

Finti: le righe di ``mike_trades`` con le chiavi vere (id, event_id, status,
pnl, mode, placed_at, settled_at); gli errori PostgREST col testo vero.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from Betfair.mike import db as MDB
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, run


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    MDB._AGG_RPC.clear()
    MDB._TOTALS.clear()
    S._LAST_AGG.clear()
    monkeypatch.setattr(S, "_freno_aperture_rest", lambda: None)
    monkeypatch.setattr(S.X, "_freno_aperture", lambda: None)

    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)
    yield
    MDB._AGG_RPC.clear()
    MDB._TOTALS.clear()
    S._LAST_AGG.clear()


def _rpc_mancante(*_a, **_k):
    raise RuntimeError("{'code': 'PGRST202', 'message': 'Could not find the function "
                       "public.get_mike_aggregates(p_mode) in the schema cache'}")


def _righe():
    ts = NOW.isoformat()
    return [{"id": 1, "event_id": "A", "status": "lost", "pnl": -80.0, "mode": "paper",
             "placed_at": ts, "settled_at": ts},
            {"id": 2, "event_id": "B", "status": "won", "pnl": 3.0, "mode": "live",
             "placed_at": ts, "settled_at": ts}]


def test_ripiego_conta_SOLO_la_modalita_chiesta(monkeypatch):
    monkeypatch.setattr(MDB, "_sb", _rpc_mancante)
    monkeypatch.setattr(MDB, "live_trades", lambda since=None: _righe())
    monkeypatch.setattr(MDB, "all_trades", lambda *a, **k: _righe())
    assert MDB.aggregates(NOW, mode="live")["realized_today"] == 3.0
    assert MDB.aggregates(NOW, mode="paper")["realized_today"] == -80.0


def test_la_rpc_riceve_la_modalita_esplicita(monkeypatch):
    chiamate = []

    class Sb:
        def rpc(self, nome, arg):
            chiamate.append((nome, dict(arg)))
            return self

        def execute(self):
            return type("R", (), {"data": {"realized_today": 1.0}})()

    monkeypatch.setattr(MDB, "_sb", lambda: Sb())
    MDB.aggregates(NOW, mode="live")
    assert chiamate == [("get_mike_aggregates", {"p_mode": "live"})]


def test_un_TIMEOUT_non_spegne_la_rpc_per_sempre(monkeypatch):
    """Un guasto transitorio risale (il servizio riusa l'ultimo valore buono
    DELLA STESSA MODALITA'); solo l'errore di schema dichiara la RPC assente."""
    def timeout(*_a, **_k):
        raise RuntimeError("The read operation timed out")
    monkeypatch.setattr(MDB, "_sb", timeout)
    with pytest.raises(RuntimeError):
        MDB.aggregates(NOW, mode="live")
    assert not MDB._AGG_RPC.get("missing")


def test_la_memoria_del_servizio_e_PER_MODALITA():
    """Una perdita in paper non puo' diventare lo stop del live passando dalla
    copia in memoria (cache viva, stesso istante)."""
    class Db:
        def aggregates(self, now, mode=None):
            return {"realized_today": {"paper": -80.0, "live": 3.0}[mode]}
    par = {"aggregates_cache_s": 600.0}
    assert S._aggregates_cached(Db(), NOW, par, mode="paper")["realized_today"] == -80.0
    assert S._aggregates_cached(Db(), NOW, par, mode="live")["realized_today"] == 3.0


def test_con_la_lettura_KO_si_riusa_l_ultimo_valore_della_STESSA_modalita():
    class Db:
        rotto = False

        def aggregates(self, now, mode=None):
            if self.rotto:
                raise RuntimeError("timeout")
            return {"realized_today": {"paper": -80.0, "live": 3.0}[mode]}
    db = Db()
    S._aggregates(db, NOW, mode="paper")
    S._aggregates(db, NOW, mode="live")
    db.rotto = True
    # la PAPER e' stata letta per prima: con una memoria unica tornerebbe il
    # valore del live (l'ultimo scritto)
    assert S._aggregates(db, NOW, mode="paper")["realized_today"] == -80.0
    assert S._aggregates(db, NOW, mode="live")["realized_today"] == 3.0


class DbModi(FakeDB):
    def aggregates(self, now=None, mode=None):
        righe = [t for t in self.trades if mode is None or t.get("mode") == mode]
        from Betfair.safe_strategy import bot_db as B
        from Betfair.safe_strategy import risk as R
        return B.aggregate_rows(righe, R.operating_day_start(now))


def test_partite_PAPER_non_tolgono_posti_al_LIVE_quando_si_armano():
    """Tetto partite = 1. Una partita paper ancora viva (PRE_OPEN) non deve
    impedire al live di armare la sua candidata."""
    db = DbModi(mode="live", params={"stake": 10, "max_open_matches": 1})
    db.events["P1"] = {"event_id": "P1", "event_name": "Paper v Paper", "state": "PRE_OPEN",
                       "mode": "paper", "cycle_no": 0, "positions": [], "ctx": {},
                       "markets": {}, "dossier": {}, "live": {},
                       "updated_at": NOW.isoformat(),
                       "ko_at": (NOW + timedelta(hours=1)).isoformat()}
    run(db, FakeMarket(), NOW, [row(payload())])
    assert "E1" in db.events, "la candidata live non e' stata armata"
    assert db.events["E1"]["mode"] == "live"
