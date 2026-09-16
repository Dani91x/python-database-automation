"""avvio_app — ALL'AVVIO DELL'APP NESSUN BOT OPERA (FASE A, 16/09/2026).

Il problema, in una riga: ogni servizio rilegge la propria riga di controllo dal
database e, se ci trova ``status='running'``, opera. Quindi un bot lasciato
acceso ieri — magari in LIVE — riparte DA SOLO al primo avvio dell'app di oggi,
senza che nessuno lo abbia acceso. E' l'opposto della regola del progetto:
**ai soldi veri si arriva scrivendolo, mai ereditandolo.**

IL MECCANISMO

``desktop/main.js`` genera UNA volta per avvio dell'app un ``APP_BOOT_ID`` e lo
mette nell'ambiente di tutti i processi che lancia. Il watchdog
(``Betfair/stream/watchdog.py``) lancia il figlio con ``popen(cmd, cwd=...)``
SENZA passare ``env=``: il figlio eredita l'ambiente del watchdog, quindi un
riavvio da crash porta con se' lo STESSO id. Cosi' si distinguono due casi che
sembrano uguali visti dal servizio:

  * **avvio nuovo dell'app** (id diverso, o assente) → il bot si FERMA:
    ``status='stopped'``, ``mode='paper'``, e per Safe tutte le voci di
    ``params.strategy_modes`` a ``'paper'``. Viene scritta un'attivita'
    ``avvio_app_bot_fermato`` con l'elenco di cio' che e' stato azzerato.
  * **riavvio da watchdog** (stesso id) → NON si tocca NIENTE: un bot acceso
    dall'utente non deve morire in silenzio a ogni crash del processo.

FAIL-CLOSED: ``APP_BOOT_ID`` assente vale come avvio nuovo. Un processo che non
sa da quale avvio viene non e' autorizzato a ereditare soldi veri.

DOVE VIVE L'ID: nella colonna ``stats`` (JSONB) che TUTTE le righe di controllo
hanno gia' (``mike_control``, ``omega_control``, ``safe_strategy_control``,
``tennis_bot_control``, ``scalper_control``). Nessuna colonna nuova, nessuna
migrazione da applicare.

⚠️ CHI SCRIVE ``stats`` DEVE TIMBRARLE. I servizi riscrivono ``stats`` per
intero a ogni battito: senza ``Guardia.timbra`` l'id sparirebbe dalla riga al
primo ciclo, e il crash successivo verrebbe scambiato per un avvio nuovo —
spegnendo il bot che l'utente aveva appena acceso.

LE STRATEGIE NON SI TOCCANO: qui si scrivono solo ``status``, ``mode``,
``stopped_at`` e ``stats``. L'unica chiave di ``params`` che puo' cambiare e'
``strategy_modes`` (Safe), che e' modalita' — paper o live — non strategia.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger("avvio_app")

#: variabile d'ambiente scritta da ``desktop/main.js``, una per avvio dell'app.
ENV_BOOT_ID = "APP_BOOT_ID"
#: chiavi dentro ``stats`` (JSONB gia' esistente su tutte le righe di controllo)
CHIAVE_BOOT_ID = "boot_id"
CHIAVE_FERMATO_AT = "fermato_all_avvio_at"
#: tipo di attivita' scritta quando un bot viene fermato all'avvio dell'app
KIND_ATTIVITA = "avvio_app_bot_fermato"


def boot_id_ambiente(env: Optional[dict] = None) -> str:
    """L'id dell'avvio dell'app corrente. Assente/vuoto → ``''`` (fail-closed:
    chi non sa da quale avvio viene viene trattato come avvio NUOVO)."""
    amb = os.environ if env is None else env
    try:
        return str(amb.get(ENV_BOOT_ID) or "").strip()
    except Exception:  # noqa: BLE001 — un ambiente strano non ferma un servizio
        return ""


def boot_id_salvato(stats: Any) -> str:
    """L'id dell'avvio a cui appartiene l'ultimo stato scritto su questa riga."""
    if not isinstance(stats, dict):
        return ""
    return str(stats.get(CHIAVE_BOOT_ID) or "").strip()


def stesso_avvio(stats: Any, boot_id: str) -> bool:
    """True SOLO se la riga porta ESATTAMENTE questo avvio dell'app.

    Due assenze non fanno un'uguaglianza: id corrente vuoto o id salvato vuoto
    valgono «non lo so», e «non lo so» qui vuol dire avvio nuovo.
    """
    if not boot_id:
        return False
    salvato = boot_id_salvato(stats)
    return bool(salvato) and salvato == boot_id


def stats_timbrate(stats: Any, boot_id: str, fermato_at: str = "") -> dict[str, Any]:
    """Copia di ``stats`` con l'id dell'avvio (e, se c'e', l'istante in cui il
    bot e' stato fermato all'avvio). Non tocca nessun'altra chiave."""
    out = dict(stats) if isinstance(stats, dict) else {}
    out[CHIAVE_BOOT_ID] = boot_id
    if fermato_at:
        out[CHIAVE_FERMATO_AT] = fermato_at
    return out


def righe_da_fermare(righe: Any, boot_id: str) -> list[dict[str, Any]]:
    """Fra righe ATTIVE (tennis per evento, scalper per partita), quelle che NON
    appartengono a questo avvio dell'app — cioe' quelle da fermare."""
    fuori: list[dict[str, Any]] = []
    for r in list(righe or []):
        if not isinstance(r, dict):
            continue
        if not stesso_avvio(r.get("stats"), boot_id):
            fuori.append(r)
    return fuori


class Guardia:
    """Memoria di PROCESSO del controllo d'avvio di UN servizio.

    ``attiva`` la accende il ``main()`` del servizio: solo un processo che gira
    come servizio deve bloccare le aperture in attesa del controllo. Un
    ``run_once`` chiamato da un test o da un banco di replay non e' un avvio
    dell'app e non deve cambiare comportamento.

    ``fatto`` diventa True SOLO quando il controllo si e' concluso con una
    scrittura riuscita (o quando non c'era niente da scrivere). Finche' e'
    False e la guardia e' attiva, ``blocca_aperture`` e' True: se il database
    non risponde in avvio si protegge quello che c'e' e non si apre niente.
    """

    def __init__(self, nome: str) -> None:
        self.nome = str(nome)
        self.attiva = False
        self.fatto = False
        self.boot_id = ""
        self.fermato_at = ""

    @property
    def blocca_aperture(self) -> bool:
        """True se il servizio non ha ancora verificato da quale avvio viene."""
        return bool(self.attiva) and not self.fatto

    def azzera(self) -> None:
        """Riporta la guardia a nuova (usata dai test: lo stato e' di processo)."""
        self.attiva = False
        self.fatto = False
        self.boot_id = ""
        self.fermato_at = ""

    def timbra(self, stats: Any) -> Any:
        """Aggiunge l'id dell'avvio alle ``stats`` che il servizio sta per
        scrivere. Prima che il controllo sia stato fatto non tocca niente."""
        if not self.fatto:
            return stats
        return stats_timbrate(stats, self.boot_id, self.fermato_at)


def ferma_al_nuovo_avvio(
    guardia: Guardia,
    *,
    control: Any,
    set_control: Callable[..., Any],
    log: Optional[Callable[..., Any]] = None,
    now_iso: str,
    params_reset: Optional[Callable[[Any], Any]] = None,
    boot_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Ferma il bot se questo processo appartiene a un avvio NUOVO dell'app.

    ``control``: la riga di controllo GIA' letta (singleton).
    ``set_control(**campi)``: scrittura sulla riga.
    ``log(kind, payload)``: attivita' (best-effort, non ferma niente).
    ``params_reset(params_grezzi) -> (params_patchati | None, elenco_live)``:
      solo Safe. Tocca ESCLUSIVAMENTE ``strategy_modes``.

    Ritorna il riepilogo di cio' che e' stato azzerato, oppure ``None`` se non
    c'era niente da fare (stesso avvio, controllo gia' fatto, bot gia' fermo in
    paper). Solleva se la scrittura fallisce: il chiamante non deve segnare il
    controllo come fatto, cosi' il giro dopo riprova e intanto non si apre.
    """
    if guardia.fatto:
        return None
    boot = boot_id_ambiente() if boot_id is None else str(boot_id or "").strip()
    riga = control if isinstance(control, dict) else {}
    stats = riga.get("stats")

    if stesso_avvio(stats, boot):
        # RIAVVIO DA WATCHDOG: il bot lo ha acceso l'utente in QUESTO avvio
        # dell'app e non lo spegne un crash del processo. Non si tocca niente.
        guardia.boot_id = boot
        # si porta avanti l'istante del blocco d'avvio, se c'era: le ``stats``
        # vengono riscritte per intero a ogni battito e altrimenti lo perderebbero.
        guardia.fermato_at = str((stats or {}).get(CHIAVE_FERMATO_AT) or "")
        guardia.fatto = True
        logger.info("[avvio_app] %s: stesso avvio dell'app (%s) — non tocco niente.",
                    guardia.nome, boot or "senza id")
        return None

    stato_prima = str(riga.get("status") or "")
    modo_prima = str(riga.get("mode") or "")
    params_grezzi = riga.get("params")
    patched = None
    live_prima: list[str] = []
    if params_reset is not None:
        try:
            patched, live_prima = params_reset(params_grezzi)
        except Exception as ex:  # noqa: BLE001 — i params non devono impedire lo stop
            logger.warning("[avvio_app] %s: reset delle modalita' per strategia KO: %s",
                           guardia.nome, str(ex)[:160])
            patched, live_prima = None, []

    # C'ERA DAVVERO QUALCOSA DA SPEGNERE? La riga si riscrive comunque (l'id
    # dell'avvio deve restare sulla riga), ma l'attivita' e il cartello in
    # Control Room hanno senso solo se questo avvio ha fermato qualcosa: un bot
    # gia' fermo in paper non e' stato «fermato all'avvio».
    azzerato = bool(stato_prima in ("running", "stopping", "error")
                    or modo_prima == "live"
                    or patched is not None)
    fermato_at = now_iso if azzerato else ""

    campi: dict[str, Any] = {
        "status": "stopped",
        "mode": "paper",
        "stopped_at": now_iso,
        "stats": stats_timbrate(stats, boot, fermato_at),
    }
    if patched is not None:
        campi["params"] = patched
    set_control(**campi)

    riepilogo = {
        "bot": guardia.nome,
        "boot_id": boot,
        "boot_id_precedente": boot_id_salvato(stats),
        "status_precedente": stato_prima,
        "mode_precedente": modo_prima,
        "strategy_modes_live": list(live_prima),
        "azzerato": azzerato,
        "motivo": ("APP_BOOT_ID assente nell'ambiente: trattato come avvio nuovo"
                   if not boot else "avvio nuovo dell'app"),
        "effetto": ("i bot li accende l'utente: status=stopped, mode=paper. "
                    "Le posizioni gia' aperte restano sorvegliate."),
        "ts": now_iso,
    }
    if azzerato and log is not None:
        try:
            log(KIND_ATTIVITA, riepilogo)
        except Exception as ex:  # noqa: BLE001 — il log non ferma mai un bot
            logger.warning("[avvio_app] %s: attivita' non scritta: %s",
                           guardia.nome, str(ex)[:160])
    guardia.boot_id = boot
    guardia.fermato_at = fermato_at
    guardia.fatto = True
    if azzerato:
        logger.warning("[avvio_app] %s FERMATO all'avvio dell'app (era %s/%s): "
                       "l'accensione e' un gesto dell'utente.",
                       guardia.nome, stato_prima or "?", modo_prima or "?")
    else:
        logger.info("[avvio_app] %s: avvio nuovo, il bot era gia' fermo in prova.",
                    guardia.nome)
    return riepilogo
