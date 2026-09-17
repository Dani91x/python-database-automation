# -*- coding: utf-8 -*-
"""IL PONTE fra l'INTERRUTTORE per bot e l'ARMATURA per evento.

Il reperto (17/09 sera): la Control Room legge e scrive
`tennis_bot_service_control` — una riga per `bot_key`, con `status`, `mode`,
`stake`, `params` — ma NESSUN codice Python la guardava. Il runner arma per
(evento, bot) su `tennis_bot_control`. Senza ponte le quattro righe restavano
«stato non letto» e i pulsanti della UI non facevano niente.

Qui si collauda la traduzione. I finti hanno le IDENTICHE chiavi della tabella e
delle RPC (`bot_key`, `status`, `mode`, `stake`, `params`, `stats`): un finto che
parlasse un'altra lingua certificherebbe il difetto 27 del catalogo.

Ogni regola ha il suo contrario: una regola che non sa dire di no non e' una
regola.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream.tennis_live import tennis_bot_service as S


class _DbFinto:
    """Parla come `tennis_db`: stesse firme, stessi nomi di chiave, stessi tipi
    di ritorno (`list_tennis_bot_services` torna `None` quando NON ha letto)."""

    def __init__(self, servizi: Optional[List[Dict[str, Any]]],
                 controls: Optional[List[Dict[str, Any]]] = None) -> None:
        self._servizi = servizi
        self._controls = list(controls or [])
        self.armati: List[Dict[str, Any]] = []
        self.stati: List[tuple] = []
        self.servizio_scritto: List[Dict[str, Any]] = []

    def list_tennis_bot_services(self):
        return self._servizi

    def list_tennis_bot_controls(self, event_id=None, statuses=None):
        return [dict(r) for r in self._controls]

    def upsert_tennis_bot_control(self, row):
        self.armati.append(dict(row))

    def set_tennis_bot_status(self, event_id, bot_key, status, **kw):
        self.stati.append((event_id, bot_key, status))

    def set_tennis_bot_service_state(self, bot_key, **kw):
        self.servizio_scritto.append({"bot_key": bot_key, **kw})
        return True


def _riga(bot="tennis_flb", status="running", mode="paper", stake=3,
          params=None, stats=None):
    """La riga VERA di `tennis_bot_service_control`, chiave per chiave."""
    return {"bot_key": bot, "status": status, "mode": mode, "stake": stake,
            "params": params if params is not None else {},
            "stats": stats, "error": None, "started_at": None,
            "stopped_at": None, "heartbeat_at": None, "updated_at": None}


@pytest.fixture
def eventi(monkeypatch):
    monkeypatch.setattr(S, "_followed_event_ids", lambda: {"35794049", "35790089"})


# ===========================================================================
# 1. la lettura: cosa il bot DEVE fare
# ===========================================================================
def test_interruttori_non_letti_non_sono_bot_fermi():
    """LA REGOLA PIU' IMPORTANTE: un DB muto (o la migrazione non applicata) NON
    vuol dire «tutti fermi». Dedurlo disarmerebbe bot vivi."""
    assert S.stato_desiderato(None) is None


def test_running_vuol_dire_desiderato_con_la_sua_modalita():
    d = S.stato_desiderato([_riga(status="running", mode="live", stake=7)])
    assert d["tennis_flb"]["acceso"] is True
    assert d["tennis_flb"]["mode"] == "live"
    assert d["tennis_flb"]["stake"] == 7


@pytest.mark.parametrize("status", ["stopped", "stopping", "error", "", None])
def test_tutto_cio_che_non_e_running_e_fermo(status):
    d = S.stato_desiderato([_riga(status=status)])
    assert d["tennis_flb"]["acceso"] is False


@pytest.mark.parametrize("mode", [None, "", "LIVE ", "paper", "boh"])
def test_la_modalita_non_si_eredita_MAI(mode):
    """Ai soldi veri si arriva solo SCRIVENDOLO: una modalita' assente, vuota o
    incomprensibile vale `paper`. Solo un `live` esplicito e' live."""
    d = S.stato_desiderato([_riga(mode=mode)])
    atteso = "live" if str(mode or "").strip().lower() == "live" else "paper"
    assert d["tennis_flb"]["mode"] == atteso


def test_un_bot_key_sconosciuto_viene_ignorato():
    """La whitelist e' quella del `CHECK` della tabella: una riga storta non
    puo' far armare un bot che non esiste."""
    assert S.stato_desiderato([_riga(bot="tennis_inventato")]) == {}


# ===========================================================================
# 2. il giro: dall'interruttore all'armatura per evento
# ===========================================================================
def test_acceso_arma_su_OGNI_evento_seguito(eventi):
    db = _DbFinto([_riga(status="running", mode="paper", stake=5,
                         params={"lay_max": 1.05})])
    esito = S.riconcilia_interruttori(db)
    assert esito["letto"] is True and esito["armati"] == 2
    assert {r["event_id"] for r in db.armati} == {"35794049", "35790089"}
    r = db.armati[0]
    assert r["bot_key"] == "tennis_flb" and r["status"] == "requested"
    assert r["stake"] == 5 and r["params"] == {"lay_max": 1.05}


def test_in_PAPER_il_bot_non_nasce_in_dry_run(eventi):
    """In paper gli ordini sono simulati per costruzione: `dry_run` falso, cosi'
    passano dal blotter e si vedono sul ladder come dal vivo."""
    db = _DbFinto([_riga(status="running", mode="paper")])
    S.riconcilia_interruttori(db)
    assert db.armati[0]["dry_run"] is False


def test_in_LIVE_il_bot_nasce_in_dry_run(eventi):
    """Prudenza sui soldi veri: in LIVE il `dry_run` va tolto a mano, come fa
    gia' `_instantiate_bot`."""
    db = _DbFinto([_riga(status="running", mode="live")])
    S.riconcilia_interruttori(db)
    assert db.armati[0]["dry_run"] is True


def test_non_si_riarma_un_evento_gia_attivo(eventi):
    """Idempotenza: il ponte gira ogni 15 s e non deve ri-chiedere cio' che c'e'
    gia' (un riarmo dentro la finestra di disarm e' un difetto noto)."""
    db = _DbFinto([_riga(status="running")],
                  controls=[{"event_id": "35794049", "bot_key": "tennis_flb",
                             "status": "running"}])
    esito = S.riconcilia_interruttori(db)
    assert esito["armati"] == 1
    assert db.armati[0]["event_id"] == "35790089"


def test_spento_porta_a_stopping_non_a_stopped(eventi):
    """`stopped` lo scrive il RUNNER a posizione flat verificata: scriverlo qui
    sarebbe uno stato bugiardo. E lo stop ferma le APERTURE, non le uscite."""
    db = _DbFinto([_riga(status="stopped")],
                  controls=[{"event_id": "35794049", "bot_key": "tennis_flb",
                             "status": "running"}])
    esito = S.riconcilia_interruttori(db)
    assert esito["fermati"] == 1
    assert db.stati == [("35794049", "tennis_flb", "stopping")]
    assert db.armati == [], "un bot spento non arma niente"


def test_interruttori_non_letti_non_toccano_niente(eventi):
    """LA FALSIFICAZIONE: con il DB muto non si arma e non si disarma nulla."""
    db = _DbFinto(None, controls=[{"event_id": "35794049",
                                   "bot_key": "tennis_flb", "status": "running"}])
    esito = S.riconcilia_interruttori(db)
    assert esito["letto"] is False
    assert db.armati == [] and db.stati == [] and db.servizio_scritto == []


# ===========================================================================
# 3. il battito e le `stats` che la UI legge
# ===========================================================================
def test_il_battito_porta_le_chiavi_che_il_frontend_legge(eventi):
    """I NOMI sono quelli di `useControlRoom.ts`: riscriverli con altre parole
    vorrebbe dire due verita' diverse (difetto 33 del catalogo)."""
    db = _DbFinto([_riga(status="running")])
    S.riconcilia_interruttori(db)
    assert len(db.servizio_scritto) == 1
    w = db.servizio_scritto[0]
    assert w["heartbeat"] is True
    st = w["stats"]
    assert st["cadenza_battito_s"] == S.CADENZA_BATTITO_S
    assert st["stop_ferma_solo_aperture"] is True
    assert st["partite_esposte"] == 2
    assert st["motivo_blocco"] is None


def test_acceso_senza_eventi_DICE_perche_non_sta_facendo_niente(monkeypatch):
    """Un bot acceso che non opera deve spiegarsi: il silenzio e' il difetto."""
    monkeypatch.setattr(S, "_followed_event_ids", lambda: set())
    db = _DbFinto([_riga(status="running")])
    S.riconcilia_interruttori(db)
    motivo = db.servizio_scritto[0]["stats"]["motivo_blocco"]
    assert motivo and "nessun evento" in motivo


def test_la_cadenza_la_dichiara_chi_batte():
    """La Control Room giudica la freschezza del battito con QUESTO numero: se
    fosse una costante scritta nella pagina, allargare il ciclo lato servizio
    renderebbe «morto» un bot vivissimo (review 15/09)."""
    assert S.CADENZA_BATTITO_S == S.ENSURE_POLL_SEC


# ===========================================================================
# 4. la guardia d'avvio sugli INTERRUTTORI
# ===========================================================================
def test_al_nuovo_avvio_un_interruttore_acceso_torna_stopped(monkeypatch):
    """Regola di `avvio_app.py`: alla riapertura dell'app nessun bot opera. La
    riga e' persistita, quindi senza questo un `running` di ieri sera farebbe
    ripartire il bot da solo."""
    monkeypatch.setenv("APP_BOOT_ID", "avvio-NUOVO")
    db = _DbFinto([_riga(status="running", stats={"boot_id": "avvio-VECCHIO"})])
    fermati = S.ferma_interruttori_al_nuovo_avvio(db=db)
    assert fermati == ["tennis_flb"]
    w = db.servizio_scritto[0]
    assert w["status"] == "stopped" and w["stopped"] is True
    # il frontend mostra questo campo per spiegare all'utente perche' e' fermo
    assert w["stats"]["fermato_all_avvio_at"]


def test_un_riavvio_dal_watchdog_NON_tocca_niente(monkeypatch):
    """LA FALSIFICAZIONE: stesso `APP_BOOT_ID` = non e' un avvio nuovo. Fermare
    qui spegnerebbe un bot che l'utente ha acceso un minuto fa."""
    monkeypatch.setenv("APP_BOOT_ID", "stesso-avvio")
    db = _DbFinto([_riga(status="running", stats={"boot_id": "stesso-avvio"})])
    assert S.ferma_interruttori_al_nuovo_avvio(db=db) == []
    assert db.servizio_scritto == []


def test_un_interruttore_gia_fermo_non_si_tocca(monkeypatch):
    monkeypatch.setenv("APP_BOOT_ID", "avvio-NUOVO")
    db = _DbFinto([_riga(status="stopped", stats={"boot_id": "avvio-VECCHIO"})])
    assert S.ferma_interruttori_al_nuovo_avvio(db=db) == []


def test_senza_tabella_la_guardia_non_inventa(monkeypatch):
    monkeypatch.setenv("APP_BOOT_ID", "avvio-NUOVO")
    db = _DbFinto(None)
    assert S.ferma_interruttori_al_nuovo_avvio(db=db) == []
    assert db.servizio_scritto == []
