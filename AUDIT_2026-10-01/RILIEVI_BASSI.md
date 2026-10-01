# Rilievi BASSI/MEDI del 01/10: referto del delegato

Delegato Opus del coordinatore admin-01, worktree `agent-abaa4a95411e33a91`, base master `fc5afbd`. Niente commit, niente `git add`, niente build.
Patch: `AUDIT_2026-10-01/RILIEVI_BASSI.patch` (33 file; md5 26269f8594084be73202cb3ce322dc56; `git apply --check -R` passato sul worktree; `git diff master` piu' il file di test nuovo aggiunto con `git diff --no-index`). Solo `frontend/src`: nessun file Python, nessun SQL, nessuna strategia toccata.
Il checkout principale non e' scrivibile da questo worktree: patch e referto stanno nel worktree, sotto `AUDIT_2026-10-01/`.

## Tabella: rilievo, correzione, file, test, falsificazione

| # | Rilievo | Correzione | File | Test | Falsificazione |
|---|---|---|---|---|---|
| 1 | Plancia «oggi per bot» e riassunto del gruppo per REGOLAMENTO sulle sole righe in memoria | Una funzione comune `posizioniDellaGiornata` (in `lib/chiuseGiornata.ts`) fa la giornata per la scheda Chiuse E per la plancia: memoria + STESSA lettura della giornata (`chiuseGiornata`, memoria condivisa), giorno ereditato dal database (`unisciRighe`/`haGiornoDb`), esclusione delle partite di altri giorni (`MARGINE_LETTURA_MS`, spostato qui e riesportato da `PosizioniChiuse.tsx`). `pnlChiuseDelGiorno` toglie le escluse. Le righe senza il dato restano sul REGOLAMENTO e la plancia lo DICE nella nota della cifra: «N chiuse senza il giorno della partita dal database: contate nel giorno di regolamento (provvisorie)». Il contatore della scheda nella pagina toglie anche lui le escluse | `lib/chiuseGiornata.ts`, `lib/posizioniChiuse.ts`, `components/controlroom/PosizioniChiuse.tsx`, `components/controlroom/useControlRoom.ts`, `pages/ControlRoom.tsx` | NUOVO `components/controlroom/plancia.giornoPartita.test.tsx` (4 test): con gli STESSI finti, plancia per bot (Omega 1,00, Mike 2,05) = riassunto del gruppo BOT CALCIO (3,05) = totale della scheda Chiuse (3,05); la partita di ieri regolata stanotte fuori; riga senza dato dichiarata; database non raggiunto = ripiego al regolamento dichiarato | 4 mutazioni, tutte ROSSE (sotto) |
| 2 | C-05 «pari» a +/-0,005 nelle Chiuse, 0 esatto nel SQL | `esitoDi` = zero esatto al centesimo (valore portato al centesimo in modo simmetrico, poi segno), come `total_pnl > 0 / < 0` del database. `statoDaNetto` usa la stessa regola per lo stato delle righe tennis e scalper. `SOGLIA_PARI` resta solo per gli IMPORTI (residui) | `lib/posizioniChiuse.ts`, `useControlRoom.ts` | `lib/posizioniChiuse.test.ts` «C-05» (3 test nuovi) | ROSSO (2 test) |
| 3 | B-14 periodi diversi fra Storico dello sport e storici dei bot; «Tutto» non onesto; `window_clamped` non letto | Una serie sola (`PERIOD_LABEL`/`periodRange` in `lib/dailyHistory.ts`): 7 / 30 / 90 giorni, Mese corrente, «Tutto» (+ «Oggi» solo nello sport, «Anno» solo nei bot). Lo sport prende le etichette e gli intervalli dalla stessa funzione. «Tutto» = ultimi 400 giorni, e sotto i filtri una riga dice quanto copre davvero (`coperturaTutto`: tetto, primo giorno con operazioni, giorni coperti, finestra ridotta dal database con `window_clamped`/`window_from` se la RPC li manda; ora `normalizeDailyRow` li legge) | `lib/dailyHistory.ts`, `lib/storicoSport.ts`, `pages/StoricoSport.tsx`, `components/trading/PerformancePanel.tsx` | `lib/storicoSport.test.ts`: test B-14 rivisto (motivo scritto nel test) + 1 nuovo | ROSSO su etichetta e su `window_clamped` |
| 4 | D-06 due tipi `FontePnl` | UN tipo, quello di `lib/fontePnl.ts` (`conto` / `stima` / `simulato`). `lib/eventGroups.ts` lo importa e lo riesporta; `fonteDiRiga`/`fonteDiRighe` e le Chiuse usano le stesse parole; tolta la rimappatura a mano in `PosizioniChiuse.tsx`. Il filtro «solo Betfair» delle Chiuse tiene il suo valore di filtro (`'betfair'`), confronta con `'conto'` | `lib/eventGroups.ts`, `lib/posizioniChiuse.ts`, `PosizioniChiuse.tsx` | 5 file di test aggiornati nei valori attesi (`pnlRealeBetfair`, `posizioniChiuse.raggruppamento` lib e componente, `chiuseGiornata`, `useControlRoom`), motivo scritto in testa a ciascuno | tsc ROSSO (11 errori) rimettendo il secondo tipo |
| 5 | C-08 «parziale» senza test | Nessun codice cambiato | - | `PosizioniChiuse.giornoPartita.test.tsx` «C-08» (5 test: ieri ripiego tutti gli sport / tennis = badge col motivo; ieri lettura completa, ieri scheda calcio, oggi = niente badge) | 3 mutazioni, tutte ROSSE |
| 6 | R-05 stop dalla testata con `raw` vecchio fino a 30 s | `salvaStop` per i bot: cancello di prima (parametri della pagina), poi RILEGGE i parametri dalla stessa lettura dello stato del servizio da cui arrivano quelli della pagina (`get_safe_state`, `get_mike_state`, `get_omega_state` con 1 riga di attivita') e compone il payload sulla riga appena letta. Rilettura fallita o vuota = niente scrittura, errore «parametri di X non riletti prima di salvare (motivo): nulla e' stato scritto, riprova» (il componente lo mostra gia' come «non salvato: ...») | `components/controlroom/testata/salvaStop.ts` | `salvaStop.test.ts`: 3 test nuovi R-05; 3 test esistenti cambiati (la scrittura e' ora la SECONDA chiamata, motivo scritto) | 2 mutazioni, ROSSE |
| 7 | R-06 predefiniti frontend contro Python | Tabella sotto. UNA differenza sovrascrive un valore vero: Safe `risk.max_open_trades` scritto 0 (= NESSUN tetto) invece di lasciarlo assente (= tetto del bot, 20) o del valore del database. Corretta nel percorso dello stop: si riscrive il valore della riga letta, assente resta assente | `salvaStop.ts` | `salvaStop.test.ts` «R-06» (2 test nuovi); il test «identico a BotParamsSheet.save» cambia (motivo scritto: il foglio ha ancora il difetto) | ROSSO (3 test) |
| 8 | R-07 testo dello Scalper | «Tennis e Scalper: nessuno stop giornaliero proprio. ... Lo Scalper ha in piu' due tetti suoi, nei parametri della sessione: perdita massima per partita ed esposizione massima per selezione.» Title con le cifre verificate. Tolto dal title il nome della tabella | `testata/FasciaStop.tsx` | `FasciaStop.test.tsx` (test aggiornato, motivo scritto) | ROSSO |
| 9 | R-08, R-10 | Lasciati, spiegazione sotto | - | - | - |
| 10 | Nomi di file SQL a schermo | Storico di Mike: «storico di Mike non disponibile: il database non ha ancora l'aggiornamento dello storico (da applicare)», senza piu' l'errore grezzo del database (che conteneva nomi di funzioni: va in `console.warn`). Tooltip di `StatoOrdine`: «numero preso dalla nota scritta dal bot, non dallo stato dell'ordine letto da Betfair: il database non ha ancora l'aggiornamento che salva quello stato» | `lib/mike.ts`, `components/trading/StatoOrdine.tsx` | `lib/mike.test.ts` (aggiornato + controllo «nessun nome del database»), `pages/Mike.test.tsx` (aggiornato), `StatoOrdine.test.tsx` (1 nuovo) | ROSSO su entrambi |
| 11 | `SaldoBetfairCard.tsx` nel codice solo per `CANALI_SALDO` | `CANALI_SALDO` spostato in `lib/saldoBetfair.ts` (modulo puro della logica del saldo). Cercato `SaldoBetfairCard` in `frontend/src`: lo importavano solo `useControlRoom.ts` (la costante) e il suo test. Cancellati `SaldoBetfairCard.tsx` e `SaldoBetfairCard.test.tsx` (con loro `checkedAtDiMessaggioAccount`, usata solo li'). Restano citazioni nei COMMENTI di altri file (storiche, non import) | `lib/saldoBetfair.ts`, `useControlRoom.ts`, file cancellati | `lib/saldoBetfair.test.ts` (costante, 1 nuovo), `useControlRoom.test.tsx` (il hook ascolta «account» su tutti e 5 i canali, 1 nuovo) | 2 mutazioni, ROSSE |

### Punto 1 nel dettaglio

- **Che cosa conta ora la plancia LIVE dalle righe dei bot** (conto non letto, e sempre per le strategie calcio di Safe): le posizioni chiuse di oggi con giorno della PARTITA quando la riga lo porta dal database; senza il dato, giorno di regolamento, provvisorie e dichiarate nella nota; fuori le posizioni che la lettura di oggi dice di partite di altri giorni. E' la regola della scheda, con la STESSA funzione.
- **Invariato, di proposito**: la cifra LIVE della plancia quando il CONTO e' letto (fonte CONTO, decisione dell'utente del 30/09 «com'e'»); la barra dell'Obiettivo (composizione per voce: con il conto e' il regolato Betfair per giorno di regolamento; senza conto le righe dei bot su quello STESSO perimetro, cosi' la cifra non salta quando il conto arriva, ed e' il perimetro della controprova B-12 della scheda); la PROVA della plancia (corsia P8bis: partite di oggi regolate oggi, giorno della partita dal fischio o dall'apertura, arretrati a parte). Per «barra» nel test ho usato il riassunto del gruppo della plancia (la somma «oggi» LIVE di BOT CALCIO), che segue la plancia. **Da decidere per il coordinatore**: se anche la barra dell'Obiettivo senza conto deve passare al giorno della partita (cambierebbe il perimetro della controprova B-12).
- **Chiamate al database, prima e dopo** (memoria dell'utente: contare le chiamate): prima la plancia non leggeva niente; la scheda Chiuse aperta leggeva `oggi|live` al massimo ogni 60 s. Ora il hook legge `oggi|live` (la stessa RPC, la STESSA memoria della scheda) SOLO se c'e' almeno una posizione LIVE di oggi ancora senza il giorno del database: al massimo una lettura al minuto, zero quando tutto e' confermato. Con la scheda aperta non si aggiunge niente (la memoria e' condivisa). Caso limite: database SENZA la migrazione del 01/10, le posizioni restano senza dato e la lettura si ripete una volta al minuto finche' ci sono chiuse live di oggi. Nessun processo nuovo, nessun canale nuovo.
- `vm.chiuse` ora e' l'insieme unito (tipo `readonly`): la scheda continua a ricostruire dalle righe grezze + sua lettura; il contatore della scheda nella pagina usa `vm.chiuseEscluse`.

### R-06: tabella delle differenze (confronto fatto da un sotto-delegato Sonnet in sola lettura; il difetto l'ho riletto io sul codice)

RPC: `safe_update_params` (`migrations/safe_strategy_bot.sql:237`), `mike_update_params` (`migrations/mike_bot.sql:237`), `omega_update_params` (`migrations/omega_daily_v2.sql:109`) fanno tutte `params = coalesce(p_params, params)`: SOSTITUISCONO l'oggetto.

| Bot | Chiave | Frontend | Python | Effetto | Esito |
|---|---|---|---|---|---|
| Safe | `risk.max_open_trades` | sempre **0** (non e' in `SAFE_RISK_DEFAULTS`, `mergeRiskParams` la scarta, `toValues` la legge `NaN -> 0`) | assente = `None` -> vale `max_open_trades` del bot (20) (`risk.py` `DEFAULT_RISK_PARAMS`, `risk_params`); 0 = nessun tetto (`risk.py` `check`: `if max_open and ...`) | Salvare lo stop TOGLIEVA il tetto delle posizioni aperte (o riscriveva un 5 del database a 0) | **CORRETTO nel percorso dello stop** |
| Safe | le altre 76 chiavi del payload (risk, exits 20 chiavi, base/esatto/punta/tennis, bot, opps, toggle) | | | predefiniti identici al Python; nessun clamp nel percorso di salvataggio (`toValues`/`fromValues` non fanno min/max) | nessuna differenza |
| Safe | dati malformati nel DB (non provato che esistano): `base.minuteMin: null` | scritto 0 | il Python userebbe 55 | | non corretto, segnalato |
| Safe | `strategy_modes: {tennis: 'LIVE'}` (maiuscolo) | scartata (diventa «eredita») | il Python fa `.lower()` e la tiene LIVE | | non corretto, segnalato |
| Mike | 107 chiavi di `MIKE_PARAM_DEFAULTS`/`MIKE_PARAM_FIELDS` contro `PARAM_SPEC` (`config.py`) | | | predefiniti, min, max e scelte identici (confronto automatico, falsificato iniettando due differenze); il clamp del frontend non e' mai piu' stretto del Python | nessuna differenza |
| Mike | dati malformati: bool salvato come numero (`pre_enabled: 0`) | tiene il predefinito (true) | `bool(0)` = false | | non corretto, segnalato |
| Omega | `omegaParamsPatch` | copia l'oggetto del servizio e aggiunge SOLO la chiave dello stop; nessun predefinito riempito, nessun clamp | `strategy_version` 3 e `v3_daily_loss_cap` 300 coincidono (`omega_config.py`) | | nessuna differenza |

**Attenzione, fuori dal mio perimetro**: lo stesso difetto di `risk.max_open_trades` c'e' nel FOGLIO parametri di Safe (`BotParamsSheet.save`, stesse `toValues`/`fromValues`): salvare il foglio scrive 0. Non l'ho corretto (cambierebbe il foglio e il suo campo; il commento del campo dice «Vuoto/assente = vale quello generale», il codice no). Va deciso e corretto a parte.

### R-08 e R-10: lasciati

- **R-08** (riga in memoria senza giorno del database, regolata piu' di 5 min prima della lettura e assente dalla risposta, esclusa per al massimo 60 s): transitorio auto-correggente; la correzione non e' una riga (servirebbe un margine adattivo o una seconda lettura). Ora vale identico anche per la plancia, perche' usa la stessa funzione.
- **R-10** (Storico di Omega in PROVA di partenza prima della lettura del controllo): verificato che nel flusso normale non accade: lo Storico sta dentro `loading ? ... : ...` (`pages/Omega.tsx`), e `loading` diventa false solo dopo `setControl` della prima lettura. Resta solo se la prima lettura FALLISCE (control null): la pagina intera e' allora in `paper` e lo Storico chiede e dichiara PROVA (badge e cifre coerenti, nessuna mescolanza). La correzione («non letto» invece di PROVA) non e' una riga: tocca i due fetcher, `filterKey`, `modo` e richiede un errore dichiarato quando la moneta non e' nota. Non fatta.

## Numeri

- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori**.
- Suite intera `npx vitest run`: vedi riga finale qui sotto (prima: 310 file / 4764 test).
- SUITE: **310 file passati e 10 saltati; 4767 test passati e 50 saltati; 0 falliti** (532 s). Rispetto a prima (310 / 4764): +1 file di test nuovo (plancia), -1 cancellato (card del saldo); +21 test nuovi, -18 del test della card cancellata.

## Falsificazioni (script `_tmp_rilievi/falsifica.py` e `falsifica_r06.py` nel worktree; ogni file ripristinato e verificato byte per byte)

```
ROSSO P1a plancia dalle sole righe in memoria (regolamento, nessuna lettura)
      Test Files  1 failed (1) | Tests  3 failed | 1 passed (4)
      rossi: × punto 1: plancia, riassunto del gruppo e scheda Chiuse = stesso numero (giorno della PARTITA) > la plancia legge la giornata di oggi in SOLDI VERI con la lettura della scheda 1219ms
             × punto 1: plancia, riassunto del gruppo e scheda Chiuse = stesso numero (giorno della PARTITA) > per bot: Omega 1,00 (la partita di IERI regolata stanotte NON e' di oggi), Mike 2,05 1107ms
             × punto 1: plancia, riassunto del gruppo e scheda Chiuse = stesso numero (giorno della PARTITA) > le TRE viste con gli stessi finti: plancia = riassunto del gruppo = scheda Chiuse 1096ms
ROSSO P1b esclusione «partita di un altro giorno» spenta nella funzione comune
      Test Files  2 failed (2) | Tests  4 failed | 13 passed (17)
      rossi: × la chiusura di ieri sera NON e' di oggi > in memoria senza il giorno del database, la lettura di oggi la esclude: fuori dal totale, contata 1388ms
             × punto 1: plancia, riassunto del gruppo e scheda Chiuse = stesso numero (giorno della PARTITA) > la plancia legge la giornata di oggi in SOLDI VERI con la lettura della scheda 1339ms
             × punto 1: plancia, riassunto del gruppo e scheda Chiuse = stesso numero (giorno della PARTITA) > per bot: Omega 1,00 (la partita di IERI regolata stanotte NON e' di oggi), Mike 2,05 1106ms
             × punto 1: plancia, riassunto del gruppo e scheda Chiuse = stesso numero (giorno della PARTITA) > le TRE viste con gli stessi finti: plancia = riassunto del gruppo = scheda Chiuse 1103ms
ROSSO P1c pnlChiuseDelGiorno ignora le escluse
      Test Files  1 failed (1) | Tests  3 failed | 1 passed (4)
      rossi: × punto 1: plancia, riassunto del gruppo e scheda Chiuse = stesso numero (giorno della PARTITA) > la plancia legge la giornata di oggi in SOLDI VERI con la lettura della scheda 1197ms
             × punto 1: plancia, riassunto del gruppo e scheda Chiuse = stesso numero (giorno della PARTITA) > per bot: Omega 1,00 (la partita di IERI regolata stanotte NON e' di oggi), Mike 2,05 1083ms
             × punto 1: plancia, riassunto del gruppo e scheda Chiuse = stesso numero (giorno della PARTITA) > le TRE viste con gli stessi finti: plancia = riassunto del gruppo = scheda Chiuse 1083ms
ROSSO P1d nessuna nota delle provvisorie nella plancia
      Test Files  1 failed (1) | Tests  2 failed | 2 passed (4)
      rossi: × punto 1: plancia, riassunto del gruppo e scheda Chiuse = stesso numero (giorno della PARTITA) > per bot: Omega 1,00 (la partita di IERI regolata stanotte NON e' di oggi), Mike 2,05 109ms
             × punto 1: plancia, riassunto del gruppo e scheda Chiuse = stesso numero (giorno della PARTITA) > senza lettura (database non raggiunto): ripiego al REGOLAMENTO, dichiarato 99ms
ROSSO C-05 soglia +/-0,005 rimessa
      Test Files  1 failed (1) | Tests  2 failed | 44 passed (46)
      rossi: × C-05: «pari» = zero esatto al centesimo, come il database > mezzo centesimo si porta al centesimo, in modo simmetrico 13ms
             × C-05: «pari» = zero esatto al centesimo, come il database > un centesimo basta per un esito; lo stato di una riga tennis segue la stessa regola 1ms
ROSSO C-08 parziale sempre falso
      Test Files  1 failed (1) | Tests  2 failed | 11 passed (13)
      rossi: × C-08: «parziale» sulla giornata passata letta in ripiego > ieri, lettura di ripiego, tutti gli sport: «parziale» col motivo 70ms
             × C-08: «parziale» sulla giornata passata letta in ripiego > ieri, lettura di ripiego, scheda tennis: «parziale» 1053ms
ROSSO C-08 condizione su oggi tolta
      Test Files  1 failed (1) | Tests  1 failed | 12 passed (13)
      rossi: × C-08: «parziale» sulla giornata passata letta in ripiego > OGGI in ripiego: nessun «parziale» (oggi i bot tennis arrivano dalla memoria) 57ms
ROSSO C-08 condizione sullo sport tolta
      Test Files  1 failed (1) | Tests  1 failed | 12 passed (13)
      rossi: × C-08: «parziale» sulla giornata passata letta in ripiego > ieri, ripiego, scheda CALCIO: nessun «parziale» (il ripiego legge tutto il calcio) 61ms
ROSSO R-05 payload composto sui parametri della pagina
      Test Files  1 failed (1) | Tests  2 failed | 19 passed (21)
      rossi: × R-05: prima di scrivere si RILEGGONO i parametri del bot > Mike: un foglio ha cambiato max_open_matches (10 -> 12) dopo la lettura della pagina: il 12 resta 27ms
             × R-05: prima di scrivere si RILEGGONO i parametri del bot > Safe: una strategia aggiunta nel frattempo (punta) non si perde 10ms
ROSSO R-05 nessuna rilettura
      Test Files  1 failed (1) | Tests  6 failed | 15 passed (21)
      rossi: × salvaStop - RPC vere, chiavi vere, cifra dal database > Safe: safe_update_params({ p_params }) col payload del foglio; ritorna |risk.daily_loss_stop| della riga 40ms
             × salvaStop - RPC vere, chiavi vere, cifra dal database > Mike: mike_update_params({ p_params, p_mode: null }): la modalita' non si tocca 10ms
             × salvaStop - RPC vere, chiavi vere, cifra dal database > Omega: omega_update_params con p_daily_goal null (obiettivo intatto) e p_mode null 3ms
             × R-05: prima di scrivere si RILEGGONO i parametri del bot > Mike: un foglio ha cambiato max_open_matches (10 -> 12) dopo la lettura della pagina: il 12 resta 2ms
             × R-05: prima di scrivere si RILEGGONO i parametri del bot > Safe: una strategia aggiunta nel frattempo (punta) non si perde 5ms
             × R-05: prima di scrivere si RILEGGONO i parametri del bot > rilettura FALLITA o VUOTA: niente scrittura, e il motivo si legge 9ms
ROSSO R-07 testo vecchio dello scalper
      Test Files  1 failed (1) | Tests  1 failed | 41 passed (42)
      rossi: × R_T (30/09) + 01/10 - frasi chiare, mai criptiche > tennis e scalper: la verita' verificata nel codice (nessuno stop proprio; lo stop del conto li ferma ma non conta le loro perdite) 80ms
ROSSO P10 nome del file SQL nel tooltip di StatoOrdine
      Test Files  1 failed (1) | Tests  1 failed | 9 passed (10)
      rossi: × StatoOrdineRiga — i tre numeri e lo stato > il tooltip «dalla nota» non nomina file SQL 13ms
ROSSO P10 errore grezzo del database nello Storico di Mike
      Test Files  2 failed (2) | Tests  2 failed | 88 passed | 1 skipped (91)
      rossi: × mike storico: errore LEGGIBILE senza la migrazione (R2) > gli errori di firma/RPC diventano «aggiornamento dello storico da applicare», senza nomi del database 21ms
             × Mike page — storico senza migrazione > non mostra "is not unique" nudo ma dice quale migrazione applicare 551ms
ROSSO P11 un canale tolto da CANALI_SALDO
      Test Files  1 failed (1) | Tests  1 failed | 18 passed (19)
      rossi: × CANALI_SALDO - i canali che portano il topic «account» > sono i 5 processi che piazzano ordini veri (porte esistenti) 13ms
ROSSO P11 il hook ascolta solo 4 canali
      Test Files  1 failed (1) | Tests  1 failed | 71 passed (72)
      rossi: × saldo del conto: il hook ascolta il topic «account» di TUTTI i canali del saldo > una sottoscrizione «account» per ciascuno dei 5 canali 102ms
ROSSO B-14 etichetta vecchia di «Tutto»
      Test Files  1 failed (1) | Tests  1 failed | 36 passed (37)
      rossi: × intervalli: oggi, 7 giorni, 30 giorni, mese, tutto > B-14: STESSE etichette e STESSI intervalli degli storici dei bot 19ms
ROSSO B-14 finestra ridotta dal database ignorata
      Test Files  1 failed (1) | Tests  1 failed | 36 passed (37)
      rossi: × intervalli: oggi, 7 giorni, 30 giorni, mese, tutto > B-14: «Tutto» dice quanti giorni copre davvero, e la finestra ridotta dal database 48ms
ROSSO D-06 secondo tipo FontePnl rimesso in eventGroups
      11 errori tsc; primo: src/components/controlroom/PosizioniChiuse.tsx(770,31): error TS2322: Type '"simulato" | FontePnl | "stima"' is not assignable to type 'FontePnl | undefined'.
fine: tutti i file ripristinati byte per byte
ROSSO R-06 correzione di risk.max_open_trades tolta
    × payloadStop - lo STESSO payload del foglio del proprietario > Safe: identico a BotParamsSheet.save con il solo stop cambiato (chiavi ignote conservate) 18ms
    × R-06: salvare lo stop di Safe non tocca il tetto delle posizioni aperte > chiave ASSENTE nel database: resta assente (il servizio usa il tetto del bot) 2ms
    × R-06: salvare lo stop di Safe non tocca il tetto delle posizioni aperte > chiave PRESENTE (5): resta 5, mai 0 (= nessun tetto) 1ms
    Test Files  1 failed (1)
    Tests  3 failed | 20 passed (23)
ripristinato byte per byte
```

## Test esistenti cambiati (motivo scritto nel test)

- `lib/storicoSport.test.ts`: «B-14 ... Ultimi 400 giorni» diventa «STESSE etichette ... "Tutto"».
- `components/controlroom/testata/salvaStop.test.ts`: Safe/Mike/Omega, la scrittura e' la seconda chiamata (R-05); «identico a BotParamsSheet.save» senza `risk.max_open_trades` (R-06).
- `components/controlroom/testata/FasciaStop.test.tsx`: testo dello Scalper (R-07).
- `lib/mike.test.ts`, `pages/Mike.test.tsx`: messaggio dello Storico di Mike senza nome di file (punto 10).
- D-06: valori attesi `conto`/`stima`/`simulato` in `pnlRealeBetfair.test.ts`, `posizioniChiuse.raggruppamento.test.ts`, `chiuseGiornata.test.ts`, `PosizioniChiuse.raggruppamento.test.tsx`, `useControlRoom.test.tsx`.
- Cancellato `SaldoBetfairCard.test.tsx` con il suo componente (punto 11); la sua asserzione su `CANALI_SALDO` e' ripresa in `lib/saldoBetfair.test.ts`.

## Cosa NON ho potuto verificare

- **Database** (nessun accesso): se la migrazione del 01/10 e' applicata e se `get_posizioni_chiuse_giornata` manda davvero `giorno_partita`/`giorno_da`/`in_day`; i `params` reali di Safe (se oggi `risk.max_open_trades` e' assente o valorizzato, cioe' se il difetto R-06 ha gia' scritto 0 con uno stop salvato dalla testata); che le RPC vive coincidano con le migrazioni del repo.
- **A schermo**: niente build ne' app. Non ho visto la nota delle provvisorie nella plancia (sta nel title della cifra e nel marchio della fonte), la riga «Tutto = ...» sotto i filtri, il testo lungo dello Scalper nella testata.
- **Python**: i tetti dello scalper (R-07) li ho letti nel codice (`scalper_session.py` `event_loss_cap` 1,5 e `min(..., 1.0)` in modalita' intervallo; `scalper_bot.py` force-flat oltre il tetto; tetto di esposizione per selezione `stake x (price_max-1) x 2`), non provati su un replay.
- **Paper della plancia** e barra dell'Obiettivo: non portati al giorno della partita (vedi punto 1): due regole diverse restano per la PROVA (plancia/corsia: partite di oggi regolate oggi, giorno dal fischio o dall'apertura) e la scheda Chiuse in prova (giorno dal database).
- Commenti di altri file che citano ancora `SaldoBetfairCard` (storici, nessun import): non toccati.
