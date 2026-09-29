# Inventario Mike - AREA C: come Mike manda e segue gli ordini

**Intervallo letto (tutto, riga per riga):**
- `Betfair/mike/service.py` righe 1-3250 (fino a `_request_approva_uscita` compresa; `_request_cancel` a riga 3253 e' fuori area).
- `Betfair/mike/porta_ordini.py` righe 1-225 (tutto il file).

**Letto solo quanto basta (fuori area, per capire le chiamate):** `service.py` 4290-4530 (`_run_event`: dove vengono chiamate le funzioni di quest'area), 4682-4737 (`_event_rows`, `_trade_row_for_leg`, `_trade_unknown_outcome`), 5077-5186 (`_mark_trade_cancelled`), 3440-3496 (`run_once`, inizio); `Betfair/safe_strategy/execution.py` 134-214 (`_live_brake`, `_freno_aperture`), 478-651 (`_place_via_canale`, `_annulla_via_canale`), 653-987 (`place`); `Betfair/safe_strategy/porta_ordini.py` (costanti, `terminale`, memoria); `Betfair/omega/omega_market.py` 696-775 (`place_order_live`), 950-979 (`place_submin_live`), 1345-1369 (`order_state_by_bet_id`); `Betfair/mike/engine.py` (ruoli, stati, `stato_mercato`, freno copertura 1595-1661); `Betfair/stream/trading/stato_mercato.py` 54-216; `Betfair/stream/trading/controls.py` 107-132; `Betfair/mike/config.py`; `Betfair/mike/db.py` 518-525; `Betfair/mike/COSTITUZIONE_MIKE.md` §0-§7, §15, §16.1, §17.3.

**Numero di schede: 62** (la 24 e' una tabella riassuntiva per tipo d'ordine).

## Elenco di TUTTE le funzioni e classi dell'intervallo, con la scheda che le copre

### service.py (righe 1-3250)
| Funzione / classe | Riga | Scheda |
|---|---|---|
| `mike_live_abilitato` | 92 | 1 |
| `_LiveNonAbilitato` (classe) | 101 | 1 |
| `_pretendi_live_abilitato` | 106 | 1 |
| `_RealMarket` (classe) | 120 | 2 |
| `_RealMarket._bind_strategy_ref` | 122 | 2 |
| `_RealMarket.read_book` | 135 | 2 |
| `_RealMarket.place_order_live` | 141 | 2 |
| `_RealMarket.place_submin_live` | 152 | 2 |
| `_RealMarket.cancel_order_live` | 168 | 2 |
| `_RealMarket.list_current_orders` | 189 | 2 |
| `_RealMarket.list_cleared_orders` | 197 | 2 |
| `_RealMarket.list_account_orders` | 211 | 3 |
| `_RealMarket.list_account_cleared_orders` | 217 | 3 |
| `_RealMarket.market_profit_and_loss` | 223 | 3 |
| `_now` | 234 | 4 |
| `_iso` | 238 | 4 |
| `_p_under35_calibrata` | 290 | 8 |
| `_Cache` (classe) | 325 | 9 |
| `_Cache.__init__` | 330 | 9 |
| `_Cache.fresco` | 334 | 9 |
| `_Cache.metti` | 337 | 9 |
| `_Cache.svuota` | 341 | 9 |
| `svuota_le_cache` | 365 | 10 |
| `_legs_from_json` | 393 | 7 |
| `_ctx_from_row` | 430 | 6 |
| `_row_from_ctx` | 446 | 6 |
| `_corpo_sostanziale` | 509 | 12 |
| `_signature` | 521 | 12 |
| `_punteggio_ingresso` | 532 | 13 |
| `_trade_row` | 546 | 14 |
| `_is_missing_column_error` | 586 | 15 |
| `_insert_trade_row` | 597 | 15 |
| `execute_place` | 618 | 16, 17, 18, 19, 20, 21, 22, 23 |
| `_esito_rifiuto_mercato` | 946 | 25 |
| `market_winner` | 1010 | 27 |
| `final_total_from_books` | 1027 | 27 |
| `market_voided` | 1047 | 27 |
| `settle_plan` | 1069 | 27 |
| `_aggregates_cached` | 1099 | 28 |
| `_aggregates` | 1120 | 28 |
| `_books_ripiego_rest` | 1163 | 29 |
| `_esposizione_mike` | 1193 | 30 |
| `_scanner_stato` | 1209 | 31 |
| `_scanner_age` | 1216 | 31 |
| `_live_exit_override` | 1235 | 32 |
| `_params_for` | 1268 | 33 |
| `_log_throttled` | 1279 | 34 |
| `_rifiutata` | 1304 | 26 |
| `_is_resting_leg` | 1330 | 35 |
| `_gia_appoggiata` | 1349 | 36 |
| `_porta_paper` | 1407 | 37 |
| `_attendi_terminale` | 1418 | 37 |
| `_nota_senza_runner` | 1429 | 37 |
| `_senza_runner` | 1433 | 37 |
| `_num_evento` | 1449 | 38 |
| `_segui_ordini_paper_su_runner` | 1456 | 38, 39, 40 |
| `_piazza_resting_paper` | 1665 | 41 |
| `_freno_gia_appoggiata` | 1727 | 36 |
| `_resting_e_chiusura` | 1751 | 42 |
| `_resting_in_attesa` | 1762 | 43 |
| `_freno_aperture_rest` | 1801 | 44 |
| `_rifiuto_non_di_mercato` | 1821 | 45 |
| `_ferma_aperture` | 1826 | 45 |
| `_causa_aperture_ferme` | 1851 | 45 |
| `_aggiorna_aperture_ferme` | 1862 | 45 |
| `_freno_resting_paper` | 1887 | 42 |
| `_piazza_resting_live` | 1903 | 46 |
| `_aggiorna_riga_resting` | 2092 | 47 |
| `campo_ordine` | 2168 | 48 |
| `_num_ordine` | 2185 | 48 |
| `ordine_normalizzato` | 2199 | 48 |
| `ref_ordine_di_riga` | 2219 | 49 |
| `_ordine_della_riga` | 2229 | 49 |
| `_ordine_di` | 2290 | 49 |
| `_segui_resting_live` | 2318 | 50 |
| `_gambe_appoggiate_vive` | 2430 | 51 |
| `_classifica_ordine` | 2435 | 52 |
| `_rileggi_ordine_appoggiato` | 2467 | 52 |
| `_chiudi_gamba_scaduta` | 2510 | 53 |
| `_applica_esito_riapertura` | 2549 | 53 |
| `azzera_cache_di_processo` | 2653 | 11 |
| `_netto_su_selezione` | 2696 | 54 |
| `_posizione_attesa` | 2724 | 54 |
| `_refs_di_mike` | 2738 | 54 |
| `_sorveglia_posizione_di_conto` | 2760 | 54 |
| `_sorveglia_sospensione` | 2872 | 51 |
| `_sorveglia_mercato_copertura` | 2965 | 55 |
| `_result` | 3012 | 56 |
| `_richiesta_non_di_questa_partita` | 3032 | 57 |
| `process_requests` | 3077 | 56 |
| `_id_approvazione` | 3181 | 58 |
| `_approvazione_eseguita` | 3192 | 58 |
| `_chiave_gamba` | 3208 | 58 |
| `_request_approva_uscita` | 3216 | 58 |

Costanti e memorie di modulo dell'intervallo (non funzioni, coperte comunque): `_LOCK_PORT`, `_PENDING_STALE_S`, `_SETTLE_RETRY_S`, `_SETTLE_MAX_WAIT_S`, `_DAILY_STOP_LOGGED`, `_ROW_MISSING_GRACE_S`, `_MATCH_OVER_S`, `_MATCH_LIKELY_OVER_S`, `_CRITICAL_LOG_EVERY_S`, `_STALE_REQUEST_MIN`, `_STRATEGY_REF`, `_LAST_HEARTBEAT`, `_CONFIG_WARNED`, `_GUARDIA_AVVIO`, `ACTIVE_STATES` (scheda 5); `_CTX_FIELDS` (scheda 6); `_ULTIMI_PARAMS`, `_CACHE_FEED`, `_CACHE_AGGREGATI`, `_CACHE_EVENTI`, `_EVENTI_LETTI_A`, `_RICONCILIATO_A`, `_SCRITTO_A` (scheda 9); `_MALFORMED_LOGGED`, `_MALFORMED_EVERY_S` (scheda 7); `_LIVE_VOLATILI`, `_CTX_VOLATILI` (scheda 12); `_SCHEMA_ERR_MARKERS` (scheda 15); `_VOID_MARKET_STATUS`, `_VOID_RUNNER_STATUS` (scheda 27); `_LAST_AGG` (scheda 28); `_ULTIMO_STATO_SCANNER` (scheda 31); `APERTURE_MIKE`, `_RIPIEGO_REST_MIN_S`, `_RIPIEGO_REST_ULTIMO`, `_FLUSSO_CRITICO`, `_FLUSSO_RIPIEGO` (scheda 29); `_SCADENZA_TAKER_PAPER_S`, `ATTESA_ESITO_TAKER_MAX_S`, `_SENZA_RUNNER_LOG_S`, `_SENZA_RUNNER_LOGGATO`, `_NOTE_SENZA_RUNNER` (scheda 37); `_ATTESE_RESTING` (scheda 43); `_PREFISSI_NON_DI_MERCATO` (scheda 45); `_ALIAS_ORDINE`, `_ASSENTE` (scheda 48); `_ESITO_VIVO`, `_ESITO_SCADUTO`, `_ESITO_ABBINATO`, `_ESITO_PARZIALE`, `_ESITO_IGNOTO` (scheda 52); `_CONTO_LETTO_A`, `_CONTO_EPS` (scheda 54); `_CACHE_DI_PROCESSO` (scheda 11); `_REJECT_CODES` (scheda 56).

### porta_ordini.py (tutto)
| Funzione / classe | Riga | Scheda |
|---|---|---|
| `ref_ordine` | 50 | 59 |
| `ref_annullo` | 56 | 59 |
| `adatta_comando` | 63 | 60 |
| `VistaMike` (classe) | 115 | 61 |
| `VistaMike.__init__` | 122 | 61 |
| `VistaMike.attore` | 132 | 61 |
| `VistaMike.memoria` | 136 | 61 |
| `VistaMike.disponibile` | 139 | 61 |
| `VistaMike.invia` | 145 | 61 |
| `VistaMike.esiti` | 154 | 61 |
| `VistaMike.attendi_esito_bet` | 157 | 61 |
| `PortaCanaleMike` (classe) | 161 | 62 |
| `PortaCanaleMike.avvia` | 164 | 62 |
| `_crea_porta` | 172 | 62 |
| `porta_mike` | 182 | 62 |
| `porta_esistente` | 196 | 62 |
| `installa` | 201 | 62 |
| `azzera` | 209 | 62 |
| `vista` | 221 | 62 |

Costanti del modulo: `ATTORE`, `STRATEGY_REF`, `TABELLA_ORIGINE`, `PREFISSO_REF`, `FOK`, `REF_MAX`, `MOTIVO_NON_VALIDO`, `CHIAVI_COMANDO`, `Ack`, `terminale`, `FASI_TERMINALI`, `_PORTA`, `_LOCK` (schede 59-62).

Nota di numerazione: le schede 16-23 sono tutte `execute_place` (e' la funzione piu' lunga, spezzata per passaggi); la scheda 24 e' la tabella riassuntiva "ogni ordine, che tipo e cosa succede se...". Le schede sono in ordine di lettura logica, non di riga.

---

## PARTE 1 - GLI INTERRUTTORI E LO SPORTELLO VERSO BETFAIR

### 1. L'interruttore dei soldi veri (MIKE_LIVE_ENABLED)
- **Cosa fa**: e' l'ultima barriera prima che un ordine con soldi veri parta. Se l'interruttore nel file di configurazione del PC non e' acceso, qualsiasi ordine reale (punta, banca, annullo) viene fermato PRIMA di contattare Betfair, con un avviso critico.
- **Quando scatta**: a ogni tentativo di ordine reale passato dallo sportello di Mike: piazzamento normale, piazzamento sotto il minimo, annullamento. Il valore si rilegge a OGNI chiamata (spegnerlo ha effetto subito, senza riavviare).
- **Cosa succede dopo**: se spento, l'ordine non parte, viene sollevato l'errore "live non abilitato" (`_LiveNonAbilitato`). Chi chiama (`execution.place`) lo tratta come esito IGNOTO (vedi scheda 22: l'eccezione generica finisce in `_reconciling`), quindi la gamba va in riconciliazione. Le letture (ordini vivi, regolati, posizione di conto, libro prezzi) NON sono bloccate da questo interruttore.
- **Numeri**: `MIKE_LIVE_ENABLED`, variabile d'ambiente, default **spento** (`C.env_bool("MIKE_LIVE_ENABLED", False)`); valori che la accendono: `1`, `true`, `yes`, `on` (`config.py:62-66`).
- **Esempio**: partita armata in live, il bot decide la copertura Over 4.5 da 2,26 EUR; con `MIKE_LIVE_ENABLED` vuoto nel `.env` nessuna chiamata va a Betfair; nel registro compare "ORDINE REALE BLOCCATO (place_order_live)".
- **Cosa vede l'utente**: nel log del processo una riga CRITICA in italiano ("ORDINE REALE BLOCCATO ... impostare MIKE_LIVE_ENABLED=1 nel .env e riavviare l'app"). In pagina, indirettamente, la riga che resta in riconciliazione.
- **Dove**: `service.py:92-98` (`mike_live_abilitato`), `:101-103` (`_LiveNonAbilitato`), `:106-114` (`_pretendi_live_abilitato`); chiamata in `:144`, `:162`, `:184`.
- **Paper o live**: solo live. Il paper non passa mai di qui.

### 2. Lo sportello REST di Mike verso Betfair (`_RealMarket`)
- **Cosa fa**: e' l'oggetto con cui Mike parla a Betfair usando la sessione condivisa di Omega (`omega_market`). Espone: lettura del libro prezzi di un mercato, piazzamento di un ordine, piazzamento sotto il minimo (place-and-trim), annullamento, elenco degli ordini vivi di Mike, elenco degli ordini regolati di Mike.
- **Quando scatta**: ogni volta che il servizio deve leggere/piazzare/annullare in live (e per leggere il libro nel regolamento e nel ripiego REST, anche in paper: `read_book`).
- **Cosa succede dopo**:
  - `_bind_strategy_ref`: prima di ogni operazione "marchia" la sessione con il riferimento di strategia `mike` (cosi' gli ordini di Mike non escono marchiati "omega").
  - `read_book(market_id, names)`: legge il libro via REST (nessun interruttore).
  - `place_order_live(**kw)`: pretende l'interruttore (scheda 1), marchia, aggiunge `strategy_ref="mike"` se non c'e', piazza.
  - `place_submin_live(**kw)`: idem, per importi sotto il minimo di Betfair (parcheggio a quota non abbinabile, taglio, riprezzo; di default ritira il non abbinato a fine sequenza: `omega_market.py:953`, `fill_or_kill=True`).
  - `cancel_order_live(bet_id, market_id, size_reduction)`: pretende l'interruttore, annulla davvero su Betfair (esiste dal 16/09).
  - `list_current_orders()`: ordini VIVI marchiati `mike` (filtrati per strategia).
  - `list_cleared_orders()`: ordini REGOLATI marchiati `mike`.
- **Numeri**: riferimento di strategia `mike` (`config.CUSTOMER_STRATEGY_REF`, `config.py:30`); porta del lucchetto del processo `MIKE_LOCK_PORT`, default 47319 (`service.py:47`, `config.py:32`).
- **Esempio**: lay appoggiata 10,14 EUR a 1,48: `place_order_live(market_id=..., selection_id=1222344, price=1.48, size=10.14, side="lay", customer_ref="mike-t4817", fill_or_kill=False)` con `strategy_ref="mike"`.
- **Cosa vede l'utente**: niente direttamente.
- **Dove**: `service.py:120-231`.
- **Paper o live**: `read_book` serve anche in paper (regolamento, ripiego REST); tutto il resto e' live. ATTENZIONE: lo sportello NON espone `order_state_by_bet_id` (vedi scheda 52 e "Cose strane").

### 3. Le letture della posizione di CONTO (ordini di chiunque)
- **Cosa fa**: tre letture che NON filtrano per strategia: gli ordini vivi di chiunque su un mercato (`list_account_orders`), quelli regolati di chiunque (`list_account_cleared_orders`), e il profitto/perdita di mercato di Betfair (`market_profit_and_loss`). Servono a capire se l'utente ha chiuso lui la posizione fuori dall'app.
- **Quando scatta**: le prime due solo da `_sorveglia_posizione_di_conto` (scheda 54), in live, al piu' ogni `reconcile_every_s` per partita. La terza non e' chiamata da nessuna parte del servizio (vedi "Cose strane").
- **Cosa succede dopo**: restituiscono elenchi; nessuna decisione qui.
- **Numeri**: cadenza `reconcile_every_s` = **30 s** di default (parametro UI, min 0, max 600; `config.py:336`).
- **Esempio**: mercato Under/Over 3.5 `1.234`: due chiamate REST (vivi + regolati) ogni 30 s mentre c'e' una posizione aperta.
- **Cosa vede l'utente**: niente.
- **Dove**: `service.py:210-228`.
- **Paper o live**: solo live (in paper la funzione che le usa esce subito).

### 4. Orologio e date
- **Cosa fa**: `_now` da' l'ora attuale in tempo universale; `_iso` trasforma un istante in testo data-ora (o niente se l'istante manca/e' zero).
- **Quando scatta**: dovunque serva l'ora.
- **Cosa succede dopo**: nessun effetto sugli ordini.
- **Numeri**: nessuno.
- **Esempio**: 1759140000 -> "2025-09-29T10:00:00+00:00".
- **Cosa vede l'utente**: niente.
- **Dove**: `service.py:234-239`.
- **Paper o live**: uguale.

### 5. Le costanti di tempo e le memorie del servizio (inizio file)
- **Cosa fa**: fissa i tempi che il servizio usa in molte funzioni (alcune fuori da quest'area).
- **Quando scatta**: sempre (valori fissi nel codice, NON modificabili dalla UI).
- **Cosa succede dopo**: vedi le schede che le usano.
- **Numeri** (tutti costanti nel codice, `service.py:47-72`):
  - `_PENDING_STALE_S` = **120 s**: una gamba taker "in attesa" senza esito oltre 120 s viene ritirata (esito noto) o mandata in riconciliazione (esito ignoto) - usata in `_run_event:4331` (fuori area).
  - `_SETTLE_RETRY_S` = **30 s** (ripiego fra due letture REST a mercato chiuso se `settle_confirm_s`=0).
  - `_SETTLE_MAX_WAIT_S` = **7200 s** (2 ore): oltre si regola con l'ultimo punteggio o ERROR.
  - `_ROW_MISSING_GRACE_S` = **600 s**: riga assente dal feed per meno di 10 minuti = transitoria.
  - `_MATCH_OVER_S` = **10800 s** (3 ore dal KO: partita finita comunque).
  - `_MATCH_LIKELY_OVER_S` = **6000 s** (KO + 100': riga sparita = partita finita).
  - `_CRITICAL_LOG_EVERY_S` = **45 s** (scheda 34).
  - `_STALE_REQUEST_MIN` = **10 minuti**: richieste UI rimaste "in lavorazione" oltre 10 minuti vengono chiuse in errore (usata in `run_once:3480`).
  - `_LOCK_PORT` = `MIKE_LOCK_PORT` (env) o **47319**.
  - `_STRATEGY_REF` = "mike".
  - `_GUARDIA_AVVIO` = guardia "all'avvio dell'app nessun bot apre" (`AA.Guardia("mike")`), usata in `run_once:3452`.
  - `ACTIVE_STATES` = tutti gli stati tranne SETTLED, ERROR, SKIPPED. Non usata da nessuna parte (vedi "Cose strane").
  - `_DAILY_STOP_LOGGED`, `_LAST_HEARTBEAT`, `_CONFIG_WARNED`: memorie di processo (stop giornaliero loggato una volta al giorno, firma dell'ultimo battito, ultimo avviso di configurazione).
- **Esempio**: una punta taker mandata alle 15:00:00 senza risposta: alle 15:02:00 scatta il controllo dei 120 s.
- **Cosa vede l'utente**: niente di diretto.
- **Dove**: `service.py:47-72`.
- **Paper o live**: uguale.

---

## PARTE 2 - LA MEMORIA DELLA PARTITA E LE MEMORIE TEMPORANEE

### 6. Che cosa Mike ricorda di una partita (salvataggio e rilettura)
- **Cosa fa**: trasforma la riga della partita salvata nel database (`mike_events`) nello stato di lavoro del motore, e viceversa. Elenca i campi che DEVONO sopravvivere a un riavvio.
- **Quando scatta**: a ogni lettura/scrittura della partita.
- **Cosa succede dopo**:
  - `_ctx_from_row`: stato (se manca: `WATCH`), gambe (scheda 7), numero del ciclo, prezzo d'ingresso iniziale; poi copia dal blocco `ctx` tutti i campi di `_CTX_FIELDS` non vuoti; il P&L regolato viene dalla colonna di testa `settled_pnl`.
  - `_row_from_ctx`: scrive stato, ciclo, prezzo iniziale, le gambe POTATE (quelle annullate e mai abbinate, oltre le ultime per ruolo, vengono tolte: `engine.prune_dead_legs`), il P&L regolato, e nel blocco `ctx` i campi di `_CTX_FIELDS` presi dal motore (vincono sui valori vecchi).
- **Numeri**: i campi ricordati (`service.py:245-287`): ultimo green, ultima azione, tentativi, rientro permesso/fatto, motivo di chiusura, copertura saltata, sequenza, chiusura manuale in corso, divieto di rientro, prezzo Under al fischio, orologio dal fischio (`live_since`), gol al fischio, momento del gol precoce, seconda puntata fatta, tranche della copertura e sua ora, copertura forzata, rifiuti del mercato (`rifiuti`), memoria della sospensione (`riapertura`), chiuso dall'utente fuori app, freno copertura (`cover_rifiuti`), ultimo stato mercato Over 4.5 (`cover_mercato`), proposta e approvazione dell'uscita, veto P Under 3.5 (`veto_u35`), aperture ferme (`aperture_ferme`).
- **Esempio**: il processo riparte al 20': grazie a `live_since` e `cover_stage` la copertura a tranche riprende dal punto giusto invece di ricominciare.
- **Cosa vede l'utente**: niente.
- **Dove**: `service.py:245-287`, `:430-443`, `:446-462`.
- **Paper o live**: uguale.

### 7. Gambe lette dal database e gamba "rovinata"
- **Cosa fa**: ricostruisce le gambe (ordini) della partita dal testo salvato. Se una gamba e' rovinata (non leggibile) NON la butta in silenzio: scrive un avviso critico, perche' sarebbe una posizione che il bot non vede piu'.
- **Quando scatta**: a ogni ricostruzione della partita.
- **Cosa succede dopo**: la gamba rovinata viene scartata (resta fuori dal ragionamento del bot!), nel log di processo compare "gamba MALFORMATA scartata"; nell'attivita' una riga `error` con motivo `leg_malformata` e `critical`, al massimo una volta ogni 300 s per partita.
- **Numeri**: `_MALFORMED_EVERY_S` = **300 s** (costante, `service.py:390`).
- **Esempio**: una gamba salvata con un campo di tipo sbagliato: il bot non la conta nella posizione; l'avviso ricompare ogni 5 minuti.
- **Cosa vede l'utente**: riga di attivita' `error` "leg_malformata" (critica).
- **Dove**: `service.py:389-427`.
- **Paper o live**: uguale.

### 8. La probabilita' calibrata dell'Under 3.5 per il veto
- **Cosa fa**: prende dal dossier della partita la probabilita' dell'Under 3.5 SOLO se viene dalla fonte calibrata; altrimenti dice "non c'e'" e il veto (motore) tace.
- **Quando scatta**: quando il servizio prepara i dati per il motore (`_run_event:4250`, fuori area).
- **Cosa succede dopo**: restituisce un numero fra 0 e 1, oppure niente se: il dossier non e' valido, la fonte non e' `calibrated`, il valore non e' un numero, o e' fuori da 0-1.
- **Numeri**: accetta solo 0 <= P <= 1.
- **Esempio**: dossier con `p_under35_fonte="calibrated"`, `p_under35_cal=0.71` -> 0,71; dossier scritto prima del 25/09 senza fonte -> niente.
- **Cosa vede l'utente**: niente qui.
- **Dove**: `service.py:290-301`.
- **Paper o live**: uguale.

### 9. Le memorie temporanee (per far respirare il database)
- **Cosa fa**: tiene in memoria per qualche secondo cose lette dal database, per non rileggerle a ogni giro. Non cambia la logica di trading, solo "ogni quanto si rilegge".
- **Quando scatta**: `_Cache.fresco(ora, durata)` dice se il valore c'e' ed e' piu' giovane della durata; `metti` lo salva con l'ora; `svuota` lo butta.
- **Cosa succede dopo**: memorie di modulo e a cosa servono:
  - `_CACHE_FEED`: il feed prezzi (durata `feed_cache_s`).
  - `_CACHE_AGGREGATI`: gli aggregati di giornata (durata `aggregates_cache_s`, scheda 28).
  - `_CACHE_EVENTI` + `_EVENTI_LETTI_A`: le partite seguite, rilette per intero ogni `events_reload_s`.
  - `_RICONCILIATO_A`: ultima riparazione dello specchio gambe/righe, per partita.
  - `_SCRITTO_A`: ultima scrittura della partita (orologio del battito di pubblicazione).
  - `_ULTIMI_PARAMS`: i parametri dell'ultimo giro (servono per decidere quanto aspettare).
- **Numeri** (parametri UI, `config.py`): `feed_cache_s` = **4,0 s** (0-30; ATTENZIONE: il commento a `service.py:320` e la Costituzione §17.3 dicono 2 s), `events_reload_s` = **60 s** (0-600), `aggregates_cache_s` = **20 s** (0-300), `reconcile_every_s` = **30 s** (0-600).
- **Esempio**: feed letto alle 15:00:00; fino alle 15:00:04 il giro usa la copia; la freschezza delle quote resta giudicata sull'ora di aggiornamento della riga, non su quando e' stata letta.
- **Cosa vede l'utente**: niente.
- **Dove**: `service.py:325-362`.
- **Paper o live**: uguale.

### 10. Svuotare le memorie temporanee
- **Cosa fa**: butta via tutto il letto: la prossima lettura va al database.
- **Quando scatta**: nei test e quando si vuole forzare un riallineamento.
- **Cosa succede dopo**: azzera `_ULTIMI_PARAMS`, il diario delle attese di riapertura (`_ATTESE_RESTING`), feed, aggregati, partite, riconciliazioni, scritture, battito, stato scanner, orologi del ripiego REST, i due promemoria del flusso, l'ora di lettura delle partite, e le righe arrivate dal canale del feed (`azzera_canale_scan`, fuori area).
- **Numeri**: nessuno.
- **Esempio**: dopo una modifica a mano del database, chiamarla fa rileggere tutto al giro dopo.
- **Cosa vede l'utente**: niente.
- **Dove**: `service.py:365-386`.
- **Paper o live**: uguale.

### 11. Azzeramento "come un processo appena acceso" (per il banco di replay)
- **Cosa fa**: riporta le memorie del modulo allo stato di un processo appena avviato; restituisce l'elenco di cio' che ha azzerato.
- **Quando scatta**: la usa il banco di replay all'inizio di ogni replay e nello scenario "riavvio" (`Betfair/mike/tools/replay_registrazioni.py:236,785`); in produzione nessuno la chiama.
- **Cosa succede dopo**: svuota le memorie elencate in `_CACHE_DI_PROCESSO` (stop giornaliero loggato, battito, avviso configurazione, partite, riconciliazioni, scritture, gambe malformate loggate, aggregati, ultima lettura del conto), poi `_ULTIMI_PARAMS`, `_EVENTI_LETTI_A`, la sveglia (`_SVEGLIA.azzera`) e il canale del feed. NON tocca `_ALIAS_ORDINE` (di proposito) e NON tocca il database.
- **Numeri**: nessuno.
- **Esempio**: scenario "riavvio" a meta' partita: la lettura del conto riparte subito invece di aspettare 30 s ereditati.
- **Cosa vede l'utente**: niente.
- **Dove**: `service.py:2648-2689`.
- **Paper o live**: uguale. Vedi "Cose strane" per le memorie che NON azzera.

### 12. "E' cambiato qualcosa?" (la firma della riga partita)
- **Cosa fa**: calcola un'impronta della riga della partita ignorando i campi che cambiano da soli (orologio, eta', libro prezzi, cash-out, hazard, probabilita' di modello...). Serve a decidere se riscrivere la riga nel database: se l'impronta non cambia, non si riscrive.
- **Quando scatta**: prima e dopo ogni giro della partita (`_run_event:4017`, `_persist:5500`) e sul battito (`run_once:3783`).
- **Cosa succede dopo**: toglie `updated_at`; dal blocco `live` toglie `published_at`, `published_ts`, `feed_age_s`, `scanner_age_s`, `books`, `total_matched`, `cashout`, `posizioni`, `hazard`, `hazard_atlas`, `hazard_model`, `pressure`, `hazard_n`, `hazard_nota`, `hazard_recupero_atteso_min`, `p4_market`, `p4_model`, `p_total_model`, `p_total_emp`, `p_over45_model`, `cover_gain_pct`, `model_probs`, `ko_drift_ticks`; dal blocco `ctx` toglie `last_reason`, `last_cashout`, `last_cover_wait`, `last_loss_exit`. Un campo nuovo non elencato conta come "sostanziale" (regola prudente: al massimo una scrittura in piu').
- **Numeri**: impronta MD5 del testo ordinato.
- **Esempio**: due giri a un secondo con solo il best back passato da 1,50 a 1,51: stessa impronta, nessuna riscrittura.
- **Cosa vede l'utente**: niente.
- **Dove**: `service.py:486-526`.
- **Paper o live**: uguale.

---

## PARTE 3 - LA RIGA DI RISERVA E IL PIAZZAMENTO TAKER (`execute_place`)

### 13. Il punteggio d'ingresso scritto sulla riga
- **Cosa fa**: scrive il punteggio "casa-ospiti" al momento dell'ordine; se manca uno dei due numeri scrive niente (non piu' "None-None").
- **Quando scatta**: quando si prepara la riga dell'ordine (`_run_event:4396`).
- **Cosa succede dopo**: solo informazione sulla riga; nessuna decisione la legge.
- **Numeri**: nessuno.
- **Esempio**: 1 e 0 -> "1-0"; pre-partita -> niente.
- **Cosa vede l'utente**: nella Control Room "ingresso 1-0" o niente.
- **Dove**: `service.py:532-543`.
- **Paper o live**: uguale.

### 14. La riga di riserva dell'ordine (`mike_trades`)
- **Cosa fa**: prepara la riga che viene scritta nel database PRIMA di mandare l'ordine ("prima si prenota, poi si piazza").
- **Quando scatta**: per ogni ordine taker (`execute_place`) e ogni lay appoggiata (paper e live).
- **Cosa succede dopo**: la riga contiene partita, ruolo (anche in `strategy`), ciclo, mercato e tipo mercato (`OVER_UNDER_35` o `OVER_UNDER_45`), selezione e nome, lato, modalita', quota, importo, esposizione, commissione, persistenza della gamba, minuto e punteggio d'ingresso, stato **`pending`**, P&L 0, origine (`manual` se ruolo `manual_close` o motivo `manual`, altrimenti `auto`), `signal_key` = riferimento della gamba. Nel `meta`: fase `reserved`, riferimento gamba, "finale", eventuale chiave dell'approvazione dell'utente; sulle gambe di CHIUSURA anche il tipo d'uscita (`exit_kind`), il motivo (`exit_reason`) e quale gamba chiude (`closes_ref`). Se si conosce la riga chiusa: `closes_trade_id`.
- **Numeri**: esposizione: banca = importo x (quota - 1), arrotondata al centesimo; punta = importo. Commissione = `commission_pct`/100 = **0,05** (parametro UI 5%, 0-20).
- **Esempio**: banca 10,14 EUR a 1,48 -> esposizione 10,14 x 0,48 = 4,87 EUR; punta 10 EUR a 1,50 -> esposizione 10 EUR.
- **Cosa vede l'utente**: la riga "in attesa" nella scheda Trade.
- **Dove**: `service.py:546-580`.
- **Paper o live**: uguale; il campo `mode` dice quale. ATTENZIONE: `persistence` della gamba (es. PERSIST) finisce solo sulla riga, non sull'ordine vero (scheda 24).

### 15. Scrittura tollerante della riga di riserva
- **Cosa fa**: scrive la riga. Se il database dice che la colonna `closes_trade_id` non esiste (migrazione non applicata), riscrive la riga senza quella colonna tenendo il riferimento nel `meta` (`closes_trade_id_pending`) e scrive un avviso `schema_warn`. Su QUALUNQUE altro errore (rete, tempo scaduto) NON riprova: l'errore risale, perche' riprovare potrebbe creare una riga doppia.
- **Quando scatta**: ad ogni riserva.
- **Cosa succede dopo**: restituisce il numero della riga; il chiamante, se non c'e' numero o c'e' errore, NON piazza l'ordine (riga `error` "reserve_failed" nell'attivita').
- **Numeri**: l'errore e' "di colonna mancante" solo se il messaggio contiene il nome della colonna E uno fra `42703`, `pgrst204`, `does not exist`, `unknown column`, `schema cache` (`service.py:583`).
- **Esempio**: database senza la migrazione `mike_bot_v2.sql`: la chiusura `under_close` viene comunque prenotata e piazzata.
- **Cosa vede l'utente**: attivita' `schema_warn` oppure `error` "reserve_failed".
- **Dove**: `service.py:583-615`.
- **Paper o live**: uguale.

### 16. `execute_place` - l'ordine dei controlli prima di un ordine TAKER
- **Cosa fa**: e' la porta unica di ogni ordine "che prende" il prezzo del mercato (punta d'ingresso, chiusure, green-up taker, copertura, seconda puntata, re-ingresso, ultimo ingresso). Prima di prenotare controlla, in QUESTO ordine, e si ferma al primo no (la gamba diventa `cancelled` e ritorna "cancelled"):
  1. mercato o selezione sconosciuti -> attivita' `skip` "mercato/selezione assenti";
  2. gamba di CHIUSURA con un'altra uguale gia' in attesa (scheda 17);
  3. copertura Over 4.5 col freno scattato (scheda 18);
  4. mercato non APERTO (scheda 19);
  5. prezzi dal ripiego REST e gamba che apre rischio (scheda 19);
  6. feed stantio (scheda 19);
  7. prezzo non piu' disponibile (scheda 19);
  8. modalita' prova (`dry`): nessun ordine, attivita' `would_place`;
  9. legalizzazione dell'importo se gli importi esatti sono spenti (scheda 20);
  10. in paper: runner non raggiungibile (scheda 21);
  11. prenotazione della riga (scheda 15); poi piazzamento (schede 21 e 22).
- **Quando scatta**: chiamata da `_run_event` per ogni gamba nuova non appoggiata (`service.py:4522`) e per le azioni differite rimaste in memoria (`:4413`).
- **Cosa succede dopo**: ritorna `open` (abbinata), `cancelled` (nessun ordine a mercato), `pending` (in attesa), `pending_reconcile` (esito ignoto).
- **Numeri**: vedi le schede 17-23.
- **Esempio**: punta Under 3.5 10 EUR a 1,50 con feed vecchio: si ferma al punto 6, nessuna riga, attivita' `no_fill` "feed_stantio".
- **Cosa vede l'utente**: le attivita' indicate per ogni ramo.
- **Dove**: `service.py:618-943`.
- **Paper o live**: i controlli 1-9 sono identici; cambiano 10-11.

### 17. Freno "una sola gamba di chiusura in volo"
- **Cosa fa**: se la gamba e' di CHIUSURA (`under_green`, `ko_green`, `under_close`, `over_close`, `reentry_green`, `manual_close`) e c'e' gia' una riga `pending` con lo stesso ruolo, ciclo e lato, non ne piazza una seconda.
- **Quando scatta**: primo controllo sostanziale di `execute_place`, solo sulle chiusure. Se le righe della partita non si riescono a leggere: si comporta come se ci fosse gia' (prudenza: nel dubbio nessun ordine).
- **Cosa succede dopo**: gamba `cancelled`; il motore viene informato che "la richiesta e' stata rifiutata" (`_rifiutata`, scheda 26) con motivo "gamba di chiusura gia' in volo"; attivita' `place_saltato` critica con il numero della riga gia' in volo; ritorna "cancelled".
- **Numeri**: nessuna soglia.
- **Esempio**: 15/09 Trinec: il bot avrebbe creato 60 righe `under_close` da 0,20 EUR; con il freno ne nasce una.
- **Cosa vede l'utente**: attivita' `place_saltato` "gamba_di_chiusura_gia_in_volo".
- **Dove**: `service.py:656-669`; il confronto in `_gia_appoggiata` (`:1349-1387`, scheda 36).
- **Paper o live**: uguale.

### 18. Seconda barriera del freno della copertura
- **Cosa fa**: se la gamba e' la copertura Over 4.5 (`over_cover`) e il freno della copertura e' scattato (troppi rifiuti uguali, scheda 25), nessun ordine parte.
- **Quando scatta**: solo con ruolo `over_cover` e contesto partita presente; la prima barriera e' nel motore (`engine._freno_copertura`, area motore).
- **Cosa succede dopo**: gamba `cancelled`; attivita' `skip` critica "copertura_bloccata" con codice d'errore, conteggio, massimo e stato `LIVE_COVER_BLOCKED`; ritorna "cancelled". Le uscite e chiusure non sono toccate.
- **Numeri**: `cover_rifiuti_max` = **3** (parametro UI, 1-20).
- **Esempio**: tre rifiuti `CANCELLED_NOT_PLACED` di fila: il quarto tentativo non esce.
- **Cosa vede l'utente**: attivita' `skip` "copertura_bloccata"; si sblocca con "Riprendi" (scheda 56) o con un codice d'errore diverso.
- **Dove**: `service.py:677-690`.
- **Paper o live**: uguale.

### 19. Mercato non aperto, ripiego REST, feed stantio, prezzo sparito
- **Cosa fa**: quattro controlli sul mercato prima di prenotare.
- **Quando scatta / cosa succede dopo**:
  - **Mercato non APERTO** (libro mancante o stato diverso da `OPEN`): gamba `cancelled`, attivita' `skip` con lo stato per nome (`aperto`/`sospeso`/`chiuso`/`ignoto`; `INACTIVE` conta come chiuso; stato mancante = ignoto). Non conta come rifiuto del mercato.
  - **Prezzi dal ripiego REST** (lo scanner ha il flusso fermo e i prezzi vengono letti in REST): se la gamba APRE rischio (`under_entry`, `under_last`, `under_second`, `reentry` - la copertura `over_cover` NO) -> nessun ordine, attivita' `no_fill` "flusso_interrotto". Chiusure, green-up e copertura partono.
  - **Feed stantio** (`feed_fresh` falso): NESSUN ordine, ne' apertura ne' chiusura, in paper E in live (decisione dell'utente 28/09, applicata il 29/09). Attivita' `no_fill` "feed_stantio".
  - **Prezzo non piu' disponibile**: per una punta serve miglior punta >= quota chiesta; per una banca serve miglior banca <= quota chiesta (tolleranza 0,000000001). Se no: gamba `cancelled`, il motore viene informato (`_rifiutata`: "prezzo non disponibile (x)") cosi' non ripete la stessa identica richiesta, attivita' `no_fill` con ruolo, importo, quota voluta, quota e importo disponibili.
- **Numeri**: la freschezza del feed e' decisa fuori area (`feed.feed_fresh`: nella Costituzione riga > 15 s E scanner muto > 30 s; parametri `feed_max_age_s`, `scanner_alive_max_s`).
- **Esempio**: chiusura `under_close` banca a 1,40 mentre la miglior banca e' 1,42 -> no_fill "available 1.42", nessuna riga.
- **Cosa vede l'utente**: attivita' `skip` o `no_fill` col motivo.
- **Dove**: `service.py:691-740`; `APERTURE_MIKE` a `:1154`.
- **Paper o live**: identico.

### 20. Importi legalizzati (solo se gli importi esatti sono spenti)
- **Cosa fa**: se dalla UI si spengono gli "importi esatti", una PUNTA sotto il minimo di Betfair viene alzata al minimo legale italiano.
- **Quando scatta**: lato punta, `exact_sizes` spento, importo che richiederebbe il place-and-trim (`engine.needs_submin`). Il codice non guarda il ruolo (vale per ogni punta, non solo le aperture).
- **Cosa succede dopo**: importo cambiato, attivita' `size_legalized` "da ... a ...".
- **Numeri**: `exact_sizes` = **acceso** di default (parametro UI); arrotondamento `cover_rounding` = **"ceil"** (per eccesso; scelte ceil/floor/nearest); minimo .it punta 2,00 EUR, passo 0,50 (`engine.legalize_back_size`).
- **Esempio**: copertura 1,35 EUR con importi esatti spenti -> 2,00 EUR.
- **Cosa vede l'utente**: attivita' `size_legalized`.
- **Dove**: `service.py:746-753`.
- **Paper o live**: uguale.

### 21. `execute_place` in PAPER: l'ordine lo esegue il runner
- **Cosa fa**: in paper l'ordine NON viene piu' "riempito in casa" guardando il libro: va al runner (simulatore flumine) sul canale di comando di Mike, che applica ritardo di piazzamento, coda, parziali, scadenze. Runner giu' = ordine NON eseguito, dichiarato.
- **Quando scatta**: modalita' `paper`, dopo tutti i controlli della scheda 16.
- **Cosa succede dopo**, passo per passo:
  1. Si chiede la porta del runner (`_porta_paper(appoggiata=False)`, scheda 37). Se non c'e': gamba `cancelled`, NESSUNA riga, avviso `skip` "paper_senza_runner" (al massimo ogni 60 s per partita), e le APERTURE si fermano finche' la causa non cambia (`_ferma_aperture`, scheda 45).
  2. Si prenota la riga (scheda 15). Se fallisce: nessun ordine.
  3. Si segna "questa gamba chiude" nel `meta` di esecuzione se la riga ha `closes_trade_id`, o se il ruolo e' di chiusura (valore `-1` = "chiude, riferimento ignoto").
  4. Se e' la copertura: si fa partire l'orologio del ritmo minimo PRIMA di mandare (`engine.segna_tentativo_copertura`).
  5. **Freno unico sulle aperture** (`blocco_paper`): se NON e' una chiusura si legge il freno d'emergenza condiviso (scheda 44). Se tirato: niente comando, esito "errore" col motivo (trattato come il live, scheda 22 punto "rifiuto").
  6. Altrimenti `execution.place` manda il comando al runner: stessa quota (arrotondata al tick nella direzione giusta: banca verso l'alto, punta verso il basso), importo ridotto alla liquidita' al best se piu' grande. Sotto il minimo, con la porta taker, il runner fa il place-and-trim con FOK; se il libro dello stream dice gia' che non si puo' abbinare, rifiuto certo senza comando (`execution._rifiuto_submin_fok`).
  7. Se il runner ha preso il comando (esito "in attesa") e NON e' un esito ignoto: il servizio **aspetta** l'esito finale del runner fino a min(**15 s**, ritardo di piazzamento del mercato + **3 s**), poi rilegge subito gli esiti (`_segui_ordini_paper_su_runner`, schede 38-40) e ritorna `open`, `cancelled` o `pending_reconcile`. Se l'esito non arriva in tempo, la gamba resta `pending` e la chiude il giro dopo (attivita' `place_pending`).
  8. Se l'esito e' "errore" con nota di runner giu' (`canale_giu`, `paper_no_fill`, `canale_premarcatura_fallita`, `canale_senza_trade_id`, `paper_senza_runner`): riga in `error` motivo `paper_senza_runner`, avviso, aperture ferme.
- **Numeri**: `ATTESA_ESITO_TAKER_MAX_S` = **15 s** (costante; il banco di replay la mette a 0: `mike/tools/replay_registrazioni.py:456`); `+3 s` cablato; canale del runner porta `LIVE_LOCAL_WS_PORT` (env) o **47331**.
- **Esempio**: punta Under 3.5 10 EUR a 1,50 in gioco, ritardo 5 s: il giro aspetta fino a 8 s; il runner dice "abbinato 10 a 1,50" -> gamba `open`, riga `open`, attivita' `place` "runner_paper:abbinato".
- **Cosa vede l'utente**: attivita' `place` / `no_fill` / `skip paper_senza_runner` / `place_pending`.
- **Dove**: `service.py:754-766`, `:805-822`, `:829-853`, `:854-883`; `execution.py:774-788`, `:478-604`.
- **Paper o live**: solo paper. NOTA: durante l'attesa (fino a 15 s) il giro intero e' fermo.

### 22. `execute_place` in LIVE: REST "tutto o niente"
- **Cosa fa**: in live l'ordine va a Betfair in REST diretto con la sessione condivisa, "tutto o niente" (FILL_OR_KILL) e persistenza LAPSE; sotto il minimo con il place-and-trim che ritira il non abbinato.
- **Quando scatta**: modalita' `live`, dopo i controlli della scheda 16 e la riserva.
- **Cosa succede dopo**:
  - Modo d'esecuzione: `rest`, a meno che `MIKE_USE_FLUMINE_QUEUE` sia acceso (allora `auto`, coda del runner) - default spento (`service.py:781`).
  - Freni del live (solo se NON e' una chiusura; `execution._live_brake`): freno d'emergenza condiviso (env `LIVE_KILL_SWITCH` o interruttore del database), poi modo ordini (tetto `LIVE_ORDER_MODE` dell'env e scelta della Control Room: se non e' LIVE niente apertura). Freni non leggibili = niente apertura. La copertura `over_cover` NON e' una chiusura: e' frenata.
  - Poi `MIKE_LIVE_ENABLED` (scheda 1) su ogni ordine, chiusure comprese.
  - **Abbinato** (`open`): gamba `open` con abbinato e prezzo medio veri; riga aggiornata con stato `open`, quota, importo abbinato, esposizione, bet_id, `meta.phase=open`, e le colonne "chiesto/abbinato/residuo" (`X.aggiorna_trade`); attivita' `place` con chiesto e residuo. Se la conferma sul database fallisce: log critico (l'ordine resta comunque abbinato).
  - **Parziale**: se Betfair riporta un abbinamento parziale, la gamba vale per l'abbinato; `execution` scrive l'attivita' `place_parziale` critica "parziale x su y, residuo r" (con FOK senza soglia minima il residuo e' annullato da Betfair).
  - **Esito ignoto** (eccezione dopo l'invio, TIMEOUT, nessun report): gamba `pending_reconcile`, log critico, attivita' `reconcile_pending` critica; conta nel rischio e blocca le aperture; MAI annullata per tempo.
  - **Rifiuto dichiarato** (FOK non abbinato, codice d'errore, istruzione non accettata, freni): gamba `cancelled`; il motore e' informato (`_rifiutata`: "rifiutata da Betfair (codice o nota)"); riga in `error` col motivo; conteggio del freno copertura e attivita' `place_rifiutato` se c'e' un codice (scheda 25); attivita' `skip` col motivo; se il rifiuto viene da un freno e non dal mercato -> aperture ferme (scheda 45).
- **Numeri**: `MIKE_USE_FLUMINE_QUEUE` env default spento; `LIVE_KILL_SWITCH`, `LIVE_ORDER_MODE` env (valori fuori area).
- **Esempio**: copertura 2,26 EUR a 6,6 FOK: Betfair risponde EXECUTION_COMPLETE 2,26 a 6,6 -> `open`. Se risponde "non abbinato" -> riga `error` "live_not_matched:EXPIRED", rifiuto contato per il freno copertura.
- **Cosa vede l'utente**: attivita' `place`, `place_parziale`, `reconcile_pending`, `place_rifiutato`, `skip`.
- **Dove**: `service.py:780-781`, `:839-853`, `:884-943`; `execution.py:799-969`.
- **Paper o live**: solo live.

### 23. `execute_place` - cosa si fa dopo il piazzamento (comune)
- **Cosa fa**: riassume i quattro esiti possibili e cosa viene scritto.
- **Quando scatta**: dopo la risposta del runner (paper) o di Betfair (live).
- **Cosa succede dopo**:
  - `open`: gamba e riga aperte con i numeri veri.
  - `pending` normale (paper, esito non ancora arrivato; o coda del runner in live): attivita' `place_pending`, la gamba si segue al giro dopo.
  - `pending` con nota `place_exception_reconciling`: riconciliazione (gamba `pending_reconcile`).
  - qualsiasi altro: `cancelled` + riga `error` + conteggi e avvisi.
- **Numeri**: nessuno nuovo.
- **Esempio**: vedi schede 21-22.
- **Cosa vede l'utente**: le attivita' citate.
- **Dove**: `service.py:884-943`.
- **Paper o live**: la logica di esito e' la stessa; cambia chi risponde.

### 24. TABELLA: ogni ordine di Mike, che tipo e', cosa succede nei casi difficili
| Ordine | Chi lo piazza | Tipo vero sull'exchange | Abbinato in parte | Rifiutato | Esito ignoto | Rete/runner giu' |
|---|---|---|---|---|---|---|
| Punta d'ingresso `under_entry`, seconda puntata `under_second`, re-ingresso `reentry` | `execute_place` | **LAPSE + FILL_OR_KILL** (paper: comando al runner con `time_in_force=FILL_OR_KILL`, `persistence=LAPSE`; live: `place_order_live` con FOK e `persistenceType=LAPSE`) | vale solo l'abbinato; il resto e' annullato dal FOK | gamba annullata, riga `error`, motore informato (non ripete la stessa richiesta) | `pending_reconcile`, blocca le aperture | paper: non eseguito, aperture ferme; live: eccezione -> esito ignoto |
| Ultimo ingresso `under_last` (la gamba dice PERSIST) | `execute_place` | **LAPSE + FILL_OR_KILL** anche lui: la persistenza PERSIST della gamba NON arriva all'ordine (vedi "Differenze") | come sopra | come sopra | come sopra | come sopra |
| Copertura `over_cover` | `execute_place` | LAPSE + FOK; sotto il minimo place-and-trim con FOK | vale l'abbinato | come sopra + conteggio del freno copertura (3 uguali = ferma) | `pending_reconcile`, nessun conteggio | paper: aperture ferme (la copertura e' un'"apertura" per quel freno); frenata dal freno d'emergenza e dal modo ordini |
| Chiusure taker `under_close`, `over_close`, `manual_close`, green-up taker (`under_green`/`reentry_green` con `pre_exit_mode=taker`) | `execute_place` | LAPSE + FOK con "riduce l'esposizione"; mai frenate dai freni d'apertura | vale l'abbinato | annullata, motore informato; una sola in volo per ruolo/ciclo/lato | `pending_reconcile` | paper: non eseguito, il motore ripropone al giro dopo |
| Lay appoggiata `ko_green` (sempre), `under_green` e `reentry_green` (se `pre_exit_mode=resting`, default) | paper: `_piazza_resting_paper`; live: `_piazza_resting_live` | **LAPSE senza FOK**: resta sul libro; alla sospensione Betfair la fa scadere | la gamba resta `pending` con l'abbinato e il residuo vivo; si segue | paper: riga chiusa, motore informato; live: riga chiusa se rifiuto pulito, riconciliazione se il rifiuto ha tracce | live: `pending_reconcile` | paper: niente riga; live: eccezione -> riconciliazione |
| Annullo | `_mark_trade_cancelled` (fuori area) | annullo vero sul runner (paper) o su Betfair (live) | abbinato nel frattempo = posizione | non confermato -> riconciliazione | riconciliazione | vedi scheda 38 (annullo appena noto il bet_id) |

- **Dove**: `execution.py:514,531-534`; `porta_ordini.py:77-78`; `omega_market.py:735,746`; `service.py:1972-1976`.

---

## PARTE 4 - RIFIUTI, FRENI E APERTURE FERME

### 25. Il "no" definitivo del mercato: conteggio del freno della copertura
- **Cosa fa**: quando un ordine taker riceve un "no" definitivo, conta il rifiuto se e' la copertura Over 4.5 (per codice d'errore) e scrive le righe di attivita'. E' UNA funzione per le due strade (risposta immediata in live, esito del runner in paper).
- **Quando scatta**: dal ramo "rifiuto" di `execute_place` (scheda 22) e dal ramo "finale senza abbinamento" di `_segui_ordini_paper_su_runner` (scheda 40). Mai su un esito ignoto.
- **Cosa succede dopo**:
  - se ruolo `over_cover`: `engine.registra_rifiuto_copertura` -> stesso codice di prima = conteggio +1, codice diverso = riparte da 1; quando conteggio >= massimo -> copertura BLOCCATA;
  - se c'e' un codice di Betfair: attivita' `place_rifiutato` critica con codice, motivo, conteggio e massimo;
  - se il freno e' appena scattato: attivita' `error` critica "copertura_bloccata" ("serve un intervento (Riprendi) o un codice d'errore diverso") e log critico.
- **Numeri**: `cover_rifiuti_max` = **3** (UI, 1-20). Codice usato per contare: il codice di Betfair, se manca il motivo (es. `runner_annullato`, `live_not_matched:EXPIRED`), se manca anche quello "senza_codice"; tagliato a 60 caratteri.
- **Esempio**: tre coperture 1,26 EUR a 3,9 rifiutate `CANCELLED_NOT_PLACED`: al terzo rifiuto `bloccata=True`, attivita' critica; il quarto tentativo e' fermato dalla scheda 18.
- **Cosa vede l'utente**: `place_rifiutato` "x/3" e poi `error` "copertura_bloccata".
- **Dove**: `service.py:946-1004`; `engine.py:1595-1615`.
- **Paper o live**: stessa funzione; in paper il runner non da' codice d'errore, quindi si conta sul motivo `runner_<fase>` e NON si scrive `place_rifiutato` (solo `no_fill` con conteggio, scheda 40).

### 26. "Il mercato ha detto no a questa richiesta" (memoria per il motore)
- **Cosa fa**: scrive nella memoria della partita che il mercato ha rifiutato QUESTA richiesta, cosi' il motore non la ripropone identica al giro dopo.
- **Quando scatta**: solo quando nessun ordine e' nato e la risposta e' definitiva: prezzo non disponibile, rifiuto di Betfair o del runner, FOK non abbinato (runner: fase annullato/scaduto), lay appoggiata rifiutata, freno anti-doppione della chiusura. Mai su esito ignoto, mai in prova (`dry`). Se il contesto partita manca (solo nei test) non fa niente.
- **Cosa succede dopo**: chiama `engine.registra_rifiuto` (area motore).
- **Numeri**: nessuno.
- **Esempio**: registrazione 35674515: senza questa memoria `reentry_green` banca 10,11 a 1,75 veniva riproposta 531 volte.
- **Cosa vede l'utente**: niente direttamente.
- **Dove**: `service.py:1304-1327`.
- **Paper o live**: uguale.

---

## PARTE 5 - REGOLAMENTO, AGGREGATI, SCANNER, PARAMETRI DEL GIRO

### 27. Chi ha vinto (regolamento a mercato chiuso)
- **Cosa fa**: dal libro REST di un mercato chiuso capisce quale selezione e' stata dichiarata vincente; dai due mercati deduce la somma gol "rappresentativa"; riconosce un mercato annullato; prepara il piano di regolamento per mercato.
- **Quando scatta**: nel ramo di regolamento (`_run_event:4097,4109`, fuori area) a mercato chiuso.
- **Cosa succede dopo**:
  - `market_winner`: solo se lo stato del libro e' `CLOSED`; cerca il corridore `WINNER` e lo traduce in Under o Over confrontando l'id di selezione; altrimenti niente.
  - `final_total_from_books`: Under 3.5 vincente -> **3**; Over 4.5 vincente -> **5**; Over 3.5 e Under 4.5 vincenti -> **4**; altrimenti niente.
  - `market_voided`: annullato se lo stato e' `VOID`/`VOIDED`, oppure `CLOSED` senza nessun `WINNER` e con TUTTI i corridori `REMOVED`/`REMOVED_VACANT`/`VOID`/`VOIDED`. `INACTIVE` NON e' annullato.
  - `settle_plan`: per ogni mercato (3.5 e 4.5): annullato -> vincitore "nessuno" (le sue gambe valgono zero), altrimenti il vincitore; se un mercato non e' ne' regolato ne' annullato -> "si aspetta ancora" (niente P&L inventato).
- **Numeri**: nessuna soglia.
- **Esempio**: 3.5 CLOSED con Over WINNER, 4.5 CLOSED con Under WINNER -> totale 4 (perdono entrambe le puntate).
- **Cosa vede l'utente**: indirettamente la riga regolata.
- **Dove**: `service.py:1010-1090`.
- **Paper o live**: uguale (in paper il libro si legge comunque in REST).

### 28. Gli aggregati di giornata (stop giornaliero e numeri in testata)
- **Cosa fa**: legge dal database i numeri della giornata (P&L realizzato, posizioni aperte...), al massimo ogni `aggregates_cache_s`, per la sola modalita' in cui il bot opera; se la lettura fallisce riusa l'ultimo valore buono della stessa modalita' invece di "zero".
- **Quando scatta**: a ogni giro (`run_once:3538`), e forzata subito dopo un'azione (`:3676`).
- **Cosa succede dopo**: se si cambia modalita' si rilegge subito (mai lo stop del live sui numeri del paper). Lettura vuota o fallita -> avviso nel log e ultimo valore noto (o vuoto se non c'e' mai stato).
- **Numeri**: `aggregates_cache_s` = **20 s** (UI, 0-300). Lo stop giornaliero `daily_loss_stop` = 50 EUR e' deciso fuori area.
- **Esempio**: alle 18:00 il database non risponde: lo stop continua a vedere il -48 EUR letto alle 17:59:45, non 0.
- **Cosa vede l'utente**: numeri in testata stabili.
- **Dove**: `service.py:1096-1146`.
- **Paper o live**: memoria separata per modalita'.

### 29. Il ripiego REST quando il flusso dello scanner e' fermo
- **Cosa fa**: se lo scanner dichiara fermi i prezzi di una partita, Mike rilegge in REST il libro delle sue due linee (3.5 e 4.5) con la lettura gia' esistente. Quei prezzi servono SOLO a chiudere, coprire, proteggere (scheda 19).
- **Quando scatta**: dal giro partita (`_run_event:4242`) e dalle richieste dell'utente (`:3320`, senza tetto).
- **Cosa succede dopo**: per ogni linea del mercato fermo: se `con_tetto`, al massimo una lettura ogni 10 s per mercato; lettura fallita = avviso e niente; tiene solo i libri con stato `OPEN`. Se l'orologio del tetto supera 2000 mercati viene svuotato.
- **Numeri**: `_RIPIEGO_REST_MIN_S` = **10 s** (costante); limite memoria 2000. `APERTURE_MIKE` = `under_entry`, `under_last`, `under_second`, `reentry` (senza `over_cover`). Promemoria critici `_FLUSSO_CRITICO` e `_FLUSSO_RIPIEGO` (usati fuori area, `:4258-4264`).
- **Esempio**: scanner fermo sulla partita X al 60' con la copertura scoperta: ogni 10 s si legge il libro 4.5 in REST e la copertura puo' partire; una punta d'ingresso no.
- **Cosa vede l'utente**: attivita' di flusso interrotto (fuori area).
- **Dove**: `service.py:1149-1190`.
- **Paper o live**: uguale.

### 30. Esposizione attuale di Mike su una partita
- **Cosa fa**: somma il rischio delle gambe gia' abbinate e ancora aperte: punta = importo abbinato, banca = abbinato x (prezzo - 1).
- **Quando scatta**: per l'avviso del flusso interrotto (`_run_event:4268`).
- **Cosa succede dopo**: restituisce gli euro (al centesimo) o niente se illeggibile. Conta solo gambe con stato `open` o `pending` e abbinato > 0.
- **Numeri**: nessuno.
- **Esempio**: punta 10 a 1,50 abbinata + banca 5 abbinata a 1,40 -> 10 + 2 = 12,00 EUR.
- **Cosa vede l'utente**: il numero nell'avviso.
- **Dove**: `service.py:1193-1206`.
- **Paper o live**: uguale.

### 31. Lo stato dello scanner e la sua eta'
- **Cosa fa**: legge la riga di stato dello scanner (tabella `safe_strategy_status`, id `scanner`), tiene il suo contenuto per il giro (per sapere se il flusso e' fermo) e calcola quanti secondi sono passati dall'ultimo aggiornamento.
- **Quando scatta**: a ogni giro (`run_once:3496`), senza parametro di cadenza.
- **Cosa succede dopo**: se lo scanner e' "vecchio" (stato senza il blocco `flusso`) scrive UNA volta l'attivita' critica `flusso_non_dichiarato`. Lettura fallita (gestita in `db.scanner_status`) -> eta' sconosciuta.
- **Numeri**: eta' = ora - `updated_at` (mai negativa).
- **Esempio**: scanner aggiornato 12 s fa -> 12.
- **Cosa vede l'utente**: attivita' `flusso_non_dichiarato` (una volta).
- **Dove**: `service.py:1209-1232`; `db.py:518-525`.
- **Paper o live**: uguale.

### 32. La valvola dell'uscita appoggiata in live
- **Cosa fa**: in live, se l'uscita pre-partita e' impostata "appoggiata" ma la valvola `live_resting_enabled` e' spenta, forza l'uscita "a mercato" (taker). Non tocca `ko_green` (sempre appoggiata).
- **Quando scatta**: sui parametri del giro (`_params_for`) e su quelli della singola partita col suo modo (`_run_event:4014`, `:3306`).
- **Cosa succede dopo**: `pre_exit_mode` diventa `taker` per `under_green` e `reentry_green`.
- **Numeri**: `pre_exit_mode` = **"resting"** (UI, resting/taker); `live_resting_enabled` = **acceso** (UI).
- **Esempio**: live, valvola spenta: il green-up pre-match diventa una banca FOK al best invece di una banca appoggiata a -2 tick.
- **Cosa vede l'utente**: niente di specifico.
- **Dove**: `service.py:1235-1265`.
- **Paper o live**: solo live.

### 33. Bot fermo: niente ingressi nuovi
- **Cosa fa**: se il bot non e' "in marcia" (o la guardia d'avvio blocca), spegne per il giro gli ingressi pre-partita, i re-ingressi e l'ultimo ingresso PERSIST. Protezioni e uscite restano.
- **Quando scatta**: a ogni giro (`run_once:3453`).
- **Cosa succede dopo**: `pre_enabled`, `reentry_enabled`, `last_entry_persist` = spenti. NON spegne `second_entry_enabled` (seconda puntata dopo gol precoce) ne' la copertura (vedi "Cose strane").
- **Numeri**: nessuno.
- **Esempio**: utente preme "Ferma": una partita in gioco con Under aperto continua a coprirsi e a uscire.
- **Cosa vede l'utente**: nessun ingresso nuovo.
- **Dove**: `service.py:1268-1276`.
- **Paper o live**: uguale.

### 34. Avvisi a raffica limitata
- **Cosa fa**: impedisce di riscrivere lo STESSO avviso sulla stessa partita piu' di una volta ogni N secondi; gli avvisi critici hanno un intervallo piu' corto.
- **Quando scatta**: per gli avvisi ripetitivi (riconciliazione in attesa, linea mancante, tetto partite, posizione di conto non letta, lay in sospensione...).
- **Cosa succede dopo**: la chiave e' "tipo:motivo" (o "tipo:gamba"); la memoria delle ultime volte sta nel contesto della partita (`log_seen`) e viene ripulita delle voci piu' vecchie di 4 intervalli. Se e' troppo presto, niente scrittura.
- **Numeri**: `skip_log_interval_s` = **300 s** (UI, 10-3600; se vuoto 300); avvisi critici: il minore fra 300 e **45 s** (`_CRITICAL_LOG_EVERY_S`).
- **Esempio**: `reconcile_pending` critico: al massimo una riga ogni 45 s.
- **Cosa vede l'utente**: meno righe ripetute nell'attivita'.
- **Dove**: `service.py:1279-1301`.
- **Paper o live**: uguale.

---

## PARTE 6 - LA LAY APPOGGIATA (ordine che resta sul libro)

### 35. Quale uscita e' "appoggiata"
- **Cosa fa**: decide se una gamba e' una banca appoggiata sul libro (aspetta di essere abbinata) invece di un ordine a mercato.
- **Quando scatta**: per ogni gamba nuova e per quelle vive.
- **Cosa succede dopo**: e' appoggiata se: NON e' "finale", e' una banca, e (ruolo `ko_green` SEMPRE; oppure ruolo `under_green`/`reentry_green` con `pre_exit_mode="resting"`).
- **Numeri**: `pre_exit_mode` default "resting"; `ko_green_retry_s` = 5 (UI) non ha piu' effetto.
- **Esempio**: uscita al fischio banca 10,14 a 1,48 -> appoggiata anche con `pre_exit_mode=taker`.
- **Cosa vede l'utente**: niente di diretto.
- **Dove**: `service.py:1330-1346`.
- **Paper o live**: uguale.

### 36. Freno "ne ho gia' una in volo?" (anti-doppione)
- **Cosa fa**: prima di piazzare una banca appoggiata (e prima di una chiusura taker, scheda 17) cerca fra le righe della partita una riga `pending` con lo stesso ruolo, lo stesso ciclo e lo stesso lato. Se c'e', la nuova non nasce.
- **Quando scatta**: `_freno_gia_appoggiata`: live (`_piazza_resting_live:1925`) e paper (`_run_event:4504`).
- **Cosa succede dopo**: gamba `cancelled`, attivita' `place_saltato` critica "gamba_gia_appoggiata" col numero della riga in volo, log critico. Righe illeggibili = come se ci fosse (fail-closed; nel log `gia_in_volo` e' vuoto).
- **Numeri**: nessuno. Confronta ruolo, ciclo, lato (NON il mercato, nonostante il commento lo dica).
- **Esempio**: 15/09 Beijing Guoan: 32 green-up identici banca 5,07 a 1,43 in loop; con il freno ne resta uno.
- **Cosa vede l'utente**: attivita' `place_saltato`.
- **Dove**: `service.py:1349-1387`, `:1727-1748`.
- **Paper o live**: identico.

### 37. La porta paper verso il runner
- **Cosa fa**: fornisce il collegamento al runner per un ordine paper e riconosce quando il runner e' giu'.
- **Quando scatta**: a ogni ordine paper e alla verifica delle aperture ferme.
- **Cosa succede dopo**:
  - `_porta_paper(appoggiata)`: crea la vista della porta di Mike (scheda 62: al primo uso accende anche il collegamento); se la porta non si costruisce o non e' collegata -> niente.
  - `_attendi_terminale(porta, ref, attesa)`: aspetta l'evento FINALE del runner per quel riferimento (leggendo la memoria della porta, nessuna chiamata in piu').
  - `_nota_senza_runner(nota)`: vero se la nota comincia con `canale_giu`, `paper_no_fill`, `canale_premarcatura_fallita`, `canale_senza_trade_id`, `paper_senza_runner`.
  - `_senza_runner`: dichiara "ordine NON eseguito, runner non raggiungibile" (attivita' `skip` critica, al massimo ogni 60 s per partita) e un avviso nel log. Non e' un rifiuto del mercato: il motore ripropone.
- **Numeri**: `_SENZA_RUNNER_LOG_S` = **60 s**; `_SCADENZA_TAKER_PAPER_S` = **60 s** (scheda 38); `ATTESA_ESITO_TAKER_MAX_S` = 15 s.
- **Esempio**: runner spento: ogni ordine paper -> `skip paper_senza_runner` una volta al minuto per partita.
- **Cosa vede l'utente**: attivita' `skip` "paper_senza_runner".
- **Dove**: `service.py:1393-1446`.
- **Paper o live**: solo paper.

### 38. Seguire gli ordini paper sul runner - ordini senza notizie e ordini ancora vivi
- **Cosa fa**: per ogni gamba viva (o a esito ignoto) con riga paper mandata sul canale (`meta.canale_ref`) chiede alla memoria della porta l'ultimo evento dell'ordine e lo porta su gamba e riga. Gli eventi di modalita' live vengono ignorati (paper e live mai mischiati).
- **Quando scatta**: all'inizio di ogni giro partita in paper, prima di tutto il resto (`_run_event:4305`), e subito dopo l'attesa di un taker (scheda 21).
- **Cosa succede dopo**:
  - **Nessun evento**: se e' un taker (non appoggiato) e sono passati piu' di 60 s dall'invio (`canale_inviato_at`, o dall'ora della gamba) -> gamba `cancelled`, riga `error` motivo "runner_senza_esito", colonne abbinato 0/residuo 0, attivita' `no_fill` critica. La lay appoggiata senza eventi aspetta senza limite.
  - **Abbinamento cresciuto**: gamba con abbinato e prezzo medio veri (se manca il prezzo medio: la quota chiesta).
  - **Evento non finale** (ordine vivo): se e' un evento nuovo (numero di sequenza maggiore di quello salvato) aggiorna `meta` (fase, sequenza), toglie motivo/errore, salva il bet_id se mancava, scrive chiesto/abbinato/residuo/prezzo medio/ora; se la gamba era a esito ignoto torna `pending` (l'ordine esiste ed e' vivo). Se sulla riga c'e' un **annullo richiesto** e ora il bet_id e' noto -> annulla subito (`_mark_trade_cancelled`, fuori area).
- **Numeri**: `_SCADENZA_TAKER_PAPER_S` = **60 s**; tolleranza abbinato 0,000000001.
- **Esempio**: lay appoggiata paper 10,14 a 1,48; il runner dice "vivo, abbinato 4,00, residuo 6,14": gamba abbinato 4,00, riga aggiornata, resta `pending`.
- **Cosa vede l'utente**: righe Trade con abbinato/residuo aggiornati; `no_fill runner_senza_esito`.
- **Dove**: `service.py:1456-1542`.
- **Paper o live**: solo paper.

### 39. Seguire gli ordini paper - la fase "errore" del runner (esito ignoto)
- **Cosa fa**: se il runner riporta la fase `errore` (piazzamento con esito dubbio o place-and-trim abbandonato), l'ordine POTREBBE esistere: non si dichiara annullato.
- **Quando scatta**: evento finale con fase `errore`.
- **Cosa succede dopo**: prima si controlla se per lo STESSO bet_id e' arrivato un evento finale definitivo diverso da `errore` (paper): se si', vale quello (e si passa alla scheda 40). Altrimenti, se evento nuovo o gamba non gia' in riconciliazione: gamba `pending_reconcile`; riga marcata `phase=reserved`, motivo `place_exception_reconciling`, errore `runner_errore_esito_ignoto`, `runner_esito_ignoto=True` (conta nel rischio e blocca le aperture); log critico; attivita' `reconcile_pending` critica "runner_errore". Nessun conteggio del freno copertura.
- **Numeri**: nessuno.
- **Esempio**: copertura sotto il minimo, il place-and-trim del runner si interrompe: la gamba resta in verifica finche' arriva un esito certo.
- **Cosa vede l'utente**: attivita' `reconcile_pending`.
- **Dove**: `service.py:1543-1594`.
- **Paper o live**: solo paper.

### 40. Seguire gli ordini paper - l'esito finale
- **Cosa fa**: applica l'esito definitivo del runner.
- **Quando scatta**: evento finale (`rifiutato`, `abbinato`, `annullato`, `scaduto`) diverso da `errore`.
- **Cosa succede dopo**:
  - toglie dalla riga motivo, errore, annullo richiesto, marca "era ignoto"; salva bet_id.
  - **abbinato > 0**: gamba `open`; riga `open` con importo abbinato, prezzo medio, esposizione; `meta.fill="runner_paper:<fase>"`; attivita' `place` (taker) o `fill_resting` (appoggiata) con chiesto e residuo.
  - **abbinato = 0**: gamba `cancelled`; riga `error` motivo `runner_<fase>`. Per un taker non passato da esito ignoto: fase `rifiutato` -> motore informato "rifiutata dal runner"; fase `annullato`/`scaduto` -> motore informato "FOK non abbinato". Se evento nuovo: conteggio del freno copertura (scheda 25, codice = `runner_<fase>`). Per la lay appoggiata: e' una scadenza, nessun "no" al motore. Attivita' `no_fill` con fase, motivo e, se c'e', conteggio/massimo del freno.
- **Numeri**: nessuno nuovo.
- **Esempio**: copertura 1,26 a 3,9 FOK: runner "annullato" senza abbinamento -> `no_fill runner_annullato 1/3`.
- **Cosa vede l'utente**: attivita' `place`, `fill_resting`, `no_fill`.
- **Dove**: `service.py:1595-1662`.
- **Paper o live**: solo paper.

### 41. Piazzare la lay appoggiata in PAPER
- **Cosa fa**: manda la banca appoggiata al libro del runner, con lo stesso tipo del live (nessun FOK, LAPSE).
- **Quando scatta**: gamba appoggiata nuova, modalita' paper, dopo: feed fresco e non-apertura in ripiego REST, mercato operabile (scheda 43), non prova, freno d'emergenza se apertura (scheda 42), anti-doppione (scheda 36) (`_run_event:4461-4515`).
- **Cosa succede dopo**: porta del runner (appoggiata); giu' -> gamba `cancelled`, nessuna riga, avviso `paper_senza_runner` (NON ferma le aperture). Prenota la riga; fallita -> `error` "reserve_failed". Segna "chiude" se e' una copertura `*_green` o dichiara la riga chiusa. Manda con `execution.place` (importo esatto, nessun taglio sulla liquidita'). Esito "in attesa" -> attivita' `place_resting` ("via runner"). Esito runner giu' -> riga `error` `paper_senza_runner`. Altro esito -> attivita' `place_rifiutato` critica "resting_rifiutata", riga chiusa (`_mark_trade_cancelled`), motore informato.
- **Numeri**: nessuno nuovo.
- **Esempio**: `ko_green` banca 10,14 a 1,48 in paper: riga `pending`, `place_resting via runner`.
- **Cosa vede l'utente**: attivita' `place_resting` / `place_rifiutato`.
- **Dove**: `service.py:1665-1724`.
- **Paper o live**: solo paper.

### 42. La lay appoggiata "chiude"? e il freno d'emergenza sulle appoggiate paper
- **Cosa fa**: `_resting_e_chiusura` dice se la banca appoggiata riduce una posizione (ruolo che finisce con `_green` o riga chiusa dichiarata). `_freno_resting_paper` ferma in paper una banca appoggiata di APERTURA se il freno d'emergenza e' tirato.
- **Quando scatta**: prima di piazzare una banca appoggiata (paper `_run_event:4498`; live dentro `_piazza_resting_live`).
- **Cosa succede dopo**: freno tirato -> gamba `cancelled`, attivita' `place_saltato` "kill_switch" (non critica in paper), avviso. Oggi tutte le appoggiate sono `*_green` = chiusure, quindi il freno non scatta mai su di loro (vedi "Cose strane").
- **Numeri**: nessuno.
- **Esempio**: `under_green` -> chiusura -> passa anche a freno tirato.
- **Cosa vede l'utente**: niente, di fatto.
- **Dove**: `service.py:1751-1754`, `:1887-1900`.
- **Paper o live**: `_freno_resting_paper` solo paper; `_resting_e_chiusura` entrambi.

### 43. Guardia dello stato del mercato per la lay appoggiata
- **Cosa fa**: non appoggia la banca se il mercato non e' operabile (sospeso, chiuso, inattivo, incompleto, stato sconosciuto o assente). La gamba torna al motore che la ripropone alla riapertura.
- **Quando scatta**: per ogni banca appoggiata nuova, non in prova (`_run_event:4478`).
- **Cosa succede dopo**: se operabile: chiude l'eventuale attesa nel diario e si prosegue. Se no: gamba `cancelled` (nessuna riga, nessun "no" al motore); la PRIMA volta per quella sospensione (chiave partita+mercato+ruolo) scrive l'attivita' `attesa_riapertura` con motivo, stato e "aspetta" vero/falso.
- **Numeri**: nessuno. Lo stato viene dal libro del feed (status, in gioco, ritardo).
- **Esempio**: gol al 2', mercato SOSPESO: la `ko_green` non parte; una riga `attesa_riapertura`; alla riapertura il motore la ripropone.
- **Cosa vede l'utente**: attivita' `attesa_riapertura`.
- **Dove**: `service.py:1757-1798`; `stato_mercato.py:164-216`.
- **Paper o live**: uguale.

### 44. Il freno d'emergenza condiviso sulle aperture
- **Cosa fa**: legge il freno d'emergenza di tutto il sistema (env `LIVE_KILL_SWITCH` o interruttore nel database `betfair_live_settings.kill_switch`). Se non si riesce a valutarlo, frena ("kill_switch_illeggibile").
- **Quando scatta**: aperture taker paper (`blocco_paper`, scheda 21), appoggiate di apertura (schede 42 e 46), verifica delle aperture ferme in paper (scheda 45).
- **Cosa succede dopo**: restituisce il motivo (`live_kill_switch_attivo`, `db_kill_switch_attivo`, `kill_switch_illeggibile`) o niente.
- **Numeri**: cache del database ~2 s (dentro `controls`, fuori area).
- **Esempio**: utente accende il freno dalla Control Room: la punta d'ingresso paper successiva non parte; le chiusure si'.
- **Cosa vede l'utente**: attivita' `skip` col motivo e aperture ferme.
- **Dove**: `service.py:1801-1810`; `controls.py:107`.
- **Paper o live**: vale in entrambi (in live le aperture taker lo leggono dentro `_live_brake`).

### 45. Aperture ferme per una causa che non e' il mercato
- **Cosa fa**: quando un'APERTURA e' rifiutata per un freno (freno d'emergenza, modo ordini non LIVE, freni illeggibili) o per il runner giu' in paper, lo dice UNA volta e ferma le aperture della partita finche' la causa non cambia (il motore non le ripropone a ogni giro).
- **Quando scatta**:
  - `_rifiuto_non_di_mercato`: vero se la nota comincia con `live_order_mode_non_live`, `live_kill_switch_attivo`, `db_kill_switch_attivo`, `kill_switch_illeggibile`, `freni_live_non_letti` o e' una nota di runner giu'.
  - `_ferma_aperture`: dopo un rifiuto di quel tipo, solo per ruoli di apertura (`under_entry`, `under_last`, `under_second`, `over_cover`, `reentry`).
  - `_aggiorna_aperture_ferme`: prima di ogni decisione del motore (`_run_event:4428`).
- **Cosa succede dopo**:
  - fermo: memoria `aperture_ferme` = {motivo, modo, da quando}; se era gia' ferma con lo stesso motivo e modo, niente; altrimenti attivita' `skip` critica con `aperture_ferme=True` e log critico.
  - ripresa: se il modo della partita e' cambiato, oppure la causa riletta adesso non c'e' piu' (runner di nuovo raggiungibile / `execution._live_brake` in live / freno d'emergenza in paper) -> memoria cancellata, attivita' `state` "aperture_riprese". Se la causa non si riesce a valutare, restano ferme.
- **Numeri**: motivo tagliato a 120 caratteri.
- **Esempio**: live con `LIVE_ORDER_MODE=PAPER` nel `.env`: la prima punta d'ingresso e' rifiutata `live_order_mode_non_live:PAPER`; una riga `skip`; niente piu' riproposte finche' il modo non torna LIVE.
- **Cosa vede l'utente**: attivita' `skip` (aperture ferme) e `state` (aperture riprese).
- **Dove**: `service.py:1813-1884`.
- **Paper o live**: la causa si rilegge diversamente (paper: runner o freno d'emergenza; live: tutti i freni live).

### 46. Piazzare la lay appoggiata in LIVE
- **Cosa fa**: piazza davvero su Betfair la banca appoggiata e la lascia sul libro. Stessa selezione, lato, quota, importo del paper.
- **Quando scatta**: gamba appoggiata nuova, modalita' live, dopo le guardie di `_run_event` (feed, mercato operabile, non prova).
- **Cosa succede dopo**, nell'ordine:
  1. anti-doppione (scheda 36);
  2. se NON e' una chiusura: freno d'emergenza (oggi mai, scheda 42);
  3. prenota la riga PRIMA dell'ordine (fallita -> niente ordine, `error` "reserve_failed");
  4. piazza con riferimento `mike-t<id riga>`, lato banca, `fill_or_kill=False` (LAPSE);
  5. **eccezione** (rete, tempo scaduto, interruttore spento): esito IGNOTO -> gamba `pending_reconcile`, attivita' `reconcile_pending` "resting_place_unknown";
  6. **rifiuto dichiarato con tracce** (bet_id o abbinato presenti): riconciliazione, attivita' `reconcile_pending` "resting_rifiutata_con_tracce";
  7. **rifiuto pulito**: gamba `cancelled`, attivita' `place_rifiutato` critica con stato e codice, riga chiusa, motore informato;
  8. **accettato**: salva sempre il bet_id sulla riga (mancante -> `error` "resting_senza_bet_id"; salvataggio fallito -> `error` "bet_id_non_salvato");
  9. abbinamento immediato: abbinato e prezzo medio veri; tutto abbinato -> gamba `open`, altrimenti resta `pending`;
  10. aggiorna sempre la riga (scheda 47) con chiesto/abbinato/residuo (residuo di Betfair, o chiesto - abbinato) e attivita' `place_resting` ("parziale x su y, residuo r vivo" se parziale).
- **Numeri**: nessuno nuovo.
- **Esempio**: `ko_green` banca 10,14 a 1,48: Betfair accetta, abbinato 0 -> riga `pending` con bet_id, residuo 10,14.
- **Cosa vede l'utente**: attivita' `place_resting`, `place_rifiutato`, `reconcile_pending`, `error`.
- **Dove**: `service.py:1903-2089`.
- **Paper o live**: solo live.

### 47. Aggiornare la riga della lay appoggiata
- **Cosa fa**: porta sulla riga l'abbinamento della banca appoggiata: stato (`open` se abbinata tutta, altrimenti `pending`), prezzo medio (o chiesto), importo = abbinato, `meta.phase="open"`, come e' stato abbinato; e le colonne chiesto/abbinato/residuo/prezzo medio/ora di Betfair.
- **Quando scatta**: dopo il piazzamento live (scheda 46), a ogni progresso dell'abbinamento (scheda 50), alla riapertura con esito "abbinato" (scheda 53).
- **Cosa succede dopo**: riga non trovata -> niente. Aggiornamento fallito -> attivita' `error` "fill_update_failed".
- **Numeri**: residuo = quello passato, altrimenti chiesto - abbinato.
- **Esempio**: abbinato 4,00 su 10,14 -> riga `pending`, importo 4,00, residuo 6,14.
- **Cosa vede l'utente**: scheda Trade aggiornata.
- **Dove**: `service.py:2092-2121`.
- **Paper o live**: usata in live (in paper l'aggiornamento lo fa la scheda 38-40).

---

## PARTE 7 - LEGGERE GLI ORDINI DI BETFAIR

### 48. Leggere i campi di un ordine, comunque siano scritti
- **Cosa fa**: un'unica tabella dei nomi dei campi di un ordine Betfair, che accetta sia la grafia con trattino basso sia quella "attaccata" (es. `size_matched` e `sizeMatched`). Nasce dal loop dei 32 ordini veri del 15/09 (un nome sbagliato = "abbinato zero").
- **Quando scatta**: ogni volta che si legge un ordine Betfair.
- **Cosa succede dopo**: `campo_ordine` restituisce il valore (un valore presente ma vuoto resta vuoto: "non lo so" non e' "zero"); `_num_ordine` lo rende numero (difetto se manca o non e' un numero); `ordine_normalizzato` riscrive l'ordine con tutti i nomi in grafia con trattino basso.
- **Numeri**: campi: bet_id, riferimento cliente, abbinato, prezzo medio, residuo, regolato, annullato, scaduto, nullo, data abbinamento, data piazzamento, mercato, selezione, stato, lato.
- **Esempio**: ordine grezzo `{"sizeMatched": 5.07}` -> abbinato 5,07.
- **Cosa vede l'utente**: niente.
- **Dove**: `service.py:2146-2216`.
- **Paper o live**: live (e banco).

### 49. Riconoscere l'ordine di una riga
- **Cosa fa**: trova, fra gli ordini di Betfair, quello che appartiene a una riga di Mike. Tre strade: 1) il bet_id scritto sulla riga; 2) il riferimento `mike-t<id riga>`; 3) il vecchio riferimento della gamba (`under_green-0-2`), accettato SOLO se mercato e selezione coincidono (non e' unico fra partite).
- **Quando scatta**: seguire la lay appoggiata (scheda 50), rilettura alla riapertura (scheda 52), riconciliazione (fuori area).
- **Cosa succede dopo**: restituisce l'ordine o niente. `_ordine_di`: senza riga non cerca affatto (meglio aspettare un giro che contabilizzare l'ordine di un'altra partita).
- **Numeri**: nessuno.
- **Esempio**: riga #4817 con bet_id 3456 -> trova l'ordine 3456 anche se il riferimento cliente e' diverso.
- **Cosa vede l'utente**: niente.
- **Dove**: `service.py:2219-2315`.
- **Paper o live**: live.

### 50. Seguire la lay appoggiata in LIVE
- **Cosa fa**: a ogni giro chiede a Betfair gli ordini vivi di Mike e guarda quanto si e' abbinata la banca appoggiata.
- **Quando scatta**: per ogni gamba appoggiata viva, in live, a OGNI giro (`_run_event:4373`), senza cadenza propria: una chiamata REST per gamba per giro.
- **Cosa succede dopo**:
  - lettura fallita (rete): si riprova al giro dopo, niente inventato;
  - ordine non piu' fra i vivi e sospensione in corso gia' annotata: NON decide (lo fara' la rilettura alla riapertura), avviso limitato `resting_in_sospensione`;
  - ordine non piu' fra i vivi (senza sospensione): gamba `pending_reconcile`, avviso critico limitato `reconcile_pending` "resting_uscito_dagli_ordini_vivi";
  - abbinato non cresciuto: niente;
  - abbinato cresciuto: gamba con abbinato e prezzo medio; tutto abbinato -> `open`; riga aggiornata (residuo di Betfair); attivita' `fill_resting` ("parziale x su y, residuo r vivo" o "abbinata tutta").
- **Numeri**: tolleranza 0,000000001.
- **Esempio**: banca 10,14 a 1,48, al 2' Betfair dice abbinato 10,14 -> gamba `open`, `fill_resting abbinata tutta (10.14)`.
- **Cosa vede l'utente**: attivita' `fill_resting` / `reconcile_pending`.
- **Dove**: `service.py:2318-2401`.
- **Paper o live**: solo live.

---

## PARTE 8 - SOSPENSIONE, RIAPERTURA, CONTO, COPERTURA

### 51. La sospensione uccide le lay appoggiate: memoria e rilettura
- **Cosa fa**: se il mercato si sospende con una banca appoggiata viva, lo ricorda; alla riapertura rilegge l'ordine per sapere cosa e' successo (vivo, scaduto, abbinato, parziale, ignoto).
- **Quando scatta**: a ogni giro, PRIMA della decisione (`_run_event:4307`). Lo stato e' letto SOLO dal libro Under 3.5 (anche per `reentry_green`, che vive sull'Under 4.5).
- **Cosa succede dopo**:
  - **Sospeso o sconosciuto** con appoggiate vive (`_gambe_appoggiate_vive`): se non e' gia' annotata la stessa sospensione con gli stessi riferimenti, memoria `riapertura` = {ora, riferimenti, letto=falso, esiti} e attivita' `mercato_sospeso` critica.
  - **Chiuso**: niente.
  - **Aperto** con memoria non letta: per ogni riferimento: gamba sparita o non piu' viva -> "gamba_non_piu_viva". In PAPER: se la riga e' sul runner, si ANNULLA sul runner (applicando la regola di Betfair) e l'esito vale: abbinato -> "abbinato", annullato -> "scaduto", altrimenti "ignoto"; attivita' `rilettura_alla_riapertura` (fonte runner) e, se scaduto, `ordine_scaduto_alla_sospensione` critica. Riga non sul runner: esito "scaduto" applicato direttamente (scheda 53). In LIVE: rilettura (scheda 52); se non si e' potuto leggere si esce e si riprova al giro dopo (resta "non letto"); altrimenti si applica l'esito (scheda 53).
  - alla fine: memoria `letto=vero` con ora ed esiti.
- **Numeri**: nessuno.
- **Esempio**: gol al 2' con `ko_green` viva; alla riapertura Betfair non ha piu' l'ordine -> vedi scheda 52.
- **Cosa vede l'utente**: attivita' `mercato_sospeso`, `rilettura_alla_riapertura`, `ordine_scaduto_alla_sospensione`.
- **Dove**: `service.py:2430-2432`, `:2872-2962`.
- **Paper o live**: in paper la scadenza si applica SEMPRE (per regola), in live decide Betfair.

### 52. Rileggere da Betfair l'ordine appoggiato e classificarlo
- **Cosa fa**: rilegge l'ordine della gamba e lo classifica con i numeri di Betfair.
- **Quando scatta**: alla riapertura, in live (scheda 51).
- **Cosa succede dopo**:
  - riga non trovata -> "ignoto" (riga_assente);
  - lettura degli ordini vivi fallita -> "non so ancora" (si riprova);
  - ordine trovato fra i vivi -> classifica;
  - non trovato: senza bet_id o se lo sportello non sa leggere per bet_id -> "ignoto" (`senza_bet_id` / `mercato_senza_lettura`). ATTENZIONE: lo sportello di produzione `_RealMarket` NON ha `order_state_by_bet_id`, quindi in live reale questo ramo da' sempre "ignoto" (vedi "Cose strane");
  - lettura per bet_id: errore -> "non so ancora"; Betfair non lo conosce -> "ignoto"; altrimenti classifica.
  - **Classifica** (`_classifica_ordine`): residuo > 0,009 e stato diverso da EXECUTION_COMPLETE -> **vivo**; abbinato >= chiesto - 0,009 -> **abbinato**; abbinato > 0,009 -> **parziale**; altrimenti **scaduto**. Numeri riportati: chiesto, abbinato, residuo (quello di Betfair se c'e'), scaduto, annullato, stato, prezzo medio, ora.
- **Numeri**: soglie 0,009 EUR (costanti).
- **Esempio**: chiesto 10,14, abbinato 6,00, residuo 0, scaduto 4,14 -> "parziale".
- **Cosa vede l'utente**: indirettamente (scheda 53).
- **Dove**: `service.py:2423-2507`.
- **Paper o live**: live.

### 53. Le quattro reazioni alla riapertura
- **Cosa fa**: applica l'esito della rilettura.
- **Quando scatta**: dopo la classificazione (scheda 52) o, in paper, con esito "scaduto" per regola.
- **Cosa succede dopo**:
  - **vivo**: niente cambia (attivita' `rilettura_alla_riapertura` "ancora vivo: nessuna gamba nuova");
  - **abbinato**: gamba `open` con abbinato e prezzo medio, riga aggiornata (residuo 0), attivita' "abbinato durante la sospensione";
  - **ignoto**: gamba `pending_reconcile`, log critico, attivita' `rilettura_alla_riapertura` critica e `reconcile_pending` "riapertura_esito_ignoto";
  - **scaduto / parziale**: attivita' `rilettura_alla_riapertura` + `ordine_scaduto_alla_sospensione` critica; poi `_chiudi_gamba_scaduta`: abbinato > 0 -> gamba `open`, riga `open` con abbinato e prezzo; abbinato 0 -> gamba `cancelled`, riga `error`; `meta.phase="lapsed"`, motivo `lapsed_alla_sospensione`, residuo 0. Aggiornamento fallito -> `error` "lapsed_update_failed". Poi decide il motore (ri-appoggia se la finestra e' aperta, altrimenti copre).
- **Numeri**: nessuno.
- **Esempio**: `ko_green` 10,14 a 1,48 scaduta senza abbinamento -> riga `error` "lapsed_alla_sospensione"; il motore al giro dopo ne appoggia una nuova se la finestra di 180 s non e' finita.
- **Cosa vede l'utente**: attivita' citate.
- **Dove**: `service.py:2510-2604`.
- **Paper o live**: uguale una volta deciso l'esito.

### 54. "Se chiudo io, il bot deve saperlo": la posizione di conto
- **Cosa fa**: in live confronta quanto Mike CREDE di avere su ogni selezione con la posizione reale del CONTO (ordini di chiunque). Se l'utente ha chiuso tutto fuori dall'app, Mike smette di gestire la partita.
- **Quando scatta**: a ogni giro prima della decisione (`_run_event:4321`), ma lavora solo se: modalita' live, partita non gia' "chiusa dall'utente", passati almeno `reconcile_every_s` dall'ultima lettura per la partita, e ci sono selezioni aperte.
- **Cosa succede dopo**:
  - lo sportello non espone le letture di conto -> avviso limitato `posizione_di_conto_non_letta`;
  - per ogni selezione aperta con posizione attesa oltre 0,05 EUR: legge vivi+regolati del mercato (una volta per mercato); lettura fallita -> si azzera l'orologio (si riprova al giro dopo) e si esce;
  - `_posizione_attesa`: punta meno banca dell'abbinato delle gambe non archiviate;
  - `_refs_di_mike`: i riferimenti di Mike (riferimento gamba e `mike-t<id>`);
  - `_netto_su_selezione`: punta meno banca dell'abbinato sul conto, una volta solo per i riferimenti di Mike, una volta per tutti;
  - le gambe di Mike NON si ritrovano sul conto (mio + 0,05 < atteso) -> attivita' `posizione_di_conto` critica "gambe_non_ritrovate" (riconciliazione, niente si spegne);
  - parte viva = quanto della posizione di Mike sopravvive nel netto di conto: <= 0,05 -> "chiusa_dall_utente"; ridotta -> "ridotta_dall_utente" (si dichiara, si continua a proteggere);
  - se almeno una selezione e' chiusa dall'utente: attivita' `chiuso_dall_utente` critica, annulla davvero tutti gli ordini vivi di Mike sulla partita, e accende: chiuso dall'utente, niente rientri, rientro gia' fatto, chiusura manuale spenta.
- **Numeri**: `reconcile_every_s` = **30 s** (UI); `_CONTO_EPS` = **0,05 EUR** (costante).
- **Esempio**: Mike ha punta Under 10 EUR; sul conto c'e' anche una banca 10 EUR dell'utente -> netto 0 -> `chiuso_dall_utente`; da qui nessuna azione di Mike sulla partita; il P&L lo fa il regolamento.
- **Cosa vede l'utente**: attivita' `posizione_di_conto`, `chiuso_dall_utente`.
- **Dove**: `service.py:2626`, `:2693-2869`.
- **Paper o live**: solo live (in paper esce subito).

### 55. Lo stato del mercato della copertura Over 4.5
- **Cosa fa**: mentre la copertura e' da fare o sul libro, osserva lo stato del mercato Over 4.5 e scrive UNA riga per ogni cambio (sospeso/chiuso/sconosciuto, riaperto). Non emette ne' annulla ordini.
- **Quando scatta**: a ogni giro prima della decisione (`_run_event:4314`), solo se `engine.copertura_in_corso`.
- **Cosa succede dopo**: stato uguale al precedente -> niente; prima lettura con mercato aperto -> si memorizza e basta; non aperto -> attivita' `mercato_sospeso` critica (fase copertura, riferimenti delle coperture vive o in verifica); tornato aperto -> attivita' `skip` "mercato_riaperto". Memoria `cover_mercato` = {stato, ora}.
- **Numeri**: nessuno.
- **Esempio**: 30' gol, mercato 4.5 sospeso durante la copertura: una riga "mercato della copertura Over 4.5 non operabile"; alla riapertura "la copertura riprende".
- **Cosa vede l'utente**: attivita' `mercato_sospeso` e `skip mercato_riaperto`.
- **Dove**: `service.py:2965-3009`.
- **Paper o live**: uguale.

---

## PARTE 9 - LE RICHIESTE DELL'UTENTE

### 56. Le richieste dalla UI (cash out, flatten, annulla, approva, salta, riprendi)
- **Cosa fa**: legge le richieste in attesa e le esegue una per una, con un esito dichiarato in italiano.
- **Quando scatta**: a ogni giro (`run_once:3567`), prima delle partite.
- **Cosa succede dopo**: per ogni richiesta la marca "in lavorazione", poi:
  - partita non seguita -> rifiuto `evento_non_seguito`;
  - partita SETTLED o ERROR e richiesta diversa da "riprendi" -> rifiuto `stato_terminale`;
  - cash out / flatten: prima il controllo "e' davvero per questa partita?" (scheda 57, rifiuto `richiesta_ambigua` + attivita' `error`), poi `_request_flatten` (fuori area) con i parametri effettivi del giro;
  - annulla -> `_request_cancel` (fuori area);
  - approva uscita -> scheda 58;
  - **salta**: se c'e' posizione aperta o una gamba viva/in verifica -> rifiuto `posizione_aperta` ("prima chiudi con Cash out"); altrimenti stato SKIPPED, riga salvata, attivita' `skip_event`;
  - **riprendi**: da SKIPPED -> WATCH, divieto di rientro e chiusura manuale spenti, attivita' `resume_event`; altrimenti se c'e' divieto di rientro, chiusura manuale o copertura bloccata -> tutti tolti (anche il freno della copertura: `engine.sblocca_copertura`), attivita' `resume_event` con il verbale del freno sbloccato, esito "Rientro riabilitato" (lo stato resta quello che era); altrimenti rifiuto `stato_non_riprendibile`;
  - tipo sconosciuto -> errore `kind_non_valido`; eccezione -> errore `errore_interno`.
  - Esito finale: `done` se ok; `rejected` se il codice e' fra quelli attesi; altrimenti `error`.
- **Numeri**: codici "rifiuto atteso": `evento_non_seguito`, `stato_terminale`, `posizione_aperta`, `stato_non_riprendibile`, `feed_assente`, `snapshot_assente`, `niente_da_chiudere`, `feed_stantio`, `richiesta_ambigua`, `flusso_interrotto`, `proposta_non_viva`, `proposta_cambiata`.
- **Esempio**: "Riprendi" su una partita con copertura bloccata dopo 3 rifiuti -> freno azzerato, al giro dopo la copertura si ritenta.
- **Cosa vede l'utente**: il messaggio dell'esito e le attivita' `skip_event` / `resume_event`.
- **Dove**: `service.py:3012-3029` (`_result`, `_REJECT_CODES`), `:3077-3178`.
- **Paper o live**: uguale.

### 57. La richiesta di chiusura e' davvero per questa partita?
- **Cosa fa**: per cash out / flatten dalla Control Room verifica che la richiesta sia per Mike, nella modalita' della partita, e che la riga indicata sia una riga di Mike di questa partita.
- **Quando scatta**: prima di ogni cash out / flatten (scheda 56).
- **Cosa succede dopo**: rifiuta (con motivo in italiano) se: il bot indicato non e' "mike"; la modalita' indicata e' diversa da quella della partita; la riga indicata non si puo' verificare o leggere, non esiste, non e' di questa partita, o e' di modalita' diversa. Chiavi assenti = nessun controllo su quelle.
- **Numeri**: nessuno.
- **Esempio**: clic "Chiudi" su una riga paper di una partita armata in live -> "paper e live non si mischiano".
- **Cosa vede l'utente**: messaggio "Rifiutato: ...".
- **Dove**: `service.py:3032-3074`.
- **Paper o live**: uguale.

### 58. Approvare un'uscita proposta (uscite manuali)
- **Cosa fa**: quando le uscite automatiche sono spente, il bot propone l'uscita e l'utente la approva. Qui NON si piazza niente: si scrive la firma dell'utente nella memoria della partita; al giro dopo il motore esegue l'uscita con i prezzi e gli importi di quel momento, se la proposta e' ancora la stessa.
- **Quando scatta**: richiesta `approva_uscita` (scheda 56).
- **Cosa succede dopo**:
  - `_request_approva_uscita`: nessuna proposta viva -> rifiuto `proposta_non_viva`; chiave mancante o diversa -> rifiuto `proposta_cambiata` (con la chiave nuova); altrimenti memoria `uscita_approvata` = {chiave, ora, numero della richiesta, contesto del clic}, riga salvata, attivita' `uscita_approvata`, messaggio "Uscita approvata: parte al prossimo giro del bot".
  - `_id_approvazione`: numero intero > 0 o niente.
  - `_approvazione_eseguita`: dopo la decisione del motore, se la sua telemetria dice "uscita eseguita su approvazione" con la STESSA chiave, restituisce il numero della richiesta.
  - `_chiave_gamba`: quel numero va scritto SOLO sulle gambe d'uscita discrezionale (`under_green`, `ko_green`, `under_close`, `over_close`, `reentry_green`), mai su una copertura nata nello stesso giro.
- **Numeri**: `uscite_automatiche` = **spento** di default (UI, `config.py:254`).
- **Esempio**: proposta "cash out +0,75 EUR" chiave K1; l'utente approva K1; al giro dopo la chiusura parte e la riga porta `approvazione_id` = numero della richiesta.
- **Cosa vede l'utente**: messaggio di esito e attivita' `uscita_approvata`.
- **Dove**: `service.py:3181-3250`; uso in `_run_event:4425-4430`, `:4497`, `:4515`, `:4527`.
- **Paper o live**: uguale.

---

## PARTE 10 - LA PORTA ORDINI DI MIKE VERSO IL RUNNER (`porta_ordini.py`)

### 59. I riferimenti degli ordini paper di Mike
- **Cosa fa**: `ref_ordine(numero riga)` -> `mike-t<numero>`; `ref_annullo(bet_id, riduzione)` -> `mike-c<bet_id>` piu' eventualmente `-<riduzione in centesimi>`.
- **Quando scatta**: `ref_annullo` quando un comando di annullo non ha gia' un riferimento di Mike (scheda 60); `ref_ordine` non e' usata dal servizio (costruisce `mike-t<id>` da se').
- **Cosa succede dopo**: riferimento tagliato alla lunghezza massima.
- **Numeri**: lunghezza massima **32** caratteri (`REF_MAX`); prefisso `mike-`.
- **Esempio**: riga 4817 -> `mike-t4817`; annullo del bet 3456 riducendo 1,25 -> `mike-c3456-125`.
- **Cosa vede l'utente**: niente.
- **Dove**: `porta_ordini.py:36-60`.
- **Paper o live**: paper.

### 60. Il comando di Safe reso comando di Mike (`adatta_comando`)
- **Cosa fa**: prende il comando costruito dal modulo comune di esecuzione e lo trasforma nel comando di Mike, fissando il tipo d'ordine uguale al live. Se qualcosa non torna, solleva un errore e NON manda niente.
- **Quando scatta**: a ogni invio dalla vista di Mike (scheda 61).
- **Cosa succede dopo**:
  - lay appoggiata: nessun FOK, persistenza LAPSE;
  - taker: tiene la scelta di `execution` (FOK, o nessun FOK sotto il minimo), persistenza quella del comando o LAPSE;
  - controlla: azione ammessa (place, cancel, replace, greenup, cashout_event, cashout_all), modo paper/live, riferimento che inizia con `mike-` e <= 32 caratteri (per l'annullo lo ricostruisce `mike-c...`), tipo di durata solo FOK o niente, persistenza solo LAPSE/PERSIST, ora di creazione numerica;
  - imposta attore e strategia `mike`, origine tabella `mike_trades`; per `place`: durata, "riduce l'esposizione", persistenza; per gli altri: niente durata, "riduce" falso;
  - restituisce solo le chiavi del protocollo.
- **Numeri**: `FOK` = "FILL_OR_KILL"; persistenze ammesse LAPSE, PERSIST.
- **Esempio**: comando di una `ko_green` con `time_in_force=FILL_OR_KILL` arrivato da `execution` -> la vista appoggiata lo rende senza FOK e LAPSE.
- **Cosa vede l'utente**: niente; su errore log "comando NON inviato".
- **Dove**: `porta_ordini.py:63-112`.
- **Paper o live**: paper (il live non passa dal canale).

### 61. La vista di Mike sulla porta (`VistaMike`)
- **Cosa fa**: e' la porta come la vede UNA azione: sa se l'ordine e' appoggiato; manda i comandi adattati; legge gli esiti.
- **Quando scatta**: creata per ogni ordine paper (`vista()`).
- **Cosa succede dopo**:
  - `__init__`: ricorda la porta di base e se e' appoggiata; `submin_fill_or_kill` = vero per i taker (sotto il minimo si fa comunque "tutto o niente", come il live), falso per l'appoggiata;
  - `attore` = "mike"; `memoria` = memoria degli eventi della porta;
  - `disponibile()`: collegata? (errore = no);
  - `invia(comando)`: adatta (scheda 60); se non valido risponde "non inviato" col motivo `mike_comando_non_valido` e log di errore; altrimenti manda;
  - `esiti(ref)`, `attendi_esito_bet(bet_id, attesa)`: girano alla porta di base.
- **Numeri**: nessuno.
- **Esempio**: taker 1,26 EUR (sotto il minimo) -> `submin_fill_or_kill` vero -> comando con FOK.
- **Cosa vede l'utente**: niente.
- **Dove**: `porta_ordini.py:115-158`.
- **Paper o live**: paper.

### 62. Accendere, riusare e spegnere la porta di Mike
- **Cosa fa**: una sola porta a comandi per processo, verso il canale del runner.
- **Quando scatta**: al primo ordine paper (o controllo aperture ferme).
- **Cosa succede dopo**:
  - `PortaCanaleMike`: la porta di Safe identica, col nome del collegamento `mike-porta-mike`; `avvia` lo accende una volta sola;
  - `_crea_porta`: porta calcio, attore "mike", indirizzo `LIVE_LOCAL_WS_PORT` o 47331;
  - `porta_mike(avvia=True)`: crea la porta se non c'e' e la accende (nessun interruttore: in paper Mike passa SEMPRE dal runner);
  - `porta_esistente()`: la porta se c'e', senza crearla;
  - `installa(porta)`: la sostituisce (banco e test con un runner finto);
  - `azzera()`: la toglie e la ferma;
  - `vista(appoggiata)`: la vista per un ordine (scheda 61).
- **Numeri**: porta **47331** (env `LIVE_LOCAL_WS_PORT`).
- **Esempio**: al primo ordine paper dopo l'avvio del processo la porta si accende; finche' non e' collegata il primo ordine risulta "runner non raggiungibile".
- **Cosa vede l'utente**: niente.
- **Dove**: `porta_ordini.py:161-224`.
- **Paper o live**: paper.

---

## Glossario

| Nome interno | In parole semplici |
|---|---|
| `mike_trades` | tabella delle righe-ordine di Mike (una riga per ordine) |
| `mike_events` | tabella delle partite seguite, con lo stato e la memoria di ciascuna |
| `mike_activity` | registro delle attivita' visibile in pagina |
| `ctx` (MatchCtx) | la memoria di lavoro di una partita |
| gamba (`Leg`) | un ordine del bot, con il suo ruolo |
| `pending` | ordine in attesa (in coda o appena mandato) |
| `open` | abbinato (posizione presa) |
| `cancelled` | ritirato / non nato |
| `pending_reconcile` | esito ignoto: l'ordine potrebbe esistere, si verifica con Betfair |
| `error` (riga) | riga chiusa senza abbinamento (rifiutata, scaduta, annullata) |
| `archived` | gamba di un ciclo pre-partita gia' chiuso (conta nella contabilita', non nel rischio) |
| `under_entry` | punta d'ingresso sull'Under 3.5 pre-partita |
| `under_green` | banca di green-up pre-partita (profitto bloccato) |
| `under_last` | ultimo ingresso a 10' dal fischio (la gamba dice PERSIST) |
| `under_second` | seconda puntata sull'Under 3.5 dopo un gol precoce |
| `ko_green` | banca d'uscita al fischio, appoggiata |
| `over_cover` | copertura: punta sull'Over 4.5 |
| `under_close`, `over_close` | chiusure a mercato delle due gambe |
| `reentry` | re-ingresso: punta Under 4.5 dopo un gol |
| `reentry_green` | banca di green-up del re-ingresso |
| `manual_close` | chiusura chiesta dall'utente |
| aperture (`OPENING_ROLES`) | `under_entry`, `under_last`, `under_second`, `over_cover`, `reentry` |
| chiusure (`CLOSING_ROLES`) | `under_green`, `ko_green`, `under_close`, `over_close`, `reentry_green`, `manual_close` |
| `APERTURE_MIKE` | aperture senza la copertura (quelle vietate col ripiego REST) |
| uscite discrezionali | `under_green`, `ko_green`, `under_close`, `over_close`, `reentry_green` |
| lay appoggiata / resting | banca lasciata sul libro ad aspettare |
| taker | ordine che prende subito il prezzo migliore |
| FOK / FILL_OR_KILL | tutto subito o niente (il non abbinato e' cancellato) |
| LAPSE | il non abbinato decade alla sospensione / passaggio in gioco |
| PERSIST | il non abbinato resta anche in gioco |
| place-and-trim | tecnica per importi sotto il minimo: parcheggio a quota impossibile, taglio, riprezzo |
| runner | il simulatore (flumine) che in paper esegue gli ordini come Betfair |
| canale di comando | collegamento locale dal bot al runner (porta 47331) |
| `canale_ref` | riferimento dell'ordine sul canale del runner, scritto sulla riga |
| evento `order` / fase | notizia del runner su un ordine: `rifiutato`, `abbinato`, `annullato`, `scaduto`, `errore` (finali) o intermedie |
| bet_id | numero dell'ordine dato da Betfair (o dal runner) |
| `mike-t<id>` | riferimento cliente dell'ordine, dal numero di riga |
| `signal_key` | riferimento della gamba scritto sulla riga (`ruolo-ciclo-seq`) |
| riserva / reserve-first | prima si scrive la riga, poi si manda l'ordine |
| `closes_trade_id` | la riga che questa gamba chiude |
| freno d'emergenza / kill-switch | interruttore che ferma le aperture (env `LIVE_KILL_SWITCH` o database) |
| modo ordini / `LIVE_ORDER_MODE` | tetto OFF/PAPER/LIVE per i soldi veri |
| `MIKE_LIVE_ENABLED` | interruttore di Mike per i soldi veri |
| freno copertura / `LIVE_COVER_BLOCKED` | copertura fermata dopo N rifiuti uguali |
| aperture ferme | aperture sospese per una causa che non e' il mercato |
| ripiego REST | prezzi letti in REST quando lo scanner ha il flusso fermo |
| feed stantio | prezzi non piu' vivi |
| `riapertura` | memoria della sospensione con lay appoggiata viva |
| `attesa_riapertura` | attivita': ordine appoggiato non mandato perche' il mercato non e' operabile |
| `chiuso_dall_utente` | la posizione e' stata chiusa dall'utente fuori dall'app |
| `uscita_proposta` / `uscita_approvata` | proposta d'uscita del bot / firma dell'utente |
| `dry` | modalita' prova: nessun ordine, solo "avrei piazzato" |
| stati di mercato | `aperto`, `sospeso`, `chiuso` (anche INACTIVE), `ignoto` |
| attivita' citate | `skip`, `no_fill`, `place`, `place_pending`, `place_parziale`, `place_rifiutato`, `place_saltato`, `place_resting`, `fill_resting`, `reconcile_pending`, `would_place`, `size_legalized`, `schema_warn`, `error`, `state`, `attesa_riapertura`, `mercato_sospeso`, `rilettura_alla_riapertura`, `ordine_scaduto_alla_sospensione`, `posizione_di_conto`, `posizione_di_conto_non_letta`, `chiuso_dall_utente`, `resting_in_sospensione`, `flusso_non_dichiarato`, `skip_event`, `resume_event`, `uscita_approvata`, `cancel_richiesto`, `cancel_esito` |

---

## Differenze dalla Costituzione

(Elenco, senza giudizio. "Cost." = `Betfair/mike/COSTITUZIONE_MIKE.md`.)

1. **Ultimo ingresso PERSIST** - Cost. §3 Fase 2 (righe 134-140), §5 riga "PERSIST al KO", §15.1: il nuovo back Under 3.5 a 10' dal fischio ha persistenza PERSIST "resta valido in-play". Codice: la gamba `under_last` porta `persistence="PERSIST"` solo sulla riga (`service.py:572`); l'ordine vero parte **LAPSE + FILL_OR_KILL** sia in paper (`execution.py:514` `persistence="LAPSE"`, `:531` FOK) sia in live (`omega_market.py:735` `persistenceType: LAPSE` fisso, `:746` FOK di default). Nessun residuo PERSIST puo' esistere. (La stessa Cost. §7 riga 470 dice "Rinviato alla fase F6: persistence PERSIST su place_order_live".)
2. **Punta d'ingresso "LAPSE, TTL 60 s"** - Cost. §3 Fase 1 riga 123: "BACK ... LAPSE, TTL 60 s (non abbinato -> annullato, si riprova)". Codice: il taker e' FILL_OR_KILL (`execution.py:531`, `omega_market.py:746`): non resta mai sul libro, il TTL non ha oggetto.
3. **Paper = fill sul feed** - Cost. §2 riga 71 e §7 righe 453-459: "paper = fill sul feed", "fill DIFFERITO di bet_delay", "lay appoggiata abbinata quando il best back supera il prezzo". Codice: dal 29/09 il paper passa dal runner (`service.py:754-766`, `:1665-1724`, `porta_ordini.py:1-22`), niente fill in casa, niente differita (`_run_event:4518-4521`).
4. **Lay appoggiata in live "non esiste"** - Cost. §7 righe 464-466: `_params_for` forza `pre_exit_mode='taker'` e logga `resting_live_unsupported`. Codice: la lay appoggiata live esiste (`_piazza_resting_live`, `service.py:1903`); `_live_exit_override` forza taker solo se `live_resting_enabled` e' spento (`:1262-1264`); nessun `resting_live_unsupported`.
5. **Feed stantio: chiusure permesse** - Cost. §5 riga 284: "nessun ingresso/re-ingresso; chiusure permesse". Codice: con feed non fresco NESSUN ordine, chiusure comprese, paper e live (`service.py:709-717`; lay appoggiate `_run_event:4464-4477`).
6. **Ordine senza esito in paper "si risolve subito"** - Cost. §5 riga 285: "In paper si risolve subito (nessun ordine e' mai partito)". Codice: in paper l'ordine esiste sul runner; la fase `errore` e il "nessun ack" portano a riconciliazione (`service.py:1562-1594`; `execution.py:572-584`); un taker senza eventi per 60 s viene invece dichiarato NON eseguito (`service.py:1494-1508`).
7. **"Riprendi" su ERROR** - Cost. §5 righe 293-294: "Riprendi si', ed e' raggiungibile anche su ERROR e SKIPPED". Codice: su ERROR riprendi non cambia lo stato; funziona solo se c'e' divieto di rientro / chiusura manuale / copertura bloccata, altrimenti rifiuto `stato_non_riprendibile` (`service.py:3134-3170`).
8. **Paper sotto il minimo** - Cost. §15.5 tabella riga 1248: "paper: esecuzione simulata, non esiste nessun minimo, l'importo esatto si abbina". Codice: la porta taker di Mike dichiara `submin_fill_or_kill` (`porta_ordini.py:129`) e il runner fa place-and-trim con FOK; rifiuto certo se il libro dice che non si abbina (`execution.py:775-782`).
9. **Rilettura alla riapertura con `order_state_by_bet_id`** - Cost. §15.6 righe 1317-1319. Codice: `_rileggi_ordine_appoggiato` la cerca con `getattr(market, "order_state_by_bet_id")` (`service.py:2492`), ma lo sportello di produzione `_RealMarket` (`service.py:120-228`) NON la espone: in live reale, se l'ordine non e' piu' fra i correnti, l'esito e' sempre IGNOTO "mercato_senza_lettura" -> riconciliazione; la reazione (b) "scaduto" in live non si raggiunge per un ordine scaduto senza abbinamento.
10. **`feed_cache_s` = 2 s** - Cost. §17.3 riga 1775 e righe 1783-1784. Codice: default **4,0 s** (`config.py:327`); il commento a `service.py:320` dice ancora 2 s.
11. **Uscite automatiche** - Cost. §15.7-ter righe 1444-1449: proposte da approvare ANNULLATE, "Le uscite di Mike restano automatiche". Codice: esiste l'approvazione (`_request_approva_uscita`, `service.py:3216`) e `uscite_automatiche` e' SPENTO di default (`config.py:254`).
12. **Mike non coperto da `LIVE_ORDER_MODE`** - Cost. §16.1 righe 1582-1586: "Mike piazza in REST diretto, quindi non e' coperto da LIVE_ORDER_MODE". Codice: le aperture taker live passano da `execution._live_brake` (freno d'emergenza + modo ordini, `execution.py:872-874`); la lay appoggiata live usa solo il freno d'emergenza e solo sulle aperture (`service.py:1933-1942`), le chiusure solo `MIKE_LIVE_ENABLED`.
13. **Bot fermo: nessun ingresso** - Cost. §5 riga 288. Codice: `_params_for` spegne ingresso pre-partita, re-ingresso e ultimo ingresso, ma NON la seconda puntata `under_second` (`service.py:1268-1276`; `engine.py:3044` la guarda solo con `second_entry_enabled`). Da verificare nell'area motore se altrove e' bloccata.
14. **Sospensione con lay appoggiata: "il mercato"** - Cost. §15.6 riga 1314: "A ogni sospensione con la lay appoggiata viva". Codice: lo stato si legge solo dal libro Under 3.5 (`service.py:2881`), anche per `reentry_green` che sta sull'Under 4.5 (`engine.py:3732`).
15. **Ordine senza esito: si riconcilia ... "in paper nessun ordine"** e §4.11: "Un ordine con esito IGNOTO non e' mai dato per non piazzato". Codice paper: taker con esito ignoto per mancanza di ack (`canale_esito_ignoto`) e nessun evento per 60 s -> dichiarato `runner_senza_esito`, riga `error` (`service.py:1494-1508`).

---

## Cose strane

1. **Rifiuti "non di mercato" contati come rifiuti del mercato.** In `execute_place` un rifiuto per freno (freno d'emergenza, modo ordini, freni illeggibili; anche il freno paper `blocco_paper`) passa comunque da `_rifiutata` (`service.py:927`) e da `_esito_rifiuto_mercato` (`:934`) PRIMA di `_ferma_aperture` (`:939-942`): per la copertura `over_cover` il freno delle coperture conta un "rifiuto" che non viene dal mercato (con 3 conteggi uguali la copertura resta BLOCCATA anche dopo che il freno e' tolto, finche' "Riprendi"). Il commento di `_rifiutata` dice "si scrive SOLO dove ... la risposta e' definitiva" del mercato.
2. **La copertura e' frenata dai freni d'apertura.** `over_cover` non e' una chiusura per `execution` (`is_closing` falso): in live il freno d'emergenza e `LIVE_ORDER_MODE` la bloccano (`execution.py:872`), in paper `blocco_paper` (`service.py:839-841`), e il runner giu' ferma le aperture comprese le coperture (`_ferma_aperture` include `over_cover`). Invece col ripiego REST la copertura e' trattata come protezione (`APERTURE_MIKE`, `:1154`). Due regole diverse per la stessa gamba.
3. **`_RealMarket` senza `order_state_by_bet_id`** (vedi Differenze 9): il ramo "scaduto alla sospensione" in live reale per un ordine non abbinato non e' raggiungibile; nel banco il finto ce l'ha (`banco_comune.py:836`), quindi il replay esercita una strada che la produzione non ha.
4. **Commento di testa di `service.py` superato**: righe 10-13 descrivono il paper "fill sul feed ... DIFFERITO di bet_delay"; righe 3-8 citano le richieste "cashout / flatten / skip / resume" (mancano cancel e approva_uscita).
5. **Commento di `execute_place` righe 823-828**: parla di "ladder a LIQUIDITA' ZERO" e `paper_no_fill`; in realta' `execution.place` in paper senza runner restituisce subito `paper_senza_runner:<motivo>` (`execution.py:846`) senza usare la ladder. `ladder_paper` e' di fatto inutile.
6. **`_gia_appoggiata`**: il commento dice "si confronta ruolo + ciclo + mercato + lato", il codice confronta ruolo, ciclo e lato, NON il mercato (`service.py:1377-1386`).
7. **`feed_cache_s`**: commento (`service.py:320` "2 s di default") contro `config.py:327` (4,0).
8. **Attesa bloccante in paper**: dopo ogni ordine taker paper il giro intero si ferma fino a 15 s (`service.py:860-862`); con piu' partite le altre aspettano. Nel banco l'attesa e' 0 (`replay_registrazioni.py:456`): il replay non misura questo ritardo.
9. **`_segui_ordini_paper_su_runner` chiamata da `execute_place` senza memoria delle righe** (`cache` assente, `:863-865`): per ogni gamba della partita rilegge le righe dal database.
10. **Primo ordine paper dopo l'avvio**: `_porta_paper` accende il collegamento al primo uso (`porta_mike(avvia=True)`) e subito chiede `disponibile()`; finche' non e' collegato l'ordine e' dichiarato "runner non raggiungibile" e le aperture si fermano (fino al giro in cui la causa sparisce).
11. **Lay appoggiata paper senza eventi**: nessun limite di tempo (`service.py:1496` vale solo per i taker) e il controllo dei 120 s esclude le appoggiate (`_run_event:4331`): se la memoria della porta si perde (riavvio del processo) la gamba puo' restare `pending` a lungo.
12. **Freni sulla lay appoggiata mai usati oggi**: tutte le appoggiate sono `*_green`, quindi `_resting_e_chiusura` e' sempre vero; il ramo freno di `_piazza_resting_live` (`:1933-1942`) e `_freno_resting_paper` (`_run_event:4498`) non scattano mai.
13. **Ordine dei freni diverso fra paper e live sulla lay appoggiata**: live prima l'anti-doppione poi il freno d'emergenza; paper prima il freno poi l'anti-doppione (`_run_event:4498-4507`). Oggi senza effetto (punto 12).
14. **`_aggiorna_riga_resting`** scrive `meta.phase="open"` anche quando lo stato resta `pending` e mette `size` = abbinato (0 appena piazzata): la colonna `size` di una lay appena appoggiata vale 0 (il chiesto sta nelle colonne nuove). L'esposizione (`liability`) non viene aggiornata.
15. **`_sorveglia_sospensione`**: guarda solo l'Under 3.5 (Differenze 14); se il mercato passa da sospeso a CHIUSO la memoria `riapertura` resta "non letta" per sempre (`:2899-2900`). In paper applica la scadenza a OGNI sospensione (anche non dovuta a evento materiale), in live decide Betfair: possibile divergenza.
16. **In paper alla riapertura** una gamba con abbinato parziale e annullo confermato viene etichettata "abbinato" (mappa `{"open": abbinato}`, `:2934`), non "parziale".
17. **`azzera_cache_di_processo` incompleta rispetto a `svuota_le_cache`**: non azzera `_ATTESE_RESTING`, `_RIPIEGO_REST_ULTIMO`, `_ULTIMO_STATO_SCANNER`, `_CACHE_FEED`, `_CACHE_AGGREGATI`, `_FLUSSO_CRITICO/_RIPIEGO`; `_SENZA_RUNNER_LOGGATO` non lo azzera nessuna delle due. Nel banco questi valori sopravvivono fra scenari (difetto 37 del catalogo).
18. **`_log_throttled` scrive `log_seen` nel contesto partita** (`:1299`), che e' salvato e NON e' nella lista dei campi volatili (`_CTX_VOLATILI`): ogni avviso limitato cambia l'impronta e provoca una riscrittura della riga partita.
19. **`process_requests`**: `db.set_request_status(rid, "processing")` (`:3097`) e' fuori dal blocco protetto: se fallisce, il giro delle richieste si interrompe e le successive restano; quelle "in lavorazione" vengono chiuse in errore dopo 10 minuti.
20. **Codice mai chiamato in produzione**: `ACTIVE_STATES` (`:72`, nessun uso); `_RealMarket.market_profit_and_loss` (`:223`, nessun chiamante); `porta_ordini.ref_ordine` (il servizio scrive `mike-t{id}` da se'); `porta_ordini.azzera` (nessun chiamante trovato).
21. **Lettura dello scanner e degli ordini vivi senza cadenza**: `_scanner_age` legge a ogni giro; `_segui_resting_live` fa una chiamata REST `list_current_orders` per ogni lay appoggiata viva a ogni giro (Cost. §17.4 punto 1 chiede un parametro di cadenza per ogni lettura periodica).
22. **Importi legalizzati**: con `exact_sizes` spento si alza al minimo OGNI punta sotto il minimo, non solo le aperture come dice il commento (`:746-753`).
23. **`_attendi_terminale`** legge l'attributo interno `mem._eventi` della memoria della porta (`:1425-1426`).
24. **Codice del freno copertura in paper** = `runner_<fase>`: fasi diverse (`annullato`, `scaduto`, `rifiutato`) azzerano il conteggio l'una con l'altra ("codice diverso = notizia nuova"), quindi il freno puo' non scattare mai se il runner alterna le fasi.

---

## Non ho capito / non ho letto

1. **Area motore**: non ho letto come `engine.decide` usa `aperture_ferme`, `rifiuti` (`registra_rifiuto`), `riapertura`, `cover_mercato`, `uscita_approvata`, ne' se la seconda puntata `under_second` sia bloccata altrove a bot fermo (Differenze 13). Rimando al delegato del motore.
2. **Fuori area servizio**: non ho letto `_request_flatten`, `_request_cancel`, `_reconcile_unknown`, `_aggancia_riserve_orfane`, `run_once` oltre riga 3510, `_run_event` fuori dalle righe 4290-4530; di `_mark_trade_cancelled` ho letto solo il corpo (5077-5186), non `X.annulla_su_betfair`.
3. **Runner e motore ordini** (`motore_ordini`, flumine simulato): non ho letto come il runner esegue il place-and-trim con FOK, come applica il ritardo, e se dopo un riavvio del processo Mike la memoria degli eventi della porta viene ripopolata (sequenze `da_seq`): da questo dipende il punto 11 delle Cose strane.
4. **FILL_OR_KILL senza soglia minima**: non ho verificato sulla documentazione Betfair se un FOK senza `minFillSize` possa tornare abbinato in parte; il codice gestisce comunque il parziale (`execution.py:933-944`).
5. **`omega_market.place_submin_live`** e **`cancel_order_live`**: letta solo la firma e la descrizione, non la sequenza completa.
6. **`listCurrentOrders` e ordini scaduti**: non ho verificato se un ordine LAPSED senza abbinamento sparisce dai correnti (lo presuppone il codice e la mia deduzione al punto 9 delle Differenze).
7. **`feed.feed_fresh`, `F._flusso`** (freschezza, flusso interrotto, promemoria): fuori area, non letti; le soglie di "feed stantio" citate vengono dalla Costituzione, non dal codice.
8. **`controls.motivo_kill_switch`** letto solo fino a riga 132 (cache del database "~2 s" presa dal commento).
9. **`X.aggiorna_trade`** (scrittura delle colonne chiesto/abbinato/residuo): non letto; presumo che tolleri colonne mancanti.
10. **`AA.Guardia` (`_GUARDIA_AVVIO`)**: non letto il funzionamento interno.
