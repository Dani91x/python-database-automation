# I problemi del backend di oggi rispetto ai competitor (12/10/2026)

Destinatario: l'agente del PC che confronta BettingToolkit col nostro sistema
(`ARCHITETTURA_2026-10/CONFRONTO_BETTINGTOOLKIT/`). Scopo: sapere ESATTAMENTE cosa ci manca, per dire punto per punto
se BettingToolkit lo risolve, come, e a che prezzo.

Fonti (tutte nel repo, ramo `claude/architettura-tappa0` salvo dove detto): `ARCHITETTURA_2026-10/06_RIEPILOGO_PER_L_UTENTE.md`,
`07_MISURE_OGGI.md` (misure vere), `02_COMPETITOR.md` (63 fonti pubbliche), `ondata2/MATRICE_PARITA.md` (51 voci contro
i competitor, con file:riga), `ondata2/PIANO_AGGANCIO.md` (chi apre cosa, oggi e dopo), `ondata1/DECISIONI_PER_L_UTENTE.md`
(decisioni vincolanti dell'utente). I numeri qui sotto vengono da li': verificali sul codice di master se ti servono.

---

## 0. Il problema in una frase

Oggi l'app e' un insieme di ~18 processi che parlano con Betfair OGNUNO PER CONTO SUO e parlano FRA LORO attraverso il
database cloud (Supabase). I competitor (Bet Angel, Geeks Toy, Cymatic, Fairbot, Bfexplorer) sono UN programma con UNA
sessione Betfair, lo stream come fonte unica, tutto lo stato in memoria/locale e nessun database remoto nel percorso dei
prezzi e degli ordini.

---

## 1. Connessioni e sessioni Betfair: ognuno apre le sue

| Problema | Oggi (verificato) | Competitor | Conseguenza |
|---|---|---|---|
| Login | Ogni processo fa il suo: fino a **12 sessioni vive** insieme (runner calcio 2, tennis 1, scanner 1, scalper 1 + fino a 4 sessioni figlie, Omega/Safe bot/Mike 1 ciascuno), + 48 login/giorno del job quote tennis, + un login IN PIU' che flumine fa all'avvio di ogni framework (`flumine/baseflumine.py:498`) | 1 login, 1 keepAlive (.it: sessione di 20 min) | rischio di superare il tetto di login del conto, relogin a cascata, token diversi per processo |
| Connessioni Stream (limite Betfair: **10 per app key**) | prezzi calcio 1-3, ordini calcio 1, prezzi tennis 1, ordini tennis 1, scanner 1-4, ogni sessione scalper 2 in LIVE. **Caso peggiore LIVE: 10/10 senza scalper, 18 con 4 sessioni scalper** (oltre il limite: Betfair rifiuta, a caso) | un solo gestore dei flussi, 200 mercati per connessione (Bet Angel dichiara 1.000 mercati in streaming) | quando le connessioni finiscono un flusso ripiega sulla REST (lenta) o resta muto; nessuna priorita': puo' restare senza stream proprio il mercato con soldi in gioco |
| Stream ORDINI | uno per processo flumine (runner calcio, runner tennis, ogni scalper): lo stesso ordine del conto arriva 3+ volte; flumine SCARTA gli ordini senza `customerOrderRef` e quelli delle strategie che il processo non ha (`flumine/order/process.py:39-40,101-114`) | uno solo per l'app; Geeks Toy mostra anche le «External Bets» | il ladder NON vede gli ordini fatti dal sito Betfair ne' quelli degli altri processi/bot |
| REST nel percorso dei prezzi | board calcio/tennis ogni 10 s via REST; scanner sui mercati oltre la capacita' degli shard via REST; Omega e Mike leggono il book via REST nelle decisioni e uscite (`omega_market.read_book`) | REST solo di riserva (decisione utente 8: «stream dove possibile, REST solo backup») | dati vecchi di secondi, peso REST sul conto |
| Conflation dello scanner | **1.000 ms fisso** (`safe_strategy/stream.py:66-67`): lo scanner alimenta Mike, Safe e Omega | Cymatic conflate 0 ms; Bet Angel refresh 20 ms | i tre bot vedono prezzi fino a 1 s vecchi (cambiarlo cambia l'input dei bot: solo con decisione U-01 e replay) |

## 2. Popolamento del ladder: lento, parziale, a volte dal cloud

| Problema | Oggi | Competitor | Conseguenza |
|---|---|---|---|
| Cadenza | il runner pubblica il ladder al canale locale con un worker ogni **200 ms** (`config_stream.py:74`, `ladder_canale.py`): un cambio aspetta 0-200 ms prima ancora di partire; il DB `live_ladder` e' scritto ogni 0,3 s dall'app (2 s di serie) | Bet Angel: refresh fino a **20 ms**, «update» a ogni messaggio | 10 volte piu' lento del riferimento; l'utente ha deciso «massima velocita'» (20 ms) |
| Sorgente di riserva | se il canale locale non c'e', la UI legge il ladder dal **DB cloud in realtime** (`frontend/src/lib/live.ts:619-632`) | nessun DB remoto | ladder dal cloud = centinaia di ms o secondi |
| Ordini sul ladder | solo i «miei» ordini dello specchio del processo (`liveOrders.ts:530-536` via RPC cloud `get_live_orders`, o push `order` del canale); **esclusi** ordini dal sito e di altri processi; nessuna colonna «autore» | tutti gli ordini del conto (Geeks Toy External Bets) | l'utente non vede tutta la sua esposizione sul ladder |
| P&L «se vince» | per selezione da sola; P&L di mercato solo nel replay; ordini fuori specchio non contati | Bet Angel/Traderline/Fairbot: P&L in tempo reale per selezione su ogni mercato | decisione utente 5: «se vince» su TUTTI i mercati |
| Spostare un ordine (drag) | cancel POI place (2 transazioni, posizione in coda persa; `LadderView.tsx:2023-2026`) | drag&drop (Fairbot); decisione utente D-5: trascinare = replaceOrders, il bet delay riparte | doppie transazioni, coda persa |
| Annulla | per lato con N `cancel` in sequenza; **nessun «annulla tutto il mercato / tutti i mercati»** in una chiamata; decisione utente D-5: tasto destro = annulla con un clic su ogni ordine (anche dei bot, che si fermano) | Bfexplorer: chiusura singola/mercato/tutte; Betfair `cancelOrders` senza istruzioni = tutto il mercato | lento nelle emergenze |
| Bet delay a schermo | non mostrato | (Betfair lo da' nella MarketDefinition) | l'utente non sa quanto aspettera' |
| Contatore transazioni | tetto PER PROCESSO (1.000/h), non per conto; non sul ladder | Bet Angel: contatore a schermo; Betfair conta per conto (5.000/h) | rischio di superare il tetto del conto senza saperlo |
| Puntate .it | il ladder calcio TRONCA in silenzio una puntata non multipla di 0,50 (`live_order_worker.py:1497-1502`), il terminale la rifiuta | decisione utente 3: la UI offre SOLO multipli di 0,50 (nessun rifiuto, nessun troncamento nascosto) | importi diversi da quelli scelti |
| Tennis | niente FOK sul ladder tennis, cash-out e stop parziali | completi | asimmetria calcio/tennis |

## 3. Nessun DB/cache locale: tutto passa dal cloud (il problema piu' grande)

| Cosa | Oggi | Competitor | Misura |
|---|---|---|---|
| Comandi e prezzi ai bot | Mike, Safe e Omega leggono prezzi e comandi dal DB cloud a giri di **1-5 s** | in memoria | - |
| Coda ordini | un ordine messo in coda sul DB cloud viene preso dal worker che legge ogni 1 s (`LIVE_ORDER_QUEUE_POLL_SEC=1.0`) | ordine diretto dal programma all'API | coda -> elaborazione, ordini paper: **p50 492 ms, p95 2.481 ms, p99 26.636 ms, max 36.524 ms** (`07_MISURE_OGGI.md` 3b); cancel p50 406, replace p50 307, greenup p50 365 ms |
| Stop, trailing, regole armate | salvate nel DB cloud (`liveOrders.ts:435`), controllate da un giro di 0,15-1 s; tennis senza | locali, a ogni tick | un'operazione manuale con stop dipende dal cloud |
| Kill-switch, impostazioni, specchio ordini/posizioni, P&L, giornate | sul DB cloud, letti di continuo | locali | **707-1.309 richieste al DB al minuto** con l'app accesa (`07` 4a) |
| Latenza di rete verso il cloud | ogni richiesta ~21 ms p50 su connessione calda, 79 ms la prima (DNS 23 + TCP 15 + TLS 50 ms) | 0 (locale: SQLite 0,6 ms per una scrittura sicura, misurato) | ogni giro di lettura aggiunge decine-centinaia di ms; nel caso peggiore secondi |
| Peso | cloud 52 GB, 173 tabelle; `match_odds` 20 GB (92,5 M righe) | archivio locale + backup | decisione utente 10: «tutta l'app in tempo reale per Betfair, il cloud SOLO come backup, il resto sul DB locale» |

Cosa vuole l'utente (vincolante): stream -> app -> DB LOCALE -> copia in sottofondo al cloud (backup, senza doppioni,
anche dopo un'assenza di rete). Nessun dato Betfair passa dal cloud. Il cloud resta per cio' che il cloud CALCOLA
(analisi pre-partita di Mike, tabelle di Omega, statistiche), aggiornato appena cambia.

## 4. Ordini e sicurezza

| Problema | Oggi | Competitor |
|---|---|---|
| Strade degli ordini | **7 strade diverse** per mandare un ordine a Betfair, 9 modi di controllare che tornino; Mike live manda ordini per conto suo (REST) | una porta |
| Heartbeat API di Betfair (cancella i LIMIT se il programma muore) | non usata | rete di sicurezza lato Betfair |
| Monitor dell'API con pausa automatica | la «Salute» misura ma non agisce | Cymatic sospende il trading oltre soglia |
| Precedenza delle connessioni quando non bastano | nessuna (decide Betfair, a caso) | decisione utente D-4: «tutto cio' che ha soldi in gioco o da gestire ha la priorita'» |
| Ordini dei bot toccati dall'utente | oggi il bot lo vede e si ferma | decisione utente D-5: deve restare cosi' |

## 5. Fragilita' dei processi

- ~18 processi (ogni servizio = watchdog Python + figlio), spegnimento in parallelo con attese fino a 150 s.
- Se il guardiano di un servizio cade nessuno lo riavvia; chiudere la finestra spegne tutto.
- Feed: ~10 buchi all'ora oltre 5 s in partita (in parte stream, in parte registratore); rimbalzi di latenza alle
  risottoscrizioni a caldo (fino a 1.912 avvisi «High latency» in una sessione).
- Codice duplicato: 4 definizioni di «oggi», 6 copie del green-up, ogni bot col suo modo di parlare col DB.

## 6. Cosa abbiamo GIA' costruito (nucleo, ramo `claude/architettura-tappa0`, NON ancora agganciato)

`Betfair/nucleo/`: sessione unica con freno dei login (W1-A1), gestore dei flussi a 200 mercati/connessione e stream
ordini del conto senza filtro (W1-A2), ladder a ogni cambio con coalescenza 20 ms (W1-A2), porta unica degli ordini con
minimi .it (W1-C1), libro ordini del conto con autore e P&L (W1-C2), archivio locale SQLite + postino verso il cloud
(W1-G1), client cloud unico con cache (W1-G2), stato partita (W1-B). Suite 13.082 verdi. Manca l'AGGANCIO (ondata 2,
piano in `ondata2/PIANO_AGGANCIO.md`: processo unico `betfair-nucleo`, connessioni da 18 a 10, login da 12 a 1;
stima 49-64 giorni). Se BettingToolkit copre questi pezzi, la domanda vera e': ci risparmia l'aggancio o solo il nucleo
che abbiamo gia'?

## 7. Cosa NON deve cambiare (vale anche per BettingToolkit)

Strategie dei bot intoccate (soglie, stake, tetti, gambe); paper e live mai sommati; calcio e tennis mai mischiati; bot
accesi solo dall'utente; minimi italiani (1 EUR diretto, passi di 0,50); certificazione dei bot sul banco col codice di
produzione; ogni sostituzione prima in ombra e su master solo se uguale o meglio.

## 8. Cosa chiediamo al confronto (una riga per ciascun problema dei par. 1-5)

Per ogni riga: **BettingToolkit lo risolve? (si'/in parte/no)**, con file e funzione di BettingToolkit; come
(processo/thread/cache/DB); cosa servirebbe per collegarlo ai nostri bot Python, alla UI Electron/React e al canale
locale; rischi (licenza, lingua, dipendenze, chi lo mantiene, test esistenti); se e' piu' rapido del nostro aggancio.
In testa: provenienza e licenza esatta (non copiare il loro codice nel nostro repo finche' la licenza non lo permette),
lingua, dimensione, data dell'ultimo aggiornamento.
