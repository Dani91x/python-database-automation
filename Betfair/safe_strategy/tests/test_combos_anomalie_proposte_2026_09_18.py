# -*- coding: utf-8 -*-
"""COMBINAZIONI E ANOMALIE DIVENTANO PROPOSTE (18/09/2026).

Ordine dell'utente (testuale, riportato dal coordinatore): «si, convertili a
proposte e falli finire come proposte sia tennis che calcio» — riferito ad
``auto_trade_combos`` e ``auto_trade_anomalies``, gli ultimi due motori che il
17/09 erano rimasti "automatici, motore proprio" (vedi
``CHECKPOINT_PROPOSTE_OPPORTUNITA_2026-09-17.md``, divergenza 1).

Questo file certifica, sul codice di produzione (``bot_service.py``,
``proposte_opportunita.py``), la parte che ``test_bot_service.py`` non copre a
livello di ciclo intero:
  1. COMBO — una proposta con TUTTE le gambe dentro (``payload.legs``), MAI un
     ``insert_trade``/``_execute`` finche' non arriva l'approvazione;
     l'approvazione (``_request_place`` -> ``_request_place_combo``) e'
     ATOMICA: una gamba sparita o fuori tolleranza -> rifiuto dichiarato,
     NESSUNA gamba piazzata; un fallimento in esecuzione sulla seconda gamba
     (dopo la riserva) -> la prima, gia' fillata, viene SVOLTA subito (H-20/H6,
     stessa logica di ieri, mai riscritta).
  2. ANOMALIA — chiave STABILE (``event_id|anomaly:market_type:selection_id:
     side``, MAI il tempo): un RIFIUTA tiene, una DECADENZA vera si vede
     quando l'anomalia sparisce dal feed. All'approvazione si ricontrolla che
     l'anomalia ci sia ancora (prezzo corrente sul lato) e non si sia mossa
     oltre tolleranza.
  3. In ENTRAMBI i casi: la modalita' della riga resta quella della
     STRATEGIA (``modalita_di_strategia``), non del servizio nudo — una riga
     PAPER non diventa mai LIVE solo perche' il servizio e' in LIVE.

I finti hanno le IDENTICHE chiavi del vero (``bot_db.proposte_opportunita`` e
compagne, righe del feed con gli stessi blocchi di
``test_due_motori_tennis_2026_09_17.py``/``test_bot_service.py``).

ASCII-only nel codice, commenti in italiano.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import proposte_opportunita as PO

NOW = datetime(2026, 9, 18, 21, 0, tzinfo=timezone.utc)
EV = "36099001"


class DbFinto:
    """Specchio in memoria di safe_strategy_* — stesse chiavi del vero, sia
    per le proposte (``bot_db.proposte_opportunita`` e compagne) sia per i
    trade (``insert_trade``/``delete_trade``/``get_trade``/``update_trade``,
    identici a ``FakeDB`` di ``test_bot_service.py``)."""

    def __init__(self) -> None:
        self.attivita: list[tuple[str, dict]] = []
        self.opps: list = []
        self.trades: list[dict] = []
        self.richieste: list[dict] = []
        self._id = 0

    # --- attivita' / feed ---
    def log(self, kind, payload=None):
        self.attivita.append((kind, dict(payload or {})))

    def kinds(self):
        return [k for k, _ in self.attivita]

    def upsert_opportunities(self, righe):
        self.opps.extend(righe)

    def purge_opportunities(self, older_than_iso):
        pass

    def open_trades(self):
        return [t for t in self.trades if t.get("status") in ("open", "hedged")]

    # 18/09 — stessa chiave del vero (``bot_db.trades_pending_o_aperti``):
    # QUALUNQUE origine, solo 'pending'/'open'.
    def trades_pending_o_aperti(self, mode=None):
        return [t for t in self.trades if t.get("status") in ("pending", "open")]

    def aggregates(self, mode=None):
        return {}

    def scanner_status(self):
        return None

    def list_trades(self):
        return list(self.trades)

    def traded_signal_keys(self, mode=None):
        return {(str(t.get("event_id")), str(t.get("signal_key")))
                for t in self.trades
                if t.get("signal_key") and t.get("status") != "error"
                and str(t.get("origin") or "auto") == "auto"}

    # --- trade (stesse chiavi di FakeDB in test_bot_service.py) ---
    def insert_trade(self, trade):
        self._id += 1
        row = dict(trade)
        row["id"] = self._id
        self.trades.append(row)
        return self._id

    def update_trade(self, trade_id, **fields):
        for t in self.trades:
            if t["id"] == trade_id:
                t.update(fields)

    def delete_trade(self, trade_id):
        self.trades = [t for t in self.trades
                       if not (t["id"] == trade_id and t.get("status") == "pending")]

    def get_trade(self, trade_id):
        return next((t for t in self.trades if t["id"] == int(trade_id)), None)

    def closing_trades_for(self, ids):
        ids = {int(i) for i in ids}
        return [t for t in self.trades if t.get("closes_trade_id") in ids]

    # --- coda delle proposte: stesse chiavi del vero ---
    def proposte_opportunita(self, ore=24, limit=300):
        return [r for r in self.richieste
                if r.get("kind") == "place"
                and r.get("status") in ("proposed", "rejected")
                and (r.get("payload") or {}).get("opp_key")]

    def scrivi_proposta_opportunita(self, opp_key, payload, req_id=None):
        corpo = {**payload, "opp_key": str(opp_key)}
        if req_id is not None:
            for r in self.richieste:
                if r["id"] == int(req_id) and r["status"] == "proposed":
                    r["payload"] = corpo
            return int(req_id)
        self._id += 1
        self.richieste.append({"id": self._id, "kind": "place", "status": "proposed",
                               "payload": corpo, "result": None})
        return self._id

    def chiudi_proposta_opportunita(self, req_id, motivo):
        for r in self.richieste:
            if r["id"] == int(req_id) and r["status"] == "proposed":
                r["status"] = "rejected"
                r["result"] = {"decaduta": True, "motivo": str(motivo)[:200]}

    def marca_proposta_opportunita_annotata(self, req_id, result):
        for r in self.richieste:
            if r["id"] == int(req_id):
                r["result"] = {**(result or {}), "attivita_scritta": True}

    # --- comode per i test ---
    def vive(self):
        return [r for r in self.richieste if r["status"] == "proposed"]


# ---------------------------------------------------------------------------
# Feed: STESSI blocchi del vero scanner (ou/btts), un evento in-play calcio
# con le due gambe della combo E l'anomalia sulla stessa selezione ou25.
# ---------------------------------------------------------------------------
def _riga_feed(event_id=EV, *, ou25_back=2.2, ou25_lay=2.24, btts_back=1.9, btts_lay=1.95):
    return {"event_id": event_id, "sport": "calcio", "updated_at": NOW.isoformat(),
            "payload": {"event_name": "Roma v Lazio", "inplay": True, "minute": 40,
                       "score_home": 1, "score_away": 0, "odds_ts_ms": 1,
                       "ou": [{"market_id": "ou25", "line": 2.5, "selections": [
                           {"selection_id": 47972, "name": "Over 2.5 Goals",
                            "back": ou25_back, "lay": ou25_lay,
                            "back_size": 300.0, "lay_size": 200.0}]}],
                       "btts": {"market_id": "btts1", "selections": [
                           {"selection_id": 30246, "name": "Yes",
                            "back": btts_back, "lay": btts_lay,
                            "back_size": 10.0, "lay_size": 11.0}]}}}


def _combo_legs():
    return [
        {"market_type": "OVER_UNDER_25", "market_id": "ou25", "selection_id": 47972,
         "selection_name": "Over 2.5 Goals", "side": "back", "price": 2.2,
         "size_available": 300.0, "stake_ratio": 0.5},
        {"market_type": "BOTH_TEAMS_TO_SCORE", "market_id": "btts1", "selection_id": 30246,
         "selection_name": "Yes", "side": "back", "price": 1.9,
         "size_available": 10.0, "stake_ratio": 0.5},
    ]


def _combo(**kw):
    c = {"id": "cA", "confidence": 1.0, "edge": 0.3, "rationale": "dutching",
         "legs": _combo_legs()}
    c.update(kw)
    return c


def _anomaly(**kw):
    a = {"market_type": "OVER_UNDER_25", "market_id": "ou25", "selection_id": 47972,
         "selection_name": "Over 2.5 Goals", "side": "back", "price": 2.2,
         "size_available": 300.0, "confidence": 1.0, "edge": 0.2,
         "p_model": 0.7, "p_implied": 0.45, "ev": 0.18, "rationale": "spread anomalo",
         "rule": "ou_ladder"}
    a.update(kw)
    return a


class FakeCombosMod:
    def __init__(self, combos):
        self.combos = list(combos)

    def find_combos(self, payload, book, *, params=None):
        return list(self.combos)


def _ciclo_combo(db, combos, *, rows=None, mode="paper", params=None):
    """``process_opportunities`` vero, col modulo combo finto — stessa forma
    di ``_ciclo`` in ``test_proposte_opportunita_2026_09_17.py``."""
    righe = rows if rows is not None else [_riga_feed()]

    class _FakeOppModel:
        def evaluate(self, payload, *, sport, lambdas, league_id, now_ts, **kw):
            return []

        def book(self, payload, *, lambdas, league_id, ht_ratio=None):
            return {"over_2_5": 0.5}

    fake_opp_mod = _FakeOppMod()
    return S.process_opportunities(
        db=db, market=None, rows=righe,
        params={"opps_interval_s": 0.0, "risk": {"model_stake": 5.0},
               **(params or {})},
        model=_FakeOppModel(), opp_mod=fake_opp_mod, mode=mode, now=NOW,
        state={"last_ts": 0.0, "hashes": {}},
        rows_by_event={r["event_id"]: r for r in righe},
        auto_trade=True, auto_trade_kinds={"model": True, "tennis": True, "combo": True},
        extra={"anomaly": None, "combos": FakeCombosMod(combos), "tennis": None},
        scanner_ts=NOW.timestamp(), scanner_ts_known=True)


class _FakeOppMod:
    @staticmethod
    def resolve_lambdas(payload, *, fixture):
        return (1.3, 1.1, 135, "prematch")


def _ciclo_anomalia(db, anomalies, *, rows=None, mode="paper", params=None):
    """``process_opportunities`` vero con le anomalie GIA' TROVATE nello stato
    (come le scrive ``process_anomalies``): qui si isola la parte che
    PROPONE, senza rimontare anche ``detect()``."""
    righe = rows if rows is not None else [_riga_feed()]

    class _FakeOppModel:
        def evaluate(self, payload, *, sport, lambdas, league_id, now_ts, **kw):
            return []

    st = {"last_ts": 0.0, "hashes": {}, "anomalies": {EV: [dict(a, kind="anomaly") for a in anomalies]}}
    return S.process_opportunities(
        db=db, market=None, rows=righe,
        params={"opps_interval_s": 0.0, "risk": {"model_stake": 5.0},
               **(params or {})},
        model=_FakeOppModel(), opp_mod=_FakeOppMod(), mode=mode, now=NOW,
        state=st, rows_by_event={r["event_id"]: r for r in righe},
        auto_trade=True, auto_trade_kinds={"model": True, "tennis": True, "combo": True},
        extra={"anomaly": None, "combos": None, "tennis": None},
        scanner_ts=NOW.timestamp(), scanner_ts_known=True)


# ===========================================================================
# 1. COMBO — LA PROPOSTA NASCE CON TUTTE LE GAMBE, L'ORDINE NO
# ===========================================================================
def test_combo_propone_con_tutte_le_gambe_e_non_chiama_execute(monkeypatch):
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("_execute non deve essere chiamata: le combo si "
                       "piazzano SOLO dalla scheda, atomicamente")))
    db = DbFinto()
    out = _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    assert out["traded"] == 0 and db.trades == []
    assert out["proposte"] == 1
    riga = db.vive()[0]
    assert riga["kind"] == "place" and riga["status"] == "proposed"
    p = riga["payload"]
    assert p["kind"] == "combo" and p["opp_key"].startswith(f"{EV}|combo:")
    legs = p["legs"]
    assert len(legs) == 2
    assert {l["market_id"] for l in legs} == {"ou25", "btts1"}
    assert [l["size"] for l in legs] == [5.0, 5.0]
    assert p["size"] == 10.0 and p["liability"] == 10.0 and p["mode"] == "paper"


def test_ispezione_niente_insert_trade_ne_execute_in_proponi_combo():
    """Come per ``_proponi_opps`` (17/09): il codice che costruisce la
    proposta combo non puo' aggirare il cancelletto per distrazione."""
    src = inspect.getsource(S._proponi_combo)
    corpo = src.split('"""', 2)[-1]
    assert "insert_trade" not in corpo and "_execute(" not in corpo
    assert not hasattr(S, "_auto_trade_combos"), \
        "la vecchia strada automatica e' ancora li': andava sostituita, non affiancata"


# ===========================================================================
# 2. COMBO — APPROVAZIONE ATOMICA
# ===========================================================================
def test_combo_approvazione_piazza_tutte_le_gambe_quando_fresche_e_in_tolleranza(monkeypatch):
    db = DbFinto()
    _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    corpo = dict(db.vive()[0]["payload"])

    def esecuzione(**kw):
        db.update_trade(kw["trade_id"], size_matched=kw["row"]["size"],
                        avg_price_matched=kw["row"]["price"], betfair_updated_at=NOW.isoformat())
        return _Esito(status="open", price=kw["row"]["price"], size=kw["row"]["size"])

    monkeypatch.setattr(S, "_execute", esecuzione)
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("ok") is True, out
    assert out["placed_legs"] == 2 and out["total_legs"] == 2
    assert len(db.trades) == 2
    assert all(t["mode"] == "paper" and t["strategy"] == "model"
              and t["meta"]["kind"] == "combo" for t in db.trades)
    assert {t["market_id"] for t in db.trades} == {"ou25", "btts1"}
    assert [t["size"] for t in db.trades] == [5.0, 5.0]
    att = [p for k, p in db.attivita if k == "opportunita_piazzata"]
    assert att and att[0]["kind"] == "combo" and att[0]["placed_legs"] == 2


def test_combo_approvazione_gamba_sparita_nessuna_gamba_piazzata(monkeypatch):
    """CRITERIO DI ACCETTAZIONE ESPLICITO: una gamba sparita dal feed (nessun
    prezzo risolvibile ne' dal feed ne' dal REST) fa rifiutare l'INTERA
    proposta — nessuna gamba, nemmeno quella ancora buona, viene piazzata."""
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("nessuna gamba deve arrivare a _execute")))
    db = DbFinto()
    _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    corpo = dict(db.vive()[0]["payload"])
    # la riga del feed usata all'approvazione NON porta piu' il mercato btts1
    # (rimosso dal book, come un mercato chiuso/sospeso sparito dallo scan):
    # "sparita" per il codice, senza inventare un prezzo.
    riga_senza_btts = _riga_feed()
    del riga_senza_btts["payload"]["btts"]
    out = S._request_place(db=db, market=None, rows_by_event={EV: riga_senza_btts},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("error") == "combo_gamba_sparita"
    assert db.trades == [], "NESSUNA gamba piazzata, nemmeno quella ancora quotata"
    assert _skip_reasons(db, "combo_gamba_sparita")


def test_combo_approvazione_gamba_fuori_tolleranza_rifiutata(monkeypatch):
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("nessuna gamba deve arrivare a _execute")))
    db = DbFinto()
    _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    corpo = dict(db.vive()[0]["payload"])
    # ou25 si e' mossa da 2.20 a 2.60: oltre il 2% di tolleranza
    riga_mossa = _riga_feed(ou25_back=2.60, ou25_lay=2.64)
    out = S._request_place(db=db, market=None, rows_by_event={EV: riga_mossa},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("error") == "combo_gamba_fuori_tolleranza"
    assert db.trades == []


def test_combo_approvazione_gamba_con_prezzo_nan_rifiutata(monkeypatch):
    """ORDINE DEL COORDINATORE (18/09, 3o giro): ramo scritto da me
    (``_request_place_combo``), fail-closed su un prezzo non finito."""
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("una gamba con prezzo nan non deve arrivare a _execute")))
    db = DbFinto()
    _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    corpo = dict(db.vive()[0]["payload"])
    corpo["legs"][0]["price"] = float("nan")
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("error") == "combo_gamba_0_dati_non_validi"
    assert db.trades == []


def test_combo_approvazione_gamba_con_size_infinita_rifiutata(monkeypatch):
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("una gamba con size infinita non deve arrivare a _execute")))
    db = DbFinto()
    _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    corpo = dict(db.vive()[0]["payload"])
    corpo["legs"][1]["size"] = float("inf")
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("error") == "combo_gamba_1_dati_non_validi"
    assert db.trades == []


def test_combo_approvazione_fallimento_alla_seconda_gamba_unwind(monkeypatch):
    """CRITERIO DI ACCETTAZIONE ESPLICITO: la RISERVA di entrambe le gambe
    riesce, ma l'ESECUZIONE della seconda fallisce (rifiuto Betfair): la prima
    gamba, gia' fillata, viene SVOLTA SUBITO — stessa macchina H-20/H6 di
    ``_auto_trade_combos``, estratta in ``_esegui_combo_riservata`` e riusata
    qui, non riscritta."""
    chiamate: list[str] = []

    def esecuzione(**kw):
        mid = kw["row"]["market_id"]
        chiamate.append(mid)
        if mid == "btts1":
            return _Esito(status="error", fill_note="rifiuto_betfair")
        db.update_trade(kw["trade_id"], status="open", size_matched=kw["row"]["size"])
        return _Esito(status="open", price=kw["row"]["price"], size=kw["row"]["size"])

    db = DbFinto()
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(AssertionError("non usata")))
    _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    corpo = dict(db.vive()[0]["payload"])
    monkeypatch.setattr(S, "_execute", esecuzione)
    # ``_unwind_combo`` chiude via ``prices_from_row``: serve un prezzo per la
    # gamba fillata (ou25) nella riga del feed passata alla chiusura.
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("ok") is True and out["placed_legs"] == 1 and out["total_legs"] == 2
    assert chiamate == ["ou25", "btts1"]
    ou25_leg = next(t for t in db.trades if t["market_id"] == "ou25" and not t.get("closes_trade_id"))
    # 24/09 - ADATTATO alla decisione dell'utente B25 ("LASCIA E AVVISA"): la
    # gamba e' origin='manual' (nata dal PIAZZA del trader) e NON si chiude
    # piu'. Resta aperta, marcata, e l'avviso dice quale gamba e' stata uccisa.
    assert ou25_leg["origin"] == "manual"
    assert ou25_leg["status"] == "open", "la gamba manuale e' del trader: resta a mercato"
    assert [t for t in db.trades if t.get("closes_trade_id") == ou25_leg["id"]] == []
    assert isinstance(ou25_leg["meta"].get(S.COMBO_LASCIATA_KEY), dict)
    avvisi = [p for k, p in db.attivita if k == "combo_incomplete" and p.get("lasciata_al_trader")]
    assert len(avvisi) == 1 and avvisi[0]["trade_id"] == ou25_leg["id"]
    assert "btts1" not in avvisi[0]["reason"] and "Yes" in avvisi[0]["reason"]
    assert "combo_incomplete" in db.kinds()


def test_combo_rifiuto_persiste_e_decade_se_una_gamba_sparisce():
    db = DbFinto()
    _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    riga = db.vive()[0]
    chiave = riga["payload"]["opp_key"]
    riga["status"] = "rejected"
    riga["result"] = {"ignorata_dall_utente": True, "motivo": "non mi convince"}
    out = _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    assert out["proposte"] == 0 and db.vive() == [], "la combo rifiutata e' tornata su: NON deve"
    # torna con la STESSA chiave dopo il rifiuto: resta rifiutata
    out2 = _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    assert out2["proposte"] == 0
    # una gamba sola sparisce dal libro combo (find_combos non la produce
    # piu'): l'INTERA proposta decade, non "si aggiorna a una gamba".
    db2 = DbFinto()
    _ciclo_combo(db2, [_combo()], params={"auto_trade_combos": True})
    assert db2.vive()[0]["payload"]["opp_key"] == chiave
    _ciclo_combo(db2, [], params={"auto_trade_combos": True})   # niente combo questo giro
    assert db2.vive() == []
    assert "opportunita_decaduta" in db2.kinds()


def test_combo_riga_paper_resta_paper_anche_con_servizio_live(monkeypatch):
    """CRITERIO DI ACCETTAZIONE ESPLICITO: col servizio in LIVE e il modello
    in PAPER (``strategy_modes`` assente), la combo si propone e si piazza in
    PAPER — mai ereditando ``control.mode`` nudo."""
    monkeypatch.setattr(S, "_execute", lambda **kw: _Esito(
        status="open", price=kw["row"]["price"], size=kw["row"]["size"]))
    db = DbFinto()
    _ciclo_combo(db, [_combo()], mode="live", params={"auto_trade_combos": True})
    corpo = dict(db.vive()[0]["payload"])
    assert corpo["mode"] == "paper"
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="live")
    assert out.get("ok") is True, out
    assert all(t["mode"] == "paper" for t in db.trades)


def test_combo_proposta_che_dice_live_col_modello_in_paper_e_rifiutata():
    db = DbFinto()
    _ciclo_combo(db, [_combo()], mode="live", params={"auto_trade_combos": True})
    corpo = {**db.vive()[0]["payload"], "mode": "live"}
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="live")
    assert "rejected" in out and db.trades == []


# ===========================================================================
# 3. ANOMALIA — CHIAVE STABILE, RIFIUTO PERSISTE, DECADENZA VERA
# ===========================================================================
def test_anomalia_propone_con_chiave_stabile_senza_tempo():
    db = DbFinto()
    out = _ciclo_anomalia(db, [_anomaly()])
    assert out["traded"] == 0 and db.trades == []
    assert out["proposte"] == 1
    p = db.vive()[0]["payload"]
    assert p["kind"] == "anomaly"
    assert p["opp_key"] == f"{EV}|anomaly:OVER_UNDER_25:47972:back"
    assert ":" + str(int(NOW.timestamp())) not in p["opp_key"], \
        "la chiave NON deve portare l'epoch (dedupe di ieri, non piu' pertinente)"


def test_anomalia_rifiutata_non_viene_riproposta():
    """CRITERIO DI ACCETTAZIONE ESPLICITO."""
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()])
    riga = db.vive()[0]
    riga["status"] = "rejected"
    riga["result"] = {"ignorata_dall_utente": True, "motivo": "non convince"}
    out = _ciclo_anomalia(db, [_anomaly()])
    assert out["proposte"] == 0, "l'anomalia rifiutata e' tornata su: NON deve"
    assert db.vive() == []
    assert db.kinds().count("opportunita_rifiutata") == 1
    _ciclo_anomalia(db, [_anomaly()])
    assert db.kinds().count("opportunita_rifiutata") == 1, "l'attivita' si scrive una volta sola"


def test_anomalia_decade_quando_sparisce_dal_feed():
    """CRITERIO DI ACCETTAZIONE ESPLICITO: l'anomalia non e' piu' fra quelle
    trovate (``st['anomalies']`` vuoto per l'evento) -> la proposta decade."""
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()])
    assert len(db.vive()) == 1
    _ciclo_anomalia(db, [])          # partita ancora in gioco, anomalia sparita
    assert db.vive() == []
    assert "opportunita_decaduta" in db.kinds()
    motivo = [p for k, p in db.attivita if k == "opportunita_decaduta"][0]
    assert motivo["motivo"] == "opportunita' sparita dal feed"


# ===========================================================================
# 4. ANOMALIA — APPROVAZIONE (esiste ancora? prezzo entro tolleranza?)
# ===========================================================================
def test_anomalia_approvazione_ok_scrive_consapevolezza(monkeypatch):
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()])
    corpo = dict(db.vive()[0]["payload"])

    def esecuzione(**kw):
        db.update_trade(kw["trade_id"], size_matched=kw["row"]["size"],
                        avg_price_matched=kw["row"]["price"], betfair_updated_at=NOW.isoformat())
        return _Esito(status="open", price=kw["row"]["price"], size=kw["row"]["size"])

    monkeypatch.setattr(S, "_execute", esecuzione)
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("ok") is True, out
    riga = db.trades[0]
    assert riga["meta"]["kind"] == "anomaly" and riga["meta"]["opp_key"] == corpo["opp_key"]
    assert riga["size_matched"] == 5.0 and riga["avg_price_matched"] == corpo["price"]


def test_anomalia_approvazione_sparita_rifiutata(monkeypatch):
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("l'anomalia sparita non deve arrivare a _execute")))
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()])
    corpo = dict(db.vive()[0]["payload"])
    riga_senza_ou25 = _riga_feed()
    riga_senza_ou25["payload"]["ou"] = []
    out = S._request_place(db=db, market=None, rows_by_event={EV: riga_senza_ou25},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("error") == "anomalia_sparita"
    assert db.trades == []


def test_anomalia_approvazione_fuori_tolleranza_rifiutata(monkeypatch):
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("l'anomalia fuori tolleranza non deve arrivare a _execute")))
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()])
    corpo = dict(db.vive()[0]["payload"])
    riga_mossa = _riga_feed(ou25_back=2.70, ou25_lay=2.74)
    out = S._request_place(db=db, market=None, rows_by_event={EV: riga_mossa},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("error") == "anomalia_fuori_tolleranza"
    assert db.trades == []


def test_anomalia_manuale_investi_senza_opp_key_non_ha_la_barriera_nuova(monkeypatch):
    """Il "Investi" manuale dalla tabella delle opportunita' (nessun
    ``opp_key``: e' una decisione immediata, non l'approvazione di una
    scheda) NON guadagna la nuova barriera di tolleranza — resta come prima
    del 18/09."""
    monkeypatch.setattr(S, "_execute", lambda **kw: _Esito(
        status="open", price=kw["row"]["price"], size=kw["row"]["size"]))
    db = DbFinto()
    payload_manuale = {"event_id": EV, "market_id": "ou25", "market_type": "OVER_UNDER_25",
                       "selection_id": 47972, "side": "back", "price": 2.2, "size": 5.0,
                       "mode": "paper", "strategy": "model", "kind": "anomaly"}
    riga_mossa = _riga_feed(ou25_back=2.70, ou25_lay=2.74)   # prezzo mosso oltre tolleranza
    out = S._request_place(db=db, market=None, rows_by_event={EV: riga_mossa},
                           payload=payload_manuale, params={"commission_pct": 5.0}, now=NOW)
    assert out.get("ok") is True, out   # nessun rifiuto: non e' un'approvazione di proposta


def test_anomalia_riga_paper_resta_paper_anche_con_servizio_live(monkeypatch):
    monkeypatch.setattr(S, "_execute", lambda **kw: _Esito(
        status="open", price=kw["row"]["price"], size=kw["row"]["size"]))
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()], mode="live")
    corpo = dict(db.vive()[0]["payload"])
    assert corpo["mode"] == "paper"
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="live")
    assert out.get("ok") is True and db.trades[0]["mode"] == "paper"


# ===========================================================================
# 5. COERENZA CON GLI ORDINI (18/09, permesso esplicito dell'utente: «se ho
# approvato o rifiutato un segnale deve essere coerente con gli ordini»).
#
# Reperto EREDITATO (trovato nel 1o giro, chiuso qui): un'anomalia/combo/
# modello/tennis approvato diventa un trade ``origin='manual'`` (mai
# 'auto': lo scrive ``_request_place``/``_esegui_combo_riservata``), quindi
# ``_traded_keys`` (che filtra SOLO 'auto') non lo vedeva: lo STESSO segnale
# poteva tornare a proporsi mentre l'ordine che ne era nato era ancora in
# coda o abbinato sul mercato. ``_opp_keys_con_ordine_vivo`` chiude il buco
# leggendo gli stati VERI della tabella (pending/open, qualunque origine).
# ===========================================================================
def test_proposta_approvata_con_ordine_ancora_pending_non_si_ripropone():
    """CRITERIO DI ACCETTAZIONE ESPLICITO. Vale per QUALSIASI kind a una
    gamba sola (model/tennis/anomaly: passano tutti da ``_proponi_opps``)."""
    db = DbFinto()
    opp_key = PO.opp_key(EV, "model", "OVER_UNDER_25", 47972, "back")
    # l'ordine nato da un'approvazione precedente: origin='manual' (mai
    # 'auto', cosi' nasce _request_place), stato 'pending' (in coda, non
    # ancora confermato — lo stato che ``open_trades()`` non vede).
    db.trades.append({"id": 1, "event_id": EV, "signal_key": "model:OVER_UNDER_25:47972:back",
                      "status": "pending", "origin": "manual", "mode": "paper",
                      "meta": {"opp_key": opp_key}})
    vivi = S._opp_keys_con_ordine_vivo(db)
    assert vivi == {opp_key}
    corpi = S._proponi_opps(db=db, payload=_riga_feed()["payload"], event_id=EV,
                            opps=[_anomaly()], params={"opps_min_confidence": 0.0,
                                                       "opps_stake": 4.0},
                            mode="paper", now=NOW, rows_by_event={EV: _riga_feed()},
                            kind="model", vivi_ordine=vivi,
                            scanner_ts=NOW.timestamp(), scanner_ts_known=True)
    assert corpi == [], "l'ordine e' ancora pending: il segnale NON deve tornare a proporsi"


def test_proposta_approvata_con_ordine_abbinato_open_non_si_ripropone():
    db = DbFinto()
    opp_key = PO.opp_key(EV, "anomaly", "OVER_UNDER_25", 47972, "back")
    db.trades.append({"id": 1, "event_id": EV, "signal_key": "anomaly:OVER_UNDER_25:47972:back",
                      "status": "open", "origin": "manual", "mode": "paper",
                      "meta": {"opp_key": opp_key}})
    vivi = S._opp_keys_con_ordine_vivo(db)
    corpi = S._proponi_opps(db=db, payload=_riga_feed()["payload"], event_id=EV,
                            opps=[_anomaly()], params={"opps_min_confidence": 0.0,
                                                       "risk": {"model_stake": 5.0}},
                            mode="paper", now=NOW, rows_by_event={EV: _riga_feed()},
                            kind="anomaly", vivi_ordine=vivi,
                            scanner_ts=NOW.timestamp(), scanner_ts_known=True)
    assert corpi == [], "l'ordine e' abbinato (open): il segnale NON deve tornare a proporsi"


def test_proposta_approvata_con_ordine_chiuso_senza_abbinamento_si_ripropone():
    """CRITERIO DI ACCETTAZIONE ESPLICITO: un ordine 'error' (rifiutato da
    Betfair, mai abbinato) NON blocca — il segnale e' di nuovo un segnale
    nuovo, esattamente come dice l'ordine dell'utente."""
    db = DbFinto()
    opp_key = PO.opp_key(EV, "model", "OVER_UNDER_25", 47972, "back")
    db.trades.append({"id": 1, "event_id": EV, "signal_key": "model:OVER_UNDER_25:47972:back",
                      "status": "error", "origin": "manual", "mode": "paper",
                      "meta": {"opp_key": opp_key}})
    vivi = S._opp_keys_con_ordine_vivo(db)
    assert opp_key not in vivi
    corpi = S._proponi_opps(db=db, payload=_riga_feed()["payload"], event_id=EV,
                            opps=[_anomaly()], params={"opps_min_confidence": 0.0,
                                                       "opps_stake": 4.0},
                            mode="paper", now=NOW, rows_by_event={EV: _riga_feed()},
                            kind="model", vivi_ordine=vivi,
                            scanner_ts=NOW.timestamp(), scanner_ts_known=True)
    assert len(corpi) == 1, "l'ordine e' chiuso SENZA abbinamento: il segnale torna a proporsi"


def test_proposta_approvata_con_ordine_gia_regolato_si_ripropone():
    """Un ordine gia' REGOLATO (won/lost/void, non solo 'error') non e' piu'
    'vivo' nel senso di ``pending``/``open``: la posizione ha gia' vissuto
    tutto il suo ciclo. Non e' un caso esplicitamente elencato dall'ordine
    dell'utente (che parla di "chiuso/annullato/scaduto SENZA abbinamento"),
    ma la lettura letterale degli stati richiesti ("SOLO pending/open
    bloccano") lo implica: lo dichiaro qui, non lo invento in silenzio."""
    for stato in ("won", "lost", "void", "hedged"):
        db = DbFinto()
        opp_key = PO.opp_key(EV, "model", "OVER_UNDER_25", 47972, "back")
        db.trades.append({"id": 1, "event_id": EV, "status": stato, "origin": "manual",
                          "mode": "paper", "meta": {"opp_key": opp_key}})
        vivi = S._opp_keys_con_ordine_vivo(db)
        assert opp_key not in vivi, f"stato {stato} non deve bloccare la riproposta"


def test_combo_con_una_gamba_ancora_viva_non_si_ripropone():
    """CRITERIO DI ACCETTAZIONE ESPLICITO: coerenza SULL'INSIEME. Una sola
    gamba ancora 'pending' basta a bloccare l'INTERA combo — nessuna logica
    per-gamba in piu': ``meta.opp_key`` e' lo STESSO ``combo_key`` su ogni
    gamba (scritto da ``_esegui_combo_riservata``), quindi un solo controllo
    di appartenenza al set basta."""
    db = DbFinto()
    ckey = PO.combo_key(EV, "cA")   # "cA" e' l'id esplicito di _combo()
    db.trades.append({"id": 1, "event_id": EV, "market_id": "ou25", "selection_id": 47972,
                      "signal_key": "combo:cA:0", "status": "pending", "origin": "manual",
                      "mode": "paper", "meta": {"opp_key": ckey, "combo_id": "cA"}})
    vivi = S._opp_keys_con_ordine_vivo(db)
    assert vivi == {ckey}
    corpi = S._proponi_combo(db=db, payload=_riga_feed()["payload"], event_id=EV,
                             combos=[_combo()], params={"opps_min_confidence": 0.0,
                                                        "risk": {"model_stake": 5.0}},
                             mode="paper", now=NOW, rows_by_event={EV: _riga_feed()},
                             vivi_ordine=vivi,
                             scanner_ts=NOW.timestamp(), scanner_ts_known=True)
    assert corpi == [], "una gamba della combo e' ancora viva: l'INTERA combo non si ripropone"


def test_combo_con_tutte_le_gambe_chiuse_senza_abbinamento_si_ripropone():
    db = DbFinto()
    ckey = PO.combo_key(EV, "cA")
    db.trades.append({"id": 1, "event_id": EV, "signal_key": "combo:cA:0", "status": "error",
                      "origin": "manual", "mode": "paper", "meta": {"opp_key": ckey}})
    db.trades.append({"id": 2, "event_id": EV, "signal_key": "combo:cA:1", "status": "error",
                      "origin": "manual", "mode": "paper", "meta": {"opp_key": ckey}})
    vivi = S._opp_keys_con_ordine_vivo(db)
    assert ckey not in vivi
    corpi = S._proponi_combo(db=db, payload=_riga_feed()["payload"], event_id=EV,
                             combos=[_combo()], params={"opps_min_confidence": 0.0,
                                                        "risk": {"model_stake": 5.0}},
                             mode="paper", now=NOW, rows_by_event={EV: _riga_feed()},
                             vivi_ordine=vivi,
                             scanner_ts=NOW.timestamp(), scanner_ts_known=True)
    assert len(corpi) == 1, "nessuna gamba e' viva: la combo torna a proporsi"


def test_lettura_ordini_vivi_fallita_e_fail_closed_non_si_propone_niente():
    """Come ``_leggi_proposte_opp``: se la lettura fallisce, ``None`` e
    NESSUNA proposta nasce in questo ciclo (fail-closed, non fail-open)."""
    db = DbFinto()

    def rotta(*_a, **_k):
        raise RuntimeError("DB muto")

    db.trades_pending_o_aperti = rotta  # type: ignore[assignment]
    assert S._opp_keys_con_ordine_vivo(db) is None
    out = _ciclo_anomalia(db, [_anomaly()])
    assert out["proposte"] == 0 and db.richieste == []


def test_db_senza_l_accessor_nuovo_non_blocca_nulla_compatibilita():
    """Un finto vecchio (senza ``trades_pending_o_aperti``, come ``FakeDB`` in
    ``test_bot_service.py`` prima di questo giro) non deve rompersi: si
    degrada al comportamento di prima (nessun blocco extra), stessa scelta
    gia' fatta per ``_traded_keys`` quando l'accessor manca."""
    class DbSenzaAccessor(DbFinto):
        trades_pending_o_aperti = None  # niente attributo callable

    db = DbSenzaAccessor()
    assert S._opp_keys_con_ordine_vivo(db) == set()


# ===========================================================================
# 6. RUBINETTI DELLE PROPOSTE (18/09, decisione «B» dell'utente): spengono la
# VISTA di un tipo di proposta (nessun tetto numerico). Quattro chiavi NUOVE
# (``proponi_model``/``proponi_tennis``/``proponi_combo``/``proponi_anomaly``),
# default TRUE: NON sono gli ``auto_trade_*`` (quelli valgono False oggi sul
# DB col vecchio significato — riusarli avrebbe nascosto in silenzio le
# proposte di modello che l'utente vuole vedere).
# ===========================================================================
def _ciclo_modello(db, opps, *, rows=None, mode="paper", params=None):
    righe = rows if rows is not None else [_riga_feed()]

    class _FakeOppModel:
        def evaluate(self, payload, *, sport, lambdas, league_id, now_ts, **kw):
            return list(opps)

    return S.process_opportunities(
        db=db, market=None, rows=righe,
        params={"opps_interval_s": 0.0, "risk": {"model_stake": 5.0},
               "opps_stake": 4.0, **(params or {})},
        model=_FakeOppModel(), opp_mod=_FakeOppMod(), mode=mode, now=NOW,
        state={"last_ts": 0.0, "hashes": {}},
        rows_by_event={r["event_id"]: r for r in righe},
        auto_trade=True, auto_trade_kinds={"model": True, "tennis": True, "combo": True},
        extra={"anomaly": None, "combos": None, "tennis": None},
        scanner_ts=NOW.timestamp(), scanner_ts_known=True)


def test_rubinetto_model_a_false_zero_proposte_nuove():
    db = DbFinto()
    out = _ciclo_modello(db, [_anomaly()], params={"proponi_model": False})
    assert out["proposte"] == 0 and db.vive() == []


def test_rubinetto_anomaly_a_false_zero_proposte_nuove():
    db = DbFinto()
    out = _ciclo_anomalia(db, [_anomaly()], params={"proponi_anomaly": False})
    assert out["proposte"] == 0 and db.vive() == []


def test_rubinetto_combo_a_false_zero_proposte_nuove():
    db = DbFinto()
    out = _ciclo_combo(db, [_combo()], params={"proponi_combo": False})
    assert out["proposte"] == 0 and db.vive() == []


def test_rubinetto_a_false_le_proposte_gia_vive_decadono_con_motivo_dichiarato():
    """CRITERIO DI ACCETTAZIONE ESPLICITO."""
    db = DbFinto()
    _ciclo_combo(db, [_combo()])   # rubinetto aperto (default): la combo si propone
    assert len(db.vive()) == 1
    out = _ciclo_combo(db, [_combo()], params={"proponi_combo": False})
    assert out["proposte"] == 0
    assert db.vive() == [], "il rubinetto chiuso non fa decadere la proposta gia' viva"
    motivo = [p for k, p in db.attivita if k == "opportunita_decaduta"][0]
    assert motivo["motivo"] == "tipo di proposta disattivato dall'interruttore"

    # stesso comportamento per l'anomalia
    db2 = DbFinto()
    _ciclo_anomalia(db2, [_anomaly()])
    assert len(db2.vive()) == 1
    _ciclo_anomalia(db2, [_anomaly()], params={"proponi_anomaly": False})
    assert db2.vive() == []
    motivo2 = [p for k, p in db2.attivita if k == "opportunita_decaduta"][0]
    assert motivo2["motivo"] == "tipo di proposta disattivato dall'interruttore"


def test_rubinetto_default_assente_vale_true():
    """CRITERIO DI ACCETTAZIONE ESPLICITO: nessuna delle quattro chiavi nei
    ``params`` -> comportamento di oggi invariato (tutto proposto)."""
    p = S.resolve_params({})
    assert p["proponi_model"] is True and p["proponi_tennis"] is True
    assert p["proponi_combo"] is True and p["proponi_anomaly"] is True
    db = DbFinto()
    out = _ciclo_combo(db, [_combo()], params={})   # nessuna chiave proponi_* passata
    assert out["proposte"] == 1


def test_rubinetto_valore_non_booleano_ripiega_sul_default_true():
    """Un valore sporco sul DB (stringa, None esplicito) non deve spegnere una
    vista che l'utente non ha mai toccato consapevolmente."""
    for sporco in (None, "no", 0, [], "false"):
        p = S.resolve_params({"proponi_combo": sporco})
        assert p["proponi_combo"] is True, f"valore sporco {sporco!r} ha spento il rubinetto"
    p2 = S.resolve_params({"proponi_combo": False})
    assert p2["proponi_combo"] is False, "un False esplicito deve invece spegnerlo"


def test_rubinetto_nessun_effetto_su_ordini_gia_approvati(monkeypatch):
    """Spegnere il rubinetto DOPO l'approvazione non deve toccare l'ordine gia'
    aperto: e' solo una vista sulle PROPOSTE, non un freno sugli ordini."""
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()])
    corpo = dict(db.vive()[0]["payload"])

    def esecuzione(**kw):
        db.update_trade(kw["trade_id"], status="open", size_matched=kw["row"]["size"])
        return _Esito(status="open", price=kw["row"]["price"], size=kw["row"]["size"])

    monkeypatch.setattr(S, "_execute", esecuzione)
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0,
                                                  "proponi_anomaly": False},
                           now=NOW, control_mode="paper")
    assert out.get("ok") is True, out
    assert len(db.trades) == 1 and db.trades[0]["status"] == "open"


# ===========================================================================
# 7. IL PREZZO CHE L'UTENTE VEDE (18/09, ordine dell'utente: «il prezzo può
# muoversi, io devo vedere la tab aggiornata e quando clicco prendiamo QUEL
# NUMERO CHE VEDO»). ``price_visto``/``legs_prices_visti`` arrivano nel
# payload SOLO se il client li manda (dopo la migrazione RPC): senza, tutto
# funziona come nel 3o giro (fotografia congelata).
# ===========================================================================
def test_prezzo_visto_diventa_il_prezzo_dell_ordine_non_la_fotografia(monkeypatch):
    """CRITERIO DI ACCETTAZIONE ESPLICITO."""
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly(price=2.2)])   # fotografia congelata: 2.2
    corpo = dict(db.vive()[0]["payload"])
    assert corpo["price"] == 2.2
    corpo["price_visto"] = 2.3   # il numero che l'utente vedeva al clic
    corpo["price_visto_at"] = NOW.isoformat()
    visto: dict = {}

    def esecuzione(**kw):
        visto["price"] = kw["row"]["price"]
        db.update_trade(kw["trade_id"], status="open", size_matched=kw["row"]["size"])
        return _Esito(status="open", price=kw["row"]["price"], size=kw["row"]["size"])

    monkeypatch.setattr(S, "_execute", esecuzione)
    # la quota corrente deve essere vicina al VISTO (2.3), non alla fotografia
    riga = _riga_feed(ou25_back=2.3, ou25_lay=2.34)
    out = S._request_place(db=db, market=None, rows_by_event={EV: riga},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("ok") is True, out
    assert visto["price"] == 2.3, "l'ordine doveva partire al prezzo VISTO, non alla fotografia"
    assert db.trades[0]["price"] == 2.3
    # la liability si ricalcola sul prezzo NUOVO (regola di stake invariata:
    # e' la formula che dipende dal prezzo, non lo stake stesso)
    assert db.trades[0]["liability"] == db.trades[0]["size"]   # back: liability = stake, sempre


def test_prezzo_visto_lay_liability_ricalcolata_sul_prezzo_nuovo(monkeypatch):
    """Lay: la liability dipende dal prezzo (stake*(prezzo-1)) — QUESTA si
    ricalcola sul prezzo visto; lo STAKE resta quello di sempre (non tocco la
    regola, la applico al prezzo nuovo, come ordinato)."""
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly(side="lay", price=2.2)])
    corpo = dict(db.vive()[0]["payload"])
    stake = corpo["size"]
    corpo["price_visto"] = 2.5
    corpo["price_visto_at"] = NOW.isoformat()
    monkeypatch.setattr(S, "_execute", lambda **kw: _Esito(
        status="open", price=kw["row"]["price"], size=kw["row"]["size"]))
    riga = _riga_feed(ou25_back=2.46, ou25_lay=2.5)
    out = S._request_place(db=db, market=None, rows_by_event={EV: riga},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("ok") is True, out
    assert db.trades[0]["price"] == 2.5
    assert db.trades[0]["size"] == stake, "lo stake NON cambia col prezzo"
    assert db.trades[0]["liability"] == round(stake * (2.5 - 1), 2)


def test_clic_troppo_vecchio_rifiutato_nessun_ordine(monkeypatch):
    """CRITERIO DI ACCETTAZIONE ESPLICITO."""
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("un clic troppo vecchio non deve arrivare a _execute")))
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()])
    corpo = dict(db.vive()[0]["payload"])
    corpo["price_visto"] = 2.2
    vecchio = NOW - timedelta(seconds=PO.CLICK_MAX_AGE_S + 1)
    corpo["price_visto_at"] = vecchio.isoformat()
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("error") == "clic_troppo_vecchio"
    assert db.trades == []


def test_clic_appena_dentro_la_soglia_passa(monkeypatch):
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()])
    corpo = dict(db.vive()[0]["payload"])
    corpo["price_visto"] = 2.2
    appena = NOW - timedelta(seconds=PO.CLICK_MAX_AGE_S - 1)
    corpo["price_visto_at"] = appena.isoformat()
    monkeypatch.setattr(S, "_execute", lambda **kw: _Esito(
        status="open", price=kw["row"]["price"], size=kw["row"]["size"]))
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("ok") is True, out


def test_prezzo_visto_fuori_tolleranza_rifiutato(monkeypatch):
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("prezzo visto fuori tolleranza non deve arrivare a _execute")))
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()])
    corpo = dict(db.vive()[0]["payload"])
    corpo["price_visto"] = 2.2
    corpo["price_visto_at"] = NOW.isoformat()
    # il mercato ORA e' molto lontano dal prezzo che l'utente diceva di vedere
    riga = _riga_feed(ou25_back=3.0, ou25_lay=3.05)
    out = S._request_place(db=db, market=None, rows_by_event={EV: riga},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("error") == "prezzo_visto_fuori_tolleranza"
    assert db.trades == []


def test_prezzo_visto_non_valido_rifiutato(monkeypatch):
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("un prezzo visto invalido non deve arrivare a _execute")))
    for sporco in (float("nan"), float("inf"), "2.3", 1.0, -5.0, True):
        db = DbFinto()
        _ciclo_anomalia(db, [_anomaly()])
        corpo = dict(db.vive()[0]["payload"])
        corpo["price_visto"] = sporco
        corpo["price_visto_at"] = NOW.isoformat()
        out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                               payload=corpo, params={"commission_pct": 5.0},
                               now=NOW, control_mode="paper")
        assert out.get("error") == "prezzo_visto_non_valido", f"sporco={sporco!r}"
        assert db.trades == []


def test_slippage_pct_dal_payload_allarga_o_stringe_la_tolleranza(monkeypatch):
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()])
    corpo = dict(db.vive()[0]["payload"])
    corpo["price_visto"] = 2.2
    corpo["price_visto_at"] = NOW.isoformat()
    corpo["slippage_pct"] = 10.0   # l'utente ha allargato la tolleranza a video
    monkeypatch.setattr(S, "_execute", lambda **kw: _Esito(
        status="open", price=kw["row"]["price"], size=kw["row"]["size"]))
    # scostamento ~4.5%: col default (2%) sarebbe rifiutato, con 10% no
    riga = _riga_feed(ou25_back=2.3, ou25_lay=2.34)
    out = S._request_place(db=db, market=None, rows_by_event={EV: riga},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("ok") is True, out


def test_senza_price_visto_funziona_come_il_giro_precedente(monkeypatch):
    """Prima della migrazione (o con un client vecchio) il payload non porta
    MAI ``price_visto``: comportamento IDENTICO al 3o giro."""
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly(price=2.2)])
    corpo = dict(db.vive()[0]["payload"])
    assert "price_visto" not in corpo
    monkeypatch.setattr(S, "_execute", lambda **kw: _Esito(
        status="open", price=kw["row"]["price"], size=kw["row"]["size"]))
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("ok") is True, out
    assert db.trades[0]["price"] == 2.2   # la fotografia congelata, invariata


def test_price_size_non_finiti_con_opp_key_rifiutati_ramo_mio():
    """Il nan-gap sul ramo CONDIVISO (righe ~2187-2192 di ``_request_place``)
    resta com'era; QUESTO controllo (righe subito dopo, con ``opp_key``) e'
    il permesso ottenuto dal coordinatore nel 3o giro: qui lo si verifica
    ancora valido nel 4o."""
    db = DbFinto()
    _ciclo_anomalia(db, [_anomaly()])
    corpo = dict(db.vive()[0]["payload"])
    corpo["price"] = float("nan")
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("error") == "price/size non finiti"
    assert db.trades == []


# ===========================================================================
# 8. COMBO — un prezzo VISTO per OGNI gamba
# ===========================================================================
def test_combo_un_prezzo_visto_per_ogni_gamba_usato_per_l_ordine(monkeypatch):
    """CRITERIO DI ACCETTAZIONE ESPLICITO."""
    db = DbFinto()
    _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    corpo = dict(db.vive()[0]["payload"])
    assert [l["price"] for l in corpo["legs"]] == [2.2, 1.9]
    corpo["legs_prices_visti"] = {"0": 2.25, "1": 1.92}
    corpo["price_visto_at"] = NOW.isoformat()
    visti: list[float] = []

    def esecuzione(**kw):
        visti.append(kw["row"]["price"])
        db.update_trade(kw["trade_id"], status="open", size_matched=kw["row"]["size"])
        return _Esito(status="open", price=kw["row"]["price"], size=kw["row"]["size"])

    monkeypatch.setattr(S, "_execute", esecuzione)
    riga = _riga_feed(ou25_back=2.25, ou25_lay=2.29, btts_back=1.92, btts_lay=1.96)
    out = S._request_place(db=db, market=None, rows_by_event={EV: riga},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("ok") is True, out
    assert sorted(visti) == [1.92, 2.25]
    assert sorted(t["price"] for t in db.trades) == [1.92, 2.25]


def test_combo_prezzi_visti_incompleti_rifiuta_l_intera_combo(monkeypatch):
    """CRITERIO DI ACCETTAZIONE ESPLICITO: se arriva ``legs_prices_visti`` ma
    manca una gamba, l'INSIEME e' incompleto -> rifiuto dichiarato, NESSUNA
    gamba (nemmeno quelle con un prezzo visto valido) viene piazzata."""
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("nessuna gamba deve arrivare a _execute")))
    db = DbFinto()
    _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    corpo = dict(db.vive()[0]["payload"])
    corpo["legs_prices_visti"] = {"0": 2.25}   # manca la gamba 1
    corpo["price_visto_at"] = NOW.isoformat()
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("error") == "combo_prezzi_visti_incompleti"
    assert db.trades == []


def test_combo_senza_legs_prices_visti_funziona_come_il_giro_precedente(monkeypatch):
    db = DbFinto()
    _ciclo_combo(db, [_combo()], params={"auto_trade_combos": True})
    corpo = dict(db.vive()[0]["payload"])
    assert "legs_prices_visti" not in corpo
    monkeypatch.setattr(S, "_execute", lambda **kw: _Esito(
        status="open", price=kw["row"]["price"], size=kw["row"]["size"]))
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("ok") is True, out
    assert sorted(t["price"] for t in db.trades) == [1.9, 2.2]   # fotografia, invariata


# ===========================================================================
# aiutanti
# ===========================================================================
class _Esito:
    def __init__(self, status="open", price=None, size=None, fill_note=None):
        self.status, self.price, self.size, self.fill_note = status, price, size, fill_note


def _skip_reasons(db, reason):
    return [p for k, p in db.attivita if k == "skip" and p.get("reason") == reason]
