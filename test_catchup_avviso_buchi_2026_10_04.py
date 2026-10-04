"""04/10/2026 - Seasons Catchup: rosso SOLO per i guasti veri.

Run rosse 29/09, 01-04/10 (36615357543, 36821373801, 37049359939, 37141249749, 37185437609):
un buco vecchio dovuto solo a "API vuota / in attesa del 2o tentativo / flag coverage False"
metteva exit 1. Regola nuova: quei buchi sono un AVVISO dichiarato (log + GITHUB_STEP_SUMMARY),
exit 0; restano exit 1: ris.errori, degradate persistenti, buchi vecchi con errore API ripetuto
(o partite non tentate / aggregati da fare / fermati per errori_api).
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from typing import Any, Dict, List

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")
os.environ.setdefault("API_FOOTBALL_KEY", "x")

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import season_gaps as sg  # noqa: E402
import seasons_catchup as sc  # noqa: E402

OGGI = date(2026, 10, 4)
MAX_GG = 3


class QuotaFinta:
    stato = None

    def capacita_giornaliera(self) -> int:
        return 7000


def _riga(flag_events=True, flag_stats=False) -> Dict[str, Any]:
    # stesse chiavi del vero record api_coverage_by_season
    return {"league_id": 129, "season_year": 2026, "fixtures_events": flag_events,
            "fixtures_lineups": False, "fixtures_statistics_players": flag_stats,
            "fixtures_statistics_fixtures": flag_stats, "odds": False}


def _voce(conteggi: Dict[str, Dict[str, int]], riga=None, aggregati=None) -> sc.Voce:
    lac = sg.Lacune(129, 2026, partite_totali=10, ft_totali=10, conteggi=conteggi)
    if aggregati:
        lac.aggregati = aggregati
    return sc.Voce(row=riga or _riga(), lacune=lac, priorita=2, stato_prec=None)


def _lancia(voce, errori=None, degradate=None, fermate=None, rimaste=None, giorni=10):
    k = voce.chiave
    ris = sc.Risultato()
    ris.errori = list(errori or [])
    ris.aperto_dal = {k: (OGGI - timedelta(days=giorni)).isoformat()}
    ris.fermate_per = dict(fermate or {})
    ris.rimaste = list(rimaste or [])
    if degradate:
        ris.degradate_timeout = [k]
        ris.degradate_consecutivi = {k: degradate}
    righe: List[str] = []
    codice = sc.referto_buchi([voce], ris, QuotaFinta(), MAX_GG, {}, righe.append, OGGI)
    return codice, "\n".join(righe)


def test_solo_api_vuota_exit0_e_avviso_dichiarato(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    v = _voce({"match_events": {"in_attesa": 9}})
    codice, log = _lancia(v)
    assert codice == 0
    assert sc.TITOLO_AVVISO_BUCHI in log
    assert "BUCHI CHE L'API NON RIEMPIE (avviso, non guasto)" in log
    assert "AVVISO BUCO API VUOTO: lega 129 stagione 2026 aperto da 10 gg" in log
    assert "API vuota su 9 partite-tabella" in log
    assert "BUCO VECCHIO" not in log


def test_flag_coverage_false_e_api_vuota_exit0(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    v = _voce({"match_events": {"in_attesa": 2}}, riga=_riga(flag_events=True, flag_stats=False))
    codice, log = _lancia(v)
    assert codice == 0
    assert "flag coverage False (non richieste)" in log


def test_errore_api_ripetuto_exit1(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    v = _voce({"match_events": {"errore": 1}})
    codice, log = _lancia(v)
    assert codice == 1
    assert "BUCO VECCHIO: lega 129 stagione 2026" in log
    assert "errore API ripetuto su 1 partite-tabella" in log
    assert sc.TITOLO_AVVISO_BUCHI not in log


def test_errore_api_misto_ad_api_vuota_exit1(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    v = _voce({"match_events": {"in_attesa": 5, "errore": 1}})
    codice, log = _lancia(v)
    assert codice == 1
    assert "BUCO VECCHIO" in log


def test_partite_non_tentate_exit1(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    v = _voce({"match_events": {"in_attesa": 5, "da_chiamare": 3}})
    codice, log = _lancia(v)
    assert codice == 1
    assert "BUCO VECCHIO" in log


def test_fermato_per_errori_api_exit1(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    v = _voce({"match_events": {"in_attesa": 5}})
    codice, log = _lancia(v, fermate={v.chiave: "errori_api"})
    assert codice == 1
    assert "10 partite di fila con tutti gli endpoint in errore" in log


def test_errori_veri_exit1(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    v = _voce({"match_events": {"in_attesa": 9}})
    codice, log = _lancia(v, errori=["lega 129 stagione 2026: boom"])
    assert codice == 1
    assert "ERRORE: lega 129 stagione 2026: boom" in log


def test_degradate_persistenti_exit1(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    v = _voce({})
    codice, log = _lancia(v, degradate=MAX_GG + 1)
    assert codice == 1
    assert "DEGRADATA PERSISTENTE" in log


def test_nessun_buco_exit0_db_senza_buchi(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    v = _voce({})
    codice, log = _lancia(v)
    assert codice == 0
    assert "DB SENZA BUCHI" in log
    assert sc.TITOLO_AVVISO_BUCHI not in log


def test_buco_recente_nessun_avviso(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    v = _voce({"match_events": {"in_attesa": 9}})
    codice, log = _lancia(v, giorni=1)
    assert codice == 0
    assert sc.TITOLO_AVVISO_BUCHI not in log


def test_riepilogo_scritto_su_github_step_summary(monkeypatch, tmp_path):
    f = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(f))
    v = _voce({"match_events": {"in_attesa": 9}})
    codice, _ = _lancia(v)
    assert codice == 0
    t = f.read_text(encoding="utf-8")
    assert sc.TITOLO_AVVISO_BUCHI in t
    assert "BUCHI CHE L'API NON RIEMPIE (avviso, non guasto)" in t
    assert "lega 129 stagione 2026 aperto da 10 gg" in t
    assert "API vuota su 9 partite-tabella" in t


def test_senza_variabile_nessun_errore_e_nessun_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.chdir(tmp_path)
    v = _voce({"match_events": {"in_attesa": 9}})
    codice, log = _lancia(v)
    assert codice == 0
    assert list(tmp_path.iterdir()) == []


def test_riepilogo_non_scritto_se_percorso_illeggibile_non_rompe(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "manca" / "s.md"))
    v = _voce({"match_events": {"in_attesa": 9}})
    codice, log = _lancia(v)
    assert codice == 0
    assert "riepilogo del job non scritto" in log


def test_solo_api_vuota_senza_partite_in_attesa_non_e_avviso():
    # Senza in_attesa, errori, chiamate e aggregati il buco e' irraggiungibile da referto_buchi
    # (lac.aperti() vale 0 e la lega-stagione viene saltata), ma la funzione resta prudente:
    # nessuna "API vuota" provata -> non e' un avviso.
    v = _voce({})
    assert sc._solo_api_vuota(v.lacune, v.flags, None) is False
    v2 = _voce({"match_events": {"in_attesa": 1}})
    assert sc._solo_api_vuota(v2.lacune, v2.flags, None) is True
