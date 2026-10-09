# B - STATO DELLA PARTITA (W1-B, ondata 1, 09/10/2026)

Schema del `COSA_FA.md` (04 par. 2.4). Codice: `Betfair/nucleo/stato_partita/`. Contratto (fisso):
`contratto.py`. Scheda: `ARCHITETTURA_2026-10/03_SCHEDE_COMPONENTI/B_PUNTEGGI_STATO_PARTITA.md`.
Referto: `ARCHITETTURA_2026-10/ondata1/W1-B/REFERTO.md`.

## 1. Scopo

Lo stato della partita (minuto, tempo, fase, gol, rossi, corner, gialli, set/game del tennis, calcio
d'inizio, eta' in tre parti, fonte vera, verdetto della condizione 11 sui prezzi) calcolato UNA volta,
tenuto in memoria e consegnato a evento a chi si iscrive. Oggi lo stesso numero si ricalcola in 9
punti, il calcio d'inizio ha 4 copie, lo stato viaggia su 5 relay (scheda B par. 3). Qui ogni valore e'
IL valore di oggi: le funzioni di oggi sono importate, mai copiate; dove le copie di oggi divergono il
modulo le espone tutte e la divergenza e' scritta per l'utente.

## 2. Entrate

| Entrata | Da dove | File |
|---|---|---|
| righe di `safe_strategy_scan` | `ScanRowCache` di oggi (DB, o DB+canale con `PUNTEGGI_CANALE`) | `adattatori/ips.py` `FonteIpsScanner` |
| feed fresco o IPS diretto (runner calcio) | `fresh_payload` + `BetfairInPlayProvider` | `adattatori/ips.py` `FonteIpsRunner` |
| feed fresco o `get_scores` diretto (runner tennis) | come `score_and_now_worker` | `adattatori/ips_tennis.py` |
| API-Football e circuito primario/ripiego | `ApiFootballProvider`, `ScorePoller` di oggi | `adattatori/api_football.py` |
| sidecar `.scores.jsonl` / `.score.jsonl` | `banco_comune.carica_punteggi` | `adattatori/registrazione.py` |
| righe e battito dal canale 47336 | `canale_scan.ClientScan`/`CacheScan` | `adattatori/canale.py` |
| `MarketBook` di un mercato della partita | flumine / betfairlightweight | `servizio.osserva_book` |

Tutte le fonti restituiscono la stessa busta (`adattatori/lettura.py`: `fonte`, `trasporto`, `sport`,
`riga`, `grezzo`, `grezzi`, `scanner_s`, `stato_scanner`, `istante_ms`, `origine`).

## 3. Uscite

- `ServizioStatoPartita.stato(event_id) -> StatoPartita | None` (contratto);
- `iscrivi(cb)` (contratto): `cb(StatoPartita)` a ogni cambio, nessuna SELECT per chi legge;
- `iscrivi_eventi(cb)` (estensione): `StatoCambiato`, `GolSegnato`, `FaseCambiata`, `FlussoInterrotto`,
  `FlussoRipreso` (`servizio.py:59-98`);
- `prezzi_vivi(event_id, mercati)`: `flusso_prezzi.valuta` sull'ultima riga, per i mercati di una decisione.
- Funzioni pure di `calcolo.py` (stato da grezzo/riga/API-Football/tennis, `ko_epoch_ms`, `KoPerMercato`,
  `KoUnico`, `fase_partita`, `minuto_da_orologio`) e di `freschezza.py` (`eta_riga_s`, `eta_punteggio_s`,
  `eta_scanner_da_stato_s`, `calcola_eta`).

## 4. Dipendenze ammesse

Codice di oggi, solo funzioni pure o classi riusate, importate (mai copiate):
`scores/betfair_inplay.parse_score_dict`, `scores/scan_feed` (`row_age_sec`, `fresh_payload`,
`IPS_SCORE_LAG_SEC`, `ScanRowCache`), `scores/poller.ScorePoller`, `scores/api_football`
(`parse_fixture_response`, `ApiFootballProvider`), `scalper/atlante_v4` (`tempo_da_stato_ips`,
`tempo_da_payload`), `omega/omega_engine` (`mission_phase`, `minute_from_clock`),
`tennis_scalper/tennis_score` (`parse_tennis_scores`, `TennisScore`), `stream/flusso_prezzi`,
`backtest/banco_comune.carica_punteggi`. I moduli che all'import aprono qualcosa (`betfair_inplay` ->
`urllib3` crea un socket di prova IPv6; `api_client` -> `config` legge `.env`) o pesano (`atlante_v4` ->
`numpy`, `banco_comune`) si importano al primo uso. Nessun import di supabase. NOTA: `mission_phase`
(Omega), `atlante_v4` (scalper) e `tennis_score` (vecchio pacchetto tennis) stanno oggi in pacchetti di bot:
si importano come funzioni pure (brief comune regola 3); il trasloco (`tennis_score` ->
`adattatori/ips_tennis.py`, fase/tempo nel nucleo) e' della tappa T9 vera, con il test di parita' gia' pronto.

## 5. Funzionalita' coperte (id di `01_FUNZIONALITA.md`) e test

| Id | Cosa | Dove | Test |
|---|---|---|---|
| B-001, B-002 | tipo dello stato e fonte sostituibile | `contratto.py` (fisso), `adattatori/*` | `test_b_servizio::test_rispetta_il_contratto` |
| B-003, B-004, B-005 | parser IPS calcio (minuto 0, forme del punteggio, statistiche) | `calcolo.stato_calcio_da_grezzo` | `test_b_calcolo::test_parita_ogni_riga_*`, `test_casi_limite_con_gli_arbitri` |
| B-007, B-015, A-083 | IPS diretto e provider dal feed | `adattatori/ips.FonteIpsRunner` | `test_b_adattatori::test_runner_sceglie_come_scan_feed` (56 casi) |
| B-008, B-009 | API-Football | `adattatori/api_football.FonteApiFootball`, `calcolo.stato_calcio_da_api_football` | `test_fonte_api_football`, `test_le_righe_registrate_dicono_la_loro_fonte` |
| B-010 | circuito primario/ripiego (U-10 invariata) | `adattatori/api_football.FonteCircuitoCalcio` | `test_circuito_identico_al_poller_di_oggi` |
| B-011, B-012, B-013, A-082, D-014, D-020 | cache per processo, fusione col canale, battito | `adattatori/ips.FonteIpsScanner`, `adattatori/canale.py` | `test_fonte_scanner_da_le_righe_senza_filtro`, `test_canale_righe_battito_e_stato` |
| B-014 | `fresh_payload` (15 s / scanner vivo 30 s / tetto 180 s) | riusata in `FonteIpsRunner.grezzo_dal_feed` | griglia + `test_zero_a_zero_fermo_con_scanner_vivo_resta_sul_feed` |
| B-016 | eta' onesta = riga + 3 s | `freschezza.eta_punteggio_s` | `test_b_freschezza`, `test_b_parita_banco` (per tick) |
| B-018 | `apply_score_state` (numeri della riga) | `calcolo.stato_calcio_da_riga` | `test_b_parita_banco` |
| B-030, B-031, B-032, E5-060, E5-061 | tennis: `TennisScore`, `key()`, pressione, parser | `calcolo.stato_tennis_*`, `chiave_tennis` | `test_tennis_chiave_e_pressione_uguali_al_parser` (9 casi) |
| B-034 (parte punteggio) | strada feed/diretto del runner tennis | `adattatori/ips_tennis.py` | `test_tennis_feed_diretto_errore` |
| B-036, B-037 (valuta), E3-S08 | condizione 11 dentro lo stato | `servizio.esito_flusso`, `prezzi_vivi` | `test_prezzi_vivi_per_i_mercati_della_decisione`, `test_b_parita_banco` |
| B-045, B-044 | fase e tempo da stato IPS | `calcolo.fase_partita`, `tempo_partita` | sidecar + per tick + divergenze |
| B-047 | `_ko_epoch_ms` (4 copie) | `calcolo.ko_epoch_ms`, `KoPerMercato`, `KoUnico` | `test_ko_identico_alle_4_copie_sui_book_veri`, `test_ko_bordi_e_divergenza_della_cache_unica` |
| B-049 | sidecar per registrazioni (lettura) | `adattatori/registrazione.py` | `test_registrazione_scorre_come_il_banco`, `test_registrazione_tennis` |
| B-050 | parita' paper/live: una sola strada, nessun ramo per modo | tutto il comparto (nessun parametro di modo) | per costruzione (nessun `mode` nel codice) |
| D-017 (parte) | punteggio/minuto per chi oggi legge `live_now` | `servizio.iscrivi` | `test_segui_stato_iscrivi_ed_eventi` |

Restano al codice di oggi (ondata 2 o tappa T9): B-006/B-019/B-020/B-025 (timeline), B-017/B-021/B-022/B-023 (poll
batch dello scanner, lato scanner per ultimo), B-024/B-026/B-027/B-035/A-070/G-011 (scritture `live_now`/`tennis_live_now`),
B-028/B-029 (upload e curatore), B-033 (pollatori legacy), B-038..B-043/D-015/D-016 (involucri e soglie dei bot: U-08),
B-046/B-048 (osservatori dello scalper e minuto di telemetria: leggeranno `stato()`, U-11), B-051/B-052/B-053, E3-S07 (scanner).

## 6. Interruttore previsto

`ARCH_STATO_PARTITA=vecchio|ombra|nuovo` (05 T9). Spento = il codice di oggi riga per riga. Dettaglio
dell'aggancio: referto par. 8.

## 7. Come si sostituisce

Una fonte nuova = una classe con `nome` e `leggi(event_ids) -> {event_id: busta}` (busta di
`adattatori/lettura.py`) in `adattatori/`, piu' il suo test di parita'. Il servizio, il calcolo e i bot
non cambiano. Oggi la stessa sostituzione tocca >= 11 file (scheda B par. 4.5).

## 8. Come si prova da solo

```
python -m pytest Betfair/nucleo/stato_partita/tests -q -p no:cacheprovider -m "not cert"   # ~45 s
python -m pytest Betfair/nucleo/stato_partita/tests/test_b_parita_banco.py -q -p no:cacheprovider -s   # cert, ~150 s
```
I test leggono le registrazioni da `registrazioni_banco/` (gz) e scompattano in una cartella temporanea:
nessun file fuori da `tmp`, nessuna rete, nessun DB.

## 9. Misure

Parita' 100% su 220 righe di sidecar e su 17.796 giri per tick dello scanner vero (6.076 + 11.720), 0
divergenze; numeri e durate nel referto par. 3-5. Latenza: il servizio non aggiunge relay ne' SELECT per
chi si iscrive (sveglia in processo); la misura del ritardo reale e' dell'ombra (ondata 2).

## 10. PROCESSO_STANDARD_BOT par. 6/7

Referto par. 7.
