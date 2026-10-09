# AVANZAMENTO DELLA MIGRAZIONE — punto d'ingresso unico (aperto il 09/10/2026)

Ordine dell'utente (09/10): «tutte si, parti tu con quello che puoi fare; aggiorna il documento che siamo partiti con la fase 0,
non voglio ripetere le cose 100 volte: ad ogni sessione andremo avanti».

**Regola per ogni sessione (cloud o PC)**: si legge QUESTO file per primo (poi l'ultima sezione di `CRONOSTORIA.md`), si riparte
dalla prima riga «da fare» della tabella delle tappe, e a fine lavoro si aggiorna la tabella e il registro qui sotto. Il piano non
si rimette in discussione: le tappe, le regole (§0) e le decisioni sono in `05_PIANO_DI_MIGRAZIONE.md`; il riassunto per l'utente
in `06_RIEPILOGO_PER_L_UTENTE.md`. Le decisioni gia' prese NON si richiedono all'utente.

## Regola dei rami e dell'ingresso su master (decisione dell'utente, 09/10 — VALE PER OGNI SESSIONE)

1. L'architettura vive SOLO sul ramo `claude/architettura-tappa0` (poi un ramo per tappa, nominato in questa tabella). Mai
   mescolata con altre funzionalita' (pagine, correzioni ai bot): quelle vanno su rami loro.
2. Una tappa alla volta: il cloud la costruisce e certifica (test, replay, falsificazione), il PC la verifica di persona e firma.
3. Solo DOPO la firma e SOLO con l'ok esplicito dell'utente, QUELLA tappa entra su master con l'interruttore su «vecchio»
   (l'app funziona identica; il codice nuovo c'e' ma e' spento). Mai la punta del ramo senza controllo di cosa contiene.
4. Poi «ombra» sulle giornate vere (il nuovo calcola e confronta, non manda ordini), poi «nuovo» solo su decisione dell'utente;
   ritorno a «vecchio» con l'interruttore.
5. Dopo ogni ingresso su master il ramo dell'architettura riparte da master aggiornato per la tappa successiva.
6. Alla fine nessuna fusione gigante: il codice definitivo e' gia' su master tappa per tappa; resta solo da archiviare il vecchio.

## PRIORITA' DELL'UTENTE (09/10): prima TUTTA la parte Betfair, con il DB locale

«Sistemare il prima possibile tutta la parte Betfair (con il DB locale) e lasciare il cloud alle operazioni che fa gia'; il resto
del codice si sistema dopo. Almeno cosi' posso operare una volta finito.» L'ordine delle tappe segue il grafo di 05 §3:

1. T0 (metro) — obbligatoria, in corso.
2. TRAGUARDO 1 «operare a mano come i competitor» (~4-5 settimane dopo T0): T5 sessione e REST -> T6 ladder a ogni cambio ->
   T10 contratto e porta degli ordini -> T11 riconciliatore in ombra + stream degli ordini del CONTO (senza filtro, sola lettura)
   che alimenta il ladder di Trading con TUTTI gli ordini (tuoi, bot, sito), etichetta di chi li ha fatti, abbinato, prezzo medio,
   P&L di mercato.
3. TRAGUARDO 2 «tutto Betfair nell'app, nessun DB nel percorso» (totale ~12-15 settimane): T2 -> T8 archivio locale e postino;
   T7 algoritmi del cloud letti prima (mai nel percorso dell'ordine); T9 stato partita; T12 runtime + pilota Omega; T14 stato del
   denaro in locale + postino; T15 Mike (paper); T4 + T17 Safe e scanner; T19 gestore dei flussi; T20 scalper calcio; T21 tennis.
   T16 (Mike live dalla porta) solo su ordine dell'utente.
4. DOPO: T1, T3, T13, T18, T22-T26 (pulizia, contabilita' unica, UI dai manifesti, supervisore, banco unico, flumine 3).
Il cloud resta com'e' (algoritmi, analisi pre-partita, archivio di tutto): nessuna tappa cambia cio' che il cloud calcola.

## ONDATA 1 — costruzione dei comparti del modulo Betfair (avviata il 09/10)

Regola: codice NUOVO solo sotto `Betfair/nucleo/`, nessun file esistente toccato, niente agganciato all'app; parita' col codice di oggi
provata da test; aggancio = ondata 2 (dopo la tappa 0, una tappa alla volta, interruttore spento, firma del PC, si' dell'utente).
«Niente andra' su master finche' non siamo certi che funzioni allo stesso modo O MEGLIO» (utente, 09/10).
Contratti fissi e brief comune: `559a96df` (`Betfair/nucleo/*/contratto.py`, `ondata1/BRIEF_COMUNE_ONDATA1.md`).

| ID | Comparto | Ramo | Stato |
|---|---|---|---|
| W1-A1 | sessione unica e REST (T5) | `architettura/w1-a1` | in costruzione |
| W1-A2 | stream ordini del CONTO, ladder a ogni cambio, profili, gestore stream (T6, T19, T11 parte A) | `architettura/w1-a2` | in costruzione |
| W1-C1 | porta ordini: adattatore, minimi .it unici, controlli, seq/da_seq, porta (T10) | `architettura/w1-c1` | in costruzione |
| W1-C2 | libro ordini del conto con autore, P&L di mercato, riconciliazione in ombra (T11) | `architettura/w1-c2` | in costruzione |
| W1-G1 | archivio locale invisibile, postino, riconcilia, migrazione uid/ombra (T8, T14 base) | `architettura/w1-g1` | in costruzione |
| W1-G2 | registro delle tabelle, client cloud unico, cache degli algoritmi (T2, T7) | `architettura/w1-g2` | in costruzione |
| W1-B | stato della partita (T9) | `architettura/w1-b` | in costruzione |

Dopo ogni consegna: verifica del coordinatore (diff, test, mutazioni proprie) + revisore indipendente (Sonnet), poi il ramo entra
nel ramo dell'architettura. Ondata 2 (aggancio, ombra, replay sul PC) solo dopo la tappa 0 chiusa.

## Obiettivo (parole dell'utente, 09/10)

- Tutto cio' che e' Betfair vive nell'app desktop, «esattamente come i competitor»: nessun database nel percorso
  Betfair -> decisione -> ordine; stato vivo in memoria + archivio locale (SQLite) per i soldi; postino verso il cloud.
- Il database cloud serve solo agli algoritmi, alle analisi pre-partita e ad archiviare tutto.
- La UI resta questa; cambia cio' che c'e' dietro. Nessuna funzionalita' persa (le 970 voci di `01_FUNZIONALITA.md`).
- Metodo: stessa repo, cartelle nuove (`Betfair/nucleo/`, `Betfair/bots/`), un pezzo alla volta, prima in ombra accanto al
  vecchio, interruttore e ritorno; il cervello dei bot non si tocca (impronta della strategia = 0 differenze).
- Ogni funzionalita' o bot NUOVO si costruisce solo nella struttura nuova.
- Priorita' dell'utente dentro il piano: il ladder di Trading «come un tool professionale» (tutti gli ordini del conto, di chiunque,
  con P&L completo): arriva con la porta unica degli ordini (T10-T11) via stream ordini del conto in sola lettura.

## Decisioni dell'utente

| Data | Decisione | Esito |
|---|---|---|
| 09/10 | Le 7 che bloccano la tappa 0 (05 §8.1): U-62 ora di Windows + PC sveglio + avvio al login; U-32 finto di Omega corretto prima del congelamento; U-27 baseline di Mike e registrazioni COMPLETE aggiuntive; U-44 3-5 partite tennis nel repo; U-37 commit dei 4 documenti; U-59 le sole 3 tolleranze dell'ombra; U-60 misurare i 120 ms | **TUTTE SI'** (U-60: misurarli) |

Le altre 79 decisioni (05 §8.2-8.6) si portano all'utente solo quando la tappa che le richiede sta per partire.

## Tappe

Stato: `da fare` · `in corso (chi)` · `in verifica PC` · `fatta (commit, data)`.

| Tappa | Contenuto | Chi | Stato |
|---|---|---|---|
| T0A | Modulo «Salute» + misure mancanti + referto 24 h | cloud (codice) + PC (migrazione `monitor_metrics`, 24 h app accesa) | parte cloud fatta (`e44032a9`, `6d02e578`, `bd9e37cc`, 09/10); **verificata e FIRMATA dal PC** (09/10, `tappa0/VERIFICA_PC_2026-10-09/`): additiva sotto `MONITOR_SALUTE`, Mike/Safe identici, suite verde; ramo `tappa0-salute-su-master` pronto (solo i 67 file di T0A su `979aac18`, pytest 11.533/0, build ok). **SU MASTER SPENTA** (`cf5236f9`, 09/10 23:20, con R-4/R-5/R-6/R-9 chiusi dal cloud in f9084b4c). Poi: migrazione (utente), `MONITOR_SALUTE=1` + build, 24 h, 30 ordini paper, referto (§5) |
| T0B (1)-(3) | Cantieri 15, 11, 7 del banco | cloud | fatta (fusi su master entro il 09/10, `CRONOSTORIA.md` 08/10) |
| T0B (4) | Finto di Omega con la firma del vero (`aggregates(..., mode)`), referto prima/dopo | cloud | fatta (`07115d13`, 09/10; referto `tappa0/T0B4_FINTO_OMEGA/`); **FIRMATA dal PC** (09/10: firme identiche al vero, 28/28, mutazione rossa) |
| T0B (5) | 3-5 partite tennis in `registrazioni_banco/` (U-44) + registrazioni calcio COMPLETE aggiuntive per Mike (U-27) | PC | fatta (`695a62cd`, 09/10): tennis in `registrazioni_banco/tennis/<giorno>/<id>/` (albero del recorder, `TENNIS_RECORD_DIR`): 35790089, 35794049 (COMPLETE), 35795993 (PARTIAL 65,7%), 35797566 senza raw del Match Odds (inutilizzabile, dichiarato); calcio per Mike 35777617, 35768365, 35774000 (stati D11: seconda entrata e re-ingresso; scoperti PRE_LAST_ENTRY_PENDING, SKIPPED, ERROR); sha256 verificati dal coordinatore; fixture della barra di Match Replay generate per le 3 calcio (`6247fbd0`, standard del 07/10: ogni calcio in `registrazioni_banco/` ha la sua fixture); referto `tappa0/T0B5_REGISTRAZIONI/`. Reperti: `validate_recordings` da' COMPLETE 100% a 36006953 ferma al 44'; il feed ri-emette le righe-evento dopo una riconnessione (35774000, gol del 16' ripetuto 6 minuti dopo): il verificatore le dedupe, il test ora conta come lui |
| T0B (6) | Commit dei 4 documenti (U-37) + testo della Base allineato al 25/09 | PC | 4 documenti versionati byte per byte (`143a60d6`, 09/10); allineamento della Base (quota di banca 20-34, Q1 del 25/09) approvato dall'utente sul diff e committato (`7c92904c`) |
| U-62 | Ora di Windows, niente sospensione, avvio al login (app spenta o bot flat) | PC + utente | fatta (PC, 09/10 18:05, app spenta): w32time Automatico/Running su time.windows.com, risincronizzato (scarto residuo -0,16 s su 5 campioni); sospensione/ibernazione a rete mai; riavvio automatico di Windows Update bloccato con utente connesso (`NoAutoRebootWithLoggedOnUsers=1`, ore attive 6-24); avvio al login = collegamento nella cartella Esecuzione automatica dell'utente all'avviatore esistente `desktop/release/AlphaScore Trading 1.1.0.exe` (attivita' pianificata rifiutata senza amministratore). Niente ricompilato |
| U-60 | Misura dei 120 ms delle letture REST del banco | PC | misurata (`e7eee8bd`, 09/10, app spenta): letture DB a connessione viva p50 111 / p90 148 / p99 493 ms, a connessione nuova p50 228 ms; non misurate le letture verso Betfair. Decisione sul valore: utente (proposta: 120 ms confermati con incertezza 110-150) |
| T0C strumenti | Cassetta, ombra (`--ombra`), `TOLLERANZE.md`, `congela`, determinismo, impronte | cloud | fatta (`cd41b2f1`, 09/10; referto `tappa0/T0C_STRUMENTI/`); **FIRMATA dal PC** (09/10: senza flag = corpo di prima, 39 verdi, mutazione rossa); R-3 (lista della tolleranza 3 non bloccata dai test) da chiudere nel cloud PRIMA del congelamento |
| T0C congelamento | Baseline (due giri ciascuna) e `MANIFEST.json` | PC (sulla macchina dell'ombra) | da fare: dopo T0B (5)-(6), U-62, U-60 e le decisioni tecniche qui sotto; comandi in `tappa0/T0C_STRUMENTI/REFERTO.md` §10 |
| T1..T26 | Come in 05 §2 | | da fare |

## Registro (una riga per evento, la piu' recente in fondo)

- 09/10 — Utente: tutte e 7 le decisioni della tappa 0 = si'. Aperto questo file. Cloud (sessione `claude/sweet-hypatia-t4bmna`)
  avvia in parallelo T0A (modulo Salute), T0B (4) (finto di Omega) e T0C (solo strumenti: cassetta, ombra, tolleranze, congela,
  con prova di innocuita', falsificazione e determinismo; nessuna baseline congelata finche' T0B non e' completa).
  Al PC: U-62, U-60, T0B (5)-(6) (testo nella conversazione e nel blocco del 09/10 di `CRONOSTORIA.md`).

- 09/10 — T0B (4) FATTA e verificata dal coordinatore cloud (`07115d13`): solo il finto del banco
  (`Betfair/omega/tools/replay_registrazioni.py`), firma identica al vero; CRITICAL «paper e live SOMMATI» 22 -> 0 righe sulla
  35760084 (24 -> 0 sulla 35797769), stderr altrimenti identico, esiti 22/22 invariati su entrambe; test nuovo 28 rossi prima /
  28 verdi dopo, mutazione del coordinatore rossa (16); suite 11.503 verdi. Reperti aperti per l'utente: R1 (nessuno scenario di
  Omega mescola paper e live: proposta di uno scenario «modalita-mista» PRIMA del congelamento), R2 (`omega 35797769 --scenari
  tutti --worker 3` 1033-1466 s, sopra il tetto dei 600 s, su macchina condivisa), R3 (altri finti di Omega nei test unitari senza
  `mode`, 12 chiavi contro 19), R4 (parita' della RPC `get_omega_aggregates_modalita` da verificare sul PC col DB in sola lettura).

- 09/10 — T0C strumenti FATTA e verificata dal coordinatore cloud (`cd41b2f1`): additivita' e innocuita' 4/4 (Mike, Omega, Safe,
  scalper `base`), falsificazione dell'ombra 10/10, test 39 verdi e mutazione del coordinatore rossa (13), impronte di Omega/Safe/
  scalper/tennis (0 differenze, falsificazione 16/16). Determinismo: Mike, Omega, Safe 0 divergenze; SCALPER 3 divergenze (pid in una
  riga di log, `scalper_session.py:1590`).
- 09/10 — T0A parte cloud FATTA e verificata dal coordinatore cloud: `Betfair/monitor/`, migrazione `monitor_metrics_2026-10-09.sql`
  (NON applicata), pagina `/salute`, agganci additivi sotto `MONITOR_SALUTE` (di serie 0) in 19 file; banco identico (Mike `base`,
  Safe `rapidi`); mutazioni del coordinatore rosse (monitor sempre acceso: 7; diario non scritto: 6). Volume stimato ~29.000 righe
  al giorno (30-55 MB) in `monitor_metrics`: conservazione da decidere (utente).
- 09/10 — Cima integrata del ramo cloud: pytest Betfair 11.571 verdi / 0 rossi; vitest 5551 verdi; tsc 0; build ok.
- 09/10 — DECISIONI TECNICHE DEL COORDINATORE (nel perimetro delle decisioni dell'utente, da applicare prima del congelamento):
  (a) R2 scalper: il banco DICHIARA un pid fisso nel replay dello scalper (nessuna tolleranza in piu': restano le 3 di U-59);
  (b) R1 Mike (diradamento dei log a orologio di macchina, `mike/service.py:5739`) + R3 (percorsi assoluti e riga dei worker nel
  referto): le cassette di riferimento si congelano e si confrontano SULLA STESSA MACCHINA (il PC, dove gira l'ombra); il cloud
  per le sue verifiche usa una baseline propria dallo stesso commit; (c) R4 sha256 delle `.timeline.jsonl`: si calcolano sui byte
  del repo (`git show`), mai sulla copia di lavoro con `autocrlf`; (d) R5: Omega e Safe si congelano su `tutti`; (e) R6: cassette
  `tutti` nel repo COMPRESSE (~0,4-0,8 MB ciascuna).
- 09/10 — DECISE dal coordinatore su delega esplicita dell'utente («devi dirmi tu la soluzione migliore»): (1) scenario
  «modalita-mista» di Omega SI', aggiunto dal cloud PRIMA del congelamento (solo banco, strategia intatta); (2) `monitor_metrics`:
  7 giorni nel DB (pulizia con la RPC `monitor_metrics_pulizia`), copia completa sul PC in `_logs/monitor/`; (3) la misura di 24 h
  di T0A si fa DOPO che il PC ha verificato e firmato T0A e l'utente ha detto si' al suo ingresso su master con
  `MONITOR_SALUTE=0` (regola dei rami, punto 3): niente copie parallele dell'app; (4) congelamento di T0C dopo B1-B5 del PC e la
  firma delle tre consegne del cloud.

- 09/10 — Separazione dei rami (ordine dell'utente: «l'architettura e' un argomento a se'»): tutto il lavoro della tappa 0 e'
  sul ramo `claude/architettura-tappa0` (cima `66c19c7d` prima di questa riga). Su master va SOLO `a7cf9fdd` del ramo
  `claude/sweet-hypatia-t4bmna` (Programma del giorno + Control Room). Regola dei rami scritta in testa a questo file.

- 09/10 (PC, 18:05-18:20) - U-62 FATTA ad app spenta (vedi tabella); T0B (6): 4 documenti versionati (`143a60d6`), diff della Base mostrato all'utente. B2 (registrazioni), B4 (misura REST U-60) e B5 (verifica PC di T0A/T0B4/T0C) in corso con tre delegati; esiti nelle righe seguenti.

- 09/10 (PC, 18:05-19:10) - B1-B5 FATTI. U-62 (ora, PC sveglio, avvio al login), T0B (5) registrazioni (`695a62cd`, `6247fbd0`), T0B (6) documenti
  (`143a60d6`, `7c92904c`), U-60 misura (`e7eee8bd`), verifica del PC di T0A/T0B4/T0C (`fe531f51`: tutte firmate, R-1..R-9). Correzioni
  del PC ai test: `salute.test.ts` CRLF (`be660b93`), test della barra con ri-emissioni del feed (`6247fbd0`). DECISIONI DELL'UTENTE: ok al diff
  della Base; T0A su master SPENTA solo se firmata (si'), con il solo perimetro di T0A e test/build verdi. In attesa dell'utente: R-5 (voce
  di menu «Salute» visibile a monitor spento: entra cosi' o si aspetta un interruttore?). Da fare nel cloud: R-3 prima del congelamento, R-4
  (7 giorni) prima della migrazione, R-6, R-9; poi le decisioni tecniche (a)-(e) e lo scenario «modalita-mista».

- 09/10 (cloud, 19:00) - CHIUSI R-3, R-4, R-5, R-6, R-9 in un solo commit sul ramo dell'architettura, perimetro T0A/T0C (da portare sul
  ramo `tappa0-salute-su-master` con cherry-pick). R-5: la voce «Salute» si vede SOLO con il monitor acceso: la STESSA riga
  `MONITOR_SALUTE=1` del `.env` della radice, letta da `vite.config.ts` alla build (`VITE_MONITOR_SALUTE`, `frontend/src/lib/monitorSalute.ts`);
  nessuna chiamata a runtime (una prima versione con una RPC ogni 5 minuti e' stata scartata: la fotografia di parita' vieta al guscio
  letture nuove, 24 pagine rosse). Dopo aver cambiato la riga: `npm run build` ad app spenta. La rotta /salute resta. Scelta del
  coordinatore su delega dell'utente: niente voce visibile a monitor spento. R-4: pulizia di serie 7 giorni (migrazione, COSA_FA, referto T0A) con test. R-9: test in processo pulito
  (`sonde.ATTIVO` falso all'import; la mutazione del PC ora e' rossa). R-6: il finto `update_trade(id, **fields)` come il vero. R-3:
  `CAMPI_ID_OROLOGIO` legato alla tabella del par. 3 di `TOLLERANZE.md` (campo in piu' o in meno = rosso). U-60: confermati 120 ms
  (incertezza 110-150) come proposto dal PC. Ogni test nuovo falsificato (rosso con la mutazione, verde col ripristino).

- 09/10 (PC, 22:10-23:25) - T0A SU MASTER, SPENTA (decisione dell'utente: aspettato l'interruttore di R-5). Rilette sul PC f9084b4c e
  2255266c (solo perimetro T0A): pytest Betfair/monitor 60/60, vitest shell+monitorSalute+fotografia 70/70, tsc 0, mutazione del
  coordinatore sull'interruttore (`!== '0'` al posto di `=== '1'`) ROSSA (2 test) e ripristinata. Ramo `tappa0-salute-su-master` =
  master 30216dac + e44032a9 + 6d02e578 + test CRLF + f9084b4c + 2255266c (referto T0A lasciato fuori da master): pytest 11.535/0,
  vitest 5.572/0, tsc 0, build ok. PUSH su master in avanzamento veloce: master = `cf5236f9`. Pull e build ad app spenta nel
  checkout principale (23:22, `.env` senza MONITOR_SALUTE: voce «Salute» assente). U-60: utente CONFERMA 120 ms (incertezza 110-150).
  Latenza comando->place (test 20 ms, rosso nel cloud sotto carico): sul PC scarico p95 1,92 / 2,53 / 3,12 ms su 3 corse (p50 1,2-1,5,
  max 13 ms): il tetto di 20 ms regge, il rosso del cloud e' carico della macchina. PROSSIMI PASSI nell'ordine: (1) l'utente applica
  `migrations/monitor_metrics_2026-10-09.sql` (7 giorni); (2) il PC aggiunge `MONITOR_SALUTE=1` al `.env`; (3) `npm run build` ad app
  spenta (la voce compare solo cosi'); (4) l'utente riavvia; (5) 24 h di misura; (6) referto T0A §5.

## Punto di ripresa

Ordine dei lavori: PC -> B1-B5 e verifica/firma di T0A, T0B4, T0C strumenti; cloud -> decisioni tecniche (a)-(e), scenario
«modalita-mista» di Omega, istruzioni del congelamento; utente -> un si' per l'ingresso di T0A su master (spento); PC -> 24 h
della Salute e congelamento. Prossima sessione: le tre consegne del 09/10 sono verificate e integrate (sul ramo dell'architettura). Da fare nel cloud: applicare le decisioni tecniche
(a)-(e) e, se l'utente dice si', lo scenario «modalita-mista» di Omega; leggere i numeri del PC (U-62, U-60, T0B 5-6, T0A 24 h).
Poi il PC produce le baseline (due giri ciascuna) e il manifesto di T0C sulla sua macchina.
Dopo T0C: T1/T2/T3 (05 §3, grafo delle dipendenze).
