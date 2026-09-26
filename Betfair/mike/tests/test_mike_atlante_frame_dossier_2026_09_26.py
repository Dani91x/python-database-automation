"""Mike e l'atlante v4: reperti del test e2e del 26/09/2026. File ASCII-only.

R-FA-2: ``dossier.live_frame`` calcola ``hazard_versione``, ``hazard_fase``,
``hazard_recupero_atteso_min``, ``hazard_nota`` ma il frame live costruito da
``service._run_event`` (``ev["live"]``, persistito in ``mike_events.live``) non
le copiava: 0/166 frame. Ora le porta (solo diagnostica, nessun gate).

R-FA-3: ``dossier.build_prematch`` valorizzava lega e id squadra SOLO se c'erano
i lambda: con la riga di ``fixture_predictions`` senza lambda Mike consultava
l'atlante sul globale, senza lega ne' forza. Ora lega e id sempre, se noti.
Il produttore vero e' ``Betfair.stream.db.get_fixture_prematch_lambdas``
(``con_squadre=True``, chiamato da ``mike.db.fixture_lambdas``).
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Dict

from Betfair.mike import dossier as D
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_respiro_scritture_2026_09_13 import (  # noqa: F401 (db = fixture)
    NOW, _giro, _partita, _riga_feed, db,
)

CHIAVI_V4 = ("hazard_versione", "hazard_fase", "hazard_recupero_atteso_min", "hazard_nota")


# ------------------------------------------------------------------ R-FA-2
def test_il_frame_live_porta_le_chiavi_v4_del_dossier(db, monkeypatch):
    vero = D.live_frame

    def con_v4(dossier: Dict[str, Any], **kw: Any) -> Dict[str, Any]:
        out = vero(dossier, **kw)
        # stessi tipi di consulta_atlante_v4 -> live_frame (dossier.py)
        out.update({"hazard_versione": "v4", "hazard_fase": "recupero_2T",
                    "hazard_recupero_atteso_min": 4.6,
                    "hazard_nota": "storico v4 (A*): lega 142, forza non usata"})
        return out
    monkeypatch.setattr(D, "live_frame", con_v4)
    ko = NOW - timedelta(minutes=95)
    db.eventi = {"E1": _partita("E1", inplay=True, ko=ko)}
    db.righe_feed = [_riga_feed("E1", NOW, inplay=True, minute=92, gol_casa=1, gol_ospiti=0, ko=ko)]
    _giro(db, NOW)
    live = db.eventi["E1"]["live"]
    assert live.get("inplay") is True and "hazard_atlas" in live       # frame costruito
    assert live["hazard_versione"] == "v4"
    assert live["hazard_fase"] == "recupero_2T"
    assert live["hazard_recupero_atteso_min"] == 4.6
    assert live["hazard_nota"].startswith("storico v4")


def test_senza_atlante_le_chiavi_ci_sono_e_valgono_none(db):
    ko = NOW - timedelta(minutes=30)
    db.eventi = {"E1": _partita("E1", inplay=True, ko=ko)}
    db.righe_feed = [_riga_feed("E1", NOW, inplay=True, minute=30, gol_casa=0, gol_ospiti=0, ko=ko)]
    _giro(db, NOW)
    live = db.eventi["E1"]["live"]
    assert all(k in live and live[k] is None for k in CHIAVI_V4)


# ------------------------------------------------------------------ R-FA-3
class _SB:
    """Finto supabase-py sulla catena vera table().select().eq().limit().execute()."""

    def __init__(self, riga: Dict[str, Any]) -> None:
        self.riga = riga

    def table(self, nome: str) -> "_SB":
        assert nome == "fixture_predictions"
        return self

    def select(self, colonne: str) -> "_SB":
        self._col = colonne.split(",")
        return self

    def eq(self, *a: Any) -> "_SB":
        return self

    def limit(self, *a: Any) -> "_SB":
        return self

    def execute(self) -> Any:
        return SimpleNamespace(data=[{k: self.riga.get(k) for k in self._col}])


# riga vera della partita Liga F del 26/09 (fixture 1573593): lega e squadre, lambda assenti
RIGA_SENZA_LAMBDA = {"league_id": 142, "home_team_id": 19896, "away_team_id": 22018,
                     "tactical_engine_json": None, "db_json_analisi": {"inputs": {}}}


def test_produttore_senza_lambda_da_lega_e_squadre_solo_con_squadre(monkeypatch):
    from Betfair.stream import db as SDB
    monkeypatch.setattr(SDB, "get_supabase_client", lambda: _SB(RIGA_SENZA_LAMBDA))
    assert SDB.get_fixture_prematch_lambdas(1573593) is None                  # Omega/runner: invariato
    assert SDB.get_fixture_prematch_lambdas(1573593, con_squadre=True) == (None, None, 142, 19896, 22018)


class _MikeDB:
    """Finto db di Mike: stesse funzioni di ``Betfair/mike/db.py``; fixture_lambdas
    passa dal produttore VERO (stream.db) sopra un supabase finto."""

    def fixture_id_for_event(self, event_id: str) -> int:
        return 1573593

    def fixture_lambdas(self, fid: int) -> Any:
        from Betfair.mike import db as MDB
        return MDB.fixture_lambdas(fid)

    def fixture_analysis(self, fid: int) -> Any:
        return None


def test_dossier_senza_lambda_ha_lega_e_id_squadra(monkeypatch):
    from Betfair.stream import db as SDB
    monkeypatch.setattr(SDB, "get_supabase_client", lambda: _SB(RIGA_SENZA_LAMBDA))
    dos = D.build_prematch("35000001", _MikeDB())
    assert (dos["league_id"], dos["home_team_id"], dos["away_team_id"]) == (142, 19896, 22018)
    assert dos["lambda_home"] is None and dos["lambda_away"] is None
    assert dos["source"] == "none"                     # i lambda non vengono dalla fixture
    assert dos["p4_pre"] is None


def test_dossier_con_lambda_invariato(monkeypatch):
    from Betfair.stream import db as SDB
    riga = dict(RIGA_SENZA_LAMBDA, db_json_analisi={"inputs": {"lambda_home": 1.4, "lambda_away": 1.0}})
    monkeypatch.setattr(SDB, "get_supabase_client", lambda: _SB(riga))
    dos = D.build_prematch("35000001", _MikeDB())
    assert (dos["lambda_home"], dos["lambda_away"], dos["source"]) == (1.4, 1.0, "fixture")
    assert (dos["league_id"], dos["home_team_id"], dos["away_team_id"]) == (142, 19896, 22018)
