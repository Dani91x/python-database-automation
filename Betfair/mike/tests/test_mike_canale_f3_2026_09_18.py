"""F3 - MIKE PUBBLICA LE RIGHE CHE SCRIVE (18/09/2026).

Oggi Mike spinge sul canale 47333 la scheda della partita (``mike_event``) e i
numeri di testata (``mike_stato``). Le POSIZIONI e le ATTIVITA' - cioe' le
righe di ``mike_trades`` e ``mike_activity`` - la pagina le vede solo passando
dal database, al poll di 30 s.

Questi test difendono le regole della fase, non l'ottimizzazione:

* si pubblica **dopo** la scrittura riuscita, e si pubblica **la riga che il
  database ha restituito**: mai un messaggio per una riga che non esiste;
* con l'interruttore **spento** (il default) non esce niente e non si esegue
  nulla in piu': il percorso e' quello di prima, istruzione per istruzione;
* il canale morto non ferma Mike: la riga finisce sul database lo stesso;
* il ``mode`` viaggia perche' sta nella riga, mai perche' lo sa il servizio.
"""
from __future__ import annotations

import pytest

from Betfair.mike import db as D
from Betfair.stream import canale_bot as CB


class RispostaFinta:
    def __init__(self, data) -> None:  # noqa: ANN001
        self.data = data


class TabellaFinta:
    """Registra l'ordine delle chiamate: serve a provare che si pubblica DOPO."""

    def __init__(self, diario, nome, risposta) -> None:  # noqa: ANN001
        self._diario = diario
        self._nome = nome
        self._risposta = risposta

    def insert(self, payload):  # noqa: ANN001, ANN201
        self._diario.append(("insert", self._nome, payload))
        return self

    def update(self, payload):  # noqa: ANN001, ANN201
        self._diario.append(("update", self._nome, payload))
        return self

    def eq(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
        return self

    def execute(self):  # noqa: ANN201
        self._diario.append(("execute", self._nome, None))
        return self._risposta


class ClientFinto:
    def __init__(self, diario, risposte) -> None:  # noqa: ANN001
        self._diario = diario
        self._risposte = risposte

    def table(self, nome):  # noqa: ANN001, ANN201
        return TabellaFinta(self._diario, nome, self._risposte.get(nome, RispostaFinta([])))


class CanaleFinto:
    def __init__(self, solleva: bool = False) -> None:
        self.inviati: list[tuple[str, dict]] = []
        self.solleva = bool(solleva)

    def publish(self, topic, payload):  # noqa: ANN001, ANN201
        if self.solleva:
            raise RuntimeError("canale morto")
        self.inviati.append((topic, payload))


@pytest.fixture
def banco(monkeypatch):
    """Database finto + canale finto + interruttore ACCESO."""
    diario: list = []
    risposte: dict = {}
    canale = CanaleFinto()
    monkeypatch.setattr(D, "_sb", lambda: ClientFinto(diario, risposte))
    monkeypatch.setattr(CB, "_canale", lambda: canale)
    monkeypatch.setattr(D, "_CANALE_ACCESO", True)
    CB.azzera_statistiche()
    yield {"diario": diario, "risposte": risposte, "canale": canale}
    CB.azzera_statistiche()


RIGA_TRADE = {
    "id": 41, "event_id": "35760084", "event_name": "Foo v Bar",
    "market_id": "1.24", "selection_id": 47973, "selection_name": "Under 3.5",
    "side": "back", "mode": "paper", "price": 1.9, "size": 2.0,
    "liability": 2.0, "commission": 0.05, "status": "open", "pnl": 0.0,
    "bet_id": "3123", "placed_at": "2026-09-18T10:00:00+00:00",
    "settled_at": None, "meta": {"phase": "reserved"}, "leg": "under35",
}
RIGA_ATTIVITA = {"id": 9, "kind": "skip", "event_id": "35760084",
                 "payload": {"reason": "no_edge"},
                 "created_at": "2026-09-18T10:00:00+00:00"}


# -------------------------------------------------- si pubblica DOPO la scrittura
def test_la_posizione_esce_sul_canale_dopo_la_scrittura(banco):
    banco["risposte"]["mike_trades"] = RispostaFinta([RIGA_TRADE])
    assert D.insert_trade(dict(RIGA_TRADE)) == 41
    assert [t for t, _ in banco["canale"].inviati] == [CB.TOPIC["mike_posizioni"]]
    passi = [p[0] for p in banco["diario"]]
    assert passi == ["insert", "execute"], "la scrittura resta una sola"


def test_il_messaggio_e_la_riga_che_il_database_ha_restituito(banco):
    banco["risposte"]["mike_trades"] = RispostaFinta([RIGA_TRADE])
    D.insert_trade({"event_id": "35760084"})   # cio' che MANDIAMO e' parziale
    _, msg = banco["canale"].inviati[0]
    assert set(msg) - set(CB.CHIAVI_META) == set(RIGA_TRADE)
    for k, v in RIGA_TRADE.items():
        assert msg[k] == v and type(msg[k]) is type(v), k


def test_laggiornamento_di_una_posizione_esce_sul_canale(banco):
    aggiornata = {**RIGA_TRADE, "status": "won", "pnl": 1.8}
    banco["risposte"]["mike_trades"] = RispostaFinta([aggiornata])
    D.update_trade(41, status="won", pnl=1.8)
    _, msg = banco["canale"].inviati[0]
    assert msg["status"] == "won" and msg["pnl"] == 1.8
    assert msg["id"] == 41, "la riga INTERA, non solo i campi toccati"


def test_lattivita_esce_sul_canale(banco):
    banco["risposte"]["mike_activity"] = RispostaFinta([RIGA_ATTIVITA])
    D.log("skip", {"reason": "no_edge"}, event_id="35760084")
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["mike_attivita"]
    assert set(msg) - set(CB.CHIAVI_META) == set(RIGA_ATTIVITA)


def test_una_scrittura_senza_rappresentazione_non_pubblica_niente(banco):
    """Il database e' il registro: senza riga tornata, nessun messaggio."""
    banco["risposte"]["mike_trades"] = RispostaFinta([])
    D.update_trade(41, status="won")
    assert banco["canale"].inviati == []


def test_il_mode_e_quello_della_riga_non_quello_del_servizio(banco):
    banco["risposte"]["mike_trades"] = RispostaFinta([{**RIGA_TRADE, "mode": "live"}])
    D.insert_trade({"event_id": "1", "mode": "paper"})
    assert banco["canale"].inviati[0][1]["mode"] == "live"


# --------------------------------------------------------- interruttore SPENTO
def test_con_linterruttore_spento_non_esce_niente(banco, monkeypatch):
    monkeypatch.setattr(D, "_CANALE_ACCESO", False)
    banco["risposte"]["mike_trades"] = RispostaFinta([RIGA_TRADE])
    banco["risposte"]["mike_activity"] = RispostaFinta([RIGA_ATTIVITA])
    D.insert_trade(dict(RIGA_TRADE))
    D.update_trade(41, status="won")
    D.log("skip", {})
    assert banco["canale"].inviati == []


def test_con_linterruttore_spento_non_si_costruisce_nemmeno_il_messaggio(banco, monkeypatch):
    """A interruttore spento il percorso e' quello di prima: non si chiama
    nemmeno il modulo della pubblicazione."""
    monkeypatch.setattr(D, "_CANALE_ACCESO", False)
    chiamate: list = []
    monkeypatch.setattr(CB, "busta", lambda r: chiamate.append(r) or dict(r))
    banco["risposte"]["mike_trades"] = RispostaFinta([RIGA_TRADE])
    D.insert_trade(dict(RIGA_TRADE))
    assert chiamate == []


def test_linterruttore_di_serie_e_spento(monkeypatch):
    monkeypatch.delenv(CB.ENV_MIKE, raising=False)
    assert CB.acceso(CB.ENV_MIKE) is False


# ------------------------------------------------- il canale non ferma il bot
def test_col_canale_morto_la_riga_va_sul_database_lo_stesso(banco, monkeypatch):
    monkeypatch.setattr(CB, "_canale", lambda: CanaleFinto(solleva=True))
    banco["risposte"]["mike_trades"] = RispostaFinta([RIGA_TRADE])
    assert D.insert_trade(dict(RIGA_TRADE)) == 41      # nessuna eccezione
    assert CB.statistiche()["errori"] == 1, "l'errore si conta, non si perde"


def test_col_canale_morto_laggiornamento_non_solleva(banco, monkeypatch):
    monkeypatch.setattr(CB, "_canale", lambda: CanaleFinto(solleva=True))
    banco["risposte"]["mike_trades"] = RispostaFinta([RIGA_TRADE])
    D.update_trade(41, status="won")                    # nessuna eccezione


def test_una_scrittura_che_fallisce_non_pubblica(banco, monkeypatch):
    """Se il database rifiuta, sul canale non esce niente: il registro comanda."""
    class TabellaKO(TabellaFinta):
        def execute(self):  # noqa: ANN201
            raise RuntimeError("PostgREST KO")

    class ClientKO(ClientFinto):
        def table(self, nome):  # noqa: ANN001, ANN201
            return TabellaKO(self._diario, nome, None)

    monkeypatch.setattr(D, "_sb", lambda: ClientKO(banco["diario"], {}))
    with pytest.raises(RuntimeError):
        D.insert_trade(dict(RIGA_TRADE))
    assert banco["canale"].inviati == []
