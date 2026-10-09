# DECISIONI PER L'UTENTE - Audit matematica (ripulito in fase 2, 09/10/2026)

Solo questioni ancora aperte e basate su fatti certificati (`05_ERRORI_DI_PROGETTAZIONE.md`, `CERTIFICAZIONE_REFERTI.md`).
Tolte rispetto alla fase 1 (versione originale in `lavori/fase2/DECISIONI_fase1_originale.md`):
- **D6** (massimo fra atlante e modello in Mike): e' una scelta scritta in `COSTITUZIONE_MIKE.md:157-158`.
- **D10** (convenzione della tau in-play): nessun bot usa l'altra convenzione; quella di `live_engine_pro` e' dichiarata.
- **D16** (minimo di puntata .it con prova vera): gia' deciso da te (1,00, multipli di 0,50; CRONOSTORIA.md:4790-4793, 4947).
- **D17** (tetto 10.000 EUR e back+lay): reperto falso, il tetto e' gia' gestito e il back+lay misto non puo' partire.

Stato di certificazione (dovuto dallo standard): **Safe tennis e' certificato** sul replay del 09/10, 18/18 OK, codice
`25cab047` (CRONOSTORIA.md:5609-5618). Ogni modifica che arriva a un bot passa da
`python -m Betfair.stream.backtest.certifica <bot> ...` -> paper -> live.

## 1. Dal fix del dutching (fase 2: correzione fatta, restano questi punti fuori perimetro)

| # | Decisione | Contesto | Rif. |
|---|---|---|---|
| F1 | Build dell'app ad app chiusa e ricertifica a vista del pannello Dutching | Il codice e i test sono pronti (`REFERTO_FIX_DUTCHING.md`); niente build e niente commit fatti | REFERTO sez. 2 |
| F2 | L'anteprima del dutching deve mostrare anche gli importi dopo la regola .it dei multipli di 0,50 (a mercato 40,50/34,00/25,00 invece del piano 40,51/34,18/25,32)? Vale per equal, target e variable | `build_order` arrotonda per difetto dopo il piano; il `profit_if_wins` del risultato e' quello del piano | REFERTO sez. 4.1 |
| F3 | Con pricing best / in_front / nominated l'anteprima e' una stima: basta l'etichetta, o va chiesto il piano al server prima della conferma? | | REFERTO sez. 4.2 |
| F4 | Allineare `roundToTick` di `frontend/src/lib/matching.ts` a flumine e dichiarare `legs` nel tipo `LiveOrderResult` (`liveOrders.ts`) | file fuori dal perimetro della fase 2 | REFERTO sez. 4.3-4.4 |
| F5 | Il server deve rifiutare un dutch BACK con profitto minimo negativo (book > 100%) o basta la conferma dell'utente? | oggi lo piazza se confermato | REFERTO sez. 4.5 |
| F6 | Controllare nello storico del conto se il dutching variable sul lato Lay e' mai stato usato in LIVE prima del fix | un ordine back a prezzo lay probabilmente restava non abbinato; danno non provato | 05 A1 |

## 2. Previsioni e modelli (gia' noti dal 02/10, mai decisi)

| # | Decisione | Contesto | Rif. |
|---|---|---|---|
| D4 | Vuoi la misura fuori campione del veto Under 3.5 di Mike (proposta del 02/10, 1-2 giorni)? | Il veto e' acceso per tua decisione (CRONOSTORIA.md:3058, 3118); il Poisson che lo alimenta e' meno informato delle quote (gia' noto, CRONOSTORIA.md:4888). Ogni cambio delle P obbliga a ritarare le soglie e a ricertificare Mike | 05 MA2 |
| D5 | Un solo motore per i lambda (tattico o Poisson) con identificativo nel dossier di Mike | Gia' proposto il 02/10 (CRONOSTORIA.md:4888, 3-4 giorni), non fatto | 05 M12 |
| D13 | Gate ML con baseline della media di lega e campioni di prova piu' grandi | Cambia quali mercati ML sono attivi e lo stake del foglio Quant Fund (non dei bot) | 05 MA1, A3 |
| D15 | Tenere in UI i consigli ML? | Il modello servito non aggiunge informazione alle quote | 05 A2 |
| D20 | Rimisurare dopo la notte del 10/10 le previsioni generate dopo il calcio d'inizio; poi marcare o escludere i residui | La causa probabile (cron GitHub in ritardo di 5-6 ore) e' stata rimossa il 09/10 con l'orologio pg_cron approvato (CRONOSTORIA.md:5580-5600); il legame e' un'inferenza, da confermare con la misura | 05 M1 |
| D23 | Salvare l'orario delle quote nell'ETL di `match_odds` | Serve a sapere se l'ML usa quote di chiusura come feature; che oggi l'orario manchi del tutto NON e' verificato in fase 2 | 05 M6 |

## 3. Strategie dei bot (divergenze scritte, nessuna modificata)

| # | Decisione | Contesto | Rif. |
|---|---|---|---|
| D2 | Safe tennis, cancello delle uscite in profitto: deve usare i punti del game e la forza dei giocatori? | Gli ingressi seguono le tue regole e non usano il modello; il modello decide solo se tenere o incassare un'uscita in profitto, con hold uguali 0,75 (manca `serve_data.csv`) e senza i punti del game | 05 A4 |
| D3 | Lo stop giornaliero di conto deve contare la commissione? | Il perimetro e' gia' deciso (E34, CRONOSTORIA.md:2956); lo stop di conto e' spento di serie (NULL = off nel codice; il valore sul DB non e' stato letto); resta solo la questione lordo/netto | 05 M22 |
| D7 | Theta sull'atlante v4? | Safe e Mike sono gia' sul v4; Theta e' opt-in e usa ancora il v3 | 05 M19 |
| D8 | (nota) Omega: tabella per minuto usata per 5 minuti, effetto prudente di circa x1,3 nella finestra d'ingresso | solo per conoscenza | 05 M21 |
| D9 | Scalper calcio: il bias confronta ML calibrato e Poisson 1X2 grezzo con il mid di mercato; tenere l'ML nel bias? | L'ML non aggiunge informazione al mercato; il Poisson 1X2 grezzo e calibrato sono quasi uguali | 05 A2, B6 |
| D11 | min_edge e Kelly calcolati per euro di stake anche sui lay | Nessuna scelta documentata trovata; e' strategia | 05 M17 |
| D12 | De-vig power/Shin al posto del moltiplicativo dove i lambda vengono dalle quote | Migliore sull'1X2 nella misura della fase 1 (non rifatta in fase 2); cambia i lambda in-play | 05 B14 |

## 4. Foglio Quant Fund, processi, pulizie

| # | Decisione | Contesto | Rif. |
|---|---|---|---|
| D14 | Il foglio Quant Fund (`money_management.py`, lanciato a mano con `aggiorna_report.bat`) e' ancora usato? Se si': minimo 1,00 dopo il tetto Kelly | Non usato dai bot (CRONOSTORIA.md:5384-5385) | 05 B8, B38 |
| D18 | Aliquota di commissione reale del conto per le stime paper/replay | Il conto reale usa la commissione vera; nessuna fonte certificata dell'aliquota italiana | 05 B9 |
| D19 | Permesso per un cruscotto settimanale di qualita' delle previsioni (Poisson, tattico, ML, quote) | Esiste solo un controllo settimanale ML nel foglio (`_auto_bss_check`); processo nuovo = serve permesso | 05 M2, B21 |
| D21 | Migrazioni SQL di coerenza dei report (drawdown, ROI dei lay, denominatori Decisioni) | Le applichi tu | 05 M15, M18, B3 |
| D22 | Cancellare le cartelle di modelli locali vecchi in `Ai Engine/models_cache/league_*` | Non sono serviti; «alcuni con leakage» NON VERIFICATO in fase 2 | 05 M10 |
