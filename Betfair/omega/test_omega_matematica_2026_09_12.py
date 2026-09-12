"""CERTIFICAZIONE MATEMATICA OMEGA — 12/09/2026.

Regressioni dei difetti trovati certificando riga per riga la matematica di
Omega (modello, mercato, empirica, banco, consulente, report liquidità).

Filo conduttore: **ovunque una probabilità nasca da un PREZZO, quel prezzo deve
essere liquido e plausibile**. Un'offerta-civetta da 2 € non deve poter
spostare i λ del modello, e nessun numero non finito (NaN/inf) deve poter
attraversare un filtro di sicurezza o finire in un ordine reale.
"""
from __future__ import annotations

import math

import pytest

from Betfair.omega import liquidity_probe as LP
from Betfair.omega import omega_advisor as AD
from Betfair.omega import omega_empirical as EMP
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as MK
from Betfair.omega import omega_model as M

RHO = M.DEFAULT_RHO
ST = M.LiveState(minute=60, score_home=0, score_away=0)


# ---------------------------------------------------------------------------
# helper: book Correct Score COERENTE generato da λ residui noti
# ---------------------------------------------------------------------------
def _cs_book(lh: float, la: float, *, size: float = 50.0, overround: float = 1.10,
             extra=None, drop=()):
    grid = M.residual_grid(lh, la, RHO, 10, dixon_coles=True)
    sels, listed = [], []
    for h in range(4):
        for a in range(4):
            p = grid[(h, a)] * overround
            sels.append({"selection_id": 100 * h + a, "name": f"{h} - {a}", "runner_status": "ACTIVE",
                         "back": round(1.0 / (p * 0.98), 2), "lay": round(1.0 / (p * 1.02), 2),
                         "back_size": size, "lay_size": size})
            listed.append((h, a))
    for kind, label in (("home", "Any Other Home Win"), ("away", "Any Other Away Win"),
                        ("draw", "Any Other Draw")):
        p = max(sum(v for (h, a), v in grid.items() if (h, a) not in listed and (
            (kind == "home" and h > a) or (kind == "away" and a > h) or (kind == "draw" and h == a))), 1e-4) * overround
        sels.append({"selection_id": 900 + len(sels), "name": label, "runner_status": "ACTIVE",
                     "back": round(1.0 / (p * 0.98), 2), "lay": round(1.0 / (p * 1.02), 2),
                     "back_size": size, "lay_size": size})
    sels = [s for s in sels if s["name"] not in drop]
    if extra:
        sels.append(extra)
    return {"cs": {"status": "OPEN", "market_id": "m-cs", "selections": sels}, "ou": []}


def _ou_block(line, over, under, *, size=50.0, status="OPEN"):
    return {"line": line, "status": status, "selections": [
        {"name": f"Over {line} Goals", "runner_status": "ACTIVE", "back": over, "lay": over + 0.1,
         "back_size": size, "lay_size": size},
        {"name": f"Under {line} Goals", "runner_status": "ACTIVE", "back": under, "lay": under + 0.02,
         "back_size": size, "lay_size": size}]}


class _R:
    """ScoreRunner minimale per select_by_model."""

    def __init__(self, sid, name, lay_price, lay_size, back_price=None, back_size=None):
        self.selection_id, self.name = sid, name
        self.lay_price, self.lay_size = lay_price, lay_size
        self.back_price, self.back_size = back_price, back_size


# ---------------------------------------------------------------------------
# 1. Un prezzo senza liquidità non è una probabilità
# ---------------------------------------------------------------------------
def test_quote_p_richiede_prezzo_vero_e_liquidita():
    assert M.quote_p(50.0, 50.0) == pytest.approx(0.02)
    assert M.quote_p(50.0, M.MARKET_QUOTE_MIN_SIZE) == pytest.approx(0.02)   # bordo incluso
    assert M.quote_p(50.0, M.MARKET_QUOTE_MIN_SIZE - 0.01) is None           # civetta
    assert M.quote_p(50.0, None) is None                                     # size assente = zero
    assert M.quote_p(50.0, 0.0) is None
    assert M.quote_p(1.0, 100.0) is None                                     # quota impossibile
    assert M.quote_p(float("nan"), 100.0) is None
    assert M.quote_p(50.0, float("nan")) is None
    assert M.quote_p(None, 100.0) is None


def test_civetta_da_2_euro_non_sposta_piu_i_lambda_del_mercato():
    """Prima del 12/09: una SOLA offerta back da 2 € sullo 0-0 (senza controparte)
    veniva letta come un vincolo PUNTUALE p(0-0) = 1/1,2 = 0,83 e i λ del mercato
    crollavano da (0,562; 0,440) a (0,380; 0,312): P(3-1) passava da 0,48 % a
    0,14 %, cioè un risultato 3,4× più probabile di quanto il modello credesse —
    e Omega lo avrebbe bancato con soldi veri. Ora quel prezzo non vincola il fit
    e l'overround che produce (1,65) e' fuori scala: nessun λ di mercato."""
    civetta = _cs_book(0.55, 0.45, drop=("0 - 0",), extra={
        "selection_id": 77, "name": "0 - 0", "runner_status": "ACTIVE",
        "back": 1.2, "lay": None, "back_size": 2.0, "lay_size": 0.0})
    assert M.market_cs_brackets(civetta, ST) == ({}, [])
    assert M.lambdas_from_market_grid(civetta, ST, None) is None


def test_quota_unilaterale_non_vincola_il_fit_ma_pesa_nella_devig():
    """Una longshot con il solo lato back resta nella normalizzazione (la devig
    ha senso solo sul book intero) ma non impone nessun vincolo al fit: i λ
    restano quelli del book pulito."""
    cells0, aggs0 = M.market_cs_brackets(_cs_book(0.55, 0.45), ST)
    pulito = M.fit_residual_lambdas_to_market(cells0, {}, ST, RHO, aggs=aggs0)
    monco = _cs_book(0.55, 0.45)
    for s_ in monco["cs"]["selections"]:
        if s_["name"] == "3 - 3":
            s_["lay"], s_["lay_size"] = None, 0.0
    cells, aggs = M.market_cs_brackets(monco, ST)
    assert (3, 3) not in cells and (2, 2) in cells
    dopo = M.fit_residual_lambdas_to_market(cells, {}, ST, RHO, aggs=aggs)
    assert abs(dopo[0] - pulito[0]) < 0.02 and abs(dopo[1] - pulito[1]) < 0.02


def test_scala_cs_incompleta_o_implausibile_non_produce_lambda():
    """Se restano troppo pochi risultati a due lati liquidi, o l'overround della
    scala è implausibile, si rinuncia al λ di mercato: mai un numero inventato."""
    tutte_civetta = _cs_book(0.55, 0.45, size=1.0)          # nessun lato liquido
    assert M.market_cs_brackets(tutte_civetta, ST) == ({}, [])
    assert M.lambdas_from_market_grid(tutte_civetta, ST, None) is None
    # troppe celle senza controparte: restano meno di MARKET_GRID_MIN_CS vincoli
    mezzo = _cs_book(0.55, 0.45)
    for s_ in mezzo["cs"]["selections"][:14]:
        s_["lay"], s_["lay_size"] = None, 0.0
    assert M.market_cs_brackets(mezzo, ST) == ({}, [])
    # overround fuori scala (book "a somma 2"): nessun lambda di mercato
    gonfia = _cs_book(0.55, 0.45, overround=2.0)
    assert M.market_cs_brackets(gonfia, ST) == ({}, [])
    assert M.lambdas_from_market_grid(gonfia, ST, None) is None


def test_quota_lay_civetta_su_cella_centrale_non_diventa_un_lambda():
    """Un lay a 1000 con 2 € (nessun back) sull'1-1 toglieva la cella centrale
    dai vincoli senza far scattare nessuna guardia: il fit finiva sul fondo
    scala (λ_trasferta 0,020) e P(3-1) crollava da 0,46 % a 0,008 %. Ora il fit
    NON riproduce il book (loss 0,68 > MARKET_FIT_MAX_LOSS) e si rinuncia."""
    b = _cs_book(0.55, 0.45, drop=("1 - 1",))
    b["cs"]["selections"].append({"selection_id": 77, "name": "1 - 1", "runner_status": "ACTIVE",
                                  "back": None, "lay": 1000.0, "back_size": 0.0, "lay_size": 2.0})
    cells, aggs = M.market_cs_brackets(b, ST)
    assert (1, 1) not in cells
    assert M.fit_residual_lambdas_to_market(cells, {}, ST, RHO, aggs=aggs)[2] > M.MARKET_FIT_MAX_LOSS
    assert M.lambdas_from_market_grid(b, ST, None) is None


def test_fit_ricostruisce_i_lambda_veri_da_un_book_coerente():
    cells, aggs = M.market_cs_brackets(_cs_book(0.55, 0.45), ST)
    lh, la, loss = M.fit_residual_lambdas_to_market(cells, {}, ST, RHO, aggs=aggs)
    assert abs(lh - 0.55) < 0.05 and abs(la - 0.45) < 0.05 and loss < 0.01


# ---------------------------------------------------------------------------
# 2. Linee Over/Under: liquidità e linea davvero a mezzo gol
# ---------------------------------------------------------------------------
def test_ou_senza_liquidita_non_da_lambda():
    liquido = {"ou": [_ou_block(2.5, 6.0, 1.18)]}
    assert M.residual_total_from_ou(liquido, ST) is not None
    civetta = {"ou": [_ou_block(2.5, 6.0, 1.18, size=1.0)]}
    assert M.residual_total_from_ou(civetta, ST) is None
    assert M.lambdas_from_live_ou(civetta, ST, None) is None
    assert M.market_ou_probs(civetta, ST) == {}


def test_linea_ou_non_a_mezzo_gol_ignorata():
    """``int(2.0 - 0.5)`` valeva 1: la linea 2,0 veniva letta come la 1,5."""
    assert M._is_half_line(2.5) and not M._is_half_line(2.0) and not M._is_half_line(2.25)
    assert M.market_ou_probs({"ou": [_ou_block(2.0, 6.0, 1.18)]}, ST) == {}
    assert M.residual_total_from_ou({"ou": [_ou_block(2.0, 6.0, 1.18)]}, ST) is None
    # la 2,5 con 0 gol segnati e' la linea "residuo >= 3", cioe' k = 2
    assert list(M.market_ou_probs({"ou": [_ou_block(2.5, 6.0, 1.18)]}, ST)) == [2]
    # con 1 gol gia' segnato la stessa linea diventa "residuo >= 2" (k = 1)
    st1 = M.LiveState(minute=60, score_home=1, score_away=0)
    assert list(M.market_ou_probs({"ou": [_ou_block(2.5, 6.0, 1.18)]}, st1)) == [1]


# ---------------------------------------------------------------------------
# 3. Selezione: banda di P equivalente, NaN, filtri
# ---------------------------------------------------------------------------
def _probs(**over):
    base = {(3, 1): 0.002, (2, 2): 0.010, (0, 3): 0.002}
    base.update(over)
    return base


def test_banda_p_equivalente_applicata_al_ranking_ev():
    """`select_p_band_ratio` (costituzione §15.4, esposto dalla UI) era un
    argomento INERTE: il ranking per EV poteva scegliere un risultato 5× più
    probabile del più raro solo perché costava meno coprirlo."""
    runners = [
        _R(1, "3 - 1", 120.0, 200.0, back_price=110.0, back_size=200.0),   # p 0.002, copertura cara
        _R(2, "2 - 2", 25.0, 200.0, back_price=24.0, back_size=200.0),     # p 0.010, liability bassa -> EV migliore
    ]
    kw = dict(state=ST, price_min=20.0, price_max=200.0, min_liquidity=5.0, p_max=0.02,
              size_needed=6.0, min_goal_distance=2, cost_aware=True, commission=0.05)
    largo = M.select_by_model(runners, _probs(), band_ratio=10.0, **kw)
    stretto = M.select_by_model(runners, _probs(), band_ratio=1.0, **kw)
    assert largo.name == "2 - 2"      # senza banda vince l'EV (risultato più probabile)
    assert stretto.name == "3 - 1"    # con la banda vince il risultato PIÙ RARO
    assert M._p_band([], 2.0) == []


def test_size_lay_non_finita_non_passa_il_filtro_di_liquidita():
    """``nan < need`` è False: una size NaN superava il filtro di liquidità e il
    runner diventava candidato con liquidità indefinita."""
    nan_runner = [_R(1, "3 - 1", 100.0, float("nan"), back_price=95.0, back_size=50.0)]
    assert M.select_by_model(nan_runner, _probs(), state=ST, price_min=20.0, price_max=200.0,
                             min_liquidity=5.0, p_max=0.02, size_needed=6.0) is None


def test_prezzo_lay_non_finito_scartato():
    assert M.select_by_model([_R(1, "3 - 1", float("nan"), 500.0)], _probs(), state=ST,
                             price_min=20.0, price_max=200.0, min_liquidity=5.0, p_max=0.02) is None


def test_back_non_finito_non_avvelena_il_costo_di_copertura():
    assert M.cover_cost(6.0, 100.0, float("nan")) is None
    assert M.cover_cost(6.0, float("nan"), 90.0) is None
    assert M.cover_cost(float("nan"), 100.0, 90.0) is None
    assert M.cover_cost(6.0, 100.0, 90.0) == pytest.approx(0.67, abs=0.005)   # 6·(100/90−1)
    sel = M.select_by_model([_R(1, "3 - 1", 100.0, 500.0, back_price=float("nan"),
                                back_size=float("inf"))],
                            _probs(), state=ST, price_min=20.0, price_max=200.0,
                            min_liquidity=5.0, p_max=0.02, size_needed=6.0, cost_aware=True)
    assert sel is not None and sel.back_price is None and sel.back_size is None


def test_soglia_di_valore_con_commissione_a_mano():
    """p_implied = (1−c)/(L−c): a L = 20 e c = 5 % vale 0,95/19,95 = 4,7619 %."""
    sel = M.select_by_model([_R(1, "3 - 1", 20.0, 500.0)], _probs(), state=ST,
                            price_min=20.0, price_max=200.0, min_liquidity=5.0,
                            p_max=0.02, commission=0.05)
    assert sel.p_implied == pytest.approx(0.95 / 19.95, rel=1e-12)
    assert sel.p_model == pytest.approx(0.002, rel=1e-12)    # tail_factor 1 = nessuna correzione


# ---------------------------------------------------------------------------
# 4. Griglia, coda, incertezza: invarianti numeriche
# ---------------------------------------------------------------------------
def test_griglia_e_sempre_una_distribuzione():
    for cv in (0.0, 0.30, 1.0):
        g = M.residual_grid(0.7, 0.6, RHO, 10, dixon_coles=True, cv=cv)
        assert abs(sum(g.values()) - 1.0) < 1e-12
        assert all(0.0 <= p <= 1.0 for p in g.values())
    # l'incertezza sui λ ingrassa la coda (mai la assottiglia)
    senza = M.residual_grid(0.7, 0.6, RHO, 10, dixon_coles=True)
    con = M.residual_grid(0.7, 0.6, RHO, 10, dixon_coles=True, cv=0.30)
    assert con[(3, 3)] > senza[(3, 3)]


def test_score_probs_traslate_sul_punteggio_corrente():
    st = M.LiveState(minute=70, score_home=2, score_away=1)
    p = M.score_probs(lh_pre=1.4, la_pre=1.1, rho=RHO, state=st, league_id=None, half=False)
    assert abs(sum(p.values()) - 1.0) < 1e-9
    assert all(h >= 2 and a >= 1 for (h, a) in p)         # mai un risultato irraggiungibile


def test_fattore_di_coda_continuo_e_monotono():
    f0, pmax = 1.3, M.TAIL_P_MAX
    assert M.apply_tail_factor(pmax, f0) == pytest.approx(pmax * (1.0 + f0) / 2.0)
    prev = -1.0
    for i in range(1, 400):
        q = M.apply_tail_factor(i / 1000.0, f0)
        assert q > prev
        prev = q
    assert M.apply_tail_factor(0.01, float("nan")) == 0.01
    assert M.apply_tail_factor(0.01, 0.0) == 0.01


def test_uncertainty_p_pool_logaritmico():
    centre, prudent = M.uncertainty_p([0.01, 0.04], k_se=1.0)
    assert centre == pytest.approx(math.sqrt(0.01 * 0.04))
    assert prudent > centre
    assert M.uncertainty_p([], k_se=1.0) == (0.0, 0.0)
    assert M.uncertainty_p([float("nan")], k_se=1.0) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# 5. Empirica: campioni piccoli mai spacciati per certezze
# ---------------------------------------------------------------------------
def test_wilson_regola_del_tre_a_zero_successi():
    # k = 0, n = 200, z = 1,64 -> z²/(n+z²) = 2,6896/202,6896 = 0,013269
    assert EMP.p_upper(0, 200) == pytest.approx(2.6896 / 202.6896, rel=1e-6)
    assert EMP.p_upper(0, 200) > 0.0
    assert EMP.p_upper(5, 0) == 1.0                    # nessun campione = nessuna certezza
    assert EMP.p_upper(200, 200) == 1.0


def test_shrunk_upper_senza_campione_globale_non_esplode():
    assert EMP.shrunk_upper(0, 10, 0, 0) == 1.0        # prima: ZeroDivisionError
    # con 10 casi di lega e 200 globali il limite resta vicino al globale
    assert EMP.shrunk_upper(0, 10, 2, 200) == pytest.approx(EMP.p_upper(2, 200), abs=0.01)


def test_stato_troppo_raro_non_parla():
    rows = [{"league_id": 0, "ht": "1-0", "ft": "1-0", "n": 50}]
    assert EMP.EmpiricalTable(rows).p_ft_given_ht((1, 0), (1, 0)) is None   # < MIN_GLOBAL_N


# ---------------------------------------------------------------------------
# 6. Mercato REST: back con size, ordini mai a prezzo/size non validi
# ---------------------------------------------------------------------------
def _book(lay, lay_size, back, back_size):
    return {"marketId": "1.1", "status": "OPEN", "inplay": True, "runners": [
        {"selectionId": 7, "status": "ACTIVE", "ex": {
            "availableToLay": [{"price": lay, "size": lay_size}],
            "availableToBack": [{"price": back, "size": back_size}]}}]}


def test_snapshot_rest_porta_anche_la_size_del_back():
    mk = MK.CorrectScoreMarket("1.1", "e1", "A v B", None, {7: "3 - 1"})
    snap = MK._snapshot_from_book(mk, _book(100.0, 40.0, 90.0, 12.0))
    r = snap.runners[0]
    assert r.back_price == 90.0 and r.back_size == 12.0
    # livello back senza size o non finito = nessuna liquidità
    r2 = MK._snapshot_from_book(mk, _book(100.0, 40.0, 90.0, 0.0)).runners[0]
    assert r2.back_price is None and r2.back_size == 0.0
    r3 = MK._snapshot_from_book(mk, _book(100.0, 40.0, float("inf"), 10.0)).runners[0]
    assert r3.back_price is None


@pytest.mark.parametrize("size", [0.0, -1.0, float("nan"), float("inf"), 0.004, "x"])
def test_place_order_live_rifiuta_size_non_valide_senza_toccare_betfair(monkeypatch, size):
    chiamate = []
    monkeypatch.setattr(MK, "call_mutating", lambda fn: chiamate.append(fn) or {})
    with pytest.raises(ValueError):
        MK.place_order_live(market_id="1.1", selection_id=7, price=50.0, size=size, event_id="e1")
    assert chiamate == []


@pytest.mark.parametrize("price", [float("nan"), float("inf")])
def test_place_order_live_rifiuta_prezzi_non_finiti(monkeypatch, price):
    chiamate = []
    monkeypatch.setattr(MK, "call_mutating", lambda fn: chiamate.append(fn) or {})
    with pytest.raises(ValueError):
        MK.place_order_live(market_id="1.1", selection_id=7, price=price, size=5.0, event_id="e1")
    assert chiamate == []


def test_place_order_live_arrotonda_al_tick_valido(monkeypatch):
    visti = {}

    def _fake(fn):
        class _C:
            def place_orders(self, market_id, instrs, **kw):
                visti["instr"] = instrs[0]
                return {"status": "SUCCESS", "instructionReports": [
                    {"status": "SUCCESS", "orderStatus": "EXECUTION_COMPLETE",
                     "betId": "b1", "sizeMatched": 5.0, "averagePriceMatched": 50.0}]}
        return fn(_C())

    monkeypatch.setattr(MK, "call_mutating", _fake)
    res = MK.place_order_live(market_id="1.1", selection_id=7, price=49.9, size=5.004, event_id="e1")
    assert res.ok and visti["instr"]["limitOrder"]["price"] == E.round_to_tick(49.9) == 50.0
    assert visti["instr"]["limitOrder"]["size"] == 5.0


# ---------------------------------------------------------------------------
# 7. Consulente e report liquidità
# ---------------------------------------------------------------------------
def test_advisor_dc_tau_mai_negativo_e_niente_probabilita_nan():
    # con rho positivo grande la cella (0,0) sarebbe 1 − λh·λa·ρ < 0
    assert AD._dc_tau(0, 0, 2.0, 2.0, 0.5) == 0.0
    assert AD._dc_tau(1, 1, 0.0, 0.0, 1.5) == 0.0
    p = AD.score_grid_prob(1.4, 1.2, 0.5, 0, 0, 10)
    assert p is not None and 0.0 <= p <= 1.0
    assert AD.score_grid_prob(float("nan"), 1.2, -0.13, 1, 0, 10) is None
    assert AD.poisson_score_prob({"lambda_home": float("nan"), "lambda_away": 1.0}, 1, 0, half=False) is None


def test_report_liquidita_scarta_le_quote_non_numeriche():
    righe = [{"ts": 1.0, "event_id": "e1", "blk": "cs", "name": "A v B", "minute": 60,
              "sh": 0, "sa": 0, "sel": [
                  {"sid": 1, "name": "2 - 0", "st": "ACTIVE", "lay": float("nan"), "ls": 40},
                  {"sid": 2, "name": "2 - 1", "st": "ACTIVE", "lay": "60", "ls": 40},
                  {"sid": 3, "name": "3 - 0", "st": "ACTIVE", "lay": 60.0, "ls": 40}]}]
    obs = LP.eligible_observations(righe)
    assert sorted(o.sel_name for o in obs) == ["2 - 1", "3 - 0"]   # NaN fuori, stringa convertita
    # una riga senza punteggio completo non deve rompere il report dei green-up
    assert LP.greenup_cases(righe + [{"ts": 2.0, "event_id": "e1", "blk": "cs", "sh": 1,
                                      "sa": None, "sel": []}]) == []


def test_greenup_need_a_mano():
    # 6 € layati a 100 coperti a 90: servono 6·100/90 = 6,67 €, perdita 0,67 €
    assert LP.greenup_need(6.0, 100.0, 90.0) == (6.67, 0.67)


# ===========================================================================
# CERTIFICAZIONE DEL P&L MOSTRATO IN UI — 12/09/2026
# Riscontro incrociato con Betfair/tools/verifica_pnl_2026_09_12.py sul DB reale
# (omega_trades: 80 righe, totale storico -19,46 EUR).
# ===========================================================================
from datetime import datetime, timezone      # noqa: E402

from Betfair.omega import omega_engine as _OE     # noqa: E402

_DAY = datetime(2026, 9, 11, 22, 0, tzinfo=timezone.utc)   # mezzanotte Europe/Rome


def _riga(tid, status, pnl, placed, **kw):
    r = {"id": tid, "event_id": kw.pop("ev", "e%d" % tid), "status": status,
         "pnl": pnl, "placed_at": placed, "liability": kw.pop("liab", 0.0),
         "meta": kw.pop("meta", {}), "side": "lay"}
    r.update(kw)
    return r


def test_una_posizione_APERTA_non_entra_mai_nel_realizzato():
    """Il P&L realizzato conta SOLO gli esiti gia' decisi: un 'open' con una
    liability di 100 EUR non deve spostare ne' il totale ne' la giornata."""
    rows = [_riga(1, "won", 2.57, "2026-09-12T08:00:00+00:00"),
            _riga(2, "open", 0.0, "2026-09-12T08:10:00+00:00", liab=100.0),
            _riga(3, "pending", 0.0, "2026-09-12T08:20:00+00:00", liab=50.0)]
    agg = _OE.aggregate_trades(rows, day_start=_DAY)
    assert agg["realized_profit"] == 2.57
    assert agg["realized_today"] == 2.57
    assert agg["open_liability"] == 100.0, "il 'pending' senza bet_id non e' a mercato"


def test_la_gamba_di_CHIUSURA_sta_nel_giorno_della_sua_apertura():
    """Caso reale: un green-up piazzato dopo mezzanotte non deve spostare sul
    giorno nuovo il P&L di una posizione aperta il giorno prima."""
    rows = [_riga(1, "lost", -11.20, "2026-09-11T10:00:00+00:00", ev="e1"),
            _riga(2, "won", 4.60, "2026-09-12T00:30:00+00:00", ev="e1",
                  closes_trade_id=1, side="back")]
    agg = _OE.aggregate_trades(rows, day_start=_DAY)
    assert agg["realized_profit"] == -6.60
    assert agg["realized_today"] == 0.0, "la chiusura eredita il giorno dell'apertura"
    assert agg["legs_today"] == 0 and agg["events_today"] == 0


def test_la_chiusura_non_conta_come_posizione_indipendente():
    rows = [_riga(1, "won", 2.16, "2026-09-12T08:00:00+00:00", ev="e1"),
            _riga(2, "lost", -24.24, "2026-09-12T08:30:00+00:00", ev="e1",
                  closes_trade_id=1, side="back")]
    agg = _OE.aggregate_trades(rows, day_start=_DAY)
    assert agg["realized_today"] == -22.08
    assert agg["legs_today"] == 1, "una posizione, non due"
    assert agg["events_today"] == 1
    # V/P si contano sul segno della POSIZIONE (apertura + chiusure), non della gamba
    assert (agg["won_today"], agg["lost_today"]) == (0, 1)


def test_void_vale_zero_e_non_sposta_il_pnl():
    rows = [_riga(1, "void", 0.0, "2026-09-12T08:00:00+00:00")]
    agg = _OE.aggregate_trades(rows, day_start=_DAY)
    assert agg["realized_profit"] == 0.0 and agg["realized_today"] == 0.0


def test_copertura_completa_azzera_il_rischio_e_isola_il_bloccato():
    """A copertura completa la liability aperta e' ZERO (la perdita e' gia'
    fatta) e il risultato bloccato si legge a parte: mai sommato al rischio."""
    rows = [_riga(1, "hedged", 0.0, "2026-09-12T08:00:00+00:00", liab=116.64,
                  meta={"locked_pnl": -22.10, "residual_size": 0.0,
                        "hedged_size": 2.16, "if_win": -22.10})]
    agg = _OE.aggregate_trades(rows, day_start=_DAY)
    assert agg["open_liability"] == 0.0
    assert agg["locked_pnl_open"] == -22.10
    assert agg["locked_pnl_open_today"] == -22.10
    # guardie: la perdita bloccata pesa subito sullo stop giornaliero
    assert _OE.realized_effective(agg) == -22.10
    # ...e il cap di esposizione non si libera per un green-up in perdita
    assert _OE.open_liability_effective(agg) == 22.10


def test_il_bloccato_di_omega_e_LORDO_mentre_il_realizzato_e_NETTO():
    """DIFETTO CERTIFICATO 12/09 (non corretto qui: e' in
    ``safe_strategy.execution.hedge_state``, condiviso con Safe).

    ``meta.locked_pnl`` = min(win, lose) delle esposizioni LORDE. Se il netto
    del mercato e' POSITIVO, il trader legge un bloccato piu' alto di quello che
    incassera' (la commissione del 5% non e' dedotta). Su perdita bloccata non
    cambia nulla (Betfair non incassa sulle perdite): per questo la guardia
    ``realized_effective`` resta corretta."""
    from Betfair.safe_strategy import execution as X
    st = X.hedge_state({"id": 1, "side": "lay", "size": 2.0, "price": 30.0},
                       [{"id": 2, "side": "back", "size": 1.0, "price": 60.0,
                         "status": "open"}])
    assert st["complete"] is True and st["locked_pnl"] == 1.0   # LORDO
    ap, ch = X.settle_group({"id": 1, "side": "lay", "size": 2.0, "price": 30.0},
                            [{"id": 2, "side": "back", "size": 1.0, "price": 60.0}],
                            runner_won=False, commission=0.05)
    assert round(ap + sum(ch), 2) == 0.95, "incassato NETTO: 5 centesimi in meno"
