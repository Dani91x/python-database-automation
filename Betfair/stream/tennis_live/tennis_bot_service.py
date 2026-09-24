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
from typing import Any, Dict, List, Optional

from .. import avvio_app as AA
from .. import canale_bot as _cb
from .. import local_channel as _lc
from .. import sveglia_canale as _SV
from ..single_instance import acquire_single_instance_lock
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
            "azzerato": True,
            "motivo": ("APP_BOOT_ID assente nell'ambiente: trattato come avvio nuovo"
                       if not boot else "avvio nuovo dell'app"),
            "effetto": "i bot li arma l'utente: la riga torna a 'stopped'.",
            "ts": ora,
        }
        try:
            db.set_tennis_bot_status(
                ev, bot_key, "stopped", stopped=True,
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
        }
    return out


def _stats_battito(desiderio: Dict[str, Any], eventi: int,
                   motivo_blocco: Optional[str]) -> Dict[str, Any]:
    """Le `stats` che la Control Room legge, con i NOMI del frontend
    (`useControlRoom.ts`: `cadenza_battito_s`, `motivo_blocco`,
    `stop_ferma_solo_aperture`, `fermato_all_avvio_at`). Riscriverli con altre
    parole vorrebbe dire due verita' diverse — il difetto 33 del catalogo."""
    vecchie = desiderio.get("stats")
    out: Dict[str, Any] = dict(vecchie) if isinstance(vecchie, dict) else {}
    out["cadenza_battito_s"] = CADENZA_BATTITO_S
    out["partite_esposte"] = int(eventi)
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
      modalita', lo stake e i params dichiarati, su OGNI evento seguito;
    * interruttore fermo -> le righe attive di quel bot vanno a `stopping`: il
      runner le porta a `stopped` a posizione FLAT verificata (le protezioni
      girano, le aperture no);
    * in ogni caso si scrive `heartbeat_at` e le `stats` che la UI legge.
    """
    desiderato = stato_desiderato(db.list_tennis_bot_services())
    if desiderato is None:
        return {"letto": False, "armati": 0, "fermati": 0}
    eventi = sorted(_followed_event_ids())
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
    fermi_letti: Dict[str, Optional[set]] = {}

    def _chiusi_su(ev: str) -> Optional[set]:
        if ev not in fermi_letti:
            try:
                fermi_letti[ev] = _cm.chiusi_dall_utente(db.list_tennis_bot_controls(
                    ev, statuses=["stopped", "error", "done"]))
            except Exception as e:  # noqa: BLE001 - una select KO non ferma il giro
                logger.warning("[tennis-bot-svc] righe chiuse dall'utente KO (%s): %s",
                               ev, str(e)[:160])
                fermi_letti[ev] = None
        return fermi_letti[ev]

    for bot, d in desiderato.items():
        try:
            attive = {r.get("event_id"): r for r in
                      db.list_tennis_bot_controls(statuses=list(_ACTIVE_STATUSES))
                      if r.get("bot_key") == bot}
        except Exception as e:  # noqa: BLE001 - una select KO non ferma il giro
            logger.warning("[tennis-bot-svc] controls KO (%s): %s", bot, str(e)[:160])
            continue
        motivo = None
        if d["acceso"] and not eventi:
            motivo = "acceso, ma nessun evento tennis seguito in questo momento"
        if d["acceso"] and bloccato:
            motivo = ("guardia d'avvio: il controllo d'avvio dell'app non e' ancora "
                      "riuscito, nessun bot si arma finche' non riesce")
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
                db.upsert_tennis_bot_control({
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
                    "params": d["params"],
                })
                armati += 1
        else:
            for ev in attive:
                db.set_tennis_bot_status(ev, bot, "stopping")
                fermati += 1
        db.set_tennis_bot_service_state(
            bot, heartbeat=True,
            stats=_stats_battito(d, len(eventi) if d["acceso"] else 0, motivo))
    return {"letto": True, "armati": armati, "fermati": fermati,
            "eventi": len(eventi)}


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
        if str(r.get("status") or "").strip().lower() not in ("running", "stopping"):
            continue
        if AA.stesso_avvio(r.get("stats"), boot):
            continue          # stesso avvio (watchdog): non si tocca
        stats = AA.stats_timbrate(r.get("stats"), boot, ora)
        # il frontend legge `stats.fermato_all_avvio_at` e lo mostra: e' il
        # modo in cui l'utente capisce perche' il bot che aveva acceso e' fermo
        stats["fermato_all_avvio_at"] = ora
        if db.set_tennis_bot_service_state(bot, status="stopped", stopped=True,
                                           stats=stats):
            fermati.append(bot)
            logger.info("[tennis-bot-svc] avvio NUOVO dell'app: interruttore "
                        "%s riportato a 'stopped' (lo accende l'utente).", bot)
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
