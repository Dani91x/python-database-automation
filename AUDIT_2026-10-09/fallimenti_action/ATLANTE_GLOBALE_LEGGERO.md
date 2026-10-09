# Atlante hazard: riga globale leggera (09/10/2026, opzione (a) dell'indagine)

Delegato Opus. Worktree `wt-atlante`, ramo `cantiere-atlante-leggero` da `origin/master` c4fc5fbf.
Niente commit, niente push, nessun workflow lanciato. Sul DB solo 2 SELECT di misura (sotto) e una
terza SELECT di prova andata in timeout (sotto, "Non verificato"). Nessuna scrittura. La migrazione
la applica l'utente.

Decisione dell'utente (delegata al coordinatore): scrivere sul DB il meno possibile, nessuna perdita
di dati o di qualita', action funzionanti, prestazioni uguali.

## 0. In breve

- La riga globale `hazard_atlas` ora porta nel payload solo `meta` e `global`.
  **POST della versione globale: 24.022.015 -> 125.093 byte (-99,48%)**, misurato sull'atlante
  vero (stato locale, 404 leghe). Colonne, RPC, ritentativi e controllo "gia' scritto" del 09/10
  non cambiano.
- L'atlante assemblato (`assembla`) e il file del modo `domanda` (quello che leggono i bot e lo
  scalper) sono **identici byte per byte** a prima: stessi sha256 col codice di master e col
  codice nuovo, sia sugli stati finti sia sullo stato vero (24.021.887 byte,
  sha `e293ce44...`). **Il percorso di lettura dei bot non e' toccato, quindi il replay non va
  rilanciato.**
- Modo `scarica`: con il payload leggero ora assembla dalle righe per lega di
  `hazard_atlas_leghe`, come la action. Sullo stato vero, con gli stessi stati, produce lo stesso
  file del vecchio `scarica`: 24.021.905 byte, sha `5e88b404...`, byte identici. Con un payload
  intero (righe di prima della migrazione) si comporta come prima.
- Migrazione `migrations/hazard_atlas_globale_leggero_2026-10-09.sql`: svuota il payload delle 7
  versioni gia' in tabella lasciando meta e global. E' idempotente, senza DROP e senza VACUUM; il
  commento spiega l'autovacuum e come forzarlo dal pannello.
- Test: 10 nuovi, 3 asserzioni vecchie adeguate al contratto nuovo. **Falsificazione: 20 mutazioni
  su 20 rosse**, ripristino verificato con sha256.
- `hazard_atlas_leghe` non e' toccata. La normalizzazione (b) resta una decisione aperta (par. 6).

## 1. Diff riga per riga

### 1.1 `Betfair/stream/scalper/genera_atlante.py` (+30/-5, CRLF conservati)
- Nuovi, prima di `class _Scrittore`:
  - `CHIAVI_PAYLOAD_GLOBALE = ("meta", "global")`, con un commento che spiega il perche';
  - `payload_globale_leggero(atlas)`, che restituisce `{k: atlas[k] for k in CHIAVI if k in atlas}`
    (stessi oggetti, l'atlante del chiamante non si tocca).
- `_Scrittore._scrivi_riga`: `leggero = payload_globale_leggero(atlas)`. Lo usano sia la RPC
  (`"p_payload": leggero`) sia il ripiego diretto (`"payload": leggero`). Le docstring sono
  aggiornate.
- `salva_versione`: cambia solo la docstring. `n_leghe`, `n_partite` e la filigrana si leggono
  ancora da `atlas["meta"]` (intero) e vanno nelle colonne come prima.
- Non toccati: `assembla`, `main` (il file `--json` e il riepilogo restano interi), `_req`, il
  controllo "gia' scritto", `salva_leghe`, la potatura `tieni=7`.

### 1.2 `Betfair/stream/scalper/hazard_atlas_sync.py` (+74/-1)
- Docstring del modulo: descrive il modo `scarica` dal 09/10.
- `_payload_leggero(atlas)`: c'e' `meta.generated_at` e manca `by_league`.
- `PAGINA_LEGHE = 50`.
- `_assembla_da_leghe(url, key, get, meta, pagina=None)`:
  - pagine a chiave su `hazard_atlas_leghe` (`select=league_id,stato`, `order=league_id.asc`,
    `league_id=gt.<ultimo>`, timeout 180 s): stessa select e stesso ordine di
    `genera_atlante.leggi_stato_db`;
  - **guardia**: restituisce None (file lasciato com'e') se le leghe lette sono 0 o meno di
    `meta.n_leagues_in_state`. L'ho aggiunta perche' un test l'ha fatta emergere: senza, una
    lettura vuota produceva un atlante fatto del solo seme v3, che `_valido` accettava;
  - poi `G.assembla(stati, generated_at=meta.generated_at, watermark=meta.watermark_event_id,
    seme=v3 se presente)` e `meta.run` copiato dalla versione.
- `sincronizza`: dopo la GET del payload (stessa richiesta di prima, ora ~0,13 MB), se il payload
  e' leggero si chiama `_assembla_da_leghe`; poi lo stesso `_valido` e la stessa scrittura atomica.
  Un payload intero segue il ramo di prima.
- Il modo `domanda` (predefinito, l'unico acceso nel `.env`) non e' toccato.

### 1.3 `Betfair/stream/tests/test_genera_atlante_scrittura_ritentativi_2026_09_28.py` (+7/-3)
Tre asserzioni chiedevano `p_payload == atlante intero`, cioe' il contratto vecchio. Ora chiedono
`{"meta": ..., "global": ...}`: `test_scrivi_riga_usa_la_rpc_se_c_e`,
`test_scrivi_riga_ripiega_sulla_post_diretta_se_manca_la_rpc`,
`test_salva_versione_scrive_il_payload_intero_atomico`. Il nome dell'ultimo e' rimasto quello di
prima. Prima della modifica le tre erano rosse, come atteso.

### 1.4 File nuovi
- `Betfair/stream/tests/test_atlante_globale_leggero_2026_10_09.py`: 10 test, par. 3.
- `migrations/hazard_atlas_globale_leggero_2026-10-09.sql`: par. 5.
- `AUDIT_2026-10-09/fallimenti_action/atlante_leggero/`: script di verifica
  (`misura_post.py`, `parita_reale.py`, `golden2.py`, `mutazioni_atlante.py`) ed esito delle
  mutazioni. Si lanciano dalla radice del worktree con `PYTHONPATH=.`.

## 2. Byte prima e dopo

### 2.1 POST della versione globale
Atlante assemblato dallo stato vero locale (`hazard_atlas_stato.json`, 404 leghe, letto in sola
lettura dal checkout principale) + seme v3. I byte della richiesta sono catturati da `urlopen`
(`misura_post.py`).

| | Byte della richiesta `rpc/hazard_atlas_salva_versione` | chiavi di `p_payload` |
|---|---|---|
| prima (codice di master) | 24.022.015 | by_league, by_team, global, h2h_hint, meta, v4 |
| dopo | **125.093** | global, meta |

Composizione dell'atlante (invariata): meta 119.666, global 5.280, by_league 2.541.783,
by_team 6.140.671, h2h_hint 13.190.029, v4 2.024.397.

### 2.2 Misure sul DB (sola lettura, 09/10 ~12:30)
- 7 versioni in tabella (id 7-13, dal 02/10 all'08/10; **quella del 09/10 manca**, perche' la
  scrittura e' fallita). Dimensione su disco del payload (`pg_column_size`): 4,51 / 4,95 / 4,96 /
  6,39 / 6,40 / 6,56 / 6,73 MB. `pg_total_relation_size('hazard_atlas')` = **52 MB**.
- Sulla riga 13: il payload leggero calcolato in SELECT pesa 132.181 byte come testo e 166.356 byte
  come jsonb non compresso.
- `hazard_atlas_leghe`: 404 righe, 29 MB su disco.

### 2.3 Dopo la migrazione e il vacuum (stima, non misurato)
7 righe da ~0,13-0,17 MB, cioe' circa 1 MB invece di 52. Ogni notte entra ~0,13 MB invece di ~24.

## 3. Test

Stati finti prodotti dal generatore vero (`bootstrap` su PostgREST finto con le colonne vere):
- leghe 39, 140 e 835 del test del v4 collegato, quindi con le chiavi vere `cells`, `teams`, `h2h`,
  `v4` e il resto;
- piu' la lega 61, con esattamente 3 scontri fra le squadre 3 e 4 (soglia `MIN_H2H` sul filo).

Il seme e' il v3 vero, tracciato in git. Le righe di `hazard_atlas_leghe` passano per un giro JSON,
come la colonna jsonb di PostgREST.

| Test | Cosa prova |
|---|---|
| `test_payload_leggero_solo_meta_e_global_sotto_1_mb` | solo {meta, global}, stessi valori, < 1 MB, l'atlante del chiamante resta intero |
| `test_la_post_della_rpc_non_porta_mai_i_blocchi_derivati` | byte veri della POST alla RPC: niente h2h_hint/by_team/by_league/v4, < 1 MB, colonne giuste |
| `test_il_ripiego_diretto_non_porta_mai_i_blocchi_derivati` | RPC 404 (PGRST202), poi POST diretta: stesso controllo su entrambe |
| `test_assembla_identico_a_prima_byte_per_byte` | sha256 di `assembla` = valore misurato col codice di master |
| `test_file_del_modo_domanda_identico_a_prima_byte_per_byte` | sha256 del file di `MotoreAtlante._scrivi_live` = valore di master |
| `test_scarica_riassembla_lo_stesso_file_di_prima` | payload leggero, poi assemblaggio dalle leghe: byte identici al vecchio `scarica`; la seconda passata fa 1 sola GET |
| `test_scarica_legge_tutte_le_pagine_delle_leghe` | pagina=1: 5 GET `None, gt.39, gt.61, gt.140, gt.835`, file identico |
| `test_scarica_senza_leghe_o_monca_non_tocca_il_file` | 0 leghe, oppure 2 su 4: `payload_non_valido`, file intatto |
| `test_scarica_uguale_a_domanda` | stessi blocchi (global, by_league, by_team, h2h_hint, v4); meta uguale salvo le chiavi del modo (modo, generator, leghe_in_preparazione, leghe_senza_dati, run, watermark_event_id) |
| `test_migrazione_tiene_solo_meta_e_global_idempotente_senza_drop` | UPDATE con jsonb_build_object meta/global, WHERE idempotente, niente DROP/DELETE/VACUUM, nessun riferimento a hazard_atlas_leghe, BEGIN/COMMIT, ASCII |

Golden (`golden2.py`) calcolati due volte, col codice del checkout principale (master c4fc5fbf,
nessuna modifica locale sui file dell'atlante) e col worktree:
- assembla `31a50deb...3661`, uguale nei due;
- domanda `a198f49e...33c2`, uguale nei due.

Parita' sullo stato vero:
- `assembla` (404 leghe + seme): `e293ce44...85cd1`, uguale prima e dopo la modifica;
- `scarica` contro il vecchio payload intero (`parita_reale.py`): 9 GET da 50 leghe,
  24.021.905 byte, `5e88b404...da13` in entrambi i casi, byte identici e valori uguali.

Suite eseguite nel worktree:
- atlante + sync + selezione Safe + `test_fallimenti_action_2026_10_09.py` +
  `tools/test_catena_action_2026_10_09.py`: 267 passati;
- piu' ampia (`Betfair/stream/tests`, `Betfair/safe_strategy/tests`, `Betfair/omega`, piu' i due
  file sopra, `-n 4`): **8458 passati, 63 saltati, 1 xfail, 0 rossi** in 3 min.

## 4. Falsificazione (`atlante_leggero/mutazioni_atlante.py`)

Ogni mutazione si applica a un file, si lanciano i 4 file di test (nuovo + ritentativi 28/09 +
24/09 + fallimenti 09/10, con `-x`), poi si ripristina dai byte originali. Lo sha256 e' verificato
su ogni file: genera_atlante `3931d3ae...`, sync `d26985db...`, migrazione `d4afbb43...`,
atlante_a_domanda `0273288f...`. **20 su 20 rosse.** Con `-x` si vede solo il primo test rosso.

| Mutazione | Primo test rosso |
|---|---|
| M01 payload leggero = atlante intero | test_payload_leggero_solo_meta_e_global_sotto_1_mb |
| M02 by_league fra le chiavi ammesse | idem |
| M03 RPC con l'atlante intero | test_la_post_della_rpc_non_porta_mai_i_blocchi_derivati |
| M04 ripiego diretto con l'atlante intero | test_il_ripiego_diretto_non_porta_mai_i_blocchi_derivati |
| M05 global tolto dal payload | test_payload_leggero_solo_meta_e_global_sotto_1_mb |
| M06 assembla: MIN_H2H 3->4 | test_assembla_identico_a_prima_byte_per_byte |
| M19 assembla: K_TEAM 12->13 | idem |
| M20 file domanda: meta.modo cambiato | test_file_del_modo_domanda_identico_a_prima_byte_per_byte |
| M07 scarica non riassembla il payload leggero | test_scarica_riassembla_lo_stesso_file_di_prima |
| M08 scarica riassembla anche il payload intero | test_sync_scarica_solo_se_piu_nuovo_e_i_consumatori_ricaricano (24/09) |
| M09 scarica dimentica meta.run | test_scarica_riassembla_lo_stesso_file_di_prima |
| M10 scarica senza seme | idem |
| M11 scarica legge solo la prima pagina | test_scarica_legge_tutte_le_pagine_delle_leghe |
| M12 scarica in ordine decrescente | test_scarica_riassembla_lo_stesso_file_di_prima |
| M13 scarica senza filigrana | idem |
| M14 scarica accetta una lettura monca o vuota | test_scarica_senza_leghe_o_monca_non_tocca_il_file |
| M15 scarica con la data di adesso | test_scarica_riassembla_lo_stesso_file_di_prima |
| M16 migrazione senza WHERE | test_migrazione_... |
| M17 migrazione tiene h2h_hint | idem |
| M18 migrazione con VACUUM FULL | idem |

Nota: alla prima tornata M06 era **verde**, perche' gli stati finti avevano una sola coppia con
molti scontri e la soglia non mordeva. Ho aggiunto la lega 61 (3 scontri esatti) e ricalcolato i
golden col codice di master: ora e' rossa.

## 5. Migrazione `migrations/hazard_atlas_globale_leggero_2026-10-09.sql` (la applica l'utente)

```sql
BEGIN;
SET LOCAL statement_timeout = '300s';
UPDATE public.hazard_atlas
   SET payload = jsonb_build_object('meta', payload -> 'meta')
                 || CASE WHEN payload ? 'global'
                         THEN jsonb_build_object('global', payload -> 'global')
                         ELSE '{}'::jsonb END
 WHERE (payload - 'meta' - 'global') <> '{}'::jsonb;
COMMIT;
```

- E' idempotente: la seconda volta tocca 0 righe.
- Colonne e `hazard_atlas_leghe` intatte. Nessun DROP, DELETE o VACUUM.
- Il commento spiega:
  - quando applicarla: fuori dalla finestra delle action, 06:30-09:30 UTC;
  - che l'autovacuum rende riutilizzabile lo spazio TOAST (~40 MB);
  - come forzarlo dal SQL editor: `VACUUM (VERBOSE, ANALYZE) public.hazard_atlas;`, da solo e
    fuori transazione;
  - che `VACUUM FULL` (lock esclusivo, restituisce lo spazio al sistema operativo) e' una scelta
    dell'utente e non e' nella migrazione;
  - le SELECT di verifica e come riassemblare un atlante intero se mai servisse.
- La RPC `hazard_atlas_salva_versione` non cambia: `p_payload jsonb` senza vincoli sulle chiavi;
  la tabella ha solo `payload NOT NULL`.
- Anche senza migrazione la potatura `tieni=7` sostituisce le righe pesanti entro 7 notti; la
  migrazione anticipa il risultato.

## 6. Decisione aperta: `hazard_atlas_leghe` (opzione (b), non realizzata)

Il formato e' invariato: cambiarlo richiede di ricertificare. Misure sullo stato vero locale
(404 leghe), JSON compatto:

| Parte | Oggi |
|---|---|
| `h2h` | 21,48 MB |
| `teams` | 8,21 MB |
| `fixtures` | 3,47 MB (letta solo per le leghe toccate) |
| `v4` | 3,47 MB |
| `cells` | 0,55 MB |
| **stato senza fixtures** (letto per intero ogni notte da `leggi_stato_db`) | **33,89 MB** |

Proposta (b), senza perdite:
- `h2h`: `[ft, ht]` senza `team_a`/`team_b` ripetuti, con un dizionario id -> nome per lega:
  21,48 -> ~8,78 MB;
- `teams`: array di 18 fasce: 8,21 -> ~2,16 MB;
- stato letto ogni notte: **~33,9 -> ~15,1 MB (~2,2x)**.

Avvertenze:
- i nomi delle squadre non sono sempre unici per id (l'indagine conta 943 varianti nel globale):
  per non perdere nulla le varianti vanno tenute, il che costa un po' piu' della stima;
- tocca `assembla`, `aggiungi_partita`, `atlante_a_domanda` e la lettura degli stati: va
  ricertificata e serve una migrazione dei dati delle 404 righe.

**Decisione dell'utente.**

## 7. Non verificato

- La SELECT di prova della migrazione sul DB vero (espressione + idempotenza sulla riga 13, senza
  scrivere) e' andata in **timeout del client MCP**: il CTE ricostruiva il payload da 24 MB piu'
  volte. Non l'ho rilanciata per non caricare il DB, che stamattina era in crash.
  - Verificato sul DB: l'espressione `jsonb_build_object('meta', ..., 'global', ...)` gira sulla
    riga 13 (2a SELECT, riuscita).
  - Verificate solo staticamente nel test: la clausola WHERE e l'UPDATE vero.
- Lo stato vero sul DB puo' differire da quello locale: le misure di byte e parita' sono fatte
  sullo stato locale (stesso formato).
- Il modo `scarica` con il DB vero non e' stato esercitato (e' spento nel `.env`). Due cose
  cambiano:
  - legge ~34 MB di stati (9 GET da 50 leghe, timeout 180 s ciascuna) invece del payload da 24 MB,
    una volta per versione nuova;
  - l'ordine delle chiavi del file segue league_id, mentre prima seguiva quello del jsonb: valori
    uguali, byte non confrontabili col vecchio file reale (nemmeno prima erano stabili).
- Che nessun processo fuori dal repo legga `hazard_atlas.payload`: dal codice non si puo'
  verificare (grep su py/ts/sql/yml: nessun lettore).
- La suite completa `Betfair/` (mike, tennis e altro) non l'ho lanciata. Ho lanciato stream, safe,
  omega e i test delle action: 8458 verdi.
- Il replay dello scalper non serve: il percorso di lettura dei bot non e' toccato (file
  `domanda` identico byte per byte). Lo segnalo comunque al coordinatore.

## 8. Blocco per CRONOSTORIA

```
- 12:42 Atlante globale leggero (opzione (a), delegato Opus, worktree wt-atlante, ramo
  cantiere-atlante-leggero da c4fc5fbf, NON committato): payload di hazard_atlas = solo
  meta+global (genera_atlante.payload_globale_leggero, RPC e ripiego). POST 24.022.015 ->
  125.093 byte sullo stato vero. assembla e file 'domanda' identici byte per byte (sha uguali
  master/worktree), replay scalper non necessario. 'scarica' riassembla da hazard_atlas_leghe
  (parita' byte sullo stato vero, guardia su lettura monca). Migrazione
  migrations/hazard_atlas_globale_leggero_2026-10-09.sql DA APPLICARE (utente, fuori 06:30-09:30
  UTC; vacuum automatico). Test: 10 nuovi + 3 asserzioni adeguate; 20/20 mutazioni rosse; 8458
  verdi. Referto AUDIT_2026-10-09/fallimenti_action/ATLANTE_GLOBALE_LEGGERO.md. Aperta: (b)
  normalizzazione di hazard_atlas_leghe (~33,9 -> ~15,1 MB letti per notte), decisione utente.
  Da verificare dal coordinatore: diff, suite, mutazioni.
```
