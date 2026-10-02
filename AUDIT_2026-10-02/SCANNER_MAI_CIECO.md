# SCANNER MAI CIECO: punti 26, 27, 28, 29 (02/10/2026)

Costruttore: delegato Opus. Worktree `agent-af761b24032dde437`, ramo locale `scanner-mai-cieco`
(commit `1d1a027` + `c509176`), base master `67261b9`. Patch completa con i file nuovi:
`AUDIT_2026-10-02/SCANNER_MAI_CIECO.patch` (`git diff master`).

Cosa NON è stato fatto:
- nessun push e nessun commit su master;
- nessun ordine vero, nessun processo lasciato acceso;
- nessuna strategia toccata: soglie, stake, quote, timing e force-flat sono quelli di master;
- nessuna migrazione;
- né suite intera né replay: li lancia il coordinatore.

## 0. Sintesi

| Punto | Prima (master) | Ora |
|---|---|---|
| 27 | Lo scanner conosceva solo l'esposizione di **Mike** (`mike_events`). Con gli altri bot la riga usciva 3 h dopo l'orario previsto. Un evento fuori finestra restava trattenuto solo se di Mike e solo per il calcio | Conosce le esposizioni di **tutti** i bot, paper e live: Omega, Safe calcio/tennis, scalper, sniper, theta, bot tennis, ordini manuali, Mike invariato. Una partita esposta resta finché il Match Odds non è CLOSED **e** nessun altro mercato esposto è noto aperto. Il tetto di 3 h resta solo per chi non ha esposizione |
| 28 | Correct Score solo dal 30' e con ≤3 gol; Half Time Score 15'-44'; 1X2 del primo tempo <45'; linee O/U decise potate; tetto di 20 eventi a gol. **Nessuna esenzione** per Omega e Safe | Un mercato esposto è catalogato con una chiamata mirata per `market_id`, resta sottoscritto e pubblicato fino al suo CLOSED, al tier -1 (davanti a tutto). A pool pieno escono solo i mercati senza esposizione; diario CRITICAL/WARNING |
| 29 | Catalogo oltre i 1000 mercati: solo un WARNING nel log, le partite in coda fuori in silenzio | Gli eventi esposti entrano **sempre**, con una chiamata mirata per `event_id`. CRITICAL in `live_alerts` con l'elenco se non si può. WARNING col conteggio in `live_alerts`, una volta per episodio, più il log a ogni giro di catalogo |
| 26 | Eccezione nel ciclo, Ctrl+C o segnale: `sys.exit(1)` senza annullare nulla. Stop dall'app e freno: dopo i 30 s di force-flat flumine si spegneva lasciando gli ordini rimasti | Prima di uscire si annullano gli ordini **non abbinati** (tetto 10 s). Le posizioni abbinate si dichiarano soltanto, con diario e CRITICAL «posizione lasciata a mercato per arresto»; mai chiuse di iniziativa. Poi lo stato e l'uscita. Stesso codice in paper e live |

Numeri:
- **Test nuovi:** 47 (28 scanner, 19 scalper).
- **Falsificazione:** 34 mutazioni su 34 rosse, più F0 (codice di master).
- **Test mirati:** 1461 verdi, 23 saltati; scalper 597 verdi (§5).

## 1. Documentazione «partita finita»

Il testo completo, con le citazioni, è in **`AUDIT_2026-10-02/SCANNER_PARTITA_FINITA.md`**.

Le fonti del repo bastano solo in parte:
- il PDF ha gli esempi, non gli enum;
- non c'è lo Stream API.

Le definizioni vengono quindi dalle pagine ufficiali, scaricate il 02/10. Copie e estrattore stanno in
`AUDIT_2026-10-02/_fonti_betfair/`. Le citazioni chiave:
- **MarketStatus `CLOSED`**: «The market has been settled and is no longer available for betting».
- **`SUSPENDED`**: «not available for betting». Il `suspendReason` di un mercato calcio è Goal,
  Penalty, Red Card…
- **Stream `status`**: «OPEN, SUSPENDED, CLOSED (settled), etc.».
- **`marketTime`/`openDate`** sono orari *previsti*. **`complete`** riguarda i runner aggiunti,
  **`bspReconciled`** il BSP. Nessuno dei due vuol dire «partita finita».
- **listMarketCatalogue**: «**does not return markets that are CLOSED**». La stessa pagina dice
  `maxResults` ≤ 1000.
- **Stream**: «set to 200 markets by default».
- **Fatto interno**: un Half Time Score è stato CLOSED al 45' con il Match Odds aperto. Quindi lo
  stato di ogni mercato va letto dal suo book.
- **Non documentato da nessuna parte**: se O/U e CS chiudono insieme al Match Odds, quanto durano le
  sospensioni lunghe, i ritardi di regolamento.

**Regola unica derivata:** la partita esposta è finita quando il Match Odds è CLOSED e nessun altro
mercato esposto è noto aperto (ultimo `status` del suo book). Mai un orologio.
- Mercato esposto mai visto: nessun fatto lo dice aperto, quindi vale il CLOSED del Match Odds.
- Evento o mercato esposto che Betfair non restituisce più a catalogo: è CLOSED per definizione.
  Si scrive nel diario, senza CRITICAL.

## 2. Punto per punto (file:riga del worktree finale)

### 27. Esposizioni di tutti i bot

- **Fonte: `Betfair/safe_strategy/db.py:400` `list_bot_exposures()`.** Sola lettura, una SELECT
  filtrata per fonte:
  - `omega_trades` con stato `pending/open/hedged` (`:352`);
  - `safe_strategy_trades`, stessi stati, con `sport` (calcio/tennis);
  - `betfair_live_orders` con stato vivo, in tutte e due le grafie dell'Enum (nome e valore);
  - `betfair_live_positions` con `esposizione_aperta` e non regolate in `betfair_live_settled`. È la
    stessa regola della guardia del catalogo vuoto, `stream/db._posizioni_aperte_non_regolate`;
  - `tennis_live_orders` e `tennis_live_positions`.
- **Limite di lettura delle posizioni:** 7 giorni su `updated_at` (`:363`). Serve perché lo specchio
  non cancella le righe regolate. È un limite di lettura, non una regola di «finita».
- **Fonte che cade:** torna `None` solo per quella fonte. Tabella assente: `[]`.
- **Perché questa via:**
  - è la meno invasiva: usa righe che i bot scrivono già, zero codice nei bot, zero migrazioni, zero
    processi nuovi;
  - è lo stesso schema di Mike (`list_mike_followed_event_ids`, cache 10 s);
  - paper e live insieme, perché nessuna fonte filtra `mode`;
  - `source` non si legge, così una migrazione mancante non può accecare la fonte.
- **Interfaccia unica:** `service.py:1953` `Scanner._esposizioni()`, che restituisce
  `{event_id: {mercati, priorita, bot, sport, bot_mercato}}`.
  - Cache di 10 s; per ogni fonte si tiene l'**ultima lista buona**.
  - In `dry` (banco, collaudo) non c'è lettura DB; il banco può dichiarare `_esposizioni_fonti`.
  - Mike resta su `_mike_followed`, invariato. Le sue due linee e il Match Odds di ogni evento esposto
    vanno in `priorita`.
- **Funzioni di supporto:**
  - `_eventi_esposti` (`:2009`): Mike per primo, filtro per sport;
  - `_mercati_esposti` (`:2027`);
  - `_stato_blocco` (`:2034`);
  - `_esposti_aperti_dopo_mo` (`:2051`): la regola unica di §1;
  - `_avviso_episodio` (`:2076`): un avviso per episodio in `live_alerts`, tramite la coda dello
    scanner che c'era già (`_avvisi_in_attesa` → `_scarica_avvisi` → `stream/db.insert_alert`).
- **`build_rows` (`:2519`).**
  - Prima: `esposti` = solo Mike (master `:2120`) e MO CLOSED = riga fuori (master `:2131`).
  - Ora: esposti di tutti i bot (`:2528`). Con MO CLOSED la riga resta solo se un mercato esposto è
    noto aperto.
- **`_tieni_eventi_vivi` (`:781`).** Prima: Mike e solo calcio (master `:687`). Ora: tutti i bot, ogni
  sport; MO CLOSED con la stessa regola.
- **Tetto di 3 h** (`scanner.POST_KO_WAIT_SEC`): invariato. Morde solo dove `esposto=False`.

### 28. Tetti per CS, HT e mercati a gol

- **`ranked_relevant_markets` (`:1165`).**
  - I mercati esposti noti all'indice (CS, HT, a gol) entrano anche fuori da ogni tetto di
    candidatura, finché il loro stato non è CLOSED.
  - Ogni mercato esposto, compresi il Match Odds dell'evento e le linee di Mike, passa al tier -1
    (`:1215`). Siccome `plan_shards` tronca per shard in ordine di chiave, a pool pieno escono per
    primi i non esposti.
- **`_prune_opp_blocks` (`:2337`).** Il blocco esposto resta nella riga finché non è CLOSED; una linea
  decisa resta marcata `decided`, come prima.
- **`refresh_mercati_esposti` (`:2249`).** Una chiamata mirata `marketIds` (≤100, peso
  `MARKET_DESCRIPTION` = 1) per i mercati esposti ancora ignoti: CS prima del 30', HT prima del 15', a
  gol fuori dal tetto, riavvio. Il mercato va nella cache del suo tipo.
  - Tipo che lo scanner non pubblica: CRITICAL solo se il mercato è di Mike, Omega o Safe, cioè dei
    bot che leggono i prezzi dal feed. Altrimenti diario: scalper e tennis hanno il loro stream.
  - Mercato non restituito: diario, e si richiede dopo 300 s.
  - Cablato nel `tick` con il throttle di 20 s (`:3115`).
- **`refresh_opp_catalogue` (`:2158`).** Nel lotto passano davanti tutti gli esposti, non solo Mike.
- **Diario del pool stream** (`_diario_pool_stream`, `:1345`).
  - Esposto fuori dal pool: CRITICAL `SCANNER_ESPOSTI_NON_SOTTOSCRITTI` con l'elenco, una volta per
    elenco. Il mercato resta sul poll REST di ripiego.
  - Non esposti fuori: WARNING nel log col conteggio, quando cambia.

### 29. Catalogo con tetto 1000

- **`refresh_catalogue`** (`:628`; parsing estratto tale e quale in `_metas_da_catalogo`, `:679`).
- **Priorità:**
  1. gli esposti, sempre, con `_aggiungi_esposti_mancanti` (`:715`): chiamata `eventIds` sul solo
     MATCH_ODDS, senza finestra né tetto. Zero chiamate se non manca nessuno;
  2. quelli in gioco;
  3. i prossimi per orario.

  I punti 2 e 3 sono l'ordine `FIRST_TO_START` di Betfair sulla finestra -6/+14 h, perché chi è già
  iniziato viene prima.
- Fra due cataloghi (300 s), un evento che diventa esposto entra entro circa 20 s (`tick`, `:2996`).
- **(b)** Chiamata mirata fallita: CRITICAL `SCANNER_ESPOSTI_NON_SOTTOSCRITTI` con l'elenco.
- **(c)** Troncamento: WARNING `CATALOGO_TRONCATO` in `live_alerts`, una volta per episodio, con il
  conteggio: eventi dentro, quanti in gioco, esposti aggiunti, ultimo orario dentro. Il log si ripete
  a ogni catalogo.

### 26. Scalper: uscita senza togliere gli ordini vivi

Tutto in `Betfair/stream/scalper/scalper_session.py`.

- **Nuove funzioni:**
  - `ARRESTO_ANNULLO_TIMEOUT_S = 10` (`:487`), `CAUSE_ARRESTO`, `CODICE_ARRESTO`;
  - `_ordini_vivi_lista` (`:494`);
  - `annulla_ordini_vivi_all_arresto` (`:514`): flumine `market.cancel_order` per ogni ordine vivo,
    attesa fino al tetto. Solo in LIVE, se ne restano o flumine è morto: `_sweep_cancel` REST mirato
    ai loro bet_id, **mai market-wide**. In paper niente REST, perché toccherebbe il conto vero
    (stessa regola di `_handle_flumine_crash`);
  - `chiudi_all_arresto` (`:554`): diario e, per le cause di arresto, CRITICAL `SCALPER_ARRESTO` con
    «posizione lasciata a mercato per arresto» e/o gli ordini rimasti. Non solleva mai.
- **Cablaggio:**
  - stop dall'app e freno: `causa_arresto` (`:1678`). Dopo il force-flat esistente e **prima** del
    `TerminationEvent`: `elif causa_arresto in CAUSE_ARRESTO` (`:1733`);
  - eccezione e Ctrl+C: master `except Exception` + `sys.exit(1)` (`:1625-1631`). Ora
    `except (Exception, KeyboardInterrupt)` (`:1768`) → `_uscita_su_eccezione` (`:1779`), che fa
    annullo e dichiarazione, **poi** stato `error` e `sys.exit(1)`. Le altre `BaseException` passano
    come prima: SystemExit e i fermi del banco che simulano un processo ucciso (`_ArmamentoCatturato`,
    `_ProcessoUcciso`). Un primo tentativo con `except BaseException` aveva rotto 2 test del banco: è
    stato ristretto;
  - segnali: `installa_segnali_di_arresto` (`:1816`, chiamata in `main`): SIGTERM e SIGBREAK
    diventano `KeyboardInterrupt`.
- **Invariati:** fine vita, partita finita, crash di flumine (che ha già il suo sweep e il suo
  CRITICAL), e il force-flat delle strategie.
- **Lo sniper (e il theta)** vivono nella stessa sessione: coperti dallo stesso codice.

**Gli altri bot all'arresto** (verifica in sola lettura, nessuna modifica):

| Bot | File:riga | Comportamento |
|---|---|---|
| Mike | `mike/service.py:7114-7127`, `:7214-7223`, `finally` `:7236-7241` | Controlla il file `ARRESTO` ed esce; Ctrl+C e eccezioni non fermano il ciclo. **Gli ordini vivi non si toccano**: le lay appoggiate restano sul conto e la ripresa si affida al DB |
| Safe | `safe_strategy/bot_service.py:10457-10468`, `:10555-10570`, `:10590-10594` | Stesso schema: **nessun annullo** all'arresto |
| Omega | `omega/omega_service.py:8490-8503`, `:8579-8587`, `:8597-8601` | Stesso schema: **nessun annullo**. Gli ordini sono LAPSE |

Nessuno dei tre ha `signal` o `atexit`; il kill forzato è `taskkill /T /F` dopo 25 s
(`desktop/main.js:283-286,489-497`). Reperto R1, non corretto (perimetro).

## 3. Tabella caso → test

Test dello scanner: `Betfair/safe_strategy/tests/test_scanner_mai_cieco_2026_10_02.py`.

| Caso | Test |
|---|---|
| La fonte DB legge tutte le fonti, paper e live; esclude le posizioni regolate e quelle pari; ordini in tutte e due le grafie | `test_db_list_bot_exposures_legge_tutte_le_fonti_paper_e_live` |
| Una fonte che cade non spegne le altre; tabella assente = `[]` | `test_db_una_fonte_che_cade_non_spegne_le_altre` |
| Cache di 10 s e ultima lista buona per fonte | `test_scanner_tiene_l_ultima_lista_buona_per_fonte` |
| Omega, Safe, ordini e posizioni dello specchio: riga oltre le 3 h | `test_partita_esposta_di_qualunque_bot_oltre_il_tetto_resta` (×4) |
| Tennis esposto oltre le 3 h | `test_tennis_esposto_oltre_il_tetto_resta` |
| Senza esposizione, oltre il tetto esce (non regressione) | `test_senza_esposizione_oltre_il_tetto_esce_ancora` |
| MO CLOSED + CS esposto SUSPENDED: riga e CS restano | `test_mo_chiuso_ma_cs_esposto_ancora_aperto_la_riga_resta` |
| MO CLOSED + CS esposto CLOSED: esce | `test_mo_chiuso_e_cs_esposto_chiuso_la_riga_esce` |
| MO CLOSED + mercato esposto mai visto: esce | `test_mo_chiuso_e_mercato_esposto_mai_visto_la_riga_esce` |
| Catalogo: tennis esposto da Safe fuori finestra resta | `test_catalogo_tiene_tennis_esposto_da_safe_fuori_finestra` |
| CS esposto al 10': dentro, tier -1 | `test_cs_esposto_prima_del_30_e_sottoscritto_e_davanti` |
| CS esposto con 4 gol | `test_cs_esposto_con_4_gol_resta_sottoscritto` |
| HT Score esposto al 46' | `test_ht_score_esposto_nel_recupero_del_primo_tempo_resta` |
| O/U decisa con posizione Safe: nella riga (`decided`) e nello stream | `test_linea_ou_decisa_con_posizione_safe_resta_nella_riga_e_nello_stream` |
| Mercato esposto CLOSED: esce | `test_mercato_esposto_chiuso_esce` |
| Tetto dei 20 eventi: l'esposto entra | `test_tetto_dei_20_eventi_non_esclude_una_partita_esposta` |
| Pool pieno: esce il non esposto (con il vero `plan_shards`) | `test_pool_pieno_escono_solo_i_mercati_senza_esposizione` |
| Diario del pool: CRITICAL solo per gli esposti, un episodio | `test_diario_del_pool_critical_solo_per_gli_esposti` |
| Mercati esposti ignoti: una chiamata `marketIds`, poi zero | `test_mercato_esposto_ignoto_entra_con_una_chiamata_per_market_id` |
| Tipo non pubblicato: CRITICAL solo per i bot sul feed, mai richiesto di nuovo | `test_mercato_esposto_di_tipo_non_pubblicato_critical_solo_per_i_bot_sul_feed` |
| Mercato non restituito (chiuso): niente CRITICAL, niente raffica, richiesta dopo il TTL | `test_mercato_esposto_non_restituito_e_chiuso_niente_critical_niente_raffica` |
| Catalogo troncato: l'esposto entra con `eventIds`, WARN col conteggio, un episodio | `test_catalogo_troncato_l_esposto_entra_sempre_e_warning_col_conteggio` |
| Chiamata mirata fallita: CRITICAL con l'elenco | `test_catalogo_esposto_mancante_chiamata_fallita_critical_con_elenco` |
| Evento esposto non restituito: niente CRITICAL, niente raffica | `test_catalogo_esposto_che_betfair_non_restituisce_e_chiuso_niente_critical` |
| Nessun esposto mancante: zero chiamate in più | `test_catalogo_senza_esposti_mancanti_zero_chiamate_in_piu` |

Test dello scalper: `Betfair/stream/tests/test_scalper_arresto_ordinato_2026_10_02.py`.

| Caso | Test |
|---|---|
| Annullo via flumine, paper e live; l'ordine abbinato non si tocca | `test_arresto_annulla_gli_ordini_vivi_via_flumine_paper_e_live` (×2) |
| Live, flumine morto: REST mirato, mai market-wide | `test_arresto_live_flumine_morto_ripiego_rest_mirato_mai_market_wide` |
| Paper, flumine morto: nessun REST | `test_arresto_paper_flumine_morto_nessun_rest_sul_conto_vero` |
| Tetto di tempo, poi ripiego | `test_arresto_annullo_con_tempo_massimo_poi_ripiego_live` |
| Nessun ordine vivo: nessuna chiamata | `test_arresto_senza_ordini_vivi_nessuna_chiamata` |
| Posizione abbinata: CRITICAL, mai chiusa, per ogni causa | `test_posizione_abbinata_lasciata_a_mercato_critical_mai_chiusa` (×4) |
| Piatto: niente CRITICAL | `test_arresto_piatto_senza_ordini_nessun_critical` |
| Ordini rimasti (paper): CRITICAL | `test_ordini_rimasti_vivi_in_paper_critical` |
| Non solleva mai | `test_chiudi_all_arresto_non_solleva_mai` |
| Except esterno → uscita ordinata | `test_l_eccezione_del_ciclo_passa_dall_uscita_ordinata` |
| Annullo prima dello stato e di `sys.exit` (eccezione e segnale) | `test_uscita_su_eccezione_annulla_prima_dello_stato_e_di_sys_exit` (×2) |
| Senza framework: nessun annullo | `test_uscita_su_eccezione_senza_framework_nessun_annullo` |
| Stop dall'app e freno passano dall'arresto prima del `TerminationEvent` | `test_stop_dall_app_e_freno_passano_dall_arresto_prima_di_spegnere_flumine` |
| Segnale → `KeyboardInterrupt`; handler installati | `test_segnale_di_arresto_diventa_keyboardinterrupt` |

**Finti:**
- righe postgrest con le colonne delle migrazioni;
- `OrderStatus` vero di flumine;
- oggetti betfairlightweight con gli attributi veri;
- filtri prodotti dal vero `betfairlightweight.filters` (`eventIds`, `marketIds`, `marketTypeCodes`).

**Conftest.** `Betfair/safe_strategy/tests/conftest.py` ha una fixture autouse nuova: nei test
`list_bot_exposures` restituisce `{}`. Senza, gli scanner non-dry dei test esistenti avrebbero letto
il DB vero: è successo una volta durante la costruzione, in sola lettura, prima della fixture.

## 4. Falsificazione

Script: `AUDIT_2026-10-02/falsifica_scanner.py`. Esito: `AUDIT_2026-10-02/falsifica_scanner_out.txt`.
Lo script ripristina byte per byte con un'asserzione; `git status` dei file mutati è pulito (l'unica
`M` vista era la mia modifica non ancora committata, poi committata in `c509176`).

**Esito: 34 mutazioni su 34 rosse.**

| Gruppo | Mutazioni |
|---|---|
| Punto 27 | F1, F2: il comportamento esatto di `aa5749a`, solo Mike (6 e 1 rossi); F3, F4: la regola «finita» nei due versi; F10 |
| Fonte DB | F19-F22 |
| Punto 28 | F5-F9, F15-F18 |
| Punto 29 | F11-F14 |
| Punto 26 | G1, G1b (il difetto originale `sys.exit` senza annullo), G2-G7, G9-G11 |

**F0** = i test nuovi sul codice di master: errore di importazione, perché le funzioni non
esistono. Il rosso **comportamentale** contro il codice di prima lo danno F1/F2 (scanner) e G1/G1b/G2
(scalper).

Esempio di mutazione sopravvissuta poi corretta: alla prima corsa **G1 era sopravvissuta**. Il test
del cablaggio leggeva solo il sorgente. L'uscita è stata estratta in `_uscita_su_eccezione` con un
test di comportamento; alla seconda corsa G1 e G1b sono rosse.

## 5. Test mirati (numeri esatti)

- **Test nuovi:** 28 + 19 = **47 verdi**.
- **Tutti i file di test che importano `safe_strategy.service`, `safe_strategy.db`, `ScannerReplay` o
  `banco_comune`** (52 file, compresi i test del banco che usano lo scanner vero): **1461 verdi,
  23 saltati**, 0 rossi (118 s).
  - I saltati sono test che cercano le registrazioni o i file del checkout principale (`_live_raw`),
    assenti nel worktree. Non verificati da me.
- **Scalper/sniper/theta/freno/fine evento/stream muto/contratto strada unica** (filtro dei nomi in
  `Betfair/stream/tests`): **597 verdi**, 0 rossi.
  - Prima corsa: 2 rossi in `test_scalper_certificazione_2026_09_24` per `except BaseException`;
    corretti.
- Suite intera e replay: non lanciati, come da brief.

## 6. Banco di certificazione

Nessun controllo del banco riguarda lo scanner:
- lo scanner è `NON_BOT` in `registro_bot.py:361`;
- non esiste nessuna famiglia L1/L2;
- `banco_comune.pubblica` (`:2354-2359`) rimuove in silenzio le righe non volute;
- LIMITE 2 dichiarato: un evento per volta, nessun tetto morde.

Quindi **nessun controllo aggiunto**.

Proposta, non costruita:
- un contatore delle righe rimosse in `banco_comune.pubblica`, con lo stato del Match Odds e
  l'esposizione dichiarata;
- un controllo «partita esposta rimossa prima del CLOSED» sollecitato da uno scenario che dichiara
  `_esposizioni_fonti`.

Stima: S/M.

In `dry` il banco non legge il DB. Per Mike le liste che il banco dichiara (`_mike_followed_ids`)
danno esattamente gli stessi insiemi di prima. L'unica differenza possibile è l'**ordine** dei
mercati rilevanti, perché il tier -1 vale anche per il Match Odds e le linee di Mike; l'insieme non
cambia.

## 7. Reperti e cose NON verificate

- **R1. Mike, Safe e Omega non annullano gli ordini vivi all'arresto** (§2, tabella). Non corretto,
  per perimetro. Da portare all'utente.
- **R2. Tempi dello stop dello scalper.**
  - Il supervisore termina la sessione dopo 60 s (`scalper_service.py:707-723`); `main.js` concede
    70 s.
  - La sessione può impiegare fino a 90 s di force-flat (30 s per maker, sniper e theta), più ora
    10 s di annullo, più lo stop letto al battito di 5 s.
  - Il `terminate()` di Windows (TerminateProcess) e `taskkill /F` non si possono intercettare:
    in quel caso l'annullo non gira.
  - Proposta: il supervisore manda CTRL_BREAK, che ora la sessione gestisce, e allunga l'attesa.
    Non toccato.
- **R3. Fine vita e partita finita dello scalper** spengono flumine dopo 30 s anche con ordini vivi
  rimasti. Lasciati invariati perché non sono un «arresto». Con la partita CLOSED gli ordini sono già
  decaduti; a fine vita (KO+vita) no. Da decidere.
- **R4. Contratto «strada unica»** (`test_contratto_strada_unica_2026_09_25.py:236-242`):
  `scalper_session.py` era già autorizzato. Il suo `motivo` cita solo `_sweep_cancel`; ora c'è anche
  `market.cancel_order` all'arresto. Il test è verde; la frase va aggiornata da chi tiene il contratto.
- **R5. Esposizione di Mike in produzione e nel banco.** In produzione gli ordini paper di Mike via
  runner entrano anche nello specchio, quindi le sue linee esposte valgono per la regola «MO CLOSED +
  mercato aperto». Nel banco (`dry`) no. Divergenza solo nel caso, raro, di un Match Odds chiuso con
  una linea ancora aperta.
- **R6. Carico DB.** 6 SELECT (+1 sulle regolazioni) ogni 10 s, cioè circa 60.000 letture al giorno
  in più. Leggere, filtrate, ma da conoscere (cfr. «-86.000 letture/giorno» del 30/09). Il TTL è
  `Scanner._ESPOSIZIONI_TTL_S`; si può alzare (es. 30 s) se l'utente preferisce.
- **R7. Un'esposizione nata da meno di 10 s** (TTL) non è ancora nota allo scanner.
- **R8. Righe dei diari dei bot rimaste aperte per errore** (es. un `pending` mai piazzato). Tengono
  la riga oltre le 3 h solo finché il Match Odds non è CLOSED; un evento non più a catalogo si scrive
  nel diario, senza CRITICAL. Le posizioni tennis non hanno una tabella di regolazione: una riga
  stantia vale «aperta», ma il Match Odds CLOSED la libera.
- **R9. Cache dei mercati esposti senza book.** `_refresh_score_catalogue` toglie dalla cache i mercati
  CS/HT di eventi senza book. Un esposto risolto su un evento senza book può essere richiesto ogni
  20 s finché il primo book non arriva. Non verificato sui dati.
- **Non verificato:**
  - replay e suite intera (li lancia il coordinatore; durata attesa invariata, perché in `dry` niente
    DB e calcoli trascurabili);
  - comportamento contro il DB vero (le colonne lette sono quelle delle migrazioni);
  - forma reale degli `status` nello specchio tennis;
  - effetto di `market.cancel_order` chiamato dal thread principale con flumine vivo. Il precedente
    è `run_scalper_live.py:183-187`; nessun test con flumine vero.
- **Documentazione scritta dopo il primo codice.** La sezione «partita finita» è stata scritta dopo
  le prime righe di codice del punto 27 (il brief chiedeva prima). La regola codificata è quella del
  documento; i test di §3 la verificano.

## 8. Rischi di regressione e come li ho esclusi

- **Bot che vedono righe che prima sparivano** (partite esposte oltre le 3 h; Match Odds CLOSED con
  un esposto aperto e `mo_status: CLOSED` nel payload). È il comportamento richiesto. Il secondo caso
  vale solo con un fatto positivo, cioè un mercato esposto visto OPEN o SUSPENDED.
- **Ordine del pool.** Cambia solo la priorità degli esposti. Lo shard dipende dall'id del mercato
  (`shard_index`), quindi nessuna risottoscrizione in più a pool non pieno.
- **Chiamate a Betfair in più:** solo quando un esposto manca, con throttle di 20 s e richiesta dopo
  300 s per i non restituiti. Zero chiamate a regime: provato da
  `test_catalogo_senza_esposti_mancanti_zero_chiamate_in_piu` e dal primo assert di
  `test_mercato_esposto_ignoto_...`.
- **Test esistenti:** tutti verdi (§5). Nessun test esistente modificato; solo la fixture del
  conftest.
- **Banco:** nessuna lettura DB in `dry`; i fermi `BaseException` del banco passano come prima.
- **Paper e live:** stesso codice; l'unica differenza, voluta, è il REST di ripiego solo in live.
