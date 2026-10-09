# CERTIFICAZIONE DEI REFERTI DELL'AUDIT MATEMATICA (fase 2, 09/10/2026)

Ordine dell'utente: ogni cosa scritta nell'audit deve essere vera e certificata. Questo file dice, per ogni reperto,
il verdetto, la prova e come e' stato verificato; per le affermazioni di 00-04, 06, 07 e DECISIONI rimanda alle
tabelle dei certificatori e riporta le correzioni applicate.

## 1. Metodo

- Cinque certificatori Sonnet in sola lettura, ciascuno con un perimetro (brief comune `lavori/fase2/BRIEF_CERTIFICAZIONE.md`):
  CERT_1 (A1-A4, MA1-MA2, M1-M12), CERT_2 (M13-M23, B1-B20), CERT_3 (B21-B41), CERT_4 (affermazioni di 01, 02, 04,
  06, 07, DECISIONI), CERT_5 (affermazioni di 00 e 03, campione di 40 citazioni, 17 blocchi di esempi numerici rifatti
  con le funzioni di produzione). Input: i referti V1/V2/V3 di `verifica_coordinatore/`, riverificati.
- Per ogni reperto: codice riletto alle righe attuali; percorso vivo e consumatore; ricerca in CRONOSTORIA.md, nelle
  costituzioni, in `PIANO_MODIFICHE_MIKE_2026-09-29.md` e negli audit precedenti; numeri rifatti con sonde nuove
  (`lavori/fase2/sonde/cert*.py`); stato dei bot solo dalla cronostoria.
- Il coordinatore non si e' fidato dei certificatori: ha riaperto di persona i punti che cambiano il messaggio
  all'utente (sez. 2) e ha verificato il fix del dutching per intero (`REFERTO_FIX_DUTCHING.md`).
- Correzioni applicate: 05, 07 e DECISIONI riscritti dal coordinatore; 00 e 03 (124 correzioni) e 01, 02, 04, 06 (180
  sostituzioni) corretti da due redattori con registro riga per riga (`lavori/fase2/APPLICATE_00_03.md`,
  `APPLICATE_01_02_04_06.md`), ogni punto marcato «[cert. fase 2]».

## 2. Verifiche indipendenti del coordinatore (riaperte di persona)

| Punto | Esito | Prova |
|---|---|---|
| A4 Safe tennis: ingressi senza modello | CONFERMATO | `safe_strategy/engine.py:1567` `evaluate_tennis`: nessun import di `tennis_opportunity`/`p_match` nel modulo; `bot_service.py:5295` `_model_gate` «Solo per le uscite in PROFITTO»; `bot_service.py:193` `auto_trade_tennis: False` |
| Safe tennis certificato | CONFERMATO | CRONOSTORIA.md:5609-5618: safe_tennis 18/18 OK, 0 violazioni, codice `25cab047`, «TUTTI I BOT TENNIS CERTIFICATI» |
| M20 Mike max hazard = scelta | CONFERMATO | `COSTITUZIONE_MIKE.md:157-158`: «Hazard 3' = MAX fra Atlante empirico ... e modello ... fino a x1,25. Comanda la fonte piu' prudente» |
| M13 minimi .it gia' decisi | CONFERMATO | CRONOSTORIA.md:4790-4793 (doc 2,00 smentito sul conto; minimi reali 1,00/1,00; modulo `minimi_it.py`) |
| B39 tetto 10.000 gestito | CONFERMATO (reperto FALSO) | `live_order_build.py:875-886` «Payout massimo (.it EUR 10.000)» con `raise ValueError` |
| M22 stop di conto spento e perimetro deciso | CONFERMATO | `config_stream.py:325` «NULL = off»; CRONOSTORIA.md:2956 «DECISIONE UTENTE: stop giornaliero E34 resta com'e'» |
| B7 calibrazione "none" scritta come calibrata | CONFERMATO (non assegnato ad alcun certificatore: verificato dal coordinatore) | `poisson_calibrator.py:86-92` (`source` resta "none" se DB e json non si leggono); `mike/dossier.py:102` legge `markets_calibrated` |
| A1 / M11 dutching | CONFERMATI e CORRETTI | `REFERTO_FIX_DUTCHING.md`: diff riletto, suite 11477 -> 11483 passati senza regressioni, 11 mutazioni proprie, differenziale 0/20.000 con seme proprio, percorso `_dispatch` -> `_write_error` letto (:4000-4008) |
| Gravita' A2, A3, MA1, MA2, M1 | CONFERMATE come GIA' NOTE | CRONOSTORIA.md:4888 rimanda ad `AUDIT_2026-10-02/AUDIT_ML_POISSON.md` («Nessuna modifica fatta») |

## 3. Tabella reperto -> verdetto -> prova -> come verificato

Colonne complete (righe attuali, output delle sonde, riferimenti) nei file CERT indicati; qui la sintesi.

| Reperto | Verdetto | Gravita' certificata | Prova sintetica | Come verificato |
|---|---|---|---|---|
| A1 | CONFERMATO, CORRETTO | ALTO (risolto) | worker :2914-2919, `dutching.py:224,239` side back | CERT_1 + coordinatore + fix |
| A2 | CONFERMATO, GIA' NOTO | MEDIO-ALTO | log-loss ML vs quote/climatologia rifatti (cert1_misure*.py) | CERT_1, sonda propria su m_dati.json |
| A3 | CONFERMATO, GIA' NOTO, numeri corretti | MEDIO-ALTO | `seriea_model_export.py:401`; holdout mediano ~90; ECE fallisce 89% a n=40 | CERT_1 (cert1_gate_sim.py, 1 SELECT registry LIMIT 500) |
| A4 | RIDIMENSIONATO; FALSO su ingressi e certificazione | MEDIO | engine.py:1567, bot_service.py:5295, CRONOSTORIA.md:5609-5618 | CERT_1 + coordinatore |
| MA1 | CONFERMATO, GIA' NOTO | MEDIO | `confidence_gate.py:170-215`; predittore costante a 0,74 -> BSS 0,23 | CERT_1 (cert1_gate_sim.py) |
| MA2 | CONFERMATO, GIA' NOTO | MEDIO-ALTO | RPS 1X2 +0,0164 [0,0117; 0,0209] | CERT_1 |
| M1 | CONFERMATO, GIA' NOTO, causa rimossa | MEDIO (da rimisurare) | 160/1519 e 200/1510; CRONOSTORIA.md:5580-5600 | CERT_1, CERT_4 |
| M2 | CONFERMATO | MEDIO | `valida_motore_poisson.py:28,96`; master_backtest in nessun workflow | CERT_1 |
| M3 | CONFERMATO sul numero, FALSO sullo scalper | BASSO | `bias_resolver.py:79-92` solo 1X2; pendenza O2.5 0,44-0,47 | CERT_1 |
| M4, M5 | CONFERMATI / RIDIMENSIONATI | BASSO | today_predictions_backfill.py | CERT_1 |
| M6 | CONFERMATO nel codice; NULL al 100% NON VERIFICATO | MEDIO | `feature_pipeline.py:35-82` | CERT_1 |
| M7 | SCELTA DI PROGETTO dichiarata | BASSO-MEDIO | `seriea_model_export.py:234-262` | CERT_1 |
| M8, M9 | CONFERMATI (M8 GIA' NOTO) | MEDIO | ensemble_trainer.py:866-872; predict_fixture.py:870-909 | CERT_1 |
| M10 | CONFERMATO | BASSO | seriea_model_export.py:50 | CERT_1 |
| M11 | CONFERMATO, CORRETTO | MEDIO (risolto) | anteprima = piano server | CERT_1 + fix |
| M12 | CONFERMATO, GIA' NOTO in parte | MEDIO | stream/db.py:262-285 | CERT_1 |
| M13 | CONFERMATO incoerenza; regola GIA' DECISA | BASSO | CRONOSTORIA.md:4790-4793, 4947 | CERT_2 + coordinatore |
| M14-M16, M18, M23 | CONFERMATI | BASSO | vedi CERT_2 | CERT_2 (cert2_sonda.py) |
| M17 | CONFERMATO, nessuna scelta documentata | MEDIO (strategia) | live_engine_pro.py:596-607 | CERT_2 |
| M19 | CONFERMATO in parte | MEDIO ripiego / BASSO Theta | theta_bot.py:546-551; CRONOSTORIA.md:3045-3047 | CERT_2 |
| M20 | SCELTA DOCUMENTATA | NESSUNA (BASSO "1,25 non calibrato") | COSTITUZIONE_MIKE.md:157-158 | CERT_2 + coordinatore |
| M21 | RIDIMENSIONATO | BASSO | finestra d'ingresso fino all'80', ~x1,3 prudente | CERT_2 (sonda aritmetica) |
| M22 | RIDIMENSIONATO, GIA' DECISO (perimetro) | BASSO | config_stream.py:325; CRONOSTORIA.md:2956 | CERT_2 + coordinatore |
| B1-B20 | 16 CONFERMATI, B4 RIDIMENSIONATO, B5/B11 in parte, B19 NON VERIFICATO; B7 CONFERMATO (coordinatore) | BASSO (B15 BASSO-MEDIO) | CERT_2 tab.; B10: 196 su 99.900 | CERT_2, coordinatore per B7 |
| B21-B41 | B39 FALSO; B25 NESSUNA; B28, B32 SCELTA DOCUMENTATA; B21, B22, B24, B33, B38, B41 RIDIMENSIONATI; B29, B31, B36, B37 in parte NON VERIFICATI; gli altri CONFERMATI | BASSO / NESSUNA (B40 MEDIO se l'effetto si conferma) | CERT_3 tab.; live_order_build.py:875-886 | CERT_3 (cert3_*.py) |

## 4. Affermazioni di 00-04, 06, 07, DECISIONI

- 00 e 03 (CERT_5): campione di 40 citazioni -> 35 confermate, 4 imprecise, 1 falsa; scansione di 428 citazioni -> 2
  sbagliate (`devig.py`, `journalStats.ts`); 3 consumatori falsi (P-13, P-15, P-23/24/28) e 3 imprecisi; 20 gravita'
  disallineate; frasi false su Safe tennis non certificato, minimi .it "da provare", tetto 10.000 non gestito;
  contraddizione Kelly. Tutto corretto (registro `APPLICATE_00_03.md`).
- 01, 02, 04, 06 (CERT_4): parametri del tattico in `tactical_engine/serving.py:46,48` (non `model.py`); righe dei pesi
  di forma (:1493), k=8 (:1522), blend (:1523); pendenza O2.5 0,44-0,47 (non 0,53); holdout ~90; causa delle previsioni
  tardive rimossa il 09/10; proposte di 06 in contrasto con scelte documentate (n.7, n.30, n.31, n.32, n.23/29)
  riscritte; proposte 1-2 segnate FATTE. Registro `APPLICATE_01_02_04_06.md`.
- 07 e DECISIONI: riscritti dal coordinatore. Tolte D6, D10, D16, D17; riscritte D2, D3, D4, D7, D9, D14, D20, D23;
  aggiunte F1-F6 dal fix del dutching. Nel 07 restano solo fatti certificati; «4 ALTI», «17% dove succede 33%»,
  «Safe tennis non certificato», «regole .it non gestite» tolti.

## 5. NON VERIFICATO (non entra nel riepilogo come fatto)
- `snapshot_time` NULL al 100% in `match_odds` (M6); effetto in euro di MA2 sul veto di Mike; contaminazione delle
  previsioni tardive; ramo temperature dei calibratori (M8); se il tattico arrivi dopo l'armo di Mike (M12).
- «-44% a 88-89'» dell'atlante v3 (M19); 2,6% dell'hedge nello stesso mercato (B15); unita' di B19; B29, B30 (effetto),
  B31, B36, B37 in parte.
- Stato di certificazione attuale di Mike e dello scalper calcio (non riletto in cronostoria oltre il 04/10).
- Il fix del dutching non e' stato eseguito contro Betfair (nessun ordine per regola) ne' visto nell'app (build da fare).
