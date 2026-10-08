# -*- coding: utf-8 -*-
"""08/10/2026 sera - DECISIONI DELL'UTENTE SUL BANCO (D-1 in
`test_scalper_certificazione_2026_09_24.py`; qui D-13, D-14b, D-14c, D-15).

* D-13: `omega_service._LAMBDA_CACHE` (catena dei lambda della Safe) scade a
  orologio di PARETE; il banco della Safe la azzera fra uno scenario e l'altro
  (ingresso e uscita di ogni replay), NON al riavvio a meta' partita.
* D-14b: senza `psutil` il taglio dei worker non e' piu' silenzioso: il
  referto stampa ``worker: 1 (psutil assente: richiesti N)``.
* D-14c: il riavvio a meta' partita di Omega perde TUTTO lo stato di processo,
  con la stessa funzione e lo stesso elenco dell'ingresso di ogni scenario.
* D-15: il PADRE di `certifica` non trattiene le righe dello specchio dei
  figli (`ordini_specchio`, che `main` non stampa) ne' i risultati gia' letti
  della pool: con 56 scenari dello scalper arrivava a ~10 GB.

Solo banco: nessun servizio di produzione cambia. ASCII-only, commenti in
italiano.
"""
from __future__ import annotations

import gc
import os
import sys
import weakref

from Betfair.omega import omega_service as OS
from Betfair.omega.tools import replay_registrazioni as OR
from Betfair.safe_strategy.certificazione_tennis import Referto
from Betfair.stream import flusso_prezzi as FP
from Betfair.stream.backtest import certifica as C
from Betfair.stream.scalper import certificazione as SCERT
from Betfair.safe_strategy.tools import replay_registrazioni as SR


# ---------------------------------------------------------------------------
# D-13
# ---------------------------------------------------------------------------
def _lambda_in_cache() -> None:
    # la forma VERA della voce: ((lh, la, league_id, fonte), istante)
    OS._LAMBDA_CACHE["35760084"] = ((1.31, 1.02, 135, "pre_ko_odds"), 1.0)


def test_d13_la_pulizia_di_ogni_scenario_della_safe_azzera_i_lambda():
    _lambda_in_cache()
    try:
        SR._pulisci_cache_di_processo()
        assert "35760084" not in OS._LAMBDA_CACHE
    finally:
        OS._LAMBDA_CACHE.pop("35760084", None)


def test_d13_il_riavvio_a_meta_partita_della_safe_non_tocca_i_lambda():
    # decisione dichiarata: il banco della Safe non esercita `get_event`, con
    # cui la produzione riavviata ritrova il modello; azzerarli al riavvio
    # ricalcolerebbe i lambda dal solo mercato di quel momento
    _lambda_in_cache()
    try:
        SR._riavvia_processo()
        assert OS._LAMBDA_CACHE.get("35760084") == ((1.31, 1.02, 135, "pre_ko_odds"), 1.0)
    finally:
        OS._LAMBDA_CACHE.pop("35760084", None)


def test_d13_ogni_replay_della_safe_pulisce_all_ingresso_e_all_uscita(monkeypatch, tmp_path):
    # `_certifica_evento` chiama la pulizia all'ingresso; all'uscita la chiama
    # il `finally` dopo il motore (qui: registrazione assente -> solo ingresso,
    # l'uscita e' provata dal sorgente)
    import inspect
    chiamate = []
    vero = SR._pulisci_cache_di_processo
    monkeypatch.setattr(SR, "_pulisci_cache_di_processo",
                        lambda: (chiamate.append(1), vero())[1])
    _lambda_in_cache()
    SR._certifica_evento("99999999", data_dir=str(tmp_path))
    assert chiamate and "35760084" not in OS._LAMBDA_CACHE
    src = inspect.getsource(SR._certifica_evento)
    fin = src.index("finally:")
    assert "_pulisci_cache_di_processo()" in src[fin:fin + 600]


# ---------------------------------------------------------------------------
# D-14b
# ---------------------------------------------------------------------------
def _senza_psutil(monkeypatch, thread: int = 4) -> None:
    # `import psutil` fallisce come su una macchina che non lo ha (ImportError)
    monkeypatch.setitem(sys.modules, "psutil", None)
    monkeypatch.setattr(os, "cpu_count", lambda: thread)


def test_d14b_senza_psutil_il_taglio_dei_worker_si_dichiara(monkeypatch):
    _senza_psutil(monkeypatch)
    assert not C.psutil_presente()
    assert C.core_fisici() == 2                 # stima dai thread: 4 // 2
    processi = C.quanti_processi(3, 10)
    assert processi == 1
    assert C.riga_worker(processi, 3, 10) == "worker: 1 (psutil assente: richiesti 3)"


def test_d14b_con_psutil_la_riga_e_quella_di_sempre():
    assert C.psutil_presente()
    n = C.core_fisici()
    assert C.riga_worker(3, 3, 56) == (
        "worker: 3 su %d core fisici (un processo per coppia evento x scenario, "
        "56 coppie; il referto resta nello stesso ordine)" % n)
    # uno solo, chiesto uno o con un solo compito: niente da dire
    assert C.riga_worker(1, 1, 10) is None
    assert C.riga_worker(1, 3, 1) is None
    assert C.riga_worker(2, 3, 2) is not None and "richiesti" not in C.riga_worker(2, 3, 2)


def test_d14b_main_stampa_la_riga_quando_psutil_manca(monkeypatch, capsys):
    _senza_psutil(monkeypatch)

    def _fake(compiti, processi, picchi):  # noqa: ARG001 - stessa firma del vero
        assert processi == 1
        for c in compiti:
            yield Referto(event_id=str(c[1]), decisioni=1)

    monkeypatch.setattr(C, "_esegui_compiti", _fake)
    C.main(["safe_tennis", "999998", "999999", "--scenari", "base", "--worker", "3"])
    out = capsys.readouterr().out
    assert "worker: 1 (psutil assente: richiesti 3)" in out, out


# ---------------------------------------------------------------------------
# D-14c
# ---------------------------------------------------------------------------
def test_d14c_il_riavvio_di_omega_perde_tutto_lo_stato_di_processo():
    for nome in OR.STATO_DI_PROCESSO_FRA_SCENARI:
        getattr(OS, nome)["__prova__"] = 1
    OS._AVVISO_AGGREGATI_SENZA_MODO["dato"] = True
    FP._NON_NOTO_AVVISATO.add("omega")
    OS._CATENA_OMEGA["__prova__"] = 1          # di `svuota_le_cache`
    azzerati = OR._riavvia_processo()
    rimasti = [n for n in OR.STATO_DI_PROCESSO_FRA_SCENARI if getattr(OS, n)]
    assert not rimasti, rimasti
    assert not OS._CATENA_OMEGA
    assert OS._AVVISO_AGGREGATI_SENZA_MODO["dato"] is False
    assert "omega" not in FP._NON_NOTO_AVVISATO
    # il referto dice che cosa e' stato buttato: TUTTI i nomi che erano pieni
    for nome in OR.STATO_DI_PROCESSO_FRA_SCENARI:
        assert nome in azzerati, nome
    # i 13 stati in piu' rispetto al riavvio di prima ci sono (cantiere 11 par.9.2)
    for nome in ("_EVENTS_REFRESH_AT", "_LEG_RETRY_DB", "_DAILY_GOAL_WRITTEN",
                 "_REALLY_OVER_CACHE", "_ULTIMO_STATO_SCANNER_OMEGA"):
        assert nome in azzerati, nome


def test_d14c_riavvio_e_ingresso_sono_la_stessa_funzione(monkeypatch):
    chiamate = []
    monkeypatch.setattr(OR, "_processo_nuovo", lambda: chiamate.append(1))
    OR._riavvia_processo()
    assert chiamate == [1]
    # nessun secondo elenco nel modulo del banco
    assert not hasattr(OR, "CACHE_DI_PROCESSO_DEL_BANCO")
    assert not hasattr(OR, "_azzera_cache_di_processo")


# ---------------------------------------------------------------------------
# D-15
# ---------------------------------------------------------------------------
def _righe_specchio(n: int):
    # le chiavi di una riga `betfair_live_orders` catturata dal banco (+ `_ms`)
    return [{"bet_id": str(100000000000 + i), "client_order_ref": "scalp-1-%d" % i,
             "market_id": "1.259819674", "selection_id": 58805, "side": "BACK",
             "price": 4.1, "size": 25.0, "size_matched": 0.0, "status": "EXECUTABLE",
             "_ms": 1_700_000_000_000 + i} for i in range(n)]


def _referto_scalper(ev: str, n_righe: int):
    r = SCERT.Referto(event_id=ev, tick=10, decisioni=3, azioni=1,
                      stati_visti=["slot:IDLE"], note=["nota di prova"])
    r.ordini_specchio = _righe_specchio(n_righe)          # come il replay vero
    return r


def test_d15_il_figlio_non_manda_al_padre_le_righe_dello_specchio(monkeypatch):
    monkeypatch.setattr(C, "_lavora", lambda c: (_referto_scalper(str(c[1]), 500), 1.0))
    r, mem, secondi = C._lavora_cronometrato(("scalper_calcio", "35797769", "d", "base", 0, 0))
    assert not hasattr(r, "ordini_specchio")
    assert r.ordini_specchio_tolte == 500                # dichiarato, non azzerato
    assert (r.tick, r.decisioni, r.azioni, r.note) == (10, 3, 1, ["nota di prova"])
    assert mem == 1.0 and secondi >= 0.0


def test_d15_il_referto_stampato_e_identico_con_o_senza_le_righe(monkeypatch, capsys):
    # `main` con `--worker 1` (stesso processo): referto con le righe tolte
    # contro referto con le righe tenute -> stesse righe (tolte quelle dei tempi)
    monkeypatch.setattr(C, "_lavora", lambda c: (_referto_scalper(str(c[1]), 300), 1.0))
    argv = ["scalper_calcio", "35797769", "--scenari", "base,paper", "--worker", "1",
            "--data-dir", "C:/inesistente"]
    C.main(argv)
    alleggerito = capsys.readouterr().out
    monkeypatch.setattr(C, "_per_il_padre", lambda r: r)
    C.main(argv)
    intero = capsys.readouterr().out
    assert "nota di prova" in alleggerito
    assert C.righe_senza_tempi(alleggerito) == C.righe_senza_tempi(intero)


def test_d15_la_pool_non_trattiene_i_risultati_gia_letti(monkeypatch):
    import concurrent.futures as CF

    class _PoolFinta:
        def __init__(self, max_workers=None, initializer=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def submit(self, fn, c):
            f = CF.Future()
            f.set_result(fn(c))
            return f

    monkeypatch.setattr(CF, "ProcessPoolExecutor", _PoolFinta)
    monkeypatch.setattr(C, "_lavora", lambda c: (_referto_scalper(str(c[1]), 10), 1.0))
    compiti = [("scalper_calcio", str(i), "d", "base", 0, 0) for i in range(3)]
    gen = C._esegui_compiti(compiti, 3, [], [])
    primo = next(gen)
    assert not hasattr(primo, "ordini_specchio")
    rif = weakref.ref(primo)
    del primo
    next(gen)
    gc.collect()
    assert rif() is None, "il padre trattiene ancora il referto gia' letto"
