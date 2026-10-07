"""Caricamento AUTOMATICO nel Replay Tennis a fine partita, dentro il runner tennis.

Il tee del recorder tennis (``tennis_live/tennis_recorder.py``) vede passare il
raw della partita registrata: quando la marketDefinition del MATCH_ODDS diventa
``CLOSED`` programma UNA volta, in un thread dello stesso processo, conversione e
caricamento. Qui: il messaggio vero di chiusura (formato dello stream), il
caricamento sostituito da un finto che registra la chiamata, il thread atteso.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, List

import pytest

from Betfair.stream.tennis_live import tennis_recorder as trec
from Betfair.stream.tennis_replay import caricamento as car
from Betfair.stream.tennis_replay.tests import dati_tennis as dt

EV = "35999999"


@pytest.fixture()
def tee(tmp_path, monkeypatch):
    monkeypatch.setenv("TENNIS_REPLAY_CARICA_DOPO_S", "0")
    monkeypatch.delenv("TENNIS_REPLAY_CARICA", raising=False)
    t = trec.TennisRawTee()
    t.dir = str(tmp_path)
    return t


@pytest.fixture()
def chiamate(monkeypatch) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    def finto(rt, *, fonte, raw_files=None, raw_bytes=None):
        out.append({"rt": rt, "fonte": fonte, "raw_files": raw_files, "raw_bytes": raw_bytes})
        return {}

    monkeypatch.setattr(car, "carica_replay", finto)
    return out


def _solo_match_odds() -> List[str]:
    """Le righe del file A della partita costruita, col solo mercato MATCH_ODDS."""
    righe = []
    for r in dt.partita_costruita()["a"]:
        m = json.loads(r)
        m["mc"] = [c for c in m["mc"] if c["id"] == dt.MO]
        if m["mc"]:
            righe.append(json.dumps(m, separators=(",", ":")))
    return righe


def _attendi(t: trec.TennisRawTee) -> None:
    """Attende TUTTI i thread di caricamento (anche quelli non piu' nel dizionario)."""
    for timer in list(t._fine_programmata.values()):
        timer.join(timeout=30)
    for th in threading.enumerate():
        if th.name.startswith("tennis-replay-"):
            th.join(timeout=30)


def test_chiusura_del_match_odds_carica_una_volta(tee, chiamate) -> None:
    meta = {"market_id": dt.MO, "selection_names": {"101": "Giocatore Uno", "202": "Giocatore Due"},
            "competition_name": "ATP Prova"}
    tee.enable(EV, [dt.MO], meta=meta)
    righe = _solo_match_odds()
    for r in righe:
        tee.write_message(r)
    tee.write_message(righe[-1])  # una seconda chiusura non riprogramma
    _attendi(tee)
    assert len(chiamate) == 1
    c = chiamate[0]
    assert c["fonte"] == "runner" and c["raw_files"][0].endswith(f"{EV}.raw.jsonl") and c["raw_bytes"] > 0
    rt = c["rt"]
    assert rt.evento["competition_name"] == "ATP Prova"
    assert (rt.evento["player1_name"], rt.evento["player2_name"]) == ("Giocatore Uno", "Giocatore Due")
    assert [s["status"] for s in rt.mercati[0]["selections"]] == ["LOSER", "WINNER"]
    assert rt.snapshot[-1]["status"] == "CLOSED"


def test_niente_caricamento_senza_chiusura_o_se_spento(tee, chiamate, monkeypatch) -> None:
    tee.enable(EV, [dt.MO])
    for r in _solo_match_odds()[:-1]:  # tutto tranne la chiusura
        tee.write_message(r)
    _attendi(tee)
    assert chiamate == [] and tee._fine_programmata == {}
    monkeypatch.setenv("TENNIS_REPLAY_CARICA", "0")
    tee.write_message(_solo_match_odds()[-1])
    _attendi(tee)
    assert chiamate == [] and tee._fine_programmata == {}


def test_chiusura_di_un_altro_mercato_o_evento_non_registrato(tee, chiamate) -> None:
    # SET_BETTING chiuso: la partita non e' finita
    chiuso_sb = json.dumps({"op": "mcm", "clk": "x", "pt": 1783427400000, "mc": [{"id": dt.SB, "marketDefinition": dict(
        json.loads(dt.partita_costruita()["b"][0])["mc"][0]["marketDefinition"], status="CLOSED")}]})
    tee.enable(EV, [dt.MO, dt.SB])
    tee.write_message(chiuso_sb)
    # MATCH_ODDS chiuso di un evento NON registrato (opt-in): nessun file, nessun caricamento
    tee.market_to_event["1.555"] = "altro"
    chiuso_mo = json.loads(_solo_match_odds()[-1])
    chiuso_mo["mc"][0]["id"] = "1.555"
    tee.write_message(json.dumps(chiuso_mo))
    _attendi(tee)
    assert chiamate == [] and tee._fine_programmata == {}


def test_errore_del_caricamento_e_solo_un_avviso(tee, monkeypatch, caplog) -> None:
    def rotto(*_a, **_k):
        raise RuntimeError("relation tennis_replay_eventi does not exist")

    monkeypatch.setattr(car, "carica_replay", rotto)
    tee.enable(EV, [dt.MO])
    with caplog.at_level(logging.WARNING):
        for r in _solo_match_odds():
            tee.write_message(r)
        _attendi(tee)
    assert any("NON caricato" in r.message and "importa" in r.message for r in caplog.records)
    # il tee continua a registrare
    tee.write_message(_solo_match_odds()[1])
    assert tee.counts()[EV] == len(_solo_match_odds()) + 1


def test_sync_record_flags_passa_il_catalogo_del_runner(tee) -> None:
    meta = {EV: {"market_id": dt.MO, "selection_names": {"101": "Uno"}, "competition_name": "ATP"}}
    assert trec.sync_record_flags([{"event_id": EV, "record": True}], meta, tee=tee) == {EV}
    assert tee._meta[EV]["selection_names"] == {"101": "Uno"}


def test_tutti_i_mercati_della_partita_registrata_coi_nomi_del_catalogo(tee, chiamate) -> None:
    """07/10 (REC su tutti i mercati): il file porta anche TOTAL_GAMES; il
    catalogo del runner (``mercati_registrati``) da' nome del mercato e dei runner."""
    meta = {"market_id": dt.MO, "selection_names": {"101": "Giocatore Uno", "202": "Giocatore Due"},
            "mercati_registrati": [{"market_id": dt.TG, "market_type": "TOTAL_GAMES",
                                    "market_name": "Total Games 22.5",
                                    "selection_names": {"301": "Under 22.5", "302": "Over 22.5"}}]}
    tee.enable(EV, [dt.MO, dt.TG], meta=meta)
    for r in dt.partita_costruita()["a"]:
        tee.write_message(r)
    _attendi(tee)
    assert len(chiamate) == 1
    per = {m["market_id"]: m for m in chiamate[0]["rt"].mercati}
    assert set(per) == {dt.MO, dt.TG}
    assert per[dt.TG]["market_name"] == "Total Games 22.5"
    assert [s["name"] for s in per[dt.TG]["selections"]] == ["Under 22.5", "Over 22.5"]
    assert per[dt.MO]["market_name"] == "Match Odds"
