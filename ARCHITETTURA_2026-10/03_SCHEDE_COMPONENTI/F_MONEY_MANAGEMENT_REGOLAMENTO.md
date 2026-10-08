# SCHEDA F — Money management, regolamento e P&L (08/10/2026)

Autore: delegato Sonnet 5.5. Prefisso funzionalita': `F-`. Compito: solo documento, nessun codice toccato.
Precedenti usati e NON rifatti: `00_INVENTARIO.md` (relitti Sheets, righe), `C_PORTA_ORDINI.md` (riconciliazione ordini R1-R9),
`D_RUNTIME_BOT_CONTRATTO.md` (D-048), `E1_MIKE.md` (E1-048, stop nel servizio), `E2_OMEGA.md:399,415` (rimanda a F il regolamento
e propone `nucleo/contabilita_ordine`), `G_DATI_E_ALGORITMI_DEL_CLOUD.md` (G-017, G-044), `I_DESKTOP_PROCESSI_H24.md` (I-047, §1.4, §4.4),
`AUDIT_2026-10-04/PNL_UNICO.md` (le viste del 04/10 e la regola `per_posizione`), `AUDIT_2026-10-08/SPECIFICHE_CANTIERI_CLOUD_2026-10-08.md`
cantiere 10 (registro e riquadro P&L del REPLAY: fasi e conteggio cicli; qui non si contraddice, vedi F-051).

## Perimetro (righe con `wc -l`)

Il brief diceva «money_management.py e betfair_report_manager.py = money management». **Il codice dice altro** (§1, F-060/F-061): quei due file
(3.397 + 1.737 righe) sono il «Quant Fund» pre-partita su Google Sheets, non il money management dei bot di oggi. Il denaro vivo dei bot e'
nel runner (`reconcile_worker.py`), nello stop giornaliero e dentro i quattro servizi bot. Le righe del componente, per origine:

| Blocco | File / intervalli | Righe |
|---|---|---|
| Relitto Sheets | `Betfair/money_management.py` 3.397; `Betfair/betfair_report_manager.py` 1.737; `aggiorna_mm_sheets.py` 542; `aggiorna_solo_fogli.py` 46 | **5.722** |
| Conto e regolati del runner | `stream/reconcile_worker.py` saldo `:140-280` (~140) + regolati/P&L `:488-1250` (~760) | ~900 |
| Giornata e stop | `stream/trading/daily_pnl.py` 142; `stream/daily_stop_worker.py` 508 | 650 |
| Saldo a evento | `stream/saldo_evento.py` | 252 |
| Scritture DB del P&L | `stream/db.py:953-1118` (G-017) | ~190 |
| Mike | `mike/regolato_conto.py` 359 + regolamento in `service.py` 868 (E1) | 1.227 |
| Omega | `omega_service.py:4971-5424` 454 + `omega_engine.py:791-852` 62 (contabilita'/riconciliazione 338-790 restano in C) | 516 |
| Safe | `safe_strategy/execution.py:2686-3100` (~415) + `bot_service.py:1717-2380` (~660, stima dagli intervalli: parte e' in C) | ~700 |
| Scalper, tennis, paper | `media_under_bot.py:544-566`, `scalper_session.py:373`, `tennis_live_order_worker.py:447-480,1249-1290`, `live_trading_strategy.py:228` | ~170 |
| Frontend contabile (file interi, TETTO) | `composizioneConto.ts` 258, `composizioneObiettivo.ts` 571, `fontePnl.ts` 106, `eventGroups.ts` 387, `posizioniChiuse.ts` 1.051, `dailyHistory.ts` 1.285, `pages/LivePnl.tsx` 537, `anteprima/giornataBot.ts` 218, `replay-pnl.ts` 241 | 4.654 |
| **Totale perimetro** | backend vivo ~4.605 + frontend ~4.654 + relitto 5.722 | **~14.980** |

---

## 1. Oggi

### 1.1 Cosa NON e' (relitto, `git log -1`, importatori)
- `money_management.py` (ultimo commit 05/10/2026): «QUANT FUND — Money Management Engine v3.0», `SlotManager` `:263`, scanner Poisson/ML pre-partita, Kelly frazionato,
  report «Ven-Dom» su Google Sheets (`:1-14`); costanti `DEFAULT_BANKROLL=1000`, `DEFAULT_DAILY_TARGET=150`, `DEFAULT_STOP_LOSS_PCT=10`, `DEFAULT_KELLY_FRACTION=0.10`,
  `DEFAULT_MAX_STAKE_PCT=2.0`, `DEFAULT_COMMISSION_PCT=5.0` (`:45-56`). Importatori di produzione: **solo** `aggiorna_solo_fogli.py:20` e `aggiorna_mm_sheets.py:37`
  (`git grep`), entrambi manuali; nessun bot live lo importa. Scrive `signal_history` (`:2434`, `:2471`), legge `matches` (`:1399, 1522, 2167, 2270, 2330`).
  Stato su file `money_management_state.json` (`:58`): non tracciato (`git ls-files | grep -c` = 0), cancellato da `cleanup_reset.py:24`.
- **Ma e' ancora toccato dalla CI**: `.github/workflows/weekly_poisson_calibration.yml:5` (lunedi' 03:27 UTC) esegue `update_poisson_calibration.py --apply` (`:38-44`) che riscrive
  `CALIBRATION_TABLE` (`money_management.py:199`) e committa il file (`:60`). Quindi il file non si puo' cancellare senza spostare quella tabella (decisione D1).
- `betfair_report_manager.py` (ultimo commit 02/09/2026): `BetfairReportManager` `:66`, `gspread.service_account` `:71-72`, fogli «Prediction» `:368`, «Match Events» `:394`, «Segnali» `:850`;
  lancio manuale `aggiorna_report.bat:21`; legge `ai_model_registry` (`:1224, 1299, 1319, 1392`) e `matches` (`:1246`). Non e' avviato dall'app (`00_INVENTARIO.md:1986`).
- L'unico sizing con bankroll nel percorso live e' in `stream/engine/live_engine_pro.py:414-439` (`_kelly_back/_kelly_lay`) con `BANKROLL = LIVE_BANKROLL` default 100 (`config_stream.py:111`).
  `git grep -i bankroll Betfair/` fuori da `money_management.py` e test: 3 file (config_stream, live_engine_pro e un terzo non letto).

### 1.2 Chi chiama Betfair per il conto, e quanto spesso (richiesta del brief)
Nel codice di produzione **non c'e' nessuna chiamata a `getAccountStatement`** (`git grep`: solo la docstring generica `client.py:200`). Il conto si legge cosi':

| Chiamata | Chi | Cadenza | Fonte |
|---|---|---|---|
| `getAccountFunds` (saldo+esposizione) | runner: ciclo idle E BackgroundWorker, UN orologio condiviso | **20 s** fissi (3/min), qualunque modalita' | `reconcile_worker.py:96, 140-231, 268` |
| `getAccountFunds` | ogni processo bot via `saldo_evento.attiva(get_account_funds)`, dopo un evento d'ordine | a evento (frequenza NON misurata) | `omega_market.py:122-135`, `saldo_evento.py` |
| `listCurrentOrders` (ordini) | runner, solo LIVE | `RECONCILE_POLL_SEC` 30 s | `reconcile_worker.py:281, 1290-1327`; `config_stream.py:332` (I-047) |
| `listClearedOrders` groupBy MARKET (giornata di Roma) | runner, `_sync_cleared` ogni ciclo; `_leggi_mercati_regolati` con cache | cache 35 s regolare / 5 s forzato | `reconcile_worker.py:488-515, 624-625, 717` |
| `listClearedOrders` per ORDINE | runner, solo se la firma dei mercati cambia | giro ogni **300 s**, o forzato da cambio saldo (min 20 s) | `reconcile_worker.py:615, 627, 690, 1116-1150, 1229-1246` |
| `listClearedOrders` (+`marketIds`, tutto il conto) | **Mike** (propria lettura) | al regolamento di ogni partita (non misurato) | `mike/service.py:208-294, 5849, 6144-6171` |
| idem | **Omega** | idem | `omega_market.py:1633-1769`, `omega_service.py:3333, 4389` |
| idem | **Safe** | idem | `safe_strategy/bot_service.py:119-133, 1218, 2057-2088` |

Quindi 4 chiamanti indipendenti di `listClearedOrders` sullo stesso conto (runner, Mike, Omega, Safe), 3 client REST diversi (betfairlightweight del runner, `BetfairClient` JSON-RPC, `omega_market.call`: A-scheda). Nessuna di queste attese e' nel percorso stream→ordine (sono tutte
a valle o a cadenza), ma sono richieste duplicate sulla stessa risorsa.

### 1.3 Quanti calcoli di P&L esistono, e coincidono? (richiesta del brief)

**Backend — il realizzato di una posizione/partita viene calcolato in 6 posti distinti** (+ la regola paper):

| # | Dove (`file:riga`) | Cosa calcola | Lordo/netto | Coincide con la regola del conto? |
|---|---|---|---|---|
| B1 | `reconcile_worker.py:938` `componi_regolati` + `:747` `commissioni_per_ordine` | P&L reale del CONTO (tutti: bot e mano): `per_fonte`, `per_posizione`, `per_sport`, `netto` | netto = profit − quota commissione del MERCATO sui profit positivi, somma esatta al centesimo | **e' la regola** |
| B2 | `reconcile_worker.py:517` `_sync_cleared` -> `betfair_live_settled.profit` | profit per MERCATO, scritto da `db.py:953` | **LORDO** (la commissione sta solo nel gruppo, non nella colonna: `regolato_conto.py:11-13`) | stessa fonte, ma lordo |
| B3 | `trading/daily_pnl.py:49` `realized_pnl` (+`:71` `open_mtm`, `:104` `evaluate_daily_stop`) | `risk_state.total` dello stop giornaliero | somma di B2 = **LORDO** + MTM | **no, per costruzione**: il numero «Totale giornata» di `/live-pnl` e' lordo (PNL_UNICO.md §3 dice «NON verificato») |
| B4 | `mike/regolato_conto.py:114` `componi_regolato` (importa B1 a `:133, :206`) | P&L della partita di Mike (+ righe «utente», `:21-39`) | netto, STESSA funzione di B1 | **si'** (test `test_mike_pnl_reale_del_conto_2026_09_30.py`) |
| B5 | `safe_strategy/execution.py:2845-2878` (`_lordo_per_bet`, `_quote_commissione` importa B1 a `:2870`), `:2944` `settle_position` | P&L della posizione Safe | netto con B1 | **si'** (`test_pnl_netto_commissione_2026_09_30.py`) |
| B6 | `omega/omega_engine.py:815` `settle_pnl` (LAY vinto = `size*(1-c)`, per ORDINE), `omega_market.py:1599-1769`, `omega_service.py:4588` `_netto_di_conto` | P&L Omega | per-ordine / per-mercato misto; **il codice non importa `commissioni_per_ordine`** (grep: solo commenti `omega_market.py:1625, 1711`) | **non dimostrato**: test `omega/test_omega_pnl_netto_commissione_2026_09_30.py` esiste, non rieseguito |
| B7 | `scalper/media_under_bot.py:556-566` (`netto_da_lordo`: `lordo*(1-c)` solo se > 0, per CICLO), `scalper_session.py:373` `residuo_netto` | P&L scalper per ciclo | per-valore, NON per-mercato | **puo' divergere** su un green-up: stessa causa che `tennis_live_order_worker.py:1249-1262` documenta come bug del paper (back +10, lay −9 pagava 0,50 invece di 0,05) |
| P | `tennis_live_order_worker.py:462,1249` ; `daily_stop_worker.py:151` ; `live_trading_strategy.py:228` | P&L PAPER = `order.simulated.profit` di flumine; commissione di mercato ripartita (regola 28/09) | netto | paper: **paper e live mai sommati** (CLAUDE.md) |

Regola per-valore (commissione solo sull'utile del singolo valore) presente anche in: `safe_strategy/exits.py:193` `net_of_commission`, `omega_engine.py:265` `net_profit_if_win`,
`omega_v3.py:949` `profitto_bloccabile`, `mike/engine.py:1669`. Regola per-mercato (Betfair): solo B1. **Due regole per lo stesso numero** e' il «difetto 1 del catalogo»
(`regolato_conto.py:19-21`): oggi coincidono per costruzione solo dove si importa B1 (B4, B5).

**Frontend — il P&L si somma/ricompone in 8 posti** (nessuno ricalcola da Betfair; tutti leggono righe DB o `pnl_reale_oggi`):

| # | Dove | Cosa | Fonte dati |
|---|---|---|---|
| U1 | `composizioneConto.ts:82, 177, 217, 240` + `composizioneObiettivo.ts:304, 382` | tessere, composizione, conto per vista | `pnl_reale_oggi` (DB `betfair_live_account` + canale `account`) |
| U2 | `controlRoom.ts:1073` `realizzatoGiornata` | realizzato per modalita' e sport (live/paper separati, `:1060-1070`) | righe dei bot (somma lato client) |
| U3 | `posizioniChiuse.ts:742` `pnlChiuseDelGiorno`, `:582` `nettoOrdineTennis` | «Posizioni chiuse» | righe dei bot, giorno della PARTITA |
| U4 | `dailyHistory.ts:762` `settledClosesPnl` + RPC `get_omega_daily :270/339`, `get_safe_daily :293`, `get_mike_daily :412`, `get_*_day_trades :301/397/420`, `get_storico_stake :371` | storico giornate | SQL: `migrations/giornata_di_riferimento_giorno_partita_2026-10-01.sql:576, 680, 768` |
| U5 | `pages/LivePnl.tsx` | «P&L realizzato» (RPC `get_live_settled`, LORDO) e «Totale giornata» (`risk_state.total`) | B2/B3 |
| U6 | `eventGroups.ts:82, 162`, `scalperControlRoom.ts:565, 590`, `tennis.ts:1080, 1124`, `useControlRoom.ts:4279` | per evento, scalper, tennis | righe DB |
| U7 | `mike.ts:1057, 1313`, `MikeEventPnlTable.tsx:110`, `omega.ts:745`, `safeBot.ts:1063` | viste per bot + commissione per bot | servizi dei bot |
| U8 | `replay-pnl.ts:50, 58`, `replayOperazioni.ts:185, 659` | replay/backtest (display) | esito del banco |

Coincidenza dimostrata dal referto del 04/10 (`PNL_UNICO.md` §3): conto −5,15 netto = Mike −5,68 + a mano +0,53; barra, composizione, Posizioni chiuse (4 chiuse, 2V 2P) e plancia di Mike
coincidono. **NON verificate** (dichiarato nel referto, §7): `/live-pnl` «Totale giornata», `realized_today` della pagina Mike, DayBar di Omega e Safe.
Divergenza strutturale gia' nota: 3 voci usano il giorno della PARTITA (U3, U4) e il conto usa il giorno di REGOLAMENTO (`settled_date_range`, `reconcile_worker.py:496-499`).

### 1.4 Green-up e «chiusure perfette» (condizione 10 di `BRIEF_STANDARD_DELEGATI.md:45`)
La matematica di green-up e' calcolata in **UNA libreria condivisa piu' 6 copie**:
- Condivisa: `stream/trading/greenup.py:118` `compute_greenup` (132 righe, 118-249; il file ne ha 249) [corretto dal verificatore 08/10] chiamata da Mike (14 punti: `engine.py:997, 1071, 3742, 3755, 3791, 3817, 4045, 4418, 5097, 5111, 5201, 5239, 5263, 5291`),
  Safe (`execution.py:2264-2272`, 3 punti), runner (`live_order_worker.py:2330, 2627`), tennis (`tennis_live_order_worker.py:992`), `hedging.py` (2 punti). `git grep -c "compute_greenup("`: 5 file + 2.
- Copie: `scalper/scalper_bot.py:297` e `tennis_scalper/tennis_scalper_bot.py:164` (`compute_green`, **IDENTICHE**: `s04_funzioni_duplicate.tsv:254`, + `laboratorio/scalper_lab/scalper_bot_base.py:132`);
  `omega/omega_v3.py:949` `profitto_bloccabile`; `mike/engine.py:440` `locked_pnl_back`; `omega/liquidity_probe.py:239` `greenup_need`; `safe_strategy/execution.py:2283` `locked_pnl`;
  TypeScript: `ladderMath.ts:10` `lockedPnlAt`, `CashOutButton.tsx:67` `partialLockedPnl`, `cashOutPartita.ts:463` (706 righe), `MatchTradesTable.tsx:176` `closeNowPnl`, `DayDetail.tsx:66`.
- La formula e' la stessa: `locked = L + (W − L)/prezzo` (`ladderMath.ts:5-9`, `scalper_bot.py:297-320`; per il lay di Omega `s − s·L/B`, `omega_v3.py:955-958`; per il back di Mike `S(Pe/Pc − 1)`, `engine.py:440-442`).
  Derivazione algebrica mia: coincidono. **Non verificato numericamente** che tutte rispettino la condizione 10 (importo esatto al centesimo, mai gonfiato): il test che lo dimostra e' al §5.

### 1.5 Regole di stake / tetti / stop per bot (si inventariano, NON si toccano)
Valori di DEFAULT del codice (non i valori vivi nel DB `*_control`/`betfair_live_settings`: non letti):

| Bot | Parametro (default) | `file:riga` |
|---|---|---|
| Mike | `stake` 10,0 (0,5-500); `commission_pct` 5,0; `second_entry_stake_pct` 50; `daily_loss_stop` 50,0; `loss_exit_*`; `ht_loss_pct` 25; `h2_loss_pct` 25 | `mike/config.py:77, 78, 178, 318, 276-299`; uso `service.py:4120` |
| Omega | `min_stake` 0,5; `max_liability_per_match` 0; `daily_loss_cap` 0; `max_open_liability` 0; V3: `v3_stake_eur` 1,0, `v3_max_liability_per_leg` 95, `..._per_match` 190, `v3_max_open_liability` 1000, `v3_daily_loss_cap` 300; `commission_pct` 5; obiettivo `DEFAULT_DAILY_GOAL` 250 | `omega_config.py:13, 29-38, 225, 259-262`; uso `omega_service.py:1624, 1890-1906, 2502-2516, 7823-7846` |
| Safe | `daily_loss_stop`, `daily_liability_cap` (mai persistiti dalla UI: `_NEVER_PERSIST`); `commission_pct` | `bot_service.py:520, 614-620, 10400-10406`; `opportunity.py:149` |
| Scalper calcio | `media_stake` 10,0 | `scalper/media_under_bot.py:120, 320` |
| Stop di conto | `daily_loss_limit` (`betfair_live_settings`, > 0 altrimenti SPENTO) | `daily_stop_worker.py:124-138`, `daily_pnl.py:104` |
| Stream engine | `LIVE_BANKROLL` 100 (Kelly) | `config_stream.py:111`, `live_engine_pro.py:414-439` |
| Tennis (scalper/live) | non letti in questa scheda | - |

Tre implementazioni di «stop perdita giornaliera» (Mike, Omega, Safe) + quella di conto (`daily_stop_worker`): quattro, con basi di calcolo diverse (realizzato del bot vs somma lorda dei settled del conto).

### 1.6 Giornata e obiettivo
«Oggi» ha **4 definizioni** (le 3 di I-§1.4 + una): (a) giornata di Roma del REGOLAMENTO per conto e stop: `day_window_utc` `daily_pnl.py:129` (usata da `reconcile_worker.py:495, 696`, `daily_stop_worker.py:435` [corretto dal verificatore 08/10: era :424]);
(b) finestra mobile di 12 h di Omega `omega_market.py:257`; (c) data locale del PC `betfair_tennis_odds.py:311` [corretto dal coordinatore 08/10: era 310]; (d) giorno della PARTITA (Roma) per lo storico da 01/10: `dailyHistory.ts:636-650`, `romeDay :452`.
Cambio di giorno: nessun evento, ogni modulo ricalcola a ogni giro (I-§1.4); obiettivo Omega scritto una volta per giorno (`omega_service.py:5318-5332`, `omega_db.py:1041-1051` -> `omega_daily_goal`).

### 1.7 Tabelle lette/scritte (da `s03_matrice_tabelle.tsv`, verificate a campione)
| Tabella | Scrive | Legge |
|---|---|---|
| `betfair_live_account` (saldo, `manual_pnl_*`, `pnl_reale_oggi`) | `db.py:1004, 1055, 1086` | frontend `liveOrders.ts:981` + canale `account` |
| `betfair_live_settled` | `db.py:963` (da `_sync_cleared`; paper da `_sweep_settled`) | `daily_stop_worker.py:250`, `db.py:425` |
| `betfair_live_risk_state` | `db.py:978` | `liveOrders.ts:795` |
| `mike_trades`, `omega_trades`, `safe_strategy_trades` (+ `pnl_betfair`) | servizi dei bot e `db.update_pnl_betfair` (`db.py:1100`) | `reconcile_worker._proprietari :842` (una lettura per tabella), UI via RPC |
| `omega_daily_goal` | `omega_db.py:1045` | non letta da codice di produzione (matrice: 1 scrittore, 0 lettori) |
| `signal_history`, `matches`, `ai_model_registry` | Sheets-relitto `money_management.py:2434, 2471` | relitto |

---

## 2. Funzionalita'

Legenda: **[UI]** visibile in UI; **[P]** parametro editabile.

**Conto e saldo**
- F-001 Saldo/esposizione del conto ogni 20 s, write-on-change + publish a ogni lettura (`reconcile_worker.py:140-231`). [UI: freschezza «controllato N s fa», `liveOrders.ts:981`]
- F-002 Un solo orologio per due chiamanti (ciclo idle e BackgroundWorker): `run_account_sync_if_due :182`, `sync_account_worker :268`.
- F-003 Saldo a evento dopo un evento d'ordine/regolamento: `saldo_evento.py`, `annota_lettura_esterna :233`, `attiva_saldo_su_evento :248`, `omega_market.py:122-135`.

**Regolamento dal conto (autorita': il conto vince sempre, `reconcile_worker.py:42-51`)**
- F-004 Regolati per MERCATO -> `betfair_live_settled` (`:488, 517`, `db.py:953`), write-on-change per firma `(profit, bet_count)` `:534`.
- F-005 Cache e firma dei mercati regolati (`:717, 733`, cadenze `:615-627`).
- F-006 Regolati per ORDINE della giornata, paginati (`:690`, `_MAX_PAGES` `:70`).
- F-007 Classificazione dell'ordine: bot / sito / app dal ref (`:670, 354, 797, 806`).
- F-008 Proprietario per bet_id (letture DB una per tabella, solo bet_id nuovi) `_proprietari :842`.
- F-009 Commissione per ordine, regola Betfair per MERCATO (`:747`) — usata da Mike, Safe, runner.
- F-010 Composizione `componi_regolati :938`: `per_fonte` (chi ha piazzato), `per_posizione` (chi ne ha la posizione, regola 04/10), `chiusure_a_mano`, `per_sport` (`:919, 931`). [UI: tessere Calcio/Tennis, composizione, plancia]
- F-011 `manual_pnl_*` / `manual_app_pnl_*` netti, bucket (`:1116-1228`, `db.py:1011`). [UI: pannello manuale]
- F-012 `pnl_reale_oggi` su `betfair_live_account` + canale `account` con `pnl_letto_at` (`db.py:1074`, `:1190-1226`). [UI: barra di giornata, composizione]
- F-013 `pnl_betfair` sulle righe dei bot (`_scrivi_righe :1084`, `db.py:1100`). [UI: righe ordine]
- F-014 Cadenza: 300 s + giro forzato da cambio saldo/regolazione, minimo 20 s (`:1229-1246`).
- F-015 Report di ripresa all'avvio con regole armate orfane (`:1249`, C-069b).
- F-016 Riconciliazione ordini col conto (R1): in C, qui solo citata (`:359`).

**Giornata, stop, obiettivo**
- F-020 Finestra giornata Roma `day_window_utc` (`daily_pnl.py:129`).
- F-021 `realized_pnl :49`, `open_mtm :71` (worst-case se senza prezzi), `evaluate_daily_stop :104` (limite None/<=0 = SPENTO, mai falso scatto).
- F-022 Stop giornaliero di conto: `daily_stop_worker.py:413-508`, limite `daily_loss_limit` (`:124`) [P, `betfair_live_settings`], kill-switch `_activate_kill :357`, stato `_publish_state :318`. [UI: `/live-pnl` «Totale giornata»]
- F-023 Sweep paper dei settled (`_sweep_settled :167`: in LIVE non scrive, rileva solo il GAP) e lettura `_read_realized :242`.
- F-024 Stop per bot: Mike `daily_loss_stop` [P] (`mike/config.py:318`, `service.py:4120`, log una volta/giorno `:54`); Omega `daily_loss_cap`/`v3_daily_loss_cap` [P] (`omega_service.py:1624, 1904, 2513, 7828`); Safe `daily_loss_stop`, `daily_liability_cap` (`bot_service.py:617, 10400`).
- F-025 Obiettivo giornaliero Omega `daily_goal` [P] (default 250), `stop_on_goal` [P] (`omega_config.py:13, 33`; `omega_service.py:1890, 2502, 7846, 8388`; editor `obiettivoEditor.ts`, `ObiettivoEditor.tsx`, `MissionPanel.tsx`). [UI: `ObiettivoHero.tsx` DayBar]
- F-026 Target per partita derivato = `(obiettivo − realizzato)/partite utili`, dichiarato come ripiego (`controlRoom.ts:515-548`). [UI]
- F-027 Snapshot dell'obiettivo del giorno `_snapshot_daily_goal` (`omega_service.py:5321`, `omega_db.py:1041`).

**Regolamento nei bot**
- F-030 Mike: `componi_regolato` (`regolato_conto.py:114`), righe «utente» `utente-<bet_id>` (`:21-39`), `_leggi_regolato_conto` (`service.py:6144`), `_settle_trades :6403`, `_retry_settle_rows :6060`, `_marca_righe_non_regolate :6035`, `_settle_params :6088`, `settle_plan :1203`, `_netto_su_selezione :3071`.
- F-031 Mike, calcolo interno del motore (paper e CONFRONTO): `settle_legs :1608`, `settle_legs_by_market :1613`, `pnl_cicli_chiusi :1707`, `net_pnl_by_total :966`, `locked_pnl :1267`, `pnl_indipendente_dal_risultato :1130` (`engine.py`). Strategia: non si tocca.
- F-032 Omega: `settle_pnl omega_engine.py:815`, `resolve_settlement :794`, `realized_effective :565`, `locked_open_pnl :552`, `settle_open omega_service.py:4971`, `_settle_hedged :5106`, `_netto_di_conto :4588`.
- F-033 Safe: `settle_group :2692`, `settle_pair :2724`, `settle_row :2735`, `settle_position :2944`, `settle_orphan_closing :3063`, `_posizione_da_cleared :2879`, `_pnl_source_betfair :2930` (`execution.py`); `settle_open :2089`, `_stato_da_settlement_reale :1955`, `_settlement_needs_rest :1717` (`bot_service.py`).
- F-034 Scalper: P&L per ciclo `media_under_bot.py:544-566`, residuo `scalper_session.py:373`, `settled_orders` (`scalper_bot.py:756`, `sniper_bot.py:221`, `tennis_scalper_bot.py:649`), `pnl_worker run_tennis_scalper.py:141`.
- F-035 Tennis live e paper: `_pnl_ordine :462` (None se non regolato: «dato assente non e' zero», catalogo §7.21), `_commissione_mercato :447`, `_commissioni_per_ordine :1249`.
- F-036 Paper: `_settle_paper_market live_trading_strategy.py:228`.

**Green-up e chiusura**
- F-040 `compute_greenup greenup.py:118` (fraction, place_at_ticks, target_price, amount) + `FLAT_EPS`. Ordine unico di hedge; invio e place-and-trim in C.
- F-041 `hedging.net_open_pnl hedging.py:95`; `risk_engine.pnl_threshold_fires risk_engine.py:403` (regola a soglia di P&L; ordini in C).
- F-042 Safe: `close_plan execution.py:2228`, `locked_pnl :2283`, `_net_locked :1978`, `chiusura_abbinata :1933`.
- F-043 Cash-out di partita/globale (numeri; i click sono ordini, C): `cashOutPartita.ts:463`, `useCashOutPartita.ts:38`, `CashOutGlobale.tsx:430, 465`, `CashOutPartita.tsx:65`, `CashOutButton.tsx:130`, `MikeCashOutButton.tsx:51`. [UI]

**UI del denaro**
- F-050 Tessere sport, composizione, plancia, «Posizioni chiuse» con riga `cr-chiuse-conto` (`composizioneConto.ts`, `composizioneObiettivo.ts`, `SplitSport.tsx`, `PosizioniChiuse.tsx`, `ObiettivoHero.tsx`, `useControlRoom.ts`). [UI]
- F-051 P&L e registro del replay (display): `replay-pnl.ts:50, 58`, `replayOperazioni.ts:185, 659`, `RiepilogoPnlBot.tsx:32`. **Cantiere 10** modifica solo `replayOperazioni.ts::cicliOperativi` e il riquadro del replay (fasi, cicli del bot): in questa scheda resta li', fuori dal componente contabile live; il mio `Movimento` ha il campo `ciclo_bot` per non contraddirlo. [UI]
- F-052 Realizzato per modalita' e sport, live/paper mai sommati (`controlRoom.ts:1073`). [UI]
- F-053 Posizioni chiuse del giorno e stato V/P (`posizioniChiuse.ts:251, 582, 742`). [UI]
- F-054 Storico giornate per bot, giorno della PARTITA (`dailyHistory.ts:270-420, 452, 636-650, 762`; SQL `migrations/giornata_di_riferimento_giorno_partita_2026-10-01.sql`). [UI]
- F-055 Tennis: `tennis.ts:1080, 1124`, `useControlRoom.ts:4279`. [UI]
- F-056 Pagina `/live-pnl` (`LivePnl.tsx`, 537): realizzato lordo dichiarato + totale giornata. [UI]
- F-057 Per evento e scalper: `eventGroups.ts:82, 162`, `scalperControlRoom.ts:565, 590`; fonte del numero `fontePnl.ts:54-74`. [UI]
- F-058 Viste per bot: `mike.ts:1057, 1313`, `MikeEventPnlTable.tsx:110`, `omega.ts:745, 752`, `safeBot.ts:1063`, `SafeTradesTable.tsx:93, 106`. [UI]
- F-059 Ladder: `ladderMath.ts:10` (`lockedPnlAt`). [UI]
- F-059b `anteprima/giornataBot.ts` (218 righe): non letto.

**Stake e sizing**
- F-060 Stake/tetti/stop per bot: tabella §1.5 (inventario; strategia, intoccabile).
- F-061 Kelly e bankroll del motore stream (`live_engine_pro.py:414-439`, `config_stream.py:111`).

**Relitto Sheets / Quant Fund**
- F-070 `SlotManager` e scanner (`money_management.py:263`), costanti `:45-56`, `CALIBRATION_TABLE :199` (riscritta dalla CI del lunedi').
- F-071 `signal_history` (`:2434, 2471`).
- F-072 `BetfairReportManager` (`betfair_report_manager.py:66`): fogli Prediction/Match Events/Segnali, `RotatingFileHandler` `:6, 35-42`.
- F-073 `aggiorna_mm_sheets.py:37` e `aggiorna_solo_fogli.py:20`; `aggiorna_report.bat:21`, `aggiorna_report_veloce.bat:17`; istruzione UI `MatchesList.tsx:278`.

Totale: **60 funzionalita'** (F-001..F-073 con numerazione a gruppi).

---

## 3. Difetti strutturali

1. **Due regole di commissione**: per-mercato (B1, `reconcile_worker.py:747`) solo in B4, B5 e runner; per-valore in `exits.py:193`, `omega_engine.py:265`, `omega_v3.py:949`, `media_under_bot.py:561`, TS `CashOutButton.tsx:78`. Il paper del tennis aveva il bug del per-ordine (`tennis_live_order_worker.py:1249-1262`).
2. **Il numero dello stop e' lordo, quello del conto e' netto** (B3 vs B1): `risk_state.total` somma i profit lordi di `betfair_live_settled` (`daily_pnl.py:49`, `daily_stop_worker.py:250`); lo stop vede un perdente meno perdente di quanto sia (la commissione riduce solo gli utili). Entita' non misurata.
3. **Quattro «oggi»** (§1.6) e storico per giorno della partita contro conto per giorno di regolamento: un trade giocato alle 23:50 e regolato alle 01:40 sta in due giornate diverse nella stessa pagina (`dailyHistory.ts:658` vs `reconcile_worker.py:496-499`).
4. **Quattro stop-perdita giornalieri** (Mike, Omega, Safe, conto) con basi diverse e quattro punti di configurazione (§1.5).
5. **Quattro lettori indipendenti di `listClearedOrders`** sullo stesso conto (§1.2), con tre client REST; Mike, Omega e Safe rileggono cio' che il runner ha gia' composto (`pnl_reale_oggi`) per ricomporre la propria posizione.
6. **Green-up in 1 libreria + 6 copie Python/TS** (§1.4), `compute_green` doppione esatto in due file di bot (`s04_funzioni_duplicate.tsv:254`) + una terza copia in `laboratorio/`.
7. **Il nome mente**: `_sync_manual_pnl` (`:1116`) e' il giro dei regolati di tutto il conto; `money_management.py` non e' il money management dei bot (§1.1); il docstring in testa a `reconcile_worker.py:1-98` descrive ancora «A2 + A6» e non il P&L reale.
8. **Stato nel modulo**: `_LAST_*_SIG`, `_PROPRIETARIO_BET`, `_ADOTTATO_BET`, `_MERCATI_CACHE` (`reconcile_worker.py:90-96, 615-630`, `:842`): «il proprietario di un bet_id si risolve una volta per processo» (PNL_UNICO.md §2): al riavvio del runner si ricompone, ma l'ordine di scrittura Mike/runner e' un orologio implicito (caso 04/10: lettura 13:08, riga utente 13:19).
9. **Relitto in CI**: 3.397 righe di un sistema spento sono riscritte ogni lunedi' dal workflow e committate (`weekly_poisson_calibration.yml:38-60`).
10. **Il frontend ricompone** (U2-U4) dai dati delle righe invece di leggere una giornata gia' contabilizzata: le 8 somme del §1.3 sono la ragione per cui il 04/10 la tessera dava −10,75 e le Posizioni chiuse −5,68.

---

## 4. Domani

### 4.1 Struttura
UNA cartella `contabilita/` (nome: E2 dice `nucleo/contabilita_ordine`: da armonizzare dal coordinatore), UN contratto, UN `COSA_FA.md`. Contiene SOLO il denaro:
niente strategia, niente ordini (porta ordini = C), niente connessione (A: la lettura del conto passa per il client unico).

```python
# contabilita/contratto.py  -- tipi (chiavi identiche a quelle DB gia' scritte)
Modalita = Literal["live", "paper"]            # MAI sommate: la chiave di ogni aggregato
Sport    = Literal["calcio", "tennis", "altro"]
Fonte    = Literal["mike","omega","safe_calcio","scalper","tennis","manuale_sito","manuale_app"]

@dataclass(frozen=True)
class Movimento:            # un ordine REGOLATO (o simulato) -- l'unita' contabile
    bet_id: str; market_id: str; event_id: str|None; sport: Sport; modalita: Modalita
    fonte: Fonte; posizione_di: Fonte            # chi l'ha piazzato / di chi e' la posizione (regola 04/10)
    lordo: Decimal; commissione: Decimal|None    # None = commissione di mercato non letta -> niente netto finto
    netto: Decimal|None; regolato_at: datetime; partita_at: datetime|None
    ciclo_bot: int|None                          # per non contraddire il cantiere 10

@dataclass(frozen=True)
class Regolamento:          # esito della riconciliazione col conto, per mercato
    market_id: str; lordo: Decimal; commissione: Decimal|None; ordini: int; fonte: Literal["cleared","simulato"]

@dataclass(frozen=True)
class Giornata:             # LA giornata, definita in un solo posto (Europe/Rome, per PARTITA; regolamento come ripiego dichiarato)
    giorno: date; modalita: Modalita
    per_fonte: Mapping[Fonte, Quota]; per_posizione: Mapping[Fonte, Quota]; per_sport: Mapping[Sport, Quota]
    lordo: Decimal; commissione: Decimal; netto: Decimal; stop: StopStato; obiettivo: Obiettivo|None; letto_at: datetime

class Contabilita(Protocol):
    def registra_regolati(self, gruppi: Sequence[Regolamento], ordini: Sequence[OrdineRegolato]) -> Sequence[Movimento]: ...
    def giornata(self, giorno: date, modalita: Modalita) -> Giornata: ...
    def stop(self, giorno: date) -> StopStato: ...                 # una sola regola (netto), per bot e di conto
    def commissione(self, ordini, gruppi) -> Mapping[str, Decimal|None]: ...   # = commissioni_per_ordine, UNICA
    def green(self, w: Decimal, l: Decimal, prezzo: Decimal, **kw) -> PianoGreen: ...  # = compute_greenup, UNICA
# eventi esposti: MovimentoRegolato, GiornataAggiornata, StopScattato, ContoLetto(saldo, esposizione)
# eventi consumati: OrdineAbbinato/OrdineRegolato (dalla porta ordini C), CambioGiorno (dal supervisore I)
```

Dove vive ogni funzionalita': F-001..003 -> `contabilita/conto.py` (UN lettore del conto, 20 s, saldo anche a evento); F-004..016 -> `regolamento.py` + `attribuzione.py` (proprietari, per_posizione, per_sport) + `commissione.py`;
F-020..027 -> `giornata.py` (UNA `giornata()` e UNO stop; i parametri per bot restano nei bot e arrivano come `LimitiBot`); F-030..036 -> adattatori sottili `politica_<bot>.py` (~60-80 righe: cio' che e' strategia nel regolamento: separazione righe utente di Mike, `settle_legs` di confronto);
F-040..043 -> `green.py` (+ generazione TS dal contratto); F-050..059 -> `frontend/src/contabilita/` (selettori su `Giornata`, nessuna somma lato client); F-060 resta nei bot; F-070..073 -> archivio fuori dall'app (D1).

### 4.2 Un solo lettore, un solo consumatore (criterio §9.1 e §9.2)
- Il lettore `listClearedOrders` del conto e' UNO (nel componente); Mike, Omega e Safe ricevono `Movimento` gia' attribuiti invece di rileggere (togliendo le 3 copie §1.2). Cambiano i PUNTI DI INGRESSO, non le regole: la composizione per mercato e' `componi_regolati` com'e'.
- Il P&L reale del conto e lo storico delle giornate **restano alimentati dal cloud come oggi** (§9.2): `betfair_live_account.pnl_reale_oggi`, `betfair_live_settled`, `*_trades.pnl_betfair` e le RPC `get_*_daily` si scrivono dal postino asincrono (G) con la stessa forma; la giornata viva e' in memoria/canale locale (il percorso critico non attraversa la rete).
  Nessuna tabella persa; il controllo notturno del §4.3 verifica «non manca nulla».

### 4.3 Ciclo della giornata e regolamento notturno (§9.4)
- **00:00 Roma**: evento unico `CambioGiorno` (I-§4.4): `giornata()` apre il nuovo giorno; stop e obiettivo per bot si azzerano una volta; la UI ottiene la nuova `Giornata` senza ricalcolare.
- **Giornata = giorno della PARTITA (Roma)** per storico e per le viste; il conto resta per REGOLAMENTO (e' Betfair); `Giornata` porta entrambi i campi e dichiara il criterio (decisione D2: oggi sono 4 definizioni).
- **Regolamento notturno** (finestra senza partite in corso): `listClearedOrders` (`SETTLED` + `VOIDED`, finestra 72 h come `omega_market.py:1672`) contro i `Movimento` chiusi: differenze -> alert e riga di rettifica; vince il conto (regola di `reconcile_worker.py:42`). Idempotente.
- Il ricambio igienico dei servizi: guardia `solo_se_flat` (I-§4.4), invariata.

### 4.4 Stima righe DOPO (con il calcolo)
| Voce | Oggi | Domani | Motivo |
|---|---|---|---|
| Runner: saldo + regolati + attribuzione | ~900 | ~700 | stessa logica (`componi_regolati` 146 + `_proprietari` 77 + commissioni 50 = 273 restano), spariscono le ripetizioni di cadenza/cache e gli `_LAST_*` globali |
| Giornata + stop di conto | 650 | ~250 | una `giornata()` e UNO stop; il lordo/netto di B3 diventa una scelta dichiarata |
| `saldo_evento` | 252 | ~120 | stesso lettore del §4.1 |
| Scritture DB (`db.py` P&L) | ~190 | ~150 | postino asincrono (G) |
| Mike regolamento | 1.227 | ~450 (E1) + 80 politica | legge `Movimento`, resta la separazione righe utente |
| Omega regolamento | 516 | ~180 | `settle_pnl` resta (strategia/ordine), lettura dal componente |
| Safe regolamento | ~700 | ~250 | idem |
| Scalper/tennis/paper | ~170 | ~100 | commissione unica |
| Green-up | 249 + 6 copie (~150) | ~260 | `compute_greenup` + generazione TS; le copie spariscono |
| Frontend contabile | 4.654 (tetto) | ~2.400 | `composizione*` 829 -> 350; `posizioniChiuse` 1.051 -> 450; `dailyHistory` 1.285 -> 500; `LivePnl` 537 -> 400; `eventGroups` 387 -> 250; `giornataBot` 218 -> 100; `fontePnl` 106 e `replay-pnl` 241 restano |
| Relitto Sheets | 5.722 | **0 nell'app** (archivio) | D1 |
| **Totale** | **~14.980** | **~4.940** | **-67%**, di cui -5.722 dal relitto e ~-4.300 dalla ripetizione. Senza il relitto: 9.260 -> ~4.940 (-47%) |

(Stima del domani: il coordinatore la rifa' con `wc -l` a tappa chiusa; qui e' un calcolo, non una misura.)

### 4.5 Sostituire questo componente
- **OGGI**, per cambiare il modo di calcolare il P&L del conto o la commissione si toccano almeno: `reconcile_worker.py`, `daily_pnl.py`, `daily_stop_worker.py`, `regolato_conto.py` + `mike/service.py`, `omega_engine.py` + `omega_market.py` + `omega_service.py`, `safe_strategy/execution.py` + `bot_service.py`, `media_under_bot.py`, `tennis_live_order_worker.py`, e lato UI `composizioneConto.ts`, `composizioneObiettivo.ts`, `controlRoom.ts`, `posizioniChiuse.ts`, `dailyHistory.ts`, `LivePnl.tsx`, `omega.ts`, `safeBot.ts`, `CashOutButton.tsx` + 3 RPC SQL: **>= 20 file**.
- **DOMANI**: solo la cartella `contabilita/` e i suoi test di contratto (e `frontend/src/contabilita/`).

### 4.6 Gia' in una libreria matura
- Commissione/regolato: Betfair espone `commission` solo con `groupBy=MARKET` (docs «listClearedOrders - Roll-up Fields», citate in `regolato_conto.py:11-13`): non c'e' libreria che ripartisca per ordine, `commissioni_per_ordine` resta nostro (50 righe).
- `betfairlightweight` espone `list_cleared_orders` (`reconcile_worker.py:501`) e `account.get_account_funds` (`:143`): gia' usati; il client JSON-RPC proprio `client.py:395-420` `list_cleared_orders` li riscrive (A-scheda, D-del client unico).
- flumine: `order.simulated.profit` e `ClearedOrdersEvent` (`saldo_evento.py:249`) gia' usati per il paper e per l'evento di regolamento; non riscrivere il fill simulato.
- `Decimal` della libreria standard al posto di `round(x, 2)` ripetuto (`_round2` `reconcile_worker.py:133`, `round(...,2)` in decine di punti): non e' libreria matura aggiuntiva, ma elimina il difetto dei centesimi della condizione 10.

---

## 5. Parita'

Criterio: «stesso identico numero, centesimo per centesimo» su registrazioni reali, non su cio' che dichiara il delegato.
- **Replay del banco** (`python -m Betfair.stream.backtest.certifica <bot> ...`, uno per bot con ordini regolati; nessuno e' lanciato da questa scheda): per ogni registrazione gia' certificata
  (`AUDIT_2026-09-30/replay/{mike_base,omega,safe_base,safe_esatto,safe_punta}_PNL_*.txt`, `mike_chiuso_fuori_app_*_PNL_CONTO.txt`, `AUDIT_2026-10-07/replay_pro/`) il referto di domani deve coincidere numero per numero con quello di oggi:
  `lordo`, `commissione`, `netto` per bot e per partita, numero di cicli, istante di regolamento.
- **Test esistenti da tenere VERDI senza modifiche ai numeri attesi**: `Betfair/stream/tests/test_pnl_unico_conto_2026_10_04.py` (9), `test_pnl_betfair_reale_2026_09_24.py`, `test_daily_pnl.py`, `test_db_upsert_live_account_manual_pnl.py`, `test_scalper_pnl_settled_2026_07_16.py`;
  `mike/tests/test_mike_pnl_reale_del_conto_2026_09_30.py`; `omega/test_omega_pnl_netto_commissione_2026_09_30.py`, `omega/test_omega_giornata_gambe_2026_09_11.py`; `safe_strategy/tests/test_pnl_netto_commissione_2026_09_30.py`, `test_settlement_betfair_truth_2026_09_17.py`;
  `stream/tennis_live/tests/test_specchio_pnl_ref_2026_09_17.py`; frontend `pnlUnicoConto.test.ts` (6) e `pnlUnicoConto.viste.test.tsx` (3); falsificazioni `AUDIT_2026-09-30/falsifica_pnl_reale_conto*.py`.
- **Numeri di riferimento gia' verificati (04/10)**: conto netto **−5,15** = Mike **−5,68** + a mano **+0,53**; lordo −5,13, commissione 0,02; Posizioni chiuse **4 (2V 2P) −5,68**; chiusure a mano di Mike +5,07 (1 ordine); somma `per_posizione` = somma `per_fonte` = netto (assert).
- **Test NUOVI da scrivere (e falsificare)**:
  1. *Griglia green-up*: per una griglia di (W, L, prezzo, frazione) `compute_greenup`, `compute_green` (scalper/tennis), `profitto_bloccabile`, `locked_pnl_back`, `locked_pnl` Safe, `lockedPnlAt` (TS) danno lo STESSO `locked` e la stessa size al centesimo. Falsificazione: cambiare un arrotondamento in una copia -> rosso. Copre condizione 10.
  2. *Una sola commissione*: stessi ordini/gruppi passati a B1, a `net_of_commission`, a `netto_da_lordo`, a `net_profit_if_win`: oggi differiscono su un green-up (+10/−9): il test documenta la differenza e, dopo l'unificazione, diventa un'uguaglianza.
  3. *Stop lordo vs netto*: un giorno con mercati +5/−6, commissione 0,25: stop di conto con regola netta.
  4. *Giornata*: stesso insieme di ordini attraverso `giornata()` e attraverso le tre RPC `get_*_daily`: stessi totali per bot.
  5. *Contratto Python↔TS*: chiavi e tipi di `Movimento`/`Giornata` identici (cantiere 10 prevede lo stesso per `cicli_bot`).
- **Voci di `PROCESSO_STANDARD_BOT.md` coperte**: §6 «persistenza e UI» e «referto riproducibile»; §6 «ciclo di vita dell'ordine con parziali» limitatamente al regolamento; §7.21 («dato assente non e' zero», citato in `tennis_live_order_worker.py:466`). NON ho riletto §6 e §7 per intero in questa sessione (budget): il coordinatore ne controlli la corrispondenza per numero.

---

## 6. Migrazione

1. **Guscio e interruttore**: `contabilita/` nasce accanto al codice attuale con interruttore per bot `CONTABILITA_NUOVA=off|ombra|on` (come per gli altri componenti); default `off`.
2. **Ombra**: il nuovo componente calcola in parallelo e scrive in una tabella/chiave di confronto (`pnl_reale_oggi_ombra`, chiave additiva JSONB: nessuna migrazione, come ha fatto PNL_UNICO.md §2); un confronto automatico per giornata segnala qualunque differenza (> 0 centesimi) fra vecchio e nuovo, per bot e per partita. Condizione di passaggio: 5 giornate live consecutive a zero differenze + replay del banco identici.
3. **Taglio**: prima il lettore del conto (A), poi `Giornata` e stop, poi i tre adattatori bot (Mike, Safe, Omega, in quest'ordine di rischio crescente: Mike e Safe gia' usano B1), infine il frontend. Il vecchio si toglie per ultimo.
4. **Dopo C (porta ordini)** e dopo D (runtime): la contabilita' consuma gli eventi d'ordine di C; fino ad allora legge come oggi.
5. **Rischi**: (a) il tipo `Decimal` cambia gli arrotondamenti: il test griglia (§5.1) lo cattura; (b) lo stop passa da lordo a netto = **cambio di decisione** -> D3, non si fa senza l'utente; (c) la giornata unica cambia la pagina Omega/Safe: D2; (d) le RPC SQL (`get_*_daily`) le applica l'utente (CLAUDE.md: migrazioni).
6. **Ritorno indietro**: l'interruttore a `off` ripristina il vecchio percorso in un riavvio; le tabelle non cambiano forma.

---

## 7. Misure

| Misura | Oggi (fonte) | Obiettivo |
|---|---|---|
| `getAccountFunds` | 3/min runner (`reconcile_worker.py:96`) + a evento nei bot (non misurato) | 3/min totali, un solo chiamante |
| `listClearedOrders` | runner (cache 35 s, ordini ogni 300 s) + 3 lettori per bot al regolamento (non misurato) | 1 lettore; richieste/giorno = misura con contatore nel client unico (strumento: `ARCHITETTURA_2026-10/strumenti/misure/`, da scrivere) |
| Calcoli di P&L del realizzato (backend) | 6 + paper (§1.3) | 1 componente, adattatori sottili |
| Somme di P&L lato client | 8 (§1.3) | 0 (legge `Giornata`) |
| Definizioni di «oggi» | 4 (§1.6) | 1 `giornata()` |
| Copie del green-up | 1 libreria + 6 (§1.4) | 1 + generazione TS |
| Stop perdita giornaliera | 4 implementazioni (§1.5) | 1 motore, limiti per bot dichiarati |
| Righe (§4.4) | ~14.980 | ~4.940 |
| Latenza dal regolamento Betfair al numero a schermo | firma+cache: fino a 35 s (cache) o 300 s (giro ordini), 5-20 s se forzato da cambio saldo (`reconcile_worker.py:615-627`); misura end-to-end NON fatta (strumento: timestamp `pnl_letto_at` `:1218` vs `settled_at` Betfair) | <= 20 s dal regolamento |
| Richieste al cloud al minuto per il P&L | non misurata | write-on-change gia' presente (`_LAST_*_SIG`); obiettivo: postino coalescente <= 1/5 s |

---

## Decisioni per l'utente
- **D1 Relitto Sheets (5.722 righe)**: archiviare `money_management.py`, `betfair_report_manager.py`, `aggiorna_mm_sheets.py`, `aggiorna_solo_fogli.py`? Prima va deciso dove vive `CALIBRATION_TABLE` (oggi riscritta ogni lunedi' dal workflow `weekly_poisson_calibration.yml`): non ho verificato chi la consuma oltre `calibration_analysis.py:396`. Nessuna cancellazione senza il tuo ok.
- **D2 UNA giornata**: storico per giorno della PARTITA, conto/stop per giorno di REGOLAMENTO, Omega 12 h mobile. Proposta: giorno della partita ovunque tranne il conto di Betfair, dichiarato a schermo. E' un cambio di numeri visibili.
- **D3 Stop di conto lordo o netto**: oggi lordo (B3). Passare al netto cambia quando scatta lo stop (strategia/rischio): decisione tua, non la prendo.
- **D4 Commissione unica** anche per Omega e scalper (oggi regola per-valore): puo' cambiare i P&L mostrati su un green-up; l'esecuzione degli ordini non cambia, ma un target «netto» di scalper (`media_under_bot.py:556`) dipende da quella regola: **puo' toccare la strategia**, quindi decisione tua.

## Cosa ho verificato di persona / cosa non ho potuto verificare
Verificato (letto nel codice, `file:riga` sopra): cadenze e chiamate REST di `reconcile_worker.py` (§1.2), formula B1 e suoi importatori (`regolato_conto.py:133, 206`, `execution.py:2870`), assenza di `getAccountStatement`, relitti e importatori (`git grep`), workflow del lunedi', elenco delle funzioni di P&L (`git grep` sui nomi), identita' di `compute_green` (`s04`), regola per-valore in 5 punti, default dei parametri citati, tabelle (`s03_matrice_tabelle.tsv`), righe (`wc -l`).
NON verificato: (1) numericamente la coincidenza fra le copie del green-up e la condizione 10 (test §5.1 da scrivere); (2) se Omega usa o riscrive la commissione per mercato (`git grep` non trova l'import; non ho letto `omega_market.py:1599-1769` per intero); (3) lo scarto lordo/netto dello stop (B3) in euro: nessuna misura; (4) i default di Safe e dei bot tennis, e i valori VIVI nel DB; (5) cadenza e conteggio reale di `getAccountFunds` a evento e di `listClearedOrders` dei bot (nessuna misura: serve un contatore nel client); (6) quali tabelle scrive esattamente `_scrivi_righe :1084`; (7) il contenuto di `giornataBot.ts`, di `LivePnl.tsx` (letto solo via PNL_UNICO.md) e dei tre file con `bankroll` oltre i due citati; (8) `PROCESSO_STANDARD_BOT.md` §6/§7 riletti solo per le voci citate; (9) le stime di righe del §4.4 sono calcoli, non misure; (10) nessun test, replay o app e' stato eseguito (regola del brief).
