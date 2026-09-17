# CHECKPOINT T1 — LE USCITE DI OMEGA SONO PROPOSTE CHE FIRMA L'UTENTE (17/09/2026)

> Delegato Opus 5, worktree `agent-a5f04bb13d31c4d17` (base `3733f17`).
> **Referto del COSTRUTTORE. Non e' una certificazione**: certifica il coordinatore,
> rileggendo il diff, rilanciando test e replay di persona e rifacendo la falsificazione
> con mutazioni sue. Qui c'e' tutto quello che serve per farlo, comando per comando.

## 0. L'ordine dell'utente che questo lavoro esegue

`MANDATO_OMEGA_V4_2026-09-17.md` §1, regola NON negoziabile (b):

> «OMEGA DEVE AVERE LA SCHEDA DOVE L'UTENTE APPROVA LE USCITE, **SIA IN PROFIT CHE IN
> LOSS**, come succede con Safe tennis; nessuna chiusura automatica.»

E §4 punto 22 del programma: produttore Python con proposta in profitto e in perdita
(protezione), numeri (EV di tenere, bloccabile, p_lose, liability), firma dell'utente,
esecuzione via `execution.close_trade`, modello Safe tennis.

## 1. In una pagina: che cosa c'e' adesso e che cosa non c'era

| | prima del 17/09 | adesso |
|---|---|---|
| chi decide l'uscita | in v2 il bot (green-up automatico); in v3 **nessuno** | il bot PROPONE, l'utente FIRMA |
| proposta in PROFITTO | calcolata da `omega_v3.proposta_uscita`, **mai scritta** (produttore assente) | scritta sulla coda, visibile in Control Room |
| proposta in PERDITA | **impossibile** (`bloccabile_non_positivo` chiudeva ogni ramo) | `protezione` / `cap` / `rischio` |
| la coda | `omega_requests`, **tabella che nessuno drena** (reperto O-1) | `omega_manual_requests`, la coda di sempre |
| una firma eseguita | sarebbe stata marcata «chiusura dell'utente» e avrebbe spento il bot (O-3) | riconosciuta come USCITA DEL BOT approvata |
| controlli | G1, G2 (mai sollecitati) | G1, G2, **G3**, **G4** — tutti sollecitati sul banco |

**Niente e' cambiato di default**: `strategy_version` resta 2, `greenup_mode` resta
`auto`, nessuna soglia, nessuno stake, nessuna finestra, nessun cap e' stato toccato. Il
produttore gira **solo** dove il green-up automatico NON gira (`greenup_mode='off'`,
oppure `strategy_version>=3` che lo spegne dalla whitelist,
`omega_config.resolve_params:331-334`). La scelta resta dell'utente, dal pannello.

---

## 2. MAPPA — file per file, riga per riga

### 2.1 Costruito

| pezzo | dove | che cosa fa |
|---|---|---|
| **produttore** | `Betfair/omega/omega_proposte.py` (nuovo, 704 righe) | `process_proposte_uscita` (fase 1-bis), `_una_gamba`, `_scrivi`, `_decadi`, `_payload`, `cap_di_gamba_scattato`, `cap_globale_scattato`, `parametri_modello` |
| **innesto nel giro** | `omega_service.py:5810-5833` (`run_once`, fase 1-bis) | `if _greenup_active(params): process_auto_greenup(...) else: PR.process_proposte_uscita(...)` — mai insieme |
| **conteggio nel referto del giro** | `omega_service.py:5890`, `:5906`, `:6153` | `"proposte": n_proposte` nei tre ritorni di `run_once` |
| **DB delle proposte** | `omega_db.py:330-405` | `REQUEST_STATES`, `pare_schema_mancante`, `proposta_di_chiusura_viva`, `scrivi_proposta_di_chiusura`, `chiudi_proposta` — **su `omega_manual_requests`** |
| **riconoscimento della firma (O-3)** | `omega_service.py:3941-3992` | `_uscita_del_bot_approvata`, `_exit_kind_della_proposta` |
| **esecuzione della firma (O-3)** | `omega_service.py:4094-4157` (`_manual_cashout`) | `exit_kind` dal vocabolario condiviso, firma sulla riga d'apertura (`meta.chiusura_proposta`), attivita' `uscita_approvata`, **`_dopo_il_cashout` NON chiamato** |
| **rete fail-closed (G1)** | `omega_service.py:4000-4018` | una richiesta coi numeri di una proposta ma **senza `approved_at`** viene RIFIUTATA |
| **proposta in perdita** | `omega_v3.py:877-1010` (`proposta_uscita`) | motivi nuovi `cap`, `rischio`, `protezione`; parametri nuovi `cap_scattato`, `p_lose_max` |
| **controlli** | `certificazione.py` | G2 riscritto (`:1322-1334`), **G3** e **G4** nuovi (`:1400-1490`), G1 esteso (`:1310-1360` + `_firma_umana`) |
| **scenario di replay** | `tools/replay_registrazioni.py` | `proposta-approvata` in `SCENARI`/`SCENARI_DESCRITTI`, `_firma_le_proposte`, `_osserva_le_proposte`, `_aggiorna_le_approvazioni`, `_PropostaDallaCoda`, le tre funzioni di coda su `DbMemoriaOmega` |
| **migrazione** | `migrations/omega_proposte_coda_unica_2026-09-17.sql` (nuova) | **da applicare dall'utente**, vedi §3 |
| **UI** | `frontend/src/lib/omegaProposte.ts`, `omega.ts`, `components/controlroom/SchedaChiusuraOmega.tsx`, `components/omega/ManualPanel.tsx` | vedi §5 |

### 2.2 NON toccato (vincolo del brief, verificato con `git diff`)

`Betfair/safe_strategy/execution.py` · `Betfair/omega/omega_market.py` ·
`Betfair/stream/backtest/*` · `Betfair/stream/local_channel.py` · `live_order_worker.py` ·
`runner.py` · `frontend/src/lib/interruttori.ts` · `frontend/src/components/controlroom/*`
(tranne `SchedaChiusuraOmega.tsx`, esplicitamente concesso).
In `omega_service.py` gli unici blocchi toccati sono `svuota_le_cache`, `_manual_cashout`
e `run_once` (verifica: `git diff -U0 Betfair/omega/omega_service.py | grep '^@@'`).
**Nessuna riga in `scan_and_place_legs`, `_size_and_place`, `reconcile_pending`,
`reconcile_decision`** (perimetro di altri due delegati).

---

## 3. IL REPERTO O-1, E COME SI CHIUDE

`migrations/omega_proposte_uscita_2026-09-16.sql` ha creato `public.omega_requests` e ci
ha messo sopra le tre RPC. Ma il servizio drena **solo** `public.omega_manual_requests`
(`omega_db.pending_manual_requests:257-262`, `.eq("status","pending")`). Una proposta
APPROVATA sarebbe passata da 'proposed' a 'pending' **su una tabella che nessuno legge**:
il trader avrebbe premuto APPROVA, la scheda avrebbe detto «fatto», e la posizione
sarebbe rimasta aperta fino al settlement.

`migrations/omega_proposte_coda_unica_2026-09-17.sql` (da applicare, idempotente):

1. `omega_manual_requests` prende `updated_at` (non ce l'aveva: `result` si', `omega_manual.sql:81`);
2. il CHECK di `status` diventa il **superset** `('proposed','pending','processing','done','rejected','error')` — nessuna riga esistente puo' diventare invalida;
3. il CHECK di `kind` riafferma `'cashout'` (lo aggiunge gia' `omega_cashout.sql:44-45`: qui non si da' per scontato l'ordine di applicazione);
4. indice UNICO «una proposta viva per gamba» su `(payload->>'trade_id') WHERE status='proposed'` + indice di lettura;
5. `omega_request_approve` / `omega_request_ignore` / `get_omega_proposte` **ricreate sulla tabella giusta**, stessa firma e stesso ritorno: **la UI non cambia**;
6. `get_omega_manual_requests(p_limit)` ricreata con `WHERE status NOT IN ('proposed','rejected')` — senza, le proposte comparirebbero nell'elenco dei comandi manuali dell'utente (`frontend/src/lib/omega.ts:fetchManualRequests`). Stessi REVOKE/GRANT;
7. `omega_requests` orfana: **DROP solo se vuota**, altrimenti resta e il `RAISE NOTICE` dice cosa fare (una proposta mai eseguita e' una decisione sui soldi: non si butta via senza guardarla).

**Finche' la migrazione non e' applicata** il servizio e' fail-closed: la scrittura
solleva, `omega_proposte._guasto_di_scrittura` riconosce l'errore di schema
(`omega_db.pare_schema_mancante`) e scrive `schema_warn` (pattern O1, in pagina
«MIGRAZIONE MANCANTE») **una volta**; nessuna proposta, nessuna chiusura, la posizione
resta aperta e visibile. Test: `test_senza_migrazione_nessuna_proposta_e_lo_dichiara`.

⊘ **Non verificato**: le RPC vere non sono state provate contro Supabase (DB in sola
lettura, migrazione non applicata). Quello che e' provato e' che il **payload** e gli
**stati** che la RPC produce sono quelli che il servizio si aspetta (il finto del replay
e dei test rifa' `payload || {approved_at}` come la RPC, difetto 27 del catalogo).

---

## 4. LE TRE PROPOSTE NUOVE (reperto O-4)

`omega_v3.proposta_uscita` aveva **sei** esiti e uno solo proponeva. Con il bloccabile
<= 0 usciva SEMPRE da `bloccabile_non_positivo`: **in perdita il bot non chiedeva mai
niente**. Adesso, nell'ordine in cui la funzione decide:

| motivo | quando | proponi |
|---|---|---|
| `nessun_prezzo_di_back` / `controparte_insufficiente` | non si puo' chiudere | no |
| **`cap`** | un tetto di rischio e' SCATTATO (`v3_max_liability_per_leg`, `v3_max_liability_per_match`, `max_liability_per_match`, `v3_max_open_liability`, `max_open_liability`, `v3_daily_loss_cap`, `daily_loss_cap`) | **si'**, a prescindere dall'EV |
| **`rischio`** | `p_evento > proposta_p_lose_max_pct/100` — **soglia SPENTA per default (0)** | si' |
| **`protezione`** | bloccabile <= 0 **e** `ev_tenere < bloccabile` (tenere costa di piu') | **si'** |
| `bloccabile_non_positivo` | bloccabile <= 0 e tenere vale ancora di piu' | no |
| `tenere_vale_di_piu` / `aspettare_vale_di_piu` | invariati | no |
| `blocca_il_profitto` | invariato | si' |

**Nessuna soglia nuova accesa.** L'unico parametro nuovo e' `proposta_p_lose_max_pct`,
default **0 = spento**, in whitelist (`omega_config._SPEC`) e nel pannello
(`OMEGA_PARAM_GROUPS`, gruppo «Uscite — proposte che firmi tu»): il test di contratto UI
pretende che ogni chiave della whitelist abbia una UI, e viceversa.

Sul ramo `protezione` il guardiano dell'attesa (`meglio_aspettare`) **non** si applica, ed
e' una scelta dichiarata: il valore dell'attesa e' calcolato nel ramo «se il punteggio
regge», che e' esattamente il ramo che sta venendo meno. Aspettare li' non e' prudenza.

⚠️ **Un test esistente e' stato RISCRITTO**, e va guardato:
`test_bloccare_in_perdita_e_possibile_ma_non_si_propone` (v3, 16/09) asseriva che in
perdita non si propone **mai**. L'ordine dell'utente del 17/09 lo supera. Al suo posto ci
sono due test che separano i due casi (`..._col_rischio_ancora_basso_non_si_propone` →
nessuna proposta; `test_in_perdita_si_propone_la_PROTEZIONE_quando_tenere_costa_di_piu` →
proposta). **E' l'unica alterazione di comportamento, ed e' quella che l'utente ha
chiesto.**

---

## 5. LA UI (dominio Omega)

| file | che cosa cambia | perche' |
|---|---|---|
| `lib/omegaProposte.ts` | canale realtime `omega_requests` → **`omega_manual_requests`** | reperto O-1: la UI ascoltava una tabella che nessuno scrive |
| | i tre motivi nuovi nel dizionario italiano | una chiave mancante mostrerebbe «tenere\_vale\_di\_piu» al trader |
| | `motivoNonApprovabileOmega` accetta `protezione`/`cap`/`rischio` e **non pretende un bloccabile positivo** | senza, la proposta che l'utente ha chiesto sarebbe NON approvabile |
| | `eUnaProtezioneOmega`, `ordinaProposteOmega` (protezione e cap **prima** del green-up) | non approvare una protezione COSTA, non approvare un profitto no |
| | `liability`, `p_fonte`, `cap_scattato`, `riproposta_perche`, `approved_at` nel tipo del payload | sono i campi che il servizio scrive |
| `controlroom/SchedaChiusuraOmega.tsx` | badge «protezione · si blocca una perdita», bottone **«Chiudi in perdita»** (rosso), cella «Rischio impegnato» = liability, il cap e il «perche' te lo richiedo» | un bottone verde «Chiudi ora» su una perdita direbbe al trader il contrario di quello che sta facendo |
| `lib/omega.ts` | quattro etichette d'attivita' (`proposta_scritta`, `proposta_riproposta`, `proposta_decaduta`, `uscita_approvata`); il parametro nuovo nel pannello | il contratto UI (`test_omega_ui_contratto`) pretende un'etichetta per ogni `kind` |
| `components/omega/ManualPanel.tsx` | nell'elenco dei comandi manuali, una proposta firmata si legge «uscita proposta dal bot, approvata» | dalla stessa coda passano due cose diverse; chiamarle entrambe «cash out» le renderebbe indistinguibili nello storico |

⚠️ **DIVERGENZA DAL BRIEF, dichiarata**: il brief diceva «nel frontend cambia SOLO il nome
della tabella del canale realtime». Gli altri cambi di `omegaProposte.ts` e della scheda
**non sono cosmetici**: senza di essi una proposta in perdita sarebbe scritta dal servizio
e **non approvabile dalla UI** (`motivoNonApprovabileOmega` esigeva
`motivo_codice === 'blocca_il_profitto'`), cioe' la regola non negoziabile del mandato
sarebbe rimasta lettera morta. Sono tutti in file del dominio Omega e tutti coperti da
test. Se il coordinatore preferisce separarli in un secondo passaggio, si tolgono senza
toccare il Python — ma allora la scheda non firma le uscite in perdita.

---

## 6. IL RESPIRO DEL DATABASE (§20)

- il produttore **non legge il book via REST**: solo il feed unico, con la stessa
  freschezza del green-up (`GREENUP_MAX_AGE_S` per lo stato, `_feed_prices_fresh` per i
  prezzi). Test: `test_il_produttore_NON_legge_il_book_via_REST` (il finto **solleva** se
  qualcuno chiama `read_book`);
- **sostanza invariata = nessuna scrittura**: sostanza = (motivo, size, punteggio). Il
  PREZZO non e' sostanza — la scheda lo pesca vivo dal feed. Test:
  `test_sostanza_invariata_nessuna_riscrittura` (conta le scritture);
- la coda si rilegge al massimo ogni `_RICONTROLLO_PROPOSTA_S` = 20 s per gamba;
- i cap GLOBALI non costano **niente** quando sono a zero (ed e' la produzione di oggi):
  `cap_globale_scattato` esce prima di leggere gli aggregati. Test:
  `test_senza_cap_configurati_non_si_legge_NIENTE_dal_database` (il finto **solleva** se
  qualcuno legge).

**Reperto trovato dal banco e corretto** (35777617, 17/09): far decadere la proposta anche
quando mancava solo la CONTROPARTE produceva **9 proposte e 8 decadenze su una gamba
sola**, con `decided_at` che ripartiva ogni volta — cioe' la latenza della firma non
voleva piu' dire niente, e il DB prendeva ~18 scritture per gamba. I motivi TRANSITORI
(`controparte_insufficiente`, `nessun_prezzo_di_back`) adesso non fanno decadere niente: il
green-up automatico, nello stesso caso, ASPETTA. Dopo la correzione: **1 proposta, 86
osservazioni, `decided_at` fermo**. Test: `test_una_controparte_che_sparisce_NON_uccide_la_proposta`.

---

## 7. TEST — come si rifanno

```
# python (dal worktree; il python e' quello del checkout principale, via junction .venv)
python -m pytest Betfair/omega -q -p no:cacheprovider
python -m pytest Betfair/stream -q -p no:cacheprovider

# frontend (node_modules del checkout principale, via junction)
cd frontend
npx vitest run src/lib/omegaProposte.test.ts
npx vitest run                       # suite intera
npx tsc -p tsconfig.app.json --noEmit
```

| suite | prima | dopo |
|---|---|---|
| `Betfair/omega` | **976** (973 passed + 3 skipped) | **1005** (1002 passed + 3 skipped) |
| `Betfair/stream` | verde | verde |
| `Betfair/omega` + `Betfair/stream` | 2419 passed + 27 skipped | **2445 passed + 27 skipped** |
| frontend `vitest run` | — | **2682 passed, 30 skipped, 146 file** |
| frontend `tsc --noEmit` | 0 errori | **0 errori** |

⚠️ Nel worktree manca `frontend/.env`: senza, `src/integrations/supabase/client.ts`
solleva `supabaseUrl is required` e i test che montano componenti falliscono **per
l'ambiente, non per il codice**. Si gira con due variabili finte (mai il `.env` vero):
`VITE_SUPABASE_URL=http://localhost:54321 VITE_SUPABASE_ANON_KEY=finto npx vitest run`.

File di test nuovo: `Betfair/omega/test_omega_proposte_2026_09_17.py` (26 test, 697 righe).
Test toccati: `test_omega_v3_2026_09_16.py` (+4, uno riscritto: vedi §4),
`test_omega_ui_contratto_2026_09_11.py` (il contratto guarda anche `omega_proposte.py`),
`frontend/src/lib/omegaProposte.test.ts` (+7), `ManualPanel.cert.12set.test.tsx` (+2).

---

## 8. REPLAY — prima e dopo, stesso comando

```
python -m Betfair.stream.backtest.certifica omega <event> \
  --scenari v3,manuale-e-bot,cashout-globale,chiuso-fuori-app[,proposta-approvata] \
  --worker 3 --data-dir "C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\_live_raw"
```

> Le registrazioni **non sono nel worktree** (`_live_raw` non e' in git): si legge la
> cartella del checkout principale in SOLA LETTURA con `--data-dir` (equivalente a
> `LIVE_STREAM_DATA_DIR`). Nessuna copia, nessuna scrittura.

### 8.1 PRIMA (4 scenari, codice `dd82c5d4dae1`)

| evento | esito | E1 | E3 | E4 | E5 | G1 | G2 | G3 | G4 |
|---|---|---|---|---|---|---|---|---|---|
| 35760084 | **0 violazioni** | 324 | 576 | 110 | 108 | 468 | **0** | — | — |
| 35777617 | **0 violazioni** | 253 | 533 | 89 | 89 | 445 | **0** | — | — |

(G3/G4 non esistevano. G2 «non lo so»: nessuna proposta e' mai stata scritta, perche' il
produttore non c'era.)

### 8.2 DOPO (5 scenari)

Codice bot `472bba914207`, `--worker 3`, 52 controlli attivi (erano 50: G3 e G4 sono nuovi).

| evento | esito | E1 | E3 | E4 | E5 | G1 | G2 | G3 | G4 |
|---|---|---|---|---|---|---|---|---|---|
| 35760084 | **0 violazioni** | 432 | 576 | 110 | 108 | 936 | 0 ⊘ | 0 ⊘ | 0 ⊘ |
| 35777617 | **0 violazioni** | 338 | 619 | 89 | 89 | 892 | **87** | **86** | **46** |

**Come si leggono i numeri.** I conteggi sono la SOMMA sugli scenari, quindi lo scenario
in piu' li alza per costruzione:

- **E4 e E5 sono INVARIATI** (110/108 e 89/89): sono controlli di scenario
  (`cashout-globale`, `chiuso-fuori-app`) e il quinto scenario non li tocca. **E' la
  prova che nulla e' regredito** su cash-out globale e chiusura fuori app.
- **E3**: 576 su 35760084 (identico al prima), 619 su 35777617 (533 + 86 del nuovo
  scenario). Il conteggio del PRIMA per 35760084 comprendeva gia' tutti gli scenari che
  lo sollecitano.
- **E1**: 324 → 432 e 253 → 338, cioe' +108 e +85: e' esattamente il contributo dello
  scenario nuovo (un caso per giro con posizione aperta).
- **G1**: 468 → 936 e 445 → 892, cioe' esattamente raddoppiato: il quinto scenario ha
  `strategy_version=3` come `v3`, quindi G1 ha un caso a ogni giro anche li'.
- **G2/G3/G4** erano «non lo so» e adesso hanno dei casi, su 35777617.

⊘ Su **35760084** G2/G3/G4 restano a zero: su quella partita nessuna proposta e'
possibile (§8.3). E' «non lo so», non «e' sano», e il referto lo scrive.

### 8.3 Che cosa succede davvero nello scenario `proposta-approvata`

Su **35777617**: il bot apre un lay '2 - 1' a 48 per 5,26 € (liability 247,22 €); al 74'
il produttore scrive la proposta **#900001, motivo `cap`** (la liability supera
`v3_max_liability_per_leg`, 120 € di default in v3) coi numeri — blocchi **−0,48 €**
contro un EV di tenere di **+2,36 €**, P del bancato **1,044 %** (fonte `v3:pre_ko_odds`);
il banco la **FIRMA** al giro dopo come fa il trader dalla Control Room; `process_manual`
la drena e `execution.close_trade` piazza il back a 44 per 5,74 €. Esito: **eseguita dopo
1 giro**, `exit_kind='loss'` (mai «green-up» su una perdita), attivita' `uscita_approvata`,
e la partita **NON** risulta «chiusa dall'utente» — il bot continua a gestirla.

Su **35760084** nessuna proposta e' possibile ed e' un verdetto sulla PARTITA, non un
guasto: il lay e' '3 - 3' a 300 per 5,26 €, e per chiuderlo servirebbero 14,35 € di back
mentre il miglior back (110) ne offre 2,15. Il motivo dichiarato e'
`controparte_insufficiente`. G2/G3/G4 restano «non lo so» su quella registrazione, e il
referto lo scrive in chiaro.

⊘ **Limite dichiarato**: nello scenario il motore che APRE e' ancora il v2 mentre i
parametri sono quelli di v3 (`strategy_version=3` non collega ancora `omega_v3` al
servizio: e' il lavoro di un'altra fase). Ne segue che la gamba aperta ha una liability da
v2 (247 €) contro i cap di v3 (120 €), e il motivo che esce e' quasi sempre `cap`. Sul
banco di oggi **non si e' visto** ne' un `blocca_il_profitto` ne' una `protezione` in
condizioni di produzione: quei due rami sono provati dai test, non dalle registrazioni.
Per vederli sul banco serve o una registrazione con un lay che va in profitto con
controparte sufficiente, o la Fase 2 (v3 collegato, stake 1 €, liability sotto i cap).

---

## 9. FALSIFICAZIONE — il difetto rimesso, l'output rosso, il ripristino

Ogni mutazione e' stata fatta **sul codice di produzione**, non sui test; dopo ogni
ripristino e' stato verificato l'md5.

### F1 — l'approvazione trattata come chiusura dell'utente (reperto O-3)

`omega_service._uscita_del_bot_approvata` → `return False`.

```
FAILED Betfair/omega/test_omega_proposte_2026_09_17.py::test_una_proposta_firmata_si_riconosce
1 failed, 23 passed

# e sul banco (35777617, scenario proposta-approvata):
nota:   FIRMA della proposta #900001 ... exit_kind=manual, partita chiusa dall'utente=True
G3 x86: es. la proposta 900001 e' stata eseguita con exit_kind='manual': nello storico
        non si distingue piu' da un cash out premuto a mano [...] (reperto O-3)
ESITO: 0 partite senza violazioni, 1 con violazioni
       86 violazioni totali
```

Ripristinato — md5 `aefc514282e4eccd241afc40b3134ea0` (invariato).

### F2 — la proposta drenata dal servizio SENZA firma (reperto O-1 al contrario)

Due mutazioni insieme, perche' insieme fanno il difetto: (a) in `omega_service._manual_cashout`
la rete «proposta non firmata» spenta (`if False:`); (b) nel banco
`DbMemoriaOmega.pending_manual_requests` allargata a `("pending", "proposed")`.

```
G1 x1: es. ordine di BACK (= chiusura) partito senza approvazione dell'utente: ref omega-t2
ESITO: 0 partite senza violazioni, 1 con violazioni
       1 violazioni totali
```

Ripristinati — md5 `aefc514282e4eccd241afc40b3134ea0` e `7d975f982a02a147e5fd4c7a54c8409c`.

### F3 — in perdita non si propone piu' niente (reperto O-4)

`omega_v3.proposta_uscita`, ramo `protezione`: `if ev_h < b.profitto:` → `if False:`.

```
FAILED Betfair/omega/test_omega_proposte_2026_09_17.py::test_in_perdita_il_bot_PROPONE_la_protezione
FAILED Betfair/omega/test_omega_v3_2026_09_16.py::test_in_perdita_si_propone_la_PROTEZIONE_quando_tenere_costa_di_piu
  assert pr.proponi is True
E AssertionError: assert False is True
  +  where False = PropostaUscita(proponi=False, motivo_codice='bloccabile_non_positivo',
     profitto_bloccabile=-1.0, ..., testo='chiudere ora vale -1.00 EUR contro un EV di
     tenere di -29.04 EUR: si tiene').proponi
2 failed, 67 passed
```

Ripristinato — md5 `17ea528e677e0348f0a84a0f5a098fc2` (invariato).

> ⊘ **Limite di F3**: G4 **non** diventa rosso nel replay, e va detto. G4 giudica le
> proposte in perdita **scritte**; una proposta mai scritta non produce nessun momento da
> giudicare. Il caso «in perdita, tenere costa di piu', e il bot tace» e' coperto dal ramo
> (c) di G4 a livello unitario (`test_G4_...`, terzo assert) e dai due test rossi qui
> sopra. Chi certifica lo tenga presente: **sul banco, G4 vale solo su cio' che e' stato
> proposto.**

### F4 — la UI torna ad ascoltare la tabella orfana

`omegaProposte.ts`: `table: 'omega_manual_requests'` → `'omega_requests'`.

```
FAIL src/lib/omegaProposte.test.ts > realtime: la coda e UNA sola (reperto O-1)
  → expected 'omega_requests' to be 'omega_manual_requests'
Tests 1 failed | 19 passed
```

Ripristinato — md5 `5fdb397e9d6085d5fb9174f5979ee1e8` (invariato).

### F5 — il finto che non parla come il vero (difetto 27 del catalogo)

Nel test, `"selection_id"` della selezione del feed → `"selectionId"` (camelCase, come il
grezzo di Betfair).

```
11 failed, 14 passed
FAILED ...::test_la_proposta_porta_TUTTI_i_numeri_della_decisione
FAILED ...::test_in_perdita_il_bot_PROPONE_la_protezione
FAILED ...::test_un_cap_scattato_propone_e_lo_dichiara
[...]
```

Ripristinato — suite di nuovo verde (26/26).

### F6 — falsificazioni gia' scritte come test permanenti

- `test_il_servizio_non_drena_mai_una_proposta_falsificazione` — il filtro della coda si
  allarga e il cancelletto sparisce;
- `test_in_perdita_il_bot_PROPONE_la_protezione_falsificazione` — `proposta_uscita` torna a
  fermarsi su `bloccabile_non_positivo`;
- `test_senza_migrazione_nessuna_proposta_e_lo_dichiara_falsificazione` — l'errore di
  schema scambiato per un guasto qualunque: l'avviso «MIGRAZIONE MANCANTE» sparisce.

---

## 10. COPERTURA §6 del `PROCESSO_STANDARD_BOT.md`

| § | voce | stato |
|---|---|---|
| 6.1 | dati di mercato veri | **si'** — feed unico scritto dallo SCANNER VERO, book di flumine dalla registrazione |
| 6.2 | scanner vero | **si'** — `ScannerReplay` alimenta la riga, il produttore la legge come in produzione |
| 6.3 | servizio intero a cadenza reale | **si'** — `run_once` intero, `poll_interval_s`/`idle_cycle_s` veri (445-468 giri per partita) |
| 6.4 | ciclo di vita dell'ordine, parziali, bet delay | **si'** per la CHIUSURA approvata (`close_trade` → flumine, 1.861 book passati durante l'attesa di Betfair). ⊘ nessun fill PARZIALE della chiusura si e' verificato sul banco |
| 6.5 | persistenza e UI | **si'** — le proposte stanno nella coda con le colonne vere, il referto stampa la riga che il trader vedrebbe |
| 6.6 | concorrenza | **parziale** — indice UNICO «una proposta viva per gamba» nella migrazione; ⊘ la corsa fra due schede aperte e' garantita dal `FOR UPDATE` della RPC, **non provata contro Supabase** |
| 6.7 | scenari | **si'** — scenario `proposta-approvata` nel banco comune, mai «a parte» |
| 6.8 | falsificazione | **si'** — §9 |
| 6.9 | referto riproducibile | **si'** — questo file, coi comandi |
| D1 | scritture al DB per minuto | **misurato**: 1 proposta e 86 aggiornamenti-marcatore su 445 giri (1 sola riga in coda); prima della correzione erano 9 righe e 8 decadenze |

## 11. CATALOGO §7 — i difetti applicabili, e dove sono presi

| difetto | dove e' preso |
|---|---|
| 1 — il finto che non parla come il vero (camelCase) | F5 + finti costruiti sulle colonne vere |
| 2 — l'ordine rifiutato che lascia la riga viva | non applicabile (qui non si piazza: si propone) |
| 19 — lo stato che vive solo in RAM | il marcatore `meta.exit_proposal` sta sulla RIGA, la proposta nel DB; scenario `riavvio` non toccato |
| 27 — il finto che perde una chiave | `_firma_le_proposte` rifa' `payload || {approved_at}` come la RPC, e il commento lo spiega |
| «le chiusure distruggono valore» (12/09) | G1 + G4 + la rete fail-closed: nessuna chiusura parte da sola, in nessuno dei due rami |
| T14 della Safe (282 violazioni, 16/09) | O-3: `_dopo_il_cashout` NON si chiama su una firma; G3 lo verifica |

---

## 12. CIO' CHE NON HO POTUTO VERIFICARE (⊘)

1. **Le RPC vere contro Supabase.** DB in sola lettura, migrazione non applicata. Sono
   provati il payload, gli stati e il comportamento del servizio, non il SQL in esecuzione.
   In particolare: il `FOR UPDATE` della corsa fra due schede, l'indice unico parziale, il
   `DROP TABLE` condizionato di `omega_requests`.
2. **Il ramo `blocca_il_profitto` e il ramo `protezione` sul BANCO.** Sulle due
   registrazioni provate escono solo `cap` (35777617) e `controparte_insufficiente`
   (35760084). Sono provati dai test, non dalle registrazioni (vedi §8.3).
3. **Il ramo `rischio`.** La soglia nasce spenta, quindi sul banco non puo' scattare.
   Provato solo dai test.
4. **Il fill PARZIALE di una chiusura approvata.** Non si e' verificato sul banco; il
   residuo lo gestisce `close_trade` come per ogni altra chiusura, ma qui non e' stato
   esercitato.
5. **Paper vs live.** Lo scenario gira in `live` (matching di flumine). La parita' col
   percorso paper non e' stata misurata per le proposte.
6. **La scheda dal vivo.** Non ho avviato l'app (e' viva con soldi veri sul checkout
   principale): la scheda e' provata solo da vitest.
7. **`frontend/.env`** assente nel worktree: la suite frontend gira con due variabili
   finte. Se il coordinatore la rilancia dal checkout principale, usi il `.env` vero.

## 13. REPERTI CHE SEGNALO E **NON** HO CORRETTO (fuori perimetro)

- **R-T1 — `_manual_place` e la consapevolezza dell'ordine.** Il percorso di CHIUSURA
  approvata **e' a posto**: `execution.close_trade` conferma la gamba di chiusura con
  `aggiorna_trade(..., consapevolezza=out.consapevolezza, ...)`
  (`execution.py:1345-1349`), che scrive le cinque colonne
  `size_requested`/`size_matched`/`size_remaining`/`avg_price_matched`/`betfair_updated_at`
  quando esistono. Misura nel §14. Resta da guardare `_manual_place` (piazzamento manuale
  dell'utente, **non** la chiusura): non e' in questo task e non l'ho toccato.
- **La nota del referto del banco** stampava `chiesto=` leggendo `meta.requested_size`,
  che sul percorso di chiusura non esiste: e' una lacuna del REFERTO, non della riga.
  Non l'ho cambiata per non toccare il formato del referto comune.

## 14. MISURA — la gamba di chiusura di una proposta approvata

Reperto passato dal coordinatore (R-C1, controllo K7): «il percorso manuale conferma
senza `size_requested`/`size_remaining`/`betfair_updated_at`?». Misurato sullo scenario
`proposta-approvata` di 35777617, leggendo le **colonne** (non il meta) delle due righe:

```
riga 1  lay   apertura   status=won
        size_requested=5.26  size_matched=5.26  size_remaining=None
        avg_price_matched=48.0  betfair_updated_at=None
riga 2  back  CHIUSURA (closes_trade_id=1)  status=lost
        size_requested=5.74  size_matched=5.74  size_remaining=0.0
        avg_price_matched=44.0  betfair_updated_at=None
```

**Verdetto**: la gamba di CHIUSURA di una proposta approvata porta **4 colonne su 5**
(chiesto, abbinato, residuo, prezzo medio). Le scrive `execution.close_trade` chiamando
`aggiorna_trade(..., consapevolezza=out.consapevolezza, ...)` (`execution.py:1345-1349`):
**il buco R-C1 NON c'e' su questo percorso.**

⊘ `betfair_updated_at` resta vuoto **su entrambe** le righe. Non e' un difetto di questo
lavoro: e' l'istante di Betfair (`date_time_status_update`), che arriva dallo SPECCHIO
dell'order stream (`omega_service._mirror_fill`, e in live dal runner) — il mercato
simulato del banco non lo produce. **Va riguardato in paper/live**, non sul replay. Non
l'ho toccato: `execution.py` e' condiviso e il brief lo vieta.

---

## 15. PUNTO DI RIPRESA

1. **L'utente applica** `migrations/omega_proposte_coda_unica_2026-09-17.sql` (e, se non
   l'avesse gia' fatto, verifica che `omega_requests` sia vuota: il `RAISE NOTICE` lo dice).
2. Il coordinatore certifica: diff, suite, replay, falsificazioni sue.
3. Quando v3 sara' collegato al servizio (stake 1 €, liability sotto i cap), rilanciare
   `proposta-approvata` per vedere sul banco anche `blocca_il_profitto` e `protezione`.
4. Il parametro `proposta_p_lose_max_pct` resta a **0**: accenderlo e' una decisione
   dell'utente, non del codice.
