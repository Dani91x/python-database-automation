"""Stack live TENNIS dedicato (stream unico + bot + ordini) su tabelle ``tennis_*``.

Regola d'oro (richiesta esplicita utente): Tennis e Calcio sono sport diversi e NON
condividono MAI dati. Questo package scrive ESCLUSIVAMENTE tabelle ``tennis_*`` e
riusa VERBATIM le strategie tennis (``Betfair/stream/tennis_scalper``) + il feed
punteggio (``tennis_score``). Nessuna tabella/RPC del calcio viene toccata.

Ottimizzazione dati (requisito): UNA sola subscription flumine per evento tennis
seguito alimenta TUTTE le proiezioni (ladder + punteggio + now) e OSPITA i bot
armati sullo stesso stream — nessuna subscription Betfair duplicata, nessun REST
extra oltre al feed punteggio IPS.
"""
