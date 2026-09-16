# CHECKPOINT S2 — 16 settembre 2026 (delegato Opus 5 "S2")

> Perimetro: A) ESATTO «selezione aggiuntiva» (modifica ORDINATA dall'utente);
> B) SAFE calcio BASE e PUNTA — sintetiche native + tabella bande sui dati reali;
> C) SAFE tennis — copertura di tutti gli scenari sulla terna + sintetiche per T8/L2.
> Vincoli: nessun'altra regola di strategia toccata; niente `git add -A`; niente commit;
> niente avvio app. File proibiti (altro delegato): `bot_service.py`, `execution.py`,
> `bot_db.py`, `omega_market.py`, `banco_comune.py`.

## Stato
- [x] A — ESATTO selezione aggiuntiva (codice, test, replay prima/dopo: FATTO)
- [x] B — BASE e PUNTA: sintetiche + replay + tabella bande (FATTO)
- [ ] C — TENNIS: scenari su terna reale + sintetiche T8/L2

## Diario
- h00 — letti HANDOFF, PROCESSO §6-§7, PIANO (Esiti C.3/C.3-bis/C.4/C.4-bis/C.4-ter),
  SPEC, RISCONTRO_CALCIO (E10), engine.py, certificazione*.py, replay*.py.

## A — SELEZIONE AGGIUNTIVA (SPEC §2) — CHIUSO

**Paragrafo della SPEC** (`SPEC_STRATEGIA_S.md` §2, tabella, ultima riga):
`| Selezione aggiuntiva | scontri diretti senza troppi 2-2/3-3, difesa avversaria solida |`
(voce E10 del `RISCONTRO_CALCIO_2026-09-14.md`, riga 158: «⊗ manca il codice, non il dato»).

**Letture possibili** (la SPEC non quantifica «troppi» ne' «solida»):
1. *(SCELTA, letterale)* filtro di SELEZIONE DELLA PARTITA su due numeri storici:
   quota di scontri diretti finiti 2-2 o 3-3, e gol subiti per partita della squadra
   AVVERSARIA della bancata. Soglie misurate sullo stesso atlante (6,04 % e 1,37).
2. soglie fisse a occhio (es. «al massimo un 2-2/3-3», «meno di 1 gol subito»): numeri
   non presenti nella SPEC e non ricavabili da nessun dato.
3. filtro qualitativo, non automatizzabile -> la voce resta ⊗ per sempre: escluso
   dall'ordine dell'utente.

**Dove** — `Betfair/safe_strategy/selezione.py` (dato, dall'atlante gia' in casa
`Betfair/omega/data/hazard_atlas_v2.json`, lo stesso di `omega_advisor`);
`engine.py:selection_check` (regola) + `evaluate_esatto` (uso, dietro
`requireSelection`) + `DEFAULT_PARAMS['esatto']`; `service.py:build_rows`
(`payload['selection_hint']`, come `pressure_index`); gemello TS in
`frontend/src/lib/safeStrategy.ts:selectionCheck` (la parita' dei due motori e'
difesa da un test meccanico); controllo `certificazione.py:E10` riscritto.

**Replay 35797769 — prima / dopo** (`certifica safe_esatto 35797769`):
| | segnali ESATTO | ordini su flumine | fill | E10 |
|---|---|---|---|---|
| prima | 334 | 3 | 2 (32,0 e 34,0) | **334 violazioni** |
| dopo, scenario `base` (filtro SPENTO = default) | 334 | 3 | 2 (32,0 e 34,0) | 0 viol., 0 casi («non lo so») |
| dopo, scenario `selezione-aggiuntiva` (filtro ACCESO) | **0** | **0** | 0 | **x7682 sollecitato, 0 violazioni** |
Con il filtro acceso la variante non entra piu' su questa partita: `h2hDifesa:nd x7682`
— Spagna-Belgio non ha scontri diretti nell'atlante, e un dato assente non e' un
verdetto. **Sulle 39 registrazioni del corpus una sola coppia (Udinese-Venezia) ha gli
scontri diretti**: per questo il filtro nasce SPENTO, come `requireControl`.

## B — BASE e PUNTA: sintetiche + tabella delle bande sui dati REALI

### B.1 Registrazioni SINTETICHE create (dichiarate come tali)
Generatore: `Betfair/safe_strategy/tools/synth_safe.py` (`python -m
Betfair.safe_strategy.tools.synth_safe --tutte`). Formato NATIVO Betfair
(`mcm`/`rc`/`marketDefinition`) + sidecar IPS, con MATCH_ODDS, CORRECT_SCORE
(id globali veri) e O/U 2.5/3.5; mercato SOSPESO a ogni gol, CHIUSO a fine
partita con i WINNER. Il banco le riconosce dal prefisso e le DICHIARA nel
referto («!! REGISTRAZIONI SINTETICHE»).

| cartella | che cosa provoca | ordini veri | esito |
|---|---|---|---|
| `_live_raw/_synth_safe_base` | ingresso 1-0 al 55', pareggio della sfavorita (B12), secondo ingresso 2-1, uscita a tempo all'80' (B14) | 5 (2 BASE) | 0 violazioni |
| `_live_raw/_synth_safe_base_profitto` | ingresso 1-0, la favorita segna il 2o gol (B13) | 4 (2 BASE) | 0 violazioni |
| `_live_raw/_synth_safe_base_rosso` | ingresso 1-0, ROSSO alla favorita (B15) | 3 (2 BASE) | 0 violazioni |
| `_live_raw/_synth_safe_punta` | 2-0 -> ingresso al 66'; 3-0 (P8); 3-1 (P7); tempo all'83' (P9) | 6 (4 PUNTA) | 0 violazioni |
| `_live_raw/_synth_safe_tennis` | ingresso a 1,02 (T6), crollo (T7), mercato CHIUSO con WINNER (settlement, T8) | 2 | 0 violazioni |

Copertura ottenuta (prima: tutti «non lo so»):
B3 x331/x44/x21 - B9 x331/x44/x21 - B12 x55 - B13 x48/x55 - B14 x48/x55 -
B15 x5 - B16 x5 - P1..P5 x1223 - P7 x73 - P8 x73 - P9 x73 - P10 x10.
Restano «non lo so» per parametro spento e dichiarato: B10/E6/P6
(`requireControl`), B17 (`base_control_exit`), E10 (`requireSelection`).

### B.2 Tabella per la DECISIONE DELL'UTENTE (bande sui 39 dati REALI)

Scansione con le funzioni VERE (`Scanner.build_rows` ->
`build_football_ctx_from_scan` -> `evaluate_base`/`evaluate_punta`) su tutte e
39 le registrazioni reali. **Le bande NON sono state toccate.**

- **18 registrazioni su 39 non hanno il riferimento pre-KO**: li' BASE e PUNTA
  non possono entrare per mancanza di DATO (`favPre`/`leadFav` = n/d).
- **BASE, bande pre-match (favorita 1,40-1,80 E sfavorita 4-8): 5 partite su 39**
  (12,8 %).
- **Quota live della favorita in 1,20-1,34: 8 partite su 39** hanno almeno una
  riga dentro la banda; fra le 5 che rispettano anche le bande pre-match, solo
  **2** ci arrivano (`35797769` 315 righe, `35817978` 38 righe): sulle altre
  tre la favorita non passa MAI per quella finestra.
- **PUNTA: 15 partite su 39** vedono almeno una riga col punteggio ammesso
  (2-0/3-1/3-0 orientato sul leader), ma **nessuna** ha insieme punteggio,
  leader = favorita pre-KO, minuto e quota 1,03-1,10: **zero segnali in tutto
  il corpus**, confermato.

| evento | partita | fav pre | dog pre | bande BASE | righe fav live 1,20-1,34 | segnali BASE | righe punteggio PUNTA | righe entrata 1,03-1,10 |
|---|---|---|---|---|---|---|---|---|
| `35797769` | Spain v Belgium | 1.64 | 6.0 | SI | 315 | 3 | 0 | 161 |
| `35817978` | FC Astana v Dinamo Tirana | 1.53 | 7.2 | SI | 38 | 0 | 0 | 2 |
| `35768297` | Portugal v Croatia | 1.74 | 5.9 | SI | 0 | 0 | 8 | 115 |
| `35780184` | SK Super Nova v Ogre United | 1.66 | 5.3 | SI | 0 | 0 | 303 | 67 |
| `35817332` | FC Inter v Sarajevo | 1.66 | 5.9 | SI | 0 | 0 | 0 | 0 |
| `35774000` | MAS Taborsko v SKU Amstetten | 2.46 | 2.78 | no | 381 | 0 | 227 | 0 |
| `35828026` | HNK Gorica v FC Epicentr Dunaiv | 2.44 | 3.2 | no | 64 | 0 | 0 | 0 |
| `35760084` | Liepajas Metalurgs v Ogre United | 1.35 | 9.2 | no | 55 | 0 | 1390 | 207 |
| `35768365` | Spain v Austria | 1.36 | 11.5 | no | 22 | 0 | 835 | 2 |
| `35764745` | Ivory Coast v Norway | 2.2 | 3.85 | no | 8 | 0 | 0 | 46 |
| `35797538` | Zeleznicar Pancevo v CSKA 1948 Sofia | 2.04 | 3.45 | no | 2 | 0 | 0 | 83 |
| `35759636` | Rigas Futbola Skol v BFC Daugavpils | n/d | n/d | no | 0 | 0 | 1017 | 774 |
| `35772591` | Nyiregyhaza v FC Zbrojovka Brno | n/d | n/d | no | 0 | 0 | 948 | 210 |
| `35777617` | Brazil v Norway | 1.83 | 5.0 | no | 0 | 0 | 241 | 2 |
| `35788728` | Shandong Taishan v Yunnan Yukun | n/d | n/d | no | 0 | 0 | 197 | 374 |
| `35794996` | Vardar Skopje v KuPS | 1.8 | 1.8 | no | 0 | 0 | 277 | 0 |
| `35787218` | Argentina v Egypt | n/d | n/d | no | 0 | 0 | 410 | 144 |
| `35804211` | FC Inter 2 v RoPS | n/d | n/d | no | 0 | 0 | 513 | 0 |
| `35823409` | Puskas Akademia v Basaksehir | n/d | n/d | no | 0 | 0 | 1664 | 584 |
| `35833626` | Mainz v Kaiserslautern | n/d | n/d | no | 0 | 0 | 184 | 0 |
| `36006953` | Parma v US Cremonese | 2.2 | 3.45 | no | 0 | 0 | 83 | 5 |

Lettura onesta dei numeri: questa scansione valuta OGNI riga pubblicata dallo
scanner con `score_observed_sec` fissato a 60 s, mentre il replay certificato
valuta alla CADENZA del servizio (2 s) e con la freschezza vera. E' per questo
che qui `35797769` mostra 3 righe da segnale BASE e il replay ne mostra 0: la
finestra in cui le tre condizioni coincidono e' larga **tre righe** (pochi
secondi) e la cadenza del servizio la manca. Il numero da portare all'utente
non e' «3 segnali», e' **«la finestra d'ingresso della BASE, su questo corpus,
e' larga pochi secondi»**.

**Decisione all'utente (le bande NON si toccano senza suo ordine):** con le
bande del manuale la BASE e' attivabile su ~1 partita su 8 e, quando lo e',
entra per pochi secondi; la PUNTA su nessuna delle 39.

## C — SAFE TENNIS: tutti gli scenari sulla terna reale + sintetica

### C.1 Scenari sulla terna REALE (35792939, 35795560, 35790650)
`certifica safe_tennis 35792939 35795560 35790650 --scenari base,bot-fermo,
feed-stantio,esiti-ignoti,riavvio,uscita-ignota,approvata-subito,mai-approvata
--worker 3` -> **24 repliche, 0 violazioni**, e i controlli MAI SOLLECITATI
passano da **4 a 2 su 26**.

| controllo | prima (16/09 h17) | adesso | come |
|---|---|---|---|
| T6 (ingresso sotto 1,03 portato a fine partita) | ⊘ | **x272 conforme** | 35792939 entra a 1,02; con il settlement acceso la posizione arriva davvero alla fine |
| T8-DICHIARATA (perdita 5-25 %) | ⊘ | **x11 dichiarato** | settlement abilitato + stati terminali veri |
| T10 (finali) | ⊘ | ⊘ **confermato** | Betfair non pubblica il turno: nessun dato, vero o sintetico, puo' provocarlo |
| L2 (lay sostituita cancel+place) | ⊘ | ⊘ **con causa misurata** | in 24 repliche `cancellati` e' SEMPRE vuoto: il tennis chiude in FOK, non appoggia e non annulla mai. Non e' la partita: e' la forma della strategia |

### C.2 Due difetti del BANCO trovati qui (non del bot)
1. **Il settlement del tennis non avveniva MAI.** Due cause in fila: (a)
   `MercatoFlumine` non espone `read_market` (limite 8, gia' noto); (b) — nuova
   — flumine consegna il mercato chiuso a `process_closed_market`, e il ponte
   del banco comune inoltra solo `process_market_book`: **misurato, l'ultimo
   giro del servizio avviene sempre a mercato OPEN**. Quindi «manca una partita
   che arrivi a CLOSED» era una diagnosi sbagliata: nemmeno una che ci arriva
   sarebbe bastata. Rimedio nel replay tennis (file mio): `abilita_settlement`
   appoggia al mercato i `read_market`/`read_markets` di `MercatoSafe` (gia'
   certificati nel calcio) e `giri_dopo_il_fischio` fa 3 giri a mercato chiuso
   con l'esito letto dal `marketDefinition` registrato — e' quello che fa gia'
   il replay di Omega. Entrambi DICHIARATI nel referto.
2. **Il controllo T8 cercava uno stato che il bot non scrive** (`settled`): il
   bot scrive `won`/`lost`/`void` (`bot_db.py:468,494`). Con quel `quando`, T8
   non poteva avere un caso nemmeno col settlement funzionante — un controllo
   che non sa diventare rosso non certifica.

### C.3 Sintetica tennis
`_live_raw/_synth_safe_tennis` (`--data-dir _live_raw`): 1 set + 2 game di
vantaggio -> ingresso a **1,02** -> due game persi di fila e parita' (uscita
OBBLIGATORIA) -> il mercato CHIUDE col WINNER dall'altra parte. Scenari `base`
e `mai-approvata`: 0 violazioni; e' la partita su cui il buco del settlement e'
venuto fuori. Dichiarata sintetica dal banco stesso.
