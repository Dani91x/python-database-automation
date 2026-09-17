# -*- coding: utf-8 -*-
"""IL RACCORDO DI V3 DENTRO IL SERVIZIO (17/09) — quello che deve valere sempre.

Dal 17/09 `strategy_version` vale **3** di default e vuol dire:

  * UN SOLO MERCATO, il **CORRECT SCORE**. La gamba sull'HALF_TIME_SCORE non si
    fa piu' (M4M5M6_2026-09-17 §2.3: sul book HT il bias prudente nella fascia
    2-5 % vale 0,92 e sotto il 2 % non ci sono uscite).
  * DUE INGRESSI = due CELLE DIVERSE dello stesso mercato in DUE MOMENTI:
    gamba A 1'-44', gamba B 46'-85'. La P e' sempre quella della griglia
    FINALE (`periodo='ft'`), anche nel primo tempo.
  * stake FISSO (`v3_stake_eur`), fascia di probabilita' [`v3_p_min_pct`,
    `v3_p_max_pct`], margine `k = v3_k_minimo` (1,11), distanza minima 2 gol,
    tetti 95/190/1.000/300.
  * la gamba la piazza LA STESSA catena di sempre (`_size_and_place` ->
    `_place_one`: riserva, ordine, conferma).

Qui si prova che tutto questo e' vero sul percorso di produzione, che ogni
non-ingresso porta un motivo fra quelli DICHIARATI (A8) con lo scarto di ogni
runner, e che i controlli A8/A9/A10/A11/A12/C5 sanno diventare ROSSI (un test
che non sa fallire non certifica niente).

I finti sono quelli dei test del v2 (`test_omega_v2_2026_09_09`): stesse chiavi
e stessi tipi del vero, nessun fill e nessuno snapshot scritto a mano. Le righe
della tabella storica hanno le chiavi VERE della RPC
(``league_id``/``bucket``/``score``/``target``/``result``/``n``).

NOTA sul book dei test: ha CINQUE runner, sotto la soglia di
`omega_v3.p_mercato_devigata` (servono almeno sei prezzi per devigare): la
fusione col mercato quindi non si applica e la P e' quella del modello, cioe'
un numero deterministico. La fusione e' esercitata dal replay sul book vero.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from Betfair.omega import certificazione as CERT
from Betfair.omega import omega_config
from Betfair.omega import omega_empirical as EMP
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_service as S
from Betfair.omega import omega_v3 as V3
from Betfair.omega.test_omega_v2_2026_09_09 import (  # noqa: F401 — `lambdas` e' una fixture
    NOW, _DB, _Market, _runner, lambdas,
)

# LE CELLE. Con lambda (1,6 · 1,1) e griglia FINALE:
#   al 30' sullo 0-0  "1 - 3" vale 1,367 % -> a lay 55 il margine e' 1,26x
#   al 70' sullo 0-0  "2 - 1" vale 1,411 % -> a lay 55 il margine e' 1,23x
# Sono le due celle che le due gambe devono scegliere, e sono DIVERSE.
CELLA_A = (14, "1 - 3", 55.0)
CELLA_B = (13, "2 - 1", 55.0)
FUORI_TETTO = (11, "1 - 0", 3.0)        # P altissima: `p_oltre_il_tetto`
FUORI_FASCIA = (12, "0 - 2", 25.0)      # sopra il tetto al 30', sotto la fascia dopo
OLTRE_IL_CAP = (15, "3 - 2", 400.0)     # 399 EUR di liability col tetto a 95


def _books_v3(event_id, *, lay_size=50.0, prezzo_a=CELLA_A[2], prezzo_b=CELLA_B[2]):
    """Il CORRECT SCORE (l'unico mercato di V3) e, per completezza, l'HT.

    L'HALF_TIME_SCORE resta nel finto APPOSTA, e senza celle bancabili: se il
    servizio tornasse a guardarlo, i test sotto se ne accorgerebbero.
    """
    ht = [_runner(1, "0 - 0", 2.5, 200), _runner(2, "1 - 0", 4.0, 100),
          _runner(3, "2 - 1", 30.0, 60)]
    ft = [_runner(FUORI_TETTO[0], FUORI_TETTO[1], FUORI_TETTO[2], 200),
          _runner(FUORI_FASCIA[0], FUORI_FASCIA[1], FUORI_FASCIA[2], 100),
          _runner(CELLA_B[0], CELLA_B[1], prezzo_b, lay_size),
          _runner(CELLA_A[0], CELLA_A[1], prezzo_a, lay_size),
          _runner(OLTRE_IL_CAP[0], OLTRE_IL_CAP[1], OLTRE_IL_CAP[2], 40)]
    return {(event_id, "HALF_TIME_SCORE"): ht, (event_id, "CORRECT_SCORE"): ft}


def _par_v3(**over):
    base = {"engine": "legs", "strategy_version": 3, "execution_mode": "rest",
            "commission_pct": 5, "model_empirical": "off"}
    base.update(over)
    return omega_config.resolve_params(base)


def _lookup(minute, sh, sa):
    return lambda eid: S.LiveScore(minute=minute, score_home=sh, score_away=sa,
                                   updated_at=NOW.isoformat())


def _giro(db, market, ev, params, *, minute, sh=0, sa=0, goal=10.0,
          aggregates=None, legs=None):
    agg = aggregates if aggregates is not None else {
        "realized_today": 0.0, "matches_traded_today": 0, "open_liability": 0.0}
    return S.scan_and_place_legs(
        control={"daily_goal": goal, "mode": "paper"}, params=params, events=[ev],
        traded_ids=set(), traded_legs=legs if legs is not None else set(),
        aggregates=agg, market=market, db=db, now=NOW,
        score_lookup=_lookup(minute, sh, sa))


def _evento(eid="v3a", minuti_fa=70):
    return SimpleNamespace(event_id=eid, name="Nord v Sud",
                           open_date=NOW - timedelta(minutes=minuti_fa))


def _db(eid="v3a"):
    return _DB({"daily_goal": 10.0, "mode": "paper"},
               events={eid: {"fixture_id": 7, "league_id": 135}})


def _motivi(db, kind="skip"):
    return [str((p or {}).get("reason")) for k, p in db.activity if k == kind]


def _scartati(db):
    """Gli scarti per runner, da DOVE il servizio li scrive: nel log quando non
    si entra, nell'audit della riga (`meta.model.scartati`) quando si entra."""
    voci = [p.get("scartati") for k, p in db.activity
            if k == "skip" and p.get("scartati")]
    voci += [((t.get("meta") or {}).get("model") or {}).get("scartati")
             for t in db.trades]
    return " | ".join(str(x) for v in voci if v for x in v)


# ===========================================================================
# 1. L'INTERRUTTORE: chi decide, e chi non decide piu'
# ===========================================================================
def test_il_default_di_produzione_e_il_motore_v3():
    """Il default sta in `_SPEC`, che la fixture dei test NON tocca."""
    assert omega_config._SPEC["strategy_version"][0] == 3


def test_con_v3_acceso_il_motore_di_oggi_non_viene_mai_chiamato(lambdas, monkeypatch):
    chiamate = {"v2": 0, "v3": 0}
    vero_v2, vero_v3 = S._model_select, S._v3_select

    def spia_v2(**kw):
        chiamate["v2"] += 1
        return vero_v2(**kw)

    def spia_v3(**kw):
        chiamate["v3"] += 1
        return vero_v3(**kw)

    monkeypatch.setattr(S, "_model_select", spia_v2)
    monkeypatch.setattr(S, "_v3_select", spia_v3)
    ev, db, market = _evento(), _db(), _Market(_books_v3("v3a"))
    _giro(db, market, ev, _par_v3(), minute=70)
    assert chiamate["v3"] >= 1 and chiamate["v2"] == 0


def test_con_strategy_version_2_il_v3_non_viene_mai_chiamato(lambdas, monkeypatch):
    """L'interruttore e' l'unica differenza, e resta un parametro dell'utente."""
    def spia_v3(**kw):
        raise AssertionError("V3 chiamato col motore legacy acceso")

    monkeypatch.setattr(S, "_v3_select", spia_v3)
    ev, db, market = _evento("v2a"), _db("v2a"), _Market(_books_v3("v2a"))
    par = omega_config.resolve_params({"engine": "legs", "execution_mode": "rest",
                                       "strategy_version": 2, "commission_pct": 5})
    _giro(db, market, ev, par, minute=70)     # non deve sollevare


# ===========================================================================
# 2. LA GAMBA: mercato unico, scelta e piazzata dalla catena di produzione
# ===========================================================================
def test_v3_apre_sul_correct_score_con_lo_stake_esatto(lambdas):
    ev, db, market = _evento(), _db(), _Market(_books_v3("v3a"))
    assert _giro(db, market, ev, _par_v3(), minute=70) == 1, db.activity
    t = db.trades[0]
    assert t["market_id"] == "m-v3a-CORRECT_SCORE"      # MAI l'HALF_TIME_SCORE
    assert t["phase"] == "ft_cs" and t["side"] == "lay"
    # fra le due celle IN FASCIA (stessa quota 55, stessa p_implicita) vince la
    # P NOSTRA piu' bassa: al 70' e' "1 - 3" (0,32 %) contro "2 - 1" (1,41 %).
    # La fascia sta sulla p_implicita, quindi non e' piu' lei a scegliere fra le
    # due — e' il criterio di sempre (la P piu' bassa che passa il margine).
    assert t["runner_name"] == CELLA_A[1] and t["price"] == CELLA_A[2]
    assert t["status"] == "open"
    assert t["size"] == 1.0 and t["meta"]["requested_size"] == 1.0
    assert t["liability"] == E.liability_from_lay(1.0, CELLA_A[2]) == 54.0
    mod = t["meta"]["model"]
    assert mod["motore"] == "v3" and mod["mercato"] == "CORRECT_SCORE"
    assert mod["periodo"] == "ft" and mod["gamba"] == "B"
    assert mod["lambda_source"] == "fixture"
    assert mod["k_usato"] == 1.11                       # il pavimento dell'utente
    assert mod["p_selected"] * mod["k_usato"] <= mod["p_implied"] + 1e-12
    # LA FASCIA sta sulla p_IMPLICITA al tocco, non sulla P nostra: e' li' che il
    # bias e' stato misurato in gioco (M4M5M6 §2.3)
    assert 0.01 <= mod["p_implied"] <= 0.02
    assert mod["p_selected"] <= 0.02            # il tetto duro sulla P nostra


def test_la_gamba_a_e_sul_correct_score_anche_nel_primo_tempo(lambdas):
    ev = _evento("v3A", minuti_fa=30)
    db, market = _db("v3A"), _Market(_books_v3("v3A"))
    assert _giro(db, market, ev, _par_v3(), minute=30) == 1, db.activity
    t = db.trades[0]
    assert t["phase"] == "ht_cs"                        # la PRIMA gamba...
    assert t["market_id"] == "m-v3A-CORRECT_SCORE"      # ...ma sul Correct Score
    assert t["runner_name"] == CELLA_A[1]
    assert t["meta"]["model"]["periodo"] == "ft" and t["meta"]["model"]["gamba"] == "A"
    assert t["size"] == 1.0


def test_le_due_gambe_sono_due_celle_diverse_dello_stesso_mercato(lambdas):
    """Due ingressi = due celle DIVERSE: la seconda esclude quella della prima."""
    class _DBConEsposto(_DB):
        def trades_for_event(self, event_id):
            return [dict(r, closes_trade_id=None, origin="auto") for r in self.trades]

    db = _DBConEsposto({"daily_goal": 10.0, "mode": "paper"},
                       events={"v3due": {"fixture_id": 7, "league_id": 135}})
    market = _Market(_books_v3("v3due"))
    gambe: set = set()
    assert _giro(db, market, _evento("v3due", minuti_fa=30), _par_v3(),
                 minute=30, legs=gambe) == 1
    gambe.add(("v3due", "ht_cs"))
    assert _giro(db, market, _evento("v3due", minuti_fa=70), _par_v3(),
                 minute=70, legs=gambe) == 1, db.activity
    celle = [t["runner_name"] for t in db.trades]
    assert celle == [CELLA_A[1], CELLA_B[1]] and len(set(celle)) == 2
    assert {t["market_id"] for t in db.trades} == {"m-v3due-CORRECT_SCORE"}


def test_lo_stake_non_dipende_dall_obiettivo_di_giornata(lambdas):
    """A9: 1,00 EUR con G=10 e con G=5.000. In v2 la size viene dal target."""
    taglie = []
    for goal in (10.0, 5000.0):
        eid = f"v3g{int(goal)}"
        ev, db, market = _evento(eid), _db(eid), _Market(_books_v3(eid))
        assert _giro(db, market, ev, _par_v3(), minute=70, goal=goal) == 1
        taglie.append(db.trades[0]["size"])
        assert db.trades[0]["target"] == 0.0      # in V3 non esiste un target di gamba
    assert taglie == [1.0, 1.0]


def test_lo_stake_segue_il_parametro_dell_utente(lambdas):
    ev, db, market = _evento("v3s"), _db("v3s"), _Market(_books_v3("v3s"))
    # col tetto di gamba a 95 EUR, 2,50 EUR a quota 55 farebbero 135 EUR: il
    # tetto e' dell'utente quanto lo stake, e qui si alza APPOSTA
    par = _par_v3(v3_stake_eur=2.5, v3_max_liability_per_leg=200.0,
                  v3_max_liability_per_match=400.0)
    assert _giro(db, market, ev, par, minute=70) == 1, db.activity
    assert db.trades[0]["size"] == 2.5


# ===========================================================================
# 3. IL MINUTO E' QUELLO DEL FEED, MAI L'OROLOGIO
# ===========================================================================
def test_la_finestra_si_giudica_sul_minuto_reale_non_sull_orologio(lambdas):
    """Orologio a 95', feed a 70': si entra. Orologio a 70', feed a 45': no."""
    ev, db, market = _evento("v3m1", minuti_fa=95), _db("v3m1"), _Market(_books_v3("v3m1"))
    assert _giro(db, market, ev, _par_v3(), minute=70) == 1, db.activity

    ev2, db2, market2 = _evento("v3m2", minuti_fa=70), _db("v3m2"), _Market(_books_v3("v3m2"))
    assert _giro(db2, market2, ev2, _par_v3(), minute=45) == 0
    assert db2.trades == []


def test_la_gamba_b_non_parte_prima_del_46(lambdas):
    """45' e' l'intervallo: la gamba B comincia al 46'."""
    ev = _evento("v3w", minuti_fa=60)
    db, market = _db("v3w"), _Market(_books_v3("v3w"))
    assert _giro(db, market, ev, _par_v3(), minute=45) == 0
    assert _giro(db, market, ev, _par_v3(), minute=70) == 1


def test_la_gamba_a_puo_partire_dal_primo_minuto(lambdas):
    """Il Correct Score e' quotabile dal 1': la finestra A parte da li'."""
    par = _par_v3()
    assert par["v3_ht_entry_min"] == 1 and par["v3_ht_entry_max"] == 44
    assert par["v3_ft_entry_min"] == 46 and par["v3_ft_entry_max"] == 85


# ===========================================================================
# 4. LIQUIDITA', FASCIA E TETTI: si scarta, non si taglia
# ===========================================================================
def test_liquidita_sotto_lo_stake_e_uno_skip_non_un_lay_piu_piccolo(lambdas):
    ev = _evento("v3l")
    db, market = _db("v3l"), _Market(_books_v3("v3l", lay_size=0.4))
    par = _par_v3(v3_min_lay_liquidity=0.1)   # la selezione lascia passare 0,4...
    assert _giro(db, market, ev, par, minute=70) == 0
    assert "insufficient_liquidity" in _motivi(db)
    assert db.trades == []                     # ...ma NON si entra per 0,40 EUR


def test_il_tetto_di_gamba_scarta_il_runner_col_motivo(lambdas):
    """A quota 400 la liability e' 399 EUR: oltre il tetto di 95.

    Pavimento di fascia e margine si allentano APPOSTA: col pavimento all'1 %
    quella cella si ferma prima (`p_sotto_fascia`) e il tetto di gamba non
    avrebbe mai un caso — un controllo che non guarda non garantisce niente.
    """
    ev, db, market = _evento("v3c"), _db("v3c"), _Market(_books_v3("v3c"))
    _giro(db, market, ev, _par_v3(v3_p_min_pct=0.0, v3_k_minimo=1.0), minute=70)
    assert "oltre_il_cap_di_gamba" in _scartati(db)
    # e nessuna riga e' stata scritta a quel prezzo: si scarta, non si taglia
    assert all(float(t["price"]) < 400.0 for t in db.trades)


def test_la_fascia_sta_sulla_p_implicita_e_ha_due_bordi(lambdas):
    """La fascia si applica alla p_IMPLICITA AL TOCCO: sotto il pavimento
    `p_impl_sotto_fascia`, sopra il tetto `p_impl_oltre_fascia`."""
    ev, db, market = _evento("v3pm"), _db("v3pm"), _Market(_books_v3("v3pm"))
    _giro(db, market, ev, _par_v3(), minute=70)
    testo = _scartati(db)
    # "3 - 2" a 400 -> p_impl 0,24 %: sotto il pavimento dell'1 %
    assert "p_impl_sotto_fascia" in testo
    # "0 - 2" a 25 -> p_impl 3,81 %: sopra il tetto del 2 % (li' il bias vale 0,71)
    assert "p_impl_oltre_fascia" in testo
    # col pavimento a zero quella stessa cella non e' piu' scartata dal pavimento
    ev2, db2, market2 = _evento("v3pz"), _db("v3pz"), _Market(_books_v3("v3pz"))
    _giro(db2, market2, ev2, _par_v3(v3_p_min_pct=0.0), minute=70)
    assert "p_impl_sotto_fascia" not in _scartati(db2)


def test_falsificazione_la_fascia_non_e_sulla_p_nostra():
    """IL REPERTO DEL COORDINATORE (17/09): con la fascia sulla P NOSTRA una
    cella a p_impl 2,38 % — fascia 2-5 %, dove il bias misurato in gioco vale
    0,71, cioe' EV NEGATIVO — con P nostra 1,5 % PASSEREBBE. Con la fascia sulla
    p_implicita si scarta, ed e' la fascia a escluderla, non il margine."""
    comune = dict(periodo="ft", runners=[V3.RunnerV3(21, "4 - 2", 40.0, 50.0)],
                  probabilita={"4 - 2": 0.015}, commissione=0.05, size=1.0,
                  min_liquidita=1.0, distanza_minima_gol=2, punteggio=(0, 0),
                  cap_liability_gamba=0.0, k_default=1.11)
    cand, scarti = V3.valuta_runner(p_min=0.01, p_max=0.02, **comune)
    assert cand is None and any(p == "p_impl_oltre_fascia" for _, p in scarti)
    passa, _ = V3.valuta_runner(p_min=0.01, p_max=0.05, **comune)
    assert passa is not None and passa.name == "4 - 2"


def test_il_tetto_di_partita_dichiara_il_motivo(lambdas):
    class _DBConEsposto(_DB):
        def trades_for_event(self, event_id):
            return [{"id": 99, "event_id": event_id, "status": "open", "side": "lay",
                     "origin": "auto", "closes_trade_id": None, "liability": 150.0,
                     "selection_id": 999}]

    db = _DBConEsposto({"daily_goal": 10.0, "mode": "paper"},
                       events={"v3p": {"fixture_id": 7, "league_id": 135}})
    ev, market = _evento("v3p"), _Market(_books_v3("v3p"))
    assert _giro(db, market, ev, _par_v3(), minute=70,
                 legs={("v3p", "ht_cs")}) == 0     # 150 + 54 > 190
    assert "cap_partita" in _motivi(db)


def test_se_l_esposizione_di_partita_non_si_legge_non_si_apre(lambdas):
    """«Non lo so» non e' «niente» (I3): in dubbio non si aggiunge esposizione."""
    ev, db, market = _evento("v3f"), _db("v3f"), _Market(_books_v3("v3f"))
    assert _giro(db, market, ev, _par_v3(), minute=70,
                 legs={("v3f", "ht_cs")}) == 0     # `_DB` non ha trades_for_event
    assert "cap_partita" in _motivi(db)


def test_il_tetto_aperto_dichiara_il_motivo(lambdas):
    ev, db, market = _evento("v3o"), _db("v3o"), _Market(_books_v3("v3o"))
    agg = {"realized_today": 0.0, "matches_traded_today": 0, "open_liability": 990.0}
    assert _giro(db, market, ev, _par_v3(), minute=70, aggregates=agg) == 0
    assert "cap_aperto" in _motivi(db)


def test_lo_stop_loss_giornaliero_di_v3_ferma_le_aperture(lambdas):
    ev, db, market = _evento("v3d"), _db("v3d"), _Market(_books_v3("v3d"))
    agg = {"realized_today": -350.0, "matches_traded_today": 0, "open_liability": 0.0}
    assert _giro(db, market, ev, _par_v3(), minute=70, aggregates=agg) == 0
    assert any(k == "loss_stop" for k, _ in db.activity)


# ===========================================================================
# 5. OGNI NON-INGRESSO E' DICHIARATO (A8) E PORTA IL MARGINE VERO
# ===========================================================================
def test_ogni_motivo_di_non_ingresso_e_fra_quelli_dichiarati(lambdas):
    visti = set()
    prove = (
        ("v3z1", _par_v3(v3_max_liability_per_match=1.0), {"minute": 70}),
        ("v3z2", _par_v3(), {"minute": 70, "aggregates": {
            "realized_today": 0.0, "matches_traded_today": 0,
            "open_liability": 999.0}}),
        ("v3z3", _par_v3(v3_k_minimo=20.0), {"minute": 70}),
    )
    for eid, par, kw in prove:
        db, market = _db(eid), _Market(_books_v3(eid))
        _giro(db, market, _evento(eid), par, legs={(eid, "ht_cs")}, **kw)
        visti |= {m for m in _motivi(db) if m and m != "None"}
    assert visti, "nessun motivo osservato: il test non proverebbe niente"
    assert visti <= CERT.MOTIVI_V3, f"motivi non dichiarati: {visti - CERT.MOTIVI_V3}"


def test_lo_scarto_di_ogni_runner_porta_il_margine_vero(lambdas):
    """«nessun candidato» senza dire QUANTO mancava non e' una spiegazione."""
    ev, db, market = _evento("v3r"), _db("v3r"), _Market(_books_v3("v3r"))
    assert _giro(db, market, ev, _par_v3(v3_k_minimo=20.0), minute=70) == 0
    assert "nessun_candidato" in _motivi(db)
    testo = _scartati(db)
    assert "margine " in testo and "ne serve 20x" in testo


# ===========================================================================
# 6. IL VETO STORICO (A12): dove il dato parla, la sua P e' obbligatoria
# ===========================================================================
def _righe_minuto(*, bucket, score, target, result, n_result, n_altro):
    """Righe con le chiavi VERE della RPC `get_omega_minute_ft`."""
    return [
        {"league_id": EMP.GLOBAL_LEAGUE, "bucket": bucket, "score": score,
         "target": target, "result": result, "n": n_result},
        {"league_id": EMP.GLOBAL_LEAGUE, "bucket": bucket, "score": score,
         "target": target, "result": "9 - 9", "n": n_altro},
    ]


class _DbConTabella(_DB):
    def __init__(self, *a, righe=(), **kw):
        super().__init__(*a, **kw)
        self._righe = list(righe)

    def minute_transitions(self, league_id, bucket, target):
        return list(self._righe)


def test_il_veto_storico_alza_la_p_e_sotto_il_minimo_non_parla():
    stato = SimpleNamespace(minute=70, score_home=0, score_away=0,
                            yellow_home=0, yellow_away=0)
    par = _par_v3(model_empirical="veto")
    righe = _righe_minuto(bucket=70, score="0-0", target="ft", result="2 - 1",
                          n_result=40, n_altro=4000)
    db = _DbConTabella({"daily_goal": 10.0, "mode": "paper"}, righe=righe)
    S._MINUTE_CACHE.clear()
    p = S._v3_p_empirica(db, league_id=135, state=stato, half=False, payload=None,
                         params=par, n_min=200)
    assert p is not None
    got = p("2 - 1")
    assert got is not None and got[1] == 4040 and got[0] > 0.0
    assert p("Any Unquoted Draw") is None        # gli aggregati non hanno riga
    # SOTTO il minimo di casi la tabella NON ha diritto di parola
    S._MINUTE_CACHE.clear()
    assert S._v3_p_empirica(db, league_id=135, state=stato, half=False, payload=None,
                            params=par, n_min=10_000)("2 - 1") is None


def test_il_veto_storico_entra_nella_decisione_come_massimo():
    """P_nostra = max(modello, storico): con uno storico ALTO la cella si scarta."""
    runners = [E.ScoreRunner(CELLA_B[0], CELLA_B[1], lay_price=CELLA_B[2], lay_size=50.0)]
    comune = dict(periodo="ft", minuto=70.0, punteggio=(0, 0),
                  params=_par_v3(), lambdas=(1.6, 1.1),
                  parametri_modello=S._v3_tarature()[0], finestra=(46, 85))
    senza, _ = E.seleziona_v3(runners, **comune)
    assert senza is not None and senza.p_empirica is None
    con, scarti = E.seleziona_v3(runners, p_empirica=lambda n: (0.20, 5000), **comune)
    assert con is None and any("p_oltre_il_tetto" in p for _, p in scarti)


# ===========================================================================
# 7. FALSIFICAZIONE DEI CONTROLLI: sanno diventare ROSSI?
# ===========================================================================
def _cand(**over):
    base = dict(selection_id=CELLA_B[0], name=CELLA_B[1], price=CELLA_B[2], size=1.0,
                p_modello=0.01411, p_fusa=0.01411, p_empirica=None, n_empirico=None,
                p_nostra=0.01411, p_implicita=0.01729, k_usato=1.11, margine=1.225,
                ev=0.26, liability=54.0, motivo="prova")
    base.update(over)
    return V3.CandidatoV3(**base)


def _momento(**kw):
    base = dict(tipo="selezione", now=NOW, params=_par_v3(), event_id="e",
                mode="paper", motore="v3", leg="ft_cs", half=False)
    base.update(kw)
    return CERT.Momento(**base)


def _viola(m):
    return [v.codice for v in CERT.verifica(m)]


def test_falsificazione_a9_stake_diverso_dallo_stake_fisso():
    assert "A9" not in _viola(_momento(tipo="sizing", size=1.0, price=55.0))
    assert "A9" in _viola(_momento(tipo="sizing", size=1.10, price=55.0))


def test_falsificazione_a10_margine_k_non_rispettato():
    assert "A10" not in _viola(_momento(cand=_cand()))
    # k sotto il pavimento dell'utente (1,11)
    assert "A10" in _viola(_momento(cand=_cand(k_usato=1.0)))
    # P_nostra oltre la soglia p_implicita / k
    assert "A10" in _viola(_momento(cand=_cand(p_nostra=0.0172)))


def test_falsificazione_a11_punteggio_troppo_vicino():
    stato = SimpleNamespace(minute=70, score_home=0, score_away=0)
    assert "A11" not in _viola(_momento(cand=_cand(), state=stato))
    # a UN gol dal punteggio corrente, col minimo a 2
    assert "A11" in _viola(_momento(cand=_cand(name="1 - 0"), state=stato))
    # il punteggio CORRENTE: il difetto del v1
    assert "A11" in _viola(_momento(cand=_cand(name="0 - 0"), state=stato))


def test_falsificazione_a11_tetto_duro_sulla_p():
    stato = SimpleNamespace(minute=70, score_home=0, score_away=0)
    assert "A11" in _viola(_momento(cand=_cand(p_nostra=0.03), state=stato))


def test_falsificazione_a11_fascia_sulla_p_implicita():
    """Il buco trovato dalla falsificazione del 17/09: la fascia non la guardava
    nessun controllo. E la guarda sulla p_IMPLICITA, che e' dove il bias e'
    stato misurato in gioco."""
    stato = SimpleNamespace(minute=70, score_home=0, score_away=0)
    assert "A11" not in _viola(_momento(cand=_cand(), state=stato))
    sotto = _cand(p_implicita=0.0024)      # quota ~400: fuori dalla misura
    assert "A11" in _viola(_momento(cand=sotto, state=stato))
    sopra = _cand(p_implicita=0.0238)      # quota 40: fascia 2-5 %, bias 0,71
    assert "A11" in _viola(_momento(cand=sopra, state=stato))
    # col pavimento a zero la cella SOTTO non e' piu' un'accusa, quella sopra si'
    senza = _par_v3(v3_p_min_pct=0.0)
    assert "A11" not in _viola(_momento(cand=sotto, state=stato, params=senza))
    assert "A11" in _viola(_momento(cand=sopra, state=stato, params=senza))


def test_falsificazione_a12_veto_storico_saltato():
    sano = _cand(p_empirica=0.015, n_empirico=5000, p_fusa=0.01411, p_nostra=0.015)
    assert "A12" not in _viola(_momento(cand=sano))
    saltato = _cand(p_empirica=0.015, n_empirico=5000, p_fusa=0.01411, p_nostra=0.01411)
    assert "A12" in _viola(_momento(cand=saltato))
    scarso = _cand(p_empirica=0.015, n_empirico=10, p_fusa=0.01411, p_nostra=0.015)
    assert "A12" in _viola(_momento(cand=scarso))


def test_falsificazione_c5_tetto_di_gamba_ignorato():
    assert "C5" not in _viola(_momento(tipo="sizing", size=1.0, price=55.0))
    # 1 EUR a quota 400 = 399 EUR di liability, col tetto a 95
    assert "C5" in _viola(_momento(tipo="sizing", size=1.0, price=400.0))


def test_falsificazione_a8_motivo_non_dichiarato():
    assert "A8" not in _viola(_momento(cand=None, motivo="fuori_finestra"))
    assert "A8" in _viola(_momento(cand=None, motivo="perche_si"))
    assert "A8" in _viola(_momento(cand=None, motivo=""))


def test_falsificazione_pavimento_di_fascia_nel_motore():
    """Una cella SOTTO la fascia non deve mai diventare un candidato."""
    comune = dict(periodo="ft", runners=[V3.RunnerV3(99, "9 - 9", 500.0, 50.0)],
                  probabilita={"9 - 9": 0.0001}, commissione=0.05, size=1.0,
                  min_liquidita=1.0, distanza_minima_gol=2, punteggio=(0, 0),
                  p_max=0.02, cap_liability_gamba=0.0, k_default=1.11)
    cand, scarti = V3.valuta_runner(p_min=0.01, **comune)
    assert cand is None and any(p == "p_impl_sotto_fascia" for _, p in scarti)
    cand2, _ = V3.valuta_runner(p_min=0.0, **comune)
    assert cand2 is not None      # col pavimento a zero la stessa cella passa


def test_falsificazione_celle_diverse():
    """La cella gia' bancata dalla prima gamba non e' piu' un candidato."""
    comune = dict(periodo="ft", runners=[V3.RunnerV3(7, "2 - 1", 55.0, 50.0)],
                  probabilita={"2 - 1": 0.01411}, commissione=0.05, size=1.0,
                  min_liquidita=1.0, distanza_minima_gol=2, punteggio=(0, 0),
                  p_max=0.02, p_min=0.01, cap_liability_gamba=0.0, k_default=1.11)
    cand, _ = V3.valuta_runner(**comune)
    assert cand is not None
    escluso, scarti = V3.valuta_runner(escludi=(7,), **comune)
    assert escluso is None and any(p == "cella_gia_bancata" for _, p in scarti)


# ===========================================================================
# 8. I DEFAULT DELL'UTENTE (17/09): nessuno di piu', nessuno di meno
# ===========================================================================
def test_i_default_di_v3_sono_quelli_decisi_il_17_09():
    d = omega_config._SPEC
    assert d["strategy_version"][0] == 3
    assert d["v3_stake_eur"][0] == 1.0
    assert d["v3_k_minimo"][0] == 1.11
    assert d["v3_distanza_minima_gol"][0] == 2
    assert d["v3_p_max_pct"][0] == 2.0 and d["v3_p_min_pct"][0] == 1.0
    assert d["v3_max_liability_per_leg"][0] == 95.0
    assert d["v3_max_liability_per_match"][0] == 190.0
    assert d["v3_max_open_liability"][0] == 1000.0
    assert d["v3_daily_loss_cap"][0] == 300.0
    assert d["v3_ht_entry_min"][0] == 1 and d["v3_ht_entry_max"][0] == 44
    assert d["v3_ft_entry_min"][0] == 46 and d["v3_ft_entry_max"][0] == 85
    assert d["v3_modello"][0] == "gamma_poisson"
    assert d["v3_min_lay_liquidity"][0] == 1.0


def test_una_fascia_rovesciata_viene_rimessa_a_posto():
    p = omega_config.resolve_params({"v3_p_min_pct": 5.0, "v3_p_max_pct": 1.0})
    assert p["v3_p_min_pct"] == 1.0 and p["v3_p_max_pct"] == 5.0


def test_le_tarature_si_leggono_dal_file_versionato():
    par, k_tab = S._v3_tarature()
    assert par.modello == "gamma_poisson"
    # la tabella del 16/09 vale 2,0 in ogni secchio: e' per questo che NON si
    # passa piu' al motore (riporterebbe il margine a 2,0 in silenzio)
    assert k_tab and set(k_tab.values()) == {2.0}
    from Betfair.omega.tools.replay_registrazioni import _parametri_v3_dal_banco
    assert _parametri_v3_dal_banco() == par
