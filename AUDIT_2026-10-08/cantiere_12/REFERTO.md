# CANTIERE 12 - Sei test vitest rossi solo su Windows (verificatore della barra) - REFERTO

Data: 08/10/2026. Worktree: `/home/user/python-database-automation/.claude/worktrees/agent-a862a5e8ab9473fd0`.
Punto di partenza: il worktree era sul vecchio `8226d76`; l'ho portato (fast-forward, nessun commit mio) alla cima
indicata dal brief `b5547eb`. Lavoro NON committato. Nessuna strategia toccata, nessun file di bot toccato,
`.gitattributes` non toccato, nessun `skip`, le fixture NON rigenerate.

## 1. Cause (confermate leggendo il codice)

1. **Impronta delle registrazioni** - `impronteSorgente` (TS) e `impronte_sorgente` (Python) facevano lo sha256 dei
   byte del file. Sul PC `core.autocrlf=true` scrive i `.timeline.jsonl` con CRLF, le fixture portano lo sha dei
   byte LF: due test rossi (uno per partita). Nel repo i `.timeline.jsonl` sono `i/lf w/lf`
   (`git ls-files --eol registrazioni_banco`); i `.gz` sono binari (`-text`) e non cambiano.
2. **Lancio dei figli** - il test faceva `spawn('npx', [...])` senza shell (su Windows `npx` e' `npx.cmd`: ENOENT,
   poi attesa del timeout 120-180 s: quattro test rossi); lo script si rilanciava con `npx.cmd` + `shell: true` ma con il
   percorso del file NON tra virgolette (con shell Node incolla i pezzi con uno spazio: `C:\...\PYTHON DATABASE\...`
   si spezzava in due argomenti).

## 2. Cosa ho cambiato (file:riga)

- `frontend/src/lib/replayVerificaBarraLancio.ts` (NUOVO) - la funzione unica del comando figlio:
  `comandoViteNode(argomenti, piattaforma)` (riga 43; pura, piattaforma come parametro) e
  `quotaArgomentoWin32` (riga 31). win32: `npx.cmd`, `shell: true`, ogni argomento con spazi / `"&|<>^()%!` / vuoto tra
  virgolette doppie (regole CRT: virgolette interne con backslash, backslash prima di virgoletta e in coda raddoppiati);
  altrove: `npx`, `shell: false`, argomenti invariati.
- `frontend/scripts/verifica_barra_replay.ts:34,110-117` - il rilancio usa `comandoViteNode`; in piu' se il figlio non
  parte (`figlio.error`) stampa il motivo ed esce 1 (prima usciva 1 senza dire perche').
- `frontend/src/lib/replayVerificaBarraScript.test.ts:15,23,36-45` - il test usa la STESSA funzione dello script, con
  `shell: cmd.shell`; l'evento `error` del figlio fa cadere il test SUBITO col motivo (non dopo il timeout); i quattro
  timeout (180/180/120/120 s) diventano `TEMPO_MAX_MS = 40_000`. I casi e le asserzioni sono identici.
- `frontend/src/lib/__fixtures__/replayBarraTutte.ts:53-69` - `improntaContenuto(buf, testo)`: `\r\n` -> `\n` prima dello sha per
  i file di testo (`.jsonl`), byte grezzi per i `.gz`; `impronteSorgente(ev, cartella?)` (parametro nuovo, di serie la
  cartella del repo). Questo file e' l'helper dei test della barra (`__fixtures__`), l'ho considerato "test relativi".
- `tools/replay_barra_fixture.py:100-132` - `_sha256_file(path, testo=False)` con la stessa regola (a blocchi da 1 MiB, il CR
  in coda al blocco aspetta il blocco dopo), `impronte_sorgente(event_id, cartella=None)`; `.jsonl` in chiaro con
  `testo=True`, `.gz` con `testo=False`. Stessa regola del TS.

## 3. Test aggiunti

TS (17 nuovi, tutti in `frontend/src/lib/`):
- `replayVerificaBarraLancio.test.ts` (7): comando win32 con percorso con spazi tra virgolette (UN argomento), `npx.cmd`,
  `shell:true`; percorso senza spazi invariato; quoting di vuoto / `&|^()` / virgolette interne / backslash finale e prima
  di virgoletta; linux e darwin = `npx` senza shell e senza virgolette; prova con una SHELL VERA (sh) che l'argomento
  quotato con spazio arriva a node come UNO, non quotato come TRE.
- `replayVerificaBarraImpronta.test.ts` (10): per ognuna delle 2 registrazioni, copie LF e CRLF in cartelle TEMPORANEE
  (`os.tmpdir()`, mai riscrittura dei file del repo) danno la stessa impronta, uguale a `fixture.sorgente` esistente;
  l'impronta dei file del repo coincide con la fixture (fixture NON rigenerate); i `.gz` restano byte per byte; piu' 3 test
  sulla funzione (LF = CRLF, `.gz` non normalizzato, CR isolato conta) e 1 sintetico (testo normalizzato, gz no).
Python (6 nuovi, `tools/test_replay_barra_fixture.py`): LF = CRLF; i `.gz` non si normalizzano; CRLF a cavallo del blocco da
1 MiB; CR isolato e CR finale contano; impronte delle 2 fixture esistenti identiche (anche con copia CRLF in `tmp_path`).

## 4. Mutazioni (rosso poi verde, file ripristinato con verifica dello sha)

Strumento: `scratchpad/c12mut.py` (sostituisce una stringa, lancia il test, ripristina SEMPRE, confronta lo sha).
| # | Mutazione | Esito rosso | Ripristino sha (16 car.) |
|---|---|---|---|
| M1 | `quotaArgomentoWin32` ritorna l'argomento invariato | Lancio.test: 5 rossi su 7 | `c849babe899585ac` |
| M2 | ramo win32 non scatta (`'win32-mutato'`) | Lancio.test: 2 rossi su 7 | `c849babe899585ac` |
| M3 | backslash finale non raddoppiato | Lancio.test: 1 rosso su 7 | `c849babe899585ac` |
| M4 | win32 con `shell: false` | Lancio.test: 1 rosso su 7 | `c849babe899585ac` |
| M5 | `improntaContenuto` senza normalizzazione | Impronta.test: 4 rossi su 10 (partite.test resta verde su Linux LF) | `2e55e5c42508cf74` |
| M6 | impronta normalizza anche i `.gz` | Impronta.test: 5 rossi su 10 | `2e55e5c42508cf74` |
| P1 | Python senza normalizzazione | 4 rossi (LF/CRLF, a cavallo, 2 fixture) | `8e9d6f9a13210e7c` |
| P2 | Python normalizza anche i `.gz` | 5 rossi (incluso `test_fixture_presente_e_aggiornata` x2) | `8e9d6f9a13210e7c` |
| P3 | Python senza il resto a cavallo del blocco | 1 rosso (`..._a_cavallo_del_blocco_di_lettura`) | `8e9d6f9a13210e7c` |
| P4 | Python perde il CR finale | 1 rosso (`test_un_cr_isolato...`; la prima stesura del test NON lo vedeva: l'ho corretto e rifalsificato) | `8e9d6f9a13210e7c` |
| S1 | script: rilancio senza il percorso del file | Script.test: 3 rossi su 4 | `fb27881d0cba30d8` |
| S2 | test: eseguibile inesistente (`npx-inesistente`) | Script.test: 4 rossi su 4 in 341 ms (fail-fast, prima 120-180 s) | `39bd845a8462d363` |
Dopo ogni ripristino i test sono tornati verdi (esecuzioni sotto).

## 5. Comandi lanciati e esito VERO (macchina a load average 18-29, 4 CPU condivise: i tempi NON sono confrontabili)

- `npx vitest run` intero, PRIMA (modifiche gia' parziali: i file toccati dopo l'avvio possono essere entrati nel conteggio):
  364 file, **5352 test: 1 rosso | 5300 verdi | 51 skip**. Il rosso: `RitardiPanel.fixb.test.tsx` (timeout di `waitFor` sotto load 25);
  rilanciato da solo: 3/3 verdi. File: `vitest_prima_riepilogo.txt`.
- `npx vitest run` intero, DOPO: 366 file, **5369 test (+17): 3 rossi | 5315 verdi | 51 skip**. I 3 rossi sono di timeout sotto
  carico in file NON toccati (`BotParamsSheet.test.tsx` 1, `SafeStrategy.test.tsx` 2); rilanciati da soli: 2 file, 75/75 verdi.
  Nessun rosso nei file della barra. File: `vitest_dopo_riepilogo.txt`. **Non ho un run intero a 0 rossi**: due run interi, due
  volte rossi di carico diversi e non correlati al cantiere; ogni rosso e' stato rilanciato isolato ed e' verde. Il coordinatore
  rilanci l'intero su macchina libera.
- Test della barra (4 file, prima della mutazione): `replayVerificaBarraLancio` 7, `...Impronta` 10, `...partite` 17,
  `...Script` 4 = 38/38 verdi. Il file Script con il tempo limite 40 s: 9-19 s per caso sotto load 28, 79 s per l'intero file nel
  run completo: nessun caso ha superato i 40 s (margine ~2x, vedi limiti).
- `npx tsc -p tsconfig.app.json --noEmit`: exit 0, output vuoto (dopo tutte le modifiche).
  Lo script (`scripts/` non e' nel `tsconfig.app.json`): controllato con un tsconfig fuori dal repo
  (scratchpad): nessun errore nello script ne' in `replayVerificaBarraLancio.ts`; solo 2 errori `import.meta.env` in
  `integrations/supabase/client.ts` per mancanza dei tipi vite in quel tsconfig di prova (non dipendono dal cantiere).
- Python: `python3 -m pytest tools/test_replay_barra_fixture.py -q -p no:cacheprovider`:
  DOPO **2 rossi | 13 verdi** (15 test); con `BARRA_FIXTURE_SALTA_RIGENERAZIONE=1`: 13 verdi, 2 skip. PRIMA: 9 test, gli stessi 2 rossi
  (verificato rigenerando con il file ORIGINALE di `HEAD`: la fixture non coincide). I 2 rossi sono `test_fixture_riproducibile_dal_raw[...]`:
  il curator rigenerato dal raw in questo container produce 1108 frame contro 1107 della fixture (un frame in piu' e
  scarti di timestamp), `meta` uguale. **Non e' causato dal cantiere** (parte `sorgente` esclusa, il difetto e' nei `frames`) ed e' fuori
  perimetro (curator / ambiente: versioni delle dipendenze in questo container). Non rigenerato niente. Da guardare dal coordinatore sul PC.
  File: `pytest_dopo_completo.txt`.
- Fixture `replay_barra_*.json` e `registrazioni_banco/`: `git status` mostra nessuna modifica (impronte LF identiche, provato dai test).
- Replay del banco: NON eseguiti ne' necessari (nessun bot ne' banco toccato; il cantiere riguarda solo strumenti della barra).

## 6. Limiti dichiarati (cosa NON ho verificato)

- **Non ho potuto provare Windows di persona**: nessun cmd.exe qui. Verificato: la funzione per `win32` (test puri),
  il quoting passando da una shell sh (sulle regole degli spazi), le copie CRLF in cartella temporanea. Il lancio reale di `npx.cmd`
  con shell e percorso con spazio lo rifa' il coordinatore sul PC (sezione sotto).
- Il quoting win32 non gestisce `%VAR%` dentro un argomento (cmd espande `%` anche tra virgolette): oggi gli argomenti sono
  percorsi e opzioni, ne' i percorsi del repo ne' le opzioni contengono `%`. Quel carattere obbliga solo a quotare.
- Tempo limite 40 s invece dell'esempio 30 s del brief: 30 s sarebbe stato flaky (18,6 s misurati per il caso piu' lungo con load 28);
  il fallimento rapido del mancato avvio e' dato dall'evento `error`, non dal timeout.
- `replayBarraTutte.ts` sta in `__fixtures__` (fuori dall'elenco letterale del perimetro, dentro "test relativi"): dichiarato.

## 7. Decisioni per l'utente

Nessuna (nessuna strategia, soglia, stake o tetto toccati).

## 8. PRONTO PER LA VERIFICA SUL PC (comandi esatti)

Dal worktree / dopo il merge, in `frontend/`:
1. `git ls-files --eol registrazioni_banco/35760084/35760084.timeline.jsonl` deve dire `i/lf w/crlf` (il caso del PC).
2. `npx vitest run src/lib/replayVerificaBarra.partite.test.ts src/lib/replayVerificaBarraScript.test.ts src/lib/replayVerificaBarraImpronta.test.ts src/lib/replayVerificaBarraLancio.test.ts`
   atteso: 4 file, 38 test, 0 rossi (prima i 6 rossi: 2 `partite` + 4 `Script`).
3. Dalla cartella `frontend/` con il percorso "PYTHON DATABASE" con lo spazio, il comando del protocollo
   `npx vite-node scripts/verifica_barra_replay.ts --evento 35797769 --json` con VITE_SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY nell'ambiente
   (il rilancio interno ora quota il percorso: prima non partiva).
4. `python tools/test_replay_barra_fixture.py` con pytest: `python -m pytest tools/test_replay_barra_fixture.py -q -p no:cacheprovider`
   atteso sul PC: i 6 test nuovi + `test_fixture_presente_e_aggiornata` verdi anche con CRLF su disco; `..._riproducibile_dal_raw` come prima (verde sul PC, rosso nel container).
5. `npx tsc -p tsconfig.app.json --noEmit` 0 errori; `npx vitest run` intero.
Mutazioni da rifare: M1, M5, P1, S1 (almeno), con lo sha di ripristino.

## Blocco per la cronostoria

CANTIERE 12 (08/10, cloud): sei test vitest rossi solo su Windows. Impronta sha256 dei `.jsonl` di registrazione
indipendente dai fine riga (CRLF -> LF; i `.gz` no), in TS (`__fixtures__/replayBarraTutte.ts::improntaContenuto`) e Python
(`tools/replay_barra_fixture.py::_sha256_file`), fixture NON rigenerate. Lancio del figlio `npx vite-node` in UNA funzione
(`frontend/src/lib/replayVerificaBarraLancio.ts::comandoViteNode`, win32: `npx.cmd`, shell, argomenti tra virgolette)
usata da script e test; mancato avvio del figlio = rosso immediato; timeout dei test 40 s. +17 test vitest, +6 Python,
12 mutazioni rosse/verdi. tsc 0. Intero vitest: 2 run con soli rossi da carico in file non toccati (verdi isolati).
Aperto: `test_fixture_riproducibile_dal_raw` rosso nel container Linux (1108 vs 1107 frame), pre-esistente. Da
verificare sul PC (Windows reale). Non committato.

## Verifica del coordinatore cloud (08/10)
- Diff riletto: impronta con `\r\n`->`\n` solo per i `.jsonl` (i `.gz` byte grezzi), le fixture LF esistenti hanno la stessa impronta
  (nessuna rigenerata); una funzione sola `comandoViteNode` per script e test.
- Test dei file della barra (Lancio, Impronta, partite) 34/34 verdi nel worktree.
- MIE MUTAZIONI: M1 nessun quoting su win32 -> 2 rossi; M2 `.jsonl` non normalizzato -> 3 rossi. Ripristino verificato (diff identico).
- `test_fixture_riproducibile_dal_raw` (2 casi) e' rosso ANCHE sulla cima di partenza nel cloud (verificato dal coordinatore:
  2 rossi, 7 verdi su `b5547eb`+W2+C5): NON dovuto a questo cantiere; affidato al cantiere 13 (strumento della barra).
- Windows vero NON provato: passi della sez. 8 da rieseguire sul PC.
