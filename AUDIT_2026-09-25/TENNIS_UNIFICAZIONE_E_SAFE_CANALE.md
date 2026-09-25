# Tennis: iscrizione a caldo unificata col calcio + Safe tennis via canale (25/09/2026)

Delegato Opus del coordinatore. Worktree ribasato su `origin/master` `099412c`.
Nessun commit, nessun push, nessuna scrittura sul DB vero, nessun processo nuovo (solo thread
nel runner). Strategie non toccate (engine/exits di Safe, i 4 bot tennis).
Patch dei file modificati: `AUDIT_2026-09-25/tennis_unificazione.patch`. File nuovi elencati al §8.

## 0. In breve

1. **Unificazione fatta.** Un solo meccanismo, `Betfair/stream/sottoscrizione_a_caldo.py`, usato da
   calcio e tennis. I due piani restano separati.
   - Test esistenti invariati e verdi. Nel calcio c'è un solo test di latenza rosso, già rosso
     anche sul codice di base (§6).
   - Test di parità: stesso `marketSubscription`.
2. **Safe tennis via canale: costruito, SPENTO di serie.**
   - Il runner tennis monta lo **stesso `MotoreOrdini`** sul 47332 (interruttore
     `MOTORE_ORDINI_CANALE_TENNIS`), con il `_dispatch` vero del worker tennis.
   - Aggancio a comando con priorità COMANDO.
   - La porta di Safe tennis esisteva già. È stato corretto un difetto: il ref degli annulli
     era `safe-c…`, rifiutato dal motore.
3. **Banco.** `certifica safe_tennis 35795993 --scenari rapidi --trasporto entrambi`: **ESITO OK**.
   - 14 scenari su 14 OK, in 4,3 s.
   - **Parità RAGGIUNTA**: 2 ordini su 2 e 2 righe su 2 identici, scarto di tempo 0,0 s, 0 REST
     sul canale, 0 `da_seq`.
   - Durata totale 14,0 s.
4. **Tre reperti da portare all'utente (§5):**
   - R-1: sul canale tennis un'apertura sotto il minimo non parte, perché manca il place-and-trim;
   - R-2: il limite di protocollo sul ref Betfair degli ordini del canale (vale anche per il
     calcio);
   - R-3: le partite agganciate da un comando non hanno una riga in `tennis_live_follow`.
5. **Falsificazione**: 23 mutazioni, **23 ROSSE**, 0 sopravvissute, ripristino sha1 OK
   (`tennis_unificazione/falsificazione.txt`).

## 1. Unificazione (residuo 1): cosa faceva, cosa fa

| | Prima | Dopo |
|---|---|---|
| Meccanismo | Due copie:<br>- `auto_follow.SottoscrittoreStream.applica` (calcio);<br>- `iscrizione_a_caldo.sottoscrivi` + `stream_di_mercato`/`filtro_mercati`/`NonPronto`/`LIMITE` (tennis, «replicato 1:1») | UN modulo: `sottoscrizione_a_caldo.py`<br>- `sottoscrivi` `:78` (nuovo `marketSubscription` sulla stessa connessione; `stream_id` previsto assegnato prima dell'invio e rimesso se l'invio fallisce; filtro canonico su stream e strategie; mai vuoto, mai oltre 200; `NonPronto`);<br>- `stream_di_mercato` `:47`, `filtro_mercati` `:65`, `mercati_dello_stream` `:72`, `NonPronto` `:43`, `LIMITE_BETFAIR_MERCATI` |
| Calcio | Corpo proprio | `auto_follow.py:355-362`: `applica` = `_SC.sottoscrivi(fw, _SC.stream_di_mercato(fw), ids)`<br>`NonPronto` e `LIMITE` riesportati (`:86`, `:345`) |
| Tennis | Corpo proprio | `iscrizione_a_caldo.py:284`: i nomi di sempre sono riesportati dal modulo condiviso (`IAC.sottoscrivi is SC.sottoscrivi`). Runner e test invariati |
| Piani | — | Restano diversi per progetto: `PianoFollow` (calcio) e `pianifica` (tennis) |

- **Comportamento.** Identico sugli input reali. Una differenza solo teorica: il calcio contava i
  mercati come lista, il condiviso li conta senza doppioni e scarta gli id vuoti. Il piano del
  calcio passa sempre `sorted(set)`, quindi la differenza non si presenta.
- **Test esistenti, invariati:**
  - `test_auto_follow_2026_09_25.py` + `test_tennis_iscrizione_a_caldo_2026_09_25.py`: 76 verdi;
  - `test_latenza_logica_aggancio_sotto_i_20_ms` è rosso sotto carico (23-263 ms). È rosso anche
    col file `auto_follow.py` ORIGINALE rimesso al suo posto (provato, 52 e 25 ms): test sensibile
    al carico, non una regressione.

## 2. Safe tennis via canale (residuo 2)

### 2a. Motore ordini nel runner tennis

**Prima:** nessun motore nel runner tennis; `/comando/safe_tennis` riceveva `motore_non_attivo`.

**Dopo**, con `MOTORE_ORDINI_CANALE_TENNIS=1`:

**`motore_ordini.py`** (righe minime, SEGNALATE per l'altro delegato):
- parametro `esecutore` e `self._low` (`:554`);
- una riga `LOW = self._low` in 12 metodi;
- prefisso del ref interno preso dall'esecutore in `_su_riga_specchio` (calcio `awlq`, tennis
  `awtq`);
- default dell'esecutore = `live_order_worker`: il calcio è identico (i suoi test sono verdi).

**`tennis_live/esecutore_tennis.py`** (nuovo) espone i nomi che il motore chiama:
- `_dispatch` `:175` → `tennis_live_order_worker._dispatch` VERO (capture della partita, client
  della modalità T1, guardia D2 dello stato del mercato, controlli nativi, `_track_manual`);
- kill-switch e settings: le stesse funzioni che il worker tennis usa già;
- modo di processo `TENNIS_LIVE_ORDER_MODE`;
- `_assert_order_mode`: mai cross-mode su cancel e replace;
- rifiuti DICHIARATI:
  - `place_submin` → `submin_non_percorribile`;
  - `cashout_*` → `azione_non_servibile`;
- `CanaleSoloComandi` `:254`: il `/order` del desktop resta al worker tennis come oggi;
- `costruisci_motore` `:560`:
  - diario `DATA_DIR/_diario_ordini/tennis/` (oppure `TENNIS_MOTORE_DIARIO_DIR`), separato da
    quello del calcio;
  - scrittore asincrono sul client tennis.

**`tennis_live_order_worker.py`** (tutto no-op per la coda DB e per il `/order`):
- `_runner_mode` `:56` legge il modo forzato sul thread;
- `_strategy_ref` `:77`: customerStrategyRef dell'attore (`safe_tennis`), `tennis` di default;
- `_pre_invio` `:88`: diario write-ahead prima di place e greenup (`:639`, `:899`);
- `time_in_force` nel parse (`:155`) e FOK nel `LimitOrder`;
- `reduces_liability` → `min_stake_rules` (`:605`), come il calcio (CERT. 13/09);
- `riga_specchio` pura (`:447`) e osservatori (`:427`): le chiavi della riga DB sono le stesse e
  nello stesso ordine (test);
- `_lucchetto_ordini` `:920`: lo stesso `LUCCHETTO_ORDINI` attorno ai `_dispatch` del worker.

**`tennis_runner.py`:**
- `_monta_motore_tennis` `:2201`, montato all'avvio (`:2408`, solo PAPER/LIVE, mai con `--event`);
- osservatore dello specchio → eventi `order`;
- `motore.aggancia(framework, session)` a ogni build (`:2623`) e `sgancia` quando il framework si
  ferma;
- smontaggio nel `finally`.

**`guardie_tennis.py`:**
- `imposta_ripresa_motore` `:315`: la ripresa d'avvio NON disarma la guardia finché il diario del
  motore non è verificato su Betfair (`:349`);
- se la ripresa era già riuscita prima del montaggio, il diario si verifica al montaggio; se
  fallisce, la guardia si RIARMA.

### 2b. Aggancio a comando

**Prima:** una partita non seguita entrava solo con un follow (a mano o del ponte).

**Dopo:**
- **`AgganciaTennis`** (`esecutore_tennis.py:320`). Ha l'interfaccia di `AutoFollow`:
  - `servibile` `:409`: mercato nello stream + book NUOVO dopo la sottoscrizione;
  - `richiedi` `:434`: zero I/O; il tetto si verifica in RAM col piano vero (`_tetto_pieno` `:468`).
    Rifiuta, e lo dichiara, se il posto è preso da partite a mano, con posizioni o con un comando
    recente;
  - `giro` `:519`: catalogo REST solo MATCH_ODDS tennis (`_catalogo_comando` `runner:2163`,
    `_resolve_market(..., solo_match_odds=True)` `:528`), poi allineamento subito
    (`_allinea_per_comando` `:2183`);
  - thread `aggancio-comandi-tennis` dentro il runner.
- **Il parcheggio e il primo book** sono codice del motore INVARIATO (`_serve_aggancio`,
  `_parcheggia`, `avanza_aggancio`).
- **Piano:** `iscrizione_a_caldo.PRI_COMANDO=3`, fra ARMATA (2) e A MANO (ora 4); `Evento.comando`.
- **Runner** (`_allinea_follow_a_caldo`):
  - la partita del comando è un follow SINTETICO (`follows_con_comandi`), che non si scrive mai
    nel DB;
  - `_manuale` (`:1808`) non la conta come «a mano»;
  - un comando recente è protetto come una posizione;
  - il book di flumine si registra DENTRO il suo ciclo prima di sottoscrivere (`:1955`);
  - `follow_worker` e build includono i comandi (`:2124`, `:2425`);
  - un follow nuovo fatto solo di comandi NON forza la ricostruzione (niente `force_flat`);
  - TTL del comando 900 s (`TENNIS_AGGANCIO_COMANDO_TTL_S`); poi la partita esce dopo la grazia,
    ma mai con posizioni.
- **Runner senza framework:** rifiuto `runner_non_agganciato`, ma il mercato entra nel piano e la
  prossima build lo include (il bot ripete la decisione). Stesso comportamento del calcio.

### 2c. Porta Safe tennis

**Prima:** la porta esisteva già (`porta_per_sport("tennis")`, attore `safe_tennis`, ref
`safe_tennis-t<id>` di F1), ma aveva due problemi:
- il ref degli ANNULLI era `safe-c<bet>`, che il motore rifiuta (prefisso dell'attore);
- la riga risolta dal canale non aveva `meta.esecuzione` e aveva la colonna `size_requested` a
  NULL (C.12a).

**Dopo:**
- `porta_ordini.ref_annullo(..., attore=)` `:204` + `execution.py:554`: `safe_tennis-c<bet>`
  (calcio invariato `safe-c<bet>`);
- `bot_service._risolvi_una_via_canale` (`:946`, righe minime, SEGNALATE: sul file lavora un
  altro delegato): `meta.esecuzione` {percorso canale, ref, fase, chiesto, abbinato, residuo,
  medio} e `requested_size`, quindi colonne valorizzate;
  - vale anche per il calcio: è un'aggiunta e le chiavi di parità sono invariate.

### 2d. Banco

**`porta_banco.py`:**
- `PortaBanco(sport="tennis")` usa il motore con l'esecutore tennis (`:448`);
- `SessioneTennisBanco` `:309` ha le chiavi di `TennisLiveSession`;
- specchio = `_reconcile_tracked` VERO del worker tennis con il motore fra gli osservatori, e
  `tennis_db` nullo solo durante la lettura (`:755`);
- `monta_aggancio_tennis` `:560` + `AllineaBancoTennis` `:368`: `pianifica` vero; la risposta di
  Betfair è simulata col primo book NUOVO, come `SottoscrittoreBanco` del calcio.

**`trasporto.py`:** `safe_tennis` è nella tabella `ATTORI` (`:60`), con `SPORT_ATTORE` (`:64`); il
client è montato su `SPO._PORTE["tennis"]`.

**`trasporto_rapido.py`:**
- scenario d'ordine `posizione-iniettata` (`:93`);
- varianti tennis R8/R10/R10b/R10c/R10d (`:1084-1236`), con le differenze dichiarate nel docstring;
- finestra di mercato di 600 s per gli scenari di aggancio: i book pre-partita del tennis sono
  radi.

**`banco_comune.py:2081`:** `strategia.db` letto dalla traccia delle righe. Senza, `righe coda=0`.

**Controlli** `certificazione_tennis.py`:
- J4 resta rosso per ogni ref estraneo;
- un ordine NATO DA UN COMANDO (`_ordine_del_motore` `:721`: riga con `meta.canale_ref`, stesso
  bet_id o stesso mercato e selezione) va a `J4C-DICHIARATA` (`:769`) → R-2.

**Test esistente modificato (intenzionale):** in `test_strada_unica_banco_2026_09_25.py`,
`test_bot_senza_porta_non_passa_dal_canale` pretendeva che `safe_tennis` NON avesse il canale (F8
non fatta). Ora quella condizione vale solo per `mike`, più un'asserzione che `safe_tennis` ha
l'attore.

## 3. Esito del profilo rapido tennis (una corsa diagnostica + UNA corsa finale)

```
python -m Betfair.stream.backtest.certifica safe_tennis 35795993 --scenari rapidi --trasporto entrambi --worker 1 --data-dir "C:/Users/Admin/Desktop/tennis_rec/20260707" --tracce AUDIT_2026-09-25/tennis_unificazione/tracce_safe_tennis_rapidi_entrambi.json
```

Referto completo: `tennis_unificazione/profilo_rapido_safe_tennis.txt`. Exit 0.

**Scenari di trasporto:** 14, KO 0, 4,3 s.
- R1 abbinato;
- R2 e R2b: freno e mercato sospeso;
- R3: FOK ucciso;
- R4: D5, cioè l'apertura non va e la chiusura va in REST;
- R5 dedup, R6 scaduto;
- R7 kill-switch: apertura rifiutata, chiusura verificata eseguita;
- R8 rifiuto DICHIARATO `submin_non_percorribile`;
- R9: 0 `da_seq`;
- R10: aggancio → 1 ordine, 0 REST;
- R10b: candidata espulsa;
- R10c: posizioni e a mano MAI espulse, `tetto_mercati_pieno`;
- R10d: `in_aggancio` rifiutato, mai in silenzio.

**Parità coda/canale, posizione-iniettata, 35795993:**

| | coda | canale |
|---|---|---|
| ordini | `safe_tennis-t1` BACK 1,22×2,00 FOK @14:29:08.112; `safe_tennis-t2` LAY 1,20×2,03 FOK @14:35:35.548 | identici, scarto 0,0 s |
| righe | #1 won back 1,22×2,0; #2 lost lay 1,20×2,03 (live) | identiche |
| violazioni | 0 | 0 effettive + 2 `J4C-DICHIARATA` (R-2) |
| decisioni | 1053 | 1054 (il canale non blocca il bot sul bet delay; è la stessa nota del calcio) |
| REST sul canale / da_seq / buchi | — | 0 / 0 / 0 |
| motore | — | 2 comandi, 2 accettati, 6 eventi; costo del banco 0,1 s su 4423 book |

La corsa diagnostica aveva trovato due problemi:
- C1: la riga del canale era senza `meta.esecuzione`. Corretto in 2c.
- Righe non tracciate (`db` mancante nel `_Ponte`). Corretto.

## 4. Accendere Safe tennis in PAPER via canale (lo fa l'utente, in quest'ordine)

Prima di tutto va integrato questo lavoro su master.

| # | Variabile | Effetto | Log atteso |
|---|---|---|---|
| 0 | già presenti: `TENNIS_LIVE_ORDER_MODE=PAPER` o `LIVE` (tetto del runner tennis), token `LOCAL_CHANNEL_TOKEN` passato dall'app; `TENNIS_ISCRIZIONE_A_CALDO` ACCESA (default, serve all'aggancio) | — | — |
| 1 | `MOTORE_ORDINI_CANALE_TENNIS=1` (opzionale `TENNIS_MOTORE_DIARIO_DIR`) | il runner tennis monta motore e aggancio sul 47332 | `[tennis-runner] motore ordini ATTIVO sul canale 47332 (diario …\_diario_ordini\tennis), aggancio a comando ATTIVO` |
| 2 | `SAFE_TENNIS_ORDINI_VIA_CANALE=1` | Safe tennis manda i comandi su `/comando/safe_tennis` | `[safe.bot] ordini tennis via canale di comando ws://127.0.0.1:47332/comando/safe_tennis` |

Per ogni ordine:
- attività `canale_inviato` `{trade_id, mode:"paper", ref:"safe_tennis-t<id>", seq, price, size,
  chiusura}`;
- sulla riga, `meta.canale_ref`, `canale_ack_seq` e poi `meta.esecuzione.percorso="canale"`;
- nel diario `<DATA_DIR>\_diario_ordini\tennis\<AAAA-MM-GG>.jsonl`, le righe `inviato`
  (`attore:"safe_tennis"`), poi `ordine` (col `cor` vero), poi `esito`;
- età del comando = `ts_ms − parametri.creato_ms`, sotto 3000.

Su una partita NON seguita, in sequenza:
1. `[tennis-aggancio] aggancio al volo di 1.x (comando safe_tennis)`;
2. `[motore] safe_tennis-tN in attesa dell'aggancio di 1.x`;
3. `[tennis-follow] a caldo sulla stessa connessione: +1 …`;
4. `[motore] safe_tennis-tN agganciato dopo N ms: eseguo`.

A tetto pieno: `[tennis-aggancio] comando su … NON agganciabile: tetto …` (canale_rifiutato
`tetto_mercati_pieno`).

**Tornare indietro:**
1. rimettere a 0 `SAFE_TENNIS_ORDINI_VIA_CANALE`;
2. riavvio dell'app (lo fa l'utente);
3. spegnere `MOTORE_ORDINI_CANALE_TENNIS` per ultimo.

Con il motore spento e la porta accesa, ogni apertura riceve un rifiuto certo (fail-closed).

## 5. Reperti per l'utente

- **R-1 (divergenza, DA DECIDERE):** sul canale tennis un'apertura SOTTO IL MINIMO (BACK < 2,00 €)
  NON parte.
  - È rifiutata dichiarandolo (`submin_non_percorribile`, riga error `canale_rifiutato`).
  - Il runner tennis non ha il place-and-trim; la REST di oggi sì.
  - Le chiusure dichiarate (`reduces_liability`) sotto il minimo passano.
  - Opzioni:
    - accettare;
    - portare il place-and-trim del calcio nel runner tennis (lavoro a sé).
- **R-2 (limite di protocollo, vale anche per il CALCIO):** l'ordine nato da un comando porta su
  Betfair il customerOrderRef di flumine, non `safe_tennis-t<id>`/`safe-t<id>`.
  - Il bot lo rilegge dagli eventi del runner.
  - Ma una riga LIVE rimasta senza eventi oltre la scadenza passa a `X.reconcile_decision(ref=…)`,
    che **non la trova per ref**. Poi `_annulla_prima_del_terminale` agisce solo se il bet_id è
    noto.
  - Il diario del runner (`riprendi_da_diario`) copre il riavvio del runner, non questo caso.
  - Fix proposto (NON fatto, fuori perimetro):
    1. l'evento `order` porta il cor vero;
    2. Safe lo salva in `meta.canale_cor`;
    3. `ref_di_riga` e `reconcile_decision` lo includono.
  - Nel banco è `J4C-DICHIARATA`.
- **R-3:** le partite agganciate da un comando NON hanno una riga in `tennis_live_follow`, quindi
  il Terminale non le mostra come seguite.
  - Ricevono comunque ladder e now sul DB come ogni partita nello stream: non sono «silenziose»
    come quelle automatiche del calcio.
- **R-4 (test, preesistente):** `build_order_client(PAPER)` scrive `flumine.config.place_latency =
  0,6` per tutto il PROCESSO.
  - Nella stessa sessione pytest, dopo `test_tennis_iscrizione_a_caldo_2026_09_25.py`,
    `test_profilo_rapido_verde_sulla_registrazione_vera[omega]` diventa rosso (R3 paper).
  - Provato: con `TENNIS_PAPER_LATENCY_MS=120` è verde.
  - Il mio file di test ripristina la latenza con una fixture; il file dell'iscrizione a caldo è
    lasciato INVARIATO, come da brief.

## 6. Test e falsificazioni

**Nuovi:**
- `Betfair/stream/tests/test_sottoscrizione_a_caldo_unica_2026_09_25.py` (4):
  - identità delle funzioni;
  - spia del calcio;
  - **parità del `marketSubscription`** calcio/tennis su `BetfairStream` vero;
  - stesse regole: vuoto, oltre 200, NonPronto, errore d'invio.
- `Betfair/stream/tennis_live/tests/test_motore_ordini_tennis_2026_09_25.py` (26):
  - dispatch vero, capture, client e diario col cor;
  - strategy ref;
  - FOK e riduzione;
  - submin dichiarato, cashout rifiutato, ref senza prefisso;
  - cross-mode;
  - `/order` al worker;
  - specchio → evento, chiavi della riga DB invariate;
  - aggancio: piano, libro nuovo, tetto ×3, protezione, catalogo KO, TTL;
  - priorità;
  - runner: entra a caldo, esce dopo il TTL, restart non forzato;
  - ripresa col diario;
  - interruttore;
  - profilo rapido sulla registrazione vera (saltato se manca).
  - Finti: il `_Db` e il `Banco` del test dell'iscrizione a caldo (classi vere) e il
    `_CanaleBanco`.
- `Betfair/safe_strategy/tests/test_safe_tennis_canale_f8_2026_09_25.py` (8):
  - ref dell'annullo, validato dal `valida_comando` vero;
  - C.12a canale, colonne comprese;
  - J4/J4C.

**Falsificazione** (`tennis_unificazione/falsifica.py`): M1-M23 **tutte ROSSE**, ripristino sha1 OK.

**Suite dei file toccati:**
- tennis_live, auto_follow, motore, porta banco, strada unica, contratto, certifica, punto 6 e
  tutta `safe_strategy/tests`: **2488 verdi**;
- 2 rossi in quella corsa, entrambi spiegati:
  - `test_bot_senza_porta…`: aggiornato (§2d), ora verde;
  - `[omega]`: R-4, verde da solo e con la fixture.
- Sul file della strada unica: 17 su 17 verdi; con i miei test prima: 42 su 42.

## 7. Non verificato

- **Il vivo.** Nessun runner è stato avviato. Non verificati:
  - il `LocalChannel` vero del 47332 con il thread `_ciclo` del motore (nel banco si chiama
    `_gestisci` in linea);
  - il thread dell'aggancio con la connessione Betfair vera;
  - la latenza reale dell'aggancio (catalogo REST + CustomEvent + SUB_IMAGE) contro i 3000 ms di
    `MOTORE_AGGANCIO_MAX_MS`.
- **Il runner a caldo** è provato col banco del test (Flumine vero, `BetfairStream` vero con
  socket finto, pompa del ciclo). Nel banco del certifica la sottoscrizione è sostituita da
  `AllineaBancoTennis`.
- **Le matrici complete** non sono state lanciate: `--scenari tutti` (tennis) e una seconda
  registrazione.
- **Accettato, non misurato:** i bot tennis piazzano dal thread di flumine senza il lucchetto,
  come nel calcio.
- **Conflitti di merge:** in `motore_ordini.py` e `bot_service.py` lavorano altri delegati.

## 8. File

**Modificati** (nella patch):
- `auto_follow.py`, `motore_ordini.py`;
- `backtest/banco_comune.py`, `backtest/porta_banco.py`, `backtest/trasporto.py`,
  `backtest/trasporto_rapido.py`;
- `tennis_live/guardie_tennis.py`, `tennis_live/iscrizione_a_caldo.py`,
  `tennis_live/tennis_live_order_worker.py`, `tennis_live/tennis_runner.py`;
- `tests/test_strada_unica_banco_2026_09_25.py`;
- `safe_strategy/bot_service.py`, `safe_strategy/certificazione_tennis.py`,
  `safe_strategy/execution.py`, `safe_strategy/porta_ordini.py`.

**Nuovi:**
- `Betfair/stream/sottoscrizione_a_caldo.py`;
- `Betfair/stream/tennis_live/esecutore_tennis.py`;
- i 3 test del §6;
- `AUDIT_2026-09-25/tennis_unificazione/`: `falsifica.py`, `falsificazione.txt`,
  `profilo_rapido_safe_tennis.txt`, `tracce_safe_tennis_rapidi_entrambi.json`, `strumenti/` (gli
  script di modifica usati).
