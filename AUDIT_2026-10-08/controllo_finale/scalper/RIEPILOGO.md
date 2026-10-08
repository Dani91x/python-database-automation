# Controllo finale scalper_calcio sulla cima d01de76 (tutti gli scenari, `--worker 3`)

Data: 2026-10-08. Esecutore: sessione cloud delegata (nessuna modifica al codice, nessun commit di codice).
Ramo: `claude/blissful-sagan-hri7o6-finale-scalper`, creato da `d01de76e` (verificato con `git log --oneline -1`: `d01de76`).

## Ambiente

- Registrazioni: `registrazioni_banco/` decompresse in `_live_raw/` con lo script di `registrazioni_banco/LEGGIMI.md` (entrambe COMPLETE).
- Container: Python 3.13, `nproc` = 4, 15 GB RAM. Installati SOLO nel container: `psutil`, poi (il banco non partiva:
  `ModuleNotFoundError: No module named 'flumine'`, poi `scipy`) `flumine==2.13.11`, `betfairlightweight[speed]==2.23.2`
  e `pip install -r requirements.txt`. Il referto dichiara `flumine 2.13.11 | betfairlightweight 2.23.2`, come i riferimenti.
- Impronta del codice bot dichiarata dal banco: `de72fb261d8e (13 file)`, la stessa di R1 (`controllo_scalper_597ea3a`);
  R2 (`riferimenti_cloud`, cima 1ac69d0) dichiara `a80c2527fcb7 (12 file)`.
- Riga del banco presente in entrambi i referti `tutti`: `worker: 3 su 4 core fisici (un processo per coppia evento x scenario, 56 coppie; ...)`.

## Comandi e tempi (`_tempi.txt`, UTC)

| # | comando | inizio | fine | rc | note |
|---|---|---|---|---|---|
| 1 | `python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --scenari tutti --worker 3` | 15:53:37 | 16:21:32 | **137** | **processo padre ucciso dall'OOM killer** dopo 55 scenari su 56 (vedi sotto) |
| 1b | `python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --scenari rifiuti-betfair-codici-paper --worker 3` | 16:21:59 | 16:22:44 | 1 | lo scenario mancante, da solo (TEMPO TOTALE 41.4 s) |
| 2 | `python -m Betfair.stream.backtest.certifica scalper_calcio 35760084 --scenari tutti --worker 3` | 16:24:07 | 16:31:03 | 1 | completo, 56/56; TEMPO TOTALE 6m53.5s (413.5 s), nessun LENTO |

rc=1 e' l'uscita del banco quando c'e' almeno un KO (attesi, vedi tabella).

### Incidente del passo 1: memoria (fatti, nessuna ipotesi)

- `dmesg`: `Memory cgroup out of memory: Killed process 972 (python) total-vm:10901024kB, anon-rss:10176028kB` (~10 GB),
  `constraint=CONSTRAINT_MEMCG`. Il comando ha reso 137; il referto si ferma dopo `rifiuti-betfair-codici`
  (55 righe di esito su 56 scenari dichiarati), SENZA la coda (ESITO, COPERTURA DEI CONTROLLI, MAI SOLLECITATI, TEMPO TOTALE, MEMORIA).
- Manca solo `rifiuti-betfair-codici-paper`: rilanciato da solo (passo 1b) con lo stesso punto d'ingresso.
- Tre processi worker del passo 1 (pid 997, 998, 999, ppid 1, RSS 1,0-1,6 GB, tempo CPU fermo) sono rimasti orfani dopo la morte del padre.
  **Non li ho terminati**: il permesso e' stato negato. Sono ancora vivi a fine lavoro (~3,9 GB).
- Per confronto, nel passo 2 (35760084) il banco dichiara `MEMORIA: picco per worker 169-645 MB (media 331 MB su 56 repliche)`
  e il campionamento con `ps` ogni 10 s ha visto il processo piu' grande a 1800 MB a fine run.
- Conseguenza per il confronto: per 35797769 non esiste una coda (copertura dei controlli) del run completo; il confronto scenario per scenario e' completo (56/56).
- Inciampo mio (nessun effetto sui dati): per un errore nel comando in background (`&` applicato a tutta la catena `&&`) i referti 1b e 2
  e due righe di tempo sono stati scritti in `/`; li ho spostati qui senza modificarli. Resta un file `/_tempi.txt`
  (copia delle due righe di tempo), che non ho potuto cancellare (rimozione in `/` bloccata dal controllo di sicurezza).

## Metodo del confronto

Script: `confronta_referti.py` (in questa cartella). Spezza i referti per scenario (dalla riga di esito alle righe rientrate) ed esclude:
righe `tempo:`, LENTO, TEMPO TOTALE, `worker:`, `MEMORIA:`, righe di log `LIVELLO:modulo:`, impronta del codice, comando, percorso delle registrazioni.
Tutto il resto, stati compresi, si confronta riga per riga. Per ogni scenario: se c'e' in R1 (`controllo_scalper_597ea3a/<ev>_blocco1..4.txt`, 14 per evento) si confronta con R1,
altrimenti con R2 (`riferimenti_cloud/scalper_<ev>_blocco1..4.txt`, 51 per evento). Uscite:
`confronto_35797769.txt`, `confronto_35797769_rifiuti-betfair-codici-paper.txt` (`--scenario-unico`: con un solo scenario il banco non stampa `[scenario]`),
`confronto_35760084.txt`; seconda passata `--maschera-id` (gli identificativi numerici a 18 cifre diventano `<ID18>`):
`confronto_35797769_maschera_id.txt`, `confronto_35760084_maschera_id.txt`. La tabella sotto e' generata da `genera_tabella.py`.

Copertura: 56 scenari per evento, ognuno con un riferimento (14 R1 + 42 R2, perche' R2 ha 51 scenari e 9 sono anche in R1). **Nessuno scenario
presente solo nel nuovo referto**: la famiglia `ordine-esterno*` (W3b) e' tutta in R1 ed e' IDENTICA (vedi tabella).

## Esito in breve

- **35797769**: OK 49, KO 5, NE 2 (56). KO: `riavvio` B1 x21, `chiusura-abbinata-in-parte` B2 x1, `uscite-manuali-firmate` UF2 x1,
  `rifiuti-betfair-codici` RC3 x1, `rifiuti-betfair-codici-paper` RC3 x1. Sono tutti e soli i KO noti dei riferimenti.
- **35760084**: OK 37, KO 1, NE 18 (56). Unico KO `auto-live` AL1 x1, noto. Coda del referto: `ESITO: 55 partite senza violazioni, 1 con violazioni`.
- **Righe di esito** (OK/KO/NE, tick, decisioni, azioni, stati) e **controlli violati**: identici al riferimento in 112 scenari su 112.
- **R1** (28 scenari): IDENTICI riga per riga, 0 righe diverse.
- **R2** (84 scenari): 49 identici; in 35 scenari cambiano righe di `nota:`/esempio, e **ogni riga diversa differisce solo per un identificativo d'ordine a 18 cifre**.
  Con gli id mascherati: 0 differenze su 112 scenari. Elenco completo qui sotto.

## Tabella per scenario

`rif.` = riferimento usato; `righe diverse` = righe +/- del diff (0 = identico, esclusioni comprese).

| scenario | 35797769 | tick | dec. | azioni | violati | rif. | righe diverse | 35760084 | tick | dec. | azioni | violati | rif. | righe diverse |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `base` | OK | 665941 | 121012 | 44 | - | R1 | 0 | OK | 124672 | 23599 | 0 | - | R1 | 0 |
| `paper` | OK | 665941 | 121012 | 44 | - | R1 | 0 | OK | 124672 | 23599 | 0 | - | R1 | 0 |
| `senza-missione` | OK | 665941 | 121012 | 246 | - | R2 | 0 | OK | 124672 | 23599 | 0 | - | R2 | 0 |
| `bot-fermo` | OK | 233803 | 42486 | 44 | - | R2 | 0 | OK | 29369 | 5592 | 0 | - | R2 | 0 |
| `kill-switch` | OK | 233803 | 42486 | 44 | - | R2 | 0 | OK | 29369 | 5592 | 0 | - | R2 | 0 |
| `esiti-ignoti` | OK | 665941 | 121012 | 44 | - | R2 | 0 | OK | 124672 | 23599 | 0 | - | R2 | 0 |
| `rifiuti-betfair` | OK | 665941 | 121012 | 56 | - | R1 | 0 | OK | 124672 | 23599 | 0 | - | R1 | 0 |
| `riavvio` | KO | 665941 | 119822 | 160 | B1 x21 | R2 | 2 | OK | 124672 | 23303 | 0 | - | R2 | 0 |
| `chiusura-abbinata-in-parte` | KO | 665941 | 121012 | 213 | B2 x1 | R1 | 0 | OK | 124672 | 23599 | 0 | - | R1 | 0 |
| `ordine-esterno` | OK | 7760 | 1373 | 2 | - | R1 | 0 | OK | 29538 | 5607 | 0 | - | R1 | 0 |
| `ordine-esterno-app` | OK | 7760 | 1373 | 2 | - | R1 | 0 | OK | 29538 | 5607 | 0 | - | R1 | 0 |
| `ordine-esterno-di-un-bot` | OK | 665941 | 121012 | 44 | - | R1 | 0 | OK | 124672 | 23599 | 0 | - | R1 | 0 |
| `ordine-esterno-db-giu` | OK | 665941 | 121012 | 98 | - | R1 | 0 | OK | 124672 | 23599 | 0 | - | R1 | 0 |
| `ordine-esterno-altro-mercato` | OK | 665941 | 121012 | 44 | - | R1 | 0 | OK | 124672 | 23599 | 0 | - | R1 | 0 |
| `sniper` | OK | 1511913 | 286052 | 44 | - | R2 | 0 | OK | 504571 | 87165 | 0 | - | R2 | 0 |
| `sniper-paper` | OK | 1511913 | 286052 | 44 | - | R1 | 0 | OK | 504571 | 87165 | 0 | - | R1 | 0 |
| `sniper-uscite-auto` | OK | 1511913 | 286052 | 44 | - | R2 | 0 | OK | 504571 | 87165 | 0 | - | R2 | 0 |
| `uscite-manuali` | OK | 1511913 | 286052 | 239 | - | R2 | 0 | OK | 504571 | 87165 | 0 | - | R2 | 0 |
| `uscite-manuali-firmate` | KO | 1511913 | 286052 | 64 | UF2 x1 | R2 | 2 | OK | 504571 | 87165 | 0 | - | R2 | 0 |
| `auto-live` | OK | 665941 | 121012 | 44 | - | R2 | 0 | KO | 124672 | 23599 | 0 | AL1 x1 | R2 | 0 |
| `media-under` | OK | 1511913 | 78022 | 10 | - | R2 | 0 | NE | 504571 | 18662 | 0 | - | R2 | 0 |
| `media-under-paper` | OK | 1511913 | 78022 | 10 | - | R2 | 0 | NE | 504571 | 18662 | 0 | - | R2 | 0 |
| `media-under-35` | NE | 1511913 | 81112 | 0 | - | R2 | 0 | NE | 504571 | 25586 | 0 | - | R2 | 0 |
| `media-under-obiettivo-030` | OK | 1511913 | 78022 | 10 | - | R2 | 0 | NE | 504571 | 18662 | 0 | - | R2 | 0 |
| `media-under-rientri-1` | OK | 1511913 | 78022 | 10 | - | R2 | 0 | NE | 504571 | 18662 | 0 | - | R2 | 0 |
| `media-under-rischio-30` | OK | 1511913 | 78022 | 10 | - | R2 | 0 | NE | 504571 | 18662 | 0 | - | R2 | 0 |
| `media-under-tick-1` | OK | 1511913 | 78022 | 19 | - | R2 | 0 | NE | 504571 | 18662 | 0 | - | R2 | 0 |
| `media-under-riavvio` | OK | 1511913 | 77632 | 10 | - | R2 | 0 | NE | 504571 | 18588 | 0 | - | R2 | 0 |
| `media-under-rifiuti-betfair` | OK | 1511913 | 78022 | 16 | - | R2 | 0 | NE | 504571 | 18662 | 0 | - | R2 | 0 |
| `media-under-esiti-ignoti` | OK | 1511913 | 78022 | 11 | - | R2 | 0 | NE | 504571 | 18662 | 0 | - | R2 | 0 |
| `media-under-kill-switch` | OK | 138277 | 6276 | 2 | - | R2 | 0 | NE | 29369 | 1398 | 0 | - | R2 | 0 |
| `media-under-bot-fermo` | OK | 138277 | 6276 | 2 | - | R2 | 0 | NE | 29369 | 1398 | 0 | - | R2 | 0 |
| `media-under-liquidita-100` | OK | 1511913 | 78022 | 10 | - | R2 | 0 | NE | 504571 | 18662 | 0 | - | R2 | 0 |
| `media-under-35-liquidita-50` | OK | 1511913 | 81112 | 9 | - | R2 | 0 | NE | 504571 | 25586 | 0 | - | R2 | 0 |
| `media-clic-lontano` | OK | 1511913 | 78022 | 11 | - | R2 | 6 | OK | 504571 | 18662 | 25 | - | R2 | 4 |
| `media-clic-lontano-paper` | OK | 1511913 | 78022 | 11 | - | R2 | 6 | OK | 504571 | 18662 | 25 | - | R2 | 4 |
| `media-clic-lontano-filtri` | OK | 1511913 | 78022 | 15 | - | R2 | 6 | OK | 504571 | 18662 | 25 | - | R2 | 4 |
| `media-clic-lontano-35` | OK | 1511913 | 81112 | 24 | - | R2 | 8 | OK | 504571 | 25586 | 14 | - | R2 | 4 |
| `media-clic-finestra` | OK | 1511913 | 78022 | 5 | - | R2 | 4 | OK | 504571 | 18662 | 10 | - | R2 | 4 |
| `media-clic-gioco` | OK | 1511913 | 78022 | 2 | - | R2 | 4 | OK | 504571 | 18662 | 5 | - | R2 | 4 |
| `media-clic-gioco-35` | OK | 1511913 | 81112 | 2 | - | R2 | 4 | OK | 504571 | 25586 | 5 | - | R2 | 4 |
| `media-clic-prima-del-gol` | OK | 1511913 | 78022 | 22 | - | R2 | 4 | OK | 504571 | 18662 | 14 | - | R2 | 4 |
| `media-clic-prima-del-gol-35` | OK | 1511913 | 81112 | 9 | - | R2 | 4 | OK | 504571 | 25586 | 9 | - | R2 | 4 |
| `media-clic-dopo-il-gol` | OK | 1511913 | 78022 | 17 | - | R2 | 4 | OK | 504571 | 18662 | 15 | - | R2 | 4 |
| `media-clic-sospeso` | NE | 1511913 | 78022 | 15 | - | R2 | 4 | OK | 504571 | 18662 | 0 | - | R2 | 0 |
| `media-clic-prezzi-fermi` | OK | 1511913 | 77762 | 0 | - | R2 | 0 | OK | 504571 | 18599 | 0 | - | R2 | 0 |
| `media-clic-doppio` | OK | 1511913 | 78022 | 10 | - | R2 | 4 | OK | 504571 | 18662 | 15 | - | R2 | 4 |
| `media-clic-in-posizione` | OK | 1511913 | 78022 | 10 | - | R2 | 4 | OK | 504571 | 18662 | 15 | - | R2 | 4 |
| `media-clic-riavvio` | OK | 1511913 | 77632 | 11 | - | R2 | 6 | OK | 504571 | 18451 | 28 | - | R2 | 4 |
| `media-clic-tick-1` | OK | 1511913 | 78022 | 38 | - | R2 | 8 | OK | 504571 | 18662 | 23 | - | R2 | 4 |
| `media-clic-tick-1-filtri` | OK | 1511913 | 78022 | 34 | - | R2 | 8 | OK | 504571 | 18662 | 23 | - | R2 | 4 |
| `media-clic-due-clic` | OK | 1511913 | 81112 | 4 | - | R2 | 8 | OK | 504571 | 25586 | 14 | - | R2 | 8 |
| `ingresso-abbinato-in-parte` | OK | 665941 | 121012 | 49 | - | R1 | 0 | NE | 124672 | 23599 | 0 | - | R1 | 0 |
| `ingresso-abbinato-in-parte-paper` | OK | 665941 | 121012 | 49 | - | R1 | 0 | NE | 124672 | 23599 | 0 | - | R1 | 0 |
| `rifiuti-betfair-codici` | KO | 665941 | 121012 | 132 | RC3 x1 | R1 | 0 | NE | 124672 | 23599 | 0 | - | R1 | 0 |
| `rifiuti-betfair-codici-paper` | KO | 665941 | 121012 | 132 | RC3 x1 | R1 | 0 | NE | 124672 | 23599 | 0 | - | R1 | 0 |

## Differenze ATTESE

- Impronta del codice bot (`de72fb261d8e` contro `a80c2527fcb7` di R2; identica a R1). Esclusa dal confronto.
- Coda del referto (ESITO, copertura dei controlli): W3b la dichiara cambiata (`W3B_CONSAPEVOLEZZA_FLUMINE.md` §10.2: «Le altre righe diverse del referto
  sono la coda (ESITO e copertura dei controlli), che somma anche i due scenari nuovi; sulla 35760084 P1/P2 passano da x0 a x3»; §14.3: «Unica riga diversa:
  la riga vuota di fine blocco di `sniper-paper` ... e la coda dei conteggi»). Qui la coda non e' confrontabile: i riferimenti sono divisi in 4 blocchi,
  il nuovo referto e' un solo run, e per 35797769 la coda manca (OOM).
- Per gli scenari, §10.2 e §14.3 dichiarano i blocchi di scenario di riferimento IDENTICI fra PRIMA e DOPO W3b: **nessuna riga di scenario e' dichiarata cambiata**.

## Differenze NON attese (per intero)

Nessuna riga di esito, nessun controllo violato, nessun tick/decisioni/azioni/stati diverso. Le sole differenze sono righe di `nota:` e di esempio (`es.`)
in 35 scenari confrontati con R2 (19 su 35797769, 16 su 35760084). In tutte cambia **soltanto** un numero a 18 cifre (identificativo dell'ordine).
Il resto della riga e' uguale, come mostra la seconda passata con `--maschera-id` (0 differenze). Non ho indagato la causa.
Diff integrale (PRIMA = riferimento R2, DOPO = nuovo referto):

```
=== 35797769 [riavvio] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco4.txt)
    @@ -21 +21 @@
    -           es. ingresso 140107593359505910 BACK 22 @1.69 per 25.0 creato a 1783706589578 ms, con il divieto 'missione_prematch' attivo da 1783704449466 ms
    +           es. ingresso 140107676965433260 BACK 22 @1.69 per 25.0 creato a 1783706589578 ms, con il divieto 'missione_prematch' attivo da 1783704449466 ms

=== 35797769 [uscite-manuali-firmate] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco2.txt)
    @@ -22 +22 @@
    -           es. uscita firmata scalper|1.259819674|58805|140107595413943480|target: proposta 24.42, uscita a quota abbinabile 23.50 (abbinato + residuo, parcheggi esclusi)
    +           es. uscita firmata scalper|1.259819674|58805|140107679110283470|target: proposta 24.42, uscita a quota abbinabile 23.50 (abbinato + residuo, parcheggi esclusi)

=== 35797769 [media-clic-lontano] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco2.txt)
    @@ -21,3 +21,3 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107599359120660 @2.18 per 10.0 a pre-match, 136'33" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107599359120660 @2.18 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    -      nota: ATTIVA ADESSO ciclo 2: prima punta 140107599548461200 @2.16 a pre-match, 14'29" al fischio, partita da RIENTRO AUTOMATICO pre-match
    +      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107684241229950 @2.18 per 10.0 a pre-match, 136'33" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107684241229950 @2.18 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    +      nota: ATTIVA ADESSO ciclo 2: prima punta 140107684446882850 @2.16 a pre-match, 14'29" al fischio, partita da RIENTRO AUTOMATICO pre-match

=== 35797769 [media-clic-lontano-paper] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco3.txt)
    @@ -21,3 +21,3 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107598503827510 @2.18 per 10.0 a pre-match, 136'33" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107598503827510 @2.18 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    -      nota: ATTIVA ADESSO ciclo 2: prima punta 140107598731881060 @2.16 a pre-match, 14'29" al fischio, partita da RIENTRO AUTOMATICO pre-match
    +      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107684969707970 @2.18 per 10.0 a pre-match, 136'33" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107684969707970 @2.18 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    +      nota: ATTIVA ADESSO ciclo 2: prima punta 140107685194782980 @2.16 a pre-match, 14'29" al fischio, partita da RIENTRO AUTOMATICO pre-match

=== 35797769 [media-clic-lontano-filtri] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco4.txt)
    @@ -22,3 +22,3 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107600035094840 @2.18 per 10.0 a pre-match, 136'33" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107600035094840 @2.18 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    -      nota: ATTIVA ADESSO ciclo 2: prima punta 140107600282559440 @2.18 a pre-match, 13'26" al fischio, partita da RIENTRO AUTOMATICO pre-match
    +      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107684981552690 @2.18 per 10.0 a pre-match, 136'33" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107684981552690 @2.18 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    +      nota: ATTIVA ADESSO ciclo 2: prima punta 140107685206045980 @2.18 a pre-match, 13'26" al fischio, partita da RIENTRO AUTOMATICO pre-match

=== 35797769 [media-clic-lontano-35] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco1.txt)
    @@ -22,4 +22,4 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107600948267260 @1.44 per 10.0 a pre-match, 136'33" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107600948267260 @1.44 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    -      nota: ATTIVA ADESSO ciclo 2: prima punta 140107601101541560 @1.43 a pre-match, 41'00" al fischio, partita da RIENTRO AUTOMATICO pre-match
    -      nota: ATTIVA ADESSO ciclo 3: prima punta 140107601223102900 @1.42 a pre-match, 7'14" al fischio, partita da RIENTRO AUTOMATICO pre-match
    +      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107685460812080 @1.44 per 10.0 a pre-match, 136'33" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107685460812080 @1.44 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    +      nota: ATTIVA ADESSO ciclo 2: prima punta 140107685600441940 @1.43 a pre-match, 41'00" al fischio, partita da RIENTRO AUTOMATICO pre-match
    +      nota: ATTIVA ADESSO ciclo 3: prima punta 140107685717055650 @1.42 a pre-match, 7'14" al fischio, partita da RIENTRO AUTOMATICO pre-match

=== 35797769 [media-clic-finestra] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco2.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783709800000 (pre-match, 3'55" al fischio): letto dalla sessione pre-match, 3'53" al fischio; per il banco ESEGUIBILE; prima punta 140107600830674220 @2.2 per 10.0 a pre-match, 3'53" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107600830674220 @2.2 a pre-match, 3'53" al fischio, partita da CLIC (clic-1-1783709800000)
    +      nota: ATTIVA ADESSO clic clic-1-1783709800000 (pre-match, 3'55" al fischio): letto dalla sessione pre-match, 3'53" al fischio; per il banco ESEGUIBILE; prima punta 140107686416752990 @2.2 per 10.0 a pre-match, 3'53" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107686416752990 @2.2 a pre-match, 3'53" al fischio, partita da CLIC (clic-1-1783709800000)

=== 35797769 [media-clic-gioco] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco3.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783710094616 (in gioco al 1'00"): letto dalla sessione in gioco al 1'05"; per il banco ESEGUIBILE; prima punta 140107600008068650 @2.24 per 10.0 a in gioco al 1'05"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107600008068650 @2.24 a in gioco al 1'05", partita da CLIC (clic-1-1783710094616)
    +      nota: ATTIVA ADESSO clic clic-1-1783710094616 (in gioco al 1'00"): letto dalla sessione in gioco al 1'05"; per il banco ESEGUIBILE; prima punta 140107686500353010 @2.24 per 10.0 a in gioco al 1'05"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107686500353010 @2.24 a in gioco al 1'05", partita da CLIC (clic-1-1783710094616)

=== 35797769 [media-clic-gioco-35] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco4.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783710094616 (in gioco al 1'00"): letto dalla sessione in gioco al 1'05"; per il banco ESEGUIBILE; prima punta 140107601638909460 @1.48 per 10.0 a in gioco al 1'05"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107601638909460 @1.48 a in gioco al 1'05", partita da CLIC (clic-1-1783710094616)
    +      nota: ATTIVA ADESSO clic clic-1-1783710094616 (in gioco al 1'00"): letto dalla sessione in gioco al 1'05"; per il banco ESEGUIBILE; prima punta 140107687118527420 @1.48 per 10.0 a in gioco al 1'05"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107687118527420 @1.48 a in gioco al 1'05", partita da CLIC (clic-1-1783710094616)

=== 35797769 [media-clic-prima-del-gol] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco1.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783711774782 (in gioco al 29'00"): letto dalla sessione in gioco al 29'05"; per il banco ESEGUIBILE; prima punta 140107602884610690 @1.72 per 10.0 a in gioco al 29'05"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107602884610690 @1.72 a in gioco al 29'05", partita da CLIC (clic-1-1783711774782)
    +      nota: ATTIVA ADESSO clic clic-1-1783711774782 (in gioco al 29'00"): letto dalla sessione in gioco al 29'05"; per il banco ESEGUIBILE; prima punta 140107687725923580 @1.72 per 10.0 a in gioco al 29'05"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107687725923580 @1.72 a in gioco al 29'05", partita da CLIC (clic-1-1783711774782)

=== 35797769 [media-clic-prima-del-gol-35] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco2.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783711774785 (in gioco al 29'00"): letto dalla sessione in gioco al 29'05"; per il banco ESEGUIBILE; prima punta 140107602281915190 @1.24 per 10.0 a in gioco al 29'05"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107602281915190 @1.24 a in gioco al 29'05", partita da CLIC (clic-1-1783711774785)
    +      nota: ATTIVA ADESSO clic clic-1-1783711774785 (in gioco al 29'00"): letto dalla sessione in gioco al 29'05"; per il banco ESEGUIBILE; prima punta 140107687755274430 @1.24 per 10.0 a in gioco al 29'05"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107687755274430 @1.24 a in gioco al 29'05", partita da CLIC (clic-1-1783711774785)

=== 35797769 [media-clic-dopo-il-gol] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco3.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783711805547 (in gioco al 29'31"): letto dalla sessione in gioco al 29'36"; per il banco ESEGUIBILE; prima punta 140107601390263670 @1.96 per 10.0 a in gioco al 29'36"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107601390263670 @1.96 a in gioco al 29'36", partita da CLIC (clic-1-1783711805547)
    +      nota: ATTIVA ADESSO clic clic-1-1783711805547 (in gioco al 29'31"): letto dalla sessione in gioco al 29'36"; per il banco ESEGUIBILE; prima punta 140107688366847580 @1.96 per 10.0 a in gioco al 29'36"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107688366847580 @1.96 a in gioco al 29'36", partita da CLIC (clic-1-1783711805547)

=== 35797769 [media-clic-sospeso] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco4.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783711800082 (in gioco al 29'25"): letto dalla sessione in gioco al 29'31"; per il banco ESEGUIBILE; prima punta 140107602848323540 @1.81 per 10.0 a in gioco al 29'31"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107602848323540 @1.81 a in gioco al 29'31", partita da CLIC (clic-1-1783711800082)
    +      nota: ATTIVA ADESSO clic clic-1-1783711800082 (in gioco al 29'25"): letto dalla sessione in gioco al 29'31"; per il banco ESEGUIBILE; prima punta 140107688835317950 @1.81 per 10.0 a in gioco al 29'31"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107688835317950 @1.81 a in gioco al 29'31", partita da CLIC (clic-1-1783711800082)

=== 35797769 [media-clic-doppio] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco2.txt)
    @@ -21,2 +21,2 @@
    -      nota: ATTIVA ADESSO clic clic-2-1783709100400 (pre-match, 15'34" al fischio): letto dalla sessione pre-match, 15'33" al fischio; per il banco ESEGUIBILE; prima punta 140107603245467640 @2.18 per 10.0 a pre-match, 15'33" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107603245467640 @2.18 a pre-match, 15'33" al fischio, partita da CLIC (clic-2-1783709100400)
    +      nota: ATTIVA ADESSO clic clic-2-1783709100400 (pre-match, 15'34" al fischio): letto dalla sessione pre-match, 15'33" al fischio; per il banco ESEGUIBILE; prima punta 140107689434725650 @2.18 per 10.0 a pre-match, 15'33" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107689434725650 @2.18 a pre-match, 15'33" al fischio, partita da CLIC (clic-2-1783709100400)

=== 35797769 [media-clic-in-posizione] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco3.txt)
    @@ -20 +20 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783709100000 (pre-match, 15'35" al fischio): letto dalla sessione pre-match, 15'33" al fischio; per il banco ESEGUIBILE; prima punta 140107602552338610 @2.18 per 10.0 a pre-match, 15'33" al fischio
    +      nota: ATTIVA ADESSO clic clic-1-1783709100000 (pre-match, 15'35" al fischio): letto dalla sessione pre-match, 15'33" al fischio; per il banco ESEGUIBILE; prima punta 140107689692016960 @2.18 per 10.0 a pre-match, 15'33" al fischio
    @@ -22 +22 @@
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107602552338610 @2.18 a pre-match, 15'33" al fischio, partita da CLIC (clic-1-1783709100000)
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107689692016960 @2.18 a pre-match, 15'33" al fischio, partita da CLIC (clic-1-1783709100000)

=== 35797769 [media-clic-riavvio] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco4.txt)
    @@ -24,3 +24,3 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107603609080870 @2.18 per 10.0 a pre-match, 136'33" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107603609080870 @2.18 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    -      nota: ATTIVA ADESSO ciclo 2: prima punta 140107603844780870 @2.16 a pre-match, 14'29" al fischio, partita da RIENTRO AUTOMATICO pre-match
    +      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107689593421000 @2.18 per 10.0 a pre-match, 136'33" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107689593421000 @2.18 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    +      nota: ATTIVA ADESSO ciclo 2: prima punta 140107689816090770 @2.16 a pre-match, 14'29" al fischio, partita da RIENTRO AUTOMATICO pre-match

=== 35797769 [media-clic-tick-1] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco1.txt)
    @@ -22,4 +22,4 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107604795197950 @2.18 per 10.0 a pre-match, 136'33" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107604795197950 @2.18 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    -      nota: ATTIVA ADESSO ciclo 2: prima punta 140107604807255120 @2.16 a pre-match, 110'24" al fischio, partita da RIENTRO AUTOMATICO pre-match
    -      nota: ATTIVA ADESSO ciclo 3: prima punta 140107605056809370 @2.16 a pre-match, 14'29" al fischio, partita da RIENTRO AUTOMATICO pre-match
    +      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107690486327980 @2.18 per 10.0 a pre-match, 136'33" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107690486327980 @2.18 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    +      nota: ATTIVA ADESSO ciclo 2: prima punta 140107690503634190 @2.16 a pre-match, 110'24" al fischio, partita da RIENTRO AUTOMATICO pre-match
    +      nota: ATTIVA ADESSO ciclo 3: prima punta 140107690767793550 @2.16 a pre-match, 14'29" al fischio, partita da RIENTRO AUTOMATICO pre-match

=== 35797769 [media-clic-tick-1-filtri] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco2.txt)
    @@ -23,4 +23,4 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107604414933600 @2.18 per 10.0 a pre-match, 136'33" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107604414933600 @2.18 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    -      nota: ATTIVA ADESSO ciclo 2: prima punta 140107604431971730 @2.16 a pre-match, 110'24" al fischio, partita da RIENTRO AUTOMATICO pre-match
    -      nota: ATTIVA ADESSO ciclo 3: prima punta 140107604695966490 @2.18 a pre-match, 13'26" al fischio, partita da RIENTRO AUTOMATICO pre-match
    +      nota: ATTIVA ADESSO clic clic-1-1783701706771 (pre-match, 138'48" al fischio): letto dalla sessione pre-match, 136'33" al fischio; per il banco ESEGUIBILE; prima punta 140107690754775840 @2.18 per 10.0 a pre-match, 136'33" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107690754775840 @2.18 a pre-match, 136'33" al fischio, partita da CLIC (clic-1-1783701706771)
    +      nota: ATTIVA ADESSO ciclo 2: prima punta 140107690770945890 @2.16 a pre-match, 110'24" al fischio, partita da RIENTRO AUTOMATICO pre-match
    +      nota: ATTIVA ADESSO ciclo 3: prima punta 140107691055301040 @2.18 a pre-match, 13'26" al fischio, partita da RIENTRO AUTOMATICO pre-match

=== 35797769 [media-clic-due-clic] DIVERSO da R2 (riferimenti_cloud/scalper_35797769_blocco3.txt)
    @@ -21,4 +21,4 @@
    -      nota: ATTIVA ADESSO clic clic-1-1783710094616 (in gioco al 1'00"): letto dalla sessione in gioco al 1'05"; per il banco ESEGUIBILE; prima punta 140107603884236360 @1.48 per 10.0 a in gioco al 1'05"
    -      nota: ATTIVA ADESSO clic clic-2-1783711294616 (in gioco al 21'00"): letto dalla sessione in gioco al 21'03"; per il banco ESEGUIBILE; prima punta 140107604029639570 @1.3 per 10.0 a in gioco al 21'04"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107603884236360 @1.48 a in gioco al 1'05", partita da CLIC (clic-1-1783710094616)
    -      nota: ATTIVA ADESSO ciclo 2: prima punta 140107604029639570 @1.3 a in gioco al 21'04", partita da CLIC (clic-2-1783711294616)
    +      nota: ATTIVA ADESSO clic clic-1-1783710094616 (in gioco al 1'00"): letto dalla sessione in gioco al 1'05"; per il banco ESEGUIBILE; prima punta 140107691137214220 @1.48 per 10.0 a in gioco al 1'05"
    +      nota: ATTIVA ADESSO clic clic-2-1783711294616 (in gioco al 21'00"): letto dalla sessione in gioco al 21'03"; per il banco ESEGUIBILE; prima punta 140107691287765410 @1.3 per 10.0 a in gioco al 21'04"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107691137214220 @1.48 a in gioco al 1'05", partita da CLIC (clic-1-1783710094616)
    +      nota: ATTIVA ADESSO ciclo 2: prima punta 140107691287765410 @1.3 a in gioco al 21'04", partita da CLIC (clic-2-1783711294616)

=== 35760084 [media-clic-lontano] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco2.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107607985388350 @2.68 per 10.0 a pre-match, 44'06" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107607985388350 @2.68 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)
    +      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107695912640470 @2.68 per 10.0 a pre-match, 44'06" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107695912640470 @2.68 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)

=== 35760084 [media-clic-lontano-paper] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco3.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107607794442170 @2.68 per 10.0 a pre-match, 44'06" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107607794442170 @2.68 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)
    +      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107696113391890 @2.68 per 10.0 a pre-match, 44'06" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107696113391890 @2.68 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)

=== 35760084 [media-clic-lontano-filtri] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco4.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107608124446900 @2.68 per 10.0 a pre-match, 44'06" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107608124446900 @2.68 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)
    +      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107696115310560 @2.68 per 10.0 a pre-match, 44'06" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107696115310560 @2.68 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)

=== 35760084 [media-clic-lontano-35] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco1.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107608156409610 @1.74 per 10.0 a pre-match, 44'06" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107608156409610 @1.74 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)
    +      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107696412815220 @1.74 per 10.0 a pre-match, 44'06" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107696412815220 @1.74 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)

=== 35760084 [media-clic-finestra] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco2.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782835000000 (pre-match, 3'45" al fischio): letto dalla sessione pre-match, 3'35" al fischio; per il banco ESEGUIBILE; prima punta 140107608478811110 @2.94 per 10.0 a pre-match, 3'35" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107608478811110 @2.94 a pre-match, 3'35" al fischio, partita da CLIC (clic-1-1782835000000)
    +      nota: ATTIVA ADESSO clic clic-1-1782835000000 (pre-match, 3'45" al fischio): letto dalla sessione pre-match, 3'35" al fischio; per il banco ESEGUIBILE; prima punta 140107696641761690 @2.94 per 10.0 a pre-match, 3'35" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107696641761690 @2.94 a pre-match, 3'35" al fischio, partita da CLIC (clic-1-1782835000000)

=== 35760084 [media-clic-gioco] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco3.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782835744357 (in gioco al 8'39"): letto dalla sessione in gioco al 8'43"; per il banco ESEGUIBILE; prima punta 140107608302501530 @5.6 per 10.0 a in gioco al 8'43"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107608302501530 @5.6 a in gioco al 8'43", partita da CLIC (clic-1-1782835744357)
    +      nota: ATTIVA ADESSO clic clic-1-1782835744357 (in gioco al 8'39"): letto dalla sessione in gioco al 8'43"; per il banco ESEGUIBILE; prima punta 140107696673140150 @5.6 per 10.0 a in gioco al 8'43"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107696673140150 @5.6 a in gioco al 8'43", partita da CLIC (clic-1-1782835744357)

=== 35760084 [media-clic-gioco-35] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco4.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782835744399 (in gioco al 8'39"): letto dalla sessione in gioco al 8'43"; per il banco ESEGUIBILE; prima punta 140107608644692130 @2.58 per 10.0 a in gioco al 8'43"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107608644692130 @2.58 a in gioco al 8'43", partita da CLIC (clic-1-1782835744399)
    +      nota: ATTIVA ADESSO clic clic-1-1782835744399 (in gioco al 8'39"): letto dalla sessione in gioco al 8'43"; per il banco ESEGUIBILE; prima punta 140107696829984810 @2.58 per 10.0 a in gioco al 8'43"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107696829984810 @2.58 a in gioco al 8'43", partita da CLIC (clic-1-1782835744399)

=== 35760084 [media-clic-prima-del-gol] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco1.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782835293201 (in gioco al 1'08"): letto dalla sessione in gioco al 1'11"; per il banco ESEGUIBILE; prima punta 140107608536798810 @2.86 per 10.0 a in gioco al 1'11"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107608536798810 @2.86 a in gioco al 1'11", partita da CLIC (clic-1-1782835293201)
    +      nota: ATTIVA ADESSO clic clic-1-1782835293201 (in gioco al 1'08"): letto dalla sessione in gioco al 1'11"; per il banco ESEGUIBILE; prima punta 140107696944703790 @2.86 per 10.0 a in gioco al 1'11"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107696944703790 @2.86 a in gioco al 1'11", partita da CLIC (clic-1-1782835293201)

=== 35760084 [media-clic-prima-del-gol-35] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco2.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782835293214 (in gioco al 1'08"): letto dalla sessione in gioco al 1'12"; per il banco ESEGUIBILE; prima punta 140107608798608520 @1.74 per 10.0 a in gioco al 1'12"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107608798608520 @1.74 a in gioco al 1'12", partita da CLIC (clic-1-1782835293214)
    +      nota: ATTIVA ADESSO clic clic-1-1782835293214 (in gioco al 1'08"): letto dalla sessione in gioco al 1'12"; per il banco ESEGUIBILE; prima punta 140107696979143920 @1.74 per 10.0 a in gioco al 1'12"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107696979143920 @1.74 a in gioco al 1'12", partita da CLIC (clic-1-1782835293214)

=== 35760084 [media-clic-dopo-il-gol] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco3.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782835323206 (in gioco al 1'38"): letto dalla sessione in gioco al 1'42"; per il banco ESEGUIBILE; prima punta 140107608555956930 @2.66 per 10.0 a in gioco al 1'42"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107608555956930 @2.66 a in gioco al 1'42", partita da CLIC (clic-1-1782835323206)
    +      nota: ATTIVA ADESSO clic clic-1-1782835323206 (in gioco al 1'38"): letto dalla sessione in gioco al 1'42"; per il banco ESEGUIBILE; prima punta 140107697114112000 @2.66 per 10.0 a in gioco al 1'42"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107697114112000 @2.66 a in gioco al 1'42", partita da CLIC (clic-1-1782835323206)

=== 35760084 [media-clic-doppio] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco2.txt)
    @@ -21,2 +21,2 @@
    -      nota: ATTIVA ADESSO clic clic-2-1782834300400 (pre-match, 15'25" al fischio): letto dalla sessione pre-match, 15'14" al fischio; per il banco ESEGUIBILE; prima punta 140107609122096710 @2.88 per 10.0 a pre-match, 15'14" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107609122096710 @2.88 a pre-match, 15'14" al fischio, partita da CLIC (clic-2-1782834300400)
    +      nota: ATTIVA ADESSO clic clic-2-1782834300400 (pre-match, 15'25" al fischio): letto dalla sessione pre-match, 15'14" al fischio; per il banco ESEGUIBILE; prima punta 140107697505743000 @2.88 per 10.0 a pre-match, 15'14" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107697505743000 @2.88 a pre-match, 15'14" al fischio, partita da CLIC (clic-2-1782834300400)

=== 35760084 [media-clic-in-posizione] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco3.txt)
    @@ -20 +20 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782834300000 (pre-match, 15'25" al fischio): letto dalla sessione pre-match, 15'14" al fischio; per il banco ESEGUIBILE; prima punta 140107608903317140 @2.88 per 10.0 a pre-match, 15'14" al fischio
    +      nota: ATTIVA ADESSO clic clic-1-1782834300000 (pre-match, 15'25" al fischio): letto dalla sessione pre-match, 15'14" al fischio; per il banco ESEGUIBILE; prima punta 140107697572489340 @2.88 per 10.0 a pre-match, 15'14" al fischio
    @@ -22 +22 @@
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107608903317140 @2.88 a pre-match, 15'14" al fischio, partita da CLIC (clic-1-1782834300000)
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107697572489340 @2.88 a pre-match, 15'14" al fischio, partita da CLIC (clic-1-1782834300000)

=== 35760084 [media-clic-riavvio] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco4.txt)
    @@ -23,2 +23,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107609103285170 @2.68 per 10.0 a pre-match, 44'06" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107609103285170 @2.68 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)
    +      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107697584211080 @2.68 per 10.0 a pre-match, 44'06" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107697584211080 @2.68 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)

=== 35760084 [media-clic-tick-1] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco1.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107609068835360 @2.68 per 10.0 a pre-match, 44'06" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107609068835360 @2.68 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)
    +      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107697933573140 @2.68 per 10.0 a pre-match, 44'06" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107697933573140 @2.68 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)

=== 35760084 [media-clic-tick-1-filtri] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco2.txt)
    @@ -20,2 +20,2 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107609474084370 @2.68 per 10.0 a pre-match, 44'06" al fischio
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107609474084370 @2.68 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)
    +      nota: ATTIVA ADESSO clic clic-1-1782832552415 (pre-match, 44'33" al fischio): letto dalla sessione pre-match, 44'06" al fischio; per il banco ESEGUIBILE; prima punta 140107698001304340 @2.68 per 10.0 a pre-match, 44'06" al fischio
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107698001304340 @2.68 a pre-match, 44'06" al fischio, partita da CLIC (clic-1-1782832552415)

=== 35760084 [media-clic-due-clic] DIVERSO da R2 (riferimenti_cloud/scalper_35760084_blocco3.txt)
    @@ -21,4 +21,4 @@
    -      nota: ATTIVA ADESSO clic clic-1-1782835744399 (in gioco al 8'39"): letto dalla sessione in gioco al 8'43"; per il banco ESEGUIBILE; prima punta 140107609305279300 @2.58 per 10.0 a in gioco al 8'43"
    -      nota: ATTIVA ADESSO clic clic-2-1782836944399 (in gioco al 28'39"): letto dalla sessione in gioco al 29'11"; per il banco ESEGUIBILE; prima punta 140107609366066460 @3.3 per 10.0 a in gioco al 29'11"
    -      nota: ATTIVA ADESSO ciclo 1: prima punta 140107609305279300 @2.58 a in gioco al 8'43", partita da CLIC (clic-1-1782835744399)
    -      nota: ATTIVA ADESSO ciclo 2: prima punta 140107609366066460 @3.3 a in gioco al 29'11", partita da CLIC (clic-2-1782836944399)
    +      nota: ATTIVA ADESSO clic clic-1-1782835744399 (in gioco al 8'39"): letto dalla sessione in gioco al 8'43"; per il banco ESEGUIBILE; prima punta 140107698192907930 @2.58 per 10.0 a in gioco al 8'43"
    +      nota: ATTIVA ADESSO clic clic-2-1782836944399 (in gioco al 28'39"): letto dalla sessione in gioco al 29'11"; per il banco ESEGUIBILE; prima punta 140107698274413020 @3.3 per 10.0 a in gioco al 29'11"
    +      nota: ATTIVA ADESSO ciclo 1: prima punta 140107698192907930 @2.58 a in gioco al 8'43", partita da CLIC (clic-1-1782835744399)
    +      nota: ATTIVA ADESSO ciclo 2: prima punta 140107698274413020 @3.3 a in gioco al 29'11", partita da CLIC (clic-2-1782836944399)

```

## File

- `scalper_35797769_tutti.txt`: referto del passo 1 (55 scenari, senza coda: OOM).
- `scalper_35797769_rifiuti-betfair-codici-paper.txt`: referto del passo 1b.
- `scalper_35760084_tutti.txt`: referto del passo 2, completo.
- `confronta_referti.py`, `genera_tabella.py`, `confronto_*.txt`, `_tempi.txt`.
