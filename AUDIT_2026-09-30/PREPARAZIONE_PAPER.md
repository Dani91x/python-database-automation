# PREPARAZIONE AL PAPER DI MIKE - 30/09/2026 (delegato in SOLA LETTURA, letto alle 11:05 italiane)

Repo `python-database-automation`, master `a7e9f66` (10:53 del 30/09). Nessun file del repo toccato, nessuna scrittura sul
database, nessun processo avviato, nessuna chiamata a Betfair. Solo letture di Supabase col codice del repo
(`Betfair.mike.db`, `Betfair.safe_strategy.bot_db`, `fixture_predictions`, `omega_events`) e lettura del codice.
Tutti gli orari sono italiani (CEST = UTC+2) salvo dove scritto UTC.

## SINTESI (per chi ha fretta)

1. **9 righe paper aperte, tutte ORFANE**: 5 di Mike (2 partite) e 4 di Safe (4 partite), tutte del 26/09, partite finite da 3 giorni e mezzo.
   Non serve un intervento manuale SE Betfair restituisce ancora i mercati chiusi (non verificabile senza chiamarla): al primo giro del servizio
   il bot le regola da solo. Se i mercati non si leggono piu': Mike regola la partita A col ripiego sull'ultimo punteggio (giusto: 4 gol) ma manda la
   partita B in ERRORE (riga «da regolare»); Safe le lascia `open` per sempre con la riga di diario `market_missing`. In quei casi serve una regolazione
   manuale, decisione dell'utente. Il risultato vero delle 6 partite e' nel database (`fixture_predictions`): sezione 1.
2. **Parametri salvati**: 4 chiavi, 2 vincono su un valore di serie diverso: `stake` = 5,00 (serie 10,00) e `max_open_matches` = 2 (serie 10).
   `reentry_max_goals` e `cover_form` NON sono salvati: valgono i valori del codice (rientro con 2 gol ATTIVO; copertura = PUNTA Over 4,5,
   cioe' la banca Under 4,5 e' SPENTA). `uscite_automatiche` = false (= serie). Modalita' `paper`, stato `stopping` (app spenta dal 26/09 17:40 UTC).
   **Attenzione**: con `max_open_matches` = 2 e le due partite del 26/09 ancora non regolate, Mike non puo' aprire nessuna partita nuova.
3. **Calendario**: la tabella del feed di Betfair (`safe_strategy_scan`) e' ferma al 26/09 17:40 UTC: le partite «viste da Mike» oggi NON si
   leggono senza lo scanner acceso. Ho elencato dal DB dei pronostici (`fixture_predictions`) le partite di oggi e domani con una quota teorica
   dell'Under 3,5 (STIMA mia, non il prezzo Betfair). Le prime partite plausibili per Mike sono le Under 21 delle 18:00 (ingresso dalle 17:00).
4. **Build dell'app VECCHIA**: `frontend/dist` e' del 30/09 10:26; l'ultimo commit su `frontend/src` e' delle 10:53 (etichetta «LINEA DECISA DAI GOL»).
   Serve `npm run build` PRIMA di aprire l'app per il paper (sezione 5).

---

## 1. RIGHE PAPER APERTE DAL 26/09

Lettura: `Betfair.mike.db.open_trades()` (stati `open`/`hedged`/`pending`) e `Betfair.safe_strategy.bot_db.open_trades()` (`open`/`hedged`).
Trovate 5 + 4 = 9, tutte `mode = paper`, `status = open`. Nessuna `pending`, nessuna `hedged`.
Il controllo (`mike_control`) e' `stopping` da allora: l'ultimo battito di Mike e' del 26/09 17:40:13 UTC (19:40 italiane): l'app e' stata chiusa
mentre le partite erano al 75'-83'. Nessuno le ha piu' regolate.

Risultati veri (da `fixture_predictions.result_*`, stato `FT`). Il bot NON li usa, ma permettono al coordinatore di controllare il regolamento.

### 1.1 MIKE (5 righe, 2 partite)

**Partita A - Latvia U21 v Germany U21** (event 36109477, UEFA U21 Euro Qualifiers), KO 26/09 18:00 italiane (16:00 UTC).
Stato in `mike_events`: `SETTLING`, modo `paper`, ultimo aggiornamento 17:40:21 UTC; `ctx.settle_first_ts` = 17:35:47 UTC del 26/09 (l'istante in cui
il 3,5 chiuso dopo il quarto gol e' stato scambiato per «partita chiusa»: il difetto del mercato deciso, oggi corretto su master); `goals` 4,
`last_goals` 4, `seen_inplay` vero. Risultato finale VERO: **0-4 (4 gol)**.
L'ultimo scan (17:40 UTC, 80') mostra Under/Over 3,5 in `CLOSED` e la 4,5 `OPEN`: e' la conferma, sul dato di produzione, che lo scanner scrive CLOSED
sul 3,5 dopo il quarto gol (era il punto «non verificato» di `AUDIT_2026-09-30/MIKE_MERCATO_DECISO.md` sez. 12).

| id | ruolo | mercato | selezione | lato | prezzo | size chiesta | abbinato | stato | piazzata (UTC / italiane) |
|---|---|---|---|---|---|---|---|---|---|
| 5077 | under_entry | OVER_UNDER_35 (1.262857494) | Under 3.5 | back | 2,18 | 5,00 | 5,00 | open | 26/09 15:18:51 / 17:18 |
| 5078 | under_second | OVER_UNDER_35 | Under 3.5 | back | 1,25 | 2,50 | 2,50 | open | 26/09 16:03:18 / 18:03 |
| 5080 | over_cover | OVER_UNDER_45 (1.262857491) | Over 4.5 | back | 1,72 | 6,40 | 6,40 | open | 26/09 16:05:17 / 18:05 |
| 5081 | over_cover | OVER_UNDER_45 | Over 4.5 | back | 1,71 | 6,67 | 6,67 | open | 26/09 16:08:24 / 18:08 |

`settled_at`, `betfair_updated_at`, `pnl_betfair` nulli; `pnl` = 0,0; `bet_id` nullo; `meta.fill = paper_fill:execution_mode_rest`; `origin = auto`.
(La riga 5079 e' dell'evento 35925542, San Marino v Finland, gia' `won` +5,76: non e' aperta.) La scheda a 75' mostrava una proposta di uscita
in perdita (`uscita_proposta` 17:35:15 UTC, cash out -7,02) che nessuno ha firmato prima della chiusura dell'app.
P&L atteso di regolamento coi 4 gol: **-20,57** (Under 3,5 persa -7,50, Over 4,5 persa -13,07; e' `pnl_by_total['4']` della scheda).

**Partita B - MVV Maastricht v Helmond Sport** (event 36093027, Dutch Eerste Divisie), KO 26/09 20:00 italiane (18:00 UTC).
Stato: `PRE_OPEN` (mai in gioco: l'app si e' fermata alle 19:40 italiane, 20 minuti prima del fischio), `seen_inplay` assente. Risultato finale VERO:
**2-0 (2 gol)**.

| id | ruolo | mercato | selezione | lato | prezzo | size chiesta | abbinato | stato | piazzata (UTC / italiane) |
|---|---|---|---|---|---|---|---|---|---|
| 5082 | under_entry | OVER_UNDER_35 (1.262856594) | Under 3.5 | back | 1,48 | 5,00 | 5,00 | open | 26/09 17:21:06 / 19:21 |

Con 2 gol l'Under 3,5 e' vinta: P&L atteso **+2,28** (`pnl_by_total['2']`, commissione 5 % inclusa). Sulla scheda c'era la proposta di green-up
(`green_pre|c0`, lay 5,07) mai firmata/abbinata.

### 1.2 SAFE (4 righe, 4 partite, strategia `esatto`, tutte lay su «Altro risultato»)

| id | event_id | partita (KO italiane) | mercato | selezione | lato | prezzo | size (abbinata) | stato | piazzata (UTC) | aggiornata (UTC) | risultato finale VERO |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 359 | 35926090 | Bulgaria - Luxembourg (18:00) | CORRECT_SCORE 1.262661603 | Altro risultato Ospite | lay | 60,00 | 2,00 (2,00) | open | 26/09 16:50:55 (48') | 16:51:01 | 1-2 |
| 361 | 36090836 | Faroe Islands - Kazakhstan (18:00) | CORRECT_SCORE 1.262661513 | Altro risultato Casa | lay | 30,00 | 2,00 (2,00) | open | 26/09 16:57:23 (53') | 16:57:29 | 1-1 |
| 362 | 36114311 | Kuwait - Iraq (17:55) | CORRECT_SCORE 1.262898785 | Altro risultato Ospite | lay | 60,00 | 2,00 (2,00) | open | 26/09 17:23:18 (65') | 17:23:24 | 2-3 |
| 363 | 35925583 | Iceland - Estonia (18:00) | CORRECT_SCORE 1.262661536 | Altro risultato Casa | lay | 34,00 | 2,00 (2,00) | open | 26/09 17:25:20 (66') | 17:25:25 | 1-1 |

Tutte con `bet_id` finto (`10000000000x`), `meta.fill = flumine_paper`, `percorso = canale`, `origin = auto`. In tutte e quattro il risultato finale e'
uno dei punteggi in griglia (1-2, 1-1, 2-3, 1-1), quindi «Altro risultato» ha PERSO e la banca ha vinto: atteso +2,00 lordi (+1,90 con commissione 5 %)
a riga, +7,60 in tutto. E' un calcolo mio dalla regola del mercato, NON letto da un regolamento. L'ultimo scan (17:40 UTC) le mostrava ancora aperte (77'-83').

### 1.3 Che cosa farebbe il codice di oggi (master `a7e9f66`) al riavvio

**Mike** (`Betfair/mike/service.py`: `run_once` righe 3592-3835, giro per partita da riga ~4250):
1. `list_events` (`Betfair/mike/db.py` righe 99-113) restituisce SEMPRE le partite NON terminali, di qualunque eta' (correzione D1 del 28/09: e' proprio
   il caso di queste 5 righe). Le 2 partite tornano quindi nel ciclo. Il regolamento e le protezioni girano anche col bot su «Fermo»: `running` falso
   impedisce solo le aperture (`run_once` righe 3624-3626 e 3742-3744).
2. Costanti (`service.py` righe 51-56): `_ROW_MISSING_GRACE_S = 600` (riga assente dal feed da meno di 10 minuti = transitoria), `_MATCH_OVER_S = 3 h`
   dal KO (oltre, la partita e' finita comunque), `_MATCH_LIKELY_OVER_S = 100 min` (vista in gioco e KO + 100'), `_SETTLE_MAX_WAIT_S = 2 h`,
   `settle_confirm_s = 60 s` fra due letture REST. Con la riga assente dal feed e il KO di 4 giorni fa, `absent_closed` e' vero SUBITO (KO + 3 h superato):
   niente attesa dei 10 minuti. Partita chiusa -> lettura REST dei due mercati (`market.read_book`: e' una chiamata VERA a Betfair, throttle 60 s) e `_settle_trades`.
3. Se Betfair restituisce i mercati `CLOSED` con i vincitori: `final_total_from_books` ricava il totale e Mike regola da solo (A: totale «4», -20,57; B: Under 3,5
   vinta, +2,28), scrive la riga di diario `settled` («REGOLATA»), le righe passano a `won`/`lost` con `pnl` e `settled_at`, l'evento a `SETTLED`.
   Tempo: dal primo giro del servizio, da una decina di secondi a uno-due minuti (throttle).
4. Se i libri NON sono leggibili (mercati chiusi da 4 giorni: Betfair puo' non restituirli piu'):
   - Partita A: `settle_first_ts` e' vecchio di 3 giorni, il tetto di 2 h e' gia' scaduto: ripiega SUBITO sull'ultimo punteggio visto (`last_goals` = 4,
     `seen_inplay` vero), scrive `settle_fallback` («REGOLAMENTO DA FEED») e regola come 4 gol. **Coincide col risultato vero (0-4)**: -20,57.
   - Partita B: mai vista in gioco, niente ripiego sul punteggio; il P&L dipende dal risultato (Under 3,5 aperta), quindi `_marca_righe_non_regolate` marca la riga
     5082 «da regolare», scrive `error` `settle_timeout` (critico, «regolamento non determinabile») e la partita va in **ERROR** (terminale): la riga resta `open` e
     nessuno la richiude piu'. Serve un intervento manuale.
     Attenzione: prima di arrivare li' il tetto di 2 h riparte dal PRIMO tentativo di oggi (`settle_first_ts` nuovo): l'ERROR arriva circa 2 ore dopo il primo giro, non subito.
5. Non verificato (non l'ho potuto simulare): se il servizio parte PRIMA dello scanner, `safe_strategy_scan` contiene ancora le 33 righe stantie del 26/09
   (17:40 UTC), comprese queste due partite. Con una riga presente, anche stantia, `row is None` e' falso: `absent_closed` resta falso e le partite non vanno al
   regolamento finche' lo scanner non parte e le cancella (all'avvio `purge_orphans`, `Betfair/safe_strategy/service.py` righe 2115-2127). Che cosa fa il motore
   con una riga stantia e stato `SETTLING` non l'ho provato. Consiglio: scanner acceso PRIMA di Mike.

**Safe** (`Betfair/safe_strategy/bot_service.py`): `settle_open` (riga 1887) gira a OGNI ciclo, «SEMPRE» (chiamata alla riga 9746), su tutte le righe
`open`/`hedged` di qualunque eta', senza finestre di tempo e senza guardare lo stato del bot. Per le aperture senza chiusure: `_read_markets_batch` (una
`listMarketBook` REST per tutti i mercati); se il mercato risulta `closed` -> `X.settle_position` (paper compreso) con esito dai runner `WINNER/LOSER`. Se il mercato non si
legge: `_market_missing`; dopo 3 letture consecutive fallite (`MARKET_MISSING_MIN_FAILS`) scrive `meta.market_missing_since` e la riga di diario `market_missing`
(ripetuta ogni 5 minuti). NON c'e' un tetto di tempo ne' un errore terminale: le righe restano `open` per sempre, non con un numero inventato. Non ho trovato in Safe
un equivalente di `_MATCH_OVER_S` per le righe orfane.

### 1.4 Che cosa deve fare l'utente (io non ho chiuso ne' regolato niente)

- Ricostruire l'app (`npm run build`), poi avviare l'app: parte lo scanner (pulisce le righe stantie), poi i servizi. Mike e Safe possono restare su «Fermo»: le
  righe si regolano lo stesso. Non premere «Chiudi»/cash out su queste righe (mercati chiusi).
- Il coordinatore, dopo qualche minuto, controlla nel DB che le 9 righe siano passate a `won`/`lost` con `settled_at` valorizzato e che il P&L coincida con
  gli attesi: Mike A -20,57, Mike B +2,28, Safe +1,90 x 4 (attesi, non letti da un regolamento). Diario: Mike `settled`; Safe `settle_position`/`settled`.
- Se dopo qualche minuto restano `open`: Mike, guardare `mike_events.state` (`ERROR`) e la riga `error` con `reason: settle_timeout`; Safe, la riga `market_missing`.
  Serve allora una decisione dell'utente (regolare a mano con i risultati veri, oppure annullare le righe).
- Non aspettarsi ingressi nuovi di Mike finche' le due partite non sono `SETTLED`: con `max_open_matches` = 2 salvato le due partite del 26/09 occupano i due
  posti (all'ultimo battito `motivo_blocco = "tetto partite raggiunto: 2 su 2 in paper"`, `partite_esposte = 2`). Se restassero in ERROR, il tetto non le conta piu'
  (stato terminale), ma la loro riga resta aperta nel DB e negli aggregati di rischio.

---

## 2. PARAMETRI SALVATI (`mike_control`, id 1)

`status` = `stopping` (al primo giro del servizio diventa `stopped`: `run_once` righe 3829-3835). `mode` = `paper`. `error` nullo. `started_at` 26/09 17:21:03 UTC,
`heartbeat_at` 26/09 17:40:13 UTC. `stats.live_abilitato` = true (il flag del processo di quel giorno; la modalita' resta paper), `stats.day_pnl` +3,66,
`realized_total` +11,80.

`params` salvato: 4 chiavi soltanto.

| chiave | salvato | serie (`merge_params(None)`) | effetto |
|---|---|---|---|
| `stake` | 5,0 | 10,0 | **VINCE il salvato**: ingressi da 5,00 (meta' dello stake di serie) |
| `max_open_matches` | 2 | 10 | **VINCE il salvato**: solo 2 partite con posizione alla volta (oggi sara' il collo di bottiglia, vedi 1.4) |
| `uscite_automatiche` | false | false | uguale: uscite in perdita = proposte da firmare; le uscite in profitto le esegue il bot |
| `entry_hours_before_ko` | 1,0 | 1,0 | uguale |

Chiavi NON salvate: valgono i valori di serie (`Betfair/mike/config.py` `PARAM_SPEC`).

| chiave | valore oggi | nota |
|---|---|---|
| `reentry_max_goals` | 2 | rientro con 1 o 2 gol ATTIVO (la migrazione `mike_reentry_max_goals_2026-09-29.sql` qui non cambia nulla) |
| `cover_form` | `back_over45` | **la banca Under 4,5 e' SPENTA**: la copertura e' la PUNTA Over 4,5 (minimo 2,00, passi 0,50). Il pannello ha il campo (`frontend/src/lib/mike.ts` riga 497). La decisione dell'utente delle 09:25 (banca di serie: SI') NON e' ancora su master (`MIKE_P5_5.patch` + `MIKE_P6_6.patch` in `AUDIT_2026-09-29/in_attesa_del_via/`, da integrare dopo un replay del coordinatore). Per provarla oggi va salvata dal pannello: scelta dell'utente |
| `cover_max_goals` | 2 | |
| `pre_last_entry_min` | 10 | ultimo ingresso a 10' dal fischio |
| `pre_entry_price_min` / `max` | 1,30 / 3,00 | banda dell'Under 3,5 |
| `pre_exit_mode` | `resting` | banca a +2 tick appoggiata (`pre_green_ticks` 2) |
| `pre_max_cycles` | 10 | |
| `daily_loss_stop` | 50,0 | |
| `max_liability_per_match` | 0 (spento) | |
| `event_loss_cap_pct` | 100 | |
| `last_entry_persist` | true | |

Se il paper deve mostrare il comportamento «di serie» (stake 10, fino a 10 partite) l'utente deve decidere se togliere `stake` e `max_open_matches`
salvati dal pannello: non li ho toccati. Nessun'altra chiave salvata vince su un valore cambiato di recente.

---

## 3. LISTA DI CONTROLLO DEL PAPER (per l'utente, non tecnica)

Come leggerla. Ogni caso ha: cosa succede, cosa devi vedere (in quale pagina), quando e' GIUSTO, quando e' un DIFETTO, e in fondo dove il coordinatore
lo verifica nel database. Le etichette in maiuscolo sono quelle scritte nel diario delle attivita' di Mike (Control Room e scheda della partita; sono
in `frontend/src/lib/mike.ts` `MIKE_ACTIVITY_EXTRA` e in `frontend/src/lib/tradeStatus.ts` `ACTIVITY_BASE`). Le etichette nuove (`LINEA DECISA DAI GOL`)
compaiono solo dopo `npm run build`.

Prima di tutto (valido per ogni caso): la partita deve comparire nella pagina di Mike come «ARMATA» ~1 ora prima del fischio; il badge del servizio non deve
essere «FEED FERMO»; il tetto partite (2) non deve dire «TETTO PARTITE: NON ENTRA» per colpa delle partite del 26/09 (sezione 1).

### (a) Partita con 4 gol e posizione coperta: firma dell'uscita che arriva al mercato

- Cosa succede: Under 3,5 + Over 4,5 abbinati (stato «IN GIOCO · COPERTO»); arriva il quarto gol. Betfair CHIUDE il mercato Under/Over 3,5 (Under persa), l'Over 4,5
  resta aperto. Mike non deve credere che la partita sia finita ne' che il flusso prezzi sia fermo: continua sull'Over 4,5.
- Cosa devi vedere: nel diario UNA riga **LINEA DECISA DAI GOL** (kind `mercato_deciso`; mercato `OU35`, `stato_mercato` `SUSPENDED` o `CLOSED`, `esito` `{"OU35|UNDER": "persa"}`);
  poi le proposte **USCITA PROPOSTA: DECIDI TU** (`uscita_proposta`, evidenziata) che continuano a comparire; quando la firmi (Control Room, «Chiudi»/approva un clic
  in paper): **USCITA APPROVATA (utente)** (`uscita_approvata`), poi **ORDINE**/`place` e **USCITA ESEGUITA SU APPROVAZIONE** (`uscita_eseguita_su_approvazione`), cioe' una gamba
  `over_close` (chiusura dell'Over 4,5) e la riga passa a chiusa. La firma vale 120 s (`APPROVAZIONE_TTL_S`): se la lasci scadere ricompare la proposta.
- Giusto: una sola riga `mercato_deciso` per linea; nessun «FLUSSO PREZZI INTERROTTO» riferito al 3,5; la partita NON passa a «IN REGOLAMENTO» finche' la 4,5 e' aperta;
  la firma produce un ordine sull'Over 4,5 entro pochi secondi; le uscite in PERDITA non partono senza firma (`uscite_automatiche` = false), quelle in profitto si.
- Difetto: **FLUSSO PREZZI INTERROTTO** (`flusso_interrotto`) con l'id del mercato 3,5; **NON ABBINATO** (`no_fill`) con `reason: feed_stantio` dopo la firma (e' esattamente il difetto
  del 26/09: firma alle 19:25:34 su -2,54, 21 tentativi rifiutati, finale -14,00); stato «IN REGOLAMENTO» (`settle`, `settling_reverted`/«REGOLAMENTO ANNULLATO») con la 4,5 aperta;
  proposta che non si firma mai (pulsante spento).
- Il coordinatore verifica: `mike_activity` dell'evento: una `mercato_deciso` (payload `market`, `goals` 4, `stato_mercato`, `esito`); zero `flusso_interrotto` con `mercati` = id del 3,5;
  zero `settle`/`settling_reverted` prima del fischio finale; dopo la firma `uscita_approvata` -> `uscita_eseguita_su_approvazione`; `mike_trades`: riga `over_close` (o `manual_close`),
  `closes_trade_id` = riga `over_cover`; nessun `no_fill`.

### (b) Ultimo ingresso a 10 minuti dal fischio

- Cosa succede: a KO - 10' (`pre_last_entry_min`) se Mike e' piatto sulla partita entra come sempre (punta Under 3,5 con lo stake) passando da tutti i controlli d'ingresso; all'abbinamento appoggia la
  banca a 2 tick sotto, che resta fino al fischio. Dal 30/09: se un controllo momentaneo fallisce (pausa dopo un giro chiuso, libro assente, spread, prezzo fuori banda,
  liquidita', prezzi non vivi, mercato sospeso) NON rinuncia: riprova a ogni giro fino al fischio. Rinuncia solo per «max cicli», «cap liability partita», mercato chiuso, veto P calibrata Under 3,5.
- Cosa devi vedere: stato **ULTIMO INGRESSO** (`PRE_LAST_ENTRY_PENDING`, se il motore lo mostra) / **UNDER 3.5 APERTO**; nel diario **FASE** con motivo che comincia con «ultimo ingresso:»
  (es. «ultimo ingresso: ingresso ciclo N», oppure «ultimo ingresso: ...: riprovo al prossimo giro» = ATTESA, va bene), poi **ORDINE**/`place` Under 3.5 back (ruolo `under_entry`, oppure `under_last`),
  **ORDINE APPOGGIATO** (`place_resting`) della banca a 2 tick sotto, eventualmente **APPOGGIATA ABBINATA** (`fill_resting`). Stato **TIENE FINO AL FISCHIO** (`HOLD`) se ha rinunciato per sostanza.
- Giusto: l'ingresso arriva tra KO-10' e il fischio o resta in attesa con «riprovo»; MAI un ingresso dopo il fischio (Mike non entra da zero in gioco); una riga `place` sola per ingresso.
- Difetto: nessun tentativo dopo il segno con Mike piatto e prezzo in banda; «ULTIMO INGRESSO» senza mai una riga `place` ne' un motivo; due ingressi nello stesso minuto (duplicato: `place_saltato`
  «DUPLICATO EVITATO» e' il freno, se compare e' normale una volta); ingresso con prezzo fuori dalla banda 1,30-3,00.
- Il coordinatore verifica: `mike_activity` kind `state` con `reason` che comincia per `ultimo ingresso`; `mike_trades` riga `under_entry`/`under_last` con `placed_at` fra `ko_at - 10 min` e `ko_at`,
  `price` in banda; poi banca `under_green` lay a +2 tick sotto (`price`), `status` open finche' non si abbina.

### (c) Banca Under 4,5 abbinata e chiusa

- **Condizione preliminare**: oggi `cover_form` = `back_over45` (punta Over 4,5). La banca Under 4,5 si vede SOLO se l'utente salva `cover_form = lay_under45` dal pannello, oppure dopo
  l'integrazione di `MIKE_P5_5.patch` + `MIKE_P6_6.patch`. Con la forma di serie di oggi questo caso NON si presenta: e' la punta Over 4,5 (etichetta **COPERTURA OVER 4.5**, kind `cover`).
- Cosa succede (forma banca): arriva un gol (`cover_max_goals` 2) mentre l'Under 3,5 e' scoperto: dopo il ritardo (`cover_postgoal_delay_s` 45 s, a due tranche se il gol e' precoce) Mike mette una BANCA
  sull'Under 4,5 (rischio ~ perdita Under 3,5 x 1,2 / (1 - commissione), meno cio' che e' gia' coperto; importo esatto al centesimo, minimo 0,50). Sul banco: banca 12,63 a 1,33, rischio 4,17.
- Cosa devi vedere: **COPERTURA OVER 4.5** (`cover`) con forma banca, riga di ordine `over_cover` lato **BANCA** su Under 4.5 (`meta.cover_form = lay_under45`), stato «IN GIOCO · COPERTO»;
  poi, se chiudi (cash out): gamba `over_close` sulla stessa selezione e **CASH OUT ESEGUITO**. Mai due banche sul 4,5 (`place_saltato` se ci prova).
- Giusto: una sola banca per tranche, abbinata (`fill_resting` o `place` con `size_matched` = chiesto), rischio dichiarato coerente con la perdita coperta; cash out dopo la copertura -0,61 sul banco.
  Se Betfair rifiuta: **RIFIUTATO DA BETFAIR** (`place_rifiutato`) e la scheda deve dire «la copertura NON e' a mercato» (sopra 3 rifiuti con lo stesso codice si ferma: `cover_rifiuti_max`).
- Difetto: banca piazzata e mai riletta (**ORDINE IN VERIFICA** `reconcile_pending` che non si chiude); due banche sullo stesso mercato; importo sotto il minimo senza `size_legalized`; copertura assente
  dopo un gol con Mike scoperto per piu' di ~3 minuti senza una riga che spieghi perche' (attesa «intelligente» = `cover_wait`).
- Il coordinatore verifica: `mike_trades` `role = over_cover`, `side = lay`, `market_type = OVER_UNDER_45`, `selection_name = Under 4.5 Goals`, `meta.cover_form = lay_under45`, `size_matched` = `size`;
  chiusura: `role = over_close` con `closes_trade_id` valorizzato; `mike_activity` `place`/`cover`/`cashout_done`.

### (d) Rientro con 1-2 gol

- Cosa succede: dopo aver chiuso in profitto un ciclo (green-up) Mike e' piatto; se la partita ha 1 o 2 gol (`reentry_max_goals` = 2, di serie), il minuto e' entro il 45' (`reentry_until_min`), l'Under 4,5
  ha un prezzo sopra quello d'ingresso e c'e' liquidita', entra con una punta Under 4,5 (stake come da `stake`, oggi 5,00) e appoggia la banca del green a +2 tick.
- Cosa devi vedere: stati **RE-INGRESSO IN CORSO** (`REENTRY_PENDING`) poi **RE-INGRESSO UNDER 4.5** (`REENTRY_OPEN`); diario **ORDINE** ruolo `reentry` back Under 4.5, poi **ORDINE APPOGGIATO** (`reentry_green`),
  eventualmente **APPOGGIATA ABBINATA**. Se il 3° gol arriva: uscita in perdita = proposta da firmare; in profitto a tempo la esegue il bot (decisione dell'utente 30/09 punto 8).
- Giusto: al massimo UN rientro per partita (`reentry_done`); con 3 o piu' gol niente rientro («flat: N gol fuori range re-ingresso»); mai rientro se Mike e' ancora esposto.
- Difetto: rientro con 3+ gol o dopo il 45'; due rientri; rientro con il mercato Under 4,5 sospeso/chiuso; banca del green mai piazzata.
- Il coordinatore verifica: `mike_trades` `role = reentry` (market OVER_UNDER_45, Under 4.5, back) e `reentry_green`; `mike_events.ctx.reentry_done` vero; `mike_activity` `state` con `reason` «re-ingresso Under 4.5».

### (e) Regolamento a fine partita con le righe scritte giuste

- Cosa succede: fine partita (o mercato chiuso con vincitori), Mike legge i due mercati, calcola il totale, regola tutte le righe.
- Cosa devi vedere: stato **IN REGOLAMENTO** poi **REGOLATA** (`SETTLED`); nel diario **REGOLATA** (`settled`, payload `total`, `pnl`, `per_leg`); ogni riga della partita `won`/`lost`/`void` con
  `pnl` e `settled_at`; nulla resta `open`/`pending`. La pagina «storico» ora mostra il giorno del REGOLAMENTO (P6 blocco 4, con la migrazione `mike_storico_giorno_regolamento_2026-09-29.sql`: va applicata).
- Giusto: somma dei `pnl` delle righe = `mike_events.settled_pnl` = netto atteso dal totale gol (controllabile con `pnl_by_total` della scheda, commissione 5 %); le gambe mai piazzate valgono zero
  (**GAMBE MAI PIAZZATE**); annullo di un ordine ancora vivo sul 4,5 prima di regolare.
- Difetto: **ERRORE** con `settle_timeout` («regolamento non determinabile»); **REGOLAMENTO DA FEED** (`settle_fallback`, ripiego sull'ultimo punteggio: ammesso ma da guardare); **COMMISSIONE NON UNIFORME**;
  righe ancora `open` a partita `SETTLED`; **REGOLAMENTO ANNULLATO** (`settling_reverted`) a partita davvero finita; ordini vivi sul 4,5 dopo la fine (limite noto: nel ramo regolamento gli annulli della decisione
  SETTLING non vengono eseguiti, reperto C1 della revisione critica `AUDIT_2026-09-30/REVISIONE_CRITICA_MIKE_29_09.md`).
- Il coordinatore verifica: `mike_trades` dell'evento: stato, `pnl`, `settled_at`; `mike_events.state = SETTLED`, `settled_pnl`; `mike_activity` `settled`; confronto col risultato vero in `fixture_predictions.result_*`.

### (f) Sospensione con banca appoggiata

- Cosa succede: la banca a +2 tick (green-up) e' appoggiata sul book e il mercato si sospende (gol, o fischio): Betfair fa SCADERE gli ordini non abbinati (LAPSE) alla sospensione.
  Al fischio d'inizio la banca pre-partita NON viene annullata (decisione utente 30/09 punto 9, piano M2.1).
- Cosa devi vedere: **MERCATO SOSPESO** (`mercato_sospeso`, critico) o **APPOGGIATA: SOSPENSIONE IN CORSO** (`resting_in_sospensione`); alla riapertura **ORDINE RILETTO ALLA RIAPERTURA**
  (`rilettura_alla_riapertura`) con l'esito letto da Betfair; se e' scaduto **ORDINE SCADUTO NELLA SOSPENSIONE** (`ordine_scaduto_alla_sospensione`, critico) e la banca viene ripresentata al giro dopo.
- Giusto: l'esito lo scrive Betfair (non un'ipotesi del bot): la riga riflette lo stato reale dell'ordine; nessun nuovo ordine sullo stesso mercato mentre e' sospeso (**MERCATO SOSPESO** con «copertura ... finche' non riapre»).
- Difetto: banca «abbinata» dal bot durante la sospensione; nessuna rilettura dopo la riapertura; due banche vive; **ANNULLO: ESITO DA BETFAIR** (`cancel_esito`) non confermato e la riga risulta annullata lo stesso.
- Il coordinatore verifica: `mike_activity` sequenza `mercato_sospeso` -> `rilettura_alla_riapertura` [-> `ordine_scaduto_alla_sospensione` -> `place_resting`]; `mike_trades` `under_green` con `size_matched` coerente
  con la rilettura; nessun `reconcile_pending` che resti aperto.

### (g) Linea decisa dai gol (riga di diario «LINEA DECISA DAI GOL»)

- Cosa succede: un gol supera una linea (4 gol: 3,5; 5 gol: anche 4,5). Betfair chiude quel mercato pochi secondi dopo. Mike lo scrive UNA volta per linea (`extra.linee_decise`) e continua sull'altra.
- Cosa devi vedere: nel diario **LINEA DECISA DAI GOL** (badge azzurro, kind `mercato_deciso`; payload `market` OU35/OU45, `market_id`, `goals`, `stato_mercato`, `esito` per le gambe aperte «vinta»/«persa», `state`).
- Giusto: una riga per linea e per partita; a 5 gol due righe (3,5 e 4,5) e solo allora la partita puo' andare in regolamento; nessun `flusso_interrotto` in quel momento.
- Difetto: nessuna riga dopo il 4° gol con posizione sull'Under 3,5; righe ripetute a ogni giro; «LINEA DECISA» seguita da «IN REGOLAMENTO» con la 4,5 aperta; se l'app non e' ricostruita la riga compare con il nome
  tecnico invece dell'etichetta (sezione 5).
- Il coordinatore verifica: `mike_activity` `kind = mercato_deciso`: una riga per `market`; `mike_events.ctx.linee_decise` = elenco delle linee scritte.

Altri segnali di difetto da guardare in ogni caso (catalogo): **ERRORE** critico (`error`), **ORDINE IN VERIFICA** (`reconcile_pending`) che non passa, **LINEA ASSENTE NEL FEED** (`feed_line_missing`),
**POSIZIONE DI CONTO NON LETTA**, **FLUSSO FERMO E REST MUTO: POSIZIONE SCOPERTA** (`flusso_interrotto_senza_rest`): con una posizione aperta sono i piu' gravi.

Nota sui tempi: i casi (a), (d), (f), (g) dipendono dai gol veri: non si possono programmare. (b) e' pianificabile (KO - 10'), (e) arriva a fine partita.

---

## 4. CALENDARIO: partite di OGGI (30/09) e DOMANI (01/10) che Mike potrebbe vedere

Fonte e limite. La tabella del feed di Betfair che Mike legge (`safe_strategy_scan`, 33 righe) e' ferma al 26/09 17:40 UTC (lo scanner e' spento dal 26/09): NON contiene le partite di oggi e le
quote Under 3,5 di Betfair non sono leggibili senza accendere lo scanner o chiamare Betfair (non l'ho fatto). Ho quindi usato il DB dei pronostici (`fixture_predictions`, API-Football, tutte le partite del mondo) e ho
stimato la quota Under 3,5 dai gol attesi (`lambda_casa + lambda_trasferta`, Poisson indipendente: P(Under 3,5), quota teorica = 1/P, senza margine). E' una STIMA: la quota vera di Betfair sara' un po' diversa
e Betfair non ha mercati Over/Under 3,5 e 4,5 su tutte queste partite (es. molte categorie giovanili sudamericane, campionati minori). Mike arma una partita quando: KO entro 1 ora (`entry_hours_before_ko`), non in gioco,
entrambe le linee 3,5 e 4,5 nel feed, poi entra solo con Under 3,5 in banda 1,30-3,00 e i controlli d'ingresso.

Adesso sono le 11:05 del 30/09: la prima partita con dati e' alle 14:00 (ingresso dalle 13:00). Il DB dei pronostici ha per il 01/10 solo le partite notturne (dopo mezzanotte): quelle diurne di domani non sono ancora caricate.
Piu' probabili su Betfair (competizioni con mercato Over/Under noto al circuito): Under 21 europee delle 18:00-21:00, National League inglese delle 20:45 (Eastleigh - Southend, Tamworth - Sutton Utd), qualche campionato
maggiore/minore europeo. Il giudizio finale lo dara' lo scanner acceso (pagina di Mike, lista «partite armate»).

### 4.1 Partite con gol attesi nel DB (65): 50 hanno una quota teorica dentro la banda 1,30-3,00 dell'Under 3,5

| Ora (italiana) | Partita | Lega (id) | Gol attesi | P(Under 3,5) | Quota teorica | Nella banda 1,30-3,00? |
|---|---|---|---|---|---|---|
| 30/09 14:00 | Bhutan U19 - Thimphu | 1031 | 3.25 | 0.592 | 1.69 | si |
| 30/09 15:00 | Guarany U20 - Jaguar U20 | 1088 | 3.47 | 0.542 | 1.84 | si |
| 30/09 15:00 | Iskra - Grbalj | 356 | 2.2 | 0.819 | 1.22 | no (troppo bassa) |
| 30/09 15:00 | Madureira U20 - Vasco da Gama U20 | 1114 | 2.61 | 0.734 | 1.36 | si |
| 30/09 15:00 | Mladost Lješkopolje - Jedinstvo | 356 | 3.2 | 0.602 | 1.66 | si |
| 30/09 15:00 | Mogren - Lovćen | 356 | 2.74 | 0.704 | 1.42 | si |
| 30/09 15:00 | Rudar - Berane | 356 | 2.41 | 0.776 | 1.29 | no (troppo bassa) |
| 30/09 17:00 | Sporting Lagos - Ikorodu City | 399 | 2.77 | 0.7 | 1.43 | si |
| 30/09 17:00 | Warri Wolves - Enugu Rangers | 399 | 2.24 | 0.811 | 1.23 | no (troppo bassa) |
| 30/09 17:00 | Zeta - Kom | 356 | 2.18 | 0.823 | 1.22 | no (troppo bassa) |
| 30/09 18:00 | Czech Republic U21 - Bulgaria U21 | 850 | 2.7 | 0.714 | 1.4 | si |
| 30/09 18:00 | Faroe Islands U21 - Luxembourg U21 | 850 | 3.62 | 0.511 | 1.96 | si |
| 30/09 18:00 | Malta U21 - Germany U21 | 850 | 3.56 | 0.524 | 1.91 | si |
| 30/09 18:00 | Poland U21 - Sweden U21 | 850 | 3.15 | 0.614 | 1.63 | si |
| 30/09 18:00 | Romania U21 - Finland U21 | 850 | 3.11 | 0.623 | 1.61 | si |
| 30/09 18:00 | Ryazan - Zenit Penza | 650 | 2.41 | 0.777 | 1.29 | no (troppo bassa) |
| 30/09 18:30 | Dobrovce - Hajdina | 794 | 3.76 | 0.482 | 2.08 | si |
| 30/09 19:00 | Kosovo U21 - Cyprus U21 | 850 | 3.43 | 0.552 | 1.81 | si |
| 30/09 19:00 | Umeå FC Akademi - IFK Umeå | 594 | 4.16 | 0.403 | 2.48 | si |
| 30/09 19:30 | Wiedenbrück - Sportfreunde Siegen | 87 | 3.31 | 0.579 | 1.73 | si |
| 30/09 19:45 | Verl II - Gievenbeck | 747 | 3.3 | 0.58 | 1.72 | si |
| 30/09 20:00 | America PE U20 - Serrano PE U20 | 1088 | 2.79 | 0.694 | 1.44 | si |
| 30/09 20:00 | Athletico PR U17 - Cruzeiro U17 | 1128 | 4.17 | 0.4 | 2.5 | si |
| 30/09 20:00 | Atlético Mineiro U17 - Juventude U17 | 1128 | 3.96 | 0.44 | 2.27 | si |
| 30/09 20:00 | Bahia U17 - Fluminense U17 | 1128 | 2.86 | 0.678 | 1.48 | si |
| 30/09 20:00 | Botafogo U17 - RB Bragantino U17 | 1128 | 5.11 | 0.25 | 4.0 | no (troppo alta) |
| 30/09 20:00 | Corinthians U17 - Atletico GO U17 | 1128 | 5.01 | 0.264 | 3.79 | no (troppo alta) |
| 30/09 20:00 | Flamengo RJ U17 - America MG U17 | 1128 | 3.5 | 0.536 | 1.87 | si |
| 30/09 20:00 | Fortaleza U17 - Internacional U17 | 1128 | 3.08 | 0.63 | 1.59 | si |
| 30/09 20:00 | Gremio U17 - Sao Paulo U17 | 1128 | 3.03 | 0.64 | 1.56 | si |
| 30/09 20:00 | Independiente Riva. Res. - Belgrano Córdoba Res. | 906 | 2.78 | 0.696 | 1.44 | si |
| 30/09 20:00 | Instituto Res. - Racing Club Res. | 906 | 2.45 | 0.769 | 1.3 | si |
| 30/09 20:00 | Kreuzlingen - Brühl | 510 | 2.59 | 0.738 | 1.36 | si |
| 30/09 20:00 | Nautico U20 - Petrolina U20 | 1088 | 3.24 | 0.594 | 1.68 | si |
| 30/09 20:00 | Palmeiras U17 - Vasco U17 | 1128 | 3.95 | 0.442 | 2.26 | si |
| 30/09 20:00 | Platense Res. - Huracán Res. | 906 | 1.68 | 0.909 | 1.1 | no (troppo bassa) |
| 30/09 20:00 | Quilmes 2 - Estudiantes Rio Cuarto 2 | 906 | 2.13 | 0.833 | 1.2 | no (troppo bassa) |
| 30/09 20:00 | RWDM - Rochefort | 487 | 2.7 | 0.714 | 1.4 | si |
| 30/09 20:00 | Rosario Central Res. - Unión Santa Fe Res. | 906 | 2.24 | 0.812 | 1.23 | no (troppo bassa) |
| 30/09 20:00 | Santos U17 - Vitoria U17 | 1128 | 3.65 | 0.505 | 1.98 | si |
| 30/09 20:00 | Sport Recife U20 - Academica Vitoria U20 | 1088 | 2.97 | 0.654 | 1.53 | si |
| 30/09 20:00 | Sporting Charleroi II - Habay-la-Neuve | 487 | 2.52 | 0.754 | 1.33 | si |
| 30/09 20:15 | FC Wohlen - Schötz | 600 | 3.82 | 0.469 | 2.13 | si |
| 30/09 20:30 | Scotland U21 - Azerbaijan U21 | 850 | 3.38 | 0.562 | 1.78 | si |
| 30/09 20:45 | Eastleigh - Southend | 43 | 3.26 | 0.589 | 1.7 | si |
| 30/09 20:45 | Frome Town - Taunton Town | 60 | 3.47 | 0.543 | 1.84 | si |
| 30/09 20:45 | Gosport Borough - Bracknell Town | 60 | 3.36 | 0.566 | 1.77 | si |
| 30/09 20:45 | Tamworth - Sutton Utd | 43 | 3.01 | 0.645 | 1.55 | si |
| 30/09 20:45 | Whyteleafe - Brentwood Town | 58 | 3.24 | 0.594 | 1.68 | si |
| 30/09 21:00 | Portugal U21 - Gibraltar U21 | 850 | 4.79 | 0.296 | 3.37 | no (troppo alta) |
| 30/09 21:00 | Real Oruro - Always Ready | 964 | 3.42 | 0.555 | 1.8 | si |
| 30/09 21:30 | Atletico el Vigia FC - Zamora FC B | 300 | 3.08 | 0.629 | 1.59 | si |
| 30/09 21:30 | Club Atletico Barinas - Fundación Lara Deportiva | 300 | 3.44 | 0.549 | 1.82 | si |
| 30/09 22:00 | Cienciano - Club Deportivo Los Chankas | 281 | 2.92 | 0.665 | 1.5 | si |
| 30/09 22:00 | Salcedo - Delfines Del Este | 759 | 2.11 | 0.837 | 1.19 | no (troppo bassa) |
| 30/09 22:00 | Yaracuyanos FC - Puerto Cabello II | 300 | 2.5 | 0.758 | 1.32 | si |
| 30/09 23:30 | Águila - Inter | 370 | 3.08 | 0.629 | 1.59 | si |
| 01/10 00:00 | Central Córdoba SdE Res. - Newell's Old Boys Res. | 906 | 1.87 | 0.88 | 1.14 | no (troppo bassa) |
| 01/10 00:30 | Real Tomayapo - Nacional Potosí | 964 | 3.43 | 0.553 | 1.81 | si |
| 01/10 01:00 | Atlético Ottawa - Cavalry FC | 479 | 2.35 | 0.788 | 1.27 | no (troppo bassa) |
| 01/10 01:00 | Brooklyn - Detroit City | 255 | 2.2 | 0.82 | 1.22 | no (troppo bassa) |
| 01/10 01:00 | Concepción - O'Higgins | 267 | 3.09 | 0.628 | 1.59 | si |
| 01/10 01:00 | Deportivo Lara - Real Frontera | 300 | 3.76 | 0.481 | 2.08 | si |
| 01/10 01:00 | Miami FC - Sporting JAX | 255 | 3.67 | 0.501 | 2.0 | si |
| 01/10 01:30 | Rhode Island - Indy Eleven | 255 | 2.65 | 0.726 | 1.38 | si |


### 4.2 Partite senza gol attesi nel DB, dalle 17:00 di oggi e tutte quelle del 01/10 (91 su 126 senza dati)

Per queste non ho nemmeno la stima della quota. Le prime 35 (prima delle 17:00 italiane, quasi tutte giovanili/minori asiatiche e africane) non sono elencate.

| Ora (italiana) | Partita | Lega (id) |
|---|---|---|
| 30/09 17:00 | Canada U18 - Spain U18 | 10 |
| 30/09 17:00 | Enyimba - Shooting Stars | 399 |
| 30/09 17:00 | Katsina United - Rivers United | 399 |
| 30/09 17:00 | Medeama - Port City | 570 |
| 30/09 18:00 | Angola U23 - Namibia U23 | 1015 |
| 30/09 18:00 | Brann W - HJK W | 1191 |
| 30/09 18:00 | Eritrea - South Africa | 36 |
| 30/09 18:00 | Flint - Sandefjord | 105 |
| 30/09 18:00 | Fortuna Hjørring W - PSV/Eindhoven W | 1191 |
| 30/09 18:00 | Hønefoss - KFUM Oslo | 105 |
| 30/09 18:00 | Kalsdorf - Grazer AK | 667 |
| 30/09 18:00 | Lithuania - Andorra | 10 |
| 30/09 18:00 | Rosenborg W - Slovan Liberec W | 1191 |
| 30/09 18:00 | Rwanda U23 - Sudan U23 | 1015 |
| 30/09 18:00 | Spartak Myjava W - PAOK W | 1191 |
| 30/09 18:00 | Togo U23 - Libya U23 | 1015 |
| 30/09 18:00 | Vålerenga W - Feyenoord W | 1191 |
| 30/09 18:00 | Zimbabwe U23 - Mauritius U23 | 1015 |
| 30/09 18:30 | Eintracht Frankfurt W - FH W | 1191 |
| 30/09 18:30 | Portugal U19 - Netherlands U19 | 10 |
| 30/09 18:30 | Sturm Graz W - VfL Wolfsburg W | 1191 |
| 30/09 18:45 | Häcken W - Juventus W | 525 |
| 30/09 18:45 | Paris FC W - Arsenal W | 525 |
| 30/09 18:45 | Roma W - Barcelona W | 525 |
| 30/09 18:50 | Nordia Jerusalem - Hapoel Hadera | 496 |
| 30/09 18:55 | Hapoel Nazareth Illit - Tzeirey Tamra | 496 |
| 30/09 19:00 | Czarni Sosnowiec W - Breidablik W | 1191 |
| 30/09 19:00 | Fenerbahce W - Minsk W | 1191 |
| 30/09 19:00 | Hapoel Mahane Yehuda - Dimona | 496 |
| 30/09 19:00 | Konyaspor - Palestine | 10 |
| 30/09 19:00 | Luxembourg U19 - North Macedonia U19 | 10 |
| 30/09 19:00 | Maccabi Ashdod - Holon Yermiyahu | 496 |
| 30/09 19:00 | Malmö FF W - St. Pölten W | 1191 |
| 30/09 19:00 | Real Sociedad W - Hearts W | 1191 |
| 30/09 19:00 | Sestao River - Terrassa | 735 |
| 30/09 19:00 | Sunnanå W - Piteå W | 737 |
| 30/09 19:00 | Örebro SK W - Eskilstuna United W | 737 |
| 30/09 19:30 | Bahrain - Yemen | 25 |
| 30/09 19:30 | Hapoel Beit Shean - Ironi Baka El Garbiya | 496 |
| 30/09 19:30 | United Arab Emirates - Qatar | 25 |
| 30/09 20:00 | Birmingham City W - Liverpool W | 697 |
| 30/09 20:00 | Crystal Palace W - Charlton Athletic W | 697 |
| 30/09 20:00 | De Kempen - Diegem Sport | 150 |
| 30/09 20:00 | Diksmuide - Voorde Appelterre | 149 |
| 30/09 20:00 | Durham W - Manchester United W | 697 |
| 30/09 20:00 | EC Novo Horizonte - Clube 1992 | 1150 |
| 30/09 20:00 | Flénu - Olympic Charleroi | 487 |
| 30/09 20:00 | Futebol Com Vida - Panambi | 1150 |
| 30/09 20:00 | Houtvenne - Mandel United | 487 |
| 30/09 20:00 | Huy - Crossing Schaerbeek | 148 |
| 30/09 20:00 | Leicester City U21 - Real Sociedad II | 1039 |
| 30/09 20:00 | Merelbeke - Dessel Sport | 487 |
| 30/09 20:00 | Middlesbrough U21 - Juventus U21 | 1039 |
| 30/09 20:00 | Navalcarnero - Real Murcia | 735 |
| 30/09 20:00 | Nottingham Forest U21 - Sporting CP B | 1039 |
| 30/09 20:00 | RFC Wetteren - Londerzeel | 149 |
| 30/09 20:00 | Rangers W - Hammarby W | 1191 |
| 30/09 20:00 | Real - Farroupilha | 1150 |
| 30/09 20:00 | Roeselare Daisel - Thes Sport | 487 |
| 30/09 20:00 | Seuzach - FC Winterthur | 667 |
| 30/09 20:00 | Sint-Truiden II - Nijlen | 150 |
| 30/09 20:00 | Spouwen-Mopertingen - Heist | 487 |
| 30/09 20:00 | Tzeirey Tira - FC Jerusalem | 496 |
| 30/09 20:00 | VW Hamme - Oostkamp | 149 |
| 30/09 20:00 | Wellen - Racing Mechelen | 150 |
| 30/09 20:00 | West Ham W - Southampton W | 697 |
| 30/09 20:00 | Zelzate - Knokke | 487 |
| 30/09 20:00 | Älvsjö AIK W - Djurgården W | 737 |
| 30/09 20:30 | Aston Villa W - Newcastle United W | 697 |
| 30/09 20:30 | Harelbeke - Hoogstraten | 487 |
| 30/09 20:30 | Ipswich Town W - London City Lionesses W | 697 |
| 30/09 20:30 | Recreativo Huelva - Conil | 735 |
| 30/09 20:30 | Rotselaar - Rupel Boom | 150 |
| 30/09 20:30 | Spain U20 - Mexico U20 | 10 |
| 30/09 20:45 | Brighton W - Tottenham Hotspur W | 697 |
| 30/09 20:45 | Sporting CP W - Brøndby W | 1191 |
| 30/09 21:00 | Cerro Largo - Rentistas | 930 |
| 30/09 21:00 | Defensor Sporting - Plaza Colonia | 930 |
| 30/09 21:00 | Lyon W - Chelsea W | 525 |
| 30/09 21:00 | SL Benfica W - Bayern Munich W | 525 |
| 30/09 21:00 | Torreense W - Metalist 1925 W | 1191 |
| 30/09 22:00 | Independiente F.b.c. - Nacional Asuncion | 501 |
| 30/09 23:30 | River AC - Picos | 1203 |
| 01/10 00:00 | São Paulo RS - FBC Riograndense RS | 1150 |
| 01/10 00:30 | Cerro Porteno - Rubio NU | 501 |
| 01/10 00:30 | Cruz A. - SC Rio Grande | 1150 |
| 01/10 00:30 | Cruzeiro PB - Femar | 1037 |
| 01/10 00:30 | Santa Rita - São Paulo Crystal | 1037 |
| 01/10 01:00 | Correcaminos UAT II - Héroes de Zaci | 722 |
| 01/10 01:15 | Auto Esporte - Picuiense | 1037 |
| 01/10 01:30 | DC United - SC Paderborn 07 | 667 |


---

## 5. BUILD DELL'APP

Verifica in sola lettura:

- ultimo commit che tocca `frontend/src`: `a7e9f66`, **2026-09-30 10:53:13 +0200** (4 righe in `frontend/src/lib/mike.ts`: kind `mercato_deciso` ed etichetta «LINEA DECISA DAI GOL»).
  Prima: `b2b6b69` 10:27:25 (storico col giorno del regolamento e «Chiudi» un clic).
- `frontend/dist`: `index.html`, `assets/js/index-BHplcssB.js`, `assets/style-DM28Ig5p.css` del **2026-09-30 10:26** (le date dei file: 10:26:58).
- Esito: **il build e' PIU' VECCHIO dell'ultimo commit su `frontend/src` (di circa 27 minuti): `dist` NON ha l'etichetta «LINEA DECISA DAI GOL»** (a7e9f66). Per il commit `b2b6b69` (10:27:25) il build delle 10:26:58 e' di
  un minuto PRIMA del commit ma dopo le modifiche nel working tree (la cronostoria dice `npm run build` fatto dopo la consegna D): probabilmente le contiene, non l'ho verificato aprendo il bundle.
- `git status` su `frontend/src`: nessuna modifica non committata (solo file `.md` non tracciati in `frontend/`).
- Cosa deve fare il coordinatore/utente PRIMA del paper: `npm run build` in `frontend/` (io non l'ho lanciato: non potevo scrivere). Poi riavviare l'app.

---

## COSA NON HO POTUTO VERIFICARE

1. **Se Betfair restituisce ancora i mercati chiusi del 26/09** (Under/Over 3,5-4,5 e Correct Score): senza una chiamata a Betfair (vietata) non so se le 9 righe si regolano da sole o restano appese. Il codice prevede entrambi i casi (sezione 1.3);
   la documentazione Betfair nel repo non dice per quanto tempo `listMarketBook` restituisce mercati chiusi.
2. **Il comportamento del motore di Mike con una riga stantia del feed e stato `SETTLING` se il servizio parte prima dello scanner** (sezione 1.3, punto 5): dedotto dal codice, non simulato.
3. **Se l'app avvia il servizio di Mike anche con il bot su «Fermo»** (e quindi se le 2 partite orfane si regolano senza premere «Avvia»): dal codice il ciclo protegge e regola con qualunque stato di controllo, ma non ho letto il lanciatore dei processi
   (`main.js`/`avvio_app.py`); `avvio_app.py` e' citato solo per le uscite manuali di serie.
4. **I P&L attesi delle righe Safe (+1,90 x 4)**: calcolati da me con la regola del mercato Correct Score («Altro risultato» = punteggio fuori griglia) e coi risultati finali di `fixture_predictions`; non letti da un regolamento Betfair.
5. **Il calendario di Betfair di oggi/domani**: lo scanner e' spento, il feed e' fermo al 26/09; la quota Under 3,5 di ogni partita e' una mia STIMA da Poisson (senza margine ne' movimenti di mercato), e non so quali partite abbiano davvero i mercati Over/Under 3,5 e 4,5 sull'exchange.
   Le partite del 01/10 diurne non sono ancora nel DB dei pronostici.
6. **Le etichette delle pagine oltre a quelle in `mike.ts`/`tradeStatus.ts`**: non ho aperto l'app; per la pagina di Mike, la scheda partita e la Control Room ho descritto cosa deve comparire dal codice (kind, etichette, stati), non da uno schermo. In particolare lo stato «ULTIMO INGRESSO»
   (`PRE_LAST_ENTRY_PENDING`) esiste nella mappa degli stati ma il motore (`_ultimo_ingresso`) ritorna `PRE_ENTRY_PENDING` con motivo «ultimo ingresso: ...»: che cosa mostri la scheda in quel momento va guardato dal vivo.
7. **La forma banca Under 4,5 dal vivo**: e' certificata solo sul banco (referti `AUDIT_2026-09-29`), oggi e' spenta di serie; il caso (c) presuppone che l'utente la accenda dal pannello.
8. **Il `build` dell'app**: non ho lanciato `npm run build` ne' aperto il bundle per cercare la stringa dell'etichetta (sola lettura); la conclusione si basa sulle date dei file e del commit.
9. **Le righe 5079 e Safe diverse dalle 9 aperte**: non le ho controllate (fuori compito). Non ho controllato `safe_strategy_control` oltre allo stato `stopping`.

File letti principali: `CLAUDE.md`, `CRONOSTORIA.md` (sezione 30/09 e checkpoint 21:15 del 29/09), `Betfair/mike/service.py`, `engine.py`, `feed.py`, `config.py`, `db.py`,
`Betfair/safe_strategy/bot_service.py`, `bot_db.py`, `service.py`, `frontend/src/lib/mike.ts`, `tradeStatus.ts`,
`AUDIT_2026-09-29/INDAGINE_MIKE_MERCATO_DECISO.md`, `AUDIT_2026-09-30/MIKE_MERCATO_DECISO.md`.
