# Controllo finale del banco — Omega (+ Safe base) — 08/10/2026

Esecutore: sessione cloud https://claude.ai/code/session_01HcqJSA5cLcTummVq4LvuBP.
Nessuna modifica al codice, nessuna strategia toccata. Commit SOLO di questa cartella.

## Esito in breve

**Nessuna riga di esito diversa, nessun controllo violato, nessuna differenza di tick, decisioni, azioni o stati, nessun
cambio nel sommario dei controlli.**
Ci sono **tre** righe NON ATTESE secondo il perimetro della consegna, tutte nella nota `attivita' del servizio`. Le riporto per intero più sotto.

| bot | evento | comando | OK | NE | KO | violazioni | riferimento | esiti uguali al riferimento |
|---|---|---|---|---|---|---|---|---|
| omega | 35797769 | `--scenari tutti --worker 3` | 20 | 2 | 0 | 0 | W3A 20 OK / 2 NE | SI', 22/22 |
| omega | 35760084 | `--scenari tutti --worker 3` | 22 | 0 | 0 | 0 | cantiere 11 w3: **0 righe diverse**; W3A 22 OK | SI', 22/22 |
| omega | 35760084 | `--scenari apertura --trasporto canale --worker 1` | 1 | 0 | 0 | 0 | — | — |
| omega | 35760084 | `--scenari apertura --trasporto entrambi --worker 1` (aggiuntivo, vedi §Parità) | 2 | 0 | 0 | 0 | — | coda = `apertura` del giro `tutti` |
| safe_base | 35760084 | `--scenari tutti --worker 3` | 22 | 1 | 0 | 0 | W3A 22 OK / 1 NE | SI', 23/23 |

Gli NE sono gli stessi del riferimento: omega 35797769 `chiuso-fuori-app-canale` e `ridotto-fuori-app-canale`
(canale del conto: messaggi 0), safe_base `chiusura-fuori-app-canale`.

Impronte del codice, identiche ai riferimenti: omega `ad274e67e2b2` (13 file), safe_base `ee82ce75a8ad` (19 file);
flumine 2.13.11, betfairlightweight 2.23.2.

## Passo 0 e ambiente

- `git fetch origin claude/blissful-sagan-hri7o6 && git checkout -B claude/blissful-sagan-hri7o6-finale-omega d01de76...`
  -> `git log --oneline -1` = `d01de76 docs: documento di verifica, riga e decisioni del cantiere 11, metodo con --worker 3`. OK.
- Registrazioni decompresse con lo script di `registrazioni_banco/LEGGIMI.md` in `_live_raw/` (fuori dal repo).
- `pip install psutil` (7.2.2): tutti i giri `--worker 3` hanno la riga
  `worker: 3 su 4 core fisici (un processo per coppia evento x scenario, ...)`.
- **Deviazione da dichiarare**: il container era privo delle dipendenze del repo. Il primo lancio del replay 1 è
  uscito subito con `ModuleNotFoundError: No module named 'flumine'` (rc=1, 0 s, nessun replay eseguito).
  Ho installato nel container (solo lì) `pip install -r requirements.txt`, con le versioni fissate dal repo (flumine
  2.13.11, betfairlightweight 2.23.2). Senza queste dipendenze nessun replay parte. Poi ho rilanciato il replay 1 da capo.

## Comandi e tempi (uno alla volta, in background)

| # | comando | rc | durata parete | TEMPO TOTALE del referto |
|---|---|---|---|---|
| 1 | `python -m Betfair.stream.backtest.certifica omega 35797769 --scenari tutti --worker 3` | 0 | 884 s | 881.5 s (LENTO: avviso sopra il tetto di 600 s, scenario più caro `v4` 118.8 s; l'esito non cambia) |
| 2 | `python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti --worker 3` | 0 | 208 s | 205.0 s |
| 3 | `python -m Betfair.stream.backtest.certifica omega 35760084 --scenari apertura --trasporto canale --worker 1` | 0 | 31 s | 29.0 s |
| 4 | `python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari tutti --worker 3` | 0 | 292 s | 289.9 s |
| 3b | `python -m Betfair.stream.backtest.certifica omega 35760084 --scenari apertura --trasporto entrambi --worker 1` (aggiuntivo) | 0 | 55 s | 53.0 s |

## Metodo del confronto

- `python -m Betfair.stream.backtest.tools.confronta_referti PRIMA DOPO` (righe diverse, senza tempi, log, worker,
  memoria e righe vuote) -> `confronti/*_righe.txt`.
- `classifica.py` (in questa cartella; non tocca il codice del banco) confronta scenario per scenario la riga di esito e
  ogni riga del blocco, più la coda (sommario dei controlli). Esclude tempi, LENTO, TEMPO TOTALE, `worker:`, `MEMORIA:`,
  log `LIVELLO:modulo:`, impronta, comando e percorso. Classifica ogni differenza come attesa (a/b) o NON ATTESA
  -> `confronti/*_classifica.txt`.
- **Falsificazione del classificatore**: su una copia del referto 1 ho alterato `tick` di `[v3]` (1470869 -> 1470868),
  il conteggio `G1 x11654 -> x11655` nel sommario e ho aggiunto una nota inventata. Risultato: 7 differenze NON ATTESE,
  tutte e tre le alterazioni segnalate. Il classificatore sa diventare rosso.

## Differenze ATTESE (con conteggio)

### Omega 35797769 vs `W3A_DOPO_CLOUD/omega_35797769_tutti.txt` (22 scenari)
- (a) `chiamate al mercato: list_today_football_events` **+10** in tutti i 21 scenari dove compare
  (x374->x384 ×2, x686->x696 ×7, x690->x700 ×1, x736->x746 ×11): **21 righe**.
- (a) nota `[NON ESERCITABILE]`, con `fixtures_for_window` aggiunto in testa e `minute_transitions | ht_ft_transitions`
  che seguono (la nota `minute_transitions` si sposta): **19 righe**. In 2 scenari (`feed-stantio`, `manuale-e-bot`)
  la nota `[NON ESERCITABILE] fixtures_for_window` è nuova e da sola (prima non c'era alcuna nota NON ESERCITABILE): **2 righe**.
- (a) `attivita' del servizio`: compare `flusso_non_dichiarato x1`, il resto è identico: **18 righe**
  (+1 riga, `cashout-globale`, sotto NON ATTESE).
- (c) impronta del codice: identica (`ad274e67e2b2`).

### Omega 35760084 vs `cantiere_11/verifica_coordinatore/omega_35760084_tutti_w3.txt`
- **0 righe diverse** (701 contro 701), come atteso.

### Omega 35760084 vs `W3A_DOPO_CLOUD/omega_35760084_tutti.txt` (22 scenari)
- (a) `list_today_football_events` **+6** in 21 righe (x438->x444 ×16, x467->x473 ×5).
- (a) nota `[NON ESERCITABILE]` con `fixtures_for_window` in testa: **19 righe**; nuova e da sola: **2 righe**.
- (a) `attivita' del servizio` con `flusso_non_dichiarato x1` in più: **17 righe** (+2 sotto NON ATTESE).
- Sono le stesse differenze che il referto cantiere 11 w3 aveva già rispetto a W3A (0 righe diverse da quello).

### Safe base 35760084 vs `W3A_DOPO_CLOUD/safe_base_35760084_tutti.txt` (23 scenari)
- (b) note `save_event_model` / `NON ESERCITABILE get_event`: **0 spostamenti** (10 occorrenze per parte, nelle
  stesse posizioni).
- (c) impronta del codice: identica (`ee82ce75a8ad`).
- Totale righe diverse (`confronta_referti`): 4, cioè 2 coppie, tutte sotto NON ATTESE.

## Differenze NON ATTESE (per intero)

### N1 — Omega 35797769 `[cashout-globale]`, nota delle attività: sparisce `settle_position x1`
```
PRIMA:       nota: attivita' del servizio: skip x3, diagnosi x2, settle x2, live_fok_fallback x1, place x1, replay_cashout_globale x1, place_parziale x1, cashout x1, cashout_manual x1, settle_position x1
DOPO :       nota: attivita' del servizio: skip x3, diagnosi x2, settle x2, flusso_non_dichiarato x1, live_fok_fallback x1, place x1, replay_cashout_globale x1, place_parziale x1, cashout x1, cashout_manual x1
```
Fatto verificato nel codice, non una spiegazione dedotta: la nota stampa solo `kinds.most_common(10)`
(`Betfair/omega/tools/replay_registrazioni.py:2371`). PRIMA e DOPO contano esattamente 10 voci. La riga di esito,
`righe per stato`, le righe 1 e 2 degli ordini, fill, P&L e `E4 sollecitato 362 volte` sono identiche.

### N2 — Omega 35760084 `[chiuso-fuori-app-canale]`, nota delle attività: sparisce `goal_stop x1`
```
PRIMA:       nota: attivita' del servizio: skip x5, replay_chiuso_fuori_app x3, chiuso_dall_utente x2, flusso_interrotto x1, live_fok_fallback x1, place x1, diagnosi x1, replay_chiuso_fuori_app_abbinato x1, settle x1, goal_stop x1
DOPO :       nota: attivita' del servizio: skip x5, replay_chiuso_fuori_app x3, chiuso_dall_utente x2, flusso_non_dichiarato x1, flusso_interrotto x1, live_fok_fallback x1, place x1, diagnosi x1, replay_chiuso_fuori_app_abbinato x1, settle x1
```

### N3 — Omega 35760084 `[ridotto-fuori-app-canale]`, nota delle attività: sparisce `goal_stop x1`
```
PRIMA:       nota: attivita' del servizio: skip x5, chiuso_dall_utente x2, flusso_interrotto x1, live_fok_fallback x1, place x1, replay_chiuso_fuori_app x1, replay_chiuso_fuori_app_abbinato x1, diagnosi x1, settle x1, goal_stop x1
DOPO :       nota: attivita' del servizio: skip x5, chiuso_dall_utente x2, flusso_non_dichiarato x1, flusso_interrotto x1, live_fok_fallback x1, place x1, replay_chiuso_fuori_app x1, replay_chiuso_fuori_app_abbinato x1, diagnosi x1, settle x1
```
Per N2 e N3 vale lo stesso fatto di N1: 10 voci da entrambe le parti, troncamento `most_common(10)`.
Anche queste due righe compaiono identiche nel referto cantiere 11 w3, da cui il replay 2 non differisce in nulla.

### N4 — Safe base 35760084: `flusso_non_dichiarato x1` nella nota delle attività di `[bot-fermo]` e `[riavvio]`
Per Safe la consegna ammette soltanto lo spostamento delle note `save_event_model` e `get_event`, quindi questa differenza è fuori elenco.
```
[bot-fermo]
PRIMA:       nota: attivita' del servizio: replay_richiesta_manuale x2, place x1, diagnosi x1, place_parziale x1, cashout x1
DOPO :       nota: attivita' del servizio: replay_richiesta_manuale x2, flusso_non_dichiarato x1, place x1, diagnosi x1, place_parziale x1, cashout x1
[riavvio]
PRIMA:       nota: attivita' del servizio: diagnosi x25, replay_richiesta_manuale x2, place x1, replay_riavvio x1, place_parziale x1, cashout x1
DOPO :       nota: attivita' del servizio: diagnosi x25, replay_richiesta_manuale x2, flusso_non_dichiarato x1, place x1, replay_riavvio x1, place_parziale x1, cashout x1
```
Fatti, senza interpretazione: nel riferimento W3A la stessa voce `flusso_non_dichiarato x1` c'era già in Safe
`[cap-stretto]` e lì è rimasta invariata. Righe di esito, tick, decisioni, azioni e stati dei due scenari sono identici.
Non ho indagato oltre: lo segnalo al coordinatore.

## Parità paper/live (trasporto)

- Il giro commissionato (`--trasporto canale --worker 1`) dà `OK 35760084 [apertura] <canale> tick=482333
  decisioni=467 azioni=2`, con 0 violazioni. Il referto **non contiene un rapporto di parità**: `certifica._stampa_parita`
  lo stampa solo quando lo scenario gira nei DUE trasporti. Per questo ho aggiunto il giro 3b (`--trasporto entrambi`):
  ```
  TRASPORTO 35760084 [apertura]:
    PARITA' coda/canale: RAGGIUNTA | ordini coda=1 canale=1 | righe coda=1 canale=1 | REST sul canale=0
       tempi (canale - coda, s di mercato): {'max': 0.0, 'min': 0.0, 'n': 1} | durata replay s: {'coda': 25.5, 'canale': 26.5}
       client: {'da_seq': 0, 'buchi': 0, 'connessioni': 1} | motore: {'comandi': 1, 'accettati': 1, 'rifiutati': 0, 'order': 3} | costo del banco sul canale: 0.9 s su 482333 book
  ```
- In 3b la parte `<coda>` (tick=482034, decisioni 467, azioni 2) coincide con `[apertura]` del giro 2. La parte
  `<canale>` coincide con il giro 3 (tick=482333).
- Differenze di contenuto tra `apertura` diretto (giro 2) e `<canale>` (giro 3):
  - `tick` 482034 -> 482333;
  - attività `live_fok_fallback x1, place x1` -> `canale_inviato x1, flumine_fill x1`;
  - riga 1 `residuo=None` -> `residuo=0.0`;
  - `bet delay` 509 book -> 0 book.

  Stessa gamba (`ft_cs lay '3 - 3'` a 300, 5.26 EUR, won, pnl 5.0).

## Contenuto della cartella

- `omega_35797769_tutti.txt`, `omega_35760084_tutti.txt`, `omega_35760084_apertura_canale.txt`,
  `omega_35760084_apertura_entrambi.txt`, `safe_base_35760084_tutti.txt`: referti integrali.
- `confronti/`: uscite di `confronta_referti` e di `classifica.py` per ogni coppia.
- `classifica.py`: classificatore delle differenze usato qui.
