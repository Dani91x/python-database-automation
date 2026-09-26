"""SERVIZIO SCALPER — supervisore locale (processo SEPARATO dal runner).

ARCHITETTURA: UN PROCESSO PER PARTITA. Il supervisore polla
``scalper_control`` e per ogni riga 'requested' spawna
``python -m Betfair.stream.scalper.scalper_session <event_id>`` (che ha il
PROPRIO login Betfair e la PROPRIA istanza flumine). Due framework flumine
nello stesso processo con client condiviso producevano WinError 10035 sui
socket dello stream (visto live il 02/07): mai piu' sessioni in-process.

Il supervisore inoltre:
  * marca 'error' le righe 'running' orfane (heartbeat fermo e nessun figlio);
  * gestisce 'stopping' per sessioni senza processo (righe zombie);
  * kill-switch globale: file ``STOP_SCALPER`` nella cwd;
  * 25/09 AUTO-MODE: con l'interruttore globale acceso
    (``scalper_service_control``, dalla Control Room) arma DA SOLO le partite
    calcio del FEED UNICO (``safe_strategy_scan``) entro un tetto, con
    ``origine='auto'``; spento o partita uscita dal feed = stop pulito delle
    sole sessioni automatiche (logica pura in ``auto_mode.py``);
  * 25/09 CANALE 47338 (``SCALPER_CANALE=1``, sola lettura): pubblica la riga
    dell'interruttore (``scalper_stato``) e le righe di sessione
    (``scalper_sessioni``) che ha gia' letto. Nessun processo nuovo.

Avvio:  python -m Betfair.stream.scalper.scalper_service
        (oppure avvia_scalper_service.bat)
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .. import avvio_app as AA

logger = logging.getLogger(__name__)

KILL_FILE = "STOP_SCALPER"
POLL_S = 3.0
ORPHAN_HEARTBEAT_S = 60.0
# scan automatico delle partite ADATTE (habitat_scan): ogni 30 min il
# supervisore scrive la classifica in scalper_activity (event_id='habitat');
# la dashboard la mostra nella card "Partite adatte oggi".
HABITAT_SCAN_INTERVAL_S = 1800.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- 25/09 AUTO-MODE ------------------------------------------------------
#: la riga dell'interruttore globale (migrations/scalper_auto_mode_2026-09-25.sql)
TABELLA_SERVIZIO = "scalper_service_control"
#: ogni quanto l'auto-mode rilegge il feed e decide (s). L'interruttore si
#: rilegge a OGNI giro del supervisore (3 s): un cambio fa partire subito il
#: giro dell'auto-mode, senza aspettare questi 15 s (stessa cadenza del ponte
#: tennis: il feed si legge dal database e l'IO e' la risorsa scarsa, 13/09).
AUTO_GIRO_S = 15.0


class OrigineAssente(Exception):
    """``scalper_control.origine`` non esiste: migrazione non applicata."""


class Db:
    def __init__(self) -> None:
        from db_client import get_supabase_client
        self.sb = get_supabase_client()

    def controls(self) -> List[Dict[str, Any]]:
        r = self.sb.table("scalper_control").select("*").in_(
            "status", ["requested", "arming", "running", "stopping"]).execute()
        return r.data or []

    def set_control(self, event_id: str, **fields: Any) -> None:
        fields["updated_at"] = _now_iso()
        self.sb.table("scalper_control").update(fields) \
            .eq("event_id", event_id).execute()

    def activity(self, event_id: str, kind: str, payload: Dict[str, Any]) -> None:
        """Append su ``scalper_activity`` (best-effort: il log non ferma niente)."""
        self.sb.table("scalper_activity").insert(
            {"event_id": event_id, "kind": kind, "payload": payload}).execute()

    # ---- 25/09 AUTO-MODE (migrations/scalper_auto_mode_2026-09-25.sql) ----
    def servizio(self) -> Optional[Dict[str, Any]]:
        """La riga dell'interruttore globale (``scalper_service_control``
        id=1). Solleva se la lettura fallisce (tabella assente compresa): il
        chiamante decide, mai "spento" dedotto da un errore."""
        r = self.sb.table(TABELLA_SERVIZIO).select("*").eq("id", 1).limit(1).execute()
        rows = r.data or []
        return rows[0] if rows else None

    def set_servizio(self, **fields: Any) -> Any:
        """Scrive la riga dell'interruttore e RITORNA la risposta (PostgREST
        porta la rappresentazione: e' quella che esce sul canale)."""
        fields["updated_at"] = _now_iso()
        return self.sb.table(TABELLA_SERVIZIO).update(fields).eq("id", 1).execute()

    def feed_calcio(self) -> Optional[List[Dict[str, Any]]]:
        """Le righe CALCIO del feed unico (``safe_strategy_scan``), solo le
        chiavi del payload che servono (``payload->chiave``: niente score_raw,
        quote, timeline). ``None`` = non letto (mai "feed vuoto")."""
        from .auto_mode import CHIAVI_FEED
        try:
            r = (self.sb.table("safe_strategy_scan")
                 .select(",".join(["event_id", "sport", "updated_at"]
                                  + ["%s:payload->%s" % (k, k) for k in CHIAVI_FEED]))
                 .eq("sport", "calcio").execute())
        except Exception as e:  # noqa: BLE001
            logger.warning("[scalper-svc] lettura feed calcio KO: %s", str(e)[:160])
            return None
        out: List[Dict[str, Any]] = []
        for row in (r.data or []):
            if isinstance(row, dict):
                out.append({"event_id": row.get("event_id"), "sport": row.get("sport"),
                            "updated_at": row.get("updated_at"),
                            "payload": {k: row.get(k) for k in CHIAVI_FEED}})
        return out

    def battito_scanner(self) -> Optional[Dict[str, Any]]:
        """``safe_strategy_status`` id='scanner': ``{payload, updated_at}``."""
        try:
            r = (self.sb.table("safe_strategy_status").select("updated_at")
                 .eq("id", "scanner").limit(1).execute())
        except Exception as e:  # noqa: BLE001
            logger.warning("[scalper-svc] battito scanner KO: %s", str(e)[:160])
            return None
        rows = r.data or []
        return rows[0] if rows else None

    def righe_control(self, event_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Le righe ``scalper_control`` di queste partite (qualunque stato),
        con ``origine``. Solleva ``OrigineAssente`` se la colonna non esiste
        (migrazione non applicata): senza ``origine`` una sessione automatica
        non si distingue da una dell'utente, quindi non si arma niente."""
        out: Dict[str, Dict[str, Any]] = {}
        for i in range(0, len(event_ids), 100):
            blocco = event_ids[i:i + 100]
            try:
                # 26/09: + il marcatore del freno (una riga fermata DAL FRENO
                # non e' "chiusa a mano": si riarma al rilascio)
                r = (self.sb.table("scalper_control")
                     .select("event_id,status,requested_at,dry_run,origine,"
                             "fermata_dal_freno:stats->fermata_dal_freno")
                     .in_("event_id", blocco).execute())
            except Exception as e:  # noqa: BLE001
                if "origine" in str(e):
                    raise OrigineAssente(str(e)[:200]) from e
                raise
            for row in r.data or []:
                out[str(row.get("event_id"))] = row
        return out

    def follows(self, event_ids: List[str]) -> Dict[str, str]:
        """event_id -> ``live_follow.status`` delle partite gia' seguite."""
        out: Dict[str, str] = {}
        for i in range(0, len(event_ids), 100):
            r = (self.sb.table("live_follow").select("event_id,status")
                 .in_("event_id", event_ids[i:i + 100]).execute())
            for row in r.data or []:
                out[str(row.get("event_id"))] = str(row.get("status") or "")
        return out

    def segui(self, p: Dict[str, Any]) -> None:
        """Il follow della partita del feed, SOLO se non esiste gia'
        (``ignore_duplicates``: un follow dell'utente, con fixture/watchlist/
        record, non si riscrive mai). ``scalper_control`` lo pretende (FK) e
        la sessione ci legge nomi e kickoff. Nessun ``record``: la partita
        non si registra per il Replay (opt-in dell'utente, 17/07)."""
        riga = {
            "event_id": p["event_id"], "home_name": p["home"], "away_name": p["away"],
            "open_date": p.get("open_date"), "league_name": p.get("competition"),
            "status": "PENDING", "updated_at": _now_iso(),
            # 26/09 (reperto e2e): il follow lo apre l'auto-mode, non l'utente.
            # Senza, il default della colonna ('manuale') lo mostrava seguito a
            # mano e l'auto-follow del runner non lo poteva gestire.
            "origine": "auto",
        }
        self.sb.table("live_follow").upsert(
            riga, on_conflict="event_id", ignore_duplicates=True).execute()

    def arma(self, event_id: str, campi: Dict[str, Any],
             vecchia: Optional[Dict[str, Any]]) -> Any:
        """La riga di sessione della partita del feed, ``origine='auto'``.
        Mai sopra una riga viva: nuova = insert che non sovrascrive (una card
        armata nello stesso istante vince); ferma = update SOLO se e' ancora
        la stessa riga ferma (stesso ``requested_at``)."""
        if vecchia is None:
            riga = {"event_id": event_id, **campi}
            return self.sb.table("scalper_control").upsert(
                riga, on_conflict="event_id", ignore_duplicates=True).execute()
        q = (self.sb.table("scalper_control").update(campi)
             .eq("event_id", event_id).eq("status", "stopped"))
        if vecchia.get("requested_at"):
            q = q.eq("requested_at", vecchia["requested_at"])
        return q.execute()

    def ferma_auto(self, event_id: str) -> Any:
        """Stop pulito di UNA sessione AUTOMATICA: 'stopping' (la sessione fa
        force-flat e attende il flat, lo stop di sempre; senza processo il
        giro del supervisore la chiude 'stopped'). Solo righe automatiche e
        attive: una sessione dell'utente non si tocca da qui."""
        return (self.sb.table("scalper_control")
                .update({"status": "stopping", "updated_at": _now_iso()})
                .eq("event_id", event_id).eq("origine", "auto")
                .in_("status", ["requested", "arming", "armed", "running"]).execute())

    def riga_control(self, event_id: str) -> Optional[Dict[str, Any]]:
        r = (self.sb.table("scalper_control").select("*")
             .eq("event_id", event_id).limit(1).execute())
        rows = r.data or []
        return rows[0] if rows else None


def _viva(row: Dict[str, Any]) -> bool:
    """True se dietro questa riga c'e' ancora una sessione che respira.

    Una sessione figlia SOPRAVVIVE al supervisore (``Popen``, nessun kill in
    cascata): se il suo heartbeat e' fresco sta operando davvero e non la si
    tocca da qui — e' esattamente la ragione per cui ``_stopping_zombie``
    esiste. Heartbeat assente o fermo da oltre ``ORPHAN_HEARTBEAT_S`` = nessuno
    dietro.
    """
    age = _hb_age_s(row)
    return age is not None and age <= ORPHAN_HEARTBEAT_S


def ferma_sessioni_al_nuovo_avvio(db: Any, boot_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """FASE A — all'avvio NUOVO dell'app nessuna sessione scalper riparte da sola.

    ``scalper_control`` persiste lo stato PER PARTITA: il supervisore, appena
    avviato, trova le righe 'requested' di ieri e ne spawna una sessione a testa
    (``status == "requested" and not alive`` nel loop qui sotto). Qui ogni riga
    attiva che non porta l'``APP_BOOT_ID`` di questo avvio — e dietro cui non
    respira piu' nessuno — viene portata a 'stopped' con un'attivita'
    ``avvio_app_bot_fermato``. I ``params``, lo stake e la modalita' della riga
    NON si toccano: si scrive solo lo stato.

    Le righe di QUESTO avvio e quelle con un heartbeat fresco restano come sono.
    """
    boot = AA.boot_id_ambiente() if boot_id is None else str(boot_id or "").strip()
    try:
        righe = db.controls()
    except Exception:  # noqa: BLE001 — mai bloccare l'avvio per una select
        logger.exception("[scalper-svc] controllo d'avvio: lettura KO")
        return []
    fermate: List[Dict[str, Any]] = []
    ora = _now_iso()
    for r in AA.righe_da_fermare(righe, boot):
        ev = str(r.get("event_id") or "")
        if not ev:
            continue
        if _viva(r):
            logger.warning("[scalper-svc] %s: sessione ancora viva (heartbeat fresco), "
                           "non la fermo dall'avvio: fermala dalla sua pagina.", ev)
            continue
        payload = {
            "bot": "scalper", "event_id": ev, "boot_id": boot,
            "boot_id_precedente": AA.boot_id_salvato(r.get("stats")),
            "status_precedente": str(r.get("status") or ""),
            "mode_precedente": r.get("mode"), "dry_run_precedente": r.get("dry_run"),
            "azzerato": True,
            "motivo": ("APP_BOOT_ID assente nell'ambiente: trattato come avvio nuovo"
                       if not boot else "avvio nuovo dell'app"),
            "effetto": "le sessioni le arma l'utente: la riga torna a 'stopped'.",
            "ts": ora,
        }
        try:
            db.set_control(ev, status="stopped", stopped_at=ora,
                           stats=AA.stats_timbrate(r.get("stats"), boot, ora),
                           error=("fermata all'avvio dell'app: l'attivazione e' un "
                                  "gesto dell'utente — riarma se serve"))
        except Exception:  # noqa: BLE001 — una riga rotta non ferma le altre
            logger.exception("[scalper-svc] stop d'avvio %s KO", ev)
            continue
        fermate.append(payload)
        try:
            db.activity(ev, AA.KIND_ATTIVITA, payload)
        except Exception:  # noqa: BLE001 — il log non ferma mai niente
            logger.warning("[scalper-svc] attivita' d'avvio %s non scritta", ev)
    if fermate:
        logger.warning("[scalper-svc] avvio dell'app: %d sessioni scalper fermate (%s)",
                       len(fermate), ", ".join(f["event_id"] for f in fermate[:6]))
    return fermate


# ===========================================================================
# 25/09 - AUTO-MODE: lo scalper lavora da solo sulle partite del FEED UNICO
# ===========================================================================
# La logica di decisione e' PURA in ``auto_mode.py``; qui ci sono solo le
# letture/scritture, nell'ordine in cui avvengono. Vedi la docstring di
# ``auto_mode`` per tetto, vita della sessione, esclusioni e paper/live.
class StatoAuto:
    """Memoria di PROCESSO dell'auto-mode (il supervisore e' uno solo: lock
    di singola istanza in ``main``)."""

    def __init__(self) -> None:
        self.guardia = AA.Guardia("scalper-auto")
        self.assenti_dal: Dict[str, float] = {}
        self.ultimo_giro: float = 0.0
        self.firma_servizio: Optional[str] = None
        self.firma_stats: Optional[str] = None
        self.servizio: Optional[Dict[str, Any]] = None
        self.servizio_letto = False
        #: 26/09 - ultimo freno visto: un cambio fa partire subito il giro
        self.freno: Optional[str] = None


def _firma_auto(auto: Dict[str, Any]) -> str:
    """Firma dei fatti dell'auto-mode SENZA le eta' (cambiano a ogni giro):
    la riga dell'interruttore si riscrive solo quando cambia qualcosa di vero."""
    import json as _json
    senza = {k: v for k, v in auto.items() if k not in ("giro_at",)}
    feed = dict(senza.get("feed") or {})
    feed.pop("eta_scanner_s", None)
    senza["feed"] = feed
    return _json.dumps(senza, sort_keys=True, default=str)


def _pubblica(topic_chiave: str, res_o_riga: Any, *, e_riga: bool = False) -> None:
    """Sul canale 47338 (se acceso). Mai un'eccezione verso il chiamante."""
    try:
        from .. import canale_bot as _cb
        if not _cb.acceso(_cb.ENV_SCALPER):
            return
        if e_riga:
            if isinstance(res_o_riga, dict):
                _cb.pubblica(_cb.TOPIC[topic_chiave], res_o_riga)
        else:
            _cb.pubblica_scritte(_cb.TOPIC[topic_chiave], res_o_riga)
    except Exception:  # noqa: BLE001 - mostrare non ferma mai il supervisore
        logger.debug("[scalper-svc] pubblicazione %s KO", topic_chiave, exc_info=True)


def giro_auto(db: Any, st: StatoAuto, righe_attive: List[Dict[str, Any]],
              ora: float, *, forza: bool = False,
              freno: Optional[str] = None) -> Dict[str, Any]:
    """UN giro dell'auto-mode. ``righe_attive`` = le righe che il supervisore
    ha appena letto (``Db.controls``: requested/arming/running/stopping).
    ``freno`` = il motivo del freno unico letto dal supervisore in QUESTO giro
    (26/09: a freno tirato non si arma niente e ``motivo_blocco`` lo dice).

    Ritorna i fatti del giro (anche per i test). Non solleva: ogni lettura
    fallita ferma il giro SENZA dedurre niente (mai "spento" da un errore,
    mai "partita sparita" da un feed non letto)."""
    from . import auto_mode as AM

    esito: Dict[str, Any] = {"letto": False, "armate": [], "fermate": [],
                             "motivo": None}
    # 1. l'interruttore, a ogni giro del supervisore (3 s)
    try:
        serv = db.servizio()
    except Exception as e:  # noqa: BLE001
        if not st.servizio_letto:
            logger.warning("[scalper-svc] interruttore auto-mode non leggibile "
                           "(migrazione scalper_auto_mode_2026-09-25.sql applicata?): %s",
                           str(e)[:160])
        st.servizio = None
        return esito
    if serv is None:
        st.servizio = None
        return esito
    st.servizio_letto = True
    esito["letto"] = True
    ora_iso = datetime.fromtimestamp(ora, tz=timezone.utc).isoformat()

    # 2. FASE A: all'avvio NUOVO dell'app l'interruttore torna spento (come
    #    ogni altro bot): mai un auto-mode ereditato da ieri, men che mai live.
    if st.guardia.attiva and not st.guardia.fatto:
        try:
            AA.ferma_al_nuovo_avvio(
                st.guardia, control=serv,
                set_control=lambda **c: _pubblica("scalper_stato", db.set_servizio(**c)),
                log=lambda kind, payload: db.activity("servizio", kind, payload),
                now_iso=ora_iso)
            serv = db.servizio() or serv
        except Exception as e:  # noqa: BLE001 - la guardia resta armata
            logger.warning("[scalper-svc] controllo d'avvio dell'auto-mode KO: %s",
                           str(e)[:160])
    firma = "%s|%s|%s" % (serv.get("updated_at"), serv.get("status"), serv.get("mode"))
    cambiato = firma != st.firma_servizio
    if cambiato:
        st.firma_servizio = firma
        _pubblica("scalper_stato", serv, e_riga=True)
    st.servizio = serv
    freno_cambiato = (freno or None) != st.freno
    st.freno = freno or None
    if not (cambiato or forza or freno_cambiato or ora - st.ultimo_giro >= AUTO_GIRO_S):
        return esito
    st.ultimo_giro = ora

    acceso = str(serv.get("status") or "") == "running"
    modalita = "live" if str(serv.get("mode") or "") == "live" else "paper"
    params = serv.get("params") if isinstance(serv.get("params"), dict) else {}
    tetto = AM.tetto_partite(params)
    bloccato = st.guardia.blocca_aperture
    auto_attive = [r for r in righe_attive
                   if AM.origine_riga(r) == AM.ORIGINE_AUTO
                   and str(r.get("status") or "") in AM.STATI_ATTIVI]

    # 3. SPENTO: le sessioni automatiche si fermano (stop pulito, a flat)
    if not acceso:
        for r in auto_attive:
            ev = str(r.get("event_id"))
            try:
                db.ferma_auto(ev)
                esito["fermate"].append(ev)
            except Exception as e:  # noqa: BLE001
                logger.warning("[scalper-svc] stop auto %s KO: %s", ev, str(e)[:160])
        st.assenti_dal.clear()
        _scrivi_stats(db, st, {"acceso": False, "modalita": modalita, "tetto": tetto,
                               "fermate": esito["fermate"], "giro_at": ora_iso})
        return esito

    # 4. IL FEED (solo acceso): conta SOLO con lo scanner vivo
    righe_feed = db.feed_calcio()
    hb = db.battito_scanner() if righe_feed is not None else None
    eta = AM.eta_s((hb or {}).get("updated_at"), ora) if hb else None
    feed_letto = righe_feed is not None
    feed_vivo = feed_letto and eta is not None and eta <= AM.SCANNER_VIVO_S
    partite = AM.partite_dal_feed(righe_feed) if feed_vivo else []
    nel_feed = {p["event_id"] for p in partite}

    # 5. PARTITA USCITA DAL FEED: stop pulito delle SOLE sessioni automatiche
    if feed_vivo:
        for ev in AM.da_fermare_per_feed(auto_attive, nel_feed, st.assenti_dal, ora):
            try:
                db.ferma_auto(ev)
                esito["fermate"].append(ev)
                st.assenti_dal.pop(ev, None)
            except Exception as e:  # noqa: BLE001
                logger.warning("[scalper-svc] stop auto %s KO: %s", ev, str(e)[:160])

    # 6. ARMAMENTO dal feed (mai con la guardia d'avvio armata)
    con_processo = AM.sessioni_con_processo(righe_attive)
    conflitto = AM.conflitto_modalita(con_processo, modalita)
    origine_ok = True
    armabili = 0
    posti = max(0, tetto - len(con_processo))
    # 26/09 (reperto e2e 09:42Z): a freno tirato NESSUNA riga nuova
    if not freno and not bloccato and not conflitto and tetto > 0 and posti > 0 and partite:
        vive = [p for p in partite if AM.ha_ancora_vita(p.get("open_date"), params, ora)]
        ids = [p["event_id"] for p in vive]
        per_ev = {p["event_id"]: p for p in vive}
        try:
            righe = db.righe_control(ids) if ids else {}
            follow = db.follows(ids) if ids else {}
        except OrigineAssente:
            origine_ok = False
            righe, follow = None, None
        except Exception as e:  # noqa: BLE001 - lettura KO: niente armamento
            logger.warning("[scalper-svc] letture per l'armamento KO: %s", str(e)[:160])
            righe, follow = None, None
        if righe is not None and follow is not None:
            acceso_dal = serv.get("started_at")

            def escludi(ev: str) -> bool:
                if str(follow.get(ev) or "").upper() in AM.FOLLOW_CHIUSI:
                    return True
                return AM.motivo_esclusione(righe.get(ev), acceso_dal) is not None

            armabili = sum(1 for ev in ids if not escludi(ev))
            scelta = AM.scegli_partite(ids, [], escludi, posti)
            for ev in scelta["nuove"]:
                p = per_ev[ev]
                campi = {
                    "status": "requested",
                    "mode": str(serv.get("strategia") or "maker"),
                    # D3 (25/09): SEMPRE dry-run alla nascita, anche in live
                    # (i soldi veri li mette l'utente per sessione)
                    "dry_run": AM.dry_run_alla_nascita(modalita),
                    "stake": serv.get("stake") if serv.get("stake") is not None else 25,
                    "params": AM.params_per_sessione(params),
                    "bias": None, "bias_meta": None, "error": None,
                    "stats": AA.stats_timbrate(None, st.guardia.boot_id)
                    if st.guardia.boot_id else None,
                    "requested_at": ora_iso, "started_at": None, "stopped_at": None,
                    "heartbeat_at": None, "updated_at": ora_iso,
                    "origine": AM.ORIGINE_AUTO,
                }
                try:
                    if ev not in follow:
                        db.segui(p)
                    res = db.arma(ev, campi, righe.get(ev))
                except Exception as e:  # noqa: BLE001 - una partita non ferma le altre
                    logger.warning("[scalper-svc] armamento auto %s KO: %s", ev, str(e)[:160])
                    continue
                if getattr(res, "data", None):
                    esito["armate"].append(ev)
                    _pubblica("scalper_sessioni", res)
                    try:
                        db.activity(ev, "auto_armata", {
                            "msg": "armata dal feed (auto-mode)", "modalita": modalita,
                            "dry_run": campi["dry_run"],
                            "strategia": campi["mode"], "stake": campi["stake"],
                            "home": p["home"], "away": p["away"],
                            "open_date": p.get("open_date"), "fonte": AM.FONTE_FEED})
                    except Exception:  # noqa: BLE001 - il log non ferma niente
                        pass
            if esito["armate"]:
                logger.info("[scalper-svc] auto-mode: armate %s (%s)",
                            ", ".join(esito["armate"]), modalita)

    sessioni = len(con_processo) + len(esito["armate"])
    motivo = AM.motivo_blocco(
        acceso=True, bloccato=bloccato, feed_letto=feed_letto, feed_vivo=feed_vivo,
        partite_feed=len(partite), origine_ok=origine_ok, tetto=tetto,
        sessioni=sessioni, conflitto=conflitto, armabili=armabili, freno=freno)
    esito["motivo"] = motivo
    pnl = 0.0
    vivi = 0
    for r in con_processo:
        s = r.get("stats") if isinstance(r.get("stats"), dict) else {}
        for k in ("pnl_locked", "sniper_pnl_locked", "theta_pnl_locked"):
            try:
                pnl += float(s.get(k) or 0.0)
            except (TypeError, ValueError):
                pass
        try:
            vivi += int(s.get("ordini_vivi") or 0)
        except (TypeError, ValueError):
            pass
    _scrivi_stats(db, st, {
        "acceso": True, "modalita": modalita, "tetto": tetto,
        # D3 (25/09): la Control Room lo dice («nascono in dry-run»)
        "nascono_in_dry_run": AM.dry_run_alla_nascita(modalita),
        "sessioni": sessioni,
        "sessioni_auto": len([r for r in con_processo
                              if AM.origine_riga(r) == AM.ORIGINE_AUTO]) + len(esito["armate"]),
        "armate_ora": esito["armate"], "fermate_ora": esito["fermate"],
        "motivo_blocco": motivo, "conflitto": conflitto,
        "freno": freno or None,
        "pnl_lordo_bot": round(pnl, 2), "ordini_vivi": vivi,
        "feed": {"letto": feed_letto, "vivo": feed_vivo, "partite": len(partite),
                 "eta_scanner_s": None if eta is None else round(eta, 1),
                 "fonte": AM.FONTE_FEED},
        "giro_at": ora_iso,
    })
    return esito


def _scrivi_stats(db: Any, st: StatoAuto, auto: Dict[str, Any]) -> None:
    """I fatti dell'auto-mode in ``stats.auto`` della riga dell'interruttore
    (write-on-change, timbrate con l'avvio dell'app), poi sul canale la riga
    RESTITUITA dalla scrittura."""
    firma = _firma_auto(auto)
    if firma == st.firma_stats:
        return
    serv = st.servizio or {}
    stats = dict(serv.get("stats") or {}) if isinstance(serv.get("stats"), dict) else {}
    stats["auto"] = auto
    try:
        res = db.set_servizio(stats=st.guardia.timbra(stats))
    except Exception as e:  # noqa: BLE001 - riprova al giro dopo
        logger.warning("[scalper-svc] stats auto-mode non scritte: %s", str(e)[:160])
        return
    st.firma_stats = firma
    righe = getattr(res, "data", None) or []
    if righe and isinstance(righe[0], dict):
        st.servizio = righe[0]
        st.firma_servizio = "%s|%s|%s" % (righe[0].get("updated_at"),
                                          righe[0].get("status"), righe[0].get("mode"))
    _pubblica("scalper_stato", res)


def _avvia_canale() -> None:
    """Il canale locale dello scalper (47338, SOLA LETTURA), nel supervisore
    che l'app avvia gia'. Non solleva MAI: senza canale tutto come prima."""
    from .. import canale_bot as _cb
    from .. import local_channel as _lc
    if not _cb.acceso(_cb.ENV_SCALPER):
        return
    try:
        porta = int((os.environ.get(_cb.ENV_PORTA_SCALPER) or "").strip()
                    or _cb.PORTA_SCALPER)
    except ValueError:
        porta = _cb.PORTA_SCALPER
    try:
        ch = _lc.start_channel(porta, "scalper", solo_lettura=True)
        if ch is None:
            logger.warning("[scalper-svc] canale locale NON attivo su %d: la pagina "
                           "continuera' a leggere dal database.", porta)
            return
        ch.set_hello(topic=[_cb.TOPIC["scalper_stato"], _cb.TOPIC["scalper_sessioni"]],
                     cadenza_battito_s=POLL_S)
        logger.info("[scalper-svc] canale locale attivo su 127.0.0.1:%d (sola lettura)", porta)
    except Exception as ex:  # noqa: BLE001 - il canale e' opzionale, sempre
        logger.warning("[scalper-svc] canale locale KO: %s", str(ex)[:160])


class PubblicaSessioni:
    """Le righe di sessione sul canale: quelle che il supervisore ha APPENA
    letto dal database (nessuna lettura in piu'), solo se cambiate; una
    sessione uscita dalle attive si rilegge UNA volta e si pubblica nel suo
    stato finale (la pagina la vede chiudersi subito). Con il canale spento
    non fa niente (nemmeno quella lettura)."""

    def __init__(self) -> None:
        self.firme: Dict[str, str] = {}

    def __call__(self, db: Any, righe: List[Dict[str, Any]]) -> None:
        from .. import canale_bot as _cb
        if not _cb.acceso(_cb.ENV_SCALPER):
            self.firme.clear()
            return
        viste: Dict[str, str] = {}
        for r in righe:
            ev = str(r.get("event_id") or "")
            if not ev:
                continue
            firma = "%s|%s|%s" % (r.get("updated_at"), r.get("heartbeat_at"), r.get("status"))
            viste[ev] = firma
            if self.firme.get(ev) != firma:
                _pubblica("scalper_sessioni", r, e_riga=True)
        for ev in [e for e in self.firme if e not in viste]:
            try:
                finale = db.riga_control(ev)
            except Exception:  # noqa: BLE001 - la pagina la vedra' al poll
                finale = None
            if finale:
                _pubblica("scalper_sessioni", finale, e_riga=True)
        self.firme = viste


def freno_supervisore() -> Optional[str]:
    """R3 (25/09): il freno unico visto dal supervisore (env + DB; il file
    ``STOP_SCALPER`` il supervisore lo gestisce gia' da se', uscendo).
    Stessa funzione della sessione: fail-closed."""
    from .scalper_session import motivo_freno

    return motivo_freno()


def sessione_da_avviare(row: Dict[str, Any], alive: bool,
                        freno: Optional[str]) -> bool:
    """Una riga 'requested' senza processo diventa una sessione SOLO a freno
    rilasciato. A freno tirato la riga resta com'e' ('requested'): nessun
    processo, nessun login, nessun ordine."""
    return str(row.get("status") or "") == "requested" and not alive and not freno


def _spawn(event_id: str) -> subprocess.Popen:
    repo_root = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", ".."))
    return subprocess.Popen(
        [sys.executable, "-m", "Betfair.stream.scalper.scalper_session",
         str(event_id)],
        cwd=repo_root,
    )


def _hb_age_s(row: Dict[str, Any]) -> Optional[float]:
    hb = row.get("heartbeat_at") or row.get("started_at")
    if not hb:
        return None
    try:
        t = datetime.fromisoformat(str(hb).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds()
    except ValueError:
        return None


def _stopping_zombie(row: Dict[str, Any]) -> bool:
    """True se una riga 'stopping' SENZA figlio registrato e' davvero zombie.

    FIX 15/07 (bug 2, dossier theta): dopo un RESTART del supervisore i figli
    vivi delle run precedenti NON sono in ``children`` — flippare subito
    'stopping'→'stopped' bruciava lo stop: la sessione viva (che polla lo
    status) non vedeva mai 'stopping' e restava armata SENZA force-flat.
    Zombie = heartbeat assente o fermo da oltre ORPHAN_HEARTBEAT_S; con un
    heartbeat fresco la sessione e' viva altrove e gestira' lo stop da sola.
    """
    age = _hb_age_s(row)
    return age is None or age > ORPHAN_HEARTBEAT_S


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    sys.path.insert(0, os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "..")))
    # Lock di SINGOLA ISTANZA (fix 17/07, parità con runner/tennis/omega):
    # due supervisori concorrenti vedrebbero la stessa riga 'requested' nello
    # stesso giro di poll e spawnerebbero DUE sessioni per lo stesso evento —
    # in live = ordini reali duplicati. Il socket va tenuto referenziato.
    from ..single_instance import acquire_single_instance_lock
    _lock = acquire_single_instance_lock(  # noqa: F841 - vita = processo
        int(os.getenv("SCALPER_SVC_LOCK_PORT", "47314")), "scalper-svc")
    db = Db()
    children: Dict[str, subprocess.Popen] = {}
    logger.info("[scalper-svc] supervisore avviato (un processo per partita). "
                "Kill-switch: file %s", KILL_FILE)
    # FASE A (16/09) — PRIMA del primo giro di poll: se l'app e' stata riaperta,
    # le righe 'requested' di ieri NON devono diventare sessioni nuove.
    ferma_sessioni_al_nuovo_avvio(db)
    # 25/09 - AUTO-MODE + CANALE 47338. La guardia d'avvio dell'interruttore
    # globale e' attiva SOLO qui (processo di servizio): finche' il controllo
    # d'avvio non riesce l'auto-mode non arma niente.
    _avvia_canale()
    stato_auto = StatoAuto()
    stato_auto.guardia.attiva = True
    pubblica_sessioni = PubblicaSessioni()
    #: R3 (25/09): ultimo motivo del freno gia' detto nel log (una riga al cambio)
    freno_detto: Dict[str, Optional[str]] = {"motivo": None}

    # ---- habitat scan periodico (thread, best-effort) ----
    def _habitat_loop() -> None:
        import json as _json
        trading = None
        while True:
            try:
                if trading is None:
                    from ..auth import build_client
                    trading = build_client(login=True)
                from .habitat_scan import scan
                rows = scan(hours=8.0, top=15, trading=trading)  # stessa sessione, mai re-login
                db.sb.table("scalper_activity").insert({
                    "event_id": "habitat", "kind": "habitat_scan",
                    "payload": _json.loads(_json.dumps(
                        {"rows": rows, "n": len(rows)}, default=str)),
                }).execute()
                logger.info("[scalper-svc] habitat scan: %d partite valutate",
                            len(rows))
            except Exception:  # noqa: BLE001 - lo scan non ferma il servizio
                logger.exception("[scalper-svc] habitat scan KO")
                trading = None  # ricostruisce il login al giro dopo
            time.sleep(HABITAT_SCAN_INTERVAL_S)

    threading.Thread(target=_habitat_loop, daemon=True,
                     name="habitat-scan").start()

    while True:
        if os.path.isfile(KILL_FILE):
            logger.warning("[scalper-svc] kill-switch: attendo la chiusura "
                           "flat delle sessioni figlie e esco")
            # i figli vedono il kill-file da soli (stessa cwd) e chiudono flat
            deadline = time.time() + 60
            while children and time.time() < deadline:
                for ev in [e for e, p in children.items() if p.poll() is not None]:
                    children.pop(ev, None)
                time.sleep(2)
            for p in children.values():
                p.terminate()
            return
        try:
            # figli terminati → rimuovi dal registro
            for ev in [e for e, p in children.items() if p.poll() is not None]:
                code = children.pop(ev).returncode
                logger.info("[scalper-svc] sessione %s terminata (exit=%s)",
                            ev, code)

            righe_attive = db.controls()
            # 25/09 - le righe appena lette escono sul canale (se acceso) e
            # l'auto-mode decide su QUESTE (nessuna lettura in piu')
            pubblica_sessioni(db, righe_attive)
            # R3 (25/09): il freno unico, UNA lettura per giro (cache ~2 s).
            # 26/09 (reperto e2e): letto PRIMA dell'auto-mode, che a freno
            # tirato non deve armare (prima armava e il freno fermava solo
            # l'avvio del processo).
            freno = freno_supervisore()
            try:
                giro_auto(db, stato_auto, righe_attive, time.time(), freno=freno)
            except Exception:  # noqa: BLE001 - l'auto-mode non ferma il supervisore
                logger.exception("[scalper-svc] giro auto-mode KO")
            if freno and freno_detto.get("motivo") != freno:
                logger.warning("[scalper-svc] FRENO TIRATO (%s): nessuna sessione nuova "
                               "si avvia; quelle vive chiudono flat da sole", freno)
            freno_detto["motivo"] = freno
            for row in righe_attive:
                ev = str(row["event_id"])
                status = row["status"]
                alive = ev in children and children[ev].poll() is None
                if sessione_da_avviare(row, alive, freno):
                    children[ev] = _spawn(ev)
                    logger.info("[scalper-svc] avviata sessione %s (pid=%s, "
                                "mode=%s dry=%s stake=%s)", ev,
                                children[ev].pid, row.get("mode"),
                                row.get("dry_run"), row.get("stake"))
                elif status == "stopping" and not alive:
                    # fix 15/07 (bug 2): chiudi la riga SOLO se davvero zombie
                    # (heartbeat fermo). Un figlio di un supervisore precedente
                    # (post-restart) e' vivo ma non registrato: deve vedere
                    # 'stopping' da solo e chiudere flat.
                    if _stopping_zombie(row):
                        db.set_control(ev, status="stopped",
                                       stopped_at=_now_iso())
                elif status in ("running", "arming") and not alive:
                    age = _hb_age_s(row)
                    if age is not None and age > ORPHAN_HEARTBEAT_S:
                        logger.warning("[scalper-svc] %s orfana (hb %.0fs, "
                                       "nessun figlio): error", ev, age)
                        db.set_control(ev, status="error",
                                       error="sessione orfana (processo morto)",
                                       stopped_at=_now_iso())
        except Exception:  # noqa: BLE001
            logger.exception("[scalper-svc] errore nel loop di polling")
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
