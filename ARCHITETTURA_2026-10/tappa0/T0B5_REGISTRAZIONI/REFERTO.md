# T0B (5) - Registrazioni nel banco: tennis (U-44) e calcio COMPLETE per Mike (U-27)

Data: 09/10/2026. Delegato del coordinatore, worktree `pda-architettura` (ramo
`claude/architettura-tappa0`, HEAD `ee965e26`). Nessun commit, nessun replay, nessun codice
toccato, nessuna registrazione modificata. Sorgenti lette in sola lettura.

## 1. Cosa e' stato copiato

Compressione: gzip livello 9, `mtime=0` (copia deterministica). Tutto in `registrazioni_banco/`.

| evento | sport | file nel repo | byte |
|---|---|---|---|
| 35790089 | tennis | `35790089.raw.jsonl.gz`, `35790089.score.jsonl.gz` | 135.852 + 1.917 |
| 35794049 | tennis | `35794049.raw.jsonl.gz`, `35794049.score.jsonl.gz` | 210.436 + 3.169 |
| 35795993 | tennis | `35795993.raw.jsonl.gz`, `35795993.score.jsonl.gz` | 210.779 + 3.313 |
| 35797566 | tennis | `35797566.score.jsonl.gz` (da `20260707/`); `setbetting_20260707/35797566.raw.jsonl.gz`, `setbetting_20260707/35797566.score.jsonl.gz` | 504 + 2.546 + 504 |
| 35777617 | calcio | `.raw.jsonl.gz`, `.scores.jsonl.gz`, `.timeline.jsonl` | 3.243.204 + 6.546 + 1.769 |
| 35768365 | calcio | `.raw.jsonl.gz`, `.scores.jsonl.gz`, `.timeline.jsonl` | 3.522.375 + 6.578 + 2.104 |
| 35774000 | calcio | `.raw.jsonl.gz`, `.scores.jsonl.gz`, `.timeline.jsonl` | 1.212.698 + 4.762 + 2.154 |

Totale aggiunto: **8.571.210 byte** (tennis 569.020; calcio parte B 8.002.190, sotto il tetto di
10 MB). Piu' `LEGGIMI.md` riscritto (tabella, sha256, ricostruzione calcio+tennis, comandi).

### Il raw di 35797566 (Match Odds) NON esiste

Cercato in `~/Desktop/tennis_rec/` (tutte le sottocartelle) e in `_live_raw/` del checkout
principale: in `20260707/35797566/` c'e' solo `35797566.score.jsonl` (7.560 B). L'unico raw e'
`setbetting_20260707/35797566/35797566.raw.jsonl` (19.221 B, 62 righe, solo `SET_BETTING`, stato
sempre OPEN, validatore PARTIAL 6,8%). Copiati entrambi tali e quali, nelle loro cartelle.
Per i bot tennis (Match Odds) questa partita resta inutilizzabile: il banco risponde ERROR
"registrato solo il SET_BETTING", come gia' nel referto
`AUDIT_2026-10-08/applica_bot_tennis/certifica_dopo.txt`. Niente e' stato inventato.
Per U-44 (3-5 partite): le partite tennis UTILI sono 3 (35790089, 35794049, 35795993, di cui
35795993 PARTIAL); per avere 3 COMPLETE servono nuove giornate registrate.

## 2. Scelta delle registrazioni calcio per Mike (E1 D11)

### Cosa fa scattare i 7 stati mai visti (letto in `Betfair/mike/engine.py`, `service.py`, `config.py`)

| stato | condizione (default di `config.py`) | dipende dalla registrazione? |
|---|---|---|
| `LIVE_SECOND_ENTRY` | gol dopo il fischio mentre la banca del fischio (finestra `ko_green_window_s` = 180 s) non e' abbinata, `second_entry_enabled` (engine.py:4108-4121) | SI': gol nei primi 3 minuti |
| `REENTRY_PENDING/OPEN/GREEN_PENDING` | da `FLAT` (es. verde al fischio, `reentry_allowed`), 1..2 gol (`reentry_max_goals`), entro il 45' (`reentry_until_min`), U4.5 aperto e quota U4.5 > ingresso iniziale, liquidita' (engine.py:5160-5283) | SI': verde al fischio + gol prima del 45' |
| `PRE_LAST_ENTRY_PENDING` | verde FINALE pre-partita abbinata a KO-10' (`_after_final_green`, engine.py:3785, 3848-3895) | SI', ma dal movimento dei prezzi pre-partita: non stimabile senza replay |
| `SKIPPED` | solo su comando dell'utente "salta partita" (`service.py:4014`) | NO: nessuna registrazione lo produce |
| `ERROR` | stato sconosciuto nel `_dispatch` (engine.py:3480, 3806) | NO: nessuna registrazione lo produce |

### Dati delle candidate

Validatore lanciato sul checkout principale (sola lettura): 84 cartelle, 64 righe JSON:
13 COMPLETE, 26 PARTIAL, 24 NO_RAW, 1 UNKNOWN. Fonti dell'analisi: `marketDefinition` del raw
(ora del KO, CLOSED per mercato), sidecar `scores.jsonl` (fonte `betfair`: il punteggio come lo
vede Mike), `timeline.jsonl`. "U3.5 primi 180 s" = last traded price dell'Under 3.5 all'ultimo
valore pre-KO -> minimo nei primi 180 s dal passaggio in gioco (stima del verde al fischio a 2 tick).

| evento | partita (data) | ris. | gol veri (feed betfair) | gol annullati nel feed | pre-match registrato | U3.5 primi 180 s | MB raw | stati D11 attesi |
|---|---|---|---|---|---|---|---|---|
| **35777617** | Brazil - Norway, World Cup (05/07) | 1-2 | 79', 89', 99' | **2' (0-1 alle 20:03:04, 0-0 alle 20:03:49)** | 23' | 1,49 -> 1,45 | 18,8 | `LIVE_SECOND_ENTRY` (gol dentro la finestra di 180 s, poi annullato) oppure, se il verde al fischio e' gia' abbinato, `FLAT` -> re-ingresso |
| **35768365** | Spain - Austria, World Cup (02/07) | 3-0 | 35', 65', 88' | **28' (1-0 alle 19:29:03, 0-0 alle 19:30:01)** | 106' | 1,50 -> 1,46 | 20,5 | `REENTRY_*` (verde al fischio probabile, gol prima del 45'); pre-match piu' lungo delle tre per `PRE_LAST_ENTRY_PENDING` |
| **35774000** | Taborsko - SKU Amstetten, amichevole (30/06) | 0-3 | 15', 80', 87' | nessuno nel feed (la timeline ha un doppione al 16') | 39' | 1,55 -> 1,42 | 8,1 | `REENTRY_*` (calo forte del prezzo nei primi 3', gol al 15') |
| 36006953 | Parma - Cremonese, Coppa Italia (01/09) | 0-2 al 42' | 5', 41' | - | 14' | 1,32 -> 1,27 | 6,6 | SCARTATA: vedi sotto |
| 35764745 | Ivory Coast - Norway (30/06) | 1-2 | 39', 74', 86' | - | 114' | 1,42 -> 1,40 | 22,2 | re-ingresso dubbio (verde al limite); raw piu' grande |
| 35780184 | Super Nova - Ogre United (06/07) | 1-2 | 48', 80', 92' | - | 20' | 1,68 -> 1,71 (sale) | 8,9 | nessuno (niente verde al fischio, primo gol dopo il 45') |
| 35781607 | Suduva - TransINVEST (06/07) | 0-0 | - | - | 6' | - | 8,7 | nessuno |
| 35797538 | Zeleznicar Pancevo - CSKA 1948 (07/07) | 0-1 | 87' | - | 19' | - | 9,2 | nessuno |
| 35674515 | (nomi non nel sidecar) (26/06) | 4-2 | (timeline vuota) | - | 14' | - | 10,1 | U3.5 CLOSED al 31' (mercato deciso dai gol, caso gia' noto); nessuno D11 |
| 35759636, 35772591 | (30/06) | 3-1, 0-3 | - | - | registrazione iniziata 6' DOPO il KO | - | 7,9 / 7,0 | nessuno: Mike non entra (niente pre-match) |
| 35797769 (gia' nel repo) | Spain - Belgium (10/07) | 2-1 | 30', 41' | - | 148' | 1,47 -> 1,46 (1 tick) | 23,1 | re-ingresso possibile solo se il verde abbina: dubbio. Mai usata per Mike: si puo' provare senza copiare nulla |

Scelta: **35777617, 35768365, 35774000**. Motivo: sono le sole COMPLETE con un gol nella finestra
del fischio (35777617) o con verde al fischio probabile + gol prima del 45' (35768365, 35774000);
due di esse portano anche un **gol annullato** nel feed (gol che appare e sparisce entro un minuto:
non elencato in D11 ma mai visto da Mike). 35774000 e' la piu' piccola a parita' di stato.

**Scartata 36006953** nonostante il verdetto COMPLETE 100%: la registrazione si ferma alle 16:44
(44' dal KO; 2 sessioni in `recmeta`), l'Under 3.5 non arriva mai a CLOSED (ultimo stato OPEN);
il validatore la promuove perche' la sua finestra si chiude su un mercato chiuso (sono chiusi solo
O/U 0.5, O/U 1.5 e i mercati del primo tempo). E' un reperto sul validatore (`validate_recordings`
da' COMPLETE a una partita registrata per un solo tempo), da portare al coordinatore; non l'ho
toccato.

### Stati D11: coperti / ancora scoperti (il simbolo del piano per "scoperto")

| stato | dopo questa scelta | causa |
|---|---|---|
| `LIVE_SECOND_ENTRY` | ATTESO su 35777617 | da confermare col replay (dipende da quando abbina il verde al fischio) |
| `REENTRY_PENDING`, `REENTRY_OPEN`, `REENTRY_GREEN_PENDING` | ATTESI su 35768365 e 35774000 (e forse 35777617) | da confermare col replay: servono anche quota U4.5 > ingresso e liquidita'; il verde del re-ingresso dipende dai prezzi dopo l'ingresso |
| `PRE_LAST_ENTRY_PENDING` | SCOPERTO (probabile) | richiede una verde finale pre-partita abbinata a KO-10'; nelle candidate il last traded pre-match dell'Under 3.5 e' quasi piatto (es. 35768365 1,47-1,51 nell'ora prima del KO): non stimabile senza replay; restano le sintetiche `ultimo_ingresso*` |
| `SKIPPED` | SCOPERTO per costruzione | nasce solo dal comando dell'utente (`service.py:4014`): nessuna registrazione puo' produrlo; va coperto con uno scenario del banco o con le sintetiche |
| `ERROR` | SCOPERTO per costruzione | nasce solo da uno stato sconosciuto: nessuna registrazione puo' produrlo |

Attenzione: le tre partite chiudono tutte a 3 gol (Under 3.5 vincente): la copertura Over 4.5
dopo il 4o gol resta esercitata solo da 35760084 (4-0).

## 3. Verifiche

### V1 - sha256 sorgente = copia decompressa (24 file su 24 UGUALI, anche nelle dimensioni)

Decompressione di prova in `scratchpad/b2/` (fuori dal repo) con lo script di ricostruzione del
LEGGIMI; poi una seconda volta con il testo estratto DAL LEGGIMI (identico byte per byte allo
script provato) in `b2/leggimi/`: 24 file identici; una terza esecuzione sulla stessa cartella
non sovrascrive nulla (24 righe "esiste gia'").

| file | byte | sha256 |
|---|---|---|
| 35777617.raw.jsonl | 18.825.474 | 3914a449d91a9101e2a1d9f563ad335b2d449aff839d8490889e8934c918f1fa |
| 35777617.scores.jsonl | 191.871 | 135a686eba8ecfa9093b546b2c311d9615464e212ea2c98062875968e843b028 |
| 35777617.timeline.jsonl | 1.769 | d2b4a6365184191f47165eec4b2d3e829254f52fe928b8748a5815eed90eec7e |
| 35768365.raw.jsonl | 20.541.204 | 654a6f1e5a6fc304b1f619057118aa8c92031f8cafe45072ae2deee88692c498 |
| 35768365.scores.jsonl | 190.651 | abd17c6027aa68551fcf096471c891f4127c4512d3dd110c26d3ee534e16bd2a |
| 35768365.timeline.jsonl | 2.104 | 3a54b93df5eba2547d17c57bb43347a6bef9043911a4b7fa629dba77aa024a04 |
| 35774000.raw.jsonl | 8.120.242 | a35071a6b214bc918e75e64d9f6710b292a6c54ba7691364683ad809252360a1 |
| 35774000.scores.jsonl | 155.407 | f251b042792071c866cfe718356d0635846d8f9b148623905908f8d943931f69 |
| 35774000.timeline.jsonl | 2.154 | 38d8e622146ae5977459780012e6539bb8c135c39ca86fd5d438ac78fe571f20 |
| 35790089.raw.jsonl | 841.467 | ffb2a523544e17d55767a67ce8f582a710dd99a1cc2d322a45f045d8b00d942b |
| 35790089.score.jsonl | 71.604 | 99edcc184e68e368035395c41b07c76b321528ab41fdf991a55800e76db38d25 |
| 35794049.raw.jsonl | 1.311.381 | 3d5ed00f255146a0028b8e726459cfb3ac374c0c9f7cfccc986a4368de4737aa |
| 35794049.score.jsonl | 118.226 | e0cb019bb816f2027d9a34f16102e3f8e15a728574fea5ee10b084d076f2a56e |
| 35795993.raw.jsonl | 1.349.675 | 35bceb13cd1d393b2d3f8cb7f8c0800ae2bf21123a8b7dd2dd1e0aaa67dadd9b |
| 35795993.score.jsonl | 125.611 | e9b7c928dae4ad8c882363b62b785328c3d0bfa2a7556b8a9ec9eae86e313e4c |
| 35797566.score.jsonl (20260707) | 7.560 | d2fce618715c21b8803a33693068dd131fee15a3d321823b2ba450c0807fed6a |
| 35797566.raw.jsonl (setbetting) | 19.221 | 9931ac405dc9f206741773cfd0cc104ac60b8c9479fb6f13465f086c7a4a81cc |
| 35797566.score.jsonl (setbetting) | 7.706 | e08f74021cb3e2da269af70d6f9c0bf6e454c36f42eca8dd592c7149fe31f7ab |
| 35760084.raw / scores / timeline (gia' nel repo) | 7.373.985 / 145.856 / 2.020 | 8037bac2... / 6910bcab... / 31dc7de9... (= `_live_raw`) |
| 35797769.raw / scores / timeline (gia' nel repo) | 23.100.247 / 234.040 / 1.959 | c11894ab... / 28c3de96... / 7a92a5c7... (= `_live_raw`) |

### V2 - validatore sulla copia decompressa = sorgente

`python -m Betfair.stream.tools.validate_recordings --json --data-dir <b2/calcio>` confrontato
con la riga dello stesso evento lanciato sul checkout principale: TUTTI i campi JSON uguali
(nessuna differenza), verdetto e copertura compresi:
35760084 COMPLETE 95,2; 35768365 COMPLETE 95,0; 35774000 COMPLETE 98,1; 35777617 COMPLETE 97,1;
35797769 COMPLETE 95,4.
Buchi in finestra delle nuove (minuti dal KO): 35768365 3,4-4,6 / 112,4-113,5 / 121,2-125,1 (il
primo cade subito dopo la finestra di 180 s del fischio: da tenere presente leggendo il replay);
35774000 100,4-101,4 / 104,2-105,3; 35777617 127,7-131,6 (dopo la chiusura dell'U3.5 a 126,1').
Stesso confronto sul tennis (`--data-dir` sulla cartella del giorno): 35790089 COMPLETE 92,4;
35794049 COMPLETE 99,1; 35795993 PARTIAL 65,7; 35797566 NO_RAW (20260707) e PARTIAL 6,8
(setbetting): tutti i campi uguali fra sorgente e copia.

### V3 - tennis: righe, `pt`, `marketDefinition`, confronto coi referti gia' esistenti

| evento | righe raw | primo / ultimo `pt` (UTC, 07/07) | marketDefinition | righe score | referti esistenti |
|---|---|---|---|---|---|
| 35790089 | 5.217 | 12:28:16 / 13:58:58 | 4, MATCH_ODDS (OPEN, SUSPENDED, CLOSED) | 104 | `tick=5216`, "COMPLETE 92.4% (5 buchi)", "104 campioni dal sidecar" (`AUDIT_2026-10-08/banco_attraversa/tennis_dopo.txt`) |
| 35794049 | 8.609 | 12:28:16 / 14:44:13 | 5, MATCH_ODDS (OPEN, SUSPENDED, CLOSED) | 180 | `tick=8608`, "COMPLETE 99.1% (1 buchi)", "180 campioni", catalogo Sinner/Struff (`AUDIT_2026-09-28/replay/giro_finale_29_09/tennis_pro_35794049_9048238.txt`) |
| 35795993 | 8.353 | 12:28:16 / 15:50:05 | 18, MATCH_ODDS (OPEN, SUSPENDED, CLOSED) | 191 | `tick=8352`, "PARTIAL 65.7% (11 buchi)", "191 campioni" (`.../tennis_pro_35795993_9048238.txt`) |
| 35797566 (setbetting) | 62 | 17:32:42 / 18:16:45 | 10, SET_BETTING (solo OPEN) | 12 | ERROR "registrato solo il SET_BETTING" (`AUDIT_2026-10-08/applica_bot_tennis/certifica_dopo.txt`) |

Sidecar score (campo `t`, UTC): 35790089 12:28:16-13:58:21; 35794049 12:28:16-14:43:24;
35795993 13:30:34-15:49:29; 35797566 18:03:15-18:17:29 (setbetting 18:03:12-18:17:27).
In ogni referto `tick` = righe del raw - 1, e copertura e campioni coincidono: e' la stessa
registrazione usata nelle certificazioni.

### V4 - dimensioni e stato git

Totale aggiunto 8.571.210 byte. `git status --short --untracked-files=all registrazioni_banco`:

```
 M registrazioni_banco/LEGGIMI.md
?? registrazioni_banco/35768365/35768365.timeline.jsonl
?? registrazioni_banco/35774000/35774000.timeline.jsonl
?? registrazioni_banco/35777617/35777617.timeline.jsonl
```

I 15 file `.jsonl.gz` NON compaiono perche' `.gitignore:44` (`*.jsonl.gz`) li ignora
(`git check-ignore -v` lo conferma): `.gitignore` non e' stato toccato; al commit serve
`git add -f` sui percorsi esatti (lo fa il coordinatore).

## 4. Cosa NON ho potuto verificare

- Che i replay di Mike sulle tre partite scelte producano davvero gli stati attesi: e' una STIMA da
  punteggi e last traded price, non un replay (vietato a me). Va confermata con
  `certifica mike <id> --scenari base` dal coordinatore. Mike con `tutti` impiegava 728 s su una
  partita da 7,4 MB: su queste (8-20 MB) la durata va dichiarata prima di lanciare.
- Che il banco tennis legga davvero la cartella ricostruita via `TENNIS_RECORD_DIR`: letto nel
  codice (`registro_bot._cartella_tennis`, `applica_bot.risolvi_cartella_tennis`), non eseguito.
- Che il banco calcio legga `_live_raw/` ricostruito nel worktree: letto in
  `config_stream.DATA_DIR`, non eseguito.
- I nomi di squadre e giocatori vengono dai sidecar (troncati per il tennis): non verificati altrove.
- Altri file presenti in `_live_raw/<id>/` (`<id>.jsonl`, per 36006953 anche `recmeta`) NON sono
  stati copiati: non fanno parte dello schema delle due registrazioni gia' nel repo.

## 5. Cosa manca

- Raw Match Odds di 35797566: non esiste da nessuna parte.
- Partite tennis COMPLETE oltre a 35790089 e 35794049: servono nuove giornate registrate (U-44,
  seconda meta').
- Una registrazione che porti a `PRE_LAST_ENTRY_PENDING` (non individuabile senza replay) e uno
  scenario per `SKIPPED`/`ERROR` (non producibili da registrazioni).
- Reperto da decidere: `validate_recordings` dichiara COMPLETE 100% la 36006953, registrata per un
  solo tempo.
