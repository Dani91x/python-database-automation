# -*- coding: utf-8 -*-
"""D2 (24/09) - SAFE: lo stato del mercato davanti agli invii che non lo
guardavano (mappa del 24/09).

  * approvazione di una COMBO: una gamba su un mercato sospeso -> NESSUNA gamba
    piazzata (tutto o niente), rifiuto col motivo, UNA riga
    ``attesa_riapertura``;
  * piazzamento MANUALE: stessa guardia (``_mercato_non_operabile``);
  * svolgimento di una combo incompleta (``_unwind_combo``, ogni ciclo): a
    mercato sospeso la gamba non si manda e si riprende al ciclo dopo;
  * F2 (25/09) - chiusura SOLIDALE delle sorelle (``_close_combo_siblings``,
    quando il parent chiude e trascina le altre gambe): era l'unica strada
    rimasta senza guardia (dichiarato "resta" nel commit ``baf4286`` del
    24/09 e in CRONOSTORIA 24/09 sera).

Lo stato si legge dalla riga di scan con le chiavi dello scanner vero
(``btts.status``, ``ou[i].status``, ``mo_status``) tramite ``exits.market_open``.
ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, List

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy.tests.test_combos_anomalie_proposte_2026_09_18 import (
    EV, NOW, DbFinto, _anomaly, _ciclo_anomalia, _Esito, _ciclo_combo, _combo, _riga_feed)
from Betfair.stream.trading import stato_mercato as SM


def _riga_con_btts(status: str) -> Dict[str, Any]:
    r = _riga_feed()
    r["payload"]["btts"]["status"] = status
    r["payload"]["ou"][0]["status"] = "OPEN"
    return r


def _approva(monkeypatch, riga: Dict[str, Any]):
    db = DbFinto()
    _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    corpo = dict(db.vive()[0]["payload"])
    eseguite: List[Any] = []

    def esecuzione(**kw):
        eseguite.append(kw)
        return _Esito(status="open", price=kw["row"]["price"], size=kw["row"]["size"])

    monkeypatch.setattr(S, "_execute", esecuzione)
    out = S._request_place(db=db, market=None, rows_by_event={EV: riga},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    return db, out, eseguite


def test_combo_con_una_gamba_sospesa_nessuna_gamba_parte(monkeypatch):
    db, out, eseguite = _approva(monkeypatch, _riga_con_btts("SUSPENDED"))
    assert out.get("error") == "mercato_non_operabile" and out.get("motivo") == "SUSPENDED"
    assert out.get("gamba") == 1
    assert eseguite == [] and db.trades == []
    att = [p for k, p in db.attivita if k == SM.KIND_ATTESA]
    assert len(att) == 1 and att[0]["percorso"] == "combo" and att[0]["origin"] == "manual"


def test_combo_a_mercati_aperti_si_piazza_come_prima(monkeypatch):
    db, out, eseguite = _approva(monkeypatch, _riga_con_btts("OPEN"))
    assert out.get("ok") is True, out
    assert len(eseguite) == 2
    assert SM.KIND_ATTESA not in db.kinds()


def test_stato_assente_nella_riga_si_passa_come_oggi(monkeypatch):
    """Stato ignoto: la guardia non blocca (bloccare spegnerebbe la strategia)."""
    db, out, eseguite = _approva(monkeypatch, _riga_feed())
    assert out.get("ok") is True, out
    assert len(eseguite) == 2


def _approva_anomalia(monkeypatch, riga: Dict[str, Any]):
    """Il piazzamento MANUALE a una gamba (`_request_place`, approvazione di una
    proposta anomalia su ou25)."""
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()])
    corpo = dict(db.vive()[0]["payload"])
    eseguite: List[Any] = []

    def esecuzione(**kw):
        eseguite.append(kw)
        return _Esito(status="open", price=kw["row"]["price"], size=kw["row"]["size"])

    monkeypatch.setattr(S, "_execute", esecuzione)
    out = S._request_place(db=db, market=None, rows_by_event={EV: riga},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    return db, out, eseguite


def test_manuale_a_mercato_sospeso_nessuna_riserva_nessun_ordine(monkeypatch):
    riga = _riga_feed()
    riga["payload"]["ou"][0]["status"] = "SUSPENDED"
    db, out, eseguite = _approva_anomalia(monkeypatch, riga)
    assert out.get("error") == "mercato_non_operabile", out
    assert eseguite == [] and db.trades == []
    assert [p for k, p in db.attivita if k == SM.KIND_ATTESA][0]["percorso"] == "manuale"


def test_manuale_a_mercato_aperto_come_prima(monkeypatch):
    riga = _riga_feed()
    riga["payload"]["ou"][0]["status"] = "OPEN"
    db, out, eseguite = _approva_anomalia(monkeypatch, riga)
    assert out.get("ok") is True, out
    assert len(eseguite) == 1


def test_guardia_una_riga_per_sospensione_e_chiuso_non_si_aspetta():
    db = DbFinto()
    trade = {"market_type": "BOTH_TEAMS_TO_SCORE", "market_id": "btts1"}
    for _ in range(10):
        r = S._mercato_non_operabile(db, "E7", trade, _riga_con_btts("SUSPENDED"), "manuale")
        assert r is not None and r["motivo"] == "SUSPENDED"
    assert len([k for k in db.kinds() if k == SM.KIND_ATTESA]) == 1
    assert S._mercato_non_operabile(db, "E7", trade, _riga_con_btts("OPEN"), "manuale") is None
    r = S._mercato_non_operabile(db, "E7", trade, _riga_con_btts("CLOSED"), "manuale")
    assert r["motivo"] == "CLOSED"
    att = [p for k, p in db.attivita if k == SM.KIND_ATTESA]
    assert len(att) == 2 and att[-1]["aspetta"] is False


def test_match_odds_legge_mo_status():
    db = DbFinto()
    riga = _riga_feed()
    riga["payload"]["mo_status"] = "SUSPENDED"
    r = S._mercato_non_operabile(db, "E8", {"market_type": "MATCH_ODDS", "market_id": "1.MO"},
                                 riga, "manuale")
    assert r is not None and r["motivo"] == "SUSPENDED"


def test_svolgimento_combo_aspetta_la_riapertura(monkeypatch):
    db = DbFinto()
    tid = db.insert_trade({"event_id": EV, "status": "open", "market_type": "BOTH_TEAMS_TO_SCORE",
                           "market_id": "btts1", "selection_id": 30246, "side": "back",
                           "price": 1.9, "size": 5.0, "origin": "auto", "mode": "paper",
                           "meta": {}})
    chiuse: List[Any] = []
    monkeypatch.setattr(S, "_close_combo_siblings",
                        lambda **kw: chiuse.append(kw) or 1)
    n = S._unwind_combo(db=db, market=None, ids=[tid],
                        rows_by_event={EV: _riga_con_btts("SUSPENDED")}, event_id=EV,
                        params={}, now=NOW)
    assert n == 0 and chiuse == []
    assert [p for k, p in db.attivita if k == SM.KIND_ATTESA][0]["origin"] == "bot"
    # al ciclo dopo il mercato e' riaperto: la gamba si chiude
    n = S._unwind_combo(db=db, market=None, ids=[tid],
                        rows_by_event={EV: _riga_con_btts("OPEN")}, event_id=EV,
                        params={}, now=NOW)
    assert n == 1 and len(chiuse) == 1


# ===========================================================================
# F2 (25/09) - la CHIUSURA SOLIDALE delle sorelle di una combo (quando il
# parent chiude e trascina le altre gambe) era l'UNICA strada rimasta senza
# la guardia D2 del 24/09 (``baf4286``, dichiarato "resta" in CRONOSTORIA
# 24/09 sera e nel commit stesso: "Resta senza guardia la chiusura solidale
# delle sorelle nelle combo Safe"). Stessa funzione condivisa
# (``_mercato_non_operabile``), stessa semantica delle altre strade sopra.
# ===========================================================================
def _gamba_combo(db: DbFinto, *, market_type: str = "BOTH_TEAMS_TO_SCORE",
                 market_id: str = "btts1") -> Dict[str, Any]:
    tid = db.insert_trade({"event_id": EV, "status": "open", "mode": "paper",
                           "market_type": market_type, "market_id": market_id,
                           "selection_id": 30246, "side": "back", "price": 1.9,
                           "size": 5.0, "origin": "auto",
                           "meta": {"combo_id": "c1"}})
    return db.get_trade(tid)


def test_chiusura_solidale_sorella_mercato_sospeso_nessuna_gamba_parte(monkeypatch):
    db = DbFinto()
    leg = _gamba_combo(db)
    chiamate: List[Any] = []
    monkeypatch.setattr(S.X, "close_trade", lambda **kw: chiamate.append(kw) or {})
    n = S._close_combo_siblings(
        db=db, market=None, legs=[leg], prices_by_id={int(leg["id"]): {"back": 1.9, "lay": 2.0}},
        params={}, now=NOW, reason="combo: chiusura solidale della combinazione",
        row=_riga_con_btts("SUSPENDED"))
    assert n == 0 and chiamate == [], "F2: nessun ordine a mercato sospeso"
    att = [p for k, p in db.attivita if k == SM.KIND_ATTESA]
    assert len(att) == 1 and att[0]["motivo"] == "SUSPENDED"
    # la gamba resta 'open' (nessuna chiusura inventata)
    assert db.get_trade(leg["id"])["status"] == "open"


def test_chiusura_solidale_sorella_mercato_aperto_piazza_come_prima(monkeypatch):
    """Falsificazione della falsificazione: mercato OPEN -> comportamento
    INVARIATO rispetto a prima del fix (una gamba, una X.close_trade)."""
    db = DbFinto()
    leg = _gamba_combo(db)
    chiamate: List[Any] = []
    monkeypatch.setattr(
        S.X, "close_trade",
        lambda **kw: chiamate.append(kw) or {"ok": True, "closing_trade_id": 999,
                                             "side": "lay", "price": 2.0, "size": 5.0,
                                             "locked_pnl": 0.1})
    n = S._close_combo_siblings(
        db=db, market=None, legs=[leg], prices_by_id={int(leg["id"]): {"back": 1.9, "lay": 2.0}},
        params={}, now=NOW, reason="combo: chiusura solidale della combinazione",
        row=_riga_con_btts("OPEN"))
    assert n == 1 and len(chiamate) == 1
    assert SM.KIND_ATTESA not in db.kinds()


def test_chiusura_solidale_sorella_stato_ignoto_passa_come_oggi(monkeypatch):
    """Stato assente dalla riga (feed senza il blocco del mercato): si passa,
    come per le altre strade D2 — non e' questo fix a irrigidirlo."""
    db = DbFinto()
    leg = _gamba_combo(db)
    chiamate: List[Any] = []
    monkeypatch.setattr(
        S.X, "close_trade",
        lambda **kw: chiamate.append(kw) or {"ok": True, "closing_trade_id": 999,
                                             "side": "lay", "price": 2.0, "size": 5.0,
                                             "locked_pnl": 0.1})
    n = S._close_combo_siblings(
        db=db, market=None, legs=[leg], prices_by_id={int(leg["id"]): {"back": 1.9, "lay": 2.0}},
        params={}, now=NOW, reason="combo: chiusura solidale della combinazione",
        row=_riga_feed())
    assert n == 1 and len(chiamate) == 1
