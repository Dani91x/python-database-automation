# W_B1 — referto (30/09/2026, sera)

Worktree `...\.claude\worktrees\agent-a32982190acf0f4b4`. Base: `git checkout --detach -f d4b4f6b` (dopo
`B1_backup_pre_W.patch`), poi `R_B1_incr_lane.patch` applicata pulita. Patch: `W_B1.patch` = `git diff -- frontend/`
(R_B1 + W_B1, 15 file, `git apply --check -R` = 0). Niente commit, niente build, nessun processo.

## 1. P10 — la scheda PRE-PARTITA riceve le operazioni e mostra il cash out
- `pages/ControlRoom.tsx`, `ElencoPartite` ramo `pre`: passa `operazioni={operazioni.get(p.event_id) ?? []}` e
  `mike={mikeEventi?.get(p.event_id) ?? null}` a `SchedaPreMatch`. Commento aggiunto in testa al file. (Il
  «commento-contratto» che diceva che la pagina non passa le operazioni stava in testa a `SchedaPreMatch.tsx` e
  nella doc della prop: aggiornati li'.)
- `SchedaPreMatch.tsx`: prop `mike?: MikeEvent | null` nuova; sotto le operazioni `<CashOutGlobalePartita sport
  operazioni mike />` (non modificato: senza gambe abbinate non si monta e non apre sottoscrizioni) e `SchedaMike`
  (`data-testid="cr-pre-mike"`) se Mike «ha una posizione» = ha righe su questa partita O il servizio ne dichiara
  (`mike.positions`). Regola scelta da me: dichiarata.
- PRIMA: pre-partita senza ordini ne' cash out. DOPO: righe dell'operazione (`cr-pre-operazioni`), riquadro «cash out
  della partita» (LIVE/PROVA come in gioco), scheda di Mike.

## 2. Eta' delle quote nella barra tennis
- Verificato nel Python: `state.updated_ms` = `int(datetime.now(...)*1000)` nel momento in cui il runner COSTRUISCE lo
  stato mercati dall'ultimo book in cache (`tennis_runner.py:1477-1503`), riscritto a OGNI giro del worker senza
  write-on-change (`tennis_runner.py:1607-1611` -> `tennis_db.upsert_tennis_now`, `tennis_db.py:266-292`, canale locale
  + upsert). E' una LETTURA, non un cambio: quindi NON le parole di `EtaQuote` («ultimo cambio»), ma
  «ultimo aggiornamento del runner: N s». Colori (`LETTURA_CLS`, scelta mia, dichiarata): entro 20 s GRIGIO neutro,
  MAI il verde di «fresco» (una lettura recente non prova prezzi freschi: la cache del runner puo' essere vecchia);
  oltre 20 s o «età ignota» ARANCIONE (una lettura vecchia prova che il runner e' fermo). Title: «ultima LETTURA ...
  non l'ultimo cambio di prezzo».
- `useTennisVivo.ts`: `etaQuoteS` + `freschezzaQuote` (da `row.state.updated_ms`, ricalcolati col tic da 1 s gia'
  esistente dell'hook; null se manca, mai l'eta' del punteggio). `SchedaPartita.tsx` (solo la barra):
  `cr-tennis-vivo-eta-quote` accanto alle celle. L'eta' del punteggio (`cr-tennis-vivo-eta`) resta com'era.

## 3. Spread «poco liquido»
- `QuoteMercato.tsx`: `SOGLIA_SPREAD_TICK = 5`, `spreadTick(back, lay)` con `ticksBetween` (`lib/riskMath.ts`); se
  lo spread supera 5 tick, accanto alla cella (FUORI dalla cella: il testo della cella resta «X 15,00/18,00») una nota
  grigia «spread N tick · poco liquido» con title. Vale per 1X2, P1/P2, barra tennis e linee Under/Over (stesso
  componente). Un lato assente: nessuno spread.
- Nota sull'esempio dell'utente «1 40,00/50,00 · X 15,00/18,00 · 2 1,08/1,10»: 40->50 = 5 tick (passo 2 fra 30 e 50):
  alla soglia, nessuna nota; 15->18 = 6 tick: nota; 1,08->1,10 = 2 tick: niente.

## 4. Tennis P1/P2 col nome
- `celleMatchOdds(sport, odds, giocatori?)`: con ENTRAMBI i nomi dello scanner (`p.giocatori`) la cella porta il nome
  (P1 = `giocatori.p1`), title «<nome> = selezione del Match Odds con ordine Betfair (sortPriority) 1: nome dallo
  scanner (event_name diviso), abbinato per ordine — P1 = primo nome = sortPriority 1». Un nome mancante/vuoto: P1/P2.
  Applicato alla pre-partita e alla fila tennis dello scanner della scheda in gioco (non alla barra del runner, che
  ha gia' i nomi con i prezzi). L'assunzione ordine-nome resta NON dimostrata dal codice: e' dichiarata, come nella barra.

## Test (nuovi, tutti falsificati)
`SchedaPreMatch.cashout.test.tsx` 3 (nuovo file) · `ControlRoom.test.tsx` +1 (la pagina passa le operazioni al
pre-match) · `useTennisVivo.test.ts` +2 · `SchedaPartita.test.tsx` +4 (eta' quote barra ×3, nomi tennis) ·
`QuoteMercato.test.tsx` +5 (spread ×4, nomi tennis) · `SchedaPreMatch.test.tsx` +1 (nomi tennis).
Test esistenti cambiati: nessuno. Rossi prima del codice: P10 2/3, etaQuoteS 2, spread 2 (poi corretto l'esempio
40/50 del mio test: sono 5 tick, non 10). Il test di pagina P10 e quelli della barra li ho scritti insieme al codice:
la loro prova sono W1, W5, W6.
Falsificazioni (`falsifica_w_b1.ps1`, copia fuori dal repo, try/finally, hash identico, `git diff` identico prima/dopo):
W1 pagina senza operazioni al pre-match ROSSO · W2 niente cash out ROSSO (2) · W3 niente scheda Mike ROSSO ·
W4 eta' quote = eta' punteggio ROSSO (2) · W5 colore dal punteggio ROSSO · W12 verde di «fresco» su una lettura
ROSSO (rilanciate W5/W12 dopo `LETTURA_CLS`, diff identico) · W6 la lettura chiamata «ultimo cambio»
ROSSO (2) · W7 soglia inclusiva ROSSO · W8 spread con un lato assente ROSSO · W9 nomi ignorati ROSSO · W10 un nome solo
basta ROSSO · W11 pre-match senza nomi ROSSO.

## Numeri
- tsc: 0 errori (alla fine, e di nuovo dopo `LETTURA_CLS`).
- mirati `--maxWorkers=2` (QuoteMercato, SchedaPreMatch, SchedaPartita, SchedaPreMatch.cashout, useTennisVivo): 86/86;
  dopo `LETTURA_CLS`: SchedaPartita 38/38.
- allargato (`src/components/controlroom src/pages/ControlRoom.test.tsx src/components/trading/StatoOrdine.montaggio.test.tsx src/lib/flussoLineeMike.test.tsx src/lib/controlRoom.test.ts`, `--maxWorkers=2`): **73 file, 1167/1167**
  (prima di `LETTURA_CLS`, che tocca solo la classe di uno span della barra tennis; dopo: SchedaPartita 38/38).

## Non verificato
- App a schermo non vista (jsdom).
- Pre-partita con posizione aperta: il cash out usa i prezzi della ladder al ms se il contesto della Control Room la
  fornisce, altrimenti lo scanner (dichiarato riga per riga da `CashOutGlobale`): non provato su una partita vera.
- Barra tennis: «ultimo aggiornamento del runner» dice quando il runner ha RILETTO la sua cache; se lo stream del
  runner tace, la cache resta vecchia e il numero resta basso (il runner riscrive comunque). Il numero non vede quel
  caso; lo vede il flusso/punteggio. Da sapere.
