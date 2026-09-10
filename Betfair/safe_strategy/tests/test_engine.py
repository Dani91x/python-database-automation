# -*- coding: utf-8 -*-
"""test_engine.py - port dei test del motore PURO Safe Strategy.

Ogni caso di ``frontend/src/lib/safeStrategy.test.ts`` che riguarda il MOTORE e'
riprodotto qui con le STESSE fixture e gli STESSI esiti attesi: i due motori
(TypeScript nel browser, Python sul server) devono decidere identico.

Differenza di FONTE (voluta): il TS costruisce i contesti sia dagli snapshot
``live_now`` sia dalle righe dello scanner; il motore Python parte SEMPRE dalle
righe ``safe_strategy_scan``, quindi le fixture sono i payload dello scanner.
L'unica conseguenza semantica e' lo stato mercato assente: negli snapshot
legacy valeva "aperto", nello scanner vale "ignoto" (n/d) - il TS lo certifica
gia' cosi' nel blocco build*CtxFromScan.

Il file non stampa nulla di non-ASCII (console Windows cp1252).
"""
from typing import Any, Dict, List, Optional

import pytest

from Betfair.safe_strategy import engine as eng

# --------------------------------------------------------------------- fixture
PRE_MATCH = {"home": 1.65, "draw": 4.0, "away": 5.5}
_UNSET = object()


def calcio_payload(
    minute: Any = 58,
    sh: Any = 1,
    sa: Any = 0,
    inplay: bool = True,
    fav_back: Optional[float] = 1.28,
    fav_lay: Optional[float] = 1.3,
    dog_back: Optional[float] = 8.0,
    dog_lay: Optional[float] = 8.4,
    any_other_home_lay: Optional[float] = 45,
    any_other_away_lay: Optional[float] = 50,
    with_cs: bool = True,
    mo_status: Optional[str] = "OPEN",
    cs_status: Optional[str] = "OPEN",
    red_home: Any = _UNSET,
    red_away: Any = _UNSET,
    pre_match: Any = _UNSET,
    with_sizes: bool = False,
) -> Dict[str, Any]:
    """Equivalente scanner della fixture ``liveNow`` del TS (Nord FC = casa)."""

    def pair(back, lay, bsz=None, lsz=None, sid=None):
        p: Dict[str, Any] = {"back": back, "lay": lay}
        if with_sizes:
            p["back_size"] = bsz
            p["lay_size"] = lsz
        if sid is not None:
            p["selection_id"] = sid
        return p

    payload: Dict[str, Any] = {
        "event_name": "Nord FC v Sud FC",
        "home": "Nord FC",
        "away": "Sud FC",
        "competition": "Serie A",
        "open_date": "2026-09-02T16:00:00+00:00",
        "inplay": inplay,
        "mo_market_id": "1.1",
        "mo_status": mo_status,
        "odds": {
            "home": pair(fav_back, fav_lay, 152.4, 41.26, 1),
            "draw": pair(5.0, 5.2, 10, 12, 3),
            "away": pair(dog_back, dog_lay, 7.5, 120, 2),
        },
        "minute": minute,
        "score_home": sh,
        "score_away": sa,
        "red_home": None if red_home is _UNSET else red_home,
        "red_away": None if red_away is _UNSET else red_away,
        "pre_ko": PRE_MATCH if pre_match is _UNSET else pre_match,
        "cs": None,
    }
    if with_cs:
        payload["cs"] = {
            "market_id": "1.2",
            "status": cs_status,
            "any_other_home": pair(44, any_other_home_lay, 3.5, 2.25),
            "any_other_away": pair(48, any_other_away_lay, 1, 9),
            "selections": [
                {"selection_id": 10, "name": "1 - 0", "back": 3.0, "lay": 3.1},
                {"selection_id": 11, "name": "Any Other Home Win", "back": 44, "lay": any_other_home_lay},
                {"selection_id": 12, "name": "Any Other Away Win", "back": 48, "lay": any_other_away_lay},
            ],
        }
    return payload


def ctx_of(stable_since: Any = 50, observed_sec: Any = 60, **over: Any) -> eng.FootballMatchCtx:
    return eng.build_football_ctx_from_scan("ev1", calcio_payload(**over), stable_since, observed_sec)


def tennis_payload(
    sets: Any = _UNSET,
    games: Any = _UNSET,
    inplay: bool = True,
    p1_back: Optional[float] = 1.03,
    p2_lay: Optional[float] = 15,
    mo_status: Optional[str] = "OPEN",
    p1: str = "Rossi M.",
    p2: str = "Bianchi L.",
    competition: Optional[str] = None,
    with_sizes: bool = False,
) -> Dict[str, Any]:
    """Equivalente scanner della fixture ``tennisNow`` del TS."""
    sets_v = {"p1": 1, "p2": 0} if sets is _UNSET else sets
    games_v = {"p1": 3, "p2": 0} if games is _UNSET else games

    def pair(back, lay, bsz=None, lsz=None, sid=None):
        p: Dict[str, Any] = {"back": back, "lay": lay}
        if with_sizes:
            p["back_size"] = bsz
            p["lay_size"] = lsz
        if sid is not None:
            p["selection_id"] = sid
        return p

    return {
        "event_name": f"{p1} v {p2}",
        "p1": p1,
        "p2": p2,
        "competition": competition,
        "open_date": None,
        "inplay": inplay,
        "mo_market_id": "1.9",
        "mo_status": mo_status,
        "odds": {
            "p1": pair(p1_back, None if p1_back is None else p1_back + 0.01, 812.5, 90, 1),
            "p2": pair(None if p2_lay is None else p2_lay - 1, p2_lay, 4, 6, 2),
        },
        "sets": sets_v,
        "games": games_v,
    }


def tennis_ctx(observed_sec: Any = 60, **over: Any) -> eng.TennisMatchCtx:
    return eng.build_tennis_ctx_from_scan("tv1", tennis_payload(**over), observed_sec)


def row(event_id: str, sport: str, payload: Dict[str, Any], updated_at: Optional[str] = None) -> Dict[str, Any]:
    return {"event_id": event_id, "sport": sport, "payload": payload, "updated_at": updated_at}


def check(ev: eng.VariantEvaluation, check_id: str) -> Optional[eng.ConditionCheck]:
    return next((c for c in ev.checks if c.id == check_id), None)


class FakeClock:
    """orologio iniettabile (secondi epoch) per i test dei tracker."""

    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


# ------------------------------------------------------------------ utilities
def test_parse_scoreline_validi_e_malformati():
    assert eng.parse_scoreline("2-1") == (2, 1)
    assert eng.parse_scoreline(" 10-0 ") == (10, 0)
    assert eng.parse_scoreline("2:1") is None
    assert eng.parse_scoreline("a-b") is None
    assert eng.parse_scoreline("") is None


def test_score_in_list_orientato_vs_qualsiasi_ordine():
    assert eng.score_in_list_oriented(["1-0", "2-1"], 1, 0) is True
    assert eng.score_in_list_oriented(["1-0"], 0, 1) is False
    assert eng.score_in_list_any_order(["1-0"], 0, 1) is True
    assert eng.score_in_list_any_order(["1-1"], 1, 1) is True
    assert eng.score_in_list_any_order(["2-0"], 1, 1) is False


# ---------------------------------------------------------------- merge params
def _tsparams(p: Dict[str, Any]) -> Dict[str, Any]:
    """le 4 sezioni portate dal TS (la sezione stake e' un'aggiunta Python)."""
    return {k: v for k, v in p.items() if k != "stake"}


def test_merge_params_input_nullo_o_garbage_torna_ai_default():
    assert _tsparams(eng.merge_params(None)) == _tsparams(eng.DEFAULT_PARAMS)
    assert _tsparams(eng.merge_params("x")) == _tsparams(eng.DEFAULT_PARAMS)
    assert eng.merge_params({"base": {"minuteMin": "boom", "scores": 42}})["base"] == eng.DEFAULT_PARAMS["base"]


def test_merge_params_override_parziale_preserva_il_resto():
    p = eng.merge_params({"base": {"minuteMin": 50}, "tennis": {"gamesLeadMin": 3}})
    assert p["base"]["minuteMin"] == 50
    assert p["base"]["scores"] == eng.DEFAULT_PARAMS["base"]["scores"]
    assert p["tennis"]["gamesLeadMin"] == 3
    assert p["esatto"] == eng.DEFAULT_PARAMS["esatto"]


def test_merge_params_legacy_minutemax_ignorato_senza_errori():
    p = eng.merge_params({"base": {"minuteMin": 55, "minuteMax": 62}, "esatto": {"minuteMax": 50}})
    assert p["base"]["minuteMin"] == 55
    assert "minuteMax" not in p["base"]
    assert p["esatto"] == eng.DEFAULT_PARAMS["esatto"]


def test_merge_params_scores_filtra_malformati_e_lista_vuota_torna_default():
    assert eng.merge_params({"base": {"scores": ["1-0", "x"]}})["base"]["scores"] == ["1-0"]
    assert eng.merge_params({"base": {"scores": ["bad"]}})["base"]["scores"] == eng.DEFAULT_PARAMS["base"]["scores"]


def test_merge_params_stake_default_e_override():
    assert eng.merge_params(None)["stake"] == {"laySize": 2.0, "backSize": 2.0}
    assert eng.merge_params({"stake": {"laySize": 25}})["stake"]["laySize"] == 25
    assert eng.merge_params({"backSize": 10})["stake"]["backSize"] == 10


# ------------------------------------------------------------ stateFromChecks
def test_state_from_checks_false_vince_su_null_null_vince_su_true():
    def c(ok):
        return eng.ConditionCheck("a", "", "", ok)

    assert eng.state_from_checks([c(True)]) == "signal"
    assert eng.state_from_checks([c(True), c(None)]) == "nd"
    assert eng.state_from_checks([c(None), c(False)]) == "no"


# ------------------------------------------------------------- contesto calcio
def test_build_ctx_mappa_odds_any_other_e_pre_match():
    ctx = ctx_of()
    assert (ctx.odds.home.back, ctx.odds.home.lay) == (1.28, 1.3)
    assert (ctx.odds.away.back, ctx.odds.away.lay) == (8.0, 8.4)
    assert (ctx.odds.draw.back, ctx.odds.draw.lay) == (5.0, 5.2)
    assert ctx.any_other.home.lay == 45
    assert ctx.any_other.away.lay == 50
    assert ctx.pre_match == {"home": 1.65, "draw": 4.0, "away": 5.5}
    assert eng.favorite_side(ctx.pre_match) == "home"
    # selection_id risolti: MATCH_ODDS dal pair, "Any Other" dal nome nel CS
    assert ctx.odds.away.selection_id == 2
    assert ctx.any_other_home_selection_id == 11
    assert ctx.any_other_away_selection_id == 12


def test_build_ctx_payload_vuoto_campi_null_mai_inventati():
    ctx = eng.build_football_ctx_from_scan("ev1", {}, None, None)
    assert ctx.odds is None
    assert ctx.any_other is None
    assert ctx.pre_match is None
    assert ctx.minute is None
    assert ctx.inplay is False
    assert ctx.red is None


# -------------------------------------------------------------------- 1 . Base
def test_base_segnale_favorita_1_0_al_58():
    ev = eng.evaluate_base(ctx_of(), eng.DEFAULT_PARAMS["base"])
    assert ev.state == "signal"
    assert ev.headline == "BANCA Sud FC"
    assert ev.side == "LAY"
    assert ev.entry_odds == 8.4


def test_base_no_minuto_prima_della_soglia():
    ev = eng.evaluate_base(ctx_of(minute=54), eng.DEFAULT_PARAMS["base"])
    assert ev.state == "no"
    assert check(ev, "minute").ok is False


def test_base_soglia_minuto_nessun_tetto():
    for minute in (55, 70, 89):
        assert eng.evaluate_base(ctx_of(minute=minute), eng.DEFAULT_PARAMS["base"]).state == "signal"


def test_base_no_favorita_non_in_vantaggio():
    assert eng.evaluate_base(ctx_of(sh=0, sa=1), eng.DEFAULT_PARAMS["base"]).state == "no"


def test_base_no_quota_live_favorita_fuori_range():
    assert eng.evaluate_base(ctx_of(fav_back=1.5), eng.DEFAULT_PARAMS["base"]).state == "no"


def test_base_no_favorita_pre_match_fuori_range():
    ctx = ctx_of(pre_match={"home": 1.15, "draw": 6.0, "away": 12.0})
    assert eng.evaluate_base(ctx, eng.DEFAULT_PARAMS["base"]).state == "no"


def test_base_nd_pre_match_mancante_mai_falso_positivo():
    ev = eng.evaluate_base(ctx_of(pre_match=None), eng.DEFAULT_PARAMS["base"])
    assert ev.state == "nd"
    assert ev.headline is None


def test_base_no_non_in_play():
    assert eng.evaluate_base(ctx_of(inplay=False), eng.DEFAULT_PARAMS["base"]).state == "no"


def test_base_no_mercato_sospeso():
    assert eng.evaluate_base(ctx_of(mo_status="SUSPENDED"), eng.DEFAULT_PARAMS["base"]).state == "no"


def test_base_segnale_con_favorita_in_trasferta():
    ctx = ctx_of(
        sh=0,
        sa=1,
        fav_back=8.0,
        fav_lay=8.4,      # Nord (casa) qui SFAVORITA
        dog_back=1.28,
        dog_lay=1.3,      # Sud (trasferta) qui FAVORITA
        pre_match={"home": 5.5, "draw": 4.0, "away": 1.65},
    )
    ev = eng.evaluate_base(ctx, eng.DEFAULT_PARAMS["base"])
    assert ev.state == "signal"
    assert ev.headline == "BANCA Nord FC"
    assert ev.entry_odds == 8.4


def test_base_nd_stabilita_punteggio_non_osservabile():
    assert eng.evaluate_base(ctx_of(observed_sec=None), eng.DEFAULT_PARAMS["base"]).state == "nd"


def test_base_no_punteggio_osservato_da_10_secondi():
    assert eng.evaluate_base(ctx_of(observed_sec=10), eng.DEFAULT_PARAMS["base"]).state == "no"


def test_base_no_rosso_alla_favorita():
    ctx = ctx_of(red_home=1, red_away=0)
    assert eng.evaluate_base(ctx, eng.DEFAULT_PARAMS["base"]).state == "no"


def test_base_rosso_alla_sfavorita_non_blocca():
    ctx = ctx_of(red_home=0, red_away=1)
    assert eng.evaluate_base(ctx, eng.DEFAULT_PARAMS["base"]).state == "signal"


def test_base_cartellini_non_esposti_check_saltato():
    ev = eng.evaluate_base(ctx_of(), eng.DEFAULT_PARAMS["base"])
    assert ev.state == "signal"
    assert check(ev, "noRedFav") is None


def test_base_nd_lay_sfavorita_mancante():
    ev = eng.evaluate_base(ctx_of(dog_lay=None), eng.DEFAULT_PARAMS["base"])
    assert ev.state == "nd"
    assert ev.entry_odds is None


def test_base_mo_status_assente_e_ignoto_non_aperto():
    # semantica SCANNER (build*CtxFromScan del TS): mai "aperto" per default
    ctx = ctx_of(mo_status=None)
    assert ctx.match_odds_open is None
    assert eng.evaluate_base(ctx, eng.DEFAULT_PARAMS["base"]).state == "nd"


def test_base_selection_id_e_mercato_nel_segnale():
    ev = eng.evaluate_base(ctx_of(), eng.DEFAULT_PARAMS["base"])
    assert ev.market_type == "MATCH_ODDS"
    assert ev.market_id == "1.1"
    assert ev.selection_id == 2


# --------------------------------------------------------- 2 . Risultato Esatto
def test_esatto_segnale_lato_casa():
    ev = eng.evaluate_esatto(ctx_of(minute=49), eng.DEFAULT_PARAMS["esatto"], "home")
    assert ev.state == "signal"
    assert "Altro risultato Casa" in ev.headline
    assert ev.entry_odds == 45
    assert ev.market_type == "CORRECT_SCORE"
    assert ev.market_id == "1.2"
    assert ev.selection_id == 11


def test_esatto_soglia_minuto_48_nessun_tetto():
    assert eng.evaluate_esatto(ctx_of(minute=47), eng.DEFAULT_PARAMS["esatto"], "home").state == "no"
    for minute in (48, 65, 80):
        assert eng.evaluate_esatto(ctx_of(minute=minute), eng.DEFAULT_PARAMS["esatto"], "home").state == "signal"


def test_esatto_tetto_reale_e_il_range_quota():
    ctx = ctx_of(minute=80, any_other_home_lay=90)
    assert eng.evaluate_esatto(ctx, eng.DEFAULT_PARAMS["esatto"], "home").state == "no"


def test_esatto_no_lato_con_troppi_gol_ma_altro_lato_valido():
    ev = eng.evaluate_esatto(ctx_of(minute=49, sh=2, sa=1), eng.DEFAULT_PARAMS["esatto"], "home")
    assert ev.state == "no"
    ev_away = eng.evaluate_esatto(
        ctx_of(minute=49, sh=2, sa=1, any_other_away_lay=50), eng.DEFAULT_PARAMS["esatto"], "away"
    )
    assert ev_away.state == "signal"


def test_esatto_no_punteggio_non_in_lista():
    ctx = ctx_of(minute=49, sh=3, sa=0)
    assert eng.evaluate_esatto(ctx, eng.DEFAULT_PARAMS["esatto"], "away").state == "no"


def test_esatto_no_quota_fuori_range():
    ctx = ctx_of(minute=49, any_other_home_lay=20)
    assert eng.evaluate_esatto(ctx, eng.DEFAULT_PARAMS["esatto"], "home").state == "no"


def test_esatto_nd_mercato_correct_score_assente():
    ctx = ctx_of(minute=49, with_cs=False)
    assert eng.evaluate_esatto(ctx, eng.DEFAULT_PARAMS["esatto"], "home").state == "nd"


def test_esatto_nd_lay_mancante_mai_il_back_come_sostituto():
    ev = eng.evaluate_esatto(ctx_of(minute=49, any_other_home_lay=None), eng.DEFAULT_PARAMS["esatto"], "home")
    assert ev.state == "nd"
    assert ev.entry_odds is None


def test_esatto_no_mercato_correct_score_sospeso():
    ctx = ctx_of(minute=49, cs_status="SUSPENDED")
    assert eng.evaluate_esatto(ctx, eng.DEFAULT_PARAMS["esatto"], "home").state == "no"


def test_esatto_no_punteggio_osservato_da_10_secondi():
    ctx = ctx_of(minute=49, observed_sec=10)
    assert eng.evaluate_esatto(ctx, eng.DEFAULT_PARAMS["esatto"], "home").state == "no"


def test_esatto_nd_stabilita_punteggio_non_osservabile():
    ctx = ctx_of(minute=49, observed_sec=None)
    assert eng.evaluate_esatto(ctx, eng.DEFAULT_PARAMS["esatto"], "home").state == "nd"


# ------------------------------------------------------------ 3 . Variante Punta
PUNTA = dict(minute=68, sh=2, sa=0, fav_back=1.06, stable_since=63)


def test_punta_segnale_2_0_al_68_assestato():
    ev = eng.evaluate_punta(ctx_of(**PUNTA), eng.DEFAULT_PARAMS["punta"])
    assert ev.state == "signal"
    assert ev.headline == "PUNTA Nord FC"
    assert ev.side == "BACK"
    assert ev.entry_odds == 1.06


def test_punta_soglia_minuto_66_nessun_tetto():
    assert eng.evaluate_punta(ctx_of(**{**PUNTA, "minute": 65}), eng.DEFAULT_PARAMS["punta"]).state == "no"
    assert eng.evaluate_punta(ctx_of(**{**PUNTA, "minute": 66}), eng.DEFAULT_PARAMS["punta"]).state == "signal"
    assert eng.evaluate_punta(ctx_of(**{**PUNTA, "minute": 85}), eng.DEFAULT_PARAMS["punta"]).state == "signal"


def test_punta_no_gol_troppo_recente():
    ctx = ctx_of(**{**PUNTA, "stable_since": 67})
    assert eng.evaluate_punta(ctx, eng.DEFAULT_PARAMS["punta"]).state == "no"


def test_punta_nd_stabilita_non_ancora_osservabile():
    ctx = ctx_of(**{**PUNTA, "stable_since": None})
    assert eng.evaluate_punta(ctx, eng.DEFAULT_PARAMS["punta"]).state == "nd"


def test_punta_no_in_vantaggio_c_e_la_sfavorita():
    ctx = ctx_of(**{**PUNTA, "sh": 0, "sa": 2, "dog_back": 1.06})
    assert eng.evaluate_punta(ctx, eng.DEFAULT_PARAMS["punta"]).state == "no"


def test_punta_no_margine_di_un_solo_gol():
    ctx = ctx_of(**{**PUNTA, "sh": 2, "sa": 1})
    assert eng.evaluate_punta(ctx, eng.DEFAULT_PARAMS["punta"]).state == "no"


def test_punta_no_mercato_sospeso():
    ctx = ctx_of(**{**PUNTA, "mo_status": "SUSPENDED"})
    assert eng.evaluate_punta(ctx, eng.DEFAULT_PARAMS["punta"]).state == "no"


def test_punta_no_rosso_a_chi_si_punta():
    ctx = ctx_of(**{**PUNTA, "red_home": 1, "red_away": 0})
    assert eng.evaluate_punta(ctx, eng.DEFAULT_PARAMS["punta"]).state == "no"


def test_punta_rosso_a_chi_perde_non_blocca():
    ctx = ctx_of(**{**PUNTA, "red_home": 0, "red_away": 1})
    assert eng.evaluate_punta(ctx, eng.DEFAULT_PARAMS["punta"]).state == "signal"


def test_punta_cartellini_non_esposti_check_saltato():
    ev = eng.evaluate_punta(ctx_of(**PUNTA), eng.DEFAULT_PARAMS["punta"])
    assert ev.state == "signal"
    assert check(ev, "noRedLead") is None


def test_punta_segnale_con_favorita_in_trasferta():
    ctx = ctx_of(
        minute=68,
        sh=0,
        sa=2,
        stable_since=63,
        dog_back=1.06,
        pre_match={"home": 5.5, "draw": 4.0, "away": 1.65},
    )
    ev = eng.evaluate_punta(ctx, eng.DEFAULT_PARAMS["punta"])
    assert ev.state == "signal"
    assert ev.headline == "PUNTA Sud FC"


# ------------------------------------------------------------------ 4 . Tennis
def test_tennis_segnale_set_1_0_e_3_0():
    ev = eng.evaluate_tennis(tennis_ctx(), eng.DEFAULT_PARAMS["tennis"])
    assert ev.state == "signal"
    assert ev.headline == "PUNTA Rossi M."
    assert ev.side == "BACK"
    assert ev.entry_odds == 1.03


def test_tennis_segnale_back_leader_1_08():
    ev = eng.evaluate_tennis(tennis_ctx(p1_back=1.08), eng.DEFAULT_PARAMS["tennis"])
    assert ev.state == "signal"
    assert ev.entry_odds == 1.08


def test_tennis_no_back_leader_fuori_range():
    assert eng.evaluate_tennis(tennis_ctx(p1_back=1.15), eng.DEFAULT_PARAMS["tennis"]).state == "no"


def test_tennis_nd_back_leader_non_disponibile():
    assert eng.evaluate_tennis(tennis_ctx(p1_back=None), eng.DEFAULT_PARAMS["tennis"]).state == "nd"


def test_tennis_no_punteggio_osservato_da_5_secondi():
    assert eng.evaluate_tennis(tennis_ctx(observed_sec=5), eng.DEFAULT_PARAMS["tennis"]).state == "no"


def test_tennis_nd_stabilita_non_osservabile():
    assert eng.evaluate_tennis(tennis_ctx(observed_sec=None), eng.DEFAULT_PARAMS["tennis"]).state == "nd"


def test_tennis_filtro_competizioni():
    params = {**eng.DEFAULT_PARAMS["tennis"], "excludeCompetitions": ["wimbledon"]}

    def at(comp):
        return eng.evaluate_tennis(tennis_ctx(competition=comp), params).state

    assert at("ATP Wimbledon") == "no"
    assert at("ATP Rome") == "signal"
    assert at(None) == "nd"
    # lista vuota (default) -> check assente, nessun blocco
    ev = eng.evaluate_tennis(tennis_ctx(), eng.DEFAULT_PARAMS["tennis"])
    assert check(ev, "competition") is None


def test_tennis_no_solo_un_game_di_vantaggio():
    ctx = tennis_ctx(games={"p1": 2, "p2": 1})
    assert eng.evaluate_tennis(ctx, eng.DEFAULT_PARAMS["tennis"]).state == "no"


def test_tennis_no_vantaggio_game_del_giocatore_sbagliato():
    ctx = tennis_ctx(games={"p1": 0, "p2": 3})
    assert eng.evaluate_tennis(ctx, eng.DEFAULT_PARAMS["tennis"]).state == "no"


def test_tennis_no_set_in_parita():
    ctx = tennis_ctx(sets={"p1": 1, "p2": 1})
    assert eng.evaluate_tennis(ctx, eng.DEFAULT_PARAMS["tennis"]).state == "no"


def test_tennis_no_doppio_escluso():
    ctx = tennis_ctx(p1="Rossi/Verdi", p2="Bianchi/Neri")
    assert eng.evaluate_tennis(ctx, eng.DEFAULT_PARAMS["tennis"]).state == "no"


def test_tennis_nd_punteggio_non_disponibile():
    ctx = tennis_ctx(sets=None, games=None)
    assert eng.evaluate_tennis(ctx, eng.DEFAULT_PARAMS["tennis"]).state == "nd"


def test_tennis_no_mercato_sospeso():
    ctx = tennis_ctx(mo_status="SUSPENDED")
    assert eng.evaluate_tennis(ctx, eng.DEFAULT_PARAMS["tennis"]).state == "no"


# ------------------------------------------------------ contesti dallo SCANNER
def test_scan_calcio_payload_completo_da_segnale_base():
    ctx = eng.build_football_ctx_from_scan(
        "ev9",
        {
            "event_name": "Nord FC v Sud FC",
            "home": "Nord FC",
            "away": "Sud FC",
            "competition": "Serie A",
            "open_date": "2026-09-02T16:00:00+00:00",
            "inplay": True,
            "mo_market_id": "1.1",
            "mo_status": "OPEN",
            "odds": {
                "home": {"back": 1.28, "lay": 1.3},
                "draw": {"back": 5.0, "lay": 5.2},
                "away": {"back": 8.0, "lay": 8.4},
            },
            "minute": 58,
            "score_home": 1,
            "score_away": 0,
            "red_home": 0,
            "red_away": 0,
            "pre_ko": {"home": 1.65, "draw": 4.0, "away": 5.5, "captured_at": "x"},
            "cs": {
                "market_id": "1.2",
                "status": "OPEN",
                "any_other_home": {"back": 44, "lay": 45},
                "any_other_away": {"back": 48, "lay": 50},
            },
        },
        50,
        60,
    )
    ev = eng.evaluate_base(ctx, eng.DEFAULT_PARAMS["base"])
    assert ev.state == "signal"
    assert ev.headline == "BANCA Sud FC"
    assert ctx.red == {"home": 0, "away": 0}
    assert ctx.any_other.home.lay == 45


def test_scan_calcio_mo_status_null_mercato_nd():
    ctx = eng.build_football_ctx_from_scan(
        "ev9",
        {
            "event_name": None, "home": None, "away": None, "competition": None, "open_date": None,
            "inplay": True, "mo_market_id": None, "mo_status": None, "odds": None,
            "minute": None, "score_home": None, "score_away": None,
            "red_home": None, "red_away": None, "pre_ko": None, "cs": None,
        },
        None,
        None,
    )
    assert ctx.match_odds_open is None
    assert ctx.correct_score_open is None
    assert ctx.pre_match is None


def test_scan_tennis_payload_con_competizione_e_segnale():
    ctx = eng.build_tennis_ctx_from_scan(
        "tv9",
        {
            "event_name": "Rossi M. v Bianchi L.", "p1": "Rossi M.", "p2": "Bianchi L.",
            "competition": "ATP Rome", "open_date": None, "inplay": True,
            "mo_market_id": "1.9", "mo_status": "OPEN",
            "odds": {"p1": {"back": 1.03, "lay": 1.04}, "p2": {"back": 14, "lay": 15}},
            "sets": {"p1": 1, "p2": 0}, "games": {"p1": 3, "p2": 0},
        },
        60,
    )
    assert ctx.competition == "ATP Rome"
    assert eng.evaluate_tennis(ctx, eng.DEFAULT_PARAMS["tennis"]).state == "signal"


# --------------------------------------------------------- stabilita punteggio
def test_track_score_stability_primo_avvistamento():
    assert eng.track_score_stability(None, 58, 1, 0, 1000) == eng.ScoreStability("1-0", 58, 1000)


def test_track_score_stability_stesso_punteggio_conserva_la_prima_osservazione():
    prev = eng.ScoreStability("1-0", 58, 1000)
    assert eng.track_score_stability(prev, 63, 1, 0, 9000) is prev


def test_track_score_stability_gol_fa_ripartire_il_timer():
    prev = eng.ScoreStability("1-0", 58, 1000)
    assert eng.track_score_stability(prev, 66, 2, 0, 9000) == eng.ScoreStability("2-0", 66, 9000)


def test_track_score_stability_dati_mancanti_non_toccano_lo_stato():
    prev = eng.ScoreStability("1-0", 58, 1000)
    assert eng.track_score_stability(prev, None, 1, 0, 2000) is prev
    assert eng.track_score_stability(prev, 60, None, 0, 2000) is prev


def test_track_tennis_score_stability():
    first = eng.track_tennis_score_stability(None, "s1-0" + eng.MIDDOT + "g3-0", 1000)
    assert first == eng.TennisScoreStability("s1-0" + eng.MIDDOT + "g3-0", 1000)
    assert eng.track_tennis_score_stability(first, first.score_key, 9000) is first
    assert eng.track_tennis_score_stability(first, None, 9000) is first
    assert eng.track_tennis_score_stability(first, "s1-0" + eng.MIDDOT + "g4-0", 9000).since_ms == 9000


# ---------------------------------------------------- riconciliazione segnali
def candidate(key: str, odds: float = 8.4, size: Optional[float] = 120) -> eng._Candidate:
    return eng._Candidate(
        key=key, sport="calcio", variant="base", sub_id=None, event_id="ev1",
        event_name="Nord FC " + eng.NDASH + " Sud FC", headline="BANCA Sud FC", side="LAY",
        entry_odds=odds, entry_size=size, market_type="MATCH_ODDS", market_id="1.1",
        selection_id=2, selection_name="Sud FC", minute=58, score="1-0",
        context_at_trigger="58" + eng.PRIME, checks=(),
    )


def test_reconcile_candidato_nuovo_attivo_e_fresh():
    nxt, fresh = eng.reconcile_signals([], [candidate("k1")], 1000)
    assert len(nxt) == 1
    assert nxt[0].status == "active"
    assert len(fresh) == 1


def test_reconcile_candidato_gia_attivo_aggiorna_quota_e_size_senza_fresh():
    first, _ = eng.reconcile_signals([], [candidate("k1", 8.4, 120)], 1000)
    nxt, fresh = eng.reconcile_signals(first, [candidate("k1", 8.8, 35.5)], 2000)
    assert fresh == []
    assert nxt[0].cand.entry_odds == 8.8
    assert nxt[0].cand.entry_size == 35.5
    assert nxt[0].triggered_at == 1000


def test_reconcile_candidato_sparito_expired_ma_resta_nello_storico():
    first, _ = eng.reconcile_signals([], [candidate("k1")], 1000)
    nxt, fresh = eng.reconcile_signals(first, [], 2000)
    assert fresh == []
    assert nxt[0].status == "expired"
    assert nxt[0].expired_at == 2000


def test_reconcile_situazione_tornata_valida_riattiva_senza_fresh():
    s1, _ = eng.reconcile_signals([], [candidate("k1")], 1000)
    s2, _ = eng.reconcile_signals(s1, [], 2000)
    nxt, fresh = eng.reconcile_signals(s2, [candidate("k1")], 3000)
    assert fresh == []
    assert nxt[0].status == "active"


# ------------------------------------------------------- estrazione candidati
def test_football_candidates_solo_signal_chiave_con_punteggio():
    ctx = ctx_of()
    evs = [
        eng.evaluate_base(ctx, eng.DEFAULT_PARAMS["base"]),      # signal (58' 1-0)
        eng.evaluate_punta(ctx, eng.DEFAULT_PARAMS["punta"]),    # no (margine 1 gol)
    ]
    cands = eng.football_candidates(ctx, evs)
    assert len(cands) == 1
    assert cands[0].key == eng.signal_key("ev1", "base", None, "1-0")
    with_esatto = eng.football_candidates(
        ctx, evs + [eng.evaluate_esatto(ctx, eng.DEFAULT_PARAMS["esatto"], "home")]
    )
    assert [c.key for c in with_esatto] == [
        eng.signal_key("ev1", "base", None, "1-0"),
        eng.signal_key("ev1", "esatto", "home", "1-0"),
    ]


def test_tennis_candidates_chiave_con_punteggio_set():
    ctx = tennis_ctx()
    cands = eng.tennis_candidates(ctx, eng.evaluate_tennis(ctx, eng.DEFAULT_PARAMS["tennis"]))
    assert len(cands) == 1
    assert cands[0].key == eng.signal_key("tv1", "tennis", None, "set 1-0")
    assert cands[0].context_at_trigger == "set 1-0 " + eng.MIDDOT + " game 3-0"


# ------------------------------------------- importo abbinabile SUBITO (size)
def test_size_base_lay_sfavorita():
    ev = eng.evaluate_base(ctx_of(with_sizes=True), eng.DEFAULT_PARAMS["base"])
    assert ev.state == "signal"
    assert ev.entry_odds == 8.4
    assert ev.entry_size == 120
    assert check(ev, "dogLay").value == "8.40 " + eng.MIDDOT + " " + eng.EURO + "120 abbinabili"


def test_size_esatto_lay_altro_risultato_anche_decimale():
    ev = eng.evaluate_esatto(ctx_of(with_sizes=True), eng.DEFAULT_PARAMS["esatto"], "home")
    assert ev.state == "signal"
    assert ev.entry_odds == 45
    assert ev.entry_size == 2.25
    assert check(ev, "entry").value == "45.00 " + eng.MIDDOT + " " + eng.EURO + "2.25 abbinabili"


def test_size_punta_back_squadra_in_vantaggio():
    payload = calcio_payload(minute=68, sh=2, sa=0, with_sizes=True)
    payload["odds"] = {
        "home": {"back": 1.06, "lay": 1.07, "back_size": 2500, "lay_size": 300, "selection_id": 1},
        "draw": {"back": 20, "lay": 22, "back_size": 5, "lay_size": 5, "selection_id": 3},
        "away": {"back": 60, "lay": 70, "back_size": 2, "lay_size": 2, "selection_id": 2},
    }
    ctx = eng.build_football_ctx_from_scan("ev9", payload, 50, 60)
    ev = eng.evaluate_punta(ctx, eng.DEFAULT_PARAMS["punta"])
    # stable_since=50 -> 18' dopo l'ultimo gol osservato: assestato
    assert ev.state == "signal"
    assert ev.entry_size == 2500


def test_size_tennis_back_leader_e_lay_perdente_informativo():
    ctx = eng.build_tennis_ctx_from_scan(
        "tv9",
        {
            "event_name": "Rossi v Bianchi", "p1": "Rossi", "p2": "Bianchi",
            "competition": "ATP Rome", "open_date": None, "inplay": True,
            "mo_market_id": "1.9", "mo_status": "OPEN",
            "odds": {
                "p1": {"back": 1.03, "lay": 1.04, "back_size": 812.5, "lay_size": 90},
                "p2": {"back": 20, "lay": 30, "back_size": 4, "lay_size": 6},
            },
            "sets": {"p1": 1, "p2": 0}, "games": {"p1": 3, "p2": 0},
        },
        60,
    )
    ev = eng.evaluate_tennis(ctx, eng.DEFAULT_PARAMS["tennis"])
    assert ev.state == "signal"
    assert ev.entry_size == 812.5
    expected = (
        "back 1.03 " + eng.MIDDOT + " " + eng.EURO + "812.50 abbinabili "
        + eng.MIDDOT + " lay perdente 30.00 " + eng.MIDDOT + " " + eng.EURO + "6 abbinabili"
    )
    assert check(ev, "odds").value == expected


def test_size_fonte_senza_size_entry_size_none():
    ev = eng.evaluate_base(ctx_of(), eng.DEFAULT_PARAMS["base"])
    assert ev.state == "signal"
    assert ev.entry_size is None
    assert check(ev, "dogLay").value == "8.40"


def test_size_quota_assente_niente_size_senza_prezzo():
    payload = calcio_payload()
    payload["odds"] = {
        "home": {"back": 1.28, "lay": 1.3},
        "draw": None,
        "away": {"back": 8, "lay": None, "lay_size": 50},
    }
    ctx = eng.build_football_ctx_from_scan("ev9", payload, 50, 60)
    ev = eng.evaluate_base(ctx, eng.DEFAULT_PARAMS["base"])
    assert ev.entry_odds is None
    assert ev.entry_size is None


def test_size_i_candidati_portano_la_size_nel_segnale():
    ctx = ctx_of(with_sizes=True)
    cands = eng.football_candidates(ctx, [eng.evaluate_base(ctx, eng.DEFAULT_PARAMS["base"])])
    assert cands[0].entry_size == 120


# =========================================================== SafeEngine (API)
# NB: sulla fixture standard (58', 1-0) scattano TRE segnali - Base + Risultato
# Esatto su entrambi i lati - esattamente come certifica il TS ("al 58' anche il
# R.E. e' oltre la sua soglia di 48': entra come secondo candidato").
def keys_of(signals: List[eng.Signal]) -> List[str]:
    return [s.key for s in signals]


def by_variant(signals: List[eng.Signal], variant: str, sub: Optional[str] = None):
    hits = [s for s in signals if s.variant == variant and (sub is None or f":{sub}:" in s.key)]
    return hits[0] if hits else None


def test_engine_evaluate_produce_il_segnale_base_completo():
    clock = FakeClock()
    e = eng.SafeEngine(clock=clock)
    rows = [row("ev1", "calcio", calcio_payload(with_sizes=True))]
    e.evaluate(rows)          # prima osservazione: il punteggio parte adesso
    clock.advance(60)
    signals = e.evaluate(rows)
    assert keys_of(signals) == ["ev1:base:1-0", "ev1:esatto:away:1-0", "ev1:esatto:home:1-0"]
    s = by_variant(signals, "base")
    assert s.key == "ev1:base:1-0"
    assert s.event_id == "ev1"
    assert s.sport == "calcio"
    assert s.variant == "base"
    assert s.market_type == "MATCH_ODDS"
    assert s.market_id == "1.1"
    assert s.selection_id == 2
    assert s.selection_name == "Sud FC"
    assert s.side == "lay"
    assert s.price == 8.4
    assert s.size_available == 120
    assert s.size == eng.DEFAULT_PARAMS["stake"]["laySize"]
    assert s.headline == "BANCA Sud FC"
    assert s.minute == 58
    assert s.score == "1-0"
    assert s.first_seen_ts == clock.t
    assert isinstance(s.checks, tuple) and len(s.checks[0]) == 3


def test_engine_anti_blip_il_segnale_arriva_solo_dopo_la_soglia():
    clock = FakeClock()
    e = eng.SafeEngine(clock=clock)
    rows = [row("ev1", "calcio", calcio_payload())]
    assert e.evaluate(rows) == []            # 0s osservati
    clock.advance(29)
    assert e.evaluate(rows) == []            # 29s < 30s
    clock.advance(2)
    assert by_variant(e.evaluate(rows), "base") is not None    # 31s >= 30s


def test_engine_il_gol_fa_ripartire_il_contatore():
    clock = FakeClock()
    e = eng.SafeEngine(clock=clock)
    e.evaluate([row("ev1", "calcio", calcio_payload())])
    clock.advance(60)
    assert by_variant(e.evaluate([row("ev1", "calcio", calcio_payload())]), "base") is not None
    # gol: 2-0 al 60' -> nuovo punteggio, finestra anti-blip azzerata
    goal = calcio_payload(minute=60, sh=2, sa=0)
    assert e.evaluate([row("ev1", "calcio", goal)]) == []
    clock.advance(31)
    # 2-0 e' nella lista Base (orientata alla favorita) ma NON in quella del
    # R.E.: torna il solo segnale Base, con chiave NUOVA
    assert keys_of(e.evaluate([row("ev1", "calcio", goal)])) == ["ev1:base:2-0"]


def test_engine_first_seen_ts_stabile_tra_le_chiamate():
    clock = FakeClock()
    e = eng.SafeEngine(clock=clock)
    rows = [row("ev1", "calcio", calcio_payload())]
    e.evaluate(rows)
    clock.advance(60)
    first = e.evaluate(rows)[0]
    clock.advance(120)
    later = e.evaluate(rows)[0]
    assert later.first_seen_ts == first.first_seen_ts


def test_engine_segnale_sparito_non_e_piu_attivo():
    clock = FakeClock()
    e = eng.SafeEngine(clock=clock)
    e.evaluate([row("ev1", "calcio", calcio_payload())])
    clock.advance(60)
    assert by_variant(e.evaluate([row("ev1", "calcio", calcio_payload())]), "base") is not None
    # Match Odds sospeso: la Base decade (il R.E. guarda il Correct Score, resta)
    after = e.evaluate([row("ev1", "calcio", calcio_payload(mo_status="SUSPENDED"))])
    assert by_variant(after, "base") is None
    assert "ev1:base:1-0" not in keys_of(after)


def test_engine_tennis_end_to_end_con_tracker():
    clock = FakeClock()
    e = eng.SafeEngine(clock=clock)
    rows = [row("tv1", "tennis", tennis_payload(with_sizes=True))]
    assert e.evaluate(rows) == []
    clock.advance(16)
    sigs = e.evaluate(rows)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.sport == "tennis"
    assert s.variant == "tennis"
    assert s.side == "back"
    assert s.price == 1.03
    assert s.size_available == 812.5
    assert s.selection_id == 1
    assert s.score == "set 1-0 " + eng.MIDDOT + " game 3-0"
    assert s.minute is None


def test_engine_ordine_deterministico_calcio_poi_tennis():
    clock = FakeClock()
    e = eng.SafeEngine(clock=clock)
    rows = [
        row("tv1", "tennis", tennis_payload()),
        row("ev2", "calcio", calcio_payload()),
        row("ev1", "calcio", calcio_payload()),
    ]
    e.evaluate(rows)
    clock.advance(60)
    keys = keys_of(e.evaluate(rows))
    assert keys == [
        "ev1:base:1-0", "ev1:esatto:away:1-0", "ev1:esatto:home:1-0",
        "ev2:base:1-0", "ev2:esatto:away:1-0", "ev2:esatto:home:1-0",
        "tv1:tennis:set 1-0",
    ]
    assert keys == sorted(keys)


def test_engine_evento_sparito_azzera_il_tracker():
    clock = FakeClock()
    e = eng.SafeEngine(clock=clock)
    rows = [row("ev1", "calcio", calcio_payload())]
    e.evaluate(rows)
    clock.advance(60)
    assert by_variant(e.evaluate(rows), "base") is not None
    assert e.evaluate([]) == []          # evento fuori dallo scan
    assert e.evaluate(rows) == []        # ritorna: il contatore riparte da zero
    clock.advance(31)
    assert by_variant(e.evaluate(rows), "base") is not None


def test_engine_evaluations_espone_tutte_le_varianti():
    clock = FakeClock()
    e = eng.SafeEngine(clock=clock)
    rows = [row("ev1", "calcio", calcio_payload()), row("tv1", "tennis", tennis_payload())]
    e.evaluate(rows)
    clock.advance(60)
    evs = e.evaluations(rows)
    assert set(evs) == {"ev1", "tv1"}
    assert [v["variant"] for v in evs["ev1"]] == ["base", "esatto", "esatto", "punta"]
    assert [v["sub_id"] for v in evs["ev1"]] == [None, "home", "away", None]
    assert evs["ev1"][0]["state"] == "signal"
    assert evs["ev1"][3]["state"] == "no"          # punta: margine di 1 gol
    assert [v["variant"] for v in evs["tv1"]] == ["tennis"]
    first_check = evs["ev1"][0]["checks"][0]
    assert set(first_check) == {"id", "label", "value", "ok"}


def test_engine_update_params_cambia_le_decisioni():
    clock = FakeClock()
    e = eng.SafeEngine(clock=clock)
    rows = [row("ev1", "calcio", calcio_payload(minute=54))]
    e.evaluate(rows)
    clock.advance(60)
    assert by_variant(e.evaluate(rows), "base") is None      # 54' < soglia 55'
    e.update_params({"base": {"minuteMin": 50}})
    assert by_variant(e.evaluate(rows), "base") is not None


def test_engine_riga_piu_vecchia_non_sovrascrive_quella_accettata():
    clock = FakeClock()
    e = eng.SafeEngine(clock=clock)
    recent = row("ev1", "calcio", calcio_payload(), "2026-09-09T12:00:10+00:00")
    stale = row("ev1", "calcio", calcio_payload(mo_status="SUSPENDED"), "2026-09-09T12:00:00+00:00")
    e.evaluate([recent])
    clock.advance(60)
    assert by_variant(e.evaluate([recent]), "base") is not None
    # la riga vecchia (mercato sospeso) viene IGNORATA: la Base resta attiva
    assert by_variant(e.evaluate([stale]), "base") is not None


def test_engine_payload_vuoto_non_lancia_e_non_produce_segnali():
    e = eng.SafeEngine()
    assert e.evaluate([{"event_id": "x", "sport": "calcio", "payload": {}}]) == []
    assert e.evaluate([{"event_id": "y", "sport": "tennis", "payload": {}}]) == []
    assert e.evaluate([None, {"sport": "calcio"}]) == []


# ------------------------------------------------------------- formattazioni
@pytest.mark.parametrize(
    "value,expected",
    [(120, eng.EURO + "120"), (2.25, eng.EURO + "2.25"), (812.5, eng.EURO + "812.50"), (None, None)],
)
def test_fmt_eur(value, expected):
    assert eng.fmt_eur(value) == expected


def test_fmt_odds_e_minute():
    assert eng.fmt_odds(8.4) == "8.40"
    assert eng.fmt_odds(None) == "n/d"
    assert eng.fmt_minute(None) == "n/d"
    assert eng.fmt_minute(58) == "58" + eng.PRIME


def test_js_num_stampa_come_javascript():
    assert eng.js_num(4) == "4"
    assert eng.js_num(4.0) == "4"
    assert eng.js_num(1.4) == "1.4"


def test_signal_key_con_e_senza_sub_id():
    assert eng.signal_key("ev1", "base", None, "1-0") == "ev1:base:1-0"
    assert eng.signal_key("ev1", "esatto", "home", "1-0") == "ev1:esatto:home:1-0"
