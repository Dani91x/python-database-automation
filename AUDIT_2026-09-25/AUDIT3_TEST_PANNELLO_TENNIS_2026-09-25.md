# AUDIT3 — test di componente per il pannello per-partita dei bot tennis (25/09, sessione B)

Reperto di origine: `AUDIT_2026-09-24/AUDIT_MODALITA_PAPER_LIVE_2026-09-24.md` §(b).4 — "nessun
test di componente per il pannello per-partita" (`TennisBotPanel.tsx`): checkbox `dryRun`,
`window.confirm` quando `!dryRun && orderMode==='LIVE'`, chiamata `armTennisBot` -> RPC
`tennis_bot_arm`.

## 0. Stato trovato all'apertura (importante per il coordinatore)

Il reperto del 24/09 e' **stantio**: `frontend/src/components/tennis/TennisBotPanel.test.tsx`
**esiste gia'**, committato su `origin/master` come parte del commit `bfd4d1f` (gia' integrato dal
coordinatore, vedi `CRONOSTORIA.md` riga ~2648, h17:40 del 25/09: "test TennisBotPanel (`bfd4d1f`;
REPERTO: il gate live per partita ha UN solo confirm, non due)"). Quel file copre gia' 5 casi (i
casi 2 e 3 del brief, piu' i tipi del payload). **Non l'ho riscritto da zero**: ho letto tutto il
componente aggiornato (25/09, auto-mode + uscite manuali incluse) e ho **aggiunto** i casi che
quel file non copriva, nello stesso file, con lo stesso stile (finti derivati da
`TENNIS_BOT_REGISTRY`, non ricopiati a mano).

Casi gia' presenti (non toccati, solo riverificati con `npx vitest run`):
1. PAPER, default: arma con `dry_run=false`, nessun confirm.
2. LIVE, checkbox non toccata (default protetto): arma con `dry_run=true`, nessun confirm.
3. LIVE, checkbox tolta, confirm negato: nessuna chiamata a `armTennisBot`.
4. LIVE, checkbox tolta, confirm accettato: arma con `dry_run=false`.
5. Tipi esatti del payload (`dry_run` booleano, `one_tick_per_phase` booleano non stringa).

Casi aggiunti da me (AUDIT3, in coda allo stesso file):
- default protetto per **OGNI** modalita' (PAPER/LIVE/OFF, incluso il testo a video) — brief caso 1.
- PAPER: scelta **esplicita** dell'utente di togliere la spunta (spunta poi la ritoglie), non solo
  il default gia' scoperto — brief caso 4.
- **`orderMode='OFF'`** per intero, mai testato prima — brief caso 5, con un REPERTO (§3).
- payload completo verso `tennis_bot_arm` (nessuna scrittura parziale) — brief caso 7, esplicito.
- caso 6 (uscita manuale per bot): NON e' nel componente — documentato in §4, non serve un test qui.

## 1. File toccati

- `frontend/src/components/tennis/TennisBotPanel.test.tsx` — **modificato** (aggiunte 4 nuove
  `describe`, 8 nuovi test; i 5 test preesistenti sono rimasti intatti). Nessuna modifica a
  `TennisBotPanel.tsx`, `lib/tennis.ts` o a codice Python.
- Ho dovuto **creare la junction mancante** `frontend/node_modules` -> checkout principale
  (`New-Item -ItemType Junction`, PowerShell): in questo worktree non esisteva (vitest/tsc non
  partivano, `ERR_MODULE_NOT_FOUND`). Non e' una modifica al repo (node_modules e' ignorato), lo
  segnalo perche' il worktree non era nello stato "pronto" descritto da `CLAUDE.md`.

## 2. Comportamento reale osservato, caso per caso (con numeri)

**Caso 1 — default protetto per modalita'** (`TennisBotPanel.tsx:117` e l'effetto `:134-139`, non
`:117` da solo — vedi §3.a): `dryRun` iniziale = `orderMode !== 'PAPER'`. Osservato:
- PAPER: checkbox `data-state=unchecked`, testo "ORDINI SIMULATI · visibili sul ladder" visibile
  (linea 257-261 del componente).
- LIVE: checkbox `data-state=checked`, nessun avviso "ORDINI REALI".
- OFF: checkbox `data-state=checked`, testo "runner OFF: dry-run forzato" visibile (linea 262-266).
3 test nuovi, tutti verdi.

**Caso 2 — LIVE, dry-run non toccato**: gia' coperto (test preesistente #2), riverificato verde:
arma con `dry_run=true`, nessun `window.confirm`.

**Caso 3 — LIVE, dry-run tolto**: gia' coperto (test preesistenti #3/#4), riverificato verde: un
solo `window.confirm` (testo `/ORDINI REALI/i`), negato -> `armTennisBot` MAI chiamata; accettato
-> chiamata con `dry_run=false` esplicito.

**Caso 4 — PAPER, scelta esplicita di togliere la spunta**: in PAPER la spunta parte gia' tolta
(caso 1); ho quindi testato l'azione ESPLICITA dell'utente (spunta -> la ritoglie) per non
confondere "default" con "scelta". Osservato: nessun `window.confirm` (la guardia in `handleArm`
controlla solo `orderMode==='LIVE'`, mai PAPER), `armTennisBot` chiamata con `dry_run=false`. 1
test nuovo, verde.

**Caso 5 — `orderMode='OFF'`**: **il pannello NON impedisce di armare in OFF** — ne' il pulsante
ne' la checkbox sono disabilitati per `orderMode==='OFF'` (`TennisBotPanel.tsx:233,241,412`
controllano solo `active`/`busy`, mai `orderMode`). Osservato con 2 test:
- default (checkbox spuntata): arma con `dry_run=true`, nessun confirm.
- utente toglie la spunta: **nessun confirm** (la guardia controlla solo LIVE) e `armTennisBot`
  riceve **`dry_run=false`**. Vedi REPERTO in §3.b: non e' un buco di sicurezza sui soldi (il
  backend forza comunque `dry_run=True` per il kill-switch di modalita'), ma e' un'incongruenza
  della UI da segnalare.

**Caso 6 — uscita manuale per bot**: **non esiste in `TennisBotPanel.tsx`**. Vedi §4: nessun test
aggiunto qui, per costruzione.

**Caso 7 — nessuna scrittura parziale**: il payload verso `armTennisBot` e' sempre costruito come
spread di TUTTI i parametri correnti (`{ ...params }`, `TennisBotPanel.tsx:161`) piu' la
conversione booleana dei campi `select/bool`; non esiste un percorso che ne ometta uno. Verificato
con un test dedicato che itera `SCALPER.params` e pretende ogni chiave nel payload ricevuto da
`armTennisBot`, e falsificato (§5.4): con una chiave rimossa a mano il test diventa rosso.

## 3. Due reperti (non correggo: solo per il coordinatore)

**a) Il "default" e' governato dall'`useEffect` (`:134-139`), non dalla `useState` iniziale
(`:117`)** — trovato falsificando: mutare SOLO `useState(orderMode !== 'PAPER')` in
`useState(orderMode === 'PAPER')` **non ha rotto NESSUN test** (12/12 verdi lo stesso), perche'
l'effetto che segue il mount (`dryRunTouched` parte `false`, `orderMode` e' nelle dipendenze) lo
riallinea SUBITO dopo il primo render, prima che React Testing Library restituisca il controllo al
test. La `useState` iniziale e' quindi, di fatto, ridondante/morta per il primo paint osservabile
da un test (e probabilmente anche per l'utente, dato che l'effetto scatta prima che il browser
dipinga). Non e' un difetto funzionale (il risultato finale e' corretto), ma e' un pezzo di codice
che non fa quello che sembra fare a prima lettura — l'ho dovuto scoprire per scrivere una
falsificazione che funzionasse (vedi §5.1, ho dovuto mutare la riga `:137` dentro l'effetto, non
la `:117`).

**b) OFF non e' un "modo sicuro" nella UI, solo nel runner** (`TennisBotPanel.tsx:233,241,412` +
`Betfair/stream/tennis_live/tennis_runner.py:654-655`): il pannello per-partita lascia che
l'utente tolga la spunta "dry-run" e prema ARMA anche con `orderMode==='OFF'`, senza alcun
`window.confirm` e senza disabilitare nulla — mentre il testo a video (linea 262-266) promette
"runner OFF: dry-run forzato". La RPC `tennis_bot_arm` riceve comunque `dry_run:false` (la riga di
control in DB lo dichiara), e SOLO lato Python (`tennis_runner.py:611-613,654-655`, commento "OFF:
dry-run FORZATO (kill-switch, il control non puo' aggirarlo)") il bot viene comunque forzato in
paper_trade: **nessun ordine reale puo' partire**, quindi non e' un rischio sui soldi. Resta pero'
una riga di control bugiarda (`dry_run:false` scritta da un pannello che dichiara "forzato") e
un'assenza di conferma che il resto del componente usa sistematicamente (LIVE) — segnalo per
decisione dell'utente/coordinatore se allineare il testo o il gate, non ho toccato nulla.

## 4. Caso 6 — dove vive davvero l'uscita manuale per bot

`TennisBotPanel.tsx` (il pannello per-partita dentro il Tennis Terminal) **non ha nessun controllo
di uscita manuale**: solo ARMA/DISARMA per l'intero bot su quell'evento (`handleToggle`,
`:156-167`). Cercato con `grep -rn "requestTennisChiudiBot|chiudi_bot|ChiudiBot|uscite_automatiche|
setTennisBotUscite" frontend/src/components/tennis/ frontend/src/pages/TennisTerminal.tsx`: zero
riscontri.

Le due funzionalità del 25/09 che il brief chiama "uscita manuale" vivono nella **Control Room**,
non nel Terminal tennis:
- **"Chiudi ora" per bot** (D3, 24/09): `frontend/src/components/controlroom/chiudiRiga.ts:166`
  chiama `requestTennisChiudiBot` (`frontend/src/lib/tennis.ts:465`, azione `chiudi_bot` sulla
  stessa coda ordini). Gia' testato in
  `frontend/src/components/controlroom/chiudiRiga.test.ts` (non toccato da me).
- **Uscite automatiche/manuali per bot** (25/09, `migrations/tennis_uscite_manuali_2026-09-25.sql`,
  non ancora applicata secondo il commento in `lib/tennis.ts:905-907`):
  `frontend/src/components/controlroom/UsciteTennis.tsx:54` chiama `setTennisBotUscite`
  (`lib/tennis.ts:915`). Test dedicati in `frontend/src/components/controlroom/tennisAuto.test.ts`
  (non toccato da me).

Nessun test aggiunto per il caso 6 in questo file: sarebbe fuori perimetro (componente diverso,
gia' coperto altrove) e il brief lo prevedeva esplicitamente ("altrimenti scrivi che vive
altrove").

## 5. Falsificazione obbligatoria — mutazioni, rosso, ripristino

Tutte le mutazioni sono state fatte SOLO su `TennisBotPanel.tsx`, verificate con
`npx vitest run src/components/tennis/TennisBotPanel.test.tsx --reporter=verbose`, poi ripristinate
e confermate con `git diff frontend/src/components/tennis/TennisBotPanel.tsx` vuoto (vedi §6).

**5.1 — default invertito** (riga `:137`, dentro l'effetto — non la `useState` di riga `:117`, vedi
§3.a): `setDryRun(orderMode !== 'PAPER')` -> `setDryRun(orderMode === 'PAPER')`.
Risultato: **6 test rossi / 12** — tutti e 3 i test "default protetto" (PAPER/OFF), il test PAPER
esplicito (caso 4), entrambi i test OFF (caso 5). I test che non dipendono dal default (LIVE con
checkbox toccata a mano, payload) restano verdi, come atteso.

**5.2 — confirm esteso anche a OFF** (riga `:506`): `if (!dryRun && orderMode === 'LIVE')` ->
`if (!dryRun && (orderMode === 'LIVE' || orderMode === 'OFF'))`.
Risultato: **1 test rosso / 12** — esattamente il test "OFF, utente toglie la spunta" (quello che
certifica il reperto §3.b). Tutti gli altri restano verdi: la falsificazione e' mirata.

**5.3 — checkbox ignorata in `handleToggle`** (riga `:165`): `onArm(descriptor.key, dryRun, stake,
payload)` -> `onArm(descriptor.key, true, stake, payload)` (dry-run sempre vero, a prescindere
dalla spunta).
Risultato: **6 test rossi / 12** — caso PAPER default (#1), i due test LIVE-checkbox-tolta e quello
dei tipi (#3/#4/#5 preesistenti — dimostra che restano falsificabili), il caso PAPER esplicito
(caso 4), il caso OFF-spunta-tolta (caso 5).

**5.4 — payload parziale** (riga `:161`): `{ ...params }` -> omesso `price_min` prima dello spread
(`const { price_min: _omessa, ...params_incompleti } = params`).
Risultato: **7 test rossi / 12** — il test dedicato "payload completo" (caso 7) piu' tutti i test
che confrontano il payload intero con `toHaveBeenCalledWith(...)` (le uguaglianze esatte lo
beccano anche senza un assert dedicato).

Dopo ogni mutazione: ripristino con `Edit` (stringa esatta rimessa), rilancio verde 12/12, e alla
fine `git diff` del componente vuoto (verificato, §6).

## 6. Comandi e esiti

```
cd frontend
npx vitest run src/components/tennis/TennisBotPanel.test.tsx --reporter=verbose
  -> 12 test, 12 verdi (stato finale, dopo il ripristino di tutte le mutazioni)
npx tsc -p tsconfig.app.json --noEmit
  -> 0 errori
git diff frontend/src/components/tennis/TennisBotPanel.tsx
  -> vuoto (il componente non e' stato toccato)
git status --short
  -> " M frontend/src/components/tennis/TennisBotPanel.test.tsx" (unico file modificato)
```

Non ho lanciato la suite intera vitest ne' `npm run build`, come da perimetro del brief ("niente
suite intera, niente build").

## 7. NON VERIFICATO

- Non ho verificato lato Python se esiste un test che certifichi il caso "OFF + dry_run:false
  scritto dalla UI -> forzatura lato runner": ho letto il commento e la logica
  (`tennis_runner.py:611-655`) ma non ho cercato un test dedicato a quella combinazione precisa
  nella suite Python (fuori perimetro: "Lato Python SOLO lettura").
- Non ho verificato se `migrations/tennis_uscite_manuali_2026-09-25.sql` (citata in
  `lib/tennis.ts:905-907`) e' stata applicata al DB: fuori perimetro (nessuna scrittura DB, questo
  e' un audit di test frontend).
- Non ho controllato se il reperto §3.b (OFF senza conferma) e' gia' noto/accettato dall'utente in
  una sezione precedente di `CRONOSTORIA.md` diversa da quella che ho letto (h17:40 del 25/09):
  ho cercato solo "TennisBotPanel"/"bfd4d1f" nel file, non l'ho letto per intero.
