"""CERTIFICAZIONE NUMERICA del CUORE PROBABILISTICO condiviso (12/09/2026).

Questi test sono la RETE DI SICUREZZA di Omega, Safe Strategy e Mike insieme:
tutti e tre leggono ``live_engine.inplay_residual_rates`` e la griglia aggregata
da ``live_engine_pro._markets_from_residual``. Un errore qui sbaglia i segnali
dei tre bot su soldi veri.

Niente mock: sono calcoli NUMERICI veri, confrontati con le proprieta'
matematiche che le probabilita' devono rispettare per forza.
"""
from __future__ import annotations

import math

import pytest

from Betfair.stream.engine import live_engine as LE
from Betfair.stream.engine import live_engine_pro as LP
from tactical_engine.dixon_coles import dc_tau, score_matrix

LINES = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]
LEAGUES = [None, 135, 4, 39, 99999999]   # note, sconosciute e assenti


def _key(line: float) -> str:
    return str(line).replace(".", "_")


class _GridView:
    """La griglia dict di ``omega_model.residual_grid`` esposta con l'interfaccia
    che ``_markets_from_residual`` usa (stessa classe di safe_strategy)."""

    def __init__(self, grid, n):
        self._g = grid
        self.shape = (n, n)

    def __getitem__(self, ij):
        return self._g.get((ij[0], ij[1]), 0.0)


# ---------------------------------------------------------------------------
# 1. lambda residui: dominio, finitezza, minuto oltre il 90, rossi, parametri assenti
# ---------------------------------------------------------------------------
def test_lambda_residui_sempre_finiti_e_dentro_la_banda():
    """Su TUTTO il dominio operativo i lambda restano finiti e in banda: mai
    negativi, mai infiniti, mai NaN (un NaN qui diventa una griglia di NaN)."""
    for minute in [None, 0, 1, 44, 45, 46, 89, 90, 91, 94, 95, 96, 120, 200]:
        for sh in range(0, 6):
            for sa in range(0, 6):
                for reds in [(0, 0), (1, 0), (0, 1), (2, 1), (3, 3)]:
                    for league in LEAGUES:
                        lh, la = LE.inplay_residual_rates(
                            1.45, 1.20, minute, sh, sa,
                            red_home=reds[0], red_away=reds[1],
                            yellow_home=3, yellow_away=1, league_id=league,
                        )
                        for lam in (lh, la):
                            assert math.isfinite(lam)
                            assert LE.MIN_RESIDUAL_LAMBDA <= lam <= LE.MAX_RESIDUAL_LAMBDA


def test_lambda_residui_non_crescenti_col_minuto_a_punteggio_fermo():
    """A punteggio fermo il tempo puo' solo TOGLIERE gol attesi: i lambda residui
    non possono risalire con il minuto che avanza (dentro i tempi regolamentari
    e nel recupero modellato)."""
    prev_h = prev_a = None
    for minute in range(0, 96):
        lh, la = LE.inplay_residual_rates(1.4, 1.2, minute, 0, 0, league_id=135)
        if prev_h is not None:
            assert lh <= prev_h + 1e-12
            assert la <= prev_a + 1e-12
        prev_h, prev_a = lh, la


def test_recupero_dopo_il_90_decade_a_zero_e_non_resuscita():
    """Il 90'+ NON e' 'partita finita' (i gol del recupero esistono) ma la massa
    residua deve decadere e non tornare mai negativa/positiva dal nulla."""
    w89 = LE.residual_time_weight(89)
    w90 = LE.residual_time_weight(90)
    w93 = LE.residual_time_weight(93)
    assert w90 > 0.0, "al 90' il rischio gol e' ancora vivo"
    assert w90 <= w89 + 1e-12
    assert 0.0 < w93 < w90
    # oltre la finestra di recupero modellata: zero esatto, mai negativo
    for m in (95, 96, 120, 200):
        assert LE.residual_time_weight(m) == 0.0
    # ... e il lambda scende al minimo strutturale, non sotto
    lh, la = LE.inplay_residual_rates(1.4, 1.2, 200, 1, 1, league_id=135)
    assert lh == LE.MIN_RESIDUAL_LAMBDA and la == LE.MIN_RESIDUAL_LAMBDA


def test_zero_a_zero_stato_di_gioco_neutro_e_simmetrico():
    """A 0-0 (e a ogni pareggio) nessuna squadra insegue: moltiplicatori neutri e
    lambda proporzionali ai soli lambda pre-match."""
    for diff_score in [(0, 0), (1, 1), (3, 3)]:
        assert LE.game_state_multipliers(0, 60, 135) == (1.0, 1.0)
        lh, la = LE.inplay_residual_rates(1.4, 1.4, 60, *diff_score, league_id=135)
        assert abs(lh - la) < 1e-12
    # simmetria: scambiando casa/trasferta (lambda e punteggio) i lambda si scambiano
    a = LE.inplay_residual_rates(1.6, 0.9, 70, 2, 0, red_home=1, red_away=0, league_id=135)
    b = LE.inplay_residual_rates(0.9, 1.6, 70, 0, 2, red_home=0, red_away=1, league_id=135)
    assert abs(a[0] - b[1]) < 1e-12 and abs(a[1] - b[0]) < 1e-12


def test_rosso_abbassa_chi_lo_prende_e_alza_l_avversario():
    """Effetto dei ROSSI dai coefficienti calibrati: chi resta in 10 segna meno,
    l'avversario segna di piu'. Direzione, non solo 'non esplode'."""
    base_h, base_a = LE.inplay_residual_rates(1.4, 1.4, 50, 0, 0, league_id=135)
    red_h, red_a = LE.inplay_residual_rates(1.4, 1.4, 50, 0, 0, red_home=1, league_id=135)
    assert red_h < base_h, "la squadra in 10 deve segnare MENO"
    assert red_a > base_a, "l'avversaria in 11 deve segnare DI PIU'"
    # due rossi alla stessa squadra: effetto monotono, sempre in banda
    red2_h, red2_a = LE.inplay_residual_rates(1.4, 1.4, 50, 0, 0, red_home=2, league_id=135)
    assert red2_h < red_h and red2_a > red_a
    for lam in (red2_h, red2_a):
        assert LE.MIN_RESIDUAL_LAMBDA <= lam <= LE.MAX_RESIDUAL_LAMBDA


def test_parametri_assenti_o_sporchi_non_rompono_il_modello():
    """None / NaN / infinito / stringhe: MAI un'eccezione, MAI un NaN in uscita
    (regressione: un lambda o una pressione NaN propagava NaN a tutta la griglia
    dei tre bot)."""
    nan, inf = float("nan"), float("inf")
    casi = [
        dict(prematch_lambda_home=nan, prematch_lambda_away=1.2),
        dict(prematch_lambda_home=inf, prematch_lambda_away=inf),
        dict(prematch_lambda_home=-3.0, prematch_lambda_away=1.2),
        dict(pressure_home=nan, pressure_away=None),
        dict(red_home=None, red_away=None, yellow_home=None, yellow_away=None),
        dict(score_home=None, score_away=None),
    ]
    for extra in casi:
        kw = dict(prematch_lambda_home=1.4, prematch_lambda_away=1.2,
                  minute=55, score_home=1, score_away=0, league_id=135)
        kw.update(extra)
        lh, la = LE.inplay_residual_rates(
            kw.pop("prematch_lambda_home"), kw.pop("prematch_lambda_away"),
            kw.pop("minute"), kw.pop("score_home"), kw.pop("score_away"), **kw,
        )
        assert math.isfinite(lh) and math.isfinite(la)
        assert LE.MIN_RESIDUAL_LAMBDA <= lh <= LE.MAX_RESIDUAL_LAMBDA
        assert LE.MIN_RESIDUAL_LAMBDA <= la <= LE.MAX_RESIDUAL_LAMBDA
    # minuto non numerico -> peso NEUTRO, non un crash
    assert LE.residual_time_weight("boh") == 1.0
    assert LE.residual_time_weight(float("nan")) == 1.0


def test_moltiplicatori_stato_gioco_in_banda_simmetrica():
    """REGRESSIONE: la banda era asimmetrica (leader senza tetto, chaser senza
    pavimento). Con una calibrazione anomala il chaser poteva diventare NEGATIVO
    -> lambda negativo, azzerato in silenzio a valle."""
    for diff in range(-4, 5):
        for minute in (None, 0, 45, 80, 90, 120):
            for league in LEAGUES:
                gh, ga = LE.game_state_multipliers(diff, minute, league)
                for g in (gh, ga):
                    assert LE.STATE_MULT_MIN <= g <= LE.STATE_MULT_MAX
    # calibrazione con segno invertito (scenario di rottura del file esterno)
    veleno = {"leader_per_goal": -9.0, "chaser_per_goal": -9.0, "max_lead": 2, "late_amp": 0.0}
    orig = LE._INTENSITY
    LE._INTENSITY = {"global": {"game_state": veleno}}
    try:
        gh, ga = LE.game_state_multipliers(1, 80, None)
        assert gh >= LE.STATE_MULT_MIN and ga >= LE.STATE_MULT_MIN
        lh, la = LE.inplay_residual_rates(1.4, 1.2, 80, 1, 0, league_id=None)
        assert lh > 0 and la > 0
    finally:
        LE._INTENSITY = orig


# ---------------------------------------------------------------------------
# 2. griglia -> mercati: [0,1], somme a 1, coda troncata, celle negative
# ---------------------------------------------------------------------------
def _griglie_di_prova():
    for lh in (0.05, 0.3, 0.8, 1.5, 2.6):
        for la in (0.05, 0.4, 1.1, 2.0):
            yield lh, la


def test_ogni_probabilita_in_zero_uno_e_famiglie_che_sommano_a_uno():
    for lh, la in _griglie_di_prova():
        for sh in range(0, 4):
            for sa in range(0, 4):
                rho = LP.effective_rho(-0.13, lh, la, sh, sa)
                p = LP._markets_from_residual(score_matrix(lh, la, rho), sh, sa, LINES)
                for k, v in p.items():
                    assert 0.0 <= v <= 1.0, (k, v)
                assert abs(p["home"] + p["draw"] + p["away"] - 1.0) < 1e-12
                assert abs(p["btts_yes"] + p["btts_no"] - 1.0) < 1e-12
                for ln in LINES:
                    somma = p[f"over_{_key(ln)}"] + p[f"under_{_key(ln)}"]
                    assert abs(somma - 1.0) < 1e-12, (ln, somma)


def test_scala_over_under_coerente_e_monotona():
    """P(Over n) NON CRESCENTE in n e P(Under n) NON DECRESCENTE.

    E' la proprieta' su cui si basa la regola delle anomalie di Safe Strategy: se
    la griglia la violasse i bot segnalerebbero incoerenze inesistenti."""
    for lh, la in _griglie_di_prova():
        for sh in range(0, 5):
            for sa in range(0, 5):
                rho = LP.effective_rho(-0.13, lh, la, sh, sa)
                p = LP._markets_from_residual(score_matrix(lh, la, rho), sh, sa, LINES)
                over = [p[f"over_{_key(ln)}"] for ln in LINES]
                under = [p[f"under_{_key(ln)}"] for ln in LINES]
                for i in range(len(LINES) - 1):
                    assert over[i + 1] <= over[i] + 1e-15, (lh, la, sh, sa, LINES[i])
                    assert under[i + 1] >= under[i] - 1e-15, (lh, la, sh, sa, LINES[i])


def test_esiti_gia_decisi_valgono_uno_e_zero_esatti():
    """Totale corrente gia' oltre la linea -> Over = 1 e Under = 0 ESATTI (non
    0.999...): un arrotondamento a 0.999 mostrerebbe un 'edge' inesistente."""
    for lh, la in _griglie_di_prova():
        for sh in range(0, 5):
            for sa in range(0, 5):
                rho = LP.effective_rho(-0.13, lh, la, sh, sa)
                p = LP._markets_from_residual(score_matrix(lh, la, rho), sh, sa, LINES)
                for ln in LINES:
                    if sh + sa > ln:
                        assert p[f"over_{_key(ln)}"] == 1.0
                        assert p[f"under_{_key(ln)}"] == 0.0
                if sh >= 1 and sa >= 1:
                    assert p["btts_yes"] == 1.0 and p["btts_no"] == 0.0


def test_coda_troncata_finisce_nella_rinormalizzazione_di_tutte_le_famiglie():
    """REGRESSIONE: prima solo l'1X2 veniva rinormalizzato sulla massa della
    griglia troncata; Over/Under e BTTS restavano su una scala diversa. Con una
    griglia che somma 0.8 (coda tagliata) le due scale divergevano."""

    class _Troncata:
        shape = (3, 3)

        def __getitem__(self, ij):
            # massa totale 0.8: 0.2 di coda buttata via oltre la griglia
            base = {(0, 0): 0.4, (1, 0): 0.2, (0, 1): 0.1, (1, 1): 0.1}
            return base.get((ij[0], ij[1]), 0.0)

    p = LP._markets_from_residual(_Troncata(), 0, 0, [0.5, 1.5, 2.5])
    assert abs(p["home"] + p["draw"] + p["away"] - 1.0) < 1e-12
    assert abs(p["over_0_5"] + p["under_0_5"] - 1.0) < 1e-12
    # over 0.5 = 1 - P(0,0) sulla massa RINORMALIZZATA = 1 - 0.4/0.8
    assert abs(p["over_0_5"] - 0.5) < 1e-12
    assert abs(p["btts_yes"] - 0.1 / 0.8) < 1e-12


def test_celle_negative_non_producono_probabilita_negative():
    """Con lambda estremi la correzione tau puo' diventare negativa (celle di
    probabilita' negative). Il risultato deve restare una distribuzione valida."""

    class _ConNegativi:
        shape = (2, 2)

        def __getitem__(self, ij):
            return {(0, 0): 0.5, (0, 1): -0.05, (1, 0): 0.3, (1, 1): 0.2}[(ij[0], ij[1])]

    p = LP._markets_from_residual(_ConNegativi(), 0, 0, [0.5, 1.5])
    for v in p.values():
        assert 0.0 <= v <= 1.0
    assert abs(p["home"] + p["draw"] + p["away"] - 1.0) < 1e-12
    assert abs(p["over_1_5"] + p["under_1_5"] - 1.0) < 1e-12


# ---------------------------------------------------------------------------
# 3. Dixon-Coles: solo dove ha senso, e mai con tau negativa
# ---------------------------------------------------------------------------
def test_dixon_coles_solo_a_zero_a_zero():
    """REGRESSIONE (money): la tau e' calibrata sui RISULTATI FINALI bassi. Sui
    gol RESIDUI vale solo se la partita e' ancora 0-0. Prima veniva applicata
    sempre: a 1-1 gonfiava il residuo 1-1 (finale 2-2) e spostava il pareggio di
    ~2,5 punti percentuali, piu' della soglia di segnale (min_edge 0.03)."""
    assert LP.effective_rho(-0.13, 0.7, 0.6, 0, 0) == -0.13
    for sh, sa in [(1, 0), (0, 1), (1, 1), (2, 1), (3, 3)]:
        assert LP.effective_rho(-0.13, 0.7, 0.6, sh, sa) == 0.0
    # rho nullo -> tau neutra su tutte e quattro le celle basse
    for x, y in ((0, 0), (0, 1), (1, 0), (1, 1)):
        assert dc_tau(x, y, 0.7, 0.6, 0.0) == 1.0


def test_dixon_coles_spento_se_tau_diventa_negativa():
    """tau(0,1) = 1 + lam_home*rho: con lam grande e rho negativo diventa < 0."""
    assert dc_tau(0, 1, 9.0, 1.0, -0.13) < 0.0
    assert LP.effective_rho(-0.13, 9.0, 1.0, 0, 0) == 0.0
    g = score_matrix(9.0, 1.0, LP.effective_rho(-0.13, 9.0, 1.0, 0, 0))
    assert float(g.min()) >= 0.0, "nessuna cella negativa nella griglia usata"


def test_stessa_griglia_di_omega_e_safe_strategy():
    """I tre bot devono vedere gli STESSI numeri: a parita' di lambda e rho la
    griglia del motore live deve coincidere con ``omega_model.residual_grid``
    (che applica la tau solo a 0-0). Prima divergevano fuori dallo 0-0."""
    import Betfair.omega.omega_model as M

    for lh, la in ((0.7, 0.55), (1.3, 1.1), (0.2, 0.9)):
        for sh, sa in ((0, 0), (1, 0), (1, 1), (2, 1)):
            dc = (sh == 0 and sa == 0)
            mine = LP._markets_from_residual(
                score_matrix(lh, la, LP.effective_rho(-0.13, lh, la, sh, sa), 10),
                sh, sa, LINES,
            )
            omega = LP._markets_from_residual(
                _GridView(M.residual_grid(lh, la, -0.13, 10, dixon_coles=dc), 11),
                sh, sa, LINES,
            )
            for k in mine:
                assert abs(mine[k] - omega[k]) < 1e-9, (lh, la, sh, sa, k)


# ---------------------------------------------------------------------------
# 4. hazard gol imminente
# ---------------------------------------------------------------------------
def test_hazard_dominio_monotonia_e_orizzonte_dichiarato_onesto():
    base = dict(prematch_lambda_home=1.4, prematch_lambda_away=1.2, league_id=135)
    for minute in range(1, 95):
        hz = LP.event_goal_hazard(score_home=0, score_away=0, minute=minute, **base)
        if hz is None:
            continue
        assert 0.0 <= hz["p_next"] <= 1.0
        assert hz["exp_goals_next"] >= 0.0
        assert abs(hz["p_next"] - (1.0 - math.exp(-hz["exp_goals_next"]))) < 1e-3
    # orizzonte piu' lungo -> hazard non minore
    a = LP.event_goal_hazard(score_home=0, score_away=0, minute=30, horizon_min=2.0, **base)
    b = LP.event_goal_hazard(score_home=0, score_away=0, minute=30, horizon_min=10.0, **base)
    assert b["p_next"] >= a["p_next"]
    # ONESTA': l'orizzonte dichiarato e' quello davvero usato (la CDF e' al minuto)
    c = LP.event_goal_hazard(score_home=0, score_away=0, minute=30, horizon_min=2.4, **base)
    assert c["horizon_min"] == 2.0
    assert c["p_next"] == a["p_next"]
    # tempo (modello) esaurito -> None, mai un hazard inventato
    assert LP.event_goal_hazard(score_home=1, score_away=1, minute=120, **base) is None


# ---------------------------------------------------------------------------
# 5. evaluate_event end-to-end: scala coerente sui mercati REALI
# ---------------------------------------------------------------------------
def _ou(line_key: str, line_name: str, sel_under: int, sel_over: int):
    return {
        "market_id": f"1.{line_key}", "market_type": f"OVER_UNDER_{line_key}",
        "selections": [
            {"selection_id": sel_under, "name": f"Under {line_name} Goals", "sort_priority": 1},
            {"selection_id": sel_over, "name": f"Over {line_name} Goals", "sort_priority": 2},
        ],
    }


def _lad(back: float, lay: float, size: float = 50.0):
    return {"back": [[back, size]], "lay": [[lay, size]], "ltp": back, "tv": 500.0}


@pytest.mark.parametrize("sh,sa,minute", [(0, 0, 5), (1, 0, 40), (1, 1, 62), (3, 1, 80)])
def test_scala_ou_coerente_sui_segnali_del_motore(sh, sa, minute):
    """La scala Over/Under vista dall'UTENTE (model_prob dei segnali) deve
    restare monotona linea per linea, altrimenti i bot vedono anomalie finte."""
    righe = [("05", "0.5"), ("15", "1.5"), ("25", "2.5"), ("35", "3.5"),
             ("45", "4.5"), ("55", "5.5"), ("65", "6.5")]
    markets, ladder = [], {}
    for i, (k, n) in enumerate(righe):
        u, o = 100 + 2 * i, 101 + 2 * i
        markets.append(_ou(k, n, u, o))
        ladder[f"1.{k}"] = {str(u): _lad(2.0, 2.02), str(o): _lad(2.0, 2.02)}
    sigs = LP.evaluate_event(
        score_home=sh, score_away=sa, minute=minute,
        prematch_lambda_home=1.4, prematch_lambda_away=1.2, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    by_sel = {s.selection_id: s for s in sigs}
    over = [by_sel[101 + 2 * i].model_prob for i in range(len(righe))]
    under = [by_sel[100 + 2 * i].model_prob for i in range(len(righe))]
    for i in range(len(righe) - 1):
        assert over[i + 1] <= over[i] + 1e-9, (righe[i], over)
        assert under[i + 1] >= under[i] - 1e-9, (righe[i], under)
    for i in range(len(righe)):
        assert abs(over[i] + under[i] - 1.0) < 1e-3
        # linea gia' superata dal punteggio corrente: certezza, non stima
        if sh + sa > float(righe[i][1]):
            assert over[i] == 1.0 and under[i] == 0.0


def test_nessun_segnale_su_mercato_gia_deciso():
    """Over 0.5 con 3 gol gia' fatti: il mercato e' deciso, nessuna direzione
    azionabile (dal vivo e' sospeso: un 'soldi gratis' sarebbe finto)."""
    markets = [_ou("05", "0.5", 100, 101)]
    ladder = {"1.05": {"100": _lad(50.0, 100.0), "101": _lad(1.01, 1.02)}}
    sigs = LP.evaluate_event(
        score_home=2, score_away=1, minute=70,
        prematch_lambda_home=1.2, prematch_lambda_away=1.0, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    assert {s.direction for s in sigs} == {"HOLD"}
    assert all(s.edge is None for s in sigs)


def test_gate_liquidita_blocca_il_segnale_senza_controparte():
    markets = [_ou("25", "2.5", 100, 101)]
    # size 1 EUR al miglior prezzo: nessuna controparte vera
    ladder = {"1.25": {"100": _lad(1.2, 1.22, size=1.0), "101": _lad(8.0, 9.0, size=1.0)}}
    comune = dict(score_home=0, score_away=0, minute=70,
                  prematch_lambda_home=1.4, prematch_lambda_away=1.2, league_id=135,
                  markets=markets, ladder_by_market=ladder)
    con_liq = LP.evaluate_event(min_liquidity=0.0, **comune)
    senza_liq = LP.evaluate_event(min_liquidity=20.0, **comune)
    assert any(s.direction != "HOLD" for s in con_liq)
    assert all(s.direction == "HOLD" for s in senza_liq)
    # l'edge resta calcolato e mostrato: si blocca l'AZIONE, non la trasparenza
    assert any(s.edge is not None for s in senza_liq)
