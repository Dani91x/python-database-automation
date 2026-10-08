# Riferimenti scalper calcio, tutti gli scenari, su 1ac69d0 (banco cloud, 08/10/2026)

Commit del codice: `1ac69d0` (feat(banco scalper): scavalco e rifiuti Betfair coi codici veri ...). Esecutore: sessione cloud, nessuna modifica al codice. Punto d'ingresso unico: `python -m Betfair.stream.backtest.certifica scalper_calcio <ev> --scenari <blocco> --worker 1`.

Macchina: `nproc` = 4, 15 GB RAM. Scenari: 51 (da `SCENARI_DESCRITTI`), divisi in 4 blocchi (round-robin) lanciati IN PARALLELO; prima 35797769, poi 35760084. Ogni scenario compare esattamente una volta per registrazione (51 + 51, verificato). Registrazioni: `registrazioni_banco/` decompresse in `_live_raw/` con lo script di `registrazioni_banco/LEGGIMI.md`. Entrambe COMPLETE.

## Esito in breve

- 35797769: OK 44, KO 5, NE 2. KO attesi: `chiusura-abbinata-in-parte` (B2), `rifiuti-betfair-codici` (RC3), `uscite-manuali-firmate` (UF2).
- 35797769: **KO NON attesi**: `riavvio` (**B1 x21**) e `rifiuti-betfair-codici-paper` (RC3 x1, stesso difetto della gemella live: probabilmente atteso per estensione, da confermare dal coordinatore).
- 35760084: OK 32, KO 1, NE 18. Unico KO `auto-live` (AL1, atteso). Il maker non fa NESSUNA azione su tutta la registrazione (azioni=0 negli scenari maker: OK a vuoto); la media under e' NE ovunque (filtro min size), gli scenari `media-clic-*` invece agiscono e sono OK.

### Il KO non atteso: `riavvio` su 35797769, B1 x21

> B1: nessun INGRESSO nuovo quando le aperture sono vietate ...  
> es. ingresso BACK 22 @1.69 per 25.0 creato a 1783706589578 ms, con il divieto 'missione_prematch' attivo da 1783704449466 ms

Contesto del referto: processo della sessione ucciso a 1783706402670 ms (posizione abbinata aperta: no), sessione RIARMATA dopo 120 s; la seconda sessione apre ingressi mentre il divieto `missione_prematch` e' attivo (21 casi). **Riproducibile**: rilanciato DA SOLO a macchina scarica (`scalper_35797769_riavvio_da_solo.txt`), stesso KO B1 x21, stesso istante 1783706589578: non e' un effetto del parallelo. Non indagato oltre (compito di sola esecuzione).

## Tabella scenario -> esito

Legenda: azioni = azioni del bot nel referto; controlli = controlli violati (codice x casi); per i NE il motivo.

| scenario | 35797769 | azioni | controlli violati / motivo | 35760084 | azioni | controlli violati / motivo |
|---|---|---|---|---|---|---|
| `base` | OK | 44 | - | OK | 0 | - |
| `paper` | OK | 44 | - | OK | 0 | - |
| `senza-missione` | OK | 246 | - | OK | 0 | - |
| `bot-fermo` | OK | 44 | - | OK | 0 | - |
| `kill-switch` | OK | 44 | - | OK | 0 | - |
| `esiti-ignoti` | OK | 44 | - | OK | 0 | - |
| `rifiuti-betfair` | OK | 56 | - | OK | 0 | - |
| `riavvio` | KO | 160 | B1 x21 (**NON atteso**) | OK | 0 | - |
| `chiusura-abbinata-in-parte` | KO | 213 | B2 x1 (atteso) | OK | 0 | - |
| `sniper` | OK | 44 | - | OK | 0 | - |
| `sniper-paper` | OK | 44 | - | OK | 0 | - |
| `sniper-uscite-auto` | OK | 44 | - | OK | 0 | - |
| `uscite-manuali` | OK | 239 | - | OK | 0 | - |
| `uscite-manuali-firmate` | KO | 64 | UF2 x1 (atteso) | OK | 0 | - |
| `auto-live` | OK | 44 | - | KO | 0 | AL1 x1 (atteso) |
| `media-under` | OK | 10 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475533: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-paper` | OK | 10 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475533: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-35` | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259819686: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475537: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-obiettivo-030` | OK | 10 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475533: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-rientri-1` | OK | 10 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475533: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-rischio-30` | OK | 10 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475533: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-tick-1` | OK | 19 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475533: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-riavvio` | OK | 10 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475533: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-rifiuti-betfair` | OK | 16 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475533: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-esiti-ignoti` | OK | 11 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475533: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-kill-switch` | OK | 2 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475533: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-bot-fermo` | OK | 2 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475533: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-liquidita-100` | OK | 10 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475533: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-under-35-liquidita-50` | OK | 9 | - | NE | 0 | - (la modalita' media under non ha piazzato NESSUN ordine su 1.259475537: filtro che l'ha fermata piu' spesso: liquidita' sotto il minimo al miglior prezzo (min si) |
| `media-clic-lontano` | OK | 11 | - | OK | 25 | - |
| `media-clic-lontano-paper` | OK | 11 | - | OK | 25 | - |
| `media-clic-lontano-filtri` | OK | 15 | - | OK | 25 | - |
| `media-clic-lontano-35` | OK | 24 | - | OK | 14 | - |
| `media-clic-finestra` | OK | 5 | - | OK | 10 | - |
| `media-clic-gioco` | OK | 2 | - | OK | 5 | - |
| `media-clic-gioco-35` | OK | 2 | - | OK | 5 | - |
| `media-clic-prima-del-gol` | OK | 22 | - | OK | 14 | - |
| `media-clic-prima-del-gol-35` | OK | 9 | - | OK | 9 | - |
| `media-clic-dopo-il-gol` | OK | 17 | - | OK | 15 | - |
| `media-clic-sospeso` | NE | 15 | - (ATTIVA ADESSO `sospeso`: nessun clic consegnato nel caso voluto (mercato SUSPENDED): consegne [('clic-1-1783711800082', True, None)]) | OK | 0 | - |
| `media-clic-prezzi-fermi` | OK | 0 | - | OK | 0 | - |
| `media-clic-doppio` | OK | 10 | - | OK | 15 | - |
| `media-clic-in-posizione` | OK | 10 | - | OK | 15 | - |
| `media-clic-riavvio` | OK | 11 | - | OK | 28 | - |
| `media-clic-tick-1` | OK | 38 | - | OK | 23 | - |
| `media-clic-tick-1-filtri` | OK | 34 | - | OK | 23 | - |
| `media-clic-due-clic` | OK | 4 | - | OK | 14 | - |
| `ingresso-abbinato-in-parte` | OK | 49 | - | NE | 0 | - (ingresso-abbinato-in-parte: nessun gruppo d'ingresso abbinato in parte (il guasto non ha mai avuto effetto: SV1-SV5 'non lo so')) |
| `ingresso-abbinato-in-parte-paper` | OK | 49 | - | NE | 0 | - (ingresso-abbinato-in-parte-paper: nessun gruppo d'ingresso abbinato in parte (il guasto non ha mai avuto effetto: SV1-SV5 'non lo so')) |
| `rifiuti-betfair-codici` | KO | 132 | RC3 x1 (atteso) | NE | 0 | - (rifiuti-betfair-codici: nessun gruppo d'ingresso abbinato in parte (il guasto non ha mai avuto effetto: SV1-SV5 'non lo so')) |
| `rifiuti-betfair-codici-paper` | KO | 132 | RC3 x1 (**NON atteso**) | NE | 0 | - (rifiuti-betfair-codici-paper: nessun gruppo d'ingresso abbinato in parte (il guasto non ha mai avuto effetto: SV1-SV5 'non lo so')) |

## Blocchi e tempi (wall clock, `time`)

| blocco | scenari | 35797769 | 35760084 |
|---|---|---|---|
| 1 | base, kill-switch, chiusura-abbinata-in-parte, uscite-manuali, media-under-paper, media-under-rischio-30, media-under-esiti-ignoti, media-under-35-liquidita-50, media-clic-lontano-35, media-clic-prima-del-gol, media-clic-prezzi-fermi, media-clic-tick-1, ingresso-abbinato-in-parte-paper | 23m16.064s | 4m28.379s |
| 2 | paper, esiti-ignoti, sniper, uscite-manuali-firmate, media-under-35, media-under-tick-1, media-under-kill-switch, media-clic-lontano, media-clic-finestra, media-clic-prima-del-gol-35, media-clic-doppio, media-clic-tick-1-filtri, rifiuti-betfair-codici | 22m41.925s | 5m9.823s |
| 3 | senza-missione, rifiuti-betfair, sniper-paper, auto-live, media-under-obiettivo-030, media-under-riavvio, media-under-bot-fermo, media-clic-lontano-paper, media-clic-gioco, media-clic-dopo-il-gol, media-clic-in-posizione, media-clic-due-clic, rifiuti-betfair-codici-paper | 20m28.614s | 4m33.405s |
| 4 | bot-fermo, riavvio, sniper-uscite-auto, media-under, media-under-rientri-1, media-under-rifiuti-betfair, media-under-liquidita-100, media-clic-lontano-filtri, media-clic-gioco-35, media-clic-sospeso, media-clic-riavvio, ingresso-abbinato-in-parte | 20m40.073s | 4m32.445s |

Totale a parete: 35797769 dalle 13:34 alle 13:58 UTC (~24 min, blocco piu' lungo 23m16s); 35760084 dalle 13:58 alle 14:03 UTC (~5 min). Il banco segnala LENTO (sopra il tetto di 600 s) i quattro blocchi della 35797769: e' un avviso, l'esito non cambia; i blocchi sono serie di 12-13 replay. Riprova isolata di `riavvio`: 47.8 s.

## File

- `scalper_<ev>_blocco<k>.txt` / `.err`: referto completo e stderr (log del bot + `time`) di ogni blocco.
- `scalper_35797769_riavvio_da_solo.txt` / `.err`: riprova isolata del KO non atteso.
