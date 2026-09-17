# T2 — IL RACCORDO DI V3 DENTRO IL SERVIZIO (17/09/2026)

> **Che cosa e' cambiato, in una riga.** Fino a ieri `omega_v3.py` girava solo nel
> replay, **in ombra**: il servizio non lo chiamava e il banco misurava «cosa avrebbe
> fatto». Da oggi `omega_service.py` lo chiama davvero: con `strategy_version >= 3` la
> gamba la **sceglie, dimensiona e piazza V3** lungo la catena di produzione
> (riserva -> ordine -> conferma -> consapevolezza), e il banco certifica **quel**
> percorso.
>
> **Base di lavoro**, in due passi:
> 1. worktree `agent-af84954150e351fc6` partito da `1ee7624`, **mergiato su `master`
>    locale `3733f17`** (fast-forward, nessun conflitto). Suite: **976 verdi**.
> 2. su ordine del coordinatore, **integrati T3 (consapevolezza) e T1 (proposte)**, che
>    su master c'erano gia' non committati: `t3.patch` e `t1.patch` applicati
>    sull'albero pulito + i 5 file nuovi copiati dai worktree sorelle (sola lettura).
>    Suite con T3+T1 e senza il mio lavoro: **1.021**. Poi il mio diff rimesso sopra
>    con un merge a 3 vie (`git apply --3way`): **9 file puliti, 2 in conflitto**
>    (`omega_service.py`, `tools/replay_registrazioni.py`), risolti a mano **tenendo
>    tutto di entrambi** (dettaglio al §1-bis). Suite finale: **1.056**.
>
> **Niente commit, nessun `git add -A`, nessuna migrazione applicata, nessun processo
> avviato, nessuna chiamata Betfair, DB solo in lettura.** Per il merge a 3 vie ho
> usato un commit WIP **temporaneo**, subito annullato con `git reset --mixed HEAD~1`:
> `HEAD` e' tornato a `3733f17` e nel branch non resta nessun commit. Lo stash e' stato
> creato col tag `t2-raccordo-af84954150e351fc6`, riapplicato per SHA
> (`5d21d61...`) e **droppato** ritrovandolo per tag (mai `stash`/`pop` nudi: lo stack
> e' condiviso).

---

## 0. IL MANDATO, E COME E' CAMBIATO IN CORSA

Il brief iniziale chiedeva il raccordo di V3 **a parametri invariati** (default
`strategy_version=2`, k=2, due mercati). Alle 16:30 il coordinatore ha portato
l'ordine dell'utente («deve trovare lui la soluzione migliore, nessuna domanda») e ha
**deciso i default sui dati** (blocco «DECISIONI DEL COORDINATORE admin-b1 h16:40» in
`CRONOSTORIA.md`). Questo referto documenta **lo stato finale**, cioe' il mandato
aggiornato; dove il lavoro intermedio ha prodotto numeri che restano utili (per
esempio la battuta col cancello del 16/09) sono riportati come confronto.

**Le sette decisioni recepite** (e nient'altro: tutto il resto e' invariato):

| voce | prima | ora | dove |
|---|---|---|---|
| motore di default | `strategy_version=2` | **3** | `omega_config.py:214` |
| margine k | 2,0 | **1,11** (bias prudente in gioco, M4M5M6 §2.3) | `omega_config.py:230` |
| distanza dal punteggio | 1 gol | **2 gol** | `omega_config.py:262` |
| fascia di P | solo tetto 2 % | **[1 %, 2 %]** — `v3_p_min_pct` NUOVO | `omega_config.py:267-268` |
| tetti | 120/240/2.000/400 | **95/190/1.000/300** | `omega_config.py:249-252` |
| mercato | HALF_TIME_SCORE + CORRECT_SCORE | **SOLO Correct Score** | `omega_service.py:1348` |
| finestre | 25'-44' / 55'-85' | **1'-44' / 46'-85'**, due CELLE diverse | `omega_config.py:239-242` |

**Fuori perimetro, dichiarati**: quotazione passiva / quota viva / prezzo di riserva
`L*` (Fase 2 del `PROGETTO_OMEGA_V4`), CUSUM, qualunque cosa che non sia «prendere al
tocco» (FOK) sul percorso esistente.

---

## 1-bis. L'INTEGRAZIONE CON T3 (consapevolezza) E T1 (proposte)

Su `master` c'erano gia', non committate e certificate dal coordinatore, due lavori
sorelle. La mia patch non ci si applicava sopra. Li ho integrati nel worktree e ho
risolto i conflitti **tenendo tutto**; questi i punti dove si toccavano davvero:

| dove | conflitto | come l'ho risolto |
|---|---|---|
| `omega_service.svuota_le_cache` | T1 azzera la cache di `omega_proposte`, T2 quella delle tarature V3 | **tutte e due**, una dopo l'altra |
| `omega_service._v3_tarature` | T1 ha `omega_proposte.parametri_modello()`, T2 aveva un **secondo** caricatore dello stesso file | **tolto il mio**: ora `_v3_tarature` chiama il caricatore di T1 e aggiunge solo la tabella di k. Un file, un caricatore — se no la proposta d'uscita e la selezione d'ingresso parlerebbero di due modelli diversi |
| `replay._parametri_v3_dal_banco` | idem | delega a `PROPOSTE.parametri_modello()` (versione T1) |
| `replay.SCENARI` | T1 aggiunge `proposta-approvata` e teneva il vecchio `"v3"` in ombra | **tenuti `v4`/`v4-riavvio`/`v4-bot-fermo`/`v3`-legacy di T2 + `proposta-approvata` di T1**; la voce `"v3"` in ombra di T1 e' caduta (il raccordo l'ha superata) |
| `replay.OmegaCert.__init__` | T1 aggiunge i campi delle proposte, T2 `decisioni_v3`/`motore` | tutti e due |
| `replay`, corpo della classe | T1 aggiunge `_firma_le_proposte` / `_osserva_le_proposte` / `_aggiorna_le_approvazioni`; T2 **toglie** `_ombra_v3` | **tenuti i tre metodi di T1**, `_ombra_v3` resta tolto |
| `replay._componi_note` | T1 il blocco delle PROPOSTE, T2 quello di V3 sul percorso vero | tutti e due |
| `replay.certifica_scenario` | T1 la nota di `proposta-approvata`, T2 `v4-bot-fermo` in `bot-fermo` | tutti e due |
| `certificazione.py`, `omega_config.py`, `omega_engine.py`, `omega_v3.py`, `conftest.py`, `frontend/src/lib/omega.ts` | nessun conflitto | applicati puliti (G1(c)/G2/G3/G4 di T1 e il `_j3` corretto di T3 convivono col pavimento in A11 e con B1 che tace su V3) |

**Effetto misurato del `_j3` corretto da T3**: le **J3 x8** del mio referto precedente
**sono sparite** — vedi §3.6.

---

## 1. LA MAPPA — file : riga

### `Betfair/omega/omega_service.py` (il raccordo)

| dove | che cosa |
|---|---|
| `:215`, `:262` | `_CACHE_V3_TARATURE` + azzeramento in `svuota_le_cache` (le tarature lette da file sono di PROCESSO e non devono passare da uno scenario all'altro) |
| `:935` `_v3_tarature()` | parametri del modello vincente (`data/parametri_vincenti_2026-09-16.json`) e tabella di k, **una volta sola**; file assente = default del motore, mai un bot fermo |
| `:979` `_v3_finestra(params, half)` | la finestra della GAMBA: `v3_ht_*` per la gamba A, `v3_ft_*` per la B — sul minuto REALE del feed |
| `:990` `_v3_p_empirica(...)` | il VETO DI CODA (A12): stessa tabella del v2 (`omega_empirical`), `None` sotto `v3_empirical_min_n` e sugli aggregati (che una riga storica non ce l'hanno) |
| `:1037` `_v3_select(...)` | **la gemella di `_model_select` per V3**: finestra -> stop-loss -> book -> catena lambda -> `E.seleziona_v3` -> tetti. Ritorna `(candidato, audit, motivo)` e ogni motivo sta in `certificazione.MOTIVI_V3` |
| `:1147` `_v3_esposizione_di_partita(db, ev)` | UNA lettura per due cose: liability gia' esposta (tetto di partita) e **celle gia' bancate** (due ingressi = due celle diverse). Lettura KO -> `inf` (fail-closed, I3) |
| `:1175` `_v3_selection_dal_candidato(cand, snapshot)` | il candidato nella forma che la catena conosce, **con la controparte vera del book** (`CandidatoV3` non porta la size lay: senza questo `_size_and_place` non saprebbe se il book regge l'ordine) |
| `:1271-1275` | lo stop-loss giornaliero e' quello del motore acceso: `v3_daily_loss_cap` con V3 |
| `:1318` | `v3_on` |
| `:1324-1329` | il pre-filtro d'orologio usa le finestre del motore ACCESO |
| `:1340-1343` | la finestra della gamba |
| `:1348` | **il mercato: sempre `CORRECT_SCORE` con V3** |
| `:1363-1394` | il ramo V3 completo: esposizione di partita -> `_v3_select` -> `_size_and_place` con `v3=parametri_v3(params)` |
| `:1559` `_size_and_place(..., v3=...)` | con `v3` la size e' lo **stake esatto**: un taglio per liquidita' o per tetto e' uno **SKIP**, mai un lay piu' piccolo. Il resto del percorso e' identico |

### `Betfair/omega/omega_v3.py` (il motore)

| dove | che cosa |
|---|---|
| `:430` `p_mercato_devigata(runners)` | la devigatura **spostata qui dal replay**: servizio e banco devono fondere con lo stesso metro, se no la certificazione non parla della decisione vera |
| `:587` `p_min` | il PAVIMENTO della fascia -> scarto `p_sotto_fascia` (`:660`) |
| `:615` `escludi` | la cella gia' bancata dalla prima gamba -> scarto `cella_gia_bancata` |

### `Betfair/omega/omega_engine.py`
`:1127` `seleziona_v3(..., finestra=, escludi=)` — la finestra la porta la **gamba**,
non il periodo: dal 17/09 le due gambe stanno sullo **stesso** mercato (`periodo='ft'`)
in due momenti diversi, e senza questo la gamba del primo tempo non aprirebbe mai.
`:1187` passa `p_min` ed `escludi` al motore.

### `Betfair/omega/certificazione.py`
- `:1247` **A11 guarda anche il PAVIMENTO di fascia** — buco trovato dalla
  falsificazione (§4): il tetto era controllato, il pavimento no.
- `:1438` `osserva` legge il **candidato** quando il motore e' V3: leggere `m.sel`
  faceva contare ogni gamba V3 **aperta** come uno skip «senza motivo» (`ft_cs:None`).
- **B1** (target di gamba) ora tace su V3: in V3 un target di gamba non esiste (lo
  stake e' fisso), e giudicarlo col metro del v2 era un falso positivo — trovato dal
  banco, 1 accusa per scenario sulla sintetica.

### `Betfair/omega/tools/replay_registrazioni.py` (il banco)
- **`_ombra_v3` TOLTA** (~110 righe). Motivo: con V3 acceso il v2 **non sceglie piu'
  niente**, quindi non c'e' piu' una seconda decisione da confrontare sulla stessa
  occasione; e tenere l'ombra avrebbe prodotto momenti V3 **doppi** (uno dal percorso
  vero, uno dall'ombra), cioe' controlli contati due volte su una decisione sola. Il
  confronto v2/v3 resta **fra scenari** sulla stessa registrazione (`apertura` contro
  `v4`), ed e' quello riportato al §3.
- Nuova sonda su `omega_service._v3_select` (`:1539`), con firma **`**kw`** di
  proposito (vedi il reperto R2 al §6).
- Il momento `sizing` e quello `ordine` dichiarano il **motore** (senza, A9 e C5 non
  avrebbero mai un caso).
- Scenari nuovi: **`v4`** (i default di oggi), `v4-riavvio`, `v4-bot-fermo`, e **`v3`**
  ridefinito come «il cancello del 16/09» per confronto.
- Nuova nota di referto «**SCANSIONE DELL'EVENTO FALLITA**» (`:1869`).

### `frontend/src/lib/omega.ts`
Specchio della whitelist: tipo `v3_p_min_pct`, default nuovi, etichette del pannello
(gamba A / gamba B sul Correct Score). **`npm run build` NON e' stato eseguito**: nel
worktree non c'e' `node_modules` e non ho installato niente (vincolo dell'utente). La
modifica e' di soli dati/etichette; il build lo fa chi consegna.

### `Betfair/omega/conftest.py`
La fixture autouse **pinna `strategy_version=2` per la suite storica**. Vedi il limite
⊘-1 al §7: e' la scelta che ha reso possibile consegnare entro la scadenza, ed e'
dichiarata.

---

## 2. TEST

`Betfair/omega/tests/test_raccordo_v3_2026_09_17.py` — **NUOVO**, 36 test.
Finti: quelli del v2 (`test_omega_v2_2026_09_09`), stesse chiavi e stessi tipi del
vero; le righe della tabella storica hanno le chiavi VERE della RPC
(`league_id`/`bucket`/`score`/`target`/`result`/`n`).

Che cosa prova, in gruppi:
1. **l'interruttore** — il default di produzione e' 3 (letto da `_SPEC`, che la fixture
   non tocca); con V3 acceso `_model_select` non viene chiamato **mai**; con
   `strategy_version=2` non viene chiamato `_v3_select`;
2. **la gamba** — mercato `CORRECT_SCORE` anche per la gamba del primo tempo, `periodo`
   sempre `ft`, stake 1,00 EUR, `target` 0,00 sulla riga, audit col motore e i numeri;
3. **due celle diverse** — la seconda gamba esclude la cella della prima;
4. **il minuto e' quello del feed** — orologio a 95' e feed a 70': si entra; orologio a
   70' e feed a 45': no. E la gamba B non parte prima del 46';
5. **liquidita' e tetti** — sotto lo stake e' uno SKIP, non un lay piu' piccolo; tetto
   di gamba, di partita, aperto e stop-loss con **il motivo dichiarato**; lettura
   dell'esposizione KO -> non si apre;
6. **A8** — ogni motivo osservato sta in `MOTIVI_V3`, e ogni scarto porta il **margine
   vero** («margine 0,57x, ne serve 20x»);
7. **il veto storico** — alza la P, e sotto `n_min` non parla;
8. **falsificazione dei controlli** — A8, A9, A10, A11 (distanza, tetto, **pavimento**),
   A12, C5 sanno diventare rossi; e nel motore, `p_sotto_fascia` e `cella_gia_bancata`;
9. **i default** — i tredici numeri decisi il 17/09, uno per uno, piu' lo scambio della
   fascia rovesciata.

Suite, esecuzione finale **con T3 e T1 dentro**:

| | |
|---|---|
| `pytest Betfair/omega -q` | **1.053 passed + 3 skipped = 1.056** (1.021 con T3+T1 e senza il mio lavoro, **+35** miei) |
| `pytest Betfair/stream -q` | **1.443 passed + 24 skipped, 0 failed** |

> Durante il lavoro `Betfair/stream/tests/test_runner_lifecycle.py::test_second_instance_exits_immediately`
> e' fallito due volte con `WinError 10048` (porta 47399 occupata sul PC): **ambientale**,
> falliva anche da solo e passa nelle esecuzioni finali. Non tocca il mio perimetro.

---

## 3. REPLAY — PRIMA e DOPO

Comando (identico prima e dopo; le registrazioni non stanno in git, il banco legge
`LIVE_STREAM_DATA_DIR`):

```
LIVE_STREAM_DATA_DIR="...\python-database-automation\_live_raw" \
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti --worker 3
```

### 3.1 PRIMA del raccordo (base `3733f17`, codice di ieri)

| | |
|---|---|
| partite-scenario | 14 |
| pulite / con violazioni | **13 / 1** |
| violazioni | **2** — `J3 x2` su `rifiuti-betfair` (reperto NOTO del motore v2, gia' a referto il 16/09) |
| scenario `v3` | il servizio **ignorava** `strategy_version`: il **v2** apriva 1 gamba a quota 300 per 5,26 EUR, **1.572,74 EUR di liability**. V3 girava in ombra e non apriva (margine migliore **0,78x**, mediana 0,57x contro i 2 chiesti) |
| A9 / A10 / A11 / A12 / C5 | **mai sollecitati** (⊘): V3 non piazzava niente |

### 3.2 DOPO il raccordo — vedi §3.3 per la battuta finale

Sul solo `35760084`, con la prima versione del raccordo (cancello del 16/09, k=2):
**16 partite-scenario, 15 pulite, le stesse 2 violazioni `J3` di prima**. Lo scenario
`v3` e' cambiato come doveva: **azioni 2 -> 0**, ordini 1 -> 0, e i 121 momenti di
selezione portano tutti il motivo `nessun_candidato` con lo scarto di ogni runner —
**margine migliore 0,78x, mediana 0,57x**, cioe' gli **stessi numeri** che il referto
del 16/09 aveva misurato in ombra. Il raccordo non ha cambiato la risposta del motore:
ha cambiato **chi la da'**.

> Questo e' il controllo di non-regressione piu' importante del lavoro: il percorso di
> produzione riproduce, cifra per cifra, quello che l'ombra aveva misurato.

### 3.3 COI DEFAULT DEL 17/09: **V3 APRE SULLE REGISTRAZIONI VERE**

E' il risultato che cambia il quadro rispetto al 16/09. Con k = 1,11, la fascia
[1 %, 2 %] e il Correct Score guardato **dal 1'**, V3 trova le gambe che il cancello
di ieri non trovava. Scenario `base` (che coi default nuovi **e'** V3):

| partita | gambe | gamba A | gamba B | liability | esito |
|---|---|---|---|---|---|
| **35797769** | 2 | 1' sullo 0-0, `3 - 3` a **80** — P 1,068 % vs 1,188 %, **margine 1,11x**, EV +0,096 EUR, liability **79 EUR** | 71' sull'1-1, `3 - 2` a **40** — P 1,921 % vs 2,378 %, **margine 1,24x**, EV +0,183 EUR, liability **39 EUR** | max **79 EUR** | entrambe `won`, +0,95 EUR l'una |
| **35777617** | 2 | 3' sullo 0-0, `2 - 3` a **55** — P 1,519 % vs 1,729 %, **margine 1,14x**, EV +0,115 EUR, liability **54 EUR** | 46' sullo 0-0, `2 - 2` a **50** — P 1,589 % vs 1,902 %, **margine 1,20x**, EV +0,157 EUR, liability **49 EUR** | max **54 EUR** | entrambe `won`, +0,95 EUR l'una |
| **35760084** | **0** | — | — | — | 216 occasioni, **tutte** `nessun_candidato`; margine migliore offerto **0,65x** (mediana 0,64x). E' la partita finita 4-0: le celle raggiungibili sono poche e il mercato non le sovrapprezza |

**Gli scarti, per motivo** (e' la risposta a «perche' non entra», A8):
- 35760084: `senza_lay` x1.102 · `troppo_vicino_al_punteggio` x148 · `p_oltre_il_tetto`
  x17 · **margine insufficiente x14** · **`p_sotto_fascia` x12** · `liquidita_insufficiente` x3
- 35797769: `senza_lay` x390 · `troppo_vicino_al_punteggio` x83 · `p_oltre_il_tetto` x4 ·
  **`p_sotto_fascia` x2** · `liquidita_insufficiente` x1
- 35777617: `senza_lay` x19 · `troppo_vicino_al_punteggio` x14 · `p_oltre_il_tetto` x9 ·
  **margine insufficiente x3** · `irraggiungibile` x2 · **`p_sotto_fascia` x1**

> **Va detto con chiarezza, e non e' una buona notizia mascherata.** I margini reali
> sono **1,11x-1,24x**, cioe' appena sopra il pavimento: l'EV per gamba vale
> **+0,10 / +0,18 EUR** contro una liability di **39-79 EUR**. Sono le gambe che il
> pavimento k = 1,11 lascia passare **per costruzione** — il numero e' il bias prudente
> misurato, non un margine di sicurezza. Due partite non sono un campione: qui si
> certifica la **condotta**, non il rendimento.

**LE DUE ACCUSE, su 35797769** (`base` e `giornata-reale`, la stessa partita):

| controllo | accusa | lettura |
|---|---|---|
| **J3 x1** | «ref `omega-t2` non riconducibile a nessuna riga» | la gamba 2 e' stata rifiutata da Betfair (`live_not_matched`) e la riserva **cancellata** da `_leg_certain_failure`: a mercato non c'e' nessun ordine da riconciliare, ma il ref resta orfano. **E' il reperto J3 gia' a referto il 16/09** (x2 su `rifiuti-betfair` e `chiuso-fuori-app`), non una novita' del raccordo |
| **J6 x1** | «abbinato 0,0 su 1,0 e nessun `place_parziale`» | abbinato **zero** non e' un parziale, e' un no-fill: `place_parziale` non va scritto. **Stesso genere del falso positivo J6 gia' a referto il 16/09** |

**Non le ho aggiustate**: stanno nella famiglia J (percorso dell'ordine del motore di
oggi), fuori dal perimetro di questo lavoro, e il brief dice di riportare i reperti,
non di farli tacere. Vanno portate a chi ha in mano quella parte.

### 3.3-bis CHE COSA CAMBIA IL CANCELLO DI IERI (scenario `v3`, k = 2)

Sulla **stessa** registrazione `35797769`, col cancello del 16/09, V3 apre **una**
gamba sola: al 42' sull'1-1 banca `Any Unquoted Draw` a **110**, P 0,377 % contro
0,864 % — margine **2,29x**, EV **+0,535 EUR**, ma **109 EUR di liability**.

E' esattamente il compromesso che i nuovi default spostano:

| | cancello del 16/09 (k=2) | default del 17/09 (k=1,11, fascia 1-2 %, tetto 95 EUR) |
|---|---|---|
| gambe su 35797769 | 1 | 2 |
| cella | `Any Unquoted Draw` a 110 | `3 - 3` a 80 e `3 - 2` a 40 |
| margine | 2,29x | 1,11x e 1,24x |
| EV per gamba | +0,535 EUR | +0,096 / +0,183 EUR |
| **liability** | **109 EUR** | **79 e 39 EUR** |

Il tetto di gamba a **95 EUR** (con stake 1,00 EUR = quota lay massima 96) e' quello
che **esclude** la gamba a 110 di ieri: non e' un dettaglio contabile, e' la manopola
che decide quanto si rischia per ogni euro di EV. Con k = 1,11 si apre **piu' spesso**,
con **meno margine** e **meno liability** per gamba.

### 3.4 LA SINTETICA — dove V3 apre davvero

`_synth_omega_prezzo_migliore` (DICHIARATA finta: e' una partita che non e' mai
esistita, costruita nel formato nativo Betfair per provocare una condizione che le
registrazioni vere non contengono; **non conta in nessun conteggio di partite reali**).

**Scenario `v4` (i default di oggi): V3 apre DUE gambe, su DUE celle diverse dello
stesso Correct Score.**

| gamba | minuto | punteggio | cella | quota | stake | liability | P_nostra | p_implicita | margine | EV |
|---|---|---|---|---|---|---|---|---|---|---|
| A (`ht_cs`) | 1' | 0-0 | `3 - 3` | 15 | 1,00 EUR | **14,00 EUR** | 1,132 % | 6,355 % | **5,61x** | +0,781 EUR |
| B (`ft_cs`) | 46' | 1-0 | `3 - 2` | 15 | 1,00 EUR | **14,00 EUR** | 1,790 % | 6,355 % | **3,55x** | +0,682 EUR |

Le due righe percorrono **riserva -> ordine -> conferma -> settlement**: stato finale
`won`, `pnl` +0,95 EUR ciascuna, `chiesto=1.0 abbinato=1.0 residuo=None`.
`v4-riavvio` (riavvio a meta' partita) e `v4-bot-fermo` (bot fermato dalla UI con
posizione aperta) danno **le stesse righe** e **zero violazioni**: la posizione si
ritrova dal DB, e a bot fermo non si apre piu' niente ne' parte nessuna chiusura.

**Scenario `v3` (il cancello del 16/09) sulla stessa sintetica**: apre 1 gamba,
`Any Unquoted Draw` a 36, liability **35,00 EUR**, margine 185x — gli stessi numeri del
`REFERTO_V3_2026-09-16.md` §5.

**Controlli sollecitati sulla sintetica** (4 scenari): **A9 x12 · A10 x70 · A11 x70 ·
C5 x76 · G1 x1.278 · K1-K7 x1.064 ciascuno** — zero violazioni.

### 3.3-ter LA BATTUTA FINALE — 24 partite-scenario

```
LIVE_STREAM_DATA_DIR=...\_live_raw
python -m Betfair.stream.backtest.certifica omega 35760084 35797769 35777617 \
       _synth_omega_prezzo_migliore \
       --scenari v4,v3,v4-riavvio,v4-bot-fermo,esiti-ignoti,rifiuti-betfair --worker 3
```

**ESITO: 19 partite-scenario senza violazioni, 5 con violazioni, 10 violazioni
totali.** Le dieci sono **tutte della famiglia J** (percorso dell'ordine del motore di
oggi): **J3 x8** e **J6 x2**, sul genere gia' descritto al §3.3 — un ref rimasto orfano
dopo una riserva **cancellata** perche' Betfair non ha abbinato, e un «abbinato 0 su 1»
letto come parziale. **Zero accuse ai controlli di V3** (A8-A12, C5, G1) e **zero alla
famiglia K** (consapevolezza) in 5.373 verifiche per controllo.

| scenario | 35760084 | 35797769 | 35777617 | sintetica |
|---|---|---|---|---|
| `v4` | OK, 0 gambe | **KO** (J3 x1, J6 x1), 2 gambe | OK, 2 gambe | OK, 2 gambe |
| `v3` (cancello del 16/09) | OK, 0 gambe | OK, 1 gamba | OK, 0 gambe | OK, 1 gamba |
| `v4-riavvio` | OK, 0 | **KO** (J3 x1, J6 x1), 2 | OK, 2 | OK, 2 |
| `v4-bot-fermo` | OK | OK | OK | OK |
| `esiti-ignoti` | OK | OK | OK | OK |
| `rifiuti-betfair` | OK | **KO** (J3 x2) | **KO** (J3 x2) | **KO** (J3 x2) |

**Copertura dei controlli su questa battuta** (quante volte ognuno ha avuto un caso):

| | |
|---|---|
| **A8** (ogni non-ingresso ha un motivo dichiarato) | **x1.845** |
| **A9** (stake esatto) | **x72** |
| **A10** (margine k = 1,11) | **x108** |
| **A11** (distanza, tetto e **pavimento** di fascia) | **x108** |
| **C5** (tetto di gamba 95 EUR) | **x145** |
| **G1** (nessuna chiusura automatica) | **x11.604** |
| **K1-K7** (consapevolezza) | **x5.373** ciascuno |
| **A5** (fonte dei lambda, anche su V3) | **x1.953** |
| **C4** (a bot fermo non si apre) | **x1.007** |
| **E1** (mai due lay vive sulla stessa selezione) | **x5.283** |
| **F1 / F2** (settlement, esito ignoto) | x90 / x37 |
| **A12**, **G2** | **x0 — ⊘**, cause al §7 |
| A1-A4, A6, A7, B1, B3, C1-C3 (controlli del v2) | x0: con V3 acceso il motore di oggi non decide |

### 3.6 LA BATTUTA **DOPO** L'INTEGRAZIONE DI T3 E T1 (i numeri che contano)

**(a) `35760084`, `--scenari tutti` (18 scenari, ora ci sono anche `proposta-approvata`
e i tre di V4):**

```
ESITO: 18 partite senza violazioni, 0 con violazioni — 0 violazioni totali
```

> **Le J3 x2 di `rifiuti-betfair` sono CHIUSE**: il `_j3` corretto da T3 esclude il caso
> del rifiuto certo (`ok=False`, nessun `bet_id`), che era il falso positivo. Su questa
> registrazione J3 e J6 **non hanno piu' nessun caso** (x0).
> V3 su `35760084` continua a non aprire: 216 occasioni, tutte `nessun_candidato`,
> margine migliore **0,65x** — e la nota ora stampa correttamente «contro i **1.11x**
> richiesti» (⊘-10 chiuso).
> Controlli: **A8 x3.362 · G1 x7.913 · K1-K7 x466** ciascuno, zero violazioni.

**(b) `35797769`, `35777617`, sintetica × `v4,v4-riavvio,v4-bot-fermo,esiti-ignoti,rifiuti-betfair,proposta-approvata`:**

```
ESITO: 15 partite senza violazioni, 3 con violazioni — 6 violazioni totali
```

Le sei sono **J3 x3 + J6 x3**, tutte sulla **stessa** partita `35797769` e sullo
**stesso** singolo piazzamento, ripetuto nei tre scenari in cui V3 apre (`v4`,
`v4-riavvio`, `proposta-approvata`). **`rifiuti-betfair` e' pulito ovunque.**

**LA DIAGNOSI (come chiesto, senza aggiustare a caso).** Il caso NON e' il rifiuto che
T3 ha gia' escluso. Qui Betfair **accetta** l'ordine e il **FOK lo uccide senza
abbinare**: il banco (`banco_comune.place_order_live:577-584`) torna
`ok=True`, `bet_id=<id>`, `size_matched=0.0`; il servizio legge
`if not res.ok or res.size_matched <= 0` e chiama `_leg_certain_failure`, che
**cancella** la riserva. E' la condotta giusta: un FOK a zero non lascia niente a
mercato.

| controllo | perche' accusa | perche' **e' un falso positivo del controllo** |
|---|---|---|
| **J3** | la riga e' stata cancellata, il ref `omega-t2` non e' piu' riconducibile; l'esclusione di T3 chiede `ok=False` **e** nessun `bet_id`, e qui `ok` e' True | J3 esiste per garantire che un ordine **vivo** sia ritrovabile dalla riconciliazione. Un FOK ucciso a saldo zero non e' una posizione: non c'e' niente da riconciliare, esattamente come nel rifiuto. Manca **il secondo ramo** della stessa esclusione: `ok=True` **con `size_matched == 0` e stato terminale** |
| **J6** | il `quando` (`certificazione.py:1084-1089`) scatta su `ok=True` e `size_matched < size`, e 0 < 1 | **0 abbinato non e' un parziale, e' un no-fill**: `place_parziale` serve a mostrare al trader un **residuo vivo**, e qui non c'e' ne' abbinato ne' residuo. J6 dovrebbe partire da `size_matched > 0` |

**NON ho toccato ne' `_j3` ne' `_j6`**: sono il perimetro di T3 (famiglia J / percorso
dell'ordine), e il brief dice di riportare la diagnosi, non di far tacere il controllo.
La correzione proposta e' di **una riga per controllo** ed e' scritta qui sopra.

#### 3.7 DUE CORREZIONI DI MERITO, DOPO LA REVISIONE DEL COORDINATORE

**(1) I due falsi positivi J3/J6 sono CHIUSI** (perimetro esteso a
`certificazione.py` per queste due righe).

- **`_j3`, secondo ramo dell'esclusione** (`certificazione.py`, `_fok_ucciso_a_zero`):
  la riga assente non e' un buco anche quando `ok=True` **e** `size_matched == 0` **e**
  lo stato e' TERMINALE. L'elenco degli stati terminali (`STATI_TERMINALI`) sta **nel
  controllo**, non importato da `omega_service`: un controllo che prendesse l'elenco dal
  codice che giudica sbaglierebbe insieme a lui. **Se lo stato non e' leggibile o non e'
  fra quelli dichiarati, J3 ACCUSA**: un esito ambiguo e' un rischio.
- **`_j6`, il `quando`**: scatta solo con `size_matched > 0` e sotto il chiesto. Abbinato
  **zero** e' un no-fill, non un parziale: `place_parziale` serve a mostrare un residuo
  **vivo**, e li' non c'e' ne' abbinato ne' residuo. Il no-fill lo giudicano J1 e la
  famiglia K.

**Falsificazione, nelle due direzioni** (`test_omega_replay_2026_09_16.py`, 6 test nuovi):
(a) FOK a zero terminale con riga assente -> **J3 verde**; (b) ordine accettato con
`size_matched > 0` e riga assente -> **J3 rosso**; (c) `ok=True`, abbinato 0 ma stato
**EXECUTABLE** (ordine vivo) -> **J3 rosso**; stato vuoto o sconosciuto -> **J3 rosso**;
(d) J6 con abbinato 0,4 su 1 e nessun `place_parziale` -> **rosso**; con abbinato 0 ->
**nemmeno sollecitato**.

**Mutazione md5** (`certificazione.py`, md5 `2829a2ab4189aa4d120d7ab4a7aac6b4` prima e
dopo, identico): togliendo il vincolo dello stato terminale da `_fok_ucciso_a_zero`, il
test (c) passa da **verde a ROSSO**. Il vincolo serve davvero.

**(2) LA FASCIA VA SULLA p_IMPLICITA, non sulla P nostra** — reperto del coordinatore
sul mio diff, e aveva ragione. Il bias e' stato misurato **per fascia di p_implicita**
(`tools/k_in_gioco.py`, M4M5M6 §2.3): «p_impl 1-2 % = quote 47,5-95». Applicandola alla
P nostra passava la gamba **`3 - 2 @ 40`** (p_impl **2,38 %**), che sta nella fascia
2-5 % dove il bias prudente misurato vale **0,71**, cioe' **EV negativo**: proprio quella
da escludere.

- `omega_v3._seleziona`: `p_min`/`p_max` si applicano a **`p_imp`**, coi motivi
  **`p_impl_sotto_fascia`** / **`p_impl_oltre_fascia`**.
- Il tetto duro `p_nostra <= p_max` (semantica del 16/09) **resta** (`p_oltre_il_tetto`).
- Il cap di gamba 95 EUR **resta**.
- **A11** guarda la fascia su `p_implicita` del candidato (= `p_implied` dell'audit), con
  i due bordi.
- `omega_config` lo dice in chiaro: `v3_p_max_pct` fa **due cose diverse** (tetto della
  fascia su p_impl **e** tetto duro sulla P nostra), e il commento le distingue.

**Falsificazione del reperto**: `test_falsificazione_la_fascia_non_e_sulla_p_nostra` —
una cella a p_impl 2,38 % con P nostra 1,5 % viene **scartata `p_impl_oltre_fascia`**;
allargando il tetto di fascia al 5 % la **stessa** cella passa. Cioe' e' la fascia a
escluderla, non il margine: con la fascia sulla P nostra il test sarebbe verde a
sproposito.

### 3.8 GLI SCENARI DEL BANCO ORA DICHIARANO IL MOTORE

Col default a 3, gli scenari legacy giravano con V3 mentre le loro descrizioni
parlavano del v2 (target G=250, banda di quota 500): il referto certificava una cosa e
ne dichiarava un'altra. Sistemato:

| scenari | `strategy_version` | descrizione |
|---|---|---|
| `base`, `giornata-reale`, `apertura`, `paper` | **2 esplicito** | «MOTORE v2 LEGACY, per non perdere la copertura del vecchio motore» |
| `v4`, `v4-riavvio`, `v4-bot-fermo`, `proposta-approvata`, `v3` | **3 esplicito** | (non si affidano piu' al default) |
| `cap-stretto`, `bot-fermo`, `feed-stantio`, `esiti-ignoti`, `riavvio`, `manuale-e-bot`, `cashout-globale`, `rifiuti-betfair`, `chiuso-fuori-app` | **default** (= v3, il motore di produzione) | «CONDOTTA (motore di DEFAULT)», neutre rispetto al motore |

> **Da sapere leggendo i numeri**: su `35760084` V3 **non apre**, quindi li' gli scenari
> di CONDOTTA non sono sollecitati — nessuna posizione da fermare, riavviare, chiudere a
> mano o vedersi rifiutare. La condotta la esercitano `35797769`, `35777617` e la
> sintetica, dove V3 apre.

### 3.5 COME SI RIFANNO, ESATTAMENTE

```
# le registrazioni NON stanno in git: il banco legge LIVE_STREAM_DATA_DIR
set LIVE_STREAM_DATA_DIR=C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\_live_raw

# 1) il cuore: i due motori a confronto sulle tre partite e sulla sintetica
python -m Betfair.stream.backtest.certifica omega 35760084 35797769 35777617 ^
       _synth_omega_prezzo_migliore ^
       --scenari v4,v3,v4-riavvio,v4-bot-fermo,esiti-ignoti,rifiuti-betfair --worker 3

# 2) la batteria intera su una partita (17 scenari)
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti --worker 3

# 3) la falsificazione col metodo dell'md5
python Betfair/omega/tools/falsifica_raccordo_v3_2026_09_17.py
```

> **Nota sui tempi, misurata**: `--scenari tutti` su **tutte e quattro** le
> registrazioni sono 68 coppie evento-scenario e su questa macchina (4 core, 3 worker)
> costano **~1 ora e 45**. Le due registrazioni lunghe (35797769: 1,46 M tick;
> 35777617: 1,22 M tick) pesano ~4-5 minuti di orologio ciascuna per scenario. Ho
> **interrotto** quella battuta dopo 7 coppie per rientrare nella scadenza e l'ho
> rilanciata mirata (comando 1): i 7 risultati gia' prodotti sono quelli del §3.3 e
> sono riportati.

---

## 4. FALSIFICAZIONE (metodo dell'md5, sul codice VERO)

Script riproducibile: `Betfair/omega/tools/falsifica_raccordo_v3_2026_09_17.py`.
Per ogni difetto: si rompe **un** frammento nel file di produzione (in **binario**,
per non toccare nemmeno i fine riga), si fa girare il banco sulla sintetica, si
ripristina e si **verifica l'md5**.

**Rifatta sul codice POST-MERGE (con T3 e T1 dentro)**, stesso esito:

```
md5 PRIMA: omega_service.py 1643c8c42fcc476cb047bce9593e65a5
           omega_v3.py      f433b562c006602486f58742dcc06ed1
SANO: 1 partita senza violazioni, 0 violazioni totali
```

| difetto rotto nel codice vero | esito | md5 ripristinato |
|---|---|---|
| **A9** — `size = stake + 0,10` (lay da 1,10 invece di 1,00) | **A9 x4, 4 violazioni** | si' |
| **A10** — `k_usato` dichiarato x10 rispetto a quello applicato | **A10 x2, 2 violazioni** | si' |
| **A11** — pavimento `v3_p_min_pct` spento nel motore | **A11 x83, 83 violazioni** | si' |
| **A11** — distanza minima dal punteggio spenta | nessuna accusa — **⊘, causa sotto** | si' |
| **C5** — tetto di gamba spento (motore **+** difesa del servizio) | nessuna accusa — **⊘, causa sotto** | si' |
| **K1** — conferma col prezzo CHIESTO invece dell'ABBINATO | nessuna accusa — **⊘, causa sotto** | si' |

```
md5 DOPO:  omega_service.py 1643c8c42fcc476cb047bce9593e65a5
           omega_v3.py      f433b562c006602486f58742dcc06ed1
```
Identici: il codice consegnato e' esattamente quello provato. (La stessa batteria,
girata prima dell'integrazione di T3/T1, aveva dato gli stessi sei esiti sugli md5
`2d447acf…` / `e093d36a…`.)

**Le tre ⊘, con la causa** (non sono «passate», sono «non esercitabili li'»):
- **A11/distanza** e **C5**: sulla sintetica, coi default di oggi, la cella vincente e'
  a 3-4 gol di distanza e costa 14 EUR di liability. Spegnere la distanza o il tetto
  non cambia **quale** cella vince (vince la P piu' bassa che passa il margine), quindi
  il caso non si presenta. Sono coperte dai test di §2.8, che le fanno diventare rosse
  su un momento costruito.
- **K1**: il caso «abbinato a prezzo diverso dal chiesto» esiste nella sintetica solo
  nella deriva del `3 - 3` dopo il 56', e coi default di oggi la gamba B entra al 46',
  prima della deriva. Serve una sintetica con la deriva spostata: **non l'ho fatta**,
  e lo dichiaro.

**Il reperto piu' importante l'ha trovato proprio la falsificazione**: spegnendo
`p_min` nel motore il bot bancava celle sotto la fascia e **nessun controllo se ne
accorgeva**. Il pavimento e' stato aggiunto ad A11 (`certificazione.py:1247`) e la
falsificazione, rifatta, accusa **83 volte**.

---

## 5. STATI E FASI VISTI

- **stati del control**: `running`, `stopped` (scenari `*-bot-fermo`).
- **stati delle righe**: `pending` (riserva) -> `open` (conferma) -> `won` (settlement).
  Nello scenario `rifiuti-betfair` la riserva viene **cancellata** e la gamba torna
  tentabile col budget di `_leg_retry_allowed`.
- **fasi del servizio esercitate**: riconciliazione dei `pending`, poll flumine,
  settlement, risultati, manuale, missioni, scan+place, stats.
- **famiglia K (consapevolezza)**: K1-K7 girano **dopo ogni giro**, confrontando le
  righe di `omega_trades` con gli ordini VERI del banco, ref per ref.

---

## 6. REPERTI TROVATI STRADA FACENDO

**R1 — `osserva` contava le gambe V3 aperte come skip senza motivo.**
`certificazione.osserva` leggeva `m.sel`, che per V3 e' sempre `None` (V3 porta il
`cand`): ogni gamba **aperta** finiva nel referto come `ft_cs:None`, cioe' come una
gamba **non** aperta e per giunta senza motivo. Corretto a `certificazione.py:1438`.

**R2 — una sonda del banco con la firma copiata a mano ha spento un'intera partita, in
silenzio.** Aggiungendo un argomento a `_v3_select` la sonda del replay (che ne
ripeteva la firma) ha cominciato a sollevare `TypeError`; `scan_and_place_legs` cattura
l'eccezione **per evento** e va avanti, quindi il referto diceva tranquillamente «0
gambe, 0 violazioni» mentre **nessuna decisione veniva presa**. Due correzioni:
(a) la sonda ora ha firma `**kw` e non puo' piu' divergere;
(b) il referto **grida** se una scansione e' fallita (`replay_registrazioni.py:1869`).
E' il tipo di silenzio che una certificazione non puo' permettersi.

**R3 — B1 accusava V3 di un target che in V3 non esiste.** 1 violazione per scenario
sulla sintetica. B1 e' la regola §14.2 del v2: ora tace su V3 e lo dichiara.

**R4 — la tabella di k del 16/09 avrebbe reso inerte la decisione dell'utente.**
**Decisione del coordinatore (17/09): confermato, la tabella NON si passa piu'.** Il 2,0
del 16/09 e' stato misurato **pre-match** e in un contesto in cui il bias «non era
dimostrato»; k = 1,11 viene dalla misura **IN GIOCO** (M6), che e' piu' recente e piu'
pertinente. Scritto nel commento del codice.

`omega_v3` combina pavimento e tabella come `max(k_minimo, k_tab[secchio])`, e la
tabella misurata il 16/09 vale **2,0 in ogni secchio**: passarla avrebbe riportato il
margine a 2,0 **in silenzio**, cancellando il k = 1,11 deciso sui dati. Il servizio
**non passa piu' la tabella** (`omega_service.py:1103-1109`, dichiarato nel codice); la
tabella resta caricata e disponibile. **Va portato all'utente**: o si rimisura k per
secchio in gioco, o il pavimento resta l'unico metro.

**R5 — `omega_engine.selezione_da_v3` perde la controparte del book.** `CandidatoV3`
non porta `lay_size`, quindi la `Selection` usciva con `lay_size_available=0.0` e
`_size_and_place` non poteva sapere se il book reggeva l'ordine. Aggirato nel servizio
(`_v3_selection_dal_candidato`, `:1175`); la correzione pulita sarebbe dentro
`CandidatoV3`, **non l'ho fatta** per non toccare il motore certificato.

**R6 — `n_min_empirico` di `omega_v3._seleziona` e' un parametro MORTO.**
(Decisione del coordinatore: R5 e R6 **solo segnalati**, non si toccano.) E' dichiarato
nella firma e non viene usato nel corpo: il filtro sui casi minimi del veto storico lo
fa il provider che ho scritto nel servizio (`_v3_p_empirica`). Funziona, ma il motore
promette una cosa che non fa. **Non l'ho corretto** (e' logica di selezione): reperto.

**R7 — scenario `v3` legacy sulla sintetica: 65 selezioni, 1 riga.** Il cancello di
ieri sceglie la stessa cella (`Any Unquoted Draw`) per tutte e due le gambe, e
l'unique del database la rifiuta 64 volte con `already_reserved`. **Nessuna posizione
doppia** (I1 tiene), ma e' rumore: coi default di oggi non succede, perche' la seconda
gamba **esclude** la cella della prima.

---

## 7. LIMITI DICHIARATI (⊘) — quello che NON ho verificato

**⊘-1. DEBITO DICHIARATO (accettato dal coordinatore per stasera, da rifare file per
file). La suite storica di Omega gira con `strategy_version=2` pinnato.** Portare il
default a 3 fa cadere **126 test** scritti per il motore v2 (due mercati, size dal
target, green-up automatico): non li stavano collaudando male, stavano collaudando
**un altro motore**. Ho pinnato l'interruttore nella fixture autouse
(`conftest.py`), non nei 126 test, per consegnare entro la scadenza. **Conseguenza da
sapere**: quei test **non coprono piu' il default di produzione**. Il percorso V3 e'
coperto dai 36 test nuovi e dal banco; **flumine paper/live, green-up, chaos e audit
con V3 acceso non hanno test unitari**. Va rifatto file per file.

**⊘-2. A12 (veto storico) non e' sollecitato dal banco.** Le tabelle di transizione
sono un dato di DATABASE e non stanno dentro la registrazione di una partita
(`minute_transitions` e `ht_ft_transitions` sono elencate fra i «[NON ESERCITABILE]»
del referto). A12 e' coperto dai test con righe a chiavi vere, **non dal replay**.

**⊘-3. G2 (proposta di uscita) non e' sollecitato.** Le proposte nascono da una parte
del servizio che non e' in questo perimetro (`process_auto_greenup` / pagina Control
Room, altro delegato) e la migrazione `omega_proposte_uscita_2026-09-16.sql` **non e'
applicata**.

**⊘-4. `A4` (banda di quota `price_min`/`price_max`) NON si applica a V3, e non l'ho
cambiato.** In V3 la banda di quota non esiste: il limite e' il **tetto di liability
per gamba** (95 EUR con stake 1,00 EUR = quota lay massima 96). I momenti V3 portano il
`cand` e non la `Selection`, quindi A4 non li giudica. E' una scelta di progetto del
16/09, qui solo **dichiarata**.

**⊘-5. Falsificazioni A11/distanza, C5 e K1 col metodo md5**: il caso non si presenta
sulla sintetica coi default di oggi (§4). Coperte dai test.

**⊘-6. `npm run build` non eseguito** (nessun `node_modules` nel worktree, e non ho
installato niente). `npx tsc` e `npx vitest` **non eseguiti** per lo stesso motivo: la
modifica a `frontend/src/lib/omega.ts` e' di soli dati ed etichette, ma **va
ricompilata e ricontrollata da chi consegna**.

**⊘-7. Non esiste un parametro «solo Correct Score» ne' una «P minima» prima di oggi**:
il primo e' diventato **codice** (il mercato lo decide `strategy_version`, non un
parametro — se un domani si volesse tornare a due mercati serve un parametro nuovo), la
seconda e' `v3_p_min_pct`. Nessuno dei due e' stato inventato di iniziativa: sono
l'ordine del 17/09.

**⊘-8. `test_second_instance_exits_immediately`** (`Betfair/stream`) e' rosso per una
**porta occupata sul PC**, non per il codice.

**⊘-10. Una nota del referto mostra ancora «contro i 2,00x richiesti».** La riga
«V3, QUANTO MANCAVA» aveva il **2,00 scritto a mano** invece del `v3_k_minimo` dei
parametri: con k = 1,11 diceva un numero falso. **Corretto**
(`replay_registrazioni.py:1983`), ma i referti prodotti dalla battuta finale erano
gia' partiti: i processi figli avevano importato il modulo **prima** della correzione.
Va riletto tenendolo presente; il prossimo run mostrera' il numero giusto.

**⊘-9. Paper e live.** Il banco esercita il percorso **live su flumine** (con il gate
del runner assente si ripiega sul REST, che e' il percorso vero quando il runner e'
giu') e il percorso **paper legacy** (`E.paper_fill`, fill istantaneo su snapshot senza
bet delay) nello scenario `paper`. La divergenza P4 e' quella gia' dichiarata nel
piano: qui si misura, non si corregge. **Nessun ordine reale, nessuna chiamata Betfair.**

---

## 7-bis. FILE TOCCATI (e quelli che NON ho toccato)

**Miei, modificati** (9): `Betfair/omega/omega_service.py` · `omega_v3.py` ·
`omega_engine.py` · `omega_config.py` · `certificazione.py` · `conftest.py` ·
`test_omega_v3_certificazione_2026_09_16.py` (due finti adeguati al pavimento di
fascia) · `tools/replay_registrazioni.py` · `frontend/src/lib/omega.ts`.

**Miei, nuovi** (3): `Betfair/omega/tests/test_raccordo_v3_2026_09_17.py` ·
`Betfair/omega/tools/falsifica_raccordo_v3_2026_09_17.py` · questo referto.

**Di T3 e T1, portati dentro dal worktree (non miei, non modificati oltre ai conflitti
del §1-bis)**: `omega_db.py` · `test_omega_replay_2026_09_16.py` ·
`test_omega_ui_contratto_2026_09_11.py` · `test_omega_v3_2026_09_16.py` ·
`frontend/src/components/controlroom/SchedaChiusuraOmega.tsx` ·
`frontend/src/components/omega/ManualPanel.tsx` (+ il suo test) ·
`frontend/src/lib/omegaProposte.ts` (+ il suo test); **nuovi**:
`Betfair/omega/omega_proposte.py` · `test_omega_proposte_2026_09_17.py` ·
`test_t3_consapevolezza_2026_09_17.py` ·
`migrations/omega_proposte_coda_unica_2026-09-17.sql` ·
`migrations/omega_trades_status_cancelled_lapsed_2026-09-17.sql`.
**Le due migrazioni sono SCRITTE, NON applicate.**

**NON toccati** (vincolo dell'utente, verificato con `git status`):
`Betfair/safe_strategy/*` · `Betfair/omega/omega_market.py` ·
`Betfair/stream/backtest/*` (il banco e' condiviso) · `local_channel.py` ·
`live_order_worker.py` · `runner.py` · `frontend/src/lib/interruttori.ts` ·
`frontend/src/components/controlroom/*`. Non ho toccato la fase 1-bis di `run_once`
(`process_auto_greenup`, proposte) ne' `reconcile_pending` / `reconcile_decision` /
`_ordine_ancora_vivo`.

**Worktree**: nessuna junction e nessun symlink creati a `.venv` o
`frontend/node_modules`; nessun `pip install`, nessun `npm install`. Test e replay
girati col python del checkout principale
(`.venv\Scripts\python.exe`), con `LIVE_STREAM_DATA_DIR` puntato in **sola lettura**
alle registrazioni del principale. Nessun `git worktree remove`, nessuna cancellazione
ricorsiva: la rimozione la fa il coordinatore.

---

## 7-ter. COME PRENDERE QUESTO LAVORO

Il worktree `agent-af84954150e351fc6` contiene **T3 + T1 + T2 gia' fusi** su
`3733f17`, con i conflitti risolti (§1-bis). Due strade:

1. **La patch fusa** (T3+T1+T2 insieme, contro `3733f17`):
   `…\scratchpad	3_t1_t2_fusi.patch` (3.293 righe) — piu' i **8 file nuovi** non
   tracciati, da copiare dal worktree.
2. **I file interi** dal worktree: e' la via piu' sicura sui due file dove i tre
   lavori si sono toccati (`omega_service.py`, `tools/replay_registrazioni.py`).

`HEAD` e' a `3733f17`, **indice vuoto, stash vuoto, nessun commit**.

---

## 8. PUNTO DI RIPRESA / COSA CHIEDERE ALL'UTENTE

1. **J3 e J6 su un FOK ucciso** (§3.6): due falsi positivi dei controlli, correzione
   di una riga ciascuno, perimetro T3. Finche' restano, la battuta su `35797769` e'
   KO per un motivo che non e' del bot.
2. **R4 — chiuso dal coordinatore**: la tabella di k del 16/09 non si passa piu'
   (pre-match, bias non dimostrato); k = 1,11 viene dalla misura in gioco M6. Resta
   aperta la domanda se **rimisurare k per secchio in gioco**.
3. **⊘-1 (debito accettato)** — rimettere in piedi la copertura unitaria del percorso
   V3 su flumine paper/live, uscite (che in V3 sono «proposte») e chaos: oggi quei 126
   test girano col v2 pinnato.
4. **Le due migrazioni** di T3 e T1 (`omega_trades_status_cancelled_lapsed` e
   `omega_proposte_coda_unica`) sono **scritte e non applicate**: finche' non ci sono,
   G2/G3/G4 restano «non lo so» e l'uscita di V3 esiste solo come calcolo.
5. **Frontend** — `omega.ts` e' modificato da T1 e da me: `npm run build`, `npx tsc` e
   `npx vitest` li fa il coordinatore su master (nel worktree non c'e' `node_modules` e
   non ho installato niente).
6. **R5/R6** — segnalati, non toccati per ordine del coordinatore.
7. **Niente live e niente paper** finche' il coordinatore non ha **rieseguito di
   persona** diff, test e replay di questo referto.

---

## 9. STATO AL PARCHEGGIO (17/09, ordine dell'utente: crediti in esaurimento)

Lavoro **fermato su ordine**, in stato coerente. Nessun lavoro nuovo iniziato.

### I quattro punti dell'ultimo giro di revisione

| punto | stato | dove |
|---|---|---|
| **1. J3 / J6 (falsi positivi sul FOK ucciso)** | **FATTO e verificato** | `certificazione.py`: `STATI_TERMINALI` + `_fok_ucciso_a_zero` + secondo ramo in `_j3`; `quando` di `_j6` con `size_matched > 0`. 6 test nuovi in `test_omega_replay_2026_09_16.py` (casi a/b/c/d + stato illeggibile + elenco chiuso). **Mutazione md5 fatta**: tolto il vincolo dello stato terminale, il caso (c) passa da verde a ROSSO; md5 `2829a2ab4189aa4d120d7ab4a7aac6b4` identico prima e dopo. |
| **2. Fascia sulla p_IMPLICITA** | **FATTO e verificato** | `omega_v3._seleziona`: `p_min`/`p_max` su `p_imp`, motivi `p_impl_sotto_fascia` / `p_impl_oltre_fascia`; tetto duro `p_nostra <= p_max` invariato; cap di gamba invariato. `certificazione._a11` guarda `p_implicita` del candidato coi due bordi. `omega_config` con la doppia semantica di `v3_p_max_pct` scritta in chiaro. Test di falsificazione del reperto: `test_falsificazione_la_fascia_non_e_sulla_p_nostra`. |
| **3. Etichetta e nota del pannello** | **FATTO** | `frontend/src/lib/omega.ts`: «Motore v3 — il motore di default dal 17/09» + nota completa (solo Correct Score, due celle 1'-44'/46'-85', stake 1 EUR, fascia p_impl 1-2 %, k 1,11, cap 95/190/1.000/300, uscite a proposta, il bot lo accende comunque l'utente). Aggiornate anche le etichette di `v3_p_min_pct`/`v3_p_max_pct`. **Nel file non resta nessuna occorrenza di «ombra»** (verificato con grep). |
| **4. Scenari legacy pinnati a v2 + descrizioni** | **FATTO** | `tools/replay_registrazioni.py`: `base`/`giornata-reale`/`apertura`/`paper` -> `strategy_version=2` esplicito e descrizione «MOTORE v2 LEGACY…»; `v4`/`v4-riavvio`/`v4-bot-fermo`/`v3`/`proposta-approvata` -> `strategy_version=3` esplicito; i nove scenari di condotta restano sul default con descrizione «CONDOTTA (motore di DEFAULT)». |

### La battuta finale: **NON ESEGUITA** (interrotta su ordine)

E' l'unica cosa che manca. Era stata lanciata
(`35797769 --scenari tutti`, poi `35777617 --scenari tutti`, poi la sintetica, poi
`35760084 --scenari tutti`) ed e' stata **fermata prima del primo referto**: nessuno dei
quattro file di esito e' stato prodotto. **I numeri di replay in questo documento sono
quelli di PRIMA delle due correzioni di merito del §3.7** e vanno rifatti:

```
set LIVE_STREAM_DATA_DIR=...\python-database-automation\_live_raw
python -m Betfair.stream.backtest.certifica omega 35797769 --scenari tutti --worker 3
python -m Betfair.stream.backtest.certifica omega 35777617 --scenari tutti --worker 3
python -m Betfair.stream.backtest.certifica omega _synth_omega_prezzo_migliore --scenari v4,esiti-ignoti,rifiuti-betfair --worker 3
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti --worker 3
```

**Attesi, da verificare**: 0 violazioni ovunque (J3/J6 chiusi); su `35797769` la gamba
`3 - 3 @ 80` (p_impl 1,19 %) **dentro** e la `3 - 2 @ 40` (p_impl 2,38 %) **fuori**, con
motivo `p_impl_oltre_fascia`. Su `35760084` V3 non apre, quindi gli scenari di condotta
non sono sollecitati.

### L'ultimo comando eseguito, e il suo esito

```
python -m pytest Betfair/omega Betfair/stream -q -p no:cacheprovider
-> 2.503 passed, 27 skipped, 0 failed
```

### `git status --short` finale

`HEAD = 3733f17`, **indice vuoto, stash list vuota, nessuna junction** (`.venv` e
`frontend/node_modules` non esistono nel worktree). 18 file modificati + 8 non tracciati
(T3 + T1 + T2 fusi: elenco al §7-bis). **Nessun commit.**
