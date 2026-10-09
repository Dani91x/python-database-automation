"""W1-G1 - parita' della RIGA: cio' che il postino consegna == cio' che il codice di oggi inserisce.

Per ogni scrittore di log di oggi (funzione VERA, chiamata davvero) si cattura il corpo dell'``insert``
che parte verso PostgREST (client supabase vero su ``httpx.MockTransport``, come
``test_catchup_rete_2026_10_08.py``); la STESSA riga passa da ``ArchivioLocale.scrivi`` e dal
postino; la riga che il postino consegna deve essere IDENTICA, con in piu' solo le due colonne
dichiarate: ``uid`` (migrazione G1, U-50) e la colonna del tempo che oggi riempie ``now()`` del
cloud (timbrata all'accodamento). Stessa tabella, stesse colonne, stessi valori.
L'aggancio vero (chi chiama ``scrivi`` al posto dell'insert) e' l'ondata 2 (T8): qui si prova che
il trasporto non altera nulla.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import httpx
import pytest
import supabase
from supabase import ClientOptions

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

import db_client  # noqa: E402
from Betfair.nucleo.dati.archivio import COLONNE_TEMPO_PREDEFINITE, ArchivioLocale  # noqa: E402
from Betfair.nucleo.dati.postino import PostinoLocale  # noqa: E402
from Betfair.nucleo.dati.tests.test_g1_finti import SPEC, CloudProva, PostgrestFinto  # noqa: E402


@pytest.fixture
def inserti(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, Any]]:
    """Ogni insert del codice di oggi: (tabella, corpo JSON) come arriva a PostgREST."""
    visti: List[Tuple[str, Any]] = []

    def gestisci(req: httpx.Request) -> httpx.Response:
        tabella = req.url.path.replace("/rest/v1/", "")
        corpo = json.loads(req.content or b"null")
        visti.append((tabella, corpo))
        righe = corpo if isinstance(corpo, list) else [corpo]
        return httpx.Response(201, json=[{**r, "id": i + 1} for i, r in enumerate(righe)])

    def crea(*_a: Any, **_k: Any) -> Any:
        return supabase.create_client("https://abc.supabase.co", "x" * 40,
                                      options=ClientOptions(httpx_client=httpx.Client(
                                          transport=httpx.MockTransport(gestisci))))

    monkeypatch.setattr(db_client, "create_client", crea)
    # il client del thread si ricrea sul trasporto finto; il contenuto di _TLS lo rimette a
    # posto la fixture autouse di Betfair/conftest.py (_ripristina_stato_di_processo_di_db_client)
    db_client._TLS.client = None
    return visti


def _scrittori() -> List[Tuple[str, str, Callable[[], None]]]:
    from Betfair.mike import db as mike_db
    from Betfair.omega import omega_db
    from Betfair.safe_strategy import bot_db
    from Betfair.stream import db as stream_db

    return [
        ("mike/db.py:71 log", "mike_activity",
         lambda: mike_db.log("freno", {"motivo": "liquidita'", "quota": 2.04, "lista": [1, 2]}, event_id=35760084)),
        ("omega/omega_db.py:61 log", "omega_activity",
         lambda: omega_db.log("ciclo", {"eventi": 3, "nota": None})),
        ("safe_strategy/bot_db.py:87 log", "safe_strategy_activity",
         lambda: bot_db.log("rifiuto", {"motivo": "spread", "x": 1.5})),
        ("stream/db.py:690 insert_alert", "live_alerts",
         lambda: stream_db.insert_alert("WARN", "LIMITE", "m" * 700, None)),
        ("stream/db.py:981 insert_live_journal", "betfair_live_journal",
         lambda: stream_db.insert_live_journal({"mode": "paper", "action": "place", "market_id": "1.234",
                                                "selection_id": 47972, "side": "back", "price": 2.02, "size": 2.0,
                                                "book": {"b": [[2.02, 10.0]]}, "inplay": True})),
    ]


@pytest.mark.parametrize("indice", range(5))
def test_riga_consegnata_identica_a_quella_di_oggi(tmp_path: Path, inserti: List[Tuple[str, Any]],
                                                   indice: int) -> None:
    nome, tabella, chiama = _scrittori()[indice]
    chiama()
    assert len(inserti) == 1, f"{nome}: atteso UN insert, visti {inserti}"
    tabella_oggi, corpo_oggi = inserti[0]
    assert tabella_oggi == tabella
    srv = PostgrestFinto()
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        a.scrivi(tabella, corpo_oggi)
        assert a.conferma()
        esito = PostinoLocale(a, CloudProva(srv)).drena()
        assert (esito.consegnate, esito.dead_letter) == (1, 0), esito
    finally:
        a.chiudi()
    rpc = [c for rotta, c in srv.richieste if rotta == "/rpc/postino_consegna"]
    assert len(rpc) == 1 and rpc[0]["p_tabella"] == tabella and rpc[0]["p_op"] == "insert"
    consegnata = rpc[0]["p_righe"][0]
    aggiunte = set(consegnata) - set(corpo_oggi)
    assert aggiunte == {"uid", COLONNE_TEMPO_PREDEFINITE[tabella]}, aggiunte
    assert {k: v for k, v in consegnata.items() if k not in aggiunte} == corpo_oggi
