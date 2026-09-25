# AIUTI E MIGLIORIE SPENTI DI DEFAULT O NON COLLEGATI - 25/09/2026 (sessione B, delegato Opus)

Ordine dell'utente (25/09 sera, testuale): «TUTTI I BOT DEVONO AVERE GLI "AIUTI" O LE MIGLIORIE ACCESE DI
DEFAULT, NON VOGLIO TROVARMI CON BOT PARZIALI O SENZA TUTTO LO STACK A DISPOSIZIONE.»

Metodo: SOLA LETTURA su `origin/master` **f4af173** (checkout staccato nel worktree, albero pulito). Nessun codice
toccato, nessun test, nessun DB, nessun processo. Del `.env` del checkout principale ho letto i NOMI e, solo per gli
interruttori di questa lista, se valgono `1` (i valori non booleani li ho riportati come `<altro>`, nessun segreto).
Referti incrociati: `AUDIT_2026-09-24/AUDIT_BOT_DATI_ALGORITMI_2026-09-24.md` (§3.2, §5),
`AUDIT_2026-09-25/MISURA_PUNTO8_2026-09-25.md`, `AUDIT_2026-09-25/VALIDAZIONE_HAZARD.md`,
`AUDIT_2026-09-25/ATLANTE_V4_COLLEGATO.md`, `AUDIT_2026-09-25/ATLANTE_V4_FORZA_ID_SQUADRA.md`,
`AUDIT_2026-09-25/O1_M1_O5_INTEGRABILI_2026-09-25.md`, `AUDIT_2026-09-25/STRADA_UNICA_BANCO_E_PAPER.md`,
`CRONOSTORIA.md` sezione 25/09.

**Attenzione a cosa vuol dire «default».** Qui «default» è il valore nel CODICE. I params salvati sul DB
(`*_control.params`) lo scavalcano, e non li ho letti (vincolo: niente DB). Quindi un interruttore spento nel codice
può essere già acceso sul DB, e viceversa: vedi §7 NON VERIFICATO.

Legenda delle colonne:
- **Stato**: `SPENTO` (spento di default nel codice) / `ENV ASSENTE` (interruttore env non presente nel `.env`) /
  `NON COLLEGATO` (scritto o calcolato, nessuno lo usa) / `NON ALIMENTATO` (collegato, ma manca il dato) /
  `NON COSTRUITO` (proposto dall'audit, niente codice).
- **Tipo**: `TEC` = aiuto tecnico (modello, dato, calibrazione); `SPEC` = condizione di strategia della SPEC o
  scelta dell'utente sulla strategia; `INFRA` = canali, motore ordini, sincronizzazione.
- **Proposta**: `ACCENDERE SUBITO` / `ACCENDERE ALL'ACCENSIONE PAPER` (infrastruttura certificata sul banco, da
  accendere col paper che è la sua certificazione) / `ACCENDERE DOPO MISURA` / `NON ACCENDERE` / `DECISIONE UTENTE`.

---

## 0. Risposta breve

1. **Due aiuti misurati «migliora» sono pronti ma SPENTI: Omega O1 (`lambda_quote_prima`) e O5
   (`model_red_cards`).** L'utente ha già detto SÌ il 25/09 alle 18:15. Il codice è su master (`da21cf8`), la parità
   a interruttori spenti è 3/3, manca solo il flag nei params. Un terzo, **Mike M1** (`veto_p_under35_cal`), è
   misurato «migliora» (come informazione) e deciso SÌ, ma **non è ancora su master**: è solo nella patch
   `AUDIT_2026-09-25/o1_m1_o5_integrabili_2026-09-25.patch`.
2. **L'atlante hazard v4 (A\*, misurato «migliora») è collegato a Safe e Mike ma oggi NON è alimentato.**
   `Betfair/omega/data/hazard_atlas_live.json` non esiste nel checkout principale, quindi i bot usano il ripiego v3.
   Il file lo scrive `HAZARD_ATLAS_SYNC=1`, che nel `.env` c'è dal 25/09, ma non è ancora partito nessun avvio
   dell'app.
3. **La strada unica degli ordini via canale è SPENTA** (`MOTORE_ORDINI_CANALE`, `SAFE_ORDINI_VIA_CANALE`,
   `OMEGA_ORDINI_VIA_CANALE` assenti dal `.env`). È certificata sul banco (profilo rapido, parità coda/canale) e
   D-1 è risolto dall'auto-follow (`edc5540`): va accesa con il paper. Per **Mike la porta non esiste** e ordina in
   REST. Per **Safe tennis il motore non è montato**.
4. **Tutti i canali di LETTURA sono già accesi nel `.env`**: `*_LEGGE_CANALE`, sveglie, `PUNTEGGI_CANALE`,
   `ESITI_ORDINI_CANALE`, `*_CANALE_POSIZIONI`, `TENNIS_BOT_CANALE`, `SAFE_SCAN_CANALE`, `SAFE_BOT_GIRO_VELOCE`.
   Mancano `SCALPER_CANALE` e `TENNIS_RUNNER_SVEGLIA_CANALE`.
5. **Alcuni aiuti restano spenti per un NUMERO e non vanno accesi**: S2 (calibrazione delle uscite Safe), X1 (bias
   calibrato dello scalper), O6 (coda di Omega, nulla da correggere), theta (EV− in 18/18 varianti), M2 (dato
   inesistente).
6. **Alcuni sono condizioni della SPEC spente per scelta dell'utente**: Safe `requireControl` (Q2 = NO il 25/09),
   `base_control_exit`, `tennis_exit_on_lost_game`, e le uscite automatiche di Omega (V3 «uscita a proposta», 17/09).
   Si accendono solo su suo ordine.

---

## 1. OMEGA

| # | Interruttore / parametro | Default (file:riga) | Cosa fa se acceso | Stato | Misurato? | Tipo | Rischio | Proposta |
|---|---|---|---|---|---|---|---|---|
| OM1 | `lambda_quote_prima` (O1) | `False`, `Betfair/omega/omega_config.py:106`; letto a `omega_service.py:1058` | Nella catena dei lambda le quote 1X2 pre-KO devigate passano DAVANTI alla fixture del DB. La fixture resta il ripiego. Cambia i lambda di circa il 47 % delle partite | SPENTO | **MIGLIORA**: fuori campione unito (734 partite) log-loss CS FT −0,0238 [−0,0450; −0,0038], HT −0,0186 [−0,0338; −0,0050]; estensione 17→23/09 −0,119 [−0,246; −0,027] (`MISURA_PUNTO8` §1) | TEC | Basso: nessuna lettura in più (anzi meno). Parità a interruttore spento 3/3 scenari (`certifica omega 35760084`, cronostoria h20:00). Replay A/B a interruttore ACCESO non eseguito | **ACCENDERE SUBITO** (utente SÌ h18:15): params Omega `{"lambda_quote_prima": true}` |
| OM2 | `model_red_cards` (O5) | `False`, `omega_config.py:293`; `omega_engine.py:1148`, `omega_proposte.py:384` | I rossi del feed entrano nel V3 con i moltiplicatori GLOBALI di `inplay_intensity_by_league.json`, sia in ingresso sia in uscita | SPENTO | **MIGLIORA** su campione piccolo: 77 partite dal 30/06, al primo rosso log-loss CS FT −0,113 [−0,187; −0,046] (`MISURA_PUNTO8` §2) | TEC | Medio-basso: tocca solo le partite con rosso, e l'IC è largo | **ACCENDERE SUBITO** (utente SÌ h18:15 «se migliora aggiungilo»): `{"model_red_cards": true}` |
| OM3 | O3: totale gol del ripiego `pre_ko` dalla linea O/U bookmaker (oggi dal solo 1X2, `omega_model.py:131-142`) | - | Lambda pre-KO più informati. **Con OM1 acceso** il ramo `pre_ko` diventa PRIMARIO per metà delle partite, quindi questa voce pesa di più | NON COSTRUITO | Mai misurato | TEC | Medio: il bookmaker non è Betfair, il margine va devigato | **ACCENDERE DOPO MISURA** (log-loss CS sulle stesse 2.072 partite di O1) |
| OM4 | O4: stessa P in ingresso e in uscita. `_p_del_bancato` usa la P GREZZA del modello, senza fusione col mercato e senza veto empirico | `omega_proposte.py:471-507` | Le proposte d'uscita ragionano con la stessa P con cui si è entrati | NON COSTRUITO | Mai misurato | TEC | Basso: cambia solo le proposte | **ACCENDERE DOPO MISURA** (banco: proposte generate sugli stessi scenari) |
| OM5 | `uscite_protezione` | `"avvisa_e_proponi"`, `omega_config.py:309` | Le uscite già calcolate (`blocca_il_profitto`/`protezione`/`cap`/`rischio`) le esegue il bot da solo (`"automatico"`) | SPENTO (unico bot con le uscite automatiche spente di default: Mike `config.py:238`, Safe e scalper sono `True`) | Non è un aiuto misurabile: è CHI esegue | SPEC (mandato V3 del 17/09: «l'uscita è una proposta») | Alto: chiude posizioni senza firma | **DECISIONE UTENTE** (in tensione con l'ordine «tutto acceso»: va chiesto esplicitamente) |
| OM6 | `proposta_p_lose_max_pct` | `0.0` = spenta, `omega_config.py:300`; `omega_proposte.py:405` | Propone l'uscita «rischio» sopra una P di perdita massima | SPENTO | Mai misurato | SPEC (soglia nuova; regola dell'utente «nessuna soglia nuova di iniziativa», commento `:294-299`) | Medio | **DECISIONE UTENTE** (serve il valore) |
| OM7 | `model_calibration` (O6) | `"off"`, `omega_config.py:73` | Applica il calibratore condiviso di Safe alla P di Omega | SPENTO. **Inerte anche se acceso**: in V3 la selezione usa solo `parametri_v3` (`omega_config.py`, `def parametri_v3`); il calibratore entra solo nel v2 (`omega_service.py:1281`) e nel green-up v2 (`:6085`) | **NON MIGLIORA**: P fusa calibrata entro l'IC in tutte le fasce, fascia 1-2 % 0,95 [0,44; 1,55] (`MISURA_PUNTO8` O6). Inoltre il calibratore è addestrato sulle P di Safe, non su quelle di Omega (`:66-72`) | TEC | - | **NON ACCENDERE** |
| OM8 | Tabella di k misurata (`k_tab`) | passata `None`, `omega_service.py:1505` | Margine per secchio dalla tabella del 16/09 (vale 2,0 in ogni secchio) | SPENTO per scelta dichiarata (17/09) | Misurato: il bias prudente in gioco è 1,11 (M4M5M6 §2.3) | SPEC (k = 1,11 deciso sui dati) | Accenderla riporterebbe k a 2,0 in silenzio | **NON ACCENDERE** |
| OM9 | `poll_interval_s` 20 s contro 5 s | `20`, `omega_config.py:35` | Giro più frequente | Oggi con `OMEGA_LEGGE_CANALE=1` il canale sveglia il giro con un pavimento di 5 s (`omega_service.py:522-546`), quindi il 20 s vale solo come ripiego | Procedura A/B pronta (`MISURA_PUNTO8` §8), non eseguita | INFRA | Carico DB | **DECISIONE UTENTE** (rimandata da lui il 25/09 h16:10) |
| OM10 | Parametri v2 accesi ma INERTI in V3: `model_tail_factor` 1,3 (`:96`), `select_cost_aware` (`:89`), `select_k_se` 0 (`:112`), `model_lambda_cv` (`:109`) | - | Nulla in V3 (`strategy_version` 3, `:220`) | Acceso ma inerte | - | TEC (motore v2) | - | Nessuna azione. Da sapere: in UI sembrano «aiuti accesi» ma in V3 non fanno niente |

Già accesi e alimentati (nessuna azione): `model_empirical="veto"` (`:78`, transizioni ricostruite e PUBBLICATE il
25/09 h17:20), `lambda_market_grid`, `lambda_live_fallback`, `v3_fusione_mercato="auto"`, `model_use_yellow_cards`,
`omega_live_via_flumine`. Omega non consuma hazard, solo `h2h_hint` nell'advisor, che è solo UI.

---

## 2. MIKE

| # | Interruttore / parametro | Default (file:riga) | Cosa fa se acceso | Stato | Misurato? | Tipo | Rischio | Proposta |
|---|---|---|---|---|---|---|---|---|
| MK1 | `veto_p_under35_cal` (M1) | **Non esiste su master.** Oggi `p_under35_cal` viene calcolata (`Betfair/mike/dossier.py:97`) e non la legge nessuno. L'interruttore è nella patch `o1_m1_o5_integrabili_2026-09-25.patch`, con soglie 0,807/0,684/0,514/0,385/0,275 per quota | Veto sull'ingresso live/HOLD con la P calibrata dell'Under 3.5 | NON COLLEGATO (patch non integrata: aspetta l'avviso «Mike libero») | **MIGLIORA come informazione**: Brier −0,0093 [−0,0155; −0,0034] su 243 partite. **Veto sul replay (parte B) MAI misurato** (`MISURA_PUNTO8` M1) | TEC | Medio: la P calibrata esiste per circa il 28-33 % delle partite; il veto cambia gli ingressi | **ACCENDERE SUBITO dopo l'integrazione** (utente SÌ h18:15, con replay iper rapido `certifica mike 35760084 base,riavvio`): `{"veto_p_under35_cal": true}` |
| MK2 | Atlante v4 (A\*) in `live_frame` | collegato (`1ba167e`, `82cf793`) | Hazard dei prossimi 3' con recupero per lega e forza delle squadre | NON ALIMENTATO: `hazard_atlas_live.json` assente, quindi ripiego v3 dichiarato (`ATLANTE_V4_COLLEGATO` §6) | **MIGLIORA**: log-loss 3' −0,00156 [−0,00224; −0,00082]; recupero 2T −7,3 % (`VALIDAZIONE_HAZARD` §0) | TEC | Basso; cambia i tempi di copertura (Mike usa `max(atlante, modello)`) | **ACCENDERE SUBITO = avviare l'app** con `HAZARD_ATLAS_SYNC=1` (già nel `.env`) e verificare nei log `[atlante-domanda]` che il blocco v4 venga scritto |
| MK3 | `p4_model` solo in telemetria; M3 pavimento di P4 dal prior di lega | `mike/engine.py:1174` (solo `tele`) | P(4 gol esatti) di modello o di lega nell'uscita in perdita | NON COLLEGATO / NON COSTRUITO | Mai misurato | TEC | Basso | **ACCENDERE DOPO MISURA** (banco A/B sull'uscita in perdita) |
| MK4 | `p_over45_cal` (M2) | mai valorizzata, `dossier.py:72` | Terza fonte in `blend_totals` | NON ALIMENTATO | **NON REALIZZABILE**: `over_4_5` non esiste nel DB (0 righe su 20.883) | TEC | - | **NON ACCENDERE** (manca il dato) |
| MK5 | `MIKE_USE_FLUMINE_QUEUE` / porta ordini via canale | `False`, `mike/service.py:696` (`env_bool`, default False). Il `.env` non ce l'ha | Gli ordini di Mike passano dalla coda flumine o dal canale (paper uguale al live) | SPENTO / NON COSTRUITO: nessuna porta a comandi, `execute_place` sempre in REST (`STRADA_UNICA` F7) | Mai certificato | INFRA | Medio: le appoggiate, il submin e il bet delay vanno riportati sul canale | **ACCENDERE DOPO** costruzione e certificazione (lavoro da ordinare) |

Già accesi (nessuna azione): `loss_exit_mode="model"` (`config.py:251`), `loss_exit_p4_prudent`,
`cashout_smart_enabled`, `cover_enabled`, `second_entry_enabled`, `reentry_enabled`, `uscite_automatiche` (`:238`),
`MIKE_LEGGE_CANALE=1`, `MIKE_SVEGLIA_CANALE=1`.

---

## 3. SAFE (calcio, tennis, opportunità)

| # | Interruttore / parametro | Default (file:riga) | Cosa fa se acceso | Stato | Misurato? | Tipo | Rischio | Proposta |
|---|---|---|---|---|---|---|---|---|
| SF1 | Atlante v4 nel controincrocio hazard delle opportunità (S1) | collegato: `OpportunityModel(params, atlas=_atlante_hazard())`, `Betfair/safe_strategy/bot_service.py:9373`; v4 in `opportunity.py` `_hazard_check` | Confidenza dimezzata o scarto se il modello diverge dall'atlante (`hazard_warn` 0,30 / `hazard_drop` 0,60) | NON ALIMENTATO: manca il file live, quindi ripiego v3 | **MIGLIORA** (A\*): le divergenze spurie contro il modello Safe scendono dal 10 % al 5 % (`VALIDAZIONE_HAZARD`) | TEC | Basso: tocca solo le PROPOSTE | **ACCENDERE SUBITO = primo avvio con `HAZARD_ATLAS_SYNC=1`**, come MK2 |
| SF2 | Catena dei lambda di Safe senza i params di Omega | `bot_service.py:6658-6660`: `_prematch_lambdas(db, event_id, payload)` senza `params`, quindi `lambda_quote_prima` vale sempre False | Con O1 acceso in Omega anche Safe (uscite e opportunità) avrebbe le quote pre-KO davanti alla fixture | NON COLLEGATO (accendere O1 in Omega NON cambia Safe) | Mai misurato sulle P di Safe. Misurato per Omega (OM1). Coerente con `VALIDAZIONE_HAZARD`: i λ di `fixture_predictions` predicono peggio di un Poisson-Elo | TEC | Medio: cambia le P di uscita e le opportunità | **ACCENDERE DOPO MISURA** (Brier delle P d'uscita con la catena O1, stesso strumento di S2) oppure **DECISIONE UTENTE** |
| SF3 | Calibrazione delle P d'USCITA (S2) | `_exit_model` costruisce `OpportunityModel(params)` e usa il book grezzo (`bot_service.py:4072`, `:4263`); `calibrate` solo per le opportunità | P d'uscita calibrate | NON COLLEGATO | **NON MIGLIORA**: Brier +0,0018 [−0,0023; +0,0057], stima puntuale peggiore (14 partite, `MISURA_PUNTO8` S2) | TEC | - | **NON ACCENDERE** (rimisurare quando le registrazioni saranno molte di più) |
| SF4 | `dynamic_cal` (`_CALIBRATION_ENABLED`) | `False`, `Betfair/stream/engine/live_engine_pro.py:113` | Calibrazione dinamica delle probabilità del motore live | SPENTO (costante nel codice, senza interruttore) | Costruita su P PRE-MATCH: applicarla in gioco non è validato (`:110-112`); la calibrazione affine S2 non migliora | TEC | Medio | **NON ACCENDERE** (prima una misura in gioco) |
| SF5 | `use_pressure` | `False`, `opportunity.py:91` | Corner e gialli diventano moltiplicatori dei lambda (±25 %) | SPENTO | Mai misurato. `opp_calibration.json` è stimata a pressione NEUTRA (`:86-90`) | TEC (vicino alla SPEC «controllo del gioco») | Medio-alto: cambia i lambda sotto una calibrazione stimata senza pressione | **ACCENDERE DOPO MISURA** (e dopo aver ricalibrato `opp_calibration` a pressione accesa) |
| SF6 | `requireControl` (Base, Esatto, Punta) | `False`, `Betfair/safe_strategy/engine.py:192`, `:216`, `:271`; UI `frontend/src/lib/safeStrategy.ts:229,240,256` | «La favorita deve avere il controllo del gioco» (SPEC) | SPENTO | Mai misurato (segnale povero: solo corner e gialli) | **SPEC** | Alto | **DECISIONE UTENTE, già presa: Q2 = NO** (25/09 h15:50, «nessuno strumento per vedere le partite»). Resta spento |
| SF7 | `base_control_exit` | `False`, `Betfair/safe_strategy/exits.py:78` | Uscita BASE «il controllo passa alla sfavorita» | SPENTO | Mai misurato | SPEC (stesso dato di SF6) | Alto: chiude posizioni su un dato di copertura ignota | **DECISIONE UTENTE** (coerente con Q2 = NO: resta spento) |
| SF8 | `tennis_exit_on_lost_game` | `False`, `exits.py:98` | Esce se il leader perde un game | SPENTO | Mai misurato | SPEC (uscita opzionale del manuale) | Medio | **DECISIONE UTENTE** |
| SF9 | `auto_trade_opportunities` / `_anomalies` / `_combos` / `_tennis` | `False`, `bot_service.py:165-169` | Storicamente: piazzamento automatico delle opportunità | SPENTO e INERTE: dal 18/09 (decisione «B») non piazzano più nulla; le opportunità sono solo PROPOSTE (`:170-176`) | - | SPEC (operatività, non un aiuto) | Alto | **DECISIONE UTENTE** (se vuole il modello a mercato da solo serve un ordine esplicito e una certificazione) |
| SF10 | Safe tennis: hold per giocatore | `hold_prior` 0,75, `Betfair/safe_strategy/tennis_opportunity.py:77`; `serve_data.csv` cercato in `Betfair/stream/tennis_scalper/tennis_serve_data.py:23`, ASSENTE (anche nel checkout principale) | Hold reale per giocatore nel Markov | NON ALIMENTATO | Non misurabile: nessun dato storico tennis nel DB | TEC | - | **NON ACCENDERE** (manca il dato. Fonte da decidere: DECISIONE UTENTE) |
| SF11 | `SAFE_ORDINI_VIA_CANALE` | spento se non scritto (`porta_ordini.py:69`, `:734`, `acceso()` `:134`); ASSENTE dal `.env` | Safe calcio manda i comandi sul `/comando/safe` del motore del runner (strada unica, al ms) | ENV ASSENTE | Banco: parità coda/canale su 1 scenario d'ordine + 11 scenari di trasporto; replay miei rapidi su 35760084 safe_base 11/11 + parità (cronostoria h19:20). Matrice completa `--scenari tutti --trasporto entrambi` NON eseguita | INFRA | Medio: primo uso reale. D-1 risolto da `edc5540` (auto-follow, nessun rifiuto «mercato non seguito») | **ACCENDERE ALL'ACCENSIONE PAPER** (passo 2, insieme a INF1: punto di ripresa 26/09) |
| SF12 | `SAFE_TENNIS_ORDINI_VIA_CANALE` | spento, `porta_ordini.py:70`, `:731` | Safe tennis via canale | ENV ASSENTE / NON COSTRUITO lato runner: il runner tennis non monta il motore (`STRADA_UNICA` F8); il ref è corretto da F1 (`safe_tennis-t`) | - | INFRA | Alto: ogni comando riceverebbe `motore_non_attivo` | **NON ACCENDERE** finché il motore non è montato nel runner tennis (lavoro da ordinare) |

Già accesi (nessuna azione): `requireSelection` = **True** (Q7, `engine.py:237`); `vetoCampionati` (`:213`, `:268`,
`:279`); `red_card_fav_exit`; `tennis_take_profit_next_game`; uscite a modello (`hold_max_risk` e seguenti);
`SAFE_BOT_LEGGE_CANALE`, `SAFE_BOT_SVEGLIA_CANALE`, `SAFE_BOT_GIRO_VELOCE`, `SAFE_SCAN_CANALE` = 1; calibrazione
delle OPPORTUNITÀ `calibration="auto"` (`opportunity.py:327`), che però è alimentata da `opp_calibration.json` del
10/09 su 32 partite (dato vecchio, vedi §6). Nota di igiene: il commento in `frontend/src/lib/safeStrategy.ts:132`
dice ancora «Default OFF» per `requireSelection`, ma il valore a `:243` è `true`.

---

## 4. I 4 BOT TENNIS (scalper, pro, flb, swing)

| # | Interruttore / parametro | Default (file:riga) | Cosa fa se acceso | Stato | Misurato? | Tipo | Rischio | Proposta |
|---|---|---|---|---|---|---|---|---|
| TN1 | `surface` di tennis_pro (T1) | `"grass"`, `Betfair/stream/tennis_scalper/tennis_pro_bot.py:116`, quindi `_lay_rev=False` (`:119`) e 3 setup su 6 SPENTI: `enable_serving_set` (`:168`), `enable_double_break` (`:173`), `enable_compressed_fav` (`:184`) | La superficie vera accende i setup di reversione su terra e WTA | NON COLLEGATO: nessun runner la passa (grep «surface» in `tennis_live/`: 0 risultati; `competition_name` è già letto a `tennis_bot_service.py:145`) | **NON MISURABILE** coi dati di oggi: 0 eventi su 83 con superficie nota (`MISURA_PUNTO8` T1) | TEC, ma accende 3 SETUP mai certificati, quindi di fatto una modifica di strategia | Medio-alto | **DECISIONE UTENTE** (proposta: registrare la superficie da `competition_name` senza accendere i setup, misurare, poi decidere) |
| TN2 | `p_match` Markov come veto per flb e pro (T2) | calcolato solo per la UI, `Betfair/stream/tennis_live/tennis_runner.py:285-290` | Non laiare un favorito ≤ 1,10 se il Markov lo dà sopra 1/1,10 più la commissione | NON COLLEGATO | Mai misurato | TEC | Medio: l'hold stimato dai break è grezzo (e `serve_data.csv` manca, SF10) | **ACCENDERE DOPO MISURA** (banco A/B `certifica` tennis_flb / tennis_pro) |
| TN3 | tennis_pro `trend`, `adapt`, `maker` | `False`, `tennis_pro_bot.py:123`, `:127`, `:148` | Varianti di direzione (cavalca o fade) e d'ingresso | SPENTO | Nessun verdetto fuori campione nel repo per queste varianti (la bibbia tennis dà l'in-play 1-tick falsificato) | SPEC (varianti di strategia, non aiuti) | Alto | **DECISIONE UTENTE** |
| TN4 | `TENNIS_RUNNER_SVEGLIA_CANALE` | spento, `Betfair/stream/tennis_live/canale_bot_tennis.py:72`, `:328-329`; ASSENTE dal `.env` | Il worker di armatura del runner si sveglia dal 47337 (clic → armamento al ms, pavimento 1 s) invece di aspettare il poll | ENV ASSENTE | Test del modulo presenti; certificazione in paper NON VERIFICATA | INFRA (regola del 23/09 «tutto dai canali») | Basso | **ACCENDERE ALL'ACCENSIONE PAPER** |

Già accesi: `TENNIS_BOT_CANALE=1`, `TENNIS_BOT_SVEGLIA_CANALE=1`, `TENNIS_ISCRIZIONE_A_CALDO` (acceso di serie,
`iscrizione_a_caldo.py:76-77`), `uscite_automatiche=True` sui bot (`tennis_pro_bot.py:90`). I parametri di
microstruttura dello scalper tennis (`allow_inplay`, `require_oscillation`, `pipeline`, `exact_exits`…,
`tennis_scalper_bot.py:285-446`) sono parametri di STRATEGIA, non aiuti: li ho esclusi.

---

## 5. SCALPER CALCIO (maker / sniper / theta)

| # | Interruttore / parametro | Default (file:riga) | Cosa fa se acceso | Stato | Misurato? | Tipo | Rischio | Proposta |
|---|---|---|---|---|---|---|---|---|
| SC1 | Bias con P calibrate (X1: `ml_post_calibration`, `poisson_calibration`, `direction_pagella`) | `Betfair/stream/scalper/bias_resolver.py:79-90`, `:193-204` (P grezze) | Direzione del maker da P calibrate | NON COSTRUITO | **PEGGIORA**: Brier ML +0,0024 [+0,0008; +0,0041] su 16.172 partite; 0 bias cambiati su 2 (`MISURA_PUNTO8` X1) | TEC | - | **NON ACCENDERE** |
| SC2 | `mode` `bias`/`both` (bias grezzo, consenso ML+Poisson) | `"auto"`, `scalper_session.py:37`; strategia di default dell'auto-mode `"maker"`, `scalper_service.py:457` | Il maker lavora solo nella direzione concordata dai motori | SPENTO | Solo in campione: 4/4 casi di consenso, caso peggiore −0,31 € (`SCALPER_BOT_DOSSIER.md:367-375`). Fuori campione MAI | TEC | Medio: pochissime partite con consenso | **ACCENDERE DOPO MISURA** (fuori campione sulle registrazioni) |
| SC3 | `sniper_mode` | spento (toggle UI, whitelist `scalper_session.py:80`, letto a `:657`) | Sniper in-play sulla linea (gol+1).5 | SPENTO | +0,99 su 14 eventi, «MA out-of-sample obbligatorio» (`BIBBIA_SCALPER_CALCIO.md:481`) | SPEC (strategia) | Medio | **DECISIONE UTENTE** (prima il fuori campione) |
| SC4 | `theta_mode` | spento (toggle UI, `scalper_session.py:84`) | Theta scalper in-play | SPENTO | **EV− in TUTTE le 18 varianti** (miglior cella C7 −22,07; `theta_bot.py:9-13`) | SPEC | Perdita attesa | **NON ACCENDERE** (in paper solo per raccolta dati, se lo vuole l'utente) |
| SC5 | Punteggio di sniper, theta e HT da `live_now` a polling invece che dal canale | `scalper_session.py:921`, `:1030`, `:1072` | Punteggio e minuto al ms dal feed unico (regola del 25/09 «UN solo canale dati per tutti i bot») | NON COLLEGATO al canale | - | INFRA | Basso (conta solo con SC3, SC4 o `ht_mode` accesi) | **ACCENDERE DOPO** (da costruire, e solo se si accende SC3 o SC4) |
| SC6 | Atlante v4 per theta | theta usa il lookup v3 dell'atlante condiviso (`hazard_atlas.py:130-145`, `theta_bot.py:16`) | Hazard A\* nel semaforo di theta | NON COLLEGATO a v4 | A\* migliora (vedi MK2) | TEC | - | Nessuna azione finché theta resta spento (SC4) |
| SC7 | `SCALPER_CANALE` | spento, `Betfair/stream/canale_bot.py:136`, `acceso()` `:145`; ASSENTE dal `.env` | Stato del supervisore e delle sessioni sul 47338 (Control Room al ms) | ENV ASSENTE | 118 pytest e 2 mutazioni rosse (cronostoria h15:45); paper no | INFRA | Basso (sola pubblicazione) | **ACCENDERE ALL'ACCENSIONE PAPER** (lo prevede il punto di ripresa 26/09, passo 2) |

`DRY_RUN_ALLA_NASCITA=True` (`auto_mode.py:278`) è una protezione dei soldi, non un aiuto: resta com'è.

---

## 6. INFRASTRUTTURA, DATI E CALIBRAZIONI

### 6.1 Interruttori di processo

| # | Interruttore | Default nel codice (file:riga) | Nel `.env` (25/09) | Cosa fa | Certificato | Proposta |
|---|---|---|---|---|---|---|
| INF1 | `MOTORE_ORDINI_CANALE` | spento se non `"1"`, `Betfair/stream/runner.py:1624-1625` | **ASSENTE** | Il runner calcio monta l'esecutore a evento dei comandi sul 47331 (diario write-ahead) | Banco (strada unica `5139d2b`, R-A e R-B corretti); paper NO | **ACCENDERE ALL'ACCENSIONE PAPER** (passo 1) |
| INF2 | `SAFE_ORDINI_VIA_CANALE` | vedi SF11 | **ASSENTE** | - | - | **ACCENDERE ALL'ACCENSIONE PAPER** (passo 2) |
| INF3 | `OMEGA_ORDINI_VIA_CANALE` | spento, `Betfair/omega/porta_ordini.py:48`, `:68` | **ASSENTE** | Omega su `/comando/omega` | Banco: omega 10 OK + 1 N/A + parità | **ACCENDERE DOPO** aver visto Safe in paper (passo 3, `STRADA_UNICA` §5) |
| INF4 | `SAFE_TENNIS_ORDINI_VIA_CANALE` | vedi SF12 | ASSENTE | - | NO (motore non montato) | **NON ACCENDERE** |
| INF5 | `SCALPER_CANALE` | vedi SC7 | **ASSENTE** | - | test | **ACCENDERE ALL'ACCENSIONE PAPER** |
| INF6 | `TENNIS_RUNNER_SVEGLIA_CANALE` | vedi TN4 | **ASSENTE** | - | test | **ACCENDERE ALL'ACCENSIONE PAPER** |
| INF7 | `HAZARD_ATLAS_SYNC` | spento, `Betfair/stream/scalper/hazard_atlas_sync.py:126` | **1** (messo il 25/09) | Atlante a domanda; scrive il file live col blocco v4 | Test verdi, misura reale lega 135 | Già acceso. Da VERIFICARE al primo avvio (MK2, SF1) |
| INF8 | `HAZARD_ATLAS_MODO` / `HAZARD_ATLAS_SCRIVI_DB` | `domanda` / acceso (`:134`, `:159`) | assenti = default | - | - | Nessuna azione |
| INF9 | `LIVE_TEMPI_ORDINE` | ACCESO di serie (`live_order_worker.py:57`, `live_trading_strategy.py:42`) | assente = acceso | Misura dei 5 tempi dell'ordine (solo log) | `f8b3a7e` | Nessuna azione |
| INF10 | `RUNNER_AUTO_FOLLOW` / `TENNIS_ISCRIZIONE_A_CALDO` | ACCESI di serie (`auto_follow.py:115-119`, `iscrizione_a_caldo.py:76`) | assenti = accesi | - | - | Nessuna azione |
| INF11 | `LIVE_MARKET_TYPES` | vuoto = tutti i tipi, `config_stream.py:169` | assente | Tetto dei mercati per partita seguita a mano | - | **DECISIONE UTENTE** (già elencata nel punto di ripresa) |
| INF12 | Conflate dello stream (1 s → al tick) | `Betfair/safe_strategy/stream.py:22` (dall'audit 24/09) | - | Quote più fresche | Da misurare | **DECISIONE UTENTE** (rimandata da lui il 25/09 h16:10) |
| INF13 | Già accesi nel `.env` | - | `OMEGA/MIKE/SAFE_BOT_LEGGE_CANALE`, `OMEGA/MIKE/SAFE_BOT/TENNIS_BOT_SVEGLIA_CANALE`, `PUNTEGGI_CANALE`, `ESITI_ORDINI_CANALE`, `MIKE/OMEGA/SAFE_CANALE_POSIZIONI`, `TENNIS_BOT_CANALE`, `SAFE_SCAN_CANALE`, `SAFE_BOT_GIRO_VELOCE` = 1 | - | - | Nessuna azione. Nel codice nascono tutti SPENTI (`canale_bot.py:145-152`: acceso solo se scritto): se il `.env` si perde, si spengono tutti |

### 6.2 Atlante hazard: modelli oltre A\*

| # | Voce | Stato | Misurato? | Proposta |
|---|---|---|---|---|
| HZ1 | **B1** (LightGBM sulla stessa verità) | NON COSTRUITO in produzione | **MIGLIORA anche su A\***: −0,00107 [−0,00160; −0,00056] sul 3', 75-89' −0,00157 [−0,00280; −0,00030] (`VALIDAZIONE_HAZARD` §0) | **DECISIONE UTENTE** (costo: action di riaddestramento. Gli id squadra ora sono collegati, `82cf793`) |
| HZ2 | Livello squadre del v3 (by_team) | acceso nel ripiego v3 quando i nomi coincidono | **PEGGIORA**: +0,00120 [+0,00066; +0,00173] | Con il v4 alimentato non si usa più. Se il ripiego v3 resta frequente: **DECISIONE UTENTE** se togliere il livello squadre dal ripiego |
| HZ3 | Forza globale contro forza per lega; `BETA_DEFAULT` contro eta 0,035 | decisioni aperte (punto di ripresa 26/09, §5) | parzialmente | **DECISIONE UTENTE** |

### 6.3 Calibrazioni e motori del DB: chi li usa e chi no

| Fonte | Chi la usa oggi | Misura | Proposta |
|---|---|---|---|
| `fixture_predictions.tactical_engine_json` (TacticAI) → lambda | Primo gradino della catena per Omega (`stream/db.py:211-262`), per Mike e per il runner; Safe ci passa attraverso la catena di Omega | M2 (17/09): nessuna fonte DB batte le quote devigate; O1: le quote prima MIGLIORA | Accendere OM1 (le quote prima). Per Safe vedi SF2 |
| `poisson_calibration` (tabella DB) | Nessun bot direttamente. Entra in `db_json_analisi.markets_calibrated`, da cui Mike ricava `p_under35_cal` | MK1: MIGLIORA come informazione | Collegare con MK1 |
| `ml_post_calibration`, `direction_pagella` | Nessun bot | X1: PEGGIORA | **NON ACCENDERE** |
| `data/opp_calibration.json` (isotonica, 10/09, 32 partite) | Safe OPPORTUNITÀ (acceso) | Per le uscite (S2): NON MIGLIORA | Tenerla sulle opportunità. Ricalibrarla sulle registrazioni cresciute: **ACCENDERE DOPO MISURA** |
| `dynamic_cal.json` | nessuno (SF4 spenta) | pre-match, mai validata in gioco | **NON ACCENDERE** |
| Calibratore condiviso in Omega (`model_calibration`) | nessuno (OM7) | O6: niente da correggere | **NON ACCENDERE** |
| `analytics_signals`, `engine_signals`, `match_odds`, team stats, lineups | nessun bot | M2: peso 0 fuori campione; `engine_signals` fermo e lasciato così dall'utente | **NON ACCENDERE** |

---

## 7. NON VERIFICATO

1. **Params effettivi sul DB** (`omega_control`, `mike_control`, `safe_strategy_bot_control`, `scalper_control`,
   `tennis_bot_control`): non letti. Un interruttore spento nel codice può essere già acceso lì (o il contrario).
   Serve una SELECT in sola lettura sui `params` delle righe di controllo prima di dire all'utente «è spento».
2. **Primo avvio con `HAZARD_ATLAS_SYNC=1`**: se il file `hazard_atlas_live.json` viene scritto con il blocco `v4`, e
   in quanto tempo le leghe osservate lo ricevono. Oggi il file non c'è.
3. **Effetto di OM1 e OM2 ACCESI sul banco**: la parità è stata provata solo a interruttori SPENTI. A interruttori
   accesi non c'è un replay A/B: la misura è offline (log-loss).
4. **M1 parte B** (il veto sul replay `certifica mike`): mai eseguita.
5. **TN4 e SC7 certificati in paper**: ho visto solo le dichiarazioni dei test nella cronostoria, non li ho rilanciati
   (il perimetro era di sola lettura).
6. **`serve_data.csv`**: cercato nel worktree e nel checkout principale (`Betfair/stream/tennis_scalper/`), assente. Non
   ho cercato altrove sul disco.
7. **SF2**: che Safe chiami la catena di Omega senza `params` l'ho letto a `bot_service.py:6658-6660`. Non ho
   verificato se esistono altri chiamanti con `params`.
8. **INF12**: la riga del conflate (`safe_strategy/stream.py:22`) viene dall'audit del 24/09, non l'ho riletta oggi.

---

## 8. Riepilogo per l'utente

**Accendere subito** (misurati «migliora», decisione già presa o costo zero):
- Omega `lambda_quote_prima` (O1) e `model_red_cards` (O5): params Omega `{"lambda_quote_prima": true, "model_red_cards": true}`.
- Mike `veto_p_under35_cal` (M1): prima integrare la patch e fare il replay iper rapido, poi `{"veto_p_under35_cal": true}`.
- Atlante v4 (Safe e Mike): basta avviare l'app (il `HAZARD_ATLAS_SYNC=1` c'è già) e verificare che il file live abbia il blocco v4.

**Accendere all'accensione in paper** (infrastruttura certificata sul banco):
- `MOTORE_ORDINI_CANALE=1` e `SAFE_ORDINI_VIA_CANALE=1`; poi `OMEGA_ORDINI_VIA_CANALE=1` dopo aver visto Safe.
- `SCALPER_CANALE=1` e `TENNIS_RUNNER_SVEGLIA_CANALE=1`.

**Accendere dopo una misura** (mai misurati):
- Omega: O3 (O/U bookmaker nel ripiego pre-KO), O4 (stessa P in ingresso e in uscita).
- Mike: P4 di modello o di lega nell'uscita in perdita (M3).
- Safe: catena lambda con le quote prima anche per Safe (SF2), `use_pressure`, ricalibrazione di `opp_calibration`.
- Tennis: `p_match` come veto (T2).
- Scalper: bias grezzo (`mode` bias/both) fuori campione.
- Mike via canale e punteggi dello scalper dal canale: prima vanno costruiti.

**Da decidere (utente)**:
- Omega `uscite_protezione` automatiche (oggi a proposta per mandato V3) e `proposta_p_lose_max_pct`.
- Safe `requireControl` e `base_control_exit` (Q2 = NO: restano spenti se non cambia idea), `tennis_exit_on_lost_game`, `auto_trade_*`.
- Tennis: superficie di tennis_pro (accende 3 setup mai certificati), `trend`/`adapt`/`maker`.
- Scalper: `sniper_mode`.
- Hazard: B1 LightGBM, forza, eta.
- `LIVE_MARKET_TYPES`, conflate, giro Omega 20 s contro 5 s.

**Non accendere** (con il numero):
- S2 calibrazione delle uscite Safe: Brier +0,0018.
- X1 bias calibrato: Brier +0,0024.
- O6 / `model_calibration`: nulla da correggere, e inerte in V3.
- `dynamic_cal`: pre-match, non validata in gioco.
- `k_tab`: riporterebbe k a 2,0.
- Theta: EV− in 18/18 varianti.
- M2 `p_over45_cal`: il dato non esiste.
- `serve_data.csv`: il dato non esiste.
- `SAFE_TENNIS_ORDINI_VIA_CANALE`: il motore non è montato.
- `ml_post_calibration`, `direction_pagella`, `analytics_signals`: peso 0 o peggiora.
