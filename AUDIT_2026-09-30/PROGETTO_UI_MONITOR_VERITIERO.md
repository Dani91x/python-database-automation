# PROGETTO - UI «monitor veritiero» per il trader (30/09/2026)

Revisore-progettista in SOLA LETTURA, base master `30917ed`. Nessun file del repo modificato
(solo questo referto). DB letto in sola lettura il 30/09 alle 14:10-14:20 UTC (16:10-16:20 Roma).
Estende `AUDIT_2026-09-30/AUDIT_UI_VERIDICITA.md` (36 reperti su Mike/Control Room): quei reperti
NON sono ripetuti; qui si tratta cio' che il trader ha visto oggi nelle 6 sezioni.

Ordine dell'utente: «quello che vede il trader deve essere accurato, reale e preciso [...] massima
coerenza [...] NON DOVETE ROMPERE NULLA [...] le migliorie valgono per TUTTI i bot [...] il trader
deve capire esattamente cosa sta succedendo, sia su ordini sia su PnL». Modifiche chirurgiche.

Percorsi: `frontend/src/...` salvo `Betfair/...` e `migrations/...`.

---

## 0. I FATTI DI OGGI (DB, sola lettura) che spiegano le cifre

Righe LIVE di Mike non regolate alle 14:17 UTC (`mike_trades`, stato `open`):

| id | partita | ruolo | cosa e' davvero | colonna `liability` |
|---|---|---|---|---|
| 5085 | Follo v Sarpsborg | punta Under 3,5 5,00 @ 2,40 | abbinata, VIVA | 5,00 |
| 5094 | Follo v Sarpsborg | banca Under 4,5 6,32 @ 1,76 (copertura) | abbinata, VIVA | 4,80 |
| 5087 | FC Vsetin v Bohemians | punta Under 3,5 5,00 @ 2,12 | abbinata | 5,00 |
| 5089 | FC Vsetin v Bohemians | banca ko_green richiesta 5,10 @ 2,08 | abbinata SOLO 1,00, resto ritirato (`phase=cancelled`, `ritirato_da_noi`) | 5,51 (sulla richiesta) |
| 5090 | FC Vsetin v Bohemians | banca Under 4,5 5,05 @ 1,48 | abbinata | 2,42 |
| 5091 | Farul (W) v Sparta Prague (W) | punta Under 3,5 5,00 @ 2,87 | abbinata | 5,00 |
| 5092 | Farul (W) v Sparta Prague (W) | banca green Under 3,5 5,06 @ 2,84 | abbinata: la partita e' PAREGGIATA (+0,05/+0,06) | 9,31 |
| | | | **somma lorda** | **37,04** |

- Righe `error` di Follo (5086 `reconciled_not_placed`, 5093 `cancelled_by_engine` / `ritirato_da_noi`): due banche di green-up MAI abbinate, **ritirate**, non rifiutate da Betfair.
- **Ordini FUORI dai bot** (specchio `betfair_live_orders`, `client_order_ref = ext...`, piazzati dal sito/app): su FC Vsetin punta **Over 3,5** 4,34+0,09 @ 1,92 e punta **Under 4,5** 5,18 @ 1,44 (~13:31 UTC). Con questi la partita di Vsetin, sul CONTO, e' praticamente chiusa: Under 3,5 ≈ +0,09/+0,08, linea 4,5 ≈ −0,15/−0,13.
- **Esposizione Betfair** (`betfair_live_account.exposure`, getAccountFunds): **−9,95** alle 14:04 UTC = Follo 9,80 + Vsetin 0,15 + Farul 0. Torna al centesimo.
- **Mike invece crede** (`mike_events.live`): Follo `LIVE_COVERED` liability 9,80 cash out −0,74; **Vsetin `LIVE_COVERED` liability 6,42, cash out +0,16** (non vede gli ordini del sito); Farul `IDLE_LIVE` liability 0.
- `betfair_live_risk_state`: `limit_value = null`, `reason = limit_off`: **nessuno stop perdita sul conto e' attivo oggi**.
- `pnl_reale_oggi` (conto): 0 ordini regolati oggi, `letto_at` 12:41 UTC (scrittura solo al cambio: l'eta' reale della lettura non e' nota alla pagina).
- Paper regolato oggi alle 12:41 UTC (riavvio): **Safe** 4 righe del 26/09 = **+7,60**; **Mike** 5 righe del 26/09 (Latvia U21 v Germany U21, MVV v Helmond) = **−18,29**. La UI mostra solo il +7,60 (vedi §2.3).

Tre cifre dell'esposizione, stesso istante, tre significati:

| Cifra | Dove | Formula | Vera come rischio? |
|---|---|---|---|
| 39,15 (37,04 alle 14:17) | testata «Esposizione» e Obiettivo «Liability aperta» | somma LORDA della colonna `liability` di ogni riga live non regolata di Omega/Safe/Mike/tennis, solo partite del feed | **NO**: conta Farul (pareggiata) 14,31, conta Vsetin 12,93 (sul conto 0,15), conta la ko_green 5089 sulla richiesta e non sull'abbinato |
| 9,80 | scheda Follo «resp.» | stessa somma lorda, per la sola partita | si', per coincidenza (con 4 gol esatti perdono entrambe le gambe) |
| −10,15 / −9,95 | «Esposizione» del saldo conto | getAccountFunds: caso peggiore per MERCATO, nettato, TUTTO il conto (bot+sito+app) | **SI'**: e' la verita' del conto |
| (16,22) | non mostrata | somma di `live.liability` NETTA dei servizi (Mike 9,80 + 6,42 + 0) = `aggregates.open_liability`, codice morto `useControlRoom.ts:3507` | vera per la «credenza» dei bot, falsa su Vsetin per gli ordini del sito |

La differenza residua 39,15 → 37,04 dipende dall'istante (righe che cambiano stato fra la tua schermata e la mia lettura): non l'ho ricostruita al centesimo.

---

## 1. SEZIONE 1 - Intestazione della Control Room

Componente: `Testata`, `pages/ControlRoom.tsx:930-1025`; dati da `components/controlroom/useControlRoom.ts` (VM restituito a `:3663-3700`).

### 1.A Da dove viene / 1.B E' vero?

| Testo | Codice | Fonte | Vero per il trader? |
|---|---|---|---|
| «Esposizione 39,15» | `ControlRoom.tsx:958-963`; `totaliGiornata` `lib/controlRoom.ts:1082-1115` (`:1101`); per partita `soldiPerPartita` `:668-712` → `groupCicliByEvent` `lib/eventGroups.ts:291-293` | righe dei bot (RPC `get_omega_trades`, `get_safe_state`, `get_mike_state`, `get_tennis_bot_orders_today`), solo partite presenti in `safe_strategy_scan` | **NO**. Somma lorda, non nettata; conta gambe `cancelled/pending/hedged` (`isSettled` `eventGroups.ts:104`); tennis sulla size RICHIESTA (`controlRoom.ts:529-537`); esclude scalper, ordini del sito/app, partite uscite dal feed. Oggi 4× il conto |
| «Con posizione 3 / 28» | `ControlRoom.tsx:964-970`; numeratore `controlRoom.ts:1100`, denominatore `:1094` | partite del feed con almeno una riga live non regolata / tutte le righe di `safe_strategy_scan` calcio+tennis | **Parziale**. 3 = Follo, Vsetin, Farul: ma Farul e' pareggiata e Vsetin e' chiusa sul conto dal sito. Rischio vero su **1** partita. «28» = il programma dello scanner, non partite operate |
| «Stop perdita −50,00» | `ControlRoom.tsx:971`, `Freni` `:1086-1100`; `useControlRoom.ts:3674` `freni = safe.control.stats.risk` | default `Betfair/safe_strategy/risk.py:43` (−50), override `safe_strategy_control.params.risk.daily_loss_stop`; applicato da Safe (`risk.py:188-202`, `bot_service.py:6427`) solo sulle NUOVE aperture automatiche di Safe | **NO come presentato**: e' lo stop di **SAFE** (oggi in paper), non del conto. Stop del conto (`daily_stop_worker.py`, `betfair_live_settings.daily_loss_limit`) oggi **SPENTO** (`limit_off`); Mike ha il suo (`mike/config.py:318`, 50), Omega il suo (`omega_config.py:37`/`:262`). «Non modificabile» perche' la testata non ha editor: il valore si cambia solo dal foglio parametri di Safe |
| «Runner in streaming · live+paper · canale 1 s» | `ControlRoom.tsx:972`, `Runner` `:1038-1078` (modo `:1073`); `runnerDalCanale` `lib/runnerCanale.ts:119-154` | «LIVE+PAPER» = `heartbeat_mode()` `Betfair/stream/runner.py:2176-2192`: `.env LIVE_ORDER_MODE == LIVE` | **Oscuro**: vuol dire «il runner PUO' servire ordini veri e simulati (tetto del .env)», non «in che modo sta operando un bot». Il modo ordini effettivo e' nella riga «Ordini reali» (`sovrapponiModoOrdini`, `runnerCanale.ts:236`) |
| «Runner tennis vivo, in attesa · paper · canale 0 s» | `ControlRoom.tsx:973` | `TENNIS_LIVE_ORDER_MODE` (`tennis_runner.py:138-140`) sul canale 47332 | vero, stessa oscurita' |
| «Omega paper · senza spinta · stato db 6 s» | chip `ControlRoom.tsx:1148-1160`; `etaPushS` `useControlRoom.ts:2239-2240`; `fonteDi` `:2275-2278` | «senza spinta» = nessun push `omega_stato` sul 47334 da quando la pagina e' aperta. Omega pubblica solo a fine giro ATTIVO (`omega_service.py:8197`, esce prima a `:7924-7949` se non `running`) | **Vero ma incomprensibile**: non distingue «bot fermo, per costruzione non invia» da «bot acceso ma muto (guasto)». «stato db 6 s» e' l'eta' della LETTURA della pagina (`lettoAlle`, ogni 30 s), non del battito di Omega |
| «Safe paper · 0 s · stato canale 0 s», «Mike LIVE · 1 s · stato canale 1 s» | idem | `control.mode` delle RPC + push `*_stato` | modalita' vera (modo del servizio). Nota: Omega/Mike fissano il modo sulla PARTITA: il chip puo' dire paper con una partita armata in live (`mike/service.py:3717-3723`) |
| «Scalper paper · Pro paper · FLB paper · Swing paper · 2 s» | chip tennis `useControlRoom.ts:2301-2313` | `get_tennis_bot_services` + 47337 | vero |
| «Scalper calcio modalita' ignota · senza spinta» | `ControlRoom.tsx:1165-1169`; `statoBotScalper` `lib/scalperControlRoom.ts:350-382` (`:363-364`) | modo solo se sessione viva o interruttore `running`; da spento `null` | **Incoerente**: gli altri bot mostrano il modo anche da fermi. Lo scalper pubblica solo al cambio (`scalper_service.py:397-402`) → «senza spinta» permanente da spento |
| «feed rest 6 s» | `ControlRoom.tsx:979-985`; `useControlRoom.ts:3693`, `:3627` | `safe_strategy_status(scanner).payload.source` (`safe_strategy/service.py:2160`) | **Vero ma nascosto**: «rest» = lo scanner e' in RIPIEGO (stream fermo) ed e' scritto in grigio; il colore guarda solo l'eta' |
| «canale locale · stato canale · righe Omega db 7 s Safe canale 0 s Mike db 7 s Tennis db 7 s» | `ControlRoom.tsx:990-1016`; `fonteScan` `:3633`, `fonteStatoScanner` `:3679`, `fonteRighe` `:3638-3658` | tecnico: da quale tubo arriva ogni dato | vero ma gergo tecnico; nessun trader lo usa per decidere. Scalper assente |

### 1.C Progetto «da trader»

La testata diventa un **monitor a tre fasce**, stessa grammatica per ogni bot.

**Fascia 1 - SOLDI VERI ADESSO (fonte: conto Betfair)**

| Voce | Cifra | Etichetta/tooltip | Fonte |
|---|---|---|---|
| Esposizione del conto | 9,95 € | «rischio massimo del conto adesso, calcolato da Betfair (tutti i mercati, bot + sito + app) · controllato N s fa» | getAccountFunds (`betfair_live_account.exposure` o topic `account` 47331 con `checked_at`) |
| Disponibile | 30,61 € | «saldo giocabile» | idem |
| Rischio dei bot LIVE | 16,22 € | «perdita massima secondo i bot (per partita, nettata)» | `live.liability` netta dei servizi (Mike `E.event_liability`; Omega/Safe `aggregates.open_liability`; tennis sull'ABBINATO) |
| Scarto conto ↔ bot | −6,27 € → ambra | «il conto non torna con i bot: ordini fuori dai bot o bot non allineati. Guarda: FC Vsetin (2 ordini dal sito)» | differenza delle due righe sopra + elenco partite dallo specchio `betfair_live_orders` (`ext...`) |
| Partite con rischio vero | 1 (Follo 9,80 €) | «+ 2 partite con posizioni pareggiate o chiuse dal sito» | per partita: caso peggiore nettato dallo specchio ordini del conto |

Si TOGLIE la «Esposizione 39,15» lorda (la somma resta calcolata solo come controllo interno, mai a schermo).

**Fascia 2 - BOT (una riga per bot, sempre le stesse colonne)**

| Colonna | Contenuto | Regola |
|---|---|---|
| Bot | Omega · Safe calcio · Safe tennis · Mike · Scalper calcio · Tennis Scalper/Pro/FLB/Swing | tutti, sempre |
| Modo | `LIVE` (rosso pieno) / `PAPER` (blu contorno) / `SPENTO · ultimo modo paper` (grigio) | da `control.mode` anche da spento (scalper compreso); se una partita armata ha modo diverso dal bot: «+1 partita in LIVE» in rosso |
| Stato | in funzione / in pausa / fermo | dal servizio |
| Aggiornato | «N s fa» unico | eta' del dato piu' recente, qualunque tubo. Se il bot e' fermo: «fermo: non invia aggiornamenti» (grigio, normale). Se acceso e muto oltre 3× la sua cadenza: «ACCESO MA MUTO da N s» (rosso) |
| Posizioni LIVE | «1 partita · 2 gambe» | solo LIVE; il paper nella sua colonna |
| Rischio LIVE | € netto del servizio | |
| Oggi LIVE | realizzato dal CONTO (`pnl_reale_oggi.per_fonte`) | «—» solo se il conto non e' stato letto; 0 ordini = «0,00 (nessun ordine regolato)» |
| Oggi PROVA | P&L paper del bot | colonna separata, mai sommata |
| Stop perdita | valore del bot (Safe −50, Mike −50, Omega spento) + matita | apre l'editor ESISTENTE di quel parametro (Safe `risk.daily_loss_stop` in `BotParamsSheet.tsx:174`; Mike `daily_loss_stop` `lib/mike.ts:547`; Omega `daily_loss_cap`) |

Riga in cima, sopra i bot: **«Stop perdita del CONTO: SPENTO»** (oppure «−X € · oggi −Y € · scatta il freno generale») con matita che apre il controllo esistente `LiveControlsPanel.tsx:98/:189` (`betfair_live_settings.daily_loss_limit`, letto da `daily_stop_worker.py:124-137`). Nessun nuovo posto di salvataggio: ogni soglia resta dove e' oggi.

**Fascia 3 - IMPIANTO (compatta, apribile)**

| Oggi | Domani |
|---|---|
| «Runner in streaming · live+paper» | «Runner calcio: legge le quote in tempo reale · ordini veri CONSENTITI dal file di configurazione» (o «solo simulati») |
| «feed rest 6 s» grigio | «Quote dello scanner: RIPIEGO (stream fermo) · 6 s» in **ambra**; «stream · 1 s» verde |
| «canale locale · stato canale · righe ... db 7 s» | una sola riga «Dati: tempo reale» oppure «Dati: lettura ogni 30 s (tempo reale assente per: Omega, Tennis)», dettaglio nel tooltip |

### 1.D Rischio

| Modifica | Cosa puo' rompere | Protezione |
|---|---|---|
| Esposizione conto al posto della lorda | `ControlRoom.test.tsx:858-875` (attende «77,71» e «2 / 59»), `controlRoom.test.ts:536-560`, `:625-653`, `eventGroups.test.ts:115-118` | NON cambiare `totaliGiornata`/`groupCicliByEvent` (usati anche da schede e DayBar): aggiungere campi nuovi al VM e cambiare solo cosa stampa la testata; aggiornare solo il test della testata |
| Rischio dei bot da `open_liability` | nessuno (codice gia' calcolato e non letto, `useControlRoom.ts:3507`) | test nuovo con Mike 9,80+6,42+0 |
| Scarto conto↔bot | serve lo specchio ordini per partita: `get_live_positions_all()` esiste (`migrations/betfair_live_pnl_journal.sql:238`) - da verificare che copra `ext` | solo lettura; nessuna RPC nuova se basta quella |
| Stop per bot + conto | `ControlRoom.test.tsx:213-228` (`cr-freni`), `BotParamsSheet.test.tsx:254-268` (segno) | tenere `cr-freni` come contenitore; editor ESISTENTI; nessuna scrittura nuova |
| Chip bot | `ControlRoom.test.tsx:201-207`, `:233-240`, `:631-654`; `useControlRoom.statoCanale.test.tsx` | cambiare i testi, non `etaPushS`/`fonteDi` |
| Modo scalper da spento | `lib/scalperControlRoom.test.ts`, `PannelloBotScalper.test.tsx` | leggere `servizio.mode` anche con `status != running`, marcato «ultimo modo» |
| Runner | `lib/runnerCanale.test.ts` (18 occorrenze di `LIVE+PAPER`) | cambiare SOLO la traduzione a schermo; il valore del battito resta |

---

## 2. SEZIONE 2 - Obiettivo di oggi

Componenti: `ObiettivoHero.tsx:48-97` monta `components/trading/DayBar.tsx`; accanto `SaldoBetfairCard.tsx`; dati `useControlRoom.ts` + `lib/composizioneObiettivo.ts`.

### 2.A / 2.B

| Testo | Codice | Fonte | Vero? |
|---|---|---|---|
| «giornata operativa 30 settembre» | `DayBar.tsx:110-112`; `ControlRoom.tsx:236`, `:520` | giorno di Roma | vero |
| «obiettivo non ancora storicizzato» | `ControlRoom.tsx:533`; `useControlRoom.ts:3667` | `omega_daily_goal` (scritta solo dal servizio Omega, `omega_db.py:1042`) | vero ma gergo: vuol dire «Omega oggi non ha girato» |
| «P&L netto di commissione da Betfair, tutto il conto» | `ControlRoom.tsx:534-535`; `useControlRoom.ts:2001-2007`, `:3570` | `betfair_live_account.pnl_reale_oggi` (listClearedOrders, `reconcile_worker.py:968-1072`) - scritto SOLO dal runner calcio | fonte vera; ma **con 0 ordini il numero grande NON compare** (`DayBar.tsx:115-120`): la nota annuncia un P&L che a schermo non c'e' |
| «Obiettivo 100,00» | `DayBar.tsx:127`; `useControlRoom.ts:1958` | obiettivo di Omega | vero; e' l'obiettivo di Omega usato per tutto il conto (va detto) |
| «partite 28» | `ControlRoom.tsx:526`; `controlRoom.ts:1094` | righe di `safe_strategy_scan` | vero come «programma dello scanner», non partite operate |
| «operazioni 0 · 0V 0P» | `useControlRoom.ts:3608-3614` | cicli LIVE regolati oggi | vero, ma l'etichetta non dice «regolate» |
| «3 vive» | `DayBar.tsx:138`; `controlRoom.ts:1100` | partite del feed con riga live non regolata | **fuorviante** (vedi §1: 1 sola con rischio) |
| «in corso (stimato) −0,74» | `DayBar.tsx:153-160`; `useControlRoom.ts:3559-3564` | somma per RIGA di `chiusura.bloccabile` (prezzo dello scanner, 5 %) | **parziale**: stima per riga, non per partita; alle 14:09 il servizio dava Follo −0,74 e **Vsetin +0,16** (ma Vsetin e' gia' chiusa dal sito: sul conto «in corso» Vsetin ≈ −0,15). Non entra nella barra quando il realizzato e' nullo (`DayBar.tsx:95`) |
| «Liability aperta 39,15» | `DayBar.tsx:176-181` | stessa somma lorda della testata | **NO** (vedi §0) |
| «0,0 %» | `DayBar.tsx:199-215` | `avanz = null` | vero, ma dovrebbe essere «0,00 su 100,00» esplicito |
| Composizione (Omega —, Safe —, Mike — ...) | `ObiettivoHero.tsx:56-75`; `composizioneObiettivo.ts:104-206` | righe LIVE regolate oggi + conto per tennis/manuali/altro | vero oggi (nulla regolato). **Rischio latente**: `get_mike_state` porta solo righe piazzate oggi o aperte (`migrations/mike_bot_v2.sql:172-183`); `get_safe_state` `LIMIT 200` paper+live (`safe_strategy_paper_live_2026-09-13.sql:441-445`): una posizione di ieri regolata oggi finisce in «Altro sul conto», non sotto il bot |
| «in prova +7,60 — mai sommato» | `ObiettivoHero.tsx:86-97`; `composizioneObiettivo.ts:202-206`; duplicato in `ControlRoom.tsx:570-581` | righe paper per giorno di REGOLAMENTO del bot | **FALSO due volte**: (1) sono 4 partite **Safe del 26/09** regolate oggi al riavvio; (2) **manca Mike paper −18,29** regolato alla stessa ora (righe del 26/09, filtrate da `get_mike_state`): il totale onesto «regolato oggi in prova» sarebbe **−10,69**, e nessuna delle due cifre riguarda l'operativita' di oggi |
| «Saldo conto 30,41 · Esposizione −10,15» | `SaldoBetfairCard.tsx:149-174`; `lib/saldoBetfair.ts:155-170` | getAccountFunds | **vero** |

### 2.C Progetto

Il riquadro parla SOLO di soldi veri della giornata; il paper ha una corsia sua.

**Corsia LIVE (soldi veri)**

| Riga | Cifra | Fonte dichiarata |
|---|---|---|
| Realizzato oggi | **0,00 €** su obiettivo 100,00 (0 ordini regolati) | «conto Betfair, netto commissione, ordini regolati oggi · letto N min fa». Mostrato SEMPRE, anche 0,00 |
| Aperto adesso (se chiudo tutto ora) | somma per PARTITA del cash out del bot (§5), non per riga | «stima ai prezzi attuali · bot» |
| Rischio massimo | 9,95 € | «conto Betfair» (la stessa cifra della testata, una sola) |
| Composizione LIVE per bot | tabella: bot · realizzato oggi (conto, `per_fonte`) · aperto (bot) · partite | Mike: 0,00 / −0,74 Follo · Manuale sito: 0,00 / aperto su Vsetin |
| Avanzamento | (realizzato + aperto) / obiettivo, con la parte «aperto» tratteggiata | |

Etichette: «operazioni regolate oggi», «partite con posizione LIVE: 1 con rischio, 2 pareggiate/chiuse», «programma dello scanner: 28 partite» (in piccolo, fuori dai soldi).

**Corsia PROVA (simulato, mai sommato)**: una riga per bot, con la DATA DELLA PARTITA:

```
IN PROVA (simulato)          oggi      arretrati regolati oggi
Safe calcio   PAPER          0,00      +7,60  (4 partite del 26/09)
Mike          (LIVE ora)     —         -18,29 (2 partite del 26/09)
```

Regola proposta (DA DECIDERE CON L'UTENTE): per il paper «oggi» = partite con calcio d'inizio oggi; le righe regolate oggi di partite di altri giorni vanno in «arretrati», visibili ma separati. Per il LIVE resta il giorno di regolamento di Betfair (e' cio' che muove il saldo).

Da togliere: la seconda riga «in prova» (`ControlRoom.tsx:570-581`), la «Liability aperta» lorda, la nota «tutto il conto» quando non c'e' cifra.

**Estensione del P&L reale del conto a tutti i bot.** Il lavoro citato come `PNL_REALE_DEL_CONTO` non esiste con quel nome; quello che esiste e' `pnl_betfair_reale` (`migrations/pnl_betfair_reale_2026-09-24.sql`, `reconcile_worker.py:539-1089`): `pnl_reale_oggi.per_fonte` ha GIA' le voci `mike, omega, safe_calcio, safe_tennis, scalper, bot_tennis, manuale_app, manuale_sito, altri_bot`, attribuite per `bet_id` delle righe live dei bot (poi `customerOrderRef`, mai `customerStrategyRef`). Progetto:
1. il realizzato LIVE di OGNI bot a schermo = `per_fonte[bot].netto` (una sola fonte per tutti);
2. le righe dei bot servono solo per l'APERTO e per il dettaglio;
3. questo chiude il rischio «posizione di ieri regolata oggi» (il conto la attribuisce comunque al bot, anche se la RPC del bot non la porta);
4. il runner calcio pubblica sul canale `account` anche `pnl_letto_at` a ogni lettura (oggi scrive solo al cambio: la pagina non sa se il dato e' di 1 minuto o di 2 ore).

### 2.D Rischio

| Modifica | Cosa puo' rompere | Protezione |
|---|---|---|
| Realizzato 0,00 sempre visibile | `DayBar.pnlReale.test.tsx`, `ControlRoom.test.tsx:830-898`, `:1091-1120` | la DayBar e' usata anche da Mike/Omega/Safe: parametro nuovo opzionale, default invariato |
| Composizione da `per_fonte` | `composizioneObiettivo.test.ts`, `pnlRealeBetfair.test.ts` | ripiego sulle righe quando il conto non e' letto (esiste gia': `ControlRoom.tsx:536-537`) |
| Paper per giorno partita + arretrati | `fixPagine2609.giornata.test.tsx:67-86` (regola F-2 «per regolamento»), `ObiettivoHero.test.tsx:47` | cambia una regola certificata il 26/09: SERVE il si' dell'utente |
| Mike paper arretrati visibili | richiede che `get_mike_state` porti anche le righe `settled_at` oggi: **migrazione SQL** (la applica l'utente) | alternativa senza migrazione: leggere `get_mike_trades` per data di regolamento se esiste gia' il filtro (da verificare) |
| Aperto per partita | `useControlRoom.test.tsx` (inCorso) | calcolo nuovo accanto al vecchio, poi sostituzione |

---

## 3. SEZIONE 3 - Schede sport (SplitSport)

### 3.A / 3.B

| Testo | Codice | Fonte | Vero? |
|---|---|---|---|
| «Calcio MODALITA' PAPER» | `SplitSport.tsx:126-134`; `modalitaPerSport` `ControlRoom.tsx:798-824` (`:822`) | guarda SOLO Safe (varianti base/esatto/punta) | **FALSO**: Mike e' LIVE con soldi veri sul calcio |
| «3 aperte» (rosso) | `SplitSport.tsx:137-141`; `apertePerSport` `ControlRoom.tsx:828-841` | partite con riga LIVE non regolata | contraddice il badge PAPER nella stessa tessera; conta Farul e Vsetin |
| «+7,60 · 4 operazioni 4V 0P 100 %» | `SplitSport.tsx:96-104`, `:151-176`; `perSportPaper` `useControlRoom.ts:3522-3533`; `perSportGiornata` `controlRoom.ts:1008-1039` | paper per giorno di regolamento | **FUORVIANTE**: Safe paper del 26/09; senza Mike paper −18,29; il LIVE (Mike) e' nascosto perche' la tessera e' «paper» |
| «Tennis MODALITA' PAPER +0,00» | idem, `:820` | solo Safe tennis | vero solo per Safe tennis; i 4 bot tennis non contano |

### 3.C Progetto

Ogni tessera sport = **due corsie fisse, LIVE sopra e PROVA sotto**, mai una sola «modalita' dello sport»:

```
CALCIO
 LIVE   Mike                       realizzato oggi 0,00 (conto) · aperto -0,74 · 1 partita a rischio
 PROVA  Safe calcio · Omega        oggi 0,00 · arretrati +7,60 (26/09)
        Scalper calcio SPENTO
TENNIS
 LIVE   nessun bot
 PROVA  Safe tennis · Scalper · Pro · FLB · Swing   oggi +0,00
```

La lista dei bot per corsia viene da `control.mode` di TUTTI i bot dello sport (Omega, Safe varianti, Mike, scalper calcio; Safe tennis + 4 bot tennis). Con un solo bot LIVE, la tessera ha il bordo rosso «SOLDI VERI».

### 3.D Rischio

`modalitaPerSport` e' usata solo da SplitSport (da verificare con grep prima del lavoro); test da aggiornare: `ControlRoom.test.tsx:917-941`, `fixPagine2609.giornata.test.tsx:123-150`. Test nuovo obbligatorio: Mike LIVE + Safe paper → corsia LIVE con Mike (oggi non esiste nessun test di questo caso).

---

## 4. SEZIONE 4 - Scheda pre-match

### 4.A / 4.B

| Testo | Codice | Fonte | Vero? |
|---|---|---|---|
| «1 40,00/50,00 · X 15,00/18,00 · 2 1,08/1,10» | `SchedaPreMatch.tsx:96-121` (`cr-pre-quote`) | `p.odds` = `safe_strategy_scan.payload.odds` (scanner Safe, stream o REST: `safe_strategy/service.py:1127-1196`) + canale 47336 | cifre vere (miglior punta / miglior banca); **poco leggibili**: 10 px, `text-white/55`, nessun colore punta/banca, eta' solo se c'e' `odds_ts_ms` ed e' l'eta' dell'ULTIMO CAMBIO, non della lettura; nessun volume; spread 40/50 (mercato illiquido) non segnalato |
| Ordini pre-match | `ControlRoom.tsx:1289-1294` non passa `operazioni` a `SchedaPreMatch` | | **una posizione pre-match non si vede nella scheda pre-match** (es. Mike entra 1 h prima del fischio) |
| Nome partita | `nomePartita` `lib/controlRoom.ts:321-328` (`event_name` Betfair); diviso in due righe da `dividiNomi` (`AzioniPartita.tsx:228-232`) con loghi API-Football | stessa fonte del live | nome vero; i loghi possono non corrispondere (arricchimento Omega) |

### 4.C Progetto - «Tabellone quote» unico (pre-match, live, posizioni aperte)

Componente condiviso `TabelloneQuote` (nuovo, solo presentazione):

```
 1X2          PUNTA   BANCA   abbinato
 Seychelles   40,00   50,00   ·  spread 10 tick (poco liquido)
 Pareggio     15,00   18,00
 Sri Lanka     1,08    1,10
 Linee O/U    Under 3,5  1,30 / 1,32   Under 4,5 ...   (solo le linee dove un bot ha o puo' avere posizione)
 prezzi: stream · aggiornati 0,4 s fa        (ambra oltre 5 s, rosso oltre 30 s, «RIPIEGO REST» se lo scanner e' in REST)
```

- PUNTA su fondo azzurro, BANCA su fondo rosa (convenzione Betfair), 13-14 px tabulari.
- Eta' = eta' della LETTURA del book (non dell'ultimo cambio), sorgente dichiarata (stream / ladder al ms / REST).
- Linee O/U dal ladder al ms (`usePrezzoAlMs`) quando esistono `market_id`/`selection_id`; altrimenti da `live.books` del bot con la sua eta'.
- Spread oltre N tick = scritta «poco liquido».
- La scheda pre-match riceve le `operazioni` (una riga di codice in `ControlRoom.tsx:1289-1294`) e le mostra con lo stesso dettaglio del live.

### 4.D Rischio

`SchedaPreMatch.test.tsx`, `SchedaPartita.test.tsx` (testi `cr-pre-quote`, `cr-calcio-vivo-quote`): mantenere i `data-testid`. Passare `operazioni` al pre-match cambia il commento-contratto `ControlRoom.tsx:22-25`: va scritto il perche'.

---

## 5. SEZIONE 5 - Scheda live (Follo v Sarpsborg)

### 5.A / 5.B

| Testo | Codice | Fonte | Vero? |
|---|---|---|---|
| «Cash out globale della partita: nessuna posizione viva del bot su questa partita» | `CashOutPartita.tsx:170-174`; `lib/chiusuraUtente.ts:195`; conteggio `SchedaPartita.tsx:270-272` (`o.bot === 'safe'`) | pulsante che accoda `safe_request('cashout_event')` (`lib/safeBot.ts:1241-1243`) eseguito SOLO dal servizio Safe (`bot_service.py:3473`) | **FALSO letto dal trader**: e' «nessuna posizione di SAFE». Con 2 gambe vive di Mike il «cash out globale» non calcola ne' chiude nulla di Mike |
| «target 4,17 EUR *» | `SchedaPartita.tsx:402-408`; `targetPartita` `lib/controlRoom.ts:436-457` | ripiego della pagina: (obiettivo − realizzato live) / partite del feed non chiuse (calcio + tennis) | **stima aritmetica uguale su tutte le schede**, non il target della partita; l'asterisco lo dice solo nel tooltip |
| «resp. 9,80 EUR» | `SchedaPartita.tsx:457-462`; `soldiPerPartita` | somma lorda `liability` delle righe | vero oggi (4 gol esatti = −9,80); sovrastima in generale (Farul: 14,31 su una posizione pareggiata) |
| «chiudi ora 2,56 −0,32» / «chiudi ora 1,63 −0,50» | `DettaglioRigaView.tsx:277-347`; `useChiusuraAlMs.ts:52-86`; `chiusuraViva` `useControlRoom.ts:2559-2608`; `partialLockedPnl` `CashOutButton.tsx:34-74` | prezzo dal ladder al ms (canale o DB) oppure dallo scanner | **veri** (ricalcolati: −0,32 e −0,50). Difetto: ramo al ms **LORDO** di commissione (`lib/chiusuraAlMs.ts:64-74`), ramo scanner NETTO (`useControlRoom.ts:2594-2596`): in utile due numeri diversi per la stessa gamba |
| «cash out −0,84» | `SchedaMike.tsx:210-223` ← `live.cashout.net` di Mike (`engine.py:933-1005`, `:4140-4148`) | book della fotografia del servizio | vero per il servizio; −0,82 la somma per gamba: differenza di ISTANTE del book (e di fonte). Due cifre diverse per la stessa cosa, senza eta' affiancata |
| «ERRORE green-up» ×2 | `DettaglioRigaView.tsx:178-206`; `STATUS_META.error` `lib/tradeStatus.ts:76`; righe `closes_trade_id` `useControlRoom.ts:494-516` | `mike_trades` 5086 (`reconciled_not_placed`), 5093 (`cancelled_by_engine`, `esito_ordine=ritirato_da_noi`) | **FUORVIANTE**: non sono errori ne' rifiuti di Betfair: sono due banche di green-up NON ABBINATE e RITIRATE da Mike (0 € abbinati) |
| «FALLITA: posizione ANCORA APERTA 0 % abbinato» | `StrisciaEsitoChiusura.tsx:36`, `:112-114`; `certezzaChiusura.ts:185-207` | | vero (la punta Under 3,5 e' aperta), ma «0 %» e' della CHIUSURA; non dice che la posizione e' ora coperta dalla banca Under 4,5 |
| Nome «Seychelles v Sri Lanka» | live: `p.nome` grezzo (`SchedaPartita.tsx:300`); pre-match: `dividiNomi` a due righe con loghi; posizioni/orfane: `t.event_name` della riga del bot (`useControlRoom.ts:2650`, `:2670`, `:2692`, `:2719`, `:2754`) | due fonti (scanner e riga del bot) e tre impaginazioni | nome vero, **presentazione diversa**: stessa partita scritta in tre modi |

### 5.C Progetto - scheda live «da trader»

1. **Testata unica** (pre-match, live, posizioni): una funzione `nomeCanonico(eventId)` → `event_name` Betfair dallo scanner; se la partita non e' nel feed, `event_name` della riga del bot normalizzato con le stesse regole (porting di `Betfair/betfair_match.py:72` `normalize_name` / `:93` `split_event_name`). Sempre «Casa v Ospite» su una riga + competizione + minuto/punteggio/eta' del punteggio. Loghi solo se l'abbinamento con API-Football e' certo.
2. **Tabellone quote** di §4, con le linee O/U delle posizioni (qui Under 3,5 e Under 4,5, non l'Over 4,5 che oggi mostra SchedaMike).
3. **Cash out globale della partita = somma ESATTA di tutte le gambe vive di TUTTI i bot LIVE su quella partita**, calcolata come fa `engine.cashout_value` (`engine.py:933-1005`): esposizione raggruppata per (mercato, selezione) - non per riga -, green al best corrente del lato opposto, commissione per MERCATO sul netto positivo. Porting in una funzione pura `lib/cashOutPartita.ts`, stessa matematica di `compute_greenup` (`Betfair/stream/trading/greenup.py:118`) gia' rispecchiata in `CashOutButton.tsx:34-84`. A schermo:

```
CASH OUT DELLA PARTITA (se chiudo TUTTO adesso)        -0,82 €   netto commissione
  Mike LIVE  punta Under 3,5  5,00 @ 2,40   chiudo banca 4,69 @ 2,56   -0,32
  Mike LIVE  banca Under 4,5  6,32 @ 1,76   chiudo punta 6,82 @ 1,63   -0,50
  prezzi: ladder al ms · 0,3 s fa                 il bot calcola: -0,84 (book di 1,2 s fa)
  perdita massima se non chiudo: -9,80 € (4 gol esatti) · vincita massima: +2,20 €
```

   - Se una gamba non ha prezzo: «NON CALCOLABILE: manca il prezzo di Under 4,5» e nessuna cifra (regola A9 dell'audit, estesa a tutti i bot).
   - Se ci sono gambe PAPER di un altro bot sulla stessa partita: riga separata «PROVA» sotto, mai sommata.
   - Se sul conto ci sono ordini fuori dai bot (specchio `ext...`): riga «Sito/app» nella scomposizione, con avviso «il bot non li vede».
   - Il PULSANTE resta quello di oggi, con testo vero: «Cash out Safe (solo le posizioni di Safe)»; il pulsante per bot (Mike: `MikeCashOutButton`) resta nella sua riga. Un pulsante «chiudi TUTTI i bot su questa partita» e' un comportamento nuovo: solo su richiesta esplicita dell'utente (blocco B13).
4. **target**: togliere dalla scheda (e' una media, non un fatto della partita) oppure scriverlo «quota media dell'obiettivo per partita: 4,17 € (stima della pagina)». Proposta: toglierlo.
5. **resp.** → «perdita massima se non chiudo» dal servizio (netta, per scenario) e, se diverso, «sul conto: X» dallo specchio ordini.
6. **Tentativi di chiusura**: raggruppati, con l'esito vero da `meta.esito_ordine`/`meta.reason`:

```
green-up: 2 tentativi, 0,00 € abbinati - ritirati da Mike (non da Betfair)      [dettaglio]
posizione: punta Under 3,5 5,00 ancora APERTA, protetta dalla banca Under 4,5
```

   Etichette: `ritirato_da_noi` → «RITIRATO dal bot»; `reconciled_not_placed` → «NON PIAZZATO (verificato sul conto)»; rifiuto Betfair → «RIFIUTATO da Betfair: <codice>». «ERRORE» solo per un errore vero. Vale per tutti i bot (la funzione e' `statusMetaOf`, comune).
7. **«chiudi ora» sempre NETTO** di commissione in entrambi i rami (`chiusuraAlPrezzo` applica `netAfterCommission`), con l'eta' del prezzo accanto.

### 5.D Rischio

| Modifica | Cosa puo' rompere | Protezione |
|---|---|---|
| `cashOutPartita` pura | niente (nuova) | test tabellari con i casi di oggi (Follo −0,82; Vsetin con ordini del sito; Farul pareggiata ≈ 0) e parita' numerica con `engine.cashout_value` su 3 casi presi dai test Python (`test_mike_engine.py`) |
| Testo «nessuna posizione viva» | `ControlRoom.test.tsx:1340-1347`, `chiusuraUtente.test.ts:143-147` | cambiare il testo nel solo ramo «altri bot vivi» |
| Etichette esito | `tradeStatus.test.ts`, `StrisciaEsitoChiusura.test.tsx`, `DettaglioRigaView.test.tsx`, Omega/Safe cert (`certification/*.cert.test.tsx`) | aggiungere esiti nuovi senza cambiare il significato di `error` per Omega/Safe |
| «chiudi ora» netto | `chiusuraAlMs.test.ts`, `ResiduiB17.schede.test.tsx` | cambia i numeri in UTILE (−5 % del positivo): test nuovo che fallisce oggi |
| Nome canonico | test che cercano i nomi con trattino lungo (`home – away`) | ripiego invariato |

---

## 6. SEZIONE 6 - Posizioni aperte

### 6.A / 6.B

Componente `AperteTab` (`pages/ControlRoom.tsx:1330-1424`) su `vm.posizioni` (`useControlRoom.ts:2637-2771`): aperture Omega/Safe/Mike non regolate (gambe di chiusura escluse), ordini dei 4 bot tennis (`chiusura: null` → nessun «chiudi ora», selezione nulla), sessioni scalper. Raggruppate per `eventId`: `SchedaPartita` se la partita e' nel feed, altrimenti `RigaPosizioneOrfana` (`:1430-1528`).

| Cosa | Vero? |
|---|---|
| Contatore della linguetta (`ControlRoom.tsx:707-708`) | somma paper + live |
| Farul (pareggiata) e Vsetin (chiusa dal sito) elencate come posizioni aperte | vere come righe, **false come rischio** |
| Ordini del sito su Vsetin (`ext...`) | **invisibili**: nessuna scheda li mostra; il trader vede solo la «credenza» di Mike |
| Orfane: «chiudi ora» sulla sola gamba | ignora green e copertura (A8 dell'audit) |
| Tennis: nessun «chiudi ora», nessun nome selezione | incompleto |
| Badge live/paper per riga, banner «N posizioni con soldi veri» | vero, da conservare |

### 6.C Progetto

- Due elenchi: **LIVE** (in alto, contatore rosso) e **PROVA** (sotto, contatore blu). Mai un contatore unico.
- Ogni partita usa la STESSA scheda di §5 (testata, tabellone, cash out della partita con scomposizione): le orfane diventano schede ridotte con gli stessi campi, non un'altra grafica.
- Per ogni partita LIVE, una riga di **verifica col conto**: «Conto Betfair: rischio 0,15 € · Mike crede: 6,42 € → NON ALLINEATI (2 ordini dal sito)». Fonte: specchio `betfair_live_orders` (include gli ordini esterni, scritti da `reconcile_worker.py` ramo b).
- Stato per partita, una parola: `A RISCHIO` (caso peggiore < 0) / `PAREGGIATA` (green: caso peggiore ≥ −0,05) / `CHIUSA DAL SITO` / `DA REGOLARE`.
- Tennis: nome selezione e «chiudi ora» col ladder al ms quando c'e' `market_id`/`selection_id`; altrimenti «non calcolabile».

### 6.D Rischio

Il conteggio posizioni e' condiviso con Omega/Safe (A8): cambiare solo presentazione e aggiungere campi. La verifica col conto richiede che la RPC dello specchio restituisca gli `ext` per evento: `get_live_positions_event(p_event_id)` esiste (`betfair_live_pnl_journal.sql:258`), da verificare che copra `source='account'` - se no, **migrazione** (la applica l'utente). Test: `useControlRoom*.test.tsx`, `ControlRoom.test.tsx` sezione aperte.

---

## 7. ORDINE DEI BLOCCHI DI LAVORO (chirurgici, indipendenti)

Regole comuni a ogni blocco: niente cambi di strategia ne' di servizi Python salvo dove scritto; nessuna modifica a `totaliGiornata`/`groupCicliByEvent`/`statusMetaOf` che cambi il significato per altri componenti (si aggiungono campi); ogni test nuovo falsificato (deve diventare rosso tornando al codice di oggi); `npx tsc -p tsconfig.app.json --noEmit` a 0 errori; `npx vitest run` sui file toccati; `npm run build`; prova a schermo con l'app dell'utente.

| # | Titolo | File | Test da scrivere | Prova a schermo attesa | Rischio |
|---|---|---|---|---|---|
| B1 | Grammatica comune: marchio fonte/modo | nuovo `lib/fonteSoldi.ts` + `components/controlroom/MarchioSoldi.tsx` (CONTO / BOT / PROVA, LIVE / PAPER / SPENTO, «N s fa») | unita': ogni combinazione; un importo PROVA non si somma mai (tipo TS distinto) | nessun cambio visibile (solo mattoni) | nullo |
| B2 | Tessere sport a due corsie LIVE/PROVA con TUTTI i bot | `pages/ControlRoom.tsx:798-841`, `SplitSport.tsx` | Mike LIVE + Safe paper → corsia LIVE «Mike», corsia PROVA «Safe, Omega»; scalper spento elencato | Calcio: «LIVE Mike · 1 partita a rischio», il +7,60 in PROVA come arretrato | basso |
| B3 | Esposizione della testata = conto + rischio bot + scarto | `ControlRoom.tsx:958-970`, `useControlRoom.ts` (esporre `soldiGiornata.liability` gia' calcolata e l'account) | 39,15 lorda non compare; 9,95 conto, 16,22 bot, scarto con la partita elencata; conto non letto → «conto non letto da N s» senza cifra | «Esposizione del conto 9,95 € · bot 16,22 € · NON TORNA: FC Vsetin» | medio (test testata `:858-875`) |
| B4 | Stop perdita per bot + conto, con matita agli editor esistenti | `Freni` `ControlRoom.tsx:1086-1100`, `useControlRoom.ts:3674` | Safe −50 etichettato «Safe (paper)», Mike −50, Omega spento, conto SPENTO da `betfair_live_risk_state`; la matita apre l'editor giusto | «Stop conto: SPENTO ✎ · Safe −50 ✎ · Mike −50 ✎ · Omega spento ✎» | basso (nessuna scrittura nuova) |
| B5 | Chip bot e impianto in parole da trader | `ControlRoom.tsx:1038-1169`, `lib/scalperControlRoom.ts:363` | «fermo: non invia» vs «ACCESO MA MUTO»; scalper «SPENTO · ultimo modo paper»; feed REST ambra; runner «ordini veri consentiti» | niente «senza spinta», niente «modalita' ignota», niente «live+paper» | medio (molti test di testo, nessuna logica) |
| B6 | Obiettivo: realizzato sempre visibile, aperto per partita, via la liability lorda | `DayBar.tsx` (parametro opzionale), `ObiettivoHero.tsx`, `ControlRoom.tsx:518-581` | 0 ordini → «0,00 €, nessun ordine regolato oggi · letto N min fa»; aperto = somma dei cash out per partita | «Realizzato 0,00 / 100,00 · aperto −0,74 · rischio 9,95 (conto)» | medio (DayBar condivisa: default invariato) |
| B7 | Composizione LIVE per bot dal conto (`per_fonte`) | `composizioneObiettivo.ts`, `useControlRoom.ts:2031-2127` | una riga Mike di ieri regolata oggi finisce sotto Mike, non in «Altro» | colonne realizzato/aperto per bot | medio |
| B8 | Corsia PROVA completa e con data partita | `composizioneObiettivo.ts:202-206`, `ObiettivoHero.tsx:86-97`; **migrazione** per `get_mike_state` (righe paper regolate oggi) se serve | Safe +7,60 e Mike −18,29 entrambi in «arretrati del 26/09»; «oggi» 0,00 | «IN PROVA oggi 0,00 · arretrati regolati oggi: Safe +7,60, Mike −18,29» | medio-alto: cambia la regola F-2 del 26/09 → **decisione dell'utente** prima |
| B9 | Testata partita + tabellone quote unico | nuovo `TabelloneQuote.tsx`, `SchedaPreMatch.tsx:96-121`, `SchedaPartita.tsx:300-376`, `nomePartita` | stesso nome in pre-match/live/posizioni; punta/banca colorate; eta' della lettura; spread «poco liquido» | quote grandi, azzurro/rosa, «0,4 s fa» | basso (presentazione; `data-testid` conservati) |
| B10 | Operazioni pre-match nella scheda pre-match | `ControlRoom.tsx:1289-1294` | una punta Mike pre-match compare nella scheda pre-match | la gamba pre-fischio e' visibile | basso |
| B11 | «chiudi ora» sempre netto + eta' del prezzo | `lib/chiusuraAlMs.ts:64-74` | stessa gamba in utile: ramo ms = ramo scanner (oggi rosso) | cifre in utile −5 % sul positivo | basso |
| B12 | Cash out della partita esatto, multi-bot, con scomposizione | nuovo `lib/cashOutPartita.ts`, `CashOutPartita.tsx`, `SchedaPartita.tsx:270-272`, `:389-408`, `:457-462`; `lib/chiusuraUtente.ts:195` | Follo −0,82 con due gambe; gamba senza prezzo → «non calcolabile»; paper mai sommato; parita' con `engine.cashout_value`; target tolto | il riquadro di §5.C; il pulsante dice «Cash out Safe (solo Safe)» | medio (matematica nuova, solo lettura) |
| B13 | Esiti dei tentativi di chiusura raggruppati e veri | `DettaglioRigaView.tsx:164-206`, `lib/tradeStatus.ts` (esiti nuovi), `StrisciaEsitoChiusura.tsx` | 5086/5093 → «2 tentativi, 0 abbinato, RITIRATI dal bot»; rifiuto vero → «RIFIUTATO da Betfair: codice» | niente «ERRORE green-up» doppio | medio (tocca Omega/Safe: esiti aggiunti, non cambiati) |
| B14 | Ordini fuori dai bot + verifica conto↔bot per partita | `useControlRoom.ts` (specchio per evento), `AperteTab`, `SchedaPartita`; eventualmente **migrazione** se la RPC non porta gli `ext` | Vsetin: «Conto 0,15 · Mike crede 6,42 · 2 ordini dal sito» | la divergenza di oggi e' visibile in rosso | medio |
| B15 | Posizioni aperte: LIVE e PROVA separati, stato per partita | `AperteTab` `ControlRoom.tsx:1330-1528` | contatori separati; Farul «PAREGGIATA», Follo «A RISCHIO» | due elenchi | basso |
| B16 | (SOLO SU RICHIESTA) pulsante «chiudi TUTTI i bot su questa partita» | `CashOutPartita.tsx` + richieste ai servizi esistenti | doppia conferma LIVE, una richiesta per bot, esito per bot | | alto: comportamento nuovo, serve il si' dell'utente |

Ordine consigliato: B1 → B2 → B3 → B4 → B5 (la testata e le tessere: il danno piu' grave di oggi, nessuna matematica nuova) → B11 → B12 → B13 → B14 (le schede) → B9 → B10 → B15 → B6 → B7 → B8 (dopo la decisione sul paper) → B16 (solo se richiesto). Ogni blocco si prova da solo; nessuno dipende da un altro salvo B1 (mattoni) e B12 prima di B6 (l'«aperto» per partita).

---

## 8. COSE GIUSTE DA NON TOCCARE

1. `SaldoBetfairCard` e la catena getAccountFunds (`reconcile_worker.py:138-179`, `saldo_evento.py`): una lettura sola, cadenza 20 s + dopo ogni ordine, pubblicazione sul canale a ogni lettura. E' la verita' del conto: va solo messa in evidenza.
2. `pnl_betfair_reale`: attribuzione per `bet_id`, poi `customerOrderRef`, MAI `customerStrategyRef`; commissione ripartita per mercato; giornata di Roma; paper mai toccato (`test_pnl_betfair_reale_2026_09_24.py`).
3. `engine.cashout_value` di Mike (raggruppa per selezione, commissione per mercato, `complete=false` se manca un prezzo): e' il modello del cash out della partita.
4. I due «chiudi ora» per gamba: matematica giusta (verificata a mano: −0,32 e −0,50).
5. Striscia `certezzaChiusura` «ANCORA APERTA»: vera; si aggiunge il contesto, non si toglie.
6. Separazione live/paper gia' presente: badge per riga, banner «N posizioni con soldi veri», resp. live separata da «prova» (`SchedaPartita.tsx:410-470`), `realizzatoGiornata` live/paper separati.
7. Eta' delle quote che ticka e pulsanti di soldi spenti su dato vecchio/ignoto (audit, §4.1).
8. Stop di Safe applicato davvero (`risk.py:188-202`) e separato per modalita'; `_NEVER_PERSIST` del servizio.
9. Nota «conto Betfair non letto: P&L dalle righe dei bot» (`ControlRoom.tsx:536-537`): ripiego onesto.
10. Tutto l'elenco «cose giuste» di `AUDIT_UI_VERIDICITA.md` §4.

---

## 9. COSA NON HO POTUTO VERIFICARE

- **Non ho visto l'app a schermo**: testi troncati, tooltip, sovrapposizioni e dimensioni reali sono letti dal sorgente.
- **39,15 esatto**: alle 14:17 UTC la somma lorda era 37,04; la differenza di 2,11 con la tua schermata dipende da righe che hanno cambiato stato nel frattempo (non ricostruita).
- **−0,84 contro −0,82**: attribuito alla differenza d'istante fra il book del servizio e il ladder al ms; non riprodotto al centesimo.
- **Ordini del sito su Vsetin**: il fatto che siano dell'utente (e non di un altro processo) lo deduco da `client_order_ref = ext...` (= ordini trovati sul conto e non piazzati dai nostri processi). Non ho verificato se Mike li ha visti (il diario ha una riga `posizione_di_conto`, citata nell'audit): se Mike NON li vede, un suo cash out su Vsetin riaprirebbe esposizione. **Da controllare subito, e' un rischio di soldi, non di UI.**
- Se `get_live_positions_all()` / `get_live_positions_event()` restituiscono anche gli ordini `source='account'` (serve per B3/B14 senza migrazione).
- Se `get_mike_trades` puo' gia' filtrare per giorno di regolamento (serve per B8 senza migrazione).
- Omega paper regolato oggi: non letto (colonna `created_at` assente in `omega_trades`, non ho insistito).
- Eta' reale di `pnl_reale_oggi`: `letto_at` 12:41 UTC, ma la scrittura avviene solo al cambio; non so se il runner lo ha riletto dopo.
- Che `modalitaPerSport` sia usata solo da SplitSport (grep da fare prima di B2).
- Non ho eseguito test ne' build: referto di sola lettura del codice e del DB.
