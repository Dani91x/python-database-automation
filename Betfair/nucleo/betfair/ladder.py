"""ladder.py - il ladder verso la UI a OGNI cambio del book (minimo 20 ms), stesso JSON di oggi.

Scopo (tappa T6, scheda A P3, gap L-02 di ``02_COMPETITOR.md`` par. 6.2): oggi il
ladder della UI esce da un ``ladder_worker`` che gira a giro fisso di 200 ms
(``Betfair/stream/ladder_canale.py``, ``config_stream.py:74``) e, nello STESSO
thread, scrive anche il DB (``live_ladder``). Qui il ladder si pubblica quando il
book cambia, con una coalescenza minima di 20 ms PER MERCATO (due book dello
stesso mercato a meno di 20 ms si fondono nell'ultimo, che e' uno stato completo:
nessun dato perso a meta'), e il DB, se c'e', va in un thread SUO.

Parita' (provata in ``tests/test_a2_ladder_parita.py`` su ogni book ricostruito
dalle registrazioni vere con il listener vero di betfairlightweight):
* payload e firma IDENTICI a ``runner.py`` (``_as_levels``, ``compute_wom``,
  ``build_ladder_selection``, ``ladder_signature``, ``build_ladder_payload``) e
  ai gemelli di ``tennis_live/tennis_runner.py``: qui sono UNA copia sola,
  parametrica (livelli, livelli del WOM), riscritta e confrontata col vecchio;
* ``serialize_book`` (``Betfair/stream/recorder.py``) e la versione del payload
  (``updated_ms`` strettamente crescente, stesso payload per la stessa firma:
  ``ladder_canale.StatoLadder.versione``) sono IMPORTATI (funzioni pure di oggi);
* la riga del topic ``ladder`` ha le stesse chiavi nello stesso ordine
  (``event_id, market_id, market_type, market_name, status, ladder``): stesso
  ``json.dumps`` byte per byte.

Entrate: i ``MarketBook`` della libreria (``consumatore`` o ``sorgente``), i
metadati del mercato (``meta``: evento, tipo, nome, nomi delle selezioni; None =
il mercato non va in ladder, come oggi per gli eventi finiti o, nel tennis, per i
mercati che non sono il Match Odds dell'evento), ``push_a_ogni_cambio``.
Uscite: ``pubblica(topic, riga)`` (in esercizio ``local_channel.publish``) e,
facoltativo, ``scrivi_db(riga)`` (``db.upsert_live_ladder``) a ``db_sec``
write-on-change, come oggi.

Cosa NON fa: non apre connessioni, non legge il DB, non converte GBP->EUR (il
book arriva gia' convertito, come oggi dal middleware ``valuta`` di flumine), non
decide quali mercati seguire. Importare il modulo non crea thread: il thread
nasce in ``avvia`` e muore in ``ferma``.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Set, Tuple

from Betfair.stream.ladder_canale import StatoLadder, updated_ms_del_book
from Betfair.stream.recorder import serialize_book

logger = logging.getLogger(__name__)

#: coalescenza minima per mercato (ms): Bet Angel / Fairbot stanno a 20-200 ms
INTERVALLO_MIN_MS = 20
#: il thread del ladder si sveglia almeno cosi' spesso per accorgersi di un
#: canale che torna ad avere client (oggi: il giro di 200 ms del worker)
CONTROLLO_CANALE_S = 0.2
TOPIC_LADDER = "ladder"

Sport = Literal["calcio", "tennis"]
#: cosa fa il ladder quando arriva un book CLOSED (oggi diverso per sport):
#: calcio  = marca CLOSED l'ultimo book noto (``recorder.py:221-225``);
#: tennis  = serializza il book chiuso e lo marca CLOSED (``tennis_runner.py:443-458``)
Chiusura = Literal["marca_ultimo", "serializza_chiuso"]


# ---------------------------------------------------------------------------
# profilo del ladder (valori di oggi, stesse variabili d'ambiente)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ProfiloLadder:
    sport: Sport
    profondita: int          # livelli serializzati (LADDER_DEPTH)
    livelli_max: int         # livelli back/lay pubblicati (LADDER_MAX_LEVELS)
    livelli_wom: int         # livelli del Weight of Money (LADDER_WOM_LEVELS)
    db_sec: float            # cadenza della scrittura DB (LADDER_PUBLISH_SEC)
    chiusura: Chiusura


def profilo_ladder(sport: Sport, ambiente: Optional[Mapping[str, str]] = None) -> ProfiloLadder:
    """Il profilo di oggi: calcio ``config_stream.py:47,60,78,80``; tennis
    ``tennis_live/tennis_runner.py:104-107``. Stesso parsing (``int``/``float`` di
    ``os.getenv``): un valore illeggibile solleva come oggi all'import."""
    if sport not in ("calcio", "tennis"):
        raise ValueError("sport sconosciuto: %r" % (sport,))
    amb = os.environ if ambiente is None else ambiente
    pref = "LIVE_" if sport == "calcio" else "TENNIS_"
    prof = int(amb.get(pref + "LADDER_DEPTH", "10"))
    return ProfiloLadder(
        sport=sport,
        profondita=prof,
        livelli_max=int(amb.get(pref + "LADDER_MAX_LEVELS", str(prof))),
        livelli_wom=int(amb.get(pref + "LADDER_WOM_LEVELS", "3")),
        db_sec=float(amb.get(pref + "LADDER_PUBLISH_SEC", "2.0")),
        chiusura="marca_ultimo" if sport == "calcio" else "serializza_chiuso",
    )


@dataclass(frozen=True)
class MetaLadder:
    """Cio' che la riga del ladder porta oltre al book (oggi dalla sessione del runner)."""

    event_id: Any
    market_type: Optional[str]
    market_name: Optional[str]
    nomi: Mapping[str, str] = field(default_factory=dict)   # selection_id (str) -> nome


# ---------------------------------------------------------------------------
# funzioni pure (gemelle di runner.py:573-685 e tennis_runner.py:200-275)
# ---------------------------------------------------------------------------
def livelli(raw: Any, max_livelli: Optional[int]) -> List[List[float]]:
    """``[[prezzo, size], ...]`` in float, al massimo ``max_livelli`` (None/<=0 =
    tutti). Salta i livelli malformati e i prezzi <= 0 senza sollevare."""
    out: List[List[float]] = []
    if not raw:
        return out
    seq = raw if (max_livelli is None or max_livelli <= 0) else raw[:max_livelli]
    for lvl in seq:
        try:
            prezzo, size = lvl[0], lvl[1]
            if prezzo is None or float(prezzo) <= 0:
                continue
            out.append([float(prezzo), float(size or 0.0)])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def peso_del_denaro(back: List[List[float]], lay: List[List[float]],
                    n_livelli: int) -> Dict[str, float]:
    """Weight of Money: quota % della size back e lay nei primi ``n_livelli``.
    Somma esatta 100 (``lay = 100 - back``); 0/0 senza size."""
    n = n_livelli if n_livelli and n_livelli > 0 else 1
    back_sz = sum(s for _, s in back[:n])
    lay_sz = sum(s for _, s in lay[:n])
    totale = back_sz + lay_sz
    if totale <= 0:
        return {"back_pct": 0.0, "lay_pct": 0.0}
    back_pct = round(back_sz / totale * 100.0, 1)
    return {"back_pct": back_pct, "lay_pct": round(100.0 - back_pct, 1)}


def selezione(selection_id: Any, runner: Mapping[str, Any], nome: Optional[str],
              max_livelli: int, livelli_wom: int) -> Dict[str, Any]:
    """Una selezione dal runner serializzato (``serialize_book``): back/lay fino a
    ``max_livelli``, ``trd`` sempre pieno, WOM sui primi ``livelli_wom``."""
    back = livelli(runner.get("b"), max_livelli)
    lay = livelli(runner.get("l"), max_livelli)
    trd = livelli(runner.get("trd"), None)
    return {
        "selection_id": int(selection_id),
        "name": nome,
        "ltp": runner.get("ltp"),
        "tv": runner.get("tv"),
        "back": back,
        "lay": lay,
        "trd": trd,
        "wom": peso_del_denaro(back, lay, livelli_wom),
    }


def firma(selezioni: List[Mapping[str, Any]]) -> str:
    """SHA-1 di ltp + back/lay/trd per selezione, in ordine di ``selection_id``
    (dopo una riconnessione la libreria puo' cambiare l'ordine dei runner)."""
    dati = [
        (
            s["selection_id"],
            s["ltp"],
            tuple(tuple(lvl) for lvl in s["back"]),
            tuple(tuple(lvl) for lvl in s["lay"]),
            tuple(tuple(lvl) for lvl in s["trd"]),
        )
        for s in sorted(selezioni, key=lambda x: x["selection_id"])
    ]
    return hashlib.sha1(repr(dati).encode("utf-8")).hexdigest()  # noqa: S324 - firma, non crittografia


def payload_ladder(libro: Mapping[str, Any], nomi: Mapping[str, str], max_livelli: int,
                   livelli_wom: int) -> Dict[str, Any]:
    """``{updated_ms, selections}`` dal book serializzato; ``updated_ms`` = ``pt``
    del book se valido, altrimenti adesso (``ladder_canale.updated_ms_del_book``)."""
    selezioni = [
        selezione(sel_id, r, nomi.get(str(sel_id)), max_livelli, livelli_wom)
        for sel_id, r in (libro.get("runners") or {}).items()
    ]
    return {"updated_ms": updated_ms_del_book(libro), "selections": selezioni}


def firma_con_stato(libro: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    """Lo stato entra nella firma: OPEN -> SUSPENDED -> CLOSED si pubblica anche a
    livelli fermi (``runner.py:715-717``)."""
    return (libro.get("status") or "") + "|" + firma(payload["selections"])


def riga_ladder(meta: MetaLadder, market_id: str, libro: Mapping[str, Any],
                payload: Dict[str, Any]) -> Dict[str, Any]:
    """La riga del topic ``ladder`` (chiavi e ordine di ``runner.py:733-740``)."""
    return {
        "event_id": meta.event_id,
        "market_id": market_id,
        "market_type": meta.market_type,
        "market_name": meta.market_name,
        "status": libro.get("status"),
        "ladder": payload,
    }


def libro_chiuso(profilo: ProfiloLadder, libro: Any,
                 ultimo: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Il book serializzato dopo un CLOSED, come oggi per lo sport del profilo.

    calcio: l'ultimo book noto con ``status`` = quello del book (``recorder.py:221-225``),
    nessuno se non ce n'era uno. tennis: il book chiuso serializzato e marcato CLOSED,
    l'ultimo noto se non serializzabile (``tennis_runner.py:443-458``)."""
    if profilo.chiusura == "marca_ultimo":
        if ultimo is None:
            return None
        out = dict(ultimo)
        out["status"] = getattr(libro, "status", None) or "CLOSED"
        return out
    try:
        rec = serialize_book(libro, profilo.profondita)
    except Exception as e:  # noqa: BLE001 - book strano: si marca l'ultimo noto
        logger.warning("[ladder] book chiuso non serializzabile (%s): uso l'ultimo noto", e)
        rec = dict(ultimo or {"market_id": getattr(libro, "market_id", None), "runners": {}})
    rec["status"] = "CLOSED"
    return rec


# ---------------------------------------------------------------------------
# il ladder guidato dall'evento
# ---------------------------------------------------------------------------
@dataclass
class _Mercato:
    libro: Any = None                      # ultimo MarketBook ricevuto (consumatore)
    libro_serializzato_da: Any = None      # il MarketBook da cui viene ``serializzato``
    serializzato: Optional[Dict[str, Any]] = None
    firma_canale: Optional[str] = None
    firma_db: Optional[str] = None
    ultima_pub: Optional[float] = None     # orologio del ladder
    sporco_dal: Optional[float] = None     # primo push non ancora pubblicato


class LadderEvento:
    """Implementa ``contratto.Ladder``: pubblicazione a ogni cambio, minimo 20 ms
    per mercato, stesso JSON di oggi; DB (facoltativo) in un thread suo."""

    def __init__(self, profilo: ProfiloLadder, *,
                 meta: Callable[[str], Optional[MetaLadder]],
                 pubblica: Callable[[str, Dict[str, Any]], None],
                 sorgente: Optional[Callable[[str], Any]] = None,
                 canale_attivo: Callable[[], bool] = lambda: True,
                 scrivi_db: Optional[Callable[[Dict[str, Any]], None]] = None,
                 marca_canale: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = None,
                 intervallo_min_ms: int = INTERVALLO_MIN_MS,
                 orologio: Callable[[], float] = time.monotonic,
                 topic: str = TOPIC_LADDER) -> None:
        self.profilo = profilo
        self._meta = meta
        self._pubblica = pubblica
        self._sorgente = sorgente
        self._canale_attivo = canale_attivo
        self._scrivi_db = scrivi_db
        self._marca = marca_canale
        self._intervallo = max(0, int(intervallo_min_ms)) / 1000.0
        self._ora = orologio
        self._topic = topic
        self._cond = threading.Condition()
        self._mercati: Dict[str, _Mercato] = {}
        self._sporchi: Set[str] = set()
        self._costruzione = threading.Lock()
        # versione del payload (updated_ms crescente, stesso payload a parita' di firma):
        # SOLO ``versione`` di ``StatoLadder`` (le cadenze sono qui)
        self._versioni = StatoLadder(profilo.db_sec, 0)
        self._canale_prima = False
        self._fermo = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._thread_db: Optional[threading.Thread] = None
        self.conti: Dict[str, float] = {
            "push": 0, "pubblicati": 0, "invariati": 0, "fusi": 0, "senza_client": 0,
            "errori": 0, "db_scritti": 0, "db_errori": 0,
            "attesa_ms_somma": 0.0, "attesa_ms_max": 0.0,
        }

    # ------------------------------------------------------------ ingressi
    def consumatore(self, libro: Any) -> None:
        """Callback per ``FlussoMercato.aggiungi_consumatore``: tiene il book e spinge."""
        mid = str(getattr(libro, "market_id", "") or "")
        if not mid:
            return
        with self._cond:
            self._voce(mid).libro = libro
        self.push_a_ogni_cambio(mid)

    def push_a_ogni_cambio(self, market_id: str) -> None:
        """Il book di ``market_id`` e' cambiato: pubblicazione appena possibile,
        mai piu' di una ogni ``intervallo_min_ms`` per mercato (fusione)."""
        mid = str(market_id)
        with self._cond:
            self.conti["push"] += 1
            voce = self._voce(mid)
            if mid in self._sporchi:
                self.conti["fusi"] += 1
            else:
                self._sporchi.add(mid)
                voce.sporco_dal = self._ora()
            self._cond.notify()

    def dimentica(self, market_id: str) -> None:
        """Il mercato esce dal ladder (follow tolto): nessuna pubblicazione in piu'."""
        with self._cond:
            self._mercati.pop(str(market_id), None)
            self._sporchi.discard(str(market_id))

    # ------------------------------------------------------------ uscite
    def snapshot(self, market_id: str) -> Dict[str, Any]:
        """La riga corrente del mercato (schema del topic ``ladder``); {} se il
        mercato non ha book o non va in ladder (``meta`` None)."""
        v = self._versione(str(market_id))
        return dict(v[2]) if v is not None else {}

    def esegui_scaduti(self, adesso: Optional[float] = None) -> Optional[float]:
        """Pubblica i mercati il cui intervallo minimo e' passato. Ritorna
        l'istante (orologio del ladder) della prossima scadenza, o None."""
        ora = self._ora() if adesso is None else float(adesso)
        attivo = bool(self._canale_attivo())
        with self._cond:
            if attivo and not self._canale_prima:
                # il canale torna ad avere client: tutto si ripubblica (come
                # ``StatoLadder.giro``): il client nuovo non aspetta un cambio
                for mid, voce in self._mercati.items():
                    voce.firma_canale = None
                    if mid not in self._sporchi:
                        self._sporchi.add(mid)
                        voce.sporco_dal = ora
            self._canale_prima = attivo
            if not attivo:
                self.conti["senza_client"] += len(self._sporchi)
                self._sporchi.clear()
                return None
            pronti, prossima = self._scaduti(ora)
        for mid in pronti:
            self._pubblica_mercato(mid, ora)
        return prossima

    def esegui_db(self, adesso: Optional[float] = None) -> int:  # noqa: ARG002 - firma simmetrica
        """Un giro della scrittura DB (write-on-change): i mercati la cui firma e'
        cambiata dall'ultima scrittura RIUSCITA. Ritorna quante righe scritte."""
        if self._scrivi_db is None:
            return 0
        with self._cond:
            mercati = list(self._mercati)
        scritte = 0
        for mid in mercati:
            v = self._versione(mid)
            if v is None:
                continue
            sig, _payload, riga = v
            voce = self._mercati.get(mid)
            if voce is None or voce.firma_db == sig:
                continue
            try:
                self._scrivi_db(riga)
            except Exception as e:  # noqa: BLE001 - un errore DB non ferma il ladder
                self.conti["db_errori"] += 1
                logger.warning("[ladder] scrittura DB KO %s: %s", mid, e)
                continue
            voce.firma_db = sig
            scritte += 1
        self.conti["db_scritti"] += scritte
        return scritte

    def stato(self) -> Dict[str, Any]:
        """Contatori per la Salute: push, pubblicati, fusi, invariati, attesa media/max."""
        with self._cond:
            c = dict(self.conti)
            n = int(c["pubblicati"]) or 1
            c["attesa_ms_media"] = round(c["attesa_ms_somma"] / n, 3)
            c["mercati"] = len(self._mercati)
            c["in_attesa"] = len(self._sporchi)
            c["intervallo_min_ms"] = int(self._intervallo * 1000)
            c["thread_vivo"] = bool(self._thread is not None and self._thread.is_alive())
        return c

    # ------------------------------------------------------------ thread
    def avvia(self) -> None:
        """Avvia il thread del ladder e, con ``scrivi_db``, quello del DB."""
        if self._thread is not None:
            return
        self._fermo.clear()
        self._thread = threading.Thread(target=self._ciclo, name="ladder-evento", daemon=True)
        self._thread.start()
        if self._scrivi_db is not None:
            self._thread_db = threading.Thread(target=self._ciclo_db, name="ladder-db", daemon=True)
            self._thread_db.start()

    def ferma(self, attesa_s: float = 2.0) -> None:
        """Ferma i thread (attende al massimo ``attesa_s`` ciascuno)."""
        self._fermo.set()
        with self._cond:
            self._cond.notify_all()
        for t in (self._thread, self._thread_db):
            if t is not None:
                t.join(timeout=attesa_s)
        self._thread = None
        self._thread_db = None

    def _ciclo(self) -> None:
        prossima: Optional[float] = None
        while not self._fermo.is_set():
            with self._cond:
                attesa = CONTROLLO_CANALE_S
                if prossima is not None:
                    attesa = min(attesa, max(0.0, prossima - self._ora()))
                if not self._sporchi or prossima is not None:
                    self._cond.wait(timeout=attesa)
            if self._fermo.is_set():
                break
            try:
                prossima = self.esegui_scaduti()
            except Exception as e:  # noqa: BLE001 - il thread del ladder non muore
                self.conti["errori"] += 1
                logger.warning("[ladder] giro KO: %s", e)
                prossima = None

    def _ciclo_db(self) -> None:
        while not self._fermo.wait(self.profilo.db_sec):
            try:
                self.esegui_db()
            except Exception as e:  # noqa: BLE001
                self.conti["db_errori"] += 1
                logger.warning("[ladder] giro DB KO: %s", e)

    # ------------------------------------------------------------ interni
    def _voce(self, mid: str) -> _Mercato:
        voce = self._mercati.get(mid)
        if voce is None:
            voce = _Mercato()
            self._mercati[mid] = voce
        return voce

    def _scaduti(self, ora: float) -> Tuple[List[str], Optional[float]]:
        """(mercati da pubblicare adesso, prossima scadenza). Sotto ``_cond``."""
        pronti: List[str] = []
        prossima: Optional[float] = None
        for mid in sorted(self._sporchi):
            voce = self._mercati.get(mid)
            if voce is None:
                continue
            dovuto = ora if voce.ultima_pub is None else voce.ultima_pub + self._intervallo
            if dovuto <= ora + 1e-9:
                pronti.append(mid)
            else:
                prossima = dovuto if prossima is None else min(prossima, dovuto)
        for mid in pronti:
            self._sporchi.discard(mid)
        return pronti, prossima

    def _pubblica_mercato(self, mid: str, ora: float) -> None:
        try:
            v = self._versione(mid)
        except Exception as e:  # noqa: BLE001 - un mercato malformato non blocca gli altri
            self.conti["errori"] += 1
            logger.warning("[ladder] costruzione KO %s: %s", mid, e)
            return
        voce = self._mercati.get(mid)
        if v is None or voce is None:
            return
        sig, _payload, riga = v
        if voce.firma_canale == sig:
            self.conti["invariati"] += 1
            return
        uscita = riga
        if self._marca is not None and voce.serializzato is not None:
            uscita = self._marca(riga, voce.serializzato)
        self._pubblica(self._topic, uscita)
        voce.firma_canale = sig
        voce.ultima_pub = ora
        if voce.sporco_dal is not None:
            attesa = max(0.0, (ora - voce.sporco_dal) * 1000.0)
            self.conti["attesa_ms_somma"] += attesa
            self.conti["attesa_ms_max"] = max(self.conti["attesa_ms_max"], attesa)
            voce.sporco_dal = None
        self.conti["pubblicati"] += 1

    def _libro_corrente(self, mid: str, voce: _Mercato) -> Any:
        if self._sorgente is not None:
            return self._sorgente(mid)
        return voce.libro

    def _serializza(self, mid: str, voce: _Mercato) -> Optional[Dict[str, Any]]:
        """Il book serializzato corrente (ricalcolato solo se il MarketBook e'
        un oggetto nuovo: la libreria ne crea uno a ogni aggiornamento)."""
        libro = self._libro_corrente(mid, voce)
        if libro is None or libro is voce.libro_serializzato_da:
            return voce.serializzato
        if getattr(libro, "status", None) == "CLOSED":
            nuovo = libro_chiuso(self.profilo, libro, voce.serializzato)
        else:
            nuovo = serialize_book(libro, self.profilo.profondita)
        voce.libro_serializzato_da = libro
        voce.serializzato = nuovo
        return nuovo

    def _versione(self, mid: str) -> Optional[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
        """(firma, payload, riga) del mercato, o None (nessun book / fuori ladder)."""
        meta = self._meta(mid)
        if meta is None:
            return None
        with self._costruzione:
            voce = self._mercati.get(mid)
            if voce is None:
                return None
            libro = self._serializza(mid, voce)
            if libro is None:
                return None
            p = self.profilo

            def _costruisci() -> Tuple[Dict[str, Any], str]:
                payload = payload_ladder(libro, meta.nomi, p.livelli_max, p.livelli_wom)
                return payload, firma_con_stato(libro, payload)
            sig, payload = self._versioni.versione(mid, libro, _costruisci)
            return sig, payload, riga_ladder(meta, mid, libro, payload)
