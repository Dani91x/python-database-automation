"""Test del fan-out delle righe feature causato dal merge `standings`.

Causa radice (21/09/2026): la tabella `standings` ha una riga per
(lega, stagione, squadra, GRUPPO). Nelle leghe con piu' classifiche per stagione
(Argentina "Apertura, Group A" + "Anual" + "Promedios" = 3, Uruguay/Bolivia = 2)
il merge in feature_pipeline moltiplica la riga della fixture per
n_gruppi_casa * n_gruppi_trasferta (9, 4, ...). predict_ensemble accetta
esattamente 1 riga => quelle fixture finivano in `errors` e restavano senza
`model_predictions_json` nel DB, ogni giorno.

Tutti i dati sono FINTI ma con le IDENTICHE chiavi e tipi del vero
(fixture_predictions / standings, come li restituisce PostgREST). Nessun DB.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytest


# -- Finti con chiavi e tipi identici al vero --------------------------------

def _fixture_row(fixture_id: int = 1493151, league_id: int = 999128) -> Dict[str, Any]:
    """Riga di `fixture_predictions` come la restituisce PostgREST."""
    return {
        "fixture_id": int(fixture_id),
        "league_id": int(league_id),
        "league_name": "Liga Profesional Argentina",
        "season_year": 2026,
        "fixture_date": "2026-09-21T00:30:00+00:00",
        "home_team_id": 438,
        "home_team_name": "Talleres Cordoba",
        "away_team_id": 452,
        "away_team_name": "Gimnasia L.P.",
        "status": "NS",
        "goals_home_line": None,
        "goals_away_line": None,
        "under_over_line": None,
        "percent_home": "45%",
        "percent_draw": "28%",
        "percent_away": "27%",
        "win_or_draw": False,
        "advice": "Double chance : Talleres Cordoba or draw",
        "winner_team_id": None,
        "winner_name": None,
        "raw_json_odds": None,
    }


def _standings_row(league_id: int, team_id: int, gruppo: str, rank: int) -> Dict[str, Any]:
    """Riga di `standings` come la restituisce PostgREST (colonne reali)."""
    return {
        "league_id": int(league_id),
        "season_year": 2026,
        "team_id": int(team_id),
        "team_name": f"Team {team_id}",
        "rank": int(rank),
        "played": 9,
        "win": 4,
        "draw": 3,
        "lose": 2,
        "goals_for": 12,
        "goals_against": 9,
        "goals_diff": 3,
        "points": 15,
        "form": "WDLWW",
        "standing_group": gruppo,
        "description": None,
    }


_GRUPPI_HOME = ["Apertura, Group A", "Anual 2026", "Promedios 2026"]
_GRUPPI_AWAY = ["Apertura, Group B", "Anual 2026", "Promedios 2026"]

_HIST_COLS = [
    "fixture_id", "league_id", "season_year", "fixture_date",
    "home_team_id", "home_team_name", "away_team_id", "away_team_name",
    "goals_home", "goals_away",
]


def _fanout_reale(monkeypatch, n_home: int, n_away: int) -> pd.DataFrame:
    """Esegue il CODICE DI PRODUZIONE (feature_pipeline) con standings finte e
    restituisce il DataFrame delle feature: e' la riproduzione della causa radice."""
    from ai_engine import feature_pipeline as fp

    riga = _fixture_row()
    league_id = riga["league_id"]
    standings = (
        [_standings_row(league_id, riga["home_team_id"], g, i + 1)
         for i, g in enumerate(_GRUPPI_HOME[:n_home])]
        + [_standings_row(league_id, riga["away_team_id"], g, i + 5)
           for i, g in enumerate(_GRUPPI_AWAY[:n_away])]
    )
    monkeypatch.setattr(
        fp, "fetch_standings_by_league_seasons", lambda league_seasons: list(standings)
    )

    fixtures_df = pd.DataFrame([riga])
    history_df = pd.DataFrame(columns=_HIST_COLS)
    return fp.build_feature_dataframe_for_fixtures(
        fixtures_df, history_df, [(league_id, 2026)],
        include_odds=False, include_events=False, include_team_stats=False,
        include_player_stats=False, include_team_window_stats=False, pre_match=True,
    )


# -- 1. Riproduzione della causa radice --------------------------------------

class TestCausaRadice:
    @pytest.mark.parametrize("n_home,n_away,attese", [(3, 3, 9), (2, 2, 4), (1, 1, 1)])
    def test_merge_standings_moltiplica_le_righe(self, monkeypatch, n_home, n_away, attese):
        out = _fanout_reale(monkeypatch, n_home, n_away)
        assert len(out) == attese, (
            f"{n_home} gruppi casa x {n_away} trasferta devono dare {attese} righe"
        )

    def test_le_righe_differiscono_solo_sulle_colonne_standings(self, monkeypatch):
        out = _fanout_reale(monkeypatch, 3, 3)
        num = out.select_dtypes(include=["number", "bool"])
        non_std = num.drop(
            columns=[c for c in num.columns
                     if c.startswith(("home_standings_", "away_standings_"))],
            errors="ignore",
        )
        assert not non_std.empty
        assert len(non_std.drop_duplicates()) == 1, (
            "le 9 righe devono essere identiche su tutte le feature non-standings"
        )
        # e le colonne standings, invece, differiscono davvero (fan-out per gruppo)
        assert out["home_standings_standing_group"].nunique() == 3
        assert out["away_standings_standing_group"].nunique() == 3


# -- 2. Il collasso a 1 riga -------------------------------------------------

class TestCollapseStandingsFanout:
    def test_riduce_a_una_riga_conservando_le_feature(self, monkeypatch):
        from ai_engine.predict_fixture import _collapse_standings_fanout

        out = _fanout_reale(monkeypatch, 3, 3)
        ridotto = _collapse_standings_fanout(out, 1493151)

        assert len(ridotto) == 1
        num_prima = out.select_dtypes(include=["number", "bool"])
        num_dopo = ridotto.select_dtypes(include=["number", "bool"])
        non_std = [c for c in num_dopo.columns
                   if not c.startswith(("home_standings_", "away_standings_"))]
        for c in non_std:
            a = num_prima[c].iloc[0]
            b = num_dopo[c].iloc[0]
            assert (a == b) or (pd.isna(a) and pd.isna(b)), f"colonna {c} alterata"

    def test_no_op_con_una_sola_riga(self, monkeypatch):
        from ai_engine.predict_fixture import _collapse_standings_fanout

        out = _fanout_reale(monkeypatch, 1, 1)
        ridotto = _collapse_standings_fanout(out, 1493151)
        assert len(ridotto) == 1
        pd.testing.assert_frame_equal(
            ridotto.reset_index(drop=True), out.reset_index(drop=True)
        )

    def test_solleva_se_le_righe_differiscono_su_una_feature_vera(self, monkeypatch):
        """Guardia: se la moltiplicazione NON viene dalle classifiche (righe con
        feature diverse) l'errore deve restare VISIBILE, non essere ingoiato."""
        from ai_engine.predict_fixture import _collapse_standings_fanout

        out = _fanout_reale(monkeypatch, 3, 3).copy()
        out["elo_diff"] = [float(i) for i in range(len(out))]  # feature vera diversa
        with pytest.raises(RuntimeError, match="feature numeriche DIVERSE"):
            _collapse_standings_fanout(out, 1493151)


# -- 2b. La guardia copre TUTTI i dtype, non solo i numerici -----------------

class TestGuardiaTutteLeColonne:
    """La guardia deve accorgersi di una differenza su QUALUNQUE colonna che non
    sia home_standings_*/away_standings_*, altrimenti collasserebbe righe diverse
    scegliendone una a caso (dato perso in silenzio)."""

    def _base(self, monkeypatch) -> pd.DataFrame:
        return _fanout_reale(monkeypatch, 3, 3).copy()

    def test_colonna_object_diversa(self, monkeypatch):
        from ai_engine.predict_fixture import _collapse_standings_fanout

        out = self._base(monkeypatch)
        out["home_team_name"] = [f"Squadra {i}" for i in range(len(out))]
        with pytest.raises(RuntimeError, match="'home_team_name' DIVERSA"):
            _collapse_standings_fanout(out, 1493151)

    def test_colonna_datetime_diversa(self, monkeypatch):
        from ai_engine.predict_fixture import _collapse_standings_fanout

        out = self._base(monkeypatch)
        out["kickoff"] = pd.to_datetime(
            [f"2026-09-21T{10 + i}:00:00" for i in range(len(out))]
        )
        assert out["kickoff"].dtype.kind == "M"
        with pytest.raises(RuntimeError, match="'kickoff' DIVERSA"):
            _collapse_standings_fanout(out, 1493151)

    def test_colonna_categorical_diversa(self, monkeypatch):
        from ai_engine.predict_fixture import _collapse_standings_fanout

        out = self._base(monkeypatch)
        out["fase"] = pd.Categorical(
            ["gruppo", "finale", "gruppo", "finale", "gruppo",
             "finale", "gruppo", "finale", "gruppo"],
            categories=["gruppo", "finale"],
        )
        assert isinstance(out["fase"].dtype, pd.CategoricalDtype)
        with pytest.raises(RuntimeError, match="'fase' DIVERSA"):
            _collapse_standings_fanout(out, 1493151)

    def test_colonna_dict_diversa(self, monkeypatch):
        """raw_json_odds arriva come dict: deve essere confrontato, non ignorato."""
        from ai_engine.predict_fixture import _collapse_standings_fanout

        out = self._base(monkeypatch)
        out["raw_json_odds"] = [
            {"bookmakers": [{"id": i, "bets": []}]} for i in range(len(out))
        ]
        with pytest.raises(RuntimeError, match="'raw_json_odds' DIVERSA"):
            _collapse_standings_fanout(out, 1493151)

    def test_int64_nullable_diverso(self, monkeypatch):
        from ai_engine.predict_fixture import _collapse_standings_fanout

        out = self._base(monkeypatch)
        out["minuti"] = pd.array([1, 2, 3, 4, 5, 6, 7, 8, pd.NA], dtype="Int64")
        assert str(out["minuti"].dtype) == "Int64"
        with pytest.raises(RuntimeError, match="DIVERSE tra loro|DIVERSA tra le righe"):
            _collapse_standings_fanout(out, 1493151)

    def test_int64_nullable_uguale_con_na_passa(self, monkeypatch):
        from ai_engine.predict_fixture import _collapse_standings_fanout

        out = self._base(monkeypatch)
        out["minuti"] = pd.array([pd.NA] * len(out), dtype="Int64")
        out["gol_attesi"] = pd.array([7] * len(out), dtype="Int64")
        ridotto = _collapse_standings_fanout(out, 1493151)
        assert len(ridotto) == 1
        assert pd.isna(ridotto["minuti"].iloc[0])
        assert ridotto["gol_attesi"].iloc[0] == 7

    def test_nulli_uguali_non_sollevano(self, monkeypatch):
        """NaN == NaN, None == None, NaT == NaT: righe identiche, si collassa."""
        from ai_engine.predict_fixture import _collapse_standings_fanout

        out = self._base(monkeypatch)
        out["metrica"] = [float("nan")] * len(out)          # colonna numerica
        out["nota"] = [None] * len(out)                     # object, stesso oggetto
        out["quando"] = pd.to_datetime([None] * len(out))   # NaT
        # object con NaN DISTINTI: non sono lo stesso oggetto e `==` e' False,
        # quindi solo un confronto che tratta NaN==NaN li accetta.
        out["nan_object"] = pd.Series(
            [float("nan") for _ in range(len(out))], dtype=object
        )
        assert out["nan_object"].dtype == object
        primo, secondo = out["nan_object"].iloc[0], out["nan_object"].iloc[1]
        assert primo is not secondo and not (primo == secondo)
        ridotto = _collapse_standings_fanout(out, 1493151)
        assert len(ridotto) == 1
        assert pd.isna(ridotto["metrica"].iloc[0])
        assert ridotto["nota"].iloc[0] is None
        assert pd.isna(ridotto["quando"].iloc[0])
        assert pd.isna(ridotto["nan_object"].iloc[0])

    def test_nullo_contro_non_nullo_solleva(self, monkeypatch):
        from ai_engine.predict_fixture import _collapse_standings_fanout

        out = self._base(monkeypatch)
        out["nota"] = [None] * (len(out) - 1) + ["valore"]
        with pytest.raises(RuntimeError, match="'nota' DIVERSA"):
            _collapse_standings_fanout(out, 1493151)

    def test_solo_colonne_standings_collassa_e_logga(self, caplog):
        """Nessuna colonna da confrontare: si collassa comunque, ma il caso NON
        passa in silenzio (riga di log)."""
        import logging

        from ai_engine.predict_fixture import _collapse_standings_fanout

        df = pd.DataFrame({
            "home_standings_standing_group": ["Anual 2026", "Promedios 2026"],
            "home_standings_rank": [3, 5],
            "away_standings_standing_group": ["Anual 2026", "Promedios 2026"],
            "away_standings_rank": [7, 9],
        })
        with caplog.at_level(logging.WARNING, logger="ai_engine.predict_fixture"):
            ridotto = _collapse_standings_fanout(df, 1493151)
        assert len(ridotto) == 1
        assert any("nessuna colonna da confrontare" in r.getMessage()
                   for r in caplog.records)


# -- 2c. La riga tenuta e' deterministica ------------------------------------

class TestDeterminismoRigaTenuta:
    """`fetch_standings_by_league_seasons` non ordina: senza ordinamento stabile la
    riga tenuta (e quindi le standings_* che finiscono in build_coverage_report)
    cambierebbe da un run all'altro."""

    def test_permutazioni_danno_lo_stesso_risultato(self, monkeypatch):
        from ai_engine.predict_fixture import _collapse_standings_fanout

        base = _fanout_reale(monkeypatch, 3, 3)
        assert len(base) == 9

        atteso = _collapse_standings_fanout(base, 1493151)
        permutazioni = [
            [8, 0, 5, 3, 1, 7, 2, 6, 4],
            list(reversed(range(9))),
            [2, 3, 4, 5, 6, 7, 8, 0, 1],
        ]
        for ordine in permutazioni:
            permutato = base.iloc[ordine].reset_index(drop=True)
            ottenuto = _collapse_standings_fanout(permutato, 1493151)
            pd.testing.assert_frame_equal(ottenuto, atteso)

    def test_riga_tenuta_e_la_prima_in_ordine_di_gruppo(self, monkeypatch):
        from ai_engine.predict_fixture import _collapse_standings_fanout

        base = _fanout_reale(monkeypatch, 3, 3)
        ridotto = _collapse_standings_fanout(base, 1493151)
        atteso_home = sorted(base["home_standings_standing_group"].tolist())[0]
        assert ridotto["home_standings_standing_group"].iloc[0] == atteso_home
        sotto = base[base["home_standings_standing_group"] == atteso_home]
        assert (ridotto["away_standings_standing_group"].iloc[0]
                == sorted(sotto["away_standings_standing_group"].tolist())[0])


# -- 3. predict_fixture end-to-end (senza DB, senza storage) -----------------

class _FakeQuery:
    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def update(self, *a, **k):  # pragma: no cover - non deve mai accadere
        raise AssertionError("scrittura su DB con store=False")

    def execute(self):
        return SimpleNamespace(data=[])


class _FakeSupabase:
    def table(self, _name: str):
        return _FakeQuery()


def _modello_finto():
    """EnsemblePayload serializzato come sul disco (dict), con un modello sklearn
    vero: percorso ensemble_v2 => passa da predict_ensemble, come in produzione."""
    from sklearn.linear_model import LogisticRegression

    rng = np.random.RandomState(0)
    X = pd.DataFrame({
        "elo_diff": rng.normal(0, 50, 200),
        "h2h_avg_goals": rng.normal(2.5, 0.8, 200),
    })
    y = np.where(X["elo_diff"] + rng.normal(0, 10, 200) > 0, "True", "False")
    clf = LogisticRegression(max_iter=500).fit(X.to_numpy(dtype=float), y)
    return {
        "model_type": "ensemble_v2",
        "features": ["elo_diff", "h2h_avg_goals"],
        "base_models": [("logreg", clf)],
        "meta_model": None,
        "scaler": None,
        "feature_medians": {"elo_diff": 0.0, "h2h_avg_goals": 2.5},
        "class_labels": ["False", "True"],
        "base_weights": {"logreg": 1.0},
        "metrics": {},
        "isotonic_calibrators": {},
        "calibration_metrics": {"brier": 0.21, "ece": 0.04},
    }


def _registry_row(league_id: int) -> List[Dict[str, Any]]:
    """Riga di `ai_model_registry` come la restituisce PostgREST."""
    return [{
        "target": "target_over_2_5",
        "model_name": "ensemble_v2",
        "storage_bucket": f"ai-models-league-{league_id}",
        "storage_path": "ensemble_v2_target_over_2_5.pkl.gz",
        "features_version": "v1",
        "targets_version": "v1",
        "trained_at": "2026-09-20T03:11:42.512Z",
    }]


def _predici(monkeypatch, tmp_path, features_df: pd.DataFrame) -> Dict[str, Any]:
    from ai_engine import predict_fixture as pf

    riga = _fixture_row()
    league_id = riga["league_id"]
    history_df = pd.DataFrame([
        {
            "fixture_id": 1000 + i, "league_id": league_id, "season_year": 2026,
            "fixture_date": f"2026-0{(i % 8) + 1}-10T20:00:00+00:00",
            "home_team_id": 438, "home_team_name": "Talleres Cordoba",
            "away_team_id": 452, "away_team_name": "Gimnasia L.P.",
            "goals_home": 1, "goals_away": 1,
        }
        for i in range(20)
    ])

    monkeypatch.setattr(pf, "ROOT", str(tmp_path))
    monkeypatch.setattr(pf, "fetch_fixture_prediction_by_id", lambda fid: [dict(riga)])
    monkeypatch.setattr(pf, "get_supabase_client", lambda: _FakeSupabase())
    monkeypatch.setattr(pf, "_get_league_data", lambda lid, last_n: {
        "ts": 0.0,
        "seasons": [2024, 2025, 2026],
        "league_seasons": [(lid, 2024), (lid, 2025), (lid, 2026)],
        "history_df": history_df,
        "deep_match_df": history_df,
        "deep_is_history": True,
        "history_fetch_cache": {},
    })
    monkeypatch.setattr(
        pf, "build_feature_dataframe_for_fixtures",
        lambda *a, **k: features_df.copy(),
    )
    monkeypatch.setattr(pf, "_get_model_registry", lambda lid: _registry_row(lid))
    monkeypatch.setattr(pf, "_download_model", lambda bucket, path, out_path: None)
    payload = _modello_finto()
    monkeypatch.setattr(pf, "_load_model_cached", lambda path: payload)
    pf._POST_CAL_CACHE.clear()

    return pf.predict_fixture(riga["fixture_id"], store=False)


class TestPredictFixtureConFanout:
    def test_nove_righe_danno_la_stessa_predizione_di_una(self, monkeypatch, tmp_path):
        """Senza il collasso questo test e' ROSSO: predict_ensemble solleva
        'accetta esattamente 1 riga, ricevute 9'."""
        fanout = _fanout_reale(monkeypatch, 3, 3)
        fanout = fanout.assign(elo_diff=42.0, h2h_avg_goals=2.75)
        una = fanout.head(1).reset_index(drop=True)

        res_9 = _predici(monkeypatch, tmp_path / "a", fanout)
        res_1 = _predici(monkeypatch, tmp_path / "b", una)

        probs = res_9["targets"]["target_over_2_5"]
        assert set(probs) == {"True", "False"}
        assert abs(sum(probs.values()) - 1.0) < 1e-6
        assert all(0.0 <= v <= 1.0 for v in probs.values())

        volatili = {"run_id", "generated_at"}
        assert ({k: v for k, v in res_9.items() if k not in volatili}
                == {k: v for k, v in res_1.items() if k not in volatili}), (
            "la predizione con fan-out deve essere identica a quella senza"
        )
