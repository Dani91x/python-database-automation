"""F3 - IL BOT SAFE PUBBLICA LE RIGHE CHE SCRIVE (18/09/2026).

Safe e' l'unico bot che gioca su DUE sport. La regola che vale piu' di ogni
altra qui e' l'invariante B12 del piano: **calcio e tennis non si mischiano
mai**, nemmeno dentro un payload. Due topic separati, e lo sport che decide il
topic e' quello della RIGA - non quello del servizio, non quello del ciclo.

La seconda regola e' quella del 14/09: ai soldi veri si arriva solo
scrivendolo. Il ``mode`` viaggia perche' sta nella riga.

ATTENZIONE, perimetro: ``bot_service.py`` NON viene toccato da questo lavoro
(la conversione a proposte del 18/09 e' arrivata da un'altra mano). Qui si
tocca solo ``bot_db.py``, cioe' l'imbuto delle scritture.
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import bot_db as D
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

    def in_(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
        return self

    def gte(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
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


RIGA_CALCIO = {
    "id": 771, "event_id": "35760084", "event_name": "Foo v Bar",
    "sport": "calcio", "strategy": "base", "market_id": "1.24",
    "market_type": "MATCH_ODDS", "selection_id": 47973,
    "selection_name": "Foo", "side": "back", "mode": "paper",
    "price": 2.2, "size": 2.0, "liability": 2.0, "commission": 0.05,
    "minute_at_entry": 31, "score_at_entry": "0 - 0", "status": "open",
    "pnl": 0.0, "origin": "auto", "signal_key": "k1",
    "meta": {"phase": "placed"}, "placed_at": "2026-09-18T10:00:00+00:00",
    "settled_at": None,
}
RIGA_TENNIS = {**RIGA_CALCIO, "id": 772, "sport": "tennis",
               "event_id": "35794049", "mode": "live"}
RIGA_ATTIVITA = {"id": 5, "kind": "skip", "payload": {"reason": "stale"},
                 "created_at": "2026-09-18T10:00:00+00:00"}
RIGA_PROPOSTA = {"id": 61, "kind": "cashout", "status": "proposed",
                 "payload": {"trade_id": 771}, "result": None,
                 "created_at": "2026-09-18T10:00:00+00:00",
                 "updated_at": "2026-09-18T10:00:00+00:00"}
RIGA_PROPOSTA_OPP = {**RIGA_PROPOSTA, "id": 62, "kind": "place",
                     "payload": {"opp_key": "o1", "sport": "calcio"}}


# ------------------------------------------- calcio e tennis non si mischiano
def test_la_posizione_di_calcio_va_sul_topic_del_calcio(banco):
    banco["risposte"]["safe_strategy_trades"] = RispostaFinta([RIGA_CALCIO])
    assert D.insert_trade(dict(RIGA_CALCIO)) == 771
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["safe_posizioni_calcio"]
    assert set(msg) - set(CB.CHIAVI_META) == set(RIGA_CALCIO)
    for k, v in RIGA_CALCIO.items():
        assert msg[k] == v and type(msg[k]) is type(v), k


def test_la_posizione_di_tennis_va_sul_topic_del_tennis(banco):
    banco["risposte"]["safe_strategy_trades"] = RispostaFinta([RIGA_TENNIS])
    D.insert_trade(dict(RIGA_TENNIS))
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["safe_posizioni_tennis"]
    assert msg["sport"] == "tennis"


def test_il_topic_del_calcio_non_porta_mai_una_riga_di_tennis(banco):
    banco["risposte"]["safe_strategy_trades"] = RispostaFinta([RIGA_CALCIO, RIGA_TENNIS])
    D.update_trade(771, status="open")
    per_topic = {t: m["sport"] for t, m in banco["canale"].inviati}
    assert per_topic[CB.TOPIC["safe_posizioni_calcio"]] == "calcio"
    assert per_topic[CB.TOPIC["safe_posizioni_tennis"]] == "tennis"


def test_lo_sport_lo_decide_la_riga_non_il_servizio(banco):
    """Anche se il ciclo sta lavorando il calcio, una riga di tennis esce sul
    topic del tennis: il topic si legge dal dato, non dal contesto."""
    banco["risposte"]["safe_strategy_trades"] = RispostaFinta([RIGA_TENNIS])
    D.insert_trade({"event_id": "1", "sport": "calcio"})
    assert banco["canale"].inviati[0][0] == CB.TOPIC["safe_posizioni_tennis"]


def test_una_riga_senza_sport_non_esce_su_nessun_topic(banco):
    """Fail-closed: meglio niente che sul topic sbagliato."""
    senza = {k: v for k, v in RIGA_CALCIO.items() if k != "sport"}
    banco["risposte"]["safe_strategy_trades"] = RispostaFinta([senza])
    D.insert_trade(dict(senza))
    assert banco["canale"].inviati == []


def test_uno_sport_sconosciuto_non_esce_su_nessun_topic(banco):
    banco["risposte"]["safe_strategy_trades"] = RispostaFinta([{**RIGA_CALCIO, "sport": "basket"}])
    D.insert_trade(dict(RIGA_CALCIO))
    assert banco["canale"].inviati == []


# ------------------------------------------------------------ mode della riga
def test_il_mode_e_quello_della_riga_non_quello_del_servizio(banco):
    banco["risposte"]["safe_strategy_trades"] = RispostaFinta([RIGA_CALCIO, RIGA_TENNIS])
    D.update_trade(771, status="open")
    modi = sorted(m["mode"] for _, m in banco["canale"].inviati)
    assert modi == ["live", "paper"]


# ------------------------------------------------------- attivita' e proposte
def test_lattivita_esce_sul_canale(banco):
    banco["risposte"]["safe_strategy_activity"] = RispostaFinta([RIGA_ATTIVITA])
    D.log("skip", {"reason": "stale"})
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["safe_attivita"]
    assert set(msg) - set(CB.CHIAVI_META) == set(RIGA_ATTIVITA)


def test_la_proposta_di_chiusura_nuova_esce_sul_canale(banco):
    banco["risposte"]["safe_strategy_requests:select"] = RispostaFinta([])
    banco["risposte"]["safe_strategy_requests:insert"] = RispostaFinta([RIGA_PROPOSTA])
    assert D.scrivi_proposta_di_chiusura(771, {"motivo": "target"}) == 61
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["safe_proposta"]
    assert msg["kind"] == "cashout" and msg["status"] == "proposed"


def test_la_proposta_di_chiusura_aggiornata_esce_sul_canale(banco):
    banco["risposte"]["safe_strategy_requests:select"] = RispostaFinta([RIGA_PROPOSTA])
    banco["risposte"]["safe_strategy_requests:update"] = RispostaFinta([RIGA_PROPOSTA])
    D.scrivi_proposta_di_chiusura(771, {"prezzo": 1.5})
    assert banco["canale"].inviati[0][0] == CB.TOPIC["safe_proposta"]


def test_la_proposta_di_chiusura_decaduta_esce_sul_canale(banco):
    decaduta = {**RIGA_PROPOSTA, "status": "rejected"}
    banco["risposte"]["safe_strategy_requests:select"] = RispostaFinta([RIGA_PROPOSTA])
    banco["risposte"]["safe_strategy_requests:update"] = RispostaFinta([decaduta])
    D.chiudi_proposta(771, "il mercato e' cambiato")
    assert banco["canale"].inviati[0][1]["status"] == "rejected"


def test_la_proposta_di_opportunita_esce_sul_canale(banco):
    banco["risposte"]["safe_strategy_requests:insert"] = RispostaFinta([RIGA_PROPOSTA_OPP])
    assert D.scrivi_proposta_opportunita("o1", {"sport": "calcio"}) == 62
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["safe_proposta"]
    assert msg["kind"] == "place" and msg["payload"]["opp_key"] == "o1"


def test_la_proposta_di_opportunita_aggiornata_esce_sul_canale(banco):
    banco["risposte"]["safe_strategy_requests:update"] = RispostaFinta([RIGA_PROPOSTA_OPP])
    D.scrivi_proposta_opportunita("o1", {"sport": "calcio"}, req_id=62)
    assert banco["canale"].inviati[0][0] == CB.TOPIC["safe_proposta"]


def test_la_proposta_di_opportunita_decaduta_esce_sul_canale(banco):
    decaduta = {**RIGA_PROPOSTA_OPP, "status": "rejected"}
    banco["risposte"]["safe_strategy_requests:update"] = RispostaFinta([decaduta])
    D.chiudi_proposta_opportunita(62, "sparita dal feed")
    assert banco["canale"].inviati[0][1]["status"] == "rejected"


# ------------------------------------------------------------ database registro
def test_una_scrittura_senza_rappresentazione_non_pubblica_niente(banco):
    banco["risposte"]["safe_strategy_trades"] = RispostaFinta([])
    D.update_trade(771, status="won")
    assert banco["canale"].inviati == []


# --------------------------------------------------------- interruttore SPENTO
def test_con_linterruttore_spento_non_esce_niente(banco, monkeypatch):
    monkeypatch.setattr(D, "_CANALE_ACCESO", False)
    banco["risposte"]["safe_strategy_trades"] = RispostaFinta([RIGA_CALCIO])
    banco["risposte"]["safe_strategy_activity"] = RispostaFinta([RIGA_ATTIVITA])
    banco["risposte"]["safe_strategy_requests:select"] = RispostaFinta([])
    banco["risposte"]["safe_strategy_requests:insert"] = RispostaFinta([RIGA_PROPOSTA])
    D.insert_trade(dict(RIGA_CALCIO))
    D.update_trade(771, status="won")
    D.log("skip", {})
    D.scrivi_proposta_di_chiusura(771, {})
    D.scrivi_proposta_opportunita("o1", {})
    D.chiudi_proposta_opportunita(62, "x")
    assert banco["canale"].inviati == []


def test_linterruttore_di_serie_e_spento(monkeypatch):
    monkeypatch.delenv(CB.ENV_SAFE, raising=False)
    assert CB.acceso(CB.ENV_SAFE) is False


# ------------------------------------------------- il canale non ferma il bot
def test_col_canale_morto_il_bot_lavora_identico(banco, monkeypatch):
    monkeypatch.setattr(CB, "_canale", lambda: CanaleFinto(solleva=True))
    banco["risposte"]["safe_strategy_trades"] = RispostaFinta([RIGA_CALCIO])
    assert D.insert_trade(dict(RIGA_CALCIO)) == 771
    assert CB.statistiche()["errori"] == 1


def test_il_canale_di_safe_resta_di_sola_lettura():
    import inspect

    from Betfair.safe_strategy import bot_service as S

    assert "solo_lettura=True" in inspect.getsource(S._avvia_canale)
