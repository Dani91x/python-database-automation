"""25/09/2026 - LO SCALPER CALCIO LAVORA DA SOLO SUL FEED (auto-mode + flag + canale).

Ordine dell'utente (testuale): «Lo scalper deve lavorare da solo su tutte le
partite del feed come gli altri bot, i suoi ordini devono finire flaggati col
nome "scalper", pubblicalo sul canale come tutti gli altri.»

Si certifica, SENZA database e SENZA rete:
  (1) la logica pura (``scalper/auto_mode.py``): lista dal feed, tetto, vita
      della sessione, esclusioni, paper/live, partita sparita;
  (2) il giro del supervisore (``scalper_service.giro_auto``) con un finto del
      Db che ha gli STESSI metodi e restituisce righe con le chiavi VERE
      (``scalper_service_control``, ``scalper_control``, ``safe_strategy_scan``
      col payload del ramo calcio di ``build_rows``, ``live_follow``);
  (3) le query vere del Db (filtri, ``ignore_duplicates``, ``origine='auto'``)
      contro un client finto che registra la catena PostgREST;
  (4) il flag degli ordini: lo specchio VERO della sessione scrive
      ``source='scalper'`` in paper e in live; il giro dei regolati lo conta
      sotto la voce ``scalper``;
  (5) il canale: messaggi = riga + busta, solo a canale acceso, solo se la
      riga cambia, riga finale riletta una volta;
  (6) la migrazione: owner-only, corpi IDENTICI a quelli di prima dove dice
      "stesso corpo", CHECK della source con 'scalper'.
File ASCII-only.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream import avvio_app as AA
from Betfair.stream import canale_bot as CB
from Betfair.stream.scalper import auto_mode as AM
from Betfair.stream.scalper import scalper_service as SVC

RADICE = Path(__file__).resolve().parents[3]
MIGRAZIONE = RADICE / "migrations" / "scalper_auto_mode_2026-09-25.sql"

ORA = datetime(2026, 9, 25, 18, 0, 0, tzinfo=timezone.utc)
ORA_EP = ORA.timestamp()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# righe VERE (chiavi e tipi delle tabelle)
# ---------------------------------------------------------------------------
def riga_feed(ev: str, *, ko_min: float = 10.0, inplay: bool = False,
              home: str = "Casa", away: str = "Ospite", mo_status: str = "OPEN",
              mid: Optional[str] = "1.500", sport: str = "calcio") -> Dict[str, Any]:
    """Una riga di ``safe_strategy_scan`` come la restituisce ``Db.feed_calcio``
    (payload del ramo calcio di ``safe_strategy/service.py::build_rows``)."""
    return {
        "event_id": ev, "sport": sport, "updated_at": _iso(ORA),
        "payload": {
            "event_name": f"{home} v {away}", "home": home, "away": away,
            "competition": "Serie A", "open_date": _iso(ORA + timedelta(minutes=ko_min)),
            "inplay": inplay, "mo_market_id": mid, "mo_status": mo_status,
        },
    }


def riga_control(ev: str, *, status: str = "running", dry_run: bool = True,
                 origine: str = "auto", requested_at: Optional[str] = None,
                 stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Una riga di ``scalper_control`` (migrations/scalper_bot.sql + origine)."""
    return {
        "event_id": ev, "status": status, "mode": "maker", "dry_run": dry_run,
        "stake": 25, "params": {}, "bias": None, "bias_meta": None,
        "stats": stats, "error": None,
        "requested_at": requested_at or _iso(ORA - timedelta(minutes=5)),
        "started_at": None, "stopped_at": None, "heartbeat_at": _iso(ORA),
        "updated_at": _iso(ORA), "origine": origine,
    }


def riga_servizio(**over: Any) -> Dict[str, Any]:
    """La riga di ``scalper_service_control`` (colonne della migrazione)."""
    base = {
        "id": 1, "status": "running", "mode": "paper", "strategia": "maker",
        "stake": 25, "params": {}, "stats": None,
        "started_at": _iso(ORA - timedelta(hours=1)), "stopped_at": None,
        "updated_at": _iso(ORA - timedelta(minutes=30)),
    }
    base.update(over)
    return base


class DbFinto:
    """Stessi metodi di ``scalper_service.Db`` usati dal giro dell'auto-mode."""

    def __init__(self, servizio: Optional[Dict[str, Any]], feed: Optional[List[Dict[str, Any]]],
                 *, battito_eta_s: Optional[float] = 2.0,
                 control: Optional[Dict[str, Dict[str, Any]]] = None,
                 follow: Optional[Dict[str, str]] = None,
                 origine_assente: bool = False) -> None:
        self._servizio = servizio
        self._feed = feed
        self._battito = (None if battito_eta_s is None else
                         {"updated_at": _iso(ORA - timedelta(seconds=battito_eta_s))})
        self._control = dict(control or {})
        self._follow = dict(follow or {})
        self._origine_assente = origine_assente
        self.chiamate: List[tuple] = []

    # -- interruttore
    def servizio(self) -> Optional[Dict[str, Any]]:
        self.chiamate.append(("servizio",))
        if isinstance(self._servizio, Exception):
            raise self._servizio
        return None if self._servizio is None else dict(self._servizio)

    def set_servizio(self, **fields: Any) -> Any:
        self.chiamate.append(("set_servizio", fields))
        self._servizio = {**(self._servizio or {}), **fields,
                          "updated_at": _iso(ORA + timedelta(seconds=len(self.chiamate)))}
        return SimpleNamespace(data=[dict(self._servizio)])

    # -- feed
    def feed_calcio(self) -> Optional[List[Dict[str, Any]]]:
        self.chiamate.append(("feed_calcio",))
        return None if self._feed is None else list(self._feed)

    def battito_scanner(self) -> Optional[Dict[str, Any]]:
        self.chiamate.append(("battito_scanner",))
        return self._battito

    # -- righe
    def righe_control(self, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        self.chiamate.append(("righe_control", list(ids)))
        if self._origine_assente:
            raise SVC.OrigineAssente("column scalper_control.origine does not exist")
        return {e: self._control[e] for e in ids if e in self._control}

    def follows(self, ids: List[str]) -> Dict[str, str]:
        self.chiamate.append(("follows", list(ids)))
        return {e: self._follow[e] for e in ids if e in self._follow}

    def segui(self, p: Dict[str, Any]) -> None:
        self.chiamate.append(("segui", p["event_id"]))
        self._follow[p["event_id"]] = "PENDING"

    def arma(self, ev: str, campi: Dict[str, Any], vecchia: Optional[Dict[str, Any]]) -> Any:
        self.chiamate.append(("arma", ev, dict(campi), vecchia))
        riga = {"event_id": ev, **campi}
        self._control[ev] = riga
        return SimpleNamespace(data=[riga])

    def ferma_auto(self, ev: str) -> Any:
        self.chiamate.append(("ferma_auto", ev))
        return SimpleNamespace(data=[])

    def activity(self, ev: str, kind: str, payload: Dict[str, Any]) -> None:
        self.chiamate.append(("activity", ev, kind))
        # D3 (25/09): il payload si conserva a parte (le tuple di sopra restano uguali)
        self.attivita = getattr(self, "attivita", []) + [(ev, kind, dict(payload))]

    def riga_control(self, ev: str) -> Optional[Dict[str, Any]]:
        self.chiamate.append(("riga_control", ev))
        return self._control.get(ev)

    # -- aiuti per i test
    def nomi(self, nome: str) -> List[tuple]:
        return [c for c in self.chiamate if c[0] == nome]


def _stato(guardia_fatta: bool = True) -> SVC.StatoAuto:
    st = SVC.StatoAuto()
    if guardia_fatta:
        st.guardia.attiva = True
        st.guardia.fatto = True
        st.guardia.boot_id = "boot-1"
    return st


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(AM.ENV_TETTO, raising=False)
    monkeypatch.delenv(CB.ENV_SCALPER, raising=False)
    CB.azzera_statistiche()


# ===========================================================================
# (1) logica pura
# ===========================================================================
def test_partite_dal_feed_filtri_e_ordine() -> None:
    righe = [
        riga_feed("30", ko_min=30),
        riga_feed("10", ko_min=-20, inplay=True),
        riga_feed("20", ko_min=5),
        riga_feed("40", mo_status="CLOSED"),
        riga_feed("50", mid=None),
        riga_feed("60", sport="tennis"),
        riga_feed("70", home=""),
        riga_feed("20", ko_min=5),                     # doppione
        {"event_id": "80", "sport": "calcio", "payload": "non un dict"},
    ]
    out = AM.partite_dal_feed(righe)
    assert [p["event_id"] for p in out] == ["10", "20", "30"]
    assert out[0] == {"event_id": "10", "home": "Casa", "away": "Ospite",
                      "competition": "Serie A",
                      "open_date": _iso(ORA - timedelta(minutes=20)), "inplay": True}


@pytest.mark.parametrize("params,env,atteso", [
    ({}, {}, 2),
    ({}, {"SCALPER_AUTO_MAX_PARTITE": "3"}, 3),
    ({"auto_max_partite": 1}, {"SCALPER_AUTO_MAX_PARTITE": "3"}, 1),
    ({"auto_max_partite": 0}, {}, 0),
    ({"auto_max_partite": 99}, {}, 4),
    ({"auto_max_partite": "x"}, {"SCALPER_AUTO_MAX_PARTITE": ""}, 2),
    ({"auto_max_partite": -1}, {}, 2),
])
def test_tetto(params: Dict[str, Any], env: Dict[str, str], atteso: int) -> None:
    assert AM.tetto_partite(params, env) == atteso


def test_params_per_sessione_toglie_solo_il_tetto() -> None:
    p = {"auto_max_partite": 3, "sniper_mode": True, "uscite_automatiche": False}
    assert AM.params_per_sessione(p) == {"sniper_mode": True, "uscite_automatiche": False}
    assert p["auto_max_partite"] == 3          # l'originale non si muta


def test_sniper_mode_acceso_di_default() -> None:
    """ordine dell'utente 25/09 sera (testuale): <<scalper, modalita' sniper:
    acceso>> + regola generale <<tutti i bot devono avere gli aiuti e le
    migliorie accese di default>>. L'ASSENZA della chiave e' ON; SOLO
    ``sniper_mode=false`` ESPLICITO spegne. Falsificazione: rimettendo il
    default a False (``bool(p.get("sniper_mode"))``) le prime due righe
    diventano rosse."""
    assert AM.sniper_mode_acceso({}) is True
    assert AM.sniper_mode_acceso(None) is True
    assert AM.sniper_mode_acceso({"sniper_mode": True}) is True
    assert AM.sniper_mode_acceso({"sniper_mode": False}) is False
    # None esplicito (chiave scritta ma senza valore) = "non dichiarato" = ON
    assert AM.sniper_mode_acceso({"sniper_mode": None}) is True


def test_vita_della_sessione_numeri_di_prima() -> None:
    # 25/09 sera: lo sniper e' ACCESO di default (ordine dell'utente) -> con
    # params VUOTI la sessione vive ora 7800s (vita sniper/theta), non piu'
    # 600 (dichiarato: il ramo "solo maker" resta raggiungibile SOLO con
    # sniper_mode=False esplicito, come manda la card quando l'utente spegne
    # lo sniper o accende la gamba HT, mutuamente esclusiva).
    assert AM.vita_sessione_s({}) == 7800
    assert AM.vita_sessione_s({"sniper_mode": False}) == 600
    assert AM.vita_sessione_s({"sniper_mode": False, "ht_mode": True}) == 4200
    assert AM.vita_sessione_s({"sniper_mode": True}) == 7800
    assert AM.vita_sessione_s({"theta_mode": True, "ht_mode": True}) == 7800
    ko = _iso(ORA - timedelta(minutes=11))
    assert AM.ha_ancora_vita(ko, {}, ORA_EP) is True
    assert AM.ha_ancora_vita(ko, {"sniper_mode": False}, ORA_EP) is False
    assert AM.ha_ancora_vita(
        ko, {"sniper_mode": False, "ht_mode": True}, ORA_EP) is True
    assert AM.ha_ancora_vita(None, {}, ORA_EP) is True


def test_la_sessione_usa_la_stessa_vita() -> None:
    """La sessione non ha piu' i numeri inline: li prende da auto_mode."""
    src = (RADICE / "Betfair/stream/scalper/scalper_session.py").read_text(encoding="utf-8")
    assert "_life_s = vita_sessione_s({" in src
    assert "7800 if (sniper_mode or theta_mode)" not in src


def test_la_sessione_usa_lo_stesso_default_sniper() -> None:
    """25/09 sera: la sessione NON deve reintrodurre un bool() locale che
    riporterebbe il default a spento -- l'unico punto di risoluzione resta
    ``auto_mode.sniper_mode_acceso`` (falsificazione: sostituendo l'import o
    la chiamata con ``bool((...).get("sniper_mode"))`` questo test e' rosso)."""
    src = (RADICE / "Betfair/stream/scalper/scalper_session.py").read_text(encoding="utf-8")
    assert "from .auto_mode import sniper_mode_acceso" in src
    assert "sniper_mode = sniper_mode_acceso(control.get(\"params\") or {})" in src
    assert 'bool((control.get("params") or {}).get("sniper_mode"))' not in src


@pytest.mark.parametrize("riga,atteso", [
    (None, None),
    ({"status": "running"}, "attiva"),
    ({"status": "stopping"}, "attiva"),
    ({"status": "armed"}, "in attesa di consenso bias"),
    ({"status": "error"}, "in errore"),
    ({"status": "done"}, "conclusa"),
    ({"status": "stopped", "requested_at": _iso(ORA - timedelta(hours=2))}, None),
    ({"status": "stopped", "requested_at": _iso(ORA - timedelta(minutes=10))}, "chiusa a mano"),
    ({"status": "stopped", "requested_at": None}, "chiusa a mano"),
    ({"status": "boh"}, "stato sconosciuto (boh)"),
])
def test_motivo_esclusione(riga: Optional[Dict[str, Any]], atteso: Optional[str]) -> None:
    acceso_dal = _iso(ORA - timedelta(hours=1))
    assert AM.motivo_esclusione(riga, acceso_dal) == atteso


def test_origine_solo_auto_scritto() -> None:
    assert AM.origine_riga({"origine": "auto"}) == "auto"
    assert AM.origine_riga({"origine": " AUTO "}) == "auto"
    assert AM.origine_riga({}) == "manuale"
    assert AM.origine_riga({"origine": None}) == "manuale"


def test_partita_sparita_dopo_60s_e_memoria_pulita() -> None:
    assenti: Dict[str, float] = {}
    righe = [riga_control("1"), riga_control("2")]
    assert AM.da_fermare_per_feed(righe, {"1"}, assenti, 100.0) == []
    assert assenti == {"2": 100.0}
    assert AM.da_fermare_per_feed(righe, {"1"}, assenti, 159.0) == []
    assert AM.da_fermare_per_feed(righe, {"1"}, assenti, 160.0) == ["2"]
    # torna nel feed: dimenticata
    assert AM.da_fermare_per_feed(righe, {"1", "2"}, assenti, 170.0) == []
    assert assenti == {}


def test_conflitto_modalita() -> None:
    assert AM.conflitto_modalita([riga_control("1", dry_run=True)], "paper") is None
    assert AM.conflitto_modalita([riga_control("1", dry_run=False)], "paper") == "live"
    # D3 (25/09): in LIVE le sessioni automatiche nascono in dry-run e l'utente
    # toglie il dry-run per sessione: prova e soldi veri convivono per sua
    # scelta, nessun conflitto (prima: "paper")
    assert AM.conflitto_modalita([riga_control("1", dry_run=True)], "live") is None
    assert AM.conflitto_modalita([riga_control("1", dry_run=False),
                                  riga_control("2", dry_run=True)], "live") is None


def test_d3_dry_run_alla_nascita_sempre_vero() -> None:
    """D3 (25/09): «dry run per tutti: decido io cosa attivare, se PAPER o LIVE»."""
    assert AM.dry_run_alla_nascita("live") is True
    assert AM.dry_run_alla_nascita("paper") is True
    assert AM.dry_run_alla_nascita("") is True


# ===========================================================================
# (2) il giro del supervisore
# ===========================================================================
def test_acceso_arma_dal_feed_fino_al_tetto_con_i_campi_giusti() -> None:
    serv = riga_servizio(params={"auto_max_partite": 2, "sniper_mode": False,
                                 "uscite_automatiche": False}, stake=12)
    db = DbFinto(serv, [riga_feed("3", ko_min=30), riga_feed("1", ko_min=5),
                        riga_feed("2", ko_min=10)],
                 follow={"2": "STREAMING"})
    es = SVC.giro_auto(db, _stato(), [], ORA_EP)
    assert es["armate"] == ["1", "2"]
    # il follow si scrive SOLO dove manca
    assert [c[1] for c in db.nomi("segui")] == ["1"]
    arma = db.nomi("arma")
    assert [c[1] for c in arma] == ["1", "2"]
    campi = arma[0][2]
    assert campi["status"] == "requested"
    assert campi["origine"] == "auto"
    assert campi["dry_run"] is True                 # paper: client simulato
    assert campi["mode"] == "maker"
    assert campi["stake"] == 12
    assert campi["params"] == {"sniper_mode": False, "uscite_automatiche": False}
    assert campi["stats"] == {"boot_id": "boot-1"}  # timbrata con l'avvio
    assert arma[0][3] is None                       # riga nuova: mai sopra una viva
    # i fatti in stats.auto, scritti una volta
    st = db.nomi("set_servizio")[-1][1]["stats"]["auto"]
    assert st["acceso"] is True and st["tetto"] == 2 and st["armate_ora"] == ["1", "2"]
    assert st["feed"]["fonte"] == "safe_strategy_scan" and st["feed"]["partite"] == 3
    assert es["motivo"] is None


def test_live_nasce_in_dry_run() -> None:
    """D3 (25/09, ordine dell'utente «dry run per tutti: decido io cosa
    attivare, se PAPER o LIVE»): con l'interruttore in soldi veri la partita
    armata dal feed nasce in DRY-RUN (prima di oggi nasceva con soldi veri,
    ``test_live_nasce_live``). L'attivita' e le stats lo dicono."""
    db = DbFinto(riga_servizio(mode="live"), [riga_feed("1")])
    es = SVC.giro_auto(db, _stato(), [], ORA_EP)
    assert es["armate"] == ["1"]
    assert db.nomi("arma")[0][2]["dry_run"] is True
    att = [p for ev, kind, p in db.attivita if kind == "auto_armata"]
    assert att and att[-1]["dry_run"] is True and att[-1]["modalita"] == "live"
    auto = db.nomi("set_servizio")[-1][1]["stats"]["auto"]
    assert auto["modalita"] == "live" and auto["nascono_in_dry_run"] is True


def test_live_con_sessioni_in_dry_run_continua_ad_armare() -> None:
    """D3: in live le sessioni automatiche in dry-run NON sono un conflitto
    (prima bloccavano l'armamento delle partite successive)."""
    viva = riga_control("7", dry_run=True, origine="auto")
    db = DbFinto(riga_servizio(mode="live"), [riga_feed("7"), riga_feed("1")])
    es = SVC.giro_auto(db, _stato(), [viva], ORA_EP)
    assert es["armate"] == ["1"]
    assert db.nomi("set_servizio")[-1][1]["stats"]["auto"]["conflitto"] is None


def test_il_tetto_conta_anche_le_sessioni_della_card() -> None:
    manuale = riga_control("99", origine="manuale", status="running")
    db = DbFinto(riga_servizio(), [riga_feed("1"), riga_feed("2")])
    es = SVC.giro_auto(db, _stato(), [manuale], ORA_EP)
    assert es["armate"] == ["1"]                    # tetto 2 - 1 della card


def test_tetto_pieno_nessuna_lettura_per_armare() -> None:
    righe = [riga_control("1"), riga_control("2")]
    db = DbFinto(riga_servizio(), [riga_feed("1"), riga_feed("2"), riga_feed("3")])
    es = SVC.giro_auto(db, _stato(), righe, ORA_EP)
    assert es["armate"] == []
    assert db.nomi("righe_control") == [] and db.nomi("follows") == []


def test_mai_riarmare_chiuse_a_mano_errore_concluse_follow_chiusi() -> None:
    dal = ORA - timedelta(hours=1)
    control = {
        "1": riga_control("1", status="stopped", requested_at=_iso(dal + timedelta(minutes=5))),
        "2": riga_control("2", status="error"),
        "3": riga_control("3", status="done"),
        "5": riga_control("5", status="stopped", requested_at=_iso(dal - timedelta(minutes=5))),
    }
    db = DbFinto(riga_servizio(params={"auto_max_partite": 4}),
                 [riga_feed(e) for e in ("1", "2", "3", "4", "5")],
                 control=control, follow={"4": "CLOSED"})
    es = SVC.giro_auto(db, _stato(), [], ORA_EP)
    assert es["armate"] == ["5"]
    # la riga ferma di PRIMA dell'accensione si riarma con la guardia della riga
    assert db.nomi("arma")[0][3] == control["5"]


def test_partita_oltre_la_vita_non_si_arma() -> None:
    # 25/09 sera: lo sniper e' ACCESO di default -> con params VUOTI la vita
    # e' gia' quella lunga (sniper/theta, 130'). Per vedere il taglio corto
    # (solo maker, KO+10') va dichiarato sniper_mode=False ESPLICITO.
    db = DbFinto(riga_servizio(params={"sniper_mode": False}),
                 [riga_feed("1", ko_min=-11, inplay=True),
                  riga_feed("2", ko_min=5)])
    es = SVC.giro_auto(db, _stato(), [], ORA_EP)
    assert es["armate"] == ["2"]
    # params VUOTI (default): "1" (11' dopo il KO) e' ancora nella vita lunga
    # dello sniper acceso di default -> SI arma (falsificazione: rimettendo
    # il default a spento questa riga torna rossa, come prima del 25/09).
    db2 = DbFinto(riga_servizio(), [riga_feed("1", ko_min=-11, inplay=True)])
    assert SVC.giro_auto(db2, _stato(), [], ORA_EP)["armate"] == ["1"]


def test_paper_e_live_mai_insieme() -> None:
    live_card = riga_control("9", origine="manuale", dry_run=False)
    db = DbFinto(riga_servizio(mode="paper"), [riga_feed("1")])
    es = SVC.giro_auto(db, _stato(), [live_card], ORA_EP)
    assert es["armate"] == []
    # c'e' una sessione viva: nessun "motivo" (sta lavorando), ma il fatto si scrive
    auto = db.nomi("set_servizio")[-1][1]["stats"]["auto"]
    assert auto["conflitto"] == "live"
    # senza sessioni vive la frase lo dice
    assert AM.motivo_blocco(acceso=True, bloccato=False, feed_letto=True, feed_vivo=True,
                            partite_feed=1, origine_ok=True, tetto=2, sessioni=0,
                            conflitto="live", armabili=1) == (
        "sessioni in soldi veri ancora attive: paper e live mai insieme, nessuna "
        "partita nuova finche' non si fermano")


def test_spento_ferma_solo_le_automatiche_e_non_legge_il_feed() -> None:
    righe = [riga_control("1", origine="auto"), riga_control("2", origine="manuale"),
             riga_control("3", origine="auto", status="stopping")]
    db = DbFinto(riga_servizio(status="stopped"), [riga_feed("1")])
    es = SVC.giro_auto(db, _stato(), righe, ORA_EP)
    assert es["fermate"] == ["1"]
    assert db.nomi("feed_calcio") == [] and db.nomi("arma") == []


def test_partita_uscita_dal_feed_stop_pulito_solo_auto() -> None:
    righe = [riga_control("1", origine="auto"), riga_control("2", origine="manuale")]
    st = _stato()
    db = DbFinto(riga_servizio(), [riga_feed("7")])
    SVC.giro_auto(db, st, righe, ORA_EP)
    assert db.nomi("ferma_auto") == []               # prima assenza: si aspetta
    db._battito = {"updated_at": _iso(ORA + timedelta(seconds=60))}   # scanner vivo
    SVC.giro_auto(db, st, righe, ORA_EP + 61, forza=True)
    assert [c[1] for c in db.nomi("ferma_auto")] == ["1"]


def test_feed_muto_non_arma_e_non_ferma() -> None:
    righe = [riga_control("1", origine="auto")]
    st = _stato()
    db = DbFinto(riga_servizio(), [], battito_eta_s=45.0)     # scanner fermo
    es = SVC.giro_auto(db, st, righe, ORA_EP)
    SVC.giro_auto(db, st, righe, ORA_EP + 120, forza=True)
    assert db.nomi("ferma_auto") == [] and es["armate"] == []
    db2 = DbFinto(riga_servizio(), None)                        # lettura KO
    es2 = SVC.giro_auto(db2, _stato(), [], ORA_EP)
    assert es2["motivo"] == AM.MOTIVO_FEED_MUTO
    assert db2.nomi("battito_scanner") == []


def test_feed_vuoto_lo_dice() -> None:
    db = DbFinto(riga_servizio(), [])
    assert SVC.giro_auto(db, _stato(), [], ORA_EP)["motivo"] == AM.MOTIVO_FEED_VUOTO


def test_origine_assente_non_arma_e_lo_dice() -> None:
    db = DbFinto(riga_servizio(), [riga_feed("1")], origine_assente=True)
    es = SVC.giro_auto(db, _stato(), [], ORA_EP)
    assert es["armate"] == [] and es["motivo"] == AM.MOTIVO_ORIGINE_ASSENTE


def test_guardia_d_avvio_armata_non_arma() -> None:
    st = SVC.StatoAuto()
    st.guardia.attiva = True             # controllo d'avvio non ancora riuscito
    db = DbFinto(Exception("rete giu'"), [riga_feed("1")])
    es = SVC.giro_auto(db, st, [], ORA_EP)
    assert es["letto"] is False and es["armate"] == []


def test_guardia_non_riuscita_blocca_l_armamento(monkeypatch: pytest.MonkeyPatch) -> None:
    """Il controllo d'avvio non riesce a scrivere: la guardia resta armata e
    NIENTE si arma, anche con l'interruttore acceso e il feed pieno."""
    monkeypatch.setenv(AA.ENV_BOOT_ID, "boot-oggi")

    class _DbScritturaKO(DbFinto):
        def set_servizio(self, **fields: Any) -> Any:
            self.chiamate.append(("set_servizio_ko", fields))
            raise RuntimeError("503 PGRST002")
    st = SVC.StatoAuto()
    st.guardia.attiva = True
    db = _DbScritturaKO(riga_servizio(stats={"boot_id": "boot-ieri"}), [riga_feed("1")])
    es = SVC.giro_auto(db, st, [], ORA_EP)
    assert st.guardia.blocca_aperture is True
    assert es["armate"] == [] and db.nomi("arma") == []
    assert es["motivo"] == AM.MOTIVO_GUARDIA


def test_avvio_nuovo_dell_app_spegne_l_interruttore_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AA.ENV_BOOT_ID, "boot-oggi")
    st = SVC.StatoAuto()
    st.guardia.attiva = True
    db = DbFinto(riga_servizio(mode="live", stats={"boot_id": "boot-ieri"}), [riga_feed("1")])
    es = SVC.giro_auto(db, st, [], ORA_EP)
    primo = db.nomi("set_servizio")[0][1]
    assert primo["status"] == "stopped" and primo["mode"] == "paper"
    assert es["armate"] == []
    assert ("activity", "servizio", AA.KIND_ATTIVITA) in db.chiamate


def test_interruttore_letto_a_caldo_e_giro_a_15s() -> None:
    st = _stato()
    db = DbFinto(riga_servizio(), [])
    SVC.giro_auto(db, st, [], ORA_EP)
    n_feed = len(db.nomi("feed_calcio"))
    SVC.giro_auto(db, st, [], ORA_EP + 3)            # nessun cambio: niente feed
    assert len(db.nomi("feed_calcio")) == n_feed
    assert len(db.nomi("servizio")) == 2             # l'interruttore si rilegge sempre
    # l'utente spegne: il giro parte SUBITO (nessuna attesa dei 15 s)
    db._servizio = {**db._servizio, "status": "stopped",
                    "updated_at": _iso(ORA + timedelta(seconds=4))}
    es = SVC.giro_auto(db, st, [riga_control("1")], ORA_EP + 4)
    assert es["fermate"] == ["1"]


def test_interruttore_illeggibile_non_deduce_niente() -> None:
    db = DbFinto(Exception("relation scalper_service_control does not exist"), [riga_feed("1")])
    es = SVC.giro_auto(db, _stato(), [riga_control("1")], ORA_EP)
    assert es == {"letto": False, "armate": [], "fermate": [], "motivo": None}
    assert [c[0] for c in db.chiamate] == ["servizio"]


def test_stats_write_on_change() -> None:
    st = _stato()
    db = DbFinto(riga_servizio(), [])
    SVC.giro_auto(db, st, [], ORA_EP)
    SVC.giro_auto(db, st, [], ORA_EP + 20, forza=True)
    assert len(db.nomi("set_servizio")) == 1         # stessi fatti: nessuna scrittura


# ===========================================================================
# (3) le query VERE del Db, su un client che registra la catena PostgREST
# ===========================================================================
class _Catena:
    def __init__(self, reg: List[tuple], tabella: str) -> None:
        self.reg = reg
        self.reg.append(("table", tabella))

    def __getattr__(self, nome: str) -> Any:
        def f(*a: Any, **k: Any) -> "_Catena":
            self.reg.append((nome, a, k))
            return self
        return f

    def execute(self) -> Any:
        self.reg.append(("execute",))
        return SimpleNamespace(data=[{"event_id": "1"}])


class _SbFinto:
    def __init__(self) -> None:
        self.reg: List[tuple] = []

    def table(self, nome: str) -> _Catena:
        return _Catena(self.reg, nome)


def _db_vero() -> SVC.Db:
    db = SVC.Db.__new__(SVC.Db)
    db.sb = _SbFinto()
    return db


def test_query_ferma_auto_tocca_solo_righe_auto_attive() -> None:
    db = _db_vero()
    db.ferma_auto("35")
    reg = db.sb.reg
    assert ("table", "scalper_control") in reg
    assert ("eq", ("origine", "auto"), {}) in reg
    assert ("in_", ("status", ["requested", "arming", "armed", "running"]), {}) in reg
    upd = [c for c in reg if c[0] == "update"][0][1][0]
    assert upd["status"] == "stopping"


def test_query_segui_e_arma_non_sovrascrivono() -> None:
    db = _db_vero()
    db.segui({"event_id": "35", "home": "A", "away": "B", "open_date": "x",
              "competition": "Serie A"})
    ups = [c for c in db.sb.reg if c[0] == "upsert"][0]
    assert ups[2] == {"on_conflict": "event_id", "ignore_duplicates": True}
    assert "record" not in ups[1][0] and ups[1][0]["status"] == "PENDING"
    db2 = _db_vero()
    db2.arma("35", {"status": "requested"}, None)
    ups2 = [c for c in db2.sb.reg if c[0] == "upsert"][0]
    assert ups2[2] == {"on_conflict": "event_id", "ignore_duplicates": True}
    db3 = _db_vero()
    db3.arma("35", {"status": "requested"}, {"requested_at": "T0"})
    assert ("eq", ("status", "stopped"), {}) in db3.sb.reg
    assert ("eq", ("requested_at", "T0"), {}) in db3.sb.reg


def test_query_feed_solo_calcio_e_chiavi_utili() -> None:
    db = _db_vero()
    db.sb.table = lambda nome: _CatenaFeed(db.sb.reg, nome)  # type: ignore[assignment]
    righe = db.feed_calcio()
    sel = [c for c in db.sb.reg if c[0] == "select"][0][1][0]
    assert "home:payload->home" in sel and "score_raw" not in sel
    assert ("eq", ("sport", "calcio"), {}) in db.sb.reg
    assert righe == [{"event_id": "1", "sport": "calcio", "updated_at": "t",
                      "payload": {k: ("A" if k == "home" else None) for k in AM.CHIAVI_FEED}}]


class _CatenaFeed(_Catena):
    def execute(self) -> Any:
        return SimpleNamespace(data=[{"event_id": "1", "sport": "calcio",
                                      "updated_at": "t", "home": "A"}])


def test_righe_control_senza_origine_solleva_origine_assente() -> None:
    db = _db_vero()

    class _Rotta(_Catena):
        def execute(self) -> Any:
            raise RuntimeError("column scalper_control.origine does not exist")
    db.sb.table = lambda nome: _Rotta(db.sb.reg, nome)  # type: ignore[assignment]
    with pytest.raises(SVC.OrigineAssente):
        db.righe_control(["1"])


# ===========================================================================
# (4) il flag degli ordini
# ===========================================================================
def _ordine_flumine(ref: str) -> Any:
    ot = SimpleNamespace(ORDER_TYPE=SimpleNamespace(name="LIMIT"), price=2.0, size=10.0,
                         persistence_type="LAPSE")
    return SimpleNamespace(
        id="OID-9", bet_id="228000000001", market_id="1.200", selection_id=47972,
        handicap=0.0, side="BACK", status=SimpleNamespace(name="EXECUTABLE"),
        order_type=ot, size_matched=10.0, size_remaining=0.0, size_cancelled=0.0,
        size_lapsed=0.0, size_voided=0.0, average_price_matched=2.0,
        customer_order_ref=ref,
        responses=SimpleNamespace(date_time_placed="2026-09-25T12:00:00+00:00"),
        date_time_status_update="2026-09-25T12:00:01+00:00")


@pytest.mark.parametrize("modo", ["paper", "live"])
def test_lo_specchio_vero_della_sessione_flagga_scalper(modo: str, monkeypatch) -> None:
    from Betfair.stream.scalper import scalper_session as SS
    scritte: List[Dict[str, Any]] = []
    import Betfair.stream.engine.live_trading_strategy as LTS
    monkeypatch.setattr(LTS, "_db", lambda: SimpleNamespace(
        upsert_live_order=lambda row: scritte.append(row),
        upsert_live_position=lambda row: None,
        find_live_order_ref=lambda *a: None))
    mirror = SS._make_session_mirror(["1.200"], modo)
    mercato = SimpleNamespace(event_id="35760084", market_id="1.200", blotter=None)
    mirror.process_orders(mercato, [_ordine_flumine("b1946ac92492d-17a2f3")])
    assert len(scritte) == 1
    assert scritte[0]["source"] == "scalper" and scritte[0]["mode"] == modo


def test_ordini_vivi_dal_blotter() -> None:
    from Betfair.stream.scalper import scalper_session as SS
    o = lambda st: SimpleNamespace(status=SimpleNamespace(name=st))  # noqa: E731
    fw = SimpleNamespace(markets=[SimpleNamespace(blotter=[o("EXECUTABLE"), o("EXECUTION_COMPLETE")]),
                                  SimpleNamespace(blotter=[o("PENDING")]),
                                  SimpleNamespace(blotter=None)])
    assert SS._ordini_vivi(fw) == 2

    class _Rotto:
        @property
        def markets(self) -> Any:
            raise RuntimeError("mutato")
    assert SS._ordini_vivi(_Rotto()) is None


def test_i_regolati_contano_lo_scalper_sotto_la_sua_voce() -> None:
    from Betfair.stream import reconcile_worker as rw
    assert "scalper" in rw.FONTI
    o = SimpleNamespace(event_type_id="1")
    assert rw._fonte_di("betfair_live_orders", {"source": "scalper"}, o) == "scalper"
    assert rw._fonte_di("betfair_live_orders", {"source": "runner"}, o) == "manuale_app"
    assert rw._fonte_di("betfair_live_orders", {"source": "bot:x"}, o) == "altri_bot"
    ordine = SimpleNamespace(bet_id="5", profit=2.0, market_id="1.2", settled_date=None,
                             customer_order_ref=None, customer_strategy_ref=None,
                             event_type_id="1")
    gruppi = [SimpleNamespace(market_id="1.2", commission=0.1, profit=2.0, bet_count=1)]
    tot, _righe = rw.componi_regolati([ordine], gruppi,
                                      {"5": ("betfair_live_orders", 77, {"source": "scalper"})},
                                      "2026-09-25")
    assert tot["per_fonte"]["scalper"]["netto"] == pytest.approx(1.9)
    assert tot["per_fonte"]["manuale_app"]["ordini"] == 0


# ===========================================================================
# (5) il canale
# ===========================================================================
class _CanaleFinto:
    def __init__(self) -> None:
        self.msg: List[tuple] = []

    def publish(self, topic: str, payload: Any) -> None:
        self.msg.append((topic, payload))


@pytest.fixture()
def canale(monkeypatch: pytest.MonkeyPatch) -> _CanaleFinto:
    ch = _CanaleFinto()
    monkeypatch.setattr(CB, "_canale", lambda: ch)
    monkeypatch.setenv(CB.ENV_SCALPER, "1")
    return ch


def test_topic_e_porta_in_un_posto_solo() -> None:
    assert CB.TOPIC["scalper_stato"] == "scalper_stato"
    assert CB.TOPIC["scalper_sessioni"] == "scalper_sessioni"
    assert CB.PORTA_SCALPER == 47338
    assert CB.PORTA_SCALPER not in (47331, 47332, 47333, 47334, 47335, 47336, 47337)


def test_sessioni_sul_canale_riga_piu_busta_solo_se_cambia(canale: _CanaleFinto) -> None:
    pub = SVC.PubblicaSessioni()
    r1 = riga_control("1", stats={"pnl_locked": 0.4, "ordini_vivi": 2})
    db = DbFinto(None, None, control={"1": {**r1, "status": "stopped"}})
    pub(db, [r1])
    pub(db, [r1])                                        # identica: niente
    assert len(canale.msg) == 1
    topic, msg = canale.msg[0]
    assert topic == "scalper_sessioni"
    assert {k: v for k, v in msg.items() if k not in CB.CHIAVI_META} == r1
    assert msg["fonte"] == "canale" and isinstance(msg["_seq"], int)
    # la sessione esce dalle attive: riletta UNA volta e pubblicata finale
    pub(db, [])
    assert canale.msg[-1][1]["status"] == "stopped"
    assert db.nomi("riga_control") == [("riga_control", "1")]
    pub(db, [])
    assert db.nomi("riga_control") == [("riga_control", "1")]


def test_canale_spento_nessun_messaggio_nessuna_lettura(monkeypatch) -> None:
    ch = _CanaleFinto()
    monkeypatch.setattr(CB, "_canale", lambda: ch)
    pub = SVC.PubblicaSessioni()
    db = DbFinto(None, None)
    pub(db, [riga_control("1")])
    pub(db, [])
    assert ch.msg == [] and db.chiamate == []


def test_stato_sul_canale_e_la_riga_restituita(canale: _CanaleFinto) -> None:
    db = DbFinto(riga_servizio(), [riga_feed("1")])
    SVC.giro_auto(db, _stato(), [], ORA_EP)
    stati = [m for t, m in canale.msg if t == "scalper_stato"]
    assert stati, "lo stato deve uscire sul canale"
    ultimo = stati[-1]
    assert ultimo["id"] == 1 and ultimo["stats"]["auto"]["armate_ora"] == ["1"]
    sess = [m for t, m in canale.msg if t == "scalper_sessioni"]
    assert sess and sess[0]["event_id"] == "1" and sess[0]["origine"] == "auto"


# ===========================================================================
# (6) la migrazione
# ===========================================================================
def _sql(p: Path = MIGRAZIONE) -> str:
    return p.read_text(encoding="utf-8")


def _corpo(sql: str, nome: str) -> str:
    i = sql.index(f"CREATE OR REPLACE FUNCTION public.{nome}(")
    a = sql.index("AS $$", i)
    b = sql.index("$$;", a + 5)
    return sql[a + 5:b]


def _norm(s: str) -> List[str]:
    return [l.split("--", 1)[0].rstrip() for l in s.splitlines()
            if l.split("--", 1)[0].strip()]


@pytest.mark.parametrize("nome,firma", [
    ("scalper_auto_activate", "text, numeric, text, jsonb"),
    ("scalper_auto_stop", ""),
    ("scalper_auto_update", "numeric, jsonb, text"),
    ("scalper_uscite_automatiche", "boolean"),
    ("get_scalper_control_room", "integer"),
    ("scalper_activate", "text,text,boolean,numeric,jsonb"),
])
def test_rpc_owner_only_e_grant(nome: str, firma: str) -> None:
    sql = _sql()
    c = _corpo(sql, nome)
    prima = [l.strip() for l in _norm(c.split("BEGIN", 1)[1])][0]
    assert prima == "IF NOT public.betfair_live_is_owner() THEN"
    i = sql.index(f"CREATE OR REPLACE FUNCTION public.{nome}(")
    testa = sql[i:sql.index("AS $$", i)]
    assert "SECURITY DEFINER" in testa and "SET search_path = public, pg_temp" in testa
    assert f"REVOKE ALL    ON FUNCTION public.{nome}({firma}) FROM public, anon;" in sql
    assert f"GRANT EXECUTE ON FUNCTION public.{nome}({firma}) TO authenticated, service_role;" in sql


def test_get_scalper_control_room_stesso_corpo_piu_servizio() -> None:
    vecchio = _norm(_corpo(_sql(RADICE / "migrations/scalper_control_room_2026-09-24.sql"),
                           "get_scalper_control_room"))
    nuovo = _norm(_corpo(_sql(), "get_scalper_control_room"))
    aggiunte = [l for l in nuovo if l not in vecchio]
    assert aggiunte == [
        "    v_servizio jsonb;",
        "    SELECT to_jsonb(s.*) INTO v_servizio",
        "      FROM public.scalper_service_control s WHERE s.id = 1;",
        "        'servizio', v_servizio,",
    ]
    assert [l for l in vecchio if l not in nuovo] == []


def test_scalper_activate_stesso_corpo_piu_origine_manuale() -> None:
    vecchio = _norm(_corpo(_sql(RADICE / "migrations/scalper_bot.sql"), "scalper_activate"))
    nuovo = _norm(_corpo(_sql(), "scalper_activate"))
    tolte = [l for l in vecchio if l not in nuovo]
    aggiunte = [l for l in nuovo if l not in vecchio]
    assert tolte == [
        "         requested_at, started_at, stopped_at, heartbeat_at, updated_at)",
        "         NULL, NULL, NULL, NULL, now(), NULL, NULL, NULL, now())",
        "        updated_at   = now()",
    ]
    assert aggiunte == [
        "         requested_at, started_at, stopped_at, heartbeat_at, updated_at, origine)",
        "         NULL, NULL, NULL, NULL, now(), NULL, NULL, NULL, now(), 'manuale')",
        "        updated_at   = now(),",
        "        origine      = 'manuale'",
    ]


def test_stop_auto_stesse_transizioni_di_scalper_stop() -> None:
    c = _corpo(_sql(), "scalper_auto_stop")
    assert "SET status = CASE WHEN status IN ('running', 'arming', 'armed')" in c
    assert "THEN 'stopping' ELSE 'stopped' END" in c
    assert "WHERE status IN ('requested', 'arming', 'armed', 'running');" in c
    assert re.findall(r"UPDATE public\.(\w+)", c) == ["scalper_service_control", "scalper_control"]
    assert "DELETE" not in c


def test_activate_rifiuta_cambio_modalita_a_caldo() -> None:
    c = _corpo(_sql(), "scalper_auto_activate")
    assert "IF v_row.status = 'running' AND v_row.mode <> v_mode THEN" in c
    assert "v_mode NOT IN ('paper', 'live')" in c


def test_check_source_con_scalper_e_nient_altro() -> None:
    s = _sql()
    assert "CHECK (source IN ('runner', 'account', 'scalper')) NOT VALID;" in s
    assert "LIKE 'bot:" not in s


def test_colonne_interruttore_compatibili_con_avvio_app() -> None:
    """`avvio_app.ferma_al_nuovo_avvio` scrive status='stopped' e mode='paper':
    devono stare nei CHECK della tabella."""
    s = _sql()
    assert "CHECK (status IN ('running', 'stopped'))" in s
    assert "CHECK (mode IN ('paper', 'live'))" in s
    assert "CHECK (origine IN ('manuale', 'auto'))" in s
