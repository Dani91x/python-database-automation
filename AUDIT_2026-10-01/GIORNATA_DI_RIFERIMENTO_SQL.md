# Giornata di riferimento = giorno della partita (SQL), 01/10/2026

Delegato Opus del coordinatore admin-01. Migrazione:
`migrations/giornata_di_riferimento_giorno_partita_2026-10-01.sql` (NON applicata, la applica l'utente).
Nessuna scrittura sul DB: tutte le verifiche qui sotto sono letture REST (`select`) o chiamate a RPC
`STABLE` di sola lettura con la service role.

**Revisione 2 (stessa giornata, correzione del coordinatore)**: il ripiego al giorno di REGOLAMENTO è stato
tolto ovunque. L'ordine di ricerca del giorno di riferimento, per Omega, Safe e Mike, nel motore, in
`get_posizioni_chiuse_giornata` e in `get_storico_stake`, è:
1. inizio partita dalla catena di fonti → `giorno_da = 'partita'`;
2. altrimenti, se `minute_at_entry` non è nullo, `placed_at - minute_at_entry * interval '1 minute'`
   (inizio stimato dal minuto di gioco) → `giorno_da = 'partita'`;
3. altrimenti `placed_at` → `giorno_da = 'piazzamento'`.

Valori ammessi di `giorno_da`: 'partita' | 'piazzamento'. Il regolamento non decide mai il giorno.

## 1. Da dove viene il giorno, tabella per tabella (DB reale, 01/10)

Colonne lette con `select=*&limit=1` e dallo schema OpenAPI di PostgREST. `minute_at_entry` è `integer`
su `mike_trades`, `omega_trades` e `safe_strategy_trades`.

Righe REGOLATE (won/lost/void, aperture + chiusure), per fonte del giorno:

| Tabella | catena | minuto | piazzamento | totale |
|---|---|---|---|---|
| `mike_trades` (paper 365 + live 60) | 425 | 0 | 0 | 425 |
| `omega_trades` (paper) | 122 | 1 | 2 | 125 |
| `safe_strategy_trades` calcio (paper) | 85 | 101 | 3 | 189 |
| `safe_strategy_trades` tennis | 20 (18 paper, 2 live) | 0 | 127 (106 paper, 21 live) | 147 |
| `tennis_live_orders` 4 bot tennis | 17 | — | 0 | 17 |

**Fonti della catena:**
- Calcio (`inizio_partita_evento`): `mike_events.ko_at` → `min(omega_trades.kickoff)` → `omega_missions.kickoff`
  → `live_follow.open_date` → `omega_events.open_date`. Omega guarda prima il proprio `t.kickoff`.
- Tennis: `tennis_live_follow.open_date` → `tennis_markets.open_date`.

Tutte le fonti sono timestamptz con chiave `event_id` text. Sono tutte PK tranne `omega_trades`, e tu hai
verificato che nessun `event_id` è duplicato. Fonti in disaccordo sullo stesso evento: **0**.

**Reperti:**
- **Safe tennis** non scrive né l'inizio partita né `minute_at_entry`: 127 righe su 147 vanno a piazzamento.
  Per chiuderlo, il servizio Safe dovrebbe scrivere l'inizio partita. È fuori perimetro e va deciso.
- **Mike, minuto 0**: 43 righe hanno `minute_at_entry = 0` (pre-partita). Non incidono, perché Mike è
  coperto al 100% dalla catena. Su un bot senza catena, la stima con minuto 0 darebbe il giorno di
  piazzamento come inizio.

## 2. Cosa cambia per ogni RPC

| RPC | Prima | Dopo |
|---|---|---|
| `trading_daily_history` | 'placed' / 'settled' | + **'event'** (§2.1) |
| `trading_day_trades` | 'placed' / 'settled' | + **'event'** (§2.2) |
| `get_omega_daily` / `get_omega_day_trades` | 'placed' | 'event': cambia solo l'argomento (+ commento) |
| `get_safe_daily` / `get_safe_day_trades` | 'placed' | 'event': cambia solo l'argomento; i `DROP` del 13/09 non sono stati ricopiati |
| `get_mike_daily` / `get_mike_day_trades` | 'settled' | 'event': cambia solo l'argomento (+ commento) |
| `get_storico_stake` (presente sul DB, POST = 200) | piazzamento | partita (catena, poi minuto), ripiego piazzamento (§2.3) |
| `get_posizioni_chiuse_giornata` | gamba regolata nel giorno | giorno di riferimento della radice (§2.4) |
| `get_tennis_bot_daily` | giorno partita | **non toccata** |

Firme, `SECURITY DEFINER`, `search_path`, REVOKE/GRANT sono identici.

**Basi** (corpi copiati):
- `storico_esito_a_zero_2026-09-26.sql`
- `mike_history_v2.sql`
- `storico_sport_2026-09-17.sql`
- `safe_strategy_paper_live_2026-09-13.sql`
- `mike_storico_giorno_regolamento_2026-09-29.sql`
- `posizioni_chiuse_giornata_2026-09-24.sql`

**Aiutanti nuovi:**
- `inizio_partita_evento(event_id, sport)`: la catena di fonti;
- `inizio_partita_sql(tabella, alias)`: catena più stima dal minuto, come testo SQL; tabella e alias sono
  in lista bianca;
- `posizioni_chiuse_tabella_partita`.

### 2.1 'event' in `trading_daily_history`
- La posizione INTERA va al giorno di riferimento della sua apertura: piazzamento (`trades_placed`,
  `max_liability`, `hedged_closed`, first/last_trade_at), P&L, V/P, chiusure, commissioni.
- Le chiusure prendono il riferimento della loro apertura diretta; a ripiego, il piazzamento dell'apertura.
- I candidati si cercano da 7 giorni prima a 7 giorni dopo, poi il filtro resta per giorno.
- In 'placed' e 'settled' il comportamento è identico a prima: l'inizio non si calcola (`NULL`).

### 2.2 `trading_day_trades` in 'event'
- Restituisce le aperture il cui giorno di riferimento è il giorno chiesto.
- Aggiunge 3 chiavi per riga, solo in 'event':
  - `giorno_partita` (YYYY-MM-DD; NULL se `giorno_da='piazzamento'`);
  - `giorno_da`;
  - `in_day` (il riferimento cade nel giorno: sempre true nelle righe restituite).
- Nessuna chiave tolta.

### 2.3 `get_storico_stake`
`op_day` = giorno di riferimento (catena, poi minuto, poi piazzamento). È la stessa regola di `placed_day`
nel motore, quindi il ROI divide grandezze dello stesso giorno. Firma e uscita sono invariate.

### 2.4 `get_posizioni_chiuse_giornata`
- Un ciclo entra se il giorno di riferimento della RADICE cade nel giorno e almeno una gamba è regolata
  (`settled_at` o `pnl_betfair_settled_at`), in qualunque momento.
- Per i 4 bot tennis il riferimento è `coalesce(tennis_live_follow.open_date, placed_at)`, solo per gli ordini regolati.
- Uscita invariata.
- Chiavi per riga: `giorno_partita`, `giorno_da`, `in_day` (sempre true: il ciclo intero è del giorno);
  solo per il tennis anche `event_name` (17 su 17 risolti da `tennis_live_follow`).
- **Divergenza nota**: `get_tennis_bot_daily` ripiega su `settled_at`, non su `placed_at`. Conta solo per
  ordini senza `tennis_live_follow`, oggi 0. Non l'ho toccata.

## 3. P&L live: `pnl` contro `pnl_betfair`
Righe live regolate con `pnl_betfair`:
- Mike: 10 su 60, 0 differenze (1,88 = 1,88);
- Omega: 0 righe live;
- Safe: 23 regolate live, nessuna con `pnl_betfair`.

Il motore resta su `pnl`. Su Safe la verifica è vuota, non positiva.

## 4. Le 5 aperture Mike `void` con `settled_at` NULL
4780, 4812, 4819, 4821 live e 4777 paper, tutte partite del 15/09, pnl 0. Con 'event' vanno al 15/09 per
catena (`mike_events.ko_at`).

Contano come **void** (V 0, P 0, `void` +1 ciascuna, P&L 0), mai come vinte o perse.

Cella Mike live del 15/09:

| | piazzati | settled | V | P | void | P&L |
|---|---|---|---|---|---|---|
| prima (RPC viva) | 4 | 0 | 0 | 0 | 0 | 0 |
| dopo (modello) | 4 | 4 | 0 | 0 | 4 | 0 |

**Da sapere**: il contatore `settled` del motore include i void per definizione, già oggi e per ogni void
(`settled = count(trade_tot)`). Quindi queste 4 righe entrano anche in `settled`. Se le si vuole fuori da
`settled`, bisogna cambiare la definizione del contatore per tutti i void. Non l'ho fatto: decisione tua.

## 5. Tennis: coerenza col criterio
- `get_tennis_bot_daily` è coerente, salvo il ripiego (§2.4).
- RPC tennis di posizioni e ordini usate da `frontend/src/lib/tennis.ts`: corpi non letti
  (`pg_get_functiondef` non è disponibile via REST). Sono stato corrente, non attribuzione a una giornata.
  Unica da controllare: `get_tennis_bot_orders_today`.

## 6. Frontend da adeguare (NON toccato)
1. `dailyHistory.ts:525-540`: `attributionOf`.
2. `dailyHistory.ts:649` e `:673`: il dettaglio giornata e la liability devono filtrare con `in_day`.
   Altrimenti il 30/09 la cella dice +1,88 e il dettaglio 0.
3. `posizioniChiuse.ts:82-244`: oggi rifiltra per giorno di regolamento; deve usare `in_day` / `giorno_da`.
4. `chiuseGiornata.ts:66`: deve passare `o.event_name` a `rigaDaOrdineTennis`.
5. `provaGiornata.ts:9-26`: i commenti dicono che il live resta per regolamento e che Safe e Mike non hanno
   l'inizio partita. Ora ci sono `giorno_partita` e `giorno_da` ('partita' | 'piazzamento').

## 7. Test di accettazione (30/09, Mike live)
Eventi:
- 36132117 Follo v Sarpsborg (ko 14:00Z);
- 36130526 FC Vsetin v Bohemians 1905 (ko 13:30Z);
- 36134898 FC Farul Constanta (W) v Sparta Prague (W) (ko 14:00Z).

Regolati il 01/10 fra 07:00:48Z e 07:00:52Z.

| | Prima (RPC vive lette oggi) | Dopo (modello, nuovo ripiego) |
|---|---|---|
| `get_mike_daily` 30/09 | P&L 0, 5 piazzati, 0 regolati | **P&L +1,88, 5 piazzati, 5 regolati (2V 3P, 0 void)** |
| `get_mike_daily` 01/10 | P&L +1,88, 5 regolati (2V 3P) | **nessuna riga** |
| `get_mike_day_trades` 30/09 | — | 6 aperture (5083 error, 5085, 5087, 5090, 5091, 5094), `in_day=true`, `giorno_da='partita'`, `giorno_partita='2026-09-30'` |
| `get_mike_day_trades` 01/10 | — | 0 righe dei tre eventi |
| Posizioni chiuse 30/09 / 01/10 | 0 / 14 righe | **14 / 0 righe** |
| `get_storico_stake` | 26,37 il 30/09, 5 piazzati | invariato |

**Il modello Python** (`modello3.py`) è indipendente dalla migrazione e applica il nuovo ripiego:
- **Validazione nei criteri attuali** ('placed' per Omega e Safe, 'settled' per Mike): riproduce le RPC vive
  **con 0 giorni discordanti** su tutto 01/09–01/10. Vale per Omega paper (10 giorni), Safe paper (9),
  Safe live (5), Mike paper (8), Mike live (4); controlla P&L, piazzati, regolati, V, P e void.
- **Previsione 'event'**: P&L totale invariato per ogni bot e modalità. Giorni che cambiano:
  Safe paper 2, Mike paper 8, Mike live 3, Omega 0, Safe live 0.
- **Regolate nella finestra**: crescono solo per le aperture void con `settled_at` NULL (Mike paper 254 → 255,
  Mike live 7 → 11): sono esattamente le 5 aperture del §4.

Le query SQL esatte sono nell'intestazione della migrazione.

## 8. Verifiche eseguite
- **(a)** Ogni `rpc('...')` di `dailyHistory.ts` e `chiuseGiornata.ts` è ridefinita nella migrazione:
  le 6 RPC di storico, `get_storico_stake` e `get_posizioni_chiuse_giornata`.
- **(b)** sqlfluff e pglast non ci sono nel `.venv`. Ho usato pglast 8.4 installato con `pip --target` in
  una cartella temporanea del worktree e poi rimosso.
  - `parse_sql` di tutto il file: 39 istruzioni, OK;
  - `parse_plpgsql` delle 13 funzioni: OK;
  - i 4 blocchi di SQL dinamico espansi per 3 tabelle × 2 criteri e analizzati: OK. L'espressione
    dell'inizio è riprodotta a mano nello script di verifica: il testo esatto prodotto dal `format()` di
    `inizio_partita_sql` si vede solo sul server;
  - un REVOKE e un GRANT per ogni funzione;
  - falsificazione: 7 mutazioni, 7 rosse.
- **(c)** Diff dei corpi contro le migrazioni di origine:
  - le 6 RPC di storico cambiano solo l'argomento (più commenti);
  - motore, stake e posizioni cambiano solo nelle righe marcate «EVENT 01/10» o descritte al §2.

## 9. Cosa NON ho potuto verificare
- **Compilazione ed esecuzione lato server**. pglast non risolve nomi, tipi, `$n` e funzioni. In particolare:
  - `tennis_markets.player1->>'name'`;
  - `date - 7`;
  - la concatenazione dei due letterali adiacenti nel `format` di `inizio_partita_sql`;
  - `integer * interval`.
- **Corpi vivi uguali alle migrazioni di origine**: il modello che riproduce le RPC vive è un indizio, non una prova.
- **EXPLAIN** in 'event' e **proprietario** delle funzioni.
- **Corpi delle RPC tennis** di posizioni e ordini.
