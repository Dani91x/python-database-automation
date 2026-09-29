# Inventario Mike - AREA B: la strategia (cosa decide il bot in ogni momento della partita)

- **Intervallo letto**: `Betfair/mike/engine.py` righe 2494-3869 (da `_entry_guard` alla fine del file), riga per riga.
- **Letto in piu', solo per capire le chiamate fuori area** (non inventariato qui, e' delle aree A/C): `engine.py` 30-75
  (costanti), 82-383 (Book, Leg, Snapshot, MatchCtx, Action, Decision), 409-532 (matematica copertura), 550-705
  (stato del mercato, esposizione, posizione, capitale investito), 737-805 (`cashout_value`), 993-1016, 1075-1251
  (cash out intelligente, uscita a modello, `cover_timing`), 1464-1560, 1672-1816, 1854-2216 (le guardie di `decide`),
  2225-2491 (`gate_uscite`, `_dispatch`); `Betfair/stream/trading/greenup.py` 118-210 (`compute_greenup`);
  `Betfair/mike/service.py` 1235-1276 (`_live_exit_override`, `_params_for`); `Betfair/mike/config.py` intero;
  `Betfair/mike/COSTITUZIONE_MIKE.md` §3, §5, §15.1-15.6, §16.4-bis (punti 1-66).
- **Numero di schede**: 52 (piu' la sezione «Percorso di una partita, passo per passo»).
- **Valori**: tutti i numeri sono i DEFAULT di `config.py` (`PARAM_SPEC`), modificabili dalla UI (tabella `mike_control.params`,
  passano da `merge_params` con limiti min/max). Dove un valore e' una costante del codice e' scritto «costante».

## Elenco di TUTTE le funzioni dell'intervallo e scheda che le copre

| Funzione / costante | Righe | Scheda |
|---|---|---|
| `_entry_guard` | 2495-2538 | 1 |
| `VETO_U35_NODI`, `VETO_U35_NOTE` (costanti) | 2560-2567 | 3 |
| `veto_u35_acceso` | 2570-2577 | 2 |
| `soglia_veto_under35` | 2580-2598 | 3 |
| `valuta_veto_under35` | 2601-2625 | 4 |
| `_decide_prematch` | 2628-2816 | 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18 |
| `_after_entry_fill` | 2819-2832 | 19 |
| `_cycle_done` | 2835-2855 | 20 |
| `_after_final_green` | 2858-2908 | 21 |
| `gol_dopo_il_fischio` | 2934-2942 | 22 |
| `momento_del_gol` | 2945-2960 | 23 |
| `finestra_uscita_scaduta` | 2963-2981 | 24 |
| `piano_uscita_ko` | 2984-2998 | 25 |
| `_decide_ko_green` | 3001-3157 | 26, 27, 28, 29, 30, 31 |
| `_decide_second_entry` | 3160-3225 | 32 |
| `attesa_prima_tranche` | 3228-3237 | 33 |
| `frazione_copertura` | 3240-3270 | 34 |
| `_decide_uncovered` | 3273-3412 | 35, 36 |
| `_late_persist_cancel` | 3415-3422 | 37 |
| `_decide_cover_pending` | 3425-3498 | 38 |
| `_loss_rule` | 3501-3508 | 39 |
| `_decide_covered` | 3511-3603 | 40, 41, 42, 43, 44 |
| `_decide_closing` | 3606-3651 | 45 |
| `residuo_non_chiudibile` | 3654-3674 | 46 |
| `_decide_flat` | 3677-3708 | 47 |
| `_decide_reentry_pending` | 3711-3740 | 48 |
| `_decide_reentry_open` | 3743-3787 | 49 |
| `_decide_reentry_green_pending` | 3790-3808 | 50 |
| `apply_decision` | 3814-3869 | 51 |
| (tipi d'ordine usati da tutta l'area: `_place`, persistenza) | 1487-1491 | 52 |

## Premessa per chi legge (come «pensa» il bot)

Il bot gira ogni ~0,5-2 secondi su ogni partita (parametro `decide_min_interval_ms` = 500 ms, servizio). A ogni giro
guarda lo **stato** della partita (una parola come `WATCH`, `PRE_OPEN`, `LIVE_COVERED`: sono le «caselle» della macchina
a stati, tradotte nel Glossario) e decide UNA cosa: piazzare ordini, ritirarne, cambiare casella, o niente. Le schede
di questa area descrivono cosa decide in ogni casella.

Tre cose valgono sempre e NON sono in quest'area (stanno in `decide`, area A), ma cambiano cio' che succede davvero:
1. **Uscite manuali di default** (`uscite_automatiche` = False, `config.py:254`): ogni USCITA discrezionale che la
   strategia decide qui (green-up pre-match `under_green`, uscita al fischio `ko_green`, cash out e uscite in perdita
   `under_close`/`over_close`, green del re-ingresso `reentry_green`) NON parte: diventa una **proposta** nella scheda
   che l'utente approva o no (`engine.gate_uscite`, 2337). Restano sempre automatici: copertura Over 4,5, cap perdita
   partita (`loss_cap`), annulli degli ordini d'ingresso, regolamento. Quando in questa area scrivo «piazza una lay di
   uscita», con i default di oggi va letto «propone all'utente una lay di uscita».
2. **Mai due lay a mercato** (`_una_sola_lay`, 1901): se su una selezione c'e' gia' una lay viva o a esito ignoto,
   una lay nuova viene rimandata al giro dopo (parte solo l'annullo). Stesso per la copertura (`_mai_sovracopertura`,
   1972) e per il freno sui rifiuti della copertura (`_freno_copertura`, 2023: max 3 rifiuti con lo stesso codice,
   minimo 15 s fra due tentativi).
3. **Ordine a esito ignoto o aperture ferme**: vengono tolti tutti gli ordini di APERTURA (`_strip_openings`, 1854).

---

## PRE-PARTITA

### 1. Le condizioni per entrare (il cancello d'ingresso)
- **Cosa fa**: prima di ogni puntata sull'Under 3,5 in pre-partita controlla, nell'ordine, 13 condizioni. Alla prima che
  non va, non entra e scrive il motivo.
- **Quando scatta**: in casella `WATCH` (scheda 6), a ogni giro. Controlli nell'ordine esatto:
  1. partita chiusa a mano dall'utente (`no_reentry`) -> «rientro disabilitato (chiusura manuale): premi Riprendi»;
  2. chiusura manuale in corso (`flatten_pending`) -> «chiusura manuale in corso»;
  3. pre-partita spento (`pre_enabled` = False) -> «pre_disabilitato»;
  4. dati non abbastanza freschi per mandare un ordine (`snap.order_fresh` falso, calcolato dal servizio con
     `order_max_age_s` = 20 s e `order_scanner_max_s` = 30 s) -> «feed stantio»;
  5. troppo presto: adesso < fischio - `entry_hours_before_ko` (1,0 ore) -> «fuori finestra»;
  6. troppo tardi: adesso >= fischio - `pre_last_entry_min` (10 minuti) -> «finestra pre-match chiusa»;
  7. cicli gia' fatti (`cycle_no`) >= `pre_max_cycles` (10) -> «max cicli»;
  8. pausa dopo l'ultimo green: meno di `pre_reentry_cooldown_s` (60 s) dall'ultimo ciclo chiuso -> «cooldown»;
  9. manca il book Under 3,5, o la quota back non e' valida, o il mercato non e' APERTO, o il book dice gia' in gioco
     -> «book assente»;
  10. quota back Under 3,5 fuori dalla banda `pre_entry_price_min` 1,30 - `pre_entry_price_max` 3,00 -> «prezzo X fuori banda»;
  11. liquidita' disponibile al miglior back < stake x `pre_min_back_size_factor` (10 x 1,0 = 10 EUR) -> «liquidita X < Y»;
  12. se c'e' una quota lay: distanza fra miglior back e miglior lay > `pre_max_spread_ticks` (6 tick), o non calcolabile
      -> «spread N tick»;
  13. stake > spazio residuo sotto `max_liability_per_match` (0 = nessun tetto) -> «cap liability partita».
- **Cosa succede dopo**: se tutte passano, la scheda 6 piazza l'ingresso. Altrimenti resta in `WATCH` con il motivo.
- **Numeri**: `entry_hours_before_ko` 1,0 h (limiti 0,25-12); `pre_last_entry_min` 10 min (1-120); `pre_max_cycles` 10
  (0-100); `pre_reentry_cooldown_s` 60 s (0-3600); `pre_entry_price_min` 1,30; `pre_entry_price_max` 3,00;
  `pre_min_back_size_factor` 1,0 (0,5-5); `stake` 10 EUR (0,50-500); `pre_max_spread_ticks` 6 (1-20);
  `max_liability_per_match` 0 = spento. Tutti `config.py`.
- **Esempio**: fischio alle 21:00, sono le 20:30, Under 3,5 back 1,50 con 42 EUR disponibili, lay 1,52 (2 tick): entra.
  Alle 20:51 non entra piu' («finestra pre-match chiusa»). Alle 19:45 non entra ancora («fuori finestra»).
- **Cosa vede l'utente**: il motivo nella card/attivita' (testi tra virgolette sopra).
- **Dove**: `engine.py:2495-2538` (1: 2497; 2: 2500; 3: 2502; 4: 2504; 5: 2512-2514; 6: 2515; 7: 2517; 8: 2519;
  9: 2521-2523; 10: 2524; 11: 2526-2528; 12: 2532-2535; 13: 2536). Spazio residuo: `liability_room` 1707.
- **Paper o live**: identico. Il servizio, a bot fermo, forza `pre_enabled` = False (`service.py:1273`).

### 2. L'interruttore del veto sulla probabilita' calibrata dell'Under 3,5
- **Cosa fa**: dice se il «veto» (scheda 4) e' acceso.
- **Quando scatta**: ogni volta che serve sapere se il veto va valutato (schede 4, 11, 21).
- **Cosa succede dopo**: se la chiave `veto_p_under35_cal` manca dai parametri si usa il default della whitelist
  (ACCESO); se c'e' ma non e' un vero/falso, e' SPENTO.
- **Numeri**: `veto_p_under35_cal` = True (acceso) di default, `config.py:152`.
- **Esempio**: parametri presi dalla UI senza la chiave -> acceso; chiave = "si" (testo) -> spento (ma `merge_params`
  converte sempre in vero/falso, quindi in pratica vale il valore della UI).
- **Cosa vede l'utente**: niente direttamente.
- **Dove**: `engine.py:2570-2577`.
- **Paper o live**: identico.

### 3. La soglia del veto alla quota di adesso
- **Cosa fa**: data la quota back dell'Under 3,5, calcola la probabilita' minima che l'Under deve avere (secondo il
  modello calibrato) perche' tenere la posizione valga la pena.
- **Quando scatta**: dentro la scheda 4.
- **Cosa succede dopo**: restituisce un numero fra 0 e 1. Cinque punti fissi (quota -> soglia), fra due punti si
  interpola in linea retta; sotto 1,30 vale la soglia di 1,30, sopra 3,00 quella di 3,00.
- **Numeri**: nodi (costante `VETO_U35_NODI`, valori modificabili dalla UI): 1,30 -> 0,807 (`veto_p_under35_soglia_130`);
  1,50 -> 0,684 (`..._150`); 2,00 -> 0,514 (`..._200`); 2,50 -> 0,385 (`..._250`); 3,00 -> 0,275 (`..._300`).
  `config.py:153-157`. Un valore non numerico nella UI torna al default del nodo.
- **Esempio**: quota 1,40 -> 0,807 + (0,684 - 0,807) x (0,10 / 0,20) = 0,7455. Quota 1,20 -> 0,807. Quota 3,50 -> 0,275.
- **Cosa vede l'utente**: la soglia compare nel motivo del veto (scheda 4).
- **Dove**: `engine.py:2560-2566` (nodi), `2580-2598`. Testo fisso della nota d'ordine: `VETO_U35_NOTE` = «veto P
  calibrata Under 3.5: chiusura in perdita» (2567).
- **Paper o live**: identico.

### 4. Il veto sull'Under 3,5 (probabilita' calibrata contro quota)
- **Cosa fa**: confronta la probabilita' calibrata che la partita finisca con 0-3 gol (dal dossier pre-partita) con
  la soglia della scheda 3. Se e' sotto, dichiara «veto»: la posizione in perdita non si porta in gioco e l'ultimo
  ingresso non si fa.
- **Quando scatta**: solo in due punti: a 10' dal fischio con posizione in perdita (scheda 11, punto «hold») e prima
  di piazzare l'ultimo ingresso PERSIST (scheda 21, punto «persist»).
- **Cosa succede dopo**: restituisce uno di tre esiti: `veto` (P < soglia), `nessun_veto` (P >= soglia),
  `non_valutabile` (manca la P calibrata nel dossier, o manca la quota: nessun veto). Se l'interruttore e' spento
  restituisce niente e il bot si comporta come prima del 25/09.
- **Numeri**: soglie della scheda 3. La P viene da `snap.p_under35_cal` (dossier, `markets_calibrated.over_3_5`, letta
  dal servizio: `service.py:290`, `4250`).
- **Esempio**: quota Under 1,40, P calibrata 0,70, soglia 0,7455 -> «veto», motivo «P calibrata 0.700 < soglia 0.746 a
  quota 1.40». Con P 0,80 -> «nessun_veto».
- **Cosa vede l'utente**: attivita' con la voce `veto_under_calibrata` (punto, P, quota, soglia, esito, motivo, eseguito).
- **Dove**: `engine.py:2601-2625`.
- **Paper o live**: identico.

### 5. Il fischio d'inizio: passaggio dal pre-partita al gioco
- **Cosa fa**: appena la partita risulta in gioco, qualunque sia la casella pre-partita, ritira gli ordini non abbinati
  e decide come entra in gioco: con posizione Under 3,5 -> prova l'uscita al fischio; senza posizione -> «in gioco
  senza posizione».
- **Quando scatta**: `snap.inplay` vero, casella in `WATCH`, `PRE_ENTRY_PENDING`, `PRE_OPEN`, `PRE_GREEN_PENDING`,
  `HOLD` o `PRE_LAST_ENTRY_PENDING`. E' il PRIMO controllo di `_decide_prematch`, prima di tutto il resto.
- **Cosa succede dopo**:
  - ritira ogni ordine vivo, TRANNE l'ultimo ingresso PERSIST (`under_last`) se dal fischio di calendario sono passati
    meno di `cancel_unmatched_after_ko_s` (120 s): quello puo' ancora abbinarsi;
  - se c'e' posizione Under (S > 0): scrive il prezzo del primo ingresso (se non c'era), il prezzo back dell'Under al
    fischio (UNA volta sola), l'ora in cui si e' visto il gioco (`live_since`, da qui parte la finestra d'uscita) e i
    gol al fischio (`ko_goals`);
    - uscita al fischio accesa (`ko_green_enabled`) e prezzo medio valido -> casella `LIVE_KO_GREEN`, «in gioco: provo
      l'uscita a +2 tick»;
    - altrimenti -> casella `LIVE_UNCOVERED` con copertura «ordinata» (`cover_forced`), «in-play con posizione Under»;
  - senza posizione -> casella `IDLE_LIVE`, «in-play senza posizione».
- **Numeri**: `cancel_unmatched_after_ko_s` 120 s (0-900); `ko_green_enabled` True; `ko_green_ticks` 2.
- **Esempio**: posizione 10 EUR back @ 1,50, fischio visto alle 21:00:40 -> `live_since` = 21:00:40, `ko_goals` = 0,
  casella `LIVE_KO_GREEN`.
- **Cosa vede l'utente**: il motivo; la fase della card passa in gioco.
- **Dove**: `engine.py:2636-2666` (grazia PERSIST 2641-2643; prezzo al fischio 2650-2651; `live_since` 2656-2659;
  uscita 2660-2663; copertura 2664-2665; senza posizione 2666).
- **Paper o live**: identico.

### 6. L'ingresso di un ciclo pre-partita
- **Cosa fa**: se il cancello (scheda 1) e' aperto, punta l'Under 3,5 con lo stake intero al miglior prezzo back.
- **Quando scatta**: casella `WATCH`, partita non in gioco, `_entry_guard` senza motivi.
- **Cosa succede dopo**: ordine BACK, mercato Over/Under 3,5, selezione Under, quota = miglior back di adesso
  (arrotondata alla scala Betfair), importo = `stake` (10 EUR), ruolo `under_entry`, **cade al fischio** (LAPSE). Casella
  -> `PRE_ENTRY_PENDING`, «ingresso ciclo N» (N parte da 1).
- **Numeri**: `stake` 10 EUR.
- **Esempio**: back 10 EUR @ 1,50 sull'Under 3,5, «ingresso ciclo 1».
- **Cosa vede l'utente**: riga d'ordine nella scheda Trade e motivo in attivita'.
- **Dove**: `engine.py:2668-2674`.
- **Paper o live**: stesso ordine; l'esecuzione (simulata o vera) e' del servizio.

### 7. L'attesa dell'abbinamento dell'ingresso (e la scadenza a 60 secondi)
- **Cosa fa**: controlla l'ultima puntata d'ingresso e decide se e' entrata, se aspettare o se ritirarla.
- **Quando scatta**: casella `PRE_ENTRY_PENDING`, partita non in gioco.
- **Cosa succede dopo** (nell'ordine):
  1. nessuna gamba d'ingresso -> `WATCH`, «gamba assente»;
  2. ordine non piu' vivo e niente abbinato (ritirato, rifiutato, scaduto) -> `WATCH`, «ingresso non abbinato»
     (nessuna pausa, nessun ciclo contato: al giro dopo il cancello puo' rientrare subito);
  3. abbinato per intero e non piu' vivo -> scheda 19 (dopo l'abbinamento);
  4. ancora vivo da >= `pre_entry_ttl_s` (60 s): se ha abbinato qualcosa -> ritira il residuo e passa a `PRE_OPEN`
     tenendo la parte abbinata («ttl: tengo la parte abbinata»); se non ha abbinato niente -> ritira e torna a `WATCH`
     («ttl scaduto»);
  5. ancora vivo ma gia' abbinato per intero -> scheda 19;
  6. altrimenti -> resta, «attesa fill ingresso».
- **Numeri**: `pre_entry_ttl_s` 60 s (5-3600).
- **Esempio**: back 10 EUR @ 1,50 piazzato alle 20:30:00; alle 20:31:00 ha abbinato 4 EUR -> ritira i 6 EUR restanti, posizione
  4 EUR @ 1,50, casella `PRE_OPEN`.
- **Cosa vede l'utente**: i motivi sopra.
- **Dove**: `engine.py:2676-2691` (2678-2679; 2680-2681; 2682-2683; 2684-2688; 2689-2690; 2691).
- **Paper o live**: identico.

### 8. Posizione pre-partita sparita
- **Cosa fa**: se in `PRE_OPEN` la posizione Under risulta zero, ritira tutto e torna a guardare.
- **Quando scatta**: casella `PRE_OPEN`, somma degli Under abbinati e non archiviati (S) <= 0.
- **Cosa succede dopo**: ritira ogni ordine vivo; casella `WATCH`, «posizione assente».
- **Numeri**: nessuno.
- **Esempio**: gamba d'ingresso annullata dalla riconciliazione -> torna a `WATCH`.
- **Cosa vede l'utente**: «posizione assente».
- **Dove**: `engine.py:2694-2695`.
- **Paper o live**: identico.

### 9. Ultimo ingresso (10' dal fischio): posizione gia' piatta
- **Cosa fa**: a 10 minuti dal fischio, se la posizione e' gia' chiusa in pari (green abbinato), chiude il ciclo.
- **Quando scatta**: casella `PRE_OPEN`, adesso >= fischio - `pre_last_entry_min` (10'), esposizione netta piatta
  (differenza fra vincita e perdita < 0,01 EUR).
- **Cosa succede dopo**: ritira la lay di green eventualmente viva; poi chiusura ciclo (scheda 20) -> `WATCH`. Da
  `WATCH` il cancello e' ormai chiuso («finestra pre-match chiusa»): nessun ultimo ingresso PERSIST in questo caso.
- **Numeri**: `pre_last_entry_min` 10; soglia piatto 0,01 EUR (costante `_FLAT_EPS`).
- **Esempio**: resting green abbinata alle 20:50:05 -> ciclo chiuso, la partita entra in gioco senza posizione.
- **Cosa vede l'utente**: «ciclo N chiuso: +0.14».
- **Dove**: `engine.py:2702-2705`.
- **Paper o live**: identico.

### 10. Ultimo ingresso: in profitto -> chiusura finale al mercato
- **Cosa fa**: a 10' dal fischio, se chiudere ADESSO al miglior prezzo lay blocca un profitto, ritira la green appoggiata
  e chiude la posizione con una lay al miglior prezzo.
- **Quando scatta**: casella `PRE_OPEN`, adesso >= fischio - 10', posizione non piatta, c'e' un prezzo lay, il calcolo
  di chiusura (`compute_greenup` sul miglior back/lay) e' eseguibile e il profitto bloccato (il minore dei due esiti,
  al lordo della commissione) > 0,01 EUR.
- **Cosa succede dopo**: ritira la `under_green` viva; ordine LAY, Over/Under 3,5, Under, quota = miglior lay,
  importo = (vincita - perdita) / quota (chiude tutta l'esposizione netta), ruolo `under_green`, marcato «finale»,
  cade al fischio (LAPSE), nota «ultimo ingresso: chiusura in profitto». Casella -> `PRE_GREEN_PENDING`, «ultimo
  ingresso: locked X > 0». Se la green vecchia e' ancora viva, la lay nuova parte al giro dopo (regola «mai due lay»).
- **Numeri**: `pre_last_entry_min` 10; soglia 0,01 EUR.
- **Esempio**: back 10 EUR @ 1,50 (vince +5, perde -10). Miglior lay 1,46 -> lay 15/1,46 = 10,27 EUR @ 1,46; bloccato
  -10 + 10,27 = +0,27 EUR su ogni esito.
- **Cosa vede l'utente**: motivo; telemetria `last_entry_locked`. Con le uscite manuali (default) e' una proposta.
- **Dove**: `engine.py:2702-2703`, `2714-2721`.
- **Paper o live**: identico.

### 11. Ultimo ingresso: in perdita -> tengo (HOLD) oppure veto e chiudo in perdita
- **Cosa fa**: a 10' dal fischio, se chiudere adesso non darebbe profitto, di norma TIENE la posizione e la porta in
  gioco. Col veto acceso (default) e la P calibrata sotto soglia, invece la CHIUDE in perdita al miglior prezzo lay.
- **Quando scatta**: casella `PRE_OPEN`, adesso >= fischio - 10', posizione non piatta, e uno di questi:
  - (a) manca il book o manca la quota lay: casella `HOLD`, «ultimo ingresso: prezzo lay assente, tengo» (se il veto e'
    acceso lo valuta solo per scriverlo, `eseguito` = falso: senza prezzo lay non si puo' chiudere);
  - (b) profitto bloccabile <= 0,01 EUR e veto spento o non applicabile: `HOLD`, «ultimo ingresso: locked X <= 0, tengo»;
  - (c) profitto bloccabile <= 0,01, veto acceso con esito «veto» e chiusura eseguibile: LAY finale al miglior lay per
    tutta l'esposizione (ruolo `under_green`, «finale», LAPSE, nota «veto P calibrata Under 3.5: chiusura in perdita»),
    casella `PRE_GREEN_PENDING`, si ricorda il veto (`veto_u35`) sulla partita;
  - (d) veto acceso ma esito «nessun_veto» o «non_valutabile»: `HOLD`, «tengo», con la telemetria del veto.
- **Cosa succede dopo**: in tutti i casi ritira la `under_green` appoggiata. `HOLD` aspetta il fischio (scheda 17).
  Nel caso (c) l'attivita' si scrive una volta sola (se il veto era gia' scritto o c'e' gia' una lay in volo, niente
  telemetria).
- **Numeri**: soglie scheda 3; `pre_last_entry_min` 10.
- **Esempio**: back 10 EUR @ 1,50, adesso back 1,60 / lay 1,62 -> chiudere costa: lay 15/1,62 = 9,26 EUR, bloccato -0,74.
  P calibrata 0,62 a quota back 1,60: soglia 0,684 + (0,514-0,684) x 0,10/0,50 = 0,650 -> veto: lay 9,26 @ 1,62, perdita
  bloccata -0,74. Con P 0,70 -> tengo (HOLD).
- **Cosa vede l'utente**: motivi sopra; con le uscite manuali (default) il caso (c) e' una proposta.
- **Dove**: `engine.py:2706-2713` (a), `2722-2743` (b, c, d).
- **Paper o live**: identico.

### 12. Posizione pre-partita tornata piatta: ciclo chiuso
- **Cosa fa**: se la lay di green si e' abbinata per intero (esposizione piatta) e non ci sono green vive, chiude il ciclo.
- **Quando scatta**: casella `PRE_OPEN`, prima dei 10' finali, esposizione piatta e nessuna `under_green` viva.
- **Cosa succede dopo**: scheda 20 -> `WATCH`.
- **Numeri**: soglia piatto 0,01 EUR.
- **Esempio**: back 10 @ 1,50 + lay 10,14 @ 1,48 abbinata -> «ciclo 1 chiuso: +0.14».
- **Cosa vede l'utente**: il motivo e la riga `pre_cycle`.
- **Dove**: `engine.py:2745-2746`.
- **Paper o live**: identico.

### 13. Green appoggiata (modo «resting», il default)
- **Cosa fa**: tiene sul book una lay di green 2 tick sotto il prezzo medio d'ingresso; se non c'e' (mai messa,
  ritirata, o abbinata solo in parte e poi ritirata) ne rimette una per il residuo.
- **Quando scatta**: casella `PRE_OPEN`, prima dei 10' finali, posizione non piatta, `pre_exit_mode` = «resting».
- **Cosa succede dopo**:
  - green assente o non viva: LAY, Over/Under 3,5, Under, quota = prezzo medio - `pre_green_ticks` (2 tick), importo =
    esposizione netta / quota, ruolo `under_green`, cade al fischio (LAPSE). Resta in `PRE_OPEN`, «green resting
    appoggiata» (o «(residuo)»). Se la stessa identica richiesta era gia' stata rifiutata dal mercato non la ripete
    («gia' rifiutata a mercato ... non si ripropone identica»);
  - green viva: niente, «posizione aperta, green resting sul book».
- **Numeri**: `pre_exit_mode` «resting» (scelte resting/taker); `pre_green_ticks` 2 (1-10).
- **Esempio**: posizione 10 EUR @ 1,50, green abbinata per 4 EUR e poi ritirata: esposizione vince +5 - 4x0,48 = +3,08, perde
  -10 + 4 = -6 -> nuova lay (3,08+6)/1,48 = 6,14 EUR @ 1,48.
- **Cosa vede l'utente**: motivi sopra; con le uscite manuali e' una proposta la prima volta del ciclo (vedi Cose strane).
- **Dove**: `engine.py:2747-2761`; freno sui rifiuti `tentativo_gia_rifiutato` 1522.
- **Paper o live**: identico nell'engine. In live, se l'utente spegne `live_resting_enabled` (default acceso), il
  servizio forza `pre_exit_mode` = «taker» (`service.py:1262-1264`) e vale la scheda 14.

### 14. Green al mercato (modo «taker»)
- **Cosa fa**: non appoggia niente; aspetta che il miglior lay scenda a 2 tick sotto il prezzo d'ingresso e allora
  chiude al miglior lay.
- **Quando scatta**: casella `PRE_OPEN`, prima dei 10' finali, posizione non piatta, `pre_exit_mode` = «taker».
- **Cosa succede dopo**: se miglior lay <= prezzo medio - 2 tick e la chiusura e' eseguibile: LAY al miglior lay per
  tutta l'esposizione (ruolo `under_green`, LAPSE), casella `PRE_GREEN_PENDING`, «green taker: 2 tick disponibili»
  (salvo richiesta identica gia' rifiutata: resta `PRE_OPEN`). Altrimenti `PRE_OPEN`, «posizione aperta, in attesa dei
  2 tick».
- **Numeri**: `pre_green_ticks` 2.
- **Esempio**: back 10 @ 1,50, miglior lay 1,48 -> lay 10,14 @ 1,48.
- **Cosa vede l'utente**: motivi sopra.
- **Dove**: `engine.py:2762-2777`.
- **Paper o live**: identico; e' il ramo che il live usa se `live_resting_enabled` e' spento.

### 15. Attesa della green al mercato / della chiusura finale
- **Cosa fa**: segue la lay di chiusura piazzata dalle schede 10, 11(c) o 14.
- **Quando scatta**: casella `PRE_GREEN_PENDING`, partita non in gioco.
- **Cosa succede dopo** (nell'ordine):
  1. nessuna `under_green` -> `PRE_OPEN`, «green assente»;
  2. green non viva e niente abbinato -> se era «finale» `HOLD`, altrimenti `PRE_OPEN` («green non abbinata»);
  3. green abbinata (anche in parte e poi ritirata) ma esposizione ancora aperta -> `HOLD` se finale, altrimenti
     `PRE_OPEN` («green parziale: residuo aperto»);
  4. green abbinata e posizione piatta: se finale -> scheda 21 (ultimo ingresso PERSIST); altrimenti chiusura ciclo
     (scheda 20);
  5. green viva da >= `close_retry_s` (10 s) e tentativi < `close_max_attempts` (20), mercato aperto con prezzo lay:
     ritira la green e ne manda una nuova al miglior lay per l'esposizione netta (stessa marcatura «finale»), tentativi +1,
     «green taker: riprezzo»;
  6. altrimenti «attesa fill green».
- **Numeri**: `close_retry_s` 10 s (1-600); `close_max_attempts` 20 (1-100).
- **Esempio**: lay finale 10,27 @ 1,46 non abbinata dopo 10 s, miglior lay 1,47 -> ritira e rimanda 10,20 @ 1,47.
- **Cosa vede l'utente**: motivi sopra.
- **Dove**: `engine.py:2779-2808` (2781-2782; 2783-2786; 2787-2796; 2797-2807; 2808).
- **Paper o live**: identico. Vedi «Cose strane» n. 3: per via di «mai due lay» il riprezzo di fatto non avviene.

### 16. HOLD: si tiene la posizione in perdita fino al fischio
- **Cosa fa**: non fa niente: aspetta il fischio con la posizione Under aperta.
- **Quando scatta**: casella `HOLD`, partita non in gioco.
- **Cosa succede dopo**: resta `HOLD`, «in perdita pre-KO: tengo fino al live». Al fischio vale la scheda 5 (uscita al
  fischio).
- **Numeri**: nessuno.
- **Esempio**: back 10 @ 1,50 quotato 1,60 alle 20:50 -> HOLD fino al fischio.
- **Cosa vede l'utente**: «in perdita pre-KO: tengo fino al live».
- **Dove**: `engine.py:2810-2811`.
- **Paper o live**: identico.

### 17. Attesa dell'ultimo ingresso PERSIST
- **Cosa fa**: aspetta il fischio mentre l'ultimo ingresso PERSIST e' sul book.
- **Quando scatta**: casella `PRE_LAST_ENTRY_PENDING`, partita non in gioco.
- **Cosa succede dopo**: resta, «attesa fill ingresso PERSIST». Nessun controllo di abbinamento qui: se ne occupa il
  fischio (scheda 5).
- **Numeri**: nessuno.
- **Esempio**: back PERSIST 10 @ 1,45 piazzato alle 20:50:30: resta fino al fischio.
- **Cosa vede l'utente**: il motivo.
- **Dove**: `engine.py:2813-2814`.
- **Paper o live**: identico.

### 18. Casella pre-partita sconosciuta
- **Cosa fa**: rete di sicurezza per una casella che non esiste.
- **Quando scatta**: `_decide_prematch` chiamata con una casella non prevista.
- **Cosa succede dopo**: ritira tutti gli ordini vivi, casella `ERROR`, «stato pre-match sconosciuto X».
- **Numeri**: nessuno.
- **Esempio**: stato corrotto nel DB.
- **Cosa vede l'utente**: la partita in «DA SISTEMARE».
- **Dove**: `engine.py:2816`. (Di fatto irraggiungibile: `_dispatch` 2462-2464 chiama questa funzione solo con le sei
  caselle gestite.)
- **Paper o live**: identico.

### 19. Subito dopo l'abbinamento dell'ingresso
- **Cosa fa**: registra il prezzo del primo ingresso della partita e, in modo «resting», appoggia subito la green a 2 tick.
- **Quando scatta**: da scheda 7, ingresso abbinato per intero.
- **Cosa succede dopo**: se non c'era, `entry_price_initial` = prezzo medio di questa gamba (serve al re-ingresso,
  scheda 47). In «resting»: LAY Over/Under 3,5 Under, quota = prezzo d'abbinamento - 2 tick, importo = esposizione netta /
  quota, ruolo `under_green`, LAPSE, nota «take-profit resting». Casella `PRE_OPEN`, «ingresso abbinato». In «taker» nessun
  ordine.
- **Numeri**: `pre_green_ticks` 2; `pre_exit_mode` resting.
- **Esempio**: back 10 @ 1,50 abbinato -> lay 10,14 @ 1,48 (profitto bloccato +0,14 lordi se si abbina), come Costituzione §3.
- **Cosa vede l'utente**: «ingresso abbinato»; con le uscite manuali la green diventa proposta.
- **Dove**: `engine.py:2819-2832`.
- **Paper o live**: identico (vedi scheda 13 per il ripiego taker in live).

### 20. Chiusura di un ciclo pre-partita
- **Cosa fa**: dichiara chiuso il ciclo, calcola il profitto bloccato, ritira gli ordini ancora vivi, archivia le gambe
  del ciclo e torna a guardare per il ciclo successivo.
- **Quando scatta**: schede 9, 12, 15(4 non finale).
- **Cosa succede dopo**: ritira ogni ordine vivo; casella `WATCH`; `cycle_no` + 1; `last_green_at` = adesso (parte la
  pausa di 60 s); tentativi = 0; gambe del ciclo archiviate (restano per il conto finale, non contano piu' come rischio).
  Profitto bloccato = la vincita netta attuale dell'esposizione (se fornita) oppure stake x (prezzo ingresso / prezzo
  uscita - 1). Lordo, senza commissione.
- **Numeri**: pausa `pre_reentry_cooldown_s` 60 s (applicata dal cancello, scheda 1).
- **Esempio**: 10 @ 1,50 chiuso con 10,14 @ 1,48 -> «ciclo 1 chiuso: +0.14», telemetria `pre_cycle` {ciclo 0, entry 1,50,
  exit 1,48, stake 10, locked 0,14}.
- **Cosa vede l'utente**: il motivo e la riga di ciclo nello storico.
- **Dove**: `engine.py:2835-2855`.
- **Paper o live**: identico.

### 21. Dopo la chiusura finale: l'ultimo ingresso PERSIST
- **Cosa fa**: chiusa in profitto (o col veto) la posizione a 10' dal fischio, rientra con una puntata nuova che resta
  valida in gioco, cosi' la partita entra in gioco con una posizione Under 3,5 «fresca».
- **Quando scatta**: da scheda 15(4), lay finale abbinata e posizione piatta.
- **Cosa succede dopo** (sempre: ciclo +1, `last_green_at` = adesso, tentativi 0, gambe archiviate), nell'ordine:
  1. `last_entry_persist` spento -> `IDLE_LIVE`, «ultimo ingresso disabilitato»;
  2. veto acceso e veto gia' scattato su questa partita -> `IDLE_LIVE`, «non si rientra dopo il veto»;
  3. mercato sospeso o ignoto (con una quota valida) -> resta nella casella attuale, «ultimo ingresso: mercato sospeso,
     aspetto» (senza archiviare);
  4. book assente, quota non valida o mercato non aperto -> `IDLE_LIVE`, «ultimo ingresso: book assente»;
  5. liquidita' al miglior back < 10 EUR -> `IDLE_LIVE`;
  6. `max_liability_per_match` > 0 e stake oltre il tetto -> `IDLE_LIVE`, «cap liability partita»;
  7. quota = miglior back + `last_entry_ticks_above` tick (0 di default);
  8. veto acceso: esito «veto» alla quota del PERSIST -> `IDLE_LIVE`, «non rientro», veto ricordato;
  9. altrimenti: ordine BACK, Over/Under 3,5, Under, quota come al punto 7, importo = stake (10 EUR), ruolo `under_last`,
     **resta in gioco** (PERSIST). Casella `PRE_LAST_ENTRY_PENDING`, «ultimo ingresso PERSIST».
- **Numeri**: `last_entry_persist` True; `last_entry_ticks_above` 0 (0-3); `pre_min_back_size_factor` 1,0; `stake` 10.
- **Esempio**: lay finale abbinata alle 20:50:20, miglior back 1,45 con 30 EUR -> back 10 EUR @ 1,45 PERSIST.
- **Cosa vede l'utente**: i motivi; `IDLE_LIVE` in card = «LIVE · NESSUNA POSIZIONE».
- **Dove**: `engine.py:2858-2908` (1: 2861; 2: 2863; 3: 2873-2875; 4: 2876; 5: 2878-2880; 6: 2883-2885; 7: 2886-2889;
  8: 2890-2898; 9: 2899-2908).
- **Paper o live**: identico. A bot fermo il servizio spegne `last_entry_persist` (`service.py:1275`).

---

## DAL FISCHIO D'INIZIO

### 22. C'e' stato un gol dopo il fischio?
- **Cosa fa**: confronta i gol di adesso con quelli al fischio.
- **Quando scatta**: dentro l'uscita al fischio (scheda 27).
- **Cosa succede dopo**: vero se gol adesso > gol al fischio. Se uno dei due numeri manca: falso (meglio perdere la
  seconda puntata che inventarsi un gol).
- **Numeri**: nessuno.
- **Esempio**: al fischio 0 gol, adesso 1 -> vero. Gol al fischio sconosciuti -> falso.
- **Cosa vede l'utente**: niente direttamente.
- **Dove**: `engine.py:2934-2942`.
- **Paper o live**: identico.

### 23. Il momento del gol
- **Cosa fa**: stabilisce da quando contare l'attesa della prima tranche di copertura dopo un gol precoce.
- **Quando scatta**: quando il gol precoce viene riconosciuto (scheda 27).
- **Cosa succede dopo**: usa l'ora del gol data dal feed se e' fra 0 e 900 s fa (ultimi 15 minuti, non nel futuro);
  altrimenti usa adesso.
- **Numeri**: 900 s (costante nel codice).
- **Esempio**: gol dichiarato 25 s fa -> quell'ora. Gol dichiarato 20 minuti fa (o fra 10 s) -> adesso.
- **Cosa vede l'utente**: niente.
- **Dove**: `engine.py:2945-2960`.
- **Paper o live**: identico.

### 24. La finestra dell'uscita al fischio e' scaduta?
- **Cosa fa**: dice se sono passati i minuti concessi all'uscita al fischio.
- **Quando scatta**: dentro la scheda 28.
- **Cosa succede dopo**: falso se non si sa quando e' iniziato il gioco; falso se in questo momento il mercato Under 3,5
  non e' APERTO e IN GIOCO; altrimenti vero se adesso - `live_since` >= `ko_green_window_s` (180 s).
- **Numeri**: `ko_green_window_s` 180 s (0-900).
- **Esempio**: gioco visto alle 21:00:40, alle 21:03:40 mercato aperto in gioco -> scaduta. Alle 21:03:40 mercato sospeso
  -> non scaduta; appena riapre (es. 21:04:30) risulta subito scaduta (vedi Cose strane n. 6).
- **Cosa vede l'utente**: niente direttamente.
- **Dove**: `engine.py:2963-2981`.
- **Paper o live**: identico.

### 25. Il piano dell'uscita al fischio
- **Cosa fa**: calcola la lay di uscita: quota 2 tick sotto il prezzo medio della posizione Under, importo che chiude
  tutta l'esposizione netta.
- **Quando scatta**: dentro la scheda 30.
- **Cosa succede dopo**: se il prezzo medio non e' valido, o il piano non e' eseguibile, niente piano. Il prezzo medio
  viene prima arrotondato alla scala Betfair.
- **Numeri**: `ko_green_ticks` 2 (1-10).
- **Esempio**: posizione 10 @ 1,50 -> lay 10,14 @ 1,48 (limite: se il mercato offre meglio si abbina meglio).
- **Cosa vede l'utente**: niente direttamente.
- **Dove**: `engine.py:2984-2998`.
- **Paper o live**: identico.

### 26. Uscita al fischio: niente posizione, o PERSIST da ritirare
- **Cosa fa**: in `LIVE_KO_GREEN`, se non c'e' posizione Under ritira tutto e chiude la partita; e ritira in ogni caso il
  residuo PERSIST scaduto (scheda 37). Aggiorna `live_since` e i gol al fischio se mancavano.
- **Quando scatta**: casella `LIVE_KO_GREEN`.
- **Cosa succede dopo**: S <= 0 -> ritira ogni ordine vivo, `IDLE_LIVE`, «nessuna posizione Under».
- **Numeri**: vedi scheda 37.
- **Esempio**: PERSIST mai abbinato e ingressi archiviati -> `IDLE_LIVE`.
- **Cosa vede l'utente**: il motivo.
- **Dove**: `engine.py:3003-3011`.
- **Paper o live**: identico.

### 27. Uscita al fischio: strada A (abbinata) e strada C (gol precoce)
- **Cosa fa**: A) se la lay d'uscita si e' abbinata, blocca il profitto senza copertura; C) se arriva un gol mentre si e'
  ancora scoperti, annulla l'uscita e passa alla seconda puntata.
- **Quando scatta**: casella `LIVE_KO_GREEN`, S > 0. A viene controllata prima di C.
- **Cosa succede dopo**:
  - **A, abbinata per intero** (ultima `ko_green` con abbinato > 0, non piu' viva, e nessuna selezione aperta): casella
    `FLAT`, motivo di chiusura «profit», **re-ingresso permesso**, tentativi 0, «uscita al fischio: +X» (profitto netto
    commissione, `locked_pnl`);
  - **A, abbinata solo in parte** (e ormai non piu' viva): `LIVE_UNCOVERED` con copertura ordinata, «uscita al fischio
    parziale: copro il residuo» (la copertura si calcola sul netto residuo);
  - **C, gol dopo il fischio**: ritira la `ko_green` viva; `early_goal_at` = momento del gol (scheda 23). Seconda puntata
    accesa (`second_entry_enabled`) e non ancora fatta -> `LIVE_SECOND_ENTRY`, «gol precoce: seconda puntata
    sull'Under 3.5»; altrimenti -> `LIVE_UNCOVERED` con copertura ordinata, «gol precoce: copertura Over 4.5».
- **Numeri**: `second_entry_enabled` True.
- **Esempio A**: lay 10,14 @ 1,48 abbinata al 2' -> vince 5 - 10,14x0,48 = +0,13, perde -10+10,14 = +0,14; netto circa
  +0,12 / +0,13 -> «uscita al fischio: +0.13» (commissione 5 % sul netto positivo).
  **Esempio C**: 1-0 al 2', uscita non abbinata -> ritirata, seconda puntata.
- **Cosa vede l'utente**: i motivi; telemetria `ko_green` con esito «abbinata» o «gol».
- **Dove**: `engine.py:3019-3035` (A), `3037-3050` (C).
- **Paper o live**: identico.

### 28. Uscita al fischio: strada B (finestra scaduta)
- **Cosa fa**: se passano 3 minuti di gioco senza gol e senza abbinamento, annulla l'uscita e passa alla copertura
  piena sull'Over 4,5.
- **Quando scatta**: casella `LIVE_KO_GREEN`, S > 0, niente A ne' C, finestra scaduta (scheda 24).
- **Cosa succede dopo**: ritira la `ko_green` viva; `LIVE_UNCOVERED` con copertura ordinata, «uscita non abbinata in 3':
  copertura Over 4.5».
- **Numeri**: `ko_green_window_s` 180 s.
- **Esempio**: gioco dalle 21:00:40, alle 21:03:40 lay ancora non abbinata -> copertura.
- **Cosa vede l'utente**: motivo e telemetria `ko_green` esito «scaduta».
- **Dove**: `engine.py:3052-3060`.
- **Paper o live**: identico.

### 29. Uscita al fischio: il mercato non permette di appoggiare
- **Cosa fa**: prima di appoggiare la lay d'uscita guarda lo stato del mercato Under 3,5: la lay si appoggia solo a
  mercato APERTO e GIA' IN GIOCO (prima Betfair la cancellerebbe al passaggio in gioco).
- **Quando scatta**: casella `LIVE_KO_GREEN`, dopo i controlli A/C/B.
- **Cosa succede dopo**: aperto ma non ancora in gioco -> resta, «mercato aperto ma non ancora in gioco: aspetto»;
  sospeso o ignoto -> resta, «mercato sospeso: aspetto la riapertura per uscire»; chiuso -> `LIVE_UNCOVERED` con
  copertura ordinata, «mercato chiuso: l'uscita al fischio non e' piu' possibile».
- **Numeri**: nessuno.
- **Esempio**: 21:00:05 mercato sospeso per il fischio -> aspetta.
- **Cosa vede l'utente**: i motivi.
- **Dove**: `engine.py:3074-3087`.
- **Paper o live**: identico.

### 30. Uscita al fischio: si appoggia (o si aspetta) la lay
- **Cosa fa**: appoggia UNA lay d'uscita 2 tick sotto il prezzo medio e la lascia sul book; non la rifa' a ritmo.
- **Quando scatta**: casella `LIVE_KO_GREEN`, mercato aperto e in gioco.
- **Cosa succede dopo** (nell'ordine):
  1. piano non calcolabile (scheda 25) -> `LIVE_UNCOVERED` con copertura ordinata, «uscita al fischio non calcolabile»;
  2. una lay sull'Under 3,5 a esito ignoto -> aspetta, «uscita ... a esito ignoto: aspetto la riconciliazione»;
  3. una lay viva di un altro ruolo (es. la green pre-partita non ancora confermata annullata) -> aspetta, «attendo
     l'annullamento della lay precedente»;
  4. la `ko_green` e' viva con stessa quota e stesso importo del piano -> niente, «uscita a +2 tick sul book»;
  5. la `ko_green` e' viva ma quota o importo sono cambiati (es. si e' abbinato il residuo PERSIST e la media e' cambiata)
     -> la ritira (la nuova arriva al giro dopo);
  6. richiesta identica gia' rifiutata dal mercato -> non la ripete;
  7. altrimenti: LAY, Over/Under 3,5, Under, quota = prezzo medio - 2 tick, importo = esposizione netta / quota, ruolo
     `ko_green`, tipo LAPSE nell'ordine ma trattata come «appoggiata» dal servizio, nota «uscita al fischio: 2 tick sotto
     1.50». Resta `LIVE_KO_GREEN`, «uscita appoggiata a 1.48», telemetria con i secondi che restano della finestra.
- **Numeri**: `ko_green_ticks` 2; `ko_green_window_s` 180. `ko_green_retry_s` (5 s) NON e' letto da nessun ramo.
- **Esempio**: posizione 10 @ 1,50 -> lay 10,14 @ 1,48; alle 21:01:10 «scade fra 150 s».
- **Cosa vede l'utente**: motivi; con le uscite manuali (default) l'uscita e' una proposta, e l'orologio della finestra
  continua a correre.
- **Dove**: `engine.py:3089-3157` (1: 3090-3093; 2: 3106-3114; 3: 3115-3118; 4: 3119-3124; 5: 3125-3127; 6: 3143-3149;
  7: 3150-3157).
- **Paper o live**: la lay e' appoggiata in entrambi (per il servizio `ko_green` e' sempre «resting»,
  `service._is_resting_leg`, area C). L'engine non distingue.

### 31. (Scheda di raccordo) Cosa NON fa l'uscita al fischio
- **Cosa fa**: elenca i casi che il codice non prevede, per completezza.
- **Quando scatta**: sempre in `LIVE_KO_GREEN`.
- **Cosa succede dopo**: non c'e' uscita in perdita, non c'e' cash out, non c'e' copertura finche' non scatta A/B/C o il
  mercato chiude. Se l'uscita e' stata abbinata IN PARTE e poi cancellata da Betfair (sospensione per gol), il codice va
  alla copertura del residuo (strada A parziale) senza riappoggiare il residuo anche se la finestra e' ancora aperta.
- **Numeri**: -
- **Esempio**: lay 10,14 abbinata per 4 EUR, poi gol: prima di C scatta A-parziale -> copertura, niente seconda puntata.
- **Cosa vede l'utente**: «uscita al fischio parziale: copro il residuo».
- **Dove**: `engine.py:3020-3035` (A prima di C).
- **Paper o live**: identico.

### 32. La seconda puntata dopo un gol precoce
- **Cosa fa**: dopo un gol nei primi minuti punta di nuovo l'Under 3,5 con meta' stake al miglior prezzo (la quota e'
  salita, la media migliora). Non deve mai ritardare la copertura: passati 2 minuti dal gol si copre comunque.
- **Quando scatta**: casella `LIVE_SECOND_ENTRY`.
- **Cosa succede dopo** (nell'ordine; «tempo scaduto» = adesso - momento del gol >= `early_goal_cover_delay_s` 120 s):
  1. S <= 0 -> ritira tutto, `IDLE_LIVE`;
  2. (sempre) ritira il residuo PERSIST scaduto (scheda 37);
  3. seconda puntata abbinata (anche in parte) e non piu' viva -> `LIVE_UNCOVERED`, seconda puntata fatta, copertura a
     tranche (`cover_stage` 1), ordinata, tentativi 0, «seconda puntata abbinata a Q (media M su S EUR)»;
  4. seconda puntata viva e tempo scaduto -> la ritira; `LIVE_UNCOVERED`, `cover_stage` 0 (copertura piena in una
     volta), «seconda puntata non abbinata in tempo: copertura piena»;
  5. seconda puntata viva e tempo non scaduto -> resta, «seconda puntata sul book»;
  6. nessun ordine vivo e tempo scaduto -> `LIVE_UNCOVERED`, copertura piena, «non piazzabile»;
  7. tentativi >= `close_max_attempts` (20) -> `LIVE_UNCOVERED`, copertura piena, «tentativi esauriti»;
  8. book assente, quota non valida o mercato non aperto -> resta, «seconda puntata: mercato sospeso/...»;
  9. importo = stake x `second_entry_stake_pct` / 100; se < 0,01 EUR -> copertura piena, «importo nullo»;
  10. importo > spazio sotto il tetto per partita -> copertura piena, «cap liability partita»;
  11. liquidita' al miglior back < importo -> resta, «seconda puntata: liquidita X < Y»;
  12. altrimenti: BACK, Over/Under 3,5, Under, quota = miglior back, importo come al punto 9, ruolo `under_second`, cade
      alla sospensione (LAPSE), nota «seconda puntata dopo gol precoce»; tentativi +1; resta `LIVE_SECOND_ENTRY`.
- **Numeri**: `second_entry_stake_pct` 50 % (0-200); `early_goal_cover_delay_s` 120 s (0-900); `close_max_attempts` 20;
  `stake` 10.
- **Esempio** (Costituzione §15.3): 10 EUR @ 1,50 + 5 EUR @ 1,95 = 15 EUR a media 1,65; vincendo +9,75 invece di +5,00.
- **Cosa vede l'utente**: i motivi; telemetria `second_entry` (piazzata / abbinata).
- **Dove**: `engine.py:3160-3225` (1: 3167-3168; 2: 3169; 3: 3174-3184; 4: 3186-3193; 5: 3194; 6: 3198-3200;
  7: 3201-3203; 8: 3204-3207; 9: 3208-3211; 10: 3212-3214; 11: 3215-3217; 12: 3218-3225).
- **Paper o live**: identico. Nessun controllo di banda di quota e nessun controllo «richiesta gia' rifiutata» qui.

### 33. Quanto manca alla prima tranche di copertura
- **Cosa fa**: dopo un gol precoce, conta i secondi che mancano ai 2 minuti di attesa prima di comprare la prima tranche.
- **Quando scatta**: dentro la scheda 35 con `cover_stage` = 1.
- **Cosa succede dopo**: niente attesa se il momento del gol non e' noto o se il tempo e' passato; altrimenti i secondi
  mancanti (arrotondati a 0,1).
- **Numeri**: `early_goal_cover_delay_s` 120 s.
- **Esempio**: gol alle 21:05:00, adesso 21:06:10 -> mancano 50 s.
- **Cosa vede l'utente**: «prima tranche fra 50 s (attesa dal gol)».
- **Dove**: `engine.py:3228-3237`.
- **Paper o live**: identico.

### 34. Quale frazione della copertura comprare adesso
- **Cosa fa**: decide se comprare tutta la copertura o solo la prima meta' (dopo un gol precoce).
- **Quando scatta**: dentro le schede 35 e 38.
- **Cosa succede dopo**: se `cover_stage` non e' 1 -> tutta (100 %). Se e' 1: frazione = `early_goal_cover_pct`
  (limitata fra 0 e 100 %); 0 % o 100 % -> tutta. Con importi esatti (default) basta che la tranche sia >= 0,01 EUR; con
  importi esatti spenti la tranche deve arrivare da sola al minimo italiano di 2,00 EUR, altrimenti si copre tutto in
  una volta («split declassato»).
- **Numeri**: `early_goal_cover_pct` 50 % (0-100); `exact_sizes` True; minimo 0,01 EUR (costante `SUBMIN_FLOOR`) o 2,00
  EUR (costante `IT_BACK_MIN`).
- **Esempio**: copertura piena 2,71 EUR, fase 1 -> compra 1,35 EUR. Importi esatti spenti e copertura piena 3,00 -> 1,50 < 2,00:
  compra tutto (3,00) in una volta.
- **Cosa vede l'utente**: «copertura Over 4.5 in una volta (la tranche sarebbe sotto il minimo)» se declassato.
- **Dove**: `engine.py:3240-3270`.
- **Paper o live**: identico.

### 35. La copertura sull'Over 4,5: quando e se comprarla
- **Cosa fa**: decide se comprare adesso la protezione sull'Over 4,5 (5+ gol), aspettare, o non comprarla.
- **Quando scatta**: casella `LIVE_UNCOVERED`.
- **Cosa succede dopo** (nell'ordine):
  1. S <= 0 -> ritira tutto, `IDLE_LIVE`; poi (sempre) ritira il PERSIST scaduto (scheda 37);
  2. fase tranche 1 o 2 senza momento del gol (riavvio) -> si copre in una volta (fase 0);
  3. copertura spenta (`cover_enabled` = False) -> `LIVE_COVERED`, «copertura disabilitata»;
  4. fase 1 e mancano secondi all'attesa dal gol -> resta, «prima tranche fra N s»;
  5. calcoli: rischio Under = perdita netta se l'Under perde; gia' coperto = netto con 5+ gol delle coperture gia'
     abbinate; quota Over = miglior back Over 4,5; quota limite = quota Over - `cover_place_at_ticks` (2 tick);
     decisione di tempo (`cover_timing`, area A): «skip» se gol > `cover_max_goals` (2), «wait» nei 45 s dopo un gol,
     altrimenti con copertura ordinata «cover» (l'attesa «intelligente» vale solo senza copertura ordinata);
     copertura piena = (1,2 x rischio - gia' coperto) / ((quota Over - 1) x (1 - 5 %)); frazione dalla scheda 34;
  6. «skip» (3+ gol) -> `LIVE_COVERED`, «copertura saltata: troppi gol»;
  7. rischio Under <= 0 -> `LIVE_COVERED`, «nessuna liability Under da coprire»;
  8. mercato Over 4,5 non aperto -> resta, «copertura: mercato Over 4.5 sospeso, si aspetta la riapertura»;
  9. «wait» o quota Over assente -> resta, «attendo per coprire»;
  10. importo da comprare < 0,01 -> `LIVE_COVERED`, «copertura gia' sufficiente»;
  11-14: scheda 36.
- **Numeri**: `cover_enabled` True; `cover_profit_factor` 1,2 (1-3); `commission_pct` 5 %; `cover_place_at_ticks` 2
  (0-6); `cover_max_goals` 2 (0-4); `cover_postgoal_delay_s` 45 s (0-300); `cover_policy` «auto»; attesa intelligente
  (solo senza copertura ordinata): `cover_wait_max_min` 10, `cover_wait_hazard_max` 0,06, `cover_wait_p4_max` 0,16,
  `cover_good_price` 7,0, `cover_wait_min_gain_pct` 8 %.
- **Esempio** (Costituzione §3 Fase 3): rischio 10 EUR, Over 6,6 -> 12 / (5,6 x 0,95) = 2,26 EUR; limite 2 tick sotto 6,6
  = 6,2.
- **Cosa vede l'utente**: i motivi; telemetria `cover_wait` / `cover_staged`.
- **Dove**: `engine.py:3273-3365` (1: 3274-3277; 2: 3282-3283; 3: 3284-3286; 4: 3287-3293; 5: 3299-3339;
  6: 3340-3342; 7: 3343-3345; 8: 3353-3359; 9: 3360-3365; 10: 3366-3368).
- **Paper o live**: identico.

### 36. La copertura sull'Over 4,5: l'ordine
- **Cosa fa**: dimensiona e piazza la puntata sull'Over 4,5.
- **Quando scatta**: seguito della scheda 35, quando la copertura va comprata.
- **Cosa succede dopo**:
  11. importo: con importi esatti = importo calcolato al centesimo; con importi esatti spenti = arrotondato al passo .it
      (min 2,00, passo 0,50) e se il sovrappiu' supera `cover_max_overshoot_pct` (30 %) si arrotonda per difetto; se
      anche cosi' supera -> resta, «copertura: overshoot X% oltre il tetto 30%»;
  12. spazio sotto il tetto per partita < 0,01 -> `LIVE_COVERED`, «copertura saltata: cap liability partita»; se
      l'importo supera lo spazio viene tagliato allo spazio;
  13. liquidita' al miglior back Over < importo -> resta, «copertura: liquidita X < Y»; importo < 0,01 -> resta,
      «copertura: size non piazzabile»;
  14. altrimenti: BACK, Over/Under 4,5, Over, quota = quota limite (2 tick sotto il miglior back; se non calcolabile il
      miglior back), importo come sopra, ruolo `over_cover`, LAPSE. Casella `LIVE_COVER_PENDING`, con la fase
      (`cover_stage`) aggiornata. Etichetta: «copertura Over 4.5: prima tranche» (fase 1), «... seconda tranche
      (residuo)» (fase 3), «... in una volta (la tranche sarebbe sotto il minimo)» (declassato), altrimenti «copertura
      Over 4.5».
- **Numeri**: `exact_sizes` True; `cover_rounding` «ceil»; `cover_max_overshoot_pct` 30 %; `max_liability_per_match` 0.
- **Esempio**: 2,26 EUR back Over 4,5 @ limite 6,2 (si abbina al miglior prezzo disponibile, 6,6). Con 5+ gol: +2,26 x 5,6
  x 0,95 = +12,02 = 1,2 x 10 (l'Under perde 10: netto +2,02, cioe' +20 % di S). Con 0-3 gol: +5 - 2,26 = +2,74 (lordo
  Under). Con 4 gol: -10 - 2,26 = -12,26.
- **Cosa vede l'utente**: etichetta; telemetria `cover` (x, size, prezzo, rischio, gia' coperto, fase, frazione).
- **Dove**: `engine.py:3369-3412` (11: 3369-3382; 12: 3383-3388; 13: 3389-3397; 14: 3398-3412).
- **Paper o live**: identico nell'engine; sotto i 2 EUR in live il servizio usa il «place-and-trim» (area C).

### 37. Ritiro del residuo PERSIST dopo il fischio
- **Cosa fa**: ritira la parte non abbinata dell'ultimo ingresso PERSIST passati 2 minuti dal fischio di calendario.
- **Quando scatta**: all'inizio di `LIVE_KO_GREEN`, `LIVE_SECOND_ENTRY`, `LIVE_UNCOVERED`, `LIVE_COVERED`.
- **Cosa succede dopo**: per ogni `under_last` ancora vivo con adesso - fischio di calendario >= 120 s: ordine di ritiro.
- **Numeri**: `cancel_unmatched_after_ko_s` 120 s.
- **Esempio**: fischio 21:00; alle 21:02:00 il PERSIST ha abbinato 6 EUR su 10 -> ritira i 4 EUR restanti.
- **Cosa vede l'utente**: il ritiro nella scheda Trade.
- **Dove**: `engine.py:3415-3422`.
- **Paper o live**: identico. NON e' chiamato in `IDLE_LIVE`, `LIVE_COVER_PENDING`, `LIVE_CLOSING`, `FLAT` (vedi Cose strane n. 1).

### 38. Copertura sul book: attesa, abbinamento, riprezzo
- **Cosa fa**: segue la puntata di copertura.
- **Quando scatta**: casella `LIVE_COVER_PENDING`.
- **Cosa succede dopo** (nell'ordine):
  1. nessuna gamba `over_cover` -> `LIVE_UNCOVERED`, «gamba copertura assente»;
  2. non viva e non abbinata per intero (ritirata con 0 o con parte abbinata) -> `LIVE_UNCOVERED`, tentativi +1,
     «copertura non completata: ridimensiono sulla copertura reale gia' abbinata»;
  3. abbinata per intero: se era la prima tranche -> fase 2, `cover_stage1_at` = adesso, `LIVE_COVERED`, «prima tranche
     di copertura abbinata»; altrimenti fase 0, `LIVE_COVERED`, «copertura abbinata». Copertura ordinata spenta,
     tentativi 0;
  4. viva da >= `close_retry_s` (10 s) e tentativi < 20: se il mercato Over 4,5 non e' aperto -> niente riprezzo; se c'e'
     quota: ricalcola la copertura residua sul miglior back attuale (stessa frazione in prima tranche); se < 0,01 ->
     ritira e `LIVE_COVERED`, «copertura sufficiente»; altrimenti ritira e rimanda BACK Over 4,5 al limite 2 tick sotto il
     miglior back, tentativi +1, «copertura: riprezzo» (la nuova parte al giro dopo, regola «mai sovracopertura»);
  5. altrimenti «attesa fill copertura».
- **Numeri**: `close_retry_s` 10; `close_max_attempts` 20; `cover_place_at_ticks` 2; `cover_profit_factor` 1,2.
- **Esempio**: copertura 2,26 @ 6,2 non abbinata in 10 s, Over sceso a 6,0 -> residuo 12/(5 x 0,95) = 2,53 EUR al limite 5,8
  (2 tick da 0,10 sotto 6,0).
- **Cosa vede l'utente**: i motivi.
- **Dove**: `engine.py:3425-3498` (1: 3427-3428; 2: 3429-3445; 3: 3446-3456; 4: 3457-3497; 5: 3498).
- **Paper o live**: identico.

---

## POSIZIONE COPERTA: USCITE GLOBALI

### 39. Quale regola di perdita tollerata vale adesso
- **Cosa fa**: dice se siamo in una finestra in cui e' permesso chiudere in perdita, e con quale percentuale.
- **Quando scatta**: dentro la scheda 42.
- **Cosa succede dopo**: intervallo in corso e `ht_loss_exit_enabled` -> (25 %, «ht»); altrimenti minuto noto fra
  `h2_loss_from_min` (46) e `h2_loss_to_min` (85) compresi e `h2_loss_exit_enabled` -> (25 %, «2t»); altrimenti nessuna.
- **Numeri**: `ht_loss_pct` 25 %; `h2_loss_pct` 25 %; `h2_loss_from_min` 46; `h2_loss_to_min` 85; entrambe accese.
- **Esempio**: intervallo -> 25 % «ht»; 60' -> 25 % «2t»; 30' o 88' -> nessuna.
- **Cosa vede l'utente**: niente direttamente.
- **Dove**: `engine.py:3501-3508`.
- **Paper o live**: identico.

### 40. Posizione coperta: niente esposizione o prezzi incompleti
- **Cosa fa**: controlla che ci sia qualcosa da gestire e che i prezzi bastino a calcolare «se chiudo ora».
- **Quando scatta**: casella `LIVE_COVERED`.
- **Cosa succede dopo**: nessuna selezione aperta ancora in gioco -> `FLAT`, «nessuna esposizione gestibile» (senza
  cambiare il permesso di re-ingresso). Poi ritira il PERSIST scaduto (scheda 37) e calcola il valore di cash out
  netto commissione (`cashout_value`, area A) e la base = capitale investito (tutte le puntate back ancora a rischio:
  Under + Over + re-ingresso). Se manca un prezzo -> resta, «prezzi incompleti».
- **Numeri**: `cashout_base` «total»; `cashout_place_at_ticks` 0.
- **Esempio**: Under 10 + Over 2,26 -> base 12,26.
- **Cosa vede l'utente**: telemetria `cashout` (netto, lordo, per selezione, %).
- **Dove**: `engine.py:3512-3526`.
- **Paper o live**: identico.

### 41. Cash out a profitto (soglia fissa e cash out intelligente)
- **Cosa fa**: chiude tutto se il profitto netto bloccabile e' almeno il 5 % della base; oppure prima, col cash out
  intelligente, quando tenere non vale il rischio.
- **Quando scatta**: casella `LIVE_COVERED`, prezzi completi.
- **Cosa succede dopo**: soglia fissa: netto >= 5 % della base -> ordini di chiusura su ogni selezione aperta
  (`_close_actions`, area A: LAY al miglior prezzo per Under 3,5 = ruolo `under_close`, per Over 4,5 = `over_close`,
  per Under 4,5 = `reentry_green`; prima ritira gli altri ordini vivi sulla stessa selezione), `LIVE_CLOSING`, motivo di
  chiusura «profit», «profit: X >= 5% di B». Altrimenti cash out intelligente (area A, `smart_cashout`): mai sotto il 2 %
  della base; 3+ gol; o entro 2 punti dalla soglia con hazard >= 10 % o pressione >= 1,15; o valore atteso dell'attesa
  inferiore -> stessa chiusura, «profit smart: X (motivo)».
- **Numeri**: `cashout_profit_pct` 5 %; `cashout_smart_enabled` True; `cashout_smart_min_pct` 2 %;
  `cashout_smart_tolerance_pct` 2 %; `cashout_smart_hazard_hot` 0,10; `cashout_smart_pressure_hot` 1,15;
  `cashout_smart_goals_hot` 3; `cashout_smart_ev_margin_pct` 1 %.
- **Esempio** (Costituzione Fase 4): base 12,26, soglia 0,61; al 40' 0-0 netto +0,75 -> chiude.
- **Cosa vede l'utente**: motivo; con le uscite manuali (default) e' una proposta.
- **Dove**: `engine.py:3527-3539`.
- **Paper o live**: identico.

### 42. Uscita in perdita all'intervallo e nel secondo tempo
- **Cosa fa**: nelle finestre della scheda 39, con 3 o 4 gol, confronta «chiudo adesso» con «tengo fino alla fine» e
  chiude se conviene; senza dati di modello usa la regola fissa «perdita entro il 25 % della base».
- **Quando scatta**: casella `LIVE_COVERED`, nessun cash out a profitto, regola di perdita attiva.
- **Cosa succede dopo**: gol fra `ht_loss_goals_min` (3) e `ht_loss_goals_max` (4) (valgono anche per il 2° tempo).
  Modo «model»: `loss_exit_model` (area A); se decide di chiudere -> chiusura (`LIVE_CLOSING`, motivo «loss_ht» o
  «loss_2t»), «uscita a modello (ht): ...». Se il modello non ha dati (o modo «fixed"): netto >= -25 % della base -> stessa
  chiusura, «loss tollerata (ht): X entro 25% di B». Se il modello decide di tenere, la regola fissa NON si applica.
- **Numeri**: `loss_exit_mode` «model»; `loss_exit_risk_premium_pct` 10 %; `loss_exit_p4_prudent` True;
  `loss_exit_max_pct` 0; `ht_loss_goals_min` 3; `ht_loss_goals_max` 4; percentuali scheda 39.
- **Esempio**: HT 2-1, base 12,26, modello assente, netto -2,50 (20 %) -> chiude («loss tollerata»).
- **Cosa vede l'utente**: motivo; attivita' `loss_exit_deciso`; con le uscite manuali e' una proposta urgente.
- **Dove**: `engine.py:3540-3578`.
- **Paper o live**: identico.

### 43. Cap di perdita per partita
- **Cosa fa**: chiude tutto se la perdita bloccabile raggiunge la percentuale massima della base.
- **Quando scatta**: casella `LIVE_COVERED`, nessuna uscita precedente, `event_loss_cap_pct` > 0, base > 0, netto <=
  -base x cap / 100.
- **Cosa succede dopo**: chiusura (`LIVE_CLOSING`, motivo «loss_cap»), «cap perdita evento: X». Sempre automatica anche
  con le uscite manuali.
- **Numeri**: `event_loss_cap_pct` 100 % (0-500).
- **Esempio**: base 12,26 -> chiude solo se il netto bloccabile e' <= -12,26.
- **Cosa vede l'utente**: il motivo.
- **Dove**: `engine.py:3579-3583`.
- **Paper o live**: identico.

### 44. Seconda tranche di copertura (o «tengo»)
- **Cosa fa**: se nessuna uscita globale scatta e si e' in attesa della seconda tranche, dopo 3 minuti dalla prima torna
  a coprire il residuo; altrimenti tiene.
- **Quando scatta**: casella `LIVE_COVERED`, nessuna uscita, `cover_stage` = 2.
- **Cosa succede dopo**: se l'ora della prima tranche manca, o sono passati >= `early_goal_cover2_delay_s` (180 s) ->
  `LIVE_UNCOVERED`, fase 3, copertura ordinata, «seconda tranche: completo la copertura». Altrimenti `LIVE_COVERED`,
  «tengo».
- **Numeri**: `early_goal_cover2_delay_s` 180 s (0-900).
- **Esempio** (Costituzione §15.3): prima tranche 1,35 EUR @ 8,00 alle 21:07; alle 21:10 Over a 5,00 -> seconda tranche 2,37 EUR.
- **Cosa vede l'utente**: motivo; telemetria `cover_staged`.
- **Dove**: `engine.py:3593-3603`.
- **Paper o live**: identico.

### 45. La chiusura in corso
- **Cosa fa**: segue gli ordini di chiusura (cash out / uscite): ritira quelli su selezioni gia' decise, riprezza quelli
  fermi, ripete la chiusura del residuo, e quando e' tutto chiuso passa a `FLAT`.
- **Quando scatta**: casella `LIVE_CLOSING`.
- **Cosa succede dopo** (nell'ordine; «chiusure in attesa» = ordini vivi di ruolo `under_close`, `over_close`, `manual_close`):
  1. chiusure in attesa su una selezione il cui esito e' gia' deciso dai gol -> le ritira, «chiusura su selezione gia'
     decisa: annullo»;
  2. nessuna chiusura in attesa: se resta esposizione ancora in gioco e tentativi < 20 -> rimanda le chiusure del
     residuo (tentativi +1, «chiusura residuo»); altrimenti `FLAT` («chiuso (motivo)»), re-ingresso permesso SOLO se il
     motivo era «profit», tentativi 0;
  3. tentativi >= 20 -> resta, «chiusura: tentativi esauriti» (telemetria `close_retries_exhausted`);
  4. per ogni chiusura ferma da >= 10 s con book: ritira e rimanda al miglior prezzo per il residuo netto, tentativi +1,
     «chiusura: riprezzo»;
  5. altrimenti «attesa fill chiusura».
- **Numeri**: `close_retry_s` 10; `close_max_attempts` 20; `cashout_place_at_ticks` 0.
- **Esempio**: lay di chiusura Under 3,5 ferma 10 s -> ritirata e rimessa al nuovo miglior lay.
- **Cosa vede l'utente**: i motivi.
- **Dove**: `engine.py:3606-3651` (1: 3610-3615; 2: 3616-3626; 3: 3628-3632; 4: 3633-3650; 5: 3651).
- **Paper o live**: identico.

### 46. Residuo troppo piccolo per essere chiuso
- **Cosa fa**: dice se l'esposizione rimasta e' cosi' piccola che nessun ordine puo' chiuderla.
- **Quando scatta**: dentro la scheda 47.
- **Cosa succede dopo**: se il calcolo del cash out va in errore -> «no»; se non c'e' nessun piano eseguibile -> «no»;
  «si'» solo se TUTTI i piani eseguibili hanno importo < 0,01 EUR.
- **Numeri**: 0,01 EUR (`size_chiudibile`, 1717).
- **Esempio**: residuo che richiederebbe una lay da 0,004 EUR -> non chiudibile, va al regolamento.
- **Cosa vede l'utente**: «residuo sotto il minimo Betfair: si porta al regolamento».
- **Dove**: `engine.py:3654-3674`.
- **Paper o live**: identico.

### 47. FLAT: posizione chiusa, eventuale re-ingresso sull'Under 4,5
- **Cosa fa**: a posizione chiusa controlla che non resti esposizione e, se la chiusura precedente era in profitto e c'e'
  stato esattamente 1 gol nel primo tempo, punta l'Under 4,5.
- **Quando scatta**: casella `FLAT`.
- **Cosa succede dopo** (nell'ordine):
  1. esposizione ancora in gioco: residuo non chiudibile -> resta `FLAT`, «residuo sotto il minimo Betfair»; altrimenti
     -> `LIVE_COVERED`, «esposizione residua»;
  2. chiusa a mano dall'utente (`no_reentry`) -> `FLAT`, «rientro disabilitato (chiusura manuale)»;
  3. re-ingresso spento, o non permesso (chiusura non in profitto), o gia' fatto -> `FLAT`;
  4. dati non freschi per un ordine, o gol/minuto sconosciuti -> `FLAT`, «dati feed mancanti»;
  5. gol < 1 o > `reentry_max_goals` (1) -> `FLAT`, «N gol fuori range re-ingresso»;
  6. minuto > `reentry_until_min` (45) -> `FLAT`, «oltre il minuto di re-ingresso»;
  7. book Under 4,5 assente o non aperto -> `FLAT`;
  8. `reentry_price_min_over_entry` acceso e quota back Under 4,5 <= prezzo del PRIMO ingresso della partita -> `FLAT`;
  9. liquidita' < 10 EUR -> `FLAT`, «liquidita re-ingresso»;
  10. tetto per partita -> `FLAT`;
  11. altrimenti: BACK, Over/Under 4,5, Under, quota = miglior back, importo = stake (10 EUR), ruolo `reentry`, LAPSE.
      Casella `REENTRY_PENDING`, «re-ingresso Under 4.5».
- **Numeri**: `reentry_enabled` True; `reentry_max_goals` 1 (0-1); `reentry_until_min` 45; `reentry_price_min_over_entry`
  True; `pre_min_back_size_factor` 1,0; `stake` 10.
- **Esempio**: uscita al fischio abbinata (profit), 1-0 al 30', Under 4,5 a 1,70 > 1,50 -> back 10 EUR @ 1,70 Under 4,5.
- **Cosa vede l'utente**: i motivi.
- **Dove**: `engine.py:3677-3708` (1: 3678-3683; 2: 3684-3685; 3: 3686-3687; 4: 3688-3689; 5: 3690-3692; 6: 3693-3694;
  7: 3695-3697; 8: 3698-3700; 9: 3701-3703; 10: 3704-3705; 11: 3706-3708).
- **Paper o live**: identico. A bot fermo il servizio spegne `reentry_enabled` (`service.py:1274`).

### 48. Re-ingresso: attesa dell'abbinamento
- **Cosa fa**: segue la puntata Under 4,5; quando e' abbinata appoggia la lay di green 2 tick sotto.
- **Quando scatta**: casella `REENTRY_PENDING`.
- **Cosa succede dopo**: gamba assente -> `FLAT`; non viva e niente abbinato -> `FLAT`, re-ingresso fatto; abbinata:
  mercato Under 4,5 non aperto -> aspetta; altrimenti LAY Over/Under 4,5 Under, quota = prezzo abbinato - 2 tick,
  importo = esposizione netta / quota, ruolo `reentry_green`, LAPSE; casella `REENTRY_OPEN`, «re-ingresso abbinato»;
  viva da >= 60 s: con parte abbinata -> ritira il residuo, `REENTRY_OPEN`; senza -> ritira, `FLAT`, re-ingresso fatto;
  altrimenti «attesa fill re-ingresso».
- **Numeri**: `reentry_green_ticks` 2; `pre_entry_ttl_s` 60 s.
- **Esempio**: back 10 @ 1,70 abbinato -> lay 17/1,68 = 10,12 EUR @ 1,68 (profitto +0,12 lordi).
- **Cosa vede l'utente**: i motivi.
- **Dove**: `engine.py:3711-3740`.
- **Paper o live**: identico (in live con `live_resting_enabled` spento la green del re-ingresso segue il ramo taker del
  servizio, area C).

### 49. Re-ingresso aperto: la green resta sul book
- **Cosa fa**: tiene sul book la lay di green del re-ingresso fino a fine gara; se sparisce la rimette.
- **Quando scatta**: casella `REENTRY_OPEN`.
- **Cosa succede dopo**: esposizione piatta -> ritira la green viva, `FLAT`, re-ingresso fatto, «re-ingresso chiuso».
  Se `reentry_exit_until_min` > 0 e il minuto e' raggiunto: con `reentry_hold_if_loss` resta; altrimenti ritira la green
  e chiude al miglior prezzo (`REENTRY_GREEN_PENDING`, motivo «reentry_time»). Green assente o non viva: mercato non
  aperto -> aspetta; altrimenti LAY Under 4,5 a prezzo medio - 2 tick per l'esposizione netta (salvo richiesta identica
  gia' rifiutata), «green re-ingresso appoggiata». Altrimenti «re-ingresso aperto, green sul book».
- **Numeri**: `reentry_exit_until_min` 0 (= mai chiusura forzata); `reentry_hold_if_loss` False; `reentry_green_ticks` 2.
- **Esempio**: green 10,12 @ 1,68 ritirata da Betfair alla sospensione per un gol -> rimessa al giro dopo la riapertura.
- **Cosa vede l'utente**: i motivi.
- **Dove**: `engine.py:3743-3787`.
- **Paper o live**: identico.

### 50. Chiusura a tempo del re-ingresso in corso
- **Cosa fa**: segue la chiusura al mercato del re-ingresso (solo se `reentry_exit_until_min` > 0).
- **Quando scatta**: casella `REENTRY_GREEN_PENDING`.
- **Cosa succede dopo**: esposizione piatta o green abbinata (anche in parte e ritirata) -> `FLAT`, re-ingresso fatto;
  green morta senza abbinamento -> `REENTRY_OPEN`; green viva da >= 10 s, tentativi < 20, book aperto con lay -> ritira e
  rimanda al miglior prezzo, tentativi +1; altrimenti «attesa fill chiusura re-ingresso».
- **Numeri**: `close_retry_s` 10; `close_max_attempts` 20.
- **Esempio**: con `reentry_exit_until_min` = 70, al 70' lay al miglior lay; non abbinata in 10 s -> riprezzo.
- **Cosa vede l'utente**: i motivi.
- **Dove**: `engine.py:3790-3808`.
- **Paper o live**: identico. Con il default 0 questa casella non si raggiunge mai.

### 51. Applicare la decisione alla partita
- **Cosa fa**: scrive sulla partita cio' che la decisione ha stabilito: nuovi valori, archiviazione del ciclo, nuova
  casella, e crea le gambe «in attesa» per ogni ordine da piazzare.
- **Quando scatta**: dopo ogni decisione (lo chiama il servizio).
- **Cosa succede dopo**: copia ogni aggiornamento; se c'e' l'ordine di archiviare, archivia tutte le gambe tranne quelle
  ancora vive o a esito ignoto, e cancella dalla memoria dei rifiuti tutto cio' che non e' del ciclo attuale; imposta la
  casella; per ogni ordine da piazzare crea una gamba (codice `ruolo-ciclo-progressivo`, stato «in attesa», ora di
  piazzamento, persistenza, ciclo, «finale»); per le chiusure scrive quale apertura chiudono. I ritiri NON cambiano le
  gambe (lo fa il servizio quando Betfair conferma). Se c'e' almeno un'azione aggiorna `last_action_at`.
- **Numeri**: nessuno.
- **Esempio**: decisione dell'ultimo ingresso con ciclo +1 = 3 -> archiviate le gambe dei cicli chiusi, nuova gamba
  `under_last-3-17` PERSIST.
- **Cosa vede l'utente**: le nuove righe d'ordine.
- **Dove**: `engine.py:3814-3869` (aggiornamenti 3822-3826; archiviazione 3827-3849; gambe nuove 3851-3866).
- **Paper o live**: identico.

### 52. I tipi d'ordine che la strategia usa
- **Cosa fa**: ogni ordine della strategia passa da `_place` (area A, 1487): quota arrotondata alla scala Betfair,
  importo al centesimo, persistenza LAPSE («cade al fischio / alla sospensione») salvo diversa indicazione.
- **Quando scatta**: sempre.
- **Cosa succede dopo**: in quest'area l'unico ordine **che resta in gioco** (PERSIST) e' l'ultimo ingresso `under_last`.
  Nessun ordine e' chiesto come **tutto o niente** (fill-or-kill) dall'engine: se il servizio lo usa per le uscite al
  mercato in live e' dell'area C. `ko_green` e' chiesto LAPSE ma il servizio lo tratta sempre come appoggiato.
- **Numeri**: -
- **Esempio**: -
- **Cosa vede l'utente**: -
- **Dove**: `engine.py:1487-1491`, `2901-2902`.
- **Paper o live**: identico.

---

## Percorso di una partita, passo per passo

### I cicli
1. **Cicli pre-partita** (da 1 ora a 10' dal fischio): fino a 10 (`pre_max_cycles`). Ognuno = back Under 3,5 10 EUR +
   lay di green 2 tick sotto. Chiuso un ciclo, 60 s di pausa e si ricomincia.
2. **Ultimo ingresso** (a 10' dal fischio, solo se il ciclo aperto viene chiuso con la lay «finale»): back Under 3,5
   10 EUR PERSIST, che entra in gioco. Se a 10' il ciclo e' in perdita si tiene quella posizione (HOLD); se e' gia' piatto
   non c'e' ultimo ingresso.
3. **Uscita al fischio**: lay 2 tick sotto la media, per 3 minuti di gioco.
4. **Seconda puntata** (solo con gol entro la finestra): back Under 3,5 5 EUR, una volta sola.
5. **Copertura** Over 4,5: piena, oppure in due tranche dopo la seconda puntata.
6. **Uscite globali** (cash out, perdita tollerata, cap).
7. **Re-ingresso** Under 4,5 (una volta sola, dopo una chiusura in profitto, con 1 gol entro il 45').

### Ogni ingresso e ogni uscita

| Ruolo | Mercato | Selezione | Punta/banca | Quota | Importo | Tipo |
|---|---|---|---|---|---|---|
| `under_entry` | O/U 3,5 | Under | punta | miglior back | stake 10 | cade al fischio |
| `under_green` (resting) | O/U 3,5 | Under | banca | prezzo medio - 2 tick | esposizione netta / quota | cade al fischio |
| `under_green` (taker / finale / veto) | O/U 3,5 | Under | banca | miglior lay | esposizione netta / quota | cade al fischio |
| `under_last` | O/U 3,5 | Under | punta | miglior back + 0 tick | stake 10 | **resta in gioco** |
| `ko_green` | O/U 3,5 | Under | banca | prezzo medio - 2 tick | esposizione netta / quota | appoggiata (LAPSE, cade alle sospensioni) |
| `under_second` | O/U 3,5 | Under | punta | miglior back | 50 % stake = 5 | cade alla sospensione |
| `over_cover` | O/U 4,5 | Over | punta | miglior back - 2 tick (limite) | (1,2 x rischio - gia' coperto)/((q-1) x 0,95) x frazione | cade alla sospensione |
| `under_close` | O/U 3,5 | Under | banca | miglior lay (+0 tick) | esposizione netta | cade alla sospensione |
| `over_close` | O/U 4,5 | Over | banca | miglior lay | esposizione netta | cade alla sospensione |
| `reentry` | O/U 4,5 | Under | punta | miglior back | stake 10 | cade alla sospensione |
| `reentry_green` | O/U 4,5 | Under | banca | prezzo medio - 2 tick (o miglior lay se chiusura a tempo/cash out) | esposizione netta / quota | cade alla sospensione |

(`manual_close` = cash out dell'utente, area A/C.)

### Tabella delle transizioni

| Stato di partenza | Condizione | Azione | Stato di arrivo |
|---|---|---|---|
| qualunque pre-partita | partita in gioco, posizione Under > 0, uscita al fischio accesa | ritira ordini vivi (non il PERSIST nei primi 120 s); salva prezzo al fischio, `live_since`, gol al fischio | `LIVE_KO_GREEN` |
| qualunque pre-partita | in gioco, posizione > 0, uscita al fischio spenta | ritira ordini vivi; copertura ordinata | `LIVE_UNCOVERED` |
| qualunque pre-partita | in gioco, nessuna posizione | ritira ordini vivi (non il PERSIST nei primi 120 s) | `IDLE_LIVE` |
| `WATCH` | una delle 13 condizioni della scheda 1 fallisce | niente | `WATCH` |
| `WATCH` | cancello aperto | punta Under 3,5 10 EUR al miglior back (LAPSE) | `PRE_ENTRY_PENDING` |
| `PRE_ENTRY_PENDING` | gamba assente o morta senza abbinato | niente | `WATCH` |
| `PRE_ENTRY_PENDING` | abbinato per intero | resting: banca Under 3,5 a media - 2 tick | `PRE_OPEN` |
| `PRE_ENTRY_PENDING` | 60 s, abbinato in parte | ritira il residuo | `PRE_OPEN` |
| `PRE_ENTRY_PENDING` | 60 s, niente abbinato | ritira | `WATCH` |
| `PRE_ENTRY_PENDING` | altrimenti | niente | `PRE_ENTRY_PENDING` |
| `PRE_OPEN` | posizione zero | ritira tutto | `WATCH` |
| `PRE_OPEN` | >= KO-10', piatto | ritira green; ciclo +1, archivia, pausa 60 s | `WATCH` |
| `PRE_OPEN` | >= KO-10', niente prezzo lay | ritira green | `HOLD` |
| `PRE_OPEN` | >= KO-10', bloccato > 0,01 | ritira green; banca finale al miglior lay | `PRE_GREEN_PENDING` |
| `PRE_OPEN` | >= KO-10', bloccato <= 0,01, veto «veto» | ritira green; banca finale al miglior lay (in perdita); ricorda il veto | `PRE_GREEN_PENDING` |
| `PRE_OPEN` | >= KO-10', bloccato <= 0,01, nessun veto | ritira green | `HOLD` |
| `PRE_OPEN` | piatto e nessuna green viva | ritira tutto; ciclo +1, archivia | `WATCH` |
| `PRE_OPEN` | resting, green assente/morta | banca Under 3,5 a media - 2 tick sul residuo | `PRE_OPEN` |
| `PRE_OPEN` | resting, green viva | niente | `PRE_OPEN` |
| `PRE_OPEN` | taker, miglior lay <= media - 2 tick | banca al miglior lay | `PRE_GREEN_PENDING` |
| `PRE_OPEN` | taker, altrimenti | niente | `PRE_OPEN` |
| `PRE_GREEN_PENDING` | green assente | niente | `PRE_OPEN` |
| `PRE_GREEN_PENDING` | green morta senza abbinato / abbinata in parte | niente | `HOLD` (finale) o `PRE_OPEN` |
| `PRE_GREEN_PENDING` | green abbinata, piatto, non finale | ciclo +1, archivia | `WATCH` |
| `PRE_GREEN_PENDING` | green finale abbinata, piatto, PERSIST acceso, niente veto, mercato ok | ciclo +1, archivia; punta Under 3,5 10 EUR PERSIST | `PRE_LAST_ENTRY_PENDING` |
| `PRE_GREEN_PENDING` | green finale abbinata, ma PERSIST spento / veto / book assente / liquidita' / tetto | ciclo +1, archivia | `IDLE_LIVE` |
| `PRE_GREEN_PENDING` | green finale abbinata, mercato sospeso | niente | `PRE_GREEN_PENDING` |
| `PRE_GREEN_PENDING` | green viva >= 10 s, tentativi < 20 | ritira + banca al nuovo miglior lay (la nuova parte al giro dopo) | `PRE_GREEN_PENDING` |
| `HOLD` | fino al fischio | niente | `HOLD` |
| `PRE_LAST_ENTRY_PENDING` | fino al fischio | niente | `PRE_LAST_ENTRY_PENDING` |
| `IDLE_LIVE` | nessuna gamba mai | niente, P&L 0 | `SETTLED` |
| `IDLE_LIVE` | ha gambe | niente | `IDLE_LIVE` (fino a mercato chiuso) |
| `LIVE_KO_GREEN` | posizione zero | ritira tutto | `IDLE_LIVE` |
| `LIVE_KO_GREEN` | uscita abbinata per intero | ritira PERSIST scaduto; re-ingresso permesso, motivo «profit» | `FLAT` |
| `LIVE_KO_GREEN` | uscita abbinata in parte (non piu' viva) | copertura ordinata | `LIVE_UNCOVERED` |
| `LIVE_KO_GREEN` | gol dopo il fischio, seconda puntata accesa e mai fatta | ritira l'uscita; segna il momento del gol | `LIVE_SECOND_ENTRY` |
| `LIVE_KO_GREEN` | gol dopo il fischio, seconda puntata spenta o gia' fatta | ritira l'uscita; copertura ordinata | `LIVE_UNCOVERED` |
| `LIVE_KO_GREEN` | 180 s di gioco con mercato aperto | ritira l'uscita; copertura ordinata | `LIVE_UNCOVERED` |
| `LIVE_KO_GREEN` | mercato aperto non in gioco / sospeso / ignoto | niente | `LIVE_KO_GREEN` |
| `LIVE_KO_GREEN` | mercato chiuso, o piano non calcolabile | copertura ordinata | `LIVE_UNCOVERED` |
| `LIVE_KO_GREEN` | lay ignota o altra lay viva | niente | `LIVE_KO_GREEN` |
| `LIVE_KO_GREEN` | uscita viva ma prezzo/importo cambiati | ritira l'uscita | `LIVE_KO_GREEN` |
| `LIVE_KO_GREEN` | nessuna uscita viva | banca Under 3,5 a media - 2 tick (appoggiata) | `LIVE_KO_GREEN` |
| `LIVE_SECOND_ENTRY` | puntata abbinata | copertura a tranche (fase 1) | `LIVE_UNCOVERED` |
| `LIVE_SECOND_ENTRY` | 120 s dal gol senza abbinamento / tentativi esauriti / importo nullo / tetto | ritira la puntata viva; copertura piena (fase 0) | `LIVE_UNCOVERED` |
| `LIVE_SECOND_ENTRY` | mercato non aperto / poca liquidita' / puntata viva | niente | `LIVE_SECOND_ENTRY` |
| `LIVE_SECOND_ENTRY` | nessuna puntata viva | punta Under 3,5 5 EUR al miglior back | `LIVE_SECOND_ENTRY` |
| `LIVE_UNCOVERED` | copertura spenta / 3+ gol / niente rischio / gia' sufficiente / tetto | niente | `LIVE_COVERED` |
| `LIVE_UNCOVERED` | attesa prima tranche / mercato Over non aperto / attesa dopo gol / overshoot / liquidita' | niente | `LIVE_UNCOVERED` |
| `LIVE_UNCOVERED` | si copre | punta Over 4,5 al limite 2 tick sotto il miglior back | `LIVE_COVER_PENDING` |
| `LIVE_COVER_PENDING` | gamba assente o ritirata non piena | tentativi +1 | `LIVE_UNCOVERED` |
| `LIVE_COVER_PENDING` | prima tranche abbinata | fase 2, orologio seconda tranche | `LIVE_COVERED` |
| `LIVE_COVER_PENDING` | copertura abbinata | fase 0 | `LIVE_COVERED` |
| `LIVE_COVER_PENDING` | ferma 10 s, residuo < 0,01 | ritira | `LIVE_COVERED` |
| `LIVE_COVER_PENDING` | ferma 10 s, mercato aperto | ritira + punta il residuo al nuovo limite (giro dopo) | `LIVE_COVER_PENDING` |
| `LIVE_COVERED` | nessuna esposizione in gioco | niente | `FLAT` |
| `LIVE_COVERED` | netto >= 5 % base o cash out intelligente | chiusure al mercato su ogni selezione | `LIVE_CLOSING` (motivo «profit») |
| `LIVE_COVERED` | HT o 46'-85', 3-4 gol, modello/regola fissa | chiusure al mercato | `LIVE_CLOSING` (motivo «loss_ht»/«loss_2t») |
| `LIVE_COVERED` | netto <= -100 % base | chiusure al mercato | `LIVE_CLOSING` (motivo «loss_cap») |
| `LIVE_COVERED` | fase 2 e 180 s dalla prima tranche | copertura ordinata, fase 3 | `LIVE_UNCOVERED` |
| `LIVE_COVERED` | altrimenti | niente | `LIVE_COVERED` |
| `LIVE_CLOSING` | chiusure su selezioni gia' decise | ritira | `LIVE_CLOSING` |
| `LIVE_CLOSING` | nessuna chiusura viva, residuo, tentativi < 20 | chiusure del residuo | `LIVE_CLOSING` |
| `LIVE_CLOSING` | nessuna chiusura viva e niente residuo (o tentativi finiti) | re-ingresso permesso se «profit» | `FLAT` |
| `LIVE_CLOSING` | chiusura ferma 10 s | ritira + rimette al miglior prezzo | `LIVE_CLOSING` |
| `FLAT` | esposizione residua chiudibile | niente | `LIVE_COVERED` |
| `FLAT` | tutte le condizioni del re-ingresso | punta Under 4,5 10 EUR al miglior back | `REENTRY_PENDING` |
| `FLAT` | altrimenti | niente | `FLAT` |
| `REENTRY_PENDING` | abbinato, mercato aperto | banca Under 4,5 a prezzo - 2 tick | `REENTRY_OPEN` |
| `REENTRY_PENDING` | 60 s con parte abbinata | ritira residuo | `REENTRY_OPEN` |
| `REENTRY_PENDING` | morto senza abbinato / 60 s senza abbinato | ritira; re-ingresso fatto | `FLAT` |
| `REENTRY_OPEN` | piatto | ritira green; re-ingresso fatto | `FLAT` |
| `REENTRY_OPEN` | green assente, mercato aperto | banca Under 4,5 a media - 2 tick | `REENTRY_OPEN` |
| `REENTRY_OPEN` | minuto limite (solo se > 0) | ritira green + banca al miglior lay | `REENTRY_GREEN_PENDING` |
| `REENTRY_GREEN_PENDING` | piatto o green abbinata | re-ingresso fatto | `FLAT` |
| `REENTRY_GREEN_PENDING` | green morta senza abbinato | niente | `REENTRY_OPEN` |
| qualunque (area A) | mercato chiuso | ritira tutto; poi regolamento | `SETTLING` -> `SETTLED` |

---

## Glossario

**Caselle (stati)**
- `WATCH`: guardo la partita, nessuna posizione aperta nel ciclo.
- `PRE_ENTRY_PENDING`: puntata d'ingresso pre-partita in coda.
- `PRE_OPEN`: posizione Under 3,5 aperta in pre-partita, green in coda o in attesa.
- `PRE_GREEN_PENDING`: lay di chiusura pre-partita (al mercato o finale) in coda.
- `HOLD`: posizione in perdita a 10' dal fischio: la tengo fino al gioco.
- `PRE_LAST_ENTRY_PENDING`: ultimo ingresso (PERSIST) in coda, aspetto il fischio.
- `IDLE_LIVE`: in gioco senza posizione.
- `LIVE_KO_GREEN`: in gioco, provo l'uscita a +2 tick per 3 minuti.
- `LIVE_SECOND_ENTRY`: dopo un gol precoce, seconda puntata Under 3,5.
- `LIVE_UNCOVERED`: in gioco senza copertura, devo (o sto per) comprarla.
- `LIVE_COVER_PENDING`: copertura Over 4,5 in coda.
- `LIVE_COVERED`: coperto, valgono le uscite globali.
- `LIVE_CLOSING`: ordini di chiusura in coda.
- `FLAT`: posizione chiusa.
- `REENTRY_PENDING` / `REENTRY_OPEN` / `REENTRY_GREEN_PENDING`: re-ingresso Under 4,5 in coda / aperto con green sul book /
  chiusura a tempo in coda.
- `SETTLING` / `SETTLED`: regolamento in corso / fatto. `ERROR`: guasto. `SKIPPED`: saltata dall'utente.

**Ruoli delle gambe**: `under_entry` ingresso del ciclo; `under_green` green pre-partita (resting, taker o finale);
`under_last` ultimo ingresso PERSIST; `ko_green` uscita al fischio; `under_second` seconda puntata; `over_cover`
copertura; `under_close` / `over_close` chiusure del cash out; `reentry` re-ingresso Under 4,5; `reentry_green` green o
chiusura del re-ingresso; `manual_close` cash out dell'utente.

**Parole della partita (`ctx`)**: `cycle_no` cicli gia' chiusi (0 = primo in corso; nei testi +1); `entry_price_initial`
prezzo del primo ingresso della partita; `last_green_at` ora dell'ultimo ciclo chiuso (pausa); `attempts` tentativi di
riprezzo; `reentry_allowed` / `reentry_done` re-ingresso permesso / gia' fatto; `close_reason` motivo della chiusura
(«profit», «loss_ht», «loss_2t», «loss_cap», «reentry_time», «manual»); `cover_skipped` copertura saltata; `ko_price_under`
quota Under al fischio; `live_since` ora in cui si e' visto il gioco; `ko_goals` gol al fischio; `early_goal_at` ora del
gol precoce; `second_entry_done` seconda puntata gia' tentata; `cover_stage` fase copertura (0 in una volta, 1 prima
tranche, 2 attesa seconda, 3 seconda tranche); `cover_stage1_at` ora della prima tranche abbinata; `cover_forced`
copertura ordinata (niente attesa intelligente); `veto_u35` verbale del veto scattato; `no_reentry` chiusa a mano,
niente ingressi; `flatten_pending` cash out manuale in corso; `rifiuti` ultime richieste rifiutate dal mercato;
`_archive_legs` ordine di archiviare il ciclo.

**Termini tecnici**: *finale* = lay di chiusura a 10' dal fischio (se non si abbina si va in HOLD); *archiviata* = gamba
di un ciclo chiuso: conta nel conto finale, non nel rischio; *esposizione netta* = quanto si vince/perde sulla
selezione con i soli abbinamenti; *LAPSE* = la parte non abbinata cade al passaggio in gioco (e alle sospensioni in
gioco); *PERSIST* = la parte non abbinata resta in gioco; *appoggiata (resting)* = lay lasciata sul book a una quota
fissa; *taker* = chiusura al miglior prezzo disponibile.

**Voci di telemetria/attivita'**: `pre_cycle` ciclo chiuso; `last_entry_locked` profitto dell'ultimo ingresso;
`veto_under_calibrata` veto; `ko_green` esito dell'uscita al fischio (appoggiata / abbinata / gol / scaduta);
`second_entry` seconda puntata; `cover` copertura piazzata; `cover_wait` attesa copertura (motivo); `cover_staged`
tranche; `cashout` valore del cash out; `loss_exit` / `loss_exit_deciso` uscita in perdita; `close_retries_exhausted`
tentativi di chiusura finiti.

---

## Differenze dalla Costituzione

1. **§3 Fase 1 titolo «da KO - 3h»**: il codice entra da 1 ora prima (`entry_hours_before_ko` = 1,0, `config.py:85`,
   letto in `engine.py:2512`).
2. **§3 Fase 1 «mai chiudere in perdita pre-match» e Fase 2 «in PERDITA -> HOLD»**: col veto M1 acceso di default
   (`config.py:152`) il codice CHIUDE in perdita a 10' dal fischio quando la P calibrata e' sotto soglia
   (`engine.py:2722-2739`) e non fa l'ultimo ingresso (2890-2898). La Costituzione non nomina il veto da nessuna parte.
3. **§3 schema «HOLD -> LIVE_UNCOVERED» e «PRE_LAST_ENTRY_PENDING -> LIVE_UNCOVERED»**: il codice passa prima da
   `LIVE_KO_GREEN` (uscita al fischio) quando `ko_green_enabled` e' acceso (`engine.py:2660-2663`); la §15 lo descrive,
   lo schema del §3 no.
4. **§3 Fase 2 «in PROFITTO -> green taker + nuovo BACK PERSIST»**: nel codice il PERSIST parte SOLO dopo che la lay
   finale si e' abbinata per intero (`engine.py:2794-2795`); se la lay finale non si abbina entro 10 s la posizione va in
   `HOLD` (vedi Cose strane n. 3) e il PERSIST non parte. Se a 10' il ciclo era gia' piatto, nessun PERSIST (2704-2705).
5. **§3 Fase 5 «Solo con 2, 3 o 4 gol»**: il codice usa 3-4 gol (`ht_loss_goals_min` = 3, `config.py:287`,
   `engine.py:3543-3544`), e la stessa fascia vale anche per il 2° tempo.
6. **§15.6 «la finestra `ko_green_window_s` non scorre quando non si puo' appoggiare»**: il codice non ferma l'orologio,
   si limita a non dichiarare la scadenza durante la sospensione; l'orologio parte da `live_since` e conta anche il
   tempo sospeso (`engine.py:2979-2981`).
7. **§15.6 tabella caso (d) «abbinato in parte: il residuo scaduto ... come in (b): finestra aperta -> si ri-appoggia»**:
   il codice, con l'ultima `ko_green` abbinata in parte e non piu' viva, va subito a coprire il residuo senza
   riappoggiare l'uscita (`engine.py:3032-3035`).
8. **§15.2 riga B «Stato LIVE_COVER_PENDING»**: il codice va prima a `LIVE_UNCOVERED` (`engine.py:3057`); la copertura
   parte al giro dopo.
9. **§3 Fase 3 attesa «intelligente ma non lenta» (0 gol, max 10', hazard, P(4), quota, risparmio)**: in tutte le
   strade che portano a `LIVE_UNCOVERED` il codice mette `cover_forced` = vero, e con copertura ordinata l'attesa
   intelligente viene saltata (`engine.py:3329-3330`): resta solo l'attesa di 45 s dopo un gol. Nel flusso normale
   l'attesa intelligente descritta dalla Fase 3 non si applica.
10. **§16.4-bis punto 27 «chiusura finale non abbinata: riprezza»**: vedi n. 4 e Cose strane n. 3.
11. **§3 Fase 6 «lay non abbinata -> resta sul book fino a fine gara»**: coerente, ma nel codice la posizione Under 4,5
    del re-ingresso non ha copertura ne' uscita in perdita ne' cash out mentre e' in `REENTRY_OPEN` (solo la green).
    La Costituzione non dice ne' si' ne' no: lo segnalo.
12. **§15.3 «prima tranche dopo 2 minuti dal gol»**: coerente (`early_goal_cover_delay_s` 120). Ma se la seconda puntata
    si abbina, la prima tranche aspetta ANCHE il riprezzo di 45 s dopo l'ultimo gol (`cover_postgoal_delay_s`): con
    un secondo gol la prima tranche puo' slittare.

---

## Cose strane

1. **PERSIST non abbinato al fischio lasciato vivo per sempre (money-critical, da verificare con l'area C)**: dalla
   casella `PRE_LAST_ENTRY_PENDING`, se al fischio il PERSIST non ha abbinato nulla e i cicli precedenti sono archiviati,
   S = 0 -> `IDLE_LIVE` SENZA ritirare il PERSIST (grazia di 120 s, `engine.py:2641-2643`, 2666). In `IDLE_LIVE`
   l'engine non fa nulla (`_dispatch` 2465-2470, nessun `_late_persist_cancel`). Se il PERSIST si abbina dopo, nessuna
   casella lo gestisce: posizione Under 3,5 in gioco senza uscita e senza copertura fino al regolamento. Nel servizio
   non ho trovato un ripiego (cercato `IDLE_LIVE`, `cancel_unmatched_after_ko_s`: solo il ritorno da falso regolamento,
   `service.py:4068`).
2. **Commenti che dicono «SPENTO» per il veto**: `engine.py:2542` («PREPARATO, SPENTO») e `engine.py:352` (MatchCtx:
   «interruttore SPENTO»), mentre `config.py:152` e `engine.py:2571` lo dicono ACCESO di default. Vale il codice: acceso.
3. **Il riprezzo della lay finale di fatto non avviene**: `PRE_GREEN_PENDING` emette ritira + nuova lay nello stesso giro
   (`engine.py:2804-2807`); «mai due lay» (`_una_sola_lay` 1901) toglie la lay nuova e lascia il ritiro (con i
   tentativi +1). Al giro dopo la vecchia e' ritirata senza abbinato e il ramo 2783-2786 manda in `HOLD` (finale) o
   `PRE_OPEN` (non finale). Per la finale: la posizione entra in gioco scoperta invece di essere chiusa. Stessa dinamica
   per il riprezzo di `REENTRY_GREEN_PENDING` (3804-3807 -> 3795-3796) e `LIVE_CLOSING` (lay di chiusura).
4. **`_pending_closings` non conta `reentry_green`** (`engine.py:1815-1816`), ma il cash out chiude l'Under 4,5 proprio
   con quel ruolo (1759). In `LIVE_CLOSING` una chiusura `reentry_green` viva non e' vista come «in attesa»: si passa a
   «chiusura residuo» e si ripropone la chiusura; la regola «mai due lay» dovrebbe rimandarla, ma l'annullo della
   vecchia non viene emesso (`_close_actions` esclude dal ritiro il proprio ruolo, 1778): rischio di attesa indefinita.
   Da verificare in replay.
5. **Ingresso non abbinato torna a `WATCH` senza pausa e senza freno sui rifiuti** (`engine.py:2680-2681`): un ingresso
   rifiutato dal mercato puo' essere ripresentato al giro dopo; lo copre solo `aperture_ferme` (cause non di mercato).
6. **Finestra d'uscita e sospensione**: vedi Differenza n. 6. Con una sospensione lunga (es. VAR) la finestra risulta
   scaduta appena il mercato riapre.
7. **Docstring di `residuo_non_chiudibile`** dice «sotto il minimo Betfair di 2 EUR» (`engine.py:3656-3657`) ma la soglia
   e' 0,01 EUR (`size_chiudibile` 1734). Anche il testo mostrato all'utente («residuo sotto il minimo Betfair», 3682)
   ricorda i 2 EUR.
8. **`_after_final_green` e il tetto per partita**: confronta lo stake col tetto intero (2883-2884) invece di usare
   `liability_room`, con la motivazione che le gambe verranno archiviate; e' coerente solo se non ci sono altre gambe
   vive o ignote (quelle non vengono archiviate, 3834-3841).
9. **Commento di `apply_decision`** (3843-3846): «restano solo quelli del ciclo corrente e dei successivi»; il codice
   tiene SOLO il ciclo corrente (uguaglianza, 3848-3849).
10. **`ko_green_retry_s`** (5 s, `config.py:173`) non e' letto da nessun ramo (dichiarato nel commento 3128-3136).
11. **`entry_price_initial` non viene scritto** se l'ingresso e' tenuto per scadenza a 60 s con abbinamento parziale
    (2684-2687, niente `_after_entry_fill`); viene poi scritto al fischio (2647). Nel frattempo nessuno lo usa.
12. **Casella `PRE_GREEN_PENDING` per la lay finale col veto**: il verbale `veto_u35` viene salvato anche quando, per le
    uscite manuali (default), la lay non parte e diventa proposta (`gate_uscite` tiene gli aggiornamenti tranne
    `close_reason`/`attempts`, 2411-2418): se l'utente non approva, la posizione entra in gioco e il veto risulta
    «scattato» (niente PERSIST).
13. **`_cycle_done`** usa come profitto la vincita lorda dell'esposizione (2839-2840) mentre l'uscita al fischio usa il
    netto commissione (`locked_pnl`, 3022): i due numeri mostrati all'utente non sono omogenei.
14. **`_decide_prematch` ramo ERROR (2816)** e il `return` finale di `soglia_veto_under35` (2598) sono irraggiungibili.
15. **Cap perdita a 100 %**: `event_loss_cap_pct` = 100 fa scattare la chiusura solo con netto <= -base, cioe' quando
    non c'e' piu' niente da salvare: in pratica spento.
16. **`attempts` condiviso**: lo stesso contatore serve a green pre-partita, seconda puntata, copertura e chiusure; non
    viene azzerato entrando in `LIVE_SECOND_ENTRY` (i tentativi di riprezzo pre-partita in `HOLD` restano), quindi la
    seconda puntata puo' avere meno di 20 tentativi.

---

## Non ho capito / non ho letto

- Non ho letto il servizio (`service.py`) oltre alle righe citate: come esegue gli ordini (paper/live, FOK, place-and-
  trim), come costruisce `order_fresh`, `inplay`, `ht_active`, `hazard`, `p_under35_cal` e se c'e' un ripiego per il
  caso di Cose strane n. 1 (area C).
- Non ho letto `settle_legs`, `locked_pnl` nel dettaglio fiscale, `smart_cashout`/`loss_exit_model`/`cover_timing` oltre
  a quanto serve (area A).
- Non so con certezza se Betfair cancelli le puntate LAPSE non abbinate a ogni sospensione in gioco per il calcio (lo
  afferma la Costituzione §15.6 per l'uscita al fischio; l'engine non lo gestisce, lo fa il servizio con `riapertura`).
- Cose strane n. 3 e n. 4 dipendono dall'ordine in cui `decide` applica le guardie (area A) e da quando il servizio
  marca le gambe ritirate: le ho ricostruite leggendo, non eseguendo. Vanno confermate col replay.
- Se `early_goal_at` restasse vuoto in `LIVE_SECOND_ENTRY` (riavvio), il «tempo scaduto» non arriverebbe mai
  (`engine.py:3171-3172`) e la copertura dipenderebbe solo dai 20 tentativi: non so se il servizio lo persiste sempre.
- Gli esempi numerici con commissione sono arrotondati al centesimo a mano; le quote dei tick (0,01 sotto 2,00; 0,02 fra 2
  e 3; 0,10 fra 4 e 6; 0,20 fra 6 e 10) sono la scala standard Betfair usata da `ticks_away`.
