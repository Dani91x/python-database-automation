# CANTIERE 11 — Velocita' del banco, senza controllare di meno (referto del delegato cloud, 08/10/2026)

Ramo `claude/blissful-sagan-hri7o6-c11`, partenza `1ac69d0` (contiene `b5547eb`, «regola del mercato che
attraversa»: condizione §0.1 rispettata). Ambiente: container Linux, **4 core** (`nproc`=4, `psutil`: 4 fisici),
Python 3.13, flumine 2.13.11, betfairlightweight 2.23.2. Solo registrazioni calcio del banco (35797769, 35760084).
Punti del metodo fatti: **1 (misura), 2 (punti caldi), 3 (tempi prima/dopo), 5 (suite / xdist)**.
Strumenti installati SOLO nel container (non nel repo, non sul PC): `psutil`, `pyinstrument`, `py-spy`, `pytest-xdist`. Il punto 4
(pagine) non e' stato toccato. Il punto 3 «clic in pochi secondi / punti di salvataggio» non e' stato toccato.

## 0. In una riga

1. **REPERTO (difetto vero del banco, corretto): Omega e Mike non erano isolati fra scenari con `--worker 1`.**
   Con `certifica omega 35760084 --scenari tutti --worker 1` **19 scenari su 20** davano un referto diverso da
   quello dello stesso scenario girato da solo: lo stato di processo di `omega_service` (13 dizionari mai
   azzerati) passava da uno scenario al successivo. Per questo `--worker 3` dava un referto diverso da
   `--worker 1` (403 righe). Corretto nel banco (non nel servizio): adesso `--worker 1`, `--worker 3` e ogni
   scenario da solo sono **identici**, riga per riga (20/20). Mike: stesso difetto in piccolo (2 note), corretto.
2. **Con l'isolamento corretto `--worker N` e' la via ufficiale per la verifica veloce**: referto identico a
   `--worker 1` (0 righe diverse con `confronta_referti`, scalper e omega), omega `tutti` **253 s -> 88 s**,
   scalper 5 scenari **247 s -> 137 s** (4 core; sul PC 8 thread/4 core lo stesso tetto di 3 worker).
3. Ottimizzazioni a processo singolo (conversione dei livelli, livelli dello scanner, verdetto della
   registrazione): referti **identici** (0 righe), guadagno piccolo e onesto: **-3/-9 %**. Il profilo dice
   perche': il tempo e' sparso (bot, flumine, banco, controlli), nessun punto caldo singolo sopra il 16 %.
4. **Suite**: seriale 291 s, con `pytest-xdist -n 4` 88 s, stessi 11149 passed e 0 rossi (sez. 7).
5. **Lavoro comune fra scenari (lettura raw + book + verdetto + import) = 7-8 % di uno scenario**: farlo una
   volta per registrazione varrebbe al massimo quello, con il rischio di condividere book mutati in place
   (conversione EUR). Non fatto: il guadagno vero e' il parallelo.

## 1. Misura prima di toccare (punto 1)

Comandi (macchina scarica, uno alla volta):
```
python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --scenari base --worker 1     # 32,3 s
python -m Betfair.stream.backtest.certifica omega 35797769 --scenari base --worker 1              # 49,0 s
python -m cProfile -o prof.out -m Betfair.stream.backtest.certifica <bot> 35797769 --scenari base --worker 1
```
Profili completi in `profili/` (`cprofile_*.txt`; `pyspy_omega_base_35760084.txt` = campionamento a parete con
py-spy, che vede anche il thread del motore). Tempo PROPRIO per componente (cProfile, scalato sul tempo a parete
senza profilatore; cProfile gonfia le funzioni chiamate milioni di volte: e' una stima d'ordine, non un cronometro):

**scalper_calcio 35797769 `base` (28,9 s, 665.941 book emessi = 30.272 righe x ~22 mercati)**

| punto caldo | s | % |
|---|---:|---:|
| builtin (dict.get / getattr / round / isinstance, sparsi ovunque) | 6.3 | 21.9 |
| banco del bot (`scalper/tools/replay_registrazioni.py`: giro per book, orologio, scenari) | 4.3 | 15.0 |
| flumine: middleware simulato (abbinamento, `RunnerAnalytics`) | 2.4 | 8.2 |
| specchio ordini (`engine/live_trading_strategy.py`, produzione) | 2.2 | 7.7 |
| banco comune (motore, `_a_flumine`, scanner replay) | 2.1 | 7.3 |
| codice del bot (scalper_bot, scalper_session) | 2.1 | 7.2 |
| conversione GBP->EUR (`valuta.py`) | 1.9 | 6.7 |
| controlli del banco (`certificazione.py`) | 1.9 | 6.5 |
| lettura raw + costruzione book (bflw/json) | 1.8 | 6.2 |
| flumine: resto | 1.6 | 5.7 |
| turni fra thread (orologio sessione/motore) | 0.9 | 3.1 |
| import + verdetto registrazione | 0.6 | 1.8 |

**omega 35797769 `base` (48,7 s, 1.785.014 book)**

| punto caldo | s | % |
|---|---:|---:|
| banco comune (motore, scanner replay `applica_book`/`registra_mercato`, specchio varianti) | 11.9 | 24.3 |
| builtin | 10.5 | 21.6 |
| conversione GBP->EUR (`valuta._nuovo_livello`: 12,5 M livelli) | 7.9 | 16.1 |
| flumine: middleware simulato | 5.5 | 11.3 |
| codice del servizio / scanner di produzione | 3.5 | 7.1 |
| lettura raw + costruzione book | 3.3 | 6.7 |
| flumine: resto | 2.6 | 5.3 |
| altro / banco del bot / import | 3.4 | 7.0 |

`sniper-paper` (109 s, lo scenario piu' caro dello scalper): il codice del bot (`scalper_bot._update_flow`,
`sniper_bot.process_market_book`) pesa 15,6 %, il resto come sopra. Tabelle in `profili/`.

**Gli scenari ripetono lavoro comune?** Si', ma e' poco: import (~1,3 s, una volta per processo), verdetto della
registrazione `validate_event` (0,5 s su 35797769, **due volte per scenario**: testa del referto + nota dello
scenario), lettura+parsing del raw e costruzione dei book (misurati da soli con `GeneratoreLibri.veloce`:
4,3 s per 81.137 righe su 35797769 / 1,3 s su 35760084, tutti i mercati). Totale 7-8 % di uno scenario. I book
NON si possono riusare fra scenari nello stesso processo cosi' come sono: `valuta.converti_libro` li converte IN
PLACE (marcatore `size_gbp_convertite`) e flumine li tiene nei suoi mercati; condividerli richiederebbe copie
profonde che costano quanto costruirli. Il guadagno grosso e' il parallelo (sez. 3).

## 2. REPERTO e correzione: isolamento degli scenari (Omega, Mike)

**Prova del difetto.** `--worker 1` contro `--worker 3`, stessa registrazione, stesso codice (`1ac69d0`):

| bot | scenari | righe diverse (tolti tempi, log, diagnostica worker) |
|---|---:|---:|
| scalper_calcio 35797769 (5 scenari del brief) | 5 | 0 |
| omega 35760084 `tutti` | 20 | **403** |
| mike 35760084 `tutti` | 26 | **2** |

Omega: lo scenario `giornata-reale` da solo (`--scenari giornata-reale`, processo nuovo) da' «attivita' del
servizio: skip x3, flusso_non_dichiarato x1», «list_today_football_events x444», la nota NON ESERCITABILE delle
fixture; nel referto `--worker 1` (secondo scenario dello stesso processo) «attivita': (vuota)», «x438», nota
assente. Negli scenari V3/V4 anche numeri di decisione: «V3: 177 occasioni» (`--worker 1`) contro «213» (da solo).
Script `sezioni_contro_solo.py` (spezza il referto per scenario e confronta con `referti/omega_solo/<scenario>.txt`):
**prima: 19 scenari su 20 DIVERSI da se stessi girati da soli; dopo: 0 su 20.**

**Causa (omega).** `omega_service.svuota_le_cache` (chiamata dal banco a inizio e fine scenario, `AmbienteOmega`)
non azzera 13 dizionari di modulo: `_EVENTS_REFRESH_AT` (istante dell'ultimo refresh eventi: a fine scenario e'
l'istante di fine partita, e nello scenario dopo il refresh non riparte MAI), `_SKIP_SEEN`, `_LAMBDA_CACHE`,
`_LEG_RETRY`, `_LEG_RETRY_DB`, `_BLIND_CYCLES`, `_MARKET_FIT_CACHE`, `_EMPIRICAL_CACHE`, `_MINUTE_CACHE`,
`_REALLY_OVER_CACHE`, `_IDLE_STATS_AT`, `_DAILY_GOAL_WRITTEN`, `_ULTIMO_STATO_SCANNER_OMEGA`; piu' due avvisi «una
volta per processo» (`_AVVISO_AGGREGATI_SENZA_MODO`, `flusso_prezzi._NON_NOTO_AVVISATO` per "omega"). Il test che
sorveglia l'elenco (`test_ogni_cache_di_processo_e_nell_elenco_di_svuota_le_cache`) guarda solo i nomi coi prefissi
`_CACHE_`, `_ULTIMI_`...: questi gli sfuggivano.
**Causa (mike).** `mike/dossier._EMPIRICAL_FAILED` (istante dell'ultimo tentativo della tabella HT->FT) non e'
azzerato da `service.azzera_cache_di_processo`: per 600 s nello scenario dopo `ht_ft_rows` non si chiede e la nota
NON ESERCITABILE sparisce. Solo una nota, nessun numero di decisione.

**Correzione (solo il banco; il servizio di produzione NON e' toccato).**
- `Betfair/omega/tools/replay_registrazioni.py`: `STATO_DI_PROCESSO_FRA_SCENARI` (i 13 nomi), `COSTANTI_DI_MODULO`
  (`_GREENUP_REASON`, `_MISSION_MARKET_LABEL`: tabelle di testo), `_processo_nuovo()` = `svuota_le_cache` + i 13 +
  i due avvisi; `AmbienteOmega.__enter__/__exit__` chiamano `_processo_nuovo()` al posto di `svuota_le_cache()`.
  Lo scenario `riavvio` (`_riavvia_processo`, a meta' partita) NON e' cambiato.
- `Betfair/mike/tools/replay_registrazioni.py`: `STATO_DOSSIER_FRA_SCENARI`, `_dossier_nuovo()`, chiamata subito
  dopo `S.azzera_cache_di_processo()` all'inizio di ogni replay.

**Effetto sui referti `--worker 1` (ogni riga spiegata).**
- omega 35760084 `tutti`: 19 scenari cambiano e diventano IDENTICI al loro referto da soli (`sezioni_contro_solo.py`:
  0/20 diversi); il primo scenario (`base`, processo nuovo anche prima) e' identico a prima. ESITO invariato:
  20 OK su 20. Referti: `referti/t_prima_omega_w1.txt`, `referti/t_dopo_omega_w1.txt`, `referti/omega_solo/`.
- mike 35760084 `tutti`: 24 righe diverse, TUTTE la nota «[NON ESERCITABILE] ... ht_ft_rows ...» che ora c'e' in
  ogni scenario (in uno e' fusa con la nota `proprietari_bet` gia' presente). ESITO invariato: 26 OK su 26.
  Referti: `referti/mike_w1.txt` (prima), `referti/fix_mike_w1.txt` (dopo).
- scalper: nessun cambiamento (0 righe), il suo banco era gia' isolato.

**Test** (falsificati, sez. 6): `Betfair/omega/test_omega_banco_isolamento_2026_10_08.py` (riflessione su TUTTI i
dict/set/list di modulo di `omega_service`: ognuno deve stare in `svuota_le_cache`, nell'elenco del banco o fra le
costanti dichiarate), `Betfair/mike/test_mike_banco_isolamento_2026_10_08.py`.

## 3. `--worker N`: perche' il protocollo impone `--worker 1`, e la via veloce

Perche' `--worker 1`: lo standard dei tempi (`PROCESSO_STANDARD_BOT.md` §6.9) e' definito a processo singolo
(«tutti i suoi scenari, una registrazione, `--worker 1`»), e prima di oggi i referti `--worker N` di Omega e Mike
NON erano identici (sez. 2) — chi li avesse confrontati avrebbe visto righe diverse senza spiegazione.
**Adesso sono identici** (scalper 5 scenari, omega `tutti`, mike `tutti`: 0 righe diverse con
`python -m Betfair.stream.backtest.tools.confronta_referti W1.txt W3.txt`). Proposta: `--worker 3` come via
ufficiale per la verifica veloce, con il confronto qui sopra contro un `--worker 1` quando serve la prova; la
misura dello standard dei 5 minuti resta a `--worker 1`.

Note:
- lo strumento di confronto toglie SOLO: righe dei tempi (`righe_senza_tempi`), `worker:`/`MEMORIA:` (esistono solo
  con N>1), righe di log `LIVELLO:modulo:` (con piu' processi lo stderr arriva intercalato), righe vuote;
- **cloud senza `psutil`**: `core_fisici()` stima `nproc//2` = 2 -> tetto 1: `--worker 3` diventava IN SILENZIO
  `--worker 1` (nessuna riga «worker:» nel referto). Sul PC (8 thread) il tetto e' comunque 3. `psutil` non e' in
  `requirements.txt`: punto aperto per il coordinatore (aggiungerlo, o stampare una riga quando il tetto taglia);
- il parallelo e' limitato dallo scenario piu' lungo: scalper `sniper-paper` (110 s) parte per ultimo; sottomettere
  i compiti dal piu' lungo (ordine di raccolta invariato) abbasserebbe il tempo a ~115 s. Non fatto: serve una
  stima del costo per scenario (proposta).

## 4. Ottimizzazioni dei punti caldi (punto 2) — file per file

| file | cosa | perche' e' identico |
|---|---|---|
| `Betfair/stream/valuta.py` (`_livelli`) | il livello `dict` di flumine si copia e si converte in linea, senza `_nuovo_livello` + genexpr per livello | stessa copia `dict(liv)`, stesso `round(float(size)*r, 2)`, stesso ordine delle chiavi; ogni altra forma (sottoclassi di dict, liste, tuple, PriceSize) passa da `_nuovo_livello` come prima. Test di equivalenza su 12 forme + un MarketBook vero |
| `Betfair/stream/backtest/banco_comune.py` (`_livelli_di_produzione`, 8 righe) | il `dict` di flumine si legge con `get` + `float` invece di `_offer_price`/`_offer_size` | stesse chiavi, stesso `float`, None se manca; test anche sul TIPO (2 == 2.0) |
| `Betfair/stream/tools/validate_recordings.py` (`scan_raw`) | la passata sul raw si ricorda per processo, chiave = percorso + dimensione + mtime_ns + soglia; copia profonda in uscita | file che cambia = rilettura; ogni chiamante riceve una copia; file assente si rompe come prima |

Non fatto, e perche': filtrare lo specchio degli ordini terminali (`gira_specchio` riscrive ogni secondo tutti gli
ordini del blotter: 7,7 %) — le righe finiscono in `righe_specchio` e nei controlli P1/P2 (`x5515`): cambierebbe il
referto. Saltare i book dei mercati che nessuno legge: cambia `tick=`. Memoria per identita' delle liste convertite
in `valuta` (il 65 % dei livelli convertiti e' la STESSA lista del book precedente): richiede liste condivise fra
book in codice di PRODUZIONE; nessuna scrittura in place trovata (grep su Betfair/ e flumine), ma lo lascio come
proposta al coordinatore. `orjson` in `scan_raw`: accetta meno di `json` (NaN), non e' identico.

## 5. Tempi prima/dopo (punto 3)

Macchina scarica, un replay alla volta. «Prima» = checkout di `1ac69d0` in una cartella di lavoro separata
(`git worktree`), «dopo» = questo ramo. CPU = user+sys del processo (con N>1 somma dei figli).

| replay | prima parete | prima CPU | dopo `--worker 1` parete | dopo CPU | dopo `--worker 3` parete |
|---|---:|---:|---:|---:|---:|
| scalper_calcio 35797769 `base` | 32,3 s | 33,0 s | 29,6 s (-8,6 %) | 30,2 s | — |
| scalper_calcio 35797769 5 scenari del brief | 246,9 s | 246,8 s | 240,5 s (-2,6 %) | 240,6 s | **137,0 s** (-45 %) |
| omega 35797769 `base` | 49,0 s | 49,7 s | 49,1 s (=) | 49,8 s | — |
| omega 35760084 `tutti` (20) | 253,4 s | 254,2 s | 245,5 s (-3,1 %) | 246,2 s | **87,7 s** (-65 %) |
| mike 35760084 `tutti` (26) | (non misurato a macchina scarica) | | 608,7 s (TEMPO TOTALE, >tetto: LENTO) | | 209,3 s |

`nproc` = 4. Sul PC (Ryzen 7 3750H) i numeri assoluti cambiano: il coordinatore li rimisura.

**Diff dei referti (tolti tempi/log/diagnostica worker, `confronta_referti`)**:
- scalper 5 scenari: prima (riferimento del 08/10 e checkout `1ac69d0`) vs dopo `--worker 1`: **0 righe**
  (l'unica riga diversa col checkout separato e' il percorso della cartella dati in testa); dopo `--worker 1` vs
  `--worker 3`: **0 righe**. ESITO 4 OK + 1 KO (`chiusura-abbinata-in-parte`, il KO B2 gia' noto, decisione D1).
- scalper `base`, omega 35797769 `base`: **0 righe**.
- omega 35760084 `tutti`: prima vs dopo = le righe della sez. 2 (isolamento), tutte spiegate; dopo vs referto con
  la sola correzione d'isolamento: **0 righe** (le ottimizzazioni non cambiano niente); dopo `--worker 1` vs
  `--worker 3`: **0 righe**; dopo vs i 20 scenari da soli: **0/20 diversi**.

## 6. Test nuovi e falsificazioni

| test | mutazione | esito |
|---|---|---|
| `omega/test_omega_banco_isolamento_2026_10_08.py` (5) | M1 `_EVENTS_REFRESH_AT` tolto dall'elenco | 2 rossi |
| | M2 `AmbienteOmega.__enter__` torna a `svuota_le_cache()` | 1 rosso |
| | M3 niente `discard("omega")` dell'avviso del flusso | 1 rosso |
| | M4 avviso aggregati non riarmato | 1 rosso |
| | M5 l'elenco non si svuota (`pass`) | 2 rossi |
| | M6 stato NUOVO di modulo aggiunto a `omega_service` (`_STATO_NUOVO_DIMENTICATO`) | 1 rosso |
| `mike/test_mike_banco_isolamento_2026_10_08.py` (4) | M1 chiamata `_dossier_nuovo()` tolta | 1 rosso |
| | M2 `_EMPIRICAL_FAILED` fuori elenco | 2 rossi |
| | M3 niente `clear()` | 2 rossi |
| `stream/tests/test_banco_velocita_2026_10_08.py` (36) | V1 arrotondamento a 1 cifra nel percorso rapido | 7 rossi |
| | V2 `isinstance` + dict ricostruito {price,size} (perde chiavi, prende sottoclassi) | 2 rossi |
| | V3 conversione in place (niente copia) | 1 rosso |
| | P1 prezzo senza `float` in `_livelli_di_produzione` | 1 rosso |
| | P2 size senza `float` | 3 rossi |
| | S1 memoria restituita senza copia | 1 rosso |
| | S2 si memorizza l'oggetto restituito (non una copia) | 1 rosso |
| | S3 chiave senza dimensione/mtime | 1 rosso |
| | S4 chiave senza soglia | 1 rosso |
| | C1 confronto senza filtro dei log | 2 rossi |
| | C2 confronto che butta le note | 2 rossi |
| | C3 confronto che tiene le righe vuote | 2 rossi |

Totale **22 mutazioni, 22 rosse**. Nella prima stesura P1 e S1 sopravvivevano (forme senza prezzo intero/testo;
copia verificata solo alla prima lettura): test rinforzati, poi rossi. Ripristino verificato con sha256 (16 cifre):
omega replay `3b0a533668d2af6f`, omega_service `5aa75467ede22173`, mike replay `52a53418d5aff884`, valuta
`9cdf2a76de7f665a` (dopo la correzione del solo commento; durante le mutazioni `501810d024fcbb22`), banco_comune `c4f5a034c80174dd`, validate_recordings `8710a145caa57f0a`, confronta_referti
`23b17601617aafb3` (uguali prima e dopo ogni mutazione).

## 7. Suite (punto 5)

`python -m pytest Betfair/ -q -p no:cacheprovider` su questo ramo (con tutte le modifiche):
**11149 passed, 64 skipped, 6 xfailed, 0 rossi** (nessun test di latenza rosso in questo giro).

| suite | parete | CPU (user+sys) | esito |
|---|---:|---:|---|
| seriale (com'e' oggi) | 291 s (4m51) | 183 s | 11149 passed, 0 rossi |
| `pytest-xdist -n 3` | 100 s | — | 11149 passed, 0 rossi |
| `pytest-xdist -n 4` | **88 s** (-70 %) | 197 s | 11149 passed, 0 rossi |

Isolamento verificato: tre giri con distribuzione diversa dei test fra processi (seriale, 3, 4 worker) danno lo
stesso conteggio e zero rossi; `git status` dopo i giri non mostra file nuovi o cambiati dalla suite (nessuna
scrittura condivisa nel repo). La parete seriale e' molto sopra la CPU (291 s contro 183 s: test che ASPETTANO),
ed e' per questo che il parallelo rende piu' dei core. Le fixture autouse di `Betfair/conftest.py` (ripristino di
`flumine.config` e dei riferimenti di strategia) valgono per processo: con xdist ogni worker ha le sue.
Limite: non e' stato provato l'ordine CASUALE (`pytest-randomly` non e' installato), solo distribuzioni diverse.
`certifica.quanti_processi` resta a 1 dentro pytest (`"pytest" in sys.modules`), anche nei worker xdist.
**Proposta**: `pytest-xdist` nel `.venv` del PC (installazione da autorizzare: nel cloud `pip install pytest-xdist`,
sul PC NON fatto) e comando `python -m pytest Betfair/ -q -p no:cacheprovider -n 3`. Sul PC il coordinatore
rimisura e verifica i 0 rossi su Windows (xdist usa processi nuovi anche li': nessuna differenza attesa, da provare).

## 7-bis. Fusione con la cima nuova del ramo base (`36a9126`, arrivata durante il lavoro)

Il ramo e' costruito su `1ac69d0` come da brief (tutti i numeri valgono li'); non l'ho fuso. Prova di fusione a
secco (`git merge-file`, nessun commit): `mike/tools/replay_registrazioni.py` e `banco_comune.py` si fondono senza
conflitti; `omega/tools/replay_registrazioni.py` ha **2 conflitti**, in `AmbienteOmega.__enter__/__exit__`: il
cantiere 7 (RB-5) ha aggiunto in parallelo `_azzera_cache_di_processo()` con l'elenco `CACHE_DI_PROCESSO_DEL_BANCO`
(9 nomi: `_LEG_RETRY`, `_SKIP_SEEN`, `_BLIND_CYCLES`, `_MARKET_FIT_CACHE`, `_LAMBDA_CACHE`, `_IDLE_STATS_AT`,
`_CATENA_OMEGA`, `_EMPIRICAL_CACHE`, `_MINUTE_CACHE`) e l'aggancio `FP._ora_ms`. Il suo elenco NON copre
`_EVENTS_REFRESH_AT` (la causa principale: refresh eventi e fixture), `_LEG_RETRY_DB`,
`_ULTIMO_STATO_SCANNER_OMEGA`, `_DAILY_GOAL_WRITTEN`, `_REALLY_OVER_CACHE` ne' i due avvisi «una volta per
processo». **Risoluzione proposta** (nessuna riga di nessuno dei due si perde):
```
    def __enter__(self):
        ...
        FP._ora_ms = (lambda: int(float(self.banco.ora) * 1000))  # cantiere 7, RB-3
        _processo_nuovo()               # cantiere 11: svuota_le_cache + 13 nomi + 2 avvisi
        _azzera_cache_di_processo()     # cantiere 7, RB-5 (anche _CATENA_OMEGA)
        return self

    def __exit__(self, *_exc):
        ... (ripristini di sempre)
        FP._ora_ms = self._prima["_ora_ms"]
        _processo_nuovo()
        _azzera_cache_di_processo()
```
Le due nuove variabili di modulo della cima (`_MERCATI_CONTO`, `_DA_ANNULLARE_PAPER`) sono gia' in
`svuota_le_cache`: il test di riflessione resta verde. Dopo la fusione vanno rifatti: i test dei due cantieri,
`omega 35760084 --scenari tutti` a `--worker 1` e `--worker 3` con `confronta_referti` (atteso 0 righe) e
`sezioni_contro_solo.py` (atteso 0/20).

## 8. Come rifarlo sul PC

```
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti --worker 1 > o_w1.txt 2>&1
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti --worker 3 > o_w3.txt 2>&1
python -m Betfair.stream.backtest.tools.confronta_referti o_w1.txt o_w3.txt          # atteso: righe diverse 0
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari giornata-reale --worker 1 > gr.txt 2>&1
#   la sezione [giornata-reale] di o_w1.txt deve essere uguale a gr.txt (sezioni_contro_solo.py lo fa per tutti)
python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper --worker 1
#   contro AUDIT_2026-10-08/cantiere_11/referti/t_dopo_scalper5_w1.txt: righe diverse 0
python -m pytest Betfair/omega/test_omega_banco_isolamento_2026_10_08.py Betfair/mike/test_mike_banco_isolamento_2026_10_08.py Betfair/stream/tests/test_banco_velocita_2026_10_08.py -q -p no:cacheprovider
```

## 9. Punti aperti per il coordinatore

1. **Prima di fidarsi di qualunque referto `--worker 1` multi-scenario di Omega precedente a oggi**: dal secondo
   scenario in poi era contaminato (sez. 2). Gli ESITI OK/KO su 35760084 non cambiano, ma note, motivi e conteggi si'.
   Da rifare sul PC: omega su 35797769 `tutti` (non rifatto qui per tempo) e ogni referto Omega/Mike
   multi-scenario usato come riferimento (in `AUDIT_2026-10-08/riferimenti/` oggi ci sono solo referti scalper).
2. `_riavvia_processo` di Omega (scenario `riavvio`) azzera ancora un sottoinsieme (7 nomi): un riavvio vero
   perderebbe anche `_EVENTS_REFRESH_AT`, `_EMPIRICAL_CACHE`... Cambiarlo cambia lo scenario `riavvio`: decisione
   del coordinatore (non fatto).
3. Safe (3 varianti) e i bot tennis non verificati qui (`--worker 1` contro `--worker 3`): Safe non ha
   `svuota_le_cache`, i suoi stati di modulo (`_TOPIC_SCAN`, `_SPORTS`) sembrano costanti; tennis senza registrazioni
   nel cloud. Da fare sul PC con `confronta_referti`.
4. `psutil` assente nel cloud -> `--worker N` diventa 1 in silenzio (sez. 3).
5. Mike `tutti` su 35760084 a `--worker 1`: **608,7 s, sopra il tetto** (riga LENTO); a `--worker 3` 209 s.
6. Proposte non fatte (sez. 4): memoria per identita' delle liste convertite in `valuta` (-65 % dei livelli
   convertiti, codice di produzione), ordine di sottomissione dal compito piu' lungo, punti di salvataggio (punto 3
   del cantiere) per l'«Applica bot».
