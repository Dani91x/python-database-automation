# T0C — SOLO GLI STRUMENTI: cassetta, ombra, tolleranze, congelamento, determinismo, impronte (referto, 09/10/2026)

Delegato T0C (cloud), ramo `tappa0-cassetta-ombra` da `0aa76dfa`. Mandato: 05 §1 T0C passi 2, 3, 4, 6 (NON il congelamento
finale). Nessuna strategia toccata; nessun file fuori dal dominio dichiarato salvo UNA riga d'elenco in un test di contratto
(§9). Il manifesto VERO (`ARCHITETTURA_2026-10/riferimenti_congelati/MANIFEST.json`) **non** e' stato scritto.

## 0. Sintesi

| Prova | Esito |
|---|---|
| Cassetta: 6 `kind`, JSON Lines canonico, agganci ai punti del piano (righe di oggi in §1) | fatta |
| Additivita' (senza flag nuovi = referto di `0aa76dfa`, esclusi i tempi) Mike/Omega/Safe/scalper `base` | **4/4 identici** |
| Innocuita' (cassetta accesa = referto di `0aa76dfa`, esclusi i tempi) Mike/Omega/Safe/scalper `base` | **4/4 identici**; tennis_pro ⊘ (nessuna registrazione tennis nel cloud: lo fa il PC) |
| Ombra `--ombra` + `TOLLERANZE.md` (solo le 3 di U-59) | fatta, exit code 3 a divergenza |
| Falsificazione dell'ombra sul replay VERO di Mike (H §4.3) | vedi §4: tabella mutazione -> esito |
| Falsificazione dei test nuovi (17 mutazioni del codice) | **17/17 rosse**, file ripristinati con sha256 verificato |
| `congela` + `--congela` + `--verifica-congelati` su manifesto DI PROVA | fatta (§5) |
| Determinismo (stesso comando due volte) | Mike, Omega, Safe: **0 divergenze**; scalper: **3 divergenze (`pid`) = REPERTO T0C-R2** |
| Impronte della strategia per Omega, Safe, scalper calcio, tennis | 501 / 800 / 570 / 363 voci; identita' 0 differenze; soglia e condizione cambiate = rosse (16/16) |
| Suite `python -m pytest Betfair/ -q -p no:cacheprovider` | §8 |

## 1. I file (righe di OGGI, il piano citava quelle dell'08/10)

Nuovi, nel banco (`Betfair/stream/backtest/`):
- `cassetta.py` (833 righe): `VoceCassetta` :79, `KINDS` :62, `jsonabile` :90 (mai un `repr` di oggetto: niente indirizzi),
  `canonica`, `Registratore` :181 (`dopo_il_giro` :218 = livello `decisione`), avvolgimenti `_avvolgi_rest` :379,
  `_avvolgi_conto` :408, `_avvolgi_transazione` :421, `_avvolgi_fill` :448, `_avvolgi_specchio` :472, `delta` :494,
  `_avvolgi_db` :520, `_avvolgi_init_db` :572, `_avvolgi_init_referto` :596, `_avvolgi_esegui` :607, `installa` :662,
  `compito` :710 (accende e SPEGNE gli agganci per UN replay), `assembla` :765, `scrivi`/`leggi` (anche `.gz`
  deterministico), `verifica_sigillo` :816.
- `ombra.py` (503): tolleranze :50-78, `Divergenza` :84, `normalizza` :153, `confronta_voci` :246, `descrivi` :328,
  `certifica_con_cassetta` :396, `EXIT_OMBRA = 3` :393, `main` (due cassette a confronto).
- `congela.py` (358): manifesto solo aggiunta con CATENA (`_anello` :159, `aggiungi_voci` :199, `verifica_catena` :237,
  `verifica` :248), `congela_giro` :298, CLI `aggiungi`/`verifica` :330.

Modificato: `certifica.py` (+56 righe, additivo): `_lavora` :479 (cassetta spenta = `_lavora_di_sempre` :502, il corpo di
prima, identico); flag `--cassetta`, `--ombra`, `--congela`, `--verifica-congelati`, `--congelati` in `main` :891; il corpo di
`main` dopo la lettura degli argomenti e' `_certifica` :963, riga per riga quello di prima.

**Gli agganci** (installati SOLO a cassetta accesa, per il tempo di un replay, e tolti anche su eccezione; a cassetta spenta
nessuna funzione e' sostituita: test `test_spenta_nessun_aggancio`, `test_accesa_installa_e_toglie_gli_agganci`):

| Livello | Punto agganciato (riga di oggi) | Nota |
|---|---|---|
| decisione | `MotoreReplay.esegui` `banco_comune.py:2608`, chiamate a `check_market_book`/`process_market_book` :2638-2640 | avvolgimento SULL'ISTANZA della strategia del bot; copre `_Ponte._giro` `banco_comune.py:3232` (Safe tennis), i ponti di Mike/Omega/Safe e il ponte dello scalper (che fa tutto in `check_market_book` e torna False). Il dato e' la DIFFERENZA del `Referto` del bot dopo il book (decisioni, azioni, motivi, sollecitati per codice, violazioni, stati nuovi): il `Referto` si osserva avvolgendo `CERT.Referto.__init__` |
| ordine | `Transaction.place_order/cancel_order/update_order/replace_order` (flumine `execution/transaction.py:62,104,124,169`) | OGNI istruzione che arriva a flumine, di ogni bot e di ogni strada (lo scalper e il tennis non passano da `MercatoFlumine`) |
| ordine | `MercatoFlumine.place_order_live` `banco_comune.py:691`, `cancel_order_live` :873, `place_submin_live` :972 | richiesta del bot e risposta (o eccezione) del banco |
| ordine | `SpecchioOrdini._riga` `varianti_bot.py:359` | le righe `betfair_live_orders` quando nascono |
| fill | `SimulatedOrder._update_matched` (flumine `simulation/simulatedorder.py:543`) | anche i fill del mercato che attraversa (`banco_comune.py:2343`) |
| conto | `MercatoFlumine.pnl_betfair` :1491, `pnl` :1392, `riepilogo_fill` :1368 | |
| riga_db | `DbMemoria.insert_trade` :314, `update_trade` :320, `upsert_event` :303, `log` :334, `set_control` :292 (+`delete_trade` delle sottoclassi) | si avvolge la classe che DEFINISCE il metodo (Omega `DbMemoriaOmega`, Safe `DbSafeMemoria` non chiamano `super()`); i finti dello scalper (`_DbFinto`) e del tennis (`_DbReplay`). `upsert_event` (Mike: ~7.500 chiamate da 6 KB) si scrive come DIFFERENZA colonna per colonna dall'ultima riga della stessa chiave: 48 MB -> 5,7 MB |
| referto | `certifica._lavora` (numeri del `Referto` di ogni replay) e il testo intero del referto stampato da `main` | + testata (comando, versioni, commit/codice: tolleranza 2) e SIGILLO sha256 in coda |

Piu' processi: ogni replay scrive il suo segmento in `$BANCO_CASSETTA_DIR`; il padre li riunisce in ordine canonico.

## 2. Additivita' e innocuita' (prova 1)

Comandi (cloud, `_live_raw/` scompattato da `registrazioni_banco/`, raw e scores con gli sha256 del piano):
`certifica <bot> <evento> --scenari base` su `0aa76dfa` (PRIMA), poi sul ramo senza flag (SENZA), poi con `--cassetta`
(CON). Confronto con `ARCHITETTURA_2026-10/tappa0/T0C_STRUMENTI/prova_innocuita.py` (toglie SOLO le righe dei tempi
`righe_senza_tempi` e il blocco `CASSETTA:` che il flag aggiunge in coda; nemmeno le righe vuote).

| Bot | Comando | PRIMA vs SENZA | PRIMA vs CON | Esito del referto | Voci della cassetta (decisione/ordine/fill/conto/riga_db/referto) |
|---|---|---|---|---|---|
| Mike | `mike 35760084 --scenari base` | IDENTICI (107 righe) | IDENTICI (107) | OK, 0 violazioni | 13.031 (5.247 / 26 / 2 / 3 / 7.640 / 113), 5,7 MB (0,39 MB gz) |
| Omega | `omega 35760084 --scenari base` | IDENTICI (134) | IDENTICI (134) | OK, 0 violazioni (0 ordini) | 1.022 (437 / 0 / 0 / 2 / 443 / 140) |
| Safe | `safe_base 35760084 --scenari base` | IDENTICI (216) | IDENTICI (216) | OK, 0 violazioni (0 azioni) | 7.272 (3.513 / 0 / 0 / 2 / 3.535 / 222) |
| Scalper calcio | `scalper_calcio 35797769 --scenari base` | IDENTICI (55) | IDENTICI (55) | OK, 0 violazioni, 44 azioni | 127.245 (124.146 / 50 / 20 / 0 / 2.968 / 61), 19,7 MB (0,77 MB gz) |
| tennis_pro | `tennis_pro 35790089 --scenari tutti` | ⊘ | ⊘ | nessuna registrazione tennis nel cloud (05 §0.1): **lo fa il PC** | |

Ho usato `safe_base ... --scenari base` (il mandato ammette `rapidi` o `base`). Tempi (macchina libera, una sola misura):
Mike 67 s senza / 69-72 s con cassetta; scalper 76 s / 92 s (+21%: 124.146 decisioni); Omega 43 / 40 s; Safe 62 / 53 s.
Nota: Omega `base` e Safe `base` su 35760084 non piazzano ordini: i livelli `ordine`/`fill` li esercitano Mike e lo scalper.

## 3. Determinismo (prova 4)

Stesso comando due volte (`--cassetta giro1`, poi `--cassetta giro2 --ombra giro1`):

| Bot | Divergenze | Note |
|---|---|---|
| Mike `base` | **0** (13.028/13.028 voci) | dopo aver dichiarato in tolleranza 3 i timbri della macchina trovati QUI (vedi sotto): al primo giro erano 6 divergenze `riga_db` |
| Omega `base` | **0** (1.019) | |
| Safe `base` | **0** (7.269) | |
| Scalper `base` | **3** (`riga_db`, `log` con `pid`) -> exit 3 | REPERTO T0C-R2: niente congelamento finche' non si decide |

E' esattamente il motivo per cui si prova prima di congelare: la prima esecuzione ha trovato, nel codice di produzione,
valori scritti con l'orologio della MACCHINA: Mike `settled_at`/`pnl_betfair_settled_at` (`mike/service.py:6707,6723,6849`,
`now_iso` a :6768), `letto_at` (:6892, :6899), `last_loss_exit_deciso_ts` (:5739); scalper `started_at`/`stopped_at`/
`heartbeat_at` (`scalper_session.py:304` `_now_iso`, 1.475 battiti). Sono timbri d'orologio (come `created_at`), quindi
rientrano nella tolleranza 3 di U-59: sono elencati UNO PER UNO, con la riga che li scrive, in `TOLLERANZE.md` e in
`ombra.CAMPI_ID_OROLOGIO`, con test di falsificazione. Il `pid` no (non e' un orologio).

## 4. Falsificazione dell'ombra (prova 2, H §4.3)

### 4.1 Sul replay VERO (Mike `base`, riferimento = cassetta del giro 1)

Script: `ARCHITETTURA_2026-10/tappa0/T0C_STRUMENTI/falsifica_ombra.py tutte --riferimento <cas> --uscite <dir>`
(mutazioni IN MEMORIA nel processo del replay, nessun file del repository cambiato; ~70 s a giro, 2 in parallelo).

| Mutazione (H §4.3) | Cosa cambia | exit | Divergenze | Livelli rossi | Atteso | Esito |
|---|---|---|---|---|---|---|
| identita' | nulla | 0 | 0 | - | nessuno | come atteso |
| (a) soglia di un tick | `pre_green_ticks` 2 -> 3 | 3 | 17 | ordine, riga_db | ordine | come atteso (es. banca 1.69 -> 1.68, 10.12 -> 10.18) |
| (b) importo 0,01 | ogni banca emessa da `engine._place` +0,01 | 1 | 6.219 | tutti e sei | ordine, riga_db | come atteso (scatta anche il controllo P1 del bot: «ko_green lay 10.13 riproposta 21 volte») |
| (b') importo 0,01 sul parametro | `stake` 10,00 -> 10,01 | 3 | 27 | decisione, riga_db, referto | decisione, riga_db | come atteso (Mike porta la punta a 10,00: ordini identici, diverge il motivo «liquidita 8.02 < 10.01») |
| (c) istante 1 ms | `varianti_bot.ms_di` +1 ms (righe dello specchio) | 3 | 14 | ordine | ordine | come atteso (`_ms` 1782832089862 -> ...863) |
| (d) decisione tolta | la prima decisione con un piazzamento torna senza azioni | 3 | 5.265 | decisione, ordine, riga_db, referto | decisione | come atteso (`azioni: 1 -> 0` al primo giro diverso) |
| (e) `ok` invertito | `engine.riaprira` negata | 3 | 6.002 | tutti e sei | decisione | come atteso |
| (f) colonna DB cambiata | `insert_trade`: `liability` scritta come `responsabilita` | 3 | 5 | riga_db | riga_db | come atteso |
| (g) controllo spento | `certificazione.verifica_consapevolezza` (K1-K4) spenta | 3 | 5.228 | decisione, referto | decisione, referto | come atteso (`sollecitati.K1..K4` spariscono, `?? K1 x0`) |
| sigillo | un byte della cassetta di riferimento | 1 | - | sigillo | sigillo | come atteso |

**10 prove, 10 come atteso.** Exit 3 = replay pulito ma ombra divergente; exit 1 = anche violazioni di condotta.

Nota sulla prima esecuzione: con l'importo mutato sul PARAMETRO `stake` (10,00 -> 10,01) l'ombra era rossa ma solo a
livello `decisione`/`riga_db`/`referto` (motivo «liquidita 8.02 < 10.01»), con ordini identici: Mike porta da solo le punte
a multipli di 0,50 per difetto (`engine._place` :1876). E' la strategia che assorbe il centesimo, non l'ombra che lo perde:
la mutazione `importo_0_01` ora agisce sull'importo EMESSO (banche +0,01) e `stake_0_01` resta in tabella come prova.

### 4.2 Sui test (cassetta sintetica coi sei livelli) e sul codice degli strumenti

`Betfair/stream/tests/test_banco_cassetta_ombra_t0c_2026_10_09.py` (32 test): identita' = 0; soglia di un tick ->
`decisione`+`ordine`; importo 0,01 -> `ordine`; istante 1 ms -> `fill`; decisione tolta -> `decisione`; `ok` invertito ->
`decisione`; colonna DB cambiata -> `riga_db`; controllo spento -> `decisione`+`referto`; netto di un centesimo -> `conto`;
un byte del riferimento -> sigillo rotto; tolleranze 1-2-3 coprono SOLO cio' che dichiarano (righe dei tempi si, nota che
parla di tempo no; hash del codice si, numero dei controlli sulla stessa riga no; id coerenti si, fill spostato sull'altro
ordine no, `bet_id` no, `pid` no, `updated_at` fuori elenco no); gzip deterministico e gzip rotto = sigillo rosso.

Falsificazione dei test (`falsifica_test_t0c.py`, 17 mutazioni del codice di `ombra`/`cassetta`/`congela`/`certifica`, file
ripristinati con sha256 verificato):

| Mutazione | File | Test rossi |
|---|---|---|
| confronto sempre vuoto | ombra.py | 13 |
| tolleranza 1 allargata a «tempo» ovunque | ombra.py | 1 |
| tolleranza 2 toglie l'intera riga del codice | ombra.py | 1 |
| `bet_id`/`pid` fra gli id d'orologio | ombra.py | 2 |
| id d'orologio senza ordinale | ombra.py | 1 |
| sigillo mai verificato | cassetta.py | 2 |
| forma non canonica (chiavi non ordinate) | cassetta.py | 1 |
| `repr` degli oggetti (indirizzi) | cassetta.py | 1 |
| le toppe non si tolgono | cassetta.py | 6 |
| DB delle sottoclassi non osservato | cassetta.py | 2 |
| decisioni mai scritte | cassetta.py | 2 |
| fill non registrato | cassetta.py | 1 |
| manifesto sovrascrivibile | congela.py | 1 |
| catena mai verificata | congela.py | 1 |
| verifica non ricalcola lo sha256 | congela.py | 2 |
| `_lavora` ignora la cassetta | certifica.py | 1 |
| `--congela` senza prova di determinismo | ombra.py | 1 |

**17/17 rosse** (base: 32 verdi, 0 rossi). Alla prima esecuzione «tolleranza 1 allargata» era VERDE: il test non la
discriminava; corretto il test (una nota che parla di tempo, diversa nei due giri, deve essere rossa), poi 17/17.

## 5. Congelamento (prova 3) su un manifesto DI PROVA (cartella temporanea)

Script rieseguibile: `bash ARCHITETTURA_2026-10/tappa0/T0C_STRUMENTI/prova_congela.sh <CARTELLA_TEMP> <CAS_GIRO1>
<CAS_GIRO2>` (rifiuta di girare sulla cartella vera; ~2 min). Sequenza ed esiti (eseguita due volte, l'ultima con lo
script committato), tutto in una cartella temporanea:
1. `certifica omega 35760084 --scenari base --congela --congelati <tmp>` senza `--ombra` -> **rifiutato, rc 2** («vuole la
   prova di DETERMINISMO»);
2. `... --ombra <giro1> --congela --congelati <tmp>` -> ombra 0 divergenze, **CONGELATI** cassetta (`.jsonl.gz`
   deterministico, 24.604 byte) e referto (14.782 byte), rc 0;
3. `python -m Betfair.stream.backtest.congela aggiungi --tipo registrazione ...` (raw, scores, `.gz`) e `--tipo software`
   (`requirements.txt`, `banco_comune.py`): sha256 del raw `8037bac2...` e dello scores `6910bcab...` = quelli del piano;
4. la stessa voce di nuovo -> 0 aggiunte; 5. `certifica --verifica-congelati --congelati <tmp>` -> 7/7 OK, rc 0;
6. secondo `--congela` dello stesso comando -> **rifiutato** (file esistente: solo aggiunta), rc 2;
7. un byte della cassetta congelata cambiato -> verifica **KO** (sha256 diverso), rc 1;
8. `ombra` contro la cassetta ritoccata -> sigillo rotto, DIVERGENTE, rc 1 (e ripristinata: 0 divergenze);
9. una voce del manifesto ritoccata a mano (`comando`) -> **catena rotta**, rc 1; 10. ripristinato -> verde.
Ogni voce porta: percorso, byte, sha256, tipo, comando esatto (senza i flag della cassetta), commit + albero sporco,
versioni (python 3.13.16, flumine 2.13.11, betfairlightweight 2.23.2, sha256 del `pip freeze` dalle distribuzioni
installate, sha256 di `requirements.txt`), sha256 dei sorgenti del banco, data, determinismo (sha256 del primo giro, 0
divergenze), catena.

## 6. Impronte della strategia (prova 5)

`ARCHITETTURA_2026-10/strumenti/impronte/impronta_strategia_bot.py scrivi|confronta [bot|tutti]` (stile di
`e1_impronta_strategia.py`: SHA-1 dell'AST senza docstring/commenti/righe; in piu' metodi e campi di classe e una voce PER
CHIAVE delle tabelle di parametri DEFAULT/PARAM/SPEC). File: Omega `omega_engine, omega_v3, omega_model, omega_empirical,
omega_advisor, omega_proposte, omega_config` (501 voci); Safe `engine, opportunity, exits, risk, selezione, pressure,
combos, calibration, anomaly, tennis_opportunity, veto_campionati` + da `bot_service` `DEFAULT_PARAMS`,
`STRATEGIE_CON_USCITE`, `normalize_uscite_automatiche`, `uscite_automatiche_di`, `resolve_params` (800); scalper calcio
`scalper_bot, sniper_bot, theta_bot, media_under_bot, auto_mode, bias_resolver, risk_semaphore, habitat_scan,
hazard_atlas` + `scalper_session.VALIDATED_PARAMS`, `UI_PARAM_WHITELIST` (570); tennis `tennis_scalper_bot,
tennis_pro_bot, tennis_flb_bot, tennis_swing_bot, tennis_winprob, tennis_score, superficie, condotta_ordini` +
`run_tennis_pro.PRO_PARAMS`, `run_tennis_scalper.TENNIS_PARAMS` (363). TSV generati su questo commit:
`impronta_{omega,safe,scalper_calcio,tennis}.tsv`. Mike resta su `e1_impronta_strategia.py` (386 voci): `confronta` = 0.

Falsificazione (`falsifica_impronte.py`, su copie in cartella temporanea): per ogni bot identita' = 0, commenti/docstring
aggiunti = 0, una soglia cambiata = rossa sulla voce giusta (Omega `MIN_PRICE` 1.01 -> 1.02, cioe' un tick; Safe
`DEFAULT_OPP_PARAMS[min_edge]`; scalper `VALIDATED_PARAMS[scalp_ticks]`; tennis `PRO_PARAMS[stake]`), un `<` -> `<=` in una
funzione = rossa sulla funzione: **16/16 come atteso**. Limite dichiarato: la scelta dei file «di strategia» e' mia (dalle
schede E2-E5 e da `registro_bot.py`); il guscio (servizi, sessioni, runner) e' escluso apposta, salvo i nomi elencati.

## 7. REPERTI (si scrivono e si portano all'utente; nessuno corretto)

- **T0C-R1 (Mike, orologio della macchina nel replay)**: `mike/service.py:5739` usa `_time.time()` per diradare le righe
  `loss_exit_deciso` di `mike_activity` (`_LOSS_EXIT_DECISO_MIN_S`). Nel replay il tempo della macchina scorre ~800 volte
  piu' lento di quello di mercato: QUANTE righe si scrivono dipende dalla velocita' della macchina, e una macchina piu'
  lenta (il PC) puo' scriverne di piu'. Oggi i due giri cloud coincidono nel numero; il valore e' in tolleranza 3. Vale
  la pena che il banco dia a Mike il tempo di mercato anche qui (decisione dell'utente: tocca il banco o il servizio).
  Lo stesso vale per `settled_at`/`letto_at` (timbri della macchina invece del tempo di mercato: innocui per le decisioni).
- **T0C-R2 (scalper, `pid` nella cassetta)**: `scalper_session.py:1590` scrive `os.getpid()` in una riga `log`; il
  determinismo dello scalper e' rosso (3 divergenze) e il congelamento dello scalper e' BLOCCATO. Strade: (a) l'utente
  estende la tolleranza 3 agli identificatori di processo; (b) il banco dichiara un `pid` fisso nel replay dello scalper
  (modifica dell'adattatore, condotta invariata). Non e' una tolleranza che posso aggiungere io (U-59).
- **T0C-R3 (cassette confrontabili solo sulla stessa macchina)**: la prima riga del referto porta il percorso ASSOLUTO
  di `--data-dir`, e con piu' compiti la riga `worker: N su M core fisici`: diversi fra PC e cloud, non coperti dalle 3
  tolleranze. Conseguenza: le baseline congelate sul PC si confrontano sul PC (o si decide una normalizzazione in piu').
- **T0C-R4 (hash delle `.timeline.jsonl` del piano)**: il piano (05 T0C B, H §4.4) da' per
  `registrazioni_banco/*/<id>.timeline.jsonl` `31dc7de9...` e `7a92a5c7...`; nel repository (fine riga LF, `git ls-files
  --eol` = `i/lf w/lf`) sono `0a4253f9...` (35760084) e `9a107208...` (35797769). Probabile `core.autocrlf` sul PC (CRLF
  in copia di lavoro). Al congelamento: hash dalla copia di lavoro DEL PC e `.gitattributes` (`*.jsonl -text`) oppure
  hash del blob git. Tutti gli altri sha256 (raw/scores `.gz` e scompattati) coincidono col piano.
- **T0C-R5 (Omega e Safe `base` non piazzano)**: su 35760084 `base` Omega fa 0 ordini e Safe 0 azioni: la loro ombra
  `base` non esercita i livelli `ordine`/`fill`. Le baseline di Omega e Safe vanno congelate su `tutti` (come da piano).
- **T0C-R6 (dimensione delle cassette)**: in chiaro Mike `base` 5,7 MB, scalper `base` 19,7 MB; compresse (`.jsonl.gz`,
  come le scrive `--congela`) 0,39 e 0,77 MB. Stima per le baseline `tutti`: Mike ~10 MB, scalper ~35 MB, Omega/Safe
  qualche MB: decidere se stanno nel repository o accanto al manifesto (l'hash e' comunque nel manifesto).
- Dall'esecuzione: la riga `CRITICAL:omega.service: ... paper e live SOMMATI` del replay di Omega e' il finto di Omega
  (`aggregates`) che corregge l'altro delegato (T0B 4): congelare Omega solo dopo.

## 8. Suite

`python -m pytest Betfair/ -q -p no:cacheprovider` (cloud, Python 3.13.16, senza `.venv`):
- prima esecuzione coi file nuovi: **1 rosso** (`test_submin_contratto_chiamanti_2026_09_17.py::test_nessun_chiamante_nuovo_non_registrato`:
  `cassetta.py` nomina `place_submin_live`, vedi §9), 11.506 verdi, 65 saltati, 6 xfailed;
- finale: **11.507 verdi, 0 rossi, 65 saltati, 6 xfailed** (444 s). Di cui 32 test nuovi in
  `Betfair/stream/tests/test_banco_cassetta_ombra_t0c_2026_10_09.py`.
- frontend: non toccato (nessun `vitest`/`tsc` necessario).

## 9. Fuori dominio (una riga)

`Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py`: il test di contratto elenca i file che NOMINANO
`place_submin_live`; `cassetta.py` lo nomina per AVVOLGERE `MercatoFlumine.place_submin_live` (osservatore, nessuna copia
della sequenza): aggiunto all'elenco con il motivo. Era l'unico rosso della suite dopo i file nuovi.

## 10. Cosa resta per congelare DAVVERO (dopo T0B 4-6, U-62, U-60; dal PC, durate dichiarate)

Protocollo per OGNI baseline (sulla STESSA macchina su cui si fara' l'ombra, per T0C-R3):
```
python -m Betfair.stream.backtest.certifica <ARGOMENTI> --cassetta <tmp>/giro1.jsonl
python -m Betfair.stream.backtest.certifica <ARGOMENTI> --ombra <tmp>/giro1.jsonl --congela
python -m Betfair.stream.backtest.certifica --verifica-congelati
```
Il secondo comando congela SOLO a 0 divergenze. Durata = 2 x il replay + la cassetta (+0-5% Mike/Omega/Safe, +21% scalper).

| # | ARGOMENTI (comando esatto) | Durata stimata di UN giro (H §1.5, misure 08-09/10) | x2 |
|---|---|---|---|
| A | `python -m Betfair.stream.backtest.congela aggiungi --tipo software requirements.txt Betfair/stream/backtest/*.py` + un `pip freeze > pip_freeze.txt` aggiunto con `--tipo software` | secondi | |
| B | `python -m Betfair.stream.backtest.congela aggiungi --tipo registrazione _live_raw/35760084/35760084.raw.jsonl _live_raw/35760084/35760084.scores.jsonl _live_raw/35797769/35797769.raw.jsonl _live_raw/35797769/35797769.scores.jsonl registrazioni_banco/*/*` + le 22 partite di Safe + tennis `35790089`, `35794049`, `35795993` (raw e score) + le registrazioni di T0B 5 | secondi | |
| 1 | `mike 35760084 --scenari tutti` | ~12 min (728 s; con 3 worker) | ~25 min |
| 2 | `mike 35760084 --scenari base --trasporto canale` | ~1,5 min | ~3 min |
| 3 | `omega 35760084 --scenari base` (DOPO il finto di Omega, T0B 4) | 40 s | 1,5 min |
| 4 | `omega 35760084 --scenari tutti` | 7,3-7,6 min | ~15 min |
| 5 | `omega 35797769 --scenari tutti` | ~7,5 min | ~15 min |
| 6 | `safe_base --scenari tutti` (22 partite, come `safe_base_tutti_PUNTE_MULTIPLE.txt`) | ~4,5 min (254 s) | ~9 min |
| 7 | `safe_base 35760084 --scenari rapidi --trasporto entrambi` | ~2 min | ~4 min |
| 8 | `scalper_calcio 35797769 --scenari tutti` (BLOCCATO da T0C-R2) | da misurare dopo il cantiere 11 (base 76 s x 47 scenari / 3 worker ~ 20 min) | ~45 min |
| 9 | `scalper_calcio 35797769 --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper` (BLOCCATO da T0C-R2) | ~4 min | ~9 min |
| 10 | `tennis_pro 35790089 --scenari tutti --data-dir <tennis_rec>/20260707` (PC) | 19 s | <1 min |
| 11 | `tennis_flb 35794049 ...` (i 6 replay del referto `tennis_flb_35794049_TETTO.txt`), `safe_tennis 35795993 --scenari tutti`, `tennis_scalper 35790089 --scenari tutti`, `tennis_swing 35790089 --scenari tutti` (PC) | <1 min ciascuno | |
| 12 | Mike: le 5 sintetiche (`Betfair/mike/tools/synth_mike.py`) e le registrazioni COMPLETE aggiuntive di T0B 5 (U-27) | ~1 min a partita x scenario | |

Prima del #3-#5: il finto di Omega corretto (T0B 4). Prima del #8-#9: decisione su T0C-R2. Prima di tutto: T0C-R3/R4
(dove si congela e come si calcola l'hash delle `.timeline.jsonl`). Infine: impronte rigenerate sul commit di
congelamento (`impronta_strategia_bot.py scrivi tutti`, `e1_impronta_strategia.py scrivi`) e messe nel manifesto; tag del
commit di congelamento.

## 11. Come rifare tutto (dalla radice; il cloud non ha `.venv`, si usa `python`)

```
python - <<'PY'   # scompatta registrazioni_banco/ in _live_raw/ (registrazioni_banco/LEGGIMI.md)
...
PY
python -m pytest Betfair/stream/tests/test_banco_cassetta_ombra_t0c_2026_10_09.py -q -p no:cacheprovider
python ARCHITETTURA_2026-10/tappa0/T0C_STRUMENTI/falsifica_test_t0c.py                       # ~2 min
python ARCHITETTURA_2026-10/tappa0/T0C_STRUMENTI/prova_innocuita.py SENZA.txt CON.txt
python ARCHITETTURA_2026-10/tappa0/T0C_STRUMENTI/falsifica_ombra.py tutte --riferimento CAS.jsonl --uscite DIR   # ~8 min
python -I ARCHITETTURA_2026-10/strumenti/impronte/impronta_strategia_bot.py confronta tutti
python -I ARCHITETTURA_2026-10/strumenti/impronte/falsifica_impronte.py
python -I ARCHITETTURA_2026-10/strumenti/e1/e1_impronta_strategia.py confronta
```
