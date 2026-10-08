# Controllo scalper_calcio sulla cima 597ea3a

Data: 2026-10-08. Esecutore: sessione cloud delegata (nessuna modifica al codice).

- Codice: `597ea3a` (W3b, ordini esterni), ramo `claude/blissful-sagan-hri7o6-controllo-scalper`.
- Banco: `python -m Betfair.stream.backtest.certifica scalper_calcio <ev> --worker 1 --scenari <blocco>`,
  4 blocchi in parallelo (nproc=4), stessa divisione di `W3B/dopo_cloud` (vedi `_tempi.txt`).
- Registrazioni: `registrazioni_banco/` decompresse in `_live_raw/` con lo script di `LEGGIMI.md`.
- Riferimento: `AUDIT_2026-10-08/W3B/dopo_cloud/*_blocco*.txt` (codice precedente, senza il cantiere 7).
- Impronta del codice bot dichiarata dal banco: `de72fb261d8e (13 file)` sia qui sia in `W3B/dopo_cloud`.
- Codici di uscita: 35797769 blocchi 1-3 rc=1 (KO attesi), blocco 4 rc=0; 35760084 tutti rc=0. Uguali a W3b.

## Esiti

Confronto su: esito, tick, decisioni, azioni, controlli violati (codice e conteggio). Ignorati stati e tempi.

| registrazione | scenario | esito | tick | decisioni | azioni | violati | uguale al DOPO di W3b |
|---|---|---|---|---|---|---|---|
| 35797769 | base | OK | 665941 | 121012 | 44 | - | si |
| 35797769 | paper | OK | 665941 | 121012 | 44 | - | si |
| 35797769 | chiusura-abbinata-in-parte | KO | 665941 | 121012 | 213 | B2 x1 | si |
| 35797769 | rifiuti-betfair | OK | 665941 | 121012 | 56 | - | si |
| 35797769 | sniper-paper | OK | 1511913 | 286052 | 44 | - | si |
| 35797769 | ingresso-abbinato-in-parte | OK | 665941 | 121012 | 49 | - | si |
| 35797769 | ingresso-abbinato-in-parte-paper | OK | 665941 | 121012 | 49 | - | si |
| 35797769 | rifiuti-betfair-codici | KO | 665941 | 121012 | 132 | RC3 x1 | si |
| 35797769 | rifiuti-betfair-codici-paper | KO | 665941 | 121012 | 132 | RC3 x1 | si |
| 35797769 | ordine-esterno | OK | 7760 | 1373 | 2 | - | si |
| 35797769 | ordine-esterno-app | OK | 7760 | 1373 | 2 | - | si |
| 35797769 | ordine-esterno-di-un-bot | OK | 665941 | 121012 | 44 | - | si |
| 35797769 | ordine-esterno-db-giu | OK | 665941 | 121012 | 98 | - | si |
| 35797769 | ordine-esterno-altro-mercato | OK | 665941 | 121012 | 44 | - | si |
| 35760084 | base | OK | 124672 | 23599 | 0 | - | si |
| 35760084 | paper | OK | 124672 | 23599 | 0 | - | si |
| 35760084 | chiusura-abbinata-in-parte | OK | 124672 | 23599 | 0 | - | si |
| 35760084 | rifiuti-betfair | OK | 124672 | 23599 | 0 | - | si |
| 35760084 | sniper-paper | OK | 504571 | 87165 | 0 | - | si |
| 35760084 | ingresso-abbinato-in-parte | NE | 124672 | 23599 | 0 | - | si |
| 35760084 | ingresso-abbinato-in-parte-paper | NE | 124672 | 23599 | 0 | - | si |
| 35760084 | rifiuti-betfair-codici | NE | 124672 | 23599 | 0 | - | si |
| 35760084 | rifiuti-betfair-codici-paper | NE | 124672 | 23599 | 0 | - | si |
| 35760084 | ordine-esterno | OK | 29538 | 5607 | 0 | - | si |
| 35760084 | ordine-esterno-app | OK | 29538 | 5607 | 0 | - | si |
| 35760084 | ordine-esterno-di-un-bot | OK | 124672 | 23599 | 0 | - | si |
| 35760084 | ordine-esterno-db-giu | OK | 124672 | 23599 | 0 | - | si |
| 35760084 | ordine-esterno-altro-mercato | OK | 124672 | 23599 | 0 | - | si |

## Differenze

Nessuna: 28 righe su 28 uguali. Verifica aggiuntiva: diff integrale degli 8 file di blocco contro
quelli di `W3B/dopo_cloud`, escluse solo le righe di tempo/tick al secondo, il comando, il percorso
delle registrazioni e la colonna stati: **0 righe diverse** (note, motivi, copertura dei controlli,
mai sollecitati, ESITO compresi).

## KO presenti (gia' presenti identici in W3b, non nuovi)

- 35797769 `chiusura-abbinata-in-parte`: B2 x1 (al fischio una posizione aperta).
- 35797769 `rifiuti-betfair-codici` e `-paper`: RC3 x1 (rifiuto BET_TAKEN_OR_LAPSED del replaceOrders
  mai scritto col codice nell'attivita' del bot).
- 35760084: 4 scenari NE (ingresso-abbinato-in-parte*, rifiuti-betfair-codici*), come in W3b.
