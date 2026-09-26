# ADMIN26 — E2E FASE 2: auto-mode scalper/tennis e checklist Safe (§7.6, §7.7, §7.9.6, §7.9.7)

Delegato di verifica in SOLA LETTURA, 26/09/2026. Consegna **PARZIALE**. Finestra osservata dal vivo:
**09:18–10:56 UTC** (canali + DB), più una fotografia DB alle **14:40 UTC**. Dalle 10:57 UTC la rete è
caduta (DNS, `getaddrinfo failed`, visibile in `automode_safe/armate_*.jsonl`). I due processi di sonda in
sottofondo sono stati poi **fermati da Claude Code per memoria di sistema scarsa**: su indicazione dello
strumento NON li ho rilanciati. Alle 14:41 UTC la rete è caduta di nuovo (timeout/DNS verso Supabase): le
verifiche successive usano solo i file già registrati.

Nessuna scrittura sul DB, nessun comando sui canali (collegamento come `/lettore/<topic>`), nessun file
del repo toccato tranne questo referto e i miei `sonda_automode_*.py`. Nota di forma: gli output delle sonde
sono finiti in `automode_safe/` e in `automode_safe_ascolto_stdout.txt`, cioè file senza prefisso `sonda_`
(sono dati, non script). Il grezzo del feed (`scan_raw_*.jsonl.gz`) è nella mia scratchpad, fuori dal repo.

## Sonde (riproducibili, `.venv\Scripts\python.exe`, dalla cartella `AUDIT_2026-09-25/e2e_fase2`)

| script | cosa fa |
|---|---|
| `sonda_automode_db.py "<tabella?select=..&limit=N>"` | GET PostgREST, select e limit obbligatori |
| `sonda_automode_ascolto.py <min>` | lettore 47335/47336/47337/47338; fa girare un **`SafeEngine` di produzione importato** sulle righe del 47336 ogni 2 s, con i params veri |
| `sonda_automode_armate.py <min> <s>` | ogni 30 s: feed (con la STESSA proiezione di scalper e ponte tennis), control, follow, `tennis_live_now`; insieme atteso ricalcolato con `scalper/auto_mode.py`, `tennis_live/auto_mode.py`, `chiusura_manuale.chiusi_dall_utente` |
| `sonda_automode_analisi.py` | cronologia e divergenze da `armate_*.jsonl` |
| `sonda_automode_safe_checklist.py <dal_utc>` | per ogni ingresso/scarto Safe prende la riga del feed dello stesso istante (`updated_at = meta.tempi.t1_feed_ms`) e ricalcola con `engine.evaluate_*`, `veto_campionati.*`, `selezione.conta_scontri_diretti` (h2h letto da `fixture_predictions`), `engine.tennis_sfavorito_estremo_check`, `bot_service.prices_from_row` + `exits.spread_ratio` |

## Tabella degli esiti

| id | esito | sintesi |
|---|---|---|
| 7.6.2 | NON CERTIFICATO | serve una chiamata alla RPC (`scalper_auto_activate('live')`): è un'azione, fuori dalla sola lettura |
| 7.6.4 | NON CERTIFICATO (parziale) | la vita in uso è 7800 s (sniper acceso di default, `auto_mode.py:154-184`): nessuna sessione è stata armata oltre KO+vita (`auto_oltre_vita` sempre vuoto). La partita oltre la vita però non si è mai presentata nel feed: il filtro non è stato messo alla prova |
| 7.6.5 | PASS (con nota) / NON CERTIFICATO sulla parte «manuali» | le sessioni auto si fermano dopo l'uscita dal feed; misurato 83-90 s dall'ultima riga contro i ~60-75 s dichiarati. Oggi nessuna sessione manuale: la parte «manuali non toccate» non è verificata |
| 7.6.6 | NON CERTIFICATO | richiede di spegnere e riaccendere (gesto dell'utente) |
| 7.6.8 | PASS nella finestra | `mode=paper` sempre; 7/7 righe `origine='auto'` di oggi con `dry_run=true` (09:18-10:56 e 14:40 UTC) |
| Fatto «freno» (dal coordinatore) | **CONFERMATO, REPERTO** | l'auto-mode arma righe nuove a freno tirato e il `motivo_blocco` resta vuoto; nessun processo e nessun ordine finché il freno è tirato (§A) |
| Fatto «residuo sniper orfano» | CONFERMATO in parte | il residuo esiste (0,085 € di sbilancio), ma è ACCETTATO dal codice, non orfano. «NON flat dopo 30s» è confermato. Gli ordini lasciati vivi non sono verificabili (§A) |
| 7.7.4 | NON CERTIFICATO | nessuna condizione d'uscita discrezionale né di protezione si è verificata: FLB salito di 1 tick contro gli 8 richiesti; le 2 entrate swing sono scadute senza fill |
| 7.7.8 | **FAIL** | una partita tennis automatica finita non viene mai chiusa: `tennis_live_now.status` non arriva mai a `CLOSED` (§B) |
| 7.9.6.B | PASS sulle partite nel feed / **FAIL** sul tetto | le armate nel feed coincidono con le idonee, nello stesso ordine, dentro il tetto. Ma col tennis le partite finite si accumulano: 12 armate per bot contro un tetto di 5 (stessa causa di §B) |
| 7.9.6.E1 | scalper PASS · tennis **FAIL** | scalper: stop pulito dopo l'uscita dal feed. Tennis: le righe restano `running` per ore su un mercato chiuso (§B) |
| 7.9.6.E2 | NON CERTIFICATO | lo scanner non è mai stato fermo: età massima del battito 12,4 s su 110 giri, soglia 30 s |
| 7.9.6.E3 | referti riconciliati · dinamica NON CERTIFICATA | `iscrizione_a_caldo.py` è su master (commit `9ed1bbe`, `tennis_runner.py:79,489,1786`, interruttore acceso di serie `iscrizione_a_caldo.py:60,80`): `AUTO_FOLLOW_TUTTI_I_BOT.md` §6 è superato. Il caso «posizione viva + partita nuova» non si è verificato: la posizione FLB è stata regolata alle 09:25:02, la partita nuova è stata armata alle 09:25:16 |
| 7.9.7.C | PASS sui candidati osservati (4 ingressi, 127 scarti, 19+ partite) | nessuna divergenza (§C) |

## A. Scalper: auto-mode contro il freno R3 (fatti segnalati dal coordinatore)

Sequenza dal DB (`scalper_control`, `scalper_activity`, `betfair_live_settings`) e da `armate_*.jsonl`:
- **09:41:59.955Z** `betfair_live_settings.kill_switch=true` (il freno viene tirato).
- **09:42:02** le due sessioni vive (36090788, 36090854) scrivono `stop richiesto: force-flat` con
  `freno: db_kill_switch_attivo`. **09:42:32** entrambe scrivono `error "stop: posizione NON flat dopo 30s"`
  (`scalper_session.py:1318-1321`). **09:42:34-35** passano a `stopped`.
- **09:42:42.658Z**, ancora a freno tirato, l'auto-mode scrive 2 righe NUOVE `requested`
  `origine='auto'` `dry_run=true` su 36090936 e 36090937, con attività `auto_armata` alle 09:42:44.
  In `stats.auto` (giro delle 09:42:57): `sessioni: 2`, **`motivo_blocco: null`**.
- Le due righe restano `requested` e senza processo fino al rilascio del freno (09:56:28Z). I processi
  partono alle **09:56:37** (`started_at`).

**Causa nel codice.** Nel ciclo del supervisore `giro_auto` gira PRIMA della lettura del freno
(`scalper_service.py:745` contro `:750`). La condizione di armamento (`:430`) guarda solo la guardia
d'avvio, il conflitto, il tetto e i posti liberi, mai il freno. Il freno blocca solo l'avvio del processo
(`sessione_da_avviare`, `:622-627`, usata a `:757`). `motivo_blocco` (`auto_mode.py:371-398`) non conosce
il freno: con 2 righe `requested` conta 2 sessioni e restituisce None.

**Conseguenze osservate:**
1. A freno tirato la Control Room non dice perché la sessione non parte, e mostra «sessioni 2».
2. Le due partite fermate DAL FRENO (36090788, 36090854) diventano «chiuse a mano»: righe `stopped` più
   recenti dell'accensione corrente (`auto_mode.py:271-276`). Dopo il rilascio non vengono più riarmate
   (nei giri dopo il rilascio non compaiono né fra le armate né fra le armabili).
3. Nessun ordine e nessun processo in quella finestra: da questo lato la barriera R3 tiene.

Non è money-critical in paper. È un reperto di trasparenza e di semantica, da portare all'utente senza
correzione.

**Residuo sniper.** Alle 09:42:02, su 36090854, `sniper_flat_residual {nl:0.5, nw:0.585, locked:0.0}`.
Lo sbilancio |nw−nl| è di 0,085 €. Il codice lo ACCETTA come micro-residuo quando è ≤ 0,30 e non restano
ordini vivi (`sniper_bot.py:649-662`): per costruzione non è «orfano». La sessione però dichiara «NON flat
dopo 30s» per entrambe le partite, e le righe finiscono `stopped` con `error=null`: il campo `error` non
riporta la dichiarazione di `_dichiarazione_non_flat` (`scalper_session.py:255-269`). **Non verificabile:**
se siano rimasti ordini vivi. Alle 09:29 UTC avevo letto 6 righe `betfair_live_orders` con
`source='scalper'`, `mode='paper'` (una `EXECUTABLE` delle 09:27:57 su 36090854). Alle 14:39 UTC la
tabella non ha **nessuna** riga di oggi: l'ultima è del 01/09 (`select ... order by updated_at desc limit 5`).
Le righe paper di oggi sono sparite; causa non indagata, fuori perimetro, forse il riavvio del runner delle
12:01 locali. Ne segue che lo specchio `source='scalper'` è osservato alle 09:29-09:30 ma non è più
ricontrollabile.

## B. Tennis: una partita automatica finita non si chiude mai (7.7.8 / 7.9.6.E1 / tetto) — FAIL

Evidenza:
- 36118619 (Bondar v Birrell): il 47336 la vede SUSPENDED dalle 09:24:18, ultima riga alle 09:24:58, poi
  esce dal feed. Il bot FLB scrive `mercato_chiuso` alle **09:25:02** («il mercato e' CHIUSO»): flumine ha
  chiuso il mercato e l'ordine 4001 è regolato (`pnl -0.04`).
- `tennis_live_now.status` di 36118619 resta **`SUSPENDED`**, riscritto ogni ~2 s: 09:25:38, 09:29:35,
  09:31:34, 10:15:58. Alle **14:40 UTC** sono 7 le partite finite ferme a `SUSPENDED`: 36117278, 36116084,
  36118619, 36116721, 36116525, 36117297, 36112100. `select ... from tennis_live_now where status='CLOSED'`
  restituisce **0 righe su tutta la tabella**, storico compreso.
- Per ogni bot le righe restano `running`, `stopping=[]`, e i follow automatici restano `STREAMING`. Alle
  14:40 UTC ogni bot ha **12 partite armate col tetto a 5** (7 fuori dal feed + 5 nel feed). La crescita
  osservata è stata 5 → 6 (09:25) → 7 (09:51) → 8 (09:57) → 9 → 10 → 11 (10:33) → 12.

Causa nel codice:
- flumine non passa MAI un book `CLOSED` a `process_market_book`: `CloseMarketEvent` + `continue`
  (`.venv/Lib/site-packages/flumine/baseflumine.py:157-159`).
- La cattura del runner tiene solo l'ultimo book ricevuto (`tennis_runner.py:390-392`), e
  `_build_now_state` ne ricava lo stato con un default `SUSPENDED` (`tennis_runner.py:1273-1295`).
  `upsert_tennis_now` (`:1380`) non scrive quindi mai `CLOSED`.
- Il ponte ferma le partite automatiche uscite dal feed SOLO se `_mercato_chiuso` legge `CLOSED`
  (`tennis_bot_service.py:492-500, 565-572`). Non succede mai: le righe non vanno a `stopping` e il follow
  non si chiude (`:612-620`, la partita risulta sempre occupata).
- Il tetto conta solo le armate ancora nel feed (`tengo`, `tennis_live/auto_mode.py:190-191`, chiamato a
  `tennis_bot_service.py:543-544`). Per questo le partite nuove continuano ad armarsi mentre le morte si
  accumulano.

Effetti: sorveglianza e armamento restano su mercati chiusi per ore, la lista del runner cresce per tutto
il giorno (una riga `tennis_live_now` ogni 2 s per ogni partita morta: IO sul DB), e il numero di armate
per bot supera il tetto dichiarato. Nessun ordine è possibile su un mercato chiuso: non è money-critical
diretto. Nessuna correzione fatta.

## C. Safe: checklist contro il feed dello stesso istante (7.9.7.C)

- **Motore indipendente contro bot.** Il `SafeEngine` di produzione, alimentato dal 47336, ha emesso 4
  segnali: 36115980 esatto 0-1 (09:22:32), 36090940 esatto 1-1 (09:22:40), 36119297 tennis (10:03:59) e
  36117297 tennis (10:07:17). Il bot li ha trattati tutti e 4: i due ESATTO scartati prima per
  `spread_anomalo` (09:22:34 e 09:22:41) e poi presi (trade 343 e 342), i due tennis presi (trade 344 e 345,
  2 s dopo). Il bot non ha nessun ingresso che il motore indipendente non avesse emesso. Esito **4/4**.
- **Ingressi (4/4 CONCORDA)**, ricostruiti sulla riga del feed con `updated_at = t1_feed_ms`, stato
  ricalcolato `signal` e prezzo uguale:
  - 342 Iwata v Vanraure, J2: lay 50 in 30-70, minuto 62, 1-1. h2h del feed [1 incontro, 1 da ≥4 gol] =
    h2h ricalcolato dal DB [1, 1] («troppo pochi: non blocca»). Difesa avversaria 1,20 ≤ 1,37. Spread
    1,5625 ≤ 1,6. Nessun veto.
  - 343 Ryukyu v Ehime, J3: lay 55. h2h del feed [8, 2] = DB [8, 2], quota 0,25 ≤ 0,58. La bancata è
    l'ospite, quindi la difesa che conta è quella di casa: 1,20 ≤ 1,37 (il lato è verificato: l'ospite ha
    1,40 e non è quello usato). Spread 1,31.
  - 344 Grant v Kalinina, BJK Cup: back 1,02. `pre_ko` 2,60/1,39: il favorito non è un super favorito,
    `sfavorito_estremo` ok. Spread 1,03.
  - 345 Mert v Tikhonova, WTA Adana: back 1,02. `pre_ko` assente → «dato assente (non blocca)», come da
    regola D5. Spread 1,07.
- **Scarti (tutti CONCORDA).** 2 `spread_anomalo`: rapporto ricalcolato 4,17 e 1,67, contro 1,6 = gli
  stessi valori scritti dal bot. 125 `pre_ko_assente`: le partite J2/J3 con KO 08:00 erano già in gioco
  all'avvio dell'app (08:56 UTC). Ricalcolati 17 su 17 per il giro delle 09:23: `pre_ko=null`, `inplay=true`.
- **Veti su 21 partite calcio.** Ricalcolo indipendente contro il check `campionato` del motore: 21 su 21
  concordi. Liga F: «FC Badalona (W) v Granada (W)» e «Real Sociedad (W) v Real Madrid FC (W)» scartati con
  «veto campionato: calcio femminile (nome squadra) (corso)», anche se «Spanish Liga F» non è nella lista
  delle competizioni. h2h e gol subiti del `selection_hint` uguali al ricalcolo da `fixture_predictions`
  su tutte le partite con fixture abbinata (esito in `automode_safe/safe_checklist_esito.json`).
- **Limite da dichiarare.** `fixture_round` è `None` su tutte le partite osservate. Le fixture di oggi (J2
  1606670, Liga F 1573593/1573597) NON sono nella tabella `matches`, quindi il veto «finale dal round» di
  oggi ricade sempre sul nome dell'evento Betfair. È un buco di copertura dei dati, non un errore di codice.
- **Limite.** Nessuna partita del pomeriggio europeo è stata osservata (rete caduta alle 10:57 UTC): la
  richiesta «≥ 5 partite del pomeriggio» è soddisfatta solo con 4 ingressi + 21 partite del mattino. BASE e
  PUNTA non sono state esercitate (pre-KO assente al mattino, Liga F vietata).

## Cosa NON ho potuto verificare
7.6.2 e 7.6.6 (azioni); il pomeriggio (rete giù dalle 10:57 alle 14:37 UTC e di nuovo alle 14:41 UTC;
sonde fermate per memoria); gli ordini scalper lasciati vivi a freno tirato (righe paper di oggi sparite da
`betfair_live_orders`); scanner fermo (E2); uscite discrezionali e di protezione tennis (7.7.4); il caso
«tennis a caldo» con posizione viva (E3); h2h indipendente per il trade 345 (tennis, non serve) e per le
partite viste dopo le 10:57.
