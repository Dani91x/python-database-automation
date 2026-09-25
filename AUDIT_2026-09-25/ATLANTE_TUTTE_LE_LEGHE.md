# Atlante Hazard: tutte le leghe con dati, a domanda, per la partita osservata (25/09/2026)

Delegato del coordinatore, worktree `agent-ab520d20ea240f66f`, base `84cf1e6`. Nessun commit, nessuna
scrittura sul DB vero, nessun bootstrap e nessun lancio reale. Brief applicato: quello RIVISTO
(atlante leggero e a domanda). I punti 1 e 4 del primo brief (bootstrap massivo) sono stati
sostituiti. Del bootstrap massivo non resta nulla: resta solo il calcolo per singola lega.

## 0. Numeri misurati sul DB (4 GET in sola lettura, 1.790 righe, sonda `sonde/misura_leghe_giorno.py`)

Fonte delle partite da osservare: `fixture_predictions`, cioè la stessa tabella che Safe e Omega già
leggono per le fixture del giorno (`omega_db.fixtures_for_window`, `bot_service._fixtures_window`).

| finestra | partite | leghe | leghe con stagioni a eventi | coppie lega-stagione (ultime 10 con eventi) | 2026 eventi=false | 2026 eventi=true | 2026 assente |
|---|---|---|---|---|---|---|---|
| ieri 24/09 | 93 | 39 | 35 | 203 | 21 | 11 | 7 |
| oggi 25/09 | 263 | 119 | 113 | 645 | 80 | 28 | 11 |
| finestra ±36 h | 335 | 135 | 127 | 736 | 91 | 31 | 13 |

Delle 21 leghe del v3, solo 1 è nella finestra di oggi. Due leghe della finestra non hanno nessuna
riga in coverage.

Rapporti usati per le stime, misurati sul v3 del 24/09: 494 richieste, 216.293 righe e 177 s per 210 coppie,
cioè 2,35 richieste, 1.030 righe e 0,84 s per coppia (circa 4 righe per partita).

## 1. «Cosa fa ora → cosa fa dopo»

### P1. Copertura guidata dalle partite osservate (sostituisce il bootstrap massivo)
- **Prima**: bootstrap con una lista di 21 id scritta a mano (`genera_atlante.py main`, `--leghe`).
  Altre leghe entravano solo tramite la filigrana globale e `--bootstrap-nuove 10` la notte. Le
  stagioni senza eventi venivano scaricate e scartate dopo.
- **Dopo**: nuovo modulo `Betfair/stream/scalper/atlante_a_domanda.py` (`MotoreAtlante`). A ogni ciclo:
  1. Una GET a `fixture_predictions` sulla finestra [ora-36h, ora+36h], 5 colonne, `and=(fixture_date.lt…)`,
     limit 3000 (`partite_osservate`).
  2. Le leghe nuove si ordinano per calcio d'inizio: prima quelle in gioco.
  3. Ogni lega nuova si prepara una volta sola (`prepara_lega`), in quest'ordine:
     - stato già in memoria o nel file locale: 0 richieste;
     - riga già su `hazard_atlas_leghe`: 1 GET, adottata;
     - altrimenti si calcola: 1 GET di coverage con **filtro server** `fixtures_events=eq.true`
       (`G.stagioni_con_eventi`, `genera_atlante.py:658`), poi il `bootstrap` sulle ultime `stagioni_max=10`
       stagioni con eventi, poi un upsert su `hazard_atlas_leghe`.
  4. Una lega senza nessuna stagione con eventi va in `senza_dati` e si riprova solo dopo 24 h.
- **Incrementale per lega** (`MotoreAtlante.incrementale`):
  - Legge solo le partite della finestra già finite (150' dopo il KO) che non sono ancora nello stato,
    con GET per `fixture_id` a blocchi di 100: una su `matches`, una sui gol di `match_events`, e una
    sugli eventi solo per gli 0-0.
  - Una partita FT senza eventi resta in attesa e si riprova ogni 60' fino a 34 h.
  - Se la coverage dice che per quella stagione gli eventi non arrivano, si chiude subito.
  - Uno 0-0 conta solo se ha almeno un evento: è la stessa distorsione che la soglia di copertura del
    v1 impedisce.
  - Le partite AET/PEN/CANC/PST/ABD/AWD/WO si chiudono.
  - Una partita che `matches` non ha ancora resta in attesa.
- **Efficienza del bootstrap per lega** (`genera_atlante.py:612-627`):
  - **Prima**: i gol si leggevano con `league_id=eq&season_year=eq&event_type=eq.Goal order=id`.
    `match_events` ha solo la pkey `id` e l'indice su `fixture_id` (verificato il 21/09, commento in
    `Ai Engine/ai_engine/db_adapter.py:84-89`), quindi la query scorreva la pkey su circa 10 M righe.
  - **Dopo**: la lettura avviene per `fixture_id=in.(…)` a blocchi di `LOTTO_GOL=200`, sull'indice
    `fixture_id` (misurato 2,6 ms ogni 200 partite). Le righe lette sono le stesse, quindi il metodo
    statistico non cambia.

### P2. Adattamento per lega senza soglia cieca
- **Prima**: `genera_atlante.py:60` con `MIN_FIXTURES_LEAGUE=300`. Sotto soglia la lega era esclusa
  da `by_league` e il lookup andava sul globale.
- **Dopo** (`genera_atlante.py:67-78`, `assembla` da 269):
  - Ogni lega con `n_fixtures>0` ha la sua griglia, shrinkata verso il globale con lo stesso `K_LEAGUE`
    (`:316`).
  - La soglia 300 resta solo per tre cose: il campione del globale (`base = coperte or stati`,
    invariato), il livello squadre (i profili si shrinkano verso il side_rate di leghe affidabili
    soltanto) e l'etichetta.
  - Etichette:
    - ogni cella porta `n` e `conf`;
    - ogni lega porta `n_fixtures`, `affidabile` e `confidenza`;
    - soglie di lega: alta ≥300 partite, media ≥100, bassa sotto;
    - soglie di cella: peso della lega `w=n/(n+K)`, alta ≥0,5 (n≥1500), media ≥0,2 (n≥375), bassa sotto.
  - Nel meta: `n_leagues_affidabili`, `globale.fonte`, `confidenza` (le regole scritte).
- **K_LEAGUE resta 1500.** Motivo: con 300 partite una cella popolata (per esempio 0-5', 0 gol, circa 5
  partite-minuto per partita) arriva a n≈1500, quindi w=0,5: la soglia del v1 e K sono già coerenti fra
  loro. Cambiare K cambierebbe anche le griglie delle 21 leghe in uso.
- **Invarianza provata in due modi**:
  - Test `test_lega_affidabile_identica_con_o_senza_le_leghe_piccole`: la lega affidabile, il globale e
    le squadre restano identici quando entrano leghe piccole.
  - Sonda `sonde/confronto_lookup_head.py`: `hazard_lookup` nuovo contro quello di HEAD sui file veri,
    **v2: 184.730 confronti, di cui 163.800 a livello squadre, 0 diversi; v3: 184.730, 160.200, 0 diversi.**
- «Premier 2015-2024 identica al v2»: un test su dati veri non esiste. Senza lo stato grezzo non si può
  rigenerare (il v3 usa 2016-2025 e differisce dal v2 al massimo di 0,0196 nella cella 5-10/3+, per le
  stagioni diverse, non per il metodo). L'invarianza del metodo è coperta dal test con il finto e dalla
  sonda qui sopra.

### P3. Dove gira (il thread di sync)
- **Prima**: `hazard_atlas_sync.avvia_se_abilitato` scaricava ogni 30' la versione assemblata dalla action.
- **Dopo**: `HAZARD_ATLAS_MODO` (`hazard_atlas_sync.py:129`) può valere:
  - `domanda`, il default: ogni `HAZARD_ATLAS_CICLO_S` secondi (default 600, minimo 120) un
    `MotoreAtlante.ciclo()` (`:175`);
  - `scarica`: il comportamento del 24/09, invariato.

  Resta tutto spento finché `HAZARD_ATLAS_SYNC=1` non viene impostato. Parametri da env
  (`parametri_da_env`, `:145`): `HAZARD_ATLAS_TETTO_CICLO` (10), `_TETTO_ORA` (40), `_PAUSA_LEGA_S` (5),
  `_STAGIONI` (10), `_GIORNI_INATTIVA` (7). `HAZARD_ATLAS_SCRIVI_DB=0` spegne le scritture.
- **Lega in preparazione**: il file live porta `meta.leghe_in_preparazione`, scritto prima di lavorare, così
  lo vede ogni processo. Il lookup usa il globale e lo dichiara.
- **Scritture**: il file live viene scritto in modo atomico solo se qualcosa è cambiato, o almeno ogni 12 h
  perché l'età dichiarata resti vera. Lo stato locale va in `Betfair/omega/data/hazard_atlas_stato.json`
  (aggiunto a `.gitignore`). Su `hazard_atlas_leghe`:
  - la lega appena calcolata si scrive subito;
  - gli aggiornamenti si scrivono **a blocchi ogni 6 h** (`scrivi_db_ogni_h`), perché una riga pesa
    50-100 KB di jsonb.
- **Leghe non osservate da 7 giorni**: non si aggiornano più (l'incrementale guarda solo la finestra, il
  ricontrollo stagioni solo le leghe attive). Restano nello stato e nell'atlante.
- Nessun flumine importato: verificato con `'flumine' in sys.modules → False` dopo l'import di
  sync e motore.

### P4. Globale e seme
- Il globale si stima sulle leghe affidabili dello stato solo se sommano almeno
  `MIN_FIXTURES_GLOBALE=10.000` partite (`genera_atlante.py:78`). Con 10k partite la cella meno
  popolata (85-90, 3+ gol) ha circa 4.500 partite-minuto, cioè un errore standard di circa 0,5 punti su
  p≈0,12.
- Sotto quella soglia si usa il globale del **seme v3** (`hazard_atlas_v3.json`, 24/09, 53.187 partite),
  dichiarato in `meta.globale`, incluso nell'etichetta con la sua data.
- Le leghe, squadre e scontri diretti del seme che lo stato non ha ancora restano disponibili, marcati
  `da_seme`. Nella nota compare «dal seme».
- **Divergenza dal brief, da decidere**: il brief dice «finché lo stato è vuoto»; io uso il seme finché le
  leghe affidabili sono sotto 10k partite. Motivo: un globale stimato su 1-2 leghe tirerebbe tutte le
  altre verso quelle.

### P5. Stagioni che avanzano
- `MotoreAtlante.stagioni_nuove`: una volta ogni 24 h, una GET di coverage per le leghe attive.
  - Le stagioni con eventi non ancora acquisite si acquisiscono con lo stesso bootstrap, solo per
    quella stagione.
  - Le stagioni recenti (anno-1 e successive) scartate o vuote si riprovano; le vecchie no.
  - Conta nel tetto orario.
- Il bootstrap ora registra `stagioni_acquisite`, `stagioni_vuote` e `stagioni_scartate`. Una stagione
  scartata e riprovata non si conta due volte in `n_discarded`.

### Consumatori (P3 del primo brief)
- `hazard_atlas.consulta_atlante` (`hazard_atlas.py:271`) accetta `league_id`, `home_id`, `away_id` e
  i nomi, minuto e gol. Restituisce `p`, `fonte` (chiave storica), `livello`
  (`squadra+lega`/`lega`/`globale`/`nessuno`), `n`, `confidenza`, `lega{coperta, in_preparazione,
  n_partite, confidenza, nome, affidabile, da_seme}`, `atlante` (etichetta), `eta_giorni` e `nota`.
- `hazard_lookup` (`:403`) ora è la sua forma corta: stessi numeri, provato dalla sonda.
- `_find_team` (`:206`) cerca prima per id, poi per nome. Con omonimi vince la squadra della lega della
  partita; se resta ambiguo non sceglie nessuna. Sul v2 non esistono omonimi, verificato: 632 nomi unici.
- Il livello squadre si usa solo su lega affidabile. Un atlante v1/v2 senza il campo `affidabile`
  mantiene il comportamento storico.
- Tipi degli id: l'id lega è un intero API-Football passato così com'è. Safe lo ricava da
  `resolve_lambdas`/`_lambdas_from_fixture`, Mike da `dossier["league_id"]`, e il lookup usa `str()`.
- Oggi **Safe e Mike passano i nomi Betfair delle squadre, non gli id**. `consulta_atlante` accetta gli
  id, ma il collegamento degli id non è fatto (vedi §5).
- «Lega non coperta» ora compare solo per una lega che nel DB non ha stagioni con eventi: 8 delle 135
  leghe di oggi, 2 senza coverage. Per le leghe non ancora preparate compare «in preparazione».

## 2. Comando e stima (nessun lancio fatto)

**Sul PC** (nel `.env`, poi riavvio dell'app da parte dell'utente):
```
HAZARD_ATLAS_SYNC=1
# default: HAZARD_ATLAS_MODO=domanda, HAZARD_ATLAS_CICLO_S=600, HAZARD_ATLAS_TETTO_CICLO=10,
# HAZARD_ATLAS_TETTO_ORA=40, HAZARD_ATLAS_PAUSA_LEGA_S=5, HAZARD_ATLAS_STAGIONI=10
```

**Primo giorno** (finestra di oggi: 127 leghe con eventi, 736 coppie, in media 5,8 per lega):

| voce | per lega | 127 leghe |
|---|---|---|
| GET | 2 + 5,8 × 3 ≈ 19,4 | ≈ 2.460 |
| POST (upsert) | 1 | 127 |
| righe | 5,8 × 1.030 ≈ 6.000 | ≈ 760.000 |
| tempo DB (ritmo v3) | ≈ 4,9 s | ≈ 10 min, più 10,6 min di pause |

Nella tabella: 2 GET per lega sono hazard_atlas_leghe e coverage, 3 GET per coppia lega-stagione sono
1 per le partite e 2 blocchi di gol.

Con i tetti (10 leghe per ciclo, 40 per ora) le 127 leghe sono pronte in circa 3,2 h, prima quelle che
giocano prima. Carico orario: circa 780 GET/h e circa 240k righe/h (circa 67 righe/s). Il bootstrap v3
del 24/09 (216k righe in 177 s, circa 1.220 righe/s) è passato senza incidenti. In più i gol ora si
leggono dall'indice `fixture_id` e non più dalla scansione della pkey.

**A regime** (stime, non misurate):

| voce | GET/giorno | righe/giorno |
|---|---|---|
| finestra | 144 | ≈ 48k (5 colonne) |
| partite finite (~300) | ≈ 10-15 | ≈ 1,5k |
| riprove in attesa | ≤ 1 ogni 60' per partita coperta | poche |
| leghe nuove (5-20, stima) | ≤ 400 | ≤ 120k |
| coverage | 1 | — |
| scritture su `hazard_atlas_leghe` | ≤ 4 flush | leghe toccate × 50-100 KB |

**Job notturno** (`.github/workflows/*` NON toccato; cosa dovrebbe cambiare):
```
python -m Betfair.stream.scalper.genera_atlante
  --stato-db --incrementale --solo-leghe-in-stato --filigrana-da-ora-se-assente
  --seme Betfair/omega/data/hazard_atlas_v3.json --scrivi-db
```
- Togliere `--bootstrap-nuove 10 --stagioni-indietro 10`.
- Con `--filigrana-da-ora-se-assente` il job non va più in rosso con «filigrana assente»: la prima notte
  fissa la filigrana al max id.
- `--solo-leghe-in-stato` aggiorna solo le leghe già calcolate dal PC. È la rete di sicurezza per le
  partite che la finestra non ha visto o i cui eventi sono arrivati dopo 34 h.
- Costo del job: legge tutte le righe `stato` (senza i fixture_id, circa 30-60 KB per lega) e scrive
  una versione (circa 5-8 MB); se ne tengono 7.
- Bootstrap manuale di una singola lega: `--bootstrap --leghe <id> --stagioni auto --stato-db
  --scrivi-db` (stagioni dalla coverage).

## 3. Modifiche (diff: `atlante_tutte_le_leghe.patch`, 8 file tracciati, +582/-115)

| file | cosa |
|---|---|
| `Betfair/stream/scalper/genera_atlante.py` | soglie e confidenze (:67-83, 252-266); `assembla` con tutte le leghe, `conf`, seme (:269-460); bootstrap con gol per fixture_id, `stagioni_acquisite`/`_vuote`, scarto non doppio (:600-655); `stagioni_con_eventi` (:658); `incrementale(..., solo_leghe_in_stato)` (:681); `_Scrittore.salva_leghe`/`salva_versione` (:791, :810); CLI `--solo-leghe-in-stato`, `--filigrana-da-ora-se-assente`, `--seme`, `--stagioni auto` (:894-960) |
| `Betfair/stream/scalper/hazard_atlas.py` | `ATLAS_V3_PATH`, `ATLAS_STATO_PATH` (:64-65); `_find_team` per id e omonimi (:206); `leghe_in_preparazione`, `consulta_atlante`, `_nota_consulta` (:264-400); `hazard_lookup` come wrapper (:403) |
| `Betfair/stream/scalper/hazard_atlas_sync.py` | `modo`, `parametri_da_env`, `crea_motore`, `giro_a_domanda`, `avvia_se_abilitato` in due modi (:129-215) |
| `Betfair/stream/scalper/atlante_a_domanda.py` | NUOVO, il motore (485 righe) |
| `Betfair/safe_strategy/opportunity.py` | `_hazard_check` usa `consulta_atlante` (:677); chiavi `livello`/`confidenza`/`n` solo con atlante presente; prefisso «in preparazione» (:694); dettaglio nella nota (:697). Soglie e decisioni INVARIATE |
| `Betfair/mike/dossier.py` | `live_frame` usa `consulta_atlante` (:303) e aggiunge `hazard_livello`, `hazard_n`, `hazard_confidenza`, `hazard_nota`; `hazard`/`combine_hazard` invariati |
| `Betfair/mike/service.py` | `hazard_n`, `hazard_nota` in `_LIVE_VOLATILI` (:458), perché cambiano ogni 5' e non devono provocare scritture |
| `Betfair/stream/tests/test_genera_atlante_2026_09_24.py` | il test «lega sotto soglia resta fuori» è RISCRITTO nel comportamento nuovo richiesto (entra, `affidabile=False`, confidenza bassa) |
| `.gitignore` | `hazard_atlas_stato.json` |

**Test nuovi**: `Betfair/stream/tests/test_atlante_a_domanda_2026_09_25.py` (15) e
`Betfair/safe_strategy/tests/test_atlante_note_livello_2026_09_25.py` (3). I finti sono PostgREST in
memoria (eq/in/gt/gte/lt/and, booleani `eq.true`) sulle colonne vere di `fixture_predictions`,
`api_coverage_by_season` (`leagues_mapper`), `matches`/`match_events` (`COLONNE_MATCH`/`COLONNE_GOL`) e
`hazard_atlas_leghe` (migrazione). Lo scrittore è il VERO `_Scrittore` con la sola `_req` finta.

**Falsificazione**: `sonde/falsificazioni.py` applica 27 rotture minime (M1-M26 più M2b) e ripristina
dalla memoria, mai con git checkout. **Tutte ROSSE**; al ripristino 30 test su 30 verdi.
Esito: `sonde/falsificazioni_esito.txt`.

| rottura | test che diventa rosso |
|---|---|
| M1 ricalcolo a ogni comparsa, M2 coverage senza filtro, M19 gol per lega/stagione | una volta sola |
| M2b coverage senza filtro | test dedicato alla coverage |
| M3 nessuna adozione dal DB | adozione dal DB |
| M4 niente attesa, M5 rilettura delle contate, M23 niente pausa di 60' | incrementale |
| M6 tetto orario ignorato, M7 priorità al contrario | tetti |
| M8 stagioni nuove mai cercate | stagione nuova |
| M9 in preparazione mai letto, M10 seme ignorato | lookup |
| M11, M12, M13 (squadre, id, omonimi) | squadre |
| M14 globale su tutte le leghe | invarianza |
| M15 soglia media spostata | confidenze |
| M16, M17 | notturno e CLI |
| M18 by_league solo sopra soglia | test riscritto |
| M20, M21 | note Safe |
| M22 | Mike |
| M24, M25 | coverage/matches |
| M26 | scrittura a blocchi |

**Suite dei file toccati** (URL finto esportato): 261 passati, 10 saltati (mike audit, respiro
scritture, dossier; safe atlante e opportunity; stream atlante, genera, theta ×2, banco comune).
Suite intere e replay: NON eseguiti (ordine del 24/09).

## 4. A video (esempi)
- **Safe, lega coperta**:
  - prima: `hazard coerente con l'atlante (verificato: modello 10.4% vs storico 11.4% [league], divergenza 9%; atlante del 24/09, 61234 partite)`
  - dopo: `... vs storico 11.4% [league] (lega, n=800, confidenza media), divergenza 9%; atlante del 24/09, ...`
- **Safe, lega che l'atlante sta calcolando**:
  - prima: `atlante: lega non coperta (4321), confronto con lo storico globale; ...`
  - dopo: `atlante: lega 4321 in preparazione, confronto con lo storico globale; ... [global] (globale, n=90000, confidenza alta) ...`
- **Safe, lega senza eventi nel DB**: nota invariata («lega non coperta»), con in più il dettaglio globale.
- **Mike, scheda live**: in più ci sono `hazard_livello` (`lega`), `hazard_n`, `hazard_confidenza` e
  `hazard_nota` (`storico Premier League (lega, 3800 partite) [n=800; confidenza media; atlante del 25/09, ...]`).
  La UI di Mike NON è stata toccata: i campi sono nel frame, la loro visualizzazione è da fare.
- **Omega**: usa solo `h2h_hint`, che resta invariato (il seme porta le coppie).

## 5. Non verificato e aperto
- **Nessun ciclo contro il DB vero.** Non sono verificati: la query `fixture_predictions` con `order`
  (la sonda l'ha provata senza `order`), la GET su `hazard_atlas_leghe` (tabella vuota) e i tempi reali
  per lega con i gol per `fixture_id`. Il primo lancio va osservato nei log `[atlante-domanda] lega i/N`
  (richieste, righe, secondi per lega).
- **Id squadra non collegati**: Safe (`opportunity._hazard_check`, `payload["home"]`) e Mike
  (`service.py:3340`, nomi) passano nomi Betfair, non API-Football. Il livello squadre scatta solo se
  i nomi coincidono. Per collegare gli id:
  - Safe: `_lambdas_from_fixture` (bot_service) ha `fx` con `home_team_id`/`away_team_id`;
  - Mike: `build_prematch` ha `fixture_id`.

  Non fatto, per restare nel perimetro.
- **Concorrenza PC/action** sulla stessa riga di `hazard_atlas_leghe`: vince l'ultimo che scrive.
  L'incrementale del PC (finestra di 36 h) ricopre ciò che la notte aggiunge per le leghe osservate.
  Non c'è un test di concorrenza.
- **Coerenza del dato**: una partita presente in `matches` ma non in `fixture_predictions` entra solo con
  la rete notturna o con l'acquisizione della stagione.
- **Reperto 5** (decisione dell'utente): nella finestra di oggi 91 leghe su 135 hanno la stagione 2026
  con `fixtures_events=false`. Per quelle leghe l'atlante si ferma alla stagione con eventi più recente
  (tipicamente 2025): le partite 2026 finite si chiudono senza contarle, e la stagione entra da sola
  quando la coverage passa a `true` (P5). Nel DB ci sono 303 leghe con 2026 a true su 1.095 (dato del
  coordinatore, non riverificato).
- **Stime a regime non misurate**: leghe nuove al giorno e dimensioni reali di file live e stato
  (stimati 5-8 MB e 10-15 MB).

## File nuovi
- `Betfair/stream/scalper/atlante_a_domanda.py`
- `Betfair/stream/tests/test_atlante_a_domanda_2026_09_25.py`
- `Betfair/safe_strategy/tests/test_atlante_note_livello_2026_09_25.py`
- `AUDIT_2026-09-25/ATLANTE_TUTTE_LE_LEGHE.md`, `AUDIT_2026-09-25/atlante_tutte_le_leghe.patch`
  (solo i file tracciati; i nuovi sono elencati qui)
- `AUDIT_2026-09-25/sonde/misura_leghe_giorno.py` (sola lettura del DB, usa il `.env` passato come
  argomento), `sonde/confronto_lookup_head.py`, `sonde/falsificazioni.py`,
  `sonde/falsificazioni_esito.txt`
