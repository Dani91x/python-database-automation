"""D1 (28/09) - MIKE: AL RIAVVIO UNA PARTITA FINITA AD APP SPENTA SI REGOLA.

Reperto del coordinatore (DB, 28/09): ad app spenta dal 26/09 17:40Z restano
5 posizioni PAPER di Mike 'open' su partite finite da due giorni. ``run_once``
carica le partite con ``list_events(since_iso=adesso-48h)``, che nel vero
(``mike/db.py``) filtra su ``updated_at``; ad app spenta la scheda non si
aggiorna, quindi oltre le 48 ore una partita NON terminale non veniva piu'
letta ne' regolata. Il finto di ``test_mike_service`` ignorava ``since_iso``:
qui lo applica come il vero (``updated_at >= since``, ``state in states``).

La regolazione passa dalla strada di sempre: riga assente dal feed, KO oltre
3 ore -> ``read_book`` dei due mercati (``listMarketBook``: runner
WINNER/LOSER con le chiavi di ``omega_market.read_book``) -> SETTLED.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_audit_2026_09_11 import asdict, live_event, over_leg, under_leg
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, run

SEL = {"OU35|UNDER": 101, "OU35|OVER": 102, "OU45|UNDER": 201, "OU45|OVER": 202}


@pytest.fixture(autouse=True)
def _nessun_db_vero(monkeypatch):
    monkeypatch.setattr(S, "_freno_aperture_rest", lambda: None)
    monkeypatch.setattr(S.X, "_freno_aperture", lambda: None)

    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)


class DbFinestra(FakeDB):
    """``list_events`` come ``mike/db.py``: ``since_iso`` = ``updated_at >= since``
    OPPURE stato non terminale (``db.STATI_TERMINALI``). ``VECCHIA_FINESTRA``
    riproduce il vero di prima del 28/09 (solo ``updated_at``)."""

    VECCHIA_FINESTRA = False

    def list_events(self, states=None, since_iso=None):
        from Betfair.mike import db as MDB

        self.letture_eventi = getattr(self, "letture_eventi", 0) + 1
        out = []
        for e in self.events.values():
            if states and e.get("state") not in states:
                continue
            if since_iso:
                recente = str(e.get("updated_at") or "") >= str(since_iso)
                viva = e.get("state") not in MDB.STATI_TERMINALI
                if not (recente or (viva and not self.VECCHIA_FINESTRA)):
                    continue
            out.append(dict(e))
        return out

    def upsert_event(self, row):
        self.events[str(row["event_id"])] = {**dict(row), "updated_at": self._ora}


def _libro(mid, vincitore_sid, sids):
    """Come ``omega_market.read_book`` su un mercato CHIUSO."""
    return {"market_id": mid, "status": "CLOSED", "inplay": False,
            "runners": [{"selection_id": s, "status": "WINNER" if s == vincitore_sid else "LOSER",
                         "name": "?", "lay_price": None, "lay_size": 0.0, "back_price": None,
                         "back_size": 0.0, "lay_ladder": []} for s in sids]}


def _scenario(ore_ferma: float, mode="paper"):
    fine = NOW - timedelta(hours=ore_ferma)
    db = DbFinestra(params={"stake": 10})
    db._ora = NOW.isoformat()
    ev = live_event([asdict(under_leg()), asdict(over_leg())], mode=mode,
                    ko=fine - timedelta(hours=2),
                    ctx={"seen_inplay": True, "selections": SEL})
    ev["updated_at"] = fine.isoformat()
    db.events["E1"] = ev
    db.trades = [
        {"id": 1, "event_id": "E1", "signal_key": "under_last-1-1", "status": "open",
         "role": "under_last", "side": "back", "price": 1.5, "size": 10.0, "mode": mode,
         "pnl": 0, "commission": 0.05, "meta": {}},
        {"id": 2, "event_id": "E1", "signal_key": "over_cover-1-2", "status": "open",
         "role": "over_cover", "side": "back", "price": 6.0, "size": 2.53, "mode": mode,
         "pnl": 0, "commission": 0.05, "meta": {}},
    ]
    mk = FakeMarket()
    # finita 1-1: 2 gol -> Under 3.5 VINCE, Under 4.5 vince (Over 4.5 perde)
    mk.books = {"1.35": _libro("1.35", 101, (101, 102)),
                "1.45": _libro("1.45", 201, (201, 202))}
    return db, mk


@pytest.mark.parametrize("ore_ferma", [3.0, 70.0])
def test_partita_finita_ad_app_spenta_si_regola_al_riavvio(ore_ferma):
    """A 3 ore e a quasi 3 giorni dall'ultimo aggiornamento: stessa regolazione."""
    db, mk = _scenario(ore_ferma)
    run(db, mk, NOW, [])
    assert db.events["E1"]["state"] == "SETTLED", (
        f"partita ferma da {ore_ferma} h non regolata: stato {db.events['E1']['state']}")
    stati = {t["signal_key"]: t["status"] for t in db.trades}
    assert stati == {"under_last-1-1": "won", "over_cover-1-2": "lost"}


def test_con_la_finestra_di_prima_la_partita_restava_aperta_per_sempre():
    """Il difetto, riprodotto col finto che parla come il vero di prima."""
    db, mk = _scenario(70.0)
    db.VECCHIA_FINESTRA = True
    run(db, mk, NOW, [])
    assert db.events["E1"]["state"] == "LIVE_COVERED"
    assert {t["status"] for t in db.trades} == {"open"}


def test_le_terminali_vecchie_restano_fuori_e_la_lettura_resta_UNA():
    """Cintura: nessuna lettura in piu' (regola del respiro del DB, 13/09) e
    una partita SETTLED vecchia non si rilegge."""
    db, mk = _scenario(70.0)
    db.events["E1"]["state"] = "SETTLED"
    run(db, mk, NOW, [])
    assert mk.calls == []
    assert db.letture_eventi == 1


def test_gli_stati_terminali_del_db_sono_quelli_dell_engine():
    from Betfair.mike import db as MDB

    assert set(MDB.STATI_TERMINALI) == set(E.TERMINAL_STATES)


def test_il_vero_list_events_usa_la_finestra_con_le_non_terminali(monkeypatch):
    """Il VERO ``mike/db.list_events``: col costruttore PostgREST registrato si
    vede quale filtro parte verso il server (nessuna rete)."""
    from Betfair.mike import db as MDB

    chiamate = []

    class Q:
        def __getattr__(self, nome):
            def f(*a, **k):
                chiamate.append((nome, a))
                return self
            return f

        def execute(self):
            return type("R", (), {"data": []})()

    class Sb:
        def table(self, nome):
            chiamate.append(("table", (nome,)))
            return Q()

    monkeypatch.setattr(MDB, "_sb", lambda: Sb())
    MDB.list_events(since_iso="2026-09-26T13:53:18+00:00")
    assert ("or_", (MDB.filtro_finestra_eventi("2026-09-26T13:53:18+00:00"),)) in chiamate
    assert not any(n == "gte" for n, _ in chiamate), "finestra solo su updated_at"


def test_il_filtro_postgrest_e_quello_verificato_sul_server():
    """Stringa provata il 28/09 con una GET in sola lettura su ``mike_events``
    (7 righe, identiche all'SQL equivalente)."""
    from Betfair.mike import db as MDB

    assert MDB.filtro_finestra_eventi("2026-09-26T13:53:18+00:00") == (
        'updated_at.gte."2026-09-26T13:53:18+00:00",state.not.in.(SETTLED,ERROR,SKIPPED)')
