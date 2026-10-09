# Esito della verifica del coordinatore sui reperti principali (09/10/2026)

Tre verificatori Opus indipendenti (referti V1_ML.md, V2_POISSON.md, V3_BOT.md) + controlli a campione del coordinatore
sul codice. Questo file PREVALE su 05 e 07 dove differiscono.

| Reperto | Esito | Soldi dei bot? | Nota |
|---|---|---|---|
| A1 dutching variable lato LAY piazza BACK | CONFERMATO (coordinatore) | strumento manuale, anche live | il piu' urgente |
| M11 anteprima dutching variable diversa dal piazzato | CONFERMATO | strumento manuale | fino a 16 EUR per gamba su 100 |
| A4 Safe tennis | RIDIMENSIONATO + FALSO in parte | solo cancello degli incassi | ingressi = regole dell'utente; certificato 18/18 il 09/10 |
| MA2 Poisson perde contro le quote | CONFERMATO (gia' noto dal 02/10) | Mike veto U3.5 (effetto in EUR non misurato) | |
| M3 Poisson grezzo troppo estremo sui mercati gol | CONFERMATO sui gol, FALSO sullo scalper | Mike U3.5 (calibrato ancora estremo) | lo scalper legge solo 1X2, quasi calibrato |
| M1 previsioni dopo il calcio d'inizio | CONFERMATO, impatto RIDIMENSIONATO | no | analytics e calibrazione settimanale |
| A2 ML senza valore oltre quote/tasso base | CONFERMATO (gia' noto dal 02/10) | no (Omega/Mike/Safe non leggono ML) | consigli UI, Direzione, Telegram, foglio |
| A3 gate ML su holdout minuscoli | CONFERMATO, peggio del dichiarato | no | |
| MA1 BSS contro baseline uniforme | CONFERMATO | no | foglio Quant Fund assegna stake |
| M22 stop giornaliero lordo di commissione | RIDIMENSIONATO | stop di conto oggi SPENTO; stop dei bot al netto | |
| M20 hazard di Mike | SCELTA DOCUMENTATA (COSTITUZIONE_MIKE.md:157-158) | ~0,18 EUR/partita | non e' un errore |
| M21 tabella per minuto di Omega | RIDIMENSIONATO | puo' solo togliere ingressi | sfasamento non documentato |

Lezione: l'audit automatico va usato come elenco di indizi; MA2, M1, A2, A3, MA1 erano gia' in
`AUDIT_2026-10-02/AUDIT_ML_POISSON.md` e non erano mai stati portati all'utente per una decisione.
