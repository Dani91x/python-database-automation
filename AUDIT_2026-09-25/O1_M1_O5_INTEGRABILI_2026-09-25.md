# O1 + M1 + O5 INTEGRABILI - 25/09/2026 (delegato Opus, sessione B)

Mandato: consegnare INTEGRABILI le tre modifiche decise dall'utente alle 18:00, ognuna
dietro il suo interruttore:
- O1 Omega, quote pre-KO PRIMA della fixture nella catena lambda: `lambda_quote_prima`;
- M1 Mike, veto sull'ingresso live con la P calibrata dell'Under 3.5: `veto_p_under35_cal`;
- O5 Omega V3, cartellini rossi nel modello con i moltiplicatori GLOBALI: `model_red_cards`.

**AGGIORNAMENTO 25/09 sera - DEFAULT ACCESI.** Ordine dell'utente (testuale, via il
coordinatore): «per TUTTI i bot i valori statistici e gli aiuti devono essere di default
accesi». I tre interruttori sono ora **DEFAULT ACCESO** (sez. 0). Dove sotto (sez. 1-3,
scritte prima) si legge «default spento» vale la sez. 0; le parti «spento = identico a
prima» restano vere, ma ora si provano passando lo SPENTO per esteso.

Worktree `agent-aac4a32e334c9b596`, base `origin/master` **43e1468** (contiene 1ba167e
«atlante v4»). Niente commit, niente `git add`, niente replay, niente DB vero (ogni pytest
con `SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x`).

**Patch unica pronta**: `AUDIT_2026-09-25/o1_m1_o5_integrabili_2026-09-25.patch` (base
43e1468, **17 file, +1373 -43**, fine riga LF; `git apply --check --reverse` nel worktree
= OK). Si rigenera con `python AUDIT_2026-09-25/genera_patch_o1_m1_o5.py`. ATTENZIONE: se
la patch passa da un commit e torna in un checkout con `core.autocrlf=true` diventa CRLF e
`git apply` la rifiuta (e' successo con la patch O1/M1 di stamattina, vedi sez. 1):
applicarla dal file del worktree, o riconvertirla in LF prima.

## REBASE su origin/master 099412c + d771d05 e Safe (25/09 sera, ultimo giro)

**Base**: `origin/master` = **d771d05** (fetch del 25/09 sera; contiene da21cf8 = parte Omega
di O1/O5 a default SPENTI, 82cf793 = id squadra in `mike/dossier.py`/`mike/db.py`,
099412c = punto 6 su `omega_service.py`/`bot_service.py`). Il mio lavoro e' un commit
WIP locale (`git add` con percorsi espliciti) ribasato sopra; niente push.

**Patch**: `AUDIT_2026-09-25/o1_m1_o5_default_acceso_su_d771d05.patch` = `git diff
origin/master` (patch escluse), rigenerabile con `genera_patch_o1_m1_o5.py`. La patch
vecchia `o1_m1_o5_integrabili_2026-09-25.patch` (tracciata sul master, base 43e1468) e'
SUPERATA: non va applicata.

**Conflitti risolti**
| File | Tipo | Come |
|---|---|---|
| `Betfair/omega/omega_config.py` | 3 blocchi | lato mio (default ACCESO, commenti) |
| `Betfair/omega/omega_service.py` | 2 blocchi (docstring e lettura di `lambda_quote_prima`) | lato mio (chiave assente = default whitelist); il punto 6 di 099412c e' fuori dai blocchi, fuso da git e intatto |
| `frontend/src/lib/omega.ts` | 4 blocchi | lato mio (default `true` e hint) |
| `Betfair/mike/dossier.py` | 1 blocco (docstring + dict di `build_prematch`) | UNIONE: `home_team_id`/`away_team_id` di 82cf793 + `p_under35_fonte` di M1 |
| `Betfair/omega/tests/test_o1_quote_prima_2026_09_25.py`, `test_o5_rossi_v3_2026_09_25.py` | add/add | versione mia (superset: default acceso + ramo spento esplicito) |
| `AUDIT_2026-09-25/O1_M1_O5_INTEGRABILI_2026-09-25.md`, `genera_patch_o1_m1_o5.py`, `mutazioni_o5_rossi_2026-09-25.py` | add/add | versione mia (aggiornata) |
Senza conflitti: `mike/config.py`, `engine.py`, `feed.py`, `service.py`, `mike.ts`,
`test_omega_certificazione_2026_09_11.py`, `o1_catena_lambda.py`, test M1.

**Safe (autorizzato dall'utente e dall'altra sessione)**: `Betfair/safe_strategy/bot_service.py`
`resolve_event_lambdas` chiamava `omega_service._prematch_lambdas(db, event_id, payload)`
SENZA params. Ora passa `params=_omega_params_catena_lambda()` = `omega_config.resolve_params({})`
(nuova funzione accanto, `{}` se Omega non e' importabile). Nient'altro di Safe cambia;
punto 6 e D3/D7 di admin-26 intatti (il file non era in conflitto). Nota: col mio
`omega_service` anche la chiamata senza params avrebbe gia' preso il default acceso;
ora e' esplicito e governato dalla whitelist di Omega.
- `Betfair/safe_strategy/tests/test_bot_service.py`: `OmegaStub._prematch_lambdas` portato
  alla firma del vero (`*, state=None, params=None`) e registra i params (finto = vero).
- NUOVO `Betfair/safe_strategy/tests/test_safe_lambda_quote_prima_2026_09_25.py` (4 test,
  catena VERA di Omega, finti del test O1): default -> `pre_ko_odds` e nessuna lettura
  della fixture; Safe passa params risolti con `lambda_quote_prima` True; params con
  `lambda_quote_prima=False` -> fixture prima come oggi; senza quote -> fixture.
- Falsificazione (`AUDIT_2026-09-25/mutazioni_safe_lambda_2026-09-25.py`): S1 params tolti
  dalla chiamata -> ROSSO 2 failed; S2 Safe passa lo spento -> ROSSO 2 failed; ripristino OK.
- Esistenti (`test_bot_service`, `test_audit_2026_09_11`, `test_atlante_v4_forza_id_squadra`):
  **prima (file di HEAD) 277 passed, dopo 277 passed**. Tutti i 43 file di test Safe che
  importano `bot_service`/opportunita': **1291 passed, 3 skipped, 1 xfailed**.

**Numeri dopo il rebase (default ACCESI)**
- 3 file nuovi + `test_omega_certificazione_2026_09_11.py`: **116 passed**.
- Omega (50 file che importano i moduli toccati, inclusi i 2 nuovi, + 4 del banco):
  **1291 passed, 3 skipped** (= 1244 di prima + 47 dei due file nuovi).
- Mike `Betfair/mike/tests`: **889 passed**.
- Safe: vedi sopra. tsc **0 errori**; vitest 5 file Omega/Mike **159 passed**.

## Params: nessuno da mettere per accenderli (sono gia' accesi di default)

Per SPEGNERLI (ramo di sempre): Omega `{"lambda_quote_prima": false, "model_red_cards":
false}`, Mike `{"veto_p_under35_cal": false}`. Soglie M1 ai default misurati:
`veto_p_under35_soglia_130/150/200/250/300` = 0,807 / 0,684 / 0,514 / 0,385 / 0,275.

## 0. Il passaggio a DEFAULT ACCESO (25/09 sera)

**Codice**
- `Betfair/omega/omega_config.py:101-107` `"lambda_quote_prima": (True, bool, None, None)`;
  `:288-295` `"model_red_cards": (True, bool, None, None)`.
- `Betfair/omega/omega_service.py:1059-1060`: con la chiave ASSENTE dai params
  `_prematch_lambdas` usa `omega_config.DEFAULTS["lambda_quote_prima"]` (prima: `False`
  cablato). Chi chiama senza params (proposte, test, strumenti) ha la catena nuova.
  `omega_engine.moltiplicatori_rossi_v3` passava gia' dalla whitelist (`parametri_v3`):
  chiave assente = default = acceso.
- `Betfair/mike/config.py:144-152` `"veto_p_under35_cal": (True, bool, None, None, None)`.
- `Betfair/mike/engine.py:2515-2523` `veto_u35_acceso`: chiave ASSENTE = default della
  whitelist (`config.PARAM_SPEC`, import locale: il motore resta senza dipendenze in
  testa); valore non booleano = spento (come prima).
- `frontend/src/lib/omega.ts:948, :1000` default `true`; hint dei due campi «ACCESO di
  default (misura 25/09: migliora); spento = ...». `frontend/src/lib/mike.ts:561` default
  `true`, hint `:458` idem.

**Test esistenti ADEGUATI (strategia decisa dall'utente, non un bug)**
1. `Betfair/omega/test_omega_certificazione_2026_09_11.py::test_m3_cache_lambda_ttl_solo_sulle_fonti_di_ripiego`:
   l'ultima asserzione («una FIXTURE in cache non scade mai») e' la catena di PRIMA; ora
   passa `params={"lambda_quote_prima": False}` esplicito (acceso la fixture scade col
   TTL, provato in `test_o1_quote_prima`). Nessun'altra riga cambiata.
2. `Betfair/stream/backtest/tools/misura_punto8/test_misura_punto8.py::test_o1_catena_attuale_e_quella_di_produzione`:
   NON ho cambiato il test ma lo STRUMENTO di misura `o1_catena_lambda.lambda_attuale`
   (`:169-173`): il suo braccio «attuale» chiamava la produzione senza params e ora
   avrebbe preso le quote (il confronto attuale/variante sarebbe diventato pre_ko contro
   pre_ko, e cosi' anche i bracci «attuali» di `o5_rossi` e `o6_coda`, che lo usano).
   Ora passa `params={"lambda_quote_prima": False}`: la misura resta riproducibile e
   identica a quella del mattino.
Nessun altro test esistente e' cambiato: su Mike nessun test esistente ha una
`p_under35_cal` nello snapshot, quindi il veto acceso non ha P e tace (condotta identica).

**Test nuovi adeguati**
- `test_o1_quote_prima`: whitelist -> `test_parametro_esiste_acceso_di_default...`
  (True, "off"/False spengono); ramo spento con `{"lambda_quote_prima": False}` per
  esteso (2 test); NUOVO `test_default_senza_params_e_whitelist_vuota_quote_in_testa`
  (senza params e con `resolve_params({})` -> `pre_ko_odds`). 12 test.
- `test_o5_rossi_v3`: costante `SPENTO = {"model_red_cards": False}` usata in tutti i test
  del ramo spento (neutro al 1e-12 «spento_con_rossi», `seleziona_v3` spento, spento coi
  rossi = senza, `_v3_select` spento, uscita spenta, `p_fonte` senza `+rossi`); whitelist ->
  `test_interruttore_in_whitelist_default_acceso` (anche `parametri_v3({})`); NUOVO
  `test_default_acceso_i_rossi_entrano_senza_toccare_niente` (params di default e `None`
  -> coefficienti JSON). 35 test.
- `test_mike_veto_p_under35`: whitelist -> `test_parametri_nella_whitelist_accesi_di_default`
  (+ `veto_u35_acceso({})` True, False/"si" spenti); HOLD/PERSIST/servizio spenti con
  `veto_p_under35_cal=False` per esteso; NUOVO `test_hold_coi_parametri_di_default_il_veto_scatta`.
  30 test.

**Falsificazione dei «default acceso»**
(`AUDIT_2026-09-25/mutazioni_default_acceso_2026-09-25.py`, ripristino byte per byte OK)
| Mutazione | Esito |
|---|---|
| D1 O1 default whitelist spento | ROSSO 2 failed |
| D2 O1 chiave assente = spento nel servizio | ROSSO 1 failed |
| D3 O5 default whitelist spento | ROSSO 2 failed |
| D4 M1 default whitelist spento | ROSSO 2 failed |
| D5 M1 chiave assente = spento nel motore | ROSSO 1 failed |
Rilanciate anche le 14 mutazioni O5 (F8 ora = «default spento»): **14/14 rosse**,
ripristino OK.

**Numeri prima/dopo il passaggio a default acceso**
| Suite | 43e1468 pulito | default SPENTI | default ACCESI |
|---|---|---|---|
| Omega 48 file + 4 del banco | 1244 passed, 3 skip | 1244 passed, 3 skip | al primo giro 15 failed (2 esistenti + 13 nuovi), dopo gli adeguamenti **1244 passed, 3 skip** |
| Mike `Betfair/mike/tests` | 859 | 888 | al primo giro 4 failed (tutti nuovi), dopo **889** (+1 test nuovo) |
| Extra `omega_engine` (Omega/Safe/stream) | - | 607 | **607** |
| Nuovi O1+O5+M1 | - | 74 | **77** (12 + 35 + 30) |
| tsc / vitest 5 file | 0 / 159 | 0 / 159 | **0 / 159** |

---

## 1. Punto di partenza: la patch O1/M1 sul master di oggi

`git apply --3way AUDIT_2026-09-25/preparazione_o1_m1_2026-09-25.patch` falliva su TUTTI i
file («patch does not apply», anche sulla base fcc99e7): il file della patch nel checkout
ha fine riga **CRLF** (1.072 righe su 1.072), mentre i blob sono LF. Convertita in LF in
una copia temporanea, `git apply --3way` e' passata **pulita su tutti i 9 file**, nessun
conflitto con 1ba167e: l'atlante v4 in `mike/dossier.py` (`live_frame`,
`consulta_atlante_v4`, `hazard_versione/fase/recupero_atteso_min`) e' intatto; M1 tocca solo
`build_prematch` (`p_under35_fonte`) e, in `mike/service.py`, `_CTX_FIELDS`,
`_p_under35_calibrata`, lo snapshot e la tupla delle attivita'. Il `--3way` aveva messo i
file in stage: tolti con `git reset -q` (solo indice, lavoro intatto). Diff identico a
quello del referto O1/M1 (9 file, +249 -11).

O1 e M1 restano **esattamente** come descritti in `PREPARAZIONE_O1_M1_2026-09-25.md`
(nessuna riga cambiata da me). In breve:

### O1 - Omega, quote pre-KO prima della fixture
- **Ora**: `_prematch_lambdas` = fixture DB -> `saved` -> quote 1X2 `pre_ko` -> hint -> griglia
  di mercato -> O/U live.
- **Acceso**: se il `pre_ko` e' completo, lambda = `lambdas_from_pre_ko` con fonte
  `pre_ko_odds` e la fixture NON si legge; fixture e `saved` solo se le quote mancano;
  la fixture in cache scade col TTL (spento: mai, come oggi).
- **Numeri**: log-loss CS FT -0,0231 [-0,0359; -0,0103] su 1.995 partite; fuori campione
  unito (734) FT -0,0238 [-0,0450; -0,0038], HT -0,0186 [-0,0338; -0,0050]; estensione
  17->23/09 -0,119 [-0,246; -0,027]. Cambia le lambda del ~47 % delle partite.
- **File:riga**: `Betfair/omega/omega_service.py:1048-1058` (interruttore, `:1058`
  `quote_prima = bool(params.get("lambda_quote_prima", False))`), `:1062-1064`, `:1078-1084`,
  `:1105`; `Betfair/omega/omega_config.py:101-106`; `frontend/src/lib/omega.ts:233, :1000,
  :1077`.

### M1 - Mike, veto con la P calibrata dell'Under 3.5
- **Ora**: all'ultimo ingresso in perdita -> HOLD (la posizione va in gioco); in profitto ->
  chiusura e PERSIST (rientro).
- **Acceso**: se `p_under35_cal` (SOLO da `markets_calibrated`) < soglia(quota del best
  back Under), in perdita si chiude con lay finale invece di tenere, e il PERSIST non
  parte; senza P o senza quota: condotta di oggi + attivita' `veto_under_calibrata` con
  `esito = non_valutabile`.
- **Numeri**: P calibrata contro grezza fuori campione dal 21/09, Brier -0,0093
  [-0,0155; -0,0034], log-loss -0,0322 [-0,0506; -0,0151] su 243 partite. **Il veto in
  se' NON e' misurato** (parte B aperta).
- **File:riga**: `Betfair/mike/config.py:144-157`, `Betfair/mike/engine.py:205, :337-341,
  :2515 (interruttore `veto_u35_acceso`), :2521 (`soglia_veto_under35`), :2647-2687,
  :2804-2807, :2831-2845`, `Betfair/mike/dossier.py:61-68, :82-88`,
  `Betfair/mike/feed.py:308, :343`, `Betfair/mike/service.py:275-293, :3418, :3670-3675`,
  `frontend/src/lib/mike.ts`.

---

## 2. O5 - Omega V3, cartellini rossi nel modello (NUOVO, costruito qui)

**Cosa fa ora.** `omega_v3.griglia_finale` ignora i rossi: il feed li porta
(`red_home`/`red_away` nella riga dello scanner, `LiveState.red_home/red_away` da
`omega_service._live_state_for:978-979`), il modello V3 no.

**Cosa fa acceso (`model_red_cards=True`).** L'intensita' RESIDUA di ciascun lato e'
moltiplicata per i coefficienti **GLOBALI** di `inplay_intensity_by_league.json`
(`global.red_card`: `carded_factor` 0,7461 per chi e' espulso, `opponent_factor` 1,3832 per
l'avversario, potenze per piu' rossi, banda [0,25; 2,0]), letti con la funzione di
produzione `live_engine.red_card_multipliers(rh, ra, None)` - **mai per lega**. Nel ramo
gamma-Poisson (quello di produzione, `v3_modello = gamma_poisson`) moltiplicare
l'intensita' per m equivale a moltiplicare l'esposizione residua per m, cioe' beta ->
beta/m: e' la matematica di `misura_punto8/o5_rossi.griglia_con_rossi`, riusata riga per
riga (test di equivalenza al 1e-12 con m diverso da 1). La correzione tau di Dixon-Coles
usa le intensita' gia' moltiplicate, come nella misura. Negli altri rami (poisson,
dixon_coles, bivariato, mistura) il moltiplicatore scala le stesse intensita' residue:
coerente, ma **non misurato** (non sono in produzione).

Ingresso e uscita vedono la STESSA P: un solo punto di calcolo,
`omega_engine.moltiplicatori_rossi_v3(params, red_home, red_away)`:
- ingresso: `omega_service._v3_select` passa `rossi=(state.red_home, state.red_away)` a
  `omega_engine.seleziona_v3`, che passa `mult_rossi` a `omega_v3.probabilita_selezioni`;
- uscita: `omega_proposte._una_gamba` calcola gli stessi moltiplicatori dalla riga del feed
  e li passa sia a `_p_del_bancato` (P del bancato) sia a `omega_v3.proposta_uscita`
  (traiettoria e `p_punteggio_invariato`, cioe' quanto vale aspettare).
- **Spento = identico al bit**: `moltiplicatori_rossi_v3` torna `(1.0, 1.0)`
  (`omega_v3.MULT_NEUTRO`) e ogni moltiplicazione per 1,0 e' esatta; con rossi 0-0 idem.
- Dati in piu' SOLO ad acceso e con rossi: `audit["mult_rossi"]` nella decisione V3 e il
  suffisso `+rossi` su `p_fonte` della proposta d'uscita. A spento audit e payload
  identici (test dedicati).

**Numeri della misura** (`MISURA_PUNTO8_2026-09-25.md` sez. 2): dal 30/06, fuori dal fit
dei coefficienti, al primo rosso, 77 partite: log-loss CS FT 1,9531 -> 1,8405, diff.
**-0,1126 [-0,1872; -0,0462]**, Brier -0,0213 [-0,0357; -0,0071]; ogni 10' fino all'85'
(272 punti, 77 partite) -0,1045 [-0,1833; -0,0313]; tutte (90 partite) -0,0884
[-0,1537; -0,0252]. Limiti della misura: campione piccolo (IC +/-0,07), misura al minuto
del rosso col punteggio vero e NON al cancello di Omega (nessun prezzo, nessuna cella),
solo periodo FT; effetto sulle decisioni non misurato. Rischio: medio (lambda residue
-25 % / +38 % sul rosso singolo).

**File:riga (O5)**
- `Betfair/omega/omega_v3.py:107-108` `MULT_NEUTRO`; `:268-312` `intensita_residue`
  (param `mult_rossi`, `:285`, moltiplicatore sui due rami `:307-308, :311-312`);
  `:315-329` `griglia_residua` (param `:327`, intensita' per tau `:329`), `:346-350` ramo
  gamma (`rh/ra * mh/ma`, cioe' beta/m); `:401-409` `griglia_finale`; `:489-501`
  `probabilita_selezioni`; `:848-865` `p_punteggio_invariato`; `:884-933`
  `traiettoria_bloccabile`; `:965-1016` `proposta_uscita`.
- `Betfair/omega/omega_engine.py:1143-1173` `moltiplicatori_rossi_v3` (nuova);
  `:1185` param `rossi` di `seleziona_v3`; `:1214-1220` passaggio al modello.
- `Betfair/omega/omega_service.py:1511-1517` (`_v3_select`: rossi dello stato live a
  `seleziona_v3`), `:1533-1537` (`audit["mult_rossi"]` solo se non neutro).
- `Betfair/omega/omega_proposte.py:381-389` (moltiplicatori dal feed, a `_p_del_bancato`),
  `:413` (a `proposta_uscita`), `_p_del_bancato` param `mult_rossi`, suffisso `+rossi`
  su `p_fonte`, `mult_rossi` a `probabilita_selezioni`.
- `Betfair/omega/omega_config.py:286-293` `"model_red_cards": (False, bool, None, None)`;
  `parametri_v3()["rossi"]` (con la coercizione della whitelist: "false" resta spento).
- `frontend/src/lib/omega.ts:314-315` tipo, `:948` default `false`, `:1166` campo nel
  pannello v3 (`test_omega_ui_contratto` pretende la parita' whitelist <-> UI: verde).

**Limiti dichiarati di O5**
- Se il punteggio arriva dallo `score_lookup` di ripiego (feed assente), `LiveState` non
  porta i rossi: 0-0, cioe' modello di oggi. L'uscita legge SEMPRE la riga del feed.
- Una gamba HALF_TIME_SCORE in uscita (`periodo='ht'`) riceve lo stesso moltiplicatore:
  la misura e' solo FT (in V3 le gambe sono sul Correct Score, quindi caso raro).
- Nessun cap sul minuto: un rosso al 5' vale come al 75' (e' cosi' anche nella misura).

---

## 3. Test

### Nuovi di O5: `Betfair/omega/tests/test_o5_rossi_v3_2026_09_25.py` - 34 test
Finti con le chiavi vere: riga del feed dello scanner (`minute`, `score_home`,
`score_away`, `red_home`, `red_away`, blocco `cs` con `selections` - riusati da
`test_omega_proposte_2026_09_17`: `DbFinto`, `MercatoFinto`, `_lay`, `_payload_feed`),
`omega_model.LiveState`, `omega_engine.ScoreRunner`; coefficienti letti dal JSON vero.
- whitelist: default spento, `parametri_v3()["rossi"]`, stringa "false" spenta;
- **neutro = prima al 1e-12** (12 casi: 4 stati x {default, acceso con 0-0, spento con
  rossi}) contro **valori d'oro** calcolati dal `omega_v3.py` di 43e1468 caricato a parte
  (`AUDIT_2026-09-25/oro_o5_griglia_v3_2026-09-25.py`): firma dell'intera griglia, cella,
  intensita';
- rosso in casa -> intensita' casa x `carded_factor`, trasferta x `opponent_factor` (dal
  JSON, al 1e-12); rosso in trasferta; doppio rosso; `red_card_multipliers` chiamata con
  `league_id=None`;
- griglia di produzione = `o5_rossi.griglia_con_rossi` della misura al 1e-12 (4 stati, con
  e senza tau); il rosso in casa sposta massa verso la trasferta;
- ingresso: `seleziona_v3` passa al modello il neutro a spento / senza rossi / rossi 0-0 e
  i coefficienti JSON ad acceso; spento coi rossi = identico a senza rossi; `_v3_select`
  (servizio vero, lambda e P empirica sostituiti) passa i rossi dello stato e scrive
  `audit.mult_rossi` solo ad acceso;
- uscita: `process_proposte_uscita` (produttore vero) -> `proposta_uscita` riceve i
  moltiplicatori JSON ad acceso e la **P del bancato = P dell'ingresso al 1e-12** (e
  diversa dal neutro); spento coi rossi = identico a senza rossi (P, moltiplicatori e
  proposta); `p_fonte` con `+rossi` solo ad acceso; la traiettoria cambia coi rossi;
  `proposta_uscita` passa i rossi alla traiettoria (`bloccabile_max_atteso` cambia).

### Falsificazione O5 (`AUDIT_2026-09-25/mutazioni_o5_rossi_2026-09-25.py`: mutazione sul
file, test, ripristino dei byte originali in `finally`, hash sha256 prima/dopo)
| Mutazione | Esito |
|---|---|
| F1 moltiplicatore ignorato ovunque (V3) | ROSSO 9 failed |
| F1b moltiplicatore ignorato solo nella griglia NegBin | ROSSO 4 failed |
| F1c tau con le intensita' senza rossi | ROSSO 2 failed |
| F2 interruttore ignorato (sempre acceso) | ROSSO 9 failed |
| F2b interruttore ignorato (mai acceso) | ROSSO 14 failed |
| F3a uscita: la P del bancato non vede i rossi | ROSSO 1 failed |
| F3b uscita: la traiettoria non riceve i rossi | ROSSO 1 failed |
| F3c `proposta_uscita` non passa i rossi alla traiettoria | ROSSO 1 failed (al primo giro era VERDE: aggiunto `test_proposta_uscita_passa_i_rossi_alla_traiettoria`) |
| F4 ingresso: `seleziona_v3` non passa i rossi al modello | ROSSO 2 failed |
| F5 `_v3_select` non passa i rossi del feed | ROSSO 2 failed |
| F6 coefficienti PER LEGA (39) invece che globali | ROSSO 6 failed |
| F7 casa/trasferta invertiti | ROSSO 6 failed |
| F8 default della whitelist acceso | ROSSO 10 failed |
| F9 `p_fonte` senza `+rossi` | ROSSO 1 failed |
14/14 rosse; «ripristino byte per byte: OK»; `git diff --stat` identico prima e dopo
(12 file, +376 -40).

### O1/M1: i 40 test del referto rieseguiti sul master di oggi
`test_o1_quote_prima_2026_09_25.py` 11 passed; `test_mike_veto_p_under35_2026_09_25.py`
29 passed. Le 17 mutazioni O1/M1 del referto di stamattina NON le ho rilanciate (codice
invariato riga per riga, vedi sez. 1).

### Esistenti - parita' a interruttori spenti (stessi comandi, stessi file)
- **Omega**: 48 file (`Betfair/omega/test_*.py` e `Betfair/omega/tests/test_*.py` che
  importano `omega_service`/`omega_v3`/`omega_proposte`/`omega_config`) + 4 del banco
  (`misura_punto8/test_misura_punto8.py`, `stream/tests/test_submin_contratto_chiamanti`,
  `test_sveglia_bot_f5_f6`, `test_saldo_evento`):
  **prima (43e1468 pulito) 1244 passed, 3 skipped; dopo O1/M1 1244 passed, 3 skipped;
  dopo O5 1244 passed, 3 skipped.** Il rosso d'ordine `test_l03_stats_azzerate_a_bot_fermo`
  del referto O1/M1 in quest'ordine di file non si presenta.
- **Mike** (`Betfair/mike/tests`, tutta la cartella; non esistono `test_mike_*.py` fuori):
  **prima 859 passed; dopo 888 passed = 859 + i 29 nuovi di M1.**
- **Extra** che importano `omega_engine` (7 Omega, 7 Safe, `Betfair/tests/test_consapevolezza_ordine`,
  `stream/tests/test_genera_atlante`): **607 passed** (solo DOPO: il prima non l'ho
  misurato).
- **Frontend**: `npx tsc -p tsconfig.app.json --noEmit` **0 errori** (exit 0, output
  vuoto); `npx vitest run src/lib/omega.test.ts src/lib/mike.test.ts
  src/lib/omegaAudit1209.test.ts src/lib/omegaProposte.test.ts src/lib/omegaUscita.test.ts`
  **159 passed** (5 file).

---

## 4. REPLAY «IPER RAPIDO» per il coordinatore (uno alla volta, mai in parallelo)

**Cosa il banco PUO' e NON PUO' dire** (letto nel codice, non provato):
- O1: il DB finto di Omega non ha `fixture_id` (`omega/tools/replay_registrazioni.py`:
  `get_event`, fixture «assente dalla registrazione»): la catena usa GIA' il `pre_ko` ->
  ad acceso le lambda devono restare IDENTICHE. Il banco prova parita' e assenza di
  regressioni, non l'effetto (quello e' la misura).
- M1: il DB finto di Mike non ha il dossier: `p_under35_cal` sempre assente -> ad acceso
  solo attivita' `veto_under_calibrata` con `esito = non_valutabile`, condotta identica.
- O5: le registrazioni di Omega del banco non hanno rossi (non verificato su 35760084
  riga per riga); l'UNICA registrazione con rosso e' **35794996** (rosso al 75', finale
  0-2, 1,6 MB, ha il CORRECT_SCORE: letto nel raw), non e' nell'elenco Omega ma si puo'
  passare come evento. Al 75' la gamba B (finestra 46'-85') e le uscite possono cambiare.

**Durata stimata (NON misurata oggi)**: il 16/09 `certifica mike 35760084 --scenari base`
girava in **59 s** wall (`CHECKPOINT_PERF_2026-09-16.md` sez. 3); il 25/09 il profilo
`rapidi` di Omega su 35760084 con parita' coda/canale ha preso 140 s; il coordinatore ha
stimato «9 replay Omega ~ 1 h» (~6-7 min l'uno sulle registrazioni grandi da 18-22 MB).
Su **35760084 (7 MB)** stimo **1-3 min per scenario Omega** e **~1 min per scenario
Mike**; 35794996 (1,6 MB) meno di 1 min. Totale del set qui sotto a interruttori spenti:
~10-15 min per baseline + variante. **Se uno scenario Omega su 35760084 supera 5 min,
e' fuori stima: dirlo all'utente prima di lanciare gli altri.**

Dal **worktree** serve `--data-dir` (lezione del 18/09: senza, NO_RAW e BANCO-ESPLOSO):
`--data-dir "C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\_live_raw"`.

**AGGIORNAMENTO default ACCESI (25/09 sera).** Ora il worktree gira GIA' coi tre
interruttori accesi senza toccare niente: il confronto master (= catena di prima) contro
worktree (= default nuovi) e' direttamente «prima/dopo». Set minimo consigliato, stessi
comandi sui due lati:
```
python -m Betfair.stream.backtest.certifica omega 35760084 35794996 --scenari v4,v4-riavvio,proposta-approvata --worker 1 --json --diario omega_default.txt
python -m Betfair.stream.backtest.certifica mike 35760084 --scenari base,riavvio --worker 1 --json --diario mike_default.txt
```
Atteso: su 35760084 Omega IDENTICO al master (il banco non ha fixture: O1 non cambia le
lambda; niente rossi attesi: O5 neutro); su 35794996 le differenze possibili sono SOLO dopo
il rosso del 75' (`audit.mult_rossi`, `p_fonte` `+rossi`), zero violazioni; Mike IDENTICO
salvo attivita' `veto_under_calibrata` `non_valutabile` a ogni HOLD/PERSIST, `veto_u35:
null` nel ctx e `p_under35_fonte` nel dossier. Stima: ~8-12 min in tutto. Il vecchio
giro «spento contro master» (A qui sotto) servirebbe solo a provare che lo SPENTO e'
identico al master: e' gia' provato nei test al 1e-12; per farlo sul banco servirebbe uno
scenario con i tre `False` (non esiste; `certifica` non prende params).

**A (superato dal default acceso). Parita' a interruttori SPENTI** (master = baseline,
worktree = variante; stessi comandi, confronto riga per riga dei `--json`):
```
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari v4,v4-riavvio,proposta-approvata --worker 1 --json --diario omega_spento.txt
python -m Betfair.stream.backtest.certifica mike 35760084 --scenari base,riavvio --worker 1 --json --diario mike_spento.txt
```
Perche' questi: `v4` = il motore V3 di default sul percorso di produzione (ingresso O1/O5);
`v4-riavvio` = cache di processo svuotate a meta' partita (la cache lambda di O1, lo stato
dal DB); `proposta-approvata` = il produttore delle uscite (`omega_proposte`, dove passano
i rossi) firmato come dalla Control Room; Mike `base` = HOLD/PERSIST all'ultimo ingresso
(i due punti di M1), `riavvio` = `ctx` riletto dal DB (`veto_u35` nuovo in `_CTX_FIELDS`).
Atteso: violazioni 0, stessi stati/fasi/ordini/P&L/`scartati`, stessa `fonte_lambda`.
Unica differenza ammessa su Mike: `veto_u35: null` nel ctx e `p_under35_fonte` nel
dossier (dati, nessuna condotta).

**B. Interruttori ACCESI** - il banco oggi NON ha uno scenario che li accenda
(`certifica` non prende params da riga di comando). Da aggiungere (fuori dal mio
perimetro, non fatto), una voce per bot + la sua riga in `SCENARI_DESCRITTI`:
```python
# Betfair/omega/tools/replay_registrazioni.py, SCENARI
"v4-o1-o5": dict(_APRE, strategy_version=3, lambda_quote_prima=True, model_red_cards=True),
# Betfair/mike/tools/replay_registrazioni.py, SCENARI
"veto-u35": {"veto_p_under35_cal": True},
```
poi:
```
python -m Betfair.stream.backtest.certifica omega 35760084 35794996 --scenari v4,v4-o1-o5 --worker 1 --json --diario omega_acceso.txt
python -m Betfair.stream.backtest.certifica mike 35760084 --scenari veto-u35 --worker 1 --json --diario mike_acceso.txt
```
Atteso: Omega 35760084 `v4-o1-o5` = `v4` (stessa `fonte_lambda` `pre_ko_odds`; se non ci
sono rossi, stesse celle); 35794996 = unica partita in cui O5 puo' cambiare P/celle/uscite
dopo il 75' (`audit.mult_rossi` = [0,7461; 1,3832] o invertito secondo chi e' espulso,
`p_fonte` con `+rossi`): ogni differenza va letta, zero violazioni. Mike `veto-u35` = `base`
+ attivita' `veto_under_calibrata` `non_valutabile`; una differenza di condotta sarebbe un
difetto.

---

## NON VERIFICATO
- Nessun replay lanciato (per mandato): parita' sul banco, durate e condotta ad acceso
  sono del coordinatore (sez. 4). Le durate sono stime da referti vecchi.
- Che 35760084 non abbia rossi: non controllato nel raw.
- 35794996 non e' mai passata dal banco di Omega: possibile che sia incompleta per Omega
  (1,6 MB, 10 righe CORRECT_SCORE nel raw); `--complete` la escluderebbe se giudicata
  incompleta.
- L'effetto di O5 sulle DECISIONI (quante gambe cambiano) non e' misurato da nessuno; la
  misura e' sulla log-loss del risultato esatto al minuto del rosso, solo FT.
- I rami V3 non di produzione (poisson, dixon_coles, bivariato, mistura) col moltiplicatore:
  coerenti ma non misurati.
- Il veto M1 in se' (quante HOLD/PERSIST toglie e con che P&L): parte B aperta; il banco non
  ha il dossier.
- Il «prima» dei 607 test extra non e' stato misurato (solo il dopo, tutti verdi).
- Le 17 mutazioni O1/M1 del referto del mattino non rilanciate (codice identico).
- `npm run build` non eseguito (niente integrazione dal worktree).

## File toccati (elenco esatto, rispetto a 43e1468)
Modificati (12): `Betfair/mike/config.py`, `Betfair/mike/dossier.py`,
`Betfair/mike/engine.py`, `Betfair/mike/feed.py`, `Betfair/mike/service.py` (O1/M1 dalla
patch, invariati); `Betfair/omega/omega_config.py` (O1 + O5), `Betfair/omega/omega_service.py`
(O1 + O5), `Betfair/omega/omega_engine.py` (O5), `Betfair/omega/omega_proposte.py` (O5),
`Betfair/omega/omega_v3.py` (O5), `frontend/src/lib/mike.ts` (M1),
`frontend/src/lib/omega.ts` (O1 + O5).
Modificati per il DEFAULT ACCESO (25/09 sera, +2):
`Betfair/omega/test_omega_certificazione_2026_09_11.py` (una asserzione: spento esplicito),
`Betfair/stream/backtest/tools/misura_punto8/o1_catena_lambda.py` (braccio «attuale» con
lo spento esplicito). Totale modificati: 14.
Nuovi (test): `Betfair/omega/tests/test_o1_quote_prima_2026_09_25.py`,
`Betfair/mike/tests/test_mike_veto_p_under35_2026_09_25.py`,
`Betfair/omega/tests/test_o5_rossi_v3_2026_09_25.py`.
Nuovi (referto e strumenti): questo referto,
`AUDIT_2026-09-25/o1_m1_o5_integrabili_2026-09-25.patch`,
`AUDIT_2026-09-25/genera_patch_o1_m1_o5.py`,
`AUDIT_2026-09-25/mutazioni_o5_rossi_2026-09-25.py`,
`AUDIT_2026-09-25/mutazioni_default_acceso_2026-09-25.py`,
`AUDIT_2026-09-25/oro_o5_griglia_v3_2026-09-25.py`.
Junction nel worktree: `.venv`, `frontend/node_modules` (togliere con `cmd /c rmdir`,
MAI `git worktree remove --force`).

## Comandi eseguiti ed esito
- `git fetch`; HEAD = `origin/master` = 43e1468.
- pytest Omega (48+4 file) su 43e1468 pulito: 1244 passed, 3 skipped. pytest Mike
  `Betfair/mike/tests`: 859 passed.
- `git apply --3way` della patch O1/M1: fallito (CRLF); script di fusione a 3 vie con base
  fcc99e7: fallito (stesso motivo); patch convertita in LF + `git apply --3way`: pulita
  su 9 file; `git reset -q` per togliere lo stage.
- pytest dopo O1/M1: Omega 1244 passed 3 skipped; Mike 888 passed; `test_o1_quote_prima` 11.
- O5 costruito; valori d'oro dal `omega_v3.py` di HEAD (`oro_o5_griglia_v3_2026-09-25.py`).
- pytest dopo O5: Omega 1244 passed 3 skipped; extra 607 passed; nuovi O1+O5+M1 74 passed
  (11 + 34 + 29); ultimo giro nuovi + contratto UI + config Omega 97 passed.
- 14 mutazioni O5: 14 rosse, ripristino byte per byte OK.
- `npx tsc -p tsconfig.app.json --noEmit`: exit 0, 0 righe; `npx vitest run` 5 file: 159 passed.
- `git apply --check --reverse` della patch unica nel worktree: OK.
- 25/09 sera, DEFAULT ACCESI: flip in config/servizio/motore/UI; primo giro Omega 15
  failed + 1274 passed (2 esistenti, 13 nuovi), Mike 4 failed (nuovi); adeguati i test
  (sez. 0); poi Omega 48+4 file **1244 passed, 3 skipped**, Mike **889 passed**, extra
  **607 passed**, nuovi **77 passed** (12 + 35 + 30); 5 mutazioni «default acceso» rosse,
  14 mutazioni O5 rosse, ripristino OK; tsc 0 errori, vitest 5 file 159 passed; patch
  rigenerata (17 file, +1373 -43), `git apply --check --reverse` OK.
