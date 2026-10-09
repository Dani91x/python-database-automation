# C2 — Libro ordini del conto, P&L di mercato, riconciliazione in ombra (W1-C2, 09/10/2026)

Comparto C (porta degli ordini), parte 2. Schema del `COSA_FA.md` (04 par. 2.4). Referto completo:
`ARCHITETTURA_2026-10/ondata1/W1-C2/REFERTO.md`.

## 1. Scopo

Dare al ladder di Trading TUTTI gli ordini del conto «come un tool professionale» (priorita' dell'utente, 09/10): ogni
ordine, dell'utente o dei bot, dall'app o dal sito, con CHI l'ha fatto, abbinato, residuo, prezzo medio, stato, e il
P&L di mercato «se vince» per selezione (totale e per autore). Accanto, un riconciliatore IN OMBRA (tappa T11) che
confronta conto, specchio, blotter e diario e scrive le divergenze, senza toccare niente.

| File | Cosa |
|---|---|
| `attribuzione.py` | `OrdineDalConto` -> `Autore` (`attribuisci_riferimenti`, `attribuisci`, `attribuisci_dichiarato`), `Indizio` (DB/specchio/coda come dati), `regole_di_oggi()` (costanti importate dal codice di oggi) |
| `libro_conto.py` | `LibroConto` (implementa `LibroOrdiniConto`), `SorgenteOrdiniProva`/`OrdineInProva` (paper), conversioni `ordine_da_riga_conto`/`ordine_da_corrente`, `fase_dell_ordine`, `comandi_ammessi` (proposta) |
| `pnl_mercato.py` | `calcola`/`posizione_mercato` -> `PosizioneMercato`; `esposizioni_per_selezione` (flumine), `pnl_se_vince` (formula del ladder), `pnl_bloccato` (`lockedPnlAt`) |
| `riconciliazione.py` | `RiconciliatoreOmbra.giro` -> `RefertoOmbra` (divergenze, `StatoOrdine`, `PosizioneConto`, comandi in volo); `in_volo_dal_diario` |

## 2. Entrate

- LIVE: un `FlussoOrdiniConto` (protocollo di `nucleo/betfair/contratto.py`, implementazione W1-A2) -> `OrdineDalConto`.
- PROVA: una `SorgenteOrdiniProva` (protocollo definito in `libro_conto.py`, alimentato in ondata 2 dai motori paper)
  -> `OrdineInProva(ordine, attore)`; la grafia e' quella di `listCurrentOrders` (`esiti_ordini_canale.ordine_paper_del_conto`).
- Indizi di attribuzione come DATI (righe gia' lette altrove: tabelle dei bot, specchio, coda del runner).
- Riconciliazione: conto (`OrdineDalConto`, dal libro o da `listCurrentOrders` con `ordine_da_corrente`), righe di
  `betfair_live_orders` con `mode`, ordini del blotter flumine (oggetti veri), righe del diario del motore;
  `conto_completo` = il libro ha fatto il seme.
- Revisione 09/10: il SEME da `listCurrentOrders` (`SorgenteOrdiniCorrenti`, REST di A1) all'avvio e a ogni
  riconnessione senza ripresa (lo stream non rimanda gli EXECUTION_COMPLETE); `mb`/`ml` dello stream per
  `verifica_abbinato`; dal book `imposta_mercato` (runner, `bettingType`, `numberOfWinners`, chiuso).

## 3. Uscite

- `LibroConto.ordini(market_id, modo)` -> `OrdineConto` (autore, abbinato, residuo, prezzo medio, stato = fase del motore).
  Un ordine col solo ref del terminale manuale (`live`/`tennis`) e' `sconosciuto` PROVVISORIO finche' un indizio non dice
  di chi e' (`LibroConto.attribuzione(...).provvisoria`): nessun comando sul ladder nel frattempo.
- `LibroConto.posizione(market_id, modo)` -> `PosizioneMercato` (UN modo: paper e live mai sommati);
  `calcolo_posizione` -> `CalcoloPosizione` (supportato, esposizione `None` se i runner non sono noti, motivi:
  `tipo_ignoto`, `runner_ignoti`, `seme_non_fatto`, `abbinato_mancante`, `ordini_riassunti`...; `solo_abbinato`: gli
  ordini non abbinati NON entrano nell'esposizione, la UI lo dice). Per la UI: `pnl_mercato.posizione_per_json` (`NaN` ->
  `null`). Senza `numberOfWinners` il modello vale solo per i `marketType` a vincitore unico per definizione
  (`vincitori_ignoti`). Una riga di coda prova l'autore SOLO se ha piazzato quell'ordine (mai cancel/replace).
- `LibroConto.aggiungi_consumatore(cb)`: avviso a ogni ordine cambiato (aggancio al ladder in ondata 2).
- `RefertoOmbra`: divergenze tipizzate con gravita' e motivo; `StatoOrdine` per bet_id; `PosizioneConto` per selezione.

## 4. Dipendenze ammesse

`nucleo/comuni.py`, `nucleo/betfair/contratto.py` (solo tipi), `nucleo/ordini/contratto.py`. Librerie: flumine
(`calculate_matched_exposure`, `wap`). Codice di oggi IMPORTATO (riuso di funzioni pure e costanti, import PIGRO:
importare il nucleo non importa `Betfair.stream`, provato da un test in sottoprocesso):
`motore_ordini.fase_da_riga`, `ATTORI_COMANDO`; `esiti_ordini_canale.ordine_del_conto`;
`esposizione_fuori_bot.{prefissi_ref_bot, bot_di, motivo_bot_da_coda, TABELLE_BOT, SOURCE_SPECCHIO_A_MANO}`;
`reconcile_worker.{SOURCE_SCALPER, _REF_BOT_CON_TABELLA}`; `live_order_worker.CUSTOMER_STRATEGY_REF`;
`tennis_live_order_worker.CUSTOMER_STRATEGY_REF`; `tennis_runner._BOT_REGISTRY`; `scalper_session.PREFISSI_STRATEGIA`;
`canale_bot_tennis.SORGENTI_BOT_TENNIS`; `omega_config`, `mike.config`, `safe_strategy.bot_service.{SAFE_STRATEGY_REF,
_SAFE_REFS_STORICI}`. Quando il vecchio codice sara' archiviato (T26) queste costanti si spostano qui, con i test di
parita' che restano.

## 5. Funzionalita' coperte (id di `01_FUNZIONALITA.md`) e test

| Id | Cosa (in ombra / nuovo) | Test |
|---|---|---|
| F-007 | classificazione dell'ordine bot/sito/app dal ref | `test_c2_attribuzione.py::test_parita_con_la_classificazione_di_oggi` (43 riferimenti generati) |
| F-008 | proprietario per bet_id (qui come indizio-dato; la lettura DB resta vecchia) | `::test_indizi_dai_motivi_della_lettura_di_oggi_sul_client_vero`, `::test_indizi_tabella_vince_e_il_conflitto_si_scrive` |
| F-016 / D-045 | riconciliazione R1 col conto (ombra) | `test_c2_riconciliazione.py::test_parita_con_r1_giro_per_giro` (8 scenari x 2 giri) |
| C-055 / D-045 | ripresa dal diario R2 (ombra) | `::test_parita_con_r2_riavvio_con_ordini_in_volo` |
| C-050 | fasi dell'ordine (riuso di `fase_da_riga`) | `test_c2_libro_conto.py::test_stato_e_la_fase_del_motore_di_oggi` |
| F-040, F-059 | green-up / `lockedPnlAt` sulla posizione | `test_c2_pnl_mercato.py::test_green_up_e_lockedpnl_sulla_stessa_posizione` |
| J-078 (dati) | ordini e P&L del ladder di Trading | `test_c2_libro_conto.py`, `test_c2_pnl_mercato.py::test_se_vince_identico_alla_formula_del_ladder` |
| G-012 (in parte) | «ci sono soldi su questo evento?» dalla posizione del libro | `test_c2_pnl_mercato.py::test_esposizione_massima_con_e_senza_elenco_dei_runner` |

Restano al vecchio codice: C-052, C-054, D-046, D-054, F-009 (commissione), tutte le scritture (specchio, alert).

## 6. Interruttore previsto (ondata 2)

`ARCH_RICONCILIA=vecchio|ombra|nuovo` (di serie `vecchio`). `ombra`: il riconciliatore gira accanto a R1/R2 e scrive
il suo referto (in memoria e nel diario della Salute), mai nel DB. Il libro per il ladder: `ARCH_LIBRO_CONTO=0|1`
(topic additivo sul canale locale, vedi referto par. 8).

## 7. Come si sostituisce

Ogni pezzo e' dietro un protocollo: `LibroOrdiniConto` (contratto), `FlussoOrdiniConto`/`SorgenteOrdiniProva` per le
entrate, `RegoleAttribuzione` per le regole (si passa al costruttore: un test o un componente nuovo ne da' altre).
Cambiare la regola di attribuzione = cambiare `attribuzione.py` e la tabella `DIVERGENZE_ATTESE` del test.

## 8. Come si prova da solo

`python -m pytest Betfair/nucleo/ordini/tests/test_c2_*.py -q -p no:cacheprovider` (232 test dopo la seconda revisione del 09/10, ~15-30 s; mutazioni: `python ARCHITETTURA_2026-10/ondata1/W1-C2/mutazioni.py .`). Nessuna rete,
nessun DB (il client supabase e' vero su `httpx.MockTransport`), nessun file fuori da `tmp_path`.

## 9. Misure (macchina condivisa, carico ~8, Python 3.13)

| Misura | Valore |
|---|---|
| `ricevi_live` (attribuzione + fase + indici), 2000 ordini | p50 15 us, p95 29 us, p99 78 us |
| memoria del libro con 2000 ordini (tracemalloc) | ~1,4 MB |
| `posizione` su 30 ordini / 2000 ordini | p50 0,2 ms / 24 ms |
| `giro` dell'ombra, 2000 ordini sul conto, 1000 righe di specchio | 112 ms |
| primo `regole_di_oggi()` (import pigri del codice di oggi) | 3,6 s: va chiamato all'avvio, MAI nel percorso del ladder |

## 10. `PROCESSO_STANDARD_BOT.md` par. 6/7

Vedi referto par. 7 (voci sollecitate o ⊘ con la causa).
