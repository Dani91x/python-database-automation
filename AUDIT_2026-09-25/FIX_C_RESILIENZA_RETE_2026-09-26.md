# FIX-C — Resilienza alla caduta di rete (servizi della sessione B) — 26/09/2026

Referto del delegato Opus della sessione B (coordinatore admin-9d). Lavoro fatto nel worktree
`agent-a51e920771fb3756f`: sviluppato su `498ba07`, poi **riallineato con fast-forward su
`origin/master` `3df556e`** (contiene 78d9f65 di admin-26, valuta K1). Le mie modifiche
sono state riapplicate con `git apply --3way` senza conflitti, e l'indice è stato ripulito.
Le righe `valuta` di admin-26 in `service.py`/`stream.py` restano. Patch contro master 1760ef7:
`AUDIT_2026-09-25/fix_c.patch`. **Non ho fatto commit.** Non ho scritto sul DB
vero, non ho riavviato l'app e non ho toccato `desktop/main.js`, `runner.py` né
`tennis_runner.py`.
Brief: `brief_fix_C_resilienza.md`. Requisito dell'utente: dopo una caduta di rete ogni
componente deve tornare a funzionare da solo.

## 0. Esito in una riga

**Causa del «mai più rientrato» del 26/09: la sessione Betfair del feed unico è scaduta e
nessuno l'ha rifatta.** Il keepAlive dello scanner cadeva ogni 900 s. Quello delle 10:42Z è
caduto durante l'interruzione di rete ed è stato segnato come «fatto»: il tentativo successivo
sarebbe arrivato solo 900 s dopo. Nel frattempo la sessione .it, che dura 20 minuti, è
scaduta: da quel momento ogni keepAlive riceve `NO_SESSION` per sempre e non esiste un
re-login. REST e stream sono rimasti senza sessione per 4 ore. Adesso c'è un «custode della
sessione» con ritentativi e login, in scanner e sessioni scalper. In più ho sistemato nove
punti di ripresa nei servizi e ho scritto la specifica del watchdog. Tutto è testato
RED→GREEN, con falsificazione e ripristino byte-identico.

## 1. Perché lo scanner non è rientrato (evidenze + file:riga del codice di prima)

Evidenze, lette in sola lettura dalle registrazioni della fase 2
(`AUDIT_2026-09-25/e2e_fase2/canali_ordini/scanner_*.jsonl`, script
`AUDIT_2026-09-25/fix_c/stato_scan.py`):

| ora (Z) | source | stream_markets | shard[0] | last_error |
|---|---|---|---|---|
| 10:15:40 | stream | 48 | subscribed 48, eta_resub_s 14.9 | — |
| 10:56:19 | rest | 0 | **subscribed 0**, eta_msg/eta_book null, **eta_resub_s 978.8** (ultimo subscribe 10:40:00Z) | quote assenti da 893s su 28 mercati |
| 14:39:08 | rest | 0 | subscribed 0, **eta_resub_s 14348** | **quote assenti da 14262s su 32 mercati** |

Le evidenze dicono tre cose.
- Lo shard non ha mai più completato un subscribe (`_subscribed` vuoto, `_last_resub`
  fermo alle 10:40Z), anche se il thread di riconnessione ritentava ogni 30 s
  (`stream.py:_run` di prima, righe 329-373).
- Neanche il REST ha più consegnato un prezzo: «quote assenti» vale **per qualunque fonte**
  (`price_mono`). `rest_books_vuoti` resta fermo a 930 dalle 10:13Z, quindi le chiamate REST
  fallivano e non restituivano book vuoti. Stream e REST morti insieme, con la rete
  tornata già alle ~10:48Z, indicano una causa comune: **la sessione**.
- Codice di prima:
  - `Betfair/safe_strategy/service.py:1913-1915`: `if now_mono - self.keepalive_ts > 900:
    keep_alive(self.client); self.keepalive_ts = now_mono`. **Il timestamp avanza anche se
    il keepAlive fallisce.**
  - `Betfair/stream/auth.py:81-88`: `keep_alive` ingoia l'eccezione e registra un WARNING.
    **Nessun re-login da nessuna parte nello scanner** (`build_client(login=True)` solo in
    `main`).
  - `betfairlightweight/baseclient.py:53`: `SESSION_TIMEOUT italy = 20*60`. Le chiamate API
    non prolungano la sessione: lo nota già il codice del repo
    (`scalper_session.py`, commento del 16/07, «le chiamate API NON lo estendono»).
  - Tempi: scanner avviato alle 08:56:57Z, keepAlive a ogni tick oltre i 900 s, cioè circa
    09:12, 09:27, 09:42, 09:57, 10:12, 10:27, **10:42** (proprio dentro la caduta
    10:41:41Z, con DNS KO fino alle ~10:48Z). Ultimo keepAlive riuscito ~10:27, sessione
    scaduta ~10:47, prossimo tentativo ~10:57 con `NO_SESSION`. Da lì: REST
    `INVALID_SESSION_INFORMATION` e autenticazione dello stream rifiutata (ListenerError), a
    ogni giro, fino al riavvio.
- **Non verificato sul log**: la console dell'app non è su file (R-F2-C3), quindi il
  `keep_alive fallito: APIError` delle 10:42Z e i `NO_SESSION` successivi non si possono
  leggere. Gli orari dei keepAlive sono ricostruiti dal codice e dallo `started_at`. La
  prova d'insieme (sez. 5) riproduce la catena.

**Probabile causa comune anche per il runner calcio e il tennis (NON mio, per admin-26).**
Il worker keep-alive di flumine (`flumine/worker.py:99-116`) non arriva mai a `login()` se il
keepAlive fallisce. `BetfairClient.keep_alive` (`flumine/clients/betfairclient.py:41-50`)
restituisce `None` su `BetfairError`, e `resp.status` su `None` solleva un AttributeError,
ingoiato dal BackgroundWorker. Anche `runner.py:1180` usa `auth.keep_alive`, che non rifà il
login. Il custode (sez. 2) è riusabile così com'è: `CustodeSessione(trading,
periodo_s=600).tick()` nel loop del runner.

## 2. Correzioni (causa → file → test → falsificazione; righe «di prima» su 498ba07)

Diff completo contro `origin/master` `1760ef7`: `AUDIT_2026-09-25/fix_c.patch`. La versione
contro `498ba07` è in `fix_c/fix_c_su_498ba07.patch`. Falsificazione:
`AUDIT_2026-09-25/fix_c/falsifica_fix_c.py`; esito in `falsifica_esito.txt`, sez. 4.

| # | componente | difetto (codice di prima) | correzione | test |
|---|---|---|---|---|
| C1 | **custode della sessione** (utility condivisa, nuova) | nessun ritentativo né re-login su keepAlive fallito (`auth.py:81-88`) | `Betfair/stream/auth.py`: `CustodeSessione` + `e_errore_di_sessione`. A regime **una keepAlive per periodo, nessuna chiamata in più**. Dopo un KO ritenta a 15/30/60/60… s. Rifà il login se Betfair dice `NO_SESSION`/`INVALID_SESSION_INFORMATION` o se si è oltre il 90% della vita della sessione. Non solleva mai. Lo stato non contiene mai il token. `keep_alive` storico INVARIATO (lo usano i runner) | `test_resilienza_rete_fix_c_2026_09_26.py` (custode) |
| C2 | **scanner: sessione** | `service.py:1913-1915` (sopra) | `Scanner.sessione = CustodeSessione(..., periodo_s=900)`, `tick()` a ogni giro. Gli errori di sessione di catalogo e poll REST anticipano il rinnovo (`segnala_errore`) | idem: rete giù a cavallo del keepAlive → sessione valida; sessione già scaduta → login; a regime 11-12 keepAlive in 3 h e 0 login; backoff 3-15 tentativi in 600 s di rete giù |
| C3 | **scanner: il cambio di fonte si DICE** | il ripiego REST era visibile solo nel campo `source` | `SorvegliaFonte` (pura). **Un** avviso `FEED_RIPIEGO_REST` (WARN) se `rest` per ≥30 s di fila, **un** `FEED_RIENTRO_STREAM` (INFO) dopo ≥10 s di stream. Nessun avviso per uno scatto breve (caso delle 09:21Z). Un nuovo ripiego entro 300 s va solo nello stato. Gli avvisi aspettano in coda e si scrivono dal thread dello stato: se la rete è giù restano in coda e partono al rientro, una volta. `scanner_stato` guadagna `fonte` {attuale, da_s, in_ripiego, motivo, ripieghi, ultimo_cambio}, `sessione` (stato del custode) e `avvisi_in_attesa`: chiavi **additive**, nessuna rimossa | idem: 4 test (sequenza, scatto breve, integrazione `tick`+`publish_status`, avviso a rete giù ritentato) |
| C4 | **scanner: stream** | il rientro c'era già (backoff 2/5/10/30 s, `stream.py:51,371-373`), ma lo stato non diceva perché falliva | `StreamShard.stato()` + `riconnessioni`, `ultimo_errore` (tipo + codice Betfair, per esempio `ListenerError: NO_SESSION`, `gaierror: getaddrinfo failed`), azzerato al subscribe riuscito | shard vero su un thread con stream finto: SocketError → gaierror → NO_SESSION → login → risottoscritto col token NUOVO |
| C5 | **Safe bot: loop** | `bot_service.py:9765` (prima): `_real_db.read_control()` nel loop, fuori dal ramo degradato di `run_once`. Con Supabase giù il giro saltava intero e la PROTEZIONE (riconciliazione, uscite, settlement con l'ultimo control noto, niente ingressi) non partiva mai | `_control_per_il_giro(db)`: lettura KO con un control noto → si prosegue (e `run_once` degrada da sola); senza nulla in memoria l'errore sale come prima | `test_resilienza_rete_fix_c_insieme_2026_09_26.py` (3 test + prova d'insieme) |
| C6 | **Safe bot: riconciliazione tennis** | `bot_service.py:80-85`: il filtro degli ordini di Safe teneva solo `safe-`. Dal 25/09 il tennis scrive `safe_tennis-t<id>` (`porta_ordini.py:178-190`): **un place REST tennis a esito ignoto (timeout, rete giù) non trovava il suo ordine vero** e finiva `reconcile_ordine_assente` | `_SAFE_PREFISSI_ORDINE = ("safe-", "safe_tennis-")` | `test_riconciliazione_vede_gli_ordini_tennis_di_safe` |
| C7 | **Omega: keepAlive** | `omega_service.py:7698` (prima): `_maybe_keepalive` restituiva `now_ts` anche su KO, quindi ritentava dopo 600 s | su KO restituisce `now_ts - 600 + 60`: ritenta fra 60 s. A regime invariato | `Betfair/omega/test_omega_flumine_live.py::test_keepalive_ko_non_ferma_il_loop`: **asserzione esistente cambiata**. Prima pretendeva `last == 5.0` («timestamp avanzato»), cioè codificava il difetto. Ora pretende il ritentativo a 60 s e non prima |
| C8 | **sessione scalper (LIVE)** | `scalper_session.py:1069-1075` (prima): `wait(600)` + `auth.keep_alive`, nessun ritentativo né login. Il worker di flumine non rifà il login (sez. 1) | `mantieni_sessione(trading, stop_flag)`: custode a 600 s, passo 5 s. Relogin sullo stesso `trading`, quindi anche place, cancel, force-flat e la riconnessione degli stream di flumine (che rileggono il token dal client) ripartono | `Betfair/stream/tests/test_resilienza_rete_fix_c_scalper_2026_09_26.py` (3 test) |
| C9 | **scalper-service: avvio** | `scalper_service.py:239-243` (prima): con la lettura KO all'avvio `ferma_sessioni_al_nuovo_avvio` restituiva `[]` = «fatto». Tornata la rete, le righe `requested` di un avvio precedente diventavano sessioni: viola «all'avvio nessun bot opera» | `controllo_avvio()` → `None` se non concluso. Il loop lo ritenta a ogni giro e **non spawna niente** finché non riesce. `ferma_sessioni_al_nuovo_avvio` resta con la firma di prima (i test esistenti passano) | idem |
| C10 | **scalper-service: false orfane** | `scalper_service.py:765-780` (prima): dopo un riavvio del supervisore (`children` vuoto) una sessione VIVA con il battito invecchiato dalla caduta di rete veniva messa in `error`, quindi force-flat e stop | `orfane_giudicabili(db_sano_dal, adesso)`: orfane/zombie solo dopo 60 s consecutivi di DB leggibile (i battiti tornano ogni 5 s) | idem (funzione pura + cablaggio del loop verificato sul sorgente) |

Cosa NON ho cambiato perché era già corretto (verificato nel codice, inventario sez. 3):
rientro dei lettori dei canali locali (`canale_scan.ClientScan`, backoff 0,5-5 s, fonte
dichiarata in `stats.fonte_scan` / `statistiche_canale_scan`); cicli principali di Omega,
Mike, Safe, ponte e supervisore scalper (try per giro, il processo non muore);
ri-login reattivo di `omega_market.call`/`call_mutating`, per cui il primo ordine dopo il
rientro con sessione scaduta rifà il login e parte **una volta** (provato nella sez. 5);
idempotenza delle scritture d'ordine (riserva su indice unico, coda runner su `client_ref`
con `ON CONFLICT DO NOTHING`, `customerOrderRef` deterministico).

## 3. Inventario per servizio (sintesi; il dettaglio con file:riga è nei tre referti di inventario, riportato qui)

| servizio | ciclo (rete giù) | client Supabase | sessione Betfair | canali locali | freschezza | ripresa |
|---|---|---|---|---|---|---|
| **scanner** | `tick` in try, non muore | nessun retry; scrive stato dal thread punteggi | **C2** | server 47336 | fonte + età in stato; **C3** | watchdog; `pre_ko` reidratato dal DB |
| **Omega** | try per giro (`omega_service.py:7941-7984`); `run_once` salta se `read_control` fallisce (7260), le fasi interne hanno ognuna il proprio try | `db_client.py:17-23` per thread, senza retry, timeout PostgREST 120 s (default libreria) | `omega_market` condiviso, keepAlive = `listEventTypes` ogni 600 s (**C7**), re-login reattivo | lettore 47336 (spento di serie) con fonte dichiarata | `fresh_payload` + `scanner_age_sec` | lock 47313; `reconcile_pending` per `customerOrderRef` |
| **Mike** | try per giro; `read_control` protetto (2708) | come sopra | nessun client proprio: `omega_market` reattivo | lettore 47336 (spento di serie) | `feed_fresh` 45/180/75 s | `_reconcile_trades` / `_reconcile_unknown` |
| **Safe bot** | try per giro; **C5** | come sopra | `omega_market` reattivo; nessun keepAlive nel processo | lettore 47336 (spento di serie), porta 47331/47332 (spenta di serie) | `feed_is_fresh` 20/45/120 s | riserva su indice unico; **C6** |
| **ponte tennis** | 3 try per giro (`tennis_bot_service.py:892-913`) | `_exec_retry` solo sugli upsert (~0,45 s) | nessuna | inoltro 47332 con backoff | battito scanner ≤30 s (fail-closed) | guardia `APP_BOOT_ID` (862-890); **niente watchdog** → spec |
| **scalper-service** | try unico per giro (733-783) | nessun retry; `sb` condiviso tra thread | habitat: login solo dopo 1800 s | server 47338 | — | **C9, C10**; **niente watchdog** → spec |
| **sessioni scalper** | battito protetto | come sopra | **C8** | — | — | flumine `@retry` sugli stream |

## 4. Falsificazione (mutazione → ROSSO, ripristino byte-identico)

`AUDIT_2026-09-25/fix_c/falsifica_fix_c.py` → `fix_c/falsifica_esito.txt`, eseguito sulla
base `498ba07` prima del riallineamento. **15 mutazioni su 15 danno ROSSO e tutte tornano
byte-identiche** (SHA-256):

| id | mutazione (rimette il difetto) | test che diventa rosso |
|---|---|---|
| M1 | scanner: vecchio keepAlive (fatto anche se fallito, nessun login) | sessione_resta_viva / già_scaduta / insieme |
| M2 | custode: dopo un KO si aspetta un periodo intero | sessione_resta_viva (secondi «ciechi» a rete su) + scalper |
| M3 | custode: NO_SESSION non porta al login | no_session_dal_server_rifa_il_login |
| M4 | custode: login a ogni periodo (chiamate in più a regime) | a_regime_nessuna_chiamata_in_più / scalper 600 s |
| M5 | fonte: avviso anche per uno scatto breve | non_avvisa_per_uno_scatto_breve |
| M6 | avviso non scritto a rete giù perso | avviso_non_scritto_si_ritenta |
| M7 | tick: la fonte non è osservata | tick_e_stato / insieme |
| M8 | shard: ultimo errore non azzerato al rientro | shard_rientra |
| M9 | Safe: il loop salta il giro a DB giù | control_del_giro_usa_l_ultimo_noto |
| M10 | Omega: keepAlive KO rinviato di 600 s | test_keepalive_ko_non_ferma_il_loop |
| M11 | scalper-svc: orfane giudicate subito | orfane_giudicabili |
| M12 | scalper-svc: controllo d'avvio KO = fatto | controllo_avvio_ko_non_vale_fatto |
| M13 | sessione scalper: vecchio keep-alive | sopravvive_alla_rete_giu / scaduta_rifa_il_login |
| M14 | Safe: riconciliazione cieca agli ordini tennis | vede_gli_ordini_tennis |
| M15 | fonte: falso ripiego a ogni avvio | avvio_non_e_un_ripiego |

Il primo giro di falsificazione aveva trovato **VERDI** M2 e M3: i test guardavano solo lo
stato finale della sessione, e la regola del 90% rifaceva comunque il login. Li ho
rafforzati: ora misurano i secondi a rete su con la sessione scaduta e il login nello
stesso giro su un `NO_SESSION` del server. Dopo il rinforzo sono rossi.

**RED sul codice di prima** (`fix_c/rosso_su_codice_di_prima.txt`, sorgenti riportati a
HEAD e poi ripristinati byte-identici): 11 falliti su 12, 5 su 5 e 6 su 6. L'unico verde sul
vecchio è la cintura «nessuna chiamata in più a regime», verde per costruzione (la sua
falsificazione è M4).

## 5. Prova d'insieme «rete giù 60 s, poi su» (finti, nessuna rete)

`Betfair/safe_strategy/tests/test_resilienza_rete_fix_c_insieme_2026_09_26.py::test_rete_giu_60s_poi_su_tutto_torna_da_solo`
fa girare 600 s simulati, un passo al secondo, con rete giù da 120 a 180 s:
- **scanner vero** (`Scanner.tick` + `publish_status`): pool stream finto che smette di
  consegnare a rete giù e torna 5 s dopo il rientro. Client .it finto con vita della
  sessione ridotta a 200 s e keepAlive dovuto a t=150 (dentro la caduta). DB e
  `live_alerts` finti che falliscono a rete giù;
- **loop del bot Safe** (`_control_per_il_giro`) ogni 2 s, con Supabase giù;
- **primo ordine LIVE REST dopo il rientro** (`omega_market.place_order_live` →
  `call_mutating`, il percorso comune a Omega, Mike e Safe) a t=300, contro un exchange finto
  con la sessione di Omega scaduta (errore con il testo esatto di `BetfairClient._rpc`,
  `INVALID_SESSION_INFORMATION`).

Verifiche, tutte verdi:
- nessuna eccezione non gestita;
- avvisi = esattamente `["FEED_RIPIEGO_REST", "FEED_RIENTRO_STREAM"]`. L'avviso di ripiego
  nasce a rete giù, resta in coda e parte al rientro, una volta;
- fonte tornata a `stream`, sia nello scanner sia nell'ultimo stato scritto;
- sessione del feed valida (senza C2 sarebbe scaduta a t=200) e `fallimenti == 0`;
- bot Safe: 300 giri su 300 con un control. A DB giù usa l'ultimo noto e non salta;
- exchange: **un solo ordine**, ref `omega-t4242`, esito ok, login rifatto una volta
  (2 login in tutto).

## 6. Numeri delle suite (un pytest alla volta, solo i file che toccano i moduli modificati)

**Dopo il riallineamento su master 3df556e** (`fix_c/suite_*.txt`, l'ultimo):
test FIX-C 13, 5 e 6 passati; `test_paper_fill_al_best_2026_09_26` 7 passati;
`test_valuta_k1_2026_09_26` 22 passati (compresi i 4 test Safe e scanner lanciati da
soli); `test_incidente_quote_2026_09_17` 50; `test_canale_scanner_al_ms_2026_09_18` 51;
`test_banco_comune` 20 passati e 10 saltati; `test_avvio_app` 22; `test_theta_bot` 42;
`test_scalper_freno_origine` 21; `test_scalper_certificazione` 37; `test_bot_service` 189.
**`Betfair/omega/test_omega_flumine_live.py`: 19 falliti e 27 passati, GIÀ SUL CODICE DI
PRIMA.** Li ho verificati con `fix_c/base_vs_fix.py`, riportando `omega_service.py` e il
test a HEAD 498ba07: stessi 19 falliti. Non dipendono da me. Il test che ho cambiato
(`test_keepalive_ko_non_ferma_il_loop`) passa.
Prima del riallineamento, sulla base 498ba07, erano verdi anche `test_canale_scan_f4` (42),
`test_cert_2026_09_13` (68), `test_pre_ko_ou` (8), `test_safe_d5` (110), `test_safe_q7_q12`
(36), `test_scanner` (50), `test_scanner_mike_followed_c1` (6), `test_selezione_esatto`
(23), `test_tennis_auto_mode` (68), `test_punteggi_canale` (31), `test_scalper_auto_mode`
(70), `test_scalper_live_cli_guardia` (10), `test_r3_freno_unico` (25),
`test_contratto_strada_unica` (24), `test_cert_banco` (6 passati e 6 saltati),
`test_stato_mercato_freno` (36), `test_scalper_uscite_automatiche` (13),
`test_scalper_session_gates` (14), `test_scalper_mission` (18), `test_scalper_control_room`
(9), `test_scalper_audit` (20) e `test_registro_bot` (19). Non li ho rilanciati dopo il
riallineamento per stare nei tempi.

## 7. Cosa NON ho corretto (reperti aperti, in ordine di gravità) e cosa NON ho potuto verificare

1. **I bot non sanno che le quote sono ferme se la riga è fresca.** Fatto del 26/09: dalle
   10:42 alle 14:47Z le righe di `safe_strategy_scan` potevano essere riscritte per i cambi
   di punteggio (IPS vivo, `updated_at` fresco) con quote vecchie di ore. `odds_ts_ms` è
   l'istante dell'ultimo CAMBIO, non l'ultimo dato ricevuto. I veti dei bot guardano l'età
   della riga e il battito dello scanner (Safe `feed_is_fresh`, Omega `fresh_payload` +
   `scanner_age_sec`, Mike `feed_fresh`), non `source` né `stream_mercati_allarme`: nessun
   bot usa questi due campi (inventario). Con C2 la causa del 26/09 non si ripete, e C3
   mette il ripiego nei banner, ma il veto manca. Proposta, da decidere col coordinatore
   perché tocca il cancello decisionale di tre bot: lo scanner pubblica per riga
   `quote_ferme` (MO nel suo `mercati_allarme`, fuori dalla firma di scrittura per non
   moltiplicare l'IO) e i tre bot non aprono né chiudono a mercato su una riga
   `quote_ferme`. **Non implementato.**
2. **Omega paper, riserva con risposta persa** (`omega_service.py:3841-3879`): se l'insert
   della riserva va a buon fine sul server ma la risposta si perde (timeout), in paper
   `reconcile_pending` conferma la riga orfana come fill inventato. Non si distingue da
   «crash dopo la simulazione» senza un segno scritto dalla simulazione: serve una
   decisione. **Non corretto.**
3. **Mike, riserva con risposta persa** (`mike/service.py:716-720, 1278-1285, 4026,
   4043-4044`): la riga `pending` resta per sempre e blocca per fail-closed
   (`_gia_appoggiata` 1130-1146) la copertura o il green-up dello stesso ruolo e ciclo.
   **Non corretto** (logica d'ordine di Mike).
4. **Timeout PostgREST 120 s** (`db_client.py:21`, default della libreria): con la rete «a
   buco nero» (non DNS KO) un giro può restare appeso minuti. `db_client.py` è condiviso
   con i runner: da decidere insieme ad admin-26. **Non toccato.**
5. **Safe paper doppio** (`execution.py:1143-1151`): se l'accodamento va in errore e anche
   la ricerca per ref fallisce, in paper parte anche il fill legacy. **Non corretto.**
6. **Omega**: `run_once` salta il giro se `read_control` fallisce (`omega_service.py:7260`).
   Non esiste un ramo degradato progettato come in Safe: inventarlo è una scelta di
   condotta. Il keepAlive è `listEventTypes`, che non prolunga una sessione .it: il ri-login
   è reattivo, e la prima chiamata dopo la scadenza paga fino a ~14 s di ritentativi di
   `_rpc`. **Non cambiato** (C7 corregge solo i tempi).
7. **Watchdog**: vedi `SPEC_WATCHDOG_SCALPER_PONTE_2026-09-26.md`, aggiornata su master
   3df556e. Mancano ancora le due righe di `main.js` (369, 375) e il battito del watchdog
   condiviso. Log su file e nome del modulo nel crash sono già su master. Tutto di
   admin-26.
8. **`net_retry.is_transient`** non riconosce un `socket.gaierror` nudo (serve che sia
   avvolto in httpx/requests). Oggi non conta, perché nessuno dei servizi B lo usa.

**NON verificato da me:**
- una caduta di rete REALE: tutto è su finti. Il login vero con certificato e il keepAlive
  vero dopo `NO_SESSION` non sono stati eseguiti (vietato chiamare Betfair a vuoto);
- i log della console del 26/09 (non esistono su file): la catena delle 10:42Z è
  ricostruita da stato, codice e tempi;
- la frase di Betfair «le chiamate API non prolungano la sessione» sul .it: la prendo dalla
  nota del repo del 16/07 e da `SESSION_TIMEOUT` di betfairlightweight, non l'ho misurata;
- il comportamento del frontend con le chiavi nuove di `scanner_stato` (`fonte`,
  `sessione`, `avvisi_in_attesa`, `stream_shards[].riconnessioni/ultimo_errore`): sono
  additive, e nessuna pagina le legge ancora;
- il banner di `live_alerts` con i codici nuovi `FEED_RIPIEGO_REST` / `FEED_RIENTRO_STREAM`
  (livelli WARN/INFO ammessi dal CHECK di `migrations/live_alerts.sql`).

## 8. File toccati (elenco esatto)

Codice:
- `Betfair/stream/auth.py` (aggiunti `CustodeSessione`, `e_errore_di_sessione`,
  `_descrivi_errore`; `keep_alive` e `build_client` invariati)
- `Betfair/safe_strategy/service.py` (scanner: custode, `SorvegliaFonte`, `_scrivi_avviso`,
  coda avvisi, `_scarica_avvisi`, campi di stato)
- `Betfair/safe_strategy/stream.py` (`_descrivi_errore_stream`, `riconnessioni`,
  `ultimo_errore`)
- `Betfair/safe_strategy/bot_service.py` (`_control_per_il_giro`, `_SAFE_PREFISSI_ORDINE`)
- `Betfair/omega/omega_service.py` (`KEEPALIVE_RITENTO_S`, `_maybe_keepalive`)
- `Betfair/stream/scalper/scalper_session.py` (`mantieni_sessione`)
- `Betfair/stream/scalper/scalper_service.py` (`controllo_avvio`, `orfane_giudicabili`,
  cablaggio nel `main`)

Test:
- `Betfair/safe_strategy/tests/test_resilienza_rete_fix_c_2026_09_26.py` (nuovo, 13 test)
- `Betfair/safe_strategy/tests/test_resilienza_rete_fix_c_insieme_2026_09_26.py` (nuovo, 5 test)
- `Betfair/stream/tests/test_resilienza_rete_fix_c_scalper_2026_09_26.py` (nuovo, 6 test)
- `Betfair/omega/test_omega_flumine_live.py` (un'asserzione cambiata, vedi C7)

Documenti e strumenti:
- `AUDIT_2026-09-25/FIX_C_RESILIENZA_RETE_2026-09-26.md` (questo)
- `AUDIT_2026-09-25/SPEC_WATCHDOG_SCALPER_PONTE_2026-09-26.md`
- `AUDIT_2026-09-25/fix_c.patch` (diff contro `origin/master` 1760ef7, file nuovi inclusi)
- `AUDIT_2026-09-25/fix_c/`: `falsifica_fix_c.py`, `falsifica_esito.txt`,
  `rosso_su_codice_di_prima.txt`, `base_vs_fix.py`, `stato_scan.py`, `pt.ps1`,
  `suite_scanner.ps1`, `suite_*.txt`, `fix_c_su_498ba07.patch`. Da NON committare:
  `orig_*.py` e `prima_del_riallineamento/` (copie di lavoro)
