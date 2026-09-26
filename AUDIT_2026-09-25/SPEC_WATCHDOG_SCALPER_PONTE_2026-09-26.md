# SPEC — watchdog per scalper-service e ponte tennis (per admin-26, `desktop/main.js`)

Cantiere FIX-C «resilienza rete», 26/09/2026, delegato Opus della sessione B.
`desktop/main.js` e `Betfair/stream/watchdog.py` sono di admin-26: qui c'è solo la
specifica. Io non li ho toccati. Il lato FIGLIO è già pronto nei miei file (sez. 4).

## 1. Stato di oggi (verificato su `origin/master` `3df556e`, con K2-LOG-FIGLI e `messaggio_crash` già dentro)

| figlio | riga `main.js` | watchdog | chi lo rilancia se muore |
|---|---|---|---|
| runner calcio, runner tennis, scanner, Omega, Safe bot, Mike | 365, 366, 381, 388, 394, 399 | sì, `python -m Betfair.stream.watchdog [-- modulo]` | il watchdog: backoff 10→300 s, al massimo 5 riavvii all'ora |
| **scalper-service** | **369**: `['-m','Betfair.stream.scalper.scalper_service']` | **no** | nessuno: `child.on('exit')` scrive solo il log |
| **ponte tennis** | **375**: `['-m','Betfair.stream.tennis_live.tennis_bot_service','--bridge-only']` | **no** | nessuno |

Cosa succede oggi se muoiono:
- **scalper-service**: niente auto-mode, niente supervisione delle sessioni (spawn, orfane,
  stop) e nessun avviso. Le sessioni già vive continuano da sole, ma nessuno riceve più
  gli stop dalla UI: la riga resta in `stopping` e solo la sessione se ne accorge.
- **ponte tennis**: lo «ferma» della UI non diventa più `stopping` (lo scrive il ponte in
  `tennis_bot_service.py:555, 597` su master), quindi i bot restano armati sul runner. Non si arma
  più niente di nuovo e il battito della UI invecchia.

## 2. Modifica richiesta a `desktop/main.js` (due righe)

```js
// 369
spawnRunner('scalper-service', ['-m', 'Betfair.stream.watchdog', '--', 'Betfair.stream.scalper.scalper_service']);
// 375
spawnRunner('tennis-bot-service', ['-m', 'Betfair.stream.watchdog', '--', 'Betfair.stream.tennis_live.tennis_bot_service', '--bridge-only']);
```

`watchdog._parse_argv` (`watchdog.py:160-170`) prende il primo token dopo `--` come modulo
e passa gli altri al figlio, quindi `--bridge-only` arriva al ponte. L'ambiente
(`APP_BOOT_ID`, `LOCAL_CHANNEL_TOKEN`, ...) passa dal watchdog al figlio perché il
watchdog lancia `popen(cmd, cwd=...)` senza `env`, cioè con l'ambiente ereditato (test
esistente: `Betfair/stream/tests/test_avvio_app_2026_09_16.py`, sezione «Il watchdog deve
poter passare l'ambiente al figlio»).

## 3. Comportamento atteso (identico agli altri figli)

| uscita del figlio | classificazione (`watchdog.classify_exit`) | effetto |
|---|---|---|
| exit 0: kill-file `STOP_SCALPER` dello scalper (`scalper_service.py`, `return` dal loop) oppure Ctrl+C del ponte | `clean` | alert INFO, il watchdog si ferma. **Corretto**: il kill-switch non va mai scavalcato |
| exit ≠ 0 entro 5 s: lock di istanza singola occupato (scalper 47314) | `lock` | alert WARN, il watchdog si ferma: niente loop contro il lock |
| qualunque altra uscita ≠ 0 | `crash` | alert CRITICAL `RUNNER_WATCHDOG` «RUNNER CRASHATO [<modulo>]: exit code X, uptime Ns. Riavvio n. K tra Bs.» (`watchdog.messaggio_crash`, già su master), riavvio con backoff 10→20→40…300 s, massimo 5 all'ora, poi CRITICAL «SERVE INTERVENTO MANUALE» |

Console su file: **già risolto su master** (K2-LOG-FIGLI, `main.js:218+`, file
`_logs/<label>_<avvio>.log`). Il watchdog non redirige stdout/stderr, quindi il figlio del
watchdog eredita il pipe e le sue righe finiscono già in `_logs/scalper-service_*.log` e
`_logs/tennis-bot-service_*.log`.

## 4. Lato FIGLIO alla ripresa (cosa fa il figlio rilanciato)

### scalper-service (`Betfair/stream/scalper/scalper_service.py`), già pronto
1. Lock di istanza singola 127.0.0.1:47314 (`main`): un secondo supervisore esce subito,
   classificato `lock`.
2. **FASE A con `APP_BOOT_ID`**: `controllo_avvio` (nuovo, FIX-C) ferma solo le righe di
   un avvio PRECEDENTE senza battito fresco. In un riavvio dal watchdog l'`APP_BOOT_ID` è
   lo stesso, quindi le sessioni armate dall'utente restano armate. **FIX-C**: se la
   lettura fallisce (DB o rete giù al riavvio), il controllo si ritenta a ogni giro e
   fino ad allora **nessuna** sessione si avvia. Prima un KO valeva «fatto».
3. **Sessioni figlie**: sono processi indipendenti (`Popen` senza kill a cascata) e
   sopravvivono alla morte del supervisore. Il nuovo supervisore le trova con
   `children = {}`. **FIX-C**: una riga `running`/`arming`/`stopping` senza figlio
   registrato si dichiara orfana o zombie SOLO dopo 60 s consecutivi di DB leggibile
   (`orfane_giudicabili`). Prima, dopo una caduta di rete e un riavvio, una sessione VIVA
   con il battito vecchio veniva messa in `error` al primo giro, con force-flat e stop.
4. Stato dal DB: il supervisore non ha altro stato. Le righe `scalper_control` sono la
   verità; l'auto-mode riparte dietro la sua `Guardia` d'avvio.
5. Rischio residuo (non corretto, per admin-26/coordinatore): la finestra fra lo spawn
   di una sessione (riga `requested`) e il suo `set_control('arming')`
   (`scalper_session.py`, subito dopo le due letture iniziali) è sotto il secondo. Se il
   supervisore muore proprio lì, il successivo può rispawnare la stessa partita: la
   sessione non ha un lock per evento. Il backoff minimo del watchdog (10 s) rende il
   caso molto improbabile. Il rimedio vero sarebbe un lock per evento nella sessione.

### ponte tennis (`Betfair/stream/tennis_live/tennis_bot_service.py --bridge-only`), già pronto
1. `ripresa_ponte` con la guardia `APP_BOOT_ID` (`tennis_bot_service.py:914` su master, ritentata nel giro a 952): con lo stesso avvio
   nessun fermo, con un avvio nuovo righe a `stopped` e paper. L'armamento salta le
   partite già attive e l'upsert `tennis_bot_control` è idempotente (`on_conflict
   event_id,bot_key`).
2. Nessun ordine e nessuna sessione Betfair nel ponte: un riavvio non può produrre un
   doppio ordine.
3. Il ramo `--bridge-only` **non ha un lock di istanza singola** (il lock sta solo in
   `run()`). Sotto watchdog non serve, perché si riavvia solo a figlio morto. Chi lo
   lancia due volte a mano ottiene due ponti che scrivono le stesse righe idempotenti.

## 5. Un difetto del watchdog da correggere insieme (file di admin-26)

(Il testo «RUNNER» senza nome del figlio è già corretto su master con
`messaggio_crash`, ma solo per il crash: i messaggi clean/lock/pianificato dicono
ancora «Runner».)

1. **Il battito del watchdog è unico per tutti**: `_db_heartbeat` scrive
   `betfair_live_heartbeat(runner=False)`, cioè le colonne `watchdog_ts`/`watchdog_pid`,
   per OGNI watchdog. Con altri due figli sotto watchdog, i watchdog che scrivono la
   stessa riga passano da 6 a 8, e quella riga non dice più nulla sul watchdog del
   runner. `WATCHDOG_HEARTBEAT_SEC=0` non lo spegne (`or 30.0`, riga 225 su master). Proposta:
   battito solo per il target di default (`Betfair.stream.runner`) oppure un env
   `WATCHDOG_BATTITO=0` per gli altri.

## 6. Come verificarlo (per chi integra)
- `python -m pytest Betfair/stream/tests/test_resilienza_rete_fix_c_scalper_2026_09_26.py -q -p no:cacheprovider`
  (lato figlio dello scalper).
- Dopo la modifica a `main.js`, ad app riavviata dall'utente: `tasklist` deve mostrare due
  `python -m Betfair.stream.watchdog -- ...scalper_service` e `...tennis_bot_service --bridge-only`.
  Un `taskkill /PID <pid del figlio> /F` (NON del watchdog) deve produrre in `live_alerts`
  un `RUNNER_WATCHDOG` CRITICAL e il figlio deve ripartire entro circa 10 s. Da fare solo
  con i bot fermi e con il permesso dell'utente.
