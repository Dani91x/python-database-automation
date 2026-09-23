"""23/09 - B-1 (revisore B): guardia d'avvio del runner e comandi del canale locale.

Difetto (regressione di a50c9d1): a guardia armata (ripresa A6 fallita, DB giu')
il worker della coda non girava, ma il canale 47331 accettava i comandi del
desktop: restavano nella coda in RAM (fino a 200) SENZA risposta e, al disarmo,
il primo giro del worker li eseguiva TUTTI (ordini di minuti prima, anche doppi:
il trader riprova con client_ref nuovi).

Correzione: a guardia armata la coda si drena per intero a ogni giro e ogni
comando riceve subito ``ok=False`` con il motivo; passa SOLO ``cancel`` (riduce
l'esposizione), con le regole del giro normale del worker. Nessun comando resta
in coda per dopo.

La sonda del revisore (``test_guardia_armata_lascia_i_comandi_locali_in_coda``,
verde = difetto) e' qui INVERTITA. Finti: ``LocalChannel``/``LocalRequest`` VERI
(``respond`` sostituito solo per registrare le risposte), ``db`` con le firme di
``stream/db.py``.
"""
from __future__ import annotations

import pytest

from Betfair.stream import live_order_worker as LOW
from Betfair.stream import local_channel as LC
from Betfair.stream import runner as R


class _DbGiu:
    def __init__(self):
        self.giu = True

    def cleanup_paper_mirror(self):
        if self.giu:
            raise ConnectionError("Server disconnected")
        return (0, 0)

    def fail_stale_pending_requests(self, older_than_sec=120.0):
        return 0

    def insert_alert(self, level, code, message):
        pass


def _req(msg_id, action, mode="live", **extra):
    params = {"action": action, "mode": mode, "client_ref": f"ref-{msg_id}",
              "market_id": "1.234", "selection_id": 47972}
    params.update(extra)
    return LC.LocalRequest(ws=None, msg_id=msg_id, method="order", params=params)


@pytest.fixture()
def ambiente(monkeypatch):
    ch = LC.LocalChannel(59998, "calcio")
    risposte = []
    monkeypatch.setattr(ch, "respond",
                        lambda req, ok, data=None, error=None:
                        risposte.append((req.msg_id, ok, error)))
    monkeypatch.setattr(LC, "get_channel", lambda: ch)
    worker = []
    monkeypatch.setattr(R, "live_order_worker",
                        lambda ctx, fl, session=None, strategy=None:
                        worker.append(LOW._process_local_requests(None, fl, "live", strategy)))
    finto_db = _DbGiu()
    monkeypatch.setattr(R, "db", finto_db)
    # percorso vero del worker per i cancel: modo LIVE, dispatch registrato
    eseguiti = []
    monkeypatch.setattr(LOW, "_live_order_mode", lambda: "LIVE")
    monkeypatch.setattr(LOW, "_kill_switch", lambda: False)
    monkeypatch.setattr(LOW, "_db_kill_switch", lambda: False)
    monkeypatch.setattr(LOW, "_dispatch",
                        lambda sb, fl, row, mode, strat: eseguiti.append(
                            (row["action"], row.get("bet_id"))))
    monkeypatch.setattr(LOW, "_record_local_request", lambda *a, **k: None)
    monkeypatch.setattr(LOW, "_journal_done", lambda *a, **k: None)
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: object())
    monkeypatch.setattr(LOW, "_LOCAL_SEEN", {})
    R._GUARDIA_AVVIO.azzera()
    R._GUARDIA_AVVIO.attiva = True
    R._RIPRESA_STATO["ultimo"] = 0.0
    yield {"ch": ch, "risposte": risposte, "worker": worker, "db": finto_db,
           "eseguiti": eseguiti}
    R._GUARDIA_AVVIO.azzera()
    R._RIPRESA_STATO["ultimo"] = 0.0


def test_guardia_armata_risponde_subito_e_svuota_la_coda(ambiente):
    ch = ambiente["ch"]
    for r in (_req(1, "place", side="BACK", price=2.0, size=2.0),
              _req(2, "cancel", bet_id="B-1"),
              _req(3, "cashout_event", event_id="E1")):
        ch._requests.put_nowait(r)
    R._live_order_worker_guardato({}, "FL")
    assert ambiente["worker"] == []                     # worker non eseguito
    assert ch._requests.qsize() == 0                    # nessun comando lasciato in coda
    per_id = {mid: (ok, err) for mid, ok, err in ambiente["risposte"]}
    assert set(per_id) == {1, 2, 3}                     # tutti risposti SUBITO
    assert per_id[1][0] is False and "NON eseguito" in per_id[1][1]
    assert per_id[3][0] is False and "NON eseguito" in per_id[3][1]
    # cancel: passato dal percorso normale del worker (riduce l'esposizione)
    assert per_id[2][0] is True
    assert ambiente["eseguiti"] == [("cancel", "B-1")]


def test_al_disarmo_non_parte_nessun_comando_vecchio(ambiente):
    ch = ambiente["ch"]
    ch._requests.put_nowait(_req(1, "place", side="LAY", price=3.0, size=2.0))
    ch._requests.put_nowait(_req(2, "greenup"))
    R._live_order_worker_guardato({}, "FL")
    assert ch._requests.qsize() == 0
    # minuti dopo il DB torna: la ripresa riesce, il worker gira...
    ambiente["db"].giu = False
    R._RIPRESA_STATO["ultimo"] = 0.0
    R._live_order_worker_guardato({}, "FL")
    assert len(ambiente["worker"]) == 1
    # ...ma non trova piu' nulla da eseguire: i comandi vecchi hanno avuto il rifiuto
    assert ambiente["worker"] == [0]
    assert ambiente["eseguiti"] == []


def test_coda_piena_drenata_per_intero(ambiente):
    ch = ambiente["ch"]
    for i in range(LC._MAX_QUEUE):
        ch._requests.put_nowait(_req(i, "place", side="BACK", price=2.0, size=2.0))
    R._live_order_worker_guardato({}, "FL")
    assert ch._requests.qsize() == 0
    assert len(ambiente["risposte"]) == LC._MAX_QUEUE
    assert all(ok is False for _, ok, _ in ambiente["risposte"])


def test_snapshot_in_guardia_rifiutato(ambiente):
    ch = ambiente["ch"]
    ch._requests.put_nowait(LC.LocalRequest(ws=None, msg_id=9, method="snapshot",
                                            params={"market_id": "1.234"}))
    R._live_order_worker_guardato({}, "FL")
    assert ambiente["risposte"] == [(9, False, R._MOTIVO_GUARDIA_LOCALE)]


def test_cancel_con_modo_off_rifiutato_non_eseguito(ambiente, monkeypatch):
    monkeypatch.setattr(LOW, "_live_order_mode", lambda: "OFF")
    ch = ambiente["ch"]
    ch._requests.put_nowait(_req(5, "cancel", bet_id="B-5"))
    R._live_order_worker_guardato({}, "FL")
    assert ambiente["eseguiti"] == []
    assert [(m, ok) for m, ok, _ in ambiente["risposte"]] == [(5, False)]


def test_guardia_disarmata_invariata(ambiente):
    ambiente["db"].giu = False
    R._GUARDIA_AVVIO.azzera()                          # guardia non attiva
    ch = ambiente["ch"]
    ch._requests.put_nowait(_req(1, "place", side="BACK", price=2.0, size=2.0))
    R._live_order_worker_guardato({}, "FL")
    # nessun rifiuto della guardia: il comando va al worker normale
    assert ambiente["worker"] == [1]
    assert ambiente["eseguiti"] == [("place", None)]
