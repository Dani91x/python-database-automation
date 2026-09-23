"""23/09 - live_order_worker: l'audit (e la scrittura dell'esito) che fallisce
non si ingoia piu' in silenzio.

Prima: ``_audit`` avvolgeva l'insert su ``betfair_live_audit`` in
``except Exception: pass`` - un ordine reale poteva restare senza riga di
audit e nessun log lo diceva. Stesso ``pass`` nudo attorno a ``_write_error``
(esito 'error' della riga di coda). Adesso: log con il motivo, flusso invariato
(nessuna eccezione propagata).

Il finto ``sb`` imita la catena del client supabase-py vero
(``table().insert().execute()``, ``table().select().eq()...execute().data``);
le righe di coda hanno le colonne vere di ``betfair_live_orders``
(``id``, ``status``, ``action``, ``mode``).
"""
from __future__ import annotations

import logging

from Betfair.stream import live_order_worker as wk


class _Catena:
    def __init__(self, sb, tabella):
        self._sb, self._t = sb, tabella

    def __getattr__(self, nome):          # select/eq/order/limit/update/...
        return lambda *a, **k: self

    def insert(self, riga):
        self._sb.inserite.append((self._t, riga))
        return self

    def execute(self):
        if self._t in self._sb.cadute:
            raise ConnectionError(f"insert {self._t}: Server disconnected")
        return type("R", (), {"data": list(self._sb.righe.get(self._t, []))})()


class _Sb:
    def __init__(self, cadute=(), righe=None):
        self.cadute, self.righe, self.inserite = set(cadute), righe or {}, []

    def table(self, nome):
        return _Catena(self, nome)


def _risultato():
    return {"mode": "live", "action": "place", "market_id": "1.234",
            "selection_id": 55, "side": "LAY", "price": 2.14, "size": 5.0,
            "error": None, "detail": None, "bet_id": "B1"}


def test_audit_fallito_si_logga_con_il_motivo(caplog):
    sb = _Sb(cadute={"betfair_live_audit"})
    with caplog.at_level(logging.WARNING, logger=wk.logger.name):
        wk._audit(sb, 77, _risultato(), "done")        # non solleva: flusso invariato
    testi = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("77" in t and "audit" in t.lower() and "Server disconnected" in t
               for t in testi), testi


def test_audit_riuscito_resta_muto(caplog):
    sb = _Sb()
    with caplog.at_level(logging.WARNING, logger=wk.logger.name):
        wk._audit(sb, 78, _risultato(), "done")
    assert sb.inserite and sb.inserite[0][0] == "betfair_live_audit"
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_esito_error_non_scritto_si_logga(monkeypatch, caplog):
    riga = {"id": 91, "status": "processing", "action": "place_submin", "mode": "live"}
    sb = _Sb(righe={wk._TABLE: [riga]})
    monkeypatch.setattr(wk, "_kill_switch", lambda: False)

    def avanza(*a, **k):
        raise RuntimeError("replace KO")

    def scrive_errore(*a, **k):
        raise ConnectionError("update betfair_live_orders: Server disconnected")

    monkeypatch.setattr(wk, "_advance_submin_row", avanza)
    monkeypatch.setattr(wk, "_write_error", scrive_errore)
    with caplog.at_level(logging.WARNING, logger=wk.logger.name):
        n = wk._advance_inflight_submins(sb, object(), "live", None)
    assert n == 1                                   # flusso invariato
    testi = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("91" in t and "Server disconnected" in t for t in testi), testi
