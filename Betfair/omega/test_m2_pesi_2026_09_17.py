# -*- coding: utf-8 -*-
"""Test di CONTRATTO di ``Betfair/omega/tools/m2_pesi.py`` (delegato M2, 17/09/2026).

Regola della casa (memoria `feedback_i_finti_devono_parlare_come_il_vero`): un finto
nei test ha le IDENTICHE chiavi e gli identici tipi del vero. Il 15/09 i finti scritti
in camelCase hanno certificato un bug e sono usciti 32 ordini veri in loop. Qui i finti
hanno le chiavi di ``fixture_predictions`` (``db_json_analisi.inputs.lambda_home``,
``tactical_engine_json.lambda_home``, ``percent_home/draw/away``), di
``betfair_market_odds`` (``back``/``lay`` come liste di ``{price,size}``) e di
``omega_minute_transitions`` (``league_id,bucket,score,target,result,n``).

Ogni test e' stato FALSIFICATO: la falsificazione e' scritta nel docstring del test.
"""
from __future__ import annotations

import math
import os

import pytest

from Betfair.omega.tools import m2_pesi as T


# ---------------------------------------------------------------------------
# finti con le chiavi VERE
# ---------------------------------------------------------------------------
def riga_fixture_predictions(*, poisson=(1.60, 1.10), tattico=(1.50, 1.20),
                             percent=(45.0, 27.0, 28.0)) -> dict:
    """Una riga di ``fixture_predictions`` come la restituisce PostgREST."""
    riga = {
        "fixture_id": 1515877,
        "league_id": 365,
        "league_name": "Virsliga",
        "fixture_date": "2026-06-30T16:00:00+00:00",
        "home_team_id": 4979,
        "away_team_id": 8305,
        "db_json_analisi": None,
        "tactical_engine_json": None,
        "percent_home": None, "percent_draw": None, "percent_away": None,
    }
    if poisson:
        riga["db_json_analisi"] = {
            "model": "poisson_xg_hybrid_dc",
            "inputs": {"dc_rho": -0.13, "lambda_home": poisson[0], "lambda_away": poisson[1]},
            "markets": {}, "markets_calibrated": {},
        }
    if tattico:
        riga["tactical_engine_json"] = {"lambda_home": tattico[0], "lambda_away": tattico[1],
                                        "markets": {}, "top_scores": []}
    if percent:
        riga["percent_home"], riga["percent_draw"], riga["percent_away"] = percent
    return riga


def quote_match_odds(back=(2.10, 3.40, 3.60), lay=(2.14, 3.50, 3.70)) -> dict:
    """``quote_1x2`` come le costruisce ``m2_pesi`` da ``betfair_market_odds``
    (mercato ``Match Odds``, ``sort_priority`` 1=casa 2=trasferta 3=pareggio)."""
    return {"back_home": back[0], "lay_home": lay[0],
            "back_away": back[1], "lay_away": lay[1],
            "back_draw": back[2], "lay_draw": lay[2]}


# ---------------------------------------------------------------------------
# 1. lettura delle fonti dalle chiavi vere
# ---------------------------------------------------------------------------
def test_fonti_da_evento_legge_le_chiavi_vere():
    """Falsificato: togliendo ``inputs`` da ``db_json_analisi`` la fonte
    ``fixture`` sparisce -> il test diventa rosso."""
    ev = {"fixture_predictions": riga_fixture_predictions(),
          "quote_1x2": quote_match_odds(),
          "storico": {"forza": [1.4, 1.2], "forma": [1.5, 1.1],
                      "h2h": [1.3, 1.3], "lega": [1.45, 1.15]}}
    fonti = T.fonti_da_evento(ev)
    assert set(fonti) == {"mercato", "fixture", "tattico", "api", "forza", "forma", "h2h", "lega"}
    assert fonti["fixture"] == (1.60, 1.10)
    assert fonti["tattico"] == (1.50, 1.20)
    assert fonti["mercato"][0] > 0 and fonti["mercato"][1] > 0


def test_camelcase_non_viene_letto():
    """La lezione del 15/09: una chiave in camelCase NON e' la chiave vera.
    Falsificato: se ``fonti_da_evento`` leggesse anche ``lambdaHome``, l'assert
    ``"fixture" not in fonti`` diventerebbe rosso."""
    riga = riga_fixture_predictions(poisson=None, tattico=None, percent=None)
    riga["db_json_analisi"] = {"inputs": {"lambdaHome": 1.6, "lambdaAway": 1.1}}
    riga["tactical_engine_json"] = {"lambdaHome": 1.5, "lambdaAway": 1.2}
    fonti = T.fonti_da_evento({"fixture_predictions": riga})
    assert "fixture" not in fonti
    assert "tattico" not in fonti
    assert fonti == {}


def test_db_json_analisi_come_stringa_json():
    """PostgREST puo' consegnare il JSONB gia' decodificato o come stringa: entrambe
    devono funzionare. Falsificato: senza ``_json`` la stringa non viene letta."""
    import json as _json
    riga = riga_fixture_predictions(tattico=None, percent=None)
    riga["db_json_analisi"] = _json.dumps(riga["db_json_analisi"])
    fonti = T.fonti_da_evento({"fixture_predictions": riga})
    assert fonti["fixture"] == (1.60, 1.10)


# ---------------------------------------------------------------------------
# 2. la fusione
# ---------------------------------------------------------------------------
def test_pool_logaritmico_e_media_geometrica_pesata():
    """Il numero, non la parola: con pesi 1 e 3 su lambda 1 e 2, il pool logaritmico
    da' exp((1*ln1 + 3*ln2)/4) = 2^0,75. Falsificato: con la media ARITMETICA
    (1*1+3*2)/4 = 1,75 il test e' rosso (2^0,75 = 1,6818)."""
    out = T.fondi({"mercato": (1.0, 1.0), "fixture": (2.0, 2.0)},
                  {"mercato": 1.0, "fixture": 3.0},
                  {"cv0": 0.2, "c_disp": 0.0, "c_mancanza": 0.0})
    assert out is not None
    assert abs(out["lh"] - 2.0 ** 0.75) < 1e-9
    assert abs(out["la"] - 2.0 ** 0.75) < 1e-9


def test_peso_zero_non_entra_nella_fusione():
    """Falsificato: se il peso 0 entrasse, ``fonti_usate`` conterrebbe ``fixture``."""
    out = T.fondi({"mercato": (1.5, 1.2), "fixture": (9.0, 9.0)},
                  {"mercato": 1.0, "fixture": 0.0}, dict(T.CV_PRIOR))
    assert out["fonti_usate"] == ("mercato",)
    assert abs(out["lh"] - 1.5) < 1e-9


def test_nessuna_fonte_torna_none():
    """Nessuna fonte = si salta la partita, MAI a occhi chiusi.
    Falsificato: un ritorno con lambda di comodo renderebbe l'assert rosso."""
    assert T.fondi({}, dict(T.PESI_PRIOR), dict(T.CV_PRIOR)) is None
    assert T.intensita_prematch({"fixture_predictions": {}}) is None


# ---------------------------------------------------------------------------
# 3. LA DEGRADAZIONE CON GRAZIA (il cuore dell'ordine del 17/09)
# ---------------------------------------------------------------------------
def test_meno_fonti_piu_incertezza():
    """Meno fonti -> cv piu' largo. Falsificato: con ``c_mancanza`` = 0 i due cv
    sono uguali e il test diventa rosso."""
    pesi = dict(T.PESI_PRIOR)
    cvp = dict(T.CV_PRIOR)
    tutte = T.fondi({"mercato": (1.5, 1.2), "fixture": (1.5, 1.2), "tattico": (1.5, 1.2),
                     "api": (1.5, 1.2), "forza": (1.5, 1.2), "forma": (1.5, 1.2),
                     "h2h": (1.5, 1.2), "lega": (1.5, 1.2)}, pesi, cvp)
    sola = T.fondi({"mercato": (1.5, 1.2)}, pesi, cvp)
    assert sola["cv"] > tutte["cv"]
    assert sola["copertura"] < tutte["copertura"]


def test_piu_incertezza_piu_coda():
    """La conseguenza che il motore v4 usa: cv piu' largo -> la coda pesa di piu'
    -> p_sup piu' alto -> prezzo di riserva piu' basso -> meno ingressi.
    Falsificato: se ``residual_grid`` ignorasse il cv le due masse sarebbero uguali."""
    import Betfair.omega.omega_model as M
    g_basso = M.residual_grid(1.5, 1.2, T.RHO, T.MAX_GOALS, dixon_coles=True, cv=0.15)
    g_alto = M.residual_grid(1.5, 1.2, T.RHO, T.MAX_GOALS, dixon_coles=True, cv=0.60)
    coda_b = sum(p for p in g_basso.values() if p <= 0.02)
    coda_a = sum(p for p in g_alto.values() if p <= 0.02)
    assert coda_a > coda_b


def test_fonti_in_disaccordo_alzano_il_cv():
    """Falsificato: con ``c_disp`` = 0 i due cv coincidono."""
    pesi = {"mercato": 1.0, "fixture": 1.0}
    cvp = dict(T.CV_PRIOR)
    daccordo = T.fondi({"mercato": (1.5, 1.2), "fixture": (1.5, 1.2)}, pesi, cvp)
    litigano = T.fondi({"mercato": (1.5, 1.2), "fixture": (3.0, 2.4)}, pesi, cvp)
    assert litigano["cv"] > daccordo["cv"]


# ---------------------------------------------------------------------------
# 4. il contratto col motore
# ---------------------------------------------------------------------------
def test_intensita_prematch_si_spacchetta_in_cinque():
    """La firma promessa al costruttore: (lam_casa, lam_tras, cv, fonti, pesi).
    Falsificato: cambiando l'ordine dei campi della NamedTuple il test e' rosso."""
    ev = {"fixture_predictions": riga_fixture_predictions(),
          "quote_1x2": quote_match_odds()}
    lam_h, lam_a, cv, fonti, pesi = T.intensita_prematch(
        ev, pesi=dict(T.PESI_PRIOR), cv=dict(T.CV_PRIOR))
    assert lam_h > 0 and lam_a > 0
    assert 0.0 < cv <= 1.0
    assert "mercato" in fonti and "fixture" in fonti
    assert abs(sum(pesi.values()) - 1.0) < 1e-6


def test_intensita_prematch_e_pura():
    """Niente rete, niente database, niente orologio: se ``m2_pesi`` chiamasse il
    DB questo test fallirebbe con l'errore del client. Falsificato: aggiungendo
    una ``_sb()`` dentro ``fonti_da_evento`` il test diventa rosso."""
    ev = {"fixture_predictions": riga_fixture_predictions(), "quote_1x2": quote_match_odds()}
    a = T.intensita_prematch(ev, pesi=dict(T.PESI_PRIOR), cv=dict(T.CV_PRIOR))
    b = T.intensita_prematch(ev, pesi=dict(T.PESI_PRIOR), cv=dict(T.CV_PRIOR))
    assert a == b


# ---------------------------------------------------------------------------
# 5. LA FALSIFICAZIONE CHIESTA DAL MANDATO: un peso invertito peggiora la metrica
# ---------------------------------------------------------------------------
def _campione_finto(n: int = 120):
    """Partite finte in cui la VERITA' e' la fonte ``mercato`` e ``rumore`` e'
    scorrelato: chi pesa il rumore DEVE perdere."""
    import random
    rng = random.Random(20260917)
    righe = []
    for i in range(n):
        lh = 0.8 + 1.6 * rng.random()
        la = 0.6 + 1.4 * rng.random()
        gh = sum(1 for _ in range(12) if rng.random() < lh / 12.0)
        ga = sum(1 for _ in range(12) if rng.random() < la / 12.0)
        righe.append({
            "fixture_id": 900000 + i, "insieme": "test", "run_date": "2026-08-01",
            "league_id": 1, "fixture_date": "2026-08-01T00:00:00+00:00",
            "fonti": {"mercato": (lh, la),
                      "rumore": (0.3 + 3.0 * rng.random(), 0.3 + 3.0 * rng.random())},
            "esito": {"fixture_id": 900000 + i, "status_short": "FT",
                      "goals_home": gh, "goals_away": ga,
                      "halftime_home": None, "halftime_away": None},
            "mercato_back": (lh, la),
        })
    return righe


def test_falsificazione_peso_invertito_peggiora():
    """Il banco sa diventare rosso: se si sposta il peso dalla fonte VERA a una
    fonte di RUMORE, la log-loss fuori campione deve peggiorare. Se non peggiorasse,
    la taratura non misurerebbe niente. Falsificato al contrario: invertendo il
    verso dell'assert il test e' rosso."""
    righe = _campione_finto()
    cvp = {"cv0": 0.25, "c_disp": 0.0, "c_mancanza": 0.0}
    giusto, _ = T.misura_arm(righe, "fusione", {"mercato": 1.0, "rumore": 0.0}, cvp)
    invertito, _ = T.misura_arm(righe, "fusione", {"mercato": 0.0, "rumore": 1.0}, cvp)
    assert giusto["ll_ft"] < invertito["ll_ft"], (giusto["ll_ft"], invertito["ll_ft"])
    assert giusto["brier_ft"] < invertito["brier_ft"]


def test_bootstrap_dichiara_quando_non_migliora():
    """Due bracci IDENTICI: la differenza e' 0 e l'IC contiene 0 -> nessun
    miglioramento dichiarabile. Falsificato: se il bootstrap ricampionasse le
    righe invece delle differenze appaiate, l'IC non sarebbe degenere."""
    a = [{"fixture_id": i, "ll_ft": 3.0 + 0.01 * i} for i in range(50)]
    m, lo, hi = T.bootstrap_differenza(a, list(a), giri=200)
    assert m == 0.0 and lo == 0.0 and hi == 0.0


# ---------------------------------------------------------------------------
# 6. l'hazard: il sistema 2x2 deve RITROVARE le intensita' che hanno generato i dati
# ---------------------------------------------------------------------------
def _transizioni_finte(lh: float, la: float, n_partite: int = 4_000_000):
    """Conteggi ``omega_minute_transitions`` generati da intensita' NOTE e costanti.

    Chiavi identiche alla tabella vera: ``league_id,bucket,score,target,result,n``.
    Si propaga in avanti la catena di Markov a passi di 5 minuti e si registra, per
    ogni stato attraversato, la distribuzione del risultato FINALE.
    """
    passo = T.PASSO_BUCKET / 90.0
    ph, pa = lh * passo, la * passo
    buckets = list(range(0, 90, T.PASSO_BUCKET))
    # distribuzione del punteggio a ogni bucket, partendo da 0-0
    stato = {b: {} for b in buckets}
    stato[0][(0, 0)] = 1.0
    for i, b in enumerate(buckets[:-1]):
        for (h, a), p in stato[b].items():
            d = stato[buckets[i + 1]]
            d[(h, a)] = d.get((h, a), 0.0) + p * (1.0 - ph - pa)
            d[(h + 1, a)] = d.get((h + 1, a), 0.0) + p * ph
            d[(h, a + 1)] = d.get((h, a + 1), 0.0) + p * pa
    # P(finale | stato) per propagazione in avanti da ogni stato
    def finale_da(b_idx: int, sc):
        cur = {sc: 1.0}
        for _ in buckets[b_idx:-1]:
            nxt = {}
            for (h, a), p in cur.items():
                nxt[(h, a)] = nxt.get((h, a), 0.0) + p * (1.0 - ph - pa)
                nxt[(h + 1, a)] = nxt.get((h + 1, a), 0.0) + p * ph
                nxt[(h, a + 1)] = nxt.get((h, a + 1), 0.0) + p * pa
            cur = nxt
        return cur

    righe = []
    for i, b in enumerate(buckets):
        for sc, peso in stato[b].items():
            massa = peso * n_partite
            if massa < 5000:
                continue
            for fin, p in finale_da(i, sc).items():
                n = int(round(massa * p))
                if n <= 0:
                    continue
                righe.append({"league_id": 0, "bucket": b,
                              "score": "%d-%d" % sc, "target": "ft",
                              "result": "%d-%d" % fin, "n": n})
    return righe


def test_hazard_ritrova_le_intensita_vere():
    """Il sistema 2x2 di ``hazard_da_transizioni`` deve ritrovare le lambda che
    hanno GENERATO i conteggi, a meno dell'arrotondamento. Falsificato: usando
    ``A_h(b,S) - A_h(b+1,S)`` grezzo (senza i termini dei rami con gol) l'errore
    supera il 5 % e il test diventa rosso."""
    righe = _transizioni_finte(1.40, 1.05)
    haz = T.hazard_da_transizioni(righe, 0)
    v = haz["0|0-0"]
    assert abs(v["lambda_casa"] - 1.40) < 0.05, v
    assert abs(v["lambda_trasferta"] - 1.05) < 0.05, v
    v = haz["30|1-0"]
    assert abs(v["lambda_casa"] - 1.40) < 0.08, v
    assert abs(v["lambda_trasferta"] - 1.05) < 0.08, v


def test_hazard_stati_troppo_rari_non_entrano():
    """Sotto ``HAZ_N_MIN`` lo stato e' un 'non lo so', non un numero.
    Falsificato: abbassando la soglia a 0 lo stato comparirebbe."""
    righe = [{"league_id": 0, "bucket": 0, "score": "0-0", "target": "ft",
              "result": "1-0", "n": 10},
             {"league_id": 0, "bucket": 5, "score": "0-0", "target": "ft",
              "result": "1-0", "n": 10}]
    assert T.hazard_da_transizioni(righe, 0) == {}


# ---------------------------------------------------------------------------
# 7. la forza delle squadre non deve MAI guardare il futuro
# ---------------------------------------------------------------------------
def _partita(fid, data, lega, casa, tras, gh, ga):
    return {"fixture_id": fid, "league_id": lega, "season_year": 2026,
            "fixture_date": data, "status_short": "FT",
            "goals_home": gh, "goals_away": ga,
            "halftime_home": 0, "halftime_away": 0,
            "home_team_id": casa, "away_team_id": tras}


def test_forza_ignora_le_partite_dopo_il_taglio():
    """Falsificato: togliendo il filtro ``fixture_date < taglio`` la squadra 99
    comparirebbe fra quelle stimate."""
    storia = [_partita(i, "2026-01-%02d" % (1 + i % 28), 1, 10 + i % 4, 20 + i % 4, 2, 1)
              for i in range(60)]
    storia.append(_partita(999, "2026-08-01", 1, 99, 98, 5, 0))
    f = T.ForzaSquadre(storia, "2026-07-01")
    assert 99 not in f.att and 98 not in f.att
    assert 10 in f.att


def test_forma_e_h2h_non_guardano_la_partita_stessa():
    """Falsificato: con ``<=`` invece di ``<`` la partita del giorno entrerebbe
    nella propria forma e i numeri cambierebbero."""
    storia = [_partita(1, "2026-05-01", 1, 10, 20, 1, 0),
              _partita(2, "2026-06-01", 1, 20, 10, 0, 3),
              _partita(3, "2026-07-01", 1, 10, 20, 9, 0)]
    st = T.Storico(storia)
    assert st.forma(10, "2026-07-01") == (2.0, 0.0, 2)
    assert st.h2h(10, 20, "2026-07-01") == (2.0, 0.0, 2)


# ---------------------------------------------------------------------------
# 8. i file consegnati esistono e sono leggibili
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.exists(T.F_PESI), reason="pesi non ancora tarati")
def test_file_dei_pesi_ha_il_contratto():
    pesi, cvp, ripiego = T.carica_pesi()
    assert set(cvp) >= {"cv0", "c_disp", "c_mancanza"}
    assert pesi.get("mercato") == 1.0, "il mercato e' il riferimento di scala"
    assert all(v >= 0.0 for v in pesi.values())
    assert set(pesi) <= set(T.FONTI)
    assert set(ripiego) <= set(T.FONTI) - {"mercato"}


def test_forma_gamma_e_il_cv_detto_in_gamma():
    """``omega_v3`` parla in ``forma_gamma``, ``omega_model`` in ``cv``: devono
    essere lo stesso numero. Falsificato: con a = 1/cv il test e' rosso."""
    assert abs(T.forma_gamma_da_cv(0.30) - 1.0 / 0.09) < 1e-9
    for cv in (0.15, 0.30, 0.55, 0.90):
        assert abs(1.0 / math.sqrt(T.forma_gamma_da_cv(cv)) - cv) < 1e-12


# ---------------------------------------------------------------------------
# 9. IL RIPIEGO: quando il mercato manca non si salta, si diventa PRUDENTI
# ---------------------------------------------------------------------------
def test_ripiego_entra_solo_se_manca_il_peso_misurato():
    """Con i pesi finali (mercato 1, tutto il resto 0) una partita SENZA quote
    userebbe zero fonti: il ripiego evita di saltarla. Falsificato: senza
    ``pesi_ripiego`` la fusione torna None e il test e' rosso."""
    pesi = {"mercato": 1.0, "fixture": 0.0, "forza": 0.0}
    rip = {"fixture": 0.12, "forza": 0.09}
    senza_mercato = {"fixture": (1.5, 1.2), "forza": (1.4, 1.1)}
    assert T.fondi(senza_mercato, pesi, dict(T.CV_PRIOR)) is None
    out = T.fondi(senza_mercato, pesi, dict(T.CV_PRIOR), rip)
    assert out is not None and out["ripiego"] is True
    assert set(out["fonti_usate"]) == {"fixture", "forza"}


def test_ripiego_e_piu_prudente_del_mercato():
    """Il punto dell'ordine del 17/09: meno informazione -> cv piu' largo.
    Falsificato: se la copertura del ripiego fosse calcolata sulla sola scala del
    ripiego varrebbe 1 e i due cv sarebbero uguali."""
    pesi = {"mercato": 1.0, "fixture": 0.0, "forza": 0.0}
    rip = {"fixture": 0.12, "forza": 0.09}
    cvp = dict(T.CV_PRIOR)
    col_mercato = T.fondi({"mercato": (1.5, 1.2)}, pesi, cvp, rip)
    senza = T.fondi({"fixture": (1.5, 1.2), "forza": (1.5, 1.2)}, pesi, cvp, rip)
    assert col_mercato["ripiego"] is False
    assert senza["cv"] > col_mercato["cv"]
    assert senza["copertura"] < col_mercato["copertura"]


def test_mercato_presente_il_ripiego_non_tocca_niente():
    """Falsificato: se il ripiego entrasse anche col mercato presente, le lambda
    non sarebbero piu' quelle del mercato."""
    pesi = {"mercato": 1.0, "fixture": 0.0}
    rip = {"fixture": 0.12}
    out = T.fondi({"mercato": (1.5, 1.2), "fixture": (9.0, 9.0)}, pesi,
                  dict(T.CV_PRIOR), rip)
    assert out["fonti_usate"] == ("mercato",)
    assert abs(out["lh"] - 1.5) < 1e-9
