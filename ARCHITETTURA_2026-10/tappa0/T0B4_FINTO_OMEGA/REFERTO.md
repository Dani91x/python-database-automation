# T0B punto (4) - Il finto del database di Omega con la firma del vero (09/10/2026)

Delegato cloud (Opus 5.5), ramo `tappa0-finto-omega` da `0aa76dfa`. Decisione dell'utente U-32 (si'). Fonti: `05_PIANO_DI_MIGRAZIONE.md`
§1 T0B punto (4); `03_SCHEDE_COMPONENTI/E2_OMEGA.md` difetto 5 e decisione 4; `H_BANCO_REPLAY.md` punto 6; `PROCESSO_STANDARD_BOT.md`
§7 n.21 (paper e live sommati), n.27 (finti con chiavi o tipi diversi dal vero), n.35 (test mai visto rosso).

## 0. Esito in una riga

Il CRITICAL «paper e live SOMMATI» sparisce da tutti gli scenari di Omega su 35760084 e 35797769 (22 + 24 righe di stderr -> 0);
`confronta_referti` PRIMA/DOPO = **0 righe diverse** su entrambe le partite; nel referto grezzo cambiano solo righe di tempo e di
memoria. Il vero (`omega_db.py`), il servizio e la strategia di Omega non sono toccati (`git diff 0aa76dfa` vuoto su `omega_db.py`,
`omega_service.py`, `omega_engine.py`).

## 1. Il difetto

`DbMemoriaOmega` (`Betfair/omega/tools/replay_registrazioni.py`) e' il database di Omega in memoria del banco. I suoi
`aggregates(self, day_start=None)` e `aggregates_coppia(self, day_start=None)` non avevano `mode`. Il servizio
(`omega_service._con_modalita`, `omega_service.py:409-431`) guarda la firma con `inspect.signature`: un lettore senza `mode` viene
chiamato senza modalita' (numeri di TUTTE le righe) e il servizio lo grida una volta per processo:
`CRITICAL:omega.service:[omega] il lettore degli aggregati non separa le modalita': paper e live SOMMATI nelle decisioni (catalogo 7.21)`.
In produzione il vero legge i numeri della sola modalita' del bot (stop giornaliero, tetti, obiettivo): il replay certificava un
percorso diverso.

## 2. Firme a confronto (`inspect.signature`)

| | prima (0aa76dfa) | dopo | vero (`omega_db.py:777,787`) |
|---|---|---|---|
| `aggregates` | `(self, day_start: Any = None)` | `(self, day_start: Any = None, mode: Optional[str] = None)` | `(day_start=None, mode: Optional[str] = None)` |
| `aggregates_coppia` | `(self, day_start: Any = None)` | `(self, day_start: Any = None, mode: Optional[str] = None)` | `(day_start=None, mode: Optional[str] = None)` |

Il test confronta nome, tipo (`POSITIONAL_OR_KEYWORD`) e default di ogni parametro, `self` escluso: identici.

## 3. Il diff spiegato (unico file di codice: `Betfair/omega/tools/replay_registrazioni.py`, +24 -5)

1. `aggregates(self, day_start=None, mode=None)` -> `self.aggregates_coppia(day_start, mode=mode)[0]`: come il vero
   (`omega_db.aggregates` = primo della coppia, `omega_db.py:794`).
2. `aggregates_coppia(self, day_start=None, mode=None)`: `m = str(mode or "").strip().lower()`; se `m` e' `paper` o `live` le righe
   passano dalla funzione PURA del vero `omega_engine.righe_della_modalita` (una chiusura vale la modalita' della sua apertura, una
   riga senza `mode` vale `paper`, default NOT NULL del DB); ogni altro valore (None, vuota, sconosciuta) = tutte le righe. E' la
   stessa normalizzazione e la stessa diramazione del vero (`omega_db.py:820-823`) e lo stesso calcolo del suo percorso «in casa»
   (`_aggregati_modalita`, `omega_db.py:859-861`), che il vero dichiara «stesso risultato» della RPC `get_omega_aggregates_modalita`.
   Nessuna aritmetica scritta nel finto: le chiavi e i tipi del risultato sono quelli di `omega_engine.aggregate_trades`.
3. Docstring: perche' e da quando. Codice ASCII-only.

Non toccati: l'elenco delle colonne del finto (ne legge 5 in piu' del vero, `size, price, commission, phase, side`, che
`aggregate_trades` non usa: effetto nullo, gia' coperto dal test del 16/09 `test_gli_aggregati_passano_dalla_funzione_pura_vera`).

## 4. Test nuovo - `Betfair/omega/test_omega_finto_aggregati_modalita_2026_10_09.py` (28 casi)

Confronto contro il VERO, non contro una copia: `omega_db.aggregates_coppia` gira davvero con `_sb` che fallisce (nessuna RPC: il
vero ripiega sul calcolo in casa) e `_righe_per_aggregati` che serve le righe proiettate sulle colonne della SUA `select` (estratte
dal sorgente del vero: se domani ne legge una in piu', il test la segue).

- firma: `aggregates` e `aggregates_coppia` identiche al vero (2); il servizio riconosce il finto come lettore per modalita' (1);
- comportamento: `aggregates_coppia` == vero con chiavi e TIPI identici per 7 modalita' (`None`, `""`, `paper`, `live`,
  `" LIVE "`, `Paper`, `sconosciuta`) x con/senza giornata (14); `aggregates` == vero per le 7 modalita' (7);
- numeri scritti (se vero e finto sbagliassero insieme): paper +5,00 / live -36,25 (bot -43,25 senza la manuale) / tutte -31,25;
  chiusura senza `mode` attribuita alla modalita' dell'apertura, riga senza `mode` = paper (1); modalita' senza righe = zeri con le
  chiavi vere (1);
- attraverso il servizio vero `_aggregati_cached(..., mode=paper|live)`: nessun CRITICAL «SOMMATI», numeri della sola modalita' (2).

| Codice | Esito |
|---|---|
| `0aa76dfa` (finto vecchio) | **28 failed** (23 TypeError `unexpected keyword argument 'mode'`, 2 firme diverse, 1 firma senza `mode`, 2 CRITICAL «SOMMATI» registrato) |
| dopo | **28 passed** |

Rifatto due volte: subito dopo averlo scritto e a fine lavoro, rimettendo nel file il sorgente di `0aa76dfa` (`git show`), poi
ripristino verificato con lo sha256 (`97809deb...33e3`).

## 5. Falsificazione (mutazioni del finto, una alla volta; `falsifica.py`, esito in `falsifica_esito.txt`)

| Mutazione | Rossi su 28 |
|---|---|
| M1 accetta `mode` ma lo ignora (somma paper e live) | 16 |
| M2 firma di prima (`**_k`, `mode` ignorato) | 18 |
| M3 modalita' non normalizzata (niente `strip`/`lower`) | 6 |
| M4 filtro ingenuo `r["mode"] == m` (chiusure e righe senza `mode` perse) | 13 |
| M5 modalita' sconosciuta filtra tutto invece di tornare tutte | 3 |
| M6 `aggregates` torna i numeri del bot invece dei totali di pagina | 6 |
| M7 default della firma diverso dal vero (`mode="paper"`) | 2 |
| M8 `aggregates` non passa `mode` alla coppia | 5 |

8 mutazioni su 8 rosse; dopo ognuna il file e' tornato allo sha256 originale `97809deb06cb8a3332c530cb0ab6f29504c6b8222c35f9fab433c1577d9133e3`.

## 6. Replay PRIMA e DOPO (punto d'ingresso unico)

Registrazioni scompattate da `registrazioni_banco/` in `_live_raw/<id>/` con la procedura di `registrazioni_banco/LEGGIMI.md`
(sha256 dei raw: 35760084 `8037bac2...a8`, 35797769 `c11894ab...5883`, quest'ultimo uguale a H §4.4). Comandi, identici prima e dopo:

```
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti --worker 3
python -m Betfair.stream.backtest.certifica omega 35797769 --scenari tutti --worker 3
```

PRIMA = codice di `0aa76dfa`; DOPO = codice di questo ramo. Stdout in `.txt`, stderr (log) in `.err`, stessa cartella.

| File | sha256 |
|---|---|
| `PRIMA_omega_35760084_tutti.txt` | `db37e6fcc9a7fde1022de57158ffbbedc4cbea1b88ae79378c9db6033de39636` |
| `PRIMA_omega_35760084_tutti.err` | `f83decd2df0239832afdfa889a917855f87d6fb1597e8d96725dd02eeb70488a` |
| `DOPO_omega_35760084_tutti.txt` | `6da7f807b6cf8eb129f248001801b1b0d8cdcdb3d4c1b2f9f6672892859d70d5` |
| `DOPO_omega_35760084_tutti.err` | `9ac5d69b735beb4f8252521bebc770bf4e45ba4657aca51fb287007acf319899` |
| `PRIMA_omega_35797769_tutti.txt` | `65628c07fca1126af7c2deb79258e3b1f42ba840f1c4474a019ec69b305cdcab` |
| `PRIMA_omega_35797769_tutti.err` | `9c6dd38e08c1883cda5754da93013f9ba915ac793df35c47fa5c9facdad765c2` |
| `DOPO_omega_35797769_tutti.txt` | `36ec22ad1123eabeaa0877b382ecbbb9f95867ea7552b4ecf9955f81cce0f07a` |
| `DOPO_omega_35797769_tutti.err` | `95c4601f6183582e1cedb3fb50b8568ea22a9e7cb60ff7d5f3a0750297f6cc15` |

Esito, uguale prima e dopo: 35760084 **22 partite senza violazioni, 0 con violazioni**; 35797769 **22 senza violazioni, 0 con
violazioni**. Exit code 0 in tutti e quattro i lanci. `codice bot ad274e67e2b2 (13 file)` uguale prima e dopo: l'impronta copre i
moduli di produzione e `omega.certificazione`, non il banco (`certifica.impronta`), quindi nessun file di Omega e' cambiato.

### 6.1 `confronta_referti`

```
python -m Betfair.stream.backtest.tools.confronta_referti PRIMA_omega_35760084_tutti.txt DOPO_omega_35760084_tutti.txt
  -> 701 righe | 701 righe | righe diverse: 0   (exit 0)
python -m Betfair.stream.backtest.tools.confronta_referti PRIMA_omega_35797769_tutti.txt DOPO_omega_35797769_tutti.txt
  -> 742 righe | 742 righe | righe diverse: 0   (exit 0)
```

### 6.2 Ogni riga cambiata (diff grezzo, nulla escluso)

| Partita | Righe | Cosa | Spiegazione |
|---|---|---|---|
| 35760084 stdout | 22 | `tempo: 35760084 [<scenario>] ...` | tempo macchina per scenario (macchina condivisa con altri delegati) |
| 35760084 stdout | 1 | `MEMORIA: picco per worker ...` | misura di RAM del momento (214-230 MB -> 211-225 MB) |
| 35760084 stdout | 1 | `TEMPO TOTALE: 242.1 s -> 266.1 s` | tempo macchina |
| 35797769 stdout | 22 | `tempo: 35797769 [<scenario>] ...` | tempo macchina |
| 35797769 stdout | 1 | `MEMORIA: ...` | misura di RAM del momento |
| 35797769 stdout | 1 | `TEMPO TOTALE: 1032.7 s -> 1465.9 s` | tempo macchina |
| 35797769 stdout | 1 | `LENTO: ...` (scenario piu' caro `rifiuti-betfair` -> `proposta-approvata`) | avviso di tempo, presente prima e dopo |
| 35760084 stderr | **-22** | `CRITICAL ... paper e live SOMMATI ... (catalogo 7.21)` | **il difetto corretto**: il servizio ora chiama il finto con `mode` |
| 35797769 stderr | **-24** | idem | idem (24 e non 22: gli scenari di riavvio rinascono come processo nuovo e l'avviso «una volta per processo» si riazzera, `_processo_nuovo`) |

Prova che lo stderr cambia SOLO per quelle righe: `PRIMA.err` senza le righe «SOMMATI» e' identico, riga per riga e nello stesso
ordine, a `DOPO.err` (`diff` vuoto, exit 0) su entrambe le partite. Restano, uguali prima e dopo, i CRITICAL attesi degli scenari
(posizione chiusa/ridotta dall'utente fuori dall'app, place LIVE a esito ignoto) e i WARNING del banco.

Perche' i numeri non cambiano: nel banco ogni riga di `omega_trades` nasce con la modalita' dello scenario (il servizio scrive
`control.mode`; le righe seminate dal banco usano `self.mode`, `replay_registrazioni.py:1422,1919`), quindi filtrare per modalita' non
toglie nessuna riga e gli aggregati sono gli stessi. Cambia il PERCORSO (quello di produzione, con `mode`), non il risultato.

## 7. Suite

- `Betfair/omega/` + `Betfair/stream/tests/test_banco_decisioni_sera_2026_10_08.py` + `test_banco_velocita_2026_10_08.py`:
  **1664 passed, 2 skipped** (39,6 s).
- `python -m pytest Betfair/ -q -p no:cacheprovider`: **11503 passed, 65 skipped, 6 xfailed, 0 failed** (481,5 s). 14 warning gia'
  presenti (thread dei test di battito tennis).
- Frontend non toccato (vitest/tsc non pertinenti).

## 8. PSB §6 e §7 per questo lavoro

- §7 n.27: chiuso per il finto del banco (firma, chiavi e tipi uguali al vero, provato contro il vero). n.35: test visto rosso (28/28)
  e mutazioni rosse (8/8). n.21: chiuso il SOMMARE del finto; **a livello di replay resta ⊘** (vedi reperto R1).
- §6.8: comando esatto, versioni (flumine 2.13.11, betfairlightweight 2.23.2), impronta del codice nei referti salvati.
- §6.9: **35797769 `tutti` sopra il tetto** (reperto R2). Nessuna ottimizzazione tentata: fuori mandato.
- Perimetro rispettato: nessun file in `Betfair/monitor/`, `Betfair/stream/backtest/**`, `omega_db.py`, strategia di Omega.

## 9. Reperti per l'utente (nessuno corretto qui)

- **R1 - n.21 non e' sollecitato dal replay.** Nessuno scenario di Omega ha righe di DUE modalita' nella stessa tabella, e nessun
  controllo del banco guarda i numeri per modalita': la mutazione M1 (finto che accetta `mode` e somma) lascerebbe il referto identico
  e senza CRITICAL. Oggi lo prova solo il test unitario. Inoltre `confronta_referti` scarta le righe di log: la sparizione (o la
  ricomparsa) del CRITICAL non la vede, l'ho provata con il diff dello stderr. Proposta: uno scenario «modalita-mista» (una riga
  regolata dell'altra modalita' seminata all'avvio, che deve lasciare invariati stop e tetti) e/o un controllo; cambierebbe il referto
  di Omega, quindi va deciso prima del congelamento di T0C.
- **R2 - Tempo.** 35797769 `--scenari tutti --worker 3`: 1032,7 s prima e 1465,9 s dopo (macchina a 4 core condivisa con altri
  delegati), contro tetto 600 s (PSB §6.9, CANT 11). 35760084: 242 s e 266 s (entro il tetto). La durata dichiarata prima del lancio
  (~7 min per 35797769) e' stata superata: segnalato qui.
- **R3 - Altri finti senza `mode` nei test unitari** (stesso schema del n.27, non toccati perche' fuori mandato):
  `Betfair/omega/test_omega_proposte_2026_09_17.py:174,535` e `Betfair/omega/tests/test_v3_any_other_2026_10_07.py:589`
  (`aggregates_coppia(self, day_start=None)`, e il loro `aggregates` torna 12 chiavi contro le 19 di `aggregate_trades`: mancano
  `events_traded`, `legs_today`, `won_today`, `lost_today`, `matches_won`, `matches_lost`, `live_now`). Il finto
  `DbVecchio` di `test_omega_chiuso_dall_utente_2026_09_16.py:762` e' invece VOLUTO (simula il DB storico).
- **R4 - Il vero.** Nessun difetto trovato nel percorso «in casa» di `omega_db.aggregates_coppia(mode)`: il test lo esegue davvero e
  coincide con le attese scritte. Il ramo RPC (`get_omega_aggregates_modalita`) non si puo' eseguire senza DB: la parita' RPC/in casa
  resta quella dichiarata dal vero e dai test del cantiere C (28/09); da verificare sul PC con il DB in sola lettura se serve.

## 10. Come rifarlo

```
python - <<'PY'   # procedura di registrazioni_banco/LEGGIMI.md
...
PY
python -m pytest Betfair/omega/test_omega_finto_aggregati_modalita_2026_10_09.py -q -p no:cacheprovider
python ARCHITETTURA_2026-10/tappa0/T0B4_FINTO_OMEGA/falsifica.py
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti --worker 3 > DOPO.txt 2> DOPO.err
python -m Betfair.stream.backtest.tools.confronta_referti ARCHITETTURA_2026-10/tappa0/T0B4_FINTO_OMEGA/DOPO_omega_35760084_tutti.txt DOPO.txt
```
