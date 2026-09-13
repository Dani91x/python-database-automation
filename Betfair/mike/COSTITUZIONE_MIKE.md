# COSTITUZIONE MIKE — bot di trading Under 3.5 / Over 4.5

Documento normativo e spiegazione completa del bot Mike (sezione "Mike" dell'app, `/mike`).
Come le costituzioni di Omega e Safe Strategy: ciò che è scritto qui vale più di ogni parametro.
Aggiornato al **12/09/2026** sul codice pushato con `9d09c81` (base `1b6b151`): audit
`Betfair/AUDIT_2026-09-11_omega_safe_mike.md` §1 applicato per intero, review indipendente
(5 CRITICAL + 8 HIGH) corretta, certificazione UI↔servizio meccanica e certificazione sui dati
reali del DB. Codice in `Betfair/mike/`, UI in `frontend/src/pages/Mike.tsx` +
`frontend/src/components/mike/`, data-layer in `frontend/src/lib/mike.ts`.

**Stato operativo al 12/09/2026**: paper **non ancora certificato** (0 partite paper complete
sul codice nuovo); live **BLOCCATO**. Due migrazioni da applicare a mano (§0, §9, §10).

---

## §0 Verdetto di partenza e gate

- La struttura STATICA del bot legacy MIKE2 (back Under 3.5 + back Over 4.5 tenuti fino al 90')
  è **NO-GO** su 18.441 partite reali: ROI −9,67%, con le regole esatte di MIKE2 −6,36%.
  La probabilità reale di "esattamente 4 gol" è 14,7% ed è prezzata correttamente dal mercato:
  non esiste un edge a tenere la scommessa fino alla fine.
- Mike NON è quella scommessa. È un bot di **TRADING**: guadagna i tick del green-up pre-match,
  si copre in-play sull'Over 4.5, esce a profitto o con una perdita piccola prima che il 4° gol
  possa farlo perdere tutto. L'obiettivo dichiarato è **evitare tassativamente la somma gol 4**
  senza uscire troppo presto.
- Fatti noti che impongono prudenza: il green-up in-play simulato dell'Under resta negativo
  (−9,4% → −3,4% con modello equo); il back Under in-play (theta) è EV− in tutte le varianti
  testate; a 0-0 l'Under 3.5 decade solo ~0,5 tick al minuto.
- Quindi: **paper-first**. GO/NO-GO al live solo dopo almeno 40 partite paper complete e un
  backtest sulle registrazioni REC con haircut −1 tick sui fill taker. Il verdetto va scritto QUI,
  in questo paragrafo, con i numeri.

### Gate del 12/09/2026 (da superare nell'ordine)

1. **Migrazioni**: `migrations/mike_bot_v2.sql` poi `migrations/mike_history_v2.sql`, nell'ordine
   di `migrations/APPLY_ORDER_2026-09-11.md` (sonda sul DB reale dell'11/09: `get_mike_aggregates`
   → `PGRST202` «non esiste», `get_mike_daily` → `42725 is not unique`). Senza la seconda lo
   **storico di Mike è ROTTO**, non degradato.
2. **Riavvio dei servizi** (l'exe è l'avviatore del `main.js` vivo: si riavvia l'app, non si
   ricompila): al riavvio partono la riconciliazione `mike_trades` ↔ `positions` (H2) e la
   pubblicazione della liability NETTA per partita (M4). Finché il servizio non riparte,
   `aggregates.liability_source` resta `rows_sum` e la UI lo **dichiara**.
3. **Paper ≥ 40 partite complete** sul codice nuovo, poi il verdetto scritto sopra, con i numeri.
   Nessun GO al live prima: la riconciliazione live non è mai stata provata sul campo (§10).

---

## §1 Che cos'è Mike in una frase

Per ogni partita di calcio con calcio d'inizio entro 3 ore, Mike punta l'Under 3.5 pre-match e lo
chiude subito a +2 tick (green-up, ripetuto finché c'è tempo); se arriva in-play con l'Under
aperto, compra una copertura sull'Over 4.5 dimensionata per guadagnare il 20% se finisce 5+ gol,
poi chiude tutto al primo profitto del 5% (o prima, se il rischio lo consiglia), oppure esce
con una perdita piccola all'intervallo o nel secondo tempo quando i 4 gol sono troppo probabili.

Unica famiglia di esiti: con 0-3 gol vince l'Under, con 5+ gol vince l'Over, con **esattamente 4**
gol perdono entrambi. Tutto il bot è costruito attorno a questa casella.

---

## §2 Da dove arrivano i dati (regola dei processi: nessuna chiamata Betfair duplicata)

| Dato | Fonte | Note |
|---|---|---|
| Quote back/lay, size, stato mercato, in-play, betDelay | **feed unico** `safe_strategy_scan` (scanner della Safe Strategy) | ramo pre-KO O/U acceso con env `SAFE_PRE_KO_OU_HOURS=3`: pubblica le linee 3.5 e 4.5 già 3 ore prima del KO. Una SELECT per ciclo |
| Minuto, punteggio, espulsioni, intervallo, corner/cartellini | stesso feed (`score_raw`, `timeline`) | ritardo punteggi 2-3 s: ricordarlo |
| λ Dixon-Coles per squadra, ρ, calibrati | `fixture_predictions` via ponte evento→fixture (`live_follow`) | letture DB, zero Betfair |
| Hazard di gol nei 3' successivi | Atlante hazard (theta, 54.009 partite) | JSON caricato una volta |
| Distribuzione HT→FT | tabella empirica Omega (RPC `get_omega_ht_ft`) | cache per lega, retry ogni 10' |
| Regolamento (esito dei runner) | REST `listMarketBook`, 2 chiamate per partita, solo a mercato chiuso | throttle 30 s |
| Ordini | `safe_strategy/execution.place` (paper = fill sul feed; live = REST FOK con la sessione condivisa) | stessa macchina di Omega e Safe |

Mike NON ha un login proprio, NON apre connessioni stream, NON ha un catalogo proprio.
Costo aggiunto alla piattaforma: un processo (`mike-service` sotto watchdog, lock porta 47319) e
2 mercati per partita in finestra sul pool stream dello scanner (tier 2, capacità 720, ~100 usati).

I selection ID vengono risolti PER NOME **dal feed** (`feed.event_info`, dai nomi dentro
`blk["selections"]`) e persistiti in `ctx.selections` (`service.py`, `extra["selections"]`), che è
la sola fonte usata dal regolamento a mercato chiuso. Riferimento noto: Under 3.5 = 1222344,
Over 3.5 = 1222345, Over 4.5 = 1222346, Under 4.5 = 1222347.
Certificazione dell'11/09: 44 selezioni su 11 partite, zero scostamenti.

> Nota — **superato l'11/09/2026 (sera)**: prima la risoluzione passava da un catalogo proprio
> (`Betfair/mike/catalogue.py`) che confrontava gli id con `config.EXPECTED_SEL` e logava un WARN
> sugli scostamenti. `catalogue.py` era codice morto ed è stato **rimosso** (audit M3): oggi
> `config.EXPECTED_SEL` resta solo come costante documentale (usata dai test, mai a runtime) e
> **non esiste più nessun WARN di scostamento**. Se il feed non porta entrambe le linee, la
> partita semplicemente non è completa (`EventInfo.complete = False`) e non viene armata.

---

## §3 La vita di una partita, fase per fase

Ogni partita è una macchina a stati indipendente (`engine.py`, logica pura senza I/O).
Il servizio (`service.py`) gira ogni 1-2 secondi: legge il feed, costruisce lo `Snapshot`
(book, minuto, gol, hazard, probabilità di modello), chiama `decide`, esegue le azioni, salva.

```
WATCH → PRE_ENTRY_PENDING → PRE_OPEN → PRE_GREEN_PENDING → WATCH (ciclo+1) …
                                │ KO − 10'
                                ├─ in perdita → HOLD → LIVE_UNCOVERED
                                └─ in profitto → green taker + PRE_LAST_ENTRY_PENDING (PERSIST) → LIVE_UNCOVERED
LIVE_UNCOVERED ─copertura─► LIVE_COVER_PENDING → LIVE_COVERED ─profitto / uscita─► LIVE_CLOSING → FLAT
FLAT ─1 gol, chiusura precedente in profitto─► REENTRY_PENDING → REENTRY_OPEN → REENTRY_GREEN_PENDING → FLAT
KO senza mai una gamba → IDLE_LIVE → SETTLED ("nessuna operazione")
Cash out / Flatten dalla UI → ctx.flatten_pending → cancel → chiusura netta (manual_close)
                              → in-play: FLAT · pre-KO: WATCH con ctx.no_reentry (solo "Riprendi" riabilita)
mercato CLOSED → SETTLING → SETTLED · errore → ERROR · "Salta" dalla UI → SKIPPED
```

### Fase 1 — Pre-match: ingresso e green-up ciclico (da KO − 3h a KO − 10')

Condizioni di ingresso (tutte insieme, ogni ciclo):
```
mercato Under/Over 3.5 APERTO, non in-play, feed fresco
quota BACK Under 3.5 fra 1,30 e 3,00
liquidità al best ≥ stake (fattore 1,0)
spread back/lay ≤ 6 tick    (ingresso MOLTO anticipato: i book larghi sono normali ore prima)
cicli fatti < 10 · cooldown 60 s dall'ultimo green · stop giornaliero non attivo · tetto partite non raggiunto
```
Cosa fa:
```
BACK Under 3.5 stake (10 €) al best, LAPSE, TTL 60 s (non abbinato → annullato, si riprova)
appena abbinato → LAY resting a −2 tick (green-up) appoggiata SUBITO sul book
lay abbinata → profitto bloccato su entrambi gli esiti, ciclo +1 → WATCH → nuovo ingresso
lay non abbinata → si aspetta (mai chiudere in perdita pre-match)
```
Esempio: BACK 10 € @ 1,50 → LAY 10,14 € @ 1,48 sul book. Presa: +0,14 € lordi qualunque sia
il finale. Con 10 cicli in 3 ore: ~+1,3 €. Fill parziali: la lay è sempre dimensionata
sull'esposizione NETTA abbinata (mai sulla size chiesta).

### Fase 2 — Ultimo ingresso (KO − 10')

```
posizione in PROFITTO (lay a +2 tick abbinabile ora) → green taker al best + NUOVO BACK Under 3.5
                                                       con persistenza PERSIST (resta valido in-play)
posizione in PERDITA                                 → HOLD: si tiene l'Under e si entra live scoperti
residuo PERSIST non abbinato 120 s dopo il KO       → annullato (niente fill su spike post-gol)
```
Perché PERSIST: il mercato sospende al calcio d'inizio e gli ordini LAPSE vengono cancellati.

### Fase 3 — Live: copertura sull'Over 4.5 ("intelligente ma non lenta")

Formula: `X = 1,2 × S / ((Po − 1) × (1 − c))` con S = euro Under abbinati, Po = quota Over 4.5,
c = 5% commissione. Con 5+ gol il netto è **+20% di S**; con 0-3 gol si perde X; con 4 gol
si perde S + X.

Quando copre:
```
0 gol e TUTTE le seguenti → ASPETTA (max 10'): hazard 3' ≤ 6% · P(4) mercato ≤ 16% ·
                            quota Over < 7,0 · risparmio atteso in 5' ≥ 8%
una sola che cade          → COPRE nello stesso ciclo
dopo un gol                → 45 s di riprezzo, poi COPRE (X raddoppia: la quota Over si dimezza)
3+ gol                     → nessuna copertura (la gestione passa al cash-out / uscita)
dati mancanti              → COPRE subito (mai attesa al buio)
```
Hazard 3' = MAX fra Atlante empirico (minuto, gol, lega, squadre) e modello λ-residue
amplificato dalla pressione (corner/cartellini, fino a ×1,25). Comanda la fonte più prudente.
Esempi: S = 10 € @ 1,50 · 7' 0-0 quota 6,6 → BACK 2,26 € · 12' 1-0 quota 3,5 → BACK 5,05 €.

### Fase 4 — Cash-out globale a profitto (stato LIVE_COVERED)

Ogni ciclo il bot calcola "quanto incasso se chiudo ORA entrambe le selezioni con una LAY di
full green ciascuna" (stessa aritmetica del ladder, `compute_greenup`), commissione 5% solo sulle
selezioni in positivo. Base = capitale investito S + X (parametro: total | under).

Regola piena: **valore netto ≥ 5% della base → chiude tutto** (LIVE_CLOSING).
Esempio (10 € @ 1,50 + 2,26 € @ 6,6, base 12,26 €, soglia 0,61 €):
```
30' 0-0  Under lay 1,30 → +1,46 | Over lay 12 → −1,02 → +0,44 € (3,6%)  TIENE
40' 0-0  Under lay 1,22 → +2,18 | Over lay 18 → −1,43 → +0,75 € (6,1%)  CHIUDE: +0,75 € certi, anche con 4 gol
```

**Cash-out intelligente** (chiude PRIMA della soglia, mai sotto il profitto minimo del 2%):
1. **punteggio caldo**: 3+ gol (il prossimo è il 4°) → chiude appena sopra il minimo;
2. **fase calda a un passo dalla soglia**: entro 2 punti dal 5% E (hazard 3' ≥ 10% O pressione ≥ 1,15) → chiude;
3. **valore atteso dell'attesa** (modello): `EV = h·V_gol + (1−h)·V_dopo` con h = P(gol entro 5')
   dall'hazard, V_gol/V_dopo = valore del cash-out con i book proiettati dal modello (quota di
   mercato scalata per P_ora/P_scenario). Vicino alla soglia basta EV < valore attuale; lontano
   serve un margine di 1 punto.
Esempi: 30' 0-0 +0,44 € con 5 corner in 8' e hazard 11% → CHIUDE · 55' 2-1 +0,30 € → CHIUDE
(3 gol) · 40' 0-0 +0,20 € (1,6%) → TIENE (sotto il minimo).

### Fase 5 — Uscita in perdita all'intervallo e nel 2° tempo (a MODELLO)

Finestre: intervallo (feed "half time") e dal 46' all'85'. Solo con **2, 3 o 4 gol** totali
(con 0-1 gol l'Under è avanti: si va verso il profitto). Precedenza: profitto → intelligente →
uscita in perdita → cap.

Decisione a modello (`loss_exit_mode = model`):
```
CHIUDO ORA = valore certo del cash-out (negativo)
TENGO      = Σ P(gol totali = t) × P&L(t)  −  premio al rischio (50% × P(4) × capitale)
chiude se CHIUDO ORA ≥ TENGO − premio
```
P(gol totali) = media fra griglia Omega (λ, minuto, punteggio, rossi) e tabella empirica HT→FT
(parla finché il punteggio è quello dell'intervallo); P(4) prudente = la più pessimista fra
modello/empirico e mercato. Senza dati di modello → regola fissa "perdita ≤ 25% del capitale".
Esempi (Under 20 € @ 1,50 + Over 4 € @ 8, capitale 24 €):
```
HT 1-1  chiudo −5,51 (23%)  tengo −0,79 · P(4) 22% · premio 2,64 → soglia −3,43 → TIENE
        (la regola fissa avrebbe chiuso: uscita troppo presto)
HT 2-1  chiudo −6,53 (27%)  tengo −3,08 · P(4) 30% · premio 3,60 → soglia −6,68 → CHIUDE
        (la regola fissa avrebbe tenuto: il 4° gol era troppo probabile)
HT 1-1  mercato prezza P(4) al 45%                                           → CHIUDE
```
Dopo un'uscita in perdita → FLAT senza re-ingresso.

### Fase 6 — Re-ingresso live (una sola volta per partita)

```
SOLO se la chiusura precedente della partita è stata in PROFITTO
SOLO dopo un gol: esattamente 1 gol totale, nel 1° tempo (minuto ≤ 45)
quota BACK Under 4.5 > quota del primo ingresso Under 3.5 · liquidità ≥ stake · feed fresco
BACK Under 4.5 stesso stake → LAY resting a +2 tick
lay abbinata → profitto, FLAT · lay non abbinata → resta sul book fino a fine gara (Under 4.5 vince con ≤ 4 gol)
```
Nessuna chiusura forzata (parametro `reentry_exit_until_min` = 0 = mai; esiste solo come opzione).

### Fase 7 — Fine gara, regolamento, sicurezze

Regolamento: mercato CLOSED nel feed → lettura REST del book ogni 30 s → Under 3.5 WINNER = 0-3
gol, Over 4.5 WINNER = 5+, Over 3.5 + Under 4.5 WINNER = 4 gol → ogni gamba abbinata won/lost,
commissione per mercato sul netto positivo, gambe mai abbinate void → SETTLED → scheda "Regolate"
e storico giornaliero. Dopo 2 ore senza esito: ultimo punteggio del feed (`settle_fallback`), altrimenti ERROR.

Una riga ASSENTE dal feed vale come mercato chiuso solo dopo 10 minuti di assenza (o partita
finita): al calcio d'inizio il feed passa dal blocco pre-KO a quello in-play e la riga può
sparire per qualche minuto. Un SETTLING falso viene annullato ricostruendo lo stato dalle posizioni.

Partite arrivate in-play senza mai avere una gamba (KO senza ingresso) → `IDLE_LIVE`
("LIVE · NESSUNA POSIZIONE") e poi SETTLED "nessuna operazione", senza P&L. Una partita **già in
gioco non viene più armata affatto** (`feed.is_candidate` ritorna `False` con `payload["inplay"]`,
L4 dell'audit): Mike non entra mai in-play da zero, quindi armarla produceva solo rumore.
Le partite armate prima del KO restano seguite in-play perché arrivano da `mike_events`, non da
`is_candidate`.

---

## §4 Matematica certificata (invarianti money-critical)

1. Esposizioni SOLO dai fill (`Leg.matched`, `avg_price`), mai dalla size chiesta. Ogni ordine
   sul lato opposto (green, copertura, chiusura, riprezzo) è dimensionato sull'esposizione NETTA
   abbinata: i fill parziali sono coerenti per costruzione (test dedicati).
2. Green-up e cash-out con `compute_greenup` (stessa aritmetica del ladder):
   posizione back W/L → LAY al best lay, bloccato = L + (W − L)/lay.
3. Copertura `X = factor·S/((Po−1)(1−c))`; residuo con `cover_size_residual` sui fill parziali:
   con 5+ gol il netto è ESATTAMENTE +20% di S.
4. Commissione per MERCATO sul netto positivo (come `execution.settle_group`).
5. P&L per gol totali (`net_pnl_by_total`) coerente con `pnl_by_scoreline`.
6. Prezzo mancante → nessuna azione (`cashout_value.complete = False`), mai numeri inventati.
7. Cicli pre-match chiusi = `Leg.archived`: contabilità sì, capitale a rischio no.
8. Riprezzo di una chiusura parzialmente abbinata = SOLO il residuo, sull'esposizione inclusiva.
9. `max_liability_per_match` è un clamp DENTRO l'engine (vale anche a UI mal configurata).
10. Mode (paper | live) SOLO da `mike_control.mode`; il codice non promuove mai a live.
11. Un ordine con esito REST IGNOTO non è mai "dato per non piazzato": la gamba diventa
    `pending_reconcile`, conta nella liability al peggior caso e viene riconciliata contro
    Betfair. *Nota — **superato l'11/09**: prima questo caso mandava la partita in ERROR con
    riconciliazione manuale; oggi la partita resta viva, si bloccano le sole APERTURE e la
    riconciliazione è automatica e throttlata (§5, §13.1 C-1, §13.2 H-2/H-8).*
12. **Nessun P&L scritto due volte**: il regolamento deduplica le righe con lo stesso
    `signal_key` (la più vecchia vince, le altre `error` con `meta.duplicate_of`) e una lettura
    fallita di `mike_trades` non vale mai "nessuna riga" (§13.1 C-1).
13. **Il void è PER MERCATO**: una linea annullata non azzera il P&L dell'altra
    (`engine.settle_legs_by_market`); `INACTIVE` non è un void (§13.1 C-4).
14. **Il "se chiudo ora" è SEMPRE netto commissione e lo calcola il servizio**
    (`live.cashout.per`): la UI non ricalcola e non mescola lordo e netto (§12 M5).
15. **Il `pnl` di ogni riga è NETTO** commissione e la somma delle righe di una partita è il suo
    `settled_pnl`; ogni chiusura porta `closes_trade_id`, quindi V/P contano i **cicli**, non le
    gambe (§12 H4).

---

## §5 Sicurezze sempre attive

| Sicurezza | Regola |
|---|---|
| Stop giornaliero | P&L della giornata operativa (Europe/Rome) = **regolato + BLOCCATO** delle partite vive piazzate oggi ≤ −50 € → nessuna partita nuova, niente ingressi, **niente ULTIMO INGRESSO (PERSIST)** né re-ingressi: SOLO chiusure. Tile rossa "STOP giornaliero ATTIVO · solo chiusure". Il bloccato di ieri non entra nello stop di oggi |
| Tetto partite | max 10 partite con POSIZIONE (WATCH e in-play senza posizione non contano) |
| Capitale per partita | `max_liability_per_match` (0 = off): blocca ingresso, copertura e re-ingresso oltre il tetto |
| Cap perdita partita | `event_loss_cap_pct`: chiude tutto a qualsiasi minuto se la perdita bloccabile lo raggiunge |
| Feed stantio | riga > 15 s E scanner muto > 30 s → nessun ingresso/re-ingresso; chiusure permesse |
| Ordine senza esito | pending > 120 s con esito ignoto → gamba `pending_reconcile` (MAI `cancelled`/`error` per TTL): conta nella liability al **peggior caso** (`engine._assume_matched`: abbinata per intero), blocca **le sole APERTURE** sulla partita (`engine._strip_openings`) mentre annulli, cash-out, uscite e cap di perdita restano attivi, attività `reconcile_pending` (critica). In paper si risolve subito (nessun ordine è mai partito); in live si riconcilia contro `listCurrentOrders`/`listClearedOrders` per `customerOrderRef` `mike-t<id>`, **con un throttle** di `max(5 s, settle_confirm_s)` per partita. Se Betfair non risponde non si ipotizza nulla (`reason=betfair_non_raggiungibile`). La lay appoggiata è esclusa: resta sul book legittimamente |
| PERSIST al KO | residuo non abbinato annullato 120 s dopo il KO |
| Processo | lock porta 47319 (una istanza), watchdog, stato riletto dal DB ad ogni ciclo |
| Bot fermo | nessun ingresso; posizioni aperte gestite fino al regolamento |

Comandi UI: **Cash out** e **Flatten** (chiudono la posizione netta al best, senza soglia; ARMATI:
prima i `cancel`, poi la chiusura guidata dall'engine), **Annulla ordini** (solo il book, le
posizioni abbinate restano), **Salta** (solo senza posizione), **Riprendi**, **Ferma bot**.
Cash out, Flatten, Annulla ordini e Salta non agiscono sugli stati terminali; **Riprendi sì**, ed è
raggiungibile anche su ERROR e SKIPPED (sezione «DA SISTEMARE» della UI, §8). Ogni comando torna
con un esito dichiarato: `done` / `rejected` (rifiuto atteso, es. feed stantio o posizione ancora
aperta) / `error`, sempre con un messaggio in italiano (§13.5).

---

## §6 Parametri (tutti editabili dalla UI, gruppo per gruppo)

Whitelist in `config.PARAM_SPEC` (default, tipo, min, max, scelte): **72 chiavi**, specchiate una
a una in `frontend/src/lib/mike.ts` (`MIKE_PARAM_FIELDS` + `MIKE_PARAM_DEFAULTS`, 72 chiavi, stessi
clamp, stesse `choices`, stessi default). Lo specchio non è una promessa: è verificato
meccanicamente da `tests/test_mike_certificazione_ui_2026_09_11.py::test_contratto_parametri_*`
— se il backend aggiunge o cambia un parametro senza dichiararlo nella UI, i test diventano rossi.
Chiavi ignote scartate (`config.merge_params`), valori fuori banda riportati nel range, coppie
min/max invertite → default. `mode` NON è un parametro: vive in `mike_control.mode`.

**Parametri RIMOSSI l'11/09/2026** (audit M3, `config.REMOVED_PARAMS`): `max_matches`,
`catalogue_refresh_s`, `stream_extra_lines`, `min_total_matched`. Erano **inerti** e la UI li
mostrava come se lavorassero. Se arrivano ancora dalla UI vengono scartati in silenzio, senza
errore. Il motivo è scritto per ognuno in `config.py` (es. `min_total_matched`: 3 ore prima del KO
lo scambiato di una linea O/U è bassissimo e il default di 2.000 € che la UI mostrava avrebbe
azzerato ogni ingresso; la liquidità che conta per un fill è quella al BEST, già governata da
`pre_min_back_size_factor`). Non vanno reintrodotti se non con default 0 = spento.

**Parametri ora CABLATI** (prima esistevano ma non facevano niente): `settle_confirm_s`
(intervallo fra due letture REST del book a mercato chiuso, minimo effettivo 5 s — governa anche
il throttle della riconciliazione degli ordini a esito ignoto), `skip_log_interval_s`
(`service._log_throttled`: dedup dei log ripetitivi per partita), `cover_max_overshoot_pct`
(tetto di sovracopertura sull'Over 4.5). Non esiste nessun `place_max_attempts`: i tentativi
sono governati da `close_retry_s` / `close_max_attempts` per le chiusure e da `pre_entry_ttl_s`
per l'ingresso.

**Generale**
| chiave | default | significato |
|---|---|---|
| stake | 10,0 (0,50–500) | importo LIBERO per gamba (anche 1,23 €): sotto-minimo via place-and-trim |
| commission_pct | 5 | commissione Betfair |
| entry_hours_before_ko | 3 | finestra pre-match (deve combaciare con `SAFE_PRE_KO_OU_HOURS`) |
| competition_filter | "" | CSV di competizioni ammesse (vuoto = tutte) |
| feed_max_age_s | 15 | età massima della riga del feed |
| decide_min_interval_ms | 500 | intervallo minimo fra due decisioni |

**Pre-match**
| chiave | default | significato |
|---|---|---|
| pre_enabled | on | |
| pre_entry_price_min / max | 1,30 / 3,00 | banda di quota dell'Under 3.5 |
| pre_min_back_size_factor | 1,0 | liquidità al best ≥ fattore × stake |
| pre_max_spread_ticks | 6 | spread massimo back/lay |
| pre_green_ticks | 2 | tick del green-up |
| pre_exit_mode | resting | resting = lay appoggiata subito; taker = chiude al best quando disponibile |
| pre_entry_ttl_s | 60 | vita dell'ordine di ingresso |
| pre_max_cycles | 10 | cicli massimi per partita |
| pre_reentry_cooldown_s | 60 | pausa dopo un green |
| pre_last_entry_min | 10 | minuti prima del KO per l'ultimo ingresso |
| last_entry_persist | on | ultimo ingresso in PERSIST |
| last_entry_ticks_above | 0 | ultimo ingresso N tick sopra il best |
| cancel_unmatched_after_ko_s | 120 | annullo del residuo PERSIST dopo il KO |

**Copertura Over 4.5**
| chiave | default | significato |
|---|---|---|
| cover_enabled | on | |
| cover_profit_factor | 1,2 | +20% di S con 5+ gol |
| cover_policy | auto | auto / immediate / wait |
| cover_wait_hazard_max | 0,06 | attende solo se hazard 3' ≤ 6% |
| cover_wait_max_min | 10 | attesa massima |
| cover_wait_p4_max | 0,16 | attende solo se P(4) mercato ≤ 16% |
| cover_good_price | 7,0 | copre subito se la quota Over è già ≥ 7 |
| cover_wait_min_gain_pct | 8 | attende solo se il risparmio atteso in N' ≥ 8% |
| cover_wait_step_min | 5 | orizzonte del risparmio (e dell'EV del cash-out) |
| cover_postgoal_delay_s | 45 | riprezzo dopo un gol |
| cover_max_goals | 2 | nessuna copertura oltre |
| cover_rounding, cover_max_overshoot_pct, exact_sizes | ceil, 30, on | legalizzazione .it solo se `exact_sizes` = off |

**Cash-out globale**
| chiave | default | significato |
|---|---|---|
| cashout_profit_pct | 5 | soglia piena |
| cashout_base | total | total = S + X; under = solo S |
| cashout_place_at_ticks | 0 | chiusura N tick oltre il best (resting) |
| cashout_smart_enabled | on | cash-out intelligente |
| cashout_smart_min_pct | 2 | profitto minimo per chiudere prima |
| cashout_smart_tolerance_pct | 2 | "a un passo" = entro N punti dalla soglia |
| cashout_smart_hazard_hot | 0,10 | fase calda: hazard 3' |
| cashout_smart_pressure_hot | 1,15 | fase calda: pressione |
| cashout_smart_goals_hot | 3 | punteggio caldo |
| cashout_smart_ev_margin_pct | 1 | margine EV lontano dalla soglia |
| close_retry_s / close_max_attempts | 10 / 20 | riprezzo del residuo di chiusura |

**Uscite HT / 2T**
| chiave | default | significato |
|---|---|---|
| loss_exit_mode | model | model / fixed |
| loss_exit_risk_premium_pct | 50 | premio al rischio (% capitale × P(4)) |
| loss_exit_p4_prudent | on | P(4) = max(modello/empirico, mercato) |
| loss_exit_max_pct | 0 | tetto "non cristallizzare oltre" (0 = off) |
| loss_exit_emp_min_n | 200 | casi minimi della tabella HT→FT |
| ht_loss_exit_enabled / ht_loss_pct | on / 25 | regola fissa all'intervallo (fallback) |
| ht_loss_goals_min / max | 2 / 4 | gol per cui vale l'uscita (HT e 2T) |
| h2_loss_exit_enabled / h2_loss_pct | on / 25 | regola fissa nel 2T (fallback) |
| h2_loss_from_min / to_min | 46 / 85 | finestra del 2T |

**Re-ingresso**
| chiave | default | significato |
|---|---|---|
| reentry_enabled | on | |
| reentry_green_ticks | 2 | |
| reentry_max_goals | 1 | 1 = linea Under 4.5 (unica nel feed) |
| reentry_until_min | 45 | gol nel 1° tempo |
| reentry_exit_until_min | 0 | 0 = mai chiusura forzata |
| reentry_price_min_over_entry | on | solo se la quota supera il primo ingresso |
| reentry_hold_if_loss | off | vale solo con una chiusura forzata impostata |

**Rischio**
| chiave | default | significato |
|---|---|---|
| max_open_matches | 10 | partite con posizione |
| daily_loss_stop | 50 | stop giornaliero (0 = off) |
| max_liability_per_match | 0 | capitale massimo per partita (0 = off) |
| event_loss_cap_pct | 100 | cap perdita partita |
| settle_confirm_s | 60 | intervallo fra due letture REST del book a mercato chiuso (minimo effettivo 5 s) |
| skip_log_interval_s | 300 | dedup dei log ripetitivi per partita (skip, no fill, linee assenti, riconciliazione) |

Variabili d'ambiente (pattern `os.getenv(X, "").strip() or default`, mai `??`): `MIKE_LOCK_PORT`
(47319), `MIKE_USE_FLUMINE_QUEUE` (0), `SAFE_PRE_KO_OU_HOURS` (3, letta sia dallo scanner sia da
Mike per il controllo di coerenza M8). L'Atlante hazard non ha una env propria di Mike: arriva da
`Betfair/stream/scalper/theta_bot.load_hazard_atlas` via `mike/dossier.load_atlas`
(nota: `MIKE_ATLAS_PATH`, citata dalle versioni precedenti di questo documento, **non esiste**).

Costanti non editabili dalla UI, ma normative: `_SETTLE_MAX_WAIT_S = 2 h` (oltre: fallback sul
punteggio del feed o ERROR), `_HEARTBEAT_MIN_S = 10 s` e `_STATS_MIN_S = 5 s` (scrittura di
`mike_control`), `db._TOTALS_TTL_S = 300 s` (cache dei cumulativi nel fallback degli aggregati),
`safe_strategy/scanner.MIKE_MAX_FOLLOWED = 10` (tetto delle partite Mike esenti dal
`scanner.OPP_MAX_EVENTS = 20` del motore opportunità — è il `max_open_matches` del bot),
`safe_strategy/service.Scanner._MIKE_FOLLOWED_TTL_S = 10 s` (cache della lista delle partite
seguite: una query leggera, mai nel percorso caldo dello stream).

---

## §7 Esecuzione e fedeltà paper

- Ordini via `safe_strategy/execution.place` (reserve-first su `mike_trades`, `client_ref`
  `mike-t<id>`): **paper** = fill sul feed al prezzo richiesto SOLO se ancora disponibile, size
  cappata alla liquidità al best; **live** = REST FOK con la sessione condivisa
  (`omega_market.place_order_live`).
- In paper e in-play il fill è DIFFERITO di `bet_delay` (dal feed) e rieseguito al prezzo
  allora disponibile: mai più ottimista del live. Una LAY appoggiata si considera abbinata solo
  quando il best back SUPERA il suo prezzo (regola stretta).
- Importi liberi: con `exact_sizes = on` la size esatta passa in paper; in live il sotto-minimo /
  fuori passo va via place-and-trim (`Betfair/stream/trading/submin.py`, come i tool pro).
- **Nessun fill simulato con feed stantio**, nemmeno per una lay appoggiata: motivo `feed_stantio`
  (§12 M7). Un fill a prezzi fantasma a scanner fermo è un profitto che non esiste.
- **In LIVE la lay appoggiata non esiste** finché non è cablata: `_params_for` forza
  `pre_exit_mode = 'taker'` e l'eventuale tentativo viene loggato come `resting_live_unsupported`
  (critico), anche con la coda flumine accesa (§12 H3, §13.3 L-3).
- Riconciliazione `listCurrentOrders`/`listClearedOrders` per `customerOrderRef` `mike-t<id>`:
  **scritta e cablata** (`service._reconcile_unknown` → `execution.reconcile_decision`, throttlata
  a `max(5 s, settle_confirm_s)` per partita), **mai provata sul campo** (§10.B.2).
- Rinviato alla fase F6 (live): `persistence` PERSIST su `place_order_live`; cancel/replace REST
  per il sotto-minimo; lay appoggiata in live (REST senza FOK) o coda flumine
  (`MIKE_USE_FLUMINE_QUEUE=1`).

---

## §8 La UI (`/mike`) e come leggerla

La pagina rispetta il **design system unico dei tre bot** (`frontend/src/components/trading/DESIGN_SYSTEM.md`):
nessun formatter locale (solo `lib/format.ts`: `fmtMoney` → `12,50 €`, `fmtOdds` → `2,04`,
`fmtPct` su frazione 0–1, `fmtTime` sempre Europe/Rome, `−` = U+2212 unico meno ammesso, il `+`
solo con `{signed:true}` su P&L e delta), nessuna mappa di stati locale (`statusMeta`,
`botStatusMeta`, `sideMeta`, `activityMeta`, glossario `T` da `lib/tradeStatus.ts`), nessun
componente doppione, tutto in italiano, colori per ruolo (BACK sky · LAY rose · favorevole
emerald · sfavorevole red · chiusura/green teal · attesa amber · liability `orange-400`),
**accento di Mike = `text-teal-300`**.

### Struttura (una sola, identica a Omega e Safe)

```
PageShell  (titolo "Mike | Alpha Score", footer: fonte dati = feed unico, paper-first)
 └ BotHeader   bot="mike" · badge stato · ServiceHealthChip · ModeToggle PAPER/LIVE · Parametri · Avvia/Ferma
 └ ModeBanner  paper: "simulazione fedele…" · live: "soldi veri" · migrationWarning
 └ DayBar      giornata operativa (Europe/Rome) con V/P, partite, operazioni, live, liability, bloccato
 └ KpiRow      7 StatTile
 └ Tabs        TabsList sticky, top = navH misurato da BotHeader.onHeight (l'header va a capo su mobile)
 └ LiveConfirmDialog
```

**Stato del bot** (`botStatusWithBeat`, prefisso `BOT`): INATTIVO / IN CORSA / IN ARRESTO / FERMO /
ERRORE. Se è `running` ma il battito manca o è più vecchio di **45 s** il badge diventa rosso
**"IN CORSA · SENZA BATTITO"** con `data-stale="true"` e il tooltip dice cosa fare
(«il servizio non batte da …: riavvia l'app desktop»). La stessa verità è ripetuta nella tile
**Ultimo ciclo**, che in quel caso scrive «servizio senza battito: riavvia l'app desktop».
Un bot in corsa che non batte è un bot che NON sta lavorando: la UI non lo nasconde mai.

**Le 7 tile**: Partite seguite (`N pre-match · N live · N con posizione`) · Posizioni aperte
(`N in verifica su Betfair` in fuchsia se ci sono ordini a esito ignoto) · P&L oggi
(`giornata operativa <data> · Europe/Rome`) · P&L totale · **Liability aperta** (sub: `STOP
giornaliero ATTIVO · solo chiusure`, oppure `stimata dalle righe` in ambra quando
`aggregates.liability_source = 'rows_sum'`, `· di cui N in verifica`, `· dato stantio` se
`liability_stale`) · **P&L bloccato** · Ultimo ciclo. I numeri vengono dagli `aggregates` della
RPC e **non vengono mai ricontati dal client** quando la RPC li porta.

**Le 5 schede** (ordine ed emoji sono contratto del design system):
`⚽ Partite (N)` · `📋 Trade (N)` · `🧾 Attività` · `✅ Regolate (N)` · `📅 Storico`.

### Scheda Partite — tre sezioni FISSE, mai in movimento

```
⏱ PRE-MATCH (N)    · per calcio d'inizio       (sempre montata, anche vuota)
🔴 LIVE (N)        · in gioco                  (sempre montata, anche vuota)
⚠️ DA SISTEMARE (N) · partite in errore o saltate: serve una mano   (solo se N > 0)
```

- **Ordine**: `lib/mike.ts::splitMikeEvents` → `compareByKickoff` = **calcio d'inizio crescente e,
  a pari KO, `event_id`**. Mai la fase, mai lo stato: la fase cambia a ogni ciclo del servizio e
  faceva saltare le schede di posto. KO assente o illeggibile va in fondo.
- **PRE → LIVE è una sola direzione**: una partita passa in LIVE al primo `live.inplay === true`
  (`isEventLive`) e non torna più indietro, perché la pagina tiene una memoria sticky
  (`liveSeen` ref + `rememberLive`). Un buco di feed non fa rimbalzare la card fra le sezioni.
- **DA SISTEMARE** esiste perché ERROR e SKIPPED prima erano invisibili e il bottone "Riprendi"
  irraggiungibile (audit H6): `needsAttention(ev)` = `ERROR` ∨ `SKIPPED` ∨ `ev.skipped`.
- **Card memoizzate**: `MikeMatchCard = memo(...)` con comparatore esplicito su
  `event_id`, **`updated_at`**, `state`, identità di `params`, `mode`, `busy`, `stale`,
  `lastRequest.{id,status}`, `pendingKinds`, mercati void, `onRequest`. **Il tempo non è fra le
  props**: l'orologio vive solo nelle foglie (`useMikeClock`, tick 1 s), così il countdown scorre
  senza ridisegnare la card. L'identità di `params` è stabile (`paramsKey` + `paramsRef` in
  `useMike`): parametri uguali = stesso riferimento = nessun ridisegno.
- **Altezza fissa, niente salti**: ogni zona della card ha un `min-h-` e **resta montata anche
  senza dati**, con `—` (o `–` per il punteggio). Una zona che appare e sparisce fa ballare la
  pagina: qui non succede.
- **Ricariche**: canale realtime unico `mike-live` su `MIKE_REALTIME_TABLES = mike_control,
  mike_events, mike_trades, mike_activity, mike_requests`; N notifiche ravvicinate = **UNA**
  ricarica (`RELOAD_DEBOUNCE_MS = 1.500 ms`), più un poll di sicurezza a 15 s. Il **battito è
  filtrato**: `isHeartbeatOnlyChange` + `controlSignature` scartano le notifiche di `mike_control`
  che cambiano solo `heartbeat_at`, `updated_at`, `stats.last_cycle`, `stats.scanner_age_s`.
- Vuoto globale: «Nessuna partita seguita. Con il bot in corsa, le partite con calcio d'inizio
  entro {entry_hours_before_ko} ore e le linee 3.5/4.5 nel feed compaiono qui.»

### Le zone della card, nell'ordine

Bordo sinistro per gruppo di fase: **teal** pre-match · **viola** live · **verde** flat ·
bianco tenue regolate · **rosso** ERROR/SKIPPED.

1. **Header** — punteggio grande (`0–1`, en-dash; `–` se assente) con la riga espulsioni
   `🟥 casa/trasferta`; nome partita e competizione; poi, secondo il caso: in play
   `· 34′ · 2 gol · intervallo · 1T 1–1`; pre-match `· KO 20:45 · fra 1h 12m`; terminale
   `· KO 20:45 · 3 gol totali · regolata`. Badge di **fase** (19 etichette, tabella sotto) e badge
   di **freschezza del feed DI QUESTA PARTITA** (`live.feed_age_s`): `feed 3 s` verde fino a 5 s,
   `feed 12 s` ambra fino a 20 s, **`FEED FERMO (34 s)`** rosso oltre, **`FEED: NESSUN DATO`** se
   il servizio non ha pubblicato l'età. Se il calcio d'inizio è passato ma il feed non dice ancora
   `inplay`, la card resta in PRE-MATCH e lo dichiara in ambra: **«in attesa del fischio»**
   (`MIKE_AWAITING_KICKOFF_NOTE`) invece di un «fra —» che sembra un guasto.
2. **Allarmi** (riga sempre presente) — banner rosso `role="alert"` «linea Over 4.5 assente nel
   feed: nessuna copertura e nessun cash out possibile»; badge `CHIUSURA IN CORSA`
   (`ctx.flatten_pending`), `VOID · mercato annullato` oppure `VOID (linea 3.5)` **per mercato**,
   `ORDINE IN VERIFICA SU BETFAIR` (`live.reconcile_pending`), `NESSUN RIENTRO`
   (`ctx.no_reentry` ∨ `live.no_reentry`), `SOLDI VERI` se la partita è in modalità live.
3. **Quadro modello** — P(4 gol) modello · P(4 gol) mercato · in play `Hazard gol 3′` (con
   `atl … · mod …`) / pre-match `P(Over 4.5) modello` · in play `Pressione ×1,18 🔥` (🔥 oltre
   `cashout_smart_pressure_hot`) / pre-match `λ casa / trasferta`.
4. **Istogramma P(totale gol) 0…8** — 9 barre da `live.p_total_model` (etichetta `modello`) o
   `live.p_total_emp` (`empirico`), e **«nessun modello per questa partita»** quando non c'è nulla
   (è il caso del ponte evento→fixture vuoto, §10.1). La barra **4 è rossa**: è l'unica casella
   che perde.
5. **Le tre linee** (sempre tutte e tre, anche assenti) — `Under 3.5`, `Over 4.5`,
   `Under 4.5 (re-ingresso)`: best back / best lay con le **size**, la **variazione dal tick
   precedente** (`▲`/`▼`/`·`, di colore **neutro** di proposito: salita e discesa non sono buone o
   cattive in sé, dipendono dal lato), il `betDelay N s` e lo **stato del mercato in italiano** —
   `OPEN` non si scrive, `SUSPENDED` → **SOSPESO** (ambra), `CLOSED` → **CHIUSO** (rosso),
   `INACTIVE` → **NON ATTIVO** (rosso), ignoto → il codice con gli underscore sciolti, in ambra.
   Tooltip con `market_id` e `selection_id`.
6. **Riga meta** — `scambiato …` · `primo ingresso …` · `ciclo N` · `regolato …`.
7. **Posizioni** — colonne `Posizione · Ingresso · Quota ora · Δ ingresso · Se chiudo ora`.
   Lato netto (BACK sky / LAY rose), euro abbinati e `(+… sul book)`, ruoli tradotti, e i marcatori
   `· IN VERIFICA`, `· esito già deciso`, `· VOID (linea …)`. **Δ ingresso** è in **tick**
   (`ticksBetween` sul prezzo con cui si chiuderebbe: netta BACK → best lay, netta LAY → best
   back), emerald se a favore, rosso se contro, `= 0 tick` grigio. **«Se chiudo ora» viene SOLO
   dal servizio** (`live.cashout.per[...]`, NETTO commissione, M5): se il servizio non l'ha
   pubblicato la cella dice `—` e lo spiega nel tooltip — la UI non ricalcola un netto per conto
   suo e non mescola lordo e netto.
8. **Ordini sul book** — solo gambe vive con residuo: ruolo, linea, `€ residuo @ quota`, stato
   (`SUL BOOK`, `SUL BOOK (parziale)`, `IN VERIFICA`, `· PERSIST`, `· abbinati …`) e la distanza
   dal best: `al best` (verde), `N tick sopra/sotto il best` (ambra), `distanza dal best: —`.
9. **P&L a fine gara per gol totali** — una cella per totale (l'ultima come `5+`), la cella **4 in
   rosso** con il tooltip «i 4 gol: l'unico esito che perde» e i **gol attuali cerchiati**. Sotto:
   **`Liability aperta`** (netta, `live.liability`) in arancio e **`P&L bloccato`** firmato.
10. **Cash out** — valore netto firmato con `(% · soglia %)`, oppure `prezzi incompleti` /
    `nessuna posizione`; barra `role="progressbar"` verso la soglia; riga **intelligente**
    (`min … · a un passo dal 5% · fase calda · aspettare vale … · → chiude (trigger)`); riga
    **uscita a modello** (`tenere vale … · P(4) … · premio … · → chiude/tiene`, o
    `modello senza dati → regola fissa`); riga **copertura** (`attende quota migliore · risparmio
    atteso … · hazard … · al massimo fino al N′`).
11. **Esito dell'ultima richiesta** — riga in italiano da `requestOutcome`, mai un codice nudo
    (M1): `Cash out in corso…` (grigio) · `Cash out rifiutato: feed stantio` (ambra) ·
    `Cash out in errore: …` (rosso) · **`Cash out armato: annullati 2 ordini sul book · chiusura
    in corso · netto stimato +0,47 €`** (verde) quando il servizio risponde `result.phase='armed'`.
12. **Azioni** — `Cash out <netto>` · **`Annulla ordini`** (solo ordini sul book, le posizioni
    abbinate restano) · **`Flatten`** (chiude tutto a mercato senza guardare la soglia) ·
    **`Salta`** (solo senza posizione) · **`Riprendi`** (visibile anche negli stati terminali e
    quando il rientro è disabilitato: è il motivo per cui esiste la sezione DA SISTEMARE).
    Ogni bottone spento **dice perché**, in quest'ordine di precedenza: chiusura manuale già in
    corso · operazione in corso · feed stantio (scanner fermo) · feed di questa partita fermo ·
    linea assente nel feed · nessuna posizione aperta.

**Cash out — dialog, breakdown, doppia conferma** (`MikeCashOutButton`): il bottone spento mostra
il motivo **in chiaro accanto a sé**, non solo nel tooltip. Il dialog dichiara che «la chiusura è
intera: Mike non accetta cash out parziali», mostra il **P&L bloccato chiudendo ora (netto
commissione, dal servizio)** con `% della base` e `soglia automatica`, e un **breakdown una riga
per selezione netta** preso da `cashout.per` (mai ricalcolato). In **LIVE** compare la riga rossa
«MODALITÀ LIVE: soldi veri» e la conferma è **doppia**: il primo click arma, il bottone diventa
**«Confermi? soldi veri»**, e l'armamento **decade da solo dopo 10 s** e si azzera ogni volta che
il netto cambia — non si conferma mai su un numero vecchio.

### Fasi (19 stati, `MIKE_PHASE_META`)

IN ATTESA · INGRESSO… · UNDER APERTO (PRE) · GREEN-UP… · HOLD → LIVE · ULTIMO INGRESSO (PERSIST) ·
LIVE · NESSUNA POSIZIONE · LIVE · SCOPERTO · COPERTURA… · LIVE · COPERTO · CHIUSURA… · FLAT ·
RE-INGRESSO… · RE-INGRESSO U4.5 · GREEN RE-INGRESSO… · REGOLAMENTO… · REGOLATA · ERRORE · SALTATA.

### Scheda Trade

Righe di `mike_trades` della **giornata operativa** (toggle `solo oggi` / `mostra tutte`), con le
**chiusure ANNIDATE sotto la loro apertura** (`closes_trade_id`): la riga figlia è prefissata da
`↳`, colonna Partita = `chiusura`, e il **P&L netto della riga di apertura è quello del CICLO**
(apertura + chiusure regolate). Una chiusura la cui apertura non è fra le righe caricate non viene
nascosta: diventa un gruppo a sé marcato **`orfana`**. Colonne: `Ora · Partita · Gamba · Lato ·
Quota · Size · Stato · Uscita · P&L netto`.
Marcatori: **`✋`** davanti alla gamba quando la riga nasce da un comando dell'utente
(`origin='manual'` ∨ `role='manual_close'` ∨ `meta.exit_kind='manual'`); **VOID per mercato** scritto
come `VOID (Under 3.5)` — mai «partita annullata» quando è saltata una sola linea; `LIVE` in rosso
sulle righe in modalità live; `IN VERIFICA` sulle `pending` con `meta.reason =
place_exception_reconciling`. Le righe ancora aperte hanno il link **«→ scheda partita»** che porta
alla scheda Partite e illumina la card per 2 s (il cash out si fa dalla card, non dalla tabella).
Nota in ambra quando la RPC tronca: **`mostrate le ultime 500 righe (tetto della RPC)`**
(`MIKE_TRADES_LIMIT = 500`). Sotto la tabella la **equity curve** della giornata operativa
(`mikeEquitySeries`: gradini sul momento di regolamento, P&L netto cumulato; a giornata vuota
«nessun trade ancora regolato oggi — la curva compare al primo incasso»).

### Scheda Regolate

Le partite `SETTLED`/`SETTLING` della giornata operativa, come card in **sola lettura** (nessun
comando): mercato chiuso, esito dichiarato da Betfair, P&L definitivo. Vuota:
«Nessuna partita regolata nella giornata operativa.»

### Scheda Attività

`ActivityFeed` **filtrabile** con l'ora ai secondi, una riga per evento del servizio, in italiano:
ogni `kind` ha la sua resa (`mikeActivityLine`) e i tre kind **critici** sono rossi
(`reconcile_pending` → ORDINE IN VERIFICA, `feed_line_missing` → LINEA ASSENTE NEL FEED,
`resting_live_unsupported` → APPOGGIATA NON SUPPORTATA IN LIVE). Nessun JSON nudo: un kind
sconosciuto ricade sui campi comuni del payload (`reason`/`err`/`note`/`message`).

### Scheda Storico

`TradingHistory variant="mike"`: calendario giornaliero dalle RPC `get_mike_daily` /
`get_mike_day_trades`. Se le RPC sono ambigue o assenti l'errore è **leggibile**:
«storico Mike: applica `migrations/mike_history_v2.sql` (…)» invece del codice nudo `42725`.

### Parametri

`MikeParamsSheet` è costruito su **`ParamsSheetBase`** (lo stesso pannello di Omega e Safe):
7 gruppi (Generale · Pre-match · Copertura Over 4.5 · Cash-out globale · Uscite HT / 2T ·
Re-ingresso · Rischio), clamp **dichiarato** accanto al campo, pallino "modifiche non salvate",
bottone `Default`, **un solo** bottone `Salva parametri`, e il promemoria che la modalità
PAPER/LIVE **non è un parametro**: si cambia solo dal toggle in alto, con conferma.

---

## §9 Operatività

- Migrazioni (manuali, in ordine): `migrations/mike_bot.sql`, `migrations/mike_history.sql`
  (applicate), poi **`migrations/mike_bot_v2.sql`** e **`migrations/mike_history_v2.sql`**
  (⚠️ **DA APPLICARE**, in quest'ordine, dopo `omega_daily_v2.sql` e `omega_models_v4.sql` che sul
  DB reale risultano già applicate — la sequenza completa e il "cosa succede se non la applico"
  stanno in `migrations/APPLY_ORDER_2026-09-11.md`, dove Mike viene prima di
  `safe_strategy_bot_v2.sql` e `omega_models_v5.sql`).
  - `mike_bot_v2.sql`: colonne difensive (`mike_trades.closes_trade_id`, `mike_requests.result`),
    stato `'rejected'` sulle richieste, `mike_aggregates_sql()`/`get_mike_aggregates()` (KPI in una
    sola scansione, liability NETTA con fonte dichiarata), `get_mike_state()` con `requests[]`,
    `aggregates`, `day_start`, `day_by` e il tetto `LIMIT 500` sui trade.
  - `mike_history_v2.sql`: **DROP** delle firme vecchie a 7/3 argomenti di
    `trading_daily_history`/`trading_day_trades` rimesse da `mike_history.sql` e `CREATE OR
    REPLACE` di quelle a 8/4 argomenti con `'mike_trades'` in whitelist, clamp a 400 giorni,
    `hedged_closed`/`commission_paid` corrette, predicato `is_placed` allineato ai KPI,
    `get_mike_daily`/`get_mike_day_trades` con tutti gli argomenti e `p_day_by='placed'`.
- Env: `SAFE_PRE_KO_OU_HOURS=3` nel `.env` (lo scanner pubblica le linee pre-match).
- L'exe è l'avviatore del `main.js` vivo: dopo una modifica al codice si RIAVVIA l'app (mai
  ricompilare). Il servizio `mike-service` parte con l'app sotto watchdog; il bot lavora solo
  dopo "Avvia" in `/mike` (stato `running` in `mike_control`).
- Test (numeri verificati il 12/09/2026):
  - `python -m pytest Betfair/mike -q` → **232** test raccolti (era 108): `test_mike_engine` 55,
    `test_mike_audit_2026_09_11` 57, `test_mike_review_2026_09_11` 36,
    `test_mike_certificazione_ui_2026_09_11` 39, `test_mike_service` 16, `test_mike_dossier` 11,
    `test_mike_config` 10, `test_mike_feed` 6.
  - Suite dei tre bot: `python -m pytest Betfair/mike Betfair/omega Betfair/safe_strategy -q`
    → **1254** test raccolti (Mike non rompe Omega né Safe).
  - Frontend Mike: `cd frontend && npx vitest run src/lib/mike.test.ts src/pages/Mike.test.tsx
    src/components/mike` → **128** test (46 `lib/mike`, 27 `pages/Mike`, 24 `MikeMatchCard`,
    14 `MikeTradesTable`, 13 `MikeCashOutButton`, 4 `MikeParamsSheet`) + **10** di certificazione
    → oltre 137 in totale. `npx tsc --noEmit -p .` e `npm run build` devono restare puliti.
  - **Certificazione sui DATI REALI** (letture, service role, realtime stubbato):
    `cd frontend && npx vitest run --config vitest.cert.config.ts`. Gira solo
    `src/certification/**/*.cert.test.*` (`mike.cert.test.tsx`: forma della RPC e ripieghi, render
    senza crash e senza `console.error`, KPI e DayBar = valori della RPC, conteggi e ordine delle
    tre sezioni, quote e posizioni di ogni card, attività/Trade/Storico). I file `.cert.test.*` si
    **auto-saltano** con `npm test`: il DB reale non si interroga per sbaglio.
- Diagnosi rapida: `select * from mike_control` (stats: `by_state`, `daily_stop`, `scanner_age_s`,
  `reconciling`, `locked_open`, `day_pnl`), `mike_events` (`state`, `positions`, `live`,
  `ctx.last_reason`, `ctx.flatten_pending`, `ctx.no_reentry`), `mike_activity`,
  `select public.get_mike_aggregates()`, `select jsonb_object_keys(public.get_mike_state())`.

---

## §10 Limiti noti e cose da fare

### 10.A Bloccanti — da fare adesso, nell'ordine

1. **Applicare le due migrazioni**: `migrations/mike_bot_v2.sql` poi `migrations/mike_history_v2.sql`
   (§9, `migrations/APPLY_ORDER_2026-09-11.md`). **Senza la seconda lo storico di Mike è ROTTO**:
   ogni chiamata a `trading_daily_history`/`trading_day_trades` con meno di 8/4 argomenti fallisce
   con `42725 is not unique` (verificato sul DB reale l'11/09) e la scheda Storico resta vuota —
   la UI almeno lo dice a parole («storico Mike: applica `migrations/mike_history_v2.sql`»).
   Senza la prima: nessun `get_mike_aggregates` (`PGRST202`), nessun `requests[]`/`day_start` nel
   payload, i rifiuti restano `'error'` invece di `'rejected'`, la giornata operativa la stima il
   client (`romeDayStartMs`) e la V/P la conta il client (`dayResultCounts`) — la UI **dichiara**
   ognuno di questi ripieghi, ma sono ripieghi.
2. **Riavviare i servizi** (riavvio dell'app, mai ricompilare l'exe). Al riavvio: parte la
   riconciliazione `mike_trades` ↔ `positions` a ogni ciclo (H2) e il servizio inizia a pubblicare
   `mike_events.live.liability` — finché non riparte, `aggregates.liability_source` resta
   `rows_sum` e la tile "Liability aperta" scrive `stimata dalle righe` in ambra.
3. **Paper ≥ 40 partite complete** sul codice nuovo, poi il verdetto scritto in §0 con i numeri.
   Nessun GO al live prima.

### 10.B Rischi residui (noti, verificati nel codice, NON risolti)

1. **Mercato rimosso / illeggibile → attesa di 2 ore per EVENTO, non per mercato.**
   `service._SETTLE_MAX_WAIT_S = 2 h` è un orologio unico per partita, fissato al primo giro a
   mercato chiuso (`extra["settle_first_ts"]`): non esiste un timeout per singolo mercato né una
   regolazione parziale per timeout. Scaduto: se il feed aveva visto l'in-play si usa l'ultimo
   punteggio noto (`settle_fallback`), altrimenti la partita va in **ERROR** con
   `reason=settle_timeout` e le sue righe `mike_trades` restano `open`/`pending` (contano ancora
   in `open_count` e nella liability delle righe).
   Sottocaso da tenere d'occhio: il ramo void-per-mercato (`settle_plan` +
   `settle_legs_by_market`) gira solo quando `final_total_from_books` non riesce a dedurre un
   totale. Se la 3.5 dichiara UNDER (totale dedotto = 3) e la 4.5 è **annullata**, si passa dalla
   strada normale e la 4.5 viene regolata come UNDER invece di essere trattata void: il fix C-4
   non copre questa combinazione.
2. **La riconciliazione live non è mai stata provata sul campo.** Il percorso
   `_reconcile_unknown` → `execution.reconcile_decision` contro `listCurrentOrders`/
   `listClearedOrders` per `customerOrderRef` `mike-t<id>` è scritto e testato con dei doppi, mai
   eseguito contro Betfair. In paper si risolve subito (nessun ordine è mai partito).
3. **`realized_total` cachato 5 minuti quando la migrazione non c'è.** Nel fallback degli
   aggregati (`db.aggregates`) i cumulativi di sempre (`realized_total`, `won`, `lost`) arrivano da
   `db._cumulative_totals`, in cache `_TOTALS_TTL_S = 300 s`, mentre `realized_today`,
   `open_count` e la liability sono freschi: per qualche minuto i KPI possono essere incoerenti
   fra loro. Inoltre `_AGG_RPC["missing"]` è un **latch di processo**: appena la RPC risulta
   assente non viene più ritentata fino al riavvio del servizio — applicata la migrazione, il
   servizio va riavviato. E `agg["totals_from"] = "full_scan_cache"` **non** viene propagato in
   `stats` né nel payload: la UI non può dichiarare che quel numero è cachato (a differenza di
   `liability_source`/`liability_stale`, che invece espone).
4. **`is_placed` ha due definizioni.** In `mike_bot_v2.sql` è
   `bet_id IS NOT NULL OR meta->>'flumine_client_ref' IS NOT NULL` (con `reconciling` come colonna
   separata); in `mike_history_v2.sql` include direttamente
   `meta->>'reason' = 'place_exception_reconciling'`. Su righe piazzate senza `bet_id` né
   `flumine_client_ref` i KPI e lo storico possono divergere.
5. **`_insert_trade_row`, secondo tentativo non protetto.** Il ripiego senza `closes_trade_id`
   (colonna assente) fa un secondo `insert_trade` che, se va a buon fine ma risponde in timeout,
   può lasciare una riga doppia. Mitigato a valle dal dedup per `signal_key` del regolamento
   (C-1), quindi il P&L non raddoppia, ma la riga doppia esiste fino al regolamento.

### 10.C Limiti di modello e funzionalità mancanti

1. **Ponte evento→fixture** sulle leghe minori: dossier vuoto (`source: none`) → niente λ, niente
   hazard/P(4) di modello, niente EV per cash-out e uscite. Effetto: copertura immediata e regola
   fissa; nella card l'istogramma dice **«nessun modello per questa partita»**. Da sistemare per
   primo dopo le prime partite paper.
2. Live (F6): PERSIST reale su `place_order_live`, sotto-minimo via cancel/replace REST, **lay
   appoggiata in live** (oggi in live `pre_exit_mode` è forzato a `taker`: una resting non
   esiste finché non è cablata, e il tentativo viene loggato come
   `resting_live_unsupported`, critico).
3. Re-ingresso oltre la linea 4.5 (2+ gol) richiede una linea extra nel feed: non implementato
   (il parametro `stream_extra_lines` era inerte ed è stato **rimosso** dalla whitelist).
4. Manca una tabella di frequenza "4 gol esatti" per lega; oggi la P(4) viene da griglia, empirico
   HT→FT e mercato.
5. Gate F5: certificazione paper (n ≥ 40) + backtest REC; il verdetto va scritto in §0.

---

## §11 Cosa Mike NON fa

- Non entra mai in-play "da zero": l'unico ingresso live è il re-ingresso dopo un profitto e dopo un gol.
- Non apre posizioni a bot fermo o con stop giornaliero attivo (chiusure e regolamento restano attivi).
- Non chiude in perdita fuori dalle regole HT/2T (a modello o fisse) e dal cap di perdita evento.
- Non opera linee non presenti nel feed.
- Non fa chiamate Betfair per i dati e non ha un login proprio (le sole chiamate REST sono il book
  a mercato chiuso e la riconciliazione degli ordini, entrambe throttlate).
- Non passa mai a LIVE da solo.
- Non arma una partita **già in gioco** (§3, Fase 7).
- Non inventa prezzi: linea assente nel feed → `feed_line_missing` (critica) e cash out rifiutato
  con `feed_assente`, mai un numero al posto di un prezzo.
- Non chiude un ciclo su cui c'è ancora una posizione viva senza prezzo: **aspetta** (§13.1 C-2).
- Non rientra dopo un cash out manuale pre-KO finché l'utente non preme **Riprendi** (§13.1 C-3).
- Non mostra un numero senza dire da dove viene: liability stimata dalle righe, giornata o V/P
  calcolati dal client, battito assente — la UI lo **dichiara** sempre (§13.4).

---

## §12 Audit 11/09/2026 (sera) — correzioni applicate al backend

Riferimento: `Betfair/AUDIT_2026-09-11_omega_safe_mike.md`, sezione 1 (MIKE) + sezione 4 (storico).
Numerazione **dell'audit**: C1–C3, H1–H6, M1–M10, L1–L5. La **review indipendente** che è venuta
dopo ha una numerazione propria (C-1…C-5, H-1…H-8, M-1…M-9, L-1…L-3) e sta nel §13: le due liste
non vanno confuse. Tutto quanto segue è pushato con `9d09c81`.

| Item | Regola che ora vale |
|---|---|
| C1 | Le linee di una partita SEGUITA restano nel feed: lo scanner ha `select_opp_candidates(followed=…)` (partite Mike esenti dal tetto dei 20 eventi) e `is_opp_market_live(..., mike=True)`. Se una linea manca comunque, Mike NON inventa prezzi: attività `feed_line_missing` (critica) e `live.lines_missing` sulla card |
| C2 | Dopo il 4° gol la partita NON si congela: una selezione con esito già deciso vale 0/1 SENZA prezzo (`engine.selection_decided`), `complete=true` se tutte le selezioni VIVE hanno prezzo, il cash out agisce sulle sole gambe vive e una chiusura in attesa su una selezione decisa viene annullata |
| C3 | Esito ordine IGNOTO → gamba `pending_reconcile`: mai `cancelled`/`error` per TTL, conta nella liability al peggior caso, blocca i nuovi ingressi, attività `reconcile_pending` / `reconcile_fix` |
| H1 | Cash out manuale: PRIMA i cancel (attesa conferma), POI la chiusura della posizione netta; il contesto NON viene azzerato; pre-KO il ciclo è chiuso E `no_reentry=true` (solo "Riprendi" riabilita il rientro); con feed stantio la richiesta viene RIFIUTATA |
| H2 | Riconciliazione `mike_trades` ↔ `positions` a OGNI ciclo: gamba senza riga → riga ricostruita, riga senza gamba → `meta.orphan` (in live mai chiusa in silenzio) |
| H3 | In LIVE la lay appoggiata NON esiste (finché non è cablata): `pre_exit_mode` forzato a `taker`, nessun fill simulato con o senza coda flumine |
| H4 | `pnl` di ogni riga NETTO commissione (somma righe = `settled_pnl`); ogni chiusura porta `closes_trade_id` + `meta.exit_kind` ∈ {greenup, profit, loss, time, forced, manual, other} + `meta.exit_reason`; lo storico conta i CICLI |
| H5 | Log `state` solo al cambio di stato, battito su `mike_control` al massimo ogni 10 s (`_HEARTBEAT_MIN_S`, stats ogni 5 s solo se qualcosa è cambiato), righe della partita lette UNA volta per ciclo (`_event_rows` + `trades_cache` di `run_once`), `_open_refs_by_event` in una query, lettura incrementale di `mike_trades` (`db.live_trades`) e aggregati via RPC SQL |
| H6 | Le partite **ERROR** e **SKIPPED** non sono più invisibili in UI: sezione fissa «⚠️ DA SISTEMARE» nella scheda Partite (`lib/mike.ts::needsAttention` + `splitMikeEvents`), con il bottone **Riprendi** raggiungibile anche negli stati terminali |
| M1 | Ogni richiesta chiusa con `status` ∈ {done, rejected, error} e `result` = {code, message in italiano} |
| M2 | `fail_stale_processing` a ogni ciclo |
| M3 | Rimossi (inerti): `max_matches`, `catalogue_refresh_s`, `stream_extra_lines`, `min_total_matched`; cablati: `settle_confirm_s`, `skip_log_interval_s`, `cover_max_overshoot_pct`. `catalogue.py` (codice morto) rimosso |
| M4 | "Capitale a rischio" = liability delle posizioni NETTE (`engine.event_liability`), non la somma delle gambe |
| M5 | "Se chiudo ora" SEMPRE netto commissione lato servizio: `live.cashout.{net, gross, base, per, per_gross, decided, complete, commission, pct, target_pct}` |
| M6 | Giornata operativa = giorno di PIAZZAMENTO (Europe/Rome) per KPI, regolate e storico |
| M7 | In paper nessun fill (anche resting) con feed stantio: motivo `feed_stantio` |
| M8 | All'avvio, `entry_hours_before_ko` > ramo pre-KO dello scanner (o ramo spento) → attività `config_warn` |
| M9 | Mercato VOID/abbandonato riconosciuto da `service.market_voided` → gambe di QUEL mercato `void` e partita `SETTLED` con il motivo. ⚠️ **superato dalla review (§13 C-4)**: il void è PER MERCATO, quindi `settled_pnl = 0` **solo se sono annullati tutti e due** i mercati; con una sola linea annullata l'altra viene regolata normalmente e il P&L reale resta |
| M10/R2 | `migrations/mike_history_v2.sql`: una sola firma delle funzioni condivise (8/4 argomenti) con `mike_trades` ammessa; `get_mike_daily`/`get_mike_day_trades` passano tutti gli argomenti con `p_day_by='placed'` |
| L1..L5 | `customerStrategyRef` = `mike` sugli ordini live (`config.CUSTOMER_STRATEGY_REF`); stop giornaliero per giorno di Roma (`_operating_day_key`) e comprensivo del P&L BLOCCATO; partite già in gioco non armate (`feed.is_candidate` ritorna `False` in-play); tutti i `kind` di attività dichiarati alla UI e verificati da un test |

> Nota — l'esenzione delle partite Mike dal tetto dello scanner (C1) è stata **ristretta dalla
> review**: solo le partite con ESPOSIZIONE reale sono esenti, al massimo 10, e portano nel pool
> le sole linee 3.5/4.5. Vedi §13 H-4/H-5/H-6/H-7.

---

## §13 REVIEW E CERTIFICAZIONE 11/09 sera (pushato `9d09c81`)

Dopo l'audit del §12 il codice è passato a una **review indipendente** che ha trovato altri
5 CRITICAL e 8 HIGH (più M-1…M-9 e L-1…L-3), tutti corretti; poi a una **certificazione del
contratto UI↔servizio** fatta a macchina (`tests/test_mike_certificazione_ui_2026_09_11.py`, 39
test che leggono direttamente `frontend/src/lib/mike.ts` e le migrazioni: se il backend aggiunge un
parametro, un `kind`, uno stato, un ruolo o un codice di esito senza dichiararlo nella UI, QUESTI
TEST FALLISCONO); infine a una **certificazione sui dati reali** del DB
(`frontend/src/certification/`, `npx vitest run --config vitest.cert.config.ts`). Un test per ogni
finding sta in `tests/test_mike_review_2026_09_11.py` (36 test).

### 13.1 I 5 CRITICAL della review

| # | Cosa andava storto | Regola che ora vale |
|---|---|---|
| **C-1** | Una lettura FALLITA di `mike_trades` valeva "nessuna riga": la riconciliazione REINSERIVA una riga per ogni gamba abbinata → righe doppie con lo stesso `signal_key`, P&L e stop giornaliero **raddoppiati** | `service._event_rows` ritorna **`None` = lettura fallita** e **non mette mai `[]` in cache** (la cache è il dizionario `trades_cache` creato in `run_once`: vive UN ciclo, non ha TTL, e `_reconcile_unknown` la invalida per evento dopo una correzione). Con `rows is None` non si ripara nulla: attività `reconcile_pending` con `reason=righe_illeggibili`, `critical=true`, e si riprova al ciclo dopo. In più il regolamento **deduplica per `signal_key`** (`service._settle_trades`, dove `signal_key = leg.ref`): vince la riga con l'`id` più basso, le altre vanno `status='error'`, `pnl=0`, `meta.duplicate_of` + attività `error` con `reason=duplicate_signal_key`. Garanzia: somma dei `pnl` delle righe = `settled_pnl` |
| **C-2** | Il cash out manuale pre-KO con la lay di green-up **appoggiata** (default `pre_exit_mode=resting`) era un loop: il servizio la cancellava e il ciclo dopo la **riappoggiava**, senza mai chiudere | Il flatten è **ARMATO dall'engine**: `service._request_flatten` non chiude più da sé, mette `ctx.flatten_pending = True` (+ `no_reentry` se pre-KO) e `engine.decide` ci fa cortocircuito su **`engine._decide_flatten`** prima di qualunque dispatch → nessuna riappoggiata. Ordine obbligato: (1) `cancel` degli ordini vivi, (2) chiusura della posizione netta delle sole selezioni VIVE con ruolo `manual_close` (`engine.MANUAL_ROLE_MAP`), (3) chiusura del ciclo. `engine.force_flat_plan` ritorna **cancel e close SEPARATI** proprio perché vanno in quest'ordine. Se la posizione è viva ma **non c'è prezzo per chiuderla si ASPETTA**: chiudere il ciclo lì archivierebbe una posizione aperta (capitale a rischio invisibile). `flatten_pending` e `no_reentry` sono persistiti (`service._CTX_FIELDS`) |
| **C-3** | `no_reentry` veniva scritto ma **non letto**: dopo un cash out manuale pre-KO il bot **rientrava** appena scaduto il cooldown | `no_reentry` è letto in due punti: in **`engine.decide`** (i `params` vengono riscritti con `pre_enabled=False, reentry_enabled=False, last_entry_persist=False`) e in **`engine._entry_guard`** (primissimo check: «rientro disabilitato (chiusura manuale): premi Riprendi»), più `_decide_flat` per il re-ingresso live. Solo il comando **Riprendi** (`resume_event`) lo rimette a `False`, e lo dice nell'attività. Pubblicato alla UI in `live.no_reentry` e `ctx.no_reentry` (badge **NESSUN RIENTRO**) |
| **C-4** | Il void era per PARTITA: una sola linea annullata azzerava il P&L di tutta la partita. E `INACTIVE` era trattato come void | Regolamento **PER MERCATO**: `engine.settle_legs_by_market(legs, winners, commission)`, dove `winners[market] = None` significa «quel mercato è annullato» → **solo** le sue gambe valgono `("void", 0.0)` e l'altra linea viene regolata normalmente (caso certificato: 4 gol con Over 4.5 annullato → **−10 €**, non 0). `settle_legs` è ora un wrapper su `winners_from_total`. `service.settle_plan` ritorna `None` se **almeno un** mercato non è né regolato né annullato: si ASPETTA, non si inventa un P&L. **`INACTIVE` NON è un void**: `service._VOID_MARKET_STATUS = ("VOID","VOIDED")` — `INACTIVE` è un mercato non ancora attivo (pre-apertura), e trattarlo come annullato azzerava il P&L di una partita viva |
| **C-5** | L'`insert` di una riga veniva ritentato "alla cieca": un timeout dopo un insert andato a buon fine creava la **riga doppia** | `service._insert_trade_row` ritenta **solo** su errore di schema, riconosciuto da `_is_missing_column_error(ex, "closes_trade_id")`: il messaggio deve contenere il nome della colonna **E** uno dei marcatori `42703` / `pgrst204` / `does not exist` / `unknown column` / `schema cache`. Un timeout o un errore di rete **non** è uno schema mancante: l'eccezione risale e non si reinserisce niente. Il ripiego (colonna assente = migrazione non applicata) avviene **una volta sola**, scrive `meta.closes_trade_id_pending` e l'attività `schema_warn`; il valore viene poi ribaltato in colonna dal ciclo (M-9) |

### 13.2 Gli 8 HIGH della review

| # | Regola che ora vale |
|---|---|
| **H-1** | Lo **stop giornaliero spegne anche `last_entry_persist`**: l'ULTIMO INGRESSO (PERSIST) è un ingresso nuovo e senza spegnerlo `_after_final_green` piazzava ancora `under_last`. A stop attivo: `pre_enabled=False, reentry_enabled=False, last_entry_persist=False`, solo chiusure. Trigger: `day_pnl = realized_today + locked_open ≤ −daily_loss_stop`, loggato **una volta per giornata operativa** (`_operating_day_key`) |
| **H-2** | **Esito ignoto fail-closed**: `service._trade_unknown_outcome` ritorna `True` (= ignoto) sia quando le righe sono illeggibili sia quando la riga specchio non esiste. Una gamba `pending` nel dubbio diventa `pending_reconcile`, **mai `cancelled`**. Riga senza gamba: in paper `status='error'` con `meta.reason='orphan_paper'`, in live `meta.orphan` + log critico — mai chiusa in silenzio |
| **H-3** | **Fallback aggregati incrementale**: senza `mike_bot_v2.sql` non si scansiona più `mike_trades` per intero a ogni ciclo. `db.live_trades(since_iso)` legge le righe non terminali (paginate) + quelle regolate nella finestra + le **aperture** di quelle righe (una chiusura eredita il giorno della sua apertura, M6); i cumulativi di sempre arrivano da una scansione completa in cache 5 min (`_TOTALS_TTL_S`). Il warning «RPC assente» si scrive **una volta sola**, non a raffica |
| **H-4** | **Esenzione dello scanner solo con ESPOSIZIONE**: `safe_strategy/db.list_mike_followed_event_ids` + `_mike_has_exposure` — una partita è esente solo se ha uno stato operativo oppure almeno una gamba `pending` / `pending_reconcile` / `open` non archiviata (un ciclo pre-match ARCHIVIATO non conta più: il capitale non è più a rischio). Le partite in sola osservazione (`WATCH` / `IDLE_LIVE` senza gambe) **non** sono esenti: non hanno nulla da proteggere e pesavano sul pool stream per niente. Tetto **DURO** `scanner.MIKE_MAX_FOLLOWED = 10` (= `max_open_matches`): anche con un bug che marcasse 90 partite come «seguite», il pool non può essere invaso. E chi entra **solo** perché seguito da Mike porta nel pool **le sole linee 3.5/4.5** (`scanner.MIKE_OU_MARKET_TYPES`), non gli altri ~8 mercati a gol dell'evento. La lista è in cache 10 s e, se la lettura fallisce, **resta valida l'ultima buona** |
| **H-5** | **Tier 1.5** in `scanner.opp_rank_key(minute, open_date, mike=True)`: le linee di una partita Mike con posizione stanno DOPO i mercati core (tier 0/1) ma **PRIMA** di ogni altro mercato opportunità (tier 2). Restare fuori dal pool per il troncamento degli shard significherebbe una posizione aperta senza prezzo, quindi senza copertura né cash out. I tier restano numerici e distinti: l'ordinamento non confronta mai una data con un minuto |
| **H-6** | I blocchi tenuti vivi **solo** per Mike sono marcati (`decided`, `for_mike`) da `scanner.ou_block_decided` e **scartati** da `safe_strategy/opportunity.OpportunityModel._market_specs`: per una posizione aperta una linea superata è il prezzo con cui si esce, per il motore opportunità è aritmetica — e con `max_prob_lay = 0` il bot Safe avrebbe potuto layarla. Doppia difesa: anche **senza** il marcatore la linea superata viene scartata |
| **H-7** | **Candidate anche a minuto 0 / `None`**: la regola generale resta `is_opp_candidate(inplay, minute) = minute ≥ 1`, ma `opp_candidates` ammette in OR le partite seguite da Mike già in-play. Prima, fra lo spegnimento del ramo pre-KO al fischio e il 1° minuto, una posizione aperta restava per qualche minuto **senza nessuna linea O/U nel feed** e il cash out rispondeva «feed assente» |
| **H-8** | **Riconciliazione throttlata e ciclo che CONTINUA**: `every = max(5 s, settle_confirm_s)` su `ctx.reconcile_next_ts` (prima erano 2 chiamate REST al secondo per evento). Con un ordine a esito ignoto il ciclo non esce più prima di copertura, cash-out, uscite e cap di perdita: **`engine._strip_openings`** toglie dalla decisione **le sole APERTURE** (`OPENING_ROLES`) e lascia `cancel` e chiusure — restano attive tutte le azioni che RIDUCONO il rischio. Se Betfair non risponde: `reconcile_pending` con `reason=betfair_non_raggiungibile`, critico, e **nessuna ipotesi** |

### 13.3 MEDIUM e LOW della review

| # | Regola che ora vale |
|---|---|
| **M-1** | Lo stop giornaliero guarda **solo la giornata operativa**: il P&L bloccato di una partita piazzata ieri non entra nello stop di oggi (`service._locked_open_pnl` filtra su `_first_placed_at(legs) ≥ day_start_ts`) |
| **M-2** | Riga **orfana** `open` in paper chiusa con `status='error'`, `meta.reason='orphan_paper'` (in live mai chiusa in silenzio: `meta.orphan` + log critico) |
| **M-3** | Una **gamba malformata grida**: `service._legs_from_json` scarta solo la gamba illeggibile, tiene le altre, e scrive `logger.critical` + attività `error` con `reason='leg_malformata'`, `critical=true`. Niente più `positions` silenziosamente dimezzate |
| **M-4** | La **liability ha una fonte dichiarata**: `mike_aggregates_sql` usa la liability NETTA da `mike_events.live->>'liability'` e, se NESSUN evento ha la chiave (servizio non ancora riavviato), ripiega sulla somma delle righe e lo **dichiara** con `liability_source='rows_sum'`. Prima quel caso mostrava «nessun rischio» con decine di posizioni aperte |
| **M-5** | `get_mike_state().trades` ha un **tetto DURO `LIMIT 500`** e un ordinamento esplicito (`placed_at DESC`): una giornata piena di cicli pre-match fa centinaia di righe e la RPC non deve crescere senza limite. La UI lo dichiara («mostrate le ultime 500 righe (tetto della RPC)») |
| **M-6** | Il **battito non si scrive a ogni ciclo**: non basta «qualcosa è cambiato», perché P&L e liability cambiano quasi sempre. Regola: `stats` al massimo ogni `_STATS_MIN_S = 5 s` se la firma è cambiata, e comunque un battito ogni `_HEARTBEAT_MIN_S = 10 s`. Certificato: 10 cicli a 1 s con prezzi diversi → **≤ 3** scritture (prima 10 su 10) |
| **M-7** | Un **log CRITICO non resta muto 5 minuti**: `service._log_throttled` accorcia l'intervallo a `_CRITICAL_LOG_EVERY_S = 45 s` quando il payload ha `critical=true`; i log non critici restano su `skip_log_interval_s` (300 s) |
| **M-8** | All'avvio, `entry_hours_before_ko` più ampia del ramo pre-KO dello scanner (o ramo spento) → attività `config_warn` con entrambi i numeri |
| **M-9** | `meta.closes_trade_id_pending` (scritto dal ripiego C-5) viene **ribaltato in colonna** dal ciclo appena la colonna esiste, e la chiave `meta` rimossa: nessuna chiusura resta scollegata dalla sua apertura |
| **L-1** | `db.open_trades` è **paginata**: oltre 1000 righe Supabase troncava in silenzio e la riconciliazione avrebbe visto gambe «senza riga» |
| **L-2** | Il **throttle del regolamento persiste comunque lo stato**: dentro la finestra il ciclo esce senza rileggere il book, ma `ctx` (es. `ht_score`) viene salvato e `settle_next_ts` non viene rifissato |
| **L-3** | La **chiusura manuale usa i parametri EFFETTIVI**: in live `_params_for` forza `pre_exit_mode='taker'`, quindi il flatten non tenta una lay appoggiata che in live non esiste |
| **`is_placed`** | Nello **storico condiviso** una riga `pending` in RICONCILIAZIONE (`meta.reason='place_exception_reconciling'`) conta come **PIAZZATA**, come già fanno i KPI di Omega/Safe/Mike: prima lo storico mostrava meno `trades_placed` dei KPI della stessa giornata. ⚠️ `mike_bot_v2.sql` definisce `is_placed` in modo diverso (`bet_id` o `flumine_client_ref`) e tiene `reconciling` come colonna separata — vedi §10.B.4 |

### 13.4 I fix della certificazione UI

| Cosa | Regola che ora vale |
|---|---|
| **Realtime completo** | `mike_activity` è **nel canale realtime**: `lib/mike.ts::MIKE_REALTIME_TABLES = ['mike_control','mike_events','mike_trades','mike_activity','mike_requests']`, un solo canale `mike-live` per tutte e cinque. Senza `mike_activity` la scheda Attività si aggiornava solo al poll da 15 s o per rimbalzo di un'altra tabella. Un test verifica che le tabelle sottoscritte siano **esattamente** quelle che il servizio scrive |
| **Nessun `kind` non dichiarato** | **`settle` non è un kind di attività** e non viene più loggato come tale: il regolamento scrive `settled`, dal ramo «mercato chiuso», dopo `_settle_trades`. Dei sei valori di telemetria dell'engine solo `pre_cycle`, `cover` e `close_retries_exhausted` diventano attività; `cover_wait`, `cashout` e `loss_exit` finiscono in `ctx` (`last_cover_wait`, `last_cashout`, `last_loss_exit`) e vanno nella card, non nel log. Un test confronta i `kind` scritti dal backend con `MIKE_ACTIVITY_KINDS` dichiarati nella UI |
| **«in attesa del fischio»** | Calcio d'inizio passato ma il feed non dice ancora `inplay`: la card **resta in PRE-MATCH** e lo scrive in ambra (`MIKE_AWAITING_KICKOFF_NOTE`), invece di mostrare «fra —» e sembrare rotta |
| **Stato mercato in italiano** | `books[...].status` arriva grezzo da Betfair e non finisce più nudo nella card: `OPEN` non si scrive, `SUSPENDED` → **SOSPESO** (ambra), `CLOSED` → **CHIUSO** (rosso), `INACTIVE` → **NON ATTIVO** (rosso), ignoto → il codice con gli underscore sciolti, in ambra. SOSPESO e CHIUSO significano «non puoi operare adesso»: sono allarmi, non grigio |
| **Errore dello storico leggibile** | `mikeHistoryErrorMessage` / `withMikeHistoryError` traducono `42725 is not unique` (e «does not exist», «could not find the function», …) in **«storico Mike: applica `migrations/mike_history_v2.sql`»**, invece di un codice nudo su una pagina vuota |
| **«→ scheda partita»** | Nella scheda Trade le righe ancora aperte (`pending`/`open`/`hedged`) hanno il link **→ scheda partita**, che porta alla card e la illumina per 2 s: il cash out si fa dalla card, dove ci sono prezzi, netto e motivi, non dalla tabella |
| **Ripieghi senza `mike_bot_v2.sql`** | La UI funziona anche senza la migrazione, ma **lo dichiara sempre**: giornata operativa stimata dal client con **`romeDayStartMs`** (mezzanotte di Roma) e nota in ambra nella scheda Trade; **V/P calcolati dal client** con `dayResultCounts` e nota nella DayBar; `requests[]` letti a parte da `mike_requests`; contatori con fallback (`events_today ?? partite attive`, `cycles_today ?? righe`, `live_now ?? sezione LIVE`); liability `stimata dalle righe` quando `liability_source='rows_sum'`. E quando il servizio non batte da oltre 45 s: **«servizio senza battito: riavvia l'app desktop»** nella tile Ultimo ciclo e **«IN CORSA · SENZA BATTITO»** nel badge del bot |
| **Ordine indipendente dallo stato** | Un test verifica che **l'ordine delle schede non dipenda dallo stato**: solo calcio d'inizio + `event_id` (§8) |

### 13.5 CONTRATTO UI — definitivo, preso dal codice

La UI legge **una sola** RPC: `public.get_mike_state()` (definita in `migrations/mike_bot_v2.sql`,
`SECURITY DEFINER` con guardia `betfair_live_is_owner()`), consumata da
`lib/mike.ts::fetchMikeState`. **8 chiavi di primo livello**:

```
control · events · trades · activity · aggregates · requests · day_start · day_by
```

- **`control`** = `mike_control` (id 1): `status` ∈ `idle|running|stopping|stopped|error`,
  `mode` ∈ `paper|live`, `params`, `stats`, `error`, `started_at`, `stopped_at`, `heartbeat_at`,
  `updated_at`. `stats` (scritto da `service.run_once`): `events_feed`, `events_tracked`,
  `by_state`, `trades_open`, `open_liability`, `open_liability_rows`, `realized_today`,
  `realized_total`, `locked_open`, `day_pnl`, `won_today`, `lost_today`, `cycles_today`,
  `events_today`, `live_now`, `scanner_age_s`, `last_cycle`, `dry`, `mode`, `daily_stop`,
  `reconciling`.
- **`events[]`** = `mike_events` non terminali + terminali delle ultime 24 h, `ORDER BY ko_at`,
  `LIMIT 200`. Campi: `event_id`, `fixture_id`, `event_name`, `competition`, `league_id`, `ko_at`,
  `mode`, `markets`, `state`, `cycle_no`, `entry_price_initial`, `dossier`, `live`, `positions[]`,
  `ctx`, `skipped`, `settled_pnl`, `updated_at`.
  - **`live.*` completo** (scritto dal servizio): `minute`, `goals`, `inplay`, `ht`, `score_home`,
    `score_away`, `red_home`, `red_away`, **`feed_age_s`** (età della riga di QUESTA partita),
    `scanner_age_s`, **`lines_missing[]`**, **`reconcile_pending`**, **`liability`** (netta,
    `engine.event_liability`), **`locked`** (`engine.locked_pnl`), **`no_reentry`**,
    `total_matched`, `model_probs`, `ht_score`, `p_total_model`, `p_total_emp`, `hazard`,
    `hazard_atlas`, `hazard_model`, `pressure`, `cover_gain_pct`, `p_over45_model`, `p4_market`,
    `p4_model`, `cover_wait`, `pnl_by_total`, `books`, `feed_fresh`, `loss_exit`, `cashout`.
  - `live.cashout` = `{net, gross, base, complete, pct, target_pct, commission, per, per_gross,
    decided[], smart{enabled, floor, near, hot, hazard, pressure, cv_goal, cv_later, h_step,
    ev_hold, trigger}}` — `per` è il bloccabile **NETTO per selezione** ("OU35|UNDER" → €),
    `per_gross` il lordo (solo tooltip), `decided` le selezioni con esito già deciso.
  - `live.loss_exit` = `{mode, window, ev_hold, p4, p4_model, p4_emp, p4_market, premium,
    threshold, sources[], missing, beyond_cap, pct}`.
  - `live.books` = `{"OU35|UNDER": {best_back, back_size, best_lay, lay_size, status, inplay,
    bet_delay}, …}`.
  - **`positions[]`** (una gamba): `role`, `market` ∈ `OU35|OU45`, `selection` ∈ `UNDER|OVER`,
    `side` ∈ `back|lay`, `price`, `size`, `matched`, `avg_price`, `ref`, **`status` ∈
    `pending | pending_reconcile | open | cancelled | settled`**, `placed_at`, `persistence`,
    `cycle_no`, `final`, `archived`, `closes_ref`. **`pending_reconcile`** = esito IGNOTO su
    Betfair, mai trattata come annullata; l'aggregato per partita è `live.reconcile_pending`.
  - **`ctx`**: `last_green_at`, `last_action_at`, `attempts`, `reentry_allowed`, `reentry_done`,
    `close_reason`, `cover_skipped`, `seq`, **`flatten_pending`**, **`no_reentry`**, più le chiavi
    di servizio (`selections`, `seen_inplay`, `last_goals`, `ht_score`, `deferred`, `log_seen`,
    `last_reason`, `last_cashout`, `last_cover_wait`, `last_loss_exit`, `settle_first_ts`,
    `settle_next_ts`, `reconcile_next_ts`, `row_missing_since`). La UI legge
    **`ctx.flatten_pending`** (badge CHIUSURA IN CORSA) e **`ctx.no_reentry`** (badge NESSUN
    RIENTRO, in OR con `live.no_reentry`).
- **`trades[]`** = righe della giornata operativa (giorno di piazzamento della POSIZIONE) **più**
  tutte le righe ancora vive dei giorni precedenti (mai una posizione aperta invisibile),
  `ORDER BY placed_at DESC`, **`LIMIT 500`**, arricchite con
  `day_placed_at = coalesce(apertura.placed_at, riga.placed_at)`. Campi: `id`, `event_id`,
  `event_name`, `strategy`, `role`, `cycle_no`, `market_type`, `selection_name`, `side`, `mode`,
  `price`, `size`, `liability`, `status` ∈ `pending|open|hedged|won|lost|void|error`,
  **`pnl` NETTO commissione**, `placed_at`, `settled_at`, `signal_key`, `meta`,
  **`closes_trade_id`**, `day_placed_at`, `origin` ∈ `auto|manual`.
  - **`meta.*`** che la UI usa: `exit_kind` ∈ `greenup|profit|loss|time|forced|manual|other`
    (`engine.EXIT_KINDS`, da `engine.exit_kind_for`), `exit_reason`, `pnl_gross`,
    `commission_paid`, `commission_market`, `orphan`, `reconciled`, `reason`, `void_reason`,
    `duplicate_of`. Altre chiavi scritte dal servizio: `phase`, `leg_ref`, `final`, `closes_ref`,
    `closes_trade_id_pending`, `bet_id`, `fill`, `flumine_client_ref`.
- **`activity[]`** = `mike_activity` della giornata operativa, `ORDER BY ts DESC`, `LIMIT 400`:
  `id`, `ts`, `event_id`, `kind`, `payload`. **Tutti i `kind`**, dichiarati in
  `lib/mike.ts::MIKE_ACTIVITY_KINDS` e verificati contro il backend da un test:

  ```
  armed · state · place · place_pending · place_deferred · place_resting · fill_resting ·
  cancel · skip · no_fill · would_place · size_legalized · pre_cycle · cover ·
  close_retries_exhausted · settled · settle_fallback · settling_reverted · daily_stop · stop ·
  skip_event · resume_event · reconcile_pending · reconcile_fix · resting_live_unsupported ·
  feed_line_missing · config_warn · schema_warn · error
  ```

  I tre **critici** (rossi in UI, intervallo di log accorciato a 45 s): `reconcile_pending`,
  `feed_line_missing`, `resting_live_unsupported` — e sono anche i tre che passano **solo** da
  `_log_throttled`. **`settle` non è un kind.**
- **`aggregates`** (da `mike_aggregates_sql()`): `realized_total`, `realized_today`, `open_count`,
  `open_liability`, **`liability_source`** ∈ `net_positions|rows_sum`, **`liability_stale`**
  (battito più vecchio di 60 s), **`heartbeat_at`**, `open_liability_rows`, `live_now`, `won`,
  `lost`, `won_today`, `lost_today`, `cycles_today`, `events_today`, **`reconciling`**,
  **`day_by`** = `'placed'`.
- **`requests[]`** = ultime 50 `mike_requests`: `id`, `kind` ∈
  `cashout|flatten|skip_event|resume_event|cancel`, `payload`, **`status` ∈
  `pending | processing | done | rejected | error`**, `result`, `created_at`, `updated_at`.
  - **`result`** = `{code, message (in italiano), ok, phase:'armed', cancelled, legs,
    cashout_net, complete, warning:'reconcile'}`. `rejected` = rifiuto **ATTESO**, non un errore, e
    i codici che lo producono sono una whitelist (`service._REJECT_CODES`): `evento_non_seguito`,
    `stato_terminale`, `posizione_aperta`, `stato_non_riprendibile`, `feed_assente`,
    `snapshot_assente`, `niente_da_chiudere`, `feed_stantio`. Tutto il resto è `error`,
    **`kind_non_valido` compreso** (è un contratto rotto fra UI e DB, non un rifiuto).
    `phase='armed'` è la risposta del cash out / flatten: gli ordini sul book sono stati annullati
    e la chiusura la guida l'engine nei cicli successivi. Senza `mike_bot_v2.sql` lo stato
    `'rejected'` non esiste e `db.set_request_status` ripiega su `'error'` con lo **stesso**
    `result` (la UI mostra lo stesso messaggio).
- **`day_start`** = mezzanotte **Europe/Rome** dichiarata dal DB; **`day_by`** = `'placed'`.

**I 19 stati** (`engine.STATES` = `lib/mike.ts::MIKE_STATES`, identici per test):
`WATCH`, `PRE_ENTRY_PENDING`, `PRE_OPEN`, `PRE_GREEN_PENDING`, `HOLD`, `PRE_LAST_ENTRY_PENDING`,
`IDLE_LIVE`, `LIVE_UNCOVERED`, `LIVE_COVER_PENDING`, `LIVE_COVERED`, `LIVE_CLOSING`, `FLAT`,
`REENTRY_PENDING`, `REENTRY_OPEN`, `REENTRY_GREEN_PENDING`, `SETTLING`, `SETTLED`, `ERROR`,
`SKIPPED`. Terminali: `SETTLED`, `ERROR`, `SKIPPED`.

**I 9 ruoli** (`engine.ROLES`): `under_entry`, `under_green`, `under_last`, `over_cover`,
`under_close`, `over_close`, `reentry`, `reentry_green`, **`manual_close`** (la chiusura decisa
dall'utente, marcata `✋` nella scheda Trade). Aperture =
`OPENING_ROLES = (under_entry, under_last, over_cover, reentry)`: sono le sole azioni che
`_strip_openings` toglie quando c'è un ordine a esito ignoto. Chiusure =
`CLOSING_ROLES = (under_green, under_close, over_close, reentry_green, manual_close)`: sul DB
portano sempre `closes_trade_id`.

**Parametri**: rimossi `max_matches`, `catalogue_refresh_s`, `stream_extra_lines`,
`min_total_matched` (erano inerti e la UI li mostrava come se lavorassero; un test verifica che
non tornino); ora cablati `settle_confirm_s`, `skip_log_interval_s`, `cover_max_overshoot_pct`.
Dettagli e motivazioni in §6.

### 13.6 La giornata operativa è il giorno di PIAZZAMENTO

Una sola definizione, in tutti i posti: **la giornata operativa di una riga è il giorno
(Europe/Rome) in cui è stata piazzata la POSIZIONE**, non la riga.

- Una **chiusura eredita il giorno della sua apertura** (`closes_trade_id`): un green-up fatto a
  mezzanotte e cinque resta nella giornata in cui il trade è stato aperto.
- Un **regolamento notturno** resta nel giorno in cui il trade è stato aperto.
- Vale per: KPI e DayBar, scheda Trade, scheda Regolate, equity curve e **storico**.
- Implementazione: `mike_aggregates_sql` e `get_mike_state` con
  `pos_placed_at = coalesce(apertura.placed_at, riga.placed_at)` e `day_by='placed'`;
  `get_mike_daily` / `get_mike_day_trades` con `p_day_by='placed'`; lato Python
  `db.aggregate_rows` risale a `closes_trade_id` e la mezzanotte di Roma arriva da
  `safe_strategy.risk.operating_day_start`; lato UI `tradeDayMs(t) = day_placed_at ?? placed_at`,
  con il ripiego dichiarato `romeDayStartMs` quando il DB non espone `day_start`.
- Anche lo **stop giornaliero** usa la stessa giornata, e comprende il P&L BLOCCATO delle partite
  vive piazzate oggi: il bloccato di ieri non entra nello stop di oggi (§13.3 M-1).

---

## §14 IL MODELLO ERA SPENTO, PUNTI APERTI E CONSIGLI (12/09/2026 sera, `cda8e20` + `b267497`)

Analisi completa in `Betfair/CHIUSURE_2026-09-12.md`.

### §14.1 Il difetto più grave della storia del bot: il modello non ha MAI funzionato

Il dossier era **vuoto su tutti e 93 gli eventi** (`lambda_home` e `lambda_away` a `null`,
`source: "none"`). Causa: `fixture_id_for_event` cercava la partita SOLO in `live_follow`,
la tabella del runner del trading live, che segue partite sue — **nessuno dei 19 eventi Mike
vivi era lì dentro** (55 righe, zero in comune).

Senza gol attesi non c'è griglia Poisson. Quindi, su OGNI partita:

| Dato | Stato | Che cosa comandava al suo posto |
|---|---|---|
| `p_total_model` | sempre `null` | l'uscita in perdita decideva su tabella empirica e mercato |
| `hazard_model` | sempre `null` | il cash out «intelligente» non si è **mai** attivato |
| `cover_gain_pct` | sempre `null` | l'attesa della copertura non si è **mai** attivata |

Conseguenza pratica più cara: `cover_timing` copre subito a ogni dato mancante («mai attesa
al buio»), quindi **Mike ha sempre coperto al primo prezzo invece che al migliore**.

**Correzioni** (tutte e tre necessarie, una sola non basta):
1. `db.fixture_id_for_event` guarda anche `omega_events` (17 eventi vivi su 25 hanno lì la
   fixture). È la fonte MIGLIORE: lambda indipendenti dai prezzi.
2. `dossier.lambdas_con_ripiego` riusa la catena di Omega (§14 di quella costituzione):
   fixture → quote 1X2 pre-KO → mercato O/U live. Nessun ripiego riuscito = `(None, None,
   "none")`: il bot resta cieco ma **non decide su numeri inventati**.
3. `service._retry_dossier` RITENTA ogni 300 s le partite vive col dossier cieco.
   `build_prematch` girava una sola volta alla presa in carico: se in quel momento la fixture
   non c'era, il dossier restava vuoto **per sempre**. È così che tutti e 93 gli eventi si
   sono ritrovati con `source: "none"`.

**Verificato dal vivo (12/09, 22:42:46)**: due partite hanno risolto la fixture e ricevuto
gol attesi veri (CD Gualberto Villarroel 1,50/1,11 · Deportivo La Guaira 0,99/1,70). È la
prima volta che Mike ha un modello **indipendente dai prezzi di mercato**.

**NORMA**: `lambda_source` è pubblicato nello stato live e mostrato in scheda. Se dice
`none`, il bot sta decidendo senza modello e chi legge deve saperlo. Un numero etichettato
«modello» che nasce dal mercato non è un modello.

### §14.2 Uscita in perdita: lo stesso rischio non si conta due volte

`loss_exit_model` chiude se `cv_net ≥ ev_hold − premio`, con
`premio = capitale × pct × P(4 gol)`. Ma **il disastro dei 4 gol è già dentro `ev_hold`**
(è uno dei termini di `Σ P(totale) × P&L(totale)`, su una posizione tipica pesa −2,41 €):
sottrarne un altro pezzo proporzionale a P(4) conta la stessa perdita una seconda volta.
`loss_exit_risk_premium_pct` **50 → 10**.

Storia che l'ha motivata: 7 uscite in perdita, **6 su partite finite sotto i 3,5 gol**
(l'Under avrebbe vinto), 4 chiuse con l'Under ancora **favorito al 57-66 %**.
Reale −19,56 contro +21,37 tenendo. Vale però la legge di §18.1 della costituzione Omega:
chiudere a mercato è neutro, quindi quella differenza si realizza solo se il modello batte
il mercato — ed è esattamente perché il modello era spento che non poteva farlo.

### §14.3 Esecuzione (corretto e misurato)

- **Copertura sotto il minimo Betfair**: 176 tentativi rifiutati, ritentati a ogni giro.
  Decisioni di copertura da **4,9 al minuto a 0,08** (61 volte meno rumore).
- **Priorità a chi ha soldi a rischio** (`scanner.prioritize_followed`): il lotto del catalogo
  mercati viene troncato e l'ordine era solo «minuti più avanzati». Al riavvio 11 partite con
  posizioni aperte sono rimaste ~10 minuti **senza nessuna linea O/U** (46 allarmi critici).
  Dopo il fix: **8 partite su 8** con le linee, allarmi **da 46 a 9**.
- **Allarme critico falso**: le gambe pianificate e mai piazzate valgono zero e non sono un
  errore (verificato: scarto 0,00 € su 8 partite). Ora scrivono `settle_gambe_non_piazzate`.
- Il paper è **fedele al live**: FILL OR KILL con uccisione dei parziali, rispetto della
  liquidità al best price, rifiuto sotto i 2 €. I suoi numeri valgono come prova.

### §14.4 Punti aperti

1. **Nessun margine dimostrato.** Su 42 partite l'Under è uscito **69,0 %**, ma l'intervallo
   di confidenza al 95 % va da **55,1 % a 83,0 %** (z = 0,43 contro il pareggio al 65,8 %):
   compatibile con zero. Servono ~330 partite per misurarlo a ±5 punti, ~910 a ±3.
   **Non tarare la selezione sulle fasce di quota**: i gruppi hanno 3-18 casi, è rumore.
2. **La copertura Over 4.5 peggiora SEMPRE il valore atteso.** Non è assicurazione gratuita:
   si paga sul 66 % delle partite in cui l'Under vince.

   | Copertura | Stake | EV/partita |
   |---|---|---|
   | nessuna, solo Under | — | −0,13 |
   | Over 4.5 @ 5,0 | 2,50 | −1,13 |
   | Over 4.5 @ 6,0 | 2,00 | −0,69 |
   | Over 4.5 @ 7,0 | 1,67 | −0,40 |

   Compra **riduzione della varianza** (il caso ≥5 gol da −10 a circa zero), non profitto.
   Più alta è la quota Over quando si copre, meno costa.
3. Distribuzione reale dei gol su 56 partite: **≤3 66,1 % · 4 21,4 % · ≥5 12,5 %**. A quota
   media d'ingresso 1,52 il pareggio è al 65,8 %: il margine è indistinguibile da zero.

### §14.5 Consigli (in ordine di valore)

1. **FAR SCEGLIERE MIKE. È il consiglio più importante di tutto il documento.**
   Oggi l'ingresso è una **pura finestra di prezzo**: `pre_entry_price_min` 1,30 e
   `pre_entry_price_max` 3,00, e dentro quella finestra entra su qualunque partita, **senza
   mai confrontare il modello col prezzo**. Il modello lo usa solo per USCIRE.
   Senza selezione non c'è margine: si paga lo spread su tutto, ed è la spiegazione del
   66,1 % osservato contro il 65,8 % di pareggio.
   Da quando il modello funziona (§14.1) questo confronto è **finalmente possibile**: entrare
   solo quando `P(≤3) del modello − P(≤3) implicita nel prezzo` supera una soglia dichiarata.
   È l'unico intervento che può **creare** un margine invece di proteggerne uno che non
   sappiamo se esista.
2. **`cover_profit_factor` da 1,2 a 1,0**: vale **+0,19 € per partita** (~11 € sulle 56
   seguite) e rispetta comunque la regola dichiarata «si perde solo con 4 gol» — a 1,0 il
   caso ≥5 chiude in pareggio invece che a +2. Caso vero: Koper v Olimpija, coperti 6,16 €
   dove 5,13 bastavano.
3. Il rialzo al minimo Betfair su quote Over alte **conviene** (verificato: +0,05 € di EV):
   l'extra costa 0,46 € nell'87,5 % dei casi e rende +3,58 € nel 12,5 %. Non toccarlo.

---

## §15 IL FLUSSO DAL FISCHIO D'INIZIO (13/09/2026)

Specifica dettata dall'utente e confermata prima di scrivere una riga di codice.
Riguarda **solo** la posizione Under 3.5 che il pre-match non è riuscito a chiudere e che
entra in gioco. Tutti i cicli pre-match già chiusi restano chiusi: questa è un'operazione
nuova, che parte dal calcio d'inizio.

### 15.1 Premessa verificata sulla documentazione Betfair

`persistenceType` riguarda **solo la parte ineseguita** di un ordine: `LAPSE` la fa
annullare al passaggio in gioco, `PERSIST` la porta dentro. Una gamba **già abbinata** non
è toccata da nessuno dei due: entra in gioco comunque. Quindi la posizione Under 3.5
abbinata prima del fischio è in gioco per costruzione, e l'ultimo ingresso in `PERSIST`
serve a portare dentro anche l'eventuale **residuo** non ancora abbinato.

### 15.2 Le tre strade

Al fischio il bot appoggia l'**ordine opposto** (lay) a `ko_green_ticks` tick **sotto il
nostro prezzo di ingresso** — la media delle gambe Under abbinate e ancora a rischio, non
il prezzo di mercato. È un **limite**: se il mercato offre di meglio si abbina meglio, mai
peggio. L'ordine resta per `ko_green_window_s` **contati dal fischio visto in gioco**, non
dal `ko_at` di calendario.

| | Condizione | Cosa fa il bot | Stato |
|---|---|---|---|
| **A** | l'ordine si abbina entro la finestra | profitto bloccato, **nessuna copertura**, capitale libero | `FLAT` |
| **B** | la finestra scade senza gol e senza abbinamento | annulla l'ordine e compra la copertura **piena** sull'Over 4.5 | `LIVE_COVER_PENDING` |
| **C** | arriva un gol dentro la finestra, ancora scoperti e non usciti | annulla l'ordine, **seconda puntata** sull'Under 3.5, poi copertura in **due tranche** | `LIVE_SECOND_ENTRY` |

La strada C **non** si apre in nessun altro caso: né dopo la copertura, né su un secondo
gol, né a finestra scaduta. `second_entry_done` la rende irripetibile.

### 15.3 La strada C, passo per passo

1. **Seconda puntata** `second_entry_stake_pct`% dello stake (50 % = 5 € su 10) sull'Under
   3.5 **al miglior prezzo disponibile**. Dopo un gol la quota è salita: la seconda puntata
   alza la **quota media** e sfrutta il tempo che resta senza gol.
   Esempio della specifica: 10 € a 1,50 + 5 € a 1,95 = **15 € a 1,65**; vincendo si incassa
   **+9,75** invece di +5,00, con un rischio di 15 invece di 10.
2. **Prima tranche** di copertura dopo `early_goal_cover_delay_s` **dal gol** (2 minuti):
   `early_goal_cover_pct`% della copertura necessaria.
3. **Seconda tranche** dopo `early_goal_cover2_delay_s` **dall'abbinamento della prima**
   (3 minuti): il **residuo**, ricalcolato da `cover_residual` sulla quota Over di **quel
   momento** e su quanto la prima tranche ha già garantito. **Non** è «l'altra metà dello
   stesso importo»: su 15 € di rischio, con la prima tranche a 1,35 € (Over 8,00), la
   seconda vale 2,37 € se l'Over è sceso a 5,00 e 0,68 € se è salito a 15,00. In ogni caso
   la protezione totale resta quella dichiarata da `cover_profit_factor`. Entrambe le
tranche si piazzano per il loro importo esatto (§15.5).

La seconda puntata **non ritarda mai la copertura**: se non si abbina entro i due minuti
viene annullata e si compra la copertura piena.

### 15.4 Dal momento in cui ci sono due gambe a mercato, le uscite sono GLOBALI

Regola esplicita dell'utente. Appena Under 3.5 e Over 4.5 sono entrambi a mercato, le
decisioni di uscita riguardano la **posizione intera** (cash-out globale, cash-out
intelligente, uscite HT/2T a modello, cap di perdita evento), **mai la singola gamba**.
Per questo la copertura a tranche **passa da `LIVE_COVERED`** fra una tranche e l'altra:
è lì che vivono le uscite globali, e hanno la **precedenza** sulla seconda tranche — se la
posizione si chiude non c'è più niente da coprire.

### 15.5 QUALSIASI IMPORTO È PIAZZABILE — place-and-trim collegato (13/09)

**Regola definitiva: su Betfair si piazza qualunque cifra, fino al centesimo.**
Il minimo di giurisdizione (.it BACK 2,00 € / LAY 0,50 €) riguarda il place **diretto**, non
l'ordine in sé: un ordine già esistente può essere **ridotto** sotto quella soglia. È la
tecnica di Bet Angel, Fairbot e Betting Toolkit, e si chiama **place-and-trim**:

1. si **parcheggia** il minimo a una quota NON abbinabile (BACK 1000 / LAY 1.01), persistenza
   LAPSE e **senza** fill-or-kill (deve restare a riposo per poter essere tagliato);
2. si **taglia** con un cancel parziale (`sizeReduction`): resta esattamente l'importo voluto;
3. si **riprezza** (`replaceOrders`) alla quota reale.

**Com'era prima del 13/09.** La macchina esisteva già in `Betfair/stream/trading/submin.py`,
ma **nessuno la chiamava**: `execution.py::enqueue_place` accodava sempre `action: "place"`, e
per giunta il runner flumine che esegue quella coda è **fermo dal 2 settembre**. Risultato:
`exact_sizes=True` non aveva alcun effetto sotto i 2,00 € e il bot comprava 2,00 € di Over
dove ne servivano 1,35 (il 48 % in più, tutto sovracopertura pagata).

**Com'è adesso.** Tre percorsi, in ordine:

| Dove | Come |
|---|---|
| **paper** | l'esecuzione è simulata: non esiste nessun minimo da aggirare, l'importo esatto si abbina |
| **live, coda del runner accesa** | azione `place_submin` sulla coda (macchina a stati asincrona, ripristinabile dopo un crash) |
| **live, coda spenta** | `omega_market.place_submin_live` — la **stessa** sequenza in tre chiamate REST sincrone: nessun runner, nessuna dipendenza |

Il terzo percorso è quello che rende la regola vera sempre: non dipende da nessun processo
acceso. `cover_legal_size` non alza più niente al minimo, e la divisione in due tranche si fa
a **qualunque** quota dell'Over (prima si fermava sopra 5,74, cioè quasi sempre).

**Guardie money-critical della sequenza REST** (le stesse della macchina asincrona, testate
in `Betfair/omega/test_place_and_trim_2026_09_13.py`):

* il **parcheggio non deve mai abbinarsi** — a quota 1000 / 1.01 non c'è controparte. Se si
  abbina siamo entrati a mercato in modo non previsto: si ritira tutto, si solleva, **nessun
  ritento automatico**;
* **senza il taglio confermato da Betfair non si riprezza.** È la guardia più importante:
  `sizeCancelled` deve combaciare con la riduzione chiesta. Senza questa verifica un replace
  porterebbe la size **piena** del parcheggio (2,00 €) alla quota reale;
* **ogni fallimento dopo il parcheggio ritira il residuo** prima di propagare l'errore: mai un
  ordine a riposo non tracciato sul conto.

Il floor assoluto è **0,01 €** (`engine.SUBMIN_FLOOR`): sotto il centesimo non esiste ordine,
e la richiesta viene rifiutata **prima** di toccare la rete.

Unica eccezione, ed è una scelta esplicita dell'utente: se dalla UI si spengono gli **importi
esatti** (`exact_sizes = false`), gli ordini tornano legalizzati al minimo .it e la divisione
in tranche si ferma quando ciascuna metà non ci arriva da sola.

### 15.6 Nota sul percorso LIVE

In live la lay **appoggiata** non esiste su nessun percorso di Mike (nota H3 in
`service._live_exit_override`: niente fill simulati su soldi veri). L'ordine di uscita
quindi non è marcato «resting» in live: viene **ri-presentato al mercato** ogni
`ko_green_retry_s` secondi e si abbina appena il prezzo c'è — l'equivalente pratico di un
ordine appoggiato. Il ritmo esiste perché 180 secondi a mezzo secondo produrrebbero 360
righe di attività per partita, che è esattamente la zavorra da cui è arrivato lo
`statement timeout` del 13/09.

### 15.7 Guardie money-critical introdotte

* **mai due lay vive sull'Under 3.5**: se la lay del ciclo pre-match non è ancora annullata
  per davvero, l'ordine di uscita aspetta. Un doppio abbinamento ribalterebbe la posizione
  da back netto a lay netto;
* **baseline dei gol**: senza il punteggio al fischio la strada C non parte. Meglio perdere
  la seconda puntata che aprirla su un gol che non c'è stato;
* **orologi persistiti** (`live_since`, `ko_goals`, `early_goal_at`, `cover_stage`,
  `cover_stage1_at`, `cover_forced`): un riavvio a metà partita non perde i tempi. Se il
  momento del gol manca comunque, la copertura si compra **in una volta** invece di restare
  in attesa di un'attesa che non finisce mai;
* **la copertura ordinata dal flusso non ripassa dall'attesa "intelligente"** di
  `cover_timing`: finestra scaduta e gol precoce sono decisioni già prese.

### 15.8 Parametri nuovi (gruppo «Dal fischio d'inizio» nella UI)

| Parametro | Default | Che cosa governa |
|---|---|---|
| `ko_green_enabled` | `true` | off = si copre e basta, nessun tentativo di uscita |
| `ko_green_ticks` | 2 | tick sotto il nostro ingresso |
| `ko_green_window_s` | 180 | durata della finestra, dal fischio |
| `ko_green_retry_s` | 5 | ritmo di ri-presentazione (solo live) |
| `second_entry_enabled` | `true` | seconda puntata dopo un gol precoce |
| `second_entry_stake_pct` | 50 | % dello stake iniziale |
| `early_goal_cover_delay_s` | 120 | prima tranche, dal gol |
| `early_goal_cover_pct` | 50 | % della copertura nella prima tranche |
| `early_goal_cover2_delay_s` | 180 | seconda tranche, dall'abbinamento della prima |

Copertura di test: `Betfair/mike/tests/test_mike_flusso_fischio_2026_09_13.py`, 42 casi —
tre strade, matematica delle due tranche a quote diverse, soglia del minimo piazzabile,
uscite globali, percorso live, riavvio a metà partita.

---

## §16 CERTIFICAZIONE PRE-PRODUZIONE (13/09/2026) E PROTOCOLLO DI VERIFICA IN LIVE

Prima del passaggio a soldi veri sono state fatte girare **quattro certificazioni
indipendenti e in parallelo** — separazione paper/live, logiche dell'engine, ciclo di vita
dell'ordine, componenti della UI — ognuna con l'obbligo di **provare** ogni affermazione
eseguendo un controesempio, non di dedurla.

Il verdetto iniziale è stato **NO, non si può andare live**. Quello che segue è ciò che è
stato trovato, ciò che è stato corretto, e ciò che **resta da verificare sul campo**.

### 16.1 La regola che governa tutto: paper e soldi veri non si sommano MAI

Un trader che legge `+42,10 €` deve sapere se sono quarantadue euro o quarantadue finti.
È la differenza fra uno strumento e un giocattolo.

| Dove | Com'era | Com'è |
|---|---|---|
| Aggregati SQL | nessun filtro su `mode`: «P&L oggi» e «P&L totale» avrebbero sommato euro veri e simulati | `mike_aggregates_sql(p_mode)` filtra sulla modalità **corrente del bot**, e pubblica entrambi i realizzati |
| Pagina | tutte le righe insieme | solo la modalità in corso; quelle dell'altra vengono **dichiarate**, non nascoste |
| Stop giornaliero e liability | sommavano tutte le partite seguite | filtrano per modalità: il rischio di una partita in paper non è rischio |
| Ordini reali | **nessun interruttore**: l'unica barriera era il valore di una colonna sul database | `MIKE_LIVE_ENABLED`, spento di default |

**`MIKE_LIVE_ENABLED` è l'ultima barriera prima di Betfair.** Mike piazza in REST diretto,
quindi non è coperto da `LIVE_ORDER_MODE` né dal rifiuto cross-mode del worker della coda,
che sono gli interruttori di Omega e Safe. Finché non è acceso nel `.env`, ogni tentativo
di piazzare un ordine reale solleva **prima** di toccare la rete. Non è una scomodità: è la
differenza fra «ho deciso di operare in live» e «il bot ha trovato un flag acceso da ieri».

**Il `mode` si congela sulla PARTITA quando viene armata.** Riportare il toggle su paper
**non** ferma quelle già avviate in live: continuano a coprirsi, chiudere e fare cash-out
con soldi veri. Ora è un log critico, un numero pubblicato e un banner rosso in pagina —
prima non lo diceva nessuno.

### 16.2 I difetti corretti, con la conseguenza misurata

Ordinati per quanto costavano. Ognuno ha il suo test in
`tests/test_mike_certificazione_2026_09_13.py` e `tests/test_mike_paper_vs_live_2026_09_13.py`.

| # | Difetto | Conseguenza misurata |
|---|---|---|
| 1 | le chiusure si piazzavano senza annullare le lay già **vive** sulla stessa selezione | **−9,39 €** su 10 di stake, e sull'esito **più probabile** |
| 2 | il regolamento contava zero una gamba a esito **ignoto** | `settled_pnl` sbagliato fino a **133 €**, e lo stop giornaliero ci crede |
| 2b | `pnl_indipendente_dal_risultato` chiudeva a 0,00 una partita con una gamba in riconciliazione | posizione forse **viva**, archiviata |
| 3 | con un ordine ignoto l'apertura veniva tolta ma lo **stato avanzava** lo stesso | **13,50 €** su 20 di stake, e il bot si dichiarava coperto |
| C-1 | il place-and-trim lasciava l'ordine **a riposo**; chi chiamava lo dava per rifiutato | ordine vivo su Betfair, invisibile → **posizione doppia** |
| C-2 | il sotto-minimo forzato sulla coda che Mike non legge | il TTL annullava la gamba mentre il runner la piazzava → **posizione doppia** |
| 4 | una gamba in riconciliazione **parzialmente** abbinata nascondeva il rischio | **99 € su 100** dichiarati zero |
| 6 | il flatten archiviava una perdita **già certa** | **30 €** spariti dalla liability e dal tetto per partita |
| 5 | seconda tranche che non parte mai senza l'orologio | posizione coperta a metà fino al fischio finale |
| 7 | la copertura ordinata comprava nei secondi del gol | ~**1 €** di sovracosto per 10 di stake |
| 8 | una probabilità `NaN` diventava quota 1000 | cash-out anticipato su un valore atteso inventato |
| 9 | le celle del cash-out non sommavano al totale | 1 centesimo, ma chi somma con gli occhi trova un altro numero |
| B1 | `onRequest` non restituiva una Promise | una chiusura **fallita** sembrava riuscita |
| B2 | in live non confermato i due click si consumavano nel nulla | il bottone diceva di aver chiuso, il servizio non riceveva niente |
| B3 | età dello scanner **fail-open** | feed illeggibile creduto fresco, bottoni con soldi veri accesi |
| UI#1 | l'età delle quote era **congelata** | servizio fermo, badge verde per sempre, e quel badge è il semaforo dei bottoni |

### 16.3 La UI, rifatta dove mentiva

* **«Operazioni»**: una riga per **partita** col netto delle sue operazioni (commissione già
  tolta), e il dettaglio **apribile** — prima cicli, poi i singoli ordini. Verde sopra zero,
  rosso sotto. Prima era un elenco piatto di cicli sparsi fra partite diverse, e mostrava
  gli stessi euro **due volte** (netto del ciclo sull'apertura, netto della gamba sulle
  chiusure) senza che niente lo dicesse.
* **«Risultati Pre-Match»** e **«Risultati Live»**: ogni partita finisce nei risultati della
  fase in cui ha operato, e in **entrambe** se ha operato in entrambe. La fase si deduce dal
  **ruolo della gamba che apre il ciclo**, non dall'orologio.
* **«Regolate» è stata rimossa**: era una terza lista di card che ripeteva le stesse partite.
* Il servizio **pubblica** quello che la UI ricalcolava per conto suo (posizione netta,
  prezzo medio, prezzo e size di chiusura, **eseguibilità** del cash-out, cicli col loro
  P&L, capitale impegnato, istante di pubblicazione). Due implementazioni della stessa cosa
  divergono sempre, e su una scheda di trading divergere vuol dire mentire.
* L'età delle quote **cresce da sola**: si calcola da `published_ts`, che è un istante
  assoluto. Un'età **assente** non è zero secondi — è «non lo so», e vale fail-closed.

### 16.4 🔴 LE 75 CONDIZIONI VANNO VERIFICATE PRIMA IN PAPER, POI IN LIVE

**Questo è il punto che chiude la certificazione, e non è ancora fatto.**

Il 13/09 sono state ripercorse **75 condizioni operative** — ogni ramo del codice, dal primo
ordine pre-match al regolamento — dando i dati all'engine vero e leggendo cosa decide. Tutte
e 75 sono risultate corrette, e l'utente le ha confermate una per una.

Ma quella era una verifica **a tavolino**: dati costruiti, passati alla funzione `decide`,
risposta letta. Non dice niente su cosa succede quando le stesse condizioni si presentano
**da sole**, su partite vere, con il feed vero e il servizio che gira.

Servono quindi **due passaggi, in quest'ordine**:

> **1. IN PAPER — su partite vere, col servizio in esecuzione.** Ogni condizione va
> osservata mentre accade: la riga di `mike_activity` che la registra, la riga di
> `mike_trades` che ne esce, lo stato in cui la partita finisce. Certifica che il codice
> faccia davvero, sul campo, quello che fa in laboratorio.
>
> **2. IN LIVE — su soldi veri.** Il paper resta una verifica contro il **nostro modello**
> di Betfair, non contro Betfair: non conosce le code, i rifiuti reali, la latenza vera, i
> mercati sospesi all'improvviso, i fill parziali che arrivano in ritardo.

> **REGOLA: Mike non è certificato per la produzione finché tutte e 75 le condizioni non
> sono state osservate almeno una volta IN PAPER sul campo, e poi almeno una volta IN LIVE,
> con l'esito atteso in entrambi i casi.**

Le 75 condizioni, per blocco (l'elenco operativo completo con i numeri attesi è nella
sessione del 13/09 e va riportato qui man mano che vengono verificate):

| Blocco | Condizioni | Che cosa certifica |
|---|---|---|
| 1 · Pre-match, chi entra e chi no | 1-13 | banda di prezzo, liquidità, spread, finestra, cicli, pausa, feed, mercato sospeso |
| 2 · Il ciclo pre-match | 14-22 | ingresso, TTL, fill parziale, uscita appoggiata, ciclo chiuso, rientro |
| 3 · L'ultimo ingresso (10′ dal fischio) | 23-27 | chiusura in profitto, HOLD in perdita, rientro in PERSIST, riprezzo |
| 4 · Il fischio d'inizio | 28-32 | passaggio in gioco, nessuna posizione, residuo PERSIST e grazia |
| 5 · La copertura su Over 4.5 | 33-43 | quando compra, quando aspetta, liquidità, riprezzo, troppi gol |
| 6 · Le uscite globali | 44-52 | cash-out a soglia, intelligente, HT/2T a modello, cap, finestre |
| 7 · Chiusura e residui | 53-56 | riprezzo, abbinamento, residuo minuscolo |
| 8 · Il re-ingresso su Under 4.5 | 57-63 | gol, minuto, prezzo, già fatto, chiusura precedente |
| 9 · Fine partita | 64-66 | mercato chiuso, punteggio, contabilità |
| 10 · Eccezioni e comandi | 67-75 | esito ignoto, cash out manuale, flatten, saltata, stato imprevisto |

Ogni condizione ha quindi **due caselle** da riempire: `paper` e `live`.

**Come si verifica una condizione.** Serve, per ognuna: la riga di `mike_activity` che la
registra, la riga di `mike_trades` con il suo esito, lo stato in cui la partita è finita, e
il confronto col numero che il modello aveva previsto. Uno scarto va indagato **prima** di
passare alla condizione successiva.

**Ordine consigliato.** Le condizioni 1-27 (pre-match) si verificano senza rischio in gioco:
sono il banco di prova naturale, e in paper si riempiono in una sola giornata di partite.
Le 28-43 richiedono di portare almeno una posizione in gioco. Le 44-66 arrivano da sole con
le partite. Le 67-75 (le eccezioni) **non si possono aspettare**: vanno provocate a mano,
una per una — in paper si provocano senza conseguenze, ed è lì che vanno provate tutte.

**Finché la colonna `paper` non è piena, non si passa in live. Finché la colonna `live` non
è piena, lo `stake` resta al minimo e `max_open_matches` a 1.**

### 16.5 Che cosa resta aperto

1. **Le 75 condizioni: prima in PAPER sul campo, poi in LIVE** (§16.4). È il lavoro
   principale, e la verifica in paper parte subito.
2. **`migrations/mike_aggregati_per_modalita_2026-09-13.sql` da applicare.** Senza, gli
   aggregati continuano a mescolare le due modalità. La migrazione fa `DROP` delle vecchie
   funzioni a zero argomenti: se in futuro qualcuno riapplicasse `mike_bot_v2.sql`, le due
   firme coesisterebbero e ogni chiamata diventerebbe ambigua — **riapplicare poi questa**.
3. **Lo storico non filtra per modalità** (`get_mike_daily`, `get_mike_day_trades`): il
   giorno della transizione sommerà euro veri e simulati, e per sempre.
4. **Il runner flumine è fermo dal 2 settembre.** Non serve al percorso REST di Mike, ma
   finché è fermo la coda non è una via di riserva.
5. **`MIKE_LIVE_ENABLED` va acceso a mano** quando si decide davvero di operare. Se il bot
   è in modalità live e l'interruttore è spento, la pagina lo dice con un banner.

---

## §17 IL SOFTWARE DEVE LASCIAR RESPIRARE IL DATABASE (13/09/2026)

### 17.1 Cosa è successo

Il 13/09, con l'app **spenta**, una lettura per chiave primaria su Supabase ha impiegato
**da 3 a 13 secondi**, e `omega_control` è andata in **timeout a 120 s**. Non era un
problema di query: era il **budget di IO su disco esaurito**
(`supabase.com/docs/guides/troubleshooting/exhaust-disk-io`). Quando quel budget finisce
l'istanza viene **strozzata**: i tempi di risposta esplodono, l'autovacuum salta, e da lì
in poi peggiora da sola.

Il contributo di Mike era questo, **ogni secondo**:

| lettura | cosa costava |
|---|---|
| `list_events(since=48h)` | `select *` su tutte le partite di due giorni, riga intera |
| `fetch_scan_rows()` | tutto il feed unico |
| RPC aggregati | scansione di `mike_trades` |
| righe ordine per partita | una query **per ogni partita viva**, a ogni giro |

86.400 giri al giorno, e Mike è **uno dei trenta servizi**. Il sintomo visibile in pagina
erano le partite ferme in `HOLD` con il calcio d'inizio passato da un'ora: il motore
decideva correttamente, ma il ciclo non chiudeva mai perché le letture non tornavano.

### 17.2 La regola

> **Non si chiede al database una cosa che il database non ha ancora avuto il tempo di
> cambiare.**

Non è un'ottimizzazione: è una **condizione di produzione**. Un'app che si blocca perché
il database è stanco non è pronta per il live.

### 17.3 Come è implementata (Mike)

Cinque parametri, tutti regolabili dalla UI (gruppo *rischio*), tutti con default
conservativi. **Nessuno di essi tocca la logica di trading**: cambiano solo *ogni quanto*
si rilegge.

| parametro | default | cosa governa | perché è sicuro |
|---|---:|---|---|
| `feed_cache_s` | 2 s | rilettura del feed unico | lo scanner non lo aggiorna più in fretta; la **freschezza** resta giudicata sull'`updated_at` della riga (`feed_max_age_s` = 15 s), non su quando l'abbiamo letta — una riga vecchia resta vecchia anche se la rileggiamo adesso |
| `events_reload_s` | 60 s | rilettura completa di `mike_events` | il servizio è l'**unico** che scrive quella tabella: fra una rilettura e l'altra la copia in memoria *è* la verità. Le richieste della UI passano da `mike_requests`, letta a **ogni** giro |
| `aggregates_cache_s` | 20 s | RPC degli aggregati | governano lo stop giornaliero e i numeri di testata: non sono decisioni al secondo. Dopo un'azione si **forza** il ricalcolo (`forza=True`) |
| `reconcile_every_s` | 30 s | riparazione specchio gambe ↔ righe, **per partita** | è una **rete di sicurezza**, non un passaggio del flusso: ripara le stesse cose ogni mezzo minuto |
| `idle_cycle_s` | 5 s | ritmo del ciclo a riposo | il ciclo pieno serve solo quando qualcosa si muove **da solo**: partita in gioco, ordine vivo sul book, richiesta dalla UI (`c_e_fretta`) |

Due scelte meritano di essere scritte, perché sono money-critical:

1. **Il feed ha la cache più corta di tutte** (2 s contro i 15 s della soglia di
   freschezza) perché è l'**unica lettura che influenza una decisione di mercato**.
2. **Se `list_events` fallisce e abbiamo già una copia in memoria, si continua a lavorare
   con quella** invece di fermare tutto. Una posizione aperta non può restare senza
   nessuno che la guardi perché una `select` è andata in timeout. Senza copia in memoria,
   il comportamento resta quello di prima: si salta il giro.

Il loop non rilegge più `mike_control` due volte per giro: `run_once` lo legge già, e i
parametri del giro precedente (`_ULTIMI_PARAMS`) bastano a decidere quanto aspettare.

### 17.4 Obblighi per chi tocca il codice

1. **Ogni nuova lettura periodica deve avere il suo parametro di cadenza.** Una `select`
   dentro un ciclo senza una cadenza dichiarata è un difetto, non una svista.
2. **Le cache sono variabili di modulo**: ogni test deve azzerarle. Per Mike lo fa
   `Betfair/mike/tests/conftest.py` (fixture autouse), che azzera anche i parametri di
   cadenza — quasi tutti i test simulano più cicli nello **stesso istante**, cosa che
   nella realtà non accade, e con le cache accese misurerebbero la cache invece del
   comportamento. Chi vuole provare le cache lo fa **apposta**, passando i parametri
   (`test_mike_respiro_db_2026_09_13.py`).
3. **Mai mettere in cache una scrittura, né una lettura che decide un ordine senza un
   criterio di freschezza sul dato stesso.**
4. `svuota_le_cache()` esiste per forzare un riallineamento immediato (riavvio,
   modifica fatta a mano sul database).

### 17.5 Resta da fare

- Estendere la stessa disciplina agli **altri servizi**. Safe ha già `poll_interval_s`
  regolabile e Omega i suoi intervalli di refresh, ma nessuno dei due ha ancora una
  **cache di lettura** con cadenza dichiarata.
- Misurare i tempi di risposta **dopo** il riavvio con il respiro attivo, e confrontarli
  con i 3-13 s misurati ad app spenta.
