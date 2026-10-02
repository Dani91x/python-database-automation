# Isolamento dei test, terza parte (02/10/2026)

Ramo `test-isolamento-3`, preso da master. Una sola modifica, nel test; la produzione non è toccata.

STATO AL 14:30: fatto. Difetto riprodotto, corretto, falsificato e verificato su `Betfair/mike` intera. Manca solo la revisione del coordinatore.

## Il caso

`Betfair/mike/tests/test_mike_legge_canale_2026_09_23.py::test_1_interruttore_spento_chiamate_identiche_a_prima[None]`.

Il test fa due corse nello stesso processo (PRIMA e DOPO) e confronta le chiamate al DB.

**Causa.** `Betfair/mike/service.py:4461` (`_config_warn`) scrive la riga `config_warn` una sola volta per chiave. La memoria è `_CONFIG_WARNED`, definita a riga 76 e scritta a :4483. Quando `SAFE_PRE_KO_OU_HOURS` manca o vale 0, l'avviso esce solo nella prima corsa, e alla seconda manca → il confronto cade.

**Perché dipendeva dalla macchina.** Nel mio worktree il `.env` vero, letto alla raccolta, imposta la variabile, quindi il test era verde. Nell'ambiente del coordinatore mancava, e il test era rosso. Non l'ho riprodotto con l'ambiente così com'è, ma con `SAFE_PRE_KO_OU_HOURS=0` nell'ambiente del processo: 1 failed, 24 passed.

**Correzione.** In `_sequenza` (il test) aggiunto `S._CONFIG_WARNED.clear()` accanto all'azzeramento di `_NON_NOTO_AVVISATO` dell'isolamento 2. Le due corse partono così dallo stesso stato, qualunque cosa dica il `.env`.

## Falsificazione (`falsifica_test_isolamento_3.py` e `_out.txt`)

Esito: **TUTTO COME ATTESO**.

| Stato | `SAFE_PRE_KO_OU_HOURS` | Atteso | Ottenuto |
|---|---|---|---|
| con la correzione | 0 | verde | 25 passed |
| con la correzione | 3 | verde | 25 passed |
| con la correzione | assente (decide il `.env` vero) | verde | 25 passed |
| riga tolta | 0 | rosso | 1 failed, 24 passed |
| riga tolta | 3 | verde (senza avviso il difetto non si vede) | 25 passed |
| ripristinato | 0 | verde | 25 passed |

Lo sha256 del file ripristinato è verificato.

## Esecuzioni

| Cartella | `SAFE_PRE_KO_OU_HOURS` | Esito | Durata |
|---|---|---|---|
| `Betfair/mike` | dal `.env` | 1539 passed | 48,8 s |
| `Betfair/mike` | 0 | 1539 passed | 48,7 s |

## NON VERIFICATO

- La suite intera non l'ho lanciata: la modifica tocca un solo file di test.
- Non ho cercato in altri test di Mike lo stesso schema "due corse a confronto" esposto ad altre memorie una-volta.
