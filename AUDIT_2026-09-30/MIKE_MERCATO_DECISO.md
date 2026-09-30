# MIKE - MERCATO DECISO DAI GOL (30/09/2026) - referto del delegato

Worktree `.claude/worktrees/agent-a169d1942e0512816`, base `fc0428f` (master). Nessun commit,
nessun `git add` salvo `git add -N` (solo intenzione, per mettere nella patch il file di test
nuovo) e lo stage automatico di `git apply --3way` del file di test dell'indagine.
Patch: `AUDIT_2026-09-30/MIKE_MERCATO_DECISO.patch` (tutto il diff contro `HEAD`, test compresi;
verificata con `git apply --check -R`). La sola parte frontend anche in
`AUDIT_2026-09-30/MIKE_MERCATO_DECISO_frontend.patch` (vedi "Fuori perimetro").
Non dichiaro "certificato": certifica il coordinatore.

## 1. In breve

- **Blocco A (il bot)**: una linea gia' DECISA dal punteggio (gol > linea) non ferma piu' la
  partita: flusso, snapshot, ripiego REST e cash out manuale guardano solo le linee ancora in
  gioco; lo stato del mercato si legge dalla linea ancora in gioco; il 3,5 CHIUSO con il 4,5
  aperto non manda piu' Mike al regolamento; Mike scrive UNA riga `mercato_deciso` per linea.
  Nessuna soglia, stake, tetto, gamba, finestra o modello toccato.
- **Blocco B (il banco)**: il replay di Mike ora fa arrivare il book CLOSED allo scanner vero
  (ramo di produzione visibile), due scenari nuovi con la firma VERA dell'utente, controllo di
  condotta nuovo **M1**. `banco_comune.py` NON toccato (la correzione sta nel replay di Mike):
  Omega e Safe non sono toccati, nessun loro replay da rifare.
- **Scenario nuovo** `firma-dopo-gol-decisivo`: firma alle 17:25:33 UTC (19:25:33 italiane) su
  "chiudendo ora -2,54": la chiusura dell'Over 4,5 arriva al mercato e si abbina (banca a
  1,34 e 1,35), **P&L NETTO -2,54 EUR** (lordo -2,15, commissione 0,39), 0 `no_fill
  feed_stantio`. Col codice di ieri (correzione 1 tolta, variante senza chiusura): 21 rifiuti
  `feed_stantio`, P&L -14,00, **M1 x1141 + M1-FIRMA x1 = ROSSO**. Correzione 2 tolta: servizio
  in SETTLING dalle 17:25:25, nessuna proposta, P&L -14,00, **M1 x1134 = ROSSO**.
- **Replay completo** (23 scenari): 0 violazioni; i 21 scenari di prima hanno ordini, fill,
  P&L, stati, righe e esiti IDENTICI al referto `mike_tutti_P5_4C.txt`; le sole differenze sono
  quelle attese (sezione 6). Durata **25m16s** con il PC al 100 % di CPU per altri processi
  (sezione 7): sopra il tetto di 10 minuti, il referto stampa `LENTO`.

## 2. Test dell'indagine, prima e dopo

`python -m pytest Betfair/mike/tests/test_mike_indagine_mercato_deciso_2026_09_29.py -q -p no:cacheprovider`
(patch `in_attesa_del_via/INDAGINE_MIKE_MERCATO_DECISO_test_rossi.patch` applicata con `git apply --3way`)

| | esito |
|---|---|
| prima (master `fc0428f`) | **3 failed, 3 passed** (i 3 rossi: `test_rosso_3_5_deciso_e_fermo...`, `test_rosso_dopo_il_quarto_gol...`, `test_rosso_3_5_chiuso_da_betfair...`) |
| dopo | **6 passed** (i 3 di confine restano verdi) |

Suite di Mike: `python -m pytest Betfair/mike -q -p no:cacheprovider` = **1242 passed** (riferimento
1222 su master + 6 dell'indagine + 14 nuovi), 50-87 s. Test del banco:
`Betfair/stream/tests/test_banco_comune_2026_09_16.py test_cert_banco_2026_09_16.py
test_contratto_strada_unica_2026_09_25.py test_banco_uscite_manuali_n3_2026_09_28.py
test_banco_uscite_dichiarate_n3_2026_09_28.py` = **155 passed, 16 skipped** (skip gia' presenti:
test marcati `cert`/registrazioni). Tutto in ambiente neutro (SUPABASE_URL finto, canali a 0).

## 3. Cosa ho cambiato e perche' (file:riga del worktree)

### Blocco A
1. `Betfair/mike/feed.py:107-123` - nuove `linea_decisa(market, goals)` (usa
   `engine.selection_decided`, non una copia) e `linea_di_riferimento(goals)` (prima linea
   ancora in gioco; con 5+ gol resta il 3,5 = regola di prima).
   `feed.py:126-150` `mercati_di_mike`: salta le linee decise dal punteggio della riga
   (`goals_from_payload`). Effetto: `flusso_esito` non guarda piu' il 3,5 deciso; una linea viva
   ferma continua a bloccare (test di confine verdi).
   `feed.py:450-454` `snapshot_from_row`: `market_status` dal blocco della linea di riferimento
   invece che dal 3,5 (col 4-0: il 4,5).
2. `Betfair/mike/service.py:4279-4285` `status_closed`: letto dal blocco della linea di
   riferimento (con 4 gol il 4,5; con 5+ gol il 3,5 come prima), con lo stesso ripiego su
   `mo_status` quando il blocco non ha lo stato. Il 3,5 CLOSED col 4,5 aperto non e' piu'
   "partita chiusa". Nota: NON ho aggiunto un "OR MATCH_ODDS CLOSED" esplicito (il codice di
   prima usava il MATCH_ODDS solo come ripiego dello stato del blocco): aggiungerlo avrebbe
   potuto anticipare il regolamento in partite dove il MO chiude prima del 4,5; lo segnalo.
   `service.py:1209-1225` `_books_ripiego_rest(..., goals=None)`: salta la linea decisa;
   chiamata con `goals` da `_request_flatten` (`service.py:3469-3470`) e da `_run_event`
   (`service.py:4553`). Senza elenco dei fermi (giro scanner bloccato) prima leggeva anche il 3,5.
3. `service.py:4498-4515` consapevolezza: `db.log("mercato_deciso", {"market": "OU35",
   "market_id": "1.xx", "goals": 4 (int), "stato_mercato": "SUSPENDED"|"CLOSED"|None,
   "esito": {"OU35|UNDER": "persa"}, "state": "LIVE_COVERED"}, event_id)`, una volta per linea
   (memoria `ctx.linee_decise`, persistita con la riga dell'evento: sopravvive al riavvio).
   `mike_activity` non ha CHECK su `kind` (`migrations/mike_bot.sql:124-130`): nessuna migrazione.
4. Difetti minori dell'indagine: **NON fatti**, non sono a costo zero.
   - Etichetta "FLAT chiuso" per un giro dopo i tentativi esauriti (`engine.py:4196-4207`
     `_decide_closing`): correggerla vuol dire restare in `LIVE_CLOSING` invece di passare da
     `FLAT` -> `LIVE_COVERED "esposizione residua"`, cioe' cambiare la macchina a stati (il giro
     dopo oggi riapre la gestione). Decisione per l'utente/coordinatore.
   - Testo "da N s" che conta dal fischio: l'eta' viene da `flusso.dal_ms` della RIGA
     (`stream/flusso_prezzi.py:_con_eta`, modulo condiviso da tutti i bot) e lo scanner non
     scrive un istante per mercato; servirebbe un campo per mercato nello scanner
     (`safe_strategy/service.py`, escluso). Con la correzione 1 il caso del 3,5 deciso non
     produce piu' l'avviso.

### Blocco B
5. `Betfair/mike/tools/replay_registrazioni.py`:
   - `:169-187` scenari `firma-dopo-gol-decisivo` e `firma-dopo-gol-decisivo-senza-chiusura`
     (nessun parametro toccato), `GOL_DECISIVO = 4`.
   - `:815-842` `_firma_dopo_gol`: al primo giro con una proposta viva con `gol >= 4` manda la
     richiesta VERA `approva_uscita` a `service.process_requests` (stessa strada di
     `cashout-globale`), condizionata ai gol e non a un orario (vale per ogni registrazione).
   - `:1240-1265` note del referto e violazione di scenario `M1-FIRMA` se la firma e' partita ma
     l'uscita non e' stata eseguita o ci sono rifiuti `feed_stantio`.
6. `Betfair/mike/certificazione.py:1192-1297` famiglia **M**, controllo **M1** (in
   `elenco_controlli`, conta nella copertura): il caso lo decide la RIGA (gol dal punteggio, linea
   decisa per regola, flusso della linea in gioco dal modulo condiviso `flusso_prezzi`, riga non
   invecchiata dallo scenario, linea in gioco non CLOSED). Viola se (a) il feed di Mike dichiara
   fermo il flusso, (b) un ordine sulla linea viva e' rifiutato per `feed_stantio` nel giro,
   (c) il servizio e' in regolamento (`settle_first_ts`) con la linea viva aperta. Agganciato dopo
   ogni giro in `replay_registrazioni.py:780-791` e `:843-862` (costo misurato: 0,18 s per 6000 giri).
7. Mercato CHIUSO nel banco (`replay_registrazioni.py:549-574`): `MikeCert.process_closed_market`
   (flumine consegna qui i book CLOSED, `baseflumine.py:376-380`) passa il book allo SCANNER VERO
   (`Scanner._apply_market_book` su `libro_di_produzione`, la stessa funzione di
   `ScannerReplay.applica_book`, senza conflazione, una volta per mercato). Lo scanner scrive
   `status: CLOSED` nel blocco (`_apply_opp_book`), esattamente come in produzione. Nel referto:
   "mercati CHIUSI ... passati allo scanner vero" (sulla 35760084: 3,5 `1.259475537` alle
   17:25:25.616 UTC, 4,5 alle 17:54 UTC, e le linee 0,5/1,5/2,5).
   **Perche' non in `banco_comune.py`**: la modifica minima e sicura sta nel replay di Mike, cosi'
   Omega e le Safe restano byte per byte come prima (nessun loro replay da rifare). Se il
   coordinatore la vuole nel banco comune, servirebbe un metodo `ScannerReplay.applica_chiusura`
   e i replay rapidi di Omega e delle tre Safe da confrontare.
   **Reperto del banco**: con le chiusure visibili il ramo "3,5 fermo" del 29/09 NON capita
   piu' da solo sulla 35760084 (lo scanner salta i blocchi CLOSED in `flusso_evento`): la
   correzione 1 restava senza caso. Per questo lo scenario `...-senza-chiusura` inietta il guasto
   "la chiusura non arriva allo scanner" (il banco di prima): il 3,5 resta sospeso e FERMO, ed e'
   li' che la correzione 1 si mette alla prova.

### Fuori perimetro (da approvare)
- `frontend/src/lib/mike.ts` (+4 righe, solo dati): `'mercato_deciso'` in `MIKE_ACTIVITY_KINDS`
  e l'etichetta `LINEA DECISA DAI GOL` in `MIKE_ACTIVITY_EXTRA`. Il brief escludeva il frontend,
  ma il contratto UI (`test_mike_certificazione_ui_2026_09_11.py::
  test_contratto_ogni_kind_di_attivita_del_backend_e_dichiarato_in_ui`) va ROSSO per ogni kind
  nuovo non dichiarato in UI: senza queste righe la suite ha 1 rosso. Patch separata per
  scartarla se non approvata. `npm run build`, `tsc` e `vitest` NON eseguiti (nel worktree non
  c'e' `node_modules`).
- `Betfair/mike/tests/test_mike_audit_2026_09_11.py` (+3 righe): `mercato_deciso` nell'elenco
  dichiarato dei kind (test L5).

## 4. Test nuovi (`Betfair/mike/tests/test_mike_mercato_deciso_2026_09_30.py`, 14 test)

Finti: `payload`/`row` di `test_mike_feed`, `FakeDB`/`FakeMarket` di `test_mike_service`, riga
vera delle 17:25:33 UTC dall'indagine (`_payload`), libri REST con le chiavi di
`omega_market.read_book`. Coprono: stato del mercato dalla linea in gioco; linea di riferimento;
regolamento con 4 gol e 4,5 CHIUSO (confine); regolamento con 5 gol e 3,5 CHIUSO (confine, nessun
ordine); nessun regolamento con 4 gol e 3,5 CHIUSO; ripiego REST che non legge la linea decisa;
`mercato_deciso` una volta con chiavi e tipi; con 5 gol anche il 4,5 (`OU45|OVER: vinta`); nessuna
riga sotto la linea; M1 nell'elenco; M1 sano sulla riga vera con la correzione; M1 che scatta
(flusso fermo, rifiuto, regolamento); M1 senza caso ai confini (linea viva ferma davvero, 3 gol,
5 gol, riga invecchiata, 4,5 CHIUSO).

## 5. Falsificazioni (tutte eseguite davvero, ripristino dalla copia, sha256 verificato, `git diff` identico prima e dopo)

Unita' (`AUDIT_2026-09-30/falsifica_test_MERCATO_DECISO.txt`):

| mutazione | test rossi |
|---|---|
| M-A `mercati_di_mike` conta anche la linea decisa (correzione 1 tolta) | 3 (2 rossi dell'indagine + M1 sano) |
| M-B snapshot: stato dal blocco 3,5 | 1 |
| M-C `status_closed` dal 3,5 (correzione 2 tolta) | 2 (rosso dell'indagine + nessun regolamento) |
| M-C2 linea di riferimento con 5+ gol = 4,5 | 2 |
| M-C3 `status_closed` mai vero | 1 |
| M-D ripiego REST legge la linea decisa | 1 |
| M-E `mercato_deciso` a ogni giro | 1 |
| M-F M1 non guarda il flusso del bot | 1 |
| M-G M1 conta la linea in gioco CHIUSA | 1 |
| M-H M1 ignora il regolamento | 1 |

Replay (punto 6 del brief; `falsifica_replay_correzione1_tolta.txt`,
`falsifica_replay_correzione2_tolta.txt`):

| codice | scenario | esito | P&L | M1 |
|---|---|---|---|---|
| corretto | `firma-dopo-gol-decisivo` | OK, 0 violazioni | -2,54 | x1145 sollecitato, 0 KO |
| corretto | `...-senza-chiusura` | OK, 0 violazioni | -2,54 | x1145, 0 KO |
| correzione 1 tolta | `...-senza-chiusura` | **KO**, 1143 violazioni (M1 x1141, M1-FIRMA x1), 21 rifiuti `feed_stantio`, flusso_interrotto x37, senza_rest x29 | -14,00 | x1145 |
| correzione 2 tolta | `firma-dopo-gol-decisivo` | **KO**, M1 x1134, stato SETTLING, "firma mai partita" | -14,00 | x1138 |
| correzione 1 tolta | `firma-dopo-gol-decisivo` (chiusure visibili) | OK: NON scatta (vedi reperto del banco, sezione 3.7) | -2,54 | x1145 |

## 6. Replay completo e confronto con `mike_tutti_P5_4C.txt`

Comando (ambiente neutro):
`python -m Betfair.stream.backtest.certifica mike 35760084 --scenari tutti --trasporto canale --worker 0 --data-dir "C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/_live_raw"`
Referto: `AUDIT_2026-09-30/mike_tutti_MERCATO_DECISO.txt` (codice bot `532ad0b89289`; dopo il
replay ho cambiato solo un commento in `service.py`, virgolette caporali sostituite con `"` per l'ASCII: hash diverso,
comportamento identico). Confronto campo per campo:
`AUDIT_2026-09-30/confronto_replay_P5_4C_vs_MERCATO_DECISO.txt`.

**Esito: 23 scenari, 0 violazioni, controlli attivi 43 (erano 42: + M1), M1 x24045.**

Identici in TUTTI i 21 scenari di prima: esito, stati visti, azioni, ordini reali piazzati, righe
`mike_trades`, righe per stato, motivi dichiarati, fill, **P&L** (base -14,00; cap-stretto
-12,00; ecc.), bet delay, note degli scenari. Scenari 4-21: anche tick (56229) e decisioni
identici. Differenze, una per una:

| differenza | dove | spiegazione |
|---|---|---|
| `flusso_interrotto` x37 -> x3; `flusso_interrotto_senza_rest` x28 -> x3 (base/taker/cap-stretto) | tutti | spariscono gli avvisi sul 3,5 deciso/chiuso (episodio B dell'indagine); restano i 3 veri (4,5 sospeso dopo il 3o gol, fine gara) |
| cashout-globale e cashout-dopo-copertura `flusso_interrotto` x7 -> x2 | 2 | stessa causa |
| `mercato_deciso` x1 (nuovo kind) | tutti tranne bot-fermo/feed-stantio | la riga di consapevolezza, una volta per il 3,5 |
| chiamate di LETTURA 150 -> 3, tick 56098 -> 56226, decisioni 5804 -> 5863, `tengo` +30, `prezzi incompleti` +2, `uscita_proposta` +1 e `decadute` +1 (base, taker, cap-stretto) | 3 | le 150 letture erano il ripiego REST sul 3,5 chiuso (ogni 10 s per 25 minuti), che consumavano 18 s di tempo di mercato: non era la "memoria di processo" ma questo difetto. Ora i tre scenari si allineano agli altri 18 (proposte 18/16 come nel riferimento). Ordini, fill e P&L invariati |
| righe di scan scritte +1 | tutti | lo scanner riscrive la riga quando il blocco del 3,5 passa a CLOSED |
| nota nuova "mercati CHIUSI da Betfair passati allo scanner vero" | tutti | il banco nuovo (punto 7) |
| B2 x22672 -> x1189 | copertura | B2 si sollecita a feed non fresco: il 3,5 deciso non rende piu' stantio il feed |
| G2 x0 -> x2 | copertura | la firma negli scenari nuovi mette finalmente alla prova G2 ("nessuna uscita in perdita senza la SUA firma"): prima MAI sollecitato |
| MAI SOLLECITATI 10 -> 9 | copertura | G2 esce dall'elenco |
| 2 scenari nuovi | - | `firma-dopo-gol-decisivo` e `...-senza-chiusura`: OK, 8 ordini, 5 abbinamenti su 4 ordini per 25,85 EUR (prezzi 1,34/1,35/1,71/4,0), stati fino a `LIVE_CLOSING,FLAT`, P&L NETTO **-2,54** (lordo -2,15, comm. 0,39) |

Base: nessuno firma, **P&L -14,00 invariato**.
Regolamento a fine gara: in nessuno scenario (ne' prima ne' ora) la partita arriva allo stato
terminale nel replay: `MercatoFlumine.read_book` torna None sui mercati chiusi (limite 8 del
banco), quindi il regolamento via REST aspetta; il P&L lo calcola il banco da flumine. Con la
correzione, a fine gara (4,5 CHIUSO alle 17:54 UTC) Mike entra nella strada del regolamento come
deve (test `test_con_4_gol_il_4_5_chiuso_porta_al_regolamento`).

## 7. Durata dei replay (PC al 100 % di CPU per altri processi: python/node di altre sessioni)

| replay | durata |
|---|---|
| `firma-dopo-gol-decisivo` da solo (1a prova) | 124,5 s (tempo del referto 116,4 s) |
| `base` da solo | 141 s (referto 130,2 s; nel riferimento 66,5 s a PC libero) |
| falsificazione correzione 1 su `firma-dopo-gol-decisivo` | 159 s |
| falsificazione correzione 2 su `firma-dopo-gol-decisivo` | 131 s |
| `...-senza-chiusura` corretto | 167 s |
| falsificazione correzione 1 su `...-senza-chiusura` | 143 s |
| **completo, 23 scenari** | **25m16s (1516,5 s)**, `LENTO` sopra il tetto di 600 s |

Il costo aggiunto dal controllo M1 e' misurato a parte: 0,18 s per 6000 giri. I due scenari
nuovi aggiungono circa 2 x 70 s a PC libero (stima dal rapporto con `base`). Il sovraccarico
misurato e' del carico del PC, non del banco, ma NON ho potuto dimostrarlo con un replay a PC
libero: il coordinatore dovrebbe rilanciare a PC libero per confermare i 9-10 minuti.

## 8. Parita' paper/live

Tutte le modifiche del bot sono in `feed.py` e `service.py` su percorsi comuni ai due modi
(`flusso_esito`, `snapshot_from_row`, `status_closed`, `_books_ripiego_rest`, `_run_event`):
nessun ramo `paper`/`live`. `execute_place` non e' toccato: il muro `feed_stantio` vale identico
nei due modi, solo che non scatta piu' per una linea decisa. Il replay gira in paper sul canale
(`--trasporto canale`); il live non e' stato replicato in questo lavoro (la parita' e' per
costruzione, stesso codice).

## 9. Copertura §6 e catalogo §7

§6: 6.1 stato del mercato tick per tick: ora anche CLOSED arriva allo scanner (prima no) - fatto.
6.2 scanner vero e feed di produzione - invariato, fatto. 6.3 `_run_event` vero a cadenza reale,
richieste della UI via `process_requests` - fatto; SETTLING via chiusura: visto nella
falsificazione, non negli scenari corretti (limite 8 del banco). 6.4 chiusura firmata con bet
delay e matching di flumine (5 abbinamenti, parziale 1,34+1,35) - fatto; sospensione vs chiusura
("su sospeso si aspetta, su chiuso si cambia strada") ora distinta anche per linea - fatto.
6.5 attivita' `mercato_deciso` con chiavi e tipi coerenti, nessun CHECK - fatto; colonne DB non
toccate. 6.6 concorrenza - non applicabile (una partita). 6.7 scenari con solo guasti/azioni
dell'utente, controllo con `quando`, sollecitazioni contate (M1 x24045), falsificazione rossa -
fatto. 6.8 referto riproducibile (comando, versioni, hash) - fatto. 6.9 velocita': sopra il tetto
per carico del PC - NON verificato a PC libero.

§7 (applicabili): 17 sospeso/chiuso - e' esattamente questo difetto (chiuso per UNA linea letto
come fermo o come partita finita): corretto e falsificato. 27 finti con chiavi vere - fatto.
28/29/30/35 test che asseriscono il giusto, che espongono la condizione e che diventano rossi -
10 mutazioni unitarie + 2 di replay, tutte rosse. 36 controllo che non dipende dalla confessione
del bot: M1 decide il caso dalla RIGA e dal modulo condiviso; usa l'attivita' del bot solo per la
parte "rifiuto `feed_stantio`", e la parte (a) e (c) leggono il feed e il contesto veri. 37 cache
di processo: `_RIPIEGO_REST_ULTIMO` gia' azzerata dal banco; `ctx.linee_decise` sta nella riga
dell'evento (non in RAM). 15/31 nessuno snapshot a mano, nessuna classe di laboratorio - fatto.
19 stato in RAM perso al riavvio - `linee_decise` persistita. 1-14, 16, 18, 20-26, 32-34: non
toccati da questo lavoro (nessun cambio a ordini, riconciliazione, DB, modalita', frontend logico).

## 10. Divergenze dalla strategia

Nessuna. Non ho toccato soglie, stake, tetti, gambe, finestre delle uscite, modello P(4),
`cover_form`. Uscite in perdita: restano proposte da firmare (G2 ora sollecitato e verde); in
profitto: automatiche. Nota per l'utente (non cambiata): dopo il quarto gol la "P(4) di mercato"
(`feed.implied_p4`) resta non calcolabile perche' vuole il libro del 3,5 (indagine, domanda 2):
e' un ingresso della strategia, decide l'utente.

## 11. Da controllare in paper al prossimo avvio

Partita coperta che arriva a 4 gol: in `mike_activity` UNA riga `mercato_deciso` (market `OU35`,
`stato_mercato` SUSPENDED o CLOSED, `esito {"OU35|UNDER": "persa"}`); NESSUN `flusso_interrotto`
con `mercati` = id del 3,5; nessun `settle`/`settling_reverted` finche' il 4,5 e' aperto; le
proposte d'uscita continuano e una firma produce `uscita_eseguita_su_approvazione` e una banca
sull'Over 4,5 (nessun `no_fill` con `reason: feed_stantio`).

## 12. COSA NON HO POTUTO VERIFICARE

- Replay a PC libero: tutti i miei replay hanno girato col PC al 100 % per altri processi; non
  posso dire se il totale sta nei 9-10 minuti. Da rilanciare dal coordinatore.
- Frontend: `tsc`, `vitest`, `npm run build` non eseguiti (nessun `node_modules` nel worktree, e
  il frontend era fuori perimetro). Le due righe sono solo dati (array `as const` e `Record<string, ...>`).
- Replay con `--trasporto entrambi` (coperture su coda e canale, come fa `replay_mike.sh`) non
  lanciato: il brief chiedeva il solo `--scenari tutti --trasporto canale`.
- Che lo scanner di PRODUZIONE scriva davvero CLOSED nel blocco (dedotto dal codice
  `_apply_opp_book`, come nell'indagine; nel banco ora lo fa la stessa funzione). Da vedere in paper.
- Il regolamento a fine gara nel replay (limite 8 del banco: `read_book` None sui mercati chiusi).
- Il ramo live dell'esecuzione (paper sul canale soltanto; parita' per costruzione).
- Regola "OR MATCH_ODDS CLOSED" nello `status_closed`: lasciata come prima (MO solo come ripiego
  dello stato del blocco); se il coordinatore la vuole esplicita, e' una riga.

## 13. File toccati

Modificati: `Betfair/mike/feed.py`, `Betfair/mike/service.py`, `Betfair/mike/certificazione.py`,
`Betfair/mike/tools/replay_registrazioni.py`, `Betfair/mike/tests/test_mike_audit_2026_09_11.py`,
`frontend/src/lib/mike.ts` (fuori perimetro, sezione 3).
Nuovi: `Betfair/mike/tests/test_mike_indagine_mercato_deciso_2026_09_29.py` (dalla patch
dell'indagine, invariato), `Betfair/mike/tests/test_mike_mercato_deciso_2026_09_30.py`,
`AUDIT_2026-09-30/` (questo referto, patch, referto del replay, confronto, falsificazioni).
Da NON committare: `_tmp_delegato/` nel worktree (script di falsificazione, ambiente neutro,
output grezzi dei replay).
