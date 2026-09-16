# CHECKPOINT — prestazioni e fedelta' del banco (16/09/2026)

> Punto di ripresa. Se la sessione si interrompe, si riparte da qui.
> Stato: **FATTO.** Cache Poisson applicata, testata e misurata; latenza di
> lettura 120 ms applicata, dichiarata e testata; suite verde salvo tre rossi
> di un altro delegato (§5).

## 1. Cache Poisson — FATTA (autorizzata dal coordinatore)

`Betfair/omega/omega_model.py`:

| riga | cosa |
|---|---|
| `import functools` (32) | l'unico import aggiunto |
| `CACHE_GRIGLIE = 4096` (~44-68) | tetto + la nota «memoizzazione pura, 16/09, misurata 2,3x; nessun numero cambia» con la misura (6.779.932 chiamate per **1.586 argomenti distinti** in una partita) e il conto della memoria (~16 KB per griglia -> ~65 MB di tetto) |
| `_full_match_1x2` (~150) | `@functools.lru_cache(maxsize=CACHE_GRIGLIE)` diretto: torna una **tupla**, gia' immutabile |
| `_poisson_grid` (~281) | guscio che torna `dict(_poisson_grid_memo(...))` — una **COPIA** |
| `_poisson_grid_memo` (~288) | il corpo di prima, con `lru_cache` |
| `residual_grid` (~300) | guscio che torna `dict(_residual_grid_memo(...))` — una **COPIA**; firma invariata (`dixon_coles`/`cv` restano parole chiave per chi chiama) |
| `_residual_grid_memo` (~318) | il corpo di prima, con `lru_cache` |

Condizioni rispettate: nessun cambio di firma; **nessun arrotondamento nuovo**
(la chiave sono gli argomenti come arrivano); cache limitata; le due griglie
(`dict`, mutabili) si consegnano copiate, la tupla no; purezza verificata —
`_poisson_grid` e' chiamata solo da `residual_grid` (righe 279/284 di prima),
nessun chiamante muta il risultato, `MAX_GOALS_GRID` / `_GH5` / `DEFAULT_RHO`
sono assegnate una volta sola in tutto il repo (verificato con grep).

## 2. Test — SCRITTI E VERDI

`Betfair/omega/test_omega_cache_pura_2026_09_16.py` — **13 verdi**:
- `argomenti_reali()` cattura i **200 argomenti VERI** con cui la catena
  (`lambdas_from_pre_ko` -> doppia bisezione) chiama il fondo, su tre pre-KO
  diversi; un test verifica che si raccolgano davvero (difetto 29 del catalogo);
- cache vs non-cache **elemento per elemento** per `_poisson_grid`,
  `residual_grid` (cv 0 e 0,30) e `_full_match_1x2`;
- la catena intera (`lambdas_from_pre_ko`) da' gli stessi lambda a cache vuota e
  a cache piena;
- chi modifica la griglia consegnata **non** corrompe la cache (prova della copia);
- il tetto e' dichiarato e limitato.
- **Falsificazioni**: chiave che perde un argomento (5 posizioni, ognuna con un
  secondo argomento che differisce SOLO li') -> la cache monca consegna la
  stessa griglia a chiamate diverse in tutti i casi; e una chiave arrotondata
  cambierebbe piu' di meta' delle griglie (prova che NON si e' arrotondato).

Comando: `python -m pytest Betfair/omega/test_omega_cache_pura_2026_09_16.py -q -p no:cacheprovider`

## 3. FATTO — misure di chiusura

**Confronto sha con e senza cache, corse simultanee sullo stesso codice
`4d34f20152f8`** (`scratchpad/cache_base.txt`), `35760084` scenario `base`:

| | wall | CPU | picco | sha |
|---|---|---|---|---|
| senza cache | 59,3 s | 56,3 s | 223,6 MB | `c1caa08ad6f6` |
| con cache | 59,3 s | 56,2 s | 223,2 MB | `c1caa08ad6f6` |

**Referto IDENTICO, e guadagno ZERO — e la ragione va detta**: fra la misura del
pomeriggio e questa, il percorso caldo di Mike e' cambiato (altro delegato) e lo
stesso replay e' passato da **1028,7 s a 56,3 s di CPU**. La doppia bisezione su
`pre_ko` non viene piu' chiamata a ogni giro, quindi la cache oggi non ha quasi
niente da cachare *su Mike*. Resta: (a) corretta e a costo zero, (b) utile per
Omega e Safe, che chiamano `residual_grid` per conto loro, (c) una rete di
sicurezza se quel percorso tornasse caldo. La misura **2,31x / 2,37x con sha
identica** resta valida per il codice di allora (`f7e3c8b6213c`) ed e' la prova
che la memoizzazione non cambia un numero.

**Latenza di lettura — FATTA.** `banco_comune.py`: `LATENZA_LETTURA_S = 0.120`
(la stessa `config.place_latency` gia' certificata, non un numero nuovo),
`MercatoFlumine._costa_una_lettura` su `list_current_orders`,
`list_cleared_orders` e `read_book`, e `MotoreReplay.consuma_tempo` che fa
scorrere il tempo di mercato senza far girare il bot (lo scanner invece continua
a ricevere, come in produzione). Dichiarata come **assunta, non misurata** nel
commento e nel referto, che stampa anche «chiamate di LETTURA a Betfair: N (x
per giro) -> s di tempo di mercato consumati». Manopola: `LATENZA_LETTURA_S`
(0.0 riporta il banco a com'era). Test: `test_una_lettura_costa_tempo_di_mercato`
(il conteggio dei tick cambia se la si spegne -> il controllo sa vedere
l'assunzione) e `test_la_latenza_di_lettura_e_dichiarata_e_governabile`.

## 3-bis. RESTA DA FARE

0. (fatto, vedi sopra) ~~Confronto sha appaiato prima/dopo la cache~~ su `35760084` scenari
   `base` e `taker`. Comando esatto (le corse vanno lanciate INSIEME, perche'
   sulla macchina lavorano altri delegati e il codice di Mike cambia sotto la
   misura):
   ```
   REPO="$PWD" python <scratchpad>/appaiato.py 35760084 base cache
   REPO="$PWD" python <scratchpad>/appaiato.py 35760084 taker cache
   ```
   `appaiato.py` lancia in parallelo A (tutto spento), B (generatore veloce) e C
   (B + cache Poisson **in memoria**), e stampa per ognuna wall, CPU, picco di
   memoria, **sha del referto** e **impronta del codice**: le sha devono
   coincidere. Adesso che la cache e' nel file, per avere il "PRIMA" si spegne a
   runtime cosi':
   ```python
   M._poisson_grid = M._poisson_grid_memo.__wrapped__
   M._full_match_1x2 = M._full_match_1x2.__wrapped__
   _rg = M._residual_grid_memo.__wrapped__
   M.residual_grid = (lambda lh, la, rho, mg, *, dixon_coles, cv=0.0:
                      _rg(lh, la, rho, mg, bool(dixon_coles), float(cv or 0.0)))
   ```
   (e' gia' scritto in `/tmp/senza_cache.py`, usabile anche come `-p senza_cache`).
   **Misura gia' presa con la stessa cache messa in memoria** (prima che fosse
   nel file), corse simultanee sullo stesso codice `f7e3c8b6213c`:
   | scenario | senza cache (wall/CPU) | con cache (wall/CPU) | sha |
   |---|---|---|---|
   | base | 1118,1 / 1028,7 s | **484,5 / 444,7 s (2,31x)** | identica |
   | taker | 1313,2 / 1153,3 s | **560,1 / 486,8 s (2,37x)** | identica |
   Con `residual_grid` e `_full_match_1x2` cachate (oggi) il guadagno atteso e'
   maggiore: **va rimisurato**.
1. **Rimisurare la latenza di lettura su una partita intera**: i test la
   provano, ma non ho ancora un prima/dopo su `35760084` con sha (la misura
   costa ~20 minuti di macchina).
2. Portare la cadenza a fine giro anche nei replay di **Omega** e **tennis**
   (una riga per file, `_ultimo_ms` dopo il giro): li stanno scrivendo i loro
   delegati.
3. ~~Latenza 120 ms~~ — fatta. Resta da **sostituire l'assunzione con una
   misura vera**: serve una catena dei tempi per le LETTURE, come
   `storia_operazioni.py` ha gia' per il piazzamento (`t4_inviato ->
   t5_risposta`). Finche' non c'e', il referto dice «assunta, non misurata».

## 4. Misure gia' prese (reperti nello scratchpad della sessione)

- `profilo.txt` — profilo campionato: `_run_event` 90,2 %, dentro cui
  `lambdas_from_pre_ko` **83,6 %**; `payload_signature` 8,7 %; **flumine + banco
  0,6 %**.
- `appaiato_base.txt` / `appaiato_taker.txt` — generatore veloce: referto
  identico, guadagno end-to-end ~1 % su questa partita (perche' flumine vale
  0,6 %), **5,0x-5,6x sul livello stream** (15,0 -> 2,9 s su 35760084; 62,9 ->
  10,9 s su 35768297 da 25 MB), con gli **stessi book emessi** (643.713 e
  2.378.913) e il 90 % di oggetti in meno costruiti.
- `pool.txt` / `pool2.txt` — `--worker` 3: 3 partite 344,5 -> 320,2 s (campione
  sbilanciato), 1 partita x 3 scenari **71,9 -> 41,9 s (1,72x)**, referto
  identico riga per riga; **picco per worker 176-184 MB** (la memoria non e' il
  limite: i core lo sono).
- `tempo_sep.txt` — i due effetti della regola del tempo, separati, corse
  simultanee sullo stesso codice `bb7238a9e552`:
  | | wall | CPU | sha | effetto sul referto |
  |---|---|---|---|---|
  | entrambe spente | 1679,3 | 1228,2 | `b8c36a2b9e4a` | — |
  | solo attesa esatta | 1651,9 | 1240,8 | `0f8a5de001ed` | tick 55769->55778, book attesi 4813->4748; **ordini, azioni e fill invariati**; 0 violazioni |
  | solo cadenza a fine giro | 1648,7 | 1245,8 | `5b68759589e7` | decisioni 5838->5815, azioni 12->15, **ordini 10->13** (4 `place_rifiutato` + 4 `skip`: FOK non abbinati, ramo vero di Mike), controlli piu' sollecitati (C1/C3 8->11, J2 6->9, A3 10->13); **0 violazioni** |
  Attribuzione: il comportamento lo cambia la **cadenza**, non l'attesa.
- `gol_precoce.txt` — `35777617 --scenari gol-precoce`: 121.738 tick, 7.605
  decisioni, 0 violazioni; ordini uccisi dalla sospensione **0**, **R1 x0** (il
  ramo resta «non lo so»).

## 5. ⚠️ I 13 ROSSI DI `Betfair/mike` NON SONO MIEI (da confermare)

`python -m pytest Betfair/stream Betfair/mike -q` -> **13 failed, 2101 passed**.
Tutti in `Betfair/mike/tests/` e tutti su comportamento dell'**engine/service**
di Mike, che sta modificando un altro delegato e che io non ho toccato:
`campo_ordine({'sizeMatched': 3.0}, 'size_matched')` torna `None` (normalizzazione
camelCase sparita), `['cancel','place'] == ['cancel']` (cancel+place nello stesso
giro), «kind dichiarati in UI e mai scritti: `chiuso_dall_utente`,
`loss_exit_deciso`». Alle 17:00 `Betfair/mike` era **659 verdi** con le mie
modifiche al banco gia' dentro. La prova in corso quando la sessione si e'
interrotta: rilanciare quei test con la memoizzazione SPENTA
(`-p senza_cache`, vedi §3.1): se restano rossi, non sono della cache.
**AGGIORNAMENTO**: dei 13 ne restano **3**, tutti sulla normalizzazione
camelCase di `service.py::campo_ordine` (`test_si_accettano_tutte_e_due_le_grafie`,
`test_gli_ordini_arrivano_normalizzati_anche_se_camelCase`,
`test_la_vecchia_chiave_camelCase_continua_a_funzionare`): `campo_ordine` sta in
`Betfair/mike/service.py`, che non ho mai toccato, e nessun mio file lo
nomina. Gli altri 10 sono rientrati da soli mentre l'altro delegato lavorava
(`test_mike_engine.py` e' tornato 57/57). Ultima corsa completa:
`Betfair/stream` + `Betfair/mike` + `Betfair/omega` -> **2864 passati, 3
falliti**; `pytest -m cert` -> **18 verdi**.

## 6. Cosa e' gia' FATTO e consegnato (referto parziale gia' inviato)

Generatore memorizzato (`GeneratoreLibri`), pool `--worker` con memoria nel
referto, `DbMemoria.ht_ft_rows`, `_lapse_alla_sospensione`, regola del tempo
(`ATTESA_ESATTA`, `CADENZA_DOPO_LE_CHIAMATE`), test di identita' a 7 casi con
falsificazioni, diagnosi del tennis 35795560 (i tre scenari **non condividono
l'ingresso**: `safe-t1` chiede 1,08 in `base` e 1,58 negli altri due, dove e'
**identico** — non e' un difetto dell'orologio).
