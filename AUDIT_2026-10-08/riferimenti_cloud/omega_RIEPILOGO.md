# Riferimenti omega su 1ac69d0 (cloud, 2026-10-08)

Commit: `1ac69d0 feat(banco scalper): scavalco e rifiuti Betfair coi codici veri, parcheggio LAY 1,01-1,03 riconosciuto da UF2 (cantiere 9)` | nproc: 4 | 3 lanci in parallelo, `--worker 1` ciascuno.
Registrazioni decompresse da `registrazioni_banco/` in `_live_raw/` (procedura di LEGGIMI.md). Exit code di tutti i lanci: 0.

## omega_35760084_tutti

```
comando: python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti
OK  35760084 [base]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [giornata-reale]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [apertura]  tick=482034 decisioni=  467 azioni=   2 stati=running [COMPLETE]
OK  35760084 [paper]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [cap-stretto]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [bot-fermo]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [feed-stantio]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [esiti-ignoti]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [riavvio]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [manuale-e-bot]  tick=482983 decisioni=  467 azioni=   1 stati=running [COMPLETE]
OK  35760084 [cashout-globale]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [proposta-approvata]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [uscite-automatiche]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [v4]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [v4-riavvio]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [v4-bot-fermo]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [v3]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [rifiuti-betfair]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [chiuso-fuori-app]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
OK  35760084 [chiusura-abbinata-in-parte]  tick=483985 decisioni=  438 azioni=   0 stati=running [COMPLETE]
ESITO: 20 partite senza violazioni, 0 con violazioni, 0 senza decisioni
TEMPO TOTALE: 9m27.1s (567.1 s) su 20 replay | obiettivo 300 s, tetto 600 s (CERTIFICA_TETTO_S)
```

Scenari KO: nessuno (0 con violazioni). Tempo misurato dalla shell: 570.0 s.

stderr (righe CRITICAL/ERROR):
```
      1 CRITICAL:omega.service:[omega] il lettore degli aggregati non separa le modalita': paper e live SOMMATI nelle decisioni (catalogo 7.21)
```

## omega_35797769_tutti

```
comando: python -m Betfair.stream.backtest.certifica omega 35797769 --scenari tutti
OK  35797769 [base]  tick=1470869 decisioni=  686 azioni=   0 stati=running [COMPLETE]
OK  35797769 [giornata-reale]  tick=1470869 decisioni=  686 azioni=   0 stati=running [COMPLETE]
OK  35797769 [apertura]  tick=1470869 decisioni=  686 azioni=   0 stati=running [COMPLETE]
OK  35797769 [paper]  tick=1470869 decisioni=  686 azioni=   0 stati=running [COMPLETE]
OK  35797769 [cap-stretto]  tick=1462841 decisioni=  736 azioni=   4 stati=running [COMPLETE]
OK  35797769 [bot-fermo]  tick=1464026 decisioni=  736 azioni=   2 stati=running,stopped [COMPLETE]
OK  35797769 [feed-stantio]  tick=1470869 decisioni=  686 azioni=   0 stati=running [COMPLETE]
OK  35797769 [esiti-ignoti]  tick=1462964 decisioni=  736 azioni=   6 stati=running [COMPLETE]
OK  35797769 [riavvio]  tick=1462841 decisioni=  736 azioni=   4 stati=running [COMPLETE]
OK  35797769 [manuale-e-bot]  tick=1468611 decisioni=  736 azioni=   1 stati=running [COMPLETE]
OK  35797769 [cashout-globale]  tick=1466508 decisioni=  736 azioni=   2 stati=running [COMPLETE]
OK  35797769 [proposta-approvata]  tick=1462841 decisioni=  736 azioni=   4 stati=running [COMPLETE]
OK  35797769 [uscite-automatiche]  tick=1462841 decisioni=  736 azioni=   4 stati=running [COMPLETE]
OK  35797769 [v4]  tick=1462841 decisioni=  736 azioni=   4 stati=running [COMPLETE]
OK  35797769 [v4-riavvio]  tick=1462841 decisioni=  736 azioni=   4 stati=running [COMPLETE]
OK  35797769 [v4-bot-fermo]  tick=1464026 decisioni=  736 azioni=   2 stati=running,stopped [COMPLETE]
OK  35797769 [v3]  tick=1470869 decisioni=  686 azioni=   0 stati=running [COMPLETE]
OK  35797769 [rifiuti-betfair]  tick=1464070 decisioni=  736 azioni=   4 stati=running [COMPLETE]
OK  35797769 [chiuso-fuori-app]  tick=1466579 decisioni=  736 azioni=   2 stati=running [COMPLETE]
OK  35797769 [chiusura-abbinata-in-parte]  tick=1463012 decisioni=  736 azioni=   4 stati=running [COMPLETE]
ESITO: 20 partite senza violazioni, 0 con violazioni, 0 senza decisioni
TEMPO TOTALE: 40m30.9s (2430.9 s) su 20 replay | obiettivo 300 s, tetto 600 s (CERTIFICA_TETTO_S)
LENTO: la certificazione ha impiegato 40m30.9s (2430.9 s), sopra il tetto di 600 s | scenario piu' caro: 35797769 [rifiuti-betfair] 2m22.3s (142.3 s) | e' un AVVISO: l'esito non cambia
```

Scenari KO: nessuno (0 con violazioni). Tempo misurato dalla shell: 2434.0 s.

stderr (righe CRITICAL/ERROR):
```
      1 CRITICAL:omega.service:[omega] evento 35797769: posizione chiusa DALL'UTENTE fuori dall'app -> il bot non gestisce piu' questa partita
      1 CRITICAL:omega.service:[omega] il lettore degli aggregati non separa le modalita': paper e live SOMMATI nelle decisioni (catalogo 7.21)
      1 CRITICAL:omega.service:[omega] place LIVE a esito IGNOTO (trade 1, evento 35797769): in riconciliazione
      1 CRITICAL:omega.service:[omega] place LIVE a esito IGNOTO (trade 2, evento 35797769): in riconciliazione
```

## omega_35760084_apertura

```
comando: python -m Betfair.stream.backtest.certifica omega 35760084 --scenari apertura
OK  35760084  tick=482034 decisioni=  467 azioni=   2 stati=running [COMPLETE]
ESITO: 1 partite senza violazioni, 0 con violazioni, 0 senza decisioni
TEMPO TOTALE: 29.6s (29.6 s) su 1 replay | obiettivo 300 s, tetto 600 s (CERTIFICA_TETTO_S)
```

Scenari KO: nessuno (0 con violazioni). Tempo misurato dalla shell: 32.6 s.

stderr (righe CRITICAL/ERROR):
```
      1 CRITICAL:omega.service:[omega] il lettore degli aggregati non separa le modalita': paper e live SOMMATI nelle decisioni (catalogo 7.21)
```

## Note
- 35797769 tutti: 2430.9 s, sopra il tetto di 600 s (AVVISO LENTO del banco, esito invariato); scenario piu' caro rifiuti-betfair 142.3 s. Girava in parallelo con gli altri due lanci su 4 core.
- In ogni lancio stderr riporta il CRITICAL di omega.service "il lettore degli aggregati non separa le modalita': paper e live SOMMATI nelle decisioni (catalogo 7.21)": e' un messaggio del servizio, nessun controllo del banco lo ha contato come violazione. Va valutato dal coordinatore.
