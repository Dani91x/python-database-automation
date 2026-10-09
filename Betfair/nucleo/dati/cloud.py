"""Client cloud unico del nucleo (comparto G, tappa T2): implementazione del protocollo ``Cloud``.

Scopo
    UN client verso Supabase/PostgREST con UNA politica di errore per profilo di processo
    (``bot``, ``runner``, ``catena``), al posto dei due client e delle quattro politiche di oggi
    (G par. 1.1). Non riscrive nulla di ``db_client.py``: ne IMPORTA il client per thread
    (``get_supabase_client``), la classificazione dei guasti (``classifica_guasto_rete``) e il
    motore dei ritentativi (``con_ritentativi``), quindi classifica ogni risposta esattamente
    come oggi la catena backfill.

Regole (piano T2, G par. 3 punto 4)
    * si ritenta SOLO cio' che e' idempotente: letture, upsert, RPC di sola lettura;
    * MAI un insert (log senza ``uid``: un ritento scrive due volte), MAI un patch o un delete
      (proposta prudente: in T2 il piano ritenta solo letture e upsert), MAI una RPC che
      scrive (registro: ``RPC_SCRIVENTI_ELENCO``) ne' una RPC sconosciuta;
    * MAI un 4xx, MAI il 57014 (statement timeout: oggi non ritentato per scelta): decide
      ``db_client.classifica_guasto_rete``, che per questi restituisce None;
    * timeout per profilo: ``bot`` = profilo bot di ``db_client`` (5 s connessione, 20 s lettura,
      ``usa_timeout_bot``), ``runner`` e ``catena`` = default della libreria (120 s) come oggi;
    * cache per lettura con ``cache_s`` (solo letture e RPC di lettura; gli errori non vanno
      mai in cache).

Entrate: nome tabella o RPC, filtri/argomenti. Uscite: righe (copie profonde), valore della RPC.
Errori: risale l'eccezione originale (4xx, 57014, errori applicativi) oppure
``db_client.GuastoRete`` dopo l'ultimo tentativo di un guasto di rete persistente.

Cosa NON fa
    Importarlo non apre file, socket o thread (``db_client`` si importa alla prima chiamata:
    il suo ``config`` legge il file ``.env``). Non accende il profilo bot da solo
    (``attiva_profilo`` va chiamato dal ``main`` del processo, come ``usa_timeout_bot`` oggi).
    Non sostituisce ancora nessuna chiamata di oggi: l'aggancio e' l'ondata 2
    (``ARCH_DATI_CLIENT=vecchio|nuovo``, vedi ``interruttore_client``).
"""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, Dict, Iterable, Literal, Mapping, Optional, Sequence, Tuple

from .contratto import Operazione
from .registro import REGISTRO, RegistroTabelle, e_rpc_di_lettura

logger = logging.getLogger("nucleo.dati.cloud")

Profilo = Literal["bot", "runner", "catena"]

#: le attese dei bot e del runner sono quelle che hanno oggi le scritture del runner
#: (``Betfair/stream/db.py:44`` ``_exec_retry`` -> ``net_retry.with_backoff(attempts=3,
#: base_delay=0.15)``: 0,15 s e 0,30 s), ma con la classificazione di ``db_client``
ATTESE_BOT_S: Tuple[float, ...] = (0.15, 0.30)
#: variabile d'ambiente dell'interruttore per processo (ondata 2)
ENV_INTERRUTTORE = "ARCH_DATI_CLIENT"
_OPERATORI = frozenset({"gt", "gte", "lt", "lte", "neq", "like", "ilike"})
_CHIAVI_SPECIALI = frozenset({"select", "order", "limit"})


@dataclass(frozen=True)
class PoliticaProfilo:
    """Timeout e ritentativi di UN profilo di processo."""

    nome: Profilo
    attese_s: Tuple[float, ...]          # attese fra i tentativi (solo operazioni idempotenti)
    timeout_bot: bool                    # True: db_client.usa_timeout_bot(); False: 120 s di libreria
    nota: str


def _db() -> ModuleType:
    """``db_client`` importato alla prima chiamata (mai all'import di questo modulo)."""
    import db_client

    return db_client


def politica(profilo: Profilo) -> PoliticaProfilo:
    """La politica del profilo; ``catena`` usa le attese di ``db_client.ATTESE_RETE_S``."""
    if profilo == "bot":
        return PoliticaProfilo("bot", ATTESE_BOT_S, True,
                               "servizi dei bot: 5 s connessione / 20 s lettura (db_client.timeout_bot)")
    if profilo == "runner":
        return PoliticaProfilo("runner", ATTESE_BOT_S, False,
                               "runner: timeout di libreria 120 s come oggi (profilo bot = decisione utente)")
    if profilo == "catena":
        return PoliticaProfilo("catena", tuple(_db().ATTESE_RETE_S), False,
                               "catena backfill e action: 2-4-8-16-32 s (db_client.con_ritentativi)")
    raise ValueError(f"profilo sconosciuto: {profilo!r} (bot, runner, catena)")


def interruttore_client() -> Literal["vecchio", "nuovo"]:
    """``ARCH_DATI_CLIENT`` del processo: ``nuovo`` solo se scritto esplicitamente."""
    valore = (os.environ.get(ENV_INTERRUTTORE) or "").strip().lower()
    return "nuovo" if valore == "nuovo" else "vecchio"


def _chiave_cache(tipo: str, nome: str, dati: Mapping[str, Any]) -> str:
    return tipo + ":" + nome + ":" + json.dumps(dati, sort_keys=True, default=repr)


def costruisci_lettura(client: Any, tabella: str, filtri: Mapping[str, Any]) -> Any:
    """Builder PostgREST di una SELECT dai filtri: ``select`` (colonne), ``order``
    ("col" o "col.desc", piu' colonne separate da virgola), ``limit``; ogni altra chiave e'
    una colonna: scalare -> ``eq``, lista/tupla/insieme -> ``in``, None -> ``is null``,
    ``col__op`` con op in gt/gte/lt/lte/neq/like/ilike -> l'operatore."""
    f = dict(filtri)
    q = client.table(tabella).select(str(f.pop("select", "*")))
    ordine = f.pop("order", None)
    limite = f.pop("limit", None)
    for chiave, valore in f.items():
        colonna, _, op = chiave.partition("__")
        if op:
            q = getattr(q, op)(colonna, valore)
        elif valore is None:
            q = q.is_(colonna, "null")
        elif isinstance(valore, (list, tuple, set, frozenset)):
            q = q.in_(colonna, list(valore))
        else:
            q = q.eq(colonna, valore)
    for pezzo in (str(ordine).split(",") if ordine else ()):
        colonna, _, verso = pezzo.strip().partition(".")
        q = q.order(colonna, desc=(verso == "desc"))
    if limite is not None:
        q = q.limit(int(limite))
    return q


def _valida_filtri(filtri: Mapping[str, Any]) -> None:
    for chiave in filtri:
        if chiave in _CHIAVI_SPECIALI:
            continue
        _, _, op = chiave.partition("__")
        if op and op not in _OPERATORI:
            raise ValueError(f"operatore di filtro sconosciuto: {chiave!r} (ammessi: {sorted(_OPERATORI)})")


class _Cache:
    """Cache per lettura: chiave -> (scadenza monotona, valore). Thread-safe. Mai errori."""

    def __init__(self, orologio: Callable[[], float]) -> None:
        self._orologio = orologio
        self._lock = threading.Lock()
        self._voci: Dict[str, Tuple[float, Any]] = {}

    def prendi(self, chiave: str) -> Tuple[bool, Any]:
        with self._lock:
            voce = self._voci.get(chiave)
            if voce is None:
                return False, None
            if self._orologio() >= voce[0]:
                del self._voci[chiave]
                return False, None
            return True, copy.deepcopy(voce[1])

    def metti(self, chiave: str, valore: Any, durata_s: float) -> None:
        with self._lock:
            self._voci[chiave] = (self._orologio() + float(durata_s), copy.deepcopy(valore))

    def svuota(self) -> None:
        with self._lock:
            self._voci.clear()


class ClienteCloud:
    """Il client cloud del nucleo (protocollo ``Cloud`` del contratto, piu' ``scrivi`` come
    estensione additiva per il postino). Un oggetto per processo; sicuro fra thread (il
    client PostgREST e' per thread, come oggi in ``db_client``)."""

    def __init__(self, profilo: Profilo = "bot", *, registro: RegistroTabelle = REGISTRO,
                 fabbrica_client: Optional[Callable[[], Any]] = None,
                 orologio: Callable[[], float] = time.monotonic,
                 dormi: Optional[Callable[[float], Any]] = None,
                 casuale: Optional[Callable[[], float]] = None,
                 rpc_sola_lettura: Iterable[str] = ()) -> None:
        self._politica = politica(profilo)
        self._registro = registro
        self._fabbrica = fabbrica_client
        self._dormi = dormi
        self._casuale = casuale
        self._rpc_lettura = frozenset(rpc_sola_lettura)
        self._cache = _Cache(orologio)
        self._lock = threading.Lock()
        self._conti: Dict[str, int] = {"letture": 0, "rpc": 0, "scritture": 0, "colpi_cache": 0,
                                       "con_ritentativi": 0, "un_tentativo": 0}

    # ------------------------------------------------------------------ profilo
    @property
    def profilo(self) -> PoliticaProfilo:
        return self._politica

    def attiva_profilo(self) -> Any:
        """Applica il timeout del profilo a TUTTO il processo (``db_client``, come oggi
        ``usa_timeout_bot`` nel ``main``). Ritorna il timeout applicato o None (libreria)."""
        if self._politica.timeout_bot:
            return _db().usa_timeout_bot()
        corrente = _db().timeout_corrente()
        if corrente is not None:
            logger.warning("[cloud] profilo %s in un processo col timeout bot gia' acceso: resta %s",
                           self._politica.nome, corrente)
        return corrente

    # ------------------------------------------------------------------ Cloud
    def leggi(self, tabella: str, filtri: Mapping[str, Any], *, cache_s: float = 0.0) -> Sequence[Mapping[str, Any]]:
        """SELECT con i filtri (vedi ``costruisci_lettura``). Idempotente: ritentata."""
        _valida_filtri(filtri)
        chiave = _chiave_cache("t", tabella, filtri)
        if cache_s > 0:
            trovato, valore = self._cache.prendi(chiave)
            if trovato:
                self._conta("colpi_cache")
                return valore
        self._conta("letture")
        risposta = self._esegui(lambda c: costruisci_lettura(c, tabella, filtri), f"leggi {tabella}", True)
        righe = [dict(r) for r in (getattr(risposta, "data", None) or [])]
        if cache_s > 0:
            self._cache.metti(chiave, righe, cache_s)
        return copy.deepcopy(righe) if cache_s > 0 else righe

    def rpc(self, nome: str, args: Mapping[str, Any], *, cache_s: float = 0.0) -> Any:
        """Chiama una RPC. Ritentata (e mettibile in cache) SOLO se di lettura."""
        ritenta = self.rpc_ritentabile(nome)
        if cache_s > 0 and not ritenta:
            raise ValueError(f"cache_s su una RPC che scrive o non riconosciuta: {nome}")
        chiave = _chiave_cache("r", nome, args)
        if cache_s > 0:
            trovato, valore = self._cache.prendi(chiave)
            if trovato:
                self._conta("colpi_cache")
                return valore
        self._conta("rpc")
        risposta = self._esegui(lambda c: c.rpc(nome, dict(args)), f"rpc {nome}", ritenta)
        dati = getattr(risposta, "data", None)
        if cache_s > 0:
            self._cache.metti(chiave, dati, cache_s)
            return copy.deepcopy(dati)
        return dati

    # ------------------------------------------------------------------ estensione: scrittura
    def scrivi(self, tabella: str, op: Operazione, righe: Any, *, on_conflict: Optional[str] = None,
               ignora_duplicati: bool = False, filtri: Optional[Mapping[str, Any]] = None) -> Sequence[Mapping[str, Any]]:
        """Scrittura (estensione per il postino), SOLO su tabelle del registro. Ritentata SOLO
        l'``upsert``; ``insert``, ``patch`` e ``delete`` hanno UN tentativo (l'errore risale identico)."""
        if op not in ("upsert", "insert", "patch", "delete"):
            raise ValueError(f"operazione sconosciuta: {op!r}")
        if tabella not in self._registro.tabelle():
            # il cloud non riceve righe da tabelle che il registro non conosce (R23)
            raise ValueError(f"tabella non registrata: {tabella} (Betfair/nucleo/dati/registro.py)")
        if op in ("patch", "delete") and not filtri:
            raise ValueError(f"{op} senza filtri: rifiutato (toccherebbe tutta la tabella {tabella})")
        _valida_filtri(filtri or {})

        def costruisci(c: Any) -> Any:
            t = c.table(tabella)
            if op == "upsert":
                return t.upsert(righe, on_conflict=on_conflict or "", ignore_duplicates=ignora_duplicati)
            if op == "insert":
                return t.insert(righe)
            q = t.update(righe) if op == "patch" else t.delete()
            for colonna, valore in (filtri or {}).items():
                q = q.in_(colonna, list(valore)) if isinstance(valore, (list, tuple, set)) else q.eq(colonna, valore)
            return q

        self._conta("scritture")
        risposta = self._esegui(costruisci, f"{op} {tabella}", op == "upsert")
        return [dict(r) for r in (getattr(risposta, "data", None) or [])]

    # ------------------------------------------------------------------ servizio
    def rpc_ritentabile(self, nome: str) -> bool:
        """True se la RPC e' di sola lettura: non registrata come scrivente, non fra quelle
        NON idempotenti di ``db_client``, e di lettura per nome (get_/list_) o dichiarata."""
        db = _db()
        if self._registro.rpc_scrive(nome) or nome in db.RPC_NON_IDEMPOTENTI:
            return False
        return e_rpc_di_lettura(nome, self._rpc_lettura | db.RPC_LETTURA_ACTION)

    def svuota_cache(self) -> None:
        self._cache.svuota()

    def statistiche(self) -> Mapping[str, int]:
        with self._lock:
            return dict(self._conti)

    def _conta(self, voce: str) -> None:
        with self._lock:
            self._conti[voce] += 1

    def _client(self) -> Any:
        return (self._fabbrica or _db().get_supabase_client)()

    def _esegui(self, costruisci: Callable[[Any], Any], etichetta: str, ritenta: bool) -> Any:
        """Esegue la query. ``ritenta``: con ``db_client.con_ritentativi`` (solo guasti di rete
        classificati); altrimenti UN tentativo e l'errore risale cosi' com'e'."""
        if not ritenta:
            self._conta("un_tentativo")
            return costruisci(self._client()).execute()
        self._conta("con_ritentativi")
        return _db().con_ritentativi(lambda: costruisci(self._client()).execute(), etichetta=etichetta,
                                     attese=self._politica.attese_s, dormi=self._dormi, casuale=self._casuale)
