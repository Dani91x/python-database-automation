# W_T - P15 (Posizioni aperte) + P14 (ordini del conto fuori dai bot)

Worktree: `C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a4993b702a303cacc`.
Base: `d4b4f6b` (`checkout --detach -f`) + `R_T_incr_lane.patch` (applicata pulita). Nessun commit, nessun build.
Patch: `W_T.patch` = `git diff -- frontend/` (R_T + P15 + P14). Solo P15: `W_T_P15.patch`.
Backup della base precedente: `T_backup_pre_W.patch`.

## P15 - «Posizioni aperte» da trader

| Prima | Dopo |
|---|---|
| Linguetta `Posizioni aperte 5` (righe, live+paper insieme) | `Posizioni aperte 2 LIVE · 1 prova` (PARTITE; LIVE in rosso) |
| Un solo elenco + banner `3 posizioni con soldi veri` | Due sezioni: `LIVE: soldi veri [2]` sopra, `PROVA: simulato, mai sommato [1]` sotto; banner `2 partite con posizione LIVE · 3 gambe con soldi veri` |
| Nessuno stato per partita | Per ogni partita LIVE: `A RISCHIO` / `PAREGGIATA` / `DA REGOLARE` / `NON CALCOLABILE` + `caso peggiore −9,80 €`; nel title i numeri per mercato (se vince / se perde / peggiore) |
| Fuori programma: riga compatta per gamba | Scheda con la stessa grafica: `NomiPartita` (nome della riga del bot) + «fuori dal programma di oggi», riquadro `CashOutGlobalePartita` con le sue operazioni, righe `RigaOperazione`; sotto, per gamba, la riga di sempre col «chiudi ora» (testid `cr-posizione`, `cr-chiudi` invariati) |
| Testata `Posizioni LIVE 3 partite` | `Posizione LIVE 3 partite con posizione LIVE (5 gambe)` |

- **Regole:** una partita va fra le LIVE se ha almeno una gamba NON paper; una modalità non dichiarata va fra le LIVE (fail-safe).
- **Stato** (`components/controlroom/aperte/statoPartitaAperta.ts`, puro):
  - `gambeDaOperazioni` + `cashOutPartita` SENZA prezzi: servono solo le esposizioni (seVince/sePerde), quindi nessuna sottoscrizione.
  - Caso peggiore per mercato = min(somma L, min_k(W_k + somma L_{j≠k})); sui mercati a due esiti si riduce a min(W, L). La partita somma i mercati.
  - A RISCHIO se < 0; PAREGGIATA se ≥ 0 (nessun esito perde: green fatto, anche in utile). Farul vale +0,04/+0,06: non è «piatto» per `PIATTO_EPS`, ma non perde su nessun esito.
  - DA REGOLARE se la partita del programma è `chiusa`.
  - NON CALCOLABILE se manca un dato della gamba (i «manca il prezzo» non contano) o se nessuna gamba LIVE è abbinata.
  - Per i mercati di Mike `dueEsitiMike(mike)` (già in pagina).
- **Test:**
  - `statoPartitaAperta.test.ts` (6): Follo −9,80 A RISCHIO, Farul PAREGGIATA, DA REGOLARE, NON CALCOLABILE, PROVA esclusa, nessun abbinato.
  - Pagina (3): due elenchi e linguetta, stati, fuori programma.
  - Cambiati: «1 posizione con soldi veri» → «1 partita con posizione LIVE · 1 gamba con soldi veri» (partite e gambe mai con la stessa parola); `soldiVeri.test` `partiteConPosizione` ha in più `gambeLive: 5`; i finti `partite` della testata in `ControlRoom.test` hanno `gambeLive`.
- **Falsificazioni** (`mut_w15.json`), tutte ROSSE: sempre PAREGGIATA (2), prezzo mancante come dato mancante (4), caso peggiore senza il ramo «nessuna vince» (1), partita paper fra le LIVE (1), linguetta col contatore unico (1).
- **Test di blocco P15:** `npx vitest run src/pages/ControlRoom.test.tsx src/components/controlroom --maxWorkers=2` = 70 file, 1055 verdi.

## P14 - ordini del conto fuori dai bot, per partita

- **Lettura** (`lib/liveOrders.ts`):
  - Tipi `OrdineContoFuoriBot` / `OrdiniContoFuoriBot` con le chiavi ESATTE del contratto, e `fetchLiveOrdersAccountOpen()` (RPC `get_live_orders_account_open`).
  - Una risposta senza `rows`/`letto_at` o un errore = eccezione.
- **Hook** (`useControlRoom.ts`, additivo):
  - Stato `ordiniConto` letto dentro `ricarica` (stesso giro dei 30 s, nessun poll nuovo) e dopo ogni clic di chiusura (`seguiClic`).
  - Errore o RPC assente = `non-letti` col motivo «RPC non disponibile», e NON entra in «fonti non raggiunte»: finché la migrazione non è applicata comparirebbe a ogni giro.
  - Campi nuovi: `ordiniConto` e `soldiVeri.ordiniFuori`.
- **`components/controlroom/ordiniConto.ts`** (puro): raggruppamento per `event_id` (gli ordini senza partita vanno a parte), motivo della lettura fallita, partite coi nomi.
- **`OrdiniContoPartita.tsx`:**
  - Mostra `Ordini dal sito/app (conto Betfair): BACK Over 3.5 Goals 4,43 € @ 1,92 · BACK Under 4.5 Goals 5,18 € @ 1,44 [CONTO BETFAIR · 12 s fa]`.
  - Sotto, in ambra: «il bot non li vede: la cifra del cash out delle gambe dei bot non e' la posizione del conto».
  - Se non letti: `ordini del conto: non letti (RPC non disponibile)`.
  - Partita senza ordini fuori dai bot (letti): niente. Fuori contesto: niente.
- **Montaggio:**
  - `SchedaPartita.tsx`: 1 riga subito sotto `CashOutGlobalePartita` più l'import.
  - Scheda fuori programma: stessa riga.
  - Contesto `OrdiniContoContext` intorno alle schede in `ControlRoom.tsx`: 2 righe fuori dalla zona dichiarata, necessarie perché `SchedaPartita` non riceve il modello di vista.
  - Col campo assente dal modello (finti di prima) il contesto è `null`: niente a schermo.
- **Testata** (`FasciaSoldiVeri`): `ORDINI FUORI DAI BOT: partite con ordini fuori dai bot: 1 (FC Vsetin v Bohemians)` in ambra (più «+ N senza partita»); non letti = `ordini del conto: non letti (RPC non disponibile)`, mai «0».
- **Test:**
  - `OrdiniContoPartita.test.tsx` (6): puro e componente, il caso Vsetin nella forma del contratto.
  - Hook (+3): RPC assente → non letti e non fra le fonti cadute; letti per partita; una lettura per giro.
  - Testata (+1). Pagina (+2): scheda live con l'ordine e l'avviso; non letti.
- **Allineato al contratto committato (`2a5cbba`):**
  - `price_matched: number | null`: con null la riga dice «non abbinato», niente «0,00» e niente quota.
  - `source: 'runner' | 'account'`.
  - Limite del backend a schermo: «aperto per il conto letto alle HH:MM:SS» (da `letto_at`, ora di Roma).
  - Scheda TENNIS: niente, perché gli ordini manuali tennis stanno in `tennis_live_orders`. Il prop `sport` passa dalla riga di montaggio.
- **Test del contratto:** finti con `price_matched: null` e con `event_id: null`.
- **Falsificazioni** (`mut_w14.json`, `mut_w14b.json`, `mut_w14c.json`), tutte ROSSE, ripristino con hash:

| Mutazione | Esito |
|---|---|
| RPC assente scritta come lista vuota | ROSSO 1 |
| ordini del conto non letti nel giro | ROSSO 3 |
| avviso ambra tolto | ROSSO 2 |
| «non letti» non detto | ROSSO 1 |
| testata: «non letti» mostrato come 0 | ROSSO 1 |
| RPC assente non riconosciuta | ROSSO 2 |
| `price_matched` null mostrato 0,00 | ROSSO 1 |
| scheda tennis che promette ordini del conto | ROSSO 1 |
| «aperto» senza l'ora della lettura | ROSSO 1 |

- **Verifiche:**
  - `npx vitest run src/pages/ControlRoom.test.tsx src/components/controlroom src/lib/liveOrders --maxWorkers=2` = 74 file, 1133 verdi (prima dell'allineamento a `2a5cbba`).
  - Dopo l'allineamento: `OrdiniContoPartita.test` 9/9; `SchedaPartita.test` + hook + pagina = 173 verdi.
  - `npx tsc -p tsconfig.app.json --noEmit` = 0.

## COSA NON HO FATTO / NON VERIFICATO

- La RPC non esiste ancora: il ramo «letti» è provato solo coi finti del contratto. Da provare dal vivo dopo la migrazione.
- La verifica per partita è un AVVISO: non calcolo la posizione del conto sommando gli ordini del sito alle gambe dei bot.
- Gli ordini con `event_id` null finiscono solo nel conteggio della testata («+ N senza partita»).
- L'app a schermo non l'ho vista (altezza delle due sezioni, lettura degli stati).
- `SchedaPartita.tsx` è stata toccata con UNA riga più l'import, sotto il riquadro del cash out, senza cambiarlo.
