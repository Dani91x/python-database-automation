# 07 - RIEPILOGO PER L'UTENTE (audit della matematica, certificato il 09/10/2026)

Questo riepilogo contiene solo fatti ricontrollati sul codice, sulla cronostoria e con calcoli rifatti (fase 2).
La prima versione conteneva errori (in particolare su Safe tennis): e' conservata in `lavori/fase2/07_fase1_originale.md`.

## In tre righe
1. **Le formule che muovono i soldi dei bot sono giuste** (green-up, profitti e perdite back e lay, puntate, scala delle
   quote). Nessun errore critico. Restano differenze di centesimi tra copie della stessa formula (es. la commissione
   stimata nel cash-out di Mike: 0,62 EUR nel caso provato), elencate in 05 come BASSE.
2. **L'unico errore con soldi veri era nel dutching manuale** (modo "variabile" sul lato LAY piazzava puntate BACK) ed e'
   **corretto**: codice e test pronti, manca solo la build dell'app ad app chiusa.
3. **I modelli di previsione (Poisson e ML) prevedono peggio delle quote dei bookmaker.** Era gia' scritto nell'audit
   del 2 ottobre e non e' mai stato deciso niente: va deciso se e come usarli.

## Cosa e' stato corretto oggi (dutching)
- Il modo "variabile" sul lato LAY ora viene **rifiutato** sia dal pannello sia dal server: zero ordini.
- L'anteprima del modo "variabile" ora mostra **esattamente il piano che il server usa** (controllato su 40.000 casi:
  nessuna differenza).
- Se il server non piazza niente, il pannello scrive "Dutching NON piazzato" invece di "inviato".
- Controlli: togliendo un pezzo della correzione alla volta, i test nuovi se ne accorgono (10 prove su 11; l'undicesima e'
  una protezione doppia, rilevata insieme all'altra); suite completa dei bot
  11.477 -> 11.483 test superati, nessun test rotto, zero errori di tipi nel frontend.
- Resta da sapere: a mercato ogni puntata viene poi arrotondata per difetto a multipli di 0,50 (la regola .it che hai
  deciso), quindi gli importi veri possono essere fino a 0,50 piu' bassi per gamba di quelli in anteprima.

## Le domande dell'audit

| Domanda | Risposta | Perche' |
|---|---|---|
| Poisson: siamo al miglior livello? | **No** | Le formule sono corrette, ma il modello usa solo le partite della stagione e non le quote: sull'1X2 sbaglia piu' delle quote, in modo netto e sicuro. Gia' noto dal 2 ottobre. |
| Poisson: abbiamo omesso qualcosa? | **Si'** | Nessuna misura settimanale della qualita'; nessuna memoria della stagione precedente; un solo valore fisso di correlazione dei gol per quasi tutte le leghe (scelta dichiarata nel codice). |
| Poisson: si puo' migliorare? | **Si'** | Le probabilita' sui gol sono troppo "sicure di se'": nella fascia dove il modello dice 16% l'Over 2.5 e' successo il 30% delle volte (27 partite); la calibrazione corregge solo in parte. |
| ML: e' al massimo livello? | **No** | E' costruito con cura, ma il modello in uso non aggiunge niente alle quote e su Over 2.5 e Goal/NoGoal non fa meglio della media della lega. Omega, Mike e Safe non lo usano; lo usano i consigli in UI, lo scalper calcio, il foglio Quant Fund. |
| ML: cosa manca? | | Il "cancello" che giudica un modello affidabile decide su circa 90 partite di prova e lo confronta con una moneta invece che con la media della lega: un modello che ripete solo la media passa, e un modello
  perfetto viene bocciato spesso (54% delle volte con 87 partite di prova). Gia' noto dal 2 ottobre. |
| Componenti dei bot: sono giusti? | **Si' per eseguire** | Green-up, P&L, Kelly, scala delle quote: rifatti con le funzioni vere, tornano; la commissione differisce di qualche centesimo tra copie (BASSO). Le regole .it (minimo 1,00, tetto di vincita 10.000 EUR) sono gia' gestite. |
| Componenti dei bot: dove si puo' fare meglio? | **In parte** | Safe tennis: gli ingressi seguono le tue regole; solo la decisione "incasso ora o tengo" usa un modello che guarda il punteggio dei giochi ma non i punti del game ne' chi e' piu' forte. Il bot e' certificato (18/18 il 9/10). |
| I numeri arrivano bene a bot e UI? | **In gran parte si'** | Unita' coerenti dappertutto. Restano: solo Omega controlla quanto sono vecchi i gol attesi che usa (in cache); Mike no, lo scalper non verificato; Mike non sa se i gol attesi vengono dal motore tattico o dal Poisson; alcune schermate calcolano la stessa cosa in due modi (drawdown 20 contro 30 sulla stessa serie). |

## Le prime azioni (in ordine)
1. **Build del pannello dutching ad app chiusa** e prova a vista (F1).
2. **Decidere cosa fare dei modelli di previsione** (gia' in sospeso dal 2 ottobre): misura fuori campione del veto
   Under 3.5 di Mike (D4), un solo motore per i gol attesi (D5), cancello ML onesto (D13), consigli ML in UI (D15).
3. **Rimisurare dopo la notte del 10/10** le previsioni scritte a partita iniziata: la causa probabile (orologio delle action in
   ritardo di 5-6 ore) e' stata tolta oggi (D20).
4. **Safe tennis**: decidere se il cancello "incasso o tengo" deve usare i punti del game e la forza dei giocatori (D2).
5. **Cruscotto settimanale della qualita' delle previsioni**, con il tuo permesso (D19).

Dettagli: `05_ERRORI_DI_PROGETTAZIONE.md` (ogni reperto con verdetto), `CERTIFICAZIONE_REFERTI.md` (come e' stato
verificato ogni punto), `REFERTO_FIX_DUTCHING.md`, `DECISIONI_PER_L_UTENTE.md`.

Non verificato (quindi non scritto qui come fatto): l'effetto in euro dei limiti dei modelli sui bot; se il dutching
variabile sul lato LAY sia mai stato usato in live prima di oggi; l'aspetto del pannello nell'app (non avviata).
