# SAFE BASE SOLO NEL SECONDO TEMPO — referto del delegato (07/10/2026 sera)

Decisione dell'utente (testuale): «SAFE BASE SEMPRE E SOLO SECONDO TEMPO». Base di partenza:
`claude/eloquent-franklin-g2nyk5` @ `2af4b773` (contiene l'ESATTO solo nel 2T, merge `2e70ff5`).
Worktree: `/home/user/python-database-automation/.claude/worktrees/agent-a4674e5bfb5783628`,
ramo `lavoro-base`. **Lavoro NON committato** (vedi par. 6).

## 1. Causa radice
`evaluate_base` (`Betfair/safe_strategy/engine.py`) aveva come finestra solo `minute_check` con
`minuteMin` 55. All'intervallo il feed IPS tiene `FirstHalfEnd` ma il minuto continua a contare
(misura del 25/09 in `Betfair/stream/scalper/atlante_v4.py:536-541`: 35674515, 45 -> 56 in 13';
sulla 35797769 lo stato vero dell'intervallo e' `FirstHalfEnd` con timeElapsed 45-50, reg 45).
Con il minuto a 55-56 la BASE poteva segnalare a partita ferma. Prova TDD: con la mutazione
B-M1 (= codice di prima) `test_intervallo_al_55_non_entra` e il test del motore intero sono rossi
(stato `signal`). Nota: sulla 35797769 il minuto dell'intervallo e' arrivato a 50 e il punteggio
era 1-1 (BASE comunque fuori): il caso al 55 usa la forma vera dello stato con il minuto misurato
sull'altra partita.

## 2. Cosa ho cambiato
- `engine.py`: `evaluate_base` aggiunge `secondo_tempo_check(ctx)` subito dopo il minuto (stessa
  funzione e stessa fonte `tempo_da_stato_ips` dell'ESATTO, stessi esiti: 2T vero, 1T, recupero
  del 1T e intervallo falso, stato assente o ambiguo n/d). Soglia 55 invariata, nessun parametro
  nuovo. `SafeEngine.fase_ignota_events(variante)` generalizza
  `esatto_fase_ignota_events` (che resta e la richiama).
- `bot_service.py`: `_log_base_fase_ignota` (scarto `base_fase_ignota`, solo con la BASE accesa),
  chiamata in `scan_and_place` prima dell'uscita su «nessun segnale»; corpo comune
  `_log_fase_ignota`. **Difetto trovato e corretto**: senza `signal_key` le due righe ESATTO e
  BASE della stessa partita avrebbero avuto la stessa chiave di deduplica in `_log_skip` e,
  con motivi diversi, si sarebbero alternate scrivendo a ogni giro: ora
  `signal_key = "fase_ignota:<variante>"` (vale anche per l'ESATTO: chiave in piu' nel payload,
  motivo invariato).
- `certificazione.py`: controllo di condotta **B18** (stessa verifica di E11, funzione comune
  `_solo_secondo_tempo`).
- `frontend/src/lib/safeStrategy.ts`: `evaluateBase` aggiunge `secondoTempoCheck(ctx)` dopo il
  minuto (gemello della pagina).
- `COSTITUZIONE_SAFE_STRATEGY.md` par. 2: nota datata 07/10 sera.
- Test: NUOVI `Betfair/safe_strategy/tests/test_base_secondo_tempo_2026_10_07.py` (19) e
  `frontend/src/lib/safeStrategy.baseSecondoTempo.test.ts` (6). Aggiornati (la decisione cambia
  l'atteso, o finto senza lo stato IPS che il vero ha sempre):
  `test_esatto_secondo_tempo_2026_10_07.py::test_la_regola_e_solo_dellesatto` (ora la BASE ha il
  check, la PUNTA no), `safeStrategy.secondoTempo.test.ts` (idem),
  `test_engine.py::test_scan_calcio_payload_completo_da_segnale_base` e il gemello in
  `safeStrategy.test.ts` (aggiunto `score_raw` 2T con la forma vera).

File toccati: `Betfair/safe_strategy/{engine,bot_service,certificazione}.py`,
`Betfair/safe_strategy/COSTITUZIONE_SAFE_STRATEGY.md`,
`Betfair/safe_strategy/tests/{test_engine,test_esatto_secondo_tempo_2026_10_07}.py`,
`frontend/src/lib/{safeStrategy.ts,safeStrategy.test.ts,safeStrategy.secondoTempo.test.ts}`;
nuovi: i due test sopra e questo referto. `frontend/node_modules` = collegamento simbolico al
checkout principale (ignorato da git).

## 3. Test e falsificazioni
- `python3 -m pytest Betfair/safe_strategy -q -p no:cacheprovider`: **2275 passati, 8 saltati,
  1 xfail, 0 rossi**.
- `npx vitest run src/components/safestrategy src/lib/safeBot.test.ts src/lib/vetoCampionati.test.ts
  src/lib/safeStrategy src/pages/SafeStrategy src/lib/faseIps`: **29 file, 588 test, 0 rossi**.
- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori** (exit 0, output vuoto).
- Falsificazione (copia, mutazione, test, ripristino con sha256): **7 mutazioni, 7 ROSSE**:
  B-M1 check tolto dalla BASE (Python, 2 rossi); B-M2 check tolto dal gemello TS (5 rossi);
  B-M3 B18 muto; B-M4 il bot non chiama la diagnostica BASE; B-M5 `signal_key` tolta (motivi che
  si alternano); B-M6 attivita' BASE con la BASE spenta; B-M7 diagnostica BASE con la soglia
  dell'ESATTO. Una prima B-M7 (variante fissa «esatto» nel ciclo) era VERDE: mutante
  equivalente (stesso contesto -> stesso esito del check per ESATTO e BASE), sostituita.
  Codice ASCII-only nelle righe aggiunte (verificato).

## 4. Migrazioni SQL
Nessuna.

## 5. Parita' paper/live
Check nel motore, a monte della modalita': paper e live identici. Bot e pagina con lo stesso check.

## 6. NON fatto / NON verificato
- **Commit NON fatto**: il classificatore dei permessi ha negato il commit («Unrequested Commit»:
  il messaggio di un agente non vale come consenso dell'utente). Non l'ho aggirato.
- Il lavoro ESATTO non committato del mio worktree (identico, file per file, a quello integrato
  nel ramo) e' in uno stash etichettato `delegato-a4674e5-esatto-2t-0710` (`7fba88a4`) e il diff
  e' in `scratchpad/esatto_lavoro_non_committato.diff`. Va scartato a mano dopo il controllo.
- Ho creato per errore un secondo worktree
  `.claude/worktrees/agent-a4674e5bfb5783628-base` (sul ramo `lavoro-base`, contenuto di
  `f9b02968`, nessuna modifica mia): non posso scriverci ne' rimuoverlo. Va rimosso dal
  coordinatore (`git worktree remove`, e' pulito rispetto a `f9b02968`).
- Replay non lanciati (come da istruzioni). Atteso su 35797769/35760084: nessun ordine BASE
  cambiato (la BASE non entra sulle due partite); B18 sollecitato con 0 violazioni.
- Suite intera del repo e vitest intero non lanciati.

## 7. Decisioni per l'utente
Nessuna nuova. La PUNTA (66') non e' raggiungibile nel 1T e non cambia.

## 8. Da controllare in paper
All'intervallo di una partita con la favorita avanti 1-0 e banca della sfavorita in 20-34: valutazione
BASE «Solo nel 2° tempo = intervallo (FirstHalfEnd)», stato no, nessun ordine; dalla ripresa, dal 55',
ingresso come prima.
