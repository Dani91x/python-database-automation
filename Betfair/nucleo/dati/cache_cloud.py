"""Cache degli algoritmi del cloud fuori dal ciclo di decisione (comparto G, tappa T7).

Scopo
    Togliere dal ciclo di decisione le letture SINCRONE del cloud degli algoritmi che restano nel
    cloud (G parte 2, 04 par. 6.3) senza cambiare un valore ne' una scadenza:
      * tabella HT->FT (RPC ``get_omega_ht_ft``) e tabella per minuto (RPC ``get_omega_minute_ft``)
        di Omega (G-035) e di Mike (G-034): ``ReplicaEmpirica``, prefetch per lega di TUTTI i
        bucket, riletta dopo ogni giro del pg_cron (sentinella: ``omega_transitions_state``,
        ``built_at`` di ``omega_ht_ft_transitions``, ``omega_build_jobs``);
      * dossier pre-match di Mike (G-033): ``DossierPrematch``, ponte evento->fixture e righe di
        ``fixture_predictions`` lette a blocchi PRIMA dell'aggancio (``lambda_home/away``, ``rho``,
        ``p4_pre``, ``p_under35_cal`` restano calcolati da ``mike/dossier.build_prematch``).

Le scadenze di oggi NON cambiano (U-53): la cache di Omega scade dopo 6 h
(``omega_service.EMPIRICAL_CACHE_TTL_S``) e quella di Mike mai (``mike/dossier._EMPIRICAL_CACHE``):
restano NEI BOT, sopra questa replica, che risponde con le STESSE firme delle funzioni di oggi
(``omega_db.ht_ft_transitions``/``minute_transitions``, ``mike.db.fixture_id_for_event``/
``fixture_lambdas``/``fixture_analysis``/``ht_ft_rows``) e con le STESSE righe dell'RPC, compresa la
distinzione "[] = vuota, None = errore (mai in cache)". Il dossier tiene in memoria SOLO le risposte
positive (fixture trovata, gol attesi presenti) e per al massimo ``SCADENZA_DOSSIER_S`` = 300 s (il
ritento di Mike, ``mike/service._DOSSIER_RETRY_SEC``): un negativo va sempre al ripiego, come oggi.

Decisione 10 dell'utente (10/10/2026): "tutta l'app in tempo reale per Betfair; il cloud solo come
backup; il resto sul DB locale". I dati che il cloud CALCOLA (dossier di Mike, tabelle di Omega)
arrivano APPENA il cloud ricalcola, non fino a 300 s dopo: ``Sorveglianza`` (par. 4) fa UNA
chiamata leggera ogni ``INTERVALLO_RAPIDO_S`` = 5 s (RPC ``nucleo_sentinella_cloud`` della
migrazione ``migrations/nucleo_sentinella_cloud_2026-10-10.sql``: impronta di Omega + per ogni
evento seguito ponte, presenza e ``nucleo_versione`` della riga di ``fixture_predictions``) e al
cambio di un'impronta rilegge SOLO quel pezzo. Senza la migrazione ripiega sulle letture REST di
oggi ogni ``INTERVALLO_LETTURE_S`` = 15 s. La scadenza di 300 s del dossier resta come riserva
(mai piu' lento di oggi se la sorveglianza tace); la lettura diretta di riserva (``ripiego``) resta
sempre accesa.

Entrate: un ``Cloud`` (``cloud.ClienteCloud``), le leghe e gli eventi da preparare e da seguire.
Uscite: righe identiche a quelle delle RPC/letture di oggi, servite dalla memoria; gli eventi il cui
dossier e' cambiato nel cloud (``DossierPrematch.prendi_cambiati``).

Cosa NON fa
    Non importa nessun bot (le funzioni di oggi sono gli ARBITRI nei test). Non decide nulla: non
    ricostruisce il dossier di Mike ne' svuota le cache dei bot (Omega 6 h, Mike mai: U-53), le
    rende solo fresche e dice CHI e' cambiato. Non usa Supabase Realtime (il client sincrono di
    supabase-py 2.28 non lo implementa: ``SyncRealtimeClient.channel`` solleva NotImplementedError).
    Non apre thread all'import: i thread di prefetch e di sorveglianza nascono solo con ``avvia`` e
    muoiono con ``ferma``. Un mancato prefetch (chiave assente) va al ``ripiego`` (la funzione di
    oggi, sincrona, identica) se c'e', altrimenti risponde None come un errore di oggi (mai in
    cache) e chiede di nuovo il prefetch della lega (al piu' ogni ``RITARDO_RIPREFETCH_S``): e'
    l'unico punto in cui il nuovo puo' differire, e l'ombra (ondata 2,
    ``ARCH_PREFETCH_<BOT>=vecchio|ombra|nuovo``) lo misura.
"""
from __future__ import annotations

import json
import logging
import math
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .contratto import Cloud

logger = logging.getLogger("nucleo.dati.cache_cloud")

# ---------------------------------------------------------------------------
# Costanti di oggi (provate uguali a quelle dei bot nei test di parita')
# ---------------------------------------------------------------------------
#: bucket della tabella per minuto: ``omega_empirical.minute_bucket`` (passo 5, max 85 FT, 40 HT)
BUCKET_FT: Tuple[int, ...] = tuple(range(0, 86, 5))
BUCKET_HT: Tuple[int, ...] = tuple(range(0, 41, 5))
CHIAVI_PER_LEGA = 1 + len(BUCKET_FT) + len(BUCKET_HT)
#: scadenze delle cache DEI BOT, che restano nei bot (U-53): qui solo dichiarate
SCADENZA_OMEGA_S = 6 * 3600.0        # omega_service.EMPIRICAL_CACHE_TTL_S
SCADENZA_MIKE_S: Optional[float] = None  # mike/dossier._EMPIRICAL_CACHE: mai
#: ogni quanto il thread rilegge la sentinella (giro del pg_cron delle 04:00 UTC)
INTERVALLO_SORVEGLIANZA_S = 300.0
#: una lega con chiavi mancanti si richiede di nuovo al piu' ogni tanti secondi
RITARDO_RIPREFETCH_S = 60.0
#: dopo tante letture della sentinella fallite DI FILA si rilegge comunque tutto (scelta prudente:
#: con l'intervallo di serie di 300 s una ricostruzione non resta invisibile oltre ~15 minuti)
SENTINELLA_ERRORI_MAX = 3
_SENTINELLA_IGNOTA = "?ignota"
#: il dossier positivo vale al massimo quanto il ritento di Mike (mike/service._DOSSIER_RETRY_SEC)
SCADENZA_DOSSIER_S = 300.0
COLONNE_PREMATCH = "fixture_id,league_id,tactical_engine_json,db_json_analisi,home_team_id,away_team_id"
BLOCCO_IN = 50                        # valori per filtro ``in`` (URL corte)
ENV_PREFETCH = "ARCH_PREFETCH_{bot}"  # vecchio | ombra | nuovo (ondata 2)
#: decisione 10 (10/10): cadenza della sentinella leggera con la RPC (una chiamata per giro)
INTERVALLO_RAPIDO_S = 5.0
#: cadenza senza la migrazione (letture REST di oggi: 3 + 2 per 50 eventi + 1 per 50 fixture a giro)
INTERVALLO_LETTURE_S = 15.0
#: RPC assente (migrazione non applicata): la si riprova al piu' ogni tanti secondi
RIPROVA_RPC_S = 600.0
#: eventi per chiamata della RPC (tetto della funzione SQL: 500)
BLOCCO_RPC = 500
#: codici di "funzione assente": PostgREST (schema cache) e PostgreSQL (undefined_function)
CODICI_RPC_ASSENTE = frozenset({"PGRST202", "42883"})
#: attese dopo giri falliti DI FILA (15, 30, poi 60 s fissi); al primo giro riuscito si torna alla cadenza
BACKOFF_ERRORI_S: Tuple[float, ...] = (15.0, 30.0, 60.0)
#: anche con la versione del trigger una voce del dossier si rilegge comunque dopo tanti secondi dalla
#: LETTURA (riserva contro uno scrittore che aggira il trigger: replica, DISABLE TRIGGER, ALTER TYPE)
SCADENZA_MASSIMA_S = 3600.0


def _lega(league_id: Any) -> Optional[int]:
    """Come ``omega_db``: ``int(league_id)`` o None."""
    return int(league_id) if league_id is not None else None


def _lista_o_vuota(dati: Any) -> List[Dict[str, Any]]:
    """Come ``omega_db``: una lista resta lista (copia), ogni altra cosa diventa []."""
    return list(dati) if isinstance(dati, list) else []


def _copia(righe: Optional[Sequence[Mapping[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    return None if righe is None else [dict(r) for r in righe]


# ---------------------------------------------------------------------------
# 1. Le due RPC di Omega con gli argomenti e i ritorni di oggi
# ---------------------------------------------------------------------------
class SorgenteOmega:
    """``get_omega_ht_ft`` e ``get_omega_minute_ft`` via ``Cloud.rpc``: stessi argomenti e stessi
    ritorni di ``omega_db.ht_ft_transitions``/``minute_transitions`` ([] = vuota, None = errore).
    Differenza dichiarata: il ``Cloud`` ritenta i guasti di rete (RPC di lettura), oggi no."""

    def __init__(self, cloud: Cloud) -> None:
        self._cloud = cloud

    def ht_ft(self, league_id: Optional[int]) -> Optional[List[Dict[str, Any]]]:
        try:
            return _lista_o_vuota(self._cloud.rpc("get_omega_ht_ft", {"p_league_id": _lega(league_id)}))
        except Exception as ex:  # noqa: BLE001 - errore = None, mai in cache (come omega_db)
            logger.warning("[cache_cloud] get_omega_ht_ft KO (%s): %s", league_id, str(ex)[:120])
            return None

    def minuti(self, league_id: Optional[int], bucket: int, target: str) -> Optional[List[Dict[str, Any]]]:
        try:
            return _lista_o_vuota(self._cloud.rpc("get_omega_minute_ft", {
                "p_league_id": _lega(league_id), "p_bucket": int(bucket), "p_target": str(target)}))
        except Exception as ex:  # noqa: BLE001
            logger.warning("[cache_cloud] get_omega_minute_ft KO (%s,%s,%s): %s", league_id, bucket, target,
                           str(ex)[:120])
            return None

    def sentinella(self) -> Optional[str]:
        """Impronta dell'ultima ricostruzione delle DUE tabelle: la riga di ``omega_transitions_state``
        (``updated_at`` a ogni giro del pg_cron incrementale, anche quando cambia solo la tabella per
        minuto; ``published_at``), il ``built_at`` massimo di ``omega_ht_ft_transitions`` e l'ultimo
        ``omega_build_jobs`` (costruzione a mano v3/v4 della tabella per minuto). None = "non so" se una
        delle letture fallisce: ``ReplicaEmpirica.controlla_ricostruzione`` riprova al giro dopo e, dopo
        ``SENTINELLA_ERRORI_MAX`` errori di fila, rilegge comunque (mai ciechi per sempre)."""
        letture = (("omega_transitions_state", {"select": "updated_at,published_at", "id": 1}),
                   ("omega_ht_ft_transitions", {"select": "built_at", "order": "built_at.desc", "limit": 1}),
                   ("omega_build_jobs", {"select": "job,updated_at", "order": "updated_at.desc", "limit": 1}))
        pezzi = []
        for tabella, filtri in letture:
            try:
                righe = self._cloud.leggi(tabella, filtri)
            except Exception as ex:  # noqa: BLE001
                logger.warning("[cache_cloud] sentinella %s non leggibile: %s", tabella, str(ex)[:120])
                return None
            pezzi.append(json.dumps(righe[:1], sort_keys=True, default=str))
        return "|".join(pezzi)


# ---------------------------------------------------------------------------
# 2. Replica delle tabelle empiriche (prefetch per lega, rilettura dopo la sentinella)
# ---------------------------------------------------------------------------
Chiave = Tuple[Any, ...]   # ("ht_ft", lega) | ("minuti", lega, bucket, target)
Righe = List[Dict[str, Any]]
_FINE = object()           # sentinella di ``ferma`` nella coda (None e' una lega valida: il globale)
_LEGGI = object()          # ``controlla_ricostruzione`` senza valore: legge la sentinella da se'


@dataclass(frozen=True)
class _Notifica:
    """Valore della sentinella letto da fuori (``Sorveglianza``), consegnato al thread della replica
    nella stessa coda dei prefetch: la rilettura gira dove gira oggi, mai nel thread che sorveglia."""
    valore: Optional[str]


@dataclass(frozen=True)
class EsitoPrefetch:
    lette: int
    errori: int


class ReplicaEmpirica:
    """Memoria delle righe delle due RPC per chiave, ogni voce marcata con la GENERAZIONE della
    sentinella in cui e' stata letta. Le letture (``ht_ft_transitions``, ``minute_transitions``,
    ``ht_ft_rows``) NON vanno in rete se la chiave e' pronta. Una scrittura iniziata in una
    generazione e finita in un'altra si scarta (mai righe della notte vecchia dopo il cambio);
    la rilettura dopo la ricostruzione FONDE, non sostituisce (le leghe preparate nel frattempo
    restano).

    Con ``sentinella_esterna=True`` il thread NON legge la sentinella da se': gliela consegna una
    ``Sorveglianza`` (``notifica_sentinella``) ogni ``INTERVALLO_RAPIDO_S`` invece di ogni 300 s
    (decisione 10); il thread continua a fare i prefetch e a riaccodare le leghe incomplete."""

    def __init__(self, sorgente: SorgenteOmega, *, ripiego_sincrono: bool = True,
                 intervallo_sorveglianza_s: float = INTERVALLO_SORVEGLIANZA_S,
                 ritardo_riprefetch_s: float = RITARDO_RIPREFETCH_S,
                 orologio: Callable[[], float] = time.monotonic,
                 sentinella_esterna: bool = False) -> None:
        self._sorgente = sorgente
        self._ripiego = ripiego_sincrono
        self._esterna = bool(sentinella_esterna)
        self._intervallo = float(intervallo_sorveglianza_s)
        self._ritardo = float(ritardo_riprefetch_s)
        self._orologio = orologio
        self._lock = threading.Lock()
        self._righe: Dict[Chiave, Tuple[int, Righe]] = {}
        self._leghe: set = set()
        self._richieste: Dict[Optional[int], float] = {}
        self._gen = 0
        self._sentinella: Optional[str] = None
        self._errori_sentinella = 0
        self._coda: "queue.Queue[Any]" = queue.Queue()
        self._ferma = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._conti: Dict[str, int] = {"colpi": 0, "mancati": 0, "ripieghi": 0, "letture_rete": 0,
                                       "ricostruzioni": 0, "errori": 0, "scartate": 0, "riprefetch": 0,
                                       "riletture_forzate": 0}

    # --------------------------------------------- firme di omega_db / mike.db (ciclo di decisione)
    def ht_ft_transitions(self, league_id: Optional[int]) -> Optional[Righe]:
        lega = _lega(league_id)
        return self._servi(("ht_ft", lega), lambda: self._sorgente.ht_ft(lega), lega)

    def minute_transitions(self, league_id: Optional[int], bucket: int, target: str) -> Optional[Righe]:
        lega = _lega(league_id)
        chiave = ("minuti", lega, int(bucket), str(target))
        return self._servi(chiave, lambda: self._sorgente.minuti(lega, int(bucket), str(target)), lega)

    def ht_ft_rows(self, league_id: Optional[int]) -> Optional[Righe]:
        """Firma di ``mike.db.ht_ft_rows`` (che delega a ``omega_db.ht_ft_transitions``)."""
        return self.ht_ft_transitions(league_id)

    # --------------------------------------------- riempimento (fuori dal ciclo)
    def prefetch_lega(self, league_id: Optional[int], *, solo_mancanti: bool = False) -> EsitoPrefetch:
        """Legge HT->FT e TUTTI i bucket (FT 0..85, HT 0..40) della lega (o solo le chiavi che
        mancano nella generazione corrente). Gli errori non entrano in memoria."""
        lega = _lega(league_id)
        with self._lock:
            self._leghe.add(lega)
            gen = self._gen
            presenti = {k for k, (g, _) in self._righe.items() if g == gen} if solo_mancanti else set()
        lette = errori = 0
        for chiave, leggi in self._chiavi_di(lega):
            if chiave in presenti:
                continue
            righe = leggi()
            self._memorizza(chiave, righe, gen)
            lette += righe is not None
            errori += righe is None
        return EsitoPrefetch(lette, errori)

    def richiedi_prefetch(self, league_id: Optional[int], *, forza: bool = True) -> bool:
        """Accoda la lega al thread (non blocca). Con ``forza=False`` al piu' una richiesta ogni
        ``ritardo_riprefetch_s`` per lega. Ritorna True se accodata."""
        lega = _lega(league_id)
        adesso = self._orologio()
        with self._lock:
            if not forza and adesso - self._richieste.get(lega, -1e18) < self._ritardo:
                return False
            self._richieste[lega] = adesso
        self._coda.put(lega)
        return True

    def drena_coda(self) -> int:
        """Esegue SUBITO i prefetch in coda (le chiavi mancanti delle leghe richieste): lo usa il
        thread; senza thread lo chiama chi vuole un riempimento sincrono fuori dal ciclo."""
        fatte = 0
        while True:
            try:
                lega = self._coda.get_nowait()
            except queue.Empty:
                return fatte
            if lega is _FINE:
                self._coda.put(_FINE)
                return fatte
            if isinstance(lega, _Notifica):
                self.controlla_ricostruzione(sentinella=lega.valore)
                continue
            self.prefetch_lega(lega, solo_mancanti=True)
            fatte += 1

    def richiedi_incomplete(self) -> int:
        """Riaccoda (col ritardo minimo) le leghe note a cui manca qualche chiave."""
        with self._lock:
            per_lega: Dict[Optional[int], int] = {lega: 0 for lega in self._leghe}
            for chiave, (g, _) in self._righe.items():
                if g == self._gen and chiave[1] in per_lega:
                    per_lega[chiave[1]] += 1
        incomplete = [lega for lega, n in per_lega.items() if n < CHIAVI_PER_LEGA]
        accodate = sum(self.richiedi_prefetch(lega, forza=False) for lega in incomplete)
        with self._lock:
            self._conti["riprefetch"] += accodate
        return accodate

    def notifica_sentinella(self, valore: Optional[str]) -> None:
        """Consegna al thread della replica un valore della sentinella letto da fuori (None = lettura
        fallita, "non so"). Non blocca: la eventuale rilettura la fa il thread (o ``drena_coda``)."""
        self._coda.put(_Notifica(valore))

    def controlla_ricostruzione(self, sentinella: Any = _LEGGI) -> bool:
        """Legge la sentinella (o usa quella data da ``notifica_sentinella``, stessa forma di
        ``SorgenteOmega.sentinella``): se e' cambiata apre una generazione nuova, rilegge TUTTE le chiavi
        delle leghe note e le FONDE nella memoria; alla fine toglie le voci rimaste della
        generazione vecchia (rilettura fallita = errore = mai in cache). La prima lettura registra
        soltanto. Durante la rilettura si servono le voci vecchie (finestra dichiarata).

        Sentinella illeggibile = "non so" (mai "uguale"): si riprova al giro dopo; dopo
        ``SENTINELLA_ERRORI_MAX`` errori DI FILA si rilegge comunque tutto (puo' esserci stata una
        ricostruzione che non vediamo) e la sentinella diventa ignota, cosi' la prima lettura riuscita
        rilegge ancora: la replica non resta mai cieca a una ricostruzione."""
        nuova = self._sorgente.sentinella() if sentinella is _LEGGI else sentinella
        with self._lock:
            if nuova is None:
                self._errori_sentinella += 1
                if self._errori_sentinella < SENTINELLA_ERRORI_MAX:
                    return False
                self._errori_sentinella = 0
                self._sentinella = _SENTINELLA_IGNOTA
                self._conti["riletture_forzate"] += 1
                logger.warning("[cache_cloud] sentinella illeggibile %d volte di fila: rilettura forzata",
                               SENTINELLA_ERRORI_MAX)
            else:
                self._errori_sentinella = 0
                vecchia = self._sentinella
                if vecchia == nuova:
                    return False
                self._sentinella = nuova
                if vecchia is None:
                    return False
            self._gen += 1
            gen = self._gen
            leghe = sorted(self._leghe, key=lambda x: (x is None, x))
        lette = 0
        for lega in leghe:
            for chiave, leggi in self._chiavi_di(lega):
                righe = leggi()
                lette += self._memorizza(chiave, righe, gen)
        with self._lock:
            if self._gen == gen:
                for chiave in [k for k, (g, _) in self._righe.items() if g < gen]:
                    del self._righe[chiave]
            self._conti["ricostruzioni"] += 1
        logger.info("[cache_cloud] ricostruzione del pg_cron: %d chiavi rilette (generazione %d)", lette, gen)
        return True

    # --------------------------------------------- thread
    def avvia(self) -> None:
        """Thread di prefetch (coda) e sorveglianza della sentinella (ogni ``intervallo``)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._ferma.clear()
        self._thread = threading.Thread(target=self._giro, name="cache_cloud_replica", daemon=True)
        self._thread.start()

    def ferma(self, attesa_s: float = 5.0) -> None:
        self._ferma.set()
        self._coda.put(_FINE)
        if self._thread is not None:
            self._thread.join(attesa_s)
            if self._thread.is_alive():
                logger.error("[cache_cloud] il thread della replica non si e' fermato in %.1f s", attesa_s)
        self._thread = None

    def vivo(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def statistiche(self) -> Mapping[str, Any]:
        with self._lock:
            return {**self._conti, "chiavi": len(self._righe), "leghe": len(self._leghe),
                    "generazione": self._gen, "sentinella": self._sentinella}

    # --------------------------------------------- interni
    def _chiavi_di(self, lega: Optional[int]) -> List[Tuple[Chiave, Callable[[], Optional[Righe]]]]:
        s = self._sorgente
        out: List[Tuple[Chiave, Callable[[], Optional[Righe]]]] = [(("ht_ft", lega), lambda: s.ht_ft(lega))]
        for target, bucket_di in (("ft", BUCKET_FT), ("ht", BUCKET_HT)):
            for b in bucket_di:
                out.append((("minuti", lega, b, target), lambda b=b, t=target: s.minuti(lega, b, t)))
        return out

    def _memorizza(self, chiave: Chiave, righe: Optional[Righe], gen: int) -> bool:
        """Salva le righe lette nella generazione ``gen`` SOLO se e' ancora la corrente."""
        with self._lock:
            self._conti["letture_rete"] += 1
            if righe is None:
                self._conti["errori"] += 1
                return False
            if gen != self._gen:
                self._conti["scartate"] += 1
                return False
            self._righe[chiave] = (gen, righe)
            return True

    def _servi(self, chiave: Chiave, leggi: Callable[[], Optional[Righe]], lega: Optional[int]) -> Optional[Righe]:
        with self._lock:
            voce = self._righe.get(chiave)
            if voce is not None:
                self._conti["colpi"] += 1
                return _copia(voce[1])
            self._conti["mancati"] += 1
            gen = self._gen
        self.richiedi_prefetch(lega, forza=False)      # lega nuova o chiave mancante: di nuovo
        if not self._ripiego:
            return None                               # come un errore di oggi: il bot riprova
        righe = leggi()
        with self._lock:
            self._conti["ripieghi"] += 1
        self._memorizza(chiave, righe, gen)
        return _copia(righe)

    def _giro(self) -> None:
        prossima = 0.0
        while not self._ferma.is_set():
            adesso = time.monotonic()
            if adesso >= prossima:
                try:
                    if not self._esterna:
                        self.controlla_ricostruzione()
                    self.richiedi_incomplete()
                except Exception:  # noqa: BLE001 - il thread non muore: si logga e si riprova
                    logger.exception("[cache_cloud] sorveglianza della ricostruzione fallita")
                prossima = adesso + self._intervallo
            try:
                lega = self._coda.get(timeout=max(0.05, min(1.0, prossima - time.monotonic())))
            except queue.Empty:
                continue
            if lega is _FINE or self._ferma.is_set():
                break
            try:
                if isinstance(lega, _Notifica):
                    self.controlla_ricostruzione(sentinella=lega.valore)
                else:
                    self.prefetch_lega(lega, solo_mancanti=True)
            except Exception:  # noqa: BLE001
                logger.exception("[cache_cloud] prefetch o rilettura fallita (%s)", lega)


# ---------------------------------------------------------------------------
# 3. Dossier pre-match di Mike
# ---------------------------------------------------------------------------
def lambdas_da_riga(riga: Mapping[str, Any], *, con_squadre: bool = True) -> Optional[tuple]:
    """Lambda pre-match dalla riga di ``fixture_predictions``: catena ``tactical_engine_json`` ->
    ``db_json_analisi.inputs`` (JSON in stringa ammesso). Riscrittura di
    ``Betfair/stream/db.get_fixture_prematch_lambdas`` sulla riga gia' letta: la parita' e' provata
    da ``test_g2_cache_cloud.py`` su una griglia di righe (stessi ritorni, compresa la tupla con
    lambda None quando la riga c'e' e le lambda no)."""
    league_id = riga.get("league_id")
    for chiave, sotto in (("tactical_engine_json", None), ("db_json_analisi", "inputs")):
        nodo = riga.get(chiave)
        if isinstance(nodo, str):
            try:
                nodo = json.loads(nodo)
            except (ValueError, TypeError):
                nodo = None
        if sotto and isinstance(nodo, dict):
            nodo = nodo.get(sotto)
        if isinstance(nodo, dict):
            lh, la = nodo.get("lambda_home"), nodo.get("lambda_away")
            try:
                if lh is not None and la is not None and float(lh) > 0 and float(la) > 0:
                    if con_squadre:
                        return (float(lh), float(la), league_id, riga.get("home_team_id"), riga.get("away_team_id"))
                    return (float(lh), float(la), league_id)
            except (TypeError, ValueError):
                pass
    if con_squadre:
        return (None, None, league_id, riga.get("home_team_id"), riga.get("away_team_id"))
    return None


_ASSENTE = object()   # nessuna voce valida in memoria: si va al ripiego


class DossierPrematch:
    """Le letture del dossier di Mike preparate PRIMA dell'aggancio, con le firme di ``mike.db``
    usate da ``mike/dossier.build_prematch``. In memoria SOLO i positivi (evento con fixture, riga
    con gol attesi) e per ``scadenza_s``: un negativo (fixture non trovata, previsione assente o
    senza lambda) NON si memorizza, cosi' la fixture che arriva dopo accende il modello al ritento
    di Mike (CERT 12/09) esattamente come oggi. Chiave non pronta -> ``ripiego`` (il modulo
    ``mike.db`` di oggi, sincrono) o None se non c'e'.

    Decisione 10 (10/10): gli eventi SEGUITI (``segui``, e ogni evento passato a ``precarica``)
    sono sorvegliati da una ``Sorveglianza``, che a ogni giro porta l'impronta che il cloud ha di
    ognuno (``applica_impronte``). Impronta cambiata = il cloud ha ricalcolato: si tolgono le voci,
    si rilegge SOLO quell'evento e lo si mette fra i cambiati (``prendi_cambiati``: all'aggancio Mike
    riprova SUBITO il dossier cieco, senza aspettare i 300 s). Impronta uguale e garantita dalla
    versione del trigger (modo ``rpc``) = la voce e' confermata fresca adesso (``rinnova``). Ogni
    chiave ha una generazione: una lettura iniziata prima di un'invalidazione non rimette in memoria
    il dato vecchio."""

    def __init__(self, cloud: Cloud, *, replica: Optional[ReplicaEmpirica] = None, ripiego: Any = None,
                 orologio: Callable[[], float] = time.time, scadenza_s: float = SCADENZA_DOSSIER_S,
                 scadenza_massima_s: float = SCADENZA_MASSIMA_S) -> None:
        self._cloud = cloud
        self._replica = replica
        self._ripiego = ripiego
        self._orologio = orologio
        self._scadenza = float(scadenza_s)
        self._lock = threading.Lock()
        self._ponte: Dict[str, Tuple[float, int]] = {}
        self._fixture: Dict[int, Tuple[float, Mapping[str, Any]]] = {}
        self._conti: Dict[str, int] = {"colpi": 0, "mancati": 0, "ripieghi": 0, "letture_rete": 0, "errori": 0,
                                       "cambi": 0, "rinnovi": 0, "scartate": 0, "riletture_fallite": 0}
        # decisione 10: eventi sorvegliati, ultima impronta vista, generazioni, cambiati da consegnare,
        # istante della LETTURA di ogni voce (("e", evento) / ("f", fixture)): il rinnovo sposta solo la validita'
        self._massima = max(float(scadenza_massima_s), self._scadenza)
        self._lette: Dict[Tuple[str, Any], float] = {}
        self._seguiti: set = set()
        self._impronte: Dict[str, str] = {}
        self._gen: Dict[Tuple[str, Any], int] = {}
        self._cambiati: set = set()

    # --------------------------------------------- preparazione (fuori dal ciclo)
    def precarica(self, event_ids: Iterable[str]) -> int:
        """Ponte evento->fixture (``live_follow`` poi ``omega_events``) e righe di
        ``fixture_predictions`` per gli eventi dati, a blocchi. Ritorna gli eventi con fixture.
        Gli eventi diventano SEGUITI dalla sorveglianza. In memoria va SOLO il dossier positivo: il ponte
        di un evento entra solo se la sua fixture ha la riga con i gol attesi (un dossier cieco va sempre
        al ripiego, cioe' alla lettura di oggi, mai a un ponte tenuto in memoria)."""
        eventi = sorted({str(e) for e in event_ids})
        with self._lock:
            self._seguiti.update(eventi)
            gen_eventi = {ev: self._gen.get(("e", ev), 0) for ev in eventi}
        ponte = self._leggi_ponte(eventi)
        adesso = self._orologio()
        self._precarica_fixture(sorted(set(ponte.values())))
        with self._lock:
            for ev, fid in ponte.items():
                if self._gen.get(("e", ev), 0) != gen_eventi[ev]:
                    self._conti["scartate"] += 1       # invalidato mentre si leggeva: dato forse vecchio
                    continue
                riga = self._fixture.get(fid)
                if riga is None or adesso - riga[0] >= self._scadenza:
                    continue                           # dossier cieco: nessun ponte in memoria
                self._ponte[ev] = (adesso, fid)
                self._lette[("e", ev)] = adesso
        self.pota()
        return len(ponte)

    def segui(self, event_ids: Iterable[str]) -> None:
        """Gli eventi da sorvegliare SOSTITUISCONO i precedenti (all'aggancio: i ``tracked`` di Mike a
        ogni giro). Le impronte degli eventi non piu' seguiti si dimenticano al giro dopo."""
        with self._lock:
            self._seguiti = {str(e) for e in event_ids}

    def seguiti(self) -> Tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._seguiti))

    def adesso(self) -> float:
        """L'orologio del dossier (quello delle scadenze), per chi sorveglia."""
        return self._orologio()

    def prendi_cambiati(self, dossier_dei_bot: Optional[Mapping[str, Mapping[str, Any]]] = None, *,
                        anche_pieni: bool = False) -> Tuple[str, ...]:
        """Gli eventi il cui dossier e' cambiato nel cloud dall'ultima chiamata (e sono gia' riletti): li
        consuma. DI SERIE solo i CIECHI: ``dossier_dei_bot`` (i ``tracked`` di Mike, evento -> voce con
        ``"dossier"``) e' obbligatorio e si restituiscono solo gli eventi che vi compaiono col dossier
        ancora senza gol attesi (``dossier_cieco``). Un dossier PIENO non si ricostruisce a partita
        armata (decisione D10-b dell'utente): per averli tutti serve ``anche_pieni=True``, esplicito."""
        if dossier_dei_bot is None and not anche_pieni:
            raise ValueError("prendi_cambiati: servono i dossier del bot (solo i ciechi) o anche_pieni=True")
        with self._lock:
            tutti, self._cambiati = tuple(sorted(self._cambiati)), set()
        if anche_pieni:
            return tutti
        assert dossier_dei_bot is not None
        return tuple(ev for ev in tutti if ev in dossier_dei_bot and dossier_cieco(dossier_dei_bot[ev]))

    def annulla_rinnovi(self) -> int:
        """Dopo un giro fallito: ogni voce torna alla scadenza calcolata dalla sua LETTURA, non
        dall'ultima conferma (mai piu' tardi della lettura di oggi se la sorveglianza tace)."""
        tornate = 0
        with self._lock:
            for prefisso, memoria in (("e", self._ponte), ("f", self._fixture)):
                for chiave, (t, valore) in list(memoria.items()):
                    letta = self._lette.get((prefisso, chiave), t)
                    if letta < t:
                        memoria[chiave] = (letta, valore)
                        tornate += 1
        return tornate

    def applica_impronte(self, impronte: Mapping[str, str], *, rinnova: bool, letto_alle: float) -> Tuple[str, ...]:
        """Un giro della sorveglianza: ``impronte`` = evento -> impronta del cloud letta a partire da
        ``letto_alle`` (orologio del dossier). Evento seguito con impronta diversa dall'ultima (o mai
        vista) -> voci tolte, evento riletto; se la rilettura riesce l'impronta si registra e l'evento
        va fra i cambiati, altrimenti si riprova al giro dopo (intanto: ripiego, cioe' la lettura di
        oggi). Impronta uguale con ``rinnova`` -> voci confermate fresche a ``letto_alle``. Ritorna i
        cambiati registrati in questo giro."""
        with self._lock:
            seguiti = set(self._seguiti)
            for ev in [e for e in self._impronte if e not in seguiti]:
                del self._impronte[ev]
            nuove = {str(ev): str(imp) for ev, imp in impronte.items() if str(ev) in seguiti}
            cambiati = sorted(ev for ev, imp in nuove.items() if self._impronte.get(ev) != imp)
            da_rileggere: List[str] = []
            if rinnova:
                da_rileggere = sorted(ev for ev in nuove.keys() - set(cambiati) if self._rinnova(ev, letto_alle))
            for ev in cambiati:
                self._invalida(ev, _fixture_di_impronta(nuove[ev]))
            self._pota_generazioni(seguiti)
            errori_prima = self._conti["errori"]
        if da_rileggere:
            self.precarica(da_rileggere)                # tetto di SCADENZA_MASSIMA_S: si rilegge comunque
        if not cambiati:
            return ()
        self.precarica(cambiati)
        with self._lock:
            if self._conti["errori"] != errori_prima:
                self._conti["riletture_fallite"] += 1
                return ()
            for ev in cambiati:
                self._impronte[ev] = nuove[ev]
            self._cambiati.update(cambiati)
            self._conti["cambi"] += len(cambiati)
        return tuple(cambiati)

    def pota(self) -> int:
        """Toglie le voci scadute (la memoria non cresce oltre la finestra di ``scadenza_s``).
        La chiama ``precarica``; ritorna quante ne ha tolte."""
        adesso = self._orologio()
        tolte = 0
        with self._lock:
            for memoria in (self._ponte, self._fixture):
                for chiave in [k for k, (t, _) in memoria.items() if adesso - t >= self._scadenza]:
                    del memoria[chiave]
                    tolte += 1
            for chiave in [k for k in self._lette if k[1] not in (self._ponte if k[0] == "e" else self._fixture)]:
                del self._lette[chiave]
        return tolte

    # --------------------------------------------- firme di mike.db (ciclo)
    def fixture_id_for_event(self, event_id: str) -> Optional[int]:
        voce = self._fresca(self._ponte, str(event_id))
        if voce is not _ASSENTE:
            return voce  # type: ignore[return-value]
        return self._da_ripiego("fixture_id_for_event", str(event_id))

    def fixture_lambdas(self, fixture_id: Optional[int]) -> Optional[tuple]:
        if fixture_id is None:
            return None
        riga = self._fresca(self._fixture, int(fixture_id))
        if riga is _ASSENTE:
            return self._da_ripiego("fixture_lambdas", fixture_id)
        return lambdas_da_riga(riga)

    def fixture_analysis(self, fixture_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if fixture_id is None:
            return None
        riga = self._fresca(self._fixture, int(fixture_id))
        if riga is _ASSENTE:
            return self._da_ripiego("fixture_analysis", fixture_id)
        return riga.get("db_json_analisi")

    def ht_ft_rows(self, league_id: Optional[int]) -> Optional[Righe]:
        if self._replica is not None:
            return self._replica.ht_ft_rows(league_id)
        return self._da_ripiego("ht_ft_rows", league_id)

    def statistiche(self) -> Mapping[str, int]:
        with self._lock:
            return {**self._conti, "eventi": len(self._ponte), "fixture": len(self._fixture),
                    "seguiti": len(self._seguiti)}

    # --------------------------------------------- interni
    def _rinnova(self, ev: str, letto_alle: float) -> bool:
        """(sotto lock) La voce dell'evento e della sua fixture valgono da ``letto_alle``, mai indietro e
        mai oltre ``SCADENZA_MASSIMA_S`` dalla LETTURA. True = tetto raggiunto: la voce va riletta."""
        voce = self._ponte.get(ev)
        if voce is None:
            return False
        tetto = False
        for prefisso, memoria, chiave in (("e", self._ponte, ev), ("f", self._fixture, voce[1])):
            attuale = memoria.get(chiave)
            if attuale is None:
                continue
            limite = self._lette.get((prefisso, chiave), attuale[0]) + self._massima - self._scadenza
            tetto = tetto or letto_alle > limite
            nuova = min(letto_alle, limite)
            if nuova > attuale[0]:
                memoria[chiave] = (nuova, attuale[1])
                self._conti["rinnovi"] += int(prefisso == "e")
        return tetto

    def _invalida(self, ev: str, fixture_nuova: Optional[int]) -> None:
        """(sotto lock) Toglie le voci dell'evento, della fixture che aveva e di quella nuova, e ne
        alza le generazioni: le letture gia' in volo non le rimettono."""
        voce = self._ponte.pop(ev, None)
        fixture = {f for f in (voce[1] if voce else None, fixture_nuova) if f is not None}
        for chiave in [("e", ev)] + [("f", f) for f in fixture]:
            self._gen[chiave] = self._gen.get(chiave, 0) + 1
            self._lette.pop(chiave, None)
        for f in fixture:
            self._fixture.pop(f, None)

    def _pota_generazioni(self, seguiti: set) -> None:
        """(sotto lock) Le generazioni servono solo alle letture in volo: si tengono quelle degli
        eventi seguiti e delle fixture in memoria."""
        if len(self._gen) <= 4 * max(len(seguiti), 64):
            return
        tenere = {("e", ev) for ev in seguiti} | {("f", f) for f in self._fixture} | \
                 {("f", fid) for _, fid in self._ponte.values()}
        for chiave in [k for k in self._gen if k not in tenere]:
            del self._gen[chiave]

    def _fresca(self, memoria: Dict[Any, Tuple[float, Any]], chiave: Any) -> Any:
        with self._lock:
            voce = memoria.get(chiave)
            if voce is None or self._orologio() - voce[0] >= self._scadenza:
                self._conti["mancati"] += 1
                return _ASSENTE
            self._conti["colpi"] += 1
            return voce[1]

    def _da_ripiego(self, funzione: str, argomento: Any) -> Any:
        if self._ripiego is None:
            return None
        with self._lock:
            self._conti["ripieghi"] += 1
        return getattr(self._ripiego, funzione)(argomento)

    def _leggi_blocchi(self, tabella: str, colonne: str, colonna: str, valori: Sequence[Any]) -> Tuple[Righe, bool]:
        """Righe di ``tabella`` con ``colonna`` in ``valori``, a blocchi. (righe, tutto_letto)."""
        righe: Righe = []
        ok = True
        for i in range(0, len(valori), BLOCCO_IN):
            try:
                righe.extend(self._cloud.leggi(tabella, {"select": colonne, colonna: list(valori[i:i + BLOCCO_IN])}))
                with self._lock:
                    self._conti["letture_rete"] += 1
            except Exception as ex:  # noqa: BLE001 - il blocco non entra in memoria: ripiego al ciclo
                ok = False
                with self._lock:
                    self._conti["errori"] += 1
                logger.warning("[cache_cloud] %s non letta (%d valori): %s", tabella, len(valori[i:i + BLOCCO_IN]),
                               str(ex)[:120])
        return righe, ok

    def _leggi_ponte(self, eventi: List[str]) -> Dict[str, int]:
        """Come ``mike.db.fixture_id_for_event``: la prima tabella con ``fixture_id`` intero vince.
        Solo i POSITIVI, e solo se le tabelle consultate prima della risposta sono state lette senza
        errori (altrimenti la risposta di oggi potrebbe essere un'altra)."""
        out: Dict[str, int] = {}
        da_cercare = list(eventi)
        for tabella in ("live_follow", "omega_events"):
            if not da_cercare:
                break
            righe, ok = self._leggi_blocchi(tabella, "event_id,fixture_id", "event_id", da_cercare)
            if not ok:
                return out
            per_evento = {str(r.get("event_id")): r.get("fixture_id") for r in righe}
            restano = []
            for ev in da_cercare:
                fid = per_evento.get(ev)
                try:
                    if fid is not None:
                        out[ev] = int(fid)
                        continue
                except (TypeError, ValueError):
                    pass
                restano.append(ev)
            da_cercare = restano
        return out

    def _precarica_fixture(self, fixture_ids: List[int]) -> None:
        if not fixture_ids:
            return
        with self._lock:
            gen_fixture = {f: self._gen.get(("f", f), 0) for f in fixture_ids}
        righe, _ok = self._leggi_blocchi("fixture_predictions", COLONNE_PREMATCH, "fixture_id", fixture_ids)
        adesso = self._orologio()
        with self._lock:
            for r in righe:
                fid = r.get("fixture_id")
                if fid is not None and int(fid) in fixture_ids and lambdas_da_riga(r)[0] is not None:
                    if self._gen.get(("f", int(fid)), 0) != gen_fixture[int(fid)]:
                        self._conti["scartate"] += 1   # invalidata mentre si leggeva
                        continue
                    self._fixture[int(fid)] = (adesso, r)     # solo la riga CON i gol attesi
                    self._lette[("f", int(fid))] = adesso


def dossier_cieco(voce: Mapping[str, Any]) -> bool:
    """Lo stesso criterio di ``mike/service.dossier_da_ritentare`` (provato nei test): il dossier della
    voce di un bot e' PIENO se ha ``lambda_home`` E ``lambda_away``; altrimenti (assente, non dict, senza
    gol attesi) e' cieco."""
    d = voce.get("dossier") if isinstance(voce, Mapping) else None
    if not isinstance(d, Mapping):
        return True
    return not (d.get("lambda_home") and d.get("lambda_away"))


def _intero(valore: Any) -> Optional[int]:
    """``int(valore)`` o None (come la conversione di ``mike.db.fixture_id_for_event``)."""
    try:
        return int(valore) if valore is not None else None
    except (TypeError, ValueError):
        return None


def _fixture_di_impronta(impronta: str) -> Optional[int]:
    """La fixture risolta, primo elemento di ogni impronta del dossier (vedi ``SentinellaCloud``)."""
    try:
        dati = json.loads(impronta)
    except (TypeError, ValueError):
        return None
    return _intero(dati[0]) if isinstance(dati, list) and dati else None


# ---------------------------------------------------------------------------
# 4. Sorveglianza dei ricalcoli del cloud (decisione 10 dell'utente, 10/10/2026)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Istantanea:
    """Cio' che il cloud dice in UN giro. ``omega``: impronta della sentinella di Omega (stessa forma
    di ``SorgenteOmega.sentinella``; None = non chiesta o non letta). ``impronte``: evento ->
    impronta del suo dossier (None = lettura fallita: nessuna conclusione). ``modo``: "rpc" (la
    migrazione c'e': UNA chiamata, versioni garantite dal trigger) o "letture" (REST di oggi)."""

    omega: Optional[str]
    impronte: Optional[Mapping[str, str]]
    modo: str


class SentinellaCloud:
    """La lettura leggera di un giro. Con la migrazione ``nucleo_sentinella_cloud_2026-10-10.sql``:
    UNA RPC (fino a ``BLOCCO_RPC`` eventi) che restituisce l'impronta di Omega e, per evento,
    ``[fixture, riga presente, nucleo_versione]``. Senza (PGRST202/42883): le letture REST di oggi
    (le 3 della sentinella di Omega, ``live_follow`` e ``omega_events`` a blocchi di 50, poi
    ``fixture_id,updated_at`` di ``fixture_predictions``) e la RPC si riprova ogni ``riprova_rpc_s``.
    Ogni errore diverso da "funzione assente" = istantanea senza conclusioni, mai un cambio di modo."""

    def __init__(self, cloud: Cloud, *, orologio: Callable[[], float] = time.monotonic,
                 riprova_rpc_s: float = RIPROVA_RPC_S) -> None:
        self._cloud = cloud
        self._omega = SorgenteOmega(cloud)
        self._orologio = orologio
        self._riprova = float(riprova_rpc_s)
        self._lock = threading.Lock()
        self._rpc_assente_da: Optional[float] = None
        self._conti: Dict[str, int] = {"rpc": 0, "letture": 0, "errori": 0, "rpc_assente": 0}

    def leggi(self, *, omega: bool, eventi: Iterable[str]) -> Istantanea:
        eventi_ord = sorted({str(e) for e in eventi})
        if self._prova_rpc():
            esito = self._leggi_rpc(omega, eventi_ord)
            if esito is not None:
                return esito
        return self._leggi_rest(omega, eventi_ord)

    def modo(self) -> str:
        with self._lock:
            return "letture" if self._rpc_assente_da is not None else "rpc"

    def statistiche(self) -> Mapping[str, Any]:
        with self._lock:
            return {**self._conti, "modo": "letture" if self._rpc_assente_da is not None else "rpc"}

    # --------------------------------------------- interni
    def _prova_rpc(self) -> bool:
        with self._lock:
            return self._rpc_assente_da is None or self._orologio() - self._rpc_assente_da >= self._riprova

    def _conta(self, voce: str) -> None:
        with self._lock:
            self._conti[voce] += 1

    def _leggi_rpc(self, omega: bool, eventi: List[str]) -> Optional[Istantanea]:
        """None = la funzione non c'e' (si passa alle letture); altrimenti l'istantanea."""
        impronte: Dict[str, str] = {}
        impronta_omega: Optional[str] = None
        blocchi = [eventi[i:i + BLOCCO_RPC] for i in range(0, len(eventi), BLOCCO_RPC)] or [[]]
        for n, blocco in enumerate(blocchi):
            con_omega = omega and n == 0
            try:
                self._conta("rpc")
                dati = self._cloud.rpc("nucleo_sentinella_cloud", {"p_event_ids": blocco, "p_omega": con_omega})
            except Exception as ex:  # noqa: BLE001 - si distingue "assente" da ogni altro errore
                if str(getattr(ex, "code", "") or "") in CODICI_RPC_ASSENTE:
                    self._segna_assente()
                    return None
                self._conta("errori")
                logger.warning("[cache_cloud] nucleo_sentinella_cloud KO: %s", str(ex)[:160])
                return Istantanea(None, None, "rpc")
            letto = _dati_sentinella(dati, blocco, con_omega)
            if letto is None:
                self._conta("errori")
                logger.warning("[cache_cloud] nucleo_sentinella_cloud: risposta di forma inattesa")
                return Istantanea(None, None, "rpc")
            if con_omega:
                impronta_omega = letto[0]
            impronte.update(letto[1])
        with self._lock:
            if self._rpc_assente_da is not None:
                logger.info("[cache_cloud] nucleo_sentinella_cloud di nuovo presente: una chiamata per giro")
            self._rpc_assente_da = None
        return Istantanea(impronta_omega, impronte, "rpc")

    def _segna_assente(self) -> None:
        with self._lock:
            prima = self._rpc_assente_da is None
            self._rpc_assente_da = self._orologio()
            self._conti["rpc_assente"] += 1
        if prima:
            logger.warning("[cache_cloud] nucleo_sentinella_cloud assente (migrazione non applicata): "
                           "letture REST ogni %.0f s, la RPC si riprova ogni %.0f s",
                           INTERVALLO_LETTURE_S, self._riprova)

    def _leggi_rest(self, omega: bool, eventi: List[str]) -> Istantanea:
        impronta_omega = self._omega.sentinella() if omega else None
        impronte = self._impronte_rest(eventi) if eventi else {}
        if impronte is None:
            self._conta("errori")
        return Istantanea(impronta_omega, impronte, "letture")

    def _impronte_rest(self, eventi: List[str]) -> Optional[Dict[str, str]]:
        """Impronta per evento senza la RPC: [fixture risolta, riga presente, updated_at della riga,
        fixture grezza di live_follow, di omega_events]. Una lettura fallita = None."""
        grezzi: Dict[str, Dict[str, Any]] = {"live_follow": {}, "omega_events": {}}
        for tabella in grezzi:
            for i in range(0, len(eventi), BLOCCO_IN):
                righe = self._leggi_o_none(tabella, {"select": "event_id,fixture_id",
                                                     "event_id": eventi[i:i + BLOCCO_IN]})
                if righe is None:
                    return None
                grezzi[tabella].update({str(r.get("event_id")): r.get("fixture_id") for r in righe})
        risolte = {ev: next((f for f in (_intero(grezzi["live_follow"].get(ev)),
                                         _intero(grezzi["omega_events"].get(ev))) if f is not None), None)
                   for ev in eventi}
        fixture = sorted({f for f in risolte.values() if f is not None})
        versioni: Dict[Optional[int], Any] = {}
        for i in range(0, len(fixture), BLOCCO_IN):
            righe = self._leggi_o_none("fixture_predictions", {"select": "fixture_id,updated_at",
                                                               "fixture_id": fixture[i:i + BLOCCO_IN]})
            if righe is None:
                return None
            versioni.update({_intero(r.get("fixture_id")): r.get("updated_at") for r in righe})
        return {ev: json.dumps([fid, fid in versioni, versioni.get(fid), grezzi["live_follow"].get(ev),
                                grezzi["omega_events"].get(ev)], default=str)
                for ev, fid in risolte.items()}

    def _leggi_o_none(self, tabella: str, filtri: Mapping[str, Any]) -> Optional[Sequence[Mapping[str, Any]]]:
        try:
            self._conta("letture")
            return self._cloud.leggi(tabella, filtri)
        except Exception as ex:  # noqa: BLE001 - nessuna conclusione dal giro: si riprova al prossimo
            logger.warning("[cache_cloud] sentinella REST: %s non letta: %s", tabella, str(ex)[:120])
            return None


def _dati_sentinella(dati: Any, eventi: Sequence[str],
                     con_omega: bool) -> Optional[Tuple[Optional[str], Dict[str, str]]]:
    """Risposta della RPC -> (impronta di Omega, impronte degli eventi). L'impronta di Omega ha la
    STESSA forma di ``SorgenteOmega.sentinella`` (le tre letture, la prima riga di ognuna): cambiare
    modo non simula una ricostruzione. Ogni evento chiesto deve esserci; forma diversa = None."""
    if not isinstance(dati, dict) or not isinstance(dati.get("eventi"), list):
        return None
    omega: Optional[str] = None
    if con_omega:
        parti = dati.get("omega")
        if not isinstance(parti, list) or len(parti) != 3 or not all(isinstance(x, list) for x in parti):
            return None
        omega = "|".join(json.dumps(x[:1], sort_keys=True, default=str) for x in parti)
    impronte: Dict[str, str] = {}
    for riga in dati["eventi"]:
        if not isinstance(riga, list) or len(riga) != 4:
            return None
        impronte[str(riga[0])] = json.dumps([_intero(riga[1]), bool(riga[2]), riga[3]], default=str)
    if set(impronte) != set(eventi):
        return None
    return omega, impronte


@dataclass(frozen=True)
class EsitoGiro:
    modo: str                      # "rpc" | "letture"
    omega_notificata: bool         # valore della sentinella consegnato alla replica
    cambiati: Tuple[str, ...]      # eventi del dossier cambiati nel cloud e gia' riletti
    errore: bool                   # qualcosa non si e' potuto leggere (nessuna conclusione su quello)


class Sorveglianza:
    """Il giro della decisione 10: ogni ``intervallo_s`` (5 s con la RPC, ``intervallo_letture_s``
    = 15 s senza) UNA ``SentinellaCloud.leggi`` per la replica di Omega e il dossier di Mike dello
    stesso processo. Omega: il valore va al thread della replica (``notifica_sentinella``), che
    rilegge come oggi; uguale al precedente = niente; un errore si consegna al piu' ogni
    ``INTERVALLO_SORVEGLIANZA_S`` (cosi' "3 errori di fila" restano ~15 minuti come oggi e un
    singhiozzo del cloud non provoca una rilettura forzata di tutte le leghe). Dossier:
    ``DossierPrematch.applica_impronte`` (rilegge SOLO gli eventi cambiati); un giro fallito riporta le
    voci alla scadenza della loro lettura (``annulla_rinnovi``). Dopo giri falliti di fila l'attesa sale
    a 15, 30, poi 60 s (``BACKOFF_ERRORI_S``) e torna alla cadenza al primo giro riuscito: il ripiego
    verso il dato resta quello di oggi. ``al_cambio`` (opzionale) riceve TUTTI i cambiati, anche i
    dossier pieni: per Mike si usa ``DossierPrematch.prendi_cambiati(tracked)``, che da' solo i ciechi."""

    def __init__(self, sentinella: SentinellaCloud, *, replica: Optional[ReplicaEmpirica] = None,
                 dossier: Optional[DossierPrematch] = None, intervallo_s: float = INTERVALLO_RAPIDO_S,
                 intervallo_letture_s: float = INTERVALLO_LETTURE_S,
                 al_cambio: Optional[Callable[[Tuple[str, ...]], Any]] = None,
                 orologio: Callable[[], float] = time.monotonic) -> None:
        if replica is None and dossier is None:
            raise ValueError("Sorveglianza senza replica ne' dossier: niente da sorvegliare")
        self._sentinella = sentinella
        self._replica = replica
        self._dossier = dossier
        self._intervallo = float(intervallo_s)
        self._intervallo_letture = float(intervallo_letture_s)
        self._al_cambio = al_cambio
        self._orologio = orologio
        self._lock = threading.Lock()
        self._ultima_omega: Any = _LEGGI          # nessun valore ancora consegnato
        self._ultimo_errore_omega = -math.inf
        self._modo = "rpc"
        self._errori_di_fila = 0
        self._ferma = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._conti: Dict[str, int] = {"giri": 0, "errori": 0, "notifiche_omega": 0, "cambiati": 0}

    def giro(self) -> EsitoGiro:
        """UN giro, sincrono (il thread lo chiama ogni ``attesa()``; i test lo chiamano a mano)."""
        eventi = self._dossier.seguiti() if self._dossier is not None else ()
        letto_alle = self._dossier.adesso() if self._dossier is not None else 0.0
        ist = self._sentinella.leggi(omega=self._replica is not None, eventi=eventi)
        notificata = self._consegna_omega(ist.omega) if self._replica is not None else False
        cambiati: Tuple[str, ...] = ()
        if self._dossier is not None and ist.impronte is not None:
            cambiati = self._dossier.applica_impronte(ist.impronte, rinnova=ist.modo == "rpc",
                                                      letto_alle=letto_alle)
        if self._dossier is not None and ist.impronte is None:
            self._dossier.annulla_rinnovi()
        errore = ((self._dossier is not None and ist.impronte is None)
                  or (self._replica is not None and ist.omega is None))
        with self._lock:
            self._errori_di_fila = self._errori_di_fila + 1 if errore else 0
            self._modo = ist.modo
            self._conti["giri"] += 1
            self._conti["errori"] += int(errore)
            self._conti["notifiche_omega"] += int(notificata)
            self._conti["cambiati"] += len(cambiati)
        if cambiati and self._al_cambio is not None:
            try:
                self._al_cambio(cambiati)
            except Exception:  # noqa: BLE001 - chi ascolta non ferma la sorveglianza
                logger.exception("[cache_cloud] al_cambio fallito per %s", cambiati[:5])
        return EsitoGiro(ist.modo, notificata, cambiati, errore)

    def attesa(self) -> float:
        with self._lock:
            base = self._intervallo if self._modo == "rpc" else self._intervallo_letture
            if self._errori_di_fila == 0:
                return base
            return max(base, BACKOFF_ERRORI_S[min(self._errori_di_fila, len(BACKOFF_ERRORI_S)) - 1])

    def avvia(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._ferma.clear()
        self._thread = threading.Thread(target=self._ciclo, name="cache_cloud_sorveglianza", daemon=True)
        self._thread.start()

    def ferma(self, attesa_s: float = 5.0) -> None:
        self._ferma.set()
        if self._thread is not None:
            self._thread.join(attesa_s)
            if self._thread.is_alive():
                logger.error("[cache_cloud] il thread della sorveglianza non si e' fermato in %.1f s", attesa_s)
        self._thread = None

    def vivo(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def statistiche(self) -> Mapping[str, Any]:
        with self._lock:
            return {**self._conti, "modo": self._modo, "errori_di_fila": self._errori_di_fila}

    # --------------------------------------------- interni
    def _consegna_omega(self, valore: Optional[str]) -> bool:
        adesso = self._orologio()
        with self._lock:
            if valore is None:
                if adesso - self._ultimo_errore_omega < INTERVALLO_SORVEGLIANZA_S:
                    return False
                self._ultimo_errore_omega = adesso
            elif valore == self._ultima_omega:
                return False
            self._ultima_omega = valore
        if self._replica is not None:
            self._replica.notifica_sentinella(valore)
        return True

    def _ciclo(self) -> None:
        while not self._ferma.is_set():
            try:
                self.giro()
            except Exception:  # noqa: BLE001 - il thread non muore: si logga e si riprova
                logger.exception("[cache_cloud] giro della sorveglianza fallito")
            self._ferma.wait(self.attesa())
