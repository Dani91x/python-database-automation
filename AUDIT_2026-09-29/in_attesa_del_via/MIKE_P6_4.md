# CANTIERE MIKE-APP - Pacchetto P6, blocco 4: un solo criterio per il giorno (M8.10), 29/09/2026

Patch: `AUDIT_2026-09-29/MIKE_P6_4.patch`, sopra P6_1..P6_3 (verificato su master `83c999b` +
P6_1..3: `--check` pulito). Contiene anche la migrazione (solo SCRITTA, la applica l'utente).

## 1. Dove si decide il giorno dello Storico di Mike
- **Nel database**: `get_mike_daily` e `get_mike_day_trades` (versione viva:
  `migrations/mike_storico_per_modalita_2026-09-14.sql` + `..._fix_alias_2026-09-14.sql`)
  chiamano il motore comune con `'placed'` (giorno di PIAZZAMENTO).
- **Nel frontend**: `lib/dailyHistory.ts::attributionOf` (testo in testa allo Storico e filtro del
  dettaglio del giorno `summarizeDayTrades`) restituiva `'placed'` per tutti i bot.
- «Posizioni chiuse» (Control Room, `get_posizioni_chiuse_giornata`) conta il giorno di
  REGOLAMENTO. Scelta del coordinatore: regolamento ovunque.

## 2. Cosa e' cambiato
| File | Cosa |
|---|---|
| `migrations/mike_storico_giorno_regolamento_2026-09-29.sql` (NUOVO, da APPLICARE dall'utente) | `get_mike_daily` e `get_mike_day_trades` rifatte identiche a quelle vive, con `'settled'` al posto di `'placed'`. Stesse firme e permessi, `CREATE OR REPLACE`, nessun dato toccato. Il motore comune supporta gia' `'settled'` (e' il suo valore di serie). Omega e Safe non cambiano |
| `frontend/src/lib/dailyHistory.ts` | `attributionOf('mike')` -> `'settled'`; Omega e Safe `'placed'` come prima |
| `frontend/src/components/trading/TradingHistory.tsx` | il testo del criterio `'settled'` (usato solo da Mike): «P&L realizzato = posizioni REGOLATE nel giorno (chiusure incluse), come in «Posizioni chiuse»» |

**ORDINE DI APPLICAZIONE**: migrazione e patch INSIEME. Solo la patch senza migrazione: la cella
del calendario (dal DB) conterebbe ancora per piazzamento e il dettaglio per regolamento, quindi
sulle posizioni a cavallo della mezzanotte i due numeri non tornerebbero. Solo la migrazione
senza patch: calendario per regolamento, testo e dettaglio per piazzamento.

## 3. Test
- Nuovo `src/components/trading/StoricoMikeGiornoRegolamento.test.tsx` (3 test): attribuzioni
  per bot; una posizione piazzata ieri alle 23:30 e regolata oggi conta oggi nel dettaglio di
  Mike; la pagina dice il criterio.
- Modificato `src/lib/dailyHistory.test.ts` riga 420: `attributionOf('mike')` da `'placed'` a
  `'settled'` (decisione D10/M8.10). Nessun test cancellato.
- `npx vitest run src/components/trading src/lib/dailyHistory src/lib/storicoSport
  src/lib/chiuseGiornata src/pages/Mike src/components/mike` -> **29 file, 477 verdi, 1 saltato
  (preesistente)**; `tsc` 0 errori.
- Contratto Python: legge `mike_history_v2.sql` (non toccato): invariato.
- Falsificazione (`falsifica_mike_p6.mjs 4`): G1 Mike di nuovo per piazzamento ROSSO; G2 tutti per
  regolamento (Omega/Safe cambiati) ROSSO; G3 testo vecchio ROSSO.

## 3-bis. STATO: SOSPESO dal coordinatore (29/09 sera)
Non si integra finche' l'utente non sceglie il criterio e applica la migrazione. Patch e
migrazione restano come sono.

## 3-ter. Tabella per la decisione dell'utente: ogni numero della pagina, quale giorno conta
| Numero (dove si vede) | Fonte | Giorno che conta OGGI | Con la patch P6_4 + migrazione |
|---|---|---|---|
| «P&L oggi» (casella di testata) | `mike_aggregates_sql` `realized_today` (`migrations/mike_aggregati_per_modalita_2026-09-13.sql` riga 97-98: `pos_placed_at >= v_day`) | PUNTATA | PUNTATA (non toccato) |
| Barra della giornata (P&L, partite, operazioni, V/P) | stessi aggregati (`won_today`, `lost_today`, `cycles_today`, `events_today`, riga 122-130, `day_by = 'placed'`) | PUNTATA | PUNTATA (non toccato) |
| Scheda «Operazioni» e «Risultati Pre-Match/Live» | `get_mike_state` righe del giorno (`mike_bot_v2.sql` riga 176-192, `day_placed_at`) + `lib/mike.ts::tradeDayMs` | PUNTATA | PUNTATA (non toccato) |
| Scheda «Storico» (calendario, P&L del giorno, dettaglio del giorno) | `get_mike_daily` / `get_mike_day_trades` + `attributionOf` | PUNTATA | **REGOLAMENTO** |
| «Posizioni chiuse» (Control Room) | `get_posizioni_chiuse_giornata` (`posizioni_chiuse_giornata_2026-09-24.sql`: gamba regolata nel giorno) | **REGOLAMENTO** | REGOLAMENTO |
| «Storico calcio» (somma Omega + Safe + Mike) | `lib/storicoSport.ts` -> `get_mike_daily` | PUNTATA | Mike REGOLAMENTO, Omega e Safe PUNTATA |

Per avere UN criterio su tutta la pagina di Mike servirebbe anche una migrazione di
`mike_aggregates_sql` e `get_mike_state` (P&L oggi, barra, Operazioni). La differenza si vede
solo sulle posizioni piazzate prima della mezzanotte e regolate dopo (tipico: partite serali
del pre-partita). Esempio: puntata alle 23:30 del 28, partita finita all'01:15 del 29 con
+4,75 €. Per PUNTATA va nel 28; per REGOLAMENTO va nel 29.

## 4. NON verificato / NON fatto
- La migrazione NON e' stata eseguita (DB in sola lettura): verificata solo per confronto riga
  per riga col corpo vivo (unica differenza: `'placed'` -> `'settled'` nelle due chiamate).
  Le query di verifica sono in testa al file.
- **Restano per PIAZZAMENTO (decisione per il coordinatore/utente)**: i numeri di testata della
  pagina di Mike («P&L oggi», barra della giornata, scheda Operazioni: `get_mike_state` /
  `mike_aggregates_sql` con `day_by = 'placed'`, `lib/mike.ts::tradeDayMs`). Uniformarli
  richiede un'altra migrazione (`mike_aggregates_sql`, `get_mike_state`) e cambia cosa conta
  «oggi» nella pagina: non l'ho fatto senza conferma.
- La pagina «Storico calcio» (`lib/storicoSport.ts`) somma Omega, Safe e Mike per giorno: dopo la
  migrazione Mike vi entra per regolamento e gli altri per piazzamento (differenza solo a cavallo
  della mezzanotte). Scritto anche in testa alla migrazione.
