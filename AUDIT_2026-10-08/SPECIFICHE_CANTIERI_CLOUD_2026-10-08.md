# SPECIFICHE PER LA SESSIONE CLOUD — cantieri dell'08/10/2026

Autore: coordinatore sul PC (Fable 5.1), su ordine dell'utente dell'08/10.
Destinatario: la sessione cloud (coordinatore + delegati). Ramo: `claude/eloquent-franklin-g2nyk5`.
Comunicare in italiano. Regole: `CLAUDE.md`, `BRIEF_STANDARD_DELEGATI.md`, `PROCESSO_STANDARD_BOT.md` §6-§7.

## 0. Ordine dell'utente (testuale) e regole del gioco

> «Massima attenzione al codice. Indicazioni chiare e mirate. Non accetto regressioni di nessun tipo.
> Il codice e' funzionante e in produzione, voglio che resti cosi'. Non accetto regressioni o bug di nessun tipo.»
> «I replay devono essere perfetti e replicare il funzionamento del bot esattamente come se operasse nella realta'.
> Sia calcio che tennis.»
> «L'utente deve poter utilizzare tutti gli strumenti in pochi secondi, senza aspettare caricamenti infiniti.»

Regole vincolanti per OGNI cantiere di questo documento:

1. **Punto di partenza**: la cima del ramo DOPO il commit del coordinatore PC «fix(banco): regola del mercato
   che attraversa» (tocca `Betfair/stream/backtest/banco_comune.py`, `varianti_bot.py`,
   `Betfair/stream/scalper/tools/replay_registrazioni.py`, `Betfair/stream/tennis_live/tools/replay_bot.py`).
   `git fetch origin` e verificare che quel commit ci sia: finche' non c'e', NON partire sui cantieri 7 e 11.
2. **Nessuna strategia toccata**: soglie, stake, tetti, gambe, finestre, condizioni d'ingresso e d'uscita
   restano quelle di produzione. Una divergenza si SCRIVE e si porta all'utente, non si corregge.
3. **Modifica minima**: mai riscritture, mai «mentre ci sono sistemo anche». Ogni cantiere = un merge
   separato, con il suo referto in `AUDIT_2026-10-08/<cantiere>/` e il suo blocco in `CRONOSTORIA.md`.
4. **Prova di non regressione obbligatoria, numero per numero**: replay PRIMA (cima di partenza) e DOPO
   (stessa registrazione, stessi scenari, `--worker 1`) con `diff` dei referti esclusi tempi e hash;
   ogni riga diversa va elencata e spiegata dalla correzione; una riga non spiegabile = cantiere fermo,
   reperto scritto, niente merge. Stessa cosa per le suite: `python -m pytest Betfair/ -q -p no:cacheprovider`
   0 rossi; `frontend/`: `npx tsc -p tsconfig.app.json --noEmit` 0 errori, `npx vitest run` 0 rossi.
5. **Falsificazione**: ogni test nuovo va reso rosso con una mutazione del codice (scritta nel referto con
   il numero di rossi), poi ripristino verificato con lo sha del file.
6. **Finti con chiavi e tipi identici al vero** (nessun finto «comodo»). Nessun fill, snapshot o book a mano.
7. **Prestazioni**: ogni cantiere misura il tempo prima/dopo delle cose che tocca (replay, pagina, test) e
   lo scrive nel referto. Un rallentamento e' una regressione.
8. **Git**: commit solo dei propri file, uno per uno, mai `git add -A`; `git fetch` + merge prima di ogni
   commit, mai rebase, mai force-push. Migrazioni in `migrations/`, MAI applicate dal cloud.
9. **Il PC verifica**: ogni cantiere viene rifatto sul PC dal coordinatore (diff riletto, test e replay
   rilanciati, mutazioni proprie, prova a schermo). Il referto deve permettere questa ripetizione: comandi
   esatti, file, numeri attesi.
10. **Ordine consigliato**: 12 → 5 → 6 → 14 → 10 → 13 → 7 → 9 → 11 (con la misura iniziale dell'11, sola
    lettura, fatta subito in parallelo).

---------------------------------------------------------------------------------------------------

## CANTIERE 5 — Parcheggio del place-and-trim nei bot TENNIS: uniformare al calcio e verificare

**Problema.** Nel calcio (cantiere L del 07/10) il parcheggio della banca nel place-and-trim sta nella banda
che Betfair accetta: `Betfair/stream/scalper/scalper_bot.py::stato_parcheggio` (righe 124-157) usa
`trading/submin.place_min_size` (1,00) e `submin.quota_parcheggio_lontano` (LAY: la quota piu' bassa con la
banca residua dentro la banda INVALID_PROFIT_RATIO 0,80-1,25: 0,70 → 1,03, 0,80 → 1,01; None = nessuna
quota sicura = nessun ordine). I bot tennis parcheggiano ANCORA a LAY 1,01 fisso: per resti fra 0,50 e 0,79
Betfair rifiuterebbe il taglio (INVALID_PROFIT_RATIO). Riferimenti: `Betfair/stream/tennis_scalper/tennis_scalper_bot.py`
(`_place_exact` ~2636, `_drive_submins` ~2757, commento ~2216 «PARK ... LAY@1.01»); tennis_pro/FLB/swing
passano dalla condotta ordini comune del tennis (`Betfair/stream/tennis_live/`, cercare chi costruisce il
`SubminState` con `park_price`); il banco tennis `Betfair/stream/tennis_live/certificazione_bot.py:220`
`_QUOTA_PARCHEGGIO = {"BACK": 1000.0, "LAY": 1.01}` controlla la quota del parcheggio come fissa.

**Da fare.**
- Una sola fonte: i bot tennis (scalper tennis, pro, FLB, swing, safe_tennis se usa il place-and-trim) prendono
  `placed_size` da `place_min_size` e `park_price` da `quota_parcheggio_lontano`, come il calcio. Nessuna
  copia della logica: si chiama la stessa funzione di `trading/submin.py`.
- Banco tennis: il controllo del parcheggio accetta la quota in banda (1,01-1,03 per LAY, 1000 BACK) e
  VERIFICA che sia quella di `quota_parcheggio_lontano(lato, residuo)`; una quota diversa = violazione.
  Nuovo controllo con sigla, falsificato (parcheggio a 1,01 con residuo 0,70 deve essere rosso).
- Caso `None` (nessuna quota sicura): il bot non manda l'ordine e lo scrive nell'attivita'; il banco lo verifica.
- Test unitari per ogni bot toccato: residui 0,50 / 0,70 / 0,79 / 0,80 / 0,99 → quota attesa; falsificati.

**Prova di non regressione.** `certifica <bot> 35790089 --data-dir <tennis_rec/20260707> --scenari tutti --worker 1`
per tennis_scalper, tennis_pro, tennis_flb, tennis_swing, safe_tennis, prima e dopo; piu' `tennis_pro 35794049`
e `tennis_scalper 35794049` (registrazione piu' liquida). ATTESO: 0 violazioni; differenze SOLO nelle quote di
parcheggio (1,01 → 1,02/1,03 dove il residuo e' 0,50-0,79) e nelle righe di attivita' corrispondenti; esiti,
tick, decisioni, netti identici. Riferimenti del mattino del 07/10: `AUDIT_2026-10-07/riferimenti_coordinatore/finale/tennis_finale_<bot>.txt`.

**Non fare.** Non cambiare quando si chiude, quanto si chiude, la sequenza place-and-trim, i TTL. Solo la quota
e l'importo del parcheggio, dalla fonte unica.

---------------------------------------------------------------------------------------------------

## CANTIERE 6 — Banco tennis: nomi dei giocatori e scenario `gate-aperto`

**Problema.** (a) `python -m Betfair.stream.backtest.certifica` per i bot tennis NON passa i nomi dei giocatori
(`_names.json` accanto alle registrazioni, che `Betfair/stream/tennis_live/tools/replay_bot.py` sa leggere:
`--nomi` o cache `_names.json` in `data_dir`, righe ~465-480): i setup di tennis_pro che dipendono dai nomi
(fade dopo il break del favorito, set transition, break point: cantiere I del 07/10, D1-D3) non si certificano
sul banco ufficiale. (b) Lo scenario `gate-aperto` cambia parametri regolabili dalla UI
(`min_book_size`, `min_matched`, `min_total_matched`, `price_max`, `price_min`) e lo dichiara in nota: va
bene, ma deve essere l'UNICO scenario che lo fa e non deve mai toccare parametri di strategia.
(c) Sul PC la 35790089 non e' nel `_names.json` (solo la 35794049): il banco deve dirlo, non tacere.

**Da fare.**
- `certifica` (registro tennis in `Betfair/stream/backtest/registro_bot.py`, `_MODULI_TENNIS`) passa al banco
  tennis il `_names.json` della cartella risolta (stessa cartella che trova `applica_bot.risolvi_cartella_tennis`,
  commit `69baf115`); se il file manca o non ha la partita, il referto lo scrive in testa
  («nomi dei giocatori ASSENTI: setup X, Y, Z non esercitabili») e i controlli che dipendono dai nomi
  risultano `⊘ non esercitabile` con causa, mai «conforme» a vuoto.
- Scenari nuovi di tennis_pro con i nomi, sulla 35794049 (Sinner-Struff, nomi presenti): uno per fade dopo il
  break del favorito, uno per la transizione di set, uno per il break point; per ciascuno il controllo del
  banco deve essere sollecitato almeno una volta (contatore > 0) oppure dichiarato `⊘` con causa misurata
  sulla registrazione (es. «nessun break del favorito nella registrazione»).
- `gate-aperto`: test di contratto che elenca i parametri cambiati dallo scenario e fallisce se compare un
  parametro che non sia nella lista bianca dei «numeri che l'utente puo' gia' cambiare dalla UI»
  (`parametri_modificabili` del bot, `Betfair/stream/backtest/varianti_bot.py`).
- Nel referto del banco, in testa: «nomi: presenti/assenti», «parametri cambiati dallo scenario: ...».

**Prova di non regressione.** Tutti e 5 i bot tennis `--scenari tutti` su 35790089 e 35794049 prima/dopo:
identici salvo le note nuove e gli scenari aggiunti; 0 violazioni.

**Non fare.** Non inventare nomi; non dedurli dall'IPS troncato per i setup (quello vale solo per la UI,
cantiere 14). Non cambiare fade/set transition/break point: si certificano, non si modificano.

---------------------------------------------------------------------------------------------------

## CANTIERE 7 — Banco di Omega: reperti RB-1 … RB-5 (`AUDIT_2026-10-07/OMEGA_APERTURA_35760084.md` sez. 10)

Nessuno tocca `omega_v3.py`/`omega_engine.py`: sono difetti del BANCO e del servizio di replay. Dettagli:

- **RB-1 conflazione che perde l'ultimo stato** — `banco_comune.py` `ScannerReplay.applica_book`
  (era alle righe 2561-2565): tiene il PRIMO book di ogni secondo per mercato e scarta gli altri. Betfair
  (`conflateMs`) consegna lo stato FUSO piu' recente. Prova: l'HT della 35760084 passa SUSPENDED → CLOSED
  nello stesso secondo (16:47:58) e il CLOSED si perde: nel banco l'HT non e' mai CLOSED. Correzione: per
  ogni secondo e mercato consegnare l'ULTIMO stato (fuso), mai perdere uno stato terminale. Test:
  due book nello stesso secondo, il secondo CLOSED → lo scanner vede CLOSED. Falsificare.
- **RB-2 il banco consegna mercati che lo scanner vero non seguirebbe** — `applica_book` controlla solo
  `market_meta`, non le finestre dei candidati (HT/CS/O-U): l'HT riceve book fino al 47' mentre
  `is_ht_candidate` e' falso dal 45'. Correzione: stesse finestre di sottoscrizione della produzione
  (la funzione di produzione, non una copia). Test con falsificazione.
- **RB-3 eta' assurde nei testi** — `flusso_prezzi._con_eta` usa l'orologio di sistema contro `dal_ms` in
  tempo di mercato («da 8534488 s»). Correzione: orologio di mercato nel replay (lo stesso meccanismo che
  il banco usa per `time.time`). Solo testo, ma il testo finisce nei referti: test.
- **RB-4 il paper di Omega non si certifica sul banco** — lo scenario `paper`
  (`Betfair/omega/tools/replay_registrazioni.py`, ~976 e nota ~2320) non ha il runner: dal 28/09 il paper di
  Omega passa SOLO dal runner (`omega_service.py` ~2858-2869, `paper_runner_non_disponibile`). Correzione:
  agganciare la porta del runner del banco allo scenario `paper` (come `--trasporto canale`), aggiornare la
  nota; ATTESO sulla 35760084: il paper apre il '3 - 3' come il live (parita' paper/live dimostrata).
- **RB-5 cache di processo non azzerate fra scenari** (catalogo §7.37) — `_EMPIRICAL_CACHE` e
  `_MINUTE_CACHE` (`omega_service.py` ~1313-1374) non sono nell'elenco delle cache che il banco azzera:
  con `--worker 1` la tabella letta da uno scenario resta per i successivi. Correzione: aggiungerle
  all'elenco del banco (non toccare come Omega le usa); test: due scenari in sequenza, il secondo non vede
  la cache del primo.

**Prova di non regressione.** `certifica omega 35760084 --scenari apertura` e `--scenari tutti`, idem 35797769,
prima/dopo (riferimenti: `AUDIT_2026-10-07/omega_apertura_35760084/replay/FINALE_*` e `DOPO_*`). ATTESO:
467 decisioni / 2 azioni sulla 35760084 `apertura` invariati; `tutti` 20/20 su entrambe; differenze SOLO
spiegate (HT ora CLOSED, paper con runner, testi dell'eta', note `[NON ESERCITABILE]` corrette). Il `tutti`
della 35797769 dura 33 minuti: misurare e, se si riesce senza controllare meno, portarlo sotto il tetto (vedi 11).

---------------------------------------------------------------------------------------------------

## CANTIERE 9 — Scalper/sniper CALCIO: scavalco, tetto di perdita, rifiuti Betfair (copertura del banco)

**Contesto.** Il 07/10 sera (merge `83ac73c9`): residuo da ingresso abbinato sotto 0,50 chiuso con due ordini
legali (`ordine_di_scavalco`, `scalper_bot.py:158`), tetto di perdita senza i residui (`stats.pnl_residui`),
chiusure dimensionate al best. Mai provato su Betfair vero; sul PC si prova in PROVA (non nel cloud).

**Da fare nel banco (non nei bot).**
- Scenario che forza un ingresso abbinato in parte sotto 0,50 (es. 0,29 su 10) e verifica: scavalco
  (punta 1,00 + chiusura al centesimo) entro N book, posizione PIATTA a fine ciclo (|differenza fra gli
  esiti| ≤ 0,02), al massimo 3 scavalchi per ciclo, attivita' `scavalco` e `loss_cap` con due cifre.
- Scenario `rifiuti-betfair` esteso: il finto Betfair risponde con i codici veri `INVALID_PROFIT_RATIO`,
  `INVALID_BET_SIZE`, `BET_TAKEN_OR_LAPSED` sugli ordini del place-and-trim e dello scavalco (stesse chiavi e
  tipi delle risposte vere di `placeOrders`/`replaceOrders`); ATTESO: nessuna posizione fantasma, nessun loop,
  ogni rifiuto scritto nell'attivita', residuo dichiarato se non chiudibile.
- Parita' paper/live sugli scenari nuovi (stesse azioni, stessi importi).
- Nel referto: tabella «caso → ordini mandati → risposta → stato finale della posizione».

**Prova di non regressione.** `certifica scalper_calcio 35797769 --scenari tutti --worker 1` e
`certifica sniper_calcio` (o lo scenario `sniper-paper`) prima/dopo: identici (riferimento
`AUDIT_2026-10-07/riferimenti_coordinatore/finale/scalper_N2.txt`: base 44, paper 44,
chiusura-abbinata-in-parte 215, rifiuti-betfair 56, sniper-paper 44, 0 violazioni) salvo gli scenari nuovi.

**Non fare.** Non toccare `scalper_bot.py`/`sniper_bot.py` se non per un bug dimostrato dal banco (allora:
test rosso → verde, falsificazione, e lo si scrive in testa al referto).

---------------------------------------------------------------------------------------------------

## CANTIERE 10 — Registro operazioni e P&L del bot: fasi separate e conteggio dei cicli allineato

**Problema (visto a schermo dall'utente l'08/10, Match Replay 35768297, media under).**
(a) Il registro mette in fila pre-partita e gioco senza separarli: illeggibile. (b) Il registro conta 3 cicli
(`frontend/src/lib/replayOperazioni.ts::cicliOperativi`, ~568: ciclo = da posizione piatta a piatta) mentre il
bot e il DB ne contano 4 (`esito.cicli_bot`): le prime due coppie punta/banca del bot (ciclo 1 chiuso alle
23:04:21 con rientro immediato alle 23:04:21.752, stesso istante) vengono fuse in un solo «Ciclo 1» da +0,37,
e la riga «per il bot: lordo +0,18» di quel ciclo non torna con il +0,37. I totali tornano (+0,76).

**Da fare.**
- Fonte dei cicli: quando l'esito porta `cicli_bot`, il registro usa ESATTAMENTE i cicli del bot (numero,
  istanti, origine `clic`/`rientro automatico`, lordo/netto) e li chiama con i numeri del bot; la regola
  «da piatto a piatto» resta solo come ripiego quando `cicli_bot` manca, e in quel caso lo dice.
  Test: esito con 4 cicli del bot → 4 cicli nel registro; 2 cicli che si toccano nello stesso istante
  restano 2. Falsificare. Test di contratto Python↔TS sulla forma di `cicli_bot` (chiavi identiche).
- Fasi: il registro e il riquadro P&L si dividono in sezioni fisse PRE-PARTITA / 1° TEMPO / INTERVALLO /
  2° TEMPO (calcio; dal tabellone e dallo stato IPS della registrazione, fonte unica gia' usata dalla barra:
  `replayTimelineEvents.ts::punteggioAlTs` e gli eventi KickOff/FirstHalfEnd/SecondHalfKickOff) e per il tennis
  PRE-PARTITA / SET 1 / SET 2 / … . Ogni sezione: cicli, ordini, P&L lordo/netto della sezione; i totali in
  fondo uguali a quelli di oggi («✓ uguale al banco»). Un ciclo che attraversa due fasi sta nella fase in cui
  e' nato, con l'indicazione «chiuso al 14'».
- Riquadro P&L: aggiungere la riga «per fase» (pre-partita / 1T / 2T) sopra «a regolamento»; niente altro
  cambia (i tre blocchi attuali restano, con gli stessi numeri).
- Il pulsante «mostra anche i N tolti senza abbinamenti» e la tabella ordini restano come sono.

**Prova di non regressione.** Fixture `frontend/src/lib/__fixtures__/replay_pro/esito_*.json` (5 esiti veri
di bot diversi): per ciascuno, totali identici a prima (test gia' esistenti `replayOperazioni.test.ts` restano
verdi senza modifiche ai numeri attesi), piu' i test nuovi; vitest intero 0 rossi, tsc 0 errori.

**Non fare.** Non cambiare come il bot calcola i cicli (Python); non cambiare le fotografie del frontend
se non per righe aggiunte.

---------------------------------------------------------------------------------------------------

## CANTIERE 11 — Velocita': tutto in pochi secondi (ordine dell'utente), senza controllare di meno

**Misure di partenza (08/10, PC dell'utente, DB `live_backtest_requests`):**
| cosa | oggi |
|---|---|
| «Applica bot» scalper calcio `media-under-paper` sulla 35768297, un solo scenario, dal worker | 258-314 s per ogni richiesta (6 richieste misurate) |
| ogni clic «Attiva adesso» o modifica dei clic | rifa' TUTTA la partita: altri 5 minuti |
| certificazione media under, 18 scenari su una partita | 68 min (`AUDIT_2026-10-07/replay/clic_35797769_r5.txt`), tetto del banco 600 s |
| `certifica omega 35797769 --scenari tutti` | 33 min |
| strumento della barra su 38 partite (`verifica_barra_replay.ts`) | 3,5 min |
| suite Python intera sul PC | 9-19 min |

**Obiettivi (misurabili, nel referto prima/dopo, sul PC li rimisura il coordinatore):**
- «Applica bot», un bot, uno scenario, una partita intera: ≤ 30 s. Un clic aggiunto o tolto: ≤ 5 s.
- Certificazione completa di un bot su una registrazione (`--scenari tutti`): ≤ 5 min, tetto 10 (standard
  del 29/09, `PROCESSO_STANDARD_BOT.md` §6.9) — oggi media under e Omega lo sforano.
- Pagine Match Replay e Replay Tennis: elenco ≤ 1 s, primo fotogramma ≤ 2 s, spostamento del cursore senza
  attese percepibili, caricamento del resto in sottofondo (oggi `live.ts::fetchFramesAFinestre`, finestre da
  10.000 frame).

**Metodo, nell'ordine (ogni passo con referto identico numero per numero: nessun book saltato, nessun controllo spento).**
1. **Misura prima di toccare** (sola lettura, si puo' iniziare subito): profilo (`cProfile`/`pyinstrument`)
   di una richiesta `applica_bot` e di una `certifica` lenta; dove va il tempo: lettura del raw, costruzione
   dei book, flumine, controlli del banco, scrittura dello specchio, DB. Tabella «punto caldo → secondi → %».
   Stesso per la pagina: tempi delle RPC e del rendering (devtools o misure nel codice).
2. **Punti caldi del banco**: togliere i costi che non cambiano l'esito (es. conversioni ripetute dei livelli,
   `traded_volume` convertito quando nessuno lo legge — gia' fatto il 30/09, verificare che non sia
   regredito; specchio scritto a blocchi; book identici consecutivi; parsing del raw con `orjson` se
   disponibile). Ogni ottimizzazione: referto identico (diff 0 righe esclusi i tempi) su UN replay calcio
   (`scalper_calcio 35797769 --scenari tutti`) e UN replay tennis (`tennis_pro 35790089 --scenari tutti`).
3. **Clic in pochi secondi — punti di salvataggio del banco**: il banco salva lo stato della sessione
   (bot + ordini simulati + specchio + controlli) a intervalli di tempo di mercato (es. ogni 60 s) durante
   la prima esecuzione; una richiesta con clic diversi riparte dall'ULTIMO punto di salvataggio precedente
   al primo clic cambiato. Vincolo assoluto: il risultato deve essere IDENTICO byte per byte a un'esecuzione
   intera (test: esecuzione intera vs ripresa dal salvataggio, stesso referto, stesse righe, stessi istanti).
   Se uno stato non e' serializzabile in modo fedele (es. oggetti di flumine), lo si scrive e si sceglie la
   via sicura: cache del tratto comune a livello di book gia' letti e parsati (riuso dei book, riesecuzione
   del bot) — gia' questo toglie la lettura e il parsing del raw, che vanno misurati al punto 1.
4. **Pagine**: elenco e meta in una sola RPC; frame del replay caricati per finestre piu' piccole attorno al
   cursore con prefetch in sottofondo; niente ricalcoli sincroni nel render (memoizzazione dei derivati:
   barra, registro, P&L); il worker del Backtest risponde con lo stato `RUNNING` + percentuale cosi' la
   pagina mostra l'avanzamento (oggi: attesa muta).
5. **Suite**: `pytest -p no:cacheprovider` con `-x` no; parallelizzare con `pytest-xdist` SOLO se i test sono
   gia' isolati (il 02/10 e' stato fatto l'isolamento: verificare), altrimenti no.

**Prova di non regressione.** Per OGNI passo: i due replay di riferimento identici (esclusi i tempi), suite
verdi, e tabella dei tempi prima/dopo. Un referto piu' corto o un controllo in meno = regressione.

**Non fare.** Non ridurre i book, non campionare, non spegnere controlli «perche' lenti», non cambiare la
cadenza del servizio. Non introdurre processi nuovi o cache su disco condivise fra sessioni senza dichiararlo.

---------------------------------------------------------------------------------------------------

## CANTIERE 12 — Sei test vitest rossi SOLO su Windows (test del verificatore della barra)

**Fatti (PC, `AUDIT_2026-10-07/certificazione_db/vitest_pc_pulito.txt`).**
- `frontend/src/lib/replayVerificaBarra.partite.test.ts` x2: «la registrazione 35760084/35797769 e' cambiata
  dopo la generazione della fixture». Causa: `impronteSorgente` fa lo sha256 dei byte di
  `registrazioni_banco/<id>/<id>.timeline.jsonl`; sul PC `core.autocrlf=true` scrive CRLF
  (`git ls-files --eol`: `i/lf w/crlf`), la fixture ha lo sha dei byte LF. I `.gz` non sono toccati.
- `frontend/src/lib/replayVerificaBarraScript.test.ts` x4: `spawn('npx', [...])` senza shell → `spawn npx ENOENT`
  su Windows (riga 30), poi timeout di 120-180 s.
- Stesso difetto nello strumento: `frontend/scripts/verifica_barra_replay.ts` ~107 si rilancia con
  `npx.cmd` + `shell: true` ma il percorso del file contiene uno spazio («PYTHON DATABASE») e non e' tra
  virgolette: il comando del protocollo non parte sul PC (il delegato l'ha aggirato lanciando vite-node
  direttamente). Lo sha dei `.jsonl` degli script di fixture (`tools/replay_barra_fixture.py`) va reso
  coerente con lo stesso criterio.

**Da fare.**
- Impronta indipendente dai fine riga: sha256 del contenuto con `\r\n` → `\n` (sia nel test TS sia nello
  script Python che genera la fixture); test che una copia CRLF e una LF danno la stessa impronta. NON
  cambiare `.gitattributes` (rinormalizzerebbe i file di tutti).
- Lancio dei processi figli portabile: su win32 `npx.cmd` con `shell: true` e argomenti quotati (una
  funzione sola, usata dal test e dallo script); test che il comando costruito contiene il percorso tra
  virgolette quando ha spazi. Il timeout dei test del rilancio scende a un valore che fallisce in fretta se
  il figlio non parte (es. 30 s) senza cambiare i casi.
- Sul cloud (Linux) i 6 test devono restare verdi; sul PC li rilancia il coordinatore.

**Non fare.** Non segnare i test come `skip` su Windows. Non cambiare cosa verificano.

---------------------------------------------------------------------------------------------------

## CANTIERE 13 — Strumento della barra: 13 partite su 38 con incoerenze (controllare e correggere OGNI cosa)

**Fatti (PC, `AUDIT_2026-10-07/certificazione_db/verifica_barra_tutte.txt`, uscita 1).** 38 partite nel DB,
25 coerenti, 13 incoerenti, tutte del 02/07-17/07 (prima dello standard della barra del 07/10); le due del banco
(35797769, 35760084) coerenti. Occorrenze per codice: `BUCO_REGISTRAZIONE` 67 (nota), `KICKOFF_DISCORDANTE` 12
(avviso), `SIMBOLO_GOL_SENZA_AUMENTO` 10 (ERRORE), `CARTELLINI_DIVERSI` 10 (avviso), `TABELLONE_CORREZIONE_FEED` 9,
`INIZIO_IN_CORSO` 9, `SOSPENSIONE_NON_VISIBILE` 4, `CONTEGGI_ASSENTI` 3, `GOL_ANNULLATO` 2, `PUNTEGGIO_ASSENTE` 1.
Partite con ERRORE: 35787218 Argentina-Egypt (gol senza aumento + cartellini), 35777617 Brazil-Norway,
35768297 Portugal-Croatia (quella del replay dell'08/10), 35768365 Spain-Austria, piu' una quinta nel referto.
Codici definiti in `frontend/src/lib/replayVerificaBarra.ts` (tipo `CodiceRilievo`, righe ~47-59).

**Da fare, per OGNI incoerenza delle 13 partite (nessuna esclusa):**
1. Riprodurla con la fixture della partita (`tools/replay_barra_fixture.py <id>` dalle registrazioni del DB:
   il PC fornira' i raw se non sono nel repo; chiedere) e stabilire con prova scritta se e':
   (a) falso positivo del VERIFICATORE (la pagina mostra il giusto, il controllo sbaglia: es. gol
   annullato dal VAR classificato «gol senza aumento», cartellini contati due volte nel feed) → correggere
   il verificatore con test rosso → verde e falsificazione;
   (b) difetto della PAGINA (barra/tabellone/simboli sbagliati con dati buoni) → correggere la pagina,
   stessa regola;
   (c) difetto dei DATI registrati (buco, punteggio IPS assente, kickoff mancante) → NESSUNA correzione a
   mano: strumento di CURA che rigenera timeline e punteggi dal raw con la regola unica del curatore
   (`Betfair/stream/curator.py::curate_records`, cantiere D del 07/10) e ricarica la partita; se il raw non
   basta, la partita resta dichiarata «incoerente per dati» con il motivo nella pagina (avviso visibile), mai
   silenziosa.
2. Tabella finale nel referto: partita → codice → classe (a/b/c) → correzione → esito dopo (coerente / dichiarata).
3. ATTESO a fine cantiere sul PC: `verifica_barra_replay.ts` esce con 0 sulle 38 partite, oppure con 1 e
   SOLO partite dichiarate «per dati» con causa; le 25 coerenti restano coerenti (nessuna nuova incoerenza).

**Prova di non regressione.** Fixture delle due partite del banco invariate (test `replayVerificaBarra.partite.test.ts`
verdi); mutanti `replayBarraMutanti.ts` ancora tutti rilevati; vitest intero 0 rossi.

---------------------------------------------------------------------------------------------------

## CANTIERE 14 — Replay tennis: nome «Marcelo Tomas Barrios V» troncato

**Fatti.** Il replay della 35790089 mostra «Marcelo Tomas Barrios V»: il nome arriva dall'IPS troncato.
`Betfair/stream/tennis_replay/convertitore.py` (~383-389): nome = `nomi` dati dal chiamante (catalogo del
runner o `_names.json`) → `info.name` → ripiego IPS (`nomi_ips`) → `#sid`. Sul PC il `_names.json` ha solo la
35794049; la 35790089 non c'e' ne' nel file ne' nel DB (`tennis_live_*`). Il flusso Betfair non porta i nomi dei
runner: li porta solo il catalogo (`listMarketCatalogue`).

**Da fare.**
- Registratore tennis (`Betfair/stream/tennis_live/tennis_recorder.py`, cantiere D): a ogni REC scrive
  SEMPRE accanto al raw i nomi COMPLETI dei runner di tutti i mercati registrati (catalogo), nel
  `_names.json` della cartella (chiave `event_id` → `market_id` → `selection_id` → nome), senza sovrascrivere le
  partite gia' presenti. Test con falsificazione.
- Importatore/convertitore: ordine delle fonti `_names.json` → catalogo nel DB (tabelle `tennis_live_*` o
  `betfair_market_*` se portano i nomi) → IPS; se il nome viene dall'IPS troncato, la pagina lo mostra con
  l'indicazione «nome dall'IPS, troncato» (tooltip), mai come se fosse completo. Reimport idempotente che
  AGGIORNA i nomi quando compare una fonte migliore (upsert sui mercati, senza toccare gli snapshot).
- Pagina Replay Tennis: usa il nome dell'evento (`tennis_replay_eventi`) come oggi; nessun cambio di layout.

**Prova di non regressione.** Reimport sul cloud di una cartella finta con `_names.json` completo e di una
senza: conteggi identici a prima (eventi/mercati/snapshot/punteggi), nomi aggiornati solo dove c'e' la fonte;
suite tennis_replay verde; vitest 0 rossi.

---------------------------------------------------------------------------------------------------

## Consegna

Per ogni cantiere: commit separato (merge sul ramo), referto `AUDIT_2026-10-08/<cantiere>/REFERTO.md` con
causa, file:riga, test (verdi e mutazioni rosse), replay prima/dopo con ogni riga diversa spiegata, tempi
prima/dopo, «cosa non ho potuto verificare», e il blocco in `CRONOSTORIA.md`. Alla fine: un paragrafo
«PRONTO PER LA VERIFICA SUL PC» con l'elenco dei cantieri, i commit e i comandi che il coordinatore PC deve
rilanciare, nello stile di `AUDIT_2026-10-07/HANDOFF_CERTIFICAZIONE_DB.md`.
