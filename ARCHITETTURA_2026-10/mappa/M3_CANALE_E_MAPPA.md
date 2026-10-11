# M-3 - Registratore del canale locale e mappa dei flussi reali

Agente M-3 della mappatura dei flussi reali (11/10/2026), ramo `mappa/m3-canale` da
`a3a58ad8` (cima di MASTER). Permesso esplicito dell'utente per un registratore nuovo:
«Voglio che mappi qualsiasi cosa per poi fare la v2 al pari dei competitor».
Entra su MASTER solo dopo la firma del PC (par. 6).

Moduli:

- `Betfair/stream/registratore_canale.py` - il registratore (spento di serie);
- `Betfair/stream/mappa_flussi.py` - l'analisi di una giornata (referto Markdown + JSON);
- `Betfair/stream/tests/test_registratore_canale_2026_10_11.py` (14 test);
- `Betfair/stream/tests/test_mappa_flussi_2026_10_11.py` (7 test);
- `ARCHITETTURA_2026-10/mappa/misura_registratore_m3.py` - misura di costo e peso.

## 1. Che cosa registra

Un file per processo e per giorno: `<cartella>/<AAAA-MM-GG>/canale_<porta>.jsonl.gz`
(la porta identifica il processo: un processo, un canale - `start_channel`). Cartella di
serie `_logs/canale/` (gia' fuori da git). Un riavvio nello stesso giorno aggiunge un
membro gzip in coda allo stesso file (il `pid` nelle righe distingue le vite).
Data della cartella = data LOCALE del PC (rotazione a mezzanotte).

Una riga JSON per record, chiavi comuni: `v` (versione formato, 1), `k` (genere), `seq`
(sequenza di processo, assegnata PRIMA della coda: un buco = un record scartato),
`mono_ns` (orologio monotono), `epoca_ms`, `porta`, `sport`, `pid`.

| `k` | quando | campi propri | payload |
|---|---|---|---|
| `pub` | ogni giro di broadcast di `publish` (thread del loop) | `topic`, `byte` (testo JSON inviato), `dest` (client che lo ricevono), `saltati` (client oltre `_MAX_INVII_IN_VOLO` = 64 invii in volo), `client`, `lettori`, `n_topic` (contatore per porta e topic); `clienti` = composizione `[cliente, genere, chi]` di TUTTI i client collegati, solo quando l'insieme dei client cambia (e' il "chi riceve") | `msg` COMPLETO per `order`, `esiti`, `conto`, `conto_paper`, `modo_ordini` (`payload: "pieno"`); per tutti gli altri topic (ladder, board, board_mercato, now, scan_*, *_stato, account, ...) il 1o e poi 1 ogni N (`payload: "campione"`, N = `REGISTRA_CANALE_CAMPIONE`, di serie 20). I metadati SEMPRE. |
| `giro_saltato` | `publish` con NESSUN client pronto (giro saltato per intero) | `topic`, `client`, `lettori`, `in_volo` | - |
| `rx` | ogni messaggio ricevuto da un client (`_on_message`: `/order`, `snapshot`, `board_mercato`, sveglia, `/comando/<attore>`, messaggi dei lettori) | `cliente` (numero progressivo nel processo, mai dati del socket), `genere` (`desktop` / `lettore` / `comando`), `chi` (attore del comando o topic del lettore), `byte` | `msg` COMPLETO (ripulito) |
| `tx` | ogni risposta mirata: `respond` (esito dei comandi `/order`), `_send` (rifiuti immediati, sveglia, board_mercato), `invia` e `invia_attore` (ack ed eventi del motore ordini) | `cliente`, `genere`, `chi`, `byte`, `via` | `msg` COMPLETO (ripulito) |
| `stato` | ogni 30 s e alla chiusura, in ogni file aperto | `conti`: `scartati_coda`, `scartati_tetto`, `errori_disco`, `errori_aggancio`, `scritti`, `mascherati`, `giorni_rimossi`, `peso_cartella_byte`, `in_coda`, `seq_prossimo`; `campione`, `pieni`, `tetto_mb`, `coda_max` | - |
| `tetto_raggiunto` | oggi da solo supera il tetto: da qui la registrazione e' sospesa fino a domani | come `stato` | - |

**Niente dati sensibili.** Il token del canale viaggia nel percorso (`?t=`) e
nell'header `X-Canale-Token`: il registratore non legge mai ne' percorso ne' header.
Nei payload ogni chiave che somiglia a una credenziale (`token`, `passw`, `secret`,
`app_key`, `session`, `ssoid`, `cookie`, `authoriz`, `cert`, `credenzial`, `api_key`)
viene scritta `"***"`; il numero e' in `conti.mascherati`. Test: il token e una chiave
`session_token` non compaiono nei byte del file.

**Che cosa NON registra** (dichiarato, non nascosto):

- i `publish` senza nessun client collegato o con soli lettori che non hanno chiesto
  quel topic: il canale esce prima di serializzare e prima dell'aggancio (un processo
  "tace" nella mappa quando la UI e' chiusa: e' il comportamento vero, non un buco);
- il `hello` inviato all'apertura e le aperture/chiusure delle connessioni come
  eventi a se': il numero di client e' in ogni riga `pub` (`client`, `lettori`) e la
  composizione nella prima riga `pub` dopo ogni cambio (una connessione aperta e chiusa
  senza nessun publish in mezzo non lascia traccia); il numero `cliente` e' per
  processo e, dopo una chiusura, puo' essere riusato da un socket nuovo (si basa su
  `id()`);
- l'istante del `publish` nel thread del chiamante: si registra l'istante del giro di
  broadcast nel thread del loop (la differenza e' l'attesa nel loop, sotto il ms a
  carico normale - vedi par. 3).

## 2. Come si accende, si spegne, si regola

| variabile | di serie | significato |
|---|---|---|
| `REGISTRA_CANALE` | `0` | `1` = acceso (qualunque altro valore, anche `true`, = spento) |
| `REGISTRA_CANALE_DIR` | `_logs/canale` | cartella base |
| `REGISTRA_CANALE_MB` | `1024` | tetto in MB dell'intera cartella (tutti i processi, tutti i giorni) |
| `REGISTRA_CANALE_GIORNI` | `7` | conservazione: giorni oltre questa eta' cancellati |
| `REGISTRA_CANALE_CAMPIONE` | `20` | 1 payload ogni N per i topic non pieni |

Si legge all'import di `local_channel` (cioe' all'avvio di ogni processo che ha un
canale): prima l'ambiente del processo, poi - se l'ambiente non nomina la variabile - il
file `.env` della radice, LETTO dal registratore e mai caricato nell'ambiente (alcuni
servizi importano il canale prima del loro `load_dotenv`; caricarlo qui cambierebbe
l'ambiente del processo). Per accenderlo l'utente scrive `REGISTRA_CANALE=1` nel `.env`
della radice (o nell'ambiente con cui l'app avvia i processi) e riavvia l'app; per
spegnerlo lo toglie (o `0`) e riavvia. Le altre variabili seguono la stessa regola. Spento anche se: gira pytest; nel
processo e' caricato il banco (`Betfair.stream.backtest*`, controllato all'accensione e
di nuovo al primo record, quando parte il thread).

A registratore spento: ogni aggancio e' un `if _reg.ATTIVO` falso, nessun file, nessun
thread. A registratore acceso: UN thread demone per processo (`registratore-canale`),
che parte al primo record. Nessuna connessione, nessun processo nuovo.

Tetto e conservazione (ogni 30 s, nel thread): si tolgono i giorni piu' vecchi della
conservazione, poi, finche' il peso supera il tetto, il giorno piu' vecchio - MAI oggi,
e solo i file `canale_*.jsonl.gz` (un file estraneo nella cartella resta). Se oggi da
solo supera il tetto, riga `tetto_raggiunto` e scrittura sospesa fino a mezzanotte
(i record si contano in `scartati_tetto`).

## 3. Costo e peso (misurati qui, NON sul PC)

Macchina di sviluppo condivisa (Linux, Python 3.13), quindi numeri indicativi: sul PC
vanno rifatti (par. 6, punto 6).

**Percorso caldo.** L'aggancio non scrive su disco e non prende lucchetti: una tupla di
riferimenti (il testo JSON gia' serializzato dal canale, immutabile) in una `deque` con
tetto `CODA_MAX = 20000`; piena = si scarta e si conta. Il thread del chiamante di
`publish` paga solo il controllo `if _reg.ATTIVO`: il conteggio dei destinatari avviene
nel giro di broadcast, nel thread del loop.

| misura | spento | acceso |
|---|---|---|
| `publish` + giro di broadcast, ladder realistico (3 runner x 10 livelli), loop finto, mediana di 4 serie alternate da 500 msg (`test_costo_per_messaggio_col_registratore_acceso`, 5 esecuzioni) | 43,7-58,4 us/msg | 48,7-62,5 us/msg (differenza tipica +5 us) |
| aggancio `pubblicato` da solo | - | 2,1-3,8 us/msg |
| canale SENZA agganci (sorgente con gli agganci tolti) contro canale con agganci SPENTI, migliore di 6 giri alternati (`test_spento_identico_al_canale_senza_agganci`, tolleranza dichiarata: 5 us o 10 %, il maggiore; 5 esecuzioni) | 43,6-46,9 us/msg (senza agganci) | differenza fra -1,2 e +0,5 us |
| scrittura nel thread (json, ripulitura, gzip), per record, campione 1/20 | - | 17,7-22,0 us/record |
| server ws VERO, 500 ladder/s (10 mercati x 50/s, caso peggiore) per 10 s x 2 giri alternati, `misura_registratore_m3.py`: `publish` p50 / p99 nel chiamante | 194 / 476 us | 190 / 432 us |
| idem: latenza publish -> ricezione nel client p50 / p95 / p99 | 0,77 / 1,23 / 3,59 ms | 0,73 / 1,30 / 3,35 ms |
| idem: CPU del processo | 38,7 % | 38,8 % |
| server ws VERO, 50 ladder/s (10 mercati al tetto del canale di 200 ms): `publish` p50, latenza p50 / p99, CPU | 293 us, 1,22 / 3,06 ms, 8,1 % | 294 us, 1,19 / 3,24 ms, 8,3 % |

Messaggi ricevuti dal client identici nelle due fasi (5012 su 5012); nessuno scarto,
nessun errore. Le differenze fra spento e acceso sono dentro il rumore della macchina
(stesse grandezze con segno alterno fra i giri).

**Peso su disco** (gzip, campione 1/20, ladder realistico):

- 500 msg/s: 9,3 KB/s = 32,5 MB/ora = 781 MB per 24 h di carico pieno (caso peggiore);
- 50 msg/s: 1,0 KB/s = 3,6 MB/ora = 87 MB per 24 h di carico pieno.

Stima per una giornata vera: il ladder e' write-on-change con tetto di 200 ms per
mercato, la UI e' aperta qualche ora; con 10-20 mercati seguiti per 8-12 ore piu' board,
scanner (47336) e bot: **circa 50-300 MB al giorno** per tutta l'app. Il tetto di serie
(1 GB, 7 giorni) basta; se il primo giorno pesa di piu', si alza
`REGISTRA_CANALE_CAMPIONE` (100 = circa un quinto del peso dei payload) prima di toccare
il tetto. Memoria nel caso peggiore (thread fermo, coda piena): 20000 tuple (~200 B) piu'
i testi tenuti (1/20 dei non pieni, tutti i pieni): qualche decina di MB.

## 4. Punti toccati (file:riga)

Unico file di produzione toccato: `Betfair/stream/local_channel.py`, 15 righe aggiunte,
nessuna tolta o cambiata. Ogni aggancio e' la coppia `if _reg.ATTIVO:` + chiamata.

| riga | dove | aggancio |
|---|---|---|
| 35 | import | `from . import registratore_canale as _reg` |
| 405-406 | `_on_message` (ricezione comandi, thread del loop), prima riga | `_reg.ricevuto(self, ws, raw)` |
| 562-563 | `_send`, dopo la serializzazione | `_reg.risposta(self, ws, text, "send")` |
| 621-622 | `invia`, dopo la serializzazione | `_reg.risposta(self, ws, text, "invia")` |
| 643-644 | `invia_attore`, dopo la serializzazione | `_reg.risposta_attore(self, attore, text)` |
| 697-698 | `publish`, ramo "nessun client pronto" | `_reg.giro_saltato(self, topic)` |
| 713-714 | `publish` -> `_broadcast` (thread del loop), prima del ciclo di invio | `_reg.pubblicato(self, topic, text)` |
| 755-756 | `respond`, dopo la serializzazione | `_reg.risposta(self, req.ws, text, "respond")` |

Il test `test_spento_identico_al_canale_senza_agganci` ricostruisce il canale togliendo
dal sorgente l'import e le 7 coppie e conta le coppie (`AGGANCI_DICHIARATI = 7`): un
aggancio nuovo non dichiarato fa diventare rosso il test.

Divergenza dal brief, da portare al coordinatore: il brief parlava di «UNA riga in
publish e nella ricezione dei comandi». Per avere l'ESITO dei comandi (richiesto dalla
mappa) servono anche le risposte: `respond`, `_send`, `invia`, `invia_attore`. Sono
4 agganci in piu', dello stesso stampo; si possono togliere senza toccare il resto (la
mappa allora dichiara "senza esito" per ogni comando).

Non toccati: stream ordini e REST (M-1), sonde di `Betfair/monitor` (M-2), bot,
frontend, DB, migrazioni.

## 5. Prove (PSB par. 6.7, 6.8; par. 7 n. 27, 29, 30, 35)

Test nuovi (20, verdi): server ws VERO su 127.0.0.1 e client `websockets` VERI per
spento/acceso/identita'; loop e ws finti con le chiavi del vero (stesso schema dei test
di D4 esistenti) per contropressione, coda e disco; raw VERO di
`registrazioni_banco/35760084` (sola lettura) per la mappa; righe di Salute costruite con
`costruisci_riga` vero.

| richiesta | test |
|---|---|
| interruttore | `test_interruttore_dal_file_env_letto_e_mai_caricato` (`.env` letto e mai caricato, l'ambiente vince) |
| spento = nessun file e publish identico | `test_spento_nessun_aggancio_nessun_file_e_stessi_messaggi` (spie: zero chiamate; nessun file; messaggi identici a quelli del giro acceso); `test_spento_identico_al_canale_senza_agganci` (stessi messaggi del canale SENZA agganci e costo entro 5 us/msg); `test_interruttore_dall_ambiente_in_un_processo_vero` (assente / `0` / `true` = spento, `1` = acceso, banco prima o dopo = spento) |
| acceso = file corretto | `test_acceso_file_corretto` (metadati di ogni publish, pieni e campione 1/21/41, dest e saltati, comandi e risposte, sequenza 1..n, token assente, mascheratura); `test_acceso_col_thread_vero_scrive_e_si_ferma` |
| coda piena = scarta e conta, mai blocca | `test_coda_piena_scarta_conta_e_non_blocca` (coda da 10, 1000 publish in un thread con scadenza, 990 scartati, consegne del canale intatte) |
| errore del disco mai propagato | `test_errore_del_disco_mai_propagato` (permessi, disco pieno in scrittura e flush, aggancio che esplode: il canale consegna lo stesso); `test_thread_vero_con_disco_rotto_non_muore` |
| rotazione e tetto | `test_conservazione_e_tetto`; `test_rotazione_a_mezzanotte_e_sospensione_al_tetto`; `test_file_troncato_si_legge_fino_al_troncamento` |
| client saltati | `test_client_saltati_e_giro_saltato_registrati` (record = `statistiche()["saltati_client"]` del canale) |
| costo | `test_costo_per_messaggio_col_registratore_acceso` (stampa i numeri; tetto largo 100 us) |
| mappa | `test_canale_numeri_esatti`, `test_buchi_della_sequenza_e_file_troncato`, `test_fonti_mancanti_dichiarate`, `test_raw_vero_del_banco`, `test_salute_e_ordini_m1`, `test_referto_riproducibile_e_cli`, `test_percentile_a_rango` |

Nella suite intera il banco (`Betfair.stream.backtest`) e' gia' caricato da altri test,
quindi il registratore - correttamente - rifiuta di accendersi: la prima suite intera ha
dato 12 rossi, tutti nei test nuovi, per questo motivo. I test in-processo sostituiscono
`nel_banco` con `False` (fixture), il controllo VERO del banco resta provato in un
processo Python a parte (`test_interruttore_dall_ambiente_in_un_processo_vero`, banco
prima e dopo l'import; mutazione M13 rossa). Verificato anche con
`python -m pytest -p Betfair.stream.backtest <i due file>`: 21 verdi.

**Falsificazione** (23 mutazioni, una alla volta sul codice corretto, file ripristinato
dopo ognuna): tutte ROSSE.

| mutazione | rosso in |
|---|---|
| M1 aggancio di publish senza interruttore | spento |
| M2 aggancio di `respond` tolto | acceso |
| M3 regola dei saltati sbagliata nel registratore | client saltati |
| M4 coda che ASPETTA invece di scartare | coda piena (scadenza) |
| M5 scarto non contato | coda piena |
| M6 errore del disco propagato | errore del disco |
| M7 tetto che cancella anche oggi | conservazione e tetto |
| M8 campione mai salvato | acceso |
| M9 niente mascheratura | acceso |
| M10 niente rotazione a mezzanotte | rotazione |
| M11 niente sospensione al tetto | rotazione e sospensione |
| M12 interruttore acceso con qualunque valore | processo vero |
| M13 banco non controllato al primo record | processo vero |
| M14 mappa: ack del motore letto come `ok` | numeri esatti |
| M15 mappa: scarti in coda alla sequenza ignorati | buchi |
| M16 mappa: percentile spostato di un rango | percentile |
| M17 mappa: raw senza filtro del giorno | raw vero |
| M18 mappa: fonte mancante non dichiarata | fonti mancanti |
| M19 mappa: esito attribuito al comando di un altro client (stesso id) | numeri esatti |
| M20 interruttore che costa anche da spento (`if _reg.ATTIVO or <lavoro>`) | identita' col canale senza agganci (tempi) |
| M21 `.env` ignorato | interruttore dal file |
| M22 composizione dei client mai scritta | acceso |
| M23 mappa: composizione ignorata | numeri esatti |

M19 era VERDE al primo giro: il test non esponeva due client con lo stesso id. Si e'
aggiunto il caso (`intruso` manda `id 7` come `desk`) e ora e' rosso. Anche una prima
M20 (lavoro aggiunto in `publish` FUORI dagli agganci) era verde, ed e' giusto: il
confronto dei tempi certifica il costo degli agganci spenti, non il resto del canale,
che e' identico nei due lati. La M20 mirata all'interruttore e' rossa.

## 6. Checklist di firma per il PC

Da eseguire sul PC dell'utente, in quest'ordine, da chi firma (non dal delegato):

1. **Diff.** `git fetch` e `git diff a3a58ad8..mappa/m3-canale --stat`: devono esserci
   SOLO `Betfair/stream/local_channel.py` (+15 righe, nessuna tolta),
   `Betfair/stream/registratore_canale.py`, `Betfair/stream/mappa_flussi.py`, i due test,
   `ARCHITETTURA_2026-10/mappa/`. Rileggere le 7 coppie del par. 4 in
   `git diff a3a58ad8..mappa/m3-canale -- Betfair/stream/local_channel.py`.
2. **Test nuovi.** `python -m pytest Betfair/stream/tests/test_registratore_canale_2026_10_11.py Betfair/stream/tests/test_mappa_flussi_2026_10_11.py -q -p no:cacheprovider -s`
   (con `-s` stampa le due righe `[M3 costo]` e `[M3 spento]`: annotarle).
3. **Mutazioni.** Rifarne almeno tre a mano (M1, M4, M6 del par. 5): ognuna rossa,
   poi `git checkout -- <file>`.
4. **Suite intera**, una volta: `python -m pytest Betfair/ -q -p no:cacheprovider`, 0 rossi.
5. **Giro paper con registratore SPENTO** (come oggi: nessuna `REGISTRA_CANALE` ne'
   nell'ambiente ne' nel `.env`): app avviata
   dall'utente, ladder e un ordine paper dal ladder. Verificare: nessuna cartella
   `_logs/canale/<oggi>`, nessun thread `registratore-canale`, ordine paper come sempre.
6. **Giro paper con registratore ACCESO**: `REGISTRA_CANALE=1` nel `.env` della radice,
   riavvio dell'app da parte dell'utente, STESSO giro del punto 5. Verificare: stessa
   UI, stessi tempi percepiti, stesso esito dell'ordine; nascono
   `_logs/canale/<oggi>/canale_47331.jsonl.gz` (e gli altri processi accesi); poi
   `python ARCHITETTURA_2026-10/mappa/misura_registratore_m3.py --secondi 10 --giri 2 --cartella <cartella usa e getta>`
   (NON tocca l'app: canale suo su porta libera) per i numeri del PC.
7. **Mappa di prova** del giro acceso:
   `python -m Betfair.stream.mappa_flussi --giorno <oggi> --uscita ARCHITETTURA_2026-10/mappa/MAPPA_<oggi>.md`:
   deve elencare 47331 con `ladder`/`order`/`conto`, il comando dell'ordine paper con il
   suo esito, nessun `errori_disco`, `scartati_coda` = 0, e dire cosa manca.
8. **Peso dopo un giorno**: dimensione di `_logs/canale/<giorno>` contro la stima del
   par. 3; se supera 300 MB, alzare `REGISTRA_CANALE_CAMPIONE` (non il tetto).
9. Firma: chi ha rieseguito, data, numeri dei punti 2, 6, 8.

Divergenze da dire all'utente prima dell'accensione: registra comandi e ordini (prezzi,
stake, bet_id) in chiaro su disco locale per 7 giorni - nessuna credenziale.

## 7. Come si genera la mappa dopo la giornata

Dalla radice del repository, il giorno dopo (sola lettura, nessun DB):

```
python -m Betfair.stream.mappa_flussi --giorno 2026-10-12 \
    --canale _logs/canale --raw _live_raw --salute _logs/monitor \
    --ordini <cartella dei file di M-1> \
    --uscita ARCHITETTURA_2026-10/mappa/MAPPA_2026-10-12.md --json _logs/mappa_2026-10-12.json
```

`--canale`, `--raw`, `--salute` hanno questi valori di serie; `--ordini` non ne ha. Una
fonte assente non ferma la mappa: la sezione dice `Non disponibile: <motivo>` e il par. 0
la elenca con `MANCA:`. Stessi file = stessi byte (nessun "adesso" nel testo).

Contenuto: 0. fonti lette e mancanti; 1.0 chi e' collegato per porta (desktop,
lettori con i loro topic, attori di comando; quanti insieme al massimo, da quando);
1. canale - per porta e topic: messaggi, msg/s,
byte/s, cadenza p50/p95/p99 (ms fra publish consecutivi, orologio monotono),
destinatari, client e lettori, payload tenuti, saltati; 1.1 client saltati e giri saltati;
1.2 comandi ricevuti per porta, genere di client e metodo con ok / rifiutati / senza
esito, latenza ricezione -> risposta p50/p95/max e motivi di rifiuto; 2. raw dei prezzi
per evento: messaggi, heartbeat, byte/s, cadenza sul `pt`, eta' `rx - pt` (se il monitor
l'ha scritta), buchi > 15 s, marcatori del `.recmeta`; 3. Salute per servizio: righe,
CPU, RSS, richieste DB e REST, buchi > 2 finestre; 4. file di M-1; 5. buchi: sequenze
mancanti, scarti, errori del disco, tetto, silenzi > 60 s, riavvii, file troncati,
buchi del raw, di Salute e di M-1, fonti mancanti.

**Interfaccia per M-1** (stream ordini e REST): una cartella passata con `--ordini`;
dentro `<giorno>/` (oppure direttamente) file `*.jsonl` o `*.jsonl.gz`, una riga JSON per
evento con un istante in ms (prima chiave presente fra `epoca_ms`, `ts_ms`, `epoch_ms`,
`rx`, `pt`; oppure `ts` ISO 8601) e un genere (prima chiave fra `k`, `tipo`, `kind`, `op`,
`evento`). Il riassunto e' per file e genere: conteggio, cadenza p50/p95/p99/max, buchi
> 60 s, righe senza istante. Un'analisi specifica (latenze place -> ack, abbinamenti) si
aggiunge in `mappa_flussi.analizza_ordini` quando il formato di M-1 e' fissato.

## 8. Cosa non si e' potuto verificare qui

- Il PC dell'utente (Windows): gzip in append, data locale, `desktop/main.js` che
  passa `REGISTRA_CANALE` ai processi, peso e costo veri: punti 5-8 del par. 6.
- Una giornata vera: la stima del peso (50-300 MB) e' da confermare.
- Il carico reale del GIL: la scrittura (json, gzip) gira in un thread dello stesso
  processo; misurata a 500 msg/s senza differenze di CPU o latenza oltre il rumore, ma
  il processo vero (runner calcio con flumine) ha altri thread.
- I file di M-1 non esistono ancora: l'interfaccia e' generica e provata con un file
  costruito nel test.
