# CANTIERE 6 — Banco tennis: nomi dei giocatori e scenario `gate-aperto` (08/10/2026)

Delegato di costruzione, sessione cloud. Worktree
`/home/user/python-database-automation/.claude/worktrees/agent-a252c7e9b965db784`, cima di partenza
`f0f14f6` (ramo `claude/blissful-sagan-hri7o6`, contiene `b5547eb` «regola del mercato che
attraversa», W2 `5cc7103` e cantiere 5 `f0f14f6`). Nessun commit. Specifica:
`AUDIT_2026-10-08/SPECIFICHE_CANTIERI_CLOUD_2026-10-08.md` §0 + CANTIERE 6.

**Limite del container, detto subito**: qui NON ci sono registrazioni tennis (35790089, 35794049
stanno sul PC in `tennis_rec`). Nessun replay tennis e' stato eseguito: le parti del banco tennis
sono provate con test unitari/di contratto sulla CLASSE DI PRODUZIONE del bot e su `certifica.main`
(stesso schema di `test_certifica_esito_dichiarate_2026_09_17.py`); i replay prima/dopo sono
PREPARATI in §7 con comandi e righe attese. La parte generica di `certifica` e' provata qui con un
replay CALCIO vero prima/dopo (§6: 0 righe diverse).

## 1. Che cosa c'era davvero (causa)

- (a) Il banco tennis leggeva GIA' `_names.json`, ma solo da `--data-dir` cosi' com'era
  (`replay_bot.catalogo_dichiarato`): `certifica` non risolveva la cartella della partita (con
  `--data-dir` sulla radice o senza `--data-dir` e la partita in un altro giorno: «registrazione
  assente», BANCO-ESPLOSO). Sui referti della 35794049 il catalogo c'era («Sinner, Struff»); sulla
  35790089 no, ed era detto solo in una nota per scenario («catalogo NON disponibile»): niente in
  testa, e NESSUN controllo del banco guardava i setup che dipendono dai nomi (fade, set
  transition, break point, serving for set, double break): «certificati» senza un controllo.
- (b) `gate-aperto` dichiara in nota «numeri che l'utente puo' gia' cambiare dalla UI», ma
  confrontato col catalogo vero (`parametri_modificabili`) NON e' vero per tutte le chiavi
  (misura §5). Gli altri scenari coi gate (`live`, `rifiuti-betfair`, CP, `chiudi-ora`,
  `uscite-manuali*`, `soldi-veri*`) riusano ESATTAMENTE quei parametri (`parametri_scenario`), solo
  `parziali` cambia lo stake: nessun altro insieme esiste.
- (c) Il silenzio sulla 35790089: vedi (a).

## 2. Cosa ho cambiato (file:riga, diff non committato)

- `Betfair/stream/backtest/certifica.py`
  - `:393-471` nuove `cartelle_degli_eventi` (tennis: per ogni partita la cartella di
    `applica_bot.risolvi_cartella_tennis`, con `--data-dir` cosi' com'e' chiesto; calcio: `data_dir`
    come sempre), `intestazione_del_bot` (righe di testa dichiarate dal modulo di replay del bot,
    `intestazione_certifica`; un modulo che non la ha non aggiunge nulla),
    `non_esercitabili_di_tutti` (NE solo se TUTTI i referti del giro lo dichiarano).
  - `:862-868` verdetti per cartella; `:915-924` righe di testa (cartella se diversa, errori di
    risoluzione, testa del bot); `:968-969` i compiti usano la cartella della partita;
    `:1089-1109` copertura: segno `NE` per i non esercitabili, esclusi da «MAI SOLLECITATI»;
    famiglie IN PIU' del bot (`famiglie_del_bot` del modulo controlli); `:1162-1167` sezione
    «NE NON ESERCITABILI ... causa misurata».
- `Betfair/stream/tennis_live/tools/replay_bot.py`
  - `:259-373` scenari `pro-fade-dopo-break`, `pro-transizione-di-set`, `pro-break-point`
    (`SCENARI_SETUP_PRO`, nessun parametro cambiato), `CONTROLLO_DEL_SETUP` (SP1/SP2/SP3),
    `SCENARI_DESCRITTI_PRO`, `scenari_del_bot`, `SOGLIE_FUORI_CATALOGO` (le chiavi di `gate-aperto`
    fuori dal catalogo, dichiarate con lo stato misurato sull'istanza), `descrivi_parametri_scenario`,
    `intestazione_certifica` (testa: «nomi dei giocatori <ev>: PRESENTI (...) / ASSENTI (causa):
    setup ... NON ESERCITABILI», «parametri cambiati dallo scenario: ...»).
  - `:574-660` lettura di `_names.json`: forma piatta di sempre + chiave RISERVATA `"_mercati"`
    del cantiere 14 (ignorata come event_id; usata SOLO come ripiego per il MATCH_ODDS del bot se
    manca la chiave piatta, mai un altro mercato); `stato_nomi` per la testa.
  - `:849-851`, `:931-933`, `:1216-1217`, `:1597-1600`: il ponte di `tennis_pro` monta il metro
    `LettoreSetupPro` con lo STESSO catalogo del bot, gli passa lo STESSO campione IPS che passa al
    bot e porta la lettura nell'`Osservazione` (`setup_pro`).
  - `:1440` `catalogo_dichiarato(..., market_id=...)`; `:1694-1718` `chiudi_setup_pro`: a fine
    replay del pro i controlli SP mai sollecitati diventano NON ESERCITABILI con la causa (nomi
    assenti / zero occasioni misurate); negli scenari di setup il controllo-chiave a zero rende lo
    scenario NE con la causa (con occasioni ma senza ingresso: «NON LO SO», resta `??`).
  - `:1835` `main` del modulo: `--scenari tutti` usa gli scenari del bot.
- `Betfair/stream/tennis_live/certificazione_bot.py`
  - `:164-168` `Osservazione.setup_pro`; `:181-192` registro SUO della famiglia SP (i referti di
    scalper/flb/swing non cambiano: stessa tabella, stesso «controlli attivi: 22»).
  - `:1233-1584` FAMIGLIA SP: `SETUP_CON_NOMI`, `SETUP_CERTIFICATI`, `selezione_del_nome` (regole
    del bot calcolate dal banco: nome, cognome unico, prefisso unico per l'IPS troncato),
    `e_break_point` (spec del setup 1: 0-40/15-40, game normale), `favoriti`, `LettoreSetupPro`
    (break di ogni set = game vinto da chi non serviva nel campione prima; set vinti; occasioni),
    `esito_setup`, controlli **SP1** fade (BACK del favorito, <= `fade_max_game` game, DOPO un break
    subito da lui nel set), **SP2** set transition (sul vincitore dell'ultimo set, entro
    `st_window_games`), **SP3** break point (BACK, 0-40/15-40, chi serve su grass/fast, chi riceve
    altrove). Soglie lette dall'istanza di produzione.
  - `:1590-1595` `verifica` fa girare SP solo con la lettura del banco; `:1630-1645`
    `elenco_controlli_setup`, `famiglie_del_bot`; `:1668-1675` `Referto.non_esercitato`,
    `Referto.non_esercitabili` (stesse chiavi che `certifica` gia' legge per Mike/scalper).
- `Betfair/stream/backtest/registro_bot.py:368-370` tennis_pro -> `SCENARI_DESCRITTI_PRO`.
- `Betfair/stream/backtest/applica_bot.py:232-236` i tre scenari di setup fra gli SCARTATI di
  «Applica bot» (sono `base` col controllo-chiave): il catalogo TS del frontend NON cambia
  (`test_applica_bot_tutti` verde).
- Nuovo test `Betfair/stream/tennis_live/tests/test_cantiere6_nomi_setup_gate_2026_10_08.py`
  (46 test).
- Nuovi file di referto in `AUDIT_2026-10-08/cantiere_6/`.

Perimetro: tutti file nominati dal cantiere 6 (`certifica`, `registro_bot`, `replay_bot`, banco
tennis `certificazione_bot`, `applica_bot` per la classificazione degli scenari). `applica_bot.py`
e' toccato in 5 righe additive (possibile conflitto banale con altri cantieri che lo toccano).
Nessuna strategia toccata: nessun file di bot cambiato.

## 3. Test e falsificazione

Comando: `python3 -m pytest Betfair/stream/tennis_live/tests/test_cantiere6_nomi_setup_gate_2026_10_08.py -q -p no:cacheprovider`
-> **46 passed** (4-6 s, macchina carica).

Test collegati (prima della suite intera): `pytest Betfair/stream/tennis_live/tests` +
`test_registro_bot`, `test_applica_bot_tutti`, `test_applica_bot_2026_10_06`,
`test_applica_bot_cartelle_tennis`, `test_certifica_esito_dichiarate`, `test_cert_banco`,
`test_chiusura_parziale`, `test_banco_uscite_manuali_n3`, `test_banco_uscite_dichiarate_n3`,
`test_cantiere_v_replay_veloce`, `test_registro_impronta` -> **1452 passed, 26 skipped, 5 xfailed**
(146,6 s, sul codice finale; `test_collegati_DOPO.txt`).

Suite intera: §8.

Falsificazione (`scratchpad/c6_falsifica.py`, esito in `falsificazione.txt`): 15 mutazioni, tutte
ROSSE; ripristino verificato con sha256 (identico) e `git diff --stat` identico, `MUTAZIONE` = 0:

| mutazione | rossi |
|---|---|
| M1 certifica non risolve la cartella della partita | 1 |
| M2 nessun ripiego su `_mercati` | 1 |
| M3 `_mercati` letto con un mercato qualsiasi | 1 |
| M4 `price_min` del pro non dichiarato | 2 |
| M5 gate-aperto tocca una soglia di strategia (`fade_jump_ticks`) | 2 |
| M6 SP1 senza la verifica del break | 1 |
| M7 SP3 accetta i punti del tie-break | 2 |
| M8 SP3 superficie invertita | 3 |
| M9 il metro attribuisce il break a chi VINCE il game | 1 |
| M10 NE se UN referto lo dichiara (unione al posto dell'intersezione) | 1 |
| M11 NON ESERCITATO anche negli scenari non di setup | 1 |
| M12 famiglia SP accesa senza la lettura del banco | 1 (alla prima prova sopravviveva: c'erano due guardie equivalenti, ne ho tolta una e ora e' rossa) |
| M13 testa muta sui nomi assenti | 2 |
| M14 `compressed_fav` fra i setup coi nomi | 2 |
| M15 favorito letto come il prezzo piu' alto | 3 |

sha256 al ripristino (codice finale): `certificazione_bot.py` eb06d0c5...feca7ac, `replay_bot.py`
0d4b40f9...b3f548c7d83, `certifica.py` dc7f2f13...530c3252da.

I finti: record IPS con le chiavi del sidecar vero passati a `parse_tennis_scores`; book con gli
attributi del `MarketBook` di flumine (`ex.available_to_back` lista di `{price,size}`, letti con
`flumine.utils.get_price`); raw con le righe `mcm` del registratore; `_names.json` nella forma dei
grid runner + `"_mercati"` come la scrive il cantiere 14 (`tennis_recorder.scrivi_nomi_catalogo`,
riletto nel suo worktree). Il bot e' la classe di produzione `TennisProStrategy`.

## 4. La famiglia SP sul bot vero (prova di coerenza bot / banco)

Con la classe di produzione (un setup acceso per volta, nel TEST): fade, set transition e break
point (grass e hard) scattano e i controlli SP sono **sollecitati e verdi**; spostando l'ingresso
sul giocatore sbagliato SP1/SP2/SP3 diventano rossi. Ogni setup di `SETUP_CON_NOMI` scatta coi nomi
e NON senza; `compressed_fav` scatta anche senza nomi.

**Reperto (sonda `sonda_tiebreak_break_point.txt`)**: nel TIE-BREAK il bot entra in `break_point`
su 0-3 e 1-3 del ribattitore (`_point_rank` legge «1» come «15» e «3» come «40»); la spec del setup 1
dice «0-40/15-40». SP3 lo segna. Non corretto (e' la strategia): vedi «Decisioni per l'utente».

## 5. `gate-aperto`: i parametri, misurati sull'istanza vera

| bot | chiavi cambiate | FUORI dal catalogo della UI (dichiarate in `SOGLIE_FUORI_CATALOGO`) |
|---|---|---|
| tennis_scalper | inplay_tick_enabled, min_flow, min_matched, min_size, min_total_matched, price_max, price_min, runner_filter, warmup_ms | min_matched (il bot NON la legge), min_total_matched (gia' 0), warmup_ms 30000 -> 0 |
| tennis_pro | min_book_size, min_matched, min_total_matched, price_max, price_min | min_book_size 10 -> 0, min_total_matched (non letta), price_min 1,08 -> 1,01 |
| tennis_flb | lay_max, min_lay_size, min_matched, min_total_matched | min_lay_size 5 -> 0, min_total_matched (non letta) |
| tennis_swing | conf_ticks, er_max, min_matched, min_total_matched, price_max, price_min, zin | conf_ticks 2 -> 1, min_matched 10000 -> 0, min_total_matched (non letta), price_max 8 -> 30, price_min 1,08 -> 1,01 |

Contratto (test): (1) le chiavi di `gate-aperto` stanno nel catalogo (`parametri_modificabili`) o
fra le dichiarate, e le dichiarate sono ESATTAMENTE quelle fuori catalogo (nessuna vecchia); (2) mai
`stake`, `dry_run`, blindature .it, `uscite_automatiche`, tetti, `enable_*`; (3) le cause dichiarate
sono vere sull'istanza di `_instantiate_bot`; (4) ogni altro scenario non cambia niente, o solo lo
stake (`parziali`), o porta ESATTAMENTE i gate di `gate-aperto`. Lo scenario NON e' stato cambiato
(cambierebbero i referti di tutti gli scenari coi gate): la scelta e' dell'utente.

## 6. Prova di non regressione eseguita QUI (calcio, parte generica di `certifica`)

`python3 -m Betfair.stream.backtest.certifica safe_base 35760084 --data-dir <scratchpad>/c6_live_raw --scenari base --worker 1`
(registrazione `registrazioni_banco/35760084` decompressa in scratchpad), PRIMA sulla cima
`f0f14f6` e DOPO sul worktree: `calcio_safe_base_PRIMA.txt` / `_DOPO.txt`, confronto con
`certifica.righe_senza_tempi` -> **216 righe contro 216, 0 differenze** (`diff_calcio_safe_base.txt`),
impronta del codice compresa (DOPO rifatto sul codice finale). Tempi: 65,7 s prima, 53,9 s dopo
(macchina con carico 9-15 su 4 CPU condivise con altri cantieri: rumore, non un guadagno).

## 7. DA RIESEGUIRE SUL PC (tennis): comandi e righe attese

PRIMA sulla cima senza il cantiere 6, DOPO col cantiere 6, uno alla volta, `--worker 1`:

```
set D=C:/Users/Admin/Desktop/tennis_rec/20260707
for %b in (tennis_scalper tennis_pro tennis_flb tennis_swing safe_tennis) do (
  python -m Betfair.stream.backtest.certifica %b 35790089 --data-dir %D% --scenari tutti --worker 1 > c6_%b_35790089_DOPO.txt
  python -m Betfair.stream.backtest.certifica %b 35794049 --data-dir %D% --scenari tutti --worker 1 > c6_%b_35794049_DOPO.txt )
python -c "import sys,difflib;from Betfair.stream.backtest.certifica import righe_senza_tempi as r;a=r(open(sys.argv[1]).read());b=r(open(sys.argv[2]).read());print('\n'.join(difflib.unified_diff(a,b,lineterm='',n=0)))" PRIMA.txt DOPO.txt
```

Righe diverse ATTESE (ogni altra riga diversa = cantiere fermo):
1. `controlli attivi: ... codice bot <hash>` cambia per i 4 bot di `replay_bot` (l'impronta legge
   `certificazione_bot.py`). Per `safe_tennis` NO: referto identico riga per riga (nessuna testa
   nuova, nessuna famiglia nuova).
2. Testa, nuove: `nomi dei giocatori: non usati da <bot> ...` (scalper/flb/swing) oppure, per il
   pro, `nomi dei giocatori 35790089: ASSENTI (<...>/_names.json non ha la partita 35790089): setup
   break_point, fade, set_transition, serving_for_set, double_break di tennis_pro NON ESERCITABILI
   (controlli SP1, SP2, SP3)` / `nomi dei giocatori 35794049: PRESENTI (Sinner, Struff) da ...`;
   poi `parametri cambiati dallo scenario ...` e una riga per scenario (`gate-aperto` con la parte
   «FUORI dal catalogo della UI (dichiarati): ...» di §5; `live`, `rifiuti-betfair`, ecc. «gli
   stessi di gate-aperto (...)»; `parziali: stake=400.0`; gli altri «nessuno»).
3. Solo tennis_pro: `SCENARI:` con i tre scenari nuovi in coda; tre blocchi di scenario nuovi
   (`pro-fade-dopo-break`, `pro-transizione-di-set`, `pro-break-point`) con la nota «LETTURA DEL
   BANCO ...»; nella copertura il blocco `-- controlli dei setup di tennis_pro ...` con SP1-SP3.
   - 35790089 (nomi assenti): i tre scenari nuovi escono **NE** con «SPn NON ESERCITABILE: nomi dei
     giocatori ASSENTI»; riga `NE: 3 scenari ...`; SP1-SP3 `NE x0` e la sezione «NE NON
     ESERCITABILI»; tick/decisioni/azioni dei tre scenari IDENTICI a `base` (stessi parametri).
     Gli scenari di prima: righe OK/KO, note, motivi e violazioni IDENTICI.
   - 35794049 (nomi presenti): tick/decisioni/azioni dei tre scenari nuovi identici a `base`; SP1-SP3
     sollecitati dove il pro fa quegli ingressi (numeri non prevedibili da qui). Ogni violazione SP
     e' un REPERTO sulla strategia (non una regressione): il candidato noto e' il break point nel
     tie-break (§4). Se uno SP resta a x0: NE con la causa misurata (zero occasioni) oppure `??` con
     «N occasioni ma nessun ingresso» (non lo so).
4. Righe ESITO del pro: i conteggi crescono di 3 scenari (17 -> 20 per registrazione).
Tempi attesi: pro +3 scenari ~ +3 x il tempo di `base` (35794049 ~7 s l'uno sul PC del 07/10);
gli altri bot invariati.

Prova extra suggerita (cartella risolta): `certifica tennis_pro 35794049 --scenari base` SENZA
`--data-dir` con `TENNIS_RECORD_DIR` sulla radice `tennis_rec`: deve trovare la partita e il suo
`_names.json` (riga «cartella della partita ...» se non e' il giorno piu' recente).

## 8. Comandi lanciati qui (esito vero)

- test nuovi: 46 passed; collegati: 1452 passed, 26 skipped, 5 xfailed (146,6 s);
- falsificazione: 15/15 rosse, ripristino sha256 identico;
- replay calcio prima/dopo: 0 righe diverse;
- suite intera `python3 -m pytest Betfair/ -q -p no:cacheprovider` (`suite_python_DOPO.txt`):
  **2 failed, 10938 passed, 65 skipped, 6 xfailed** in 722 s. I 2 rossi sono test di LATENZA
  (`test_auto_follow_2026_09_25::test_latenza_logica_aggancio_sotto_i_20_ms`,
  `test_motore_ordini_2026_09_24::test_latenza_logica_comando_place_sotto_20_ms`), file non toccati,
  con la macchina a carico 15 su 4 CPU: rilanciati da soli -> 2 passed. ATTENZIONE: la suite e'
  girata PRIMA dell'ultima pulizia ASCII (solo commenti/stringhe; durante la pulizia ho rotto e
  corretto una stringa di `certifica.py` riga 1165, preso dal test di collezione). Dopo la pulizia:
  compilazione dei 5 file, test collegati 1452 verdi, falsificazione rifatta, replay calcio rifatto.
  La suite intera NON e' stata rilanciata dopo la pulizia: va rifatta dal coordinatore.
- Frontend: nessun file toccato; `test_applica_bot_tutti` (allineamento del catalogo TS) verde.
  `tsc`/`vitest` NON lanciati (nessun file frontend nel diff).

## 9. Parita' paper/live

Nessun codice di bot o di esecuzione toccato: solo il banco. La famiglia SP gira uguale in tutti
gli scenari del pro, paper (`base`, `gate-aperto`, ...) e live (`live`, `soldi-veri*`).

## 10. Cosa NON ho fatto / NON ho potuto verificare

- Nessun replay tennis (registrazioni assenti qui): §7 va rifatto sul PC. Non so quanti ingressi
  fade / set transition / break point fa il pro sulla 35794049, ne' se SP1-SP3 trovano reperti li'.
- I nomi della 35790089 non esistono ne' nel `_names.json` del PC ne' nel DB: NON inventati, NON
  dedotti dall'IPS troncato (vietato dalla spec). Arriveranno col registratore del cantiere 14 per
  le partite registrate da ora in poi.
- Gli scenari di setup girano coi parametri di PRODUZIONE (scelta: certificare cio' che gira, non
  una variante; accendere un solo setup o aprire i gate sarebbe un banco «aperto» rispetto alla
  produzione, catalogo §7.31). Su una registrazione dove il pro non entra mai in quel setup lo
  scenario resta NE o `??`: e' la risposta vera.
- `serving_for_set` e `double_break` sono elencati come «non esercitabili senza nomi» ma NON hanno
  un controllo SP (la spec ne chiede tre).
- La costante `CHIAVE_MERCATI_NOMI = "_mercati"` e' duplicata in `replay_bot` (nel mio ramo
  `tennis_replay/convertitore.py` non l'ha ancora): dopo l'integrazione del cantiere 14 si puo'
  importare da li'.

## 11. Decisioni per l'utente

1. **Break point nel tie-break** (`tennis_pro_bot.py` `_point_rank` / `_is_break_point`): il bot
   entra in `break_point` anche su 0-3 / 1-3 del ribattitore nel tie-break, dove non c'e' un
   servizio da strappare (la spec dice 0-40/15-40). SP3 lo segnala. Proposta: decidere se il setup
   1 vale anche nel tie-break; se no, correzione del bot in un cantiere suo (cambia una decisione
   di trading).
2. **`gate-aperto` fuori dal catalogo della UI** (§5): oggi apre anche soglie che l'utente NON puo'
   cambiare dalla scheda (es. swing `conf_ticks`, `price_min`/`price_max`; pro `min_book_size`,
   `price_min`; flb `min_lay_size`; scalper `warmup_ms`). Le note dei referti dicono «numeri che
   l'utente puo' gia' cambiare dalla UI»: per queste chiavi non e' vero. Proposta: o si portano
   nella scheda/catalogo, o si tolgono dallo scenario (i referti di tutti gli scenari coi gate
   cambieranno: replay prima/dopo dedicato).

## 12. Da controllare dal vivo in paper

Niente di nuovo per i bot (il banco non gira in produzione). Al prossimo REC di una partita tennis
col registratore del cantiere 14: `_names.json` deve avere la partita; `certifica tennis_pro <ev>`
deve dire «PRESENTI».

## Blocco per la cronostoria

```
- CANTIERE 6 (banco tennis: nomi e gate-aperto) CONSEGNATO dal delegato, NON committato
  (worktree agent-a252c7e9b965db784, cima f0f14f6). `certifica` risolve la cartella di ogni partita
  tennis come Applica bot (`risolvi_cartella_tennis`) e passa il `_names.json` di quella cartella;
  testa del referto: «nomi dei giocatori <ev>: PRESENTI/ASSENTI (causa): setup ... NON
  ESERCITABILI» e «parametri cambiati dallo scenario». Lettura `_names.json`: forma piatta +
  chiave riservata `_mercati` del cantiere 14 (ignorata come evento, ripiego solo per il Match
  Odds). Famiglia SP nuova del banco (solo tennis_pro, metro `LettoreSetupPro` sul punteggio IPS):
  SP1 fade, SP2 set transition, SP3 break point; tre scenari nuovi del pro
  (`pro-fade-dopo-break`, `pro-transizione-di-set`, `pro-break-point`, parametri di produzione,
  controllo-chiave: NE con causa misurata se a zero); copertura `NE` per i controlli non
  esercitabili in tutti i referti. `gate-aperto`: contratto sui parametri (lista bianca =
  catalogo + soglie fuori catalogo DICHIARATE), scenario NON cambiato. Test nuovo 46 verdi,
  falsificazione 15/15 rosse; collegati 1452 verdi; suite 10938 verdi + 2 rossi di latenza
  (carico macchina, verdi da soli); replay calcio safe_base 35760084 prima/dopo 0 righe diverse.
  REPERTI per l'utente: break point nel tie-break (SP3), gate-aperto fuori catalogo UI.
  DA FARE SUL PC: replay dei 5 bot tennis su 35790089 e 35794049 `--scenari tutti --worker 1`
  prima/dopo (righe attese in AUDIT_2026-10-08/cantiere_6/REFERTO.md §7).
```

## Verifica del coordinatore cloud (08/10)
- Diff riletto (5 file, applicato pulito sulla cima con C12/C14/C15). Lettura di `_names.json` compatibile col cantiere 14 (`_mercati` mai
  trattata come partita). La costante `CHIAVE_MERCATI_NOMI` resta copiata in `replay_bot` (importare `convertitore` porterebbe
  dipendenze pesanti nel replay): aggiunto un test che la tiene uguale a quella del convertitore.
- Test: file del cantiere 47 verdi; `tennis_live` + `backtest` 970 verdi / 4 saltati / 5 xfail nel checkout integrato.
- MIE MUTAZIONI: M1 chiave riservata diversa -> 2 rossi; M2 SP3 senza controllo del punteggio -> 3 rossi; M3 SP3 senza controllo
  della selezione -> 1 rosso. Ripristino verificato.
- Decisione per l'utente (punto 1): il pro entra in `break_point` anche nel tie-break (0-3/1-3 per chi riceve): e' strategia, non toccata.
- Replay tennis prima/dopo: DA RIESEGUIRE SUL PC (§7).
