# -*- coding: utf-8 -*-
"""Test della MISURA PUNTO 8. Ogni test dice nel docstring come diventa ROSSO
(la falsificazione e' eseguita da `falsifica_misura_punto8.py`).

Regola dura: il DB vero non si tocca. Le variabili del DB finto si impostano
PRIMA di ogni import del repo.
"""
from __future__ import annotations

import math
import os

os.environ.update({"SUPABASE_URL": "http://127.0.0.1:9", "SUPABASE_SERVICE_ROLE_KEY": "x",
                   "SUPABASE_KEY": "x"})

import pytest  # noqa: E402

from Betfair.stream.backtest.tools.misura_punto8 import comune as C  # noqa: E402


# ---------------------------------------------------------------------------
# comune
# ---------------------------------------------------------------------------
def test_log_loss_e_meno_log_p():
    """ROSSO se log_loss non prende il logaritmo (es. ritorna 1-p)."""
    assert C.log_loss(0.25) == pytest.approx(-math.log(0.25))
    assert C.log_loss(1.0) == pytest.approx(0.0)
    assert C.log_loss_binario(0.8, 0) == pytest.approx(-math.log(0.2))


def test_brier_multiclasse_valore_esatto():
    """(0,5-1)^2 + 0,3^2 + 0,2^2 = 0,38. ROSSO se la classe accaduta non conta (p-1)."""
    g = {"a": 0.5, "b": 0.3, "c": 0.2}
    assert C.brier_multiclasse(g, "a") == pytest.approx(0.38)
    assert C.brier_multiclasse(g, "zzz") == pytest.approx(0.25 + 0.09 + 0.04 + 1.0)


def test_bootstrap_bracci_identici_ic_degenere():
    d = [0.0] * 50
    ic = C.bootstrap_media(d, list(range(50)))
    assert ic["media"] == 0.0 and ic["lo"] == 0.0 and ic["hi"] == 0.0


def test_bootstrap_ricampiona_davvero():
    """Dati rumorosi -> IC di ampiezza > 0 che contiene la media.
    ROSSO se il bootstrap non ricampiona (lo = hi = media)."""
    import random
    r = random.Random(1)
    d = [r.gauss(0.0, 1.0) for _ in range(200)]
    ic = C.bootstrap_media(d, list(range(200)))
    assert ic["lo"] < ic["media"] < ic["hi"]
    assert ic["hi"] - ic["lo"] > 0.1


def test_bootstrap_a_grappolo_non_a_riga():
    """10 partite con 50 campioni IDENTICI ciascuna valgono 10 unita', non 500:
    l'IC deve essere largo come quello di 10 valori. ROSSO se si ricampionano
    le righe (IC ~ sqrt(50) volte piu' stretto)."""
    import random
    r = random.Random(2)
    valori_partita = [r.gauss(0.0, 1.0) for _ in range(10)]
    righe, unita = [], []
    for i, v in enumerate(valori_partita):
        righe += [v] * 50
        unita += [i] * 50
    ic_g = C.bootstrap_media(righe, unita)
    ic_10 = C.bootstrap_media(valori_partita, list(range(10)))
    assert (ic_g["hi"] - ic_g["lo"]) == pytest.approx(ic_10["hi"] - ic_10["lo"], rel=0.15)
    assert ic_g["n_unita"] == 10 and ic_g["n"] == 500


def test_bootstrap_rifiuta_meno_di_2000_giri():
    with pytest.raises(ValueError):
        C.bootstrap_media([1.0, 2.0], [1, 2], giri=500)


def test_verdetto():
    """ROSSO se "MIGLIORA" con un IC che contiene lo zero."""
    assert C.verdetto({"lo": -0.2, "hi": -0.01, "n": 50, "n_unita": 50}) == C.MIGLIORA
    assert C.verdetto({"lo": -0.2, "hi": 0.01, "n": 50, "n_unita": 50}) == C.NON_MIGLIORA
    assert C.verdetto({"lo": 0.01, "hi": 0.2, "n": 50, "n_unita": 50}) == C.PEGGIORA
    assert C.verdetto({"lo": -0.2, "hi": -0.01, "n": 50, "n_unita": 5}).startswith(C.NON_MISURABILE)


def test_rapporto_usciti_attesi():
    ic = C.bootstrap_rapporto([1, 0, 0, 1], [0.5, 0.5, 0.5, 0.5], ["a", "b", "c", "d"])
    assert ic["rapporto"] == pytest.approx(1.0)
    assert ic["lo"] <= 1.0 <= ic["hi"]


def test_wilson():
    lo, hi = C.wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-3) and hi == pytest.approx(0.5962, abs=1e-3)


# ---------------------------------------------------------------------------
# O1
# ---------------------------------------------------------------------------
def _fp_m2(tlh=None, tla=None, lh=None, la=None):
    """Riga del campione M2 (alias VERI della select di m2_pesi.SEL_FP)."""
    return {"fixture_id": 1, "league_id": 39, "lh": lh, "la": la, "tlh": tlh, "tla": tla}


def test_o1_riga_postgrest_ha_le_chiavi_vere():
    from Betfair.stream.backtest.tools.misura_punto8 import o1_catena_lambda as O1
    r = O1.riga_fp_postgrest(_fp_m2(tlh="1.5", tla="1.1", lh="1.4", la="1.0"))
    assert r["tactical_engine_json"] == {"lambda_home": "1.5", "lambda_away": "1.1"}
    assert r["db_json_analisi"] == {"inputs": {"lambda_home": "1.4", "lambda_away": "1.0"}}


def test_o1_catena_attuale_e_quella_di_produzione():
    """La fixture (tattico) vince sul pre_ko nella catena ATTUALE; la variante
    usa il pre_ko. ROSSO se il braccio attuale non chiamasse davvero
    `omega_service._prematch_lambdas` (es. ordine invertito)."""
    from Betfair.stream.backtest.tools.misura_punto8 import o1_catena_lambda as O1
    fp = O1.riga_fp_postgrest(_fp_m2(tlh="2.0", tla="0.5"))
    pre = {"home": 1.8, "draw": 3.6, "away": 4.8}
    a = O1.lambda_attuale(1, 39, fp, pre)
    v = O1.lambda_variante(1, 39, fp, pre)
    assert a == (2.0, 0.5, "fixture")
    assert v[2] == "pre_ko_odds" and (v[0], v[1]) != (2.0, 0.5)
    # senza fixture la catena attuale ricade sul pre_ko: le due braccia coincidono
    a2 = O1.lambda_attuale(2, 39, None, pre)
    assert a2[2] == "pre_ko_odds" and a2[:2] == v[:2]
    # senza pre_ko la variante ricade sulla fixture
    assert O1.lambda_variante(1, 39, fp, None) == (2.0, 0.5, "fixture")


def test_o1_distribuzione_lambda_source():
    """Righe con le chiavi dell'estrazione (`src` = model->>lambda_source).
    ROSSO se l'evento senza modello venisse scartato (il denominatore cambia)."""
    from Betfair.stream.backtest.tools.misura_punto8 import o1_catena_lambda as O1
    d = O1.distribuzione_lambda_source([{"event_id": "1", "src": "pre_ko_odds"},
                                        {"event_id": "2", "src": "pre_ko_odds"},
                                        {"event_id": "3", "src": None},
                                        {"event_id": "4", "src": "market_grid"}])
    assert d["eventi"] == 4
    assert d["per_fonte"] == {"pre_ko_odds": 2, "nessun_modello_salvato": 1, "market_grid": 1}
    assert d["quote"]["pre_ko_odds"] == 0.5


def test_o1_camelcase_non_e_una_fixture():
    """`lambdaHome` non e' la chiave vera: il lettore di produzione non la legge."""
    from Betfair.stream.backtest.tools.misura_punto8 import o1_catena_lambda as O1
    fp = {"league_id": 39, "tactical_engine_json": {"lambdaHome": 2.0, "lambdaAway": 0.5},
          "db_json_analisi": None}
    assert O1.lambda_attuale(3, 39, fp, None) is None


def test_o1_valuta_v3_e_la_griglia_di_produzione():
    from Betfair.stream.backtest.tools.misura_punto8 import o1_catena_lambda as O1
    from Betfair.omega import omega_proposte as OP
    from Betfair.omega import omega_v3 as V3
    p = OP.parametri_modello()
    es = {"goals_home": 2, "goals_away": 1, "halftime_home": 1, "halftime_away": 0}
    v = O1.valuta_v3(1.5, 1.1, es, p)
    g = V3.griglia_finale(minuto=0.0, punteggio=(0, 0), periodo="ft", p=p, lambdas=(1.5, 1.1))
    assert v["ll_ft"] == pytest.approx(-math.log(g[(2, 1)]))
    h = V3.griglia_finale(minuto=0.0, punteggio=(0, 0), periodo="ht", p=p, lambdas=(1.5, 1.1))
    assert v["ll_ht"] == pytest.approx(-math.log(h[(1, 0)]))


# ---------------------------------------------------------------------------
# O5
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("minuto,punt", [(0.0, (0, 0)), (37.0, (1, 0)), (70.0, (1, 2)), (85.0, (0, 0))])
def test_o5_moltiplicatore_neutro_e_la_produzione(minuto, punt):
    """Con m=(1,1) la griglia coi rossi e' IDENTICA a `omega_v3.griglia_finale`.
    ROSSO se l'esposizione residua fosse scalata male."""
    from Betfair.stream.backtest.tools.misura_punto8 import o5_rossi as O5
    from Betfair.omega import omega_proposte as OP
    from Betfair.omega import omega_v3 as V3
    p = OP.parametri_modello()
    a = V3.griglia_finale(minuto=minuto, punteggio=punt, periodo="ft", p=p, lambdas=(1.4, 1.1))
    b = O5.griglia_con_rossi(minuto=minuto, punteggio=punt, p=p, lambdas=(1.4, 1.1), mult=(1.0, 1.0))
    assert set(a) == set(b)
    for k in a:
        assert b[k] == pytest.approx(a[k], abs=1e-12)


def test_o5_rosso_di_casa_abbassa_i_gol_di_casa():
    """Rosso alla CASA: coefficienti globali 0,7461 / 1,3832 -> meno gol attesi
    della casa, piu' della trasferta. ROSSO se beta venisse MOLTIPLICATO per m."""
    from Betfair.stream.backtest.tools.misura_punto8 import o5_rossi as O5
    from Betfair.omega import omega_proposte as OP
    p = OP.parametri_modello()
    m = O5.moltiplicatori_globali(1, 0)
    assert m[0] == pytest.approx(0.7461, abs=1e-4) and m[1] == pytest.approx(1.3832, abs=1e-4)
    g0 = O5.griglia_con_rossi(minuto=30.0, punteggio=(0, 0), p=p, lambdas=(1.4, 1.1), mult=(1, 1))
    g1 = O5.griglia_con_rossi(minuto=30.0, punteggio=(0, 0), p=p, lambdas=(1.4, 1.1), mult=m)
    eh = lambda g: sum(h * v for (h, a), v in g.items())
    ea = lambda g: sum(a * v for (h, a), v in g.items())
    assert eh(g1) < eh(g0) and ea(g1) > ea(g0)


def test_o5_stato_al_minuto():
    from Betfair.stream.backtest.tools.misura_punto8 import o5_rossi as O5
    ev = [{"minute": 10, "tipo": "gol", "lato": "home"}, {"minute": 30, "tipo": "rosso", "lato": "away"},
          {"minute": 50, "tipo": "gol", "lato": "away"}]
    assert O5.stato_al(ev, 30) == ((1, 0), (0, 1))
    assert O5.stato_al(ev, 29) == ((1, 0), (0, 0))
    assert O5.punti_di_valutazione(ev, 30) == [30, 40, 50, 60, 70, 80]


def test_o5_estrazione_finta_con_le_chiavi_di_match_events():
    """Finti con le colonne VERE di `match_events` (event_type, detail, team_id,
    minute) e di `matches`: gol incoerenti col finale -> partita scartata."""
    from Betfair.stream.backtest.tools.misura_punto8 import o5_rossi as O5
    esiti = [{"fixture_id": 1, "league_id": 39, "goals_home": 1, "goals_away": 1,
              "home_team_id": 10, "away_team_id": 20, "fixture_date": "2026-09-20T15:00:00+00:00",
              "status_short": "FT"},
             {"fixture_id": 2, "league_id": 39, "goals_home": 3, "goals_away": 0,
              "home_team_id": 11, "away_team_id": 21, "fixture_date": "2026-09-20T15:00:00+00:00",
              "status_short": "FT"}]
    eventi = [
        {"fixture_id": 1, "team_id": 10, "event_type": "Goal", "detail": "Normal Goal", "minute": 12},
        {"fixture_id": 1, "team_id": 20, "event_type": "Card", "detail": "Red Card", "minute": 40},
        {"fixture_id": 1, "team_id": 20, "event_type": "Goal", "detail": "Penalty", "minute": 70},
        {"fixture_id": 1, "team_id": 10, "event_type": "Goal", "detail": "Missed Penalty", "minute": 80},
        {"fixture_id": 2, "team_id": 21, "event_type": "Card", "detail": "Red Card", "minute": 30},
        {"fixture_id": 2, "team_id": 11, "event_type": "Goal", "detail": "Normal Goal", "minute": 50}]
    quote = [{"fixture_id": 1, "run_date": "2026-09-20", "back_home": 2.0, "lay_home": 2.02,
              "back_draw": 3.4, "lay_draw": 3.45, "back_away": 4.0, "lay_away": 4.1}]
    partite, conta = O5.partite_da_estrazione({"esiti": esiti, "eventi": eventi, "quote": quote,
                                               "fixture_predictions": []})
    assert conta["partite_con_rosso"] == 2 and conta["scartate_gol_incoerenti"] == 1
    assert len(partite) == 1 and partite[0]["finale"] == [1, 1]
    assert [e["tipo"] for e in partite[0]["eventi"]] == ["gol", "rosso", "gol"]


# ---------------------------------------------------------------------------
# O6
# ---------------------------------------------------------------------------
def test_o6_runner_dalle_righe_di_betfair_market_odds():
    """Colonne VERE (selection, back/lay JSONB [{price,size}], anche come stringa)."""
    from Betfair.stream.backtest.tools.misura_punto8 import o6_coda as O6
    r = O6._runners_da_estrazione([
        {"fixture_id": 7, "run_date": "2026-09-17", "selection": "1 - 0",
         "back": [{"price": 8.0, "size": 3}], "lay": '[{"price": 8.4, "size": 2}]'}])
    x = r[(7, "2026-09-17")][0]
    assert (x.name, x.back_price, x.lay_price) == ("1 - 0", 8.0, 8.4)


def test_o6_esito_aggregati():
    from Betfair.stream.backtest.tools.misura_punto8 import o6_coda as O6
    q = {(h, a) for h in range(4) for a in range(4)}
    assert O6.esito_selezione("Any Other Home Win", 4, 1, q) == 1
    assert O6.esito_selezione("Any Other Home Win", 2, 1, q) == 0
    assert O6.esito_selezione("Any Other Draw", 4, 4, q) == 1
    assert O6.esito_selezione("2 - 1", 2, 1, q) == 1


def test_o6_fasce():
    from Betfair.stream.backtest.tools.misura_punto8 import o6_coda as O6
    assert O6.fascia_di(0.005) == "<=1%" and O6.fascia_di(0.01) == "<=1%"
    assert O6.fascia_di(0.015) == "1-2%" and O6.fascia_di(0.03) == "2-5%"
    assert O6.fascia_di(0.2) is None


def test_o6_p_fusa_con_le_funzioni_di_produzione():
    """Con le quote CS la P_fusa e' `fondi_col_mercato` della produzione."""
    from types import SimpleNamespace
    from Betfair.stream.backtest.tools.misura_punto8 import o6_coda as O6
    from Betfair.omega import omega_proposte as OP
    from Betfair.omega import omega_v3 as V3
    p = OP.parametri_modello()
    runners = [SimpleNamespace(name=n, back_price=10.0, lay_price=10.5)
               for n in O6.NOMI_CS_STANDARD]
    rr = O6.righe_partita(1, (1.3, 1.1), {"goals_home": 1, "goals_away": 1}, p3=p, runners_cs=runners)
    pm = V3.p_mercato_devigata(runners)
    for r in rr:
        assert r["p_fusa"] == pytest.approx(V3.fondi_col_mercato(r["p_modello"], pm(r["nome"]), p))


# ---------------------------------------------------------------------------
# S2
# ---------------------------------------------------------------------------
def _ev(eid, data, n=5, p=0.5, y=1):
    from Betfair.safe_strategy.calibration import CalSample
    return {"event_id": eid, "data": data, "fonte_lambda": "pre_ko",
            "campioni": [CalSample("mo", 10, p, y, eid) for _ in range(n)]}


def test_s2_taglio_mai_nella_stessa_giornata():
    """ROSSO se il taglio separasse due partite dello stesso giorno."""
    from Betfair.stream.backtest.tools.misura_punto8 import s2_calibrazione_uscita as S2
    ev = [_ev("a", "2026-07-01 10:00"), _ev("b", "2026-07-02 10:00"), _ev("c", "2026-07-02 18:00"),
          _ev("d", "2026-07-03 10:00"), _ev("e", "2026-07-04 10:00")]
    stima, prova, taglio = S2.dividi_per_data(ev, 0.4)
    giorni_stima = {e["data"][:10] for e in stima}
    giorni_prova = {e["data"][:10] for e in prova}
    assert not (giorni_stima & giorni_prova)
    assert max(giorni_stima) < min(giorni_prova)


def test_s2_origine_mobile_non_guarda_il_futuro():
    """Ogni giorno di prova e' visto da una tabella stimata SOLO sui giorni prima."""
    from Betfair.stream.backtest.tools.misura_punto8 import s2_calibrazione_uscita as S2
    ev = [_ev(f"e{i}", f"2026-07-0{i+1} 10:00", n=60, p=0.3, y=i % 2) for i in range(6)]
    righe = S2.origine_mobile(ev, quota_minima=0.5)
    assert righe and all(r["giorno"] >= "2026-07-04" for r in righe)
    assert {r["ev"] for r in righe} == {"e3", "e4", "e5"}


def test_s2_valuta_differenza_appaiata():
    from Betfair.stream.backtest.tools.misura_punto8 import s2_calibrazione_uscita as S2
    from Betfair.safe_strategy.calibration import Calibrator
    ev = [_ev(f"e{i}", "2026-07-01 10:00", n=10, p=0.5, y=i % 2) for i in range(12)]
    ris = S2.valuta(ev, {"identita": Calibrator.identity()}, giri=2000)
    t = ris["TUTTE"]
    assert t["diff_brier_identita"]["media"] == pytest.approx(0.0)
    assert t["brier_grezza"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# M1
# ---------------------------------------------------------------------------
def test_m1_p_under_dalla_funzione_di_mike():
    """Chiave VERA `markets_calibrated.over_3_5["True"]`. ROSSO se si leggesse "true"."""
    from Betfair.stream.backtest.tools.misura_punto8 import m1_mike as M1
    assert M1.p_under35_cal_produzione({"markets_calibrated": {"over_3_5": {"True": 0.3, "False": 0.7}}}) \
        == pytest.approx(0.7)
    assert M1.p_under35_cal_produzione({"markets_calibrated": {"over_3_5": {"true": 0.3}}}) is None


def test_m1_pareggio_back_e_soglia():
    from Betfair.stream.backtest.tools.misura_punto8 import m1_mike as M1
    # back a 2,00 con commissione 5 %: p (1)(0,95) = 1-p -> p = 1/1,95
    assert M1.pareggio_back(2.0) == pytest.approx(1 / 1.95)
    nodi = [[0.5, 0.45, 100], [0.7, 0.65, 100], [0.9, 0.88, 100]]
    assert M1.soglia_da_curva(nodi, 0.55) == pytest.approx(0.6)
    assert M1.soglia_da_curva(nodi, 0.99) is None


def test_m1_affidabilita_su_dati_finti():
    """Finti con le chiavi VERE dell'estrazione (o35 = markets_calibrated.over_3_5)."""
    from Betfair.stream.backtest.tools.misura_punto8 import m1_mike as M1
    fps, esiti = [], []
    for i in range(40):
        fps.append({"fixture_id": i, "fixture_date": "2026-09-22T12:00:00+00:00",
                    "o35": {"True": 0.25, "False": 0.75}, "o45": {"True": 0.1, "False": 0.9},
                    "r35": {"True": 0.30, "False": 0.70}, "r45": None})
        gol = 4 if i % 4 == 0 else 2
        esiti.append({"fixture_id": i, "status_short": "FT", "goals_home": gol, "goals_away": 0})
    r = M1.affidabilita({"fixture_predictions": fps, "esiti": esiti}, giri=2000)
    b = r["over_3_5"]["dal_21_09 (FUORI CAMPIONE)"]
    assert b["n"] == 40 and b["freq"] == pytest.approx(0.25)
    assert b["decili_calibrata"][0]["freq_osservata"] == pytest.approx(0.25)
    assert b["brier_calibrata"] < b["brier_grezza"]


def test_m1_conta_legge_gli_stati_del_referto():
    from Betfair.stream.backtest.tools.misura_punto8 import m1_mike as M1
    ref = [{"event_id": "1", "stati": ["WATCH", "HOLD"]}, {"event_id": "2", "stati": ["WATCH"]},
           {"event_id": "3", "stati": ["PRE_LAST_ENTRY_PENDING"]}]
    ext = {"ponte": [{"event_id": "1", "fixture_id": 10}, {"event_id": "2", "fixture_id": 20},
                     {"event_id": "3", "fixture_id": 30}],
           "fixture_predictions": [
               {"fixture_id": 10, "db_json_analisi": {"markets_calibrated": {"over_3_5": {"True": 0.5}}}},
               {"fixture_id": 30, "db_json_analisi": {"markets_calibrated": {"over_3_5": {"True": 0.2}}}}]}
    out = M1.conta(ref, ext, {"2.00": 0.6})
    assert out["entrate_hold_o_persist"] == 2
    assert out["sotto_soglia"]["2.00"]["n"] == 1      # evento 1: p_under 0,5 < 0,6
    assert M1.referto_da_stdout("riga\n[\n {\"a\": 1}\n]") == [{"a": 1}]


# ---------------------------------------------------------------------------
# X1
# ---------------------------------------------------------------------------
def _pagella():
    righe = []
    for eng in ("ml", "poisson"):
        for s in ("H", "D", "A"):
            for fa, hr in (("<.30", 0.2), (".30-.40", 0.3), (".40-.50", 0.4), (".50-.60", 0.5),
                           (".60-.70", 0.55), (">.70", 0.6)):
                righe.append({"engine": eng, "market": "1x2", "selection": s, "league_id": 0,
                              "prob_bucket": fa, "n": 100, "hits": int(hr * 100),
                              "hit_rate": hr, "base_rate": 0.4})
    return righe


def test_x1_calibra_con_la_pagella_e_chiavi_lette_dal_resolver():
    """La riga calibrata si legge con `extract_1x2` VERO. ROSSO se si scrivesse
    una chiave che il resolver non legge (es. 'target_1X2')."""
    from Betfair.stream.backtest.tools.misura_punto8 import x1_bias as X1
    from Betfair.stream.scalper.bias_resolver import extract_1x2
    pag = X1.mappa_pagella(_pagella())
    pred = {"model_predictions_json": {"targets": {"target_1x2": {"H": 0.75, "D": 0.15, "A": 0.10}}},
            "db_json_analisi": {"markets": {"1x2": {"H": 0.65, "D": 0.2, "A": 0.15}}}}
    nuova = X1.riga_calibrata(pred, pag)
    p = extract_1x2(nuova)
    assert p["ml"] == {"H": 0.6, "D": 0.2, "A": 0.2}
    assert p["poisson"] == {"H": 0.55, "D": 0.2, "A": 0.2}


def test_x1_bias_cambia_con_le_p_calibrate():
    """Grezze: consenso H con edge 0,70/0,62-1 = 12,9 % -> bias. Calibrate (pagella
    piu' bassa): p media 0,575 -> edge -7 % -> neutro."""
    from Betfair.stream.backtest.tools.misura_punto8 import x1_bias as X1
    from Betfair.stream.scalper.bias_resolver import resolve_bias
    pag = X1.mappa_pagella(_pagella())
    pred = {"model_predictions_json": {"targets": {"target_1x2": {"H": 0.75, "D": 0.15, "A": 0.10}}},
            "db_json_analisi": {"markets": {"1x2": {"H": 0.65, "D": 0.2, "A": 0.15}}}}
    nomi = {1: "Roma", 2: "Lazio", 3: "The Draw"}
    mid = {"H": 0.62, "D": 0.24, "A": 0.18}
    d0 = resolve_bias(pred, nomi, "Roma", "Lazio", mid)
    d1 = resolve_bias(X1.riga_calibrata(pred, pag), nomi, "Roma", "Lazio", mid)
    assert d0.bias and not d1.bias


def test_x1_concordanza_su_finestra_finta():
    """Chiavi dell'estrazione (ml = target_1x2, po = markets.1x2) + `matches`."""
    from Betfair.stream.backtest.tools.misura_punto8 import x1_bias as X1
    fin = [{"fixture_id": 1, "ml": {"H": 0.6, "D": 0.2, "A": 0.2}, "po": {"H": 0.5, "D": 0.3, "A": 0.2}},
           {"fixture_id": 2, "ml": {"H": 0.6, "D": 0.2, "A": 0.2}, "po": {"H": 0.2, "D": 0.3, "A": 0.5}},
           {"fixture_id": 3, "ml": None, "ml_ft": '{"H": 0.2, "D": 0.2, "A": 0.6}',
            "po": {"H": 0.2, "D": 0.2, "A": 0.6}}]
    es = [{"fixture_id": 1, "goals_home": 2, "goals_away": 0, "status_short": "FT"},
          {"fixture_id": 2, "goals_home": 0, "goals_away": 1, "status_short": "FT"},
          {"fixture_id": 3, "goals_home": 1, "goals_away": 1, "status_short": "FT"}]
    c = X1.concordanza({"finestra_1x2": fin, "esiti": es})
    assert c["n"] == 3 and c["concordi"] == 2 and c["concordi_hit"] == 1
    assert c["discordi_ml_hit"] == 0 and c["discordi_po_hit"] == 1


def test_x1_brier_grezza_contro_calibrata():
    """ML dichiara H 0,75 ma la fascia >.70 esce al 60 %: su 12 partite con esito
    D la calibrata (H 0,6 normalizzata) ha Brier piu' basso. Valore esatto sulla
    grezza: (0,75)^2 + (0,15-1)^2 + 0,10^2 = 1,295. ROSSO se la differenza
    fosse calcolata al contrario (grezza - calibrata)."""
    from Betfair.stream.backtest.tools.misura_punto8 import x1_bias as X1
    pag = X1.mappa_pagella(_pagella())
    fin = [{"fixture_id": i, "ml": {"H": 0.75, "D": 0.15, "A": 0.10},
            "po": {"H": 0.65, "D": 0.2, "A": 0.15}} for i in range(12)]
    es = [{"fixture_id": i, "goals_home": 1, "goals_away": 1, "status_short": "FT"} for i in range(12)]
    r = X1.brier_calibrazione({"finestra_1x2": fin, "esiti": es, "direction_pagella": _pagella()}, pag)
    assert r["ml"]["n"] == 12
    assert r["ml"]["brier_grezza"] == pytest.approx(1.295)
    assert r["ml"]["diff_brier"]["media"] < 0 and r["ml"]["brier_calibrata"] < 1.295
    c = r["consenso_dichiarata_vs_osservata"][">.70"]
    assert c["n"] == 12 and c["p_media_dichiarata"] == pytest.approx(0.70) and c["freq_osservata"] == 0.0


def test_x1_mid_pre_ko_su_registrazione_vera():
    """Sulla registrazione 35797769 (se presente): tre P implicite dal mid."""
    from Betfair.stream.backtest.tools.misura_punto8 import percorsi as P
    from Betfair.stream.backtest.tools.misura_punto8 import x1_bias as X1
    live = P.live_raw()
    if not live or not os.path.isdir(os.path.join(live, "35797769")):
        pytest.skip("registrazione assente")
    b = X1.mid_pre_ko(live, "35797769")
    assert b and len(b["probs"]) == 3
    assert 0.9 < sum(b["probs"].values()) < 1.1


# ---------------------------------------------------------------------------
# T1
# ---------------------------------------------------------------------------
def test_t1_superficie():
    from Betfair.stream.backtest.tools.misura_punto8 import t1_superficie as T1
    assert T1.superficie_da_nome("Wimbledon 2026") == "grass"
    assert T1.superficie_da_nome("ATP Hamburg") == "clay"
    assert T1.superficie_da_nome("US Open") == "hard"
    assert T1.superficie_da_nome("ITF M15 Xyz") == "sconosciuta"


def test_t1_soglie_uguali_al_bot():
    """Le soglie contate sono QUELLE del bot (lette dal sorgente vero)."""
    import re
    from Betfair.stream.backtest.tools.misura_punto8 import t1_superficie as T1
    src = open(os.path.join("Betfair", "stream", "tennis_scalper", "tennis_pro_bot.py"),
               encoding="utf-8").read()
    assert float(re.search(r'"db_lead_games", (\d+)', src).group(1)) == T1.DB_LEAD_GAMES
    assert float(re.search(r'"cf_max_price", ([\d.]+)', src).group(1)) == T1.CF_MAX_PRICE
    assert "srv_games >= 5" in src and T1.SFS_GAME_MIN == 5


def test_t1_punteggi(tmp_path):
    from Betfair.stream.backtest.tools.misura_punto8 import t1_superficie as T1
    import json as _j
    righe = [{"t": 1, "score": {"score": {"home": {"games": "5", "sets": "0", "isServing": True},
                                          "away": {"games": "3", "sets": "0", "isServing": False}}}},
             {"t": 2, "score": {"score": {"home": {"games": "4", "sets": "0", "isServing": False},
                                          "away": {"games": "1", "sets": "0", "isServing": True}}}}]
    f = tmp_path / "x.score.jsonl"
    f.write_text("\n".join(_j.dumps(r) for r in righe), encoding="utf-8")
    out = T1.leggi_punteggi(str(f))
    assert out["stati_serving_for_set"] == 1 and out["stati_double_break"] == 1


# ---------------------------------------------------------------------------
# estrai_db: sola lettura, niente troncamenti
# ---------------------------------------------------------------------------
class _APIError(Exception):
    """Come `postgrest.exceptions.APIError`: attributo `code` e messaggio."""

    def __init__(self, code, message):
        super().__init__({"code": code, "message": message})
        self.code, self.message = code, message


class _Q:
    def __init__(self, sb):
        self._sb, self._f, self._cols = sb, [], []

    def select(self, *_a):
        return self

    def _filtro(self, op, col, fn):
        self._f.append(fn)
        self._cols.append((op, col))
        return self

    def in_(self, col, vals):
        return self._filtro("in", col, lambda r, c=col, v=set(vals): r.get(c) in v)

    def eq(self, col, val):
        return self._filtro("eq", col, lambda r, c=col, v=val: r.get(c) == v)

    def gte(self, col, val):
        return self._filtro("gte", col, lambda r, c=col, v=val: r.get(c) >= v)

    def lt(self, col, val):
        return self._filtro("lt", col, lambda r, c=col, v=val: r.get(c) < v)

    def gt(self, col, val):
        return self._filtro("gt", col, lambda r, c=col, v=val: r.get(c) > v)

    def order(self, col):
        self._ord = col
        return self

    def limit(self, n):
        self._lim = n
        return self

    def execute(self):
        sb = self._sb
        sb.limiti.append(self._lim)
        sb.query.append(list(self._cols))
        # il comportamento del DB VERO sul 25/09: una lettura di una tabella grande
        # filtrata per data SENZA la finestra di un giorno va in statement timeout
        if sb.data_obbligatoria and not (("gte", sb.data_obbligatoria) in self._cols
                                          and ("lt", sb.data_obbligatoria) in self._cols):
            raise _APIError("57014", "canceling statement due to statement timeout")
        if sb.timeout_restanti > 0:
            sb.timeout_restanti -= 1
            raise _APIError("57014", "canceling statement due to statement timeout")
        rr = [r for r in sb.righe if all(f(r) for f in self._f)]
        if getattr(self, "_ord", None):
            rr.sort(key=lambda r: r[self._ord])
        sb.log.append(len(rr[: self._lim]))
        return type("R", (), {"data": rr[: self._lim]})()

    def __getattr__(self, nome):
        if nome in ("insert", "update", "delete", "upsert", "rpc"):
            raise AssertionError(f"SCRITTURA vietata: {nome}")
        raise AttributeError(nome)


class _SB:
    def __init__(self, righe, *, data_obbligatoria=None, timeout_primi=0):
        self.righe, self.log, self.limiti, self.query = righe, [], [], []
        self.data_obbligatoria = data_obbligatoria
        self.timeout_restanti = timeout_primi

    def table(self, _t):
        return _Q(self)


@pytest.fixture
def senza_attese(monkeypatch):
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E
    attese = []
    monkeypatch.setattr(E, "_DORMI", attese.append)
    return attese


def _fp_giorni():
    """fixture_predictions finte (colonne vere) su 5 giorni, fixture_id NON in
    ordine di data (come nel vero: la PK non segue la data)."""
    righe = []
    for i in range(1, 2400):
        g = 20 + (i * 7) % 5
        righe.append({"fixture_id": i, "fixture_date": f"2026-09-{g:02d}T{i % 24:02d}:00:00+00:00",
                      "league_id": 39})
    return righe


def test_estrai_per_giorno_legge_tutto_senza_timeout(senza_attese):
    """Il finto va in 57014 su ogni lettura senza la finestra di un giorno: la
    paginazione per giorno legge TUTTE le righe della finestra [da, a), nessuna
    duplicata. ROSSO se si torna alla keyset sull'intervallo intero."""
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E
    righe = _fp_giorni() + [{"fixture_id": 9999, "fixture_date": "2026-09-25T10:00:00+00:00",
                             "league_id": 1}]
    sb = _SB(righe, data_obbligatoria="fixture_date")
    out = E.keyset_per_giorno(sb, "fixture_predictions", "*", "fixture_date", "fixture_id",
                              "2026-09-20", "2026-09-25", pagina=100)
    ids = [r["fixture_id"] for r in out]
    assert len(ids) == len(set(ids)) == 2399          # 9999 (il 25/09) resta fuori
    assert not senza_attese                           # nessun timeout: nessun ritentativo
    # ogni query porta la finestra di UN giorno
    assert all(("gte", "fixture_date") in q and ("lt", "fixture_date") in q for q in sb.query)


# Le COLONNE VERE delle tabelle lette da `estrai_o1o6` (migrazioni e verifica del
# coordinatore sul DB del 25/09: omega_events NON ha created_at).
COLONNE_VERE = {
    "betfair_market_odds": {"fixture_id", "market_name", "selection", "sort_priority", "back",
                            "lay", "market_id", "run_date", "captured_at"},
    "matches": {"fixture_id", "league_id", "season_year", "fixture_date", "status_short",
                "goals_home", "goals_away", "halftime_home", "halftime_away",
                "home_team_id", "away_team_id"},
    "fixture_predictions": {"fixture_id", "league_id", "fixture_date", "home_team_id",
                            "away_team_id", "updated_at", "db_json_analisi",
                            "tactical_engine_json", "ht_predictions", "percent_home",
                            "percent_draw", "percent_away", "model_predictions_json",
                            "created_at"},
    "omega_events": {"event_id", "name", "open_date", "markets", "updated_at", "country_code",
                     "competition_id", "competition_name", "fixture_id", "league_id",
                     "home_team_id", "away_team_id", "model", "stato_utente"},
}


class _TabellaVera(_Q):
    """Il finto di una tabella con le sue colonne VERE: filtrare o ordinare su
    una colonna che non esiste da' 42703, come PostgREST."""

    def __init__(self, sb, tab):
        super().__init__(sb)
        self._tab = tab

    def _controlla(self, col):
        if col not in COLONNE_VERE[self._tab]:
            raise _APIError("42703", f"column {self._tab}.{col} does not exist")

    def _filtro(self, op, col, fn):
        self._controlla(col)
        return super()._filtro(op, col, fn)

    def order(self, col):
        self._controlla(col)
        return super().order(col)

    def execute(self):
        self._sb.righe = self._sb.tabelle[self._tab]
        return super().execute()


class _DBVero(_SB):
    def __init__(self, tabelle):
        super().__init__([])
        self.tabelle = tabelle

    def table(self, t):
        return _TabellaVera(self, t)


def test_estrai_o1o6_con_le_colonne_vere(senza_attese):
    """`estrai_o1o6` su un finto che conosce SOLO le colonne vere. ROSSO se si
    filtra omega_events su una colonna inesistente (created_at: il 42703 del 25/09)."""
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E
    bmo = []
    for fid, rd in ((10, "2026-09-17"), (11, "2026-09-23")):
        for sp, nome in ((1, "Casa"), (2, "Ospite"), (3, "The Draw")):
            bmo.append({"fixture_id": fid, "market_name": "Match Odds", "selection": nome,
                        "sort_priority": sp, "back": [{"price": 2.0 + sp, "size": 5}],
                        "lay": [{"price": 2.1 + sp, "size": 5}], "run_date": rd})
        bmo.append({"fixture_id": fid, "market_name": "Correct Score", "selection": "1 - 0",
                    "sort_priority": 2, "back": [{"price": 8.0, "size": 1}],
                    "lay": [{"price": 8.4, "size": 1}], "run_date": rd})
    tab = {"betfair_market_odds": bmo,
           "matches": [{"fixture_id": 10, "goals_home": 1, "goals_away": 0, "status_short": "FT"}],
           "fixture_predictions": [{"fixture_id": 11, "fixture_date": "2026-09-23T15:00:00+00:00"}],
           "omega_events": [{"event_id": "35000001", "fixture_id": 10,
                             "open_date": "2026-09-17T18:00:00+00:00",
                             "updated_at": "2026-09-17T20:00:00+00:00",
                             "model": {"lambda_source": "fixture"}}]}
    out = E.estrai_o1o6(_DBVero(tab), "2026-09-09", "2026-09-26")
    assert sorted(q["fixture_id"] for q in out["quote"]) == [10, 11]
    assert len(out["quote_cs"]) == 2 and len(out["esiti"]) == 1
    assert [e["event_id"] for e in out["omega_events_lambda_source"]] == ["35000001"]


def test_estrai_giorni():
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E
    assert E.giorni("2026-09-29", "2026-10-02") == [
        ("2026-09-29", "2026-09-30"), ("2026-09-30", "2026-10-01"), ("2026-10-01", "2026-10-02")]


def test_estrai_ritenta_su_57014_con_pagina_dimezzata(senza_attese):
    """Due timeout di fila: attese 2 s e 4 s, pagina 1000 -> 500 -> 250, e poi
    tutte le righe lette. ROSSO se il 57014 risale al primo colpo."""
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E
    righe = [{"fixture_id": i} for i in range(700)]
    sb = _SB(righe, timeout_primi=2)
    out = E.keyset(sb, "t", "*", "fixture_id", pagina=1000)
    assert [r["fixture_id"] for r in out] == list(range(700))
    assert senza_attese == [2.0, 4.0]
    assert sb.limiti[:3] == [1000, 500, 250]


def test_estrai_tre_timeout_risalgono(senza_attese):
    """Al terzo 57014 si smette: l'errore risale (mai un file troncato in silenzio)."""
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E
    sb = _SB([{"fixture_id": 1}], timeout_primi=3)
    with pytest.raises(_APIError):
        E.keyset(sb, "t", "*", "fixture_id")
    assert len(senza_attese) == 2


def test_estrai_errore_non_timeout_non_si_ritenta(senza_attese):
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E

    class _Rotto(_SB):
        def table(self, _t):
            raise _APIError("42703", "column does not exist")
    with pytest.raises(_APIError):
        E.keyset(_Rotto([]), "t", "*", "fixture_id")
    assert senza_attese == []


def test_estrai_a_blocchi_dimezza_su_57014(senza_attese):
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E
    righe = [{"fixture_id": f} for f in range(300)]
    sb = _SB(righe, timeout_primi=1)
    out = E.a_blocchi(sb, "matches", "*", "fixture_id", range(300), blocco=200)
    assert sorted(r["fixture_id"] for r in out) == list(range(300))
    assert senza_attese == [2.0]


def test_estrai_a_blocchi_dimezza_se_pieno():
    """Un blocco che torna al tetto viene DIMEZZATO e riletto: nessuna riga persa.
    ROSSO se il blocco pieno fosse accettato (troncamento silenzioso)."""
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E
    righe = [{"fixture_id": f, "sel": s} for f in range(20) for s in range(7)]
    sb = _SB(righe)
    out = E.a_blocchi(sb, "t", "*", "fixture_id", range(20), blocco=20, tetto=50)
    assert len(out) == 140


def test_estrai_keyset_legge_tutto():
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E
    righe = [{"fixture_id": i} for i in range(2345)]
    out = E.keyset(_SB(righe), "t", "*", "fixture_id", pagina=1000)
    assert [r["fixture_id"] for r in out] == list(range(2345))


def test_estrai_nessuna_scrittura_nel_sorgente():
    """Il file delle estrazioni non contiene NESSUN metodo di scrittura PostgREST."""
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E
    src = open(E.__file__, encoding="utf-8").read()
    for vietato in (".insert(", ".update(", ".delete(", ".upsert(", ".rpc("):
        assert vietato not in src, vietato


def test_estrai_eventi_da_file(tmp_path):
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E
    import json as _j
    f1 = tmp_path / "t1.json"
    f1.write_text(_j.dumps({"per_evento": [{"event_id": "3"}, {"event_id": "1"}, {"event_id": "3"}]}))
    assert E.eventi_da_file(str(f1)) == ["1", "3"]
    f2 = tmp_path / "cert.txt"
    f2.write_text("testo del referto\n[\n {\"event_id\": \"35760084\", \"stati\": []}\n]")
    assert E.eventi_da_file(str(f2)) == ["35760084"]


def test_estrai_formato_quote_m2():
    from Betfair.stream.backtest.tools.misura_punto8 import estrai_db as E
    mo = [{"fixture_id": 5, "run_date": "2026-09-17", "sort_priority": 1,
           "back": [{"price": 2.0, "size": 10}], "lay": [{"price": 2.02, "size": 5}]},
          {"fixture_id": 5, "run_date": "2026-09-17", "sort_priority": 3,
           "back": '[{"price": 3.4, "size": 10}]', "lay": []}]
    q = E.quote_mo_formato_m2(mo)
    assert q == [{"fixture_id": 5, "run_date": "2026-09-17", "back_home": 2.0, "lay_home": 2.02,
                  "back_draw": 3.4, "lay_draw": None}]
