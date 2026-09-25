# Strada unica: il banco sul canale, il profilo rapido, l'accensione in paper (25/09/2026)

Delegato Opus del coordinatore. Worktree su base `372158e`. Nessun commit, nessun push,
nessuna scrittura sul DB vero, nessun processo nuovo, strategie non toccate.
Il perimetro è il banco, il trasporto dell'ordine e gli interruttori.

## 0. In dieci righe

1. **F4 finita.** Con `--trasporto canale` il replay fa passare l'ordine di Safe e Omega dal
   **client vero** del bot (`PortaCanale`/`PortaCanaleOmega`, col suo thread). Il client parla con
   il **motore vero** (`MotoreOrdini`) su un socket in-process (`WsBanco`, busta JSON vera), il
   motore esegue il **`_dispatch` vero** del runner e l'ordine arriva al `Market` della
   `FlumineSimulation` del banco. Nessuna classe di laboratorio al posto di quelle di produzione,
   nessun fill fatto a mano.
2. **Parità raggiunta** sulla stessa registrazione (35760084), con coda e canale:
   - Safe `ordini-manuali`: 2 ordini su 2 e 2 righe su 2 identici; scarto di tempo +2,1 s su un
     ordine;
   - Omega `apertura`: 1 ordine su 1 e 1 riga su 1 identici; scarto 0,0 s.
   In entrambi i trasporti: 0 violazioni e 0 chiamate REST sul canale.
3. **Profilo rapido** `--scenari rapidi`: 11 scenari di trasporto in **4,3 s (Safe)** e **8,0 s
   (Omega)**. Con `--trasporto entrambi` si aggiunge la parità sulla partita intera: 151 s (Safe),
   118 s (Omega).
4. **Tre reperti veri** trovati dal banco e corretti:
   - **R-A (grave, avrebbe colpito la prima accensione)**: tempesta di `da_seq` nel client;
   - **R-B**: le aperture di Safe sotto il minimo erano rifiutate sul canale;
   - **R-C** (del banco, non del bot): gli ordini del motore erano invisibili ai controlli K4/K7.
5. **Reperto operativo, DA DECIDERE prima del paper (D-1)**: con l'interruttore acceso, il motore
   rifiuta ogni ordine su una partita che il runner NON segue. Oggi invece:
   - in paper: fill paper legacy;
   - in live: REST FOK.
6. Falsificazione:
   - 10 mutazioni sui test nuovi: 10 rosse, ripristino verificato con sha1;
   - 2 reperti rimessi nel codice: il profilo rapido diventa KO sullo scenario giusto.

## 1. Cosa fa ora → dopo (file:riga, worktree)

| Pezzo | Prima (24/09) | Dopo (25/09) |
|---|---|---|
| Aggancio al replay | `PortaBanco` esisteva ma nessun replay la usava | `MotoreReplay.esegui` chiama `trasporto.su_esegui` (`banco_comune.py:1675`): fuori da `trasporto.contesto` non fa niente, i replay di sempre restano identici riga per riga |
| Trasporto nel replay | solo REST servito da `MercatoFlumine` (gate chiuso) | `trasporto.contesto(bot, "coda" \| "canale")` (`trasporto.py:77`). Sul canale:<br>- accende `SAFE_/OMEGA_ORDINI_VIA_CANALE`;<br>- monta `PortaBanco` e il client vero sul `WsBanco` (`trasporto.py:178`);<br>- a ogni book: specchio → eventi `order` e adozione degli ordini nella vista di conto (`:211`, `:225`) |
| Client vero ↔ motore vero | assente | `WsBanco` (`porta_banco.py:135`): `send`/`recv`/`close` come `websockets.sync`; `PortaBanco.connetti` (`:334`) con controllo del token; `_dal_socket` (`:374`) = `LocalChannel._on_comando` |
| Riga `live` nel banco | `PortaBanco` solo PAPER: la riga live (quella del riferimento c3j/c3k) veniva rifiutata | `modo_processo="LIVE"` (`porta_banco.py:243`): il `ClienteLiveBanco` (`:86`) è il client simulato con un'etichetta di venue NON simulata. `_client_for_mode` di PRODUZIONE sceglie lui per le righe live e il simulato per le paper. Nessun soldo: nel banco non esiste un client reale (DICHIARATO) |
| Costo del banco | — | specchio solo sugli ordini vivi; blotter interi riletti solo dopo un comando o un passo del place-and-trim (`porta_banco.py:432`). Misurato: 2,8-4,2 s su 340-482 mila book |
| `certifica` | nessuna opzione di trasporto | `--trasporto coda\|canale\|entrambi`, `--tracce FILE.json` (`certifica.py:472`); rapporto di parità `_stampa_parita` (`:408`); `--scenari rapidi` (`:525`) → `trasporto_rapido.main_rapidi`. Default (senza `--trasporto`): identico a prima (`_lavora` `:246`) |
| Client di Safe/Omega (R-A) | `seq_visto` partiva da 0, il motore numera dall'epoch in ms: OGNI evento `order` apriva un «buco» e chiedeva `da_seq` dal seq 0. Il motore rimandava tutta la memoria (fino a 500 messaggi) e ognuno richiedeva di nuovo | `porta_ordini.py:343` (il primo seq è la base), `:613` (una richiesta alla volta), `:641` + `:410` (la risposta `da_seq` chiude la richiesta e, se incompleta dopo un riavvio del runner, riparte da `fino_a` e la conta) |
| Safe sotto il minimo (R-B) | canale: FOK anche sotto il minimo → il motore rifiuta `submin_non_percorribile`. Coda: `place_submin` senza FOK | `execution.py:463`: sotto il minimo nessun FOK; il motore usa la STESSA macchina place-and-trim del worker |

Moduli nuovi:
- `Betfair/stream/backtest/trasporto.py`: contesto, aggancio, traccia, `confronta`;
- `Betfair/stream/backtest/trasporto_rapido.py`: profilo rapido.

## 2. I reperti

- **R-A: tempesta di `da_seq`. Grave, avrebbe colpito la prima accensione in paper.**
  - Prova: sonda sul codice di base. Dopo l'ack con seq `base+1`, `seq_visto=0` e ogni evento
    dà `buchi+1` e `ultimo_buco=True`.
  - Col motore vero, OGNI evento chiedeva `da_seq(0)`. La risposta rimandava fino a 500 messaggi
    e ciascuno riapriva il buco: un'amplificazione senza fine sul canale 47331.
  - Corretta e inchiodata da 4 test (mutazioni M1-M3 rosse). Il profilo rapido la vede in R9.
- **R-B: aperture di Safe sotto il minimo rifiutate sul canale.**
  - Chi: le BACK sotto 2,00 € (per esempio una size ridotta dal cap di liquidità).
  - Con la coda partivano col place-and-trim; con il canale morivano in `error`.
  - Corretta (M4 rossa; il profilo rapido la vede in R8).
- **R-C: difetto del banco, non del bot.**
  - Col canale, i controlli di Safe dichiaravano «ordine inesistente a mercato»: K4 ×2808 nel
    primo replay canale (`strada_unica/prova_safe_manuali_v1.txt`).
  - Causa: `MercatoFlumine.ordini` conteneva solo gli ordini REST.
  - Ora gli ordini del motore si adottano col `customerOrderRef` VERO di flumine: K4 = 0
    (test + M9 rossa).
- **D-1 (decisione per l'utente, NON corretto): partita non seguita dal runner.**
  - Il motore non trova il mercato (`live_order_worker.py:627-628`, «market … non sottoscritto
    nel runner»). L'ordine NON parte, evento `rifiutato`, riga `error` (profilo rapido R10).
  - Oggi, sulla coda, con il gate chiuso Safe e Omega fanno invece:
    - in paper: fill legacy (`execution.py`, ramo `mode == "paper"`);
    - in live: REST FOK.
  - Conseguenza: a interruttore acceso **Safe e Omega operano SOLO sulle partite seguite**
    («Segui live»). Il runner sottoscrive tutti i mercati dell'evento seguito:
    `LIVE_MARKET_TYPES` non è impostata nel `.env`.
  - Le decisioni restano identiche; l'esecuzione sulle partite non seguite si ferma, e non in
    silenzio (attività `canale_inviato`, poi riga `error` con `canale_rifiutato`).
  - Opzioni:
    - (a) accettare così (fail-closed) e seguire le partite;
    - (b) nella porta, se l'evento non è `STREAMING` in `live_follow`, usare il trasporto di oggi
      (solo paper? anche live? D5 parla di canale giù, non di questo caso);
    - (c) auto-follow degli eventi dei bot (modifica di progetto).
- **Nota di tempo, non difetto**: Safe fa 3512 giri sul canale contro 3508 sulla coda. Sul canale
  il bot non resta fermo per il bet delay, quindi fa qualche giro in più. È la differenza
  dichiarata: la chiusura parte 2,1 s di mercato dopo, allo stesso prezzo e con la stessa size.

## 3. Comandi e durate misurate (PC condiviso con altri 6 delegati)

```
# profilo rapido (solo scenari di trasporto, secondi)
python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari rapidi --worker 1 --data-dir "<repo>/_live_raw"
python -m Betfair.stream.backtest.certifica omega     35760084 --scenari rapidi --worker 1 --data-dir "<repo>/_live_raw"
# profilo rapido + parità sulla partita intera (minuti)
python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari rapidi --trasporto entrambi --worker 1 --data-dir "<repo>/_live_raw" --tracce t.json
python -m Betfair.stream.backtest.certifica omega     35760084 --scenari rapidi --trasporto entrambi --worker 1 --data-dir "<repo>/_live_raw" --tracce t.json
# parità su uno scenario qualsiasi del bot
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari apertura --trasporto entrambi --worker 1 --data-dir "<repo>/_live_raw"
```

| Bot | Scenari rapidi (11) | Con parità (`entrambi`) | Riferimento del replay (coda, un solo scenario) |
|---|---|---|---|
| safe_base | **4,3 s** (4,5-4,7 s nelle altre corse), 11 OK | 150,7 s (187 s a orologio con gli import) | `ordini-manuali` 87 s; `base` 131 s (0 ordini) |
| omega | **8,0 s** (5,9-7,6 s), 10 OK + 1 N/A | 118,2 s (173 s a orologio) | `apertura` 74 s; `v4` 94 s (0 ordini) |

Scenari rapidi, uno per guasto:
- R1 accettato;
- R2 freno: quota 1,01 FOK;
- R2b mercato SOSPESO: primo book sospeso vero della registrazione;
- R3 parziale:
  - live FOK: ucciso con 0 abbinato;
  - Omega paper senza FOK: abbinato in parte, riga `pending` con i numeri veri;
- R4 canale giù (D5): apertura NON inviata e mai REST; chiusura sul REST di oggi; il client si
  ricollega da solo;
- R5 duplicato: `ref_gia_visto`, una sola esecuzione;
- R6 comando vecchio: consegnato 5 s dopo, `comando_scaduto`;
- R7 kill-switch: apertura rifiutata; chiusura con riduzione verificata eseguita;
- R8 sotto il minimo (Safe): fasi `inviato→parcheggiato→ridotto→accettato_betfair`, 1,50 € alla
  quota chiesta (Omega: N/A, lay fisso 1 € sopra lo 0,50);
- R9 sequenza: 0 `da_seq`, nessun buco;
- R10 mercato non seguito (D-1).

Regola D5 rispettata dal codice del 24/09 (verificata in R4): le USCITE ripiegano sul REST, le
APERTURE no.

## 4. Rapporto di parità (35760084, righe in modalità `live` come il riferimento c3j/c3k)

| | Safe `ordini-manuali` coda | Safe canale | Omega `apertura` coda | Omega canale |
|---|---|---|---|---|
| ordini | safe-t1 LAY 12,0×1,72 FOK; safe-t2 BACK 9,2×2,06 FOK | identici | omega-t1 LAY 300×5,26 FOK (CS sel 13) | identico |
| istante di mercato | 16:00:35.675 / 16:02:49.331 | 16:00:35.675 / 16:02:51.459 (+2,1 s) | 17:14:05.747 | 17:14:05.747 (0,0 s) |
| righe finali | #1 hedged lay 11,0×1,72; #2 open back 9,2×2,06 | identiche | #1 won lay 300×5,26 | identica |
| violazioni / decisioni | 0 / 3508 | 0 / 3512 | 0 / 467 | 0 / 467 |
| REST sul canale | — | 0 | — | 0 |
| client / motore | — | da_seq 0, buchi 0; 2 comandi accettati, 6 eventi | — | da_seq 0, buchi 0; 1 comando, 3 eventi |
| durata del replay | 63,8 s | 81,2 s (costo del banco 2,8 s) | 52,5 s | 58,0 s (costo del banco 3,2 s) |

Tracce complete:
- `strada_unica/tracce_FINALE_safe_rapidi_entrambi.json`;
- `strada_unica/tracce_FINALE_omega_rapidi_entrambi.json`.

Differenze ammesse e dichiarate (docstring di `trasporto.py`):
- i TEMPI: la coda blocca il bot per `latency + betDelay`, il canale no;
- il book su cui flumine esegue il pacchetto.

## 5. Accensione in PAPER (la decide e la fa l'utente)

**Stato certificato.** Sul banco la strada è certificata per trasporto: parità su 1 scenario
d'ordine per bot + 11 scenari di trasporto. **NON** è certificata la matrice completa
(`--scenari tutti --trasporto entrambi`), che tocca al coordinatore (§7).

**Prima di accendere:**
1. decidere D-1;
2. seguire in «Segui live» le partite su cui si vuole vedere operare il bot;
3. integrare questo lavoro su master (senza R-A, il primo evento avvia la tempesta di `da_seq`).

Variabili nel `.env`, nell'ordine. Ogni riavvio dell'app lo fa l'utente: i processi leggono il
`.env` all'avvio, verificato (`ESITI_ORDINI_CANALE=1` è visibile dopo l'import di `bot_service`
e `omega_service`).

| # | Variabile | Effetto | Cosa deve comparire |
|---|---|---|---|
| 0 | già presenti: `LIVE_ORDER_MODE=LIVE` (tetto), `ESITI_ORDINI_CANALE=1`; il token `LOCAL_CHANNEL_TOKEN` lo genera l'app e lo passa a runner e bot (`desktop/main.js:57`, `:232`, `spawnRunner` per tutti i servizi) | — | — |
| 1 | `MOTORE_ORDINI_CANALE=1` | il runner calcio monta il motore sul 47331 (`runner.py:1802-1806`) | log `[runner] motore ordini ATTIVO sul canale 47331 (diario …\_diario_ordini)` |
| 2 | `SAFE_ORDINI_VIA_CANALE=1` (solo calcio; il tennis resta sul suo `SAFE_TENNIS_…`, da NON accendere) | Safe calcio manda i comandi su `/comando/safe` | vedi sotto |
| 3 | `OMEGA_ORDINI_VIA_CANALE=1`, solo dopo aver visto Safe ok | Omega su `/comando/omega` (serve `execution_mode=auto`, che è il default) | vedi sotto |

Cosa deve comparire dopo il passo 2 (Safe):
- log `[safe.bot] ordini calcio via canale di comando ws://127.0.0.1:47331/comando/safe`
  (livello INFO);
- per ogni ordine, attività `canale_inviato` con `{trade_id, mode:"paper", ref:"safe-t<id>",
  seq, price, size, chiusura}`;
- sulla riga, `meta.canale_ref`, `canale_ack_seq`, `canale_ack_ms` e poi `canale_fase`;
- rifiuti: `canale_rifiutato` con il motivo del motore.

Cosa deve comparire dopo il passo 3 (Omega):
- log `[omega] ordini via canale di comando …/comando/omega`;
- le stesse attività e marcature di Safe.

«Sta passando dal canale», con età e fonte:
- la **fonte** è la riga del diario del runner, `DATA_DIR/_diario_ordini/<AAAA-MM-GG>.jsonl`:
  `{"tipo":"inviato","canale":"comando","attore":"safe","mode":"paper","ref":…,"parametri":{…"creato_ms":…},"ts_ms":…}`;
- l'**età** del comando è `ts_ms − parametri.creato_ms`, che deve stare sotto 3000
  (`max_eta_ms`);
- poi le righe `ordine` (il `customerOrderRef` vero) ed `esito`;
- nessuna riga nuova in `betfair_live_order_requests` per quel `trade_id`.

**Tornare indietro in 10 secondi:**
1. rimettere a 0 (o togliere) `SAFE_ORDINI_VIA_CANALE` / `OMEGA_ORDINI_VIA_CANALE`;
2. riavvio dell'app da parte dell'utente;
3. `MOTORE_ORDINI_CANALE` si spegne per ULTIMO.

Attenzioni:
- con il motore spento e un bot acceso, ogni apertura del bot riceve `motore_non_attivo`: rifiuto
  certo, nessun ordine, fail-closed;
- le righe in volo al riavvio:
  - paper: dopo TTL+60 s diventano `error` «canale_senza_esito» (nessun fill inventato);
  - live: si riconciliano su Betfair per ref.

**Mike e Safe tennis: solo diagnosi.**
- **Mike (F7)**: NESSUNA porta a comandi.
  - `execute_place` (`mike/service.py:559`) va sempre in REST (`:687`,
    `MIKE_USE_FLUMINE_QUEUE` assente);
  - la lay appoggiata `_piazza_resting_live` (`:1177`) chiama direttamente
    `omega_market.place_order_live`.
  - Serve: porta come Safe, appoggiate (persistenza, niente FOK), submin, `_segui_resting_live`
    dagli eventi, bet delay paper in casa spento sul canale.
  - Il banco rifiuta `--trasporto canale` per Mike, col motivo.
- **Safe tennis (F8)**:
  - il runner tennis NON monta il motore (grep `motore_ordini` in `Betfair/stream/tennis_live/`:
    0 risultati), quindi `/comando/safe_tennis` riceve `motore_non_attivo`;
  - il ref `safe-t<id>` non ha il prefisso `safe_tennis-` preteso dal motore
    (`motore_ordini.py`, `_gestisci`);
  - il controllo va fatto su `tennis_live_follow`.
  - `SAFE_TENNIS_ORDINI_VIA_CANALE` deve restare SPENTO.

## 6. Test e falsificazioni

- **Nuovo**: `Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py`, 17 test.
  - Coprono: client vero su `WsBanco`, token, LIVE/paper per client, R-A (4 test), R-B (2),
    parità (2), contesto (2), adozione (R-C), profilo rapido sulla registrazione vera
    (2, saltati se 35760084 manca).
  - Finti: `SimulatedClient` vero in `flumine.clients.Clients` vero; Market doppio del test del
    motore; DB e mercato del bot presi dal test della porta di Safe.
- **Falsificazione**: `strada_unica/falsifica.py`, esito in `strada_unica/falsificazione.txt`.
  - 10 mutazioni M1-M10, 10 ROSSE, 0 sopravvissute, ripristino dal contenuto salvato con sha1
    uguale.
  - `strada_unica/falsifica_rapidi.py` (esito in `falsificazione_rapidi.txt`): R-B rimesso → R8
    KO; R-A rimesso → R9 KO; exit 1; ripristino OK.
- **Test dei file toccati, tutti verdi**:
  - 256: porte Safe/Omega, execution, esiti canale, kill-switch, consapevolezza, hedge;
  - 249: bot_service Safe, B25, chiudi per bot, uscite Omega, kill-switch Omega;
  - 233: banco (identità, cert, certifica ×3, chiusura parziale, modo ordini, registro, submin,
    motore, porta banco).
- `test_submin_contratto_chiamanti` era rosso per un commento in `trasporto.py`: corretto.
- `test_latenza_logica_comando_place_sotto_20_ms` è rosso UNA volta sotto carico (p95 17-22 ms
  contro 20). È verde da solo e il motore non è toccato: test sensibile al carico, non una
  regressione.

## 7. Piano di verifica per il coordinatore

```
cd <worktree>; set SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x
git diff --stat   # 5 file modificati + 3 nuovi (+ AUDIT_2026-09-25/strada_unica/)
python -m pytest -q -p no:cacheprovider Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py Betfair/stream/tests/test_porta_banco_f4_2026_09_24.py Betfair/stream/tests/test_motore_ordini_2026_09_24.py Betfair/safe_strategy/tests/test_porta_ordini_f5_2026_09_24.py Betfair/omega/tests/test_porta_ordini_omega_f6_2026_09_24.py Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py
python AUDIT_2026-09-25/strada_unica/falsifica.py            # atteso: 10 ROSSO, 0 sopravvissute
python AUDIT_2026-09-25/strada_unica/falsifica_rapidi.py "<repo>/_live_raw"   # 2 ROSSO
python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari rapidi --trasporto entrambi --worker 1 --data-dir "<repo>/_live_raw"
python -m Betfair.stream.backtest.certifica omega     35760084 --scenari rapidi --trasporto entrambi --worker 1 --data-dir "<repo>/_live_raw"
```

Poi, uno per bot e in sequenza, i replay completi del riferimento SENZA `--trasporto`: devono
dare gli stessi numeri di c3j/c3k (l'aggancio è nullo fuori contesto). E, quando c'è tempo,
`--scenari tutti --trasporto entrambi` (lo lancia il coordinatore).

Mutazioni suggerite in direzioni che non ho provato:
- `trasporto.confronta` che ignora `rest_sul_canale`;
- `PortaBanco._specchio` che non toglie gli ordini chiusi da `_vivi` (deve cambiare solo il
  costo, non l'esito);
- `ClienteLiveBanco.paper_trade=True`.

## 8. Non verificato

- La matrice completa (`--scenari tutti`) nei due trasporti: non lanciata, per ordine.
- Parità in modalità PAPER sulla partita intera.
  - Sulla coda il paper di oggi nel banco è il fill legacy (non flumine), quindi il confronto non
    è significativo per costruzione.
  - Il paper sul canale è coperto da R3 (Omega paper) e dal test «live col cliente live e paper col
    simulato».
- Il vivo: nessun runner è stato avviato. Non verificati:
  - il log INFO dei bot (dipende dalla configurazione del logging);
  - il comportamento con il `LocalChannel` vero a 47331: nel banco il socket è in-process e il
    motore è chiamato subito, senza il thread `_ciclo`.
- Se esista un auto-follow degli eventi dei bot nel runner calcio: non cercato fino in fondo (D-1).
- I bot tennis, Mike e Safe tennis sul canale: solo diagnosi.

## 9. File

- Patch dei file modificati: `AUDIT_2026-09-25/strada_unica.patch` (git diff).
- File NUOVI, non nella patch:
  - `Betfair/stream/backtest/trasporto.py`;
  - `Betfair/stream/backtest/trasporto_rapido.py`;
  - `Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py`;
  - `AUDIT_2026-09-25/strada_unica/*`: referti delle corse, tracce JSON, script di
    falsificazione.
