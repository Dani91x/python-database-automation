"""Registrazione OPT-IN "Segui live" (cantiere 17/07).

Requisito: la registrazione raw + l'upload nel Replay avvengono SOLO per le
partite scelte col pulsante "Segui live" (live_follow.record=true). Per tutte
le altre: streaming, missioni, trading, ladder e ordini IDENTICI, ma niente
file raw e niente upload. Fallback: colonna ``record`` assente (migrazione non
applicata) → comportamento storico (registra tutto) + warning, mai rompere.
"""
from __future__ import annotations

import json
import os
import threading
from types import SimpleNamespace

from Betfair.stream.raw_listener import _RawState

EV_REC = "111"        # partita CON "Segui live" (record=true)
EV_NOREC = "222"      # partita seguita SENZA registrazione
M_REC = "1.111"
M_NOREC = "1.222"
M2E = {M_REC: EV_REC, M_NOREC: EV_NOREC}


def _mcm_line(market_id: str, pt: int = 1_000) -> str:
    return json.dumps({
        "op": "mcm", "clk": "1", "pt": pt,
        "mc": [{"id": market_id, "rc": [{"id": 1, "ltp": 2.0}]}],
    })


def _read_jsonl(path: str) -> list:
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _raw_path(tmp_path, ev: str) -> str:
    return os.path.join(str(tmp_path), ev, f"{ev}.raw.jsonl")


# ---------------------------------------------------------------------------
# 1) gating del tee: scrive SOLO gli eventi con record=true
# ---------------------------------------------------------------------------
def test_tee_scrive_solo_eventi_record(tmp_path):
    state = _RawState()
    state.configure(str(tmp_path), M2E, True, record_events={EV_REC})
    state.write_message(_mcm_line(M_REC))
    state.write_message(_mcm_line(M_NOREC))
    state.close()

    assert len(_read_jsonl(_raw_path(tmp_path, EV_REC))) == 1
    # per l'evento NON in registrazione: niente file, niente directory
    assert not os.path.exists(os.path.join(str(tmp_path), EV_NOREC))


def test_tee_fallback_none_registra_tutto(tmp_path):
    """record_events=None = colonna assente/tennis → comportamento storico."""
    state = _RawState()
    state.configure(str(tmp_path), M2E, True)  # nessun gating
    state.write_message(_mcm_line(M_REC))
    state.write_message(_mcm_line(M_NOREC))
    state.close()
    assert os.path.exists(_raw_path(tmp_path, EV_REC))
    assert os.path.exists(_raw_path(tmp_path, EV_NOREC))


def test_tee_toggle_a_meta_partita(tmp_path):
    """Click "Segui live" a partita in corso: l'evento entra nel set → il tee
    inizia a scrivere DA QUEL MOMENTO. Spegnere lo toglie subito."""
    state = _RawState()
    state.configure(str(tmp_path), M2E, True, record_events=set())
    state.write_message(_mcm_line(M_NOREC, pt=1_000))
    assert not os.path.exists(os.path.join(str(tmp_path), EV_NOREC))

    state.set_record_events({EV_NOREC})          # toggle ON dal runner
    state.write_message(_mcm_line(M_NOREC, pt=2_000))
    state.write_message(_mcm_line(M_NOREC, pt=3_000))

    state.set_record_events(set())               # toggle OFF
    state.write_message(_mcm_line(M_NOREC, pt=4_000))
    state.close()

    rows = _read_jsonl(_raw_path(tmp_path, EV_NOREC))
    assert [r["pt"] for r in rows] == [2_000, 3_000]  # solo la finestra ON


def test_tee_messaggio_misto_scrive_solo_il_record(tmp_path):
    """Un solo mcm con market change di ENTRAMBI gli eventi: nel raw finisce
    solo la parte dell'evento in registrazione."""
    state = _RawState()
    state.configure(str(tmp_path), M2E, True, record_events={EV_REC})
    msg = json.dumps({
        "op": "mcm", "clk": "1", "pt": 5_000,
        "mc": [{"id": M_REC, "rc": [{"id": 1, "ltp": 2.0}]},
               {"id": M_NOREC, "rc": [{"id": 2, "ltp": 3.0}]}],
    })
    state.write_message(msg)
    state.close()
    rows = _read_jsonl(_raw_path(tmp_path, EV_REC))
    assert len(rows) == 1
    assert [c["id"] for c in rows[0]["mc"]] == [M_REC]
    assert not os.path.exists(os.path.join(str(tmp_path), EV_NOREC))


def test_battito_dati_aggiornato_anche_senza_registrazioni(tmp_path):
    """Con zero partite in registrazione lo stream NON deve sembrare morto:
    last_data_ms avanza anche per i messaggi scartati dal gating (il runner
    misura lo stallo su questo, non sui write raw)."""
    state = _RawState()
    state.configure(str(tmp_path), M2E, True, record_events=set())
    state.write_message(_mcm_line(M_NOREC, pt=7_777))
    h = state.health()
    assert h["last_data_ms"] == 7_777
    assert h["last_write_ms"] == {}      # nessun write raw (gating attivo)
    assert not os.path.exists(os.path.join(str(tmp_path), EV_NOREC))


def test_mark_resubscribe_non_crea_sidecar_per_non_record(tmp_path):
    state = _RawState()
    state.configure(str(tmp_path), M2E, True, record_events={EV_REC})
    state.write_message(_mcm_line(M_REC))
    state.mark_resubscribe("test")
    state.close()
    assert os.path.exists(os.path.join(str(tmp_path), EV_REC, f"{EV_REC}.recmeta.jsonl"))
    assert not os.path.exists(os.path.join(str(tmp_path), EV_NOREC))


# ---------------------------------------------------------------------------
# 2) _sync_record_events (runner): set aggiornato + fallback colonna assente
# ---------------------------------------------------------------------------
def _session_ns() -> SimpleNamespace:
    return SimpleNamespace(record_events=None, _record_col_warned=False)


def test_sync_record_events_costruisce_il_set(monkeypatch):
    from Betfair.stream import runner as R
    import Betfair.stream.raw_listener as RL

    pushed = []
    monkeypatch.setattr(RL.RAW_STATE, "set_record_events",
                        lambda s: pushed.append(s))
    session = _session_ns()
    follows = [
        {"event_id": "111", "status": "STREAMING", "record": True},
        {"event_id": "222", "status": "PENDING", "record": False},
        {"event_id": "333", "status": "PENDING", "record": None},
    ]
    R._sync_record_events(session, follows)
    assert session.record_events == {"111"}
    assert pushed == [{"111"}]


def test_sync_record_events_fallback_colonna_assente(monkeypatch, caplog):
    from Betfair.stream import runner as R
    import Betfair.stream.raw_listener as RL

    pushed = []
    monkeypatch.setattr(RL.RAW_STATE, "set_record_events",
                        lambda s: pushed.append(s))
    session = _session_ns()
    follows = [{"event_id": "111", "status": "STREAMING"}]  # nessuna chiave record
    import logging
    with caplog.at_level(logging.WARNING):
        R._sync_record_events(session, follows)
        R._sync_record_events(session, follows)  # warning UNA volta sola
    assert session.record_events is None         # gating DISATTIVATO
    assert pushed == [None, None]
    warns = [r for r in caplog.records if "live_follow.record ASSENTE" in r.message]
    assert len(warns) == 1


def test_sync_record_events_follows_vuoti(monkeypatch):
    from Betfair.stream import runner as R
    import Betfair.stream.raw_listener as RL

    monkeypatch.setattr(RL.RAW_STATE, "set_record_events", lambda s: None)
    session = _session_ns()
    R._sync_record_events(session, [])
    assert session.record_events == set()        # niente da registrare


# ---------------------------------------------------------------------------
# 3) finalize: upload SOLO se record=true; CLOSED pulito senza upload
# ---------------------------------------------------------------------------
def _finalize_env(monkeypatch, record_flag):
    from Betfair.stream import runner as R

    statuses = []
    uploads = []
    monkeypatch.setattr(R.db, "set_follow_status",
                        lambda ev, st, detail=None: statuses.append((ev, st)))
    monkeypatch.setattr(R.db, "get_follow_record", lambda ev: record_flag)
    monkeypatch.setattr(R.uploader, "upload_event",
                        lambda ev: uploads.append(ev) or {"event_id": ev})
    session = SimpleNamespace(
        _finalize_lock=threading.Lock(),
        finished_events=set(),
        pollers={},
        _score_files={},
    )
    return R, session, statuses, uploads


def test_finalize_senza_record_chiude_senza_upload(monkeypatch):
    R, session, statuses, uploads = _finalize_env(monkeypatch, record_flag=False)
    R._finalize_event("999", session)
    assert uploads == []                          # MAI upload senza opt-in
    assert statuses == [("999", "CLOSED")]        # status terminale pulito
    assert "999" in session.finished_events       # mai follow appesi


def test_finalize_con_record_carica_nel_replay(monkeypatch):
    R, session, statuses, uploads = _finalize_env(monkeypatch, record_flag=True)
    R._finalize_event("999", session)
    assert uploads == ["999"]
    assert statuses == [("999", "CLOSED")]        # UPLOADED lo mette l'uploader


def test_finalize_record_ignoto_comportamento_storico(monkeypatch):
    """record=None (colonna assente / DB KO) → si carica come sempre: meglio
    un upload di troppo che perdere una registrazione voluta."""
    R, session, statuses, uploads = _finalize_env(monkeypatch, record_flag=None)
    R._finalize_event("999", session)
    assert uploads == ["999"]


# ---------------------------------------------------------------------------
# 4) sweep: salta i non-record (ma li chiude), carica i record, storico se
#    la colonna non esiste
# ---------------------------------------------------------------------------
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


def _sweep_env(monkeypatch, tmp_path, rows):
    from datetime import datetime, timedelta, timezone

    import Betfair.stream.uploader as up
    import db_client

    now = datetime.now(timezone.utc)
    for r in rows:
        r.setdefault("open_date", (now - timedelta(hours=4)).isoformat())
        ev = r["event_id"]
        p = tmp_path / f"{ev}.jsonl"
        p.write_text("{}", encoding="utf-8")
        old = (now - timedelta(minutes=60)).timestamp()
        os.utime(p, (old, old))                  # file fermo da 1h
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: _fake_sb(rows))
    monkeypatch.setattr(up, "market_file", lambda ev: str(tmp_path / f"{ev}.jsonl"))
    uploaded = []
    monkeypatch.setattr(up, "upload_event",
                        lambda ev: uploaded.append(ev) or {"event_id": ev})
    closed = []
    monkeypatch.setattr(up.db, "set_follow_status",
                        lambda ev, st, detail=None: closed.append((ev, st)))
    return up, uploaded, closed


def test_sweep_salta_non_record_e_carica_i_record(monkeypatch, tmp_path):
    rows = [
        {"event_id": "111", "status": "ERROR", "record": True},
        {"event_id": "222", "status": "STREAMING", "record": False},
        {"event_id": "333", "status": "CLOSED", "record": False},
    ]
    up, uploaded, closed = _sweep_env(monkeypatch, tmp_path, rows)
    out = up.sweep_pending(min_idle_min=10.0)
    assert uploaded == ["111"]                    # solo l'opt-in
    assert [o["event_id"] for o in out] == ["111"]
    # il follow non-record rimasto STREAMING viene chiuso pulito, senza upload;
    # quello gia' CLOSED non viene ritoccato
    assert closed == [("222", "CLOSED")]


def test_sweep_colonna_assente_comportamento_storico(monkeypatch, tmp_path):
    rows = [
        {"event_id": "444", "status": "ERROR"},   # nessuna chiave record
    ]
    up, uploaded, closed = _sweep_env(monkeypatch, tmp_path, rows)
    up.sweep_pending(min_idle_min=10.0)
    assert uploaded == ["444"]                    # storico: carica tutto
    assert closed == []


# ---------------------------------------------------------------------------
# 5) register_follow: record dal flag watchlist "Segui live"; mai downgrade;
#    fallback upsert senza colonna
# ---------------------------------------------------------------------------
class _UpsertRecorder:
    """Fake supabase: registra le righe upsert su live_follow e risponde al
    lookup follow_live su personal_watchlist."""

    def __init__(self, follow_live=None, fail_with_record=False):
        self.follow_live = follow_live
        self.fail_with_record = fail_with_record
        self.upserts = []

    def table(self, name):
        outer = self

        class _Q:
            def __init__(self):
                self._name = name
                self._row = None

            def select(self, *_a, **_k):
                return self

            def eq(self, *_a, **_k):
                return self

            def limit(self, *_a, **_k):
                return self

            def upsert(self, row, **_k):
                self._row = row
                return self

            def execute(self):
                if self._name == "personal_watchlist":
                    data = ([{"follow_live": outer.follow_live}]
                            if outer.follow_live is not None else [])
                    return SimpleNamespace(data=data)
                if self._row is not None:
                    if outer.fail_with_record and "record" in self._row:
                        raise RuntimeError("column live_follow.record does not exist")
                    outer.upserts.append(dict(self._row))
                return SimpleNamespace(data=[])

        return _Q()


def test_register_follow_segui_live_imposta_record_true(monkeypatch):
    from Betfair.stream import db as sdb

    sb = _UpsertRecorder(follow_live=True)
    monkeypatch.setattr(sdb, "get_supabase_client", lambda: sb)
    sdb.register_follow("111", "Casa", "Ospite", "2026-07-17T20:00:00Z",
                        watchlist_id=5)
    assert len(sb.upserts) == 1
    assert sb.upserts[0].get("record") is True


def test_register_follow_giocata_senza_segui_live_non_tocca_record(monkeypatch):
    """GIOCATA con follow_live=false: la colonna record NON entra nell'upsert
    (mai degradare a false una scelta accesa da set_follow_record)."""
    from Betfair.stream import db as sdb

    sb = _UpsertRecorder(follow_live=False)
    monkeypatch.setattr(sdb, "get_supabase_client", lambda: sb)
    sdb.register_follow("222", "Casa", "Ospite", "2026-07-17T20:00:00Z",
                        watchlist_id=6)
    assert len(sb.upserts) == 1
    assert "record" not in sb.upserts[0]


def test_register_follow_fallback_colonna_assente(monkeypatch):
    """Migrazione non applicata: il primo upsert (con record) fallisce → retry
    senza record, il follow viene comunque registrato (mai rompere il runner)."""
    from Betfair.stream import db as sdb

    sb = _UpsertRecorder(follow_live=True, fail_with_record=True)
    monkeypatch.setattr(sdb, "get_supabase_client", lambda: sb)
    monkeypatch.setattr(sdb, "_RECORD_COL_MISSING_WARNED", False)
    sdb.register_follow("333", "Casa", "Ospite", "2026-07-17T20:00:00Z",
                        watchlist_id=7)
    assert len(sb.upserts) == 1
    assert "record" not in sb.upserts[0]


# ---------------------------------------------------------------------------
# 6) get_follow_record: True/False dal DB, None su colonna assente/errore
# ---------------------------------------------------------------------------
def test_get_follow_record(monkeypatch):
    from Betfair.stream import db as sdb

    class _SB:
        def __init__(self, rows=None, raise_=False):
            self._rows = rows
            self._raise = raise_

        def table(self, *_a):
            return self

        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def execute(self):
            if self._raise:
                raise RuntimeError("column live_follow.record does not exist")
            return SimpleNamespace(data=self._rows)

    monkeypatch.setattr(sdb, "get_supabase_client",
                        lambda: _SB(rows=[{"record": True}]))
    assert sdb.get_follow_record("1") is True
    monkeypatch.setattr(sdb, "get_supabase_client",
                        lambda: _SB(rows=[{"record": False}]))
    assert sdb.get_follow_record("1") is False
    monkeypatch.setattr(sdb, "get_supabase_client", lambda: _SB(rows=[]))
    assert sdb.get_follow_record("1") is None    # riga mancante → storico
    monkeypatch.setattr(sdb, "get_supabase_client", lambda: _SB(raise_=True))
    monkeypatch.setattr(sdb, "_RECORD_COL_MISSING_WARNED", False)
    assert sdb.get_follow_record("1") is None    # colonna assente → storico
