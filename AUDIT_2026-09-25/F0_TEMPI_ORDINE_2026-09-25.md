# F0 "misura": i 5 tempi del percorso di un ordine (25/09/2026)

Piano strada unica, AUDIT_STRADE_ORDINE_2026-09-24.md par. 5, riga F0. Specifica dei
cinque tempi: ESECUZIONE_LIVE.md par. 4 ("decisione -> scrittura in coda -> claim del
worker -> risposta di Betfair -> fill. Cinque numeri").

Delegato Opus (sessione B), worktree `agent-a18e303bacfa12e8f`, base `origin/master`
39d9402 (contiene 5139d2b, strada unica). Niente commit.

## 0. In breve

- Modulo nuovo `Betfair/stream/tempi_ordine.py`: tiene in RAM gli istanti di ogni ordine
  e scrive UNA riga di log per ordine. Niente DB, niente Betfair, niente processi.
- 66 righe aggiunte in 4 file di produzione (agganci, interruttore, commenti). Sono SOLO aggiunte (il diff non ha
  righe tolte o spostate). Nessuna guardia, logica, ordine delle operazioni o IO
  cambiato.
- Interruttore `LIVE_TEMPI_ORDINE`: acceso di serie; con `0` i worker non chiamano
  nemmeno il modulo.
- Script di lettura `Betfair/stream/tools/leggi_tempi_ordine.py`: p50, p95 e massimo
  per strada e per tratto.
- Test: 13 nuovi. Sui 19 file di test dei moduli toccati: 846 verdi prima, 859 dopo
  (846 + 13), con l'interruttore acceso e spento.
- Falsificazione: 18 mutazioni su 18 danno rosso. Il diff torna identico dopo ognuna.
- NON VERIFICATO: nessuna misura dal vivo. La misura vera si prende al prossimo avvio
  dell'app in PAPER (par. 6).

## 1. La riga di log

```
tempi_ordine ref=awlq12 strada=coda via=coda azione=place mode=paper ordine=<id flumine>
  decisione_ms=na ricezione_ms=812 presa_ms=143 place_ms=2 risposta_ms=35
  abbinato_ms=1200 interno_ms=145 risposta_bf_ms=2110 abbinato_fonte=betfair
  orologi=ricezione:db/pc,risposta_bf:pc/betfair esito=abbinato rif=<client_ref o ref>
```

Il logger e' `Betfair.stream.tempi_ordine`, livello INFO. Quando l'istante manca il
campo vale `na`.

Chiavi:
- `ref`: il ref interno della richiesta (`awlq<rid>` nel calcio, `awtq<rid>` nel
  tennis).
- `rif`: il riferimento dell'attore (`client_ref` della riga o del desktop, oppure
  `ref` del `/comando`).
- `strada`: `coda`, `canale`, `comando` o `tennis`. Per il tennis, `via` vale
  `canale` o `coda`.

### 1.1 I tratti

Tutti i tratti sono in ms.

| campo | da -> a | orologio | note |
|---|---|---|---|
| `decisione_ms` | decisione -> invio (scrittura in coda o arrivo sul canale) | vedi par. 3 | serve che il comando porti l'istante della decisione |
| `ricezione_ms` | invio -> il worker legge la riga o il comando | coda: DB contro PC (MISTO); comando: PC | |
| `presa_ms` | lettura -> inizio `_dispatch` | monotonic | coda: claim e IO delle righe prima nel giro; motore: validazione, diario (fsync), ack |
| `place_ms` | inizio `_dispatch` -> subito prima di `market.place_order` | monotonic | `build_order`, guardie, diario write-ahead |
| `risposta_ms` | `place_order` -> risposta di placeOrders registrata da flumine | PC contro PC | `order.responses._date_time_placed` |
| `abbinato_ms` | risposta -> primo abbinamento | Betfair contro Betfair (`matchedDate - placedDate`) se ci sono; altrimenti prima osservazione locale (`abbinato_fonte=osservato`) | |
| `interno_ms` | lettura -> `place_order` | monotonic | il numero piu' affidabile; l'audit fissa l'obiettivo p95 < 10 ms (par. 4.2) |
| `risposta_bf_ms` | `place_order` (PC) -> `placedDate` di Betfair | MISTO | porta l'errore dell'orologio del PC |

I tratti `ricezione_ms` e `presa_ms` portano anche l'attesa del giro. Il tratto
`abbinato_ms` e' la vita dell'ordine a mercato, non una latenza nostra.

### 1.2 Esito ed emissione

- Con un ordine, la riga si scrive:
  - al primo abbinamento (`esito=abbinato`);
  - a stato terminale senza abbinamento (`esito=execution_complete`, `lapsed`,
    `violation`, ...).
- Senza ordini la riga si scrive a fine dispatch (`esito=ok` o `esito=errore`). E' il
  caso di un cancel, di un rifiuto prima del place, di un mercato non sottoscritto.
- La cache ha un TTL di 10 minuti e un tetto di 2000 voci. Ogni voce che esce dalla
  cache scrive comunque la sua riga (`esito=scaduto` o `esito=tetto`).
- Il log si scrive fuori dal lucchetto del modulo.

### 1.3 Orologi

- Gli intervalli dentro il processo usano `time.monotonic()`.
- Quando un tratto confronta orologi diversi, lo si elenca in `orologi=`.
- L'orologio del PC era indietro di circa 2,07 s il 17/09: il servizio Ora di Windows
  era spento (`Betfair/safe_strategy/LATENZA_TENNIS_2026-09-17.md` riga 31). I tratti
  misti hanno quindi un errore sistematico di quell'ordine.
- Lo script li conta a parte (colonna `misti`).
- Sincronizzare l'orologio toglie l'errore di misura, non la latenza.

## 2. Punti di aggancio (file:riga, versione del worktree)

Ogni aggancio e' una riga (o una sola istruzione su piu' righe) preceduta dal
controllo dell'interruttore:
- `_tempi_on()` in `live_order_worker.py:56`;
- una copia identica in `engine/live_trading_strategy.py:40` e
  `tennis_live/tennis_live_order_worker.py:38`.

| istante | coda calcio | canale 47331 | motore `/comando` | tennis (47332 + coda) |
|---|---|---|---|---|
| ricezione | `live_order_worker.py:3611` (dopo la lettura delle pending) + `nuovo` a `:3655` dopo il claim | `live_order_worker.py:3314` (richieste drenate) + `nuovo` a `:3378` (dopo il diario `inviato`) | `motore_ordini.py:717` (inizio `_gestisci`) + `nuovo` a `:780` (dopo ack e diario) | canale `tennis_live_order_worker.py:1220` + `:1254`; coda `:1379` + `:1415` dopo il claim |
| presa | `live_order_worker.py:3441` (inizio `_dispatch`, comune a coda, canale e motore) | idem | idem | `tennis_live_order_worker.py:827` (inizio `_dispatch`) |
| place | `live_order_worker.py:1204` in `_place_or_raise`, dopo il diario write-ahead e subito prima di `market.place_order`. Copre place, gambe di green-up/dutch/cash-out. Place-and-trim: `:2787` e `:2791` (istante preso prima di `base.place`) | idem | idem | `:546` (`_do_place`), `:805` (`_do_greenup`) |
| fine dispatch | `:3671` (errore), `:3673` (ok) | `:3391` (errore), `:3404` (ok, dopo la risposta al desktop) | `motore_ordini.py:957` | canale `:1268`; coda `:1424`, `:1434` |
| risposta / abbinamento | `engine/live_trading_strategy.py:184` (`process_orders`, prima dello specchio) | idem | idem | `tennis_live_order_worker.py:893` (`_reconcile_tracked`) |

`process_orders` gira sul thread principale di flumine. Per ogni ordine l'aggancio
costa un lookup in un dict, e ritorna subito se non ci sono ordini misurati.

## 3. Cosa manca per la DECISIONE

| strada | chi la usa | istante della decisione | stato |
|---|---|---|---|
| coda DB | Omega, Safe (`_flumine_enqueue_place` / `enqueue_place`), risk_engine, desktop senza canale | nessuno | MANCA. `params = {source, trade_id}` (omega_service.py:3138/3211, safe_strategy/execution.py:1049). Il modulo legge `params.decisione_ms`, `emesso_ms`, `creato_ms`, `decided_at_ms`, `decided_at` e `decisione_at` se un giorno ci saranno. La proposta di Omega ha `decided_at` (omega_proposte.py), ma non arriva nella riga di coda. L'invio c'e': `requested_at`, orologio del DB. |
| canale 47331 `/order` | desktop calcio (ladder, green-up, cash-out) | nessuno | MANCA. `localTransport.ts:434-450` manda il comando con `client_ref` ma senza l'istante del clic. `LocalRequest` (local_channel.py:180) non porta l'istante di arrivo sul socket. `decisione_ms` e `ricezione_ms` valgono quindi `na`. L'attesa nella coda del canale fino al drenaggio non e' visibile. |
| motore `/comando/<attore>` | bot sulla strada unica (porta di Safe e Omega) | `creato_ms` (obbligatorio nel protocollo) | C'E'. `decisione_ms = ricevuto_ms - creato_ms`, stesso PC. `ricezione_ms` = attesa nella coda del motore. |
| tennis 47332 | desktop tennis | nessuno | MANCA, come il 47331. |
| coda tennis | desktop tennis senza canale | nessuno | MANCA. L'invio c'e': `created_at`, orologio del DB. |

Per avere la decisione su tutte le strade bastano due aggiunte, NON fatte perche'
fuori perimetro:
- un `emesso_ms` nel comando del desktop e nei `params` di Omega e Safe;
- un `ricevuto_ms` in `LocalRequest`.
Il modulo le legge gia'.

## 4. Scelte e limiti dichiarati

- **Journal e audit con JSON libero: NON usati.**
  - `betfair_live_audit.detail` si scrive in `_write_done`. In quel momento la risposta
    di Betfair e l'abbinamento non ci sono ancora (arrivano dopo, dallo stream).
  - Scriverli dopo sarebbe IO nuovo, e il brief vieta di cambiare l'IO. Aggiungere
    chiavi al payload di oggi cambierebbe l'IO a strumentazione accesa, e solo con
    numeri parziali.
  - Il diario del motore (`_diario_ordini/*.jsonl`) fa fsync sul percorso dell'ordine:
    scriverci di piu' aggiungerebbe latenza.
  - Tutto resta nel log. DECISIONE DEL COORDINATORE: se si vogliono i numeri anche nel
    DB, serve un passo esplicito.
- **Non coperti** (non passano da `_dispatch` del runner):
  - i 4 bot tennis che piazzano con flumine nello stesso processo (S3b);
  - Mike e il ripiego REST di Omega e Safe (S3a, `place_order_live`);
  - lo scalper calcio (S4a).
- **Place-and-trim.** Si misura il primo place, dentro `FlumineSubminOps.place`. I
  passi di trim e replace non sono ordini nuovi e non hanno una riga.
- **Tennis dopo un replace.** L'ordine corrente del trade e' un altro oggetto: la riga
  del place originale esce per stato terminale o per TTL.
- **Bet delay.** Se lo stream vede l'abbinamento prima che flumine registri la risposta
  di placeOrders, la riga esce con `risposta_ms=na`. `abbinato_ms` si calcola comunque
  dalle date di Betfair (`placedDate` dello stream).
- **Paper.** L'ordine simulato non ha `matchedDate`, quindi
  `abbinato_fonte=osservato`. La cadenza dell'osservazione e' quella di
  `process_orders`: nel runner tennis e' `_reconcile_tracked`, a ogni giro del worker.

## 5. Test

Variabili esportate prima di OGNI pytest: `SUPABASE_URL=http://127.0.0.1:9`,
`SUPABASE_SERVICE_ROLE_KEY=x`, `SUPABASE_KEY=x`.

### 5.1 Test esistenti dei file toccati

| insieme | HEAD senza hook | dopo, acceso | dopo, spento (`LIVE_TEMPI_ORDINE=0`) |
|---|---|---|---|
| worker, canale, motore, banco, specchio, runner, tennis (10 voci sotto) | 631 | 631 | 631 |
| file vicini (8 voci sotto) | 215 | 215 | 215 |
| tutto insieme + 13 nuovi | - | 859 | 859 |

Il primo insieme:
- `Betfair/stream/tests/test_live_order_worker.py`
- `test_local_channel.py`
- `test_motore_ordini_2026_09_24.py`
- `test_strada_unica_banco_2026_09_25.py`
- `test_live_trading_strategy.py`
- `test_runner_live_strategy.py`
- `test_porta_banco_f4_2026_09_24.py`
- `test_audit_fixes_2026_07.py`
- `Betfair/stream/tennis_live/tests/` (tutta la cartella)

Il secondo insieme:
- `test_paper_live_stesso_processo_2026_09_16.py`
- `test_runner_guardia_canale_locale_2026_09_23.py`
- `test_review_finale_2026_07_17.py`
- `Betfair/safe_strategy/tests/test_porta_ordini_f5_2026_09_24.py`
- `Betfair/omega/tests/test_porta_ordini_omega_f6_2026_09_24.py`
- `test_esiti_ordini_canale_2026_09_23.py`
- `test_consapevolezza_flumine_2026_09_17.py`
- `test_scalper_control_room_2026_09_24.py`
- `test_live_order_build.py`

Come si e' preso il riferimento HEAD: `git apply -R` della patch degli hook, test,
`git apply` di nuovo. Mai `git checkout`.

### 5.2 Test nuovi: `Betfair/stream/tests/test_tempi_ordine_f0_2026_09_25.py`, 13 test

Tutti verdi, 5 ripetizioni senza instabilita'.

- (a) `test_a_coda_tutti_i_tratti_valorizzati_e_coerenti`:
  - riga vera della coda (`requested_at` ISO, `client_ref`, `params`) e claim di
    40 ms;
  - ordine flumine VERO da `build_order`;
  - risposta con `PlaceOrderInstructionReports` e stream con `UnmatchedOrder`
    (`pd`/`md` epoch ms);
  - passaggio da `LiveTradingStrategy.process_orders`.
  - Verifica tutti gli 8 tratti valorizzati, non negativi, e questi valori:
    `decisione=500`, `ricezione>=400`, `presa>=40` ma `place<40`,
    `interno=presa+place`, `abbinato=1500` da Betfair, orologi misti dichiarati,
    cache vuota alla fine.
- (a) `test_a_coda_riga_vera_di_oggi_decisione_assente`: con i `params` di oggi,
  `decisione_ms=na`; fonte dell'abbinamento `osservato`.
- (a) `test_a_coda_errore_pre_place_scrive_subito`: mercato non sottoscritto, la riga
  esce subito con `esito=errore`.
- (b) `test_b_canale_47331_strada_canale`: `LocalChannel` e `LocalRequest` VERI,
  strada=canale, decisione e ricezione `na`.
- (b) `test_b_motore_comando_strada_comando`: harness VERO del motore (fixture `amb`
  dei test del 24/09), strada=comando, `decisione>=250`.
- (c) `test_c_tennis_canale_e_coda_strada_tennis`: worker tennis vero,
  `_reconcile_tracked` vero, due righe strada=tennis (via canale e via coda).
- (d) `test_d_interruttore_spento_modulo_mai_chiamato`: tutte le funzioni del modulo
  sostituite da spie; coda, canale, tennis e specchio girano; zero chiamate e zero
  righe; gli ordini partono come prima.
- (e) `test_e_ttl_scaduto_scrive_e_libera` (orologio finto), `test_e_tetto_voci`,
  `test_e_modulo_non_solleva_mai`.
- (f) `test_f_script_p50_p95`: 1..20 da p50 10,5 e p95 19,05; 10/20/30/40 da p50 25 e
  p95 38,5; `na` saltati; misti contati; CLI `--per-via` da file.
  `test_f_script_legge_le_righe_vere_del_modulo` verifica che lo script legga il
  formato scritto dal modulo.
- (g) `test_g_traccia_identica_accesa_e_spenta`: un giro completo di `_process_once`
  (canale: place e cancel; coda: place ok, mercato mancante, cancel su bet ignoto) con
  un DB spia. Sono uguali, accesa e spenta:
  - la sequenza (tabella, passi della catena, chiavi del payload) di OGNI execute;
  - le chiamate al mercato;
  - le risposte al desktop;
  - gli stati finali delle righe.

### 5.3 Falsificazione

Script `AUDIT_2026-09-25/f0_tempi/falsifica_f0.py`, esito in `falsificazione_f0.txt`.
Ripristino byte per byte e hash di `git diff` uguale prima e dopo.

| # | mutazione | test rossi |
|---|---|---|
| M1 | tratto calcolato al contrario | a, b-comando, c |
| M2 | interruttore ignorato (calcio) | d, g |
| M3 | interruttore ignorato (tennis) | d |
| M4 | interruttore ignorato (specchio) | d |
| M5 | cache senza tetto | e-tetto |
| M6 | TTL ignorato | e-ttl |
| M7 | strada del canale sbagliata | b-canale |
| M8 | strada tennis sbagliata | c |
| M9 | la misura aggiunge una lettura al DB | g |
| M10 | percentile a rango vicino | f |
| M11 | aggancio `place` tolto | 4 |
| M12 | aggancio stream tolto | 3 |
| M13 | `place_ms` dalla ricezione | a |
| M14 | abbinato solo osservato | 4 |
| M15 | aggancio `presa` tolto | 5 |
| M16 | decisione del motore non passata | b-comando |
| M17 | orologi misti non dichiarati | a, c |
| M18 | reconcile tennis senza aggancio | c |

M13 era VERDE alla prima prova: presa e ricezione quasi coincidevano nel finto. Il
test (a) e' stato rinforzato con un claim di 40 ms, come il giro vero al DB. Ora e'
rosso.

## 6. Come si legge la misura al prossimo avvio (PAPER)

1. Avviare l'app come sempre. L'interruttore e' acceso di serie; `LIVE_TEMPI_ORDINE=0`
   nel `.env` lo spegne.
2. Il runner fa `logging.basicConfig(INFO)` su stderr. Il desktop lo ristampa con il
   prefisso `[<label>:err]` (desktop/main.js:261-270). Lo script trova
   `tempi_ordine ...` in qualunque punto della riga.
3. Salvare l'uscita della console dell'app in un file e lanciare:
   `python -m Betfair.stream.tools.leggi_tempi_ordine <file> [--per-via]`
   (oppure `-` per leggere da standard input).
4. Leggere per strada:
   - `interno_ms` (obiettivo p95 < 10 ms);
   - `presa_ms` (attesa del giro e claim);
   - `ricezione_ms` (coda: attesa del poll; e' misto, con errore circa -2 s);
   - `risposta_ms` (bet delay e rete);
   - `abbinato_ms`.

## 7. NON VERIFICATO

- Nessuna misura dal vivo: nessuna app, runner, DB vero o Betfair.
- Non so dove finisca oggi la console del desktop (file o no): va capito al prossimo
  avvio.
- In live, l'ordine di arrivo fra risposta di placeOrders e stream ordini non e'
  provato: e' coperto dai due casi del par. 4, ma senza dati veri.
- Il costo reale dell'aggancio sul thread principale di flumine con molti ordini aperti
  non e' misurato. Per costruzione e' un lookup per ordine.
- I test del banco (`certifica`) e i replay NON sono stati rilanciati: la consegna
  vietava i replay. Il banco usa `_dispatch` e `_place_or_raise`, quindi con
  l'interruttore acceso scrivera' anche righe `tempi_ordine` nel suo log.

## 8. File toccati e comandi

File nuovi:
- `Betfair/stream/tempi_ordine.py`
- `Betfair/stream/tools/leggi_tempi_ordine.py`
- `Betfair/stream/tests/test_tempi_ordine_f0_2026_09_25.py`
- `AUDIT_2026-09-25/f0_tempi/falsifica_f0.py`
- `AUDIT_2026-09-25/f0_tempi/falsificazione_f0.txt`
- questo referto

File modificati (solo righe aggiunte):
- `Betfair/stream/live_order_worker.py` (+27)
- `Betfair/stream/motore_ordini.py` (+5)
- `Betfair/stream/engine/live_trading_strategy.py` (+9)
- `Betfair/stream/tennis_live/tennis_live_order_worker.py` (+25)

Comandi eseguiti, tutti dal worktree, con le variabili `SUPABASE_*` finte:
- pytest sugli insiemi del par. 5.1, su HEAD e dopo, con l'interruttore acceso e
  spento: tutti verdi;
- pytest dei test nuovi, 5 volte: verde;
- `python AUDIT_2026-09-25/f0_tempi/falsifica_f0.py`: 18 su 18 rossi, exit 0;
- `git apply -R` / `git apply` per il riferimento HEAD: diff ripristinato identico;
- controllo ASCII dei file nuovi e delle righe aggiunte: nessun carattere non ASCII.
