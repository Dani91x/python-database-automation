"""Registrazione OPT-IN per-partita tennis (cantiere 17/07).

Coprono il contratto del tee raw dedicato (tennis_live/tennis_recorder):
  * gating per-evento: NIENTE file per gli eventi senza record=true (default
    storico del tennis), tee attivo solo per gli eventi scelti;
  * toggle a metà partita: enable → disable → re-enable senza riavvii, con
    ripresa in append sullo stesso file;
  * formato su disco identico al recorder della missione 1-tick
    (record_multi): <dir>/<event>/<event>.raw.jsonl con messaggi mcm nativi
    replayabili (op/clk/pt preservati) + <event>.score.jsonl dedup su score key;
  * fallback conservativo: colonna `record` assente (migrazione
    tennis_follow_record.sql non applicata) → nessuna registrazione + warning
    una tantum, mai eccezioni;
  * il runner usa TennisRecMarketStream sulla capture (stream unico col tee).
"""
from __future__ import annotations

import json
import logging
import os

import pytest

from Betfair.stream.tennis_live import tennis_recorder as tr
from Betfair.stream.tennis_live.tennis_recorder import (
    TennisRawTee,
    TennisRecMarketStream,
    _TennisRecListener,
    sync_record_flags,
)


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------
def _mcm(market_id: str, pt: int = 1_000, with_def: str | None = None) -> str:
    change = {"id": market_id, "rc": [{"id": 123, "ltp": 1.5}]}
    if with_def:
        change["marketDefinition"] = {"eventId": with_def}
    return json.dumps({"op": "mcm", "clk": "c1", "pt": pt, "mc": [change]})


def _tee(tmp_path) -> TennisRawTee:
    tee = TennisRawTee()
    tee.dir = str(tmp_path)
    return tee


class _FakeScore:
    def __init__(self, key, raw):
        self._key = key
        self.raw = raw

    def key(self):
        return self._key


def _raw_lines(tmp_path, ev: str):
    path = os.path.join(str(tmp_path), ev, f"{ev}.raw.jsonl")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# gating per-evento (opt-in)
# ---------------------------------------------------------------------------
def test_gating_off_nessun_file(tmp_path):
    """Evento non registrato → nessun file, nessun conteggio, dir intatta."""
    tee = _tee(tmp_path)
    tee.market_to_event["1.111"] = "ev1"  # routing noto ma evento NON abilitato
    tee.write_message(_mcm("1.111"))
    assert _raw_lines(tmp_path, "ev1") is None
    assert tee.counts() == {}
    assert os.listdir(str(tmp_path)) == []


def test_gating_on_scrive_formato_nativo(tmp_path):
    """Evento abilitato → <dir>/<event>/<event>.raw.jsonl con mcm replayabile."""
    tee = _tee(tmp_path)
    tee.enable("ev1", ["1.111"])
    tee.write_message(_mcm("1.111", pt=42))
    lines = _raw_lines(tmp_path, "ev1")
    assert lines is not None and len(lines) == 1
    msg = lines[0]
    assert msg["op"] == "mcm" and msg["pt"] == 42 and msg["clk"] == "c1"
    assert msg["mc"][0]["id"] == "1.111"
    assert tee.counts() == {"ev1": 1}


def test_solo_evento_scelto_su_stream_multi_mercato(tmp_path):
    """Due eventi sullo stesso processo: si registra SOLO quello opt-in."""
    tee = _tee(tmp_path)
    tee.market_to_event.update({"1.111": "ev1", "1.222": "ev2"})
    tee.enable("ev1", ["1.111"])
    tee.write_message(_mcm("1.111"))
    tee.write_message(_mcm("1.222"))
    assert len(_raw_lines(tmp_path, "ev1")) == 1
    assert _raw_lines(tmp_path, "ev2") is None


def test_mercato_non_routato_non_scrive(tmp_path):
    """Market ignoto (nessuna mappa, nessuna marketDefinition) → nessun file
    '_unrouted': l'opt-in registra solo eventi identificati."""
    tee = _tee(tmp_path)
    tee.enable("ev1", ["1.111"])
    tee.write_message(_mcm("1.999"))
    assert os.path.exists(os.path.join(str(tmp_path), "ev1", "ev1.raw.jsonl")) is False
    assert not os.path.exists(os.path.join(str(tmp_path), "_unrouted"))


def test_auto_routing_da_market_definition(tmp_path):
    """Il tee impara market→event dalla marketDefinition (come record_multi):
    copre i mercati visti sullo stream prima del giro del worker."""
    tee = _tee(tmp_path)
    tee.enable("ev1", [])
    tee.write_message(_mcm("1.333", with_def="ev1"))
    assert len(_raw_lines(tmp_path, "ev1")) == 1
    assert tee.market_to_event["1.333"] == "ev1"


# ---------------------------------------------------------------------------
# toggle a metà partita
# ---------------------------------------------------------------------------
def test_toggle_meta_partita_append(tmp_path):
    tee = _tee(tmp_path)
    tee.enable("ev1", ["1.111"])
    tee.write_message(_mcm("1.111", pt=1))
    tee.disable("ev1")
    tee.write_message(_mcm("1.111", pt=2))  # OFF: non scrive
    assert len(_raw_lines(tmp_path, "ev1")) == 1
    tee.enable("ev1", ["1.111"])
    tee.write_message(_mcm("1.111", pt=3))  # ON di nuovo: append
    pts = [m["pt"] for m in _raw_lines(tmp_path, "ev1")]
    assert pts == [1, 3]


def test_disable_idempotente_e_chiude_handle(tmp_path):
    tee = _tee(tmp_path)
    tee.enable("ev1", ["1.111"])
    tee.write_message(_mcm("1.111"))
    assert "ev1" in tee._files
    tee.disable("ev1")
    tee.disable("ev1")  # idempotente
    assert "ev1" not in tee._files
    assert tee.is_enabled("ev1") is False


# ---------------------------------------------------------------------------
# score tee (.score.jsonl, dedup su score key)
# ---------------------------------------------------------------------------
def test_score_tee_gating_e_dedup(tmp_path):
    tee = _tee(tmp_path)
    s1 = _FakeScore(("1-0",), {"currentSet": 1})
    tee.write_score("ev1", s1)  # evento NON abilitato → niente file
    tee.enable("ev1", ["1.111"])
    tee.write_score("ev1", s1)
    tee.write_score("ev1", s1)  # stessa key → dedup
    tee.write_score("ev1", _FakeScore(("2-0",), {"currentSet": 1}))
    path = os.path.join(str(tmp_path), "ev1", "ev1.score.jsonl")
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(x) for x in fh if x.strip()]
    assert len(rows) == 2
    assert all("t" in r and "score" in r for r in rows)  # formato record_multi


def test_score_tee_none_non_rompe(tmp_path):
    tee = _tee(tmp_path)
    tee.enable("ev1", ["1.111"])
    tee.write_score("ev1", None)  # feed KO: no-op


# ---------------------------------------------------------------------------
# robustezza del listener (il tee non deve MAI rompere lo stream)
# ---------------------------------------------------------------------------
def test_write_message_input_sporchi(tmp_path):
    tee = _tee(tmp_path)
    tee.enable("ev1", ["1.111"])
    for garbage in ("not-json", "", json.dumps({"op": "ocm"}),
                    json.dumps({"op": "mcm"})):
        tee.write_message(garbage)  # nessuna eccezione
    assert tee.counts() == {}


def test_listener_e_stream_class():
    """La capture del runner usa il MarketStream tennis col tee nel listener."""
    assert TennisRecMarketStream.LISTENER is _TennisRecListener
    from Betfair.stream.tennis_live import tennis_runner
    cap = tennis_runner._make_capture("1.111", "ev1")
    assert cap.stream_class is TennisRecMarketStream


# ---------------------------------------------------------------------------
# sync_record_flags (worker): flag DB → tee; fallback colonna assente
# ---------------------------------------------------------------------------
@pytest.fixture()
def _reset_warn(monkeypatch):
    monkeypatch.setattr(tr, "_MISSING_COLUMN_WARNED", False)


def test_sync_colonna_assente_fallback_conservativo(tmp_path, caplog, _reset_warn):
    """Migrazione non applicata (nessuna riga con chiave 'record') → NIENTE
    registrazione + warning una tantum. Mai eccezioni verso il chiamante."""
    tee = _tee(tmp_path)
    follows = [{"event_id": "ev1", "status": "STREAMING"}]
    meta = {"ev1": {"market_id": "1.111"}}
    with caplog.at_level(logging.WARNING):
        out1 = sync_record_flags(follows, meta, tee=tee)
        out2 = sync_record_flags(follows, meta, tee=tee)
    assert out1 == set() and out2 == set()
    assert tee.enabled_events == set()
    warns = [r for r in caplog.records if "tennis_follow_record.sql" in r.message]
    assert len(warns) == 1  # una tantum


def test_sync_toggle_on_off(tmp_path, _reset_warn):
    tee = _tee(tmp_path)
    meta = {"ev1": {"market_id": "1.111"}}
    on = [{"event_id": "ev1", "record": True}]
    off = [{"event_id": "ev1", "record": False}]
    assert sync_record_flags(on, meta, tee=tee) == {"ev1"}
    assert tee.is_enabled("ev1") and tee.market_to_event["1.111"] == "ev1"
    assert sync_record_flags(off, meta, tee=tee) == set()
    assert not tee.is_enabled("ev1")
    # follow sparito (match chiuso) → spegne anche senza riga
    assert sync_record_flags(on, meta, tee=tee) == {"ev1"}
    assert sync_record_flags([], meta, tee=tee) == set()
    assert not tee.is_enabled("ev1")


def test_sync_evento_non_catalogato_riprova(tmp_path, _reset_warn):
    """record=true ma evento non ancora in market_meta → non abilita (riproverà
    al prossimo giro del worker quando il runner l'avrà catalogato)."""
    tee = _tee(tmp_path)
    out = sync_record_flags([{"event_id": "ev9", "record": True}], {}, tee=tee)
    assert out == set() and tee.enabled_events == set()


def test_sync_righe_miste_non_scattano_fallback(tmp_path, caplog, _reset_warn):
    """Basta UNA riga con la chiave 'record' perché la colonna esista: nessun
    warning di migrazione mancante."""
    tee = _tee(tmp_path)
    follows = [
        {"event_id": "ev1", "record": True},
        {"event_id": "ev2", "record": False},
    ]
    meta = {"ev1": {"market_id": "1.111"}, "ev2": {"market_id": "1.222"}}
    with caplog.at_level(logging.WARNING):
        out = sync_record_flags(follows, meta, tee=tee)
    assert out == {"ev1"}
    assert not [r for r in caplog.records if "tennis_follow_record.sql" in r.message]


def test_sync_db_rotto_non_solleva(tmp_path, _reset_warn):
    """Input malformato (riga non-dict) → warning interno, nessuna eccezione."""
    tee = _tee(tmp_path)
    out = sync_record_flags([None, 42], {"ev1": {"market_id": "1.111"}}, tee=tee)  # type: ignore[list-item]
    assert out == set()
