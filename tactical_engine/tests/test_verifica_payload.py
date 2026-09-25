"""Test dello script di sola lettura tactical_engine/tools/verifica_payload_tacticai.py.

I payload sono costruiti con serving._build_payload (stesse chiavi e stessi tipi del
vero) a partire da un fit col modello DI PRIMA (limiti del dominio di rho disattivati),
cioe' esattamente come sono nati i 17 payload con under_0_5 < 0 del 25/09. Le righe
imitano l'estrazione del coordinatore: {fixture_id, league_id, fixture_date,
tactical_engine_json}. Il rifit usa il finto client Supabase di test_serving.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tactical_engine import model as M  # noqa: E402
from tactical_engine import serving  # noqa: E402
from tactical_engine.model import DixonColesModel  # noqa: E402
from tactical_engine.tests.test_rho_ammissibile import _lega_normale, _lega_poche_x00  # noqa: E402
from tactical_engine.tests.test_serving import TODAY, FakeSupabase  # noqa: E402
from tactical_engine.tools import verifica_payload_tacticai as V  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERI = os.path.join(REPO, "AUDIT_2026-09-25", "payload_tacticai_negativi_2026-09-25.json")
LEGA = 1093


def _storico(ms, league=LEGA, fid0=5_000_000):
    """Righe `matches` (chiavi e tipi del vero) da scoreline sintetiche, nel passato."""
    rows = []
    for k, m in enumerate(ms):
        when = TODAY - timedelta(days=300) + timedelta(hours=12 * k)
        rows.append({
            "fixture_id": fid0 + k, "league_id": league, "fixture_date": when.isoformat(),
            "status_short": "FT", "home_team_id": m.home_id, "away_team_id": m.away_id,
            "goals_home": m.home_goals, "goals_away": m.away_goals,
            "halftime_home": None, "halftime_away": None,
            "fulltime_home": m.home_goals, "fulltime_away": m.away_goals,
        })
    return rows


def _fp_row(fid, home, away, league=LEGA):
    return {
        "fixture_id": fid, "league_id": league, "league_name": "U21", "season_year": 2026,
        "fixture_date": (TODAY + timedelta(hours=4, minutes=30)).isoformat(),
        "home_team_id": home, "home_team_name": f"T{home}", "away_team_id": away,
        "away_team_name": f"T{away}", "status": "ok", "result_status_short": None,
        "tactical_engine_json": None,
    }


def _payload_modello_di_prima(sb, fx, monkeypatch):
    """Payload come lo scriveva il serving prima del fix (stesso percorso di run_for_date)."""
    with monkeypatch.context() as mp:
        mp.setattr(M, "_rho_limits_all_pairs", lambda *a, **k: (-math.inf, math.inf))
        mp.setattr(M, "rho_bounds", lambda *a, **k: (-math.inf, math.inf))
        ft_m, ft_d, _, _ = serving._load_prior(sb, fx["league_id"], TODAY)
        m = DixonColesModel(max_goals=10, half_life_days=serving.HALF_LIFE_CLUB, ridge=serving.RIDGE)
        fit = m.fit(ft_m, dates=ft_d, ref_date=TODAY, fit_home_adv=True)
        st = {r["team_id"]: r for r in m.strength_table()}
        pf = m.predict(fx["home_team_id"], fx["away_team_id"])
    fx2 = dict(fx, status_short=fx["result_status_short"])
    return serving._build_payload(fx2, pf, None, st, fit, False, TODAY.isoformat())


def _mondo(monkeypatch, ms, coppie):
    fps = [_fp_row(7_000_000 + i, h, a) for i, (h, a) in enumerate(coppie)]
    sb = FakeSupabase({"matches": _storico(ms), "fixture_predictions": fps})
    righe = []
    for fx in fps:
        p = _payload_modello_di_prima(sb, fx, monkeypatch)
        righe.append({"fixture_id": fx["fixture_id"], "league_id": fx["league_id"],
                      "fixture_date": fx["fixture_date"], "tactical_engine_json": p})
    return sb, righe


def _coppie_negative(monkeypatch, ms):
    """Coppie che col modello di prima danno under_0_5 < 0 (arrotondato a 4 decimali)."""
    with monkeypatch.context() as mp:
        mp.setattr(M, "_rho_limits_all_pairs", lambda *a, **k: (-math.inf, math.inf))
        mp.setattr(M, "rho_bounds", lambda *a, **k: (-math.inf, math.inf))
        sb = FakeSupabase({"matches": _storico(ms)})
        ft_m, ft_d, _, _ = serving._load_prior(sb, LEGA, TODAY)
        m = DixonColesModel(max_goals=10, half_life_days=serving.HALF_LIFE_CLUB, ridge=serving.RIDGE)
        m.fit(ft_m, dates=ft_d, ref_date=TODAY, fit_home_adv=True)
        return [(h, a) for h in m.fit_.teams for a in m.fit_.teams
                if h != a and round(m.predict(h, a)["markets"]["under_0_5"], 4) < 0]


def test_payload_negativi_diagnosi_e_griglia_valida_dopo(monkeypatch, tmp_path, capsys):
    ms = _lega_poche_x00(2)
    neg = _coppie_negative(monkeypatch, ms)
    assert len(neg) >= 2, "il dataset deve riprodurre il reperto"
    sb, righe = _mondo(monkeypatch, ms, neg[:3])
    # una riga col json come STRINGA (formato possibile dell'estrazione)
    righe[0] = dict(righe[0], tactical_engine_json=json.dumps(righe[0]["tactical_engine_json"]))

    esiti = V.verifica(righe)
    assert len(esiti) == len(righe)
    for e in esiti:
        assert e["under_0_5_scritto"] < 0
        # la formula di prima riproduce il negativo scritto (a meno degli arrotondamenti)
        assert abs(e["under_0_5_ricostruito"] - e["under_0_5_scritto"]) <= 2e-4
        assert not e["rho_nel_dominio"] and e["rho"] > e["rho_hi"]
        assert e["griglia_valida_dopo"] and 0.0 <= e["under_0_5_dopo"] <= 1.0
        assert abs(e["somma_griglia_dopo"] - 1.0) <= 1e-9 and e["cella_min_dopo"] >= 0.0

    f = tmp_path / "payload.json"
    f.write_text(json.dumps(righe), encoding="utf-8")
    assert V.main([str(f)]) == 0
    out = capsys.readouterr().out
    assert f"under_0_5 scritto < 0: {len(righe)}" in out and f"griglie valide dopo: {len(righe)}/{len(righe)}" in out

    # rifit in sola lettura col modello corretto sullo stesso storico
    n_query = len(sb.calls)
    rif = V.rifit(righe, sb)
    assert all(q.update_payload is None for q in sb.calls[n_query:]), "il rifit non deve scrivere"
    for e, r in zip(rif, righe):
        p = r["tactical_engine_json"]
        p = json.loads(p) if isinstance(p, str) else p
        assert e["n_matches_rifit"] == e["n_matches_scritto"]
        assert round(e["rho_stadio1"], 4) == e["rho_scritto"]  # stesso primo stadio di prima
        assert e["vincolo_attivo"] and e["rho_vincolato"] < e["rho_stadio1"] + 1e-12
        assert e["griglia_valida"] and e["under_0_5_rifit"] >= 0.0
    assert V._stampa_rifit(rif) == 0


def test_payload_normale_invariato(monkeypatch):
    ms = _lega_normale(21)
    sb, righe = _mondo(monkeypatch, ms, [(1, 2), (3, 4)])
    for e in V.verifica(righe):
        assert e["rho_nel_dominio"] and e["rho_dopo"] == e["rho"]
        assert e["under_0_5_dopo"] == e["under_0_5_ricostruito"]
        assert abs(e["under_0_5_ricostruito"] - e["under_0_5_scritto"]) <= 2e-4
    for e in V.rifit(righe, sb):
        assert not e["vincolo_attivo"] and e["scarto_max_mercati"] == 0.0
        assert e["squadre_coerenti"] and e["mercato_scarto_max"][3] == 0.0

    # riga di oggi con casa/trasferta invertite rispetto al payload (caso 1533031 del
    # 25/09): lo scarto e' dell'orientamento, non del modello, e lo script lo segnala
    fp = sb.tables["fixture_predictions"][0]
    fp.update(home_team_id=fp["away_team_id"], away_team_id=fp["home_team_id"],
              home_team_name=fp["away_team_name"], away_team_name=fp["home_team_name"])
    inv = V.rifit(righe[:1], sb)[0]
    assert not inv["squadre_coerenti"]
    assert inv["mercato_scarto_max"][0] in ("home", "away", "double_1x", "double_x2")
    # firma dell'inversione: lh' = la * e^g, la' = lh / e^g (g = vantaggio campo)
    p0 = righe[0]["tactical_engine_json"]
    eg = math.exp(p0["training"]["home_adv"])
    assert abs(inv["lambda_home"] - p0["lambda_away"] * eg) < 0.01
    assert abs(inv["lambda_away"] - p0["lambda_home"] / eg) < 0.01


def test_formati_non_validi():
    with pytest.raises(ValueError):
        V.verifica([{"fixture_id": 1, "tactical_engine_json": {"x": 1}}])
    with pytest.raises(ValueError):
        V.verifica([3])


@pytest.mark.skipif(not os.path.exists(VERI), reason="estrazione del coordinatore assente")
def test_i_17_payload_veri():
    with open(VERI, encoding="utf-8") as fh:
        righe = json.load(fh)
    esiti = V.verifica(righe)
    assert len(esiti) == 17
    for e in esiti:
        assert e["under_0_5_scritto"] < 0 and not e["rho_nel_dominio"]
        assert abs(e["under_0_5_ricostruito"] - e["under_0_5_scritto"]) <= 1e-4
        assert e["griglia_valida_dopo"]
