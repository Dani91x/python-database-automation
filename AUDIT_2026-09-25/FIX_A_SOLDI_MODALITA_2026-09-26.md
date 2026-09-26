# FIX-A — «soldi e modalità» (KO 1, 4, 5, 8, 10 della fase 3 sessione B + R-F2-12) — 26/09/2026

Delegato Opus (sessione B, coordinatore admin-9d), worktree `agent-a08ad47a8e98a2c8b` (base `498ba07`).
Nessun commit, nessuna scrittura sul DB vero (solo SELECT in sola lettura su `pg_proc`,
`information_schema` e poche righe, per copiare corpi e righe vere), nessun riavvio, nessun replay.
Junction create a mano (non esistevano): `.venv` e `frontend/node_modules` → checkout principale
(togliere con `cmd /c rmdir`, MAI `git worktree remove --force`).

## Riepilogo per voce

| voce | esito | dove |
|---|---|---|
| KO1 Safe paper+live sommati (U0481/U0485/U0507) | **FATTO** (solo frontend, nessuna migrazione Safe necessaria) | `lib/safeBot.ts`, `useSafeBot.ts`, `pages/SafeStrategy.tsx` |
| KO1 Omega latente (`omega_aggregates_sql` senza mode) | **FATTO** (migrazione + frontend con ripiego) | `migrations/omega_state_per_modalita_2026-09-26.sql`, `lib/omega.ts`, `pages/Omega.tsx` |
| KO4 Live P&L posizione fantasma + modalità mischiate | **FATTO** (sorgente = migrazione; filtro = frontend) | `migrations/live_positions_senza_mercati_regolati_2026-09-26.sql`, `pages/LivePnl.tsx` |
| KO5 /mike senza approvazione uscite | **FATTO** (stesso componente e comando della Control Room) | `pages/Mike.tsx` |
| KO8 «Se chiudo ora» = bloccato (Omega, Mike) | **FATTO** | `MatchTradesTable.tsx`, `pages/Omega.tsx`, `lib/mike.ts`, `pages/Mike.tsx` |
| KO10 Omega «storico 109 partite» | **FATTO** (conteggio: `events_traded`) | migrazione Omega + `pages/Omega.tsx` |
| KO10 Mike win rate con gli «a zero» | **FATTO** (conteggio nel motore comune dello storico) | `migrations/storico_esito_a_zero_2026-09-26.sql` |
| R-F2-12 freno che consuma `max_attempts` | **FATTO** | `Betfair/omega/omega_service.py`, `omega_db.py` |
| (8) estensione R-F2-12: `runner_non_agganciato` / `in_aggancio` scaduto | **FATTO** | idem |
| (7) R8 Omega paper senza FOK sul canale | **NON FATTO — bloccato dal classificatore dei permessi** (vedi §7) | nessuna modifica |

## 1. KO1 — Safe: paper e live sommati

**Causa.** `lib/safeBot.ts:1100` (`fetchSafeState`) chiama `get_safe_state` con `{}` →
`safe_aggregates_sql(NULL)` = tutte le modalità; `pages/SafeStrategy.tsx:410` scriveva
`agg.realized_total` sotto «P&L totale · PAPER». Storico: `fetchSafeDaily(from,to,sport)` senza `p_mode`.
Verificato in sola lettura (26/09): `safe_aggregates_sql(NULL)` realized_total −40,47 = paper −43,05 + live 2,58.

**Correzione (nessuna migrazione: `get_safe_aggregates(p_mode)` è già viva dal 13/09, verificato in `pg_proc`).**
- `fetchSafeState({ perModalita: true })` legge anche `get_safe_aggregates('paper')` e `('live')` in parallelo →
  `aggregates_by_mode`. Senza opzione (Control Room) nessuna lettura in più. Una modalità che non si legge resta
  `null`, mai ripiegata sulla somma.
- `aggregatiDellaModalita(state, mode, modoDelBot)`: per-modalità → `aggregates.mode === mode` → altrimenti SOLO
  `realized_<mode>_total` (oggi/liability assenti = «—» o ripiego del servizio, che è già per modalità:
  `bot_service.py:9227`) → RPC vecchia senza `mode` attribuita solo alla modalità del bot.
- Pagina: KPI/barra dalla modalità del bot; l'ALTRA modalità, se ha attività, in una riga a parte
  `safe-altra-modalita` con la sua etichetta e «NON inclusa». Storico: filtro Modalità (PAPER/LIVE), di serie la
  modalità del bot, `fetchSafeDaily/fetchSafeDayTrades(..., mode)`. «Se chiudo ora» del tab Trade: solo righe della
  modalità in etichetta.

**Test** (righe = risposte vere di `safe_aggregates_sql` del 26/09): `frontend/src/lib/safeBot.perModalita.test.ts`
(7), `frontend/src/pages/SafeStrategy.fixA.test.tsx` (5), `SafeStrategy.storico.test.tsx` aggiornato (asseriva la
chiamata SENZA modalità, cioè il difetto; ora esige `'paper'` e il passaggio a `'live'`).
**RED**: pagine/hook a HEAD → 4/5 page test rossi + storico rosso. **Falsificazione**: mutazione
`const totale = agg.realized_total` in `aggregatiDellaModalita` → test rosso; ripristino verificato sha256.

**Omega (stesso vizio, latente).** `migrations/omega_state_per_modalita_2026-09-26.sql`: overload nuovo
`omega_aggregates_sql(boolean, text)` = stesso corpo vivo + filtro sulla modalità della POSIZIONE + chiavi
`events_traded`, `mode`; `omega_aggregates_sql(boolean)` (quella del SERVIZIO) delega con NULL; `get_omega_state`
aggiunge `aggregates_by_mode {paper, live}` (`aggregates` invariato). Frontend: `aggregatiOmegaDellaModalita` +
riga `omega-altra-modalita`. Senza migrazione: modalità del bot come prima, l'altra ASSENTE (mai la somma).

## 2. KO4 — Live P&L

**Causa sorgente.** `get_live_positions_all()` (corpo vivo = `migrations/betfair_live_pnl_journal.sql`) legge tutta
`betfair_live_positions`; il runner non toglie le posizioni alla regolazione. Riga 14265 (live, evento 35797769,
mercato 1.259819675, 10/07 19:29Z) su mercato regolato (`betfair_live_settled` id 18, live, 10/07 19:31Z).
**Filtro.** `pages/LivePnl.tsx:196,269` «tutte» + posizioni calcio e tennis mai filtrate.

**Decisione riga 14265: ESCLUSA DALLA QUERY** (vale per ogni fantasma futuro, nessun dato toccato). La pulizia è
solo una PROPOSTA facoltativa: `migrations/PROPOSTA_pulizia_posizione_fantasma_14265_2026-09-26.sql` (transazione,
guardie, conteggio atteso 1) — NON eseguita, non necessaria per la pagina.

**Correzione.** Migrazione: `NOT EXISTS (settled stesso market_id E stessa modalità)`. Pagina: niente più «tutte»;
di serie la modalità del runner (`risk.mode`), altrimenti LIVE; realizzato, equity, per mercato/evento, posizioni
calcio (con `(live)`/`(paper)` in chiaro) e tabella TENNIS tutti filtrati per modalità.

**Test**: `frontend/src/pages/LivePnl.fixA.test.tsx` (3, righe vere 14265/14291/14294). RED con `LivePnl.tsx` a HEAD:
3/3 rossi. SQL: banco PGlite (§6), controllo C rosso sul corpo vivo, verde dopo; mutazione `WHERE false` → rosso.

## 3. KO5 — /mike: firmare la proposta d'uscita

`pages/Mike.tsx`: ogni card monta `PropostaUscitaMike` (il componente della Control Room, **non modificato**,
solo importato) → `requestMike('approva_uscita', {event_id, bot, mode, chiave, contesto})`: nessun secondo percorso.
Senza proposta non disegna niente. **Test** `frontend/src/pages/Mike.fixA.test.tsx` (proposta con le chiavi vere di
`engine.gate_uscite`): APPROVA manda `approva_uscita` con `chiave`. RED con `Mike.tsx` a HEAD: rosso.

## 4. KO8 — «Se chiudo ora»

- **Omega**: `legCloseNow()` (la formula della cella, ora usata ANCHE dalla cella) e `omegaCloseNowTotal()` in
  `components/omega/MatchTradesTable.tsx`; la barra usa la somma delle gambe vive della modalità; gamba coperta del
  tutto = il suo P&L bloccato (dichiarato nel commento); gamba senza prezzo fuori e contata
  (`omega-aperto-parziale`). Test `MatchTradesTable.fixA.test.tsx`: lay 1@48→back 32 = −0,50, 1@80→25 = −2,20,
  totale −2,70 = celle. Mutazione `totale += 0` → rosso.
- **Mike**: `closeNowTotal()` in `lib/mike.ts` = somma di `live.cashout.net` (il netto che la card mostra) delle
  partite esposte non terminali della modalità; la barra Operazioni lo usa al posto del bloccato. KPI «P&L bloccato»
  invariato. Test in `Mike.fixA.test.tsx`; mutazione `e.live?.locked` → rosso.

## 5. KO10 — conteggi

- **Omega**: «storico N partite» = `events_traded` (partite distinte, migrazione); senza migrazione partite distinte
  fra le righe caricate della modalità, dichiarato nel `title`. Le aperture (`matches_traded`) restano per il servizio.
- **Mike**: causa nel motore COMUNE `trading_daily_history` (corpo vivo = `migrations/mike_history_v2.sql`, md5
  verificato): a P&L totale 0 ricadeva sullo stato grezzo dell'apertura ('won'). `migrations/storico_esito_a_zero_2026-09-26.sql`:
  a zero → `'scratch'` (fra le regolate, non V/P/void). Vale per Omega/Safe/Mike (stessa definizione del tooltip).
  Righe vere 527/528/555/4762/4768 nel banco: V 3→1.

## 6. Banco SQL (le tre migrazioni)

`AUDIT_2026-09-25/fix_a_soldi/genera_migrazioni.mjs` genera le migrazioni dai file il cui corpo coincide col VIVO
(md5 senza `\r` confrontato in sola lettura con `pg_proc`: trading_daily_history e58a42c8…, omega_aggregates_sql(boolean)
6c00a734…, get_omega_state 5027acf4…, get_live_positions_all 6a4f83df…); ogni sostituzione deve trovare il testo
esattamente una volta. `AUDIT_2026-09-25/fix_a_soldi/banco_sql_pglite.mjs` (PostgreSQL vero in PGlite, installato
nello scratchpad): **PRIMA 6 controlli rossi** sui corpi vivi, **DOPO 0 KO** + idempotenza (doppia applicazione) +
**equivalenza** per il servizio Omega (`omega_aggregates_sql(false|true|())`, `get_omega_aggregates` con `auto`,
`get_omega_state.aggregates`: stessi numeri, solo le 2 chiavi in più). Mutazioni sulle tre migrazioni → 5 KO; rigenerate
→ sha256 identici (`AUDIT_2026-09-25/fix_a_soldi/sha_migrazioni.txt`). Comando:
`node AUDIT_2026-09-25/fix_a_soldi/banco_sql_pglite.mjs <DIR>/node_modules/@electric-sql/pglite/dist/index.js`.

## 7. R-F2-12 + estensione (8) — Omega

**Definizione adottata**: un tentativo della gamba è consumato SOLO se un ordine è stato sottoposto al mercato (o al
suo specchio paper). **Codici esclusi** (prefisso, `_RIFIUTI_PRIMA_DEL_MERCATO`): `kill_switch*` (freno REST/paper di
Omega e ack del runner `M_KILL`, anche `kill_switch_illeggibile`), `runner_non_agganciato` (`M_AGGANCIO`),
`in_aggancio*` (`M_IN_AGGANCIO`). L'aggancio SCADUTO arriva come evento terminale `rifiutato` senza motivo: si
riconosce dall'ack in memoria della porta (accettato con motivo `in_aggancio`), senza bet_id e senza abbinato; ogni
dubbio = il tentativo conta (fail-safe). **Continuano a consumare** (volutamente, per non creare cicli): `comando_scaduto`,
`parametri_invalidi`, `mode_non_servibile`, `guardia_avvio`, `settings_stantie`, VIOLATION di flumine e gli esiti di mercato.
Da decidere dall'utente/coordinatore se allargare.

**Codice** (`Betfair/omega/omega_service.py`): `_leg_certain_failure(..., consuma_tentativo)` e
`_flumine_no_fill_error(..., consuma_tentativo)`; a tentativo NON consumato: riserva chiusa uguale, `meta.tentativo_consumato=False`,
log senza `attempt/max`, e **stessa cadenza** di prima (`_leg_note_rifiuto_senza_tentativo` aggiorna solo l'istante;
`_leg_retry_allowed` usa `ts <= 0` invece di `n == 0`: identico per ogni caso esistente) → a freno tirato si riprova ogni
30 s come prima, senza una riserva a ogni giro. `omega_db.failed_legs` salta le righe `tentativo_consumato=False`.
Nessun cambio di strategia (soglie, stake, gambe invariati).

**Test** `Betfair/omega/tests/test_omega_freno_non_consuma_tentativi_2026_09_26.py` (11): freno VERO
(`controls.motivo_kill_switch` con env e `get_live_settings` chiave `kill_switch`), paper e live; canale con
`PlaceOutcome` vero e costanti vere di `motore_ordini`; evento terminale con `MemoriaComandi` vera; `failed_legs` con
righe dalle colonne del `_select_all`. **RED** sul codice originale: 7 rossi (tutti i casi non consumanti), 4 verdi
(parità). **Falsificazioni**: togliere `in_aggancio` dalla lista → 2 rossi; cadenza `n == 0` → 1 rosso; ripristino sha256.
Regressione: `test_omega_kill_switch_rest_o1` 13/13 (con `OMEGA_ORDINI_VIA_CANALE=false`, vedi sotto),
`test_omega_audit_2026_09_11` 70/70, `test_porta_ordini_omega_f6` 33/33.

**Reperto collaterale (non mio, da sapere)**: il `.env` del PC ora accende `OMEGA_ORDINI_VIA_CANALE`; i test lo
leggono e `test_omega_kill_switch_rest_o1_2026_09_24.py` fallisce 12/13 così com'è (canale giù nel banco) anche PRIMA
delle mie modifiche. Il mio test file spegne l'interruttore apposta con `monkeypatch`.

**(7) R8 — NON FATTO.** La modifica `omega_service.py:~2917` (`time_in_force=_PO.FOK` anche in paper, docstring
aggiornata) è stata **negata dal classificatore dei permessi** («Modify Shared Resources»). Non ho cercato vie
alternative. Serve il permesso esplicito dell'utente; se concesso: cambiare quella riga, e aggiornare
`Betfair/omega/tests/test_porta_ordini_omega_f6_2026_09_24.py:419` che oggi ASSERISCE il difetto
(`cmd["time_in_force"] is None  # paper`). Nota: anche il ramo coda paper (`_flumine_enqueue_place`) non manda FOK in
paper («la coda lo mette solo in live»): stessa decisione.

## 8. Cosa deve fare l'utente — migrazioni, in ordine

1. `migrations/storico_esito_a_zero_2026-09-26.sql` (verifica in testa al file: Mike paper 01-26/09 → V 148, P 91)
2. `migrations/omega_state_per_modalita_2026-09-26.sql`
3. `migrations/live_positions_senza_mercati_regolati_2026-09-26.sql`
4. (facoltativa) `migrations/PROPOSTA_pulizia_posizione_fantasma_14265_2026-09-26.sql`

Tutte idempotenti, nessuna modifica ai dati (tranne la 4, facoltativa). Poi `npm run build` del frontend (regola del repo)
e riavvio dell'app da parte dell'utente.

## 9. Cosa NON ho potuto verificare

- Le migrazioni sul Postgres VERO (solo PGlite con tabelle dai tipi di `information_schema`): RLS, ruoli reali e
  prestazioni di `get_omega_state` con 3 scansioni di `omega_trades` (127 righe oggi) non misurate.
- La pagina Omega non ha un test di pagina nuovo per la riga «altra modalità» e «storico N partite»: coperti gli helper
  (`aggregatiOmegaDellaModalita`, `omegaCloseNowTotal`) + `tsc` + regressione Omega (39+ test verdi).
- `PropostaUscitaMike` dentro /mike usa il ladder al ms del canale locale e `ChiusuraRigaContext` (assente fuori dalla
  Control Room: nessun seguito dell'abbinamento sotto la card di /mike, solo l'esito del clic). Non provato nell'app viva.
- Il caso VIOLATION/`rifiutato` generico del motore non è escluso dal budget (scelta conservativa, §7).
- Nessuna prova nell'app vera (vietato riavviarla); nessun replay.
- Control Room (fuori perimetro) legge ancora `get_safe_state` senza modalità per le sue righe: non toccata.

## 10. File toccati (elenco esatto)

Modificati: `Betfair/omega/omega_service.py`, `Betfair/omega/omega_db.py`,
`frontend/src/lib/safeBot.ts`, `frontend/src/components/safestrategy/useSafeBot.ts`, `frontend/src/pages/SafeStrategy.tsx`,
`frontend/src/pages/SafeStrategy.storico.test.tsx`, `frontend/src/lib/omega.ts`, `frontend/src/pages/Omega.tsx`,
`frontend/src/components/omega/MatchTradesTable.tsx`, `frontend/src/lib/mike.ts`, `frontend/src/pages/Mike.tsx`,
`frontend/src/pages/LivePnl.tsx`.
Nuovi: `Betfair/omega/tests/test_omega_freno_non_consuma_tentativi_2026_09_26.py`,
`frontend/src/lib/safeBot.perModalita.test.ts`, `frontend/src/pages/SafeStrategy.fixA.test.tsx`,
`frontend/src/components/omega/MatchTradesTable.fixA.test.tsx`, `frontend/src/pages/Mike.fixA.test.tsx`,
`frontend/src/pages/LivePnl.fixA.test.tsx`, le 4 migrazioni di §8, `AUDIT_2026-09-25/fix_a_soldi/{corpi.mjs,
genera_migrazioni.mjs, banco_sql_pglite.mjs, sha_migrazioni.txt}`, questo referto, `AUDIT_2026-09-25/fix_a.patch`.
NON toccati: `Betfair/mike/service.py`, `Betfair/safe_strategy/service.py`, `stream.py`, nessun file fuori perimetro
(`PropostaUscitaMike.tsx` solo importato).

Suite eseguite (solo file toccati): pytest 11 + 13 + 70 + 33 verdi; vitest nuovi 7+5+5+4+3 verdi, regressione Safe 99,
Omega/Mike/Control Room 106 (+1 skip), LivePnl 3; `npx tsc -p tsconfig.app.json --noEmit` 0 errori.
