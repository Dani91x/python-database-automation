"""runner_lifecycle.py — auto-SPEGNIMENTO dei runner (logica PURA, condivisa).

Fix incidente 2026-07-08: i runner (calcio/tennis) restavano attivi per GIORNI a
martellare Betfair perché il worker watchlist/follow riagganciava sempre le partite
successive. Finché il software non sarà pensato per l'h24, il runner deve spegnersi
da solo quando non serve più. Due condizioni (entrambe configurabili via env, 0 = off):

  (a) VITA MASSIMA — backstop assoluto: dopo N ore il runner esce comunque;
  (b) INATTIVITÀ  — nessun evento "vivo" tra i follow attivi: né una partita in corso
      (iniziata da meno di ``stale_hours``) né una imminente (che inizia entro
      ``imminent_min`` minuti) → fine della giornata di trading, il runner esce.
      Si rilancia col .bat quando serve.

Qui SOLO matematica su datetimes (testabile a unità): niente I/O, niente flumine.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def parse_open_date(raw: Any) -> Optional[datetime]:
    """open_date (ISO, anche con 'Z') → datetime aware UTC; None se non parsabile."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def event_is_alive(
    open_date: Optional[datetime],
    now: datetime,
    imminent_min: float,
    stale_hours: float,
) -> bool:
    """True se l'evento è IN CORSO (iniziato da < stale_hours) o IMMINENTE
    (inizia entro imminent_min). open_date non parsabile → True per PRUDENZA
    (mai spegnere il runner su un dato ambiguo)."""
    if open_date is None:
        return True
    return (open_date - timedelta(minutes=imminent_min)
            <= now
            <= open_date + timedelta(hours=stale_hours))


def any_follow_alive(
    follows: List[Dict[str, Any]],
    now: Optional[datetime] = None,
    *,
    imminent_min: float,
    stale_hours: float,
) -> bool:
    """True se ALMENO un follow attivo (PENDING/STREAMING) è vivo o imminente."""
    t = now or datetime.now(timezone.utc)
    for f in follows:
        if event_is_alive(parse_open_date(f.get("open_date")), t, imminent_min, stale_hours):
            return True
    return False


# EXIT CODE "riavvio pianificato" (audit 09/09): con LIVE_RUNNER_KEEP_ALIVE=1 (app
# desktop) la vita massima 18h NON è una fine voluta dall'utente ma un ricambio
# igienico del processo. Prima usciva con rc=0 → il watchdog (correttamente)
# non riavviava → runner MORTO in silenzio dopo 18h. Con questo codice il
# watchdog riavvia subito, senza contarlo come crash.
EXIT_PLANNED_RESTART = 75


def uptime_exceeded(started_monotonic: float, now_monotonic: float, max_hours: float) -> bool:
    """True se la vita massima è superata (max_hours <= 0 → mai)."""
    if max_hours <= 0:
        return False
    return (now_monotonic - started_monotonic) > max_hours * 3600.0


# ----------------------------------------------------------------------------
# Stallo del recorder raw (incidente 2026-07-16: stream MUTO per ~1.5h con
# runner vivo → nessun dato di mercato registrato, raw mai creati per i nuovi
# follow). Qui SOLO la matematica pura (testabile); l'azione è in runner.py.
# ----------------------------------------------------------------------------
def raw_stall_seconds(
    last_write_ms: float,
    now_ms: float,
    seconds_since_stream_start: Optional[float],
) -> Optional[float]:
    """Da quanti secondi il tee raw NON scrive.

    * ``last_write_ms > 0``: secondi trascorsi dall'ultimo write.
    * ``last_write_ms == 0`` (MAI scritto — il caso 16/07: stream mai connesso):
      l'età dello stream corrente, se nota.
    * altrimenti ``None`` (non determinabile → nessuna azione).
    """
    if last_write_ms and last_write_ms > 0:
        return max(0.0, (now_ms - last_write_ms) / 1000.0)
    if seconds_since_stream_start is not None:
        return max(0.0, seconds_since_stream_start)
    return None


def effective_stall_seconds(
    data_stall_s: Optional[float],
    heartbeat_stall_s: Optional[float],
    data_hard_cap_s: Optional[float] = None,
) -> Optional[float]:
    """Stallo EFFETTIVO della connessione (fix 17/07: stallo cieco agli heartbeat).

    Betfair invia messaggi ``mcm`` con ``ct=HEARTBEAT`` ogni 0.5-5s quando NON
    c'è traffico dati: heartbeat freschi + dati fermi = mercato legittimamente
    QUIETO (metà tempo, pre-match lontano), NON uno stream morto. Il restart
    per stallo deve scattare SOLO quando sia i dati sia gli heartbeat sono
    vecchi (connessione morta davvero):

    * ``data_stall_s is None`` → non determinabile → ``None`` (nessuna azione);
    * ``heartbeat_stall_s is None`` (heartbeat mai osservati e età stream
      ignota) → comportamento storico: conta solo il silenzio dati;
    * altrimenti → ``min`` dei due: supera la soglia solo se ENTRAMBI vecchi.

    ``data_hard_cap_s`` (review 17/07, seconda passata): l'heartbeat prova che
    il SOCKET è vivo, NON che la subscription dati è sana — con una subscription
    rotta a TCP vivo gli heartbeat "mentirebbero" per sempre. Oltre il cap di
    silenzio dati puro il restart scatta COMUNQUE, heartbeat ignorati: è il
    secondo cancello indipendente che preserva la garanzia anti-16/07.
    """
    if data_stall_s is None:
        return None
    if data_hard_cap_s is not None and data_stall_s >= data_hard_cap_s:
        return data_stall_s
    if heartbeat_stall_s is None:
        return data_stall_s
    return min(data_stall_s, heartbeat_stall_s)


def stall_restart_due(
    stall_s: Optional[float],
    threshold_s: float,
    last_restart_monotonic: float,
    now_monotonic: float,
    min_interval_s: float,
) -> bool:
    """True se lo stallo persistente giustifica una ricostruzione della
    subscription (throttled: mai più spesso di ``min_interval_s``).
    ``threshold_s <= 0`` disattiva il meccanismo."""
    if threshold_s <= 0 or stall_s is None or stall_s < threshold_s:
        return False
    return (now_monotonic - last_restart_monotonic) >= min_interval_s


# ----------------------------------------------------------------------------
# R-STREAM-1 (26/09): alle 10:41:41Z una caduta di rete ha lasciato il runner
# calcio con battito vivo e ZERO dati per 4 ore; la ricostruzione della
# subscription (14:39Z) non ha ridato dati. Due pezzi puri condivisi da calcio
# e tennis: il battito dello stream letto SENZA json.loads (vale anche a
# registrazione spenta) e il verdetto dopo una ricostruzione per stallo.
# ----------------------------------------------------------------------------
MSG_HEARTBEAT = "heartbeat"
MSG_DATI = "dati"
_RE_OP_MCM = re.compile(r'"op"\s*:\s*"mcm"')
_RE_CT_HEARTBEAT = re.compile(r'"ct"\s*:\s*"HEARTBEAT"')
_RE_MC_PIENO = re.compile(r'"mc"\s*:\s*\[\s*\{')


def classifica_messaggio_stream(raw_data: Any) -> Optional[str]:
    """``'heartbeat'`` / ``'dati'`` / ``None`` per un messaggio grezzo Betfair.

    Lettura per espressione regolare (niente ``json.loads``): costa poco,
    quindi puo' girare su OGNI messaggio anche quando nessuna partita e' in
    registrazione (prima il battito si aggiornava solo col tee acceso).
    Tollera gli spazi dopo ``:``/``,``. ``dati`` = ``mcm`` con almeno un
    market change."""
    if not isinstance(raw_data, str) or not _RE_OP_MCM.search(raw_data):
        return None
    if _RE_CT_HEARTBEAT.search(raw_data):
        return MSG_HEARTBEAT
    if _RE_MC_PIENO.search(raw_data):
        return MSG_DATI
    return None


VERDETTO_ATTENDI = "attendi"
VERDETTO_GUARITO = "guarito"
VERDETTO_ESCALA = "escala"


def verdetto_post_ricostruzione(
    stall_s: Optional[float],
    dati_dopo_rebuild: bool,
    secondi_dal_rebuild: float,
    finestra_s: float,
    osservazione_s: float,
) -> str:
    """Esito di una ricostruzione della subscription chiesta per STALLO.

    Passata la ``finestra_s`` dalla ricostruzione:

    * ``escala`` se NESSUN dato e' arrivato dopo la ricostruzione (nemmeno
      l'immagine iniziale: subscription rotta anche con heartbeat freschi,
      lezione 17/07) oppure se lo stallo EFFETTIVO (dati E heartbeat,
      ``effective_stall_seconds``) e' di nuovo >= ``finestra_s`` (26/09: 89
      ladder in pochi minuti, poi di nuovo tutto fermo) -> ricostruire nello
      stesso processo non basta, serve un processo nuovo;
    * ``guarito`` passata l'``osservazione_s`` senza escalation (o con
      ``finestra_s <= 0`` = meccanismo spento) -> si torna al ciclo normale.
      Un mercato QUIETO dopo l'immagine (heartbeat freschi) non escala;
    * ``attendi`` altrimenti.
    """
    if finestra_s <= 0:
        return VERDETTO_GUARITO
    if secondi_dal_rebuild < finestra_s:
        return VERDETTO_ATTENDI
    if not dati_dopo_rebuild:
        return VERDETTO_ESCALA
    if stall_s is not None and stall_s >= finestra_s:
        return VERDETTO_ESCALA
    if secondi_dal_rebuild >= osservazione_s:
        return VERDETTO_GUARITO
    return VERDETTO_ATTENDI


def e_errore_di_rete(exc: BaseException) -> bool:
    """True se ``exc`` (o un'eccezione della sua catena cause/context) e' un
    guasto di TRASPORTO: socket/DNS/timeout (``ConnectionError``,
    ``TimeoutError``, ``socket.gaierror``; NON ogni ``OSError``: un file non
    scrivibile e' un altro guasto), ``requests``,
    ``httpx`` (client Supabase), o il ``RuntimeError`` finale di
    ``BetfairClient._rpc`` dopo i ritentativi per errore di rete.

    26/09 (tre crash exit 1 in un giorno, cadute di rete alle 10:41Z): nel
    ciclo principale dei runner una SELECT dei follow fallita per rete
    risaliva fino a ``main`` -> processo morto (e il calcio chiudeva ogni
    follow nel ``finally``). Solo il trasporto: un errore di programmazione
    NON e' di rete e va rilanciato."""
    import socket

    tipi: tuple = (ConnectionError, TimeoutError, socket.gaierror, socket.herror)
    try:
        import requests

        tipi = tipi + (requests.RequestException,)
    except Exception:  # noqa: BLE001 - libreria assente: non e' di rete
        pass
    try:
        import httpx

        tipi = tipi + (httpx.TransportError,)
    except Exception:  # noqa: BLE001
        pass
    visti = set()
    cur: Optional[BaseException] = exc
    while cur is not None and id(cur) not in visti:
        visti.add(id(cur))
        if isinstance(cur, tipi):
            return True
        if (isinstance(cur, RuntimeError)
                and "RPC failed after" in str(cur) and "Network error" in str(cur)):
            return True
        cur = cur.__cause__ or cur.__context__
    return False
