# UI testata e Obiettivo: referto del delegato (01/10)

Delegato Opus, worktree `agent-aef887e5d6759ccb6`. Nessun commit, nessun `git add`, nessun `npm run build`.
Patch: `AUDIT_2026-10-01/UI_HEADER_OBIETTIVO.patch`. Contiene 9 file modificati e 4 file nuovi (aggiunti con `git diff --no-index`). Il controllo `git apply --check -R` è passato sul worktree.

## File toccati
- `frontend/src/pages/ControlRoom.tsx`:
  - `SaldoBetfairCard` non è più montata nella zona Obiettivo. Ho tolto anche il suo import.
  - La zona Obiettivo ora occupa tutta la larghezza (`cr-zona-obiettivo`).
  - Nella testata c'è un nuovo blocco `cr-impianto-stop`: prima le due tessere dei runner (`cr-impianto`), poi gli stop (`cr-freni`).
  - Ho tolto il vecchio `Runner` e `FASE_RUNNER`.
  - `Freni` ora riceve `vm` e passa a `StopPerdita` i dati che il modello di vista porta già: `params`, fonte ed età dello stato di ogni bot (`fonteStato`/`etaStatoS`), `modiStrategia` di Safe e `vm.ricarica`. Nessuna lettura nuova.
- `frontend/src/components/controlroom/testata/FasciaStop.tsx` (riscritto, ASCII):
  - Una riga per stop: NOME, modalità, cifra grande, stato, fonte ed età.
  - Modifica sul posto (`CifraStop`), con cancello e conferma.
  - Frasi nuove al posto di quelle criptiche.
- `frontend/src/components/controlroom/testata/salvaStop.ts` (nuovo): legge l'importo, costruisce il payload e salva con le funzioni esistenti.
- `frontend/src/components/controlroom/testata/TesseraRunner.tsx` (nuovo): `descriviRunner` è una funzione pura, più la tessera che la mostra.
- `frontend/src/components/controlroom/testata/stopPerdita.ts`: aggiunto il campo `modo` a `StopConto`, letto da `mode` della riga `betfair_live_risk_state`.
- `frontend/src/components/controlroom/testata/FasciaSoldiVeri.tsx`: aggiunto l'occhio del saldo.
- `frontend/src/components/trading/DayBar.tsx`: aggiunta la prop opzionale `enfasi` (default false), quindi Mike, Omega e Safe restano identiche. Con `enfasi`:
  - realizzato in `text-5xl`, con accanto "su 250,00 EUR" grande;
  - barra alta `h-8`;
  - l'obiettivo non si ripete nella riga.
- `frontend/src/components/controlroom/ObiettivoHero.tsx`: titolo più grande, `DayBar enfasi`, composizione su 4 colonne a xl.
- Test: `FasciaStop.test.tsx`, `FasciaSoldiVeri.test.tsx`, `pages/ControlRoom.test.tsx` (aggiornati), più i nuovi `salvaStop.test.ts` e `TesseraRunner.test.tsx`.
- Non toccati: `storicoSport.ts`, `PosizioniChiuse.tsx`, `chiuseGiornata.ts`, `dailyHistory.ts`.

## Scelte e verità verificate nel codice
- **A) Card del saldo.** `SaldoBetfairCard.tsx` NON è cancellata: `useControlRoom.ts` ne importa `CANALI_SALDO`. Non è più montata da nessuna parte; la cancellazione o lo spostamento della costante li decide il coordinatore. Montarla apriva due letture in più (fetch e subscribe di account e heartbeat), che ora non partono: il test lo verifica. Non si perde nulla:
  - saldo disponibile ed esposizione, con fonte ed età e "non verificato di recente", restano nella fascia SOLDI VERI;
  - nella card Obiettivo restano fonte del realizzato, "conto non letto", composizione per bot, operazioni regolate oggi, aperto adesso, rischio massimo e corsia PROVA.
- **B) Saldo nascosto.**
  - L'occhio (`cr-saldo-occhio`) nasconde SOLO la cifra del saldo disponibile, che diventa "••••" con title "saldo nascosto: clicca per mostrare"; anche il clic sulla cifra la rimostra.
  - Default: visibile. La chiave è la stessa della card di prima (`cr-saldo-nascosto`), letta e scritta dentro try/catch.
  - Cambio di comportamento: prima la preferenza nascondeva anche l'esposizione, ora non più. Il test vecchio è aggiornato e dichiarato.
  - L'etichetta passa da "Disponibile" a "Saldo disponibile".
- **C) Stop modificabili.** Ogni stop si salva con la stessa RPC e le stesse chiavi di prima:
  - **Conto:** `setLiveSettings({ daily_loss_limit })`. La RPC aggiorna solo le chiavi passate (`betfair_live_risk_limits_v4.sql`). Stessa regola di `LiveControlsPanel`: vuoto = spento, 0 rifiutato.
  - **Safe:** `updateSafeParams(fromValues({...toValues(mergeBotParams(raw), mergeExits(raw.exits), raw), 'risk.daily_loss_stop': -x}, variants, raw))`, cioè il percorso di `BotParamsSheet.save`, compreso il rifiuto con zero strategie.
  - **Mike:** `updateMikeParams(mergeMikeParams({...mergeMikeParams(raw), daily_loss_stop}))`, il percorso del suo foglio.
  - **Omega:** `updateOmegaParams({ params: omegaParamsPatch(raw, {chiave}) })`. La chiave segue il motore (v3 usa `v3_daily_loss_cap`, v2 usa `daily_loss_cap`). `p_daily_goal` vale null, quindi l'obiettivo non viene toccato (la RPC fa coalesce).
- **Cancello:** se i parametri grezzi sono null o `{}`, la cifra è un bottone disabilitato con scritto "parametri non letti: modifica disabilitata"; anche la funzione rifiuta (`StopNonSalvabile`). Per il conto il cancello è lo stato del runner letto.
- **Conferma:** serve per un bot in LIVE, per un bot con modalità non letta e per Safe con una strategia LIVE in `modiStrategia`. Per il conto serve se un bot è live o se la riga ha `mode = live`. La conferma scade da sola dopo 10 s.
- **Dopo il salvataggio** compare "salvato: −X,XX EUR (letto dal database)" con la cifra della riga che la RPC restituisce, poi parte `vm.ricarica`. La cifra principale resta quella dichiarata dal servizio o dal runner, che si aggiorna quando la rilegge.
- **Frasi nuove, verificate prima di scriverle:**
  - "Omega non pubblica se lo stop e' scattato" (`omega_service` scrive solo l'attività `loss_stop`).
  - "Tennis e Scalper: nessuno stop proprio. Li ferma lo stop del Conto quando scatta, ma le loro perdite non lo fanno scattare." Verificato così:
    - nessuno stop giornaliero esiste in `stream/tennis_live/` né in `stream/scalper/`;
    - lo stop del conto lo calcola solo `daily_stop_worker` del runner calcio, da `betfair_live_settled`, che solo il runner calcio scrive;
    - tennis e scalper leggono il freno `betfair_live_settings.kill_switch` (`guardie_tennis.kill_switch_attivo`, `scalper_session.motivo_freno`).
- **Runner:** due tessere, "Runner CALCIO (canale 47331)" e "Runner TENNIS (canale 47332)". Ognuna mostra:
  - pallino connesso / non connesso (`fonte === 'canale'`);
  - processo: in streaming / vivo, in attesa / fermo / mai avviato / stato non letto (tennis: "stato non noto");
  - "ORDINI VERI consentiti" in rosso LIVE, oppure "solo simulati" in tono PAPER (è il tetto del .env, come dice il title);
  - fonte ed età.
  - Cambio di testo: "spento" diventa "fermo", "ignoto" diventa "stato non letto". Test aggiornati e dichiarati.

## Test
- `tsc -p tsconfig.app.json --noEmit`: 0 errori.
- File toccati, eseguiti insieme (testata, trading, ControlRoom, ObiettivoHero): 25 file, 485 test verdi.
  - `FasciaStop` 34, `salvaStop` 15, `TesseraRunner` 6, `FasciaSoldiVeri` 16, `ControlRoom` 141.
- Suite completa: 4691 test passati, 50 saltati, 1 rosso, `Mike.test.tsx` "UNA semantica per i conteggi".
  - Nel primo giro completo era verde; isolato l'ho rilanciato 2 volte ed è verde 31/31.
  - Lo leggo come instabile sotto carico, non legato a queste modifiche (Mike usa `DayBar` senza `enfasi`, quindi invariato). Da riverificare.
- Nel primo giro completo il guardiano del design (`designGuard`) ha bloccato un mio `toFixed`; ora uso `fmtNum` ed è verde.
- **Test esistenti cambiati:**
  - FasciaStop: il link a Segui Live è sostituito dalla modifica sul posto; "scatto non pubblicato" e "stop proprio non pubblicato" sostituiti dalle frasi nuove; lo stato di uno stop scattato.
  - FasciaSoldiVeri: con il saldo nascosto l'esposizione resta visibile.
  - ControlRoom: `cr-stop-conto-modifica`; "spento" diventa "fermo"; "ignoto" diventa "stato non letto"; fonte "canale 47331 · ultimo messaggio"; "ORDINI VERI consentiti".

## Falsificazioni: tutte rosse, poi ripristinate
Script di mutazione: copia, mutazione, test mirato, ripristino. Esiti:

| # | Mutazione | Test rossi |
|---|---|---|
| F1 | default del saldo invertito | 4 |
| F2 | il nascondi torna a coprire l'esposizione | 2 |
| F3 | preferenza non salvata | 2 |
| F4 | tolta la conferma in LIVE | 3 |
| F5 | tolto il cancello nel componente | 2 |
| F6 | esito con la cifra digitata invece di quella del DB | 1 |
| F7 | conferma che non scade | 1 |
| F8 | Safe con strategie live senza conferma | 1 |
| F9 | Omega scrive sempre `daily_loss_cap` | 3 |
| F10 | payload di Safe senza le chiavi ignote | 1 |
| F11 | tolto il cancello in `payloadStop` | 2 |
| F12 | il conto spedisce 0 invece di null | 1 |
| F13 | tennis con la porta del calcio | 3 |
| F14 | "connesso" che ignora la fonte | 1 |
| F15 | card del saldo rimontata nell'Obiettivo | 1 |
| F16 | runner messi dopo gli stop | 1 |

Dopo il ripristino ho rilanciato `tsc` e i test: verdi.

## Cosa NON ho potuto verificare
- Il risultato a schermo: altezza della testata sticky con le tessere e la tabella degli stop, resa del `display: contents` con i title, wrap alle varie larghezze. Nessun build, nessuna app avviata.
- Il salvataggio vero contro Supabase: le RPC sono finte nei test, che verificano nome, argomenti e chiavi.
- Se il runner calcio rilegge `daily_loss_limit` a ogni giro: per questo dopo il salvataggio non affermo "applicato", scrivo solo "letto dal database".
- Una piccola differenza dal foglio di Safe: `ParamsSheetBase` fa il clamp di tutti i campi numerici al salvataggio, mentre qui gli altri campi ripartono dai valori del DB senza ripassare dal clamp. Un valore già fuori range sul DB verrebbe riscritto com'è, invece di essere riportato nei limiti.
- La junction `frontend/node_modules` nel worktree è ancora presente: va tolta con `cmd /c rmdir` prima di `git worktree remove`.


## Correzione dopo la verifica del coordinatore (01/10)

**Reperto del coordinatore.** È sopravvissuta una mutazione in `salvaStop.ts`, nel ramo del conto: `if (r == null) return undefined; return perdita;`, cioè la funzione restituiva la cifra DIGITATA. Il motivo: i test di salvataggio usavano finti che restituivano la stessa cifra digitata (40 → 40), quindi non potevano accorgersene.

**Cosa ho corretto (solo i test, nessun codice di produzione):**
- `salvaStop.test.ts`: in ogni caso il finto della RPC ora restituisce una cifra DIVERSA da quella digitata:
  - conto: digitato 40, riga del DB 35, la funzione ritorna 35;
  - Safe: digitato 40, DB −45, ritorna 45 (era già così);
  - Mike: digitato 40, DB 35, ritorna 35;
  - Omega: digitato 120, DB 110, ritorna 110.
  - Caso nuovo: conto digitato SPENTO, ma la riga del DB dice 25: la funzione ritorna 25.
- `FasciaStop.test.tsx`:
  - il finto del salvataggio ora restituisce 35 per un 40 digitato;
  - il test su Mike verifica che a schermo compaia «salvato: … 35,00 … (letto dal database)» e mai 40,00;
  - caso nuovo sul conto: digitato −40, riga del DB 35, a schermo esattamente «salvato: −35,00 € (letto dal database)».

**Falsificazione rifatta, in ogni ramo con la mutazione «return perdita»** (prima i test di `salvaStop` erano 15/15 verdi sotto questa mutazione):
- **conto**, la mutazione esatta del coordinatore: 2 rossi in `salvaStop.test.ts`;
- **Safe**: 1 rosso;
- **Mike**: 1 rosso;
- **Omega**: 1 rosso.

Dopo ogni mutazione il file è stato ripristinato. Esiti dopo la correzione:
- `tsc`: 0 errori;
- file toccati: 25 file, 487 test verdi (`salvaStop` 16, `FasciaStop` 35);
- patch rigenerata, `git apply --check -R` passato.
