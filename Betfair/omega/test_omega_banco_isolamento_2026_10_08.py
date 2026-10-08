"""Cantiere 11 (08/10/2026) - il banco di Omega riparte da un processo NUOVO a
ogni scenario.

Reperto: con `certifica --worker 1` i venti scenari di Omega girano nello stesso
processo e 13 dizionari di `omega_service` (fra cui `_EVENTS_REFRESH_AT`,
`_SKIP_SEEN`, `_LAMBDA_CACHE`) passavano da uno scenario al successivo: il
referto di uno scenario dipendeva da quelli girati prima, e `--worker 3` dava
un referto DIVERSO da `--worker 1` (35760084: 403 righe). Il banco ora li azzera
(`replay_registrazioni._processo_nuovo`) all'ingresso e all'uscita di ogni
scenario (`AmbienteOmega`).
"""
from __future__ import annotations

from Betfair.omega import omega_service as S
from Betfair.omega.tools import replay_registrazioni as RR
from Betfair.stream import flusso_prezzi as FP


def _stato_mutabile_di_modulo():
    """Ogni dict/set/list di modulo di `omega_service` (riflessione: e' il TEST
    che deve accorgersi di uno stato nuovo dimenticato)."""
    return sorted(n for n, v in vars(S).items()
                  if n.startswith("_") and not n.startswith("__")
                  and isinstance(v, (dict, set, list)))


def test_ogni_stato_di_processo_di_omega_riparte_a_ogni_scenario():
    """Ogni stato mutabile di modulo e' azzerato fra scenari (da
    `svuota_le_cache` o dall'elenco del banco) oppure e' una costante dichiarata."""
    import inspect

    sorgente = inspect.getsource(S.svuota_le_cache)
    dimenticati = [n for n in _stato_mutabile_di_modulo()
                   if n not in sorgente
                   and n not in RR.STATO_DI_PROCESSO_FRA_SCENARI
                   and n not in RR.COSTANTI_DI_MODULO
                   and n != "_AVVISO_AGGREGATI_SENZA_MODO"]
    assert not dimenticati, (
        "stato di processo di omega_service che passerebbe da uno scenario al "
        f"successivo con --worker 1: {dimenticati}")


def test_le_costanti_dichiarate_sono_davvero_costanti():
    """Una «costante» che il servizio scrive sarebbe stato travestito: le due
    tabelle di testo non si toccano mai con un'assegnazione per chiave."""
    import inspect

    sorgente = inspect.getsource(S)
    for nome in RR.COSTANTI_DI_MODULO:
        assert f"{nome}[" not in sorgente.replace(f"{nome}.get(", ""), nome
        assert f"{nome}.clear(" not in sorgente and f"{nome}.update(" not in sorgente, nome


def test_processo_nuovo_svuota_davvero():
    """FALSIFICAZIONE: si sporca tutto cio' che un processo nuovo avrebbe vuoto
    e si pretende che `_processo_nuovo` lo riporti a zero."""
    for nome in RR.STATO_DI_PROCESSO_FRA_SCENARI:
        getattr(S, nome)["__prova__"] = 1
    S._AVVISO_AGGREGATI_SENZA_MODO["dato"] = True
    FP._NON_NOTO_AVVISATO.add("omega")
    FP._NON_NOTO_AVVISATO.add("__altro_bot__")
    try:
        RR._processo_nuovo()
        rimasti = [n for n in RR.STATO_DI_PROCESSO_FRA_SCENARI if getattr(S, n)]
        assert not rimasti, rimasti
        assert S._AVVISO_AGGREGATI_SENZA_MODO["dato"] is False
        assert "omega" not in FP._NON_NOTO_AVVISATO
        # l'avviso degli ALTRI bot non e' di Omega: resta
        assert "__altro_bot__" in FP._NON_NOTO_AVVISATO
    finally:
        FP._NON_NOTO_AVVISATO.discard("__altro_bot__")


def test_ambiente_omega_parte_e_finisce_da_processo_nuovo(monkeypatch):
    """`AmbienteOmega` chiama `_processo_nuovo` all'ingresso e all'uscita."""
    chiamate = []
    monkeypatch.setattr(RR, "_processo_nuovo", lambda: chiamate.append(1))

    class _Finto:
        ora = 0.0

        def righe(self, *_a, **_k):
            return []

        def stato_scanner(self, *_a, **_k):
            return None

    amb = RR.AmbienteOmega(object(), _Finto(), _Finto())
    with amb:
        assert len(chiamate) == 1
    assert len(chiamate) == 2


def test_il_refresh_eventi_riparte_nello_scenario_dopo():
    """Il caso misurato: a fine scenario `_EVENTS_REFRESH_AT` porta l'istante di
    fine partita; senza azzeramento lo scenario dopo (stessa giornata, orologio
    di nuovo all'inizio) non rinfrescava MAI gli eventi."""
    from datetime import datetime, timedelta, timezone

    inizio = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    fine = inizio + timedelta(hours=3)
    RR._processo_nuovo()
    assert S._events_refresh_due(fine) is True        # scenario 1, a fine partita
    RR._processo_nuovo()                               # scenario 2
    assert S._events_refresh_due(inizio) is True
