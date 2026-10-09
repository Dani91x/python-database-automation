# REFERTO W1-C1 - Comparto C, porta degli ordini (ondata 1, 09/10/2026)

Ramo `architettura/w1-c1` da `559a96df`: consegna `0b4f2b59`, correzioni dopo la revisione indipendente nel commit
successivo (par. 10, che PREVALE sui numeri dei par. 1-9 dove diversi). Agente W1-C1 (Opus 5.5). Nessun file esistente modificato: solo file nuovi del
dominio (`Betfair/nucleo/ordini/{porta,adattatore_comando,minimi,controlli,eventi}.py`, `esecutori/runner.py`,
`tests/test_c1_*.py`, `doc/C1_PORTA.md`, questa cartella). Nessuna rete, nessun DB, nessun processo, nessun replay.

## 1. Cosa ho costruito (e cosa NON fa)

| File | Punti chiave | Cosa NON fa |
|---|---|---|
| `adattatore_comando.py` (348) | `comando_da_richiesta` :130, `richiesta_da_comando` :178 (chiama `valida_comando` di oggi: stessi `Rifiuto`), `riga_coda_da_richiesta` :233 / `richiesta_da_riga_coda` :274 (coda calcio), `payload_tennis_da_richiesta` :328 / `richiesta_da_payload_tennis` :339 (legge con `parse_order_payload` di oggi); tipi di estensione `RichiestaComposta` :58, `ExtraComando` :79, `DettagliCoda` :91 | non valida minimi ne' freni, non manda nulla |
| `minimi.py` (480) | una politica ESPLICITA per ogni definizione di oggi: `verdetto_runner` :138, `verdetto_porta` :173, `porta_al_minimo` :227, `diretta_ok_tennis` :238, `size_legale_tennis` :250, `spezza_esatta_tennis` :274, `spezza_uscita_scalper` :289, `taglia_scalper` :323 (calcio e tennis), `soglia_safe`, `verdetto_desktop` :221 (politica RIFIUTA del desktop, par. 10), forma uniforme `taglia` :434; numeri SOLO da `minimi_it` (import) | non sceglie fra definizioni divergenti; niente .com; niente equivalente sull'altra selezione |
| `controlli.py` (290) | `ContatoreTransazioni` :89 (UNO per conto, regola di flumine/Betfair), `controlla` :195 (freni del motore nello stesso ordine e con gli stessi codici), `FreniConto` :58 (iniettato), `FreniDiOggi` :263 (aggancio sopra le funzioni del worker), `tetto_di_oggi` :82 | non legge env ne' DB; non verifica la riduzione (iniettata); non sostituisce il `max_txn_hour` dello scalper |
| `eventi.py` (189) | `ConsumatoreEventi` (contiguita' di `seq` per attore, base al primo contatto, `da_seq` alla sorgente al primo buco, `chiudi_da_seq`, stato monotono, memoria limitata), `RispostaDaSeq` :44 | non riconcilia un buco non colmabile: lo conta (come oggi) |
| `porta.py` (758) | `PortaLocale` :152: `invia` :478 (serializzato; consegna ai consumatori FUORI dai lucchetti, `_consegna` :324) -> `_ref_e_dedup` :504 / `_dedup` :423 (RAM, archivio, prenotazione atomica) -> `_valuta` :527 (valida, params, freni, minimi, tetto PER MODO) -> `_accetta` :566 (seq, DIARIO poi archivio, nello stesso lucchetto) -> `_esegui` :671 (una chiamata, eccezione = `ignoto`) -> `_emetti` :705 (seq + diario durevole + stato monotono + memoria insieme); `notifica` :746, `da_seq` :355, `stato` :382, `apri` :220 / `_rileggi` :244 (dedup, stati, in volo, base dei seq) | sincrona; niente place-and-trim, equivalente, aggancio al volo, azioni composte; `posizione` delegata a C2 |
| `esecutori/runner.py` (152) | `EsecutoreRunner`: wrapper sottile su `live_order_worker._dispatch` che CHIAMA `MotoreOrdini._pre_invio`, `_imposta_contesto`, `_pulisci_contesto` (nessuna copia), shim `_LocalSb(_SbDifferito())`, `LUCCHETTO_ORDINI`; `params` del bot nella riga (`accetta_params`); `FASE_DA_MOTORE` | `submin_disponibile = False`; non rigioca lo specchio (le scritture restano in `ultimo_differito`) |

Esecutori NON costruiti (aggancio proposto, par. 8): **REST** (oggi la strada REST e' `omega/omega_market.py`, un modulo di
bot: un comparto non lo importa; serve il `ClienteRest.mutazione` di A1) e **banco** (il banco usa gia' il motore con
`PortaBanco`: `EsecutoreRunner` sul framework simulato del banco e' l'esecutore del banco, da provare nell'ombra).

## 2. Contratto

Implemento `PortaOrdini` (`PortaLocale`, verificato strutturalmente in `test_la_porta_rispetta_il_protocollo`) ed `Esecutore`
(`EsecutoreRunner`). Il contratto NON e' toccato. Estensioni PROPOSTE (in file miei, come tipi separati):

1. `RichiestaComposta` (green-up, cash-out di mercato/evento, dutch): il comando e la coda di oggi le servono; per il
   contratto stanno sopra la porta. La porta le riconosce e le rifiuta col motivo `azione_composta_sopra_la_porta`.
2. `DettagliCoda` (`liability`, `min_fill_size`, `order_type`, `azione_coda=place_submin`, `params`): colonne della coda
   senza campo nel contratto. Proposta: `RichiestaOrdine.responsabilita: Optional[float]` per la banca a liability del
   desktop (oggi solo coda) e `RichiestaOrdine.place_and_trim: bool` se la porta dovra' servire la coda.
3. `ExtraComando` (`max_eta_ms`, `params` del bot): proposta `RichiestaOrdine.max_eta_ms: Optional[int]`.
4. `PortaLocale.invia(r, extra=None)`, `notifica(ev)`, `aggiungi_consumatore`, `da_seq`, `in_volo`, `apri/chiudi`: metodi in
   piu' rispetto al `Protocol` (compatibili). Proposta: `da_seq` nel contratto (oggi `eventi` restituisce solo eventi, ma il
   `seq` e' UNO per ack ed eventi come nel motore: chi ripara un buco deve vedere anche gli ack).
5. Fase "in volo": il contratto non ha `inviato`; uso `accettato` con `bet_id=None` (motore `inviato`) e `accettato` con
   `bet_id` (motore `accettato_betfair`). `errore` del motore -> `rifiutato` se prima dell'invio, `ignoto` dopo (`post_place:`).
6. [SUPERATO dalla seconda revisione, par. 11: niente prenotazione, niente `transizione`, una porta per archivio; righe e
   colonne aggiornate nella tabella del par. 11] Archivio: la porta usa `TABELLA_REF = "ordini_ref_visti"` (chiave `ref`, righe `{ref, stato, attore, accettato, seq,
   motivo, ts_ms}`, `stato` = `ack` o `riservato:<porta>`) e `TABELLA_SEQ = "ordini_seq"` (chiave `chiave="seq"`, il blocco
   di seq prenotato `fino_a`): tabelle LOCALI da registrare in G1 (regime `stato_denaro`, NON verso il cloud). SEMANTICA
   CHIESTA A G1: `transizione(t, chiave, "", a)` = inserisci la riga `{chiave, stato: a}` SOLO SE ASSENTE, atomica, True se
   inserita (la usa il dedup fra due porte sullo stesso archivio). Il protocollo `Archivio` non ha
   una lettura per scansione: la porta fa UNA lettura puntuale per ref nuovo (locale, nessuna rete); proposta per G:
   `Archivio.elenca(tabella, filtri)` per precaricare all'avvio come fa oggi `_carica_visti`.

7. (par. 10) `Esecutore.place/cancel/replace(r, params=None)` + `accetta_params`: i params del bot verso l'esecutore;
   `RichiestaOrdine.place_and_trim: bool` (oggi la porta NON fa place-and-trim: il contratto non sa dirlo all'esecutore);
   `EventoOrdine.cor` (customerOrderRef vero, che il motore manda e `MemoriaComandi` conserva: divergenza 10b).

## 3. Parita' (funzione di oggi -> nuova -> test -> esito)

Tutti gli arbitri sono IMPORTATI dal codice di oggi e non modificati. "Identico" = stessi valori, stessi testi, stesse eccezioni.

| Oggi (file:riga) | Nuova | Test | Ingressi | Esito |
|---|---|---|---|---|
| `motore_ordini.valida_comando` :405 | `adattatore_comando.richiesta_da_comando` / `comando_da_richiesta` | `test_c1_adattatore_comando.py` | 202 richieste x 2 extra (place back/lay x LAPSE/PERSIST x FOK x riduzione x 3 handicap x paper/live x origine; 3 attori; cancel totale/parziale; replace; greenup; 2 cash-out) andata e ritorno; 26 comandi VERI da `safe_strategy/porta_ordini.costruisci_comando` :221; 14 comandi invalidi | identico (piano di `valida_comando` uguale; rifiuti con stesso codice e testo; `reduces_liability` nei params tolto come oggi) |
| `safe_strategy/execution.enqueue_place` :1767 + RPC `request_betfair_live_order` (`migrations/betfair_live_cashout_v3.sql` ~199-212) | `richiesta_da_riga_coda` / `riga_coda_da_richiesta` | `test_coda_riga_vera_di_safe_andata_e_ritorno` | 4 righe VERE (place/place_submin, paper/live, chiusura e no) | identico (riga dopo i default della RPC) |
| riga del dispatch del motore (piano di `valida_comando`) | `riga_coda_da_richiesta` | `test_riga_coda_uguale_alla_riga_del_motore` | le 202 richieste | identico chiave per chiave; UNICA differenza dichiarata: la selezione NOTA di un cancel/replace resta nella riga di coda, il motore la lascia `None` (non la legge) |
| `esecutore_tennis._payload_da_riga` :212 + `tennis_live_order_worker.parse_order_payload` :163 | `payload_tennis_da_richiesta` / `richiesta_da_payload_tennis` | `test_payload_tennis_letto_come_quello_del_motore` | le 202 richieste + greenup | identico (stessa nota sulla selezione di cancel/replace) |
| `live_order_build.min_stake_rules` :193 (.it) | `minimi.verdetto_runner` | `test_runner_parita_con_min_stake_rules` | 7 lati x 6 prezzi x 1.229 importi (0,00-12,00 al centesimo + casi limite, NaN, inf, negativi) | identico (52.000+ casi) |
| `live_order_build.verdetto_minimi` :616 (`altra_selezione=None`) | `minimi.verdetto_porta` | `test_verdetto_porta_parita_con_verdetto_minimi` | stessa griglia x submin si/no | identico |
| `trading/submin.porta_al_minimo_apertura` :312 | `minimi.porta_al_minimo` | `test_porta_al_minimo_parita_con_submin` | 7 lati x 1.227 importi | identico (eccezioni comprese) |
| `tennis_scalper/condotta_ordini.size_legale` :98, `diretta_ok` :139, `spezza_esatta` :152 | `size_legale_tennis`, `diretta_ok_tennis`, `spezza_esatta_tennis` | `test_size_legale_parita_con_condotta` (4 combinazioni live/riduce), `test_diretta_e_spezza_tennis_parita_con_condotta` | 7 lati x 1.227 importi | identico |
| `scalper/scalper_bot.spezza_uscita` :88 | `spezza_uscita_scalper` | `test_spezza_uscita_parita_con_lo_scalper` | 7 lati x 6 prezzi x 1.227 | identico |
| `ScalperStrategy._place` :2743 e `TennisScalperStrategy._place` :2418 (taglia dell'ordine VERO costruito) | `taglia_scalper(variante=calcio|tennis)` | `test_taglia_scalper_parita_col_place_vero` | 2 varianti x size_step {0, 0,5} x live_min_bet {0, 2} x exact_exits x 2 lati x ingresso/uscita x slot si/no x 454 importi (> 29.000 chiamate al `_place` vero) | identico |
| `safe_strategy/execution._min_size_live` :72 | `soglia_safe` | `test_soglia_safe_parita_con_min_size_live` | 7 valori di `SAFE_MIN_SIZE_LIVE` x 4 lati | identico |
| flumine `MaxTransactionCount` (`flumine/controls/clientcontrols.py:13`) | `ContatoreTransazioni.aggiungi/consentito` | `test_contatore_parita_col_control_di_flumine` | 4 semi x 3.000 mosse con l'ora che scorre (orologio iniettato nel modulo di flumine) | identico (conteggi, blocco, cambio d'ora) |
| flumine `BetfairExecution.execute_place/execute_cancel` (`betfairexecution.py:17, 64`) | `ContatoreTransazioni.registra` | `test_registra_parita_con_esecuzione_vera_di_flumine` | 2 semi x 200 operazioni con risposte VERE `PlaceOrders`/`CancelOrders` | identico |
| `live_order_worker._servable_modes` :235 | `controlli.servibili` | `test_servibili_parita_col_worker` | 7 valori | identico |
| `MotoreOrdini._controlla` :1061 | `controlli.controlla` | `test_controlla_parita_col_motore` | 768 casi (modo di processo x modo effettivo x modo riga x azione x riduzione x verificata x kill x guardia x settings); tutti i rami sollecitati (`None`, `mode_non_servibile`, `guardia_avvio`, `reduces_liability_non_verificabile`, `kill_switch`, `settings_stantie`) | identico (esito e testo) |
| `safe_strategy/porta_ordini.MemoriaComandi` :359 (`_avanza_seq` :379, `chiudi_da_seq` :452) | `eventi.ConsumatoreEventi` | `test_parita_con_memoria_comandi` | 12 semi x 400 messaggi con perdite (8%), duplicati (5%), scambi, risposte `da_seq` complete e non | identico (`seq_visto`, buchi, buchi non colmati, ultimo evento per ref) |
| `MotoreOrdini._esegui` :1480 -> `live_order_worker._dispatch` :4126 | `EsecutoreRunner` | `test_fase_uguale_al_motore_di_oggi` | place accettato e rifiutato dai control, su due framework gemelli | stessa fase (via `FASE_DA_MOTORE`), stesso bet_id presente/assente |
| `MotoreOrdini._carica_visti` :2494 / dedup `_gestisci` :974 | `PortaLocale.apri` + `_ref_e_dedup` + archivio | `test_dedup_*` | stessa vita, riavvio da archivio (diario nuovo), riavvio da diario (archivio nuovo) | uguale o meglio: dedup illimitato (il motore ricarica solo ieri+oggi) e fail-closed se l'archivio non risponde |
| `motore_ordini.Diario` :197 | la STESSA classe, iniettata | `test_diario_*` | | riuso, non copia |
| `order_exec.place_order` ~273-290 (desktop) | `minimi.verdetto_desktop` | `test_politica_rifiuta_del_desktop_parita_con_order_exec` | 2 lati x 803 importi, la funzione VERA fermata prima del DB | identico (stessi testi del `ValueError`) |
| `esecutore_tennis._apertura_al_minimo` :178 | `minimi.porta_al_minimo` (usata dalla porta per il tennis) | `test_apertura_tennis_al_minimo_parita_con_esecutore_tennis` | 4 lati x 1.201 importi | identico |

## 4. Migliorie misurate

Nessuna miglioria dichiarata sul percorso dell'ordine. Misura informativa (script `misura_porta.py` in questa cartella,
macchina cloud condivisa, esecutore istantaneo, archivio in memoria, 2.000 ordini): `PortaLocale.invia` p50 3,95 ms, p95
8,03, p99 11,90, max 28,0 con il diario durevole (fsync); p50 0,14 ms, p95 0,28, p99 0,49 senza fsync. Il costo e' il fsync
del write-ahead, lo stesso del motore di oggi (`Diario.scrivi`): non e' una differenza. Con l'archivio vero (SQLite di G1) si
aggiunge una scrittura per ordine: da misurare nell'ondata 2.

## 5. Test e falsificazioni

- Test nuovi: 7 file `Betfair/nucleo/ordini/tests/test_c1_*.py`, **98 verdi** (~18 s; il confronto con il `_place` vero
  degli scalper pesa ~6 s).
- Falsificazione: `falsifica_c1.py` (in questa cartella) applica 27 mutazioni al codice nuovo, rilancia i test pertinenti e
  ripristina il file confrontando lo sha256: **27/27 rosse, 27/27 ripristini con sha256 identico** (`falsifica_c1.json`;
  controllo indipendente `sha256sum -c` su tutti i moduli dopo la campagna: 0 differenze). Fra queste le quattro chieste da
  C par. 5: dedup tolto (M01, M02), `da_seq` tolto (M03) e controllo di contiguita' tolto (M04), `ok` all'esito ignoto
  (M05), ritento di una mutazione (M06).
- Al primo giro le mutazioni rosse erano 25/27, ed e' servito: **M22** era una mutazione EQUIVALENTE (un `post_place` e'
  un `RuntimeError`, e il ramo `ValueError` lo rilanciava comunque): riscritta per togliere davvero la distinzione, ora rossa;
  **M27** (lucchetto degli invii tolto) restava verde perche' il MIO archivio finto rileggeva la tabella dopo la latenza
  simulata, cioe' vedeva sempre lo scrittore concorrente: corretto il finto (fotografia della tabella, poi la latenza),
  il codice non e' cambiato; senza il lucchetto 8 thread con lo stesso ref producono 8 ordini, con il lucchetto 1.
- Suite intera `python -m pytest Betfair/ -q -p no:cacheprovider`, due volte come da brief: a meta' **11.667 passed, 0
  failed**, 87 skipped, 6 xfailed (689,9 s; 96 test C1 di allora); alla fine **11.669 passed, 0 failed**, 87 skipped, 6
  xfailed (631,9 s; i 98 test C1 compresi). Nota per il coordinatore: la cartella scratchpad e' CONDIVISA fra gli agenti
  della sessione; la mia prima uscita (`suite1.txt`) e' stata sovrascritta a meta' da quella di un altro agente (worktree
  `agent-a0aec...`, 3 rossi suoi in `nucleo/dati/tests/test_g2_registro.py` e `test_latenza_logica_comando_place_sotto_20_ms`,
  file che nel mio ramo non esiste o non fallisce): i miei numeri vengono dall'uscita del MIO processo (task in background,
  codice d'uscita 0), la seconda corsa su un file dal nome mio.

## 6. Funzionalita' di `01_FUNZIONALITA.md`

Coperte (con il test che le prova, dettaglio in `doc/C1_PORTA.md` par. 5): C-002, C-003, C-004, C-011/C-013 (forma della
riga), C-020, C-021, C-022 (solo il tetto orario, per conto), C-028 (decisione sul modo), C-030, C-031, C-032 (senza
equivalente), C-035, C-036, C-040, C-041 (place/cancel/replace), C-042 (riduzione mai creduta), C-044 (taglia non ritentata),
C-050, C-055, C-072 (taglie). Restano al codice di oggi: C-001, C-005..C-010, C-012, C-023..C-027, C-029, C-033, C-034,
C-037, C-043, C-045..C-049, C-051..C-054, C-060..C-082.

## 7. PSB par. 6 e 7

Sollecitati: 6.4 parziali (`PARZIALE` -> `parziale`, poi `notifica` -> `abbinato`), FOK (`EXPIRED` -> `scaduto`, `timeInForce`
nell'istruzione), bet delay (l'`esito_ms` e' l'istante della risposta dopo il delay, non della richiesta), rifiuto di Betfair
(`FAILURE`/`INVALID_BET_SIZE`), minimo .it e punta 0,50, esito ignoto (timeout -> `ignoto`, riconciliazione per ref); 6.6
concorrenza (tetto UNO per conto su piu' attori, seq per attore con traffico intercalato, 8 thread con lo stesso ref = 1
ordine: gli invii sono serializzati come nel thread unico del motore); 6.7 falsificazione (27 mutazioni);
6.8 riproducibile (comandi in `doc/C1_PORTA.md` par. 8). Catalogo par. 7: n.1 (le chiavi camelCase le legge la libreria), n.2
(rifiuto letto come `rifiutato`, mai copertura), n.3 (prezzo medio da `averagePriceMatched`), n.4 (diario: ref -> customerOrderRef
VERO), n.7 (bet_id anche non abbinato), n.10 (stato flumine dall'Enum via `fase_da_riga`), n.21 e n.25 (modo della RIGA,
contatore per conto), n.27 (finti con la libreria vera), n.30 e n.35 (mutazioni rosse), n.33 (numeri dei minimi importati).
⊘ con causa: n.5, n.6 (riconciliazione per ref e mercato: comparto C2), n.8, n.11-n.15, n.17, n.32 (banco e simulazione: nessun
replay in questa ondata), n.9 e n.16 (ladder e controlli di certificazione: altri comparti), n.18-n.20, n.22-n.24, n.26 (DB,
servizi e RPC: nessuna tabella toccata), n.28-n.29 (ogni test ha un arbitro di oggi o una mutazione rossa), n.31 (nessuna copia
di laboratorio), n.34, n.36 (famiglia K a livello di replay: ondata 2), n.37 (nessuna pool di processi).

## 8. Aggancio proposto per l'ondata 2 (NON fatto)

1. `Betfair/stream/motore_ordini.py`: SPOSTATO (non riscritto) dietro la porta. `MotoreOrdini._gestisci` :974-1046 diventa
   `PortaLocale.invia` con `EsecutoreRunner(flumine, strategie, low=self._low)` e il diario del motore; `_rispondi_da_seq`
   :2280 -> `PortaLocale.da_seq`; `_carica_visti` :2494 -> `apri`; `_controlla` :1061 -> `controlli.controlla` con
   `FreniDiOggi` (oppure con gli agganci `blocco_modo`/`eta_settings` del banco). Restano al motore (nell'esecutore o sopra la
   porta): aggancio al volo, place-and-trim, equivalente, sorveglianza `INVALID_BET_SIZE`, riprezzi.
2. `safe_strategy/porta_ordini.py`, `omega/porta_ordini.py`, `mike/porta_ordini.py`: ereditano da una porta generica
   (`PortaCanale(attore)`) che usa `adattatore_comando.comando_da_richiesta` e `eventi.ConsumatoreEventi` al posto di
   `MemoriaComandi` (parita' gia' provata); aggiungere, non togliere (i test di Safe sostituiscono variabili di modulo).
3. Interruttore `ARCH_ORDINI_PORTA=vecchio|nuovo` PER ATTORE, letto dove oggi si sceglie la strada (`execution.place`
   ~1219-1400, `omega_service.py` ~5690-5830, `mike/service.py` ~2195-2379); di serie `vecchio`.
4. Contatore per conto: `ContatoreTransazioni(tetto_di_oggi(), ...)` UNO nel processo del runner, `registra` chiamato dove
   flumine chiama `add_transaction` (oppure come `trading_control` di flumine che legge lo stesso contatore); esposto nella
   «Salute» (`stato()`), oggi non in UI (02 P-13).
5. Ombra: la stessa `RichiestaOrdine` produce la stessa sequenza di `EventoOrdine` su `EsecutoreRunner` (paper) e sul banco
   (`PortaBanco` + `EsecutoreRunner` sul framework simulato). Criterio di "uguale o meglio": sequenze di fasi identiche per
   ref, stessi bet_id simulati, stessi rifiuti con lo stesso codice; banco `safe_base 35760084 rapidi entrambi` e
   `omega 35760084` identici al referto del 04/10.
6. G1: registrare `ordini_ref_visti` come tabella LOCALE (mai nel postino). A1: `ClienteRest.mutazione` per l'esecutore REST.

## 9. Divergenze per l'utente, rischi, dubbi

**Divergenze fra le definizioni di oggi delle taglie** (fotografate in `test_divergenze_di_oggi_fotografate`; NON scelte):

1. **Minimo d'ingresso dello scalper TENNIS = 2,00 EUR** (`tennis_scalper_bot.py:86` `MIN_STAKE = 2.0`), scalper calcio 1,00
   (`scalper_bot.py:80`, da `minimi_it`), runner/motore/Safe/Omega/Mike 1,00 (`minimi_it.IT_MIN_BACK`). E' la divergenza "2,00
   contro 1,00" gia' nota: oggi vive nello scalper TENNIS, non in quello calcio.
2. **`live_min_bet = 2.0` dello scalper e' solo un interruttore**: i commenti dicono "minimo Betfair 2,0 su .it"
   (`scalper_bot.py:589`, `scalper_session.py:57`, `tennis_runner.py:999`), ma il minimo usato e' `_side_min` = 1,00 dei
   `minimi_it` (`scalper_bot.py:2950`, `tennis_scalper_bot.py:2583`). Documentazione che mente (PSB n.33).
3. **Passo 0,50 dello scalper al PIU' VICINO** (`round(size/0,5)*0,5`, anche verso l'ALTO: 7,27 -> 7,50; con
   l'arrotondamento bancario di Python 1,25 -> 1,00, 1,75 -> 2,00), il runner per DIFETTO col residuo dichiarato (7,27 ->
   7,00 + 0,27). Nello scalper calcio vale per ingressi e uscite non esatte, nel tennis per le punte e per gli ingressi.
4. **Divisione di un'uscita di punta**: tennis `spezza_esatta` 2,80 -> 2,50 diretta + 0,30 al place-and-trim (un resto SOTTO
   il floor di 0,50, che `verifica_importo_finale` poi rifiuta), scalper calcio `spezza_uscita` 2,80 -> 2,00 + 0,80; 1,20 ->
   tennis 1,00 + 0,20, scalper 1,00 + 0,20 di residuo dichiarato. Lo scalper tennis ha una TERZA divisione in `_place_exact`
   (`tennis_scalper_bot.py` ~2670-2674: parte diretta al multiplo di 0,50 anche per la BANCA, che il .it accetta al centesimo).
5. **Uscita sotto il minimo**: lo scalper (con `live_min_bet` > 0 e senza la via esatta) la GONFIA al gradino di 0,50 (0,60 ->
   1,00, over-hedge) da 0,25 in su; la copertura dei bot tennis (`size_legale`, regola dell'utente 28/09) non la gonfia mai.
6. Docstring che mentono sui numeri: `condotta_ordini.diretta_ok` ("BACK >= 2,00 / LAY >= 0,50", il codice usa 1,00/1,00),
   `submin.porta_al_minimo_apertura` (cita BACK 200 centesimi), `runner.py:2238` ("back EUR2 / lay EUR0,50").

**Divergenze sul conteggio delle transazioni**: oggi il tetto (`LIVE_TRANSACTION_LIMIT` 1000) e' PER CLIENT flumine, cioe' per
processo (runner calcio, runner tennis, ogni sessione scalper hanno il loro); lo scalper ha in piu' `max_txn_hour` 300 per
sessione che ferma solo gli INGRESSI (`scalper_bot.py` ~2846), mentre il control di flumine ferma TUTTO (anche le chiusure)
oltre il tetto. Il contatore nuovo e' uno per conto con la regola di flumine: con il tetto di oggi, sommare runner + scalper
potrebbe fermare prima. Decisione per l'utente prima dell'aggancio (valore del tetto per conto, chiusure sempre ammesse o no).
Inoltre flumine NON conta un place senza risposta (eccezione/timeout) che Betfair potrebbe aver ricevuto: sottostima nota.

**Rischi e dubbi**:
- La porta e' SINCRONA e SERIALIZZATA: l'esecutore gira nel thread di `invia`, un invio alla volta (`_lock_invio`, come il
  thread unico del motore e `LUCCHETTO_ORDINI`); un esecutore lento (REST) ferma gli invii degli altri attori per la sua
  durata, come oggi nel motore. Nel motore l'ack parte PRIMA dell'esecuzione: nell'ondata 2 l'ack va pubblicato prima
  (l'ordine dei seq e' gia' giusto: ack n, eventi n+1...).
- `apri()` rilegge ieri+oggi dalla data dell'orologio iniettato, mentre `Diario` scrive col suo `giorno` (data di sistema):
  coincidono in produzione; nei test si inietta lo stesso giorno.
- `EsecutoreRunner`: un'eccezione NON `ValueError` (anche se nata prima dell'invio) diventa esito IGNOTO per la porta: direzione
  sicura (si riconcilia), ma piu' rumorosa del motore, che la riporta come `errore`.
- Dedup illimitato (archivio senza scadenza) invece di "ieri+oggi" del motore: piu' severo; un ref riusato dopo giorni sarebbe
  rifiutato come doppione (i ref dei bot sono id di riga: non si riusano).
- La porta rifiuta (fail-closed) se l'archivio non risponde (`archivio_non_disponibile`); il motore all'avvio con diario
  illeggibile tiene il dedup solo in RAM e piazza. Piu' sicuro, ma e' un comportamento nuovo: va detto all'utente.
- Il 2,00 dello scalper tennis e le altre divergenze non cambiano finche' la porta non e' agganciata: nessun bot usa ancora
  `minimi.py`.
- Il contatore orario (come il control di flumine) si azzera al PRIMO controllo dell'ora (`_check_hour` con `_next_hour`
  vuoto): le transazioni registrate prima del primo controllo si perdono. Identico a flumine; scoperto scrivendo il test
  del paper (par. 10, M29 al primo giro verde).

**Divergenze aggiunte dopo la revisione (per l'utente, NON risolte di iniziativa)**:

9. **Tennis nella porta**: la consegna ignorava `r.sport`. Ora la porta fa per il tennis cio' che fa il motore con
   `esecutore_tennis`: un'APERTURA sotto il minimo si porta AL minimo (`_apertura_al_minimo`, 28/09; parita' provata con
   `minimi.porta_al_minimo` su 4 lati x 1.201 importi) e l'evento porta `portata_al_minimo`; una chiusura non si gonfia mai;
   nessun place-and-trim. NON coperto: `TENNIS_LIVE_JURISDICTION` diversa da `it` (la porta usa sempre .it), e il resto del
   runner tennis (azioni ammesse, `CanaleSoloComandi`) che resta all'esecutore. Scelta: implementare (opzione del
   coordinatore) invece di rifiutare `sport="tennis"`.
10a. **Punta non multipla di 0,50**: il terminale del desktop (`order_exec.py:285-297`) la RIFIUTA indicando i due importi
   validi; il motore, il REST di Omega e la porta la TRONCANO (7,27 -> 7,00 + residuo dichiarato). `minimi.verdetto_desktop`
   e' la politica RIFIUTA (parita' con `order_exec` provata); la porta usa la politica del motore. Quale vale per l'app
   (desktop sulla porta) lo decide l'utente.
10b. **`cor` (customerOrderRef vero) negli eventi**: il motore lo manda nel primo evento e `MemoriaComandi` lo conserva per chi
   legge l'esito tardi; `EventoOrdine` non ha il campo. Oggi la porta lo scrive SOLO nel diario (riga `ordine` dell'esecutore).
   Proposta: `EventoOrdine.cor: Optional[str]` (estensione additiva del contratto, decide il coordinatore).
11. **Tetto per modo**: oggi flumine conta per CLIENT, quindi il client simulato ha il SUO tetto (stesso valore,
   `runner.py:2281-2319`). La porta: contatore del live per conto + contatore del paper FACOLTATIVO (`contatore_paper`); mai
   sommati. Come oggi, oltre il tetto il live ferma anche cancel e replace (control di flumine su ogni operazione): ora il
   paper non puo' piu' consumarlo.
12. **Consumatore piu' severo di `MemoriaComandi`**: un terminale non si sovrascrive con un altro terminale e l'abbinato non
   cala (oggi Safe li accetta se il seq e' piu' alto). Fotografato in `test_stato_non_regredisce_piu_severo_di_oggi`.

## 10. Correzioni dopo la revisione indipendente (09/10 sera)

Revisione del coordinatore su `0b4f2b59`: DA CORREGGERE. Le prove del revisore (R01-R17, `rev_w1c1/test_rev_avversario.py`)
sono incorporate con nomi miei in `tests/test_c1_revisione.py` (25 test) e, per l'esecutore, in `test_c1_esecutore_runner.py`.
Prova "rosso prima": `rossi_prima_della_correzione.py` rimette i 5 moduli di `0b4f2b59`, lancia i test nuovi e ripristina
(sha256 ok): **29 rossi** (`rossi_prima_della_correzione.txt`). I test nuovi verdi anche sul vecchio codice (V11, V23, V43,
V52-V54, V59, V60, R17, parita' tennis) provavano un comportamento gia' giusto e non sorvegliato: ognuno uccide la sua mutazione.

| # | Difetto (revisione) | Correzione (file) | Test (rosso prima) | Mutazione |
|---|---|---|---|---|
| 1 | il PAPER consumava il tetto del LIVE e lo bloccava (anche i cancel) | un contatore PER MODO (`_contatori`, porta `_valuta`/`_esegui`) | `test_paper_non_consuma_il_tetto_del_live`, `test_il_paper_non_impedisce_al_live_di_chiudere`, `test_il_tetto_del_live_non_ferma_il_paper`, `test_contatore_proprio_del_paper` | M28, M29 |
| 2 | `params` del bot persi verso l'esecutore (cap `max_stake` sparito in silenzio) ma scritti nel diario | `Esecutore.place/cancel/replace(r, params=)` + `accetta_params`; `EsecutoreRunner` li mette nella riga; un esecutore che non li serve -> rifiuto `params_non_serviti`, nessun `inviato` | `test_params_arrivano_al_dispatch_vero` (catena VERA, il cap ferma l'ordine), `test_params_rifiutati_se_l_esecutore_non_li_serve`, `test_params_nella_riga_del_dispatch` | M30, M31 |
| 3 | DEADLOCK: callback chiamata col lucchetto tenuto | coda di consegna fuori dai lucchetti (`_consegna`, rientrante per lo stesso thread) | `test_consumatore_che_invia_dentro_la_callback_non_blocca` | M32 |
| 4 | ack fantasma (archivio scritto prima del diario) | DIARIO prima dell'archivio; archivio KO dopo `inviato` -> riga `rifiuto` che lo chiude; prenotazione orfana di QUESTA porta (stesso diario) ripresa | `test_crash_fra_diario_e_archivio_nessun_ack_fantasma`, `test_archivio_ko_dopo_inviato_chiude_il_ref_nel_diario` | M33, M34 |
| 5 | un `ignoto` chiudeva il ref al riavvio | `_rileggi`: un ref con ultima fase `ignoto` resta in volo; un evento vero lo toglie | `test_ignoto_resta_da_riconciliare_dopo_il_riavvio` | M35 |
| 6 | stato che regrediva (abbinato che cala, terminale sovrascritto) | `_stantio` in `_emetti` e `_rileggi`; stessa regola nel consumatore | `test_un_terminale_tardivo_non_cancella_un_abbinato`, `test_un_terminale_non_si_sovrascrive_con_un_altro_terminale`, `test_un_evento_vecchio_non_fa_regredire_l_abbinato`, `test_stato_non_regredisce_piu_severo_di_oggi` | M25, M36, M45 |
| 7 | seq assegnato e memorizzato in due momenti | `_nuovo_seq` + diario + stato + `_memorizza` nella STESSA sezione di `_lock` | `test_memoria_in_ordine_di_seq_sotto_stress`, `test_da_seq_non_dichiara_visto_un_seq_non_ancora_in_memoria` | M37 |
| 8 | dedup non atomico fra due porte sullo stesso archivio | [SUPERATO, par. 11: la prenotazione non funzionava con l'archivio vero; ora UNA porta per archivio] prenotazione `transizione(.., "", "riservato:<porta>")` (semantica chiesta a G1, par. 2.6); l'altra porta aspetta l'ack (0,5 s) o risponde `ref_gia_visto` senza seq | `test_due_porte_sullo_stesso_archivio_un_solo_ordine` | M38 |
| 9 | tennis ignorato | apertura al minimo come il motore tennis (divergenza 9) | `test_tennis_apertura_sotto_minimo_portata_al_minimo`, parita' in `test_c1_minimi.py` | M39 |
| 10a | desktop rifiuta, porta tronca | politica `verdetto_desktop` in `minimi.py` (divergenza 10a) | `test_politica_rifiuta_del_desktop_parita_con_order_exec` | M46 |
| R07 | eccezione del contatore dopo il place | `_conta` protetto: l'esito si scrive comunque | `test_contatore_che_solleva_dopo_l_invio_lascia_l_esito` | M43 |
| R08 | lato maiuscolo e taglia rifiutata | chiave col lato minuscolo | `test_taglia_rifiutata_anche_con_lato_maiuscolo` | M42 |
| R09 | `riduce_esposizione` letto anche su replace/cancel | riduzione solo sul place (come `valida_comando`) | `test_replace_con_riduce_non_scavalca_il_kill_switch` | M40 |
| R15 | ramo place-and-trim senza canale verso l'esecutore | TOLTO: la porta non fa place-and-trim (estensione proposta) | `test_place_and_trim_mai_dalla_porta` | - |
| R16 | seq indietro dopo un riavvio con l'orologio indietro | blocchi di seq prenotati in `TABELLA_SEQ` e seq del diario letti in `apri` | `test_seq_dopo_il_riavvio_con_orologio_indietro` | M41 |
| bassi | memoria senza limite; esito/evento non durevoli; esecutore non sottile | potatura a 5.000 ref (archivio resta la fonte del dedup); esito/evento durevoli; `EsecutoreRunner` chiama `_pre_invio`/`_imposta_contesto`/`_pulisci_contesto` del motore, ramo `startswith` morto tolto, dispatch senza esito -> ignoto | `test_memoria_della_porta_limitata`, `test_memoria_del_consumatore_limitata`, `test_write_ahead_e_durevole`, `test_dispatch_senza_esito_e_ignoto` | M44, M47 |
| V* | mutazioni sopravvissute (V08, V11, V23, V43, V52-V54, V59, V60) | test sui VALORI di `StatoOrdine`, ordini flumine abbinati/parziali con `CurrentOrder` VERO, ramo ok False, rifiuto locale e ignoto non contati, ref sconosciuto | `test_stato_porta_i_valori_veri`, `test_ordine_abbinato_e_parziale`, `test_esito_ok_false_e_rifiutato`, `test_ignoto_e_rifiuto_locale_non_contano_come_transazioni`, `test_notifica_di_un_ref_sconosciuto_ignorata`, `test_write_ahead_e_durevole` | V08=M47, V11, V23, V43, V52-V60 |

Prove del revisore rilanciate COSI' COM'ERANO sul codice corretto: 15/18 verdi; restano rosse per costruzione R14 (aggancia
`_pubblica`, che non esiste piu': lo scenario e' rifatto in `test_da_seq_non_dichiara_visto...` bloccando DENTRO la sezione
che assegna il seq), R15 (finisce con `pytest.fail` per progetto: sostituita da `test_place_and_trim_mai_dalla_porta`) e R16
(riparte con archivio E diario NUOVI: nessuna memoria da cui ripartire; la mia versione riparte con lo stesso archivio, come
in un riavvio vero).

Restano, dichiarati: l'`EsecutoreRunner` rifa' la riga da `valida_comando` (deterministica) e non rigioca lo specchio; le
righe `ripresa` del vecchio motore sono ignote ad `apri` (diario della porta separato: un ref li' resta in volo, direzione
sicura); [superato, par. 11] una prenotazione `riservato:<altra porta>` di una porta morta resta finche' qualcuno non la chiude (la porta risponde
`ref_gia_visto` senza seq: mai un secondo ordine, riconciliazione per ref).

Numeri dopo le correzioni: **135 test C1 verdi**; falsificazione **58/58 rosse, 58/58 ripristini sha256**
(M01-M27 riancorate al codice nuovo, M28-M47 nuove, 11 mutazioni del revisore); suite intera (una corsa) **11.705 passed, 1 failed**, 87 skipped, 6 xfailed (546 s): il rosso e' `test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms` (23,8 ms contro 20 su macchina condivisa con altri 6 agenti; codice NON toccato, `git diff 0b4f2b59 -- Betfair/stream/` vuoto; rilanciato da solo 3/3 verde; lo stesso rosso compare nella suite di un altro agente). Al primo giro
della nuova campagna 54/58: M25 e M45 (terminale dopo terminale con lo STESSO abbinato non provato), M28 e M29 (il test del
paper registrava prima del primo controllo dell'ora, che azzera il contatore come in flumine): test aggiunti/corretti, poi
rosse.

## 11. Seconda revisione (su `41ea9dcb`): correzioni

Esito della revisione: DA CORREGGERE, con un difetto BLOCCANTE (B). Decisioni del coordinatore applicate senza chiedere altro
a G1. Prove del revisore in `scratchpad/rev_w1c1_2/` (rilanciate sul codice corretto, risultati sotto). Ogni test nuovo
e' in `tests/test_c1_revisione.py` (sezione "seconda revisione"), salvo dove indicato.

| Punto | Difetto | Correzione (file:riga) | Test | Mutazione |
|---|---|---|---|---|
| **B** (bloccante) | prenotazione con `transizione(t, chiave, "", "riservato:<porta>")` usata come "inserisci se assente": il contratto non la prevede; con l'`ArchivioLocale` VERO di G1 (riga assente -> `False`, colonna `status`) OGNI ordine nuovo usciva `accettato=True, seq=None, "in carico a un'altra porta"` con 0 chiamate a Betfair (ack falso, ordine perso). I miei test passavano perche' il finto faceva cio' che il vero non fa | tolti prenotazione, `_attesa_altrove`, `_padrone`; dedup = memoria + diario + righe `ordini_ref_visti` scritte (`scrivi`) e rilette (`leggi`) dalla porta stessa sotto `_lock_invio` (`porta.py` `_dedup` :459); UNA porta per archivio: registro di processo delle cartelle (`_ARCHIVI_IN_USO`, `_chiave_archivio` :146, controllo nel costruttore :218-222, rilascio in `chiudi` :312-320), seconda porta -> `ArchivioGiaInUso` | `test_ogni_ordine_nuovo_parte_con_la_semantica_vera` (20 ordini nuovi = 20 invii), `test_seconda_porta_sullo_stesso_archivio_rifiutata`, `test_contratto_del_finto_transizione_come_il_vero` | M02, M38, M51, M52 |
| **B** (finto) | `_ArchivioMemoria` diverso dal vero | riscritto con la semantica di `ArchivioLocale` (W1-G1 `archivio.py:372-435`): `scrivi` = upsert che fonde le colonne, `leggi` = ultima versione o None, `transizione` SOLO su riga esistente con `colonna_stato` (di serie `status`, configurabile) che vale `da`, `cartella` per istanza (`test_c1_porta.py` :52, `transizione` :101) | `test_contratto_del_finto_transizione_come_il_vero` (riga assente -> False, colonna configurabile, fusione) | - |
| **ACK FALSO** | un ordine dall'esito non certo rispondeva `accettato=True` | `_dedup`: ref ACCETTATO da questa porta -> lo stesso ack (`ref_gia_visto`, idempotenza); ref in volo dopo il riavvio o con esito `ignoto` -> `accettato=False, seq=None, "ref_gia_in_volo: ... riconciliare per ref"` (`M_IN_VOLO`), 0 invii | `test_mai_un_ack_falso` (in volo, ignoto, idempotenza; 0 chiamate), `test_esito_ignoto_mai_ok_mai_ritentato`, `test_riavvio_con_ordine_in_volo` (aggiornati) | M33 |
| **A6** | `_emetti(tipo="esito")` saltava `_stantio`: lo stream degli ordini arrivato PRIMA della risposta REST veniva sovrascritto (abbinato 4,0 -> parziale 1,0) | `_stantio` anche sugli esiti (`porta.py` `_emetti` :735-739) | `test_esito_del_place_non_sovrascrive_il_flusso_arrivato_prima` (sequenza P2 del revisore) | M48, S10 |
| **MEMORIA** | `_pota` espelleva anche ref NON terminali (un PERSIST aperto perdeva stato e aggiornamenti) | `_pota_ref` (`porta.py:417`, `_espellibile` :410) espelle solo ref con ordine chiuso (o senza stato e non in volo); tetto pieno di aperti -> si cresce e WARNING; stessa regola nel consumatore (`eventi._pota_eventi`) | `test_un_ordine_aperto_non_si_dimentica` (P1 del revisore, tetto 20), `test_tetto_pieno_di_ordini_aperti_cresce`, `test_memoria_della_porta_limitata`, `test_memoria_del_consumatore_limitata` | M44, M49, M50 |
| **R9** | mutazione sopravvissuta: `_stantio` tolto da `_rileggi` | test del riavvio con una riga stantia nel diario | `test_riavvio_con_righe_stantie_nel_diario` | S9 |
| **R6** | mutazione EQUIVALENTE (la riga `inviati.pop` nel ramo `rifiuto` era ridondante: lo stato `rifiutato` gia' toglie il ref dagli in volo) | riga tolta; riformulata come S6 (il rifiuto non registra lo stato `rifiutato`) | `test_archivio_ko_dopo_inviato_chiude_il_ref_nel_diario` | S6 |
| **LATENZA** | lettura sincrona dell'archivio dentro `_lock_invio` per ogni ordine nuovo | misurata (sotto) | - | - |

**Latenza** (`latenza_archivio_vero.py` in questa cartella: `PortaLocale` sopra l'`ArchivioLocale` VERO di W1-G1 su SQLite
in file, diario VERO con fsync, esecutore istantaneo, 1.000 ordini; macchina cloud condivisa):
`invia` di ordini NUOVI p50 1,297 ms, p95 4,489, p99 8,104 (max 25,3); doppioni (dalla memoria) p50 0,012 (p95 0,019) ms;
la sola `Archivio.leggi` di un ref assente (cio' che la porta aggiunge al motore per ordine) p50 0,014 ms, p95
0,027 (p99 0,074). Il costo dominante resta il fsync del diario write-ahead, lo stesso del motore di oggi: la lettura
dell'archivio aggiunge centesimi di millisecondo, ben sotto i "qualche ms" ammessi rispetto al test di latenza logica del
motore (20 ms). Seconda corsa dello stesso strumento (copia committata, a campagna appena finita, macchina carica): nuovi
p50 3,814 ms, p95 8,803, p99 11,999; doppioni p50 0,007; `leggi` p50 0,016, p95 0,031: la variabilita' e' tutta del
fsync, la lettura dell'archivio resta sotto 0,1 ms al p99. **Numero dichiarato**: la porta aggiunge al motore < 0,1 ms per
ordine nuovo (p99 della `leggi`); l'`invia` intero sta sotto 9 ms al p95 anche sotto carico.

**Prove del revisore rilanciate sul codice corretto**: `b_archivio_vero.py` -> `Ack(accettato=True, seq=..., motivo=None)`,
1 chiamata a Betfair, `transizione` su riga assente -> False; `p_memoria_race.py` -> P1: `safe-0` resta `parziale` dopo 25
ordini e la sua notifica `abbinato` passa; P2: stato finale `abbinato 4,0`, un solo evento; `p_malformata.py` -> lato,
prezzo, importo e selezione malformati rifiutati `parametri_invalidi`, nessuna eccezione.

**All'integrazione** il coordinatore rilancia i test della porta (`test_c1_porta.py`, `test_c1_revisione.py`) contro
l'`ArchivioLocale` VERO di G1 al posto del finto (il ramo di G1 non e' nel mio). Tabelle LOCALI da registrare in G1
(regime `stato_denaro`, MAI verso il cloud):

| Tabella | Chiave naturale | Colonne | Scrive / legge |
|---|---|---|---|
| `ordini_ref_visti` | `ref` | `ref`, `attore`, `accettato`, `seq`, `motivo`, `ts_ms` | `PortaLocale._registra_ack` / `_rifiuto_dopo_seq` (`scrivi`), `_dedup` (`leggi`) |
| `ordini_seq` | `chiave` (sempre `"seq"`) | `chiave`, `fino_a` (blocco di seq prenotato) | `_nuovo_seq` (`scrivi`, ogni 1.000 seq), `apri` (`leggi`) |

Nessuna `transizione` e' usata dalla porta.

**sha256 dei file corretti** (quelli che ogni mutazione ripristina, verificati dopo la campagna con `sha256sum -c`, 8/8 OK):
`porta.py` `c2a615ba3d864cf7ef14273fa6a16507abd129a4328bb06d1860e40e671b0aec`, `eventi.py`
`ebe614d1ce369d1536f9999df3274dcd1310a69f4f7504430fe11a6289e083ce`; test: `test_c1_porta.py`
`266a5835dcd1ffed78418e5e22017f89f7922e49929df0084543112e915377ad`, `test_c1_revisione.py`
`567b6eecd61df942e33d4ba5f554d23b9a56ff0ba0553e300c536c0d4a105c48`. Ogni riga di `falsifica_c1.json` porta lo sha256
del file ripristinato e il test che l'ha presa.

Nota su M52: nella campagna (pytest `-x` sull'intera cartella) la prima a cadere e' `test_ref_non_valido_non_registrato`,
per un FALSO POSITIVO della chiave per identita': senza `cartella`, una porta non chiusa e raccolta dal GC lascia la voce e
un archivio nuovo allo stesso indirizzo viene rifiutato. Il test mirato `test_seconda_porta_sullo_stesso_archivio_rifiutata`
e' rosso anch'esso (provato a parte: `DID NOT RAISE ArchivioGiaInUso` sul gemello con la stessa cartella, ripristino
sha256 ok). Residuo dichiarato: un archivio SENZA `cartella` (solo i finti; l'`ArchivioLocale` vero ce l'ha) usa la
chiave per identita' e un `chiudi` dimenticato puo' dare quel falso positivo, in direzione sicura (rifiuta la porta, mai
due ordini).

**Numeri**: test C1 **142 verdi**; falsificazione **79/79 rosse, ripristini sha256 79/79**
(`falsifica_c1.json`, committato: M01-M52, le 11 V della prima revisione, le 16 S della seconda); suite intera (una corsa)
**11.713 passed, 0 failed**, 87 skipped, 6 xfailed (409 s): questa volta anche il test di latenza del motore
di oggi (`test_latenza_logica_comando_place_sotto_20_ms`, rosso sotto carico al giro precedente) e' passato.

**Divergenze per l'utente aggiornate**: (13) dopo un riavvio un ref ancora in volo risponde `accettato=False`
`ref_gia_in_volo` (il motore di oggi rispondeva l'ack del diario, `accettato=True`): un bot che lo leggesse come rifiuto e
rimandasse con un ref NUOVO creerebbe un secondo ordine; il motivo e' esplicito e il ref va riconciliato (C2). (14) Una porta
per archivio: due runner (calcio e tennis) devono avere archivi (cartelle) diversi o condividere UNA porta. (15) La memoria
cresce oltre 5.000 ref se gli ordini APERTI sono tanti (si dice a WARNING): nessun ordine aperto si dimentica.
