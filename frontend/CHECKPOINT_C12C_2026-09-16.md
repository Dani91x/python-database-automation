# CHECKPOINT C.12c — UI: chiusure dell'utente, proposte Omega, parametri V3 (16/09/2026)

> Delegato C.12c (Opus 5). Solo `frontend/` + il file di contratto
> `Betfair/omega/test_omega_ui_contratto_2026_09_11.py`.
> Nessun commit, nessun `git add`, app mai avviata.
>
> ORDINI DELL'UTENTE che questo lavoro serve (16/09 sera):
>   1. «se chiudo io il bot deve saperlo e non fare altro»;
>   2. «il green-up/cash-out passa dalla Control Room come proposta con avviso
>      e decido io».

## Stato
- [x] Punto 0 — lettura documenti e mappa dei file
- [x] Punto 1 — SAFE: cash out globale, badge «chiusa da te», Riprendi, etichette, due numeri di rischio
- [x] Punto 2 — OMEGA: etichetta, Riprendi, liability conto/bot, `conto_every_s`, parametri V3, proposte di uscita
- [x] Punto 3 — esenzioni tolte dai contratti (Python + contratto TS equivalente)
- [x] Punto 4 — test + falsificazioni + suite

---

## 1. SAFE — «se chiudo io, il bot deve saperlo»

| Cosa | Dove |
|------|------|
| Logica pura condivisa (marcatore, stato per evento, payload, motivi) | `frontend/src/lib/chiusuraUtente.ts` (NUOVO) |
| Gesto «Cash out globale della partita» + badge + «Riprendi» | `frontend/src/components/controlroom/CashOutPartita.tsx` (NUOVO) |
| RPC: `safe_request('cashout_event'\|'riprendi_evento', {event_id})` | `frontend/src/lib/safeBot.ts` (`cashOutEvento`, `riprendiEventoSafe`) |
| `SafeRequestKind` esteso ai due kind nuovi | `frontend/src/lib/safeBot.ts:261` |
| Montaggio in CONTROL ROOM (scheda partita live) | `SchedaPartita.tsx` (prop `safe`) ← `ControlRoom.tsx` (`ElencoPartite`, scheda «Live») |
| Montaggio nella PAGINA SAFE (scheda partita = `renderDettaglio`) | `pages/SafeStrategy.tsx` (`statoChiusuraSafe`, `cashOutPartita`, `riprendiPartita`) |
| Badge «chiusa da te» sulla RIGA (da `meta.chiuso_dall_utente`) | `SchedaPartita.tsx` (`MarcatoreRiga`) |
| Etichette dei kind `chiuso_dall_utente` · `posizione_di_conto` · `riprendi_evento` | `components/safestrategy/safeActivity.ts` |
| Motivo `partita_chiusa_dall_utente` + verdetti della lettura di conto | `safeActivity.ts` (`REASON_IT`, `VERDETTO_CONTO_IT`) |
| Pannello rischio a DUE numeri (`daily_liability` conto · `daily_liability_bot` · `cap_solo_automatico`) | `components/safestrategy/RiskPanel.tsx` |
| Stato/gesti nel modello di vista | `components/controlroom/useControlRoom.ts` (`statoChiusura`, `cashOutEvento`, `riprendiEvento`) |

Regole rispettate: il payload porta **solo** `event_id` (quali righe chiudere lo
decide il servizio); doppia conferma quando la modalità non è `paper`
(fail-closed: una modalità non dichiarata chiede conferma comunque); la barra
del rischio misura il numero **del bot**, e quando il servizio non lo pubblica
si scrive `—`, mai `0,00 €`.

## 2. OMEGA

| Cosa | Dove |
|------|------|
| Etichetta `chiuso_dall_utente` (+ `evento_ripreso`), CRITICAL | `frontend/src/lib/omega.ts` (`OMEGA_ACTIVITY_EXTRA`) |
| RPC `omega_evento_riprendi` e `omega_eventi_chiusi_dall_utente` | `frontend/src/lib/omega.ts` (`omegaEventoRiprendi`, `fetchOmegaEventiChiusi`) |
| Elenco + bottone «Riprendi» | `components/omega/PartiteChiuseDallUtente.tsx` (NUOVO), montato in `pages/Omega.tsx` |
| Testata: `open_liability` (conto) accanto a `open_liability_bot` | `pages/Omega.tsx` (tile «Liability aperta», `data-testid="omega-liability-bot"`) |
| `conto_every_s` nel foglio parametri (gruppo «Respiro del database», 0–3600, default 120) | `lib/omega.ts` (`OMEGA_PARAM_GROUPS`, `OMEGA_PARAM_DEFAULTS`) |
| I parametri V3 + `strategy_version` (gruppo «Motore v3 — IN OMBRA, non decide nulla») | `lib/omega.ts` — default e limiti presi da `omega_config._SPEC`, nessuno inventato |
| Proposte di uscita di Omega (modello Safe) | `lib/omegaProposte.ts` + `components/controlroom/SchedaChiusuraOmega.tsx` (NUOVI), montate nel nastro di `ControlRoom.tsx` |

Avviso «v3 in ombra»: nel `note` del gruppo parametri, e `strategy_version`
default **2** (test dedicato: portarlo a 3 fa rosso).

Proposte: `get_omega_proposte` → `omega_request_approve(p_id)` /
`omega_request_ignore(p_id, p_reason)`, doppia conferma in live, `Chiudi ora`
spento quando il servizio NON propone (`motivo_codice ≠ blocca_il_profitto`) o
manca il prezzo/importo di chiusura. La scheda mostra insieme **blocchi adesso
/ tenere vale / se il punteggio regge** (memoria del 12/09).

## 3. Contratti tornati a mordere

`Betfair/omega/test_omega_ui_contratto_2026_09_11.py`:
- `_IN_ATTESA_DI_PANNELLO` **cancellata** (`conto_every_s`, `strategy_version`,
  i `v3_*` hanno tutti un campo, con default e clamp identici al servizio);
- `_KIND_IN_ATTESA_DI_UI` **cancellata** (`chiuso_dall_utente` ha l'etichetta);
- aggiunti al contratto delle `options` i due `select` nuovi
  (`v3_modello` = `C.V3_MODELLI_AMMESSI`, `v3_fusione_mercato`).

`Betfair/safe_strategy/tests/test_audit_2026_09_11.py`: **nessuna esenzione da
togliere** — il catalogo H-16 elenca già i tre kind nuovi e non guarda la UI.
Il controllo lato UI lo fa il contratto TS equivalente:
`frontend/src/lib/chiusuraUtente.contratto.test.ts`.

## 4. Prove

- `npx vitest run` → **2598 verdi** (2503 + 95 nuovi), 0 rossi, 30 skip, 143 file.
- `npx tsc -p tsconfig.app.json --noEmit` → **13 errori**, gli stessi di prima.
- `npm run build` → ok (4085 moduli, 1m10s).
- `python -m pytest Betfair/omega/test_omega_ui_contratto_2026_09_11.py
  Betfair/safe_strategy/tests/test_audit_2026_09_11.py
  Betfair/mike/tests/test_mike_certificazione_ui_2026_09_11.py -q` → **125 verdi**.

### File di test nuovi
`lib/chiusuraUtente.test.ts` (22) · `lib/safeBotChiusura.test.ts` (6) ·
`components/controlroom/CashOutPartita.test.tsx` (12) ·
`lib/omegaProposte.test.ts` (14) ·
`components/controlroom/SchedaChiusuraOmega.test.tsx` (10) ·
`components/omega/PartiteChiuseDallUtente.test.tsx` (6) ·
`lib/chiusuraUtente.contratto.test.ts` (11) · + 6 su `RiskPanel.test.tsx` e
5 su `ControlRoom.test.tsx`.

### Falsificazione — 4 mutazioni, 11 rossi, file ripristinati e riverificati
| # | mutazione | esito |
|---|-----------|-------|
| F1 | tolta l'etichetta `chiuso_dall_utente` da `SAFE_ACTIVITY_EXTRA` | 2 rossi (contratto TS) |
| F2 | tolto `conto_every_s` da `OMEGA_PARAM_GROUPS` | 1 rosso TS + **2 rossi pytest** |
| F3 | `payloadCashoutEvento` che lascia partire un `event_id` vuoto | 2 rossi |
| F4 | doppia conferma in live disattivata (`chiedeConferma = false`) | 4 rossi |

(F1 NON tocca il test Python di Safe: quel contratto guarda solo il catalogo del
servizio, non la UI. È il motivo per cui esiste il contratto TS.)

## 5. Cosa serve ancora — MIGRAZIONI DA APPLICARE (l'utente)

Finché non sono applicate i gesti esistono ma il **servizio rifiuta**, e la
pagina mostra il suo messaggio (mai un `disabled` muto, mai un elenco vuoto
silenzioso):

1. `migrations/safe_cash_out_globale_e_cap_automatico_2026-09-16.sql` — senza,
   `safe_request` risponde «kind non valido: cashout_event» sui due bottoni
   Safe, e `risk.daily_liability_bot` non arriva (il pannello scrive «—»).
2. `migrations/omega_chiuso_dall_utente_2026-09-16.sql` — senza,
   `omega_eventi_chiusi_dall_utente()` e `omega_evento_riprendi()` non
   esistono: il riquadro «Partite che hai chiuso tu» dichiara l'errore.
3. `migrations/omega_proposte_uscita_2026-09-16.sql` — senza,
   `get_omega_proposte()` non esiste: il nastro dichiara perché non mostra
   uscite di Omega.

Altri seguiti **non** di questo delegato:
- il raccordo v3 dentro `omega_service.py` (il pannello parametri c'è, ma è il
  servizio che deve scrivere le proposte in `omega_requests`);
- `get_safe_aggregates` non torna ancora le chiavi `_auto` (§3 della migrazione
  Safe): fino ad allora `cap_solo_automatico` è `false` e la pagina lo dichiara;
- Safe non pubblica un elenco di eventi chiusi in `stats`: la pagina lo ricava
  dal marcatore sulle righe, che è dove il servizio lo scrive.

## 6. Limiti dichiarati (⊘)
- Niente provato contro il database vero: nessuna RPC reale chiamata, tutte le
  prove sono su finti con le chiavi del vero.
- La scheda delle proposte di Omega non ha (ancora) il **prezzo vivo dal feed**
  come quella della Safe: il servizio non pubblica `market_id`/`selection_id`
  dentro un blocco che la pagina sappia prezzare per Omega. Si mostra la
  fotografia della decisione, e l'etichetta lo dice.
- `posizione_di_conto` e `riprendi_evento` hanno l'etichetta ma non un pannello
  dedicato: si leggono nel feed attività di Safe.
