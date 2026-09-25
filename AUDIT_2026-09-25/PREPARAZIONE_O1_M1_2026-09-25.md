# PREPARAZIONE O1 (Omega) e M1 (Mike) - 25/09/2026 (delegato Opus, sessione B)

Mandato: preparare le due modifiche misurate come «migliorano» fuori campione dietro un
interruttore di configurazione **DEFAULT SPENTO**. Nessuna integrazione: il diff resta nel
worktree `agent-a214964ce303fe57c` (base `origin/master` `fcc99e7`), niente commit, niente
replay lanciati da me, niente DB vero (ogni pytest con `SUPABASE_URL=http://127.0.0.1:9`).
Le strategie non cambiano finche' l'utente non accende gli interruttori.

Fonte dei numeri: `AUDIT_2026-09-25/MISURA_PUNTO8_2026-09-25.md` (worktree
`agent-ac23776a52e6a74e8`), sezioni 1 e 4 e «Cosa serve per la produzione».

---

## 1. O1 - Omega, quote pre-KO PRIMA della fixture nella catena delle lambda

**Cosa fa ora.** `omega_service._prematch_lambdas` (`Betfair/omega/omega_service.py:1030`)
prova: 1) fixture del DB (`stream.db.get_fixture_prematch_lambdas`: `tactical_engine_json`,
poi `db_json_analisi.inputs`); 2) lambda salvati su `omega_events.model`; 3) quote 1X2
`pre_ko` devigate; 4) hint da un trade precedente; 5) griglia di mercato; 6) O/U live;
7) salvato scaduto.

**Cosa fa con `lambda_quote_prima=True`.** Il gradino 3 passa davanti: se il `pre_ko` c'e' ed
e' completo, `out = (lambdas_from_pre_ko, league_id dell'evento, "pre_ko_odds")`, persistito
come oggi nel ramo pre-KO. La fixture (e dopo di lei il `saved`) si legge SOLO se le quote
mancano o sono incomplete. Il `saved` resta DOPO il pre-KO, come nella misura. Il resto
della catena e' identico. `lambda_source` dice la fonte vera (`pre_ko_odds` / `fixture` /
...), e le fonti restano dentro `certificazione.FONTI_LAMBDA` (controllo A5 invariato).

Due scelte da dichiarare:
- con le quote in testa la `league_id` e' quella della riga `omega_events` (esattamente
  come oggi nel ramo pre-KO), non quella della riga `fixture_predictions`, che non si
  legge piu';
- **cache**: oggi un lambda `fixture` in `_LAMBDA_CACHE` non scade mai. Ad interruttore
  acceso scade col TTL come le altre fonti, altrimenti una prima valutazione fatta prima
  che lo scanner congelasse il `pre_ko` avrebbe inchiodato la fixture per sempre.
  Spento: identico a oggi (test dedicato).

**Perche'.** Misura sez. 1: log-loss CS FT **-0,0231 [-0,0359; -0,0103]** su 1.995 partite;
fuori campione unito (734) FT -0,0238 [-0,0450; -0,0038], HT -0,0186 [-0,0338; -0,0050];
estensione 17->23/09 (fuori campione anche per il V3) -0,119 [-0,246; -0,027]. Cambiano le
lambda del ~47 % delle partite (quelle con fixture). Letture DB in meno (la fixture non si
legge quando ci sono le quote).

**Diff.**
- `Betfair/omega/omega_service.py:1048-1058` docstring + lettura dell'interruttore;
  `:1062-1064` scadenza della fixture in cache solo ad acceso; `:1070` `persist` inizializzato
  prima; `:1078-1083` blocco pre-KO in testa (solo acceso); `:1084` fixture/saved solo se
  `out is None`; `:1105` il pre-KO al suo posto di sempre solo a spento.
- `Betfair/omega/omega_config.py:101-106` parametro `lambda_quote_prima` `(False, bool)`.
- `frontend/src/lib/omega.ts:233, :997, :1074` tipo, default `false`, campo nel pannello
  «Modello» (il contratto UI `test_omega_ui_contratto` pretende la parita' whitelist <-> UI).

**Parametro nuovo:** `lambda_quote_prima` = **False**.

---

## 2. M1 - Mike, veto sulla P calibrata dell'Under 3.5

**Cosa fa ora.** `dossier.build_prematch` calcola `p_under35_cal` e nessuno la legge.
All'ultimo ingresso (`PRE_OPEN`, KO - `pre_last_entry_min`): in perdita -> `HOLD` («tengo»,
la posizione entra in gioco); in profitto -> chiusura finale e poi ultimo ingresso `PERSIST`
(`_after_final_green`), che porta in gioco una posizione nuova.

**Cosa fa con `veto_p_under35_cal=True`.** Solo nei due punti del passaggio pre-match -> live:
- **in perdita** (`engine.py:2663-2687`): se `p_under35_cal < soglia(quota del best back
  Under adesso)` la posizione NON si tiene: lay finale al best lay (stessa aritmetica
  `compute_greenup` della chiusura in profitto), `ctx.veto_u35` registra il veto. Poi, a
  chiusura abbinata, niente PERSIST (`engine.py:2804-2807`). Se il prezzo lay manca
  (`:2647-2654`) non si puo' chiudere comunque: HOLD come oggi, con l'attivita' che lo dice;
- **PERSIST** (`engine.py:2831-2845`): se `p_under35_cal < soglia(quota del back PERSIST)`
  -> `IDLE_LIVE` senza ordine (non si rientra), altrimenti il PERSIST di sempre.
- **senza P calibrata o senza quota**: nessun veto (condotta di oggi) e attivita'
  `veto_under_calibrata` con `esito = non_valutabile` e il motivo.
- Stake, banda 1,30-3,00, copertura, cash out, uscite in perdita: **invariati**.

**Soglie** (`engine.py:2486-2566`, parametri in `config.py:144-157`): nodi della curva
isotonica della misura, 1,30 -> 0,807; 1,50 -> 0,684; 2,00 -> 0,514; 2,50 -> 0,385;
3,00 -> 0,275 (incerta: 31 partite nel decile), **interpolazione lineare** fra i nodi,
nodo di estremita' fuori dalla banda (una quota salita oltre 3,00 usa 0,275).

**La P usata e' SOLO la calibrata.** `dossier.py` ripiega su `markets` grezzi quando
`markets_calibrated` manca e scrive comunque `p_under35_cal`: le soglie sono state stimate
sulla calibrata, quindi il dossier ora dichiara `p_under35_fonte` = `calibrated` | `raw`
(`dossier.py:61-68, :82-88`) e il servizio passa allo snapshot la P solo se `calibrated`
(`service.py:282-294`, chiamata a `:3414`). Un dossier scritto prima del 25/09 (senza
fonte) = nessuna P = nessun veto.

**Build_prematch non va anticipato.** Il dossier si costruisce gia' all'ARMAMENTO
(`service.py`, blocco «nuove candidate», `D.build_prematch` prima di qualunque decisione),
e il motore lo vede dal primo giro: nessuna lettura DB in piu'.

**Attivita'** `veto_under_calibrata` (`service.py:3667-3671`, `mike.ts` kind + etichetta +
riga italiana): `{punto: hold|persist, esito, eseguito, p_under35_cal, soglia, quota,
motivo}`. Una volta sola per punto: con la green ancora viva la lay arriva al giro dopo
(`_una_sola_lay`) e l'attivita' si scrive quando la lay parte; con le uscite manuali la
proposta si ripete ma l'attivita' no (`engine.py:2671-2678`).

**Interazioni dichiarate.**
- con `uscite_automatiche` spento la chiusura per veto e' un'uscita discrezionale
  (`under_green`) e diventa una PROPOSTA come le altre (gate invariato);
- se la lay di chiusura non si abbina o si abbina in parte, il ramo `PRE_GREEN_PENDING` di
  sempre la riprezza (`close_retry_s`, `close_max_attempts`) e alla fine va in `HOLD` col
  residuo: e' la condotta esistente, non toccata;
- il caso «KO arrivato PRIMA dell'ultimo ingresso» (fischio anticipato: la posizione va in
  gioco dal ramo `snap.inplay`) NON e' coperto dal veto: il mandato era HOLD/PERSIST.

**Perche'.** Misura sez. 4: P calibrata contro grezza fuori campione dal 21/09, Brier
**-0,0093 [-0,0155; -0,0034]**, log-loss -0,0322 [-0,0506; -0,0151] su 243 partite; nel
decile 0,1-0,3 dell'Over la P dell'Under e' ~3 punti troppo alta (Mike e' ottimista proprio
dove e' tranquillo): per questo a quota 1,30 serve 0,807 e non il pareggio 0,778.
**Il veto in se' non e' misurato** (parte B della misura, conteggio sul replay, ancora
aperta): e' la domanda che il replay qui sotto deve cominciare a rispondere.

**Parametri nuovi:** `veto_p_under35_cal` = **False**; `veto_p_under35_soglia_130/150/200/
250/300` = 0,807 / 0,684 / 0,514 / 0,385 / 0,275 (float 0-1).
**Stato nuovo persistito:** `ctx.veto_u35` (`engine.py:337-341`, `service._CTX_FIELDS` `:276-279`).

---

## 3. Parita' a interruttore spento: cosa cambia comunque (solo dati, nessuna condotta)

- Mike: la riga `mike_events.ctx` porta una chiave in piu' `veto_u35: null`; il `dossier`
  (e il payload dell'attivita' `armed`) porta `p_under35_fonte`. Nessun ramo li legge a
  interruttore spento.
- Omega: nessun dato nuovo.
- UI: tre campi nuovi nei pannelli parametri (Omega 1, Mike 6), default spenti.

---

## 4. Test

### Nuovi
- `Betfair/omega/tests/test_o1_quote_prima_2026_09_25.py` - **11 test**. Finti con chiavi
  vere: riga `omega_events` (`event_id, fixture_id, league_id, model`); la fixture passa
  dalla funzione VERA `stream.db.get_fixture_prematch_lambdas` con un client PostgREST finto
  (`table/select/eq/limit/execute`, riga `fixture_predictions` con `tactical_engine_json` e
  `db_json_analisi.inputs`); il `pre_ko` lo costruisce il produttore VERO
  `safe_strategy.scanner.freeze_pre_ko` dai prezzi BACK. Coprono: spento -> fixture (stesso
  numero con e senza params); acceso -> `pre_ko_odds` = `lambdas_from_pre_ko`, persistito,
  zero letture della fixture; senza quote -> fixture in entrambi i casi (tattico e
  `db_json_analisi.inputs`); 1X2 incompleto -> fixture; `saved` resta dopo il pre-KO;
  scadenza della fixture in cache solo ad acceso; whitelist.
- `Betfair/mike/tests/test_mike_veto_p_under35_2026_09_25.py` - **29 test**. Riga
  `db_json_analisi` con `inputs`, `markets`, `markets_calibrated.over_3_5 = {"True": x,
  "False": 1-x}`. Coprono: whitelist e default; soglia sui nodi, interpolata (1,40 / 1,75 /
  2,25 / 2,80), fuori banda, letta dai parametri, nodi del motore = default della whitelist;
  HOLD spento (P 0,10: tiene come oggi, nessuna traccia); HOLD acceso a 1,50 con P 0,60
  (veto: annullo, poi lay finale a 1,52, poi nessun PERSIST) e P 0,70 (tiene, `nessun_veto`);
  HOLD acceso senza P (tiene, `non_valutabile`); PERSIST spento (rientra, P 0,10); PERSIST
  acceso a 2,50 con P 0,35 (veto) e 0,40 (rientra); PERSIST a 1,44 con soglia interpolata
  0,7209 (P 0,71 veto, 0,73 rientra); PERSIST senza P; dossier `calibrated`/`raw`/vecchio;
  snapshot; **tre giri del servizio vero** (`service.run_once` con i finti di
  `test_mike_service`): spento -> HOLD e nessuna attivita'; acceso P 0,55 a quota 1,54
  (soglia 0,6704) -> annullo, lay 1,55 abbinata, `IDLE_LIVE` senza `under_last`, attivita'
  una volta sola, `ctx.veto_u35` persistito; acceso P 0,75 -> HOLD con `nessun_veto`.

### Esistenti (parametri spenti = condotta identica)
Prima e dopo il diff, stessi comandi, stessi numeri:
- **Omega** (10 file: `test_omega_certificazione_2026_09_11`, `test_omega_giornata_gambe_2026_09_11`,
  `test_omega_audit_2026_09_11`, `test_omega_modello_definitivo_2026_09_11`,
  `tests/test_politica_v4_2026_09_17`, `test_omega_greenup_2026_09_10`, `test_omega_v2_2026_09_09`,
  `test_omega_config`, `test_omega_ui_contratto_2026_09_11`, `tests/test_raccordo_v3_2026_09_17`):
  **prima 242 passed + 1 failed; dopo 242 passed + 1 failed**. Il rosso e' PREESISTENTE e
  dipende dall'ordine: `test_omega_audit_2026_09_11.py::test_l03_stats_azzerate_a_bot_fermo`
  (`assert 1 == 0`) fallisce solo se gira dopo `test_omega_certificazione`/`giornata_gambe`;
  da solo il file e' 70/70 verde. Non tocca la catena lambda. Da segnalare a parte.
- **Mike** (18 file: audit 11/09 e 12/09, canale locale, certificazione UI, engine, engine cert,
  feed, flusso fischio, freno copertura, ko green appoggiata, mercato sospeso, prezzo morto,
  review, service, tetto partite, dossier, config, uscite automatiche): **prima 548 passed;
  dopo 548 passed**.
- Extra dopo il diff: `test_mike_conto_e_sovracopertura`, `test_mike_respiro_scritture`,
  `test_mike_respiro_db`, `test_omega_respiro_db`: 129 passed.
- Frontend: `npx tsc -p tsconfig.app.json --noEmit` **0 errori**; `npx vitest run
  src/lib/omega.test.ts src/lib/mike.test.ts src/lib/omegaAudit1209.test.ts` 117 passed.

### Falsificazione (mutazione in memoria, ripristino byte per byte in `finally`, `git diff --stat` identico dopo)
| Mutazione | Esito |
|---|---|
| O1-a interruttore ignorato (mai acceso) | ROSSO 3 failed |
| O1-b interruttore sempre acceso | ROSSO 3 failed |
| O1-c catena non invertita (la fixture sovrascrive il pre-KO anche ad acceso) | ROSSO 3 failed |
| O1-d la fixture in cache non scade mai anche ad acceso | ROSSO 1 failed |
| O1-e default della whitelist acceso | ROSSO 1 failed |
| M1-a veto applicato a interruttore spento | ROSSO 3 failed |
| M1-b soglia senza interpolazione | ROSSO 15 failed |
| M1-c confronto invertito | ROSSO 8 failed |
| M1-d soglia sbagliata a 2,50 nel motore (0,485) | ROSSO 1 failed (primo giro VERDE: i parametri arrivano sempre dalla whitelist, quindi aggiunto il test «nodi del motore = default della whitelist») |
| M1-d2 soglia sbagliata a 2,50 nella whitelist | ROSSO 7 failed |
| M1-d3 default whitelist acceso | ROSSO 4 failed |
| M1-e dopo il veto si rientra col PERSIST | ROSSO 2 failed |
| M1-f il veto legge anche la P grezza | ROSSO 1 failed |
| M1-g il servizio non passa la P allo snapshot | ROSSO 2 failed |
| M1-h in perdita il veto non chiude | ROSSO 2 failed |
| M1-i dossier: fonte sempre `calibrated` | ROSSO 1 failed |
| M1-j al PERSIST il veto non si applica | ROSSO 2 failed |

---

## 5. LISTA DEI REPLAY per il coordinatore (uno per bot, in sequenza, mai in parallelo)

**Limite del banco da sapere prima (letto nel codice, non misurato):**
- Omega: il DB finto del replay (`Betfair/omega/tools/replay_registrazioni.py:443`,
  `get_event`) non ha `fixture_id` e dichiara `fixture_predictions` «assente dalla
  registrazione» (`:640-644`). Quindi **nel replay la catena usa gia' oggi il `pre_ko`**:
  a interruttore acceso le lambda devono risultare IDENTICHE. Il banco puo' provare la
  parita' e l'assenza di regressioni, non l'effetto di O1 (quello e' la misura).
- Mike: il DB finto del banco non ha `fixture_id_for_event`/`fixture_analysis`:
  `build_prematch` restituisce un dossier vuoto, quindi **nel replay `p_under35_cal` e'
  sempre assente** e il veto acceso da' solo attivita' `non_valutabile`, nessun cambio di
  condotta. Il conteggio vero (parte B della misura) richiede di dare al banco il dossier
  della partita registrata: e' un'estensione del banco, da chiedere all'utente.
- Non esiste uno scenario che accenda gli interruttori: per il giro «acceso» serve
  aggiungere UNA voce agli scenari (non l'ho fatto: fuori perimetro), per esempio
  `"o1-quote-prima": dict(_APRE, lambda_quote_prima=True)` in `SCENARI` di Omega e
  `"veto-u35": {"veto_p_under35_cal": True}` in `SCENARI` di Mike, con la loro riga in
  `SCENARI_DESCRITTI`.

**A. Parita' a interruttore spento (obbligatoria prima di integrare).** Stessi comandi sul
master di oggi e sul worktree, referti confrontati numero per numero:
```
python -m Betfair.stream.backtest.certifica omega 35760084 35797769 35777617 --scenari cap-stretto,feed-stantio,riavvio,proposta-approvata,uscite-automatiche,rifiuti-betfair --json --diario omega_o1_spento.txt
python -m Betfair.stream.backtest.certifica mike --scenari base,gol-precoce,senza-seconda-puntata,taker,cap-stretto,bot-fermo,riavvio --json --diario mike_m1_spento.txt
```
Da confrontare: violazioni (0 attese), copertura dei controlli, stati e fasi, `scartati` per
motivo, P&L per scenario, `fonte_lambda` delle gambe Omega. **Atteso: identici.** Unica
differenza ammessa su Mike: `veto_u35: null` nel ctx e `p_under35_fonte` nel dossier.

**B. Interruttore acceso (dopo aver aggiunto gli scenari del punto sopra).**
```
python -m Betfair.stream.backtest.certifica omega 35760084 35797769 35777617 --scenari o1-quote-prima --json
python -m Betfair.stream.backtest.certifica mike --scenari veto-u35 --json
```
Atteso col banco di oggi: Omega identico allo scenario base con la stessa configurazione
(stessa `fonte_lambda` = `pre_ko_odds`, stesse celle); Mike identico a `base` piu'
attivita' `veto_under_calibrata` con `esito = non_valutabile` a ogni HOLD e a ogni PERSIST,
zero violazioni. Una differenza di condotta qui sarebbe un difetto.

**C. Effetto reale (solo se l'utente autorizza l'estensione del banco con i dati di
`fixture_predictions` delle partite registrate):** Omega - `lambda_source` passa da
`fixture` a `pre_ko_odds` sulle partite con fixture, celle e ingressi del cancello possono
cambiare; Mike - quante HOLD e quanti PERSIST in meno, P&L netto negli scenari con gol
precoce (`gol-precoce` su 35777617, 36006953, 35760084).

---

## NON VERIFICATO
- Nessun replay lanciato (per mandato): parita' sul banco e condotta ad acceso sono da
  verificare dal coordinatore (sez. 5).
- L'effetto del VETO M1 (quante posizioni toglie e con che P&L) non e' misurato da nessuno:
  la misura prova solo che la P calibrata e' migliore della grezza. Parte B aperta.
- Il banco non puo' mostrare l'effetto di O1 e di M1 (niente fixture ne' dossier nelle
  registrazioni): letto nel codice del banco, non provato con un replay.
- La soglia a 3,00 (0,275) e' incerta per la misura stessa (31 partite nel decile).
- Nessun test sul percorso live REST della lay di chiusura per veto: usa lo stesso ruolo
  (`under_green`, `final=True`) e lo stesso percorso della chiusura in profitto di sempre,
  verificato solo in paper (servizio con finti).
- `npm run build` non eseguito (nessuna app da aggiornare: niente integrazione).
- Il rosso preesistente `test_l03_stats_azzerate_a_bot_fermo` (dipendenza d'ordine fra file
  di test Omega) non e' indagato.

## File toccati
- `Betfair/omega/omega_service.py`, `Betfair/omega/omega_config.py`, `frontend/src/lib/omega.ts`
- `Betfair/mike/engine.py`, `Betfair/mike/config.py`, `Betfair/mike/dossier.py`,
  `Betfair/mike/feed.py`, `Betfair/mike/service.py`, `frontend/src/lib/mike.ts`
- nuovi: `Betfair/omega/tests/test_o1_quote_prima_2026_09_25.py`,
  `Betfair/mike/tests/test_mike_veto_p_under35_2026_09_25.py`, questo referto.
- junction create nel worktree: `.venv`, `frontend/node_modules` (da togliere con
  `cmd /c rmdir`, MAI `git worktree remove --force`).

## Comandi eseguiti (tutti con `SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x`, `timeout`)
- `git fetch`; base `origin/master` = `fcc99e7` = HEAD del worktree.
- `pytest` sui 10 file Omega prima (242 passed, 1 failed preesistente) e dopo (idem; con il
  file nuovo 253 passed, 1 failed).
- `pytest` sui 18 file Mike prima (548 passed) e dopo (548 passed).
- `pytest` file nuovi: 11 + 29 = 40 passed.
- `pytest` 4 file extra (respiro, conto): 129 passed.
- 17 mutazioni (tabella sez. 4): 17 rosse dopo l'aggiunta del test di coerenza dei nodi.
- `npx tsc -p tsconfig.app.json --noEmit`: 0 errori; `npx vitest run` su 3 file: 117 passed.
