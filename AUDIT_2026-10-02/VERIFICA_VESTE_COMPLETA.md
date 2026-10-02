# Verifica indipendente — ramo `origin/redesign/veste-completa` (`7a17f7f`) su master `67261b9`

Verificatore indipendente, 02/10/2026, worktree isolato `.claude/worktrees/agent-a74907e55967006da`,
ramo locale `verifica-veste` (= master `67261b9` + merge `--no-ff` di `7a17f7f`, commit locale `ec95a3a`,
mai pushato). Nessuna modifica al codice del ramo. Strumenti e uscite grezze: `AUDIT_2026-10-02/strumenti_verifica/`
(script riproducibili, `out/` con log della suite, build, scatti, confronto pixel).

## Giudizio finale

**FONDIBILE A UNA CONDIZIONE** (o NON FONDIBILE così com'è, se la regola è «suite verde»):

- Col guscio SPENTO l'app è quella di master: ogni riga cambiata dei 55 componenti/pagine è un'aggiunta di classi
  `ds-v2-*` (4 blocchi composti, tutti di sola classe); tutto il CSS nuovo è un'aggiunta in coda a `index.css` e
  ogni selettore (202) è condizionato da `[data-shell="v2"]`; interruttore e bottoni di ritorno NON toccati dal ramo;
  nessuna chiamata, chiave locale, form, polling, canale, testo o `data-testid` cambiato; fotografia `off` intatta e
  verde; build verde (+0,78 %); scatti a guscio spento identici a master salvo zone animate.
- **Condizione: `frontend/src/fotografia/uiDefault.test.ts` è ROSSO su Windows** (il PC dell'utente). Non è una
  regressione dell'app, è un difetto del test nuovo: con `core.autocrlf=true` (impostato a livello di sistema in
  `C:/Program Files/Git/etc/gitconfig`) i file sono CRLF sul disco, e l'estrattore di stringhe, su
  `components/ui/form.tsx` (unico file con un backtick su più righe), legge `\r\n` mentre l'istantanea è stata presa
  su Linux con `\n`. Anche il checkout principale ha `form.tsx` in CRLF: dopo la fusione la suite dell'utente sarebbe
  rossa (1 test). Correzione di una riga, da fare prima della fusione (non fatta: vincolo «nessuna modifica»):
  in `leggiTutti()` leggere `readFileSync(...).replace(/\r\n/g, '\n')`. Prova: convertito `form.tsx` in LF (stesso
  contenuto in git) il test è verde 2/2; dettaglio sotto.

## 1. Fusione

`git merge --no-ff origin/redesign/veste-completa` su `master` `67261b9`: **nessun conflitto**. Base comune
`ebfab2a`; i 4 commit di master successivi non toccano `frontend/` (diff vuoto), quindi il risultato su `frontend/`
coincide col ramo.

## 2. Ambiente

`npm ci --legacy-peer-deps` nel `frontend/` del worktree (exit 0). Nessuna junction, nessun link simbolico, nessun
`git worktree remove/prune`. Build e server solo nel worktree; checkout principale solo in lettura (ho letto i soli
NOMI delle variabili di `frontend/.env`, non i valori).

## 3. Perimetro (`git diff --name-status master verifica-veste`, 208 file)

| gruppo | file | esito |
|---|---|---|
| `frontend/src/components/**`, `frontend/src/pages/**` modificati | 55 (`.tsx`) | atteso |
| `frontend/src/index.css` modificato | 1 | atteso (solo aggiunta in coda, 0 righe tolte) |
| `frontend/src/fotografia/` nuovi | `cssVeste.test.ts`, `uiDefault.test.ts`, `snapshot/ui-default.json` | ammessi |
| `frontend/src/anteprima/*.ts` nuovi | 22 | **fuori dall'elenco atteso del brief di verifica, ma previsti dal brief 2 §7**; verificato: nessun import dall'app (`grep` degli import = 0), assenti dal bundle (`grep` di dati dei finti nel `dist` = 0); entrano in `tsc` (0 errori) |
| `AUDIT_2026-10-01/REDESIGN/REFERTO_CLOUD_2.md`, `confronto2/*.png`, `off_contro_master_finale.txt` | 107 | attesi |
| `AUDIT_2026-10-01/REDESIGN/confronto2/strumenti/*` | 20 (`.mjs`, `.sh`, `.py`, `.ts`) | **fuori dall'elenco atteso** (strumenti di scatto); 3 `.py` sono strumenti, non codice Python dell'app |

NON toccati (verificato con `git diff --name-status` sui percorsi): Python dell'app, SQL, `migrations/`, `desktop/`,
hook (`use*.ts(x)`), `package.json`, `package-lock.json`, `vite.config*`, `tsconfig*`, `tailwind.config.js`,
`index.html`, `frontend/src/lib/**` (incluso `uiShell.ts`), `components/ui/**`, `components/shell/**`, `App.tsx`,
test esistenti (0 modificati), fotografie esistenti (0 modificate).

## 4. Diff riga per riga (`strumenti_verifica/classifica.py`, uscita in `tipo_b.txt`)

Metodo: per ogni `.ts/.tsx` modificato (55), `difflib` fra master e ramo; un blocco cambiato è di tipo (a) se,
tolti i token `ds-v2-*`/`ds-portale-v2-*` (con UN solo spazio adiacente, senza normalizzare gli spazi: uno spazio
perso in una concatenazione di classi risulta (b)), è identico a master. Risultato: **258 righe di tipo (a),
13 righe di tipo (b) in 4 blocchi**. Controprova: tutte le righe aggiunte che contengono `ds-v2-` e non contengono
`className` (30) sono stringhe di classi (`SELECT_CLS`, concatenazioni `' +`, `cn(...)`, mappe di classi).

| # | file:riga (ramo) | contenuto | giudizio |
|---|---|---|---|
| b1 | `components/controlroom/PannelloBot.tsx:66-75` | costante nuova `STATO_V2` (stato → classe `ds-v2-chip--*`) | solo classi; nessuna logica, props, handler, hook. Nota di nome: `running` → `ds-v2-chip--paper` (verde, stessa tinta di `text-emerald-400` di oggi), il nome «paper» per lo stato «in corsa» è fuorviante ma innocuo |
| b2 | `PannelloBot.tsx:601` | `className` di `cr-bot-stato-*` estesa con `ds-v2-chip ${STATO_V2[r.stato] ?? 'ds-v2-chip--fermo'}` | solo classi; `data-testid`, testo, classi semantiche (`STATO_CLS`) invariati |
| b3 | `components/trading/BotHeader.tsx:165` | `className={meta.cls}` → `` className={`${meta.cls} ds-v2-forma-pillola`} `` | solo classi |
| b4 | `pages/ControlRoom.tsx:1160` | `className` di `cr-bot-${b.bot}` da stringa a template con `ds-v2-cr-chipbot` + `--live` se `b.modalita === 'live'` | solo classi; la condizione legge un campo già esistente (tsc 0 errori), `data-testid` e `title` invariati |

Letti per intero (diff completo contro master): `controlroom/testata/FasciaSoldiVeri.tsx` (1 riga, classe),
`FasciaStop.tsx` (3 righe, classi), `TesseraRunner.tsx` (1 riga, classe) — sono i 3 `.tsx` della cartella; gli altri
file di `testata/` (`soldiVeri.ts`, `salvaStop.ts`, `stopPerdita.ts`, `paroleImpianto.ts` e i test) sono identici a
master — e `dashboard/BacktestAutomatico.tsx` (4 righe: `SELECT_CLS` + 3 titoli di scheda, classi). Nessun altro
cambio: il resto del file è identico byte per byte.

## 5. CSS scoping (`strumenti_verifica/scoping_css.cjs`, postcss)

- `index.css` del ramo = master + sola aggiunta in coda (0 righe tolte o cambiate sopra).
- Sezione nuova: **175 regole, 202 selettori, 0 eccezioni**: ogni selettore inizia con `[data-shell="v2"]`,
  `:where([data-shell="v2"])` o `:where(body:has([data-shell="v2"]))`.
- `:root` nuovi: 0; variabili CSS dichiarate: 0; `@keyframes`: 0; `@font-face`/`@import`: 0; `@media`: 4
  (righe 1387, 1810, 2008, 2073), tutte con regole interne condizionate; un solo `!important` (riga ~2081) dentro
  una regola condizionata.
- Il selettore viene messo solo da `components/shell/AppShell.tsx:21` (`data-shell="v2"`), montato solo con
  `ui.shell='v2'`: a guscio spento nessuna regola si applica.
- Leve globali (34 selettori `:where([data-shell="v2"]) .<utility>`): `font-mono`, `font-black`, `text-[8|9|9.5px]`,
  `text-white*`, `border-white/*`, `bg-black/*`, `bg-white/*`, `glass-card(::before)`, `rounded-2xl`, `h1-h3`. Valgono
  solo a guscio acceso; essendo dopo le utility con pari specificità, a guscio acceso vincono su TUTTE le occorrenze
  di quelle utility nelle pagine (effetto voluto, ma ampio: es. `text-white` diventa `--foreground`).

## 6. Interruttore e ritorno a un clic

- `frontend/src/lib/uiShell.ts` **identico a master** (il ramo non lo tocca), come `ProvaNuovaGrafica.tsx`,
  `TestataGlobale.tsx` («Torna alla grafica attuale»), `AppShell.tsx`, `App.tsx`.
- Ordine di lettura: `localStorage['ui.shell']` → `VITE_UI_SHELL` → `'off'`; valore estraneo o `localStorage` che
  lancia = assente → `'off'`. Una sola chiave (`ui.shell`), invariata.
- `VITE_UI_SHELL`: nessun `.env*` nel `frontend/` del ramo; nel checkout principale `frontend/.env` contiene solo
  `VITE_SUPABASE_URL` e `VITE_SUPABASE_ANON_KEY`, la radice `.env` non ha `UI_SHELL`; `vite.config` senza `define`
  o `envDir` particolari. Nel bundle del ramo `VITE_UI_SHELL` non compare (variabile assente → `'off'`).
- I test esistenti dell'interruttore (`lib/uiShell.test.ts`, `components/shell/AppShell.test.tsx`) sono verdi nella
  suite. Verificato a vista negli scatti: a guscio spento compare «Prova la nuova grafica» in basso a destra; a guscio
  acceso «Torna alla grafica attuale» in alto a destra (scatti `out/shot/v2_1/*.png`), non nascosto dal CSS nuovo
  (l'unico `display: none` della sezione è su `.glass-card::before`).

## 7. Perdita di dati (`strumenti_verifica/grep_perdita_dati.py`)

Sulle 532 righe +/- del diff dei componenti e pagine (escluso `anteprima/`, `fotografia/`, `index.css`):
`fetch(`, `supabase`, `.rpc(`, `.from(`, `localStorage`, `sessionStorage`, `onSubmit`, `<form`, `useQuery`,
`useMutation`, `queryKey`, `setInterval`, `setTimeout`, `WebSocket`, `EventSource`, `URLSearchParams`,
`searchParams`, `navigate(`, `useEffect`, `useState`, `useRef`, `useMemo`, `useCallback`, `onClick`, `window.`,
`import`, `invoke(`, `ipcRenderer` → **0 occorrenze**. `onChange` (1), `data-testid` (12), `aria-label` (1),
`title=` (5), `placeholder` (1), `key=` (2), `disabled` (5), `if (` (2), `return` (4): compaiono solo in righe già
presenti su master in cui è stata aggiunta una classe (tutte di tipo (a) nel §4: il resto della riga è identico).
Conteggio chiamate/WebSocket per pagina guscio spento e acceso: assertito dalla fotografia (26/26 verde).

## 8. Esecuzione (macchina scarica: unico `node` estraneo = Adobe Creative Cloud)

| controllo | esito |
|---|---|
| `npx tsc -p tsconfig.app.json --noEmit` | **0 errori** (exit 0) |
| suite intera ramo, 1° giro (cache Vite fredda, worktree appena installato) | 326 file: 4 rossi / 312 verdi / 10 saltati; test: 30 rossi / 4809 verdi / 50 saltati. Rossi: 26 fotografia (timeout 60 s e conteggi presi a metà caricamento), 2 `SafeStrategy.test.tsx`, 1 `PosizioniChiuse.raggruppamento.test.tsx` (velocità), 1 `uiDefault.test.ts` |
| rilancio solo `src/fotografia` | 4 file, 39 test: **38 verdi, 1 rosso (`uiDefault`)**; fotografia 26/26 verde |
| rilancio solo `SafeStrategy.test.tsx` + `PosizioniChiuse.raggruppamento.test.tsx` | 50/50 verdi |
| suite intera MASTER nello stesso worktree (cache calda, esclusi i 2 test nuovi) | 314 file verdi / 10 saltati; **4829 verdi** / 50 saltati (521 s) |
| suite intera ramo, 2° giro (cache calda) | 326 file: **315 verdi, 1 rosso** / 10 saltati; test: **4838 verdi, 1 rosso (`uiDefault`)** / 50 saltati (515 s) |
| atteso dal referto cloud | 316 file / 4839 test verdi → su Windows 4838 + 1 rosso per il difetto CRLF del §0 |
| fotografia `off` | `git diff master -- frontend/src/fotografia/` = solo i 3 file nuovi; nessuna fotografia rigenerata |
| `npm run build` ramo | exit 0; `dist/assets` **3.522.996 B** (CSS 140.832, JS 3.382.164) |
| `npm run build` master (stesso worktree, `git checkout master -- frontend/src`, poi ripristino) | exit 0; `dist/assets` **3.495.588 B** (CSS 119.666, JS 3.375.922) |
| differenza | **+27.408 B = +0,78 %** (CSS +21.166, JS +6.242): sotto il 5 % |

I 29 rossi del primo giro non sono del ramo: spariscono a cache calda e da soli; master nello stesso ambiente è
verde. Resta il solo `uiDefault`.

### Falsificazioni (ogni file ripristinato con `git checkout --`, `git status` pulito alla fine)

| difetto introdotto | test | esito |
|---|---|---|
| `components/ui/form.tsx` convertito in LF (contenuto git identico) | `uiDefault` | **verde 2/2** (prova che il rosso è solo CRLF) |
| `components/ui/card.tsx`: `rounded-xl` → `rounded-2xl` (classe di default) | `uiDefault` | **rosso**: «components/ui/card.tsx: classi di default cambiate» |
| in coda a `index.css`: `.ds-v2-scheda { color: #ff0000; }` (fuori scope) | `cssVeste` + `cssGuscio` | **rosso** (3): `cssGuscio` «.ds-v2-* solo dentro [data-shell]», `cssVeste` «selettori che varrebbero anche con ui.shell=off: ['.ds-v2-scheda']», contrasto |
| in coda: `[data-shell="v2"] .ds-v2-scheda { font-size: 9px; }` | `cssVeste` | **rosso**: «nessuna dimensione di carattere sotto i 10 px» |
| direzione non provata dalla sessione cloud: `.glass-card { background: #ff0000; }` (regola GLOBALE, non `ds-v2`) inserita in `index.css` PRIMA del marcatore della veste | `cssVeste` + `cssGuscio` | **VERDI 11/11: il difetto passa**. Le guardie controllano solo la sezione dopo il marcatore e le sole classi `ds-v2-*`. Il mio `scoping_css.cjs` invece lo prende («ECCEZIONI 1: 920: .glass-card»). Oggi il ramo non ha regole simili (§5): è un limite della guardia, non un difetto presente. |

## 9. Confronto visivo guscio spento: ramo contro master

Lo strumento della sessione cloud (`confronto2/strumenti/server.mjs` + `scatta.mjs`) non gira su Windows così com'è
(import dinamico di percorsi assoluti senza `file://`, Playwright globale `/opt/node22/...`, `/tmp/claude-0`, `ln -s`).
Ho fatto una COPIA per Windows (`strumenti_verifica/server_win.mjs`: stessi alias, stesso client finto, stessa
anteprima popolata) e scattato con Edge headless di sistema (nessuna installazione nuova), 1280×800, profilo nuovo a
ogni scatto (= `localStorage` vuoto = guscio spento), 10 pagine, 2 giri per lato; master servito da
`git checkout master -- frontend/src` nello stesso worktree (porte diverse, cache Vite separate). Confronto pixel:
`strumenti_verifica/confronta.py` → `out/confronto_pixel.txt`.

| pagina | master vs ramo | rumore stesso codice (2 scatti) | giudizio |
|---|---|---|---|
| Control Room | identiche | identiche | uguale |
| Programma (`/board`) | identiche (1° giro); 116 px (2° giro) | ramo: stessi 116 px fra due scatti | animazione |
| Storico calcio | identiche | identiche | uguale |
| Live P&L | identiche | identiche | uguale |
| Mike | 5.193 px, fascia testata | master: 5.832 px stessa zona | età «feed fermo da…» / animazioni |
| Omega | 5.774 px, riquadro (24,48)-(1082,84) | master: 5.515 px stesso riquadro | età del feed |
| Safe Strategy | 9.101 px, testata | master: 9.109 px stessa zona | età del feed |
| Segui live | 4.352 px su una riga (minuti/pallini) | ramo: 4.350 px stessa riga | dinamico (a vista identiche) |
| Scelta sport | 404 px / 280.130 px | 411.359 px fra due scatti di master | animazione d'ingresso (framer-motion) |
| Dashboard tennis | 385.236 px | ramo 473.262, master 79.486 fra due scatti | animazione d'ingresso delle schede (a vista: stessa pagina a metà dissolvenza) |

Nessuna differenza fuori dalle zone animate o a tempo. Guscio ACCESO (server con `VITE_UI_SHELL=v2`, scatti in
`out/shot/v2_1/`): Control Room e Mike hanno la veste del prototipo (sidebar, testata, pannelli, tessere KPI, chip,
marchi della fonte), coerente con `confronto2/control-room.affianco.png`; giudizio a vista, non pixel.

## 10. Tre proposte della sessione cloud (decisione dell'utente) — tutte SOLO a guscio acceso

| proposta | dove | scoping | giudizio tecnico |
|---|---|---|---|
| righe del ladder più alte (≈21 visibili invece di 32) | `index.css` `[data-shell="v2"] .ds-v2-ladder-riga { min-height: 20px; font-size: 11.5px }`, classe in `LadderView.tsx:1110` | sotto `[data-shell="v2"]` | aree cliccabili più grandi, mai più piccole; la centratura del ladder misura dal DOM (`LadderView.tsx:532`, `offsetTop`/`clientHeight`), nessuna costante di altezza in JS: regge. Costo: meno profondità visibile senza scorrere. Non ho rimisurato le celle in Chromium (vedi NON VERIFICATO) |
| marchi della fonte coi colori del prototipo (CONTO rosso, BOT sky, PROVA verde, STIMA ambra) | `index.css` righe ~1166-1188, `MarchioSoldi.tsx` (+`ds-v2-marchio`) | sotto `[data-shell="v2"]` | coerente; testo invariato |
| «Confermo: soldi veri» rosso pieno | `[data-shell="v2"] .ds-v2-pulsante--armato` (sfondo `#dc2626`, alone) su `SchedaChiusura.tsx:303`, `SchedaChiusuraOmega.tsx:267`, `SchedaPropostaOpportunita.tsx:599` (oggi `bg-orange-500`) e sui bottoni armati di `PannelloBot`, `RigaFreno`, `RigaOrdiniReali` | sotto `[data-shell="v2"]` | più vistoso di oggi, come chiede il brief |
| «PAPER · SIMULATO» verde | `TennisTerminal.tsx:188-197` (`ds-v2-chip--paper` accanto a `bg-amber-500`) | sotto `[data-shell="v2"]` | coerente col verde unico di PAPER. **Reperto collegato**: nella stessa pillola `LIVE · REALE` riceve `ds-v2-chip--live` (sfondo rosso al 14 %, testo rosa) al posto di oggi `bg-red-500 text-white` (rosso PIENO): a guscio acceso l'avviso «soldi veri» del terminal tennis diventa MENO vistoso di oggi. Solo v2; da far decidere all'utente |

## 11. I due bug segnalati e non corretti (preesistenti, non corretti qui)

**Mojibake in `frontend/src/components/live/ScalperPanel.tsx`** (`strumenti_verifica/mojibake.py`): file
**identico byte per byte su master e sul ramo → preesistente**. 67 righe, 85 sequenze (non 24 come scrive il referto
cloud): 27 righe di commento, **40 righe di codice/testo** (a schermo, nei `toast`, nel `confirm` e nei `title`).
Righe con testo visibile e testo atteso:
45 `ARMAMENTOâ€¦`→`ARMAMENTO…`; 48 `CHIUSURAâ€¦`→`CHIUSURA…`; 157 `âš ï¸ CACCIA MULTI-LINEA…`→`⚠️ CACCIA…`;
158 `(n=1) â€” la bibbia`→`(n=1) — la bibbia`; 161 `âš ï¸ ATTIVARE LO SCALPER…`→`⚠️ ATTIVARE…`;
162 `piazzerÃ  … (stake â‚¬${stake})`→`piazzerà … (stake €${stake})`; 205 `'ATTIVATO'} â€” ${eventName}`→`— `;
225 `corsoâ€¦ … comparirÃ `→`corso… … comparirà`; 239 `Scalper Botâ€¦`→`Scalper Bot…`;
253 `âš  Stato scalper … â€” i dati`→`⚠ … — i dati`; 261 `pre-match Â· stop`→`pre-match · stop`;
267 `servizio âœ“`→`servizio ✓`; 272 `ARMATO â€” nessun ordine`→`ARMATO — nessun ordine`; 311 `Stake â‚¬`→`Stake €`;
321 `DEMO Â· PAPER (… â€” mai soldi veri)`→`DEMO · PAPER (… — mai soldi veri)`; 343 `âš ï¸ Gamba INTERVALLO`→`⚠️ Gamba`;
344 `aggregato âˆ’1.74â‚¬`→`aggregato −1.74€`; 357 `+0.99â‚¬/14 eventi, worst âˆ’0.49`→`+0.99€/…, worst −0.49`;
364 `Stake sniper â‚¬`→`Stake sniper €`; 382 `â‚¬/partita (n=1) â€” VALIDARE`→`€/partita (n=1) — VALIDARE`;
399 `âš ï¸ Theta … EVâˆ’,`→`⚠️ Theta … EV−,`; 400 `campionare) â€” SOLO PAPER`→`— SOLO PAPER`;
408 `Stake theta â‚¬`→`Stake theta €`; 439 `Tetto perdita â‚¬`→`Tetto perdita €`; 511 `stake â‚¬{ctrl.stake}`→`stake €{…}`;
526 `nessun consenso â†’ neutro`→`nessun consenso → neutro`; 532 `â€¢ {r}`→`• {r}`;
546, 552, 579, 584, 607, 612 `` `â‚¬${…}` ``→`` `€${…}` `` (i valori dei P&L, es. «â‚¬0.71»);
569, 574 `'âœ“' : 'â€”'`→`'✓' : '—'`; 597-598 (commento JSX); 627 `Nessuna attivitÃ  ancoraâ€¦`→`Nessuna attività ancora…`;
660 `<> â€” cicli`→`— cicli`; 662, 664 `(lordo) â‚¬{…}`→`(lordo) €{…}`; 667 `> â€” {ctrl.error}`→`— {ctrl.error}`.
(Elenco completo con commenti in uscita di `mojibake.py`.)

**Due bottoni «Parametri» uguali sulla riga «Safe base»** — preesistente, identico a guscio spento. Causa:
`PannelloBot.tsx:668-673` rende sulla stessa riga `{parametriRiga}` E `{mostraParametri && parametri}`.
Per la riga `safe-base`, `parametriRiga` è il foglio della SOLA strategia (`ControlRoom.tsx:450-475`,
`BotParamsSheet soloStrategia='base'`), e poiché `safe-base` è la prima riga del bot Safe
(`righeBot.ts:108` `primaDelBot = !visti.has(i.bot)` → `mostraParametri=true`, `PannelloBot.tsx:473-475`) arriva
anche `parametri.safe` (`ControlRoom.tsx:418-430`, foglio dell'INTERO servizio Safe). Entrambi usano il trigger di
`safestrategy/ParamsSheet.tsx:259` con testo fisso «Parametri» e la stessa icona: due bottoni indistinguibili.

## Altri reperti (nessuno tocca il guscio spento)

1. `uiDefault.test.ts` rosso su Windows (CRLF) — condizione della fusione, vedi in testa.
2. Le guardie CSS (`cssVeste`, `cssGuscio`) non vedono una regola globale aggiunta in `index.css` FUORI dalla
   sezione della veste o non `ds-v2` (falsificazione §8). Suggerimento: confrontare tutto `index.css` con master
   (come `scoping_css.cjs`).
3. `TennisTerminal`: «LIVE · REALE» meno vistoso a guscio acceso (§10).
4. `PannelloBot.tsx:69`: lo stato `running` usa la classe `ds-v2-chip--paper` (nome fuorviante, tinta uguale a oggi).
5. Strumenti `confronto2/strumenti/*` della sessione cloud: solo Linux (vedi §9); i `.py` sono in perimetro AUDIT.
6. Le leve globali (`text-white`, `border-white/10`, `bg-black/60`, `text-[9px]`→10 px …) cambiano a guscio acceso
   ogni occorrenza di quelle utility in tutte le pagine: effetto ampio, voluto, solo v2.

## NON VERIFICATO

- L'exe Electron vero col backend vivo e i canali locali reali: tutto è stato provato con il client finto e
  l'anteprima popolata della sessione cloud.
- Aree cliccabili del ladder in v2: non ho rieseguito `misura_ladder.mjs` (richiede Playwright, non installato e non
  installabile per vincolo); verificato solo dal CSS (`min-height` più alta, larghezze invariate) e dal codice di
  centratura.
- Confronto visivo: solo 10 pagine, solo 1280×800, solo viewport (non pagina intera: Edge CLI non fa full-page),
  orologio non fissato; 1600 px, Watchlist, Report, Match replay, Analytics, Multi-ladder, Market watch, Trade
  journal, Tennis terminal, Ladder pop-out non scattati da me.
- Fedeltà al prototipo a guscio acceso: giudicata a vista su Control Room e Mike, non pagina per pagina.
- Interazioni a guscio acceso (fogli parametri, dialoghi, conferme a due tempi) non cliccate da me: coperte solo dai
  test esistenti (che girano a guscio spento salvo la fotografia v2).
- Font veri Sora/Inter (rete esterna non verificata negli scatti).
- Contrasto: non ricalcolato in modo indipendente, solo il test `cssVeste` (verde, e falsificato dalla sessione cloud).
