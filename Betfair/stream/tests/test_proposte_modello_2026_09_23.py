# -*- coding: utf-8 -*-
"""IL MODELLO SUL BANCO (23/09, cancello C6 e) - finti, RPC, porte del DB e
controlli PM di `Betfair/stream/backtest/proposte_modello.py`.

Che cosa si difende:
  1. i FINTI parlano la lingua del VERO: stesse chiavi e stessi tipi di
     `opportunity.Opportunity`, `anomaly.detect`, `combos.find_combos`,
     `tennis_opportunity.TennisOpportunity` (le uscite vere si producono qui,
     su un payload costruito per farle parlare), stessa firma dei metodi;
  2. le porte del DB hanno la firma di `bot_db.py` e l'indice unico
     `uq_safe_requests_proposta_opp_viva` SOLLEVA come il database;
  3. le RPC `safe_request_approve` / `safe_request_ignore` si comportano come
     l'SQL: solo una riga 'proposed' cambia stato, il payload si ARRICCHISCE;
  4. ogni controllo PM diventa ROSSO sul suo difetto e tace sul caso sano
     (falsificazione dentro il test).
"""
from __future__ import annotations

import inspect
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from Betfair.safe_strategy import anomaly as AN
from Betfair.safe_strategy import bot_db as BD
from Betfair.safe_strategy import combos as CO
from Betfair.safe_strategy import opportunity as OP
from Betfair.safe_strategy import proposte_opportunita as PO
from Betfair.safe_strategy import tennis_opportunity as TO
from Betfair.stream.backtest import proposte_modello as PM

T0 = datetime(2026, 6, 30, 16, 0, 0, tzinfo=timezone.utc).timestamp()


def _odds(h=3.5, d=3.5, a=3.5, size=1000.0) -> Dict[str, Any]:
    def blk(sid, p):
        return {"selection_id": sid, "back": p, "back_size": size,
                "lay": round(p + 0.1, 2), "lay_size": size}
    return {"home": blk(1, h), "draw": blk(2, d), "away": blk(3, a)}


def _payload(**kw) -> Dict[str, Any]:
    p = {"inplay": True, "minute": 60, "score_home": 0, "score_away": 0,
         "home": "Casa FC", "away": "Ospiti FC", "mo_market_id": "1.100",
         "mo_status": "OPEN", "odds": _odds(), "odds_ts_ms": 0, "event_id": "E1"}
    p.update(kw)
    return p


class _Orologio:
    def __init__(self, t: float = T0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _tipi(d: Dict[str, Any]) -> Dict[str, str]:
    return {k: type(v).__name__ for k, v in d.items()}


def _stessi_tipi(finto: Dict[str, Any], vero: Dict[str, Any]) -> List[str]:
    """Differenze di TIPO sulle chiavi comuni (None del vero = campo opzionale)."""
    diff = []
    for k, v in vero.items():
        if v is None or finto.get(k) is None:
            continue
        if type(v) is not type(finto[k]):
            diff.append(f"{k}: vero {type(v).__name__} finto {type(finto[k]).__name__}")
    return diff


def _banco(scenario: str, sport: str = "calcio", t: float = T0):
    oro = _Orologio(t)
    return PM.BancoProposte(scenario, sport, oro), oro


# ---------------------------------------------------------------------------
# 1. i finti parlano la lingua del vero
# ---------------------------------------------------------------------------
def test_modello_calcio_stesse_chiavi_tipi_e_firma_del_vero():
    b, oro = _banco(PM.SCENARIO_APPROVATA)
    b.piano.inizia(_payload())
    oro.t = T0 + 40
    out = b.modello.evaluate(_payload(), sport="calcio", lambdas=(1.4, 1.1),
                             league_id=None, now_ts=oro.t)
    assert len(out) == 3
    campi = [f.name for f in OP.Opportunity.__dataclass_fields__.values()]
    for o in out:
        assert list(o.keys()) == campi
        assert isinstance(o["selection_id"], int) and isinstance(o["price"], float)
    # stessa FIRMA del vero (nomi, tipo di parametro, default)
    firma_vera = inspect.signature(OP.OpportunityModel.evaluate)
    firma_finta = inspect.signature(type(b.modello).evaluate)
    assert [(p.name, p.kind, p.default) for p in firma_finta.parameters.values()] == \
           [(p.name, p.kind, p.default) for p in firma_vera.parameters.values()]
    # e' un OpportunityModel VERO: `book` e' quello di produzione
    assert isinstance(b.modello, OP.OpportunityModel)
    assert type(b.modello).book is OP.OpportunityModel.book


def test_anomalia_finta_stesse_chiavi_e_tipi_di_anomaly_detect():
    vero_payload = _payload(minute=60, score_home=3, score_away=0, ou=[{
        "line": 2.5, "market_id": "1.2", "status": "OPEN", "ts_ms": 0,
        "selections": [{"name": "Over 2.5 Goals", "selection_id": 11, "back": 1.5,
                        "back_size": 100.0, "lay": 1.6, "lay_size": 100.0},
                       {"name": "Under 2.5 Goals", "selection_id": 12, "back": 3.0,
                        "back_size": 100.0, "lay": 3.2, "lay_size": 100.0}]}])
    veri = AN.detect(vero_payload, {}, params=None)
    assert veri, "il payload deve far parlare la regola 'decided' del vero"
    b, oro = _banco(PM.SCENARIO_ANOMALIA)
    b.piano.inizia(_payload())
    oro.t = T0 + 35
    finti = b.anomalie.detect(_payload(), {}, params={})
    assert len(finti) == 1
    assert list(finti[0].keys()) == list(veri[0].keys())
    assert _stessi_tipi(finti[0], veri[0]) == []
    assert inspect.signature(b.anomalie.detect).parameters.keys() == \
        inspect.signature(AN.detect).parameters.keys()


def test_combo_finta_stesse_chiavi_e_tipi_di_combos_find_combos():
    veri = CO.find_combos(_payload(), {}, params=None)
    assert veri, "il dutching 1X2 a 3.5 x3 (book 85,7%) deve far parlare il vero"
    b, oro = _banco(PM.SCENARIO_COMBOS)
    b.piano.inizia(_payload())
    oro.t = T0 + 35
    finti = b.combos.find_combos(_payload(), {}, params={})
    assert len(finti) == 1
    assert list(finti[0].keys()) == list(veri[0].keys())
    assert _stessi_tipi(finti[0], veri[0]) == []
    assert [list(l.keys()) for l in finti[0]["legs"]] == \
        [list(veri[0]["legs"][0].keys())] * len(finti[0]["legs"])
    assert _stessi_tipi(finti[0]["legs"][0], veri[0]["legs"][0]) == []
    assert inspect.signature(b.combos.find_combos).parameters.keys() == \
        inspect.signature(CO.find_combos).parameters.keys()


def test_combo_finta_sceglie_le_gambe_una_volta_e_non_le_cambia():
    b, oro = _banco(PM.SCENARIO_COMBOS)
    oro.t = T0
    b.piano.inizia(_payload())
    oro.t = T0 + 35
    p1 = _payload(odds=_odds(h=1.5, d=4.0, a=7.0))
    c1 = b.combos.find_combos(p1, {}, params={})[0]
    assert sorted(l["selection_id"] for l in c1["legs"]) == [2, 3]
    # le quote cambiano ordine: la combo resta quella (una combo e' le sue gambe)
    p2 = _payload(odds=_odds(h=9.0, d=4.0, a=2.0))
    c2 = b.combos.find_combos(p2, {}, params={})[0]
    assert sorted(l["selection_id"] for l in c2["legs"]) == [2, 3]


def test_tennis_finto_stesse_chiavi_del_vero_compresi_gli_extra():
    b, oro = _banco(PM.SCENARIO_APPROVATA, "tennis")
    classe = b.tennis.TennisOpportunityModel
    m = classe({})
    assert isinstance(m, TO.TennisOpportunityModel)
    payload = {"inplay": True, "mo_market_id": "1.9", "p1": "Uno", "p2": "Due",
               "sets": {"p1": 1, "p2": 0}, "games": {"p1": 2, "p2": 1},
               "odds": {"p1": {"selection_id": 7, "back": 1.3, "back_size": 500.0,
                               "lay": 1.31, "lay_size": 500.0},
                        "p2": {"selection_id": 8, "back": 4.2, "back_size": 500.0,
                               "lay": 4.3, "lay_size": 500.0}}}
    b.piano.inizia(payload)
    oro.t = T0 + 40
    out = m.evaluate(payload, oro.t)
    assert len(out) == 3
    campi = [f for f in TO.TennisOpportunity.__dataclass_fields__]
    sorgente = inspect.getsource(TO.TennisOpportunityModel)
    blocco = sorgente[sorgente.index("extra={"):]
    blocco = blocco[:blocco.index("}")]
    extra_veri = re.findall(r'"([a-z_]+)":', blocco)
    for o in out:
        assert list(o.keys()) == campi
        assert list(o["extra"].keys()) == extra_veri
        assert o["kind"] == "tennis"


# ---------------------------------------------------------------------------
# 2. le porte del DB
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nome", ["proposte_opportunita", "trades_pending_o_aperti",
                                  "scrivi_proposta_opportunita",
                                  "chiudi_proposta_opportunita",
                                  "marca_proposta_opportunita_annotata"])
def test_porte_del_db_con_la_firma_di_bot_db(nome):
    vera = inspect.signature(getattr(BD, nome))
    finta = inspect.signature(getattr(PM.ProposteDb, nome))
    par_finti = [p for p in finta.parameters.values() if p.name != "self"]
    assert [(p.name, p.default) for p in par_finti] == \
           [(p.name, p.default) for p in vera.parameters.values()]


def _db(mode: str = "live", params: Dict[str, Any] = None, t: float = T0):
    from Betfair.safe_strategy.tools.replay_registrazioni import DbSafeMemoria

    oro = _Orologio(t)
    db = DbSafeMemoria({"id": 1, "status": "running", "mode": mode,
                        "params": dict(params or {}), "stats": {}}, orologio=oro)
    return db, oro


def test_indice_unico_proposta_viva_solleva_come_il_database():
    db, _ = _db()
    rid = db.scrivi_proposta_opportunita("E1|model:MATCH_ODDS:2:back", {"mode": "live"})
    assert isinstance(rid, int)
    with pytest.raises(RuntimeError, match="uq_safe_requests_proposta_opp_viva"):
        db.scrivi_proposta_opportunita("E1|model:MATCH_ODDS:2:back", {"mode": "live"})
    # decaduta -> non e' piu' viva: la stessa chiave puo' tornare
    db.chiudi_proposta_opportunita(rid, "sparita")
    assert db.scrivi_proposta_opportunita("E1|model:MATCH_ODDS:2:back", {}) == rid + 1
    viste = db.proposte_opportunita()
    assert {r["status"] for r in viste} == {"proposed", "rejected"}
    assert "requests" not in db.mancanti and "richieste" not in db.mancanti


def test_trades_pending_o_aperti_come_il_vero():
    db, _ = _db()
    db.trades = [{"id": 1, "status": "pending", "mode": "live"},
                 {"id": 2, "status": "open", "mode": "paper"},
                 {"id": 3, "status": "hedged", "mode": "live"}]
    assert [t["id"] for t in db.trades_pending_o_aperti()] == [1, 2]
    assert [t["id"] for t in db.trades_pending_o_aperti(mode="live")] == [1]


# ---------------------------------------------------------------------------
# 3. le RPC
# ---------------------------------------------------------------------------
def test_rpc_approva_come_l_sql():
    db, oro = _db()
    rid = db.scrivi_proposta_opportunita("E1|model:MATCH_ODDS:2:back",
                                         {"price": 3.5, "mode": "live"})
    oro.t = T0 + 7.25
    esito = PM.rpc_approva(db, rid, oro.t, prezzo=3.55)
    assert esito == {"ok": True, "id": rid, "status": "pending"}
    r = db.requests[0]
    assert r["status"] == "pending"
    p = r["payload"]
    assert p["price"] == 3.5 and p["price_visto"] == 3.55     # il payload si ARRICCHISCE
    assert p["approved_at"].endswith("Z") and p["price_visto_at"].endswith("Z")
    # il timbro del clic e' leggibile ed e' FRESCO per la regola vera
    assert PO.clic_troppo_vecchio(p["price_visto_at"], oro.t) is False
    # una seconda approvazione non cambia niente
    assert PM.rpc_approva(db, rid, oro.t, prezzo=9.0)["ok"] is False
    assert db.requests[0]["payload"]["price_visto"] == 3.55


def test_rpc_ignora_come_l_sql():
    db, oro = _db()
    rid = db.scrivi_proposta_opportunita("E1|model:MATCH_ODDS:2:back", {})
    assert PM.rpc_ignora(db, rid, oro.t, "  ")["ok"] is True
    assert db.requests[0]["status"] == "rejected"
    assert db.requests[0]["result"] == {"ignorata_dall_utente": True,
                                        "motivo": "nessun motivo indicato"}
    assert PM.rpc_approva(db, rid, oro.t, prezzo=2.0)["ok"] is False
    assert db.requests[0]["status"] == "rejected"


# ---------------------------------------------------------------------------
# 4. i controlli PM: rossi sul difetto, zitti sul caso sano
# ---------------------------------------------------------------------------
KEY = "E1|model:MATCH_ODDS:2:back"


def _riga_feed(prezzo: float = 3.5) -> Dict[str, Any]:
    return {"event_id": "E1", "payload": _payload(odds=_odds(d=prezzo))}


def _codici(viol) -> List[str]:
    return sorted({c for c, _r, _d in viol})


def _clic(b, req_id, ok=True, prezzo=3.5, tipo="model", rilevata=True,
          sids=(2,), gambe=None, t=T0):
    c = PM.Clic(finestra="A", tipo=tipo, azione="approva", req_id=req_id,
                opp_key=KEY if tipo != "combo" else "E1|combo:abc", quando=t,
                esito={"ok": ok}, prezzo_visto=None if gambe else prezzo,
                prezzi_gambe=gambe, lato="back", sids=sids, rilevazione_attiva=rilevata)
    b.trader.clic.append(c)
    return c


def _trade(tid, key=KEY, price=3.5, origin="manual", mode="live", **kw):
    t = {"id": tid, "strategy": "model", "origin": origin, "mode": mode,
         "status": "open", "price": price, "selection_id": 2, "liability": 5.0,
         "placed_at": datetime.fromtimestamp(T0, tz=timezone.utc).isoformat(),
         "meta": {"opp_key": key, "da_proposta": True,
                  "esecuzione": {"price_richiesto": price}}}
    t.update(kw)
    return t


def _verifica(b, db, riga=None):
    soll: Dict[str, int] = {}
    v = b.sorveglianza.verifica(db=db, mercato=object(), riga=riga or _riga_feed(),
                                sollecitati=soll)
    return v, soll


def _proposta(db, mode="live", key=KEY, **payload):
    rid = db.scrivi_proposta_opportunita(key, {"mode": mode, "kind": "model",
                                               "selection_id": 2, "side": "back",
                                               **payload})
    return rid


def test_pm1_rosso_su_ordine_senza_approvazione_e_su_origin_auto():
    b, _ = _banco(PM.SCENARIO_APPROVATA)
    db, _ = _db(params={"strategy_modes": {"model": "live"}})
    db.trades.append(_trade(1))
    v, soll = _verifica(b, db)
    assert "PM1" in _codici(v) and soll["PM1"] == 1
    # caso sano: la stessa riga, con il PIAZZA del trader
    b2, _ = _banco(PM.SCENARIO_APPROVATA)
    db2, _ = _db(params={"strategy_modes": {"model": "live"}})
    rid = _proposta(db2)
    _clic(b2, rid)
    db2.requests[0]["status"] = "done"
    db2.requests[0]["result"] = {"ok": True, "trade_id": 1}
    db2.trades.append(_trade(1))
    v2, _ = _verifica(b2, db2)
    assert "PM1" not in _codici(v2)
    # origin='auto' e' sempre rosso, anche con la chiave approvata
    db2.trades.append(_trade(2, origin="auto"))
    v3, _ = _verifica(b2, db2)
    assert "PM1" in _codici(v3)


def test_pm2_rosso_su_due_proposte_vive_identiche():
    b, _ = _banco(PM.SCENARIO_APPROVATA)
    db, _ = _db()
    _proposta(db)
    v, soll = _verifica(b, db)
    assert "PM2" not in _codici(v) and soll["PM2"] == 1
    # una seconda viva scritta AGGIRANDO l'indice (il difetto da vedere)
    db.requests.append({**db.requests[0], "id": 99})
    v2, _ = _verifica(b, db)
    assert "PM2" in _codici(v2)
    # e una scrittura respinta dal DB e' rossa anche lei
    db.log("error", {"reason": "proposta_opportunita_fallita", "err": "duplicate"})
    v3, _ = _verifica(b, db)
    assert "PM2" in _codici(v3)


@pytest.mark.parametrize("prezzo_mercato,prezzo_chiesto,rosso", [
    (3.5, 3.5, False),     # visto = mercato, ordine al prezzo visto
    (3.8, 3.5, True),      # mercato +8,6% oltre il 2%: l'ordine non doveva partire
    (3.5, 3.6, True),      # ordine chiesto a un prezzo diverso dal visto
])
def test_pm3_prezzo_visto(prezzo_mercato, prezzo_chiesto, rosso):
    b, _ = _banco(PM.SCENARIO_APPROVATA)
    db, _ = _db(params={"strategy_modes": {"model": "live"}})
    rid = _proposta(db)
    _clic(b, rid, prezzo=3.5)
    db.requests[0].update(status="done", result={"ok": True, "trade_id": 1})
    db.trades.append(_trade(1, price=prezzo_chiesto))
    v, soll = _verifica(b, db, _riga_feed(prezzo_mercato))
    assert ("PM3" in _codici(v)) is rosso
    assert soll["PM3"] == 1


def test_pm3_rosso_su_rifiuto_falso_entro_tolleranza():
    b, _ = _banco(PM.SCENARIO_APPROVATA)
    db, _ = _db(params={"strategy_modes": {"model": "live"}})
    rid = _proposta(db)
    _clic(b, rid, prezzo=3.5)
    db.requests[0].update(status="error",
                          result={"error": "prezzo_visto_fuori_tolleranza"})
    v, _ = _verifica(b, db, _riga_feed(3.52))
    assert "PM3" in _codici(v)


def test_pm4_rosso_su_ordine_da_proposta_decaduta_o_rifiutata_e_su_riproposta():
    b, oro = _banco(PM.SCENARIO_SCADUTA)
    db, oro = _db()
    rid = _proposta(db, mode="paper")
    db.chiudi_proposta_opportunita(rid, "sparita")
    v, soll = _verifica(b, db)
    assert "PM4" not in _codici(v) and soll["PM4"] == 1
    db.trades.append(_trade(1, mode="paper"))
    v2, _ = _verifica(b, db)
    assert "PM4" in _codici(v2)
    # RIFIUTA tiene: una riproposta della stessa chiave e' rossa
    b3, _ = _banco(PM.SCENARIO_SCADUTA)
    db3, oro3 = _db()
    rid3 = _proposta(db3, mode="paper")
    PM.rpc_ignora(db3, rid3, oro3.t)
    oro3.t += 30
    _proposta(db3, mode="paper")
    v3, _ = _verifica(b3, db3)
    assert "PM4" in _codici(v3)


def test_pm5_modalita_scritta_e_parita_della_riga():
    b, _ = _banco(PM.SCENARIO_SCADUTA)
    db, _ = _db(mode="live", params={})          # model NON scritto -> paper
    _proposta(db, mode="paper")
    v, soll = _verifica(b, db)
    assert "PM5" not in _codici(v) and soll["PM5"] == 1
    _proposta(db, mode="live", key="E1|model:MATCH_ODDS:3:back")   # ereditata: rossa
    v2, _ = _verifica(b, db)
    assert "PM5" in _codici(v2)
    assert PM.modalita_attesa("paper", {"strategy_modes": {"model": "live"}}) == "paper"
    assert PM.modalita_attesa("live", {"strategy_modes": {"model": "live"}}) == "live"


def test_pm5_rosso_se_la_riga_nata_cambia_modalita():
    b, _ = _banco(PM.SCENARIO_APPROVATA)
    db, _ = _db(params={"strategy_modes": {"model": "live"}})
    rid = _proposta(db)
    _clic(b, rid)
    db.requests[0].update(status="done", result={"ok": True})
    db.trades.append(_trade(1, mode="paper"))
    v, _ = _verifica(b, db)
    assert "PM5" in _codici(v)


@pytest.mark.parametrize("rilevata,con_ordine,rosso", [
    (True, True, False), (False, False, False), (False, True, True)])
def test_pm6_anomalia_sparita_prima_del_clic(rilevata, con_ordine, rosso):
    b, _ = _banco(PM.SCENARIO_ANOMALIA)
    db, _ = _db(params={"strategy_modes": {"model": "live"}})
    rid = _proposta(db, kind="anomaly")
    _clic(b, rid, tipo="anomaly", rilevata=rilevata)
    db.requests[0].update(status="done" if con_ordine else "error",
                          result={"ok": True} if con_ordine else {"error": "x"})
    if con_ordine:
        db.trades.append(_trade(1))
    v, soll = _verifica(b, db)
    assert ("PM6" in _codici(v)) is rosso
    assert soll.get("PM6", 0) == (0 if rilevata else 1)


def test_pm7_rosso_su_richiesta_scaduta_per_l_eta_della_proposta():
    b, _ = _banco(PM.SCENARIO_APPROVATA)
    db, _ = _db(params={"strategy_modes": {"model": "live"}})
    rid = _proposta(db)
    _clic(b, rid, t=T0 + 180)
    db.requests[0].update(status="error", result={"reason": "richiesta_scaduta",
                                                  "age_s": 180.0})
    v, soll = _verifica(b, db)
    assert "PM7" in _codici(v) and soll["PM7"] == 1


def test_pm7_zitto_su_un_rifiuto_di_altro_genere():
    b, _ = _banco(PM.SCENARIO_APPROVATA)
    db, _ = _db(params={"strategy_modes": {"model": "live"}})
    rid = _proposta(db)
    _clic(b, rid)
    db.requests[0].update(status="error", result={"error": "risk_block"})
    v, _ = _verifica(b, db)
    assert "PM7" not in _codici(v)


def test_pm8_tutte_le_gambe_o_nessuna():
    b, _ = _banco(PM.SCENARIO_COMBOS)
    db, _ = _db(params={"strategy_modes": {"model": "live"}})
    rid = db.scrivi_proposta_opportunita("E1|combo:abc", {
        "mode": "live", "kind": "combo",
        "legs": [{"selection_id": 2, "side": "back", "price": 3.5},
                 {"selection_id": 3, "side": "back", "price": 3.5}]})
    _clic(b, rid, tipo="combo", sids=(2, 3), gambe={"0": 3.5, "1": 3.5})
    db.requests[0].update(status="done", result={"ok": True})
    db.trades.append(_trade(1, key="E1|combo:abc", selection_id=2))
    v, soll = _verifica(b, db)
    assert "PM8" in _codici(v) and soll["PM8"] == 1
    # tetto per gamba
    b2, _ = _banco(PM.SCENARIO_COMBOS)
    db2, _ = _db(params={"strategy_modes": {"model": "live"},
                         "max_liability_per_trade": 4.0})
    rid2 = db2.scrivi_proposta_opportunita("E1|combo:abc", dict(db.requests[0]["payload"]))
    _clic(b2, rid2, tipo="combo", sids=(2, 3), gambe={"0": 3.5, "1": 3.5})
    db2.requests[0].update(status="done", result={"ok": True})
    db2.trades += [_trade(1, key="E1|combo:abc", selection_id=2),
                   _trade(2, key="E1|combo:abc", selection_id=3)]
    v2, _ = _verifica(b2, db2)
    assert [d for c, _r, d in v2 if c == "PM8" and "tetto" in d]


def test_copertura_pm_solo_dei_controlli_sollecitabili():
    """Sul tennis non ci sono ne' anomalie ne' combo: PM6 e PM8 non entrano nella
    copertura (un 'non lo so' su un caso impossibile e' rumore). Col calcio intero
    ci sono tutti e otto."""
    tennis = [c for c, _r in PM.controlli_per(PM.SCENARI_TENNIS)]
    calcio = [c for c, _r in PM.controlli_per(PM.SCENARI_CALCIO)]
    assert "PM6" not in tennis and "PM8" not in tennis and len(tennis) == 6
    assert calcio == [c for c, _r in PM.elenco_controlli()]


def test_scenari_registrati_e_scenari_vecchi_intatti():
    from Betfair.safe_strategy.tools import replay_registrazioni as RR
    from Betfair.safe_strategy.tools import replay_tennis as RT

    assert list(RR.SCENARI_DESCRITTI)[-len(PM.SCENARI_CALCIO):] == list(PM.SCENARI_CALCIO)
    assert list(RT.SCENARI_DESCRITTI)[-2:] == list(PM.SCENARI_TENNIS)
    # i parametri degli scenari di prima NON cambiano
    base = RR._params_di_scenario("base", ("base", "esatto", "punta"), "live")
    assert "model" not in base["strategy_modes"] and "auto_trade_combos" not in base
    app = RR._params_di_scenario(PM.SCENARIO_APPROVATA, ("base",), "live")
    assert app["strategy_modes"] == {"base": "live", "model": "live"}
    sca = RR._params_di_scenario(PM.SCENARIO_SCADUTA, ("base",), "live")
    assert "model" not in sca["strategy_modes"]
    assert RR._params_di_scenario(PM.SCENARIO_COMBOS, ("base",), "live")["auto_trade_combos"]
    assert "model" not in RT.parametri_scenario("base")["strategy_modes"]
