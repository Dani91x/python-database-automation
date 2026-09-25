# AUDIT3 — fix pannello tennis, reperto b (orderMode='OFF' non disabilitava dry-run) — 25/09/2026

Delegato Sonnet, sessione B, worktree `agent-a89c17abdd96807d8`. Perimetro stretto:
solo `frontend/src/components/tennis/TennisBotPanel.tsx` e il suo test.

## Cosa faceva (reperto, AUDIT3_TEST_PANNELLO_TENNIS_2026-09-25.md, reperto b)

Con `orderMode='OFF'`:
- la checkbox "Dry-run" restava ABILITATA (`disabled={active || busy}`, nessun controllo
  su `orderMode`);
- l'utente poteva toglierla; `handleArm` (righe 498-537) fa scattare `window.confirm`
  SOLO quando `!dryRun && orderMode === 'LIVE'` → in OFF nessuna conferma;
- `armTennisBot` veniva chiamato con `dry_run:false` esplicito;
- il badge sotto la checkbox diceva comunque "runner OFF: dry-run forzato" — la riga
  scritta in `tennis_bot_control` mentiva rispetto a quel testo.

Non un rischio sui soldi (`Betfair/stream/tennis_live/tennis_runner.py:611-655`: il
runner in OFF non registra il worker ordini e forza comunque `dry_run=True`, kill-switch
lato Python non aggirabile dal control), ma un difetto di consapevolezza/coerenza
DB-UI, come da criteri PROCESSO_STANDARD_BOT.md (dati che il pannello scrive devono
riflettere quello che promette a video).

## Cosa fa ora

Scelta dichiarata (coerente col runner, che in OFF forza SEMPRE `dry_run=True` e non fa
mai partire ordini): **OFF si comporta come LIVE per il gate dry-run** — checkbox sempre
SPUNTATA e DISABILITATA, `dryRun` forzato a `true` e mai "touchable" finche' il bot non
e' attivo; l'armamento resta possibile (bottone ARMA non disattivato) ma porta SEMPRE
`dry_run:true`. Non ho scelto "ARMA disabilitato" perche' armare in dry-run quando il
runner e' OFF non ha alcun effetto sugli ordini (il runner Python le' non le esegue
comunque) ed e' il comportamento gia' presente e testato per LIVE-default-prudente:
riusa lo stesso pattern invece di introdurne uno nuovo.

`frontend/src/components/tennis/TennisBotPanel.tsx`:
- riga ~134-142 (useEffect): `if (orderMode === 'LIVE' || orderMode === 'OFF') { setDryRun(true); setDryRunTouched(false); return; }`
  (prima solo `orderMode === 'LIVE'`).
- riga ~241-256 (label + Checkbox): `disabled={active || busy || orderMode === 'OFF'}`,
  label con `opacity-60 cursor-not-allowed` quando `active || orderMode === 'OFF'`
  (prima solo `active`).
- riga ~272-276 (badge informativo): testo esteso da "runner OFF: dry-run forzato" a
  "runner OFF: dry-run forzato, nessun ordine possibile" (nessun cambio di logica, solo
  chiarezza — la riga ora e' vera).

In PAPER e LIVE: NESSUN cambiamento di comportamento (i test 1-5 e i casi AUDIT3
esistenti restano verdi senza modifiche al loro codice atteso).

## Perche'

La riga `tennis_bot_control` e' il contratto tra pannello e runner/DB: se dichiara
"dry-run forzato" a video ma scrive `dry_run:false`, chiunque legga il DB (dashboard,
report, un secondo operatore) vede uno stato falso. Forzare lo stato React a rispecchiare
il kill-switch del runner chiude il buco senza toccare la logica di arm/disarm ne'
introdurre un secondo `window.confirm` (gia' escluso nel referto precedente).

## Test — `frontend/src/components/tennis/TennisBotPanel.test.tsx`

Aggiornati/aggiunti (12 test totali nel file, tutti nel dominio del pannello):
- `describe('TennisBotPanel — default protetto per modalita (AUDIT3 caso 1)')`, caso
  OFF: ora verifica anche `expect(checkbox).toBeDisabled()` oltre allo stato spuntato.
- `describe('TennisBotPanel — orderMode OFF (AUDIT3 caso 5)')`: il vecchio test
  "OFF, utente toglie la spunta e arma... dry_run=false" (che documentava il reperto b
  come comportamento REALE non bloccato) e' stato riscritto in
  "OFF: la checkbox e disabilitata, un click non la tocca, ARMA porta sempre
  dry_run=true": verifica `checkbox` disabilitata, un `user.click(checkbox)` non cambia
  `data-state` (resta `checked`), il bottone ARMA resta abilitato, nessun `window.confirm`,
  e `armTennisBot` riceve `dry_run:true`.
- Nessun altro test toccato: i casi 1-5 (gate LIVE/PAPER), il caso PAPER esplicito, il
  caso "OFF default" e il caso "payload completo" restano identici e verdi.

Esito: `npx vitest run src/components/tennis/TennisBotPanel.test.tsx` → **12/12 verdi**.

## Falsificazione (obbligatoria)

Ripristinato temporaneamente `disabled={active || busy}` (comportamento vecchio, senza
il `|| orderMode === 'OFF'`), lasciando il resto del fix invariato, e rilanciato la
suite: **2 test rossi** come atteso —
`AUDIT3 caso 1 > OFF: ... DISABILITATO` e `AUDIT3 caso 5 > OFF: la checkbox e
disabilitata...`, entrambi con `expect(checkbox).toBeDisabled()` fallito (checkbox
risultava abilitata). Ripristinata la correzione (`disabled={active || busy ||
orderMode === 'OFF'}`); `git diff` del componente torna pulito (vedi sotto), suite di
nuovo 12/12 verde.

## Aggiornamento 25/09 — mutazione del coordinatore, test aggiunto (13esimo)

Il coordinatore ha rilevato un buco nella copertura sopra: tutti i test montano il
pannello GIA' in `orderMode='OFF'` (nuovo mount), quindi nessuno prova il forzaggio
`dryRun=true` dell'useEffect (`TennisBotPanel.tsx` riga 140) quando `orderMode` CAMBIA
a runtime (rerender con nuova prop, es. downgrade `LIVE_ORDER_MODE` -> OFF mentre il
pannello resta montato). Mutazione verificata dal coordinatore: togliendo
`|| orderMode === 'OFF'` dalla riga 140 (lasciando intatto il `disabled` della
checkbox), la suite restava 12/12 verde — la checkbox appariva bloccata (lucchetto
visivo corretto) ma lo stato interno `dryRun` restava quello scelto dall'utente in
PAPER (`false`), quindi ARMA avrebbe comunque spedito `dry_run:false` nonostante il
messaggio "dry-run forzato".

Aggiunto un 13esimo test, `describe('TennisBotPanel — downgrade runtime PAPER -> OFF
forza dry-run (mutazione coordinatore 25/09)')`: monta il pannello in PAPER, l'utente
tocca ESPLICITAMENTE la checkbox (la spunta e la ritoglie, cosi' `dryRunTouched=true`
— condizione necessaria: senza touch il ramo di fallback dell'effetto forza comunque
`true` per qualsiasi `orderMode != 'PAPER'`, mascherando la mutazione), poi il test fa
`rerender(...)` con `orderMode='OFF'` (stesso componente, nuova prop — non un nuovo
mount) e verifica che la checkbox torni `checked` e resti disabilitata, e che ARMA
porti `dry_run:true`.

Falsificazione rieseguita di persona: tolto di nuovo `|| orderMode === 'OFF'` dalla
riga 140 (identica mutazione del coordinatore) → **1 test rosso** (il nuovo, che si
ferma su `expect(checkboxOff).toHaveAttribute('data-state', 'checked')` perche' la
checkbox resta `unchecked` pur essendo disabilitata) e **12 verdi** (gli altri 12,
inclusi i due che montano direttamente in OFF, non toccano il caso — confermano che
prima mancava proprio questa prova). Ripristinata la riga 140 originale
(`orderMode === 'LIVE' || orderMode === 'OFF'`); `git diff --stat` del componente
torna a "17 insertions(+), 4 deletions(-)" (identico a prima della mutazione); suite
**13/13 verde**; `npx tsc -p tsconfig.app.json --noEmit` → nessun output, exit 0.

## NON VERIFICATO

- Non ho eseguito la build (`npm run build`) ne' la suite Vitest intera del frontend:
  fuori perimetro per ordine esplicito del brief ("niente build, niente suite intera").
- Non ho toccato ne' verificato `Betfair/stream/tennis_live/tennis_runner.py`: la lettura
  delle righe 611-655 citate nel reperto e nel brief e' presa per buona (gia' letta nel
  reperto originale AUDIT3_TEST_PANNELLO_TENNIS_2026-09-25.md), non ho rieseguito un
  replay o una lettura diretta del sorgente Python in questa sessione.
- Non ho verificato il comportamento a runtime nell'app desktop (nessun avvio/riavvio
  dell'app, come da vincolo del progetto: la avvia/riavvia solo l'utente).
- La junction `frontend/node_modules` mancava in questo worktree all'avvio della sessione
  (probabile incidente di creazione del worktree, non causato da questo lavoro): l'ho
  creata io (`New-Item -ItemType Junction` verso `frontend/node_modules` del checkout
  principale, nessuna scrittura nel principale) per poter eseguire vitest/tsc. Segnalo al
  coordinatore per verifica che non sia un sintomo di un problema piu' ampio sul worktree.

## File toccati e comandi con esito

File toccati (nessun commit, nessun `git add`):
- `frontend/src/components/tennis/TennisBotPanel.tsx`
- `frontend/src/components/tennis/TennisBotPanel.test.tsx`
- (worktree) creata junction `frontend/node_modules` -> checkout principale
  `frontend/node_modules` (mancante all'avvio, necessaria per eseguire i test)
- Questo referto: `AUDIT_2026-09-25/AUDIT3_PANNELLO_TENNIS_OFF_FIX_2026-09-25.md`

Comandi ed esiti:
- `npx vitest run src/components/tennis/TennisBotPanel.test.tsx` → **12 passed (12)**
  (prima e dopo la falsificazione/ripristino della prima consegna).
- Falsificazione 1 (consegna iniziale): `disabled={active || busy}` (senza
  `orderMode==='OFF'`) → `npx vitest run ... -t "OFF"` → **2 failed | 1 passed | 9
  skipped** (i 2 test sul disabled diventano rossi, come atteso).
- Dopo la mutazione segnalata dal coordinatore, aggiunto il 13esimo test (downgrade
  runtime PAPER->OFF) → `npx vitest run src/components/tennis/TennisBotPanel.test.tsx`
  → **13 passed (13)**.
- Falsificazione 2 (mutazione del coordinatore rieseguita di persona): tolto
  `|| orderMode === 'OFF'` dalla riga 140 dell'useEffect → **1 failed (il nuovo test) |
  12 passed**. Ripristinato → di nuovo **13 passed (13)**.
- `npx tsc -p tsconfig.app.json --noEmit` → **exit code 0, nessun output** (0 errori),
  rieseguito anche dopo l'aggiunta del 13esimo test.
