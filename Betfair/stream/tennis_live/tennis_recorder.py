"""Registrazione OPT-IN per-partita del raw nativo tennis (tee nel listener).

RIUSO del recorder della missione 1-tick tennis (10/07): stesso pattern e stesso
FORMATO di ``tennis_scalper/record_multi.py`` (tee del messaggio ``mcm`` nativo
nel ``StreamListener.on_data`` → ``<DIR>/<event>/<event>.raw.jsonl`` + punteggio
sincronizzato ``<event>/<event>.score.jsonl``), che è esattamente il layout
consumato dai lab tennis (``flb_backtest``/``lab_grid``/``lab_grid_score``/
``backtest_pro``/``validate``: glob ``<dir>/*/*.raw.jsonl``).

Differenze rispetto a record_multi (processo di campagna massiva):
  * qui il tee vive DENTRO il runner tennis, sulla STESSA subscription per-evento
    (stream unico: nessuna seconda connessione Betfair, zero REST extra);
  * gating PER-EVENTO opt-in: si registra SOLO l'evento con ``record=true`` in
    ``tennis_live_follow`` (migrazione ``tennis_follow_record.sql``). Il flag è
    riletto periodicamente dal ``record_flag_worker`` → il toggle a metà partita
    accende/spegne il tee senza riavviare lo stream;
  * fallback conservativo: colonna assente (migrazione non applicata) → NESSUNA
    registrazione + warning una tantum, il runner non si rompe mai.

Self-contained come record_multi: NON tocca ``raw_listener``/``recorder``
condivisi col calcio (singleton e listener DEDICATI al tennis). Il tee non deve
MAI rompere lo stream: ogni scrittura è best-effort con self-heal dell'handle.

07/10 (Replay Tennis): a FINE PARTITA (MATCH_ODDS ``CLOSED`` nella
marketDefinition di un evento registrato) il tee programma il caricamento della
registrazione nel Replay Tennis (``Betfair.stream.tennis_replay``) in un THREAD
di questo stesso processo (nessun processo nuovo), dopo
``TENNIS_REPLAY_CARICA_DOPO_S`` secondi (default 60: lascia arrivare l'ultima
riga di punteggio). ``TENNIS_REPLAY_CARICA=0`` lo spegne. Un errore (migrazione
non applicata, rete) e' solo un warning: la registrazione resta su disco e si
carica a mano con ``python -m Betfair.stream.tennis_replay.importa``.

08/10 (cantiere 14, caso 35790089 «Marcelo Tomas Barrios V» troncato dall'IPS): a ogni REC il
tee scrive accanto al raw, in ``<cartella del giorno>/_names.json``, i nomi COMPLETI dei runner
di tutti i mercati registrati (catalogo ``listMarketCatalogue``): vedi ``scrivi_nomi_catalogo``.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from betfairlightweight import StreamListener
from flumine.streams.marketstream import MarketStream

from ..runner_lifecycle import MSG_HEARTBEAT, classifica_messaggio_stream
from .mercati_registrati import CHIAVE as _CHIAVE_MERCATI, mercati_extra

logger = logging.getLogger(__name__)


def default_record_dir(now: Optional[datetime] = None) -> str:
    """Cartella di output delle registrazioni tennis.

    Root = env ``TENNIS_RECORD_DIR`` oppure ``~/Desktop/tennis_rec`` (la stessa
    usata dalle campagne record_multi della missione 1-tick, vedi
    BIBBIA_SCALPER_TENNIS §dati), con sottocartella per giorno UTC — layout
    finale ``<root>/<YYYYMMDD>/<event>/<event>.raw.jsonl``, replayabile as-is
    dai lab (``--data <root>/<YYYYMMDD>``).
    """
    root = os.getenv("TENNIS_RECORD_DIR", "").strip() or os.path.join(
        os.path.expanduser("~"), "Desktop", "tennis_rec"
    )
    day = (now or datetime.now(timezone.utc)).strftime("%Y%m%d")
    return os.path.join(root, day)


#: nome del file dei nomi accanto alle registrazioni (stesso dei grid runner/lab/banco)
FILE_NOMI = "_names.json"
_LOCK_NOMI = threading.Lock()   # un solo scrittore di _names.json alla volta, in questo processo


def nomi_dal_catalogo(meta: Optional[Dict[str, Any]]) -> "tuple[Dict[str, str], Dict[str, Dict[str, str]]]":
    """``(nomi del Match Odds, {market_id: nomi})`` dal catalogo del runner (``market_meta[event]``).

    Solo nomi veri (stringhe non vuote): il catalogo e' ``listMarketCatalogue``, i nomi COMPLETI."""
    meta = meta or {}

    def _pulisci(d: Any) -> Dict[str, str]:
        return {str(k): str(v) for k, v in (d or {}).items() if isinstance(v, str) and v.strip()}

    per_mercato: Dict[str, Dict[str, str]] = {}
    mo = _pulisci(meta.get("selection_names"))
    if meta.get("market_id") and mo:
        per_mercato[str(meta["market_id"])] = mo
    for x in meta.get(_CHIAVE_MERCATI) or []:
        n = _pulisci((x or {}).get("selection_names"))
        if (x or {}).get("market_id") and n:
            per_mercato[str(x["market_id"])] = n
    return mo, per_mercato


ESITO_SCRITTO = "scritto"
ESITO_INVARIATO = "invariato"   # niente di nuovo da aggiungere (o nessun nome nel catalogo)
ESITO_ERRORE = "errore"


def scrivi_nomi_catalogo(cartella: str, event_id: str, meta: Optional[Dict[str, Any]]) -> str:
    """Scrive in ``<cartella>/_names.json`` i nomi COMPLETI dei runner dell'evento (08/10,
    cantiere 14: il flusso Betfair non porta i nomi e l'IPS li tronca, caso 35790089).

    Formato, compatibile con TUTTI i lettori di ``_names.json`` (grid runner, lab, banco,
    ``replay_bot``, Replay Tennis): chiave piatta ``{event_id: {selection_id: nome}}`` per il
    Match Odds, e in piu' la chiave riservata ``"_mercati"`` ->
    ``{event_id: {market_id: {selection_id: nome}}}`` per TUTTI i mercati registrati.
    NON SOVRASCRIVE: la voce piatta di una partita gia' presente resta com'e'; di ogni
    mercato si aggiungono solo le selezioni mancanti. Scrittura atomica (file temporaneo +
    ``os.replace``). File esistente illeggibile = non si tocca (warning). Ritorna
    ``ESITO_SCRITTO``, ``ESITO_INVARIATO`` o ``ESITO_ERRORE``. Best-effort: MAI
    un'eccezione verso il chiamante."""
    ev = str(event_id)
    path = os.path.join(cartella, FILE_NOMI)
    try:
        from ..tennis_replay.convertitore import CHIAVE_MERCATI_NOMI

        mo, per_mercato = nomi_dal_catalogo(meta)
        if not mo and not per_mercato:
            return ESITO_INVARIATO
        with _LOCK_NOMI:
            tutto: Dict[str, Any] = {}
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        tutto = json.load(fh)
                except (ValueError, OSError) as exc:
                    logger.warning("[tennis-rec] %s illeggibile (%s): non lo tocco, nomi di %s non scritti",
                                   path, str(exc)[:100], ev)
                    return ESITO_ERRORE
                if not isinstance(tutto, dict):
                    logger.warning("[tennis-rec] %s non e' un oggetto json: non lo tocco", path)
                    return ESITO_ERRORE
            cambiato = False
            if mo and not (isinstance(tutto.get(ev), dict) and tutto[ev]):
                tutto[ev] = dict(mo)
                cambiato = True
            mercati = tutto.get(CHIAVE_MERCATI_NOMI)
            if not isinstance(mercati, dict):
                mercati = {}
            del_evento = mercati.get(ev)
            if not isinstance(del_evento, dict):
                del_evento = {}
            for mid, nomi in per_mercato.items():
                voce = del_evento.get(mid)
                if not isinstance(voce, dict):
                    voce = {}
                for sid, nome in nomi.items():
                    if sid not in voce:
                        voce[sid] = nome
                        cambiato = True
                if voce:
                    del_evento[mid] = voce
            if not cambiato:
                return ESITO_INVARIATO
            mercati[ev] = del_evento
            tutto[CHIAVE_MERCATI_NOMI] = mercati
            os.makedirs(cartella, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(tutto, fh, indent=2, default=str)
            os.replace(tmp, path)
        logger.info("[tennis-rec] nomi dei runner di %s scritti in %s (%d mercati)", ev, path, len(per_mercato))
        return ESITO_SCRITTO
    except Exception as exc:  # noqa: BLE001 - i nomi non rompono mai la registrazione
        logger.warning("[tennis-rec] nomi dei runner di %s NON scritti in %s: %s", ev, path, str(exc)[:150])
        return ESITO_ERRORE


class TennisRawTee:
    """Stato del tee raw tennis con gating PER-EVENTO (istanza dedicata al tennis).

    Adattamento di ``record_multi._MultiRawState``: stesso formato su disco,
    in più ``enabled_events`` (opt-in per-partita) e lo score tee integrato
    (dedup sulla score key, come lo ``_score_worker`` di record_multi).
    """

    def __init__(self) -> None:
        self.dir: Optional[str] = None
        self.market_to_event: Dict[str, str] = {}
        self.enabled_events: Set[str] = set()
        self._files: Dict[str, Any] = {}          # event_id -> raw file handle
        self._score_files: Dict[str, Any] = {}    # event_id -> score file handle
        self._score_lastkey: Dict[str, Any] = {}
        self._lock = threading.Lock()
        # R-STREAM-1 (26/09): battito dello stream (ms locali dell'ultimo
        # messaggio con dati / dell'ultimo heartbeat Betfair), aggiornato su
        # OGNI messaggio anche senza partite in registrazione: lo legge lo
        # stall_worker del runner tennis. 0 = mai visto.
        self.last_data_ms: int = 0
        self.last_heartbeat_ms: int = 0
        self._counts: Dict[str, int] = {}
        self._err_logged: Dict[str, float] = {}
        # 07/10 (Replay Tennis): catalogo del runner per evento (nomi dei runner,
        # torneo) e caricamenti a fine partita gia' programmati (uno per evento)
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._fine_programmata: Dict[str, threading.Timer] = {}
        # 08/10 (cantiere 14): firma dell'ultimo catalogo scritto in _names.json per evento
        # e istante prima del quale non si riprova dopo un errore di scrittura
        self._nomi_firma: Dict[str, str] = {}
        self._nomi_riprova: Dict[str, float] = {}

    # -- controllo (record_flag_worker) ------------------------------------ #
    def enable(self, event_id: str, market_ids: Iterable[str],
               meta: Optional[Dict[str, Any]] = None) -> None:
        """Accende la registrazione per UN evento (idempotente).

        ``meta`` (07/10): il catalogo del runner (``market_meta[event]``: nomi dei
        runner, torneo) che il raw non contiene; serve al caricamento nel Replay
        Tennis a fine partita."""
        ev = str(event_id)
        with self._lock:
            if meta:
                self._meta[ev] = dict(meta)
            if self.dir is None:
                self.dir = default_record_dir()
            for mid in market_ids or []:
                if mid:
                    self.market_to_event[str(mid)] = ev
            if ev not in self.enabled_events:
                self.enabled_events.add(ev)
                logger.info("[tennis-rec] REC ON evento %s -> %s", ev, self.dir)
            cartella, meta_att = self.dir, dict(self._meta.get(ev) or {})
        # 08/10 (cantiere 14): FUORI dal lock del tee (il tee dei messaggi non aspetta il disco)
        self._scrivi_nomi(ev, cartella, meta_att)

    def _scrivi_nomi(self, ev: str, cartella: Optional[str], meta: Dict[str, Any]) -> None:
        """Nomi COMPLETI dei runner (catalogo) accanto al raw, in ``_names.json``.

        Chiamata a ogni ``enable`` (il ``record_flag_worker`` lo richiama a ogni giro con il
        catalogo piu' recente, anche quando i mercati in piu' arrivano dopo): scrive solo se il
        catalogo e' cambiato dall'ultima volta; dopo un errore riprova non prima di 60 s."""
        if not cartella or not meta:
            return
        try:
            firma = json.dumps(nomi_dal_catalogo(meta), sort_keys=True)
            if self._nomi_firma.get(ev) == firma or time.time() < self._nomi_riprova.get(ev, 0.0):
                return
            esito = scrivi_nomi_catalogo(cartella, ev, meta)
            if esito == ESITO_ERRORE:
                self._nomi_riprova[ev] = time.time() + 60.0
            else:
                self._nomi_firma[ev] = firma
                self._nomi_riprova.pop(ev, None)
        except Exception as exc:  # noqa: BLE001 - mai rompere il worker per i nomi
            logger.warning("[tennis-rec] nomi dei runner %s KO (ignorato): %s", ev, str(exc)[:150])

    def disable(self, event_id: str) -> None:
        """Spegne la registrazione per UN evento e chiude i file (idempotente)."""
        ev = str(event_id)
        with self._lock:
            if ev in self.enabled_events:
                self.enabled_events.discard(ev)
                logger.info("[tennis-rec] REC OFF evento %s", ev)
            for pool in (self._files, self._score_files):
                fh = pool.pop(ev, None)
                if fh is not None:
                    try:
                        fh.close()
                    except Exception:  # noqa: BLE001
                        pass

    def is_enabled(self, event_id: str) -> bool:
        return str(event_id) in self.enabled_events

    # -- tee raw (listener) ------------------------------------------------ #
    def _file_for(self, event_id: str) -> Any:
        fh = self._files.get(event_id)
        if fh is None:
            ev_dir = os.path.join(self.dir or ".", event_id)
            os.makedirs(ev_dir, exist_ok=True)
            path = os.path.join(ev_dir, f"{event_id}.raw.jsonl")
            fh = open(path, "a", encoding="utf-8")  # noqa: SIM115 - chiuso in disable/close
            self._files[event_id] = fh
            logger.info("[tennis-rec] apro file nativo: %s", path)
        return fh

    def write_message(self, raw_data: str) -> None:
        """Tee di UN messaggio raw dello stream. Percorso veloce: nessun evento
        registrato → return immediato (zero impatto sulle partite non registrate)."""
        # R-STREAM-1 (26/09): il battito PRIMA del percorso veloce (lettura per
        # sottostringa, niente json.loads): senza, lo stallo era invisibile.
        tipo = classifica_messaggio_stream(raw_data)
        if tipo is not None:
            ora_ms = int(time.time() * 1000)
            if tipo == MSG_HEARTBEAT:
                self.last_heartbeat_ms = ora_ms
            else:
                self.last_data_ms = ora_ms
        if not self.enabled_events or not self.dir:
            return
        try:
            msg = json.loads(raw_data)
        except (ValueError, TypeError):
            return
        if msg.get("op") != "mcm":
            return
        mc = msg.get("mc")
        if not mc:
            return
        # auto-routing market->event dalla marketDefinition (come record_multi):
        # copre i mercati imparati dopo l'enable senza dipendere dal worker.
        for change in mc:
            mid = change.get("id")
            mdef = change.get("marketDefinition") or {}
            ev = mdef.get("eventId")
            if mid and ev and mid not in self.market_to_event:
                self.market_to_event[mid] = str(ev)
        by_event: Dict[str, list] = {}
        for change in mc:
            mid = change.get("id")
            ev = self.market_to_event.get(mid)
            if ev is None or ev not in self.enabled_events:
                continue  # opt-in: gli eventi non registrati non toccano il disco
            by_event.setdefault(ev, []).append(change)
        if not by_event:
            return
        with self._lock:
            for ev, changes in by_event.items():
                if ev not in self.enabled_events:  # ricontrollo sotto lock (toggle)
                    continue
                out = {k: msg[k] for k in ("op", "clk", "pt", "ct") if k in msg}
                out["mc"] = changes
                # SELF-HEAL (lezione raw_listener 11/07): un handle rotto non deve
                # uccidere il tee per sempre — drop e riapertura al prossimo messaggio.
                try:
                    fh = self._file_for(ev)
                    fh.write(json.dumps(out, separators=(",", ":")) + "\n")
                    fh.flush()
                except Exception as exc:  # noqa: BLE001 - mai rompere lo stream
                    bad = self._files.pop(ev, None)
                    if bad is not None:
                        try:
                            bad.close()
                        except Exception:  # noqa: BLE001
                            pass
                    now_s = time.time()
                    if now_s - self._err_logged.get(ev, 0.0) >= 60.0:
                        self._err_logged[ev] = now_s
                        logger.warning("[tennis-rec] write KO evento %s (riapro al "
                                       "prossimo messaggio): %s", ev, str(exc)[:150])
                    continue
                self._counts[ev] = self._counts.get(ev, 0) + 1
                if any(((c.get("marketDefinition") or {}).get("status") == "CLOSED"
                        and (c.get("marketDefinition") or {}).get("marketType") == "MATCH_ODDS")
                       for c in changes):
                    self._programma_replay(ev)

    # -- tee punteggio (score_and_now_worker) ------------------------------ #
    def write_score(self, event_id: str, ts: Any) -> None:
        """Appende il punteggio sincronizzato (formato record_multi: una riga
        ``{"t": epoch, "score": raw}`` per cambio di score key). Best-effort."""
        ev = str(event_id)
        if ts is None or ev not in self.enabled_events or not self.dir:
            return
        try:
            key = ts.key()
            if self._score_lastkey.get(ev) == key:
                return
            with self._lock:
                if ev not in self.enabled_events:
                    return
                self._score_lastkey[ev] = key
                fh = self._score_files.get(ev)
                if fh is None:
                    ev_dir = os.path.join(self.dir, ev)
                    os.makedirs(ev_dir, exist_ok=True)
                    fh = open(os.path.join(ev_dir, f"{ev}.score.jsonl"), "a",
                              encoding="utf-8")  # noqa: SIM115
                    self._score_files[ev] = fh
                fh.write(json.dumps({"t": time.time(), "score": ts.raw},
                                    default=str) + "\n")
                fh.flush()
        except Exception as exc:  # noqa: BLE001 - lo score tee non rompe mai il worker
            logger.debug("[tennis-rec] score tee KO %s (ignorato): %s", ev, exc)

    # -- Replay Tennis a fine partita (07/10) ------------------------------ #
    def _programma_replay(self, ev: str) -> None:
        """Programma UNA volta per evento il caricamento nel Replay Tennis.
        Chiamata sotto ``self._lock`` dal tee: solo stato in memoria, mai I/O."""
        if ev in self._fine_programmata or os.getenv("TENNIS_REPLAY_CARICA", "1").strip() == "0":
            return
        try:
            ritardo = max(0.0, float(os.getenv("TENNIS_REPLAY_CARICA_DOPO_S", "60")))
        except ValueError:
            ritardo = 60.0
        ev_dir = os.path.join(self.dir or ".", ev)
        timer = threading.Timer(ritardo, self._carica_replay,
                                args=(ev, ev_dir, dict(self._meta.get(ev) or {})))
        timer.daemon = True
        timer.name = f"tennis-replay-{ev}"
        self._fine_programmata[ev] = timer
        timer.start()
        logger.info("[tennis-rec] partita %s finita: caricamento nel Replay Tennis tra %.0f s", ev, ritardo)

    def _carica_replay(self, ev: str, ev_dir: str, meta: Dict[str, Any]) -> None:
        """Thread del timer: converte e carica. Best-effort, MAI un'eccezione fuori."""
        try:
            from ..tennis_replay.caricamento import carica_replay
            from ..tennis_replay.convertitore import converti_evento

            raw = os.path.join(ev_dir, f"{ev}.raw.jsonl")
            score = os.path.join(ev_dir, f"{ev}.score.jsonl")
            nomi: Dict[str, Dict[str, str]] = {}
            if meta.get("market_id") and meta.get("selection_names"):
                nomi[str(meta["market_id"])] = {str(k): str(v) for k, v in meta["selection_names"].items()}
            nomi_mercato: Dict[str, str] = {}
            for x in meta.get(_CHIAVE_MERCATI) or []:   # 07/10: catalogo degli altri mercati
                mid = str(x.get("market_id") or "")
                if mid:
                    nomi[mid] = {str(k): str(v) for k, v in (x.get("selection_names") or {}).items()}
                    if x.get("market_name"):
                        nomi_mercato[mid] = str(x["market_name"])
            anagrafica = {"competition_name": meta.get("competition_name")}
            rt = converti_evento([raw], [score] if os.path.exists(score) else [],
                                 event_id=ev, nomi=nomi, meta=anagrafica, nomi_mercato=nomi_mercato)
            carica_replay(rt, fonte="runner", raw_files=[raw], raw_bytes=os.path.getsize(raw))
        except Exception as exc:  # noqa: BLE001 - mai rompere il runner per il replay
            logger.warning("[tennis-rec] Replay Tennis %s NON caricato (resta su disco; a mano: "
                           "python -m Betfair.stream.tennis_replay.importa <cartella> --evento %s): %s",
                           ev, ev, str(exc)[:200])

    # -- telemetria / teardown --------------------------------------------- #
    def counts(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def close(self) -> None:
        with self._lock:
            for pool in (self._files, self._score_files):
                for fh in pool.values():
                    try:
                        fh.close()
                    except Exception:  # noqa: BLE001
                        pass
                pool.clear()
            self.enabled_events.clear()


# singleton DEDICATO al tennis (il listener è istanziato da flumine internamente;
# sopravvive ai restart del framework → il toggle e i file restano coerenti).
RAW_TEE = TennisRawTee()

# warning una tantum "migrazione non applicata" (fallback conservativo)
_MISSING_COLUMN_WARNED = False


class _TennisRecListener(StreamListener):
    """StreamListener tennis: tee del raw nativo, poi parsing normale."""

    def on_data(self, raw_data: str):  # type: ignore[override]
        try:
            RAW_TEE.write_message(raw_data)
        except Exception as e:  # noqa: BLE001 - il recording non deve MAI rompere lo stream
            logger.debug("[tennis-rec] tee fallito (ignorato): %s", e)
        return super().on_data(raw_data)


class TennisRecMarketStream(MarketStream):
    """MarketStream del runner tennis con tee opt-in (stessa subscription)."""

    LISTENER = _TennisRecListener
    # LATENZA STREAM: betfairlightweight confronta l'orologio locale col
    # publish-time Betfair e logga un WARNING per OGNI messaggio oltre 0.5s. Con
    # l'orologio del PC sfasato (misurato 09/09: −2.8s via w32tm) è tutto rumore
    # (3.918 righe "Latency high" nel log del runner) e CPU sprecata: la misura
    # non guida nessuna decisione qui → disattivata. La latenza reale la si
    # vede dal keep-alive/heartbeat e dai riavvii del watchdog.
    MAX_LATENCY = None


def sync_record_flags(follows: List[Dict[str, Any]],
                      market_meta: Dict[str, Dict[str, Any]],
                      tee: Optional[TennisRawTee] = None) -> Set[str]:
    """Allinea il tee ai flag ``record`` di ``tennis_live_follow``.

    ``follows`` = righe follow (select *, quindi con ``record`` SOLO se la
    migrazione è applicata); ``market_meta`` = mappa event_id -> meta del runner
    (per il routing market->event). Ritorna gli eventi con registrazione attiva.

    FALLBACK CONSERVATIVO: se nessuna riga espone la chiave ``record`` (colonna
    assente = migrazione ``tennis_follow_record.sql`` non applicata) NON si
    registra nulla (default storico del tennis) e si logga un warning una
    tantum. Mai un'eccezione verso il chiamante.
    """
    global _MISSING_COLUMN_WARNED  # noqa: PLW0603 - warning una tantum di processo
    tee = tee if tee is not None else RAW_TEE
    enabled: Set[str] = set()
    try:
        rows = [r for r in (follows or []) if r.get("event_id")]
        if rows and not any("record" in r for r in rows):
            if not _MISSING_COLUMN_WARNED:
                _MISSING_COLUMN_WARNED = True
                logger.warning(
                    "[tennis-rec] colonna 'record' assente su tennis_live_follow: "
                    "applica migrations/tennis_follow_record.sql per la "
                    "registrazione opt-in. Nessuna registrazione (default storico).")
            rows = []
        wanted = {str(r["event_id"]) for r in rows if bool(r.get("record"))}
        # enable SOLO per gli eventi effettivamente streammati dal runner
        for ev in sorted(wanted):
            meta = market_meta.get(ev) or {}
            mid = meta.get("market_id")
            if not mid:
                continue  # non (ancora) catalogato: riproverà al prossimo giro
            # 07/10: anche i mercati in piu' delle partite registrate (stesso file)
            tee.enable(ev, [mid] + mercati_extra(meta), meta=meta)
            enabled.add(ev)
        # disable per gli eventi accesi ma non più richiesti (toggle OFF a metà)
        for ev in sorted(set(tee.enabled_events) - enabled):
            tee.disable(ev)
    except Exception as e:  # noqa: BLE001 - il gating non rompe mai il worker
        logger.warning("[tennis-rec] sync flag KO (ignorato): %s", e)
    return enabled
