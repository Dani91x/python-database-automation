# SPEC - spegnimento ORDINATO dell'app (per chi tocca `desktop/main.js`)

Cantiere A (fine evento), 28/09/2026. Reperto R-28-3: ad app spenta restano righe `live_follow`
STREAMING (29 il 28/09) perche' `desktop/main.js` `killChildren()` (righe 416-427) chiude i figli con
`taskkill /PID <pid> /T /F`: TerminateProcess, nessun `finally` Python gira.

## 1. Il segnale (lato Python GIA' pronto, cantiere A)

**Un FILE**: `<cartella>/ARRESTO`, con `<cartella>` =
- env `APP_ARRESTO_DIR` se valorizzata, altrimenti
- `<LIVE_STREAM_DATA_DIR>/_arresto` (default `<radice repo>/_live_raw/_arresto`).

Modulo: `Betfair/stream/arresto_ordinato.py` (`percorso()`, `richiedi()`, `cancella()`, `richiesto()`).
Perche' un file e non un segnale: su Windows un processo Python senza console non riceve
CTRL_C/CTRL_BREAK in modo affidabile, e fra `main.js` e il runner c'e' il watchdog. Il file lo vede
qualunque processo, senza porte e senza processi nuovi. Un file con data PRECEDENTE all'avvio del
processo non conta (resto di uno spegnimento di ieri).

Chi lo legge e in quanto tempo:
| processo (`spawnRunner`) | dove | latenza |
|---|---|---|
| `runner-calcio` (`Betfair.stream.watchdog` -> `Betfair.stream.runner`) | `arresto_worker` (flumine, ogni 1 s) + cima del ciclo di `setup_and_run` | <= 1 s in streaming; <= 2 s in attesa senza eventi; <= 15 s nei rami "nessun mercato sottoscrivibile" / attesa di rete |
| `runner-tennis` (watchdog -> `tennis_runner`) | `arresto_worker` (1 s) + cima del ciclo | come sopra (<= 15 s nel ramo "nessun mercato") |

Cosa fanno: fermano il framework, escono dal ciclo, eseguono il `finally`, **exit 0**. Il watchdog
(`Betfair/stream/watchdog.py` `classify_exit`: rc 0 = 'clean') NON li rilancia ed esce anche lui (0):
per `main.js` il figlio (`runner-calcio` / `runner-tennis`) termina da solo.

Gli altri figli (`scalper-service`, `tennis-bot-service --bridge-only`, `safe-strategy-service`,
`omega-service`, `safe-strategy-bot`, `mike-service`, `tennis-odds`) NON scrivono righe STREAMING e NON
leggono il file: restano chiusi dal `taskkill` come oggi.

## 2. Cosa deve fare `main.js` (altro cantiere)

1. **All'avvio** (prima di `spawnRunner`): cancellare `<cartella>/ARRESTO` se esiste.
2. **Alla chiusura**, al posto del solo `killChildren()`:
   1. scrivere `<cartella>/ARRESTO` (creare la cartella se manca; contenuto libero);
   2. attendere che i figli `runner-calcio` e `runner-tennis` escano da soli: controllo di
      `child.exitCode !== null` ogni 250 ms, **al massimo 25 s**;
   3. poi `killChildren()` come oggi, su TUTTI i figli (quelli usciti vengono saltati: `exitCode !== null`).
   Motivo dei 25 s: ramo peggiore 15 s (attesa "nessun mercato") + chiusura dei follow (un UPDATE per
   partita, ~0,1-0,5 s ciascuno) + `motore.scrittore.svuota(5.0)` del runner calcio + logout Betfair.
   In condizioni normali escono in 1-5 s. Oltre i 25 s si uccide comunque (l'app si chiude sempre).
3. Nessun ordine diverso fra calcio e tennis: il file li ferma insieme.

Pseudocodice:
```js
const ARRESTO = path.join(process.env.APP_ARRESTO_DIR || path.join(DATA_DIR, '_arresto'), 'ARRESTO');
// avvio
try { fs.unlinkSync(ARRESTO); } catch (_) {}
// chiusura
async function spegniOrdinato() {
  try { fs.mkdirSync(path.dirname(ARRESTO), { recursive: true });
        fs.writeFileSync(ARRESTO, 'arresto ' + Date.now()); } catch (_) {}
  const runner = children.filter(c => ['runner-calcio','runner-tennis'].includes(c.__nome));
  const t0 = Date.now();
  while (Date.now() - t0 < 25000 && runner.some(c => c.exitCode === null)) await sleep(250);
  killChildren();
}
```
(`DATA_DIR` = stessa cartella del backend: `LIVE_STREAM_DATA_DIR` o `<repo>/_live_raw`.)

## 3. Cosa deve risultare sul DB a spegnimento finito

- `select count(*) from live_follow where status='STREAMING'` = **0**
- `select count(*) from tennis_live_follow where status='STREAMING'` = **0**
- partite calcio seguite a mano ancora vive o future: **PENDING** (il prossimo runner le riaggancia);
  finite: CLOSED/UPLOADED (Replay caricato solo se in registrazione).
- righe `live_follow` `origine='auto'` scritte dall'auto-follow: **CLOSED** (al prossimo avvio le
  riapre il feed o il comando di un bot; `chiudi_orfani` le chiude comunque all'avvio).
- tennis: follow automatici **CLOSED**, a mano vivi **PENDING**, finiti **CLOSED**.
- `live_now`/`tennis_live_now` NON si toccano allo spegnimento (le partite vive restano come sono; al
  riavvio le riscrive il runner, le finite le chiude la pulizia d'avvio).
- Non toccati: `scalper_control` (le sessioni le ferma `ferma_sessioni_al_nuovo_avvio` al prossimo
  avvio), righe `origine='auto'` PENDING scritte dallo scalper (PENDING = nessuno le streamma).

Se `main.js` arriva al `taskkill` senza che un runner sia uscito (25 s scaduti): le righe restano come
oggi e le sistema il prossimo avvio (auto -> `chiudi_orfani`; manuali -> ricatalogate; finite -> CLOSED
dopo la conferma del catalogo vuoto).

## 4. Verifica dopo l'integrazione in `main.js`
1. App accesa con partite seguite; chiudere l'app; entro 25 s: log `ARRESTO ORDINATO richiesto dall'app`
   nei `_logs/` dei due runner, watchdog "Runner terminato in modo pulito".
2. Query del punto 3 = 0 righe STREAMING.
3. Riaprire l'app: le partite PENDING tornano STREAMING da sole; nessun alert "RUNNER CRASHATO".

## 5. Cosa e' verificato lato Python e cosa no
- Test (`test_fine_evento_2026_09_28.py::test_arresto_ordinato_file_e_worker`,
  `test_setup_and_run_controlla_l_arresto_in_cima_al_ciclo`,
  `test_fine_evento_tennis_2026_09_28.py::test_arresto_ordinato_worker_tennis`,
  `test_uscita_ordinata_tennis`, `test_uscita_ordinata_chiude_le_finite_e_rimette_in_attesa_le_vive`):
  file, worker, cablaggio, chiusura dei follow. Falsificati (A1-A5, M6, M7, M12).
- NON verificato: un processo vero sotto watchdog che esce con 0 dopo il file (nessun processo
  lanciato per ordine del brief) e i tempi reali della chiusura.
