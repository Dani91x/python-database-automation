# A2 - Flussi e ladder (comparto A, W1-A2, ondata 1, 09/10/2026)

Schema del `COSA_FA.md` (`04_ARCHITETTURA_OBIETTIVO.md` par. 2.4). Quattro moduli nuovi in
`Betfair/nucleo/betfair/`: `flusso_ordini_conto.py`, `ladder.py`, `profili.py`, `flusso.py`.
Nessun file di oggi e' cambiato: l'aggancio e' dell'ondata 2 (referto `ARCHITETTURA_2026-10/ondata1/W1-A2/REFERTO.md` par. 8).

## 1. Scopo

- `flusso_ordini_conto.FlussoOrdiniContoBetfair` (`contratto.FlussoOrdiniConto`): lo stream degli ordini del CONTO,
  senza filtro di strategia, in sola lettura, con ripresa `initialClk`/`clk`: ogni ordine (app, bot, sito) in tempo reale.
- `ladder.LadderEvento` (`contratto.Ladder`): il ladder della UI pubblicato a OGNI cambio del book (coalescenza minima
  20 ms per mercato) invece del giro fisso di 200 ms, con lo STESSO JSON del topic `ladder` di oggi; il DB in un thread suo.
- `profili`: i quattro `ProfiloFlusso` (runner calcio, runner tennis, scanner, sessione scalper) con i valori ESATTI di oggi.
- `flusso.GestoreFlussi` (`contratto.FlussoMercato`): gli stream dei prezzi per profilo: suddivisione in connessioni,
  sottoscrizione sostitutiva, budget delle connessioni, ripresa, salute, consumatori.

## 2. Entrate

| Modulo | Entrate |
|---|---|
| `flusso_ordini_conto` | `contratto.Sessione` (`client()` = `betfairlightweight.APIClient` con sessione valida; `rinnova_se_serve()`); messaggi `ocm` dal socket Betfair |
| `ladder` | `MarketBook` della libreria (`consumatore(book)` o `sorgente(market_id)`), `push_a_ogni_cambio(market_id)`, `meta(market_id) -> MetaLadder | None`, `canale_attivo()` |
| `profili` | nome del profilo, ambiente (`os.environ` di serie, letto alla chiamata) |
| `flusso` | `contratto.Sessione`, `ProfiloFlusso`, `imposta_mercati(ids)`, `manutenzione()`; messaggi `mcm`/`status` dal socket |

## 3. Uscite

| Modulo | Uscite |
|---|---|
| `flusso_ordini_conto` | `OrdineDalConto` ai consumatori (thread di consegna; filtro per mercato), `ordini(market_id)`, `posizioni(market_id)` (`mb`/`ml` del conto), `ordini_non_confermati()`, `stato()` (vivo/muto/assente, clk, riconnessioni, eta' ultimo messaggio e ultimo ordine, `sottoscrizione` ripresa_clk|da_zero, `seme_rest_necessario`, `ordini_scartati`) |
| `ladder` | `pubblica("ladder", riga)` (riga = `{event_id, market_id, market_type, market_name, status, ladder:{updated_ms, selections}}`), `scrivi_db(riga)` a `db_sec` write-on-change, `snapshot(market_id)`, `stato()` |
| `profili` | `ProfiloFlusso`, `filtro_dati(profilo)` (il `marketDataFilter` di betfairlightweight) |
| `flusso` | `MarketBook` GIA' in EUR (`valuta.converti_libro`, K1) ai consumatori, `book(id)`, `stato()` (stesse chiavi di `GestoreFrammenti.stato()` + `profilo`, `battito_eta_s`), `stato_flusso(id)` in `vivo|muto|assente`, `capacita()` |

## 4. Dipendenze ammesse (04 par. 2.3)

- betfairlightweight (solo qui, nel comparto A): `APIClient.streaming.create_stream`, `StreamListener`, `OrderStream`,
  `UnmatchedOrder`, enum `Streaming*`, `filters`.
- Funzioni pure di oggi IMPORTATE (riuso, mai copia): `Betfair/stream/recorder.serialize_book`,
  `Betfair/stream/ladder_canale.StatoLadder.versione` e `updated_ms_del_book`, `Betfair/stream/stream_muto.stato_da_battiti`
  (+ costanti `BATTITI_PER_SOGLIA`, `HEARTBEAT_MS_RICHIESTO`), `Betfair/stream/valuta.converti_libro` e `valuta.CAMBIO` (K1).
- Riscritte con test di parita' (pezzi di file grandi legati a flumine): helper del ladder di `runner.py`/`tennis_runner.py`,
  `frammenti_mercato.pianifica` e `GestoreFrammenti.massimo_adesso`.
- Nessun import di bot, di Supabase, di flumine (salvo `recorder.py` che importa flumine per la sua classe; la funzione
  usata e' pura).

## 5. Funzionalita' coperte (`01_FUNZIONALITA.md`) e test che le provano

| Id | Cosa | Test |
|---|---|---|
| A-052 | helper del ladder (livelli, WOM, selezione, firma SHA-1, payload), calcio e gemelli tennis | `test_a2_ladder_parita.py::test_payload_e_firma_identici_su_ogni_book`, `::test_casi_limite_identici_alle_due_copie_di_oggi`, `::test_firma_indipendente_dall_ordine_dei_runner` |
| A-053, A-069 | `ladder_worker` calcio e tennis: canale + DB, firme separate, stato nella firma, giro a costo zero senza client | `test_a2_ladder_parita.py::test_sequenza_del_topic_identica_al_worker_di_oggi[calcio|tennis]`, `test_a2_ladder.py::test_canale_senza_client_*`, `::test_db_nel_suo_thread_*`, `::test_thread_vero_*` |
| A-054 | `updated_ms` strettamente crescente, stesso payload a parita' di firma (riuso di `StatoLadder.versione`) | `test_sequenza_del_topic_*` (controllo per mercato), `test_a2_ladder.py::test_book_invariato_*` |
| A-046 (parte ladder) | chiusura: calcio marca CLOSED l'ultimo book, tennis serializza il book chiuso | `test_a2_ladder.py::test_chiusura_come_oggi_per_sport`, `::test_calcio_senza_book_prima_della_chiusura_non_pubblica`, `test_sequenza_*` (21 mercati CLOSED) |
| A-062 (stream) | parametri di stream in `config_stream.py` e gemelli | `test_a2_profili.py` (3 ambienti in processo a parte) |
| A-029, A-030 | gestore delle connessioni, piano puro (un mercato non cambia connessione) | `test_a2_flusso_piano.py::test_piano_identico_a_frammenti_mercato_su_griglie`, `test_a2_flusso.py::test_suddivisione_180_*` |
| A-031 | battito per connessione, `heartbeatMs` e `connectionsAvailable` (anche 0) | `test_a2_flusso_piano.py::test_budget_identico_a_gestore_frammenti`, `::test_vince_l_ultimo_connections_available_letto`, `test_a2_flusso.py::test_riserva_e_connections_available` |
| A-032 | riconnessione con `initialClk/clk`, mai dopo la chiusura | `test_a2_flusso.py::test_ripresa_con_initial_clk_e_clk_dopo_la_caduta`, `::test_cambio_di_mercati_a_connessione_giu_*`, `::test_ferma_chiude_tutto_*` |
| A-033 | connessione muta > 180 s chiusa e mercati ripiazzati; rifiuto e pausa 300 s | `test_a2_flusso.py::test_manutenzione_chiude_la_connessione_muta_e_ripiazza`, `::test_rifiuto_di_betfair_*` |
| A-034 | sottoscrizione a caldo sostitutiva sulla stessa connessione | `test_a2_flusso.py::test_suddivisione_180_e_risottoscrizione_solo_della_connessione_che_cambia` |
| A-077 (parte stream) | salute per mercato, 503 = latente | `test_a2_flusso.py::test_salute_vivo_muto_assente_e_503` |
| T11 (nuova, priorita' dell'utente) | stream ordini del conto senza filtro, sola lettura, anche ordini del sito senza `rfo`/`rfs` (esempio ufficiale), BSP, partenza da zero dichiarata | `test_a2_flusso_ordini_conto.py` (22 test) |
| K1 (valuta) | size dello stream GBP -> EUR alla fonte | `test_a2_flusso.py::test_size_dello_stream_convertite_gbp_eur_alla_fonte` |

Restano al codice di oggi (ondata 2 o tappe successive): A-020..A-028, A-035..A-045 (follow, catalogo, ciclo di vita del
runner, framework flumine), A-047..A-051 (tee raw: P5), A-055..A-061 (live_now, board, canali), A-063..A-068, A-070..A-075
(tennis), A-076 (piano a shard `id mod N` dello scanner: vedi referto par. 9, D2), A-078..A-086.

## 6. Interruttore previsto

`ARCH_LADDER=vecchio|ombra|nuovo` (T6); `ARCH_FLUSSO_<SPORT>=vecchio|nuovo` (T19, l'ombra e' sul banco);
`ARCH_ORDINI_CONTO=spento|ombra|acceso` (proposto, T11). Di serie: vecchio / spento.

## 7. Come si sostituisce

Un modulo nuovo che implementa lo stesso protocollo di `contratto.py` e fa passare `tests/test_a2_*.py` (i test di parita'
importano il codice di oggi: restano validi finche' il vecchio esiste; al taglio diventano test d'oro sui valori registrati).

## 8. Come si prova da solo

```
python -m pytest Betfair/nucleo/betfair/tests/ -q -p no:cacheprovider -k a2
python ARCHITETTURA_2026-10/ondata1/W1-A2/misura_ladder.py          # misura della cadenza
```
Finti: un server della Exchange Stream API su 127.0.0.1 in TLS (`tests/test_a2_finti.py`), con i messaggi e le chiavi
dello schema ufficiale; dalla parte nostra TUTTA la libreria vera (`BetfairStream`, listener, cache). `APIClient` vero con
token a mano; le chiamate di scommessa sono trappole. Book: registrazioni vere `registrazioni_banco/35760084`, `35797769`.

## 9. Misure

`ARCHITETTURA_2026-10/ondata1/W1-A2/misura_ladder.py` (tempo della registrazione, `pt`): pubblicazioni e attesa
"arrivo del book -> pubblicazione" del ladder nuovo (20 ms) contro il worker di oggi (200 ms). Numeri nel referto par. 4.
Dal vivo: la sonda `ladder_pub_pt_ms` della Salute (T0A), in ombra.
`ARCHITETTURA_2026-10/ondata1/W1-A2/misura_cpu_ladder.py`: CPU del thread del ladder nuovo contro recorder +
worker di oggi, con N partite contemporanee (copie della registrazione 35797769). Numeri nel referto par. 10.

## 10. Voci di `PROCESSO_STANDARD_BOT.md`

Sollecitate: par. 6.1 (stream nativo `mcm` letto dal listener vero, stati OPEN/SUSPENDED/CLOSED), 6.5 (la riga del
ladder che la UI legge, stesse chiavi), 6.6 (connessioni e limiti Betfair), 6.7 (scenari di caduta, 503, rifiuto,
falsificazione), 6.8 (comandi esatti, versioni), par. 7 n. 9, 17 (sospeso/chiuso nel ladder), 19 (stato perso alla
caduta: ripresa con clk), 20 (battito vivo != dati: `vivo` per mercato solo con un book), 27 (finti con le chiavi vere),
29, 30, 33, 35. ⊘ con causa nel referto par. 7.


## 11. Dopo la revisione indipendente (09/10)

Correzioni (dettaglio, file:riga, test e mutazioni nel referto par. 10):

- **Ordini non confermati**: a fine immagine di SOTTOSCRIZIONE (`SUB_IMAGE` intera o `SEG_END`, anche vuota), di
  MERCATO o di RUNNER, ogni EXECUTABLE noto non riportato passa a `confermato=False` (riconsegnato ai consumatori) e in
  `ordini_non_confermati()`; torna confermato alla prima notizia dallo stream.
- **Posizioni**: una `fullImage` di mercato SOSTITUISCE le posizioni del mercato (base del P&L del comparto C).
- **Importi assenti**: None (mai 0) e dichiarati in `OrdineDalContoEsteso.campi_assenti`.
- **Backoff** azzerato dopo una connessione sana (ocm/mcm ricevuti o su oltre `VIVA_DOPO_S` = 60 s), nei due moduli:
  DIVERGENZA MIGLIORATIVA dichiarata rispetto a `frammenti_mercato.py` di oggi (che non lo azzera mai).
- **Watchdog** nei due moduli: connessione su senza NESSUN messaggio oltre 3 heartbeat (`BATTITI_WATCHDOG`, la soglia
  del "muto" dell'app; Betfair dice 2 = "forse disconnesso") -> socket chiuso, ripresa con `initialClk`/`clk`; evento
  `flusso_muto` nel gestore dei prezzi.
- **Ladder**: un errore di pubblicazione o di `marca_canale` rimette il SOLO mercato in attesa (gli altri del lotto
  escono); meta assente = attesa con riprova ogni `RIPROVA_META_S` (0,2 s, nessun giro a vuoto); invii SALTATI dal canale
  (`saltati`, contatore di `local_channel.statistiche()`) = ripubblicazione di tutti i mercati al massimo ogni
  `RIPARO_MIN_S` (0,5 s); la chiusura del calcio marca l'ULTIMO book ricevuto (anche se fuso), come il recorder di oggi.
- **Concorrenza del gestore**: nessuna rete sotto i lock della consegna (consumatori letti da una lista sostituita per
  intero; risottoscrizioni fuori dal lock del gestore; connessione e autenticazione fuori dal lock della connessione).
- **Eventi** del contratto nel gestore dei prezzi: `aggiungi_osservatore(cb)` con `mercato_chiuso`, `flusso_muto`,
  `capacita_cambiata`.
- **Slot di connessione** (stream ordini): con `disponibili()` <= riserva (1) NON apre e lo dice (`slot="in_attesa"`);
  un rifiuto di Betfair mette in pausa 300 s (`slot="negato"`). Default prudente; la scelta resta all'utente (referto 8.1).
- **Sessione**: `SessioneConSegnalazione.segnala_sessione_morta(motivo)` (estensione proposta) se c'e', altrimenti
  `rinnova_se_serve()`; nei due moduli.
- **Potatura**: ordini EXECUTION_COMPLETE oltre `TETTO_COMPLETATI` (5000); book dei mercati non piu' sottoscritti.
- **Valuta**: la conversione GBP->EUR del gestore non si spegne piu' dal costruttore (`converti_valuta` tolto).
- Orologio MONOTONO per vivo/muto dello stream ordini; ASCII; codice morto tolto.

Test nuovi: `tests/test_a2_ordini_revisione.py`, `tests/test_a2_flusso_ladder_revisione.py`.
