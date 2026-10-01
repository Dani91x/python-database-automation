# BOT MAI CIECHI: audit e correzioni (01/10/2026)

Delegato Opus del coordinatore admin-01. Worktree `agent-a6c931d3f67770bd7`, base master `97ad749`.
Ordine dell'utente (01/10): «TUTTI I BOT NON DEVONO ESSERE MAI CIECHI PER NESSUN MOTIVO, a meno
che non dipenda da Betfair».

Niente commit. Nessuna strategia toccata: soglie, stake, tetti, gambe e condizioni sono quelle di
master. Nessun processo toccato o lanciato fuori dal banco. Il DB non è stato toccato.
Patch: `AUDIT_2026-10-01/BOT_MAI_CIECHI.patch` (`git diff 97ad749`, file nuovi compresi; master nel frattempo e' avanzato a `5fc34a6`, solo frontend, nessun file in comune).

## 0. Sintesi

- **Difetto del 01/10 corretto.** La riga di Greece U21 v Latvia U21 spariva all'orario previsto
  del fischio. Ora resta pubblicata finché Betfair non mette la partita in gioco o non chiude il
  Match Odds:
  - per le partite con esposizione di Mike non c'è tetto di tempo;
  - per tutte le altre il tetto è 3 h, costante `POST_KO_WAIT_SEC`, lo stesso `_MATCH_OVER_S` di Mike.
- **Stesso buco sulle linee O/U di Mike.** Le linee 3,5 e 4,5 di Mike uscivano dallo stream nella
  stessa finestra: anche questo è corretto. Le linee di una partita di Mike con esposizione
  pre-partita salgono al tier 1,5: prima, a pool pieno, uscivano per prime.
- **Altre tre finestre cieche corrette**, tutte di sola infrastruttura:
  1. un evento in gioco o esposto che esce dalla finestra del catalogo;
  2. la pulizia delle righe orfane all'avvio, che cancellava le righe delle partite in gioco o
     di uno sport col catalogo fallito;
  3. Safe: una lettura fallita del feed trattata come «nessuna riga».
- **Le altre finestre trovate** sono proposte con stima (§3), non toccate.
- **Test.** 29 test nuovi. 15 mutazioni, tutte rosse.
- **Suite.**
  - Prima, su master `97ad749` (copia estratta fuori dal repo): 6669 verdi, 47 saltati, 1 xfail.
  - Dopo: 6717 verdi, 0 rossi, 28 saltati, 1 xfail.
- **Replay** (tutti sotto il tetto di 10 minuti):
  - Mike: 3 scenari, 67 s.
  - Safe: profilo rapido, 69 s.
  - Omega: base, 93 s.
  - Le differenze rispetto a master sono solo quelle prodotte dalla correzione (§2.6).

## 1. Tabella dell'audit

Legenda dell'esito:
- **CIECO-int**: cieco per una causa interna.
- **DICH-Bf**: cecità imposta da Betfair, dichiarata.
- **COPERTO**: non c'è cecità.
- **CORRETTO**: era CIECO-int ed è corretto in questa patch.
- **PROPOSTO**: non corretto, proposta con stima.

Le righe di file sono quelle del worktree dopo la patch, salvo dove indicato «master».

Provenienza delle voci:
- **Verificate di persona, riga per riga**: S1-S6, SF1 e la voce Mike sulla riga assente (M1).
- **Viste in due audit in sola lettura** (sub-agenti Explore), con file e righe ricontrollati a
  campione da me: A (Omega CS/HT), C (scalper fermato al KO), E (eccezione dello scalper nel
  `except` esterno), F1 (finestra del catalogo), F2 (pulizia delle orfane), F6 (lettura del feed
  di Safe).
- Le altre voci vengono dagli audit e vanno lette come «riportate».

### Scanner e feed (riguardano tutti i bot che leggono `safe_strategy_scan` o il canale 47336)

| # | File:riga | Scenario | Cosa vede il bot | Esito | Correzione |
|---|---|---|---|---|---|
| S1 | `scanner.py:380` `in_pre_ko_window` (`0 < delta`), `:432` `is_monitorable`; `service.py:2113` `build_rows`, `:2410` `publish` | Orario previsto del fischio passato, Betfair non ancora in gioco (36132210, 17:00:00-17:02:04) | Riga **cancellata**: niente quote né punteggio. Mike passa a `_sorveglia_senza_dati`, lo scalper auto ferma la sessione dopo 60 s (force-flat), le partite di tennis in ritardo spariscono | CIECO-int → **CORRETTO** | `scanner.in_post_ko_wait` (`:411`), `POST_KO_WAIT_SEC = 3 h` (`:408`); `is_monitorable(..., mo_status, esposto, visto)`; `build_rows` passa le partite esposte di Mike (`:2120`) |
| S2 | `service.py:1077` `pre_ko_ou_candidates` (KO nel futuro) + `opp_candidates` (chiede `inplay`) | Stessa finestra: le linee 3,5 e 4,5 di una posizione di Mike | Le due linee escono dalla sottoscrizione stream (e dal REST di ripiego) | CIECO-int → **CORRETTO** | `_opp_ranked_market_ids` (`:1129-1146`): le partite seguite in attesa del fischio tengono le due linee al tier 1,5, con il catalogo già in mano (0 chiamate) |
| S3 | `service.py:1124` (master: `opp_rank_key(None, open_date)`) | Posizione di Mike pre-partita, pool stream pieno | Le linee della posizione al tier 2 sono le prime a uscire | CIECO-int (a pool pieno) → **CORRETTO** | tier 1,5 se la partita è seguita da Mike |
| S4 | `service.py:189` `_CATALOGUE_PAST_H = 6`, `:614` `refresh_catalogue` (master: `st.metas = metas` sostituisce tutto), `:2584` pruning di `self.events` | Tennis «a seguire» o partita ripresa con orario previsto più di 6 h fa, **in gioco** o con esposizione | Evento tolto dal catalogo: riga cancellata, mercato fuori dallo stream | CIECO-int → **CORRETTO** | `_tieni_eventi_vivi` (`:673`): l'evento resta finché il MO non è CLOSED, tetto `_CATALOGUE_KEEP_MAX_H = 24`; 0 chiamate in più |
| S5 | `service.py:183` `_MAX_MARKETS = 1000`, `sort=FIRST_TO_START` | Giornata con più di 1000 mercati: la coda più lontana resta fuori | In silenzio (log solo info) | CIECO-int (non dichiarato) → **CORRETTO** in parte | WARNING «catalogo TRONCATO». Gli esposti già in catalogo li tiene S4 |
| S6 | `service.py:513` master `orphan_purge_ts = -1e9`; `:2397` `purge_orphans` | Scanner riavviato (app, watchdog): al primo publish le partite in gioco non hanno ancora un book, e uno sport col catalogo fallito ha `metas` vuoto | **Tutte** le loro righe vengono cancellate dalla tabella, anche con posizioni aperte, fino al primo book (secondi) o al catalogo successivo (≥ 30 s) | CIECO-int → **CORRETTO** | `_pulizia_orfani_sicura` (`:2386`): prima pulizia solo con i cataloghi di tutti gli sport caricati e 60 s dall'avvio (`_ORPHAN_FIRST_GRACE_SEC`). La riga vecchia resta e si dichiara da sola (`updated_at`) |
| S7 | `scanner.py:432` (`visto`) | Scanner appena ripartito: «non in gioco» senza nessun book | (rischio introdotto dalla correzione S1, chiuso) una riga «non in gioco» inventata sopra una partita al 70' | evitato | L'attesa del fischio vale solo con un book visto (`"inplay" in ev`) |
| S8 | `scanner.py:807` `is_ht_result_candidate` (`minute < 45`), `service.py:1886-1921` `_prune_opp_blocks` | Safe con posizione su HALF_TIME (1X2 primo tempo) nel recupero del primo tempo | Blocco tolto dal payload: `_exit_wait("prezzi_non_nel_feed")`, nessun prezzo | CIECO-int | PROPOSTO (S): tenere il blocco finché il mercato non è CLOSED se c'è esposizione |
| S9 | `scanner.py:55` `OPP_MAX_EVENTS = 20`, `select_opp_candidates` (esenta solo Mike) | Posizione di Safe su O/U o BTTS di una partita uscita dalla top 20 per minuto | Prezzi fermi; ripiego REST di Safe (10 s per mercato); motivo pubblicato «flusso_interrotto», cioè attribuito a Betfair | CIECO-int (dichiarato male) | PROPOSTO (S/M): esenzione per le partite con righe Safe vive (una select ogni 10 s come `list_mike_followed_event_ids`) |
| S10 | `scanner.py:370` CS ≥30', `:585` HT 15-44'; `service.py:1019-1026` | Gamba 1T di Omega v3 (entra dall'1', `omega_config.py:250`) prima del 15' e nel recupero | CS/HT fuori da stream e da REST: proposte saltate «prezzi_non_freschi» | CIECO-int | PROPOSTO (S/M): esenzione per gli eventi con `omega_trades` open/pending |
| S11 | `service.py:855-862` `flusso_evento` + `omega_service.py:951-959` | Blocco CS/HT rimasto nella riga dopo l'uscita dalla sottoscrizione | La partita intera di Omega risulta «flusso fermo» | probabile, **da verificare sui dati** | PROPOSTO (S): Omega valuta solo il proprio `market_id`, oppure lo scanner marca i blocchi non più sottoscritti |
| S12 | (manca) | Partita rinviata con un `market_id` nuovo | Il nuovo id arriva al refresh dei 300 s; la posizione sul vecchio id «manca» | DICH-Bf (il rinvio vero lo regola Betfair) / da verificare | nessuna |
| S13 | `service.py:2120` (`esposti` = solo Mike) | Esposizione di un bot **diverso da Mike** su una partita non in gioco oltre 3 h dall'orario previsto (tipico: tennis_scalper pre-match su partita molto in ritardo) | Dopo 3 h la riga sparisce come prima | CIECO-int (residuo) | PROPOSTO (M): `esposti` come unione delle esposizioni di tutti i bot (Safe, Omega, tennis, scalper): una lettura consolidata ogni 10 s, 0 chiamate a Betfair |
| S14 | `service.py:1904-1915` (H6) + `scanner.ou_block_decided` | Linee di Mike pre-KO senza punteggio | Blocco marcato `decided: True` (punteggio None letto come linea superata) | etichetta sbagliata, nessuna cecità | PROPOSTO (S): `decided` solo con un punteggio noto |

### Mike (`Betfair/mike/`)

| # | File:riga | Scenario | Cosa vede | Esito | Correzione |
|---|---|---|---|---|---|
| M1 | `service.py:4632-4661`, `_ROW_MISSING_GRACE_S=600` (`:55`), `:4704` | Riga assente per una causa interna (S1, S4, S6 prima delle correzioni) | Nessun prezzo REST (`_books_ripiego_rest` gira solo con la riga presente); dopo 600 s `absent_closed` → ramo di regolamento con `_esegui_annulli` anche a mercato aperto | CIECO-int | Le cause interne note sono chiuse da S1/S4/S6. Resta PROPOSTO (M, piano Mike, modifica minima): con la riga assente e una posizione aperta, prezzi da `_books_ripiego_rest`; prima di `absent_closed`, conferma REST `status == CLOSED`; mai annulli su un mercato letto OPEN |
| M2 | `safe_strategy/porta_ordini.py:390-403` `MemoriaComandi._avanza_seq`; `mike/service.py:1652-1678` | Paper: Mike o il runner ripartono mentre ci sono esiti in volo | Gli esiti persi non si rileggono; una lay appoggiata non ha scadenza | CIECO-int (solo paper), da verificare sul runner | PROPOSTO (M) |
| M3 | `feed.py:423-490` | Feed o ordini vecchi | `flusso_interrotto`, `ripiego_rest`, `flusso_interrotto_senza_rest` CRITICAL | COPERTO / dichiarato | — |
| M4 | `service.py:5027-5034` | Sospensione, intervallo, VAR | `_sorveglia_sospensione` | DICH-Bf | — |
| M5 | `service.py:4902-4916`, `:4684-4728` | Linea decisa dai gol / MO chiuso | Ordini seguiti; regolamento dal conto | COPERTO | — |
| M6 | `service.py:7025-7034` (M8.7) | Lettura del feed dal DB fallita | Ultima lista buona, avviso | COPERTO | — |
| M7 | live: REST ogni `reconcile_every_s` (30 s) | Canale conto (47331) giù | Esiti in ritardo fino a 30 s | COPERTO | — |

### Safe calcio e tennis (`Betfair/safe_strategy/`)

| # | File:riga | Scenario | Cosa vede | Esito | Correzione |
|---|---|---|---|---|---|
| SF1 | `bot_db.py:951` (master `return []`), `bot_service.py:9238-9254` `_leggi_righe_scan` | Lettura di `safe_strategy_scan` fallita (rete, 5xx, 57014) | `[]`: **ogni** posizione `feed_blind` (falso), nessuna uscita, regolamento tutto via REST; con il canale acceso anche le righe fresche del canale vengono scartate (`canale_scan.fondi` itera sulla lista del DB); il log `feed_failed` non scattava mai (l'eccezione era già ingoiata) | CIECO-int → **CORRETTO** | `fetch_scan_rows` torna `None`; si tiene l'ultima lista buona (le righe invecchiano e la freschezza lo dichiara), si ritenta al ciclo dopo, `feed_failed` CRITICAL una volta per episodio e `lettura_feed_ripresa` alla fine (`_avvisa_feed_non_letto`, `:9184`), come Mike M8.7 |
| SF2 | `bot_service.py:4128-4133`, `:5075-5096` `is_blind_relevant` | Riga assente con posizione aperta | Nessuna uscita (`ci pensa il settlement`) anche se il REST potrebbe dare il prezzo; posizioni `pre_ko`/`prematch` dopo il fischio senza allarme | CIECO-int | PROPOSTO (M): `_prezzi_ripiego_rest` anche a riga assente; `is_blind_relevant` vero per le posizioni pre-KO a KO passato |
| SF3 | `exits.py:231-245` | Feed vecchio | `_exit_wait` col motivo, `flusso_interrotto` CRITICAL | COPERTO / dichiarato | — |
| SF4 | `bot_service.py:4217-4220` | Mercato sospeso | `_exit_wait("mercato_sospeso")` | DICH-Bf | — |

### Omega (`Betfair/omega/`)

| # | File:riga | Scenario | Esito | Correzione |
|---|---|---|---|---|
| O1 | vedi S10, S11 | CS/HT non sottoscritti per l'esposizione di Omega; blocchi vecchi | CIECO-int | PROPOSTO (S/M) |
| O2 | `omega_service.py:6944`, `omega_proposte.py:421` | Gamba HT considerata finita al minuto >45 mentre il mercato è aperto nel recupero | **regola di uscita**: da portare all'utente, non toccata | — |
| O3 | `omega_service.py:3260-3312` | Paper via canale: dopo un riavvio di Omega l'esito del runner è perso → `canale_senza_esito` | CIECO-int (paper) | PROPOSTO (S): ripiego su `get_live_order_mirror` |
| O4 | `:7764-7836`, `:3738-3872` | Riavvio, order stream giù (live) | COPERTO | — |
| O5 | `:6865-6911` | Feed vecchio | DICH (`_greenup_blind`, `flusso_interrotto` CRITICAL) | — |

### Scalper calcio (`Betfair/stream/scalper/`)

| # | File:riga | Scenario | Esito | Correzione |
|---|---|---|---|---|
| SC1 | `auto_mode.py:86`, `scalper_service.py:443-450` | Riga assente 60 s al KO → sessione auto fermata (force-flat) mentre la sua vita arriva a KO+10' | CIECO-int (solo sessioni auto, dry-run) → **CORRETTO da S1** (la riga resta) | — |
| SC2 | `scalper_session.py:1625-1631` | Eccezione nel ciclo principale: `error` + `sys.exit(1)` senza sweep degli ordini vivi; il supervisore marca `error` dopo 60 s (`scalper_service.py:866-873`) senza annullare né adottare | CIECO-int (LIVE: ordini a mercato senza padrone) | PROPOSTO: sweep per bet_id anche nell'`except` esterno (S); supervisore che annulla `source='scalper'` e manda un CRITICAL (M) |
| SC3 | `scalper_session.py:619-660` | Stream di sessione muto: alert CRITICAL ma nessun ripiego | dichiarato, ma resta cieco | PROPOSTO (M): REST dei mercati esposti + riconnessione |

### Tennis (`Betfair/stream/tennis_live/`) e runner/watchdog

| # | File:riga | Scenario | Esito | Correzione |
|---|---|---|---|---|
| T1 | `tennis_bot_service.py:525-542,593-598`; `tennis_runner.py:1483` | Partita in ritardo fuori dal feed ≥600 s e stato non OPEN → chiusa; il runner scrive SUSPENDED anche senza nessun book | CIECO-int / dichiarato male (S1 copre ora le prime 3 h) | PROPOSTO (S): chiudere solo su CLOSED o mercato sparito; stato «sconosciuto» senza book |
| T2 | `tennis_runner.py:569,1006-1018` | Ricostruzione del runner: blotter vuoto, stato interno della strategia perso | da verificare | PROPOSTO (M/L) |
| R1 | `tennis_runner.py:1388-1403,2243-2266`; `runner.py:1347-1370,1664-1678` | Stallo dello stream con esposizione: il riavvio viene rinviato senza limite | dichiarato; il blocco è una regola nostra | PROPOSTO (M): nuova `marketSubscription` sulla stessa connessione |
| R2 | `watchdog.py:88-89,279-322` | Crash entro 5 s classificato `lock` → watchdog fermo per sempre con un solo WARN; un figlio bloccato ma vivo non viene mai riavviato | CIECO-int | PROPOSTO: codice d'uscita dedicato per il lock (S); riavvio sul battito vecchio (M) |

## 2. Correzioni fatte

### 2.1 Attesa del fischio (S1-S3), il difetto del 01/10

- **Dove**
  - `scanner.py`: `POST_KO_WAIT_SEC`, `in_post_ko_wait`, `is_monitorable` con i nuovi argomenti
    per nome `mo_status`, `esposto`, `visto`. Senza argomenti nuovi la firma storica si comporta
    come prima, salvo il ramo nuovo.
  - `service.py`: `build_rows` passa `mo_status`, `esposto` (dalla lista `_mike_followed`, già in
    cache da 10 s) e `visto`. `_opp_ranked_market_ids` tiene le linee di Mike.
- **Regola**
  - Dopo l'orario previsto, una partita non ancora in gioco e con il MO non CLOSED resta
    monitorata. Con esposizione non c'è tetto; senza, il tetto è 3 h.
  - Vale solo se un book della partita è già stato visto.
- **Zero chiamate a Betfair in più.**
  - Il MO era già tenuto in stream da `is_relevant_market` (KO passato = rilevante).
  - Le linee di Mike hanno già il catalogo, preso nel ramo pre-KO.
  - Il REST di ripiego copre gli stessi mercati che coprirebbe un minuto prima del fischio.
- **Test**: `Betfair/safe_strategy/tests/test_attesa_fischio_2026_10_01.py` (19 test). Coprono lo
  scenario esatto: Mike esposto con il KO previsto passato da 1 s, non in gioco, resta
  monitorabile; senza esposizione esce dopo il tetto + 1 s; in gioco resta; MO CLOSED esce;
  `publish` non mette la riga fra le rimosse; le linee restano nello stream senza chiamate.
- **Effetti collaterali da conoscere (decisione del coordinatore)**
  - (b) vale per **tutti** gli sport, come chiesto. Lo scalper auto (dry-run) e la lista
    partite del tennis vedono ora le partite non ancora in gioco fino a 3 h dopo l'orario
    previsto.
  - Quindi una partita di tennis in ritardo resta seguita e può essere armata. Prima spariva
    all'orario previsto. Se si vuole il ramo (b) solo per il calcio è una riga
    (`sport == "calcio"` in `build_rows`).
  - Più righe scritte: solo write-on-change, al più una ogni 2,5 s per evento.

### 2.2 Catalogo che tiene gli eventi vivi (S4, S5)

- `service.py:661-700`.
- **Test**: `test_bot_mai_ciechi_2026_10_01.py::test_catalogo_*`. Verificano che restino gli
  eventi in gioco e quelli esposti, mentre escono i chiusi, quelli senza esposizione e quelli
  oltre 24 h; che l'indice dei mercati e lo stream li conoscano ancora; che non ci siano chiamate
  in più; e il caso tennis.

### 2.3 Pulizia delle righe orfane solo quando è sicura (S6)

- `service.py:161-172` (costanti) e `:2386`.
- **Test**: `test_pulizia_orfane_*`. Coprono il catalogo tennis mancante, l'avvio appena fatto,
  e a regime la cancellazione della sola orfana vera (la partita in gioco resta). Usano uno
  scanner non dry con le tre funzioni di `db` finte, con le stesse firme.

### 2.4 Safe: lettura del feed fallita (SF1)

- `bot_db.py:951` e `bot_service.py:9180-9254`. `_FEED_KO` è dentro `svuota_le_cache`: il test
  di contratto `test_svuota_le_cache_d2` lo pretendeva ed era rosso nella prima corsa della
  suite.
- **Test**:
  - `test_safe_lettura_fallita_*`, sia diretto sia nel `run_once` vero con il `FakeDB` di
    `test_bot_service`;
  - `test_bot_db_fetch_scan_rows_torna_none_se_la_lettura_fallisce`.

### 2.5 Falsificazione (obbligatoria)

- Script: `AUDIT_2026-10-01/falsifica_bot_mai_ciechi.py` + `_extra.py`. Ripristina byte per byte
  in `finally`; a fine corsa `git diff --stat` era invariato.
- Output: `AUDIT_2026-10-01/falsifica_bot_mai_ciechi_out.txt`. **15 mutazioni su 15 rosse**:

| Mutazione | Rossi |
|---|---|
| F1 `is_monitorable` senza attesa del fischio (comportamento vecchio) | 10 |
| F2 `build_rows` ignora l'esposizione | 1 |
| F3 linee di Mike fuori dallo stream durante l'attesa | 1 |
| F4 pre-KO seguita al tier 2 | 1 |
| F5 attesa che ignora CLOSED | 2 |
| F6 tetto ignorato | 2 |
| F7 attesa senza nessun book (riga inventata al riavvio) | 2 |
| F8 pulizia senza margine dall'avvio | 1 |
| F9 pulizia con un catalogo mancante | 1 |
| F10 catalogo sostituito per intero (vecchio) | 2 |
| F11 catalogo che ignora l'esposizione | 1 |
| F12 catalogo che tiene i mercati chiusi | 1 |
| F13 Safe: lettura fallita = `[]` (vecchio) | 2 |
| F14 `bot_db` torna `[]` (vecchio) | 1 |
| F15 avviso a ogni ciclo invece che a episodio | 1 |

### 2.6 Replay sul banco comune (registrazione 35760084)

Il banco non ha uno scenario «fischio in ritardo», ma la registrazione lo contiene da sola:
- orario previsto 16:00:00;
- Betfair in gioco circa alle 16:00:25-30.

Confronto con master `97ad749`, riga per riga (tolti tempi e WARNING), con lo script
`AUDIT_2026-10-01/confronta_referti.py`.

Master è stato estratto **dentro** l'albero del repo con tutti i file di radice: con una copia
fuori dal repo il `.env` del principale non si trova e cambia il trasporto di Safe. Vedi §5.

| Bot | Comando (con `--data-dir <principale>/_live_raw`) | Durata | Esito | Differenze rispetto a master |
|---|---|---|---|---|
| Mike | `certifica mike 35760084 --scenari base,riavvio,feed-stantio --trasporto canale --worker 0` | 67,1 s (parete 71 s) | 3 OK, 0 violazioni | vedi sotto |
| Safe | `certifica safe_base 35760084 --scenari rapidi --trasporto entrambi --worker 1` | 69,3 s | 14 scenari di trasporto OK; PARITÀ coda/canale **NON RAGGIUNTA** | **identico a master** (anche master oggi dà NON RAGGIUNTA: §5) |
| Omega | `certifica omega 35760084 --scenari base --worker 1` | 93,0 s | OK, 0 violazioni | solo «giri senza riga nel feed» 3 → 1 e «righe scritte» 432 → 434 |

**Mike: il banco mostra il difetto e la correzione.** Con la sonda
`AUDIT_2026-10-01/sonda_motivi_mike.py` (decisione per decisione, trasporto canale, su entrambi i
codici):

- **Master**: Mike è **cieco dalle 15:59:57 alle 16:00:30,5** (nessuna decisione per 33 s; la
  riga sparisce alle 16:00:00).
- **Correzione**: decide in continuo, ogni 1-2 s:
  - alle **16:00:25,5**, ancora pre-partita, vede il residuo della banca di green e lo
    riappoggia (`green resting appoggiata (residuo)`, 1 azione);
  - alle 16:00:30,5 entra in LIVE_KO_GREEN come master;
  - poi attende l'esito di quella banca (`al fischio: attendo l'esito della banca pre-partita
    'under_green-0-3'`, x72) invece di appoggiare subito l'uscita a +2 tick (master: `uscita
    appoggiata a 1.69` alle 16:00:31,6 e `uscita a +2 tick sul book` x142 → 71);
  - copertura alle 16:03:31 identica.
- **Totali uguali**: 6 azioni, 5 ordini, P&L -14,17, stessi stati.
- **Righe del referto che cambiano**, tutte da questa finestra:
  - decisioni 5861 → 5879 (+18 giri visti);
  - «giri senza riga nel feed» 620 → 602 (feed-stantio 19 → 1);
  - `green resting sul book` 974 → 991;
  - D2 2 → 4, D3 1950 → 1986, A1/B2/J1/J3/J5 + poche decine.

  Lo scenario `riavvio` ha le stesse differenze.

Questo è un **cambio di comportamento di Mike** (oggi in LIVE): una decisione presa con il dato
che prima mancava. Le regole sono le stesse; cambia solo che adesso le vede. Va portato
all'utente.

**Scenario nuovo proposto per il banco** (non costruito): `fischio-in-ritardo`.
- Sulla registrazione vera, lo stato `inplay` del MO (e delle linee) viene trattenuto per N
  secondi dopo l'orario previsto. N = 120, come il 01/10.
- È un ritardo applicato a un fatto vero, non un fill a mano.
- Controlli:
  - nessun giro senza riga fra l'orario previsto e l'in-play;
  - le linee della posizione restano fra i mercati rilevanti;
  - nessun regolamento o annullo nella finestra.
- Serve anche che il banco dichiari `_mike_followed_ids` solo con esposizione, come la
  produzione: oggi il replay di Mike li mette per ogni stato non terminale, WATCH compreso.
- Stima: S/M.

## 3. Proposte non fatte (stima)

In ordine di priorità:
1. **M1 Mike** (M). Con la riga assente: prezzi REST e conferma REST di CLOSED prima del
   regolamento e degli annulli. Bot LIVE, modifica minima secondo il piano Mike: va decisa
   dall'utente.
2. **SC2 scalper** (S + M). Sweep degli ordini nell'`except` esterno; il supervisore annulla gli
   ordini di una sessione LIVE orfana.
3. **S13** (M). `esposti` come unione di tutti i bot.
4. **S9 / S10 / S11** (S/M ciascuno). Esenzioni per Safe e Omega; blocchi vecchi.
5. **S8** (S). HALF_TIME nel recupero del primo tempo.
6. **SF2** (M). Safe con la riga assente.
7. **T1** (S), **R2** (S/M), **O3** (S), **M2** (M), **R1** (M), **SC3** (M), **T2** (M/L),
   **S14** (S).

## 4. Suite

`python -m pytest Betfair/safe_strategy Betfair/stream/tests Betfair/mike -q -p no:cacheprovider`

- **Prima**, master `97ad749` estratto in una copia fuori dal repo: **6669 verdi, 47 saltati,
  1 xfail**, 0 rossi (592,8 s).
- **Dopo, prima corsa**: 6716 verdi, 1 rosso, 28 saltati, 1 xfail. Il rosso era
  `test_svuota_le_cache_d2`: `_FEED_KO` mancava in `svuota_le_cache`; corretto.
- **Dopo, corsa finale**: **6717 verdi, 0 rossi, 28 saltati, 1 xfail** (255,7 s).
- La differenza dei saltati (47 contro 28) viene dalla copia fuori dal repo, che non trova file
  del principale. I 29 test nuovi spiegano il resto: 6669 + 29 + 19 saltati in meno = 6717.

## 5. Cosa non ho potuto verificare / reperti fuori perimetro

- **Banco dipendente dalla posizione del checkout.**
  - Lanciata da una copia fuori dall'albero del repo, la certificazione cambia: non trova il
    `.env` del principale né i file di radice (`inplay_intensity_by_league.json` ecc.). Cambiano
    il trasporto di Safe e i conti dei modelli d'uscita di Mike.
  - Safe safe_base «rapidi» oggi dà **PARITÀ NON RAGGIUNTA** anche su master. Nella coda la
    riga va in `canale_giu:apertura_non_inviata`, perché l'interruttore del canale ordini viene
    dal `.env`. Il 30/09 era RAGGIUNTA.
  - Non è causato da questa patch: master e correzione danno lo stesso identico referto. È un
    reperto del banco: la coda dovrebbe spegnere da sé gli interruttori d'ambiente.
- **Non verificate su dati veri**: S11, S12, T2, M2. Restano «da verificare».
- **Replay non lanciati**:
  - **Mike `--scenari tutti`**: il 30/09 durava 394-994 s, a rischio oltre il tetto dei 10
    minuti. Ho lanciato i tre scenari toccati: base, riavvio, feed-stantio.
  - Safe esatto e punta, gli scenari tennis, scalper.
- **Nessuna prova in produzione o in paper**: app viva, Mike in LIVE, nessun processo toccato.
- **Esposizioni degli altri bot**: `_mike_followed` resta l'unica lista di esposizioni che lo
  scanner conosce. Le esposizioni pre-partita degli altri bot (tennis_scalper) sono coperte
  solo per 3 h (S13).
