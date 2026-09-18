"""F3 - I QUATTRO BOT TENNIS SUL CANALE 47337 (18/09/2026).

E' l'asimmetria piu' grossa fra i due sport: il calcio ha un canale per ogni bot
(Mike 47333, Omega 47334, Safe 47335), i quattro bot tennis non ne avevano
nessuno e la pagina li vedeva con un poll da 30 secondi.

Il canale 47337 NON e' un processo nuovo: vive dentro
``tennis_bot_service --bridge-only``, che l'app desktop avvia gia'
(``desktop/main.js:268``). E vive SOLO li': in modalita' ``run()`` questo stesso
modulo ospita il runner tennis, che ha gia' il suo canale 47332 - e un processo
ha un canale solo (difetto D1, corretto in F1: ``start_channel`` su una porta
diversa RIFIUTA).

Le regole difese:
* il canale e' di SOLA LETTURA: mostrare non e' comandare (i comandi sono F6);
* l'interruttore ``TENNIS_BOT_CANALE`` e' SPENTO di serie;
* la cadenza del battito la DICHIARA il servizio, non la indovina la pagina;
* una riga per bot, mai uno stato aggregato;
* il ``mode`` e' quello della riga;
* niente letture in piu' sul database: si pubblica solo cio' che si sta gia'
  scrivendo o si e' gia' letto.
"""
from __future__ import annotations

import inspect

import pytest

from Betfair.stream import canale_bot as CB
from Betfair.stream.tennis_live import tennis_bot_service as S
from Betfair.stream.tennis_live import tennis_db as TDB


class RispostaFinta:
    def __init__(self, data) -> None:  # noqa: ANN001
        self.data = data


class TabellaFinta:
    def __init__(self, diario, nome, risposte) -> None:  # noqa: ANN001
        self._diario = diario
        self._nome = nome
        self._risposte = risposte
        self._verbo = "select"

    def select(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
        self._verbo = "select"
        return self

    def update(self, payload):  # noqa: ANN001, ANN201
        self._verbo = "update"
        self._diario.append(("update", self._nome, payload))
        return self

    def upsert(self, payload, **k):  # noqa: ANN001, ANN201, ARG002
        self._verbo = "upsert"
        self._diario.append(("upsert", self._nome, payload))
        return self

    def eq(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
        return self

    def is_(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
        return self

    def in_(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
        return self

    def execute(self):  # noqa: ANN201
        self._diario.append(("execute", self._nome, self._verbo))
        return self._risposte.get(f"{self._nome}:{self._verbo}",
                                  self._risposte.get(self._nome, RispostaFinta([])))


class ClientFinto:
    def __init__(self, diario, risposte) -> None:  # noqa: ANN001
        self._diario = diario
        self._risposte = risposte

    def table(self, nome):  # noqa: ANN001, ANN201
        return TabellaFinta(self._diario, nome, self._risposte)


class CanaleFinto:
    def __init__(self, solleva: bool = False) -> None:
        self.inviati: list[tuple[str, dict]] = []
        self.solleva = bool(solleva)

    def publish(self, topic, payload):  # noqa: ANN001, ANN201
        if self.solleva:
            raise RuntimeError("canale morto")
        self.inviati.append((topic, payload))


RIGA_SERVIZIO = {
    "bot_key": "tennis_scalper", "status": "running", "mode": "paper",
    "stake": 2, "params": {}, "error": None,
    "stats": {"cadenza_battito_s": 15.0, "partite_esposte": 2,
              "stop_ferma_solo_aperture": True, "motivo_blocco": None},
    "heartbeat_at": "2026-09-18T10:00:00+00:00",
    "stopped_at": None, "updated_at": "2026-09-18T10:00:00+00:00",
}
RIGA_CONTROLLO = {
    "id": 3, "event_id": "35794049", "bot_key": "tennis_scalper",
    "status": "armed", "mode": "paper", "dry_run": False, "stake": 2,
    "params": {}, "error": None, "stats": {"pnl_giornata": 1.25},
    "heartbeat_at": "2026-09-18T10:00:00+00:00", "started_at": None,
    "stopped_at": None, "updated_at": "2026-09-18T10:00:00+00:00",
}


@pytest.fixture
def banco(monkeypatch):
    diario: list = []
    risposte: dict = {}
    canale = CanaleFinto()
    monkeypatch.setattr(TDB, "get_tennis_client", lambda: ClientFinto(diario, risposte))
    monkeypatch.setattr(CB, "_canale", lambda: canale)
    monkeypatch.setattr(TDB, "_CANALE_ACCESO", True)
    CB.azzera_statistiche()
    yield {"diario": diario, "risposte": risposte, "canale": canale}
    CB.azzera_statistiche()


# ---------------------------------------------------------------- stato per bot
def test_lo_stato_di_un_bot_esce_sul_canale_dopo_la_scrittura(banco):
    banco["risposte"]["tennis_bot_service_control"] = RispostaFinta([RIGA_SERVIZIO])
    assert TDB.set_tennis_bot_service_state("tennis_scalper", heartbeat=True) is True
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["tennis_bot_stato"]
    assert set(msg) - set(CB.CHIAVI_META) == set(RIGA_SERVIZIO)
    for k, v in RIGA_SERVIZIO.items():
        assert msg[k] == v and type(msg[k]) is type(v), k


def test_la_cadenza_del_battito_la_dichiara_il_servizio(banco):
    """Difetto 33 del catalogo: la pagina non deve cablare una costante
    propria per giudicare se un battito e' fresco."""
    banco["risposte"]["tennis_bot_service_control"] = RispostaFinta([RIGA_SERVIZIO])
    TDB.set_tennis_bot_service_state("tennis_scalper", heartbeat=True)
    _, msg = banco["canale"].inviati[0]
    assert msg["stats"]["cadenza_battito_s"] == S.CADENZA_BATTITO_S


def test_i_quattro_bot_hanno_una_riga_ciascuno_mai_uno_stato_aggregato(banco):
    righe = [{**RIGA_SERVIZIO, "bot_key": b} for b in S._BOT_KEYS]
    banco["risposte"]["tennis_bot_service_control"] = RispostaFinta(righe)
    TDB.set_tennis_bot_service_state("tennis_scalper", heartbeat=True)
    chiavi = [m["bot_key"] for _, m in banco["canale"].inviati]
    assert chiavi == list(S._BOT_KEYS)
    assert len(banco["canale"].inviati) == 4


def test_una_scrittura_che_il_database_rifiuta_non_pubblica(banco):
    """Tabella assente (migrazione non applicata): niente riga, niente messaggio."""
    class TabellaKO(TabellaFinta):
        def execute(self):  # noqa: ANN201
            raise RuntimeError("PGRST205 Could not find the table "
                               "'public.tennis_bot_service_control'")

    class ClientKO(ClientFinto):
        def table(self, nome):  # noqa: ANN001, ANN201
            return TabellaKO(self._diario, nome, {})

    import Betfair.stream.tennis_live.tennis_db as M
    orig = M.get_tennis_client
    M.get_tennis_client = lambda: ClientKO(banco["diario"], {})
    try:
        assert TDB.set_tennis_bot_service_state("tennis_scalper", heartbeat=True) is False
    finally:
        M.get_tennis_client = orig
    assert banco["canale"].inviati == []


# ------------------------------------------------------- armatura per evento
def test_larmatura_per_evento_esce_sul_canale(banco):
    banco["risposte"]["tennis_bot_control"] = RispostaFinta([RIGA_CONTROLLO])
    TDB.set_tennis_bot_status("35794049", "tennis_scalper", "armed")
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["tennis_bot_posizioni"]
    assert set(msg) - set(CB.CHIAVI_META) == set(RIGA_CONTROLLO)


def test_larmatura_nuova_esce_sul_canale(banco):
    banco["risposte"]["tennis_bot_control"] = RispostaFinta([RIGA_CONTROLLO])
    TDB.upsert_tennis_bot_control({"event_id": "35794049",
                                   "bot_key": "tennis_scalper",
                                   "status": "requested"})
    assert banco["canale"].inviati[0][0] == CB.TOPIC["tennis_bot_posizioni"]


def test_il_mode_e_quello_della_riga(banco):
    banco["risposte"]["tennis_bot_control"] = RispostaFinta([{**RIGA_CONTROLLO, "mode": "live"}])
    TDB.set_tennis_bot_status("35794049", "tennis_scalper", "armed")
    assert banco["canale"].inviati[0][1]["mode"] == "live"


def test_il_pnl_di_giornata_del_bot_viaggia_dentro_le_stats(banco):
    banco["risposte"]["tennis_bot_control"] = RispostaFinta([RIGA_CONTROLLO])
    TDB.set_tennis_bot_status("35794049", "tennis_scalper", "armed")
    assert banco["canale"].inviati[0][1]["stats"]["pnl_giornata"] == 1.25


# --------------------------------------------------------- interruttore SPENTO
def test_con_linterruttore_spento_non_esce_niente(banco, monkeypatch):
    monkeypatch.setattr(TDB, "_CANALE_ACCESO", False)
    banco["risposte"]["tennis_bot_service_control"] = RispostaFinta([RIGA_SERVIZIO])
    banco["risposte"]["tennis_bot_control"] = RispostaFinta([RIGA_CONTROLLO])
    TDB.set_tennis_bot_service_state("tennis_scalper", heartbeat=True)
    TDB.set_tennis_bot_status("35794049", "tennis_scalper", "armed")
    TDB.upsert_tennis_bot_control({"event_id": "1", "bot_key": "tennis_pro"})
    assert banco["canale"].inviati == []


def test_linterruttore_di_serie_e_spento(monkeypatch):
    monkeypatch.delenv(CB.ENV_TENNIS_BOT, raising=False)
    assert CB.acceso(CB.ENV_TENNIS_BOT) is False


# ------------------------------------------------------------------- il canale
def test_il_canale_dei_bot_tennis_e_di_sola_lettura():
    sorgente = inspect.getsource(S._avvia_canale)
    assert "solo_lettura=True" in sorgente


def test_il_canale_dei_bot_tennis_sta_sulla_porta_47337():
    assert CB.PORTA_TENNIS_BOT == 47337
    assert "PORTA_TENNIS_BOT" in inspect.getsource(S._avvia_canale)


def test_col_canale_spento_non_si_apre_nessuna_porta(monkeypatch):
    aperti: list = []
    monkeypatch.setattr(CB, "acceso", lambda nome: False)
    monkeypatch.setattr(S._lc, "start_channel",
                        lambda *a, **k: aperti.append(a) or None)
    S._avvia_canale()
    assert aperti == []


def test_col_canale_acceso_si_apre_la_47337(monkeypatch):
    aperti: list = []

    def _start(porta, sport, solo_lettura=False):  # noqa: ANN001, ANN202
        aperti.append((porta, sport, solo_lettura))
        return object()

    monkeypatch.setattr(CB, "acceso", lambda nome: True)
    monkeypatch.setattr(S._lc, "start_channel", _start)
    S._avvia_canale()
    assert aperti == [(47337, "tennis-bot", True)]


def test_una_porta_occupata_non_ferma_il_servizio(monkeypatch):
    monkeypatch.setattr(CB, "acceso", lambda nome: True)
    monkeypatch.setattr(S._lc, "start_channel", lambda *a, **k: None)
    S._avvia_canale()          # nessuna eccezione


def test_il_canale_non_si_apre_se_start_channel_solleva(monkeypatch):
    def _boom(*a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202, ARG001
        raise RuntimeError("websockets assente")

    monkeypatch.setattr(CB, "acceso", lambda nome: True)
    monkeypatch.setattr(S._lc, "start_channel", _boom)
    S._avvia_canale()          # nessuna eccezione


def test_il_canale_si_accende_solo_nel_ramo_ponte():
    """In ``run()`` questo processo ospita il runner tennis, che ha gia' il suo
    canale 47332: un processo, un canale (difetto D1). Il 47337 vive SOLO nel
    ramo ``--bridge-only``, che e' quello che l'app desktop avvia."""
    sorgente = inspect.getsource(S._main)
    prima, _, dopo = sorgente.partition("if args.bridge_only:")
    assert "_avvia_canale()" in dopo
    assert "_avvia_canale()" not in prima
    assert "_avvia_canale()" not in inspect.getsource(S.run)


# -------------------------------------------------- il canale non ferma il bot
def test_col_canale_morto_il_servizio_lavora_identico(banco, monkeypatch):
    monkeypatch.setattr(CB, "_canale", lambda: CanaleFinto(solleva=True))
    banco["risposte"]["tennis_bot_service_control"] = RispostaFinta([RIGA_SERVIZIO])
    assert TDB.set_tennis_bot_service_state("tennis_scalper", heartbeat=True) is True
    assert CB.statistiche()["errori"] == 1


def test_nessuna_lettura_in_piu_sul_database(banco):
    """Si pubblica solo cio' che si sta gia' scrivendo: la rappresentazione
    torna nella stessa risposta, non con una select in piu' (13/09: il
    database ha un budget di IO)."""
    banco["risposte"]["tennis_bot_service_control"] = RispostaFinta([RIGA_SERVIZIO])
    TDB.set_tennis_bot_service_state("tennis_scalper", heartbeat=True)
    verbi = [v for _, _, v in
             (p for p in banco["diario"] if p[0] == "execute")]
    assert verbi == ["update"], "nessuna select in piu'"
