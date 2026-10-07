# CONFORMITA' AL PROGETTO DEI BOT TENNIS — 07/10/2026

Delegato del coordinatore (worktree `agent-a3b99e75233c89de6`, base `8226d766`). Niente
commit, niente DB, niente `.env`, nessuna chiamata Betfair.

Ordine dell'utente (07/10): «non voglio regressioni, e i bot tutti devono lavorare come
progettati» e «fixa tutto quello che incontri». Bot: `tennis_pro`, `tennis_flb`,
`tennis_swing`, `safe_tennis`; `tennis_scalper` SOLO audit (il suo CP4 e' di un altro
delegato, non toccato).

**Vincolo arrivato in corso d'opera dal coordinatore**: niente replay del banco fino al «via
libera replay» (CPU alla media under). Prima del messaggio ho girato UNA sonda di replay
(`tennis_pro`, vedi §3.2); dopo, solo lettura del codice e strumenti leggeri miei sulla
registrazione (nessun flumine, nessun ordine). Per questo **le due correzioni trovate sono
consegnate come patch VERIFICATE dai test e dalla falsificazione ma NON applicate**: il
confronto `--scenari tutti` prima/dopo col riferimento del coordinatore va fatto al via libera
(comandi in §6). Il lavoro tracciato del worktree e' INTATTO (`git status`: solo la cartella
`AUDIT_2026-10-07/`).

---

## 0. In breve

* **Scenario `base`, 0-1 azioni: e' quello che la spec prevede.** Il mercato registrato e' un
  Challenger poco liquido: abbinato totale massimo **7.455 GBP (~8.680 EUR)** contro i cancelli
  di liquidita' di progetto `min_matched` 50.000 (pro), 10.000 (FLB, swing). Il pro lo dichiara
  nella sua docstring: «GATE liquidita' (mai challenger/ITF)». Lo scalper fa l'unica azione
  prevista: dichiara una volta perche' non apre (partita gia' in gioco, gamba in-play spenta,
  decisione D6 del 17/09). Safe tennis non ha mai la sua condizione (1 set + 2 game di vantaggio
  nel secondo set): la registrazione parte dal 5-5 del secondo set e il leader lo perde.
* **Scenario `gate-aperto`/`live`, molte azioni: perche' il banco apre i cancelli E cambia
  alcune soglie di STRATEGIA** (swing `zin` 2->1, `er_max` 0,4->1, `conf_ticks` 2->1; FLB
  `lay_max` 1,10->1,30; scalper gamba in-play accesa e `runner_filter` tutti), mentre la nota
  del referto dice «cambiati SOLO numeri della UI, la strategia e' quella di produzione». E'
  un reperto del banco (catalogo §7.31), in §4.4 con la proposta.
* **Due BUG di `tennis_pro`, misurati sulla registrazione vera**, entrambi con effetto sugli
  ingressi, quindi **patch pronte e non applicate** (Decisioni D1 e D2):
  1. il pro usa l'**ultimo scambiato** (`ltp`) come prezzo del runner per scegliere il favorito,
     per il «favorito cortissimo <= 1,20» e per il prezzo d'inizio set del fade. Su questo
     mercato l'`ltp` resta fermo per minuti: alle 13:54:27 e' entrato in `compressed_fav` su
     Simakin a **2,20** (ltp fermo a 1,19), che non era nemmeno il favorito (Barrios 1,76/1,84).
     Il favorito per `ltp` differisce da quello del book in **921 book su 5.212**;
  2. il nome IPS troncato («Marcelo Tomas Barrios V») non combacia col nome completo del
     catalogo: il giocatore resta senza selezione e i setup su di lui non scattano mai.
* Un difetto di **progetto** del pro (non di codice) per l'utente: il setup `fade` dice «dopo
  un break PRECOCE» ma il codice non verifica il break, solo un salto di prezzo; sulla
  registrazione **4 ingressi fade su 4 senza nessun break** (Decisione D3).
* FLB, swing, safe_tennis: **nessuno scostamento** dalla spec sulla registrazione.

---

## 1. Le fonti della spec (e cosa manca)

| Bot | Spec usata | Note |
|---|---|---|
| tennis_pro | docstring di `Betfair/stream/tennis_scalper/tennis_pro_bot.py:1-29` (6 setup, gate liquidita', scaglioni, stop, uscita strutturale) + decisioni 25/09 (superficie, `trend`/`adapt`/`maker` accesi: `CRONOSTORIA.md:3117`, `:3175`) + `superficie.py:1-28` | `TENNIS_BOT_DOSSIER.md`, citato dai referti del 17/09 come fonte, **non esiste nel repo** (`find /` vuoto) |
| tennis_flb | docstring `tennis_flb_bot.py:1-24` + decisione D4 maker al best-back (`CHECKPOINT_4_BOT_TENNIS_2026-09-17.md` D4) | idem |
| tennis_swing | docstring `tennis_swing_bot.py:1-8` + `AUDIT_4_BOT_TENNIS_2026-09-17.md` §A.4 + decisione D1 (non si dimentica un trade) | idem |
| tennis_scalper | `BIBBIA_SCALPER_TENNIS.md`, preset `run_tennis_scalper.TENNIS_PARAMS:41-79`, decisione D6 | solo audit |
| safe_tennis | `COSTITUZIONE_SAFE_STRATEGY.md` §2 riga 4 (ingresso), §3 TENNIS (uscite), §3.1 (decisione a modello), default `engine.py:281-316` | **`SPEC_STRATEGIA_S.md`, citato in `CLAUDE.md`, non esiste nel repo** |

Cancelli che l'utente controlla dalla UI (params della riga per partita, scheda del bot):
pro `min_matched`, `min_book_size`, `price_min/max`, `stake`, abilitazione dei setup, varianti;
FLB `lay_max`, `min_matched`, `min_lay_size`, `exit_mode`, `green_ticks`; swing `zin`, `er_max`,
`conf_ticks`, `price_min/max`, `min_matched`; scalper preset con `inplay_tick_enabled`,
`runner_filter`; safe_tennis `setsLeadMin`, `gamesLeadMin`, `backMin/Max`, `excludeBestOf5`,
`setsPlayedMax`, `favSuperMax`, `scoreConfirmSec`, uscite (manuali di serie per tutti).

---

## 2. La registrazione (misurata da me, sola lettura)

`_live_raw_tennis/20260707/35790089/`: Match Odds, 5.217 book (5.212 OPEN in gioco, 4
SUSPENDED, 1 CLOSED), betDelay 3, regolatore `MR_ITA`; sidecar IPS 104 campioni. Da 12:28 UTC
(set 1-0 Barrios, 5-5 nel secondo, Simakin al servizio) alla fine: Simakin vince 7-5 il
secondo e 7-6 il terzo. Barrios = 9633138 (`sortPriority` 1, «home» dell'IPS, favorito a 1,22
all'inizio), Simakin = 35635727. **Il catalogo (nomi Betfair) e la competizione NON sono nella
registrazione** (limite 1 del banco); in cloud manca anche `_names.json`.

| Grandezza | Valore misurato |
|---|---|
| abbinato totale del mercato | 604 -> 7.455 GBP (~8.680 EUR al cambio del banco) |
| best-lay minimo | Barrios 1,20 · Simakin 1,17 |
| book con best-lay <= 1,10 e >= 5 sul lato | **0** (<= 1,20: 103; <= 1,30: 526) |
| favorito per ultimo scambiato != favorito del book (medio) | **921 / 5.212** book, 23 intervalli fra 12:40 e 13:57 |
| «favorito <= 1,20»: per ultimo scambiato / per book | 166 / 214 book; per `ltp` SI' e per book NO: 123 book (13:53:32-13:55:19) |
| detector dello swing coi parametri di PRODUZIONE senza il cancello di liquidita' | 22 segnali (limite superiore: nessun trade aperto), 0 con la finestra mista fra due selezioni |

Strumenti (in `scratchpad/conf/`, fuori dal repo): `scan_raw.py` (book da
betfairlightweight, lo stesso parser di flumine, minuto per minuto) e `condizioni.py`
(condizioni d'ingresso con le funzioni PURE dei bot: `_er`, `_rsi`, `_tki`).

---

## 3. Bot per bot

### 3.1 Tabella bot x condizione

Legenda verdetto: **OK** conforme · **SCELTA** scelta documentata · **BUG** · **DUBBIO** ·
**BANCO** reperto del banco.

| Bot | Condizione (spec, file:riga) | Prevista dalla spec | Presente nei dati | Fatto dal bot | Verdetto |
|---|---|---|---|---|---|
| pro | liquidita' `min_matched` 50.000 (`tennis_pro_bot.py:154`, gate `:762`; docstring `:22`) | mai Challenger/ITF | NO (max ~8.680 EUR) | 0 ingressi in `base` | **OK** |
| pro | in gioco, punteggio presente, cambio di punteggio, un trade per game (`:760-773`) | si' | si' | rispettati (sonda §3.2) | OK |
| pro | banda 1,08-3,6 e profondita' 10 sul lato (`:556-559`) | si' | in parte | rispettate | OK |
| pro | break point 0-40/15-40, erba -> chi serve, altro -> chi riceve (`:330-340`, `:596-605`; `superficie.py:6`) | si' | in 4 game (12:35, 13:10, 13:15, 13:28, dal sidecar IPS) | 3 ingressi, direzione = ribattitore (superficie `hard` di default: competizione assente); il 4° (13:28, game 3-5) no perche' quel game era gia' tradato dal serving_for_set delle 13:26 (un trade per game, `:771-773`) | **SCELTA** (25/09) / OK |
| pro | fade «dopo un break PRECOCE» (docstring `:13-14`) / codice: salto >= 8 tick dal prezzo d'inizio set nei primi 3 game (`:607-625`) | break precoce | **nessun break** nei primi 3 game del 3° set | **4 fade** (G0-0, G0-1, G1-1, G1-2), il primo a 0-0 senza un game giocato | **BUG** (riferimento `ltp` fermo, D1) + **DUBBIO di progetto** (nessun controllo del break, D3) |
| pro | favorito cortissimo <= 1,20 (`:675-686`) | favorito a <= 1,20 | si' (214 book per book) | 1 ingresso alle 13:54:27 su Simakin a **2,20**, favorito sbagliato | **BUG** (D1) |
| pro | set transition (`:627-643`) | nei 2 game dopo il set | si' (12:35:4x) | mai: precedenza fissa al fade (`:777-790`) | OK (priorita' di progetto) |
| pro | serving for the set (`:645-659`) | 5-x, lead >= 1 | si' (13:26 Simakin 5-3) | 1 ingresso, direzione dal regime (`adapt`) | **SCELTA** (25/09) |
| pro | mappa nome IPS -> selezione (`:307-315`) | robusta | IPS «Marcelo Tomas Barrios V» (troncato) | col nome completo del catalogo: Barrios **senza selezione** | **BUG/DUBBIO** (D2: da confermare col catalogo vero) |
| pro | uscite: target, stop, strutturale, scaglione, timeout 25 s (`:879-905`) | si' | — | 6 timeout d'ingresso, 3 stop, 0 target nella sonda; stop anche dallo spread largo | OK (gate di liquidita' esiste per questo) |
| FLB | liquidita' `min_matched` 10.000 (`tennis_flb_bot.py:89`, gate `:344`) | si' | NO | 0 ingressi | **OK** |
| FLB | best-lay <= `lay_max` 1,10 e >= 5 (`:82,90`, `:384`) | favorito ESTREMO | **NO, 0 book** (minimo 1,17) | 0 ingressi anche senza cancello | **OK** |
| FLB | in gioco (`:97`, `:376`); prezzo maker al best-back (`:381`) | si' | si' | — | OK / SCELTA (D4 17/09) |
| FLB | `gate-aperto` porta `lay_max` a 1,30 (`replay_bot.py:244`) | — | 526 book | 17 azioni | **BANCO** (§4.4) |
| swing | liquidita' `min_matched` 10.000 (`tennis_swing_bot.py:98`, gate `:661`) | si' | NO | 0 ingressi | **OK** |
| swing | estremo del favorito: z >= 2, ER < 0,4, conferma 2 tick, cross RSI 65/35, banda 1,08-8 (`:80-82`, `:672-693`) | si' | **si', 22 segnali** se il mercato fosse liquido | non valutato (cancello prima) | OK |
| swing | favorito per ultimo scambiato (`:205-213`) | «il favorito» | 921 book in disaccordo col book | storia unica per mercato, 0/22 segnali con finestra mista | **DUBBIO** (§4.3, nessuna correzione) |
| swing | `gate-aperto`: `zin` 1, `er_max` 1, `conf_ticks` 1 (`replay_bot.py:245-246`) | — | — | 126 azioni | **BANCO** (§4.4) |
| scalper | missione «1 tick per fase», gamba in-play spenta (`TENNIS_PARAMS:63-68`, `tennis_scalper_bot.py:673-703`, `:909`) | non apre in gioco, lo dice una volta | partita gia' in gioco | 1 azione `missione_blocca` | **OK** (D6 17/09) |
| scalper | favorito per best-back (`tennis_scalper_bot.py:766-790`) | — | — | non usa l'`ltp` | OK |
| scalper | `gate-aperto`: in-play acceso, tutti i runner, soglie a zero | — | — | 99 azioni | **BANCO** (§4.4); CP4 all'altro delegato |
| safe_tennis | in gioco, singolare, 1+ set di vantaggio, 2+ game nel set, set giocati <= 1, quota back leader 1,02-1,10, punteggio stabile 15 s, al meglio dei 3 (`engine.py:1493-1660`, default `:281-316`) | si' | **mai**: set 1-0 solo fino a 12:35 con game 5-5/5-6 e quota 1,2; poi 1-1 | 0 ingressi; motivi `sets,games,setsPlayed` x637, `games,odds` x51 | **OK** |
| safe_tennis | competizione assente -> `bestOf` n/d -> nessun segnale (`engine.py:1590-1599`) | «mai un ingresso al buio» | assente nel raw | il banco DICHIARA un torneo al meglio dei 3 | SCELTA (CERT 14/09) |
| safe_tennis | uscita OBBLIGATORIA: 2 game persi di fila E parita'/vantaggio perso nel set (`exits.py:1034-1047`, `_track_tennis` `:833-925`) | si' | posizione iniettata: Barrios 2-2 -> 2-4 nel 3° set, mai in vantaggio | nessuna uscita, `exit_hold` x25, perdita intera -2,00 | **SCELTA** (CERT 13/09: «0-2 di inizio set resta fuori»), vedi §4.5 |

### 3.2 tennis_pro: la sonda (unico replay girato, prima dello stop)

Comando (strumento mio, banco di produzione, nessun file del repo toccato):
`python3 scratchpad/conf/sonda.py tennis_pro gate-aperto '{"min_matched":0,"min_total_matched":0}' "Marcelo Tomas Barrios V=9633138,Ilia Simakin=35635727"`
= scenario `gate-aperto` con **SOLO il cancello di liquidita' aperto** (tutte le altre soglie di
produzione) e il catalogo dichiarato coi nomi dell'IPS. Esito: **OK, 0 violazioni**, 5.216 tick,
29 azioni, 11 ordini, 4 abbinati, stati OPEN/CLOSING, 2 residui sotto 0,50 dichiarati e regolati.

| Ora | Setup | Punteggio (set, game, punti, servizio) | Lato @ prezzo | Esito |
|---|---|---|---|---|
| 12:35:08 | break_point | 1-0, 5-6, 15-40, Barrios | BACK Simakin 3,50 | timeout ingresso |
| 12:35:49 | fade | 1-1, **0-0**, 0-0 | BACK Barrios 1,52 | timeout |
| 12:48:44 | fade | 1-1, 0-1 | BACK Barrios 1,77 | timeout |
| 12:53:01 | fade | 1-1, 1-1 | BACK Barrios 1,56 | timeout |
| 12:57:47 | fade | 1-1, 1-2 | BACK Barrios 1,75 | timeout |
| 13:10:25 | break_point | 1-1, 2-3, 15-40, Barrios | BACK Simakin 1,51 | timeout |
| 13:15:10 | break_point | 1-1, 2-4, 40-0, Simakin | BACK Barrios 1,85 | stop dopo 4 s (-0,056) |
| 13:26:33 | serving_for_set | 1-1, 3-5, Simakin | LAY Simakin 1,96 | stop (-0,086) |
| 13:54:27 | compressed_fav | 1-1, 6-6, tie-break 6-6 | BACK Simakin **2,20** | stop dopo 1 s (-0,043) |

Nessun break nei primi tre game del terzo set (0-1, 1-1, 1-2 sono tutti game tenuti al
servizio): i quattro fade non hanno la causa che la spec chiede.

### 3.3 Riepilogo per bot

* **tennis_pro** — base conforme. Due BUG misurati (D1, D2) con patch pronte; un difetto di
  progetto per l'utente (D3). Le scelte del 25/09 (superficie di default `hard`, direzione
  adattiva dal regime) sono rispettate.
* **tennis_flb** — conforme: la sua condizione (favorito ESTREMO a <= 1,10) non c'e' mai su
  questa partita, quindi 0 ingressi anche senza il cancello di liquidita'. Le 17 azioni di
  `gate-aperto` vengono da `lay_max` 1,30 (strategia cambiata dal banco).
* **tennis_swing** — conforme: 0 ingressi per il cancello di liquidita'. Coi parametri di
  produzione e senza cancello il detector firmerebbe 22 volte (prova che la strategia di
  produzione, da sola, puo' essere esercitata senza abbassare `zin`/`er_max`/`conf_ticks`).
* **tennis_scalper** (solo audit) — base conforme (D6). `gate-aperto` accende la gamba in-play
  e tutti i runner: strategia diversa dal preset. CP4 non toccato.
* **safe_tennis** — conforme: condizione d'ingresso mai presente; uscite come da regole
  certificate il 13/09.

---

## 4. I reperti

### 4.1 [BUG, pro] Il prezzo del runner e' l'ultimo scambiato — patch `proposte/P1_pro_prezzo_del_book.diff`

* **Causa radice**: `tennis_pro_bot.py:343-345` (`_favourite` = minimo di `ltp`), `:682`
  (`compressed_fav` confronta `ltp` con 1,20), `:696-697` (`_set_start_px` = `ltp` al primo
  book del set, riferimento del salto del fade `:617-621`). `last_price_traded` e' l'ultimo
  SCAMBIO, non il prezzo: su un mercato con 7.455 GBP abbinati in 90 minuti resta fermo per
  minuti. Lo stesso file definisce gia' il prezzo come medio del book con `ltp` di ripiego
  (`_track_px:356`): la patch riusa quella regola (`_prezzo`), nessuna soglia cambiata.
* **Misura**: 13:54:27, Simakin `ltp` 1,19 (fermo dalle 13:52), book 2,18/2,32; Barrios `ltp`
  6,40, book 1,76/1,84 -> ingresso `compressed_fav` su Simakin a 2,20. 12:35:52, primo book
  del terzo set: Barrios `ltp` 1,40 (di prima della fine del set), book 1,51/1,57 -> salto
  «17 tick» e fade a 0-0. Al contrario, 13:27-13:30 Simakin a 1,16/1,17 con `ltp` 1,36: il
  favorito cortissimo vero NON viene visto.
* **Riga di CRONOSTORIA che motiva l'`ltp`**: nessuna (il codice e' cosi' dalla nascita; il
  17/09 l'audit §A.2 descrive i setup senza discutere la fonte del prezzo).
* **Perche' non applicata**: cambia QUANDO il bot entra (toglie ingressi falsi, ne aggiunge di
  veri) -> regola del brief: decide l'utente (D1).
* **Verifica della patch** (applicata e poi tolta): test nuovo
  `test_pro_prezzo_vivo_2026_10_07.py` 5 test: **4 rossi sul codice di oggi** per il motivo
  giusto, verdi con la patch; suite collegata `test_pro_prezzo_vivo` + `tennis_scalper/tests/
  test_tennis_pro.py` + `test_tennis_pro_superficie_2026_09_25.py` + `stream/tests/
  test_live_engine_pro.py`: **92 verdi** (1,75 s). Falsificazione: (a) `_prezzo` che rimette
  l'`ltp` davanti al book -> 4 rossi; (b) solo `compressed_fav` di nuovo su `ltp` -> 1 rosso.
  Albero ripristinato (`grep -c MUTAZIONE` = 0, `git diff --stat` identico).

### 4.2 [BUG da confermare, pro] Nome IPS troncato — patch `proposte/P2_pro_nome_ips_troncato.diff`

* **Causa radice**: `_lookup_sel` (`tennis_pro_bot.py:307-315`) prova nome completo e cognome
  (ultimo token). L'IPS scrive «Marcelo Tomas Barrios V» (23 caratteri, troncato): con un
  catalogo «Marcelo Tomas Barrios Vera» ritorna `None` (provato con la classe di produzione:
  `None` anche con «M Barrios Vera»; trovato solo se il catalogo porta il nome troncato).
* **Effetto**: nessuna inversione di direzione (fail-closed), ma i setup su Barrios non
  scattano: sulla sonda §3.2 si perde il break point delle 13:15:10 (BACK del ribattitore
  Barrios); in generale break point da ribattitore, set vinto, doppio break del giocatore dal
  nome lungo.
* **Non verificabile qui**: il nome VERO del catalogo Betfair (niente chiamate Betfair, niente
  `_names.json` in cloud). Sul PC dell'utente il `_names.json` di `tennis_rec/20260707` lo dice.
* **Patch**: dopo nome e cognome, il nome del catalogo che COMINCIA col nome IPS, solo se
  unico (due candidati = nessun match, stessa prudenza del fix audit #13). Test nuovo
  `test_pro_nome_ips_troncato_2026_10_07.py` 3 test: 1 rosso sul codice di oggi, verde con la
  patch; suite pro collegata 90 verdi. Le due patch si applicano insieme (`git apply --check`).

### 4.3 [DUBBIO, swing] Favorito per ultimo scambiato e storia unica per mercato

`tennis_swing_bot.py:205-213` sceglie il favorito per `ltp`; `:669` tiene UNA storia di tick
per mercato. Se il favorito cambia, la finestra mescola i prezzi di due giocatori. Misurato coi
parametri di produzione: **0 segnali su 22** con la finestra mista; non e' stato provocato su
questa partita. Nessuna correzione (cambierebbe il detector); da tenere d'occhio su una partita
con cambi di favorito frequenti.

### 4.4 [BANCO] `gate-aperto` cambia la strategia di swing, FLB e scalper

`Betfair/stream/tennis_live/tools/replay_bot.py:212-252` (fuori dal mio perimetro, solo
proposta): la descrizione (`:140-144`) e la nota del referto dicono «SOLO le soglie di
liquidita' e di banda ... la STRATEGIA non cambia», ma per swing abbassa `zin`, `er_max`,
`conf_ticks` (le soglie del detector), per il FLB porta `lay_max` (la definizione di
«favorito estremo») da 1,10 a 1,30, per lo scalper accende la gamba in-play e tutti i runner.
Catalogo §7.31. Le azioni di `gate-aperto`/`live`/`uscite-*`/`soldi-veri*` su quei bot
certificano la CONDOTTA degli ordini (che resta utile), non la strategia di produzione.
**Proposta al coordinatore**: uno scenario in piu' `solo-liquidita'` (`min_matched` e
`min_total_matched` a 0, nient'altro) che e' il vero test di conformita' su un Challenger: per il
pro la sonda §3.2 lo ha gia' mostrato (29 azioni, 0 violazioni); per lo swing le condizioni ci
sono (22 segnali); per FLB e scalper darebbe 0 azioni, ed e' la risposta giusta. E correggere
la nota per i bot dove si cambia una soglia di strategia. Il tempo per scenario tennis e' ~1-3 s:
il tetto non e' a rischio.

Inoltre: `certifica` non passa mai `--nomi`, e in cloud manca `_names.json`: **il pro non e'
mai certificato sui 4 setup che dipendono dai nomi** (break point, set transition, serving for
set, double break) su questa registrazione. Sul PC dell'utente il file c'e' (referto 17/09 §J).

### 4.5 [SCELTA DOCUMENTATA, safe_tennis] L'uscita obbligatoria non scatta da 2-2 a 2-4

Negli scenari con posizione iniettata (BACK Barrios 2,00 @ 1,20, non e' un ingresso della
strategia) Barrios perde due game di fila da 2-2 a 2-4 nel terzo set senza avere mai avuto un
vantaggio nel set: la regola (`exits.py:1034-1047`, `set_lead_lost` di `_track_tennis`) NON
esce, per scelta scritta il 13/09 («il 0-2 di inizio set resta fuori»). Il take profit al game
vinto passa dalla decisione a modello (§3.1 della costituzione) e tiene (`exit_hold` x25).
Risultato: -2,00 (stake intero). Conforme; lo segnalo solo perche' l'utente veda il caso.

---

## 5. Cosa ho cambiato

**Nessun file tracciato modificato.** File nuovi, solo in `AUDIT_2026-10-07/`:
* `CONFORMITA_BOT_TENNIS.md` (questo referto);
* `proposte/P1_pro_prezzo_del_book.diff` (tocca `Betfair/stream/tennis_scalper/
  tennis_pro_bot.py`, aggiunge `Betfair/stream/tennis_live/tests/test_pro_prezzo_vivo_2026_10_07.py`);
* `proposte/P2_pro_nome_ips_troncato.diff` (stesso modulo, aggiunge
  `Betfair/stream/tennis_live/tests/test_pro_nome_ips_troncato_2026_10_07.py`).

Nota di perimetro: i moduli dei tre bot stanno in `Betfair/stream/tennis_scalper/`, non in
`tennis_live/` come dice il brief; li ho trattati come «moduli dei bot tennis» (il modulo dello
scalper escluso). Se il coordinatore li considera fuori perimetro, le patch restano proposte.

Migrazioni SQL: nessuna.

---

## 6. Test, replay, tempi

* Test (patch applicate in prova e poi tolte): comandi in §4.1/§4.2,
  `python3 -m pytest <file> -q -p no:cacheprovider`; 92 e 90 verdi, 0 rossi, < 2 s.
* Replay: SOLO la sonda §3.2 (prima dello stop del coordinatore), ~3 s.
* **Da fare al «via libera replay»**, uno alla volta (per ogni patch che l'utente approva):
  ```
  git apply AUDIT_2026-10-07/proposte/P1_pro_prezzo_del_book.diff AUDIT_2026-10-07/proposte/P2_pro_nome_ips_troncato.diff
  python3 -m Betfair.stream.backtest.certifica tennis_pro 35790089 --data-dir /home/user/python-database-automation/_live_raw_tennis/20260707 --scenari tutti --worker 1
  ```
  confronto col riferimento `coord/tennis_base_tennis_pro.txt`. Attese: righe di `base`,
  `dry-run`, `bot-fermo`, `feed-stantio`, `parziali`, `riavvio`, `catalogo-assente` IDENTICHE
  (cancello di liquidita' chiuso / nessun catalogo); negli scenari a cancelli aperti cambia SOLO
  il numero di ingressi `compressed_fav`/`fade` (P1); P2 non cambia niente senza catalogo
  (il banco non lo passa). Poi la sonda §3.2 coi nomi completi
  (`"Marcelo Tomas Barrios Vera=9633138,Ilia Simakin=35635727"`) prima/dopo P2.

## 7. Parita' paper/live

Le patch toccano solo la DECISIONE d'ingresso del pro (prezzo e nome), che non distingue
paper e live: stesso codice nei due mondi, nessun ramo per modalita'. Da confermare negli
scenari `live`/`soldi-veri*` al via libera.

## 8. Cosa NON ho fatto / NON ho potuto verificare

* Replay prima/dopo delle patch (stop del coordinatore); replay di FLB, swing, scalper, safe
  coi soli cancelli di liquidita' aperti (stima dai miei strumenti, non dal banco).
* Il nome vero del catalogo di Barrios Vera; la competizione e la superficie vere della partita
  (il banco usa `hard` di default e un torneo «al meglio dei 3» dichiarato).
* **Una sola partita, da meta' del secondo set, Challenger poco liquido**: con i default nessun
  bot (tranne la spiegazione dello scalper) entra, quindi la condotta di produzione NON e'
  esercitata. Servono dalle registrazioni dell'utente: (1) una partita ATP/WTA principale con
  abbinato > 50.000 (pro coi default); (2) un favorito che scende <= 1,10 in gioco (FLB coi
  default); (3) una partita in cui Safe tennis ha 1 set + 2 game di vantaggio con quota
  1,02-1,10 (ingresso vero e uscite vere); (4) una registrazione con `_names.json` e il nome
  del torneo (setup del pro che dipendono dai nomi, superficie vera); (5) una partita con un
  break nei primi tre game del set (fade come da spec).
* Doppi, ritiri, mercato annullato, sospensioni lunghe con ordini vivi: non presenti.
* Lo scalper: solo lettura delle condizioni, nessuna correzione.

## 9. Decisioni per l'utente

* **D1 — tennis_pro legge il prezzo dall'ultimo scambiato.** Su questa partita e' entrato in un
  «favorito cortissimo <= 1,20» su un giocatore a 2,20 che non era nemmeno il favorito, e ha
  fatto un fade a 0-0 nel set per un prezzo fermo da prima della fine del set precedente.
  **Proposta**: applicare P1 (prezzo = medio del book, ultimo scambiato solo se il book e'
  vuoto; nessuna soglia cambiata). Effetto: meno ingressi falsi, qualche ingresso vero in piu'.
* **D2 — nomi IPS troncati.** Con nomi lunghi il bot puo' non riconoscere un giocatore e
  perdere i setup su di lui (mai invertire la direzione). **Proposta**: verificare sul PC il
  nome del catalogo di 35790089 in `_names.json`; se e' il nome completo, applicare P2.
* **D3 — il setup «fade» non controlla il break.** La spec dice «dopo un break precoce»; il
  codice entra su qualunque salto di 8 tick nei primi 3 game del set. Qui: 4 fade, 0 break.
  Con P1 il fade a 0-0 sparisce (salto di 1 tick), ma restano ingressi senza break (stima: 2 su
  4, da confermare col replay). **Proposta**: richiedere anche che il favorito abbia perso un
  game al servizio nel set corrente (dal punteggio IPS, che il bot ha gia'). E' una regola in
  piu': la decide l'utente.
* **D4 (banco) — `gate-aperto` cambia la strategia di swing/FLB/scalper.** Proposta §4.4:
  scenario `solo-liquidita'` e nota onesta. Decide il coordinatore (file del banco).

## 10. Da controllare dal vivo in paper al prossimo avvio

* tennis_pro su una partita di Challenger: nell'attivita' NESSUN ingresso (abbinato sotto
  50.000) — e' il comportamento di progetto, non un guasto.
* tennis_pro su una partita liquida: per ogni `entry` di tipo `compressed_fav` confrontare il
  prezzo d'ingresso con 1,20 (con il codice di oggi puo' essere molto sopra: reperto D1).
* Scheda del pro: i nomi dei due giocatori risolti (se un nome IPS e' troncato, i setup su
  quel giocatore non compaiono mai: reperto D2).
