# D-4 (gate-aperto tennis: esporre) e D-6 (Cash Out: sezione «Concluse») - referto del delegato (08/10/2026 sera)

Worktree `C:\Users\Admin\Desktop\PYTHON DATABASE\wt-ui`, ramo `cantiere-ui-sera` nato da master `d257abea`,
junction a `.venv` e `frontend\node_modules` del checkout principale (NON smontato). Nessun commit, nessun
`git add`, nessun `npm install`, nessun `npm run build`. Checkout principale non toccato (solo un replay
PRIMA lanciato in lettura dal suo codice, con `PYTHONDONTWRITEBYTECODE=1`).

## 1. Diff file per file

### D-4 - gate-aperto del banco tennis
- `Betfair/stream/tennis_live/tools/replay_bot.py`
  - `_MENU_TENNIS` (catalogo `parametri_modificabili`): + scalper `warmup_ms` («Osservazione prima di
    quotare», Tempi, int 0..120000 passo 1000 ms); + pro `price_min` (Ingresso 1,01..5 passo 0,01),
    `min_book_size` («Size minima alla quota di ingresso», Filtri 0..2000 EUR); + flb `min_lay_size`
    («Size minima alla miglior quota banca», Filtri 0..2000 EUR); + swing `conf_ticks` («Tick di conferma
    dell'inversione», 1..10), `price_min` (1,01..5), `price_max` (1,5..30), `min_matched` (0..500000
    passo 5000 EUR). Commento di testa aggiornato.
  - `SOGLIE_FUORI_CATALOGO` ridotto: restano scalper `min_matched` (non letta) e `min_total_matched`
    («gia' 0 nel preset del runner»), pro/flb/swing `min_total_matched` (non letta).
  - nuova `nota_parametri_dichiarati(extra, bot)` (pura): la nota «SCENARIO DICHIARATO» ora dice anche
    quali chiavi cambiate restano FUORI dalla scheda e perche' (prima diceva «numeri che l'utente puo' gia'
    cambiare dalla UI» anche per chiavi non a schermo: falso). `certifica_scenario` la usa (stessa
    condizione di prima, stesso ramo «stake»).
  - `parametri_scenario("gate-aperto", ...)`: NESSUN valore cambiato (test dedicato).
- `frontend/src/lib/replayBotCatalogo.ts`: RIGENERATO con `python -m Betfair.stream.backtest.applica_bot
  --catalogo-ts` (file generato; solo le voci nuove).
- `frontend/src/lib/tennis.ts` (`TENNIS_BOT_REGISTRY`, la scheda che l'utente vede e salva): stessi campi,
  stessi default di produzione (scalper `warmup_ms` 30000; pro `price_min` 1,08, `min_book_size` 10; flb
  `min_lay_size` 5; swing `conf_ticks` 2, `min_matched` 10000, `price_min` 1,08, `price_max` 8), limiti
  dentro quelli del catalogo, etichette e spiegazioni per un non tecnico. Stesso meccanismo di
  salvataggio (`TennisBotServiceParamsSheet` / `TennisBotPanel` leggono il registro: nessun codice nuovo).
  Il runner passa `params` al bot senza lista bianca (`tennis_runner._instantiate_bot`), e i quattro bot
  leggono `c.get(chiave, default)`: verificato a mano su `tennis_scalper_bot.py:417`, `tennis_pro_bot.py:158-159`,
  `tennis_flb_bot.py:90`, `tennis_swing_bot.py:82,98-100`.
- `Betfair/stream/tennis_live/tests/test_cantiere6_nomi_setup_gate_2026_10_08.py`: l'asserzione sulla
  testa del referto (fuori catalogo del pro) ora attende solo `min_total_matched`.
- NUOVI test: `Betfair/stream/tennis_live/tests/test_d4_gate_aperto_esposti_2026_10_08.py` (14) e
  `frontend/src/lib/tennisSchedaCatalogo.test.ts` (20: parita' scheda TS <-> catalogo del banco: stesse
  chiavi, stessi default di produzione, defaults SOLO dei campi, limiti dentro il catalogo, valori di
  gate-aperto impostabili, chiavi non lette mai a schermo). Prima non esisteva un confronto
  scheda-catalogo: esisteva solo `test_il_file_ts_del_catalogo_e_allineato_al_registro` (Python vs file
  generato), che resta verde.
- Fotografie: `tennis-terminal-match.{off,v2}.json` (conteggio parametri dei 4 bot 10/8/6/5 -> 11/10/7/9).

### D-6 - pagina Cash Out, sezione «Concluse»
- `components/controlroom/aperte/cashOutPagina.ts`: `faseEvento` controlla il Match Odds CLOSED PER PRIMO
  (prima: solo con `stato === 'chiusa'`; un `inplay` rimasto acceso nel feed lasciava la partita «in
  gioco»); `fase` resta `'gioco'` (per il filtro Pre-match/Live una conclusa e' gia' entrata in gioco,
  come prima). Nuovi: `SezioneScatola`, `sezioneScatola(s)`, `TESTO_CONCLUSA` = «conclusa · posizioni da
  regolare», `motivoCashOutConclusa(s)`.
- `pages/CashOut.tsx`: le tre liste si fanno con `sezioneScatola` (ogni scatola in UNA sola sezione);
  sezione «Concluse · posizioni da regolare» IN FONDO (motivo: niente da chiudere, solo da attendere il
  regolamento; le sezioni azionabili restano in alto), mostrata solo se ce n'e' almeno una (stato
  eccezionale: niente riquadro vuoto fisso) e mai col filtro Pre-match; riepilogo «N in gioco · M
  pre-match · K concluse» + «conclusa = Match Odds chiuso da Betfair».
- `components/controlroom/aperte/ScatolaCashOut.tsx`: testata della conclusa = «conclusa · posizioni da
  regolare» (al posto di `StatoPill`, che con `stato==='live'` avrebbe detto «in gioco»); riga col motivo
  `co-conclusa-motivo`; i pulsanti di cash out SPENTI col motivo: gamba dei bot (`RigaOperazione`), ordini
  fuori dai bot, posizione col conto, «Chiudi tutte le gambe dei bot», «Cash out Safe». ECCEZIONE
  dichiarata: lo SCALPER resta fermabile (il suo pulsante ferma la sessione, non piazza ordini sul
  mercato chiuso). `StatoPartitaRiga` usa la stessa regola (`nota === 'conclusa'`).
- Componenti condivisi, prop OPZIONALI con default identico a prima (Control Room invariata: fotografie
  `control-room.*` identiche): `BottoneChiudiRiga.spentoPerche` (riusa il meccanismo `chiudibile` ->
  `{ok:false, motivo}`: title «non chiudibile: ...», `data-motivo`), `RigaOperazione.chiudi.spentoPerche`,
  `CashOutGlobale(Partita).spentoPerche` (entra in `spentoPerche` del blocco, PRIMA di
  `motivoPrezziFermi`), `CashOutPartita.spentoPerche` (prima di `motivoCashoutSpento`; la conferma armata
  si spegne anch'essa). Nessun meccanismo nuovo: lo stesso «spentoPerche» dei pulsanti di soldi.
- Test: `cashOutPagina.test.ts` +4, `pages/CashOut.test.tsx` +11 (sotto «D-6: sezione Concluse»).
- Fotografie: `cash-out.{off,v2}.json` (riepilogo con «0 concluse» e la nota). `*.guscio.json` identiche.

## 2. Chiavi di gate-aperto: esposte / non esposte

| bot | chiave | prod -> gate-aperto | esito | causa |
|---|---|---|---|---|
| tennis_scalper | warmup_ms | 30000 -> 0 | ESPOSTA | letta (`c.get('warmup_ms', flow_window_ms)`, preset runner 30000) |
| tennis_scalper | min_matched | - -> 0 | NON esposta | il bot NON la legge (nessun attributo) |
| tennis_scalper | min_total_matched | 0 -> 0 | NON esposta | il bot la LEGGE (`tennis_scalper_bot.py:364,1271`) ma lo scenario non ne cambia il valore (gia' 0 nel preset): il brief diceva «non letta» per tutti, per lo scalper non e' cosi'; non esposta perche' fuori dal perimetro della decisione |
| tennis_pro | min_book_size | 10 -> 0 | ESPOSTA | letta (`tennis_pro_bot.py:158,590`) |
| tennis_pro | price_min | 1,08 -> 1,01 | ESPOSTA | letta (`:159,588`) |
| tennis_pro | min_total_matched | - | NON esposta | non letta |
| tennis_flb | min_lay_size | 5 -> 0 | ESPOSTA | letta (`tennis_flb_bot.py:90,384`) |
| tennis_flb | min_total_matched | - | NON esposta | non letta |
| tennis_swing | conf_ticks | 2 -> 1 | ESPOSTA | letta (`tennis_swing_bot.py:82,686`) |
| tennis_swing | min_matched | 10000 -> 0 | ESPOSTA | letta (`:98,661`) |
| tennis_swing | price_min / price_max | 1,08 / 8 -> 1,01 / 30 | ESPOSTE | lette (`:99-100,685`) |
| tennis_swing | min_total_matched | - | NON esposta | non letta |

## 3. Test (esiti veri, nel worktree)
- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori**.
- pytest `Betfair/stream/tennis_live` + `Betfair/stream/tests/test_applica_bot*`, `test_registro_bot*`,
  `test_certifica*`, `test_cert_banco*`, `test_replay_scalper_attiva*`: **1265 passati, 12 saltati, 5 xfail,
  0 falliti** (139,8 s).
- `npx vitest run` intero: **5478 passati / 7 falliti / 51 saltati** (379 file, 12 min). I 7: 1 fotografia
  `tennis-terminal-match` (MIA: conteggio dei parametri, fotografia rigenerata dopo, poi `src/fotografia`
  42/42 verde) + 6 in `replayVerificaBarraFixture/Script.test.ts` (script lanciati davvero, sotto carico):
  rilanciati da soli **13/13 verdi**; non toccano nessun file di questo lavoro. Riferimento del brief 5450:
  +28 sono i test nuovi (20 + 4 + 11, meno quelli gia' contati) e quelli entrati su master.
- Nuovi: Python 14/14, `tennisSchedaCatalogo` 20/20, `cashOutPagina` 18/18, `CashOut` 32/32.

## 4. Falsificazione (`AUDIT_2026-10-08/decisioni_sera/falsifica_d4_d6.py`, esiti in `falsificazione.txt`; ripristino con sha256 verificato a ogni mutazione)

| mutazione | esito |
|---|---|
| D4-M1 `warmup_ms` tolto dal catalogo Python | ROSSO |
| D4-M2 `price_min` del pro di nuovo fra le fuori catalogo | ROSSO |
| D4-M3 gate-aperto cambia un valore (swing conf_ticks 1->2) | ROSSO |
| D4-M4 nota senza le chiavi fuori scheda | ROSSO |
| D4-M5 catalogo TS non rigenerato (default warmup_ms 0) | ROSSO (vitest 1 e pytest `catalogo_e_allineato` 1; rieseguita a mano: l'ancora era doppia nello script) |
| D4-M6 `min_total_matched` fra i default della flb (senza campo) | prima SOPRAVVISSUTA -> aggiunto il controllo «defaults SOLO dei campi» -> ROSSO |
| D4-M6b campo `min_total_matched` nella scheda flb | ROSSO (4) |
| D4-M7 default swing conf_ticks 3 | ROSSO |
| D4-M8 quota min del pro da 1,05 (gate 1,01 non impostabile) | ROSSO |
| D4-M9 `warmup_ms` tolto dalla scheda | ROSSO (4) |
| D6-N1 CLOSED controllato dopo `live` (ordine di prima) | ROSSO (2) |
| D6-N2 `sezioneScatola` ignora la conclusa | ROSSO (7) |
| D6-N3 In gioco per `fase` (doppione con Concluse) | ROSSO (7) |
| D6-N4 Concluse anche col filtro Pre-match | SOPRAVVISSUTA: mutante EQUIVALENTE (con Pre-match `filtraScatole` ha gia' tolto le concluse: la guardia nella pagina e' ridondante, tenuta per simmetria con le altre sezioni) |
| D6-N5 StatoPill al posto del testo della conclusa | ROSSO |
| D6-N6 motivo non passato al pulsante della gamba | ROSSO (2) |
| D6-N7 `BottoneChiudiRiga` ignora `spentoPerche` | ROSSO (2) |
| D6-N8 scalper spento anche lui | ROSSO |
| D6-N9 ordini fuori dai bot: cash out acceso | ROSSO |
| D6-N10 posizione col conto: cash out acceso | ROSSO |
| D6-N11 «Chiudi tutte le gambe» ignora il motivo | ROSSO |
| D6-N12 Safe: cash out acceso | ROSSO |
| D6-N13 riepilogo senza le concluse | ROSSO (2) |

Finti: `PartitaGiornata`, `OperazionePartita`, `PosizioneAperta`, `OrdineContoFuoriBot`, `MikeEvent` con le
chiavi vere (fabbriche gia' esistenti dei due file di test); ladder `LiveLadderRow` della finta esistente;
lato Python l'istanza VERA del bot da `_instantiate_bot` (`_bot_dello_scenario`).

## 5. Replay tennis (banco comune, codice di produzione)
Durata dichiarata e misurata: gate-aperto,base ~31 s a processo; `--scenari tutti` 56-81 s (tetto 600 s).
- `certifica tennis_swing 35790089 --data-dir C:\Users\Admin\Desktop\tennis_rec\20260707 --scenari
  gate-aperto,base --worker 1`, PRIMA (codice di master `d257abea`, checkout principale) vs DOPO
  (worktree): **3 righe diverse**, tutte attese: impronta «codice bot» (cambia `replay_bot.py`), testa
  «FUORI dal catalogo della UI (dichiarati): min_total_matched» (prima: conf_ticks, min_matched,
  min_total_matched, price_max, price_min), nota SCENARIO DICHIARATO veritiera. Numeri (tick, decisioni,
  azioni, stati, residui, controlli) IDENTICI.
- `--scenari tutti`, PRIMA vs DOPO: **12 righe diverse**: impronta, testa, e la nota dichiarata nei 10
  scenari coi gate (gate-aperto, rifiuti-betfair, live, chiusura-abbinata-in-parte, chiudi-ora,
  uscite-manuali, uscite-manuali-firmate, soldi-veri, soldi-veri-prova, soldi-veri-paper). Nessun numero.
- Contro il riferimento `AUDIT_2026-10-07/riferimenti_coordinatore/finale/tennis_finale_tennis_swing.txt`:
  le differenze NUMERICHE sono gia' tutte su master PRIMA del mio lavoro (identiche PRIMA/DOPO), es.
  gate-aperto/live/soldi-veri azioni 126 -> 116, chiusura-abbinata-in-parte 134 -> 117, chiudi-ora 34 -> 33,
  uscite-manuali 168 -> 133, uscite-manuali-firmate 118 -> 147, oltre a testa/controlli (22 -> 23) dei
  cantieri 6/9. NON ho verificato a quale cantiere (5/6/9) appartenga ciascuna: da attribuire dal
  coordinatore. File: `AUDIT_2026-10-08/decisioni_sera/replay_swing/`.

## 6. Non verificato / limiti
- Prova a schermo nell'app desktop (scheda dei 4 bot tennis con i campi nuovi; pagina Cash Out con una
  partita conclusa): la fa l'utente dopo `npm run build`.
- Replay solo di `tennis_swing` (come chiesto); scalper/pro/flb non rigiocati: il loro gate-aperto non
  cambia valori (test `test_gate_aperto_non_cambia_valori`), cambiano solo testa e nota allo stesso modo.
- Salvataggio reale su `tennis_bot_service_control.params` non provato contro il DB: il meccanismo e'
  quello di sempre (nessun codice nuovo), le chiavi nuove viaggiano come le altre.
- Effetto pratico per l'utente: salvando la scheda di un bot dopo questo lavoro, la colonna `params`
  riceve anche le chiavi nuove coi valori di produzione (comportamento del bot invariato finche' non
  cambia un numero).
- Mutante equivalente D6-N4 e la scelta di tenere lo scalper fermabile sulla conclusa: dichiarati.

## Blocco per la cronostoria

```
- DECISIONI SERA D-4 + D-6 (delegato, worktree wt-ui ramo cantiere-ui-sera da d257abea, NON committato).
  D-4 «esporre»: le soglie di gate-aperto che i bot tennis LEGGONO sono ora nel catalogo del banco
  (replay_bot._MENU_TENNIS, replayBotCatalogo.ts rigenerato) e nella scheda TS (TENNIS_BOT_REGISTRY):
  scalper warmup_ms; pro price_min, min_book_size; flb min_lay_size; swing conf_ticks, min_matched,
  price_min, price_max (default di produzione, limiti che contengono i valori del banco).
  SOGLIE_FUORI_CATALOGO ridotto alle sole non lette/invariate (min_total_matched di tutti, min_matched
  dello scalper); nota SCENARIO DICHIARATO veritiera; valori di gate-aperto INVARIATI. Nuovo test di
  parita' scheda<->catalogo (tennisSchedaCatalogo.test.ts).
  D-6 «sezione apposta»: Cash Out con terza sezione «Concluse · posizioni da regolare» (in fondo; TUTTE e
  SOLE le partite col Match Odds CLOSED, anche con inplay acceso), testo «conclusa · posizioni da
  regolare», cash out spenti col motivo (gamba, fuori bot, posizione col conto, Chiudi tutte, Safe;
  scalper fermabile), filtri invariati. Prop opzionali additive su BottoneChiudiRiga/RigaOperazione/
  CashOutGlobale/CashOutPartita (Control Room identica).
  tsc 0; vitest intero 5478 verdi / 7 rossi (1 fotografia mia rigenerata -> 42/42; 6 replayVerificaBarra
  sotto carico, 13/13 da soli); pytest tennis_live + collegati 1265/0; falsificazione 23 mutazioni: 21
  rosse, 1 sopravvissuta poi resa rossa (test rinforzato), 1 equivalente dichiarata. Replay swing 35790089
  PRIMA/DOPO: solo impronta, testa e nota dichiarata; nessun numero cambiato.
  DA FARE: build ad app chiusa, prova a schermo dell'utente; attribuire le differenze numeriche
  riferimento 07/10 -> master (gia' presenti prima di questo lavoro).
```
