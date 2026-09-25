"""auto_follow.py - AUTO-FOLLOW del runner calcio (25/09/2026).

Ordine dell'utente (testuale): "TUTTI I BOT NELLA CONTROL ROOM UNA VOLTA ARMATI
DEVONO POTER OPERARE SU TUTTE LE PARTITE IDONEE DA SOLI [...] A che serve tutto
questo lavoro se devo cliccare "Segui"?".

PRIMA: con la strada unica degli ordini accesa (``MOTORE_ORDINI_CANALE=1``) il
motore del runner rifiutava ogni ordine su un mercato che il runner non seguiva
(``live_order_worker._resolve_market``: "market ... non sottoscritto nel
runner", scenario R10 del banco). Seguire una partita voleva dire il clic
"Segui live", e aggiungerla allo stream voleva dire RICOSTRUIRE il framework
flumine: rinviata finche' il runner non e' flat (blotter perso, posizioni paper
azzerate), quindi mai mentre i bot lavorano.

DOPO: il runner segue DA SOLO i mercati su cui i bot mandano ordini, SENZA
ricostruire niente.

  * AGGANCIO AL VOLO (motore -> ``AutoFollow.richiedi``): il comando di un bot
    su un mercato non sottoscritto non e' piu' rifiutato. Il motore lo accetta
    (ack ``accettato`` con motivo ``in_aggancio``), lo parcheggia in RAM e chiede
    il mercato; qui il mercato entra nella sottoscrizione e il comando parte
    appena arriva il primo book. Oltre ``MOTORE_AGGANCIO_MAX_MS`` senza book:
    rifiuto DICHIARATO ``in_aggancio`` (il bot ripete la decisione), mai in
    silenzio.
  * RISOTTOSCRIZIONE A CALDO (``SottoscrittoreStream``): Betfair Stream API
    sostituisce la sottoscrizione con un nuovo ``marketSubscription`` sulla
    STESSA connessione. Si usa ``BetfairStream.subscribe_to_markets`` di
    betfairlightweight (lo stesso che flumine chiama all'avvio): il listener
    registra il nuovo id e scarta i messaggi del vecchio, Betfair manda
    l'immagine piena dei mercati. Il framework, il blotter, le posizioni (paper
    e live), gli ordini vivi e i worker restano quelli di prima: NESSUN restart,
    nessuna connessione in piu'.
  * TETTO E PRIORITA' (``PianoFollow``, puro): una sola connessione di mercato,
    200 mercati per connessione (limite Betfair) -> tetto = ``HARD_MARKET_CAP``
    (180, config_stream) contando ANCHE i mercati delle partite seguite a mano.
    Priorita': posizioni vive (mai espulse) > comando di un bot > candidata del
    feed. Tetto pieno: il comando espelle l'evento automatico meno prioritario
    (e piu' vecchio) SENZA ordini nel blotter; i follow manuali non si toccano
    mai. Se non c'e' niente di espellibile: rifiuto dichiarato
    ``tetto_mercati_pieno`` (mai un ordine mandato alla cieca).
  * PROATTIVO (``_giro_feed``): con almeno un bot calcio collegato al canale di
    comando (Safe/Omega), ogni ``AUTO_FOLLOW_FEED_SEC`` si leggono dal feed unico
    (``safe_strategy_scan``, UNA select di sole chiavi) le partite calcio in
    gioco o imminenti e i mercati che i bot leggono (MATCH_ODDS, CORRECT_SCORE,
    HALF_TIME_SCORE e i blocchi opportunita' ou/btts/ht_result dello scanner),
    e si seguono in anticipo entro il tetto (priorita' candidata, senza
    espellere nessuno). Il feed e' la LISTA (regola del 23/09); con lo scanner
    fermo o il feed non letto non si toglie niente.
  * FOLLOW NEL DB (``live_follow``): con la colonna ``origine`` (migrazione
    ``live_follow_origine_2026-09-25.sql``) ogni evento seguito da solo ha la
    sua riga ``origine='auto'``, ``status='STREAMING'`` (e ``CLOSED`` quando
    esce): il Terminale mostra l'origine. Senza migrazione: tutto in RAM, niente
    righe (dichiarato nello stato). Un follow dell'utente non viene MAI
    riscritto (insert ``ignore_duplicates``, update solo sulle righe ``auto``).
  * EVENTI "SILENZIOSI": i mercati automatici stanno solo nello stream (book,
    blotter, ordini, specchio): niente ``live_now``/ladder su DB/segnali/raw,
    che per 30+ partite schiaccerebbero il DB (13/09). Chi vuole il terminale di
    quella partita clicca "Segui live" come oggi.

Nessun processo nuovo: un thread dentro il runner. Nessuna chiamata Betfair in
piu' oltre ai ``marketSubscription`` sulla connessione che esiste gia'.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

ORIGINE_AUTO = "auto"
ORIGINE_MANUALE = "manuale"

#: priorita' (piu' alto = piu' importante). Le POSIZIONI non sono un numero:
#: un evento con ordini nel blotter e' PROTETTO, mai espulso.
PRI_CANDIDATA = 1
PRI_COMANDO = 2
NOMI_PRIORITA = {PRI_CANDIDATA: "candidata", PRI_COMANDO: "comando"}

#: limite Betfair: 200 mercati per connessione (accertato 09/09, config_stream).
#: 25/09: UNA definizione per calcio e tennis (``sottoscrizione_a_caldo``).
from .sottoscrizione_a_caldo import LIMITE_BETFAIR_MERCATI  # noqa: E402

#: chiave di un evento chiesto da un comando prima di conoscerne l'event_id
PREFISSO_SOLO_MERCATO = "m:"

#: attori calcio che, collegati al canale di comando, accendono il proattivo
ATTORI_CALCIO_DEFAULT = ("safe", "omega")

#: un comando appena chiesto protegge la sua voce (il suo ordine e' in volo o
#: parcheggiato in attesa del primo book: espellerla lo farebbe scadere)
PROTEZIONE_COMANDO_S = 10.0
#: mercato sottoscritto che flumine non ha mai visto (inesistente, o tolto dopo
#: la chiusura): esce dal piano, non occupa il tetto per sempre
MAI_ARRIVATO_S = 120.0

#: tipi di mercato del feed seguiti in anticipo (chiavi del payload dello scanner)
CHIAVI_MERCATO_FEED = ("mo_market_id", "cs", "ht", "btts", "ht_result")


def _env_float(nome: str, default: float) -> float:
    raw = os.environ.get(nome, "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    return v if v > 0 else default


def acceso() -> bool:
    """Interruttore ``RUNNER_AUTO_FOLLOW``: ACCESO di serie (ordine dell'utente:
    i bot operano da soli). ``0``/``false``/``no`` lo spegne: il motore torna a
    rifiutare i mercati non seguiti come prima (fail-closed)."""
    v = os.environ.get("RUNNER_AUTO_FOLLOW", "").strip().lower()
    return v not in ("0", "false", "no", "off")


def tetto_mercati() -> int:
    """Il tetto dei mercati sulla connessione di mercato del runner.

    ``HARD_MARKET_CAP`` (180 di serie, sotto i 200 di Betfair per il margine gia'
    deciso il 09/09), sovrascrivibile con ``AUTO_FOLLOW_TETTO_MERCATI`` ma MAI
    oltre 200. Conta manuali + automatici: la connessione e' una sola."""
    try:
        from .config_stream import HARD_MARKET_CAP
        base = int(HARD_MARKET_CAP)
    except Exception:  # noqa: BLE001 - config illeggibile: il margine storico
        base = 180
    raw = os.environ.get("AUTO_FOLLOW_TETTO_MERCATI", "").strip()
    if raw:
        try:
            base = int(raw)
        except ValueError:
            pass
    return max(1, min(base, LIMITE_BETFAIR_MERCATI))


# ---------------------------------------------------------------------------
# il piano: tetto e priorita' (puro, thread-safe)
# ---------------------------------------------------------------------------
@dataclass
class Voce:
    chiave: str
    mercati: Set[str]
    priorita: int
    dal: float
    ultimo_uso: float
    motivo: str = ""
    visto_feed: float = 0.0
    info: Dict[str, Any] = field(default_factory=dict)

    @property
    def event_id(self) -> Optional[str]:
        return None if self.chiave.startswith(PREFISSO_SOLO_MERCATO) else self.chiave


@dataclass
class EsitoPiano:
    ok: bool
    aggiunti: Set[str] = field(default_factory=set)
    espulsi: List[Voce] = field(default_factory=list)
    motivo: Optional[str] = None


class PianoFollow:
    """Quali mercati il runner deve seguire, dentro il tetto.

    ``manuali``: evento -> mercati delle partite seguite a mano (la sessione del
    runner). Mai toccati, mai espulsi, contano nel tetto. ``auto``: le voci
    automatiche. ``richiedi`` e' TRANSAZIONALE: o entra tutto (con le espulsioni
    del caso) o non cambia niente."""

    def __init__(self, tetto: int) -> None:
        self.tetto = int(tetto)
        self._lock = threading.RLock()
        self._manuali: Dict[str, Set[str]] = {}
        self._auto: Dict[str, Voce] = {}

    # ------------------------------------------------------------ letture
    def _mercati_manuali(self) -> Set[str]:
        out: Set[str] = set()
        for ms in self._manuali.values():
            out |= ms
        return out

    def mercati(self) -> Set[str]:
        with self._lock:
            out = self._mercati_manuali()
            for v in self._auto.values():
                out |= v.mercati
            return out

    def mercati_manuali(self) -> Set[str]:
        with self._lock:
            return self._mercati_manuali()

    def contiene(self, market_id: str) -> bool:
        return str(market_id) in self.mercati()

    def chiave_di(self, market_id: str) -> Optional[str]:
        """La voce AUTOMATICA che porta il mercato (None = manuale o ignoto)."""
        mid = str(market_id)
        with self._lock:
            for k, v in self._auto.items():
                if mid in v.mercati:
                    return k
        return None

    def voci(self) -> Dict[str, Voce]:
        with self._lock:
            return {k: Voce(v.chiave, set(v.mercati), v.priorita, v.dal, v.ultimo_uso,
                            v.motivo, v.visto_feed, dict(v.info))
                    for k, v in self._auto.items()}

    def voce(self, chiave: str) -> Optional[Voce]:
        with self._lock:
            return self._auto.get(chiave)

    def e_manuale(self, event_id: str) -> bool:
        with self._lock:
            return str(event_id) in self._manuali

    # ------------------------------------------------------------ scritture
    def imposta_manuali(self, per_evento: Dict[str, Iterable[str]]) -> None:
        with self._lock:
            self._manuali = {str(e): {str(m) for m in ms} for e, ms in per_evento.items()}

    def richiedi(self, chiave: str, mercati: Iterable[str], *, priorita: int,
                 protetti: Set[str], puo_espellere: bool, ora: float,
                 motivo: str = "", info: Optional[Dict[str, Any]] = None) -> EsitoPiano:
        chiave = str(chiave)
        chiesti = {str(m) for m in mercati if m}
        with self._lock:
            attuali = self.mercati()
            nuovi = chiesti - attuali
            v = self._auto.get(chiave)
            if not nuovi:
                if v is not None:
                    v.priorita = max(v.priorita, priorita)
                    v.ultimo_uso = ora
                    if info:
                        v.info.update(info)
                return EsitoPiano(True)
            libero = self.tetto - len(attuali)
            espulsi: List[Voce] = []
            if libero < len(nuovi):
                if not puo_espellere:
                    return EsitoPiano(False, motivo=(
                        "%d mercati seguiti su %d, ne servono %d"
                        % (len(attuali), self.tetto, len(nuovi))))
                candidati = sorted(
                    (x for k, x in self._auto.items()
                     if k != chiave and k not in protetti and x.priorita <= priorita),
                    key=lambda x: (x.priorita, x.ultimo_uso, x.chiave))
                # simulazione: si espelle il minimo, in ordine di priorita' e eta'
                restanti = dict(self._auto)
                for x in candidati:
                    restanti.pop(x.chiave, None)
                    espulsi.append(x)
                    occupati = set(self._mercati_manuali())
                    for y in restanti.values():
                        occupati |= y.mercati
                    if self.tetto - len(occupati | nuovi) >= 0:
                        break
                else:
                    return EsitoPiano(False, motivo=(
                        "%d mercati seguiti su %d e nessun evento "
                        "automatico espellibile (posizioni vive, manuali o piu' "
                        "prioritari)" % (len(attuali), self.tetto)))
                for x in espulsi:
                    self._auto.pop(x.chiave, None)
            if v is None:
                v = Voce(chiave, set(), priorita, ora, ora, motivo)
                self._auto[chiave] = v
            v.mercati |= nuovi
            v.priorita = max(v.priorita, priorita)
            v.ultimo_uso = ora
            if info:
                v.info.update(info)
            return EsitoPiano(True, aggiunti=set(nuovi), espulsi=espulsi)

    def rientra(self, protetti: Set[str]) -> List[Voce]:
        """Se i manuali sono cresciuti (ricostruzione con una partita seguita a
        mano in piu'), le voci automatiche meno prioritarie e senza ordini escono
        finche' il totale non torna nel tetto. I manuali non escono mai."""
        with self._lock:
            out: List[Voce] = []
            while len(self.mercati()) > self.tetto:
                cand = sorted((x for k, x in self._auto.items() if k not in protetti),
                              key=lambda x: (x.priorita, x.ultimo_uso, x.chiave))
                if not cand:
                    break
                x = cand[0]
                self._auto.pop(x.chiave, None)
                out.append(x)
            return out

    def togli(self, chiave: str) -> Optional[Voce]:
        with self._lock:
            return self._auto.pop(str(chiave), None)

    def togli_mercati(self, chiave: str, mercati: Iterable[str]) -> Optional[Voce]:
        """Toglie mercati da una voce; se resta vuota la voce esce (ritornata)."""
        with self._lock:
            v = self._auto.get(str(chiave))
            if v is None:
                return None
            v.mercati -= {str(m) for m in mercati}
            if not v.mercati:
                return self._auto.pop(str(chiave), None)
            return None

    def rinomina(self, vecchia: str, event_id: str) -> Optional[Voce]:
        """La voce di un comando nata col solo mercato prende l'event_id vero
        (primo book). Se l'evento ha gia' una voce, si fondono."""
        with self._lock:
            v = self._auto.pop(str(vecchia), None)
            if v is None:
                return self._auto.get(str(event_id))
            dest = self._auto.get(str(event_id))
            if dest is None:
                v.chiave = str(event_id)
                self._auto[v.chiave] = v
                return v
            dest.mercati |= v.mercati
            dest.priorita = max(dest.priorita, v.priorita)
            dest.ultimo_uso = max(dest.ultimo_uso, v.ultimo_uso)
            dest.info.update(v.info)
            return dest


# ---------------------------------------------------------------------------
# il sottoscrittore: risottoscrizione a caldo sulla connessione di mercato
# ---------------------------------------------------------------------------
# 25/09 UNIFICAZIONE: il meccanismo (nuovo marketSubscription sulla stessa
# connessione, stream_id, filtro canonico, book vecchi scartati dal listener)
# vive in ``sottoscrizione_a_caldo`` ed e' lo STESSO del runner tennis
# (``tennis_live.iscrizione_a_caldo``). Qui restano i nomi di sempre.
from .sottoscrizione_a_caldo import NonPronto  # noqa: E402,F401 - riesportato
from . import sottoscrizione_a_caldo as _SC  # noqa: E402


def stream_di_mercato(framework: Any) -> Any:
    """LA MarketStream del runner (recorder + strategie la condividono: stesso
    filtro -> ``Streams.add_stream`` la riusa). None se non c'e'."""
    return _SC.stream_di_mercato(framework)


class SottoscrittoreStream:
    """Sostituisce la sottoscrizione della MarketStream del runner con i
    ``market_ids`` dati, sulla STESSA connessione (nessun restart, blotter
    intatto). Chiamato SOLO dal thread dell'auto-follow. Il meccanismo e'
    ``sottoscrizione_a_caldo.sottoscrivi``, lo stesso del runner tennis."""

    def applica(self, framework: Any, market_ids: List[str]) -> int:
        return _SC.sottoscrivi(framework, _SC.stream_di_mercato(framework), market_ids)


# ---------------------------------------------------------------------------
# DB: le righe live_follow automatiche (best-effort, thread dell'auto-follow)
# ---------------------------------------------------------------------------
class FollowDb:
    """Le righe ``live_follow`` con ``origine='auto'``. Nessuna scrittura se la
    colonna non esiste (migrazione non applicata): si dichiara nello stato."""

    def __init__(self, sb_factory: Optional[Callable[[], Any]] = None) -> None:
        self._sb_factory = sb_factory
        self.colonna_origine: Optional[bool] = None

    def _sb(self) -> Any:
        if self._sb_factory is not None:
            return self._sb_factory()
        from db_client import get_supabase_client
        return get_supabase_client()

    def verifica_colonna(self) -> bool:
        if self.colonna_origine is None:
            try:
                self._sb().table("live_follow").select("origine").limit(1).execute()
                self.colonna_origine = True
            except Exception as e:  # noqa: BLE001 - colonna assente o rete KO
                logger.warning("[auto-follow] live_follow.origine NON disponibile (%s): "
                               "follow automatici solo in RAM (migrazione "
                               "live_follow_origine_2026-09-25.sql non applicata?)",
                               str(e)[:160])
                self.colonna_origine = False
        return bool(self.colonna_origine)

    def chiudi_orfani(self) -> int:
        """All'avvio del runner: le righe automatiche di un processo precedente
        (PENDING/STREAMING) diventano CLOSED. Se no il boot le catalogherebbe
        come follow manuali, con TUTTI i mercati dell'evento."""
        if not self.verifica_colonna():
            return 0
        try:
            r = (self._sb().table("live_follow")
                 .update({"status": "CLOSED", "updated_at": _ora_iso()})
                 .eq("origine", ORIGINE_AUTO).in_("status", ["PENDING", "STREAMING"])
                 .execute())
            return len(getattr(r, "data", None) or [])
        except Exception as e:  # noqa: BLE001
            logger.warning("[auto-follow] chiusura follow auto orfani KO: %s", str(e)[:160])
            return 0

    def segui(self, event_id: str, info: Dict[str, Any]) -> bool:
        if not self.verifica_colonna():
            return False
        riga = {
            "event_id": str(event_id),
            "home_name": str(info.get("home") or info.get("event_name") or "?"),
            "away_name": str(info.get("away") or "?"),
            "open_date": str(info.get("open_date") or _ora_iso()),
            "status": "STREAMING",
            "origine": ORIGINE_AUTO,
            "updated_at": _ora_iso(),
        }
        try:
            sb = self._sb()
            # mai riscrivere il follow dell'utente: insert se manca...
            sb.table("live_follow").upsert(riga, on_conflict="event_id",
                                            ignore_duplicates=True).execute()
            # ...e riattivazione SOLO delle righe automatiche
            (sb.table("live_follow")
             .update({"status": "STREAMING", "updated_at": riga["updated_at"]})
             .eq("event_id", str(event_id)).eq("origine", ORIGINE_AUTO).execute())
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("[auto-follow] riga live_follow di %s KO: %s", event_id,
                           str(e)[:160])
            return False

    def chiudi(self, event_id: str) -> bool:
        if not self.verifica_colonna():
            return False
        try:
            (self._sb().table("live_follow")
             .update({"status": "CLOSED", "updated_at": _ora_iso()})
             .eq("event_id", str(event_id)).eq("origine", ORIGINE_AUTO)
             .eq("status", "STREAMING").execute())
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("[auto-follow] chiusura follow %s KO: %s", event_id, str(e)[:160])
            return False


def _ora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# il feed: partite calcio e mercati che i bot leggono (UNA select di chiavi)
# ---------------------------------------------------------------------------
SCANNER_VIVO_S = 30.0


def leggi_feed_calcio(sb: Any) -> Optional[List[Dict[str, Any]]]:
    """Righe calcio di ``safe_strategy_scan`` con SOLE le chiavi utili, o None
    (non letto / scanner fermo: mai "feed vuoto")."""
    try:
        st = (sb.table("safe_strategy_status").select("updated_at")
              .eq("id", "scanner").limit(1).execute())
        righe_st = getattr(st, "data", None) or []
        if not righe_st:
            return None
        ts = _epoch(righe_st[0].get("updated_at"))
        if ts is None or time.time() - ts > SCANNER_VIVO_S:
            return None
        r = (sb.table("safe_strategy_scan")
             .select("event_id,updated_at,inplay:payload->inplay,"
                     "open_date:payload->>open_date,home:payload->>home,"
                     "away:payload->>away,event_name:payload->>event_name,"
                     "mo_market_id:payload->>mo_market_id,mo_status:payload->>mo_status,"
                     "cs:payload->cs->>market_id,ht:payload->ht->>market_id,"
                     "btts:payload->btts->>market_id,"
                     "ht_result:payload->ht_result->>market_id,ou:payload->ou")
             .eq("sport", "calcio").execute())
        return [x for x in (getattr(r, "data", None) or []) if isinstance(x, dict)]
    except Exception as e:  # noqa: BLE001
        logger.warning("[auto-follow] lettura feed calcio KO: %s", str(e)[:160])
        return None


def _epoch(v: Any) -> Optional[float]:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError):
        return None


def mercati_della_riga(riga: Dict[str, Any]) -> Set[str]:
    """I mercati che i bot leggono da quella partita del feed."""
    out: Set[str] = set()
    for k in CHIAVI_MERCATO_FEED:
        v = riga.get(k)
        if isinstance(v, dict):
            v = v.get("market_id")
        if v:
            out.add(str(v))
    for b in (riga.get("ou") or []):
        if isinstance(b, dict) and b.get("market_id"):
            out.add(str(b["market_id"]))
    return out


def partite_dal_feed(righe: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ordine deterministico: in gioco prima, poi orario d'inizio, poi event_id.
    Fuori le partite col MATCH_ODDS chiuso e quelle senza mercati."""
    out = []
    for r in righe:
        if not r.get("event_id"):
            continue
        if str(r.get("mo_status") or "").upper() == "CLOSED":
            continue
        if not mercati_della_riga(r):
            continue
        out.append(r)
    return sorted(out, key=lambda r: (0 if r.get("inplay") in (True, "true") else 1,
                                      str(r.get("open_date") or "9999"),
                                      str(r.get("event_id"))))


# ---------------------------------------------------------------------------
# l'auto-follow del runner
# ---------------------------------------------------------------------------
class AutoFollow:
    """Il pezzo del runner che segue da solo. Interfaccia verso il motore
    ordini: ``servibile(market_id)`` e ``richiedi(market_id, ...)``; verso il
    runner: ``aggancia``/``sgancia`` a ogni framework, ``imposta_manuali``,
    ``mercati_da_sottoscrivere`` (ricostruzione), ``avvia``/``ferma``."""

    def __init__(self, *, piano: Optional[PianoFollow] = None,
                 sottoscrittore: Optional[Any] = None,
                 follow_db: Optional[FollowDb] = None,
                 feed: Optional[Callable[[], Optional[List[Dict[str, Any]]]]] = None,
                 attori_collegati: Optional[Callable[[], Iterable[str]]] = None,
                 pubblica: Optional[Callable[[Dict[str, Any]], None]] = None,
                 orologio: Callable[[], float] = time.monotonic,
                 feed_s: Optional[float] = None,
                 min_intervallo_s: Optional[float] = None,
                 attori_calcio: Iterable[str] = ATTORI_CALCIO_DEFAULT) -> None:
        self.piano = piano or PianoFollow(tetto_mercati())
        self.sottoscrittore = sottoscrittore or SottoscrittoreStream()
        self.follow_db = follow_db
        self._feed = feed
        self._attori_collegati = attori_collegati or (lambda: ())
        self._pubblica = pubblica
        self._ora = orologio
        self.feed_s = feed_s if feed_s is not None else _env_float("AUTO_FOLLOW_FEED_SEC", 30.0)
        self.min_intervallo_s = (min_intervallo_s if min_intervallo_s is not None else
                                 _env_float("AUTO_FOLLOW_MIN_RISOTTOSCRIZIONE_MS", 250.0) / 1000.0)
        self.attori_calcio = frozenset(attori_calcio)
        self._lock = threading.RLock()
        self._framework: Any = None
        self._applicati: Set[str] = set()
        # mercato appena (ri)sottoscritto -> id() del book che aveva: servibile
        # solo quando arriva un book NUOVO (mai un libro stantio di prima)
        self._attesa_libro: Dict[str, Optional[int]] = {}
        self._inviato_ts: Dict[str, float] = {}   # mercato -> ora della sottoscrizione
        self._ultima_app = -1e9
        self._ultimo_feed = -1e9
        self._sveglia = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._scritti: Set[str] = set()          # eventi con riga live_follow auto
        self._firma_stato: Optional[Tuple[Any, ...]] = None
        self.feed_info: Dict[str, Any] = {"letto": None, "partite": 0, "fonte": "db"}
        self.conti = {"risottoscrizioni": 0, "agganci_comando": 0, "espulsi": 0,
                      "rifiuti_tetto": 0, "errori_sottoscrizione": 0}
        self.ultimo_errore: Optional[str] = None

    # ------------------------------------------------------------ runner
    def aggancia(self, framework: Any, mercati_iniziali: Iterable[str]) -> None:
        """Il framework corrente e la sottoscrizione con cui e' NATO."""
        with self._lock:
            self._framework = framework
            self._applicati = {str(m) for m in mercati_iniziali}
            self._attesa_libro = {}
        self._sveglia.set()

    def sgancia(self) -> None:
        with self._lock:
            self._framework = None
            self._applicati = set()
            self._attesa_libro = {}

    def imposta_manuali(self, per_evento: Dict[str, Iterable[str]]) -> None:
        self.piano.imposta_manuali(per_evento)

    def rientra_nel_tetto(self) -> int:
        espulsi = self.piano.rientra(self._protetti())
        self._dopo_espulsioni(espulsi)
        return len(espulsi)

    def mercati_da_sottoscrivere(self) -> List[str]:
        return sorted(self.piano.mercati())

    def mercati_auto(self) -> Set[str]:
        out: Set[str] = set()
        for v in self.piano.voci().values():
            out |= v.mercati
        return out

    def segue_auto(self, event_id: str) -> bool:
        return self.piano.voce(str(event_id)) is not None

    def avvia(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._ciclo, daemon=True,
                                        name="auto-follow-calcio")
        self._thread.start()

    def ferma(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._sveglia.set()
        if self._thread is not None:
            self._thread.join(timeout)

    # ------------------------------------------------------------ motore
    def _mercati_flumine(self) -> Dict[str, Any]:
        fw = self._framework
        try:
            d = fw.markets.markets if fw is not None else None
        except Exception:  # noqa: BLE001
            d = None
        return d if isinstance(d, dict) else {}

    def servibile(self, market_id: Optional[str]) -> bool:
        """Il mercato e' nella sottoscrizione INVIATA e flumine ne ha un book
        arrivato dopo l'invio: il comando puo' partire."""
        mid = str(market_id or "")
        if not mid:
            return False
        with self._lock:
            if self._framework is None or mid not in self._applicati:
                return False
            m = self._mercati_flumine().get(mid)
            if m is None:
                return False
            if mid in self._attesa_libro:
                prima = self._attesa_libro[mid]
                libro = getattr(m, "market_book", None)
                if libro is None or id(libro) == prima:
                    return False
                self._attesa_libro.pop(mid, None)
            return True

    def immagine_arrivata(self, market_ids: Iterable[str]) -> None:
        """Il SUB_IMAGE di Betfair per questi mercati e' arrivato (usato dal
        banco, dove la registrazione e' gia' lo stato corrente del mercato: la
        sottoscrizione vera risponde subito con l'immagine piena)."""
        with self._lock:
            for mid in market_ids:
                self._attesa_libro.pop(str(mid), None)

    def richiedi(self, market_id: str, *, event_id: Optional[str] = None,
                 motivo: str = "comando") -> Optional[str]:
        """Chiesto dal motore (thread del motore): mette il mercato nel piano a
        priorita' COMANDO (puo' espellere) e sveglia il thread. None = preso in
        carico; stringa = rifiuto dichiarato (tetto pieno)."""
        mid = str(market_id)
        chiave = str(event_id) if event_id else (
            self.piano.chiave_di(mid) or PREFISSO_SOLO_MERCATO + mid)
        esito = self.piano.richiedi(chiave, {mid}, priorita=PRI_COMANDO,
                                    protetti=self._protetti(), puo_espellere=True,
                                    ora=self._ora(), motivo=motivo)
        if not esito.ok:
            self.conti["rifiuti_tetto"] += 1
            logger.warning("[auto-follow] comando su %s NON agganciabile: %s", mid,
                           esito.motivo)
            return esito.motivo
        if esito.aggiunti:
            self.conti["agganci_comando"] += 1
            logger.info("[auto-follow] aggancio al volo di %s (%s)", mid, motivo)
        self._dopo_espulsioni(esito.espulsi)
        self._sveglia.set()
        return None

    # ------------------------------------------------------------ protezione
    def _protetti(self) -> Set[str]:
        """Le voci con ORDINI nel blotter (qualunque strategia, paper o live):
        mai espulse. Nel dubbio (blotter illeggibile) protette. Protette anche
        le voci di un comando appena chiesto (``PROTEZIONE_COMANDO_S``): il suo
        ordine e' in volo o in attesa del primo book."""
        out: Set[str] = set()
        ora = self._ora()
        for k, v in self.piano.voci().items():
            if v.priorita == PRI_COMANDO and ora - v.ultimo_uso < PROTEZIONE_COMANDO_S:
                out.add(k)
        for mid, m in list(self._mercati_flumine().items()):
            chiave = self.piano.chiave_di(mid)
            if chiave is None:
                continue
            try:
                ha_ordini = len(list(iter(m.blotter))) > 0
            except Exception:  # noqa: BLE001
                ha_ordini = True
            if ha_ordini:
                out.add(chiave)
        return out

    def _dopo_espulsioni(self, espulsi: List[Voce]) -> None:
        for v in espulsi:
            self.conti["espulsi"] += 1
            logger.warning("[auto-follow] ESPULSO %s (%d mercati, priorita' %s, senza "
                           "ordini) per fare posto", v.chiave, len(v.mercati),
                           NOMI_PRIORITA.get(v.priorita, v.priorita))
            if v.event_id and v.event_id in self._scritti and self.follow_db is not None:
                self._scritti.discard(v.event_id)
                self.follow_db.chiudi(v.event_id)

    # ------------------------------------------------------------ il giro
    def _ciclo(self) -> None:
        while not self._stop.is_set():
            self._sveglia.wait(timeout=0.25)
            self._sveglia.clear()
            if self._stop.is_set():
                return
            try:
                self.giro()
            except Exception:  # noqa: BLE001 - l'auto-follow non muore mai
                logger.exception("[auto-follow] giro KO")

    def giro(self) -> None:
        ora = self._ora()
        self._giro_feed(ora)
        self._pulisci(ora)
        self._applica(ora)
        self._rinomina_e_scrivi()
        self._annuncia()

    def _applica(self, ora: float) -> None:
        voluti = self.piano.mercati()
        with self._lock:
            fw = self._framework
            if fw is None or not voluti or voluti == self._applicati:
                return
            if ora - self._ultima_app < self.min_intervallo_s:
                self._sveglia.set()              # si riprova appena scade
                return
            prima = set(self._applicati)
        try:
            self.sottoscrittore.applica(fw, sorted(voluti))
        except NonPronto as e:
            self.ultimo_errore = str(e)
            return
        except Exception as e:  # noqa: BLE001
            self.conti["errori_sottoscrizione"] += 1
            self.ultimo_errore = str(e)[:200]
            logger.error("[auto-follow] risottoscrizione KO: %s", str(e)[:200])
            return
        with self._lock:
            if self._framework is not fw:
                return
            mercati = self._mercati_flumine()
            for mid in voluti - prima:
                self._inviato_ts[mid] = ora
                m = mercati.get(mid)
                self._attesa_libro[mid] = (id(m.market_book) if m is not None and
                                           getattr(m, "market_book", None) is not None
                                           else None)
            for mid in prima - voluti:
                self._attesa_libro.pop(mid, None)
                self._inviato_ts.pop(mid, None)
            self._applicati = set(voluti)
            self._ultima_app = ora
        self.conti["risottoscrizioni"] += 1
        logger.info("[auto-follow] sottoscrizione a caldo: %d mercati (+%d -%d) sulla "
                    "stessa connessione, tetto %d", len(voluti), len(voluti - prima),
                    len(prima - voluti), self.piano.tetto)

    def _rinomina_e_scrivi(self) -> None:
        """Voci nate dal solo mercato -> event_id dal primo book; poi le righe
        live_follow degli eventi automatici non ancora scritte."""
        mercati = self._mercati_flumine()
        for chiave, v in self.piano.voci().items():
            if chiave.startswith(PREFISSO_SOLO_MERCATO):
                for mid in v.mercati:
                    m = mercati.get(mid)
                    ev = getattr(m, "event_id", None) if m is not None else None
                    if ev:
                        info = {"event_name": getattr(m, "event_name", None)}
                        try:
                            info["open_date"] = m.market_start_datetime.isoformat()
                        except Exception:  # noqa: BLE001
                            pass
                        nuova = self.piano.rinomina(chiave, str(ev))
                        if nuova is not None:
                            for k, val in info.items():
                                nuova.info.setdefault(k, val)
                        break
        if self.follow_db is None:
            return
        for chiave, v in self.piano.voci().items():
            ev = v.event_id
            if ev is None or ev in self._scritti or self.piano.e_manuale(ev):
                continue
            if not (v.mercati & self._applicati):
                continue
            info = dict(v.info)
            if not info.get("home") and info.get("event_name"):
                parti = str(info["event_name"]).split(" v ")
                if len(parti) == 2:
                    info["home"], info["away"] = parti[0].strip(), parti[1].strip()
            if self.follow_db.segui(ev, info):
                self._scritti.add(ev)

    def _pulisci(self, ora: float) -> None:
        """Mercati CHIUSI senza ordini vivi escono; voci di comando uscite dal
        feed da 15 minuti e senza ordini escono."""
        mercati = self._mercati_flumine()
        protetti = self._protetti()
        for chiave, v in self.piano.voci().items():
            chiusi = []
            for mid in v.mercati:
                m = mercati.get(mid)
                if m is None:
                    inviato = self._inviato_ts.get(mid)
                    if (mid in self._applicati and inviato is not None
                            and ora - inviato > MAI_ARRIVATO_S):
                        chiusi.append(mid)       # mai arrivato / tolto da flumine
                    continue
                stato = str(getattr(getattr(m, "market_book", None), "status", "") or "")
                if getattr(m, "closed", False) is True or stato == "CLOSED":
                    try:
                        vivi = list(getattr(m.blotter, "live_orders", []) or [])
                    except Exception:  # noqa: BLE001
                        vivi = ["?"]
                    if not vivi:
                        chiusi.append(mid)
            uscita = None
            if chiusi:
                uscita = self.piano.togli_mercati(chiave, chiusi)
            elif (v.priorita == PRI_COMANDO and chiave not in protetti and v.visto_feed
                  and ora - v.visto_feed > 900.0 and ora - v.ultimo_uso > 900.0):
                uscita = self.piano.togli(chiave)
            if uscita is not None:
                logger.info("[auto-follow] %s non piu' seguito (%s)", chiave,
                            "mercati chiusi" if chiusi else "uscito dal feed")
                if uscita.event_id and uscita.event_id in self._scritti \
                        and self.follow_db is not None:
                    self._scritti.discard(uscita.event_id)
                    self.follow_db.chiudi(uscita.event_id)

    def _giro_feed(self, ora: float) -> None:
        if self._feed is None or ora - self._ultimo_feed < self.feed_s:
            return
        self._ultimo_feed = ora
        try:
            collegati = {str(a) for a in self._attori_collegati()}
        except Exception:  # noqa: BLE001
            collegati = set()
        attivi = collegati & self.attori_calcio
        self.feed_info["attori"] = sorted(attivi)
        if not attivi:
            # nessun bot calcio sul canale: le candidate senza ordini si liberano
            protetti = self._protetti()
            for chiave, v in self.piano.voci().items():
                if v.priorita == PRI_CANDIDATA and chiave not in protetti:
                    uscita = self.piano.togli(chiave)
                    if uscita is not None and uscita.event_id in self._scritti \
                            and self.follow_db is not None:
                        self._scritti.discard(uscita.event_id)
                        self.follow_db.chiudi(uscita.event_id)
            return
        righe = self._feed()
        if righe is None:
            self.feed_info.update({"letto": False})
            return                               # feed muto: non si toglie niente
        partite = partite_dal_feed(righe)
        self.feed_info.update({"letto": True, "partite": len(partite), "ts": time.time()})
        nel_feed = {str(r["event_id"]) for r in partite}
        protetti = self._protetti()
        for chiave, v in self.piano.voci().items():
            if chiave in nel_feed:
                vv = self.piano.voce(chiave)
                if vv is not None:
                    vv.visto_feed = ora
            elif v.priorita == PRI_CANDIDATA and chiave not in protetti:
                uscita = self.piano.togli(chiave)
                if uscita is not None and uscita.event_id in self._scritti \
                        and self.follow_db is not None:
                    self._scritti.discard(uscita.event_id)
                    self.follow_db.chiudi(uscita.event_id)
        for r in partite:
            ev = str(r["event_id"])
            if self.piano.e_manuale(ev):
                continue
            info = {k: r.get(k) for k in ("home", "away", "event_name", "open_date")}
            esito = self.piano.richiedi(ev, mercati_della_riga(r), priorita=PRI_CANDIDATA,
                                        protetti=protetti, puo_espellere=False, ora=ora,
                                        motivo="feed", info=info)
            vv = self.piano.voce(ev)
            if vv is not None:
                vv.visto_feed = ora
            if not esito.ok:
                continue                         # tetto: le altre restano fuori
        self._sveglia.set()

    # ------------------------------------------------------------ stato
    def stato(self) -> Dict[str, Any]:
        voci = self.piano.voci()
        per_pri: Dict[str, int] = {}
        for v in voci.values():
            n = NOMI_PRIORITA.get(v.priorita, str(v.priorita))
            per_pri[n] = per_pri.get(n, 0) + 1
        protetti = self._protetti()
        return {
            "acceso": True,
            "tetto_mercati": self.piano.tetto,
            "limite_betfair_per_connessione": LIMITE_BETFAIR_MERCATI,
            "connessioni_di_mercato": 1,
            "mercati_seguiti": len(self.piano.mercati()),
            "mercati_manuali": len(self.piano.mercati_manuali()),
            "mercati_auto": len(self.mercati_auto()),
            "mercati_sottoscritti": len(self._applicati),
            "eventi_auto": len(voci),
            "eventi_auto_con_posizioni": len(protetti),
            "per_priorita": per_pri,
            "righe_db": (None if self.follow_db is None
                         else bool(self.follow_db.colonna_origine)),
            "feed": dict(self.feed_info),
            "conti": dict(self.conti),
            "ultimo_errore": self.ultimo_errore,
        }

    def _annuncia(self) -> None:
        s = self.stato()
        firma = (s["eventi_auto"], s["mercati_seguiti"], s["mercati_sottoscritti"],
                 s["eventi_auto_con_posizioni"], s["conti"]["espulsi"],
                 s["conti"]["rifiuti_tetto"], s["feed"].get("partite"))
        if firma == self._firma_stato:
            return
        self._firma_stato = firma
        logger.info("[auto-follow] seguiti da soli %d eventi (%d mercati) + manuali %d "
                    "mercati = %d/%d sulla connessione di mercato (limite Betfair %d); "
                    "con posizioni %d; feed %s partite (%s); espulsi %d, rifiuti tetto %d",
                    s["eventi_auto"], s["mercati_auto"], s["mercati_manuali"],
                    s["mercati_seguiti"], s["tetto_mercati"], LIMITE_BETFAIR_MERCATI,
                    s["eventi_auto_con_posizioni"], s["feed"].get("partite"),
                    s["feed"].get("fonte"), s["conti"]["espulsi"],
                    s["conti"]["rifiuti_tetto"])
        if self._pubblica is not None:
            try:
                self._pubblica(s)
            except Exception:  # noqa: BLE001 - la UI non ferma l'auto-follow
                pass
