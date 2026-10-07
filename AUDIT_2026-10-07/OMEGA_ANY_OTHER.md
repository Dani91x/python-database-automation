# OMEGA V3 INCLUDE GLI "ANY OTHER" - referto del delegato (J), 07/10/2026

Cantiere: decisione dell'utente del 07/10, testuale: "io voglio che operi come ti ho detto,
1 operazione primo tempo e 1 operazione secondo tempo (se rispetta le condizioni) deve
includere anche "Any Other"". Lavoro NON committato nel worktree
`/home/user/python-database-automation/.claude/worktrees/agent-a5fe9c88028ad9ed4`
(base `8226d766`). Replay del banco NON lanciati (attendo il "via libera replay").

## 0. Premessa sbagliata del brief (da sapere prima di tutto)

Il brief dice che oggi la V3 scarta gli aggregati col motivo `fuori_griglia`. **Non e' vero
nel codice di HEAD**, e l'ho verificato in tre modi:

- `omega_v3.probabilita_selezioni` (HEAD, righe 489-526) calcola GIA' la P di ogni nome
  `e_aggregato`; `_seleziona` (HEAD 645-657) scarta `fuori_griglia` solo un nome senza P,
  cioe' un nome che non e' ne' scoreline ne' aggregato (es. "sel 123"). I test del 16/09
  (`test_omega_v3_2026_09_16.py`: "Any Unquoted" a 65 candidato, "Any Other Draw" a 40
  scelto contro il 3-3) provano proprio che gli aggregati erano candidati.
- Lo scanner passa a Omega TUTTE le selezioni del Correct Score (`safe_strategy/scanner.py:
  build_cs_block`, nomi del catalogo: "Any Other Home Win / Away Win / Draw") e
  `omega_service._v3_select` le passa tutte a `seleziona_v3` (nessun filtro).
- Sui book VERI delle due registrazioni (81 campioni, sezione 4) HEAD sceglie
  "Any Other Home Win" due volte: 35797769, 1-1, 75' e 77'.

Quindi: **gli aggregati erano gia' candidati, ma SENZA regola di distanza**, con la P
sottostimata dal troncamento della griglia, **senza uscite** (le proposte li saltavano) e con
un regolamento paper sbagliato per i nomi del banco. Il cantiere ha corretto questi quattro
punti e aggiunto l'interruttore. "Interruttore spento identico a oggi" non e' realizzabile alla
lettera (oggi gli aggregati entrano): spento = aggregati esclusi, scoreline identiche al bit a
HEAD (provato); acceso (di serie) = cio' che ha chiesto l'utente.

## 1. Cause radice (con prova)

| # | Difetto | Dove (HEAD) | Prova |
|---|---|---|---|
| D1 | Nessuna regola di distanza per gli aggregati: a 3-0 "Any Other Home Win" (4-0, a UN gol) e a 4-0 (gia' "vinto") passavano col solo margine/tetto | `omega_v3._seleziona` 645-653: il controllo di distanza sta dentro `if sc is not None` | test `test_aggregato_troppo_vicino_si_scarta_come_un_numerico` rosso su HEAD; `test_acceso_un_aggregato_a_un_gol_sul_book_vero_si_scarta` (book vero 35760084 49', 3-0) |
| D2 | P dell'aggregato sottostimata: griglia troncata a 10 gol residui per lato e normalizzata, la massa oltre il bordo (TUTTA degli aggregati) spalmata su tutte le celle | `omega_v3.probabilita_selezioni` + `griglia_residua` (normalizzazione) | massa oltre la griglia misurata: 3e-6 (lambda 1,45/1,15 al 1'), 4,1e-4 (2,5/2,0 al 1'), 5,0e-3 (3,5/3,0); errore relativo su "Any Other Home Win" -0,1 % / -0,55 %; il pareggio invece era sovrastimato (+0,04 % / +0,5 %). Oracolo indipendente scipy, test `test_p_aggregato_uguale_all_oracolo_indipendente` |
| D3 | Nessuna uscita per un aggregato bancato: `_una_gamba` faceva decadere e saltava ogni aggregato ("selezione_aggregata") -> mai una proposta, contro la regola 4-bis | `omega_proposte._una_gamba` 392-398; `omega_v3.traiettoria_bloccabile` (nan per ogni aggregato) | test `test_la_gamba_aggregata_arriva_alla_proposta_con_la_p_dell_aggregato` rosso su HEAD |
| D4 | Ripiego pericoloso: `_nomi_del_mercato` senza selezioni nel feed tornava `[nome]` -> per un aggregato nessuna scoreline quotata = P di TUTTA la griglia | `omega_proposte._nomi_del_mercato` | `test_aggregato_senza_scoreline_note_non_inventa_una_p` |
| D5 | Regolamento paper senza mercato: "unquoted" vinceva PRIMA di guardare la direzione ("Any Unquoted Home" vincente sul 4-4, "Any Unquoted Away" sul 4-4); "Any Other Half Time Score" mai regolato (None) | `omega_engine.vince_col_risultato` 1137-1155 | test `test_vince_col_risultato_legge_la_direzione_prima_di_unquoted` (3 casi rossi su HEAD) |
| D6 (fuori perimetro, NON corretto) | **Nomi degli aggregati SCAMBIATI nel replay del banco**: `replay_registrazioni._ALTRI` dice 9063255 = "Draw", 9063256 = "Away". Il vero: 9063255 = Away Win, 9063256 = Draw | `Betfair/omega/tools/replay_registrazioni.py:123-125` | `sortPriority` 17/18/19 nel `marketDefinition` delle registrazioni = ordine del catalogo Home/Away/Draw; prezzi pre-match della 35797769: 9063255 scambiato a 80, 9063256 a 400 (il 4-4+ e' il piu' raro); la Safe usa la mappa giusta (`safe_strategy/tools/validate_opportunity.py:332`). Effetto misurato sui book veri: col codice nuovo ACCESO e i nomi del banco, 35797769 al 1' e al 5' la V3 sceglie "Any Unquoted Draw" = sid 9063255, cioe' banca l'aggregato TRASFERTA credendolo pareggio (P creduta ~0,01 %). Lo stesso succedeva con HEAD (aggregati gia' candidati). Patch pronta, sezione 7 |
| D7 (fuori perimetro, NON corretto) | Il controllo A11 della certificazione non giudica la distanza di un aggregato (`_distanza` risponde None a ogni nome non numerico): un ingresso su un aggregato a un gol passerebbe il banco in silenzio | `Betfair/omega/certificazione.py:245-257` e `_a11` | patch pronta con test, sezione 7 |

## 2. Cosa ho cambiato

### File modificati
- `Betfair/omega/omega_v3.py`
  - `MAX_GOL_CODA` (ht 30, ft 40): griglia estesa per la P degli aggregati.
  - `punteggi_quotati(nomi)`: l'insieme dei punteggi elencati, SEMPRE dai runner veri.
  - `copre(nome, cella, quotate)` / `_copre_dir`: l'unica regola "l'aggregato vince se...",
    usata da ingresso, uscita e regolamento.
  - `distanza_aggregato(nome, punteggio, quotate, limite=60)`: gol aggiuntivi fino al
    punteggio coperto piu' vicino; 0 = gia' "vinto"; None = irraggiungibile.
  - `probabilita_selezioni(..., includi_coda=False)`: con `includi_coda` la P di un
    aggregato si somma sulla griglia estesa (coda compresa); le scoreline si leggono sempre
    dalla griglia di sempre (identiche al bit, test `test_la_coda_non_tocca_le_scoreline`).
    Default False = calcolo di prima al bit (lo usano gli strumenti di misura del banco).
  - `massa_oltre_griglia(...)`: la massa oltre la griglia di sempre, dichiarata.
  - `_seleziona(..., includi_aggregati=True, nomi_mercato=None)`: aggregato escluso
    (`aggregato_escluso`) a interruttore spento; distanza dal coperto piu' vicino
    (`troppo_vicino_al_punteggio` / `irraggiungibile`); nel motivo del candidato
    "aggregato: distanza N gol dal punteggio coperto piu' vicino". Tutte le altre condizioni
    (fascia, tetto, margine, liquidita', cap di gamba, cella gia' bancata) sono le stesse
    righe di sempre, NON duplicate.
  - `traiettoria_bloccabile(..., nomi_mercato=None)` e `proposta_uscita(..., nomi_mercato=None)`:
    la traiettoria di un aggregato (P con coda a ogni minuto); senza nomi o senza nessuna
    scoreline nota: nessun punto, come prima.
- `Betfair/omega/omega_engine.py`
  - `seleziona_v3`: legge `cfg["include_aggregate"]`, passa `includi_coda`,
    `includi_aggregati`, `nomi_mercato` (i nomi del book intero); se il candidato e' un
    aggregato aggiunge al motivo "coda oltre la griglia x% compresa nella P" (finisce
    nell'audit `meta.model.motivo` scritto dal servizio, senza toccare il servizio).
  - `vince_col_risultato`: usa `omega_v3.copre` (D5).
- `Betfair/omega/omega_config.py`: `v3_include_aggregate` (bool, **di serie True**) nella
  whitelist; `parametri_v3()["include_aggregate"]` con la coercizione della whitelist
  ("false" spegne).
- `Betfair/omega/omega_proposte.py`: `_una_gamba` non salta piu' gli aggregati (motivo
  `selezione_aggregata` sostituito da `selezione_non_leggibile`, solo per nomi ne' scoreline
  ne' aggregato); `_nomi_del_mercato` per un aggregato = tutti i runner numerici del feed
  (qualunque stato) + `meta.runners`, lista vuota se nessuna scoreline -> `_p_del_bancato`
  risponde None (`posizione_senza_numeri`), mai una P inventata; `_p_del_bancato` con
  `includi_coda=True` (stessa P dell'ingresso); `nomi_mercato` passato a `proposta_uscita`.
- `Betfair/omega/COSTITUZIONE_OMEGA.md`: SOLO la sezione nuova "21. OMEGA V3 INCLUDE GLI
  ANY OTHER - decisione dell'utente (07/10/2026)".
- `Betfair/omega/test_omega_v3_2026_09_16.py`: le 14 chiamate a `V3.candidato` passano ora
  `nomi_mercato=NOMI_HT|NOMI_CS` (il mercato vero da cui il test calcola gia' `ps`). Motivo:
  quei test mettevano un aggregato DA SOLO nei runner; con la regola di distanza l'insieme
  quotato si ricava dal mercato, e un mercato fatto del solo "Any Unquoted" rende l'aggregato
  uguale al punteggio corrente. Stessi casi, stesse attese. Nota: due test di robustezza
  (`test_prezzi_impossibili_non_diventano_candidati`, `test_size_non_finita_non_passa_la_liquidita`)
  restavano verdi anche senza i nomi, ma per la ragione SBAGLIATA (scarto di distanza); coi
  nomi del mercato provano di nuovo prezzo e liquidita', come con HEAD.
- `frontend/src/lib/omega.ts`: `v3_include_aggregate` nell'interfaccia, nei default (`true`) e
  nel gruppo "Motore v3" (interruttore con spiegazione); nota del gruppo aggiornata.
- `frontend/src/lib/omega.test.ts`: 3 test (default acceso, interruttore nel gruppo v3 e
  distinto da `include_aggregate` del v2, il salvataggio lo porta al servizio).

### File nuovi
- `Betfair/omega/tests/test_v3_any_other_2026_10_07.py` (82 test).
- `Betfair/omega/tests/dati/cs_book_registrazioni_2026_10_07.json` (155 KB): 81 book veri
  del Correct Score (35797769 e 35760084, un campione ogni 2 minuti di gioco, minuto e
  punteggio dal sidecar IPS) + la fotografia della selezione di HEAD su ciascuno
  (`oggi_con_aggregati`, `oggi_senza_aggregati`). Rigenerabile:
  `python3 AUDIT_2026-10-07/omega_any_other_strumenti/estrai_book.py <json>` poi
  `PYTHONPATH=. python3 .../base_oggi.py <json>` **su HEAD**.
- `AUDIT_2026-10-07/OMEGA_ANY_OTHER.md` (questo referto),
  `AUDIT_2026-10-07/OMEGA_ANY_OTHER_replay_nomi_aggregati.patch`,
  `AUDIT_2026-10-07/OMEGA_ANY_OTHER_certificazione_A11.patch`,
  `AUDIT_2026-10-07/omega_any_other_strumenti/` (estrai_book.py, base_oggi.py, falsifica.py).
- Nel worktree: collegamento `frontend/node_modules` -> node_modules del principale (ignorato
  da git; come da brief).

Migrazioni SQL: **nessuna**. Il parametro vive in `omega_control.params` (jsonb) come tutti gli
altri della whitelist; assente = default del servizio (True).

## 3. Test

Comandi (dalla radice del worktree, Python 3.13 di sistema):

| Comando | Esito | Tempo |
|---|---|---|
| `python3 -m pytest Betfair/omega/tests/test_v3_any_other_2026_10_07.py -q -p no:cacheprovider` | 82 passati | 3,3 s |
| `python3 -m pytest Betfair/omega/ -q -p no:cacheprovider` | 1535 passati, 3 saltati, 0 rossi | 27 s |
| idem + `Betfair/tests/test_contratto_safe_request_barriera_2026_09_17.py Betfair/stream/backtest/tools/misura_punto8/test_misura_punto8.py Betfair/safe_strategy/tests/test_bot_service.py Betfair/safe_strategy/tests/test_settlement_betfair_truth_2026_09_17.py Betfair/safe_strategy/tests/test_execution.py` (tutti i test fuori da Omega che importano i moduli toccati) | 1861 passati, 3 saltati | 32 s |
| `cd frontend && npx vitest run src/lib/omega src/pages/Omega src/components/omega src/lib/chiusuraUtente` | 22 file, 373 passati | ~10 s |
| `cd frontend && npx tsc -p tsconfig.app.json --noEmit` | 0 errori (exit 0) | ~60 s |

Prima della modifica: i test nuovi davano 66 rossi su 80 (i 14 verdi = funzioni gia' giuste,
es. il regolamento col WINNER del `marketDefinition`, tenuti come guardia).

Cosa provano i test nuovi (oracoli scritti nel test, mai la funzione provata):
1. Distanza: 36 casi parametrizzati contro un oracolo a forza bruta (griglia 0..20) + i casi
   scritti a mano del brief (0-0: casa/trasferta 4, pareggio 8; 3-0: casa 1; 2-2: 2/2/4;
   4-4: pareggio 0; 3-3: pareggio 2; 4-0: casa 0) + mercato che quota fino al 4-4 (l'insieme
   si sposta) + "Any Unquoted".
2. Selezione: troppo vicino / gia' vinto -> `troppo_vicino_al_punteggio`; distanza giusta ->
   candidato; irraggiungibile -> motivo; le stesse condizioni (fascia, pavimento, margine,
   liquidita', cap di gamba, cella gia' bancata) valgono per l'aggregato; interruttore spento
   -> `aggregato_escluso`; insieme dai runner veri (mercato 0..4: a 3-0 l'aggregato parte dal
   5-0 e passa).
3. P: contro un oracolo scipy (binomiali negative per lato + tau di Dixon-Coles allo 0-0, 80x80
   celle) in 5 stati, scarto < 1e-10; la coda conta (senza, casa e trasferta sottostimate);
   la coda non tocca le scoreline (identita' al bit); oltre la griglia estesa < 1e-12 con
   lambda 3,5/3,0 al 1'; il raccordo `seleziona_v3` usa la P con la coda.
4. Book veri (81 campioni): spento -> scarti delle scoreline identici a HEAD motivo per
   motivo, scelte identiche con P identica al bit dove HEAD sceglieva una scoreline, e dove
   HEAD sceglieva l'aggregato (75', 77') la scoreline migliore non scartata ("3 - 2"); acceso
   -> differenze di scelta da HEAD elencate (nessuna) e motivo con distanza e coda.
5. Uscite: traiettoria dell'aggregato (P al primo punto = P con coda; decresce col tempo a
   punteggio fermo; senza nomi nessun punto); `proposta_uscita` su "Any Other Draw" a 3-3 non
   rompe e ha un motivo; il produttore delle proposte con un trade su "Any Other Home Win"
   scrive la proposta con la P dell'aggregato (mai None trattato come 0); senza scoreline note
   `posizione_senza_numeri`.
6. Regolamento: `marketDefinition` vero della 35760084 (chiavi dello stream `id`/`status`,
   9063254 WINNER) -> book REST (`selectionId`/`status`) -> `omega_market._snapshot_from_book`
   -> `settle_pnl`: lay "Any Other Home Win" @60 perso -59,00, "Away"/"Draw" vinti +0,95; la
   strada del paper (`vince_col_risultato` col 4-0) dice la stessa cosa.

### Falsificazioni (script `AUDIT_2026-10-07/omega_any_other_strumenti/falsifica.py`, ripristino in `finally`; dopo: `grep -c MUTAZIONE` = 0 su tutti i file, `git diff --stat` identico)

| Mutazione | Esito |
|---|---|
| M1 aggregato senza regola di distanza (= HEAD) | ROSSO, 8 test |
| M2 distanza da 1 invece che da 0 (il gia' vinto passa) | ROSSO, 9 |
| M3 coda ignorata | ROSSO, 6 |
| M4 l'aggregato copre anche i punteggi quotati | ROSSO, 36 |
| M5 interruttore spento ignorato | ROSSO, 2 |
| M6 `parametri_v3` sempre acceso | ROSSO, 2 |
| M7 raccordo senza coda | ROSSO, 1 |
| M8 proposte: l'aggregato torna a saltare (= HEAD) | ROSSO, 2 |
| M9 proposte: ripiego `[nome]` per l'aggregato | ROSSO, 1 |
| M10 traiettoria: aggregato mai calcolato (= HEAD) | ROSSO, 1 |
| M11 regolamento: "unquoted" prima della direzione (= HEAD) | ROSSO, 2 |
| M12 default dell'interruttore spento | ROSSO, 4 |
| M13 griglia quotata scritta a mano (0..3) | ROSSO, 1 (al primo giro SOPRAVVISSUTA: aggiunto `test_la_selezione_ricava_l_insieme_dai_runner_veri_del_mercato`) |
| F1 frontend: default `false` in `omega.ts` | ROSSO: vitest 1 + contratto Python `test_default_della_ui_uguali_a_quelli_del_servizio` |

Patch fuori perimetro (sezione 7), verificate applicandole TEMPORANEAMENTE nel worktree e poi
ripristinando i file (`git checkout --` sui soli due file, test temporanei cancellati):
A11 -> 2 test rossi senza patch, 105 verdi con patch (nuovi + 3 file di certificazione);
nomi del replay -> 2 rossi senza patch, 125 verdi con patch (+ `test_omega_replay_2026_09_16.py`).

## 4. Differenze di selezione (book veri, lambda fissati 1,45/1,15, parametri di produzione)

- ACCESO (di serie) contro HEAD, 81 campioni: **nessuna differenza di scelta**. Le due scelte
  di aggregato di HEAD (35797769, 1-1, 75' e 77', "Any Other Home Win") restano: la cella
  coperta piu' vicina e' il 4-1, a TRE gol (soglia 2). La P cambia appena (coda).
- SPENTO contro HEAD: a 75' e 77' al posto dell'aggregato si sceglie "3 - 2" (la stessa che
  HEAD sceglieva sul mercato senza aggregati); altrove identico al bit.
- Il caso in cui la regola nuova morde sul book vero: 35760084 al 49' (3-0) col lay
  dell'"Any Other Home Win" rimesso in fascia -> scartato (4-0 a un gol); HEAD lo bancava.
- Con i nomi SCAMBIATI del banco (D6) e interruttore acceso: 35797769 al 1' e al 5' la V3
  sceglie "Any Unquoted Draw" = sid 9063255 (la TRASFERTA vera). Coi nomi giusti no.
  **I replay del banco con aggregati vanno lanciati DOPO la patch dei nomi**, altrimenti le
  differenze che mostrano sono artefatti del banco.
- Costo: `seleziona_v3` 0,50 ms (spento) -> 2,32 ms (acceso) per chiamata (griglia estesa
  41x41); la traiettoria di un aggregato ricalcola la P estesa a ogni passo di 5 minuti.

## 5. Parita' paper/live

Nessun ramo per modalita': selezione (`seleziona_v3`), P del bancato e proposte
(`omega_proposte`), regolamento col WINNER sono gli stessi in paper e in live. L'unica strada
solo paper toccata e' `vince_col_risultato` (posizione orfana di mercato dopo 48 h, cantiere C):
ora usa la stessa regola (`omega_v3.copre`) che il mercato applica nel live col WINNER, provato
dal test sul `marketDefinition` vero (stesso esito per le due strade). Nessun ordine, size,
tipo d'ordine, bet delay o coda cambiati.

## 6. Cosa NON ho fatto / cosa NON ho potuto verificare

- **Replay del banco NON lanciati** (`--scenari tutti` di Omega sulle due partite): attendo il
  via libera. Senza la patch D6 i replay con aggregati non sono affidabili.
- **NON applicate** (fuori perimetro) le due patch: nomi del replay (D6,
  `Betfair/omega/tools/replay_registrazioni.py`, vietato) e controllo A11 (D7,
  `Betfair/omega/certificazione.py`, non nel perimetro).
- `omega_service.py` (vietato): non serve nessuna riga. Verificato: `_v3_select` passa tutti
  i runner e scrive `cand.motivo` nell'audit; `celle_gia_bancate` e' per `selection_id`;
  `_v3_p_empirica` risponde None agli aggregati (veto empirico non applicabile: le tabelle
  sono per scoreline; ⊘ dichiarato, come prima); `_greenup_one` (salta gli aggregati) e'
  solo del v2, spento in V3 dalla whitelist; settlement per `selection_id`;
  `_stamp_market_result` non timbra il risultato se il WINNER e' un aggregato (corretto: dal
  solo vincitore il punteggio non si sa; il risultato arriva dal feed).
- UI: `components/omega/MatchTradesTable.tsx` (`ResultCell`) per un aggregato non scrive
  "bancato USCITO / non uscito" (lo fa solo per scoreline). Non rompe; fuori perimetro.
- Le stringhe visibili nella UI (`omega.ts`: label/hint/nota) usano accenti e virgolette
  tipografiche come il resto del file; commenti e codice Python aggiunti sono ASCII.
- Lambda reali per partita: nei test dei book veri i lambda sono fissati (1,45/1,15): in
  produzione vengono da quote pre-KO / fixture (`_prematch_lambdas`). La parita' con HEAD e'
  provata a lambda uguali; le scelte assolute sulle due partite le dira' il replay.
- Gli strumenti di misura del banco (`banco_fusione`, `misura_ingresso_passivo`, `o6_coda`)
  chiamano `probabilita_selezioni` senza `includi_coda`: restano identici (P di prima).

## 7. Patch pronte (NON applicate) - in ordine di applicazione

1. `AUDIT_2026-10-07/OMEGA_ANY_OTHER_replay_nomi_aggregati.patch` (`git apply`): scambia
   9063255/9063256 in `replay_registrazioni._ALTRI` + test
   `Betfair/omega/tests/test_replay_nomi_aggregati_2026_10_07.py` (anche contro la mappa della
   Safe). **Va applicata prima dei replay.**
2. `AUDIT_2026-10-07/OMEGA_ANY_OTHER_certificazione_A11.patch`: `_distanza` giudica anche un
   aggregato (insieme dai runner di `m.snapshot`, regola `omega_v3.distanza_aggregato`), A11
   la usa + test `Betfair/omega/tests/test_cert_a11_aggregati_2026_10_07.py` (4: un gol e gia'
   vinto -> A11; distanza giusta e senza book -> silenzio). A2 (v2) invariato (non passa il
   book).
Entrambe: `git apply --check` pulito sul worktree.

## 8. Decisioni per l'utente

- Nessuna soglia, stake, tetto o finestra e' cambiato. Il cambio di strategia e' quello
  chiesto (aggregati candidati, interruttore di serie acceso); le due regole aggiunte per gli
  aggregati (distanza dal coperto piu' vicino, P con la coda) sono quelle del brief.
- Da sapere (non una decisione nuova): gli aggregati erano GIA' candidati da HEAD, senza
  regola di distanza. La nuova regola rende la V3 piu' prudente sugli aggregati (es. a 3-0
  niente piu' lay "Any Other Home Win").

## 9. Da controllare dal vivo in paper al prossimo avvio

- Pannello Omega, gruppo "Motore v3": c'e' "v3: includi gli aggregati" ACCESO.
- Su una partita con un lay su un aggregato: `meta.model.motivo` del trade contiene
  "aggregato: distanza N gol" con N >= 2 e "coda oltre la griglia x% compresa nella P".
- Nella scheda delle uscite: una posizione su un aggregato produce proposte (prima mai); nel
  registro attivita' non deve comparire `skip` con `reason=selezione_aggregata`.
- Mai un ingresso su un aggregato a punteggio "dentro" l'aggregato (es. "Any Other Home Win"
  a 4-0, "Any Other Draw" a 4-4).
