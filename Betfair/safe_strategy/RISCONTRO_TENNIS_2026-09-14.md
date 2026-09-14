# RISCONTRO TENNIS — la variante contro `SPEC_STRATEGIA_S.md` §3

> Punto 4 del goal dell'utente: *«il bot deve rispettare ogni cosa per cui è stato
> progettato e seguire la strategia alla lettera»*. Questa è la prova scritta.
> Al commit del 14/09/2026. Stessa scala a quattro verdetti del riscontro calcio:
> **✓ conforme** · **⊗ da fare** (manca il codice) · **⊘ non esercitabile** (manca un
> dato di terzi, con la causa per nome) · **▣ eccezione decisa dall'utente**.

## Ingresso — tabella §3 della specifica

| voce della specifica | valore nella specifica | nel codice | valore nel codice | test | verdetto |
|---|---|---|---|---|---|
| Operazione | **punti (back)** chi sta vincendo *oppure* banchi chi perde — «equivalenti, si sceglie il più comodo» | `engine.py:1101` `evaluate_tennis` → `side="BACK"`, `entry_odds = lead_back` | **BACK sul leader** | `test_engine.py` (blocco tennis) · `safeStrategy.test.ts` | ✓ — il manuale lascia la scelta, il codice ne implementa una sola ed è quella dichiarata |
| Momento ideale | **1° set vinto + 2-3 game di vantaggio nel 2°** | `engine.py:220` `setsLeadMin: 1` · `engine.py:221` `gamesLeadMin: 2` | 1 set · 2 game | `test_cert_2026_09_13.py` §tennis | ✓ |
| «il vantaggio di UN set viene dall'UNICO set giocato» | implicito nel «1° set» | `engine.py:233` `setsPlayedMax: 1`, check `setsPlayed` | max 1 set giocato | `test_cert_2026_09_13.py::test_un_solo_set_giocato` | ✓ — in bo3 è automatico; in bo5 un 2-1 passava come «un set avanti» pur avendone già perso uno |
| Quota punta (back) | **≈1.03** | `engine.py:222-223` `backMin 1.01` · `backMax 1.10` | banda 1.01–1.10 | `test_engine.py` (fixture a 1.05) | ✓ — il manuale dà un ordine di grandezza, non una banda: 1.01–1.10 la contiene |
| Quota banca (lay) | 1.18–1.34 | — | **non implementata**: il bot non banca, punta | — | ▣ non pertinente: il manuale dichiara le due vie equivalenti e il codice usa il back |
| Capitale iniziale ≈200 € | descrittivo | — | stake fisso per lato (`stake.backSize`) | — | ▣ eccezione decisa (stake fisso, 13-14/09) |
| Da evitare: **doppi** | esclusione | `engine.py:224` `excludeDoubles: True`, check `singles` | attivo di default | `test_cert_2026_09_13.py` | ✓ |
| Da evitare: **Slam maschili (5 set)** | esclusione (dalla sezione «Ritiri») | `engine.py:228` `excludeBestOf5: True` + `detect_best_of` `engine.py:679` | attivo; il tabellone femminile dello stesso Slam resta ammesso | `test_cert_2026_09_13.py::test_esclusione_slam_maschili` | ✓ |
| Da evitare: **finali** | esclusione | nessun codice | — | — | **⊘ NON ESERCITABILE** — causa: **Betfair non pubblica il turno per il tennis**. Verificato su **399 mercati** in 3 giorni: zero con `final/semi/quarter/round/R16/QF/SF` nel nome evento o mercato; `event` ha solo `id, name, openDate, timezone`; i tipi di mercato sono solo `Match Odds` e `Set Betting`. Resta una via euristica (finale = ultima partita rimasta della competizione) che però scambierebbe i quarti per finali quando i turni successivi non sono ancora pubblicati → **decisione dell'utente** |
| Da evitare: **match troppo equilibrati** | esclusione | `engine.py:222-223` banda quota + `setsLeadMin`/`gamesLeadMin` | un match equilibrato non produce un leader a 1.01–1.10 con un set e due game di vantaggio | — | ✓ per costruzione (la banda quota *è* il filtro dell'equilibrio) |
| Da evitare: **sfavoriti estremi** | esclusione | `engine.py:222` `backMin: 1.01` | sotto 1.01 non esistono quote | — | ✓ per costruzione |
| Filtro per nome torneo | non nella specifica | `engine.py` `excludeCompetitions` | **vuoto** di default | — | ✓ — è una lista che compila l'utente, non un default inventato |
| Anti-blip punteggio | non nella specifica | `engine.py:237` `scoreConfirmSec: 15` | 15 s | `test_engine.py` | aggiunta prudenziale (restringe) |

## Uscite — `_decide_tennis` (`exits.py:990-1015`)

| voce della specifica | valore | nel codice | verdetto |
|---|---|---|---|
| **Profitto** — chi vince prende anche il **game successivo** → cashout | uscita al game vinto | `exits.py:1005` `last == "won"` → `ExitDecision("profit", "leader_vince_il_game")`, interruttore `tennis_take_profit_next_game` (default acceso, `exits.py:31`) | ✓ |
| **Profitto** — «per il massimo profitto si aspetta la fine del match» | alternativa dichiarata dal manuale | l'interruttore sopra spento = si porta a termine | ✓ (entrambe le vie del manuale sono rappresentate) |
| **Perdita** — chi vince perde il game successivo → uscita conservativa | uscita al game perso | `exits.py:1013` `last == "lost"` + `tennis_exit_on_lost_game`, **default SPENTO** (`exits.py:32`) | ▣ il manuale la dà come facoltativa («uscita conservativa»); il default spento è la via del massimo profitto, anch'essa del manuale |
| **Perdita** — due game di fila **e** pareggio nel set → uscita **OBBLIGATORIA, senza eccezioni** | tassativa | `exits.py:1002` `consecutive >= 2 and set_lead_lost` → `ExitDecision("mandatory", ...)`. Le due condizioni restano in **AND**, come il manuale | ✓ |
| …e non passa da nessun filtro | «senza eccezioni» | `mandatory` ∉ `PROFIT_KINDS` (`exits.py:128`): **la decisione a modello non la vede**. Ed è urgente nel backoff (`bot_service` `URGENT_EXIT_KINDS`) | ✓ |
| Perdite dal **5 %** al **25 %** del capitale | descrittivo | nessun controllo sull'entità | ▣ conseguenza dello stake fisso: la percentuale non è comparabile fra due trade a quote diverse. **Osservata sul campo 14/09: −10,5 % dello stake** su un'uscita obbligatoria, dentro la banda |
| **Ritiro = perdita totale dello stake** | rischio dichiarato | nessuna copertura possibile | ⊘ è il rischio della strategia, non un difetto: il manuale lo dichiara irriducibile. Le tre esclusioni (doppi, 5 set, un set giocato) **sono** la mitigazione |

## Aggiunte del codice non richieste dalla specifica

Tutte **restringono**, nessuna allarga:

| cosa | dove | perché |
|---|---|---|
| take profit solo **sopra 1.03** | `exits.py:91` `tennis_take_profit_min_odds` + `exits.py:1008-1011` | sotto quella quota il guadagno massimo è più piccolo dello spread da attraversare: chiudere è una perdita **garantita**. Misurato su 29 uscite reali il 13/09: 17 su 17 a 1.01–1.02 sarebbero state migliori tenute |
| take profit solo se **blocca un profitto vero** | `exits.py:97` `tennis_take_profit_min_eur` | la decisione a modello confronta valori attesi e poteva accettare un bloccato **negativo**: un «take profit» che incassa una perdita non è un take profit |
| vantaggio nel set **perso**, non solo parità | `exits.py:858` `set_lead_lost` | da 5-4 a 5-6 senza passare dal 5-5 il vantaggio non c'è comunque più. La prima versione usava «parità o peggio» e sarebbe uscita d'obbligo a 0-2 di inizio set, dove il manuale non chiede niente |

## Osservazione sul campo — 14/09, paper

Sei partite, otto operazioni, **−0,05 €**. Le tre regole che contano si sono viste funzionare:

| caso | esito |
|---|---|
| tre ingressi a **1,01–1,02** | **portati a fine partita** (+0,04 · +0,02 · +0,04): il take profit non è scattato, come deve |
| un ingresso a **1,06** | take profit a 1,03 con **profitto vero**: +0,12 apertura, −0,06 chiusura, **netto +0,06** |
| un ingresso a **1,02** | **uscita obbligatoria** a 1,14: netto **−0,21 = −10,5 %** dello stake, dentro la banda 5–25 % |

Sei partite non dicono niente sulla **redditività**. Dicono tutto sul **comportamento**, che è la metrica stabilita quando l'utente ha confermato lo stake fisso.

## Cosa resta aperto

| | cosa | chi lo chiude |
|---|---|---|
| **⊘** | **finali non escluse** — Betfair non pubblica il turno | decisione dell'utente sull'euristica |
| — | osservazione in **LIVE** | si riempie solo operando con soldi veri |
