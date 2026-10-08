# -*- coding: utf-8 -*-
"""Plugin pytest del differenziale D-7: registra, per OGNI chiamata a ``esegui`` dei
test del W2, la riga di coda finale (senza ``processed_at``), gli ordini piazzati
(lato, prezzo, size, persistenza, ref di strategia) e i metodi chiamati sul conto.
Il file di uscita e' in ``D7_CATTURA`` (variabile d'ambiente). ASCII-only."""
import json
import os

import pytest

_LOG = {}


@pytest.fixture(autouse=True)
def _cattura_d7(request, monkeypatch):
    mod = request.module
    orig = getattr(mod, "esegui", None)
    if orig is None:
        yield
        return
    nodo = request.node.nodeid

    def esegui(sb, fl, riga):
        r = orig(sb, fl, riga)
        m = next(iter(fl.markets.markets.values()))
        clienti = getattr(fl, "clients", None) or []
        conto = (getattr(clienti[0].betting_client.betting.request, "__self__", None)
                 if clienti else None)
        r2 = dict(r)
        r2.pop("processed_at", None)
        voce = {
            "riga": r2,
            "piazzati": [(o.side, o.order_type.price, o.order_type.size,
                          o.order_type.persistence_type, kw.get("customer_strategy_ref"))
                         for o, kw in getattr(m, "piazzati", [])],
            "metodi": [c[0] for c in getattr(conto, "chiamate", [])],
            "letture_db": list(getattr(sb, "letture", [])),
            "blotter": getattr(getattr(m, "blotter", None), "letture", None),
        }
        _LOG.setdefault(nodo, []).append(json.loads(json.dumps(voce, default=str)))
        return r

    monkeypatch.setattr(mod, "esegui", esegui)
    yield


def pytest_sessionfinish(session, exitstatus):
    with open(os.environ["D7_CATTURA"], "w", encoding="utf-8") as f:
        json.dump(_LOG, f, indent=1, sort_keys=True)
