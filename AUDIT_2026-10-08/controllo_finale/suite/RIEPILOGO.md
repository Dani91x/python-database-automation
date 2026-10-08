# Controllo finale: suite complete su d01de76 (cloud, 08/10/2026)

- sha: `d01de76ea591a57850eff29063fa969abbf6559f` (verificato al passo 0: `git log --oneline -1` ->
  `d01de76 docs: documento di verifica, riga e decisioni del cantiere 11, metodo con --worker 3`)
- ramo: `claude/blissful-sagan-hri7o6-finale-suite` (creato da quella sha, nessuna modifica al codice)
- nproc 4 · Python 3.13.16 · pytest 9.1.1 · Node v22.22.0
- Nessun replay in questa sessione.

## Ambiente (da sapere prima di leggere i numeri)

Il container non aveva le dipendenze Python del progetto: la prima corsa `-n 4` e' finita con
**1016 errori di raccolta, 1 skipped, 0 test eseguiti** (`ModuleNotFoundError: No module named
'flumine'`). Uscita intera conservata in `pytest_betfair_n4_SENZA_DIPENDENZE.txt`. E' un difetto
d'ambiente, non del codice: ho installato `pytest-xdist` e `pip install -r requirements.txt`
(flumine 2.13.11, betfairlightweight 2.23.2, ...) **solo nel container**; le versioni sono in
`pip_freeze.txt`. Tutte le corse sotto sono successive all'installazione.

## Esiti

| # | Comando | Esito | Numeri esatti | Tempo |
|---|---|---|---|---|
| 1a | `python -m pytest Betfair/ -q -p no:cacheprovider -n 4` | verde (exit 0) | 11295 passed, 87 skipped, 6 xfailed, 14 warnings | 83 s (pytest 82.27 s) |
| 1b | `python -m pytest Betfair/ -q -p no:cacheprovider` (seriale) | verde (exit 0) | 11295 passed, 87 skipped, 6 xfailed, 14 warnings | 244 s (pytest 239.17 s) |
| 2 | `python -m pytest tools/ -q -p no:cacheprovider` | verde (exit 0) | 17 passed | 54 s |
| 3 | `python -m pytest test_catchup_*.py -q -p no:cacheprovider` | verde (exit 0) | 90 passed | 3 s |
| 4a | `npm ci` (node_modules mancava) | ok (exit 0) | 360 pacchetti aggiunti | 17 s |
| 4b | `npx tsc -p tsconfig.app.json --noEmit` | verde (exit 0) | **0 errori** (uscita vuota) | 34 s |
| 4c | `npx vitest run` | verde (exit 0) | 367 file passati, 10 saltati (377); 5447 test passati, 51 saltati (5498) | 308 s |
| 4d | `npm run build` | verde (exit 0) | `built in 16.79s` (solo l'avviso sulla dimensione dei chunk) | 18 s |

- **Parallela e seriale coincidono**: 11295 / 87 / 6 / 14 in entrambe.
- Confronto: seriale del coordinatore sulla 66fee096 = 11273 passed; qui +22 (i test del cantiere 11
  aggiunti dalla cima). Riferimento b4d91ed = 11247 passed + 1 failed.
- Frontend identico al riferimento b4d91ed (5447/51, 367/10).
- `git status` dopo build e suite: solo questa cartella non tracciata (la build non tocca file tracciati).

Ordine: 1a, poi 1b in background con 2 e 3 in primo piano; il frontend (4b-4d) solo DOPO la fine
della seriale, per non caricare la CPU durante i test sensibili ai tempi.

## Reperto aperto: il test del rosso di b4d91ed resta non deterministico DA SOLO

Nessun rosso nelle suite. Per scrupolo ho rilanciato da solo il test che era rosso su b4d91ed
(corretto, secondo il riferimento, in 71e56de, che **e' antenato** di d01de76):

`Betfair/stream/tests/test_frammenti_mercato_2026_09_28.py::test_auto_follow_rifiuto_betfair_rientra_e_dichiara`

- 1 giro esplorativo: **rosso**; 1 giro successivo: verde.
- Poi 23 giri da solo (`rilanci_test_auto_follow_rifiuto.txt`, uscita intera di ogni giro):
  **17 verdi, 6 rossi** (rossi ai giri 6, 8, 9, 12, 14, 23).
  Primi 3 giri del brief: giro 1 verde, giro 2 verde, giro 3 verde.
- Il suo file intero, da solo: 38 passed.
- Nelle due suite complete (parallela e seriale) e' passato.

Il rosso, per intero (giro 6):

```
>       assert s["eventi_auto"] == 67 and s["partite_fuori_n"] == 0
E       assert (45 == 67)
Betfair/stream/tests/test_frammenti_mercato_2026_09_28.py:526: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  flumine.streams.streams:streams.py:268 Client u now paper trading
WARNING  betfairlightweight.streaming.listener:listener.py:27 [Listener: 20002]: stream already registered, replacing data
ERROR    betfairlightweight.streaming.listener:listener.py:210 [None: 1]: MAX_CONNECTION_LIMIT_EXCEEDED: finto
WARNING  Betfair.stream.frammenti_mercato:frammenti_mercato.py:519 [frammenti] APERTO frammento 30000 con 88 mercati (connessione in piu')
WARNING  Betfair.stream.frammenti_mercato:frammenti_mercato.py:543 [frammenti] CHIUSO frammento 30000 (88 mercati): connessione rifiutata: MAX_CONNECTION_LIMIT_EXCEEDED
WARNING  Betfair.stream.auto_follow:auto_follow.py:857 [auto-follow] capacita' della connessione di mercato: 540 -> 180 mercati
WARNING  Betfair.stream.auto_follow:auto_follow.py:803 [auto-follow] ESPULSO 35000000 (4 mercati, ...)   (x22, 35000000..35000021)
WARNING  betfairlightweight.streaming.listener:listener.py:27 [Listener: 20003]: stream already registered, replacing data
WARNING  Betfair.stream.auto_follow:auto_follow.py:1095 [auto-follow] 22 partite idonee NON seguite (capacita' 180 mercati, 1 connessioni): 35000000, ...
WARNING  Betfair.stream.auto_follow:auto_follow.py:857 [auto-follow] capacita' della connessione di mercato: 180 -> 540 mercati
WARNING  Betfair.stream.auto_follow:auto_follow.py:1095 [auto-follow] 22 partite idonee NON seguite (capacita' 540 mercati, 1 connessioni): 35000000, ...
FAILED Betfair/stream/tests/test_frammenti_mercato_2026_09_28.py::test_auto_follow_rifiuto_betfair_rientra_e_dichiara
1 failed in 0.13s
```

Osservazione (non verificata, nessun codice toccato): rispetto a b4d91ed il sintomo e' cambiato.
Li' la capacita' restava 180; qui dopo la pausa la capacita' **torna a 540**, ma il secondo
frammento non risulta aperto (`1 connessioni`) entro i due `giro()` del test, e le 22 partite
restano fuori. La correzione 71e56de sull'`id()` riciclato non basta a rendere deterministico il
test: resta una seconda fonte di variabilita' (candidata gia' indicata su b4d91ed: il misto di
`time.monotonic()` reale con l'orologio finto). Va a chi possiede il dominio di
`Betfair/stream/frammenti_mercato.py` / `auto_follow.py`.

## File

`pytest_betfair_n4.txt`, `pytest_betfair_seriale.txt`, `pytest_tools.txt`, `pytest_catchup.txt`,
`npm_ci.txt`, `tsc.txt`, `vitest.txt`, `build.txt`, `rilanci_test_auto_follow_rifiuto.txt`,
`pytest_betfair_n4_SENZA_DIPENDENZE.txt` (corsa senza dipendenze), `pip_freeze.txt`.
Ogni uscita chiude con `EXIT=<codice> SECONDI=<durata>`.

## Verifica del coordinatore cloud (08/10)
- Numeri riletti: Betfair 11295/87/6 identici in parallelo e in serie; tools 17; catchup 90; tsc 0; vitest 5447/51; build ok.
- REPERTO DEL TEST RISOLTO (causa provata, non un «flaky»): `AutoFollow._giro_feed` rilegge il feed solo se e' passato
  `feed_s` di orologio REALE (nel test 0,001 s). Il giro legge il feed PRIMA di aggiornare la capacita': dopo la pausa il
  primo giro legge il feed a capacita' 180 e poi la porta a 540; il secondo giro, se cade entro 1 ms dal primo (macchina
  veloce), non rilegge il feed e le 22 partite restano fuori. PROVA DETERMINISTICA: con l'orologio dell'auto-follow fermo
  (`af._ora = lambda: 1000.0`) il test e' SEMPRE rosso; con la correzione SEMPRE verde; togliendo la correzione torna rosso.
  Correzione SOLO NEL TEST (`af.feed_s = 0.0`: il feed si rilegge a ogni giro, come il test presume). Il codice di produzione
  non cambia: in produzione `feed_s` = 30 s e le partite rientrano alla lettura successiva del feed (al piu' 30 s dopo che la
  capacita' torna), comportamento dichiarato. Dopo: 30/30 verdi da solo, file dei frammenti 40/40.
- L'uscita della corsa SENZA dipendenze (2,6 MB, solo errori di raccolta) e' ridotta a testa e coda; l'intera resta sul ramo
  della sessione.
