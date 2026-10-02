# Sistema - Capitolo 5b: il database come postino, tennis e scalper (schede)

Schema: `05b_database_tennis_scalper.html` (sorgente `05b_database_tennis_scalper.architecture.json`).
Fonte dei fatti: `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md`, sezione D e tabella D-M.

Schede dell'inventario usate: D-15 ... D-18, D-M, A-10.

Come si legge: come il capitolo 5a. Nel minuto misurato non c'era nessuna partita tennis seguita
e nessuna sessione scalper accesa: sono i numeri «a vuoto».

---

## Runner tennis

**Cosa fa**
- Senza partite rilegge la lista delle partite tennis da seguire.

**Quando**
- Ogni 2 s.

**Numeri**
- 28 al minuto.

**Esempio con le cifre**
- 28 letture in 60 s = una ogni 2,1 s circa.

**Cosa vedi nell'app**
- Niente finche' non segui una partita.

**Se qualcosa va storto**
- -

**Per il tecnico**
- D-15 `Betfair/stream/tennis_live/tennis_runner.py:3012`; tabella `tennis_live_follow`.

## Ponte tennis

**Cosa fa**
- Legge i comandi dei 4 bot tennis, scrive il battito di ognuno, controlla la lista delle partite.

**Quando**
- Ogni 15 s.

**Numeri**
- 36 al minuto: 33 su comandi e battiti, 3 sulla lista partite.

**Esempio con le cifre**
- Un battito per bot (4 bot) a ogni giro: 12 battiti nel minuto misurato, 72 in 5 minuti, cioe'
  18 giri in 5 minuti (uno ogni 16-17 s: 15 s di attesa piu' il lavoro del giro).

**Cosa vedi nell'app**
- Stato dei bot tennis.

**Se qualcosa va storto**
- -

**Per il tecnico**
- D-16 `Betfair/stream/tennis_live/tennis_bot_service.py:170`, `Betfair/stream/tennis_live/tennis_bot_service.py:676`.

## Scalper calcio

**Cosa fa**
- Rilegge i comandi delle sessioni, l'interruttore generale e il freno.

**Quando**
- Ogni 3 s.

**Numeri**
- 54 al minuto: 18 + 18 + 18.

**Esempio con le cifre**
- 18 letture al minuto = una ogni 3,3 s per ciascuna delle tre.

**Cosa vedi nell'app**
- Pannello scalper.

**Se qualcosa va storto**
- -

**Per il tecnico**
- D-17 `Betfair/stream/scalper/scalper_service.py:75`, `Betfair/stream/scalper/scalper_service.py:94`,
  `Betfair/stream/trading/controls.py:96`.

## Quote tennis

**Cosa fa**
- Cancella e riscrive le partite tennis del giorno.

**Quando**
- Ogni 30 minuti.

**Numeri**
- 2 chiamate per giro (una cancellazione, una scrittura a blocchi).

**Esempio con le cifre**
- 02/10: 4 chiamate in due giri (16:25 e 16:55).

**Cosa vedi nell'app**
- Lista partite tennis.

**Se qualcosa va storto**
- Fra la cancellazione e la scrittura la lista resta vuota per un attimo.

**Per il tecnico**
- D-18 `betfair_tennis_odds.py:274`, `betfair_tennis_odds.py:278`.

## Partite tennis seguite

**Cosa fa**
- Lista delle partite tennis che il runner tennis deve seguire.

**Quando**
- Letta dal runner ogni 2 s e dal ponte a ogni giro.

**Numeri**
- 31 letture al minuto.

**Esempio con le cifre**
- Il ponte aggiunge una partita: il runner la vede entro 2 s.

**Cosa vedi nell'app**
- «Segui live» del tennis.

**Se qualcosa va storto**
- -

**Per il tecnico**
- `tennis_live_follow`.

## Comandi bot tennis

**Cosa fa**
- Armamento dei 4 bot tennis per partita e stato del servizio di ognuno.

**Quando**
- Letta e scritta dal ponte a ogni giro.

**Numeri**
- 33 al minuto.

**Esempio con le cifre**
- Armi il bot «pro» su una partita: la riga nasce qui.

**Cosa vedi nell'app**
- Pannello dei bot tennis.

**Se qualcosa va storto**
- -

**Per il tecnico**
- `tennis_bot_control`, `tennis_bot_service_control`.

## Comandi scalper

**Cosa fa**
- Interruttore generale dello scalper e una riga per sessione.

**Quando**
- Letta ogni 3 s.

**Numeri**
- 36 al minuto.

**Esempio con le cifre**
- Armi lo scalper su una partita: la riga «richiesta» fa partire una sessione al giro dopo (entro
  3 s).

**Cosa vedi nell'app**
- Pannello scalper.

**Se qualcosa va storto**
- -

**Per il tecnico**
- `scalper_control`, `scalper_service_control`.

## Impostazioni ordini

**Cosa fa**
- Dice se gli ordini sono in prova o veri e se il freno di sicurezza e' tirato.

**Quando**
- Letta dallo scalper ogni 3 s e dal runner calcio circa 2 volte al secondo.

**Numeri**
- 18 al minuto dallo scalper; 123 dal runner calcio (capitolo 5a).

**Esempio con le cifre**
- Tiri il freno alle 18:00: il runner lo vede entro 1 s, lo scalper entro 3 s.

**Cosa vedi nell'app**
- Interruttore prova/vero e freno.

**Se qualcosa va storto**
- -

**Per il tecnico**
- Funzione `get_live_settings`; D-5, D-17.

## Partite tennis del giorno

**Cosa fa**
- Lista delle partite tennis di oggi con le quote.

**Quando**
- Riscritta ogni 30 minuti.

**Numeri**
- 27 partite alle 16:55 del 02/10.

**Esempio con le cifre**
- 27 partite scritte in un blocco solo.

**Cosa vedi nell'app**
- «Partite del giorno» tennis.

**Se qualcosa va storto**
- -

**Per il tecnico**
- `tennis_markets`.

## Frecce

- Runner tennis -> partite tennis seguite: 28 al minuto.
- Ponte -> partite tennis seguite: 3 al minuto.
- Ponte -> comandi bot tennis: 33 al minuto.
- Scalper -> comandi scalper: 36 al minuto.
- Scalper -> impostazioni ordini: 18 al minuto.
- Quote tennis -> partite tennis del giorno: 2 chiamate per giro (una cancellazione, una scrittura),
  tratteggiata perche' non e' continua.

## Punti da decidere

1. Runner tennis e scalper rileggono il database anche a vuoto (28 e 54 al minuto).

## Punti non chiariti

1. Con partite tennis seguite il runner tennis scrive anche quote e posizioni (dal codice: ogni 2 s
   per partita e ogni 1 s per selezione, senza controllare se sono cambiate). Non misurato il 02/10.
