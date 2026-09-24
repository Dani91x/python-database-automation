"""IL CANALE LOCALE È UN'ACCELERAZIONE, MAI L'UNICA FONTE (14/09/2026).

Mike spinge quote, P&L e stato sull'app desktop via WebSocket su 127.0.0.1,
invece di farli passare dal disco. La regola che questi test difendono è una
sola, e vale più della velocità:

    tutto ciò che finisce sul socket finisce COMUNQUE sul database.

Se il socket cade, la pagina torna a leggere da Postgres e non perde nessun
numero: al massimo lo vede con qualche secondo di ritardo. Un P&L che sparisce
perché è caduto un WebSocket sarebbe peggio di un P&L vecchio di due secondi.

E il canale non deve MAI poter fermare il bot: pubblicare è best-effort, e un
errore nel trasporto non può propagarsi al ciclo che gestisce i soldi.
"""
from __future__ import annotations

import pytest

from Betfair.mike import service as S


@pytest.fixture
def canale_finto(monkeypatch):
    """Cattura ciò che viene pubblicato, senza aprire nessuna porta."""
    inviati: list[tuple[str, object]] = []

    def _publish(topic, payload):
        inviati.append((topic, payload))

    monkeypatch.setattr(S._lc, "publish", _publish)
    return inviati


# ---------------------------------------------------------------------------
# cosa finisce sullo schermo
# ---------------------------------------------------------------------------
def test_la_scheda_della_partita_viene_pubblicata(canale_finto):
    S._pubblica_evento({"event_id": "E1", "state": "HOLD", "live": {"inplay": True}})
    assert len(canale_finto) == 1
    topic, payload = canale_finto[0]
    assert topic == "mike_event"
    assert payload["event_id"] == "E1" and payload["state"] == "HOLD"


def test_i_campi_pesanti_e_fermi_non_viaggiano(canale_finto):
    """Il dossier è il modello pre-partita e i markets sono gli identificativi
    dei mercati: non cambiano durante la partita e la pagina li ha già presi dal
    database. Mandarli a ogni giro gonfierebbe il messaggio per niente."""
    S._pubblica_evento({
        "event_id": "E1", "state": "HOLD", "live": {"x": 1},
        "dossier": {"peso": "molto"}, "markets": {"OU35": {}}, "ctx": {"roba": 1},
    })
    payload = canale_finto[0][1]
    for k in ("dossier", "markets", "ctx"):
        assert k not in payload, k
    assert payload["live"] == {"x": 1}, "il VIVO viaggia sempre"


def test_i_numeri_di_testata_vengono_pubblicati(canale_finto):
    S._pubblica_stato({"mode": "paper"}, {"realized_total": 12.5},
                      {"open_liability": 30.0}, 1_700_000_000.0)
    topic, payload = canale_finto[0]
    assert topic == "mike_stato"
    assert payload["control"]["mode"] == "paper"
    assert payload["aggregates"]["realized_total"] == 12.5
    assert payload["stats"]["open_liability"] == 30.0
    assert payload["published_ts"] == 1_700_000_000.0


# ---------------------------------------------------------------------------
# il canale non può fare danni
# ---------------------------------------------------------------------------
def test_un_errore_del_canale_non_ferma_il_bot(monkeypatch):
    """MONEY-CRITICAL: mostrare non deve mai poter fermare chi gestisce i soldi."""
    def _esplode(topic, payload):
        raise RuntimeError("socket morto")

    monkeypatch.setattr(S._lc, "publish", _esplode)
    S._pubblica_evento({"event_id": "E1"})      # non deve sollevare
    S._pubblica_stato({}, {}, {}, 0.0)          # nemmeno questo


def test_senza_app_collegata_non_succede_niente():
    """``LocalChannel.publish`` è già un no-op senza client: a canale spento
    (nessuno ha chiamato start_channel) la pubblicazione non fa nulla e non
    solleva. È ciò che rende questa aggiunta gratuita quando non serve."""
    from Betfair.stream import local_channel as lc

    assert lc.get_channel() is None, "presupposto: nessun canale in questo processo"
    lc.publish("qualsiasi", {"a": 1})           # non deve sollevare


def test_avvio_canale_non_solleva_mai(monkeypatch):
    def _ko(*_a, **_k):
        raise OSError("porta occupata")

    monkeypatch.setattr(S._lc, "start_channel", _ko)
    S._avvia_canale()                            # non deve sollevare


def test_avvio_canale_senza_porta_libera_lo_dichiara(monkeypatch, caplog):
    monkeypatch.setattr(S._lc, "start_channel", lambda *a, **k: None)
    with caplog.at_level("WARNING"):
        S._avvia_canale()
    assert any("canale locale NON attivo" in r.getMessage() for r in caplog.records)


def test_la_porta_si_puo_cambiare_da_env(monkeypatch):
    visti: list[tuple] = []
    monkeypatch.setenv("MIKE_LOCAL_WS_PORT", "47999")
    monkeypatch.setattr(S._lc, "start_channel",
                        lambda p, s, **k: visti.append((p, s, k)) or object())
    S._avvia_canale()
    assert visti[0][0] == 47999 and visti[0][1] == "mike"


def test_env_vuota_usa_il_default(monkeypatch):
    """Regola del progetto: un default da env si prende con ``.strip() or``,
    MAI con ``??``/``or None`` — una variabile impostata a stringa vuota non
    deve diventare una porta 0."""
    visti: list[tuple] = []
    monkeypatch.setenv("MIKE_LOCAL_WS_PORT", "   ")
    monkeypatch.setattr(S._lc, "start_channel",
                        lambda p, s, **k: visti.append((p, s, k)) or object())
    S._avvia_canale()
    assert visti[0][0] == S._PORTA_CANALE


def test_porta_non_numerica_usa_il_default(monkeypatch):
    visti: list[tuple] = []
    monkeypatch.setenv("MIKE_LOCAL_WS_PORT", "quarantasette")
    monkeypatch.setattr(S._lc, "start_channel",
                        lambda p, s, **k: visti.append((p, s, k)) or object())
    S._avvia_canale()
    assert visti[0][0] == S._PORTA_CANALE


# ---------------------------------------------------------------------------
# il canale dei bot MOSTRA, non comanda
# ---------------------------------------------------------------------------
def test_il_canale_di_mike_e_di_sola_lettura(monkeypatch):
    """Quello del runner esegue ordini VERI. Tenere separati chi comanda e chi
    mostra vuol dire che aggiungere uno schermo non aggiunge mai una via per
    mandare soldi."""
    visti: list[dict] = []
    monkeypatch.setattr(S._lc, "start_channel",
                        lambda p, s, **k: visti.append(k) or object())
    S._avvia_canale()
    assert visti[0].get("solo_lettura") is True


def test_un_canale_di_sola_lettura_rifiuta_i_comandi():
    from Betfair.stream.local_channel import LocalChannel

    ch = LocalChannel(47999, "mike", solo_lettura=True)
    risposte: list[dict] = []
    ch._send = lambda ws, payload: risposte.append(payload)   # type: ignore[assignment]
    ch._on_message(object(), '{"id": 1, "m": "order", "p": {"size": 10}}')
    assert risposte and risposte[0]["ok"] is False
    assert "sola lettura" in risposte[0]["e"]
    assert ch._requests.qsize() == 0, "il comando non deve nemmeno entrare in coda"


def test_il_canale_del_runner_continua_ad_accettare_i_comandi():
    """Non-regressione: il canale del runner (47331) deve restare com'era."""
    from Betfair.stream.local_channel import LocalChannel

    ch = LocalChannel(47331, "calcio")
    ch._send = lambda ws, payload: None                        # type: ignore[assignment]
    # C1 (24/09): il canale del runner accetta i comandi SOLO da una connessione
    # che si e' presentata col token di sessione (qui: gia' autorizzata).
    ws = object()
    ch._autorizzati.add(ws)
    ch._on_message(ws, '{"id": 1, "m": "order", "p": {"size": 10}}')
    assert ch._requests.qsize() == 1
