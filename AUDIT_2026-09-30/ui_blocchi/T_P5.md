# T_P5 - Chip dei bot e impianto in parole da trader (B5)

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a4993b702a303cacc`
Base: `1d058a7`. Nessun commit. Patch: `AUDIT_2026-09-30/ui_blocchi/T_P5.patch` = diff CUMULATIVO di `frontend/` (P3+P4+P5).

## 1. PRIMA -> DOPO a schermo

| Prima | Dopo |
|---|---|
| chip `Omega paper · senza spinta` (bot fermo) | `Omega` / `SPENTO · ultimo modo paper · fermo: non invia aggiornamenti` (grigio, pallino grigio) |
| chip `Mike LIVE · 1 s` | `Mike` / `LIVE · aggiornato 1 s fa` (LIVE rosso) |
| chip di un bot ACCESO senza notizie / oltre la sua cadenza: `senza spinta` o l'eta' in arancione | `ACCESO MA MUTO da 2 min` (rosso, pallino rosso); senza nessuna notizia `ACCESO MA MUTO: nessun aggiornamento ricevuto` |
| `Scalper calcio modalità ignota · senza spinta` | `SPENTO · ultimo modo paper · fermo: non invia aggiornamenti` (modo dall'interruttore `servizio.mode`) |
| modalita' davvero non dichiarata di un bot acceso | `modalità ignota` (ambra) - invariato come significato |
| `Runner in streaming · live+paper` | `Runner in streaming · ordini veri consentiti` (tooltip: «tetto del file di configurazione del runner (LIVE_ORDER_MODE): cosa PUO' servire. Con che soldi opera ogni bot lo dicono i chip dei bot e la riga "Ordini reali"») |
| `Runner tennis vivo, in attesa · paper` | `... · solo simulati` |
| `feed rest 6 s` (grigio) | `Quote dello scanner RIPIEGO REST (stream fermo) 6 s` (ambra); `stream` verde |
| `canale locale · stato canale · righe Omega db 7 s Safe canale 0 s Mike db 7 s Tennis db 7 s` | una riga `Dati: tempo reale` (verde) oppure `Dati: dal database (ogni 30 s) per: Omega, Mike, Tennis` (ambra) + `dettaglio` (un `<details>` con TUTTO il testo tecnico di prima, stessi `data-testid`) |

La riga «stato canale N s» sotto i chip di Omega/Safe/Mike (`cr-bot-fonte-*`) resta com'era (testid e test esistenti).

## 2. Fonti

- Modo: `vm.bots[].modalita` (`control.mode` del servizio). Scalper spento: nuovo `statoBotScalper().ultimoModo` =
  modalita' delle sessioni vive, altrimenti `servizio.mode` dell'interruttore (`lib/scalperControlRoom.ts`), esposto
  come campo OPZIONALE nuovo `StatoBot.modalitaUltima` (solo lo scalper lo valorizza).
- Aggiornato: `etaPushS` (canale), altrimenti eta' di `battitoAt`; muto/fresco = `freschezzaPush` gia' calcolata dal
  hook con `freschezzaBattito(..., stats.cadenza_battito_s)` (cadenza DICHIARATA dal servizio): nessuna soglia nuova.
- Runner: `r.mode` = `betfair_live_heartbeat.mode` / battito del canale = `heartbeat_mode()` (`Betfair/stream/runner.py:2176-2192`:
  `LIVE+PAPER` se `LIVE_ORDER_MODE=LIVE`, altrimenti il valore del .env).
- Feed: `safe_strategy_status.payload.source` (`vm.feedSorgente`).
- Dati: `vm.fonteScan`, `vm.fonteStatoScanner`, `vm.fonteRighe` (invariati).

## 3. File

Toccati in P5: `pages/ControlRoom.tsx` (ChipBot, Runner, riga feed, costante `TONO_CLS` al posto di
`EtichettaModalita` rimossa, import; `Modalita` non piu' importato), `components/controlroom/useControlRoom.ts`
(campo opzionale `modalitaUltima` in `StatoBot` + valorizzato per lo scalper), `lib/scalperControlRoom.ts`
(campo `ultimoModo`), `lib/scalperControlRoom.test.ts` (+1 test), `pages/ControlRoom.test.tsx` (2 test cambiati,
1 nuovo). Nuovi: `components/controlroom/testata/paroleImpianto.ts`, `paroleImpianto.test.ts`.

## 4. Test

- Nuovi: `paroleImpianto.test.ts` 11; `scalperControlRoom.test.ts` +1; pagina +1 (scalper spento, Mike LIVE, runner,
  riga Dati).
- Cambiati (perche' cambia il testo voluto):
  - `ControlRoom.test.tsx` «bot muto — canale caduto» (prima `/senza spinta/`): ora `/ACCESO MA MUTO/` e
    `not /senza spinta/` (bot acceso, canale caduto).
  - `ControlRoom.test.tsx` «la sorgente del feed è scritta» (prima `getByText('rest')`): ora
    `getByText('RIPIEGO REST (stream fermo)')` e classe ambra.
- Invariati e verdi: modalita' ignota (Omega acceso con modalita' null), runner (fasi, fonte), fonti di righe e stato
  scanner (1554-1572, 651/654): il loro testo e' nel `<details>`, nel DOM.
- `npx tsc -p tsconfig.app.json --noEmit` = 0; `npx vitest run src/pages/ControlRoom.test.tsx src/components/controlroom
  src/lib/scalperControlRoom.test.ts --maxWorkers=2` = **60 file, 937 test verdi** (305 s).
- `PannelloBotScalper.test.tsx` verde (nella cartella controlroom).

## 5. Falsificazioni (`T_falsificazioni/mut_p5.json`, `mut_p5b.json`)

| Mutazione | Esito |
|---|---|
| P5-1 torna «senza spinta» per il bot fermo | ROSSO 2 |
| P5-2 acceso e muto non segnalato | ROSSO 1 |
| P5-3 scalper spento senza ultimo modo | ROSSO 1 |
| P5-4 REST non in ambra | ROSSO 1 |
| P5-5 runner torna a scrivere «live+paper» | ROSSO 1 |
| P5-6 «Dati: tempo reale» anche con fonti dal database | ROSSO 1 |
| P5-7 il chip della pagina ignora l'ultimo modo | ROSSO 1 (pagina) |

## 6. COSA NON HO FATTO

- Colonna «STATO» esplicita (in funzione / in pausa / fermo): il chip dice LIVE/PAPER/SPENTO + aggiornato; lo stato
  fine (stopping, motivo del blocco) resta nella riga del bot in «Comando dei bot».
- «+1 partita in LIVE» quando una partita armata ha modo diverso dal bot (Omega/Mike): serve un dato per partita che
  la testata non ha gia' pronto (le partite vive di Mike hanno `mode`, Omega no).
- La riga «stato canale N s» sotto i chip: lasciata (e' dettaglio tecnico, ma coperta da test esistenti).
- I 4 bot tennis: stessa grammatica (passano da `ChipBot`), nessun trattamento proprio.

## 7. COSA NON HO POTUTO VERIFICARE

- L'app a schermo: compattezza della testata sticky con i tre blocchi (fascia soldi, stop, chip + impianto).
- Che `servizio.mode` dell'interruttore scalper sia sempre valorizzato a bot spento (dal tipo e' `string` obbligatorio).
- Che «ordini veri consentiti» per `LIVE` (riga vecchia, prima di F0) sia esatto anche per i runner vecchi: e' il
  tetto live, quindi si'; per un valore sconosciuto scrivo `tetto <valore>`.


---

# T_P5b - correzione del reperto sul chip dei bot fermi

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a4993b702a303cacc`, base `1d058a7`.
Patch CUMULATIVA di `frontend/`: `AUDIT_2026-09-30/ui_blocchi/T_P5b.patch` (`git apply --check -R` OK). Nessun commit.

## PRIMA -> DOPO (chip `cr-bot-<bot>`)

| Caso | Prima (T_P5) | Dopo |
|---|---|---|
| Mike `stopped`, `mode=live`, `stop_ferma_solo_aperture=true`, battito 10 s fa | `SPENTO · ultimo modo live · aggiornato 10 s fa` grigio, pallino grigio | `FERMO · LIVE · aperture ferme · uscite attive · aggiornato 10 s fa`: LIVE in rosso, «uscite attive» in teal col title «aperture ferme. Le posizioni già aperte restano sorvegliate: coperture, green-up, cash out e regolamento continuano», pallino rosso attenuato (`fermo-live`) |
| bot `stopping` | `SPENTO · …` | `IN ARRESTO · <modo> · …` (ambra) |
| bot `error` | `SPENTO · …` | `ERRORE · …` (rosso) |
| bot `idle` | `SPENTO · …` | `INATTIVO · …` |
| stato non letto (`stato` null) | `SPENTO` / nulla | `stato non letto` (ambra) |
| Safe fermo in paper, stop non dichiarato | `SPENTO · ultimo modo paper` | `FERMO · PAPER · …`, nessuna frase sulle uscite, pallino grigio |
| scalper senza sessioni, interruttore paper | `SPENTO · ultimo modo paper` | `FERMO · ultimo modo paper` («ultimo modo» solo qui: viene dal ripiego `modalitaUltima`) |
| bot running | `LIVE · aggiornato …` | invariato: nessuna parola di stato in più |

Le parole vengono da `botStatusMeta` / `BOT_STATUS_META` (`lib/tradeStatus.ts`, DESIGN_SYSTEM §2).
«fermo: non invia aggiornamenti» compare solo se non c'è né push né battito; se il battito c'è, si scrive l'età (come prima).

## Coerenza con PannelloBot

- **Frase sulle uscite:** `PannelloBot.tsx:740-749` ha già la frase per `stopFermaSoloAperture` (title del pulsante «ferma»: «Le posizioni già aperte restano sorvegliate: coperture, green-up, cash out e regolamento continuano»). La riuso IDENTICA nel title (`USCITE_ATTIVE_TITOLO` in `paroleImpianto.ts`: è una copia, perché `PannelloBot` è fuori perimetro e non posso esportarla da lì). Il testo corto visibile è «aperture ferme · uscite attive».
- **Parole di stato:** `PannelloBot.tsx:56-63` (`STATO_TESTO`) usa parole diverse da `botStatusMeta`: «in esecuzione / sta fermandosi / fermo / in errore / stato non letto». Il chip segue la tua indicazione (`botStatusMeta`: IN ARRESTO / FERMO / ERRORE / INATTIVO). Per avere una parola sola per lo stesso stato, `PannelloBot` andrebbe allineato a `botStatusMeta`: è fuori dal mio perimetro, lo segnalo.

## File (solo P5b)

- `testata/paroleImpianto.ts`: `modoChip` riscritta (niente più `inCorsa`, niente «SPENTO»); nuovi `statoChip`, `usciteChip`, `pallinoChip`, `USCITE_ATTIVE_TITOLO`.
- `pages/ControlRoom.tsx`: `ChipBot` (stato, modo, uscite, pallino) e costante `PALLINO_CLS`.
- `testata/paroleImpianto.test.ts`: casi di `modoChip` riscritti, più 4 test nuovi.
- `pages/ControlRoom.test.tsx`: il test T_P5 dello scalper ora attende «FERMO · ultimo modo paper» e NON «SPENTO»; 1 test nuovo T_P5b.
- Nuovi testid: `cr-bot-statoservizio-<bot>`, `cr-bot-uscite-<bot>`; attributo `data-pallino`.

## Test

- **Test nuovo di pagina (T_P5b):**
  - Mike `stopped`, live, `stopFermaSoloAperture: true`: il chip contiene FERMO, LIVE con classe rossa, «uscite attive», «aggiornato 10 s fa» e pallino `fermo-live`; NON contiene «SPENTO» né «ultimo modo».
  - Omega `stopping`: IN ARRESTO.
  - Safe fermo in paper senza dichiarazione: nessuna frase sulle uscite, pallino `fermo`.
  - `tennis_pro` in `error`: ERRORE.
- `npx tsc -p tsconfig.app.json --noEmit` = 0.
- `npx vitest run src/components/controlroom/testata/paroleImpianto.test.ts src/pages/ControlRoom.test.tsx --maxWorkers=2` = 2 file, 130 test verdi.

## Falsificazioni (`T_falsificazioni/mut_p5c.json`, copia → mutazione → ripristino con hash; `git diff --stat` identico prima e dopo)

| Mutazione | Esito |
|---|---|
| P5b-1 LIVE di un bot fermo torna «ultimo modo live» grigio | ROSSO 4 |
| P5b-2 `stopping` scritto FERMO | ROSSO 2 |
| P5b-3 uscite affermate senza dichiarazione del servizio | ROSSO 2 |
| P5b-4 fermo in LIVE grigio come il paper | ROSSO 2 |
| P5b-5 stato non letto scritto SPENTO | ROSSO 1 |
| P5b-6 ERRORE non rosso | ROSSO 1 |

## Cosa non ho verificato

- L'app a schermo.
- La cartella intera `components/controlroom` non l'ho rilanciata per il tempo: il `ChipBot` lo montano solo la pagina e i suoi test, lanciati. In T_P5 era verde (60 file, 937 test).

## Verifica del coordinatore UI (admin-07), 30/09 19:34
- `T_P5.patch` in QUESTA cartella = INCREMENTALE ricavato da me sul master `e5ec3c9` e contiene T_P5 GIA' CORRETTO (T_P5 + T_P5b): 7 file; tre vie senza conflitti.
- Reperto MIO sul primo T_P5, corretto in T_P5b: un bot non `running` era scritto «SPENTO · ultimo modo live» in grigio (caso di stasera: Mike fermo in live con posizione aperta). Ora: parole di `botStatusMeta` (FERMO / IN ARRESTO / INATTIVO / ERRORE, «stato non letto»), LIVE col suo tono anche a bot fermo, «aperture ferme · uscite attive» solo se il servizio dichiara `stop_ferma_solo_aperture`, «ultimo modo» solo per lo scalper senza sessioni.
- Numeri miei: albero integrato col primo T_P5: tsc 0, 71 file / 1080 test; con T_P5b: testata + `ControlRoom.test` 183 verdi; sul master `e5ec3c9` + T_P5: tsc e test in `tsc_INTEGRA_master3` (vedi messaggio di consegna).
- Mutazioni MIE, ROSSE, ripristino da copia: stato `stopping` trattato come running (2 rossi); stato non letto scritto «FERMO» (1).
- Test esistenti cambiati (testo voluto): «bot muto» da «senza spinta» a «ACCESO MA MUTO»; «sorgente del feed» da `rest` a «RIPIEGO REST».
- Da allineare domani (fuori da questo blocco): `PannelloBot.tsx` (`STATO_TESTO`) usa parole diverse da `botStatusMeta` per gli stessi stati.
- Non verificato: l'app a schermo (la testata sticky ora e' piu' ricca: va guardata su schermo stretto).
