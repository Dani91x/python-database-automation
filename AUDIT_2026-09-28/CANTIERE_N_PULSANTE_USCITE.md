# CANTIERE N — USCITE: UN PULSANTE PER OGNI BOT (28/09/2026)

Delegato Opus, worktree `.claude/worktrees/agent-a29743622286cd394` su `150bd46`. Lavoro NON committato.
DB `dqbwaocvlzbxfrpacsac` letto SOLO con `SELECT` (query in §A.0). Nessun replay, nessuna app, nessun
processo nuovo.

Ordine dell'utente (28/09, testuale): «TUTTI I BOT DEVONO AVERE LA POSSIBILITA' DI USCITE MANUALI,
OVVERO APPROVATE DA ME, OPPURE, TOTALMENTE AUTOMATICHE! SERVE UN PULSANTE […] OGNI BOT, PER ORA, DEVE
PASSARE DA ME, IO APPROVO LE USCITE; QUANDO MI FIDERO', LI LASCERO' LAVORARE IN AUTOMATICO.»

---------------------------------------------------------------------------------------------------

# PARTE A — AUDIT (consegnabile da sola)

Fonti: codice di oggi riga per riga (quattro letture indipendenti in sola lettura, verificate a
campione da me: `engine.py:2204/2208/2219/2293`, `omega_proposte.py:79/250/446/1046`,
`scalper_bot.py:446/1347/1389/1627/1713/1826`, i tre bot tennis), DB in sola lettura, referti
`AUDIT_2026-09-25/USCITE_AUTOMATICHE_PER_BOT.md`, `USCITE_MANUALI_DEFAULT.md`, `TENNIS_AUTO_MODE.md`.
Numeri di riga = codice di BASE `150bd46` (prima delle mie correzioni, salvo dove detto).

## A.0 Valore dell'interruttore OGGI sul DB (SELECT, 28/09 ~16:30)

| Tabella.chiave | Valore | Stato riga |
|---|---|---|
| `mike_control.params.uscite_automatiche` | `false` | `stopping` (26/09 17:40Z) |
| `safe_strategy_control.params.uscite_automatiche` | `{base,esatto,punta,tennis,model: false}`, `tennis_exit_approval=true` | `stopping` |
| `omega_control.params.uscite_protezione` | assente → codice = `avvisa_e_proponi` (manuale) | `stopping` |
| `scalper_service_control.params.uscite_automatiche` | `false` | `running` (26/09) |
| `scalper_control.params.uscite_automatiche` | `false` su TUTTE le 57 righe | misto |
| `tennis_bot_service_control.uscite_automatiche` | `false` per swing/scalper/pro/flb | swing/pro/flb `running`, scalper `stopping` (26/09) |

Oggi il DB e' tutto MANUALE (la migrazione `uscite_manuali_default_2026-09-25.sql` e' applicata).
Ma nel codice di base NESSUN bot lo riporta a manuale da solo a un riavvio (A.2): un «automatico»
scelto in una sessione sopravvive a tutte le sessioni dopo.

## A.1 Tabella per bot

Legenda uscite: **P→** = in manuale diventa PROPOSTA · **AUTO** = parte da sola anche in manuale ·
TP = trading in profitto · TL = trading in perdita · PROT = protezione.

| Bot | Interruttore backend (chiave · lettura · default codice) | Riavvio app (base) | Pulsante a schermo (base) | Uscite che diventano proposta | Uscite di TRADING che chiudono da sole anche in manuale | Dove vede/approva la proposta; se nessuno risponde | Verdetto |
|---|---|---|---|---|---|---|---|
| **omega** | `omega_control.params.uscite_protezione` (`automatico`/`avvisa_e_proponi`); default `omega_config.py:311` = avvisa; letto a ogni `run_once` (`omega_service.py:7360` → `omega_proposte.py:250 modo_uscite`, `:442`) | resta il valore del DB (`ferma_al_nuovo_avvio` `omega_service.py:7314` scrive solo status/mode/stats) | Control Room riga Omega `PannelloBot.tsx:692-743` («uscite: manuali/automatiche», conferma al 2° clic per automatiche); inoltre `OmegaParamsSheet` scelta `uscite_protezione` (`lib/omega.ts:1225`) SENZA conferma | `blocca_il_profitto` (TP), `protezione` (TL), `rischio` (TL, default spento), **`cap` (tetti di perdita: P→, test `test_omega_proposte_2026_09_17.py::test_un_cap_scattato_propone_e_lo_dichiara`)** — `omega_proposte.py:79, 1045-1057` | green-up automatico v2 (`omega_service.py process_auto_greenup :6734`) IGNORA l'interruttore — oggi dormiente (forzato off con `strategy_version>=3`, default 3) | scheda «Uscite — decidi tu» (Control Room); approva = `omega_request_approve` → `_manual_cashout` (`omega_service.py:5542`): prezzi di ADESSO ma **NON ricontrolla che la condizione valga ancora** (esegue anche con `valutazione.valida=False`); nessuna scadenza, resta `proposed`, ignora → si ripropone se cambia qualcosa | **DA CORREGGERE**: (1) riavvio non torna manuale; (2) `cap` = tetto di perdita va AUTO in entrambe; (3) approvazione senza ricontrollo della condizione; (4) scheda parametri senza conferma |
| **mike** | `mike_control.params.uscite_automatiche` bool; default `config.py:254` False; motore `engine.py:2222-2227` solo bool vero; letto a ogni `run_once` (`service.py:2730/2746`), gate `engine.gate_uscite :2293` chiamato da `decide` | resta il valore del DB (`service.py:2696` idem) | Control Room riga Mike `PannelloBot.tsx:692-743` (conferma per automatiche); `MikeParamsSheet` gruppo «uscite» (`lib/mike.ts:509`) SENZA conferma | green pre-match `under_green`, `ko_green`, cash out `under_close`/`over_close` (TP), perdita a modello/tollerata `loss_ht`/`loss_2t` (TL, urgente), `reentry_green`, `reentry_time` — `engine.py:2204` | «gia' in corso» per RUOLO nel ciclo (`engine.py:2248-2264`): se nel ciclo esiste gia' una gamba dello stesso ruolo, l'uscita successiva passa SENZA nuova firma (es. `engine.py:2664-2685` chiusura finale / veto U35 dell'ultimo ingresso, `:3698-3709` `reentry_time`); `ko_green` alla scadenza della finestra passa alla copertura da solo (`:2999-3006`) | `PropostaUscitaMike` in `SchedaMike` (Control Room); approva = `mike_request('approva_uscita', chiave)` → `service.py:2539`; al giro dopo il motore RIDECIDE sul mercato di adesso e passa solo se categoria+chiave coincidono (OK), MA chiave = `categoria|cN` senza motivo/prezzo: una firma su un cash out in profitto puo' eseguire entro 120 s un'uscita in perdita della stessa categoria; firma vale 120 s (`:2219`), proposta non scade finche' la strategia la vuole | **DA CORREGGERE**: (1) riavvio; (2) chiave senza motivo (spec, §B.7); (3) proposta senza «quanto rischi se tieni» (`bloccabile` solo per le chiusure) |
| **safe_base / safe_esatto / safe_punta** | `safe_strategy_control.params.uscite_automatiche.{base,esatto,punta}` (`bot_service.py:170`, `normalize_uscite_automatiche :427-446`, solo bool vero); letto a ogni giro (`run_once :9098`), cancello `_process_exit_one :3900-3918` | resta il valore del DB (`bot_service.py:9024` tocca solo `strategy_modes`) | Control Room + pagina Safe (`SafeStrategy.tsx:1232` monta lo stesso `PannelloBot`): riga per strategia, conferma per automatiche | tutte le regole del manuale: `loss`, `profit`, `red_card`, `controllo_passato`, `time` (`exits.py:952-986`) | (1) **se la scrittura della proposta fallisce l'uscita parte da sola** (`bot_service.py:3902-3916`, test `test_col_database_rotto_la_posizione_NON_resta_senza_uscita`); (2) residuo di un'uscita gia' inviata (completamento, `:3781-3809`) | `SchedaChiusura` (Control Room); approva = `safe_request_approve` → `_request_cashout :3152`: prezzi di ADESSO (feed fresco o REST, rifiuta a mercato sospeso) ma **NON ricontrolla la condizione** (`XE.decide` non rieseguito); proposte `cashout` **non scadono mai a tempo** (`bot_db.py:778` scade solo `place`); decadono solo se la condizione cade (strategie del manuale) | **DA CORREGGERE**: (1) riavvio; (2) ricontrollo all'approvazione (spec §B.7, file in mano a D1/J); (3) fallback «DB rotto → esce» = decisione utente (§D) |
| **safe_tennis** | `...uscite_automatiche.tennis` ↔ `tennis_exit_approval` (default True = manuale, `bot_service.py:157`, riallineati in `resolve_params :361-368`) | resta il valore del DB | riga «Tennis» di Safe in Control Room (conferma per automatiche) + spunta `tennis_exit_approval` in `BotParamsSheet.tsx:646` (senza conferma) | `mandatory` (due game persi, TL, urgente), `profit` (leader vince il game), `loss` (spenta di default) — `exits.py:1003-1014` | come Safe calcio (fallback DB rotto, residuo) | come Safe calcio | **DA CORREGGERE** come Safe calcio |
| **safe (trade `model`)** | `...uscite_automatiche.model` | resta DB | riga `safe-model` in `INTERRUTTORI` (`frontend/src/lib/interruttori.ts:188`), stesso pulsante (correzione mia: nella prima stesura avevo scritto «nessuna riga») | take-profit modello, cash-out quasi gratis (TP), linea decisa contro, game/set persi, gol/rosso avverso (TL) — `exits.py:1188-1208` via `bot_service.py:4283-4327` | come Safe | come Safe; in piu' le proposte `model` **non decadono** quando la condizione cade (`bot_service.py:3854-3859` scrive solo `_write_model_hold`) | **DA CORREGGERE**: proposte orfane (risolto da D1 su master: `_decadi_proposte_non_eseguibili`) |
| **scalper_calcio (maker)** | `scalper_control.params.uscite_automatiche` per sessione (`scalper_bot.py:446-447`, solo bool vero); a caldo ogni 5 s (`scalper_session.py:612-633, 1376-1379`); sessioni dell'auto-mode ereditano `scalper_service_control.params` (`scalper_service.py:487`, `auto_mode.py:145-151`) | riga di servizio: resta il valore del DB (`scalper_service.py:385-389` senza reset dei params); sessioni vecchie `stopped` coi params intatti | Control Room riga Scalper (`PannelloBot`, RPC `scalper_uscite_automatiche` che scrive su tutte le sessioni attive + servizio), conferma per automatiche; nessun pulsante nella pagina scalper | chiusura a +`scalp_ticks` (`_open_lock :1826`), gamba opposta maker/join (`:1347, :1389`), scratch a pari (`:1713`) | **STOP a N tick** e **timeout `lock_ttl_ms`** (`scalper_bot.py:1678-1703`) = TL, AUTO; test che lo fissa: `test_scalper_uscite_automatiche_2026_09_25.py::test_spento_lo_stop_a_n_tick_resta_automatico` | proposta = SOLO un'attivita' `uscita_proposta` in `scalper_activity` (riga grezza in `ScalperPanel.tsx:626-640`): **nessun pulsante «approva», nessuna RPC**; se nessuno risponde la posizione resta in LOCKING finche' non scatta una protezione (stop, TTL 1 h, pre-KO 180 s, force-flat) | **DA CORREGGERE**: stop/TTL in proposta; riavvio; approvazione inesistente (spec §B.6) |
| **scalper_calcio (sniper)** | base: NON legge l'interruttore (grep 0). Cantiere D2 (worktree `agent-aa4ee030442dc331f`, non committato): legge `uscite_automatiche` (`sniper_bot.py:145-158`), presa di profitto → proposta (`:466-478`), sessione gli passa l'interruttore (`scalper_session.py:935-937, 1383-1386`) | come maker | stessa riga Scalper | con D2: presa di profitto a +`target_ticks` | con D2: **STOP `stop_ticks`** e **TIMEOUT `max_pos_s`** restano AUTO (scelta dichiarata da D2 §2.6, test `test_spento_lo_stop_a_n_tick_resta_automatico`, `test_spento_il_timeout_della_posizione_resta_automatico`) | come maker | **DA CORREGGERE** (dopo l'integrazione di D2): stop e timeout in proposta (spec §B.5) |
| **scalper_calcio (theta)** | nessun interruttore uscite; ha `confirm_mode` suo (`theta_bot.py:444`), la UI lo forza `auto` (`ScalperPanel.tsx:189`); in live forzato dry-run (`scalper_session.py:975-978`) | — | nessuno | — | green immediato, scratch timer (TP/TL) sempre AUTO; in `confirm_mode` propone e dopo 60 s ESEGUE comunque | `theta_confirm_requests` (watcher `scalper_session.py:1244-1285`) | **NON ARMABILE con soldi veri** (dry-run forzato in live); DA CORREGGERE prima di renderlo armabile (spec §B.5) |
| **tennis_scalper** | ESCLUSO: `auto_mode.BOT_USCITE_SEMPRE_AUTOMATICHE = {"tennis_scalper"}` (`auto_mode.py:66, 219-223`); `tennis_scalper_bot.py` non legge l'attributo | resta DB (irrilevante: sempre automatico) | `UsciteTennis.tsx:42-48` scritta «uscite: sempre automatiche», nessun pulsante | nessuna | TUTTE: gamba opposta come chiusura (`tennis_scalper_bot.py:1515-1530`), `_open_lock :1931-1970` (TP), stop/`lock_ttl :1845-1853`, scratch (TL) | nessuna proposta | **DA CORREGGERE**: l'eccezione del 25/09 e' superata dall'ordine di oggi |
| **tennis_swing** | `tennis_bot_service_control.uscite_automatiche` (colonna, `migrations/tennis_uscite_manuali_2026-09-25.sql:72`), propagata dal ponte (`tennis_bot_service.py:594, 800-818`, ogni 15 s, SOLO a bot acceso) a `tennis_bot_control`, letta dal runner (`tennis_runner.py:860` alla nascita, `:1708/1762-1793` a caldo ogni 3 s); classe `tennis_swing_bot.py:65` False | resta il valore del DB (`ferma_interruttori_al_nuovo_avvio :858-907` scrive status/mode/stats) | Control Room, slot `parametriRiga` (`ControlRoom.tsx:466-476` → `UsciteTennis.tsx`): POSTO E PAROLE DIVERSE dagli altri bot («uscite: MANUALI (passa ad automatiche)»), conferma per automatiche | target (`:461-473`) | **stop a tick** (`:463, 474-506`, TL) e **time-stop `tmax`=90 s** (`:465-468`, chiude anche in utile) | NESSUNA proposta: solo avviso «posizione aperta da X min — chiudi con «Chiudi»» (`tennisAuto.ts:118-127`); unica azione = «Chiudi» D3 (`chiusura_manuale.py`) | **DA CORREGGERE**: stop/time-stop in proposta; proposta con numeri + approva (spec §B.6); riavvio; pulsante unificato |
| **tennis_pro** | come swing; classe `tennis_pro_bot.py:91` | come swing | come swing | scaglione (`:783-788`), target (`:790-793`) | **stop** (`:794-797`, TL) e **uscita strutturale** a cambio game/set (`:798-804`, anche in utile) | come swing | **DA CORREGGERE** come swing |
| **tennis_flb** | come swing; classe `tennis_flb_bot.py:66` | come swing | come swing | green sullo swing (`:476-496`) | nessuna (non ha stop per progetto) | come swing; se nessuno risponde tiene fino al settlement | **DA CORREGGERE**: proposta/approva (spec §B.6); riavvio; pulsante unificato |

## A.2 Riavvio dell'app: in base NESSUN bot torna a manuale

`Betfair/stream/avvio_app.py:151 ferma_al_nuovo_avvio` (Omega/Mike/Safe/scalper-servizio) scrive solo
`status`, `mode`, `stopped_at`, `stats` (+ `strategy_modes` per Safe); il ponte tennis
(`tennis_bot_service.py:858`) e lo scalper per sessione (`scalper_service.py:249`) idem. L'unico
ritorno a manuale e' stata la migrazione una-tantum del 25/09. Un riavvio dal watchdog (stesso
`APP_BOOT_ID`) giustamente non tocca niente.

## A.3 Protezioni che restano automatiche in entrambe le posizioni (per bot, e perche')

| Bot | Protezione | Dove | Perche' e' protezione e non scelta di trading |
|---|---|---|---|
| Omega | kill-switch (frena gli ordini, non chiude) | `omega_service.py:2022-2036` | sicurezza |
| Omega | stop giornaliero (ferma gli ingressi) | `:2272-2278` | non chiude |
| Omega | annullo ordini vivi a posizione chiusa dall'utente / di conto | `:4383`, `:5809-5816` | divergenza specchio |
| Omega | **tetti `cap`** (`daily_loss_cap`, `v3_daily_loss_cap`, `max_open_liability`, cap per gamba/partita) | `omega_proposte.py:98-107, 199-244, 1045` | tetto di perdita: **oggi in manuale e' PROPOSTA → corretto in §B.3** |
| Mike | tetto perdita partita `event_loss_cap_pct` (`loss_cap`) | `engine.py:2208, 3525-3529` | tetto di perdita |
| Mike | copertura Over 4.5 (prima/seconda tranche, riprezzo) | `engine.py:3344, 3442, 3539-3548` | assicura l'Under contro il 4° gol: non chiude, copre (dubbio 2 del 25/09, confermato protezione) |
| Mike | annullo ordini vivi a posizione chiusa fuori dall'app | `service.py:2113-2222` | divergenza specchio |
| Mike | completamento di un'uscita gia' approvata/partita (riprezzo, residuo) | `engine.py:2213, 2248-2264` | una chiusura a meta' lascia la posizione scoperta |
| Safe | residuo di un'uscita gia' inviata | `bot_service.py:3781-3809` | completamento |
| Safe | chiusura solidale combo / svolgimento combo incompleta | `:3919-4052`, `:8265-8348` | gamba nuda |
| Safe | kill-switch, stop giornaliero | `execution.py:803-812`, `risk.py:176-202` | fermano SOLO le aperture: **Safe non ha nessuna protezione che chiuda** una posizione (niente tetto perdita per posizione) |
| Scalper maker | pre-KO `flatten_before_s`=180, in-play senza `allow_inplay`, `inplay_close_now` | `scalper_bot.py:637-665, 703-728` | fine finestra: la strategia non puo' restare aperta |
| Scalper maker | force-flat (freno, stop sessione, fine vita), fill durante la cancel, close impossibile, residuo | `:653, 1790, 1816-1842, 1882-2009`; `scalper_session.py:1290-1426` | kill-switch / «mai nuda» |
| Scalper maker | loss cap evento 1,5 €, cap globale evento 2,0 €, circuit breaker 0,50 € | `:952-959`, `scalper_session.py:1360-1375`, `:1905-1914` | tetti di perdita — **ATTENZIONE: misurano solo il REALIZZATO** (`pnl_locked`), non la perdita aperta |
| Sniper | fuori finestra, force-flat, flatten parziale, loss cap 1,0 (solo colpi nuovi) | `sniper_bot.py:395-409, 460-467, 515-524` | fine finestra / tetto (realizzato) |
| Tennis swing/pro/flb | «Chiudi» D3, entry timeout, copertura tardiva, escalation di un'uscita gia' decisa | vari (§A.1) | comando utente / completamento |
| Tennis | kill-switch (blocca SOLO le aperture), tetto esposizione flumine (solo aperture) | `guardie_tennis.py:236-294`, `tennis_runner.py:829` | nessuna protezione che CHIUDA: niente loss cap, niente force-flat per swing/pro/flb |
| Tennis scalper | near-KO/force-flat, loss cap, circuit breaker | `tennis_scalper_bot.py:816-830, 1268-1274, 2021-2025` | fine finestra / tetto |

## A.4 Test esistenti (sintesi; dettaglio negli elenchi dei 4 audit, riportati in §E)

| Caso | Omega | Mike | Safe | Scalper | Tennis |
|---|---|---|---|---|---|
| manuale+profitto → proposta | si' | si' | si' (kind `time`; `profit` vero MANCA) | si' (maker; sniper solo in D2) | «non parte» si', proposta MANCA |
| manuale+perdita → proposta | si' | si' (loss a modello; tollerata/veto/reentry_time MANCA) | si' (`mandatory`; calcio loss/red MANCA) | **contrario** (test fissano stop AUTO) | **contrario** (test fissano stop/time-stop AUTO) |
| automatico → parte | si' | si' | si' | si' | si' |
| protezioni in entrambe | cap: **contrario** | si' in manuale | parziale | parziale | parziale |
| cambio a caldo | si' (auto→avvisa MANCA) | si' | si' | si' | si' |
| riavvio → manuale | MANCA | MANCA | MANCA | MANCA | MANCA |

## A.5 Verdetto complessivo

**Nessun bot e' CONFORME alla regola di oggi.** Difetti comuni a tutti: (1) il riavvio dell'app non
riporta le uscite a manuale; (2) il pulsante non e' nello stesso posto e con le stesse parole (tennis
diverso; schede parametri Omega/Mike/Safe-tennis cambiano l'interruttore senza conferma). Difetti per bot: uscite in PERDITA ancora automatiche in manuale (scalper stop/TTL,
sniper stop/timeout, tennis stop/time-stop/strutturale, tennis_scalper tutto); tetti di perdita di
Omega trattati come proposta; approvazione senza ricontrollo della condizione (Omega, Safe);
proposte inesistenti per scalper/sniper/tennis (solo attivita' o avviso, nessun «approva»).

---------------------------------------------------------------------------------------------------

# PARTE B — CORREZIONI

Consegna in DUE patch (`git diff origin/master`, base `949c094`, applicabili pulite IN SEQUENZA,
verificato con `git apply --cached --check` su indice temporaneo):
`AUDIT_2026-09-28/cantiere_n/cantiere_n_blocchi_1_2.patch` (34 file, +1203/-336) e poi
`AUDIT_2026-09-28/cantiere_n/cantiere_n_blocco_3.patch` (25 file, +2124/-110). Divisione riproducibile
con `AUDIT_2026-09-28/cantiere_n/dividi_patch.py`. Ramo locale del worktree con commit di LAVORO
(nessun push). Strategie non toccate: nessuna soglia, nessun importo, nessun «quando»; cambia solo CHI
esegue l'uscita.

## B.1 Riavvio dell'app → uscite MANUALI (tutti i bot)  [patch 1]

Causa radice: `avvio_app.ferma_al_nuovo_avvio` (e il ponte tennis) all'avvio nuovo scriveva solo
status/mode/stats; l'interruttore restava quello del DB (§A.2).
- `Betfair/stream/avvio_app.py`: nuove `uscite_a_manuali(bot, params)` e `STRATEGIE_SAFE_CON_USCITE`;
  nuovo parametro `uscite_bot` di `ferma_al_nuovo_avvio` (dopo l'eventuale `params_reset` di Safe).
  Non conta come «bot fermato» (niente cartello se il bot era gia' fermo in prova), l'attivita'
  `avvio_app_bot_fermato` porta `uscite_riportate_a_manuali`. Riavvio dal watchdog (stesso
  `APP_BOOT_ID`): non si tocca la scelta dell'utente.
- UNA riga ciascuno: `mike/service.py:ferma_al_nuovo_avvio` (`uscite_bot="mike"`),
  `omega/omega_service.py:ferma_al_nuovo_avvio` (`"omega"`), `safe_strategy/bot_service.py:
  ferma_al_nuovo_avvio` (`"safe"`), `stream/scalper/scalper_service.py:giro_auto` (`"scalper"`: la riga
  dell'interruttore da cui nascono le sessioni dell'auto-mode).
- Tennis: `tennis_live/tennis_bot_service.py:ferma_interruttori_al_nuovo_avvio` porta a `false` la
  colonna `uscite_automatiche` (anche per un bot fermo in prova ma in automatico, senza cartello);
  `tennis_live/tennis_db.py:set_tennis_bot_service_state` ha il kwarg `uscite_automatiche`.
- Sessioni scalper per partita: la card le riarma con `scalper_activate` che sostituisce i params
  (nascono manuali); l'auto-mode le arma coi params della riga di servizio, ora riportata a manuale.

## B.2 Approvazione che RICONTROLLA la condizione, sul mercato di adesso  [patch 1]

- Omega `omega_service.py`: nuove `_condizione_caduta`, `_rifiuta_se_condizione_caduta`, UNA chiamata in
  `_manual_cashout` dopo il controllo della firma. Una firma su una proposta che il produttore ha gia'
  marcato `valutazione.valida=False` non chiude: `error=condizione_non_piu_valida` e il messaggio
  «Per chiudere comunque usa «Chiudi»». Prezzi: gia' quelli di adesso (`_cashout_prices`).
  Nota: e' un cambio rispetto all'ordine del 24/09 («la scheda deve segnalarmi se c'e' ancora o no: io
  decido»): la scheda lo segnala ancora; la FIRMA su una condizione caduta non esegue piu' (regola di
  oggi). Il «Chiudi»/cash out dell'utente non passa di qui.
- Mike `engine.py`: nuova `_stessa_uscita_firmata`, usata in `gate_uscite`: la chiave `categoria|cN`
  non conteneva il motivo, una firma su un cash out IN PROFITTO poteva eseguire entro 120 s un'uscita IN
  PERDITA della stessa categoria. Ora passa solo se il `close_reason` di adesso e' quello firmato,
  altrimenti nasce la proposta nuova e la firma vecchia cade (telemetria
  `uscita_firmata_non_eseguita`). Il resto (il motore ridecide sul mercato di adesso) c'era gia'.
- Safe: il ricontrollo e' quello del cantiere D1 gia' su master (`_proposta_non_piu_valida` in
  `_request_cashout`); il mio doppione l'ho tolto nel merge.

## B.3 Un pulsante, stesse parole, conferma  [patch 1]

- `frontend/src/components/controlroom/InterruttoreUscite.tsx` (NUOVO): stato sempre visibile
  «uscite: MANUALI, approvi tu» / «uscite: AUTOMATICHE» (o «non lette», senza pulsante); «passa ad
  automatiche» → conferma «confermi? passa ad automatiche» INERTE 400 ms (un doppio clic non la
  colpisce, stessa regola della conferma «soldi veri») + «annulla»; «passa a manuali» senza conferma.
- `PannelloBot.tsx` usa il componente (riga del bot in Control Room e pagina di Safe, che monta lo
  stesso pannello). I 4 bot tennis entrano nello STESSO pulsante: `interruttori.ts:cambiaUscite` chiama
  `setTennisBotUscite` (RPC `tennis_bot_service_set_uscite`), nuova `usciteBotTennis`;
  `useControlRoom.ts` espone `usciteTennis` (la colonna, letta anche a bot spento); `pages/
  ControlRoom.tsx` li aggiunge alle uscite delle righe e non monta piu' `UsciteTennis`
  (`UsciteTennis.tsx` e il suo test ELIMINATI).
- Schede parametri (bug segnalato dal coordinatore): nuovo tipo di campo `'uscite'` in
  `trading/ParamsSheetBase.tsx` che rende `InterruttoreUscite` (con conferma; si applica con «Salva
  parametri»); usato per Mike (`MikeParamsSheet.tsx`, `uscite_automatiche`), Omega (`lib/omega.ts`,
  `uscite_protezione`) e Safe tennis (`BotParamsSheet.tsx`, `tennis_exit_approval`, true = manuali).
- `lib/tennis.ts`: commento superato corretto (colonna assente = manuali).

## B.4 Proposta → scheda → approva → ordine per i bot di flusso  [patch 2]

Stesso schema di Mike (proposta nel battito del bot, firma con chiave, il bot ridecide ed esegue solo se
la condizione vale ancora, TTL 120 s = `APPROVAZIONE_TTL_S` di Mike), nessuna tabella nuova.
- `Betfair/stream/uscite_proposte.py` (NUOVO, puro): `CancelloUscite` (`lascia_uscire`, `approva`,
  `conferma_vive`, `tieni_solo`, `vive`), `proposta_di` (chiavi uguali per tutti: bot, motivo, urgente,
  market_id, selection_id, lato_ingresso, prezzo, lato_chiusura, size_chiusura, `se_chiudi` = incasso o
  perdita chiudendo ORA spalmato, `se_vince`/`se_perde` = esiti se si TIENE, frazione, decided_at,
  proposed_at), `applica_firme`.
- Bot tennis (`tennis_scalper/`): `tennis_swing_bot.py` (target, STOP, TIME-STOP), `tennis_pro_bot.py`
  (scaglione, target, STOP, uscita STRUTTURALE), `tennis_flb_bot.py` (green), `tennis_scalper_bot.py`
  (target a riposo, gamba opposta del maker come chiusura solo in automatico, scratch, STOP,
  `lock_ttl`; patch applicata con `cantiere_n/patch_tennis_scalper.py`). `tennis_live/auto_mode.py`:
  `BOT_USCITE_SEMPRE_AUTOMATICHE` vuoto (lo scalper tennis ha l'interruttore e nasce manuale).
- Scalper calcio `scalper/scalper_bot.py`: target, scratch, STOP a N tick e TIMEOUT `lock_ttl` passano
  dal cancello (prima stop e TTL chiudevano da soli anche in manuale).
- Firme al bot: `tennis_live/tennis_runner.py:_aggiorna_uscite` (battito 3 s, riga per partita gia'
  letta) e `scalper/scalper_session.py` dopo `applica_uscite_automatiche` (battito 5 s, maker e sniper).
  Le firme stanno in `params.uscite_approvate` della riga di controllo (le scrive la RPC).
- Proposte alla UI: il runner le scrive gia' (le `stats` del bot vanno sulla riga nel battito); il ponte
  (`tennis_bot_service.py:_stato_auto`) le raccoglie in `stats.auto.uscite_proposte` con la partita;
  per lo scalper sono nelle `stats` delle sessioni.
- Frontend: `lib/proposteUscite.ts` (lettura pura + `approvaPropostaFlusso`),
  `components/controlroom/ProposteUsciteFlusso.tsx` (scheda «Uscite da approvare» sotto il pannello dei
  bot: cosa chiude, a che prezzo, se chiudi ora, se tieni, «approva uscita»), `useControlRoom.ts`
  (`proposteUscite` per i 4 tennis e lo scalper), `pages/ControlRoom.tsx` (montaggio).
- Migrazione `migrations/uscite_approva_bot_flusso_2026-09-28.sql` (NON applicata): RPC owner-only
  `tennis_bot_approva_uscita(event_id, bot_key, chiave)` e `scalper_approva_uscita(event_id, chiave)`
  (unione delle firme in `params.uscite_approvate`, solo su righe attive, la chiave deve essere del bot).
  Senza migrazione: «approva» risponde con l'errore della funzione mancante e NIENTE parte; il «Chiudi»
  resta. Verificati sul DB (SELECT): colonne e tipi, `tennis_is_owner`/`betfair_live_is_owner`
  esistenti, CHECK degli stati.

## B.6 Correzioni del 29/09 dopo la verifica del coordinatore (reperti A-I)

| Reperto | Causa radice (file:funzione) | Correzione | Prova |
|---|---|---|---|
| **A** firma sopravvive alla decadenza (bot di flusso) | `stream/uscite_proposte.py:CancelloUscite.conferma_vive` toglieva la proposta ma non la firma; `approva` accettava firme anche senza proposta viva | una firma vale solo per la proposta VISTA: `approva` la accetta solo se la proposta con quella chiave esiste ed e' nata PRIMA della firma (`decided_at`), altrimenti la scarta e la segna usata; `conferma_vive`/`tieni_solo`/`chiudi_posizione` tolgono proposta e firma INSIEME (`_togli`) | test del coordinatore `test_coordinatore_cancello_uscite_2026_09_28.py` (3 verdi); miei `test_firma_senza_proposta_viva_scartata_e_non_rimessa`, `test_decadenza_porta_via_la_firma_in_tieni_solo_e_chiudi_posizione`; mutazioni A1, A2 ROSSE |
| **B** Mike: firma del profitto eseguita su una perdita dopo la decadenza | `mike/engine.py:_stessa_uscita_firmata` rispondeva True con `ctx.uscita_proposta is None`; `_decadi` non toglieva `uscita_approvata` | `_stessa_uscita_firmata` -> False senza proposta; `_decadi` toglie anche la firma (anche quando la proposta era gia' assente) | test del coordinatore `test_coordinatore_firma_dopo_decadenza_2026_09_28.py` (2 verdi); mio `test_firma_senza_proposta_non_esegue_niente`; mutazioni B1, B2 ROSSE |
| **C** Omega | il payload 'pending' e' fermo al clic: il produttore aggiorna solo le 'proposed' (`omega_db.proposta_di_chiusura_viva`), quindi una condizione caduta DOPO la firma (o un motivo diverso) non si vedeva | `omega_proposte.py`: il produttore annota a ogni giro cosa pensa ADESSO di ogni gamba (`_VALUTAZIONI`, `_annota_valutazione`; una gamba non valutabile la cancella), `firma_ancora_valida`; `omega_service._rifiuta_se_condizione_caduta(..., now)` rifiuta se il bot non propone piu', propone per un ALTRO motivo, o non ha valutato la gamba in questo giro (dopo un riavvio: la firma aspetta il giro dopo, poi decade col TTL della richiesta). Il produttore gira PRIMA delle richieste nello stesso `run_once` (`omega_service.py` fase 1-bis poi `process_manual`) | 3 test nuovi in `test_omega_approvazione_ricontrolla_2026_09_28.py`; mutazioni C1, C2 ROSSE |
| **C** Safe | `bot_service._proposta_non_piu_valida` (D1) confrontava solo il TIPO (`exit_kind`) | confronta anche il MOTIVO (`exit_reason`, senza i numeri: il minuto dentro "minuto_81_..." non e' un motivo diverso). Firma che sopravvive alla proposta: NON possibile in Safe (la proposta E' la richiesta; decaduta = 'rejected'; `safe_request_approve` accetta solo 'proposed', `migrations/safe_request_approve_contesto_2026-09-24.sql:52-56`) | `test_firma_stesso_motivo_2026_09_29.py` (4 casi); mutazione C3 ROSSA |
| **D** Safe modello senza pulsante | FALSO: la riga `safe-model` esiste (`frontend/src/lib/interruttori.ts:188`, calcio) e `usciteInterruttori` le da' lo stato (`STRATEGIE_SAFE_CON_USCITE` contiene 'model', `interruttori.ts:1083`); `STRATEGIE_MANUALE` e' l'elenco delle strategie a REGOLE per le accensioni, non per le uscite. Il pulsante e' quello comune della riga | nessuna correzione; test che lo fissa | `interruttoriUscite.test.ts` "Safe modello: ha la sua riga e il suo pulsante" |
| **E** messaggio falso nel runner tennis | `tennis_runner.py:_aggiorna_uscite` scriveva "stop e protezioni restano" | testi `TESTO_USCITE_MANUALI`/`TESTO_USCITE_AUTOMATICHE` con le parole vere; stesso difetto corretto in `tennisAuto.ts:avvisoUsciteManuali` (non piu' montato, ma esportato) | `test_il_messaggio_all_utente_dice_il_vero`; mutazione E1 ROSSA; `tennisAuto.test.ts` aggiornato |
| **F** non ASCII | virgolette a caporale, lineette, apostrofi tipografici nelle righe AGGIUNTE | tutte le righe aggiunte dal cantiere in .py/.sql/.ts/.tsx rese ASCII (`cantiere_n/ascii_righe_nuove.py`); nei `.ts` gli apostrofi dentro stringhe a apice singolo sono diventati `\'`. Resta non ASCII solo testo PREESISTENTE su righe toccate (`BotParamsSheet.tsx` "finche'" con la e accentata del 14/09) | `test_i_file_nuovi_del_cantiere_sono_ascii` (modulo e migrazione); `tsc` 0 |
| **G** concorrenza del cancello | `approva` (thread del battito) e le potature (thread del mercato) iteravano dizionari vivi | `threading.RLock` su ogni metodo; iterazioni su istantanee (`list(...)`/`set(...)`); `firmata()` sotto lock usato da scalper e scalper tennis | terzo test del coordinatore verde (anche prima non riproducibile: race) |
| **H** `stats["uscite_proposte"]` cambia tipo | su origin/master l'unico uso era la SCRITTURA del contatore (`git grep -n uscite_proposte origin/master` -> solo `scalper_bot.py:1855`); nessun lettore Python, frontend, SQL o banco. Letture generiche delle `stats`: `scalper_session._stats` copia/prefissa (lista serializzabile in JSONB), `run_theta.py:163` filtra solo `v` veri; nessuna somma dei valori | contatore rinominato `uscite_proposte_emesse`, lista in `uscite_proposte` | grep riportato qui |
| **I** chiave con `id(slot.entry)` dopo un riavvio | gli ordini flumine hanno `Order.id` (stringa unica); `id()` e' solo il ripiego. Dopo un riavvio del processo la posizione ha un ordine NUOVO e la proposta una chiave nuova: la firma vecchia (chiave vecchia) non trova la sua proposta e CADE (`approva`); anche con la stessa chiave la firma e' anteriore alla proposta nuova e cade | nessuna correzione in piu' (la regola di A la copre) | `test_firma_data_prima_di_un_riavvio_cade_e_non_esegue_su_altre_posizioni` |

Test del giro 29/09: pytest `Betfair/omega Betfair/mike/tests Betfair/safe_strategy/tests
Betfair/stream/tennis_scalper/tests Betfair/stream/tennis_live/tests` + test scalper/avvio/coordinatore:
**5244 passed**, 6 skipped, 1 xfailed; vitest dei file toccati 256 + 16 verdi; `tsc` 0. Mutazioni del
giro: A1, A2, B1, B2, C1, C2, C3, E1 tutte ROSSE (`cantiere_n/falsifica_n.py`, ripristino verificato,
`git diff --stat` identico). Nota: la prima B1 era rimasta VERDE (coperta dalla B2 nei test del
coordinatore): aggiunto il test che la isola, ora ROSSA. G non ha una mutazione (il difetto non si
riproduce in modo deterministico).

## B.7 Sniper (base D2, su master da 8ada778) e strada esatta di D2 (29/09 sera)

- Merge con D2: un solo conflitto (`scalper_session.py`, punto del battito) risolto tenendo
  ENTRAMBE le modifiche: prima `applica_uscite_automatiche(..., sniper, ...)` di D2, poi
  `_UP.applica_firme((strategy, sniper), ...)` del cantiere N (`cantiere_n/risolvi_conflitto_sessione.py`).
  Gli altri 6 file in comune si sono fusi da soli: le chiusure esatte di D2 non si toccano (il cancello
  sta PRIMA della decisione di uscire; le chiusure passano ancora da `_close`/`_close_at`/`_green`).
- `Betfair/stream/scalper/sniper_bot.py` (patch `cantiere_n/patch_sniper.py`): D2 faceva passare
  dall'interruttore solo la presa di profitto; lo STOP `stop_ticks` e il TIMEOUT `max_pos_s`
  (`_begin_flatten` diretto) chiudevano da soli anche in manuale. Ora tutti e tre passano da
  `CancelloUscite` (`_lascia_uscire`, chiave `scalper|{mid}|{sid}|sn-{id ingresso}|{motivo}`: firma con
  la stessa RPC `scalper_approva_uscita`); proposte in `stats['uscite_proposte']` (nella sessione:
  `sniper_uscite_proposte`, letto dalla Control Room), contatore `uscite_proposte_emesse`. Restano
  protezioni: fine finestra, force-flat (freno/cap), divergenza del ledger, close parziale, flatten.
- Test: `test_sniper_uscite_automatiche_2026_09_28.py` (di D2) portato alla regola di oggi: stop e
  timeout in manuale -> proposta; con la firma lo stop parte; fuori finestra resta protezione; ramo
  automatico invariato. `test_sniper_bot_2026_07_10.py::test_timeout_flatten` gira ad automatiche
  (prova la meccanica). Mutazioni S1 (timeout scavalca) e S2 (stop scavalca) ROSSE.
- Strada esatta: per swing, pro e FLB un test prova che l'uscita APPROVATA parte da
  `_place(..., copertura=True)` all'importo di `compute_green` (mai gonfiato) e, sotto il minimo,
  arriva al place-and-trim di D2 (`UsciteEsatte.piazza`) all'importo esatto
  (`test_*_uscita_firmata_parte_dalla_strada_esatta`,
  `test_swing_uscita_firmata_sotto_il_minimo_passa_dal_place_and_trim_di_d2`). Mutazione X1 (uscita
  swing senza `copertura`) ROSSA.
- Frontend: le proposte dello sniper arrivano alla scheda (`useControlRoom.ts`,
  `sniper_uscite_proposte`) e si firmano con la RPC dello scalper (`proposteUscite.ts`).

## B.5 Specifiche NON fatte (file di altri cantieri o fuori master)

- **Sniper**: FATTO (B.7).
- **Theta**: in live forzato dry-run; il suo `confirm_mode` ESEGUE dopo 60 s anche se rifiutato
  (`theta_bot.py:955-979`): prima di renderlo armabile va portato sul cancello comune.
- **Omega `cap`** e **green-up v2**: vedi §G (decisione).
- **Banco di replay**: vedi §F.

---------------------------------------------------------------------------------------------------

# C. TEST (comandi ed esiti; ambiente: fixture di `Betfair/conftest.py`)

| Comando | Esito |
|---|---|
| `pytest Betfair/omega Betfair/mike/tests Betfair/safe_strategy/tests Betfair/stream/tennis_scalper/tests Betfair/stream/tennis_live/tests Betfair/stream/tests/test_scalper_uscite_automatiche_2026_09_25.py Betfair/stream/tests/test_uscite_manuali_al_nuovo_avvio_2026_09_28.py Betfair/stream/tests/test_scalper_uscite_manuali_al_riavvio_2026_09_28.py Betfair/stream/tests/test_avvio_app_2026_09_16.py Betfair/stream/tests/test_scalper_auto_mode_2026_09_25.py -q` (stato completo, dopo merge 3e96c82) | **5230 passed, 6 skipped, 1 xfailed** (172 s) |
| i 86 file di test che importano i moduli toccati (`scalper_bot`, bot tennis, `uscite_proposte`, `scalper_session`, `tennis_runner`, `tennis_bot_service`, `avvio_app`), prima del conftest | 1566 passed, 16 skipped, 2 failed = `test_omega_avvio_app_2026_09_16::test_b/test_d`, rossi anche sulla base (checkout principale); con il conftest di M passano |
| albero dei SOLI blocchi 1-2 estratto in una cartella temporanea: test nuovi 1-2 + `tennis_live/tests` + `tennis_scalper/tests` + test scalper uscite | 830 passed |
| `npx tsc -p tsconfig.app.json --noEmit` (stato completo; e frontend dei soli blocchi 1-2) | **0 errori** (entrambi) |
| vitest: `ProposteUsciteFlusso`, `PannelloBotUscite`, `interruttoriUscite`, `InterruttoreUsciteSchede`, `pages/ControlRoom`, `useControlRoom.effettiviStantii` | 162 passed |
| vitest: schede (`MikeParamsSheet`, `OmegaParamsSheet`, `BotParamsSheet`, `designSystem`, `lib/omega`, `lib/mike`) | 196 passed |
| vitest: `useControlRoom*` (5 file), `righeBot`, `PannelloBot` | 173 passed |

Test nuovi: `Betfair/stream/tests/test_uscite_manuali_al_nuovo_avvio_2026_09_28.py`,
`Betfair/mike/tests/test_mike_uscite_manuali_al_riavvio_2026_09_28.py`,
`Betfair/omega/test_omega_uscite_manuali_al_riavvio_2026_09_28.py`,
`Betfair/safe_strategy/tests/test_uscite_manuali_al_riavvio_2026_09_28.py`,
`Betfair/stream/tests/test_scalper_uscite_manuali_al_riavvio_2026_09_28.py`,
`Betfair/stream/tennis_live/tests/test_tennis_uscite_manuali_al_riavvio_2026_09_28.py`,
`Betfair/omega/tests/test_omega_approvazione_ricontrolla_2026_09_28.py`,
`Betfair/mike/tests/test_mike_firma_stesso_motivo_2026_09_28.py`,
`Betfair/stream/tennis_scalper/tests/test_uscite_proposte_bot_tennis_2026_09_28.py`,
`Betfair/stream/tennis_live/tests/test_tennis_firme_e_proposte_2026_09_28.py`,
`frontend/src/components/controlroom/ProposteUsciteFlusso.test.tsx`,
`frontend/src/components/controlroom/InterruttoreUsciteSchede.test.tsx`.
Test esistenti cambiati perche' la regola e' cambiata (dichiarati): `test_mike_avvio_app_2026_09_16.py`
(params: solo l'interruttore torna manuale; `test_d` rimette automatiche per provare che il servizio
fermo lavora le uscite), `test_scalper_uscite_automatiche_2026_09_25.py` (stop/TTL da «resta
automatico» a «diventa proposta» + ramo automatico + firma), `test_uscite_manuali_bot_tennis_2026_09_25.py`
(stop/time-stop swing e stop pro: «..._diventa_proposta» + «..._parte» in automatico; lo scalper tennis
ha l'interruttore), `test_tennis_auto_mode_2026_09_25.py` (nessuna eccezione per lo scalper; chiave
`uscite_proposte` in `stats.auto`), `test_tennis_swing.py` (l'helper `_make` gira a uscite automatiche:
la suite prova la meccanica), `PannelloBotUscite.test.tsx` (parole nuove, conferma inerte),
`interruttoriUscite.test.ts` (tennis dal pulsante comune), `OmegaParamsSheet.test.tsx` e `omega.test.ts`
(componente comune con conferma al posto dei due pulsanti).

**Falsificazione** (`AUDIT_2026-09-28/cantiere_n/falsifica_n.py`, una mutazione alla volta sul codice di
produzione, ripristino dal contenuto in memoria verificato byte per byte, `git diff --stat` identico
prima/dopo): M1 avvio non resetta · M2 Safe dimentica il cancelletto del tennis · M3-M6 Mike/Omega/
Safe/scalper non collegati · M7 tennis non resetta · M8 anche il watchdog resetta · M9 Omega firma senza
ricontrollo · M10 Omega ignora `valida` · M14 Mike firma valida per ogni motivo · M15 firma mai valida ·
M16 firma senza scadenza · M17 condizione caduta ignorata · M18 swing stop sempre automatico · M19 pro
strutturale automatica · M20 FLB green senza proposta · M21 scalper stop sempre automatico · M22
scalper tennis usa la gamba opposta in manuale · M23 eccezione dello scalper tennis rimessa · M24 il
runner non passa la firma · M25 il ponte non porta le proposte · F1 conferma non inerte · F2 tennis
fuori dal pulsante · F3 automatiche senza conferma · F4 firma al bot sbagliato · F5 scheda Mike con la
spunta libera · F6 scheda Omega coi due pulsanti: **tutte ROSSE**. (M11-M13 su Safe tolte: il
ricontrollo di Safe e' quello di D1.)

# D. MIGRAZIONI (scritte, NON applicate)

1. `migrations/uscite_approva_bot_flusso_2026-09-28.sql` — solo due funzioni nuove (CREATE OR REPLACE,
   owner-only), nessun dato. Serve al blocco 3 («approva» per tennis e scalper). Ordine: dopo
   `tennis_bots.sql`, `scalper_bot.sql`, `security_lockdown.sql` (gia' applicate).
I blocchi 1-2 non richiedono migrazioni (usano colonne/RPC gia' presenti: `tennis_bot_service_set_uscite`,
`scalper_uscite_automatiche`, `*_update_params`).

# E. PARITA' PAPER / LIVE

Nessun ramo nuovo guarda la modalita': il cancello (`CancelloUscite`, `gate_uscite`,
`_rifiuta_se_condizione_caduta`, `ferma_al_nuovo_avvio`) e' lo stesso codice in paper e in live; il
test `test_swing_paper_uguale_live` prova che in dry-run la proposta nasce identica e nessun esito
virtuale si conta. Le firme passano dalla stessa riga di controllo in entrambe le modalita'.

# F. COSA NON HO FATTO / NON HO POTUTO VERIFICARE

- Nessun replay (vincolo). **ATTENZIONE**: il banco (`Betfair/stream/backtest/`) non passa
  `uscite_automatiche` ai bot di flusso; con il default MANUALE (dal 25/09 sera) e ora anche stop,
  time-stop e strutturali in proposta, un replay di tennis/scalper senza il parametro NON chiude piu'
  niente da solo (restano fine mercato, freno, pre-KO): i numeri NON sono confrontabili coi referti
  certificati. Serve `uscite_automatiche=True` negli scenari che certificano la strategia (+ uno
  scenario «manuale» dedicato). Registro del banco fuori dal mio perimetro.
- La sessione scalper (`scalper_session` ciclo principale) non e' eseguibile nei test unitari: provata
  la funzione `applica_firme` e la riga di chiamata e' una sola; da vedere dal vivo.
- Theta (§B.5); lo sniper e' fatto (§B.7). Omega green-up v2 non governato dall'interruttore (dormiente con v3).
- Migrazione non provata su Postgres vero (solo verifica dello schema in lettura).
- UI mai vista nell'app reale (niente `npm run build`, niente app): tsc + vitest.
- Proposte tennis a bot SPENTO: il ponte scrive `stats.auto` solo a bot acceso; con bot spento e
  posizione ancora aperta la proposta vive nella riga per partita ma la Control Room non la mostra
  (resta il «Chiudi»).
- `exits.enabled` di Safe («Uscite automatiche attive» nella scheda) e' un parametro di STRATEGIA
  (spegne del tutto le uscite di regola), non l'interruttore: nome ambiguo, non toccato.

# G. RISCHIO DEL "TUTTO IN MANUALE" QUANDO NON RISPONDI, E PROTEZIONI CHE ESISTONO OGGI

La regola e' data (ogni uscita di trading passa da te). Qui, bot per bot, cosa puo' succedere se una
proposta resta senza risposta, con esempi in euro ai parametri di serie, e quali protezioni
AUTOMATICHE esistono oggi e su che cosa si misurano. Nessuna soglia nuova proposta.

| Bot | Esempio (parametri di serie) | Se non rispondi | Protezioni automatiche che ci sono | Su cosa si misurano |
|---|---|---|---|---|
| **Omega** (lay 1 EUR per gamba, v4) | lay 1 EUR sul 1-1 @ 12: liability 11 EUR. Il bot propone "protezione" quando tenere costa di piu' | se il 1-1 esce perdi 11 EUR per gamba (2 gambe: fino a 22 EUR a partita) | kill-switch (blocca gli ordini, non chiude); stop giornaliero `v3_daily_loss_cap` 300 EUR (blocca solo gli INGRESSI); i tetti `cap` (`v3_max_liability_per_leg` 95 EUR, perdita giornaliera) sono PROPOSTE per tuo ordine del 17/09: non chiudono da soli | stop giornaliero e tetti di perdita: sul REALIZZATO della giornata; tetto per gamba: sulla liability della gamba aperta. Nessuna chiusura automatica di una gamba in perdita |
| **Mike** (Under 3.5 stake 10 EUR) | back Under 3.5 10 EUR @ 1,50; al 2-1 al 60' la quota sale a 4,0: chiudendo ora circa -6 EUR | al 4° gol perdi i 10 EUR (meno la copertura Over 4.5 se piazzata) | copertura Over 4.5 (AUTOMATICA, e' la gamba che limita il danno del 4° gol); tetto perdita partita `event_loss_cap_pct` 100 % (AUTOMATICO: chiude a cash out quando la perdita aperta arriva al 100 % dello stake); kill-switch (blocca ingressi) | copertura e tetto partita: sulla posizione APERTA (valore di cash out). Le uscite in perdita a modello/tollerate sono proposte |
| **Safe** base/esatto/punta (lay 10 EUR) | base: lay 10 EUR sull'ospite @ 3,0 (liability 20 EUR); l'ospite pareggia: il bot propone "sfavorita_pareggia", chiudendo ora circa -6 EUR | se l'ospite vince perdi 20 EUR | nessuna chiusura automatica: kill-switch e stop giornaliero bloccano solo gli ingressi; se la proposta non si puo' scrivere (DB giu') l'uscita parte da sola (fail-safe esistente) | stop giornaliero: realizzato. Nessuna protezione sulla posizione aperta |
| **Safe tennis** (back 3 EUR) | back 3 EUR sul leader @ 1,30; perde due game di fila: proposta "mandatory" | se perde il match perdi 3 EUR | come Safe calcio | come Safe calcio |
| **Safe modello** | come la sua strategia (take-profit, linea decisa contro) | fino alla liability della posizione | come Safe | come Safe |
| **Scalper calcio** (stake 25 EUR, stop 1 tick, pre-match) | BACK 25 EUR @ 2,22; la quota sale a 2,40: stop proposto, chiudendo ora -1,88 EUR (lo stop automatico avrebbe perso circa -0,22 EUR); a 3,00: -6,50 EUR | la perdita cresce fino alla chiusura forzata | chiusura forzata a KO -180 s (`flatten_before_s`); freno e stop sessione (force-flat); tetto evento `event_loss_cap` 1,5 EUR e cap globale 2,0 EUR; circuit breaker 0,50 EUR | chiusura a KO e freno: sulla posizione aperta (chiudono tutto). Tetti evento, cap globale, circuit breaker: SOLO sul REALIZZATO (non vedono una perdita ancora aperta) |
| **Sniper** (in-play, stake 10 EUR) | BACK Under 10 EUR @ 1,40; gol: la quota sale a 2,50, stop e timeout proposti, chiudendo ora circa -4,40 EUR | al gol successivo si perdono i 10 EUR | fuori finestra (~110'), force-flat, loss cap 1,0 EUR | loss cap: realizzato |
| **Scalper tennis** (stake 2 EUR) | BACK 2 EUR @ 1,80, stop proposto a 1,90: circa -0,11 EUR; a 3,0: circa -0,80 EUR | fino a -2 EUR se il giocatore perde | near-KO/force-flat, freno, loss cap, circuit breaker | force-flat: posizione aperta; loss cap e circuit breaker: realizzato |
| **Tennis swing / pro** (stake 2 EUR) | pro BACK 2 EUR @ 1,80; il favorito perde il set, quota 2,50: stop/strutturale proposti, chiudendo ora circa -0,56 EUR | se perde il match -2,00 EUR (tutto lo stake); se era un LAY, la liability | "Chiudi" tuo; fine mercato (solo dichiarazione); kill-switch (blocca solo gli ingressi) | nessuna protezione automatica che chiuda: la posizione arriva a fine partita |
| **Tennis FLB** (lay max 1,10 su 2 EUR) | green proposto quando la quota risale | tieni fino a fine partita: rischio massimo la liability (circa 0,20 EUR) | nessuno stop per progetto; "Chiudi"; fine mercato | liability della gamba |

Altri punti che restano a te (non sono scelte tecniche):
1. **Omega, firma su una proposta che non vale piu'**: da oggi NON esegue (regola di oggi); il 24/09 avevi
   chiesto di poter decidere anche su una proposta non piu' valida. Per chiudere comunque resta "Chiudi".
2. **Safe, proposta non scrivibile (DB giu')**: l'uscita parte da sola anche in manuale (fail-safe
   esistente, `bot_service._proponi_chiusura` -> False -> `_send_exit`); senza DB non potresti ne'
   vederla ne' approvarla.
3. **Mike, "gia' in corso" per ruolo nel ciclo**: dopo un'uscita approvata, i seguiti dello stesso ruolo
   nello stesso ciclo (riprezzi, chiusura finale dell'ultimo ingresso, `reentry_time`) passano senza
   nuova firma (`engine._uscita_gia_in_corso`).
4. **Banco di replay**: gli scenari che certificano la strategia vanno lanciati con
   `uscite_automatiche=True`; lo scenario "manuale" (proposte, zero uscite di trading eseguite,
   protezioni eseguite) e' uno scenario in piu' da certificare.

# H. CONTROLLI DAL VIVO IN PAPER (prossimo avvio dell'app)

| Bot | Controllo | Dato atteso | Dove |
|---|---|---|---|
| tutti | dopo il riavvio dell'app | riga «uscite: MANUALI, approvi tu» per Omega, Mike, Safe (5 righe), scalper, 4 tennis; nel DB `params.uscite_automatiche=false` / `uscite_protezione` assente o `avvisa_e_proponi` / colonna tennis `false` | Control Room; SELECT su `*_control` |
| tutti | «passa ad automatiche» | serve il SECONDO clic (conferma), un doppio clic rapido non basta; «passa a manuali» immediato | Control Room, riga del bot; schede parametri Omega/Mike/Safe |
| Omega | proposta in scheda, poi la condizione cade, poi «approva» | richiesta in errore `condizione_non_piu_valida`, nessun BACK | scheda uscite Omega; `omega_manual_requests.result`; `omega_activity` reason `condizione_non_piu_valida` |
| Mike | firma su cash out in profitto, poi la strategia vuole un'uscita in perdita | nessun ordine; proposta nuova `loss_*`; telemetria `uscita_firmata_non_eseguita` | `PropostaUscitaMike`; `mike_events.ctx` |
| Safe | proposta approvata con condizione cambiata | rifiuto D1 `condizione_uscita_non_valida` | `SchedaChiusura`; `safe_strategy_requests` |
| tennis ×4 | posizione in stop/time-stop/strutturale a uscite manuali | nessun ordine; proposta in «Uscite da approvare» coi numeri; `tennis_bot_control.stats.uscite_proposte` | Control Room; `tennis_bot_activity` kind `uscita_proposta` |
| tennis ×4 | «approva uscita» con la condizione ancora vera | entro ~15 s ordine d'uscita; attivita' `uscita_eseguita_su_approvazione`; con la condizione caduta la proposta sparisce e niente parte | `tennis_bot_control.params.uscite_approvate`; attivita' |
| scalper | posizione oltre lo stop in manuale | nessun flatten; proposta `stop` in «Uscite da approvare»; con la firma → FLATTENING | `scalper_control.stats.uscite_proposte`; `scalper_activity` |
| tutti | protezioni in manuale | freno/force-flat, pre-KO scalper, «Chiudi» chiudono senza proposta | attivita' dei bot |
