# -*- coding: utf-8 -*-
"""26/09 (F-6, test e2e FASE 3) - PROPOSTE DI OPPORTUNITA' SCADUTE.

Reperto: la proposta #257 (Andorra v Malta, creata il 24/09 16:03Z, partita
finita) era ancora 'proposed' il 26/09 e la Control Room la mostrava con
«Piazza». Causa: ``bot_db.proposte_opportunita`` legge solo le ultime 24 ore;
se il servizio e' spento quando la partita finisce, la proposta esce dalla
finestra e la decadenza («partita non piu' in gioco») non la vede MAI.

Correzione: ``_scadi_proposte_vecchie`` (una volta ogni 10 minuti, e al primo
ciclo) chiama ``bot_db.scadi_proposte_opportunita(12)``: 'rejected' +
``decaduta`` (lo stato 'expired' non esiste nel CHECK della tabella).

Il DbFinto e' quello di ``test_proposte_opportunita_2026_09_17`` con in piu'
``scadi_proposte_opportunita`` che applica la STESSA regola del vero
(created_at < adesso − ore, solo kind='place' e status='proposed'); il vero
``bot_db.scadi_proposte_opportunita`` e' collaudato con un ``_sb`` registratore.

FALSIFICAZIONE (26/09): togliendo la chiamata a ``_scadi_proposte_vecchie`` da
``process_opportunities`` il primo test diventa rosso; togliendo
``.lt("created_at", ...)`` dal vero il test della query diventa rosso.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Betfair.safe_strategy import bot_db as B
from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy.tests.test_proposte_opportunita_2026_09_17 import (
    NOW, DbFinto, _ciclo, _opp)


class DbConScadenza(DbFinto):
    def scadi_proposte_opportunita(self, ore):
        limite = NOW - timedelta(hours=float(ore))
        fuori = []
        for r in self.richieste:
            nata = datetime.fromisoformat(r["created_at"])
            if r.get("kind") == "place" and r["status"] == "proposed" and nata < limite:
                r["status"] = "rejected"
                r["result"] = {"decaduta": True, "scaduta": True,
                               "motivo": f"proposta scaduta: piu' vecchia di {ore:g} ore"}
                fuori.append(dict(r))
        return fuori


def _vecchia(db, ore_fa, rid=257, event_id="35999999"):
    db.richieste.append({
        "id": rid, "kind": "place", "status": "proposed",
        "created_at": (NOW - timedelta(hours=ore_fa)).isoformat(),
        "payload": {"opp_key": f"{event_id}:model:MATCH_ODDS:1:lay", "event_id": event_id,
                    "event_name": "Andorra v Malta", "kind": "model", "mode": "paper"},
        "result": None})


def test_la_proposta_di_41_ore_fa_decade_al_primo_ciclo():
    db = DbConScadenza()
    _vecchia(db, 41)
    _ciclo(db, [_opp()])
    r257 = next(r for r in db.richieste if r["id"] == 257)
    assert r257["status"] == "rejected"
    assert r257["result"]["decaduta"] is True and r257["result"]["scaduta"] is True
    assert "opportunita_decaduta" in db.kinds()


def test_una_proposta_giovane_non_decade_per_eta():
    db = DbConScadenza()
    _vecchia(db, 2, rid=300)
    st = {}
    assert S._scadi_proposte_vecchie(db, NOW, st) == 0
    assert next(r for r in db.richieste if r["id"] == 300)["status"] == "proposed"


def test_la_pulizia_non_gira_a_ogni_ciclo():
    db = DbConScadenza()
    st = {}
    assert S._scadi_proposte_vecchie(db, NOW, st) == 0
    _vecchia(db, 41)
    # 5 minuti dopo: ancora dentro l'intervallo, nessun UPDATE
    assert S._scadi_proposte_vecchie(db, NOW + timedelta(minutes=5), st) == 0
    assert S._scadi_proposte_vecchie(db, NOW + timedelta(minutes=11), st) == 1


def test_db_senza_accessor_non_si_rompe():
    assert S._scadi_proposte_vecchie(DbFinto(), NOW, {}) == 0


class _Registratore:
    """Il costruttore di query di supabase-py, ridotto a registrare le chiamate."""

    def __init__(self):
        self.chiamate = []

    def table(self, nome):
        self.chiamate.append(("table", nome))
        return self

    def __getattr__(self, nome):
        def f(*a, **k):
            self.chiamate.append((nome, a))
            return self
        return f

    def execute(self):
        class R:
            data = [{"id": 257, "payload": {}}]
        return R()


def test_la_query_vera_filtra_kind_stato_ed_eta(monkeypatch):
    reg = _Registratore()
    monkeypatch.setattr(B, "_sb", lambda: reg)
    monkeypatch.setattr(B, "_CANALE_ACCESO", False)
    fuori = B.scadi_proposte_opportunita(12)
    assert fuori == [{"id": 257, "payload": {}}]
    nomi = [c[0] for c in reg.chiamate]
    assert ("table", "safe_strategy_requests") in reg.chiamate
    assert ("eq", ("kind", "place")) in reg.chiamate
    assert ("eq", ("status", "proposed")) in reg.chiamate
    lt = [c for c in reg.chiamate if c[0] == "lt"]
    assert lt and lt[0][1][0] == "created_at"
    limite = datetime.fromisoformat(lt[0][1][1])
    atteso = datetime.now(timezone.utc) - timedelta(hours=12)
    assert abs((limite - atteso).total_seconds()) < 60
    upd = next(c for c in reg.chiamate if c[0] == "update")[1][0]
    assert upd["status"] == "rejected" and upd["result"]["decaduta"] is True
    assert "update" in nomi
