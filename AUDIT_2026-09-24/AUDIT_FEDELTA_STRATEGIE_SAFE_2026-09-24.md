# AUDIT FEDELTA' STRATEGIE SAFE (calcio e tennis) - 24/09/2026

> Delegato Opus (audit in SOLA LETTURA). Nessuna modifica al codice, nessun commit, nessun
> processo, nessun DB. Worktree allineato a master `20a913a` (`git merge --ff-only master`).
> Domanda dell'utente: "Le strategie Safe (sia tennis che calcio) sono state progettate come
> da strategia? Dovrebbero esserci da qualche parte le trascrizioni dei video."
> Il file e' ASCII-only (niente accenti): "e'" = e accentata.
> Nome dell'autore del corso: MAI usato qui, si dice "Strategia S".

---

## 0. Risposta breve

- **Trascrizioni vere dei video: NON ESISTONO** (ne' nel repo, ne' sul Desktop, ne' in
  Documenti/Download). Esistono i VIDEO originali (63 file, 435 MB) e un RIASSUNTO fatto a
  partire dal corso; la strategia che il codice insegue e' quel riassunto. Dettaglio in par.1.
- **Calcio: PARZIALE.** I numeri del riassunto (minuti, punteggi, bande di quota, mercati,
  lato) sono copiati fedelmente e difesi da test e dal banco; ma la condizione discrezionale
  che la strategia mette in TUTTE e tre le varianti ("controllo del gioco") e' spenta, le
  uscite "esci comunque" a 80'/72'/83' possono non uscire (decisione a modello), e la
  "selezione aggiuntiva" dell'Esatto e' spenta. Le divergenze a maggior impatto sui soldi
  (stake fisso, quota di banca libera, minuti come soglia) sono DECISIONI SCRITTE
  dell'utente; due no (vedi par.6).
- **Tennis: PARZIALE.** Ingresso (1 set + 2 game, un solo set giocato, doppi e Slam maschili
  esclusi) e uscita obbligatoria (2 game di fila E vantaggio perso nel set, in AND) sono
  fedeli; ma l'uscita "obbligatoria senza eccezioni" con il cancelletto di approvazione
  acceso ASPETTA UN CLIC (decisione dell'utente 14/09), la banda d'ingresso 1,01-1,10 e'
  piu' larga del "~1,03" del riassunto (interpretazione degli sviluppatori, non trovo una
  decisione dell'utente), e "match troppo equilibrati / sfavoriti estremi" non e' filtrato
  (non c'e' nemmeno il dato pre-partita nel contesto tennis).

---

## 1. Fonti: che cosa esiste e che cosa manca

### 1.1 Catena delle fonti (dalla piu' originale alla piu' derivata)

| # | fonte | dove | stato |
|---|---|---|---|
| F0 | **Corso video originale** (63 file: 57 `.mp4` + 4 `.xlsx` + cache) | `C:\Users\Admin\Desktop\Strategia S - <autore>\Strategia S - <autore>\` | ESISTE, **mai trascritto**. Nessun `.txt/.srt/.vtt/.md` accanto ai video (ricerca `find` su Desktop/Documenti/Download, maxdepth 5, pattern trascri*/transcript*/*.srt/*.vtt: zero risultati pertinenti) |
| F1 | **Artifact "Strategia S"** (guida + quiz) | `https://claude.ai/code/artifact/7652e448-f013-4c25-856c-9243221573c1`, puntato da `C:\Users\Admin\Desktop\PYTHON DATABASE\STRATEGY S.txt:1` | ESISTE (letto oggi). Piede di pagina: "Dati **riassunti** dal corso video originale". E' un RIASSUNTO, non una trascrizione |
| F2 | **`SPEC_STRATEGIA_S.md`** | radice del checkout principale (`...\python-database-automation\SPEC_STRATEGIA_S.md`, 183 righe, 14/09 10:50) | ESISTE ma **NON E' VERSIONATO**: `git ls-files --error-unmatch SPEC_STRATEGIA_S.md` -> "did not match"; assente nel worktree. Righe 3-4: "Trascrizione fedele dell'artifact ... estratta il 14/09". Il banco lo cita come specifica (`Betfair/stream/backtest/registro_bot.py:145,156,167`) |
| F3 | `RISCONTRO_CALCIO_2026-09-14.md`, `RISCONTRO_TENNIS_2026-09-14.md` | `Betfair/safe_strategy/` | riscontri regola-per-regola del 14/09 (numeri di riga di allora, oggi spostati) |
| F4 | `CERTIFICAZIONE_2026-09-13.md` par.6 (difformita' lasciate per decisione dell'utente) | `Betfair/safe_strategy/CERTIFICAZIONE_2026-09-13.md:356-389` | decisioni del 13/09 |
| F5 | `COSTITUZIONE_SAFE_STRATEGY.md` par.2-par.3, par.2.1 (selezione aggiuntiva, 16/09), par.9.1 | `Betfair/safe_strategy/` | architettura e storia delle uscite |

Confronto F1 vs F2 fatto oggi riga per riga: F2 riporta fedelmente i parametri di F1 e ci
aggiunge le ECCEZIONI decise dall'utente (SPEC righe 8-13 e 164-183). Una sola differenza di
contenuto: F1 scrive le finestre d'ingresso chiuse (55-62', 48-50', 66-70'), F2 le riscrive
come soglie aperte per decisione dell'utente del 14/09 (SPEC righe 8-13).

### 1.2 Che cosa del corso NON e' nella strategia dichiarata

L'artifact F1 copre solo le cartelle "4. STRATEGIA", "RISULTATO ESATTO/2. STRATEGIA",
"VARIANTE PUNTA", "TENNIS/4. STRATEGIA" (e parte di "Ritiri"). Questi video **non hanno nessuna
controparte scritta**, quindi nessuno puo' dire oggi se il bot li rispetta:

| cartella / video | contenuto presumibile dal titolo | impatto sul bot |
|---|---|---|
| `2. SELEZIONE PARTITE/1. Come selezionare le partite`, `2. Competizioni da evitare`, `3. Migliori campionati` | filtro campionati/competizioni del calcio | il bot calcio **non ha nessun filtro di campionato** (`excludeCompetitions` esiste solo nella sezione tennis, `engine.py:255`) |
| `RISULTATO ESATTO/1. SELEZIONE PARTITE/1. Come selezionare le partite` | selezione specifica dell'Esatto | coperto solo in parte dalla "selezione aggiuntiva" (una riga di F1) |
| `4. STRATEGIA/8. Accortezza`, `9. Visione partite`, `10. Esempio operativita' live`, `11. Uscita emergenza altro book` | accorgimenti operativi, uscita d'emergenza | sconosciuto |
| `5. EXTRA/2. Uscita manuale`, `3. FLESSIBILITA' SELEZIONE PREMATCH`, `2. Calcolatore.xlsx`, `1. Operazioni.xlsx` | uscita manuale, tolleranze sulle bande pre-match | sconosciuto: la "flessibilita'" potrebbe toccare proprio le bande 1,40-1,80 / 4-8 che oggi rendono la BASE attivabile su ~1 partita su 8 (`PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md:571-574`) |
| `TENNIS/3. SELEZIONE PARTITE/1. Match da evitare`, `2. Parametri`, `3. Orario` | selezione tennis, orario | nel bot: solo doppi/Slam maschili/competizioni; nessun parametro pre-partita, nessun orario |
| `TENNIS/4. STRATEGIA/6. I profitti e le perdite`, `7. Uscita infortunio`, `TENNIS/5. EXTRA/1. Tennis-Operazioni-Traccia.xlsx` | uscita su infortunio | nel bot nessuna uscita per infortunio (nessun dato nel feed; nessuna occorrenza di ritiro/infortunio in `engine.py`, `exits.py`, `bot_service.py`) |

**Conclusione sulle fonti:** la "strategia dichiarata" contro cui il codice e' stato
certificato e' F2 (= riassunto F1 + eccezioni dell'utente). Il confronto con i VIDEO non e'
mai stato fatto; per farlo serve una trascrizione (decisione dell'utente: e' un processo
nuovo, non lo avvio).

---

## 2. Parametri effettivi

- **Default nel codice** (verificati oggi): `Betfair/safe_strategy/engine.py:187-270`
  (ingressi, stake), `Betfair/safe_strategy/exits.py:66-126` (uscite),
  `Betfair/safe_strategy/bot_service.py:122-200` (bot), `Betfair/safe_strategy/risk.py:39-43`
  (tetti: `per_event_liability_cap` 150, `per_event_max_trades` 3, `daily_loss_stop` -50).
- **Valori in DB**: ultima fotografia scritta = 16/09 (`FASE0_VERITA_DI_PARTENZA_2026-09-16.md:500-532`):
  `variants = ["tennis"]` (calcio SPENTO del tutto), `strategy_modes.tennis = "live"`,
  `stake = {laySize 2, backSize 3}`, `tennis_exit_approval = true`, tetti `daily_liability_cap 0`
  e `max_open_trades 0` (spenti), `daily_loss_stop -50`; uscite identiche ai default.
  **Non verificato oggi** (divieto di DB). Dal 24/09 all'avvio Safe torna in paper
  (`CRONOSTORIA.md`, sezione 24/09, riga ~2507: "al nuovo avvio ... Omega/Mike/Safe tornano a paper").

---

## 3. CALCIO - regola per regola

Legenda ESITO: **CONF** conforme - **DIV** divergente (differenza esatta) - **NON IMPL**
non implementata (o spenta) - **AGG** implementata ma non nella strategia.
Colonna "decisione": dove una divergenza e' coperta da una decisione scritta dell'utente.

### 3.1 BASE - lay della squadra che perde, 1X2 (SPEC par.1, righe 20-74)

| regola (fonte) | implementazione | parametro effettivo | esito | decisione / nota |
|---|---|---|---|---|
| Mercato 1X2, BANCA (SPEC:20) | `engine.py:998-1008` `side="LAY"`, `market_type="MATCH_ODDS"` | - | CONF | |
| Si banca chi PERDE (SPEC:22-23) | `engine.py:980-985` (sfavorita pre-match) + check `score` `engine.py:910-923` (favorita avanti) | - | CONF | |
| Minuto dal 55' (SPEC:27; F1: 55-62') | `minute_check` `engine.py:849-858`, `>=` senza tetto | `minuteMin 55` `engine.py:191` | DIV (soglia aperta) | DECISA 14/09 (SPEC:8-13) e 13/09 (CERT_13 par.6.1). Conseguenza non discussa: nessuna guardia impedisce un ingresso DOPO il minuto di uscita (80'): `grep exit_minute` in `engine.py`/`bot_service.py` = 0 |
| Punteggio 1-0/2-1/2-0 (SPEC:28) | `engine.py:910-923` orientato sulla favorita | `engine.py:192` | CONF | |
| Favorita pre 1,40-1,80 / sfavorita 4-8 (SPEC:29-30) | `engine.py:925-956` su `pre_ko` congelato | `engine.py:193-196` | CONF | bande pendenti di decisione utente per scarsita' (HANDOFF_2026-09-16_SERA.md:160-161) |
| Quota di entrata 1,20-1,34 (SPEC:31, ambigua) | `favLive` = back live della FAVORITA `engine.py:959-968` | `engine.py:197-198` | CONF (Lettura A) | DECISA 14/09 (SPEC:167-168) |
| Quota di banca | nessun filtro (`dogLay` solo "disponibile" `engine.py:984-992`) | - | DIV | DECISA 13/09+14/09 "nessun limite" (SPEC:169-173). Reale: lay a 24,0 = 46 EUR di responsabilita' per 2 EUR |
| **Controllo del gioco alla favorita** (SPEC:32) | `control_check` `engine.py:793-815`, chiamato solo se `requireControl` `engine.py:901-904` | `requireControl: False` `engine.py:189` | **NON IMPL (spenta)** | Causa dichiarata: copertura del dato IPS (corner/cartellini) non misurata (RISCONTRO_CALCIO:44). CERT_13 par.6.5 la metteva fra le difformita' lasciate; SPEC:181-183 chiede riconferma una per una: **non trovo la riconferma**. Il bot misura la copertura in attivita' `copertura_controllo_gioco` (`bot_service.py:5700-5716`): numero non letto (DB vietato) |
| Dimensionamento ("100 EUR di responsabilita'") | stake fisso `engine.py:405-426`, `bot_service.py` riserva con `liability_of` | `laySize 2` (DB 16/09) | DIV | DECISA 13/09+14/09 (SPEC:174-178) |
| Uscita profitto: la favorita segna il 2 gol (SPEC:64) | `_decide_base` `exits.py:949-966`: `fav > fav_e` = QUALSIASI gol in piu' della favorita | - | CONF (lettura) | su ingresso a 2-0/2-1 il "2 gol" e' il 3: lettura "il gol successivo", ragionevole |
| Uscita a tempo 80'-83' "esci COMUNQUE" (SPEC:65) | `exits.py:962-964` decide `time`; poi `_model_gate` `bot_service.py:4107-4146` -> `decide_time_exit` `exits.py:426-535` | `base_exit_minute 80` `exits.py:69`; `hold_max_risk 0.02` `exits.py:115` | **DIV** | con P&L bloccato < 0 e P(perdita) <= 2% il bot TIENE fino al settlement. DECISA 13/09 (CERT_13 par.6.4, :372-375; origine: punto dell'utente del 10/09, COSTITUZIONE par.9.1:652-656) ma **non riconfermata** contro la SPEC (RISCONTRO_CALCIO:132-138) |
| Controllo passa alla sfavorita -> esci in pari (SPEC:66) | `_controllo_perso` `exits.py:925-946` | `base_control_exit: False` `exits.py:78` | NON IMPL (spenta) | stessa causa del controllo in ingresso |
| Perdita: la sfavorita pareggia -> subito (SPEC:69) | `exits.py:951-952` (`fav <= dog`, prima condizione), kind `loss` fuori dal modello (`PROFIT_KINDS` `exits.py:128`), urgente `bot_service.py:3334` | - | CONF | |
| Attendi 20-60 s (SPEC:71) | `_after` `exits.py:905-909` | `loss_settle_delay_s 30` `exits.py:72` | CONF | |
| Rosso alla favorita -> esci nel 90% (SPEC:73) | `exits.py:955-956` | `red_card_fav_exit True` `exits.py:73` | CONF (piu' prudente: 100%) | rosso alla sfavorita neutro: nessun ramo, CONF |
| Perdita tipica 8-12% | nessun controllo | - | n/a | descrittiva, conseguenza dello stake fisso (SPEC:176-178) |
| (aggiunta) Nessun rosso alla favorita all'ingresso | `engine.py:972-982` | solo se il dato c'e' | AGG (restringe) | |
| (aggiunta) Punteggio stabile >= 30 s | `_score_confirm_check` `engine.py:875-882` | `scoreConfirmSec 30` `engine.py:199` | AGG (restringe) | |

### 3.2 RISULTATO ESATTO - lay "Altro risultato Casa/Ospite" (SPEC par.2, righe 78-96)

| regola (fonte) | implementazione | parametro | esito | decisione / nota |
|---|---|---|---|---|
| Lay su CORRECT_SCORE "Any Other" (SPEC:80) | `engine.py:1055-1099` prezzo = SOLO il lay | - | CONF | regex solo inglese nello scanner (RISCONTRO_CALCIO:91), segnalata |
| Minuto dal 48' (SPEC:85; F1 48-50') | `engine.py:1021` | `engine.py:204` | DIV (soglia aperta) | DECISA 14/09. Con uscita a 72' un ingresso nuovo dopo il 72' e' possibile se cambia il punteggio (chiave segnale per punteggio, `engine.py:1492-1497`): la banda 30-70 lo rende raro, nessuna guardia lo vieta |
| Punteggio 0-0/1-0/1-1/2-1 (SPEC:86) | `score_in_list_any_order` `engine.py:1043-1048` | `engine.py:205` | CONF | |
| Si banca chi ha segnato <= 1 gol (SPEC:87) | `engine.py:1049-1054` | `maxGoalsLaySide 1` | CONF | |
| Quota 30-70 (SPEC:88) | `engine.py:1068-1079` | `engine.py:207-208` | CONF | |
| **Controllo INVERTITO: la bancata NON deve averlo** (SPEC:89) | `engine.py:1022-1027` `deve_avere=False` sul lato bancato | `requireControl False` `engine.py:202` | **NON IMPL (spenta)** | stessa causa della BASE. A 0-0 i due lati passano: sceglie l'ordinamento della chiave (`engine.py:1587`) -> "away", arbitrario (RISCONTRO_CALCIO:89) |
| Selezione aggiuntiva: scontri diretti senza troppi 2-2/3-3, difesa solida (SPEC:90) | `selection_check` `engine.py:818-846`, `selezione.py` | `requireSelection False`, soglie 0,12 / 1,37 `engine.py:219-227` | **NON IMPL (spenta)** | implementazione ORDINATA 16/09 (COSTITUZIONE par.2.1:177); soglie NON nella SPEC, misurate sull'atlante; accensione e soglie **pendenti di decisione utente** (HANDOFF_2026-09-16_SERA.md:160) |
| Un solo lato per partita | `_esatto_gia_su_evento` `bot_service.py:5760`, guardia `bot_service.py:5918-5931` | - | CONF (lettura del singolare) | CERT_13 par.4.1 |
| Uscita profitto: esci comunque entro 70-75' (SPEC:92) | `exits.py:972-974` + `_model_gate` | `esatto_exit_minute 72` `exits.py:70` | **DIV** (stessa del 3.1) | DECISA 13/09, non riconfermata |
| Perdita: la bancata segna -> esci (SPEC:94) | `exits.py:968-971` | ritardo 30 s | CONF | |
| Dimensionamento | stake fisso | `laySize 2` -> fino a 138 EUR di responsabilita' a quota 70 | DIV | DECISA |

### 3.3 VARIANTE PUNTA - back della favorita avanti di 2 (SPEC par.4, righe 128-148)

| regola | implementazione | parametro | esito | nota |
|---|---|---|---|---|
| Back 1X2 sulla favorita in vantaggio (SPEC:130) | `engine.py:1102-1204`, `leadFav` `engine.py:1133-1152` | - | CONF | |
| Minuto dal 66' (F1 66-70') | `engine.py:1111` | `engine.py:232` | DIV (soglia) | DECISA 14/09 |
| Punteggio 2-0/3-1/3-0 | `engine.py:1118-1130` | `engine.py:233` | CONF | |
| Quota 1,03-1,10 | `engine.py:1167-1178` | `engine.py:234-235` | CONF | |
| Aspetta 3-4' dopo il gol | `settled` `engine.py:1180-1190` | `minMinutesAfterGoal 3` `engine.py:236` | CONF | |
| **La favorita deve continuare a spingere** | `engine.py:1112-1116` | `requireControl False` `engine.py:230` | **NON IMPL (spenta)** | stessa causa |
| Profitto: arriva il gol successivo -> cashout | `exits.py:982-983` | - | CONF | passa dal modello (kind `profit`): con P&L >= 0 esce (`exits.py:477-478`) |
| Profitto: entro l'83' | `exits.py:984-986` + `_model_gate` | `punta_exit_minute 83` | DIV (stessa del 3.1) | DECISA 13/09, non riconfermata |
| Perdita: QUALSIASI gol subito -> esci IMMEDIATAMENTE | `exits.py:980-981` (prima condizione) | +30 s di assestamento | DIV minore | "immediatamente" vs +30 s: motivo tecnico (mercato sospeso), dentro i 20-60 s concessi alla BASE (RISCONTRO_CALCIO:103). **Nessuna decisione esplicita dell'utente trovata** |
| (aggiunta) nessun rosso a chi si punta | `engine.py:1154-1164` | solo con dato | AGG (restringe) | |
| Osservabilita' | - | - | - | PUNTA: **zero segnali in tutto il corpus di 39 registrazioni** (PIANO_CERT:572-573) |

### 3.4 Trasversali calcio

| regola | implementazione | esito | nota |
|---|---|---|---|
| Disciplina: la perdita si esce SUBITO (SPEC:161-162) | `loss`/`red_card`/`mandatory` fuori da `PROFIT_KINDS` (`exits.py:128`), urgenti (`bot_service.py:3334`) | CONF | |
| Modalita' per strategia | `modalita_di_strategia` `bot_service.py:393-...`, default `strategy_modes {}` `bot_service.py:140` | AGG (impianto) | DECISA 14/09 |
| Gate spread lay/back <= 1,6 | `bot_service.py:5989` | AGG (restringe) | |
| Liquidita' >= stake | `bot_service.py:6017` | AGG (restringe) | |
| FOK in ingresso | `execution.place` (banco T2) | AGG (restringe) | un ingresso non abbinato e' perso |
| Tetti di rischio (evento 150 EUR/3 trade, stop -50) | `risk.py:39-43`, `_risk_gate` `bot_service.py:6029` | AGG | tetti giornalieri spenti per DECISIONE 14/09 (SESSIONE_LIVE_TENNIS:20-21) |
| Rientro dopo un'uscita | chiave segnale = evento+variante+lato+PUNTEGGIO (`engine.py:1424-1426`, `1492-1497`): nuova situazione = nuovo ingresso possibile | **AGG (non nella strategia, non decisa)** | la strategia descrive UN ingresso; il codice rientra a ogni punteggio nuovo che soddisfi le condizioni |
| Filtro campionati (video "Competizioni da evitare", "Migliori campionati") | nessuno | NON VERIFICABILE | video non trascritti (par.1.2) |

---

## 4. TENNIS - regola per regola (SPEC par.3, righe 100-124)

| regola (fonte) | implementazione | parametro | esito | decisione / nota |
|---|---|---|---|---|
| Punta chi vince OPPURE banca chi perde, "equivalenti" (SPEC:102-103) | solo BACK sul leader `engine.py:1229-1376` (`side="BACK"` `engine.py:1367`) | - | CONF (una delle due vie) | CERT_13 par.6.6 |
| Lay 1,18-1,34 (SPEC:109) | non implementata | - | NON IMPL | CERT_13 par.6.6 (lasciata, "incompatibile" con back ~1,03). Coerente con la scelta del solo back |
| 1 set vinto + 2-3 game nel 2 (SPEC:107) | `sets` `engine.py:1267-1281` (`abs(diff) >= setsLeadMin`), `games` stesso giocatore `engine.py:1283-1309`, `setsPlayed <= 1` `engine.py:1323-1329` | `setsLeadMin 1`, `gamesLeadMin 2`, `setsPlayedMax 1` `engine.py:239-252` | CONF | nessun tetto a 3 game (il riassunto dice 2-3: 4-0/5-0 entrano). Minore |
| Quota back ~1,03 (SPEC:108; esempio F1: 1,05) | `odds` `engine.py:1343-1365` | **`backMin 1.01`, `backMax 1.10`** `engine.py:241-242` | **DIV** | banda 1,01-1,10 = lettura degli sviluppatori (RISCONTRO_TENNIS:16 "il manuale da' un ordine di grandezza"). **Nessuna decisione dell'utente trovata.** Effetto: ingressi a 1,01-1,02 (guadagno max 1-2% contro rischio 100% dello stake) che poi NON possono fare take profit (sotto 1,03, riga sotto) e vanno a fine partita |
| Capitale ~200 EUR | stake fisso per strategia `engine.py:405-426` | `backSize 3` (DB 16/09) | DIV | DECISA (stake fisso 13-14/09; B.5 16/09) |
| Da evitare: doppi | `engine.py:1236-1245` | `excludeDoubles True` | CONF | euristica "/" nel nome |
| Da evitare: Slam maschili bo5 (SPEC:124) | `detect_best_of` `engine.py:768-783`, check `engine.py:1311-1319` | `excludeBestOf5 True` | CONF | senza nome competizione -> n/d, nessun ingresso |
| Da evitare: finali | nessun codice | - | NON IMPL | causa dichiarata: Betfair non pubblica il turno (399 mercati, RISCONTRO_TENNIS:21); **decisione utente pendente** (RISCONTRO_TENNIS:65) |
| Da evitare: match troppo equilibrati, sfavoriti estremi | nessun dato pre-partita nel contesto tennis (`TennisMatchCtx` `engine.py:528-541`: niente quote pre-match) | - | **NON IMPL** | RISCONTRO_TENNIS:22-23 li dichiara "conformi per costruzione" (banda live). **Non concordo**: la banda LIVE 1,01-1,10 non dice nulla sull'equilibrio o sullo sfavorito PRE-partita (un sfavorito a 5,0 che vince 6-4 3-0 entra). Deriva non decisa |
| Profitto: chi vince prende il game successivo -> cashout (SPEC:115) | `_decide_tennis` `exits.py:1004-1011` | `tennis_take_profit_next_game True` `exits.py:80` | DIV minore | (a) scatta a QUALSIASI game vinto dopo l'ingresso (`last_game == "won"`), anche dopo un game perso, non solo "il successivo"; (b) sotto quota d'ingresso 1,03 NON scatta (`tennis_take_profit_min_odds 1.03` `exits.py:91`); (c) passa dal modello e richiede >= 0,01 EUR bloccati (`bot_service.py:4131-4146`). (b)(c) = regole del 14/09 (RISCONTRO_TENNIS:45-46), misurate, restrittive; nessuna decisione esplicita dell'utente trovata, ma coerenti con la via "aspetta la fine" della SPEC:116 |
| Profitto massimo: aspetta la fine (SPEC:116) | interruttore spento = si tiene | - | CONF | |
| Perdita: perde il game successivo -> uscita conservativa (SPEC:119) | `exits.py:1013-1014` | `tennis_exit_on_lost_game False` `exits.py:98` | DIV (facoltativa spenta) | **DECISA 17/09** (CRONOSTORIA.md:289 "uscita al singolo game perso: resta SPENTA") |
| **2 game di fila + pareggio nel set -> OBBLIGATORIA senza eccezioni** (SPEC:120) | `_track_tennis` `exits.py:789-860` (`set_lead_lost`), `_decide_tennis` `exits.py:995-1003` in AND; `mandatory` fuori dal modello (`exits.py:128`), urgente (`bot_service.py:3334`) | ritardo 0 | CONF nella logica | "vantaggio perso" invece di "parita' esatta": copre il 5-5 saltato dal feed, non allarga (CERT_13 R5) |
| ..."senza eccezioni" | **cancelletto** `bot_service.py:3597-3609`: con `tennis_exit_approval` acceso OGNI chiusura tennis, compresa la `mandatory`, diventa una PROPOSTA e aspetta la firma | default `False` `bot_service.py:149`; **`true` in DB** (FASE0:519,532; SESSIONE_LIVE_TENNIS:19) | **DIV (la piu' pesante del tennis)** | **DECISA 14/09** ("le chiusure gliele si PROPONE e le approva lui", `bot_service.py:141-148`). Il banco la dichiara (`certificazione_tennis.py:440-461` T7-APPROVAZIONE) |
| Perdite 5-25% | nessun controllo | - | n/a | descrittiva (stake fisso); il banco difende solo "un back non perde piu' dello stake" (`certificazione_tennis.py:464-496`) |
| Ritiro = perdita totale; guardare il match; operare coi profitti (SPEC:112,123-124) | nessuna uscita per infortunio (video "Uscita infortunio" non trascritto) | - | NON IMPL / NON VERIFICABILE | rischio dichiarato irriducibile (RISCONTRO_TENNIS:37); le esclusioni sono la mitigazione |
| (aggiunta) punteggio stabile >= 15 s | `engine.py:1331` | `scoreConfirmSec 15` | AGG (restringe) | |
| (aggiunta) un ingresso per partita | chiave = "set 1-0" (`engine.py:1524-1527`) con `setsPlayedMax 1` | - | AGG (restringe) | |
| Selezione (video "Match da evitare", "Parametri", "Orario") | solo doppi/bo5/lista competizioni vuota `engine.py:255` | - | NON VERIFICABILE | video non trascritti |

---

## 5. Cosa gira nel bot Safe e NON e' nella Strategia S

Tutto questo e' "IMPLEMENTATA MA NON NELLA STRATEGIA", ma oggi **non piazza da solo**:

| componente | file | stato oggi |
|---|---|---|
| Opportunita' a modello calcio (tempo x punteggio) | `opportunity.py` (1026 righe), `calibration.py` | solo PROPOSTE dal 17/09 (`bot_service.py:6376-6383`, `6529-6531`); `auto_trade_opportunities` non piazza piu' |
| Anomalie di quota | `anomaly.py:1-30` | solo proposte dal 18/09, ordine dell'utente (`bot_service.py:6532-6536`) |
| Combinazioni (dutch, stack O/U, cs_cover) | `combos.py:1-30` | solo proposte dal 18/09 (stesso punto); approvazione atomica `bot_service.py:2671-...` |
| Secondo motore tennis (modello) | `tennis_opportunity.py` | solo proposte; `auto_trade_tennis` NON governa la Strategia S tennis (SESSIONE_LIVE_TENNIS:23-38) |
| Decisione a modello sulle uscite in profitto/tempo | `exits.py:426-535`, `bot_service.py:4107-4146` | ATTIVA sulle 4 strategie: e' la divergenza par.3.1 riga "uscita a tempo" |
| Cancelletto approvazione chiusure tennis | `bot_service.py:3597-3609`, `4492-...` | ATTIVO in DB (16/09) |

Nessuna di queste altera gli INGRESSI delle quattro varianti; la decisione a modello e il
cancelletto alterano le USCITE.

---

## 6. VERDETTO da trader

### 6.1 Calcio: **PARZIALE**

I numeri del riassunto sono dentro il codice e difesi (B1-B8, E1-E5, P1-P5 del banco
sollecitati, zero violazioni). Ma il riassunto descrive una strategia DISCREZIONALE: il cuore
di tutte e tre le varianti e' "chi comanda la partita". Il bot oggi entra solo su prezzo,
punteggio e minuto. Divergenze in ordine di impatto sui soldi:

| # | divergenza | impatto | documentata dall'utente? |
|---|---|---|---|
| 1 | Stake fisso + quota di banca senza limite (BASE e ESATTO): responsabilita' 46-138 EUR per 2 EUR di stake; manuale "100 EUR di responsabilita'" | massimo: rapporto rischio/rendimento fino a 23:1 (BASE) e 69:1 (ESATTO a 70) | **SI'** 13/09 + 14/09 "argomento chiuso" (SPEC:169-178) |
| 2 | Uscite "esci comunque" a 80'/72'/83' filtrate dal modello: con perdita bloccata piccola e P(perdita) <= 2% si TIENE fino al settlement | trasforma una chiusura a costo noto in esposizione PIENA (liability intera) su un evento raro | **SI' il 13/09** (CERT_13 par.6.4), su un punto sollevato dall'utente il 10/09 (COSTITUZIONE par.9.1); **NON riconfermata** contro la SPEC come la SPEC stessa pretende (SPEC:181-183; RISCONTRO_CALCIO:138-159 "aspetta una parola dell'utente") |
| 3 | "Controllo del gioco" spento in ingresso (BASE, PUNTA, ESATTO invertito) e in uscita (BASE) | entra anche quando la favorita subisce (BASE) o quando la bancata domina (ESATTO): e' il filtro che la strategia usa per evitare le perdite | **NO come decisione**: spenta per causa-dato (copertura IPS non misurata); CERT_13 par.6.5 la lasciava, la SPEC chiede riconferma: **non trovata**. La copertura e' misurata dal bot in attivita' ma il numero non e' scritto in nessun documento |
| 4 | Minuti come soglia aperta, senza tetto e senza guardia "ingresso prima del minuto di uscita" | ingressi tardivi (esatto al 62'/64' osservati, CERT_13 par.6.1); in teoria ingresso dopo il minuto di uscita | **SI'** 13/09 + 14/09 (SPEC:8-13). La conseguenza "ingresso dopo l'uscita" **non e' stata discussa** |
| 5 | Rientro a ogni punteggio nuovo (chiave per situazione) | piu' esposizione per partita di quanta la strategia ne preveda | **NO** (deriva di progetto, mai portata all'utente per quanto trovo) |
| 6 | Selezione aggiuntiva ESATTO spenta | ingressi su partite che il manuale scarterebbe | parzialmente: implementazione ORDINATA 16/09, soglie e accensione **pendenti** (HANDOFF:160) |
| 7 | PUNTA: uscita +30 s invece di "immediatamente" | pochi tick su un back 1,03-1,10 | NO (scelta tecnica motivata) |
| 8 | Selezione campionati / flessibilita' pre-match dei video | ignoto | NON VERIFICABILE (video non trascritti) |

Nota operativa: con `variants = ["tennis"]` (DB 16/09) le tre varianti calcio non giravano
affatto; con le bande del manuale la BASE e' attivabile su ~1 partita su 8 e la PUNTA mai nel
corpus (PIANO_CERT:571-574): anche dove e' fedele, la strategia calcio non e' mai stata
osservata operare sulle sue uscite nel banco del 23/09 (par.7).

### 6.2 Tennis: **PARZIALE** (piu' vicino alla strategia del calcio)

| # | divergenza | impatto | documentata dall'utente? |
|---|---|---|---|
| 1 | Uscita OBBLIGATORIA soggetta a firma umana (cancelletto acceso in DB) | se nessuno firma, la posizione va a fine partita con lo stake intero a rischio; lo scenario `mai-approvata` del banco lo mostra | **SI'** 14/09 (bot_service.py:141-148; SESSIONE_LIVE_TENNIS:19) |
| 2 | Banda d'ingresso 1,01-1,10 invece di "~1,03" + nessun take profit sotto 1,03 | ingressi a 1,01-1,02: rischio 100% per 1-2% di guadagno, protetti SOLO dall'uscita obbligatoria (che a sua volta aspetta la firma, #1) | **NO**: lettura dei delegati del 14/09 (RISCONTRO_TENNIS:16, 45); non trovo una decisione dell'utente |
| 3 | "Match equilibrati / sfavoriti estremi" non filtrati (manca il dato pre-partita) | ingressi su sfavoriti pre-partita avanti, il caso piu' esposto a rimonta | **NO** (il riscontro 14/09 lo dichiarava conforme "per costruzione": non lo e') |
| 4 | Finali non escluse | rischio fisico/emotivo in finale | pendente: causa-dato, euristica da decidere (RISCONTRO_TENNIS:65) |
| 5 | Take profit a qualsiasi game vinto (non solo il successivo), con minimo 0,01 EUR bloccato e passaggio dal modello | piccolo | NO esplicita; restrittiva |
| 6 | Uscita al singolo game perso spenta | la strategia la dava facoltativa | **SI'** 17/09 (CRONOSTORIA.md:289) |
| 7 | Solo back, niente lay 1,18-1,34 | nessuno (vie equivalenti) | SI' (CERT_13 par.6.6, lasciata) |
| 8 | Infortunio/ritiro, orario, parametri di selezione dei video | ignoto | NON VERIFICABILE |

Le modifiche alle strategie le decide l'utente: qui NON propongo correzioni.

---

## 7. Il banco: che cosa certifica e che cosa ha visto il 23/09

- **Controlli calcio** (`Betfair/safe_strategy/certificazione.py`): B1-B17 (par.1), E1-E10 (par.2),
  P1-P10 (par.4), T1-T14 trasversali, J1-J7 catalogo; le costanti della SPEC sono scritte nel
  controllo (`certificazione.py:62-86`), non lette dai parametri. Famiglie K (`certificazione_k.py`),
  CP (chiusura abbinata in parte) e PM (proposte) sono di ESECUZIONE, non di strategia.
- **Controlli tennis** (`certificazione_tennis.py`): T1-T13, T7-APPROVAZIONE, T8-DICHIARATA,
  J1-J5, L1-L2, S1-S4, C1, A1 + K/CP/PM.
- **Attenzione, il banco certifica la deviazione #2 del calcio, non la SPEC**: B14/E8/P9
  guardano solo che `exits.decide` produca una decisione oltre il minuto
  (`certificazione.py:515-531`, `722-735`), non che la posizione venga CHIUSA; T4
  (`certificazione.py:1076-1087`) pretende al contrario che il trattenimento a modello sia
  ACCESO. Un HOLD fino al settlement al 90' e' quindi "conforme" per il banco.
- **Referti del 23/09 (c3h, letti oggi da scratchpad della sessione)**:
  - Safe calcio 19 OK + 2 KO (PM6, T13: esecuzione/proposte, non strategia). **Tutti e tre i
    bot girano sulla sola 35760084**, che non produce segnali (BASE scartata per favPre/dogPre
    x3036). Sollecitati: B1-B2, B4-B8, B11, E1-E3, E5, E7, E10 (x6072, scenario
    `selezione-aggiuntiva`), P1-P5. **Mai sollecitati (x0, "non lo so")**: B3, B9, B10,
    B12-B17, E4, E6, E8, E9, P6-P10. Cioe' **nessuna uscita di strategia calcio e' stata
    esercitata il 23/09**; l'ultima volta che lo sono state e' il 16/09 su 35797769 e sulle
    sintetiche (PIANO_CERT:568-570: B3/B9/B12-B16 e P7-P10 sollecitati, 0 violazioni).
  - Safe tennis 34 OK + 2 KO (35794049+35790089). **Mai sollecitati: T1-T6, T10, T11, L2, CP2**:
    su queste due partite la Strategia S tennis non entra mai da sola; le posizioni sono
    INIETTATE dal replay ("i controlli T1-T4, T11 sull'ingresso NON valgono su questa riga").
    T7 x119, T7-APPROVAZIONE x77. I 2 KO (`approvata-subito`, `mai-approvata`) = uscita
    obbligatoria ferma in attesa di firma (decisione 14/09) + marcatore `exit_hold` rimasto
    sulla riga (reperto 2 del 23/09, CRONOSTORIA.md:2034-2036).

---

## 8. Cosa NON ho potuto verificare

1. Il contenuto dei VIDEO (nessuna trascrizione; non li ho trascritti: sarebbe un processo nuovo).
2. I parametri in DB di OGGI (divieto di DB): uso la fotografia del 16/09.
3. La copertura misurata del dato "controllo del gioco" (attivita' `copertura_controllo_gioco` nel DB).
4. Se l'utente abbia riconfermato a voce la decisione 13/09 sulle uscite a tempo o la banda
   tennis 1,01-1,10: nei documenti del repo non c'e'.
5. Non ho rilanciato replay (niente processi): i numeri del par.7 vengono dai referti c3h del 23/09.
6. `SPEC_STRATEGIA_S.md` non e' versionato: l'ho letto dal checkout principale; se venisse
   perso, il banco citerebbe una specifica che non esiste.
