# Controllo finale del banco - Mike (08/10/2026)

Esecutore: sessione cloud del controllo finale (nessuna modifica al codice).
Base: `d01de76ea591a57850eff29063fa969abbf6559f` (verificato con `git log --oneline -1` -> `d01de76`).
Riferimento: `AUDIT_2026-10-08/W3A_DOPO_CLOUD/mike_<ev>_tutti.txt` (giro sequenziale).

## Ambiente

- Registrazioni decompresse con lo script di `registrazioni_banco/LEGGIMI.md` in `_live_raw/` (fuori dal repo).
- `pip install psutil` nel container. **In piu' rispetto al brief**: il primo lancio e' morto subito con
  `ModuleNotFoundError: No module named 'flumine'` (container senza dipendenze), quindi ho eseguito
  `pip install -r requirements.txt` SOLO nel container -> flumine 2.13.11, betfairlightweight 2.23.2
  (stesse versioni dichiarate nel referto di riferimento).
- Riga worker presente nei referti con `--worker 3`: `worker: 3 su 4 core fisici (...)`.

## Comandi e tempi

| # | comando | exit | TEMPO TOTALE |
|---|---|---|---|
| 1 | `python -m Betfair.stream.backtest.certifica mike 35797769 --scenari tutti --worker 3 > mike_35797769_tutti.txt 2>&1` | 0 | 833.0 s (rif. sequenziale 2282.6 s) |
| 2 | `python -m Betfair.stream.backtest.certifica mike 35760084 --scenari tutti --worker 3 > mike_35760084_tutti.txt 2>&1` | 0 | 249.0 s (rif. sequenziale 754.8 s) |
| 3 | `python -m Betfair.stream.backtest.certifica mike 35760084 --scenari tutti --worker 1 > mike_35760084_tutti_w1.txt 2>&1` | 0 | 726.3 s |
| 3b | `python -m Betfair.stream.backtest.tools.confronta_referti mike_35760084_tutti_w1.txt mike_35760084_tutti.txt` | 1 | **righe diverse: 2** (atteso 0) |

Nota: il replay 1 (833 s) supera il tetto dichiarato di 600 s anche con 3 worker.

## Esiti per evento

| evento | OK | NE | KO | righe di esito vs riferimento | controlli violati |
|---|---|---|---|---|---|
| 35797769 (`--worker 3`) | 23 | 6 | 0 | identiche (29/29) | 0 |
| 35760084 (`--worker 3`) | 28 | 1 | 0 | identiche (29/29) | 0 |
| 35760084 (`--worker 1`) | 28 | 1 | 0 | identiche (29/29) | 0 |

NE su 35797769: gol-precoce, cashout-dopo-copertura, firma-dopo-gol-decisivo,
firma-dopo-gol-decisivo-senza-chiusura, uscite-in-perdita-firmate, uscite-automatiche (come nel riferimento).
NE su 35760084: cashout-dopo-copertura (come nel riferimento).
Scenari: gli stessi 29 nello stesso ordine; `confronta_referti` applicabile.

## Differenze ATTESE (vs riferimento)

Per ciascun evento `confronta_referti` riporta 29 righe diverse, tutte note `[NON ESERCITABILE]`:

| tipo | 35797769 | 35760084 (w3) | 35760084 (w1) |
|---|---|---|---|
| (a) nota `ht_ft_rows` aggiunta come riga nuova | 26 | 26 | 26 |
| (a) nota `ht_ft_rows` fusa nella nota proprietari esistente | 3 | 3 | 3 |
| (b) impronta del codice bot | 0 (invariata: `da8e7d9eb005 (9 file)` sia nel riferimento sia ora) | 0 | 0 |

La nota `ht_ft_rows` c'e' in 27 scenari su 29. **Non c'e'** in `bot-fermo` e `feed-stantio`, su
entrambi gli eventi e con entrambi i numeri di worker; in quei due scenari il riferimento non ha
nessuna nota `[NON ESERCITABILE]`, quindi rispetto al riferimento non c'e' nessuna differenza.
Lo segnalo perche' il brief dice «in ogni scenario».

Fusioni (35797769 e 35760084, uguali):
- `chiuso-fuori-app`: PRIMA `proprietari_bot_conto | proprietari_bet` -> DOPO `proprietari_bot_conto | ht_ft_rows | proprietari_bet` (attesa).
- `manuale-app-paper`: PRIMA `proprietari_bot_conto` -> DOPO `proprietari_bot_conto | ht_ft_rows` (attesa).
- `ridotto-fuori-app`: vedi sotto (contiene la differenza NON attesa).

## Differenze NON ATTESE

### N1 - `ridotto-fuori-app`, con `--worker 3`: compare `proprietari_bot_conto`

Su entrambi gli eventi, con `--worker 3`, la nota dello scenario `ridotto-fuori-app` contiene anche
`proprietari_bot_conto`, che nel riferimento non c'e'. Con `--worker 1` (35760084) la nota NON lo
contiene: li' la differenza dal riferimento e' solo la fusione attesa di `ht_ft_rows`.

PRIMA (riferimento, e uguale nella sostanza nel `--worker 1` salvo l'aggiunta attesa di `ht_ft_rows`):
```
      nota: [NON ESERCITABILE] dati di produzione assenti dalla registrazione: proprietari_bet: tabelle degli altri bot (omega_trades, safe_strategy_trades, betfair_live_orders): non sono nel replay, il proprietario di un ordine non di Mike si decide dal riferimento d'ordine
```
DOPO `--worker 1` (35760084, riga 293):
```
      nota: [NON ESERCITABILE] dati di produzione assenti dalla registrazione: ht_ft_rows: storico HT->FT (RPC get_omega_ht_ft, migliaia di partite): non e' nella registrazione di UNA partita, quindi la tabella empirica del dossier resta assente | proprietari_bet: tabelle degli altri bot (omega_trades, safe_strategy_trades, betfair_live_orders): non sono nel replay, il proprietario di un ordine non di Mike si decide dal riferimento d'ordine
```
DOPO `--worker 3` (35797769 e 35760084, identica):
```
      nota: [NON ESERCITABILE] dati di produzione assenti dalla registrazione: proprietari_bot_conto: tabelle degli altri bot e coda del runner (proprietari degli ordini altrui sul conto): non sono nel replay, un ordine non del bot si decide dai riferimenti (nessun altro bot) | ht_ft_rows: storico HT->FT (RPC get_omega_ht_ft, migliaia di partite): non e' nella registrazione di UNA partita, quindi la tabella empirica del dossier resta assente | proprietari_bet: tabelle degli altri bot (omega_trades, safe_strategy_trades, betfair_live_orders): non sono nel replay, il proprietario di un ordine non di Mike si decide dal riferimento d'ordine
```

### N2 - `--worker 1` e `--worker 3` NON danno lo stesso referto (35760084)

Uscita completa di `confronta_referti mike_35760084_tutti_w1.txt mike_35760084_tutti.txt` (exit 1):
```
... righe diverse: 2
@@ -293 +293 @@
-      nota: [NON ESERCITABILE] dati di produzione assenti dalla registrazione: ht_ft_rows: storico HT->FT (RPC get_omega_ht_ft, migliaia di partite): non e' nella registrazione di UNA partita, quindi la tabella empirica del dossier resta assente | proprietari_bet: tabelle degli altri bot (omega_trades, safe_strategy_trades, betfair_live_orders): non sono nel replay, il proprietario di un ordine non di Mike si decide dal riferimento d'ordine
+      nota: [NON ESERCITABILE] dati di produzione assenti dalla registrazione: proprietari_bot_conto: tabelle degli altri bot e coda del runner (proprietari degli ordini altrui sul conto): non sono nel replay, un ordine non del bot si decide dai riferimenti (nessun altro bot) | ht_ft_rows: storico HT->FT (RPC get_omega_ht_ft, migliaia di partite): non e' nella registrazione di UNA partita, quindi la tabella empirica del dossier resta assente | proprietari_bet: tabelle degli altri bot (omega_trades, safe_strategy_trades, betfair_live_orders): non sono nel replay, il proprietario di un ordine non di Mike si decide dal riferimento d'ordine
```
E' la stessa riga di N1. Tutto il resto (righe di esito, tick, decisioni, azioni, stati, altre note,
motivi) e' identico tra `--worker 1` e `--worker 3`. Causa non indagata (fuori mandato: nessuna
modifica al codice); il fatto osservato e' che la nota di `ridotto-fuori-app` dipende dal numero di
worker.

Nessun'altra differenza: nessuna riga di esito cambiata, nessun controllo violato, nessuna
variazione di tick/decisioni/azioni/stati.

## File

- `mike_35797769_tutti.txt` - replay 1 (`--worker 3`)
- `mike_35760084_tutti.txt` - replay 2 (`--worker 3`)
- `mike_35760084_tutti_w1.txt` - replay 3 (`--worker 1`)
