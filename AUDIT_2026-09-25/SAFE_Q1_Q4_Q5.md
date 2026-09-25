# SAFE — decisioni dell'utente del 25/09 (Q1, Q4, Q5 + fase 2: Q7-Q12)

Delegato del coordinatore, worktree `agent-a7e908d15031bcc8b`. Base: portata a
`306fd11` (origin/master, contiene c5c8a92 e b4fef79) con fast-forward + riapplicazione
delle mie modifiche (vedi §0). Niente commit, niente push, nessuna scrittura sul DB,
NESSUN replay lanciato di proposito (vedi "non verificato" per l'unica eccezione).

## 0. Base e metodo

- **rebased su b4fef79** (e oltre: `306fd11`). Non potendo fare commit (il commit WIP
  è stato negato dal permesso), il riallineamento è stato: patch delle mie modifiche
  sui file toccati anche a monte (`certificazione_tennis.py`, poi `bot_service.py`,
  `BotParamsSheet.tsx`) → `git checkout` di quei soli file → `git merge --ff-only
  origin/master` → `git apply --3way` della patch. Applicata pulita tutte e due le volte;
  nessun conflitto. Test rilanciati dopo il riallineamento (numeri in §8).
- `frontend/node_modules` del worktree è una **GIUNZIONE** verso il checkout
  principale (per vitest/tsc). Va tolta con `cmd /c rmdir` prima di rimuovere il
  worktree (MAI `--force`). È stata tolta a fine lavoro (§8).
- Ogni test nuovo è falsificato con script di mutazione (ripristino dal contenuto in
  memoria + hash verificato, mai `git checkout`):
  `AUDIT_2026-09-25/sonde/mutazioni_safe_q1_q4_q5.py`,
  `AUDIT_2026-09-25/sonde/mutazioni_safe_q7_q12.py`,
  `AUDIT_2026-09-25/sonde/mutazioni_safe_ts_25_09.py`.

---

## 1. Q1 — BASE: quota di BANCA della perdente 20-34 (via la «Lettura A»)

Trascrizione: `4. STRATEGIA/2. Entrata a mercato.txt` @69.8-93.0: «Le quote ideali per
entrare a mercato [...] vanno dal 20 al 34, a dir tanto».

| | prima | dopo |
|---|---|---|
| default | `engine.py:197-198` `favLiveMin 1.2 / favLiveMax 1.34` | `engine.py:207-208` `dogLayMin 20 / dogLayMax 34` |
| filtro | check `favLive` (back live FAVORITA in [1.20,1.34]) `engine.py:960` | **tolto** |
| check `dogLay` | `engine.py:989` "Quota banca sfavorita disponibile", ok=True se il lay esiste | `engine.py:1095` "Quota banca sfavorita 20–34", ok = lay in [20,34] estremi inclusi; lay assente = n/d |
| merge | leggeva `favLive*` | legge `dogLayMin/Max`; `favLive*` **deprecate e ignorate** anche se restano sul DB |

- Fonte del prezzo: invariata, `odds.<lato sfavorita>.lay` della riga dello scanner, cioè
  lo stesso `entry_odds` con cui l'ordine parte. Stake fisso 2 € invariato; la scala per
  quota del foglio Excel NON applicata. Minuti, punteggi, bande pre-partita, uscite: invariati.
- Gemello TS: `frontend/src/lib/safeStrategy.ts` (BaseParams, DEFAULT_PARAMS, mergeParams,
  evaluateBase). UI parametri: `BotParamsSheet.tsx` (`base.dogLayMin/Max` al posto di
  `favLive*`), `ParamsSheet.tsx` (pannello legacy). Necessario: il test di parità
  `test_cert_2026_09_13.py::test_i_due_motori_hanno_esattamente_gli_stessi_numeri` confronta
  i DEFAULT_PARAMS dei due motori.
- **Banco** `certificazione.py`: `SPEC_BASE["dogLay"] = (20, 34)` (`:73`, era
  `favLive (1.20,1.34)`); **B8** (`:401`) = ingresso solo con banca in [20,34]: banda in uso
  confrontata col corso (non specchio), prezzo della riga e `entry_odds` dentro la banda;
  **B9** (`:430`) = nessun filtro sulla favorita (rosso se ricompare il check `favLive` o i
  parametri `favLive*` fra quelli risolti).
- Migrazione (facoltativa, il default vale già): `migrations/safe_base_banca_20_34_2026-09-25.sql`
  — toglie `favLiveMin/Max` da `params.base`, scrive `dogLayMin/Max` solo se mancanti. Idempotente.

## 2. Q4 — VETO dei campionati del corso (BASE, ESATTO, PUNTA)

Modulo: `Betfair/safe_strategy/veto_campionati.py` (gemello `frontend/src/lib/vetoCampionati.ts`,
lista confrontata byte per byte da un test Python). Check `campionato` in
`engine.campionato_check` (`engine.py:930`), inserito dopo `inplay` nelle tre varianti
(`:1032`, `:1129`, `:1230`). Motivo di scarto nel valore del check:
«veto campionato: Bundesliga 2 (corso)». Parametro `vetoCampionati` per variante,
default **True** (`engine.py:212/246/257`); False = nessun check.

Trascrizione: `2. SELEZIONE PARTITE/2. Competizioni da evitare.txt`.

| voce | citazione | sinonimi Betfair riconosciuti (a parole intere, senza accenti/maiuscole) |
|---|---|---|
| calcio femminile | @12.9 «primi su tutti calcio femminile e amichevoli [...] imprevedibilità elevatissimo» | women(s), ladies, (W), femminile, femenina/o, femenil, feminino/a, frauen, damen, dames, vrouwen, wsl, nwsl, damallsvenskan |
| amichevoli | @12.9-35.2 «stessa cosa vale per le amichevoli, non c'è l'agonismo [...] scartata proprio per sempre» | friendly/friendlies (Club/International Friendlies), amichevole/i, amistoso/s, testspiel(e), freundschaftsspiel(e) |
| coppe | @40.0-69.1 «Le coppe, qui il concetto è diverso, in particolare per le fasi finali e in generale comunque le partite con aspetto emotivo troppo elevato non vanno bene [...] soprattutto in fase iniziale assolutamente da evitare» | cup(s), coppa, copa, coupe, pokal, beker, taça, cupa, kupa, kupasi, puchar, supercup/supercoppa/supercopa/supercoupe, trophy, shield, champions league, europa league, conference league, libertadores, sudamericana |
| Bundesliga 2 | @90.0-98.5 «evitiamo le, soprattutto le loro serie B» + utente «2. Bundesliga NO» | bundesliga 2, 2. bundesliga, bundesliga ii, zweite bundesliga, 2nd bundesliga (esclusa la Bundesliga AUSTRIACA) |
| Bundesliga | @72.5 «Bundesliga e Redivisie [...] propensione al gol talmente elevata» | bundesliga, 1. bundesliga (esclusa austria/austrian/osterreich) |
| Eerste Divisie | @90.0-98.5 (serie B olandese) | eerste divisie, keuken kampioen (divisie) |
| Eredivisie | @72.5 (trascritto «Redivisie») | eredivisie |
| campionato boliviano | @102.0-116.5 «campionati un po' assurdi, quindi serie di boliviana, esempio [...] evitiamo totalmente» | bolivia, bolivian, boliviana, boliviano |

Letture dichiarate (da confermare, §9): **coppe = TUTTE** (dal nome Betfair la fase non si
ricava; la frase dice «in particolare per le fasi finali e in generale»); Champions/Europa/
Conference League, Libertadores, Sudamericana contate come coppe; Bolivia inclusa perché è
l'unico campionato NOMINATO (come esempio); nessun altro campionato aggiunto.
**Competizione assente** nella riga → veto non applicabile, nessun check (stessa regola dei
cartellini rossi). È il caso del banco di replay (`banco_comune`, LIMITE 1: `competition`
None): lì il veto non è esercitabile.

## 3. Q5 — Tennis: quota minima d'ingresso 1,01 → 1,02

- `engine.py:241` `backMin 1.01` → `engine.py:263` `backMin 1.02` (e gemello TS).
- Banco T1 (`certificazione_tennis.py:248`): prima leggeva la banda dai parametri (specchio,
  `:245` `lo, hi = _num(par.get("backMin"))...`); ora `SPEC_TENNIS_BACK_MIN = 1.02` (`:245`)
  e un `backMin` in uso diverso da 1,02 è ROSSO (anche None/testo).
- Migrazione `migrations/safe_tennis_backmin_102_2026-09-25.sql`: **serve davvero SE sul DB
  c'è `params.tennis.backMin`** (il valore del DB vince sul default del codice); lo porta a
  1.02 se diverso, lo dice (NOTICE). Non ho potuto leggere il DB: da verificare con la
  SELECT in testa al file.

## 4. Q7 — ESATTO: selezione aggiuntiva ACCESA «dove disponibile»

Trascrizione `RISULTATO ESATTO/1. SELEZIONE PARTITE/1. Come selezionare le partite.txt`:
@63.2-76.5 «si guardano queste statistiche qua [...] se ci sono troppi due a due, tre a tre,
quattro a due, quattro a uno insomma magari andiamo ad evitare»; @119.8-174.5 «i gol subiti
[...] non la squadra che voglio bancare, l'altra, e vado a vedere la sua difesa».

- Fonti vere trovate: la Dashboard legge `fixture_predictions.raw_json` (API-Football:
  `h2h`, `teams.*.league.goals.against`, `comparison.att/def`) — `pages/Dashboard.tsx:50-58`
  → `lib/normalizePrediction.ts`. **Safe NON legge `raw_json`**: legge solo `db_json_analisi`
  della fixture abbinata (`omega_db.fixture_analysis`, `omega_db.py:754-760`, catena λ di
  `bot_service`), che contiene λ/medie di lega ma **non** h2h né gol subiti per squadra.
  Il dato per partita che Safe HA GIÀ, senza letture nuove, è `selection_hint` della riga
  scan (scanner, `selezione.hint` dall'atlante `hazard_atlas_v2`: h2h 2-2/3-3 + gol subiti
  per partita della squadra) — è quello usato. Usare `raw_json` = colonna in più nella query
  e plumbing nuovo nel bot → **non fatto, proposta** (§9).
- Semantica nuova di `selection_check` (`engine.py:871`): ogni parte si giudica per conto
  suo; parte col dato → soglia (0,12 quota 2-2/3-3; 1,37 gol subiti dall'avversaria,
  `engine.py` esatto `h2hBigDrawRateMax/oppConcededMax`, delegati 16/09); parte senza dato →
  NON blocca e il valore lo dice («scontri diretti: dato assente» / «difesa: dato assente»;
  tutto assente → «dato assente (non blocca)», ok=True). Prima: dato assente = n/d = blocco
  (`engine.py:834/841` di HEAD).
- Default `requireSelection` False → **True** (`engine.py:236`; TS idem). Nessuna
  migrazione: la UI non espone la chiave (se sul DB fosse scritta a False resterebbe spenta —
  non verificabile senza DB).
- Banco **E10** riscritto (`certificazione.py:779`): rifà il conto parte per parte, rosso se
  il check è n/d, se un dato assente blocca, se una parte presente e violata passa, o lati
  invertiti.
- Nota: il corso cita anche 4-2 / 4-1 (e 3-2 «storcere il naso»); la regola resta
  2-2/3-3 come SPEC e soglia misurata → dubbio §9.

## 5. Q8 — mai un ingresso AL minuto di uscita o dopo

`bot_service.py:6174` (guardia) + helper `:6001-6021`: per BASE/ESATTO/PUNTA, se il minuto
del segnale ≥ `exits.<variante>_exit_minute` in uso (80/72/83, dagli stessi `exit_params`
delle uscite) → scarto `minuto_ingresso_oltre_uscita` con `minuto` e `minuto_uscita`.
Tennis escluso (niente minuto). È una guardia del BOT (come spread/liquidità): la checklist
della pagina può mostrare il segnale, il bot lo scarta dicendolo.

## 6. Q9 — un solo ingresso per variante e per partita

`bot_service.py:6228` + `_variante_gia_entrata` (`:6023`): se fra le chiavi già prese
dall'automatico nella stessa modalità (`traded_signal_keys`: origin auto, status ≠ error,
closes_trade_id null) esiste `<event_id>:<variante>:...`, il segnale è scartato
(`un_solo_ingresso_per_partita`), anche se la posizione è chiusa. **La chiave di dedup
`(event_id, signal_key)` e l'indice unico del DB NON cambiano**: è una guardia in più,
messa DOPO la guardia ESATTO lato-già-aperto (motivo più preciso). Vale anche per il tennis
(una chiave per partita di fatto). Caso «2-0 → 2-1 della perdente»: le uscite non sono
toccate (tenute come oggi); con Q9 però un NUOVO ingresso al 2-1 dopo un'uscita non avviene
→ dubbio §9.

## 7. Q10 — PUNTA con le bande pre-partita della BASE

`engine.pre_bands_checks` (`engine.py:999`) è l'UNICA implementazione delle bande favorita
1,40-1,80 / sfavorita 4-8, usata da BASE e PUNTA; `evaluate_punta(ctx, params, bande_pre)`
(`:1213`, check `:1273`) riceve `params["base"]` da `evaluate_football_all` (`:1340`); senza
argomento usa i default del codice. Nessuna chiave duplicata nella sezione `punta`. Gemello
TS `preBandsChecks` / `evaluatePunta(ctx, params, bandePre)`.

## 8. Q11 — finali tennis dai dati Betfair: NO

Prova: `RISCONTRO_TENNIS_2026-09-14.md:21` (399 mercati in 3 giorni, zero con
final/semi/quarter/round/R16/QF/SF nel nome evento o mercato; `event` ha solo id, name,
openDate, timezone; mercati solo Match Odds e Set Betting) e `certificazione_tennis.py` T10
(⊘ con causa). Nel feed Safe la riga tennis porta solo `competition` (nome torneo) —
`service.build_rows`; `betfair_tennis_odds.py:177-184` `competition_name` = nome della
competizione. Nessun campo di turno. **Veto non implementato.** Fonte proposta: (a)
euristica «ultima partita rimasta della competizione nel catalogo» — inaffidabile (scambia
i quarti per finali quando i turni dopo non sono pubblicati); (b) una fonte esterna di
tabelloni (API tennis con `round`) → richiede permesso per un processo/lettura nuova.

## 9. Q12 — tennis: quota pre-partita CONGELATA + sfavoriti estremi

- Congelamento: `scanner.freeze_pre_ko_tennis` (`scanner.py:442`), stesso schema di
  `freeze_pre_ko` calcio (si aggiorna prima dell'inizio, si congela al primo tick in-play,
  coppia completa o niente). `service.py:879` lo usa per il tennis (prima passava `None`,
  `service.py:869` di HEAD); riga tennis con chiave ADDITIVA `pre_ko` (`service.py:1638`);
  reidratazione al riavvio estesa al tennis (`service.py:1710`, `_pre_ko_usabile` `:221`,
  `db.is_usable_pre_ko_tennis` `db.py:116`, `load_scan_pre_ko` `db.py:111`) — stessa query
  di prima, nessuna lettura nuova.
- Contesto: `TennisMatchCtx.pre_match` (`engine._tennis_pre_match` `:785`).
- Regola: check `leaderPre` (`engine.py:1406`): quota pre-partita del giocatore che si punta
  ≤ `leaderPreMax`. Trascrizione `TENNIS/3. SELEZIONE PARTITE/2. Parametri.txt` @56.3-93.6:
  «meglio non andare su uno sfavorito, davvero troppo sfavorito [...] la loss diventerebbe
  troppo alta [...] prediligere sempre [...] almeno un leggero favorito». **Il video non dà
  un numero: default proposto 4,0** (prob. implicita 25 %), 0 = spento, esposto in
  `BotParamsSheet` (`tennis.leaderPreMax`). Dato assente → NON blocca, lo dichiara
  («pre-partita: dato assente (non blocca)»).
- «Match equilibrati»: nel video (`1. Match da evitare.txt` @65.5-103.7) è l'equilibrio IN
  CAMPO nel 2° set («0-1, 1-2, 2-2, 2-3»), non una quota pre-partita → **nessun filtro
  pre-partita aggiunto**; già coperto da `gamesLeadMin 2` e dall'uscita sul pareggio nel set.
  Da confermare (§11).
- Vantaggio di game: resta 2 per tutti (test dedicato).
- Contratto payload tennis aggiornato in `Betfair/stream/tests/test_banco_comune_2026_09_16.py`
  (`PAYLOAD_VERO_TENNIS` + `pre_ko`).

---

## 10. Test

File nuovi: `Betfair/safe_strategy/tests/test_safe_q1_q4_q5_2026_09_25.py`,
`Betfair/safe_strategy/tests/test_safe_q7_q12_2026_09_25.py`,
`frontend/src/lib/vetoCampionati.test.ts`, `frontend/src/lib/safeStrategy.q7q12.test.ts`.

Test ESISTENTI aggiornati (uno per uno):
- `test_engine.py`: fixture `calcio_payload` sfavorita da 8.0/8.4 → 24.0/25.0 (dentro 20-34)
  e le asserzioni sul prezzo (8.4→25.0, "8,40"→"25,00", payload inline `:638`, fixture
  favorita in trasferta); `test_base_no_quota_live_favorita_fuori_range` →
  `test_base_quota_live_favorita_non_filtra_piu` (ora "signal"); nuovi
  `test_base_banda_quota_di_banca_20_34_estremi_inclusi`, `..._dai_parametri`.
- `test_certificazione_c3_2026_09_16.py`: payload sfavorita 12/13 → 24/25;
  `test_b8_quota_live_favorita_fuori_banda_scatta` → `test_b8_banda_della_quota_di_banca_spostata_scatta`;
  nuovi B8/B9 (banda diversa, motore che ignora la banda, prezzo d'ordine fuori banda, bordi,
  `favLive` che ricompare, parametri Lettura A, favorita 1,60 non è veto); E10: `spenta_non_ha_casi`
  ora spegne a mano (il default è acceso), nuovo `accesa_di_default_ha_casi_e_tace_senza_dato`,
  `accesa_senza_il_check_scatta` costruito con parametro spento.
- `test_selezione_esatto_2026_09_16.py`: `test_spento_di_default_...` → `test_spento_non_aggiunge_nessun_check`
  + `test_q7_acceso_di_default`; `test_dato_assente_non_e_un_verdetto` (n/d) →
  `test_q7_dato_del_tutto_assente_non_blocca_e_lo_dichiara` + parziali; merge: malformato → True;
  `test_e10_scatta_se_un_dato_assente_diventa_un_verdetto` → `test_e10_scatta_se_un_dato_assente_blocca`
  + nuovi (n/d è difetto, parte presente violata ignorata); `senza_il_parametro` spegne a mano.
- `frontend/src/lib/safeStrategy.test.ts`: stesse fixture (24/25), test Lettura A → Q1.
- `Betfair/stream/tests/test_banco_comune_2026_09_16.py`: contratto chiavi payload tennis + `pre_ko`.

**Numeri finali (dopo il riallineamento a 306fd11), sandbox `SUPABASE_URL=http://127.0.0.1:9`, `-m "not cert"`:**
- Python, 41 file di test dei moduli toccati in `Betfair/safe_strategy/tests/` +
  `Betfair/stream/tests/test_banco_comune_2026_09_16.py` + `test_registro_bot_2026_09_16.py`:
  **1493 passed, 11 skipped, 5 deselected (cert), 1 xfailed, 0 failed**.
- vitest (safeStrategy, vetoCampionati, q7q12, components/safestrategy, pages/SafeStrategy*,
  safeBot, safeStrategyScan.localCanale): **25 file, 529 test, 0 falliti**.
- `tsc -p tsconfig.app.json --noEmit`: **0 errori**.

**Falsificazione (tutte ROSSE, file ripristinati con hash identico):**
- `mutazioni_safe_q1_q4_q5.py`: 20/20 rosse (Q1 ×4, Q4 ×9 compresa lista TS divergente,
  Q5 ×2, B8 ×3, B9 ×2). Un sopravvissuto al primo giro (B8 «prezzo del segnale») ha portato
  ai due test B8 isolati; rilanciato: rosso.
- `mutazioni_safe_q7_q12.py`: 22/22 rosse (Q7 ×5, Q8 ×3, Q9 ×3, Q10 ×2, Q12 ×9). Un
  sopravvissuto al primo giro (E10 «accetta n/d») ha portato a isolare il test
  `test_e10_scatta_se_un_dato_assente_torna_n_d`; rilanciato: rosso.
- `mutazioni_safe_ts_25_09.py` (motore della pagina): 11/11 rosse.

## 11. Dubbi da confermare con l'utente

1. Q4 coppe: TUTTE le coppe (lettura) o solo fasi finali (non riconoscibili dai dati)?
   Champions/Europa/Conference League, Libertadores, Sudamericana come coppe: ok?
2. Q4 Bolivia: il video la nomina «ad esempio» fra i campionati «assurdi»; inclusa. Altri no.
3. Q4 competizione assente: oggi il veto NON si applica (niente check). Alternativa: n/d = blocco.
4. Q4 donne riconosciute solo dal NOME DELLA COMPETIZIONE (non dai nomi squadra «(W)»).
5. Q7 il corso cita anche 4-2 / 4-1 (e 3-2): oggi si contano solo 2-2/3-3 (SPEC + soglia 0,12
   misurata su quelli). Allargare = rimisurare la soglia.
6. Q7 fonte più ricca (h2h e gol subiti di API-Football in `raw_json`, quelli della Dashboard):
   richiede una colonna in più nella query di `fixture_analysis` e plumbing bot→motore; la
   pagina (motore TS) non la vedrebbe senza passare dallo scanner. Serve il permesso.
7. Q9 «2-0 → 2-1 della perdente: tenere come oggi»: se significava «rientrare al 2-1 dopo
   un'uscita», con Q9 non avviene più (un solo ingresso). Le uscite non sono toccate.
8. Q12 soglia 4,0 per lo «sfavorito estremo»: proposta mia, da confermare.
9. Q12 «match equilibrati»: nessun filtro pre-partita (il video parla del punteggio in campo).
10. Q11 finali: nessun dato Betfair; scegliere tra euristica inaffidabile e fonte esterna.
11. Proposte non fatte (fuori perimetro): controlli del banco per Q4 (nessun segnale su
    campionato vietato), Q8, Q9, Q10, Q12.

## 12. Non verificato

- DB vero (sola lettura non fatta, per mandato): presenza di `favLive*`, `tennis.backMin`,
  `esatto.requireSelection` in `safe_strategy_control.params`. Se `tennis.backMin` = 1,01
  sul DB, Q5 NON è attiva finché non si applica la migrazione (T1 lo segnala in rosso).
- Nomi Betfair delle competizioni: presi dal codice/test e dalla conoscenza di Betfair, NON
  dal DB (per mandato): nessun elenco reale di `competition.name` consultato.
- Nessun replay di certificazione lanciato. ECCEZIONE dichiarata: il test non-`cert`
  `test_banco_comune_2026_09_16.py::test_banco_tennis_produce_una_riga_con_le_chiavi_della_tabella_vera`
  (suite dei file toccati) fa girare un breve segmento del banco su una registrazione tennis
  per controllare le chiavi della riga; è così che è emersa la chiave `pre_ko` nuova.
- `SPEC_STRATEGIA_S.md` NON aggiornato: è non versionato e vive solo nel checkout
  principale, fuori dal mio worktree (scrittura rifiutata dall'isolamento). Testo proposto
  qui sotto, da incollare dal coordinatore.
- App desktop non avviata, `npm run build` non lanciato.

### Testo proposto per `SPEC_STRATEGIA_S.md` (solo righe Q1/Q4/Q5)

- §1 tabella, riga «Quota di entrata (live)» → «Quota di entrata | **quota di BANCA della
  squadra che perde 20–34** (estremi inclusi) — corso «4. STRATEGIA/2. Entrata a mercato»
  @93.0: «vanno dal 20 al 34, a dir tanto». Decisione dell'utente 25/09: sostituisce la
  Lettura A (1,20–1,34 sulla favorita), che non è più un filtro.» Il riquadro «PUNTO AMBIGUO»
  e l'eccezione «Quota di entrata 1.20–1.34 = quota LIVE DELLA FAVORITA» e «QUOTA DI BANCA:
  NESSUN LIMITE» vanno marcati **superati il 25/09**.
- Nuova riga comune alle 3 varianti calcio: «Campionati da evitare (corso «2. SELEZIONE
  PARTITE/2. Competizioni da evitare»): calcio femminile e amichevoli @12.9; coppe @40.0;
  Bundesliga ed Eredivisie @72.5 e le loro serie B (2. Bundesliga, Eerste Divisie) @90.0;
  campionati "assurdi" come quello boliviano @103.5. Decisione dell'utente 25/09.»
- §3 tabella, riga «Quota punta (back)»: «≈1.03 — banda d'ingresso nel codice **1,02–1,10**
  (quota minima 1,02, decisione dell'utente 25/09)».
