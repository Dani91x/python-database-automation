"""watchdog.py — A5: processo SENTINELLA del runner di trading live (money-critical).

Uso (dalla radice del repo):
    python -m Betfair.stream.watchdog
        → sorveglia il modulo di default ``Betfair.stream.runner``
    python -m Betfair.stream.watchdog -- Betfair.stream.tennis_live.tennis_runner [--args...]
        → dopo ``--``: modulo target + argomenti extra passati al figlio

Il watchdog lancia il runner come processo FIGLIO e lo sorveglia. Alla morte
del figlio classifica l'uscita (``classify_exit``):

  * PULITA (exit code 0 — auto-spegnimento lifecycle 18h/idle, fine naturale
    dei follow o Ctrl+C) → alert INFO e il watchdog SI FERMA. MAI riavvio in
    questo caso (decisione utente: niente h24 automatico — il runner ha
    deciso di spegnersi e va rispettato).
  * GIÀ ATTIVO (exit code != 0 con uptime sotto ``WATCHDOG_LOCK_GRACE_SEC``:
    il lock di singola istanza — porta localhost, vedi single_instance.py —
    solleva SystemExit immediato) → alert WARN e il watchdog SI FERMA:
    MAI un loop di riavvii contro il lock.
  * CRASH (qualunque altro exit code != 0) → alert CRITICAL + Telegram
    (best-effort) e RIAVVIO automatico con backoff esponenziale
    (10s → 20s → 40s … cap 300s) e tetto riavvii/ora (finestra scorrevole).
    Tetto raggiunto → alert CRITICAL "SERVE INTERVENTO MANUALE" e exit 1.

Mentre il figlio gira, ogni ``WATCHDOG_HEARTBEAT_SEC`` il watchdog scrive il
proprio heartbeat (``db.upsert_live_heartbeat(runner=False, ...)`` → colonne
watchdog_ts/watchdog_pid di ``betfair_live_heartbeat``).

Config via env: WATCHDOG_MAX_RESTARTS_PER_HOUR (5), WATCHDOG_BACKOFF_BASE_SEC
(10), WATCHDOG_BACKOFF_CAP_SEC (300), WATCHDOG_LOCK_GRACE_SEC (5),
WATCHDOG_HEARTBEAT_SEC (30).

MONEY-CRITICAL:
  * il watchdog NON deve MAI morire perché DB/Telegram sono giù: alert,
    heartbeat e notifiche sono best-effort (in caso di errore logga soltanto);
  * il watchdog NON acquisisce il lock del runner: deve poter girare INSIEME
    al runner (è il figlio a tenere il lock);
  * decisioni in funzioni PURE (classify_exit / next_backoff / should_restart)
    e dipendenze iniettabili (popen/sleep/now/alert/heartbeat/telegram):
    tutto testabile senza processi reali né rete.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TARGET = "Betfair.stream.runner"
_ALERT_CODE = "RUNNER_WATCHDOG"
_WINDOW_SEC = 3_600.0  # finestra scorrevole del tetto riavvii: 1 ora


# ---------------------------------------------------------------------------
# Funzioni PURE di decisione (nessun I/O)
# ---------------------------------------------------------------------------
def classify_exit(returncode: int, uptime_sec: float, lock_grace_sec: float = 5.0) -> str:
    """Classifica l'uscita del figlio: ``'clean'`` | ``'lock'`` | ``'crash'``.

    * rc == 0 → ``'clean'`` sempre (anche dopo ore: auto-spegnimento voluto).
    * rc != 0 con uptime SOTTO ``lock_grace_sec`` → ``'lock'``: il lock di
      singola istanza (single_instance.py) solleva SystemExit in avvio →
      exit code 1 in una manciata di istanti. Un'altra istanza è già attiva.
    * qualunque altro rc != 0 → ``'crash'``.
    """
    if returncode == 0:
        return "clean"
    if uptime_sec < lock_grace_sec:
        return "lock"
    return "crash"


def next_backoff(consecutive_crashes: int, base: float = 10.0, cap: float = 300.0) -> float:
    """Backoff esponenziale prima del riavvio, in secondi.

    ``consecutive_crashes`` è 1-based: 1° crash → ``base`` (10s), 2° → 20s,
    3° → 40s, … con tetto ``cap`` (300s). Input < 1 → ``base`` (mai sotto).
    """
    n = max(1, int(consecutive_crashes))
    # esponente limitato: evita 2**n gigante con contatori assurdi
    exp = min(n - 1, 64)
    return float(min(base * (2.0 ** exp), cap))


def should_restart(restart_ts: List[float], now: float, max_per_hour: int) -> bool:
    """True se i riavvii nell'ULTIMA ORA (finestra scorrevole su timestamp
    monotonic, bordo escluso: esattamente 1h fa = fuori) sono < ``max_per_hour``."""
    recenti = [t for t in restart_ts if now - t < _WINDOW_SEC]
    return len(recenti) < int(max_per_hour)


# ---------------------------------------------------------------------------
# Dipendenze di default (DB / Telegram) — tutte best-effort
# ---------------------------------------------------------------------------
def _db_alert(level: str, msg: str) -> None:
    """Alert → live_alerts (import lazy: il modulo si importa anche senza DB)."""
    from . import db

    db.insert_alert(level, _ALERT_CODE, msg)


def _db_heartbeat() -> None:
    """Heartbeat del WATCHDOG (runner=False → watchdog_ts/watchdog_pid)."""
    from . import db

    db.upsert_live_heartbeat(runner=False, pid=os.getpid())


def _send_telegram(msg: str) -> None:
    """Notifica FORTE via Telegram. OPZIONALE: senza TELEGRAM_BOT_TOKEN /
    TELEGRAM_CHAT_ID è un no-op. Il chiamante la incapsula best-effort."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    import urllib.request

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": msg}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - host fisso api.telegram.org
        resp.read()


# ---------------------------------------------------------------------------
# Utilità interne
# ---------------------------------------------------------------------------
def _env_float(name: str, default: float) -> float:
    """Float da env; valore assente/invalido/negativo → default (mai crashare
    in avvio per una env sporca: il watchdog deve partire comunque)."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        val = float(raw)
    except (TypeError, ValueError):
        logger.warning("[watchdog] env %s invalida (%r): uso default %s", name, raw, default)
        return default
    if val < 0:
        logger.warning("[watchdog] env %s negativa (%s): uso default %s", name, val, default)
        return default
    return val


def _parse_argv(argv: Optional[List[str]]) -> tuple[str, List[str]]:
    """(modulo_target, args_extra). Tutto ciò che segue ``--`` è il comando
    del figlio: primo token = modulo, il resto = argomenti extra."""
    args = list(argv or [])
    if "--" in args:
        dopo = args[args.index("--") + 1:]
        if dopo:
            return dopo[0], dopo[1:]
    if args:
        logger.warning("[watchdog] argomenti ignorati (usa `-- modulo [args...]`): %s", args)
    return _DEFAULT_TARGET, []


def _safe(fn: Callable[..., None], *args: object, what: str = "callback") -> None:
    """Esegue una dipendenza best-effort: se solleva, si LOGGA e si va avanti.
    Il watchdog non deve MAI morire perché DB o Telegram sono giù."""
    try:
        fn(*args)
    except Exception as e:  # noqa: BLE001 - by design: mai far cadere la sentinella
        logger.warning("[watchdog] %s KO (ignoro): %s", what, str(e)[:200])


# ---------------------------------------------------------------------------
# Loop principale
# ---------------------------------------------------------------------------
def run_watchdog(
    argv: Optional[List[str]] = None,
    *,
    popen=subprocess.Popen,
    sleep=time.sleep,
    now=time.monotonic,
    alert=None,
    heartbeat=None,
    telegram=None,
    max_cycles: Optional[int] = None,
) -> int:
    """Sorveglia il runner finché non esce pulito / il lock è occupato / il
    tetto riavvii è esaurito. Ritorna l'exit code del watchdog (0 = uscita
    ordinata, 1 = serve intervento manuale). ``max_cycles`` (SOLO test) limita
    il numero di spawn: raggiunto il limite ritorna 1.
    """
    alert = alert if alert is not None else _db_alert
    heartbeat = heartbeat if heartbeat is not None else _db_heartbeat
    telegram = telegram if telegram is not None else _send_telegram

    target, extra = _parse_argv(argv)
    cmd = [sys.executable, "-m", target, *extra]
    # cwd = radice del repo (parent di Betfair/): gli import `-m` del figlio
    # funzionano ovunque venga lanciato il watchdog.
    repo_root = Path(__file__).resolve().parents[2]

    max_per_hour = int(_env_float("WATCHDOG_MAX_RESTARTS_PER_HOUR", 5))
    backoff_base = _env_float("WATCHDOG_BACKOFF_BASE_SEC", 10.0)
    backoff_cap = _env_float("WATCHDOG_BACKOFF_CAP_SEC", 300.0)
    lock_grace = _env_float("WATCHDOG_LOCK_GRACE_SEC", 5.0)
    hb_sec = _env_float("WATCHDOG_HEARTBEAT_SEC", 30.0) or 30.0

    consecutive_crashes = 0
    restart_ts: List[float] = []  # timestamp monotonic dei riavvii (finestra 1h)
    spawns = 0

    logger.info("[watchdog] sorveglio: %s (cwd=%s)", " ".join(cmd), repo_root)
    while True:
        if max_cycles is not None and spawns >= max_cycles:
            logger.error("[watchdog] max_cycles=%d raggiunto: esco.", max_cycles)
            return 1
        spawns += 1
        started = now()
        try:
            proc = popen(cmd, cwd=str(repo_root))
        except Exception as e:  # noqa: BLE001 - spawn fallito: mai morire in silenzio
            _safe(alert, "CRITICAL",
                  f"WATCHDOG: lancio del runner FALLITO ({str(e)[:150]}) — "
                  "SERVE INTERVENTO MANUALE, il watchdog si ferma.", what="alert")
            _safe(telegram, f"WATCHDOG: lancio runner FALLITO: {str(e)[:150]}", what="telegram")
            return 1

        # attesa: heartbeat del watchdog a ogni giro finché il figlio è vivo
        while proc.poll() is None:
            _safe(heartbeat, what="heartbeat")
            sleep(hb_sec)

        uptime = max(0.0, now() - started)
        rc = proc.returncode
        esito = classify_exit(rc, uptime, lock_grace)
        logger.info("[watchdog] figlio uscito: rc=%s uptime=%.0fs esito=%s", rc, uptime, esito)

        if esito == "clean":
            # decisione utente: MAI h24 automatico — l'auto-spegnimento del
            # runner (lifecycle 18h/idle, fine naturale, Ctrl+C) va rispettato.
            _safe(alert, "INFO",
                  f"Runner terminato in modo pulito (uptime {uptime:.0f}s) — "
                  "il watchdog si ferma.", what="alert")
            return 0

        if esito == "lock":
            # single_instance: un runner è GIÀ attivo — mai martellare il lock.
            _safe(alert, "WARN",
                  "Runner già attivo (lock porta di singola istanza) — "
                  "il watchdog si ferma senza riavviare.", what="alert")
            return 0

        # CRASH → notifica forte + riavvio con backoff (entro il tetto orario)
        consecutive_crashes += 1
        base_msg = f"RUNNER CRASHATO: exit code {rc}, uptime {uptime:.0f}s."
        if not should_restart(restart_ts, now(), max_per_hour):
            msg = (f"{base_msg} Riavvii/ora esauriti ({max_per_hour}/h): "
                   "SERVE INTERVENTO MANUALE — il watchdog si ferma.")
            _safe(alert, "CRITICAL", msg, what="alert")
            _safe(telegram, msg, what="telegram")
            return 1
        backoff = next_backoff(consecutive_crashes, base=backoff_base, cap=backoff_cap)
        msg = f"{base_msg} Riavvio n. {consecutive_crashes} tra {backoff:.0f}s."
        _safe(alert, "CRITICAL", msg, what="alert")
        _safe(telegram, msg, what="telegram")
        restart_ts.append(now())
        sleep(backoff)


def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run_watchdog(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(_main())
