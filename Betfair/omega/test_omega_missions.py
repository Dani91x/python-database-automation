"""Test MISSIONI — centro di controllo per partita (2026-07-15).

Copre: fase partita (status/minuto/kickoff), regola linea scalp, scelta runner
Under PER NOME, suggerimenti per gamba (HT in pre/1T, FT all'intervallo, mai
riproporre gambe fatte), auto-chiusura, guardia del loop automatico (fail-safe),
phase sui trade manuali. Riusa i fake di test_omega_service.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace as NS

from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as M
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_service import (
    NOW, FakeDB, FakeMarket, _closed_snapshot, _control, _cs, _event, _manual_req,
    _open_snapshot,
)


class _Snap:
    """ScoreSnapshot minimale per i test (duck-typed)."""

    def __init__(self, minute=None, home=None, away=None, status=None):
        self.minute = minute
        self.score_home = home
        self.score_away = away
        self.status = status


def _mission(eid="1.100", phase="pre", **over):
    m = {"event_id": eid, "event_name": "Home v Away", "kickoff": NOW.isoformat(),
         "mission_date": "2026-07-12", "target": 5.0, "status": "active",
         "phase_now": phase, "minute": None, "score_home": None, "score_away": None,
         "score_status": None, "suggestion_ht": None, "suggestion_ft": None,
         "suggestion_scalp": None}
    m.update(over)
    return m


# ---------------------------------------------------------------------------
# Funzioni pure
# ---------------------------------------------------------------------------
def test_mission_phase_da_status_provider():
    k = NOW
    # ordine dei check: FirstHalfEnd (intervallo) NON deve matchare FirstHalf
    assert E.mission_phase(status="FirstHalfEnd", minute=45, kickoff=k, now=NOW) == "ht"
    assert E.mission_phase(status="HalfTime", minute=45, kickoff=k, now=NOW) == "ht"
    assert E.mission_phase(status="FirstHalf", minute=30, kickoff=k, now=NOW) == "1t"
    assert E.mission_phase(status="KickOff", minute=0, kickoff=k, now=NOW) == "1t"
    assert E.mission_phase(status="SecondHalfKickOff", minute=46, kickoff=k, now=NOW) == "2t"
    assert E.mission_phase(status="Finished", minute=90, kickoff=k, now=NOW) == "finita"


def test_mission_phase_fallback_minuto_kickoff_prev():
    assert E.mission_phase(status=None, minute=30, kickoff=None, now=NOW) == "1t"
    assert E.mission_phase(status=None, minute=70, kickoff=None, now=NOW) == "2t"
    # kickoff futuro → pre
    assert E.mission_phase(status=None, minute=None,
                           kickoff=NOW + timedelta(hours=2), now=NOW) == "pre"
    # kickoff passato >3h senza dati → finita (difensivo)
    assert E.mission_phase(status=None, minute=None,
                           kickoff=NOW - timedelta(hours=4), now=NOW) == "finita"
    # buco dati: mantiene la fase precedente, mai retrocedere a caso
    assert E.mission_phase(status=None, minute=None,
                           kickoff=NOW - timedelta(minutes=50), now=NOW, prev="1t") == "1t"


def test_scalp_market_types_regola_linea():
    assert E.scalp_market_types(0) == ["OVER_UNDER_25", "OVER_UNDER_35"]
    # esempio utente: 1-0 (1 gol) al 51' → Under 3.5
    assert E.scalp_market_types(1) == ["OVER_UNDER_35", "OVER_UNDER_45"]
    assert E.scalp_market_types(6) == ["OVER_UNDER_85"]
    assert E.scalp_market_types(9) == []


def test_pick_under_runner_per_nome_mai_posizione():
    # Over PRIMA nella lista: un match posizionale punterebbe l'Over → soldi persi
    rs = [NS(selection_id=2, name="Over 3.5 Goals", back_price=1.9),
          NS(selection_id=1, name="Under 3.5 Goals", back_price=1.36)]
    assert E.pick_under_runner(rs).selection_id == 1
    assert E.pick_under_runner([NS(selection_id=2, name="Over 3.5 Goals")]) is None


# ---------------------------------------------------------------------------
# Processor end-to-end (fake market/db)
# ---------------------------------------------------------------------------
def test_mission_pre_propone_gamba_ht_e_blocca_ft():
    db = FakeDB(_control(status="idle"))
    db.missions = [_mission(kickoff=(NOW + timedelta(hours=1)).isoformat())]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {}
    S.process_missions(market=market, db=db, now=NOW)
    m = db.missions[0]
    assert m["phase_now"] == "pre"
    assert m["suggestion_ht"] is not None
    assert m["suggestion_ht"]["market_type"] == "HALF_TIME_SCORE"
    assert m["suggestion_ht"]["market_id"] == "m-1.100-HALF_TIME_SCORE"
    assert m["suggestion_ht"]["runner_name"] == "3 - 2"      # quota lay piu' alta
    assert m["suggestion_ft"] is None                         # 2T bloccata fino a intervallo


def test_mission_intervallo_propone_ft_e_chiude_ht():
    db = FakeDB(_control(status="idle"))
    db.missions = [_mission(phase="1t", suggestion_ht={"market_id": "x"})]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=45, home=1, away=0, status="HalfTime")}
    S.process_missions(market=market, db=db, now=NOW)
    m = db.missions[0]
    assert m["phase_now"] == "ht"
    assert m["score_home"] == 1 and m["score_away"] == 0 and m["minute"] == 45
    assert m["suggestion_ft"] is not None
    assert m["suggestion_ft"]["market_type"] == "CORRECT_SCORE"
    assert m["suggestion_ht"] is None             # finestra 1T chiusa all'intervallo


def test_mission_gamba_gia_piazzata_non_riproposta():
    db = FakeDB(_control(status="idle"))
    db.missions = [_mission(phase="ht")]
    db.trades.append({"id": 5, "event_id": "1.100", "phase": "ft_cs", "status": "open",
                      "pnl": 0, "liability": 100, "selection_id": 4, "price": 110,
                      "size": 1, "side": "lay"})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=46, home=1, away=0, status="HalfTime")}
    S.process_missions(market=market, db=db, now=NOW)
    assert db.missions[0]["suggestion_ft"] is None    # mai riproporre una gamba fatta


def test_mission_scalp_suggerimento_under_per_nome():
    db = FakeDB(_control(status="idle"))
    db.missions = [_mission(phase="2t")]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=51, home=1, away=0, status="SecondHalf")}
    ou = M.CorrectScoreMarket(market_id="m-ou35", event_id="1.100",
                              event_name="Home v Away", market_start_time=None,
                              runner_names={7: "Under 3.5 Goals", 8: "Over 3.5 Goals"})
    cs_ft = M.CorrectScoreMarket(market_id="m-1.100-CORRECT_SCORE", event_id="1.100",
                                 event_name="Home v Away", market_start_time=None,
                                 runner_names={1: "0 - 0", 3: "2 - 1", 4: "3 - 2"})
    market.markets_by_type = {
        ("1.100", "CORRECT_SCORE"): cs_ft,
        ("1.100", "OVER_UNDER_35"): ou,
    }
    market.books = {"m-ou35": {"market_id": "m-ou35", "status": "OPEN", "inplay": True,
                    "runners": [
                        # Over PRIMA: la scelta posizionale punterebbe l'Over
                        {"selection_id": 8, "name": "Over 3.5 Goals", "status": "ACTIVE",
                         "lay_price": 2.1, "lay_size": 50,
                         "back_price": 2.08, "back_size": 40},
                        {"selection_id": 7, "name": "Under 3.5 Goals", "status": "ACTIVE",
                         "lay_price": 1.37, "lay_size": 900,
                         "back_price": 1.36, "back_size": 800},
                    ]}}
    S.process_missions(market=market, db=db, now=NOW)
    sc = db.missions[0]["suggestion_scalp"]
    assert sc is not None
    assert sc["market_type"] == "OVER_UNDER_35"       # 1 gol → linea gol+2.5
    assert sc["selection_id"] == 7                     # Under scelto PER NOME
    assert sc["runner_name"].startswith("Under 3.5")
    assert sc["back_price"] == 1.36


def test_mission_finita_si_autochiude_senza_trade_vivi():
    db = FakeDB(_control(status="idle"))
    db.missions = [_mission(phase="2t")]
    db.trades.append({"id": 6, "event_id": "1.100", "phase": "ft_cs", "status": "won",
                      "pnl": 0.95, "liability": 0, "selection_id": 4, "price": 110,
                      "size": 1, "side": "lay"})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=90, home=1, away=0, status="Finished")}
    S.process_missions(market=market, db=db, now=NOW)
    assert db.missions[0]["phase_now"] == "finita"
    assert db.missions[0]["status"] == "closed"


def test_mission_finita_resta_aperta_con_trade_vivo():
    db = FakeDB(_control(status="idle"))
    db.missions = [_mission(phase="2t")]
    db.trades.append({"id": 7, "event_id": "1.100", "phase": "ft_cs", "status": "open",
                      "pnl": 0, "liability": 100, "selection_id": 4, "price": 110,
                      "size": 1, "side": "lay"})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=90, home=1, away=0, status="Finished")}
    S.process_missions(market=market, db=db, now=NOW)
    assert db.missions[0]["status"] == "active"       # chiude solo a trade regolati


def test_guardia_auto_non_piazza_su_evento_con_missione():
    db = FakeDB(_control())                           # automatico RUNNING
    db.missions = [_mission()]                        # missione attiva su 1.100
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {}
    res = S.run_once(market=market, db=db, now=NOW)
    auto_trades = [t for t in db.trades if t.get("origin") == "auto"]
    assert res.get("placed", 0) == 0 and not auto_trades   # territorio dell'utente


def test_guardia_fail_safe_se_lettura_missioni_fallisce():
    db = FakeDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {}

    def boom():
        raise RuntimeError("db down")

    db.mission_event_ids = boom
    res = S.run_once(market=market, db=db, now=NOW)
    assert res.get("skipped") == "mission_ids_failed"
    assert len([t for t in db.trades if t.get("origin") == "auto"]) == 0


def test_manual_place_con_phase_etichetta_il_trade():
    db = FakeDB(_control(status="idle"))
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "paper",
                                  "price": 110, "size": 1, "phase": "ht_cs"})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert db.trades[0]["phase"] == "ht_cs"
    assert db.trades[0]["origin"] == "manual"


def test_manual_place_phase_non_valida_rifiutata():
    db = FakeDB(_control(status="idle"))
    db.manual_reqs = _manual_req({"event_id": "1.100", "market_id": "m-1.100",
                                  "selection_id": 4, "side": "lay", "mode": "paper",
                                  "price": 110, "size": 1, "phase": "hack"})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(db.trades) == 0
    assert db.manual_reqs[0]["status"] == "error"


def test_mission_ft_esclude_punteggi_irraggiungibili():
    # HT 2-1: "0 - 0" e "2 - 1"... no: 2-1 e' il corrente (raggiungibile);
    # irraggiungibili sono h<2 o a<1 (es. "0 - 0" e "1 - 0"): il meno probabile
    # tra i RAGGIUNGIBILI e' "3 - 2" anche se "0 - 0" avesse quota piu' alta stantia.
    db = FakeDB(_control(status="idle"))
    db.missions = [_mission(phase="ht")]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=46, home=2, away=1, status="HalfTime")}
    cs_ft = M.CorrectScoreMarket(market_id="m-ft", event_id="1.100",
                                 event_name="Home v Away", market_start_time=None,
                                 runner_names={1: "0 - 0", 2: "1 - 0", 3: "2 - 1", 4: "3 - 2"})
    market.markets_by_type = {("1.100", "CORRECT_SCORE"): cs_ft,
                              ("1.100", "HALF_TIME_SCORE"): None,
                              ("1.100", "OVER_UNDER_35"): None,
                              ("1.100", "OVER_UNDER_45"): None}

    class _SnapMkt:
        status = "OPEN"; inplay = True; closed = False
        winner_selection_id = None; voided = False
        runners = [
            # book stantio: "0 - 0" mostra ancora lay 500 con liquidita' — IRRAGGIUNGIBILE
            E.ScoreRunner(1, "0 - 0", lay_price=115.0, lay_size=50, lay_ladder=((115.0, 50.0),)),
            E.ScoreRunner(3, "2 - 1", lay_price=8.0, lay_size=100, lay_ladder=((8.0, 100.0),)),
            E.ScoreRunner(4, "3 - 2", lay_price=90.0, lay_size=30, lay_ladder=((90.0, 30.0),)),
        ]
    market.read_market = lambda cs: _SnapMkt() if cs.market_id == "m-ft" else _open_snapshot()
    S.process_missions(market=market, db=db, now=NOW)
    sugg = db.missions[0]["suggestion_ft"]
    assert sugg is not None
    assert sugg["runner_name"] == "3 - 2"        # mai lo 0-0 impossibile
    assert sugg["selection_id"] == 4


# ---------------------------------------------------------------------------
# Regressioni review finale 15/07 (agenti backend+frontend)
# ---------------------------------------------------------------------------
def test_mission_scalp_non_riproposto_se_gamba_fatta():
    # CRITICAL: dopo un gol la linea cambia MERCATO; con una gamba scalp gia'
    # fatta il servizio NON deve riproporre un secondo back (doppio stake).
    db = FakeDB(_control(status="idle"))
    db.missions = [_mission(phase="2t",
                            suggestion_scalp={"market_id": "m-ou35", "selection_id": 7})]
    db.trades.append({"id": 9, "event_id": "1.100", "phase": "scalp", "status": "open",
                      "pnl": 0, "liability": 100, "selection_id": 7, "price": 1.36,
                      "size": 100, "side": "back"})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=60, home=2, away=0, status="SecondHalf")}
    S.process_missions(market=market, db=db, now=NOW)
    assert db.missions[0]["suggestion_scalp"] is None     # guardia attiva


def test_mission_ht_esclude_punteggi_irraggiungibili_nel_1t():
    # MEDIUM: al 30' sull'1-0 il book HT stantio mostra ancora "0 - 0" quotato:
    # non va MAI proposto (irraggiungibile nel primo tempo).
    db = FakeDB(_control(status="idle"))
    db.missions = [_mission(phase="1t")]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=30, home=1, away=0, status="FirstHalf")}
    ht = M.CorrectScoreMarket(market_id="m-ht", event_id="1.100",
                              event_name="Home v Away", market_start_time=None,
                              runner_names={1: "0 - 0", 3: "2 - 1", 4: "3 - 2"})
    market.markets_by_type = {("1.100", "HALF_TIME_SCORE"): ht,
                              ("1.100", "OVER_UNDER_35"): None,
                              ("1.100", "OVER_UNDER_45"): None}

    class _SnapHT:
        status = "OPEN"; inplay = True; closed = False
        winner_selection_id = None; voided = False
        runners = [
            E.ScoreRunner(1, "0 - 0", lay_price=110.0, lay_size=50, lay_ladder=((110.0, 50.0),)),
            E.ScoreRunner(3, "2 - 1", lay_price=40.0, lay_size=100, lay_ladder=((40.0, 100.0),)),
        ]
    market.read_market = lambda cs: _SnapHT() if cs.market_id == "m-ht" else _open_snapshot()
    S.process_missions(market=market, db=db, now=NOW)
    sugg = db.missions[0]["suggestion_ht"]
    assert sugg is not None and sugg["runner_name"] == "2 - 1"   # mai lo 0-0


def test_mission_non_si_chiude_con_pending_live_senza_bet_id():
    # MEDIUM: conferma DB fallita dopo ordine LIVE → pending SENZA bet_id.
    # La missione NON deve chiudersi (riaprirebbe l'evento all'automatico
    # prima della riconciliazione).
    db = FakeDB(_control(status="idle"))
    db.missions = [_mission(phase="2t")]
    db.trades.append({"id": 11, "event_id": "1.100", "phase": "ft_cs",
                      "status": "pending", "mode": "live", "bet_id": None,
                      "pnl": 0, "liability": 100, "selection_id": 4, "price": 110,
                      "size": 1, "side": "lay"})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=95, home=1, away=0, status="Finished")}
    S.process_missions(market=market, db=db, now=NOW)
    assert db.missions[0]["status"] == "active"          # mai chiudere qui


def test_mission_phase_extra_time_prima_di_halftime():
    # LOW: "ExtraTimeHalfTime" contiene anche "halftime" → deve vincere l'ET (2t)
    assert E.mission_phase(status="ExtraTimeHalfTime", minute=105,
                           kickoff=NOW, now=NOW) == "2t"
    assert E.mission_phase(status="PenaltyShootout", minute=120,
                           kickoff=NOW, now=NOW) == "2t"


# ---------------------------------------------------------------------------
# CONSULENTE DATI (advisor) — task S5: segnali INFORMATIVI best-effort dentro
# le suggestion CS. Presente quando i dati ci sono; None DICHIARATO quando
# mancano (matching fallito, db senza letture, errori) SENZA bloccare la
# proposta; MAI influenza id/prezzi (money-critical).
# ---------------------------------------------------------------------------
from Betfair.omega import omega_advisor as A  # noqa: E402


class _AdvisorDB(FakeDB):
    """FakeDB + letture advisor (fixture del giorno, Poisson, frequenze lega)."""

    def __init__(self, control, fixtures=None, analysis=None, freq=None):
        super().__init__(control)
        self.adv_fixtures = fixtures or []
        self.adv_analysis = analysis
        self.adv_freq = freq
        self.freq_calls = []

    def fixtures_for_window(self, start_iso, end_iso):
        return self.adv_fixtures

    def fixture_analysis(self, fixture_id):
        return self.adv_analysis

    def market_frequency(self, league_id, market, selection):
        self.freq_calls.append((league_id, market, selection))
        return self.adv_freq


_FIXTURE = {"fixture_id": 77, "home_team_name": "Home", "away_team_name": "Away",
            "fixture_date": NOW.isoformat(), "league_id": 242,
            "home_team_id": 10, "away_team_id": 20}
_ANALYSIS = {"model": "poisson_xg_hybrid_dc",
             "inputs": {"lambda_home": 1.0017, "lambda_away": 0.5974, "dc_rho": -0.13,
                        "ht_ratio_home": 0.427, "ht_ratio_away": 0.463}}
_FREQ = {"meta": {"baseline": 0.008, "n_effective": 300}}


def test_advisor_presente_su_ft_con_dati_reali_fake():
    # Intervallo → suggestion FT "3 - 2": advisor con Poisson + lega + H2H.
    A.reset_caches()
    A._H2H_CACHE = {"10-20": {"n_meetings": 6,
                              "ft_scores_a_b": {"3-2": 1, "0-0": 2},
                              "ht_scores_a_b": {"0-0": 5}}}
    db = _AdvisorDB(_control(status="idle"), fixtures=[_FIXTURE],
                    analysis=_ANALYSIS, freq=_FREQ)
    db.missions = [_mission(phase="1t")]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=45, home=1, away=0, status="HalfTime")}
    S.process_missions(market=market, db=db, now=NOW)
    sugg = db.missions[0]["suggestion_ft"]
    assert sugg is not None and sugg["runner_name"] == "3 - 2"
    adv = sugg["advisor"]
    assert adv is not None
    assert adv["matched_fixture_id"] == 77
    # Poisson: probabilità positiva e piccola per un 3-2 con quei lambda
    assert adv["poisson_prob"] is not None and 0 < adv["poisson_prob"] < 0.05
    assert adv["freq_league"] == {"p": 0.008, "n": 300}
    assert db.freq_calls == [(242, "exact_ft", "3-2")]
    assert adv["h2h"] == {"n_meetings": 6, "n_score": 1}
    assert set(adv["sources"]) >= {"match", "poisson", "freq_league", "h2h"}
    # MONEY-CRITICAL: l'advisor non ha toccato id/prezzi della proposta
    assert sugg["selection_id"] == 4 and sugg["market_id"] == "m-1.100-CORRECT_SCORE"
    assert sugg["lay_price"] == 110.0


def test_advisor_ht_usa_griglia_primo_tempo_e_freq_fuori_griglia_none():
    # Gamba HT "3 - 2": Poisson sulla griglia PRIMO TEMPO; exact_ht copre solo
    # 0..2 → freq_league None DICHIARATO (mai l'aggregato spacciato per il punteggio).
    A.reset_caches()
    A._H2H_CACHE = {"10-20": {"n_meetings": 6,
                              "ft_scores_a_b": {}, "ht_scores_a_b": {"0-0": 5}}}
    db = _AdvisorDB(_control(status="idle"), fixtures=[_FIXTURE],
                    analysis=_ANALYSIS, freq=_FREQ)
    db.missions = [_mission(kickoff=(NOW + timedelta(hours=1)).isoformat())]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {}
    S.process_missions(market=market, db=db, now=NOW)
    sugg = db.missions[0]["suggestion_ht"]
    assert sugg is not None and sugg["market_type"] == "HALF_TIME_SCORE"
    adv = sugg["advisor"]
    assert adv is not None
    assert adv["freq_league"] is None and db.freq_calls == []   # 3-2 fuori exact_ht
    assert adv["h2h"] == {"n_meetings": 6, "n_score": 0}        # mai uscito 3-2 HT
    # HT più raro del FT per lo stesso punteggio (lambda dimezzati dai ratio)
    p_ft = A.poisson_score_prob(_ANALYSIS["inputs"], 3, 2, half=False)
    assert adv["poisson_prob"] < p_ft


def test_advisor_matching_fallito_advisor_none_ma_proposta_viva():
    # Nessuna fixture nella finestra → matching fallito → advisor None
    # DICHIARATO; la proposta esce comunque intatta (mai bloccare).
    A.reset_caches()
    db = _AdvisorDB(_control(status="idle"), fixtures=[],
                    analysis=_ANALYSIS, freq=_FREQ)
    db.missions = [_mission(phase="ht")]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=46, home=0, away=0, status="HalfTime")}
    S.process_missions(market=market, db=db, now=NOW)
    sugg = db.missions[0]["suggestion_ft"]
    assert sugg is not None and sugg["runner_name"] == "3 - 2"
    assert sugg["advisor"] is None


def test_advisor_db_senza_letture_advisor_none():
    # FakeDB "vecchio" senza fixtures_for_window: advisor None, zero errori.
    A.reset_caches()
    db = FakeDB(_control(status="idle"))
    db.missions = [_mission(phase="ht")]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=46, home=0, away=0, status="HalfTime")}
    S.process_missions(market=market, db=db, now=NOW)
    sugg = db.missions[0]["suggestion_ft"]
    assert sugg is not None and sugg["advisor"] is None


def test_advisor_errore_db_non_blocca_la_proposta():
    # La lettura fixture esplode → advisor None, la proposta resta viva (I6).
    A.reset_caches()
    db = _AdvisorDB(_control(status="idle"), fixtures=[_FIXTURE])
    def boom(start, end):
        raise RuntimeError("db down")
    db.fixtures_for_window = boom
    db.missions = [_mission(phase="ht")]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=46, home=0, away=0, status="HalfTime")}
    S.process_missions(market=market, db=db, now=NOW)
    sugg = db.missions[0]["suggestion_ft"]
    assert sugg is not None and sugg["advisor"] is None


def test_advisor_freq_error_non_azzera_gli_altri_segnali():
    # RPC frequenze KO → solo freq_league None; Poisson e H2H restano.
    A.reset_caches()
    A._H2H_CACHE = {"10-20": {"n_meetings": 4, "ft_scores_a_b": {"3-2": 2},
                              "ht_scores_a_b": {}}}
    db = _AdvisorDB(_control(status="idle"), fixtures=[_FIXTURE],
                    analysis=_ANALYSIS)
    def freq_boom(league_id, market, selection):
        raise RuntimeError("rpc down")
    db.market_frequency = freq_boom
    db.missions = [_mission(phase="ht")]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    market.scores = {"1.100": _Snap(minute=46, home=0, away=0, status="HalfTime")}
    S.process_missions(market=market, db=db, now=NOW)
    adv = db.missions[0]["suggestion_ft"]["advisor"]
    assert adv is not None
    assert adv["freq_league"] is None
    assert adv["poisson_prob"] is not None
    assert adv["h2h"] == {"n_meetings": 4, "n_score": 2}


# --------------------------- funzioni pure dell'advisor ---------------------
def test_advisor_griglia_poisson_fedele_al_motore():
    # Somma della griglia = 1 (rinormalizzata) e correzioni DC nei versi giusti:
    # con rho<0 lo 0-0 è PIÙ probabile dell'indipendente, l'1-0 MENO.
    lh, la, rho = 1.0, 0.8, -0.13
    total = sum(A.score_grid_prob(lh, la, rho, h, a, max_goals=10)
                for h in range(11) for a in range(11))
    assert abs(total - 1.0) < 1e-9
    import math
    def indep(h, a):
        return (math.exp(-lh) * lh**h / math.factorial(h)
                * math.exp(-la) * la**a / math.factorial(a))
    norm = sum(indep(h, a) * A._dc_tau(h, a, lh, la, rho)
               for h in range(11) for a in range(11))
    assert A.score_grid_prob(lh, la, rho, 0, 0, 10) > indep(0, 0) / norm * 0.999999 \
        and A.score_grid_prob(lh, la, rho, 0, 0, 10) > indep(0, 0)
    assert A.score_grid_prob(lh, la, rho, 1, 0, 10) < indep(1, 0)
    # fuori griglia / lambda non validi → None (mai numeri inventati)
    assert A.score_grid_prob(lh, la, rho, 11, 0, 10) is None
    assert A.score_grid_prob(0.0, la, rho, 0, 0, 10) is None


def test_advisor_freq_selection_whitelist_rpc():
    # Mapping identico alla whitelist della RPC get_market_frequency
    assert A.freq_selection(3, 3, half=False) == ("exact_ft", "3-3")
    assert A.freq_selection(4, 0, half=False) is None           # fuori 0..3
    assert A.freq_selection(2, 2, half=True) == ("exact_ht", "2-2")
    assert A.freq_selection(3, 0, half=True) is None            # fuori 0..2


def test_advisor_h2h_orientamento_chiavi_e_punteggi():
    # Policy atlante: chiave 'idA-idB' con idA<idB, punteggi gol_A-gol_B.
    atlas = {"10-20": {"n_meetings": 5, "ft_scores_a_b": {"1-2": 3},
                       "ht_scores_a_b": {}}}
    # home=10 (id minore): il 1-2 proposto si cerca dritto
    assert A.h2h_score_stats(10, 20, 1, 2, half=False, atlas=atlas) == \
        {"n_meetings": 5, "n_score": 3}
    # home=20 (id maggiore): il 2-1 proposto (home-away) va INVERTITO in 1-2
    assert A.h2h_score_stats(20, 10, 2, 1, half=False, atlas=atlas) == \
        {"n_meetings": 5, "n_score": 3}
    # coppia assente → None (fallback pulito, mai un match forzato)
    assert A.h2h_score_stats(1, 2, 0, 0, half=False, atlas=atlas) is None


# ---------------------------------------------------------------------------
# Fix 16/07 — fasi provider mancanti + chiusura da solo orologio verificata
# ---------------------------------------------------------------------------
def test_mission_phase_secondhalfend_e_stati_abbandono():
    # 'SecondHalfEnd' contiene 'secondhalf': DEVE vincere il check FINISHED
    assert E.mission_phase(status="SecondHalfEnd", minute=90, kickoff=NOW, now=NOW) == "finita"
    assert E.mission_phase(status="Abandoned", minute=30, kickoff=NOW, now=NOW) == "finita"
    assert E.mission_phase(status="Postponed", minute=None, kickoff=NOW, now=NOW) == "finita"
    assert E.mission_phase(status="Cancelled", minute=None, kickoff=NOW, now=NOW) == "finita"


def test_mission_clock_finita_ma_book_vivo_non_chiude():
    # kickoff+4h senza MAI dati provider, ma il mercato CS è ancora vivo su
    # Betfair (partita rinviata/spostata) → la missione NON si chiude e la
    # fase resta quella precedente (mai 'finita' scritta dal solo orologio)
    S._REALLY_OVER_CACHE.clear()
    db = FakeDB(_control())
    kick = (NOW - timedelta(hours=4)).isoformat()
    db.missions = [_mission("77", kickoff=kick)]
    market = FakeMarket([], _cs("77"), _open_snapshot())   # book OPEN, non closed
    market.scores = {}                                     # provider muto
    S.process_missions(market=market, db=db, now=NOW)
    m = db.missions[0]
    assert m["status"] == "active"
    assert m["phase_now"] == "pre"
    # review 16/07 (finding 4): la missione tenuta viva deve CONSERVARE i
    # suggerimenti — la fase usata dalla logica suggerimenti è quella
    # ripristinata ('pre'), non 'finita' → la gamba HT resta proposta
    assert m["suggestion_ht"] is not None


def test_mission_clock_finita_e_book_chiuso_chiude():
    S._REALLY_OVER_CACHE.clear()
    db = FakeDB(_control())
    kick = (NOW - timedelta(hours=4)).isoformat()
    db.missions = [_mission("77", kickoff=kick)]
    market = FakeMarket([], _cs("77"), _closed_snapshot(1))  # mercato CLOSED
    market.scores = {}
    S.process_missions(market=market, db=db, now=NOW)
    m = db.missions[0]
    assert m["status"] == "closed" and m["phase_now"] == "finita"


def test_mission_clock_verifica_book_in_cache_ttl():
    # finding 10: la verifica "davvero finita" è cachata (TTL) — su cicli
    # ravvicinati NON si richiama Betfair a ogni giro
    S._REALLY_OVER_CACHE.clear()
    db = FakeDB(_control())
    kick = (NOW - timedelta(hours=4)).isoformat()
    db.missions = [_mission("77", kickoff=kick)]
    market = FakeMarket([], _cs("77"), _open_snapshot())
    market.scores = {}
    calls = {"n": 0}
    orig = market.get_correct_score_market
    def counting(ev):
        calls["n"] += 1
        return orig(ev)
    market.get_correct_score_market = counting
    S.process_missions(market=market, db=db, now=NOW)
    S.process_missions(market=market, db=db, now=NOW + timedelta(seconds=30))
    assert calls["n"] == 1  # 2° ciclo dentro il TTL → nessuna nuova chiamata


def test_mission_finita_da_provider_chiude_senza_verifica_book():
    # dato provider esplicito ('Finished') → si chiude anche se il fake book
    # è ancora OPEN: la verifica extra vale SOLO per il fallback orologio
    db = FakeDB(_control())
    db.missions = [_mission("77", kickoff=NOW.isoformat())]
    market = FakeMarket([], _cs("77"), _open_snapshot())
    market.scores = {"77": _Snap(minute=90, home=1, away=0, status="Finished")}
    S.process_missions(market=market, db=db, now=NOW)
    assert db.missions[0]["status"] == "closed"


def test_guardia_auto_salta_anche_missioni_in_pausa():
    # audit M7: missione PAUSATA = evento comunque riservato alla scheda
    db = FakeDB(_control())
    db.missions = [_mission("1.100", status="paused")]
    ids = db.mission_event_ids()
    assert "1.100" in ids
