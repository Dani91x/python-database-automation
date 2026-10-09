# REFERTO W1-C1 - Comparto C, porta degli ordini (ondata 1, 09/10/2026)

Ramo `architettura/w1-c1` da `559a96df`. Agente W1-C1 (Opus 5.5). Nessun file esistente modificato: solo file nuovi del
dominio (`Betfair/nucleo/ordini/{porta,adattatore_comando,minimi,controlli,eventi}.py`, `esecutori/runner.py`,
`tests/test_c1_*.py`, `doc/C1_PORTA.md`, questa cartella). Nessuna rete, nessun DB, nessun processo, nessun replay.

## 1. Cosa ho costruito (e cosa NON fa)

| File | Punti chiave | Cosa NON fa |
|---|---|---|
| `adattatore_comando.py` (348) | `comando_da_richiesta` :130, `richiesta_da_comando` :178 (chiama `valida_comando` di oggi: stessi `Rifiuto`), `riga_coda_da_richiesta` :233 / `richiesta_da_riga_coda` :274 (coda calcio), `payload_tennis_da_richiesta` :328 / `richiesta_da_payload_tennis` :339 (legge con `parse_order_payload` di oggi); tipi di estensione `RichiestaComposta` :58, `ExtraComando` :79, `DettagliCoda` :91 | non valida minimi ne' freni, non manda nulla |
| `minimi.py` (458) | una politica ESPLICITA per ogni definizione di oggi: `verdetto_runner` :138, `verdetto_porta` :173, `porta_al_minimo` :227, `diretta_ok_tennis` :238, `size_legale_tennis` :250, `spezza_esatta_tennis` :274, `spezza_uscita_scalper` :289, `taglia_scalper` :323 (calcio e tennis), `soglia_safe` :372, forma uniforme `taglia` :412; numeri SOLO da `minimi_it` (import) | non sceglie fra definizioni divergenti; niente .com; niente equivalente sull'altra selezione |
| `controlli.py` (287) | `ContatoreTransazioni` :89 (UNO per conto, regola di flumine/Betfair), `controlla` :195 (freni del motore nello stesso ordine e con gli stessi codici), `FreniConto` :58 (iniettato), `FreniDiOggi` :263 (aggancio sopra le funzioni del worker), `tetto_di_oggi` :82 | non legge env ne' DB; non verifica la riduzione (iniettata); non sostituisce il `max_txn_hour` dello scalper |
| `eventi.py` (171) | `ConsumatoreEventi` :62 (contiguita' di `seq` per attore, base al primo contatto, `da_seq` alla sorgente al primo buco, `chiudi_da_seq`), `RispostaDaSeq` :44 | non riconcilia un buco non colmabile: lo conta (come oggi) |
| `porta.py` (564) | `PortaLocale` :118: `invia` :338 (invii serializzati da `_lock_invio`) -> `_ref_e_dedup` :358 -> `_valuta` :381 (valida, freni, minimi, tetto) -> `_accetta` :414 (seq, archivio, diario write-ahead) -> `_esegui` :492 (una chiamata, eccezione = `ignoto`); `notifica` :550, `da_seq` :250, `eventi` :261, `stato` :277, `apri` :168 (dedup e stati dal diario, ordini in volo -> `ignoto`) | sincrona; niente place-and-trim, equivalente, aggancio al volo, azioni composte; `posizione` delegata a C2 |
| `esecutori/runner.py` (164) | `EsecutoreRunner` :66: wrapper sottile su `live_order_worker._dispatch` con gli shim di oggi (`_LocalSb(_SbDifferito())`, `LUCCHETTO_ORDINI`, `_CONTESTO`), riga `ordine` del diario prima di `place_order` (:105), `FASE_DA_MOTORE` :45 | `submin_disponibile = False`; non rigioca lo specchio (le scritture restano in `ultimo_differito`) |

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
6. Archivio: la porta usa `TABELLA_REF = "ordini_ref_visti"` (chiave `ref`, righe `{ref, attore, accettato, seq, motivo,
   ts_ms}`): tabella LOCALE da registrare in G1 (regime `stato_denaro`, NON verso il cloud). Il protocollo `Archivio` non ha
   una lettura per scansione: la porta fa UNA lettura puntuale per ref nuovo (locale, nessuna rete); proposta per G:
   `Archivio.elenca(tabella, filtri)` per precaricare all'avvio come fa oggi `_carica_visti`.

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
