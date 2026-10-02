# Sistema - Capitolo 7: la porta degli ordini, le strade verso Betfair (schede)

Schema: `07_porta_degli_ordini.html` (sorgente `07_porta_degli_ordini.architecture.json`).
Fonte dei fatti: `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md`, sezione F.

Schede dell'inventario usate: F-1 ... F-16, C-3, C-17, D-2.

Come si legge: a sinistra chi vuole piazzare un ordine calcio; al centro le tre strade (filo,
coda, domanda diretta); a destra chi lo porta a Betfair. Le frecce tratteggiate sono i ripieghi.
L'elenco ufficiale delle strade e' controllato da un test del repo (`F-1`).

---

## App desktop

**Cosa fa**
- Ordini a mano dalla scala prezzi e dai pannelli di trading.

**Quando**
- Al clic.

**Numeri**
- Strada: filo 47331 con la chiave; se il filo e' giu' o manca la chiave, coda nel database.

**Esempio con le cifre**
- Punti 2,00 EUR a 3,50 dalla scala: l'ordine va sul filo e il runner lo piazza subito.

**Cosa vedi nell'app**
- L'ordine in coda e poi abbinato.

**Se qualcosa va storto**
- Coda nel database: il runner lo prende entro 1 s.

**Per il tecnico**
- F-10 `frontend/src/lib/localTransport.ts:441`, `frontend/src/lib/liveOrders.ts:133`.

## Safe e Omega

**Cosa fa**
- I due bot calcio che usano la stessa porta degli ordini.

**Quando**
- Quando la strategia decide di entrare o uscire.

**Numeri**
- Ordine di scelta: 1) filo 47331; 2) coda nel database; 3) in prova senza runner: rifiuto;
  4) in vero, se anche la coda fallisce: domanda diretta.

**Esempio con le cifre**
- Safe vuole bancare 5,00 EUR a 1,30: prova il filo; se il runner non risponde, mette l'ordine in
  coda; se e' un ordine vero e la coda non e' possibile, lo chiede direttamente a Betfair.

**Cosa vedi nell'app**
- L'operazione nella pagina del bot.

**Se qualcosa va storto**
- In prova senza runner: «paper senza runner», l'ordine non parte e si riprova al giro dopo.

**Per il tecnico**
- F-6 `Betfair/safe_strategy/execution.py:871`, `Betfair/safe_strategy/execution.py:1003`,
  `Betfair/safe_strategy/execution.py:1070`, `Betfair/safe_strategy/execution.py:1095`; F-7
  `Betfair/omega/omega_service.py:2707`, `Betfair/omega/omega_service.py:2751`.

## Mike in prova

**Cosa fa**
- Mike in modo prova (paper) manda gli ordini al runner sul filo.

**Quando**
- Quando la strategia decide.

**Numeri**
- Sempre e solo il filo 47331.

**Esempio con le cifre**
- Mike in prova punta 2,00 EUR sull'Under 3,5: il runner simula l'abbinamento.

**Cosa vedi nell'app**
- Pagina di Mike, modo prova.

**Se qualcosa va storto**
- Runner giu': ordine rifiutato («senza runner»).

**Per il tecnico**
- F-8 `Betfair/mike/porta_ordini.py:9`.

## Mike vero

**Cosa fa**
- Mike con soldi veri (LIVE) chiede direttamente a Betfair, senza passare dal runner.

**Quando**
- Quando la strategia decide; solo se il suo interruttore del vero e' acceso.

**Numeri**
- Sempre domanda diretta.

**Esempio con le cifre**
- Il 02/10 il registro di Mike segnala partite vive in modo diverso da «prova» e 12 saldi riletti
  dopo un ordine.

**Cosa vedi nell'app**
- Pagina di Mike, modo vero.

**Se qualcosa va storto**
- Ripete una volta dopo un nuovo accesso.

**Per il tecnico**
- F-8 `Betfair/mike/porta_ordini.py:11`, `Betfair/mike/service.py:152`, `Betfair/mike/service.py:2208`.

## Filo ordini 47331

**Cosa fa**
- Porta l'ordine al runner calcio senza passare dal database.

**Quando**
- Subito: ogni ordine sveglia il motore degli ordini del runner.

**Numeri**
- Accetta ordini solo con la chiave (app) o col nome del bot (safe, omega, mike).

**Esempio con le cifre**
- Il registro del 02/10 di Omega: «ordini via canale di comando ws://.../comando/omega».

**Cosa vedi nell'app**
- Niente di diretto.

**Se qualcosa va storto**
- Chi manda l'ordine passa alla coda.

**Per il tecnico**
- F-4 `Betfair/stream/motore_ordini.py:801`; C-17.

## Coda nel database

**Cosa fa**
- Tiene l'ordine finche' il runner lo prende.

**Quando**
- Riletta dal runner circa ogni secondo.

**Numeri**
- 189 letture al minuto (capitolo 5a).

**Esempio con le cifre**
- Ordine scritto alle 18:00:00.2, preso alle 18:00:01.0.

**Cosa vedi nell'app**
- Ordine «in attesa».

**Se qualcosa va storto**
- Una richiesta rimasta a meta' viene chiusa alla ripartenza del runner.

**Per il tecnico**
- F-5 `Betfair/stream/live_order_worker.py:61`; D-2.

## Domanda diretta

**Cosa fa**
- Il bot stesso chiede a Betfair di piazzare l'ordine (senza runner).

**Quando**
- Mike vero sempre; Safe e Omega veri solo se filo e coda falliscono.

**Numeri**
- Controllo del minimo di 1,00 EUR per lato; sotto il minimo, riduzione fino a 0,50 EUR o rifiuto.

**Esempio con le cifre**
- Mike banca 1,50 EUR: sopra il minimo, parte diretto.

**Cosa vedi nell'app**
- Pagina del bot.

**Se qualcosa va storto**
- Una ripetizione dopo un nuovo accesso.

**Per il tecnico**
- F-9 `Betfair/omega/omega_market.py:696`, `Betfair/omega/omega_market.py:1018`; F-13
  `Betfair/omega/omega_market.py:731`.

## Runner calcio

**Cosa fa**
- Punto comune: controlla l'ordine (modo prova o vero, freno, minimi) e lo piazza con la libreria
  flumine; in prova lo simula.

**Quando**
- Subito dal filo; entro 1 s dalla coda.

**Numeri**
- Minimo 1,00 EUR per lato al centesimo; pavimento di legge 0,50 EUR.

**Esempio con le cifre**
- Ordine da 0,80 EUR: sotto il minimo; si parcheggia a 1,00 e si riduce a 0,80 (finale sopra 0,50);
  sotto 0,50 EUR nessun ordine.

**Cosa vedi nell'app**
- Ordini nella pagina di trading.

**Se qualcosa va storto**
- Un ordine sotto 0,50 EUR viene rifiutato con «sotto il minimo, non piazzabile».

**Per il tecnico**
- F-2 `Betfair/stream/live_order_worker.py:3673`, `Betfair/stream/live_order_worker.py:1273`; F-3;
  F-4 `Betfair/stream/motore_ordini.py:1071`; F-12, F-14.

## Ordini a mano vecchi

**Cosa fa**
- Vecchia strada degli ordini a mano (porta 8787 e coda propria nel database).

**Quando**
- Solo se qualcuno lancia a mano `start_order_server.py`. L'app NON lo accende.

**Numeri**
- Controllo del minimo 1,00 EUR.

**Esempio con le cifre**
- Pannello «multi trade» della watchlist: usa questa coda.

**Cosa vedi nell'app**
- Pannello multi trade.

**Se qualcosa va storto**
- Se il server non e' acceso, l'ordine resta in coda senza esecutore.

**Per il tecnico**
- F-11 `Betfair/order_exec.py:207`, `Betfair/order_worker.py:29`, `start_order_server.py:24`;
  `frontend/src/lib/betfair.ts:159`.

## Betfair

**Cosa fa**
- Riceve gli ordini veri.

**Quando**
- Dal runner (ordini veri del filo e della coda), dalla domanda diretta, dai vecchi ordini a mano.

**Numeri**
- Gli ordini in prova non arrivano mai a Betfair: li simula il runner.

**Esempio con le cifre**
- Il 02/10 alle 16:25 il registro del runner calcio dice: «tetto LIVE, effettivo PAPER»: il `.env`
  permette il vero, ma l'app ha scelto la prova; quindi gli ordini calcio passati dal runner erano
  simulati. Mike vero, che va diretto, non dipende da questa scelta.

**Cosa vedi nell'app**
- Ordini abbinati.

**Se qualcosa va storto**
- Rifiuto di Betfair: l'esito torna al bot.

**Per il tecnico**
- F-2, F-9, F-11.

## Frecce

- App -> filo: con la chiave.
- Safe e Omega -> filo: prima scelta.
- Mike in prova -> filo: solo in prova.
- Filo -> coda: se il filo e' giu' (tratteggiata).
- Coda -> domanda diretta: se anche la coda fallisce, solo con soldi veri (tratteggiata).
- Mike vero -> domanda diretta: sempre.
- Filo -> runner: subito.
- Coda -> runner: riletta ogni 1 s.
- Runner -> Betfair: ordine vero o simulato.
- Domanda diretta -> Betfair: soldi veri.
- Ordini a mano vecchi -> Betfair: solo se lanciati a mano (tratteggiata).

## Punti da decidere

1. Quattro strade per gli ordini calcio. Mike vero e' l'unico bot che va sempre diretto.
2. La «traduzione» di un ordine sotto il minimo sull'altra selezione e' spenta per tutti i bot
   (insieme vuoto): restano riduzione o rifiuto.
3. Scalper e sniper calcio usano un minimo proprio di 2,00 EUR, diverso dall'1,00 delle altre strade.

## Punti non chiariti

1. Bot tennis e sessioni scalper piazzano nel loro processo (non disegnati qui): vedi F-15.
2. Non verificato se il pannello «multi trade» sia ancora usato.
