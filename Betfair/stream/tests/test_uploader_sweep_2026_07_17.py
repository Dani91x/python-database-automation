"""Sweep Replay — guardia anti-hijack dei match VIVI (incidente 17/07).

Il solo "raw fermo da N minuti" non prova la fine: dopo una finestra di
riavvii dell'exe, lo sweep marcava UPLOADED una partita in corso mentre il
runner la stava ri-streamando (UI bloccata su "In attesa dello stream…").
Regola pinnata: un follow col kickoff entro la soglia stantia (3h) non viene
MAI toccato dallo sweep, qualunque sia l'idle del file.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import Betfair.stream.uploader as up


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _fake_sb(rows):
    class _Q:
        def __init__(self, data):
            self._d = data

        def select(self, *_a, **_k):
            return self

        def neq(self, *_a, **_k):
            return self

        def execute(self):
            return SimpleNamespace(data=self._d)

    return SimpleNamespace(table=lambda *_: _Q(rows))


def test_sweep_salta_i_match_potenzialmente_vivi(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    rows = [
        # kickoff 90 min fa: match VIVO anche se il raw è fermo → MAI sweep
        {"event_id": "111", "status": "STREAMING", "open_date": _iso(now - timedelta(minutes=90))},
        # kickoff 4h fa: certamente finita → sweep legittimo
        {"event_id": "222", "status": "ERROR", "open_date": _iso(now - timedelta(hours=4))},
    ]
    for ev in ("111", "222"):
        p = tmp_path / f"{ev}.jsonl"
        p.write_text("{}", encoding="utf-8")
        old = (now - timedelta(minutes=60)).timestamp()
        os.utime(p, (old, old))  # raw fermo da 1h per ENTRAMBI

    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: _fake_sb(rows))
    monkeypatch.setattr(up, "market_file", lambda ev: str(tmp_path / f"{ev}.jsonl"))
    uploaded = []
    monkeypatch.setattr(up, "upload_event", lambda ev: uploaded.append(ev) or {"event_id": ev})

    out = up.sweep_pending(min_idle_min=10.0)

    assert uploaded == ["222"]           # solo la partita certamente finita
    assert [o["event_id"] for o in out] == ["222"]


def test_sweep_open_date_illeggibile_ricade_su_idle(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    rows = [{"event_id": "333", "status": "ERROR", "open_date": "boh"}]
    p = tmp_path / "333.jsonl"
    p.write_text("{}", encoding="utf-8")
    old = (now - timedelta(minutes=60)).timestamp()
    os.utime(p, (old, old))

    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: _fake_sb(rows))
    monkeypatch.setattr(up, "market_file", lambda ev: str(tmp_path / f"{ev}.jsonl"))
    uploaded = []
    monkeypatch.setattr(up, "upload_event", lambda ev: uploaded.append(ev) or {"event_id": ev})

    up.sweep_pending(min_idle_min=10.0)
    assert uploaded == ["333"]  # comportamento storico preservato
