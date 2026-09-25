# D3 + D7 (25/09) - Dry-run per tutti, schede al ms, esecuzione a mercato entro la banda

Delegato, worktree `agent-a858482ff6bdfa68f`, **rebased su `43e1468`** (>= `1ba167e`; partito da `2f04bc4`). Niente commit,
nessuna scrittura sul DB, nessun processo nuovo. Replay: vedi §5.
Patch: `AUDIT_2026-09-25/dryrun_esecuzione.patch` (file tracciati) + file nuovi in fondo.

Ordini dell'utente (testuali, 25/09):
- **D3** «dry run per tutti: decido io cosa attivare, se PAPER o LIVE».
- **D7** «I prezzi delle schede devono aggiornarsi anche se il mercato si sposta; quando clicco devo
  essere avvisato del prezzo reale di abbinamento e se l'ordine e' stato abbinato».

Strategie intoccate: soglie, bande, stake e criteri non cambiano. Cambiano solo il prezzo d'invio
(a mercato dentro la banda), il `dry_run` di nascita dello scalper automatico e le schede.

---

## 1. D3 - bot x «nasce in live senza gesto?»

| Bot | Prima | Dopo | Prova |
|---|---|---|---|
| **Scalper calcio (auto-mode)** | **SI'**: interruttore in LIVE, le partite del feed nascono con `dry_run=false`, cioe' ordini reali (`scalper_service.py:458` in `3084d3b`: `"dry_run": modalita != "live"`) | **NO**: nascono SEMPRE in `dry_run=true` (client simulato), anche in LIVE | `auto_mode.py:278` `DRY_RUN_ALLA_NASCITA = True`, `:281` `dry_run_alla_nascita`; `scalper_service.py:460`; attivita' `auto_armata` con `dry_run` e `stats.auto.nascono_in_dry_run` (`:515`) |
| Scalper: conflitto «paper e live mai insieme» | in LIVE una sessione in prova bloccava l'armamento | con l'interruttore in LIVE nessun conflitto (prova e soldi veri convivono per scelta dell'utente); con l'interruttore in PROVA una sessione in soldi veri blocca ancora | `auto_mode.py:298` |
| Scalper: come si toglie il dry-run | - | doppio gesto dalla scheda scalper della partita (`ScalperPanel`): FERMA la sessione automatica (non viene riarmata: «chiusa a mano», `auto_mode.motivo_esclusione`), poi ARMA senza «Solo ARMATO» con la conferma dei soldi veri (`ScalperPanel.tsx:141-155`). La sessione nasce `origine='manuale'` e l'auto-mode non la tocca | la sessione legge `dry_run` una volta sola all'armo (`scalper_session.py:644`): non si puo' togliere a caldo |
| 4 bot tennis | NO (gia' `442d21c`, dry-run di nascita in LIVE) | invariato | `AUDIT_2026-09-25/TENNIS_AUTO_MODE.md` §7 |
| **Omega** | nessuna partita nasce reale senza gesto: la modalita' e' PER BOT (`omega_control.mode`, `omega_service.py:1718`, `:2184`) e si mette in LIVE solo dalla UI con doppia conferma (`PannelloBot.tsx:22`, `:794`, `:830`); a ogni avvio nuovo dell'app torna `stopped/paper` (`avvio_app.py:151` `ferma_al_nuovo_avvio`, Guardia `omega_service.py:239`); in piu' il freno condiviso `LIVE_ORDER_MODE` (OFF/PAPER/LIVE dalla UI, fail-closed, `e41cf72`, `46e6667`) | invariato | - |
| **Mike** | come Omega: ogni partita seguita nasce con la modalita' del bot (`service.py:2772` `"mode": mode`), che diventa LIVE solo col gesto doppio in UI; avvio nuovo = paper (Guardia `service.py:66`) | invariato | Nota per l'utente: con Mike in LIVE **ogni partita nuova del feed** nasce live senza un secondo gesto per partita (il gesto e' quello sul bot). Non c'e' un dry-run per partita in Mike: introdurlo sarebbe una modifica della strategia/servizio, non fatta. |
| **Safe** | nessuna strategia va live senza scriverlo: `modalita_di_strategia` (`bot_service.py:453-480`) = servizio in LIVE **e** voce `strategy_modes.<strategia>='live'` scritta; assente/illeggibile = paper; le proposte dicono la modalita' e il servizio la riverifica all'approvazione (`_verifica_modalita_proposta`); avvio nuovo = tutte le voci a paper (`strategy_modes_a_paper`, `bot_service.py:8755`) | invariato | Come Mike: con `strategy_modes.X='live'` le operazioni AUTOMATICHE di X nascono live senza un gesto per partita (il gesto e' sulla strategia). |

**Strade live senza gesto trovate**: solo quella dello scalper, chiusa. Per Omega/Mike/Safe il gesto
esiste ma e' per bot/strategia, non per partita: e' una scelta da portare all'utente, non l'ho toccata.

---

## 2. D7 - scheda x (prezzo al ms prima del clic / esecuzione / messaggio dopo)

| Scheda (manda ordini) | Prezzo PRIMA del clic | Esecuzione al clic | Messaggio DOPO (B17) |
|---|---|---|---|
| **Safe opportunita' a una gamba** (modello, tennis, anomalia) `SchedaPropostaOpportunita.tsx` | al ms (`usePrezzoAlMs`, gia' dal 24/09). **Nuovo**: riga «al clic: a mercato, al miglior prezzo di quel momento (ora X), solo dentro la banda Y-Z della strategia» (`cr-opp-esecuzione`, `:493`) e, fuori banda, l'avviso «prezzo attuale X fuori dalla banda Y-Z della strategia: al clic l'ordine non parte» ricalcolato al tick (`:262-287`). PIAZZA resta acceso (decide il servizio al prezzo dell'istante). | **Prima**: al prezzo VISTO, rifiuto se il mercato era a >2 % dal visto. **Dopo**: al MIGLIOR prezzo di adesso (`prices[side]` del servizio, feed fresco o REST) se dentro la banda; fuori banda `fuori_banda_strategia` col messaggio; senza prezzo `prezzo_attuale_assente` (`bot_service.py:2682-2725`). FOK in live come prima (`_execute`). Sulla riga `meta.esecuzione_al_clic = {regola, banda, prezzo_attuale, prezzo_visto}` e nell'attivita' `opportunita_piazzata`. | striscia B17 montata (`OpportunitaColonna.tsx:80`); il rifiuto arriva come «rifiutato: prezzo attuale 1.01 (back) fuori dalla banda 1.05-1000 della strategia» (`result.message`) |
| **Safe combo** | prezzi delle gambe dal feed dello scanner (`prezziViviGambe`), NON ladder al ms (invariato) | invariato: prezzo visto per gamba + tolleranza `slippage_pct` (default 2 %); la scheda lo dichiara («nessuna banda per gamba») | striscia B17 |
| **Safe proposta senza `criteri`** (nata prima del 24/09) | al ms | invariato (prezzo visto + tolleranza), **dichiarato**: `meta.esecuzione_al_clic.regola = "prezzo_visto_senza_banda"` e testo in scheda | striscia B17 |
| **Safe uscita / proposta di chiusura** `SchedaChiusura.tsx` | al ms (dal 24/09, `:108`) | gia' A MERCATO (D5): `_request_cashout` -> `execution.close_trade` coi prezzi di adesso, `exit_kind="manual"` -> 0 tick (`execution.py:1422-1427`, `:1552`). Non toccato. | striscia B17 in «Uscite» (`UsciteColonna.tsx:79-82`) |
| **Omega uscita** `SchedaChiusuraOmega.tsx` | al ms (dal 24/09, `:80`) | gia' A MERCATO: `_manual_cashout` -> `_cashout_prices` (feed fresco, poi REST, mai mercato sospeso) -> `close_trade`, 0 tick (`omega_service.py:5457`, `:5274`). Non toccato. | striscia B17 in «Uscite» |
| **Mike proposta d'uscita** `PropostaUscitaMike.tsx` | **Prima: NON al ms** (book di `mike_events.live`, 1 s). **Dopo: al ms** per OGNI ordine proposto: gli id veri si leggono dalla stessa riga della partita (`markets[mercato].market_id`, `ctx.selections["OU35\|UNDER"]`, scritti dal servizio dal feed: `service.py:2769`) con `idsOrdineMike` (`:79`); ripiego dichiarato sul feed della partita («feed della partita» vs «al ms» nella riga). Al clic il contesto porta il prezzo AL MS, `fonte: "ladder al ms (canale\|db)"`, `market_id`, `selection_id`. | gia' A MERCATO: la firma passa la decisione della strategia al giro dopo coi prezzi del momento (`service.py:2431` `_request_approva_uscita`, `engine.gate_uscite`). Non toccato; la scheda lo dice (`cr-mike-proposta-esecuzione`). | striscia B17 (gia' montata, `:157`) |
| **«Chiudi» di riga** (tutti i bot, tennis compresi) `BottoneChiudiRiga.tsx` | il prezzo «se chiudo ora» della riga (canale del bot o DB), non il ladder: invariato | a mercato con la macchina d'uscita di ciascun bot (Safe/Omega `close_trade` 0 tick, Mike flatten del motore, tennis macchina del bot `512440f`) | messaggio d'ordine B17 accanto al bottone (`:104-108`) |
| Cash out globale di partita (Safe) `CashOutPartita.tsx` | - | a mercato (`_request_cashout_event`) | **solo stato della richiesta** (`StrisciaEsitoChiusura`), NON il messaggio d'abbinamento per ordine: reperto, non fatto (vedi §6) |

## 3. Bande usate per operazione (fonte nei params)

| Operazione | Banda | Fonte |
|---|---|---|
| Apertura Safe da proposta modello calcio / tennis / anomalia | tick della scala Betfair dove i criteri DI PREZZO di `valuta_al_prezzo` reggono con la `p_model` della proposta: `min_back_price`, `max_lay_price`, `min_edge` (motore), `opps_min_edge` (servizio), EV > 0 con `commission`, `max_liability_per_trade` con lo `stake` | `payload.criteri` = `PO.criteri_proposta(motore.params EFFETTIVI, params del servizio)` scritti alla nascita (`bot_service._proponi_opps`, 24/09); `proposte_opportunita.banda_della_strategia` (`:707`), `in_banda` (`:697`), `CODICI_DI_PREZZO` (`:668`) |
| Esclusi dalla banda (non sono un prezzo) | `min_size` (lo fa il FOK), `min_prob_back`/`max_prob_lay`, causa «modello» | decide l'utente come dal 24/09 |
| Combo | nessuna banda per gamba nei criteri: prezzo visto + `slippage_pct` (payload, default `SLIPPAGE_PCT_DEFAULT` 2 %) | invariato, dichiarato |
| Proposta senza `criteri`/`p_model` | nessuna banda: prezzo visto + tolleranza | invariato, dichiarato su riga e scheda |
| Uscite/chiusure Safe, Omega | nessuna banda: a mercato, 0 tick (1 tick per `loss/mandatory/red_card`) | `execution.ticks_for_exit` (`execution.py:1425`) |
| Uscite Mike | la decisione della strategia coi prezzi del momento | `engine.gate_uscite` |

Esempi (file d'oro `frontend/src/lib/bandaStrategia.golden.json`): tennis back p=0,99 -> 1.05-1000;
tennis back p=0,77 -> 1.36-1000; tennis lay p=0,01 (tetto 20 EUR, stake 5) -> 1.01-5; modello back
p=0,5 -> 2.14-1000; anomalia back p=0,7 -> 1.46-1000; anomalia lay p=0,2 -> 1.01-4.7.

La stessa funzione esiste in TypeScript (`valutaProposta.ts` `bandaDellaStrategia`/`inBanda`/
`testoBanda`), legata al Python dal file d'oro (generatore
`Betfair/safe_strategy/tools/genera_oro_banda_strategia.py`).

## 4. Test

**pytest** (sandbox `SUPABASE_URL=http://127.0.0.1:9`):
- nuovo `Betfair/safe_strategy/tests/test_esecuzione_a_mercato_d7_2026_09_25.py`: 28 verdi (parita'
  banda = `valuta_al_prezzo` su tutta la scala, banda assente senza criteri/P, banda vuota, testo,
  file d'oro, back/lay a mercato in banda, fuori banda, senza prezzo, senza prezzo visto, senza
  criteri = regola del 18/09 dichiarata, «Investi» manuale invariato).
- Safe toccati e vicini (audit_09_11, b25, bot_service, combos_anomalie, modalita_model_manual,
  prezzo_segnale_b17, proposte_opportunita, stato_mercato, scheda_al_ms, contratto barriera):
  **401 verdi**.
- scalper `test_scalper_auto_mode_2026_09_25.py` + `test_scalper_control_room_2026_09_24.py`: **77 verdi**.
- **Test riscritti sul contratto nuovo** (ognuno lo dice nel docstring, «D7 (25/09)» / «D3 (25/09)»):
  `test_scheda_al_ms` (6 casi: ordine a mercato e non al visto; rifiuto solo fuori banda; codice
  `prezzo_attuale_assente`; proposta non valida per il MODELLO si approva, per il PREZZO fuori banda
  no), `test_combos_anomalie` (4: anomalia a mercato, lay con p_model coerente), `test_prezzo_segnale_b17`
  (1), `test_proposte_opportunita` (2: il finto di `prices_for` ora ha `back`/`lay`, chiavi del vero;
  prezzo 1,40 perche' il finto `_opp` dichiara edge 0,2 ma coi suoi numeri a 1,30 l'edge e' 0,0008),
  `test_scalper_auto_mode` (`test_live_nasce_live` -> `test_live_nasce_in_dry_run`, conflitto in live).

**vitest** (file toccati e vicini, 16 file): **294 verdi** (prima dei 2 casi d'oro aggiunti; i file
banda/scheda/Mike/scalper riverificati verdi nel controllo della falsificazione). Nuovi:
`valutaProposta.banda.test.ts` (20, su 18 casi d'oro), `SchedaPropostaOpportunita.banda.test.tsx` (4), 4 casi D7 in `PropostaUscitaMike.test.tsx`.
**tsc** `npx tsc -p tsconfig.app.json --noEmit`: **0 errori**.

**Falsificazione**: `AUDIT_2026-09-25/mutazioni_dryrun_esecuzione.py`, log
`falsificazione_dryrun_esecuzione.txt`: controllo senza mutazioni VERDE (7 comandi), poi
**21/21 mutazioni ROSSE** (13 Python, 8 TS), md5 ripristinato su tutte. Al primo giro PY7 («la banda
ignora l'edge minimo») era VERDE: nei casi di prova l'edge del motore non era mai il vincolo che
morde; aggiunti al file d'oro due casi in cui lo e' («edge del motore stringente» back/lay), ora ROSSA.

## 5. SEGUITO del coordinatore (25/09 sera): PM3, mutazioni scalper, rebase, replay

**Rebased su `43e1468`** (origin/master, gia' oltre `1ba167e`): nessun mio file toccato da master
(`opportunity.py`, `mike/service.py`, `mike/dossier.py`, atlante: solo loro, conservati). Metodo:
`git reset --keep origin/master` (nessun commit mio; le mie modifiche restano nel working tree, verificate
identiche all'istantanea presa prima: diff vuoto sui miei file). Dopo il rebase: pytest file toccati
**549 verdi**, vitest 16 file **302 verdi**, tsc **0 errori**.

**Correzione trovata strada facendo**: la chiave `meta.esecuzione` e' GIA' dell'esecuzione (t4/t5,
`price_richiesto`, letta da `_prezzo_chiesto` del banco) e al fill `_execute` la RISCRIVE
(`bot_service.py` ~5469). La mia regola di esecuzione ora sta in **`meta.esecuzione_al_clic`** (riga,
attivita' `opportunita_piazzata`, risultato). Test e mutazioni aggiornati.

**(1) PM3 riscritto** (`Betfair/stream/backtest/proposte_modello.py`, regola in `REGOLE` e
`_banda`/`_pm3_banda`): per le proposte con banda (`banda_della_strategia` non None: criteri + p_model,
non combo) PM3 rilegge il MERCATO dal feed (`prezzo_in_riga`, non dalla riga del servizio) e viola se:
ordine nato col mercato fuori banda; rifiuto `fuori_banda_strategia` col mercato in banda; riga senza
`esecuzione_al_clic.regola = a_mercato_entro_banda`; prezzo chiesto (`_prezzo_chiesto`, ordine vero su
flumine) diverso da `esecuzione_al_clic.prezzo_attuale`; chiesto fuori banda. Senza banda (e combo):
il PM3 di prima, invariato. Test nuovi in `Betfair/stream/tests/test_proposte_modello_2026_09_23.py`
(banda del caso 3.15-1000; 6 casi parametrizzati; rifiuto fuori banda solo a mercato fuori banda;
rifiuto di tolleranza in banda non piu' giudicato): 44 verdi. **Rosso -> verde**: col PM3 di prima
(mutazione PM3b) il caso «+8,6 % dal visto ma in banda» e' una violazione SPURIA -> test ROSSO.
Falsificazione PM3 (`mutazioni_dryrun_esecuzione.py`, PM3a-e): **5/5 ROSSE**. PM3a («accetta un
ordine fuori banda») al primo giro era VERDE (il caso di prova aveva anche il chiesto fuori banda,
preso da un altro controllo): aggiunto il caso feed 3,1 / riga dichiarata 3,5, ora ROSSA (log in coda
a `falsificazione_dryrun_esecuzione.txt`). Totale del file: **26/26 ROSSE** (21 di prima + 5 PM3).

**(2) `mutazioni_scalper_auto_mode.py` aggiornato** al contratto «live nasce in dry-run» (via «live
nasce paper / paper nasce live»; dentro «live nasce con soldi veri (contratto di ieri)», «tutto nasce
con soldi veri», «dry-run di nascita spento», «in live il dry-run blocca l'armamento»). Rilanciato:
**50/50 ROSSE** (`falsificazione_scalper_auto_mode_d3.txt`).

**(4) Replay** Safe, scenario `proposta-approvata` (lo scenario delle proposte di modello approvate,
dove vive PM3), `--worker 1`, `--data-dir <repo>/_live_raw`, bot `safe_base`:
- tutte le 40 registrazioni: **fermato a 10 minuti** come da ordine (601 s, `timeout` exit 124).
  In 10 minuti 4 partite su 40, tutte **OK, 0 violazioni** (35674515, 35759636, 35760084, 35764745;
  `replay_safe_proposta_approvata_d7.txt`, parziale). Il giro intero vuole ~2,5 min a partita, ~100 min.
- una partita intera, 35759636 (quella con un rifiuto `fuori_banda_strategia` fra gli esiti): **76 s**,
  `ESITO: 1 partite senza violazioni, 0 violazioni totali`, **PM3 x3 sollecitato, 0 violazioni**
  (`replay_safe_proposta_approvata_d7_35759636.txt`). Esiti delle approvazioni: 1 ok, 1
  `fuori_banda_strategia`, 1 `non_eseguito` (FOK).
- Non lanciati: gli altri scenari Safe e il giro completo delle 40 partite.

Scalper: `certifica scalper_calcio` non cambia (il supervisore non e' nel banco).

## 6. Non fatto / non verificato

- Replay solo parziale (§5), nessuna suite intera, nessuna prova nell'app, `npm run build` non eseguito.
- **Cash out globale di partita** (`CashOutPartita`): manda ordini ma mostra solo lo stato della
  richiesta, non il prezzo d'abbinamento per ordine (servirebbe seguire N chiusure con `useSeguiOrdini`,
  che oggi segue una posizione per clic).
- **«Chiudi» di riga e gambe della combo**: prima del clic il prezzo e' quello della riga / del feed
  dello scanner, non il ladder al ms.
- **Mike**: gli id veri non sono scritti SULLA proposta (`engine.gate_uscite` e' la strategia): la
  scheda li prende dalla riga della partita, che il servizio scrive dallo stesso feed. Se la proposta
  un giorno li portera', `idsOrdineMike` li preferisce. Le gambe di Mike restano per correlazione
  (B17 §6.2).
- A mercato = il MIGLIOR prezzo come ordine limite FOK: se al miglior prezzo non c'e' tutta la size,
  in live il FOK muore (messaggio «NON abbinato (FOK)»). Non ho scelto di mandare il limite al bordo
  della banda (spazzerebbe piu' livelli): e' una decisione dell'utente.
- `clic_troppo_vecchio` (20 s) resta quando la scheda manda l'istante del clic.
- Il miglior prezzo e' quello che il SERVIZIO vede all'esecuzione (`prices_for`: feed fresco, poi
  REST), non il ladder al ms della pagina.
- Scalper: togliere il dry-run e' un gesto dalla scheda della partita (/segui-live), non dalla Control
  Room; la riga «Scalper» mostrera' «misto» (prova + soldi veri) quando convivono.
- Omega/Mike/Safe: in LIVE le partite nuove nascono live col solo gesto sul bot/strategia (§1).

## File

Modificati: `Betfair/safe_strategy/bot_service.py`, `Betfair/safe_strategy/proposte_opportunita.py`,
`Betfair/stream/scalper/auto_mode.py`, `Betfair/stream/scalper/scalper_service.py`,
`frontend/src/components/controlroom/PropostaUscitaMike.tsx`,
`frontend/src/components/controlroom/SchedaPropostaOpportunita.tsx`, `frontend/src/lib/valutaProposta.ts`,
`frontend/src/lib/scalperControlRoom.ts`; test: `test_scheda_al_ms_2026_09_24.py`,
`test_combos_anomalie_proposte_2026_09_18.py`, `test_prezzo_segnale_b17_2026_09_25.py`,
`test_proposte_opportunita_2026_09_17.py`, `test_scalper_auto_mode_2026_09_25.py`,
`PropostaUscitaMike.test.tsx`, `scalperAuto.test.ts`.

Nuovi: `Betfair/safe_strategy/tests/test_esecuzione_a_mercato_d7_2026_09_25.py`,
`Betfair/safe_strategy/tools/genera_oro_banda_strategia.py`, `frontend/src/lib/bandaStrategia.golden.json`,
`frontend/src/lib/valutaProposta.banda.test.ts`,
`frontend/src/components/controlroom/SchedaPropostaOpportunita.banda.test.tsx`,
`AUDIT_2026-09-25/mutazioni_dryrun_esecuzione.py`, `falsificazione_dryrun_esecuzione.txt`, questo file,
`dryrun_esecuzione.patch`.

Junction `frontend/node_modules` creata nel worktree: toglierla con `cmd /c rmdir`, mai `--force`.
