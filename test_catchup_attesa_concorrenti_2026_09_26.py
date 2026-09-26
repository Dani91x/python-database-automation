"""R-CATCHUP-1 (26/09/2026): il catchup del mattino ASPETTA le action concorrenti.

Evidenza e2e (run 36223432528): la catena Daily -> Mapper -> Catchup avvia il catchup alle 06:20Z
mentre il Retrain (agganciato allo stesso Daily, 06:18-07:13Z) e' in corso: "STOP prima di lega 78:
action concorrente in_progress: retrain_models.yml", 0 chiamate. Ora il catchup, prima di iniziare,
ricontrolla ogni 2 min (al massimo CATCHUP_ATTESA_CONCORRENTI_MAX_MINUTI) e parte appena libero.

Finto GitHub = quello di test_riserva_dinamica (GET .../actions/workflows/{file}/runs con `status`,
`per_page`, risposta {"total_count", "workflow_runs"}), qui con anche retrain_models.yml.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import List, Optional

os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "x"
os.environ["SUPABASE_KEY"] = "x"
os.environ["API_FOOTBALL_KEY"] = "x"

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import seasons_catchup as sc  # noqa: E402
import test_riserva_dinamica_2026_09_25 as trd  # noqa: E402

RETRAIN = "retrain_models.yml"
trd.NOMI.setdefault(RETRAIN, "Retrain ML Models (cloud, all leagues)")
MATTINA = datetime(2026, 9, 26, 6, 18, 52, tzinfo=timezone.utc)


class Tempo:
    """Orologio finto: dormi() fa avanzare il tempo e, dopo `fine_dopo` secondi, chiude il Retrain."""

    def __init__(self, gh: trd.FintoGitHub, fine_dopo: Optional[float]) -> None:
        self.t = 1_000_000.0
        self.t0 = self.t
        self.gh = gh
        self.fine_dopo = fine_dopo
        self.sonni: List[float] = []

    def orologio(self) -> float:
        return self.t

    def dormi(self, sec: float) -> None:
        self.sonni.append(sec)
        self.t += sec
        if self.fine_dopo is not None and self.t - self.t0 >= self.fine_dopo:
            for r in self.gh.runs:
                if r["_wf"] == RETRAIN and r["status"] == "in_progress":
                    r["status"], r["conclusion"] = "completed", "success"


def _mondo(retrain_in_corso: bool, fine_dopo: Optional[float]):
    gh = trd.FintoGitHub()
    if retrain_in_corso:
        gh.run(RETRAIN, MATTINA, status="in_progress")
    return gh, Tempo(gh, fine_dopo), trd._controllo(gh)


def test_aspetta_la_fine_del_retrain_e_poi_parte():
    gh, tempo, conc = _mondo(True, fine_dopo=55 * 60)          # il Retrain del 26/09 e' durato ~55 min
    righe: List[str] = []
    esito = sc.attendi_action_concorrenti(conc, 90, stampa=righe.append, dormi=tempo.dormi, orologio=tempo.orologio)
    assert esito is None                                        # via libera: il catchup lavora
    assert tempo.sonni == [120] * 28                            # 28 x 2 min = 56 min >= 55
    assert any("ATTESA: action concorrente in_progress: retrain_models.yml" in r for r in righe)
    assert righe[-1].startswith("[CATCHUP] ATTESA FINITA dopo 56 min")
    # ogni ricontrollo interroga davvero GitHub (forza=True, niente cache di 2 min)
    assert sum(1 for q in gh.richieste if q["url"].endswith(f"/{RETRAIN}/runs")) >= 29


def test_attesa_scaduta_restituisce_il_motivo_e_non_supera_il_tetto():
    gh, tempo, conc = _mondo(True, fine_dopo=None)              # il Retrain non finisce mai
    righe: List[str] = []
    esito = sc.attendi_action_concorrenti(conc, 90, stampa=righe.append, dormi=tempo.dormi, orologio=tempo.orologio)
    assert esito == "action concorrente in_progress: retrain_models.yml"
    assert sum(tempo.sonni) == 90 * 60                          # mai oltre il tetto dichiarato
    assert righe[-1].startswith("[CATCHUP] ATTESA SCADUTA dopo 90/90 min")


def test_nessuna_action_concorrente_nessuna_attesa():
    gh, tempo, conc = _mondo(False, fine_dopo=None)
    righe: List[str] = []
    assert sc.attendi_action_concorrenti(conc, 90, stampa=righe.append, dormi=tempo.dormi,
                                         orologio=tempo.orologio) is None
    assert tempo.sonni == [] and righe == []


def test_senza_token_nessuna_attesa():
    conc = sc.ControlloConcorrenza(env={}, http_get=trd.FintoGitHub().get)
    sonni: List[float] = []
    assert sc.attendi_action_concorrenti(conc, 90, stampa=lambda _r: None, dormi=sonni.append) is None
    assert sonni == []


def test_main_aspetta_prima_di_eseguire(monkeypatch):
    import api_client
    import db_client
    ordine: List[str] = []
    monkeypatch.setenv("CATCHUP_ATTESA_CONCORRENTI_MAX_MINUTI", "90")
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: object())
    monkeypatch.setattr(api_client, "APIFootballClient", lambda: object())
    monkeypatch.setattr(sc, "ControlloConcorrenza", lambda: "conc")
    monkeypatch.setattr(sc, "GestoreQuota", lambda **kw: "quota")

    def attendi(conc, attesa_max_min, *a, **kw):
        ordine.append(f"attendi {conc} {attesa_max_min}")
        return None

    class Ris:
        codice = 0

    def esegui(sb, client, quota, conc):
        ordine.append("esegui")
        return Ris()
    monkeypatch.setattr(sc, "attendi_action_concorrenti", attendi)
    monkeypatch.setattr(sc, "esegui_catchup", esegui)
    assert sc.main([]) == 0
    assert ordine == ["attendi conc 90", "esegui"]
