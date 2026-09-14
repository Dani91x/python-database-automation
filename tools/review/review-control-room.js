export const meta = {
  name: 'review-control-room',
  description: 'Review a 12 dimensioni della Control Room con verifica avversariale di ogni reperto',
  phases: [
    { title: 'Ricerca', detail: 'un agente per dimensione, ciascuno su file e domande sue' },
    { title: 'Verifica', detail: 'tre scettici con lenti diverse per ogni reperto' },
    { title: 'Sintesi', detail: 'critico di completezza: cosa non e stato guardato' },
  ],
}

const RADICE = 'C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation'

const CONTESTO = `
CONTESTO — leggi prima di cercare.

Repo: ${RADICE}
Questa e la CONTROL ROOM di una piattaforma di trading Betfair che opera con
SOLDI VERI. Oggi ha validato un bot in live (5 operazioni, +0,44 EUR reali).
L'utente: "OGNI COSA DEVE FUNZIONARE ALLA PERFEZIONE, IL TRADER DEVE AVERE
TUTTO SOTTO CONTROLLO E TUTTO QUELLO CHE VEDE DEVE ESSERE STATO CONTROLLATO E
CERTIFICATO PER GARANTIRNE L'ATTENDIBILITA".

LE REGOLE DEL PROGETTO, che sono anche i criteri di questa review:

1. PAPER E LIVE NON SI SOMMANO MAI. Soldi veri e simulati in un numero solo
   sono una bugia. Oggi ne sono stati trovati QUATTRO casi. Cercane altri.
2. ASSENTE non e ZERO. Un valore che non conosciamo si scrive "—", mai
   "0,00 EUR" e mai "0 ms". "Istantaneo" e "non lo so" sono affermazioni
   diverse.
3. FAIL-CLOSED. Nel dubbio si sceglie la strada che NON mette a rischio
   denaro: una modalita non dichiarata vale paper, un'eta ignota non e
   "fresca", un bot muto non e un bot sano.
4. DESIGN SYSTEM: i soldi passano da fmtMoney, le quote da fmtOdds, le eta da
   fmtAge. Mai toFixed a mano, mai stringhe con l'euro costruite a mano.
   Testi in ITALIANO, mai stati in inglese sotto gli occhi del trader.
5. UN PULSANTE SPENTO DICE PERCHE. Mai un disabled muto.
6. LE STRATEGIE NON SI TOCCANO. Segnalare una modifica alla logica di
   strategia e un errore, non un reperto.

COME LAVORARE:
- Leggi il codice VERO con Read/Grep. Non dedurre dai nomi.
- Prima di dichiarare che qualcosa non funziona, CERCA NEL REPO se qualcun
  altro lo fa gia funzionare: e una regola di questo progetto, nata da un
  errore vero.
- Un reperto senza uno scenario di fallimento concreto (input -> output
  sbagliato) non e un reperto: e un'opinione. Scartalo tu prima di scriverlo.
- NON proporre refactor estetici, rinomine, o "si potrebbe migliorare".
  Cerchiamo cose ROTTE o BUGIARDE.
`

const SCHEMA_REPERTI = {
  type: 'object',
  properties: {
    reperti: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          titolo: { type: 'string' },
          file: { type: 'string' },
          riga: { type: 'number' },
          gravita: { type: 'string', enum: ['critico', 'alto', 'medio', 'basso'] },
          descrizione: { type: 'string' },
          scenario: { type: 'string' },
          prova: { type: 'string' },
        },
        required: ['titolo', 'file', 'gravita', 'descrizione', 'scenario'],
      },
    },
    guardato: { type: 'string' },
  },
  required: ['reperti', 'guardato'],
}

const SCHEMA_VERDETTO = {
  type: 'object',
  properties: {
    confutato: { type: 'boolean' },
    perche: { type: 'string' },
    correzione: { type: 'string' },
  },
  required: ['confutato', 'perche'],
}

const DIMENSIONI = [
  {
    chiave: 'numeri-misti',
    prompt: `DIMENSIONE 1 — PAPER E LIVE MISCHIATI (la piu importante).

Oggi sono stati corretti quattro punti dove soldi veri e simulati venivano
sommati. Il tuo compito: trovarne ALTRI, o dimostrare che non ce ne sono.

File: frontend/src/lib/controlRoom.ts, frontend/src/components/controlroom/useControlRoom.ts,
frontend/src/pages/ControlRoom.tsx, frontend/src/lib/dailyHistory.ts,
frontend/src/components/controlroom/SplitSport.tsx, SchedaPartita.tsx

Cerca OGNI punto dove un numero mostrato al trader potrebbe contenere
righe di modalita diverse: P&L, esposizione/liability, contatori di
operazioni, vinte/perse, win rate, target, avanzamento, totali di colonna,
aggregati dei tre servizi, e la lista posizioni.
Controlla anche il percorso inverso: un numero LIVE che per sbaglio esclude
righe live (altrettanto grave: nasconde rischio reale).
Verifica che modoDi() sia usato ovunque serva e che non ci siano confronti
con 'live' scritti a mano che sbaglierebbero su 'LIVE' o ' live '.`,
  },
  {
    chiave: 'assente-non-zero',
    prompt: `DIMENSIONE 2 — ASSENTE SCAMBIATO PER ZERO.

File: frontend/src/lib/controlRoom.ts, controlRoomCatena.ts, controlRoomProposte.ts,
posizioniChiuse.ts, e tutti i componenti in frontend/src/components/controlroom/

Cerca ogni punto dove un valore mancante puo diventare 0, 0,00 EUR, 0 ms,
0%, "fresco", o far sembrare misurato qualcosa che non lo e. Guarda in
particolare: ?? 0, || 0, Number(x) su undefined, somme che partono da 0 e
restano 0 quando non c'e nessun addendo, e percentuali calcolate su
denominatori vuoti.
Guarda anche il contrario: uno ZERO VERO che viene mostrato come "—"
(perdere l'informazione "pareggio" o "istantaneo" e un difetto simmetrico).`,
  },
  {
    chiave: 'comandi-bot',
    prompt: `DIMENSIONE 3 — I COMANDI CHE ACCENDONO UN BOT SU SOLDI VERI.

File: frontend/src/components/controlroom/comandiBot.ts, PannelloBot.tsx,
e le funzioni che chiama in frontend/src/lib/omega.ts, safeBot.ts, mike.ts.
Controlla anche le RPC in ${RADICE}/migrations/*.sql (omega_activate,
safe_activate, mike_activate, *_update_params, *_stop).

Domande:
- cambiaImporto riparte dai parametri correnti: puo perdere chiavi? Cosa
  succede se i parametri correnti sono parziali o non ancora caricati?
- scriviChiave: casi limite (chiave vuota, chiave con punto finale,
  prototype pollution con __proto__ o constructor).
- cambiaModalita su Safe chiama activateSafe: activateSafe con params
  undefined AZZERA i parametri sul DB? Leggi la RPC safe_activate.
- avvia/ferma: doppie chiamate, stato incoerente, race se il trader clicca
  due volte.
- la doppia conferma per il live: si puo aggirare? Lo stato armato si
  azzera quando deve?`,
  },
  {
    chiave: 'catena-tempi',
    prompt: `DIMENSIONE 4 — LA CATENA DEI TEMPI E LA LATENZA.

File: frontend/src/lib/controlRoomCatena.ts e il suo test,
${RADICE}/Betfair/safe_strategy/bot_service.py (funzione _catena_dei_tempi,
intorno a riga 2793) e execution.py (funzione scorrimento, riga ~201).

Oggi e stato corretto un difetto: t3 registrava l'inizio del ciclo invece
dell'istante della decisione, quindi il salto "bot -> decisione" risultava
negativo e la pagina lo mostrava come "—".
Verifica che la correzione sia completa e cerca altri istanti mal presi:
t0/t1/t2/t4/t5/t6, il segno dello scorrimento in tick, la differenza fra
betfair_ms dichiarato e sottratto, e i totali che sommano salti non
misurati.`,
  },
  {
    chiave: 'corsia-preferenziale',
    prompt: `DIMENSIONE 5 — LA CORSIA PREFERENZIALE DELLE CHIUSURE (backend Python).

File: ${RADICE}/Betfair/safe_strategy/bot_service.py — le funzioni
process_requests (con il parametro solo_chiusure), run_once (la chiamata
"a-0" in testa al ciclo e quella al punto "c"), _attesa_interrompibile e
main().

Questa modifica esegue ordini REALI. Domande:
- una richiesta puo essere eseguita DUE VOLTE (una nella passata veloce e
  una in quella completa)?
- una richiesta di tipo place puo restare appesa per sempre?
- _attesa_interrompibile: puo entrare in un ciclo stretto che martella il
  database? Il guardiano _SVEGLIA_FATTA funziona anche con piu richieste in
  coda o solo con una?
- lo stato _APERTE viene aggiornato anche quando il ciclo esce presto o
  fallisce?
- process_requests con solo_chiusure salta fail_stale_processing: una
  richiesta bloccata in 'processing' resta bloccata piu a lungo?
NON proporre modifiche alla strategia. Solo alla meccanica di esecuzione.`,
  },
  {
    chiave: 'proposte-chiusura',
    prompt: `DIMENSIONE 6 — LE PROPOSTE DI CHIUSURA (il trader ci clicca sopra e parte un ordine vero).

File: frontend/src/lib/controlRoomProposte.ts, controlRoomProposte.test.ts,
frontend/src/components/controlroom/SchedaChiusura.tsx.

Domande:
- prezzoVivo: prende davvero il prezzo dal FEED e non quello congelato
  nella proposta? Cosa succede se il feed non ha quella selezione?
- scostamento: il segno e giusto per BACK e per LAY? Su un lay un prezzo
  che sale COSTA: il calcolo lo riflette?
- motivoNonApprovabile: copre tutti i casi in cui approvare sarebbe
  sbagliato? Esiste un percorso in cui il bottone e attivo ma non dovrebbe?
- il calcolo di quanto si blocca: usa la matematica condivisa di
  CashOutButton o ne ha una sua (che sarebbe una seconda verita)?
- l'importo abbinabile mostrato: e quello vero del book o un'altra cosa?`,
  },
  {
    chiave: 'posizioni-chiuse',
    prompt: `DIMENSIONE 7 — POSIZIONI CHIUSE E P&L GLOBALE.

File: frontend/src/lib/posizioniChiuse.ts e il suo test.
Confronta con la logica gia esistente che fa la stessa cosa altrove:
frontend/src/lib/eventGroups.ts, frontend/src/lib/omegaMatches.ts.

Domande:
- una posizione con PIU coperture parziali (place-and-trim) viene sommata
  bene?
- una copertura che punta a un trade inesistente (closes_trade_id orfano):
  che fine fa il suo P&L? Sparisce silenziosamente?
- una catena di chiusure (A chiuso da B, B chiuso da C) viene gestita?
- il P&L globale include le righe VOID?
- questa libreria duplica una logica che eventGroups gia fa meglio? Se si,
  dillo: due verita sullo stesso numero sono un difetto.`,
  },
  {
    chiave: 'ritorno-navigazione',
    prompt: `DIMENSIONE 8 — RITORNO AL PUNTO ESATTO E NAVIGAZIONE.

File: frontend/src/lib/ritorno.ts + test, frontend/src/components/controlroom/AzioniPartita.tsx.
Guarda anche chi legge il parametro "from": frontend/src/pages/Dashboard.tsx,
frontend/src/pages/SeguiLive.tsx.

Domande:
- AzioniPartita salva un punto di ritorno e naviga verso /dashboard e
  /segui-live e /tennis/terminal: quelle pagine hanno un pulsante per
  tornare alla Control Room? Se NO, il ritorno promesso non esiste ed e un
  reperto CRITICO rispetto alla richiesta esplicita dell'utente.
- portaInVista usa CSS.escape: e disponibile nell'ambiente di test e nei
  browser target?
- il punto di ritorno viene mai cancellato dopo l'uso? Se no, un secondo
  ritorno riporta in un posto sbagliato.
- sessionStorage: chiavi in conflitto con altre parti del software?`,
  },
  {
    chiave: 'registrazione-sport',
    prompt: `DIMENSIONE 9 — "SEGUI LIVE": LA REGISTRAZIONE FUNZIONA DAVVERO?

File: frontend/src/components/controlroom/AzioniPartita.tsx,
frontend/src/lib/omegaMissions.ts, frontend/src/lib/tennis.ts.
Backend: ${RADICE}/Betfair/stream/runner.py,
${RADICE}/Betfair/stream/tennis_live/tennis_recorder.py,
${RADICE}/migrations/live_follow_record.sql, tennis_follow_record.sql, tennis_live.sql.

E stato affermato che il calcio registra via live_follow + set_follow_record
e il tennis via tennis_live_follow + tennis_set_follow_record, e che
confonderli accenderebbe una spia verde senza registrare niente.
VERIFICA CHE SIA VERO leggendo il codice del registratore, e poi verifica
che AzioniPartita usi davvero il percorso giusto per ciascuno sport.
Controlla anche: cosa succede se si attiva la registrazione su una partita
di tennis senza market_id? E su una di calcio senza orario di inizio?
E se il runner corrispondente e SPENTO — il trader vede REC e non registra
niente?`,
  },
  {
    chiave: 'design-system',
    prompt: `DIMENSIONE 10 — DESIGN SYSTEM E LINGUA.

File: tutti i frontend/src/components/controlroom/*.tsx e
frontend/src/pages/ControlRoom.tsx.
Regole: frontend/src/components/trading/designGuard.test.ts (e la guardia
meccanica: leggila per sapere cosa controlla gia, e cerca cio che NON copre).

Cerca:
- denaro/quote/eta formattati a mano invece che con fmtMoney/fmtOdds/fmtAge;
- stati o etichette in inglese sotto gli occhi del trader;
- pulsanti disabled senza una ragione scritta o senza title;
- colori che cambiano significato fra un componente e l'altro (es. rosso
  che a volte vuol dire "live" e a volte "perdita");
- testo che puo traboccare o essere tagliato su nomi lunghi di partite;
- contrasto e leggibilita di testi a opacita molto bassa (text-white/25 e
  simili) su dati che il trader deve leggere davvero.`,
  },
  {
    chiave: 'test-veri',
    prompt: `DIMENSIONE 11 — I TEST PASSANO DAVVERO O PASSANO A VUOTO?

File: tutti i *.test.ts e *.test.tsx toccati oggi:
frontend/src/lib/controlRoom.test.ts, controlRoomCatena.test.ts,
controlRoomProposte.test.ts, posizioniChiuse.test.ts, ritorno.test.ts,
frontend/src/pages/ControlRoom.test.tsx,
frontend/src/components/controlroom/comandiBot.test.ts,
${RADICE}/Betfair/safe_strategy/tests/test_bot_service.py.

Cerca FALSI VERDI:
- asserzioni che passerebbero anche se il codice fosse rotto (es.
  not.toContain su una stringa che non comparirebbe comunque, senza una
  asserzione positiva che dimostri il contrario);
- test che non montano il componente o non chiamano la funzione;
- mock cosi permissivi da non provare niente;
- expect dentro callback che potrebbero non essere mai eseguite;
- casi strutturalmente impossibili spacciati per casi limite;
- copertura mancante sui percorsi che toccano SOLDI VERI.
Per ogni falso verde indica l'asserzione esatta e perche non discrimina.`,
  },
  {
    chiave: 'realtime-freschezza',
    prompt: `DIMENSIONE 12 — IL DATO E DAVVERO IN TEMPO REALE?

File: frontend/src/components/controlroom/useControlRoom.ts (RICARICA_MS,
le sottoscrizioni realtime, i canali locali), frontend/src/lib/localChannel.ts,
frontend/src/lib/controlRoom.ts (freschezza, statoQuote, etaSecondi).

L'utente ha detto: "LA NOSTRA UI DEVE ESSERE AL PARI DELLA VISUALE DI
BETFAIR, GLI AGGIORNAMENTI DEVONO ESSERE IN TEMPO REALE".

Domande:
- cosa si aggiorna in realtime e cosa solo ogni RICARICA_MS? Il trader puo
  distinguere i due casi guardando lo schermo?
- un prezzo mostrato accanto a un pulsante che manda un ordine: quanto puo
  essere vecchio nel caso peggiore?
- le sottoscrizioni realtime vengono smontate correttamente (perdite di
  memoria, doppie sottoscrizioni al rimontaggio)?
- se una fonte cade, la pagina continua a mostrare l'ultimo dato: lo
  DICHIARA in modo che il trader non lo scambi per attuale?
- la pagina mostra l'eta di cio che vede, e quell'eta e calcolata sul
  peggiore dei canali o sul migliore?`,
  },
]

phase('Ricerca')
log(`12 dimensioni, ciascuna con file e domande sue. Ogni reperto passera da 3 scettici.`)

const LENTI = [
  'CORRETTEZZA: il codice fa davvero quello che il reperto dice? Leggi le righe citate.',
  'RIPRODUCIBILITA: lo scenario di fallimento descritto e raggiungibile con dati reali? Se richiede uno stato impossibile, e confutato.',
  'GIA-RISOLTO: cerca nel repo se questo caso e gia gestito altrove (un guardiano, un default, un test). Se lo e, il reperto e confutato.',
]

const risultati = await pipeline(
  DIMENSIONI,
  (d) => agent(`${CONTESTO}\n\n${d.prompt}`, {
    label: `cerca:${d.chiave}`, phase: 'Ricerca', schema: SCHEMA_REPERTI,
  }),
  (trovato, d) => {
    if (!trovato || !trovato.reperti || trovato.reperti.length === 0) return []
    return parallel(trovato.reperti.map((r) => () =>
      parallel(LENTI.map((lente, i) => () =>
        agent(
          `${CONTESTO}\n\nSEI UNO SCETTICO. Il tuo compito e CONFUTARE questo reperto, non confermarlo.\n\n` +
          `REPERTO: ${r.titolo}\nFile: ${r.file}${r.riga ? `:${r.riga}` : ''}\n` +
          `Gravita dichiarata: ${r.gravita}\n` +
          `Descrizione: ${r.descrizione}\n` +
          `Scenario di fallimento: ${r.scenario}\n` +
          `Prova addotta: ${r.prova || '(nessuna)'}\n\n` +
          `LA TUA LENTE: ${lente}\n\n` +
          `Leggi il codice VERO. Nel dubbio confuta (confutato=true): un reperto ` +
          `falso fa perdere tempo e fiducia piu di uno mancato. Se invece regge, ` +
          `confutato=false e scrivi in "correzione" la correzione minima e concreta.`,
          { label: `verifica:${d.chiave}#${i}`, phase: 'Verifica', schema: SCHEMA_VERDETTO },
        ),
      )).then((voti) => {
        const validi = voti.filter(Boolean)
        const reggono = validi.filter((v) => !v.confutato)
        return {
          ...r,
          dimensione: d.chiave,
          voti: validi.length,
          aFavore: reggono.length,
          confermato: validi.length > 0 && reggono.length >= 2,
          correzione: reggono.map((v) => v.correzione).filter(Boolean)[0] || '',
          confutazioni: validi.filter((v) => v.confutato).map((v) => v.perche),
        }
      }),
    ))
  },
)

const tutti = risultati.flat().filter(Boolean)
const confermati = tutti.filter((r) => r.confermato)
const scartati = tutti.filter((r) => !r.confermato)

log(`${tutti.length} reperti grezzi -> ${confermati.length} confermati da almeno 2 scettici su 3, ${scartati.length} confutati.`)

phase('Sintesi')
const critico = await agent(
  `${CONTESTO}\n\nSEI IL CRITICO DI COMPLETEZZA.\n\n` +
  `Una review a 12 dimensioni ha appena esaminato la Control Room. ` +
  `Dimensioni coperte: ${DIMENSIONI.map((d) => d.chiave).join(', ')}.\n\n` +
  `Reperti CONFERMATI (${confermati.length}):\n` +
  confermati.map((r) => `- [${r.gravita}] ${r.titolo} (${r.file}) — ${r.descrizione}`).join('\n') +
  `\n\nLa tua domanda e una sola: CHE COSA NON E STATO GUARDATO?\n` +
  `Pensa a: file della Control Room che nessuna dimensione nomina; percorsi ` +
  `che toccano soldi veri e non sono stati letti; migrazioni SQL non verificate; ` +
  `stati dell'interfaccia che nessuno ha provato (caricamento, errore, vuoto, ` +
  `fonte caduta); interazioni fra i pezzi (es. un filtro attivo mentre arriva ` +
  `una proposta); e casi che un trader incontrerebbe e uno sviluppatore no.\n\n` +
  `Elenca SOLO buchi concreti e verificabili, con il file o la domanda precisa ` +
  `da porre. Niente consigli generici.`,
  { label: 'critico:completezza', phase: 'Sintesi' },
)

return {
  totaleGrezzi: tutti.length,
  confermati: confermati.sort((a, b) => {
    const ordine = { critico: 0, alto: 1, medio: 2, basso: 3 }
    return (ordine[a.gravita] ?? 9) - (ordine[b.gravita] ?? 9)
  }),
  confutati: scartati.map((r) => ({
    titolo: r.titolo, file: r.file, dimensione: r.dimensione,
    perche: r.confutazioni[0] || 'confutato',
  })),
  nonGuardato: critico,
}
