# 08/10 - Banco comune: il mercato che attraversa (blocco del delegato, da integrare)

## Cosa e' stato fatto
- Regola nuova nel banco comune (`Betfair/stream/backtest/banco_comune.py`, testata 6-quater,
  interruttore `ATTRAVERSAMENTO = True`, metodo `MotoreReplay._mercato_che_attraversa`, chiamato
  in `MotoreReplay._a_flumine` DOPO il `SimulatedMiddleware` e PRIMA di
  `_process_simulated_orders`): un ordine LIMIT vivo (non PENDING, `bet_id` assegnato, book
  pubblicato DOPO `date_time_placed`), con residuo, su mercato OPEN e runner ACTIVE, viene
  abbinato per tutto il residuo AL SUO PREZZO quando nel book c'e' volume scambiato nuovo
  (`RunnerAnalytics.traded`, delta di tradedVolume, non consumato dalla coda) a un prezzo oltre
  il suo (LAY: < P; BACK: > P). Si registra solo l'abbinato EFFETTIVO (un guasto con tetto
  puo' rifiutarlo). Registro: `SimulatedOrder.fill_attraversati`, `MotoreReplay.fill_attraversati`,
  `MercatoFlumine.fill_attraversati()` e `riepilogo_fill()["attraversati"]`,
  `EsitoReplay.fill_attraversati`, nota di referto `nota_fill_attraversati` (scalper calcio e
  tennis), specchio `_fill_attraversato` (`varianti_bot.campi_ordine`, chiave presente SOLO
  quando e' successo).
- Test: `Betfair/stream/tests/test_banco_attraversa_2026_10_08.py`, 11 verdi; mutazioni
  M1-M9 tutte ROSSE (M3b verde: guardia ridondante, attesa) - `mutazioni.txt`.
- Suite: `pytest Betfair/stream/backtest` + contratti applica_bot + replay professionale +
  fedelta' paper: 244 passed, 5 skipped; `Betfair/stream/tests` + `tennis_live/tests`: exit 0.

## Caso vero (35768297, media-under-paper, clic 1783034130481)
- banca 10,20 @2,02: prima 23:21:53 (coda) -> dopo **23:18:01 UTC, motivo attraversato**
  (scambio a 2,00), verificato sul raw (`caso_vero_verifica_sul_raw.txt`).
- NON "tutto il resto identico": la regola vale per TUTTI gli ordini della sessione, e gia'
  la banca 10,18 @2,20 del ciclo 1 si abbina alle 20:57:46 (scambio a 2,18, verificato sul raw)
  invece che alle 21:04:21: da li' il bot segue un altro percorso (5 cicli invece di 4, 20
  ordini invece di 16). P&L a regolamento (conto_banco) lordo 0,76 -> 0,95 (netto 0,72 -> 0,90).
  Violazioni: nessuna, prima e dopo.

## Certificazione
- Tennis tennis_pro 35790089 tutti (17 scenari): 0 violazioni prima e dopo; unica differenza la
  nota "fill per mercato che attraversa: 0" in ogni scenario (19 s).
- Calcio scalper_calcio 35797769: prima `tutti` (47 scenari) 115 min (oltre il tetto: lo dico),
  KO pre-esistenti in `riavvio` e `uscite-manuali-firmate`. Dopo, per ordine del coordinatore,
  solo i 5 scenari di riferimento (6 min 11 s): base, paper, rifiuti-betfair, sniper-paper OK;
  **chiusura-abbinata-in-parte KO (NUOVO)**: B2 (sel 22 del MATCH_ODDS 1.259819674 aperta al
  fischio, 0,91) e CP4 (chiusura LAY che chiede 1,02 con 0,91 da chiudere). Tutti i 5 scenari
  divergono dal prima perche' alle 17:00:06.704 un unico messaggio dello stream porta scambi da
  1,64 a 1,72 sulla sel 22 e da 4,0 a 4,4 sulla 58805: tre ordini dello scalper (BACK 1,66, LAY
  1,65, BACK 4,20) vengono abbinati per attraversamento nello stesso book e la sessione segue
  un altro percorso. NON certificato: va deciso dal coordinatore/utente.

## Punto di ripresa
Decidere sul KO nuovo di chiusura-abbinata-in-parte (difetto di condotta dello scalper esposto
dal percorso nuovo, o artefatto del messaggio aggregato delle 17:00:06): referti in
`AUDIT_2026-10-08/banco_attraversa/`.
