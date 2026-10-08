# COSTI DELLA SESSIONE DEL PIANO DI ARCHITETTURA (tetto 190 USD, ordine dell'utente)

Fonte: contatore di spesa della sessione (Claude Agent SDK), letto a ogni tappa; dalla ripresa delle 14:33
il cumulativo = 40,94 USD (spesa del primo processo, comunicata dall'utente) + contatore del processo corrente.
Cumulativo = spesa totale (coordinatore + delegati).

| Ora | Tappa | Cumulativo USD | Nota |
|---|---|---|---|
| 12:20 | 0. Avvio: lettura del brief, brief comune dei delegati | 0,40 | |
| 12:35 | 1. Lancio dei 19 delegati Sonnet (inventario, competitor, misure, schede A-K) | 9,70 | costo del lancio (prompt iniziali) |
| 12:37 | Fine del primo processo: delegati interrotti prima di scrivere le schede; restano script e uscite in `strumenti/` | 40,94 | dato del registro di `sessione_sdk.py` |
| 14:40 | Ripresa: stato su disco verificato, brief comune con sezione «ripresa ed efficienza»; delegati a ondate di 4, in primo piano | 41,70 | |
| 15:35 | 2. Ondata 1 (4 delegati Sonnet in primo piano): 00 inventario, 02 competitor, 07 misure, scheda A; verifica a campione del coordinatore | 68,60 | ~6,5 USD per delegato: dalla prossima ondata tetto di chiamate piu' stretto; G1+G2 fuse, K assorbita da 00 |
