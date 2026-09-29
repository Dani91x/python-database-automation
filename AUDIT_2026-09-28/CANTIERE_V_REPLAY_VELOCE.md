# CANTIERE V - replay veloce dello scalper calcio (29/09/2026)

Patch: `AUDIT_2026-09-28/CANTIERE_V.patch` (su master 7c1a40e). Referti e script: `AUDIT_2026-09-28/cantiere_v/`.
File toccati: `Betfair/stream/scalper/certificazione.py`, `Betfair/stream/scalper/tools/replay_registrazioni.py`,
`Betfair/stream/backtest/banco_comune.py`; nuovo `Betfair/stream/tests/test_cantiere_v_replay_veloce_2026_09_29.py`. Nessun file dei bot.

| replay (`--worker 1` salvo dove detto) | prima | dopo | referto |
|---|---|---|---|
| scalper 35797769 base+paper (codice di master, rif. `cantiere_s/scalper_calcio_base_paper_S.out.txt`) | 15 min 59 s | 130 s | IDENTICO: blocchi, esito e copertura (conteggi di ogni controllo) |
| scalper 35797769 4 scenari (rif. `scalper_calcio_KO_2f53bb0_4scenari.txt`, codice 2f53bb0 = fa84ee7 per i bot) | 115 min | 1270 s (21 min) | IDENTICO salvo 1 riga: l'id d'ordine flumine (`uuid1().time`, orologio di sistema) nella chiave UF2 |
| scalper 35797769 4 scenari, codice di master | - | 1019 s `--worker 1` / 358 s `--worker 0` | i due referti uguali fra loro (stessa sola riga d'id) |
| scalper 35674515 sniper+sniper-paper (rif. `sniper_2f53bb0.txt`) | 12 min 14 s | 154 s | IDENTICO: blocchi, esito e copertura |

Cosa ho cambiato. (1) S5: la copertura dei buchi vive nella `Memoria` (`_CoperturaCrescente`, `_StatoS5`) invece di essere ricostruita su tutti i buchi a ogni giro; una coppia di battiti con b-a <= massimo non guarda i buchi (copertura >= 0); una coppia gia' giudicata SANA resta sana finche' l'elenco dei buchi si allunga soltanto (dimostrazione nel docstring: la copertura puo' solo crescere); le coppie difettose si rigiudicano sempre; elenco cambiato = si riparte da zero. (2) Il replay passa i buchi come vista di un registro solo-in-aggiunta (`RegistroBuchi`/`VistaBuchi`): niente copia a ogni giro, prefisso garantito per costruzione. (3) `running_e_battiti` incrementale (prima due passate su tutte le scritture a ogni giro; la versione lenta resta come riferimento). (4) `vita_ms` ricalcolata solo quando cambiano interruttori o costanti; `import` fuori dal percorso di ogni book (`_modulo`, `_flumine_utils_events`). Cadenza, book, giri e controlli invariati.

Test: suite `-k "scalper or sniper or banco or certificazione or cantiere_v"` 789 passati, 25 saltati. Test nuovi (200) con equivalenza contro la formula lenta e contro S5 di oggi (copiata nel test) giro per giro; falsificazione: 16 mutazioni, 16 rosse, ripristino con controllo dell'hash (`cantiere_v/falsifica_esito2.txt`).

Dove sta il limite (misura): dopo il cantiere uno scenario manuale (1,51 M tick, KO+7800 s con sniper) dura 272 s; spegnendo per prova TUTTI i giri di verifica (copia fuori dal repo) dura 280 s: i controlli non pesano piu'. Il profilo (cProfile, `uscite-manuali-firmate`) da' il resto a flumine (middleware di simulazione ~16 %), codice di produzione non-bot (valuta, specchio ~14 %), bot (~11 %), ciclo per-book del banco e builtin. Con `--worker 1` i 4 scenari restano sopra i 10 minuti (1019 s) per i due scenari manuali lunghi; con `--worker 0` 358 s.

NON verificato: i tempi sono misurati con altri replay (Mike, di un altro delegato) accesi sulla stessa macchina; non esiste un «prima» degli scenari manuali col codice di master (equivalenza provata solo dai test e dal confronto su 2f53bb0); l'impronta «codice bot» nel referto cambia perche' include `certificazione.py` (con il file di HEAD si riottiene bc5b32492db1); nessuna ottimizzazione di flumine, valuta, specchio o bot (fuori perimetro).
