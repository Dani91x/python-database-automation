# -*- coding: utf-8 -*-
"""B25, ESTENSIONE (24/09/2026): i due PULSANTI sulla gamba manuale della combo.

Ordine dell'utente: "devo poter scegliere tramite pulsanti: sia la possibilita'
di avere l'avviso con PROPOSTA DI COPERTURA a un click, sia la possibilita' di
lasciarlo AUTOMATICO (tramite pulsante) e quindi si occupa tutto lui."

Parametro di Safe `combo_gamba_manuale`:
  * 'avvisa_e_proponi' (DEFAULT, anche assente o sconosciuto): il bot non tocca
    la gamba manuale; avviso + marcatura (B25) + UNA proposta di copertura nella
    coda delle proposte di chiusura (kind='cashout', 'proposed', stesso corpo di
    `_proponi_chiusura`); rifiuto -> mai piu'; gamba chiusa -> la proposta
    decade; APPROVA -> il percorso `_request_cashout` di sempre (origin manual);
  * 'automatico': il comportamento di PRIMA di B25, con la scelta dell'utente
    scritta nel motivo della chiusura (audit).

I finti sono `FakeDB`/`FakeMarket` di `test_bot_service.py` (stesse chiavi di
`bot_db`), con in piu' `richiesta_per_id` (stessa firma e colonne di
`bot_db.richiesta_per_id`) e le due RPC della scheda (`safe_request_approve`,
`safe_request_ignore`) riprodotte come nella migrazione
`safe_strategy_proposed_2026-09-14.sql`. ASCII-only, commenti in italiano.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import certificazione as CERT
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy.tests.test_audit_2026_09_11 import (_combo, _combo_feed_row,
                                                              _kinds)
from Betfair.safe_strategy.tests.test_b25_lascia_e_avvisa_2026_09_24 import MercatoMezzo
from Betfair.safe_strategy.tests.test_bot_service import (NOW, FakeDB, FakeMarket,
                                                          _reset_module_state)


@pytest.fixture(autouse=True)
def _stato_pulito():
    _reset_module_state()
    S._EVENTI_CHIUSI.clear()
    yield
    _reset_module_state()
    S._EVENTI_CHIUSI.clear()


class DbConRichieste(FakeDB):
    """FakeDB + `richiesta_per_id` (colonne id,kind,status,result come il vero)
    + le due RPC della scheda, come la migrazione."""

    def richiesta_per_id(self, request_id):
        for r in self.requests:
            if int(r["id"]) == int(request_id):
                return {"id": r["id"], "kind": r.get("kind"), "status": r.get("status"),
                        "result": r.get("result")}
        return None

    def rpc_approva(self, req_id, quando):
        for r in self.requests:
            if int(r["id"]) == int(req_id) and r["status"] == "proposed":
                r["status"] = "pending"
                r["payload"] = {**r["payload"],
                                "approved_at": quando.strftime("%Y-%m-%dT%H:%M:%SZ")}
                return {"ok": True}
        return {"ok": False}

    def rpc_ignora(self, req_id, motivo="ignorata"):
        for r in self.requests:
            if int(r["id"]) == int(req_id) and r["status"] == "proposed":
                r["status"] = "rejected"
                r["result"] = {**(r.get("result") or {}), "ignorata_dall_utente": True,
                               "motivo": motivo}
                return {"ok": True}
        return {"ok": False}


def _params(modo=None) -> Dict[str, Any]:
    raw: Dict[str, Any] = {"strategy_modes": {"model": "live"}}
    if modo is not None:
        raw["combo_gamba_manuale"] = modo
    return S.resolve_params(raw)


def _combo_rotta(db, mercato, params) -> Dict[str, Any]:
    row = _combo_feed_row()
    corpi = S._proponi_combo(db=db, payload=row["payload"], event_id="1.1",
                             combos=[_combo()], params=params, mode="live",
                             now=NOW, rows_by_event={"1.1": row})
    assert len(corpi) == 1
    corpo = corpi[0]
    return S._esegui_combo_riservata(
        db=db, market=mercato, event_id="1.1", event_name=corpo.get("event_name"),
        cid=corpo["combo_id"], legs_esecuzione=corpo["legs"], sport="calcio", mode="live",
        commission=0.05, minute=corpo.get("minute"), score=corpo.get("score"),
        rationale=corpo.get("rationale"), params=params, now=NOW,
        rows_by_event={"1.1": row}, risk_ctx=None)


def _gamba(db) -> Dict[str, Any]:
    return next(t for t in db.trades if t.get("market_id") == "ou25"
                and not t.get("closes_trade_id"))


def _proposte(db, tid=None, stato="proposed") -> List[Dict[str, Any]]:
    return [r for r in db.requests if r.get("kind") == "cashout"
            and (stato is None or r.get("status") == stato)
            and (tid is None or int((r.get("payload") or {}).get("trade_id") or 0) == int(tid))]


def _giri(db, mercato, n, *, da=1, passo=25, modo=None):
    """`run_once` veri, con la riga del feed fresca e i parametri nel control."""
    db.control["params"] = {**db.control.get("params", {}), "strategy_modes": {"model": "live"}}
    if modo is not None:
        db.control["params"]["combo_gamba_manuale"] = modo
    for i in range(da, da + n):
        at = NOW + timedelta(seconds=passo * i)
        riga = _combo_feed_row()
        riga["updated_at"] = at.isoformat()
        db.scan_rows = [riga]
        S.run_once(db=db, market=mercato, now=at)
    return NOW + timedelta(seconds=passo * (da + n - 1))


# ===========================================================================
# 1. IL PARAMETRO
# ===========================================================================
@pytest.mark.parametrize("valore,atteso", [
    (None, "avvisa_e_proponi"), ("", "avvisa_e_proponi"), ("boh", "avvisa_e_proponi"),
    (True, "avvisa_e_proponi"), (1, "avvisa_e_proponi"),
    ("avvisa_e_proponi", "avvisa_e_proponi"), ("automatico", "automatico"),
    (" Automatico ", "automatico"),
])
def test_parametro_fail_closed(valore, atteso):
    raw = {} if valore is None else {"combo_gamba_manuale": valore}
    p = S.resolve_params(raw)
    assert p["combo_gamba_manuale"] == atteso
    assert S.params_effective(p)["combo_gamba_manuale"] == atteso
    assert S.DEFAULT_PARAMS["combo_gamba_manuale"] == "avvisa_e_proponi"


# ===========================================================================
# 2. AUTOMATICO: IL COMPORTAMENTO DI PRIMA, CON L'AUDIT
# ===========================================================================
def test_automatico_chiude_la_gamba_manuale_come_prima_con_audit():
    db = DbConRichieste(status="running", mode="live")
    _combo_rotta(db, MercatoMezzo(), _params("automatico"))
    g = _gamba(db)
    assert g["origin"] == "manual" and db.get_trade(g["id"])["status"] == "hedged"
    figlie = [t for t in db.trades if t.get("closes_trade_id") == g["id"]]
    assert len(figlie) == 1 and figlie[0]["origin"] == "auto"
    assert figlie[0]["meta"]["exit_kind"] == "forced"
    motivo = figlie[0]["meta"]["exit_reason"]
    assert "combo incompleta" in motivo and "combo_gamba_manuale=automatico" in motivo
    assert "scelta dell'utente" in motivo
    uscite = [p for p in _kinds(db, "exit") if p.get("trade_id") == g["id"]]
    assert uscite and uscite[0]["scelta_utente"] == "combo_gamba_manuale=automatico"
    # niente avviso "lasciata", niente marcatura, nessuna proposta
    assert not [p for p in _kinds(db, "combo_incomplete") if p.get("lasciata_al_trader")]
    assert S.COMBO_LASCIATA_KEY not in (g.get("meta") or {})
    assert _proposte(db, stato=None) == []


def test_automatico_chiude_anche_una_gamba_gia_lasciata_prima_del_cambio():
    """L'utente passa ad 'automatico' con una gamba gia' lasciata e una proposta
    viva: al giro dopo il bot la chiude e la proposta decade."""
    db = DbConRichieste(status="running", mode="live")
    mercato = MercatoMezzo()
    _combo_rotta(db, mercato, _params())
    g = _gamba(db)
    assert len(_proposte(db, g["id"])) == 1
    _giri(db, mercato, 2, modo="automatico")
    assert db.get_trade(g["id"])["status"] == "hedged"
    figlie = [t for t in db.trades if t.get("closes_trade_id") == g["id"]]
    assert [t["origin"] for t in figlie] == ["auto"]
    assert _proposte(db, g["id"]) == []
    decadute = _proposte(db, g["id"], stato="rejected")
    assert len(decadute) == 1 and decadute[0]["result"]["decaduta"] is True


# ===========================================================================
# 3. AVVISA E PROPONI: UNA PROPOSTA, LE CHIAVI GIUSTE
# ===========================================================================
def _chiavi_di_proponi_chiusura() -> set:
    """Le chiavi del corpo che scrive `_proponi_chiusura` (la proposta di
    chiusura che la scheda mostra gia'), prese dal codice VERO."""
    db = FakeDB(status="running", mode="live")
    tid = db.insert_trade({"event_id": "1.1", "event_name": "Home v Away", "sport": "calcio",
                           "strategy": "base", "market_id": "ou25", "market_type": "OVER_UNDER",
                           "selection_id": 101, "selection_name": "Under 2.5 Goals",
                           "side": "back", "price": 2.0, "size": 5.0, "liability": 5.0,
                           "commission": 0.05, "status": "open", "mode": "live",
                           "origin": "auto", "meta": {}})
    tr = db.get_trade(tid)
    prezzi = S.prices_from_row(_combo_feed_row(), market_type="OVER_UNDER",
                               selection_id=101, market_id="ou25")
    dec = SimpleNamespace(kind="loss", reason="x", not_before_ts=0.0)
    assert S._proponi_chiusura(db=db, trade=tr, meta={}, decision=dec, prices=prezzi,
                               payload=_combo_feed_row()["payload"], params=S.resolve_params({}),
                               row=_combo_feed_row(), now=NOW)
    return set(db.requests[0]["payload"])


def test_avvisa_scrive_una_proposta_con_le_chiavi_della_scheda():
    db = DbConRichieste(status="running", mode="live")
    _combo_rotta(db, MercatoMezzo(), _params())
    g = _gamba(db)
    props = _proposte(db, g["id"])
    assert len(props) == 1
    pl = props[0]["payload"]
    # TUTTE le chiavi del corpo di `_proponi_chiusura`, con gli stessi tipi
    assert _chiavi_di_proponi_chiusura() <= set(pl)
    assert pl["trade_id"] == g["id"] and pl["event_id"] == "1.1"
    assert pl["entry_side"] == "back" and pl["side"] == "lay"     # copertura = lato opposto
    prezzi = S.prices_from_row(_combo_feed_row(), market_type="OVER_UNDER",
                               selection_id=101, market_id="ou25")
    assert pl["price_at_decision"] == prezzi["lay"]
    assert pl["size"] == g["size"] and pl["entry_price"] == g["price"]
    assert pl["mode"] == "live" and pl["exit_kind"] == "forced"
    assert pl["motivo"] == "copertura_combo_incompleta"
    assert "copertura della gamba manuale lasciata dalla combo incompleta" in pl["exit_reason"]
    assert "responsabilita' scoperta" in pl["exit_reason"]
    assert pl["liability_scoperta"] == round(float(g["liability"]), 2)
    # il piano e' QUELLO che il bot userebbe in automatico (close_plan, 'forced')
    plan = X.close_plan(g, best_back=prezzi["back"], best_lay=prezzi["lay"], amount=None,
                        fraction=1.0, closings=[], place_at_ticks=X.ticks_for_exit("forced"))
    assert pl["piano_copertura"] == {"side": plan.side, "price": plan.price, "size": plan.size}
    # marcatore e avviso
    cop = g["meta"][S.COMBO_LASCIATA_KEY]["copertura"]
    assert cop["request_id"] == props[0]["id"] and cop["stato"] == "proposta"
    avviso = [p for p in _kinds(db, "combo_incomplete") if p.get("lasciata_al_trader")]
    assert len(avviso) == 1 and avviso[0]["copertura_request_id"] == props[0]["id"]
    assert "proposta di copertura in scheda" in avviso[0]["reason"]
    assert avviso[0]["modo"] == "avvisa_e_proponi"
    # e nessun ordine sulla gamba
    assert [t for t in db.trades if t.get("closes_trade_id")] == []


def test_parametro_assente_vale_avvisa_e_proponi():
    db = DbConRichieste(status="running", mode="live")
    _combo_rotta(db, MercatoMezzo(), S.resolve_params({"strategy_modes": {"model": "live"}}))
    g = _gamba(db)
    assert db.get_trade(g["id"])["status"] == "open"
    assert len(_proposte(db, g["id"])) == 1


def test_idempotenza_una_sola_proposta_in_tanti_giri():
    db = DbConRichieste(status="running", mode="live")
    mercato = MercatoMezzo()
    _combo_rotta(db, mercato, _params())
    g = _gamba(db)
    _giri(db, mercato, 6)
    assert len(_proposte(db, g["id"], stato=None)) == 1
    assert len(_proposte(db, g["id"])) == 1
    assert [t for t in db.trades if t.get("closes_trade_id")] == []
    assert len([p for p in _kinds(db, "combo_incomplete") if p.get("lasciata_al_trader")]) == 1


def test_senza_prezzi_la_proposta_arriva_al_giro_dopo_una_volta_sola():
    db = DbConRichieste(status="running", mode="live")
    tid = db.insert_trade({
        "event_id": "1.1", "event_name": "Home v Away", "sport": "calcio",
        "strategy": "model", "market_id": "ou25", "market_type": "OVER_UNDER",
        "selection_id": 101, "selection_name": "Under 2.5 Goals", "side": "back",
        "price": 2.0, "size": 5.0, "liability": 5.0, "commission": 0.05,
        "status": "open", "mode": "live", "origin": "manual", "signal_key": "combo:c1:0",
        "meta": {"combo_id": "c1", "combo_incomplete": True}})
    S.unwind_incomplete_combos(db=db, market=FakeMarket(), rows_by_event={},
                               params=_params(), now=NOW)
    assert _proposte(db, tid, stato=None) == []
    assert "copertura" not in db.get_trade(tid)["meta"][S.COMBO_LASCIATA_KEY]
    for i in range(3):
        S.gestisci_coperture_combo(db=db, rows_by_event={"1.1": _combo_feed_row()},
                                   params=_params(), now=NOW + timedelta(seconds=i))
    assert len(_proposte(db, tid, stato=None)) == 1
    assert len([p for p in _kinds(db, "combo_incomplete") if p.get("copertura_proposta")]) == 1


# ===========================================================================
# 4. RIFIUTO, DECADENZA, APPROVAZIONE
# ===========================================================================
def test_rifiuto_mai_piu_proposte_per_quella_gamba():
    db = DbConRichieste(status="running", mode="live")
    mercato = MercatoMezzo()
    _combo_rotta(db, mercato, _params())
    g = _gamba(db)
    rid = _proposte(db, g["id"])[0]["id"]
    assert db.rpc_ignora(rid)["ok"]
    _giri(db, mercato, 6)
    assert _proposte(db, g["id"]) == []
    assert len(_proposte(db, g["id"], stato=None)) == 1
    cop = db.get_trade(g["id"])["meta"][S.COMBO_LASCIATA_KEY]["copertura"]
    assert cop["stato"] == "rifiutata"
    assert len([p for p in _kinds(db, "combo_incomplete") if p.get("copertura_rifiutata")]) == 1
    assert db.get_trade(g["id"])["status"] == "open"


def test_rifiuto_senza_lettura_della_richiesta_resta_fail_closed():
    """Un database che non sa dire lo stato della richiesta: l'esito e' ignoto,
    ma la regola "una sola proposta per gamba" tiene lo stesso."""
    db = FakeDB(status="running", mode="live")
    mercato = MercatoMezzo()
    _combo_rotta(db, mercato, _params())
    g = _gamba(db)
    r = _proposte(db, g["id"])[0]
    r["status"] = "rejected"
    _giri(db, mercato, 4)
    assert len(_proposte(db, g["id"], stato=None)) == 1
    cop = db.get_trade(g["id"])["meta"][S.COMBO_LASCIATA_KEY]["copertura"]
    assert cop["stato"] == "non_piu_in_attesa"


def test_cashout_dell_utente_fa_decadere_la_proposta():
    db = DbConRichieste(status="running", mode="live")
    mercato = MercatoMezzo()
    _combo_rotta(db, mercato, _params())
    g = _gamba(db)
    res = S._request_cashout(db=db, market=mercato, rows_by_event={"1.1": _combo_feed_row()},
                             payload={"trade_id": g["id"], "fraction": 1.0}, params={}, now=NOW)
    assert res.get("ok") is True
    _giri(db, mercato, 2)
    assert _proposte(db, g["id"]) == []
    dec = _proposte(db, g["id"], stato="rejected")
    assert len(dec) == 1 and dec[0]["result"]["decaduta"] is True
    assert db.get_trade(g["id"])["meta"][S.COMBO_LASCIATA_KEY]["copertura"]["stato"] == "decaduta"


def test_cashout_globale_fa_decadere_la_proposta():
    db = DbConRichieste(status="running", mode="live")
    mercato = MercatoMezzo()
    _combo_rotta(db, mercato, _params())
    g = _gamba(db)
    S._request_cashout_event(db=db, market=mercato, rows_by_event={"1.1": _combo_feed_row()},
                             payload={"event_id": "1.1"}, params={}, now=NOW)
    _giri(db, mercato, 2)
    assert _proposte(db, g["id"]) == []
    assert db.get_trade(g["id"])["meta"][S.COMBO_LASCIATA_KEY]["copertura"]["stato"] == "decaduta"


def test_approva_chiude_con_un_ordine_manuale_dal_percorso_di_sempre():
    db = DbConRichieste(status="running", mode="live")
    mercato = MercatoMezzo()
    _combo_rotta(db, mercato, _params())
    g = _gamba(db)
    rid = _proposte(db, g["id"])[0]["id"]
    assert db.rpc_approva(rid, NOW + timedelta(seconds=10))["ok"]
    _giri(db, mercato, 3)
    figlie = [t for t in db.trades if t.get("closes_trade_id") == g["id"]]
    assert len(figlie) == 1
    assert figlie[0]["origin"] == "manual" and figlie[0]["mode"] == "live"
    assert figlie[0]["side"] == "lay"
    assert db.get_trade(g["id"])["status"] == "hedged"
    assert db.get_trade(g["id"])["meta"][S.COMBO_LASCIATA_KEY]["copertura"]["stato"] == "approvata"
    assert _proposte(db, g["id"]) == []
    # l'approvazione di una proposta NON e' una chiusura "dell'utente" della partita
    assert S.evento_chiuso_dall_utente("1.1") is None


# ===========================================================================
# 5. IL BANCO: T13 e T13-COMBO NEI DUE MODI
# ===========================================================================
class _Db:
    def __init__(self, trades, attivita=(), requests=None):
        self.trades = list(trades)
        self.attivita = list(attivita)
        if requests is not None:
            self.requests = list(requests)

    def aggregates(self, mode=None):
        return {}


class _Mercato:
    def list_current_orders(self, strategy_ref=None):
        return []


def _ciclo(db, modo=None, **kw) -> CERT.Ciclo:
    params = {} if modo is None else {"combo_gamba_manuale": modo}
    return CERT.Ciclo(db=db, market=_Mercato(), params=params, mode="live", now_ts=0.0, **kw)


def _codici(c) -> set:
    return {v.codice for v in CERT.verifica(c)}


def _sollecitato(c, codice) -> bool:
    sol: Dict[str, int] = {}
    CERT.verifica(c, sol)
    return bool(sol.get(codice))


def _dal_servizio(db) -> _Db:
    return _Db(db.trades, [(k, p, p.get("event_id")) for k, p in db.activity],
               requests=db.requests)


def test_banco_automatico_conforme_sul_servizio():
    db = DbConRichieste(status="running", mode="live")
    _combo_rotta(db, MercatoMezzo(), _params("automatico"))
    c = _ciclo(_dal_servizio(db), "automatico",
               attivita_del_giro=[(k, p, p.get("event_id")) for k, p in db.activity])
    assert _sollecitato(c, "T13-COMBO")
    assert "T13-COMBO" not in _codici(c) and "T13" not in _codici(c)
    # la stessa storia giudicata col modo di default: il bot ha chiuso la gamba
    c2 = _ciclo(_dal_servizio(db), None)
    assert "T13-COMBO" in _codici(c2) and "T13" in _codici(c2)


def test_banco_automatico_senza_audit_scatta():
    db = DbConRichieste(status="running", mode="live")
    _combo_rotta(db, MercatoMezzo(), _params("automatico"))
    for t in db.trades:
        if t.get("closes_trade_id"):
            t["meta"] = {**t["meta"], "exit_reason": "combo incompleta: gamba chiusa subito"}
    c = _ciclo(_dal_servizio(db), "automatico")
    assert "T13-COMBO" in _codici(c)


def test_banco_avvisa_conforme_sul_servizio_con_la_proposta():
    db = DbConRichieste(status="running", mode="live")
    _combo_rotta(db, MercatoMezzo(), _params())
    c = _ciclo(_dal_servizio(db))
    assert _sollecitato(c, "T13-COMBO")
    assert "T13-COMBO" not in _codici(c) and "T13" not in _codici(c)


def test_banco_avvisa_due_proposte_vive_scatta():
    db = DbConRichieste(status="running", mode="live")
    _combo_rotta(db, MercatoMezzo(), _params())
    g = _gamba(db)
    db.requests.append({**_proposte(db, g["id"])[0], "id": 999})
    assert "T13-COMBO" in _codici(_ciclo(_dal_servizio(db)))


def test_banco_avvisa_proposta_nuova_dopo_il_rifiuto_scatta():
    db = DbConRichieste(status="running", mode="live")
    _combo_rotta(db, MercatoMezzo(), _params())
    g = _gamba(db)
    cop = g["meta"][S.COMBO_LASCIATA_KEY]["copertura"]
    g["meta"][S.COMBO_LASCIATA_KEY]["copertura"] = {**cop, "stato": "rifiutata"}
    assert "T13-COMBO" in _codici(_ciclo(_dal_servizio(db)))
