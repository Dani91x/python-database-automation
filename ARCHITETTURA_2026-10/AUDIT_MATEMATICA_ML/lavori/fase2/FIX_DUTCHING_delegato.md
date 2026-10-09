# Referto delegato: correzione minima dutching (A1 + M11 + V3), 09/10/2026

Baseline: `suite/pytest_betfair_PRIMA.txt` terminata prima di toccare qualsiasi file: `11477 passed, 11 skipped, 6 xfailed in 853s`.
Nessun commit, nessun add/checkout/stash, nessun processo toccato, nessun ordine, nessun `npm install/build`, niente `any`/`@ts-ignore`.
File toccati (tutti nel perimetro): `Betfair/stream/live_order_worker.py`, `Betfair/stream/tests/test_dutching.py`,
`Betfair/stream/tests/test_live_order_dutch_cashout.py`, `frontend/src/components/live/DutchingPanel.tsx`, `DutchingPanel.test.tsx`.
`Betfair/stream/trading/dutching.py` NON modificato (la matematica del server e' corretta: divergeva l'anteprima UI).
Diff completo: `lavori/fase2/suite/diff_fix_dutching.patch` (working tree CRLF, indice LF: il diff e' pulito, solo le righe vere).

## Cosa ho cambiato e perche'

### A1 - variable + lay (worker): `live_order_worker.py` ~2914, in `_do_dutch`, ramo `dmode == "variable"`
Prima di qualsiasi calcolo/prezzo/ordine: `if side == "lay": raise ValueError("dutch mode=variable: supportato solo per back")`,
stesso stile di target+lay. Il ValueError esce da `_do_dutch` e il chiamante (righe ~4213/4372) lo scrive con `_write_error`
(status=error, result.error, error_code): zero ordini. Variable+back invariato (test di caratterizzazione).

### A1 - UI: `DutchingPanel.tsx`
- opzione "Variable (peso)" `disabled` sul lato Lay (come Target), etichetta "- solo Back".
- NESSUN ripiego automatico a Equal (scelta mia, diversa da Target): se l'utente sceglie variable e poi passa a Lay, lo stato resta
  variable+lay, compare l'avviso "Variable non disponibile sul lato Lay ...", il bottone e' disabilitato; `guardBeforeSend`
  restituisce comunque il motivo leggibile (difesa in profondita').

### M11 - anteprima variable = server: `DutchingPanel.tsx`
Nuove funzioni esportate: `pyRound2`, `nearestTickPrice`, `dutchVariablePlan` (+ `pySum` interna). Formula identica a `dutch_variable`:
k = T(1-S 1/p)/S(w/p); s_i = round((T+k w_i)/p_i, 2); totale = round(S s_i, 2); profit_i = round(s_i p_i - totale, 2); stesse esclusioni
(quota<=1 o non finita, peso<=0 o non finito: gia' applicate dal filtro `valid` dell'anteprima) e stesso rifiuto se uno stake e' negativo:
"Pesi irrealizzabili con book X%: stake negativo sulla selezione ...", stake e profitti mostrati "—", bottone disabilitato, guard che blocca.
Il book% in variable e' quello del server (prezzi al tick, `round(S 1/p * 100, 2)`); "stake sommati" = totale del server (es. 100.01).
Equal/target: codice di prima, invariato (test di regressione sul modo equal).
Arrotondamenti, scelta documentata:
- `pyRound2`: `round(x,2)` di Python = centesimo piu' vicino sul valore binario ESATTO, pareggio esatto (x=j/8, j dispari: 0.125, 0.375, 0.625, 0.875, 1.125...) al pari.
  `Number(x.toFixed(2))` e' corretto sul valore esatto, ma sui pareggi esatti va al maggiore: li intercetto (`a*8` intero dispari) e scelgo il pari.
- `pySum`: da Python 3.12 `sum()` dei float e' compensata (Neumaier); il venv e' 3.13.3. Replicata.
- `nearestTickPrice`: la `roundToTick` di `@/lib/matching` NON coincide con `flumine.get_nearest_price` (37 divergenze sulla griglia 1.01..1000, tutte sui pareggi
  mezzo tick, es. 2.01: JS 2.00, flumine 2.02), quindi ne ho scritta una a parte con aritmetica intera (mezzo tick in su, come ROUND_HALF_UP di flumine).
Prezzo usato dall'anteprima: quello della riga (digitato o back/lay mostrato) PORTATO AL TICK. A `sendDutch` va il prezzo digitato (non lo altero: il server lo porta al tick).

### V3 - esito ok senza ordini: `DutchingPanel.tsx` `handleDutch`
Forma REALE del risultato: `_result(...)` ha le chiavi `ok, action, mode, bet_id, status, size_matched, average_price_matched, size_remaining,
market_id, selection_id, side, price, size, customer_order_ref, submin_step, error, detail`; SOLO dopo il piazzamento `_do_dutch` aggiunge
`result["legs"] = placed` prima di `_write_done`. Con piano non azionabile (pesi irrealizzabili, book>=100% in target, nessuna selezione) scrive
`ok=True`, `detail=plan.note` e NESSUN `legs`. `get_betfair_live_order` restituisce `to_jsonb(riga)` intera (migrations/betfair_live_order_queue.sql ~311), quindi `result.legs` arriva al client.
`LiveOrderResult` (`liveOrders.ts`, fuori perimetro) non dichiara `legs`: uso `res as LiveOrderResult & { legs?: unknown }` (niente `any`).
Criterio: `ok && !(Array.isArray(legs) && legs.length > 0)` -> `toast.error('Dutching NON piazzato', { description: res.detail ?? ... })`; altrimenti "Dutching inviato" come prima.
Il reset della conferma LIVE (`shouldResetLiveConfirm(isLive, res.ok)`) e' invariato.

## Test aggiunti
Python `test_live_order_dutch_cashout.py`: `test_dutch_variable_lay_is_rejected_with_zero_orders`, `..._even_when_pricing_would_fail` (il rifiuto precede il calcolo prezzi),
`test_dutch_variable_back_unchanged_places_server_plan`. `test_dutching.py`: 3 test con valori di riferimento letterali di `dutch_variable` (casi A, B, fuori-tick, irrealizzabile).
Frontend `DutchingPanel.test.tsx`: 15 test nuovi (28 in tutto): A1 x3, M11 x7 (A, B, C fuori-tick, irrealizzabile, book>100 realizzabile, 4 gambe, equal invariato),
funzioni pure x2 (`pyRound2` su 19 casi, `nearestTickPrice` su 33), V3 x3. Il finto `sendDutch` ora restituisce l'esito con le chiavi identiche a `_result` (+`legs`):
il default dei test esistenti e' stato aggiornato di conseguenza (senza `legs` vedrebbero "NON piazzato", come deve).
Valori attesi: letterali copiati dall'esecuzione della VERA funzione, comando (dalla radice R):
`PYTHONPATH=. .venv/Scripts/python.exe -c "from Betfair.stream.trading.dutching import dutch_variable as d; p=d([(1,2.5,1),(2,3.0,2),(3,4.0,1)],100); print([(l.selection_id,l.price,l.size,l.profit_if_wins) for l in p.legs], p.total_stake, p.book_pct)"`
e lo stesso per B `[(1,2.0,1),(2,5.0,3)],50`; C `[(1,2.01,1.5),(2,3.03,1),(3,4.5,2)],37.5`; D `[(1,1.5,1),(2,1.8,1),(3,3.0,2)],10`;
E irrealizzabile `[(1,1.5,1),(2,1.8,1),(3,10.0,6)],10`; F `[(1,2.2,1),(2,3.4,1.25),(3,6.2,0.5),(4,11.0,3)],123.45`.
Tick e pareggi attesi: `flumine.utils.get_nearest_price(x)` e `round(x,2)` eseguiti in Python.

## ROSSO prima, VERDE dopo
- Python prima del fix: `suite/pytest_dutch_ROSSO_prima_fix.txt` -> `2 failed, 24 passed` (i 2 test di rifiuto: "DID NOT RAISE ValueError"; gli altri sono caratterizzazioni
  gia' verdi: guardia di regressione e fonte dei letterali). Dopo: `suite/pytest_dutch_FINALE.txt` -> `26 passed in 0.43s`.
- Frontend prima: `suite/vitest_dutching_ROSSO_prima_fix.txt` -> 12 failed, 16 passed (i rossi mostrano i numeri vecchi dell'audit, es. 30.38/50.63/18.99 invece di 40.51/34.18/25.32;
  `pyRound2/nearestTickPrice is not a function`; avviso e toast assenti). Dopo: `suite/vitest_dutching_FINALE.txt` -> `Tests 28 passed (28)`.
  `suite/tsc_FINALE.txt`: `npx tsc -p tsconfig.app.json --noEmit` exit 0, 0 errori.

## Falsificazione (output in suite/)
- Python, tolto il fix (`if False and side == "lay"`): `suite/pytest_dutch_FALSIFICAZIONE_senza_fix.txt` -> `2 failed, 24 passed`; rimesso -> `26 passed`.
- Frontend (`suite/_mutate.cjs`, una mutazione alla volta, ripristino dalla copia fedele verificato con `cmp`), output `suite/vitest_FALSIFICAZIONE.txt` e `..._bis.txt`:
  opzione Variable non disabilitata -> 1 rosso; avviso+bottone variable+lay tolti -> 1 rosso; formula vecchia (stake proporzionale a peso/quota) -> 6 rossi (tutti i casi M11);
  `pyRound2` ingenuo (Math.round) -> 1 rosso; `nearestTickPrice` ingenuo -> 2 rossi; V3 tolto -> 2 rossi; infeasible non bloccante -> 1 rosso.
  NON falsificabile da un test via UI: la sola clausola della guardia `guardBeforeSend` per variable+lay (il bottone disabilitato impedisce di arrivarci): e' difesa in profondita', coperta dal bottone e dall'avviso, che hanno i loro test rossi.
- Test indipendente extra, differenziale TS vs Python: `suite/_gen_cases.py` (`PYTHONPATH=.`) genera 20000 casi casuali (2-8 gambe, quote su tick e fuori tick, pesi decimali, T casuali; 310 irrealizzabili)
  con la VERA `dutch_variable`; `suite/_diff.mjs` estrae dal sorgente reale del pannello le funzioni e le confronta (`node --experimental-strip-types`):
  `suite/differenziale_ts_vs_python.txt` -> 0 divergenze su 20000 casi e 0 su 99.900 prezzi (griglia 1.01..1000 passo 0.01 vs `get_nearest_price`).
  Con `pyRound2` ingenuo: 748 divergenze; con somma ingenua: 2 (`differenziale_FALSIFICAZIONE_*.txt`): il differenziale discrimina e le due accortezze servono.
  I due JSON voluminosi (`_cases.json`, `_tick_py.json`) sono stati cancellati; `_cases.json` si rigenera con `_gen_cases.py`, `_tick_py.json` con `get_nearest_price(i/100)` per i in 101..100000.

## Non verificato
- La resa a schermo reale (browser/app) e il polling vero di `sendLiveOrderCommand` con Supabase: verificato solo in jsdom con `sendDutch` mockato (chiavi identiche a `_result`) e leggendo la RPC SQL.
- La suite intera `Betfair/` e `npx vitest run` completa: non lanciate (le rilancia il coordinatore). Eseguiti solo i 3 comandi richiesti.
- Il percorso `_process_*` -> `_write_error` per variable+lay e' letto, non eseguito end to end (il test chiama `_do_dutch` come gli altri test esistenti del file).

## Fuori perimetro / reperti da portare all'utente
1. **Prezzo effettivo del server**: l'anteprima conosce solo il prezzo della riga. Con `pricing` best / in_front / nominated il server usa un altro prezzo
   (book corrente, un tick davanti, prezzo unico nominato per TUTTE le gambe): per quelle modalita' l'anteprima di variable (e di equal/target) e' una stima, non il piano esatto.
   L'esattezza vale con `as_given`. La nota in UI "stima UI - il server piazza ..." resta; non ho cambiato la gestione del pricing (semantica degli altri comportamenti).
2. **`build_order` porta lo stake al multiplo di 0,50 per difetto** (log: "punta 40.51 -> 40.50 (multiplo di 0,50 per difetto): residuo 0.01 NON piazzato", giurisdizione .it) DOPO il piano di `dutch_variable`:
   gli ordini reali del caso A sono 40.50/34.00/25.00 (non 40.51/34.18/25.32) e i profitti reali differiscono da quelli del piano (il worker scrive `profit_if_wins` del PIANO, non ricalcolato sulle punte effettive).
   Vale anche per equal/target. Anteprima e `result.legs.profit_if_wins` non lo riflettono. Non toccato (fuori richiesta e dentro `live_order_build.py`).
3. `frontend/src/lib/liveOrders.ts`: `LiveOrderResult` non dichiara `legs`; consigliato aggiungere `legs?: {selection_id:number; side:string; price:number; size:number; profit_if_wins:number}[] | null` per togliere l'intersezione di tipo in `DutchingPanel.tsx`.
4. `@/lib/matching.roundToTick` diverge da `get_nearest_price` di flumine sui pareggi mezzo tick (37 casi sulla griglia): chiunque lo usi per prevedere il prezzo del server sbaglia di un tick su quei casi.
5. Il server, per variable, usa `_f(weight) or 1.0`: un peso 0 diventerebbe 1.0 lato server; la UI non lo invia mai (peso <=0 escluso), quindi nessun effetto oggi.

## Diff del codice di produzione (worker + pannello)
```diff
diff --git a/Betfair/stream/live_order_worker.py b/Betfair/stream/live_order_worker.py
index 7f342936..2c72c6b5 100644
--- a/Betfair/stream/live_order_worker.py
+++ b/Betfair/stream/live_order_worker.py
@@ -2912,6 +2912,11 @@ def _do_dutch(sb: Any, flumine: Any, request_row: Dict[str, Any], mode: str, str
         return price
 
     if dmode == "variable":
+        # A1 (audit matematica ML): dutch_variable e' SOLO back (restituisce sempre side="back").
+        # Con side=lay il worker piazzava ordini BACK per una richiesta LAY: rifiuto esplicito,
+        # PRIMA di qualsiasi calcolo/ordine, come per target+lay.
+        if side == "lay":
+            raise ValueError("dutch mode=variable: supportato solo per back")
         triples = [
             (int(s["selection_id"]), _price_or_raise(s), _f(s.get("weight")) or 1.0)
             for s in sels_in
diff --git a/frontend/src/components/live/DutchingPanel.tsx b/frontend/src/components/live/DutchingPanel.tsx
index 9a4c8fbc..55458480 100644
--- a/frontend/src/components/live/DutchingPanel.tsx
+++ b/frontend/src/components/live/DutchingPanel.tsx
@@ -8,8 +8,9 @@
 //
 // Matematica QUI = solo anteprima:
 //   book% = Σ(1/quota)·100  (bookPercentage da @/lib/riskMath)
-//   peso base_i = 1/quota_i ; variable → base_i·peso_utente_i
-//   stake_i = totale · peso_i / Σpeso
+//   equal : peso base_i = 1/quota_i ; stake_i = totale · peso_i / Σpeso
+//   variable: IDENTICA a `dutch_variable` del server (profitto ∝ peso utente), vedi
+//             `dutchVariablePlan` (solo BACK: sul lato Lay il worker la rifiuta)
 //   BACK: profitto_se_vince_i = stake_i·quota_i − totale (equal → uguale per tutte)
 //   LAY : responsabilità_i    = stake_i·(quota_i − 1)
 //   BACK favorevole se book% < 100 · LAY favorevole se book% > 100.
@@ -29,7 +30,7 @@ import { bookPercentage } from '@/lib/riskMath';
 import {
     sendDutch, shouldResetLiveConfirm,
     type LiveOrderMode, type LiveOrderSide, type LivePersistence,
-    type DutchMode, type DutchPricing,
+    type DutchMode, type DutchPricing, type LiveOrderResult,
 } from '@/lib/liveOrders';
 
 // 'off' = runner senza ordini: pannello in sola lettura (zero regressioni).
@@ -81,6 +82,93 @@ const money = (v?: number | null) =>
     v == null || !Number.isFinite(v) ? '—' : `${v < 0 ? '−' : ''}€${Math.abs(v).toFixed(2)}`;
 const r2 = (x: number) => Math.round(x * 100) / 100;
 
+// ------------------- aritmetica IDENTICA al server (dutch_variable) -------------------
+// Il server calcola in Python: `round(x, 2)` arrotonda sul valore binario ESATTO e, sui
+// pareggi esatti (x = j/8 con j dispari: 0.125, 0.375, ...), va al pari; `sum()` dei float
+// e' compensata (Neumaier, da Python 3.12). Math.round(x*100)/100 differisce da entrambi.
+
+/** `round(x, 2)` di Python: sul valore binario esatto, pareggi esatti al centesimo pari. */
+export function pyRound2(x: number): number {
+    if (!Number.isFinite(x)) return x;
+    const a = Math.abs(x);
+    const e = a * 8; // moltiplicare per 2^k e' esatto
+    if (Number.isInteger(e) && e % 2 === 1) { // pareggio esatto: a*100 = n + 0.5
+        const lo = Math.floor(a * 100);
+        const n = lo % 2 === 0 ? lo : lo + 1;
+        return Math.sign(x) * (n / 100);
+    }
+    return Number(x.toFixed(2)); // toFixed e' corretto sul valore binario esatto
+}
+
+/** `sum()` di Python sui float (3.12+): somma compensata alla Neumaier. */
+function pySum(xs: readonly number[]): number {
+    let acc = 0;
+    let c = 0;
+    for (const x of xs) {
+        const t = acc + x;
+        if (!Number.isFinite(t)) { acc = t; continue; }
+        if (Math.abs(acc) >= Math.abs(x)) c += (acc - t) + x; else c += (x - t) + acc;
+        acc = t;
+    }
+    return c !== 0 && Number.isFinite(c) ? acc + c : acc;
+}
+
+// [limite superiore, passo in centesimi] — scala dei tick Betfair (flumine CUTOFFS)
+const TICK_CUTOFFS: ReadonlyArray<readonly [number, number]> = [
+    [2, 1], [3, 2], [4, 5], [6, 10], [10, 20], [20, 50], [30, 100], [50, 200], [100, 500], [1000, 1000],
+];
+
+/** `get_nearest_price` di flumine (quanto usa il server): tick piu' vicino, mezzo tick in su. */
+export function nearestTickPrice(price: number): number {
+    if (price <= 1.01) return 1.01;
+    if (price > 1000) return 1000;
+    let stepCents = 1000;
+    for (const [cutoff, st] of TICK_CUTOFFS) {
+        if (price < cutoff) { stepCents = st; break; }
+    }
+    // aritmetica intera su price*1e8 (i pareggi tipo 2.01 -> 2.02 non dipendono dal float)
+    const x = Math.round(price * 1e8);
+    const k = 1e6 * stepCents;
+    const n = Math.floor((2 * x + k) / (2 * k));
+    return (n * stepCents) / 100;
+}
+
+export interface VariablePlanLeg { price: number; stake: number; profit: number }
+export interface VariablePlan {
+    legs: VariablePlanLeg[];
+    total: number;
+    bookPct: number;
+    /** indice (in `input`) della prima gamba con stake negativo = pesi irrealizzabili; -1 = ok */
+    negativeIndex: number;
+}
+
+/**
+ * Stessa matematica di `dutch_variable` (Betfair/stream/trading/dutching.py): profitto
+ * proporzionale al peso, k = T(1−Σ1/p)/Σ(w/p), s_i = round((T + k·w_i)/p_i, 2),
+ * totale = round(Σs, 2), profitto_i = round(s_i·p_i − totale, 2). I prezzi sono portati al
+ * tick come fa il server. `input` e' GIA' filtrato (quota > 1, peso > 0).
+ */
+export function dutchVariablePlan(
+    input: readonly { price: number; weight: number }[],
+    totalStake: number,
+): VariablePlan {
+    const prices = input.map(l => nearestTickPrice(l.price));
+    const invSum = pySum(prices.map(p => 1 / p));
+    const wpSum = pySum(input.map((l, i) => l.weight / prices[i]));
+    const k = totalStake * (1 - invSum) / wpSum;
+    const bookPct = pyRound2(invSum * 100);
+    const stakes = input.map((l, i) => pyRound2((totalStake + k * l.weight) / prices[i]));
+    const negativeIndex = stakes.findIndex(s => s < 0);
+    if (negativeIndex >= 0) return { legs: [], total: 0, bookPct, negativeIndex };
+    const total = pyRound2(pySum(stakes));
+    return {
+        legs: stakes.map((stake, i) => ({
+            price: prices[i], stake, profit: pyRound2(stake * prices[i] - total),
+        })),
+        total, bookPct, negativeIndex: -1,
+    };
+}
+
 // ----------------------------- badge modalità -----------------------------
 function ModeBadge({ mode }: { mode: DutchPanelMode }) {
     if (mode === 'live') {
@@ -181,7 +269,17 @@ export function DutchingPanel({
         });
 
         const validRaws = raws.filter(r => r.valid);
-        const book = bookPercentage(validRaws.map(r => r.price));
+        // VARIABLE: stessa formula e stessi arrotondamenti del server (profitto ∝ peso).
+        const variable = calcMode === 'variable' && validRaws.length > 0
+            ? dutchVariablePlan(validRaws.map(r => ({ price: r.price, weight: r.userWeight })), enteredTotal)
+            : null;
+        const negLeg = variable != null && variable.negativeIndex >= 0 ? validRaws[variable.negativeIndex] : null;
+        const infeasible: string | null = variable != null && negLeg != null
+            ? `Pesi irrealizzabili con book ${variable.bookPct.toFixed(2)}%: stake negativo sulla selezione `
+                + `«${negLeg.s.name ?? `#${negLeg.s.selection_id}`}» `
+                + '— riduci i pesi o usa Equal (profitto pari). Il server non piazzerebbe nulla.'
+            : null;
+        const book = variable != null ? variable.bookPct : bookPercentage(validRaws.map(r => r.price));
 
         // TARGET (equal-profit): il server dimensiona le gambe dal profitto obiettivo.
         // Stima UI del totale per il lato back: S = T·b/(1−b) con b=book/100 (fattibile solo se book<100).
@@ -196,15 +294,18 @@ export function DutchingPanel({
         const sumW = weighted.reduce((a, b) => a + b.w, 0);
 
         // 3) stake + profitto/responsabilità per gamba.
-        const legs: Leg[] = weighted.map(({ r, w }) => {
-            const stake = sumW > 0 ? r2(total * w / sumW) : 0;
+        const legs: Leg[] = weighted.map(({ r, w }, i) => {
+            // variable: stake/profitto = quelli del server; irrealizzabile = nulla da mostrare.
+            const stake = variable != null
+                ? (variable.legs[i]?.stake ?? 0)
+                : (sumW > 0 ? r2(total * w / sumW) : 0);
             return {
                 selection_id: r.s.selection_id,
                 name: r.s.name ?? `#${r.s.selection_id}`,
                 price: r.price,
                 userWeight: r.userWeight,
                 stake,
-                profitBack: r2(stake * r.price - total),
+                profitBack: variable != null ? (variable.legs[i]?.profit ?? 0) : r2(stake * r.price - total),
                 liability: r2(stake * (r.price - 1)),
             };
         });
@@ -220,13 +321,14 @@ export function DutchingPanel({
             target,
             book,
             bookOk,
+            infeasible,
             legs,
             legById,
             count: legs.length,
             minProfit: profits.length ? Math.min(...profits) : 0,
             maxProfit: profits.length ? Math.max(...profits) : 0,
             totalLiability: liabilities.reduce((a, b) => a + b, 0),
-            sumStake: r2(legs.reduce((a, b) => a + b.stake, 0)),
+            sumStake: variable != null ? variable.total : r2(legs.reduce((a, b) => a + b.stake, 0)),
         };
         // defaultPrice dipende da `side`: incluso nelle deps sotto.
         // eslint-disable-next-line react-hooks/exhaustive-deps
@@ -246,7 +348,13 @@ export function DutchingPanel({
         if (side === 'lay' && isTargetMode) {
             return 'Modalità Target non disponibile sul lato Lay (il worker la rifiuta): usa Equal/Variable.';
         }
+        // A1: dutch_variable e' SOLO back (il worker rifiuta variable + lay): blocco client-side.
+        if (side === 'lay' && calcMode === 'variable') {
+            return 'Modalità Variable non disponibile sul lato Lay (il worker la rifiuta): usa Equal o passa a Back.';
+        }
         if (preview.count < 2) return 'Seleziona almeno 2 selezioni con quota valida.';
+        // M11/V3: pesi irrealizzabili = il server non piazzerebbe nulla → non inviare.
+        if (preview.infeasible) return preview.infeasible;
         if (isTargetMode) {
             if (preview.target <= 0) return 'Profitto obiettivo non valido (> 0).';
         } else if (preview.total <= 0) {
@@ -285,7 +393,15 @@ export function DutchingPanel({
                     ...(calcMode === 'variable' ? { weight: l.userWeight } : {}),
                 })),
             });
-            if (res.ok) {
+            // V3: il worker risponde ok=True ANCHE quando il piano non e' azionabile (es. pesi
+            // irrealizzabili) e non parte alcun ordine: in quel caso `legs` (scritto dal worker
+            // solo dopo il piazzamento) manca o e' vuoto → NON dire "inviato".
+            const placedLegs = (res as LiveOrderResult & { legs?: unknown }).legs;
+            if (res.ok && !(Array.isArray(placedLegs) && placedLegs.length > 0)) {
+                toast.error('Dutching NON piazzato', {
+                    description: res.detail ?? 'nessun ordine partito (piano non azionabile)',
+                });
+            } else if (res.ok) {
                 toast.success('Dutching inviato', {
                     description: [
                         `${preview.count} gambe`,
@@ -375,7 +491,10 @@ export function DutchingPanel({
                         <select className={SELECT_CLS} value={calcMode}
                             onChange={e => setCalcMode(e.target.value as DutchMode)}>
                             <option value="equal">Equal (profitto pari)</option>
-                            <option value="variable">Variable (peso)</option>
+                            {/* A1: Variable e' solo Back (il worker rifiuta variable + lay) */}
+                            <option value="variable" disabled={side === 'lay'}>
+                                Variable (peso{side === 'lay' ? ' — solo Back' : ''})
+                            </option>
                             {/* fix audit #19: Target non disponibile sul lato Lay (il worker lo rifiuta) */}
                             <option value="target" disabled={side === 'lay'}>
                                 Target (profitto obiettivo{side === 'lay' ? ' — solo Back' : ''})
@@ -483,15 +602,16 @@ export function DutchingPanel({
                                                     </td>
                                                 )}
                                                 <td className="py-1.5 px-2 text-right font-mono text-white">
-                                                    {leg ? money(leg.stake) : '—'}
+                                                    {leg && !preview.infeasible ? money(leg.stake) : '—'}
                                                 </td>
                                                 <td className={`py-1.5 pl-2 text-right font-mono ${
-                                                    !leg ? 'text-white/40'
+                                                    !leg || preview.infeasible ? 'text-white/40'
                                                         : sideIsBack
                                                             ? (leg.profitBack >= 0 ? 'text-emerald-300' : 'text-rose-300')
                                                             : 'text-rose-300'
                                                 }`}>
-                                                    {leg ? money(sideIsBack ? leg.profitBack : leg.liability) : '—'}
+                                                    {leg && !preview.infeasible
+                                                        ? money(sideIsBack ? leg.profitBack : leg.liability) : '—'}
                                                 </td>
                                             </tr>
                                         );
@@ -502,6 +622,17 @@ export function DutchingPanel({
                     )}
                 </div>
 
+                {side === 'lay' && calcMode === 'variable' && (
+                    <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[11px] font-bold text-amber-300">
+                        Variable non disponibile sul lato Lay (il worker la rifiuta): passa a Back o scegli Equal.
+                    </div>
+                )}
+                {preview.infeasible && (
+                    <div className="rounded-xl border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-[11px] font-bold text-rose-300">
+                        {preview.infeasible}
+                    </div>
+                )}
+
                 {/* ---------------- ANTEPRIMA LIVE ---------------- */}
                 <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3 md:p-4">
                     <div className="flex items-center justify-between gap-3 flex-wrap">
@@ -598,6 +729,8 @@ export function DutchingPanel({
                             || (isNominated && !((num(nominatedPrice) ?? 0) > 1))
                             || bookFresh === false
                             || (side === 'lay' && isTargetMode)
+                            || (side === 'lay' && calcMode === 'variable')
+                            || preview.infeasible != null
                             || (isLive && !confirmLive)}
                         className={`font-black ${
                             sideIsBack
```
