# -*- coding: utf-8 -*-
"""REPERTO 17/09 sera (Pieczonka v Trungelliti, event_id 36077210): Safe ha DUE
motori sul tennis, e la Control Room ne confondeva uno con l'altro.

1. La Strategia S tennis (righe ``strategy='tennis'``): accesa SOLO da
   ``params.variants`` che contenga "tennis" (``bot_service.scan_and_place``,
   variabile ``variant``/``_modalita_di``).
2. Le "opportunita' di modello tennis" (righe ``strategy='model'``,
   ``meta.kind='tennis'``, prodotte da ``tennis_opportunity.py`` e piazzate da
   ``_auto_trade_opps``): accese da ``params.auto_trade_tennis``
   (``auto_trade_kinds={"tennis": bool(params.get("auto_trade_tennis")) ...}``
   dentro ``process_opportunities``).

``auto_trade_tennis`` compare SOLO alle righe che leggono/normalizzano il
parametro e nel punto che costruisce ``auto_trade_kinds``: NON governa la
Strategia S. La scheda "Solo tennis" della Control Room lo forzava a `true`
credendo servisse alle entrate della Strategia S: sul match il trader ha visto
3 righe (2 paper del modello + 1 live della Strategia S) e ha creduto a 3
ingressi separati sulla stessa strategia.

Questo file e' il test di CONTRATTO fra i due motori:
  (a) la Strategia S tennis piazza con ``auto_trade_tennis=False`` (prova che
      l'interruttore non la governa) — sia per ISPEZIONE del codice
      (``scan_and_place`` non nomina mai ``auto_trade_tennis``) sia FUNZIONALE
      (``scan_and_place`` piazza davvero una riga ``strategy='tennis'`` con
      quel parametro spento);
  (b) ``process_opportunities`` con ``auto_trade_kinds={'tennis': False}`` NON
      piazza righe del modello tennis, con ``True`` le piazza in modo
      ``modalita_di_strategia('model', ...)`` e SEMPRE con
      ``strategy='model'``/``meta.kind='tennis'``, mai ``strategy='tennis'``.

I finti hanno le stesse chiavi del vero (stesso schema di
``test_incidente_quote_2026_09_17.py``: ``rows``/``payload`` del feed unico,
segnali con le chiavi che ``bot_service._sig`` legge davvero).

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone

from Betfair.safe_strategy import bot_service as S

NOW = datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc)


# ===========================================================================
# finti comuni
# ===========================================================================
class DbFinto:
    """Le sole porte che ``scan_and_place``/``process_opportunities`` usano
    davvero in questo scenario (nessuna posizione viva, nessun aggregato)."""

    def __init__(self) -> None:
        self.attivita: list[tuple[str, dict]] = []
        self.opps: list = []
        self.trades: list[dict] = []
        self.richieste: list[dict] = []

    def log(self, kind, payload):
        self.attivita.append((kind, dict(payload)))

    def upsert_opportunities(self, righe):
        self.opps.extend(righe)

    def open_trades(self):
        return []

    def aggregates(self, mode=None):
        return {}

    def scanner_status(self):
        return None

    def insert_trade(self, row):
        tid = len(self.trades) + 1
        self.trades.append({**row, "id": tid})
        return tid

    def update_trade(self, *_a, **_k):
        pass

    # --- coda delle proposte (17/09): stesse chiavi di ``bot_db`` ---
    def proposte_opportunita(self, ore=24, limit=300):
        return [r for r in self.richieste
                if r.get("status") in ("proposed", "rejected")]

    def scrivi_proposta_opportunita(self, opp_key, payload, req_id=None):
        corpo = {**payload, "opp_key": str(opp_key)}
        if req_id is not None:
            for r in self.richieste:
                if r["id"] == int(req_id):
                    r["payload"] = corpo
            return int(req_id)
        rid = len(self.richieste) + 1
        self.richieste.append({"id": rid, "kind": "place", "status": "proposed",
                               "payload": corpo, "result": None})
        return rid

    def chiudi_proposta_opportunita(self, req_id, motivo):
        for r in self.richieste:
            if r["id"] == int(req_id) and r["status"] == "proposed":
                r["status"] = "rejected"
                r["result"] = {"decaduta": True, "motivo": str(motivo)[:200]}

    def marca_proposta_opportunita_annotata(self, req_id, result):
        for r in self.richieste:
            if r["id"] == int(req_id):
                r["result"] = {**(result or {}), "attivita_scritta": True}


class _EsitoFinto:
    """Sostituto di ``X.PlaceOutcome``: qui basta ``status`` ('open' = riuscito,
    la stessa condizione che ``scan_and_place``/``_auto_trade_opps`` guardano)."""

    def __init__(self, status: str = "open") -> None:
        self.status = status


def _righe_di(db, strategy: str) -> list[dict]:
    return [t for t in db.trades if t.get("strategy") == strategy]


# ===========================================================================
# (a) LA STRATEGIA S TENNIS NON E' GOVERNATA DA auto_trade_tennis
# ===========================================================================
def test_scan_and_place_non_nomina_auto_trade_tennis():
    """ISPEZIONE: il codice che piazza le 4 varianti del manuale (base, esatto,
    punta, tennis) non legge mai ``auto_trade_tennis`` — quel parametro vive
    solo nel motore delle opportunita' di modello."""
    src = inspect.getsource(S.scan_and_place)
    assert "auto_trade_tennis" not in src


class _EngineFinto:
    """Un segnale unico, variante 'tennis' (Strategia S), come lo emette il
    motore vero (chiavi che ``bot_service._sig`` legge: key/event_id/variant/
    side/market_id/selection_id/price/size)."""

    def __init__(self, segnale: dict) -> None:
        self._segnale = segnale

    def evaluate(self, rows):
        return [self._segnale]


def _segnale_tennis(event_id: str) -> dict:
    return {
        "key": f"{event_id}:tennis:leader_lay", "event_id": event_id,
        "variant": "tennis", "sport": "tennis", "side": "lay",
        "market_id": "1.900", "market_type": "MATCH_ODDS", "selection_id": 11,
        "selection_name": "Leader", "price": 1.32, "size": 3.0,
        "event_name": "Pieczonka v Trungelliti", "minute": None, "score": None,
        "headline": "test", "checks": {}, "first_seen_ts": NOW.timestamp(),
        "size_available": 500.0,
    }


def _riga_feed_tennis(event_id: str) -> dict:
    return {
        "event_id": event_id, "sport": "tennis", "updated_at": NOW.isoformat(),
        "payload": {
            "event_name": "Pieczonka v Trungelliti", "inplay": True,
            "odds": {
                "p1": {"selection_id": 11, "back": 1.30, "lay": 1.32,
                       "back_size": 500.0, "lay_size": 500.0},
                "p2": {"selection_id": 22, "back": 4.00, "lay": 4.40,
                       "back_size": 200.0, "lay_size": 200.0},
            },
        },
    }


def test_strategia_s_tennis_piazza_con_auto_trade_tennis_spento(monkeypatch):
    """FUNZIONALE: ``auto_trade_tennis=False`` e ``variants=['tennis']`` — la
    Strategia S tennis piazza LO STESSO. Se l'interruttore la governasse
    davvero, questo test dovrebbe restare a zero piazzamenti."""
    monkeypatch.setattr(S, "_execute", lambda **kw: _EsitoFinto("open"))
    db = DbFinto()
    event_id = "36077210-a"
    engine = _EngineFinto(_segnale_tennis(event_id))
    rows = [_riga_feed_tennis(event_id)]
    params = {"variants": ["tennis"], "auto_trade_tennis": False,
              "max_open_trades": 0, "max_liability_per_trade": 0.0,
              "min_size_available_factor": 0.0, "commission_pct": 5.0,
              "max_spread_ratio": 1.6}
    piazzati, segnali = S.scan_and_place(
        db=db, market=None, engine=engine, rows=rows, params=params,
        mode="paper", now=NOW, scanner_ts=NOW.timestamp(), scanner_ts_known=True)
    assert segnali == 1
    assert piazzati == 1, "auto_trade_tennis=False ha bloccato la Strategia S: NON dovrebbe"
    righe = _righe_di(db, "tennis")
    assert len(righe) == 1
    assert righe[0]["mode"] == "paper"


# ===========================================================================
# (b) LE OPPORTUNITA' DI MODELLO TENNIS: strategy='model', meta.kind='tennis',
#     SEMPRE governate da auto_trade_tennis (via auto_trade_kinds)
# ===========================================================================
class _TennisModelFinto:
    def __init__(self, opps: list[dict]) -> None:
        self._opps = opps

    def evaluate(self, payload, now_ts):
        return list(self._opps)


class _ModuloTennisFinto:
    def __init__(self, modello) -> None:
        self._m = modello

    def TennisOpportunityModel(self, params):  # noqa: N802 - nome del vero
        return self._m


def _opp_modello_tennis() -> dict:
    return {"market_type": "MATCH_ODDS", "market_id": "1.900", "selection_id": 11,
            "selection_name": "Leader", "side": "back", "price": 1.30,
            "size_available": 500.0, "confidence": 1.0, "edge": 1.0,
            "p_model": 0.7, "p_implied": 0.5, "ev": 0.15, "rationale": "test"}


def _riga_opp_tennis(event_id: str) -> dict:
    return {"event_id": event_id, "sport": "tennis",
            "payload": {"event_name": "Pieczonka v Trungelliti", "inplay": True,
                        "odds": {"p1": {"selection_id": 11, "back": 1.30, "lay": 1.32,
                                        "back_size": 500.0, "lay_size": 500.0},
                                 "p2": {"selection_id": 22, "back": 4.00, "lay": 4.40,
                                        "back_size": 200.0, "lay_size": 200.0}},
                        "sets": {"p1": 1, "p2": 0}, "games": {"p1": 4, "p2": 2}}}


def _rows_by_event_di(event_id: str) -> dict:
    riga = _riga_opp_tennis(event_id)
    return {event_id: {**riga, "updated_at": NOW.isoformat()}}


def _esegui_opps(db, event_id: str, kinds: dict, mode: str = "paper"):
    modello = _TennisModelFinto([_opp_modello_tennis()])
    return S.process_opportunities(
        db=db, market=None, rows=[_riga_opp_tennis(event_id)],
        params={"opps_interval_s": 0.0}, model=None, opp_mod=None, mode=mode,
        now=NOW, state={"last_ts": 0.0, "hashes": {}},
        rows_by_event=_rows_by_event_di(event_id),
        auto_trade_kinds=kinds,
        extra={"anomaly": None, "combos": None,
               "tennis": _ModuloTennisFinto(modello)},
        scanner_ts=NOW.timestamp(), scanner_ts_known=True)


def test_auto_trade_kinds_tennis_false_non_piazza_righe_modello(monkeypatch):
    monkeypatch.setattr(S, "_execute", lambda **kw: _EsitoFinto("open"))
    db = DbFinto()
    out = _esegui_opps(db, "36077210-b", {"tennis": False})
    assert out["traded"] == 0
    assert db.trades == [], "kinds['tennis']=False ma il modello ha piazzato lo stesso"


def test_auto_trade_kinds_tennis_true_non_piazza_piu_ma_propone(monkeypatch):
    """17/09, ORDINE DELL'UTENTE — con ``auto_trade_tennis`` ACCESO il motore
    del modello tennis non manda piu' ordini: scrive una PROPOSTA.

    Prima questo test pretendeva la riga a mercato (``traded == 1``); il
    reperto della sera del 17/09 (tre righe su una partita, due del modello in
    paper) ha portato all'ordine: le opportunita' di modello si piazzano SOLO
    dalla scheda. Il contratto sul contenuto resta identico
    (``strategy='model'``, ``kind='tennis'``, modalita' da
    ``modalita_di_strategia``), ma su una PROPOSTA."""
    monkeypatch.setattr(S, "_execute", lambda **kw: _EsitoFinto("open"))
    db = DbFinto()
    out = _esegui_opps(db, "36077210-c", {"tennis": True}, mode="paper")
    assert out["traded"] == 0
    assert db.trades == [], "l'interruttore ha piazzato da solo: NON deve piu'"
    assert out["proposte"] == 1
    assert len(db.richieste) == 1
    riga = db.richieste[0]
    assert riga["kind"] == "place" and riga["status"] == "proposed"
    corpo = riga["payload"]
    # (b) — contratto: MAI strategy='tennis' per un'opportunita' del modello
    assert corpo["strategy"] == "model"
    assert corpo["kind"] == "tennis"
    assert corpo["opp_key"] == "36077210-c|tennis:MATCH_ODDS:11:back"
    # modo = quello che modalita_di_strategia('model', mode, params) avrebbe
    # dato (servizio paper -> tetto paper, qualunque sia strategy_modes)
    assert corpo["mode"] == S.modalita_di_strategia("model", "paper", {"opps_interval_s": 0.0})
    assert corpo["mode"] == "paper"
    # l'attivita' porta il `mode` della PROPOSTA, non quello del servizio
    kinds = [k for k, _ in db.attivita]
    assert "proposta_opportunita" in kinds
    riga_att = [p for k, p in db.attivita if k == "proposta_opportunita"][0]
    assert riga_att["mode"] == "paper"


def test_modalita_di_strategia_model_e_paper_oggi():
    """D (referto): oggi ``strategy_modes`` non ha 'model' in live da nessuna
    parte del bot -> il servizio in LIVE senza la voce scritta resta paper
    (regola 'i soldi veri si raggiungono solo scrivendolo')."""
    assert S.modalita_di_strategia("model", "live", {}) == "paper"
    assert S.modalita_di_strategia(
        "model", "live", {"strategy_modes": {"model": "live"}}) == "live"


# ===========================================================================
# FALSIFICAZIONE
# ===========================================================================
def test_falsificazione_se_auto_trade_tennis_governasse_la_strategia_s(monkeypatch):
    """Se qualcuno aggiungesse per errore un gate ``auto_trade_tennis`` dentro
    ``scan_and_place`` (il difetto che l'utente teme), questo test lo denuncia:
    simuliamo il gate SBAGLIATO e verifichiamo che azzererebbe i piazzamenti —
    la prova che il test sopra falsifica davvero, non e' un test cieco."""
    monkeypatch.setattr(S, "_execute", lambda **kw: _EsitoFinto("open"))
    db = DbFinto()
    event_id = "36077210-falsi"
    engine = _EngineFinto(_segnale_tennis(event_id))
    rows = [_riga_feed_tennis(event_id)]
    params = {"variants": ["tennis"], "auto_trade_tennis": False,
              "max_open_trades": 0, "max_liability_per_trade": 0.0,
              "min_size_available_factor": 0.0, "commission_pct": 5.0,
              "max_spread_ratio": 1.6}

    vero_sig = S._sig

    def sig_col_gate_sbagliato(signal, name, default=None):
        # il gate SBAGLIATO che il reperto teme: 'tennis' bloccata da
        # auto_trade_tennis anche nella Strategia S.
        if name == "variant" and not params.get("auto_trade_tennis"):
            return "__mai__"
        return vero_sig(signal, name, default)

    monkeypatch.setattr(S, "_sig", sig_col_gate_sbagliato)
    piazzati, segnali = S.scan_and_place(
        db=db, market=None, engine=engine, rows=rows, params=params,
        mode="paper", now=NOW, scanner_ts=NOW.timestamp(), scanner_ts_known=True)
    assert piazzati == 0, "il gate sbagliato avrebbe dovuto azzerare i piazzamenti"
