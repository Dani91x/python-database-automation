# ONDATA 1 — Brief comune a tutti gli agenti (09/10/2026)

Coordinatore: sessione cloud sul ramo `claude/architettura-tappa0`. Leggi questo file per intero prima di scrivere una riga.

## 0. Cosa vuole l'utente (parole sue, vincolanti)

- «Un software identico a quello dei competitor nel backend e nella struttura: l'app desktop deve funzionare esattamente come la
  loro; le nostre funzionalita' extra sono un vantaggio in piu'.»
- «Prima tutta la parte Betfair, con il database locale; il cloud fa le operazioni che fa gia'.»
- «Il database locale l'utente NON deve vederlo, NON deve usarlo: totalmente automatico e integrato nell'app.»
- «Il database cloud NON deve perdere nessun dato rispetto a oggi.»
- «Struttura a comparti: se devo cambiare un componente ci metto pochi minuti, non giorni.»
- «Massima cura del codice, massima documentazione. Nessuna funzionalita' persa, nessuna regressione.»
- **«Niente andra' su master finche' non siamo certi che funzioni allo stesso modo O MEGLIO.»**

## 1. Le regole dell'ondata 1 (non negoziabili)

1. **Nessun file esistente si modifica.** Si scrive SOLO nei file del proprio dominio (§3), tutti nuovi, sotto `Betfair/nucleo/`,
   `ARCHITETTURA_2026-10/ondata1/<ID>/` e (solo W1-G1) `migrations/`. Il codice di produzione di oggi non cambia di un byte: l'aggancio
   all'app e' l'ONDATA 2 (dopo la tappa 0, una tappa alla volta, dietro `ARCH_<COMPONENTE>=vecchio|ombra|nuovo`). Se per il tuo
   comparto serve toccare un file esistente, NON farlo: scrivi nel referto la sezione «Aggancio proposto» con file:riga e la modifica.
2. **I contratti sono fissi.** `Betfair/nucleo/comuni.py` e i `contratto.py` dei quattro comparti li ha scritti il coordinatore dal
   piano (04 par. 3). Non modificarli. Se serve un'estensione, implementala in un tuo file come tipo separato e proponila nel referto.
3. **Riuso, mai copia.** Dove oggi esiste gia' la logica (funzioni pure, regole .it, firme del ladder, parsing dei punteggi, classi della
   libreria betfairlightweight/flumine) il comparto la IMPORTA. Se un pezzo va estratto da un file grande, il nuovo modulo lo riscrive solo
   se un TEST DI PARITA' prova che vecchio e nuovo danno lo stesso risultato sugli stessi ingressi (vedi punto 5); niente copie silenziose.
4. **Strategie intoccabili.** Nessuna soglia, stake, tetto, gamba o regola di un bot cambia. Paper e live mai sommati. Calcio e tennis mai
   mischiati. Se trovi una divergenza di comportamento fra copie del codice di oggi (es. due definizioni dei minimi .it), NON sceglierne una:
   scrivila nel referto come «Divergenza per l'utente».
5. **Parita' provata, non dichiarata.** Ogni funzione nuova che ha un equivalente di oggi ha un test che confronta vecchio e nuovo sugli
   stessi ingressi: ingressi VERI dove esistono (registrazioni in `registrazioni_banco/`, da scompattare in `_live_raw/<id>/`, fuori da git)
   e casi limite. Uguale = identico, non «simile». Migliore = solo dove e' misurabile e dichiarato (es. latenza), mai sul risultato di un bot.
6. **Test che sanno diventare rossi.** Ogni test nuovo va falsificato: rompi il codice, mostra il rosso, ripristina (sha256 del file uguale).
   Finti con le identiche chiavi e tipi del vero: oggetti VERI di betfairlightweight per book e ordini; client Supabase vero su
   `httpx.MockTransport` (modello: `Betfair/scores/` e i test `test_catchup_rete_2026_10_08.py`), mai dizionari inventati.
7. **Niente rete, niente DB vero, niente Betfair vero, niente processi nuovi.** Importare un modulo del nucleo non deve aprire file, socket
   o thread. Thread e file solo dentro metodi espliciti (`avvia`, `apri`), chiusi da `ferma`/`chiudi`, provati nei test.
8. **Qualita' del codice**: Python 3.13, `from __future__ import annotations`, tipi su tutte le firme pubbliche, funzioni corte, niente
   stato globale mutabile non dichiarato, nessuna eccezione inghiottita in silenzio (si logga col motivo), codice ASCII-only, commenti e
   docstring in italiano, stile del codice circostante (vedi `Betfair/monitor/` come esempio recente e pulito).
9. **Documentazione**: (a) docstring di modulo che dice scopo, entrate, uscite, cosa NON fa; (b) il file `Betfair/nucleo/<comparto>/doc/<ID>_<NOME>.md`
   con lo schema del `COSA_FA.md` (04 par. 2.4: 1 scopo, 2 entrate, 3 uscite, 4 dipendenze ammesse, 5 funzionalita' coperte con gli id di
   `01_FUNZIONALITA.md` e il test che prova ognuna, 6 interruttore previsto, 7 come si sostituisce, 8 come si prova da solo, 9 misure,
   10 voci di `PROCESSO_STANDARD_BOT.md` par. 6/7 sollecitate o ⊘ con causa). Il coordinatore unira' i doc nel `COSA_FA.md` della cartella.
10. **Dipendenze ammesse** (04 par. 2.3): solo `nucleo/betfair/` importa betfairlightweight per sessione/REST/stream; solo `nucleo/dati/`
    (e `db_client.py`) importa supabase; `ordini/` puo' importare `betfair/` e `dati/` (solo i contratti, fra comparti diversi);
    `stato_partita/` puo' importare `betfair/`. Nessun comparto importa un bot. Il codice di oggi si importa (riuso) solo per funzioni pure.
11. **Criteri di accettazione per riferimento**: `PROCESSO_STANDARD_BOT.md` par. 6 (copertura del banco: dati di mercato, scanner vero,
    servizio intero a cadenza reale, ciclo di vita dell'ordine con parziali e bet delay, persistenza e UI, concorrenza, scenari,
    falsificazione, referto riproducibile) e par. 7 (catalogo dei 35 errori gia' visti): nel referto, per il tuo comparto, quali voci hai
    sollecitato e quali sono ⊘ con la causa.
12. **Parita' con i competitor e limiti Betfair** (`02_COMPETITOR.md` par. 3 e 6): 200 punti di peso per `listMarketBook`, 3 richieste
    concorrenti per conto, login max 100/min (ban 20 min), sessione .it 20 min (keepAlive), 200 mercati per sottoscrizione, una
    sottoscrizione SOSTITUISCE la precedente, `heartbeatMs` 500-5000, ripresa con `initialClk`/`clk`, segmentazione, `customerStrategyRef`
    15 caratteri, `customerRef` 32 caratteri (dedup 60 s), minimi .it (2,00 EUR, passi 0,50), ordini e mercato su due sistemi senza garanzia
    d'ordine d'arrivo fra `ocm` e `mcm`.

## 2. Git e prove

- PRIMA COSA: `git checkout -B <ramo del tuo ID> <commit base indicato nel tuo brief>`. Commit SOLO sul tuo ramo, mai push.
- Mai `git add -A`: aggiungi i file per nome. Coda di ogni messaggio di commit:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` e `Claude-Session: https://claude.ai/code/session_016SiD8k9vaLT7Lgo5DGrMRv`.
- La macchina e' condivisa da 7 agenti: lancia i TUOI test quanto vuoi, la suite intera `python -m pytest Betfair/ -q -p no:cacheprovider`
  al massimo DUE volte (a meta' e alla fine), con i numeri nel referto. Nessun replay del banco in questa ondata salvo dove il tuo brief lo
  chiede esplicitamente.
- Dipendenze Python gia' installate; se ne serve una nuova, NON installarla: scrivila nel referto.

## 3. I domini (file esclusivi; nessuno scrive nei file di un altro)

| ID | Comparto | File tuoi (tutti nuovi) | Test | Doc e referto |
|---|---|---|---|---|
| W1-A1 | A sessione e REST | `nucleo/betfair/{sessione,rest,limiti,salute}.py` | `nucleo/betfair/tests/test_a1_*.py` | `nucleo/betfair/doc/A1_SESSIONE_REST.md`, `ondata1/W1-A1/` |
| W1-A2 | A stream e ladder | `nucleo/betfair/{profili,flusso,flusso_ordini_conto,ladder}.py` | `nucleo/betfair/tests/test_a2_*.py` | `nucleo/betfair/doc/A2_FLUSSI_LADDER.md`, `ondata1/W1-A2/` |
| W1-C1 | C porta ordini | `nucleo/ordini/{porta,adattatore_comando,minimi,controlli,eventi}.py`, `nucleo/ordini/esecutori/*.py` | `nucleo/ordini/tests/test_c1_*.py` | `nucleo/ordini/doc/C1_PORTA.md`, `ondata1/W1-C1/` |
| W1-C2 | C libro ordini e riconciliazione | `nucleo/ordini/{attribuzione,libro_conto,pnl_mercato,riconciliazione}.py` | `nucleo/ordini/tests/test_c2_*.py` | `nucleo/ordini/doc/C2_LIBRO_RICONCILIAZIONE.md`, `ondata1/W1-C2/` |
| W1-G1 | G archivio locale e postino | `nucleo/dati/{percorso,schema_locale,archivio,postino,riconcilia}.py`, `migrations/architettura_uid_ombra_2026-10-09.sql` | `nucleo/dati/tests/test_g1_*.py` | `nucleo/dati/doc/G1_ARCHIVIO_POSTINO.md`, `ondata1/W1-G1/` |
| W1-G2 | G registro e cloud | `nucleo/dati/{registro,cloud,cache_cloud}.py` | `nucleo/dati/tests/test_g2_*.py` | `nucleo/dati/doc/G2_REGISTRO_CLOUD.md`, `ondata1/W1-G2/` |
| W1-B | B stato partita | `nucleo/stato_partita/{servizio,calcolo,freschezza}.py`, `nucleo/stato_partita/adattatori/*.py` | `nucleo/stato_partita/tests/test_b_*.py` | `nucleo/stato_partita/doc/B_STATO_PARTITA.md`, `ondata1/W1-B/` |

Le cartelle `tests/`, `doc/`, `esecutori/`, `adattatori/` e i loro `__init__.py` esistono gia' (li ha creati il coordinatore).

## 4. Il referto (`ARCHITETTURA_2026-10/ondata1/<ID>/REFERTO.md`, committato)

1. Cosa hai costruito (file:riga dei punti chiave) e cosa NON fa.
2. Contratto: quali protocolli implementi; estensioni proposte (se servono).
3. Parita': tabella «funzione di oggi (file:riga) -> funzione nuova -> test -> esito su ingressi veri e casi limite».
4. Migliorie misurate (solo dove misurabili e dichiarate: latenze, chiamate, memoria) con lo strumento.
5. Test e falsificazioni: numeri (verdi, mutazioni rosse/totali, ripristino con sha256), suite intera.
6. Funzionalita' di `01_FUNZIONALITA.md` coperte (id) e quelle che restano al vecchio codice.
7. PSB par. 6/7: voci sollecitate o ⊘ con causa.
8. Aggancio proposto per l'ondata 2: file:riga da toccare, interruttore, ombra, criterio di «uguale o meglio».
9. Divergenze per l'utente, rischi, dubbi. Mai nascosti.

## 5. Dopo la consegna

Il coordinatore rilegge il diff, rilancia i tuoi test, prova mutazioni sue e fa attaccare il codice da un revisore indipendente. Solo dopo
il tuo ramo entra nel ramo dell'architettura. Su master non entra nulla fino all'ondata 2, certificata, firmata dal PC e approvata
dall'utente.
