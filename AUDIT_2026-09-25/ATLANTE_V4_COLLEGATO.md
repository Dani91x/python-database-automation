# Atlante v4 (A*) collegato a Safe e Mike (25/09/2026 sera, ordine «D2: COLLEGALO!»)

Delegato del coordinatore. Worktree `agent-a7f69454de0f496bb`, base `2f04bc4` (master ≥ `000d8f6`).
Nessun commit, nessun push, nessuna scrittura sul DB. Soglie e decisioni delle strategie non toccate:
`hazard_warn`/`hazard_drop`, `combine_hazard`, Safe `engine.py`/`exits.py`, `omega_v3.py`, `mike/engine.py`.

## 0. Sintesi
- **Generatore e motore a domanda.** Accumulano lo stato v4 per lega **dalle stesse righe** del v3. Rispetto a ieri si
  legge una sola colonna in più (`extra:raw_json->fixture->status->extra`); le righe restano quelle. `assembla` scrive
  il blocco `atlas["v4"]` nel file live e nella versione `hazard_atlas`, accanto ai blocchi v3, che restano invariati.
- **Safe `_hazard_check` e Mike `live_frame`.** Chiamano `consulta_atlante_v4` con il **tempo (1T/2T) ricavato dal
  feed** (`score_raw.matchStatus`). Il ripiego sul v3 è dichiarato nella nota
  («atlante v3: recupero non modellato (motivo)»).
- **Parità col banco.** Si parte dalle stesse righe del DB. Il generatore di produzione e il motore a domanda da un lato,
  il candidato validato `candidati` A1+A2 dall'altro. Differenza massima ≤ 1e-6 su 3.100 stati (2.500 regolari e 600 di
  recupero 2T), e i blocchi v4 del motore e del generatore sono identici.
- **Falsificazione:** 24 rotture su 24 diventano rosse.
- **Omega:** nessun consumo di hazard, lo usa solo `h2h_hint`, che resta identico (provato). Non l'ho toccato:
  aggiungere un segnale sarebbe stato alterare la strategia.
- **Forza pre-partita: NON usata in live, ed è dichiarato.** Non passo i λ di `fixture_predictions` (punto (c) del
  brief). Il proxy Poisson-Elo del banco richiede gli id squadra API-Football, che Safe e Mike oggi non hanno: Safe
  passa i nomi Betfair e il dossier di Mike non ha `home_team_id`. Quindi oggi il v4 collegato è **A1+A2**. Costo
  misurato nel banco (referto di validazione §4):
  - insieme pulito: 0,30488 contro 0,30477 di A*;
  - regolari sicuri: A1 −0,00038 contro A* −0,00067 rispetto al v3.

  Vale comunque meglio del v3 ovunque. Per usare la forza servono gli id squadra collegati: è una decisione dell'utente.

## 1. Generatore / stato per lega: prima → dopo
| dove | prima (HEAD `2f04bc4`) | dopo |
|---|---|---|
| `genera_atlante.py:616` `COLONNE_MATCH` | 13 colonne (`:542`) | + `extra:raw_json->fixture->status->extra`. Non esiste una colonna vera: `fixtures_backfill.py` salva solo `status_short/long/elapsed`. `minute_extra` era già in `COLONNE_GOL` |
| `genera_atlante.py:186-219` `stato_lega_vuoto`, `_v4_vuoto`, `aggiungi_v4` | solo v3 | lo stato nuovo nasce con `"v4"` (`atlante_v4.stato_v4_vuoto`: stagioni, `quota_extra`, `affidabile`, `scarti`). `aggiungi_v4` somma la partita **solo dopo** che `aggiungi_partita` l'ha contata: l'idempotenza è quella del v3, senza una seconda lista di fixture_id. Uno stato senza `"v4"` non viene toccato |
| `genera_atlante.py:666` `_sequenze` | `aggiungi_partita` (`:585`) | + `aggiungi_v4` (bootstrap e incrementale notturno) |
| `genera_atlante.py:724-735` `bootstrap` | `_sequenze` (`:645`) | reperto 6: si calcola la quota dei gol di fine tempo con `minute_extra` **sulla stagione intera, già letta**, e si passa `affidabile_v4` |
| `genera_atlante.py:517-546` `assembla` + `assembla_blocco_v4` | ritornava i soli v3 (`:474`) | + `out["v4"]` e `meta["v4"]`. `stagione_rif` = ultima stagione contata + 1, come nel banco. Il seme v3 resta per il globale v3 |
| `atlante_a_domanda.py:376` incrementale | `aggiungi_partita` (`:363`) | + `G.aggiungi_v4(st, m, gg)`. L'affidabilità si decide sui conteggi **cumulati** della stagione nello stato |
| `atlante_a_domanda.py:205` `_da_db` | adottava qualunque stato (`:203`) | uno stato senza `v4` non si adotta |
| `atlante_a_domanda.py:237,421` `ciclo` | `nuove` = leghe non nello stato (`:406`) | anche le leghe nello stato **senza v4**: si ricalcolano per intero, con lo stesso tetto. Nel frattempo i consumatori usano il v3 e lo dichiarano |
| `atlante_v4.py:145-218` | – | `affidabile_da_quota`, `stato_v4_vuoto`. `aggiungi_partita_v4(registra_fixture=False)` salva i conteggi come interi (stessi valori) |
| `atlante_v4.py:258-275` `assembla_v4` | con nessuna lega affidabile il globale era NaN | si ripiega su tutte le leghe, come fa il v3. In meta: `n_partite_affidabili`, `globale_solido` (≥ 10.000, stessa soglia del globale v3). L'etichetta `affidabile` per lega resta ≥ 300 |
| `validazione_hazard/candidati.py` | `from scipy.optimize import ...` in testa | scipy caricato pigramente: il processo del feed non lo carica (provato) |
| `validazione_hazard/raccogli.py:44` | `extra` ripetuto | tolto, perché ora sta in `COLONNE_MATCH`. La lista delle colonne è la stessa di prima |
| `.github/workflows/hazard_atlas.yml` | nessun `pip install` | step `pip install numpy==2.4.6`. Senza questo step il job notturno fallirebbe al primo stato v4, perché lo stato v4 si conta con numpy |

## 2. Feed → tempo (misurato, non presunto)
Sonda `sonde/sonda_minuto_ips_recupero.py` sulle **60 registrazioni vere** `_live_raw/*/*.scores.jsonl` (7.539 righe).
- **1T:** il `matchStatus` è `KickOff`, mai `FirstHalf` (che compare solo nei sintetici).
  - Nel **recupero del 1T il minuto è CUMULATO**: `timeElapsed` 46, 47, … con `elapsedRegularTime` 45 e
    `elapsedAddedTime` = j. Non è un 45 fisso.
  - Senza il tempo, un 46' del recupero 1T è indistinguibile dalla ripresa. È ciò che faceva il v3: al 47' del recupero
    1T usava la cella 45-50.
- **Intervallo:** `FirstHalfEnd`, e `timeElapsed` **riparte da 45 e continua a contare** (35674515: da 45 a 56 in 13').
- **2T:** `SecondHalfKickOff`. Nel recupero `timeElapsed` 91.. con `elapsedRegularTime` 90 e `elapsedAddedTime` =
  minuto − 90. È il recupero **giocato**: quello annunciato non esiste nel feed, quindi resta la stima per lega. I
  consumatori non hanno «minuti di recupero noti» da passare.
- **Stato vecchio:** 35833626 `KickOff` con `timeElapsed` 88 ed `elapsedRegularTime` 35.
- **Regola** (`atlante_v4.tempo_da_stato_ips`, `:375`; `tempo_da_payload`, `:413`):
  - `secondhalf`/`extratime`/`penalt` → 2;
  - `firsthalfend`/`halftime` → 1;
  - `firsthalf`/`kickoff` → 1 solo se il minuto è ≤ 60, altrimenti lo stato è vecchio;
  - senza stato: `elapsedRegularTime` 45/90 con `elapsedAddedTime` → 1/2; poi minuto < 45 → 1, ≥ 90 → 2, altrimenti
    None (convenzione del v3).
- Test con i record IPS veri copiati (chiavi identiche): `test_tempo_dai_record_ips_veri` (13 casi) e
  `test_minuto_46_del_recupero_1T_non_e_la_ripresa`.

## 3. Consumatori: prima → dopo
| dove | prima | dopo |
|---|---|---|
| Safe `opportunity.py:686` | `consulta_atlante(atlas, minute, gol, lega, home_team, away_team)` (`:677`) | `consulta_atlante_v4(..., tempo=tempo_da_payload(payload), home_team, away_team)`. Le squadre servono solo al ripiego v3. Niente λ. `out` porta anche `versione`, `fase`, `recupero_atteso_min`. Decisione: le stesse righe `div > hazard_drop` / `> hazard_warn`, invariate |
| Safe note `:698-734` | `…divergenza X%; atlante del …` | `…divergenza X%; atlante v4, <fase>[, recupero atteso ancora N']; atlante del …` oppure `atlante v3: recupero non modellato (<motivo>)` |
| Mike `dossier.py:309` | `consulta_atlante(...)` (`:303`) | `consulta_atlante_v4(..., tempo=tempo_da_payload(payload+minute))`, più `hazard_versione`, `hazard_fase`, `hazard_recupero_atteso_min`. `combine_hazard` e le soglie del timing sono invariati (provato) |
| Mike `service.py:467` `_LIVE_VOLATILI` | – | `hazard_recupero_atteso_min` è volatile (cambia a ogni minuto del recupero). Versione e fase non lo sono |
| Omega | solo `h2h_hint` | invariato (test `test_omega_h2h_invariato_col_v4`) |

**Ripiego v3** (`atlante_v4.py:450-497`). Vale solo se l'atlante porta anche i blocchi v3: in produzione sempre, nel banco
mai, quindi la parità del banco non cambia. I motivi:
- blocco v4 assente;
- lega non ancora nel v4 ma presente nel v3;
- lega non nel v4 e globale v4 non solido;
- lega del v4 non affidabile (< 300 partite) e globale v4 non solido.

Nel ripiego il minuto al v3 è quello di sempre, quindi i numeri sono quelli di ieri.

### Note prima/dopo (dati sintetici del test, `sonde/esempi_note_v4.txt`, lega 39, 93' 1-1)
- Safe prima:
  > `hazard coerente con l'atlante (verificato: modello 8.4% vs storico 11.3% [league] (lega, n=510, confidenza media), divergenza 25%; atlante v3: recupero non modellato (blocco v4 assente); atlante del 25/09, 1272 partite)`
- Safe dopo:
  > `hazard coerente con l'atlante (verificato: modello 8.4% vs storico 7.6% [league] (lega, n=427.0, confidenza media), divergenza 11%; atlante v4, recupero_2T, recupero atteso ancora 3.48'; atlante del 25/09, 1272 partite)`
- Mike prima:
  > `storico lega 39 (lega, 636 partite) [n=437; ...] [atlante v3: recupero non modellato (blocco v4 assente)]`

  `hazard_atlas` 0,1348.
- Mike dopo:
  > `storico v4 lega 39 (lega, 636 partite) [recupero_2T; recupero atteso ancora 3.48'; forza non usata; confidenza bassa; ...]`

  `hazard_atlas` 0,0876.
- p3 v3 → v4 (stessi dati sintetici):

  | stato | v3 | v4 |
  |---|---|---|
  | 65' 2 gol | 0,0817 | 0,0763 |
  | 87' 1 gol | 0,1348 | 0,0785 |
  | 93' | 0,1348 | 0,0876 |
  | 97' | 0,1348 | 0,0538 |
  | 47' recupero 1T | 0,0709 (cella 45-50) | 0,0941 (cella 40-45) |

  Sono gli stessi effetti del referto di validazione: il clamp gonfiava il valore a fine tempo.

## 4. Costi (misurati)
`sonde/costo_v4_collegato_esito.txt`: lega sintetica di 10 stagioni × 380 partite, PC di sviluppo.

| voce | misura |
|---|---|
| righe lette | **invariate** (3.800 = 3.800), nessuna richiesta in più |
| byte della risposta `matches` (finto) | +12,4 B a riga (+4,6%) |
| **DB vero, sola lettura, 4 GET** (`sonde/sonda_db_colonna_extra_esito.txt`, Premier 2024) | 380 righe, 108.184 → 112.183 B (+3,7%). Tempi: prima 484/250 ms, dopo 308/190 ms, cioè nessun aumento misurabile. `extra` presente in 327 righe su 380. L'alias funziona con la codifica del `LettoreDB` |
| CPU del bootstrap di una lega grande | 2,4 s → 7,5 s (+5,1 s, +1,3 ms a partita). Quasi tutto è `stati_partita` del banco, usato così com'è per la parità |
| assemblaggio | 1 lega 0,9 → 3,3 ms; 20 leghe 9,4 → 27,3 ms |
| consultazione `consulta_atlante_v4` | 0,056 ms |
| stato v4 per lega (jsonb) | 10,8 KB (≈1,1 KB a stagione), contro 3,5 KB del v3 più 34 KB di fixture_id |
| blocco v4 per lega nel file live | 3,4 KB (20 leghe: file da 149 a 221 KB) |

I tetti del motore sono invariati (10 leghe a ciclo, 40 l'ora, pausa 5 s). Il carico sul DB è invariato: 0 righe in più.
Il costo è di CPU: il giorno 1, circa 127 leghe × 5 s ≈ 11 min in più, spalmati sulle ≈ 3,2 h del riempimento.

## 5. Test e falsificazione
- **Nuovo:** `Betfair/stream/tests/test_atlante_v4_collegato_2026_09_25.py`, 32 test. Coprono:
  - la parità col banco;
  - la parità tra motore e generatore;
  - il globale non solido con ripiego dichiarato;
  - il v4 popolato da `status.extra` e `minute_extra`;
  - la stagione senza extra non affidabile, nel bootstrap e nell'incrementale cumulato;
  - la lega col vecchio stato ricalcolata e non adottata;
  - nessun NaN;
  - `h2h` di Omega identico;
  - il workflow con numpy;
  - il tempo sui record IPS veri;
  - Safe (3 fasi, con la decisione ricalcolata da `hazard_warn`/`hazard_drop` sul dato nuovo) e Mike (v4 e ripiego);
  - `_LIVE_VOLATILI`;
  - nessun flumine o scipy nel sottoprocesso.
- **Finti con le chiavi vere.** Le righe `matches` portano `raw_json` (API-Football) e i finti PostgREST risolvono
  l'alias `alias:col->a->b` come PostgREST (`seleziona`, aggiunto ai finti di `test_genera_atlante` e
  `test_atlante_a_domanda`, i cui `_match` ora portano `raw_json`).
- **Suite dei file toccati:** 927 passati e 10 saltati (Safe, Mike, Omega advisor, stream atlante/genera/validazione/
  banco comune; timeout 600, sandbox DB).
- **Falsificazione** (`sonde/falsificazioni_v4_collegato.py` → `_esito.txt`): ripristino dal testo in memoria con verifica
  dell'hash. Al primo giro **23/24 rosse**: M8 (intervallo trattato come 1T in gioco) era VERDE, perché i casi restavano
  sotto i 60'. Ho aggiunto il caso dell'intervallo al 63' e M8 è diventato ROSSO. **Totale 24/24; suite verde dopo i
  ripristini.**
- Le rotture M1-M24:
  - select senza extra;
  - `_sequenze` e motore senza v4;
  - stagione sempre affidabile;
  - conteggi non cumulati;
  - `matchStatus` ignorato;
  - stato vecchio creduto;
  - intervallo;
  - Safe senza tempo o con i λ;
  - Mike senza tempo;
  - ripiego mai attivo;
  - ripiego non dichiarato;
  - adozione di uno stato senza v4;
  - lega senza v4 non ricalcolata;
  - `stagione_rif` sbagliata;
  - NaN;
  - globale sempre solido;
  - seconda lista di fixture_id;
  - recupero atteso non volatile;
  - nota senza versione;
  - workflow senza numpy;
  - scipy importato in testa;
  - recupero 1T trattato come ripresa.

## 6. Replay (NON eseguiti, come da brief: li lancia il coordinatore, uno per bot, in sequenza)
```
python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica safe_esatto 35760084 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica safe_punta 35760084 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica mike 35760084 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti --worker 1
```
- **Esiti attesi.** I replay caricano l'atlante con `percorso_atlante()`: il file live se c'è, altrimenti il v2 committato.
  - **Senza `hazard_atlas_live.json`** (oggi il main non ce l'ha): non c'è il blocco v4, quindi il ripiego è v3 con lo
    stesso minuto, **stessi p, stesse decisioni, stesso P&L del 24/09**. Cambiano solo le note (suffisso «atlante v3:
    recupero non modellato (blocco v4 assente)») e le chiavi in più del frame di Mike.
  - **Con il file live v4** (dopo il primo avvio con `HAZARD_ATLAS_SYNC=1`): i p cambiano per costruzione (dato nuovo,
    soglie invariate).
    - Le divergenze di Safe si dimezzano circa (referto §4.6), quindi cambiano penalità e drop.
    - Mike: `hazard` = max(atlante, modello). Il v4 è più basso a fine tempo, quindi più spesso comanda il modello.
    - Divergenza dal 24/09 da portare all'utente con i numeri del replay.
  - Omega: identico in entrambi i casi.

## 7. Non verificato / reperti
1. **Nessun ciclo reale del motore sul DB.** Ho fatto solo 4 GET in sola lettura della colonna `extra`. Il primo
   riempimento con v4 va osservato nei log `[atlante-domanda]`.
2. **`hazard_atlas_leghe` con righe scritte prima di stasera:** le leghe si ricalcolano per intero quando vengono
   osservate. È un costo una tantum, con gli stessi tetti. Non ho verificato se oggi la tabella ha righe.
3. **Forza non usata.** Servono gli id squadra API-Football (Safe `_lambdas_from_fixture` li ha in `fx`; Mike: il
   dossier non li porta). È fuori perimetro, decisione dell'utente.
4. **Intervallo:** `FirstHalfEnd` con minuto da 45 a oltre 56. Il v4 dà la cella 40-45, il v3 dava 45-55. Nessuno dei
   due modella l'intervallo, dove il rischio vero nei prossimi 3' è circa 0. Anche il modello di Safe
   (`event_goal_hazard`) riceve 46.. come ripresa nel recupero 1T. **Da portare all'utente**, non toccato.
5. **Supplementari** (`ExtraTime*`): tempo 2, minuti ≥ 90, quindi fase «recupero_2T». Non modellati, come ieri.
6. **Recupero annunciato:** non esiste nel feed (`elapsedAddedTime` è quello giocato). L'oracolo varrebbe −0,0067 di
   log-loss per stato di recupero.
7. **Incrementale della stagione corrente.** L'affidabilità del recupero si decide sui conteggi cumulati: con meno di 5
   gol di fine tempo la stagione si presume affidabile, come vuole la regola del modulo. Una stagione nuova che nasce
   senza `minute_extra` conta le prime partite «piene». È dichiarato, non misurato.
8. **Stagioni acquisite fuori ordine.** Senza forza non conta: i conteggi sono additivi.
9. **Stato `hazard_atlas_leghe` più pesante di circa 11 KB per lega:** non misurato sul DB vero.
10. **CPU del bootstrap v4:** +5 s per lega grande, nel thread del processo dello scanner Safe. Possibile ottimizzazione
    (uno `stati_partita` ridotto alle colonne usate), da fare solo con una nuova prova di parità.
11. **Suite intere e replay:** NON eseguiti (brief).

## 8. Consegna
- Patch: `AUDIT_2026-09-25/atlante_v4_collegato.patch` (`git diff`, 11 file tracciati).
- File nuovi (non tracciati):
  - `Betfair/stream/tests/test_atlante_v4_collegato_2026_09_25.py`;
  - in `AUDIT_2026-09-25/sonde/`: `sonda_minuto_ips_recupero.py`, `costo_v4_collegato.py`(+`_esito.txt`),
    `sonda_db_colonna_extra.py`(+`_esito.txt`), `falsificazioni_v4_collegato.py`(+`_esito.txt`),
    `esempi_note_v4.py`(+`.txt`);
  - questo referto.
