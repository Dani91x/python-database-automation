# -*- coding: utf-8 -*-
"""O5 (25/09/2026) - i CARTELLINI ROSSI nel modello V3 di Omega, dietro
l'interruttore `model_red_cards` (DEFAULT SPENTO).

Decisione dell'utente (25/09 h18): "SE MIGLIORA AGGIUNGILO". Misura:
AUDIT_2026-09-25/MISURA_PUNTO8_2026-09-25.md sez. 2 (77 partite fuori dal fit,
log-loss CS FT al primo rosso -0,113 [-0,187; -0,046]).

Interruttore DEFAULT ACCESO (ordine dell'utente del 25/09 sera: "per TUTTI i
bot i valori statistici e gli aiuti di default accesi"): il ramo spento si prova
passando SEMPRE `model_red_cards=False` per esteso (`SPENTO`).

Cosa si prova:
  * neutro (rossi 0-0, o interruttore spento) = la griglia di PRIMA al 1e-12,
    contro valori d'oro calcolati dal `omega_v3.py` di `origin/master` 43e1468;
  * rosso in casa -> intensita' residua casa x carded_factor e trasferta x
    opponent_factor, letti dal JSON vero (`inplay_intensity_by_league.json`,
    blocco GLOBALE), mai cablati;
  * la matematica e' QUELLA della misura (`o5_rossi.griglia_con_rossi`): stessa
    griglia al 1e-12 con moltiplicatori diversi da 1;
  * l'ingresso (`_v3_select` -> `seleziona_v3`) e l'uscita
    (`omega_proposte.process_proposte_uscita` -> `proposta_uscita`) ricevono gli
    stessi moltiplicatori e vedono la STESSA P del bancato.

I finti parlano come il vero: la riga del feed ha le chiavi dello scanner
(`minute`, `score_home`, `score_away`, `red_home`, `red_away`, blocco `cs`),
lo stato live e' `omega_model.LiveState`, i runner sono `omega_engine.ScoreRunner`.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.omega import omega_config as C
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_model as M
from Betfair.omega import omega_proposte as PR
from Betfair.omega import omega_service as S
from Betfair.omega import omega_v3 as V3
from Betfair.omega.test_omega_proposte_2026_09_17 import (DbFinto, MercatoFinto, _lay,
                                                          _payload_feed)

ADESSO = datetime(2026, 9, 17, 20, 30, tzinfo=timezone.utc)
LAMBDA = (1.45, 1.10)

# ---------------------------------------------------------------------------
# i coefficienti VERI, dal file che legge la produzione (mai cablati qui)
# ---------------------------------------------------------------------------
_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "inplay_intensity_by_league.json")


def _coeff_globali() -> tuple:
    with open(_JSON, encoding="utf-8") as fh:
        rc = json.load(fh)["global"]["red_card"]
    return float(rc["carded_factor"]), float(rc["opponent_factor"])


def _p(**kw: Any) -> Dict[str, Any]:
    return C.resolve_params({"strategy_version": 3, **kw})


ACCESO = {"model_red_cards": True}
SPENTO = {"model_red_cards": False}


# ---------------------------------------------------------------------------
# 0. whitelist
# ---------------------------------------------------------------------------
def test_interruttore_in_whitelist_default_acceso():
    assert C.DEFAULTS["model_red_cards"] is True
    assert _p()["model_red_cards"] is True
    assert C.parametri_v3(_p())["rossi"] is True
    assert C.parametri_v3({})["rossi"] is True
    assert C.parametri_v3(_p(**SPENTO))["rossi"] is False
    assert C.parametri_v3(_p(**ACCESO))["rossi"] is True
    # la stringa "false" dalla UI resta SPENTA, anche su params gia' risolti
    assert C.parametri_v3({"strategy_version": 3, "model_red_cards": "false"})["rossi"] is False


# ---------------------------------------------------------------------------
# 1. neutro = griglia di PRIMA al 1e-12 (valori d'oro dal master 43e1468)
# ---------------------------------------------------------------------------
# (minuto, punteggio, periodo, lambda) -> (firma, P della cella +1/+1, intensita')
# firma = sum(P * (1 + 7h + 13a)) su tutta la griglia finale
_ORO = [
    ((60.0, (0, 0), "ft", (1.45, 1.10)),
     10.569802594673781, 0.08771345476915865, (0.5628122247229675, 0.43323563741757787)),
    ((74.0, (1, 0), "ft", (1.80, 0.95)),
     14.028562405769277, 0.04909290904188838, (0.4466775071436643, 0.22321691221174034)),
    ((30.0, (0, 1), "ht", (1.20, 1.30)),
     18.487446493928534, 0.02977697603113888, (0.19929098982281898, 0.23787784088210376)),
    ((82.0, (2, 2), "ft", None),
     45.32177641756329, 0.030810306092332505, (0.2503484712223968, 0.19764131684718464)),
]


@pytest.mark.parametrize("stato,firma,cella,intens", _ORO)
@pytest.mark.parametrize("modo", ["default", "acceso_senza_rossi", "spento_con_rossi"])
def test_neutro_griglia_identica_a_prima_al_1e_12(stato, firma, cella, intens, modo):
    m, sc, per, lam = stato
    p = PR.parametri_modello()
    if modo == "default":
        kw: Dict[str, Any] = {}
    elif modo == "acceso_senza_rossi":
        kw = {"mult_rossi": E.moltiplicatori_rossi_v3(_p(**ACCESO), 0, 0)}
    else:
        kw = {"mult_rossi": E.moltiplicatori_rossi_v3(_p(**SPENTO), 1, 1)}
    g = V3.griglia_finale(minuto=m, punteggio=sc, periodo=per, p=p, lambdas=lam, **kw)
    assert abs(sum(v * (1 + 7 * h + 13 * a) for (h, a), v in g.items()) - firma) < 1e-12
    assert abs(g[(sc[0] + 1, sc[1] + 1)] - cella) < 1e-12
    ir = V3.intensita_residue(minuto=m, punteggio=sc, periodo=per, p=p, lambdas=lam, **kw)
    assert abs(ir[0] - intens[0]) < 1e-12 and abs(ir[1] - intens[1]) < 1e-12


# ---------------------------------------------------------------------------
# 2. i moltiplicatori vengono dal JSON GLOBALE
# ---------------------------------------------------------------------------
def test_default_acceso_i_rossi_entrano_senza_toccare_niente():
    """25/09 sera: coi parametri di DEFAULT (whitelist risolta da vuoto, e
    anche senza params) un rosso cambia i moltiplicatori."""
    carded, opp = _coeff_globali()
    assert E.moltiplicatori_rossi_v3(_p(), 1, 0) == pytest.approx((carded, opp), abs=1e-12)
    assert E.moltiplicatori_rossi_v3(None, 1, 0) == pytest.approx((carded, opp), abs=1e-12)


def test_rosso_in_casa_intensita_moltiplicate_dal_json():
    carded, opp = _coeff_globali()
    mult = E.moltiplicatori_rossi_v3(_p(**ACCESO), 1, 0)
    assert abs(mult[0] - carded) < 1e-12 and abs(mult[1] - opp) < 1e-12
    p = PR.parametri_modello()
    base = V3.intensita_residue(minuto=60.0, punteggio=(0, 0), periodo="ft", p=p,
                                lambdas=LAMBDA)
    rosso = V3.intensita_residue(minuto=60.0, punteggio=(0, 0), periodo="ft", p=p,
                                 lambdas=LAMBDA, mult_rossi=mult)
    assert abs(rosso[0] / base[0] - carded) < 1e-12
    assert abs(rosso[1] / base[1] - opp) < 1e-12


def test_rosso_in_trasferta_e_doppio_rosso_dal_json():
    carded, opp = _coeff_globali()
    fuori = E.moltiplicatori_rossi_v3(_p(**ACCESO), 0, 1)
    assert abs(fuori[0] - opp) < 1e-12 and abs(fuori[1] - carded) < 1e-12
    due = E.moltiplicatori_rossi_v3(_p(**ACCESO), 2, 0)
    assert abs(due[0] - max(0.25, carded ** 2)) < 1e-12
    assert abs(due[1] - min(2.0, opp ** 2)) < 1e-12


def test_i_coefficienti_sono_globali_mai_per_lega(monkeypatch: pytest.MonkeyPatch):
    """Anche se `live_engine` avesse un blocco per la lega, V3 chiede il
    GLOBALE: `red_card_multipliers(rh, ra, None)`."""
    from Betfair.stream.engine import live_engine as LE
    visti: List[Any] = []
    vero = LE.red_card_multipliers

    def _spia(rh, ra, league_id=None):
        visti.append(league_id)
        return vero(rh, ra, league_id)

    monkeypatch.setattr(LE, "red_card_multipliers", _spia)
    E.moltiplicatori_rossi_v3(_p(**ACCESO), 1, 0)
    assert visti == [None]


# ---------------------------------------------------------------------------
# 3. la matematica e' quella della MISURA
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("minuto,sc,rossi", [(60.0, (0, 0), (1, 0)), (74.0, (1, 0), (0, 1)),
                                             (35.0, (0, 0), (1, 1)), (80.0, (2, 1), (2, 0))])
def test_griglia_coi_rossi_uguale_alla_misura_o5(minuto, sc, rossi):
    from Betfair.stream.backtest.tools.misura_punto8 import o5_rossi as O5
    p = PR.parametri_modello()
    mult = E.moltiplicatori_rossi_v3(_p(**ACCESO), *rossi)
    assert mult != V3.MULT_NEUTRO
    prod = V3.griglia_finale(minuto=minuto, punteggio=sc, periodo="ft", p=p,
                             lambdas=LAMBDA, mult_rossi=mult)
    mis = O5.griglia_con_rossi(minuto=minuto, punteggio=sc, p=p, lambdas=LAMBDA, mult=mult)
    assert set(prod) == set(mis)
    assert max(abs(prod[k] - mis[k]) for k in prod) < 1e-12


def test_rosso_in_casa_sposta_la_massa_verso_la_trasferta():
    p = PR.parametri_modello()
    nomi = ["1 - 0", "0 - 1", "0 - 0"]
    prima = V3.probabilita_selezioni(periodo="ft", minuto=60.0, punteggio=(0, 0),
                                     nomi=nomi, p=p, lambdas=LAMBDA)
    dopo = V3.probabilita_selezioni(periodo="ft", minuto=60.0, punteggio=(0, 0),
                                    nomi=nomi, p=p, lambdas=LAMBDA,
                                    mult_rossi=E.moltiplicatori_rossi_v3(_p(**ACCESO), 1, 0))
    assert dopo["1 - 0"] < prima["1 - 0"]
    assert dopo["0 - 1"] > prima["0 - 1"]


# ---------------------------------------------------------------------------
# 4. ingresso: seleziona_v3 e _v3_select
# ---------------------------------------------------------------------------
def _runners() -> List[E.ScoreRunner]:
    return [E.ScoreRunner(selection_id=13, name="2 - 1", lay_price=60.0, lay_size=9.0,
                          back_price=44.0, back_size=88.75),
            E.ScoreRunner(selection_id=14, name="1 - 1", lay_price=9.4, lay_size=50.0,
                          back_price=9.0, back_size=50.0),
            E.ScoreRunner(selection_id=15, name="0 - 0", lay_price=12.5, lay_size=50.0,
                          back_price=12.0, back_size=50.0)]


def _spia_probabilita(monkeypatch: pytest.MonkeyPatch) -> List[dict]:
    chiamate: List[dict] = []
    vero = V3.probabilita_selezioni

    def _spia(**kw):
        out = vero(**kw)
        chiamate.append({"mult": tuple(kw.get("mult_rossi", V3.MULT_NEUTRO)), "p": dict(out)})
        return out

    monkeypatch.setattr(V3, "probabilita_selezioni", _spia)
    return chiamate


@pytest.mark.parametrize("params,rossi,atteso", [
    ("spento", (1, 0), "neutro"), ("spento", None, "neutro"),
    ("acceso", None, "neutro"), ("acceso", (0, 0), "neutro"), ("acceso", (1, 0), "json")])
def test_seleziona_v3_usa_i_rossi_solo_ad_acceso(monkeypatch, params, rossi, atteso):
    chiamate = _spia_probabilita(monkeypatch)
    pr = _p(**ACCESO) if params == "acceso" else _p(**SPENTO)
    E.seleziona_v3(_runners(), periodo="ft", minuto=74.0, punteggio=(0, 0), params=pr,
                   lambdas=LAMBDA, parametri_modello=PR.parametri_modello(), rossi=rossi)
    assert len(chiamate) == 1
    if atteso == "neutro":
        assert chiamate[0]["mult"] == (1.0, 1.0)
    else:
        carded, opp = _coeff_globali()
        assert chiamate[0]["mult"] == pytest.approx((carded, opp), abs=1e-12)


def test_seleziona_v3_spento_coi_rossi_identico_a_senza_rossi():
    pr = _p(**SPENTO)
    kw = dict(periodo="ft", minuto=74.0, punteggio=(0, 0), params=pr, lambdas=LAMBDA,
              parametri_modello=PR.parametri_modello())
    a = E.seleziona_v3(_runners(), **kw)
    b = E.seleziona_v3(_runners(), rossi=(1, 0), **kw)
    assert a == b


def _v3_select(monkeypatch, params: dict, red_home: int, red_away: int):
    monkeypatch.setattr(S, "_prematch_lambdas",
                        lambda db, eid, payload, **kw: (LAMBDA[0], LAMBDA[1], 39, "pre_ko_odds"))
    monkeypatch.setattr(S, "_v3_p_empirica", lambda db, **kw: None)
    stato = M.LiveState(74, 0, 0, red_home, red_away)
    visti: List[Any] = []
    vero = E.seleziona_v3

    def _spia(runners, **kw):
        visti.append(kw.get("rossi"))
        return vero(runners, **kw)

    monkeypatch.setattr(E, "seleziona_v3", _spia)
    cand, audit, motivo = S._v3_select(
        db=DbFinto(), event_id="35760084", payload=_payload_feed(),
        snapshot=SimpleNamespace(runners=_runners()), state=stato, half=False,
        params=params, aggregates={})
    return visti, audit


def test_v3_select_passa_i_rossi_del_feed_e_li_scrive_in_audit(monkeypatch):
    chiamate = _spia_probabilita(monkeypatch)
    visti, audit = _v3_select(monkeypatch, _p(**ACCESO), 1, 0)
    assert visti == [(1, 0)]
    carded, opp = _coeff_globali()
    assert chiamate[-1]["mult"] == pytest.approx((carded, opp), abs=1e-12)
    assert audit["mult_rossi"] == [round(carded, 4), round(opp, 4)]


def test_v3_select_spento_audit_identico_senza_chiave(monkeypatch):
    chiamate = _spia_probabilita(monkeypatch)
    visti, audit = _v3_select(monkeypatch, _p(**SPENTO), 1, 0)
    assert visti == [(1, 0)]
    assert chiamate[-1]["mult"] == (1.0, 1.0)
    assert "mult_rossi" not in audit


# ---------------------------------------------------------------------------
# 5. uscita: la proposta vede gli STESSI rossi e la STESSA P dell'ingresso
# ---------------------------------------------------------------------------
@pytest.fixture
def _uscita(monkeypatch: pytest.MonkeyPatch):
    S.svuota_le_cache()
    monkeypatch.setattr(S, "_feed_prices_fresh", lambda market, eid: True)
    monkeypatch.setattr(S, "_prematch_lambdas",
                        lambda db, eid, payload, **kw: (LAMBDA[0], LAMBDA[1], 39, "pre_ko_odds"))
    viste: List[dict] = []
    vero = V3.proposta_uscita

    def _spia(posizione, **kw):
        out = vero(posizione, **kw)
        viste.append({"mult": tuple(kw.get("mult_rossi", V3.MULT_NEUTRO)),
                      "p_evento": float(kw["p_evento"]), "proposta": out})
        return out

    monkeypatch.setattr(V3, "proposta_uscita", _spia)
    yield viste
    S.svuota_le_cache()


def _payload_con_rossi(rh: int, ra: int) -> dict:
    pl = _payload_feed()
    pl["red_home"], pl["red_away"] = rh, ra
    return pl


def _gira_uscita(params: dict, payload: dict) -> DbFinto:
    db = DbFinto([_lay()])
    PR.process_proposte_uscita(params=params, market=MercatoFinto(), db=db, now=ADESSO,
                               feed=lambda _eid: payload)
    return db


def _p_ingresso(mult) -> float:
    return V3.probabilita_selezioni(periodo="ft", minuto=74.0, punteggio=(0, 0),
                                    nomi=["2 - 1", "1 - 1", "0 - 0"],
                                    p=PR.parametri_modello(), lambdas=LAMBDA,
                                    mult_rossi=mult)["2 - 1"]


def test_uscita_acceso_vede_i_rossi_con_la_stessa_p_dell_ingresso(_uscita):
    _gira_uscita(_p(**ACCESO), _payload_con_rossi(1, 0))
    assert len(_uscita) == 1
    carded, opp = _coeff_globali()
    assert _uscita[0]["mult"] == pytest.approx((carded, opp), abs=1e-12)
    mult = E.moltiplicatori_rossi_v3(_p(**ACCESO), 1, 0)
    assert abs(_uscita[0]["p_evento"] - _p_ingresso(mult)) < 1e-12
    assert abs(_uscita[0]["p_evento"] - _p_ingresso(V3.MULT_NEUTRO)) > 1e-6


def test_uscita_spento_coi_rossi_identica_a_senza_rossi(_uscita):
    _gira_uscita(_p(**SPENTO), _payload_con_rossi(1, 0))
    _gira_uscita(_p(**SPENTO), _payload_con_rossi(0, 0))
    assert len(_uscita) == 2
    assert _uscita[0]["mult"] == (1.0, 1.0) == _uscita[1]["mult"]
    assert _uscita[0]["p_evento"] == _uscita[1]["p_evento"]
    assert abs(_uscita[0]["p_evento"] - _p_ingresso(V3.MULT_NEUTRO)) < 1e-12
    assert _uscita[0]["proposta"] == _uscita[1]["proposta"]


def test_uscita_acceso_fonte_della_p_dichiara_i_rossi(_uscita):
    db = _gira_uscita(_p(**ACCESO), _payload_con_rossi(1, 0))
    fonti = [str((r.get("payload") or {}).get("p_fonte")) for r in db.richieste]
    fonti += [str(p.get("p_fonte")) for _k, p in db.attivita if p.get("p_fonte")]
    assert fonti and all(f.endswith("+rossi") for f in fonti)
    db0 = _gira_uscita(_p(**SPENTO), _payload_con_rossi(1, 0))
    fonti0 = [str((r.get("payload") or {}).get("p_fonte")) for r in db0.richieste]
    assert fonti0 and not any("+rossi" in f for f in fonti0)


def test_traiettoria_dell_uscita_cambia_coi_rossi():
    """La traiettoria (quanto vale aspettare) usa la stessa griglia: con un
    rosso i punti della traiettoria cambiano."""
    pos = V3.Posizione(periodo="ft", selection_name="2 - 1", lay_price=48.0, size=1.0)
    p = PR.parametri_modello()
    mult = E.moltiplicatori_rossi_v3(_p(**ACCESO), 1, 0)
    a = V3.traiettoria_bloccabile(pos, minuto=74.0, punteggio=(0, 0), p=p, lambdas=LAMBDA,
                                  p_evento_ora=0.02)
    b = V3.traiettoria_bloccabile(pos, minuto=74.0, punteggio=(0, 0), p=p, lambdas=LAMBDA,
                                  p_evento_ora=0.02, mult_rossi=mult)
    assert len(a) == len(b) and len(a) > 1
    assert all(math.isfinite(x.p_evento) for x in b)
    assert any(abs(x.p_evento - y.p_evento) > 1e-9 for x, y in zip(a, b))
    assert any(abs(x.p_invariato - y.p_invariato) > 1e-9 for x, y in zip(a, b))


def test_proposta_uscita_passa_i_rossi_alla_traiettoria():
    """La DECISIONE d'uscita (quanto vale aspettare) cambia coi rossi anche a
    parita' di P di adesso: `proposta_uscita` deve passare i moltiplicatori
    alla traiettoria, non solo riceverli."""
    pos = V3.Posizione(periodo="ft", selection_name="2 - 1", lay_price=48.0, size=1.0)
    p = PR.parametri_modello()
    mult = E.moltiplicatori_rossi_v3(_p(**ACCESO), 1, 0)
    kw = dict(minuto=74.0, punteggio=(0, 0), back_price=44.0, back_size=100.0,
              p_evento=0.02, p=p, lambdas=LAMBDA, commissione=0.05)
    senza = V3.proposta_uscita(pos, **kw)
    con = V3.proposta_uscita(pos, mult_rossi=mult, **kw)
    assert abs(senza.bloccabile_max_atteso - con.bloccabile_max_atteso) > 1e-6
    assert V3.proposta_uscita(pos, mult_rossi=V3.MULT_NEUTRO, **kw) == senza
