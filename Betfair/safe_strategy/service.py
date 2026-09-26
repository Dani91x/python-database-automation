"""service.py — SCANNER AUTONOMO Safe Strategy (calcio + tennis in-play).

Monitora TUTTI gli eventi live del momento (nessuna iscrizione manuale):
  · catalogo MATCH_ODDS per sport su finestra MOBILE (KO da -6h a +14h,
    refresh 300s, peso ~0, fino a 1000 mercati/sport = massimo Betfair: mai
    tagliare le giornate piene);
  · quote MATCH_ODDS dei soli mercati RILEVANTI (in-play, o KO entro 20′):
    Exchange Stream API ufficiale (push, conflate 1s, cap 180 mercati con
    priorità in-play) + poll REST EX_BEST_OFFERS (chunk 25 → peso 125 < 200)
    come FALLBACK per i mercati che lo stream non copre o quando lo stream
    non è in salute — cadenza ADATTIVA 10s (2°T calcio dal 40′ in poi /
    tennis in-play), 20-60s altrimenti;
  · punteggi/minuti/rossi + disponibilità video/animazione per TUTTI gli
    in-play in UNA chiamata IPS scoresAndBroadcast (chunk 50 id) ogni 2s in un
    THREAD dedicato (ScoreFeedWorker: mai in coda alle quote) + timeline calcio
    in batch ogni 30s (fallback get_scores): è il FEED UNICO
    di punteggi/timeline anche per i runner calcio e tennis (stato IPS grezzo
    `score_raw` nel payload → scores/scan_feed.py), che così non rifanno per
    ogni evento seguito le stesse chiamate;
  · Correct Score dei candidati (calcio in-play dal 30′, ≤3 gol/lato):
    catalogo appena compare un candidato nuovo, poi il mercato va sul POOL
    STREAM (o nel REST di fallback) e viene pubblicato COMPLETO — tutte le
    selezioni con id/nome/prezzi/size: è il feed anche per Omega;
  · MERCATI A GOL dei candidati opportunità (calcio in-play dal 1′, al massimo
    scanner.OPP_MAX_EVENTS eventi, solo le linee ancora INDECISE): Over/Under
    0.5-7.5, Gol/NoGol, 1X2 primo tempo. Stesso ciclo di vita del Correct Score
    (catalogo per i candidati nuovi, quote dal pool stream con priorità SEMPRE
    inferiore ai mercati core, REST come fallback) → blocchi `ou`/`btts`/
    `ht_result` del payload. La VALUTAZIONE (opportunity.py) NON gira qui: la fa
    bot_service.py sulla tabella safe_strategy_opportunities. Solo per collaudo
    si può accendere in linea con SAFE_SCAN_OPPORTUNITIES=1;
  · riferimento 1X2 pre-KO: aggiornato da KO-15′ e CONGELATO al primo tick
    in-play (mai quote live nel riferimento — regola di certificazione).

Scrive i FATTI su safe_strategy_scan (write-on-change) + heartbeat su
safe_strategy_status. La VALUTAZIONE resta nel motore certificato frontend.
Nessun ordine, mai.

Uso:  python -m Betfair.safe_strategy.service [--once] [--dry]
  --once  un ciclo completo e esce (collaudo)
  --dry   nessuna scrittura DB, stampa il riepilogo (collaudo senza migrazione)
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from collections import deque
from contextlib import contextmanager
from typing import Any, Deque, Dict, List, Optional, Sequence

from Betfair.stream.auth import build_client, keep_alive, safe_logout
from Betfair.stream.scores.betfair_inplay import normalize_timeline, parse_score_dict
from Betfair.stream.single_instance import acquire_single_instance_lock
from Betfair.stream import valuta as _valuta
from Betfair.stream.tennis_scalper.tennis_score import parse_tennis_scores

from . import db as scan_db
from . import pressure as _pressure
from . import scanner
from . import selezione as _selezione
from .stream import MarketStreamPool

logger = logging.getLogger("safe_strategy")

_LOCK_PORT = int(os.getenv("SAFE_STRATEGY_LOCK_PORT", "47315"))
# ===========================================================================
# F1 (18/09) - IL CANALE LOCALE DELLO SCANNER, IN SOLA PUBBLICAZIONE
# ===========================================================================
# Porta 47336, accanto a 47331 (runner calcio), 47332 (runner tennis), 47333
# (Mike), 47334 (Omega), 47335 (bot Safe). Nessun processo nuovo: il canale
# nasce DENTRO il processo dello scanner, che gira gia'.
#   · ``scan_calcio``   la riga di scan del CALCIO, identica a quella del DB;
#   · ``scan_tennis``   la riga di scan del TENNIS, identica a quella del DB;
#   · ``scanner_stato`` la stessa riga che va su ``safe_strategy_status``.
# Due topic separati e non uno con un campo ``sport``: calcio e tennis non si
# mischiano mai, nemmeno dentro un payload (invariante B12 del piano). Il campo
# ``sport`` resta comunque dentro il messaggio, cosi' un consumatore che
# sbagliasse topic se ne accorgerebbe lo stesso.
# ``solo_lettura=True`` come tutti i canali dei bot: si mostra, non si comanda.
# Il canale del RUNNER, che esegue ordini veri, resta un'altra cosa e non si
# allarga (``local_channel`` §SICUREZZA).
_PORTA_CANALE_SCAN = 47336
_PORTA_CANALE_ENV = "SAFE_SCAN_WS_PORT"
_TOPIC_SCAN = {"calcio": "scan_calcio", "tennis": "scan_tennis"}
_TOPIC_SCANNER_STATO = "scanner_stato"
# INTERRUTTORE DI FASE, default SPENTO. Acceso SOLO se qualcuno lo scrive
# davvero: variabile assente, vuota o con qualunque altro valore = spento.
# Il verso conta piu' del valore. Il `.env` arriva allo scanner per la catena
# di import di testa (`stream/auth.py` -> `config.load_dotenv()`), che non e'
# garantita da nulla: se un domani quell'import diventasse pigro - cioe'
# esattamente la cura applicata il 17/09 a `stream/scalper/__init__.py` - ogni
# costante di modulo prenderebbe il proprio default in silenzio. Con questo
# verso il guasto silenzioso e' "il canale resta spento"; col verso opposto
# sarebbe "il canale si accende da solo, senza che nessuno l'abbia chiesto".
_CANALE_ENV = "SAFE_SCAN_CANALE"
_CANALE_VALORI_ACCESI = ("1", "true", "si", "yes")


def _letto_acceso() -> bool:
    """L'interruttore del canale, letto dall'ambiente ADESSO.

    Sta in una funzione perche' la regola vada provata senza ricaricare il
    modulo; il valore che conta in esercizio resta la COSTANTE qui sotto,
    valutata una volta sola all'import - cioe' dopo che la catena di import di
    testa ha chiamato ``load_dotenv()`` (Appendice H del piano).
    """
    return (os.getenv(_CANALE_ENV) or "").strip().lower() in _CANALE_VALORI_ACCESI


_CANALE_ACCESO = _letto_acceso()
_CATALOGUE_TTL_SEC = 300.0
# catalogo Correct Score: la chiamata parte SOLO se c'è un candidato senza
# mercato in cache (refresh_cs_catalogue esce subito altrimenti), quindi il
# throttle può essere corto: un candidato nuovo al 48′ ha la quota entro ~20s
# (prima il TTL era 600s → segnale R.E. in ritardo fino a 10 minuti)
_CS_CATALOGUE_MIN_INTERVAL_SEC = 20.0
# IPS non ha stream: poll batch in un THREAD DEDICATO (ScoreFeedWorker), così
# il giro punteggi non blocca mai la pubblicazione delle quote e viceversa
# (misurato 09/09: un giro serializzato nel tick costava fino a ~3s in più).
# 2s = la cadenza che il runner tennis usava PER EVENTO, qui per TUTTI gli
# in-play con 1-3 chiamate (chunk 50, verificato: ~70ms a chiamata). È il FEED
# UNICO di punteggi anche per i runner (scores/scan_feed.py).
_SCORES_PERIOD_SEC = 2.0
# respiro tra i lotti IPS (servizio separato da API-NG: niente peso 200)
_IPS_REQ_DELAY = 0.1
# timeline calcio (gol/cartellini col minuto) in batch: cambia a eventi discreti
_TIMELINE_PERIOD_SEC = 30.0
# throttle di scrittura per-evento: con lo STREAM le quote cambiano ogni secondo
# (conflate 1s) — mai inondare Supabase: max 1 riga/evento ogni 2.5s (e comunque
# solo write-on-change).
_PUBLISH_MIN_INTERVAL_SEC = 2.5
_STATUS_PERIOD_SEC = 10.0
_ORPHAN_PURGE_PERIOD_SEC = 300.0
_KEEPALIVE_PERIOD_SEC = 900.0
_BOOK_CHUNK = 25          # peso EX_BEST_OFFERS 5/mercato → 125 < 200
_SCORES_CHUNK = 50        # eventId per chiamata IPS (verificato 09/09: 50 ok, ~70ms)
_REQ_DELAY = 0.35         # respiro tra chiamate REST (anti-throttling)
# cap catalogo per sport = massimo Betfair per listMarketCatalogue (1000): le
# proiezioni usate pesano 0 (EVENT, COMPETITION, MARKET_START_TIME,
# RUNNER_DESCRIPTION) → nessun vincolo di peso, una chiamata ogni 5' per sport.
# Col vecchio 120 + sort FIRST_TO_START gli eventi serali del sabato restavano
# FUORI dal radar finché quelli del pomeriggio non chiudevano; con 1000 nessuna
# giornata reale (calcio ~300-500 match/20h) tocca il tetto.
_MAX_MARKETS = 1000
# limite DURO di listMarketCatalogue (Betfair: max_results 1-1000). Oltre,
# l'API risponde INVALID_INPUT_DATA e l'eccezione porterebbe via l'intero giro.
_MAX_CATALOGUE_RESULTS = 1000
# finestra catalogo MOBILE: in-play iniziati fino a 6h fa + KO nelle prossime
# 14h (la vecchia finestra "fino a mezzanotte UTC" perdeva i notturni)
_CATALOGUE_PAST_H = 6
_CATALOGUE_AHEAD_H = 14

_SPORTS = {"calcio": "1", "tennis": "2"}
# IPS Betfair (non ufficiale, lo stesso di betfairlightweight in_play_service e del
# sito): punteggi + disponibilità video/animazione in una chiamata. Host .it come
# il sito italiano (il .com risponde identico).
_IPS_SB_URL = "https://ips.betfair.it/inplayservice/v1.1/scoresAndBroadcast"


# OPPORTUNITA' dentro il feed: SPENTE di default. Il calcolo vive in
# bot_service.py (ogni ~10s per riga in-play, risultati su safe_strategy_opportunities,
# che e' cio' che legge la UI): rifarlo qui duplicherebbe la CPU dentro il processo
# critico del feed. Il flag serve solo per collaudo/diagnostica; a 0 la chiave
# `opportunities` NON compare proprio nel payload.
_OPPORTUNITIES_ENV = "SAFE_SCAN_OPPORTUNITIES"

# RAMO PRE-KO O/U (bot Mike): ore prima del KO in cui tenere sotto quote le linee
# Over/Under 3.5 e 4.5 delle partite NON ancora iniziate (scanner.PRE_KO_OU_MARKET_TYPES).
# Vuoto/0 = spento (feed identico a prima). Costo: 2 mercati per partita in
# finestra sul pool stream (tier 2: mai davanti ai mercati core) + UNA
# listMarketCatalogue ogni 20s SOLO se ci sono candidati senza catalogo.
_PRE_KO_OU_ENV = "SAFE_PRE_KO_OU_HOURS"
# chiavi che _prune_opp_blocks aggiunge ai blocchi a gol in cache (H6): non
# sono prezzo, non contano nel confronto "book invariato" di _apply_opp_book
_OPP_MARKER_KEYS = ("ts_ms", "seen_ms", "decided", "for_mike")
# una chiamata Betfair fallita NON si ripete a ogni tick (0,5 s): catalogo
# ritentato dopo 30 s, poll REST dei book dopo la sua cadenza normale
_CATALOGUE_RETRY_SEC = 30.0
# 17/09 - COPERTURA PER MERCATO, non per socket. Un mercato sottoscritto che
# da questo tempo non consegna un book CON PREZZI e' "scoperto" e torna al poll
# REST, anche se lo shard e' sano: il 17/09 lo stream consegnava book di sola
# ``marketDefinition`` (runner con selection_id e status, scalette vuote) e il
# fallback non e' mai partito perche' "coperto" si decideva sugli heartbeat.
_STREAM_PRICE_MAX_AGE_SEC = 20.0
# oltre questo tempo SENZA UN PREZZO da nessuna fonte (stream o REST) il
# mercato entra in ``stream_mercati_senza_quote``: il 17/09 ``last_error`` era
# null mentre il feed era morto da ore, ed e' questo che ha reso il blackout
# invisibile al trader.
_SENZA_QUOTE_MAX_AGE_SEC = 30.0
# un mercato che AVEVA prezzi dallo stream e li ha persi da piu' di questo
# tempo, senza che il REST lo copra, e' un allarme anche se giovane
_STREAM_PERSO_MAX_AGE_SEC = 60.0
# MERCATI CORE: quelli su cui si apre, si esce e ci si copre (il MATCH_ODDS di
# calcio e tennis, il Correct Score e l'Half Time Score dei candidati).
# Le linee a gol (``kind == "opp"``) NON sono core: una Over 7.5 o una linea
# esotica puo' legittimamente non avere NESSUNA offerta a book, e farci scattare
# l'allarme lo terrebbe acceso in permanenza - cioe' lo spegnerebbe, perche' un
# allarme sempre acceso il trader impara a ignorarlo. Restano contate in
# ``stream_mercati_senza_quote``, che e' un FATTO, non un allarme.
_KIND_CORE = (None, "cs", "ht")
# 17/09 - FLUMINE NON DEVE STARE NEL PROCESSO DEL FEED.
# ``flumine/__init__.py:13`` sostituisce ``bettingresources.RunnerBookEX`` con
# una classe che lascia i livelli del ladder come dizionari: da quel momento
# ``scanner.best_price`` leggeva ``None`` su OGNI prezzo, da stream e da REST.
# E' la causa del blackout del 17/09. La causa e' tolta alla radice
# (``stream/scalper/hazard_atlas.py`` + import pigro nel package) e la lettura
# regge entrambe le forme, ma se flumine ricompare qui dentro bisogna SAPERLO:
# e' un import che non ci deve essere, e costa CPU e memoria a un servizio di
# feed.
_FLUMINE = "flumine"
# quanti mercati senza quote si elencano nello stato (il conteggio e' sempre
# intero): la riga di stato non deve diventare un registro
_SENZA_QUOTE_ELENCO_MAX = 30


def _pre_ko_usabile(ev: Dict[str, Any]) -> bool:
    """Il riferimento pre-partita dell'evento e' completo PER IL SUO SPORT:
    tripla 1X2 nel calcio, coppia p1/p2 nel tennis (Q12, 25/09)."""
    pre = ev.get("pre_ko")
    if ev.get("sport") == "tennis":
        return scan_db.is_usable_pre_ko_tennis(pre)
    return scan_db.is_usable_pre_ko(pre)


def _pre_ko_ou_hours() -> float:
    raw = (os.getenv(_PRE_KO_OU_ENV) or "").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def _opportunities_enabled() -> bool:
    """Flag da env. Variabile VUOTA = default (spento): mai trattarla come "settata"."""
    raw = (os.getenv(_OPPORTUNITIES_ENV) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _market_type_from_name(market_name: Optional[str]) -> Optional[str]:
    """Fallback: tipo di mercato dal NOME quando la MARKET_DESCRIPTION manca.
    'Over/Under 2.5 Goals' → OVER_UNDER_25, 'Both teams to score?' → BTTS,
    'Half Time' → HALF_TIME."""
    n = (market_name or "").strip().lower()
    if not n:
        return None
    if "both teams" in n:
        return scanner.BTTS_MARKET_TYPE
    if n.startswith("half time") and "score" not in n:
        return scanner.HT_RESULT_MARKET_TYPE
    m = re.search(r"(\d+)\.(\d)", n)
    if m and "over" in n and "under" in n:
        return f"OVER_UNDER_{m.group(1)}{m.group(2)}"
    return None


def _catalogue_window_iso() -> "tuple[str, str]":
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=_CATALOGUE_PAST_H)
    end = now + timedelta(hours=_CATALOGUE_AHEAD_H)
    return start.isoformat(), end.isoformat()


class SportState:
    def __init__(self) -> None:
        self.catalogue_ts = 0.0
        # ultimo TENTATIVO di catalogo fallito (backoff _CATALOGUE_RETRY_SEC);
        # separato da catalogue_ts, che resta "0 = mai caricato" per lo stream
        self.catalogue_fail_ts = -1e9
        self.books_ts = 0.0
        # meta per evento: market_id, event_name, open_date, competition, sides
        self.metas: Dict[str, Dict[str, Any]] = {}


class Scanner:
    def __init__(self, api_client: Any, dry: bool, use_stream: bool = False,
                 orologio: Optional[Any] = None,
                 canale: Optional[bool] = None) -> None:
        self.client = api_client
        self.dry = dry
        # OROLOGIO INIETTABILE — esiste SOLO per il banco di prova (replay sulle
        # registrazioni), dove "adesso" e' il publish time del tick e non l'ora
        # del PC: con l'orologio del PC una registrazione di giugno risulterebbe
        # vecchia di mesi e ogni riga nascerebbe gia' stantia.
        # None (produzione) = time.time()/time.monotonic()/scanner.now_iso(),
        # cioe' esattamente il comportamento di prima. Deve restituire EPOCH
        # SECONDI (float), la stessa unita' di time.time().
        self.orologio = orologio
        self.sports = {name: SportState() for name in _SPORTS}
        # stato runtime per evento (inplay, quote, punteggio, pre_ko, cs, …)
        self.events: Dict[str, Dict[str, Any]] = {}
        # QUOTE IN TEMPO REALE: Exchange Stream API ufficiale su un POOL di
        # connessioni (sharding ≤180 mercati/connessione, vedi stream.py); il poll
        # REST resta come fallback per i mercati che il pool non copre.
        self.stream: Optional[MarketStreamPool] = (
            MarketStreamPool(api_client) if use_stream else None
        )
        # F1 (18/09) - CANALE LOCALE, in sola pubblicazione. Nasce solo col
        # pool stream acceso (cioe' nel servizio vero): nel BANCO di replay
        # ``use_stream=False`` e il canale non esiste proprio, cosi' la
        # certificazione misura la stessa identica condotta di prima.
        # ``canale=None`` (il caso normale) legge l'interruttore di fase; un
        # booleano esplicito serve ai test, che non possono contare su un
        # valore d'ambiente.
        canale_voluto = _CANALE_ACCESO if canale is None else bool(canale)
        self.canale: Optional[Any] = (
            self._avvia_canale() if (use_stream and canale_voluto) else None
        )
        # indice market_id → (sport, meta) per applicare i book (stream E rest)
        self.market_meta: Dict[str, "tuple[str, Dict[str, Any]]"] = {}
        # 17/09 - QUANDO OGNI MERCATO HA CONSEGNATO L'ULTIMO PREZZO.
        # ``stream_price_mono``: solo dallo STREAM, ed e' cio' che decide se un
        # mercato e' coperto o se va al poll REST (un mercato che riceve solo
        # definizioni NON e' coperto). ``price_mono``: da QUALSIASI fonte, ed e'
        # cio' su cui si denuncia "quote assenti" nello stato.
        # ``rilevante_da_mono``: da quando un mercato e' rilevante, per dare
        # un'eta' anche a chi un prezzo non l'ha mai avuto.
        self.stream_price_mono: Dict[str, float] = {}
        self.price_mono: Dict[str, float] = {}
        self.rilevante_da_mono: Dict[str, float] = {}
        # book SENZA un solo prezzo, per mercato: non sono un aggiornamento di
        # quote e non devono toccare ``odds``/``odds_ts_ms``. Contarli e' l'unico
        # modo per accorgersene dal vivo.
        self.book_vuoti: Dict[str, int] = {}
        self.book_vuoti_rest = 0
        # mercati rilevanti senza un prezzo da oltre _SENZA_QUOTE_MAX_AGE_SEC
        # (aggiornato a ogni tick) e da quanto dura il piu' vecchio: e' il FATTO,
        # comprese le linee a gol illiquide
        self.mercati_senza_quote: List[str] = []
        self.senza_quote_eta_s: float = 0.0
        # i soli mercati CORE senza quote: e' l'ALLARME (last_error, WARNING,
        # badge REST). Sottoinsieme del precedente.
        self.mercati_allarme: List[str] = []
        self.allarme_eta_s: float = 0.0
        # flumine caricato nel processo: si dice UNA volta nel log e sempre
        # nello stato (vedi _FLUMINE)
        self.flumine_detto = False
        # throttle di pubblicazione per-evento (solo cambi di QUOTE; i cambi
        # critici — gol, set, stato mercato — passano subito: written_crit)
        self.last_pub_mono: Dict[str, float] = {}
        self.written_crit: Dict[str, str] = {}
        self.scores_ts = 0.0
        self.timelines_ts = 0.0
        self.orphan_purge_ts = -1e9  # prima pulizia subito al primo publish
        # CERT. 13/09 — reidratazione del riferimento 1X2 pre-KO dal DB.
        # ``pre_ko`` viveva SOLO qui dentro: a ogni riavvio (app chiusa, crash +
        # watchdog, modifica al codice) si perdeva per tutte le partite gia' in
        # corso, e BASE e PUNTA non potevano piu' scattare per il resto della
        # giornata (ESATTO non usa ``pre_ko``: era l'unica a sopravvivere).
        # Il dato era gia' su ``safe_strategy_scan.payload.pre_ko``: adesso lo si
        # rilegge PRIMA del primo publish, che altrimenti lo sovrascrive con None.
        # Un solo tentativo per evento, best-effort, mai nel percorso caldo.
        self.pre_ko_tried: set = set()
        # D5 (25/09): SCHEDA DB della fixture abbinata (scontri diretti, forze
        # attacco/difesa, gol subiti, round): letture leggere e dichiarate in
        # `selezione.SchedeFixture`. Si aggiorna SOLO nel `tick` del run vero
        # (`hydrate_schede`): `build_rows` legge la cache e basta, quindi il
        # banco di replay (che chiama `build_rows`) non tocca mai il DB.
        self.schede = _selezione.SchedeFixture(
            leggi_finestra=scan_db.fixtures_window,
            leggi_schede=scan_db.load_schede_fixture,
            leggi_round=scan_db.load_round_fixture,
        )
        # thread punteggi (run persistente): None = poll dentro al tick
        self.score_worker: Optional["ScoreFeedWorker"] = None
        self.cs_catalogue_ts = 0.0
        self.ht_catalogue_ts = 0.0
        self.status_ts = 0.0
        self.keepalive_ts = time.monotonic()
        # CERT. 14/09 - quanto dura il giro e dove se ne va il tempo.
        # Finche' la pubblicazione dei prezzi sta dentro un giro lento, una
        # pagina che scrive "tempo reale" al trader gli mente.
        self.crono = Cronometro()
        self.written_sig: Dict[str, str] = {}
        self.last_error: Optional[str] = None
        self.started_at = scanner.now_iso()
        # cache mercati Correct Score: event_id → {market_id, runners}
        self.cs_markets: Dict[str, Dict[str, Any]] = {}
        # HALF TIME SCORE dei candidati 1T (Omega v2): stesso ciclo di vita del CS
        self.ht_markets: Dict[str, Dict[str, Any]] = {}
        # mercati a gol del motore OPPORTUNITA' (Over/Under, Gol/NoGol, 1X2 1T):
        # event_id → {market_id: {market_id, market_type, line, names}}
        self.opp_markets: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.opp_catalogue_ts = 0.0
        # eventi con il catalogo opportunità COMPLETO (tutte le linee): un evento
        # entrato dal ramo pre-KO (solo 3.5/4.5) va completato quando va in-play
        self.opp_full_eids: set = set()
        # ramo pre-KO O/U (Mike): ore dal KO; 0 = spento. Oltre la finestra del
        # catalogo MATCH_ODDS (+14h) non c'e' nulla da candidare: lo si dice
        self.pre_ko_ou_hours: float = _pre_ko_ou_hours()
        if self.pre_ko_ou_hours > _CATALOGUE_AHEAD_H:
            logger.warning("[safe-scan] %s=%.1f oltre la finestra catalogo (+%dh): effetto limitato a %dh",
                           _PRE_KO_OU_ENV, self.pre_ko_ou_hours, _CATALOGUE_AHEAD_H, _CATALOGUE_AHEAD_H)
        self.pre_ko_catalogue_ts = 0.0
        # modello opportunità (puro): atlante hazard caricato una volta sola
        self._opp_model: Optional[Any] = None
        self._opp_atlas_loaded = False
        # partite SEGUITE da Mike (mike_events non terminali): esenti dal tetto
        # dei 20 eventi e con le linee 3.5/4.5 sempre vive (audit 11/09 C1/C2).
        # Cache di 10 s: una query leggera, mai nel percorso caldo dello stream.
        # LISTA, non insieme: l'ordine (soldi a rischio decrescente) e' un dato
        self._mike_followed_ids: List[str] = []
        self._mike_followed_ts: float = -1e9

    # --------------------------------------------------------------- orologio
    # Tre letture dell'ora, tutte incanalate qui: senza orologio iniettato
    # rispondono esattamente come prima (time.time / time.monotonic / now_iso).
    def _ora(self) -> float:
        """Epoch secondi ("quando e' successo": ts_ms, seen_ms, odds_ts_ms)."""
        return time.time() if self.orologio is None else float(self.orologio())

    def _ora_mono(self) -> float:
        """Orologio MONOTONO (solo differenze: throttle di pubblicazione)."""
        return time.monotonic() if self.orologio is None else float(self.orologio())

    def _ora_iso(self) -> str:
        """``updated_at`` della riga di scan e ``captured_at`` del pre-KO."""
        if self.orologio is None:
            return scanner.now_iso()
        return datetime.fromtimestamp(float(self.orologio()), tz=timezone.utc).isoformat()

    # ------------------------------------------------------------- catalogo MO
    def refresh_catalogue(self, sport: str) -> None:
        from betfairlightweight import filters

        st = self.sports[sport]
        frm, to = _catalogue_window_iso()
        cats = self.client.betting.list_market_catalogue(
            filter=filters.market_filter(
                event_type_ids=[_SPORTS[sport]],
                market_type_codes=["MATCH_ODDS"],
                market_start_time={"from": frm, "to": to},
            ),
            market_projection=[
                "EVENT", "COMPETITION", "MARKET_START_TIME", "RUNNER_DESCRIPTION",
            ],
            sort="FIRST_TO_START",
            max_results=_MAX_MARKETS,
        )
        metas: Dict[str, Dict[str, Any]] = {}
        for c in cats or []:
            event = getattr(c, "event", None)
            event_id = getattr(event, "id", None)
            market_id = getattr(c, "market_id", None)
            if not event_id or not market_id:
                continue
            runners = [
                {
                    "selection_id": getattr(r, "selection_id", None),
                    "name": getattr(r, "runner_name", None),
                    "sort_priority": getattr(r, "sort_priority", None),
                }
                for r in (getattr(c, "runners", None) or [])
            ]
            start = getattr(c, "market_start_time", None)
            comp = getattr(c, "competition", None)
            metas[str(event_id)] = {
                "event_id": str(event_id),
                "market_id": market_id,
                "event_name": getattr(event, "name", None),
                "open_date": start.isoformat() if hasattr(start, "isoformat") else start,
                "competition": getattr(comp, "name", None),
                "runners": runners,
                "sides": (
                    scanner.selection_sides(runners)
                    if sport == "calcio"
                    else scanner.tennis_sides(runners)
                ),
            }
        st.metas = metas
        st.catalogue_ts = time.monotonic()
        self._rebuild_market_index()
        logger.info("[safe-scan] catalogo %s: %d eventi oggi", sport, len(metas))

    def _rebuild_market_index(self) -> None:
        """Indice market_id → (sport, meta) su tutto il catalogo MATCH_ODDS più i
        mercati CORRECT_SCORE già risolti (meta con kind='cs')."""
        idx: Dict[str, "tuple[str, Dict[str, Any]]"] = {}
        for sport, st in self.sports.items():
            for meta in st.metas.values():
                idx[meta["market_id"]] = (sport, meta)
        for kind, store in (("cs", self.cs_markets), ("ht", self.ht_markets)):
            for eid, mk in store.items():
                idx[mk["market_id"]] = ("calcio", {
                    "event_id": eid, "market_id": mk["market_id"], "kind": kind, "names": mk["names"],
                })
        for eid, markets in self.opp_markets.items():
            for mid, mk in markets.items():
                idx[mid] = ("calcio", {
                    "event_id": eid, "market_id": mid, "kind": "opp",
                    "market_type": mk.get("market_type"), "line": mk.get("line"),
                    "names": mk.get("names") or {},
                })
        self.market_meta = idx

    def _aggiorna_copertura(self, now_mono: float,
                            rilevanti: List[str],
                            now: Optional[datetime] = None) -> "tuple[set, List[str]]":
        """Chi e' COPERTO dallo stream e chi e' SENZA QUOTE. 17/09.

        ``coperti``: mercati di uno shard che consegna book E che hanno dato un
        prezzo DALLO STREAM da meno di ``_STREAM_PRICE_MAX_AGE_SEC``. Tutti gli
        altri vanno al poll REST, anche se il socket e' sanissimo: e' il buco
        che il 17/09 e' rimasto aperto per ore.

        ``senza_quote``: mercati rilevanti che da oltre
        ``_SENZA_QUOTE_MAX_AGE_SEC`` non hanno un prezzo da NESSUNA fonte. E'
        quello che ``last_error`` deve dire al trader.

        Un mercato CHIUSO (o non piu' rilevante) non entra in nessuna delle due
        liste: un mercato finito non manca di quote, e' finito (17/09 sera,
        Half Time Score ``1.262446903``, CLOSED al 45' con la partita ancora
        OPEN — vedi ``_mercato_attivo``).
        """
        now = now or datetime.now(timezone.utc)
        rilevanti_set = set(rilevanti)
        coperti: set = set()
        if self.stream is not None:
            for mid in self.stream.covered_ids():
                ts = self.stream_price_mono.get(mid)
                if ts is not None and now_mono - ts <= _STREAM_PRICE_MAX_AGE_SEC:
                    coperti.add(mid)
        # un mercato che smette di essere rilevante non deve restare a
        # invecchiare nelle mappe (memoria e falsi allarmi)
        for mappa in (self.stream_price_mono, self.price_mono, self.rilevante_da_mono):
            for mid in [m for m in mappa if m not in rilevanti_set]:
                mappa.pop(mid, None)
        senza: List["tuple[float, str]"] = []
        allarme: List["tuple[float, str]"] = []
        for mid in rilevanti:
            if not self._mercato_attivo(mid, now):
                # CHIUSO (o non piu' rilevante sul SUO stato): fuori da
                # entrambe le liste E dalle mappe di copertura, subito - non
                # deve invecchiare fino al prossimo giro in cui sparisse da
                # ``rilevanti`` (che e' esattamente cio' che non e' successo
                # il 17/09: il market_id restava candidato).
                for mappa in (self.stream_price_mono, self.price_mono, self.rilevante_da_mono):
                    mappa.pop(mid, None)
                continue
            base = self.price_mono.get(mid)
            if base is None:
                base = self.rilevante_da_mono.setdefault(mid, now_mono)
            eta = now_mono - base
            # (a) nessun prezzo da NESSUNA fonte (ne' stream ne' REST) da > 30 s
            senza_da_nessuno = eta > _SENZA_QUOTE_MAX_AGE_SEC
            # (b) aveva prezzi DALLO STREAM e li ha persi da > 60 s, e il REST
            #     non lo sta coprendo. In pratica (a) lo prende gia' prima; resta
            #     esplicito perche' e' la condizione dell'incidente del 17/09 e
            #     non deve dipendere dalla soglia dell'altra.
            ts_stream = self.stream_price_mono.get(mid)
            perso_dallo_stream = (
                ts_stream is not None
                and now_mono - ts_stream > _STREAM_PERSO_MAX_AGE_SEC
                and senza_da_nessuno
            )
            if senza_da_nessuno:
                senza.append((eta, mid))
            if (senza_da_nessuno or perso_dallo_stream) and self._e_core(mid):
                allarme.append((eta, mid))
        senza.sort(reverse=True)
        allarme.sort(reverse=True)
        self.senza_quote_eta_s = senza[0][0] if senza else 0.0
        self.mercati_senza_quote = [mid for _, mid in senza]
        self.allarme_eta_s = allarme[0][0] if allarme else 0.0
        self.mercati_allarme = [mid for _, mid in allarme]
        return coperti, self.mercati_allarme

    def _e_core(self, market_id: str) -> bool:
        """E' un mercato CORE (MATCH_ODDS, Correct Score, Half Time Score)?

        Solo questi fanno ALLARME: sono quelli su cui si apre, si esce e ci si
        copre. Le linee a gol senza offerte sono un fatto normale del mercato.
        """
        trovato = self.market_meta.get(market_id)
        if not trovato:
            return False
        return (trovato[1].get("kind") or None) in _KIND_CORE

    def _mercato_attivo(self, market_id: str, now: datetime) -> bool:
        """Il mercato e' ancora APERTO e rilevante: solo su questi ha senso
        parlare di "quote assenti". 17/09 sera.

        Un Correct Score o un Half Time Score puo' chiudere (fine 1T, fine
        partita) mentre il MATCH_ODDS dell'evento resta OPEN — la partita
        continua. Guardare ``ev["mo_status"]`` (lo stato del MATCH_ODDS) per
        decidere se il mercato CS/HT e' finito e' la domanda sbagliata: va
        guardato lo stato del SUO blocco (``ev["cs"]["status"]``/
        ``ev["ht"]["status"]``), quello che ``_apply_cs_book`` aggiorna a ogni
        book, anche vuoto. E' esattamente il caso del mercato Half Time Score
        ``1.262446903``: CLOSED da Betfair al 45', rimasto 509 s in allarme
        perche' nessuno controllava lo stato del BLOCCO, solo quello (OPEN,
        la partita proseguiva) del MATCH_ODDS.
        """
        trovato = self.market_meta.get(market_id)
        if not trovato:
            return False
        _, meta = trovato
        ev = self.events.get(meta.get("event_id"))
        if ev is None:
            return False
        kind = meta.get("kind")
        if kind in ("cs", "ht", "opp"):
            blocco = ev.get(kind) if kind != "opp" else (ev.get("opp") or {}).get(market_id)
            stato = blocco.get("status") if isinstance(blocco, dict) else None
            return stato != "CLOSED"
        # MATCH_ODDS: CLOSED e' gia' un fatto diretto; ``is_relevant_market``
        # copre anche "non piu' rilevante" (KO passato, in-play sconosciuto).
        return scanner.is_relevant_market(
            ev.get("inplay"), ev.get("mo_status"), meta.get("open_date"), now)

    def flumine_caricato(self) -> bool:
        """``flumine`` e' finito nel processo del feed? (non ci deve stare)"""
        return _FLUMINE in sys.modules

    def controlla_flumine(self) -> Optional[str]:
        """Se flumine e' stato caricato lo si denuncia: WARNING una volta sola,
        poi resta nello stato finche' dura (cioe' per sempre: non si scarica)."""
        if not self.flumine_caricato():
            return None
        if not self.flumine_detto:
            self.flumine_detto = True
            logger.warning(
                "[safe-scan] FLUMINE CARICATO NEL PROCESSO DEL FEED: sostituisce "
                "RunnerBookEX e il ladder arriva come dizionari. E' l'incidente "
                "del 17/09: trovare l'import e toglierlo."
            )
        return "flumine caricato nel processo del feed"

    def allarme_quote(self) -> Optional[str]:
        """Il messaggio di ``last_error`` quando mancano le quote sui mercati
        CORE (None = tutto a posto). Il 17/09 ``last_error`` era null mentre il
        feed era morto da ore: il badge STREAM verde ha reso il blackout
        invisibile."""
        n = len(self.mercati_allarme)
        if not n:
            return None
        return f"quote assenti da {self.allarme_eta_s:.0f}s su {n} mercati"

    def relevant_market_ids(self, sport: str, now: datetime) -> List[str]:
        """Mercati del sport che servono QUOTE adesso (scanner.is_relevant_market),
        ordinati per priorità (in-play prima, poi per KO). Il resto del catalogo
        (KO lontano) non consuma né stream né REST."""
        return [mid for _, mid in self.ranked_relevant_markets(sport, now)]

    def ranked_relevant_markets(self, sport: str, now: datetime) -> List["tuple[tuple, str]"]:
        """Come ``relevant_market_ids`` ma con la CHIAVE di priorità di ogni
        mercato (core: ``scanner.rank_key``; a gol: ``scanner.opp_rank_key``,
        con il tier 1.5 delle linee di Mike). E' l'UNICA fonte dell'ordine:
        lo stream (``refresh_stream_set``) la riusa tale e quale — prima
        ricalcolava un tier 2 uniforme e le linee di una posizione Mike
        potevano essere troncate dallo shard (audit H5)."""
        out: List["tuple[tuple, str]"] = []
        for eid, meta in self.sports[sport].metas.items():
            ev = self.events.get(eid)
            inplay: Optional[bool] = None if ev is None else bool(ev.get("inplay"))
            status = None if ev is None else ev.get("mo_status")
            if scanner.is_relevant_market(inplay, status, meta.get("open_date"), now):
                out.append((scanner.rank_key(inplay, meta.get("open_date")), meta["market_id"]))
            # CORRECT SCORE dei candidati (calcio in-play dal 30', ≤3 gol/lato):
            # stessa priorità del suo MATCH_ODDS in-play → stream, REST se scoperto
            if sport == "calcio" and inplay and eid in self.cs_markets and status != "CLOSED":
                if scanner.is_cs_candidate(ev.get("minute"), ev.get("score_home"), ev.get("score_away")):
                    out.append((scanner.rank_key(True, meta.get("open_date")), self.cs_markets[eid]["market_id"]))
            # HALF TIME SCORE dei candidati 1T (Omega v2): stessa priorità
            if sport == "calcio" and inplay and eid in self.ht_markets and status != "CLOSED":
                if scanner.is_ht_candidate(ev.get("minute")):
                    out.append((scanner.rank_key(True, meta.get("open_date")), self.ht_markets[eid]["market_id"]))
        if sport == "calcio":
            out.extend(self._opp_ranked_market_ids(now))
        out.sort()
        return out

    def _opp_ranked_market_ids(self, now: Optional[datetime] = None) -> List["tuple[tuple, str]"]:
        """Mercati a gol del motore opportunità da tenere sotto quote ADESSO.

        Priorità SEMPRE dopo i mercati core (``scanner.opp_rank_key`` tier 2, con
        i minuti più avanzati per primi): se il pool stream è pieno restano fuori
        loro, mai un MATCH_ODDS o un Correct Score. Solo le linee ancora indecise.
        """
        out: List["tuple[tuple, str]"] = []
        followed = self._mike_followed()
        cands = self.opp_candidates()
        # H4: gli eventi che entrano SOLO perché seguiti da Mike portano nel pool
        # le due linee 3.5/4.5 e NIENTE altro (gli altri ~8 mercati a gol di
        # quell'evento restano soggetti al tetto normale).
        base = set(scanner.select_opp_candidates(cands, followed=()))
        for eid in cands:
            ev = self.events.get(eid) or {}
            if ev.get("mo_status") == "CLOSED":
                continue
            meta = self.sports["calcio"].metas.get(eid) or {}
            is_mike = str(eid) in followed
            only_mike = is_mike and eid not in base
            for mid, mk in (self.opp_markets.get(eid) or {}).items():
                mtype = str(mk.get("market_type") or "").upper()
                mike_line = is_mike and mtype in scanner.MIKE_OU_MARKET_TYPES
                if only_mike and not mike_line:
                    continue
                if scanner.is_opp_market_live(
                    mk.get("market_type"), mk.get("line"), ev.get("minute"),
                    ev.get("score_home"), ev.get("score_away"), mike=is_mike,
                ):
                    # H5: le linee di Mike hanno priorità sopra gli altri mercati
                    # opportunità (mai troncate dallo shard dello stream)
                    out.append((scanner.opp_rank_key(ev.get("minute"), meta.get("open_date"),
                                                     mike=mike_line), mid))
        # ramo pre-KO O/U (Mike): SOLO le due linee, tier 2 con minuto 0 → dopo
        # ogni mercato in-play; se il pool è pieno escono per primi loro
        for eid in self.pre_ko_ou_candidates(now):
            meta = self.sports["calcio"].metas.get(eid) or {}
            key = scanner.opp_rank_key(None, meta.get("open_date"))
            for mid, mk in (self.opp_markets.get(eid) or {}).items():
                if scanner.is_opp_market_live(mk.get("market_type"), mk.get("line"),
                                              None, None, None, pre_ko=True):
                    out.append((key, mid))
        return out

    def pre_ko_ou_candidates(self, now: Optional[datetime] = None) -> List[str]:
        """Eventi calcio NON iniziati con KO entro ``pre_ko_ou_hours`` (ramo Mike).
        Lista vuota se il ramo è spento: nessun effetto sul feed."""
        if self.pre_ko_ou_hours <= 0.0:
            return []
        now = now or datetime.now(timezone.utc)
        out: List[str] = []
        for eid, meta in self.sports["calcio"].metas.items():
            ev = self.events.get(eid) or {}
            if scanner.is_pre_ko_ou_candidate(
                bool(ev.get("inplay")), ev.get("mo_status"), meta.get("open_date"),
                now, self.pre_ko_ou_hours,
            ):
                out.append(eid)
        return out

    def _is_pre_ko_ou_event(self, eid: Optional[str], ev: Dict[str, Any],
                            now: Optional[datetime] = None) -> bool:
        """L'evento è nel ramo pre-KO O/U adesso (non iniziato, KO in finestra)?"""
        if not eid or self.pre_ko_ou_hours <= 0.0 or ev.get("inplay"):
            return False
        meta = self.sports["calcio"].metas.get(str(eid)) or {}
        return scanner.is_pre_ko_ou_candidate(
            bool(ev.get("inplay")), ev.get("mo_status"), meta.get("open_date"),
            now or datetime.now(timezone.utc), self.pre_ko_ou_hours,
        )

    def refresh_stream_set(self, now: datetime,
                           per_sport: Optional[Dict[str, List["tuple[tuple, str]"]]] = None) -> None:
        """Subscription stream = mercati rilevanti di TUTTI gli sport insieme.

        Parte SOLO quando tutti gli sport hanno un catalogo caricato (warm-up in
        main): senza questa guardia lo stream partiva col solo calcio e il
        throttle anti-resubscribe teneva fuori il tennis per minuti (visto in
        collaudo). Va chiamata a ogni tick: il set cambia quando un evento va
        in-play, entra in finestra pre-KO o chiude — non solo al refresh catalogo.
        """
        if self.stream is None:
            return
        if not all(st.catalogue_ts > 0.0 for st in self.sports.values()):
            return
        # STESSA priorità di ranked_relevant_markets (core tier 0/1, linee Mike
        # 1.5, altri mercati a gol 2): prima qui il tier veniva ricalcolato a 2
        # per ogni mercato a gol e le linee 3.5/4.5 di una posizione Mike
        # potevano essere troncate dallo shard con il pool pieno (audit H5)
        ranked: List["tuple[tuple, str]"] = []
        for sport in self.sports:
            ranked.extend(
                self.ranked_relevant_markets(sport, now) if per_sport is None
                else per_sport.get(sport, [])
            )
        ranked.sort()
        ids = [mid for _, mid in ranked]
        if ids:
            self.stream.set_markets(ids)

    def _segna_prezzi(self, market_id: Any, dallo_stream: bool) -> None:
        """Questo mercato ha appena consegnato un book CON PREZZI."""
        mid = str(market_id)
        ora = time.monotonic()
        self.price_mono[mid] = ora
        if dallo_stream:
            self.stream_price_mono[mid] = ora

    def _segna_book_vuoto(self, market_id: Any, dallo_stream: bool) -> None:
        """Book SENZA un solo prezzo: si conta, non si applica come quota."""
        if dallo_stream:
            mid = str(market_id)
            self.book_vuoti[mid] = self.book_vuoti.get(mid, 0) + 1
        else:
            self.book_vuoti_rest += 1

    def _apply_market_book(self, book: Any, dallo_stream: bool = False) -> None:
        """Applica UN MarketBook (dal poll REST o dallo STREAM) allo stato evento.

        ``dallo_stream`` distingue la FONTE: solo un prezzo arrivato dallo
        stream rende un mercato "coperto" e tiene fermo il poll REST.
        """
        found = self.market_meta.get(getattr(book, "market_id", None))
        if not found:
            return
        sport, meta = found
        if meta.get("kind") in ("cs", "ht"):
            self._apply_cs_book(meta, book, dallo_stream)
            return
        if meta.get("kind") == "opp":
            self._apply_opp_book(meta, book, dallo_stream)
            return
        pairs: Dict[int, Dict[str, Any]] = {}
        for r in getattr(book, "runners", None) or []:
            sid = getattr(r, "selection_id", None)
            if sid is None:
                continue
            # selection_id + LTP nel pair: la board del desktop (board_worker) li
            # legge da QUI invece di rifare il listMarketBook via REST
            pairs[int(sid)] = {
                **scanner.price_pair(getattr(r, "ex", None)),
                "selection_id": int(sid),
                "ltp": scanner.num_or_none(getattr(r, "last_price_traded", None)),
            }
        sides = meta["sides"]
        odds = {
            side: pairs.get(sid) if sid is not None else None
            for side, sid in sides.items()
        }
        ev = self.events.setdefault(meta["event_id"], {})
        ev["sport"] = sport
        # la DEFINIZIONE si applica SEMPRE: e' l'unica cosa che un book di sola
        # marketDefinition porta di sicuro, ed e' informazione buona
        ev["inplay"] = bool(getattr(book, "inplay", False))
        ev["mo_status"] = getattr(book, "status", None)
        ev["mo_total_matched"] = scanner.num_or_none(getattr(book, "total_matched", None))
        # F0 (18/09) - BET DELAY DI QUESTO MERCATO, dal ``marketDefinition`` che
        # il book ha gia' in mano: zero chiamate, zero migrazioni, chiave
        # ADDITIVA nel payload. Prima lo leggeva solo ``_apply_opp_book`` (i
        # mercati a gol del calcio, per Mike): i blocchi MATCH_ODDS e TUTTO il
        # tennis passavano senza, quindi il bot non sapeva a quale ritardo era
        # soggetto e la certificazione doveva ASSUMERE 3 s invece di leggerlo.
        # STA SOPRA LA GUARDIA ``has_any_price`` DI PROPOSITO: viene dalla
        # DEFINIZIONE del mercato, non dai prezzi, ed e' informazione buona
        # anche su un book che di prezzi non ne porta nemmeno uno - esattamente
        # come ``inplay``, ``mo_status`` e ``mo_total_matched`` qui sopra.
        # Assente non e' zero: un ``bet_delay: 0`` inventato direbbe "nessun
        # ritardo" a chi non lo sa, quindi si scrive solo quando c'e' davvero.
        bd = scanner.num_or_none(getattr(book, "bet_delay", None))
        if bd is not None:
            ev["bet_delay"] = int(bd)
        ora_ms = int(self._ora() * 1000)
        # 17/09 - UN BOOK SENZA PREZZI NON E' UN AGGIORNAMENTO DI QUOTE.
        # betfairlightweight, su un messaggio di sola ``marketDefinition``, crea
        # i runner dalla definizione (selection_id e status presenti) con le
        # scalette VUOTE e pubblica comunque il MarketBook
        # (streaming/cache.py:314-351, streaming/stream.py:211-215).
        # Applicarlo cancellava le quote buone E faceva avanzare ``odds_ts_ms``,
        # cioe' dichiarava fresche quote che non esistevano: le uscite finivano
        # in ``prezzi_non_nel_feed`` per sempre e nessuno lo vedeva.
        if not scanner.has_any_price(pairs):
            # il blocco nasce UNA volta sola, perche' la riga dica onestamente
            # "quote assenti" - ma senza timestamp di prezzo
            ev.setdefault("odds", odds)
            ev["odds_vuote_ms"] = ora_ms
            self._segna_book_vuoto(meta["market_id"], dallo_stream)
            return
        # ts dell'ULTIMO CAMBIO delle quote 1X2 (non dell'ultimo poll): il motore
        # opportunità penalizza i prezzi fermi, il write-on-change resta pulito
        if ev.get("odds") != odds:
            ev["odds_ts_ms"] = ora_ms
            # F0 (18/09) - accanto al NOSTRO istante, quello di BETFAIR: il
            # ``publishTime`` del book che ha portato questo cambio. Fra i due
            # c'e' il conflate (1 s) piu' la cadenza del tick, cioe' il salto
            # che nessuno poteva misurare perche' mancava il campo. Chiave
            # ADDITIVA: ``odds_ts_ms`` resta esattamente com'era.
            # STA QUI SOTTO, DENTRO LA GUARDIA, PERCHE' E' UN ISTANTE DI
            # PREZZO: sopra la guardia un book di sola ``marketDefinition``
            # farebbe avanzare l'istante di un prezzo che non esiste, cioe'
            # esattamente l'incidente del 17/09 con un campo in piu'.
            # ATTENZIONE: e' l'orologio di BETFAIR, non il nostro. Si sottrae
            # solo passando da ``Betfair.stream.orologio``.
            ev["odds_pt_ms"] = scanner.publish_time_ms(book)
        ev["odds"] = odds
        ev["odds_seen_ms"] = ora_ms          # ultima osservazione CON prezzi
        self._segna_prezzi(meta["market_id"], dallo_stream)
        # riferimento pre-KO: aggiorna pre-KO, congela al primo in-play
        # Q12 (25/09): anche il tennis ha il suo riferimento pre-partita
        # congelato, con lo stesso schema (coppia p1/p2 invece della tripla).
        _congela = (scanner.freeze_pre_ko if sport == "calcio"
                    else scanner.freeze_pre_ko_tennis)
        ev["pre_ko"] = _congela(
            ev.get("pre_ko"), ev["inplay"], odds,
            # in PRODUZIONE si passa None e `freeze_pre_ko` chiama `now_iso()`
            # solo quando il riferimento lo costruisce davvero: questo e' il
            # percorso caldo dello stream (migliaia di book al minuto) e non ci
            # si aggiunge una formattazione di data per ogni book.
            adesso_iso=(None if self.orologio is None else self._ora_iso()),
        )

    def _apply_cs_book(self, meta: Dict[str, Any], book: Any,
                       dallo_stream: bool = False) -> None:
        """MarketBook CORRECT_SCORE (stream o REST) → blocco `cs` COMPLETO
        dell'evento (tutte le selezioni con id/nome/prezzi/size/stato runner)."""
        ev = self.events.get(meta["event_id"])
        if ev is None:
            return
        names = meta.get("names") or {}
        selections = [
            {
                "selection_id": getattr(r, "selection_id", None),
                "name": names.get(getattr(r, "selection_id", None)),
                "runner_status": getattr(r, "status", None),
                **scanner.price_pair(getattr(r, "ex", None)),
            }
            for r in getattr(book, "runners", None) or []
        ]
        # 17/09 - stesso difetto del MATCH_ODDS: un book di sola definizione
        # sostituiva il blocco Correct Score/Half Time con uno senza prezzi, ed
        # e' su quello che Omega decide se coprirsi. Si aggiorna SOLO lo stato.
        if not scanner.has_any_price(selections):
            self._segna_book_vuoto(meta["market_id"], dallo_stream)
            blk = ev.get(meta.get("kind") or "cs")
            if isinstance(blk, dict):
                blk["status"] = getattr(book, "status", None)
                blk["inplay"] = bool(getattr(book, "inplay", False))
                return
            # nessun blocco ancora: nasce (onesto, senza prezzi) una volta sola
        else:
            self._segna_prezzi(meta["market_id"], dallo_stream)
        ev[meta.get("kind") or "cs"] = scanner.build_cs_block(
            meta["market_id"], getattr(book, "status", None), selections,
            inplay=bool(getattr(book, "inplay", False)),
            total_matched=scanner.num_or_none(getattr(book, "total_matched", None)),
        )

    def _apply_opp_book(self, meta: Dict[str, Any], book: Any,
                        dallo_stream: bool = False) -> None:
        """MarketBook di un mercato a gol (Over/Under, Gol/NoGol, 1X2 1T) → blocco
        generico nel dizionario `opp` dell'evento (poi diviso in ou/btts/ht_result).

        Il ``ts_ms`` del blocco è il momento dell'ULTIMO CAMBIO reale, non
        dell'ultimo poll: il motore opportunità lo usa per penalizzare i prezzi
        fermi, e il write-on-change non deve riscrivere la riga per un timestamp.
        """
        ev = self.events.get(meta["event_id"])
        if ev is None:
            # ramo pre-KO (Mike): prima del KO il MATCH_ODDS non è in stream e
            # l'evento non è ancora nato dal suo book → nasce qui, dalla linea O/U
            if not self._is_pre_ko_ou_event(meta["event_id"], {}):
                return
            ev = self.events.setdefault(meta["event_id"], {"sport": "calcio", "inplay": False})
        names = meta.get("names") or {}
        selections = [
            {
                "selection_id": getattr(r, "selection_id", None),
                "name": names.get(getattr(r, "selection_id", None)),
                "runner_status": getattr(r, "status", None),
                **scanner.price_pair(getattr(r, "ex", None)),
            }
            for r in getattr(book, "runners", None) or []
        ]
        store = ev.setdefault("opp", {})
        # 17/09 - un book di sola definizione NON sostituisce il blocco a gol:
        # sono le linee su cui Mike si copre e su cui si esce. Si aggiorna solo
        # lo stato del mercato, e il book vuoto si conta.
        if not scanner.has_any_price(selections):
            self._segna_book_vuoto(meta["market_id"], dallo_stream)
            prec = store.get(meta["market_id"])
            if isinstance(prec, dict):
                prec["status"] = getattr(book, "status", None)
                prec["inplay"] = bool(getattr(book, "inplay", False))
                prec["seen_ms"] = int(self._ora() * 1000)
                return
        else:
            self._segna_prezzi(meta["market_id"], dallo_stream)
        blk = scanner.build_market_block(
            meta["market_id"], getattr(book, "status", None), selections,
            inplay=bool(getattr(book, "inplay", False)),
            total_matched=scanner.num_or_none(getattr(book, "total_matched", None)),
            market_type=meta.get("market_type"), line=meta.get("line"),
            bet_delay=scanner.num_or_none(getattr(book, "bet_delay", None)),
        )
        if blk is None:
            return
        prev = store.get(meta["market_id"])
        prev_ts = prev.get("ts_ms") if isinstance(prev, dict) else None
        # i marker ``decided``/``for_mike`` li aggiunge _prune_opp_blocks sul
        # blocco in cache: non sono un cambio di PREZZO. Confrontandoli, ogni
        # book (anche identico) rinfrescava ts_ms e riscriveva la riga a ogni
        # giro per tutte le partite seguite da Mike o con una linea decisa.
        unchanged = (
            isinstance(prev, dict) and prev_ts is not None
            and {k: v for k, v in prev.items() if k not in _OPP_MARKER_KEYS} == blk
        )
        ora_ms = int(self._ora() * 1000)
        blk["ts_ms"] = int(prev_ts) if unchanged else ora_ms
        # CERT. 13/09 — ULTIMA OSSERVAZIONE, distinta dall'ultimo CAMBIO.
        # ``ts_ms`` dice quando il prezzo si e' mosso l'ultima volta; da solo non
        # permette di distinguere "mercato fermo ma sotto osservazione" da
        # "mercato che non guardiamo piu'". Nel secondo caso il blocco resta in
        # cache col PREZZO VECCHIO e viene ripubblicato come se fosse valido:
        # chi ci si copre o ci esce lo fa su un prezzo morto, che e' peggio che
        # non coprirsi. ``seen_ms`` e' il momento dell'ultimo book ricevuto, e
        # sta FUORI dalla firma del write-on-change (``scanner._FUORI_FIRMA``),
        # altrimenti riscriverebbe la riga a ogni poll.
        blk["seen_ms"] = ora_ms
        store[meta["market_id"]] = blk

    # ------------------------------------------------------------- quote (REST)
    def poll_books(self, sport: str, ids: List[str]) -> None:
        """Poll REST EX_BEST_OFFERS dei mercati indicati (chunk 25, peso 125)."""
        from betfairlightweight import filters

        st = self.sports[sport]
        for i in range(0, len(ids), _BOOK_CHUNK):
            chunk = ids[i:i + _BOOK_CHUNK]
            books = self.client.betting.list_market_book(
                market_ids=chunk,
                price_projection=filters.price_projection(price_data=["EX_BEST_OFFERS"]),
            )
            for b in books or []:
                # dallo_stream=False: un prezzo preso via REST NON rende
                # "coperto" il mercato (il REST e' il fallback, non la fonte)
                self._apply_market_book(b)
            time.sleep(_REQ_DELAY)
        st.books_ts = time.monotonic()

    # ------------------------------------------------------------- punteggi IPS
    def _ips_headers(self) -> Dict[str, str]:
        return {
            "X-Application": str(getattr(self.client, "app_key", "") or ""),
            "X-Authentication": str(getattr(self.client, "session_token", "") or ""),
            "Accept": "application/json",
        }

    def _ips_batch(self, chunk: List[str]) -> List["tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]"]:
        """Punteggi + disponibilità media in UNA chiamata IPS `scoresAndBroadcast`
        (stesso servizio non ufficiale di get_scores, stesso endpoint che usa il
        sito Betfair per icone video/animazione; verificato il 09/09 con la nostra
        app key). Ritorna (event_id, state|None, broadcasts|None). Se fallisce,
        fallback al get_scores già collaudato (senza media)."""
        try:
            resp = self.client.session.get(
                _IPS_SB_URL,
                params={
                    "eventIds": ",".join(chunk), "alt": "json",
                    "regionCode": "UK", "locale": "it", "channel": "WEB",
                },
                headers=self._ips_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                out = []
                for rec in data:
                    if not isinstance(rec, dict) or rec.get("eventId") is None:
                        continue
                    state = rec.get("state")
                    bc = rec.get("broadcasts")
                    out.append((
                        str(rec["eventId"]),
                        state if isinstance(state, dict) else None,
                        bc if isinstance(bc, dict) else None,
                    ))
                return out
        except Exception as e:  # noqa: BLE001 - IPS non ufficiale: fallback
            logger.warning("[safe-scan] scoresAndBroadcast KO (%s): fallback get_scores", str(e)[:100])
        results = self.client.in_play_service.get_scores(event_ids=chunk, lightweight=True)
        return [
            (str(rec["eventId"]), rec, None)
            for rec in results or []
            if isinstance(rec, dict) and rec.get("eventId") is not None
        ]

    def poll_scores(self) -> None:
        inplay_ids = [
            eid for eid, ev in self.events.items() if ev.get("inplay")
        ]
        if not inplay_ids:
            self.scores_ts = time.monotonic()
            return
        raw_by_event: Dict[str, Dict[str, Any]] = {}
        for i in range(0, len(inplay_ids), _SCORES_CHUNK):
            chunk = inplay_ids[i:i + _SCORES_CHUNK]
            try:
                batch = self._ips_batch(chunk)
            except Exception as e:  # noqa: BLE001 - IPS non ufficiale: best-effort
                logger.warning("[safe-scan] punteggi IPS KO: %s", str(e)[:120])
                continue
            for eid, state, broadcasts in batch:
                ev = self.events.get(eid)
                if ev is None:
                    continue
                if broadcasts is not None:
                    ev["media"] = scanner.media_flags(broadcasts)
                if state is not None:
                    raw_by_event[eid] = state  # stato assente = punteggio precedente resta
            time.sleep(_IPS_REQ_DELAY)
        for eid, rec in raw_by_event.items():
            self.apply_score_state(eid, rec)
        self.scores_ts = time.monotonic()

    def apply_score_state(self, eid: str, rec: Dict[str, Any]) -> bool:
        """Lo STATO IPS GREZZO di un evento entra nello stato-evento.

        Corpo estratto da ``poll_scores`` senza cambiarne una riga: da qui
        passano sia il poll IPS di produzione sia il banco di prova, che rilegge
        lo stesso identico record dal sidecar della registrazione
        (``<id>.scores.jsonl`` calcio / ``<id>.score.jsonl`` tennis). Un finto
        che ricostruisse "minute/score_home/..." a mano parlerebbe una lingua
        diversa dal vero: qui non c'e' nessun finto, c'e' la funzione vera.
        Torna False se l'evento non esiste ancora (stato assente = nessun
        punteggio, mai un evento inventato).
        """
        ev = self.events.get(eid)
        if ev is None:
            return False
        # FEED UNICO (audit 09/09): lo stato IPS grezzo va nel payload, così i
        # runner calcio/tennis lo parsano coi loro parser di sempre invece di
        # rifare per ogni evento la stessa chiamata (scores/scan_feed.py).
        upd: Dict[str, Any] = {"score_raw": scanner.strip_volatile_state(rec)}
        if ev.get("sport") == "calcio":
            snap = parse_score_dict(eid, rec)
            upd.update(minute=snap.minute, score_home=snap.score_home,
                       score_away=snap.score_away, red_home=snap.red_home,
                       red_away=snap.red_away)
        else:
            ts = parse_tennis_scores([rec], eid)
            if ts is not None:
                upd["sets"] = (
                    {"p1": ts.sets_home, "p2": ts.sets_away}
                    if ts.sets_home is not None and ts.sets_away is not None
                    else None
                )
                upd["games"] = (
                    {"p1": ts.games_home, "p2": ts.games_away}
                    if ts.games_home is not None and ts.games_away is not None
                    else None
                )
        # UN solo update (atomico sotto il GIL): il tick, che pubblica da un
        # altro thread, vede sempre punteggio e stato grezzo COERENTI, mai
        # un gol a metà (score_home nuovo con score_away vecchio)
        ev.update(upd)
        return True

    # ------------------------------------------------------------- timeline IPS
    def poll_timelines(self) -> None:
        """Cronologia eventi (gol/cartellini/kickoff) di TUTTI gli in-play CALCIO
        in batch (``eventTimelines``, chunk 20) ogni _TIMELINE_PERIOD_SEC: prima
        ogni runner la chiedeva PER EVENTO ogni 5s. Il formato è quello di
        ``normalize_timeline`` (identico al provider diretto del runner)."""
        ids = [
            eid for eid, ev in self.events.items()
            if ev.get("sport") == "calcio" and ev.get("inplay")
        ]
        for i in range(0, len(ids), _SCORES_CHUNK):
            chunk = ids[i:i + _SCORES_CHUNK]
            try:
                res = self.client.in_play_service.get_event_timelines(
                    event_ids=[int(e) for e in chunk], lightweight=True
                )
            except Exception as e:  # noqa: BLE001 - endpoint non ufficiale: best-effort
                logger.warning("[safe-scan] eventTimelines KO: %s", str(e)[:120])
                continue
            for rec in res or []:
                if not isinstance(rec, dict) or rec.get("eventId") is None:
                    continue
                ev = self.events.get(str(rec["eventId"]))
                if ev is not None:
                    ev["timeline"] = normalize_timeline(rec)
            time.sleep(_IPS_REQ_DELAY)
        self.timelines_ts = time.monotonic()

    # ------------------------------------------------------------- Correct Score
    def cs_candidates(self) -> List[str]:
        out = []
        for eid, ev in self.events.items():
            if ev.get("sport") != "calcio" or not ev.get("inplay"):
                continue
            if scanner.is_cs_candidate(
                ev.get("minute"), ev.get("score_home"), ev.get("score_away")
            ):
                out.append(eid)
        return out

    def ht_candidates(self) -> List[str]:
        return [eid for eid, ev in self.events.items()
                if ev.get("sport") == "calcio" and ev.get("inplay") and scanner.is_ht_candidate(ev.get("minute"))]

    _MIKE_FOLLOWED_TTL_S = 10.0

    def _mike_followed(self, now_mono: Optional[float] = None) -> List[str]:
        """event_id delle partite seguite da Mike (cache 10 s). In caso di
        errore di lettura resta valida l'ultima lista buona: meglio tenere una
        linea in più che togliere le quote a una posizione aperta.

        CERT. 13/09 — torna una LISTA, non un insieme, e l'ORDINE È UN DATO:
        le partite arrivano ordinate per soldi a rischio decrescente
        (``db.list_mike_followed_event_ids``) e quando il tetto
        ``MIKE_MAX_FOLLOWED`` morde si taglia dal fondo. Conservandole in un
        ``set`` l'ordine si perdeva e il taglio tornava casuale: chi restava
        senza quote — quindi senza copertura e senza uscita — poteva essere la
        partita con più denaro sopra."""
        if self.dry:
            # collaudo/dry: nessuna lettura DB (nessuna posizione Mike può
            # dipendere da uno scanner che non pubblica)
            return list(self._mike_followed_ids)
        t = time.monotonic() if now_mono is None else now_mono
        if t - self._mike_followed_ts >= self._MIKE_FOLLOWED_TTL_S:
            self._mike_followed_ts = t
            ids = scan_db.list_mike_followed_event_ids()
            if ids is not None:
                self._mike_followed_ids = [str(e) for e in ids]
        return list(self._mike_followed_ids)

    def opp_candidates(self) -> List[str]:
        """Eventi calcio in-play (dal 1') per cui tenere sotto quote i mercati a
        gol del motore opportunità, al massimo ``scanner.OPP_MAX_EVENTS``: i posti
        vanno ai minuti più avanzati (probabilità estreme = opportunità vere).
        Le partite seguite da Mike sono ESENTI dal tetto (audit C1) e sono
        candidate anche nei primi istanti di gioco (H7): ``is_opp_candidate``
        chiede ``minute >= 1`` e il ramo pre-KO si spegne appena l'evento va
        in-play → per qualche minuto una posizione aperta restava senza NESSUNA
        linea O/U nel feed e il cash out rispondeva "feed assente"."""
        followed = self._mike_followed()
        cands = [
            (-(ev.get("minute") or 0), eid)
            for eid, ev in self.events.items()
            if ev.get("sport") == "calcio"
            and ev.get("mo_status") != "CLOSED"
            and (scanner.is_opp_candidate(ev.get("inplay"), ev.get("minute"))
                 or (str(eid) in followed and ev.get("inplay")))
        ]
        cands.sort()
        return scanner.select_opp_candidates([eid for _, eid in cands], followed=followed)

    def refresh_opp_catalogue(self, candidates: List[str],
                              market_types: Optional["tuple[str, ...]"] = None) -> None:
        """Catalogo (id + linea + nomi runner) dei mercati a gol per i candidati
        che non ce l'hanno ancora. UNA chiamata per lotto; le QUOTE arrivano poi
        dallo stream (o dal poll REST di fallback) come per il MATCH_ODDS.

        ``market_types`` = None → tutte le linee del motore opportunità (evento
        marcato "completo"); ramo pre-KO Mike → solo ``PRE_KO_OU_MARKET_TYPES``:
        i mercati trovati si AGGIUNGONO a quelli già in cache (mai sostituiti) e
        l'evento verrà completato con le altre linee quando andrà in-play."""
        from betfairlightweight import filters

        full = market_types is None
        types = tuple(market_types) if market_types else scanner.OPP_MARKET_TYPES
        # cache solo per eventi ancora noti: pre-KO l'evento puo' non essere ancora
        # in self.events (nasce dal primo book O/U), ma e' nel catalogo del giorno
        known = {eid for st in self.sports.values() for eid in st.metas}
        for eid in [e for e in self.opp_markets if e not in self.events and e not in known]:
            self.opp_markets.pop(eid, None)
            self.opp_full_eids.discard(eid)
        if full:
            missing = [e for e in candidates if e not in self.opp_full_eids]
        else:
            missing = [e for e in candidates if e not in self.opp_markets]
        if not missing:
            return  # nessuna chiamata: il throttle non parte
        # LIMITE BETFAIR: listMarketCatalogue accetta max_results 1-1000 e oltre
        # risponde INVALID_INPUT_DATA. Col ramo pre-KO acceso su molte ore
        # ``missing`` puo' valere centinaia di partite: senza questo taglio la
        # chiamata falliva e con lei TUTTO il giro dello scanner (nessuna
        # pubblicazione). Si prende quel che ci sta e il resto al giro dopo:
        # il lotto e' gia' "solo i mancanti", quindi converge in pochi giri.
        per_event = max(1, len(types))
        # CERT. 12/09 -- PRIORITA' A CHI HA SOLDI A RISCHIO.
        # Il lotto viene TRONCATO, e chi non ci sta aspetta il giro dopo. Finche'
        # l'ordine era solo "minuti piu' avanzati", una posizione Mike APERTA
        # poteva restare in fondo alla coda: senza i suoi mercati a catalogo non
        # arrivano le quote, e senza quote non c'e' copertura, ne' cash out, ne'
        # uscita. Osservato dal vivo al riavvio delle 21:43: 11 partite con
        # posizioni aperte sono rimaste ~10 minuti senza NESSUNA linea O/U, con
        # 46 allarmi 'feed_line_missing' critici.
        # Le partite seguite da Mike passano davanti: sono poche (tetto
        # MIKE_MAX_FOLLOWED) e non spostano il costo della chiamata.
        missing = scanner.prioritize_followed(missing, self._mike_followed())
        missing = missing[:max(1, _MAX_CATALOGUE_RESULTS // per_event)]
        cats = self.client.betting.list_market_catalogue(
            filter=filters.market_filter(
                event_ids=missing, market_type_codes=list(types),
            ),
            market_projection=["EVENT", "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"],
            max_results=min(_MAX_CATALOGUE_RESULTS, len(missing) * per_event),
        )
        found = {e: {} for e in missing}
        for c in cats or []:
            event_id = getattr(getattr(c, "event", None), "id", None)
            market_id = getattr(c, "market_id", None)
            if not event_id or not market_id or str(event_id) not in found:
                continue
            mtype = getattr(getattr(c, "description", None), "market_type", None)
            if mtype is None:  # proiezione assente: risalgo dal nome del mercato
                mtype = _market_type_from_name(getattr(c, "market_name", None))
            if mtype not in types:
                continue
            found[str(event_id)][market_id] = {
                "market_id": market_id,
                "market_type": mtype,
                "line": scanner.ou_line_from_market_type(mtype),
                "names": {
                    getattr(r, "selection_id", None): getattr(r, "runner_name", None)
                    for r in (getattr(c, "runners", None) or [])
                },
            }
        # anche l'evento senza mercati resta in cache: niente richieste a raffica
        for eid, mk in found.items():
            self.opp_markets.setdefault(eid, {}).update(mk)
        if full:
            self.opp_full_eids.update(found.keys())
        self._rebuild_market_index()

    def refresh_cs_catalogue(self, candidates: List[str]) -> None:
        self._refresh_score_catalogue(self.cs_markets, candidates, "CORRECT_SCORE")
        self.cs_catalogue_ts = time.monotonic()

    def refresh_ht_catalogue(self, candidates: List[str]) -> None:
        self._refresh_score_catalogue(self.ht_markets, candidates, "HALF_TIME_SCORE")
        self.ht_catalogue_ts = time.monotonic()

    def _refresh_score_catalogue(self, store: Dict[str, Dict[str, Any]], candidates: List[str],
                                 market_type: str) -> None:
        """Catalogo (id + nomi runner) di un mercato "punteggio" per i candidati
        mancanti; una sola chiamata per lotto. Le QUOTE arrivano poi dallo stream
        (o dal poll REST di fallback) come per il MATCH_ODDS."""
        from betfairlightweight import filters

        # cache solo per eventi ancora noti (memoria stabile nei run lunghi)
        for eid in [e for e in store if e not in self.events]:
            store.pop(eid, None)
        missing = [e for e in candidates if e not in store]
        if not missing:
            return  # nessuna chiamata: il throttle non parte
        # un mercato per evento: ``max_results`` deve seguire il LOTTO, non
        # restare fisso a 50 — in una giornata piena i candidati CS superano
        # i 50 e le partite oltre il tetto restavano senza Correct Score
        # (Omega e la Safe R.E. cieche su quelle) fino al giro successivo.
        missing = missing[:_MAX_CATALOGUE_RESULTS]
        cats = self.client.betting.list_market_catalogue(
            filter=filters.market_filter(
                event_ids=missing, market_type_codes=[market_type],
            ),
            market_projection=["EVENT", "RUNNER_DESCRIPTION"],
            max_results=min(_MAX_CATALOGUE_RESULTS, max(1, len(missing))),
        )
        for c in cats or []:
            event_id = getattr(getattr(c, "event", None), "id", None)
            market_id = getattr(c, "market_id", None)
            if not event_id or not market_id:
                continue
            store[str(event_id)] = {
                "market_id": market_id,
                "names": {
                    getattr(r, "selection_id", None): getattr(r, "runner_name", None)
                    for r in (getattr(c, "runners", None) or [])
                },
            }
        # i mercati entrano nell'indice → da qui in poi vanno sullo stream
        # (refresh_stream_set) o nel poll REST di fallback come il MATCH_ODDS
        self._rebuild_market_index()


    # ------------------------------------------------------------ opportunità
    def _prune_opp_blocks(self, ev: Dict[str, Any], eid: Optional[str] = None,
                          now: Optional[datetime] = None) -> Dict[str, Dict[str, Any]]:
        """Blocchi opportunità ancora VIVI per lo stato corrente: un mercato la
        cui linea è ormai decisa (o il 1T finito) esce dallo stream e i suoi
        prezzi si fermano — pubblicarlo sarebbe pubblicare un prezzo morto.
        Evento del ramo pre-KO (Mike): vivono le sole linee 3.5/4.5."""
        blocks = ev.get("opp")
        if not isinstance(blocks, dict):
            return {}
        pre_ko = self._is_pre_ko_ou_event(eid, ev, now)
        mike = bool(eid) and str(eid) in set(self._mike_followed())
        live = {
            mid: blk for mid, blk in blocks.items()
            if scanner.is_opp_market_live(
                blk.get("market_type"), blk.get("line"), ev.get("minute"),
                ev.get("score_home"), ev.get("score_away"), pre_ko=pre_ko, mike=mike,
            )
        }
        # H6 — una linea tenuta viva SOLO per Mike può essere già DECISA: va
        # marcata, altrimenti il motore opportunità la prezzerebbe come se fosse
        # in gioco (e con max_prob_lay=0 il bot Safe potrebbe layarla).
        for mid, blk in live.items():
            if not isinstance(blk, dict):
                continue
            decided = scanner.ou_block_decided(blk, ev.get("score_home"), ev.get("score_away"))
            if decided:
                blk["decided"] = True
            elif "decided" in blk:
                blk.pop("decided", None)
            if mike:
                blk["for_mike"] = True
            elif "for_mike" in blk:
                blk.pop("for_mike", None)
        if len(live) != len(blocks):
            ev["opp"] = live
        return live

    def opp_model(self) -> Optional[Any]:
        """Modello opportunità (puro) con l'Atlante Hazard caricato UNA volta.
        None se il modulo/atlante non sono disponibili: lo scanner non deve mai
        morire per il motore di analisi."""
        if self._opp_model is not None or self._opp_atlas_loaded:
            return self._opp_model
        self._opp_atlas_loaded = True
        try:
            from .opportunity import OpportunityModel
        except Exception as e:  # noqa: BLE001
            logger.warning("[safe-scan] motore opportunita non disponibile: %s", str(e)[:120])
            return None
        # 24/09: UN solo caricamento dell'atlante in tutta Safe. Prima qui si
        # leggeva hazard_atlas_v1 (default del loader) e in selezione il v2:
        # due file, due istanze, e un aggiornamento avrebbe toccato solo meta'
        # dei consumatori. Ora il modello riceve il FORNITORE di selezione
        # (v2, ricarica per mtime). Le griglie usate dal controincrocio
        # (global/by_league/by_team) sono identiche in v1 e v2 (verificato).
        atlas = _selezione.atlante
        if not atlas():
            logger.warning("[safe-scan] atlante hazard non caricato: controincrocio assente")
        self._opp_model = OpportunityModel(atlas=atlas)
        return self._opp_model

    def opportunities(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Opportunità REALI dell'evento (probabilità × prezzo × liquidità).

        λ dalle quote 1X2 pre-KO congelate nel payload (lo scanner non ha il
        fixture_id: chi ha il DB può rifare il calcolo con λ migliori usando
        ``opportunity.resolve_lambdas(payload, fixture=…)``). [] su qualsiasi
        problema: un'analisi non deve mai fermare la pubblicazione dei FATTI.
        """
        model = self.opp_model()
        if model is None:
            return []
        try:
            from .opportunity import resolve_lambdas

            lam = resolve_lambdas(payload, fixture=None)
            if lam is None:
                return []
            return model.evaluate(
                payload, sport="calcio", lambdas=(lam[0], lam[1]),
                league_id=lam[2], now_ts=time.time(),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[safe-scan] opportunita KO: %s", str(e)[:140])
            return []

    # ------------------------------------------------------------- canale locale
    def _avvia_canale(self) -> Optional[Any]:
        """Accende il canale locale dello scanner. Non solleva MAI.

        Senza canale (porta occupata, ``websockets`` assente, qualunque altro
        guasto) lo scanner lavora esattamente come prima: i bot leggono dal
        database e la pagina pure. E' la direzione giusta del ripiego - un
        guasto del TRASPORTO non puo' fermare il feed unico di tutti i bot.
        """
        try:
            from Betfair.stream import local_channel as _lc

            try:
                porta = int((os.environ.get(_PORTA_CANALE_ENV) or "").strip()
                            or _PORTA_CANALE_SCAN)
            except ValueError:
                porta = _PORTA_CANALE_SCAN
            ch = _lc.start_channel(porta, "safe-scan", solo_lettura=True)
            if ch is None:
                logger.warning("[safe-scan] canale locale NON attivo su %d (porta "
                               "occupata?): tutto resta sul database.", porta)
                return None
            # la cadenza attesa la DICHIARA il produttore: chi consuma calcola
            # da qui quando dirsi "muto", invece di cablare una costante propria
            # (difetto §7.33 del catalogo: la costante duplicata nel frontend).
            ch.set_hello(topic=sorted(_TOPIC_SCAN.values()) + [_TOPIC_SCANNER_STATO],
                         cadenza_scan_s=_PUBLISH_MIN_INTERVAL_SEC,
                         cadenza_stato_s=_STATUS_PERIOD_SEC)
            logger.info("[safe-scan] canale locale attivo su 127.0.0.1:%d "
                        "(sola lettura; topic: %s, %s, %s)", porta,
                        _TOPIC_SCAN["calcio"], _TOPIC_SCAN["tennis"], _TOPIC_SCANNER_STATO)
            return ch
        except Exception as ex:  # noqa: BLE001 - il canale e' opzionale, sempre
            logger.warning("[safe-scan] canale locale KO: %s", str(ex)[:160])
            return None

    def _spingi_riga(self, sport: str, riga: Dict[str, Any]) -> None:
        """La riga di scan sul canale, nel punto in cui e' pronta e COMPLETA.

        Sta PRIMA del freno di scrittura (``_PUBLISH_MIN_INTERVAL_SEC``): il
        freno esiste per proteggere l'IO di Supabase (lezione del 13/09, budget
        esaurito) e li' resta; sul canale non c'e' nessun budget da proteggere,
        quindi il prezzo esce a ogni cambiamento invece di aspettare fino a
        2,5 s. Il DATABASE continua a ricevere la stessa identica riga: il push
        e' un'ACCELERAZIONE, non una sostituzione.

        La riga spinta e' LO STESSO OGGETTO che finisce in ``rows``, non una sua
        proiezione: un consumatore deve poter mettere la riga del canale al
        posto della riga del database senza sapere da dove viene (difetto D3 del
        piano: spingendola prima del blocco ``opportunities`` la riga del canale
        sarebbe stata monca proprio dove il prezzo si muove).

        Topic separato per sport: calcio e tennis non si mischiano mai.
        Non solleva e non blocca: ``publish`` esce senza client, serializza dopo
        il controllo e ingoia qualunque errore. Se il canale e' morto, lo
        scanner fa esattamente quello che farebbe senza canale.
        """
        canale = self.canale
        if canale is None:
            return
        topic = _TOPIC_SCAN.get(sport)
        if topic is None:
            return
        try:
            canale.publish(topic, riga)
        except Exception as ex:  # noqa: BLE001 - mostrare non ferma mai lo scanner
            logger.debug("[safe-scan] push della riga KO: %s", str(ex)[:120])

    def _spingi_stato(self, payload: Dict[str, Any]) -> None:
        """Lo stato dello scanner sul canale: gli STESSI campi della riga di
        ``safe_strategy_status``, zero campi nuovi, zero scritture in piu'."""
        canale = self.canale
        if canale is None:
            return
        try:
            canale.publish(_TOPIC_SCANNER_STATO, payload)
        except Exception as ex:  # noqa: BLE001 - mostrare non ferma mai lo scanner
            logger.debug("[safe-scan] push dello stato KO: %s", str(ex)[:120])

    def canale_statistiche(self) -> Optional[Dict[str, Any]]:
        """Che cosa sta facendo il canale (None se non c'e'): e' il numero che
        la prova a secco legge per dire se qualcuno ha perso un fotogramma."""
        canale = self.canale
        if canale is None:
            return None
        try:
            return canale.statistiche()
        except Exception:  # noqa: BLE001 - una misura non ferma mai lo scanner
            return None

    # ------------------------------------------------------------- pubblicazione
    def build_rows(self, now: datetime) -> "tuple[List[Dict[str, Any]], List[str]]":
        rows: List[Dict[str, Any]] = []
        wanted: List[str] = []
        for sport, st in self.sports.items():
            for eid, meta in st.metas.items():
                ev = self.events.get(eid) or {}
                inplay = bool(ev.get("inplay"))
                if not scanner.is_monitorable(inplay, meta.get("open_date"), now,
                                              self.pre_ko_ou_hours if sport == "calcio" else 0.0):
                    continue
                if ev.get("mo_status") == "CLOSED":
                    continue  # partita finita: la riga verrà cancellata
                wanted.append(eid)
                if sport == "calcio":
                    home, away = scanner.split_event_name(meta.get("event_name"))
                    payload: Dict[str, Any] = {
                        "event_name": meta.get("event_name"),
                        "home": home,
                        "away": away,
                        "competition": meta.get("competition"),
                        "open_date": meta.get("open_date"),
                        "inplay": inplay,
                        "mo_market_id": meta.get("market_id"),
                        "mo_status": ev.get("mo_status"),
                        "odds": ev.get("odds"),
                        "minute": ev.get("minute"),
                        "score_home": ev.get("score_home"),
                        "score_away": ev.get("score_away"),
                        "red_home": ev.get("red_home"),
                        "red_away": ev.get("red_away"),
                        "pre_ko": ev.get("pre_ko"),
                        "cs": ev.get("cs"),
                        "ht": ev.get("ht"),      # HALF TIME SCORE completo (gamba 1T Omega v2)
                        # disponibilità video/animazione Betfair (IPS): i pulsanti
                        # 📺/📊 della UI la mostrano come fa il sito
                        "media": ev.get("media"),
                        # FEED UNICO per i runner: stato IPS grezzo + timeline +
                        # volume scambiato (board desktop)
                        "score_raw": ev.get("score_raw"),
                        "timeline": ev.get("timeline"),
                        "mo_total_matched": ev.get("mo_total_matched"),
                        # K1 (26/09), chiave ADDITIVA: size e volumi in EUR (stream
                        # convertito alla fonte, REST gia' nella valuta del conto)
                        "valuta": _valuta.VALUTA_CONTO,
                        # ts dell'ultimo CAMBIO delle quote 1X2 (freschezza prezzo)
                        "odds_ts_ms": ev.get("odds_ts_ms"),
                        # F0 (18/09), chiavi ADDITIVE: l'istante di BETFAIR dello
                        # stesso cambio (``publishTime`` del book) e il ritardo
                        # che l'exchange impone su QUESTO mercato. Nessuna
                        # chiamata in piu': entrambi vengono dal book gia' in
                        # mano. Nessuna chiave storica tolta.
                        "odds_pt_ms": ev.get("odds_pt_ms"),
                        "bet_delay": ev.get("bet_delay"),
                        # MERCATI A GOL del motore opportunità (chiavi ADDITIVE):
                        # ou = [{line, market_id, status, selections…}], btts, ht_result
                        **scanner.split_opportunity_blocks(self._prune_opp_blocks(ev, eid, now)),
                    }
                    # CERT. 14/09 - "controllo del gioco": indice unico calcolato
                    # QUI, una volta sola, da corner (finestra mobile sulla
                    # timeline) e cartellini. Va nel payload perche' il motore
                    # della UI e quello del bot devono leggere lo STESSO numero:
                    # se lo ricalcolassero ognuno per conto proprio, la pagina
                    # potrebbe mostrare un segnale che il bot non prende.
                    # Deriva solo da campi gia' nella firma (minute, score_raw,
                    # timeline): non aggiunge una sola riscrittura.
                    payload["pressure_index"] = _pressure.pressure_index(payload)
                    # SPEC §2 «Selezione aggiuntiva» (ordine dell'utente
                    # 16/09), FONTE cambiata il 25/09 (D5 punti 5-6): gli
                    # scontri diretti VERI e le forze attacco/difesa della
                    # fixture abbinata, dal DB (`fixture_predictions.raw_json`,
                    # la riga della Dashboard), non piu' l'atlante per nome.
                    # Pubblicati QUI una volta sola per la stessa ragione di
                    # `pressure_index`: il motore del bot e quello della
                    # pagina devono leggere LO STESSO numero. Qui si LEGGE la
                    # cache (`hydrate_schede` nel tick): nessuna query in
                    # `build_rows`. None = dato assente.
                    payload["selection_hint"] = self.schede.hint(eid)
                    # D5 punto 1, chiave ADDITIVA: il round di API-Football
                    # della fixture abbinata (veto delle FINALI)
                    payload["fixture_round"] = self.schede.round(eid)
                else:
                    p1, p2 = scanner.split_event_name(meta.get("event_name"))
                    payload = {
                        "event_name": meta.get("event_name"),
                        "p1": p1,
                        "p2": p2,
                        "competition": meta.get("competition"),
                        "open_date": meta.get("open_date"),
                        "inplay": inplay,
                        "mo_market_id": meta.get("market_id"),
                        "mo_status": ev.get("mo_status"),
                        "odds": ev.get("odds"),
                        "sets": ev.get("sets"),
                        "games": ev.get("games"),
                        "media": ev.get("media"),
                        "score_raw": ev.get("score_raw"),
                        "mo_total_matched": ev.get("mo_total_matched"),
                        "valuta": _valuta.VALUTA_CONTO,   # K1 (26/09), additiva
                        # ts dell'ultimo CAMBIO delle quote (freschezza prezzo),
                        # come per il calcio: chiave additiva
                        "odds_ts_ms": ev.get("odds_ts_ms"),
                        # F0 (18/09) - nel tennis erano proprio i due numeri che
                        # mancavano: senza ``odds_pt_ms`` il salto fra la
                        # pubblicazione di Betfair e la nostra lavorazione non
                        # era misurabile, e senza ``bet_delay`` il bot non sapeva
                        # a quale ritardo era soggetto (3 s, 5 s su alcuni ITF).
                        "odds_pt_ms": ev.get("odds_pt_ms"),
                        "bet_delay": ev.get("bet_delay"),
                        # Q12 (25/09), chiave ADDITIVA: quota pre-partita
                        # congelata {p1, p2} (stesso nome e schema del calcio)
                        "pre_ko": ev.get("pre_ko"),
                    }
                sig = scanner.payload_signature(payload)
                if self.written_sig.get(eid) == sig:
                    continue  # write-on-change
                # throttle per-evento SOLO per le quote: con lo stream cambiano ogni
                # secondo, la riga aspetta il prossimo giro (sig NON consumata) — mai
                # perdere l'ultimo stato, mai inondare il DB. Un cambio CRITICO
                # (gol, minuto, rosso, in-play, stato mercato, set/game) passa SUBITO:
                # la realtà mostrata deve coincidere con quella di Betfair.
                crit = scanner.critical_signature(sport, payload)
                mono = self._ora_mono()
                # throttle per-evento SOLO per le quote (vedi sopra). Da qui in
                # avanti la decisione e' una VARIABILE e non un ``continue``,
                # perche' il canale deve ricevere anche la riga che il freno del
                # database trattiene: e' tutto il senso della fase.
                frenata = (
                    self.written_crit.get(eid) == crit
                    and mono - self.last_pub_mono.get(eid, 0.0) < _PUBLISH_MIN_INTERVAL_SEC
                )
                if frenata and self.canale is None:
                    # SENZA CANALE il percorso e' identico a quello di prima,
                    # istruzione per istruzione: si esce qui e non si calcola
                    # niente. E' la garanzia che a interruttore spento lo scanner
                    # sia quello di sempre.
                    continue
                # le OPPORTUNITA' sono un DERIVATO dei fatti e vivono in
                # bot_service.py (tabella safe_strategy_opportunities): qui restano
                # SPENTE salvo SAFE_SCAN_OPPORTUNITIES=1. Quando accese si calcolano
                # DOPO la firma (la confidenza dipende anche dall'orologio: dentro
                # la firma riscriverebbe la riga a ogni tick) e PRIMA del push,
                # perche' la riga del canale deve essere identica a quella del
                # database anche nel blocco ``opportunities``: spingerla prima
                # (difetto D3) l'avrebbe lasciata monca proprio nell'istante in
                # cui il prezzo si muove, e chi fonde per payload intero sarebbe
                # diventato cieco su quel blocco.
                if sport == "calcio" and _opportunities_enabled():
                    payload["opportunities"] = self.opportunities(payload)
                riga = {
                    "event_id": eid,
                    "sport": sport,
                    "payload": payload,
                    "updated_at": self._ora_iso(),
                }
                # LO STESSO OGGETTO va sul canale e nel database: chiavi, tipi e
                # valori non possono divergere perche' non ci sono due oggetti.
                self._spingi_riga(sport, riga)
                if frenata:
                    continue
                self.last_pub_mono[eid] = mono
                self.written_sig[eid] = sig
                self.written_crit[eid] = crit
                rows.append(riga)
        return rows, wanted

    def hydrate_schede(self, now: Optional[datetime] = None) -> int:
        """D5 (25/09): abbina alle fixture del DB le partite di calcio
        CANDIDATE (in-play o nella finestra pre-KO) e legge la loro scheda
        (una query a blocchi per giro, solo per le fixture NUOVE; la finestra
        di fixture una volta ogni 10 minuti). Mai eccezioni."""
        now = now or datetime.now(timezone.utc)
        st = self.sports.get("calcio")
        if st is None:
            return 0
        eventi: List[Dict[str, Any]] = []
        for eid, meta in st.metas.items():
            ev = self.events.get(eid) or {}
            if not (ev.get("inplay") or scanner.in_pre_ko_window(meta.get("open_date"), now)):
                continue
            eventi.append({"event_id": eid, "event_name": meta.get("event_name"),
                           "open_date": meta.get("open_date")})
        return self.schede.aggiorna(eventi, now)

    def hydrate_pre_ko(self) -> int:
        """Rilegge dal DB il riferimento 1X2 pre-KO delle partite di calcio gia'
        IN CORSO che non ce l'hanno in memoria (tipicamente: lo scanner e'
        ripartito a partita iniziata).

        Va chiamata PRIMA di ``publish``: il publish riscrive la riga con
        ``pre_ko`` preso dallo stato in RAM, quindi un giro pubblicato prima
        della reidratazione DISTRUGGE la copia sul DB.

        Un solo tentativo per evento (``pre_ko_tried``): se il riferimento non
        c'e' nemmeno sul DB, non lo si va a ricercare a ogni giro. In ``dry``
        non si legge nulla. Torna quanti riferimenti sono stati recuperati."""
        if self.dry:
            return 0
        # Q12 (25/09): anche il tennis (coppia p1/p2), con la sua condizione
        da_cercare = [
            eid for eid, ev in self.events.items()
            if ev.get("sport") in ("calcio", "tennis")
            and ev.get("inplay")
            and not _pre_ko_usabile(ev)
            and eid not in self.pre_ko_tried
        ]
        if not da_cercare:
            return 0
        # CERT. 13/09 (review) — si segna "gia' tentato" SOLO cio' che e' stato
        # davvero interrogato con esito. Prima si marcava PRIMA della lettura:
        # un solo timeout del DB (e il DB oggi va in timeout spesso) bruciava il
        # tentativo per TUTTE le partite in corso, per il resto della giornata —
        # cioe' il difetto che questa funzione esiste per chiudere si richiudeva
        # da solo al primo intoppo.
        try:
            trovati = scan_db.load_scan_pre_ko(da_cercare)
        except Exception as e:  # noqa: BLE001 - mai fatale, e si ritenta al giro dopo
            logger.warning("[safe-scan] reidratazione pre-KO KO (si ritenta): %s", str(e)[:140])
            return 0
        if trovati is None:
            return 0
        # ``load_scan_pre_ko`` ritorna un dizionario con una chiave per OGNI
        # evento interrogato (valore None = cercato e non trovato): quelli che
        # non compaiono non sono stati chiesti e restano da ritentare.
        self.pre_ko_tried.update(k for k in trovati)
        recuperati = 0
        for eid, pre in trovati.items():
            if pre is None:
                continue
            ev = self.events.get(eid)
            if ev is None or _pre_ko_usabile(ev):
                continue
            # la forma deve essere quella dello SPORT dell'evento
            if not _pre_ko_usabile({"sport": ev.get("sport"), "pre_ko": pre}):
                continue
            # si conserva il ``captured_at`` originale e si dichiara che il
            # riferimento arriva dal DB, non da una cattura in diretta
            ev["pre_ko"] = {**pre, "rehydrated": True}
            recuperati += 1
        if recuperati:
            logger.info(
                "[safe-scan] riferimento pre-KO recuperato dal DB per %d partite in corso "
                "(BASE e PUNTA tornano valutabili); cercato per %d",
                recuperati, len(da_cercare),
            )
        elif da_cercare:
            logger.info(
                "[safe-scan] nessun riferimento pre-KO sul DB per %d partite in corso: "
                "BASE e PUNTA restano n/d su queste (scanner acceso a match iniziato)",
                len(da_cercare),
            )
        return recuperati

    def purge_orphans(self, wanted: List[str]) -> int:
        """Righe in tabella che NON appartengono a questo giro (istanze
        precedenti dello scanner, riavvii dell'app): vanno CANCELLATE, altrimenti
        la UI mostra partite vecchie per sempre (visto dal vivo 09/09: 123 righe
        in tabella con 25 eventi monitorati). All'avvio e poi ogni
        _ORPHAN_PURGE_PERIOD_SEC."""
        known = scan_db.list_scan_event_ids()
        if known is None:
            return 0
        keep = set(wanted)
        orphans = [eid for eid in known if eid not in keep]
        if orphans:
            scan_db.delete_scan_rows(orphans)
            logger.info("[safe-scan] pulite %d righe orfane di istanze precedenti", len(orphans))
        self.orphan_purge_ts = time.monotonic()
        return len(orphans)

    def publish(self, now: datetime) -> "tuple[int, int]":
        rows, wanted = self.build_rows(now)
        stale = [eid for eid in self.written_sig if eid not in set(wanted)]
        if self.dry:
            return len(rows), len(stale)
        if time.monotonic() - self.orphan_purge_ts > _ORPHAN_PURGE_PERIOD_SEC:
            self.purge_orphans(wanted)
        if rows:
            scan_db.upsert_scan_rows(rows)
        if stale:
            scan_db.delete_scan_rows(stale)
            for eid in stale:
                self.written_sig.pop(eid, None)
                self.written_crit.pop(eid, None)
                self.last_pub_mono.pop(eid, None)
        return len(rows), len(stale)

    def publish_status(self, monitored: int) -> None:
        payload = {
            "calcio_inplay": sum(
                1 for e in self.events.values() if e.get("sport") == "calcio" and e.get("inplay")
            ),
            "tennis_inplay": sum(
                1 for e in self.events.values() if e.get("sport") == "tennis" and e.get("inplay")
            ),
            "monitored": monitored,
            "dry": self.dry,
            "source": getattr(self, "last_source", "rest"),
            # copertura stream (0 = REST puro): mercati serviti da connessioni vive,
            # connessioni attive e capacità del pool — nei weekend pieni si vede
            # subito se il pool basta o se una parte va al fallback REST
            "stream_markets": len(self.stream.covered_ids()) if self.stream else 0,
            "stream_connections": self.stream.active_connections() if self.stream else 0,
            "stream_capacity": self.stream.capacity if self.stream else 0,
            # 17/09 - un book SENZA prezzi e' un evento da CONTARE, non da
            # subire, e i mercati che non hanno quote vanno detti per NOME.
            "stream_books_vuoti": sum(self.book_vuoti.values()),
            "rest_books_vuoti": self.book_vuoti_rest,
            "stream_mercati_senza_quote": self.mercati_senza_quote[:_SENZA_QUOTE_ELENCO_MAX],
            "stream_mercati_senza_quote_n": len(self.mercati_senza_quote),
            "stream_senza_quote_eta_s": round(self.senza_quote_eta_s, 1),
            # i soli mercati CORE: sono questi a fare allarme e badge REST
            "stream_mercati_allarme": self.mercati_allarme[:_SENZA_QUOTE_ELENCO_MAX],
            "stream_mercati_allarme_n": len(self.mercati_allarme),
            # flumine nel processo del feed = ladder a dizionari (17/09)
            "flumine_caricato": self.flumine_caricato(),
            # F1 (18/09) - l'INTERRUTTORE non si deduce dai log, si legge. Sta
            # qui accanto a ``flumine_caricato`` per la stessa ragione: e' un
            # fatto del processo, e uno stato onesto lo dichiara. Costa zero
            # letture e zero scritture (viaggia sulla riga che si scrive
            # comunque). ``canale`` porta i conti del canale - se qualcuno ha
            # perso un fotogramma LO SI DICE.
            "canale_acceso": self.canale is not None,
            "canale": self.canale_statistiche(),
            "stream_shards": self.stream.stato_shard() if self.stream else [],
            # mercati a gol sotto quote per il motore opportunità (peso sul pool)
            "opp_events": len(self.opp_markets),
            "opp_markets": sum(len(m) for m in self.opp_markets.values()),
            "last_error": self.last_error,
            "started_at": self.started_at,
            # CERT. 14/09 - DURATA DEL GIRO, per fase. Va sullo stato e non nel
            # log perche' una misura che vive solo nel terminale non la legge
            # nessuno, e questa deve poter essere confrontata prima e dopo un
            # intervento. Nessuna scrittura in piu': viaggia sulla riga di stato
            # che si scrive comunque.
            "tick": self.crono.riassunto(),
        }
        # lo STESSO payload che va (o andrebbe) sul database: nessuna proiezione,
        # nessun campo inventato per il canale. Anche in ``dry``, perche' in dry
        # l'unica differenza deve restare "non si scrive sul database".
        self._spingi_stato(payload)
        if self.dry:
            logger.info("[safe-scan] status: %s", payload)
        else:
            scan_db.upsert_status(payload)
        self.status_ts = time.monotonic()

    # ------------------------------------------------------------- ciclo
    def any_hot_calcio(self) -> bool:
        return any(
            ev.get("sport") == "calcio"
            and ev.get("inplay")
            and scanner.is_hot_minute(ev.get("minute"))
            for ev in self.events.values()
        )

    def _safe_catalogue(self, label: str, fn: Any, *args: Any, **kwargs: Any) -> None:
        """Un catalogo SECONDARIO (CS, HT, mercati a gol, pre-KO) non e' mai
        motivo per perdere un giro: si logga, si segna in ``last_error`` e si
        riprova al prossimo throttle. Le quote e i punteggi vengono pubblicati
        comunque — sono loro che tengono vive copertura, cash out e uscite."""
        try:
            fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - mai fermare la pubblicazione dei fatti
            self.last_error = f"catalogo {label}: {type(e).__name__}: {str(e)[:120]}"
            logger.warning("[safe-scan] catalogo %s KO (riprovo al prossimo giro): %s",
                           label, str(e)[:140])

    def tick(self) -> None:
        now_mono = time.monotonic()
        now = datetime.now(timezone.utc)
        self.crono.apri_giro(now_mono)
        try:
            if now_mono - self.keepalive_ts > _KEEPALIVE_PERIOD_SEC:
                keep_alive(self.client)
                self.keepalive_ts = now_mono

            for sport, st in self.sports.items():
                if now_mono - st.catalogue_ts > _CATALOGUE_TTL_SEC \
                        and now_mono - st.catalogue_fail_ts > _CATALOGUE_RETRY_SEC:
                    try:
                        with self.crono.fase("catalogo"):
                            self.refresh_catalogue(sport)
                    except Exception as e:  # noqa: BLE001 - backoff, il resto del giro continua
                        # prima: eccezione → giro abortito (nessuna pubblicazione) e
                        # NUOVA listMarketCatalogue ogni 0,5 s finché Betfair non
                        # rispondeva (martellamento + feed fermo per tutti gli sport)
                        st.catalogue_fail_ts = now_mono
                        self.last_error = f"catalogo {sport}: {type(e).__name__}: {str(e)[:120]}"
                        logger.warning("[safe-scan] catalogo %s KO (riprovo fra %.0fs): %s",
                                       sport, _CATALOGUE_RETRY_SEC, str(e)[:140])
                    time.sleep(_REQ_DELAY)
            # pruning: eventi non più nel catalogo del giorno → via dallo stato
            known = {
                eid for st in self.sports.values() for eid in st.metas
            }
            for eid in [e for e in self.events if e not in known]:
                self.events.pop(eid, None)

            # QUOTE: stream ufficiale (push, conflate 1s) sui mercati rilevanti;
            # poll REST come FALLBACK per i mercati rilevanti che lo stream non
            # copre (oltre il cap, o stream non in salute) — mai un buco dati.
            # la classifica dei mercati rilevanti si calcola UNA volta per giro
            # e la riusano sia lo stream sia il fallback REST (prima la
            # calcolava refresh_stream_set e poi di nuovo il ciclo dei book)
            ranked_per_sport = {
                sport: self.ranked_relevant_markets(sport, now) for sport in self.sports
            }
            rilevanti = {
                sport: [mid for _, mid in r] for sport, r in ranked_per_sport.items()
            }
            with self.crono.fase("stream"):
                self.refresh_stream_set(now, ranked_per_sport)
                if self.stream is not None:
                    for b in self.stream.drain():
                        self._apply_market_book(b, dallo_stream=True)
            # 17/09 - COPERTURA PER MERCATO. Prima: `covered_ids()` sulla salute
            # del SOCKET, cioe' gli heartbeat ogni 5 s; una connessione viva che
            # non consegnava quote dichiarava coperti tutti i mercati e
            # `poll_books` non partiva MAI (fasi_p95.book = 0.0 per ore).
            tutti_rilevanti = [mid for ids in rilevanti.values() for mid in ids]
            covered, in_allarme = self._aggiorna_copertura(now_mono, tutti_rilevanti, now)
            # il badge STREAM/REST: "rest" quando ci si ripiega davvero, cioe'
            # quando lo stream non consegna o un mercato CORE resta senza quote.
            # Una linea a gol illiquida non deve far diventare rosso il badge.
            self.last_source = (
                "stream" if (self.stream is not None and not in_allarme
                             and self.stream.serving()) else "rest"
            )
            any_inplay_c = any(
                e.get("sport") == "calcio" and e.get("inplay") for e in self.events.values()
            )
            any_inplay_t = any(
                e.get("sport") == "tennis" and e.get("inplay") for e in self.events.values()
            )
            periods = {
                "calcio": scanner.books_period_calcio(any_inplay_c, self.any_hot_calcio()),
                "tennis": scanner.books_period_tennis(any_inplay_t),
            }
            for sport, period in periods.items():
                st = self.sports[sport]
                if now_mono - st.books_ts <= period:
                    continue
                uncovered = [mid for mid in rilevanti[sport] if mid not in covered]
                if uncovered:
                    try:
                        with self.crono.fase("book"):
                            self.poll_books(sport, uncovered)
                    except Exception as e:  # noqa: BLE001 - si riprova alla cadenza normale
                        # prima: eccezione → giro abortito e listMarketBook ripetuta
                        # a ogni tick (0,5 s) con Betfair già in difficoltà
                        st.books_ts = now_mono
                        self.last_error = f"book {sport}: {type(e).__name__}: {str(e)[:120]}"
                        logger.warning("[safe-scan] poll book %s KO (riprovo fra %.0fs): %s",
                                       sport, period, str(e)[:140])
                else:
                    st.books_ts = now_mono

            # punteggi/timeline: nel run persistente li fa ScoreFeedWorker (thread);
            # qui SOLO se il thread non c'è (collaudo/test)
            if self.score_worker is None:
                if now_mono - self.scores_ts > _SCORES_PERIOD_SEC:
                    self.poll_scores()
                if now_mono - self.timelines_ts > _TIMELINE_PERIOD_SEC:
                    self.poll_timelines()

            # Correct Score: catalogo appena compare un candidato nuovo; le QUOTE
            # arrivano dallo stream (o dal poll REST di fallback) come per il
            # MATCH_ODDS — nessun poll dedicato (audit 09/09 sera: prima 15s REST)
            # Un catalogo secondario che fallisce NON deve portarsi via il giro:
            # la pubblicazione dei FATTI (quote, punteggi) e' la linea vitale di
            # tutti e tre i bot. Prima una qualunque eccezione qui saltava
            # ``publish`` e ``publish_status`` di quel tick.
            candidates = self.cs_candidates()
            if candidates and now_mono - self.cs_catalogue_ts > _CS_CATALOGUE_MIN_INTERVAL_SEC:
                self.cs_catalogue_ts = now_mono
                self._safe_catalogue("correct score", self.refresh_cs_catalogue, candidates)
            ht_cands = self.ht_candidates()
            if ht_cands and now_mono - self.ht_catalogue_ts > _CS_CATALOGUE_MIN_INTERVAL_SEC:
                self.ht_catalogue_ts = now_mono
                self._safe_catalogue("half time score", self.refresh_ht_catalogue, ht_cands)
            # mercati a gol del motore opportunità: stesso schema (catalogo solo
            # per i candidati nuovi, quote dallo stream / REST di fallback)
            opp_cands = self.opp_candidates()
            if opp_cands and now_mono - self.opp_catalogue_ts > _CS_CATALOGUE_MIN_INTERVAL_SEC:
                self.opp_catalogue_ts = now_mono
                self._safe_catalogue("mercati a gol", self.refresh_opp_catalogue, opp_cands)
            # ramo pre-KO O/U (Mike): SOLO le linee 3.5/4.5 delle partite in
            # finestra, stesso throttle; a ramo spento la lista è vuota
            pre_cands = self.pre_ko_ou_candidates(now)
            if pre_cands and now_mono - self.pre_ko_catalogue_ts > _CS_CATALOGUE_MIN_INTERVAL_SEC:
                self.pre_ko_catalogue_ts = now_mono
                self._safe_catalogue("pre-KO O/U", self.refresh_opp_catalogue, pre_cands,
                                     market_types=scanner.PRE_KO_OU_MARKET_TYPES)

            # PRIMA del publish: il publish riscriverebbe pre_ko=None sul DB
            with self.crono.fase("pre_ko"):
                self.hydrate_pre_ko()
                # D5 (25/09): schede DB delle fixture nuove (h2h, forze, round)
                self.hydrate_schede(now)
            with self.crono.fase("scrittura"):
                written, deleted = self.publish(now)
            if written or deleted:
                logger.info(
                    "[safe-scan] pubblicate %d righe, rimosse %d (monitorati %d)",
                    written, deleted, len(self.written_sig),
                )
            # CERT. 13/09 — il BATTITO lo scrive il thread punteggi, non il tick.
            # Qui era IN CODA al tick, dentro lo stesso try: la sua eta' non
            # misurava "lo scanner e' vivo", misurava LA DURATA DEL GIRO. Con
            # giri da 24 s (poll REST dei book a lotti di 25) il battito nasceva
            # gia' vecchio di 24 s, durante un refresh del catalogo superava i
            # 30 s e faceva cadere la deroga di freschezza di Mike — cioe' lo
            # stesso rallentamento che invecchiava le righe disarmava la valvola
            # che doveva coprirle. E una qualunque eccezione prima di questa
            # riga lo saltava del tutto. Nel run persistente lo fa il thread
            # (ogni 2 s, mai dietro alla rete); qui resta solo per --once/test.
            if self.score_worker is None and now_mono - self.status_ts > _STATUS_PERIOD_SEC:
                self.publish_status(len(self.written_sig))
            # 17/09 - un giro andato bene non vuol dire che ci siano le QUOTE:
            # se mancano, lo si scrive qui, dove prima si azzerava e basta
            self.last_error = self.controlla_flumine() or self.allarme_quote()
            if self.last_error and in_allarme:
                logger.warning("[safe-scan] %s (primi: %s)",
                               self.last_error, ", ".join(in_allarme[:5]))
        except Exception as e:  # noqa: BLE001 - lo scanner non muore mai per un giro storto
            self.last_error = f"{type(e).__name__}: {str(e)[:140]}"
            logger.warning("[safe-scan] ciclo KO: %s", self.last_error)
        finally:
            # anche un giro finito male e' un giro: escluderlo falserebbe la
            # misura proprio nei momenti peggiori, che sono quelli da misurare.
            self.crono.chiudi_giro(time.monotonic())


class Cronometro:
    """Quanto dura il giro dello scanner, e DOVE se ne va il tempo.

    Un totale da solo non serve a niente: se il giro dura 40 s bisogna sapere
    se sono il poll dei book, il catalogo o la scrittura sul database, perche'
    le tre cose si curano in modi diversi. Tiene una finestra scorrevole degli
    ultimi giri (in memoria, nessuna scrittura in piu') e ne pubblica mediana,
    95esimo percentile e massimo, per fase.

    Il 95esimo si legge cosi': "un giro su venti e' piu' lento di questo". La
    mediana descrive la giornata normale, il 95esimo il momento in cui il
    trader ha bisogno del prezzo e non ce l'ha.
    """

    FINESTRA = 120          # ~ gli ultimi 120 giri
    FASI = ("catalogo", "stream", "book", "pre_ko", "scrittura", "altro")

    def __init__(self) -> None:
        self.giri: Deque[float] = deque(maxlen=self.FINESTRA)
        self.fasi: Dict[str, Deque[float]] = {
            f: deque(maxlen=self.FINESTRA) for f in self.FASI
        }
        self._parziali: Dict[str, float] = {}
        self._inizio_giro: Optional[float] = None

    # -- misura
    def apri_giro(self, ora: float) -> None:
        self._inizio_giro = ora
        self._parziali = {}

    @contextmanager
    def fase(self, nome: str):
        """Somma il tempo speso in una fase, anche se ci si passa piu' volte
        nello stesso giro (il poll dei book, per esempio)."""
        t0 = time.monotonic()
        try:
            yield
        finally:
            self._parziali[nome] = self._parziali.get(nome, 0.0) + (time.monotonic() - t0)

    def chiudi_giro(self, ora: float) -> None:
        if self._inizio_giro is None:
            return
        totale = max(0.0, ora - self._inizio_giro)
        self.giri.append(totale * 1000.0)
        misurato = 0.0
        for nome in self.FASI:
            if nome == "altro":
                continue
            v = self._parziali.get(nome, 0.0)
            misurato += v
            self.fasi[nome].append(v * 1000.0)
        # "altro" e' il tempo NON attribuito: se cresce, la strumentazione sta
        # guardando dalla parte sbagliata e va spostata. Meglio vederlo che
        # crederlo zero.
        self.fasi["altro"].append(max(0.0, totale - misurato) * 1000.0)
        self._inizio_giro = None

    # -- lettura
    @staticmethod
    def _pct(valori: Sequence[float], q: float) -> Optional[float]:
        if not valori:
            return None
        ordinati = sorted(valori)
        i = min(len(ordinati) - 1, max(0, int(round(q * (len(ordinati) - 1)))))
        return round(ordinati[i], 1)

    def riassunto(self) -> Dict[str, Any]:
        if not self.giri:
            return {}
        out: Dict[str, Any] = {
            "giri": len(self.giri),
            "p50": self._pct(self.giri, 0.50),
            "p95": self._pct(self.giri, 0.95),
            "max": round(max(self.giri), 1),
        }
        out["fasi_p95"] = {
            nome: self._pct(valori, 0.95)
            for nome, valori in self.fasi.items() if valori
        }
        return out


class ScoreFeedWorker(threading.Thread):
    """Thread dedicato ai PUNTEGGI (IPS scoresAndBroadcast ogni _SCORES_PERIOD_SEC,
    timeline calcio ogni _TIMELINE_PERIOD_SEC). Separato dal tick per due motivi:
      · latenza: il tick pubblica le righe ogni 0.5s e non deve mai aspettare la
        rete dell'IPS; un punteggio nuovo è in tabella entro ~0.5s dal poll;
      · quote: il drain dello stream non si ferma durante il giro punteggi.
    Tocca SOLO gli stati-evento già esistenti (ev.update atomico); la creazione
    degli eventi e il pruning restano nel tick. Errori: loggati, mai fatali."""

    def __init__(self, scan: "Scanner") -> None:
        super().__init__(name="safe-scan-scores", daemon=True)
        self.scan = scan
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.scan.poll_scores()
                if time.monotonic() - self.scan.timelines_ts > _TIMELINE_PERIOD_SEC:
                    self.scan.poll_timelines()
            except Exception as e:  # noqa: BLE001 - il feed punteggi non muore mai
                logger.warning("[safe-scan] giro punteggi KO: %s", str(e)[:140])
            # BATTITO dello scanner (CERT. 13/09): sta QUI e non nel tick perche'
            # deve dire "il processo e' vivo", non "quanto e' durato il giro".
            # E' in un try suo: se il giro punteggi esplode, il battito esce lo
            # stesso — chi legge (Mike) deve poter distinguere "scanner morto"
            # da "scanner lento".
            try:
                if time.monotonic() - self.scan.status_ts > _STATUS_PERIOD_SEC:
                    self.scan.publish_status(len(self.scan.written_sig))
            except Exception as e:  # noqa: BLE001
                logger.warning("[safe-scan] battito KO: %s", str(e)[:140])
            # cadenza fissa: attesa = periodo meno il tempo speso (mai negativa)
            self._stop.wait(max(0.2, _SCORES_PERIOD_SEC - (time.monotonic() - started)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Scanner Safe Strategy")
    parser.add_argument("--once", action="store_true", help="un ciclo e esce (collaudo)")
    parser.add_argument("--dry", action="store_true", help="nessuna scrittura DB")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    lock = None
    if not args.once:
        lock = acquire_single_instance_lock(_LOCK_PORT, "safe-strategy")

    client = build_client(login=True)
    # K1 (26/09): cambio GBP->EUR per le size dello stream (listCurrencyRates,
    # rinfresco orario, cache su disco). Mai un'eccezione.
    _valuta.CAMBIO.avvia(client)
    # stream ufficiale SOLO nel run persistente (--once = collaudo REST puro)
    scan = Scanner(client, dry=args.dry, use_stream=not args.once)
    try:
        if args.once:
            # collaudo: un giro completo esplicito (senza il write-on-change del
            # tick, così le righe restano visibili nel log)
            now = datetime.now(timezone.utc)
            for sport in scan.sports:
                scan.refresh_catalogue(sport)
                time.sleep(_REQ_DELAY)
            for sport in scan.sports:
                ids = scan.relevant_market_ids(sport, now)
                logger.info(
                    "[safe-scan] %s: %d mercati a catalogo, %d rilevanti (in-play / KO entro 20′)",
                    sport, len(scan.sports[sport].metas), len(ids),
                )
                scan.poll_books(sport, ids)
            # secondo passaggio: gli in-play appena scoperti sono ora rilevanti
            for sport in scan.sports:
                ids = scan.relevant_market_ids(sport, now)
                scan.poll_books(sport, ids)
            scan.poll_scores()
            candidates = scan.cs_candidates()
            if candidates:
                scan.refresh_cs_catalogue(candidates)
                scan.poll_books("calcio", [scan.cs_markets[e]["market_id"] for e in candidates if e in scan.cs_markets])
            rows, wanted = scan.build_rows(datetime.now(timezone.utc))
            logger.info(
                "[safe-scan] COLLAUDO: %d eventi monitorabili, %d candidati CS, %d righe",
                len(wanted), len(candidates), len(rows),
            )
            for r in rows[:8]:
                logger.info(
                    "[safe-scan]   %s %s → %s",
                    r["sport"], r["event_id"], str(r["payload"])[:240],
                )
            if not args.dry:
                if rows:
                    scan_db.upsert_scan_rows(rows)
                scan.publish_status(len(wanted))
            return
        # warm-up: ENTRAMBI i cataloghi prima del primo tick, così lo stream
        # nasce già con calcio+tennis insieme (vedi nota in _rebuild_market_index)
        for sport in scan.sports:
            try:
                scan.refresh_catalogue(sport)
            except Exception as e:  # noqa: BLE001 - il tick riproverà
                logger.warning("[safe-scan] warm-up catalogo %s KO: %s", sport, str(e)[:120])
            time.sleep(_REQ_DELAY)
        scan.score_worker = ScoreFeedWorker(scan)
        scan.score_worker.start()
        # 24/09 - ATLANTE HAZARD dal DB al file dei bot (hazard_atlas_sync):
        # SPENTO finche' HAZARD_ATLAS_SYNC=1 non e' nel .env. Un thread demone
        # in QUESTO processo (nessun processo nuovo), una GET da una riga ogni
        # 30'. Il modulo non importa flumine (incidente 17/09).
        try:
            from Betfair.stream.scalper import hazard_atlas_sync as _atl_sync

            _atl_sync.avvia_se_abilitato()
        except Exception as e:  # noqa: BLE001 - il feed non muore per l'atlante
            logger.warning("[safe-scan] sync atlante non avviato: %s", str(e)[:120])
        while True:
            scan.tick()
            time.sleep(0.5)
    finally:
        if scan.score_worker is not None:
            scan.score_worker.stop()
        if scan.stream is not None:
            scan.stream.stop()
        safe_logout(client)
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    main()
