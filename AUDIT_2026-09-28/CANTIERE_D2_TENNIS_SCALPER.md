# CANTIERE D2 — Tennis e scalper: importo minimo e paper specchio del live (28/09/2026)

Delegato Opus del coordinatore, worktree `agent-aa4ee030442dc331f` su master `2eb3c1d`.
Nessun commit, nessun push, nessuna scrittura sul DB (solo 3 `SELECT`), nessuna chiamata a
Betfair, nessun processo nuovo, nessun replay del banco lanciato da me (vedi §6 per l'unica
eccezione: un test gia' esistente della suite che gira il profilo rapido su una registrazione).

Aggiunte del coordinatore in corsa, entrambe fatte: **R-F2-9** (sniper e interruttore uscite
automatiche, §2.6) e **§7.21 / §7.14** (nessun numero di decisione somma paper e live; nessun
fill paper «di casa», §2.8 e §5).

## 0. In breve

| # | Cosa | Esito |
|---|---|---|
| 1 | Apertura tennis sotto il minimo (R-1) | **FATTO**: portata AL minimo (BACK 2,00 / LAY 0,50) e piazzata, paper = live, canale di Safe tennis e 4 bot tennis |
| 2 | Parita' paper/live (4 bot tennis, Safe tennis, scalper calcio) | tabella §4: **6 BUG corretti** qui, 2 fuori perimetro con proposta, il resto uguale o decisione gia' presa dall'utente |
| 3 | R-2 (customerOrderRef vero) | **meta' fatta**: l'evento `order` porta ora il `cor` vero di Betfair; la parte di Safe (salvarlo e usarlo) e' fuori perimetro (§5) |
| 4 | R-3 (partite da comando senza riga nel Terminale) | non fatto: tocca il ciclo di vita del follow (cantiere A); proposta in §5 |
| 5 | Sniper «NON flat dopo 30 s» | **causa radice trovata e corretta**: `is_flat` misurava le stake, non la piattezza |
| 6 | R-F2-9 sniper e uscite automatiche | **FATTO** con la semantica dello scalper; una differenza col testo del brief, spiegata in §2.6 |
| 7 | Debiti del banco (sniper, tennis_pro fuori erba) | preparati: cosa manca al banco, registrazioni, comandi (§7) |

Test: **1.351 verdi** sui file toccati e collegati (+172 Safe canale/porta), 0 rossi.
Falsificazione: **18 mutazioni, 18 ROSSE**, ripristino verificato (sha1 per file, `git diff`
identico byte per byte a prima).

---

## 1. Il minimo vero (documentazione ufficiale)

Betfair Developer Program, pagina **«Betting On Italian Exchange» → «Italian Exchange Specific
Bet Rules»**
(<https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687808/Betting+On+Italian+Exchange>),
testo letto oggi:

1. «The stake for each back offer is a minimum of 200 Euro Cents and can only be incremented in
   multiples of 50 Euro Cents.»
2. «Any lay offers placed by the customer, must be placed in such a way as to ensure that the
   stake for any corresponding back offer amounts to a minimum of 50 Euro Cents.»
   Cioe': la **size** di un LAY (= stake del bancatore) deve essere almeno 0,50 EUR.
3. Vincita potenziale massima 10.000 EUR stake compreso.

Nessun «Minimum Bet Payout» su .it. Coincide con le costanti gia' nel repo
(`live_order_build.py:40-47`, `trading/submin.py::place_min_size`): nessuna costante nuova.

## 2. Cosa ho cambiato e perche'

### 2.1 Apertura tennis sotto il minimo → al minimo (punto 1, decisione dell'utente)

**Causa radice di R-1.** Il motore ordini (`motore_ordini.py:955-979`) manda ogni apertura sotto il
minimo sulla macchina place-and-trim (`place_submin`); l'esecutore tennis non ce l'ha e rifiutava
(`esecutore_tennis.py`, `MOTIVO_SUBMIN`). Con il FOK il rifiuto arrivava ancora prima
(`motore_ordini.py:967`).

**Correzione.**
- `trading/submin.py`: funzione pura nuova `porta_al_minimo_apertura(giurisdizione, lato, size)`.
  Accanto a `place_min_size`, stesse costanti. Alza solo, e solo fino al minimo.
- `tennis_live/esecutore_tennis.py`: `_apertura_al_minimo(side, size)` dichiara la regola per il
  tennis.
- `motore_ordini.py` (righe minime, SEGNALATE: file condiviso):
  - se l'esecutore dichiara `_apertura_al_minimo`, un `place` senza `reduces_liability` sotto il
    minimo si porta al minimo e parte come place normale, FOK compreso;
  - l'evento `order` porta `portata_al_minimo: {chiesto, piazzato}`, cosi' l'attore lo sa;
  - il calcio non dichiara la regola (`live_order_worker` non ha l'attributo): per lui nulla
    cambia, resta il place-and-trim.
- `tennis_scalper/condotta_ordini.py::size_legale`: per i 4 bot tennis un INGRESSO sotto il minimo
  si porta al minimo (prima: rifiuto, «non si gonfia lo stake»). Sopra il minimo resta la regola
  .it di sempre: BACK al multiplo di 0,50 per difetto.
- Le CHIUSURE (`reduces_liability`, coperture dei bot) non passano da qui. Il test
  `test_chiusura_sotto_il_minimo_non_si_gonfia_mai` e la mutazione M10 lo provano.
- Banco: lo scenario R8 tennis (`backtest/trasporto_rapido.py::_r8_tennis`) ora verifica il nuovo
  comportamento: un ordine a 2,00, nessun REST, l'evento lo dichiara, riga Safe non in errore.

**Effetto sul rischio, in parole semplici.**
- **BACK**: un'apertura calcolata fra 0,01 e 1,99 EUR diventa 2,00 EUR.
  - Lo stake cresce al massimo di 1,99 EUR per ordine.
  - Esempio: Safe tennis calcola 1,22 EUR → piazza 2,00 EUR (+0,78, +64 %). La perdita massima
    della gamba e' 2,00 invece di 1,22.
- **LAY**: una size calcolata fra 0,01 e 0,49 EUR diventa 0,50 EUR. La responsabilita' cresce con
  la quota: 0,50 × (quota − 1).
  - A quota 1,05 (il FLB): 0,025 EUR invece di ~0,01, cioe' trascurabile.
  - A quota 3,0: 1,00 EUR invece di (per es.) 0,60.
  - A quota 20: 9,50 EUR invece di 5,70.
  - **A quota alta un LAY minimo non e' piccolo.**
- Il tetto per ordine (`TENNIS_LIVE_MAX_STAKE_PER_ORDER`) e i controlli di esposizione di flumine
  restano DOPO la regola. Un minimo che sfonda un tetto e' rifiutato come prima.

### 2.2 Paper tennis con le blindature .it del live (BUG)

`tennis_runner.py::_instantiate_bot` in PAPER azzerava `live_min_bet`/`size_step`:
- in paper un ingresso da 1,50 o una copertura da 0,93 venivano piazzati e riempiti;
- in live lo stesso ordine era rifiutato o arrotondato;
- lo scalper tennis in paper chiudeva 1,98 EUR, in live 2,00.

Ora PAPER e LIVE ricevono le stesse blindature; solo OFF (nessun ordine possibile) resta senza.

### 2.3 Restart forzato solo in PAPER (BUG)

`tennis_runner.py::_request_restart`: scaduta la grazia, in PAPER il restart del framework si
forzava e azzerava la posizione simulata del bot (ordini VOIDED). In LIVE, con la stessa
posizione, restava bloccato e lo diceva (`restart_blocked` CRITICAL).

Ora PAPER fa come LIVE. Si forza solo in OFF.

**Effetto pratico**: in paper un bot automatico non piatto blocca arm/disarm e nuovi follow finche'
non si chiude la posizione, esattamente come in live.

### 2.4 Commissione del paper = commissione di Betfair (BUG)

`tennis_live_order_worker.py::_reconcile_bots` calcolava la commissione ordine per ordine sul
profitto positivo. Betfair la calcola sulle vincite NETTE del MERCATO
(<https://support.betfair.com/app/answers/detail/413-exchange-what-is-commission-and-how-is-it-calculated/>:
«Betfair charges a Commission on your net winnings on a market. If you have a net loss on a
market you do not pay commission»).

Esempio, green-up back +10,00 e lay −9,00:
- prima il paper pagava 0,50;
- Betfair paga 0,05;
- il paper era piu' severo del live.

Ora: `_commissioni_per_ordine` = max(0, netto del mercato) × aliquota, ripartita sugli ordini in
utile. La somma delle quote e' la commissione del mercato, al centesimo.

### 2.5 Sniper «posizione NON flat dopo 30 s» (reperto e2e 26/09)

**Causa radice.** `sniper_bot.py::is_flat` confrontava le STAKE (|back − lay| > 0,02). Un green-up
riuscito ha stake diverse (back 10 @3,0 + lay 12 @2,5 = +2 EUR su entrambi gli esiti), quindi
risultava «non flat» per sempre. Lo stop della sessione (`scalper_session._all_flat`) aspettava
30 s a vuoto e dichiarava aperta una posizione chiusa. Uguale in paper e in live.

**Correzione.** La stessa misura con cui il bot decide (|se vince − se perde|, `_real_net`) e la
sua tolleranza (0,02, o residuo accettato + 0,02).

Il micro-residuo accettato per costruzione (≤ 0,30, `_drive_flatten`) resta una regola della
strategia, intoccata. Lo dichiara l'attivita' `sniper_flat_residual`; la riga lo dichiara quando
supera 0,30 (D7). L'altra meta' del reperto (`error=null` nella riga) era gia' corretta su master
(`scalper_session.dichiarazione_stop_non_flat`/`dichiara_stato_finale`, commento «26/09 reperto
e2e»); commit non verificato da me.

### 2.6 R-F2-9: lo sniper e l'interruttore «uscite automatiche»

`sniper_bot.py` legge ora `uscite_automatiche` con la STESSA semantica di `scalper_bot.py:434-447`:
- default False;
- solo un booleano vero accende;
- `uscita_proposta` una volta per motivo e per ciclo, con le stesse chiavi (`_proponi_uscita`).

`scalper_session.py` passa il valore allo sniper alla nascita e lo riapplica a caldo a ogni
battito (`applica_uscite_automatiche` anche sullo sniper).

- **Spento (default)**: la presa di profitto a +target_ticks NON parte, si propone.
  Riacceso a caldo, al book dopo la chiusura la mette il bot.
- **Restano automatiche** (come nello scalper, che le chiama PROTEZIONI a `scalper_bot.py:441-443`):
  - stop a N tick;
  - timeout della posizione `max_pos_s` (l'equivalente del `lock_ttl` dello scalper, che nello
    scalper resta automatico, `:1693-1703`);
  - fine finestra;
  - force-flat (freno, cap);
  - flatten e divergenza dello specchio.

**Differenza col testo del brief**, detta apertamente. Il brief chiedeva un test in cui «timeout e
stop dello sniper NON chiudono da soli ma producono la proposta». Nello scalper stop e `lock_ttl`
restano automatici con l'interruttore spento. Replicare lo scalper «senza inventare una semantica
nuova» significa quindi tenerli automatici, e cosi' ho fatto; i test lo provano
(`test_spento_lo_stop_a_n_tick_resta_automatico`, `test_spento_il_timeout_della_posizione_resta_automatico`,
mutazione M14). Se l'utente vuole anche stop e timeout manuali, e' una regola nuova (§8).

Theta (`ThetaStrategy`) ha il suo `process_market_book` e il suo bus di conferma: non toccato.

### 2.7 R-2: il customerOrderRef vero di Betfair nell'evento

- `tennis_live_order_worker._result` porta `cor_betfair`, cioe' `order.customer_order_ref` di
  flumine (`<name_hash><sep><order.id>`).
- `motore_ordini._esegui` lo mette nell'evento `order` come `cor` (primo evento, `inviato`).
- Solo il tennis lo dichiara: nessun effetto sul calcio.
- Il diario write-ahead aveva gia' lo stesso `cor`; il test verifica che coincidano.

### 2.8 Tetto partite dei bot tennis: solo la modalita' del bot (§7.21)

`tennis_bot_service.py::riconcilia_interruttori`: il tetto dell'auto-mode contava le righe armate
del bot in ENTRAMBE le modalita' (es. partite paper ancora vive dopo il passaggio a live). Ora:
- conta solo le righe della modalita' attuale del bot;
- una riga viva dell'altra modalita' non si riscrive mai (mai cambiare modalita' a una riga
  armata).

## 3. File

**Modificati.**

Codice:
- `Betfair/stream/trading/submin.py`
- `Betfair/stream/motore_ordini.py` (condiviso: righe minime e segnalate)
- `Betfair/stream/tennis_live/esecutore_tennis.py`
- `Betfair/stream/tennis_live/tennis_live_order_worker.py`
- `Betfair/stream/tennis_live/tennis_runner.py`
- `Betfair/stream/tennis_live/tennis_bot_service.py`
- `Betfair/stream/tennis_scalper/condotta_ordini.py`
- `Betfair/stream/scalper/sniper_bot.py`
- `Betfair/stream/scalper/scalper_session.py`
- `Betfair/stream/backtest/trasporto_rapido.py` (scenario R8 tennis)

Test esistenti, aggiornati perche' asserivano il comportamento ora corretto (catalogo #28, ognuno
commentato):
- `test_condotta_ordini_2026_09_17.py`
- `test_tennis_bot_params.py`
- `test_motore_ordini_tennis_2026_09_25.py` (R8)
- `test_tennis_audit_runner.py`
- `test_paper_execution_gap5.py`
- `test_tennis_auto_mode_2026_09_25.py`
- `test_modalita_e_guardie_tennis_2026_09_24.py`
- `test_chiudi_ora_bot_tennis_2026_09_24.py`: prova il protocollo sulla size esatta, quindi spegne
  le blindature .it esplicitamente; la granularita' e' provata nei test nuovi.
- `test_sniper_bot_2026_07_10.py` (il ramo verde a uscite accese)
- `test_submin_contratto_chiamanti_2026_09_17.py` (solo commento)

**Nuovi.**
- `Betfair/stream/tennis_live/tests/test_cantiere_d2_minimo_e_specchio_2026_09_28.py` (30 test)
- `Betfair/stream/tests/test_sniper_is_flat_2026_09_28.py` (6)
- `Betfair/stream/tests/test_sniper_uscite_automatiche_2026_09_28.py` (14)
- `AUDIT_2026-09-28/cantiere_d2/`:
  - `falsifica_d2.py`, `falsificazione.txt`;
  - `patch_prima.diff` (il diff completo del lavoro), `stat_prima.txt`;
  - `pytest_toccati.txt`.

**Migrazioni SQL**: nessuna.

## 4. Tabella di parita' paper/live

Verdetti:
- **uguale** = stesso codice e stesso esito;
- **BUG corretto** = corretto qui;
- **decisione utente** = regola gia' presa dall'utente, non un difetto;
- **fuori perimetro** = proposta in §5.

| # | Bot | Ramo (file:riga, codice di oggi) | Paper | Live | Verdetto |
|---|---|---|---|---|---|
| 1 | 4 bot tennis | `tennis_runner.py:799-826` `live_min_bet`/`size_step` | prima 0/0 (size libere), ora 2,00/0,50 | 2,00/0,50 | **BUG corretto** (§2.2) |
| 2 | 4 bot tennis | `condotta_ordini.py:88-131` ingresso sotto il minimo | ora al minimo | ora al minimo (prima rifiuto) | **BUG corretto + decisione utente 28/09** |
| 3 | 4 bot tennis | `condotta_ordini.py:103-117` copertura sotto minimo = over-hedge al gradino 0,50 sopra | uguale (da oggi) | uguale | uguale; ma vedi §8 D-1 |
| 4 | 4 bot tennis | `tennis_runner.py:772-781` `dry_run` di default | False (ordini simulati visibili) | True finche' l'utente non lo toglie per partita | **decisione utente** (T1 24/09, «il reale e' un gesto per partita») |
| 5 | 4 bot tennis | `tennis_runner.py:1150-1185` restart a grazia scaduta | prima forzato (posizione azzerata), ora bloccato | bloccato | **BUG corretto** (§2.3) |
| 6 | 4 bot tennis | `tennis_runner.py:141-178` client: `paper_trade`, latenza 600 ms, bet delay dal `marketDefinition` (`paper_execution` fresco), FOK nativo | simulato flumine | reale | uguale (modello del live; nessun fill di casa) |
| 7 | 4 bot tennis | `guardie_tennis.py:281-294` kill-switch dentro flumine | si' | si' | uguale |
| 8 | 4 bot tennis | `tennis_live_order_worker.py:1083-1140` commissione | prima per ordine, ora netto di mercato | Betfair (netto di mercato), via `pnl_betfair` | **BUG corretto** (§2.4) |
| 9 | 4 bot tennis | stesso, P&L: `simulated.profit` in paper, `pnl_betfair` da Betfair in live | fonte simulata | fonte Betfair | uguale nella regola; fonti diverse per natura (dichiarato, §7.21 «assente non e' zero» rispettato) |
| 10 | 4 bot tennis | `tennis_bot_service.py` tetto auto-mode | prima paper+live, ora solo la sua | idem | **BUG corretto** (§2.8) |
| 11 | 4 bot tennis | `source` / `mode` nello specchio: `_modo_strategia`, `ref_bot_stabile` | 'paper' + bot_key | 'live' + bot_key | uguale |
| 12 | 4 bot tennis | riconciliazione: `_strategy_is_flat` dal blotter | blotter simulato | blotter reale | uguale |
| 13 | Safe tennis (canale) | `motore_ordini.py:955-990` + `esecutore_tennis._apertura_al_minimo` | al minimo, FOK | al minimo, FOK | **BUG corretto (R-1)**, test di parita' campo per campo |
| 14 | Safe tennis (canale) | cor vero nell'evento (R-2) | si' | si' | runner fatto; Safe **fuori perimetro** (§5) |
| 15 | Safe tennis (REST, oggi di serie: canale spento) | `safe_strategy/execution.py:673-790` sotto il minimo | `E.paper_fill` ISTANTANEO al prezzo del book, size esatta (1,22), senza bet delay ne' coda | `place_submin_live` REST (place-and-trim, size esatta, a riposo) | **BUG, fuori perimetro** (file di D1): fill «di casa» in paper (§7.14); e con il canale acceso lo stake e' diverso (2,00). §5 |
| 16 | Safe tennis | stop di giornata/cap/P&L per modalita': `bot_db.py:136-161` | filtrati per `mode` | idem | uguale (gia' separati dal 13/09; area D1) |
| 17 | Scalper calcio | `scalper_session.py:787-851` client `paper_trade` da `dry_run`, strategie `dry_run=False`, `VALIDATED_PARAMS` identici (minimi .it in entrambe) | ciclo ordini flumine simulato | reale | uguale — **7.6.8 verificato sul codice**: in paper gli ordini passano da `market.place_order` → `SimulatedExecution` (`_order_client_kwargs`, `install_fresh_delay_execution` `:1109-1115`, bet delay fresco) |
| 18 | Scalper calcio | `auto_mode.py:319-331` sessioni automatiche nascono SEMPRE in dry_run (paper) anche a interruttore live | paper | paper finche' l'utente non toglie il dry-run per sessione | **decisione utente** (D3 25/09) |
| 19 | Scalper calcio | `scalper_session.py:485-499` crash di flumine: sweep REST solo in live | niente sweep (ordini simulati morti col processo) | sweep dei bet_id | uguale nell'effetto (nessun ordine sopravvive); necessario |
| 20 | Scalper calcio | `scalper_session.py:427-445` theta in live forzato dry_run | theta pieno | theta mai | **decisione utente** (verdetto S4: theta solo paper) |
| 21 | Scalper calcio (sniper) | `sniper_bot.py:is_flat` | falso «non flat» | idem | **BUG corretto** (§2.5), uguale nei due modi |
| 22 | Scalper calcio (sniper) | uscite automatiche (R-F2-9) | ignorate | ignorate | **BUG corretto** (§2.6) |
| 23 | Scalper calcio | auto-mode tetto sessioni `scalper_service.py:449-455` conta sessioni con processo di ogni modalita' | — | — | uguale nei due modi; e' un tetto di PROCESSI/connessioni (capacita', cantiere B), non un numero di rischio. Il conflitto paper↔live e' gia' bloccato (`conflitto_modalita`). Non toccato |
| 24 | Scalper calcio | cap evento/globale per sessione (`scalper_session.py:1360-1375`) | una sessione = una modalita' | idem | uguale (mai sommati) |
| 25 | Tutti tennis | ordini MANUALI dal Terminale sotto il minimo (`tennis_live_order_worker._do_place`, `min_stake_rules`) | rifiutati | rifiutati | uguale; l'importo lo scrive l'utente, non un calcolo: la regola del 28/09 NON si applica (se la vuole anche qui: §8 D-3) |

## 5. Cose trovate FUORI perimetro (non toccate, con proposta)

- **F-1 (Safe tennis, `execution.py`, file di D1).**
  - *Il difetto*: a canale spento (la configurazione di oggi) Safe tennis in paper riempie «in
    casa» e istantaneamente (`E.paper_fill`), senza bet delay, coda e parziali. E' il §7.14, e
    viola l'ordine del coordinatore.
  - *In live* va in REST con il place-and-trim sotto il minimo: nessuno dei due passa dal runner
    tennis.
  - *Proposta*:
    1. accendere di serie `MOTORE_ORDINI_CANALE_TENNIS=1` e `SAFE_TENNIS_ORDINI_VIA_CANALE=1`: la
       strada e' certificata sul profilo rapido, 14/14, e la paper e' flumine;
    2. oppure far dichiarare a `execution.place` un paper tennis senza canale come «non eseguito:
       paper tennis senza percorso flumine».
  - In entrambi i casi sotto il minimo vale la regola del 28/09 (2,00) solo sul canale. Con il REST
    live resta 1,22 esatto via place-and-trim: da allineare nello stesso intervento, per es. con
    `porta_al_minimo_apertura` quando la riga e' tennis. Lo decide il coordinatore con D1.
- **F-2 (R-2, parte Safe, `bot_service.py`).** Salvare `ev["cor"]` in `meta.canale_cor` alla prima
  vista e aggiungerlo ai ref di `ref_di_riga`/`X.reconcile_decision`. Cosi' una riga LIVE rimasta
  senza eventi oltre la scadenza si ritrova su Betfair per ref. Il runner lo manda da oggi (§2.7).
- **F-3 (R-3).** La partita agganciata da un comando vive solo nel piano del runner
  (`esecutore_tennis.follow_sintetico`, «MAI scritta nel DB», per scelta del 25/09). Il Terminale
  legge `tennis_live_follow`.
  - Proposta, senza scrivere follow finti: il runner pubblica sul canale 47332 l'elenco delle
    partite da comando (`session.comandi`), e il Terminale le mostra con l'etichetta «da comando».
  - Tocca il ciclo di vita del follow e la UI (cantiere A / UI): non fatto.
- **F-4.** `motore_ordini.py` e `trasporto_rapido.py` sono condivisi con altri cantieri (Omega C,
  B): le mie righe sono minime e marcate «28/09». Possibili conflitti di merge.

## 6. Test

Comando (dal worktree):

```
.venv/Scripts/python.exe -m pytest Betfair/stream/tennis_live/tests Betfair/stream/tennis_scalper/tests \
  Betfair/stream/tests/test_motore_ordini_2026_09_24.py Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py \
  Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py Betfair/stream/tests/test_porta_banco_f4_2026_09_24.py \
  Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py Betfair/stream/tests/test_submin_nucleo_2026_09_17.py \
  Betfair/stream/tests/test_submin.py Betfair/safe_strategy/tests/test_safe_tennis_canale_f8_2026_09_25.py \
  Betfair/stream/tests/test_scalper_*.py Betfair/stream/tests/test_theta_*.py Betfair/stream/tests/test_sniper_*.py \
  Betfair/stream/tests/test_resilienza_rete_fix_c_scalper_2026_09_26.py Betfair/stream/tests/test_risk_semaphore_2026_07_11.py \
  -q -p no:cacheprovider
```

- Esito: **1351 passed**, 0 failed, 1 min 47 s (`cantiere_d2/pytest_toccati.txt`).
- Piu' i file Safe canale/porta/strada + `test_local_channel.py`: **172 passed**, 54 s.
- Nella prima corsa `test_profilo_rapido_safe_tennis_sulla_registrazione_vera` e' diventato rosso
  su R8, come atteso (asseriva il rifiuto). L'ho corretto nello scenario del banco; ora e' verde,
  16 s.
  - E' un test gia' esistente della suite che gira `trasporto_rapido` sulla registrazione
    35795993: e' l'unico «replay» toccato. Non ho lanciato `certifica`.

**Falsificazione** (`AUDIT_2026-09-28/cantiere_d2/falsifica_d2.py`, esito in
`falsificazione.txt`): 18 mutazioni, **18 ROSSE**, ripristino sha1 per file, `git diff --stat` e
`git diff` identici a prima.

| Mutazione | Difetto reintrodotto |
|---|---|
| M1 | `is_flat` sulle stake (il codice di prima) |
| M2 | motore senza regola |
| M3 | esecutore senza regola |
| M4 | la regola gonfia sopra il minimo |
| M5 | ingresso dei bot rifiutato (il codice di prima) |
| M6 | paper senza blindature (il codice di prima) |
| M7 | restart forzato in paper (il codice di prima) |
| M8 | evento senza `cor` |
| M9 | esito senza `cor` |
| M10 | la chiusura si gonfia |
| M11 | evento muto sul minimo |
| M12 | lo sniper ignora l'interruttore (il codice di prima) |
| M13 | lo sniper nasce ad uscite automatiche |
| M14 | lo stop dello sniper diventa discrezionale |
| M15 | la proposta a ogni book |
| M16 | commissione per ordine (il codice di prima) |
| M17 | tetto tennis paper+live (il codice di prima) |
| M18 | riga viva dell'altra modalita' riscritta |

Le mutazioni marcate «il codice di prima» sono il ROSSO prima della correzione.

I finti sono quelli gia' esistenti e certificati: banco dell'iscrizione a caldo con Flumine e
`BetfairStream` veri, `_FakeOrder` dello sniper con `status` Enum, finti del P&L con
`simulated.profit`, `_Db` del ponte con le firme di `tennis_db`. In LIVE il `place_order` del
mercato e' una spia che non chiama Betfair.

## 7. Debiti del banco: cosa serve perche' li copra (NON lanciato)

### 7.1 Scalper calcio con lo sniper acceso (default di produzione dal 25/09)

**Oggi il banco lo esclude per costruzione.** `scalper/tools/replay_registrazioni.py`:
- `control_della_ui` ha `sniper_mode: False`;
- limite 3 del docstring: «sniper e theta non sono nel perimetro»;
- fine vita fissa KO+10' a `:1175-1182`.

**Cosa manca:**
- uno scenario `sniper` con `sniper_mode: True` nel control;
- la vita della sessione da `auto_mode.vita_sessione_s({"sniper_mode": True})` (KO+130');
- il watcher dei gol che chiama `set_line`/`set_lines` dal sidecar `.scores.jsonl`, con il
  ritardo IPS;
- i mercati `OVER_UNDER_05..85` a catalogo;
- controlli di condotta dello sniper in `scalper/certificazione.py`: flat al verde, stop 2 tick,
  timeout, proposta a uscite spente, residuo ≤ 0,30.

**Registrazioni con tutte le OU in gioco e sidecar** (`_live_raw`, lette oggi):

| Evento | Dimensione | Definizioni in gioco |
|---|---|---|
| 35674515 | 10 MB | 200 |
| 35768297 | 26 MB | 172 |
| 35760084 | 8 MB | 167 |
| 35759636 | 8 MB | 155 |
| 35768365 | 20 MB | 150 |
| 35777617 | 18 MB | 128 |
| 35797538 | 9 MB | 118 |
| 36006953 | 7 MB | 65, con recmeta |

Evitare 35784105, 35823616, 35828026 (0-4 definizioni in gioco) e 36106722 (nessuna OU).

Comando, quando lo scenario esistera':

```
python -m Betfair.stream.backtest.certifica scalper_calcio 35674515 35768297 35797538 --scenari sniper,sniper-paper --worker 1
```

Oggi `--scenari sniper` non esiste: e' il lavoro da fare, non l'ho fatto (cantiere a se').

### 7.2 tennis_pro fuori dall'erba

**Oggi.** `replay_bot.py:989,1017` istanzia il bot SENZA `competition_name`. `superficie_della_partita`
quindi dichiara `hard` (default) su ogni registrazione: il banco non ha mai visto la superficie
vera, ne' erba ne' terra.

**Registrazioni.** Solo `~/Desktop/tennis_rec/20260707` (88 partite, 7/7/2026, MATCH_ODDS +
`.score.jsonl`).
- Il torneo non e' nella registrazione.
- `tennis_markets` sul DB non ha questi eventi: `SELECT` fatta, 0 righe; la tabella parte da
  35799219.
- Dai nomi nel sidecar (es. 35790089 Barrios Vera – Simakin) ci sono partite Challenger fuori
  Wimbledon, probabilmente su terra.

**Cosa serve:**
1. una mappa evento → torneo per la cartella (es. `_tornei.json`, scritta a mano dall'utente o
   dal recorder da ora in poi);
2. `replay_bot` che la legge e passa `competition_name` a `_instantiate_bot`, come fa il runner
   (`_con_competizione`);
3. registrazioni nuove su terra/cemento: il recorder dovrebbe salvare `competition_name` in un
   sidecar.

Comando, quando 1-2 esisteranno:

```
python -m Betfair.stream.backtest.certifica tennis_pro <ev1> <ev2> --data-dir "C:/Users/Admin/Desktop/tennis_rec/20260707" --scenari base,gate-aperto,parziali,riavvio --worker 1
```

**Da rilanciare comunque (coordinatore, uno alla volta).** I risultati di tutti i replay tennis in
PAPER cambiano per §2.2 (blindature .it):

```
python -m Betfair.stream.backtest.certifica safe_tennis 35795993 --scenari rapidi --trasporto entrambi --worker 1 --data-dir "C:/Users/Admin/Desktop/tennis_rec/20260707"
```

- Poi `tennis_scalper`, `tennis_pro`, `tennis_flb`, `tennis_swing` sulla stessa cartella,
  `--scenari tutti`.
- Poi `scalper_calcio` (per lo sniper nulla cambia nel banco: e' escluso).

## 8. Decisioni per l'utente (solo cio' che cambia una regola di trading)

- **D-1 [SUPERATA dalla seconda consegna, §11: era un bug, corretto]** Chiusure dei bot tennis
  sotto il minimo. Il brief dice «le chiusure restano esatte, non
  gonfiare mai una chiusura». Nel codice (regola del 17/09, `condotta_ordini.size_legale`) le
  coperture dei bot tennis in live sono SEMPRE state gonfiate al gradino da 0,50 sopra.
  - Esempio: chiudere 2,02 EUR → piazza 2,50 (0,48 di sovra-copertura).
  - Il «chiudi ora» di una posizione non multipla di 0,50 finisce quindi «con residuo» dopo la
    grazia.
  - Da oggi il paper fa lo stesso.
  - Proposta: chiusure a importo esatto con il place-and-trim (esiste gia' per lo scalper tennis,
    `_place_exact`, spento in `tennis_runner` in attesa di certificazione). E' un cantiere a se'.
- **D-2 Sniper a uscite manuali (default).** Con l'interruttore spento lo sniper non prende mai
  profitto da solo.
  - Esempio: entra BACK Under 10 EUR a 3,40; il prezzo scende a 3,35 (il tick del suo verde, circa
    +0,15 EUR bloccabili).
  - Il bot NON chiude: emette la proposta «chiudi LAY 10,15 a 3,35».
  - Se l'utente non approva in tempo, la posizione esce solo per stop (quota a 3,50, perdita circa
    −0,30), per timeout dopo 5 minuti o a fine finestra.
  - Per uno sniper «a 1 tick» e' quasi sempre troppo lento.
  - Due alternative:
    1. accendere le uscite automatiche per lo scalper/sniper (interruttore esistente, per sessione);
    2. rendere lo sniper «sempre automatico» come lo scalper tennis (`BOT_USCITE_SEMPRE_AUTOMATICHE`).
- **D-3 (facoltativa)** Ordini MANUALI del Terminale tennis sotto il minimo: oggi rifiutati (paper e
  live). La regola del 28/09 riguarda le aperture calcolate dai bot. Portarli al minimo anche a
  mano? Proposta: no, l'importo scritto dall'utente non si cambia.

## 9. Cosa NON ho fatto / cosa NON ho potuto verificare

**Non fatto:**
- F-1 (Safe tennis REST/paper di casa), F-2 (R-2 lato Safe), F-3 (R-3): fuori perimetro, §5;
- scenario `sniper` del banco e competizione nel banco tennis: §7;
- theta non allineato all'interruttore: ha la sua conferma, fuori richiesta.

**Non verificato:**
- il vivo: nessun runner, nessuna app;
- il cablaggio di `applica_uscite_automatiche` sullo sniper dentro `run_session`: provato sulla
  funzione e sull'istanza vera, non con una sessione intera;
- la ripartizione della commissione per bot quando piu' strategie operano sullo stesso mercato:
  Betfair nette per CONTO, noi per strategia, come prima;
- i replay completi del banco dopo §2.2/§2.3: vanno rilanciati (§7.2);
- la parte R-2 lato Safe: il `cor` arriva nell'evento, nessuno lo usa ancora.

## 10. Controlli dal vivo in paper al prossimo avvio

| Controllo | Dato atteso | Dove leggerlo |
|---|---|---|
| Apertura Safe tennis sotto il minimo (canale acceso) | ordine a 2,00; evento con `portata_al_minimo {chiesto 1,xx, piazzato 2,0}`; riga Safe non in errore; `meta.esecuzione.size_richiesta` 1,xx, `size_abbinata` ≤ 2,00 | log runner tennis `[motore]`, diario `_diario_ordini/tennis/<data>.jsonl`, `safe_strategy_trades.meta` |
| Evento `order` col `cor` | `cor` = customerOrderRef del diario (riga `ordine`) | diario tennis |
| Bot tennis in paper: size | ingressi ≥ 2,00 BACK / ≥ 0,50 LAY, BACK multipli di 0,50 | `tennis_live_orders` (`mode='paper'`, `source=<bot>`) |
| Bot tennis in paper non piatto + arm/disarm altrui oltre 180 s | `restart_blocked` CRITICAL «restart PAPER bloccato…», nessun `restart_forced` | `tennis_bot_activity` |
| Commissione paper a mercato chiuso | somma `commission` per mercato e bot = 5 % del netto positivo | `tennis_live_orders` |
| Scalper con sniper, uscite spente (default) | `uscita_proposta motivo=target` nell'attivita', nessuna chiusura a target; stop/timeout chiudono da soli | `scalper_activity` (o log sessione) |
| Freno sullo scalper con lo sniper in verde | niente «posizione NON flat dopo 30 s» se la posizione e' verde; `error` null | `scalper_control.error`/`stats` |
| Tetto auto-mode tennis dopo cambio modalita' | le partite dell'altra modalita' non occupano posti | `tennis_bot_service_control.stats.auto` |

---

# SECONDA CONSEGNA (28/09 sera)

Base: la prima consegna, accettata dal coordinatore, piu' `origin/master` `512db64` (cantiere A)
unito nel ramo del worktree.

## 11. D-1 non era una decisione: CHIUSURE ESATTE al centesimo (bug corretto)

**La regola**, permanente e dell'utente: «le chiusure devono sempre essere perfette e spalmare il
profitto o la loss su entrambe le selezioni».

**Il difetto**:
- `condotta_ordini.size_legale(riduce_liability=True)` gonfiava le coperture di pro, FLB e swing
  al gradino da 0,50 sopra (2,02 → 2,50);
- `tennis_runner` teneva SPENTE le uscite esatte dello scalper tennis (`exact_exits`, «⊘ in
  attesa di certificazione»).

**La correzione** usa la macchina che esiste gia'. Nessuna copia della sequenza.

- `condotta_ordini` (modulo comune ai 4 bot):
  - `size_legale(copertura)`: passa solo cio' che Betfair accetta DIRETTAMENTE (`diretta_ok`:
    BACK ≥ 2,00 e multiplo di 0,50, LAY ≥ 0,50). Il resto NON si gonfia mai.
  - `spezza_esatta`: una parte diretta (BACK al multiplo di 0,50 per difetto) e un resto; la somma
    e' sempre la size chiesta.
  - `UsciteEsatte`, sulla macchina `trading/submin.py` (`SubminState` + `advance_submin` +
    `FlumineSubminOps`), la stessa di `TennisScalperStrategy._place_exact`/`_drive_submins`:
    - la parte diretta passa dal `_place` del bot, con le stesse guardie;
    - il resto va col place-and-trim: parcheggio legale da 2,00 a quota non abbinabile (BACK
      1000 / LAY 1,01), riduzione con `sizeReduction`, rimpiazzo alla quota vera;
    - anti-cascata con gli STESSI numeri dello scalper tennis: 30 s fra due sequenze per
      selezione, sull'orologio del mercato del bot; rinuncia DICHIARATA dopo 5 sequenze FALLITE.
  - `OrdineComposto`: la chiusura vista dal bot come UN ordine, con le chiavi che i bot gia'
    leggono (`size_remaining`, `status` Enum, `side`, `order_type`...). L'esposizione la legge
    sempre il blotter.
- Bot `tennis_flb_bot.py`, `tennis_pro_bot.py`, `tennis_swing_bot.py`:
  - una copertura non diretta va a `UsciteEsatte.piazza`;
  - `avanza` gira a ogni book;
  - `_cancel` annulla anche una chiusura esatta, fermandone la sequenza.
  - Il cablaggio e' fatto con ancore esatte da `cantiere_d2/strumenti/cabla_uscite_esatte.py`:
    +25 righe per bot.
- `tennis_runner._instantiate_bot`: `exact_exits=True` per lo scalper tennis in PAPER e in LIVE.
- Banco: `certificazione_bot.riga_ordine` riconosce l'ordine SOSTITUTO del gradino 3 (chiave
  `sostituto`, stessa regola del banco dello scalper calcio `scalper/certificazione.py`). B8 non lo
  conta piu' come «piazzato sotto il minimo», che era la causa per cui il 17/09 le uscite esatte
  erano rimaste spente.
- `test_submin_contratto_chiamanti`: `condotta_ordini.py` registrato come chiamante del nucleo.

**Il runner paper sa eseguire la sequenza come Betfair?** Verificato sul codice di flumine 2.13.11
e con un test end-to-end sul runner paper VERO (`test_cantiere_d2_chiusure_esatte_2026_09_28.py`):
- parcheggio: `SimulatedOrder.place`, non abbinato a 1000;
- riduzione: `SimulatedOrder.cancel` legge `update_data["size_reduction"]` (`simulatedorder.py:286-303`);
- rimpiazzo: `SimulatedExecution.execute_replace` (`simulatedexecution.py:106-160`), che annulla il
  residuo e piazza il sostituto con la size annullata alla quota nuova, sullo stesso client.

Nel test la selezione chiude con «se vince» = «se perde» al centesimo, e la sequenza e' quella di
Betfair: parcheggio 2,00 a 1000, `size_cancelled` 2,00 fra taglio e rimpiazzo, sostituto
abbinato al resto.

**Dove il paper NON e' fedele** (limite di flumine, non corretto; proposta sotto):
1. `SimulatedOrder.place` non applica NE' il minimo di giurisdizione NE' la guardia
   `INVALID_PROFIT_RATIO`. Betfair rifiuta una riduzione o un rimpiazzo che rende il 20 % in meno o
   il 25 % in piu' del «giusto» (Developer Program, «Why am I receiving the INVALID_PROFIT_RATIO
   error?»: <https://support.developer.betfair.com/hc/en-us/articles/360010423978>). Esempio: un
   resto da 0,13 a 1,06.
   - In paper passa sempre, in live puo' fallire: paper piu' generoso.
   - Proposta: un trading control di flumine, uguale in paper e live, che rifiuta PRIMA una
     riduzione o un rimpiazzo fuori banda (la formula c'e' gia': `live_order_build.
     INVALID_PROFIT_RATIO_MIN/MAX`).
2. Rimpiazzo IN GIOCO di un residuo sotto il minimo (reperto 25 del 17/09, Mike live: 111
   `CANCELLED_NOT_PLACED` su 111):
   - Betfair lo ha rifiutato, flumine lo esegue;
   - codice interno mai letto (`submin.esito_istruzione` ora lo registra);
   - finche' non si conosce il codice, il live puo' lasciare scoperto il resto (< 0,50, o l'intera
     chiusura se era sotto 2,00 BACK);
   - `UsciteEsatte` lo DICHIARA (`uscita_esatta_abort`) e il bot ritenta al piu' ogni 30 s, per 5
     volte.
   - Proposta: preferire il percorso A del nucleo (`pianifica_submin`: parcheggio ALLA quota
     target quando non e' abbinabile, nessun rimpiazzo). Per una chiusura aggressiva non si puo';
     serve la prova dal vivo col codice interno.

**Scalper calcio, sniper, theta: le uscite sono esatte di serie in produzione?**
- Il solo punto d'ingresso di produzione e' `scalper_session.run_session`, lanciato da
  `scalper_service` e da `desktop/main.js:369`:
  - maker: `VALIDATED_PARAMS["exact_exits"]=True` (`scalper_session.py:58`);
  - sniper: `sniper_params["exact_exits"]=True` (`:920`);
  - theta: `exact_exits=True` (`:991`).
- Il default False dei costruttori vale solo per chi non lo passa:
  - `run_scalper_live.py:255`: True;
  - `run_scalper.py`, `run_theta.py` (False dichiarato), `tune_tennis.py`, `run_tennis_scalper.py`:
    strumenti di ricerca, non lanciati dall'app.
- Scalper tennis: da oggi True dal runner (sopra).
- **Eccezioni RESIDUE, di serie** (regole anti-cascata misurate, che l'utente deve conoscere):
  - `_place_exact` di scalper, scalper tennis e sniper SALTA il resto quando:
    - e' < 0,05 EUR;
    - in FLATTENING (inseguimento del book) esiste gia' una parte diretta;
    - non sono passati 30 s dall'ultima sequenza;
    - sono gia' state fatte 5 sequenze nel ciclo.
  - Quel resto resta come micro-residuo accettato (tolleranza del bot 0,30 / 0,02).
  - Riferimenti: `tennis_scalper_bot.py:2417-2435`, `sniper_bot.py:812-818` e analoghi nello
    scalper calcio.
  - Lezione del 02/07: 2.355 sequenze in una partita.
  - Non le ho toccate: rimuoverle cambia una regola di rischio (§13).

## 12. Mutazioni che non si applicavano al coordinatore

- **(a) motore, `and not riduce`**: nel file ci sono DUE righe `if azione == "place" and not
  riduce:` (la mia, prima della regola del minimo, e quella storica del place-and-trim), quindi una
  sostituzione per testo trova 2 occorrenze.
  - La mia M10 colpisce la prima: il test `test_chiusura_sotto_il_minimo_non_si_gonfia_mai` e
    quello di riduzione esistente diventano ROSSI.
  - Il test verifica che una chiusura BACK 1,20 esca a 1,20 e senza `portata_al_minimo`.
- **(b) sniper, `pos.proposta == motivo`**: il file e' CRLF, e una mutazione scritta con `\n` non
  si applica.
  - La mia M15 (CRLF gestito) e' ROSSA su `test_spento_la_proposta_e_una_sola_anche_su_piu_book`.
  - Aggiunto `test_ciclo_nuovo_proposta_nuova`: chiuso il ciclo, il ciclo dopo emette la SUA
    proposta.
- Tutte le mutazioni sono in `cantiere_d2/falsifica_d2.py` con la gestione del CRLF, per il
  rilancio.

## 12-bis. Lo scenario SNIPER del banco (realizzato) e i replay da rilanciare

**Il banco non copriva lo sniper**: il control aveva `sniper_mode: False`, la fine vita era fissa a
KO+10' e il watcher della linea girava su un thread che il turno dell'orologio non regge.

Cosa ho fatto (perimetro allargato dal coordinatore: `replay_registrazioni.py` + registro):
- `scalper_session.applica_linea_sniper`: il corpo del watcher `sniper-line`, estratto TALE E
  QUALE (nessun cambio di logica); il thread di produzione la chiama come prima.
- `replay_registrazioni`:
  - scenari `sniper` (LIVE), `sniper-paper`, `sniper-uscite-auto`;
  - vita della sessione di produzione (`auto_mode.vita_sessione_s`);
  - riga `live_now` ricostruita dal sidecar `.scores.jsonl` (`score_home/score_away/minute`, le
    colonne che il runner scrive in `live_now`, con il ritardo IPS gia' nel `ts_ms`);
  - il thread `sniper-line` non parte (`_ThreadingSessione`) e la funzione di produzione la
    chiama il ponte del motore ogni 15 s di mercato;
  - lo sniper e' una strategia COMPAGNA del maker: i controlli del maker restano sul maker;
  - controlli propri Z1-Z4 dello sniper (`_Banco.controlli_sniper`):
    - Z1 legalita' .it, sostituti esclusi;
    - Z2 piatto o dichiarato a fine sessione;
    - Z3 nessun verde da solo a uscite manuali;
    - Z4 chiavi della proposta;
  - le sollecitazioni Z* sono nel `sollecitati` del referto, non nella tabella dei 22 controlli
    registrati di `certificazione.py`.
- `registro_bot.scalper_calcio.mercati`: tutte le linee OU 05-85.
- **Lentezza del banco scoperta e corretta** (stesso risultato, test di equivalenza):
  - `certificazione._s5` rifaceva, a ogni giro, la somma delle sovrapposizioni con TUTTI i buchi
    della registrazione per OGNI coppia di heartbeat;
  - con la vita dello sniper (KO+130') il 99 % del tempo del motore finiva li' (campionato);
  - il primo tentativo e' andato in `BancoBloccato` dopo 120 minuti reali;
  - ora `_CoperturaBuchi` (integrale della copertura, O(log n), esatta anche con buchi sovrapposti
    o fuori ordine) e `_Orologio.buchi` incrementale;
  - lo stesso replay ora dura **73 s**.
- **Prova** (un solo replay, `--worker 1`, per verificare lo scenario):
  - comando: `certifica scalper_calcio 35796477 --scenari sniper`;
  - esito OK, 84.338 tick, 15.682 decisioni, 0 violazioni, sessione `done`;
  - 142 righe `live_now`, linea aggiornata 2 volte (2 gol);
  - su questa partita lo sniper NON ha mai sparato (gate S16 non verdi), quindi Z1-Z4 sono
    sollecitati a vuoto. Serve una partita dove spara: le 8 del §7.1.
  - Referto: `cantiere_d2/smoke_sniper_35796477.txt`.

**Comandi da rilanciare, uno per bot, nell'ordine, dalla radice del repo.**
- I tempi sono misurati dove indicato, stimati altrove.
- La cartella tennis e' `C:/Users/Admin/Desktop/tennis_rec/20260707` e la partita 35794049
  (Sinner-Struff, quella dei referti del 17/09; erba).

```
# 1. tennis_scalper   (uscite esatte ora ACCESE; paper = live sulle blindature)   ~1-2 min stimati
python -m Betfair.stream.backtest.certifica tennis_scalper 35794049 --data-dir "C:/Users/Admin/Desktop/tennis_rec/20260707" --scenari base,live,gate-aperto,parziali --worker 1
# 2. tennis_pro                                                                   ~1-2 min stimati
python -m Betfair.stream.backtest.certifica tennis_pro 35794049 --data-dir "C:/Users/Admin/Desktop/tennis_rec/20260707" --scenari base,live,gate-aperto,parziali --worker 1
# 3. tennis_flb                                                                   ~1-2 min stimati
python -m Betfair.stream.backtest.certifica tennis_flb 35794049 --data-dir "C:/Users/Admin/Desktop/tennis_rec/20260707" --scenari base,live,gate-aperto,parziali --worker 1
# 4. tennis_swing                                                                 ~1-2 min stimati
python -m Betfair.stream.backtest.certifica tennis_swing 35794049 --data-dir "C:/Users/Admin/Desktop/tennis_rec/20260707" --scenari base,live,gate-aperto,parziali --worker 1
# 5. safe_tennis (profilo rapido, entrambi i trasporti; R8 = apertura al minimo) ~15 s (misurato 25/09: 14 s)
python -m Betfair.stream.backtest.certifica safe_tennis 35795993 --scenari rapidi --trasporto entrambi --worker 1 --data-dir "C:/Users/Admin/Desktop/tennis_rec/20260707"
# 6a. scalper_calcio SENZA sniper (maker, KO+10')                                ~1-2 min stimati
python -m Betfair.stream.backtest.certifica scalper_calcio 35760084 --scenari base,paper --worker 1 --data-dir "C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/_live_raw"
# 6b. scalper_calcio CON sniper (KO+130')                                        ~1,5 min per partita per scenario (misurato 73 s su 35796477)
python -m Betfair.stream.backtest.certifica scalper_calcio 35674515 35768297 35797538 --scenari sniper,sniper-paper,sniper-uscite-auto --worker 1 --data-dir "C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/_live_raw"
```

- Nei replay tennis in `live` e in paper le coperture non dirette partono ora col place-and-trim
  (ordini SOSTITUTI).
- B8 li riconosce. Se B8 o K5 diventano rossi su un sostituto, e' un difetto del mio lavoro da
  rimandarmi.
- Sulla partita 35794049 il 17/09 era uscito K5 0,31 contro 0,30 per l'over-hedge: con le chiusure
  esatte deve sparire. E' il confronto da fare numero per numero.

## 13. Decisioni per l'utente (aggiornate)

- D-1: CHIUSA (era un bug, corretto).
- D-2 (sniper e interruttore): portata all'utente dal coordinatore, invariata; ci lavora il
  cantiere N.
- D-3: confermata dal coordinatore (ordini manuali sotto il minimo rifiutati).
- **D-4 (nuova)**: le eccezioni anti-cascata del §11. Una chiusura esatta NON e' garantita:
  - a) resto < 0,05 EUR;
  - b) durante l'inseguimento di un flatten, se una parte diretta e' gia' partita;
  - c) oltre 5 sequenze fallite per ciclo o selezione.
  In quei casi resta un micro-residuo dichiarato, al massimo 0,30 EUR di sbilancio. Toglierle
  riapre il rischio cascata. Proposta: tenerle e mostrarle nella scheda del bot come «residuo
  accettato».

## 14. Seconda consegna: file, test, falsificazione, integrazione

**Git.** Sul ramo del worktree ci sono solo commit LOCALI, mai pushati, fatti su ordine del
coordinatore per il riallineamento:
- `f5f88d5`: prima consegna;
- merge di `origin/master` `512db64` (cantiere A): conflitto in `tennis_bot_service.py` (esclusione
  in `_escludi`), risolto tenendo ENTRAMBE le righe: la mia (riga dell'altra modalita') e quella
  di A (partita finita);
- `1350e6e`: seconda consegna;
- merge di `origin/master` `949c094`: pulito.

Da allora master e' andato a `03e484d`, che tocca solo documenti (G2 e cronostoria).
L'ultima modifica ai test di `test_banco_scalper_sniper` e' nel working tree, non committata.

**Consegna**: `AUDIT_2026-09-28/CANTIERE_D2_su_master.patch`.
- Contenuto: `git diff --binary origin/master -- Betfair/`, 32 file, prima e seconda consegna
  insieme, SOLO miei.
- Verifiche:
  - la pre-immagine e' `origin/master` per costruzione;
  - `git apply -R --check` sul worktree = OK (la post-immagine e' il mio albero);
  - i due soli commit di master successivi al mio merge non toccano nessuno dei 32 file.

**File toccati in questo giro** (oltre a quelli della prima consegna):
- `tennis_scalper/condotta_ordini.py`: `diretta_ok`, `spezza_esatta`, `OrdineComposto`,
  `UsciteEsatte`;
- `tennis_scalper/tennis_flb_bot.py`, `tennis_pro_bot.py`, `tennis_swing_bot.py`;
- `tennis_live/tennis_runner.py`: `exact_exits`;
- `tennis_live/certificazione_bot.py`: `sostituto`, B8;
- `tennis_live/tennis_bot_service.py`: solo la risoluzione del merge;
- `scalper/scalper_session.py`: `applica_linea_sniper`, `SNIPER_LINEA_OGNI_S`;
- `scalper/tools/replay_registrazioni.py`: scenari sniper;
- `scalper/certificazione.py`: `_CoperturaBuchi`;
- `backtest/registro_bot.py`: mercati.

Test:
- aggiornati: `test_condotta_ordini_2026_09_17.py`, `test_chiudi_ora_bot_tennis_2026_09_24.py`,
  `test_submin_contratto_chiamanti_2026_09_17.py`, `test_cantiere_d2_minimo_e_specchio_2026_09_28.py`,
  `test_sniper_uscite_automatiche_2026_09_28.py`;
- nuovi: `tennis_live/tests/test_cantiere_d2_chiusure_esatte_2026_09_28.py` (17),
  `tests/test_banco_scalper_sniper_2026_09_28.py` (31).

Strumenti (fuori dal patch):
- `cantiere_d2/strumenti/cabla_uscite_esatte.py`, `diagnosi_sniper.py`, `campiona_sniper.py`;
- referti `cantiere_d2/smoke_sniper_35796477.txt`, `falsificazione.txt`, `pytest_toccati.txt`.

**Test** (stesso comando del §6 piu' `test_fine_evento_2026_09_28.py` di A,
`test_banco_scalper_sniper`, `test_registro_bot`):
- **1.466 verdi, 1 rosso**, 1 min 55 s;
- il rosso e' `test_submin_contratto_chiamanti::test_nessun_chiamante_nuovo_non_registrato` e NON
  e' mio:
  - lo porta master: `Betfair/mike/porta_ordini.py` (cantiere D1) chiama il place-and-trim e non
    e' registrato nel censimento (`git show origin/master:...` = 0 occorrenze);
  - e' rosso anche su master puro;
  - va registrato da D1: non l'ho fatto io, e' il suo file.
- I test di fine evento di A sono inclusi e verdi: `tennis_live/tests` contiene quelli del tennis.

**Falsificazione**: `falsifica_d2.py`, 28 mutazioni, **28 ROSSE**, ripristino sha1 per file,
`git diff` identico a prima.

| Mutazione | Difetto reintrodotto |
|---|---|
| M19 | copertura gonfiata al gradino, com'era |
| M20 | bot non instradato sull'uscita esatta |
| M21 | resto perso |
| M22 | sequenza ferma |
| M23 | annullo che non ferma la sequenza |
| M24 | anti-cascata spenta |
| M25 | scalper tennis senza uscite esatte, com'era |
| M26 | S5 veloce ma sbagliata |
| M27 | linea sniper di una sotto |
| M28 | `live_now` vuota nel banco |

Le M1-M18 della prima consegna sono ancora ROSSE.

**Non verificato (seconda consegna):**
- il comportamento di Betfair live su riduzione e rimpiazzo del place-and-trim in gioco
  (INVALID_PROFIT_RATIO, reperto 25);
- replay tennis e scalper completi con le chiusure esatte: comandi al §12-bis;
- lo sniper che spara davvero in uno scenario del banco: sulla partita provata i gate S16 non si
  sono mai aperti;
- theta: non ha lo scenario.

## 15. Terza consegna (revisione del coordinatore) e riallineamento

**Base:** origin/master `66a8672`. Merge `77cd96c` nel worktree; l'unico conflitto era
`test_submin_contratto_chiamanti_2026_09_17.py`, dove ho tenuto sia la riga D1-bis
(`Betfair/mike/porta_ordini.py`) sia la mia (`Betfair/stream/tennis_scalper/condotta_ordini.py`),
ognuna col suo commento. Patch `CANTIERE_D2_su_master.patch` = `git diff --binary origin/master -- Betfair/`:
33 file, +2528/-190, 182957 byte, sha1 `5567EB70...`. `git apply --check -R` passa pulito.
Test mirati (tennis_live, tennis_scalper, trading, scalper, contratto place-and-trim e
test_r3_freno_unico): **874 passed**.

**(a) Test che passano SOLO dal bot**
(`tennis_live/tests/test_cantiere_d2_chiusure_via_bot_2026_09_28.py`). Book veri al Flumine
del runner paper, poi `process_market_book` del bot vero; il test non chiama mai `avanza` o
`_drive_submins`. Per flb/pro/swing e per lo scalper tennis verifica tre cose:
- l'abbinato e' esatto al centesimo;
- nessun ordine resta vivo a mercato, parcheggio compreso;
- se vince = se perde entro 0,01.

Mutazioni: M29-M32 (`avanza` -> `pass` in ciascun bot, `_drive_submins` -> `pass`) sono ROSSE.

**(b) Scoperto: quanto e per quanto tempo; chi lo dice.**

Quanto resta scoperto durante un'attesa:
- il resto sotto il minimo, cioe' fino a 0,49 EUR;
- tutta la chiusura se e' interamente sotto il minimo (BACK <= 1,99, LAY <= 0,49).

Correzione di D-4: il valore massimo di 0,30 scritto prima era sbagliato.

Tempi: la prima sequenza parte subito. Fra una sequenza e la successiva sullo stesso
mercato/selezione l'attesa e' di 30 s, poi, dopo ogni sequenza fallita, 60, 120, 240 e 300 s
(tetto), e resta a 300 s. **La rinuncia non e' mai definitiva**: il conteggio si azzera al
primo successo.

Chi lo dice: righe attivita' `CRITICAL`, con lo scoperto in EUR, il lato, i secondi alla
prossima prova e "Puoi chiudere a mano dal Terminale":
- `uscita_esatta_attesa`, una per ogni blocco;
- `uscita_esatta_abort`, a ogni fallimento.

Prima c'era una rinuncia permanente dopo 5 sequenze con una sola riga non critica.

Mutazioni: M24 e M33-M35 ROSSE.

**(c) Esiti della revisione.**
1. Punto 1: vedi (b), solo in `UsciteEsatte`; lo scalper non e' toccato.
2. Punto 2: `OrdineComposto.completa` (`size_remaining <= 0`). FLB decide "verde" dall'abbinato.
   Il test su una sequenza abortita a meta' non conta il verde; M36 ROSSA.
3. Punto 3: il B8 `sostituto` vale solo per la catena legittima: ordine precedente nello stesso
   Trade, stesso lato, quota di parcheggio (BACK 1000 / LAY 1,01), size >= 2,00, ridotto > 0.
   Un sotto-minimo secondo nel Trade senza parcheggio prima viola B8 (5 casi); M37 ROSSA.
4. Punto 5: tutte le righe che ho aggiunto sono ASCII.
5. Punto 4, **le uscite dello sniper** (`scalper/sniper_bot.py`, righe della base attuale).
   NON corrette: e' perimetro del cantiere N.

| Uscita | file:riga | Passa dall'interruttore? |
|---|---|---|
| appiattimento per divergenza del registro / force-flat di sessione | 402-412 | no, automatica |
| timeout `max_pos_s` | 428-430 | **no**: `_begin_flatten` diretto |
| force_flat / fine finestra | 432-433 | no, automatica |
| stop | 454-457 | no, automatica |
| target (verde) | 466-474 | **si'**: `_proponi_uscita` |
| chiusura parziale (nw/nl divergenti) | 497-501 | no, automatica |
| submin abortito con abbinato | 983-985 | no, appiattimento automatico |

Tre controlli non sono uscite: bloccano solo i NUOVI ingressi.
- `profit_target` (517-519);
- cancello di fine partita (529-531);
- tetto perdite `_loss_capped` (551-557).

**Rossi dopo il merge precedente:** i 4 di `test_r3_freno_unico` (Mike) e il contratto
place-and-trim non erano miei. Su `66a8672` sono verdi. `test_latenza_logica_comando_place_sotto_20_ms`
dipende dal carico: e' verde da solo.

**Script di falsificazione:** `AUDIT_2026-09-28/cantiere_d2/falsifica_d2.py` (M1-M37, gestisce
CRLF; argv = filtro per nome). Il ripristino si verifica con stat e sha1.

