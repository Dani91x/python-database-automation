"""canale_bot_tennis.py - 24/09: i 4 bot tennis in Control Room DAL LORO CANALE (47337).

Decisione dell'utente (24/09): "righe nuove dei bot in Control Room subito, non
al poll dei 30 s; bot tennis dal loro canale".

IL PROBLEMA DI TOPOLOGIA (verificato nel codice, non dedotto). I 4 bot tennis
vivono in DUE processi:

* il RUNNER tennis (``tennis_runner``, canale 47332) ospita i bot, piazza gli
  ordini e scrive lo specchio ``tennis_live_orders`` (``_mirror_order`` ->
  ``tennis_db.upsert_tennis_order``) e le righe di armatura per partita
  (``tennis_bot_control``: arming/running/stopped);
* il PONTE (``tennis_bot_service --bridge-only``, canale 47337) scrive gli
  interruttori per bot (``tennis_bot_service_control``) e le richieste di
  armatura (``tennis_bot_control``: requested/stopping).

Un processo ha UN canale (difetto D1): le righe d'ordine scritte dal runner non
possono uscire direttamente sul 47337. Qui ci sono i due pezzi che chiudono il
giro SENZA letture in piu' sul database e SENZA processi nuovi:

1. ``InoltroPosizioni`` (gira nel PONTE): si aggancia al canale del runner come
   LETTORE (``/lettore/tennis_bot_posizioni``: non conta come desktop, non
   manda comandi, riceve solo quel topic) e ripubblica sul 47337 il messaggio
   IDENTICO (riga del database + busta del produttore: ``_seq`` e
   ``_pubblicato_ms`` restano quelli del runner, cioe' dell'istante DOPO la
   scrittura riuscita). Il ponte non tocca il contenuto: inoltra.
2. ``CancelloBotControl`` (gira nel RUNNER): la SVEGLIA del
   ``bot_control_worker``. Oggi il worker legge ``tennis_bot_control`` ogni 3 s.
   Con ``TENNIS_RUNNER_SVEGLIA_CANALE=1`` il runner ascolta il 47337
   (``tennis_bot_armamento``, le richieste scritte dal ponte) e il giro parte
   subito, con un PAVIMENTO di 1 s fra due giri anticipati; senza sveglie il
   worker gira esattamente ogni 3 s come oggi (il poll resta il ripiego).

Interruttori, DEFAULT SPENTO (``canale_bot.acceso``):
* ``TENNIS_BOT_CANALE`` (gia' esistente, lo stesso del canale 47337): accende
  la pubblicazione delle righe d'ordine dei bot e l'inoltro nel ponte;
* ``TENNIS_RUNNER_SVEGLIA_CANALE`` (NUOVO): accende la sveglia del worker di
  armatura nel runner. E' un interruttore a parte perche' cambia la cadenza di
  un worker del processo che gestisce i soldi.

MODULO PURO: nessun import di flumine, betfairlightweight, supabase o database.
``websockets`` entra solo dentro il thread del client (import pigro).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

from .. import canale_bot as _cb

logger = logging.getLogger(__name__)

#: Le chiavi dei 4 bot: sono il ``source`` delle loro righe in
#: ``tennis_live_orders`` (stessa lista di ``tennis_bot_service._BOT_KEYS`` e
#: della RPC ``get_tennis_bot_orders_today``; un test di contratto le confronta).
SORGENTI_BOT_TENNIS = frozenset({"tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing"})

#: Topic delle righe d'ordine dei bot (riga di ``tennis_live_orders`` + busta).
TOPIC_POSIZIONI = _cb.TOPIC["tennis_bot_posizioni"]
#: Topic delle righe di armatura per partita (riga di ``tennis_bot_control``).
TOPIC_ARMAMENTO = _cb.TOPIC["tennis_bot_armamento"]

#: Porta del canale del RUNNER tennis (lo stesso nome che usa il runner).
ENV_PORTA_RUNNER = "TENNIS_LOCAL_WS_PORT"
PORTA_RUNNER = 47332

#: Interruttore della sveglia del worker di armatura nel runner. SPENTO di serie.
ENV_SVEGLIA_RUNNER = "TENNIS_RUNNER_SVEGLIA_CANALE"
#: Pavimento fra due giri ANTICIPATI (s). La sorgente e' umana (un clic che il
#: ponte traduce in una riga): come ``tennis_bot_service.MINIMO_SVEGLIA_S``.
PAVIMENTO_SVEGLIA_S = 1.0
#: Passo del worker quando la sveglia e' accesa: il worker viene chiamato ogni
#: PASSO ma lavora (e legge il database) solo quando il cancello lo dice.
PASSO_WORKER_S = 0.25

_ATTESE_S = (0.5, 1.0, 2.0, 5.0)
_RECV_TIMEOUT_S = 2.0


def porta_runner() -> int:
    """La porta del canale del runner tennis: ``TENNIS_LOCAL_WS_PORT`` o 47332."""
    grezza = (os.getenv(ENV_PORTA_RUNNER) or "").strip()
    if not grezza:
        return PORTA_RUNNER
    try:
        return int(grezza)
    except ValueError:
        return PORTA_RUNNER


def e_riga_di_bot(riga: Any) -> bool:
    """La riga d'ordine e' di uno dei 4 bot? (``source`` = chiave del bot).
    Gli ordini manuali (``source`` = 'manual') non escono su questo topic."""
    return isinstance(riga, dict) and str(riga.get("source") or "") in SORGENTI_BOT_TENNIS


# =========================================================================
# 1) L'INOLTRO NEL PONTE: runner (47332) -> ponte (47337)
# =========================================================================
def _connetti_ws(url: str) -> Any:
    """Client WebSocket di sola lettura. Import PIGRO: senza ``websockets`` il
    modulo resta importabile e il ponte lavora esattamente come oggi."""
    from websockets.sync.client import connect

    return connect(url, open_timeout=5.0, close_timeout=1.0, max_queue=64)


def _pubblica_sul_canale_del_processo(topic: str, messaggio: Dict[str, Any]) -> bool:
    """Consegna il messaggio GIA' IMBUSTATO al canale di questo processo
    (il 47337 nel ponte). Non solleva mai."""
    try:
        from .. import local_channel as _lc

        ch = _lc.get_channel()
        if ch is None:
            return False
        ch.publish(str(topic), messaggio)
        return True
    except Exception:  # noqa: BLE001 - mostrare non ferma mai il ponte
        return False


class InoltroPosizioni:
    """LETTORE del canale del runner tennis che ripubblica sul canale del
    processo (47337) le righe d'ordine dei 4 bot, IDENTICHE.

    Nessuna lettura al database, nessun comando: se il runner non c'e' o il
    canale cade, si riprova con attesa crescente e la pagina resta al poll.
    """

    def __init__(self, *, porta_ws: Optional[int] = None, host: str = "127.0.0.1",
                 connetti: Optional[Callable[[str], Any]] = None,
                 pubblica: Optional[Callable[[str, Dict[str, Any]], bool]] = None) -> None:
        self.porta = int(porta_ws) if porta_ws is not None else porta_runner()
        self.host = host
        self._connetti = connetti or _connetti_ws
        self._pubblica = pubblica or _pubblica_sul_canale_del_processo
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._detto = False
        self._conti: Dict[str, Any] = {
            "connessioni": 0, "riagganci": 0, "ricevuti": 0, "inoltrati": 0,
            "scartati": 0, "errori": 0, "ultimo_errore": None, "collegato": False,
        }

    @property
    def url(self) -> str:
        return "ws://%s:%d%s%s" % (self.host, self.porta, "/lettore/", TOPIC_POSIZIONI)

    def avvia(self) -> bool:
        if self._thread is not None:
            return True
        self._thread = threading.Thread(target=self._gira, daemon=True,
                                        name="tennis-bot-inoltro")
        self._thread.start()
        return True

    def ferma(self) -> None:
        self._stop.set()

    def statistiche(self) -> Dict[str, Any]:
        with self._lock:
            return {**self._conti, "url": self.url}

    def _conta(self, chiave: str, errore: Optional[str] = None) -> None:
        with self._lock:
            self._conti[chiave] = int(self._conti[chiave]) + 1
            if errore is not None:
                self._conti["ultimo_errore"] = errore[:200]

    def _gira(self) -> None:
        i = 0
        while not self._stop.is_set():
            try:
                with self._connetti(self.url) as ws:
                    with self._lock:
                        self._conti["collegato"] = True
                    self._conta("connessioni")
                    self._detto = False
                    i = 0
                    logger.info("[tennis-bot-inoltro] agganciato come lettore a %s", self.url)
                    while not self._stop.is_set():
                        try:
                            grezzo = ws.recv(timeout=_RECV_TIMEOUT_S)
                        except TimeoutError:
                            continue
                        self.inoltra(grezzo)
            except Exception as ex:  # noqa: BLE001 - il ponte vive senza runner
                self._conta("errori", str(ex))
                if not self._detto:
                    self._detto = True
                    logger.info("[tennis-bot-inoltro] canale del runner %s non disponibile "
                                "(%s): le righe dei bot tennis restano al poll della "
                                "pagina, riprovo da solo.", self.url, str(ex)[:120])
            finally:
                with self._lock:
                    self._conti["collegato"] = False
            if self._stop.is_set():
                break
            self._conta("riagganci")
            self._stop.wait(_ATTESE_S[min(i, len(_ATTESE_S) - 1)])
            i += 1

    def inoltra(self, grezzo: Any) -> bool:
        """Un messaggio del runner. ``True`` se e' stato ripubblicato.

        Si inoltra SOLO un push ``tennis_bot_posizioni`` con la busta del canale
        (``fonte`` = 'canale', ``_seq``, ``_pubblicato_ms``) e la riga di un bot:
        tutto il resto (hello, messaggi storti, ordini manuali) si scarta. Il
        messaggio esce IDENTICO: niente busta nuova, niente chiavi aggiunte.
        NON SOLLEVA MAI (e' il pezzo che i test esercitano senza socket).
        """
        try:
            msg = json.loads(grezzo) if isinstance(grezzo, (str, bytes, bytearray)) else grezzo
        except (ValueError, TypeError):
            self._conta("scartati")
            return False
        if not isinstance(msg, dict) or msg.get("t") != TOPIC_POSIZIONI:
            return False                    # hello e altro: non sono righe
        self._conta("ricevuti")
        riga = msg.get("d")
        if (not e_riga_di_bot(riga) or riga.get(_cb.CHIAVE_FONTE) != "canale"
                or not isinstance(riga.get(_cb.CHIAVE_SEQ), int)
                or not isinstance(riga.get(_cb.CHIAVE_PUBBLICATO_MS), int)):
            self._conta("scartati")
            return False
        try:
            ok = bool(self._pubblica(TOPIC_POSIZIONI, riga))
        except Exception as ex:  # noqa: BLE001 - inoltrare non ferma il client
            self._conta("errori", str(ex))
            return False
        if ok:
            self._conta("inoltrati")
        return ok


_INOLTRO: Optional[InoltroPosizioni] = None


def avvia_inoltro_nel_ponte() -> Optional[InoltroPosizioni]:
    """Accende l'inoltro nel ponte. SOLO con ``TENNIS_BOT_CANALE`` acceso e con
    il canale del processo attivo (senza 47337 non c'e' dove ripubblicare).
    Non solleva mai: senza inoltro il ponte fa esattamente quello di oggi."""
    global _INOLTRO
    if not _cb.acceso(_cb.ENV_TENNIS_BOT):
        return None
    try:
        from .. import local_channel as _lc

        if _lc.get_channel() is None:
            return None
        if _INOLTRO is None:
            _INOLTRO = InoltroPosizioni()
            _INOLTRO.avvia()
            logger.info("[tennis-bot-inoltro] attivo: le righe d'ordine dei 4 bot dal "
                        "runner (%s) escono anche sul canale del ponte.", _INOLTRO.url)
        return _INOLTRO
    except Exception as ex:  # noqa: BLE001 - l'inoltro e' un'accelerazione
        logger.warning("[tennis-bot-inoltro] avvio KO: %s", str(ex)[:160])
        return None


def statistiche_inoltro() -> Optional[Dict[str, Any]]:
    return _INOLTRO.statistiche() if _INOLTRO is not None else None


# =========================================================================
# 2) LA SVEGLIA DEL WORKER DI ARMATURA NEL RUNNER
# =========================================================================
class CancelloBotControl:
    """Decide, a ogni chiamata del worker, se questo giro LAVORA.

    * senza sveglie: lavora ogni ``cadenza_s`` (3 s, la cadenza di oggi): le
      letture al minuto sono IDENTICHE a oggi;
    * con una sveglia alzata: lavora appena sono passati ``pavimento_s`` (1 s)
      dall'ultimo giro che ha lavorato. Un giro anticipato rimette a zero la
      cadenza: al massimo ``60 / pavimento_s`` giri al minuto anche sotto una
      tempesta di sveglie, e solo finche' la tempesta dura.

    ``alza(motivo, minimo_s)`` ha la stessa firma di ``sveglia_canale.Sveglia``:
    ``AscoltoScan`` lo usa senza sapere la differenza. NON SOLLEVA MAI.
    """

    def __init__(self, cadenza_s: float, pavimento_s: float = PAVIMENTO_SVEGLIA_S,
                 ora: Optional[Callable[[], float]] = None) -> None:
        self.cadenza_s = max(0.0, float(cadenza_s))
        self.pavimento_s = max(0.0, float(pavimento_s))
        self._ora: Callable[[], float] = ora or time.monotonic
        self._lock = threading.Lock()
        self._alzata = False
        self._ultimo: Optional[float] = None
        self._conti: Dict[str, Any] = {
            "sveglie": 0, "giri_per_cadenza": 0, "giri_per_sveglia": 0,
            "ultimo_motivo": None,
        }

    def alza(self, motivo: str = "armamento", minimo_s: Optional[float] = None) -> None:  # noqa: ARG002
        with self._lock:
            self._alzata = True
            self._conti["sveglie"] = int(self._conti["sveglie"]) + 1
            self._conti["ultimo_motivo"] = str(motivo)

    def deve_girare(self) -> bool:
        ora = self._ora()
        with self._lock:
            if self._ultimo is None or ora - self._ultimo >= self.cadenza_s:
                self._ultimo = ora
                self._alzata = False
                self._conti["giri_per_cadenza"] = int(self._conti["giri_per_cadenza"]) + 1
                return True
            if self._alzata and ora - self._ultimo >= self.pavimento_s:
                self._ultimo = ora
                self._alzata = False
                self._conti["giri_per_sveglia"] = int(self._conti["giri_per_sveglia"]) + 1
                return True
            return False

    def statistiche(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._conti)


def sveglia_runner_accesa() -> bool:
    return _cb.acceso(ENV_SVEGLIA_RUNNER)


def avvia_ascolto_armamento(cancello: CancelloBotControl,
                            interessa: Callable[[str], bool],
                            porta_ws: Optional[int] = None,
                            connetti: Optional[Callable[[str], Any]] = None) -> Any:
    """Aggancia il runner al canale del PONTE (47337, topic
    ``tennis_bot_armamento``): una riga di armatura scritta dal ponte per una
    partita che il runner segue alza la sveglia del worker. Riusa
    ``sveglia_canale.AscoltoScan`` (legge SOLO ``event_id``, butta il resto).
    Torna l'ascolto o ``None``. Non solleva mai."""
    try:
        from .. import sveglia_canale as _SV

        porta = porta_ws
        if porta is None:
            try:
                porta = int((os.environ.get(_cb.ENV_PORTA_TENNIS_BOT) or "").strip()
                            or _cb.PORTA_TENNIS_BOT)
            except ValueError:
                porta = _cb.PORTA_TENNIS_BOT
        ascolto = _SV.AscoltoScan(cancello, interessa, topic=(TOPIC_ARMAMENTO,),
                                  porta=porta, nome="tennis-armamento", connetti=connetti)
        return ascolto if ascolto.avvia() else None
    except Exception as ex:  # noqa: BLE001 - la sveglia e' un'accelerazione
        logger.warning("[tennis-runner] aggancio della sveglia di armatura KO: %s",
                       str(ex)[:160])
        return None
