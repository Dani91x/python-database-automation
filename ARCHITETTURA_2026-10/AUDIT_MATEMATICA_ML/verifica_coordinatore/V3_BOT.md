# V3 - Verifica indipendente dei reperti M11, M22, M20, M21 (bot e soldi)

Verificatore indipendente, 09/10/2026 ore 13:11 (orologio). Sola lettura sul master `852b717f`.
Nessun file del repo modificato oltre a questo referto; due SELECT leggere sul DB
(`betfair_live_settings`, `betfair_live_settled` LIMIT 400, `omega_control`, `mike_control`);
script di sonda nello scratchpad della sessione, non nel repo. Nessun replay lanciato, nessun processo avviato.

## Sintesi

| Reperto | Verdetto | In una riga |
|---|---|---|
| M11 dutching variable | **CONFERMATO** (strumento manuale, non bot) | anteprima e server calcolano due ripartizioni diverse; numeri dell'audit riprodotti al centesimo |
| M22 stop giornaliero | **RIDIMENSIONATO** (lordo: vero ma oggi spento; perimetro: scelta documentata) | lo stop di conto E34 è SPENTO (`daily_loss_limit = NULL`); gli stop propri dei bot sono NETTI |
| M20 Mike combine_hazard | **SCELTA DOCUMENTATA** | la regola «max, fonte più prudente, pressione fino a ×1,25» è scritta in COSTITUZIONE_MIKE; un numero dell'audit è sbagliato |
| M21 Omega tabella per minuto | **RIDIMENSIONATO** | il meccanismo è vero, ma ×1,57 a 89' sta fuori dalla finestra d'ingresso (V3 entra fino all'85'); nella finestra il massimo è circa ×1,3 a 84', solo in direzione prudente |

---

## M11 - Dutching «variable»: anteprima UI diversa dagli ordini piazzati

**(1) Codice e percorso VIVO**
- Anteprima: `frontend/src/components/live/DutchingPanel.tsx:194-209`: `w = (1/quota)·peso`, `stake_i = T·w_i/Σw`
  (lo stake è proporzionale a peso/quota).
- Invio: `DutchingPanel.tsx:270-286` manda `dutchMode: 'variable'`, `totalStake` e il `weight` di ogni gamba. NON manda gli stake.
- Server: `Betfair/stream/live_order_worker.py:2914-2919` (`_do_dutch`, modo `variable`) chiama
  `Betfair/stream/trading/dutching.py:184-244` (`dutch_variable`): impone **profitto ∝ peso**,
  `k = T(1−Σ1/p)/Σ(w/p)`, `s_i = (T + k·w_i)/p_i`.
- Il pannello è montato in `frontend/src/pages/SeguiLive.tsx:817` (strumento «dutching»), in modalità paper e live.
  È uno strumento MANUALE: nessun bot (Omega, Mike, Safe, tennis) lo usa.

**(2) Esempio rifatto (a mano e con la funzione vera)**
Quote 2,5/3,0/4,0, pesi 1/2/1, T = 100. Σ(1/p) = 0,98333; Σ(w/p) = 0,4+0,6667+0,25 = 1,31667.
- Server: k = 100·0,016667/1,31667 = 1,266 → stake 40,51/34,18/25,32, profitti +1,26/+2,53/+1,27
  (risultato identico da `dutch_variable` eseguita).
- Anteprima: stake 100·(0,4; 0,6667; 0,25)/1,31667 = 30,38/50,63/18,99, profitti −24,05/+51,89/−24,04.
- Secondo esempio mio: quote 2,0/5,0, pesi 1/3, T = 50. Il server piazza 27,78/22,22 (profitti +5,56/+16,66).
  L'anteprima mostra 22,73/27,27 (profitti −4,55/+86,36).

**(3) Scelta documentata?** No. In CRONOSTORIA il dutching compare solo per il reperto
«variable + LAY piazza BACK» (checkpoint 12:56 del 09/10) e per il dutch di Safe. Nessun
documento definisce che cosa significhi il «peso» (moltiplicatore dello stake per la UI, rapporto di profitto per il server).
Il test `Betfair/stream/tests/test_dutching.py:65` copre solo il server.

**Impatto in euro.** Con book < 100% il server dà sempre profitti tutti positivi, quindi in
questi esempi il reale è MENO rischioso del mostrato. Però l'utente conferma (anche in LIVE)
stake e profitti falsi: fino a 16,45 € di scarto per gamba su T = 100 e un +86 € mostrato
contro +16,66 € reale nel secondo esempio. È una decisione presa su numeri sbagliati. Le perdite
aggiunte sono 0 in questi casi, ma in generale non si possono escludere.
**Osservazione (NON verificata, fuori perimetro)**: con pesi irrealizzabili il server
risponde `ok=True` con una nota e senza ordini (`live_order_worker.py:2932-2937`). Il pannello
potrebbe mostrare «Dutching inviato» anche se non è stato piazzato nulla: va controllato sul `res.status`.

**Verdetto: CONFERMATO.**

---

## M22 - Stop giornaliero lordo di commissione e perimetro asimmetrico

**(1) Codice e percorso VIVO**
- Matematica: `Betfair/stream/trading/daily_pnl.py:49-56` (somma dei `profit`), `:105-127`
  (scatta se realized + MTM ≤ −limite).
- Worker: `Betfair/stream/daily_stop_worker.py`, registrato SOLO nel runner calcio
  (`Betfair/stream/runner.py:2988-2994`) con `strategy=live_strategy`.
- Realized LIVE: lo scrive `Betfair/stream/reconcile_worker.py:550-557` con il `profit`
  per MERCATO di `listClearedOrders`. Lo stesso file (`:573-582`) dichiara che quel `profit` è
  LORDO e che il netto è `profit − commission`.
- Realized PAPER: `order.simulated.profit` (flumine 2.13.11, `simulation/simulatedorder.py:564-`):
  `size·(prezzo−1)`, senza commissione.
- Quindi il realized dello stop di conto è **lordo**: confermato.
- Effetto dello scatto: `set_live_kill_switch(true)` (`daily_stop_worker.py:357-410`). Il
  kill-switch condiviso lo leggono Mike (`mike/service.py:2079-2087`), Omega
  (`omega/omega_service.py:2200-2211`), Safe (`safe_strategy/execution.py:144-181`), tennis
  (`stream/tennis_live/guardie_tennis.py:279-282`) e il motore ordini (`motore_ordini.py:1111, 2036`).
- MTM: solo gli ordini di `live_strategy` nel blotter del runner calcio (`daily_stop_worker.py:262-300`).
  Omega e Safe calcio piazzano dal canale (`.env`: `OMEGA_ORDINI_VIA_CANALE=1`,
  `SAFE_ORDINI_VIA_CANALE=1`), che passa da `_dispatch` con la strategia del runner, quindi
  le loro posizioni aperte SONO nel MTM. Restano fuori il tennis (runner separato, Safe tennis
  su strada diretta, `SAFE_TENNIS_ORDINI_VIA_CANALE=0`) e le posizioni aperte a mano sul sito.

**(4) P&L e commissione che usano davvero lo stop e i bot**
| Freno | P&L usato | Commissione |
|---|---|---|
| Stop di conto E34 (`daily_stop_worker`) | realized di conto (cleared LIVE / simulato PAPER) + MTM `live_strategy` | **LORDO** |
| Mike `daily_loss_stop` (50 € in `mike_control`) | `realized_today` + bloccato (`mike/service.py:4428-4449`, `mike/db.py:340-381`) | **NETTO** (`mike/db.py:308`: «pnl di ogni riga e' NETTO commissione») |
| Omega `v3_daily_loss_cap` (300 € di serie, non sovrascritto in `omega_control`) | `realized_effective` = R + perdite bloccate (`omega_service.py:1625-1630, 1895-1912`) | **NETTO** (`omega_engine.net_profit_if_win`, controllo F1 della certificazione) |
| Safe | ledger con commissione fissata sul trade (`safe_strategy/execution.py:1979-2037`) | **NETTO** |
| Tennis | commissione per ordine «come Betfair» (`tennis_live_order_worker.py:1256-`) | **NETTO** |

**(2) Esempio rifatto.** Il limite è 50 €. In giornata i mercati vinti fanno +200 lordi (commissione 5% = 10 €) e quelli persi −250.
Il realized lordo è −50 e lo stop scatta, ma il netto vero è già −60. Lo stop scatta quindi tardi di
Σ(commissione dei mercati vinti). Il conto torna: il numero dell'audit (circa 10 € su +200) è giusto.

**Misura dal DB (SELECT, mode=live)**: `betfair_live_settings.daily_loss_limit = NULL`, cioè
**stop E34 SPENTO** (`daily_pnl.py:113-114` → `limit_off`). Le giornate live registrate:
04/10 vincite lorde 9,89 € → 0,49 € di commissione; 01/10 7,68 € → 0,38 €; 10/07 206,16 € → 10,31 €.

**(3) Scelte documentate**
- Perimetro (tennis e posizioni aperte fuori dal conteggio): **DECISIONE DELL'UTENTE** in
  CRONOSTORIA, riga 2956 (25/09 h17:15): «stop giornaliero E34 resta com'è (NO all'inclusione di
  esposizione aperta e paper del tennis)». Il realized su tutto il conto è l'ordine n.10
  dell'utente (`reconcile_worker.py:560-570`).
- Lordo di commissione: **NON documentato come scelta**. Il checkpoint delle 12:56 del 09/10 lo
  lascia «da verificare».

**Verdetto: RIDIMENSIONATO.** Il lordo è vero, ma: (a) oggi lo stop di conto è spento; (b) i
freni dei singoli bot, che sono quelli tarati e accesi (Mike 50 €), usano il netto; (c) con i
volumi live reali lo scarto è di centesimi (0,4-0,5 € a giornata). Arriva a circa 10 € solo in
una giornata con circa 200 € di vincite lorde. Il perimetro asimmetrico è una SCELTA
DOCUMENTATA dell'utente e non è un errore.

---

## M20 - Mike `combine_hazard` = max(atlante, modello × pressione)

**(1) Codice e percorso VIVO**: `Betfair/mike/dossier.py:114-123`, chiamata a `:410`
(`out["hazard"] = combine_hazard(...)`). La pressione arriva da
`safe_strategy/pressure.py:43, 110` (clip 0,85-1,25; `combine_hazard` usa `max(1, mult)`).
L'hazard è consumato da `mike/engine.py:1591` (`cover_timing`: si aspetta solo se hazard ≤
`cover_wait_hazard_max` = 0,06) e `:1449` (cash-out «fase calda» se ≥ 0,10). Valori
confermati in `mike_control`: 0,06 / 0,10, `cover_wait_max_min` = 10, policy `auto`.
L'hazard quindi pesa solo nei primi 10' a 0-0 (attesa della copertura) e nel cash-out «fase calda».

**(2) Esempio rifatto (funzione vera)**: `combine_hazard(0,05; 0,048; 1,25)` = 0,06 (con la
pressione si arriva esattamente alla soglia), mentre la pressione «sul tasso» darebbe
1−(1−0,048)^1,25 = 0,0596. Lo scarto è 0,0004: irrilevante alle soglie di Mike.
`combine_hazard(0,08; 0,10; 1,25)` = 0,125 contro 1−0,9^1,25 = **0,1234**.
**Errore aritmetico dell'audit**: Z1 §2.4 scrive 0,1295 per la versione sul tasso. Il valore
giusto è 0,1234, quindi la versione sulla probabilità è leggermente PIÙ prudente, non meno.
Il bias del massimo (s/√π) è una proprietà matematica corretta, ma gli s sono ipotesi (lo dice l'audit stesso).

**(3) Scelta documentata**: SÌ. `Betfair/mike/COSTITUZIONE_MIKE.md:157-158`: «Hazard 3' = MAX fra
Atlante empirico … e modello λ-residue amplificato dalla pressione (corner/cartellini, fino a
×1,25). Comanda la fonte più prudente.» Anche la tabella dei parametri (`:393, :412`) e il docstring («Hazard 3' PRUDENTE») lo dicono.
In `PIANO_MODIFICHE_MIKE_2026-09-29.md` l'hazard non compare. Il valore 1,25 non è
calibrato nel codice letto (NON verificato altrove).

**Impatto in euro**: alzare l'hazard sopra 0,06 può solo far coprire PRIMA invece di aspettare.
Il costo è il risparmio rinunciato, che la regola stessa richiede ≥ 8% della copertura per
aspettare. Con l'esempio della costituzione (S = 10 € @1,50, copertura 2,26 €) sono circa 0,18 € a partita, e solo nei primi 10' a 0-0.

**Verdetto: SCELTA DOCUMENTATA** (non è un errore; il numero 0,1295 dell'audit è sbagliato).

---

## M21 - Omega, tabella per minuto usata su b..b+4

**(1) Codice e percorso VIVO**
- Costruzione: `migrations/omega_transitions_catchup_2026-09-25.sql:331-341`: lo stato del
  bucket b = punteggio con i gol `minute <= b`, con b ∈ {0, 5, …, 85}. I gol del recupero sono
  registrati a 90 (`:271`, `minute BETWEEN 0 AND 90`).
- Consumo: `Betfair/omega/omega_empirical.py:150-155` (`minute_bucket` = ⌊m/5⌋·5, tetto 85) in
  `MinuteTable.p_result` (`:184-205`).
- Percorso V3 (motore di serie: `strategy_version` = 3, `omega_control.params` non lo
  sovrascrive): `omega_service.py:2043` `_v3_select` → `:1650` `_v3_p_empirica` (`:1547-1592`,
  sempre target FT, `half=False`) → `omega_v3.py:813-821`, `p_nostra = max(p_fusa, p_emp)`,
  veto se > p_max (2%) o se il margine non basta.
- Percorso V2 (`_model_select`, `omega_service.py:1401-1451`) e proposte manuali (`:7761`): stesso lookup.
  Il ranking per minimo (`omega_model.py:582-586`) è del V2.

**(2) Esempio rifatto (modello semplice: 0,03 gol/min nel 2T e circa 0,14 gol di recupero registrati al 90')**
- m = 84 → bucket 80. Massa residua della tabella (80-90] = 10·0,03 + 0,14 = 0,44; vera
  (84-90] = 0,32. Rapporto **≈ 1,37** (audit: 1,32).
- m = 89 → bucket 85. 0,29 contro 0,17, rapporto ≈ 1,7 (audit: 1,57). Coerente.
- Finestra d'ingresso V3: `v3_ft_entry_min/max` = 46/85, `v3_ht_entry_min/max` = 1/44
  (`omega_config.py:250-253`, di serie, non sovrascritti nel DB). Quindi **a 89' Omega non
  entra**. All'85' il bucket è esatto (rapporto 1,0). Il caso peggiore nella finestra è m = 84
  (circa ×1,3). Nella gamba HT il target è comunque FT, con 46'+ di partita davanti: lo
  sfasamento di 4' pesa pochi punti percentuali.

**(3) Scelta documentata?** In parte. `COSTITUZIONE_OMEGA.md` §15.2 (`:922-931`) documenta i
bucket di 5', il recupero «solo nel finale» e `p_selected = max(P modello, P empirica)`. Il
limite superiore di Wilson come veto prudente è documentato in `omega_empirical.py:27-30`
(review F13) e in `omega_v3.py:725-728` («sbagliare per difetto costa la liability intera, per
eccesso solo un'occasione persa»). Lo sfasamento dentro il bucket NON è nominato.

**Impatto in euro**: la direzione è sempre prudente. Il dato entra solo in un `max` e in un veto,
quindi può solo TOGLIERE ingressi e mai aggiungere liability. Con lo stake fisso del V3 (1,00 €)
il costo è l'EV rinunciato sugli ingressi scartati tra b+1 e b+4: centesimi a ingresso.
Il numero di ingressi persi NON è misurato (servirebbe un replay: non lanciato).

**Verdetto: RIDIMENSIONATO** (meccanismo vero, non documentato, ma ×1,57 è fuori finestra e
l'effetto è solo prudenziale).

---

## Cosa NON ho potuto verificare
- M11: resa a schermo e comportamento del toast con un piano non azionabile (né UI né invio eseguiti).
- M22: aliquota reale di commissione del conto .it (assunta 5% come nei parametri dei bot);
  posizioni live di Mike via canale o REST nel blotter del runner (non tracciato fino in fondo).
- M20: calibrazione di 1,25 (`safe_strategy/pressure.py`, non cercata la validazione).
- M21: numero di ingressi Omega persi per lo sfasamento (serve un replay, non lanciato); massa
  dei gol per minuto misurata sul DB (`match_events` troppo grande per una SELECT leggera:
  ho usato un modello semplice e i rapporti dell'audit).
