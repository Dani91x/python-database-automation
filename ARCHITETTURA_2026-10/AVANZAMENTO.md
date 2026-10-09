# AVANZAMENTO DELLA MIGRAZIONE — punto d'ingresso unico (aperto il 09/10/2026)

Ordine dell'utente (09/10): «tutte si, parti tu con quello che puoi fare; aggiorna il documento che siamo partiti con la fase 0,
non voglio ripetere le cose 100 volte: ad ogni sessione andremo avanti».

**Regola per ogni sessione (cloud o PC)**: si legge QUESTO file per primo (poi l'ultima sezione di `CRONOSTORIA.md`), si riparte
dalla prima riga «da fare» della tabella delle tappe, e a fine lavoro si aggiorna la tabella e il registro qui sotto. Il piano non
si rimette in discussione: le tappe, le regole (§0) e le decisioni sono in `05_PIANO_DI_MIGRAZIONE.md`; il riassunto per l'utente
in `06_RIEPILOGO_PER_L_UTENTE.md`. Le decisioni gia' prese NON si richiedono all'utente.

## Obiettivo (parole dell'utente, 09/10)

- Tutto cio' che e' Betfair vive nell'app desktop, «esattamente come i competitor»: nessun database nel percorso
  Betfair -> decisione -> ordine; stato vivo in memoria + archivio locale (SQLite) per i soldi; postino verso il cloud.
- Il database cloud serve solo agli algoritmi, alle analisi pre-partita e ad archiviare tutto.
- La UI resta questa; cambia cio' che c'e' dietro. Nessuna funzionalita' persa (le 970 voci di `01_FUNZIONALITA.md`).
- Metodo: stessa repo, cartelle nuove (`Betfair/nucleo/`, `Betfair/bots/`), un pezzo alla volta, prima in ombra accanto al
  vecchio, interruttore e ritorno; il cervello dei bot non si tocca (impronta della strategia = 0 differenze).
- Ogni funzionalita' o bot NUOVO si costruisce solo nella struttura nuova.
- Priorita' dell'utente dentro il piano: il ladder di Trading «come un tool professionale» (tutti gli ordini del conto, di chiunque,
  con P&L completo): arriva con la porta unica degli ordini (T10-T11) via stream ordini del conto in sola lettura.

## Decisioni dell'utente

| Data | Decisione | Esito |
|---|---|---|
| 09/10 | Le 7 che bloccano la tappa 0 (05 §8.1): U-62 ora di Windows + PC sveglio + avvio al login; U-32 finto di Omega corretto prima del congelamento; U-27 baseline di Mike e registrazioni COMPLETE aggiuntive; U-44 3-5 partite tennis nel repo; U-37 commit dei 4 documenti; U-59 le sole 3 tolleranze dell'ombra; U-60 misurare i 120 ms | **TUTTE SI'** (U-60: misurarli) |

Le altre 79 decisioni (05 §8.2-8.6) si portano all'utente solo quando la tappa che le richiede sta per partire.

## Tappe

Stato: `da fare` · `in corso (chi)` · `in verifica PC` · `fatta (commit, data)`.

| Tappa | Contenuto | Chi | Stato |
|---|---|---|---|
| T0A | Modulo «Salute» + misure mancanti + referto 24 h | cloud (codice) + PC (migrazione `monitor_metrics`, 24 h app accesa) | in corso (cloud, 09/10) |
| T0B (1)-(3) | Cantieri 15, 11, 7 del banco | cloud | fatta (fusi su master entro il 09/10, `CRONOSTORIA.md` 08/10) |
| T0B (4) | Finto di Omega con la firma del vero (`aggregates(..., mode)`), referto prima/dopo | cloud | in corso (cloud, 09/10) |
| T0B (5) | 3-5 partite tennis in `registrazioni_banco/` (U-44) + registrazioni calcio COMPLETE aggiuntive per Mike (U-27) | PC | da fare (PC) |
| T0B (6) | Commit dei 4 documenti (U-37) + testo della Base allineato al 25/09 | PC | da fare (PC) |
| U-62 | Ora di Windows, niente sospensione, avvio al login (app spenta o bot flat) | PC + utente | da fare (PC) |
| U-60 | Misura dei 120 ms delle letture REST del banco | PC | da fare (PC) |
| T0C | Cassetta, ombra (`--ombra`), `TOLLERANZE.md`, `congela`, determinismo, impronte, manifesto | cloud (strumenti e baseline calcio) + PC (tennis, firma) | in corso (cloud: SOLO strumenti, 09/10); baseline e manifesto DOPO T0B (4)-(6) |
| T1..T26 | Come in 05 §2 | | da fare |

## Registro (una riga per evento, la piu' recente in fondo)

- 09/10 — Utente: tutte e 7 le decisioni della tappa 0 = si'. Aperto questo file. Cloud (sessione `claude/sweet-hypatia-t4bmna`)
  avvia in parallelo T0A (modulo Salute), T0B (4) (finto di Omega) e T0C (solo strumenti: cassetta, ombra, tolleranze, congela,
  con prova di innocuita', falsificazione e determinismo; nessuna baseline congelata finche' T0B non e' completa).
  Al PC: U-62, U-60, T0B (5)-(6) (testo nella conversazione e nel blocco del 09/10 di `CRONOSTORIA.md`).

## Punto di ripresa

Prossima sessione: leggere i referti delle tre consegne del 09/10 (cartella `ARCHITETTURA_2026-10/tappa0/`), verificarle e
integrarle; poi, appena il PC chiude T0B (5)-(6) e U-62/U-60, produrre le baseline (due volte ciascuna) e il manifesto di T0C.
Dopo T0C: T1/T2/T3 (05 §3, grafo delle dipendenze).
