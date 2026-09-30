# APP: Storico di Mike per giorno del regolamento + «Chiudi» un clic in paper / conferma in live (30/09/2026)

Base: master `fc0428f`. Patch: `AUDIT_2026-09-30/APP_STORICO_E_CHIUDI.patch` (tutto il diff, migrazione compresa).
Niente commit; nessun file Python; nessun `npm run build`/`npm install`.

## 1. Storico di Mike: giorno del REGOLAMENTO (decisione «Si', giorno del regolamento»)

Patch pronta `AUDIT_2026-09-29/in_attesa_del_via/MIKE_P6_4.patch`. `git apply --3way` NON si applicava
pulita (`patch failed` su 3 file): causa i fine riga CRLF dei file del repo. Applicata con
`git apply --ignore-whitespace` senza alcuna modifica di contenuto: tutti i file restano CRLF coerenti.
Riletta riga per riga: fa SOLO cio' che dice `MIKE_P6_4.md`.

| File | Cosa |
|---|---|
| `frontend/src/lib/dailyHistory.ts` (~530-538) | `attributionOf('mike')` -> `'settled'`; Omega e Safe `'placed'`. Aggiornato anche il commento di docstring («TUTTI E TRE i bot» non era piu' vero) |
| `frontend/src/components/trading/TradingHistory.tsx:118` | testo del criterio `'settled'` (usato solo da Mike): «posizioni REGOLATE nel giorno... come in «Posizioni chiuse»» |
| `frontend/src/lib/dailyHistory.test.ts:420` | `attributionOf('mike')` da `'placed'` a `'settled'` |
| `frontend/src/components/trading/StoricoMikeGiornoRegolamento.test.tsx` (nuovo, 3 test) | attribuzioni per bot; posizione piazzata ieri 23:30 e regolata oggi conta oggi; la pagina dice il criterio |
| `migrations/mike_storico_giorno_regolamento_2026-09-29.sql` (nuovo) | `get_mike_daily` e `get_mike_day_trades` rifatte con `'settled'` al posto di `'placed'` |

Migrazione, controllo di persona: confrontata col corpo vivo (`mike_storico_per_modalita_2026-09-14.sql` +
`..._fix_alias_2026-09-14.sql`): unica differenza `'placed'` -> `'settled'` nelle due chiamate al motore comune
(alias `t` per il calendario, `o` per il dettaglio, come nel fix del 14/09). Stesse firme e permessi, `CREATE OR REPLACE`
(idempotente), nessun dato toccato, commentata. Ho aggiunto in coda il blocco «Verifica (sola lettura)» come in
`mike_reentry_max_goals_2026-09-29.sql` (le query c'erano gia' in testa). NON eseguita.
Nota di precisione: a differenza di `mike_reentry_max_goals` NON e' «solo dati»: ridefinisce due funzioni (nessun dato).
**Ordine**: migrazione e patch dell'app insieme (altrimenti calendario e dettaglio non tornano a cavallo della mezzanotte).
Restano per PIAZZAMENTO «P&L oggi», barra della giornata e scheda Operazioni di Mike (tabella in `MIKE_P6_4.md` §3-ter):
non toccati, come da referto originale.

## 2. «Chiudi» in Control Room: un clic in paper, conferma in live

Flusso di oggi: il «Chiudi» di ogni riga e' `BottoneChiudiRiga` (un clic, in qualsiasi modalita', poi `api.chiudi(riga)`),
montato da `DettaglioRigaView.tsx` (righe) e `pages/ControlRoom.tsx` (posizioni orfane). Meccanismo di conferma gia'
esistente riusato come gesto: `CashOutPartita.tsx` (primo clic arma, secondo manda, «annulla», fail-closed se modalita'
non dichiarata). Non ne ho creato uno nuovo: stesso schema, applicato al bottone di riga.

| File | Cosa |
|---|---|
| `frontend/src/components/controlroom/BottoneChiudiRiga.tsx` | costante `BOT_CON_CONFERMA_LIVE = {'mike'}`; `chiedeConferma = bot in set && modalita !== 'paper'` (fail-closed). Paper: il clic chiama subito `manda()`. Live: il clic arma e compare «Conferma» + frase «Live, soldi veri: confermi la chiusura? Stima chiudendo ora +x €» + «annulla»; solo «Conferma» chiama `manda()`. `manda()` fa esattamente cio' che faceva il vecchio onClick (stessa `api.chiudi(riga con prezzoVisto/contestoVisto)`): la richiesta e' identica. Il prezzo al clic viene preso al momento della conferma (quando parte davvero). Nuova prop opzionale `stimaOra`, usata solo nel testo, mai nel payload |
| `DettaglioRigaView.tsx` (+1 riga), `pages/ControlRoom.tsx` (+1 riga) | passano `stimaOra = ch.bloccabile` (P&L bloccabile chiudendo ora, gia' mostrato nella scheda) |
| `BottoneChiudiMikeConferma.test.tsx` (nuovo, 6 test, incluso `modalita` null) | paper = 1 clic; live: 1 clic non manda e mostra confermare+stima; conferma manda la stessa richiesta una sola volta; annulla non manda; Omega live resta a un clic |

**Decisione di perimetro da confermare**: l'ordine parla di Mike, quindi la conferma live vale SOLO per `mike`. Il difetto D5
del piano dice che in live il «Chiudi» chiude a un clic per tutti i bot: estenderlo a Omega/Safe/tennis e' cambiare una parola
(l'insieme `BOT_CON_CONFERMA_LIVE`), ma rompe i test di Omega/tennis in live e non l'ho fatto senza via.
Se armato e la riga diventa non chiudibile/occupata, la conferma sparisce e torna il bottone spento col motivo.

## 3. Verifiche
- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori** (rieseguito a fine lavoro).
- `npx vitest run src/components/mike src/components/controlroom src/lib/mike src/lib/interruttori src/pages` + `src/components/trading src/lib/dailyHistory`
  (le ultime due per i test della patch dello Storico; `src/lib/mike` e `src/lib/interruttori` non esistono come cartelle): **106 file, 1690 verdi, 1 saltato (preesistente)**.
  Nella prima corsa 2 test di `src/pages/SafeStrategy.test.tsx` (`invest-place`, timeout 1 s sotto carico: la suite girava in 464 s) sono
  andati in timeout; rieseguito da solo il file: 28/28 verdi, ne' toccato ne' correlato. E' un flake da carico, non un mio effetto.

## 4. Falsificazione (mutazioni eseguite e ripristinate, verificato che i file tornassero identici)
1. `chiedeConferma = false` (live senza conferma): `BottoneChiudiMikeConferma` **3 rossi su 5** (live arma, conferma, annulla).
2. `chiedeConferma = true` (conferma anche in paper e per Omega): **2 rossi su 5** (paper un clic, Omega un clic).
3. `attributionOf('mike')` di nuovo `'placed'`: **4 rossi** fra `StoricoMikeGiornoRegolamento` e `dailyHistory.test`.
4. (rilievo del coordinatore) Nuovo test 6/6 «modalita' IGNOTA (null): bottone spento, nessuna richiesta, nessuna conferma armata»
   (`BottoneChiudiMikeConferma.test.tsx`). Mutazione `modalita !== 'paper'` -> `modalita === 'live'` nel solo bottone: test
   VERDE, e resta verde per costruzione: `chiudibile()` (`chiudiRiga.ts:104`) rifiuta gia' `modalita` null e il bottone e' spento.
   Il test fissa quel comportamento a monte: mutando `chiudibile` (tolto il controllo della modalita'): **ROSSO** (bottone acceso);
   mutando entrambi (chiudibile senza controllo + `=== 'live'`): **ROSSO** (la richiesta partirebbe senza conferma). Il
   `!== 'paper'` del bottone e' quindi la seconda linea di difesa, raggiungibile solo se `chiudibile` cede: coperta dalla mutazione doppia.
Script di mutazione temporaneo cancellato; nessun `.orig` rimasto. Perimetro della conferma: resta solo Mike.

## COSA NON HO POTUTO VERIFICARE
- La migrazione non e' stata eseguita (ordine): verificata solo per confronto testuale col corpo vivo dei file di migrazione; non so se il DB vivo ha corpi diversi da quelli nei file (`get_mike_daily`/`get_mike_day_trades`).
- Nessuna prova nell'app desktop reale (niente build, niente avvio): il comportamento e' provato con test di componente e tsc.
- La conferma live e' verificata sul bottone isolato e sui test esistenti della Control Room (verdi); non ho un test end-to-end della pagina `ControlRoom` con riga Mike live che passi per i due clic.
- «Stima chiudendo ora» mostra `ch.bloccabile` solo se la scheda ha gia' il prezzo; senza, la frase non ha importo (dichiarato, non inventato).
- Se «Chiudi» in altri punti (es. proposta `PropostaUscitaMike`, «approva») debba avere lo stesso gesto: non toccato, fuori perimetro.
- `git apply --3way` come chiesto non e' riuscito (CRLF): usato `--ignore-whitespace`; il risultato e' lo stesso contenuto della patch.
