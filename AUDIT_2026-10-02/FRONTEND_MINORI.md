# FRONTEND MINORI (02/10/2026) - punti 31, 32, 33, 35, A, B, C, 30

Delegato Opus, worktree isolato, ramo locale `frontend-minori` partito da `61f73a6`
(base indicata dal brief). Nel frattempo master e' avanzato a `9803700` (8 commit di sola
documentazione, nessun file di `frontend/` toccato): `git merge-tree master HEAD` pulito.
Patch: `AUDIT_2026-10-02/FRONTEND_MINORI.patch` = `git diff master...HEAD` (dalla base comune,
con i file nuovi). Nessun push, nessun commit su master, nessun `git add -A`, nessuna
junction, nessun processo lasciato acceso, nessun file del checkout principale toccato.

## Verifica finale (nel worktree, macchina scarica: unico node estraneo = Adobe CC)

| controllo | esito |
|---|---|
| `npx tsc -p tsconfig.app.json --noEmit` e `npx tsc --noEmit` | **0 errori** (exit 0) |
| suite intera `npx vitest run` | **317 file verdi / 10 saltati; 4848 test verdi / 50 saltati; 0 rossi** (736 s). Base: 316 / 4839 + 1 file nuovo + 9 test nuovi |
| fotografia `off` | `git diff 61f73a6 -- frontend/src/fotografia/snapshot` **vuoto**: nessuna fotografia rigenerata; 26/26 verdi |
| `npm run build` | exit 0; `dist/assets` 3.525.849 B (ramo veste nel referto di verifica: 3.522.996 B; +2.853 B = helmet 3 + 1 regola CSS). L'avviso "chunk size" c'era gia' |
| `npm ci` SENZA flag | exit 0, nessun warning di peer dependency |
| falsificazione | `falsifica_frontend_minori.py` -> **25/25 come atteso**, `git status` identico prima/dopo (`falsifica_frontend_minori_out.txt`) |

## 31. Fotografia fragile sotto carico

**Causa (riprodotta, non supposta).** Prova "prima": `vitest run src/fotografia src/pages/MarketWatch.test.tsx`
lanciato 5 s dopo un secondo `vitest run src/components` (161 file, stessa macchina):
**26 rossi su 44** (`fot_carico_prima_1`): `board` scaduto a 60 026 ms, poi 25 pagine con DOM VUOTO
(`titolo: ""`, `testi: []`) o chiamate a zero. Da sola, a cache fredda, `board` impiega gia' 42,7 s
(gli altri 4-5 s): la PRIMA `import('@/App')` trasforma tutto il grafo dei moduli. Sotto carico supera
i 60 s, il test scade ma la sua funzione resta viva in sottofondo e continua a montare/smontare l'app
(e a fare `cleanup()`, `azzeraRegistro()`, `replaceState`) mentre girano i test seguenti: la catena dei
26 rossi. Secondo difetto: `attendiStabile` accettava come "ferma" una pagina con DOM vuoto (spinner di
`ProtectedRoute`, nessun testo) se restava uguale 400 ms, e non guardava le chiamate al backend.

**Correzione** (`frontend/src/fotografia/fotografia.test.tsx`, solo il test):
- `:284` `beforeAll(async () => { await import('@/App'); }, 600_000)`: la trasformazione si paga una
  volta, fuori dal tempo dei test (poi `vi.resetModules` rivaluta senza ritrasformare).
- `:293` `TEMPO_PER_PAGINA_MS = 300_000` (era 60 000), `:295` `STABILE_ENTRO_MS = 120_000`.
- `:313-332` `attendiStabile`: scatta solo quando la pagina e' PRONTA (almeno un testo della pagina,
  `:321`) e FERMA: 5 letture uguali di fila del DOM **e** delle chiamate (nomi distinti rpc/tabelle,
  canali, WebSocket). Oltre 120 s errore esplicito col nome della pagina (prima: dopo 75 giri si
  scattava comunque, anche a meta'). Tempo misurato con `performance.now()` (Date e' finto e fermo).
- Asserzioni identiche (stesse 4 famiglie, stessi file di confronto); `chiamate` costruite dalla
  stessa funzione, stesso ordine delle chiavi.

**Numeri** (uscite in `AUDIT_2026-10-02/carico/`: `fot_carico_prima_1.txt`, `fot_carico_dopo_1.txt`,
`carico_components_*.txt`, `suite_intera_finale.txt`).

| prova | prima | dopo |
|---|---|---|
| fotografia + MarketWatch con `vitest run src/components` in parallelo | 26 rossi / 18 verdi (44) | **45/45 verdi** (`fot_carico_dopo_1`: 11:34:17-11:39:04, carico 11:34:01-11:40:10, 161 file / 2019 test verdi anche lui) |
| test piu' lento sotto carico | board 60 026 ms (scaduto) | control-room 14 187 ms, board 8 111 ms |
| fotografia da sola, macchina scarica | 39/39, 210 s | 40/40, 191 s (con helmet 3 e tutti i punti) |

**Falsificazione** (deterministica, "carico simulato" = sessione del finto a 1,5 s, pagina sullo spinner):
F1 fotografia di master -> ROSSO (`mike.off.json e' cambiata`); F1b fotografia corretta -> VERDE;
F2 fotografia corretta SENZA la condizione "pronta" -> ROSSO.

## 32. `src/pages/MarketWatch.test.tsx` fragile sotto carico

**Causa.** Tre letture indipendenti (follows, now, posizioni): sotto carico la riga compare prima delle
sue posizioni, e il test "paper e live" leggeva subito dopo `findAllByTestId` (`live€0.00` invece di
`€3.00`, gia' visto dalla sessione cloud); le `findBy*` avevano l'attesa di serie di 1 s; il test
"riga tennis" contava i bottoni cash-out appena visto il tennis, senza aspettare la riga calcio.
**Correzione** (solo il test): `:108` `ATTESA = { timeout: 10_000 }` su ogni `findBy*`; `:179`
`waitFor(..., ATTESA)` attorno alle stesse due asserzioni dei rischi; nel test tennis si aspetta anche
la riga calcio (`findByText('Milan – Inter')`) prima di contare: asserzioni identiche, nessun sleep.
**Falsificazione** (carico simulato: letture finte a 200/600/1500/300/700/900 ms, fuori ordine):
W1 test di master -> ROSSO (2: `expected 'live€0.00' to contain '€3.00'`, `mw-tennis-finita` non
trovato in 1 s); W1b test corretto -> VERDE 5/5; W2 corretto senza il `waitFor` -> ROSSO.
Sotto carico reale: 5/5 nella prova del punto 31.

## 33. `npm ci` senza `--legacy-peer-deps`

**Registro npm**: `react-helmet-async@3.0.0` (ultima) ha `peerDependencies.react = "^16.6.0 || ^17.0.0 ||
^18.0.0 || ^19.0.0"`; stesse dipendenze di 2.0.5 (`invariant`, `react-fast-compare`, `shallowequal`).
Scelta: aggiornare (nessuna sostituzione, nessun hook proprio). `npm install react-helmet-async@^3.0.0`
SENZA flag. Diff: `package.json:50` `^2.0.5` -> `^3.0.0`; `package-lock.json`: la voce del pacchetto
(versione, `resolved`, `integrity`, peer) e tre `"dev": true` -> `"devOptional": true` (`@types/react`,
`@types/react-dom`, `csstype`: ricalcolo di npm, nessuna versione cambiata). Nient'altro aggiornato
(`@types/react-helmet-async` stub lasciato com'e'). Prima: `npm ci --dry-run` sul lock di master ->
`ERESOLVE ... peer react@"^16.6.0 || ^17.0.0 || ^18.0.0" from react-helmet-async@2.0.5`. Dopo: `npm ci`
exit 0, nessun warning.
**Cosa cambia in 3.0 (README del pacchetto)**: con React 19 `<Helmet>` rende i `<title>` veri e li fa
portare in `<head>` da React; `HelmetProvider` diventa un passacarte; API invariata. Punti d'uso
verificati: `HelmetProvider` in `App.tsx:99` e `certification/sessB/util.tsx:13`; `<Helmet><title>` in
16 file (PageShell, Board, Dashboard, LadderPopout, LivePnl, MarketWatch, MatchReplay, MultiLadder,
ReportPersonale, SeguiLive, SelectSport, TennisDashboard, TennisTerminal, TradeJournal, Watchlist; uno
solo per pagina, figlio unico). Nessun uso di `titleTemplate`, `defaultTitle`, `htmlAttributes`,
`bodyAttributes`, `context`. I `<title>` dentro gli SVG (grafici) non sono di Helmet. Prova: la fotografia
registra `document.title` di 26 pagine con guscio spento e acceso: **identico** con 3.0.0 (40/40).

## 35. Foglio parametri Safe: campo numerico svuotato -> `""` nel DB

**Causa.** `ParamsSheetBase` mette `''` nel campo svuotato; `fromValues` faceva `setPath(out, key, '')`
(eccetto `risk.max_open_trades`, gia' corretto da R-06). Prova "prima" nel foglio vero: svuotati tutti i
campi, **62 chiavi `""`** nel payload (test UI rosso su master). Alla rilettura `toValues` faceva
`Number('')` = 0: il campo mostrava 0.
**Correzione** (`components/safestrategy/BotParamsSheet.tsx`): `:271` `CHIAVI_NUMERICHE` (le chiavi dei
7 elenchi di campi numerici del foglio, 64); `:353` `deletePath` (copia i nodi, la riga letta non si
muta); `:886` in `fromValues`: campo numerico con stringa vuota -> **chiave tolta** (assente = valore di
serie del servizio), coerente con R-06 (`SAFE_FOGLIO_TETTO.md`: assente, non `null`). Lato Python
verificato in lettura: `bot_service.resolve_params` (`:319-397`) parte da `DEFAULT_PARAMS`/motore e
applica `_f(v, default)`; `exits`/`risk` passano da `merge_exit_params`/`merge_risk_params`: chiave
assente -> default, come prima con `""`. Nessuna strategia e nessun valore non vuoto cambia.
**Test** (`BotParamsSheet.test.tsx:671`, finti = `RAW` del file + chiavi di produzione): (1) le chiavi
sono quelle del foglio: 64 = numero degli `input[type=number]` resi; (2) puro, per OGNI campo: vuoto ->
chiave assente, tutte le altre 63 identiche al salvataggio senza modifiche, nessun `""`/NaN nel payload,
riga letta non mutata; (3) foglio vero: svuotati tutti i 64 campi, salvato -> nessuna chiave numerica,
nessun `""`, resto del payload (chiave ignota, varianti, `exits.enabled`) invariato.
**Falsificazione**: M1 ramo tolto -> ROSSO (126 e 63 rilievi); M2 chiave del DB conservata invece di
tolta -> ROSSO; M3 elenco senza le uscite numeriche -> ROSSO (`expected 56 to be 64`).

## A. Mojibake in `components/live/ScalperPanel.tsx` (e controllo di tutto `src/`)

**Causa**: file UTF-8 riletto come cp1252 e risalvato UTF-8 (preesistente su master), con BOM.
Il mio rilevatore trova **71 righe, 89 sequenze**: le 85 del referto di verifica + 4 emoji
(`ðŸŽ¯`/`ðŸ”«`/`ðŸ”¬` alle righe 356, 379, 396, 424, che il rilevatore della verifica non contava).
**Ricerca nel resto del repo** (tutti i file tracciati di testo): nessun altro sorgente dell'app; solo
documenti AUDIT che citano il difetto e `AUDIT_2026-09-30/app_tabellone/falsifica_riga_tennis_inversa.py:16`
(cerca apposta `Ã—` nell'uscita di vitest mal decodificata: e' voluto, non toccato). BOM: solo ScalperPanel.
**Correzione**: `ripara_mojibake.py` ricodifica SOLO le sequenze cp1252 che ritradotte in byte sono UTF-8
valido, riga per riga, conservando i fine riga; toglie il BOM. Elenco riga per riga prima/dopo in
`ripara_mojibake_out.txt`. Prova indipendente `verifica_mojibake.py`: riguastando il file riparato si
ottiene master **riga per riga** (71 cambiate, 0 non spiegate dal mojibake, stesse 675 righe) e i **40**
testi attesi del par. 11 della verifica ci sono tutti (es. `:311` `Stake €`, `:546` `` `€${...}` ``,
`:162` `piazzerà ... (stake €${stake})`, `:627` `Nessuna attività ancora…`).
**Test** nuovo `src/test/codificaSorgenti.test.ts` (ASCII, sequenze scritte come `\u`): controprova
(6 sequenze guaste riconosciute, testo italiano buono `€ à è… — ⚠️ · → « » ≥ −` mai accusato),
nessun sorgente di `src/` (ts/tsx/css/html/json) con mojibake, nessuno col BOM.
Falsificazione: A1 riga 311 rimessa guasta -> ROSSO; A2 BOM rimesso -> ROSSO; A3 (direzione nuova)
mojibake in un altro file (`index.css`) -> ROSSO.

## B. Due bottoni "Parametri" identici sulla riga "Safe base"

**Causa** (riletta sul codice): `PannelloBot.tsx:668-673` rende sulla stessa riga `parametriRiga`
(foglio della sola strategia, `ControlRoom.tsx:470-482`) e, perche' `safe-base` e' la prima riga del
bot (`righeBot.ts:108`), `parametri.safe` (foglio dell'intero servizio, `ControlRoom.tsx:423-433`).
Correzione al referto di verifica: il bottone NON e' quello di `safestrategy/ParamsSheet.tsx:259`, ma
quello di `ParamsSheetBase.tsx:198-199` (`triggerLabel = 'Parametri'` di serie).
**Correzione**: `BotParamsSheet.tsx:515/520/768` nuova prop `triggerLabel` passata a `ParamsSheetBase`
(assente = "Parametri", quindi pagina Safe Strategy invariata); `ControlRoom.tsx:429-430` foglio del
servizio intero: **"Parametri comuni di Safe"** (stesse parole della descrizione del foglio di strategia,
"parametri comuni di Safe"), testid `cr-safe-params-trigger` (era il generico `params-trigger`);
`ControlRoom.tsx:480` fogli delle 4 strategie: **"Parametri strategia"** (testid gia' distinti
`cr-safe-<s>-params-trigger`). Fotografia: la Control Room del finto non legge parametri (mostra
"parametri non letti"), quindi nessuna fotografia cambia (verificato 26/26 senza rigenerare).
**Test** (`ControlRoom.test.tsx:2282`): per ogni `cr-bot-riga-*` nessun nome di comando ripetuto (e
almeno un comando in piu' delle righe); riga safe-base con i due testid e i due testi; riga safe-esatto
con il solo foglio di strategia. Rosso su master (`cr-bot-riga-safe-base: "Parametri"`).
Falsificazione: B1/B2 un'etichetta tolta -> ROSSO; B3 `triggerLabel` non passato -> ROSSO.

## C. "LIVE · REALE" del Tennis Terminal a guscio acceso

**Causa**: `TennisTerminal.tsx:187` ha `bg-red-500 text-white ds-v2-chip--live`; a guscio acceso
`[data-shell="v2"] .ds-v2-chip--live` (specificita' maggiore) lo portava a sfondo rosso al 14 % e testo
rosa. **Correzione** solo CSS (`index.css:1156-1159`): `[data-shell="v2"] .ds-v2-chip--live.bg-red-500
{ background-color: #dc2626; border-color: #f87171; color: #ffffff; }`: dove oggi il marcatore e' rosso
pieno, resta rosso pieno. Rosso 600 (come "Confermo: soldi veri" della veste) perche' bianco su rosso 500
fa 3,76:1, sotto il 4,5:1 che la guardia della veste pretende; su rosso 600 fa 4,83:1. A guscio spento
non cambia nulla: selettore sotto `[data-shell="v2"]` (guardie `cssVeste`/`cssGuscio` verdi), fotografia
26/26 identica. Gli altri due marcatori `ds-v2-chip--live` (PannelloBot:611, FasciaStop:75) oggi sono
gia' tinta (`bg-red-500/20 text-red-300`) e restano come la veste li ha fatti.
**Test** (`cssVeste.test.ts:231`): per ogni marcatore `ds-v2-chip--live` del codice (3 trovati) calcola
la resa a guscio acceso (regole della veste applicabili alle sue classi, ordinate per specificita' e
posizione) e pretende: contrasto >= 4,5:1 su tutti i fondi della pagina, rosso visibile (sfondo o testo
composti sul fondo), e sfondo rosso PIENO dove oggi e' pieno. Rosso su master (`TennisTerminal ... alfa
0.14`). Falsificazione: C1 regola tolta, C2 sfondo al 50 %, C3 testo rosa su rosso -> ROSSO; C4
(direzione nuova) i marcatori tinta diventano grigi -> ROSSO (al primo giro il test passava: giudicava
il rosso sull'RGB senza alfa; corretto per giudicare il colore composto, poi 25/25).

## 30. Rilievi bassi della review del 01/10

- **R-07** (frontend): GIA' corretto su master prima di questo lavoro: `FasciaStop.tsx:59-61`
  "Tennis e Scalper: nessuno stop giornaliero proprio ... Lo Scalper ha in piu' due tetti suoi",
  test `FasciaStop.test.tsx` (RILIEVI_BASSI.md riga 8). Nulla da fare.
- **R-08** (frontend, `lib/chiuseGiornata.ts:190-213` `posizioniDellaGiornata`, usato da
  `PosizioniChiuse.tsx:197-211`): **NON corretto**. Una posizione in memoria senza giorno del DB, la cui
  chiusura (`chiusaAt`, che preferisce l'istante di Betfair `pnl_betfair_settled_at`) e' di oltre 5 min
  prima della lettura, finisce per al massimo una scadenza (60 s) in "altre giornate". Una correzione
  giusta deve sapere QUANDO la riga e' stata scritta nel DB (la lettura non poteva vederla): quel dato
  non c'e' nel tipo (`TradeChiudibile` non porta `created_at`/`updated_at`); usare `settled_at` del bot
  richiede di accertare nel Python chi scrive quale istante. Toccare l'attribuzione del giorno dei soldi
  senza quella prova rischia una regressione; la review e chi l'ha rilasciato consigliano "nessuna".
  Decisione da portare all'utente (proposta: escludere solo se `max(settled_at, pnl_betfair_settled_at)`
  e' anteriore al margine, dopo aver verificato nei servizi che `settled_at` e' l'istante di scrittura).
- **R-10** (frontend, `pages/Omega.tsx:153/156-166/863-864`): **NON corretto**. Nel flusso normale lo
  Storico e' dentro `loading ? ... :` (`:599`) e `loading` va a false dopo `setControl` (`:178-198`).
  Solo se la PRIMA lettura fallisce (`:249`) la pagina intera resta su `mode = 'paper'` e lo Storico
  chiede e dichiara PROVA: cifre ed etichetta coincidono (nessuna mescolanza, nessuna etichetta falsa
  sulle cifre mostrate). La correzione ("moneta non letta") tocca `TradingHistory` (componente
  condiviso) e i due fetcher: non e' minima. Lasciato, come la review.

## Reperti nuovi (NON corretti: fuori dai punti assegnati)

1. **Foglio Safe, due campi che si mostrano falsi** (`BotParamsSheet.tsx:234` e `:732`):
   `exits.base_control_exit` (interruttore) e `exits.base_control_exit_max` (soglia) non sono in
   `ExitsParams`/`mergeExits` (`:83-131`), quindi `toValues` non li legge mai: il foglio mostra
   l'interruttore SPENTO e la soglia vuota qualunque cosa ci sia nel DB (il servizio li legge:
   `exits.py:80-81, 308-311, 984-990`). Salvare senza toccarli conserva il valore del DB (si riparte da
   `raw`). Se nel DB l'uscita fosse ACCESA il foglio direbbe il falso. Il mio test UI li svuota passando
   prima da '1' proprio per questo.
2. **Stesso difetto del punto 35 negli altri fogli**: Omega `lib/omega.ts:1273-1282`
   (`omegaParamsPatch`: `''` diverso dal valore -> scritto `""`); Mike `lib/mike.ts:619-620`
   (`Number('')` = 0 -> campo svuotato salvato al MINIMO del campo, non al valore di serie); bot tennis
   `components/tennis/TennisBotServiceParamsSheet.tsx:107-108` (`Number('')` = 0 -> salvato 0).
   Per Mike e tennis e' piu' grave di Safe: il valore cambia davvero. Da decidere con l'utente.
3. Il referto di verifica (par. 11) attribuisce il bottone a `safestrategy/ParamsSheet.tsx:259`: e'
   `ParamsSheetBase.tsx:198-199` (vedi B).

## NON VERIFICATO

- App Electron vera col backend vivo: provato solo con vitest/jsdom e `npm run build`. Il titolo della
  finestra con helmet 3 e' provato in jsdom (fotografia `document.title` di 26 pagine), non nell'exe.
- Resa a guscio acceso del marchio "LIVE · REALE" vista solo dal calcolo CSS del test, non a schermo.
- Il comportamento del servizio Python con le chiavi ora ASSENTI e' letto nel codice
  (`resolve_params`, `merge_exit_params`, `merge_risk_params`), non provato su un servizio acceso; i
  campi di strategia (`base.*`, `esatto.*`, ...) passano da `merge_params` del motore, letto solo in
  `resolve_params` (fusione profonda con i default), non riga per riga.
- Il DB vero: non letto. Se oggi contiene gia' `""` scritti dal foglio, restano finche' qualcuno non
  risalva quel foglio (allora la chiave sparisce). Nessuna migrazione scritta (non richiesta).
- La prova sotto carico e' UNA corsa per lato (prima/dopo) con un carico preciso (un secondo vitest di
  161 file); carichi diversi (es. suite intera x2) non provati.
- `npm audit` segnala 16 vulnerabilita' preesistenti: non toccate (vietato aggiornare altro).

## Cosa cambia a schermo per l'utente

- **Control Room, riga "Safe base"**: i due bottoni ora si chiamano **"Parametri strategia"** (apre i
  soli campi della Base) e **"Parametri comuni di Safe"** (apre il foglio dell'intero servizio). Sulle
  righe Risultato Esatto, Punta e Tennis di Safe il bottone si chiama "Parametri strategia". Pagina Safe
  Strategy, Mike, Omega, bot tennis: invariati ("Parametri").
- **Pannello Scalper (Segui Live)**: tutti i testi tornano leggibili: "Stake €", "€0.71" nei P&L,
  "attività", "—", "✓", "⚠️", "→", "…", anche nel messaggio di conferma prima dei soldi veri e nei toast.
- **Foglio parametri di Safe**: svuotare un campo numerico e salvare ora vuol dire "usa il valore di
  serie del servizio" (la chiave sparisce dal DB); prima nel DB restava un testo vuoto e alla
  riapertura il campo mostrava 0.
- **Grafica nuova (solo se accesa)**: nel Tennis Terminal "LIVE · REALE" resta rosso pieno con scritta
  bianca, come nella grafica di oggi. Con la grafica attuale nulla cambia.
- Nulla cambia nel resto: nessuna fotografia rigenerata; i punti 31, 32 e 33 non toccano lo schermo
  (test e dipendenza; il titolo delle finestre e' identico).
