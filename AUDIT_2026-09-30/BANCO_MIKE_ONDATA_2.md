# BANCO DI MIKE - ONDATA 2 (30/09): il banco sollecita le regole che non provava mai

Delegato di costruzione, worktree `agent-a8e127c12a581738f`. Base: master `a7e9f66` +
`AUDIT_2026-09-30/BANCO_QUATTRO_DIFETTI.patch` applicata e committata SOLO nel worktree
(commit temporaneo `747ff90`, "wip: base BANCO_QUATTRO_DIFETTI", da NON fondere).
`BANCO_MIKE_ONDATA_2.patch` = `git diff 747ff90 -- Betfair` (solo il mio lavoro;
`git apply -R --check` verificato). Nessun commit mio, nessun `git add -A` (solo
`git add -N` dei due file di test nuovi per includerli nel diff).
Nota: il worktree era su `fc0428f`, non su `a7e9f66` come da brief: portato su `a7e9f66`
(worktree pulito, nessun lavoro perso) prima di applicare la patch del banco.

Nessuna modifica a `engine.py`, `service.py`, `safe_strategy/service.py` (le mutazioni di
falsificazione sono state applicate e RIPRISTINATE con verifica sha256; `grep MUTAZIONE` = 0,
`git diff --stat` identico a prima). Nessuna strategia toccata.

## File toccati
- `Betfair/mike/certificazione.py` (G2 riscritto, B7 nuovo, E2 punta corretto, G4/RG1 nuovi,
  `SorveglianzaFirme`, `confronta_regolamento`, `elenco_stati`/`stati_mai_visti`, campi del
  `Referto`: `non_esercitato`, `non_applicabili`, `contatori`)
- `Betfair/mike/tools/replay_registrazioni.py` (scenari nuovi, attesa a tempo di mercato,
  libro dei mercati chiusi, coda dopo lo stream, `ev["markets"]` completato, G4, RG1,
  NON ESERCITATO, CP con effetto, `TRASPORTO_OBBLIGATO`, `esiti_del_banco`)
- `Betfair/stream/backtest/banco_comune.py` (`MercatoFlumine.registra_libro_chiuso`,
  `read_book` dei mercati chiusi, `MotoreReplay.avanza_un_book`)
- `Betfair/stream/backtest/chiusura_parziale.py` (spinta dichiarata opzionale, effetto del
  guasto, `Sorveglianza(solo_con_effetto=...)`; di serie SPENTI: altri bot invariati)
- `Betfair/stream/backtest/certifica.py` (segno `NE`, `NA` nella copertura, stati mai visti,
  trasporto obbligato per scenario)
- `Betfair/stream/backtest/registro_bot.py` (campo `trasporti_scenari`, Mike: chiuso-fuori-app -> coda)
- `Betfair/stream/backtest/trasporto.py` (`specchio_canale`, `client_del_canale`)
- test esistente modificato: `Betfair/mike/tests/test_mike_p1_cancello_uscite_2026_09_29.py`
  (1 riga: la firma del test era di 46 minuti prima, `at: KO`; il cancello del motore la
  rifiuterebbe per `APPROVAZIONE_TTL_S` e ora anche G2: portata a 5 s prima)
- test nuovi: `Betfair/mike/tests/test_mike_banco_ondata2_2026_09_30.py` (45),
  `Betfair/stream/tests/test_banco_mike_ondata2_2026_09_30.py` (11)

## 1. G2 sul NUMERO + G4 firma eseguita (revisione A1)
Causa: `_g2` aveva `quando=_nasce_uscita_in_perdita` (ordini con motivo `loss_*`): a uscite
manuali senza firma nessun ordine nasce, quindi mai un caso; e la perdita la riconosceva il
MOTIVO del motore (copia di `engine.uscita_in_perdita`).
Correzione (`certificazione.py`, `valore_uscita`, `_nasce_chiusura_in_perdita`, `firma_valida`,
`_g2`): il netto che la chiusura BLOCCA si calcola qui (gambe abbinate + ordini di chiusura
come abbinati al prezzo che il mercato darebbe, P&L per ogni totale gol ancora possibile, caso
MIGLIORE: conservativo). Una chiusura che parte da uno stato non di chiusura (non
`flatten_pending`) con netto < -0,05 senza firma valida = violazione. Firma valida = proposta e
firma con la STESSA chiave, che e' la chiave di questa uscita (categoria dai ruoli + ciclo), lo
STESSO `close_reason`, non scaduta (`APPROVAZIONE_TTL_S`). `loss_cap` resta sempre violazione.
`reentry_time` in profitto senza firma: lecito (avviso del coordinatore; test
`test_g2_chiusura_a_tempo_del_rientro_in_profitto_senza_firma_e_lecita` + gemello in perdita).
G4 (`SorveglianzaFirme`, `FIRMA_ESEGUITA_ENTRO_S = 90` s di mercato): firma nuova vista dal
replay -> esecuzione vista nel `decide` sorvegliato (chiusura con firma valida) -> ordine NUOVO
del bot nella vista di conto del banco (`mercato.ordini`). Firma consumata o viva senza ordini
oltre 90 s = violazione; proposta decaduta = contata a parte.
Scenari nuovi: `uscite-in-perdita-firmate` (firma OGNI proposta dopo 5 s di mercato con
`approva_uscita` vero in `process_requests`) e `uscite-automatiche` (`uscite_automatiche=True`).
Replay (`replay/dopo_uscite_firmate_canale.txt`, 90 s): OK, G2 x1, G4 x2, firme 1 viste / 1
eseguite / 0 violate. `replay/dopo_uscite_automatiche_canale.txt` (70 s): OK, G2 x1 (tace),
P&L -2,59 = banco.
Falsificazione:
- B-5 (G2 senza confronto chiave firma/proposta): ROSSA
  (`test_g2_firma_di_un_altra_chiave_parla`).
- G2 riportato al motivo del motore: ROSSA (`test_g2_motivo_profit_su_una_chiusura_in_perdita_non_la_salva`).
- REPLAY "Mike chiude in perdita senza firma" (`engine.gate_uscite`: `if not uscita_in_perdita(d)` ->
  `if True`) su `base`: **KO, G2 x1** ("chiusura che blocca -2.74 ... senza la sua firma")
  (`replay/mut_gate_base_canale.txt`).
- REPLAY "la firma passa e la chiusura muore nel servizio" (difetto C1: `service` rifiuta
  `under_close`/`over_close` come `feed_stantio`) su `uscite-in-perdita-firmate`: **KO, G4 x76**
  (+ M1 x525, P1/P2/P3) (`replay/mut_firma_uscite_firmate.txt`).

## 2. R3 / NON ESERCITATO (revisione A2, A3)
Causa: sul canale Mike gira in paper e `_sorveglia_posizione_di_conto` esce subito: R3 x0 e OK.
Correzione: `registro_bot.trasporti_scenari` + `replay_registrazioni.TRASPORTO_OBBLIGATO =
{"chiuso-fuori-app": "coda"}`; `certifica` (`trasporto_dello_scenario`) con `--trasporto canale`
fa girare quello scenario sulla coda e lo scrive in testa ("scenari sul loro trasporto") e
nell'etichetta `<coda>`. Con `entrambi` il canale resta per la parita' e li' lo scenario esce NE.
Regola generale: `causa_non_esercitato(scenario, referto)` (contatore-chiave per ogni scenario
speciale; per `copertura-rifiutata*` rifiuti provocati = 0 o S1/S3 a zero; per il CP: nessuna
chiusura con effetto) -> `referto.non_esercitato`; `certifica.segno_referto` stampa `NE` invece
di `OK`, riga `NON ESERCITATO: <causa>` e riga di riepilogo `NE: ...` (exit code invariato).
Replay: `replay/dopo_chiuso_fuori_app_canale.txt` (58 s, comando col canale): `<coda>`, R3 x5836,
SETTLED -10,00 = banco. `replay/dopo_gol_precoce_canale.txt`: **NE** (R1 x0, causa scritta).
`replay/dopo_copertura_rifiutata_canale.txt`: rifiuti 1, S1/S3 x4708 (esercitato).
Falsificazione REPLAY "il bot agisce dopo la chiusura dell'utente" (`engine.decide`: guardia
`chiuso_dall_utente` tolta): **KO, R3 x5** (`replay/mut_r3_chiuso_fuori_app.txt`).

## 3. Il regolamento di Mike sul banco (revisione A6)
Cause (tre, tutte del banco):
(a) `MercatoFlumine.read_book` tornava sempre None;
(b) flumine non consegna i book CLOSED a `process_market_book`: dopo la chiusura dei mercati
il servizio non girava piu' (in produzione gira a timer);
(c) il replay scriveva `ev["markets"]` al PRIMO giro anche con la sola 3,5 nella riga e non lo
completava: il regolamento non trovava il 4,5 (in produzione si arma solo con `info.complete`).
Correzioni: (a) `banco_comune.registra_libro_chiuso` / `read_book` (forma di
`omega_market.read_book`, lettura dei prezzi con `_best_lay`/`_best_back` di produzione; test:
stesso JSON `listMarketBook` dato ai due, risultati identici); `process_closed_market` del
replay registra il libro a ogni consegna; (b) `coda_dopo_la_registrazione`: se una linea di Mike
e' chiusa, il servizio fa i suoi giri alla sua cadenza per `CODA_S = 900` s di mercato dopo
l'ultimo book (nessun book nuovo), fino al terminale; (c) `ev["markets"]` completato appena la
riga porta la linea mancante.
RG1 (`confronta_regolamento`, `esiti_del_banco`): P&L `settled_pnl` di Mike contro il netto del
banco; per riga esito won/lost/void e lordo (`meta.pnl_gross`) contro `runner_status` e
`simulated.profit` di flumine; riga `error` senza P&L = void.
Esito: SETTLING e SETTLED ora visti in tutti gli scenari con posizione; RG1 x1 senza violazioni
in base, taker, gol-precoce, copertura-rifiutata, firma-dopo-gol-decisivo, uscite-*, chiusura
parziale, chiuso-fuori-app (coda). Stati mai visti elencati per nome in ogni referto e in fondo
(`STATI MAI VISTI (par. 6.3)`). Nei miei replay restano mai visti: PRE_GREEN_PENDING,
PRE_LAST_ENTRY_PENDING, IDLE_LIVE (visto solo in bot-fermo/feed-stantio, non rilanciati),
LIVE_SECOND_ENTRY, REENTRY_PENDING/OPEN/GREEN_PENDING (solo sintetiche), ERROR, SKIPPED.
Falsificazione REPLAY `_settle_trades` scrive won/lost scambiati: **KO, RG1 x2**
(`replay/mut_rg1_base.txt`); `read_book` che torna None: ROSSA
(`test_read_book_mercato_chiuso_stessa_forma_della_produzione`).
Il ramo del regolamento in `service.py` (annulli non eseguiti) NON e' toccato: sulla 35760084 la
partita chiude comunque (nessun ordine vivo al regolamento negli scenari girati).

## 4. chiusura-abbinata-in-parte (revisione M2)
Causa: le 3 chiusure colpite erano banche al fischio scadute (abbinato 0,00): CP1/CP3/CP4
contati su una condizione mai accaduta; CP2 `??`.
Correzione: `GuastoChiusuraParziale(spinta_prezzo=True)` (solo Mike): la chiusura APPOGGIATA
colpita che sul libro vero non trova il suo prezzo vede UN livello al suo prezzo per il tetto
(40 %) - `libro_con_spinta`, liquidita' aggiunta DICHIARATA nel referto; il resto dell'ordine
resta vivo con la coda vera. `Sorveglianza(solo_con_effetto=True)`: CP1/CP3/CP4 contati solo
dove il guasto ha avuto effetto (appoggiata abbinata; FOK uccisa che il libro vero avrebbe
abbinato). CP2 in `referto.non_applicabili` -> `NA` nella tabella con la causa.
Replay `replay/dopo_cp_canale.txt` (65 s): banca pre-partita LAY chiesto 10,12, tetto 4,04 ->
abbinato 4,04, 6,08 LAPSE al fischio [SPINTA dichiarata]; 1 chiusura con effetto su 1;
CP1 x4702, CP3 x4702, CP4 x4704, 0 violazioni; `NA CP2`; SETTLED -8,46 = banco (prima -14,00:
cambia per costruzione, la banca ora si abbina in parte).
Falsificazione REPLAY "il parziale trattato come abbinato intero"
(`service._segui_ordini_paper_su_runner`): **KO, CP1 x1** ("abbinato creduto 10.12 contro 4.04"),
CP3 x1, RG1 x3 (`replay/mut_parziale_cp.txt`). Unitaria: regola «solo con effetto» tolta ->
ROSSA (`test_sorveglianza_solo_con_effetto_non_conta_la_chiusura_mai_abbinata`).

## 5. E2 della punta Over (revisione M8)
Correzione (`_e2`, ramo `back`): `commission_pct`, `cover_profit_factor` veri; importo verificato
come per la banca (`cover_residual` sul miglior back x `frazione_copertura`), al centesimo con
`exact_sizes` (di serie), fra floor legale e tetto `cover_max_overshoot_pct` se legalizzato;
piu' piccolo solo se il tetto per partita lo riduce. Le 14 prove E2 della banca: verdi.
Falsificazioni: commissione di nuovo da `params["commission"]` -> ROSSA
(`test_e2_punta_legge_la_commissione_vera`); di nuovo solo "piu' grande" -> ROSSA
(`test_e2_punta_piu_piccola_senza_tetto_parla`). Sul replay `copertura-legacy` NON rilanciato
(vedi sotto).

## 6. M8.11: l'attesa dell'esito taker (revisione A7)
Causa: `S.ATTESA_ESITO_TAKER_MAX_S = 0` nel replay. Correzione: tolto; sul canale
`memoria.attendi` del client vero e' sostituita (solo nel replay) da un'attesa che guarda 50 ms
in tempo vero (conferme del client) e poi fa scorrere i book (`MotoreReplay.avanza_un_book` +
`trasporto.specchio_canale`) fino all'esito o a `timeout` chiesto dal servizio (bet delay + 3 s).
Referto: "attesa dell'esito taker: N attese | esito arrivato | scadute | book passati | s di
mercato" (base: 3 attese, 3 esiti, 859 book, 5,8 s; uscite firmate: 6/6, 22,0 s).
Numeri che cambiano negli scenari esistenti (base, stesso seme; `prima_base_canale.txt` ->
`dopo_base_canale.txt`): tick 56226 -> 56145 (i book passati mentre il bot aspetta non sono
tick del giro), decisioni 5863 -> 5861, `place_pending x2` sparito e `no_fill` 3 -> 2 (l'esito
arriva nello stesso giro come in produzione), letture 3 -> 5 (le 2 `read_book` di regolamento),
stati + SETTLING, SETTLED, righe `open` -> `lost` (regolate). Fill e P&L identici (-14,00).
firma-dopo-gol-decisivo: tick 56226 -> 56116, azioni 9 -> 8, P&L -2,54 identico, M1 1145 -> 1137.
Tempo: base 98,8 s -> 63,5 s (misurato, causa del guadagno non indagata).

## 7. BASSO
- B7 (nuovo): al segno, da piatto e con tutte le condizioni d'ingresso vere (ricalcolate dal
  piano M2.4, veto compreso), l'ultimo ingresso AVVIENE. Test verdi/rossi; replay sintetico
  `_synth_mike_ultimo_ingresso` (`replay/dopo_synth_ultimo_ingresso.txt`, 12 s): B7 x1, 0
  violazioni. Sulla 35760084 B7 x0 (Mike non e' piatto al segno: B6 x0 anche prima).
- A2: la falsificazione e' `test_a2_falsificato_decisione_da_stato_terminale` (rossa con azioni
  da SETTLED/ERROR/SKIPPED), citata nella nota del referto; ora i giri terminali esistono
  (regolamento raggiunto).

## Tempi dei replay (uno alla volta, `--worker 0`, un solo scenario)
base 68 s | uscite-in-perdita-firmate 90 | uscite-automatiche 70 | chiusura-abbinata-in-parte 65 |
chiuso-fuori-app (coda) 58 | firma-dopo-gol-decisivo 83 | copertura-rifiutata 74 | gol-precoce 65 |
taker 79 | sintetica ultimo ingresso 12. Mutazioni replay: 70-85 s l'una. Scenari aggiunti al
giro `tutti`: 2 (circa +140 s di CPU); la `coda` dopo lo stream aggiunge 601 giri senza book per
scenario (pochi secondi).

## Test
`Betfair/mike`: **1321 passed** (42 s). `Betfair/stream/tests -k "banco or certifica or registro
or chiusura_parziale or cp1 or cantiere_v or strada_unica or trasporto or uscite_manuali or
proposte_modello"`: **671 passed, 25 skipped**. File nuovi: 45 + 11 verdi.

## Copertura par. 6 / catalogo par. 7
6.3 stati per nome + SETTLING/SETTLED via regolamento; 6.4 parziali (abbinato in parte vero) e
settlement con commissione (RG1); 6.7 controlli con `quando` e NE per scenario non esercitato;
6.8 note nuove nel referto. Catalogo: 7.16 (falso positivo evitato: `reentry_time` in profitto,
riga `error`=void), 7.29 (test che passa a vuoto -> NE), 7.30 (mutazioni catturate sopra),
7.36 (G4 legge il mercato, non la confessione del bot).

## COSA NON HO POTUTO VERIFICARE
- `--scenari tutti` NON lanciato (vincolo): tempo totale e numeri degli altri 15 scenari
  (bot-fermo, feed-stantio, esiti-ignoti, riavvio, cashout-*, copertura-legacy, rifiuti-betfair,
  fermo-copertura, lettura-dati-ko, punteggio-ko, firma-...-senza-chiusura, cap-stretto,
  senza-seconda-puntata, copertura-rifiutata-legacy, taker-esiti-ignoti) NON visti dopo le
  modifiche: possibili NE nuovi o RG1 da leggere. Replay Omega/Safe non lanciati (banco_comune,
  certifica, chiusura_parziale toccati: default invariati per costruzione, da confermare).
- `--trasporto entrambi` non provato (con il trasporto obbligato il canale di chiuso-fuori-app
  esce NE: previsto, non visto).
- G4 non distingue "il cancello consuma la firma senza ordini" da "la proposta decade": entrambi
  tolgono proposta e firma; oggi il primo caso conta come decaduta (limite dichiarato).
- L'attesa a tempo di mercato fa un primo sguardo di 50 ms in tempo vero (consegna del client):
  valore scelto, non misurato. La causa del tempo piu' basso (99 -> 63 s) non indagata.
- La `coda` dopo lo stream (900 s, giri senza book nuovi) e' un'assunzione del banco: il
  servizio vero continua a girare; il feed dopo l'ultimo messaggio e' fermo per costruzione.
- La spinta del CP aggiunge liquidita' al prezzo della chiusura colpita: dichiarata, ma e' un
  fill che la registrazione non contiene.
- Sintetica ultimo ingresso: P&L Mike +0,35 contro banco +0,34 (dentro la tolleranza 0,02 di
  RG1: arrotondamento della commissione, non indagato).
- `valore_uscita` e' conservativo (caso migliore): una chiusura PARZIALE in perdita non viene
  accusata da G2.
- Il file `replay_registrazioni.py` e `certifica.py` nel worktree sono a capo LF (li ha
  normalizzati `sed`), gli altri CRLF: il diff git e' pulito; applicare con
  `git apply --3way --ignore-whitespace`.

## Decisioni per l'utente
Nessuna: nessuna strategia toccata. Da portare: (1) CP «solo con effetto» e la spinta sono
accesi solo per Mike; estenderli a Omega/Safe cambia i loro contatori CP; (2) il regolamento di
produzione legge il 4,5 da `ev["markets"]` scritto all'armo: corretto solo perche' si arma con
le due linee (`is_candidate`); da tenere presente se l'armo cambia.
