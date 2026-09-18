"""F3 - IL MODULO CONDIVISO DELLA PUBBLICAZIONE (18/09/2026).

Quello che questi test difendono, in ordine di importanza:

1. **Il messaggio E' la riga.** Non una sua proiezione, non un suo riassunto.
   Un consumatore deve poter mettere la riga del canale al posto della riga del
   database senza sapere da dove viene. Le uniche chiavi in piu' sono quelle
   della BUSTA, dichiarate una volta sola in ``CHIAVI_META``.
2. **Il database resta il registro.** Si pubblica DOPO la scrittura riuscita e
   solo cio' che la scrittura ha restituito: mai un messaggio per una riga che
   sul database non esiste.
3. **Pubblicare non puo' fermare il bot.** Canale giu', porta occupata,
   ``websockets`` assente, client fermo: il bot lavora identico. Le eccezioni si
   INGHIOTTONO e si CONTANO - mai il silenzio totale.
4. **Il ``mode`` e' quello della RIGA**, mai quello del servizio.
5. **Modulo puro**: nessun flumine, nessun supabase. Lo importano anche processi
   in cui flumine non deve entrare mai (l'incidente del 17/09).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from Betfair.stream import canale_bot as CB

RADICE = Path(__file__).resolve().parents[3]


class CanaleFinto:
    """Un canale con le STESSE firme di ``LocalChannel``: publish(topic, payload)."""

    def __init__(self, solleva: bool = False) -> None:
        self.inviati: list[tuple[str, object]] = []
        self.sul_filo: list[tuple[str, object]] = []
        self.solleva = bool(solleva)

    def publish(self, topic, payload):  # noqa: ANN001, ANN201
        if self.solleva:
            raise RuntimeError("canale morto")
        self.inviati.append((topic, payload))
        # cio' che il consumatore vedrebbe DAVVERO: il canale vero serializza
        # dentro publish, quindi un campo aggiunto un istante dopo non arriva.
        self.sul_filo.append((topic, json.loads(json.dumps(payload, default=str))))


class RispostaFinta:
    """La risposta di PostgREST: ``.data`` con la rappresentazione della riga."""

    def __init__(self, data) -> None:  # noqa: ANN001
        self.data = data


@pytest.fixture(autouse=True)
def _pulizia(monkeypatch):
    CB.azzera_statistiche()
    monkeypatch.setattr(CB, "_canale", lambda: None)
    yield
    CB.azzera_statistiche()


@pytest.fixture
def canale(monkeypatch):
    ch = CanaleFinto()
    monkeypatch.setattr(CB, "_canale", lambda: ch)
    return ch


# --------------------------------------------------------------- interruttore
@pytest.mark.parametrize("valore", [None, "", "  ", "0", "false", "no", "off", "spento", "2"])
def test_senza_env_scritto_linterruttore_e_spento(monkeypatch, valore):
    """Acceso SOLO se qualcuno lo scrive davvero. Vuoto, assente o qualunque
    altra scritta: spento. E' il verso giusto del guasto (difetto D2 di F1)."""
    if valore is None:
        monkeypatch.delenv("PROVA_CANALE_F3", raising=False)
    else:
        monkeypatch.setenv("PROVA_CANALE_F3", valore)
    assert CB.acceso("PROVA_CANALE_F3") is False


@pytest.mark.parametrize("valore", ["1", "true", "TRUE", "si", "Si", "yes", " yes "])
def test_con_env_scritto_linterruttore_e_acceso(monkeypatch, valore):
    monkeypatch.setenv("PROVA_CANALE_F3", valore)
    assert CB.acceso("PROVA_CANALE_F3") is True


# ------------------------------------------------------- il messaggio E' la riga
def test_il_messaggio_ha_le_stesse_chiavi_e_gli_stessi_tipi_della_riga(canale):
    riga = {"id": 7, "event_id": "36050104", "mode": "paper", "price": 2.5,
            "size": None, "meta": {"phase": "reserved"}, "status": "open"}
    assert CB.pubblica("omega_posizioni", riga) is True
    topic, msg = canale.sul_filo[0]
    assert topic == "omega_posizioni"
    assert set(msg) - set(CB.CHIAVI_META) == set(riga)
    for k, v in riga.items():
        assert type(msg[k]) is type(v), k
        assert msg[k] == v, k


def test_le_chiavi_in_piu_sono_solo_quelle_della_busta(canale):
    CB.pubblica("omega_posizioni", {"id": 1})
    _, msg = canale.sul_filo[0]
    assert set(msg) - {"id"} == set(CB.CHIAVI_META)
    assert msg[CB.CHIAVE_FONTE] == "canale"


def test_il_messaggio_non_muta_la_riga_del_database(canale):
    riga = {"id": 1, "status": "open"}
    prima = dict(riga)
    CB.pubblica("omega_posizioni", riga)
    assert riga == prima, "la riga che va sul database non si tocca"


def test_ogni_messaggio_porta_un_numero_di_sequenza_crescente(canale):
    for _ in range(3):
        CB.pubblica("omega_posizioni", {"id": 1})
    seq = [m[CB.CHIAVE_SEQ] for _, m in canale.sul_filo]
    assert seq == sorted(seq) and len(set(seq)) == 3


def test_il_numero_di_sequenza_cresce_anche_fra_topic_diversi(canale):
    CB.pubblica("omega_posizioni", {"id": 1})
    CB.pubblica("omega_attivita", {"id": 2})
    a, b = (m[CB.CHIAVE_SEQ] for _, m in canale.sul_filo)
    assert b > a


def test_ogni_messaggio_porta_listante_di_pubblicazione(canale):
    CB.pubblica("omega_posizioni", {"id": 1})
    _, msg = canale.sul_filo[0]
    ms = msg[CB.CHIAVE_PUBBLICATO_MS]
    assert isinstance(ms, int) and ms > 1_700_000_000_000


def test_il_messaggio_porta_il_mode_della_riga_non_quello_del_servizio(canale):
    """Paper e live non si sommano MAI. Il ``mode`` viaggia perche' sta nella
    riga, non perche' qualcuno lo attacca sapendo com'e' avviato il servizio."""
    CB.pubblica("safe_posizioni_calcio", {"id": 1, "mode": "paper"})
    CB.pubblica("safe_posizioni_calcio", {"id": 2, "mode": "live"})
    assert [m["mode"] for _, m in canale.sul_filo] == ["paper", "live"]


# ------------------------------------------------- il database resta il registro
def test_senza_riga_scritta_non_si_pubblica_niente(canale):
    """``update`` che non torna nessuna rappresentazione: nessun messaggio.
    Mai un messaggio sul canale per una riga che sul database non esiste."""
    assert CB.pubblica_scritte("omega_posizioni", RispostaFinta([])) == 0
    assert CB.pubblica_scritte("omega_posizioni", RispostaFinta(None)) == 0
    assert CB.pubblica_scritte("omega_posizioni", None) == 0
    assert canale.inviati == []


def test_si_pubblica_ogni_riga_che_la_scrittura_ha_restituito(canale):
    res = RispostaFinta([{"id": 1, "status": "open"}, {"id": 2, "status": "open"}])
    assert CB.pubblica_scritte("omega_posizioni", res) == 2
    assert [m["id"] for _, m in canale.sul_filo] == [1, 2]


def test_una_risposta_storta_non_solleva(canale):
    assert CB.pubblica_scritte("omega_posizioni", RispostaFinta(["non un dict"])) == 0
    assert CB.pubblica_scritte("omega_posizioni", RispostaFinta("stringa")) == 0


# ------------------------------------------------- pubblicare non ferma il bot
def test_pubblicare_non_solleva_mai_verso_il_bot(monkeypatch):
    ch = CanaleFinto(solleva=True)
    monkeypatch.setattr(CB, "_canale", lambda: ch)
    assert CB.pubblica("omega_posizioni", {"id": 1}) is False   # nessuna eccezione


def test_le_eccezioni_si_contano_non_si_perdono(monkeypatch):
    ch = CanaleFinto(solleva=True)
    monkeypatch.setattr(CB, "_canale", lambda: ch)
    CB.pubblica("omega_posizioni", {"id": 1})
    CB.pubblica("omega_posizioni", {"id": 2})
    st = CB.statistiche()
    assert st["errori"] == 2 and st["pubblicati"] == 0
    assert "canale morto" in str(st["ultimo_errore"])


def test_una_riga_non_serializzabile_non_ferma_il_bot(canale):
    class Strano:
        pass
    assert CB.pubblica("omega_posizioni", {"id": 1, "x": Strano()}) is True


def test_senza_canale_non_succede_niente():
    assert CB.pubblica("omega_posizioni", {"id": 1}) is False
    assert CB.statistiche()["errori"] == 0


def test_le_statistiche_dicono_quanti_messaggi_sono_usciti(canale):
    CB.pubblica("omega_posizioni", {"id": 1})
    assert CB.statistiche()["pubblicati"] == 1


# ------------------------------------------------------------- modulo puro (B1)
def test_canale_bot_e_un_modulo_puro():
    """Lo importano anche processi in cui flumine non deve entrare mai."""
    codice = (
        "import sys;"
        "import Betfair.stream.canale_bot;"
        "vietati=[m for m in sys.modules if m.split('.')[0] in "
        "('flumine','betfairlightweight','supabase','postgrest')];"
        "print('VIETATI=' + ','.join(sorted(vietati)))"
    )
    out = subprocess.run([sys.executable, "-c", codice], cwd=str(RADICE),
                         capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, out.stderr[-2000:]
    assert "VIETATI=\n" in out.stdout or out.stdout.strip() == "VIETATI=", out.stdout


def test_i_nomi_dei_topic_stanno_in_un_posto_solo():
    """Produttore e consumatore non possono divergere se il nome del topic
    esiste una volta sola (difetto sez.7.33 del catalogo)."""
    attesi = {
        "mike_posizioni", "mike_attivita",
        "omega_posizioni", "omega_attivita", "omega_proposta",
        "safe_posizioni_calcio", "safe_posizioni_tennis",
        "safe_attivita", "safe_proposta",
        "tennis_bot_stato", "tennis_bot_posizioni",
    }
    assert attesi <= set(CB.TOPIC.values())


def test_la_porta_dei_bot_tennis_e_47337():
    assert CB.PORTA_TENNIS_BOT == 47337


def test_il_topic_calcio_e_quello_tennis_non_sono_lo_stesso():
    assert CB.TOPIC["safe_posizioni_calcio"] != CB.TOPIC["safe_posizioni_tennis"]


def test_il_dizionario_dei_topic_non_si_puo_cambiare_per_sbaglio():
    with pytest.raises(Exception):
        CB.TOPIC["safe_posizioni_calcio"] = "altro"   # type: ignore[index]
