# TOLLERANZE DELL'OMBRA (T0C, 09/10/2026) — le SOLE tre (decisione dell'utente U-59)

L'ombra (`Betfair/stream/backtest/ombra.py`, `certifica <bot> <evento> ... --ombra <cassetta>`) confronta la cassetta
del giro di oggi con quella di riferimento (congelata) a **tolleranza ZERO**: interi e stringhe uguali byte per byte,
istanti uguali al millisecondo, prezzi e importi uguali nella rappresentazione scritta dal codice (nessun arrotondamento
del confronto), stesso ordine delle voci per compito e livello. Qualunque differenza e' una
`Divergenza(livello, ms, chiave, vecchio, nuovo, regola)` e `certifica` esce con codice != 0 (3 se il replay era pulito).

Le normalizzazioni sono **tre e solo tre** (U-59, 09/10). Ogni riga qui sotto ha il motivo, il punto del codice che la
applica e il test che la FALSIFICA (`Betfair/stream/tests/test_banco_cassetta_ombra_t0c_2026_10_09.py`). Allargarne una
o aggiungerne una quarta e' una decisione dell'utente, non di chi lancia il replay.

## 1. Tempi

| Cosa si toglie | Perche' | Dove | Falsificazione |
|---|---|---|---|
| Le righe del testo del referto che COMINCIANO (dopo gli spazi) con `tempo:`, `TEMPO TOTALE:`, `LENTO:` | sono le righe dei tempi di `certifica` (`PREFISSI_RIGHE_TEMPI`, `certifica.py:617`): secondi e tick/s cambiano a ogni giro per definizione (PSB §6.9) | `ombra.PREFISSI_RIGHE_TEMPI`, `ombra._riga_dei_tempi` | `test_tolleranza_1_tempi_e_memoria`: tempi diversi = 0 divergenze; una nota che PARLA di tempo (tempo di mercato consumato) diversa = rossa |
| La riga `MEMORIA:` (picco per worker) | il picco di memoria del processo (`picco_memoria_mb`, `certifica.py:670`) cambia a ogni giro | idem | idem (riga `MEMORIA:` diversa = 0 divergenze) |

Nient'altro del referto si toglie: nemmeno le righe vuote, nemmeno la riga `worker:` (vedi «Cio' che NON e' tollerato»).

## 2. Hash del codice

| Cosa si esclude (e si STAMPA) | Perche' | Dove | Falsificazione |
|---|---|---|---|
| Nel testo del referto il solo frammento `codice bot <hash> (<n> file)` (riga `controlli attivi: ...`); nelle note del referto lo stesso frammento | e' l'impronta dei moduli del bot (`certifica.impronta`, `certifica.py:230`): cambia per definizione quando la tappa sposta il codice; il confronto lo esclude e lo stampa | `ombra.RE_CODICE_BOT` | `test_tolleranza_2_hash_del_codice_escluso_e_stampato`: hash e numero di file diversi = 0 divergenze e stampati; il numero dei controlli SULLA STESSA RIGA diverso = rosso |
| Nella testata della cassetta: `commit`, `codice_bot`, `banco` (sha256 dei sorgenti del banco) | idem: sono l'identita' del codice che ha prodotto la cassetta, non il suo comportamento | `ombra.CAMPI_TESTATA_CODICE` | idem |

## 3. Identificatori e timbri derivati dall'orologio della macchina

Si sostituiscono con un **ORDINALE per prima comparsa** (`#id1`, `#id2`, ...): due cassette con la STESSA struttura e
valori diversi sono uguali; un ordine che prende l'id di un altro, o due voci che condividono (o smettono di condividere)
un valore, sono una divergenza. Lo stesso ordinale li sostituisce dove ricompaiono dentro altre stringhe (chiavi, note).
`bet_id` (contatore deterministico di flumine, `flumine/execution/baseexecution.py:13`) e i `ref` del bot **NON** si
normalizzano. L'elenco dei campi e' CHIUSO (`ombra.CAMPI_ID_OROLOGIO`): ogni campo ha la riga che lo scrive.

| Campo | Chi lo scrive con l'orologio della macchina | Trovato da |
|---|---|---|
| `ordine_id`, `_ordine`, `_sostituisce` (e `ordine` dentro `_fill_attraversato`) | `flumine/order/order.py:78` `self.id = str(uuid.uuid1().time)` | lettura del codice di flumine 2.13.11 |
| `trade_id`, `_trade_id` | `flumine/order/trade.py:41` `self.id = str(uuid.uuid4())` | idem |
| `settled_at`, `pnl_betfair_settled_at` | `Betfair/mike/service.py:6707,6723,6849` con `now_iso = _now().isoformat()` (`:6768`) | determinismo `mike 35760084 --scenari base` (09/10) |
| `letto_at` | `Betfair/mike/service.py:6892,6899` | idem |
| `last_loss_exit_deciso_ts` | `Betfair/mike/service.py:5739` `ora_s = _time.time()` (vedi REPERTO T0C-R1) | idem |
| `started_at`, `stopped_at`, `heartbeat_at` | `Betfair/stream/scalper/scalper_session.py:304` `_now_iso()` = `datetime.now(timezone.utc)`, scritti a `:220, :255, :1517, :1524, :2209, :2393, :2424` | determinismo `scalper_calcio 35797769 --scenari base` (09/10) |

Falsificazione: `test_tolleranza_3_id_d_orologio_coerenti_si_ma_scambiati_no` (id diversi ma coerenti = 0; fill spostato
sull'ALTRO ordine = rosso; `bet_id` diverso = rosso), `test_tolleranza_3_timbri_della_macchina_dichiarati_si_pid_no`
(timbri dell'elenco diversi = 0; `pid` diverso = rosso; `updated_at` fuori elenco diverso = rosso).

## Cio' che NON e' tollerato (e quindi e' una divergenza, anche se «non dipende dal bot»)

- **`pid` del processo** (`scalper_session.py:1590`, riga `log` dello scalper): non e' un orologio. Rende rosso il
  determinismo dello scalper (REPERTO T0C-R2): serve una decisione dell'utente.
- **Percorso assoluto della cartella delle registrazioni** nella prima riga del referto (`BOT: ... registrazioni: 1 in
  <data_dir>`): uguale fra due giri sulla stessa macchina, diverso fra PC e cloud. Una cassetta congelata sul PC si
  confronta sul PC (REPERTO T0C-R3).
- **Riga `worker: N su M core fisici`** (solo con piu' compiti): dipende dai core della macchina. Le baseline si
  producono con `--worker 1` o sulla stessa macchina dell'ombra (REPERTO T0C-R3).
- Qualunque altro timbro d'orologio non elencato sopra (es. `updated_at`, `created_at` di un finto che li scrive col
  tempo di mercato): se e' deterministico resta confrontato; se non lo e', e' un reperto da capire PRIMA di congelare
  (H §4.4 passo 2), non una tolleranza da aggiungere in silenzio.
