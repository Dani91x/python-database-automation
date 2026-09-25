"""R2 (25/09 sera) - a un avvio NUOVO dell'app i 4 bot tennis tornano in PAPER.

Decisione dell'utente: «I bot a ogni riavvio (TUTTI) devono restare spenti, li
devo avviare io in live o paper» e «NO, non devono mai partire in live senza mio
ordine». Omega, Mike e Safe lo fanno gia' (``avvio_app.ferma_al_nuovo_avvio``:
``status='stopped'`` E ``mode='paper'``). I bot tennis no: al nuovo avvio
tornavano ``stopped`` ma la MODALITA' restava quella di ieri:

  * interruttore di servizio (``tennis_bot_service_control``): ``mode='live'``
    restava ``'live'``: il prossimo «avvia» dalla Control Room ripartiva live;
  * righe per partita (``tennis_bot_control``): ``mode='live'`` e
    ``dry_run=false`` restavano sulla riga fermata.

Adesso: avvio NUOVO (``APP_BOOT_ID`` diverso da quello timbrato sulla riga) ->
servizio ``stopped`` + ``mode='paper'``; righe per partita attive ``stopped`` +
``mode='paper'`` + ``dry_run=true``. Stesso ``APP_BOOT_ID`` (riavvio dal
watchdog): nulla cambia.

Finti: firme e chiavi di ``tennis_db`` (``set_tennis_bot_status``,
``set_tennis_bot_service_state``, ``list_tennis_bot_controls``,
``list_tennis_bot_services``) e le righe VERE delle due tabelle. Le due funzioni
di ``tennis_db`` sono provate anche con un client supabase finto
(``table().update().eq().execute()``) per vedere cosa scrivono davvero.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream.tennis_live import tennis_bot_service as S
from Betfair.stream.tennis_live import tennis_db as TDB

EV = "34999001"
OGGI, IERI = "avvio-di-oggi", "avvio-di-ieri"


class _DbTennis:
    """Le funzioni di ``tennis_db`` che il fermo d'avvio usa, con le firme vere."""

    def __init__(self, servizi: Optional[List[Dict[str, Any]]] = None,
                 controls: Optional[List[Dict[str, Any]]] = None) -> None:
        self.servizi = servizi
        self.controls = list(controls or [])
        self.stati: List[Dict[str, Any]] = []
        self.servizio_scritto: List[Dict[str, Any]] = []
        self.attivita: List[tuple] = []
        self._servizio_assente_detto = False

    # --- interruttori di servizio -----------------------------------------
    def list_tennis_bot_services(self) -> Optional[List[Dict[str, Any]]]:
        return None if self.servizi is None else [dict(r) for r in self.servizi]

    def set_tennis_bot_service_state(self, bot_key: str, *, status: Optional[str] = None,
                                     stats: Optional[Dict[str, Any]] = None,
                                     error: Optional[str] = None, heartbeat: bool = False,
                                     stopped: bool = False,
                                     mode: Optional[str] = None) -> bool:
        self.servizio_scritto.append({"bot_key": bot_key, "status": status, "stats": stats,
                                      "error": error, "stopped": stopped, "mode": mode})
        for r in self.servizi or []:
            if r["bot_key"] == bot_key:
                if status is not None:
                    r["status"] = status
                if mode is not None:
                    r["mode"] = mode
        return True

    # --- righe per partita -------------------------------------------------
    def list_tennis_bot_controls(self, event_id: Optional[str] = None,
                                 statuses: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.controls
                if statuses is None or r.get("status") in statuses]

    def set_tennis_bot_status(self, event_id: str, bot_key: str, status: str, *,
                              error: Optional[str] = None,
                              stats: Optional[Dict[str, Any]] = None,
                              heartbeat: bool = False, started: bool = False,
                              stopped: bool = False, mode: Optional[str] = None,
                              dry_run: Optional[bool] = None) -> None:
        self.stati.append({"event_id": event_id, "bot_key": bot_key, "status": status,
                           "mode": mode, "dry_run": dry_run, "stopped": stopped})
        for r in self.controls:
            if r["event_id"] == event_id and r["bot_key"] == bot_key:
                r["status"] = status
                if mode is not None:
                    r["mode"] = mode
                if dry_run is not None:
                    r["dry_run"] = dry_run

    def write_tennis_bot_activity(self, event_id: str, bot_key: str, kind: str,
                                  payload: Dict[str, Any]) -> None:
        self.attivita.append((event_id, bot_key, kind, dict(payload)))


def _servizio(status: str = "running", mode: str = "live", boot: str = IERI,
              bot: str = "tennis_flb") -> Dict[str, Any]:
    """La riga VERA di ``tennis_bot_service_control``."""
    return {"bot_key": bot, "status": status, "mode": mode, "stake": 3, "params": {},
            "stats": {"boot_id": boot}, "error": None, "started_at": None,
            "stopped_at": None, "heartbeat_at": None, "updated_at": None}


def _control(status: str = "running", mode: str = "live", dry_run: bool = False,
             boot: str = IERI, bot: str = "tennis_flb") -> Dict[str, Any]:
    """La riga VERA di ``tennis_bot_control`` (migrazione tennis_bot_control_mode)."""
    return {"event_id": EV, "bot_key": bot, "status": status, "mode": mode,
            "dry_run": dry_run, "stake": 2, "params": {"soglia": 2},
            "stats": {"boot_id": boot, "entries": 3}, "error": None,
            "heartbeat_at": None, "started_at": None, "stopped_at": None}


# ===========================================================================
# interruttori di servizio
# ===========================================================================
@pytest.mark.parametrize("status", ["running", "stopping"])
def test_avvio_nuovo_interruttore_live_torna_stopped_e_paper(status):
    db = _DbTennis(servizi=[_servizio(status=status, mode="live")])
    assert S.ferma_interruttori_al_nuovo_avvio(boot_id=OGGI, db=db) == ["tennis_flb"]
    w = db.servizio_scritto[0]
    assert w["status"] == "stopped" and w["stopped"] is True
    assert w["mode"] == "paper", "mai un bot tennis che riparte live senza ordine dell'utente"
    assert w["stats"]["boot_id"] == OGGI and w["stats"]["fermato_all_avvio_at"]
    assert db.servizi[0]["mode"] == "paper"
    assert S.ESITO_ULTIMO_FERMO_INTERRUTTORI["riuscito"] is True


def test_avvio_nuovo_interruttore_fermo_ma_live_torna_paper():
    """Fermo gia' da ieri ma con ``mode='live'``: il prossimo «avvia» sarebbe
    partito live. Si riporta a paper (lo stato resta 'stopped')."""
    db = _DbTennis(servizi=[_servizio(status="stopped", mode="live")])
    assert S.ferma_interruttori_al_nuovo_avvio(boot_id=OGGI, db=db) == ["tennis_flb"]
    w = db.servizio_scritto[0]
    assert w["mode"] == "paper" and w["status"] == "stopped"


def test_avvio_nuovo_interruttore_fermo_in_paper_non_si_tocca():
    db = _DbTennis(servizi=[_servizio(status="stopped", mode="paper")])
    assert S.ferma_interruttori_al_nuovo_avvio(boot_id=OGGI, db=db) == []
    assert db.servizio_scritto == []


def test_stesso_avvio_interruttore_live_intatto():
    """Riavvio dal watchdog (stesso APP_BOOT_ID): il bot lo ha acceso l'utente in
    QUESTO avvio, live compreso. Non si tocca niente."""
    db = _DbTennis(servizi=[_servizio(status="running", mode="live", boot=OGGI)])
    assert S.ferma_interruttori_al_nuovo_avvio(boot_id=OGGI, db=db) == []
    assert db.servizio_scritto == []
    assert db.servizi[0]["mode"] == "live" and db.servizi[0]["status"] == "running"


def test_avvio_nuovo_tutti_e_quattro_i_bot():
    bots = list(S._BOT_KEYS)
    assert len(bots) == 4
    db = _DbTennis(servizi=[_servizio(bot=b, mode="live") for b in bots])
    assert sorted(S.ferma_interruttori_al_nuovo_avvio(boot_id=OGGI, db=db)) == sorted(bots)
    assert {w["mode"] for w in db.servizio_scritto} == {"paper"}


# ===========================================================================
# righe per partita
# ===========================================================================
@pytest.mark.parametrize("status", ["requested", "arming", "armed", "running"])
def test_avvio_nuovo_riga_partita_torna_stopped_paper_dry_run(status):
    assert status in S._ACTIVE_STATUSES
    db = _DbTennis(controls=[_control(status=status, mode="live", dry_run=False)])
    fermate = S.ferma_bot_al_nuovo_avvio(boot_id=OGGI, db=db)
    assert len(fermate) == 1
    w = db.stati[0]
    assert w["status"] == "stopped"
    assert w["mode"] == "paper" and w["dry_run"] is True
    r = db.controls[0]
    assert (r["status"], r["mode"], r["dry_run"]) == ("stopped", "paper", True)
    # i parametri e lo stake della riga non si toccano (strategia intoccabile)
    assert r["params"] == {"soglia": 2} and r["stake"] == 2
    att = db.attivita[0][3]
    assert att["mode_precedente"] == "live" and att["dry_run_precedente"] is False


def test_stesso_avvio_riga_partita_live_intatta():
    db = _DbTennis(controls=[_control(status="running", mode="live", dry_run=False, boot=OGGI)])
    assert S.ferma_bot_al_nuovo_avvio(boot_id=OGGI, db=db) == []
    assert db.stati == []
    r = db.controls[0]
    assert (r["status"], r["mode"], r["dry_run"]) == ("running", "live", False)


# ===========================================================================
# tennis_db: cosa scrive DAVVERO (client supabase finto)
# ===========================================================================
class _SbFinto:
    """``sb.table(t).update(campi).eq(c, v)...execute()`` come il client vero.
    ``rifiuta_colonna``: la colonna che la tabella NON ha (migrazione non
    applicata): PostgREST risponde PGRST204."""

    def __init__(self, rifiuta_colonna: Optional[str] = None) -> None:
        self.rifiuta_colonna = rifiuta_colonna
        self.update: List[tuple] = []

    def table(self, nome: str) -> Any:
        sb = self

        class _Q:
            def __init__(self) -> None:
                self.campi: Dict[str, Any] = {}

            def update(self, campi):
                self.campi = dict(campi)
                return self

            def eq(self, *_a):
                return self

            def execute(self):
                col = sb.rifiuta_colonna
                if col and col in self.campi:
                    raise RuntimeError(
                        "{'code': 'PGRST204', 'message': \"Could not find the '%s' column "
                        "of '%s' in the schema cache\"}" % (col, nome))
                sb.update.append((nome, self.campi))
                return SimpleNamespace(data=[{**self.campi}])
        return _Q()


@pytest.fixture
def sb(monkeypatch):
    def _crea(rifiuta_colonna=None):
        finto = _SbFinto(rifiuta_colonna)
        monkeypatch.setattr(TDB, "get_tennis_client", lambda: finto)
        monkeypatch.setattr(TDB, "_CANALE_ACCESO", False)
        return finto
    return _crea


def test_tennis_db_riga_partita_scrive_mode_e_dry_run(sb):
    finto = sb()
    TDB.set_tennis_bot_status(EV, "tennis_flb", "stopped", stopped=True,
                              mode="paper", dry_run=True)
    nome, campi = finto.update[0]
    assert nome == "tennis_bot_control"
    assert campi["status"] == "stopped" and campi["mode"] == "paper"
    assert campi["dry_run"] is True and campi["stopped_at"]


def test_tennis_db_riga_partita_senza_colonna_mode_scrive_il_resto(sb):
    """Migrazione ``tennis_bot_control_mode_2026-09-24.sql`` non applicata: la
    riga non ha ``mode`` (il runner la legge PAPER). Lo stop e ``dry_run`` si
    scrivono lo stesso, senza la colonna mancante."""
    finto = sb(rifiuta_colonna="mode")
    TDB.set_tennis_bot_status(EV, "tennis_flb", "stopped", stopped=True,
                              mode="paper", dry_run=True)
    nome, campi = finto.update[0]
    assert "mode" not in campi
    assert campi["status"] == "stopped" and campi["dry_run"] is True


def test_tennis_db_riga_partita_senza_mode_e_dry_run_invariata(sb):
    """Chi non passa ``mode``/``dry_run`` (tutti i chiamanti di prima) scrive
    esattamente quello che scriveva."""
    finto = sb()
    TDB.set_tennis_bot_status(EV, "tennis_flb", "running", heartbeat=True)
    _nome, campi = finto.update[0]
    assert "mode" not in campi and "dry_run" not in campi


def test_tennis_db_interruttore_scrive_mode(sb):
    finto = sb()
    assert TDB.set_tennis_bot_service_state("tennis_flb", status="stopped", stopped=True,
                                            mode="paper") is True
    nome, campi = finto.update[0]
    assert nome == TDB._SERVICE_TABLE
    assert campi["status"] == "stopped" and campi["mode"] == "paper"
    finto2 = sb()
    TDB.set_tennis_bot_service_state("tennis_flb", heartbeat=True)
    assert "mode" not in finto2.update[0][1]
