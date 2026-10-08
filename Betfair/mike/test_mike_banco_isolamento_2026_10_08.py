"""Cantiere 11 (08/10/2026) - il banco di Mike riparte con il dossier di un
processo NUOVO a ogni scenario.

Reperto: con `certifica --worker 1` gli scenari di Mike girano nello stesso
processo e `dossier._EMPIRICAL_FAILED` (istante dell'ultimo tentativo fallito
della tabella HT->FT) passava allo scenario dopo: per 600 s `ht_ft_rows` non
veniva chiesta e la nota NON ESERCITABILE spariva dal referto (35760084:
`--worker 1` e `--worker 3` diversi su 2 righe).
"""
from __future__ import annotations

from Betfair.mike import dossier as D
from Betfair.mike.tools import replay_registrazioni as RR


def test_ogni_stato_del_dossier_riparte_a_ogni_scenario():
    """Ogni dict/set/list di modulo del dossier e' nell'elenco del banco (o e'
    l'avviso `_AVVISATO`, riarmato a parte)."""
    mutabili = sorted(n for n, v in vars(D).items()
                      if n.startswith("_") and not n.startswith("__")
                      and isinstance(v, (dict, set, list)))
    dimenticati = [n for n in mutabili
                   if n not in RR.STATO_DOSSIER_FRA_SCENARI and n != "_AVVISATO"]
    assert not dimenticati, dimenticati


def test_dossier_nuovo_svuota_davvero():
    """FALSIFICAZIONE: si sporca lo stato e si pretende che torni vuoto."""
    for nome in RR.STATO_DOSSIER_FRA_SCENARI:
        getattr(D, nome)["__prova__"] = 1.0
    D._AVVISATO["assente"] = True
    RR._dossier_nuovo()
    assert not [n for n in RR.STATO_DOSSIER_FRA_SCENARI if getattr(D, n)]
    assert D._AVVISATO["assente"] is False


def test_la_tabella_si_richiede_nello_scenario_dopo():
    """Il caso misurato: un tentativo fallito nello scenario 1 non deve impedire
    la richiesta nello scenario 2 (stesso processo, stesso orologio)."""
    chieste = []

    class _Db:
        def ht_ft_rows(self, key):
            chieste.append(key)
            return None

    RR._dossier_nuovo()
    assert D.get_empirical(7, _Db(), now_ts=1000.0) is None      # scenario 1
    RR._dossier_nuovo()
    assert D.get_empirical(7, _Db(), now_ts=1000.0) is None      # scenario 2
    assert chieste == [7, 7]


def test_il_replay_chiama_dossier_nuovo_all_inizio():
    """Il banco chiama `_dossier_nuovo` subito dopo l'azzeramento del servizio."""
    import inspect

    sorgente = inspect.getsource(RR._certifica_evento)
    assert "S.azzera_cache_di_processo()" in sorgente
    assert "_dossier_nuovo()" in sorgente
    assert sorgente.index("_dossier_nuovo()") > sorgente.index("S.azzera_cache_di_processo()")
