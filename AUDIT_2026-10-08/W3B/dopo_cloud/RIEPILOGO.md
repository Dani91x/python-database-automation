# Replay DOPO W3b dal cloud (08/10)

- Codice: commit `8ff9825` (ramo `claude/blissful-sagan-hri7o6-w3b-appoggio`), impronta del bot
  `de72fb261d8e` (13 file), flumine 2.13.11, betfairlightweight 2.23.2.
- Registrazioni: `registrazioni_banco/` decompresse in `_live_raw/` con lo script di `LEGGIMI.md`.
- Comando: `python -m Betfair.stream.backtest.certifica scalper_calcio <ev> --worker 1 --scenari <blocco>`,
  14 scenari in 4 blocchi lanciati in parallelo, ogni scenario una sola volta per registrazione.
- Macchina: container cloud, `nproc` = 4. Le registrazioni sono girate una dopo l'altra (prima 35797769,
  poi 35760084), con 4 processi in parallelo ciascuna.

## Esiti

| scenario | 35797769 | azioni | violati | 35760084 | azioni | violati | atteso (14.3 / 14.6) |
|---|---|---|---|---|---|---|---|
| base | OK | 44 | - | OK | 0 | - | uguale |
| paper | OK | 44 | - | OK | 0 | - | uguale |
| chiusura-abbinata-in-parte | KO | 213 | B2 x1 | OK | 0 | - | uguale (KO solo B2, 213) |
| rifiuti-betfair | OK | 56 | - | OK | 0 | - | uguale |
| sniper-paper | OK | 44 | - | OK | 0 | - | uguale |
| ingresso-abbinato-in-parte | OK | 49 | - | NE | 0 | - | uguale |
| ingresso-abbinato-in-parte-paper | OK | 49 | - | NE | 0 | - | uguale |
| rifiuti-betfair-codici | KO | 132 | RC3 x1 | NE | 0 | - | uguale (KO solo RC3, 132) |
| rifiuti-betfair-codici-paper | KO | 132 | RC3 x1 | NE | 0 | - | uguale (KO come il live) |
| ordine-esterno | OK (stop) | 2 | - | OK (stop) | 0 | - | uguale: 1018 / 886 ms |
| ordine-esterno-app | OK (stop) | 2 | - | OK (stop) | 0 | - | uguale: 1018 / 886 ms |
| ordine-esterno-di-un-bot | OK | 44 | - | OK | 0 | - | uguale: nessuno stop, ripresa 1018 / 886 ms |
| ordine-esterno-db-giu | OK | 98 | - | OK | 0 | - | uguale: sospesa, 38 rifiuti, 0 accettati |
| ordine-esterno-altro-mercato | OK | 44 | - | OK | 0 | - | uguale (come base) |

Dettagli verificati sui file dei blocchi:
- ordine-esterno e -app su 35797769: la selezione è sospesa a +0 ms, la verifica (5 select)
  è pronta a +600 ms, la decisione `fuori_bot` arriva a **1018 ms**, annullo 2/2 vivi. Su
  35760084: **886 ms**, 0 vivi.
- ordine-esterno-di-un-bot: motivo `bot:coda:omega-t9`, ripresa a 1018 ms (886 ms su 35760084);
  0 ordini nuovi accettati sulla selezione sospesa.
- ordine-esterno-db-giu su 35797769: 98 azioni, di cui 38 `place_rifiutato` e
  38 `freno_rifiuti` (le stesse 98 del giro2 in `../giro2_c9/`). La selezione non viene mai ripresa, il DB
  si rilegge ogni ~30 s di mercato e 0 ordini vengono accettati sulla selezione sospesa.
- Confronto con il PRIMA (`../giro2_c9/prima_*.txt`), righe di esito senza la colonna `stati`:
  i 9 scenari in comune sono **IDENTICI** su entrambe le registrazioni; le uniche righe in più
  sono i 5 scenari W3b.
- Nessun traceback nei file.

**Differenze dai valori attesi: nessuna.**

## Tempi (secondi di parete)

| registrazione | blocco1 | blocco2 | blocco3 | blocco4 | totale parete |
|---|---|---|---|---|---|
| 35797769 | 200 | 293 | 57 | 157 | 293 |
| 35760084 | 21 | 47 | 11 | 22 | 47 |

`rc=1` nei blocchi di 35797769 che contengono un KO atteso: è il codice d'uscita normale di
`certifica` quando c'è una violazione. I dati grezzi sono in `_tempi.txt`.

## File

`35797769_blocco1..4.txt`, `35760084_blocco1..4.txt` (uscita integrale), `_tempi.txt`.
