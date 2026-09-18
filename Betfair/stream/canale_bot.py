"""canale_bot.py - F3: le RIGHE dei bot sul canale locale, in sola lettura.

Che cosa risolve. Oggi la Control Room vede posizioni, proposte, attivita' e
stato dei bot SOLO passando dal database: il bot scrive, Supabase propaga, la
pagina ricarica al poll di 30 s. I dati ci sono e sono giusti, ma arrivano
vecchi. Questo modulo aggiunge un secondo percorso, PIU' VELOCE E MAI
ALTERNATIVO: la stessa riga, appena scritta, esce anche sul canale locale del
processo (127.0.0.1).

Le cinque regole, tutte inchiodate da un test
(``Betfair/stream/tests/test_canale_bot_f3_2026_09_18.py``):

1. **Il messaggio E' la riga.** Chiavi e tipi identici alla riga del database,
   snake_case, stessi nomi di colonna. Le uniche chiavi in piu' sono quelle
   della BUSTA (``CHIAVI_META``), dichiarate qui una volta sola.
2. **Il database resta il registro.** Si pubblica DOPO la scrittura riuscita, e
   si pubblica cio' che la scrittura ha RESTITUITO (PostgREST torna di serie la
   rappresentazione della riga: ``return=representation``, nessuna lettura in
   piu'). Mai un messaggio per una riga che sul database non esiste.
3. **Pubblicare non puo' fermare il bot.** Canale giu', porta occupata,
   ``websockets`` assente, client lento, riga non serializzabile: il bot lavora
   identico a oggi. Le eccezioni si inghiottono e si CONTANO: il silenzio totale
   non e' ammesso, il conto finisce nello stato del bot.
4. **Il ``mode`` e' quello della RIGA.** Viaggia perche' sta nella riga, non
   perche' qualcuno lo attacca sapendo com'e' avviato il servizio. Paper e live
   non si sommano mai (regola del 14/09).
5. **Interruttore per processo, via ``.env``, DEFAULT SPENTO.** Acceso solo se
   qualcuno lo scrive davvero (``1``/``true``/``si``/``yes``): vuoto, assente o
   qualunque altra scritta vale spento. E' il verso giusto del guasto, ed e' il
   difetto D2 gia' corretto in F1.

Chi legge deve poter scartare il piu' vecchio fra canale e database. Il
database di queste tabelle non ha sempre un ``updated_at`` (``omega_trades``
non ce l'ha), quindi la busta porta due numeri del PRODUTTORE:
``_pubblicato_ms`` (quando il messaggio e' uscito) e ``_seq`` (un contatore
monotono del processo). Chi tiene una riga letta dal database all'istante T
tiene la piu' recente fra le due confrontando T con ``_pubblicato_ms``; fra due
messaggi del canale decide ``_seq``. Il canale non puo' comunque AGGIUNGERE una
posizione: quali righe esistono lo dice solo il database.

I canali dei bot restano ``solo_lettura=True``: mostrano, non comandano. I
comandi sul canale sono un'altra fase (F6).

MODULO PURO: nessun import di flumine, betfairlightweight, supabase o rete. Lo
importano anche processi in cui flumine non deve entrare mai (l'incidente del
17/09). Test di contratto: ``test_canale_bot_e_un_modulo_puro`` (sottoprocesso).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Optional

logger = logging.getLogger(__name__)

#: Un interruttore e' acceso SOLO se qualcuno lo scrive davvero.
VALORI_ACCESI = frozenset({"1", "true", "si", "yes"})

#: Le chiavi della BUSTA, cioe' le sole che il messaggio ha in piu' della riga.
CHIAVE_FONTE = "fonte"
CHIAVE_SEQ = "_seq"
CHIAVE_PUBBLICATO_MS = "_pubblicato_ms"
CHIAVI_META = frozenset({CHIAVE_FONTE, CHIAVE_SEQ, CHIAVE_PUBBLICATO_MS})

#: I nomi dei topic stanno in UN POSTO SOLO: produttore e consumatore non
#: possono divergere su una stringa scritta due volte (difetto 33 del catalogo).
#: Calcio e tennis hanno topic SEPARATI: non si mischiano nemmeno dentro un
#: payload (invariante B12 del piano).
TOPIC: Mapping[str, str] = MappingProxyType({
    # Mike (47333)
    "mike_posizioni": "mike_posizioni",
    "mike_attivita": "mike_attivita",
    # Omega (47334)
    "omega_posizioni": "omega_posizioni",
    "omega_attivita": "omega_attivita",
    "omega_proposta": "omega_proposta",
    # Safe (47335) - due topic, mai uno solo con un campo sport
    "safe_posizioni_calcio": "safe_posizioni_calcio",
    "safe_posizioni_tennis": "safe_posizioni_tennis",
    "safe_attivita": "safe_attivita",
    "safe_proposta": "safe_proposta",
    # servizio dei 4 bot tennis (47337)
    "tennis_bot_stato": "tennis_bot_stato",
    "tennis_bot_posizioni": "tennis_bot_posizioni",
})

#: La porta del canale dei 4 bot tennis: NUOVA, ma dentro un processo che gira
#: gia' (``tennis_bot_service --bridge-only``, ``desktop/main.js:268``).
#: Nessun processo nuovo.
PORTA_TENNIS_BOT = 47337

#: Nomi degli interruttori, uno per processo. Default SPENTO, sempre.
ENV_MIKE = "MIKE_CANALE_POSIZIONI"
ENV_OMEGA = "OMEGA_CANALE_POSIZIONI"
ENV_SAFE = "SAFE_CANALE_POSIZIONI"
ENV_TENNIS_BOT = "TENNIS_BOT_CANALE"
ENV_PORTA_TENNIS_BOT = "TENNIS_BOT_WS_PORT"

_lock = threading.Lock()
_seq = 0
_conti: Dict[str, Any] = {"pubblicati": 0, "errori": 0, "senza_riga": 0,
                          "ultimo_errore": None}


def acceso(nome_env: str) -> bool:
    """L'interruttore di fase: acceso SOLO se scritto.

    Regola env di progetto: ``(os.getenv(x) or "").strip()`` e mai un ``??`` che
    scambi la stringa vuota per "assente". Qualunque valore diverso da
    ``1``/``true``/``si``/``yes`` vale SPENTO.
    """
    return (os.getenv(nome_env) or "").strip().lower() in VALORI_ACCESI


def _canale() -> Any:
    """Il canale locale di QUESTO processo, o ``None``.

    Import pigro: ``local_channel`` e' leggero, ma tenerlo fuori dagli import di
    testa rende questo modulo importabile anche dove non c'e' nessun canale, e
    lascia ai test un punto solo da sostituire.
    """
    try:
        from . import local_channel

        return local_channel.get_channel()
    except Exception:  # noqa: BLE001 - nessun canale: si lavora senza
        return None


def _prossima_sequenza() -> int:
    global _seq
    with _lock:
        _seq += 1
        return _seq


def busta(riga: Mapping[str, Any]) -> Dict[str, Any]:
    """La riga PIU' la busta. Copia: la riga che va sul database non si tocca.

    Il messaggio resta la riga (stesse chiavi, stessi tipi, stessi nomi di
    colonna); ``CHIAVI_META`` sono le sole tre chiavi in piu', ed esistono per
    dire A CHI LEGGE da dove viene il dato e quanto e' recente.
    """
    msg: Dict[str, Any] = dict(riga)
    msg[CHIAVE_FONTE] = "canale"
    msg[CHIAVE_SEQ] = _prossima_sequenza()
    msg[CHIAVE_PUBBLICATO_MS] = int(time.time() * 1000)
    return msg


def pubblica(topic: str, riga: Mapping[str, Any]) -> bool:
    """Un messaggio sul canale del processo. NON SOLLEVA MAI, non blocca mai.

    Torna ``True`` se il messaggio e' stato consegnato al canale (che a sua
    volta e' best-effort: senza client esce prima ancora di serializzare).
    Ogni eccezione viene inghiottita e CONTATA: un canale rotto non puo'
    fermare il ciclo che gestisce i soldi, ma non puo' nemmeno sparire in
    silenzio.
    """
    canale = _canale()
    if canale is None:
        return False
    try:
        canale.publish(str(topic), busta(riga))
    except Exception as ex:  # noqa: BLE001 - mostrare non ferma mai il bot
        with _lock:
            _conti["errori"] = int(_conti["errori"]) + 1
            _conti["ultimo_errore"] = str(ex)[:200]
        logger.debug("[canale-bot] publish %s KO: %s", topic, str(ex)[:120])
        return False
    with _lock:
        _conti["pubblicati"] = int(_conti["pubblicati"]) + 1
    return True


def righe_scritte(res: Any) -> List[Dict[str, Any]]:
    """Le righe che la scrittura ha RESTITUITO (``res.data``), mai altro.

    PostgREST torna di serie la rappresentazione della riga scritta
    (``return=representation``): leggerla non costa nessuna andata e ritorno in
    piu'. Se non c'e' rappresentazione, non c'e' niente da pubblicare: e' il
    verso giusto del guasto (meglio nessun messaggio che un messaggio per una
    riga che non esiste).
    """
    try:
        dati = getattr(res, "data", None)
        if not isinstance(dati, list):
            return []
        return [r for r in dati if isinstance(r, dict)]
    except Exception:  # noqa: BLE001 - risposta storta: nessuna riga
        return []


def pubblica_scritte(topic: str, res: Any) -> int:
    """Pubblica ogni riga restituita dalla scrittura. Torna quante ne sono uscite."""
    righe = righe_scritte(res)
    if not righe:
        if res is not None:
            with _lock:
                _conti["senza_riga"] = int(_conti["senza_riga"]) + 1
        return 0
    usciti = 0
    for riga in righe:
        if pubblica(topic, riga):
            usciti += 1
    return usciti


def pubblica_scritte_per(scegli_topic: Callable[[Dict[str, Any]], Optional[str]],
                         res: Any) -> int:
    """Come ``pubblica_scritte``, ma il topic lo sceglie la RIGA.

    Serve al bot Safe, che tiene calcio e tennis su due topic diversi: il topic
    si decide dal campo ``sport`` della riga, non da come e' avviato il
    servizio. Una riga di cui non si sa lo sport non esce (fail-closed: meglio
    niente che sul topic sbagliato).
    """
    righe = righe_scritte(res)
    if not righe:
        if res is not None:
            with _lock:
                _conti["senza_riga"] = int(_conti["senza_riga"]) + 1
        return 0
    usciti = 0
    for riga in righe:
        try:
            topic = scegli_topic(riga)
        except Exception as ex:  # noqa: BLE001
            with _lock:
                _conti["errori"] = int(_conti["errori"]) + 1
                _conti["ultimo_errore"] = str(ex)[:200]
            continue
        if not topic:
            continue
        if pubblica(topic, riga):
            usciti += 1
    return usciti


def statistiche() -> Dict[str, Any]:
    """Che cosa e' successo alla pubblicazione: messaggi usciti, eccezioni
    inghiottite, scritture senza rappresentazione. Finisce nello stato del bot:
    un canale che perde messaggi lo si legge, non lo si deduce dai log."""
    with _lock:
        return dict(_conti)


def azzera_statistiche() -> None:
    """Solo per i test e per il riavvio: azzera i contatori e la sequenza."""
    global _seq
    with _lock:
        _seq = 0
        _conti.update({"pubblicati": 0, "errori": 0, "senza_riga": 0,
                       "ultimo_errore": None})
