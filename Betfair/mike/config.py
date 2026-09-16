"""config — whitelist parametri e costanti del bot Mike (COSTITUZIONE_MIKE.md §6).

La whitelist e' la barriera di sicurezza backend: SOLO queste chiavi, con questi
tipi/limiti/scelte, vengono applicate dai ``params`` che arrivano dalla UI.
Speculare alla whitelist frontend in ``frontend/src/lib/mike.ts``
(``MIKE_PARAM_FIELDS``). ``mode`` (paper|live) NON e' un parametro: vive in
``mike_control.mode`` e non passa mai da qui.

Pattern env: ``os.getenv(X, "").strip() or default`` (mai ``??``/``or`` su None).
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional

# Codici mercato Betfair delle due linee operate.
OU35 = "OVER_UNDER_35"
OU45 = "OVER_UNDER_45"
FOOTBALL_EVENT_TYPE_ID = "1"

# Selection id ATTESI (Under 3.5 / Over 4.5). Costante DOCUMENTALE: usata solo
# dai test, mai a runtime. La risoluzione avviene sempre PER NOME dal FEED UNICO
# (``feed.event_info`` -> ``xhedge.canonical_selection``): un nome non mappabile
# non produce nessuna selezione (partita non completa), mai un id indovinato.
# Nota: sulla linea 4.5 Betfair inverte l'ordine (Under 4.5 = 1222347).
EXPECTED_SEL = {"UNDER_35": 1222344, "OVER_35": 1222345,
                "OVER_45": 1222346, "UNDER_45": 1222347}

# customerStrategyRef (<=15 char) che marchia gli ordini Mike su Betfair.
CUSTOMER_STRATEGY_REF = "mike"

LOCK_PORT_DEFAULT = 47319


# ---------------------------------------------------------------------------
# Env helpers (pattern piattaforma: stringa vuota = assente)
# ---------------------------------------------------------------------------
def env_str(name: str, default: str) -> str:
    return os.getenv(name, "").strip() or default


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return int(default)
    try:
        return int(float(raw))
    except ValueError:
        return int(default)


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Whitelist: chiave -> (default, cast, min, max, choices)
# choices != None => valore ammesso solo se in choices (min/max ignorati).
# ---------------------------------------------------------------------------
Spec = tuple[Any, Callable[[Any], Any], Optional[float], Optional[float], Optional[tuple]]

PARAM_SPEC: dict[str, Spec] = {
    # ---- generale ----
    "stake": (10.0, float, 0.50, 500.0, None),   # importo LIBERO (es. 1.23): sotto-minimo via place-and-trim
    "commission_pct": (5.0, float, 0.0, 20.0, None),
    # 15/09 — PORTATA DA 3 h A 1 h SU ORDINE DELL'UTENTE, per validare prima il
    # funzionamento pre-match: meno partite in finestra, piu' presto si vede se
    # la fase si comporta. DEVE combaciare con l'env ``SAFE_PRE_KO_OU_HOURS``
    # (il ramo dello scanner che pubblica le linee O/U): oltre quell'ora le
    # linee non sono nel feed e Mike non vedrebbe nessuna candidata. Il
    # controllo e' in `service._config_warn`.
    "entry_hours_before_ko": (1.0, float, 0.25, 12.0, None),
    "competition_filter": ("", str, None, None, None),
    "decide_min_interval_ms": (500, int, 100, 5000, None),
    # MISURA 13/09/2026 ore 21:37, 57 righe di calcio nel feed: la piu' fresca
    # aveva 24 s, NESSUNA sotto i 15 s. Non e' un guasto. Lo scanner pubblica UNA
    # volta per giro e il giro dura quanto il lavoro di rete che contiene (poll
    # REST 10/20/60 s, cataloghi secondari ogni 20 s, catalogo pieno ogni 300 s).
    # 15 s stava SOTTO il pavimento fisico del produttore: una soglia che non
    # poteva essere soddisfatta mai, e infatti "NON entra: feed stantio" e'
    # scattata 24 volte. 45 s = due pubblicazioni con margine.
    "feed_max_age_s": (45.0, float, 3.0, 180.0, None),
    # Deroga "scanner vivo". Lo scanner e' write-on-change: una riga ferma vuol
    # dire che su QUELLA partita non si e' mosso niente, non che il feed e' rotto.
    # Era CABLATA a 30 s nel default di ``feed.feed_fresh`` e cadeva a ogni giro
    # lento, perche' il battito si scrive IN CODA al giro e la sua eta' misura la
    # DURATA DEL GIRO, non la vita dello scanner. 75 s = tre battiti mancati.
    "scanner_alive_max_s": (75.0, float, 10.0, 300.0, None),
    # ---- soglia STRETTA: SOLO per emettere un ORDINE ----
    # Guardare e valutare su una riga di 60 s e' corretto (il prezzo non si e'
    # mosso). Attraversare lo spread con dei soldi no. Ma la severita' va messa
    # sul PRODUTTORE, non sull'eta' della riga: una riga vecchia con lo scanner
    # che batte E' il prezzo corrente, una riga giovane con lo scanner morto e'
    # un caso che non esiste.
    # Da quanto tempo al massimo puo' essere stato visto un BOOK perche' il suo
    # prezzo valga ancora. E' una domanda diversa da "da quanto non cambia": lo
    # scanner marca ogni blocco con ``seen_ms`` (ultimo book RICEVUTO) oltre a
    # ``ts_ms`` (ultimo CAMBIO). Un mercato uscito dal feed resta in cache con
    # l'ultimo prezzo e la riga continua ad aggiornarsi per minuto e punteggio:
    # senza questo controllo si copre o si esce su un prezzo morto.
    "book_seen_max_s": (90.0, float, 5.0, 600.0, None),
    "order_max_age_s": (20.0, float, 3.0, 120.0, None),
    "order_scanner_max_s": (30.0, float, 5.0, 120.0, None),
    # ---- pre-match ----
    "pre_enabled": (True, bool, None, None, None),
    "pre_entry_price_min": (1.30, float, 1.01, 20.0, None),
    "pre_entry_price_max": (3.00, float, 1.01, 20.0, None),
    "pre_min_back_size_factor": (1.0, float, 0.5, 5.0, None),
    # ore prima del KO i book sono larghi: spread ampio ammesso (l'uscita non
    # attraversa lo spread: la lay viene APPOGGIATA e aspetta che il mercato scenda)
    "pre_max_spread_ticks": (6, int, 1, 20, None),
    "pre_green_ticks": (2, int, 1, 10, None),
    # resting = lay a +N tick appoggiata SUBITO dopo il fill dell'ingresso (profitto
    # spalmato, nessuno spread pagato); taker = chiude al best quando i tick ci sono
    "pre_exit_mode": ("resting", str, None, None, ("resting", "taker")),
    # L'USCITA APPOGGIATA IN LIVE (14/09). ACCESA per difetto: la strategia in
    # live deve essere la STESSA del paper, e appoggiare la lay a -2 tick e'
    # tutto il suo margine. Fino al 14/09 questo ramo non era cablato e il live
    # veniva dirottato sull'uscita a mercato: in paper il ciclo chiudeva in
    # profitto, in live lo stesso ciclo poteva chiudere in perdita.
    # Spegnendola si torna a quel comportamento — ma DICHIARATO in pagina, non
    # in silenzio. Non e' un parametro di strategia: e' una valvola di
    # sicurezza sul percorso di esecuzione.
    "live_resting_enabled": (True, bool, None, None, None),
    "pre_entry_ttl_s": (60, int, 5, 3600, None),
    "pre_max_cycles": (10, int, 0, 100, None),
    "pre_reentry_cooldown_s": (60, int, 0, 3600, None),
    "pre_last_entry_min": (10, int, 1, 120, None),
    "last_entry_persist": (True, bool, None, None, None),
    "last_entry_ticks_above": (0, int, 0, 3, None),
    "cancel_unmatched_after_ko_s": (120, int, 0, 900, None),
    # ---- dal fischio d'inizio: uscita a +N tick e gol precoce (13/09) ----
    # La posizione Under 3.5 portata in gioco tenta PRIMA di uscire in profitto:
    # lay a ko_green_ticks tick sotto il nostro prezzo d'ingresso, tenuta per
    # ko_green_window_s dal fischio. Non si abbina -> copertura piena sull'Over 4.5.
    "ko_green_enabled": (True, bool, None, None, None),
    "ko_green_ticks": (2, int, 1, 10, None),
    "ko_green_window_s": (180, int, 0, 900, None),
    # ⚠️ ORDINE DELL'UTENTE 16/09 — QUESTO PARAMETRO NON HA PIU' EFFETTO.
    # L'uscita al fischio e' una lay APPOGGIATA in OGNI modalita' (paper e
    # live): resta sul book e non si ri-presenta piu' a ritmo. Governava la
    # ri-presentazione del percorso taker, che non esiste piu' (25-32 chiamate
    # REST per una sola uscita). La chiave resta — spegnerla vorrebbe dire
    # rompere i parametri gia' salvati sul DB e nella UI — ma nessun ramo la
    # legge: la scheda parametri lo DICHIARA invece di farlo credere.
    "ko_green_retry_s": (5, int, 1, 60, None),
    # Gol PRECOCE (dentro la finestra, ancora scoperti e non usciti): si annulla
    # l'uscita e si entra una SECONDA volta sull'Under 3.5 al miglior prezzo —
    # la quota e' salita, quindi alza la media e sfrutta il tempo senza gol.
    "second_entry_enabled": (True, bool, None, None, None),
    "second_entry_stake_pct": (50.0, float, 0.0, 200.0, None),
    # Copertura a DUE tranche: la prima dopo early_goal_cover_delay_s dal GOL,
    # la seconda dopo early_goal_cover2_delay_s dall'abbinamento della prima.
    # La seconda NON e' "l'altra meta'": e' il RESIDUO ricalcolato sulla quota
    # dell'Over di quel momento e su quanto la prima ha gia' garantito.
    "early_goal_cover_delay_s": (120, int, 0, 900, None),
    "early_goal_cover_pct": (50.0, float, 0.0, 100.0, None),
    "early_goal_cover2_delay_s": (180, int, 0, 900, None),
    # ---- copertura live ----
    "cover_enabled": (True, bool, None, None, None),
    "cover_profit_factor": (1.2, float, 1.0, 3.0, None),
    "cover_policy": ("auto", str, None, None, ("auto", "immediate", "wait")),
    # attesa "intelligente ma non lenta": si aspetta SOLO se l'hazard di gol nei 3'
    # (max fra Atlante empirico e modello λ-residue con pressione) e' basso, la P(4)
    # di mercato e' bassa, la quota Over NON e' gia' buona e il risparmio atteso
    # sulla copertura nei prossimi cover_wait_step_min vale almeno cover_wait_min_gain_pct
    "cover_wait_hazard_max": (0.06, float, 0.0, 1.0, None),
    "cover_wait_max_min": (10, int, 0, 45, None),
    "cover_wait_p4_max": (0.16, float, 0.0, 1.0, None),
    "cover_good_price": (7.0, float, 1.01, 50.0, None),
    "cover_wait_min_gain_pct": (8.0, float, 0.0, 100.0, None),
    "cover_wait_step_min": (5, int, 1, 20, None),
    "cover_postgoal_delay_s": (45, int, 0, 300, None),
    "cover_max_goals": (2, int, 0, 4, None),
    "cover_rounding": ("ceil", str, None, None, ("ceil", "floor", "nearest")),
    "cover_max_overshoot_pct": (30.0, float, 0.0, 200.0, None),
    # importi ESATTI al centesimo (copertura 3.61, stake 1.23): sotto-minimo / fuori passo via
    # Betfair/stream/trading/submin.py (place-and-trim, come Bet Angel/Fairbot). False = legalizza .it
    "exact_sizes": (True, bool, None, None, None),
    # ---- cash-out globale ----
    "cashout_profit_pct": (5.0, float, 0.5, 50.0, None),
    "cashout_base": ("total", str, None, None, ("total", "under")),
    "cashout_place_at_ticks": (0, int, 0, 3, None),
    # CERT. 12/09 (osservato dal vivo) — CUSCINETTO in tick sulla COPERTURA.
    # La copertura si piazzava al best back ESATTO: con il ritardo di
    # piazzamento in gioco il prezzo si muove e l'ordine muore. Misurato: 188
    # tentativi per 13 coperture abbinate (93% di fallimenti), e tre partite
    # finite a -10,00 perche' scoperte. Piazzando N tick SOTTO il best si paga
    # una quota un po' peggiore ma si ENTRA: per una protezione e' il
    # compromesso giusto (2 tick su 4,60 = 4,40: costo ~0,70 EUR contro un
    # rischio di 10,00 EUR).
    "cover_place_at_ticks": (2, int, 0, 6, None),
    # cash-out INTELLIGENTE (engine.smart_cashout): chiude prima della soglia quando tenere
    # non vale il rischio (punteggio caldo, hazard/pressione alti vicino alla soglia,
    # valore atteso dell'attesa < valore attuale). MAI sotto cashout_smart_min_pct.
    "cashout_smart_enabled": (True, bool, None, None, None),
    "cashout_smart_min_pct": (2.0, float, 0.0, 50.0, None),
    "cashout_smart_tolerance_pct": (2.0, float, 0.0, 50.0, None),
    "cashout_smart_hazard_hot": (0.10, float, 0.0, 1.0, None),
    "cashout_smart_pressure_hot": (1.15, float, 1.0, 1.25, None),
    "cashout_smart_goals_hot": (3, int, 0, 8, None),
    "cashout_smart_ev_margin_pct": (1.0, float, 0.0, 50.0, None),
    "close_retry_s": (10, int, 1, 600, None),
    "close_max_attempts": (20, int, 1, 100, None),
    # ---- uscite HT / 2T con perdita tollerata ----
    # mode "model": chiude se il valore certo di oggi >= EV a fine gara - premio al rischio
    # (risk_premium% x P(4 gol) x capitale), P(4) prudente = max(modello/empirico, mercato);
    # senza dati di modello ricade sulla regola fissa "perdita <= ht_loss_pct". "fixed" = solo la regola fissa.
    "loss_exit_mode": ("model", str, None, None, ("model", "fixed")),
    # CERT. 12/09 — 50 -> 10. Il premio SOTTRAE valore alla soglia, quindi fa
    # chiudere PRIMA. Ma il disastro dei 4 gol e' gia' dentro ``ev_hold``
    # (P(4) x P&L(4) e' uno dei termini della somma): sottrarne un altro pezzo
    # proporzionale a P(4) conta lo stesso rischio DUE VOLTE. Col 50% il bot ha
    # chiuso in perdita quattro Under che il mercato dava ancora FAVORITI al
    # 57-66% (Catania, Sparta Praga, Cukaricki, Granada): tutte e quattro le
    # partite sono finite sotto i 3,5 gol e l'Under avrebbe VINTO. Sulle 7
    # uscite in perdita della storia, tenere valeva +21,37 invece di -19,56.
    # Resta un premio piccolo come avversione al rischio, non come secondo
    # conteggio della stessa perdita.
    "loss_exit_risk_premium_pct": (10.0, float, 0.0, 300.0, None),
    "loss_exit_p4_prudent": (True, bool, None, None, None),
    "loss_exit_max_pct": (0.0, float, 0.0, 100.0, None),
    "loss_exit_emp_min_n": (200, int, 20, 5000, None),
    "ht_loss_exit_enabled": (True, bool, None, None, None),
    "ht_loss_pct": (25.0, float, 0.0, 100.0, None),
    # 13/09 — da 2 a 3 su richiesta dell'utente: con DUE gol la partita non e'
    # ancora compromessa (ne servono altri due per perdere l'Under 3.5) e
    # chiudere in perdita li' e' prematuro. La regola parte dal TERZO gol.
    "ht_loss_goals_min": (3, int, 0, 8, None),
    "ht_loss_goals_max": (4, int, 0, 8, None),
    "h2_loss_exit_enabled": (True, bool, None, None, None),
    "h2_loss_pct": (25.0, float, 0.0, 100.0, None),
    "h2_loss_from_min": (46, int, 45, 100, None),
    "h2_loss_to_min": (85, int, 45, 100, None),
    # ---- re-ingresso Under (gol + 3.5) ----
    "reentry_enabled": (True, bool, None, None, None),
    "reentry_green_ticks": (2, int, 1, 10, None),
    "reentry_max_goals": (1, int, 0, 1, None),
    "reentry_until_min": (45, int, 0, 100, None),
    # 0 = NESSUNA chiusura forzata: la lay a +N tick resta sul book fino a fine gara (specifica utente)
    "reentry_exit_until_min": (0, int, 0, 100, None),
    "reentry_price_min_over_entry": (True, bool, None, None, None),
    "reentry_hold_if_loss": (False, bool, None, None, None),
    # ---- settlement / rischio ----
    # intervallo fra due letture REST del book a mercato chiuso (service.py):
    # mai un poll stretto su un mercato gia' chiuso. Minimo effettivo 5 s.
    "settle_confirm_s": (60, int, 0, 600, None),
    "max_open_matches": (10, int, 1, 90, None),
    "daily_loss_stop": (50.0, float, 0.0, 100_000.0, None),
    "max_liability_per_match": (0.0, float, 0.0, 100_000.0, None),
    "event_loss_cap_pct": (100.0, float, 0.0, 500.0, None),
    # dedup dei log ripetitivi per partita (skip / no_fill / riconciliazione):
    # lo stesso motivo non viene riscritto piu' di una volta ogni N secondi.
    "skip_log_interval_s": (300, int, 10, 3600, None),
    # ---- quanto spesso si disturba il database (13/09) ----
    # Il budget di IO di Supabase non e' infinito: finito quello, l'istanza viene
    # strozzata e i tempi di risposta esplodono (guides/troubleshooting/
    # exhaust-disk-io). Misurato: una lettura per chiave primaria arrivata a 39
    # secondi, e la query che il ciclo fa ogni secondo che smette di rispondere.
    # Questi parametri NON toccano la logica di trading: dicono solo ogni quanto
    # si richiede al database una cosa che nel frattempo non e' cambiata.
    #
    # il FEED: MISURATO il 13/09 — il produttore riscrive ogni ~22 s (una sola
    # upsert per giro). Rileggerlo ogni 2 s vuol dire dieci letture identiche per
    # ogni pubblicazione, circa 300 KB l'una (57 righe col payload intero): 150
    # KB al secondo di JSON serializzato tutto il giorno, per niente. La
    # freschezza continua a giudicarsi sull'``updated_at`` (``feed.feed_fresh``):
    # rileggere una riga non la ringiovanisce.
    "feed_cache_s": (4.0, float, 0.0, 30.0, None),
    # le PARTITE: il servizio e' l'UNICO che scrive mike_events, quindi la sua
    # copia in memoria e' la verita'. La rilettura completa serve solo a
    # riallinearsi dopo un riavvio o una modifica fatta da fuori.
    "events_reload_s": (60.0, float, 0.0, 600.0, None),
    # gli AGGREGATI governano lo stop giornaliero: non e' una decisione al secondo
    "aggregates_cache_s": (20.0, float, 0.0, 300.0, None),
    # la riparazione dello specchio gambe <-> righe e' una RETE DI SICUREZZA,
    # non un passaggio del flusso: per partita basta ogni mezzo minuto
    "reconcile_every_s": (30.0, float, 0.0, 600.0, None),
    # quando non c'e' NIENTE che si muove (nessuna partita in gioco, nessun
    # ordine vivo, nessuna richiesta) il ciclo rallenta da solo
    "idle_cycle_s": (5.0, float, 1.0, 60.0, None),
    # ---- quanto spesso si SCRIVE sul database (13/09, secondo tempo) ----------
    # Sulle LETTURE il lavoro era fatto (i parametri qui sopra). Ma su un
    # database a corto di IO una SCRITTURA costa piu' di una lettura: l'UPSERT
    # riscrive la riga INTERA, aggiorna gli indici, produce WAL e da' lavoro
    # all'autovacuum. E la riga ``mike_events`` non e' piccola: dentro ci sono
    # ``live``, ``ctx``, ``positions``, ``dossier``, ``markets``, tutti JSON.
    # Riscriverla piu' volte al secondo, per partita, e' il modo peggiore di
    # spendere il budget.
    #
    # Il freno e' il "write-on-change": si riscrive solo se e' cambiato
    # QUALCOSA DI SOSTANZIALE (vedi service._signature). Restano fuori dal
    # confronto i campi che si muovono DA SOLI: l'ora di pubblicazione, l'eta'
    # del feed, il book che oscilla di un tick. Ma l'ora di pubblicazione serve
    # davvero alla scheda — ci calcola sopra un'eta' che TICKA, ed e' il
    # semaforo dei bottoni che mandano ordini veri — quindi non si puo'
    # semplicemente smettere di scriverla: va rinfrescata con una CADENZA sua.
    #
    # 5 s e' l'equilibrio: la card somma l'eta' congelata del feed (1-3 s con lo
    # scanner vivo) al tempo passato dalla pubblicazione, e il badge diventa
    # ROSSO "FEED FERMO" — spegnendo il cash out — oltre i 20 s. Con 5 s il
    # peggio che si vede e' l'ambra, i bottoni restano vivi, e le scritture a
    # vuoto scendono da 60 a 12 al minuto per partita.
    "publish_heartbeat_s": (5.0, float, 0.0, 120.0, None),
    # Una partita solo OSSERVATA (nessuna gamba viva, niente da chiudere) non ha
    # nessun bottone da illuminare: li' l'eta' e' cosmetica e il battito puo'
    # essere molto piu' largo. E' la stragrande maggioranza delle righe nelle ore
    # pre-partita, ed e' quello che il 13/09 riempiva il log di POST.
    "publish_idle_heartbeat_s": (60.0, float, 0.0, 600.0, None),
    # una sola POST con tutte le righe da rinfrescare invece di una per partita
    # (l'upsert di PostgREST accetta una lista). A False si torna riga per riga.
    "events_batch_write": (True, bool, None, None, None),
    # ---- mike_control: il battito e le stats --------------------------------
    # La UI ascolta ``mike_control`` in REALTIME: ogni PATCH sveglia tutte le
    # pagine aperte. Le stats cambiano quasi sempre (il P&L aperto si muove col
    # book), quindi senza una cadenza si scriverebbe a ogni giro.
    # ``ServiceHealthChip.SERVICE_STALE_S`` dichiara il servizio morto a 45 s:
    # un battito ogni 20 s lascia due battiti di margine.
    "stats_min_s": (10.0, float, 0.0, 300.0, None),
    "heartbeat_min_s": (20.0, float, 0.0, 300.0, None),
}

# Parametri RIMOSSI dalla whitelist l'11/09/2026 (audit M3) perche' non avevano
# alcun effetto e la UI li mostrava come se lavorassero. Restano elencati qui
# per documentazione: se arrivano dalla UI vengono semplicemente scartati da
# ``merge_params`` (nessun errore, nessun comportamento nascosto).
#   max_matches         — diagnostica del catalogo proprio, che Mike non ha piu'
#                         (il pool dello scanner e' dinamico); il tetto vero e'
#                         ``max_open_matches``.
#   catalogue_refresh_s — nessun catalogo proprio: i mercati arrivano dal feed unico.
#   stream_extra_lines  — richiede una linea extra nello scanner (re-ingresso
#                         oltre la 4.5): non implementato, vedi COSTITUZIONE §10.3.
#   min_total_matched   — gate sullo "scambiato totale" del mercato. NON cablato
#                         di proposito: 3 ore prima del KO le linee O/U hanno uno
#                         scambiato bassissimo e una soglia di 2.000 EUR (il
#                         default che la UI mostrava) avrebbe azzerato ogni
#                         ingresso. La liquidita' che conta per un fill e' quella
#                         al BEST, gia' governata da ``pre_min_back_size_factor``.
#                         Se servira', va reintrodotto con default 0 (= spento).
REMOVED_PARAMS = ("max_matches", "catalogue_refresh_s", "stream_extra_lines", "min_total_matched")

# Parametri che il BACKEND onora ma che la whitelist frontend
# (``frontend/src/lib/mike.ts::MIKE_PARAM_FIELDS``) non espone ANCORA.
#
# Perche' esiste questa lista, invece di allineare subito la UI: aggiunti il
# 13/09/2026 nella sessione sulle SCRITTURE, con il perimetro limitato a
# ``Betfair/mike/*`` (``frontend/`` era in mano a un'altra sessione che ci
# stava scrivendo nello stesso momento). Il disallineamento e' quindi
# DICHIARATO, non nascosto: il test di contratto UI lo controlla contro questa
# lista invece di essere semplicemente ammorbidito.
#
# Nel frattempo si toccano da ``mike_control.params`` (passano da
# ``merge_params``, quindi con cast, clamp e default come tutti gli altri).
# Chi allineera' la UI deve SVUOTARE questa tupla: il test di contratto torna
# a pretendere la parita' piena da solo.
# Parametri che il backend onora ma che la pagina non espone ancora.
# DEVE RESTARE VUOTA: ogni cadenza che governa il comportamento del bot o il
# carico sul database va messa in mano al trader, non nascosta nel codice. La
# tupla esiste solo come valvola dichiarata per un parametro appena nato, e il
# test di contratto (``test_mike_certificazione_ui``) fallisce se una chiave ci
# resta dentro senza motivo scritto qui accanto.
BACKEND_ONLY_PARAMS: tuple[str, ...] = ()

DEFAULTS: dict[str, Any] = {k: v[0] for k, v in PARAM_SPEC.items()}


def _coerce(key: str, raw: Any) -> Any:
    default, cast, lo, hi, choices = PARAM_SPEC[key]
    try:
        if cast is bool:
            if isinstance(raw, str):
                val = raw.strip().lower() in ("1", "true", "yes", "on")
            else:
                val = bool(raw)
        elif cast is str:
            val = str(raw).strip()
        else:
            val = cast(raw)
    except (TypeError, ValueError):
        return default
    if choices is not None:
        return val if val in choices else default
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        if lo is not None and val < lo:
            val = lo if cast is float else int(lo)
        if hi is not None and val > hi:
            val = hi if cast is float else int(hi)
    return val


# coppie (min, max) che devono restare ordinate: se invertite tornano ENTRAMBE
# al default (fail-closed dichiarato, mai una finestra vuota silenziosa)
_ORDERED_PAIRS = (
    ("pre_entry_price_min", "pre_entry_price_max"),
    ("ht_loss_goals_min", "ht_loss_goals_max"),
    ("h2_loss_from_min", "h2_loss_to_min"),
)


def merge_params(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Default + SOLO le chiavi note, con cast, clamp e scelte. Chiavi ignote scartate.
    Le coppie min/max invertite tornano al default (review F0, MEDIUM #8)."""
    out = dict(DEFAULTS)
    if not raw:
        return out
    for key, value in raw.items():
        if key not in PARAM_SPEC or value is None:
            continue
        out[key] = _coerce(key, value)
    for lo_key, hi_key in _ORDERED_PAIRS:
        if out[lo_key] > out[hi_key]:
            out[lo_key] = DEFAULTS[lo_key]
            out[hi_key] = DEFAULTS[hi_key]
    return out


def commission_rate(params: dict[str, Any]) -> float:
    return float(params.get("commission_pct", DEFAULTS["commission_pct"])) / 100.0
