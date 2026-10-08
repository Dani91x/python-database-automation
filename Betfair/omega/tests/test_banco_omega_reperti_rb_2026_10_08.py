"""BANCO DI OMEGA 08/10 (cantiere 7) - i reperti RB-1 ... RB-5 del 07/10
(`AUDIT_2026-10-07/OMEGA_APERTURA_35760084.md` sez. 10), lato replay di Omega.

* RB-1: la chiusura di Betfair entra nello SCANNER del banco
  (`OmegaCert.process_closed_market`: flumine non passa i book CLOSED a
  `process_market_book`).
* RB-2: le esposizioni di Omega dette allo scanner nella forma di produzione
  (`esposizioni_omega` -> `safe_strategy.db._righe_esposte`).
* RB-3: l'«adesso» del verdetto sul flusso e' l'orologio di MERCATO nel replay
  (`AmbienteOmega` aggancia `flusso_prezzi._ora_ms`).
* RB-4: lo scenario `paper` gira con la PORTA DEL RUNNER del banco
  (`trasporto.contesto("omega", "canale")`).
* RB-5: le cache di processo che `svuota_le_cache` non tocca (le due tabelle
  storiche `_EMPIRICAL_CACHE` / `_MINUTE_CACHE` e quelle del riavvio, fra cui
  `_LEG_RETRY`) azzerate fra uno scenario e il successivo e al riavvio
  (elenco ESPLICITO del banco).

Oggetti VERI: `ScannerReplay`, la strategia del banco `OmegaCert` costruita dal
suo costruttore, `MarketBook` dalla cache di betfairlightweight sul raw vero
(`registrazioni_banco/35760084`), `DbMemoriaOmega`, le funzioni di produzione
`omega_service._empirical_table` / `_minute_table`. ASCII-only.
"""
from __future__ import annotations

import os

import pytest

from Betfair.omega import omega_config
from Betfair.omega import omega_service as S
from Betfair.omega.tools import replay_registrazioni as R
from Betfair.safe_strategy import db as SDB
from Betfair.stream import flusso_prezzi as FP
from Betfair.stream.backtest import banco_comune as B
from Betfair.stream.backtest import trasporto as TRA
from Betfair.stream.tests.test_banco_scanner_reperti_rb_2026_10_08 import (  # noqa: F401
    EVENTO, HT, MO, _a, _banco, _libro, _ms, punteggi)


def _strategia(banco: B.ScannerReplay):
    """La strategia VERA del banco di Omega, dal suo costruttore."""
    Strategia = R._crea_strategia()
    return Strategia(
        event_id=EVENTO, params=dict(omega_config.DEFAULTS), mode="live", banco=banco,
        catalogo=R.Catalogo(), feed=R.FeedReplay(banco), punteggi=[],
        nome_evento="Prova v Prova", market_filter={"markets": []},
        max_order_exposure=1e9, max_selection_exposure=1e9,
        max_trade_count=int(1e9), max_live_trade_count=int(1e9))


# ---------------------------------------------------------------------------
# RB-1 - la chiusura arriva allo scanner
# ---------------------------------------------------------------------------
def test_rb1_omega_passa_la_chiusura_di_betfair_allo_scanner(punteggi):
    banco = _banco(punteggi, "16:30:00")
    assert _a(banco, "16:30:00.600", HT, "16:30:00") is True
    st = _strategia(banco)
    chiuso = _libro(HT, "16:47:58.751")
    assert chiuso.status == "CLOSED"
    st.process_closed_market(None, chiuso)
    assert banco.scan.events[EVENTO]["ht"]["status"] == "CLOSED"
    assert banco.ora == pytest.approx(_ms("16:47:58.751") / 1000.0)
    assert st.chiusure_allo_scanner == [(HT, _ms("16:47:58.751"))]
    # flumine lo ripete a ogni riga: una volta sola
    st.process_closed_market(None, chiuso)
    assert st.chiusure_allo_scanner == [(HT, _ms("16:47:58.751"))]


# ---------------------------------------------------------------------------
# RB-2 - le esposizioni di Omega nella forma di produzione
# ---------------------------------------------------------------------------
def test_rb2_esposizioni_omega_come_le_legge_la_produzione():
    righe = [
        {"id": 1, "event_id": "E1", "market_id": "1.A", "status": "open", "source": "x"},
        {"id": 2, "event_id": "E1", "market_id": "1.B", "status": "pending"},
        {"id": 3, "event_id": "E2", "market_id": "1.C", "status": "hedged"},
        {"id": 4, "event_id": "E3", "market_id": "1.D", "status": "won"},
        {"id": 5, "event_id": "E3", "market_id": "1.E", "status": "error"},
        {"id": 6, "event_id": "E4", "market_id": "1.F", "status": "lost"},
    ]
    assert set(SDB._STATI_TRADE_ESPOSTI) == {"pending", "open", "hedged"}
    assert R.esposizioni_omega(righe) == [
        {"event_id": "E1", "market_id": "1.A", "sport": "calcio", "bot": "omega"},
        {"event_id": "E1", "market_id": "1.B", "sport": "calcio", "bot": "omega"},
        {"event_id": "E2", "market_id": "1.C", "sport": "calcio", "bot": "omega"},
    ]


def test_rb2_il_banco_di_omega_accende_le_finestre():
    assert R.FINESTRE_DI_PRODUZIONE is True


# ---------------------------------------------------------------------------
# RB-3 - l'eta' nei testi del flusso e' in tempo di mercato
# ---------------------------------------------------------------------------
def test_rb3_eta_del_flusso_sull_orologio_di_mercato():
    banco = B.ScannerReplay(sport="calcio")
    adesso = _ms("16:29:21.813")
    banco.imposta_ora(adesso / 1000.0)
    payload = {"mo_market_id": MO, "flusso": {
        "vivo": True, "motivo": None, "dal_ms": adesso - 30_000,
        "mercati_fermi": [HT], "fermi_da_ms": {HT: adesso - 30_000}}}
    vero = FP._ora_ms
    with R.AmbienteOmega(object(), R.FeedReplay(banco), banco):
        es = FP.valuta(payload, None, None, [MO, HT])
        assert not es.vivo and es.motivo == FP.MOTIVO_MERCATO_FERMO
        assert es.testo.endswith("; da 30 s"), es.testo
    assert FP._ora_ms is vero                    # rimesso a posto all'uscita
    fuori = FP.valuta(payload, None, None, [MO, HT])
    assert not fuori.testo.endswith("; da 30 s")  # fuori dal replay: l'ora del PC


# ---------------------------------------------------------------------------
# RB-4 - il paper passa dalla porta del runner del banco
# ---------------------------------------------------------------------------
def test_rb4_il_paper_aggancia_la_porta_del_runner():
    assert TRA.attivo() is None
    prima = os.environ.get("OMEGA_ORDINI_VIA_CANALE")
    with R._porta_del_runner_per_il_paper("paper"):
        st = TRA.attivo()
        assert st is not None and st["trasporto"] == "canale" and st["attore"] == "omega"
        assert os.environ.get("OMEGA_ORDINI_VIA_CANALE") == "1"
    assert TRA.attivo() is None
    assert os.environ.get("OMEGA_ORDINI_VIA_CANALE") == prima


def test_rb4_il_live_resta_sul_trasporto_di_sempre():
    with R._porta_del_runner_per_il_paper("live"):
        assert TRA.attivo() is None


def test_rb4_un_trasporto_scelto_da_certifica_si_rispetta():
    with TRA.contesto("omega", "coda"):
        with R._porta_del_runner_per_il_paper("paper"):
            assert TRA.attivo()["trasporto"] == "coda"


def test_rb4_la_descrizione_dello_scenario_paper_non_parla_piu_di_paper_fill():
    testo = R.SCENARI_DESCRITTI["paper"]
    assert "paper_fill" not in testo and "RUNNER" in testo
    assert R.SCENARI["paper"] == R.SCENARI["apertura"]


# ---------------------------------------------------------------------------
# RB-5 - le tabelle storiche non passano da uno scenario al successivo
# ---------------------------------------------------------------------------
def _leggi_tabelle(db) -> None:
    """Cio' che fa un giro di Omega: legge (e mette in cache) le due tabelle."""
    par = {"model_empirical": "veto"}
    S._empirical_table(db, 39, par)
    S._minute_table(db, 39, 50, False, par)


def test_rb5_due_scenari_in_sequenza_il_secondo_non_vede_le_tabelle_del_primo():
    db = R.DbMemoriaOmega({"id": 1, "status": "running", "mode": "live",
                           "params": {}, "daily_goal": 5.0, "stats": {}})
    banco = B.ScannerReplay(sport="calcio")
    # scenario 1
    with R.AmbienteOmega(object(), R.FeedReplay(banco), banco):
        _leggi_tabelle(db)
        assert S._EMPIRICAL_CACHE and S._MINUTE_CACHE
        # scenario 2, stesso processo (--worker 1)
    with R.AmbienteOmega(object(), R.FeedReplay(banco), banco):
        assert not S._EMPIRICAL_CACHE and not S._MINUTE_CACHE
    assert db.senza_dato and {n for n, _c in db.senza_dato} >= {"ht_ft_transitions",
                                                                  "minute_transitions"}


def test_rb5_anche_l_uscita_dal_replay_le_azzera():
    db = R.DbMemoriaOmega({"id": 1, "status": "running", "mode": "live",
                           "params": {}, "daily_goal": 5.0, "stats": {}})
    banco = B.ScannerReplay(sport="calcio")
    with R.AmbienteOmega(object(), R.FeedReplay(banco), banco):
        _leggi_tabelle(db)
    assert not S._EMPIRICAL_CACHE and not S._MINUTE_CACHE


def test_rb5_l_ingresso_nel_replay_parte_pulito():
    """Tabelle lasciate in RAM da chi ha girato prima nello stesso processo (un
    figlio della pool riusato, un replay finito male): il replay parte pulito."""
    db = R.DbMemoriaOmega({"id": 1, "status": "running", "mode": "live",
                           "params": {}, "daily_goal": 5.0, "stats": {}})
    _leggi_tabelle(db)
    assert S._EMPIRICAL_CACHE and S._MINUTE_CACHE
    banco = B.ScannerReplay(sport="calcio")
    with R.AmbienteOmega(object(), R.FeedReplay(banco), banco):
        assert not S._EMPIRICAL_CACHE and not S._MINUTE_CACHE


def test_rb5_il_riavvio_a_meta_partita_le_perde_come_un_riavvio_vero():
    db = R.DbMemoriaOmega({"id": 1, "status": "running", "mode": "live",
                           "params": {}, "daily_goal": 5.0, "stats": {}})
    _leggi_tabelle(db)
    azzerati = R._riavvia_processo()
    assert "_EMPIRICAL_CACHE" in azzerati and "_MINUTE_CACHE" in azzerati
    assert not S._EMPIRICAL_CACHE and not S._MINUTE_CACHE


def test_rb5_l_elenco_e_esplicito_e_nomina_cache_vere_di_omega_service():
    assert R.CACHE_TABELLE_STORICHE == ("_EMPIRICAL_CACHE", "_MINUTE_CACHE")
    assert R.CACHE_DI_PROCESSO_DEL_BANCO == (
        "_LEG_RETRY", "_SKIP_SEEN", "_BLIND_CYCLES", "_MARKET_FIT_CACHE",
        "_LAMBDA_CACHE", "_IDLE_STATS_AT", "_CATENA_OMEGA",
        "_EMPIRICAL_CACHE", "_MINUTE_CACHE")
    for nome in R.CACHE_DI_PROCESSO_DEL_BANCO:
        assert isinstance(getattr(S, nome), dict)


def test_rb5_un_rifiuto_di_uno_scenario_non_blocca_la_gamba_nel_successivo():
    """Il caso provato sul raw (35760084, codice di partenza): `paper` rifiutava
    5 volte il '3 - 3' (`paper_runner_non_disponibile`, tentativo non consumato
    ma istante scritto in `_LEG_RETRY`) e `apertura`, girata DOPO nello stesso
    processo, non lo apriva piu' (438/0 invece di 467/2): l'istante del rifiuto
    era alle 17:5x di mercato e la gamba restava in attesa di ritentare."""
    from datetime import datetime, timezone

    tardi = datetime.fromtimestamp(_ms("17:50:00") / 1000.0, tz=timezone.utc)
    presto = datetime.fromtimestamp(_ms("17:14:10") / 1000.0, tz=timezone.utc)
    banco = B.ScannerReplay(sport="calcio")
    with R.AmbienteOmega(object(), R.FeedReplay(banco), banco):        # scenario 1
        S._leg_note_rifiuto_senza_tentativo(EVENTO, "ft_cs", tardi,
                                            "paper_runner_non_disponibile")
        assert not S._leg_retry_allowed(EVENTO, "ft_cs", presto)
    with R.AmbienteOmega(object(), R.FeedReplay(banco), banco):        # scenario 2
        assert S._leg_retry_allowed(EVENTO, "ft_cs", presto)
