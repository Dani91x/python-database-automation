# 08 - REVISIONE CRITICA DEL PIANO (08/10/2026)

Autore: revisore critico (Opus 5.5), occhio avversario. Perimetro: `BRIEF_PIANO_ARCHITETTURA_2026-10-08.md` (brief) contro
`04_ARCHITETTURA_OBIETTIVO.md` (04), `05_PIANO_DI_MIGRAZIONE.md` (05), `06_RIEPILOGO_PER_L_UTENTE.md` (06). Solo documenti: nessun
codice di produzione toccato, nessun processo avviato, nessun commit. Strategie intoccate: nessuna correzione qui sotto cambia una
soglia, uno stake, un tetto, una gamba o un valore di serie. Le correzioni applicate in 04, 05 e 06 sono marcate
«[revisione critica 08/10]» e rimandano al rilievo (`R..`). Non toccati: `01_FUNZIONALITA.md` e le tabelle di copertura di 05 §4
(nessuna voce spostata: la tappa T18 resta proprietaria delle sue voci, cambia solo il suo ordine nel grafo, R18).

Verifiche fatte di persona nel codice (sola lettura): `Betfair/stream/local_channel.py:170-176,630-672` (disciplina «il giro si
salta»), `Betfair/stream/motore_ordini.py:30,913,961-962,2245` (`seq`/`da_seq`), `Betfair/mike/porta_ordini.py:52` e
`Betfair/mike/certificazione.py:1476-1501` (`customerOrderRef` = `mike-t<id>`), `Betfair/mike/db.py:268-347` (`closes_trade_id`),
`migrations/mike_bot.sql:109`, `migrations/omega_cashout.sql:50`, `migrations/safe_strategy_bot.sql:73`,
`migrations/scalper_bot.sql:26`, `migrations/tennis_live.sql:56-58,73-76` (chiavi esterne). Nelle schede: A §1.7, C riga 73
(diario fsync prima di ogni `place_order`), G §4.3, I §4.2 riga 312, I §7, I righe 81 e 437, E4 riga 153, 02 righe 45, 249, 314,
07 riga 125. Ricerche con `grep` su 04/05/schede: «CambioGiorno» (0 in 05), «ora legale|DST|CEST» (0), «Windows Update» (0),
«Job Object» (1, I:437, «non verificato»).

---------------------------------------------------------------------------------------------------

## 1. Lista di controllo del brief

| Requisito | Esito prima | Dove nel piano | Lacuna (rilievo) | Esito dopo le correzioni |
|---|---|---|---|---|
| §6.1 `00_INVENTARIO.md` | COPERTO | 00 (2.165 righe) | contenuto non riverificato in questa revisione | COPERTO |
| §6.2 `01_FUNZIONALITA.md` | COPERTO | 01 (970 voci); 05 §4 e §9 (971 identificatori, 0 mancanti) | - | COPERTO |
| §6.3 `02_COMPETITOR.md` | COPERTO | 02, tabella di parita' | - | COPERTO |
| §6.4 `03_SCHEDE_COMPONENTI/` | COPERTO | 15 schede A..K | sette sezioni non riverificate qui | COPERTO |
| §6.5 04 (componenti, contratti, flussi, processi, dati, schemi) | COPERTO con lacune | 04 §2-§9 | intento non persistito prima dell'invio (R03); versione delle righe (R02, R05); dipendenze fra tabelle (R06); esiti sul canale che «salta il giro» (R07) | COPERTO |
| §6.6 05 (tappe, dipendenze, stime, rischi, cloud/PC, congelamento, «fatto») | PARZIALE | 05 §0-§9 | parallelismi su file condivisi (R17); dipendenza mancante T20/T21 -> T18 (R18); percorso critico senza T14 e T25, settimane sottostimate (R19); «fatto» di T13 non controllabile (R20) | COPERTO |
| §6.7 06 (non tecnico, decisioni esplicite) | PARZIALE | 06 §1-§8 | 06 §3 afferma una prova di spegnimento che 04 §6.1 dichiara NON fatta (R22); settimane da R19 | COPERTO |
| §9.1 una cartella, un contratto, `COSA_FA.md`, «tocco solo X» | COPERTO | 04 §2.2-2.4, §9 | - | COPERTO |
| §9.2 algoritmi del cloud uno per uno, tabelle, frequenza, latenza tollerata | PARZIALE | 04 §6.3 | «storico delle giornate» (brief §9.2) non inventariato; la latenza tollerata e' implicita nella colonna della cache | COPERTO (riga aggiunta in 04 §6.3) |
| §9.3 millisecondo, obiettivi numerici per tappa, scelta dell'archivio misurata e confrontata | PARZIALE | 04 §6.1, §7; 05 T0A, T6 | coda di `fsync` del diario nel percorso dell'ordine ignorata (R04: max 0,24-0,89 s); contesa del GIL mai misurata (R08); spegnimento, due file e checkpoint non provati (04 §6.1, gia' dichiarato); competitor: «n.d.» (dichiarato, 02 R-04) | PARZIALE: le misure mancanti sono ora tappe con «fatto» (T0A, T8); restano da fare, non da scrivere |
| §9.4 h24: cambio di giorno, regolamento notturno, riconciliazione, crash e riavvio, memoria, riconnessione `initialClk/clk`, sessione che scade, keep-alive, limiti API, 24 h con obiettivi | PARZIALE | 04 §4.5, §4.6, §5; 05 T0A, T3, T5, T19, T22, T24 | `CambioGiorno` senza tappa e ora legale assente (R10); «notte senza partite» incompatibile col tennis h24 (R11); obiettivi di 24 h di I §7 non riportati (R12); limite di transazioni/ora assente (R13); supervisore senza guardia a finestra chiusa e Job Object non deciso (R09); aggiornamenti di Windows e delle librerie (R14); scanner senza `initialClk` finche' U-07 (R15); rinnovo della sessione dello stream senza ricostruzione non verificato in flumine (05 T5 rischi, gia' dichiarato) | COPERTO a livello di piano; le misure di 24 h restano da eseguire (T0A) |
| §9.5 tabella per tabella: chi scrive oggi -> domani, ritardo massimo, verifica «non manca nulla» | PARZIALE | 04 §6.2; G §4.3 | le tabelle sono per FAMIGLIA (17 righe) contro 89 tabelle (00 §0); manca «chi scrive oggi»; T14-T17 «n/a»; G stessa scrive «proposta, da validare con l'utente» (G:270) (R23); duplicati nell'ombra di T8 (R21) | COPERTO come consegna di T2 (registro a 89 righe con test che rifiuta una tabella non registrata) + U-86 |
| §9.6 occhio critico, «verificato / non verificato» | COPERTO | 04 §1, §12; 05 §9 | - | COPERTO |
| §9.7 non superficiale | COPERTO per 04/05 | - | le schede non sono state ri-auditate qui | COPERTO |
| §0 guscio, nessuna funzionalita' persa, niente codice | COPERTO | 05 §0, §4 | regola 1 di 05 §0 contraddetta da T8, T13, T14 (R21) | COPERTO |
| §8 cosa NON fare (strategie, riscritture) | COPERTO | 05 §7 | - | COPERTO |

---------------------------------------------------------------------------------------------------

## 2. Rilievi, ordinati per gravita' (soldi > h24 > manutenzione)

Legenda «Applicata»: SI' = correzione scritta in 04/05/06 con la marca; DEC = portata all'utente come decisione `U-8x` in 05 §8.6.

### 2.1 SOLDI (8)

**R01 - ALTA. L'identita' del trade dipende dall'id del cloud, e T14 lo toglie senza dire con cosa.**
Fonte: `Betfair/mike/porta_ordini.py:52` e `certificazione.py:1476-1501` (`customerOrderRef` = `mike-t<id>` con l'`id` BIGINT di
`mike_trades`); `migrations/mike_bot.sql:109`, `omega_cashout.sql:50`, `safe_strategy_bot.sql:73` (`closes_trade_id BIGINT REFERENCES
*_trades(id)`); `mike/db.py:268-347` (P&L per posizione raggruppato su `closes_trade_id`/`id`). 05 T14 vuole «nessun `insert_trade`
sincrono con id dal cloud» con il solo prerequisito `trade_uid`: senza id locale cambiano la forma del ref (che la riconciliazione al
riavvio usa, 04 §4.5), la chiave esterna e la certificazione. Correzione: id BIGINT riservati a blocchi dal cloud quando c'e' rete
(hi-lo: ref, chiave esterna e P&L restano IDENTICI); a blocco esaurito e rete assente, il comportamento di oggi (nessuna apertura,
G §1.1). Alternativa: `trade_uid` + ref nuovo + migrazione + doppio formato in lettura per tutta la transizione. «Fatto» di T14
esteso: ref e `closes_trade_id` identici in cassetta. Applicata: SI' (05 T14, 04 §6.2) + DEC U-80.

**R02 - ALTA. L'ombra di T14 mette due scrittori sulle stesse chiavi del cloud.**
Fonte: 05 T14 «il postino scrive le STESSE righe sulle stesse chiavi»; 05 §0 regola 1 «in ombra ... non scrive righe»; lettori che
decidono sullo specchio del cloud: Omega fino a 20 s (04 §7 L8, `esiti_ordini_canale.py:1-12`). Un upsert del postino in ritardo
(ritento, offline) arriva DOPO la scrittura diretta e riporta indietro lo stato (es. da abbinato a in attesa): un bot che legge lo
specchio vede uno stato vecchio. Correzione: in ombra il postino scrive solo su tabelle d'ombra (`<tabella>_ombra`, stessa forma) e
`riconcilia` confronta; al passaggio a `nuovo` ogni upsert e' condizionato a una versione monotona per riga (`rev` intero, oppure
`updated_at` del produttore: `ON CONFLICT ... DO UPDATE ... WHERE excluded.rev > t.rev`), mai «ultimo che arriva vince».
Applicata: SI' (05 §0 regola 1, T14; 04 §3.7 campo `rev_colonna`, §4.4).

**R03 - ALTA. L'intento del bot decisore non e' scritto prima dell'invio.**
Fonte: 04 §4.1 passi 7-8 (DEC decide -> `RichiestaOrdine` sul canale; nessuna scrittura locale del bot prima); 04 §3.4 (`ref`
«deterministico dalla riga del bot», dedup Betfair di 60 s, 02 §3.4); 04 §4.5 (la ricostruzione guarda solo diario e conto). Se il
bot muore fra l'invio e il salvataggio del proprio stato, al riavvio non sa di aver chiesto l'ordine e puo' decidere di nuovo: il dedup
del motore lo ferma SOLO se il ref nasce da una riga gia' durevole. Correzione: regola «prima la riga, poi l'invio»: il bot scrive la
riga del trade con il ref in `stato_denaro` (FULL) e SOLO dopo invia; al riavvio ogni ref senza `EventoOrdine` si chiede a
`PortaOrdini.stato(ref)` prima di qualunque decisione nuova. Prova: uccidere il bot fra scrittura e invio e fra invio e risposta ->
0 ordini doppi. Applicata: SI' (04 §4.1 nota, §4.5; 05 T14 «fatto quando»).

**R04 - ALTA (millisecondo). La coda di `fsync` del diario sta nel percorso dell'ordine e nessun obiettivo la conta.**
Fonte: C riga 73 («Diario write-ahead su disco con flush+fsync PRIMA di ogni `place_order`», `motore_ordini.py:183-254`, `:1424`);
misura di laboratorio di 04 §6.1 / 07 §6: «log write+flush+fsync» p99 9,7-37 ms, max 0,24-0,89 s (contro SQLite WAL FULL max
67-180 ms). 04 §7 L6 fissa «p50 < 150 ms» senza p99 e senza la quota del diario. Correzione: in T0A la marca del tempo del diario
(prima/dopo `fsync`) dentro L6 con p50/p99/max sul disco vero; obiettivo p99 dichiarato dopo la misura; se la coda e' quella del
laboratorio, la scelta fra JSONL+fsync di oggi e diario in `stato_denaro` va all'utente (non e' strategia, ma e' il percorso dei
soldi). Applicata: SI' (04 §7 riga L6b; 05 T0A) + DEC U-81.

**R05 - MEDIA-ALTA. Split-brain della configurazione: il backstop dal cloud puo' annullare un comando locale appena dato.**
Fonte: 04 §4.3 (autorita' locale, mirror verso il cloud «entro 1 s per CFG/CMD», backstop 1/s che importa dal cloud); 04 §6.2 T09-T11
(control: CACHE + sveglia). Sequenza: l'utente ferma un bot dalla UI (locale), il mirror non e' ancora partito, il backstop legge dal
cloud il valore vecchio e lo «importa e smista come un comando locale» (04 §4.3, ultimo passo): il bot riparte. Correzione: ogni riga
CFG/CMD ha `rev` monotono e `origine` (`pc` | `remoto`); il backstop importa SOLO righe con `origine=remoto` e `rev` maggiore di
quello locale; test falsificato (backstop senza il filtro -> rosso). Applicata: SI' (04 §4.3; 05 T22).

**R06 - MEDIA. Il postino ignora le chiavi esterne fra tabelle scritte da processi diversi.**
Fonte: `migrations/scalper_bot.sql:26` (`scalper_*.event_id REFERENCES live_follow`), `tennis_live.sql:56-58,73-76`
(`tennis_live_now`/`tennis_live_ladder` -> `tennis_live_follow` `ON DELETE CASCADE`), `closes_trade_id` (R01). `live_follow` lo scrive
il nucleo Betfair nel runner (04 §6.2 T07), `scalper_*` il servizio dello scalper (T12): l'ordine per `seq` vale dentro UN processo.
Un figlio che arriva prima del padre da' 23503, che con la classificazione di 04 §4.4 («errore NON transitorio -> dead_letter») finisce
fra i morti. Correzione: `SpecTabella.dipende_da`; 23503 trattato come transitorio con tetto (poi dead_letter con allarme); nessuna
`delete` coalescata su una tabella padre con `CASCADE` senza la sua sequenza. Applicata: SI' (04 §3.7, §4.4; 05 T8).

**R07 - MEDIA. Gli esiti degli ordini passano da un canale che per costruzione «salta il giro».**
Fonte: `local_channel.py:630-672` («Il giro si salta - non si accumula - perche' qui passa uno STATO COMPLETO ... Per un flusso
DIFFERENZIALE questa disciplina non andrebbe bene»), tetto `_MAX_INVII_IN_VOLO = 64` (`:176`); 04 §3.11 mette `EventoOrdine` sul
canale. Il motore ha gia' `seq` per attore e `da_seq` (`motore_ordini.py:913,961-962,2245`), ma il piano non obbliga il consumatore
a rilevare il buco. Correzione: ogni consumatore di `EventoOrdine` controlla la contiguita' di `seq` e al buco chiede `da_seq`; test
falsificato (un push scartato di proposito -> il bot recupera; senza il controllo -> rosso). T6 (ladder a ogni cambio) aumenta i push
sullo stesso server: misurare `saltati_client` in ombra. Applicata: SI' (04 §3.11; 05 T10).

**R08 - MEDIA. Contesa del GIL nel runner che ospita stream, motore di tutti i bot, ladder, scrittore e postino: mai misurata.**
Fonte: E4 riga 153 («Interferenza con la strategia (GIL, parsing JSON di Supabase): non misurata»); 07 riga 125 (canale misurato
«senza GIL contesa»: limite inferiore); 04 §4.1 (il motore ordini dei bot decisori vive nel runner calcio); 04 §6.1 («il ciclo paga
solo l'accodamento ~15 us»: misura su un thread solo); `json.dumps` 167 us p50 (07 2b) per ogni push del ladder. Correzione: in T8 una
prova di carico sul replay a cadenza reale con postino e scrittore accesi contro spenti: L2 e L6 p99 non peggiori oltre la variabilita'
fra due esecuzioni identiche; se peggiori, decisione U-82 (drenaggio rallentato o processo separato, che richiede permesso).
Applicata: SI' (04 §6.1; 05 T8) + DEC U-82.

### 2.2 H24 (8)

**R09 - ALTA. Chi sorveglia il supervisore a finestra chiusa, e cosa fa il Job Object quando il supervisore muore.**
Fonte: I riga 312 («sorvegliato ... Electron lo rilancia se esce e Windows lo avvia al login»); U-61 (finestra chiudibile senza
spegnere i servizi); 05 T22 «nessun orfano (Job Object)»; I riga 437 (Job Object «non verificato su fonte pubblica»); I riga 81 (oggi
orfani con lo stesso `APP_BOOT_ID` e lock di porta occupati). Con la finestra chiusa nessuno rilancia il supervisore fino al login
successivo; con un Job Object a chiusura che uccide i figli, un crash del supervisore abbatte INSIEME i runner con posizioni aperte.
Le due scelte sono opposte e nessuna e' scritta. Correzione: decisione esplicita (proposta: nessuna uccisione alla chiusura + adozione
dei figli vivi al riavvio tramite lock e pid + terzo livello dall'Utilita' di pianificazione con ripetizione ogni minuto). Applicata:
SI' (04 §5.1; 05 T22) + DEC U-83.

**R10 - MEDIA. `CambioGiorno` non ha una tappa e l'ora legale non compare da nessuna parte.**
Fonte: 04 §3.11 e §4.6 (`CambioGiorno` dal supervisore); `grep CambioGiorno` in 05 = 0; `grep "ora legale|DST|CEST"` in 04, 05,
schede, 02, 07 = 0. La giornata e' Europe/Rome (04 §4.6, F D3); la prossima fine dell'ora legale e' domenica 25/10/2026 (ultima
domenica di ottobre, direttiva 2000/84/CE), dentro la migrazione: un giorno di 25 ore (e il 28/03/2027 di 23). Correzione:
`CambioGiorno` in T13 (contabilita', con un temporizzatore proprio) e consegnato dal supervisore in T22; test di `giornata()` sui due
giorni di cambio con partite a cavallo dell'ora ripetuta. Applicata: SI' (05 T13, T22).

**R11 - MEDIA. «Notte senza partite» e «ricambio solo se flat» possono non verificarsi mai con il tennis h24.**
Fonte: 04 §4.6 (A6 ricambio ogni 18 h «SOLO se flat», A7 «notte senza partite: regolamento notturno»); brief §9.4 («monitorare
costantemente sia calcio che tennis»); il motore dei bot decisori vive nel runner calcio (04 §4.1), quindi «flat» del runner calcio =
nessuna posizione calcio di NESSUN bot. Se la finestra non arriva, il ricambio non avviene e la memoria e' l'unica guardia (R12).
Correzione: regolamento a giro continuo (listClearedOrders ogni N ore, indipendente dalle posizioni); ricambio con eta' massima e
allarme se non flat oltre la soglia. Applicata: SI' (04 §4.6).

**R12 - MEDIA. Gli obiettivi numerici di 24 h esistono nella scheda I ma non entrano in 04 ne' nel «fatto» di 05.**
Fonte: I §7 (CPU <= 100% di un core mediano, nessun servizio > 30% p95 a riposo; RAM: crescita <= 5% fra 2a e 24a ora, totale <= 25%
di 15,8 GB; log <= 50 MB/giorno; re-login <= 1 per servizio ogni 12 h; riavvii non pianificati 0; orologio <= 100 ms: «target
provvisorio»); 04 §7 non ha righe di risorse; 05 §0 criterio (e) «uguale o migliore». Correzione: righe L15-L19 in 04 §7 (provvisorie,
confermate dopo la baseline di T0A). Applicata: SI' (04 §7).

**R13 - MEDIA. Manca il limite di transazioni per ora fra i limiti API.**
Fonte: 02 riga 45 (Bet Angel: «il limite orario e' fissato da Betfair, oltre si paga»), riga 249 (flumine `MaxTransactionCount`), riga
314 (P-13: tetto 1000/ora in `config_stream.py:256-262`, non in UI); C riga 417 (`_max_orders_per_min` per bot). 04 §5.2 elenca login,
keepAlive e concorrenza ma non il tetto orario. Con UNA porta per tutti i bot il contatore deve essere uno per conto, nella porta.
Applicata: SI' (04 §5.2; 05 T10).

**R14 - MEDIA. Aggiornamenti di Windows e delle librerie: assenti.**
Fonte: `grep "Windows Update"` in 04/05/schede = 0; 05 T0C fissa le versioni solo nel manifesto (`pip freeze` «da produrre») e T26
e' l'unico aggiornamento previsto. Un riavvio forzato di Windows ferma l'h24 con posizioni aperte; un aggiornamento di libreria
durante la migrazione cambia il metro (R1 di 05 §6). Correzione: blocco delle versioni (Python, pacchetti con hash, Electron, Node)
dal congelamento a T26; orario attivo/rinvio dei riavvii di Windows con controllo nella «Salute». Applicata: SI' (05 T0A, §6) + DEC U-84.

**R15 - BASSA. La ripresa `initialClk/clk` dello scanner dipende da una decisione.**
Fonte: A §1.7 (lo scanner ricostruisce l'immagine piena, `safe_strategy/stream.py:418-427`); U-07 «se non decide: scanner con il suo
pool». Brief §9.4 chiede la riconnessione come requisito. A riga 625 dichiara che l'unificazione «non cambia nessuna strategia». Nessuna
correzione nel testo: si segnala all'utente che senza U-07 il requisito §9.4 resta parziale per lo scanner. Applicata: no (gia' U-07).

**R16 - BASSA. Accendere la sincronizzazione dell'ora fa saltare l'orologio di ~0,84 s all'indietro.**
Fonte: 07 1e (+844 ms, w32time fermo); U-62. Un salto all'indietro dell'ora di parete tocca ogni durata calcolata con l'ora di parete
(dedup 60 s, ripieghi a 20 s). Correzione: farlo con l'app ferma o tutti i bot flat. Applicata: SI' (05 T0A, nota).

### 2.3 MANUTENZIONE E PIANO (8)

**R17 - MEDIA. Due coppie di tappe «parallele» toccano gli stessi file (viola 05 §0 regola 3).**
Fonte: 05 §3 («T13 con T12 (file diversi)», «T6 con T7/T8»); T12 tocca `omega_service.py:1-1137, 7752-8936` e rompe il ciclo
`execution.py` <-> `omega_service.py`; T13 tocca `omega_service.py:4971-5424` e `safe_strategy/execution.py:2686-3100`; T6 tocca
`stream/db.py:650-710`, T8 `stream/db.py:644,697,988` (697 dentro 650-710). Applicata: SI' (05 §3).

**R18 - MEDIA. T18 genera i manifesti di scalper e tennis prima che esistano i loro cataloghi.**
Fonte: 05 T18 voci `E4-080..E4-083`, `E5-103..E5-105`, `E5-110..E5-118`, file `ScalperPanel`, `TennisBotServiceParamsSheet`; il
catalogo dello scalper nasce in T20 (E4 §6), `catalogo_parametri.json` del tennis in T21. Correzione: T18 in due passi, il secondo
dopo T20 e T21 (archi T20 -> T18b, T21 -> T18b); nessuna voce spostata (restano assegnate a T18 in 05 §4). Applicata: SI' (05 §3).

**R19 - MEDIA. Il percorso critico salta T14 e T25: le settimane sono sottostimate.**
Fonte: grafo di 05 §3 (T12 -> T14 -> T15; T24 -> T25 -> T26) contro il percorso scritto (T12 -> T15, T24 -> T26). Ricalcolo con le
stime di 05 §5: T0 (max(T0A, T0B) 2-3 + T0C 3-4 = 5-7) + T5 3-4 + T10 3-4 + T11 4-5 + T12 7-9 + T14 5-6 + T15 4-5 + T17 7-9 + T19 7-9
+ T20 5-6 + T21 5-6 + T23 7-9 + T24 4-5 + T25 2-3 + T26 4-6 = **72-93 giorni** (la somma delle sole tappe elencate in 05 dava gia'
65-84, non 61-80) = 14,4-18,6 settimane di lavoro, piu' le ombre sul percorso (T11 N giornate, T12 2-3 giorni, T14 5 notti, T15 1
giornata): **circa 16-20 settimane**. Il sottoinsieme «fasi 0-1-2 del 02/10» non era chiuso per dipendenze (mancano T5, richiesta da
T10, e T9, richiesta da T12): con T5 e T9 il suo percorso critico e' T0-T5-T10-T11-T12-T14-T15-T17-T24 = **42-54 giorni** + ombre =
**circa 10-12 settimane**, non 8-10. Applicata: SI' (05 §3, §5; 06 §6).

**R20 - MEDIA. Il «fatto» di T13 richiede 5 giornate LIVE, che dipendono da te.**
Fonte: 05 T13 («5 giornate live consecutive a zero differenze»); i bot li accende solo l'utente (`CLAUDE.md`); T13 -> T15 nel grafo.
Senza giornate live T13 non chiude e blocca T15 e tutto cio' che segue. Correzione: decisione U-85 (alternativa: giornate con
regolamenti reali anche manuali, Fonte `manuale_sito`/`manuale_app` di 04 §3.6, + replay). Applicata: DEC U-85.

**R21 - BASSA. La regola «in ombra non scrive righe» e' contraddetta da T8, T13, T14; l'ombra di T8 duplica i log.**
Fonte: 05 §0 regola 1 contro T8 («il postino scrive su una tabella d'ombra o con `uid` e `ON CONFLICT DO NOTHING`»), T13 (chiave
JSONB `pnl_reale_oggi_ombra`), T14 (R02). La seconda via di T8 scrive nella tabella VERA una riga in piu' per evento (la insert
vecchia non ha lo stesso `uid`): il confronto «+/- 0» di T8 fallirebbe per costruzione e l'archivio avrebbe doppioni. Correzione:
regola 1 rettificata (solo tabelle o chiavi d'ombra), in T8 solo la tabella d'ombra. Applicata: SI' (05 §0, T8).

**R22 - BASSA. 06 §3 afferma una prova che non e' stata fatta.**
Fonte: 06 §3 («0,6 ms per una scrittura che sopravvive allo spegnimento», «senza perdere niente») contro 04 §6.1 («Non provati:
spegnimento del PC»; durabilita' di FULL «per documentazione»; i log JSONL write+flush allo spegnimento «non garantito»).
Applicata: SI' (06 §3).

**R23 - BASSA. §9.5 e' risolto per famiglia, non per tabella, e i ritardi sono proposte.**
Fonte: 04 §6.2 e G §4.3 (17 famiglie; G:270 «Ritardo max cloud (proposta, da validare con l'utente)»); 89 tabelle toccate (00 §0);
colonna «chi scrive oggi» assente; T14-T17 «n/a». Correzione: consegna di T2 = registro `SpecTabella` con UNA riga per ciascuna delle
89 tabelle (scrittore oggi, scrittore domani, regime, ritardo, verifica), con test che rifiuta una tabella scritta dal codice e non
registrata (come il test di contratto del registro dei bot). Applicata: SI' (05 T2; 04 §6.2 nota) + DEC U-86.

**R24 - BASSA. Il confronto delle opzioni di archivio e' misurato su tre tecniche; mancano tre prove dichiarate.**
Fonte: 04 §6.1 (memoria, log con/senza fsync, SQLite NORMAL/FULL/lotti; «Non provati: spegnimento, checkpoint fuori dal percorso,
due file»); 02 R-04 (competitor: n.d.). La scelta e' difendibile con i numeri presenti; le tre prove mancanti piu' la prova sotto
carico (R08) diventano «fatto» di T8/T14 (U-55 gia' copre i due file). Applicata: SI' (05 T8).

### 2.4 Affermazioni senza fonte

Nessuna affermazione numerica senza fonte trovata in 04 e 05 sui punti campionati. Due affermazioni assolute non reggono contro la
fonte che esse stesse citano: 06 §3 (R22) e 04 §5.1 «sorvegliato a sua volta da Electron» quando U-61 rende la finestra chiudibile (R09).

---------------------------------------------------------------------------------------------------

## 3. Correzioni applicate (dove)

- **04**: §3.7 (`SpecTabella.rev_colonna`, `dipende_da`; regole di versione e chiavi esterne: R02, R06); §3.11 (esiti con controllo di
  `seq`: R07); §4.1 (prima la riga, poi l'invio: R03); §4.3 (`rev` + `origine` nel backstop: R05); §4.4 (23503 transitorio con tetto:
  R06); §4.5 (ref senza esito interrogati prima di decidere: R03); §4.6 (regolamento continuo, eta' massima del ricambio, ora legale:
  R10, R11); §5.1 (guardia del supervisore e Job Object: R09); §5.2 (transazioni/ora: R13); §6.1 (prova sotto carico del GIL: R08);
  §6.2 (identita' dei trade, registro per tabella: R01, R23); §6.3 (riga «storico delle giornate»: §9.2); §7 (L6b diario, L15-L19
  risorse di 24 h: R04, R12).
- **05**: §0 regola 1 (R21); T2 (R23); T0A (R04, R14, R16); T8 (R06, R08, R21, R24); T10 (R07, R13); T13 (R10, R20); T14 (R01, R02, R03);
  T22 (R05, R09, R10); §3 (R17, R18, R19); §5 (R19); §6 righe R15-R20; §8.6 decisioni U-80..U-86.
- **06**: §3 (R22); §6 (R19); §7 (U-80, U-83, U-84, U-85).

## 4. Cosa NON ho potuto verificare

- Il comportamento reale di `fsync`, del GIL e del canale sotto carico: sono misure da fare (T0A, T8), qui sono rischi con fonte.
- Che il cloud permetta di riservare blocchi di id dalle sequenze di `*_trades` senza migrazione (R01: la proposta va provata con il
  coordinatore PC sul DB, in sola lettura prima).
- Il comportamento del Job Object di Windows e dell'Utilita' di pianificazione (R09): nessuna ricerca web in questa sessione.
- Le schede (03) e gli inventari (00, 01) non sono stati ri-auditati riga per riga: questa revisione verifica il piano contro il
  brief, campionando il codice sui soli rilievi.
