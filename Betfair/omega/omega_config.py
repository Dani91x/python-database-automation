"""omega_config — default e whitelist parametri (COSTITUZIONE_OMEGA.md §7).

La whitelist è la barriera di sicurezza backend: solo queste chiavi, con questi
tipi/limiti, vengono applicate dai ``params`` che arrivano dalla UI. Speculare
alla whitelist frontend in ``frontend/src/lib/omega.ts``.
"""
from __future__ import annotations

import math
from typing import Any, Callable

# Obiettivo giornaliero di default (colonna dedicata su omega_control).
DEFAULT_DAILY_GOAL = 250.0

# eventTypeId Betfair per il calcio.
FOOTBALL_EVENT_TYPE_ID = "1"

# customerStrategyRef (<=15 char) che marchia gli ordini Omega su Betfair.
CUSTOMER_STRATEGY_REF = "omega"


# (default, cast, min, max) — min/max None = non vincolato.
_SPEC: dict[str, tuple[Any, Callable[[Any], Any], float | None, float | None]] = {
    "price_min": (20.0, float, 1.01, 1000.0),
    "price_max": (120.0, float, 1.01, 1000.0),
    "entry_minute_min": (30, int, 0, 130),
    "entry_minute_max": (60, int, 0, 130),
    "max_events": (0, int, 0, 1000),
    "commission_pct": (5.0, float, 0.0, 20.0),
    "min_lay_liquidity": (5.0, float, 0.0, 100000.0),
    "min_stake": (0.5, float, 0.5, 1000.0),
    "include_aggregate": (False, bool, None, None),
    "stop_on_goal": (True, bool, None, None),
    "entry_window_source": ("score", str, None, None),  # 'score' (minuto+punteggio da live_now condiviso) | 'clock'
    "poll_interval_s": (20, int, 5, 600),
    "max_liability_per_match": (0.0, float, 0.0, 1_000_000.0),
    "daily_loss_cap": (0.0, float, 0.0, 1_000_000.0),
    "max_open_liability": (0.0, float, 0.0, 10_000_000.0),
    # Esecuzione via coda flumine (DEMO=LIVE, §6-bis): 'auto' = coda del runner
    # quando il gate passa (fallback legacy sempre disponibile) | 'rest' = forza
    # il percorso legacy (fill snapshot in paper, place REST FOK in live).
    "execution_mode": ("auto", str, None, None),
    # TTL quasi-FOK del place paper via flumine: senza fill sufficiente entro
    # questo tempo si accoda il cancel del residuo (vedi COSTITUZIONE §6).
    # SOLO PAPER: in live il FOK vero lo esegue Betfair (timeInForce).
    "paper_fill_ttl_s": (45, int, 5, 600),
    # KILL-SWITCH del LIVE via coda flumine (§6-bis LIVE, 2026-07-17): True =
    # il place live passa dalla coda del runner (book streamato + fill
    # dall'order stream, timeInForce=FILL_OR_KILL); False = live legacy puro
    # (place REST FOK diretto + riconciliazione polling), senza log di fallback.
    "omega_live_via_flumine": (True, bool, None, None),
    # hard deadline (s) dell'esito FOK live dallo specchio: oltre, il poll
    # riconcilia via REST (per bet_id) o revoca la richiesta mai presa in
    # carico — mai un pending live zombie.
    "live_fill_deadline_s": (20, int, 5, 300),
    # ---- OMEGA v2 (09/09 sera): 2 gambe per partita, selezione per MODELLO ----
    # 'legs' = HT-CS nel 1T + CS nel 2T sul risultato con probabilità di modello
    # più bassa | 'single' = motore v1 (una gamba CS, quota più alta) kill-switch
    "engine": ("legs", str, None, None),
    "ht_entry_min": (20, int, 0, 45),      # finestra gamba 1T (minuto reale dal feed)
    "ht_entry_max": (40, int, 0, 45),
    "ft_entry_min": (50, int, 45, 130),    # finestra gamba 2T
    "ft_entry_max": (80, int, 45, 130),
    "model_p_max_pct": (2.0, float, 0.01, 50.0),   # P(modello) massima del risultato layato
    "model_min_goal_distance": (2, int, 1, 5),     # gol AGGIUNTIVI minimi dal punteggio corrente
    # P di modello CALIBRATA nella selezione (Betfair/safe_strategy/calibration.py,
    # import guardato): 'auto' = usa il calibratore se c'è | 'off' = P grezza.
    # §16 seconda passata F-03: il calibratore condiviso (famiglie cs_cell/hts_cell) è
    # addestrato sulla P del modello "opportunità" della Safe Strategy, non su quella
    # di Omega: applicarlo qui non è una calibrazione. OFF finché non esiste una
    # famiglia alimentata dagli stati REC/paper di Omega; la coda è corretta dal
    # fattore continuo `model_tail_factor` (validato sullo storico).
    "model_calibration": ("off", str, None, None),
    "model_calibration_path": ("", str, None, None),   # vuoto = default del calibratore
    # ---- §14 (11/09): seconda gamba SEMPRE coperta, dati capillari ----
    # 'veto' = per la gamba 2T la P usata è max(P modello, P empirica HT→FT dai
    # dati storici, se il punteggio è ancora quello del 45′) | 'off' = solo modello
    "model_empirical": ("veto", str, None, None),
    # minuto massimo d'ingresso 2T entro cui il veto HT→FT si applica (la
    # tabella HT→FT copre tutto il 2° tempo: oltre sovrastimerebbe la P);
    # con la tabella PER MINUTO (§15) il veto vale a ogni minuto, per entrambe le gambe
    "model_empirical_max_minute": (60, int, 45, 90),
    # ---- §15: modello definitivo ----
    # λ impliciti nell'INTERO mercato (scala CS + linee O/U) quando fixture, λ
    # salvati e pre-KO mancano; sempre calcolati per l'audit (cross-check)
    "lambda_market_grid": (True, bool, None, None),
    # selezione con COSTO DI COPERTURA: fra i risultati a P equivalente (entro
    # band_ratio × la più bassa) vince il più economico da coprire subito
    "select_cost_aware": (True, bool, None, None),
    "select_p_band_ratio": (2.0, float, 1.0, 10.0),
    # cartellini gialli dal feed nei tassi residui (moltiplicatori calibrati per lega)
    "model_use_yellow_cards": (True, bool, None, None),
    # fattore di coda (§15): P del modello ≤ 5 % moltiplicata per questo valore
    # (banco di validazione 11/09: 1,1–1,8 secondo minuto e campione → 1,3; usato SOLO
    # se il calibratore condiviso non ha una tabella per la famiglia; 1 = nessuna correzione)
    "model_tail_factor": (1.3, float, 0.5, 5.0),
    # λ dal mercato Over/Under live quando mancano fixture e quote pre-KO
    # (scanner riavviato a partita in corso, lega senza fixture): True = mai
    # una gamba saltata per "no_model_lambdas" se il mercato a gol è in stream
    "lambda_live_fallback": (True, bool, None, None),
    # §16 — incertezza sui λ (coefficiente di variazione della mistura lognormale:
    # 0 = Poisson puro; 0,30 ≈ coda binomiale negativa osservata sui dati)
    "model_lambda_cv": (0.30, float, 0.0, 1.0),
    # §16 — selezione conservativa: P = centro log-pool (modello ∥ mercato) + k·SE;
    # 0 = solo il centro (raccomandato finché il banco non misura la SE)
    "select_k_se": (0.0, float, 0.0, 3.0),
    # §16 — ranking EV: P di dover coprire (costo del green-up) e peso del costo
    "select_p_hedge": (0.5, float, 0.0, 1.0),
    "select_ev_kappa": (1.0, float, 0.0, 5.0),
    # ---- GREEN-UP AUTOMATICO (10/09, §12): la scommessa diventa un trade ----
    "greenup_enabled": (True, bool, None, None),
    "greenup_mode": ("auto", str, None, None),          # 'auto' | 'off'
    "greenup_trigger_distance": (1, int, 0, 3),         # bancato raggiungibile con ≤ N gol → uscita
    "greenup_price_trigger_ratio": (0.5, float, 0.05, 1.0),  # lay ≤ ratio × ingresso → valutazione
    "greenup_settle_delay_s": (30, int, 0, 600),        # assestamento del mercato dopo un gol
    "greenup_hold_max_risk": (0.02, float, 0.0, 1.0),   # P(perdita) ≤ → si tiene
    "greenup_risk_cap": (0.15, float, 0.0, 1.0),        # P(perdita) ≥ → si esce (caso vivo 10/09: 0.12 → tengo)
    "greenup_ev_margin": (0.10, float, 0.0, 1000.0),    # EUR: bloccato ≥ EV(tengo) − margine → esce
    # Sopra greenup_risk_cap si esce solo se il prezzo vale almeno l'EV del tenere
    # meno questa frazione della liability (premio pagato per la certezza).
    # 0 = mai sotto l'EV; 1 = vecchio tetto secco, uscita a qualunque prezzo.
    "greenup_risk_premium_pct": (0.05, float, 0.0, 1.0),
    "greenup_take_profit_frac": (0.9, float, 0.1, 1.0), # cash-out blocca ≥ frac dello stake…
    "greenup_take_profit_minute": (80, int, 0, 130),    # …dal minuto → take-profit
    "greenup_retry_s": (20, int, 2, 600),               # cooldown fra tentativi (residuo/errore)
    "greenup_max_attempts": (15, int, 0, 100),          # cap tentativi per posizione
    # 12/09: quanto il tetto di fine gara puo' superare il modello. Oltre questo
    # rapporto la quota e' considerata rotta e il modello resta l'unica stima
    # (trade 84: back 1.49 = 67,1% contro un modello all'8,5%, 8x: uscita da
    # -9,73 EUR su un lay che ha poi VINTO). 0 = nessun limite (vecchio
    # comportamento).
    "greenup_market_floor_max_ratio": (3.0, float, 0.0, 100.0),
    # ---- §18 (13/09): IL SOFTWARE DEVE LASCIAR RESPIRARE IL DATABASE ----
    # Il 13/09 Supabase e' andato giu' per esaurimento del budget di IO su disco:
    # HTTP 503 PGRST002 su tutto, letture per chiave primaria a 37 secondi, e per
    # rialzarlo e' servito un restart del progetto. Omega, da sola, chiedeva la
    # riga del feed di 34 partite UNA VOLTA AL SECONDO piu' lo stato dello
    # scanner allo stesso ritmo: non perche' servisse, ma perche' nessuno aveva
    # mai dichiarato ogni quanto si rilegge una cosa che nel frattempo non e'
    # cambiata. Questi parametri dichiarano quel "ogni quanto", uno per ogni
    # lettura periodica, tutti regolabili dalla UI, tutti a ZERO = comportamento
    # di prima (nessuna cache) senza toccare una riga di codice.
    #
    # NESSUNO DI ESSI CAMBIA UNA VIRGOLA DELLA LOGICA DI TRADING. La freschezza
    # del dato continua a essere giudicata sull'``updated_at`` della RIGA
    # (FEED_MAX_AGE_S / DECISION_MAX_AGE_S / CASHOUT_FEED_MAX_AGE_S): una riga
    # vecchia resta vecchia anche se la rileggiamo adesso, quindi allungare la
    # cache non puo' mai far passare per buone quote vecchie — al massimo fa
    # saltare una decisione, che e' il lato giusto in cui sbagliare.
    #
    # ``feed_cache_s`` e' il piu' corto di tutti perche' il feed e' l'unica
    # lettura che decide un ORDINE (selezione, sizing, green-up): 2 s contro i
    # 15/25 s oltre i quali la riga viene comunque scartata.
    "feed_cache_s": (2.0, float, 0.0, 30.0),
    # Lo stato dello scanner serve solo a dire "lo scanner e' vivo, quindi una
    # riga non riscritta di recente e' comunque l'ultimo stato". Il valore in
    # cache viene INVECCHIATO del tempo passato, quindi l'eta' che ne esce e'
    # esatta al secondo; l'unico effetto di una cache lunga e' che un heartbeat
    # NUOVO si vede con qualche secondo di ritardo, cioe' si crede lo scanner
    # piu' morto di quanto sia: fail-safe, mai il contrario.
    "scanner_status_cache_s": (10.0, float, 0.0, 300.0),
    # La RPC degli aggregati scorre l'intera omega_trades e governa stop
    # giornaliero, cap di perdita e numeri di testata: non e' una decisione al
    # secondo. Dopo un piazzamento / un settlement / un green-up si RICALCOLA
    # subito (forza=True), quindi i numeri che il bot usa per fermarsi sono
    # sempre aggiornati all'ultima cosa successa.
    "aggregates_cache_s": (20.0, float, 0.0, 300.0),
    # "Che cosa ho gia' fatto io": gambe gia' piazzate, eventi gia' toccati,
    # budget dei tentativi falliti. Le scrive QUESTO stesso processo, quindi fra
    # una rilettura e l'altra la copia in memoria E' la verita' (lo scan ci
    # scrive dentro la gamba appena piazzata). NON copre le guardie scritte
    # dalla UI (missioni, trade manuali): quelle restano lette a ogni giro.
    "sets_cache_s": (30.0, float, 0.0, 600.0),
    # Timbro dei risultati reali 1T/2T sulle posizioni recenti: e' una rete di
    # sicurezza contabile, non un passaggio del flusso — un risultato non cambia
    # piu' di una volta al minuto e il settlement lo completa comunque dal
    # WINNER del mercato.
    "results_every_s": (60.0, float, 0.0, 600.0),
    # Missioni: punteggio/fase/suggerimenti per la pagina. E' territorio
    # dell'utente, che legge e clicca — non un loop di trading. A 5 s la UI
    # resta reattiva e si smette di leggere active_missions + un
    # trades_for_event per missione a ogni giro quando il poll e' aggressivo.
    "missions_every_s": (5.0, float, 0.0, 120.0),
    # LA POSIZIONE DI CONTO (16/09, R9): ogni quanti secondi si rilegge su
    # Betfair, PER MERCATO, se la posizione del bot esiste ancora — cioe' se
    # l'utente non l'ha chiusa fuori dall'app. Sono DUE chiamate REST per
    # mercato (ordini correnti + regolati, senza filtro di strategia): a 120 s
    # una chiusura fatta a mano si scopre entro due minuti, e nel frattempo la
    # protezione non fa danni (il green-up chiede comunque prezzi freschi).
    # Zero = a ogni giro (piu' reattivo, molto piu' caro: si usa nei test).
    "conto_every_s": (120.0, float, 0.0, 3600.0),
    # Rinfresco della cache eventi (una chiamata REST Betfair + una replace):
    # era una costante nel codice, ora e' un parametro come tutti gli altri.
    "events_refresh_s": (1800.0, float, 0.0, 86400.0),
    # Stats a bot FERMO: era una costante nel codice. A bot fermo non c'e'
    # niente da decidere, basta far sapere alla pagina che il servizio e' vivo.
    "idle_stats_s": (60.0, float, 0.0, 600.0),
    # RITMO ADATTIVO. Il ciclo pieno serve quando qualcosa si muove DA SOLO:
    # una posizione aperta o in attesa di esito, una missione attiva, una
    # richiesta dalla UI, una partita gia' dentro la finestra d'ingresso. La
    # notte, o fra una giornata di partite e l'altra, girare al ritmo pieno vuol
    # dire solo bruciare il budget di IO del database per rileggere cose ferme.
    # Zero = disattivato (si usa sempre poll_interval_s, comportamento di prima).
    "idle_cycle_s": (60.0, float, 0.0, 600.0),
    # ---- OMEGA V3 (16/09 sera): lay 1 EUR, margine k misurato, uscita a PROPOSTA ----
    # LO SWITCH. 2 = motore v2 (quello fino al 17/09: due mercati, size dal
    # target di giornata, green-up automatico). 3 = motore v3 (`omega_v3.py`):
    # SOLO Correct Score, due celle in due momenti, stake fisso, margine k sulla
    # probabilita' FUSA, nessuna chiusura automatica (l'uscita e' una proposta).
    # DEFAULT 3 dal 17/09 (decisione del coordinatore sui dati, CRONOSTORIA
    # «DECISIONI DEL COORDINATORE admin-b1 h16:40»): resta comunque l'UTENTE ad
    # accendere il bot dalla UI — questo dice solo QUALE motore usa quando lo
    # accende.
    "strategy_version": (3, int, 2, 3),
    # ordine dell'utente: «INGRESSO STANDARD: 1 euro in LAY». In v3 la size NON
    # viene piu' dall'obiettivo di giornata (era la radice di R1 e R3, §1.2 del
    # progetto): e' questa, e basta.
    "v3_stake_eur": (1.0, float, 0.01, 100.0),
    # il modello che ha vinto il banco (`tools/banco_modelli.py`, 16/09):
    # 'gamma_poisson' = aggiornamento bayesiano coniugato (binomiale negativa);
    # gli altri restano selezionabili per poter rifare il confronto dal vivo.
    "v3_modello": ("gamma_poisson", str, None, None),
    # margine minimo sulla probabilita': P_nostra <= p_implicita / k.
    # 17/09: il pavimento scende da 2,0 a **1,11**, che e' il bias PRUDENTE
    # misurato in gioco (M4M5M6_2026-09-17.md §2.3, estremo basso dell'intervallo
    # sulla fascia operabile). Il 2,0 del 16/09 (K_MISURATO_2026-09-16.md) era il
    # k richiesto in assenza di una misura in gioco: con quella misura il
    # margine richiesto e' il bias dimostrato, non un numero di prudenza.
    # Decisione del coordinatore sui dati (CRONOSTORIA, admin-b1 h16:40).
    "v3_k_minimo": (1.11, float, 1.0, 20.0),
    # casi minimi perche' la tabella storica abbia diritto di veto
    "v3_empirical_min_n": (200, int, 0, 1000000),
    # FINESTRE delle due gambe, sul minuto REALE dal feed (mai l'orologio).
    # 17/09: in V3 il mercato e' UNO SOLO, il CORRECT SCORE, e «due ingressi»
    # vuol dire DUE CELLE DIVERSE in DUE MOMENTI diversi (M4M5M6 §2.3: sul
    # HALF_TIME_SCORE il bias prudente e' 0,92 nella fascia 2-5 % e sotto il 2 %
    # non ci sono uscite: quella gamba non si fa).
    #   gamba A: 1'-44'   (il Correct Score e' quotabile dal 1')
    #   gamba B: 46'-85'  (dopo l'intervallo, su una cella DIVERSA)
    # I nomi delle chiavi restano `v3_ht_*` / `v3_ft_*` perche' sono le stesse
    # due gambe di sempre (`phase` 'ht_cs'/'ft_cs'): cambia il mercato, non la
    # struttura — rinominarle avrebbe rotto righe, aggregati e UI gia' scritti.
    "v3_ht_entry_min": (1, int, 0, 45),
    "v3_ht_entry_max": (44, int, 0, 45),
    "v3_ft_entry_min": (46, int, 0, 130),
    "v3_ft_entry_max": (85, int, 45, 130),
    # CAP DI SICUREZZA. In v2 sono tutti a ZERO = spenti; in v3 NON sono zero.
    # 17/09: portati a 95 / 190 / 1.000 / 300 (decisione del coordinatore sui
    # dati). Il tetto di GAMBA a 95 EUR con stake 1,00 EUR vuol dire quota lay
    # massima 96: oltre, la cella si SCARTA (non si taglia la size, A9).
    # Restano dell'utente: si cambiano dal pannello, non dal codice.
    "v3_max_liability_per_leg": (95.0, float, 0.0, 1000000.0),
    "v3_max_liability_per_match": (190.0, float, 0.0, 1000000.0),
    "v3_max_open_liability": (1000.0, float, 0.0, 10000000.0),
    "v3_daily_loss_cap": (300.0, float, 0.0, 1000000.0),
    # con 1 EUR di lay la controparte che serve e' 1 EUR, non 5
    "v3_min_lay_liquidity": (1.0, float, 0.0, 100000.0),
    # gol AGGIUNTIVI minimi fra il punteggio corrente e quello bancato. 1 = mai il
    # risultato corrente (che e' il vincolo vero); 2 = anche mai a un gol.
    # 17/09: 2, cioe' nemmeno a un gol di distanza.
    "v3_distanza_minima_gol": (2, int, 1, 5),
    # LA FASCIA IN CUI SI OPERA, ed e' sulla **p_IMPLICITA AL TOCCO** (17/09).
    # [1,0 %, 2,0 %] di p_impl = quote lay circa **47,5-95**. E' la fascia in cui
    # il bias e' stato MISURATO in gioco: `tools/k_in_gioco.py` raggruppa per
    # fascia di p_impl, e M4M5M6 §2.3 dice che sotto l'1 % il bias non e'
    # misurato, mentre nella fascia 2-5 % il bias prudente vale **0,71**, cioe'
    # EV NEGATIVO. Una cella fuori fascia si scarta (`p_impl_sotto_fascia` /
    # `p_impl_oltre_fascia`) anche quando il margine sembra ottimo.
    #
    # ATTENZIONE, `v3_p_max_pct` fa DUE cose e sono due cose diverse:
    #   * tetto della FASCIA sulla p_implicita (sopra: bias sotto 1);
    #   * tetto DURO sulla P NOSTRA (semantica del 16/09, scarto
    #     `p_oltre_il_tetto`): non si banca una cella che il NOSTRO modello
    #     considera probabile, qualunque cosa dica il prezzo.
    "v3_p_max_pct": (2.0, float, 0.01, 50.0),
    "v3_p_min_pct": (1.0, float, 0.0, 50.0),
    # fusione col mercato (pool logaritmico in logit, pesi misurati per fascia in
    # `tools/banco_fusione.py`): 'auto' = fonde | 'off' = solo modello
    "v3_fusione_mercato": ("auto", str, None, None),
    # ---- LE PROPOSTE DI USCITA (17/09) ----
    # P MASSIMA TOLLERATA che il risultato bancato esca: oltre, il produttore
    # propone l'uscita col motivo `rischio` — non perche' sia un affare, ma per
    # ridurre il rischio. ZERO = SPENTA, ed e' il default: nessuna soglia nuova
    # si accende di iniziativa (regola dell'utente). Si accende dal pannello, in
    # punti percentuali (2.5 = 2,5%).
    "proposta_p_lose_max_pct": (0.0, float, 0.0, 100.0),
    # 24/09 - ORDINE DELL'UTENTE ("QUESTO PER TUTTI I BOT"): CHI esegue l'uscita
    # che il bot ha gia' calcolato (`omega_proposte`, motivi `blocca_il_profitto`
    # / `protezione` / `cap` / `rischio`). Non cambia NESSUN criterio d'uscita:
    #   'avvisa_e_proponi' (DEFAULT, fail-closed) = la proposta in scheda che
    #       firma l'utente, come dal 17/09;
    #   'automatico' = la stessa uscita la esegue il bot da solo, con l'audit
    #       della scelta dell'utente sulla riga e nell'attivita'.
    # Tutto cio' che non e' esattamente 'automatico' vale 'avvisa_e_proponi'.
    "uscite_protezione": ("avvisa_e_proponi", str, None, None),
}

# 24/09 - i due valori ammessi di `uscite_protezione` (il primo e' il default)
USCITE_PROTEZIONE_AMMESSE = ("avvisa_e_proponi", "automatico")

# Valori ammessi per i due `select` di V3 (specchio della UI, quando ci sara').
V3_MODELLI_AMMESSI = ("poisson", "dixon_coles", "dixon_robinson", "bivariato",
                      "gamma_poisson")

DEFAULTS: dict[str, Any] = {k: v[0] for k, v in _SPEC.items()}


def _coerce(key: str, raw: Any) -> Any:
    default, cast, lo, hi = _SPEC[key]
    try:
        if cast is bool:
            val = bool(raw) if not isinstance(raw, str) else raw.strip().lower() in ("1", "true", "yes", "on")
        else:
            val = cast(raw)
    except (TypeError, ValueError):
        return default
    if key == "entry_window_source" and val not in ("score", "clock"):
        return default
    if key == "execution_mode" and val not in ("auto", "rest"):
        return default
    if key == "engine" and val not in ("legs", "single"):
        return default
    if key in ("greenup_mode", "model_calibration") and val not in ("auto", "off"):
        return default
    # certificazione 12/09: ``model_empirical`` non era validato — un valore
    # qualsiasi ("xxx", "on") passava e il servizio (`!= "veto"`) lo leggeva
    # come OFF: veto empirico spento in silenzio da un refuso della UI
    if key == "model_empirical" and val not in ("veto", "off"):
        return default
    if key == "v3_modello" and val not in V3_MODELLI_AMMESSI:
        return default
    if key == "v3_fusione_mercato" and val not in ("auto", "off"):
        return default
    if key == "uscite_protezione":
        # fail-closed: il bot chiude da solo SOLO se l'utente l'ha scritto
        v = str(raw if raw is not None else "").strip().lower()
        return v if v in USCITE_PROTEZIONE_AMMESSE else default
    if key == "model_calibration_path":
        # None/null dalla UI → "" (prima str(None) = "None": un percorso inesistente)
        return "" if raw is None else str(val).strip()
    # certificazione 12/09: NaN/inf superano i clamp (``nan < lo`` è False) →
    # un prezzo o un cap "nan" entrava nella whitelist come valido
    if isinstance(val, float) and not math.isfinite(val):
        return default
    if lo is not None and isinstance(val, (int, float)) and val < lo:
        val = lo if cast is float else int(lo)
    if hi is not None and isinstance(val, (int, float)) and val > hi:
        val = hi if cast is float else int(hi)
    return val


def resolve_params(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Applica la whitelist: default + solo le chiavi note, coerce e clamp.

    Chiavi sconosciute vengono ignorate (I5/§7). ``price_min`` non può
    superare ``price_max`` (in tal caso si scambiano).
    """
    out = dict(DEFAULTS)
    if raw:
        for k, v in raw.items():
            if k in _SPEC:
                out[k] = _coerce(k, v)
    if out["price_min"] > out["price_max"]:
        out["price_min"], out["price_max"] = out["price_max"], out["price_min"]
    # la FASCIA di probabilita' di V3: un pavimento sopra il tetto non e' una
    # fascia, e' un insieme vuoto (nessuna cella passerebbe, in silenzio)
    if out["v3_p_min_pct"] > out["v3_p_max_pct"]:
        out["v3_p_min_pct"], out["v3_p_max_pct"] = out["v3_p_max_pct"], out["v3_p_min_pct"]
    for lo_k, hi_k in (("ht_entry_min", "ht_entry_max"), ("ft_entry_min", "ft_entry_max"),
                       ("v3_ht_entry_min", "v3_ht_entry_max"),
                       ("v3_ft_entry_min", "v3_ft_entry_max")):
        if out[lo_k] > out[hi_k]:
            out[lo_k], out[hi_k] = out[hi_k], out[lo_k]
    if out["entry_minute_min"] > out["entry_minute_max"]:
        out["entry_minute_min"], out["entry_minute_max"] = (
            out["entry_minute_max"],
            out["entry_minute_min"],
        )
    # green-up: la soglia di "margine ampio" non può superare il cap di rischio
    if out["greenup_hold_max_risk"] > out["greenup_risk_cap"]:
        out["greenup_hold_max_risk"] = out["greenup_risk_cap"]
    # G1 — IN V3 NON ESISTE UNA CHIUSURA AUTOMATICA. Ordine dell'utente del 16/09:
    # «il green-up/cash-out passa dalla Control Room come proposta con avviso e
    # decide l'utente». Il modo piu' robusto di garantirlo non e' un `if` dentro
    # al servizio (che qualcuno un giorno riscrive): e' spegnere il green-up
    # automatico QUI, nella whitelist, dove passa ogni parametro che arriva dalla
    # UI. Chi mettesse `greenup_mode='auto'` dal pannello con V3 acceso se lo
    # vedrebbe riportare a 'off' a ogni giro, e la certificazione (G1) lo verifica.
    # Restano attive le protezioni che NON chiudono: settlement e riconciliazione.
    if int(out.get("strategy_version") or 2) >= 3:
        out["greenup_mode"] = "off"
        out["greenup_enabled"] = False
        out["engine"] = "legs"     # il motore v1 "quota piu' alta" non esiste in V3
    return out


def parametri_v3(params: dict[str, Any]) -> dict[str, Any]:
    """Il sottoinsieme che riguarda V3, con i nomi senza prefisso: e' quello che
    `omega_engine.seleziona_v3` e la certificazione si passano. Chiave unica di
    lettura, cosi' nessuno va a pescare `params['v3_...']` a mano in giro."""
    p = resolve_params(params) if not params or "strategy_version" not in params else params
    return {
        "attivo": int(p.get("strategy_version") or 2) >= 3,
        "stake": float(p.get("v3_stake_eur") or DEFAULTS["v3_stake_eur"]),
        "modello": str(p.get("v3_modello") or DEFAULTS["v3_modello"]),
        "k_minimo": float(p.get("v3_k_minimo") or DEFAULTS["v3_k_minimo"]),
        "empirical_min_n": int(p.get("v3_empirical_min_n", DEFAULTS["v3_empirical_min_n"])),
        "ht_entry_min": int(p.get("v3_ht_entry_min", DEFAULTS["v3_ht_entry_min"])),
        "ht_entry_max": int(p.get("v3_ht_entry_max", DEFAULTS["v3_ht_entry_max"])),
        "ft_entry_min": int(p.get("v3_ft_entry_min", DEFAULTS["v3_ft_entry_min"])),
        "ft_entry_max": int(p.get("v3_ft_entry_max", DEFAULTS["v3_ft_entry_max"])),
        "max_liability_per_leg": float(p.get("v3_max_liability_per_leg",
                                             DEFAULTS["v3_max_liability_per_leg"])),
        "max_liability_per_match": float(p.get("v3_max_liability_per_match",
                                               DEFAULTS["v3_max_liability_per_match"])),
        "max_open_liability": float(p.get("v3_max_open_liability",
                                          DEFAULTS["v3_max_open_liability"])),
        "daily_loss_cap": float(p.get("v3_daily_loss_cap", DEFAULTS["v3_daily_loss_cap"])),
        "min_lay_liquidity": float(p.get("v3_min_lay_liquidity",
                                         DEFAULTS["v3_min_lay_liquidity"])),
        "distanza_minima_gol": int(p.get("v3_distanza_minima_gol",
                                         DEFAULTS["v3_distanza_minima_gol"])),
        "p_max": float(p.get("v3_p_max_pct", DEFAULTS["v3_p_max_pct"])) / 100.0,
        "p_min": float(p.get("v3_p_min_pct", DEFAULTS["v3_p_min_pct"])) / 100.0,
        "fusione": str(p.get("v3_fusione_mercato") or DEFAULTS["v3_fusione_mercato"]) == "auto",
        "commissione": float(p.get("commission_pct", DEFAULTS["commission_pct"])) / 100.0,
    }
