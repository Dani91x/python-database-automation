"""B33-3 (coordinatore, 24/09): Omega apriva DUE client verso la porta 47336
dello scanner quando ``OMEGA_LEGGE_CANALE`` (client proprio, ``avvia_client_scan``)
e ``PUNTEGGI_CANALE`` (client del feed unico, ``scan_feed.lettore_canale``) sono
ACCESI insieme nello stesso processo: due connessioni WebSocket allo stesso
scopo (righe di ``safe_strategy_scan``), invece di una sola condivisa.

Qui si prova che, con la correzione:

  1. con ENTRAMBI gli interruttori accesi, ``avvia_client_scan()`` RIUSA il
     client di ``scan_feed.lettore_canale()``: un solo ``ClientScan`` costruito
     in totale (non due);
  2. le righe che arrivano sul client condiviso sono viste IDENTICHE dai due
     lati -- Omega (``S._canale_scan_attivo()`` / ``S._CLIENT_SCAN["cache"]``)
     e il feed unico (``scan_feed.ScanRowCache`` / ``_fondi_canale``) -- stesso
     oggetto ``CacheScan``, stessa riga;
  3. la sveglia del ciclo di Omega (``evento``/``interessa``) resta collegata
     sul client condiviso esattamente come sul client proprio;
  4. ``ferma_client_scan()`` NON ferma il client condiviso (lo possiede
     ``scan_feed``, non Omega): ``scan_feed.lettore_canale()`` lo ritrova
     ancora vivo dopo;
  5. con SOLO ``OMEGA_LEGGE_CANALE`` acceso (``PUNTEGGI_CANALE`` spento, il
     caso di oggi in produzione) il comportamento resta BYTE-IDENTICO a prima:
     Omega costruisce il proprio client, come sempre.

Finti con le chiavi del vero: il messaggio e' quello che il produttore manda
(``{"t": "scan_calcio", "d": riga}``, le stesse quattro chiavi di
``scan_feed._fetch_rows``), incassato da ``canale_scan.ClientScan.incassa``
VERO (senza socket: si sostituisce solo ``avvia`` per non aprire un thread/rete
nel test, come fa ``test_omega_legge_canale_2026_09_23.py`` e
``test_punteggi_canale_2026_09_23.py``). File ASCII-only.
"""
from __future__ import annotations

import json
import time
from typing import Any, List

import pytest

from Betfair.omega import omega_service as S
from Betfair.safe_strategy import canale_scan as CS
from Betfair.stream.scores import scan_feed as SF

ENV_OMEGA = "OMEGA_LEGGE_CANALE"
ENV_FEED = SF.ENV_PUNTEGGI_CANALE


class _ClientSenzaRete(CS.ClientScan):
    """Lo stesso ``ClientScan`` vero, senza thread/socket nel test."""

    def avvia(self) -> None:
        pass


def _messaggio(riga: dict) -> str:
    return json.dumps({"t": "scan_calcio", "d": riga})


def _riga(eid: str, minute: int, odds_ts_ms: int = 1) -> dict:
    now = time.time()
    return {
        "event_id": eid,
        "sport": "calcio",
        "payload": {"minute": minute, "score_home": 0, "score_away": 0,
                    "inplay": True, "odds_ts_ms": odds_ts_ms},
        "updated_at": __import__("datetime").datetime.fromtimestamp(
            now, __import__("datetime").timezone.utc).isoformat(),
    }


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    """Interruttori spenti, lettore del feed unico azzerato, client di Omega
    azzerato: nessuno stato di un test passa al successivo."""
    monkeypatch.delenv(ENV_OMEGA, raising=False)
    monkeypatch.delenv(ENV_FEED, raising=False)
    SF.azzera_lettore_canale()
    S._CLIENT_SCAN.update({"client": None, "cache": None, "condiviso": False})
    monkeypatch.setattr(CS, "ClientScan", _ClientSenzaRete)
    yield
    S.ferma_client_scan()
    SF.azzera_lettore_canale()


# ===========================================================================
# (1)+(2) entrambi accesi: UN client condiviso, righe identiche dai due lati
# ===========================================================================
def test_entrambi_accesi_un_solo_client_costruito_in_totale(monkeypatch):
    monkeypatch.setenv(ENV_OMEGA, "1")
    monkeypatch.setenv(ENV_FEED, "1")

    # ordine A: il feed unico si avvia per primo (come farebbe ``_feed_row``
    # alla prima chiamata), POI Omega.
    lettore = SF.lettore_canale()
    assert lettore is not None
    assert S.avvia_client_scan() is True

    assert S._CLIENT_SCAN["client"] is lettore, "Omega deve riusare il client del feed unico"
    assert S._CLIENT_SCAN["cache"] is lettore.cache
    assert S._CLIENT_SCAN["condiviso"] is True


def test_entrambi_accesi_ordine_inverso_stesso_risultato(monkeypatch):
    monkeypatch.setenv(ENV_OMEGA, "1")
    monkeypatch.setenv(ENV_FEED, "1")

    # ordine B: Omega parte per primo.
    assert S.avvia_client_scan() is True
    client_omega = S._CLIENT_SCAN["client"]
    lettore = SF.lettore_canale()

    assert client_omega is lettore, "una connessione sola, chi arriva per primo o dopo"
    assert S._CLIENT_SCAN["condiviso"] is True


def test_righe_identiche_dai_due_lati_sul_client_condiviso(monkeypatch):
    monkeypatch.setenv(ENV_OMEGA, "1")
    monkeypatch.setenv(ENV_FEED, "1")
    assert S.avvia_client_scan() is True
    lettore = SF.lettore_canale()
    client = S._CLIENT_SCAN["client"]
    assert client is lettore

    riga = _riga("E1", minute=57)
    assert client.incassa(_messaggio(riga))

    # lato Omega: la stessa cache che ``_canale_scan_attivo``/``_riga_dal_canale``
    # userebbero durante un giro vero.
    dal_lato_omega = S._CLIENT_SCAN["cache"].riga("E1")
    # lato feed unico: la stessa cache, letta dal lettore di processo.
    dal_lato_feed = SF.lettore_canale().cache.riga("E1")

    assert dal_lato_omega == dal_lato_feed, "stessa CacheScan condivisa: riga identica"
    assert dal_lato_omega["payload"]["minute"] == 57


# ===========================================================================
# (3) la sveglia del ciclo resta collegata sul client condiviso
# ===========================================================================
def test_sveglia_di_omega_resta_collegata_sul_client_condiviso(monkeypatch):
    monkeypatch.setenv(ENV_OMEGA, "1")
    monkeypatch.setenv(ENV_FEED, "1")
    lettore = SF.lettore_canale()
    assert lettore.evento is None and lettore.interessa is None   # feed unico: nessuna sveglia di suo

    assert S.avvia_client_scan() is True
    client = S._CLIENT_SCAN["client"]
    assert isinstance(client.evento, S._SvegliaDalCanale)
    assert client.interessa is S._evento_con_posizione_viva

    S._ricorda_posizioni_vive("open", [{"event_id": "E1", "status": "open"}])
    prima = client.svegliate
    client.incassa(_messaggio(_riga("E1", minute=10)))
    assert client.svegliate == prima + 1, "la riga di una partita con posizione viva sveglia il ciclo"


def test_sveglia_non_sovrascrive_un_aggancio_gia_fatto(monkeypatch):
    """Se il client condiviso ha GIA' un aggancio (caso limite, non quello di
    oggi: nessun altro in questo processo lo usa), Omega non lo sovrascrive."""
    monkeypatch.setenv(ENV_OMEGA, "1")
    monkeypatch.setenv(ENV_FEED, "1")
    lettore = SF.lettore_canale()

    class _Sentinella:
        def set(self) -> None:
            pass
    sentinella = _Sentinella()
    lettore.evento = sentinella
    lettore.interessa = lambda eid: True

    assert S.avvia_client_scan() is True
    assert S._CLIENT_SCAN["client"].evento is sentinella, "aggancio esistente non toccato"


# ===========================================================================
# (4) ferma_client_scan() NON ferma il client condiviso
# ===========================================================================
def test_ferma_client_scan_non_ferma_il_condiviso(monkeypatch):
    monkeypatch.setenv(ENV_OMEGA, "1")
    monkeypatch.setenv(ENV_FEED, "1")
    assert S.avvia_client_scan() is True
    lettore_prima = SF.lettore_canale()

    fermati: List[Any] = []
    monkeypatch.setattr(_ClientSenzaRete, "ferma", lambda self: fermati.append(self))

    S.ferma_client_scan()

    assert fermati == [], "il client condiviso non si ferma da Omega"
    assert S._CLIENT_SCAN["client"] is None       # Omega dimentica comunque il suo riferimento
    assert S._CLIENT_SCAN["condiviso"] is False
    assert SF.lettore_canale() is lettore_prima, "il feed unico lo ritrova ancora vivo"


def test_ferma_client_scan_ferma_il_client_proprio_come_prima(monkeypatch):
    """Regressione: SENZA condivisione (PUNTEGGI_CANALE spento) il comportamento
    di ``ferma_client_scan`` resta quello di sempre -- il client si ferma."""
    monkeypatch.setenv(ENV_OMEGA, "1")
    assert S.avvia_client_scan() is True
    assert S._CLIENT_SCAN["condiviso"] is False

    fermati: List[Any] = []
    monkeypatch.setattr(_ClientSenzaRete, "ferma", lambda self: fermati.append(self))
    client = S._CLIENT_SCAN["client"]
    S.ferma_client_scan()
    assert fermati == [client]
    assert S._CLIENT_SCAN["client"] is None


def test_svuota_le_cache_non_azzera_la_memoria_condivisa(monkeypatch):
    """B33-3: ``svuota_le_cache`` (riavvio/test) non deve svuotare la memoria
    del feed unico quando il client e' condiviso -- non e' sua."""
    monkeypatch.setenv(ENV_OMEGA, "1")
    monkeypatch.setenv(ENV_FEED, "1")
    assert S.avvia_client_scan() is True
    client = S._CLIENT_SCAN["client"]
    client.incassa(_messaggio(_riga("E1", minute=44)))
    assert client.cache.riga("E1") is not None

    S.svuota_le_cache()

    assert client.cache.riga("E1") is not None, "la memoria del feed unico resta intatta"


# ===========================================================================
# (5) solo OMEGA_LEGGE_CANALE acceso: comportamento BYTE-IDENTICO a prima
# ===========================================================================
def test_solo_omega_acceso_costruisce_il_proprio_client_come_prima(monkeypatch):
    monkeypatch.setenv(ENV_OMEGA, "1")
    # PUNTEGGI_CANALE resta spento (fixture _pulito): scan_feed.lettore_canale() -> None
    assert SF.lettore_canale() is None

    assert S.avvia_client_scan() is True
    client = S._CLIENT_SCAN["client"]
    assert isinstance(client, CS.ClientScan)
    assert S._CLIENT_SCAN["condiviso"] is False
    assert isinstance(client.evento, S._SvegliaDalCanale)
    assert client.interessa is S._evento_con_posizione_viva
    # nessun client del feed unico e' stato creato di striscio
    assert SF.lettore_canale() is None


def test_solo_feed_acceso_omega_non_costruisce_niente(monkeypatch):
    """Il rovescio: PUNTEGGI_CANALE acceso, OMEGA_LEGGE_CANALE spento ->
    ``avvia_client_scan`` esce subito (interruttore di Omega spento), il
    client del feed unico resta l'unico, e Omega non lo tocca."""
    monkeypatch.setenv(ENV_FEED, "1")
    lettore = SF.lettore_canale()
    assert lettore is not None

    assert S.avvia_client_scan() is False
    assert S._CLIENT_SCAN["client"] is None
    assert lettore.evento is None and lettore.interessa is None
