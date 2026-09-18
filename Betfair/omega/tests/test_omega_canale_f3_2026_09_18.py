"""F3 - OMEGA PUBBLICA LE RIGHE CHE SCRIVE (18/09/2026).

Oggi Omega spinge sul canale 47334 solo i numeri di testata (``omega_stato``).
Posizioni, attivita' e PROPOSTE di chiusura la pagina le vede solo passando dal
database. Qui si aggiunge la pubblicazione - e nient'altro: nessuna decisione
di Omega cambia, ne' quando apre, ne' quanto, ne' a che prezzo.

Le regole difese sono le stesse di Mike: si pubblica dopo la scrittura riuscita,
si pubblica la riga che il database ha restituito, l'interruttore e' spento di
serie e un canale morto non ferma il bot.
"""
from __future__ import annotations

import pytest

from Betfair.omega import omega_db as D
from Betfair.stream import canale_bot as CB


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

    def insert(self, payload):  # noqa: ANN001, ANN201
        self._verbo = "insert"
        self._diario.append(("insert", self._nome, payload))
        return self

    def update(self, payload):  # noqa: ANN001, ANN201
        self._verbo = "update"
        self._diario.append(("update", self._nome, payload))
        return self

    def eq(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
        return self

    def limit(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
        return self

    def order(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
        return self

    def execute(self):  # noqa: ANN201
        self._diario.append(("execute", self._nome, self._verbo))
        chiave = f"{self._nome}:{self._verbo}"
        if chiave in self._risposte:
            return self._risposte[chiave]
        return self._risposte.get(self._nome, RispostaFinta([]))


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


@pytest.fixture
def banco(monkeypatch):
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
    "id": 512, "event_id": "35760084", "event_name": "Foo v Bar",
    "market_id": "1.24", "selection_id": 47973, "runner_name": "3 - 2",
    "side": "lay", "mode": "live", "price": 30.0, "size": 1.0,
    "liability": 29.0, "commission": 0.05, "target": 2.0,
    "minute_at_entry": 61, "score_at_entry": "1 - 1", "kickoff": None,
    "status": "open", "pnl": 0.0, "bet_id": "998",
    "placed_at": "2026-09-18T10:00:00+00:00", "settled_at": None,
    "meta": {"phase": "placed"},
}
RIGA_ATTIVITA = {"id": 3, "kind": "skip", "payload": {"reason": "veto"},
                 "created_at": "2026-09-18T10:00:00+00:00"}
RIGA_PROPOSTA = {"id": 88, "kind": "cashout", "status": "proposed",
                 "payload": {"trade_id": 512}, "result": None,
                 "created_at": "2026-09-18T10:00:00+00:00",
                 "updated_at": "2026-09-18T10:00:00+00:00"}


def test_la_posizione_esce_sul_canale_dopo_la_scrittura(banco):
    banco["risposte"]["omega_trades"] = RispostaFinta([RIGA_TRADE])
    assert D.insert_trade(dict(RIGA_TRADE)) == 512
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["omega_posizioni"]
    assert set(msg) - set(CB.CHIAVI_META) == set(RIGA_TRADE)
    for k, v in RIGA_TRADE.items():
        assert msg[k] == v and type(msg[k]) is type(v), k


def test_laggiornamento_di_una_posizione_esce_intero(banco):
    banco["risposte"]["omega_trades"] = RispostaFinta([{**RIGA_TRADE, "status": "won", "pnl": 0.95}])
    D.update_trade(512, status="won", pnl=0.95)
    _, msg = banco["canale"].inviati[0]
    assert msg["id"] == 512 and msg["status"] == "won" and msg["event_id"] == "35760084"


def test_lattivita_esce_sul_canale(banco):
    banco["risposte"]["omega_activity"] = RispostaFinta([RIGA_ATTIVITA])
    D.log("skip", {"reason": "veto"})
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["omega_attivita"]
    assert set(msg) - set(CB.CHIAVI_META) == set(RIGA_ATTIVITA)


def test_la_proposta_nuova_esce_sul_canale(banco):
    banco["risposte"]["omega_manual_requests:select"] = RispostaFinta([])
    banco["risposte"]["omega_manual_requests:insert"] = RispostaFinta([RIGA_PROPOSTA])
    assert D.scrivi_proposta_di_chiusura(512, {"motivo": "target"}) == 88
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["omega_proposta"]
    assert msg["status"] == "proposed" and msg["id"] == 88


def test_la_proposta_aggiornata_esce_sul_canale(banco):
    viva = {**RIGA_PROPOSTA, "payload": {"trade_id": 512, "prezzo": 1.9}}
    banco["risposte"]["omega_manual_requests:select"] = RispostaFinta([RIGA_PROPOSTA])
    banco["risposte"]["omega_manual_requests:update"] = RispostaFinta([viva])
    assert D.scrivi_proposta_di_chiusura(512, {"prezzo": 1.9}) == 88
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["omega_proposta"]
    assert msg["payload"]["prezzo"] == 1.9


def test_la_proposta_decaduta_esce_sul_canale(banco):
    decaduta = {**RIGA_PROPOSTA, "status": "rejected",
                "result": {"decaduta": True, "motivo": "il mercato e' cambiato"}}
    banco["risposte"]["omega_manual_requests:select"] = RispostaFinta([RIGA_PROPOSTA])
    banco["risposte"]["omega_manual_requests:update"] = RispostaFinta([decaduta])
    D.chiudi_proposta(512, "il mercato e' cambiato")
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["omega_proposta"]
    assert msg["status"] == "rejected"


def test_una_scrittura_senza_rappresentazione_non_pubblica_niente(banco):
    banco["risposte"]["omega_trades"] = RispostaFinta([])
    D.update_trade(512, status="won")
    assert banco["canale"].inviati == []


def test_il_mode_e_quello_della_riga(banco):
    banco["risposte"]["omega_trades"] = RispostaFinta([{**RIGA_TRADE, "mode": "paper"}])
    D.insert_trade({"event_id": "1", "mode": "live"})
    assert banco["canale"].inviati[0][1]["mode"] == "paper"


def test_con_linterruttore_spento_non_esce_niente(banco, monkeypatch):
    monkeypatch.setattr(D, "_CANALE_ACCESO", False)
    banco["risposte"]["omega_trades"] = RispostaFinta([RIGA_TRADE])
    banco["risposte"]["omega_activity"] = RispostaFinta([RIGA_ATTIVITA])
    banco["risposte"]["omega_manual_requests:select"] = RispostaFinta([])
    banco["risposte"]["omega_manual_requests:insert"] = RispostaFinta([RIGA_PROPOSTA])
    D.insert_trade(dict(RIGA_TRADE))
    D.update_trade(512, status="won")
    D.log("skip", {})
    D.scrivi_proposta_di_chiusura(512, {})
    assert banco["canale"].inviati == []


def test_linterruttore_di_serie_e_spento(monkeypatch):
    monkeypatch.delenv(CB.ENV_OMEGA, raising=False)
    assert CB.acceso(CB.ENV_OMEGA) is False


def test_col_canale_morto_omega_lavora_identico(banco, monkeypatch):
    monkeypatch.setattr(CB, "_canale", lambda: CanaleFinto(solleva=True))
    banco["risposte"]["omega_trades"] = RispostaFinta([RIGA_TRADE])
    assert D.insert_trade(dict(RIGA_TRADE)) == 512
    D.update_trade(512, status="won")
    assert CB.statistiche()["errori"] == 2


def test_il_canale_di_omega_resta_di_sola_lettura():
    """Mostrare non e' comandare: 47334 non accetta comandi. I comandi sul
    canale sono la fase F6, non questa."""
    import inspect

    from Betfair.omega import omega_service as S

    sorgente = inspect.getsource(S._avvia_canale)
    assert "solo_lettura=True" in sorgente
