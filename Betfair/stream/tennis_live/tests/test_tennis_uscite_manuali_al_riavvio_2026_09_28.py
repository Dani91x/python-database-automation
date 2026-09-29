"""CANTIERE N (28/09/2026) - bot tennis: a ogni AVVIO NUOVO dell'app l'interruttore
delle uscite (``tennis_bot_service_control.uscite_automatiche``) torna MANUALE.

Ponte vero (``tennis_bot_service.ferma_interruttori_al_nuovo_avvio``); finto con
la firma VERA di ``tennis_db.set_tennis_bot_service_state`` (compreso il nuovo
``uscite_automatiche``) e la riga VERA della tabella con la colonna della
migrazione ``tennis_uscite_manuali_2026-09-25.sql``. File ASCII-only.
"""
from __future__ import annotations

import inspect
from typing import Any, Dict, Optional

from Betfair.stream.tennis_live import tennis_bot_service as S
from Betfair.stream.tennis_live import tennis_db as TDB
from Betfair.stream.tennis_live.tests.test_r2_tennis_paper_al_nuovo_avvio_2026_09_25 import (
    IERI, OGGI, _DbTennis, _servizio,
)


class _DbTennisUscite(_DbTennis):
    """Il finto del R2 con la firma di oggi di ``set_tennis_bot_service_state``."""

    def set_tennis_bot_service_state(self, bot_key: str, *, status: Optional[str] = None,
                                     stats: Optional[Dict[str, Any]] = None,
                                     error: Optional[str] = None, heartbeat: bool = False,
                                     stopped: bool = False, mode: Optional[str] = None,
                                     uscite_automatiche: Optional[bool] = None) -> bool:
        ok = super().set_tennis_bot_service_state(bot_key, status=status, stats=stats,
                                                  error=error, heartbeat=heartbeat,
                                                  stopped=stopped, mode=mode)
        self.servizio_scritto[-1]["uscite_automatiche"] = uscite_automatiche
        for r in self.servizi or []:
            if r["bot_key"] == bot_key and uscite_automatiche is not None:
                r["uscite_automatiche"] = uscite_automatiche
        return ok


def _riga(status: str = "running", mode: str = "paper", boot: str = IERI,
          uscite: bool = True, bot: str = "tennis_swing") -> Dict[str, Any]:
    r = _servizio(status=status, mode=mode, boot=boot, bot=bot)
    r["uscite_automatiche"] = uscite
    return r


def test_la_firma_del_finto_e_quella_vera():
    vera = inspect.signature(TDB.set_tennis_bot_service_state).parameters
    assert "uscite_automatiche" in vera
    finta = inspect.signature(_DbTennisUscite.set_tennis_bot_service_state).parameters
    assert [p for p in vera] == [p for p in finta if p != "self"]


def test_avvio_nuovo_acceso_in_automatico_torna_manuale():
    db = _DbTennisUscite(servizi=[_riga(status="running", uscite=True)])
    S.ferma_interruttori_al_nuovo_avvio(boot_id=OGGI, db=db)
    assert db.servizio_scritto[0]["uscite_automatiche"] is False
    assert db.servizi[0]["uscite_automatiche"] is False


def test_avvio_nuovo_fermo_in_prova_ma_automatico_torna_manuale_senza_cartello():
    db = _DbTennisUscite(servizi=[_riga(status="stopped", mode="paper", uscite=True)])
    S.ferma_interruttori_al_nuovo_avvio(boot_id=OGGI, db=db)
    w = db.servizio_scritto[0]
    assert w["uscite_automatiche"] is False
    assert "fermato_all_avvio_at" not in (w["stats"] or {})


def test_gia_manuale_e_fermo_in_prova_non_si_scrive():
    db = _DbTennisUscite(servizi=[_riga(status="stopped", mode="paper", uscite=False)])
    S.ferma_interruttori_al_nuovo_avvio(boot_id=OGGI, db=db)
    assert db.servizio_scritto == []


def test_stesso_avvio_la_scelta_dell_utente_resta():
    db = _DbTennisUscite(servizi=[_riga(status="running", boot=OGGI, uscite=True)])
    S.ferma_interruttori_al_nuovo_avvio(boot_id=OGGI, db=db)
    assert db.servizio_scritto == [] and db.servizi[0]["uscite_automatiche"] is True


def test_senza_colonna_non_si_manda_la_chiave():
    """Migrazione non applicata: la riga non ha la colonna, la chiamata resta
    quella di prima (nessuna colonna inesistente mandata a PostgREST)."""
    db = _DbTennisUscite(servizi=[_servizio(status="running", mode="live")])
    S.ferma_interruttori_al_nuovo_avvio(boot_id=OGGI, db=db)
    assert db.servizio_scritto[0]["uscite_automatiche"] is None


def test_tennis_db_scrive_la_colonna(monkeypatch):
    """Cosa scrive DAVVERO ``tennis_db`` (client supabase finto)."""
    scritto: Dict[str, Any] = {}

    class _Q:
        def update(self, campi):
            scritto.update(campi)
            return self

        def eq(self, *_a):
            return self

        def execute(self):
            return type("R", (), {"data": []})()

    class _Sb:
        def table(self, _t):
            return _Q()

    monkeypatch.setattr(TDB, "get_tennis_client", lambda: _Sb())
    monkeypatch.setattr(TDB, "_CANALE_ACCESO", False, raising=False)
    assert TDB.set_tennis_bot_service_state("tennis_pro", uscite_automatiche=False) is True
    assert scritto["uscite_automatiche"] is False
    scritto.clear()
    TDB.set_tennis_bot_service_state("tennis_pro", status="stopped")
    assert "uscite_automatiche" not in scritto
