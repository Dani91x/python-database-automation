# CANTIERE C - OMEGA: IL PAPER SPECCHIO DEL LIVE (28/09/2026) - SECONDA CONSEGNA

Delegato: cantiere C. Worktree `agent-a946824ef51067fea` (base `2eb3c1d`). Lavoro NON committato.
Nessuna scrittura sul DB, nessuna chiamata a Betfair, nessun processo avviato, nessun replay `certifica`.
Perimetro: `Betfair/omega/` e i suoi test; allargato dal coordinatore a
`Betfair/stream/backtest/trasporto_rapido.py` per il SOLO scenario R3 di Omega paper; una migrazione in `migrations/`.

Ordine dell'utente (28/09): «deve essere lo specchio per tutti i bot»; ogni differenza paper/live e' un bug.

Questa seconda consegna risponde ai sei punti della verifica del coordinatore (§0-bis) oltre ai difetti della prima.

---

## 0. In breve

| # | Difetto | Esito |
|---|---|---|
| 1 | R8: paper senza FOK (canale e coda), live FOK | **CORRETTO** |
| 2 | ripiego paper che accettava il parziale | **CORRETTO**, e il ripiego stesso non esiste piu' (vedi 8) |
| 3 | riserva con risposta persa = fill inventato (`reconcile_pending`) | **CORRETTO** |
| 4 | `run_once` salta il giro se `read_control` fallisce | **CORRETTO**, con eta' massima del controllo (punto 6 del coordinatore) |
| 5 | chiusura automatica delle proposte fuori dalla porta degli ordini | **CORRETTO** |
| 6 | missione chiusa con un ordine paper in volo | **CORRETTO** |
| 7 | richiesta paper in coda mai presa in carico, non revocata | **CORRETTO** |
| 8 | **D1** ripiego paper «di casa» (fill istantaneo, senza bet delay) | **CORRETTO**: il paper passa SOLO dal runner, altrimenti apertura NON eseguita col motivo |
| 9 | **D3** mercato sparito da 48 h: paper chiuso a 0 | **CORRETTO**: regolato col risultato vero, altrimenti aperto con l'allarme come il live |
| 10 | **D4** aggregati del servizio che sommano paper e live | **CORRETTO** + migrazione (non applicata); funziona anche prima |
| 11 | banco R3 che pretendeva il difetto R8 | **CORRETTO** (perimetro allargato) |

Numeri: suite di Omega **1359 -> 1404 passati, 0 rossi** (interruttori dei canali a 0); col `.env` vero
**nessun rosso nuovo** (§3.2); 15 file esterni collegati + `Betfair/mike/tests`: **1472 passati, 0 rossi**;
falsificazione **22 mutazioni** (§3.4).

### 0-bis. I sei punti del coordinatore
1. **Mutazione sopravvissuta `return [dict(o)]`**: test nuovo
   `test_ordine_registrato_di_un_altra_riga_non_conferma` (id uguale, mercato O selezione diversi -> la riga resta in
   attesa per la grazia e poi si libera, mai 'open'); la tua mutazione e' M16 nel falsificatore: ROSSA.
2. **D1**: fatto (§2.8). Le CHIUSURE: reperto per il cantiere D1 in §6.
3. **D3**: fatto (§2.9).
4. **D4**: fatto (§2.10) + `migrations/omega_aggregati_servizio_per_modalita_2026-09-28.sql`.
5. **Banco**: `trasporto_rapido.py` R3 per Omega paper = live; `test_profilo_rapido_verde_sulla_registrazione_vera[omega]` VERDE.
6. **Giro degradato**: eta' massima `_ULTIMO_CONTROLLO_MAX_ETA_S = 300 s` (§2.4); freno e stato fermo confermati (§2.4).

---

### 0-ter. Riallineamento a master (richiesta del coordinatore)
- Commit LOCALE `14d5bd5` sul ramo del worktree con i soli 28 file del cantiere (elenco in
  `cantiere_c/file_del_cantiere.txt`, `git add -- <file>` uno per uno), `git fetch`, `git merge origin/master`
  (`512db64`): merge pulito, nessun push.
- Dopo il merge: `Betfair/omega` + banco `test_strada_unica_banco` + `safe_strategy/tests/test_execution.py` +
  `tests/test_consapevolezza_ordine_2026_09_16.py` = **1534 passati, 0 rossi**.
- `AUDIT_2026-09-28/CANTIERE_C_su_master.patch` = `git diff origin/master` dei soli file del cantiere (28 file);
  verificato con `git apply --cached --check` su un indice temporaneo di `origin/master`: si applica pulita.
- `trasporto_rapido.py`: modificato SOLO il docstring della riga R3 e il ramo Omega paper di `_r3` (17+/22-).
- Uscite manuali/automatiche (cantiere N): non toccato cio' che decide se un'uscita di Omega parte da sola o
  diventa proposta; la sola modifica alle proposte e' il TRASPORTO dell'uscita automatica (porta degli ordini).

## 1. Cause radice (con prova)

1.1 **R8.** Canale: `_place_via_canale` passava `time_in_force=(FOK if mode=="live" else None)`; coda:
`_flumine_enqueue_place` metteva il FOK solo in live. flumine simula il FOK come Betfair
(`flumine/simulation/simulatedorder.py:117-200`, `minFillSize` = size: tutto o niente). Test del 24/09 che asserivano
il difetto: `test_porta_ordini_omega_f6_2026_09_24.py:356,419`, `test_omega_flumine_live.py:168`.

1.2 **Ripiego che accetta il parziale** (`_place_one`, `_manual_place`): referto `ADMIN26_ORDINI_SCHEDE.md` 7.9.5.E3.

1.3 **Fill inventato**: `reconcile_pending` confermava ogni 'pending' paper senza marcatori coi dati della riserva
(FIX-C §7.2). Il live passa da `reconcile_decision` contro Betfair.

1.4 **`read_control` KO**: lettura senza protezione in `run_once`; l'eccezione saltava l'intero giro (FIX-C §7.6).

1.5 **Proposte fuori porta**: `omega_proposte.py` chiamava `close_trade` senza `_porta_kw_chiusura`, a differenza
del cash-out manuale e del green-up (F6 24/09).

1.6 **Missione**: `alive` contava un pending solo se aveva `bet_id` o era live.

1.7 **Revoca**: `_poll_one_flumine_trade` (paper) chiudeva la riga oltre la scadenza lasciando la richiesta 'pending'
(il live la revoca); il worker non filtra per eta' (`live_order_worker.py`, letto).

1.8 **D1 - simulatore «di casa»**: a gate/porta KO il paper riempiva con `E.paper_fill` sul book dell'istante, senza
bet delay e senza coda, dove il live va in REST FOK (bet delay applicato da Betfair). Catalogo 7.14.

1.9 **D3**: `_maybe_void_orphan` a 48 h in paper scriveva `void pnl=0` (P&L inventato); in live allarme e posizione
aperta.

1.10 **D4**: `omega_db._aggregati` legge `get_omega_aggregates()` -> `omega_aggregates_sql(boolean)` senza filtro di
modalita'; il ripiego in casa sommava tutte le righe. Catalogo 7.21. La migrazione del 26/09 aveva separato solo la
pagina (`get_omega_state.aggregates_by_mode`).

---

## 2. Cosa ho cambiato e perche'

(righe di `omega_service.py` finali salvo diversa indicazione; vedi `patch_prima.diff`)

2.1 **FOK in paper**: `_place_via_canale` (FOK sempre) e `_flumine_enqueue_place` (`payload["time_in_force"]` sempre).

2.2 **Parziale** - superato da 2.8: il ramo che lo gestiva non esiste piu'.

2.3 **Fonte vera del paper e riconciliazione unica**: `_ORDINI_PAPER_SIMULATI`, `_ricorda_ordine_paper`,
`ricorda_chiusura_paper`, `_ordini_paper_per` (stesso id E stesso mercato E stessa selezione). `reconcile_pending`:
paper e live passano dalla STESSA `reconcile_decision`; paper sul registro del simulatore, live su Betfair; nessun
annullo REST per una riga paper. Dopo D1 il registro lo alimentano solo le chiusure paper eseguite subito dal
simulatore di `execution.close_trade` (cash-out manuale, green-up, proposte): e' il reperto per D1 di §6.
Memoria di processo: un riavvio la perde e la riga orfana si libera (test dedicato), mai inventata.

2.4 **`read_control` KO**: `_leggi_controllo` (2 tentativi, pause 0 / 0,5 s); `_fasi_di_gestione` (estratte da
`run_once`, identiche); `_giro_senza_controllo`: con l'ultimo controllo valido **non piu' vecchio di 300 s**
(`_ULTIMO_CONTROLLO_MAX_ETA_S`) gira solo la gestione; oltre, o senza controllo, SOLO la riconciliazione
(`"controllo": "scaduto" | "assente"`). Mai aperture, manuali, missioni o cambi di stato.
**Freno e stato fermo nel giro degradato (conferma con file:riga):**
- nessuna apertura puo' partire: `_giro_senza_controllo` non chiama mai `scan_and_place*`, `process_manual`,
  `process_missions` (il freno delle aperture `_freno_rest_aperture` e' quindi irrilevante: non c'e' apertura da
  frenare); test `test_bot_fermato_durante_il_buco_non_riparte_con_il_controllo_vecchio`,
  `test_read_control_ko_giro_di_sola_gestione_con_l_ultimo_controllo`;
- le chiusure (uscite) passano dalle STESSE funzioni del giro normale (`_fasi_di_gestione`), che nel giro normale
  girano anche a bot fermo/in arresto (`run_once` le chiama PRIMA del ramo `status`); il freno non ferma le
  chiusure per regola condivisa (`safe_strategy/execution.py:803-812`, «il freno vale SOLO sulle APERTURE»;
  canale: `motore_ordini` R7 del banco). Quindi nel giro degradato freno e stato si comportano esattamente come in
  un giro normale a bot fermo: nessuna apertura, uscite protette. Lo stato 'stopping' non passa a 'stopped'
  (servirebbe una scrittura che il DB giu' non accetta): lo fa il primo giro buono.
- oltre 300 s nemmeno le uscite (se l'utente ha cambiato `greenup_mode`/`uscite_protezione` durante il buco, il
  controllo vecchio non lo sa): test `test_controllo_troppo_vecchio_solo_riconciliazione`.

2.5 **Proposte**: `omega_proposte.py` `_esegui_da_solo` passa `**S._porta_kw_chiusura(params, modo_riga)` e registra la
chiusura (`ricorda_chiusura_paper`).

2.6 **Missione**: `alive = any(status in ("open", "pending"))` in entrambe le modalita'.

2.7 **Revoca paper** alla scadenza dura (come il live): revocata -> NO-FILL `paper_revoked_deadline`; revoca persa ->
si aspetta.

2.8 **D1 - niente simulatore «di casa» nelle aperture**:
- `_place_one` ramo paper: runner (canale sopra, coda qui) oppure `_leg_certain_failure(...,
  "paper_runner_non_disponibile", {"motivo_runner": <perche' il gate e' chiuso>}, consuma_tentativo=False)`:
  nessun ordine esiste, il tentativo non si consuma (rifiuto prima del mercato, come canale giu' e freno).
- `_manual_place` ramo paper: runner (coda) oppure riga terminale `paper_runner_non_disponibile` e risposta
  `{"error": "paper_runner_non_disponibile"}` all'utente.
- `execution_mode='rest'` in paper: `_porta_per` e `_flumine_paper_gate` lo ignorano (solo per il paper di Omega; il
  gate unificato `_flumine_gate` usato anche da Safe e Mike tramite `execution._gate` resta INVARIATO) e
  `_avvisa_rest_in_paper` scrive l'attivita' `execution_mode_rest_in_paper` («vale solo per il live: in paper
  l'ordine passa dal runner»).
- `paper_fill_fallback` non esiste piu' per le aperture di Omega (nessuna riga lo scrive).

2.9 **D3**: `_maybe_void_orphan` ora ritorna uno `MarketSnapshot` CHIUSO dedotto dal risultato vero
(`meta.result_ht`/`result_ft`, scritti da `track_event_results` dal feed unico: nessuna chiamata in piu') solo in
paper; il chiamante (settlement nudo e in coppia) regola con la STESSA strada di un mercato chiuso. Risultato assente
o voce non determinabile -> allarme `orphan_live_alert` (con `mode`) e posizione aperta, come in live. Live: mai
dedotto. `omega_engine.vince_col_risultato` (pura) gestisce punteggi e «Any Other Home/Away Win / Draw / Any
Unquoted» usando i punteggi QUOTATI salvati in `meta.runners`; se non li ha, None (non si regola).

2.10 **D4**: `omega_engine.righe_della_modalita` (gamba di chiusura = modalita' dell'apertura, riga senza modalita' =
'paper' come il default del DB `omega_bot.sql`); `omega_db.aggregates/aggregates_coppia(day_start, mode=None)`: con
`mode` usa la RPC nuova `get_omega_aggregates_modalita(p_mode)` e, PRIMA della migrazione, calcola in casa dalle righe
filtrate dichiarandolo (WARNING una volta per processo). Servizio: `_aggregati_cached(..., mode=)` con una cache PER
MODALITA'; il giro, le statistiche a bot fermo, il tetto del manuale (modalita' dell'ordine) e i tetti globali delle
proposte (modalita' della posizione) usano la modalita' giusta; `_con_modalita` dichiara CRITICAL se un lettore non
sa separare le modalita'. `_c_e_fretta` guarda tutte le cache (ritmo pieno se c'e' una posizione in qualunque modalita').

2.11 **Banco R3** (`trasporto_rapido.py`, docstring R3 e `_r3`): Omega paper deve uscire come il live: FOK oltre la
liquidita' ucciso, 0 abbinato, 0 residuo, riga 'error'.

### File toccati
`Betfair/omega/omega_service.py`, `omega_proposte.py`, `omega_engine.py`, `omega_db.py`,
`Betfair/stream/backtest/trasporto_rapido.py` (solo R3); test esistenti adeguati: `test_omega_service.py`,
`test_omega_audit_2026_09_11.py`, `test_omega_certificazione_2026_09_11.py`, `test_omega_flumine_live.py`,
`test_omega_flumine_paper.py`, `test_t3_consapevolezza_2026_09_17.py`, `test_omega_avvio_app_2026_09_16.py`,
`test_omega_giornata_gambe_2026_09_11.py`, `test_omega_modello_definitivo_2026_09_11.py`, `test_omega_v2_2026_09_09.py`,
`tests/test_porta_ordini_omega_f6_2026_09_24.py`, `tests/test_raccordo_v3_2026_09_17.py`,
`tests/test_omega_kill_switch_rest_o1_2026_09_24.py`, `tests/test_omega_freno_non_consuma_tentativi_2026_09_26.py`.

### File nuovi
`Betfair/omega/tests/test_cantiere_c_parita_paper_live_2026_09_28.py`; `Betfair/omega/tests/runner_paper_finto.py`
(runner paper finto per i test che hanno bisogno di una posizione paper aperta: contratto coda/specchio di `omega_db`,
esito dichiarato finto, il matching vero e' del banco); `migrations/omega_aggregati_servizio_per_modalita_2026-09-28.sql`;
`AUDIT_2026-09-28/cantiere_c/{falsifica_c.py, controllo_consegna.py, esito_falsificazione.txt, env_vero.txt, patch_prima.diff}`.

**Sui test esistenti adeguati (45 circa):** dopo D1 i test che APRIVANO una posizione paper col vecchio simulatore di
casa (per collaudare altro: settlement, target, V3, missioni...) ora la aprono dalla strada vera del paper: runner
finto + `run_once`/scan VERO + `poll_flumine_pending` VERO (`gira`/`conferma`). Le asserzioni sul loro oggetto non sono
cambiate. I test che collaudavano il simulatore di casa stesso sono stati riscritti sulla nuova regola (apertura non
eseguita / ordine al runner), ciascuno con commento «CANTIERE C (28/09)».

---

## 3. Test

### 3.1 Comandi (dal worktree; i 20 interruttori dei canali del `.env` a "0" nell'ambiente, elenco in `falsifica_c.py`)
```
.venv\Scripts\python.exe -m pytest Betfair/omega -q -p no:cacheprovider
.venv\Scripts\python.exe -m pytest Betfair/omega/tests/test_cantiere_c_parita_paper_live_2026_09_28.py -q -p no:cacheprovider
.venv\Scripts\python.exe AUDIT_2026-09-28\cantiere_c\falsifica_c.py
.venv\Scripts\python.exe AUDIT_2026-09-28\cantiere_c\controllo_consegna.py
```

### 3.2 Numeri
| Esecuzione | Base 2eb3c1d | Dopo |
|---|---|---|
| `Betfair/omega` + test del banco `test_strada_unica_banco`, interruttori a 0 | 1359 (omega) passati, 0 rossi | **1421 passati, 3 saltati, 0 rossi** |
| `Betfair/omega` col `.env` vero | 111 rossi (inquinamento pre-esistente) | **86 rossi, 0 nuovi** (i 6 file adeguati ora spengono da soli gli interruttori: 25 rossi pre-esistenti in meno) |
| 15 file esterni collegati (stream, safe_strategy, tests di contratto) + `Betfair/mike/tests` | - | **1472 passati, 0 rossi** |
| test nuovi `test_cantiere_c_...` | - | tutti verdi (45+ casi) |

Il banco `test_profilo_rapido_verde_sulla_registrazione_vera[omega]` e' verde (§3.3).

### 3.3 La prova su flumine vero (banco)
`test_strada_unica_banco_2026_09_25.py::test_profilo_rapido_verde_sulla_registrazione_vera[omega]` (registrazione
35760084, `_place_via_canale` di produzione -> motore vero -> flumine): R3 paper ora `('annullato', 0.0, 0.0)`, riga
'error', identico al live dello stesso scenario; il test e' VERDE e diventa ROSSO con la mutazione M1.

### 3.4 Falsificazioni (`cantiere_c/esito_falsificazione.txt`)
**22 mutazioni, 22 ROSSE**; hash dei 5 file di produzione invariato, `MUTAZIONE`=0, `git diff` identico a
`patch_prima.diff`. M1 fa diventare rosso anche il banco R3 (flumine vero). M16 e' la mutazione del coordinatore
(sopravvissuta alla prima consegna, ora rossa). Le mutazioni della prima consegna sul simulatore «di casa» (ex
M3/M4/M6) non esistono piu': il codice che mutavano e' stato tolto (D1) e le sostituiscono M18-M20.

| Mut. | Difetto reintrodotto | Rossi |
|---|---|---|
| M1 / M2 | FOK solo live (canale / coda) | 3 / 3 |
| M5 | riconciliazione paper con fill dalla riserva | 3 |
| M7 / M8 | chiusura in volo registrata / cash-out che non registra | 1 / 1 |
| M9-M12 | `read_control` senza protezione / controllo vecchio usato per aprire / nessun ritentativo / senza controllo gira tutto | 3 / 2 / 1 / 1 |
| M13 | proposte fuori porta | 1 |
| M14 | missione: pending paper non vivo | 1 |
| M15 | richiesta paper stantia non revocata | 2 |
| M16 | ordine di un'altra riga accettato (coordinatore) | 2 |
| M17 | nessuna eta' massima del controllo | 1 |
| M18 / M20 | torna il fill di casa (automatico / manuale) | 3 / 2 |
| M19 | 'rest' chiude il runner in paper | 2 |
| M21 / M22 | orfano paper non regolato / esito dedotto anche in live | 2 / 1 |
| M23 / M24 | servizio che somma le modalita' / DB in casa senza filtro | 2 / 1 |
| M25 | «Any Other» senza punteggi quotati | 2 |

---

## 4. Migrazioni SQL (NON applicate)
1. `migrations/omega_aggregati_servizio_per_modalita_2026-09-28.sql` - RPC nuova `get_omega_aggregates_modalita(text)`
   (riusa `omega_aggregates_sql(boolean, text)` del 26/09, gia' applicata). Nessuna funzione esistente toccata.
   Prima dell'applicazione il servizio calcola in casa (log WARNING una volta). Verifica nel file.

---

## 5. Parita' paper/live - TABELLA DI OGNI RAMO DI `Betfair/omega/`

| # | Ramo | Paper | Live | Verdetto |
|---|---|---|---|---|
| P1 | apertura sul canale `_place_via_canale` | FOK | FOK | **BUG corretto** (R8), prova banco R3 |
| P2 | apertura sulla coda `_flumine_enqueue_place` | FOK | FOK | **BUG corretto** (R8) |
| P3 | apertura senza runner (`_place_one`) | **NON eseguita**, motivo, tentativo non consumato | REST FOK (bet delay di Betfair) | **BUG corretto** (D1: niente piu' fill di casa). Il live ha una strada in piu' (Betfair esiste), il paper non inventa un esito |
| P4 | freno sulle aperture | stesso punto, stesso esito | idem | uguale |
| P5 | gate della coda `_flumine_gate` | runner PAPER | + `omega_live_via_flumine` + revoca | uguale nell'ordine (interruttore di sicurezza dei soldi veri) |
| P6 | porta `_porta_per` | canale anche con `execution_mode='rest'` | canale se `auto` e `omega_live_via_flumine` | uguale nell'esito (FOK + bet delay in entrambi); 'rest' dichiarato in attivita' |
| P7 | chiusure (cash-out, green-up, **proposte**) | porta FOK+riduzione | idem | proposte: **BUG corretto** |
| P8 | annulli | mai REST per paper | canale, ripiego REST | uguale per costruzione |
| P9 | esiti dal canale | evento; oltre TTL annullo; poi NO-FILL | evento; oltre deadline Betfair | uguale nell'esito |
| P10 | esiti dalla coda | FOK; oltre scadenza **REVOCA** | FOK; deadline, REST, revoca | revoca: **BUG corretto** |
| P11 | orfano senza richiesta | NO-FILL (storia) | riga cancellata | uguale nell'esito |
| P12 | `reconcile_pending` | `reconcile_decision` sul simulatore | `reconcile_decision` su Betfair | **BUG corretto** |
| P13 | conferma fallita (log) | warning | CRITICAL | solo gravita' del log |
| P14 | mercato sparito 48 h | **risultato vero**, altrimenti allarme e aperto | allarme e aperto | **BUG corretto** (D3) |
| P15 | posizione di conto | saltata | letta | per costruzione (nessun conto paper) |
| P16 | annullo sugli eventi chiusi dall'utente | mai | ordini vivi con bet_id | residuo minimo, §6 |
| P17 | manuale | coda FOK o **NON eseguito** | coda FOK o REST FOK | **BUG corretto** (D1) |
| P18 | missione viva | pending = vivo | idem | **BUG corretto** |
| P19 | `read_control` KO | gestione <= 300 s, poi riconciliazione | idem | uguale |
| P20 | aggregati del servizio | **solo paper** | **solo live** | **BUG corretto** (D4) |
| P21-24 | size minima, commissione, tentativi, LAPSE | uguali | uguali | uguale |

**Strada unica:** nessuna apertura paper di Omega puo' piu' aggirare il runner: non c'e' piu' un ramo che riempie in
casa (`paper_fill_fallback` non viene piu' scritto da Omega); a runner giu' l'apertura e' dichiarata non eseguita. Le
CHIUSURE paper passano dalla porta quando l'interruttore e' acceso (anche con 'rest'); a interruttore spento e runner
giu' restano sul simulatore di `execution.close_trade` (reperto §6, cantiere D1).

---

## 6. Cosa NON ho fatto / cosa NON ho potuto verificare

- **REPERTO PER IL CANTIERE D1 (chiusure paper col fill istantaneo, file NON toccato):**
  `Betfair/safe_strategy/execution.py:737-790` (`place`, ramo `if mode == "paper":` dopo il gate): una CHIUSURA paper
  di Omega (`close_trade`, :1644) che non ha la porta (interruttore `OMEGA_ORDINI_VIA_CANALE` spento) e trova il gate
  della coda chiuso (`execution._gate` :1014 -> `omega_service._flumine_gate`: runner giu', evento non in streaming,
  o `execution_mode='rest'`) viene riempita da `E.paper_fill` sul book dell'istante, senza bet delay: il live nello
  stesso caso va in REST FOK. Con l'interruttore acceso (il `.env` dal 26/09) le chiusure di Omega vanno sempre al
  canale. Proposta: stessa regola di D1 per le chiusure paper (runner o non eseguita col motivo) - decisione del
  cantiere D1 perche' `execution.place` serve anche Safe e Mike.
- **Annullo sugli eventi chiusi dall'utente in paper (P16)**: non esteso. Con FOK su ogni ordine di Omega la finestra
  e' il solo bet delay; estenderlo vuol dire annullare sul canale senza mai il REST per una riga paper.
- **Limite dichiarato di P12**: il registro del simulatore e' memoria di processo.
- **Replay `certifica omega` NON eseguito** (lo lancia il coordinatore): i numeri paper di Omega cambiano (niente
  abbinamenti durante il TTL, niente fill di casa, aggregati per modalita').
- **Suite inquinata dal `.env` vero (reperto, una riga):** con gli interruttori dei canali del `.env` (26/09) la suite
  di Omega ha **111 rossi GIA' sulla base `2eb3c1d`**; tutti i numeri qui sono presi con i 20 interruttori a 0; i test
  nuovi spengono da soli gli interruttori.
- Un test storico instabile osservato una volta (`test_omega_missions.py::test_advisor_presente_su_ft_con_dati_reali_fake`,
  cache dell'advisor): rosso in un giro intero, verde da solo e in tutti i giri successivi. Non toccato.
- Tre righe non ASCII nel diff sono testo PREESISTENTE spostato (blocchi estratti in `_fasi_di_gestione` e nel ciclo
  unico di `reconcile_pending`), non scritto da me.
- Non verificato dal vivo: nessun ordine piazzato.

---

## 7. Decisioni per l'utente

Nessuna soglia, stake, gamba, selezione o cancello decisionale toccato. D1, D3, D4 della prima consegna sono stati
corretti come bug (ordine dell'utente riferito dal coordinatore). Resta da decidere solo:
- **Chiusure paper senza runner** (reperto §6, cantiere D1): stessa regola di D1?
- **D2** (`omega_live_via_flumine` spento: live in REST, paper sul runner): esito equivalente, proposta lasciare.

---

## 8. Controlli dal vivo in paper al prossimo avvio

| Controllo | Dato atteso | Dove |
|---|---|---|
| FOK sulle aperture paper | comandi omega paper con `time_in_force='FILL_OR_KILL'` | diario del motore, `betfair_live_order_requests.time_in_force` |
| Nessun fill di casa | 0 `paper_fill_fallback` di Omega; con runner giu' attivita' `skip reason=paper_runner_non_disponibile` col `motivo_runner` | `omega_activity` |
| 'rest' in paper | se `execution_mode='rest'`, attivita' `execution_mode_rest_in_paper` e ordini comunque in coda/canale | `omega_activity` |
| Nessun parziale paper | nessuna riga paper `open` con `size_matched < size_requested` | `omega_trades` |
| Aggregati per modalita' | prima della migrazione: WARNING «get_omega_aggregates_modalita non disponibile» nel log; dopo: stop/obiettivo di Omega paper insensibili ai trade live e viceversa | log dell'app, `omega_control.stats` |
| Orfani 48 h | paper: `settle_orphan` con `risultato`; senza risultato `orphan_live_alert` con `mode='paper'` | `omega_activity` |
| Buco di rete | `error/read_control_failed`, `stats.degraded`, nessuna riga nuova; oltre 5 min sola riconciliazione | `omega_activity`, `omega_control.stats` |
| Richieste paper stantie | nessuna richiesta Omega paper 'pending' oltre ~2 min; runner giu' -> «revocata da omega» | `betfair_live_order_requests` |
| Uscita automatica proposte | gamba di chiusura con `meta.canale_ref` | `omega_trades` |
