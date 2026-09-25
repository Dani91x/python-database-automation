# SAFE — decisioni dell'utente del 25/09 sui dubbi §11 (D5, 7 punti)

Delegato del coordinatore, worktree `agent-a03640a33cfa385c7`, base `2f04bc4`
(origin/master, contiene `000d8f6` ed `e35e70e`). Niente commit, niente push,
nessuna scrittura sul DB. Patch: `AUDIT_2026-09-25/safe_d5.patch` (+ file nuovi, §9).

Cambiato SOLO ciò che l'utente ha deciso. `bot_service.py` ed `exits.py` NON toccati.

---

## 1. Coppe ammesse, veto SOLO sulle FINALI

- **Prima**: `veto_campionati.py` voce `coppe` (cup, coppa, pokal, champions league…) = tutte le coppe vietate.
- **Ora**: voce `coppe` tolta (`veto_campionati.py:74`, commento con la frase dell'utente). Una partita è vietata se è una **FINALE** di qualunque competizione:
  - **fonte (a)**: round API-Football della fixture abbinata, `matches.raw_json->league->>round` (`fixture_predictions` il round NON lo ha: verificato sul DB). Lo scanner lo pubblica come chiave additiva `fixture_round` (`service.py:1621`). Regola `veto_campionati.is_round_finale` (`:189-219`): **finale** se l'ULTIMO pezzo (split su « - ») è esattamente Final/Finals/Grand Final/Gran Final/Finale, o se il PRIMO è esattamente «Final» e l'ultimo non è un numero di giornata; **mai** Semi-finals, Quarter-finals, 8th Finals, 1/2 Final, Elimination Finals, Final Round - 3, Finals - 11, 3rd Place Final, Placement … Final.
  - Nomi veri misurati (sonda `sonde/d5_round_finali_sola_lettura.py`, output `sonde/d5_round_finali_output.txt`, 2 finestre maggio-luglio 2025/2026): «Final» 488, «Semi-finals» 620, «Quarter-finals» 372, «Clausura - Final» 30, «Promotion Play-offs - Finals» 56, «Relegation Play-offs - Finals» 37, «Final - Relegation» 8, «3rd Place Final» 8, «Finals - 1…11», «Final Round - 1…5» …
  - **fonte (b)**, solo se il round manca: nome evento Betfair con «Final» parola intera e senza semi/quarter/place (`nome_indica_finale`, `:222`).
  - Motivi: «veto finale: round «Final» (API-Football)» / «veto finale: «Final» nel nome evento (Betfair)».
- Motore: `engine.campionato_check` (`engine.py:1042`) ora riceve anche home/away/round/nome evento via `_campionato_ctx` (`:1089`), usato dalle tre varianti (`:1170`, `:1267`, `:1369`). Contesto: `FootballMatchCtx.fixture_round` (`:596`, letto a `:766`). Gemello TS: `vetoCampionati.ts:141` (`isRoundFinale`), `:160`; `safeStrategy.ts:817` (`campionatoCheck`), `:660` (lettura di `fixture_round`).
- Decisione dichiarata: le finali di **play-off/playout** («Promotion Play-offs - Final», «Relegation - Final») contano come finali; le finali per un piazzamento (3° posto) NO.

## 2. Bolivia tolta
`veto_campionati.py:108` (+ TS). Restano: femminile, amichevoli, Bundesliga, 2. Bundesliga, Eerste Divisie, Eredivisie.

## 3. Competizione assente: invariato
Nessun check se la competizione manca **e** non scattano le regole nuove (nome squadra femminile, finale). Una finale riconosciuta dal round resta vietata anche senza competizione (è un dato diverso). Test `test_d5_p1_finale_anche_con_competizione_assente`.

## 4. Femminile anche dai nomi squadra
`veto_campionati.squadra_femminile` (`:155-168`): parole intere «women», «ladies», «femminile», «femenino», «frauen» (dell'utente) + varianti dichiarate «womens», «femenina»; «(W)» → «w» vale **solo come ultima parola** (così «W Connection», club maschile di Trinidad, non scatta). Motivo: «veto campionato: calcio femminile (nome squadra) (corso)». Gemello TS `vetoCampionati.ts:124`.

## 5. ESATTO: scontri diretti VERI dal DB
- **Fonte**: la stessa della Dashboard (`pages/Dashboard.tsx:50-58` legge `fixture_predictions.raw_json`; `H2HSection.tsx` = `raw_json.response[0].h2h`). Nessuna RPC/tabella h2h separata esiste nel frontend.
- **Regola del corso** («RISULTATO ESATTO/1. SELEZIONE PARTITE/1. Come selezionare le partite»): @63.2-76.5 «se ci sono troppi due a due, tre a tre, quattro a due, quattro a uno insomma magari andiamo ad evitare»; @79.5 «zero a zero, uno uno, uno zero, due a zero, due a uno […] quelle caratteristiche che si può»; @99.3 «c'è solo un tre a due che mi fa storcere un po' il naso». Il video NON dice quanti scontri diretti: si usano tutti quelli del DB (API-Football ne dà fino a ~10).
- «Partita da tanti gol» = **4+ gol a fine 90'** (`score.fulltime`, i supplementari non contano), solo partite finite FT/AET/PEN (`selezione.conta_scontri_diretti`, `selezione.py:281`).
- Soglia `h2hManyGoalsRateMax` **0,58** (`engine.py:256`): stesso metodo del 16/09 («troppi» = doppio della norma); norma misurata sull'atlante locale (47.460 partite, 4.838 coppie): **29,22 %** ha 4+ gol. `h2hMinMeetings` **3** (`:259`): sotto, il conto non blocca e lo dice. `h2hBigDrawRateMax` deprecata e ignorata.
- Nota dichiarata nel valore del check: «h2h: 8 partite, 2 con ≥4 gol · difesa avversaria 1,60 gol subiti · forze att 45-55 · def 60-40»; senza h2h nel DB: «h2h: nessuno scontro diretto nel DB (non blocca)»; fixture non abbinata: «scontri diretti: dato assente» (non blocca, Q7).
- Difesa avversaria: `teams.<lato>.last_5.goals.against.average` (ultime 5, il video guarda le ultime partite), soglia 1,37 invariata.
- **Letture** (scanner, `selezione.SchedeFixture` `selezione.py:391`; query in `db.py:150-190`): finestra fixture ±12 h ogni 10 min (`omega_db.fixtures_for_window`, stessa query del matcher di Omega e della catena λ del bot); per le fixture NUOVE di un giro una SELECT a blocchi di 40 su `fixture_predictions` con sole proiezioni JSON (h2h, comparison, last_5 — mai l'intero raw_json) e una su `matches` (solo il round). Una volta per partita, cache per evento; errore DB → pausa 60 s, mai eccezioni. Solo partite candidate (in-play o finestra pre-KO). Abbinamento: `betfair_match.resolve_matches` (quello di Omega), niente fuzzy di riserva; orientamento casa/ospite deciso dai nomi (lati scambiati se invertito). Aggiornamento SOLO nel `tick` (`service.py:2039` → `hydrate_schede` `:1706`); `build_rows` legge la cache (`:1618-1621`) → il banco di replay non tocca il DB.
- Motore `engine.selection_check` (`engine.py:909`), gemello TS `safeStrategy.ts:978`; banco E10 aggiornato (`certificazione.py:806-822`).
- **Nota di comportamento**: un cambio solo di `selection_hint`/`fixture_round` non è «critico» per il freno di pubblicazione: arriva nella riga al giro successivo al freno per-evento (pochi secondi), non si perde.

## 6. Forze attacco/difesa della Dashboard
`raw_json.response[0].comparison.att/def` (voci «Attacco»/«Difesa» del «CONFRONTO DIRETTO», `ComparisonSection.tsx`), nella STESSA SELECT del punto 5. **Solo dichiarate** nella nota (`engine._forze_testo` `:991`): il video non dà una soglia, e inventarla cambierebbe la strategia.

## 7. Tennis: super favorito < 1,20
- **Prima**: `leaderPreMax` 4,0 sulla quota pre-partita del leader.
- **Ora**: `favSuperMax` **1,20** (`engine.py:315`), check `leaderPre` → `engine.tennis_sfavorito_estremo_check` (`:1013`, usato a `:1548`): se la quota back pre-partita CONGELATA (`pre_ko`, `scanner.freeze_pre_ko_tennis`) del FAVORITO è **< 1,20** (stretto) e il leader che si punta è l'ALTRO → escluso, nota «favorito pre-match 1,12 → sfavorito estremo: escluso». Se si punta il favorito → ok. Quote pari → nessun favorito. 0 = spento. Dato assente → non blocca. `leaderPreMax` deprecata e ignorata. UI: `BotParamsSheet.tsx:234` (`tennis.favSuperMax`), `ParamsSheet.tsx`. Gemello TS `safeStrategy.ts:1051`.
- **Calcio**: nessun filtro nuovo. Il video del calcio non parla di «sfavorito estremo»; dice «ci deve essere una leggera favorita e una leggera sfavorita» (`4. STRATEGIA/1. La base` @44.1) e le bande pre-partita (favorita 1,40-1,80, sfavorita 4-8) di BASE e PUNTA già escludono un favorito < 1,20.
- **Misura** (sonda `sonde/d5_misura_super_favorito.py`, output `sonde/d5_misura_super_favorito_output.txt`, sola lettura, 25 SELECT):

| fonte | n | fav < 1,15 | fav < 1,20 | fav < 1,25 | fav < 1,30 |
|---|---|---|---|---|---|
| A. tennis, registrazioni Betfair locali (esito vero) | 21 | 3 (14,3 %), 0 rimonte | 7 (33,3 %), **1/7 = 14,3 %** rimonte | 7, 1/7 | 8, 1/8 |
| B. tennis, DB `tennis_markets` pre-partita dal 15/07 (niente esito) | 62 | 11,3 % | **14,5 %** (quota media 1,100 → sconfitta implicita 9,1 %) | 19,4 % | 29,0 % |
| C. calcio, `fixture_predictions` 10/08-23/09, 1X2 bookmaker + esito | 1.664 | 61, 13,1 % non vinte | 91 (5,5 %), **15/91 = 16,5 %** non vinte (implicito 10,0 %) | 123, 16,3 % | 163, 19,6 % |

  Lettura: sotto 1,20 il favorito non vince circa 1 volta su 6-7 (calcio 16,5 %, tennis 1/7); da 1,20 a 1,30 il tasso sale (calcio 19,6 %). I dati NON indicano una soglia migliore di 1,20 con sicurezza: il tennis ha solo 21 esiti (le registrazioni partono spesso in-play, il DB non ha il vincitore). **Default 1,20** come deciso; 1,15 escluderebbe ~3 punti percentuali di match in meno, 1,25 ~5 in più.

---

## 8. Test e falsificazione

Sandbox `SUPABASE_URL=http://127.0.0.1:9`, `-m "not cert"`:
- **Python**: `Betfair/safe_strategy/tests` (tutta la cartella) + `Betfair/stream/tests/test_banco_comune_2026_09_16.py`: **1810 passed, 11 skipped, 5 deselected, 1 xfailed, 0 failed**. Nuovo: `test_safe_d5_2026_09_25.py` (110 test).
- **vitest**: `safeStrategy.d5.test.ts` (nuovo), `vetoCampionati.test.ts`, `safeStrategy.q7q12.test.ts`, `safeStrategy.test.ts`, `components/safestrategy`, `pages`: **34 file, 676 passed, 1 skipped, 0 falliti**.
- **tsc** `-p tsconfig.app.json --noEmit`: **0 errori**.
- Test esistenti aggiornati: `test_safe_q1_q4_q5` (coppe e Bolivia da VIETATI a LECITI), `test_safe_q7_q12` (Q7 nuove chiavi/soglia; Q12 regola sul favorito, `favSuperMax`), `test_selezione_esatto_2026_09_16` (fonte DB, 4+ gol, 0,58, minimo 3, E10), `test_banco_comune` (contratto: chiave additiva `fixture_round`), `vetoCampionati.test.ts`, `safeStrategy.q7q12.test.ts`.
- **Falsificazione** (ripristino da memoria + hash, mai `git checkout`):
  - `sonde/mutazioni_safe_d5.py`: **30/30 rosse** (P1 ×7, P2, P4 ×2, P5 ×14, P6, P7 ×4, lista TS divergente). Al primo giro 2 frammenti non trovati per le fine riga CRLF di `veto_campionati.py`/`db.py`: script corretto, rilanciate le 2, rosse (output `sonde/mutazioni_safe_d5_output.txt`).
  - `sonde/mutazioni_safe_d5_ts.py` (motore della pagina): **16/16 rosse** (output `sonde/mutazioni_safe_d5_ts_output.txt`).

## 9. File

Modificati: `Betfair/safe_strategy/{engine,veto_campionati,selezione,db,service,certificazione}.py`, i 3 test Safe citati, `Betfair/stream/tests/test_banco_comune_2026_09_16.py`, `frontend/src/lib/{safeStrategy,safeStrategyScan,vetoCampionati}.ts`, `frontend/src/lib/{vetoCampionati,safeStrategy.q7q12}.test.ts`, `frontend/src/components/safestrategy/{BotParamsSheet,ParamsSheet}.tsx`.
Nuovi: `Betfair/safe_strategy/tests/test_safe_d5_2026_09_25.py`, `frontend/src/lib/safeStrategy.d5.test.ts`, sonde `AUDIT_2026-09-25/sonde/d5_*.py` (+ output), `mutazioni_safe_d5*.py` (+ output), questo referto.

## 10. Dubbi per l'utente

1. **Soglia h2h 0,58** (doppio della norma dei 4+ gol, 29,22 %). L'esempio del video («solo un tre a due […] al limite ma fattibile») suggerirebbe una tolleranza più stretta (~20-30 %). Serve la scelta dell'utente.
2. **4+ gol** include anche 3-1 e 4-0 (non nominati nel video, ma «tanti gol»); 3-2 incluso («storcere il naso»).
3. **Minimo 3 scontri diretti** per giudicare (lettura mia, come l'atlante).
4. **Finali di play-off/playout** contate come finali; finali per il 3° posto no.
5. **Forze attacco/difesa** solo in nota, senza soglia: se l'utente vuole un filtro, serve un numero.
6. **Tennis, corso «4. STRATEGIA/1. La base» @52.8**: «se lo sfavorito vince, meglio tre game di vantaggio» — NON applicato (l'utente il 25/09 aveva detto «lasciamo 2»); segnalo solo che il video lo dice.
7. La chiave vecchia (`h2hBigDrawRateMax`, `leaderPreMax`) eventualmente salvata sul DB è ignorata; nessuna migrazione scritta.

## 11. Non verificato

- **Nessun run vero dello scanner** contro il DB: l'abbinamento Betfair→fixture e le query sono provati con finti dalle chiavi vere e con le sonde di sola lettura, non nel processo in esercizio. Da guardare al primo avvio: log `[safe-selezione]`, fase «pre_ko» del cronometro (ci passa anche `hydrate_schede`).
- Carico DB reale non misurato (stima: 1 query/10 min per la finestra + 2 query per giro solo quando entrano partite nuove).
- Una fixture la cui scheda è vuota/senza raw_json al primo tentativo NON viene riletta durante la partita (dato assente per quella partita).
- Replay di certificazione non lanciati (il banco non ha DB: `fixture_round`/`selection_hint` restano None lì, veto finale e h2h non esercitabili nel banco).
- App desktop non avviata, `npm run build` non lanciato.
- Letture DB fatte (tutte SELECT): sonde schema (2 volte, la seconda per errore mio lanciando lo script con un argomento), copertura, round finali (1 tentativo andato in timeout 57014 sull'intera tabella, poi su finestre), forma quote, misura punto 7.
- `SPEC_STRATEGIA_S.md` non aggiornato (fuori dal worktree).
