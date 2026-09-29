"""CANTIERE J2 (28/09/2026) - il veto del flusso sulle strade che master ha
aggiunto o che il cantiere J non copriva per MERCATO.

Decisione dell'utente: se i prezzi di una partita non sono vivi nessun bot apre
ne' chiude a mercato su quei prezzi; il veto vale anche per un ordine APPROVATO
dall'utente (non parte, e lo si dice). Strade provate qui:
  * Safe, ordine a mano / proposta approvata (``_request_place``) su una linea
    col flusso fermo e il MATCH_ODDS vivo;
  * Safe, approvazione di una COMBO (``_request_place_combo``): una gamba su una
    linea ferma = nessuna gamba;
  * Safe, chiusura SOLIDALE di una combo (``_close_combo_siblings``): la sorella
    su un mercato fermo non si chiude su quei prezzi;
  * Safe, cash-out/uscita approvata rifiutata: il rifiuto porta il MOTIVO;
  * Omega, proposta di missione (``_cs_suggestion``): il blocco del feed col
    flusso fermo non si usa (si va al catalogo+book REST).
Righe prodotte dallo SCANNER VERO (``build_rows``), book ``MarketBook`` di
betfairlightweight: gli stessi finti del cantiere J.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from Betfair.safe_strategy import bot_service as BS
from Betfair.safe_strategy.tests.test_flusso_interrotto_cantiere_j_2026_09_28 import (
    MO, OU35, OU45, CacheFinta, Orologio, book, giro, runner_dict, scanner_calcio,
)
from Betfair.stream import flusso_prezzi as FP


def _righe() -> "tuple[dict, dict, float]":
    """(riga con le linee FERME e il MATCH_ODDS vivo, riga tutta viva, ora della
    riga ferma)."""
    ck = Orologio()
    scan = scanner_calcio(ck, con_linee=True)
    tab: Dict[str, dict] = {}
    scan._apply_market_book(book("1.35", OU35))
    scan._apply_market_book(book("1.45", OU45))
    scan._apply_market_book(book("1.200", MO))
    giro(scan, tab)
    viva = dict(tab["c1"])
    ck.t += 50.0
    scan._apply_market_book(book("1.200", MO))
    scan.events["c1"]["minute"] = 21
    giro(scan, tab)
    ferma = dict(tab["c1"])
    assert ferma["payload"]["flusso"]["mercati_fermi"] == ["1.35", "1.45"]
    return ferma, viva, ck.t


@pytest.fixture(autouse=True)
def _cache_pulite():
    BS._SKIP_LOG_STATE.clear()
    BS._SCANNER_TS_CACHE.update({"cycle_ts": None, "value": None, "stato": None})
    BS._FLUSSO_ANNUNCIATO.clear()
    FP._NON_NOTO_AVVISATO.clear()
    yield
    BS._SCANNER_TS_CACHE.update({"cycle_ts": None, "value": None, "stato": None})
    BS._FLUSSO_ANNUNCIATO.clear()
    FP._NON_NOTO_AVVISATO.clear()


class Db:
    """Le porte di ``BotDB`` usate dalle strade provate (stesse firme)."""

    def __init__(self, trade: Optional[dict] = None) -> None:
        self.attivita: List[tuple] = []
        self.trade = trade

    def log(self, kind, payload):
        self.attivita.append((kind, dict(payload)))

    def scanner_status(self):
        return None

    def get_trade(self, tid):
        if self.trade is not None and int(tid) == int(self.trade["id"]):
            return dict(self.trade)
        return None

    def update_trade(self, *_a, **_k):
        pass

    def insert_trade(self, row):
        raise AssertionError("nessuna riga deve nascere su prezzi non vivi")


def _ora_dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


# ===========================================================================
# 1. ORDINE A MANO / PROPOSTA APPROVATA sulla linea ferma
# ===========================================================================
def _ordine_sulla_linea(mid: str = "1.35") -> dict:
    return {"event_id": "c1", "market_id": mid, "market_type": "OVER_UNDER_35",
            "selection_id": 1222344, "side": "lay", "price": 1.52, "size": 2.0,
            "mode": "paper", "opp_key": "c1:model:u35"}


def test_ordine_approvato_su_linea_ferma_non_parte_e_dice_perche():
    ferma, _viva, ora = _righe()
    db = Db()
    res = BS._request_place(db=db, market=None, rows_by_event={"c1": ferma},
                            payload=_ordine_sulla_linea(), params={}, now=_ora_dt(ora))
    assert res == {"error": "flusso_interrotto:" + FP.MOTIVO_MERCATO_FERMO}, res
    skip = [p for k, p in db.attivita if k == "skip"]
    assert skip and skip[0]["reason"] == "flusso_interrotto:" + FP.MOTIVO_MERCATO_FERMO
    assert skip[0]["market_id"] == "1.35"


def test_ordine_approvato_sul_match_odds_vivo_non_ha_il_veto_del_flusso(monkeypatch):
    """Controllo: stessa riga, ordine sul MATCH_ODDS (vivo): il veto del flusso
    NON scatta (la strada prosegue fino al mercato: qui si ferma prima di
    piazzare perche' ``prices_for`` e' finto)."""
    ferma, _viva, ora = _righe()
    monkeypatch.setattr(BS, "prices_for", lambda **kw: None)
    db = Db()
    payload = dict(_ordine_sulla_linea("1.200"), market_type="MATCH_ODDS", selection_id=11,
                   price=1.82)
    try:
        res = BS._request_place(db=db, market=None, rows_by_event={"c1": ferma},
                                payload=payload, params={}, now=_ora_dt(ora))
    except AssertionError:
        raise
    except Exception:  # noqa: BLE001 - oltre il veto il resto della strada non interessa
        res = {}
    assert not str(res.get("error") or "").startswith("flusso_interrotto"), res
    assert not [p for k, p in db.attivita
                if str(p.get("reason") or "").startswith("flusso_interrotto")]


# ===========================================================================
# 2. APPROVAZIONE DI UNA COMBO: una gamba ferma = nessuna gamba
# ===========================================================================
def _combo(prima_mid: str) -> dict:
    gamba_linea = {"market_id": prima_mid, "market_type": "OVER_UNDER_35",
                   "selection_id": 1222344, "side": "lay", "price": 1.52, "size": 2.0}
    gamba_mo = {"market_id": "1.200", "market_type": "MATCH_ODDS", "selection_id": 11,
                "side": "back", "price": 1.80, "size": 2.0}
    return {"kind": "combo", "event_id": "c1", "combo_id": "k1", "mode": "paper",
            "opp_key": "c1:combo:k1", "legs": [gamba_linea, gamba_mo]}


def test_combo_approvata_con_una_gamba_su_linea_ferma_nessuna_gamba():
    ferma, _viva, ora = _righe()
    db = Db()
    res = BS._request_place(db=db, market=None, rows_by_event={"c1": ferma},
                            payload=_combo("1.35"), params={}, now=_ora_dt(ora))
    assert res.get("error") == "flusso_interrotto:" + FP.MOTIVO_MERCATO_FERMO, res
    assert res.get("gamba") == 0


def test_combo_approvata_linee_vive_nessun_veto_del_flusso(monkeypatch):
    _ferma, viva, ora = _righe()
    monkeypatch.setattr(BS, "prices_for", lambda **kw: None)
    db = Db()
    res = BS._request_place(db=db, market=None, rows_by_event={"c1": viva},
                            payload=_combo("1.35"), params={}, now=_ora_dt(ora - 50.0))
    assert not str(res.get("error") or "").startswith("flusso_interrotto"), res


# ===========================================================================
# 3. CHIUSURA SOLIDALE: la sorella su un mercato fermo
# ===========================================================================
def _sorella() -> dict:
    return {"id": 51, "status": "open", "origin": "auto", "mode": "paper",
            "strategy": "model", "sport": "calcio", "event_id": "c1",
            "market_id": "1.35", "market_type": "OVER_UNDER_35",
            "selection_id": 1222344, "side": "lay", "price": 1.52, "size": 2.0,
            "meta": {"combo_id": "k1"}}


def test_sorella_su_linea_ferma_non_si_chiude(monkeypatch):
    ferma, _viva, ora = _righe()
    chiusure: List[Any] = []
    monkeypatch.setattr(BS.X, "close_trade", lambda **kw: chiusure.append(kw) or {"ok": True})
    monkeypatch.setattr(BS, "_mercato_non_operabile", lambda *a, **k: None)
    db = Db()
    n = BS._close_combo_siblings(db=db, market=None, legs=[_sorella()],
                                 prices_by_id={51: {"back": 1.50, "lay": 1.52}}, params={},
                                 now=_ora_dt(ora), reason="combo: chiusura solidale", row=ferma)
    assert n == 0 and chiusure == []
    attese = [p for k, p in db.attivita if k == "exit_wait"]
    assert attese and attese[0]["reason"] == "combo_solidale"
    assert attese[0]["wait"] == "flusso_interrotto:" + FP.MOTIVO_MERCATO_FERMO


def test_sorella_su_linea_viva_si_chiude(monkeypatch):
    _ferma, viva, ora = _righe()
    chiusure: List[Any] = []
    monkeypatch.setattr(BS.X, "close_trade", lambda **kw: chiusure.append(kw) or {"ok": True})
    monkeypatch.setattr(BS, "_mercato_non_operabile", lambda *a, **k: None)
    monkeypatch.setattr(BS, "_stamp_exit_on_parent", lambda *a, **k: None)
    db = Db()
    BS._close_combo_siblings(db=db, market=None, legs=[_sorella()],
                             prices_by_id={51: {"back": 1.50, "lay": 1.52}}, params={},
                             now=_ora_dt(ora - 50.0), reason="combo: chiusura solidale", row=viva)
    assert len(chiusure) == 1


# ===========================================================================
# 4. USCITA / CASH-OUT APPROVATO rifiutato: il motivo c'e'
# ===========================================================================
def test_cashout_rifiutato_dice_il_motivo_del_flusso(monkeypatch):
    ferma, _viva, ora = _righe()
    monkeypatch.setattr(BS, "_book_prices", lambda **kw: None)
    trade = {"id": 41, "status": "open", "origin": "auto", "mode": "paper",
             "strategy": "base", "sport": "calcio", "event_id": "c1",
             "market_id": "1.35", "market_type": "OVER_UNDER_35",
             "selection_id": 1222344, "side": "lay", "price": 1.52, "size": 2.0, "meta": {}}
    res = BS._request_cashout(db=Db(trade), market=None, rows_by_event={"c1": ferma},
                              payload={"trade_id": 41}, params={}, now=_ora_dt(ora))
    assert res.get("rejected") == "quote non disponibili", res
    assert res.get("motivo") == "flusso_interrotto:" + FP.MOTIVO_MERCATO_FERMO


# ===========================================================================
# 5. OMEGA: la proposta di missione non usa il blocco del feed fermo
# ===========================================================================
def _riga_cs(ferma_cs: bool) -> dict:
    ck = Orologio()
    scan = scanner_calcio(ck)
    scan.cs_markets["c1"] = {"market_id": "1.CS", "names": {1: "0 - 0", 2: "1 - 0"}}
    scan._rebuild_market_index()
    cs = [runner_dict(1, (8.0, 50.0), (8.4, 40.0)), runner_dict(2, (6.0, 50.0), (6.2, 40.0))]
    scan._apply_market_book(book("1.CS", cs))
    scan._apply_market_book(book("1.200", MO))
    tab: Dict[str, dict] = {}
    giro(scan, tab)
    if ferma_cs:
        ck.t += 50.0
        scan._apply_market_book(book("1.200", MO))
        scan.events["c1"]["minute"] = 25
        giro(scan, tab)
        assert tab["c1"]["payload"]["flusso"]["mercati_fermi"] == ["1.CS"]
    return dict(tab["c1"], updated_at=datetime.now(timezone.utc).isoformat())


def _omega_suggerimento(monkeypatch, riga: dict) -> List[Any]:
    from Betfair.omega import omega_service as OS

    cache = CacheFinta({"c1": riga})
    monkeypatch.setattr(OS._scan_feed, "shared_cache", lambda: cache)
    for d in (OS._CACHE_FEED_RIGHE, OS._CACHE_FEED_LETTO_A, OS._CACHE_FEED_CHIESTO_A,
              OS._CACHE_SCANNER):
        d.clear()
    monkeypatch.setattr(OS, "_canale_scan_attivo", lambda: None)
    mercato = object()
    monkeypatch.setattr(OS, "_real_market", mercato)
    visti: List[Any] = []
    monkeypatch.setattr(OS, "_leg_market", lambda m, ev, mt, payload: visti.append(payload))
    OS._cs_suggestion(market=mercato, mission={"event_id": "c1", "event_name": "Roma v Lazio"},
                      market_type="CORRECT_SCORE", params={}, now=datetime.now(timezone.utc))
    return visti


def test_omega_missione_col_cs_fermo_va_al_rest(monkeypatch):
    assert _omega_suggerimento(monkeypatch, _riga_cs(True)) == [None]


def test_omega_missione_col_cs_vivo_usa_il_feed(monkeypatch):
    visti = _omega_suggerimento(monkeypatch, _riga_cs(False))
    assert len(visti) == 1 and isinstance(visti[0], dict)


# ===========================================================================
# 6. REGOLA UNICA (reperto A del coordinatore, 28/09): flusso fermo =
#    nessuna apertura; chiusure e protezioni dal ripiego REST gia' esistente;
#    REST muto = attesa + riga CRITICA al piu' una al minuto.
# ===========================================================================
class MercatoRest:
    """``market.read_book(market_id, names)`` come ``omega_market.read_book``
    (chiavi vere: status, inplay, runners[selection_id, back_price, back_size,
    lay_price, lay_size, lay_ladder]). ``book`` None = REST muto."""

    def __init__(self, book: Optional[dict]) -> None:
        self.book = book
        self.chiamate: List[str] = []

    def read_book(self, market_id, names):
        self.chiamate.append(str(market_id))
        return self.book


def _book_rest_linea() -> dict:
    return {"market_id": "1.35", "status": "OPEN", "inplay": True, "runners": [
        {"selection_id": 1222344, "name": "Under 3.5 Goals", "status": "ACTIVE",
         "back_price": 1.49, "back_size": 40.0, "lay_price": 1.51, "lay_size": 30.0,
         "lay_ladder": [[1.51, 30.0]]},
        {"selection_id": 1222345, "name": "Over 3.5 Goals", "status": "ACTIVE",
         "back_price": 2.7, "back_size": 20.0, "lay_price": 2.76, "lay_size": 10.0,
         "lay_ladder": [[2.76, 10.0]]}]}


def _trade_linea() -> dict:
    return {"id": 61, "status": "open", "origin": "auto", "mode": "paper",
            "strategy": "base", "sport": "calcio", "event_id": "c1",
            "market_id": "1.35", "market_type": "OVER_UNDER_35",
            "selection_id": 1222344, "side": "lay", "price": 1.52, "size": 2.0,
            "meta": {}}


def _uscita_a(monkeypatch, riga: dict, ora: float, mercato) -> "tuple[Db, list]":
    from Betfair.safe_strategy import exits as XE_

    BS._REST_STATE.update({"last": {}, "cycle_ts": 0.0, "used": 0})
    monkeypatch.setattr(XE_, "decide", lambda *a, **k: XE_.ExitDecision("time", "test", 0.0))
    monkeypatch.setattr(BS, "_model_gate", lambda **k: (False, {}))
    monkeypatch.setattr(BS, "_exit_due", lambda *a, **k: True)
    monkeypatch.setattr(BS, "combo_siblings", lambda *a, **k: [])
    monkeypatch.setattr(BS, "uscite_automatiche_di", lambda *a, **k: True)
    inviate: List[dict] = []
    monkeypatch.setattr(BS, "_send_exit", lambda **kw: inviate.append(kw) or True)
    db = Db()
    BS._process_exit_one(db=db, market=mercato, trade=_trade_linea(), row=riga, params={},
                         xp=XE_.merge_exit_params(None), now=_ora_dt(ora), now_ts=ora,
                         scanner_ts=ora)
    return db, inviate


def test_regola_unica_safe_chiusura_col_flusso_fermo_e_rest_vivo_parte_coi_prezzi_rest(monkeypatch):
    ferma, _viva, ora = _righe()
    mk = MercatoRest(_book_rest_linea())
    db, inviate = _uscita_a(monkeypatch, ferma, ora, mk)
    assert mk.chiamate == ["1.35"]
    assert len(inviate) == 1
    p = inviate[0]["prices"]
    assert p["fonte"] == FP.FONTE_RIPIEGO_REST and p["lay"] == 1.51 and p["back"] == 1.49
    note = [pl for k, pl in db.attivita if k == "ripiego_rest"]
    assert note and note[0]["fonte"] == "rest_ripiego" and note[0]["trade_id"] == 61


def test_regola_unica_safe_flusso_fermo_e_rest_muto_nessun_ordine_e_riga_critica(monkeypatch):
    ferma, _viva, ora = _righe()
    mk = MercatoRest(None)
    db, inviate = _uscita_a(monkeypatch, ferma, ora, mk)
    assert inviate == []
    crit = [pl for k, pl in db.attivita if k == "flusso_interrotto"]
    assert len(crit) == 1 and crit[0]["critical"] is True
    assert crit[0]["esposizione_eur"] == 1.04          # lay 2,00 @ 1,52
    assert crit[0]["da_secondi"] is not None and crit[0]["da_secondi"] >= 0
    assert crit[0]["trade_id"] == 61
    # un minuto non e' passato: nessuna seconda riga critica
    db2, _ = _uscita_a(monkeypatch, ferma, ora + 20.0, mk)
    assert [k for k, _p in db2.attivita if k == "flusso_interrotto"] == []


def test_regola_unica_safe_nessuna_apertura_col_flusso_fermo_anche_col_rest_vivo(monkeypatch):
    """Apertura automatica sul mercato fermo: scartata PRIMA di ogni lettura
    REST (nessuna chiamata), nessuna riga."""
    from Betfair.safe_strategy.tests.test_flusso_interrotto_cantiere_j_bis_2026_09_28 import (
        DbSegnali, EngineUnSegnale, _segnale_sulla_linea,
    )
    ferma, _viva, ora = _righe()
    mk = MercatoRest(_book_rest_linea())

    def _mai(**_kw):
        raise AssertionError("apertura col flusso fermo")
    monkeypatch.setattr(BS, "_execute", _mai)
    db = DbSegnali()
    BS.scan_and_place(db=db, market=mk, engine=EngineUnSegnale(_segnale_sulla_linea(ora)),
                      rows=[ferma], params={"variants": ["esatto"], "max_open_trades": 0,
                                           "max_liability_per_trade": 0.0,
                                           "min_size_available_factor": 0.0,
                                           "commission_pct": 5.0, "max_spread_ratio": 1.6},
                      mode="paper", now=_ora_dt(ora), scanner_ts=ora, scanner_ts_known=True)
    assert db.trades == [] and mk.chiamate == []


def test_regola_unica_safe_sorella_ferma_col_rest_vivo_si_chiude_coi_prezzi_rest(monkeypatch):
    ferma, _viva, ora = _righe()
    BS._REST_STATE.update({"last": {}, "cycle_ts": 0.0, "used": 0})
    chiusure: List[Any] = []
    monkeypatch.setattr(BS.X, "close_trade", lambda **kw: chiusure.append(kw) or {"ok": True})
    monkeypatch.setattr(BS, "_mercato_non_operabile", lambda *a, **k: None)
    monkeypatch.setattr(BS, "_stamp_exit_on_parent", lambda *a, **k: None)
    db = Db()
    BS._close_combo_siblings(db=db, market=MercatoRest(_book_rest_linea()), legs=[_sorella()],
                             prices_by_id={51: {"back": 1.50, "lay": 1.52}}, params={},
                             now=_ora_dt(ora), reason="combo: chiusura solidale", row=ferma)
    assert len(chiusure) == 1 and chiusure[0]["prices"]["fonte"] == FP.FONTE_RIPIEGO_REST
    assert chiusure[0]["prices"]["lay"] == 1.51


# ---------------------------------------------------------------------------
# OMEGA: apertura bloccata col flusso fermo; green-up dal ripiego REST detto
# ---------------------------------------------------------------------------
class _DbO:
    def __init__(self):
        self.attivita: List[tuple] = []

    def log(self, kind, payload):
        self.attivita.append((kind, payload))

    def update_trade(self, *_a, **_k):
        pass


def _omega_evento(monkeypatch, vivo: bool):
    from types import SimpleNamespace

    from Betfair.omega import omega_model as OM
    from Betfair.omega import omega_service as OS

    mk = MercatoRest(None)
    monkeypatch.setattr(OS, "_real_market", mk)
    monkeypatch.setattr(OS, "_live_state_for",
                        lambda *a, **k: (OM.LiveState(30, 0, 0), None, "0-0"))
    monkeypatch.setattr(OS, "_feed_fresh_for_decision", lambda *a, **k: False)
    esito = FP.VIVO if vivo else FP.Esito(False, FP.MOTIVO_INTERROTTO, "fermo")
    monkeypatch.setattr(OS, "_flusso_feed", lambda eid: esito)
    monkeypatch.setattr(OS.E, "mission_phase", lambda **k: OS._LEGS[1][3])
    tentate: List[Any] = []
    monkeypatch.setattr(OS, "_leg_retry_allowed", lambda *a, **k: tentate.append(a) or False)
    db = _DbO()
    ev = SimpleNamespace(event_id="c1", open_date=None, name="Roma v Lazio")
    params = {"max_events": 0, "strategy_version": 2, "ft_entry_min": 0, "ft_entry_max": 200,
              "ht_entry_min": 0, "ht_entry_max": 200}
    out = OS._scan_event_legs(ev=ev, events=[ev], control={}, params=params, traded_ids=set(),
                              traded_legs=set(), aggregates={}, market=mk, db=db,
                              now=datetime.now(timezone.utc), score_lookup=None, goal=0.0,
                              realized=0.0, mode="paper", commission=0.05, traded_count=0,
                              minutes_seen={})
    return out, tentate, db, mk


def test_regola_unica_omega_nessuna_apertura_col_flusso_fermo(monkeypatch):
    out, tentate, db, mk = _omega_evento(monkeypatch, vivo=False)
    assert out == (0, 0) and tentate == [] and mk.chiamate == []
    assert any(k == "flusso_interrotto" for k, _p in db.attivita)


def test_regola_unica_omega_controllo_flusso_vivo_si_valutano_le_gambe(monkeypatch):
    _out, tentate, _db, _mk = _omega_evento(monkeypatch, vivo=True)
    assert tentate, "col flusso vivo le gambe si valutano"


def test_regola_unica_omega_green_up_col_ripiego_rest_e_col_rest_muto(monkeypatch):
    from Betfair.omega import omega_service as OS
    from Betfair.safe_strategy import execution as X

    OS._FLUSSO_CRITICO_OMEGA.azzera()
    OS._FLUSSO_RIPIEGO_OMEGA.azzera()
    mk = MercatoRest(None)
    monkeypatch.setattr(OS, "_real_market", mk)
    monkeypatch.setattr(OS, "_flusso_feed",
                        lambda eid: FP.Esito(False, FP.MOTIVO_INTERROTTO, "fermo"))
    monkeypatch.setattr(X, "known_closings", lambda *a, **k: None)   # si ferma dopo i prezzi
    tr = {"id": 5, "event_id": "c1", "runner_name": "1 - 0", "market_id": "1.CS",
          "selection_id": 2, "side": "lay", "price": 6.0, "size": 2.0, "mode": "paper", "meta": {}}
    params = {"greenup_trigger_distance": 0, "greenup_price_trigger_ratio": 0.5,
              "greenup_settle_delay_s": 0}
    payload = {"score_home": 1, "score_away": 0, "minute": 60}
    # REST vivo: prezzi dal ripiego, detto nell'attivita'
    monkeypatch.setattr(OS, "_cashout_prices", lambda m, t: {"back": 1.2, "lay": 1.25})
    db = _DbO()
    OS._greenup_one(tr=dict(tr), params=params, market=mk, db=db,
                    now=datetime.now(timezone.utc), payload=payload)
    assert [k for k, _p in db.attivita if k == "ripiego_rest"] == ["ripiego_rest"]
    # REST muto: riga CRITICA con esposizione, una sola nel minuto
    monkeypatch.setattr(OS, "_cashout_prices", lambda m, t: None)
    db = _DbO()
    for _ in range(3):
        OS._greenup_one(tr=dict(tr), params=params, market=mk, db=db,
                        now=datetime.now(timezone.utc), payload=payload)
    crit = [p for k, p in db.attivita if k == "flusso_interrotto"]
    assert len(crit) == 1 and crit[0]["critical"] is True and crit[0]["esposizione_eur"] == 10.0
