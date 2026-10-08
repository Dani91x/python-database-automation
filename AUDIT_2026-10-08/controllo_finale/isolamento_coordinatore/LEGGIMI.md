# Isolamento fra scenari: ultimi due buchi chiusi (coordinatore cloud, 08/10)

Il banco e' UNICO (`banco_comune.py` + `certifica`). Ogni bot ha il suo innesto (`<bot>/tools/replay_registrazioni.py`)
che aggancia il SUO servizio di produzione al banco comune e, fra uno scenario e l'altro, svuota la memoria di processo di
quel servizio. Il controllo finale ha trovato due memorie non svuotate (solo note del referto, esiti identici):

1. Mike: `service._CONTO` (memoria W3a «di chi e' questo ordine», verifiche, versioni). Omega e Safe la svuotano gia'
   nel loro `svuota_le_cache` (`_CONTO.azzera()`); Mike no. Ora l'innesto di Mike chiama `S._CONTO.azzera()`.
2. Safe: l'avviso «scanner che non dichiara il flusso» (una volta per processo) e la cache dei lambda di Omega a
   orologio di parete (reperto D-13, prima azzerata solo negli scenari delle proposte). Ora a ogni scenario.

Prova (questa cartella): `mike 35760084 --scenari chiuso-fuori-app,ridotto-fuori-app` e
`safe_base 35760084 --scenari cap-stretto,bot-fermo,riavvio`, `--worker 1` contro `--worker 3`: `confronta_referti`
0 righe diverse; righe di esito identiche a `controllo_finale/mike` e `controllo_finale/omega/safe_base_*`.
Test: `Betfair/stream/tests/test_banco_isolamento_conto_2026_10_08.py` (3), falsificato: Mike senza `azzera` ->
rosso; Omega `svuota_le_cache` senza `_CONTO.azzera` -> rosso; Safe senza riarmo dell'avviso -> rosso; Safe con la
cache dei lambda azzerata solo per le proposte -> rosso.
