# Design system delle sezioni di trading (OMEGA · SAFE STRATEGY · MIKE)

> Questo documento è **normativo** per chi lavora su `/omega`, `/safe-strategy` e `/mike`.
> Il lavoro è **uniformare**, non reinventare: tema scuro, `glass-card`, `border-white/10`,
> `font-display`/`font-heading`, accenti `text-primary` (ciano) e `text-secondary` (oro).
>
> Regola d'oro: **lo stesso concetto ha sempre la stessa parola, lo stesso colore e lo stesso formato**.
> Un trader legge tre schermate nella stessa sessione: se "liability" si chiama in tre modi o
> `+€12.50` convive con `+12,50 €`, la lettura rallenta e si perdono soldi.

---

## 1. Struttura di pagina UNICA

```
PageShell                      (sfondo, <title>, container, pb-16)
 └─ BotHeader                  (sticky top-0 z-50; misura la sua altezza → navH)
 │   ├─ link "AI TERMINAL" → /select-sport
 │   ├─ simbolo + nome bot (colore d'accento del bot)
 │   ├─ badge stato bot        (botStatusMeta)
 │   ├─ ServiceHealthChip      (feed + battito servizio + STREAM/REST + DRY)
 │   ├─ ModeToggle             (PAPER | LIVE, aria-pressed)
 │   ├─ slot parametri         (sheet della sezione)
 │   └─ Avvia / Ferma
 ├─ ModeBanner                 (LIVE rosso / PAPER verde, DRY, errore, migrazione)
 ├─ DayBar                     ("Giornata operativa": obiettivo, realizzato, contatori)
 ├─ KpiRow > StatTile…         (riga KPI, skeleton uniforme in caricamento)
 └─ Tabs                       (TabsList sticky sotto l'header: style={{ top: navH }})
     ├─ tab "oggi" del bot
     ├─ tab specifici
     └─ 📅 Storico             (TradingHistory)
 └─ footer                     (fonte dati / avvertenze)
```

Ordine dei tab per sezione (naming ed emoji sono parte del contratto):

| Sezione | Tab |
|---|---|
| Omega | `🎯 Missione` · `⚙️ Automatico` · `✋ Manuale` · `📅 Storico` |
| Safe Strategy | `⚽ Calcio` · `🎾 Tennis` · `📅 Storico` |
| Mike | `⚽ Partite` · `📋 Trade` · `🧾 Attività` · `✅ Regolate` · `📅 Storico` |

La `TabsList` è **sempre** `className="sticky z-30" style={{ top: navH }}`, con `navH` da
`BotHeader.onHeight` (l'header va a capo su mobile: l'offset non è una costante).

---

## 2. Fondamenta pure

### `lib/format.ts` — formati
| funzione | uscita | note |
|---|---|---|
| `fmtMoney(v, {signed, decimals, currency})` | `12,50 €` · `+12,50 €` · `−12,50 €` | `null/NaN → —`, **mai** `0,00 €` per un dato assente |
| `fmtOdds(v)` | `2,04` | 2 decimali, virgola |
| `fmtPct(v, digits=1)` | `12,5 %` | **`v` è una FRAZIONE 0–1** |
| `fmtPctPoints(v, digits=1)` | `12,5 %` | per valori già in punti percentuali |
| `fmtNum(v, digits)` | `1,23` | numero generico italiano |
| `fmtTicks(n)` | `2 tick` | |
| `fmtTime(iso, {seconds})` | `18:05` / `18:05:07` | **sempre Europe/Rome** |
| `fmtDateTime(iso)` | `ven 11 set · 18:05` | |
| `fmtAge(sec)` | `3 s` · `2 min` · `1 h 05` | |
| `ageSeconds(iso, nowMs)` | numero o `null` | mai età negative |
| `MINUS` | `−` (U+2212) | l'unico meno ammesso |

Regole:
- denaro **sempre** con `fmtMoney` (simbolo dopo, virgola decimale);
- il segno `+` solo con `{ signed: true }` (P&L, delta), mai su importi e liability;
- orari **sempre** in Europe/Rome: il browser dell'utente non è la fonte di verità;
- `fmtEurIt`/`fmtOddsIt` in `lib/safeBot.ts` sono **alias storici**: nel codice nuovo usa
  `fmtMoney`/`fmtOdds`.

### `lib/tradeStatus.ts` — etichette
- `statusMeta(status, {reconciling})` → stato del **trade**:
  `pending`→**IN CORSO**, `open`→**APERTO**, `hedged`→**CHIUSO**, `won`→**VINTO**,
  `lost`→**PERSO**, `void`→**VOID**, `error`→**ERRORE**, riconciliazione→**DA RICONCILIARE**.
  Stato ignoto → **ERRORE** (mai una cella muta).
- `botStatusMeta(status, prefix?)` → stato del **bot**: INATTIVO / IN CORSA / IN ARRESTO /
  FERMO / ERRORE (`prefix='BOT'` per Safe e Mike).
- `sideMeta(side)` → **BACK** = `sky`, **LAY** = `rose`. Nessun altro colore per i lati.
- `T` = **glossario** (vedi §3).
- `ACTIVITY_BASE` + `activityMeta(kind, extra?)` + `activityLineGeneric(payload)` (vedi §6).

### `lib/toasts.ts` — notifiche
`toastSettlement({ name, pnl, side, selection, manual, statusLabel })` è l'**unico** formato di
notifica di regolazione:
- vinto → `💰 <nome>` + `+4,20 € · LAY 3 - 2` (success)
- perso → `⚠️ <nome>` + `−24,24 € · BACK Under 3.5` (error)
- void → `<nome>` + `VOID · P&L 0,00 €` (neutro)
- `manual: true` aggiunge `✋` al titolo (si deve sapere chi ha deciso).

---

## 3. Glossario (costanti `T`)

| costante | testo | vietato |
|---|---|---|
| `T.openLiability` | **Liability aperta** | "Capitale a rischio", "responsabilità", "a rischio" |
| `T.lockedPnl` | **P&L bloccato** | "bloccato" da solo come etichetta |
| `T.pnlToday` / `T.pnlTotal` | **P&L oggi** / **P&L totale** | "profit", "realized" |
| `T.cashOut` | **Cash out** | "Cash-out", "cashout" |
| `T.closedAtMarket` | **CHIUSO A MERCATO** | usarlo come stato al posto di **CHIUSO** |
| `T.operatingDay` / `T.dayBarTitle` | **giornata operativa** / **Giornata operativa** | "oggi" come se fosse il giorno del browser |
| `T.goalToday` / `T.goalHit` / `T.remaining` | **Obiettivo di oggi** / **CENTRATO** / **resta** | |
| `T.modePaper` / `T.modeLive` | **MODALITÀ PAPER** / **MODALITÀ LIVE** | |
| `T.liveConfirmTitle` | **Passare a LIVE (soldi veri)?** | varianti per bot |
| `T.restartApp` | **riavvia l'app desktop** | un pallino rosso senza istruzioni |
| `T.start` / `T.stop` / `T.saveParams` / `T.resetParams` | **Avvia** / **Ferma** / **Salva parametri** / **Default** | |

Tutto quello che vede il trader è in **italiano**: nessuno stato, motivo o kind in inglese nudo.

---

## 4. Colori

| significato | classe |
|---|---|
| BACK (punta) | `sky` (`text-sky-300`, `border-sky-500/40`) |
| LAY (banca) | `rose` |
| favorevole / vinto / realizzato ≥ 0 | `emerald` |
| sfavorevole / perso / realizzato < 0 | `red` |
| chiusura / copertura / green fatto | `teal` |
| attenzione, attesa, ritento | `amber` |
| esposizione (liability) | `orange-400` |
| obiettivo, target | `secondary` (oro) |
| accento Omega | `text-primary` · Safe `text-secondary` · Mike `text-teal-300` |

`StatTile` accetta i toni `pos | neg | plain | gold | danger | teal`; `toneOf(v)` li deriva dal segno.

---

## 5. Componenti condivisi (`components/trading/`)

| componente | props essenziali |
|---|---|
| `PageShell` | `title`, `header`, `children`, `footer` |
| `BotHeader` | `bot: 'omega'\|'safe'\|'mike'`, `status`, `statusPrefix`, `statusTestId`, `health`, `modeToggle`, `params`, `running`, `busy`, `startDisabled`, `onStart`, `onStop`, `onHeight` |
| `ServiceHealthChip` | `botName`, `nowMs`, `feedUpdatedAt`, `feedStaleMs`, `feedMissing`, `heartbeatAt`, `counts`, `source`, `streamMarkets`, `dry`, `lastError` |
| `ModeToggle` | `mode`, `onChange`, `disabled` |
| `ModeBanner` | `mode`, `liveText`, `paperText`, `dry`, `error`, `migrationWarning`, `testId` |
| `LiveConfirmDialog` | `open`, `onOpenChange`, `onConfirm`, `busy`, `intro`, `warning` |
| `StatTile` / `KpiRow` | `label`, `value`, `tone`, `icon`, `sub`, `testId` · `loading`, `tiles` |
| `DayBar` | `dayLabel`, `realized`, `realizedTotal`, `goal`, `matches`, `operations`, `won`, `lost`, `live`, `openLiability`, `lockedPnl`, `note`, `testId`, `ids` |
| `SectionCard` | `icon`, `title`, `count`, `note`, `actions`, `testId` |
| `EmptyState` / `LoadingState` | `children` · `label` |
| `ActivityFeed` | `rows`, `metaOf`, `lineOf`, `filterable`, `timeSeconds`, `maxHeightCls`, `emptyText`, `rowTestId` |
| `EquityCard` | `series`, `scope`, `emptyLabel`, `label` |
| `ParamsSheetBase` | `title`, `description`, `groups`, `values`, `onSave`, `onReset`, `busy`, `footer`, `symbol` |

`data-testid` stabili: `page-shell`, `bot-header`, `bot-name`, `bot-status`, `bot-start`,
`bot-stop`, `service-health`, `service-beat`, `service-health-action`, `mode-toggle`,
`mode-banner`, `mode-banner-error`, `mode-banner-migration`, `live-confirm`,
`live-confirm-ok`, `kpi-row`, `stat-tile`, `day-bar`, `day-bar-line`, `day-bar-counts`,
`day-bar-remaining`, `day-bar-goal-hit`, `day-bar-liability`, `day-bar-locked`,
`empty-state`, `loading-state`, `activity-feed`, `activity-row`, `activity-filter`,
`equity-card`, `params-trigger`, `params-sheet`, `params-group`, `params-clamped`,
`params-dirty`, `params-save`, `params-reset`.

`DayBar` accetta `ids` per conservare i `data-testid` storici di una pagina
(es. Omega: `omega-daily-mission`, `omega-mission-line`, `omega-operating-day`,
`omega-remaining`, `omega-goal-hit`, `omega-today-legs`). **Mai rimuovere un testid esistente**:
i test di pagina sono la rete di sicurezza di chi verrà dopo.

---

## 6. Attività del servizio: come aggiungere un `kind`

1. Se il `kind` è **comune a più bot**, aggiungilo a `ACTIVITY_BASE` in `lib/tradeStatus.ts`
   con etichetta italiana, classi colore e `critical: true` se l'utente **deve** accorgersene
   (fallimenti, feed cieco, stop giornaliero, chiusura bloccata).
2. Se è **specifico di una sezione**, mettilo in una mappa locale e passala:
   `activityMeta(kind, MIKE_ACTIVITY_EXTRA)`.
3. Non serve fare nulla per un kind sconosciuto: `activityMeta` lo traduce parola per parola
   (`place→ordine`, `cancel→annullo`, `fill→abbinato`, `retry→ritento`, `failed→fallito`,
   `pending→in corso`…) e solo se nessuna parola è riconoscibile mostra
   `"<kind> (kind sconosciuto)"` in grigio. **Mai** la chiave inglese nuda in maiuscolo.
4. Il testo della riga lo calcola il chiamante (`lineOf` / `row.line`, perché i payload sono
   per bot); `activityLineGeneric(payload)` è il fallback che legge i campi comuni
   (`event_name`, `side`, `selection`, `size`, `price`, `pnl`, `reason/err/note/msg`).

---

## 7. Accessibilità (§17 dell'audit)

- toggle e chip di filtro: `<button type="button">` con `aria-pressed`;
- tab con emoji: l'emoji resta visibile ma il nome accessibile è **testuale**
  (`aria-label="Tennis (2)"`), perciò nei test si interroga per testo, non per emoji;
- barre di avanzamento: `role="progressbar"` con `aria-valuemin/max/now` e `aria-label`;
- banner LIVE: `role="alert"` (si sta parlando di soldi veri);
- icone decorative: `aria-hidden`.

---

## 8. Formati parametri (`ParamsSheetBase`)

- la spec è `groups: { label, note?, fields: { key, label, hint?, type, min, max, step, options }[] }[]`;
- i valori fuori range vengono **clampati e dichiarati**: `clampato a 100 (ammesso 0,50 … 100)`.
  Cambiare un numero in silenzio su un bot che muove denaro è un bug, non un dettaglio;
- `dirty` → pallino sul trigger + riga "modifiche non salvate";
- `onReset` abilita il bottone **Default** (prima esisteva solo in Safe);
- un solo bottone di salvataggio: **Salva parametri**.

I tre pannelli attuali (`ParamsSheet` di Omega, `BotParamsSheet` di Safe,
`MikeParamsSheet`) **non sono ancora migrati**: la base c'è ed è testata, la migrazione
è a carico degli agenti di sezione.

---

## 9. Checklist per chi lavora su una sezione

- [ ] nessun formatter locale: solo `lib/format.ts`
- [ ] nessuna mappa di stati locale: solo `lib/tradeStatus.ts` (+ `extra` per i kind propri)
- [ ] nessun `EmptyBox`/`StatTile`/`ScannerChip` locale: usa i condivisi
- [ ] denaro `12,50 €`, quote `2,04`, percentuali `12,5 %`, orari Europe/Rome
- [ ] "Liability aperta", "P&L bloccato", "Cash out", "CHIUSO", "IN CORSA", "giornata operativa"
- [ ] BACK sky / LAY rose / esiti emerald-red
- [ ] tutti i `data-testid` preesistenti conservati
- [ ] `npx vitest run` verde e `npx tsc --noEmit -p .` pulito
