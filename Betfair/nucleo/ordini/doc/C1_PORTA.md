# C1 - Porta degli ordini (W1-C1, ondata 1, 09/10/2026)

Schema del `COSA_FA.md` (04 par. 2.4). Il coordinatore lo unira' al `COSA_FA.md` di `Betfair/nucleo/ordini/`.
Referto con numeri, parita' e divergenze: `ARCHITETTURA_2026-10/ondata1/W1-C1/REFERTO.md`.

## 1. Scopo

UNA porta per gli ordini (`PortaLocale`, contratto `PortaOrdini`): riceve `RichiestaOrdine`, risponde `Ack`, pubblica la
sequenza di `EventoOrdine` per attore con `seq` contiguo, con le garanzie del motore del runner di oggi (dedup per ref che
sopravvive al riavvio, freni, minimi .it, diario write-ahead, esito ignoto mai ok) e in piu' il tetto delle transazioni/ora
UNO per conto e SOLO per il live (paper e live mai sommati), stato per ref monotono, dedup atomico anche fra due porte sullo
stesso archivio. Sotto, un `Esecutore` iniettato (oggi: il dispatch del runner, live e paper, con i `params` del bot).

## 2. Entrate

- `RichiestaOrdine` (contratto) piu' `ExtraComando` (max_eta_ms, params del bot: arrivano all'esecutore che dichiara
  `accetta_params`, altrimenti la richiesta e' RIFIUTATA `params_non_serviti`); `RichiestaComposta` (estensione proposta:
  green-up, cash-out, dutch) e' riconosciuta e RIFIUTATA (`azione_composta_sopra_la_porta`): per contratto vive sopra.
- Le tre forme di oggi, tradotte da `adattatore_comando.py`: comando del canale (`valida_comando`), riga della coda calcio
  `betfair_live_order_requests`, payload della coda tennis `tennis_live_order_queue`.
- Iniettati: `Esecutore`, `FreniConto` (kill-switch, modo di processo, blocco del modo effettivo, eta' dei settings; quello di
  oggi e' `controlli.FreniDiOggi`), `Archivio` (`nucleo/dati/contratto.py`, tabelle locali `ordini_ref_visti` e
  `ordini_seq`, solo `leggi` e `scrivi` con la semantica VERA di G1: nessuna `transizione`; UNA porta per
  archivio nel processo, la seconda e' rifiutata `ArchivioGiaInUso`), diario
  (`motore_ordini.Diario`), `ContatoreTransazioni`, orologio, verifica della riduzione, guardia d'avvio, fonte della posizione.
- Eventi consumati: aggiornamenti successivi di un ordine (`PortaLocale.notifica`, dal flusso degli ordini).

## 3. Uscite

- `Ack` (accettato/rifiutato, `seq`, motivo con i CODICI del motore: `parametri_invalidi`, `mode_non_servibile`,
  `kill_switch`, `reduces_liability_non_verificabile`, `guardia_avvio`, `settings_stantie`, `comando_scaduto`,
  `diario_non_scrivibile`, `SOTTO_MINIMO_NON_PIAZZABILE`, `ref_gia_visto`; nuovi: `MAX_TRANSACTION_COUNT`,
  `archivio_non_disponibile`, `azione_composta_sopra_la_porta`, `params_non_serviti`).
  Ref gia' visto (memoria, diario o `ordini_ref_visti`), in ogni fase (in volo, ignoto, terminale), anche dopo il riavvio:
  l'`Ack` ORIGINALE (`accettato` e `seq` della prima risposta), motivo `ref_gia_visto`, 0 invii: parita' col motore
  (`motore_ordini.py:997-1005`). Lo stato del ref non cambia; l'esito lo dicono `stato`/`eventi`.
- Memoria: oltre 5.000 ref si dimenticano SOLO gli ordini chiusi; se i ref aperti superano il tetto la memoria cresce e lo
  dice a WARNING (nessun ordine aperto perde stato). Stato monotono anche sull'esito del place (lo stream arrivato prima
  della risposta REST non viene sovrascritto).
- `EventoOrdine` per attore: in memoria (500), ai consumatori iscritti (`aggiungi_consumatore`), con `eventi(attore, da_seq)` e
  `da_seq(attore, dal)` (`RispostaDaSeq` con `completo`). Fasi: `FASE_DA_MOTORE` in `esecutori/runner.py`; esito ignoto =
  `ignoto` con `codice_errore="ESITO_IGNOTO"`; tennis: `portata_al_minimo` sull'apertura portata al minimo. Le callback
  dei consumatori girano FUORI da ogni lucchetto (una callback puo' chiamare `invia`).
- `StatoOrdine` per ref (`stato`), `in_volo()` dopo un riavvio, `ContatoreTransazioni.stato()` per la «Salute».
- `posizione`: delegata (comparto C2); senza fonte iniettata solleva `NotImplementedError`.

## 4. Dipendenze ammesse (04 par. 2.3)

`nucleo/comuni.py`, `nucleo/ordini/contratto.py`, `nucleo/dati/contratto.py` (solo il protocollo `Archivio`). Codice di oggi
importato SOLO dentro le funzioni (riuso, nessuna copia): `motore_ordini` (`valida_comando`, `Diario`, codici, `fase_da_riga`,
`riga_specchio_da_esito`, `codice_errore`), `live_order_worker` (`_LOCAL_ROW_KEYS`, `_dispatch` e i suoi shim, freni),
`tennis_live_order_worker.parse_order_payload`, `config_stream.LIVE_TRANSACTION_LIMIT`, `betfairlightweight.enums`
(codici d'errore d'istruzione). All'import: solo `trading/minimi_it.py` (senza dipendenze). Prova: `test_c1_import.py`.
Nessun import di supabase, di flumine o di un bot (i bot sono solo ARBITRI nei test).

## 5. Funzionalita' coperte (`01_FUNZIONALITA.md`) e test

| Voce | Cosa | Dove | Test |
|---|---|---|---|
| C-002 | schema del comando, rifiuti identici | `adattatore_comando.richiesta_da_comando` (chiama `valida_comando`) | `test_c1_adattatore_comando.py` (andata e ritorno, piano identico su comandi VERI di Safe, 14 rifiuti identici) |
| C-003 | ack, `seq` per attore, `da_seq` 500 | `porta.py` `_nuovo_seq` + `_memorizza` (stesso lucchetto), `da_seq`, `eventi`; `eventi.py` | `test_c1_porta.py` (push perso riparato, memoria superata, seq per attore, seq mai indietro); `test_c1_eventi.py` (parita' con `MemoriaComandi`) |
| C-004 | dedup per ref anche dopo il riavvio (memoria + diario + righe `ordini_ref_visti` che la porta scrive e rilegge sotto il suo lucchetto; una porta per archivio) | `porta._ref_e_dedup`, `_dedup`, `apri`, registro `_ARCHIVI_IN_USO` | `test_c1_porta.py` (stessa vita, riavvio da archivio, riavvio da diario, archivio guasto fail-closed); `test_c1_revisione.py` (seconda porta rifiutata, ack fantasma, ignoto dopo il riavvio, ack originale in ogni fase, rifiuto dopo il riavvio, parita' DIRETTA col `MotoreOrdini` di oggi, finto = vero) |
| C-011, C-013 (forma) | riga di coda di Safe, riga del dispatch | `adattatore_comando.riga_coda_da_richiesta` / `richiesta_da_riga_coda` | `test_c1_adattatore_comando.py` (riga VERA di `enqueue_place` con la normalizzazione della RPC; riga = riga del motore) |
| C-020, C-021, C-028 (decisione) | kill-switch sulle aperture, modo della RIGA | `controlli.controlla` | `test_c1_controlli.py::test_controlla_parita_col_motore` (griglia di 768 casi = `_controlla`); `test_c1_porta.py` |
| C-022 (rate) | transazioni/ora per CONTO, solo live | `controlli.ContatoreTransazioni` | parita' col control VERO `MaxTransactionCount` e con l'esecuzione VERA di flumine; somma su 3 attori; paper escluso (`test_c1_revisione.py`) |
| C-030, C-031, C-035, C-036, C-072 (taglia) | minimi .it, punta 0,50, porta al minimo, taglia tennis, scalper | `minimi.py` | `test_c1_minimi.py` (griglia contro le 5 definizioni + `verdetto_minimi` + politica RIFIUTA del desktop `order_exec` + apertura tennis al minimo `esecutore_tennis`) |
| C-032 (senza equivalente), C-044 (taglia non ritentata) | verdetto dei minimi della porta | `porta._minimi` | `test_c1_porta.py::test_ciclo_di_vita_con_le_risposte_vere`, `test_minimi_punta_050_e_sotto_minimo` |
| C-040, C-041 (place/cancel/replace) | esecuzione | `esecutori/runner.py` (wrapper di `_dispatch`) | `test_c1_esecutore_runner.py` (client della riga, fase = motore) |
| C-042 (riduzione mai creduta) | `reduces_liability` | `adattatore_comando`, `controlli.controlla` | rifiuto `reduces_liability_non_verificabile` col kill-switch |
| C-050 | fasi, `esito_ms`, seq mai indietro | `porta._emetti`, `FASE_DA_MOTORE` | `test_c1_porta.py`, `test_c1_esecutore_runner.py::test_fase_uguale_al_motore_di_oggi` |
| C-055 | diario write-ahead (`inviato`, `ordine`, `esito`, `evento`) | `porta._accetta`, `EsecutoreRunner._hook` | `test_diario_write_ahead_prima_dell_esecutore`, `test_diario_ordine_prima_di_place_order`, `test_diario_non_scrivibile_niente_ordine` |
| C-045/C-046 (principio) | esito ignoto mai ok, mai ritentato | `porta._esegui` | `test_esito_ignoto_mai_ok_mai_ritentato`, `test_eccezione_dentro_place_order_e_esito_ignoto` |

Restano al codice di oggi (non coperte qui): C-001 (thread del motore), C-005 (`/order` del desktop), C-006..C-010 (le tre
porte dei bot), C-012, C-023, C-024, C-025, C-026, C-027, C-029, C-033, C-034, C-037, C-043, C-047..C-049, C-051..C-054,
C-060..C-082 (place-and-trim, equivalente, aggancio al volo, sorveglianza, specchio, riconciliazioni, tennis, banco).

## 6. Interruttore previsto

`ARCH_ORDINI_PORTA=vecchio|nuovo` PER ATTORE (05 T10), di serie `vecchio`. Gli interruttori di oggi (`*_ORDINI_VIA_CANALE`,
`MOTORE_ORDINI_CANALE_TENNIS`, `ESITI_ORDINI_CANALE`) restano e li accende solo l'utente.

## 7. Come si sostituisce

Un esecutore nuovo implementa `contratto.Esecutore` (`place/cancel/replace -> EventoOrdine`, seq 0, `submin_disponibile`
opzionale; `accetta_params` + argomento `params` per ricevere i params del bot) e deve far passare `test_c1_porta.py` (con il suo finto) e un test come `test_c1_esecutore_runner.py`. Una porta
nuova implementa `PortaOrdini` e deve far passare `test_c1_porta.py`. Le taglie si cambiano SOLO in `minimi.py` dopo una
decisione dell'utente sulle divergenze (referto par. 9) e con `test_c1_minimi.py` aggiornato insieme.

## 8. Come si prova da solo

```
python -m pytest Betfair/nucleo/ordini/tests/test_c1_*.py -q -p no:cacheprovider
python ARCHITETTURA_2026-10/ondata1/W1-C1/falsifica_c1.py <radice del repo>
```
Finti con chiavi e tipi del vero: risposte `PlaceOrders/CancelOrders/ReplaceOrders` di betfairlightweight dal JSON camelCase
di Betfair; client flumine VERI (`clients.BetfairClient`), ordini flumine VERI da `build_order`; `MaxTransactionCount` e
`BetfairExecution` VERI; diario VERO su disco; consumatore di oggi `MemoriaComandi` come arbitro.

## 9. Misure

Nessuna misura di latenza dichiarata come miglioria (la porta e' sincrona e il suo costo dominante e' il fsync del diario, lo
stesso del motore). Strumento e numeri nel referto par. 4; sopra l'`ArchivioLocale` VERO di G1 (1.000 ordini, diario con
fsync): `invia` di un ordine nuovo p50 1,3 ms, p95 4,5 ms; la lettura dell'archivio che la porta aggiunge p50 0,014 ms
(referto par. 11).

## 10. PSB par. 6/7

Sollecitati: par. 6.4 (parziali, FOK, esito ignoto, bet delay sull'orologio della risposta, rifiuto di Betfair, minimo .it e
punta 0,50, apertura tennis al minimo, eventi in ritardo scartati), 6.6 (concorrenza: un contatore per conto e solo live,
seq per attore, stesso ref da 8 thread = 1 ordine, seconda porta sullo stesso archivio rifiutata, callback che reinvia
senza blocco), 6.7 (falsificazione in
`falsifica_c1.py`, numeri nel referto); par. 7 n.1
(chiavi camelCase lette dalla libreria, mai scritte a mano), n.2 (rifiuto di Betfair letto: `rifiutato`), n.3 (prezzo medio dal
report, non dal chiesto), n.4 (riconciliazione col ref di piazzamento: il diario lega ref e customerOrderRef VERO), n.7
(bet_id dall'esito anche se non abbinato), n.10 (stato flumine letto dall'Enum via `fase_da_riga`/`_order_snapshot`), n.21 e
n.25 (modo della RIGA, paper e live mai sommati), n.27 (finti col vero), n.30 (mutazioni), n.33 (costanti dei minimi non duplicate: importate da
`minimi_it`), n.35 (ogni test visto rosso). Gli altri, con la causa: referto par. 7.
