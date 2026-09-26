# E2E FASE 2 — ORDINI PAPER, STRADA UNICA, SCHEDE B17 (§7.2, §7.5, §7.9.2, §7.9.5) — delegato admin-26

26/09/2026, app accesa (pid 15624), bot in PAPER (accensioni in `ACCENSIONE_ORA.txt`: Omega 09:10:26Z,
Safe 09:13:20Z e 09:16:16Z, scalper 09:17:58Z). SOLA LETTURA: DB solo GET PostgREST (select+limit), canali
senza token, nessun file del repo toccato fuori da `AUDIT_2026-09-25/e2e_fase2/` (referto + `sonda_ordini_*`).
Base del codice: master `075d91d`.

STATO: **CONSEGNA PARZIALE** — vedi §6 (cosa manca). Finestra osservata: 09:10Z–10:57Z con ascolto dei canali (il mio ascoltatore è stato fermato dal sistema per memoria bassa alle ~10:57Z, poi il guasto DNS 12:20-14:37Z); letture DB fino alle 14:43Z. Ordini paper Omega/Safe/Mike dopo le accensioni: **14** (Omega 4, Safe 4, Mike 6), tutti tra 09:10Z e 10:08Z: nessun ordine nuovo dopo le 10:08Z fino alle 14:43Z.

## 0. Strumenti (riproducibili)

| script | cosa fa |
|---|---|
| `sonda_ordini_db.py "<tabella>?select=...&limit=N"` | GET PostgREST, asserisce select+limit |
| `sonda_ordini_ascolto.py <min>` | ascolto senza token di 47331/47334/47335/47336; lo scanner (scan_calcio) salvato COMPATTO (MO, CS, HT, OU/BTTS/ht_result, `odds_ts_ms`, `odds_pt_ms`, `bet_delay`) solo al cambio per evento → `canali_ordini/*.jsonl` (partito 09:16:54Z, riavviato 09:22:29Z con OU/BTTS; ~100 MB/h di scanner: file NON da committare) |
| `sonda_ordini_catena.py --json sonda_ordini_catena_out.json --righe <tmp>` | ricostruzione della catena per ogni trade Omega/Safe dopo l'accensione: libro del feed prima/dopo la decisione, delta tick con `Betfair.stream.trading.risk_engine.ticks_between` (PRODUZIONE), libro a fill+`bet_delay` (specchio del FOK vero), `mercato_operabile(stato_da_riga_scan(...))` (PRODUZIONE, guardia unica), push del canale del bot vs riga DB, righe coda DB/specchio |
| `sonda_ordini_esito_b17.mjs <bundle> <righe.json>` | applica `esitoGamba`/`comeRigaOrdine`/`deltaTick` di PRODUZIONE (`frontend/src/lib/esitoAbbinamento.ts`, bundle esbuild nello scratchpad: `node_modules/.bin/esbuild src/lib/esitoAbbinamento.ts --bundle --format=esm --platform=node --outfile=<scratch>/esito.mjs`) alle righe DB |

## 1. REPERTO PRINCIPALE — gli ordini paper NON passano né dal canale né dalla CODA DB

Il brief dice «porte via canale spente → gli ordini paper vanno sulla coda DB». **Dal vivo non è così.**
Evidenza: `betfair_live_order_requests` — ultima riga id 99 del **10/07/2026**, 0 righe dopo le 09:10Z;
`betfair_live_orders` — 0 righe Omega/Safe (le sole righe nuove sono `source='scalper'`). TUTTI gli ordini
paper Omega/Safe di oggi sono stati riempiti dal **percorso legacy «fill istantaneo sullo snapshot del feed»**,
dichiarato con `omega_activity.kind='paper_fill_fallback' reason='follow_assente'` (Omega) e
`safe_strategy_trades.meta.fill='paper_fill:follow_assente'` (Safe).

Catena causale (codice + dati):
1. il gate della coda (paper E live) chiede l'evento in `live_follow` STREAMING:
   `Betfair/omega/omega_service.py:2788` (`return False, f"follow_{...}"`), usato da Safe via
   `Betfair/safe_strategy/execution.py:701` (`_gate`, riuso di `_flumine_gate`);
2. l'AUTO-FOLLOW (D-1) è montato (hello del 47331: `auto_follow.acceso=true, tetto_mercati=180, righe_db=true`)
   ma il suo giro proattivo parte SOLO con un bot calcio collegato al canale di comando:
   `Betfair/stream/auto_follow.py:867` (`if not attivi:` → libera le candidate e ritorna); stato pubblicato
   sul 47331 per tutta la finestra: `feed.attori=[]`, `eventi_auto=0`, `mercati_auto=0`,
   `conti.agganci_comando=0`; `live_follow` con `origine='auto'`: **0 righe in tutta la tabella**;
3. con `SAFE_/OMEGA_ORDINI_VIA_CANALE` spente nessun bot si collega al `/comando` → l'auto-follow non segue
   niente → il gate trova `follow_assente` → ripiego legacy (`omega_service.py:2528-2548`,
   `execution.py:752-790`): `E.paper_fill` sul SOLO best level del feed dello scanner
   (`omega_service.py:835`, ladder di un livello), **istantaneo, senza bet delay simulato**, senza coda,
   senza flumine `SimulatedExecution`.

Conseguenza per il trader (paper = specchio della realtà): il fill paper è al prezzo e al tempo dello
snapshot; in LIVE lo stesso ordine sarebbe un FOK dopo il bet delay (5 s in gioco). Ho misurato il
libro del feed a fill + 5 s per ogni ordine (§3, colonna «FOK a +bet delay»): su tutti gli ordini
osservati il FOK vero avrebbe abbinato allo stesso prezzo, quindi OGGI il ripiego non ha regalato fill; ma
la strada certificata (coda → flumine simulato con bet delay, o canale) **non è stata esercitata da nessun
ordine Omega/Safe**. Classificazione: **FAIL candidato di configurazione/progetto, non di codice**: il
comportamento è quello scritto (ripiego dichiarato), ma con le porte spente la D-1 («i bot operano da soli su
tutte le partite») non esiste di fatto per Omega/Safe e il paper resta sul percorso legacy. Da portare
all'utente: il test della strada unica e della coda richiede o le porte accese o un follow STREAMING
sull'evento. Nessuna correzione fatta.

Caso chiesto dal coordinatore (Omega trade 119, 36115980 FC Ryukyu v Ehime, lay «1 - 3» 80, min 51, 0-0):
(1) `follow_assente` perché `live_follow` non ha alcuna riga per 36115980 (né auto né manuale) e
l'auto-follow era dormiente (`attori=[]`, punto 2); (2) `paper_fill_fallback` =
`omega_service.py:2545` log, poi `E.paper_fill(size=1, best_price=80, lay_ladder=((80, lay_size),), limit=80)`
(`:2563`) → fill 1,00 @ 80,0 istantaneo (riserva 09:11:30.189Z → attività `place` 09:11:30.609Z, 420 ms),
liquidità = `lay_size` del feed al best; (3) libro del feed nello stesso istante: **non registrato da me**
(il mio ascolto parte alle 09:16:54Z; l'ascoltatore comune `canali/messaggi_*.jsonl` campiona scan_calcio
una volta al minuto per l'intero topic) → **NON CERTIFICATO** il confronto 1 tick per 117/118/119; alle
09:16:56Z il libro di «1 - 3» era back 29 / lay 110 (5 min dopo, non probante); (4) scheda: push
`omega_posizioni` (ascoltatore comune) `status=open, size_matched=1.0, avg_price_matched=80.0` = riga DB;
`esitoGamba` di produzione → fase `totale`, 0 tick vs prezzo della riga.

## 2. Tabella id → esito

| id | esito | evidenza sintetica |
|---|---|---|
| 7.2.1 auto-follow montato con MOTORE_ORDINI_CANALE=1 | **PASS** (dal canale, non dal log) | hello 47331 09:06:40Z/09:16:54Z/09:22:29Z: `auto_follow.acceso=true, tetto 180, limite 200, righe_db=true`; il blocco nasce solo dentro l'`if` del motore (`runner.py:1896-1903`). Log console non accessibile |
| 7.2.2 motore ordini attivo | **NON CERTIFICATO** | la riga di log `runner.py:1921` non è leggibile (stdout dell'app); il motore non pubblica stato proprio sul 47331; la cartella `_live_raw/_diario_ordini` non esiste (il `Diario` crea la cartella al primo record, `motore_ordini.py:190`): nessun comando ricevuto. Indiretto: `auto_follow` presente ⇒ l'`if` è stato eseguito |
| 7.2.3 Safe via canale | **NON CERTIFICATO (porta spenta)** | 0 attività `canale_inviato`; `meta.fill='paper_fill:follow_assente'` sui trade Safe |
| 7.2.4 marcature canale sul trade | **NON CERTIFICATO (porta spenta)** | trade 342/343 senza `canale_*` |
| 7.2.5 età comando < 3000 ms | **NON CERTIFICATO (porta spenta)** | diario assente |
| 7.2.6 Omega via canale | **NON CERTIFICATO (porta spenta)** | 0 `canale_inviato` in `omega_activity` |
| 7.2.7 nessuna riga coda per ordini via canale | **NON CERTIFICATO (porta spenta)** — vedi §1: 0 righe coda anche per gli ordini NON via canale | `betfair_live_order_requests` max id 99 (10/07) |
| 7.2.8 aggancio al volo | **NON CERTIFICATO (porta spenta)** | `conti.agganci_comando=0` per tutta la finestra |
| 7.2.9 0 «non sottoscritto» | **NON CERTIFICATO** | log non accessibile; nessun comando inviato (0 occorrenze in `omega_activity`/`safe_strategy_activity`, vacuo) |
| 7.2.10 tetto 180, manuali mai espulsi | **PASS parziale** | stato 47331: `mercati_seguiti=17 = mercati_manuali 17 /180`, `espulsi=0`, `rifiuti_tetto=0`; saturazione non provata (vietato seguire a mano). Vedi reperto R2 |
| 7.2.11 righe live_follow auto coerenti | **NON CERTIFICATO (0 righe auto)** + **REPERTO R2** | `live_follow origine='auto'`: 0 righe; le 2 righe di oggi (36090854, 36090788, STREAMING 09:18Z) sono `origine='manuale'` ma create dallo SCALPER auto-mode, non da un clic |
| 7.2.12 righe in volo al riavvio | **NON CERTIFICATO** | vietato riavviare l'app |
| 7.5.7 «Chiudi» per bot | **NON CERTIFICATO** | richiede clic in UI (fuori dal mio perimetro: nessun comando) |
| 7.5.8 esecuzione a mercato, nessun «fuori banda» | **PASS (osservato)** | 0 occorrenze di `banda` nelle attività Omega/Safe della finestra; tutti gli ordini eseguiti al best del feed (0 tick) |
| 7.9.2.B ref/prezzo/size lungo comando→aggancio→ordine | **NON CERTIFICATO (porta spenta)** | nessun comando; catena ricostruita sul ripiego (§3) |
| 7.9.2.C nessun ordine su mercato non operabile | **PASS sugli ordini registrati** (8: Omega 120, Safe 342/343, Mike 5072-5075; più 1 ordine Mike, 5074, piazzato 5,5 s PRIMA di una sospensione per gol: regolare) / NON CERTIFICATO 117-119 | `mercato_operabile` di produzione sullo stato CS del feed alla decisione e a +bet delay: sempre `(True,'OPEN')`; Omega salta da solo (`skip market_suspended` ×4, `mercato_sospeso` ×1 in uscita) |
| 7.9.2.E1-E5 | **NON CERTIFICATO** | richiedono azioni (fermare canale, saturare tetto, kill-switch, riavvio) vietate a questo delegato |
| 7.9.5.D numeri a video = riga/diario/libro | **PASS sui dati** per Omega/Safe (5 ordini con libro registrato); **FAIL (R7)** su Mike 5073/5074/5075 | push canale (`omega_posizioni`/`safe_posizioni_calcio`) = riga DB (status, size_matched, avg); `esitoGamba` di produzione → `totale`, delta 0 tick; libro feed alla decisione = prezzo abbinato (0 tick). Striscia B17 a video: non esiste per gli ordini AUTOMATICI (è legata a un clic, `esitoAbbinamento.ts:342-373`) → testo a video NON CERTIFICATO |
| 7.9.5.C banda al clic | **NON CERTIFICATO** | nessun clic su proposte (auto_trade_opportunities=false, nessuna approvazione) |
| 7.9.5.E1 clic su SUSPENDED | **NON CERTIFICATO** | nessun clic |
| 7.9.5.E2 replay PM3 | **NON ESEGUITO** | richiede permesso del coordinatore (un replay per bot) |
| 7.9.5.E3 FOK senza fill inventato | **PASS parziale (Safe) / OSSERVAZIONE (Omega)** | Safe ripiego uccide il parziale (`execution.py:766-769`); Omega ripiego ACCETTA il parziale (`omega_service.py:2577-2590`, `place_parziale`) mentre il live REST è FOK: divergenza paper/live nel codice, non scattata oggi (stake 1 €, `v3_min_lay_liquidity`=1,0) |

## 3. Catena degli ordini paper (ricostruita, UTC)

Colonne: decisione (riga/`tempi.t3`) · libro del feed ≤ decisione (età) · prezzo abbinato · Δ tick (produzione) ·
FOK a +bet delay (libro a fill+5 s: il live avrebbe abbinato?) · push canale = DB · percorso.

| bot/id | evento, selezione | decisione (UTC) | libro feed (età) | abbinato | Δ | FOK +bd | push=DB | percorso |
|---|---|---|---|---|---|---|---|---|
| Omega 117 | 36090940 Iwata–Vanraure, lay AOHW, 50', 0-1 | 09:10:57.749 | non registrato | 1,00 @ 95 | — | — | sì (ascoltatore comune) | legacy `follow_assente` |
| Omega 118 | 36090941 Imabari–Shonan, lay AOHW, 48', 1-1 | 09:10:58.575 | non registrato | 1,00 @ 55 | — | — | sì | legacy |
| Omega 119 | 36115980 Ryukyu–Ehime, lay «1 - 3», 51', 0-0 | 09:11:30.189 | non registrato | 1,00 @ 80 | — | — | sì | legacy |
| Omega 120 | 36115971 Kamatamare–Gifu, lay «Any Other Draw», 77', 2-4 | 09:38:44.187 | lay 48 / 4,73 € (925 ms) | 1,00 @ 48 | 0 | sì (48/4,73 a 09:38:49) | sì (seq 87, +414 ms) | legacy |
| Safe 342 esatto | 36090940, lay «Altro Casa», 62', 1-1 | 09:23:38.338 (quota Betfair 09:23:28.363, feed 29.326, letto 35.128) | lay 50 / 18,06 € (2,3 s) | 2,00 @ 50 | 0 | sì | sì (seq 162) | legacy `paper_fill:follow_assente` |
| Safe 343 esatto | 36115980, lay «Altro Ospite», 63', 0-1 | 09:25:04.906 | lay 55 / 25,37 € (537 ms) | 2,00 @ 55 | 0 | sì | sì (seq 209) | legacy |
| Safe 344 tennis | 36119297 Grant–Kalinina, back 1,02 | 10:04:01.553 | non registrato (tennis non nel mio ascolto fino alle 10:14Z) | 3,00 @ 1,02 | — | — | — | legacy |
| Safe 345 tennis | 36117297 Mert–Tikhonova, back 1,02 | 10:07:19.411 | non registrato | 3,00 @ 1,02 | — | — | — | legacy |
| Mike 5070/5071 | 36111770 / 36111764, back Under 3.5 (pre-partita) | 09:12:03 / 09:12:23 | non registrato | 5 @ 1,51 / 5 @ 1,60 | — | — | — | REST paper `execution_mode_rest` |
| Mike 5072 under_second | 36111770 Real Sociedad W–Real Madrid W, back U3.5, 2', 0-1 | differita 10:02:40 → eseguita 10:02:45 | back 1,38 / 3,44 € (2,4 s) | 2,50 @ 1,38 | 0 | sì | n/d | REST paper, bet delay 5 s simulato |
| Mike 5073 over_cover | 36111764 Badalona W–Granada W, back O4.5, 2', 0-0 | differita 10:03:11 (visto 5,7) → 10:03:17 | back **5,8** / 7,74 € | 1,34 @ **5,5** | **−3** | sì a 5,9 | n/d | idem |
| Mike 5074 over_cover | 36111770, back O4.5, 4', 0-1 | differita 10:04:39 (visto 2,88) → 10:04:44 | back **2,9** / 69,04 € | 2,52 @ **2,84** | **−3** | eseguita PRIMA della sospensione (SUSPENDED alle 10:04:49.9, gol 1-1) | n/d | idem |
| Mike 5075 over_cover | 36111770, back O4.5, 6', 1-1 | differita 10:07:45 (visto 1,9) → 10:07:50 | back **1,9** / 43,92 € | 5,37 @ **1,88** | **−2** | sì a 1,91 | n/d | idem |

Latenze misurate: riserva→fill Omega 250-470 ms; Safe decisione→risposta 324-384 ms; Safe quota→decisione
2,2 s (343), 1,7 s (344), 5,2 s (345), **10,0 s (342)**; Omega push canale del bot 0,4 s dopo la riserva.
Settlement: Omega 117-120 tutti `won` +0,95 € (09:56-10:03Z), Safe 342/343 `won` +1,90, 344/345 `won`.
Coda DB: 0 righe per tutti i 14 ordini; specchio `betfair_live_orders`: 0 righe Omega/Safe/Mike (Mike è fuori
dallo specchio per costruzione). Nota: le righe paper dello scalper nello specchio (id 37843-37847+) sono
state CANCELLATE dopo il crash del runner delle 10:00:46Z (`cleanup_paper_mirror`, `Betfair/stream/db.py:852-866`,
chiamata da `runner.py:1760` alla ripresa): coerente col progetto A6 ma cancella la traccia degli ordini paper
della mattina (per il confronto col DB di Z14 servono i log).

## 4. Reperti

- **R1 (FAIL candidato, configurazione)** — §1: strada unica/coda mai esercitate da Omega/Safe; tutti i fill
  paper sul ripiego legacy senza bet delay. `auto_follow.py:867`, `omega_service.py:2788,2528-2548`,
  `execution.py:701,752-790`.
- **R2 (FAIL candidato, dati)** — lo scalper auto-mode scrive `live_follow` SENZA `origine`
  (`Betfair/stream/scalper/scalper_service.py:165-178`, upsert `ignore_duplicates`), quindi prende il default
  `'manuale'` (`migrations/live_follow_origine_2026-09-25.sql:30`). Righe 36090854 e 36090788 (09:18:00Z,
  STREAMING, `origine='manuale'`) nate dall'armamento automatico (scalper_control `origine='auto'`,
  09:17:58Z accensione). Effetti: l'auto-follow le conta come follow MANUALI (17/17 mercati «manuali»),
  quindi mai espellibili e fuori dalla chiusura degli orfani (`chiudi_orfani` chiude solo `origine='auto'`);
  il Terminale le mostra come «seguite a mano». Nessun clic dell'utente le ha create.
- **R3 (osservazione, Omega)** — ripiego paper Omega accetta un fill parziale (`omega_service.py:2577`)
  mentre Safe lo uccide come il FOK live: due regole diverse per lo stesso caso (catalogo: parità paper/live).
- **R4 (osservazione, schede Safe proposte)** — nella stessa riga di proposta convivono due istantanee del
  libro: proposta 259 (Yamagata v Tosu, MO back): `payload.price=1.12, size_available=196.9`
  (`feed_updated_at` 09:22:18Z, coerente col feed: 1.12/196.9 a odds_ts 09:22:17.969Z) e
  `valutazione.al_prezzo.prezzo=1.13, valore 5.16` (feed 09:22:29.139Z: 1.13/5.16). Entrambi corretti alla
  loro ora; la scheda deve dire quale mostra (età/fonte), altrimenti il trader vede 1,12 «valida» e
  «non più valida» a 1,13 insieme.
- **R5 (fuori perimetro, per 7.9.7/opportunità)** — proposta 260 (Oita v Fujieda, `anomaly/ou_ladder`):
  «Over 2.5 back 1.62 con Over 7.5 a 1.04: quota incoerente». Il feed conferma Over 7.5 back 1.04 (28 €,
  lay assente) — un'offerta isolata su un mercato illiquido: una quota BACK bassa non implica P(O7.5)≈96%
  (è solo un limite superiore). Proposta generata su un dato spazzatura; non eseguita (auto_trade_anomalies=false).
- **R7 (FAIL, semantico money-relevant, Mike paper)** — il fill paper di Mike registra il PREZZO LIMITE
  della gamba, non il prezzo a cui Betfair abbinerebbe: `Betfair/mike/service.py:764-767` chiama
  `X.place(price=leg.price, ladder=(), best_size=avail_size)` e `Betfair/safe_strategy/execution.py:752`
  fa `E.paper_fill(size, best_price=price, ...)` → media = limite. Dal vivo: 5073 limite 5,5 col best back
  5,8 (−3 tick), 5074 2,84 vs 2,9 (−3), 5075 1,88 vs 1,9 (−2); un back limite sotto il best si abbina al best
  (miglioramento di prezzo). Il paper di Mike è quindi PESSIMISTA di 2-3 tick sulle coperture Over, i numeri
  (P&L, esposizione, `avg_price_matched` in scheda) non sono quelli che il live avrebbe. Oltre la tolleranza
  di 1 tick del brief. Per Omega/Safe non emerge perché il loro prezzo è già il best del feed. Nessuna correzione.
- **R6 (latenze Safe)** — trade 342: quota Betfair 09:23:28.363Z → riga feed 29.326Z → letta dal bot
  35.128Z (`feed_to_bot_ms` 5.802) → decisione 38.338Z (`prezzo_to_decisione_ms` 9.975) → fill 38.741Z.
  Il prezzo è rimasto 50 per tutto l'intervallo (fill coerente), ma 10 s fra quota e decisione sono fuori
  da ogni soglia di «al ms». Trade 343: 2.161 ms.

## 5. Cosa NON ho potuto verificare e perché

- log della console (righe `[runner] …`, `[auto-follow] …`, `[motore] …`): non accessibili (stdout dell'app);
- libro del feed per Omega 117/118/119 (prima dell'avvio del mio ascolto);
- tutto ciò che richiede porte accese, clic, riavvii, kill-switch o saturazione del tetto (vietati);
- testo della striscia B17 a video (nessun clic; gli ordini automatici non hanno striscia).

## 6. Consegna parziale — cosa manca

- libro del feed per Omega 117-119, Safe tennis 344/345, Mike 5070/5071 (prima/fuori dal mio ascolto);
- dalle 10:08Z alle 14:43Z nessun ordine nuovo Omega/Safe/Mike (Omega `nessun_candidato`/`senza_lay` sulle
  partite in corso; non ho misurato la lista delle partite idonee del pomeriggio perché la rete e poi la
  memoria hanno interrotto l'ascolto): la finestra 30-45 min con partite europee NON è stata coperta;
- tennis: ordini dei 4 bot tennis e dello scalper (fuori perimetro, altri delegati);
- tutti i NON CERTIFICATO della §2 che richiedono porte accese / clic / riavvii;
- processo stoppato dal sistema per memoria bassa (non rilanciato oltre i 50 min chiesti): `sonda_ordini_ascolto.py`
  (run3 10:14-10:57Z); rilanciato 14:38Z per 50 min su richiesta del coordinatore (run4).


---

# Riavvio 2, porte accese (seconda passata, 26/09 15:37Z-15:48Z, sola lettura)

App riavviata alle 16:52 locali con `SAFE_ORDINI_VIA_CANALE`, `OMEGA_ORDINI_VIA_CANALE`,
`MOTORE_ORDINI_CANALE_TENNIS`, `SAFE_TENNIS_ORDINI_VIA_CANALE` = 1; accensioni in `ACCENSIONE_ORA.txt`
«RIAVVIO 2» (Omega 15:16:04Z … scalper 15:33:12Z). Fonti: diario del motore (`_live_raw/_diario_ordini/2026-09-26.jsonl`
e `/tennis/2026-09-26.jsonl`, sola lettura), DB (GET), registratore leggero `sonda_ordini_ascolto.py`
(compatto, solo al cambio; file `canali_ordini/*_163904.jsonl` fino alle 15:29Z e `*_173735.jsonl` dalle 15:37Z,
**buco 15:29-15:37Z**). Script nuovo: `sonda_ordini_riavvio2.py --json sonda_ordini_riavvio2_out.json`.

## A. Trasversali

| controllo | osservato | esito |
|---|---|---|
| nessun ripiego istantaneo | `omega_activity kind='paper_fill_fallback'` dopo 15:16Z: **0**; Safe `meta.fill` con `follow_assente`: **0**; tutti i trade aperti hanno `meta.fill='flumine_paper'` | **PASS** |
| coda DB vuota | `betfair_live_order_requests` con `requested_at >= 15:16Z`: **0 righe** | **PASS** |
| attività nuove | Omega: `canale_inviato`, `flumine_fill`, `flumine_no_fill`; Safe: `canale_inviato`, `canale_rifiutato`, `flumine_fill`, `flumine_no_fill`, `place_pending`, `place_retry` | coerente |
| `live_follow origine='auto'` | **50 righe** (44 STREAMING, 6 CLOSED), la prima 36114438 creata 14:54:34Z | **PASS** (7.2.11) |
| auto-follow (47331) | 15:42:33Z: `attori=["omega","safe"]`, feed 67 partite, `eventi_auto 43`, `mercati_seguiti 179/180` (auto 153 + manuali 26), `per_priorita {candidata 41, comando 2}`, `agganci_comando 2`, `espulsi 0`, `rifiuti_tetto 0`; massimo osservato **180** (mai oltre); `ultimo_errore="stream di mercato non ancora connesso"` (residuo dell'avvio) | **PASS** 7.2.10 (tetto rispettato e SATURO: 24 partite del feed restano fuori) |

## B. Catena per ordine (13 ordini Omega/Safe/Safe-tennis dopo il riavvio)

Colonne: comando sul canale (attore, TIF, età = `ts_ms - creato_ms`) · aggancio · ordine flumine (`cor`) ·
specchio (`client_order_ref` = `ref_interno` awlq/awtq; placed/matched = dopo il bet delay simulato) ·
riga del bot · libro del feed all'istante del match (Δ tick con `ticks_between` di produzione).

| ref | comando | aggancio | ordine -> specchio | esito riga | libro al match | Δ |
|---|---|---|---|---|---|---|
| omega-t124 (VJS-KPV, lay AOHW 55) | omega, TIF null, 2457 ms | `in_aggancio` 15:21:21.100, **nessun book in 3000 ms**, rifiuto dichiarato 15:21:24.126 | nessun ordine | `error` | lay 55 (feed) | — |
| omega-t125 (Cheltenham-Chesterfield, lay AOAW 48) | omega, null, 115 ms | già seguito | 15:26:50.576 -> specchio placed 15:26:55.405, matched 55.606 | open 1 @ 48 | lay 48 / 33,1 € (15:26:55.250) | 0 |
| omega-t126 (VJS-KPV, «3 - 0» 50) | 99 ms | già seguito (dopo t124) | 15:30:48.635 -> 15:30:54.12 | open 1 @ 50 | non registrato (buco) | — |
| omega-t127 (Newport-Grimsby, «3 - 2») | comando **65**, 121 ms | già seguito | 15:31:21.654 -> matched 15:31:25.16 a **60** | open 1 @ 60 (miglioramento di prezzo del lay limite) | non registrato (buco) | — |
| omega-t128 (Sutton-Forest Green, AOHW 75) | 99 ms | `in_aggancio` 15:33:02.670, **agganciato dopo 1113 ms** | 15:33:03.791 -> 15:33:09.11 | open 1 @ 75 | non registrato (buco) | — |
| omega-t129 (Granada-Andorra, AOHW 55) | 103 ms | già seguito | 15:44:55.370 -> placed 15:45:00.762, matched .846 | open 1 @ 55 (`flumine_fill` 15:45:04.985) | lay 55 / 180,14 € (15:44:54.801) | 0 |
| safe_tennis-t346 | nessun invio | **rifiuto** `runner_non_agganciato: nessun framework flumine attivo ... aggancio richiesto` (15:24:28, attività `canale_rifiutato`) | nessun ordine | `error` | back 1,02 | — |
| safe_tennis-t347 (Maristany-Pieri, back 1,02) | safe_tennis, **FOK**, 108 ms | già seguito | 15:24:36.981 -> specchio tennis awtq9000000000 matched | 3 @ 1,02, poi `won` | back 1,02 / 130,99 € (15:24:33.301) | 0 |
| safe-t348 (Fleetwood-Rochdale, esatto lay «Altro Casa» 40) | safe, **FOK**, 118 ms | già seguito | 15:27:18.141 -> placed 15:27:21.475, matched .647 | open 2 @ 40 | lay 40 / 61,48 € (15:27:20.286) | 0 |
| safe-t349 (York-Gillingham, esatto lay 46) | safe, FOK, 137 ms | già seguito | 15:28:00.124 -> 15:28:03.442/.538 | open 2 @ 46 | lay 46 / 108,34 € (15:28:02.873) | 0 |
| safe_tennis-t350 (back, limite 1,08) | FOK, 102 ms | `in_aggancio`, **agganciato dopo 2176 ms** | 15:40:07.806 -> awtq9000000001 matched a **1,11** | open 3 @ 1,11 | back 1,11 / 47,64 € (15:40:03.315, ultimo prima del match) | 0 |
| safe_tennis-t351 (Zverev, back 1,02) | FOK, 98 ms | già seguito | 15:40:06.108 -> awtq9000000002 **size_matched 0** | `error` (FOK ucciso) | back **1,01** dalle 15:40:03 alle 15:40:17 (1,02 non disponibile dopo il bet delay) | FOK corretto |
| safe_tennis-t352 (Zverev, back 1,02, ritento) | FOK, 102 ms | già seguito | 15:40:30.204 -> awtq9000000003 matched | open 3 @ 1,02 | back 1,02 / 32,77 € (15:40:29.903) | 0 |

Sintesi: **8 ordini con libro registrato, tutti a 0 tick** (125, 129, 347, 348, 349, 350, 352 abbinati al best
dopo il bet delay; 351 FOK ucciso esattamente mentre il best era sotto il limite). Nessun fill inventato.
`ref` identica su comando/aggancio/`meta.canale_ref` (13/13); prezzo e size del comando uguali all'ordine flumine
(11/11 ordini inviati). Età dei comandi 98-137 ms (una a 2457 ms, sempre < 3000). Bet delay simulato: 3,3-5,6 s
fra ordine e specchio, col `bet_delay=3` pubblicato dal feed.

## C. Tabella id -> esito aggiornata (riavvio 2)

| id | esito | evidenza |
|---|---|---|
| 7.2.1 | PASS | auto-follow attivo e operativo (§A) |
| 7.2.2 | **PASS** | diario del motore scritto (`_live_raw/_diario_ordini/2026-09-26.jsonl`, righe `inviato/in_aggancio/agganciato/ordine/esito`) |
| 7.2.3 | **PASS** | `safe_strategy_activity kind='canale_inviato'` per safe-t348/349 e safe_tennis-t347/350-352 |
| 7.2.4 | **PASS parziale** | `canale_ref`, `canale_ack_seq`, `canale_ack_ms` su tutte le righe inviate; `canale_fase` **NULL** su omega-t124/125 e safe-t349; `abbinato_parziale` su safe_tennis-t352 che è abbinato 3/3 (R10) |
| 7.2.5 | **PASS** | età 98-137 ms, massimo 2457 ms (omega-t124), tutte < `max_eta_ms` 3000 |
| 7.2.6 | **PASS** | `omega_activity` `canale_inviato` + `flumine_fill` (t125-t129) |
| 7.2.7 | **PASS** | 0 righe in coda DB dopo 15:16Z |
| 7.2.8 | **PASS 2/3, 1 rifiuto dichiarato** | agganciati omega-t128 (1113 ms) e safe_tennis-t350 (2176 ms); omega-t124 `in_aggancio` scaduto a 3000 ms con motivo scritto, nessun ordine; la ripetizione (t126, 15:30:48) sullo stesso mercato è partita |
| 7.2.9 | **PASS** | 0 occorrenze di «non sottoscritto nel runner» nei due diari |
| 7.2.10 | **PASS** | T massimo 180/180, mai oltre; `espulsi 0`, `rifiuti_tetto 0`; manuali 26 intatti |
| 7.2.11 | **PASS** | 50 righe `origine='auto'` (44 STREAMING, 6 CLOSED) |
| 7.2.12 | NON CERTIFICATO | nessun riavvio osservato con un comando in volo |
| 7.2.13 | PASS (fase 1) | — |
| 7.5.7 | NON CERTIFICATO | nessun clic «Chiudi» osservato |
| 7.5.8 | PASS | nessun «fuori banda»; esecuzione a mercato (t127 abbinato a 60 col limite a 65) |
| 7.9.2.B | **PASS** | ref uguale sulle 4 letture (comando, aggancio, `meta.canale_ref`, riga); `customerOrderRef` di flumine (`cor`) nel diario, specchio per `ref_interno`; prezzo e size uguali |
| 7.9.2.C | PASS | `mercato_operabile` (produzione) = `(True,'OPEN')` sugli 8 ordini con libro |
| 7.9.5.D | PASS sui dati | abbinato sulla riga = specchio (`size_matched`/`average_price_matched`) per t125-t129, t348, t349; Δ 0 tick col libro. Striscia B17: solo per clic, non osservata |
| 7.9.5.E3 | **PASS** | safe_tennis-t351: FOK ucciso con best 1,01 < limite 1,02, `size_matched=0`, nessun fill parziale |

## D. Reperti nuovi (nessuna correzione)

- **R8 (osservazione, già dichiarata nel codice)** — gli ordini Omega paper via canale partono SENZA FOK
  (`time_in_force=null`, `omega_service.py:2892`: FOK solo in live; in paper il limite lavora il book fino al TTL).
  Safe usa il FOK anche in paper. Oggi tutti gli ordini Omega hanno abbinato subito, ma il paper di Omega non è
  lo specchio del FOK live.
- **R9 (FAIL candidato, attribuzione)** — gli ordini dei bot NON sono marcati col nome del bot nello specchio
  (regola del 25/09 «ordini flaggati col nome del bot»): calcio `betfair_live_orders.source='runner'` per
  Omega/Safe (id 42963-43460); tennis `tennis_live_orders.source='manual'` per Safe tennis (id 24, 28, 17016,
  17020), perché il motore tennis passa da `_track_manual`, che scrive `"source": "manual"` fisso
  (`Betfair/stream/tennis_live/tennis_live_order_worker.py:960`, chiamato a `:644,676,904`). Nelle voci per bot
  gli ordini di Safe tennis finiscono sotto «manuale app».
- **R10 (dato)** — `safe_tennis-t352`: `meta.canale_fase='abbinato_parziale'` con `size_matched=3.0 = size`
  (specchio awtq9000000003 abbinato 3/3): la fase non è aggiornata all'abbinamento completo; `canale_fase` NULL
  su 3 righe.
- **R11 (FAIL candidato LATENTE, money-critical solo in LIVE)** — i `ref_interno` dei comandi del motore ripartono
  da `awlq9000000000` a ogni avvio del processo (`_LOCAL_RID = itertools.count(9_000_000_000)`,
  `Betfair/stream/live_order_worker.py:3087`; tennis `_LOCAL_SID`, `tennis_live_order_worker.py:1302`). Oggi il
  motore ha assegnato `awlq9000000000` a omega-t124; lo stesso `client_order_ref` esiste già nello specchio come
  riga **LIVE** del 10/07 (`betfair_live_orders.id=37551`, mode live, market 1.259819675). Lo specchio fa upsert
  su `(mode, client_order_ref)` (`Betfair/stream/db.py:572-577`): in paper la collisione è evitata dalla pulizia
  delle righe paper al riavvio (`db.py:852`), ma in LIVE il primo ordine via canale dopo ogni riavvio
  sovrascriverebbe la riga live di un ordine vero di una sessione precedente (già oggi: id 37551). Il commento
  «mai in collisione col bigserial» vale solo dentro un processo. Da portare all'utente PRIMA di accendere le
  porte in live.
- **R12 (osservazione)** — `safe_tennis-t346` rifiutato `runner_non_agganciato` alle 15:24:28 (runner tennis ancora
  senza framework dopo l'avvio): rifiuto dichiarato, nessun ordine; il bot ha ripetuto (t347 alle 15:24:36, abbinato).

## E. Cosa non ho potuto verificare (riavvio 2)

- libro per omega-t126/t127/t128 (buco del registratore 15:29-15:37Z): in particolare t127, abbinato a 60 col
  limite a 65, non è confrontato col book;
- 7.2.12, 7.5.7 e i controlli E1-E5 di 7.9.2 (richiedono riavvii, clic o azioni vietate);
- il registratore resta acceso fino a ~16:32Z (55 min, file `canali_ordini/*_173735.jsonl`); gli ordini dopo le
  15:48Z non sono nel referto.
