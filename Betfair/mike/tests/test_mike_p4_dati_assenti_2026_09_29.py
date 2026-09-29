"""P4 BLOCCO 3 (29/09) - DATI CHE MANCANO: M8.4 (punteggio), M8.5 (quote).

  M8.4 - in gioco un punteggio che manca NON vale zero gol: si dichiara UNA
         volta per episodio (e quando torna), la scheda porta l'eta' del
         punteggio o «punteggio assente»; lo snapshot porta goals=None (le
         decisioni del motore sui gol sono del delegato del motore).
  M8.5 - una quota che sparisce si ricontrolla a ogni giro; se manca oltre
         `_DATO_ASSENTE_AVVISO_S` si avvisa UNA volta per episodio, e una volta
         quando torna (prima: subito e poi ogni 45 s finche' mancava).

Giro VERO (`service._run_event`), riga del feed con le chiavi vere
(`test_mike_feed.payload`), righe di `mike_trades` con le chiavi vere.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_p4_conti_dati_2026_09_29 import (  # noqa: F401
    KO, MercatoOrdini, _evento, _giro, _ingresso, _pulito, _riga)
from Betfair.mike.tests.test_mike_service import NOW, FakeDB


def _ctx_scoperto() -> E.MatchCtx:
    return E.MatchCtx(state="LIVE_UNCOVERED", legs=[_ingresso()], live_since=KO.timestamp(),
                      ko_goals=0)


def _log(db, kind, reason):
    return [p for k, p, _e in db.activity if k == kind and p.get("reason") == reason]


# ===========================================================================
# M8.4 - IL PUNTEGGIO CHE MANCA
# ===========================================================================
def test_punteggio_assente_in_gioco_si_dichiara_una_volta_e_quando_torna():
    db = FakeDB(mode="live")
    ctx = _ctx_scoperto()
    _riga(db, ctx.legs[0], status="open", bet_id="B0")
    mk = MercatoOrdini([])
    ev = _evento(ctx)
    for s in (0, 2, 4):
        t = NOW + timedelta(seconds=s)
        p = payload(ko=KO, inplay=True, minute=30, sh=None, sa=None)
        _giro(db, mk, ev, row(p, updated=t), ora=t)
    avvisi = _log(db, "feed_line_missing", "punteggio_assente")
    assert len(avvisi) == 1 and avvisi[0]["critical"] is True
    assert ev["live"]["goals"] is None          # mai zero: il dato non c'e'
    t = NOW + timedelta(seconds=6)
    _giro(db, mk, ev, row(payload(ko=KO, inplay=True, minute=30, sh=0, sa=0), updated=t), ora=t)
    assert len(_log(db, "skip", "punteggio_assente_tornato")) == 1
    assert ev["live"]["goals"] == 0


def test_prima_del_fischio_nessun_avviso_sul_punteggio():
    db = FakeDB(mode="live")
    ctx = E.MatchCtx(state="PRE_OPEN", legs=[_ingresso()])
    _riga(db, ctx.legs[0], status="open", bet_id="B0")
    ev = _evento(ctx)
    p = payload(ko=NOW + timedelta(minutes=20), inplay=False, sh=None, sa=None)
    _giro(db, MercatoOrdini([]), ev, row(p))
    assert _log(db, "feed_line_missing", "punteggio_assente") == []


# ===========================================================================
# M8.5 - LE QUOTE CHE SPARISCONO E TORNANO
# ===========================================================================
def _payload_senza_35(t):
    p = payload(ko=KO, inplay=True, minute=30, sh=0, sa=0)
    p["ou"][0]["seen_ms"] = 0            # il blocco dell'Under 3,5 non e' piu' osservato
    return row(p, updated=t)


def test_quota_che_manca_si_avvisa_una_volta_dopo_un_tempo_breve():
    db = FakeDB(mode="live")
    ctx = _ctx_scoperto()
    _riga(db, ctx.legs[0], status="open", bet_id="B0")
    mk = MercatoOrdini([])
    ev = _evento(ctx)
    for s in (0, 3, 6):
        t = NOW + timedelta(seconds=s)
        _giro(db, mk, ev, _payload_senza_35(t), ora=t)
    assert [k for k, _p, _e in db.activity if k == "feed_line_missing"] == [], \
        "avviso prima del tempo breve: una quota assente per un giro e' normale"
    for s in (12, 20, 60, 120):
        t = NOW + timedelta(seconds=s)
        _giro(db, mk, ev, _payload_senza_35(t), ora=t)
    avvisi = [p for k, p, _e in db.activity if k == "feed_line_missing"]
    assert len(avvisi) == 1 and "OU35|UNDER" in avvisi[0]["selections"]
    assert avvisi[0]["da_secondi"] >= S._DATO_ASSENTE_AVVISO_S
    t = NOW + timedelta(seconds=125)
    _giro(db, mk, ev, row(payload(ko=KO, inplay=True, minute=32, sh=0, sa=0), updated=t), ora=t)
    assert len(_log(db, "skip", "quote_assenti_tornato")) == 1


def test_scenari_del_banco_registrati():
    from Betfair.mike.tools import replay_registrazioni as R
    for s in (R.SCENARIO_LETTURA_KO, R.SCENARIO_PUNTEGGIO_KO):
        assert s in R.SCENARI_DESCRITTI
