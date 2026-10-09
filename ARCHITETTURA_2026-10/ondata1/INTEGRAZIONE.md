# Ondata 1 - integrazione di W1-G1 e W1-C1 (09-10/10/2026)

Ramo `integrazione/w1-g1-c1`, nato da `d88fc9d1` (merge di W1-G1 sul ramo dell'architettura, che conteneva gia'
W1-G2, W1-B, W1-A1, W1-A2, W1-C2). Lavoro di un agente di integrazione interrotto due volte dal riavvio del
container; il lavoro rimasto in sospeso e' stato salvato dal coordinatore (`b9b19603`, WIP) e ripreso. La verifica
finale, la misura di latenza e questo referto sono del coordinatore.

## 1. Commit

| Commit | Cosa | Perche' |
|---|---|---|
| `d88fc9d1` | merge di W1-G1 (archivio locale e postino) | tre revisioni indipendenti + quattro giri di correzioni |
| `891cc357` | registro W1-G2 aggiornato per W1-G1: `postino_versioni`, RPC del postino (`postino_consegna`, `postino_impronte`, `postino_confronta_ombra`), eccezione `public` (falso positivo degli EXECUTE dinamici `format('%I.%I', 'public', ...)`), golden delle chiavi naturali con `uid` | la guardia di copertura del registro era rossa: e' il suo lavoro (il cloud non perde nulla perche' ogni scrittura e' dichiarata) |
| `609fe25b` | merge di W1-C1 (porta degli ordini) | tre revisioni indipendenti + verifiche del coordinatore |
| `b9b19603` | (WIP) `registro.TABELLE_SOLO_LOCALI` (`ordini_ref_visti`, `ordini_seq`) in `stato_denaro`; `archivio.spec()` le riconosce; fixture finto/vero nei test di C1 | le tabelle della porta stanno SOLO sul PC |
| `2d04658f` | le tabelle solo locali non vanno MAI al cloud, tre difese: l'archivio non le mette in outbox; il postino le manda in dead_letter `registro` senza chiamate; `ClienteCloud.rpc` rifiuta `postino_consegna` con una `p_tabella` non registrata (o la sua `_ombra`) prima della rete; la riconciliazione le salta | verifica del WIP: la nota del registro "il client rifiuta le altre" era diventata falsa |
| `cdfd1785` | finto `_ArchivioMemoria` identico al vero; test di contratto finto/vero sulle stesse operazioni; tutti i test della porta girano con finto E con `ArchivioLocale` vero | il difetto bloccante di W1-C1 (seconda revisione) era nascosto da un finto piu' capace del vero |
| `4b95e39a` | falsificazione dell'integrazione: `falsifica_integrazione.py`, 21/21 rosse, sha256 ripristinati | prova che i test nuovi sanno diventare rossi |

## 2. Prove (rieseguite dal coordinatore)

- `python -m pytest Betfair/nucleo -q -p no:cacheprovider`: **1.359 verdi**, 14 saltati (test PostgreSQL senza PG).
- Falsificazione dell'agente: **21/21 rosse**, 21/21 ripristinate (`falsifica_integrazione.txt`).
- Mutazione del coordinatore: in `archivio._in_outbox` la guardia delle solo locali tolta (`if False:`) ->
  2 test rossi; ripristino con sha256 identico.
- Latenza della porta sull'`ArchivioLocale` VERO integrato (`W1-C1/latenza_archivio_vero.py`, 1.000 ordini):
  invia nuovi p50 0,585 ms, p95 0,961, p99 1,266, max 2,040; doppioni p50 0,005 ms; `Archivio.leggi` di un ref
  assente p50 0,007 ms. Il test di latenza logica del motore di oggi chiede < 20 ms.
- Suite intera: vedi AVANZAMENTO (eseguita dal coordinatore prima del push).

## 3. Differenze trovate fra finto e vero

Il finto dei test di C1 e' stato portato alla semantica del vero di G1 (`cdfd1785`): transizione su riga assente =
False, colonna di stato unica `status`, `scrivi` che fonde le colonne, cartella per istanza. Il test di contratto
confronta finto e vero sulle stesse operazioni: un'eventuale capacita' del finto che il vero non ha lo rende rosso.

## 4. Cosa resta per l'ondata 2

- Le tabelle solo locali sono dichiarate in `registro.TABELLE_SOLO_LOCALI` (fuori dal registro del cloud).
- Le decisioni dell'utente sono in `DECISIONI_PER_L_UTENTE.md` (13 voci).
- Nessun codice di produzione di oggi e' stato toccato: l'aggancio e' l'ondata 2, dietro `ARCH_<COMP>`.
