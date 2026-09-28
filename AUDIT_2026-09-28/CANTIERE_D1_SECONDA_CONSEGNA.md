# CANTIERE D1 — SECONDA CONSEGNA (29/09/2026): MIKE PAPER SULLA STRADA VERA

Si aggiunge alla prima consegna (`CANTIERE_D1_SAFE_MIKE_PARITA.md`, gia' fotografata dal
coordinatore), senza toccarla. Worktree `agent-ae168c1f19f739518`, lavoro NON committato.
Perimetro di questo giro (ristretto dal coordinatore): SOLO Mike (blocco 1) + punto 4a + banco
di Mike. Blocchi 2, 3 (parte Safe), 4b, 4c, 4d: a un altro delegato.

## 0. Esito
| # | Cosa | Esito |
|---|---|---|
| 1 | Mike PAPER sul runner (canale di comando), tipo d'ordine del live, esiti letti dal runner, niente bet delay doppio, fine di `_resting_filled` | **FATTO** |
| 1b | Banco: `certifica mike --trasporto canale` fa girare Mike in paper sul `MotoreOrdini` vero | **FATTO (cablato)**, replay NON lanciato da me |
| 4a | Mike non opera su prezzi non vivi, in paper E in live (anche la lay appoggiata) | **FATTO** |
| D | Divergenza documento/codice: PERSIST dell'ultimo ingresso | **RIPORTATA** (§5), non corretta |

Numeri: `pytest Betfair/mike/tests Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py`
→ **982 passati** (Mike 965, banco 17). Frontend: `vitest mike.test.ts
consapevolezzaOrdine.contratto.test.ts` 72 passati, `tsc -p tsconfig.app.json --noEmit` 0
errori. **24 mutazioni, tutte ROSSE** (una prima verde, test aggiunto), ripristino
byte-identico (SHA-256) ogni volta.

## 1. Cosa fa ora Mike in PAPER (il live NON cambia: REST `omega_market`)
- **Porta** `Betfair/mike/porta_ordini.py` (nuovo, stesso schema della porta di Omega): riusa
  `safe_strategy.porta_ordini.PortaCanale` (client, ack, eventi `order`, `da_seq`); la
  `VistaMike` adatta il comando costruito da `execution._place_via_canale`/`_annulla_via_canale`:
  attore e `strategy_ref` = `mike`, `origine.tabella` = `mike_trades`, annullo `mike-c<bet>`.
  **Tipo d'ordine = quello del live**: taker con il FOK che `execution` sceglie (FOK, oppure
  nessun FOK sotto il minimo di piazzamento, dove il motore fa il place-and-trim come
  `place_submin_live`); lay appoggiata SENZA FOK e `LAPSE` come `_piazza_resting_live` →
  `place_order_live(fill_or_kill=False)` (`omega_market.py:735`). Nessun interruttore: in
  paper Mike passa SEMPRE dal runner.
- **Taker** (`execute_place`): runner non raggiungibile → ordine NON eseguito PRIMA della
  riserva (nessuna riga, attivita' `skip paper_senza_runner`, non e' un rifiuto del mercato).
  Canale caduto fra controllo e invio di una CHIUSURA (unico ripiego di `execution`): la
  ladder passata e' a liquidita' ZERO, quindi il fill in casa non puo' nascere → dichiarato
  `paper_senza_runner`. Dopo l'invio si aspetta l'esito TERMINALE del runner fino a
  `min(15 s, bet_delay + 3 s)` (come il REST FOK del live, che risponde dopo il bet delay nello
  stesso giro) e lo si applica subito.
- **Esiti** `_segui_ordini_paper_su_runner` (prima di `_sorveglia_sospensione`, cioe' prima di
  ogni decisione): gamba ← riga ← runner. Abbinato (anche parziale) → `matched`/`avg_price` veri
  su gamba e colonne di consapevolezza, `bet_id` salvato; terminale con abbinato → `open`;
  terminale senza → `cancelled`, riga `error runner_<fase>` (taker: `_rifiutata` come il FOK
  ucciso in live); taker senza NESSUN evento oltre 60 s → non eseguito (mai inventato).
- **Lay appoggiata** `_piazza_resting_paper`: riserva prima dell'ordine, stesso freno
  anti-doppione e stesso freno unico del live (gia' presenti), ordine sul book del runner.
  `_resting_filled` (abbinata «in casa» se il best back scendeva sotto il prezzo) **tolta**.
- **Bet delay**: la differita paper (`place_deferred`, prima `service.py` ramo
  `mode == "paper" and delay > 0`) **tolta**: il bet delay lo applica il runner (difetto 12
  del catalogo). Le voci gia' differite in memoria si esauriscono nel ciclo esistente.
  `place_deferred` tolto dai kind scritti in `frontend/src/lib/mike.ts` (il suo `case` resta:
  le righe storiche si leggono).
- **Annulli paper** (`_mark_trade_cancelled`): una riga paper del runner si annulla SUL RUNNER
  con la stessa regola del live; senza `bet_id` ancora noto la gamba va in riconciliazione con
  `meta.annullo_richiesto` e l'annullo parte appena il runner dice il `bet_id`.
- **Riconciliazione paper** (`_reconcile_unknown`): una riga del runner non si chiude piu'
  «mai piazzata» per deduzione: la risolve il lettore degli esiti.
- **Riapertura dopo una sospensione**: se il runner ha ancora viva la lay, si ANNULLA sul runner
  (regola Betfair per gli eventi materiali) e si legge l'esito vero (abbinato nel frattempo =
  posizione; annullo non confermato = riconciliazione).
- **Uscite manuali/automatiche (vincolo del coordinatore)**: NESSUNA modifica a cio' che decide
  se un'uscita di Mike parte da sola o diventa proposta.
- **`execution.py` NON toccato.**

## 2. 4a — prezzi non vivi
`execute_place`: `if not feed_fresh` vale per paper E live (prima solo paper). Stessa regola
aggiunta alla lay appoggiata in `_run_event` (prima nessun controllo in nessun modo). Uso solo
il parametro `feed_fresh`/`snap.feed_fresh` che il servizio gia' riceve: le funzioni di
freschezza (`feed_fresh`, `order_fresh`, cantiere J) NON sono toccate.

## 3. Banco
- `Betfair/stream/backtest/trasporto.py`: attore `mike` registrato (`ATTORI`, `SPORT_ATTORE`,
  nessun interruttore), montaggio del client VERO `PortaCanaleMike` sul `WsBanco` e ripristino.
  `SENZA_CANALE` ora vuoto.
- `Betfair/mike/tools/replay_registrazioni.py`: `modo_del_banco()` → `paper` dentro
  `trasporto.contesto("mike","canale")`, altrimenti `live` (riferimento di sempre, invariato).
  Sul canale l'attesa in tempo vero dell'esito e' 0 (l'esito arriva col book successivo, come
  il banco dichiara gia' per Safe/Omega).
- Comando per il coordinatore: `python -m Betfair.stream.backtest.certifica mike <eventi>
  --trasporto canale` (e `--trasporto entrambi` per la parita' coda/canale). Il profilo
  `--scenari rapidi` NON e' cablato per Mike (`trasporto_rapido.py` conosce solo Omega/Safe).

## 4. Falsificazioni (script `AUDIT_2026-09-28/d1/falsifica.py`)
| id | mutazione | rossi |
|---|---|---|
| b1 | porta non passata a `execution.place` | 8 |
| b2 | parziale del runner ignorato | 5 |
| b3 | lay appoggiata con FOK | 2 |
| b4 | fill in casa al best (ladder del feed) | 2 |
| b5 | esito terminale non applicato | 5 |
| b6 | esito non letto nello stesso giro | 7 |
| c1 | feed stantio solo in paper (vecchio) | 1 |
| c2 | lay appoggiata su feed stantio | 2 |
| c3 | taker senza esito mai chiuso | 1 |
| c4 | annullo paper non sul runner | 3 |
| c5 | riconciliazione paper per deduzione | 1 |
| c6 | riapertura senza annullo sul runner | 1 |
| c7 | annullo richiesto mai eseguito | 1 |
| e1-e4 (porta) | strategy_ref sbagliato, lay con FOK, tabella d'origine, ref dell'annullo (**e4 prima VERDE**, test su `adatta_comando` aggiunto) | 14, 7, 1, 1 |

## 5. DIVERGENZA DOCUMENTO/CODICE (da portare all'utente, NON corretta)
- **Documento**: `Betfair/mike/COSTITUZIONE_MIKE.md:132-140` (§3 Fase 2): l'ultimo ingresso a
  KO−10' e' un BACK Under 3.5 «con persistenza PERSIST (resta valido in-play)», residuo non
  abbinato annullato 120 s dopo il KO; «Perche' PERSIST: il mercato sospende al calcio d'inizio
  e gli ordini LAPSE vengono cancellati». Parametri `last_entry_persist`,
  `cancel_unmatched_after_ko_s` (righe 366-368).
- **Codice**: il motore lo decide PERSIST (`engine.py:2846-2854`, `persistence="PERSIST"`) e
  prevede la grazia di 120 s (`engine.py:2587-2589`), ma `service.execute_place` non passa MAI
  la persistenza a chi esegue: in live `execution.place` → `omega_market.place_order_live`
  con `fill_or_kill=True` di default (taker FOK, `persistenceType` fisso `LAPSE`,
  `omega_market.py:735`). Il PERSIST non arriva mai a Betfair.
- **Da quando**: la decisione PERSIST c'e' dal primo commit di Mike `b3770d5` (11/09/2026); la
  Costituzione stessa la segna «Rinviato alla fase F6 (live): persistence PERSIST su
  place_order_live» (`COSTITUZIONE_MIKE.md:470`, e `:788`), mai fatta; il FOK di default del
  live e' di `place_order_live` (vedi `git log -S "fill_or_kill: bool = True"
  Betfair/omega/omega_market.py`).
- **Effetto pratico, esempio**: KO 20:00, alle 19:50 Mike decide l'ultimo ingresso BACK Under
  3.5 10 € @ 1,50. Sul book ci sono 6 € a 1,50. Con PERSIST (documento) si abbinano 6 €, i 4 €
  residui restano sul book, attraversano il calcio d'inizio e possono abbinarsi fino alle
  20:02. Col codice (FOK) l'ordine viene UCCISO subito per intero: nessuna posizione, niente
  Under portato in gioco; la grazia di 120 s non scatta mai perche' la gamba non resta viva.
  (Con liquidita' sufficiente i due comportamenti coincidono.) In paper, da oggi, resta
  identico al live di oggi (FOK sul runner).

## 6. File toccati in QUESTO giro
Nuovi: `Betfair/mike/porta_ordini.py`, `Betfair/mike/tests/runner_finto.py`,
`Betfair/mike/tests/test_mike_d1_paper_sul_runner_2026_09_29.py`,
`AUDIT_2026-09-28/CANTIERE_D1_SECONDA_CONSEGNA.md`.
Modificati: `Betfair/mike/service.py`, `Betfair/mike/tools/replay_registrazioni.py`,
`Betfair/stream/backtest/trasporto.py`, `Betfair/mike/tests/conftest.py` (runner finto per ogni
test), `Betfair/mike/tests/test_mike_service.py` (3 test riscritti + 1 nuovo parametrizzato),
`Betfair/mike/tests/test_mike_paper_fill_al_best_2026_09_26.py` (riscritto: fissava il fill in
casa), `Betfair/mike/tests/test_mike_legge_canale_2026_09_23.py` (un runner per corsa),
`Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py` (Mike ha la porta),
`frontend/src/lib/mike.ts` (una riga: kind `place_deferred`; `npm run build` da fare
all'integrazione). Creata nel worktree la junction `frontend/node_modules`.

## 7. Cosa NON ho fatto / NON ho potuto verificare
- **Replay del banco non lanciato** (regola del carico): la strada paper di Mike via canale non
  e' ancora passata dal `MotoreOrdini` vero su flumine. Da verificare: che i controlli di
  certificazione di Mike (famiglia K, `credenze_mike`) leggano gli ordini del motore (il banco
  li adotta in `MercatoFlumine.ordini` col ref di flumine `awlq...`, `trasporto._adotta`).
- Il runner finto dei test abbina i taker al prezzo chiesto (o a un prezzo fissato dal test) e
  le lay solo quando il test lo dice: coda, bet delay e parziali VERI li fa flumine.
- Se il runner si riavvia e perde la memoria, una lay appoggiata paper senza eventi resta
  `pending` (per il taker c'e' il termine di 60 s; per la lay no, come in live dove resta sul
  book). Da osservare dal vivo.
- Se flumine NON fa scadere la lay LAPSE alla sospensione in gioco, Mike paper la annulla alla
  riapertura (§1): comportamento del simulatore non misurato da me.
- Gate del runner: un mercato non seguito viene agganciato dal motore (`in_aggancio`,
  auto-follow); a tetto mercati pieno il runner rifiuta e l'ordine paper non parte (dichiarato).

## 8. Controlli dal vivo in PAPER (29/09)
| controllo | atteso | dove |
|---|---|---|
| ogni ordine paper di Mike | comando `/comando/mike` nel log del runner, ack accettato, eventi `order` | log runner; `mike_trades.meta.canale_ref`, `canale_fase` |
| ingresso taker | riga `open` con `bet_id` del runner e `size_matched`/`avg_price_matched` del runner | `mike_trades` |
| green-up appoggiato | riga `pending` con `canale_fase=accettato_betfair`, poi `abbinato_parziale`/`abbinato`; attivita' `fill_resting` con `note runner_paper:...` | `mike_trades`, `mike_activity` |
| nessun `place_deferred` nuovo | assente dal 29/09 | `mike_activity` |
| runner spento | attivita' `skip paper_senza_runner`, nessuna riga nuova | `mike_activity` |
| feed fermo | `no_fill reason=feed_stantio` con `mode`, nessun ordine (anche live) | `mike_activity` |
