"""CANTIERE J2 (28/09/2026) - blocco 3: la RISERVA DEI PREZZI del runner calcio.

«se cade lo stream ci dovrebbe essere il pool di backup, per le chiamate,
funziona? c'e'?» (utente, 28/09). A stream del runner MUTO (episodio dichiarato
dal suo battito, ``stream_muto``) il book in memoria e' FERMO:
  * le protezioni (stop, bracket, green-up, chiusure) leggono i prezzi dalla
    RISERVA = il feed dello scanner, SOLO se lo scanner li dichiara vivi per quel
    mercato (``riserva_prezzi``), mai il book fermo; nessuna chiamata Betfair;
  * senza riserva nessun prezzo (chi chiama non agisce) e il motivo e' scritto;
  * nessuna posizione nuova: lo stop-entry non scatta, il chase non ri-prezza;
  * al rientro dello stream si torna ai prezzi dello stream.
Finti: la riga del feed ha le chiavi VERE di ``build_rows`` (``odds`` con
``selection_id``, ``flusso``); il market ha gli attributi letti da flumine
(``market_id``, ``event_id``, ``market_type``, ``market_book.runners[].ex``).
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream import live_order_worker as LOW
from Betfair.stream import riserva_prezzi as RP
from Betfair.stream import risk_engine_worker as REW
from Betfair.stream import flusso_prezzi as FP


@pytest.fixture(autouse=True)
def _pulito():
    RP.azzera()
    yield
    RP.azzera()


def _lv(p, s):
    return SimpleNamespace(price=p, size=s)


def _market(mid="1.200", eid="c1", mtype="MATCH_ODDS", back=1.80, lay=1.82):
    """Il Market di flumine come lo leggono ``_best_prices`` e la riserva."""
    runner = SimpleNamespace(selection_id=11, handicap=0.0, last_price_traded=1.81,
                             ex=SimpleNamespace(available_to_back=[_lv(back, 100.0)],
                                                available_to_lay=[_lv(lay, 100.0)]))
    mb = SimpleNamespace(runners=[runner], inplay=True,
                         market_definition=SimpleNamespace(event_id=eid, market_type=mtype))
    return SimpleNamespace(market_id=mid, event_id=eid, market_type=mtype, market_book=mb)


def _riga(vivo=True, fermi=(), back=1.95, lay=1.97):
    return {"event_id": "c1", "payload": {
        "mo_market_id": "1.200",
        "odds": {"home": {"selection_id": 11, "back": back, "lay": lay,
                          "back_size": 50.0, "lay_size": 40.0},
                 "draw": {"selection_id": 22, "back": 3.6, "lay": 3.7}},
        "flusso": {"vivo": vivo, "motivo": None if vivo else FP.MOTIVO_INTERROTTO,
                   "dal_ms": int(time.time() * 1000) - 1000, "mercati_fermi": list(fermi)}}}


class Cache:
    """``scan_feed.ScanRowCache`` come la usa la riserva: ``rows_for``,
    ``scanner_stato`` (stesse firme)."""

    def __init__(self, riga: Optional[dict], stato: Optional[dict] = None) -> None:
        self.riga, self.stato = riga, stato
        self.letture = 0

    def rows_for(self, ids):
        self.letture += 1
        return {"c1": self.riga} if self.riga is not None and "c1" in ids else {}

    def scanner_stato(self):
        return self.stato


def _muto(mercati=()):
    RP.imposta_stato({"vivo": False, "interrotto": True, "motivo": "flusso_interrotto",
                      "mercati_fermi": list(mercati)})


# ---------------------------------------------------------------------------
def test_senza_episodio_lo_stream_e_vivo_e_la_riserva_non_si_legge(monkeypatch):
    cache = Cache(_riga())
    monkeypatch.setattr("Betfair.stream.scores.scan_feed.shared_cache", lambda: cache)
    assert LOW._best_prices(_market(), 11, 0.0) == (1.80, 1.82)
    assert cache.letture == 0


def test_stream_muto_prezzi_dalla_riserva_mai_dal_book_fermo(monkeypatch):
    cache = Cache(_riga())
    monkeypatch.setattr("Betfair.stream.scores.scan_feed.shared_cache", lambda: cache)
    _muto(["1.200"])
    assert LOW._best_prices(_market(), 11, 0.0) == (1.95, 1.97)
    assert "riserva attiva" in RP.ULTIMO_ESITO["1.200"]


def test_episodio_su_un_altro_frammento_non_tocca_questo_mercato(monkeypatch):
    cache = Cache(_riga())
    monkeypatch.setattr("Betfair.stream.scores.scan_feed.shared_cache", lambda: cache)
    _muto(["1.999"])
    assert LOW._best_prices(_market(), 11, 0.0) == (1.80, 1.82)


def test_riserva_ferma_anche_lei_nessun_prezzo_e_motivo(monkeypatch):
    cache = Cache(_riga(vivo=False))
    monkeypatch.setattr("Betfair.stream.scores.scan_feed.shared_cache", lambda: cache)
    _muto()
    assert LOW._best_prices(_market(), 11, 0.0) == (None, None)
    assert "anche il feed dello scanner e' fermo" in RP.ULTIMO_ESITO["1.200"]


def test_mercato_non_seguito_dal_feed_o_handicap_nessun_prezzo(monkeypatch):
    cache = Cache(_riga())
    monkeypatch.setattr("Betfair.stream.scores.scan_feed.shared_cache", lambda: cache)
    _muto()
    assert LOW._best_prices(_market(mid="1.AH", mtype="ASIAN_HANDICAP"), 11, 0.0) == (None, None)
    assert "non segue" in RP.ULTIMO_ESITO["1.AH"]
    assert LOW._best_prices(_market(), 11, -0.5) == (None, None)
    assert "handicap" in RP.ULTIMO_ESITO["1.200"]


def test_rientro_dello_stream_si_torna_ai_prezzi_dello_stream(monkeypatch):
    cache = Cache(_riga())
    monkeypatch.setattr("Betfair.stream.scores.scan_feed.shared_cache", lambda: cache)
    _muto()
    assert LOW._best_prices(_market(), 11, 0.0) == (1.95, 1.97)
    RP.imposta_stato({"vivo": True, "interrotto": False, "mercati_fermi": []})
    assert LOW._best_prices(_market(), 11, 0.0) == (1.80, 1.82)


def test_il_battito_del_runner_imposta_lo_stato_della_riserva():
    import inspect

    from Betfair.stream import runner as R

    assert "_RP.imposta_stato(dich)" in inspect.getsource(R._sorveglia_flusso_runner)


# ---------------------------------------------------------------------------
# regole di rischio
# ---------------------------------------------------------------------------
class Sb:
    """``sb.table(...).update(...).eq(...).execute()`` e ``sb.rpc(...)``."""

    def __init__(self) -> None:
        self.update: List[dict] = []
        self.rpc_chiamate: List[tuple] = []

    def table(self, _nome):
        sb = self

        class _Q:
            def update(self, payload):
                sb.update.append(dict(payload))
                return self

            def eq(self, *_a):
                return self

            def execute(self):
                return SimpleNamespace(data=[])
        return _Q()

    def rpc(self, nome, args):
        self.rpc_chiamate.append((nome, args))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=1))


def _fw(market):
    return SimpleNamespace(markets=SimpleNamespace(markets={market.market_id: market}))


def test_stop_entry_non_scatta_a_stream_muto_ne_apre_poi_al_rientro_si(monkeypatch):
    monkeypatch.setattr(REW, "_kill_active", lambda: False)
    mk = _market()
    rule = {"id": 9, "market_id": "1.200", "selection_id": 11, "handicap": 0,
            "entry_side": "back", "entry_size": 2.0, "rule_type": "stop_entry",
            "params": {"trigger_price": 1.5, "trigger_direction": "at_or_above"}, "result": {}}
    sb = Sb()
    _muto()
    REW._handle_stop_entry(sb, _fw(mk), dict(rule), "paper")
    assert sb.rpc_chiamate == []
    note = [u["result"] for u in sb.update
            if "flusso prezzi del runner INTERROTTO" in str((u.get("result") or {}).get("note"))]
    assert len(note) == 1
    RP.imposta_stato({"vivo": True, "interrotto": False, "mercati_fermi": []})
    REW._handle_stop_entry(sb, _fw(mk), dict(rule, result=note[0]), "paper")
    assert sb.rpc_chiamate, "al rientro lo stop-entry torna a valutarsi e scatta (LTP 1.81 >= 1.5)"


def test_prezzo_di_confronto_a_stream_muto_e_quello_di_chiusura_della_riserva(monkeypatch):
    mk = _market()
    rule_b = {"market_id": "1.200", "entry_side": "back"}
    rule_l = {"market_id": "1.200", "entry_side": "lay"}
    assert REW._prezzo_di_confronto(mk, rule_b, 11, 0.0, 1.95, 1.97) == 1.81   # LTP (vivo)
    _muto()
    assert REW._prezzo_di_confronto(mk, rule_b, 11, 0.0, 1.95, 1.97) == 1.97   # chiude di lay
    assert REW._prezzo_di_confronto(mk, rule_l, 11, 0.0, 1.95, 1.97) == 1.95   # chiude di back
    assert REW._prezzo_di_confronto(mk, rule_b, 11, 0.0, None, None) is None   # senza riserva


def test_stop_loss_a_stream_muto_scatta_sulla_riserva_non_sul_book_fermo(monkeypatch):
    """Book fermo in memoria: LTP 1.81 (sotto lo stop). La riserva viva dice che
    per chiudere il back ora serve un lay a 2.30: lo stop (trigger 2 tick sopra
    1.80 = 1.84) scatta sulla riserva."""
    monkeypatch.setattr(REW, "_kill_active", lambda: False)
    monkeypatch.setattr(LOW, "_read_matched_exposures", lambda *a, **k: (1.6, -2.0))
    cache = Cache(_riga(back=2.26, lay=2.30))
    monkeypatch.setattr("Betfair.stream.scores.scan_feed.shared_cache", lambda: cache)
    mk = _market()
    rule = {"id": 3, "market_id": "1.200", "selection_id": 11, "handicap": 0,
            "entry_side": "back", "entry_price": 1.80, "rule_type": "stop_loss",
            "params": {"trigger_ticks": 2}, "result": {}}
    sb = Sb()
    REW._handle_monitored(sb, _fw(mk), dict(rule), "paper", None)
    assert sb.rpc_chiamate == [], "stream vivo: LTP 1.81, nessuno scatto"
    _muto()
    REW._handle_monitored(sb, _fw(mk), dict(rule), "paper", None)
    assert sb.rpc_chiamate, "stream muto: lo stop scatta sul prezzo vivo della riserva"


def _chase(monkeypatch, esposizioni, riserva: bool):
    monkeypatch.setattr(REW, "_kill_active", lambda: False)
    ordine = SimpleNamespace(status=SimpleNamespace(name="EXECUTABLE"), size_remaining=2.0,
                             order_type=SimpleNamespace(price=1.70), bet_id="B1")
    monkeypatch.setattr(LOW, "_find_order_by_bet_id", lambda *a, **k: ordine)
    monkeypatch.setattr(LOW, "_read_matched_exposures", lambda *a, **k: esposizioni)
    cache = Cache(_riga(vivo=riserva))
    monkeypatch.setattr("Betfair.stream.scores.scan_feed.shared_cache", lambda: cache)
    alert: List[tuple] = []
    monkeypatch.setattr(REW, "_alert", lambda lv, msg: alert.append((lv, msg)))
    REW._AVVISO_APPOGGIATI.clear()
    rule = {"id": 4, "market_id": "1.200", "selection_id": 11, "handicap": 0,
            "entry_side": "back", "entry_bet_id": "B1", "rule_type": "chase",
            "params": {"offset_ticks": 0}, "result": {}}
    _muto()
    return rule, alert


def test_chase_apertura_senza_riserva_si_ritira_e_non_si_ripiazza(monkeypatch):
    rule, alert = _chase(monkeypatch, (0.0, 0.0), riserva=False)     # posizione piatta: APRE
    sb = Sb()
    REW._handle_chase(sb, _fw(_market()), dict(rule), "paper", object())
    cancel = [a for n, a in sb.rpc_chiamate if a["p"]["action"] == "cancel"]
    assert len(cancel) == 1 and cancel[0]["p"]["client_ref"] == "risk4cf"
    assert [a for n, a in sb.rpc_chiamate if a["p"]["action"] == "place"] == []
    fatta = [u for u in sb.update if u.get("status") == "done"]
    assert fatta and fatta[0]["result"]["ritirato_flusso"] is True
    assert alert and alert[0][0] == "CRITICAL" and "RITIRATO" in alert[0][1]


def test_chase_chiusura_senza_riserva_resta_e_si_grida_una_volta_al_minuto(monkeypatch):
    # back che chiude una posizione LAY (w < l)
    rule, alert = _chase(monkeypatch, (-3.0, 2.0), riserva=False)
    sb = Sb()
    for _ in range(3):
        REW._handle_chase(sb, _fw(_market()), dict(rule), "paper", object())
    assert sb.rpc_chiamate == [] and not [u for u in sb.update if u.get("status") == "done"]
    assert len(alert) == 1 and alert[0][0] == "CRITICAL" and "se vince -3.00" in alert[0][1]


def test_chase_chiusura_con_riserva_viva_insegue_sulla_riserva(monkeypatch):
    rule, alert = _chase(monkeypatch, (-3.0, 2.0), riserva=True)
    sb = Sb()
    REW._handle_chase(sb, _fw(_market()), dict(rule), "paper", object())
    cancel = [a for n, a in sb.rpc_chiamate if a["p"]["action"] == "cancel"]
    assert cancel and cancel[0]["p"]["client_ref"] == "risk4cc0"    # re-quote: 1.70 -> 1.95
    assert alert == []


def test_bracket_senza_riserva_grida_e_non_decide(monkeypatch):
    monkeypatch.setattr(REW, "_kill_active", lambda: False)
    monkeypatch.setattr(LOW, "_read_matched_exposures", lambda *a, **k: (1.6, -2.0))
    cache = Cache(_riga(vivo=False))
    monkeypatch.setattr("Betfair.stream.scores.scan_feed.shared_cache", lambda: cache)
    alert: List[tuple] = []
    monkeypatch.setattr(REW, "_alert", lambda lv, msg: alert.append((lv, msg)))
    monkeypatch.setattr(REW, "_offset_order_obj", lambda *a, **k: None)
    REW._AVVISO_APPOGGIATI.clear()
    rule = {"id": 7, "market_id": "1.200", "selection_id": 11, "handicap": 0,
            "entry_side": "back", "entry_price": 1.80, "rule_type": "bracket",
            "params": {"offset_ticks": 3, "trigger_ticks": 2},
            "result": {"state": "offset_placed", "offset_request_id": 1}}
    _muto()
    sb = Sb()
    REW._handle_bracket(sb, _fw(_market()), dict(rule), "paper", None)
    REW._handle_bracket(sb, _fw(_market()), dict(rule), "paper", None)
    assert sb.rpc_chiamate == [] and len(alert) == 1 and alert[0][0] == "CRITICAL"


def test_chase_non_riprezza_a_stream_muto(monkeypatch):
    monkeypatch.setattr(REW, "_kill_active", lambda: False)
    ordine = SimpleNamespace(status=SimpleNamespace(name="EXECUTABLE"), size_remaining=2.0,
                             order_type=SimpleNamespace(price=1.70), bet_id="B1")
    monkeypatch.setattr(LOW, "_find_order_by_bet_id", lambda *a, **k: ordine)
    # riserva VIVA (1.95/1.97): senza la guardia il chase ri-prezzerebbe su di lei
    cache = Cache(_riga())
    monkeypatch.setattr("Betfair.stream.scores.scan_feed.shared_cache", lambda: cache)
    mk = _market()
    rule = {"id": 4, "market_id": "1.200", "selection_id": 11, "handicap": 0,
            "entry_side": "back", "entry_bet_id": "B1", "rule_type": "chase",
            "params": {"offset_ticks": 0}, "result": {}}
    sb = Sb()
    _muto()
    REW._handle_chase(sb, _fw(mk), dict(rule), "paper")
    assert sb.rpc_chiamate == []
    assert not [u for u in sb.update if (u.get("result") or {}).get("phase") == "cancelling"]
    RP.imposta_stato({"vivo": True, "interrotto": False, "mercati_fermi": []})
    REW._handle_chase(sb, _fw(mk), dict(rule), "paper")
    assert sb.rpc_chiamate, "al rientro il chase ri-prezza sul best dello stream (1.80 != 1.70)"
