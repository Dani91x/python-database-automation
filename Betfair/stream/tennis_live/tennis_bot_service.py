"""tennis_bot_service.py — supervisore che tiene COERENTI i bot col runner tennis.

Il runner (``tennis_runner``) OSPITA i bot armati sullo stream unico e li
arma/disarma via ``bot_control_worker`` (restart del framework). Perché un bot possa
essere ospitato, però, il suo evento deve essere SEGUITO (riga in ``tennis_live_follow``,
così la subscription viene aperta). Questo servizio è il ponte:

  * poll di ``tennis_bot_control`` per righe ``requested``/``arming``/``armed``/``running``
    (bot da attivare) e ``stopping`` (da fermare);
  * per ogni evento con un bot attivo ma SENZA follow, registra il follow risolvendo
    market_id + giocatori da ``tennis_markets`` (nessun REST Betfair extra) → il runner
    lo prende in carico e aggancia il bot allo STESSO stream;
  * infine avvia/riavvia il runner (che fa l'hosting vero).

Scrive SOLO tabelle ``tennis_*``. Consistente con l'hosting in-process del runner.

Uso:
  python -m Betfair.stream.tennis_live.tennis_bot_service
  python -m Betfair.stream.tennis_live.tennis_bot_service --once   # solo ensure-follows
"""
from __future__ import annotations

import argparse
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .. import avvio_app as AA
from .. import canale_bot as _cb
from .. import local_channel as _lc
from .. import sveglia_canale as _SV
from ..single_instance import acquire_single_instance_lock
from . import auto_mode as _AM
from . import canale_bot_tennis as _CBT
from . import chiusura_manuale as _cm
from . import tennis_db

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ["requested", "arming", "armed", "running"]
ENSURE_POLL_SEC = 15.0
# Backoff quando il runner torna senza streammare nulla (nessun follow/mercato): evita un
# loop stretto di re-login Betfair (build_client(login=True) ad ogni giro → TOO_MANY_REQUESTS).
IDLE_BACKOFF_SEC = float(os.getenv("TENNIS_BOT_SVC_IDLE_BACKOFF_SEC", "30.0"))


#: guardia di PROCESSO del controllo d'avvio (vedi ``Betfair/stream/avvio_app.py``)
_GUARDIA_AVVIO = AA.Guardia("tennis")
#: esito dell'ULTIMA chiamata di ``ferma_bot_al_nuovo_avvio`` (T2, 24/09): la
#: ripresa del runner tennis lo legge per sapere se QUESTO giro e' riuscito
#: (``_GUARDIA_AVVIO.fatto`` puo' restare True da un giro precedente e non basta).
ESITO_ULTIMO_FERMO: Dict[str, Any] = {"riuscito": False}


def ferma_bot_al_nuovo_avvio(boot_id: str | None = None,
                             db: Any = tennis_db) -> List[Dict[str, Any]]:
    """FASE A — all'avvio NUOVO dell'app nessun bot tennis resta armato.

    Gli stati ``requested``/``arming``/``armed``/``running`` di
    ``tennis_bot_control`` sono PERSISTITI per evento: alla riapertura dell'app
    il ponte crea di nuovo il follow e il runner ri-arma il bot da solo. La
    pulizia degli orfani non basta — tocca solo le righe con heartbeat vecchio
    di 10 minuti, e una riga ``requested`` fresca non la guarda nemmeno.

    Qui ogni riga ATTIVA che non porta l'``APP_BOOT_ID`` di questo avvio viene
    portata a ``stopped`` con un'attivita' ``avvio_app_bot_fermato``. Le righe
    di QUESTO avvio (bot armato dall'utente poco fa, runner riavviato dal
    watchdog) non si toccano. I ``params`` e lo ``stake`` della riga restano
    identici: si scrive solo lo stato.

    Ritorna l'elenco delle righe fermate (dizionari {event_id, bot_key, ...}).
    """
    boot = AA.boot_id_ambiente() if boot_id is None else str(boot_id or "").strip()
    ESITO_ULTIMO_FERMO["riuscito"] = False
    try:
        righe = db.list_tennis_bot_controls(statuses=list(_ACTIVE_STATUSES))
    except Exception as e:  # noqa: BLE001 — mai bloccare l'avvio per una select
        logger.warning("[tennis-bot-svc] controllo d'avvio: lettura KO (%s): "
                       "riprovo al giro dopo.", str(e)[:160])
        return []
    fermate: List[Dict[str, Any]] = []
    # T2 (24/09): il controllo e' "fatto" SOLO se ogni riga da fermare e' stata
    # davvero scritta. Prima una scrittura fallita veniva saltata e la guardia si
    # disarmava lo stesso: il bot di ieri restava armato col controllo "riuscito".
    scritture_fallite = 0
    ora = tennis_db._now_iso()
    for r in AA.righe_da_fermare(righe, boot):
        ev, bot_key = str(r.get("event_id") or ""), str(r.get("bot_key") or "")
        if not ev or not bot_key:
            continue
        payload = {
            "bot": f"tennis:{bot_key}", "boot_id": boot,
            "boot_id_precedente": AA.boot_id_salvato(r.get("stats")),
            "status_precedente": str(r.get("status") or ""),
            "dry_run_precedente": r.get("dry_run"),
            "mode_precedente": r.get("mode"),
            "azzerato": True,
            "motivo": ("APP_BOOT_ID assente nell'ambiente: trattato come avvio nuovo"
                       if not boot else "avvio nuovo dell'app"),
            "effetto": ("i bot li arma l'utente: la riga torna a 'stopped', "
                        "mode='paper', dry_run=true."),
            "ts": ora,
        }
        try:
            # R2 (25/09, decisione dell'utente: «non devono mai partire in live
            # senza mio ordine»): oltre allo stop la riga torna PAPER e dry-run,
            # come Omega/Mike/Safe (``avvio_app.ferma_al_nuovo_avvio``).
            db.set_tennis_bot_status(
                ev, bot_key, "stopped", stopped=True, mode="paper", dry_run=True,
                stats=AA.stats_timbrate(r.get("stats"), boot, ora),
                error=("fermato all'avvio dell'app: l'armamento e' un gesto "
                       "dell'utente — riarma se serve"),
            )
        except Exception as e:  # noqa: BLE001 — una riga rotta non ferma le altre
            logger.warning("[tennis-bot-svc] stop d'avvio %s/%s KO: %s", ev, bot_key, str(e)[:160])
            scritture_fallite += 1
            continue
        fermate.append({"event_id": ev, "bot_key": bot_key, **payload})
        try:
            db.write_tennis_bot_activity(ev, bot_key, AA.KIND_ATTIVITA, payload)
        except Exception as e:  # noqa: BLE001 — il log non ferma mai niente
            logger.warning("[tennis-bot-svc] attivita' d'avvio %s/%s KO: %s",
                           ev, bot_key, str(e)[:160])
    _GUARDIA_AVVIO.boot_id = boot
    if scritture_fallite:
        logger.error("[tennis-bot-svc] controllo d'avvio INCOMPLETO: %d righe non "
                     "fermate - guardia d'avvio ancora armata, riprovo al giro dopo.",
                     scritture_fallite)
    else:
        _GUARDIA_AVVIO.fatto = True
        ESITO_ULTIMO_FERMO["riuscito"] = True
    if fermate:
        logger.warning("[tennis-bot-svc] avvio dell'app: %d bot tennis fermati (%s)",
                       len(fermate), ", ".join(f"{f['bot_key']}@{f['event_id']}" for f in fermate[:6]))
    return fermate


def _followed_event_ids() -> set:
    return {f["event_id"] for f in tennis_db.list_pending_tennis_follows()}


def _market_row_for(sb: Any, event_id: str) -> Dict[str, Any] | None:
    """Riga tennis_markets più recente dell'evento (per market_id + giocatori)."""
    try:
        resp = (
            sb.table("tennis_markets")
            .select("event_id,market_id,player1,player2,competition_name,open_date")
            .eq("event_id", event_id)
            .order("run_date", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("[tennis-bot-svc] tennis_markets KO %s: %s", event_id, e)
        return None
    rows = getattr(resp, "data", None) or []
    return rows[0] if rows else None


def ensure_follows_for_bots() -> List[str]:
    """Registra un follow per ogni evento con bot attivo ma non ancora seguito.

    Ritorna gli event_id per cui è stato creato un nuovo follow.
    """
    controls = tennis_db.list_tennis_bot_controls(statuses=_ACTIVE_STATUSES)
    if not controls:
        return []
    followed = _followed_event_ids()
    sb = tennis_db.get_tennis_client()
    created: List[str] = []
    for c in controls:
        event_id = c.get("event_id")
        if not event_id or event_id in followed:
            continue
        mrow = _market_row_for(sb, event_id)
        if not mrow or not mrow.get("market_id"):
            logger.warning("[tennis-bot-svc] bot su %s ma nessun market noto (aggiorna quote).", event_id)
            continue
        p1 = (mrow.get("player1") or {})
        p2 = (mrow.get("player2") or {})
        tennis_db.register_tennis_follow(
            event_id=event_id,
            market_id=mrow["market_id"],
            player1_name=str(p1.get("name") or "P1"),
            player2_name=str(p2.get("name") or "P2"),
            open_date=mrow.get("open_date"),
            competition_name=mrow.get("competition_name"),
            status="PENDING",
        )
        followed.add(event_id)
        created.append(event_id)
        logger.info("[tennis-bot-svc] follow creato per evento con bot: %s", event_id)
    return created


# ---------------------------------------------------------------------------
# IL PONTE: dall'INTERRUTTORE per bot all'ARMATURA per evento
# ---------------------------------------------------------------------------
# La Control Room accende UN BOT (`tennis_bot_service_control`: una riga per
# `bot_key`, con `status` + `mode` + `stake` + `params`). Il runner tennis, pero',
# arma per (evento, bot) su `tennis_bot_control`. Senza questo ponte le quattro
# righe restano «stato non letto» e i pulsanti della UI non fanno niente.
#
# Qui si traduce, e basta: nessun processo nuovo, nessuna tabella nuova,
# nessuna decisione di strategia. L'armatura per evento resta quella di sempre.
_BOT_KEYS = ("tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing")

# la cadenza la DICHIARA chi batte, non la indovina la pagina (review 15/09):
# finisce in `stats.cadenza_battito_s` e la Control Room giudica la freschezza
# del battito con QUESTO numero.
CADENZA_BATTITO_S = ENSURE_POLL_SEC


# ===========================================================================
# IL CANALE LOCALE DEI QUATTRO BOT TENNIS (18/09/2026, fase F3)
# ===========================================================================
# Porta 47337, accanto a 47331 (runner calcio), 47332 (runner tennis), 47333
# (Mike), 47334 (Omega), 47335 (Safe), 47336 (scanner). Era l'asimmetria piu'
# grossa fra i due sport: i quattro bot tennis non avevano nessun canale e la
# pagina li vedeva con un poll da 30 secondi.
#
# NESSUN PROCESSO NUOVO: il canale vive dentro questo servizio, che l'app
# desktop avvia gia' (``desktop/main.js:268``, ``--bridge-only``).
#
# E vive SOLO nel ramo ``--bridge-only``. In ``run()`` questo modulo ospita il
# runner tennis, che ha gia' il suo canale 47332: un processo ha un canale solo
# e ``start_channel`` su una porta diversa RIFIUTA (difetto D1, corretto in F1).
# Chiederlo li' vorrebbe dire far rifiutare il canale e scrivere un errore per
# niente.
#
# Il canale e' di SOLA LETTURA: mostrare non e' comandare. I comandi sul canale
# sono la fase F6, non questa.
def _avvia_canale() -> None:
    """Accende il canale locale dei bot tennis. Non solleva MAI: senza canale
    il servizio fa esattamente quello che fa oggi."""
    if not _cb.acceso(_cb.ENV_TENNIS_BOT):
        return
    try:
        porta = int((os.environ.get(_cb.ENV_PORTA_TENNIS_BOT) or "").strip()
                    or _cb.PORTA_TENNIS_BOT)
    except ValueError:
        porta = _cb.PORTA_TENNIS_BOT
    try:
        ch = _lc.start_channel(porta, "tennis-bot", solo_lettura=True)
        if ch is None:
            logger.warning("[tennis-bot-svc] canale locale NON attivo su %d (porta "
                           "occupata?): la pagina continuera' a leggere dal database.",
                           porta)
            return
        # la cadenza la DICHIARA chi batte, non la indovina la pagina
        # (difetto 33 del catalogo): chi consuma calcola da qui quando dirsi
        # "muto", invece di cablare una costante propria.
        ch.set_hello(topic=[_cb.TOPIC["tennis_bot_stato"],
                            _cb.TOPIC["tennis_bot_posizioni"],
                            _cb.TOPIC["tennis_bot_armamento"]],
                     cadenza_battito_s=CADENZA_BATTITO_S)
        logger.info("[tennis-bot-svc] canale locale attivo su 127.0.0.1:%d "
                    "(sola lettura; topic: %s, %s, %s)", porta,
                    _cb.TOPIC["tennis_bot_stato"], _cb.TOPIC["tennis_bot_posizioni"],
                    _cb.TOPIC["tennis_bot_armamento"])
    except Exception as ex:  # noqa: BLE001 - il canale e' opzionale, sempre
        logger.warning("[tennis-bot-svc] canale locale KO: %s", str(ex)[:160])


# ===========================================================================
# LA SVEGLIA DEL PONTE (18/09/2026, fasi F5 e F6) - interruttore SPENTO di serie
# ===========================================================================
# I QUATTRO BOT decidono dentro flumine, sul book: sono gia' al millisecondo e
# qui non si tocca niente di loro. Cio' che e' lento e' il PONTE: l'utente arma
# un bot dalla Control Room, la riga va su ``tennis_bot_control``, e questo
# ciclo se ne accorge al poll di 15 s. Con ``TENNIS_BOT_SVEGLIA_CANALE=1`` la
# dormita del ponte diventa svegliabile dal SOLO messaggio di sveglia che arriva
# sul canale 47337: nessun dato d'ordine sul canale, il comando resta la riga
# sul database, letta con le stesse funzioni e le stesse guardie di oggi.
# Il ponte NON ascolta lo scan: le quote non gli servono.
#
# Pavimento: 1 s. La sorgente e' UMANA (un clic su «avvia»/«ferma»/«approva»),
# non una macchina che pubblica quattro volte al secondo; ogni clic costa gia'
# oggi una scrittura sul database e una lettura del ponte al giro dopo.
MINIMO_SVEGLIA_S = 1.0
_SVEGLIA = _SV.Sveglia("tennis-bot")
_SVEGLIA_ATTIVA = False


def _su_sveglia_dal_canale(params: Any) -> bool:
    """F6: il SOLO messaggio che il canale 47337 puo' ricevere. Alza la sveglia
    e NIENT'ALTRO. Campi extra (prezzo, taglia, selezione): ignorati."""
    motivo = _SV.messaggio_di_sveglia(params)
    if motivo is None:
        return False
    _SVEGLIA.alza(motivo, minimo_s=MINIMO_SVEGLIA_S)
    return True


def _avvia_sveglia() -> None:
    """Aggancia la sveglia al canale del ponte. Non solleva MAI; a interruttore
    spento non cambia una sola istruzione (``stop.wait`` come oggi)."""
    global _SVEGLIA_ATTIVA
    if not _SV.acceso(_SV.ENV_TENNIS_SVEGLIA):
        return
    try:
        ch = _lc.get_channel()
        registra = getattr(ch, "set_sveglia", None) if ch is not None else None
        if callable(registra):
            registra(_su_sveglia_dal_canale)
            _SVEGLIA_ATTIVA = True
            logger.info("[tennis-bot-svc] sveglia dal canale ATTIVA: l'armamento "
                        "di un bot non aspetta piu' il poll di %.0fs.", ENSURE_POLL_SEC)
        else:
            logger.info("[tennis-bot-svc] il canale locale non espone 'set_sveglia': "
                        "la sveglia dalla UI non e' collegata (resta il poll di "
                        "%.0fs, come oggi).", ENSURE_POLL_SEC)
    except Exception as ex:  # noqa: BLE001 - la sveglia e' un'accelerazione
        logger.warning("[tennis-bot-svc] aggancio della sveglia KO: %s", str(ex)[:160])


def statistiche_sveglia() -> Optional[Dict[str, Any]]:
    """I contatori della sveglia, o ``None`` a interruttore spento."""
    return _SVEGLIA.statistiche() if _SVEGLIA_ATTIVA else None


def _dormi_o_sveglia(stop: threading.Event) -> None:
    """La dormita del ponte. A interruttore SPENTO e'
    ``stop.wait(ENSURE_POLL_SEC)``, la stessa identica istruzione di oggi."""
    if not _SVEGLIA_ATTIVA:
        stop.wait(ENSURE_POLL_SEC)
        return
    _SVEGLIA.attendi(ENSURE_POLL_SEC, MINIMO_SVEGLIA_S, interrompi=stop)


def _modalita_dichiarata(riga: Dict[str, Any]) -> str:
    """`paper` | `live`. MAI ereditata: una modalita' assente o storta vale
    `paper`. Ai soldi veri si arriva solo scrivendolo (regola del 14/09)."""
    m = str((riga or {}).get("mode") or "").strip().lower()
    return "live" if m == "live" else "paper"


def stato_desiderato(righe: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Dict[str, Any]]]:
    """Da cosa dicono gli interruttori a cosa il runner deve armare.

    `None` = interruttori NON LETTI: il chiamante non tocca niente. Dedurre
    «tutti fermi» da un DB muto disarmerebbe bot vivi.
    """
    if righe is None:
        return None
    out: Dict[str, Dict[str, Any]] = {}
    for r in righe or []:
        bot = str((r or {}).get("bot_key") or "")
        if bot not in _BOT_KEYS:
            continue
        acceso = str(r.get("status") or "").strip().lower() == "running"
        out[bot] = {
            "acceso": acceso,
            "mode": _modalita_dichiarata(r),
            "stake": r.get("stake"),
            "params": r.get("params") or {},
            "stats": r.get("stats"),
            # 25/09: None = colonna assente (migrazione non applicata): non si
            # propaga niente e il runner resta sulle uscite MANUALI (default
            # dal 25/09 sera, letto direttamente da ``auto_mode`` alla
            # costruzione della strategia).
            "uscite_automatiche": (_AM.uscite_automatiche_riga(r)
                                   if "uscite_automatiche" in r else None),
        }
    return out


def _stats_battito(desiderio: Dict[str, Any], eventi: int,
                   motivo_blocco: Optional[str],
                   auto: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Le `stats` che la Control Room legge, con i NOMI del frontend
    (`useControlRoom.ts`: `cadenza_battito_s`, `motivo_blocco`,
    `stop_ferma_solo_aperture`, `fermato_all_avvio_at`). Riscriverli con altre
    parole vorrebbe dire due verita' diverse — il difetto 33 del catalogo.

    25/09: ``auto`` = lo stato dell'AUTO-MODE (partite armate dal feed e a
    mano, feed letto/vivo con eta' e fonte, tetto, uscite) che la Control Room
    traduce in parole (``frontend/src/components/controlroom/tennisAuto.ts``).
    Assente a bot spento."""
    vecchie = desiderio.get("stats")
    out: Dict[str, Any] = dict(vecchie) if isinstance(vecchie, dict) else {}
    out["cadenza_battito_s"] = CADENZA_BATTITO_S
    out["partite_esposte"] = int(eventi)
    if auto is not None:
        out["auto"] = auto
        out["tetto_partite"] = auto.get("tetto")
    else:
        out.pop("auto", None)
    # lo STOP ferma le APERTURE, non le uscite: un bot disarmato continua a
    # proteggere la posizione aperta (`_disable_strategy` + finestra di flat).
    # Il pulsante deve dirlo, o promette una cosa che non succede.
    out["stop_ferma_solo_aperture"] = True
    out["motivo_blocco"] = motivo_blocco
    # F5: i contatori della sveglia compaiono SOLO a interruttore acceso: a
    # fase ferma lo stato non cambia di una chiave.
    sveglia = statistiche_sveglia()
    if sveglia is not None:
        out["sveglia"] = sveglia
    # 24/09: i contatori dell'inoltro delle righe d'ordine, SOLO se acceso
    inoltro = _CBT.statistiche_inoltro()
    if inoltro is not None:
        out["canale_inoltro"] = inoltro
    return out


def riconcilia_interruttori(db: Any = tennis_db) -> Dict[str, Any]:
    """UN giro del ponte. Torna un riepilogo (comodo per i test e per il log).

    * interruttore `running` -> la riga (evento, bot) viene ARMATA con la
      modalita', lo stake e i params dichiarati, su OGNI evento seguito A MANO
      e (25/09, AUTO-MODE) sulle partite del FEED UNICO fino al tetto del bot
      (``auto_mode``): il follow di una partita del feed lo crea il ponte con
      ``origine='auto'``;
    * interruttore fermo -> le righe attive di quel bot vanno a `stopping`: il
      runner le porta a `stopped` a posizione FLAT verificata (le protezioni
      girano, le aperture no);
    * una partita AUTOMATICA uscita dal feed non si riarma; se il suo mercato
      e' CHIUSO (``tennis_live_now.status``) le sue righe vanno a `stopping`;
      il suo follow si chiude quando nessuna riga la occupa piu';
    * in ogni caso si scrive `heartbeat_at` e le `stats` che la UI legge.
    """
    desiderato = stato_desiderato(db.list_tennis_bot_services())
    if desiderato is None:
        return {"letto": False, "armati": 0, "fermati": 0}
    follows = _follows_attivi(db)
    # le partite SEGUITE A MANO: quelle di sempre (l'origine assente vale
    # 'manuale'); le AUTOMATICHE le governa il feed, qui sotto.
    eventi = sorted({str(f["event_id"]) for f in follows
                     if _AM.origine_follow(f) == _AM.ORIGINE_MANUALE})
    seguite_a_mano = set(eventi)
    auto_seguite = {str(f["event_id"]) for f in follows
                    if _AM.origine_follow(f) == _AM.ORIGINE_AUTO}
    armati = fermati = 0
    # T2 (24/09): a guardia d'avvio ARMATA (controllo d'avvio non ancora
    # riuscito) il ponte NON arma niente; le fermate passano (riducono il rischio).
    bloccato = _GUARDIA_AVVIO.blocca_aperture
    # D3 (24/09) - "CHIUDI ORA": una (partita, bot) chiusa dall'utente porta
    # `stats.chiusura_manuale` sulla riga ferma e NON si riarma da qui, anche
    # con l'interruttore acceso: la riarma l'utente dalla scheda (la RPC
    # `tennis_bot_arm` azzera le stats). Non letto = non si arma niente in
    # questo giro (fail-closed); le fermate passano. Si legge SOLO la partita
    # che si sta per armare (filtrata per evento: niente storico intero ogni
    # 15 s), una volta per giro.
    fermi_letti: Dict[str, Optional[List[Dict[str, Any]]]] = {}

    def _fermi_su(ev: str) -> Optional[List[Dict[str, Any]]]:
        """Le righe FERME (stopped/error/done) della partita: una lettura per
        partita e per giro, condivisa fra i 4 bot. ``None`` = non lette."""
        if ev not in fermi_letti:
            try:
                fermi_letti[ev] = list(db.list_tennis_bot_controls(
                    ev, statuses=["stopped", "error", "done"]) or [])
            except Exception as e:  # noqa: BLE001 - una select KO non ferma il giro
                logger.warning("[tennis-bot-svc] righe chiuse dall'utente KO (%s): %s",
                               ev, str(e)[:160])
                fermi_letti[ev] = None
        return fermi_letti[ev]

    def _chiusi_su(ev: str) -> Optional[set]:
        righe = _fermi_su(ev)
        return None if righe is None else _cm.chiusi_dall_utente(righe)

    # ---- 25/09 AUTO-MODE: il feed si legge SOLO se serve (un bot acceso e
    # nessuna guardia); a bot tutti spenti niente letture in piu'.
    ora = time.time()
    qualcuno_acceso = any(d["acceso"] for d in desiderato.values())
    feed = (_leggi_feed(db, ora) if (qualcuno_acceso and not bloccato)
            else _feed_non_letto())
    candidate = [p["event_id"] for p in feed["partite"]]
    nel_feed = set(candidate)
    per_evento = {p["event_id"]: p for p in feed["partite"]}
    origine_ok = not _origine_assente_ora(ora)
    # le righe che OCCUPANO una partita (attive o in chiusura): servono a non
    # riarmare dentro la finestra di disarm e a non chiudere un follow vivo
    occupate: Optional[List[Dict[str, Any]]] = None
    if auto_seguite or feed["vivo"]:
        try:
            occupate = [r for r in (db.list_tennis_bot_controls(
                statuses=_STATI_OCCUPATI) or [])
                if str(r.get("status") or "") in _STATI_OCCUPATI]
        except Exception as e:  # noqa: BLE001
            logger.warning("[tennis-bot-svc] righe occupate KO: %s", str(e)[:160])
            occupate = None
    in_chiusura = {(str(r.get("event_id")), str(r.get("bot_key")))
                   for r in (occupate or []) if r.get("status") == "stopping"}
    bersagli: set = set()
    stato_mercato: Dict[str, Any] = {}

    def _mercato_chiuso(ev: str) -> bool:
        """Il mercato della partita e' CHIUSO secondo il runner? Una lettura
        per giro per tutte le partite automatiche uscite dal feed."""
        if "letto" not in stato_mercato:
            fuori = sorted(ev2 for ev2 in auto_seguite if ev2 not in nel_feed)
            fn = getattr(db, "list_tennis_now_status", None)
            stato_mercato["letto"] = fn(fuori) if callable(fn) else None
        m = stato_mercato["letto"]
        return m is not None and str(m.get(ev) or "").upper() == "CLOSED"

    for bot, d in desiderato.items():
        try:
            attive = {r.get("event_id"): r for r in
                      db.list_tennis_bot_controls(statuses=list(_ACTIVE_STATUSES))
                      if r.get("bot_key") == bot}
        except Exception as e:  # noqa: BLE001 - una select KO non ferma il giro
            logger.warning("[tennis-bot-svc] controls KO (%s): %s", bot, str(e)[:160])
            continue
        motivo = None
        tetto = _AM.tetto_partite(d["params"])
        params_bot = _AM.params_per_strategia(d["params"])
        nuove_armate: List[str] = []
        if d["acceso"] and not bloccato:
            for ev in eventi:
                if ev in attive:
                    continue
                chiusi_utente = _chiusi_su(ev)
                if chiusi_utente is None:
                    # non letto: questa partita non si arma in questo giro (ma
                    # NON si ferma niente: l'`else` e' per gli interruttori spenti)
                    motivo = ("righe chiuse dall'utente non lette: la partita %s "
                              "non si arma in questo giro" % ev)
                    continue
                if (str(ev), bot) in chiusi_utente:
                    continue        # chiuso dall'utente: lo riarma lui
                db.upsert_tennis_bot_control(_riga_armatura(ev, bot, d, params_bot))
                nuove_armate.append(ev)
                armati += 1
            # ---- AUTO-MODE: le partite del FEED UNICO, fino al tetto
            if origine_ok and tetto > 0 and feed["vivo"] and occupate is not None:
                def _escludi(ev: str, _bot: str = bot) -> bool:
                    if ev in seguite_a_mano or (ev, _bot) in in_chiusura:
                        return True     # a mano: l'ha gia' vista il giro sopra
                    righe = _fermi_su(ev)
                    if righe is None:
                        return True     # non lette: fail-closed, niente armamento
                    if (ev, _bot) in _cm.chiusi_dall_utente(righe):
                        return True     # chiusa dall'utente: la riarma lui
                    return any(str(r.get("bot_key")) == _bot
                               and str(r.get("status")) in _STATI_NON_RIARMABILI_AUTO
                               for r in righe)
                gia = [ev for ev in attive if str(ev) not in seguite_a_mano]
                scelta = _AM.scegli_partite(candidate, gia, _escludi, tetto)
                bersagli.update(scelta["tengo"])
                for ev in scelta["nuove"]:
                    if ev not in auto_seguite:
                        esito = _segui_dal_feed(db, per_evento[ev])
                        if esito == "origine_assente":
                            origine_ok = False
                            _segna_origine_assente(ora)
                            break
                        if esito != "ok":
                            continue
                        auto_seguite.add(ev)
                    bersagli.add(ev)
                    db.upsert_tennis_bot_control(_riga_armatura(ev, bot, d, params_bot))
                    nuove_armate.append(ev)
                    armati += 1
            # ---- USCITE: l'interruttore del bot sulle righe per partita (solo
            # se la colonna c'e' su entrambe le tabelle: altrimenti automatiche)
            _propaga_uscite(db, bot, d, attive)
            # ---- partite AUTOMATICHE uscite dal feed a mercato CHIUSO: in
            # chiusura (il runner le porta a stopped a flat verificato)
            if feed["vivo"]:
                for ev in list(attive):
                    ev_s = str(ev)
                    if ev_s in auto_seguite and ev_s not in nel_feed \
                            and ev_s not in seguite_a_mano and _mercato_chiuso(ev_s):
                        db.set_tennis_bot_status(ev_s, bot, "stopping")
                        attive.pop(ev, None)
                        fermati += 1
        else:
            for ev in attive:
                db.set_tennis_bot_status(ev, bot, "stopping")
                fermati += 1
            attive = {}         # in chiusura: non sono piu' partite armate
        auto_stato = None
        if d["acceso"]:
            armate_evs = {str(e) for e in attive} | set(nuove_armate)
            a_mano = len([e for e in armate_evs if e in seguite_a_mano])
            in_attesa = len(set(nuove_armate)) + len(
                [r for r in attive.values()
                 if str(r.get("status") or "") in ("requested", "arming")])
            if motivo is None:
                motivo = _AM.motivo_blocco(
                    acceso=True, bloccato=bloccato, feed_letto=feed["letto"],
                    feed_vivo=feed["vivo"], partite_feed=len(candidate),
                    origine_ok=origine_ok, tetto=tetto, armate=len(armate_evs),
                    seguite=len(seguite_a_mano))
            auto_stato = _stato_auto(
                d, bot, tetto, feed, origine_ok, ora,
                armate_feed=len(armate_evs) - a_mano, armate_a_mano=a_mano,
                seguite_a_mano=len(seguite_a_mano), in_attesa=in_attesa,
                righe_attive=list(attive.values()))
            esposte = len(armate_evs)
        else:
            esposte = 0
        db.set_tennis_bot_service_state(
            bot, heartbeat=True,
            stats=_stats_battito(d, esposte, motivo, auto_stato))
    # ---- i follow AUTOMATICI che non servono piu' si chiudono: nessuna riga
    # li occupa (attiva o in chiusura) e nessun bot li vuole in questo giro.
    # Senza questo la lista del runner crescerebbe per tutto il giorno (una
    # riga `tennis_live_now` ogni 2 s per partita). Occupate NON lette = non si
    # chiude niente.
    chiusi_follow = 0
    if occupate is not None:
        occupati = {str(r.get("event_id")) for r in occupate}
        for ev in sorted(auto_seguite - bersagli - occupati - seguite_a_mano):
            try:
                db.set_tennis_follow_status(ev, "CLOSED")
                chiusi_follow += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("[tennis-bot-svc] chiusura follow auto %s KO: %s",
                               ev, str(e)[:160])
    return {"letto": True, "armati": armati, "fermati": fermati,
            "eventi": len(eventi), "feed": len(candidate),
            "follow_auto_chiusi": chiusi_follow}


# ===========================================================================
# 25/09 - AUTO-MODE: gli attrezzi del giro (letture/scritture del ponte)
# ===========================================================================
_STATI_OCCUPATI = list(_ACTIVE_STATUSES) + ["stopping"]
#: una partita automatica con una riga cosi' per QUEL bot non si riarma dal
#: feed: `done` = missione compiuta, `error` = uscita non verificata (va vista
#: da una persona). `stopped` si riarma (l'utente ha spento e riacceso).
_STATI_NON_RIARMABILI_AUTO = ("done", "error")
#: stessa soglia con cui il feed dice «scanner vivo»
#: (``scores/scan_feed.SCANNER_ALIVE_MAX_AGE_SEC``)
_SCANNER_VIVO_S = 30.0
FONTE_FEED = "safe_strategy_scan"
#: migrazione dell'origine assente: si riprova ogni tanto (l'utente la applica
#: ad app accesa), non a ogni giro (una scrittura fallita ogni 15 s).
_RIPROVA_ORIGINE_S = 600.0
_ORIGINE_ASSENTE: Dict[str, Optional[float]] = {"dal": None}


def _origine_assente_ora(ora: float) -> bool:
    dal = _ORIGINE_ASSENTE.get("dal")
    return dal is not None and (ora - dal) < _RIPROVA_ORIGINE_S


def _segna_origine_assente(ora: float) -> None:
    if _ORIGINE_ASSENTE.get("dal") is None:
        logger.error("[tennis-bot-svc] AUTO-MODE spento: tennis_live_follow.origine non "
                     "esiste (migrazione tennis_uscite_manuali_2026-09-25.sql NON "
                     "applicata). I bot si armano solo sulle partite seguite a mano.")
    _ORIGINE_ASSENTE["dal"] = ora


def _follows_attivi(db: Any) -> List[Dict[str, Any]]:
    """I follow PENDING/STREAMING con la loro ``origine``. Un ``db`` che non
    sa leggerli (i finti di prima del 25/09) ripiega su ``_followed_event_ids``:
    tutte manuali, cioe' il ponte di prima."""
    fn = getattr(db, "list_pending_tennis_follows", None)
    if callable(fn):
        return [f for f in (fn() or []) if isinstance(f, dict) and f.get("event_id")]
    return [{"event_id": ev} for ev in _followed_event_ids()]


def _feed_non_letto() -> Dict[str, Any]:
    return {"letto": False, "vivo": False, "partite": [], "eta_scanner_s": None,
            "righe": 0}


def _leggi_feed(db: Any, ora: float) -> Dict[str, Any]:
    """La lista partite dal FEED UNICO + il battito dello scanner. Il feed
    conta SOLO se lo scanner e' vivo (battito entro 30 s): righe presenti con
    lo scanner fermo sono l'ultimo stato di ieri, non partite di adesso."""
    esito = _feed_non_letto()
    leggi = getattr(db, "list_tennis_feed_rows", None)
    if not callable(leggi):
        return esito
    try:
        righe = leggi()
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-bot-svc] feed tennis KO: %s", str(e)[:160])
        righe = None
    if righe is None:
        return esito
    esito["letto"] = True
    esito["righe"] = len(righe)
    battito = getattr(db, "scanner_heartbeat", None)
    hb = None
    if callable(battito):
        try:
            hb = battito()
        except Exception as e:  # noqa: BLE001
            logger.warning("[tennis-bot-svc] battito scanner KO: %s", str(e)[:160])
    eta = _AM.eta_s((hb or {}).get("updated_at"), ora) if hb else None
    esito["eta_scanner_s"] = None if eta is None else round(eta, 1)
    esito["vivo"] = eta is not None and eta <= _SCANNER_VIVO_S
    if esito["vivo"]:
        esito["partite"] = _AM.partite_dal_feed(righe)
    return esito


def _segui_dal_feed(db: Any, p: Dict[str, Any]) -> str:
    """Il follow di una partita del feed, marcato ``origine='auto'``, con i
    metadati del feed (nessuna lettura di ``tennis_markets``, nessun REST).
    ``ok`` | ``origine_assente`` | ``errore``."""
    try:
        db.register_tennis_follow(
            event_id=p["event_id"], market_id=p["market_id"],
            player1_name=p["p1"], player2_name=p["p2"],
            open_date=p.get("open_date"), competition_name=p.get("competition"),
            status="PENDING", origine=_AM.ORIGINE_AUTO)
    except tennis_db.ColonnaAssente:
        return "origine_assente"
    except Exception as e:  # noqa: BLE001 - una partita KO non ferma le altre
        logger.warning("[tennis-bot-svc] follow dal feed %s KO: %s",
                       p.get("event_id"), str(e)[:160])
        return "errore"
    logger.info("[tennis-bot-svc] AUTO-MODE: follow dal feed per %s (%s - %s)",
                p["event_id"], p["p1"], p["p2"])
    return "ok"


def _riga_armatura(ev: str, bot: str, d: Dict[str, Any],
                   params_bot: Dict[str, Any]) -> Dict[str, Any]:
    """La riga per partita, IDENTICA per le partite seguite a mano e per
    quelle del feed: stessa modalita', stesso dry_run, stesso stake, stessi
    params (senza la sola chiave del tetto, che e' del ponte)."""
    riga = {
        "event_id": ev, "bot_key": bot, "status": "requested",
        # T1 (24/09): la modalita' del bot viaggia ESPLICITA sulla riga
        # per partita. Il runner la legge (guardie_tennis.modalita_riga)
        # e simula SEMPRE quando e' 'paper', qualunque sia la sua
        # modalita' di processo: prima la riga non la portava e un bot
        # PAPER su runner LIVE andava sul client REALE.
        "mode": d["mode"],
        # `dry_run` e' il cancello del BOT su `market.place_order`. In
        # PAPER e' FALSO: gli ordini passano dal blotter SIMULATO (client
        # paper_trade=True, mai Betfair) e si vedono sul ladder. In LIVE
        # resta True finche' l'utente non lo toglie a mano per partita
        # (il doppio gesto: il reale vuole mode='live' E dry_run=False).
        "dry_run": d["mode"] == "live",
        "stake": d["stake"] if d["stake"] is not None else 2,
        "params": params_bot,
    }
    if d.get("uscite_automatiche") is not None:
        riga["uscite_automatiche"] = bool(d["uscite_automatiche"])
    return riga


def _propaga_uscite(db: Any, bot: str, d: Dict[str, Any],
                    attive: Dict[Any, Dict[str, Any]]) -> int:
    """L'interruttore «uscite automatiche» del bot sulle righe per partita,
    SOLO dove e' diverso (una scrittura al cambio, non a ogni giro). Righe
    senza la colonna = migrazione non applicata su ``tennis_bot_control``:
    non si tocca niente (il runner resta manuale, il default dal 25/09 sera)."""
    voluto = d.get("uscite_automatiche")
    fn = getattr(db, "set_tennis_bot_uscite", None)
    if voluto is None or not callable(fn):
        return 0
    scritte = 0
    for ev, r in attive.items():
        if "uscite_automatiche" not in (r or {}):
            continue
        if _AM.uscite_automatiche_riga(r) == bool(voluto):
            continue
        if fn(str(ev), bot, bool(voluto)):
            scritte += 1
    return scritte


def _stato_auto(d: Dict[str, Any], bot: str, tetto: int, feed: Dict[str, Any],
                origine_ok: bool, ora: float, *, armate_feed: int,
                armate_a_mano: int, seguite_a_mano: int, in_attesa: int,
                righe_attive: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Lo stato dell'auto-mode di UN bot, con i nomi che la Control Room legge
    (``tennisAuto.ts``). Solo fatti: le parole le sceglie la pagina."""
    aperte = []
    for r in righe_attive:
        st = r.get("stats") if isinstance(r.get("stats"), dict) else {}
        dal = st.get(_AM.CHIAVE_POSIZIONE_APERTA)
        if dal:
            aperte.append(str(dal))
    uscite = d.get("uscite_automatiche")
    return {
        "attivo": bool(origine_ok and tetto > 0),
        "tetto": int(tetto),
        "armate_feed": int(max(0, armate_feed)),
        "armate_a_mano": int(armate_a_mano),
        "seguite_a_mano": int(seguite_a_mano),
        "in_attesa": int(in_attesa),
        "feed_letto": bool(feed["letto"]),
        "feed_vivo": bool(feed["vivo"]),
        "feed_partite": len(feed["partite"]),
        "feed_eta_s": feed["eta_scanner_s"],
        "fonte": FONTE_FEED,
        "origine_ok": bool(origine_ok),
        "live_in_dry_run": d.get("mode") == "live",
        # None = colonna assente: la pagina non offre l'interruttore
        "uscite_automatiche": (None if uscite is None
                               else _AM.uscite_automatiche_bot(bot, d)),
        "uscite_sempre_automatiche": bot in _AM.BOT_USCITE_SEMPRE_AUTOMATICHE,
        "posizioni_aperte_manuali": len(aperte),
        "posizione_aperta_dal": min(aperte) if aperte else None,
        "letto_at": datetime.fromtimestamp(ora, tz=timezone.utc).isoformat(),
    }


def ferma_interruttori_al_nuovo_avvio(boot_id: str | None = None,
                                      db: Any = tennis_db) -> List[str]:
    """All'avvio NUOVO dell'app nessun bot tennis opera — anche dal suo
    INTERRUTTORE, non solo dalle righe per evento.

    `tennis_bot_service_control.status` e' persistito: senza questo, riaprire
    l'app farebbe ripartire da sola una riga lasciata `running` ieri sera. Un
    riavvio dal watchdog (stesso `APP_BOOT_ID`) non tocca niente.
    Torna i `bot_key` fermati.
    """
    boot = AA.boot_id_ambiente() if boot_id is None else str(boot_id or "").strip()
    ESITO_ULTIMO_FERMO_INTERRUTTORI["riuscito"] = False
    righe = db.list_tennis_bot_services()
    if righe is None:
        # NON letto. E' un esito riuscito SOLO se la tabella non esiste (migrazione
        # dell'interruttore non applicata: non c'e' niente da fermare). Un DB giu'
        # resta un controllo NON fatto.
        ESITO_ULTIMO_FERMO_INTERRUTTORI["riuscito"] = bool(
            getattr(db, "_servizio_assente_detto", False))
        return []
    ora = tennis_db._now_iso()
    fermati: List[str] = []
    fallite = 0
    for r in righe or []:
        bot = str((r or {}).get("bot_key") or "")
        if bot not in _BOT_KEYS:
            continue
        acceso = str(r.get("status") or "").strip().lower() in ("running", "stopping")
        # R2 (25/09): anche un interruttore gia' fermo ma rimasto in LIVE torna
        # PAPER, altrimenti il prossimo «avvia» ripartirebbe in soldi veri.
        in_live = str(r.get("mode") or "").strip().lower() == "live"
        if not (acceso or in_live):
            continue
        if AA.stesso_avvio(r.get("stats"), boot):
            continue          # stesso avvio (watchdog): non si tocca
        stats = AA.stats_timbrate(r.get("stats"), boot, ora)
        # il frontend legge `stats.fermato_all_avvio_at` e lo mostra: e' il
        # modo in cui l'utente capisce perche' il bot che aveva acceso e' fermo
        stats["fermato_all_avvio_at"] = ora
        # R2 (25/09): stopped E mode='paper', come gli altri bot: in live ci si
        # torna solo con un gesto dell'utente dalla Control Room.
        if db.set_tennis_bot_service_state(bot, status="stopped", stopped=True,
                                           stats=stats, mode="paper"):
            fermati.append(bot)
            logger.info("[tennis-bot-svc] avvio NUOVO dell'app: interruttore "
                        "%s riportato a 'stopped' e 'paper' (lo accende l'utente).", bot)
        else:
            fallite += 1
    ESITO_ULTIMO_FERMO_INTERRUTTORI["riuscito"] = fallite == 0
    return fermati


#: esito dell'ULTIMA chiamata di ``ferma_interruttori_al_nuovo_avvio`` (T2, 24/09)
ESITO_ULTIMO_FERMO_INTERRUTTORI: Dict[str, Any] = {"riuscito": False}


def ripresa_ponte(db: Any = tennis_db) -> bool:
    """T2 (24/09) - il controllo d'avvio del PONTE, gemello della ripresa del
    runner: righe per partita di un avvio vecchio fermate E interruttori di un
    avvio vecchio fermati. Solo se ENTRAMBI riescono la guardia si disarma e il
    ponte torna ad armare bot; altrimenti resta armata e si riprova al giro dopo.

    Prima del 24/09 la modalita' ``--bridge-only`` (quella dell'app desktop)
    fermava le righe per partita ma NON gli interruttori: un interruttore
    lasciato 'running' ieri sera ri-armava i bot al primo giro del ponte."""
    ferma_bot_al_nuovo_avvio(db=db)
    ok_bot = bool(ESITO_ULTIMO_FERMO.get("riuscito"))
    ferma_interruttori_al_nuovo_avvio(db=db)
    ok_int = bool(ESITO_ULTIMO_FERMO_INTERRUTTORI.get("riuscito"))
    _GUARDIA_AVVIO.fatto = ok_bot and ok_int
    if not _GUARDIA_AVVIO.fatto:
        logger.error("[tennis-bot-svc] controllo d'avvio del ponte NON riuscito "
                     "(righe per partita: %s, interruttori: %s): nessun bot si arma, "
                     "riprovo al giro dopo.", "ok" if ok_bot else "KO",
                     "ok" if ok_int else "KO")
    return _GUARDIA_AVVIO.fatto


def arma_guardia_ponte() -> None:
    """La guardia del ponte si arma all'avvio del SERVIZIO (non nei test ne' nei
    replay, che chiamano le funzioni direttamente)."""
    _GUARDIA_AVVIO.attiva = True
    _GUARDIA_AVVIO.fatto = False
    _GUARDIA_AVVIO.boot_id = AA.boot_id_ambiente()


def _ensure_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        if _GUARDIA_AVVIO.blocca_aperture:
            # T2: controllo d'avvio non ancora riuscito -> si riprova; finche'
            # fallisce niente follow nuovi (riporterebbero sullo stream i bot di
            # un avvio vecchio). Il giro del ponte gira lo stesso: NON arma
            # (``riconcilia_interruttori`` lo sa) ma ferma e batte il cuore.
            try:
                ripresa_ponte()
            except Exception as e:  # noqa: BLE001 - la guardia resta armata
                logger.warning("[tennis-bot-svc] ripresa del ponte KO: %s", e)
        if not _GUARDIA_AVVIO.blocca_aperture:
            try:
                ensure_follows_for_bots()
            except Exception as e:  # noqa: BLE001
                logger.warning("[tennis-bot-svc] ensure loop KO: %s", e)
        try:
            riconcilia_interruttori()
        except Exception as e:  # noqa: BLE001 - il ponte non ferma il servizio
            logger.warning("[tennis-bot-svc] ponte interruttori KO: %s", e)
        # F5: stessa dormita di oggi, svegliabile a interruttore acceso.
        _dormi_o_sveglia(stop)


def run() -> None:
    """Avvia il ponte follow + il runner tennis (che ospita i bot).

    FIX CRITICAL doppio runner (2026-07-10): l'app desktop avvia SIA il watchdog
    (→ ``tennis_runner``) SIA questo servizio, e ``setup_and_run()`` ospita i bot
    in-process → due framework con GLI STESSI bot = stake DOPPIO. Prima di
    ospitare si acquisisce il lock di SINGOLA ISTANZA del runner (stessa porta di
    ``tennis_runner``): se è occupato, un runner è già attivo e ospita lui i bot
    → in questo ciclo si fa SOLO ensure_follows_for_bots() e si riprova al giro
    dopo. Se acquisito, il lock resta vivo per tutta la durata dell'hosting.
    """
    from .tennis_runner import setup_and_run

    # FASE A — PRIMA di creare i follow: un bot armato ieri non deve tornare
    # sullo stream solo perche' l'app e' stata riaperta; e anche gli
    # INTERRUTTORI: una riga lasciata `running` ieri sera farebbe ripartire il
    # bot da sola alla riapertura dell'app. T2 (24/09): guardia d'avvio ARMATA,
    # disarmata solo se entrambi i fermi riescono (``ripresa_ponte``).
    arma_guardia_ponte()
    ripresa_ponte()
    if not _GUARDIA_AVVIO.blocca_aperture:
        ensure_follows_for_bots()
    riconcilia_interruttori()
    lock_port = int(os.getenv("TENNIS_RUNNER_LOCK_PORT", "47312"))
    try:
        lock = acquire_single_instance_lock(lock_port, "tennis-runner")
    except SystemExit:
        logger.info(
            "[tennis-bot-svc] runner tennis GIÀ attivo (lock 127.0.0.1:%d): "
            "hosting saltato in questo ciclo (solo ensure-follows), riprovo al giro dopo.",
            lock_port,
        )
        return
    stop = threading.Event()
    t = threading.Thread(target=_ensure_loop, args=(stop,), daemon=True, name="tennis-ensure-follows")
    t.start()
    try:
        setup_and_run()
    finally:
        stop.set()
        try:
            lock.close()  # rilascia il lock: il runner watchdog può subentrare
        except OSError:
            pass


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Supervisore bot tennis (follow + hosting)")
    ap.add_argument("--once", action="store_true", help="solo ensure-follows, poi esci")
    ap.add_argument("--bridge-only", action="store_true",
                    help="solo il ponte follow in loop (nessun hosting: il runner sotto watchdog ospita i bot)")
    args = ap.parse_args()
    if args.once:
        created = ensure_follows_for_bots()
        logger.info("[tennis-bot-svc] follow creati: %s", created)
        return
    if args.bridge_only:
        # MODALITÀ APP DESKTOP (audit 09/09): l'app avvia GIÀ il runner tennis
        # sotto watchdog. Questo processo faceva la CORSA al lock 47312: se
        # vinceva, il figlio del watchdog usciva per lock e il watchdog si
        # fermava PER SEMPRE (tennis senza sentinella); se perdeva, girava a
        # vuoto. Qui solo il ponte follow, nessun hosting, nessun login Betfair.
        logger.info("[tennis-bot-svc] modalità ponte: ensure-follows ogni %.0fs, nessun hosting.",
                    ENSURE_POLL_SEC)
        # FASE A — anche il ponte lo fa, e per primo: e' lui che rimette sullo
        # stream gli eventi dei bot ancora attivi. T2 (24/09): con la guardia
        # d'avvio ARMATA e anche gli INTERRUTTORI (prima qui mancava: un
        # interruttore lasciato 'running' ieri ri-armava i bot al primo giro).
        arma_guardia_ponte()
        ripresa_ponte()
        # F3: il canale 47337 vive QUI e solo qui (vedi ``_avvia_canale``).
        _avvia_canale()
        # 24/09: le righe d'ordine dei 4 bot le scrive il RUNNER (47332): il
        # ponte le legge come LETTORE e le inoltra identiche sul 47337
        # (``canale_bot_tennis.InoltroPosizioni``). Nessuna lettura al database.
        _CBT.avvia_inoltro_nel_ponte()
        # F5/F6: la sveglia del ponte, agganciata a quello stesso canale.
        _avvia_sveglia()
        stop = threading.Event()
        try:
            _ensure_loop(stop)
        except KeyboardInterrupt:
            stop.set()
        return
    while True:
        try:
            run()
        except KeyboardInterrupt:
            logger.info("[tennis-bot-svc] interrotto.")
            break
        except Exception as e:  # noqa: BLE001
            logger.exception("[tennis-bot-svc] runner caduto: %s — riparto tra 10s", e)
            time.sleep(10.0)
            continue
        # run() è tornato SENZA streammare (nessun follow/mercato): backoff prima di ritentare
        # per non re-loggarsi a Betfair in un loop stretto (#11).
        logger.info("[tennis-bot-svc] runner tornato senza stream: attendo %ss.", IDLE_BACKOFF_SEC)
        time.sleep(IDLE_BACKOFF_SEC)


if __name__ == "__main__":
    _main()
