"""local_channel.py — A7: canale LOCALE UI(desktop) ↔ runner (WebSocket su 127.0.0.1).

È il fix strutturale della latenza: quando l'app desktop è collegata, ladder/
stato/ordini/posizioni sono PUSHATI direttamente dalla cache flumine (niente
giro sul cloud) e i comandi ordine arrivano qui e vengono ESEGUITI DALLO STESSO
path di validazione del worker coda (stesse guardie, stesso specchio, stesso
journal) — nessun secondo path ordini: cambia solo il trasporto.

SICUREZZA: bind ESCLUSIVO su 127.0.0.1 (irraggiungibile dall'esterno). I comandi
NON vengono eseguiti nel thread del WebSocket: finiscono in una coda in-memory
drenata dal THREAD del live_order_worker (un solo thread tocca flumine per gli
ordini, come oggi). Il canale è best-effort: se cade, la UI ricade sul path DB.

Protocollo (JSON, una riga per messaggio):
  push  server→client : {"t": <topic>, "d": <payload>}   topic: hello|ladder|now|order|position|board
  req   client→server : {"id": <int>, "m": "order"|"snapshot", "p": {...}}
  res   server→client : {"id": <int>, "ok": bool, "d": {...}} | {"id",..,"ok":false,"e": "msg"}
"""
from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_ALLOWED_METHODS = frozenset({"order", "snapshot"})
_MAX_QUEUE = 200  # anti-runaway: mai accumulare comandi all'infinito
# invii non ancora completati oltre i quali si smette di pubblicare: con pochi
# client su 127.0.0.1 non ci si arriva mai, e se ci si arriva vuol dire che il
# consumatore e' fermo — mandargli altra roba non lo aiuta.
_MAX_INVII_IN_VOLO = 64


@dataclass
class LocalRequest:
    """Richiesta drenata dal worker (il ws serve solo per la risposta)."""

    ws: Any
    msg_id: Any
    method: str
    params: Dict[str, Any] = field(default_factory=dict)


class LocalChannel:
    """Server WS su localhost. publish/respond sono THREAD-SAFE (call_soon_threadsafe)."""

    def __init__(self, port: int, sport: str = "calcio", solo_lettura: bool = False) -> None:
        self.port = int(port)
        self.sport = sport
        # CANALE DI SOLA USCITA (14/09). I canali dei BOT (Mike, Omega, Safe)
        # servono a mostrare, non a comandare: nessuno drena la loro coda, e una
        # richiesta che arrivasse resterebbe li' senza risposta finche' la coda
        # non si riempie (200) e comincia a rifiutare in silenzio.
        # Meglio dirlo subito e chiaramente.
        #
        # E c'e' una ragione piu' importante del garbo: il canale del runner
        # ESEGUE ORDINI VERI. Tenere i due livelli di fiducia separati — chi
        # comanda e chi mostra — vuol dire che aggiungere uno schermo non
        # aggiunge mai una via per mandare soldi.
        self.solo_lettura = bool(solo_lettura)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._clients: set = set()          # toccato SOLO dal thread del loop
        self._requests: "queue.Queue[LocalRequest]" = queue.Queue(maxsize=_MAX_QUEUE)
        self._n_clients = 0                 # letto cross-thread (int: atomico)
        self._in_volo = 0               # invii non ancora completati (contropressione)
        self._ultimo_avviso = 0.0
        self._started = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._hello_extra: Dict[str, Any] = {}

    # ------------------------------------------------------------- lifecycle
    def start(self) -> bool:
        """Avvia il server in un thread dedicato. False se la porta è occupata."""
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"local-ws-{self.port}")
        self._thread.start()
        self._started.wait(timeout=5.0)
        return self._loop is not None

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as ex:  # noqa: BLE001 - canale opzionale: il runner vive senza
            logger.warning("[local-ws] server KO (porta %d): %s", self.port, str(ex)[:160])
            self._started.set()

    async def _serve(self) -> None:
        from websockets.asyncio.server import serve

        self._loop = asyncio.get_running_loop()
        try:
            async with serve(self._handler, "127.0.0.1", self.port):
                self._started.set()
                logger.info("[local-ws] canale locale %s attivo su 127.0.0.1:%d", self.sport, self.port)
                await asyncio.Future()  # per sempre (thread daemon)
        finally:
            self._loop = None
            self._started.set()

    async def _handler(self, ws: Any) -> None:
        self._clients.add(ws)
        self._n_clients = len(self._clients)
        try:
            await ws.send(json.dumps({"t": "hello", "d": {"sport": self.sport, **self._hello_extra}}))
            async for raw in ws:
                self._on_message(ws, raw)
        except Exception:  # noqa: BLE001 - disconnessioni brusche: normali
            pass
        finally:
            self._clients.discard(ws)
            self._n_clients = len(self._clients)

    def _on_message(self, ws: Any, raw: Any) -> None:
        """Parse + enqueue (nel thread del loop). MAI eseguire ordini qui."""
        try:
            msg = json.loads(raw)
            method = str(msg.get("m") or "")
            msg_id = msg.get("id")
            if self.solo_lettura:
                self._send(ws, {"id": msg_id, "ok": False,
                                "e": "canale di sola lettura: nessun comando accettato"})
                return
            if method not in _ALLOWED_METHODS:
                self._send(ws, {"id": msg_id, "ok": False, "e": f"metodo sconosciuto: {method}"})
                return
            params = msg.get("p")
            self._requests.put_nowait(
                LocalRequest(ws=ws, msg_id=msg_id, method=method,
                             params=params if isinstance(params, dict) else {})
            )
        except queue.Full:
            self._send(ws, {"id": msg.get("id"), "ok": False,
                            "e": "coda locale piena: comando NON accettato (riprova)"})
        except Exception as ex:  # noqa: BLE001 - messaggio malformato
            logger.debug("[local-ws] messaggio malformato: %s", str(ex)[:120])

    def _send(self, ws: Any, payload: Dict[str, Any]) -> None:
        """Send fire-and-forget dal thread del loop."""
        if self._loop is None:
            return
        try:
            text = json.dumps(payload, default=str)
        except Exception:  # noqa: BLE001
            return
        self._loop.create_task(self._safe_send(ws, text))

    async def _safe_send(self, ws: Any, text: str) -> None:
        self._in_volo += 1              # solo dal thread del loop: nessuna corsa
        try:
            await ws.send(text)
        except Exception:  # noqa: BLE001 - client andato: ignora
            pass
        finally:
            self._in_volo -= 1

    # ------------------------------------------------------- API thread-safe
    def is_active(self) -> bool:
        """True se almeno un client desktop è collegato."""
        return self._n_clients > 0

    def set_hello(self, **extra: Any) -> None:
        self._hello_extra.update(extra)

    def publish(self, topic: str, payload: Any) -> None:
        """Broadcast a tutti i client. No-op senza client/loop. MAI solleva.

        CONTROPRESSIONE (14/09): se il consumatore rallenta, gli invii in volo si
        accumulano DENTRO il processo che gestisce i soldi. Finche' qui passavano
        ladder piccole non contava; ora i bot spingono la scheda intera a ogni
        giro, quindi si mette un tetto: oltre ``_MAX_INVII_IN_VOLO`` si SALTA il
        giro. Mostrare un fotogramma in meno e' sempre meglio che far crescere
        la memoria del bot — e il fotogramma dopo arriva comunque, perche' si
        pubblica lo stato corrente, non un differenziale.
        """
        loop = self._loop
        if loop is None or self._n_clients == 0:
            return
        if self._in_volo > _MAX_INVII_IN_VOLO:
            ora = time.monotonic()
            if ora - self._ultimo_avviso > 30.0:
                self._ultimo_avviso = ora
                logger.warning("[local-ws] %d invii in volo sulla porta %d: salto i push "
                               "finche' il client non recupera.", self._in_volo, self.port)
            return
        try:
            text = json.dumps({"t": topic, "d": payload}, default=str)
        except Exception as ex:  # noqa: BLE001 - payload non serializzabile: dichiara nel log
            logger.warning("[local-ws] publish %s non serializzabile: %s", topic, str(ex)[:120])
            return
        def _broadcast() -> None:
            for ws in list(self._clients):
                loop.create_task(self._safe_send(ws, text))
        try:
            loop.call_soon_threadsafe(_broadcast)
        except RuntimeError:  # loop chiuso
            pass

    def pop_requests(self, max_n: int = 20) -> "list[LocalRequest]":
        """Drena fino a max_n richieste (chiamato dal thread del worker)."""
        out: list[LocalRequest] = []
        for _ in range(max_n):
            try:
                out.append(self._requests.get_nowait())
            except queue.Empty:
                break
        return out

    def respond(self, req: LocalRequest, ok: bool, data: Any = None, error: Optional[str] = None) -> None:
        """Risposta a una richiesta (thread-safe). MAI solleva."""
        loop = self._loop
        if loop is None:
            return
        payload: Dict[str, Any] = {"id": req.msg_id, "ok": ok}
        if data is not None:
            payload["d"] = data
        if error:
            payload["e"] = str(error)[:300]
        try:
            text = json.dumps(payload, default=str)
        except Exception:  # noqa: BLE001
            text = json.dumps({"id": req.msg_id, "ok": False, "e": "risposta non serializzabile"})
        try:
            loop.call_soon_threadsafe(lambda: loop.create_task(self._safe_send(req.ws, text)))
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Singleton per-processo (calcio e tennis girano in PROCESSI separati).
# ---------------------------------------------------------------------------
_CHANNEL: Optional[LocalChannel] = None


def start_channel(port: int, sport: str, solo_lettura: bool = False) -> Optional[LocalChannel]:
    """Avvia (una volta) il canale locale del processo. None se non parte.

    ``solo_lettura=True`` per i canali dei BOT: mostrano e basta, non accettano
    comandi. Vedi ``LocalChannel.__init__``.
    """
    global _CHANNEL
    if _CHANNEL is not None:
        return _CHANNEL
    ch = LocalChannel(port, sport, solo_lettura=solo_lettura)
    if ch.start():
        _CHANNEL = ch
        return ch
    return None


def get_channel() -> Optional[LocalChannel]:
    return _CHANNEL


def channel_active() -> bool:
    ch = _CHANNEL
    return ch is not None and ch.is_active()


def publish(topic: str, payload: Any) -> None:
    """Publish best-effort sul canale del processo (no-op se assente/inattivo)."""
    ch = _CHANNEL
    if ch is not None:
        ch.publish(topic, payload)
