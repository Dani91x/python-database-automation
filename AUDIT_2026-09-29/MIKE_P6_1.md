# CANTIERE MIKE-APP - Pacchetto P6, blocco 1: testi delle uscite, parametri, esito dell'ordine (29/09/2026)

Base: `94e165c` (nessun file di `frontend/` o `migrations/` cambiato fino a master `83c999b`).
Patch: `AUDIT_2026-09-29/MIKE_P6_1.patch` - verificata con `git apply --cached --check` su un
indice temporaneo = master `83c999b`: applica pulita. Nessun commit, indice del worktree intatto.

## 1. Cosa e' cambiato (file e righe, numeri del file nuovo)

| File | Righe | Cosa |
|---|---|---|
| `frontend/src/lib/mike.ts` | 509-511 | hint di `uscite_automatiche`: «governa solo le uscite in PERDITA ... Le uscite in PROFITTO (...) le esegue Mike da solo in ogni caso». Tolto «cap perdita partita» |
| `frontend/src/lib/mike.ts` | 533, 535-537 | `reentry_enabled` «con 1 o 2 gol»; `reentry_max_goals` max 1 -> **2**, hint nuovo |
| `frontend/src/lib/mike.ts` | 546-549 | `event_loss_cap_pct`: etichetta «Cap perdita per partita % (NON ATTIVO)», hint con la spiegazione (decisione 18). Limiti e valore di serie INVARIATI |
| `frontend/src/lib/mike.ts` | 592 | `MIKE_PARAM_DEFAULTS.reentry_max_goals` 1 -> **2** |
| `frontend/src/lib/mike.ts` | 930-949 | NUOVI `MIKE_ESITO_ORDINE_LABEL` e `esitoOrdineMike()` (M8.13) |
| `frontend/src/lib/interruttori.ts` | 1105-1107, 1138-1140 | `NOTA_USCITE_MIKE`; `statoUscite` di Mike porta la nota «governa solo le uscite in perdita; le uscite in profitto le esegue Mike» (si legge accanto a «uscite: MANUALI, approvi tu» nella riga di Mike in Control Room). Solo il ramo `mike` |
| `frontend/src/components/trading/EventPnlTable.tsx` (CONDIVISO) | 154-156, 183 | nuovo gancio FACOLTATIVO `statoLabel` in `RigheLabels`: se restituisce una stringa sostituisce la parola dello stato. Nessun altro bot lo passa: per loro identico a prima |
| `frontend/src/components/mike/MikeEventPnlTable.tsx` | 36, 71-72 | Mike passa `statoLabel: esitoOrdineMike` |
| `frontend/src/components/controlroom/PropostaUscitaMike.tsx` | 8-11 | solo il commento di testa (le uscite in profitto non arrivano piu' come proposta; le categorie restano per le proposte vecchie). Nessuna riga di codice cambiata |

Punto 3 - dove stavano i testi delle uscite manuali di Mike: hint del parametro (pannello
Parametri di Mike e della Control Room, stesso componente) e riga «uscite:» della plancia. Il
componente comune `InterruttoreUscite.tsx` NON e' toccato: la nota viaggia nel suo campo `nota`
gia' esistente (stesso meccanismo dello scalper). Le categorie `green_pre`, `ko_green`,
`reentry_green` in `PropostaUscitaMike.tsx` restano (una proposta vecchia salvata si legge).

Punto 5 (M8.13) - stringhe identiche a `Betfair/mike/service.py` `ESITO_*` di master `a919314`
(verificato con `git show master:Betfair/mike/service.py`). Dove: scheda Operazioni e schede
Risultati Pre-Match/Live (tabella per partita -> ciclo -> gamba): la gamba `error` con
`meta.esito_ordine` mostra «ritirato da Mike» / «rifiutato da Betfair» / «non abbinato: tutto o
niente» / «cancellato da Betfair» / «fermato da un nostro blocco» AL POSTO di «ERRORE»; senza
la chiave (righe vecchie) o con un valore ignoto resta «ERRORE».

## 2. Test nuovi
`frontend/src/components/mike/MikeP6Blocco1.test.tsx`, 7 test: i 5 esiti; chiave assente /
valore ignoto / stato non `error` = nessuna frase; tabella vera montata (riga con esito ->
frase, riga vecchia -> ERRORE); `event_loss_cap_pct` NON ATTIVO con limiti invariati;
`reentry_max_goals` 0-2 serie 2 (anche `mergeMikeParams` non riporta piu' 2 a 1); hint
dell'interruttore; nota nella riga della Control Room (e Omega senza nota).
Finti: righe `mike_trades` con le chiavi di `MikeEventPnlTable.test.tsx`, parametri come
`mike_control.params`.

## 3. Test esistenti modificati
| Test | Prima | Dopo | Decisione |
|---|---|---|---|
| `src/lib/interruttoriUscite.test.ts` «Mike: assente = manuali ...» (5 asserzioni) | `{ automatiche: X }` | `{ automatiche: X, nota }` + un'asserzione in piu' (parametri non letti = nessuna nota) | decisioni 13 e 16 del piano (P1): l'interruttore di Mike governa solo le uscite in perdita |

Nessun test cancellato o saltato.

## 4. Comandi e numeri
- `npx vitest run src/components/mike src/lib/interruttoriUscite.test.ts src/lib/mike.test.ts
  src/components/controlroom/PannelloBotUscite.test.tsx src/components/controlroom/InterruttoreUsciteSchede.test.tsx
  src/components/trading` -> **26 file, 418 test verdi** (la cartella `components/trading`
  comprende i test di `EventPnlTable`, `DayDetail`, `StatoOrdine.montaggio` di Omega/Control Room).
- `npx tsc -p tsconfig.app.json --noEmit` -> **0 errori**.
- Contratto Python `test_mike_certificazione_ui_2026_09_11.py`: **39 verdi, 1 rosso ATTESO**:
  `reentry_max_goals: max UI 2.0 != 1` (il `config.py` di master dice ancora 1/0-1; lo porta a
  2/0-2 l'altro delegato). Rilanciato con il SOLO `PARAM_SPEC['reentry_max_goals']` portato a
  `(2, int, 0, 2, None)` in memoria (plugin pytest in scratchpad, nessun file del repo
  toccato): **40/40 verdi**. Quindi, integrato il config dell'altro delegato, il contratto torna verde.
- Suite intera NON lanciata (regola del carico: la lancia il coordinatore).

## 5. Falsificazione (`AUDIT_2026-09-29/mike_p6/falsifica_mike_p6.mjs 1`, copia in memoria + sha256 nel finally)
| Mutazione | Esito |
|---|---|
| M1 frase dell'esito sbagliata | ROSSO (2) |
| M2 esito letto anche con stato non `error` | ROSSO (1) |
| M3 la tabella ignora `statoLabel` | ROSSO (1) |
| M4 cap perdita presentato come attivo | ROSSO (1) |
| M5 `reentry_max_goals` massimo 1 | ROSSO (1) |
| M6 default `reentry_max_goals` 1 | ROSSO (1) |
| M7 nota dell'interruttore tolta | ROSSO (2, anche il test esistente aggiornato) |
| M8 testo vecchio dell'interruttore | ROSSO (1) |
Ripristino: hash identici, `git diff --stat` uguale prima e dopo, nessuna traccia delle mutazioni.

## 6. Cosa NON ho potuto verificare / non fatto
- Il test di contratto Python `test_contratto_meta_di_riga_lette_dalla_tabella_trade` guarda
  solo `meta.xxx` scritto dentro `MikeEventPnlTable.tsx`: la lettura di `esito_ordine` sta in
  `lib/mike.ts` (come `exitInfo` sta in `lib/dailyHistory.ts`), quindi quel contratto NON la
  vede. Proposta per chi tocca il Python: aggiungere `esito_ordine` al controllo (oggi il
  servizio su master lo scrive: `meta["esito_ordine"]`).
- `meta.lapse_status_reason_code` (P4 blocco 1) non e' mostrato: la frase «cancellato da
  Betfair» basta al trader; se si vuole il codice, va in un tooltip (blocco successivo).
- Nella Control Room (Posizioni chiuse, dettaglio riga) l'esito dell'ordine non e' mostrato:
  quelle viste sono comuni a tutti i bot e non mostrano oggi gli ordini `error` di Mike come riga
  a se'. Lo storico (DayDetail) idem. Mostrato dove la pagina di Mike mostra un ordine in errore.
- Etichette e spiegazioni nuove di P2 (HOLD, ultimo ingresso, `last_entry_ticks_above` non
  attivo, veto) e le attivita' di P4 blocco 2: NON in questo blocco, perche' P2 e P4 blocco 2
  non sono su master; le preparo in un blocco a parte da applicare insieme a loro (vedi
  messaggio del coordinatore).

## 7. Campi che servirebbero dal bot
Nessuno per questo blocco.

## 8. Da controllare dal vivo in paper
- Pannello Parametri di Mike: «Cap perdita per partita % (NON ATTIVO)» con la spiegazione;
  «Gol max per il re-ingresso» accetta 2 (se il valore salvato sul DB e' 1, resta 1 finche' non
  lo cambi tu: il pannello mostra il valore SALVATO).
- Control Room, riga di Mike: «uscite: MANUALI, approvi tu (governa solo le uscite in perdita;
  le uscite in profitto le esegue Mike)».
- Scheda Operazioni: un ordine ritirato mostra «ritirato da Mike» invece di «ERRORE».
