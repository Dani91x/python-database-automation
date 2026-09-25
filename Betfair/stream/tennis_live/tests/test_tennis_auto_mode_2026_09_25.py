# -*- coding: utf-8 -*-
"""AUTO-MODE dei 4 bot tennis (25/09): il ponte arma dal FEED UNICO.

ORDINE DELL'UTENTE: «i bot devono partire e lavorare tramite feed unico una
volta attivati [...] auto-mode [...] uscite in automatico o in manuale sia in
paper che in live.»

I finti parlano come il vero: le righe hanno le IDENTICHE chiavi delle tabelle
(`tennis_bot_service_control`, `tennis_bot_control`, `tennis_live_follow`,
`safe_strategy_scan` sport tennis, `safe_strategy_status`, `tennis_live_now`)
e i metodi hanno le firme di `tennis_db`. Ogni regola ha il suo contrario.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream.tennis_live import auto_mode as AM
from Betfair.stream.tennis_live import tennis_bot_service as S
from Betfair.stream.tennis_live import tennis_db
from Betfair.stream.tennis_live import tennis_runner as TR

ORA = datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ===========================================================================
# righe VERE, chiave per chiave
# ===========================================================================
def _servizio(bot="tennis_flb", status="running", mode="paper", stake=3,
              params=None, uscite=None, con_uscite=False):
    r = {"bot_key": bot, "status": status, "mode": mode, "stake": stake,
         "params": params if params is not None else {}, "stats": None,
         "error": None, "started_at": None, "stopped_at": None,
         "heartbeat_at": None, "updated_at": None}
    if con_uscite:
        r["uscite_automatiche"] = True if uscite is None else uscite
    return r


def _feed(ev, market="1.%s", inplay=True, open_min=-30, status="OPEN", p1="A", p2="B"):
    """Riga di `safe_strategy_scan` sport tennis come la scrive lo scanner
    (`safe_strategy/service.py::build_rows`, ramo tennis)."""
    return {"event_id": ev, "sport": "tennis", "updated_at": _iso(ORA),
            "payload": {"event_name": "%s v %s" % (p1, p2), "p1": p1, "p2": p2,
                        "competition": "ATP Test",
                        "open_date": _iso(ORA + timedelta(minutes=open_min)),
                        "inplay": inplay, "mo_market_id": market % ev,
                        "mo_status": status, "odds": None, "sets": None,
                        "games": None, "media": None, "score_raw": None,
                        "mo_total_matched": 1000.0, "odds_ts_ms": 1,
                        "odds_pt_ms": 1, "bet_delay": 3}}


def _follow(ev, origine=None, status="STREAMING"):
    f = {"event_id": ev, "market_id": "1.%s" % ev, "competition_name": "ATP",
         "player1_name": "A", "player2_name": "B", "open_date": _iso(ORA),
         "status": status, "error_detail": None, "inplay": True, "score": None,
         "live_status": None, "created_at": _iso(ORA), "updated_at": _iso(ORA),
         "record": False}
    if origine is not None:
        f["origine"] = origine
    return f


def _control(ev, bot="tennis_flb", status="running", stats=None, uscite=None):
    r = {"event_id": ev, "bot_key": bot, "status": status, "dry_run": False,
         "stake": 3, "params": {}, "stats": stats, "error": None,
         "mode": "paper", "heartbeat_at": None, "started_at": None,
         "stopped_at": None, "updated_at": None}
    if uscite is not None:
        r["uscite_automatiche"] = uscite
    return r


class _Db:
    """Parla come `tennis_db` (stesse firme, stessi ritorni)."""

    def __init__(self, servizi, *, controls=None, follows=None, feed=None,
                 scanner_eta_s: Optional[float] = 2.0, now_status=None,
                 origine_assente=False):
        self._servizi = servizi
        self.controls: List[Dict[str, Any]] = list(controls or [])
        self.follows: List[Dict[str, Any]] = list(follows or [])
        self._feed = feed
        self._eta = scanner_eta_s
        self._now = dict(now_status or {})
        self._origine_assente = origine_assente
        self.armati: List[Dict[str, Any]] = []
        self.stati: List[tuple] = []
        self.servizio: List[Dict[str, Any]] = []
        self.follow_registrati: List[Dict[str, Any]] = []
        self.follow_status: List[tuple] = []
        self.uscite: List[tuple] = []
        self.letture_feed = 0

    # --- servizi
    def list_tennis_bot_services(self):
        return self._servizi

    def set_tennis_bot_service_state(self, bot_key, **kw):
        self.servizio.append({"bot_key": bot_key, **kw})
        return True

    # --- righe per partita
    def list_tennis_bot_controls(self, event_id=None, statuses=None):
        out = [dict(r) for r in self.controls]
        if event_id is not None:
            out = [r for r in out if r["event_id"] == event_id]
        if statuses:
            out = [r for r in out if r["status"] in statuses]
        return out

    def upsert_tennis_bot_control(self, row):
        self.armati.append(dict(row))

    def set_tennis_bot_status(self, event_id, bot_key, status, **kw):
        self.stati.append((event_id, bot_key, status))

    def set_tennis_bot_uscite(self, event_id, bot_key, automatiche):
        self.uscite.append((event_id, bot_key, automatiche))
        return True

    # --- follow
    def list_pending_tennis_follows(self):
        return [dict(f) for f in self.follows if f["status"] in ("PENDING", "STREAMING")]

    def register_tennis_follow(self, event_id, market_id, player1_name, player2_name,
                               open_date=None, competition_name=None, status="PENDING",
                               origine=None):
        if self._origine_assente and origine is not None:
            raise tennis_db.ColonnaAssente("tennis_live_follow.origine")
        self.follow_registrati.append({
            "event_id": event_id, "market_id": market_id, "player1_name": player1_name,
            "player2_name": player2_name, "open_date": open_date,
            "competition_name": competition_name, "status": status, "origine": origine})

    def set_tennis_follow_status(self, event_id, status, error_detail=None):
        self.follow_status.append((event_id, status))

    # --- feed unico
    def list_tennis_feed_rows(self):
        self.letture_feed += 1
        return None if self._feed is None else [dict(r) for r in self._feed]

    def scanner_heartbeat(self):
        if self._eta is None:
            return None
        return {"payload": {"cycle": 1},
                "updated_at": _iso(datetime.now(timezone.utc) - timedelta(seconds=self._eta))}

    def list_tennis_now_status(self, event_ids):
        return {e: self._now[e] for e in event_ids if e in self._now}


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    monkeypatch.setattr(S._GUARDIA_AVVIO, "attiva", False)
    S._ORIGINE_ASSENTE["dal"] = None
    monkeypatch.delenv(AM.ENV_TETTO, raising=False)
    yield
    S._ORIGINE_ASSENTE["dal"] = None


def _stats(db, bot="tennis_flb"):
    return [w for w in db.servizio if w["bot_key"] == bot][-1]["stats"]


# ===========================================================================
# 1. modulo puro
# ===========================================================================
def test_feed_filtra_e_ordina():
    righe = [
        _feed("30", inplay=False, open_min=10),
        _feed("20", inplay=True, open_min=-60),
        _feed("10", inplay=True, open_min=-30),
        _feed("40", status="CLOSED"),
        {**_feed("50"), "payload": {**_feed("50")["payload"], "mo_market_id": None}},
        {**_feed("60"), "sport": "calcio"},
        {"event_id": "70", "sport": "tennis", "payload": "rotto", "updated_at": None},
    ]
    evs = [p["event_id"] for p in AM.partite_dal_feed(righe)]
    # in gioco prima (per orario), poi l'imminente; chiusi/monchi/calcio fuori
    assert evs == ["20", "10", "30"]


@pytest.mark.parametrize("params,env,atteso", [
    ({}, {}, AM.TETTO_DEFAULT),
    ({}, {AM.ENV_TETTO: "3"}, 3),
    ({AM.CHIAVE_TETTO: 2}, {AM.ENV_TETTO: "3"}, 2),
    ({AM.CHIAVE_TETTO: 0}, {}, 0),
    ({AM.CHIAVE_TETTO: "boh"}, {AM.ENV_TETTO: ""}, AM.TETTO_DEFAULT),
    ({AM.CHIAVE_TETTO: -1}, {AM.ENV_TETTO: "4"}, 4),
    ({AM.CHIAVE_TETTO: 999}, {}, AM.TETTO_MASSIMO),
])
def test_tetto(params, env, atteso):
    assert AM.tetto_partite(params, env=env) == atteso


def test_params_per_strategia_toglie_solo_il_tetto():
    p = {"lay_max": 1.05, AM.CHIAVE_TETTO: 2}
    assert AM.params_per_strategia(p) == {"lay_max": 1.05}
    assert p[AM.CHIAVE_TETTO] == 2, "l'originale non si tocca"


def test_scegli_tiene_le_armate_e_non_supera_il_tetto():
    chiesti: List[str] = []

    def escludi(ev):
        chiesti.append(ev)
        return ev == "b"
    s = AM.scegli_partite(["a", "b", "c", "d", "e"], ["d"], escludi, 3)
    assert s == {"tengo": ["d"], "nuove": ["a", "c"]}
    assert chiesti == ["a", "b", "c"], "escludi solo sulle candidate che servono"
    # tetto abbassato sotto le armate: nessuna nuova, nessuna buttata fuori
    assert AM.scegli_partite(["a", "d"], ["a", "d"], lambda e: False, 1) == \
        {"tengo": ["a", "d"], "nuove": []}


@pytest.mark.parametrize("riga,atteso", [
    ({}, True), ({"uscite_automatiche": None}, True), ({"uscite_automatiche": "false"}, True),
    ({"uscite_automatiche": True}, True), ({"uscite_automatiche": False}, False),
])
def test_uscite_false_solo_se_scritto(riga, atteso):
    assert AM.uscite_automatiche_riga(riga) is atteso
    assert AM.uscite_automatiche_bot("tennis_scalper", riga) is True


def test_origine_auto_solo_se_scritta():
    assert AM.origine_follow({"origine": "auto"}) == "auto"
    assert AM.origine_follow({}) == "manuale"
    assert AM.origine_follow({"origine": "AUTOX"}) == "manuale"


# ===========================================================================
# 2. il ponte: dal feed all'armatura
# ===========================================================================
def test_acceso_senza_seguite_si_arma_dal_feed():
    """IL REPERTO: prima, con nessuna partita seguita, niente si armava."""
    db = _Db([_servizio()], feed=[_feed("1"), _feed("2"), _feed("3")])
    esito = S.riconcilia_interruttori(db)
    assert esito["armati"] == 3
    assert {r["event_id"] for r in db.armati} == {"1", "2", "3"}
    assert [f["origine"] for f in db.follow_registrati] == ["auto"] * 3
    assert db.follow_registrati[0]["market_id"] == "1.1"
    st = _stats(db)
    assert st["motivo_blocco"] is None
    assert st["partite_esposte"] == 3
    assert st["auto"]["armate_feed"] == 3 and st["auto"]["armate_a_mano"] == 0
    assert st["auto"]["in_attesa"] == 3
    assert st["auto"]["fonte"] == "safe_strategy_scan"


def test_il_tetto_si_rispetta_e_non_arriva_al_bot():
    db = _Db([_servizio(params={"lay_max": 1.05, AM.CHIAVE_TETTO: 2})],
             feed=[_feed(str(i), open_min=-i) for i in range(1, 9)])
    S.riconcilia_interruttori(db)
    # ordine: in gioco da piu' tempo prima (orario d'inizio crescente)
    assert [r["event_id"] for r in db.armati] == ["8", "7"]
    assert all(r["params"] == {"lay_max": 1.05} for r in db.armati)
    assert _stats(db)["tetto_partite"] == 2


def test_le_armate_restano_e_il_tetto_conta_anche_loro():
    db = _Db([_servizio(params={AM.CHIAVE_TETTO: 2})],
             controls=[_control("5")],
             follows=[_follow("5", origine="auto")],
             feed=[_feed("1", open_min=-90), _feed("5", open_min=-10), _feed("2", open_min=-80)])
    S.riconcilia_interruttori(db)
    assert [r["event_id"] for r in db.armati] == ["1"], "5 tenuta, 1 posto libero"


def test_seguite_a_mano_unite_al_feed():
    db = _Db([_servizio()], follows=[_follow("99", origine="manuale")],
             feed=[_feed("1"), _feed("2")])
    S.riconcilia_interruttori(db)
    assert {r["event_id"] for r in db.armati} == {"99", "1", "2"}
    assert "99" not in [f["event_id"] for f in db.follow_registrati], \
        "la seguita a mano non si riscrive come automatica"
    st = _stats(db)["auto"]
    assert st["armate_a_mano"] == 1 and st["armate_feed"] == 2


def test_follow_senza_colonna_origine_vale_manuale():
    """Migrazione non applicata: la riga non porta `origine` = scelta
    dell'utente, come prima."""
    db = _Db([_servizio()], follows=[_follow("99")], feed=[])
    S.riconcilia_interruttori(db)
    assert [r["event_id"] for r in db.armati] == ["99"]
    assert db.follow_status == [], "un follow manuale non si chiude mai"


@pytest.mark.parametrize("stato", ["done", "error"])
def test_nel_feed_ma_concluso_o_in_errore_non_si_riarma(stato):
    db = _Db([_servizio()], controls=[_control("1", status=stato)],
             follows=[_follow("1", origine="auto")], feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    assert db.armati == []


def test_nel_feed_ma_fermo_per_spegnimento_si_riarma():
    """`stopped` (interruttore spento e riacceso) si riarma: e' il gesto
    dell'utente. Contrario del test sopra."""
    db = _Db([_servizio()], controls=[_control("1", status="stopped")],
             follows=[_follow("1", origine="auto")], feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    assert [r["event_id"] for r in db.armati] == ["1"]


def test_chiusa_dall_utente_non_si_riarma_dal_feed():
    from Betfair.stream.tennis_live import chiusura_manuale as CM
    db = _Db([_servizio()],
             controls=[_control("1", status="stopped", stats={CM.CHIAVE_STATS: {"at": "x"}})],
             follows=[_follow("1", origine="auto")], feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    assert db.armati == []


def test_in_chiusura_non_si_riarma_nella_finestra_di_disarm():
    db = _Db([_servizio()], controls=[_control("1", status="stopping")],
             follows=[_follow("1", origine="auto")], feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    assert db.armati == []
    assert db.follow_status == [], "occupata da una riga in chiusura: follow vivo"


def test_sparita_dal_feed_non_si_riarma_e_il_follow_si_chiude():
    db = _Db([_servizio()], controls=[_control("1", status="stopped")],
             follows=[_follow("1", origine="auto")], feed=[_feed("2")])
    S.riconcilia_interruttori(db)
    assert [r["event_id"] for r in db.armati] == ["2"]
    assert ("1", "CLOSED") in db.follow_status


def test_sparita_a_mercato_chiuso_va_in_chiusura():
    db = _Db([_servizio()], controls=[_control("1")],
             follows=[_follow("1", origine="auto")], feed=[],
             now_status={"1": "CLOSED"})
    S.riconcilia_interruttori(db)
    assert ("1", "tennis_flb", "stopping") in db.stati
    assert db.follow_status == [], "si chiude al giro dopo, a righe ferme"


def test_sparita_a_mercato_APERTO_non_si_tocca():
    """Il contrario: uscita dal feed ma mercato non chiuso (scanner che
    rinfresca il catalogo) = nessuna chiusura imposta alla strategia."""
    db = _Db([_servizio()], controls=[_control("1")],
             follows=[_follow("1", origine="auto")], feed=[],
             now_status={"1": "OPEN"})
    S.riconcilia_interruttori(db)
    assert db.stati == [] and db.follow_status == []


def test_scanner_fermo_niente_dal_feed():
    db = _Db([_servizio()], feed=[_feed("1")], scanner_eta_s=120.0)
    S.riconcilia_interruttori(db)
    assert db.armati == []
    st = _stats(db)
    assert st["motivo_blocco"] == AM.MOTIVO_FEED_MUTO + AM.SUFFISSO_NESSUNA_SEGUITA
    assert st["auto"]["feed_letto"] is True and st["auto"]["feed_vivo"] is False
    assert st["auto"]["feed_eta_s"] >= 119


def test_scanner_fermo_non_chiude_niente_e_non_ferma_niente():
    db = _Db([_servizio()], controls=[_control("1")],
             follows=[_follow("1", origine="auto")], feed=[], scanner_eta_s=None,
             now_status={"1": "CLOSED"})
    S.riconcilia_interruttori(db)
    assert db.stati == [] and db.follow_status == []


def test_feed_vuoto_lo_dice():
    db = _Db([_servizio()], feed=[])
    S.riconcilia_interruttori(db)
    assert _stats(db)["motivo_blocco"] == \
        "feed tennis vuoto: nessuna partita in-play ora - e nessun evento seguito a mano"


def test_feed_non_letto_lo_dice():
    db = _Db([_servizio()], feed=None)
    S.riconcilia_interruttori(db)
    assert _stats(db)["motivo_blocco"].startswith(AM.MOTIVO_FEED_MUTO)


def test_armato_su_una_partita_nessun_motivo():
    db = _Db([_servizio()], feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    assert _stats(db)["motivo_blocco"] is None


def test_guardia_d_avvio_non_arma_e_non_legge_il_feed(monkeypatch):
    monkeypatch.setattr(S._GUARDIA_AVVIO, "attiva", True)
    monkeypatch.setattr(S._GUARDIA_AVVIO, "fatto", False)
    db = _Db([_servizio()], feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    assert db.armati == [] and db.letture_feed == 0
    assert _stats(db)["motivo_blocco"] == AM.MOTIVO_GUARDIA


def test_bot_spento_non_legge_il_feed_e_chiude_i_follow_auto_liberi():
    db = _Db([_servizio(status="stopped")], follows=[_follow("1", origine="auto")],
             feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    assert db.letture_feed == 0 and db.armati == []
    assert db.follow_status == [("1", "CLOSED")]
    assert "auto" not in _stats(db)


def test_tetto_zero_auto_spento_solo_a_mano():
    db = _Db([_servizio(params={AM.CHIAVE_TETTO: 0})], follows=[_follow("9")],
             feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    assert [r["event_id"] for r in db.armati] == ["9"]
    assert _stats(db)["auto"]["attivo"] is False


def test_migrazione_origine_assente_auto_spento_e_detto():
    db = _Db([_servizio()], feed=[_feed("1"), _feed("2")], origine_assente=True)
    S.riconcilia_interruttori(db)
    assert db.armati == [], "senza origine il follow automatico NON si scrive"
    assert _stats(db)["motivo_blocco"] == \
        AM.MOTIVO_ORIGINE_ASSENTE + AM.SUFFISSO_NESSUNA_SEGUITA
    # il giro dopo non riprova (una scrittura fallita ogni 15 s no)
    db2 = _Db([_servizio()], feed=[_feed("1")])
    S.riconcilia_interruttori(db2)
    assert db2.follow_registrati == [] and db2.armati == []


@pytest.mark.parametrize("mode,dry", [("paper", False), ("live", True)])
def test_paper_e_live_la_riga_dal_feed_e_identica_a_quella_a_mano(mode, dry):
    """Stessa modalita', stesso dry_run (in LIVE nasce in dry-run come la
    riga a mano: il reale resta un gesto per partita), mai ereditati."""
    db = _Db([_servizio(mode=mode)], follows=[_follow("9")], feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    per_ev = {r["event_id"]: r for r in db.armati}
    for ev in ("9", "1"):
        assert per_ev[ev]["mode"] == mode and per_ev[ev]["dry_run"] is dry
    assert _stats(db)["auto"]["live_in_dry_run"] is (mode == "live")


# ===========================================================================
# 3. uscite: dall'interruttore alla riga per partita
# ===========================================================================
def test_uscite_si_propagano_solo_dove_cambiano():
    db = _Db([_servizio(con_uscite=True, uscite=False)],
             controls=[_control("1", uscite=True), _control("2", uscite=False),
                       _control("3")],
             follows=[_follow("1", origine="auto"), _follow("2", origine="auto"),
                      _follow("3", origine="auto")],
             feed=[_feed("1"), _feed("2"), _feed("3")])
    S.riconcilia_interruttori(db)
    # "2" e' gia' manuale, "3" non ha la colonna (tabella per partita senza migrazione)
    assert db.uscite == [("1", "tennis_flb", False)]
    assert _stats(db)["auto"]["uscite_automatiche"] is False


def test_uscite_la_riga_nuova_nasce_col_valore_del_bot():
    db = _Db([_servizio(con_uscite=True, uscite=False)], feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    assert db.armati[0]["uscite_automatiche"] is False


def test_uscite_senza_colonna_nessuna_chiave_nessuna_scrittura():
    db = _Db([_servizio()], controls=[_control("1", uscite=True)],
             follows=[_follow("1", origine="auto")], feed=[_feed("1"), _feed("2")])
    S.riconcilia_interruttori(db)
    assert db.uscite == []
    assert "uscite_automatiche" not in db.armati[0]
    assert _stats(db)["auto"]["uscite_automatiche"] is None


def test_scalper_uscite_sempre_automatiche_nello_stato():
    db = _Db([_servizio(bot="tennis_scalper", con_uscite=True, uscite=False)],
             feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    st = _stats(db, "tennis_scalper")["auto"]
    assert st["uscite_automatiche"] is True and st["uscite_sempre_automatiche"] is True


def test_posizione_aperta_a_uscite_manuali_arriva_alla_control_room():
    db = _Db([_servizio(con_uscite=True, uscite=False)],
             controls=[_control("1", uscite=False,
                                stats={AM.CHIAVE_POSIZIONE_APERTA: "2026-09-25T10:00:00+00:00"}),
                       _control("2", uscite=False,
                                stats={AM.CHIAVE_POSIZIONE_APERTA: "2026-09-25T09:00:00+00:00"})],
             follows=[_follow("1", origine="auto"), _follow("2", origine="auto")],
             feed=[_feed("1"), _feed("2")])
    S.riconcilia_interruttori(db)
    st = _stats(db)["auto"]
    assert st["posizioni_aperte_manuali"] == 2
    assert st["posizione_aperta_dal"] == "2026-09-25T09:00:00+00:00"


def test_le_chiavi_di_stats_auto_sono_quelle_della_pagina():
    """`frontend/src/components/controlroom/tennisAuto.ts::leggiAutoTennis`
    legge ESATTAMENTE queste chiavi: una rinominata qui = una pagina cieca."""
    db = _Db([_servizio()], feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    assert set(_stats(db)["auto"]) == {
        "attivo", "tetto", "armate_feed", "armate_a_mano", "seguite_a_mano",
        "in_attesa", "feed_letto", "feed_vivo", "feed_partite", "feed_eta_s",
        "fonte", "origine_ok", "live_in_dry_run", "uscite_automatiche",
        "uscite_sempre_automatiche", "posizioni_aperte_manuali",
        "posizione_aperta_dal", "letto_at"}


# ===========================================================================
# 4. il runner: uscite a caldo e restart senza forzare
# ===========================================================================
class _Strat:
    def __init__(self, auto=True, ha_force_flat=True):
        self.uscite_automatiche = auto
        if ha_force_flat:
            self.force_flat = False
        self.stats = {"pnl": 0.0}


class _Sess:
    def __init__(self):
        self.hosted = {}
        self.order_mode = "PAPER"
        self.restart_deferred_since = None
        self.stopping_deadline = {}
        self._restart_wait_marked = set()

        class _E:
            def set(self_inner):
                raise AssertionError("restart NON doveva partire")
        self.restart_requested = _E()


@pytest.fixture
def runner_db(monkeypatch):
    scritte: List[tuple] = []

    class _TDb:
        def write_tennis_bot_activity(self, ev, bot, kind, payload):
            scritte.append((ev, bot, kind, payload))

        def list_tennis_bot_controls(self, event_id=None, statuses=None):
            return []

        def set_tennis_bot_wait_reason(self, *a, **k):
            pass
    monkeypatch.setattr(TR, "tennis_db", _TDb())
    return scritte


def test_uscite_a_caldo_dalla_riga_e_attivita_una_volta(monkeypatch, runner_db):
    s = _Strat(auto=True)
    sess = _Sess()
    monkeypatch.setattr(TR, "_strategy_is_flat", lambda fl, st: False)
    TR._aggiorna_uscite(None, sess, ("1", "tennis_flb"), s, {"uscite_automatiche": False})
    TR._aggiorna_uscite(None, sess, ("1", "tennis_flb"), s, {"uscite_automatiche": False})
    assert s.uscite_automatiche is False
    assert [k for (_e, _b, k, _p) in runner_db] == ["uscite"], "attivita' una volta sola"
    assert ("1", "tennis_flb") in TR.session_posizioni_aperte(sess)
    # torna automatiche: niente piu' avviso
    TR._aggiorna_uscite(None, sess, ("1", "tennis_flb"), s, {"uscite_automatiche": True})
    assert s.uscite_automatiche is True
    assert TR.session_posizioni_aperte(sess) == {}


def test_uscite_flat_nessun_avviso(monkeypatch, runner_db):
    s = _Strat(auto=False)
    sess = _Sess()
    monkeypatch.setattr(TR, "_strategy_is_flat", lambda fl, st: True)
    TR._aggiorna_uscite(None, sess, ("1", "tennis_flb"), s, {"uscite_automatiche": False})
    assert TR.session_posizioni_aperte(sess) == {}


def test_scalper_resta_automatico_anche_se_la_riga_dice_manuale(monkeypatch, runner_db):
    s = _Strat(auto=True)
    monkeypatch.setattr(TR, "_strategy_is_flat", lambda fl, st: True)
    TR._aggiorna_uscite(None, _Sess(), ("1", "tennis_scalper"), s, {"uscite_automatiche": False})
    assert s.uscite_automatiche is True and runner_db == []


def test_restart_senza_forzare_niente_force_flat_niente_restart(monkeypatch, runner_db):
    s = _Strat(auto=True)
    sess = _Sess()
    sess.restart_deferred_since = -1e9      # grazia "scaduta" da sempre
    monkeypatch.setattr(TR, "_hosted_not_flat", lambda fl, se: [("1", "tennis_scalper", s)])
    assert TR._request_restart(None, sess, "2 nuovi follow", forza=False) is False
    assert s.force_flat is False, "nessuna uscita imposta dall'arrivo di una partita"


def test_restart_forzato_come_prima_alza_force_flat(monkeypatch, runner_db):
    """Il contrario: con forza=True (default) il comportamento di prima."""
    s = _Strat(auto=True)
    sess = _Sess()
    monkeypatch.setattr(TR, "_hosted_not_flat", lambda fl, se: [("1", "tennis_scalper", s)])
    assert TR._request_restart(None, sess, "arm/disarm bot") is False
    assert s.force_flat is True


def test_paper_a_uscite_manuali_mai_restart_forzato(monkeypatch, runner_db):
    s = _Strat(auto=False, ha_force_flat=False)
    sess = _Sess()
    sess.restart_deferred_since = -1e9
    monkeypatch.setattr(TR, "_hosted_not_flat", lambda fl, se: [("1", "tennis_flb", s)])
    assert TR._request_restart(None, sess, "arm/disarm bot") is False
    kinds = [k for (_e, _b, k, _p) in runner_db]
    assert "restart_forced" not in kinds and "restart_blocked" in kinds


def test_paper_a_uscite_automatiche_restart_forzato_come_prima(monkeypatch, runner_db):
    """Il contrario: bot automatico in PAPER, grazia scaduta = restart forzato
    (la liveness di prima)."""
    s = _Strat(auto=True, ha_force_flat=False)
    sess = _Sess()
    sess.restart_deferred_since = -1e9
    partito: List[bool] = []

    class _E:
        def set(self_inner):
            partito.append(True)
    sess.restart_requested = _E()
    monkeypatch.setattr(TR, "_hosted_not_flat", lambda fl, se: [("1", "tennis_flb", s)])
    monkeypatch.setattr(TR, "_stop_framework", lambda fl: None)
    assert TR._request_restart(None, sess, "arm/disarm bot") is True
    assert partito == [True]


@pytest.mark.parametrize("origini,forza", [(["auto", "auto"], False),
                                           (["auto", "manuale"], True),
                                           ([None], True)])
def test_follow_worker_non_forza_per_partite_dal_feed(monkeypatch, origini, forza):
    chiamate: List[Dict[str, Any]] = []
    follows = [_follow(str(i), origine=o) for i, o in enumerate(origini)]

    class _TDb:
        def list_pending_tennis_follows(self):
            return follows
    monkeypatch.setattr(TR, "tennis_db", _TDb())

    def _finto(fl, se, reason, forza=True):
        chiamate.append({"reason": reason, "forza": forza})
        return False
    monkeypatch.setattr(TR, "_request_restart", _finto)

    class _S2:
        market_meta: Dict[str, Any] = {}
    TR.follow_worker({}, None, _S2())
    assert chiamate and chiamate[0]["forza"] is forza


@pytest.mark.parametrize("caso,forza", [("disarmo", False), ("armo", True)])
def test_bot_control_worker_forza_solo_se_c_e_da_armare(monkeypatch, caso, forza):
    """Un restart di sola PULIZIA (disarmo, nessuno da armare) non impone
    force_flat agli altri bot ne' azzera posizioni simulate; un restart che
    deve ARMARE un bot forza come sempre."""
    chiamate: List[Dict[str, Any]] = []

    class _TDb:
        def set_tennis_bot_status(self, *a, **k):
            pass

        def write_tennis_bot_activity(self, *a, **k):
            pass
    monkeypatch.setattr(TR, "tennis_db", _TDb())
    monkeypatch.setattr(TR, "_CANCELLO_BOT_CONTROL", None)
    monkeypatch.setattr(TR._cm, "avanza", lambda *a, **k: [])
    monkeypatch.setattr(TR._gt, "guardia_blocca", lambda *a, **k: False)
    monkeypatch.setattr(TR, "_strategy_is_flat", lambda fl, st: True)
    monkeypatch.setattr(TR, "_disable_strategy", lambda st: setattr(st, "_tennis_disabled", True))
    if caso == "disarmo":
        monkeypatch.setattr(TR, "_desired_controls", lambda ev: {})
        monkeypatch.setattr(TR, "_stopping_controls",
                            lambda ev: {"tennis_flb": _control(ev, status="stopping")})
    else:
        monkeypatch.setattr(TR, "_desired_controls",
                            lambda ev: {"tennis_pro": _control(ev, bot="tennis_pro",
                                                               status="requested")})
        monkeypatch.setattr(TR, "_stopping_controls", lambda ev: {})

    def _finto(fl, se, reason, forza=True):
        chiamate.append({"reason": reason, "forza": forza})
        return False
    monkeypatch.setattr(TR, "_request_restart", _finto)

    class _S3:
        market_meta = {"1": {}}
        hosted = {("1", "tennis_flb"): _Strat(ha_force_flat=False)} if caso == "disarmo" else {}
        stopping_deadline: Dict[tuple, float] = {}
    TR.bot_control_worker({}, None, _S3())
    assert chiamate and chiamate[0]["forza"] is forza


def test_instantiate_bot_porta_le_uscite_della_riga():
    from betfairlightweight.filters import streaming_market_data_filter
    df = streaming_market_data_filter(fields=list(TR.STREAM_FIELDS), ladder_levels=3)
    ctl = {"event_id": "1", "bot_key": "tennis_flb", "status": "requested", "stake": 2,
           "params": {}, "dry_run": True, "mode": "paper", "uscite_automatiche": False}
    s = TR._instantiate_bot("tennis_flb", ctl, "1.1", {}, None, df, "PAPER")
    assert s.uscite_automatiche is False
    ctl2 = dict(ctl)
    ctl2.pop("uscite_automatiche")
    assert TR._instantiate_bot("tennis_flb", ctl2, "1.1", {}, None, df, "PAPER") \
        .uscite_automatiche is True
    sc = TR._instantiate_bot("tennis_scalper", {**ctl, "bot_key": "tennis_scalper"},
                             "1.1", {}, None, df, "PAPER")
    assert sc.uscite_automatiche is True


# ===========================================================================
# 5. tennis_db: le colonne della migrazione 25/09 assenti non rompono niente
# ===========================================================================
class _Risposta:
    def __init__(self, data):
        self.data = data


class _Tabella:
    """Costruttore PostgREST finto: rifiuta le chiavi in `vietate` con il
    messaggio VERO di PostgREST (PGRST204)."""

    def __init__(self, sb, nome):
        self.sb, self.nome, self.payload = sb, nome, None

    def upsert(self, payload, on_conflict=None):
        self.payload = dict(payload)
        return self

    def execute(self):
        for k in self.sb.vietate:
            if self.payload and k in self.payload:
                raise Exception("{'code': 'PGRST204', 'message': \"Could not find the '%s' "
                                "column of '%s' in the schema cache\"}" % (k, self.nome))
        if self.sb.giu:
            raise Exception("503 PGRST002 database giu'")
        self.sb.scritte.append((self.nome, self.payload))
        return _Risposta([self.payload])


class _Sb:
    def __init__(self, vietate=(), giu=False):
        # LISTA, non insieme: l'ordine dice quale colonna PostgREST denuncia
        # per prima (un insieme lo renderebbe casuale fra un giro e l'altro)
        self.vietate, self.scritte, self.giu = list(vietate), [], giu

    def table(self, nome):
        return _Tabella(self, nome)


@pytest.fixture
def sb_finto(monkeypatch):
    def _fai(**kw):
        sb = _Sb(**kw)
        monkeypatch.setattr(tennis_db, "get_tennis_client", lambda: sb)
        monkeypatch.setattr(tennis_db, "_exec_retry", lambda b: b.execute())
        monkeypatch.setattr(tennis_db, "_uscite_assente_detto", False)
        monkeypatch.setattr(tennis_db, "_mode_assente_detto", False)
        return sb
    return _fai


def test_colonna_assente_riconosce_solo_la_sua_colonna():
    e = Exception("PGRST204 Could not find the 'origine' column of 'tennis_live_follow'")
    assert tennis_db.colonna_assente(e, "origine") is True
    assert tennis_db.colonna_assente(e, "mode") is False
    assert tennis_db.colonna_assente(Exception("timeout 'origine'"), "origine") is False


def test_follow_automatico_senza_colonna_non_si_scrive(sb_finto):
    sb = sb_finto(vietate={"origine"})
    with pytest.raises(tennis_db.ColonnaAssente):
        tennis_db.register_tennis_follow("1", "1.1", "A", "B", origine="auto")
    assert sb.scritte == []
    # il follow dell'utente (senza origine) si scrive come sempre
    tennis_db.register_tennis_follow("2", "1.2", "A", "B")
    assert sb.scritte[0][1]["event_id"] == "2" and "origine" not in sb.scritte[0][1]


def test_follow_automatico_con_colonna_porta_l_origine(sb_finto):
    sb = sb_finto()
    tennis_db.register_tennis_follow("1", "1.1", "A", "B", origine="auto")
    assert sb.scritte[0][1]["origine"] == "auto"


def test_riga_per_partita_senza_colonna_uscite_si_scrive_senza(sb_finto):
    sb = sb_finto(vietate={"uscite_automatiche"})
    tennis_db.upsert_tennis_bot_control({"event_id": "1", "bot_key": "tennis_flb",
                                         "status": "requested", "mode": "paper",
                                         "uscite_automatiche": False})
    assert len(sb.scritte) == 1
    assert "uscite_automatiche" not in sb.scritte[0][1]
    assert sb.scritte[0][1]["mode"] == "paper", "la modalita' non si perde"


@pytest.mark.parametrize("ordine", [["uscite_automatiche", "mode"],
                                    ["mode", "uscite_automatiche"]])
def test_riga_per_partita_senza_uscite_ne_mode(sb_finto, ordine):
    """Due migrazioni mancanti: qualunque colonna PostgREST denunci per prima,
    la riga si scrive (PAPER e uscite automatiche: fail-closed)."""
    sb = sb_finto(vietate=ordine)
    tennis_db.upsert_tennis_bot_control({"event_id": "1", "bot_key": "tennis_flb",
                                         "status": "requested", "mode": "paper",
                                         "uscite_automatiche": True})
    assert len(sb.scritte) == 1
    assert "mode" not in sb.scritte[0][1] and "uscite_automatiche" not in sb.scritte[0][1]


def test_riga_per_partita_con_colonna_porta_le_uscite(sb_finto):
    sb = sb_finto()
    tennis_db.upsert_tennis_bot_control({"event_id": "1", "bot_key": "tennis_flb",
                                         "mode": "paper", "uscite_automatiche": False})
    assert sb.scritte[0][1]["uscite_automatiche"] is False


def test_feed_si_legge_leggero_e_torna_nella_forma_di_sempre(monkeypatch):
    """Solo le chiavi che servono (niente score_raw ogni 15 s), e la riga
    ricomposta con `payload` dizionario: `partite_dal_feed` la legge uguale."""
    visti: Dict[str, Any] = {}

    class _Q:
        def select(self, s):
            visti["select"] = s
            return self

        def eq(self, k, v):
            visti["eq"] = (k, v)
            return self

        def execute(self):
            return _Risposta([{"event_id": "7", "sport": "tennis",
                               "updated_at": _iso(ORA), "p1": "A", "p2": "B",
                               "competition": "ATP", "open_date": _iso(ORA),
                               "inplay": True, "mo_market_id": "1.7",
                               "mo_status": "OPEN"}])

    class _SbF:
        def table(self, nome):
            visti["tabella"] = nome
            return _Q()
    monkeypatch.setattr(tennis_db, "get_tennis_client", lambda: _SbF())
    righe = tennis_db.list_tennis_feed_rows()
    assert visti["tabella"] == "safe_strategy_scan" and visti["eq"] == ("sport", "tennis")
    assert "score_raw" not in visti["select"] and "payload," not in visti["select"]
    assert "mo_market_id:payload->mo_market_id" in visti["select"]
    assert [p["event_id"] for p in AM.partite_dal_feed(righe)] == ["7"]
    assert AM.partite_dal_feed(righe)[0]["market_id"] == "1.7"


def test_altro_errore_risale_identico(sb_finto):
    sb_finto(giu=True)
    with pytest.raises(Exception, match="PGRST002"):
        tennis_db.upsert_tennis_bot_control({"event_id": "1", "bot_key": "tennis_flb",
                                             "uscite_automatiche": True})
    with pytest.raises(Exception, match="PGRST002"):
        tennis_db.register_tennis_follow("1", "1.1", "A", "B", origine="auto")
