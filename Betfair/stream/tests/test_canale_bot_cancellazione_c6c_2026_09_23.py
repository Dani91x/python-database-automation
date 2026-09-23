"""C6(c) (23/09/2026) - LA CANCELLAZIONE DI UNA RIGA E' UN EVENTO SUL CANALE.

Checkpoint F3 (``Betfair/CHECKPOINT_AL_MS_F3_2026-09-18.md`` par.7) lasciava scritto:
"delete_trade (riserva 'pending' cancellata) non pubblica: la sparizione la vede
il poll." Qui si aggiunge SOLO la pubblicazione dell'evento di cancellazione,
stesso schema busta+riga delle altre pubblicazioni, nessun topic nuovo.

Una DELETE PostgREST torna di serie la rappresentazione (stesso ReturnMethod di
insert/update, verificato in
``.venv/Lib/site-packages/postgrest/_sync/request_builder.py:390``): la riga che
``res.data`` porta e' l'ULTIMO STATO NOTO della riga cancellata, non un
marcatore di sparizione. Senza una chiave in piu' questo messaggio sarebbe
indistinguibile da un update della stessa riga: da qui ``CHIAVE_AZIONE``.
"""
from __future__ import annotations

import pytest

from Betfair.stream import canale_bot as CB


class CanaleFinto:
    def __init__(self, solleva: bool = False) -> None:
        self.inviati: list[tuple[str, dict]] = []
        self.solleva = bool(solleva)

    def publish(self, topic, payload):  # noqa: ANN001, ANN201
        if self.solleva:
            raise RuntimeError("canale morto")
        self.inviati.append((topic, payload))


class RispostaFinta:
    def __init__(self, data) -> None:  # noqa: ANN001
        self.data = data


@pytest.fixture(autouse=True)
def _pulizia():
    CB.azzera_statistiche()
    yield
    CB.azzera_statistiche()


@pytest.fixture
def canale(monkeypatch):
    ch = CanaleFinto()
    monkeypatch.setattr(CB, "_canale", lambda: ch)
    return ch


RIGA_PENDING = {"id": 512, "event_id": "35760084", "status": "pending",
                "mode": "live", "price": 30.0, "size": 1.0}


def test_la_cancellazione_esce_sul_canale_con_lazione(canale):
    res = RispostaFinta([RIGA_PENDING])
    assert CB.pubblica_cancellazione("omega_posizioni", res) == 1
    topic, msg = canale.inviati[0]
    assert topic == "omega_posizioni"
    assert msg[CB.CHIAVE_AZIONE] == CB.AZIONE_CANCELLATA


def test_la_cancellazione_porta_ancora_la_chiave_identificativa_della_riga(canale):
    res = RispostaFinta([RIGA_PENDING])
    CB.pubblica_cancellazione("omega_posizioni", res)
    _, msg = canale.inviati[0]
    assert msg["id"] == 512


def test_lo_schema_e_lo_stesso_delle_altre_pubblicazioni_di_riga_piu_lazione(canale):
    """Messaggio = riga + CHIAVI_META + UNA chiave in piu' (CHIAVE_AZIONE)."""
    res = RispostaFinta([RIGA_PENDING])
    CB.pubblica_cancellazione("omega_posizioni", res)
    _, msg = canale.inviati[0]
    assert CB.CHIAVE_AZIONE in msg, "manca la chiave d'azione: indistinguibile da un update"
    chiavi_busta = set(CB.CHIAVI_META) | {CB.CHIAVE_AZIONE}
    assert set(msg) - chiavi_busta == set(RIGA_PENDING)
    for k, v in RIGA_PENDING.items():
        assert msg[k] == v and type(msg[k]) is type(v), k


def test_nessun_topic_nuovo_si_riusa_quello_delle_righe_vive(canale):
    res = RispostaFinta([RIGA_PENDING])
    CB.pubblica_cancellazione(CB.TOPIC["safe_posizioni_calcio"], res)
    topic, _ = canale.inviati[0]
    assert topic == CB.TOPIC["safe_posizioni_calcio"]


def test_una_delete_senza_rappresentazione_non_pubblica_niente(canale):
    assert CB.pubblica_cancellazione("omega_posizioni", RispostaFinta([])) == 0
    assert CB.pubblica_cancellazione("omega_posizioni", RispostaFinta(None)) == 0
    assert canale.inviati == []


def test_piu_righe_cancellate_escono_tutte(canale):
    res = RispostaFinta([{"id": 1}, {"id": 2}])
    assert CB.pubblica_cancellazione("omega_posizioni", res) == 2
    assert [m["id"] for _, m in canale.inviati] == [1, 2]
    assert all(m[CB.CHIAVE_AZIONE] == CB.AZIONE_CANCELLATA for _, m in canale.inviati)


def test_la_cancellazione_non_solleva_mai_col_canale_morto(monkeypatch):
    monkeypatch.setattr(CB, "_canale", lambda: CanaleFinto(solleva=True))
    res = RispostaFinta([RIGA_PENDING])
    assert CB.pubblica_cancellazione("omega_posizioni", res) == 0
    assert CB.statistiche()["errori"] == 1


# --------------------------------------------------- topic scelto dalla riga (Safe)
def _topic_per_sport(riga):
    return {
        "calcio": CB.TOPIC["safe_posizioni_calcio"],
        "tennis": CB.TOPIC["safe_posizioni_tennis"],
    }.get(str(riga.get("sport") or ""))


def test_la_cancellazione_per_riga_sceglie_il_topic_dallo_sport(canale):
    res = RispostaFinta([{"id": 9, "sport": "tennis"}])
    assert CB.pubblica_cancellazione_per(_topic_per_sport, res) == 1
    topic, msg = canale.inviati[0]
    assert topic == CB.TOPIC["safe_posizioni_tennis"]
    assert msg[CB.CHIAVE_AZIONE] == CB.AZIONE_CANCELLATA


def test_la_cancellazione_per_riga_senza_topic_non_esce(canale):
    res = RispostaFinta([{"id": 9, "sport": "basket"}])
    assert CB.pubblica_cancellazione_per(_topic_per_sport, res) == 0
    assert canale.inviati == []
