"""CANTIERE N (28/09/2026) - scalper calcio: a ogni AVVIO NUOVO dell'app la riga
dell'interruttore (``scalper_service_control``) torna con le uscite MANUALI, e le
sessioni nuove dell'auto-mode (che ereditano da quella riga,
``auto_mode.params_per_sessione``) nascono manuali.

Supervisore vero (``scalper_service.giro_auto``), finto con i metodi di
``scalper_service.Db`` (``test_scalper_auto_mode_2026_09_25.DbFinto``).
File ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.stream import avvio_app as AA
from Betfair.stream.scalper import scalper_service as SVC
from Betfair.stream.tests.test_scalper_auto_mode_2026_09_25 import (
    ORA_EP, DbFinto, riga_feed, riga_servizio,
)


def test_avvio_nuovo_la_riga_dell_interruttore_torna_manuale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AA.ENV_BOOT_ID, "boot-oggi")
    st = SVC.StatoAuto()
    st.guardia.attiva = True
    db = DbFinto(riga_servizio(params={"uscite_automatiche": True, "tetto_partite": 3},
                               stats={"boot_id": "boot-ieri"}), [riga_feed("1")])
    SVC.giro_auto(db, st, [], ORA_EP)
    primo = db.nomi("set_servizio")[0][1]
    assert primo["params"] == {"uscite_automatiche": False, "tetto_partite": 3}
    assert db._servizio["params"]["uscite_automatiche"] is False


def test_stesso_avvio_la_scelta_dell_utente_resta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AA.ENV_BOOT_ID, "boot-oggi")
    st = SVC.StatoAuto()
    st.guardia.attiva = True
    db = DbFinto(riga_servizio(params={"uscite_automatiche": True},
                               stats={"boot_id": "boot-oggi"}), [])
    SVC.giro_auto(db, st, [], ORA_EP)
    assert all("params" not in c[1] for c in db.nomi("set_servizio"))
    assert db._servizio["params"]["uscite_automatiche"] is True
