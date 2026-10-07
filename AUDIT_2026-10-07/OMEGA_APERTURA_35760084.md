# OMEGA NON APRE PIU' SULLA 35760084 - REGRESSIONE (07/10/2026)

Delegato del coordinatore, worktree
`/home/user/python-database-automation/.claude/worktrees/agent-aadcd5199a17dae8b`
(ramo `worktree-agent-aadcd5199a17dae8b`, base `8226d766`, lavoro NON committato).
Ambiente: cloud, Python 3.13, flumine 2.13.11, betfairlightweight 2.23.2, registrazioni in
`/home/user/python-database-automation/_live_raw`. Prove e strumenti:
`AUDIT_2026-10-07/omega_apertura_35760084/{replay,strumenti}/`.

## 0. In una riga

**REGRESSIONE del BOT (verdetto b), non del banco.** Dal commit `304a8e1d` (29/09, integrazione
del cantiere J2 «flusso dati interrotto») Omega e' **cieco per tutto il secondo tempo** quando non
ha una gamba aperta sull'Half Time Score: valuta il flusso dell'HT anche dopo l'intervallo, e
l'HT (che lo scanner smette di seguire al 44' e che si regola all'intervallo) resta «fermo» fino
al fischio. La gamba 2T non viene MAI valutata. Corretta in `Betfair/omega/omega_service.py` (+
una riga in `omega_proposte.py`): l'HT conta solo per le decisioni SULL'HT (gamba v2 1T, sue
chiusure, proposte, missioni) e solo in fase pre/1T; TDD + 8 mutazioni rosse. Con la prima
versione il replay `apertura` e' tornato identico al 25/09 (467 decisioni, 2 azioni, tick 482034,
read_market x108); la versione finale va rilanciata col via libera.

## 1. Il fatto e il commit che lo causa

| | 25/09 (referto) | 04/10 - 07/10 (prima) | 07/10 (dopo la correzione) |
|---|---|---|---|
| `35760084 [apertura]` | decisioni 467, azioni 2 | decisioni 438, azioni 0 | decisioni **467**, azioni **2** |
| tick | 482034 | 483985 | **482034** |
| chiamate al mercato | list x473, read_market x108 | list x444, read_market **x0** | list x473, read_market **x108** |
| gamba 2T | lay '3 - 3' @300 al 52', vinta, +5,00 | mai valutata | **lay '3 - 3' @300**, vinta, +5,00 |

Nota sulle «2 azioni»: il banco somma `placed + settled + greenup + missions`
(`Betfair/omega/tools/replay_registrazioni.py:1422-1424`): le 2 azioni del 25/09 sono **1 ordine
(gamba 2T) + il suo settlement**, NON due trade 1T + 2T. Lo dice anche il referto del 25/09
(«ordini reali piazzati su flumine: 1», «gambe aperte per fase: {'ft_cs': 1}»).

### 1.1 Commit di partenza (25/09)
Il referto `AUDIT_2026-09-25/strada_unica/omega_apertura_entrambi_v1.txt` dichiara
`codice bot 676085fa7cf9 (2 file)`. L'impronta del 25/09 era sha1(`omega_service.py` +
`certificazione.py`) (`registro_bot.py` di allora: `moduli_produzione=("Betfair.omega.omega_service",)`,
`certifica.py:225-253`), su file con fine riga CRLF (PC Windows). Ricalcolata su ogni commit
(`strumenti/trova_hash.py`): coincide su `baf42860`..`9cbfe763` (24/09 18:24 - 25/09 12:23); il
trasporto coda/canale nasce con `5139d2bc` (25/09 13:43). Replay su `5139d2bc` qui:
`OK 35760084 tick=482034 decisioni=467 azioni=2` (`replay/bisect_5139d2bc_25-09_buono.txt`):
il 25/09 e' riprodotto identico.

### 1.2 Ricerca binaria (repo clonato poco profondo: approfondito con `git fetch --deepen=500`)
Commit del primo genitore che toccano `Betfair/` fra `5139d2bc` e `4dd624af` (110), albero
estratto con `git archive` (nessun checkout), comando del brief, `--worker 1`, uno alla volta:

| commit | data | esito |
|---|---|---|
| `b206b1cd` | 28/09 22:34 | 467 / 2 BUONO |
| `a86b927c` | 30/09 17:14 | 438 / 0 |
| `2686136b` | 29/09 18:54 | 438 / 0 |
| `0acf3297` | 29/09 12:48 | 438 / 0 |
| `304a8e1d` | 29/09 07:43 | 438 / 0 **primo cattivo** |
| `82239dfc` | 28/09 22:55 | 467 / 2 ultimo buono |
| `4dd624af` / `8226d766` | 04/10 / 07/10 | 438 / 0 |

### 1.3 Bot o banco? Ibridi di `82239dfc` (buono) e `304a8e1d` (cattivo)
| albero | esito | dice |
|---|---|---|
| `304a8e1d` con il BANCO di prima (`Betfair/stream/backtest/**` da `82239dfc`) | 438 / 0 | **non e' il banco** |
| `82239dfc` + Omega nuovo + `flusso_prezzi.py` + `uscite_proposte.py` | 467 / 2 | Omega nuovo da solo non basta |
| idem + `scores/scan_feed.py` + `frammenti_mercato.py` | 467 / 2 | |
| idem + `safe_strategy/**` (lo SCANNER) + `stream_muto.py` + `riserva_prezzi.py` | **438 / 0** | serve lo scanner che scrive il blocco `flusso` |

Cioe': il veto di Omega (`_flusso_feed`) si accende solo quando lo scanner scrive il blocco
`flusso` (con lo scanner vecchio `valuta` torna «non noto» = nessun veto). Sono due meta' dello
stesso commit; l'errore e' nella meta' di Omega (sotto).

## 2. Causa radice (file:riga)

1. **Scanner, per progetto**: l'Half Time Score si segue solo dal 15' al 44'
   (`Betfair/safe_strategy/scanner.py:585-588` `is_ht_candidate`: `HT_MINUTE_FROM <= minute <
   HT_MINUTE_TO`, `:35-36`; `Betfair/safe_strategy/service.py:1185-1187`), salvo esposizione di un
   bot (`service.py:1188-1215`). Il blocco `ht` della riga resta con l'ultimo stato visto e il
   blocco `flusso` lo mette in `mercati_fermi` (escluso solo se CLOSED,
   `service.py:1050-1060` `_blocco_chiuso`).
2. **Omega, il difetto**: `omega_service._flusso_feed` (prima della correzione `:940-963`) passava
   a `flusso_prezzi.valuta` SEMPRE MATCH_ODDS + `cs` + `ht`. Con l'HT in `mercati_fermi`:
   `_feed_fresh_for_decision` falso (`:1069-1077` ora) -> `_live_state_for(..., decision=True)`
   senza payload (`:1087`) -> nessuno stato -> `skip no_live_state` (UNA volta: `_log_dedup` a 600 s
   di orologio vero) -> `return` prima del ciclo delle gambe: la gamba 2T non si valuta mai, il
   servizio va alla cadenza «a vuoto» (60 s: da qui 438 decisioni invece di 467 e i tick diversi).
3. **Prova sul replay** (`replay/sonda_HEAD3.txt`, sonda su `_flusso_feed` senza toccarne
   l'esito): dal 43' fino al fischio `vivo=False, motivo=mercato_fermo, mercati=('1.259475535',)`
   (l'HT); al 46'-80' il blocco `ht` e' `SUSPENDED`, MO `1.259475525` e CS `1.259475532` vivi.
   Registrazione (`strumenti/storia_mercato.py`): HT ultimo prezzo 16:45:24, SUSPENDED 16:46:25,
   CLOSED 16:47:58; CS e MO vivi fino alle 17:54.
4. **La regola che il cambio voleva applicare** (CRONOSTORIA 28/09, righe 3537-3542; brief §2
   punto 11): «se i prezzi di una partita non sono vivi nessun bot apre ne' chiude a mercato su
   QUEI prezzi». La gamba 2T decide su MATCH_ODDS e Correct Score, entrambi vivi: un HT ormai
   regolato non e' un prezzo su cui Omega decide (la gamba 1T si apre solo nella sua finestra,
   `ht_entry_max` 40 / `v3_ht_entry_max` 44; il green-up di una gamba 1T si ferma dopo il 45',
   `omega_service.py` `_greenup_one`: `if half and minute > 45: return False`). Nessuna riga di
   CRONOSTORIA, referto o decisione dell'utente dice che Omega debba smettere di operare nel
   secondo tempo: **non e' una scelta, e' un effetto non visto** (il referto del 29/09 diceva
   «Omega 13 OK» senza confrontare le azioni con il 25/09).
5. **Anche in produzione** (dedotto dal codice, non visto dal vivo): lo scanner vero toglie l'HT
   dai mercati voluti al 45' (`is_ht_candidate`), quindi la definizione CLOSED non gli arriva e
   il blocco resta all'ultimo stato -> stesso veto per tutto il 2T su ogni partita in cui Omega non
   ha una gamba 1T aperta (vale anche per il motore V3: `_flusso_feed` e' comune). Con una gamba
   1T aperta l'HT resta seguito fino al CLOSED (esposizione) e il 2T torna libero dopo il 47'-48'.

## 3. Correzione (perimetro `Betfair/omega/**`) - seconda versione, «per uso»

Prima versione (rivista dal coordinatore): l'HT contava in fase pre/1T per OGNI decisione. Il
coordinatore ha fatto notare che di serie gira la V3 (`omega_config.py:221-253`,
`strategy_version` 3: un solo mercato, il Correct Score, gamba A 1'-44', gamba B 46'-85').
Verifica: un HT fermo NEL PRIMO TEMPO fermava anche la V3, senza motivo (sez. 3.2). Regola finale:
**l'Half Time Score conta solo per le decisioni SULL'Half Time Score, e solo in fase pre/1T.**

`Betfair/omega/omega_service.py`:
- `_ht_ancora_in_gioco(payload)` (`:940-956`): fase con la regola della missione
  (`omega_engine.mission_phase`: stato IPS `score_raw.matchStatus`, poi minuto; `kickoff=None`);
  vero in `pre`/`1t`. Senza stato e senza minuto: `pre` (conta, prudente).
- `_flusso_della_riga(event_id, con_ht)` (`:959-992`): MO + CS, piu' l'HT solo con `con_ht` e in
  pre/1T (`:980`).
- `_flusso_feed(event_id)` (`:995-1002`): MO + CS (stessa firma: i test che lo sostituiscono con
  `lambda eid:` restano validi). Lo usano stato e decisione (`_feed_fresh_for_decision`,
  `_live_state_for`), `_cs_from_feed`, il cancello d'apertura prima delle gambe, cash out.
- `_flusso_feed_ht(event_id)` (`:1005-1009`): MO + CS + HT (in pre/1T). Lo usano SOLO:
  la gamba v2 del primo tempo (`:1991-2000`, nuovo controllo dopo la finestra e prima del
  conteggio dei tentativi: col flusso HT fermo `flusso_interrotto` con `leg` e `mercati`, e la
  gamba non parte); il green-up di una gamba sull'HT (`:7199-7200`, `:7255`); il suggerimento di
  missione HT (`_cs_suggestion`, `:7425`).
- `_prezzi_del_blocco_freschi(market, event_id, half)` (`:1012-1019`): `_feed_prices_fresh` piu',
  per una gamba sull'HT, il flusso HT vivo. Usato dal green-up (`:7207`) e dalle proposte
  d'uscita (`Betfair/omega/omega_proposte.py:410-411`).
Nessuna soglia, stake, finestra, filtro o gamba cambiati.

### 3.1 In V3 il blocco `ht` serve a qualcosa? (domanda del coordinatore)
- Selezione e apertura V3: **no** (`omega_service.py:2003-2005`: in V3 il mercato della gamba e'
  sempre `CORRECT_SCORE`).
- Chiusure e proposte d'uscita: **si', solo per una gamba aperta SULL'HT** (una gamba v2 rimasta
  aperta dopo il passaggio alla V3, o fatta in v2): `_greenup_block` (`:6603-6611`) prende il
  blocco `ht` se il `market_id` del trade e' quello dell'HT. Coperto da `_flusso_feed_ht` /
  `_prezzi_del_blocco_freschi` con `half`.
- Missioni (suggerimento HT per il trader): **si'**, in pre/1T, senza distinzione di versione
  (`:7585-7595`). Coperto da `_flusso_feed_ht` in `_cs_suggestion`.
- UI: la legge il frontend dalla riga del feed, non il servizio: fuori da questa correzione.

### 3.2 Dati delle due registrazioni: l'HT e' mai fermo nel 1T con CS e MO vivi? SI'
Analisi della registrazione GREZZA, nessun replay (`strumenti/ht_vuoto.py`: ladder ricostruito dai
delta; lo scanner dichiara fermo un mercato il cui ultimo book non ha prezzi):
- **35797769** (in gioco 19:00:34; HT `1.259819684`, CS `1.259819681`, MO `1.259819674`): HT
  SENZA PREZZI **19:30:01-19:31:02 (61 s, 30'-31')** mentre CS e MO erano sospesi solo fino alle
  19:30:02; HT SENZA PREZZI **19:40:44-19:41:52 (68 s, 40'-41')** con il CS mai sospeso e il MO
  sospeso 3 s. Due minuti abbondanti della finestra della gamba A V3 (1'-44') in cui la V3, con la
  prima correzione, sarebbe stata cieca per l'HT.
- **35760084** (in gioco 16:00:25; HT `1.259475535`): HT senza prezzi da solo 16:43:32-16:43:36
  (43'), e piu' a lungo del CS dopo le sospensioni (16:02:00-16:02:05, 16:04:00-16:04:05,
  16:04:33-16:04:39); nel pre-partita 15:30:11-15:30:42 e 16:00:01-16:00:32. La sonda del replay
  (`replay/sonda_HEAD3.txt`) conferma i passaggi «fermo per il solo HT» al pre-partita, 0', 3', 43'.
Con la regola finale questi intervalli non fermano piu' la V3 ne' la gamba v2 2T; fermano ancora
(giustamente) la gamba v2 1T e le chiusure/proposte di una gamba sull'HT.

## 4. Test e falsificazione

`Betfair/omega/tests/test_flusso_ht_secondo_tempo_2026_10_07.py` (11 test; righe dallo SCANNER
VERO `build_rows`, `MarketBook` di betfairlightweight, stati IPS della registrazione,
`_scan_event_legs` VERO con i parametri di serie di `omega_config.resolve_params`):
1. `test_2t_ht_fermo_omega_vede_i_prezzi_vivi_e_lo_stato` - IL CASO VERO (60', HT sospeso): stato,
   feed e CS disponibili. ROSSO sul codice di partenza.
2. `test_2t_ht_fermo_la_gamba_2t_si_valuta_v2_e_v3` - la gamba `ft_cs` arriva alla valutazione.
3. `test_2t_cs_fermo_resta_fermo` - il veto sul CS resta (nessuna gamba, v2 e v3).
4. `test_1t_ht_fermo_v3_non_e_cieca` - caso 35797769 30'/40': la gamba A V3 si valuta.
5. `test_1t_ht_fermo_v2_la_gamba_ht_resta_ferma_e_lo_dice` - la gamba v2 1T resta bloccata,
   `flusso_interrotto` con `leg=ht_cs`, `mercati=["1.HT"]`.
6. `test_1t_cs_fermo_blocca_v2_e_v3`.
7. `test_chiusura_di_una_gamba_ht_guarda_l_ht` - green-up/proposte di una gamba HT.
8. `test_2t_ht_fermo_senza_stato_ips_decide_il_minuto`.
9. `test_intervallo_lo_dice_lo_stato_ips_non_il_minuto` - `FirstHalfEnd` al 45'.
10. `test_la_fase_non_dipende_dall_orologio_di_sistema` - orologio 1970 e 2100, stessi esiti.
11. `test_proposta_d_uscita_di_una_gamba_ht_chiede_il_flusso_dell_ht` - `omega_proposte._una_gamba`
    chiede la freschezza con `half=True` per una gamba HT, `False` per una CS.

Comandi ed esiti:
- `python3 -m pytest Betfair/omega/tests/test_flusso_ht_secondo_tempo_2026_10_07.py -q -p no:cacheprovider`:
  **11 passed**. (Sul codice di partenza i test 1 e 8 della prima stesura erano ROSSI e 3, 6 verdi:
  TDD fatto sulla prima versione; la seconda e' falsificata sotto.)
- `python3 -m pytest Betfair/omega Betfair/safe_strategy/tests/test_flusso_interrotto_cantiere_j_2026_09_28.py
  Betfair/safe_strategy/tests/test_flusso_interrotto_cantiere_j_bis_2026_09_28.py
  Betfair/safe_strategy/tests/test_flusso_su_master_cantiere_j2_2026_09_28.py -q -p no:cacheprovider`:
  **1516 passed, 3 skipped, 0 rossi** (27 s).
- Falsificazione (`strumenti/muta.py` + `strumenti/falsifica.sh`, ripristino da copia, `grep -c
  MUTAZIONE` = 0, `cmp` identico; `replay/falsifica_esito.txt`):

| mutazione | rossi |
|---|---|
| M1 il difetto del 29/09: HT sempre, per ogni decisione e fase | **7** |
| M2 HT per le decisioni sull'HT anche nel 2T (fase ignorata) | **3** |
| M3 la prima correzione: HT anche per la V3 nel 1T | **3** |
| M4 la gamba v2 1T non guarda l'HT | **1** |
| M5 la chiusura di una gamba HT non guarda l'HT | **1** |
| M6 fase dal solo minuto (stato IPS ignorato) | **2** |
| M7 fase dipendente dall'orologio (kickoff fisso) | **1** |
| M8 `omega_proposte.py:411` torna a `_feed_prices_fresh` | **1** |

- Falsificazione a livello di REPLAY (prima versione): codice di partenza (= M1) 438 / 0 sulla
  35760084 [apertura] (`replay/PRIMA_4dd624af_35760084_apertura.txt`), corretto 467 / 2
  (`replay/DOPO_35760084_apertura.txt`). **Da rifare sulla seconda versione** col via libera.

## 5. Prova: la fase non dipende dall'orologio di sistema

`omega_engine.mission_phase` (`Betfair/omega/omega_engine.py:866-903`): `now` si usa SOLO nel
ramo `if kickoff is not None` (`:896-902`). Con `kickoff=None` la fase viene da `status` (`:882-893`)
o da `minute` (`:894-895`), altrimenti `prev="pre"` (`:903`). Il test 10 lo prova (orologio finto
nel 1970 e nel 2100, sei casi, esiti identici); M7 (kickoff fisso: il ramo dell'orologio diventa
raggiungibile) lo fa diventare rosso.

## 6. La regola dell'utente (07/10): «2 trade a partita, 1 nel 1T e 1 nel 2T, se le condizioni lo permettono»

Scenario `apertura` (motore v2, obiettivo G=5, banda di quota allargata a 500: `price_min` 20,
`price_max` 500; `model_p_max_pct` 2 %). Numeri dalla sonda sul modello
(`strumenti/sonda_modello.py`, avvolge `omega_model.select_by_model` senza cambiarne l'esito;
`replay/modello_*.txt`). «Vicino» = il risultato con P_sel / P_implicita piu' bassa (serve < 1).
Misurato con la PRIMA versione della correzione (in v2 1T identica alla finale per la gamba HT;
nel 2T identica): da riconfermare col via libera sulla versione finale.

| partita | tempo | condizioni | trade prima | trade dopo |
|---|---|---|---|---|
| 35760084 | 1T (HT, 20'-40') | **NO**: 59 valutazioni, 0 candidati (512 fuori banda, 53 P >= P implicita, 13 liquidita' < 5,00, 10 P > 2 %, 2 troppo vicini). Il piu' vicino: '2 - 1' @20,0 al 25' (1-0), P 6,37 % contro 4,76 % | no | no |
| 35760084 | 2T (CS, 50'-80') | **SI'** al 52' (3-0): '3 - 3' @300, P 0,316 % < 0,317 % implicita | **NO (cieco)** | **SI'**, lay 5,26 @300, vinto |
| 35797769 | 1T | **NO**: 56 valutazioni, 0 candidati (361 fuori banda, 98 P >= implicita, 50 aggregati, 32 P > 2 %, 13 liquidita', 6 troppo vicini). Il piu' vicino: '2 - 0' @20,0 al 26' (0-0), 5,19 % contro 4,76 % | no | no |
| 35797769 | 2T | **NO**: prima 0 valutazioni (cieco dal 44'), dopo 79 valutazioni, 0 candidati (1135 fuori banda, 135 P > 2 %, 103 liquidita' < 5,26, 87 P >= implicita, 41 aggregati). Il piu' vicino: '2 - 2' @22,0 all'80' (1-1), 4,77 % contro 4,33 % | no (cieco) | no (modello) |

Prima della correzione nessuna partita poteva avere il trade del 2T, qualunque fossero le
condizioni (salvo una gamba 1T aperta). Dopo: la 2T si valuta su entrambe; parte dove il modello
la ammette. Con i parametri di SERIE (`price_max` 120) il '3 - 3' a 300 della 35760084 e' fuori
banda: lo dice gia' la nota dello scenario `apertura`; i numeri degli scenari di serie dopo la
correzione arrivano coi `--scenari tutti` (sez. 9).

## 7. Lo stesso errore negli altri bot? (domanda 1 del coordinatore) - verdetto: NO

| bot | quali mercati valuta il flusso | uno che lo scanner smette di seguire mentre il bot ci decide? |
|---|---|---|
| **Mike** | `Betfair/mike/feed.py:126-145` `mercati_di_mike`: solo le linee O/U 3,5 e 4,5 presenti e ANCORA IN GIOCO (le decise escluse, decisione del 30/09); `feed.py:148-163` `flusso_esito`; `ou_blocks` `:274-309` | **No.** Per una partita seguita da Mike le due linee restano vive anche decise (`safe_strategy/scanner.py:863-864`); per le altre restano vive finche' indecise (`is_live_ou_line`) e Mike scarta le decise. Residuo (non lo stesso difetto): partita non seguita oltre il tetto dei mercati a gol -> linea mai ricevuta o ferma -> Mike non apre (prezzi davvero assenti). |
| **Safe calcio** | `Betfair/safe_strategy/exits.py:401-421` `flusso_esito`: MATCH_ODDS + il SOLO mercato della decisione (`market_id`), o il solo MATCH_ODDS | **No**: non valuta mercati estranei alla decisione. Il CS e' seguito dal 30' con <= 3 gol per lato (`scanner.py:370-377`), ma con esposizione resta seguito fino al CLOSED (`service.py:1188-1215`); senza prezzi Safe non apre, ed e' giusto. |
| **Safe tennis** | stessa `flusso_esito`, MATCH_ODDS | **No.** |
| **Runner (green-up, rischio)** | `Betfair/stream/riserva_prezzi.py:160` `valuta(payload, stato, None, [mid])`: un mercato per volta | **No.** |
| **Scalper calcio, sniper, 4 bot tennis** | non usano `mercati_fermi` della riga: guardano il proprio stream (`stream_muto.py`; `scalper_session.py:1010` solo per il riquadro) | **Non applicabile.** |

Nessuna patch per altri bot.

## 8. Parita' paper/live

`_flusso_feed` e `_ht_ancora_in_gioco` non leggono la modalita': la stessa strada decide in paper e
in live (gate di apertura `scan_and_place_legs`, green-up, cash out). La correzione cambia la
stessa cosa nei due modi. Prova di replay in paper: scenario `paper` dentro `--scenari tutti`
(sez. 9, in attesa).

## 9. NON fatto / NON verificato

- **Replay della versione FINALE non lanciati** (nessun replay dopo l'osservazione V3 del
  coordinatore): `apertura` su 35760084 e 35797769 e i `--scenari tutti` vanno rifatti col via
  libera. Attesi su `apertura` (motore v2): identici alla prima versione (la gamba HT v2 e'
  bloccata dall'HT fermo come prima, solo il punto del controllo si sposta nel ciclo delle gambe;
  l'attivita' `flusso_interrotto` porta ora anche `leg`). Attesi sugli scenari V3/V4: la gamba A
  non si ferma piu' per l'HT nel 1T.
- **`--scenari tutti` su 35760084 e 35797769 NON lanciati** (ordine del coordinatore: aspettare
  il «via libera replay»; la media under occupa i 4 core). Fino ad allora NON so come cambiano gli
  altri scenari (base, paper, v3, v4, uscite, riavvio, ...). Attesi: cambi solo dove Omega ora
  vede il 2T (gamba FT valutata, green-up delle gambe 2T dal feed invece del ripiego REST).
  Tempo: 35797769 `apertura` da solo 190-206 s qui: i `tutti` su quella partita supereranno il
  tetto dei 10 minuti (difetto del banco gia' noto? da misurare).
- Dal vivo (produzione) NON verificato: che lo scanner vero tolga l'HT al 45' e lasci il blocco
  fermo e' dedotto dal codice (sez. 2.5), nessun DB letto.
- Differenze residue col 25/09 sulla 35760084 [apertura], non indagate: motivo `market_suspended
  x1` del 25/09 non c'e' piu'; `ht_cs:no_runner_by_model` x59 contro x60. Decisioni, tick, ordine,
  P&L identici.
- Worktree temporaneo del primo replay (`git worktree add --detach .../scratchpad/bisect 5139d2bc`,
  nessun collegamento dentro): la rimozione con `git worktree remove` e' stata NEGATA dal permesso;
  resta li', pulito. Da rimuovere: `git worktree remove /tmp/claude-0/-home-user-python-database-automation/b81252ef-134e-5437-9162-d213fe1a02bc/scratchpad/bisect`.
- `git fetch --deepen=500 origin` eseguito sull'archivio condiviso (il clone era poco profondo):
  nessun file di lavoro toccato.
- Il resto della suite (`Betfair/` intera, frontend) non lanciato: nessun file fuori da
  `Betfair/omega/**` toccato.

## 10. Reperti del BANCO (fuori perimetro, solo scritti)

- **RB-1 conflazione che perde l'ultimo stato**: `Betfair/stream/backtest/banco_comune.py:2561-2565`
  (`ScannerReplay.applica_book`) tiene il PRIMO book di ogni secondo per mercato e scarta gli altri,
  senza consegnare l'ultimo a fine finestra. La conflazione di Betfair (`conflateMs`) consegna lo
  stato FUSO piu' recente. Prova (`strumenti/sonda_ht_book.py`, `replay/sonda_ht_book_sezione.txt`):
  l'ultimo book HT applicato e' SUSPENDED alle 16:47:58; il CLOSED dello stesso secondo e' scartato e
  dopo non arriva piu' niente: nel banco l'HT non risulta mai CLOSED. Effetto generale: uno stato
  terminale che cade nello stesso secondo di un altro book si perde.
- **RB-2 il banco consegna allo scanner mercati che lo scanner vero non seguirebbe**: `applica_book`
  controlla solo `market_meta`, non i mercati voluti (finestre dei candidati HT/CS/O-U): l'HT riceve
  book fino al 47' (`is_ht_candidate` e' falso dal 45'). Il banco e' piu' generoso della produzione
  sulle finestre di sottoscrizione.
- **RB-3 eta' assurde nei testi del flusso nel replay**: `flusso_prezzi._con_eta` usa l'orologio
  di sistema contro `dal_ms` in tempo di mercato: nel banco «da 8534488 s» (98 giorni). In
  produzione i due orologi coincidono; e' solo testo.

## 11. Decisioni per l'utente

Nessuna decisione di strategia: la correzione non cambia soglie, stake, finestre, filtri o gambe;
rimette in funzione la gamba 2T che la costituzione prevede e che il cambio del 29/09 aveva spento
per errore (regola dell'utente del 07/10: un trade nel 1T e uno nel 2T se le condizioni lo
permettono). Da sapere: dal 29/09 al rilascio della correzione Omega in paper/live NON ha mai
valutato la gamba del secondo tempo sulle partite senza gamba 1T aperta.

## 12. Da controllare dal vivo al prossimo avvio (paper)

- Partita seguita da Omega senza gamba 1T: dopo il 45' nelle attivita' di Omega NON deve comparire
  `skip no_live_state` ripetuto ne' `flusso_interrotto` con `mercati` = solo l'id dell'Half Time
  Score; devono comparire gli `skip` della gamba `ft_cs` (es. `no_runner_by_model`) o un `place`.
  Dove: attivita' di Omega (Control Room / `omega_activity`).
- Una gamba 2T aperta: il green-up deve usare i prezzi del feed (nessun `ripiego_rest` con flusso
  vivo su MO e CS).

## 13. File

- MODIFICATI: `Betfair/omega/omega_service.py` (+80 / -10 circa), `Betfair/omega/omega_proposte.py`
  (1 riga + commento).
- NUOVO: `Betfair/omega/tests/test_flusso_ht_secondo_tempo_2026_10_07.py`.
- NUOVI (prove): `AUDIT_2026-10-07/OMEGA_APERTURA_35760084.md`,
  `AUDIT_2026-10-07/omega_apertura_35760084/replay/*` (referti dei replay, sonde),
  `AUDIT_2026-10-07/omega_apertura_35760084/strumenti/*` (script di bisect, ibridi, sonde,
  mutazioni; tutti in sola lettura del codice, nessuno modifica il repo tranne `muta.py`, che
  `falsifica.sh` ripristina da copia).
- Nessuna migrazione SQL. `Betfair/omega/tools/replay_registrazioni.py`, banco, scalper, tennis,
  frontend: NON toccati.
