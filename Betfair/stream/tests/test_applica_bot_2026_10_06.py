"""06/10/2026 - "Applica bot" del Match Replay: la cronologia degli ordini del
bot (codice di produzione sul banco) e il ramo del worker del Backtest
Automatico. Il percorso completo sul banco e' verificato a parte sulla
registrazione vera 35797769 (referto); qui le parti pure e il cablaggio.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from Betfair.stream.backtest import applica_bot as AB


def _riga(ms: int, ref: str, **kw: Any) -> Dict[str, Any]:
    """Riga dello specchio ``betfair_live_orders`` (chiavi di
    ``LiveTradingStrategy._order_row``) con l'istante del banco."""
    r = {"bet_id": "B" + ref, "client_order_ref": ref, "request_id": None, "mode": "paper",
         "event_id": "35797769", "market_id": "1.259819682", "selection_id": 47972,
         "handicap": 0.0, "side": "back", "order_type": "LIMIT", "price": 2.18, "size": 10.0,
         "size_matched": 0.0, "size_remaining": 10.0, "size_cancelled": 0.0,
         "size_lapsed": 0.0, "size_voided": 0.0, "average_price_matched": 0.0,
         "status": "EXECUTABLE", "persistence": "LAPSE", "placed_at": None,
         "matched_at": None, "_ms": ms}
    r.update(kw)
    return r


def test_cronologia_tiene_solo_i_cambi_e_ordina():
    righe = [
        _riga(2000, "a"),
        _riga(3000, "a"),                                      # uguale: fuori
        _riga(1000, "b", side="lay", price=2.14),
        _riga(4000, "a", size_matched=10.0, size_remaining=0.0, status="EXECUTION_COMPLETE"),
        {"senza": "_ms"},                                      # scartata
    ]
    out = AB.cronologia(righe)
    assert [(r["_ms"], r["client_order_ref"]) for r in out] == [(1000, "b"), (2000, "a"), (4000, "a")]
    assert out[-1]["status"] == "EXECUTION_COMPLETE"


@pytest.mark.parametrize("params,msg", [
    ({"bot": "mike", "scenario": "base", "event_id": "1"}, "non applicabile"),
    ({"bot": "scalper_calcio", "scenario": "inventato", "event_id": "1"}, "scenario non disponibile"),
    ({"bot": "scalper_calcio", "scenario": "paper", "event_id": ""}, "event_id mancante"),
])
def test_richieste_non_valide_rifiutate(params, msg):
    with pytest.raises(ValueError, match=msg):
        AB.esegui(params)


def test_registrazione_assente_e_un_errore_parlante(tmp_path):
    with pytest.raises(ValueError, match="registrazione assente"):
        AB.esegui({"bot": "scalper_calcio", "scenario": "media-under-paper",
                   "event_id": "99999999"}, data_dir=str(tmp_path))


def test_scenari_visivi_esistono_nel_banco():
    from Betfair.stream.scalper.tools import replay_registrazioni as R

    assert set(AB.SCENARI_VISIVI["scalper_calcio"]) <= set(R.SCENARI_DESCRITTI)


# ---------------------------------------------------------------------------
# il worker del Backtest Automatico
# ---------------------------------------------------------------------------
@pytest.fixture
def worker(monkeypatch):
    from Betfair.stream.backtest import worker as W

    st: Dict[str, List[Any]] = {"esiti": [], "status": [], "backtest": []}
    monkeypatch.setattr(W.db, "write_replay_bot_esito",
                        lambda rid, esito: st["esiti"].append((rid, esito)))
    monkeypatch.setattr(W.db, "set_backtest_status",
                        lambda rid, s, err=None: st["status"].append((rid, s, err)))
    monkeypatch.setattr(W, "run_backtest", lambda p: st["backtest"].append(p) or [])
    monkeypatch.setattr(W.db, "write_backtest_results", lambda rid, rows: len(rows))
    return W, st


def test_worker_applica_bot_scrive_l_esito(worker, monkeypatch):
    W, st = worker
    params = {"tipo": "applica_bot", "bot": "scalper_calcio", "scenario": "media-under-paper",
              "event_id": "35797769"}
    monkeypatch.setattr(W.db, "claim_backtest_request", lambda: {"id": "R1", "params": params})
    esito = {"ordini": 5, "righe": [_riga(1, "a")]}
    monkeypatch.setattr(AB, "esegui", lambda p: esito if p == params else None)
    assert W.process_one() is True
    assert st["esiti"] == [("R1", esito)]
    assert st["status"] == [("R1", "DONE", None)]
    assert st["backtest"] == []                      # mai il backtest di sempre


def test_worker_applica_bot_errore_dichiarato(worker, monkeypatch):
    W, st = worker
    monkeypatch.setattr(W.db, "claim_backtest_request",
                        lambda: {"id": "R2", "params": {"tipo": "applica_bot", "bot": "x"}})
    assert W.process_one() is True
    assert st["esiti"] == []
    assert st["status"][-1][:2] == ("R2", "ERROR") and "non applicabile" in st["status"][-1][2]


def test_worker_backtest_di_sempre_invariato(worker, monkeypatch):
    W, st = worker
    monkeypatch.setattr(W.db, "claim_backtest_request",
                        lambda: {"id": "R3", "params": {"event_ids": ["1"]}})
    assert W.process_one() is True
    assert st["backtest"] == [{"event_ids": ["1"]}] and st["esiti"] == []
    assert st["status"] == [("R3", "DONE", None)]
