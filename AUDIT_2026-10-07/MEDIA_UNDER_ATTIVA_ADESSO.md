# MEDIA UNDER - <<ATTIVA ADESSO>> E OPERATIVITA' IN GIOCO (07/10/2026)

Delegato del coordinatore (Opus 5.5), worktree
`/home/user/python-database-automation/.claude/worktrees/agent-aa5ceceb277838a6f`, lavoro NON committato
(base HEAD `8226d766`). Ordine dell'utente del 07/10 + REGOLA DEFINITIVA sui nuovi cicli (07/10) + correzioni
del coordinatore. E' un CAMBIO DI STRATEGIA CHIESTO DALL'UTENTE: scritto come divergenza voluta in
`Betfair/stream/scalper/SPEC_MEDIA_UNDER_2026-10-05.md` par.13 (divergenze elencate in par.13.2).

## 0. In breve

- **Pulsante <<Attiva adesso>>** nella scheda della Media Under (prova e soldi veri, stessa strada; in soldi
  veri la conferma esplicita). Sessione ferma: il clic la accende (RPC di sempre `scalper_activate`) armata dal
  pulsante col comando dentro i params; sessione accesa: il comando arriva con la RPC nuova
  `scalper_media_attiva_adesso` (migrazione scritta, NON applicata). Il comando passa dai `params` della riga
  `scalper_control`, la stessa strada dei parametri.
- **Effetto**: prima punta SUBITO allo stake base al miglior prezzo di punta (pre-match o in gioco), senza i
  filtri d'ingresso; poi la gestione come progettato (banca, rientri, massimo, rischio massimo, riquadro
  chiusura) SENZA filtri (finestra di stop e gioco compresi). Restano tetti e protezioni: mercato aperto,
  prezzi vivi, minimi .it, freno dei soldi veri, stop/freno della sessione, attesa dopo un rifiuto, una sola
  punta e una sola banca vive.
- **Nuovi cicli** (regola definitiva): chiuso PRE-MATCH -> rientra da solo (di serie SUBITO, anche nella
  finestra di stop; coi filtri se `media_rientro_auto_filtri` = true); chiuso IN GIOCO -> `ATTESA_CLIC`;
  ciclo a cavallo del fischio -> in gioco continua, chiuso in gioco -> attesa del clic. La modalita' accesa
  nel modo di sempre NON cambia in nulla (referti identici riga per riga, par.6).
- **Un clic = una sola prima punta**: l'id del clic si registra nelle stats della riga PRIMA dell'esecuzione
  e si rilegge dopo un riavvio; scaduto (>120 s), prezzi fermi, mercato sospeso, gia' in posizione =
  rifiutato col motivo e consumato (mai accodato).
- **Replay**: contratto comune `certifica_scenario(..., parametri=None, dal_ms=None, clic_ms=None)` e
  `parametri_modificabili(scenario)` implementati coi nomi ESATTI; 18 scenari nuovi `media-clic-*`, girati su
  35797769 e 35760084: **0 violazioni in 36 replay**; controlli nuovi M12-M18 (registro separato), tutti
  sollecitati almeno una volta.
- **Numeri**: 1105 test Python passati (2 skip) nel perimetro scalper/media/replay, tsc 0 errori, vitest 30/30;
  mutazioni bot+sessione 21/21 rosse, banco 15/16 rosse (1 equivalente), TS 7/7 rosse, replay 6/8 rosse (2
  coperte dai test unitari, spiegate).

## 1. Cause radice e decisioni di progetto (con prova)

Non e' un difetto: e' una funzione nuova. Le scelte e i difetti trovati strada facendo:

| # | Reperto | Prova | Correzione |
|---|---|---|---|
| 1 | Rientri e ingressi fermati dai filtri d'ingresso anche col pulsante | HEAD `media_under_bot.py:1168` (`if self._puo_aprire(now)` in `_forse_rientro`) e `:1224` (`_punta_di_rientro`) | ora `_filtro_aperture(now)` (`:1161`, usato a `:1376` e `:1432`): col pulsante solo le protezioni (`_puo_gestire`, `:1147`), senza pulsante `_puo_aprire` come prima |
| 2 | In gioco la modalita' faceva solo la banca (`_in_live`) | HEAD `:993` `self._in_live(now, aperto, bb, bl)` | col pulsante `_in_gioco_a_clic` (`:1623`, chiamato a `:1116`): gestione come pre-match; senza pulsante `_in_live` invariato |
| 3 | `riquadro_chiusura` divideva per zero con la miglior punta a 1,01 (visto nel replay 35760084, cicli del pulsante in gioco: traceback a ogni book) | HEAD `:575` `if quota_punta and c:` | `:649` `if quota_punta and c and c < float(quota_punta) - 1e-9:`; test `test_riquadro_alla_quota_minima_nessuna_divisione_per_zero`, mutazione 20 rossa. Nei referti di HEAD 0 traceback: per la modalita' di sempre e' inerte |
| 4 | Il conteggio della parita' S6 (`_parametri`) sarebbe salito da 51 a 59 attributi | banco S6 | tutto lo stato del pulsante in UN oggetto `StatoClic` (`:862`) |
| 5 | Banco: falso M18 a processo morto (scenario riavvio) | `controlli_media` | i cronometri del rientro dovuto girano solo con una sessione della modalita' viva |
| 6 | Banco: clic <<scaduto>> sulla 35797769 (mercato quieto, nessun book per circa 2') | referto r5 primo giro | `manda_clic` (`replay_registrazioni.py:1958`) timbra il comando all'istante in cui lo scrive; le regole prezzi-fermi/doppio/in-posizione spostate a KO-15' (mercato vivo) |
| 7 | Banco: la connessione finta risultava sempre <<ferma>> | `SimulatedDateTime` di flumine sostituisce `datetime.datetime` dentro il replay | `_DATETIME_VERO` preso all'import; test `test_flusso_finto_letto_da_stato_stream` con `SimulatedDateTime`, mutazione C10 rossa |
| 8 | Banco: NE sbagliato negli scenari di rifiuto | `_referto_clic` (`:3468`) | togliere il NE <<NESSUN ordine>> quando il rifiuto atteso e' avvenuto (`_ATTESO_DELLA_REGOLA`) |
| 9 | Mutazione sopravvissuta segnalata dal coordinatore: `self.stato not in (FERMO, ATTESA_CLIC, FINE)` | blocco 1 | test parametrico `test_clic_rifiutato_in_uno_stato_di_ciclo_anche_senza_ordini` (INGRESSO, IN_POSIZIONE, RIENTRO, MASSIMO, LIVE a stato forzato senza ordini): mutazione 19 ROSSA. Sul cammino vero il controllo e' equivalente a `pos.aperta`/`_punta`: resta come difesa in profondita' |

## 2. Cosa e' cambiato; elenco esatto dei file

Modificati (9): `Betfair/stream/scalper/media_under_bot.py` (+421), `scalper_session.py` (+94),
`certificazione.py` (+407), `tools/replay_registrazioni.py` (+826), `SPEC_MEDIA_UNDER_2026-10-05.md` (+60, par.13),
`Betfair/stream/tests/test_scalper_media_under_2026_10_05.py` (+5/-2, vedi sotto),
`frontend/src/components/live/ScalperPanel.tsx` (+146), `ScalperPanel.test.tsx` (+103),
`frontend/src/lib/mediaUnder.ts` (+168).
Nuovi (6): `Betfair/stream/tests/test_scalper_media_under_attiva_adesso_2026_10_07.py` (52 test),
`Betfair/stream/tests/test_replay_scalper_attiva_adesso_2026_10_07.py` (51 test),
`frontend/src/lib/mediaUnderAttiva.ts`, `frontend/src/lib/mediaUnderAttivaAdesso.test.ts` (8 test),
`migrations/media_under_attiva_adesso_2026-10-07.sql`, questo referto + `AUDIT_2026-10-07/replay/` (560 KB, file
<1 MB). NON toccati i file dell'altro delegato (`applica_bot.py`, `registro_bot.py`, `worker.py`, replayBot.ts,
MatchReplay.tsx, components/replay/**, replayTimelineEvents.ts).

**Test esistente modificato (unico)**: `test_scalper_media_under_2026_10_05.py::test_la_sessione_arma_solo_la_modalita_e_paper_uguale_live`
riga 659: `for sc in R.SCENARI_MEDIA` -> `for sc in [s for s in R.SCENARI_MEDIA if s not in R.SCENARI_MEDIA_CLIC]`.
Motivo: gli scenari `media-clic-*` armano in `ATTESA_CLIC` (non `FERMO`) e il flag paper differisce per
costruzione; sono coperti da `test_la_sessione_vera_arma_dal_pulsante_e_paper_uguale_live` (nuovo). Gli scenari
di sempre restano asseriti identici.

Bot (`media_under_bot.py`): costanti `CHIAVE_COMANDO="media_attiva_adesso"` (`:138`), `CHIAVE_A_CLIC="media_a_clic"`
(`:141`), `CHIAVE_RIENTRO_FILTRI="media_rientro_auto_filtri"` (`:143`, default False, solo bool stretto),
`ATTESA_MASSIMA_COMANDO_S=120.0` (`:146`), stato `ATTESA_CLIC`; `leggi_comando` (`:383`); protocollo
`ricevi_comando` (`:1662`) -> la sessione scrive l'id nelle stats (`Db.set_control` ora torna bool,
`scalper_session.py:1214`) -> `rilascia_comando` (`:1694`) o `annulla_comando` (`:1703`) -> `_esegui_comando`
(`:1747`) al book dopo; `_rientro_automatico` (`:1295`, unica guardia: in gioco -> `ATTESA_CLIC`);
`_punta_morta` (`:1321`); `_ciclo_chiuso` (`:1527`); `serve_ordini_conto` (`:2225`) vero anche in gioco a clic;
ripresa a clic -> `ATTESA_CLIC`. Eventi: `media_ingresso` con `origine` (solo per ingressi non da filtri; il
payload di sempre e' identico), `media_attesa_clic`, `media_rientro_automatico`.

Sessione (`scalper_session.py`): `UI_PARAM_WHITELIST` (`:72`) + le 3 chiavi; `comando_media_precedente` (`:977`,
rilegge l'id consumato dalle stats precedenti); `consegna_comando_media` (`:1000`) chiamata all'avvio (`:1843`,
dopo il set_control "running") e a ogni battito (`:2094`, solo se lo stato non e' stopping/stopped/error, col
`_flusso` per i prezzi fermi).

Frontend: pulsante <<Attiva adesso>> nel modulo e nella scheda attiva, casella <<rientro automatico coi
filtri>>, stato del clic (inviato/eseguito/rifiutato col motivo, attesa esito 20 s), origine del ciclo (clic /
rientro automatico), testo dello stato `ATTESA_CLIC`. Conferma esplicita in soldi veri. (Le stringhe UI non
ASCII seguono la convenzione gia' presente in `mediaUnder.ts` di HEAD, 27 righe non ASCII.)

## 3. Test, comandi, numeri, falsificazioni

| Comando | Esito |
|---|---|
| `python3 -m pytest Betfair/stream/tests -q -p no:cacheprovider -p no:logging -k "scalper or media or replay or registro or contratto"` | **1105 passati, 2 skip, 0 falliti** (93 s) |
| `python3 -m pytest` sui 9 file media/scalper/certificazione/sessione | **376 passati** (13 s) |
| `npx tsc -p tsconfig.app.json --noEmit` | **0 errori** |
| `npx vitest run src/lib/mediaUnder src/components/live/ScalperPanel.test.tsx` | **30/30** (3 file) |

Suite intera `Betfair/` NON lanciata (vedi par.6).

**Mutazioni bot+sessione** (`replay/mutazioni_bot_sessione.txt`, ognuna sul file vero, ripristino verificato
md5, 0 <<MUTAZIONE>> rimaste): 21/21 ROSSE - 1 seconda punta per lo stesso comando; 2a/2b prima punta che
aspetta i filtri (finestra / liquidita'-flusso); 3 rientro bloccato dai filtri; 4 operativita' ferma in gioco;
5a/5b ordine a mercato sospeso (consegna / book); 6 prezzi fermi; 7 clic gia' in posizione; **8 in gioco
rientra da solo; 9 pre-match non rientra; 10 coi filtri spenti aspetta i filtri; 11 coi filtri accesi li
ignora** (le 4 chieste dall'utente); 12 eseguito prima della registrazione nella riga; 13 scaduto eseguito; 14
salta il freno dei soldi veri; 15 prima punta non abbinata -> riparte da sola; 16 la modalita' di sempre
diventa a clic; 17 riavvio: id non riletto; 18 non punta al miglior prezzo; 19 stato del ciclo non guardato
(coordinatore); 20 riquadro a 1,01.

**Mutazioni banco** (`replay/mutazioni_banco.txt`): 15/16 ROSSE (C1, C1b, C2-C5, C6b, C7-C14). C6 (<<riga della
UI cambiata senza parametri>>) SOPRAVVISSUTA: equivalente (ritorno anticipato che produce la stessa riga); la
variante C6b, che manda l'interruttore nella riga di sempre, e' ROSSA.

**Mutazioni TS** (`scratchpad/aa5c_mut_ts.py`): T1-T7 7/7 ROSSE - T1 il pulsante non arma la sessione a clic;
T2 l'esito di un clic vecchio vale per il nuovo; T3 doppio clic permesso; T4/T5 soldi veri senza conferma
(sessione ferma / accesa); T6 l'accensione di sempre manda le chiavi del pulsante; T7 il clic non manda il comando.

**Mutazioni a livello di REPLAY** (`replay/mutazioni_replay_35760084.txt`, copia del codice in scratchpad,
registrazione vera 35760084, banco intero):

| Mutazione | Scenario | Esito | Controllo |
|---|---|---|---|
| R1 in gioco rientra da solo | media-clic-due-clic | ROSSA | M12 x4230 |
| R2 prima punta che aspetta i filtri | media-clic-lontano | ROSSA | M15 x5889 |
| R3 rientro bloccato dai filtri | media-clic-finestra | ROSSA | M18 x1852 |
| R4 seconda punta per lo stesso clic | media-clic-due-clic | SOPRAVVISSUTA | coperta dal TTL 120 s nel replay; test unitario rosso (mut. 1) |
| R5 / R5b ordine a mercato sospeso | media-clic-sospeso | SOPRAVVISSUTE | la registrazione non ha prezzi durante la sospensione; test unitari rossi (5a/5b) |
| R6 ordine coi prezzi fermi | media-clic-prezzi-fermi | ROSSA | M12 x5332 |
| R7 clic eseguito gia' in posizione | media-clic-in-posizione | ROSSA | M2 M3 M4 M5 M11 |
| R8 operativita' ferma in gioco | media-clic-gioco | ROSSA | M18 x851 |

Prima e dopo ogni mutazione `md5` identico; 0 marcatori rimasti.

## 4. Migrazione SQL (scritta, NON applicata)

`migrations/media_under_attiva_adesso_2026-10-07.sql`: RPC `scalper_media_attiva_adesso(p_event_id text, p_id text)`,
SECURITY DEFINER, owner-only (`betfair_live_is_owner()`), scrive `params.media_attiva_adesso = {id, ts: now()}`
solo sulla riga attiva della partita con `media_mode` true; REVOKE da public/anon. Additiva e idempotente, nessuna
colonna. Ordine: dopo `scalper_bot.sql`, `scalper_auto_mode_2026-09-25.sql`, `uscite_approva_bot_flusso_2026-09-28.sql`
(gia' applicate). Senza la migrazione il pulsante a sessione FERMA funziona (usa `scalper_activate`); quello a
sessione ACCESA fallisce con l'errore della RPC mostrato nella scheda.

## 5. Parita' paper/live

Stesso codice, stessa strada: l'unica differenza e' `dry_run` (e in soldi veri la conferma esplicita nella UI e
il freno dei soldi veri, che vale anche per il clic: mutazione 14 rossa). Prove: conteggio S6 dei parametri
invariato (stato del pulsante in `StatoClic`); `test_la_sessione_vera_arma_dal_pulsante_e_paper_uguale_live`
(sessione vera fino all'armamento: stessi parametri in prova e soldi veri); nel replay `media-clic-lontano`
(soldi veri) e `media-clic-lontano-paper` danno gli stessi ordini e lo stesso netto su entrambe le
registrazioni (+0,15 / -172,56 EUR, 11 / 12 azioni).

## 6. Nessuna regressione: referti identici riga per riga

Confronto con `aa5c_confronta.py` (toglie solo tempi, impronta del codice, WARNING e id d'ordine generati):

| Registrazione | Scenari | HEAD | Nuovo | Righe | Differenze |
|---|---|---|---|---|---|
| 35797769 | media-under, media-under-paper, media-under-35, media-under-liquidita-100, media-under-35-liquidita-50, paper, base, sniper-paper | `replay/prima_8_35797769_r9.txt` | `replay/nuovo_8_35797769_r6.txt` | 181/181 | **solo** `TEMPO TOTALE` (1725,3 s vs 1734,6 s) |
| 35760084 | tutti i 15 scenari maker/sniper (base, auto-live, paper, ..., sniper-paper) | `replay/prima_s_35760084.txt` | `replay/nuovo_s_35760084.txt` | 243/243 | **solo** `TEMPO TOTALE` (289,6 s vs 306,7 s) |
| 35760084 | tutti i 14 scenari media-under-* | `replay/prima_m_35760084.txt` | `replay/nuovo_m_35760084.txt` | 331/331 | **solo** `TEMPO TOTALE` (455,8 s vs 511,6 s, sotto carico) |

Esiti 35797769 (uguali in HEAD e nuovo): OK media-under (5 azioni), media-under-paper (5), NE media-under-35 (0,
non esercitato come in HEAD), OK liquidita-100 (5), OK 35-liquidita-50 (6), OK paper/base (167), OK sniper-paper
(167). Su 35760084 i media-under sono NE come in HEAD; `auto-live` e' KO anche in HEAD (preesistente, non mio).

**Limite dichiarato**: il run di 35760084 e' di prima di tre ritocchi successivi (guardia del riquadro a 1,01,
lettura del libro del banco solo col pulsante, timbro del clic in `manda_clic`, `_DATETIME_VERO`). Per la modalita'
di sempre sono inerti: la guardia cambia solo il caso che in HEAD dava ZeroDivision (0 traceback nei referti di
HEAD), il libro e il timbro si attivano solo con `a_clic` o clic, `_DATETIME_VERO` solo nel buio dei prezzi; il
run 35797769 (r6) e' col codice finale salvo `_DATETIME_VERO`. Il rilancio degli 8 scenari su 35760084 col codice
finale e' stato NEGATO dal classificatore dei permessi (in linea con <<non lanciare altri replay>>): lo lasci al
coordinatore, comando `python -m Betfair.stream.backtest.certifica scalper_calcio 35760084 --data-dir <_live_raw>
--scenari media-under,media-under-paper,media-under-35,media-under-liquidita-100,media-under-35-liquidita-50,paper,base,sniper-paper --worker 1`
e confronto con `replay/prima_m_35760084.txt` / `prima_s_35760084.txt`.

## 7. Scenari nuovi e risultati del replay

18 scenari (`SCENARI_MEDIA_CLIC`, `replay_registrazioni.py:194`), clic posti dalla regola `clic_della_regola`
(`:347`): lontano = primo book + 600 s; vicino = KO-900 s; finestra = KO-200 s; gioco = primo tratto in gioco
>=300 s, +60 s; prima del gol -25 s; dopo il gol +3 s; sospeso = sospensione piu' lunga +0,3 s.
Nomi: `media-clic-lontano`, `media-clic-lontano-paper`, `media-clic-lontano-filtri`, `media-clic-lontano-35`,
`media-clic-finestra`, `media-clic-gioco`, `media-clic-gioco-35`, `media-clic-prima-del-gol`,
`media-clic-prima-del-gol-35`, `media-clic-dopo-il-gol`, `media-clic-sospeso`, `media-clic-prezzi-fermi`,
`media-clic-doppio`, `media-clic-in-posizione`, `media-clic-riavvio`, `media-clic-due-clic` (Under 3,5),
`media-clic-tick-1`, `media-clic-tick-1-filtri`.

**35797769** (r5 + r8 per doppio/in-posizione + r10 per prezzi-fermi; codice finale):

| scenario | esito | azioni | cicli (origine/fase) | NETTO EUR | violazioni |
|---|---|---|---|---|---|
| lontano | OK | 11 | clic/pre | +0,15 | 0 |
| lontano-paper | OK | 11 | clic/pre | +0,15 | 0 |
| lontano-filtri | OK | 11 | clic/pre | +0,15 | 0 |
| lontano-35 | OK | 10 | clic/pre, auto/pre | +0,26 | 0 |
| finestra | OK | 4 | clic/pre | +0,17 | 0 |
| gioco | OK | 2 | clic/gioco | +0,17 | 0 |
| gioco-35 | OK | 2 | clic/gioco | +0,13 | 0 |
| prima-del-gol | OK | 15 | clic/gioco | +1,51 | 0 |
| prima-del-gol-35 | OK | 12 | clic/gioco | +53,26 | 0 |
| dopo-il-gol | OK | 13 | clic/gioco | +0,10 | 0 |
| sospeso | NE | 13 | clic/gioco | +2,84 | 0 |
| prezzi-fermi | OK | 0 | - (rifiutato: prezzi fermi) | 0,00 | 0 |
| doppio | OK | 11 | clic/pre | +0,15 | 0 |
| in-posizione | OK | 11 | clic/pre (2o clic rifiutato) | +0,15 | 0 |
| riavvio | OK | 11 | clic/pre | +0,15 | 0 |
| due-clic | OK | 4 | clic/gioco, clic/gioco | +0,28 | 0 |
| tick-1 | OK | 31 | clic/pre, auto/pre, auto/pre | +0,44 | 0 |
| tick-1-filtri | OK | 28 | clic/pre, auto/pre, auto/pre | +0,44 | 0 |

Note: prima-del-gol-35 rientri fino a 457 EUR piazzati / 746 puntati, ciclo chiuso +56,06 lordo. sospeso NE: la
sospensione dura 3 s, meno del battito, il clic arriva a mercato riaperto (dichiarato). prezzi-fermi: buio dei
prezzi a 15'15", clic rifiutato <<prezzi fermi>>. doppio: il primo clic e' sovrascritto prima del battito (uno
solo eseguito). in-posizione: 2o clic a 14'05" rifiutato (posizione aperta). tick-1: rientri automatici a 33'29"
e 15'22" subito dopo ogni chiusura (M16 sollecitato); tick-1-filtri: rientro automatico dopo 11' coi filtri
(M17 x7582).

**35760084** (r7 + r10 per prezzi-fermi; codice finale):

| scenario | esito | azioni | cicli | NETTO EUR | violazioni |
|---|---|---|---|---|---|
| lontano | OK | 12 | clic/pre | -172,56 | 0 |
| lontano-paper | OK | 12 | clic/pre | -172,56 | 0 |
| lontano-filtri | OK | 12 | clic/pre | -172,56 | 0 |
| lontano-35 | OK | 12 | clic/pre | -299,34 | 0 |
| finestra | OK | 15 | clic/pre | -178,33 | 0 |
| gioco | OK | 10 | clic/gioco | -99,89 | 0 |
| gioco-35 | OK | 4 | clic/gioco | +0,13 | 0 |
| prima-del-gol | OK | 15 | clic/gioco | -122,53 | 0 |
| prima-del-gol-35 | OK | 12 | clic/gioco | -288,54 | 0 |
| dopo-il-gol | OK | 15 | clic/gioco | -155,77 | 0 |
| sospeso | OK | 0 | - (rifiutato: mercato SUSPENDED) | 0,00 | 0 |
| prezzi-fermi | OK | 0 | - (rifiutato: prezzi fermi) | 0,00 | 0 |
| doppio | OK | 15 | clic/pre | -165,40 | 0 |
| in-posizione | OK | 15 | clic/pre (2o rifiutato) | -165,40 | 0 |
| riavvio | OK | 12 | clic/pre | -127,06 | 0 |
| due-clic (U3,5) | OK | 10 | clic/gioco, clic/gioco | +0,40 | 0 |
| tick-1 | OK | 12 | clic/pre | -116,83 | 0 |
| tick-1-filtri | OK | 12 | clic/pre | -116,83 | 0 |

Le perdite vengono dall'Under che perde dopo i gol, con rientri fino a 1284-1433 EUR piazzati (parzialmente
abbinati): e' la decisione D7 per l'utente.

**Controlli M12-M18** (registro separato, `certificazione.py:2009-2191`): M12 ogni prima punta ha il suo clic o
e' un rientro automatico pre-match; M13 nessun ordine a mercato sospeso/chiuso; M14 prima punta allo stake base
al miglior prezzo; M15 ogni clic eseguibile ha la sua prima punta entro 15000 ms (`reazione_clic_ms` =
`stream_muto.SOGLIA_S` x 1000); M16 rientro automatico entro 15 s coi filtri spenti; M17 coi filtri accesi il
rientro rispetta i filtri; M18 rientro dovuto entro 15 s anche in gioco e nella finestra. Sollecitati: M12/M14
fino a x11461, M13 fino a x23, M15 fino a x11455, M16 x1 (tick-1, lontano-35), M17 x7582 (tick-1-filtri), M18
fino a x19. M7 (esenzione) e M9 (finestra) valgono solo per gli ordini non del pulsante; il force-flat per tutti.

**Contratto** (`replay/contratto_35760084.txt`): paper dal_ms=KO-20' (0 ordini, accensione 2047 s dopo l'inizio);
sniper-paper dal_ms=gioco+5' (0 ordini, `sniper_stake` sostituito); media-under-paper dal_ms=gioco+5' liquidita'
100: 15 ordini, primo dopo dal_ms, NETTO -178,33; media-under-paper dal_ms=KO-40' + clic_ms=[gioco+20']: 15 ordini,
NETTO -127,03, il clic rifiutato <<gia' in posizione (stato MASSIMO, 127,06 EUR puntati)>>. 0 violazioni.

**Tempi (LENTO, oltre il tetto del banco di 600 s, dichiarato e non rifatto)**: 35797769 da 190 a 320 s per
scenario, r5 4090 s totali; 35760084 da 45 a 134 s per scenario, r7 1508 s (sotto carico, piu' replay in
parallelo). Gli 8 scenari di sempre su 35797769: 1725 s in HEAD, 1735 s nuovo (nessun rallentamento).

## 8. Contratto per l'altro delegato (applica_bot / registro)

- `certifica_scenario(event_id, *, data_dir, scenario="base", ..., parametri: Optional[Dict]=None,
  dal_ms: Optional[int]=None, clic_ms: Optional[List[int]]=None)` (`replay_registrazioni.py:3043`): parametri
  validati da `valida_parametri` (`:489`, ValueError chiaro su chiave sconosciuta, tipo o dominio); `clic_ms`
  solo per gli scenari media (ValueError altrimenti); `dal_ms` accende la sessione tardi (maker/sniper con
  strategia segnaposto fino a dal_ms).
- `parametri_modificabili(scenario)` (`:460`) -> lista di dict con chiave, etichetta, tipo, default, min, max,
  passo, unita, gruppo. Chiavi ESATTE:
  - scenari media: `media_stake, media_obiettivo, media_tick_chiusura, media_tick_rientro, media_max_rientri,
    media_rischio_max, media_quota_min, media_quota_max, media_min_size, media_min_flow,
    media_max_spread_ticks, media_stop_ingressi_s, media_ttl_punta_ms, media_commissione_pct,
    media_rientro_auto_filtri`;
  - scenari maker: `scalp_ticks, stop_ticks, min_size, min_flow, price_min, price_max, entry_stop_before_s,
    flatten_before_s, event_profit_target, event_loss_cap, one_green_per_phase`;
  - scenari sniper: le maker + `sniper_stake`.
- La riga del registro e la rigenerazione del catalogo di Applica bot le fa il coordinatore.

## 9. Cosa NON ho fatto / NON ho potuto verificare

- UI non vista a schermo (solo vitest + tsc); `npm run build` non lanciato (l'app la gestisce l'utente).
- RPC non provata su Supabase (migrazione non applicata, per regola).
- Suite intera `Betfair/` non lanciata: solo il perimetro scalper/media/replay/registro/contratto (1105 test).
- Rilancio finale degli 8 scenari di sempre su 35760084 col codice finale: negato dai permessi (par.6).
- Latenza in produzione su mercati quieti: il clic si esegue al book DOPO la consegna; senza book (mercato
  fermo) aspetta. Proposta: un `CustomEvent` di flumine per eseguirlo subito (non fatto: cambia il ciclo della
  sessione).
- R4, R5/R5b non diventano rosse a livello di replay (spiegato al par.3; rosse sui test unitari).
- Incidente: scritto per errore un archivio di HEAD nella cartella `scratchpad/base` di un altro delegato;
  commit identico (8226d76), contenuto identico; gia' segnalato al coordinatore.

## 10. Decisioni per l'utente (strategia)

- D1 **Scadenza del clic 120 s**: un clic non eseguito entro 2' (sessione lenta, mercato fermo) e' rifiutato.
  Proposta: tenere.
- D2 **Clic non accodato**: un clic a posizione aperta e' rifiutato (non si esegue a fine ciclo). Proposta:
  tenere.
- D3 **Prima punta del clic non abbinata** (scade il TTL): si torna in `ATTESA_CLIC` (non riparte da sola).
  Proposta: tenere.
- D4 **Rientro automatico senza filtri anche nella finestra di stop** pre-match (di serie). Con
  `media_rientro_auto_filtri` = true aspetta i filtri. Proposta: tenere il default come ordinato.
- D5 **Clic su una sessione accesa nel modo di sempre senza posizione**: la sessione diventa <<a clic>> (le
  regole dei nuovi cicli valgono da li'). Proposta: tenere.
- D6 **Freno dei soldi veri**: vale anche per il clic (il clic non lo salta). Proposta: tenere.
- D7 **Rischio <<salto di prezzo>>**: sulla 35760084 i cicli del pulsante perdono da -99,89 a -299,34 EUR, con
  rientri fino a 1284-1433 EUR piazzati dopo i gol, perche' `media_rischio_max` e' spento di serie. Proposta:
  impostare un `media_rischio_max` (es. 30-50 EUR) prima dei soldi veri.
- D8 **<<Prezzi fermi>>** = vivacita' dello stream (`stream_muto`, soglia 15 s), non assenza di variazioni del
  prezzo. Proposta: tenere.

## 11. Da controllare dal vivo in prova al prossimo avvio

1. Applicata la migrazione: clic <<Attiva adesso>> a sessione accesa -> in `scalper_control.params` compare
   `media_attiva_adesso {id, ts}`; entro un book in `stats.media_comando` l'esito `eseguito` e in `scalper_trades`
   una punta allo stake base al miglior prezzo.
2. Ciclo chiuso pre-match: evento `media_rientro_automatico` e nuova punta entro pochi secondi; chiuso in gioco:
   stato `ATTESA_CLIC` nella scheda, nessun ordine fino al clic.
3. Riavvio del servizio dopo un clic: nessuna seconda punta per lo stesso id (`stats.media_comando.id` invariato).
4. Clic a posizione aperta: nella scheda <<rifiutato: gia' in posizione>>.

## 12. Catalogo par.7 (PROCESSO_STANDARD_BOT.md)

| # | Applicabile | Come e' coperto |
|---|---|---|
| 1 grafie chiavi | si' | chiavi del comando lette/scritte da costanti uniche (`CHIAVE_*`), RPC e UI con lo stesso nome; test che le chiavi siano in `UI_PARAM_WHITELIST` |
| 2 `res.ok` mai letto | si' | `set_control` torna bool: scrittura fallita -> `annulla_comando`, il clic NON si esegue (mutazione 12 rossa) |
| 3 campo inesistente | si' | finti con le stesse chiavi del vero; il clic legge `best_back` dal book vero del banco (M14) |
| 4 ref diverso | no | nessun ref nuovo (ordini della modalita' di sempre) |
| 5 closes_trade_id | no | non toccato |
| 6 ref senza mercato | no | non toccato |
| 7 bet_id solo se abbinato | no | non toccato |
| 8 fill a mano | si' | matching di flumine, nessun fill scritto |
| 9 ladder con getattr su dict | si' | M14 rilegge il book vero su cui nasce l'ordine |
| 10 status Enum | si' | `vivo_o_in_volo` di sempre; R7 rossa |
| 11 tetti di flumine | no | invariati |
| 12 bet delay | si' | in gioco col bet delay del banco (scenari gioco/prima-del-gol) |
| 13 fill sfiorato | no | matching flumine |
| 14 paper piu' generoso | si' | stessa strada paper/live; lontano vs lontano-paper identici |
| 15 snapshot a mano | si' | scanner/registrazioni vere, nessuno snapshot scritto |
| 16 falso positivo del controllo | si' | trovato e corretto (M18 a processo morto, NE nei rifiuti) |
| 17 sospeso vs chiuso | si' | M13; clic a mercato sospeso rifiutato (sospeso 35760084), test 5a/5b rossi |
| 18 CHECK del DB | si' | nessuno stato nuovo nel DB: `ATTESA_CLIC` vive nelle stats JSON, non in una colonna con CHECK |
| 19 stato in RAM perso al riavvio | si' | id consumato riletto dalle stats (mutazione 17 rossa, scenario riavvio OK) |
| 20 battito vivo != coda | si' | prezzi fermi = stream_muto (R6 rossa) |
| 21 paper+live sommati | si' | nessun conteggio nuovo |
| 22 bot che riparte da solo all'avvio | si' | il clic e' consumato una volta e scade a 120 s: un riavvio non riaccende |
| 23 stats riscritte per intero | si' | la consegna scrive le stats COMPLETE della sessione (`_stats()`, impronta compresa) con dentro `media_comando`: nessuna cancellazione |
| 24 RPC che azzera i params | si' | la RPC nuova fa `params || {...}`: non tocca gli altri params |
| 25 modalita' ereditata | si' | `media_a_clic` per riga/strategia |
| 26 execution_mode | no | non toccato |
| 27 finti diversi dal vero | si' | `_DbFinto.set_control` torna bool come il vero; flusso finto con classe `MarketStream` |
| 28 test che asserisce il sbagliato | si' | test riletti sulla regola definitiva |
| 29 test a vuoto | si' | ogni test falsificato |
| 30 mutazioni non catturate | si' | par.3 (sopravvissute spiegate) |
| 31 copie di laboratorio | si' | classi di produzione, punto d'ingresso unico del banco |
| 32 PARTIAL contate | si' | entrambe le registrazioni [COMPLETE] |
| 33 costante frontend duplicata | si' | `ATTESA_ESITO_CLIC_MS` e' solo attesa della UI; chiavi in un posto |
| 34 protezione dopo la riconciliazione | si' | force-flat e protezioni prima del comando (`_puo_gestire`) |
| 35 test verde mai rosso | si' | tutto falsificato |
| 36 famiglia K | si' | M12-M18 guardano ordini e book, non le attivita' del bot |
| 37 pool non isolata | si' | `--worker 1`, cache azzerate dal banco di sempre |

Firma: replay rieseguiti di persona dal delegato (r5-r10, 07/10 08:48-10:20); la ri-esecuzione del coordinatore
e' ancora dovuta.
