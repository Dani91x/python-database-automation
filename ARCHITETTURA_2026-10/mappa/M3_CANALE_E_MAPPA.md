# M-3 - Registratore del canale locale e mappa dei flussi reali

Agente M-3 della mappatura dei flussi reali (11/10/2026), ramo `mappa/m3-canale` da
`a3a58ad8` (cima di MASTER). Permesso esplicito dell'utente per un registratore nuovo:
«Voglio che mappi qualsiasi cosa per poi fare la v2 al pari dei competitor».
Entra su MASTER solo dopo la firma del PC (par. 7).

Commit: `3625838b` (prima versione) e, sopra, la correzione dopo la revisione
indipendente (par. 6). Storia non riscritta.

Moduli:

- `Betfair/stream/registratore_canale.py` - il registratore (spento di serie);
- `Betfair/stream/gz_tollerante.py` - lettura tollerante dei `.jsonl.gz` (coda tronca,
  membri corrotti, membri accodati dopo un flusso tronco);
- `Betfair/stream/mappa_flussi.py` - l'analisi di una giornata (referto Markdown + JSON);
- `Betfair/stream/tests/test_registratore_canale_2026_10_11.py` (24 test);
- `Betfair/stream/tests/test_mappa_flussi_2026_10_11.py` (10 test, uno con due varianti);
- `ARCHITETTURA_2026-10/mappa/misura_registratore_m3.py` - costo e peso col ladder;
- `ARCHITETTURA_2026-10/mappa/banco_carico_m3.py` - il banco di carico della revisione
  (3 client, sonda del loop ogni 5 ms, payload pieni da 20 KB);
- `ARCHITETTURA_2026-10/mappa/m3_mutazioni.py` - la falsificazione (46 mutazioni).

## 1. Che cosa registra

Un file per PROCESSO e per giorno: `<cartella>/<AAAA-MM-GG>/canale_<porta>_<pid>.jsonl.gz`,
creato in esclusiva (`xb`). MAI un append su un file esistente: un pid riusato (Windows),
la riapertura dopo un errore del disco o un secondo canale nello stesso processo prendono
il primo suffisso libero (`_2`, `_3`, ...). Cartella di serie `_logs/canale/` (fuori da
git). Data della cartella = data LOCALE del PC (rotazione a mezzanotte). Formato `v` = 2.

Una riga JSON per record, chiavi comuni: `v`, `k` (genere), `seq` (sequenza di processo,
assegnata PRIMA della coda: un buco = un record scartato), `mono_ns` (orologio monotono),
`epoca_ms`, `porta`, `sport`, `pid`, `av` (istante d'avvio del registratore nel processo:
`porta`+`pid`+`av` = una VITA di processo, anche con un pid riusato).

| `k` | quando | campi propri | payload |
|---|---|---|---|
| `pub` | ogni giro di broadcast di `publish` (thread del loop) | `topic`, `byte` (testo inviato), `dest` (client che lo ricevono), `saltati` (client OLTRE `_MAX_INVII_IN_VOLO` = 64 invii in volo, stessa regola del canale), `client`, `lettori`, `n_topic`; `clienti` = composizione `[cliente, genere, chi]` di tutte le connessioni, solo quando l'insieme delle connessioni cambia (apertura, chiusura, ricollegamento: e' il "chi riceve") | `msg` COMPLETO per `order`, `esiti`, `conto`, `conto_paper`, `modo_ordini` (`payload: "pieno"`); per gli altri topic il 1o e poi 1 ogni N (`payload: "campione"`, N = `REGISTRA_CANALE_CAMPIONE`, di serie 20) |
| `giro_saltato` | `publish` con NESSUN client pronto | `topic`, `client`, `lettori`, `in_volo` | - |
| `rx` | ogni messaggio ricevuto da un client (`_on_message`) | `cliente`, `genere` (`desktop` / `lettore` / `comando`), `chi` (attore o topic del lettore), `byte` | `msg` COMPLETO (mascherato); `txt` se non e' un oggetto JSON |
| `tx` | ogni risposta mirata: `respond`, `_send`, `invia`, `invia_attore` | `cliente`, `genere`, `chi`, `byte`, `via` | `msg` COMPLETO (mascherato) |
| `stato` | ogni 30 s | `conti` (sotto), `campione`, `pieni`, `tetto_mb`, `coda_max`, `coda_max_byte` | - |
| `chiusura` | fine del processo (`atexit`), `spegni`, rotazione di mezzanotte | come `stato` | - |
| `tetto_raggiunto` | oggi da solo supera il tetto: scrittura sospesa fino a domani | come `stato` | - |

`conti`: `scartati_coda`, `scartati_tetto`, `errori_disco`, `errori_aggancio`, `scritti`,
`mascherati`, `giorni_rimossi`, `peso_cartella_byte`, `byte_in_coda`, `in_coda`,
`seq_prossimo`. I contatori stanno sotto un lucchetto tenuto per qualche istruzione.

**Payload VERBATIM.** Il `msg` di `pub` e `tx` e' il testo JSON che il canale ha gia'
serializzato per i client, copiato cosi' com'e' (stessi separatori): il thread di
scrittura non fa mai `json.loads`/`json.dumps` dei payload del canale. Solo i messaggi
ricevuti da un client (`rx`, rari e piccoli) si controllano con `json.loads`.

**Numero del client.** Assegnato alla CONNESSIONE alla prima vista (`WeakKeyDictionary`
sul socket) e mai riusato nel processo: una connessione nuova ha sempre un numero nuovo,
anche se Python riusa l'`id` di un socket chiuso.

**Niente dati sensibili.** Il token del canale viaggia nel percorso (`?t=`) e
nell'header `X-Canale-Token`: il registratore non legge mai ne' percorso ne' header. Nei
payload si sostituiscono con `"***"` i valori delle chiavi ESATTE (maiuscole
indifferenti), a qualunque profondita' e dentro le liste: `key`, `x-authentication`,
`x-application`, `token`, `session_token`, `sessiontoken`, `password`, `passwd`,
`authorization`, `app_key`, `appkey`, `api_key`, `apikey`, `ssoid`, `cookie`, `secret`,
`client_secret`; e `t`, `tk` quando il valore e' un testo di almeno 16 caratteri (`t` e'
anche il campo del protocollo: `{"t": "ladder"}` resta). NON si mascherano `sessione`,
`sessioni`, `certified`, `incertezza_ms`, `keys`, `token_scadenza`. La mascheratura e'
SUL TESTO (ricerca di sottostringhe, poi regex solo se serve; ripiego su `json` solo se
una chiave sensibile ha per valore un oggetto o una lista). Conto in `conti.mascherati`.

**Che cosa NON registra** (dichiarato):

- i `publish` senza NESSUN client collegato, o con soli lettori che non hanno chiesto quel
  topic: il canale esce prima di serializzare e prima di ogni aggancio
  (`local_channel.py:688-693`). Contarli richiederebbe un aggancio nuovo nel percorso
  caldo; non serve alla mappa (con la UI chiusa il processo "tace" ed e' il
  comportamento vero), quindi NON si conta: dichiarato, non nascosto. Si conta invece il
  giro saltato perche' nessun client era pronto (`giro_saltato`);
- il `hello` e le aperture/chiusure come eventi: il numero di client e' in ogni `pub` e la
  composizione nel primo `pub` dopo ogni cambio (una connessione aperta e chiusa senza
  nessun publish in mezzo non lascia traccia);
- l'istante del `publish` nel thread del chiamante: si registra quello del giro di
  broadcast nel thread del loop.

## 2. Come si accende, si spegne, si regola

| variabile | di serie | significato |
|---|---|---|
| `REGISTRA_CANALE` | `0` | `1` = acceso (qualunque altro valore, anche `true`, = spento) |
| `REGISTRA_CANALE_DIR` | `_logs/canale` | cartella base |
| `REGISTRA_CANALE_MB` | `1024` | tetto in MB dell'intera cartella |
| `REGISTRA_CANALE_GIORNI` | `7` | conservazione in giorni |
| `REGISTRA_CANALE_CAMPIONE` | `20` | 1 payload ogni N per i topic non pieni |

Si legge all'import di `local_channel` (all'avvio di ogni processo che ha un canale):
prima l'ambiente, poi - se l'ambiente non nomina la variabile - il `.env` della radice,
LETTO e mai caricato nell'ambiente. Per accenderlo l'utente scrive `REGISTRA_CANALE=1` nel
`.env` (o nell'ambiente dell'app) e riavvia l'app; per spegnerlo lo toglie e riavvia.
Spento anche se: gira pytest; nel processo e' caricato il banco (`Betfair.stream.backtest*`,
controllato all'accensione e di nuovo al primo record).

Acceso: UN thread demone per processo (`registratore-canale`) che parte al primo record;
nessuna connessione, nessun processo nuovo. Coda limitata in record (`CODA_MAX` = 20000)
e in byte (`CODA_MAX_BYTE` = 32 MB): piena = si scarta e si conta, mai si aspetta. Il
thread cede il GIL (`time.sleep(0)`) ogni 32 KB composti o scritti: senza, i thread del
loop e dei bot aspetterebbero fino all'intervallo di cambio dell'interprete (5 ms).

Fine processo: `atexit` ferma il thread con un'attesa MASSIMA di 2 s (l'uscita non si
appende mai al registratore): ultimo giro, riga `chiusura`, gzip chiuso. Un processo
ucciso (kill -9, crash) lascia una coda tronca, che i lettori tollerano. `fork`: nel
figlio il registratore e' chiuso e i file ereditati sono dirottati su `devnull`
(`os.register_at_fork`), cosi' il figlio non scrive mai nel gzip del padre.

Tetto e conservazione (ogni 30 s, in ogni processo): via i giorni oltre la conservazione,
poi il giorno piu' vecchio finche' il peso supera il tetto - MAI oggi, e solo i file
`canale_*.jsonl.gz`. Se oggi da solo supera il tetto: `tetto_raggiunto` e scrittura
sospesa fino a mezzanotte. Con un file per processo il controllo e' fatto da ogni
processo per conto suo: fra processi il tetto e' BEST-EFFORT (lo si puo' sforare di
quanto i processi scrivono in 30 s).

## 3. Costo e peso (misurati qui, NON sul PC)

Macchina di sviluppo condivisa (Linux, Python 3.13): numeri indicativi, da rifare sul PC.

**Banco di carico della revisione** (`banco_carico_m3.py --secondi 15 --giri 3
--al-secondo 100 --kb 20 --anche-vecchio`): server ws vero, 3 client, sonda nel loop del
canale ogni 5 ms, 100 publish `order` al secondo da ~20 KB (payload PIENI, scritti per
intero). Ritardo del loop (mediana dei 3 giri; fra parentesi il peggiore):

| | p50 | p99 | max | CPU |
|---|---|---|---|---|
| spento | 0,46 ms | 2,67 ms (2,71) | 12,7 ms (17,1) | 27,5 % |
| acceso (questa versione) | 0,46 ms | 3,45 ms (4,08) | 20,6 ms (21,8) | 32,1 % |
| vecchio (`3625838b`: loads + ripulitura + dumps) | 0,56 ms | 55,95 ms (57,54) | 125,6 ms (637,7) | 53,4 % |

Consegne identiche (1500 su 1500 a ognuno dei 3 client), nessuno scarto. Un giro
precedente, prima del cedimento del GIL ogni 32 KB, dava 3,31 contro 3,63 ms di p99
(acceso sotto lo spento): fra spento e acceso la differenza resta nel rumore della
macchina (+0,8 ms di p99 nel giro sopra); il vecchio la moltiplicava per venti.

**Ladder** (`misura_registratore_m3.py --secondi 10 --giri 2`, 500 ladder/s, campione 1/20):

| | spento | acceso |
|---|---|---|
| `publish` p50 / p99 nel chiamante | 168 / 394 us | 165 / 400 us |
| latenza publish -> client p50 / p95 / p99 | 0,66 / 0,99 / 2,82 ms | 0,68 / 1,17 / 3,58 ms |
| CPU del processo | 33,3 % | 35,3 % |

**Test** (loop finto, 500 messaggi, 3 esecuzioni): canale SENZA agganci contro agganci
SPENTI: differenza fra -0,44 e +1,75 us/msg (tolleranza dichiarata 5 us o 10 %);
aggancio `pubblicato` da solo 4,1-4,6 us/msg (nel thread del loop, non del chiamante);
scrittura 12,7-14,4 us/record.

**Peso su disco** (gzip, campione 1/20): 500 msg/s = 9,5 KB/s = 33 MB/ora = ~800 MB per
24 h di carico pieno (caso peggiore); 50 msg/s = ~1 KB/s = ~87 MB per 24 h. Giornata
vera stimata: 50-300 MB per tutta l'app, da confermare (se di piu', alzare
`REGISTRA_CANALE_CAMPIONE` prima del tetto).

## 4. Punti toccati (file:riga)

Unico file di produzione toccato: `Betfair/stream/local_channel.py`, 15 righe aggiunte
nel commit `3625838b`, nessuna tolta o cambiata; la correzione NON lo tocca (nessun
aggancio nuovo). Ogni aggancio e' la coppia `if _reg.ATTIVO:` + chiamata.

| riga | dove | aggancio |
|---|---|---|
| 35 | import | `from . import registratore_canale as _reg` |
| 405-406 | `_on_message`, prima riga | `_reg.ricevuto(self, ws, raw)` |
| 562-563 | `_send` | `_reg.risposta(self, ws, text, "send")` |
| 621-622 | `invia` | `_reg.risposta(self, ws, text, "invia")` |
| 643-644 | `invia_attore` | `_reg.risposta_attore(self, attore, text)` |
| 697-698 | `publish`, ramo "nessun client pronto" | `_reg.giro_saltato(self, topic)` |
| 713-714 | `publish` -> `_broadcast` (thread del loop) | `_reg.pubblicato(self, topic, text)` |
| 755-756 | `respond` | `_reg.risposta(self, req.ws, text, "respond")` |

`test_spento_identico_al_canale_senza_agganci` ricostruisce il canale togliendo dal
sorgente l'import e le 7 coppie e le conta (`AGGANCI_DICHIARATI = 7`).

Divergenza dal brief (gia' portata al coordinatore): oltre agli agganci in publish e nella
ricezione, 4 agganci sulle risposte (`respond`, `_send`, `invia`, `invia_attore`) per
l'ESITO dei comandi.

Non toccati: stream ordini e REST (M-1), sonde di `Betfair/monitor` (M-2), bot, frontend,
DB, migrazioni.

## 5. La mappa dopo la giornata

```
python -m Betfair.stream.mappa_flussi --giorno 2026-10-12 \
    --canale _logs/canale --raw _live_raw --salute _logs/monitor \
    --ordini <LIVE_STREAM_DATA_DIR>/_ordini \
    --uscita ARCHITETTURA_2026-10/mappa/MAPPA_2026-10-12.md --json _logs/mappa_2026-10-12.json
```

Sola lettura. Una fonte assente non ferma la mappa (`MANCA: <motivo>`). Stessi file =
stessi byte. Tutti i gzip si leggono TOLLERANTI (`gz_tollerante.py`): blocchi, membro dopo
membro; un membro rotto o senza coda si ridecomprime solo fino al primo membro INTERO che
lo segue (zlib, se gli si lascia, legge il membro accodato come seguito di quello tronco
e ne tira fuori testo plausibile ma falso), poi si riprende da li'; la coda tronca e i
membri corrotti si dicono nei buchi.

Contenuto: 0. fonti; 1.0 chi e' collegato (connessioni per porta e genere); 1. per porta e
topic: messaggi, msg/s, byte/s, cadenza p50/p95/p99 (ms fra publish consecutivi DELLO
STESSO PROCESSO), destinatari, client, lettori, payload tenuti, saltati; 1.1 client e
giri saltati; 1.2 comandi ricevuti per porta, client, metodo (`order:place`,
`comando:comando:place`, ...) e MODO (paper, live, `-`: righe separate, mai sommate), con
ok / rifiutati / senza esito, latenza ricezione -> risposta e motivi di rifiuto (esito =
prima risposta sulla STESSA connessione arrivata DOPO il comando e non gia' usata);
2. raw dei prezzi; 3. Salute; 4. M-1; 5. buchi (sequenze mancanti, scarti, errori del
disco, tetto, silenzi > 60 s, processi senza riga di chiusura, riavvii, file rovinati).

**File di M-1** (commit `3bb418fe` del ramo `mappa/m1-ordini`, letto e mai toccato):
`<LIVE_STREAM_DATA_DIR>/_ordini/<AAAAMMGG UTC>/ordini_<servizio>_<pid>[_n].jsonl.gz`,
righe `k` = `stream` (battiti e dati insieme, `pt` dentro `msg`), `rest`, `dec` (con
`mode`), `sub`, `avvio`, `chiusura`; `ep_us`/`mono_us` in microsecondi, nelle `rest` anche
`risposta_ep_us`/`risposta_mono_us`. La mappa risolve le cartelle UTC che coprono il
giorno LOCALE (Europe/Rome: due cartelle), glob ricorsivo `ordini_*.jsonl*`, tiene le
righe con `ep_us/1000` nel giorno locale. Riassunto per file e genere (`dec:paper` e
`dec:live` separati), durate delle REST per metodo e attore (`risposta_ep_us - ep_us`),
e 4.2 la latenza comando LIVE della UI sul canale -> risposta della REST del desktop
(accoppiamento per tempo entro 5 s, mai una REST usata due volte, il paper escluso).
Se nel processo c'e' il lettore di M-1 (`Betfair.monitor.analisi_ordini`: import
OPZIONALE) la mappa legge i file con il SUO `leggi_file` e allega il referto di
`analizza_giorni` sulle cartelle UTC intere (4.3); se non c'e' lo dice ("ordini: lettore
M-1 assente") e legge con il proprio lettore tollerante.

## 6. Revisione indipendente dell'11/10: che cosa e' cambiato

| punto | correzione | prova |
|---|---|---|
| 1 gz illeggibile dopo un riavvio, mappa in traceback, coda persa all'uscita | file per processo `canale_<porta>_<pid>[_n]` in `xb`, mai append; `atexit` con attesa massima 2 s e riga `chiusura`; `register_at_fork`; lettori tolleranti (`gz_tollerante`) | `test_due_processi_veri_in_sequenza_e_uno_ucciso_poi_la_mappa` (tre processi Python VERI sulla stessa porta: due escono, uno kill -9), `test_vecchio_difetto_membro_accodato_dopo_un_flusso_tronco`, `test_fork_il_figlio_non_scrive_mai_nel_file_del_padre` |
| 2 `--ordini` non leggeva i file veri di M-1 | formato M-1, due cartelle UTC, filtro sul giorno locale, `ep_us/1000`, `risposta_ep_us`, lettore di M-1 opzionale | `test_ordini_m1_scritti_dallo_scrittore_vero[m1|assente]` con lo Scrittore VERO di M-1 al commit `3bb418fe` (`git show`), `test_cartelle_utc_del_giorno_locale`, `test_comando_della_ui_verso_la_rest` |
| 3 GIL: p99 del loop da 1,8 a 27 ms | payload VERBATIM, mascheratura sul testo, tetto della coda in byte, cessione del GIL ogni 32 KB | `test_payload_pieni_scritti_senza_rileggerli`, `test_coda_limitata_anche_in_byte`; banco di carico par. 3 |
| 4 publish senza client | dichiarato (par. 1): nessun aggancio nuovo | - |
| 5 paper e live sommati | chiave dei comandi con azione e modo | `test_canale_numeri_esatti` (righe live, paper e `-` separate) |
| 6 numeri dei client riusati | numero per connessione, composizione a ogni ricollegamento, accoppiamento per connessione | `test_numeri_dei_client_per_connessione_mai_riusati`, casi di id riusato in `test_canale_numeri_esatti` |
| 7 chiavi sensibili | chiavi esatte, liste, `t`/`tk` lunghi | `test_chiavi_sensibili_esatte_anche_nelle_liste` |
| 8 `_stop` | rinominato `_fermo` | - |
| 9 contatori | sotto lucchetto; tetto fra processi best-effort dichiarato | - |

Mutazioni sopravvissute del revisore, ora ROSSE: R1 (token tolto), R3 (`_ripulisci`
senza liste), R5 (confine `>=`), R13 (guardia di pytest tolta), R7 (giorno UTC), MC
(primo candidato senza il tempo), ME (processi per sola porta), MH (cadenza che mescola i
processi). In tutto `m3_mutazioni.py` ha 46 mutazioni, tutte ROSSE, file ripristinati
identici (impronta controllata).

## 7. Checklist di firma per il PC

1. **Diff.** `git diff a3a58ad8..mappa/m3-canale --stat`: solo
   `Betfair/stream/local_channel.py` (+15 righe, nessuna tolta), i moduli nuovi
   `registratore_canale.py`, `gz_tollerante.py`, `mappa_flussi.py`, i due test,
   `ARCHITETTURA_2026-10/mappa/`. Rileggere le 7 coppie del par. 4.
2. **Test nuovi.** `python -m pytest Betfair/stream/tests/test_registratore_canale_2026_10_11.py Betfair/stream/tests/test_mappa_flussi_2026_10_11.py -q -p no:cacheprovider -s`
   (stampa `[M3 costo]` e `[M3 spento]`). Su Windows due test si saltano da soli (fork,
   fuso da ambiente): dichiarato.
3. **Mutazioni.** `python ARCHITETTURA_2026-10/mappa/m3_mutazioni.py`: tutte ROSSE e
   "file ripristinati identici: True" (circa 10 minuti).
4. **Suite intera**, una volta: `python -m pytest Betfair/ -q -p no:cacheprovider`, 0 rossi.
5. **Giro paper SPENTO** (nessuna `REGISTRA_CANALE` ne' nell'ambiente ne' nel `.env`):
   app avviata dall'utente, ladder e un ordine paper. Nessuna `_logs/canale/<oggi>`,
   nessun thread `registratore-canale`.
6. **Giro paper ACCESO**: `REGISTRA_CANALE=1` nel `.env`, riavvio dell'app da parte
   dell'utente, STESSO giro. Stessa UI, stessi tempi percepiti, stesso esito; nascono
   `_logs/canale/<oggi>/canale_47331_<pid>.jsonl.gz` e gli altri. Poi i due banchi (non
   toccano l'app): `misura_registratore_m3.py --secondi 10 --giri 2 --cartella <usa e getta>`
   e `banco_carico_m3.py --secondi 15 --giri 3 --cartella <usa e getta> --anche-vecchio`.
7. **Riavvio a meta' giornata**: chiudere e riaprire l'app una volta: due file per porta,
   entrambi con la riga `chiusura`; la mappa li legge entrambi e conta due processi.
8. **Mappa** del giro acceso: `python -m Betfair.stream.mappa_flussi --giorno <oggi>
   --ordini <LIVE_STREAM_DATA_DIR>/_ordini --uscita ARCHITETTURA_2026-10/mappa/MAPPA_<oggi>.md`.
9. **Peso dopo un giorno** contro la stima del par. 3.
10. Firma: chi ha rieseguito, data, numeri dei punti 2, 6, 9.

Da dire all'utente prima dell'accensione: registra comandi e ordini (prezzi, stake,
bet_id) in chiaro su disco locale per 7 giorni - nessuna credenziale.

## 8. Cosa non si e' potuto verificare qui

- Il PC Windows: gzip in `xb`, data locale, `atexit` all'uscita dei processi lanciati da
  `desktop/main.js` (se l'app li termina con un kill duro, niente riga `chiusura`: la
  mappa lo dice), costo e peso veri.
- Una giornata vera: la stima del peso.
- Il carico del GIL nel runner vero (flumine e i suoi thread): misurato solo col banco.
- Il lettore di M-1 importato davvero nel pacchetto: provato iniettando nel test il
  modulo del commit `3bb418fe`; dopo l'unione di M-1 su MASTER si usa da solo.
