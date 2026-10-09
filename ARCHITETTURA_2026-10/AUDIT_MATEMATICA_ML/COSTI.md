# COSTI — Audit matematica (tetto 78 USD)

| Tappa | Ora | Spesa cumulata (USD) | Note |
|---|---|---|---|
| 0. Avvio, lettura brief, piano | 11:37 | 0.29 | nessun delegato ancora |
| 1. Ondata 1 (A Poisson, B ML, C Betfair, D frontend/SQL/analytics) | 12:00 | 8.33 | 4 delegati Sonnet, file in lavori/ |
| 2. Ondata 2 (E completezza, E2 lacune, F flusso, H verifica avversaria) | 12:15 | 16.38 | 4 delegati Sonnet |
| 3. Ondata 3 (V2 verifica, R stato dell'arte, M misure ML/Poisson/quote) + verifica personale dutching | 12:35 | 21.06 | 3 delegati Sonnet |
| 4. Consegne 00 e 03 (bozze delegate, Sonnet) + verifiche puntuali coordinatore | 12:50 | 24.65 | 2 delegati |
| 5. Consegne 01, 02, 04 scritte dal coordinatore | 13:20 | 26.41 | - |
| 6. Consegne 05, 06 scritte dal coordinatore; 00 e 03 riletti | 13:35 | 27.10 | - |
| 7. Ondata 4 (Q orario quote, X coerenza) + ondata 5 (Z1 hazard, Z2 tennis) + patch consegne | 14:15 | 36.30 | 4 delegati Sonnet |
| 8. DECISIONI, 07 riepilogo, chiusura | 14:25 | 36.80 | coordinatore |

Totale: circa 36,8 USD su 78 (47%). Delegati Sonnet: 16 (ondate 1-5 + assemblaggi), mai piu' di 4 in parallelo.
Ripartizione indicativa: inventario+Poisson+ML+componenti (ondata 1) 8,3; completezza/flusso/verifica (ondata 2) 8,0;
verifica/stato dell'arte/misure (ondata 3) 4,7; assemblaggi 00/03 3,6; orario quote/coerenza/hazard/tennis 7,2;
sintesi e patch del coordinatore ~5.

## FASE 2 - Certificazione referti + fix dutching (tetto sessione 86 USD; budget di fase ~43 USD)

| Tappa | Ora | Spesa di sessione (USD) | Note |
|---|---|---|---|
| F2-0. Avvio, lettura brief fase 2 ed ESITO_VERIFICA | 14:40 | 1.64 | contatore di sessione ripartito da 0 (36,97 USD gia' spesi in fase 1) |
| F2-1. Baseline suite + 3 certificatori (CERT_1, CERT_2, CERT_3) | 15:00 | 6.60 | 3 delegati Sonnet |
| F2-2. Fix dutching (delegato) + CERT_4, CERT_5 | 15:25 | 15.90 | 3 delegati Sonnet |
| F2-3. Verifica coordinatore fix (vitest, tsc, falsificazione UI, differenziale) + correzioni 00-04, 06 (2 delegati) | 15:55 | 23.49 | |
| F2-4. Falsificazione Python coordinatore, suite DOPO, REFERTO_FIX_DUTCHING | 16:10 | 26.15 | |
| F2-5. 05, DECISIONI, 07 riscritti dal coordinatore | 16:25 | 26.84 | |
| F2-6. CERTIFICAZIONE_REFERTI, revisione avversaria finale, correzioni, chiusura | 16:50 | 32.10 | 1 delegato Sonnet |

Totale fase 2: circa 32,1 USD (budget di fase ~43). Delegati Sonnet: 10 (CERT_1-5, fix dutching, 2 redattori, revisione finale), mai piu' di 4 insieme.
Totale audit (fase 1 + fase 2): circa 69 USD.
