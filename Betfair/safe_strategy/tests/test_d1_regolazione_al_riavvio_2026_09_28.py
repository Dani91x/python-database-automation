# -*- coding: utf-8 -*-
"""D1 (28/09) - SAFE: AL RIAVVIO UNA POSIZIONE SU UNA PARTITA FINITA SI REGOLA.

Reperto del coordinatore (DB, 28/09): ad app spenta dal 26/09 17:40Z restano
4 posizioni PAPER di Safe ancora 'open' (id 359, 361, 362, 363, esatto) su
partite finite da due giorni. Il settlement di Safe legge i mercati con
``listMarketBook`` a blocchi di 40 (``omega_market.read_markets``); la
documentazione Betfair di ``listMarketBook`` dice: «Separate requests should
be made for OPEN & CLOSED markets. Requests that include both OPEN & CLOSED
markets will only return those markets that are OPEN». In un blocco con anche
un solo mercato aperto il mercato CHIUSO manca dalla risposta: ``read_markets``
lo dice None e il settlement lo trattava come «mercato sparito» (mai regolato).

Il finto e' al confine piu' basso possibile: ``omega_market.call`` riceve un
client che risponde come ``list_market_book`` di Betfair (chiavi camelCase:
``marketId``, ``status``, ``runners[].selectionId``/``status``) applicando
la regola documentata; ``read_markets`` e ``_snapshot_from_book`` sono i veri.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from Betfair.omega import omega_market as M
from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy.tests.test_bot_service import (NOW, FakeDB, _auto_trade,
                                                          _reset_module_state)


def _book(mid, status, vincitore=None, sel=(8, 7, 9)):
    return {"marketId": mid, "status": status, "inplay": status == "OPEN",
            "runners": [{"selectionId": s,
                         "status": ("ACTIVE" if status == "OPEN" else
                                    ("WINNER" if s == vincitore else "LOSER")),
                         "ex": {"availableToBack": [], "availableToLay": []}}
                        for s in sel]}


class ClientBetfair:
    """``list_market_book`` con la regola di Betfair sui mercati misti."""

    def __init__(self, libri):
        self.libri = dict(libri)
        self.richieste: list[list[str]] = []

    def list_market_book(self, ids):
        ids = [str(i) for i in ids]
        self.richieste.append(ids)
        presenti = [self.libri[i] for i in ids if i in self.libri]
        if any(b["status"] != "CLOSED" for b in presenti):
            presenti = [b for b in presenti if b["status"] != "CLOSED"]
        return presenti


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    _reset_module_state()
    S._EVENTI_CHIUSI.clear()

    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)
    yield
    _reset_module_state()


def _mercato(monkeypatch, client):
    monkeypatch.setattr(M, "call", lambda fn: fn(client))
    return SimpleNamespace(read_markets=M.read_markets, read_market=M.read_market)


def _due_posizioni(db, mode):
    """Una posizione su una partita FINITA (mercato m-finito, l'ospite sel 8
    perde) e una su una partita ANCORA APERTA (pre-partita, m-vivo)."""
    finita = _auto_trade(db, "esatto", event_id="35926090", market_id="m-finito",
                         mode=mode, signal_key="35926090:esatto:x")
    viva = _auto_trade(db, "esatto", event_id="36999999", market_id="m-vivo",
                       mode=mode, signal_key="36999999:esatto:y")
    return finita, viva


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_blocco_MISTO_la_posizione_finita_si_regola_al_primo_giro(monkeypatch, mode):
    db = FakeDB(status="stopped", mode=mode)
    finita, viva = _due_posizioni(db, mode)
    client = ClientBetfair({"m-finito": _book("m-finito", "CLOSED", vincitore=7),
                            "m-vivo": _book("m-vivo", "OPEN")})
    n = S.settle_open(params=S.resolve_params(None), market=_mercato(monkeypatch, client),
                      db=db, now=NOW + timedelta(days=2), rows_by_event={})
    t = db.get_trade(finita)
    assert t["status"] in ("won", "lost"), (
        f"posizione su partita finita ancora {t['status']}: {client.richieste}")
    # lay sull'ospite (sel 8), ha vinto la casa (sel 7): la lay VINCE
    assert t["status"] == "won" and t["pnl"] > 0
    assert db.get_trade(viva)["status"] == "open"
    assert n == 1
    assert "market_missing" not in db.kinds()


def test_mercato_davvero_assente_resta_MANCANTE_non_inventato(monkeypatch):
    """Cintura: se neppure la lettura singola lo trova, la posizione non si
    regola e non si inventa niente (conta come lettura mancata)."""
    db = FakeDB(status="stopped")
    finita, viva = _due_posizioni(db, "paper")
    client = ClientBetfair({"m-vivo": _book("m-vivo", "OPEN")})
    S.settle_open(params=S.resolve_params(None), market=_mercato(monkeypatch, client),
                  db=db, now=NOW + timedelta(days=2), rows_by_event={})
    assert db.get_trade(finita)["status"] == "open"
    assert ["m-finito"] in client.richieste, "la lettura singola e' stata tentata"


def test_solo_mercati_chiusi_una_sola_richiesta(monkeypatch):
    """Il caso del riavvio con sole posizioni finite: il blocco li restituisce
    tutti e non servono letture singole."""
    db = FakeDB(status="stopped")
    a = _auto_trade(db, "esatto", event_id="1", market_id="m1", signal_key="1:e:x")
    b = _auto_trade(db, "esatto", event_id="2", market_id="m2", signal_key="2:e:x")
    client = ClientBetfair({"m1": _book("m1", "CLOSED", vincitore=8),
                            "m2": _book("m2", "CLOSED", vincitore=7)})
    S.settle_open(params=S.resolve_params(None), market=_mercato(monkeypatch, client),
                  db=db, now=NOW + timedelta(days=2), rows_by_event={})
    assert db.get_trade(a)["status"] == "lost" and db.get_trade(b)["status"] == "won"
    assert len(client.richieste) == 1
