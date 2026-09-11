"""CERTIFICAZIONE della sezione SAFE STRATEGY (11/09/2026 sera) - lato servizio.

Questi test difendono il CONTRATTO che la UI legge: se il servizio cambia il
nome, il tipo o la forma di una chiave, qui diventa rosso prima che il trader
veda un numero sbagliato. Nessuna rete, nessun Supabase. File ASCII-only.

Copertura:
  - `payload.kinds` delle opportunita': SEMPRE le stesse quattro chiavi, su
    calcio E tennis (prima le righe tennis non la scrivevano e la riga calcio
    non aveva `tennis`: conteggi non confrontabili tra sport).
  - `control.stats.feed_blind` e' un CONTATORE intero (il tipo TS diceva
    boolean): quante posizioni vive sono cieche in questo ciclo.
  - `control.stats` contiene TUTTE le chiavi che la UI legge, coi tipi giusti.
  - soglie di freschezza del feed condivise fra servizio e UI.
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import exits as XE
from Betfair.safe_strategy.tests.test_bot_service import (
    NOW, FakeDB, FakeMarket, FakeModel, FAKE_OPP_MOD, _feed_row, _opp,
    _reset_module_state,
)


@pytest.fixture(autouse=True)
def _clean_module_state():
    _reset_module_state()
    yield
    _reset_module_state()


def _run(db, market=None, **kw):
    return S.run_once(db=db, market=market or FakeMarket(), now=NOW, **kw)


# ---------------------------------------------------------------------------
# payload.kinds - contratto UNIFORME fra sport
# ---------------------------------------------------------------------------
_KINDS_KEYS = {"model", "anomaly", "combo", "tennis"}


def _tennis_feed_row(event_id="2.1"):
    return {"event_id": event_id, "sport": "tennis", "updated_at": NOW.isoformat(),
            "payload": {"event_name": "Rossi v Bianchi", "inplay": True,
                        "sets": {"p1": 1, "p2": 0}, "games": {"p1": 3, "p2": 1},
                        "odds": {"p1": {"selection_id": 1, "back": 1.05, "lay": 1.07,
                                        "back_size": 400.0, "lay_size": 300.0},
                                 "p2": {"selection_id": 2, "back": 20.0, "lay": 24.0}}}}


class _FakeTennisMod:
    """modulo tennis_opportunity finto: `TennisOpportunityModel(params)`."""

    def __init__(self, opps):
        self._opps = list(opps)

    def TennisOpportunityModel(self, params):  # noqa: N802 - imita il modulo vero
        opps = self._opps

        class _M:
            def evaluate(self, payload, now_ts):
                return list(opps)

        return _M()


def _tennis_opp():
    return {"market_type": "MATCH_ODDS", "market_name": "1X2", "line": None,
            "market_id": "t1", "selection_id": 1, "selection_name": "Rossi",
            "side": "back", "price": 1.05, "size_available": 400.0,
            "p_model": 0.96, "p_implied": 0.95, "edge": 0.02, "ev": 0.01,
            "confidence": 0.8, "rationale": "set + 2 game"}


def test_kinds_calcio_ha_le_quattro_chiavi():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row()]
    _run(db, engine=None, opp_model=FakeModel([_opp()]), opp_mod=FAKE_OPP_MOD,
         opps_state={"last_ts": 0.0, "hashes": {}})
    body = db.opportunities[0][0]["payload"]
    assert set(body["kinds"]) == _KINDS_KEYS, "la riga calcio deve dichiarare anche tennis=0"
    assert body["kinds"]["model"] == 1
    assert body["kinds"]["tennis"] == 0
    assert all(isinstance(v, int) for v in body["kinds"].values())


def test_kinds_tennis_ha_le_quattro_chiavi():
    db = FakeDB(status="stopped")
    db.scan_rows = [_tennis_feed_row()]
    _run(db, engine=None, opp_model=None, opp_mod=None,
         extra_mods={"tennis": _FakeTennisMod([_tennis_opp()])},
         opps_state={"last_ts": 0.0, "hashes": {}})
    assert db.opportunities, "la riga tennis deve essere scritta"
    body = db.opportunities[0][0]["payload"]
    assert set(body["kinds"]) == _KINDS_KEYS, "prima le righe tennis non scrivevano kinds"
    assert body["kinds"]["tennis"] == 1
    assert body["kinds"]["model"] == 0


def test_kinds_confrontabili_fra_i_due_sport():
    """Le due righe hanno la STESSA forma: la UI puo' sommarle senza casi speciali."""
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row(), _tennis_feed_row()]
    _run(db, engine=None, opp_model=FakeModel([_opp()]), opp_mod=FAKE_OPP_MOD,
         extra_mods={"tennis": _FakeTennisMod([_tennis_opp()])},
         opps_state={"last_ts": 0.0, "hashes": {}})
    bodies = [r["payload"] for batch in db.opportunities for r in batch]
    assert len(bodies) == 2, "una riga per sport"
    for b in bodies:
        assert set(b["kinds"]) == _KINDS_KEYS
    totale = {k: sum(b["kinds"][k] for b in bodies) for k in _KINDS_KEYS}
    assert totale == {"model": 1, "anomaly": 0, "combo": 0, "tennis": 1}


# ---------------------------------------------------------------------------
# control.stats - il contratto che la UI legge
# ---------------------------------------------------------------------------
def test_feed_blind_e_un_contatore_non_un_flag():
    """Posizione viva su un evento SPARITO dal feed: `feed_blind` = quante."""
    db = FakeDB(status="running")
    db.scan_rows = [_feed_row()]                      # evento 1.1 nel feed
    # entrata IN-PLAY (minute_at_entry): una posizione pre-KO senza riga e'
    # legittima e non va contata come cieca (M2)
    db.insert_trade({"event_id": "9.9", "market_id": "m1", "selection_id": 7,
                     "side": "lay", "size": 10.0, "price": 6.0, "status": "open",
                     "commission": 0.05, "mode": "paper", "minute_at_entry": 55,
                     "meta": {}})
    _run(db)
    stats = db.control["stats"]
    assert isinstance(stats["feed_blind"], int) and not isinstance(stats["feed_blind"], bool)
    assert stats["feed_blind"] >= 1, "la posizione su 9.9 e' cieca: va contata"


def test_feed_blind_zero_quando_tutte_le_posizioni_sono_viste():
    db = FakeDB(status="running")
    db.scan_rows = [_feed_row()]
    db.insert_trade({"event_id": "1.1", "market_id": "m1", "selection_id": 7,
                     "side": "lay", "size": 10.0, "price": 6.0, "status": "open",
                     "commission": 0.05, "mode": "paper", "minute_at_entry": 55,
                     "meta": {}})
    _run(db)
    assert db.control["stats"]["feed_blind"] == 0


def test_stats_pubblica_tutte_le_chiavi_lette_dalla_ui():
    """Ogni chiave di `SafeStats`/`SafeRiskStats`/`SafeOppCounts` (lib/safeBot.ts)."""
    db = FakeDB(status="running")
    db.scan_rows = [_feed_row()]
    _run(db)
    stats = db.control["stats"]
    attese = {
        "events_total": int, "signals_active": int, "trades_open": int,
        "open_liability": float, "reconciling_liability": float,
        "realized_today": float, "realized_total": float,
        "won_today": int, "lost_today": int, "legs_today": int, "events_today": int,
        "feed_blind": int, "last_cycle": str,
    }
    for chiave, tipo in attese.items():
        assert chiave in stats, f"la UI legge stats.{chiave}: il servizio deve scriverla"
        assert isinstance(stats[chiave], tipo), f"stats.{chiave}: atteso {tipo.__name__}"
    for chiave in ("daily_liability", "daily_cap", "reconciling_liability",
                   "loss_stop_active", "daily_loss_stop"):
        assert chiave in stats["risk"], f"la UI legge stats.risk.{chiave}"
    assert isinstance(stats["risk"]["loss_stop_active"], bool)
    assert set(stats["opps"]) == _KINDS_KEYS
    assert "params_effective" in stats


def test_params_effective_ha_le_chiavi_della_scheda_parametri():
    """H-15: la UI confronta il form coi valori REALMENTE in uso."""
    db = FakeDB(status="running")
    db.scan_rows = [_feed_row()]
    _run(db)
    pe = db.control["stats"]["params_effective"]
    for chiave in ("poll_interval_s", "commission_pct", "max_open_trades",
                   "max_liability_per_trade", "min_size_available_factor",
                   "min_stake", "max_spread_ratio", "place_max_attempts",
                   "opps_min_confidence", "opps_min_edge", "paper_fill_ttl_s",
                   "live_fill_deadline_s", "variants", "exits", "risk"):
        assert chiave in pe, f"BotParamsSheet legge params_effective.{chiave}"
    assert isinstance(pe["variants"], list) and pe["variants"], "variants mai vuoto"


# ---------------------------------------------------------------------------
# freschezza del feed - le soglie sono UNA sola coppia di numeri
# ---------------------------------------------------------------------------
def test_soglie_freschezza_del_servizio_sono_quelle_della_ui():
    """La UI spegne le azioni con le STESSE soglie del servizio. Se questi due
    numeri cambiano, vanno cambiati anche in frontend/src/lib/safeBot.ts
    (FEED_ROW_STALE_MS / FEED_HARD_MAX_MS) - c'e' un test gemello in vitest."""
    assert XE.FEED_FRESH_S == 20.0, "= FEED_ROW_STALE_MS (20_000 ms) nella UI"
    assert XE.FEED_HARD_MAX_S == 120.0, "= FEED_HARD_MAX_MS (120_000 ms) nella UI"


def test_tetto_duro_vince_sullo_heartbeat_dello_scanner():
    """M-24: riga oltre il tetto duro = inutilizzabile anche con lo scanner vivo.
    E' la regola che la UI deve rispecchiare per non mostrare un prezzo finto."""
    now_ts = 1_000_000.0
    riga_vecchia = {"updated_at": now_ts - 300.0}          # 5 minuti
    riga_fresca = {"updated_at": now_ts - 5.0}
    scanner_vivo = now_ts - 1.0
    assert XE.feed_is_fresh(riga_fresca, now_ts, scanner_vivo) is True
    assert XE.feed_is_fresh(riga_vecchia, now_ts, scanner_vivo) is False
    # dentro il tetto ma oltre i 20 s: lo heartbeat vivo la salva (write-on-change)
    riga_media = {"updated_at": now_ts - 60.0}
    assert XE.feed_is_fresh(riga_media, now_ts, scanner_vivo) is True
    assert XE.feed_is_fresh(riga_media, now_ts, None) is False


# ---------------------------------------------------------------------------
# "Investi" dalle OPPORTUNITA': il tipo dell'operazione deve sopravvivere
# ---------------------------------------------------------------------------
def _place_req(db, payload):
    db.requests.append({"id": len(db.requests) + 1, "kind": "place",
                        "status": "pending", "payload": payload})


def _opp_payload(**kw):
    base = {"event_id": "1.1", "market_id": "m1", "market_type": "MATCH_ODDS",
            "selection_id": 7, "side": "back", "price": 3.0, "size": 5.0,
            "strategy": "model", "kind": "model",
            "idempotency_key": "opp:1.1:m1:7:back"}
    base.update(kw)
    return base


def test_investi_da_opportunita_conserva_strategia_e_tipo():
    """La tabella mostra il badge del tipo solo con strategy='model' +
    meta.kind: prima l'handler li scartava e la riga diceva "MANUALE"."""
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row()]
    _place_req(db, _opp_payload())
    _run(db)
    t = db.trades[0]
    assert t["strategy"] == "model", "il badge del tipo dipende da strategy='model'"
    assert t["origin"] == "manual", "resta un'operazione MANUALE (icona mano)"
    assert t["meta"]["kind"] == "model"
    assert t["meta"]["manual"] is True


def test_investi_da_anomalia_conserva_la_regola():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row()]
    _place_req(db, _opp_payload(kind="anomaly", rule="ou_ladder"))
    _run(db)
    meta = db.trades[0]["meta"]
    assert meta["kind"] == "anomaly" and meta["rule"] == "ou_ladder"


def test_investi_da_combinazione_conserva_le_coordinate_della_gamba():
    """Le gambe di una combo devono restare riconoscibili come UNA operazione."""
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row()]
    for i in (1, 2):
        _place_req(db, _opp_payload(
            kind="combo", combo="ou_stack", combo_leg=i, combo_legs=2,
            combo_total_stake=10.0, idempotency_key=f"combo:1.1:abc123:{i}/2"))
    _run(db)
    assert len(db.trades) == 2
    for i, t in enumerate(db.trades, start=1):
        m = t["meta"]
        assert m["kind"] == "combo" and m["combo"] == "ou_stack"
        assert m["combo_leg"] == i and m["combo_legs"] == 2
        assert m["combo_total_stake"] == 10.0
        assert m["idempotency_key"] == f"combo:1.1:abc123:{i}/2"


def test_investi_da_tennis_conserva_il_tipo():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row()]
    _place_req(db, _opp_payload(kind="tennis", sport="tennis"))
    _run(db)
    assert db.trades[0]["meta"]["kind"] == "tennis"
    assert db.trades[0]["sport"] == "tennis"


def test_place_manuale_semplice_resta_manuale():
    """Piazzamento dal SEGNALE (nessuna strategia nel payload): strategy='manual',
    nessun kind inventato."""
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row()]
    _place_req(db, {"event_id": "1.1", "market_id": "m1", "market_type": "MATCH_ODDS",
                    "selection_id": 7, "side": "back", "price": 3.0, "size": 5.0})
    _run(db)
    t = db.trades[0]
    assert t["strategy"] == "manual" and "kind" not in (t["meta"] or {})


def test_il_client_non_puo_inventare_una_strategia():
    """Mai fidarsi del client su una riga che muove soldi: valori fuori
    vocabolario vengono normalizzati, non accettati."""
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row()]
    _place_req(db, _opp_payload(strategy="esatto", kind="model"))
    _run(db)
    t = db.trades[0]
    assert t["strategy"] == "manual", "strategia fuori vocabolario -> manual"
    assert "kind" not in (t["meta"] or {}), "senza strategy='model' nessun kind"


def test_kind_fuori_vocabolario_ignorato():
    db = FakeDB(status="stopped")
    db.scan_rows = [_feed_row()]
    _place_req(db, _opp_payload(kind="qualcosa_di_nuovo"))
    _run(db)
    assert "kind" not in (db.trades[0]["meta"] or {})
