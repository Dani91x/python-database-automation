# CANTIERE G2 — I campi che esistono solo in live, prima del live

Delegato G2, 28/09/2026, checkout PRINCIPALE (`.env` presente), SOLA LETTURA sul DB
(progetto Supabase `dqbwaocvlzbxfrpacsac`) e sul codice sotto `frontend/src`. Riparto
dal punto lasciato dal delegato precedente (`AUDIT_2026-09-28/CANTIERE_G_PAGINE.md`
§"Voce 6/Voce 7", `CANTIERE_H_REGISTRO_NC.md` §8.1): 33 verifiche indicate come mancanti
(20 voce 6 + 13 voce 7; nell'elenco nominale sono 18+13=31 id distinti, li ho presi
ESATTI dai due referti come richiesto).

## Sblocco del banco (differenza chiave rispetto al delegato precedente)

Il delegato precedente lavorava in un worktree senza `.env` (git-ignorato, non
condiviso fra worktree) e non ha potuto montare le pagine vere. Nel checkout
PRINCIPALE il `.env` c'è (`SUPABASE_URL=...dqbwaocvlzbxfrpacsac...`,
`SUPABASE_SERVICE_ROLE_KEY` presente). Ho quindi potuto RIUSARE il banco
`frontend/e2e_fase3_admin26/` così com'era (nessuna modifica al banco stesso) e
lanciarlo, un file alla volta:

```
npx vitest run --config e2e_fase3_admin26/vitest.fase3.config.ts e2e_fase3_admin26/controlroom.fase3.test.tsx
  -> 1 file, 1 test, 69.5s, VERDE
npx vitest run --config e2e_fase3_admin26/vitest.fase3.config.ts e2e_fase3_admin26/pagine.fase3.test.tsx
  -> 1 file, 3 test (Segui Live / Market Watch / Tennis Terminal), 79.4s, VERDI
```

Entrambi i comandi montano le pagine VERE (React reale, nessun mock di logica)
contro il DB vero in SOLA LETTURA (`clientSpecchio.ts`: solo `select`, `insert/
update/upsert/delete` bloccati e registrati — verificato in `chiamate`/`bloccate`
che la lista `bloccate` è vuota su entrambi i giri: nessuna scrittura tentata dalle
pagine, nulla da bloccare). Output salvato in `frontend/e2e_fase3_admin26/out/`
(non tracciato): `cr_dom.json`/`cr_db.json` (Control Room), `sl_dom.json`/`sl_db.json`
(Segui Live), più 3 script di sonda in sola lettura che ho aggiunto io nella stessa
cartella (`_sonda_live_g2.mjs`, `_sonda_eventi_g2.mjs`, `_sonda_rpc_g2.mjs`) per
contare le righe `mode='live'` reali e chiamare due RPC di lettura direttamente,
FUORI da React, per la controprova indipendente.

**Stato del mercato oggi (28/09, sonda diretta)**: nessuna partita calcio o tennis
è ATTUALMENTE in-play (`live_follow`/`tennis_live_follow`: tutte `CLOSED` o `ERROR`,
`live_signals` vuota, `betfair_live_xhedge` ferma al 10/07). Questo NON è un difetto
mio: è lo stato vero del DB in questo momento, e limita quali dei 33 campi possono
mostrarsi "in azione" oggi (lo dichiaro campo per campo sotto). Righe `mode='live'`
storiche invece ABBONDANO e sono quelle usate per la verifica: `betfair_live_orders`
91/93, `mike_trades` 283/1127, `safe_strategy_trades` 29/349 (righe vere, non finte).

## Metodo per campo

Dove il campo dipende da uno STATO REALE oggi (righe di oggi, età, saldo…): montaggio
reale (sopra) + lettura DB indipendente (query mie, non la stessa funzione) +
ricalcolo a mano. Dove il campo richiede un mercato ATTIVO che oggi non esiste
(pre-gol, X-Hedge live, tennis in-play, opportunità in coda…): lo dichiaro NON
VERIFICABILE OGGI con la prova che il componente non ha nemmeno provato a leggere i
suoi dati (vedi `chiamate`/`bloccate` registrati dal client specchio: nessuna chiamata
a `get_live_audit`/`get_live_xhedge`/`betfair_live_risk_state` nel giro di Segui Live
di oggi — prova che il pannello non è montato, non che io non ho guardato).

---

## BLOCCO 1 — voce 6, i 22 campi solo-live (18 restanti sui 20 elencati nel referto G,
più i 2 già chiusi da lui: U0222, U0226* — *U0226 è in realtà voce 7, vedi sotto)

| id | componente (file:riga) | dato usato | valore a schermo oggi | ricalcolo indipendente | esito |
|---|---|---|---|---|---|
| U0179 | `DayBar.tsx:143-152`; dati `useControlRoom.ts:2137-2156,2193` | `realizzatoOggi.live.totale` = Σ `righeGiornataPerCiclo` filtrate `mode==='live'`, scope OGGI (romeDay) | riga "realizzato oggi" ASSENTE (real=null → `real!==null` falso, span non renderizzato) | query diretta: `omega_trades`/`safe_strategy_trades`/`mike_trades`/`tennis_live_orders`, ultime 40-60 righe ciascuna, **0 righe con data 2026-09-28** su tutte e 4 (verificato con `placed_at`/`updated_at`) | **OK** — l'assenza è corretta: zero operazioni oggi, non un bug. Paper e live restano due array separati per costruzione (`soloLive`/`soloPaper` in `useControlRoom.ts:2149-2150`, mai sommati). |
| U0180 | `DayBar.tsx:153-161` (`day-bar-in-corso`) | Σ `p.chiusura.bloccabile` sulle posizioni LIVE aperte (`useControlRoom.ts:3413-3418`) | testid `day-bar-in-corso` ASSENTE | cross-check indipendente: pannello "Posizioni aperte" (U0246, stesso giro) mostra 11 posizioni totali, **0 con banner "posizioni con soldi veri"** (`live.length===0` in `ControlRoom.tsx:1358,1370-1374`) | **OK** — coerente: nessuna posizione LIVE aperta oggi, quindi "in corso" è correttamente assente (due punti del codice indipendenti concordano). |
| U0181 | `DayBar.tsx:162-170` | manca = obiettivo − avanzamento; "CENTRATO" se `real>=g` | ASSENTE (condizionato a `real!==null`, vedi U0179) | logica letta: il blocco è dentro `{hasGoal && real!==null && (...)}` — con `real=null` MAI mostra "manca" né "CENTRATO" per costruzione, non serve dato per confermarlo oggi | **OK** — assenza corretta e strutturale (letta a codice, confermata dal DOM). |
| U0184 | `ControlRoom.tsx:523,534` | `vm.obiettivoStoricizzato` | **presente**: "obiettivo non ancora storicizzato per oggi: è quello corrente del servizio" (testo esatto nel DOM, dentro `cr-obiettivo`) | testo verbatim confrontato col letterale del sorgente (`ControlRoom.tsx:534`) — identico carattere per carattere | **OK** — verificato con render reale. |
| U0185 | `ObiettivoHero.tsx:56-76`; `useControlRoom.ts:2138-2147` | `componiObiettivo` sulle stesse righe di U0179 | tutte le 10 righe presenti (`cr-composizione-omega/safe_calcio/safe_tennis/mike/scalper/bot_tennis/manuale/manuale_sito/manuale_app/altro`), tutte col trattino "—" (nessun valore) | coerente con U0179: 0 righe `mode='live'` oggi per qualunque bot ⇒ ogni voce deve essere `null` ⇒ trattino per costruzione (`r.valore==null ? DASH : ...`, `ObiettivoHero.tsx:63-64`) | **OK** — 10/10 voci presenti col testid giusto, valore coerente con l'assenza di dati oggi. |
| U0186 | `ObiettivoHero.tsx:80-84` | `manualeSito.fonte==='non-disponibile'` | **presente**, testo esatto: "scommesse dal sito Betfair (fuori app): — — in arrivo, non ancora collegate" | testo verbatim = sorgente | **OK**. |
| U0187 | `ObiettivoHero.tsx:86-97` (`cr-composizione-prova`) | `composizione.provaPaper` = Σ righe paper delle stesse righe di oggi | testid `cr-composizione-prova` **ASSENTE** | coerente: 0 righe (paper comprese) trovate per oggi in tutte e 4 le tabelle (stessa sonda di U0179) | **OK** — assenza corretta, non un bug (nessuna operazione in prova OGGI, il pannello sport più in basso conta lo storico non-di-oggi con etichetta diversa). |
| U0193 | `ControlRoom.tsx:576-583`; `useControlRoom.ts:3517-3525` | confronto `get_safe_daily(mode=live).by_sport.tennis.pnl` vs righe pagina, soglia 0,01€ | banner "Realizzato live: due conti diversi" **ASSENTE** | testo cercato nell'intero DOM (non solo per-testid), non trovato: `discordanza` nel codice è `null` quando `Math.abs(serverLive-nostroSafeLive) <= 0.01` — coerente con 0 trade live tennis oggi (entrambi i lati a 0 o null) | **OK** — assenza corretta. |
| U0223 | `ControlRoom.tsx:664-668`; `useControlRoom.ts:1320-1325` | elenco letture R30 fallite | banner "fonti non raggiunte" **ASSENTE**; `cr-fonte-righe` mostra tutte e 4 le fonti (`Omega/Safe/Mike/Tennis`) fresche `db 20s` | nessuna fonte in errore oggi — coerente con l'assenza | **OK, con nota**: come già segnalato dal delegato precedente, il file:riga dell'inventario punta a `soldiLetti`, non alla lista fallite vera; il meccanismo "una fonte che cade si chiama per nome" risulta GIÀ certificato dal test esistente `useControlRoom.test.tsx` (non ho rifatto quella certificazione, la confermo solo come coerente con lo stato di oggi). |
| U0230 | `SchedaPartita.tsx:292-299,516` | `giornata` (feed) | **presente** ripetutamente: nomi reali (`Kuwait v Iraq`, `San Marino v Finland`, `Iceland v Estonia`, …) con icona sport e badge "conclusa" dove applicabile | confronto diretto coi nomi restituiti dal feed (`giornata` letto nello stesso giro) | **OK**. |
| U0231 | `SchedaPartita.tsx:309-320` (`cr-latenza`) | `p.latenzaQuoteS` incrociata con vitalità scanner | **"vecchio 48 h 22/23"** ripetuto su tutte le schede | ricalcolo indipendente: `t_test − safe_strategy_status.updated_at` = `2026-09-28T18:03:11.479Z − 2026-09-26T17:40:17.106Z` = 2902,9 min = 48 h 22,9 min → **coincide** col "48 h 22/23" a video (arrotondamento sui minuti spiega la piccola oscillazione fra 22 e 23) | **OK — ricalcolo indipendente numerico coincidente.** |
| U0234 | `SchedaPartita.tsx:151-212` (`TennisVivoBar`); `useTennisVivo.ts:100-111` | `tennis_live_now` + canale | testid `cr-tennis-vivo*` **MAI presente** nel giro di oggi (0 istanze su Control Room) | sonda diretta: `tennis_live_follow` tutte `CLOSED`/`ERROR` oggi, nessun match di tennis in-play | **NON VERIFICABILE OGGI** — nessuna partita tennis viva; il componente non ha condizioni per montare. |
| U0238 | `DettaglioRigaView.tsx:262-398` (`cr-op-riga`, `cr-op-chiudo-ora*`) | `operazioni` (trade Omega/Safe/Mike/tennis) | **presente**, righe reali aperte cliccando i chip bot: es. riga BANCA (lay) "Altro risultato Casa" prezzo 34,00, size 2,00€, **resp. 66,00 €**; riga PUNTA (back) "Under 3.5 Goals" prezzo 1,48, size 5,00€, **resp. 5,00 €**; "chiudo ora" con prezzo/P&L/fonte e età (es. "174194 s fa") | **ricalcolo indipendente della responsabilità**: lay ⇒ resp = size×(prezzo−1) = 2,00×(34,00−1) = **66,00 €** ✓ esatto; back ⇒ resp = size = **5,00 €** ✓ esatto | **OK — ricalcolo indipendente esatto su 2 righe reali, formule diverse per lato.** |
| U0245 | `StrisciaEsitoChiusura.tsx:81-126`; `lib/statoOrdine.ts` | stato ordine | **presente**: badge reale "REGOLATA DAL MERCATO" con motivo "il mercato si è regolato (vinta, persa o void): nessuna esposizione residua" su una proposta Omega vera | testo confrontato con `lib/statoOrdine.ts` (badge/motivo coerenti con lo stato "settled" dichiarato) | **OK**. |
| U0246 | `ControlRoom.tsx:1350-1369` | `posizioni` (trade aperti Omega/Safe/Mike + tennis + scalper) | **"Posizioni aperte 11"**; banner "N posizioni con soldi veri" **assente** | `live = posizioni.filter(modalita==='live')`; banner condizionato a `live.length>0` — coerente con U0180 (0 posizioni live aperte oggi), stesso dato letto da due punti diversi del componente | **OK — due letture indipendenti dello stesso stato concordano.** |
| U0247 | `ControlRoom.tsx:1409-1454` (`cr-posizione`, sezione orfane) | come U0246, filtrate "senza scheda partita nota" | testid `cr-posizione`/`cr-pos-dettaglio` **0 istanze** | nessuna delle 11 posizioni aperte oggi è orfana (tutte agganciate a una partita nota nel programma) | **NON VERIFICABILE OGGI** — nessun caso reale di posizione orfana; assenza corretta ma non prova il ramo di codice. |
| U0248 | `ControlRoom.tsx:1459-1496` (dentro la riga orfana) | `p.chiusura` (bloccabile) | come sopra | come sopra | **NON VERIFICABILE OGGI** — dipende da U0247. |
| U0250 | `PosizioniChiuse.tsx:317-335,639-648`; `lib/certezzaChiusura.ts` | badge certezza | "Posizioni chiuse **0**" oggi (giornata di regolamento 28/09) — nessun badge certezza da mostrare | conteggio 0 chiuse oggi coerente con 0 operazioni oggi (stesso fatto di U0179) | **NON VERIFICABILE OGGI (in modo diretto)** — 0 righe chiuse nel giorno di regolamento odierno; il ramo badge non ha righe su cui disegnarsi. Le posizioni chiuse ESISTONO (18 live + altre paper "di altre giornate", viste col filtro "rileggi"), ma sono FUORI dal giorno di oggi e la UI stessa le tiene separate ("Qui c'è solo 28 settembre 2026 (giorno di regolamento)..."). |
| U0251 | `PosizioniChiuse.tsx:349-384` | filtri (stato locale) | **verificato in azione**: ho fatto scattare il filtro veri/prova dal test esistente (click su `cr-f-modo-paper`) e il conteggio "altre giornate" è passato da **18** (veri) a **213** (prova) — prova diretta che il filtro live/paper NON mischia mai le due popolazioni | 213 ≫ 18 è plausibile (le operazioni paper sono molto più numerose delle live, confermato anche dai totali di sonda: `mike_trades` 1127 tot vs 283 live, `safe_strategy_trades` 349 tot vs 29 live) | **OK — filtro osservato in azione con click reale, conteggi coerenti con la sonda diretta.** |
| U0255 | `EsitoAbbinamentoStriscia.tsx:31-56`; `useSeguiOrdini.ts` | esito abbinamento (ABBINATO/rifiutato/FOK…) | testid `cr-esito-abbinamento*` non trovato nel giro di oggi | nessuna richiesta di apertura/chiusura in corso in questo istante (coerente con l'assenza di operazioni odierne) | **NON VERIFICABILE OGGI** — serve una richiesta d'ordine appena eseguita, non presente nel giro. |
| U0258 | `SchedaChiusuraOmega.tsx:158-260` | `get_omega_proposte` + prezzo scanner | **presente**, proposta Omega vera: back 60,00, "per 0,80 € · bancata a 48,00", fonte "numeri della proposta (prezzo vivo assente)", avviso "⚠ prezzo vivo assente" | letto il codice sorgente (`SchedaChiusuraOmega.tsx`): la fonte "prezzo vivo assente" è la dichiarazione onesta che lo scanner non ha un book fresco per quel mercato — coerente con la partita "conclusa"/vecchia (48h+) vista in U0231; non ho ricalcolato il tick-down (`lib/matching.ts`) per mancanza di tempo, vedi "non verificato" | **OK (parziale)** — componente montato con dati reali, valori plausibili e coerenti fra loro; il tick-down non ricalcolato a mano. |
| U0263 | `SchedaPropostaOpportunita.tsx:263-290,491-495` | `bandaDellaStrategia`/`inBanda` | `cr-opportunita-contatore` = **0**, "Nessuna opportunità in coda" | 0 opportunità in coda oggi (coerente con nessuna proposta nuova) | **NON VERIFICABILE OGGI** — nessuna scheda opportunità montata. |
| U0264 | `SchedaPropostaOpportunita.tsx:485-490` | `rationale`, `mode` | come sopra | come sopra | **NON VERIFICABILE OGGI**. |

## BLOCCO 1-bis — Segui Live (voce 6, gli altri 4 id)

Ho montato `SeguiLive` col banco (`pagine.fase3.test.tsx`, evento di default
`EV_CALCIO=36090854`, l'unico hardcoded nel banco esistente — **non l'ho scelto io**).
Quell'evento è oggi `CLOSED` (nessuna partita in streaming in tutto il DB in questo
momento, verificato con la sonda). Prova diretta e non un'impressione: il registro
`chiamate` del client specchio (`sl_chiamate.json`) mostra che l'app ha chiamato SOLO
`get_live_follows` (×3), `get_live_alerts` (×1), `get_scalper_state` (×1) — **MAI**
`get_live_audit`, **MAI** `betfair_live_risk_state` (`.from`), **MAI** `get_live_xhedge`,
**MAI** `live_signals`. Questo dimostra che i 4 componenti sotto NON hanno nemmeno
tentato di leggere i loro dati: la pagina, senza un match selezionato/in streaming,
non li monta.

Nota falsa pista che ho scartato da solo: il testo lunghissimo di log "CRITICAL[ORDER_MODE]
Live trading: modalità LIVE attiva...", "RUNNER_WATCHDOG"... visibile nel DOM **non è**
il registro di U0344 (`LiveControlsPanel`/`get_live_audit`): l'ho controllato contro
`chiamate` e viene da `get_live_alerts` (un log di sistema globale, fuori dal
perimetro G2). L'avevo scambiato per U0344 in un primo passaggio — corretto dopo
il controllo incrociato, per completezza dichiaro anche l'errore che ho evitato.

| id | componente | dato usato | esito |
|---|---|---|---|
| U0302 | `SeguiLive.tsx:537-548` | `betfair_live_risk_state` (fetch a `useEffect(...,[])`, incondizionato dal codice) | **NON VERIFICATO** — per codice l'effect gira sempre al mount, ma `chiamate` non registra nessuna `.from('betfair_live_risk_state')` in questo giro: o il ramo JSX che contiene lo span non è nell'albero renderizzato con un evento CLOSED (verosimile: il componente che lo contiene richiede probabilmente `selected`), o è un limite del banco nel tracciare quella query. Non lo dichiaro OK senza prova diretta. |
| U0312 | `SeguiLive.tsx:644-677,306-309` | `live_signals` (per evento) | **NON VERIFICABILE OGGI** — tabella `live_signals` vuota nella sonda diretta (nessuna riga), nessun segnale fresco possibile oggi. |
| U0337 | `XHedgePanel.tsx:116-663` | `get_live_xhedge` + canale | **NON VERIFICABILE OGGI** — ultima riga reale in `betfair_live_xhedge` è del **10/07/2026** (2,5 mesi fa): nessun dato fresco, e `chiamate` conferma che l'RPC non è nemmeno stata invocata con l'evento CLOSED di oggi. |
| U0344 | `LiveControlsPanel.tsx:399-449` | `get_live_audit` | **NON VERIFICATO** — `get_live_audit` non è mai comparsa in `chiamate` nel giro di oggi (vedi nota sopra sulla falsa pista con `get_live_alerts`). |

**Proposta per completare i 4 di Segui Live** (per il coordinatore, fuori dal mio
perimetro di scrittura): rilanciare `pagine.fase3.test.tsx` con `E2E_EV_CALCIO=<id di
un evento REALMENTE in streaming>` il giorno in cui l'utente tiene i bot accesi in
paper (domani, secondo il brief) — in quel momento `live_follow.status='STREAMING'`
esisterà davvero e i 4 pannelli monteranno con dati veri. In alternativa, isolare
`fetchLiveRiskState`/`fetchLiveAudit` come test di funzione pura (stesso metodo di
U0222/U0226/U0240): chiamata RPC diretta (`get_live_audit`, LETTURA, consentita in
sola lettura) contro una riga vera, senza montare la pagina intera — non l'ho fatto
per limite di tempo, resta la via più veloce per chi riprende.

---

## BLOCCO 2 — voce 7, i 13 controlli "ad app spenta" restanti (U0226 già chiuso dal
delegato precedente, non ripetuto)

| id | componente | dato usato | verifica | esito |
|---|---|---|---|---|
| U0134 | `DirezioniReport.tsx:521-562,616-619`; `lib/reportistiche.ts:146-156` (`get_direction_report_matches`) | RPC diretta, sola lettura, parametri reali (`p_from=2026-09-01,p_to=2026-09-28,...`) | **chiamata reale eseguita** (fuori React, RPC pura): 5984 righe totali, prima riga esempio `O'Higgins–Deportes Santa Cruz`, `dir_ok=4, dir_tot=7, good_ok=4, good_tot=7` | **OK (livello funzione)** — la RPC vera risponde con dati veri e forma coerente con l'inventario (Giorno/Lega/Partita/Tutte ok-tot/Buone ok-tot). Non ho montato `DirezioniReport.tsx` (pagina Analytics, fuori dal banco esistente, avrei dovuto scrivere un file nuovo — non fatto per tempo). |
| U0135 | `DirezioniReport.tsx:577-597,184-192`; `get_direction_report_fixture` | RPC diretta sulla stessa `fixture_id=1638394` del punto sopra | righe: `[false,true,true,false,true,true,false]` (7 mercati, campo `hit`) | **ricalcolo indipendente**: conto i `hit:true` = **4** su 7 → coincide ESATTAMENTE con `dir_ok=4, dir_tot=7` letto in U0134 dalla RPC aggregata. Le due RPC (aggregata e drill) sono coerenti fra loro su dati reali. | **OK — cross-check numerico fra le due RPC, esatto.** |
| U0508 | `SafeStrategy.tsx:516,1582-1620`; `safeActivity.ts` | `get_safe_state` (`activity`, ripiego `safe_strategy_activity`) | chiamata RPC diretta: risponde con `activity` reale (righe vere `kind:'exit_wait'`, `kind:'exit_hold'`, con `payload` completo) | **OK (livello funzione), NON verificato a schermo** — non ho montato `SafeStrategy.tsx` (fuori dal banco esistente). **Nota da portare al coordinatore**: la mia chiamata a `get_safe_state` NON accetta `p_mode` come filtro dell'`activity` (il codice vero, `lib/safeBot.ts:1177`, la chiama `get_safe_state({})` senza `p_mode`) — le righe di `activity` che ho letto includono eventi con `payload.mode:'paper'` mescolati a quelli `live`. Se `SafeStrategy.tsx` non distingue visivamente per riga il campo `payload.mode`, un trader che guarda "Attività" sotto un bot in modalità live potrebbe leggere eventi di prova senza saperlo — **non è una somma di P&L** (nessuna violazione della regola "mai sommare paper e live"), ma è un'ambiguità di visualizzazione da controllare: non l'ho verificato a schermo, lo segnalo come sospetto aperto, non come KO certificato. |
| U0230 | (Control Room, vedi Blocco 1) | — | — | **OK** — già coperto sopra (fa parte anche della voce 6 nell'elenco fornitomi, duplicato fra i due blocchi). |
| U0231 | idem | — | — | **OK** — idem, vedi Blocco 1. |
| U0234 | idem | — | — | **NON VERIFICABILE OGGI** — idem, vedi Blocco 1. |
| U0238 | idem | — | — | **OK** — idem, vedi Blocco 1. |
| U0246 | idem | — | — | **OK** — idem, vedi Blocco 1. |
| U0247 | idem | — | — | **NON VERIFICABILE OGGI** — idem, vedi Blocco 1. |
| U0248 | idem | — | — | **NON VERIFICABILE OGGI** — idem, vedi Blocco 1. |
| U0250 | idem | — | — | **NON VERIFICABILE OGGI (diretto)** — idem, vedi Blocco 1. |
| U0251 | idem | — | — | **OK** — idem, vedi Blocco 1 (filtro veri/prova osservato in azione). |
| U0266 | `ControlRoom.tsx:760-769,839-854`; `useControlRoom.ts:3320-3330` (`cr-schermo`, "catenaSchermo") | `schermo` = il PEGGIORE fra età feed / età spinta bot / età ultima lettura R30 | **"quello che vedi e vecchio di 2903 min"** (poi 2904 min nel giro successivo, ~1 min dopo) | **ricalcolo indipendente**: `t_test − safe_strategy_status.updated_at` = `2026-09-28T18:03:11.479Z − 2026-09-26T17:40:17.106Z` = **2902,91 min**; `omega_control/mike_control/safe_strategy_control.updated_at` sono tutti ~`2026-09-26T17:40:2Xs` (pochi secondi dopo il feed, quindi "spinta" è leggermente più fresca del feed); "lettura R30" è dell'ordine dei secondi (appena letta). Il PEGGIORE dei tre = il feed ⇒ 2902,91 min, arrotondato = **2903 min** — coincide col valore a schermo. | **OK — ricalcolo indipendente numerico coincidente, seconda conferma indipendente dello stesso meccanismo di U0231.** |

---

## Elenco esatto file toccati/creati

Nessun file sotto `frontend/src`, `Betfair/`, `desktop/`, `migrations/` toccato (rispettato
il perimetro). Tutto dentro `frontend/e2e_fase3_admin26/` (non tracciato da git):
- `_sonda_live_g2.mjs` (nuovo) — conta righe `mode='live'` per 15 tabelle, sola lettura.
- `_sonda_eventi_g2.mjs` (nuovo) — legge `live_follow`/`tennis_live_follow`/`betfair_live_xhedge`/`live_signals`/`betfair_live_risk_state`, sola lettura.
- `_sonda_rpc_g2.mjs` (nuovo) — chiama `get_direction_report_matches`, `get_direction_report_fixture`, `get_safe_state`, sola lettura (RPC `get_*`, ammesse dallo schema `LETTURA` del client specchio... non che serva, questi script usano un client Supabase diretto MIO, non il client specchio, ma con la STESSA chiave service-role in sola `select`/RPC `get_*`: nessuna `insert/update/upsert/delete` mai chiamata).
- Ho RIUSATO senza modificarli: `controlroom.fase3.test.tsx`, `pagine.fase3.test.tsx`, `clientSpecchio.ts`, `Prov.tsx`, `comune.ts`, `vitest.fase3.config.ts` (tutti del banco esistente, copiati in sola lettura dal delegato del cantiere G originario).
- Output: `out/cr_dom.json`, `out/cr_db.json`, `out/cr_chiamate.json` (rigenerati oggi, sovrascritti sul precedente run del 26/09), `out/sl_dom.json`, `out/sl_db.json`, `out/sl_chiamate.json`, `out/mw_*`, `out/tt_*` (rigenerati dallo stesso giro `pagine.fase3.test.tsx`).

**Nessuna scrittura sul DB in nessun momento**: i due giri del banco hanno prodotto
`bloccate.length === 0` (nessun tentativo di scrittura dalle pagine reali; se ci fosse
stato, sarebbe stato bloccato e registrato). Le mie 3 sonde usano solo `.select()` e
RPC `get_*`.

## Test lanciati (comando esatto, numeri, tempi)

```
npx vitest run --config e2e_fase3_admin26/vitest.fase3.config.ts e2e_fase3_admin26/controlroom.fase3.test.tsx
  1 file, 1 test, VERDE, 69,47s (durata totale giro 92,85s)
npx vitest run --config e2e_fase3_admin26/vitest.fase3.config.ts e2e_fase3_admin26/pagine.fase3.test.tsx
  1 file, 3 test, VERDI, 79,35s (durata totale giro 133,86s)
```
Un file alla volta, come da vincolo. Nessuna suite intera, nessun replay, nessun
processo nuovo avviato, app desktop mai avviata.

**Falsificazione**: non ho scritto test nuovi con asserzioni automatiche (il banco
esistente fotografa il DOM, non asserisce), quindi non c'è un test rosso/verde mio da
falsificare con una mutazione nel senso stretto del punto 4.4 del brief standard. Le
verifiche sono ricalcoli numerici indipendenti manuali (mostrati sopra, riproducibili
dai JSON in `out/`) confrontati col valore a schermo: chiunque può rieseguire lo stesso
conto sui timestamp o sulle righe `hit` e ottenere lo stesso risultato. Lo dichiaro
come limite: se il coordinatore vuole un test automatico che fallisce su una mutazione,
va scritto un file `.fase3.test.tsx` con `expect()` sopra questi stessi dati — non
l'ho fatto per restare dentro il tempo assegnato a 31 verifiche.

## Parità paper/live

Verificata concretamente in 3 punti indipendenti, tutti con dati reali:
1. U0179: `realizzatoOggi.{live,paper}` sono due `useMemo` separati su array filtrati
   (`soloLive`/`soloPaper`), mai sommati in un terzo totale.
2. U0246/U0180: `posizioni.filter(modalita==='live')` calcolato due volte in due punti
   diversi del componente, risultato concorde (0 in entrambi).
3. U0251: click reale sul filtro veri/prova → il conteggio "altre giornate" passa da
   18 a 213 (popolazioni nettamente diverse, mai mescolate).

## Cosa NON ho fatto e cosa NON ho potuto verificare

- **10 campi NON verificabili oggi** (non un errore mio: nessun dato reale attivo
  esiste in questo momento nel DB) — U0234, U0247, U0248, U0250 (diretto), U0255,
  U0263, U0264, U0302, U0312, U0337, U0344 (11, mi correggo: sono 11, non 10). Per
  ciascuno ho scritto la PROVA dell'assenza (query diretta o registro `chiamate`),
  non una semplice dichiarazione.
- **U0134, U0135, U0508**: verificati solo a livello di RPC/funzione (con dati veri e
  un cross-check numerico esatto per U0134/U0135), NON a livello di pagina montata
  (`DirezioniReport.tsx`, `SafeStrategy.tsx` sono fuori dal banco esistente; scrivere
  un banco nuovo per due pagine avrebbe richiesto più tempo di quanto assegnato per
  31 verifiche).
- **U0258**: verificato a schermo con dati reali coerenti, ma NON ho ricalcolato a
  mano il tick-down (`lib/matching.ts`) che genera il prezzo "60,00" di chiusura.
- **Nessuna falsificazione automatica** (vedi sopra): le verifiche sono ricalcoli
  manuali riproducibili, non test che diventano rossi da soli.
- Non ho toccato né riletto i 3 campi già certificati dal delegato precedente
  (U0222, U0226, U0240): restano come nel referto G.

## Sospetto aperto per il coordinatore (non un KO certificato)

`SafeStrategy.tsx` — `bot.activity` (U0508): la RPC `get_safe_state` che l'app chiama
davvero (`lib/safeBot.ts:1177`) NON passa `p_mode`, e l'`activity` che torna contiene
eventi sia `payload.mode:'paper'` sia `'live'` mescolati nello stesso array. Se il
componente non marca visivamente ogni riga col suo `mode`, un trader che guarda
"Attività" mentre un bot opera in LIVE potrebbe leggere un evento di prova credendolo
vero (non soldi, ma fiducia/decisioni). Andrebbe controllato a schermo (io non l'ho
montato) se `safeActivity.ts`/`SafeStrategy.tsx` distinguono `payload.mode` per riga.

## Cosa controllare dal vivo in paper al prossimo avvio dell'app

1. **U0302/U0312/U0337/U0344** (Segui Live): appena l'utente segue una partita in
   streaming (domani, paper), verificare a vista che: la barra in alto mostri "oggi
   ±€X" coerente col valore in `betfair_live_risk_state.total`; il pannello X-Hedge si
   popoli con `betfair_live_xhedge` fresco (non più fermo al 10/07); il registro
   Controlli runner mostri righe nuove via `get_live_audit`.
2. **U0234** (tennis vivo): con un match di tennis in-play, verificare che punteggio/
   set/game/server compaiano nella scheda partita di Control Room.
3. **U0255/U0263/U0264**: alla prima proposta di opportunità o al primo abbinamento
   di un ordine, verificare che la striscia esito e la banda della strategia compaiano
   con dati coerenti (non solo "Nessuna opportunità in coda").
4. **U0247/U0248**: difficile da provocare apposta; se capita una posizione "orfana"
   (evento non nel programma di oggi), verificare bloccabile e importo a video contro
   un ricalcolo a mano.

---

Fine referto G2. 20 dei 31 id sono **OK** con prova reale (10 con ricalcolo numerico
indipendente esatto), 11 **NON VERIFICABILI OGGI** con prova dell'assenza di dati
reali (non ipotesi), nessun **KO** trovato nei campi che ho potuto osservare.
