# Replay di coerenza del coordinatore sulla cima fusa (09/10, 09:20-09:26, PC, --data-dir del checkout principale)

Confronto per blocco di scenario (script confronta_blocchi.py: esclusi tempo/worker/MEMORIA/comando/BOT/controlli attivi/TEMPO TOTALE, righe di log LIVELLO:modulo, id a 18 cifre).

## AUDIT_2026-10-08/decisioni_sera/replay_coordinatore/scalper_35797769.txt  vs  AUDIT_2026-10-08/controllo_finale/scalper/scalper_35797769_tutti.txt
[rifiuti-betfair-codici] DIVERSO: 5 righe solo nel riferimento, 3 solo nel mio
   - KO  35797769 [rifiuti-betfair-codici]  tick=665941 decisioni=121012 azioni= 132 stati=slot:IDLE,sessione:arming,sessione:running,slot:QUOTING2,slot:CANCELLING,slot:FLATTENING,slot:LOCKING,slot:DONE,sessione:done [COMPLETE]
   -       nota: FINTO BETFAIR coi codici veri: scavalco INVALID_BET_SIZE (placeOrders) su ('1.259819674', 58805) LAY 1.67 @4.2; ordini dopo 6; fine ciclo differenza 0.013; scritto col codice: si'; parcheggio INVALID_PROFIT_RATIO (plac
   -       motivo x79: min_bet_skip
   -       RC3 x1: ogni rifiuto di Betfair e' scritto nell'attivita' del bot col suo codice entro 3 giri
   -            es. ('1.259819674', 58805): rifiuto BET_TAKEN_OR_LAPSED (rimpiazzo, replaceOrders) mai scritto col codice nell'attivita' del bot
   + OK  35797769 [rifiuti-betfair-codici]  tick=665941 decisioni=121012 azioni= 132 stati=slot:IDLE,sessione:arming,sessione:running,slot:QUOTING2,slot:CANCELLING,slot:FLATTENING,slot:LOCKING,slot:DONE,sessione:done [COMPLETE]
   +       nota: FINTO BETFAIR coi codici veri: scavalco INVALID_BET_SIZE (placeOrders) su ('1.259819674', 58805) LAY 1.67 @4.2; ordini dopo 6; fine ciclo differenza 0.013; scritto col codice: si'; parcheggio INVALID_PROFIT_RATIO (plac
   +       motivo x78: min_bet_skip
[chiusura-abbinata-in-parte] DIVERSO: 3 righe solo nel riferimento, 1 solo nel mio
   - KO  35797769 [chiusura-abbinata-in-parte]  tick=665941 decisioni=121012 azioni= 213 stati=slot:IDLE,sessione:arming,sessione:running,slot:QUOTING2,slot:CANCELLING,slot:LOCKING,slot:DONE,slot:FLATTENING,sessione:done [COMPLETE]
   -       B2 x1: al FISCHIO nessuna posizione aperta: dopo il KO ogni selezione ha l'esposizione abbinata piatta (entro la tolleranza che il bot dichiara) e nessun ingresso vivo (`flatten_before_s`, bibbia 'mai posizioni aperte al KO'
   -            es. in gioco la selezione ('1.259819674', 58805) ha un'esposizione abbinata sbilanciata di 0.04 (se vince -0.93, se perde -0.97), oltre la tolleranza 0.02 del bot
   + OK  35797769 [chiusura-abbinata-in-parte]  tick=665941 decisioni=121012 azioni= 213 stati=slot:IDLE,sessione:arming,sessione:running,slot:QUOTING2,slot:CANCELLING,slot:LOCKING,slot:DONE,slot:FLATTENING,sessione:done [COMPLETE]
[base] IDENTICO (18 righe)
[ingresso-abbinato-in-parte] IDENTICO (22 righe)

## AUDIT_2026-10-08/decisioni_sera/replay_coordinatore/omega_35760084.txt  vs  AUDIT_2026-10-08/controllo_finale/omega/omega_35760084_tutti.txt
[apertura] DIVERSO: 3 righe solo nel riferimento, 0 solo nel mio
[paper] DIVERSO: 1 righe solo nel riferimento, 0 solo nel mio
[riavvio] DIVERSO: 1 righe solo nel riferimento, 0 solo nel mio

## AUDIT_2026-10-08/decisioni_sera/replay_coordinatore/mike_35760084.txt  vs  AUDIT_2026-10-08/controllo_finale/mike/mike_35760084_tutti.txt
[base] IDENTICO (24 righe)
[cap-stretto] IDENTICO (24 righe)

## AUDIT_2026-10-08/decisioni_sera/replay_coordinatore/safe_base_35760084.txt  vs  AUDIT_2026-10-08/controllo_finale/omega/safe_base_35760084_tutti.txt
[base] IDENTICO (94 righe)
[riavvio] IDENTICO (99 righe)

## AUDIT_2026-10-08/decisioni_sera/replay_coordinatore/tennis_swing_35790089.txt  vs  AUDIT_2026-10-08/decisioni_sera/replay_swing/swing_DOPO.txt
[gate-aperto] IDENTICO (12 righe)
[base] IDENTICO (11 righe)

## Lettura
- scalper: rifiuti-betfair-codici KO RC3 -> OK (D-2/D-2a; min_bet_skip x79 -> x78: l'abort al posto di uno skip), chiusura-abbinata-in-parte KO B2 0,04 -> OK (D-1); base e ingresso-abbinato-in-parte IDENTICI.
- omega: apertura/paper/riavvio righe di esito e note IDENTICHE; differiscono solo righe di log CRITICAL (una per processo worker: 3 qui, 22 nel tutti del cloud) e 2 righe 'posizione ridotta' che nel riferimento appartengono a uno scenario non rigiocato qui (uscita interfogliata dei worker).
- mike base/cap-stretto, safe_base base/riavvio: IDENTICI. tennis_swing gate-aperto/base: IDENTICI al DOPO del delegato.
