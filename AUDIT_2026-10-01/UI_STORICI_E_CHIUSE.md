# UI Storici e Posizioni chiuse: correzioni dell'audit del 01/10/2026

Costruttore: Opus (delegato di admin-01), worktree `agent-ad3af137e37beed0b`. Niente commit e niente build.
Patch: `AUDIT_2026-10-01/UI_STORICI_E_CHIUSE.patch` = `git diff master` dopo il merge fast-forward del worktree su master `2ac4105`, quindi si applica pulita su master. Il file di test nuovo `PosizioniChiuse.giornoPartita.test.tsx` è incluso con `git add -N` del solo suo percorso; nient'altro è in stage. 30 file: solo `frontend/src`, nessun file Python o SQL, nessun file `testata/*`, `ObiettivoHero`, `SaldoBetfairCard`, `FasciaStop`).

## Regola applicata

- **Giornata = giorno della PARTITA (Europe/Rome)** per tutti i bot, calcio e tennis, prova e soldi veri. Il giorno lo decide il database: `in_day`, `giorno_partita`, `giorno_da` ('partita' | 'piazzamento') secondo il contratto aggiornato dal coordinatore. Il frontend non deduce mai il giorno della partita (nemmeno da `minute_at_entry`).
- **Se il database non manda le chiavi nuove**, il frontend usa il criterio di prima e **lo dichiara a schermo**: «giornata NON per partita: il database non manda ancora il giorno della partita (serve l'aggiornamento del database del 01/10)». Il criterio di prima resta quello con cui la RPC vecchia costruisce la cella (Omega e Safe per piazzamento, Mike per regolamento), quindi dettaglio e cella coincidono anche senza migrazione.
- **Posizioni chiuse.** Le righe in memoria non hanno il giorno del database. Per questo:
  - una riga che ha lo stesso id fra quelle lette dal database ne eredita il giorno;
  - finché la conferma non arriva, la giornata vale dal regolamento ed è marcata **PROVVISORIA** (contata in una nota);
  - con una lettura del giorno che porta il contratto nuovo, una riga regolata più di 5 minuti prima della lettura e assente dalla risposta appartiene a una partita di un altro giorno: esce dal giorno e viene contata fra quelle «di altre giornate».
- **Monete separate.** Nessuna cifra dell'altra moneta compare nella vista di una moneta: Storico dello sport, Omega, Safe e Mike. L'unica traccia dell'altra moneta è il selettore per passarci.

## Tabella: reperto, correzione, file, test

| Reperto | Sev. | Correzione | File | Test (nuovo o aggiornato) |
|---|---|---|---|---|
| A-01 | ALTO | Tolti la riga «PROVA −x su N operazioni…» e `totaleAltraModalita` | `pages/StoricoSport.tsx` | `StoricoSport.test.tsx` «A-01: NESSUNA cifra dell'altra moneta, in nessuna delle due viste» (invertito) |
| A-02 | ALTO | Blocco «non separabile» senza cifre: «Omega: non incluso nei totali». Nel dettaglio non compare nessuna riga mista: `caricaTradeGiorno` restituisce `trades: []` e l'avviso dice che la riga è nascosta | `pages/StoricoSport.tsx`, `lib/storicoSport.ts` | «Omega finisce nel blocco non separabile SENZA cifre…» |
| A-03 | ALTO | Testo da trader, senza nomi di RPC o di file | `pages/StoricoSport.tsx`, `lib/chiuseGiornata.ts` (avviso di ripiego) | stesso test; `chiuseGiornata.test.ts` (avviso senza `migrazione`/`.sql`) |
| A-04 | MEDIO (esteso) | Omega e Safe: niente cifre della prova sotto i soldi veri e viceversa. Al loro posto il pulsante «apri lo Storico in PROVA / SOLDI VERI» | `pages/Omega.tsx`, `pages/SafeStrategy.tsx` | `SafeStrategy.fixA.test.tsx` (2 test aggiornati) |
| A-05 | ALTO | Lo Storico di Omega passa sempre `p_mode`, con la moneta del bot come valore di partenza e un selettore. Se il database non separa le monete il pannello non mostra cifre e dice «storico per moneta non disponibile…». La testata indica la moneta | `pages/Omega.tsx`, `components/trading/TradingHistory.tsx` | `Omega.storico.test.tsx` (aggiornato e 2 test nuovi) |
| A-06 | MEDIO | Safe: pulsanti «soldi veri / prova» nella testata dello Storico. Tolto il filtro sport «tutti»: lo sport di partenza è quello della scheda da cui si arriva | `pages/SafeStrategy.tsx` | `SafeStrategy.storico.test.tsx` (aggiornato: `'calcio'`, nessun «tutti», testata PROVA) |
| A-07 | MEDIO | Mike: `mode` sempre esplicito, selettore e testata della moneta | `pages/Mike.tsx` | `Mike.test.tsx` «storico con la moneta esplicita» (nuovo) |
| A-08 | MEDIO | Badge della moneta sempre visibile (`cr-chiuse-moneta`: «soldi veri» rosso, «prova» neutro). Pillole e tag di riga dicono «soldi veri» | `components/controlroom/PosizioniChiuse.tsx` | `PosizioniChiuse.raggruppamento.test.tsx` |
| A-09 | BASSO | Tolte le pillole doppie `storico-modo-*`. Il pulsante PROVA della testata non è più verde | `pages/StoricoSport.tsx` | «A-09: la moneta si sceglie in UN posto solo» |
| B-01 | ALTO | Il piede usa la frase unica `GIORNATA_PARTITA_TESTO`, senza nomi di funzioni | `pages/StoricoSport.tsx`, `lib/dailyHistory.ts` | «B-01: il piede dice il criterio vero» |
| B-02 | ALTO | Una sola frase per i tre bot (`history-criterio`) | `components/trading/TradingHistory.tsx` | `StoricoMikeGiornoRegolamento.test.tsx` (riscritto), `Omega.storico.test.tsx` |
| B-03 | ALTO | `DayAttribution` aggiunge `'match'`; `attributionOf` restituisce sempre `'match'`; `belongs` usa `in_day`. Senza `in_day` scatta `ripiegoAttribuzione(variant)`, contato in `senzaGiornoPartita` | `lib/dailyHistory.ts` | `dailyHistory.test.ts` (riscritto il blocco attribuzione, 4 test), `StoricoMikeGiornoRegolamento.test.tsx` |
| B-04 | ALTO | Il dettaglio di StoricoSport usa `attribution={attributionOf(d.variante)}`, mai un valore cablato | `pages/StoricoSport.tsx` | «B-04: …Mike usa il criterio della CELLA» (2 test) |
| B-05 | MEDIO | Testi del dettaglio: «+N di altre giornate (partite di altri giorni…)», «liability delle partite del giorno», tolto «(prec.)», aggiunto «(piazz.)» quando l'inizio partita non è noto, note di ripiego | `components/trading/DayDetail.tsx` | `DayDetail.test.tsx` (aggiornati) |
| B-06 | MEDIO | «aperture delle partite del periodo» nell'hint e nella tabella dei breakdown | `pages/StoricoSport.tsx`, `PerformancePanel.tsx` | — (solo testo) |
| B-07 | MEDIO | `EQUITY_AXIS_NOTE_GIORNATE` («ogni gradino è una giornata (le partite di quel giorno)») per Storico e PerformancePanel. La curva intraday delle pagine bot resta «un regolamento». Nuovo testo per la curva vuota | `EquityCard.tsx`, `PerformancePanel.tsx`, `tradeStatus.ts`, `StoricoSport.tsx` | `PerformancePanel.test.tsx` (aggiornato) |
| B-08 | MEDIO | `TIP.realizedToday`, `matches`, `operations` non affermano più un criterio. Il dettaglio ha il suo tooltip, sul giorno partita | `lib/tradeStatus.ts`, `DayDetail.tsx` | `designSystem.test.tsx:494` (aggiornato e verificato in negativo) |
| B-09 | ALTO | `GiornoDa` aggiunge `'partita'`; aggiunto `giornoConfermato`. `giornoDalDatabase` legge le chiavi del contratto e la memoria le eredita (`unisciRighe`). Testi: title, aria-label, «(giorno della partita)» | `lib/posizioniChiuse.ts`, `PosizioniChiuse.tsx` | `posizioniChiuse.test.ts` (5 test nuovi), `PosizioniChiuse.giornoPartita.test.tsx` (nuovo, 8 test), `raggruppamento.test.tsx` («aperta ieri sera…» riscritto in 2 test) |
| B-10 | ALTO | La memoria della lettura scade anche per IERI (60 s) | `lib/chiuseGiornata.ts` | `chiuseGiornata.test.ts` «B-10: anche IERI scade…» |
| B-11 | MEDIO | Una nota per ciascun ripiego, con il conteggio: inizio non noto → piazzamento; giornata PROVVISORIA; banner quando il database non manda il giorno | `PosizioniChiuse.tsx` | `PosizioniChiuse.giornoPartita.test.tsx`, `raggruppamento.test.tsx` |
| B-12 | MEDIO | Controprova sullo STESSO perimetro della barra (`regolatoNelGiorno`: gambe live regolate oggi, netto Betfair oppure stima). Le posizioni a cavallo della mezzanotte compaiono in un elenco (`cr-chiuse-a-cavallo`) con giorno della partita, giorno del regolamento e importo. Tolta la causa «ordini tennis piazzati ieri e regolati oggi» | `lib/posizioniChiuse.ts`, `PosizioniChiuse.tsx` | `PosizioniChiuse.giornoPartita.test.tsx` (B-12, 3 test), `posizioniChiuse.test.ts` (3 test) |
| B-13 | MEDIO | Le righe in memoria sono marcate PROVVISORIE ed ereditano il giorno appena arriva la lettura. Il testo «in corso» lo spiega | `PosizioniChiuse.tsx`, `lib/posizioniChiuse.ts` | «in memoria senza il giorno del database: oggi PROVVISORIA» |
| B-14 | MEDIO | «Tutto» diventa «Ultimi 400 giorni». **Non unificati** i periodi fra Storico dello sport e Storico dei bot (si cambierebbe PerformancePanel con tutti i suoi test: fuori dal criterio «modifiche minime»). `window_clamped` non letto: la RPC restituisce un array e l'audit non indica dove compaia il campo | `lib/storicoSport.ts` | `storicoSport.test.ts` «B-14» |
| B-15 | ALTO | La finestra letta è `historyWindow(griglia del mese, periodo)`, come in TradingHistory. I numeri restano del periodo (`filterRange`) e il calendario mostra tutto ciò che è stato letto. Se il periodo viene troncato lo si dice | `pages/StoricoSport.tsx` | 2 test «B-15» |
| B-16 | BASSO | «Oggi» si ricalcola ogni minuto. Il ripiego senza `Intl` tiene conto dell'ora legale (`offsetRomaMs`) | `StoricoSport.tsx`, `lib/dailyHistory.ts` | `dailyHistory.test.ts` «B-16» |
| C-01 | ALTO | Se un bot che ha giornate non ha l'importo piazzato, il ROI del totale resta «—». Con il criterio vecchio rilevato (righe senza `in_day`) il ROI di Mike è «—» e il banner lo spiega. Con il contratto nuovo l'importo segue già il giorno partita lato SQL | `lib/storicoSport.ts`, `StoricoSport.tsx` | `storicoSport.test.ts` «C-01/D-01», `StoricoSport.test.tsx` B-04 (ROI «—» con il criterio vecchio, 47,5 % con quello nuovo) |
| C-02 | ALTO | Tolto «migrazione da applicare». Il testo dice «ROI non disponibile: manca l'importo piazzato… (serve un aggiornamento del database)» oppure «(i bot tennis non registrano l'importo…)» | `StoricoSport.tsx` | ROI test (aggiornato) |
| C-03 | ALTO | **Lato frontend non si può chiudere: va deciso.** Il brief chiedeva `coalesce(pnl_betfair, pnl)` nello storico live. Il referto SQL (`GIORNATA_DI_RIFERIMENTO_SQL.md` §3) dice invece «il motore resta su `pnl`»: su Mike 10 righe su 60 hanno `pnl_betfair` e la differenza è 0; Safe non ha righe live con `pnl_betfair`. Per tenere «dettaglio = cella» anche il dettaglio resta su `pnl`: una prima versione col netto Betfair è stata TOLTA perché avrebbe contraddetto la cella. A schermo la fonte è dichiarata: «P&L scritto da ogni bot (conto Betfair e stima non separati per giornata)». Storico e Chiuse coincidono solo finché `pnl_betfair` = `pnl` | `lib/dailyHistory.ts`, `StoricoSport.tsx` | `dailyHistory.test.ts` «C-03» (3 test; falsificazione col netto Betfair nel dettaglio: 2 rossi) |
| C-04 | MEDIO | Nota fissa in Chiuse: «Qui solo operazioni CHIUSE in tutte le gambe… (lo Storico le conta già)». Nessun importo, perché le righe dei cicli aperti non stanno nella scheda | `PosizioniChiuse.tsx` | `giornoPartita.test.tsx` «note fisse» |
| C-05 | MEDIO | Il sotto-testo di «Vinte / perse» aggiunge «· N pari/annullate». `AggregatoBot.pari` e `TotaleStorico.pari`. **Non allineata** la soglia ±0,005 delle Chiuse con lo zero esatto del SQL: si toccherebbe l'esito di tutte le Chiuse | `storicoSport.ts`, `StoricoSport.tsx` | «C-05» |
| C-06 | MEDIO | Lo scalper è dichiarato nella controprova con la sua cifra («…non è in questa scheda: non registra posizioni»). `FONTI_ASSENTI.calcio` riporta il motivo vero. Corretto il commento di `VOCI_BARRA` | `PosizioniChiuse.tsx`, `storicoSport.ts` | «C-06» (component), `storicoSport.test.ts` |
| C-07 | ALTO | Il nome della partita tennis arriva da `event_name` della lettura | `lib/chiuseGiornata.ts` | `chiuseGiornata.test.ts` «C-07» |
| C-08 | MEDIO | Badge «parziale» accanto al totale quando una giornata passata viene letta in ripiego (bot tennis assenti) | `PosizioniChiuse.tsx` | — (logica di una riga; vedi «non verificato») |
| D-01 | ALTO | I 4 bot tennis entrano in `FONTI_STORICO.tennis` tramite `fetchTennisBotDaily(from,to,modo,bot)`, una moneta per lettura. `FONTI_ASSENTI.tennis = []`. ROI «—» dichiarato. Le «operazioni» sono ordini, e la riga lo dice. Il dettaglio rimanda alle Posizioni chiuse (nessuna lettura in più) | `lib/storicoSport.ts`, `StoricoSport.tsx` | `storicoSport.test.ts` (riscritto), `StoricoSport.test.tsx` (3 test tennis); «stessi ordini: totale Storico == totale Chiuse» |
| D-02 | MEDIO | Lato SQL (altro delegato): le chiuse tennis devono passare al giorno partita. Il frontend usa le chiavi se arrivano | — | — |
| D-03 | MEDIO | `stimati` letto e mostrato («(N ordini ancora stimati)») | `lib/tennis.ts`, `StoricoSport.tsx` | «D-03/D-04: solo bot tennis…» |
| D-04 | MEDIO | La fonte compare sotto il P&L: «di cui conto Betfair X · stima Y» quando tutti i bot la separano (oggi solo i bot tennis); altrimenti «fonte: P&L scritto da ogni bot (conto Betfair e stima non separati per giornata)»; in prova «simulato» | `StoricoSport.tsx` | «D-04», «D-03/D-04» |
| D-05 | BASSO | Un solo termine: «importo piazzato» / «ROI su importo piazzato» | `StoricoSport.tsx` | — |
| D-06 | BASSO | **Non fatto**: unificare i due tipi `FontePnl` tocca `eventGroups` e molte pagine | — | — |

Tutti i reperti ALTI sono corretti, tranne **C-03**: la fonte del P&L dipende dal SQL e ha due indicazioni opposte (brief del coordinatore e referto SQL), quindi serve una decisione. Fino ad allora la differenza è dichiarata a schermo. Dei MEDI restano solo tre punti, ciascuno con il suo motivo: B-14 in parte (periodi), C-05 in parte (soglia del «pari»), D-02 (è lato SQL). Dei BASSI resta D-06.

## Numeri delle suite

- Prima delle modifiche: 307 file passati e 10 saltati; 4649 test passati e 50 saltati.
- Dopo, prima di t10 (fonte «N ordini stimati»): **308 file passati e 10 saltati; 4702 test passati e 50 saltati; 0 falliti.**
- Dopo t10 e dopo le falsificazioni, sulla base originale: 308 file passati e 10 saltati; 4703 test passati e 50 saltati.
- **Dopo il merge fast-forward su master `2ac4105`** (testata e Obiettivo; nessun file in comune con questo lavoro, nessun conflitto): **310 file passati e 10 saltati; 4748 test passati e 50 saltati; 0 falliti.**
- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori**, prima e dopo il merge.

## Falsificazioni

Script: `_tmp_edits/falsifica.py` nel worktree. Per ogni caso rimette il comportamento vecchio, lancia i test e poi ripristina il file dalla copia in memoria, con verifica byte per byte. Nessun file è rimasto mutato: dopo le falsificazioni tsc e la suite sono stati rilanciati. Tutte e **24** le mutazioni fanno diventare ROSSI i test nuovi. In sintesi:

| Mutazione (comportamento vecchio rimesso) | Esito |
|---|---|
| A-01 riga con la cifra dell'altra moneta nello Storico | 1 failed (A-01) |
| A-02 cifra mista di Omega nel blocco | 1 failed |
| B-03 `attributionOf` per variante (piazzamento/regolamento) | 6 failed |
| B-03b `in_day` ignorato | 3 failed (mezzanotte, ripiego, accettazione +1,88) |
| B-04 `attribution="placed"` cablato nel dettaglio | 1 failed |
| nota di ripiego spenta | 1 failed |
| C-03 (rifatta dopo la correzione) netto Betfair rimesso nel dettaglio, cioè diverso dalla cella | 2 failed |
| B-16 ripiego fisso a +2 h | 1 failed |
| B-09 giorno dal regolamento (database ignorato) | 11 failed |
| memoria che non eredita il giorno | 3 failed |
| esclusione della chiusura di ieri spenta | 1 failed |
| B-10 scade solo oggi | 1 failed |
| C-07 nome tennis null | 1 failed |
| B-12 controprova col totale della scheda | 3 failed |
| A-08 badge solo in soldi veri | 1 failed |
| D-01 tennis senza i 4 bot | 4 failed |
| C-01 ROI del totale con l'importo di alcuni bot | 1 failed |
| B-15 lettura del solo periodo | 2 failed |
| A-04 cifra dell'altra moneta nella pagina Safe | 2 failed |
| A-05 Omega con righe miste | 1 failed |
| A-06 Safe con sport «tutti» | 1 failed |
| A-07 Mike senza moneta | 1 failed |
| D-03 `stimati` non letti | 1 failed |

L'output integrale è in `_tmp_edits/falsifica_out.txt` e `falsifica_out2.txt`. Il primo giro si è interrotto per un errore di stampa (cp1252) dopo che A-04 aveva già ripristinato il file. A-04…D-03 sono stati rilanciati con UTF-8.

## Test di accettazione del coordinatore

Finti con le stesse chiavi delle risposte vere.

- `StoricoMikeGiornoRegolamento.test.tsx`: `get_mike_daily` 30/09 = +1,88, 5 piazzati, 5 regolati, 2V 3P. Cella, KPI e dettaglio dicono gli stessi numeri (+1,88 · 5 trade · 2V 3P). Il 01/10 non ha righe: dettaglio vuoto, nessuno zero inventato.
- `chiuseGiornata.test.ts`: Posizioni chiuse 30/09 = 14 righe con `giornoPartita = true`; 01/10 = 0 righe.

## I 10 casi «non coperti» dell'audit

1. Mezzanotte 23:30 → 01:15, coperta in cella e dettaglio (`StoricoMike…`), Chiuse (`posizioniChiuse.test`, `giornoPartita.test`) e controprova con la barra. Resta fuori la barra stessa, che non è nel mio perimetro.
2. Dettaglio di Mike coerente con la cella: StoricoSport B-04.
3. `pnl_betfair` diverso da `pnl`: coperto per il dettaglio (C-03). L'uguaglianza fra cella dello Storico e Chiuse dipende dal SQL (`coalesce` nel motore) e non si può verificare qui.
4. Calendario su un mese fuori finestra: coperto (B-15).
5. Nessuna cifra della prova nella vista soldi veri, e viceversa: coperto (A-01).
6. Tennis, totale Storico == totale Chiuse sugli stessi ordini (`storicoSport.test`); nome partita nelle giornate passate (C-07).
7. Scadenza della lettura di IERI: coperto (B-10).
8. Ripiego dichiarato, per riga e con conteggio: coperto (DayDetail, Chiuse, StoricoSport).
9. Moneta dichiarata nella testata di Omega, Safe e Mike: coperto.
10. `window_clamped`: **non coperto**, vedi B-14.

## Cosa NON ho potuto verificare

- **Database**: non verificabile da qui (MCP Supabase ENOTFOUND). Non so se la migrazione del 01/10 è applicata, né che forma abbiano davvero le chiavi nuove. Ho scritto il codice sul contratto dichiarato dal coordinatore: `giorno_partita`, `giorno_da` ('partita'|'piazzamento'), `in_day`, `event_name` per il tennis. Una sola ipotesi è mia: con `giorno_da = 'piazzamento'` le Chiuse prendono il giorno di piazzamento dell'APERTURA, come fa il SQL. Va controllata contro la migrazione vera.
- **A schermo**: niente app né build, solo jsdom. Colori, a capo e lunghezza delle note nuove (cavallo della mezzanotte, provvisorie, ripiego) non li ho visti.
- **Fuori perimetro, NON toccati** (da decidere):
  - la plancia del Control Room «oggi per bot» (`pnlChiuseDelGiorno` in `useControlRoom.ts`) e la barra live restano per regolamento, perché usano solo le righe in memoria: la plancia può dire una cifra diversa dalla scheda Chiuse di oggi per le partite a cavallo della mezzanotte;
  - `lib/mike.ts` mostra ancora `mike_history_v2.sql` nell'errore dello Storico di Mike;
  - `StatoOrdine.tsx` ha nel tooltip il nome `trades_consapevolezza_ordine_2026-09-16.sql`;
  - `Mike.tsx` riga «N operazioni in paper non sono elencate» è un conteggio, non una cifra in euro, e non l'ho toccata.
- **Esclusione «partita di un altro giorno»** nelle Chiuse: una riga che Betfair ha regolato più di 5 minuti prima della lettura ma che il bot scrive dopo la lettura resta esclusa fino alla lettura successiva (al massimo 60 s per oggi e ieri). Il margine è una mia scelta (`MARGINE_LETTURA_MS`).
- **C-08 «parziale»** non ha un test dedicato.
- Lo storico di Omega usa `historyModeScelto ?? mode`. Il primo render, con `control` non ancora letto, chiede `paper` (il valore di partenza della pagina) e poi si riallinea.
