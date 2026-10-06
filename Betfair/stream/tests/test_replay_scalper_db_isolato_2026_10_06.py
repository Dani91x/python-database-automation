"""06/10/2026 - il replay dello Scalper non scrive MAI nel DB vero.

Difetto visto dall'utente: la home mostrava allarmi «WARN/CRITICAL
CAMBIO_GBP_EUR cambio GBP->EUR non letto (AttributeError: '_TradingFinto' object
has no attribute 'account')». Li scrivevano i REPLAY lanciati sul PC (dove le
credenziali del DB ci sono):

* la sessione chiama ``valuta.CAMBIO.avvia(trading)``; nel replay ``trading`` e'
  il Betfair finto del banco, senza ``account``: la lettura del cambio falliva e
  ``valuta`` scriveva l'allarme con ``Betfair.stream.db.insert_alert``;
* il banco vietava ``db_client.get_supabase_client``, ma ``Betfair/stream/db.py``
  ha importato il NOME (``from db_client import get_supabase_client``) e teneva
  il client vero.

Qui il "PC con le credenziali" e' un client finto che registra ogni scrittura
(stessa catena ``table(...).insert(...).execute()`` del client supabase vero).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest

import db_client
from Betfair.stream import db as STREAM_DB
from Betfair.stream import valuta as VALUTA
from Betfair.stream.scalper.tools import replay_registrazioni as R
from Betfair.stream.tests.banco_media_under import BancoMedia


class _Esegui:
    def __init__(self, scritte: List[Tuple[str, Dict[str, Any]]], tabella: str,
                 riga: Dict[str, Any]) -> None:
        self._scritte, self._tabella, self._riga = scritte, tabella, riga

    def execute(self) -> Any:
        self._scritte.append((self._tabella, dict(self._riga)))
        return None


class _Tabella:
    def __init__(self, scritte: List[Tuple[str, Dict[str, Any]]], nome: str) -> None:
        self._scritte, self._nome = scritte, nome

    def insert(self, riga: Dict[str, Any]) -> _Esegui:
        return _Esegui(self._scritte, self._nome, riga)


class _DbVeroFinto:
    """Il DB VERO del PC dell'utente: registra ogni scrittura."""

    def __init__(self) -> None:
        self.scritte: List[Tuple[str, Dict[str, Any]]] = []

    def table(self, nome: str) -> _Tabella:
        return _Tabella(self.scritte, nome)


@pytest.fixture
def pc_con_credenziali(monkeypatch):
    """Come sul PC: TUTTE le copie del nome portano al client vero."""
    vero = _DbVeroFinto()

    def _client() -> _DbVeroFinto:
        return vero

    monkeypatch.setattr(db_client, "get_supabase_client", _client)
    monkeypatch.setattr(STREAM_DB, "get_supabase_client", _client)
    return vero


def _banco() -> Any:
    from Betfair.stream.tests.test_scalper_media_under_giro4_2026_10_06 import _banco_su

    return _banco_su(BancoMedia())


def test_il_difetto_esiste_fuori_dal_banco(pc_con_credenziali):
    """Prova che il finto e' fedele: FUORI dal banco il Betfair finto del
    replay fa scrivere l'allarme nel DB vero (e' quello che vedeva l'utente)."""
    cambio = VALUTA.CambioGbpEur(percorso_cache="/nonesiste/currency_rate.json")
    cambio.aggiorna(R._TradingFinto(_banco()))
    allarmi = [r for t, r in pc_con_credenziali.scritte if t == "live_alerts"]
    assert len(allarmi) == 1 and allarmi[0]["code"] == "CAMBIO_GBP_EUR"
    assert "_TradingFinto" in allarmi[0]["message"]


def test_nel_replay_il_cambio_e_fisso_e_nessun_allarme(pc_con_credenziali, tmp_path):
    banco = _banco()
    prima = VALUTA.CAMBIO
    with R._iniezioni(banco, R._Orologio(), str(tmp_path / "kill")):
        assert VALUTA.CAMBIO is not prima and VALUTA.CAMBIO.fisso
        assert VALUTA.CAMBIO.rate == VALUTA.cambio_banco().rate
        # quello che fa la sessione all'armo
        VALUTA.CAMBIO.avvia(banco.trading)
    assert pc_con_credenziali.scritte == []
    assert VALUTA.CAMBIO is prima


def test_nel_replay_il_db_vero_e_vietato_anche_per_chi_ha_copiato_il_nome(
        pc_con_credenziali, tmp_path):
    banco = _banco()
    with R._iniezioni(banco, R._Orologio(), str(tmp_path / "kill")):
        with pytest.raises(RuntimeError, match="DB VERO vietato"):
            STREAM_DB.insert_alert("CRITICAL", "PROVA", "dal replay")
        with pytest.raises(RuntimeError, match="DB VERO vietato"):
            db_client.get_supabase_client()
    assert pc_con_credenziali.scritte == []
    # finito il replay il client torna quello di prima
    STREAM_DB.insert_alert("INFO", "PROVA", "fuori dal replay")
    assert pc_con_credenziali.scritte == [("live_alerts", {
        "level": "INFO", "code": "PROVA", "message": "fuori dal replay", "event_id": None})]
