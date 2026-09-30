# SAFE - P&L regolato da Betfair NETTO di commissione (30/09/2026)

Delegato costruttore (Opus), worktree `agent-aca712a4e53a0126a`. Base: il ramo del worktree e'
stato portato in avanti (fast-forward, nessuna modifica locale) a `master` 2a5cbba; la patch
`SAFE_PNL_NETTO_COMMISSIONE.patch` (`git diff HEAD`, nuovi file con `git add -N`) si applica
anche su `master` 1b1fe3b (nessun file toccato cambia fra i due). Nessun commit, nessun push,
nessuno stash, nessuna chiamata a Betfair, DB solo in lettura.

## 1. Reperto sui dati: il `profit` di Betfair e' LORDO

**Documentazione nel repo** (`Betfair/Betfair_api_documentation.pdf` pag. 54, testo estratto con
pypdf): `listClearedOrders` groupBy MARKET, back 2,00 @ 1,28 WON -> `profit` 0,56 (= 2 x 0,28,
lordo) e `commission` 0,03 A PARTE; back 2,00 @ 2,18 WON -> `profit` 2,36 (= 2 x 1,18),
`commission` 0,12.

**Conto vero** (DB, sola lettura, script `AUDIT_2026-09-30/sonda_profit_lordo_netto_2.py`):
`safe_strategy_trades` LIVE con `meta.pnl_source.kind = betfair_cleared` = 14 righe (#298..#337).
Il `profit` scritto da Betfair e' ESATTAMENTE stake x (quota - 1) sulle back vinte, cioe' lordo:

| riga | scommessa | profit Betfair | lordo atteso | netto al 5 % | Safe ha scritto `pnl` |
|---|---|---|---|---|---|
| #332 | back 3,00 @ 1,16 WON | 0,48 | 0,48 | 0,46 | 0,48 |
| #335 | back 3,00 @ 1,12 WON | 0,36 | 0,36 | 0,34 | 0,36 |
| #334 | back 3,00 @ 1,10 WON | 0,30 | 0,30 | 0,28/0,29 | 0,30 |
| #336 | back 3,00 @ 1,05 WON | 0,15 | 0,15 | 0,14 | 0,15 |
| #317 | lay 3,11 @ 1,08 WON | 3,11 | 3,11 | (mercato con #307) | 3,11 |

`commission` a livello di scommessa: **null su tutte le 14 righe** (Betfair la da' solo
raggruppando per mercato). Le colonne `pnl_betfair`/`commissione_betfair` sono vuote su TUTTE
le tabelle (`safe_strategy_trades`, `omega_trades`, `mike_trades`, `betfair_live_orders`: 0
righe), quindi la commissione VERA di questi mercati non e' leggibile dal DB e non ho chiamato
Betfair: **nessun reperto con la commissione osservata**. La prova che `profit` e' lordo e'
aritmetica (0,48 = 3 x 0,16 al centesimo; un netto al 5 % sarebbe 0,46) e documentale (pag.
54). La «verifica» del 17/09 (#298 +0,19 / #299 -0,09 = +0,10) e' un mercato con +0,10 di
vincita netta: commissione 0,005, che arrotonda a 0 o 0,01 e non distingue lordo da netto.

Stima del sovrastimato sulle 14 righe (aliquota ASSUNTA 5 %, per mercato): circa 0,08-0,10 EUR
(#332 0,02, #335 0,02, #334 0,01-0,02, #336 0,01, coppia #326/#327 0,01, coppia #307/#317 0,01,
#298/#299 0-0,01).

## 2. Cosa cambia

La regola e' UNA, quella del runner (`reconcile_worker.commissioni_per_ordine`, che scrive
`pnl_betfair`) e di Mike (`regolato_conto.componi_regolato`): netto della scommessa = `profit` -
quota della `commission` del suo MERCATO, ripartita sui profit positivi di TUTTE le scommesse del
conto su quel mercato, somma esatta al centesimo; mercato in perdita = nessuna commissione.
Riusata, non riscritta (import di `commissioni_per_ordine`).

| file | prima | dopo |
|---|---|---|
| `Betfair/safe_strategy/execution.py` `_posizione_da_cleared` (~2176) | P&L = `profit` per scommessa («GIA' netto») | P&L = `lordo - quota` (`_lordo_per_bet` somma i record doppi, `_quote_commissione` chiama `commissioni_per_ordine`); se la commissione del mercato manca -> `None` -> ripiego sul calcolo (gia' netto), MAI il lordo come netto |
| idem `_pnl_source_betfair` | `profit`, `commission` | + `lordo`, `commissione_quota`, `netto` in `meta.pnl_source` (il `profit` lordo resta dichiarato) |
| idem `settle_position` | `cleared_orders` | + parametro `cleared_markets` (default `None`: Omega che non lo passa resta identica) |
| `Betfair/safe_strategy/bot_service.py` `_cleared_orders_for_market` (~1877) | `market.list_cleared_orders(market_ids)` = scommesse SOLO di Safe, SETTLED+VOIDED | `(scommesse, mercati)`: `list_account_cleared_bets` (SETTLED, tutto il conto sul mercato) + `list_account_cleared_markets` (groupBy MARKET, solo se c'e' almeno una scommessa regolata) |
| idem `settle_open` (~1975) | `cleared_orders=cleared_cache[mid]` | `cleared_orders=..[0], cleared_markets=..[1]` |
| idem `_MercatoSafe` (~124) | - | `list_account_cleared_bets` / `list_account_cleared_markets`: STESSI NOMI dello sportello di Mike e del banco (`banco_comune.py:965/1020`), delegano a `omega_market` |
| `Betfair/omega/omega_market.py` | - | `list_cleared_bets_account(market_ids, stato)` e `list_cleared_markets_account(market_ids)` (stesso corpo delle letture di Mike in `mike/service.py:236-280`); commento di `_riga_regolata` corretto («profit LORDO») |

Perche' il conto intero e non solo Safe: la commissione del mercato e' del CONTO; ripartirla solo
sulle scommesse di Safe, con un ordine dell'utente in utile sullo stesso mercato, darebbe a Safe
anche la commissione dell'utente (test 5).

### Chiamate Betfair (per mercato chiuso con posizioni di Safe, solo al regolamento)

- **Prima**: 2 (`listClearedOrders` filtrata sui ref di Safe, SETTLED + VOIDED).
- **Dopo**: 2 (`listClearedOrders` SETTLED del conto sul mercato + `listClearedOrders`
  groupBy MARKET); 1 se Betfair non ha ancora regolato nulla. Zero a ogni giro su posizioni vive
  (si legge solo con `snap.closed`, una volta per mercato per giro, come prima).
- Misurato con `AUDIT_2026-09-30/sonda_chiamate_regolamento_safe.py` (sportello di produzione
  `_MercatoSafe(omega_market)`, client finto): chiamate del regolamento
  `listClearedOrders:SETTLED:conto`, `listClearedOrders:MARKET`; P&L scritto 9,50 = 10,00 lordo -
  0,50 commissione. Le altre chiamate stampate (listCurrentOrders, SETTLED/VOIDED del conto,
  LAPSED/CANCELLED) sono della sorveglianza del conto e della consapevolezza, invariate.

## 3. Omega

Omega NON usa mai il `profit` di Betfair come P&L: `settle_open` regola con
`omega_engine.settle_pnl` (lay vinta = size x (1 - c)) e `_settle_hedged` chiama
`execution.settle_position` SENZA `cleared_orders` (-> `settle_group`, commissione sul netto di
mercato). `omega_service.py:6842` (`profit=profit`) e' il bool «uscita in utile» dell'etichetta,
non un importo. **Omega non toccata**; dimostrato con
`Betfair/omega/test_omega_pnl_netto_commissione_2026_09_30.py` (sportello che espone ANCHE il
regolato lordo: il P&L scritto resta size x 0,95; coppia lay 2 @ 110 + back 1 @ 100 -> 1,95 /
-1,00, posizione 0,95).

## 4. Test

- Nuovo `Betfair/safe_strategy/tests/test_pnl_netto_commissione_2026_09_30.py` (16 test, finti
  nella forma VERA: scommesse camelCase passate da `omega_market._riga_regolata`, mercato con le
  chiavi di `list_cleared_markets_account`, client con i metodi del client vero):
  vincente #332 (0,48 lordo, 0,02 -> 0,46); perdente (nessuna commissione); coperta #326/#327
  (0,44 / -0,25, posizione 0,19); parziali con due chiusure e record doppio (9,93 / -4,00 /
  -4,59, posizione 1,34); ordine dell'utente sullo stesso mercato (quota Safe 0,02 su 0,05);
  commissione mancante in 4 forme -> «calcolato» 0,46, mai 0,48; lettura al regolamento (2
  chiamate, 1 senza regolati, rete giu'/sportello muto -> ripiego); delega di `_MercatoSafe`;
  forma delle due letture REST; **giro vero** `bot_service.settle_open` LIVE con
  `_MercatoSafe(omega_market)` -> 9,50 e fonte `betfair_cleared`.
- Aggiornato `test_settlement_betfair_truth_2026_09_17.py`: il finto metteva `commission: "0.05"`
  sulla scommessa (Betfair non la da': difetto 27) e certificava il lordo come netto. Ora con la
  lettura per mercato: #298 0,18 (commissione ASSUNTA 0,01), #299 -0,09, posizione 0,09; #297
  0,09 con commissione 0,00.
- Nuovo `Betfair/omega/test_omega_pnl_netto_commissione_2026_09_30.py` (2 test).
- Suite: `python -m pytest Betfair/safe_strategy Betfair/omega -q -p no:cacheprovider` (ambiente
  neutro) = **3486 passed, 6 skipped, 1 xfailed** in 83 s; base prima della modifica = 3468
  passed, 6 skipped, 1 xfailed (+18 = i test nuovi). Referti: `baseline_suite_safe_omega.txt`,
  `suite_safe_omega_PNL_NETTO.txt`.

### Falsificazione (`AUDIT_2026-09-30/falsifica_safe_pnl_netto.py`, esito `.out`)

Copia -> mutazione -> pytest -> ripristino dalla copia con hash identico (mai git checkout);
`MUTAZIONE` assente dal codice dopo il giro. **10 su 10 ROSSE**:
F1 lordo scritto come netto (il difetto) · F2 commissione mancante = 0 · F3 record doppi non
sommati · F4 `settle_open` non passa i mercati · F5 niente lettura per mercato · F6 sportello con
la lettura filtrata per strategia (quella di prima) · F7 senza `groupBy=MARKET` · F8 scommesse
del conto filtrate per strategia · F9 Omega lay vinta senza commissione · F10 calcolo senza
commissione sul netto di mercato.

## 5. Replay di certificazione (dal worktree, uno alla volta, junction `_live_raw` tolta dopo)

`python -m Betfair.stream.backtest.certifica <bot> 35760084 --scenari rapidi --trasporto entrambi`
(`--worker 1` per Safe). Confronto con `AUDIT_2026-09-30/replay/*_FINALE.txt` del checkout
principale via `confronta_referti.py` (stessa regola di `/tmp/confronta_altri.sh` + le righe
`pulita/decisioni/azioni/violazioni` e `ordini coda/canale` per intero):

| bot | durata | esito | differenze |
|---|---|---|---|
| safe_base | 168 s (profilo 159,9 s) | ESITO OK | solo i secondi di R1/R2b; decisioni 3512, azioni 2, violazioni 0, parita' coda/canale 2=2: IDENTICHE |
| safe_esatto | 218 s (178,7 s) | ESITO OK | solo secondi (R1, R8, R2b); decisioni/azioni/violazioni IDENTICHE |
| safe_punta | 196 s (142,7 s) | ESITO OK | solo secondi (R1, R4, R8, R2b); IDENTICHE |
| omega | 152 s (142,7 s) | ESITO OK | solo secondi (R10, R2b); IDENTICHE |

Referti: `AUDIT_2026-09-30/replay/{safe_base,safe_esatto,safe_punta,omega}_PNL_NETTO.txt`.
Nessuna differenza di decisioni, ordini, parita' o violazioni. **Nessuna riga di P&L da
confrontare**: questo profilo («rapidi» + trasporto) non stampa il P&L, quindi la differenza
«commissione tolta» non e' visibile nei referti (vedi §7).

## 6. Parita' paper/live

Paper: `_cleared_match` non trova mai una riga `paper` -> calcolo (`settle_group`/`settle_pnl`),
gia' netto. Live: netto di Betfair (lordo - quota della commissione del mercato) o, se Betfair
non ha ancora la commissione, lo stesso calcolo netto. Nessun ramo produce piu' un lordo.

## 7. Cosa NON ho fatto / NON ho potuto verificare

- La commissione VERA di un mercato di Safe: nessuna chiamata a Betfair; il DB non ha
  `pnl_betfair` (0 righe). La forma della risposta groupBy MARKET viene da documentazione,
  runner e Mike, non da una risposta vista oggi.
- Se nel replay il regolamento di Safe sia passato dal ramo `betfair_cleared` (il banco espone
  `list_account_cleared_*`): il profilo rapido non stampa P&L ne' la fonte. Serve un profilo
  che stampi il P&L per mostrare la differenza al centesimo.
- La lettura VOIDED non si fa piu' al regolamento: una scommessa di Safe annullata da sola su un
  mercato regolato (caso raro) fa ripiegare sul calcolo; un mercato annullato passa gia' da
  `snap.voided` senza cleared.
- `settle_orphan_closing` (gambe orfane) resta col calcolo: invariato.
- Duplicato da unificare (fuori perimetro, Mike): `mike/service.py _RealMarket.
  list_account_cleared_bets/markets` hanno lo stesso corpo delle nuove funzioni di
  `omega_market`; potrebbero delegare (2 righe).
- Nel working tree `execution.py` e il test del 17/09 sono ora a fine riga LF (core.autocrlf =
  true: il blob e la patch non cambiano).

## 8. Reperti aperti e decisioni per l'utente (nessuna strategia toccata)

1. **Safe regola «cieco»** (pre-esistente, non toccato): al primo giro con mercato chiuso, se
   Betfair non ha ancora regolato, scrive subito il calcolo e non ci torna piu'. Mike invece
   ASPETTA in SETTLING (ritentativi 1-2-4-8 poi 15 min, tetto 20). Proposta: stessa attesa per
   Safe (tocca il ciclo di regolamento, non la strategia) - decisione del coordinatore.
2. **Omega regola sempre col calcolo** (netto, ma mai col regolato vero del conto) e nette per
   posizione, non per mercato: con piu' posizioni singole indipendenti sullo stesso mercato la
   commissione calcolata puo' differire di qualche centesimo da quella di Betfair. Da portare al
   livello di Mike/Safe se si vuole il «P&L del conto» anche per Omega.
3. L'aliquota del conto (5 % assunto dai parametri) non e' verificata contro Betfair.

## 9. Da controllare dal vivo al prossimo avvio (live)

Alla prima posizione LIVE di Safe regolata: in `safe_strategy_trades.meta.pnl_source` devono
comparire `kind=betfair_cleared`, `lordo`, `commissione_quota`, `netto`, con `pnl = netto`;
quando il runner scrivera' `pnl_betfair` sulla stessa riga, i due numeri devono coincidere al
centesimo. Chiamate al regolamento: 2 per mercato (log REST).

## File

Toccati: `Betfair/safe_strategy/execution.py`, `Betfair/safe_strategy/bot_service.py`,
`Betfair/omega/omega_market.py`, `Betfair/safe_strategy/tests/test_settlement_betfair_truth_2026_09_17.py`.
Nuovi: `Betfair/safe_strategy/tests/test_pnl_netto_commissione_2026_09_30.py`,
`Betfair/omega/test_omega_pnl_netto_commissione_2026_09_30.py`.
Nel referto (fuori patch): `AUDIT_2026-09-30/SAFE_PNL_NETTO_COMMISSIONE.{md,patch}`,
`sonda_profit_lordo_netto{,_2}.py` (SELECT), `sonda_chiamate_regolamento_safe.py`,
`falsifica_safe_pnl_netto.{py,out}`, `confronta_referti.py`, `env_neutro_safe_pnl.ps1`,
`baseline_suite_safe_omega.txt`, `suite_safe_omega_PNL_NETTO.txt`, `replay/*_PNL_NETTO.txt`.
Nessuna migrazione SQL.
