"""Client cloud unico del nucleo (comparto G, tappa T2): implementazione del protocollo ``Cloud``.

Scopo
    UN client verso Supabase/PostgREST con UNA politica di errore per profilo di processo
    (``bot``, ``runner``, ``catena``), al posto dei due client e delle quattro politiche di oggi
    (G par. 1.1). Non riscrive nulla di ``db_client.py``: ne IMPORTA il client per thread
    (``get_supabase_client``), la classificazione dei guasti (``classifica_guasto_rete``) e il
    motore dei ritentativi (``con_ritentativi``), quindi classifica ogni risposta esattamente
    come oggi la catena backfill.

Regole (piano T2, G par. 3 punto 4)
    * si ritenta SOLO cio' che e' idempotente: letture, RPC di sola lettura, upsert che arbitrano
      sulla chiave naturale del registro (o su ``uid`` ignorando i duplicati: log con U-50);
      un upsert senza ``on_conflict`` su una tabella di log e' un INSERT e NON si ritenta;
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
from typing import Any, Callable, Dict, FrozenSet, Iterable, Literal, Mapping, Optional, Sequence, Tuple

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
#: RPC che scrivono la tabella passata in ``p_tabella`` (EXECUTE dinamico; in ombra
#: ``<tabella>_ombra``): il client la controlla sul registro come ``scrivi`` (integrazione
#: W1-G1 + W1-C1, 09/10): una tabella non registrata, o SOLO LOCALE, non parte mai
RPC_CON_TABELLA: FrozenSet[str] = frozenset({"postino_consegna"})
SUFFISSO_OMBRA = "_ombra"


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
    q = applica_filtri(q, f)
    for pezzo in (str(ordine).split(",") if ordine else ()):
        colonna, _, verso = pezzo.strip().partition(".")
        q = q.order(colonna, desc=(verso == "desc"))
    if limite is not None:
        q = q.limit(int(limite))
    return q


def applica_filtri(q: Any, filtri: Mapping[str, Any]) -> Any:
    """Gli stessi filtri per letture, patch e delete: scalare -> ``eq``, lista/tupla/insieme
    -> ``in``, None -> ``is null``, ``col__op`` -> l'operatore (gt/gte/lt/lte/neq/like/ilike)."""
    for chiave, valore in filtri.items():
        colonna, _, op = chiave.partition("__")
        if op:
            q = getattr(q, op)(colonna, valore)
        elif valore is None:
            q = q.is_(colonna, "null")
        elif isinstance(valore, (list, tuple, set, frozenset)):
            q = q.in_(colonna, list(valore))
        else:
            q = q.eq(colonna, valore)
    return q


def _valida_filtri(filtri: Mapping[str, Any]) -> None:
    for chiave in filtri:
        if chiave in _CHIAVI_SPECIALI:
            continue
        _, _, op = chiave.partition("__")
        if op and op not in _OPERATORI:
            raise ValueError(f"operatore di filtro sconosciuto: {chiave!r} (ammessi: {sorted(_OPERATORI)})")


class _Cache:
    """Cache per lettura: chiave -> (scadenza monotona, valore). Thread-safe. Mai errori.

    Ogni voce appartiene a un GRUPPO (``t:<tabella>`` per le letture, ``r`` per tutte le RPC) con
    una generazione: ``svuota_tabella`` la incrementa, e una lettura iniziata PRIMA (in volo
    durante la scrittura) non rimette in cache il suo valore vecchio. Le voci scadute si potano
    ogni ``POTA_OGNI`` inserimenti, non solo alla rilettura della stessa chiave."""

    POTA_OGNI = 64

    def __init__(self, orologio: Callable[[], float]) -> None:
        self._orologio = orologio
        self._lock = threading.Lock()
        self._voci: Dict[str, Tuple[float, Any]] = {}
        self._generazioni: Dict[str, int] = {}
        self._inserimenti = 0

    def generazione(self, gruppo: str) -> int:
        with self._lock:
            return self._generazioni.get(gruppo, 0)

    def __len__(self) -> int:
        with self._lock:
            return len(self._voci)

    def prendi(self, chiave: str) -> Tuple[bool, Any]:
        with self._lock:
            voce = self._voci.get(chiave)
            if voce is None:
                return False, None
            if self._orologio() >= voce[0]:
                del self._voci[chiave]
                return False, None
            return True, copy.deepcopy(voce[1])

    def metti(self, chiave: str, valore: Any, durata_s: float, *, gruppo: str, generazione: int) -> bool:
        """Mette in cache SOLO se il gruppo non e' stato invalidato da quando la lettura e' partita."""
        with self._lock:
            if self._generazioni.get(gruppo, 0) != generazione:
                return False
            adesso = self._orologio()
            self._voci[chiave] = (adesso + float(durata_s), copy.deepcopy(valore))
            self._inserimenti += 1
            if self._inserimenti % self.POTA_OGNI == 0:
                for k in [k for k, (scade, _) in self._voci.items() if adesso >= scade]:
                    del self._voci[k]
            return True

    def svuota(self) -> None:
        with self._lock:
            self._voci.clear()

    def svuota_tabella(self, tabella: str) -> None:
        """Dopo una scrittura su ``tabella``: toglie le sue letture (``t:<tabella>:...``) e TUTTE le
        RPC in cache (``r:...``): una RPC di lettura puo' leggere qualunque tabella e il registro
        conosce solo le tabelle delle RPC che SCRIVONO, quindi la scelta prudente e' svuotarle tutte.
        Incrementa le generazioni dei due gruppi (le letture in volo non rimettono il vecchio)."""
        prefisso = f"t:{tabella}:"
        with self._lock:
            for gruppo in (f"t:{tabella}", "r"):
                self._generazioni[gruppo] = self._generazioni.get(gruppo, 0) + 1
            for chiave in [k for k in self._voci if k.startswith(prefisso) or k.startswith("r:")]:
                del self._voci[chiave]


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
        gruppo = f"t:{tabella}"
        generazione = self._cache.generazione(gruppo)
        risposta = self._esegui(lambda c: costruisci_lettura(c, tabella, filtri), f"leggi {tabella}", True)
        righe = [dict(r) for r in (getattr(risposta, "data", None) or [])]
        if cache_s > 0:
            self._cache.metti(chiave, righe, cache_s, gruppo=gruppo, generazione=generazione)
        return copy.deepcopy(righe) if cache_s > 0 else righe

    def rpc(self, nome: str, args: Mapping[str, Any], *, cache_s: float = 0.0) -> Any:
        """Chiama una RPC. Ritentata (e mettibile in cache) SOLO se di lettura. Una RPC che
        scrive la tabella di ``p_tabella`` (``RPC_CON_TABELLA``) parte SOLO su una tabella del
        registro (o la sua ``_ombra``): altrimenti ``ValueError``, prima della rete."""
        if nome in RPC_CON_TABELLA:
            self._controlla_tabella_rpc(nome, args)
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
        generazione = self._cache.generazione("r")
        risposta = self._esegui(lambda c: c.rpc(nome, dict(args)), f"rpc {nome}", ritenta)
        dati = getattr(risposta, "data", None)
        if cache_s > 0:
            self._cache.metti(chiave, dati, cache_s, gruppo="r", generazione=generazione)
            return copy.deepcopy(dati)
        return dati

    # ------------------------------------------------------------------ estensione: scrittura
    def scrivi(self, tabella: str, op: Operazione, righe: Any, *, on_conflict: Optional[str] = None,
               ignora_duplicati: bool = False, filtri: Optional[Mapping[str, Any]] = None) -> Sequence[Mapping[str, Any]]:
        """Scrittura (estensione per il postino), SOLO su tabelle del registro. Ritentato SOLO
        l'``upsert`` idempotente (``upsert_ritentabile``); ``insert``, ``patch``, ``delete`` e gli
        upsert senza la chiave naturale hanno UN tentativo (l'errore risale identico). Dopo la
        scrittura le letture in cache della stessa tabella sono invalidate.
        Nota: nei processi con ``DB_RESILIENZA_ACTION=1`` (solo action) il TRASPORTO di
        ``db_client`` ritenta da se' anche PATCH/DELETE: li' il "un tentativo" di qui non vale."""
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
            return applica_filtri(t.update(righe) if op == "patch" else t.delete(), filtri or {})

        ritenta = op == "upsert" and self.upsert_ritentabile(tabella, on_conflict, ignora_duplicati)
        self._conta("scritture")
        try:
            risposta = self._esegui(costruisci, f"{op} {tabella}", ritenta)
        finally:
            self._cache.svuota_tabella(tabella)       # anche su errore: l'esito puo' essere ambiguo
        return [dict(r) for r in (getattr(risposta, "data", None) or [])]

    def upsert_ritentabile(self, tabella: str, on_conflict: Optional[str], ignora_duplicati: bool) -> bool:
        """Un upsert e' idempotente SOLO se arbitra sulla chiave naturale del registro (allora
        riscriverlo da' la stessa riga) o, per i log, su ``uid`` ignorando i duplicati (U-50).
        Senza ``on_conflict`` su una tabella senza chiave e' un INSERT: mai ritentato."""
        colonne = tuple(c.strip() for c in (on_conflict or "").split(",") if c.strip())
        if not colonne:
            return False
        if colonne == ("uid",):
            return ignora_duplicati
        return colonne == self._registro.spec(tabella).chiave_naturale

    # ------------------------------------------------------------------ servizio
    def _controlla_tabella_rpc(self, nome: str, args: Mapping[str, Any]) -> None:
        """La tabella di ``p_tabella`` deve essere del registro (in ombra: la sua base)."""
        tabella = str(args.get("p_tabella") or "")
        registrate = self._registro.tabelle()
        base = tabella[:-len(SUFFISSO_OMBRA)] if tabella.endswith(SUFFISSO_OMBRA) else tabella
        if tabella not in registrate and base not in registrate:
            # il cloud non riceve righe da tabelle che il registro non conosce (R23)
            raise ValueError(f"rpc {nome}: tabella non registrata: {tabella!r} "
                             f"(Betfair/nucleo/dati/registro.py)")

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
