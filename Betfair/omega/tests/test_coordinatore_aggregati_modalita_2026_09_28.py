"""Verifica INDIPENDENTE del coordinatore sul cantiere C (28/09/2026).

Mutazione sopravvissuta alla consegna: in ``omega_db._aggregati_modalita`` la
RPC veniva chiamata con ``{"p_mode": "paper"}`` fisso al posto di
``{"p_mode": mode}`` e l'intera suite di Omega restava verde. Cioe': nessun test
provava che i numeri chiesti per il LIVE interrogano il DB sul LIVE.

Regola dell'utente: paper e live non si sommano e non si scambiano mai nelle
decisioni (stop giornaliero, tetti, obiettivo).

Il finto del client ha la stessa forma del vero: ``rpc(nome, params)`` ritorna
un oggetto con ``execute()``, che ritorna un oggetto con ``data``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import pytest

from Betfair.omega import omega_db


class _Risposta:
    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = data


class _Chiamata:
    def __init__(self, registro: List[Tuple[str, Dict[str, Any]]], nome: str,
                 params: Dict[str, Any]) -> None:
        self._registro = registro
        self._nome = nome
        self._params = dict(params)

    def execute(self) -> _Risposta:
        self._registro.append((self._nome, dict(self._params)))
        modo = self._params.get("p_mode")
        # numeri diversi per modalita': uno scambio si vede dal valore
        realizzato = 1.5 if modo == "paper" else -7.25
        return _Risposta({"realized_today": realizzato, "mode": modo,
                          "auto": {"realized_today": realizzato / 2, "mode": modo}})


class _ClienteFinto:
    def __init__(self) -> None:
        self.chiamate: List[Tuple[str, Dict[str, Any]]] = []

    def rpc(self, nome: str, params: Dict[str, Any]) -> _Chiamata:
        return _Chiamata(self.chiamate, nome, params)


@pytest.mark.parametrize("modo, atteso", [("paper", 1.5), ("live", -7.25)])
def test_gli_aggregati_di_una_modalita_interrogano_il_db_su_quella_modalita(
        monkeypatch: pytest.MonkeyPatch, modo: str, atteso: float) -> None:
    cliente = _ClienteFinto()
    monkeypatch.setattr(omega_db, "_sb", lambda: cliente)
    giorno = datetime(2026, 9, 28, tzinfo=timezone.utc)

    completi, solo_bot = omega_db.aggregates_coppia(giorno, mode=modo)

    assert cliente.chiamate == [("get_omega_aggregates_modalita", {"p_mode": modo})]
    assert completi["realized_today"] == pytest.approx(atteso)
    assert solo_bot["realized_today"] == pytest.approx(atteso / 2)
    # la chiave di servizio ``mode`` non entra fra i numeri
    assert "mode" not in completi and "mode" not in solo_bot


def test_maiuscole_e_spazi_nella_modalita_non_cambiano_la_domanda(
        monkeypatch: pytest.MonkeyPatch) -> None:
    cliente = _ClienteFinto()
    monkeypatch.setattr(omega_db, "_sb", lambda: cliente)
    giorno = datetime(2026, 9, 28, tzinfo=timezone.utc)

    completi, _ = omega_db.aggregates_coppia(giorno, mode="  LIVE ")

    assert cliente.chiamate == [("get_omega_aggregates_modalita", {"p_mode": "live"})]
    assert completi["realized_today"] == pytest.approx(-7.25)
