# R-06 - Foglio parametri di Safe: `risk.max_open_trades` non viene piu' scritto a 0

Delegato Opus per admin-01, 01/10/2026. Worktree portato su `49fb207` (era su `2d8ee70`,
senza la correzione di `salvaStop`). Nel frattempo master e' avanzato a `97ad749`, che
aggiunge SOLO `migrations/safe_risk_max_open_trades_null_2026-10-01.sql` (sanatoria del DB):
la patch e' `git diff master -- frontend/src` e si applica su master (`git apply --check -R` ok).
Niente commit, nessun file Python/SQL toccato, nessuna strategia toccata.

## Reperto

- `toValues` costruisce `src = { ...raw, ...p }`: `p.risk` (da `mergeRiskParams`) SOSTITUISCE
  `raw.risk` e non contiene `max_open_trades` (non e' fra `SAFE_RISK_DEFAULTS`). Quindi
  `getPath(src, 'risk.max_open_trades')` era sempre `undefined` -> mostrato **0**, anche
  quando il DB aveva 5.
- `fromValues` riparte da `raw` e fa `setPath` di ogni valore: scriveva `risk.max_open_trades = 0`.
  Con un DB a 5, il 5 veniva riscritto a 0.
- Servizio (`Betfair/safe_strategy/risk.py`): `merge_risk_params` riga 80-82 tiene `None` se la
  chiave manca, altrimenti `max(0, int(...))`; `risk_params` 101-102: `None` -> `params.max_open_trades`
  del bot; `check` 203-205: `if max_open and open >= max_open` -> **0 = nessun tetto**.
  `bot_service.py:346`: `max_open_trades` del bot di serie **20** (verificato).
- Inoltre: un campo numerico svuotato arrivava a `fromValues` come stringa `''` e veniva
  scritto cosi'; per questa chiave il servizio fa `int(_f('', 0.0))` = 0 -> anche "vuoto"
  significava "nessun tetto".

## Correzione (solo `frontend/src/components/safestrategy/BotParamsSheet.tsx`)

- `TETTO_RISCHIO_KEY = 'risk.max_open_trades'` (esportata).
- `toValues`: il valore si legge dalla riga GREZZA (`raw.risk.max_open_trades`): numero finito
  -> quel numero (anche 0); assente / null / non numerico -> **campo vuoto `''`**, mai 0.
- `fromValues`: se la chiave e' fra i valori, si scrive SOLO se nel campo c'e' un numero
  (numero o stringa numerica non vuota); campo vuoto o non numerico -> la chiave viene
  **tolta** dalla copia di `risk` (la riga letta non viene mutata). Se la chiave NON e' fra i
  valori (caso `salvaStop`, che la cancella quando il DB non porta un numero) la chiave della
  riga letta resta com'e' -> `salvaStop` invariato e coerente.
- DB a 0 e campo non toccato -> resta 0 (non si decide per l'utente).
- Testo del campo: `tetto sulle posizioni vive contemporanee: ha la PRECEDENZA su "Max trade
  aperti". 0 = NESSUN tetto (illimitato); vuoto = vale "Max trade aperti" del bot (ora N; di
  serie 20)`, con N = `params.max_open_trades` del bot (se 0: "0, cioe' nessun tetto").
- A campo vuoto la riga "salvato X / il servizio usa Y" non si mostra (sarebbe "salvato 0").
- Bottone "Default": `toValues(SAFE_BOT_DEFAULTS, EXITS_DEFAULTS, null)` -> campo vuoto ->
  chiave assente (= predefinito del servizio, che e' `None`).
- Aggiunte ASCII-only.

## Test

`BotParamsSheet.test.tsx` (nuovo describe "R-06", finti = `RAW` gia' usato dal file, chiavi
di produzione `risk.daily_liability_cap`, `risk.daily_loss_stop`, `max_open_trades`):
- (a) chiave assente + campo non toccato: campo `''`, payload SENZA la chiave, resto del rischio invariato;
- (b) DB 5: mostra 5, salva 5;
- DB 0 non toccato: resta 0;
- (c) l'utente scrive 0 su chiave assente: salva 0;
- (d) l'utente svuota il campo (era 5): chiave assente nel payload, riga letta non mutata;
- testo del campo con "ora 12; di serie 20" (bot a 12);
- Default: campo vuoto, payload senza chiave;
- puro `toValues`/`fromValues`: assente, null, `'x'` -> `''` -> assente; 0 e 5 -> conservati.

`salvaStop.test.ts`:
- (e) "Safe: identico a BotParamsSheet.save": tolto il `delete v['risk.max_open_trades']` che
  documentava la vecchia differenza; ora il payload della testata coincide col foglio PURO
  e si verifica anche che la chiave sia assente;
- nuovo: identita' foglio/testata anche con DB a 5 e a 0 (chiave conservata).

Esiti: `tsc -p tsconfig.app.json --noEmit` = 0. Foglio + salvaStop + InterruttoreUsciteSchede +
FasciaStop: 4 file / 108 test verdi. `src/components/safestrategy` + `src/components/controlroom`:
91 file / 1281 verdi. `src/pages/SafeStrategy*`, `src/pages/ControlRoom*`, `src/lib/safeBot*`:
11 file / 399 verdi. Suite intera NON rilanciata.

## Falsificazione (ripristino verificato: diff identico al backup, poi tutto verde)

| Mutazione | Rossi |
|---|---|
| M1 comportamento vecchio: `toValues` assente -> 0 e `fromValues` vuoto -> 0 | 5: (a), (d), Default, puro, salvaStop "identico" |
| M2 solo `fromValues` vuoto -> 0 | 5: gli stessi |
| M3 solo `toValues` assente -> 0 | 4: (a), Default, puro, salvaStop "identico" |
| M4+M5 `toValues` ignora il valore del DB + testo vecchio "0 = illimitato" | 5: (b), DB 0, testo, puro, salvaStop "5 e 0" |
| M6 `fromValues` tratta 0 come assente | 4: DB 0, (c), puro, salvaStop "5 e 0" |

## Punto 2 - gli altri campi del rischio

Predefiniti: servizio `risk.py` DEFAULT_RISK_PARAMS; frontend `SAFE_RISK_DEFAULTS` (`lib/safeBot.ts:688`).

| Chiave | Servizio, chiave ASSENTE | Servizio, 0 | Frontend, assente | Assente e 0 diversi? | Correzione |
|---|---|---|---|---|---|
| `risk.max_open_trades` | `params.max_open_trades` del bot (di serie 20) | nessun tetto (`if max_open and`) | mostrava e scriveva 0 | SI' | **corretta** |
| `risk.daily_liability_cap` | 500 | nessun cap (`day_cap > 0`) | mostra e scrive 500 | si', ma il foglio scrive 500 = effetto identico all'assente | nessuna |
| `risk.per_event_liability_cap` | 150 | nessun cap (`ev_cap > 0`) | 150 | idem | nessuna |
| `risk.model_daily_liability_cap` | 150 | nessun cap (`m_cap > 0`) | 150 | idem | nessuna |
| `risk.per_event_max_trades` | 3 | nessun limite (`if per_ev and`) | 3 | idem | nessuna |
| `risk.correlated_cap` | 0,7 | peso 0 ai mercati diversi | 0,7 | idem | nessuna |
| `risk.daily_loss_stop` | -50 | stop spento | -50 | idem | nessuna |
| `risk.model_stake` | 5 | stake 0 | 5 | idem | nessuna |
| `max_open_trades` (bot) | 20 (`bot_service.py:346`) | illimitato | 20 | idem | nessuna |

Per tutte tranne R-06 il foglio scrive esplicitamente il predefinito del servizio: oggi stesso
effetto della chiave assente. Unica conseguenza: se un giorno cambiasse il predefinito Python,
il DB resterebbe col vecchio valore scritto (non e' un difetto di oggi).

## Cosa non ho verificato / reperti aperti

1. **Reperto aperto (non corretto, fuori perimetro)**: qualunque ALTRO campo numerico del foglio
   svuotato dall'utente viene scritto sul DB come stringa `''` (`ParamsSheetBase` passa `''`,
   `fromValues` fa `setPath`). Il servizio lo tratta col predefinito (`_f('')` -> default), il
   foglio alla riapertura mostra il predefinito di `mergeBotParams`/`mergeRiskParams`: nessun
   effetto sui soldi trovato, ma il DB porta una stringa in un campo numerico.
2. DB con valore non numerico (es. stringa) per `risk.max_open_trades`: oggi il servizio lo legge
   0 (nessun tetto); il foglio mostra vuoto e, al salvataggio, toglie la chiave (-> tetto del bot).
   Direzione prudente, ma e' un cambio di significato su un dato gia' sporco; caso non presente
   sul DB secondo il brief (valore 0).
3. Nessun test end-to-end con l'app viva ne' build: solo vitest/jsdom. Suite intera non rilanciata.
4. Non ho letto il DB: mi baso sul brief (valore 0) e sulla migrazione `97ad749`, che lo riporta
   ad assente; dopo la migrazione il foglio corretto non lo riscrive piu'.
5. `null` nel DB: il foglio salva la chiave ASSENTE, `salvaStop` conserva `null`: per il servizio
   sono identici (`None`), ma i due payload differiscono in quel solo caso (non coperto dal test di identita').
6. `salvaStop.ts` non e' stato modificato: il suo blocco R-06 ora e' ridondante ma corretto.
   La junction `frontend/node_modules` e' ancora nel worktree (la toglie il coordinatore).
