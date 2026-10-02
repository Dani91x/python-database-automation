# Sistema - Capitolo 9: il banco di prova (schede)

Schema: `09_banco_di_prova.html` (sorgente `09_banco_di_prova.architecture.json`).
Fonte dei fatti: `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md`, sezione H.

Schede dell'inventario usate: H-1 ... H-7.

Come si legge: il banco rigioca una partita vera registrata con il codice vero del bot. Betfair e
il database sono sostituiti (rosso chiaro); il bot no (verde).

---

## Comando certifica

**Cosa fa**
- E' l'unico modo ammesso per certificare un bot sul replay.

**Quando**
- Quando si certifica un bot prima della prova o del vero.

**Numeri**
- Tempo obiettivo: 5 minuti per bot, massimo 10 (regola dell'utente).

**Esempio con le cifre**
- `python -m Betfair.stream.backtest.certifica mike ...` sulla partita registrata 35760084.

**Cosa vedi nell'app**
- Niente: e' un comando da terminale.

**Se qualcosa va storto**
- Esito rosso nel referto e codice d'uscita diverso da zero.

**Per il tecnico**
- H-1 `Betfair/stream/backtest/certifica.py:1`.

## Registro dei bot

**Cosa fa**
- Elenca i bot certificabili con il loro programma di produzione e i loro controlli.

**Quando**
- Letto dal comando certifica.

**Numeri**
- 11 bot: Mike, Omega, Safe base, Safe esatto, Safe punta, Safe tennis, scalper calcio, 4 bot tennis.

**Esempio con le cifre**
- Un bot nuovo non registrato: il test di contratto lo rifiuta.

**Cosa vedi nell'app**
- Niente.

**Se qualcosa va storto**
- -

**Per il tecnico**
- H-2 `Betfair/stream/backtest/registro_bot.py:188`.

## Referto

**Cosa fa**
- Dice per ogni controllo se il bot si e' comportato bene. Misura la condotta, non il profitto.

**Quando**
- Alla fine del replay.

**Numeri**
- Un esito per controllo.

**Esempio con le cifre**
- «Mai una gamba lasciata a mercato dopo una chiusura»: superato o no.

**Cosa vedi nell'app**
- Niente.

**Se qualcosa va storto**
- -

**Per il tecnico**
- H-1 `Betfair/stream/backtest/certifica.py:15`.

## Servizio del bot

**Cosa fa**
- Il programma vero del bot, lo stesso del live, gira dentro il banco.

**Quando**
- Per tutta la partita registrata.

**Numeri**
- Stesso codice, stessi parametri.

**Esempio con le cifre**
- Mike rigioca la partita 35760084 minuto per minuto.

**Cosa vedi nell'app**
- Niente.

**Se qualcosa va storto**
- -

**Per il tecnico**
- H-2 (`moduli_produzione` del registro).

## Betfair simulata

**Cosa fa**
- Rilegge il flusso di Betfair registrato dal vivo e simula l'abbinamento degli ordini.

**Quando**
- Per tutta la partita.

**Numeri**
- Il tempo di mercato scorre anche mentre l'ordine viene piazzato (ritardo delle scommesse).

**Esempio con le cifre**
- Ritardo di 5 s in gioco: l'ordine viene abbinato ai prezzi di 5 s dopo.

**Cosa vedi nell'app**
- Niente.

**Se qualcosa va storto**
- -

**Per il tecnico**
- H-3 `Betfair/stream/backtest/banco_comune.py:2828`; H-4 `Betfair/stream/backtest/banco_comune.py:1905`.

## Porta di prova

**Cosa fa**
- Sostituisce la domanda diretta a Betfair e la coda; con la strada del filo risponde il vero
  motore degli ordini del runner.

**Quando**
- A ogni ordine del bot.

**Numeri**
- Due strade: coda o filo.

**Esempio con le cifre**
- Safe col filo: il suo ordine arriva al vero motore del runner, che lo piazza sulla Betfair
  simulata.

**Cosa vedi nell'app**
- Niente.

**Se qualcosa va storto**
- -

**Per il tecnico**
- H-5 `Betfair/stream/backtest/banco_comune.py:499`; H-7 `Betfair/stream/backtest/porta_banco.py:446`.

## Database in memoria

**Cosa fa**
- Sostituisce Supabase: le tabelle vivono nella memoria del replay.

**Quando**
- Per tutto il replay.

**Numeri**
- Nessuna chiamata a Supabase.

**Esempio con le cifre**
- Le 279 chiamate al minuto di Mike, nel banco, restano nella memoria.

**Cosa vedi nell'app**
- Niente.

**Se qualcosa va storto**
- -

**Per il tecnico**
- H-6 `Betfair/stream/backtest/banco_comune.py:217`.

## Partite registrate

**Cosa fa**
- Il flusso di Betfair e i punteggi registrati dal vivo.

**Quando**
- Registrati durante le partite vere.

**Numeri**
- Una cartella per partita in `_live_raw`.

**Esempio con le cifre**
- `_live_raw/35760084/35760084.raw.jsonl`.

**Cosa vedi nell'app**
- Niente.

**Se qualcosa va storto**
- -

**Per il tecnico**
- H-3 `Betfair/stream/backtest/banco_comune.py:6`.

## Frecce

- Comando certifica -> registro: sceglie il bot.
- Comando certifica -> referto: giudica la condotta.
- Registro -> servizio del bot: avvia il codice vero.
- Servizio del bot -> referto: cosa ha fatto.
- Partite registrate -> Betfair simulata: rilette.
- Betfair simulata -> servizio del bot: prezzi e punteggi.
- Servizio del bot -> porta di prova: ordini.
- Porta di prova -> Betfair simulata: piazza.
- Servizio del bot -> database in memoria: legge e scrive.

## Punti da decidere

1. Nessuno in questo capitolo.

## Punti non chiariti

1. Questo capitolo descrive il banco dal codice: nessun replay e' stato lanciato per disegnarlo.
