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
| T0A | Modulo «Salute» + misure mancanti + referto 24 h | cloud (codice) + PC (migrazione `monitor_metrics`, 24 h app accesa) | parte cloud fatta (`e44032a9`, `6d02e578`, `bd9e37cc`, 09/10); da fare PC: migrazione, `MONITOR_SALUTE=1`, 24 h, 30 ordini paper, referto (`tappa0/T0A_SALUTE/REFERTO.md` §5) |
| T0B (1)-(3) | Cantieri 15, 11, 7 del banco | cloud | fatta (fusi su master entro il 09/10, `CRONOSTORIA.md` 08/10) |
| T0B (4) | Finto di Omega con la firma del vero (`aggregates(..., mode)`), referto prima/dopo | cloud | fatta (`07115d13`, 09/10; referto `tappa0/T0B4_FINTO_OMEGA/`) |
| T0B (5) | 3-5 partite tennis in `registrazioni_banco/` (U-44) + registrazioni calcio COMPLETE aggiuntive per Mike (U-27) | PC | da fare (PC) |
| T0B (6) | Commit dei 4 documenti (U-37) + testo della Base allineato al 25/09 | PC | da fare (PC) |
| U-62 | Ora di Windows, niente sospensione, avvio al login (app spenta o bot flat) | PC + utente | da fare (PC) |
| U-60 | Misura dei 120 ms delle letture REST del banco | PC | da fare (PC) |
| T0C strumenti | Cassetta, ombra (`--ombra`), `TOLLERANZE.md`, `congela`, determinismo, impronte | cloud | fatta (`cd41b2f1`, 09/10; referto `tappa0/T0C_STRUMENTI/`) |
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

## Punto di ripresa

Ordine dei lavori: PC -> B1-B5 e verifica/firma di T0A, T0B4, T0C strumenti; cloud -> decisioni tecniche (a)-(e), scenario
«modalita-mista» di Omega, istruzioni del congelamento; utente -> un si' per l'ingresso di T0A su master (spento); PC -> 24 h
della Salute e congelamento. Prossima sessione: le tre consegne del 09/10 sono verificate e integrate (sul ramo dell'architettura). Da fare nel cloud: applicare le decisioni tecniche
(a)-(e) e, se l'utente dice si', lo scenario «modalita-mista» di Omega; leggere i numeri del PC (U-62, U-60, T0B 5-6, T0A 24 h).
Poi il PC produce le baseline (due giri ciascuna) e il manifesto di T0C sulla sua macchina.
Dopo T0C: T1/T2/T3 (05 §3, grafo delle dipendenze).
