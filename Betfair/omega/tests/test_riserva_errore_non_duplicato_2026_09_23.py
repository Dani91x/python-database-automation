"""23/09 - Omega, riserva (I1): solo la violazione dell'indice unico vale
"gia' riservato".

Prima: ``db.insert_trade(reserve)`` era avvolto in ``except Exception`` che
leggeva QUALSIASI errore (timeout 57014, rete, schema) come "gia' riservato":
ciclo automatico -> skip 'already_reserved' silenzioso; manuale -> errore
'gia_piazzato_su_evento' (falso: sull'evento non c'e' niente). Adesso solo la
violazione dell'unico (``code='23505'`` di postgrest / messaggio ``duplicate
key``/``unique``) e' "gia' riservato"; ogni altro errore si scrive come ERRORE
(reason 'reserve_failed' / 'riserva_non_scritta') e nessun ordine parte.

Gli errori finti sono ``postgrest.exceptions.APIError`` VERI, costruiti con il
dict che PostgREST restituisce (message/code/hint/details).
"""
from __future__ import annotations

from datetime import timedelta

from postgrest.exceptions import APIError

from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as M
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_service import (
    NOW, FakeDB, FakeMarket, _control, _cs, _event, _open_snapshot)

_DUP = {"message": 'duplicate key value violates unique constraint '
                   '"uq_omega_trades_auto_event_phase"',
        "code": "23505", "hint": None,
        "details": "Key (event_id, phase)=(1.100, ft_cs) already exists."}
_TIMEOUT = {"message": "canceling statement due to statement timeout",
            "code": "57014", "hint": None, "details": None}


class _DBRiservaKO(FakeDB):
    def __init__(self, errore):
        super().__init__(_control(status="idle"))
        self._errore = errore

    def insert_trade(self, trade):
        raise APIError(dict(self._errore))


def _place(db):
    ev = M.EventInfo("1.100", "Casa vs Ospite", NOW - timedelta(minutes=40))
    cs = M.CorrectScoreMarket(market_id="m-1.100", event_id="1.100",
                              event_name="Casa vs Ospite",
                              market_start_time=NOW - timedelta(minutes=40),
                              runner_names={3: "2 - 1"})
    sel = E.Selection(selection_id=3, name="2 - 1", price=75.0, lay_size_available=50.0)
    runner = E.ScoreRunner(3, "2 - 1", lay_price=75.0, lay_size=50.0,
                           lay_ladder=((75.0, 50.0),))
    snap = M.MarketSnapshot(status="OPEN", inplay=True, closed=False,
                            winner_selection_id=None, voided=False, runners=[runner])
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    did = S._place_one(ev=ev, cs=cs, sel=sel, snapshot=snap, size=5.0, price=75.0,
                       target=5.0, minute=10, score_str="2 - 1", mode="live",
                       commission=0.05, market=market, db=db, now=NOW,
                       requested_size=5.0, params={"execution_mode": "auto"},
                       phase="ft_cs")
    return did, market


def _reasons(db, kind):
    return [p.get("reason") for k, p in db.activity if k == kind]


def test_riconosce_solo_la_violazione_dell_unico():
    assert S._e_violazione_unica(APIError(dict(_DUP)))
    assert not S._e_violazione_unica(APIError(dict(_TIMEOUT)))
    assert not S._e_violazione_unica(ConnectionError("Server disconnected"))
    # i finti storici del banco (replay_registrazioni) parlano col messaggio
    assert S._e_violazione_unica(RuntimeError(
        'duplicate key value violates unique constraint "uq_x"'))


def test_auto_duplicato_resta_gia_riservato():
    db = _DBRiservaKO(_DUP)
    did, market = _place(db)
    assert did == 0 and market.placed == []
    assert "already_reserved" in _reasons(db, "skip")
    assert "reserve_failed" not in _reasons(db, "error")


def test_auto_errore_non_duplicato_e_un_errore_non_gia_riservato():
    db = _DBRiservaKO(_TIMEOUT)
    did, market = _place(db)
    assert did == 0 and market.placed == [], "nessun ordine senza riserva scritta"
    assert "already_reserved" not in _reasons(db, "skip")
    assert "reserve_failed" in _reasons(db, "error")


def _manuale(errore):
    db = _DBRiservaKO(errore)
    db.manual_reqs = [{"id": 1, "kind": "place", "status": "pending",
                       "payload": {"event_id": "1.100", "market_id": "m-1.100",
                                   "selection_id": 4, "runner_name": "3 - 2",
                                   "side": "lay", "mode": "live", "size": 2}}]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    return db, market


def test_manuale_duplicato_resta_gia_piazzato():
    db, market = _manuale(_DUP)
    assert market.placed == []
    assert "gia_piazzato_su_evento" in str(db.manual_reqs[0].get("result"))


def test_manuale_errore_non_duplicato_non_si_spaccia_per_gia_piazzato():
    db, market = _manuale(_TIMEOUT)
    assert market.placed == []
    res = str(db.manual_reqs[0].get("result"))
    assert "gia_piazzato_su_evento" not in res
    assert "riserva_non_scritta" in res
