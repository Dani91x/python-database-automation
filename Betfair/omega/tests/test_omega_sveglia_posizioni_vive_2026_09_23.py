"""23/09 - B-2 (revisore B): la sveglia di Omega dal canale dello scanner.

Difetto: con ``OMEGA_LEGGE_CANALE=1`` ogni riga fresca di una partita in
``_CACHE_FEED_CHIESTO_A`` (posizioni E candidate valutate negli ultimi 120 s)
alzava la sveglia con pavimento 5 s, scavalcando il pavimento F5
``poll_interval_s`` (20 s): da 3 a 12 ``run_once`` completi al minuto, con le
loro letture DB.

Correzione (decisione del coordinatore, da portare all'utente): la sveglia dal
canale scatta SOLO per partite con una POSIZIONE VIVA del bot ('open'/'pending'
lette dall'ultimo giro, nessuna lettura in piu'); pavimento
``OMEGA_CANALE_GIRO_MINIMO_S`` (default 5 s). Senza posizioni vive nessun
anticipo: il giro resta a ``poll_interval_s``.

Finti: client VERO di Safe (``ClientScan``) senza thread, ``Sveglia`` vera con
orologio a mano, righe con le chiavi di ``safe_strategy_scan``/``omega_trades``.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest

from Betfair.omega import omega_service as S
from Betfair.omega.tests import traccia_canale_scan_2026_09_23 as T
from Betfair.safe_strategy import canale_scan as CS
from Betfair.stream.scores import scan_feed as SF

ENV = "OMEGA_LEGGE_CANALE"


@pytest.fixture(autouse=True)
def _punteggi_canale_neutro(monkeypatch):
    """B33-3 (coordinatore, 24/09): come in ``test_omega_legge_canale_2026_09_23.py``
    -- questo file prova la sveglia col client PROPRIO di Omega; un
    ``PUNTEGGI_CANALE`` REALE nell'ambiente farebbe riusare il client
    condiviso del feed unico al posto di quello che ``ambiente`` costruisce
    e osserva (``client.svegliate``)."""
    monkeypatch.delenv(SF.ENV_PUNTEGGI_CANALE, raising=False)
    SF.azzera_lettore_canale()
    yield
    SF.azzera_lettore_canale()


class _Orologio:
    def __init__(self, t0: float = 1000.0) -> None:
        self.t = float(t0)
        self.dormite: list = []

    def ora(self) -> float:
        return self.t

    def dormi(self, quanto: float) -> None:
        self.dormite.append(float(quanto))
        self.t += float(quanto)


def _msg(eid: str) -> str:
    return json.dumps({"t": "scan_calcio", "d": T.riga_scan(eid, time.time(), minute=40)})


def _trade(eid: str, status: str, tid: int = 1) -> dict:
    """Riga di ``omega_trades`` con le chiavi del vero (quelle usate qui)."""
    return {"id": tid, "event_id": eid, "market_id": f"1.{tid}", "status": status,
            "mode": "paper", "origin": "auto", "closes_trade_id": None, "meta": {}}


@pytest.fixture
def ambiente(monkeypatch):
    from Betfair.stream import sveglia_canale as SV

    monkeypatch.setenv(ENV, "1")
    monkeypatch.delenv(S.ENV_GIRO_MINIMO, raising=False)
    monkeypatch.setitem(S._CLIENT_SCAN, "client", None)
    monkeypatch.setitem(S._CLIENT_SCAN, "cache", None)
    monkeypatch.setattr(CS.ClientScan, "avvia", lambda self: None)
    orol = _Orologio()
    monkeypatch.setattr(S, "_SVEGLIA", SV.Sveglia("omega", ora=orol.ora, dormi=orol.dormi))
    monkeypatch.setattr(S.time, "sleep", lambda _s: (_ for _ in ()).throw(
        AssertionError("col canale acceso la dormita non e' time.sleep")))
    S._CACHE_POSIZIONI_VIVE.clear()
    S._CACHE_FEED_CHIESTO_A.clear()
    assert S.avvia_client_scan() is True
    client = S._CLIENT_SCAN["client"]
    yield client, orol
    S.ferma_client_scan()
    S._CACHE_FEED_CHIESTO_A.clear()
    S._CACHE_POSIZIONI_VIVE.clear()


def test_partita_seguita_senza_posizione_nessuna_sveglia(ambiente):
    client, orol = ambiente
    S._CACHE_FEED_CHIESTO_A["C1"] = 0.0          # candidata valutata dal ciclo
    assert client.incassa(_msg("C1"))            # la riga entra nella memoria...
    assert client.svegliate == 0                 # ...ma non sveglia il ciclo
    # nessuna sveglia alzata: la dormita resta quella di poll_interval_s
    assert S._SVEGLIA.statistiche()["sveglie"] == 0


def test_partita_con_posizione_open_sveglia(ambiente):
    client, orol = ambiente
    S._ricorda_posizioni_vive("open", [_trade("E1", "open")])
    assert client.incassa(_msg("E1"))
    # controllato PRIMA della dormita: senza sveglia l'orologio a mano non avanza
    assert client.svegliate == 1
    S._dormi_o_sveglia(20.0, {"poll_interval_s": 20})
    assert orol.dormite == [5.0]                 # pavimento del canale, non 20 s


def test_partita_con_posizione_pending_sveglia(ambiente):
    client, _ = ambiente
    S._ricorda_posizioni_vive("pending", [_trade("P1", "pending")])
    assert client.incassa(_msg("P1"))
    assert client.svegliate == 1


def test_posizione_chiusa_smette_di_svegliare(ambiente):
    client, _ = ambiente
    S._ricorda_posizioni_vive("open", [_trade("E1", "open")])
    S._ricorda_posizioni_vive("open", [])        # il giro dopo non la trova piu'
    assert client.incassa(_msg("E1"))
    assert client.svegliate == 0


def test_riga_con_altro_stato_non_conta(ambiente):
    client, _ = ambiente
    S._ricorda_posizioni_vive("open", [_trade("H1", "hedged")])
    assert client.incassa(_msg("H1"))
    assert client.svegliate == 0


def test_pavimento_rispettato_dodici_giri_al_minuto_al_massimo(ambiente):
    client, orol = ambiente
    S._ricorda_posizioni_vive("open", [_trade("E1", "open")])
    inizio, giri = orol.t, 0
    while orol.t - inizio < 60.0:
        client.incassa(_msg("E1"))
        assert client.svegliate == giri + 1      # mai dormire senza sveglia (orologio a mano)
        S._dormi_o_sveglia(20.0, {"poll_interval_s": 20})
        giri += 1
    assert giri == 12
    assert all(d == pytest.approx(5.0) for d in orol.dormite)


def test_pavimento_dal_env_rispettato(ambiente, monkeypatch):
    client, orol = ambiente
    monkeypatch.setenv(S.ENV_GIRO_MINIMO, "10")
    S._ricorda_posizioni_vive("open", [_trade("E1", "open")])
    inizio, giri = orol.t, 0
    while orol.t - inizio < 60.0:
        client.incassa(_msg("E1"))
        assert client.svegliate == giri + 1      # mai dormire senza sveglia (orologio a mano)
        S._dormi_o_sveglia(20.0, {"poll_interval_s": 20})
        giri += 1
    assert giri == 6


def test_senza_posizioni_canale_che_parla_sempre_nessuna_sveglia(ambiente):
    """Il caso del reperto: il canale parla di continuo di partite solo
    valutate. Nessuna sveglia alzata: i giri restano quelli di
    ``poll_interval_s`` (la ``Sveglia`` senza sveglie dorme la cadenza intera).
    La dormita reale non si chiama qui: senza sveglia aspetterebbe il timeout
    sull'orologio vero."""
    client, _ = ambiente
    for eid in ("C1", "C2", "C3"):
        S._CACHE_FEED_CHIESTO_A[eid] = 0.0
    for _ in range(100):
        for eid in ("C1", "C2", "C3"):
            assert client.incassa(_msg(eid))
    assert client.svegliate == 0
    assert S._SVEGLIA.statistiche()["sveglie"] == 0


# ---- chi riempie l'insieme: le letture che il giro fa GIA' -----------------
class _DbPending:
    """Le sole letture di ``poll_flumine_pending`` usate qui (firme di omega_db)."""

    def __init__(self, righe):
        self.righe = righe

    def list_trades(self, status=None):
        return [r for r in self.righe if status is None or r["status"] == status]

    def log(self, *a, **k):
        pass


def test_poll_flumine_pending_annota_le_pending(monkeypatch):
    monkeypatch.delenv("ESITI_ORDINI_CANALE", raising=False)
    S._CACHE_POSIZIONI_VIVE.clear()
    db = _DbPending([_trade("P9", "pending", 9)])
    S.poll_flumine_pending(db=db, params={}, now=datetime.now(timezone.utc))
    assert S._evento_con_posizione_viva("P9")
    assert not S._evento_con_posizione_viva("ALTRO")
    S._CACHE_POSIZIONI_VIVE.clear()


class _Basta(Exception):
    pass


class _DbOpen:
    def __init__(self, righe):
        self.righe = righe

    def open_trades(self):
        return [r for r in self.righe if r["status"] == "open"]

    def log(self, *a, **k):
        pass


def test_settle_open_annota_le_open(monkeypatch):
    S._CACHE_POSIZIONI_VIVE.clear()
    # ci si ferma subito dopo la lettura: qui interessa solo l'annotazione
    monkeypatch.setattr(S, "sorveglia_posizione_di_conto", lambda **k: None)
    monkeypatch.setattr(S, "chiudi_eventi_in_attesa", lambda **k: None)

    def _ferma(*a, **k):
        raise _Basta()
    monkeypatch.setattr(S, "_ids_with_closings", _ferma)
    with pytest.raises(_Basta):
        S.settle_open(params={"commission_pct": 5.0}, market=None,
                      db=_DbOpen([_trade("O7", "open", 7)]), now=datetime.now(timezone.utc))
    assert S._evento_con_posizione_viva("O7")
    S._CACHE_POSIZIONI_VIVE.clear()


def test_svuota_le_cache_dimentica_le_posizioni():
    S._ricorda_posizioni_vive("open", [_trade("E1", "open")])
    S.svuota_le_cache()
    assert not S._evento_con_posizione_viva("E1")
