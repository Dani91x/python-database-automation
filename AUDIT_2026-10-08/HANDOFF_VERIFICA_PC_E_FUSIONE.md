# VERIFICA SUL PC E FUSIONE SU MASTER — lavoro della sessione cloud dell'08/10/2026

Destinatario: l'agente sul PC dell'utente (quello con accesso al PC, alle registrazioni tennis, al DB e
all'app desktop) e l'agente che fonde su master. Autore: coordinatore della sessione cloud.
Comunicare in italiano. Regole: `CLAUDE.md`, `BRIEF_STANDARD_DELEGATI.md`, `PROCESSO_STANDARD_BOT.md` §6-§7.

> BOZZA IN CORSO: le sezioni marcate «[IN ATTESA]» si completano quando chiudono gli ultimi cantieri.
> La versione finale e' quella con la riga «STATO: COMPLETO» in testa.

Ordine dell'utente (08/10, testuale): «ALLA FINE DI TUTTI I LAVORI DOVRAI STILARE UN DOCUMENTO DETTAGLIATO PER
FAR CONTROLLARE IL TUTTO ALL'ALTRO AGENTE, TUTTE LE TASK LUNGHE CERTIFICALE E APPROVALE TU, L'ALTRO AGENTE
DOVRA OCCUPARSI DI ACCERTARSI CHE TUTTO CORRISPONDA ALLA REALTA E NON CI SIANO REGRESSIONI (NON VOGLIO REPLAY
DI SETTIMANE, STUDIATE UN MODO PER FARE IL PRIMA POSSIBILE SENZA RINUNCIARE ALLA QUALITA E ALLA
CERTIFICAZIONE.)» e «VOGLIO CHE MASTER SIA PERFETTO [...] SENZA REGRESSIONI DI NESSUN TIPO».

---------------------------------------------------------------------------------------------------

## 0. In una pagina

- Ramo da fondere: `claude/blissful-sagan-hri7o6`. Contiene TUTTO `claude/eloquent-franklin-g2nyk5` (lavoro del
  07/10 e del PC dell'08/10 fino a `3c4aae6`, merge `d0cf8b94` e `66fee09`) piu' i cantieri della sessione cloud, UN COMMIT
  PER CANTIERE, ciascuno con referto e blocco in `CRONOSTORIA.md`.
- `origin/master` e' a `8226d76` (06/10) ed e' ANTENATO del ramo: la fusione e' un avanzamento senza conflitti
  (fast-forward possibile; vedi §5 per come farla).
- Il coordinatore cloud ha gia' certificato ogni cantiere: diff riletto, test rilanciati, mutazioni PROPRIE (oltre a
  quelle del delegato), replay rifatti di persona dove la registrazione e' nel cloud. Il PC NON rifa' tutto:
  controlla che i numeri del cloud siano veri sulla macchina vera e fa SOLO cio' che nel cloud non si poteva
  (registrazioni tennis, DB, app a schermo, Windows). Stima: 2-3 ore di macchina, quasi tutte in parallelo.

## 1. Cantieri e commit

| commit | cantiere | cosa | certificato nel cloud | resta al PC |
|---|---|---|---|---|
| `5cc7103` | W2 | green-up dell'esposizione FUORI BOT letta dal conto: chiudere dall'app gli ordini fatti sul sito | 56 test, parita' su 51 scenari col worker di prima, mutazioni 19+5 | nessuna prova su Betfair vero (solo su ordine reale dell'utente, vedi §4.6) |
| `f0f14f6` | 5 | parcheggio del place-and-trim tennis dalla fonte unica (LAY 1,01-1,03), controllo B11 | 1112 test tennis, mutazioni 10+4 | replay tennis prima/dopo (§3.1) |
| `4b262c4` | 12 | test vitest rossi solo su Windows (fine riga, lancio di vite-node) | 34 test della barra, mutazioni 12+2 | i 6 test su Windows vero (§3.2) |
| `d1d4cd3` | 14 | nomi completi dei giocatori tennis in `_names.json`, fonte del nome, reimport che non declassa | 64 test Python, 16 vitest, mutazioni 26+3 | 35790089 a mano, migrazione, tooltip (§3.3) |
| `3b8ce19` | 15 | banco: la RIVALUTAZIONE ORARIA DEL CAMBIO del volume scambiato non e' uno scambio (era la causa del KO dello scalper) | prova indipendente sul raw, replay identici, mutazioni 3 | nessuna (calcio rifatto nel cloud) |
| `7633e20` | 6 | banco tennis: nomi dei giocatori nel certifica, scenari e controlli SP1-SP3 del pro, contratto di gate-aperto | 47 test + 970 collegati, mutazioni 15+3 | replay tennis (§3.1) |
| `00fbd9b` | W1 | PAGINA «CASH OUT» sotto la Control Room | tsc 0, 1404 test frontend collegati, fotografie, mutazioni 28+5 | prova a schermo (§3.4), build |
| `16d6c67` | 10 | registro del replay coi cicli del bot e diviso per fasi | 284 vitest replay, contratto Python-TS, mutazioni 16+3 | 35768297 a schermo (§3.5) |
| `6f04054` | 13 | strumento della barra: falso positivo dopo il VAR, incoerenze «per dati», fixture rigenerate | 160 vitest barra, 17 pytest tools, mutazioni 13+3 | le 38 partite del DB (§3.6) |
| `1ac69d0` | 9 | banco scalper: scavalco e rifiuti Betfair coi codici veri; UF2 riconosce il parcheggio 1,01-1,03 | 93 test, replay identici, mutazioni 24+1 | replay tennis `uscite-manuali*` (§3.1) |
| `d0cf8b94` | merge | piano di architettura del PC (`eloquent-franklin` fino a `b5845bc`) | solo documenti/strumenti, nessun file > 1 MB | — |
| `328de86` | 7 | banco di Omega RB-1..RB-5: CLOSED allo scanner, finestre di sottoscrizione di produzione, paper con la porta del runner, cache azzerate fra scenari | 23 test, mutazioni 15+2, mio replay `apertura`/`paper` 467/2 identico | comandi §3.7 (Omega e controllo Mike/Safe identici) |
| `56ceb13` | test | heartbeat-stall: il test presumeva la macchina accesa da >900 s (4 rossi nel cloud) | vecchio test 4 rossi con intervallo > uptime, nuovo 16 verdi | nessuna |
| `597ea3a` | W3b | Scalper calcio e 4 bot tennis sanno degli ordini esterni (sito/app) e non fanno altro; ordini di altri bot riconosciuti (classificazione W2) | 82 test, mutazioni 4 mie (15 rossi), replay DOPO su macchina separata 14 scenari x 2 = attesi, controllo sulla cima 28/28 identici | replay tennis (§3.1, stessa corsa), log dal vivo (§3.7) |
| `5beb289` | riferimenti | Mike/Omega/Safe/Scalper `--scenari tutti` col banco realistico (punto 4 del cantiere 15), suite cloud | 3 macchine parallele: Mike 26/26 OK x2, Safe 22/22 OK x3 varianti x2, Omega 0 violazioni, Scalper KO tutti attesi tranne `riavvio` B1 PREESISTENTE (§6 D-9) | nessuna (sono il riferimento del PC) |
| `b4d91ed` | W3a | Mike/Omega/Safe sanno SUBITO (canale del conto, anche in prova) degli ordini esterni; ordini di altri bot riconosciuti; verdetto in esposizione; W2 riallineato | replay DOPO su 2 macchine: 0 KO, 0 violazioni (Mike 29, Omega 22, Safe 23 x3); 2 differenze non attese spiegate di persona con sonde (`W3A_CONSAPEVOLEZZA_SERVIZI.md`, verifica); suite cima `66fee09` 11273/0 | log dal vivo e prova in paper (§3.7) |
| `71e56de` | fix | frammenti di mercato: un id() riciclato non eredita il tempo di un altro frammento (test rosso a caso nel cloud, 20/20 rosso da solo) | test nuovo deterministico, mutazione rossa, 10/10 verdi ripetuti | nessuna |
| `66fee09` | merge | `eloquent-franklin` fino a `3c4aae6`: action Seasons Catchup resiliente alla rete + architettura tappe 2-5 | `test_catchup_*.py` 90/90, nessun file nuovo > 500 KB, CRONOSTORIA senza righe perse | nessuna |
| `3e235d1` | 11 | velocita' del banco: SCENARI ISOLATI per Omega (13 stati di processo + 2 avvisi) e Mike (dossier) -> `--worker 1` = `--worker N` = scenario da solo; conversione dei livelli e verdetto del raw piu' rapidi a referto identico; `confronta_referti` | delegato 22 mutazioni rosse; mie 2/2 rosse + 1 equivalente spiegata; mio replay omega `tutti` worker 1 = worker 3 (0 righe), esiti identici a W3a, scalper identico salvo impronta | §2.3 e §3.7 (`--worker 3` contro `--worker 1` sul PC, `psutil`) |

## 2. Il metodo rapido (perche' non servono replay di settimane)

1. **Impronte prima dei replay.** Per ogni bot il referto del banco stampa l'impronta del codice («codice bot»). Se
   l'impronta sul PC coincide con quella del referto cloud e il banco e' lo stesso commit, il replay sul PC deve
   dare righe identiche: basta UNO scenario per bot per provare che la macchina e' coerente, non `tutti`.
2. **Solo cio' che il cloud non poteva fare.** Le registrazioni calcio del banco (35760084, 35797769) sono state
   rigiocate nel cloud dal coordinatore e dalle sessioni parallele: sul PC NON si rifanno per intero.
3. **Parallelo.** `certifica` accetta `--worker N`: per la verifica rapida si lanciano processi separati per bot e
   per registrazione (uno per CPU), non in fila. DAL CANTIERE 11 `--worker 3` e' la via ufficiale per la verifica
   veloce: il referto e' identico a `--worker 1` riga per riga (Omega e Mike prima NON erano isolati fra scenari:
   corretto), confronto con `python -m Betfair.stream.backtest.tools.confronta_referti W1.txt W3.txt` (atteso 0
   righe). ATTENZIONE: senza `psutil` il tetto dei worker diventa 1 IN SILENZIO (nessuna riga «worker:» nel referto);
   sul PC verificare `python -c "import psutil"` (se manca: chiedere all'utente prima di installarlo).
4. **Mutazioni a campione.** Per ogni cantiere UNA mutazione scelta da chi verifica (non fra quelle del referto):
   deve diventare rossa. Se resta verde: reperto, il cantiere non e' certificato.
5. **Confronto, non lettura.** I referti si confrontano con `diff` esclusi tempi e hash, contro i file del cloud
   indicati per ogni cantiere; ogni riga diversa va spiegata.

## 3. Cosa fare sul PC, cantiere per cantiere

### 3.1 Replay tennis (cantieri 5, 6, 9) — UNA corsa sola che li copre tutti
Le registrazioni tennis 35790089 e 35794049 stanno in `C:\Users\Admin\Desktop\tennis_rec\20260707`.
- PRIMA: sul commit `3b8ce19^` NON serve: i referti del mattino del 07/10
  (`AUDIT_2026-10-07/riferimenti_coordinatore/finale/tennis_finale_<bot>.txt`) sono il PRIMA dei cantieri 5/6/9.
- DOPO, sulla cima del ramo, in parallelo (un processo per riga):
  `python -m Betfair.stream.backtest.certifica <bot> 35790089 --data-dir C:\Users\Admin\Desktop\tennis_rec\20260707 --scenari tutti --worker 1`
  per `tennis_scalper`, `tennis_pro`, `tennis_flb`, `tennis_swing`, `safe_tennis`; poi `tennis_pro` e
  `tennis_scalper` su 35794049.
- ATTESO (dai referti): 0 violazioni; controlli attivi 22 -> 23 (B11) per i 4 bot tennis; tennis_pro 17 -> 20 scenari
  (tre setup coi nomi; su 35790089 escono NE «nomi ASSENTI»); righe in testa «nomi» e «parametri cambiati dallo
  scenario»; parcheggi LAY con resto 0,50-0,62 da 1,01 a 1,02 e 0,63-0,79 da 1,01 a 1,03; tick, decisioni, azioni,
  esiti e netti IDENTICI. Dettagli: `cantiere_5/REFERTO.md` §6, `cantiere_6/REFERTO.md` §7, `cantiere_9/REFERTO.md` §7.
- Possibile SP3 su 35794049: il pro entra in break point anche nel tie-break (decisione dell'utente, §6 D-6).

### 3.2 Windows (cantiere 12)
`cantiere_12/REFERTO.md` §8: `git ls-files --eol` sui `.timeline.jsonl` (atteso `i/lf w/crlf`), i 4 file vitest
della barra (atteso 38/38), `npx vite-node scripts/verifica_barra_replay.ts --evento 35797769 --json` dal percorso con
lo spazio («PYTHON DATABASE»), mutazioni M1, M5, P1, S1 a campione.

### 3.3 Nomi tennis (cantiere 14)
`cantiere_14/REFERTO.md` §4. Migrazione `migrations/replay_tennis_fonte_nomi_2026-10-08.sql` DOPO
`replay_tennis_mercati_elenco_2026-10-08.sql` (§4). 35790089: nome intero scritto a mano in `_names.json`, poi
`python -m Betfair.stream.tennis_replay.importa --evento 35790089 --solo-nomi`: `n_snapshots` e `n_score` IDENTICI a
prima nel DB; tooltip «nome dall'IPS, troncato» sparito per quella partita.

### 3.4 Pagina Cash Out (W1) — a schermo, in PROVA
Dopo `npm run build` ad APP CHIUSA (regola del PC), l'utente riavvia l'app.
- Voce «Cash Out» subito sotto «Control Room»; pagina con riepilogo LIVE/PROVA mai sommati, filtri sport, Pre-match/
  Live, soldi; una scatola per partita con tutte le gambe.
- In PROVA con un bot acceso: la gamba compare nella sezione giusta; al calcio d'inizio la scatola passa da
  «Pre-match» a «In gioco» senza sparire; «Cash out» su una gamba di Omega/Safe chiude solo quella; su Mike dice
  «tutte le N gambe di Mike» e chiude il ciclo; il bot dopo il clic non rientra (marcatore «chiusa da te»).
- Ladder: si apre la finestra 560x860 del mercato della gamba. Statistiche: apre il Cruscotto e «Torna» riporta su
  Cash Out (non sulla Control Room).
- Control Room INVARIATA (stesse schede, stessi pulsanti; il ritorno al punto ora scorre davvero sulla partita).

### 3.5 Registro del replay (cantiere 10)
`cantiere_10/REFERTO.md` §9: 35768297 media under, il registro mostra N = numero dei cicli del bot e il totale
«uguale al banco»; sezioni per fase.

### 3.6 Strumento della barra (cantiere 13)
`cantiere_13/REFERTO.md` §3-§4: `npx vite-node scripts/verifica_barra_replay.ts --env-file ../.env --senza-note` sulle 38
partite (atteso: 28 OK, 10 «solo per dati», 0 da correggere) e la tabella delle 13.

### 3.7 Cantieri 7, W3a, W3b (calcio: gia' rigiocati nel cloud; qui solo il controllo di coerenza della macchina)
Le registrazioni calcio 35760084 e 35797769 sono nel repo compresse (`registrazioni_banco/`, script in `LEGGIMI.md` per
`_live_raw/`). Sul PC basta UNO scenario per bot (metodo §2.1), lanciati IN PARALLELO, un processo per riga:
```
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari apertura,paper --worker 1      # 467/2 entrambi (cantiere 7)
python -m Betfair.stream.backtest.certifica omega 35797769 --scenari chiuso-fuori-app --worker 1    # 1T '3 - 3' @80 al 1' (RB-5)
python -m Betfair.stream.backtest.certifica mike 35760084 --scenari base,cap-stretto --worker 1
python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari base,riavvio --worker 1
python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --scenari base,ordine-esterno,ordine-esterno-di-un-bot --worker 1   # OK 44 azioni / OK 2 azioni (stop) / OK 44 azioni
```
ATTESO: righe IDENTICHE (esclusi `tempo:`, `TEMPO TOTALE`, e per la Safe la nota «metodi ASSENTI dal banco» /
«NON ESERCITABILE get_event», che dipende dalla velocita' della macchina: §6 D-13) ai file del cloud indicati nel riepilogo di W3a
(`AUDIT_2026-10-08/W3A_DOPO_CLOUD/`) e di W3b (`AUDIT_2026-10-08/W3B/dopo_cloud/`); fonte
delle righe scalper: `AUDIT_2026-10-08/controllo_scalper_597ea3a/35797769_blocco{1,3,4}.txt`.
Test mirati (un minuto):
```
python -m pytest Betfair/stream/tests/test_banco_scanner_reperti_rb_2026_10_08.py Betfair/omega/tests/test_banco_omega_reperti_rb_2026_10_08.py Betfair/stream/tests/test_w3b_ordini_esterni_scalper_2026_10_08.py Betfair/stream/tennis_live/tests/test_w3b_ordini_esterni_tennis_2026_10_08.py Betfair/mike/tests/test_mike_w3a_consapevolezza_2026_10_08.py Betfair/omega/tests/test_omega_w3a_conto_canale_2026_10_08.py Betfair/safe_strategy/tests/test_safe_w3a_conto_canale_2026_10_08.py Betfair/stream/tests/test_greenup_fuori_bot_2026_10_08.py Betfair/stream/tests/test_frammenti_id_riciclato_2026_10_08.py -q -p no:cacheprovider
```
Tennis W3b: nella STESSA corsa del §3.1 (i referti tennis devono essere identici a quelli del cantiere 5 salvo la riga
`codice bot`: `W3B_CONSAPEVOLEZZA_FLUMINE.md` §9).

DAL VIVO, al primo avvio dopo la build (solo osservare i log; nessun ordine vero per prova, vedi CLAUDE.md):
- runner calcio: `[conto-ws] ... (topic conto)` in live; in prova messaggi `conto_paper` (`local_channel.statistiche`).
- Mike/Omega/Safe all'avvio: `posizione di conto dallo stream ordini del runner: ws://127.0.0.1:47331/lettore/conto,conto_paper`
  (Safe anche 47332).
- scalper LIVE: `[scalper-sess] <ev>: ordini esterni dallo stream ordini del conto (osservatore montato)`; runner tennis LIVE
  `[conto-ws] ...` una volta per build.
- PROVA A SCHERMO IN PAPER (la sola permessa senza l'utente): con Omega o Safe in prova su una partita, un ordine manuale
  dall'app sulla stessa selezione -> attivita' `chiuso_dall_utente` con `dove = "dall'app (ordine manuale sul runner paper)"` e
  latenza ~1-2 s; il bot non piazza piu' nulla su quella selezione. Un green-up dell'utente di un SUO ordine sulla selezione di
  un bot NON produce `chiuso_dall_utente`. Chiusura dalla pagina Cash Out (§3.4) -> stesso esito.

## 4. Migrazioni (le applica l'utente, nell'ordine)
Verificare in sola lettura quali sono gia' applicate, poi applicare le mancanti in quest'ordine:
1. `segui_live_apri_partita_2026-10-06.sql`, `ack_allarmi_replay_cambio_2026-10-06.sql`, `replay_applica_bot_2026-10-06.sql` (06/10)
2. `replay_tennis_2026-10-07.sql`, `media_under_attiva_adesso_2026-10-07.sql` (07/10)
3. `replay_tennis_mercati_elenco_2026-10-08.sql` POI `replay_tennis_fonte_nomi_2026-10-08.sql` (08/10; la seconda
   contiene anche `market_types`: riapplicare la prima dopo toglie `nomi_fonte`)
4. W3a, W3b, cantiere 7: NESSUNA migrazione (leggono tabelle esistenti).

## 5. Fusione su master — procedura esatta
Chi fonde: l'agente sul PC, SOLO dopo il via dell'utente e SOLO a §3 completato senza reperti aperti (o con i reperti
accettati per iscritto dall'utente). Mai riscrivere la storia: niente rebase, niente `--force`, niente squash.

**5.0 Prima di tutto (5 minuti, sola lettura)**
```
git status                         # pulito; il log da 3 GB NON va mai aggiunto (mai `git add -A`)
git fetch origin
git log --oneline -1 origin/master                                   # atteso 8226d76 (se e' cambiato: §5.5)
git log --oneline -1 origin/claude/blissful-sagan-hri7o6             # la cima CERTIFICATA scritta in testa a questo file
git merge-base --is-ancestor origin/master origin/claude/blissful-sagan-hri7o6 && echo MASTER_ANTENATO
git log --oneline origin/claude/blissful-sagan-hri7o6..origin/claude/eloquent-franklin-g2nyk5   # lavoro del PC non ancora nel ramo
```
- Se l'ultima riga e' VUOTA: il ramo cloud contiene gia' tutto il lavoro del PC -> §5.2.
- Se NON e' vuota (il PC ha pushato dopo `3c4aae6`): §5.1.

**5.1 Portare nel ramo cloud il lavoro del PC arrivato dopo** (merge, mai rebase)
```
git checkout -B fusione-master origin/claude/blissful-sagan-hri7o6
git merge --no-ff origin/claude/eloquent-franklin-g2nyk5
```
- Conflitto atteso SOLO in `CRONOSTORIA.md` (blocchi diversi): tenere ENTRAMBE le parti, ognuna nel proprio blocco; controllo
  che nessuna riga sia persa (lo script usato dal cloud per `66fee09`):
  ```
  python - <<'EOF'
  import subprocess
  r=set(open('CRONOSTORIA.md',encoding='utf-8').read().splitlines())
  for ref in ['HEAD','MERGE_HEAD']:
      t=subprocess.run(['git','show',ref+':CRONOSTORIA.md'],capture_output=True,text=True,encoding='utf-8').stdout.splitlines()
      print(ref,'righe mancanti:',sum(1 for l in t if l not in r))
  EOF
  ```
  Atteso: 0 e 0. Un conflitto in un file di CODICE e' un reperto: fermarsi e portarlo all'utente con le due versioni.
- File nuovi > 1 MB portati dal merge: `git diff --name-only --diff-filter=A HEAD~1 HEAD` e controllare le dimensioni; nessun
  `_live_raw/`, `*.log`, registrazioni decompresse (`.gitignore` li esclude: verificare con `git status --ignored` che restino fuori).
- Poi le suite di §5.2 e i replay di §5.3 su `fusione-master`.

**5.2 Suite sulla cima da fondere** (in parallelo; tempi del PC)
```
python -m pytest Betfair/ -q -p no:cacheprovider                    # atteso: 0 failed (riferimento cloud: §1, suite finale)
python -m pytest tools/ -q -p no:cacheprovider
python -m pytest test_catchup_*.py -q -p no:cacheprovider            # 90 passed
cd frontend && npx tsc -p tsconfig.app.json --noEmit                 # 0 errori
cd frontend && npx vitest run                                        # 0 failed
cd frontend && npm run build                                         # SOLO ad app chiusa (regola del PC) o in una copia
```
Un rosso: rilanciarlo DA SOLO 3 volte. Rosso anche da solo = reperto (mai «flaky» senza causa: due casi di oggi, §1 righe
`56ceb13` e `71e56de`, erano un test sbagliato e un difetto vero). Un rosso SOLO di tempo (es.
`test_latenza_logica_comando_place_sotto_20_ms`, p95 20 ms) si rilancia a macchina scarica e si annota.

**5.3 Replay di controllo** = §3.1 e §3.7 (gia' fatti per la verifica: NON rifarli se la cima e' la stessa sha verificata; se
§5.1 ha aggiunto commit del PC che toccano `Betfair/stream/` o i bot, rifare SOLO le righe di §3.7, un processo per riga).

**5.4 La fusione**
```
git checkout master
git pull --ff-only origin master
git merge --ff-only origin/claude/blissful-sagan-hri7o6     # oppure: fusione-master se si e' passati da §5.1
git log --oneline -3                                         # la cima di master = la cima verificata
git fetch origin && git push origin master                   # MAI --force
```
Se `--ff-only` rifiuta (master e' andato avanti, §5.5) NON forzare.

**5.5 Se `origin/master` non e' piu' `8226d76`**
`git log --oneline 8226d76..origin/master`: per ogni commit nuovo capire da quale ramo viene. Poi
`git merge --no-ff origin/master` DENTRO `fusione-master` (non il contrario), risolvere come §5.1, rifare §5.2 e §5.3, e
infine `git checkout master && git merge --ff-only fusione-master`.

**5.6 Dopo la fusione**
- `git diff origin/claude/blissful-sagan-hri7o6 master --stat` deve essere VUOTO (o solo i commit del PC di §5.1).
- `CRONOSTORIA.md`: blocco «FUSIONE SU MASTER» con sha prima/dopo, suite (numeri), replay (file), reperti.
- Rami: NON cancellare nessun ramo. Elencare quelli non fusi con `git branch -r --no-merged origin/master` e portarli
  all'utente (vedi §6 D-8); NON fonderli di iniziativa.
- Migrazioni: §4, le applica l'utente (non chi fonde).
- App: build ad app chiusa, poi riavvio dell'utente; all'avvio nessun bot opera (`avvio_app.py`): i bot li accende l'utente.

## 6. Decisioni aperte per l'utente
- D-1 (cantiere 15) `chiusura-abbinata-in-parte` KO solo B2 0,04 (due resti per ciclo sotto la tolleranza per ciclo):
  B2 per ciclo come K5 (patch pronta, non applicata) o il bot dichiara la polvere della selezione.
- D-2 (cantiere 9) MONEY-CRITICAL: dopo un `replaceOrders` rifiutato il place-and-trim (`trading/submin.py`, comune a
  scalper, sniper, bot tennis e worker) passa a DONE e il bot crede chiusa per ~25 s una posizione aperta.
- D-3 (cantiere 6) il pro entra in break point anche nel tie-break (0-3/1-3 per chi riceve).
- D-4 (cantiere 6) `gate-aperto` apre soglie che la UI non espone (dichiarate).
- D-5 (cantiere 10) netto per fase calcolato sulla fase (somma diversa di un centesimo dal totale, detto a schermo) o solo lordo.
- D-6 (W1) partita col mercato CLOSED e posizioni non regolate: oggi in «In gioco» con «conclusa».
- D-7 (W2) un ordine dell'app non abbinato sul lato della copertura blocca la chiusura degli ordini del sito (oggi:
  rifiuto con motivo; alternativa: annullarlo in automatico).
- D-8 rami non fusi: `audit-ml` (doc), `schema-architettura` (doc), `feature/scalper-media-under` (ladder con partita
  sintetica, «solo se l'utente lo vuole»).
- D-9 (riferimenti) scalper calcio `riavvio` B1 x21 su 35797769: dopo il riarmo la sessione apre ingressi col divieto
  `missione_prematch` attivo. PREESISTENTE (gia' sulla `b5547eb` del PC), riproducibile da solo; non toccato (strategia).
- D-10 (cantiere 7) P1 Correct Score oltre 3 gol per lato non seguito dallo scanner (Omega cieco sul 2T); P2 blocco uscito dalla
  sottoscrizione = flusso fermo = bot fermo su quella riga; P3 1T V4 su REST prima del 30'. Comportamenti di produzione mostrati
  ora dal banco, nessuna strategia toccata.
- D-11 (W3a) 1. riduzione parziale dell'utente = STOP del bot (ordine dell'08/10; sostituisce R10 del 16/09, tre test riscritti):
  confermare. 2. DB illeggibile: il fermo vale per l'intera partita del bot (le chiusure protettive aspettano fino a 30 s per
  ritentativo). 3. una copertura del WORKER che fa dire «ridotta» a un bot ora lo ferma: va rifiutata anche quella? 4. verita'
  del paper = blotter del runner paper; runner paper riavviato -> nessuna decisione (conservativo). 5. annullo esterno di un
  ordine in attesa in Omega/Safe: oggi puo' essere ri-piazzato (Mike invece si ferma). 6. Safe paper sul canale (K7
  preesistente): cantiere a parte.
- D-12 (W3b) D1 «mercato del bot» = tutti i mercati su cui e' ARMATO (non solo dove ha ordini); D3 dopo l'intervento NON parte la
  chiusura forzata di fine finestra (posizione lasciata a mercato con CRITICAL); D4 media under: all'intervento si annulla anche la
  banca PERSIST; D5 scalper in PROVA non sa degli ordini manuali del ladder in prova (processo separato, paper non specchio su
  questo punto); D6 nessuna soglia minima (anche 2 EUR fermano); D7 durante la sospensione (verifica o DB giu') si rifiutano
  anche le chiusure del bot su quella selezione (alternativa: lasciar passare le sole chiusure).
- D-13 (banco, trovato verificando W3a) `omega_service._LAMBDA_CACHE` (usata anche dalla Safe) scade dopo 900 s di orologio di
  PARETE e il banco della Safe non la azzera fra scenari: in quale scenario si ricalcola il modello dipende dalla velocita' della
  macchina (oggi sposta solo una nota, decisioni identiche). Proposta: azzerarla fra scenari come RB-5 di Omega (solo banco).
- D-14 (cantiere 11) a) `pytest-xdist` nel `.venv` del PC (suite 291 -> 88 s nel cloud): installazione da autorizzare;
  b) `psutil` non e' in `requirements.txt`: senza, `--worker N` diventa 1 in silenzio (aggiungerlo o stampare una riga);
  c) lo scenario `riavvio` di Omega azzera solo 7 stati su 20 (un riavvio vero li perde tutti): cambiarlo cambia lo scenario;
  d) memoria per identita' delle liste convertite in `valuta` (-65 % dei livelli convertiti, codice di produzione): non fatta.
