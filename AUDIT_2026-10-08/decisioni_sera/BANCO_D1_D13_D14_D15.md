# Banco: decisioni dell'utente dell'08/10 sera (D-1, D-13, D-14b, D-14c, D-14d, D-15)

Delegato Opus, worktree `C:\Users\Admin\Desktop\PYTHON DATABASE\wt-banco`, ramo `cantiere-banco-sera` da master `d257abea`.
Niente commit, niente push, niente `pip install`, nessun bot ne' strategia toccati, `trading/submin.py` non toccato.
Replay lanciati dal worktree con `--data-dir` = `_live_raw` del checkout principale (35760084, 35797769).
Strumenti (scratch, copiati qui): `strumenti/per_scenario.py` (confronto per scenario con `righe_confrontabili` del banco),
`strumenti/mut.py` (mutazioni), `strumenti/sonda_padre.py` (memoria del padre), `strumenti/misura_valuta.py`, `strumenti/prototipo_memo.py`.

## Esito in breve

| punto | stato | file toccati |
|---|---|---|
| D-1 B2 per ciclo | APPLICATO | `Betfair/stream/scalper/certificazione.py` (`_b2`) |
| D-13 lambda Safe fra scenari | GIA' IN MASTER (be3beb62, ingresso); completato all'USCITA, un solo punto | `Betfair/safe_strategy/tools/replay_registrazioni.py` |
| D-14b psutil | APPLICATO | `requirements.txt`, `Betfair/stream/backtest/certifica.py` (`riga_worker`) |
| D-14c riavvio di Omega | APPLICATO | `Betfair/omega/tools/replay_registrazioni.py` |
| D-14d memoria per identita' in `valuta` | **NON APPLICATO** (motivi sotto) | nessuno |
| D-15 memoria del padre | APPLICATO | `Betfair/stream/backtest/certifica.py` (`_per_il_padre`, futuri rilasciati) |

Test: nuovo `Betfair/stream/tests/test_banco_decisioni_sera_2026_10_08.py` (11 test), +6 test in
`test_scalper_certificazione_2026_09_24.py` (D-1), 1 test aggiornato in `Betfair/omega/tests/test_banco_omega_reperti_rb_2026_10_08.py`.
Suite chiesta (`Betfair/stream/tests Betfair/omega/tests Betfair/omega/test_*.py Betfair/safe_strategy/tests Betfair/mike/tests
Betfair/mike/test_*.py tools`, `-n 3`): **9964 passed, 64 skipped, 1 xfailed, 0 failed** in 290 s (`suite_n3.txt`).

Hash finali (sha256, 16): certificazione.py `b1304679a57a4cb6`, certifica.py `799d753ad49ca2ec`,
omega replay `2ef54b75fe20ce47`, safe replay `65d0c45aa17382f8`, requirements.txt `7439616e3df1ad6c`,
test nuovo `6fcea963c66af953`, test scalper `4a8842a7ff853430`, test RB `b37734604d164a12`.
CRLF conservati su tutti i file (verificato con `file`), righe aggiunte ASCII-only.

---

## D-1 - B2 con la stessa tolleranza PER CICLO di K5 (cantiere 15)

**Diff** (`_b2`): `tol = max(EPS, toll + 0.02 * max(0, cicli))`, con `cicli` = `slot.cycles` dalle credenze vere, la stessa
formula di K5 (`_k5`, `tol_tot`). E' la patch `cantiere_15/esperimento_B2_per_ciclo_NON_applicato.patch`, riportata sulle righe attuali.

**Divergenza dal brief, da sapere**: il caso «0,05 su 1 ciclo -> KO» NON e' KO con la regola di K5: la soglia effettiva e'
tolleranza + 0,02 x cicli + `EPS` (0,011) = 0,051, e 0,05 ci sta dentro (K5 la accetta uguale). Il test usa 0,06 su 1 ciclo
(KO) e dichiara 0,05 come bordo accettato. Cambiarlo vorrebbe dire una regola diversa da K5: non fatto.

**Test** (strategia VERA `ScalperStrategy`, credenze da `CERT.credenze`):
- `test_d1_b2_resti_di_due_cicli_dentro_la_tolleranza_per_ciclo`: 0,017+0,020 su 2 cicli -> B2 muto;
- `test_d1_b2_rosso_oltre_la_tolleranza_di_un_ciclo`: 0,06 su 1 ciclo rosso, 0,05 dentro, 0 cicli: 0,037 rosso e 0,019 muto;
- `test_d1_b2_e_k5_hanno_la_stessa_soglia_per_ciclo[0,1,2,5]`: per 30 sbilanci B2 (slot vivo) e K5 (slot chiuso) danno lo stesso giudizio.

**Mutazioni** (ripristino `b1304679a57a4cb6` ogni volta):

| mutazione | esito test D-1 |
|---|---|
| B2 senza il termine per ciclo (codice di prima) | 5 rossi su 6 |
| 0,03 per ciclo invece di 0,02 | 4 rossi |
| `cicli + 1` | 5 rossi |

**Replay** `scalper_calcio 35797769 --scenari chiusura-abbinata-in-parte,base --worker 3` (101,5 s): `replay/D1_scalper_35797769_chiusura_base.txt`.
- contro `cantiere_15/esperimento_B2_per_ciclo_NON_applicato.txt`: `chiusura-abbinata-in-parte` **0 righe diverse** (OK, 0 violazioni, 213 azioni);
- contro `controllo_finale/scalper/scalper_35797769_tutti.txt`: `base` **0 righe diverse**; `chiusura-abbinata-in-parte` 4 righe:
  la riga di esito `KO` -> `OK` (stessi tick 665941, decisioni 121012, azioni 213, stati) e le 2 righe della violazione B2 x1
  (sel 58805, 0,04) che spariscono. Nient'altro.

## D-13 - `omega_service._LAMBDA_CACHE` fra gli scenari della Safe

**Stato trovato**: master contiene gia' `be3beb62` (dopo il controllo finale `d01de76`): `PM.azzera_cache_lambda()` all'INGRESSO
di ogni replay della Safe, con il test `test_safe_ogni_scenario_riparte_pulito`.
**Diff mio**: la chiamata si sposta dentro `_pulisci_cache_di_processo` (unico punto, chiamato all'ingresso E nel `finally`
all'uscita di ogni replay), come RB-5 di Omega. **Non** al riavvio a meta' partita (`_riavvia_processo`): in produzione la Safe
riavviata rilegge l'evento con `bot_db.get_event` (tabella omega_events: fixture e modello salvato da Omega), che il banco della
Safe non esercita; azzerare li' farebbe ricalcolare i lambda dal solo mercato di quel momento, cosa che la produzione non fa.
E' una scelta: se l'utente vuole il riavvio «perde tutto» anche per la Safe, e' una riga (mutazione M2 qui sotto) e cambia lo scenario `riavvio`.
Limite residuo dichiarato: dentro UNO scenario il TTL resta di 900 s di parete (servirebbe uno scenario della Safe oltre 15 minuti).

**Test** (in `test_banco_decisioni_sera_2026_10_08.py`): pulizia di ogni scenario azzera i lambda; il riavvio NON li tocca;
`_certifica_evento` pulisce all'ingresso e il `finally` chiama la pulizia.

| mutazione (ripristino `65d0c45aa17382f8`) | esito |
|---|---|
| tolta la chiamata da `_pulisci_cache_di_processo` | 3 rossi (2 miei + `test_safe_ogni_scenario_riparte_pulito`) |
| lambda azzerati anche al riavvio | 1 rosso |
| `finally` senza pulizia | 1 rosso |

**Replay**:
1. Chiesto: `safe_base 35760084 --scenari base,riavvio --worker 3`, due corse (68 s, 81 s): contro
   `controllo_finale/omega/safe_base_35760084_tutti.txt` **0 righe diverse** in entrambi gli scenari; corsa1 contro corsa2: 0.
   Ma qui la catena dei lambda NON e' sollecitata (nota `save_event_model`/`get_event` assente in base e riavvio anche nel riferimento):
   questo replay non prova D-13.
2. Aggiunto dove la nota si spostava: `safe_base 35797769 --scenari base,riavvio,esiti-ignoti,manuale-e-bot,chiusura-abbinata-in-parte,rifiuti-betfair --worker 3`,
   due corse (528 s e 527 s; sotto il tetto di 10 minuti). Corsa1 contro corsa2: **0 righe diverse**. La nota del modello
   (`save_event_model` fra i metodi assenti + `[NON ESERCITABILE] get_event`) sta in base, esiti-ignoti, manuale-e-bot,
   chiusura-abbinata-in-parte, rifiuti-betfair in ENTRAMBE le corse (in riavvio in nessuna, come nel riferimento).
   Contro `controllo_finale/safe/safe_base_35797769_tutti.txt`: righe di esito **identiche** (6/6); 16 righe diverse, tutte note:
   - 5 x riga `attivita' del servizio`: compare `flusso_non_dichiarato x1` (l'avviso «una volta per processo» riarmato a ogni
     scenario da `be3beb62`, gia' in master, non da me) e, poiche' la riga elenca le prime 10 voci, l'ultima voce scivola fuori;
   - `chiusura-abbinata-in-parte` e `rifiuti-betfair`: + `save_event_model` nei metodi assenti e + la nota `[NON ESERCITABILE] get_event`
     (4 righe): e' D-13: nel riferimento la cache arrivava piena dallo scenario prima nello stesso figlio.
   Il mio spostamento all'uscita non puo' cambiare il referto (l'ingresso azzera comunque); serve a non lasciare la cache a chi
   gira dopo nello stesso processo.

## D-14b - `psutil`

**Diff**: `requirements.txt` + `psutil==7.2.2` (la versione del `.venv` del PC), sezione stream, con commento.
`certifica.py`: `psutil_presente()` e `riga_worker(processi, richiesti, compiti)`; quando i processi usati sono meno di quelli
voluti (chiesti, o il default 3 fuori dalla suite) e non per mancanza di compiti, la riga dice la causa:
`worker: 1 (psutil assente: richiesti 3)` (o `tetto core fisici - 1 = N` con psutil presente). Senza taglio la riga e' quella di sempre
(stessa stringa) e con un solo processo nessuna riga, come prima: i referti non cambiano (la riga `worker:` e' comunque esclusa dal confronto).

**Test**: senza psutil (`sys.modules['psutil']=None`, 4 thread) -> `quanti_processi(3,10)==1` e la riga esatta; con psutil la riga di
sempre e nessuna riga quando non c'e' taglio; `main` con `--worker 3` senza psutil stampa la riga.

| mutazione (ripristino a `f4a7c8262e728689`, hash di certifica.py prima di D-15) | esito |
|---|---|
| nessuna riga con un processo solo (il silenzio di prima) | 2 rossi |
| `main` stampa solo con piu' processi | 1 rosso |
| causa invertita | 2 rossi |
| taglio mai riconosciuto | 2 rossi |

## D-14c - lo scenario `riavvio` di Omega perde TUTTO

**Diff**: tolti `CACHE_DI_PROCESSO_DEL_BANCO` e `_azzera_cache_di_processo` (il secondo elenco). `_riavvia_processo()` = `_processo_nuovo()`
(svuota_le_cache + i 13 nomi di `STATO_DI_PROCESSO_FRA_SCENARI` + i due avvisi di processo), e torna i nomi che erano pieni.
`AmbienteOmega` chiama solo `_processo_nuovo()` (prima chiamava anche `_azzera_cache_di_processo`, che era un sottoinsieme: verificato
che ogni nome del vecchio elenco sta in `STATO_DI_PROCESSO_FRA_SCENARI` o in `svuota_le_cache`, `_CATENA_OMEGA` compreso).
`CACHE_TABELLE_STORICHE` resta come nome per i test di RB-5. Test RB-5 aggiornato: non c'e' piu' il secondo elenco e le cache di RB-5 stanno nell'unico.

**Test**: riavvio con tutto sporco -> tutto vuoto, avvisi riarmati, e il referto nomina ogni stato azzerato (fra cui `_EVENTS_REFRESH_AT`,
`_LEG_RETRY_DB`, `_DAILY_GOAL_WRITTEN`, `_REALLY_OVER_CACHE`, `_ULTIMO_STATO_SCANNER_OMEGA`); riavvio e ingresso sono la stessa funzione.

| mutazione (ripristino `2ef54b75fe20ce47`) | esito |
|---|---|
| riavvio di prima (solo `svuota_le_cache`) | 2 rossi |
| `_EVENTS_REFRESH_AT` tolto dall'elenco | 1 rosso (+ il test di isolamento di cantiere 11) |
| avvisi di processo non riarmati | 1 rosso |

**Replay**:
- Chiesto: `omega 35760084 --scenari riavvio,base --worker 3` (42 s) contro `controllo_finale/omega/omega_35760084_tutti.txt`: **0 righe diverse**.
  Su 35760084 il riavvio non scatta mai (nota «nessuna posizione aperta da ritrovare»): non prova D-14c.
- Aggiunto dove scatta: `omega 35797769 --scenari riavvio,v4-riavvio,base --worker 3` (157 s) contro `omega_35797769_tutti.txt`:
  `base` 0; righe di esito di `riavvio` e `v4-riavvio` **identiche** (tick 1462561, decisioni 736, azioni 4); 4 righe diverse per scenario:
  1. riga `attivita' del servizio`: `flusso_non_dichiarato x1` -> `x2` (l'avviso «una volta per processo» si riarma al riavvio,
     come in un riavvio vero), e quindi cambia l'ordine della riga;
  2. nota `RIAVVIO a meta' partita`: l'elenco ora nomina anche `_ULTIMO_STATO_SCANNER_OMEGA`, `_DAILY_GOAL_WRITTEN`,
     `_EVENTS_REFRESH_AT` e gli avvisi di processo. Nessun numero di decisione, ordine o violazione cambia.

## D-14d - memoria per identita' in `valuta.py` (codice di PRODUZIONE): NON APPLICATA

**Misure** (`strumenti/misura_valuta.py`, book costruiti da betfairlightweight con flumine importato, cambio del banco):

| registrazione | book | liste convertite | stessa lista del book prima | livelli | livelli in liste identiche | tempo in `converti_libro` |
|---|---:|---:|---:|---:|---:|---:|
| 35760084 | 643.713 | 258.930 | 60,9 % | 1.471.710 | 65,5 % | 4,0 s |
| 35797769 | 1.785.014 | 826.683 | 59,9 % | 12.494.493 | 72,3 % | 21,6 s |

**Verifiche di sicurezza fatte**: nessuna scrittura in place sui livelli in flumine (site-packages: `simulatedorder` legge soltanto,
`middleware` confronta `traded_volume` con `==`), in betfairlightweight (`Available.serialise` crea sempre una lista nuova, ogni
aggiornamento un dict nuovo) e in `Betfair/` (grep di `["size"] =`, `.append/.sort/.pop` e `del` sui tre campi: solo liste nuove);
nessun confronto per identita' (`is`/`id`) sulle liste dei livelli.

**Perche' non applicata**:
1. Sicurezza al 100 %: con la memoria, il book successivo riceve lo STESSO oggetto lista convertito (e gli stessi dict) del book prima.
   Per non dare mai un risultato stantio servirebbe a ogni riuso il controllo completo dell'originale E della lista convertita, tipi
   compresi. Il prototipo (`strumenti/prototipo_memo.py`) usa il confronto `==` in C su copie dei dict: non vede un cambio di solo
   tipo (es. prezzo `2` -> `2.0`, che il dict copiato porterebbe com'era) e costa una copia in piu' a ogni conversione nuova.
2. Il guadagno non e' dimostrabile su questa macchina: 4 coppie di corse sullo stesso raw (35797769):
   oggi 23,1 / 21,3 / 49,3 / 36,4 s; memoria 18,4 / 52,5 / 51,0 / 51,8 s (495.157 riusi, 331.526 conversioni). La variabilita' della
   macchina (app viva) copre la differenza, e nelle corse confrontabili la memoria e' al massimo il 20 % di `converti_libro`.
Proposta se la si vuole riprendere: misurarla su macchina scarica (cloud) e solo con un controllo per identita' dei VALORI (non `==`).

## D-15 - la memoria del PADRE di `certifica`

**Misura PRIMA** (`strumenti/sonda_padre.py`: avvolge `_esegui_compiti`, RSS del padre a ogni referto ricevuto, dimensione
serializzata del referto e dei suoi attributi; campionamento del picco ogni 0,5 s), `scalper_calcio 35797769`, 9 scenari
(`base,paper,senza-missione,bot-fermo,kill-switch,esiti-ignoti,rifiuti-betfair,riavvio,chiusura-abbinata-in-parte`), `--worker 3`:
l'unico attributo pesante e' `ordini_specchio` (le righe `betfair_live_orders` catturate: 12-132 MB serializzati per referto,
tutto il resto ~0 MB). Il padre le tiene tutte (nella lista `referti` di `main` e nei futuri della pool) fino alla fine; `main` non le
legge ne' le stampa (le usano solo i controlli dentro il figlio e `applica_bot`, che non passa da `_lavora_cronometrato`).

**Diff**: `CAMPI_SOLO_DEL_FIGLIO = ("ordini_specchio",)` e `_per_il_padre(r)`, chiamata in `_lavora_cronometrato` (nel processo che fa
il replay, prima del viaggio verso il padre): l'attributo sparisce e `ordini_specchio_tolte` dice quante righe c'erano (un dato tolto
non e' un dato zero). In `_esegui_compiti` il futuro letto si rilascia (`futuri[i] = None`). `_lavora` non cambia.

| referto ricevuto | RSS padre PRIMA (MB) | RSS padre DOPO (MB) | referto serializzato PRIMA -> DOPO |
|---|---:|---:|---:|
| 1 base | 512 | 144 | 35,3 -> 0,0 MB |
| 2 paper | 512 | 144 | 35,3 -> 0,0 |
| 3 senza-missione | 1.323 | 144 | 132,0 -> 0,0 |
| 4 bot-fermo | 1.323 | 144 | 12,1 -> 0,0 |
| 5 kill-switch | 1.323 | 144 | 12,1 -> 0,0 |
| 6 esiti-ignoti | 1.507 | 144 | 35,3 -> 0,0 |
| 7 rifiuti-betfair | 1.692 | 144 | 35,3 -> 0,0 |
| 8 riavvio | 2.051 | 144 | 69,8 -> 0,0 |
| 9 chiusura-abbinata-in-parte | 2.616 | 144 | 108,8 -> 0,0 |
| **picco campionato** | **2.725** | **144** | |
| TEMPO TOTALE | 530,6 s | 303,4 s | (la serializzazione verso il padre costava anche tempo) |
| MEMORIA dei worker (riga del banco) | 438-1246 MB | 438-934 MB | |

Proiezione su 56 scenari: prima ~+200 MB per referto (i ~10 GB del container), dopo costante.

**Referto identico**: `confronta_referti PRIMA DOPO`: 2 righe diverse, l'identificativo d'ordine a 18 cifre generato a runtime
nell'esempio di B1 di `riavvio` (`140107800576195989` -> `140107806889877792`, stesso ingresso, stesso istante, stesso divieto: e' la
differenza che il controllo finale gia' dichiara e maschera con `--maschera-id`). Contro `controllo_finale/scalper/scalper_35797769_tutti.txt`:
7 scenari 0 righe, `riavvio` solo lo stesso id a 18 cifre, `chiusura-abbinata-in-parte` le 4 righe di D-1.

**Test**: il figlio non manda `ordini_specchio` e dichiara quante; `main` (`--worker 1`) stampa le stesse righe con e senza le righe
dello specchio; la pool (finta, `Future` veri) non trattiene il referto gia' letto (riferimento debole morto dopo il `next`).

| mutazione (ripristino `799d753ad49ca2ec`) | esito |
|---|---|
| `_per_il_padre` non chiamata | 2 rossi |
| futuri trattenuti | 1 rosso |
| righe azzerate (`[]`) invece di tolte | 2 rossi |

## Non verificato / limiti

- Le righe dello specchio nei test D-15 sono finte con le chiavi della riga `betfair_live_orders` + `_ms`, non catturate da un replay.
- D-15 misurato solo sullo scalper (9 scenari); Mike/Omega/Safe hanno lo stesso campo `ordini_specchio` e passano dallo stesso
  `_lavora_cronometrato`, ma il loro RSS del padre non l'ho misurato. Un `--scenari tutti` dello scalper (56) non l'ho rilanciato (> 10 minuti).
- La corsa 2 di D-13 su 35797769 e' girata mentre facevo le mutazioni di `certifica.py` (D-14b, solo funzioni del padre: `riga_worker`/`main`,
  i figli erano gia' avviati): e' identica riga per riga alla corsa 1, girata a codice fermo.
- D-14d: tempi su una macchina con l'app viva, molto variabili (vedi tabella): nessuna conclusione sul guadagno, solo sulla sicurezza.
- Suite completa `Betfair/` intera non lanciata (solo le cartelle chieste) e frontend non toccato.
- `psutil==7.2.2` in `requirements.txt` non installato da nessuna parte (gia' nel `.venv` del PC); le Actions lo installeranno al prossimo giro.

---

## Blocco per CRONOSTORIA.md (da incollare dal coordinatore)

```
### Banco: decisioni dell'08/10 sera (delegato Opus, worktree wt-banco, ramo cantiere-banco-sera da d257abea, NON committato)
- D-1 APPLICATO: B2 con la tolleranza per ciclo di K5 (certificazione.py `_b2`). scalper 35797769 chiusura-abbinata-in-parte
  OK 0 violazioni 213 azioni (= esperimento cantiere 15, 0 righe), base identico al controllo finale. Nota: 0,05 su 1 ciclo NON e' KO
  (soglia 0,051 = 0,04 + EPS, come K5); il test usa 0,06.
- D-13: l'azzeramento all'ingresso era gia' in master (be3beb62); ora in `_pulisci_cache_di_processo` (ingresso + uscita), NON al riavvio
  (scelta dichiarata). safe_base 35797769 6 scenari x2 corse: identiche, la nota del modello sempre negli stessi 5 scenari; esiti = controllo finale.
- D-14b APPLICATO: psutil==7.2.2 in requirements.txt; riga `worker: 1 (psutil assente: richiesti N)` quando il tetto taglia.
- D-14c APPLICATO: riavvio di Omega = `_processo_nuovo()` (un solo elenco). omega 35797769 riavvio/v4-riavvio: esiti identici,
  cambiano solo la nota RIAVVIO (piu' stati) e `flusso_non_dichiarato x2`. 35760084: il riavvio non scatta (0 righe).
- D-14d NON APPLICATO: 60-72 % di riuso misurato, ma riuso sicuro al 100 % non ottenibile a costo utile e guadagno non dimostrabile sul PC.
- D-15 APPLICATO: il figlio non manda al padre `ordini_specchio`, i futuri letti si rilasciano. scalper 35797769 9 scenari w3:
  picco del padre 2725 -> 144 MB, 530 -> 303 s, referto identico (solo l'id a 18 cifre di runtime).
- Suite (stream/omega/safe/mike/tools, -n 3): 9964 passed, 64 skipped, 1 xfailed, 0 failed.
- Referto: AUDIT_2026-10-08/decisioni_sera/BANCO_D1_D13_D14_D15.md (replay in decisioni_sera/replay/).
- DA VERIFICARE dal coordinatore: diff, mutazioni, un replay (es. D-15) rilanciato dal checkout principale dopo la fusione.
```
