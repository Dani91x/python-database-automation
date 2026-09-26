# FASE 3 — pagine di admin-26 (Control Room, Segui Live, Market Watch, Tennis Terminal) — REFERTO PARZIALE (prima + seconda passata)

Delegato di certificazione, SOLA LETTURA, 26/09/2026 09:05-09:40 UTC. App accesa (pid 15624), bot
accesi in paper da altri tra le 09:10 e le 09:18 UTC (Omega, Mike, Safe tennis/model/manual, 4 bot tennis,
scalper calcio): le catture dopo le 09:14 hanno quindi posizioni paper vive.

## 0. Metodo e garanzie

- Pagine VERE (`pages/ControlRoom.tsx`, `SeguiLive.tsx`, `MarketWatch.tsx`, `TennisTerminal.tsx`) montate in
  jsdom (vitest, config propria `frontend/e2e_fase3_admin26/vitest.fase3.config.ts`) con il client Supabase
  VERO (service role dal `.env`, mai stampato) avvolto da uno SPECCHIO (`clientSpecchio.ts`): passano solo
  `select` e RPC `get_*`/`list_*`; ogni insert/update/upsert/delete e ogni altra RPC e' BLOCCATA (risposta
  d'errore finta, nessuna rete) e registrata. `svegliaBot` sostituito da un registratore. Realtime = stub.
  WebSocket = guscio spento del setup comune (`src/test/setup.ts`): **canali locali 47331-47338 NON letti**.
- **Scritture sul DB: ZERO.** Bloccate e registrate: 1 sola, `rpc('tennis_follow_event', {p_event_id:
  '36118619', p_market_id: '1.262933523'})` all'apertura del Tennis Terminal (vedi F-9). Nessuna nelle altre
  tre pagine (`out/*_chiamate.json`, campo `bloccate`).
- Ricalcolo indipendente: subito dopo ogni fotografia del DOM il test rilegge il DB con select MIE sulle
  tabelle (non le RPC della pagina) → `out/cr_db.json`, `sl_db.json`, `mw_db.json`, `tt_db.json`; le righe che
  la pagina ha letto sono in `out/*_chiamate.json` (`dati`). Formule reimplementate in
  `frontend/e2e_fase3_admin26/confronta_cr.py` (mai importate dal frontend). Esiti CR: `out/cr_esiti.json`,
  `out/cr_esiti.txt` (**90 PASS, 13 FAIL** di controllo, che corrispondono ai difetti F-1…F-7 sotto).
- Artefatti del banco dichiarati (NON difetti): (a) i canali locali sono spenti nel banco → ogni campo
  «fonte canale / spinta / età push» e' visto solo nel ramo DB; (b) realtime stub → dopo il primo caricamento
  i dati invecchiano solo nel ramo poll (es. Segui Live «⚠ DATI VECCHI 29s» = artefatto, NC); (c) primo giro
  di Market Watch catturato dentro un unico `act` di 20 s mostrava «OFF» e «MTM…»: era l'accodamento degli
  effetti di React nel banco, rifatto a passi di 2 s → la pagina mostra PAPER (nessun difetto).

## 1. Tabella per pagina

| pagina | id inventario nel perimetro | PASS | FAIL | NON CERTIFICATO |
|---|---|---|---|---|
| Control Room | U0165-U0272 (108) | 47 | 9 (U0192, U0194, U0209, U0239, U0260, U0262, U0232-dato, U0243 title, U0256) | 52 |
| Segui Live | U0282-U0344 (63) | 17 (2 provvisori, §7.2) | 1 (U0293) | 45 |
| Market Watch | U0345-U0353 (9) | 7 | 1 (U0351) | 1 |
| Tennis Terminal | U0356-U0367 (12) | 7 | 1 (U0361, scrittura all'apertura) | 4 |

(Aggiornata dopo la SECONDA PASSATA, §7. Prima passata: CR 38/7/63, SL 14/1/48, MW 6/1/2, TT 5/1/6.)

(U0232 conta PASS sul confronto pagina=DB; il reperto e' sul dato di fonte, F-8.)

## 2. FAIL con evidenza

**F-1 · U0209 — P&L «oggi» per bot sempre «—» per Omega/Mike/Safe (KO candidato §9-bis n.1 CONFERMATO).**
Cattura 09:19:38 UTC: `cr-bot-pnl-omega` = «oggi —», title «oggi non c'e' ancora niente di regolato per questo
bot»; `cr-bot-pnl-mike` idem. Stessa pagina, linguetta Posizioni chiuse · prova (09:20): Omega +0,95 € (trade 116,
settled 08:57:03 UTC), Mike +0,79 € (5063 +0,07 per ciclo, 5065 +1,62, 5069 −0,90), Safe tennis +0,03 € (341).
Causa: `frontend/src/components/controlroom/useControlRoom.ts:2236` `pnlOggi: isBotTennis(bot) ? pnlTennisDi(...) : null`.

**F-2 · U0192 / U0194 / U0249 — due verità sullo stesso denaro (giorno di piazzamento vs giorno di regolamento).**
Posizioni chiuse · prova oggi = +1,77 € su 5 operazioni (U0249, ricalcolo mio dal DB = +1,77 €, PASS). Nella stessa
pagina: la riga «in prova ±X su N operazioni simulate» (U0192, `cr-riga-paper`) e' ASSENTE e le tessere sport
(U0194) non mostrano nulla. La barra/riga paper usa il giorno di PIAZZAMENTO (`useControlRoom.ts:1987-2010`,
`righeGiornataPerCiclo`, «Paper invariato»); `get_safe_daily(2026-09-26,2026-09-26,null,'paper')` = `[]`
(stesso criterio: il 341 e' piazzato il 24/09); Posizioni chiuse usa il giorno di REGOLAMENTO
(`PosizioniChiuse.tsx`, title «per giorno di REGOLAMENTO»).

**F-3 · U0194 — tessere Calcio/Tennis: «giornata non ancora letta» quando la giornata E' stata letta (vuota).**
`get_safe_daily` chiamata 4 volte, tutte senza errore, 0 righe (log `out/cr_chiamate.json`). A video: «—» e
«giornata non ancora letta». Causa: `useControlRoom.ts:1290` `setSafeOggi((rDaily.value ?? [])[0] ?? null)` +
`SplitSport.tsx:69` `letto={perSport != null}`: «letta e vuota» collassa in «non letta», contro il commento del
componente stesso (`SplitSport.tsx:92-93`). (Il fatto che mostri SOLO Safe — KO §9-bis n.3 — resta confermato
dal codice `useControlRoom.ts:3480`; dal vivo non discriminante: nessun trade Safe calcio oggi.)

**F-4 · U0239 — «tick di movimento» col segno sbagliato e sul prezzo sbagliato.**
Title a video: «positivo = a favore della posizione». Misurato su 6 posizioni aperte (catture 09:19-09:20):
Omega 118 LAY 1@55, ora B 60 / L 110: «chiudi ora +0,08 €» (a favore) ma «−10 tick» (rosso); Mike 5071 BACK
5@1,60, ora B 1,62 / L 1,68: «chiudi ora −0,24 €» ma «+2 tick» (verde); Mike 5070 BACK 5@1,51: −0,19 € e
«0 tick»; Omega 119 LAY 1@80 (B 29): −1,76 € e «−8 tick» (atteso −17). Causa:
`frontend/src/components/controlroom/dettaglioRiga.ts:129-141`: misura sul prezzo dello STESSO lato (lay per un
lay) e il commento `:113-116` («su un LAY … si guadagna quando la quota SCENDE») e' finanziariamente falso (un
lay guadagna se la quota sale). «chiudi ora» invece e' GIUSTO su tutte e 6 (ricalcolo green-up lordo, PASS).

**F-5 · U0239 — «ingresso None-None» a video.** Righe Mike 5070/5071: `mike_trades.score_at_entry` =
stringa `'None-None'` (DB), scritta da `Betfair/mike/service.py:3616` `f"{payload.get('score_home')}-{payload.get('score_away')}"`
in pre-partita; la pagina (`cr-op-ingresso`) la stampa senza filtro.

**F-6 · U0260 — proposta di 41 ore fa mostrata come opportunità di oggi.** `safe_strategy_requests` #257
(Andorra v Malta, created 2026-09-24T16:03:30Z, status `proposed`, partita finita) e' nella colonna
Opportunità con «Piazza» presente e «partirebbe in PAPER»; unica difesa: «opportunità ancora valida: no».
Nessuna scadenza delle proposte `proposed` (lato servizio/lettura `lib/controlRoomProposte.ts:344-351`).

**F-7 · U0262 — «P del mercato» con due definizioni sulla stessa scheda.** Scheda #257 senza prezzo vivo:
P modello 97,6 %, P mercato 90,6 % (= `payload.p_implied` 0,905953, de-vig), Vantaggio 0,058 (= `payload.edge`
= p_model − 1/1,09 = 0,976−0,917). 97,6−90,6 = 7,0 ≠ 5,8. Con prezzo vivo (altre 3 schede) i tre numeri sono
coerenti (P mercato = 1/vivo): PASS. Difetto solo nel ramo «senza prezzo vivo» (`SchedaPropostaOpportunita.tsx`,
`ap?.edge ?? p.edge` con `p.p_implied` di altra natura).

**F-8 · U0232 (dato di fonte) — volume Match Odds «vol. 0,00 €» su 16/17 partite in gioco.** A video =
`safe_strategy_scan.payload.mo_total_matched` (PASS pagina=DB), ma nella mia select 19/19 righe calcio hanno 0 o
null anche in gioco (J2 al 50'), mentre il ladder della stessa partita (Segui Live) dice «Matched €559.65».
Sospetto sulla fonte `Betfair/safe_strategy/service.py:835` (`book.total_matched`). Da verificare col book
Betfair (passo A, non eseguibile qui).

**F-9 · U0293 (Segui Live) — banner avvisi: «CRITICAL [ORDER_MODE] modalita' LIVE attiva *** ORDINI REALI
(SOLDI VERI) attivi» mentre il modo effettivo e' PAPER.** `live_alerts` id 493 (08:57:03Z, non riconosciuto)
scritto da `Betfair/stream/runner.py:1629` con il modo del TETTO (`order_mode_tetto='live'`), mentre
`betfair_live_settings.order_mode='paper'` e il badge della stessa pagina dice PAPER. In più il banner porta 100
avvisi non riconosciuti dal 13/09 (53 RUNNER_WATCHDOG, 28 ORDER_MODE «LIVE attiva») senza data a video.

**F-10 · U0351 (Market Watch) — «LIVE · 5-7 6-2» per una partita FINITA.** A Bondar v Birrell (36118619):
`tennis_live_now.score.status='Finished'`, sets 1-2, games 1-6, mercato SUSPENDED/chiuso (attività FLB
«mercato_chiuso» 09:25:02Z); `MarketWatch.tsx:419` scrive «LIVE» fisso quando in gioco. Il `set_summary` del
runner ('5-7 6-2') omette il 3° set (1-6): stesso dato nel Tennis Terminal (U0357 = DB, PASS pagina, reperto dato).

**F-11 · U0361 (Tennis Terminal) — scrittura all'apertura CONFERMATA.** Bloccata dallo specchio:
`rpc('tennis_follow_event', {p_event_id:'36118619', p_market_id:'1.262933523'})`, da `pages/TennisTerminal.tsx:112-117`.

## 3. PASS (con la riga DB)

Control Room (cattura 09:19:38Z, confronto `confronta_cr.py`): U0165 giorno; U0166 esposizione live 0,00 € e
«+237,04 € in prova» (Omega 117-119 = 227 + Mike 5070/5071 = 10 + FLB lay 2@1,02 = 0,04); U0167 «0 / 38 · 6 in
prova»; U0168 −50,00 € = `stats.risk.daily_loss_stop`; U0169 modo live+paper e età battito (±5 s); U0171 modalità
di tutti i chip = `*_control.mode`; U0172 feed «stream» ed età; U0177 banner PAPER; U0178 obiettivo 100,00 €;
U0182 operazioni live 0; U0183 liability 0,00; U0188/U0189 saldo 40,56 € / esposizione 0,00 / «ultimo cambio 22
min»; U0199/U0200 PAPER, tetto LIVE; freno «rilasciato»; U0205/U0206 stato e modalità di 13 righe (Omega, Mike,
6 Safe, 4 tennis, scalper); U0212 Mike «tetto partite raggiunto: 2 su 2»; U0213 «fermato all'avvio» (presente a
bot fermi 09:08, assente a bot accesi); U0214 «3/2 posizioni aperte»; U0215 tutti gli importi (0,50 / 5 / 25 /
2-2-3-3 / 2×4); U0224 linguette (8 = 5 trade + 1 ordine tennis + 2 sessioni scalper); U0232 quote 1·X·2 17/17
= `payload.odds`; U0235 target 0,72 € = `omega stats.target_match`; U0237 «prova X» per 8 partite; U0239 «chiudi
ora» 6/6; U0243 «se finisce con N gol» (+2,85 = 5×0,60×0,95; +2,42 = 5×0,51×0,95; −5,00); U0249/U0252 chiuse prova
+1,77 € = Σ righe = Σ DB; U0260 contatore; U0262 3 schede su 4; U0267 catena #337 «3.0 s / 6.2 s» ricalcolata
da `meta.tempi/esecuzione` (nota: #337 e' del 22/09, live).
Segui Live (09:36:21Z): U0283-U0290 card (lega, «manuale», In streaming, squadre, 1-1, 72', OPEN, fonte betfair)
= `live_follow`/`get_live_follows`; U0291 nessun errore; U0294 «Registra» = `record false`; U0297 PAPER =
`live_now.state.order_mode`; U0299 72' · 1–1; U0303 saldo 40,56; U0304 runner+wd; U0306 book 102,2 % / 97,1 %
= Σ1/back, Σ1/lay della riga `live_now` letta (09:35:51); U0317/U0318/U0319 «db (poll 4 s)», nessuna posizione/
ordine = `betfair_live_positions` vuota per il mercato; U0342 P&L giornata €0.00 = `risk_state.total`.
Market Watch (09:36:50Z): U0345 PAPER; U0346/U0347 2 partite calcio con minuto/punteggio; U0348/U0349 MTM «—»,
rischio 0 (nessuna posizione); U0352 rischio 0,04 = FLB paper.
Tennis Terminal (09:37:16Z): U0356 intestazione; U0357 = `score.set_summary` (reperto F-10 sul dato); U0358
PAPER · SIMULATO; U0363 4 bot armati «Operativo»; U0365 attività = `tennis_bot_activity`.

## 4. NON CERTIFICATO (motivo)

- **Canale locale (banco con WebSocket spento):** U0170, U0173-U0175 ramo canale, U0207, U0298, ogni «fonte
  canale»/«senza spinta». Da fare con un lettore dei canali 47331-47338 affiancato (non fatto per tempo).
- **Pulsanti che scrivono (non si cliccano in sola lettura):** U0176 (ricarica: innocuo ma non provato), U0197,
  U0203, U0210, U0211, U0216-U0221, U0228, U0241, U0242, U0244 (approva), U0254, U0257, U0259, U0265, U0268-U0272
  (fogli), U0308-U0310, U0319 annulla, U0327-U0336, U0338, U0341, U0343, U0350, U0359, U0363 arma/disarma.
- **Stato non presente oggi (nessuna riga che lo alimenti):** U0179-U0181, U0184-U0187 valori live
  (nessuna riga live oggi: a video «—», coerente ma ramo del numero non esercitato), U0193, U0222, U0223, U0240,
  U0245, U0253 (0 proposte d'uscita), U0255, U0256, U0258, U0263-U0264 (non ricalcolati), U0302 stop, U0312
  pre-gol, U0337 X-Hedge, U0344 registro.
- **Non ricalcolati per tempo:** U0225/U0226 (conteggi competizioni/controllo), U0227 quote pre-match, U0230,
  U0231 latenze, U0233 minuto/punteggio calcio CR, U0234 tennis vivo CR, U0238 righe (prezzo/size ok a vista),
  U0243 P(4 gol)/λ/cash out Mike (serve `mike_events.ctx`), U0246-U0248, U0250-U0251, U0266 «feed/lettura»,
  Segui Live U0300, U0301, U0305, U0307 (artefatto realtime), U0311, U0313-U0316, U0320-U0326, U0328-U0330,
  U0339-U0340 (ladder: righe/WOM/PIQ/EV non ricalcolati; WOM a video 23 % vs DB 38,3/61,7 a istanti diversi),
  Market Watch U0353, Tennis Terminal U0359, U0362, U0364, U0366, U0367.
- **KO §9-bis n.2 (paper+live sommati)**: confermato da codice e dalla chiamata registrata
  `get_tennis_live_positions_all {p_mode: null}` e `get_live_positions_event` senza modo; NON manifesto oggi
  (nessuna riga live) → NC dal vivo.

## 5. Osservazioni (non FAIL)

Formati diversi fra pagine per lo stesso numero: CR «40,56 €», Segui Live/MW «€40.56» / «€0.00». Segui Live
«oggi +€0.00» legge `betfair_live_risk_state` il cui `mode` e' 'live' mentre si opera in PAPER. Tennis Terminal
«Equity bot (live)» con bot in paper. Scalper calcio «2 posizioni aperte» = sessioni con 0 ordini.

## 6. Come riprodurre (coordinatore)

```
cd frontend
npx vitest run --config e2e_fase3_admin26/vitest.fase3.config.ts controlroom   # ~100 s, out/cr_*.json
npx vitest run --config e2e_fase3_admin26/vitest.fase3.config.ts pagine        # ~90 s, out/sl_*, mw_*, tt_*
python e2e_fase3_admin26/confronta_cr.py                                        # out/cr_esiti.json/.txt
```
Verifica «zero scritture»: campo `bloccate` di `out/*_chiamate.json` (solo `tennis_follow_event` del Tennis
Terminal). Sonda DB GET: `.venv/Scripts/python.exe AUDIT_2026-09-25/e2e_fase2/sonda_fase3_db.py <tabella> "<qs>"`.
Falsificazione del banco non eseguita (tempo): i controlli di `confronta_cr.py` sono diventati rossi da soli su
6 difetti reali e su 5 miei errori di parsing poi corretti (tick tennis non inclusi, regex feed): non e' una
falsificazione formale.


## 7. SECONDA PASSATA (26/09, 09:40-10:05 UTC) — richiesta del coordinatore

Stesse regole della prima passata. Nessuna scrittura: lo specchio ha bloccato di nuovo SOLO `tennis_follow_event`
del Tennis Terminal. Nessun comando sui canali.
Nuovi file del banco: `wsGuardia.ts`, `confronta_canali_cr.py`, `confronta_pagine.py`, `confronta_mike.py`,
`falsifica.py`. Nuova sonda: `AUDIT_2026-09-25/e2e_fase2/sonda_fase3_canali.py`.

### 7.1 Canali locali accesi nel banco

- **Pagina.** Con `E2E_CANALI=1` il guscio spento diventa il WebSocket VERO (`ws` versione node, `wsGuardia.ts`),
  limitato a `ws://127.0.0.1:47331-47338`. **Ogni `send()` viene scartato e registrato**: nessun token (la pagina
  non può comandare), nessuna `sveglia`, nessuno `snapshot`.
  - Scartate: 4 richieste `{"m":"snapshot"}` di Segui Live verso il 47331.
  - Conseguenza: il rail di Segui Live resta «db (poll 4 s)», quindi il ramo canale di U0317-U0319 è NON CERTIFICATO.
- **Controprova indipendente.** In parallelo gira il MIO lettore puro (`/lettore/<topic>`; il server rifiuta ogni
  comando da un lettore, `local_channel.py:396-402`), che registra ogni messaggio in `out/canali_*.jsonl`. L'età a
  video si confronta con «istante del DOM − ultimo messaggio del topic» (stesso PC). Tolleranza 3 s: scatto di
  nowMs da 1 s più la ricezione dei due client.
- **Esiti Control Room** (`confronta_canali_cr.py` → `out/canali_cr_esiti.json`, cattura 09:45:58Z): **19/19 PASS**.
  - U0169: runner calcio «in streaming · live+paper · canale 0 s».
  - U0170: runner tennis «canale 0 s».
  - U0171/U0207, età della spinta:
    - Omega/Safe/Mike 1/1/0 s a video, contro 3,0/3,4/1,2 s del lettore;
    - i 4 bot tennis 7-8 s, contro 9,3-9,8 s.
  - U0171: scalper calcio «senza spinta», e il 47338 è rimasto muto per 170 s.
  - U0172-U0174: «stream · canale locale · stato canale».
  - U0175: righe Omega/Mike «db» (nessun `*_posizioni` pubblicato), righe Safe/Tennis «canale».
  - U0188: saldo 40,56 € = `account.available`.
  - U0199: «Ordini reali · canale».
- **Osservazioni (non FAIL)**
  - Il title «ultimo battito N s fa» del runner conta QUALUNQUE messaggio del 47331: il topic `battito` aveva 6,3 s.
  - La spinta del 47338 è intermittente: 0 messaggi in 170 s alle 09:45, 63 in 150 s alle 09:58.
  - Sono artefatti del banco (realtime finto; la riga DB aveva 2 s), quindi NC: «⚠ RUNNER GIÙ 30s» e «DATI VECCHI»
    in Segui Live, «agg. 27s fa» nel Tennis Terminal.
- **Evento dal vivo per il coordinatore.**
  - Alle 10:00:46Z il mio lettore ha visto chiudersi il 47331.
  - `live_alerts` 10:01:06Z: «RUNNER CRASHATO: exit code 1, uptime 3858s. Riavvio n. 1»; ripresa alle 10:01:22Z.
  - Alla ripresa è ricomparso «ORDER_MODE CRITICAL … LIVE attiva»: F-9 si ripete a ogni riavvio del runner.

### 7.2 Ricalcoli mancanti

- **Control Room** (`confronta_cr.py` sulla cattura 09:41:14Z: ora 101 PASS e 13 FAIL di controllo; i FAIL sono tutti
  F-1…F-7 già noti)
  - U0225: «31 partite in 10 competizioni» e «4 in 2» = righe scan lette dalla pagina (inplay e competition distinte). PASS.
  - U0227: quote pre-match 4/4 = `payload.odds`. PASS.
  - U0233: minuto e punteggio 17/17 schede calcio = `payload.minute/score_*`. PASS.
  - U0253: nastro «1 in attesa» = proposta Safe #265 `cashout`. PASS.
  - U0262: le schede LAY hanno Vantaggio = P mercato − P modello, coerente. PASS.
- **Mike** (`confronta_mike.py`, cattura 09:47:17Z)
  - P(4 gol) mercato 17,1 % e 16,3 %: coincide con `live.p4_market` pubblicato e col mio ricalcolo (17,2 % e 16,3 %).
    - Formula del servizio: `Betfair/mike/feed.py:159-172`, P(O3.5) − P(O4.5), de-vig sui best back.
    - Dati: righe `safe_strategy_scan.payload.ou` della mia select, tolleranza 0,6 punti. PASS.
  - Cash out −0,27 € (5@1,60 chiuso a lay 1,69) e −0,13 € (5@1,51 a 1,55). PASS.
  - λ «—» = dossier senza λ (fonte none). PASS.
  - «Se finisce con N gol» già PASS in prima passata.
- **F-13 (nuovo, U0243).** I title di `SchedaMike.tsx:120` e `:124` dicono «probabilità di 4+ gol», ma il numero è
  P(ESATTAMENTE 4) (`feed.py:160`; `p4_model` = `p_total_model[4]`). Un 17 % letto come «4 o più» sottostima il
  rischio vero dell'Under 3.5: P(>=4) = P(O3.5) ≈ 35-41 % sulle due partite.
- **F-12 (nuovo, U0256).** Scheda d'uscita Safe #265: Iwata, lay 2@50 su «Altro risultato Casa», uscita a tempo al 80′.
  - PASS: «Da chiudere 0,77 €» (= 2×50/130) e «se perde −98,00 €».
  - Il difetto:
    - «Chiudere adesso +1,23 €» è LORDO: `useControlRoom.ts:2516` usa `partialLockedPnl(prezzo, win, lose, 1)` senza
      commissione, poi `SchedaChiusura.tsx:148`.
    - «Tenere 1,90 €» è invece NETTO (`payload.hold_profit` = 2×0,95).
    - Il servizio stesso scrive `locked_at_decision: 1.17` (netto).
  - Effetto: due basi diverse affiancate nella stessa decisione, a favore del «chiudere».
- **Segui Live** (`confronta_pagine.py`, cattura 09:54:33Z, Oita–Fujieda, Match Odds)
  - Celle Back/Lay 205/206 = sumByTick del messaggio `ladder` del 47331 delle 09:54:31.4Z.
  - Matched 3/3 = `tv`.
  - WOM 3/3. Osservazione: il numero a video è lo SBILANCIO |back−lay| (`LadderView.tsx:316-341`), non la quota back.
  - Colonna EV 103/103 = evBack/evLay(prob del motore, prezzo, commissione 5 %).
  - **PROVVISORIO**: esito letto a console e NON rieseguibile oggi. La partita è finita e il file `sl_*_canale.json`
    è stato sovrascritto alle 10:00, quando il runner era crashato e l'unica partita calcio seguita era chiusa.
  - U0298 «⚡ LOCALE» presente a canale collegato. PASS.
- **Tennis Terminal** (cattura 10:00:30Z, Yu Bu–Majchrzak, mercato 1.262880764)
  - U0362: celle Back/Lay 165/168 = messaggio `ladder` del 47332 delle 10:00:30.06Z; Matched 8435,27 / 11368,78 = `tv`;
    WOM 63 % / 30 %. PASS.
  - U0366 stats = `tennis_live_now.score`: set 1-0, set-by-set 7-6, game 4-3, punti 0-0, win prob 78 %/22 %
    (`win_prob_p1` 0,7778), break 0/0. PASS; l'età a video è NC (artefatto).
- **Market Watch.** U0353 «Apri terminal tennis» compare quando `tennis_live_now.state.markets` c'è. PASS.

### 7.3 Falsificazione formale del banco (`falsifica.py` → `out/falsificazione.json`)

Metodo: copia dei JSON in `out/falsi/<caso>/`, UN valore alterato, `confronta_cr.py` rilanciato su quella copia (DB e
codice intatti). **5 ROSSI su 5**; sulla copia intatta tutti e 5 sono PASS.

| caso | campo | alterazione |
|---|---|---|
| saldo a video | U0188 | 40,56 → 40,57 |
| stop perdita nella select | U0168 | `daily_loss_stop` −50 → −49 |
| stake minimo Omega nella select | U0215 | `min_stake` 0,5 → 0,6 |
| obiettivo a video | U0178 | 100 → 101 |
| P&L del trade 116 nella select | U0249 | 0,95 → 1,95 |

### 7.4 Formule esatte per la decisione dell'utente

**KO §9-bis n.2 — paper e live sommati (Market Watch)**
- **MTM e Rischio calcio**
  1. `MarketWatch.tsx:182` chiama `fetchLivePositionsEvent(id)`, cioè la RPC `get_live_positions_event(p_event_id)`.
  2. La RPC (`migrations/betfair_live_pnl_journal.sql:258-280`) filtra solo `WHERE p.event_id = p_event_id`,
     **senza alcun filtro su `mode`**.
  3. Rischio: `MarketWatch.tsx:356` somma con `eventExposure(positions)` (`lib/eventPnl.ts:68-75`, Σ
     `selection_exposure`) su TUTTE le righe restituite.
  4. MTM: `eventMtm` (`MarketWatch.tsx:77`) usa le stesse righe.
- **Rischio tennis**
  1. `MarketWatch.tsx:284` chiama `fetchTennisPositionsAll()`, cioè `get_tennis_live_positions_all` con
     `p_mode: null` (registrato nel log del banco).
  2. La RPC (`migrations/tennis_live_positions_all_rpc.sql:19,27`: `WHERE (v_mode IS NULL OR ...)`) restituisce
     quindi tutte le modalità.
  3. `MarketWatch.tsx:430` somma con `eventExposure`.
- Oggi non si vede: non c'è nessuna riga live.
- Scelta dell'utente: filtrare sul `mode` corrente nella RPC o nella pagina, oppure mostrare due cifre separate.

**F-2 — due verità sullo stesso denaro (Control Room)**
- **Barra, riga «in prova» e P&L per bot**: `useControlRoom.ts:2005-2010` usa `righeGiornataPerCiclo`
  (`lib/composizioneObiettivo.ts:326-361`).
  - PAPER: giorno del PIAZZAMENTO (`:342-343`, `if (!delGiorno(a.placed_at)) continue`).
  - LIVE: giorno del REGOLAMENTO (`:356`, `pnl_betfair_settled_at ?? settled_at`; `:361`, `settled_at ?? placed_at`).
- **Tessere sport**: `get_safe_daily` usa il giorno del piazzamento
  (`migrations/safe_strategy_paper_live_2026-09-13.sql:329,344,348`, `pos_placed_at >= v_day`).
- **Posizioni chiuse**: la RPC `get_posizioni_chiuse_giornata(p_day, p_mode)` usa il giorno di REGOLAMENTO per
  entrambe le modalità (`migrations/posizioni_chiuse_giornata_2026-09-24.sql:9,26`).
- **Effetto oggi (paper)**: le stesse righe 116/341/5063/5065/5069 (+ tennis 4001) valgono +1,73/+1,77 € nelle
  Chiuse, ma 0 o niente nella barra, nelle tessere e nella colonna «oggi» dei bot.
- Scelta dell'utente: UNA sola regola del giorno (il regolamento per tutti, come dichiarano già le Chiuse), oppure
  etichette che dicano quale giorno si conta.

### 7.5 Ancora NON CERTIFICATO dopo la seconda passata

- Pulsanti che scrivono (invariato rispetto alla prima passata).
- Stati assenti oggi: nessuna riga live; niente X-Hedge, pre-gol, regole di rischio.
- Ramo canale del rail ordini/posizioni di Segui Live: le richieste `snapshot` sono bloccate apposta.
- Ladder calcio di Segui Live in forma rieseguibile: le partite seguite sono finite dopo il crash del runner delle 10:00.
- PIQ: nessun ordine mio in coda, la colonna è vuota (coerente).
- Chart/Depth (U0339-U0340, U0367): calcoli accumulati nel browser, non ricalcolati.
- U0266 «feed/spinta/lettura» della diagnostica.
- Tennis Terminal U0364: P&L lordo per bot, valori 0 dalle stats, non ricalcolati.
- Passo A (confronto col book Betfair vero): non eseguibile qui.

### 7.6 Riprodurre la seconda passata

```
# dalla radice: il lettore puro va avviato in parallelo, UNO per file (due lettori sullo stesso file ne mescolano le righe)
.venv/Scripts/python.exe AUDIT_2026-09-25/e2e_fase2/sonda_fase3_canali.py 170 frontend/e2e_fase3_admin26/out/canali_cr.jsonl
cd frontend
E2E_CANALI=1 npx vitest run --config e2e_fase3_admin26/vitest.fase3.config.ts controlroom
E2E_CANALI=1 E2E_EV_CALCIO=<evento calcio STREAMING> E2E_EV_TENNIS=<evento tennis> E2E_MK_TENNIS=<mercato> npx vitest run --config e2e_fase3_admin26/vitest.fase3.config.ts pagine -t "Segui|Tennis"
python e2e_fase3_admin26/confronta_canali_cr.py
python e2e_fase3_admin26/confronta_pagine.py _canale <file jsonl del lettore>
python e2e_fase3_admin26/confronta_mike.py
python e2e_fase3_admin26/confronta_cr.py
python e2e_fase3_admin26/falsifica.py
```

- Invii bloccati sui canali: campo `inviiBloccati` in `out/*_chiamate_canale.json`.
- Scritture DB bloccate: campo `bloccate`.
