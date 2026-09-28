"""Incrocio dei cantieri A (fine evento, 7a83206) e B (frammenti di mercato), 28/09.

Con flumine VERO, il recorder VERO del runner (``MarketRecorderStrategy``: una
sola istanza, agganciata a TUTTI i frammenti) e le funzioni vere del runner
(``mercati_manuali_vivi``, ``mercati_manuali_da_sottoscrivere``,
``_rilascia_mercati_finiti``, ``_frammento0``):

1. una partita i cui mercati stanno su frammenti DIVERSI e' dichiarata finita
   UNA volta sola, e ``mercati_chiusi`` vede i mercati di tutti i frammenti;
2. partita finita su un frammento aperto a caldo: i suoi mercati escono dal
   piano e dalla sottoscrizione, il frammento rimasto vuoto si CHIUDE;
3. ricostruzione con partite finite e piu' di un frammento: le finite non
   rientrano, le vive si distribuiscono su due connessioni;
4. uscita ordinata con due frammenti: ``Flumine.__exit__`` ->
   ``streams.stop()`` chiude TUTTE le connessioni, anche quelle aperte a caldo,
   nessun thread resta vivo e il gestore non ne riapre (test TCP in
   ``test_frammenti_tcp_2026_09_28.py``); ``arresto_worker`` resta registrato.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, Dict, List, Set

import pytest

from Betfair.stream import auto_follow as AF
from Betfair.stream import frammenti_mercato as FR
from Betfair.stream import runner as R
from Betfair.stream import sottoscrizione_a_caldo as SC

from .test_frammenti_mercato_2026_09_28 import (
    _chiudi_mercato, _collega, _framework, _gestore, _ids, _market_streams)

EV = "35784105"
MO = "1.259691614"          # MATCH_ODDS della registrazione .it
OU = "1.900001"


def _dove(fw: Any) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for i, s in enumerate(FR.GestoreFrammenti.frammenti(fw)):
        for m in SC.mercati_dello_stream(s):
            out[m] = i
    return out


def _sessione(rec: Any, event_markets: Dict[str, Set[str]], finite: Set[str]) -> Any:
    m2e = {m: ev for ev, ms in event_markets.items() for m in ms}
    return SimpleNamespace(recorder=rec, event_markets=event_markets, market_to_event=m2e,
                           finished_events=set(finite))


def _pronto(monkeypatch, manuali: Dict[str, Set[str]]):
    """Framework col frammento 0 = primi 180 mercati (come la build), auto-follow
    col gestore vero, manuali impostati, un giro -> frammenti in piu'."""
    fw, rec, live = _framework(_ids(0, 180))
    _collega(_market_streams(fw)[0])
    g, orologio, avviati = _gestore()
    af = AF.AutoFollow(piano=AF.PianoFollow(g.capacita(None)), sottoscrittore=g,
                       min_intervallo_s=0.0)
    monkeypatch.setitem(R._MOTORE, "auto", af)
    af.imposta_manuali(manuali)
    af.aggancia(fw, _ids(0, 180))
    af.giro()
    # il recorder vero conosce i mercati manuali (come in runner.setup_and_run)
    for ev, ms in manuali.items():
        rec.context["event_markets"][ev] = set(ms)
        for m in ms:
            rec.context["market_to_event"][m] = ev
    rec.context["market_type_by_id"].update({MO: "MATCH_ODDS", OU: "OVER_UNDER_25"})
    return fw, rec, live, g, af, avviati


def test_partita_su_frammenti_diversi_finita_una_volta_sola(monkeypatch):
    # OU sta nel frammento 0 (fra i primi 180), MO su quello aperto a caldo
    ou0 = _ids(0, 180)[5]
    manuali = {"E0": set(_ids(0, 180)) - {ou0}, EV: {MO, ou0}}
    fw, rec, _live, _g, _af, _a = _pronto(monkeypatch, manuali)
    rec.context["market_type_by_id"][ou0] = "OVER_UNDER_25"
    dove = _dove(fw)
    assert dove[MO] == 1 and dove[ou0] == 0            # due frammenti diversi
    fr = FR.GestoreFrammenti.frammenti(fw)
    assert rec in [s for s in fw.strategies] and fr[1] in rec.streams
    assert _chiudi_mercato(fw, fr[0], ou0) == 1
    assert _chiudi_mercato(fw, fr[1], MO) == 1
    assert rec.mercati_chiusi(EV) == {MO, ou0}          # entrambi i frammenti
    assert rec.drain_finished() == [EV]                 # una volta sola
    assert rec.drain_finished() == []


def test_partita_finita_su_frammento_a_caldo_rilasciata_e_frammento_chiuso(monkeypatch):
    manuali = {"E0": set(_ids(0, 180)), EV: {MO, OU}}
    fw, rec, _live, g, af, _a = _pronto(monkeypatch, manuali)
    fr = FR.GestoreFrammenti.frammenti(fw)
    assert len(fr) == 2 and set(SC.mercati_dello_stream(fr[1])) == {MO, OU}
    _chiudi_mercato(fw, fr[1], MO)
    _chiudi_mercato(fw, fr[1], OU)
    assert rec.drain_finished() == [EV]
    sessione = _sessione(rec, manuali, {EV})
    assert R.mercati_manuali_vivi(sessione) == {"E0": set(_ids(0, 180))}
    R._rilascia_mercati_finiti(sessione)                # quello che fa _finalize_event
    af.giro()
    assert not ({MO, OU} & af.piano.mercati())
    assert fr[1].chiuso and FR.GestoreFrammenti.frammenti(fw) == [fr[0]]
    assert g.stato(fw)["connessioni_di_mercato"] == 1
    assert af.stato()["mercati_sottoscritti"] == 180


def test_ricostruzione_con_partite_finite_e_piu_frammenti(monkeypatch):
    monkeypatch.setattr(R.db, "insert_alert", lambda *a, **k: None)
    manuali = {"E1": set(_ids(0, 150)), "E2": set(_ids(150, 250)), "E3": set(_ids(250, 300))}
    fw0, rec, _l = _framework(["1.1"])
    for ev, ms in manuali.items():
        rec.context["event_markets"][ev] = set(ms)
    # E3 finita: tutti i suoi mercati chiusi (visti dal recorder)
    rec._closed_markets["E3"] = set(_ids(250, 300))
    sessione = _sessione(rec, manuali, {"E3"})
    market_ids = R.mercati_manuali_da_sottoscrivere(sessione)
    assert len(market_ids) == 250 and not (set(market_ids) & set(_ids(250, 300)))
    g, _o, _a = _gestore()
    af = AF.AutoFollow(piano=AF.PianoFollow(g.capacita(None)), sottoscrittore=g,
                       min_intervallo_s=0.0)
    monkeypatch.setitem(R._MOTORE, "auto", af)
    af.imposta_manuali(R.mercati_manuali_vivi(sessione))
    af.rientra_nel_tetto()
    ids0 = R._frammento0(market_ids, market_ids, af, set(), {})
    assert len(ids0) == 180 and not (set(ids0) & set(_ids(250, 300)))
    fw, _rec, _live = _framework(ids0)
    _collega(_market_streams(fw)[0])
    af.aggancia(fw, ids0)
    af.giro()
    tutti = set()
    for s in FR.GestoreFrammenti.frammenti(fw):
        tutti |= set(SC.mercati_dello_stream(s))
    assert tutti == set(market_ids)
    assert len(FR.GestoreFrammenti.frammenti(fw)) == 2


def test_arresto_ordinato_registrato_e_nessuna_apertura_su_framework_fermo(monkeypatch):
    src = inspect.getsource(R.setup_and_run)
    assert "function=arresto_worker" in src
    fw, _rec, _live = _framework(_ids(0, 180))
    _collega(_market_streams(fw)[0])
    g, _o, avviati = _gestore()
    g.applica(fw, _ids(0, 250))
    fr = FR.GestoreFrammenti.frammenti(fw)
    assert len(fr) == 2
    fw.streams.stop()                        # quello che fa Flumine.__exit__ (baseflumine.py:523)
    assert all(s.chiuso for s in fr)
    assert FR.GestoreFrammenti.frammenti(fw) == []
    with pytest.raises(SC.NonPronto):        # il thread dell'auto-follow arriva dopo
        g.applica(fw, _ids(0, 400))
    assert len(avviati) == 1                  # nessuna connessione nuova
