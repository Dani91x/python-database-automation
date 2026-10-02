# FRONTEND MINORI (02/10/2026) - punti 31, 32, 33, 35, A, B, C, 30 + reperti 1-2

STATO AL 13:24: TUTTO FATTO. Reperto 1 (`6ba348c`), reperto 2 Mike/tennis/Omega (`9594453`,
`ea432f8`, `10852ed`), falsificazione 38/38 e tabella (`866ddc2`), referto (`3ba1246`). Verifica finale
della seconda consegna (macchina scarica): `tsc` 0 errori (app e progetto); suite intera **317 file
verdi / 10 saltati, 4864 test verdi / 50 saltati, 0 rossi** (728 s; prima consegna 4848 + 16 nuovi);
fotografia `off` invariata (`git diff 61f73a6 -- frontend/src/fotografia/snapshot` vuoto); `npm run build`
exit 0 (`dist/assets` 3.526.829 B); `npm ci` senza flag exit 0, nessun warning di peer. Master ora
`543b13d` (nessun file di `frontend/` cambiato dalla base), `git merge-tree` pulito. Patch rigenerata.
MANCA: niente.

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

## Altro reperto

- Il referto di verifica (par. 11) attribuisce il bottone a `safestrategy/ParamsSheet.tsx:259`: e'
  `ParamsSheetBase.tsx:198-199` (vedi B).

## Reperti 1-2 corretti (seconda consegna, ordine del coordinatore)

Commit, uno per passo verificato: `6ba348c` (reperto 1), `9594453` (Mike), `ea432f8` (tennis),
`10852ed` (Omega), `866ddc2` (falsificazione e tabella).

### Reperto 1 - foglio Safe: uscita BASE "il controllo passa alla sfavorita" mai letta dal DB

**Causa**: `exits.base_control_exit` (interruttore, `BotParamsSheet.tsx` gruppo uscite) e
`exits.base_control_exit_max` (soglia) non erano in `ExitsParams`/`EXITS_DEFAULTS`/`mergeExits`:
`toValues` non li leggeva mai e il foglio li mostrava SPENTO e VUOTO qualunque cosa ci fosse nel DB.
Peggio (visto dal test rosso su master): con la riga ACCESA, l'utente vedeva "spento", cliccava per
"spegnerla" e in realta' la scriveva `true`.
**Correzione** (solo `BotParamsSheet.tsx`): le due chiavi in `ExitsParams`, in `EXITS_DEFAULTS` con i
valori di serie del servizio (`false`, `-0.20`: `Betfair/safe_strategy/exits.py:80-81`) e in
`mergeExits` con le stesse regole delle altre uscite (booleano vero / numero finito, altrimenti valore
di serie). Il salvataggio segue la regola del punto 35 (soglia svuotata = chiave tolta).
**Test** (`BotParamsSheet.test.tsx`, describe "reperto 1", 4): riga con uscita ACCESA e soglia -0,35
-> il foglio mostra spunta e `-0.35` e salvando senza toccare li riscrive uguali; riga senza le chiavi
-> spenta e `-0.2`; spegnere scrive `false` e svuotare la soglia toglie la chiave; `mergeExits` puro.
Rosso su master (4/4). **Falsificazione**: R1a `mergeExits` senza le due chiavi -> ROSSO; R1b
(direzione nuova) valore di serie sbagliato (uscita accesa di serie) -> ROSSO.
Nota: `mergeExits` accetta solo un booleano vero (come per le altre uscite); un testo tipo `"si"` sul
DB il servizio lo legge acceso (`exits._bool`), il foglio spento. Il foglio scrive sempre booleani:
caso non presente se il DB e' scritto solo dal foglio (non verificato sul DB).

### Reperto 2 - campo numerico svuotato negli altri fogli

Regola unica, come Safe (punto 35): **campo svuotato = chiave omessa dal payload**. Per ognuno dei tre
servizi ho verificato che la chiave assente porti al valore di serie chiamando il codice Python VERO
(`AUDIT_2026-10-02/tabella_predefiniti.py`, uscita `tabella_predefiniti_out.md`): **235 campi numerici
(Safe 64, Mike 83, Omega 66, tennis 22), 0 senza valore di serie, 0 errori**. Le RPC di salvataggio
sostituiscono la colonna `params` (`mike_update_params` `migrations/mike_bot.sql:236-237`,
`tennis_bot_service_update_params` `migrations/tennis_bot_service_control_2026-09-17.sql:147-151`,
`omega_update_params` `migrations/omega_daily_v2.sql:107-110`): la chiave omessa resta ASSENTE nel DB.

- **Mike** (`lib/mike.ts`, `components/mike/MikeParamsSheet.tsx`). Causa: `mergeMikeParams` faceva
  `Number('')` = 0 e il clamp portava al MINIMO (stake svuotato -> 0,50). Correzione: in
  `mergeMikeParams` `""` su un numero lascia il default; nuova `parametriMikeDaSalvare(v)` =
  `mergeMikeParams(v)` senza le chiavi dei numeri svuotati; il foglio salva quella (Control Room e
  pagina Mike passano dallo stesso foglio). Python: `config.merge_params` (`Betfair/mike/config.py:473`)
  parte da `DEFAULTS` (`:437`). Test (4): `mergeMikeParams` per ognuno degli 83 numeri; puro per OGNI
  campo (vuoto -> assente, gli altri 82 + non numerici identici); foglio vero con tutti gli 83 input
  svuotati; stake svuotato non diventa 0,50. Rossi su master (4/4). Falsificazione R2m1, R2m2 -> ROSSO.
- **Bot tennis** (`components/tennis/TennisBotServiceParamsSheet.tsx`). Causa: `Number('')` = 0 ->
  salvato 0. Correzione: numero svuotato -> `delete payload[chiave]` (il payload riparte dalla riga
  letta). Python: il bot usa `c.get(chiave, default)`; per lo scalper il runner applica PRIMA il preset
  (`tennis_live/tennis_runner.py:920-923`, `setdefault` da `run_tennis_scalper.TENNIS_PARAMS`). Test
  (4, uno per bot): per OGNI campo numerico (7+5+5+5) svuotato -> chiave assente, gli altri numeri e
  una chiave ignota intatti. Rossi su master (4/4, "presente (0)"). Falsificazione R2t -> ROSSO.
- **Omega** (`lib/omega.ts` `omegaParamsPatch`, `components/omega/OmegaParamsSheet.tsx`,
  `pages/Omega.tsx`). Causa: `''` diverso dal valore -> inviato `""`. Correzione: in `omegaParamsPatch`
  una chiave il cui valore di serie della UI e' numerico, arrivata vuota, viene TOLTA (vale per i due
  fogli e per l'attivazione, che usano tutti `omegaParamsPatch`). Python:
  `omega_config.resolve_params` (`Betfair/omega/omega_config.py:368`) parte da `DEFAULTS` (`:321`).
  **Obiettivo giornaliero**: e' la COLONNA `omega_control.daily_goal`, non in `params`; il servizio non
  ha un valore di serie da usare e `omega_update_params(NULL)` la lascerebbe com'e'. Prima, svuotata,
  si scriveva **0** (`Number('')`). Ora il salvataggio si RIFIUTA: nel foglio della Control Room
  messaggio rosso `omega-params-obbligatorio` "Obiettivo giornaliero: campo obbligatorio. Non ha un
  valore di serie nel servizio: scrivi un numero (anche 0). Niente e' stato salvato."; nella pagina
  Omega lo stesso testo in un avviso ("Campo obbligatorio"). Nessuna scrittura. Test (4): puro per OGNI
  campo dei 66 (sul DB o no); foglio vero con i 66 input svuotati (obiettivo intatto, inviato 180);
  obiettivo svuotato rifiutato nel foglio e nella pagina. Rossi su master (4/4: tra l'altro dailyGoal 0
  inviato). Falsificazione R2o1, R2o2, R2o3 -> ROSSO.

**Falsificazione complessiva**: `falsifica_frontend_minori.py` ora 38/38 come atteso (25 di prima +
8 mutazioni nuove + 5 controprove finali in piu'), `git status` identico prima/dopo.

**Cosa cambia a schermo**: foglio Safe, l'uscita BASE "controllo alla sfavorita" e la sua soglia ora
mostrano il valore vero del DB; in tutti i fogli (Safe, Mike, Omega, bot tennis) svuotare un numero
e salvare vuol dire "valore di serie del servizio"; in Omega l'obiettivo giornaliero vuoto non si salva
e lo dice.

### Tabelle: campo -> valore di serie nel Python con la chiave ASSENTE (file:riga)

Generate da `tabella_predefiniti.py` chiamando le funzioni vere del servizio (Safe, Mike, Omega) o
leggendo il `c.get` del bot (tennis).

#### Safe (`bot_service.resolve_params({}, engine)`) (64 campi numerici)

| campo | valore di serie nel Python (chiave assente) | file:riga | esito |
|---|---|---|---|
| `poll_interval_s` | 2.0 | `Betfair/safe_strategy/bot_service.py:344` | OK |
| `commission_pct` | 5.0 | `Betfair/safe_strategy/bot_service.py:345` | OK |
| `max_open_trades` | 20 | `Betfair/safe_strategy/bot_service.py:346` | OK |
| `max_liability_per_trade` | 300.0 | `Betfair/safe_strategy/bot_service.py:347` | OK |
| `min_size_available_factor` | 1.0 | `Betfair/safe_strategy/bot_service.py:348` | OK |
| `min_stake` | 2.0 | `Betfair/safe_strategy/bot_service.py:360` | OK |
| `max_spread_ratio` | 1.6 | `Betfair/safe_strategy/bot_service.py:352` | OK |
| `place_max_attempts` | 3 | `Betfair/safe_strategy/bot_service.py:353` | OK |
| `paper_fill_ttl_s` | 45 | `Betfair/safe_strategy/bot_service.py:358` | OK |
| `live_fill_deadline_s` | 20 | `Betfair/safe_strategy/bot_service.py:359` | OK |
| `stake.laySize` | 2.0 | `Betfair/safe_strategy/engine.py:447` | OK |
| `stake.backSize` | 2.0 | `Betfair/safe_strategy/engine.py:448` | OK |
| `risk.daily_liability_cap` | 500.0 | `Betfair/safe_strategy/risk.py:38` | OK |
| `risk.per_event_liability_cap` | 150.0 | `Betfair/safe_strategy/risk.py:39` | OK |
| `risk.per_event_max_trades` | 3 | `Betfair/safe_strategy/risk.py:40` | OK |
| `risk.correlated_cap` | 0.7 | `Betfair/safe_strategy/risk.py:42` | OK |
| `risk.daily_loss_stop` | -50.0 | `Betfair/safe_strategy/risk.py:43` | OK |
| `risk.model_daily_liability_cap` | 150.0 | `Betfair/safe_strategy/risk.py:45` | OK |
| `risk.max_open_trades` | None | `Betfair/safe_strategy/risk.py:41` | OK (None = tetto del bot) |
| `opps_interval_s` | 10.0 | `Betfair/safe_strategy/bot_service.py:349` | OK |
| `opps_min_confidence` | 0.7 | `Betfair/safe_strategy/bot_service.py:363` | OK |
| `opps_min_edge` | 0.03 | `Betfair/safe_strategy/bot_service.py:364` | OK |
| `risk.model_stake` | 5.0 | `Betfair/safe_strategy/risk.py:44` | OK |
| `opps_stake` | 5.0 | `Betfair/safe_strategy/bot_service.py:350` | OK |
| `exits.hold_max_risk` | 0.02 | `Betfair/safe_strategy/exits.py:117` | OK |
| `exits.risk_cap` | 0.1 | `Betfair/safe_strategy/exits.py:118` | OK |
| `exits.risk_premium_pct` | 0.05 | `Betfair/safe_strategy/exits.py:120` | OK |
| `exits.ev_margin` | 0.1 | `Betfair/safe_strategy/exits.py:119` | OK |
| `exits.model_exit_p_lose` | 0.1 | `Betfair/safe_strategy/exits.py:124` | OK |
| `exits.model_take_profit_frac` | 0.8 | `Betfair/safe_strategy/exits.py:125` | OK |
| `exits.model_free_cashout_p_lose` | 0.005 | `Betfair/safe_strategy/exits.py:126` | OK |
| `exits.residual_retry_s` | 20.0 | `Betfair/safe_strategy/exits.py:105` | OK |
| `exits.residual_max_attempts` | 15 | `Betfair/safe_strategy/exits.py:106` | OK |
| `exits.base_exit_minute` | 80 | `Betfair/safe_strategy/exits.py:71` | OK |
| `exits.esatto_exit_minute` | 72 | `Betfair/safe_strategy/exits.py:72` | OK |
| `exits.punta_exit_minute` | 83 | `Betfair/safe_strategy/exits.py:73` | OK |
| `exits.loss_settle_delay_s` | 30.0 | `Betfair/safe_strategy/exits.py:74` | OK |
| `exits.exit_max_retries` | 3 | `Betfair/safe_strategy/exits.py:101` | OK |
| `exits.tennis_take_profit_min_odds` | 1.03 | `Betfair/safe_strategy/exits.py:93` | OK |
| `exits.tennis_take_profit_min_eur` | 0.01 | `Betfair/safe_strategy/exits.py:99` | OK |
| `exits.base_control_exit_max` | -0.2 | `Betfair/safe_strategy/exits.py:81` | OK |
| `base.minuteMin` | 55 | `Betfair/safe_strategy/engine.py:386` | OK |
| `base.dogLayMin` | 20 | `Betfair/safe_strategy/engine.py:395` | OK |
| `base.dogLayMax` | 34 | `Betfair/safe_strategy/engine.py:396` | OK |
| `base.scoreConfirmSec` | 30 | `Betfair/safe_strategy/engine.py:397` | OK |
| `esatto.minuteMin` | 48 | `Betfair/safe_strategy/engine.py:401` | OK |
| `esatto.entryMin` | 30 | `Betfair/safe_strategy/engine.py:406` | OK |
| `esatto.entryMax` | 70 | `Betfair/safe_strategy/engine.py:407` | OK |
| `esatto.maxGoalsLaySide` | 1 | `Betfair/safe_strategy/engine.py:405` | OK |
| `esatto.scoreConfirmSec` | 30 | `Betfair/safe_strategy/engine.py:408` | OK |
| `punta.minuteMin` | 66 | `Betfair/safe_strategy/engine.py:419` | OK |
| `punta.entryMin` | 1.03 | `Betfair/safe_strategy/engine.py:423` | OK |
| `punta.entryMax` | 1.1 | `Betfair/safe_strategy/engine.py:424` | OK |
| `punta.minMinutesAfterGoal` | 3 | `Betfair/safe_strategy/engine.py:426` | OK |
| `tennis.setsLeadMin` | 1 | `Betfair/safe_strategy/engine.py:431` | OK |
| `tennis.gamesLeadMin` | 2 | `Betfair/safe_strategy/engine.py:432` | OK |
| `tennis.backMin` | 1.02 | `Betfair/safe_strategy/engine.py:433` | OK |
| `tennis.backMax` | 1.1 | `Betfair/safe_strategy/engine.py:434` | OK |
| `tennis.scoreConfirmSec` | 15 | `Betfair/safe_strategy/engine.py:441` | OK |
| `tennis.setsPlayedMax` | 1 | `Betfair/safe_strategy/engine.py:437` | OK |
| `tennis.favSuperMax` | 1.2 | `Betfair/safe_strategy/engine.py:443` | OK |
| `base.controlMin` | 0.1 | `Betfair/safe_strategy/engine.py:388` | OK |
| `esatto.controlMin` | 0.1 | `Betfair/safe_strategy/engine.py:403` | OK |
| `punta.controlMin` | 0.1 | `Betfair/safe_strategy/engine.py:421` | OK |

#### Mike (`Betfair/mike/config.py` `merge_params({})`) (83 campi numerici)

| campo | valore di serie nel Python (chiave assente) | file:riga | esito |
|---|---|---|---|
| `stake` | 10.0 | `Betfair/mike/config.py:77` | OK |
| `commission_pct` | 5.0 | `Betfair/mike/config.py:78` | OK |
| `entry_hours_before_ko` | 1.0 | `Betfair/mike/config.py:85` | OK |
| `decide_min_interval_ms` | 500 | `Betfair/mike/config.py:87` | OK |
| `feed_max_age_s` | 45.0 | `Betfair/mike/config.py:95` | OK |
| `scanner_alive_max_s` | 75.0 | `Betfair/mike/config.py:101` | OK |
| `book_seen_max_s` | 90.0 | `Betfair/mike/config.py:114` | OK |
| `order_max_age_s` | 20.0 | `Betfair/mike/config.py:115` | OK |
| `order_scanner_max_s` | 30.0 | `Betfair/mike/config.py:116` | OK |
| `pre_entry_price_min` | 1.3 | `Betfair/mike/config.py:119` | OK |
| `pre_entry_price_max` | 3.0 | `Betfair/mike/config.py:120` | OK |
| `pre_min_back_size_factor` | 1.0 | `Betfair/mike/config.py:121` | OK |
| `pre_max_spread_ticks` | 6 | `Betfair/mike/config.py:124` | OK |
| `pre_green_ticks` | 2 | `Betfair/mike/config.py:125` | OK |
| `pre_entry_ttl_s` | 60 | `Betfair/mike/config.py:138` | OK |
| `pre_max_cycles` | 10 | `Betfair/mike/config.py:139` | OK |
| `pre_reentry_cooldown_s` | 60 | `Betfair/mike/config.py:140` | OK |
| `pre_last_entry_min` | 10 | `Betfair/mike/config.py:141` | OK |
| `last_entry_ticks_above` | 0 | `Betfair/mike/config.py:143` | OK |
| `veto_p_under35_soglia_130` | 0.807 | `Betfair/mike/config.py:153` | OK |
| `veto_p_under35_soglia_150` | 0.684 | `Betfair/mike/config.py:154` | OK |
| `veto_p_under35_soglia_200` | 0.514 | `Betfair/mike/config.py:155` | OK |
| `veto_p_under35_soglia_250` | 0.385 | `Betfair/mike/config.py:156` | OK |
| `veto_p_under35_soglia_300` | 0.275 | `Betfair/mike/config.py:157` | OK |
| `cancel_unmatched_after_ko_s` | 120 | `Betfair/mike/config.py:158` | OK |
| `ko_green_ticks` | 2 | `Betfair/mike/config.py:164` | OK |
| `ko_green_window_s` | 180 | `Betfair/mike/config.py:165` | OK |
| `ko_green_retry_s` | 5 | `Betfair/mike/config.py:173` | OK |
| `second_entry_stake_pct` | 50.0 | `Betfair/mike/config.py:178` | OK |
| `early_goal_cover_delay_s` | 120 | `Betfair/mike/config.py:183` | OK |
| `early_goal_cover_pct` | 50.0 | `Betfair/mike/config.py:184` | OK |
| `early_goal_cover2_delay_s` | 180 | `Betfair/mike/config.py:185` | OK |
| `cover_profit_factor` | 1.2 | `Betfair/mike/config.py:188` | OK |
| `cover_wait_hazard_max` | 0.06 | `Betfair/mike/config.py:194` | OK |
| `cover_wait_max_min` | 10 | `Betfair/mike/config.py:195` | OK |
| `cover_wait_p4_max` | 0.16 | `Betfair/mike/config.py:196` | OK |
| `cover_good_price` | 7.0 | `Betfair/mike/config.py:197` | OK |
| `cover_wait_min_gain_pct` | 8.0 | `Betfair/mike/config.py:198` | OK |
| `cover_wait_step_min` | 5 | `Betfair/mike/config.py:199` | OK |
| `cover_postgoal_delay_s` | 45 | `Betfair/mike/config.py:200` | OK |
| `cover_max_goals` | 2 | `Betfair/mike/config.py:201` | OK |
| `cover_max_overshoot_pct` | 30.0 | `Betfair/mike/config.py:203` | OK |
| `cover_rifiuti_max` | 3 | `Betfair/mike/config.py:235` | OK |
| `cover_retry_min_s` | 15 | `Betfair/mike/config.py:236` | OK |
| `cashout_profit_pct` | 5.0 | `Betfair/mike/config.py:238` | OK |
| `cashout_place_at_ticks` | 0 | `Betfair/mike/config.py:240` | OK |
| `cover_place_at_ticks` | 2 | `Betfair/mike/config.py:249` | OK |
| `cashout_smart_min_pct` | 2.0 | `Betfair/mike/config.py:264` | OK |
| `cashout_smart_tolerance_pct` | 2.0 | `Betfair/mike/config.py:265` | OK |
| `cashout_smart_hazard_hot` | 0.1 | `Betfair/mike/config.py:266` | OK |
| `cashout_smart_pressure_hot` | 1.15 | `Betfair/mike/config.py:267` | OK |
| `cashout_smart_goals_hot` | 3 | `Betfair/mike/config.py:268` | OK |
| `cashout_smart_ev_margin_pct` | 1.0 | `Betfair/mike/config.py:269` | OK |
| `close_retry_s` | 10 | `Betfair/mike/config.py:270` | OK |
| `close_max_attempts` | 20 | `Betfair/mike/config.py:271` | OK |
| `ht_loss_pct` | 25.0 | `Betfair/mike/config.py:292` | OK |
| `loss_exit_risk_premium_pct` | 10.0 | `Betfair/mike/config.py:287` | OK |
| `loss_exit_max_pct` | 0.0 | `Betfair/mike/config.py:289` | OK |
| `loss_exit_emp_min_n` | 200 | `Betfair/mike/config.py:290` | OK |
| `ht_loss_goals_min` | 3 | `Betfair/mike/config.py:296` | OK |
| `ht_loss_goals_max` | 4 | `Betfair/mike/config.py:297` | OK |
| `h2_loss_pct` | 25.0 | `Betfair/mike/config.py:299` | OK |
| `h2_loss_from_min` | 46 | `Betfair/mike/config.py:300` | OK |
| `h2_loss_to_min` | 85 | `Betfair/mike/config.py:301` | OK |
| `reentry_green_ticks` | 2 | `Betfair/mike/config.py:304` | OK |
| `reentry_max_goals` | 2 | `Betfair/mike/config.py:307` | OK |
| `reentry_until_min` | 45 | `Betfair/mike/config.py:308` | OK |
| `reentry_exit_until_min` | 0 | `Betfair/mike/config.py:310` | OK |
| `settle_confirm_s` | 60 | `Betfair/mike/config.py:316` | OK |
| `max_open_matches` | 10 | `Betfair/mike/config.py:317` | OK |
| `daily_loss_stop` | 50.0 | `Betfair/mike/config.py:318` | OK |
| `max_liability_per_match` | 0.0 | `Betfair/mike/config.py:319` | OK |
| `event_loss_cap_pct` | 100.0 | `Betfair/mike/config.py:320` | OK |
| `skip_log_interval_s` | 300 | `Betfair/mike/config.py:323` | OK |
| `feed_cache_s` | 4.0 | `Betfair/mike/config.py:338` | OK |
| `events_reload_s` | 60.0 | `Betfair/mike/config.py:342` | OK |
| `aggregates_cache_s` | 20.0 | `Betfair/mike/config.py:344` | OK |
| `reconcile_every_s` | 30.0 | `Betfair/mike/config.py:347` | OK |
| `idle_cycle_s` | 5.0 | `Betfair/mike/config.py:350` | OK |
| `publish_heartbeat_s` | 5.0 | `Betfair/mike/config.py:373` | OK |
| `publish_idle_heartbeat_s` | 60.0 | `Betfair/mike/config.py:378` | OK |
| `stats_min_s` | 10.0 | `Betfair/mike/config.py:388` | OK |
| `heartbeat_min_s` | 20.0 | `Betfair/mike/config.py:389` | OK |

#### Omega (`Betfair/omega/omega_config.py` `resolve_params({})`) (66 campi numerici)

| campo | valore di serie nel Python (chiave assente) | file:riga | esito |
|---|---|---|---|
| `price_min` | 20.0 | `Betfair/omega/omega_config.py:24` | OK |
| `price_max` | 120.0 | `Betfair/omega/omega_config.py:25` | OK |
| `ht_entry_min` | 20 | `Betfair/omega/omega_config.py:60` | OK |
| `ht_entry_max` | 40 | `Betfair/omega/omega_config.py:61` | OK |
| `ft_entry_min` | 50 | `Betfair/omega/omega_config.py:62` | OK |
| `ft_entry_max` | 80 | `Betfair/omega/omega_config.py:63` | OK |
| `model_p_max_pct` | 2.0 | `Betfair/omega/omega_config.py:64` | OK |
| `model_min_goal_distance` | 2 | `Betfair/omega/omega_config.py:65` | OK |
| `max_events` | 0 | `Betfair/omega/omega_config.py:28` | OK |
| `min_lay_liquidity` | 5.0 | `Betfair/omega/omega_config.py:30` | OK |
| `min_stake` | 0.5 | `Betfair/omega/omega_config.py:31` | OK |
| `entry_minute_min` | 30 | `Betfair/omega/omega_config.py:26` | OK |
| `entry_minute_max` | 60 | `Betfair/omega/omega_config.py:27` | OK |
| `model_empirical_max_minute` | 60 | `Betfair/omega/omega_config.py:82` | OK |
| `model_tail_factor` | 1.3 | `Betfair/omega/omega_config.py:96` | OK |
| `model_lambda_cv` | 0.3 | `Betfair/omega/omega_config.py:110` | OK |
| `select_p_band_ratio` | 2.0 | `Betfair/omega/omega_config.py:90` | OK |
| `select_k_se` | 0.0 | `Betfair/omega/omega_config.py:113` | OK |
| `select_p_hedge` | 0.5 | `Betfair/omega/omega_config.py:115` | OK |
| `select_ev_kappa` | 1.0 | `Betfair/omega/omega_config.py:116` | OK |
| `greenup_trigger_distance` | 1 | `Betfair/omega/omega_config.py:120` | OK |
| `greenup_price_trigger_ratio` | 0.5 | `Betfair/omega/omega_config.py:121` | OK |
| `greenup_settle_delay_s` | 30 | `Betfair/omega/omega_config.py:122` | OK |
| `greenup_hold_max_risk` | 0.02 | `Betfair/omega/omega_config.py:123` | OK |
| `greenup_risk_cap` | 0.15 | `Betfair/omega/omega_config.py:124` | OK |
| `greenup_risk_premium_pct` | 0.05 | `Betfair/omega/omega_config.py:129` | OK |
| `greenup_ev_margin` | 0.1 | `Betfair/omega/omega_config.py:125` | OK |
| `greenup_take_profit_frac` | 0.9 | `Betfair/omega/omega_config.py:130` | OK |
| `greenup_take_profit_minute` | 80 | `Betfair/omega/omega_config.py:131` | OK |
| `greenup_retry_s` | 20 | `Betfair/omega/omega_config.py:132` | OK |
| `greenup_max_attempts` | 15 | `Betfair/omega/omega_config.py:133` | OK |
| `greenup_market_floor_max_ratio` | 3.0 | `Betfair/omega/omega_config.py:139` | OK |
| `commission_pct` | 5.0 | `Betfair/omega/omega_config.py:29` | OK |
| `max_liability_per_match` | 0.0 | `Betfair/omega/omega_config.py:36` | OK |
| `daily_loss_cap` | 0.0 | `Betfair/omega/omega_config.py:37` | OK |
| `max_open_liability` | 0.0 | `Betfair/omega/omega_config.py:38` | OK |
| `poll_interval_s` | 20 | `Betfair/omega/omega_config.py:35` | OK |
| `paper_fill_ttl_s` | 45 | `Betfair/omega/omega_config.py:46` | OK |
| `live_fill_deadline_s` | 20 | `Betfair/omega/omega_config.py:55` | OK |
| `feed_cache_s` | 2.0 | `Betfair/omega/omega_config.py:161` | OK |
| `scanner_status_cache_s` | 10.0 | `Betfair/omega/omega_config.py:168` | OK |
| `aggregates_cache_s` | 20.0 | `Betfair/omega/omega_config.py:174` | OK |
| `sets_cache_s` | 30.0 | `Betfair/omega/omega_config.py:180` | OK |
| `results_every_s` | 60.0 | `Betfair/omega/omega_config.py:185` | OK |
| `missions_every_s` | 5.0 | `Betfair/omega/omega_config.py:190` | OK |
| `events_refresh_s` | 1800.0 | `Betfair/omega/omega_config.py:201` | OK |
| `idle_stats_s` | 60.0 | `Betfair/omega/omega_config.py:204` | OK |
| `idle_cycle_s` | 60.0 | `Betfair/omega/omega_config.py:211` | OK |
| `conto_every_s` | 120.0 | `Betfair/omega/omega_config.py:198` | OK |
| `strategy_version` | 3 | `Betfair/omega/omega_config.py:221` | OK |
| `v3_stake_eur` | 1.0 | `Betfair/omega/omega_config.py:225` | OK |
| `v3_k_minimo` | 1.11 | `Betfair/omega/omega_config.py:237` | OK |
| `v3_p_max_pct` | 2.0 | `Betfair/omega/omega_config.py:282` | OK |
| `v3_p_min_pct` | 1.0 | `Betfair/omega/omega_config.py:283` | OK |
| `v3_distanza_minima_gol` | 2 | `Betfair/omega/omega_config.py:268` | OK |
| `v3_empirical_min_n` | 200 | `Betfair/omega/omega_config.py:239` | OK |
| `v3_ht_entry_min` | 1 | `Betfair/omega/omega_config.py:250` | OK |
| `v3_ht_entry_max` | 44 | `Betfair/omega/omega_config.py:251` | OK |
| `v3_ft_entry_min` | 46 | `Betfair/omega/omega_config.py:252` | OK |
| `v3_ft_entry_max` | 85 | `Betfair/omega/omega_config.py:253` | OK |
| `v3_min_lay_liquidity` | 1.0 | `Betfair/omega/omega_config.py:264` | OK |
| `v3_max_liability_per_leg` | 95.0 | `Betfair/omega/omega_config.py:259` | OK |
| `v3_max_liability_per_match` | 190.0 | `Betfair/omega/omega_config.py:260` | OK |
| `v3_max_open_liability` | 1000.0 | `Betfair/omega/omega_config.py:261` | OK |
| `v3_daily_loss_cap` | 300.0 | `Betfair/omega/omega_config.py:262` | OK |
| `proposta_p_lose_max_pct` | 0.0 | `Betfair/omega/omega_config.py:302` | OK |

#### Bot tennis (`c.get(chiave, default)` del bot; scalper: preset del runner) (22 campi numerici)

| campo | valore di serie nel Python (chiave assente) | file:riga | esito |
|---|---|---|---|
| `tennis_scalper.scalp_ticks` | 1 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:43 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:317` | OK |
| `tennis_scalper.stop_ticks` | 3 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:44 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:318` | OK |
| `tennis_scalper.signal_ticks` | 1.0 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:51 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:361` | OK |
| `tennis_scalper.min_flow` | 2.0 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:58 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:385` | OK |
| `tennis_scalper.min_size` | 5.0 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:54 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:352` | OK |
| `tennis_scalper.price_min` | 1.20 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:56 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:356` | OK |
| `tennis_scalper.price_max` | 6.0 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:57 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:357` | OK |
| `tennis_pro.bp_target_ticks` | 5 | `Betfair/stream/tennis_scalper/tennis_pro_bot.py:181` | OK |
| `tennis_pro.bp_stop_ticks` | 3 | `Betfair/stream/tennis_scalper/tennis_pro_bot.py:182` | OK |
| `tennis_pro.fade_target_ticks` | 4 | `Betfair/stream/tennis_scalper/tennis_pro_bot.py:186` | OK |
| `tennis_pro.min_matched` | 50_000.0 | `Betfair/stream/tennis_scalper/tennis_pro_bot.py:152` | OK |
| `tennis_pro.price_max` | 3.6 | `Betfair/stream/tennis_scalper/tennis_pro_bot.py:155` | OK |
| `tennis_flb.lay_max` | 1.10 | `Betfair/stream/tennis_scalper/tennis_flb_bot.py:80` | OK |
| `tennis_flb.green_ticks` | 8 | `Betfair/stream/tennis_scalper/tennis_flb_bot.py:85` | OK |
| `tennis_flb.green_frac` | 0.5 | `Betfair/stream/tennis_scalper/tennis_flb_bot.py:86` | OK |
| `tennis_flb.rearm_mult` | 1.10 | `Betfair/stream/tennis_scalper/tennis_flb_bot.py:82` | OK |
| `tennis_flb.min_matched` | 10_000.0 | `Betfair/stream/tennis_scalper/tennis_flb_bot.py:87` | OK |
| `tennis_swing.N` | 40 | `Betfair/stream/tennis_scalper/tennis_swing_bot.py:77` | OK |
| `tennis_swing.zin` | 2.0 | `Betfair/stream/tennis_scalper/tennis_swing_bot.py:78` | OK |
| `tennis_swing.er_max` | 0.4 | `Betfair/stream/tennis_scalper/tennis_swing_bot.py:79` | OK |
| `tennis_swing.stop_ticks` | 8 | `Betfair/stream/tennis_scalper/tennis_swing_bot.py:82` | OK |
| `tennis_swing.tmax` | 90 | `Betfair/stream/tennis_scalper/tennis_swing_bot.py:86` | OK |

chiavi senza valore di serie numerico: 0

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
