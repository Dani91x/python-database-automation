"""sveglia_canale.py - F5/F6: il ciclo dei bot si SVEGLIA, non si accorcia.

Che cosa risolve. Oggi Mike dorme 2 s (30 s a vuoto), Omega 20 s (60 s a vuoto)
e il ponte dei 4 bot tennis 15 s. Se un gol, una quota o un comando dell'utente
arrivano un istante DOPO l'inizio della dormita, il bot se ne accorge solo al
giro dopo. Il rimedio NON e' accorciare la dormita - moltiplicherebbe le letture
al database, che il 13/09 e' caduto per IO - ma SVEGLIARE il ciclo: la dormita
resta lunga, e finisce prima solo quando e' successo qualcosa che riguarda
QUESTO bot.

Le cinque regole, ognuna con il suo test
(``Betfair/stream/tests/test_sveglia_canale_f5_f6_2026_09_18.py``):

1. **A interruttore spento non cambia una sola istruzione.** Il bot continua a
   chiamare ``time.sleep(x)`` con lo stesso ``x`` di oggi, nessun thread parte,
   nessuna porta viene aperta. Gli interruttori sono ``OMEGA_SVEGLIA_CANALE``,
   ``MIKE_SVEGLIA_CANALE``, ``TENNIS_BOT_SVEGLIA_CANALE``: accesi SOLO se
   qualcuno li scrive davvero (``1``/``true``/``si``/``yes``), come in F1/F3.
2. **Le letture al minuto non possono crescere.** ``Sveglia.attendi`` ha un
   PAVIMENTO: il giro non riparte mai prima di ``minimo_s`` dall'inizio del giro
   precedente. Chi chiama passa come pavimento la CADENZA ATTIVA DI OGGI, cioe'
   il passo piu' veloce al quale quel bot gia' gira: da li' in poi, per quante
   sveglie arrivino, i giri al minuto restano quelli del caso peggiore di oggi.
   Il guadagno e' tutto sul lato lento (Omega a vuoto: 60 s -> il pavimento).
3. **La sveglia non porta dati.** Del messaggio di scan si legge SOLO
   ``event_id``, per chiedere al bot «ti interessa?»; il payload non si conserva
   e non entra in nessuna decisione. Le quote il bot continua a leggerle dove le
   legge oggi. Del messaggio di sveglia da UI si legge SOLO ``motivo``: qualunque
   altro campo (prezzo, taglia, selezione) e' IGNORATO. Il comando vero resta la
   riga sul database, con le guardie e l'idempotenza di oggi.
4. **Un canale muto non ha nessun effetto.** ``websockets`` assente, porta
   chiusa, messaggio storto, filtro che solleva: il ciclo prosegue identico e si
   scrive UNA riga di log informativa, non un fiume di warning.
5. **Modulo PURO**: nessun import di flumine, betfairlightweight, supabase o
   database. Lo importano processi in cui flumine non deve entrare mai
   (l'incidente del 17/09). Test di contratto in SOTTOPROCESSO.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from .canale_bot import VALORI_ACCESI, acceso  # una sola definizione del verso

logger = logging.getLogger(__name__)

__all__ = [
    "VALORI_ACCESI", "acceso",
    "ENV_OMEGA_SVEGLIA", "ENV_MIKE_SVEGLIA", "ENV_TENNIS_SVEGLIA",
    "ENV_PORTA_SCAN", "PORTA_SCAN", "TOPIC_SCAN_CALCIO", "TOPIC_SCAN_TENNIS",
    "METODO_SVEGLIA", "MOTIVI_SVEGLIA", "MINIMO_UI_S",
    "messaggio_di_sveglia", "Sveglia", "AscoltoScan",
]

#: Interruttori di fase, uno per bot. Assenti = SPENTI, sempre.
ENV_OMEGA_SVEGLIA = "OMEGA_SVEGLIA_CANALE"
ENV_MIKE_SVEGLIA = "MIKE_SVEGLIA_CANALE"
ENV_TENNIS_SVEGLIA = "TENNIS_BOT_SVEGLIA_CANALE"

#: Il canale dello SCANNER (F1): porta e topic. I nomi stanno in un posto solo,
#: cosi' produttore e consumatore non possono divergere su una stringa scritta
#: due volte (difetto 33 del catalogo).
ENV_PORTA_SCAN = "SAFE_SCAN_WS_PORT"
PORTA_SCAN = 47336
TOPIC_SCAN_CALCIO = "scan_calcio"
TOPIC_SCAN_TENNIS = "scan_tennis"

#: Il SOLO messaggio che i canali dei bot (47333 Mike, 47334 Omega, 47337 bot
#: tennis) devono poter ricevere: ``{"m": "sveglia", "p": {"motivo": ...}}``.
#: Non porta nessun parametro d'ordine, e non ne porta MAI: il comando vero e'
#: la riga sul database.
METODO_SVEGLIA = "sveglia"
MOTIVI_SVEGLIA = frozenset({"approvazione", "comando"})

#: Pavimento della sveglia che arriva dalla UI. E' piu' basso di quello dello
#: scan perche' la sorgente e' UMANA (un clic su «approva» o «avvia»), non una
#: macchina che pubblica quattro volte al secondo: il ritmo lo mette la mano
#: dell'utente, e ogni clic costa gia' oggi una scrittura sul database piu' la
#: lettura del bot al giro dopo.
MINIMO_UI_S = 1.0

#: Riconnessione del client: attesa che cresce, e un tetto.
_ATTESA_MIN_S = 1.0
_ATTESA_MAX_S = 30.0
#: Ogni quanto il client torna a guardare se gli hanno detto di fermarsi.
_RECV_TIMEOUT_S = 5.0
#: Fetta di attesa quando il chiamante passa anche un evento di STOP.
_FETTA_S = 0.25


def porta_scan() -> int:
    """La porta del canale dello scanner: ``SAFE_SCAN_WS_PORT`` o 47336."""
    grezzo = (os.getenv(ENV_PORTA_SCAN) or "").strip()
    if not grezzo:
        return PORTA_SCAN
    try:
        return int(grezzo)
    except ValueError:
        return PORTA_SCAN


def messaggio_di_sveglia(params: Any) -> Optional[str]:
    """Il MOTIVO se ``params`` e' una sveglia valida, altrimenti ``None``.

    Si legge SOLO ``motivo``, e solo se e' uno dei due ammessi. Qualunque altro
    campo - ``price``, ``size``, ``selection_id``, ``market_id``, ``side`` - e'
    IGNORATO: sul canale non passano parametri d'ordine, ne' oggi ne' mai. Un
    motivo sconosciuto non sveglia niente (fail-closed).
    """
    if not isinstance(params, dict):
        return None
    motivo = str(params.get("motivo") or "").strip().lower()
    return motivo if motivo in MOTIVI_SVEGLIA else None


class Sveglia:
    """L'evento che fa ripartire il ciclo, con il suo PAVIMENTO.

    ``attendi(timeout_s, minimo_s)`` sostituisce ``time.sleep(timeout_s)``:
    torna appena qualcuno ha chiamato ``alza()``, ma **mai prima** di
    ``minimo_s`` dall'inizio del giro precedente, e comunque allo scadere di
    ``timeout_s`` (la dormita di oggi). Il pavimento e' la ragione per cui le
    letture al minuto non possono crescere: al massimo ``60/minimo_s`` giri.

    Una sveglia puo' portare un pavimento PROPRIO piu' basso (``alza(minimo_s=)``):
    serve alla sveglia della UI, che e' rara e umana, mentre quella dello scan e'
    continua e va tenuta alla cadenza attiva del bot. Fra piu' sveglie pendenti
    vince il pavimento piu' basso, ed e' il verso giusto: chi ha piu' fretta e'
    l'utente che ha appena firmato.
    """

    def __init__(self, nome: str,
                 ora: Optional[Callable[[], float]] = None,
                 dormi: Optional[Callable[[float], None]] = None) -> None:
        self.nome = str(nome)
        self._ora: Callable[[], float] = ora or time.monotonic
        self._dormi: Callable[[float], None] = dormi or time.sleep
        self._evento = threading.Event()
        self._lock = threading.Lock()
        self._pavimento: Optional[float] = None
        self._ultimo_giro: float = self._ora()
        self._conti: Dict[str, Any] = {
            "sveglie": 0, "da_scan": 0, "da_ui": 0,
            "usate": 0, "scartate_dal_minimo": 0, "per_cadenza": 0,
            "ultimo_motivo": None,
        }

    # ------------------------------------------------------------------ alza
    def alza(self, motivo: str = "scan", minimo_s: Optional[float] = None) -> None:
        """Sveglia il ciclo. NON SOLLEVA MAI: la chiama un thread di rete."""
        with self._lock:
            self._conti["sveglie"] = int(self._conti["sveglie"]) + 1
            if str(motivo) == "scan":
                self._conti["da_scan"] = int(self._conti["da_scan"]) + 1
            else:
                self._conti["da_ui"] = int(self._conti["da_ui"]) + 1
            self._conti["ultimo_motivo"] = str(motivo)
            if minimo_s is not None:
                try:
                    p = max(0.0, float(minimo_s))
                except (TypeError, ValueError):
                    p = None  # type: ignore[assignment]
                if p is not None:
                    self._pavimento = p if self._pavimento is None else min(self._pavimento, p)
        self._evento.set()

    # --------------------------------------------------------------- attendi
    def attendi(self, timeout_s: float, minimo_s: float,
                interrompi: Optional[threading.Event] = None) -> str:
        """La dormita svegliabile. Torna ``cadenza``|``sveglia``|``interrotto``.

        ``timeout_s`` e' la dormita di oggi (non si allunga e non si accorcia da
        sola); ``minimo_s`` e' il pavimento di serie, cioe' la cadenza ATTIVA del
        bot. ``interrompi`` e' l'evento di stop del servizio, quando ce n'e' uno:
        senza di esso si aspetta in una sola chiamata, senza consumare CPU.
        """
        try:
            timeout_s = max(0.0, float(timeout_s))
        except (TypeError, ValueError):
            timeout_s = 0.0
        try:
            minimo_s = max(0.0, float(minimo_s))
        except (TypeError, ValueError):
            minimo_s = 0.0
        scadenza = self._ora() + timeout_s
        scartata = False
        esito = "cadenza"
        while True:
            if interrompi is not None and interrompi.is_set():
                esito = "interrotto"
                break
            rimasto = scadenza - self._ora()
            if rimasto <= 0.0:
                esito = "cadenza"
                break
            fetta = rimasto if interrompi is None else min(rimasto, _FETTA_S)
            if not self._evento.wait(fetta):
                continue                      # niente sveglia: si ricicla
            with self._lock:
                pavimento = self._pavimento if self._pavimento is not None else minimo_s
            trascorso = self._ora() - self._ultimo_giro
            if trascorso >= pavimento:
                self._evento.clear()
                with self._lock:
                    self._pavimento = None
                    self._conti["usate"] = int(self._conti["usate"]) + 1
                esito = "sveglia"
                break
            # troppo presto: si aspetta il pavimento, ma MAI oltre la cadenza.
            if not scartata:
                scartata = True
                with self._lock:
                    self._conti["scartate_dal_minimo"] = \
                        int(self._conti["scartate_dal_minimo"]) + 1
            attesa = min(pavimento - trascorso, max(0.0, scadenza - self._ora()))
            if attesa > 0.0:
                self._dormi(attesa)
        if esito == "cadenza":
            with self._lock:
                self._conti["per_cadenza"] = int(self._conti["per_cadenza"]) + 1
        self._ultimo_giro = self._ora()
        return esito

    # ----------------------------------------------------------------- stato
    def statistiche(self) -> Dict[str, Any]:
        """Quante sveglie, quante usate, quante trattenute dal pavimento. Finisce
        nello stato che il bot gia' scrive: un pavimento che morde troppo lo si
        legge, non lo si deduce."""
        with self._lock:
            return dict(self._conti)

    def azzera(self) -> None:
        """Solo per i test e per il riavvio del banco."""
        self._evento.clear()
        with self._lock:
            self._pavimento = None
            self._conti.update({"sveglie": 0, "da_scan": 0, "da_ui": 0, "usate": 0,
                                "scartate_dal_minimo": 0, "per_cadenza": 0,
                                "ultimo_motivo": None})
        self._ultimo_giro = self._ora()


def _connetti_ws(url: str) -> Any:
    """Client WebSocket di sola lettura. Import PIGRO: senza ``websockets`` il
    modulo resta importabile e il bot lavora esattamente come oggi."""
    from websockets.sync.client import connect

    return connect(url, open_timeout=5.0, close_timeout=1.0, max_queue=16)


class AscoltoScan:
    """Client del canale dello scanner (47336) che NON conserva i payload.

    A Mike e a Omega non serve il prezzo dal canale: serve sapere CHE qualcosa
    e' cambiato su un evento che stanno seguendo. Quindi di ogni messaggio si
    legge un solo campo, ``event_id``, lo si passa al filtro ``interessa`` del
    bot (che decide su cio' che ha GIA' in memoria: nessuna lettura al database)
    e, se interessa, si alza la ``Sveglia``. Il resto del messaggio viene buttato
    prima del giro dopo.

    Non solleva mai verso il bot: gira in un thread daemon, riconnette con
    attesa crescente e conta cio' che gli succede.
    """

    def __init__(self, sveglia: Sveglia,
                 interessa: Callable[[str], bool],
                 topic: Iterable[str] = (TOPIC_SCAN_CALCIO,),
                 porta: Optional[int] = None,
                 nome: str = "scan",
                 connetti: Optional[Callable[[str], Any]] = None) -> None:
        self.sveglia = sveglia
        self._interessa = interessa
        self._topic: Tuple[str, ...] = tuple(str(t) for t in topic)
        self._porta = int(porta) if porta is not None else porta_scan()
        self.nome = str(nome)
        self._connetti = connetti or _connetti_ws
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._conti: Dict[str, Any] = {
            "connessioni": 0, "riconnessioni": 0, "messaggi": 0,
            "sveglie": 0, "scartati": 0, "errori": 0, "ultimo_errore": None,
        }

    @property
    def url(self) -> str:
        return "ws://127.0.0.1:%d" % self._porta

    # -------------------------------------------------------------- ciclo di vita
    def avvia(self) -> bool:
        """Accende il thread. ``False`` (con UNA riga di log) se ``websockets``
        non c'e': senza client il bot dorme come oggi, e va bene cosi'."""
        if self._thread is not None:
            return True
        try:
            import websockets  # noqa: F401  - solo per sapere se c'e'
        except Exception as ex:  # noqa: BLE001 - dipendenza opzionale
            logger.info("[sveglia:%s] 'websockets' non disponibile (%s): il ciclo "
                        "resta alla cadenza di oggi.", self.nome, str(ex)[:120])
            return False
        self._thread = threading.Thread(target=self._giro, daemon=True,
                                        name="sveglia-%s" % self.nome)
        self._thread.start()
        return True

    def ferma(self) -> None:
        self._stop.set()

    def attivo(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def statistiche(self) -> Dict[str, Any]:
        with self._lock:
            return {**self._conti, "porta": self._porta, "topic": list(self._topic)}

    # -------------------------------------------------------------------- filo
    def _giro(self) -> None:
        attesa = _ATTESA_MIN_S
        primo_errore_detto = False
        while not self._stop.is_set():
            try:
                with self._connetti(self.url) as ws:
                    with self._lock:
                        self._conti["connessioni"] = int(self._conti["connessioni"]) + 1
                    attesa = _ATTESA_MIN_S
                    primo_errore_detto = False
                    logger.info("[sveglia:%s] agganciato a %s (topic: %s)",
                                self.nome, self.url, ", ".join(self._topic))
                    while not self._stop.is_set():
                        try:
                            grezzo = ws.recv(timeout=_RECV_TIMEOUT_S)
                        except TimeoutError:
                            continue          # nessun messaggio: si riguarda lo stop
                        self.tratta(grezzo)
            except Exception as ex:  # noqa: BLE001 - il canale non ferma mai il bot
                with self._lock:
                    self._conti["errori"] = int(self._conti["errori"]) + 1
                    self._conti["ultimo_errore"] = str(ex)[:200]
                if not primo_errore_detto:
                    primo_errore_detto = True
                    logger.info("[sveglia:%s] canale %s non raggiungibile (%s): "
                                "il ciclo resta alla cadenza di oggi, riprovo da solo.",
                                self.nome, self.url, str(ex)[:120])
            if self._stop.wait(attesa):
                break
            with self._lock:
                self._conti["riconnessioni"] = int(self._conti["riconnessioni"]) + 1
            attesa = min(attesa * 2.0, _ATTESA_MAX_S)

    def tratta(self, grezzo: Any) -> bool:
        """Un messaggio: si legge il topic e ``event_id``, NIENT'ALTRO.

        Torna ``True`` se ha alzato la sveglia. Pubblica per i test: e' il punto
        in cui si dimostra che il payload non viene conservato.
        """
        try:
            msg = json.loads(grezzo) if isinstance(grezzo, (str, bytes, bytearray)) else grezzo
        except Exception:  # noqa: BLE001 - messaggio storto: si butta
            with self._lock:
                self._conti["scartati"] = int(self._conti["scartati"]) + 1
            return False
        if not isinstance(msg, dict) or str(msg.get("t") or "") not in self._topic:
            return False
        with self._lock:
            self._conti["messaggi"] = int(self._conti["messaggi"]) + 1
        dati = msg.get("d")
        event_id = str((dati or {}).get("event_id") or "") if isinstance(dati, dict) else ""
        if not event_id:
            with self._lock:
                self._conti["scartati"] = int(self._conti["scartati"]) + 1
            return False
        try:
            interessa = bool(self._interessa(event_id))
        except Exception as ex:  # noqa: BLE001 - un filtro che solleva NON sveglia
            with self._lock:
                self._conti["errori"] = int(self._conti["errori"]) + 1
                self._conti["ultimo_errore"] = str(ex)[:200]
            return False
        if not interessa:
            with self._lock:
                self._conti["scartati"] = int(self._conti["scartati"]) + 1
            return False
        with self._lock:
            self._conti["sveglie"] = int(self._conti["sveglie"]) + 1
        self.sveglia.alza("scan")
        return True
