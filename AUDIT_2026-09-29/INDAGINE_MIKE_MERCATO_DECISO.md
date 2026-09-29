# INDAGINE MIKE - che cosa fa dopo il gol che DECIDE l'Under/Over 3,5 (29/09/2026)

Partita registrata 35760084 (Liepajas Metalurgs - Ogre United, 4-0), master `9692eb4`, sola lettura
sul codice di produzione. Orari: **ora italiana (UTC+2)** salvo dove scritto "UTC".
Posizione di Mike: punta Under 3,5 10,00 a 1,71 + copertura punta Over 4,5 4,00 a 4,00.

## In una riga

**DIFETTO SI', money-critical.** Dopo il quarto gol Mike fa il conto giusto (Under 3,5 = -10,00 certo,
Over 4,5 al prezzo vivo) e propone l'uscita, ma **non la puo' eseguire**: il mercato 3,5, deciso e
chiuso da Betfair, viene scambiato per "flusso prezzi fermo" e questo blocca OGNI ordine sulla partita,
anche la chiusura dell'Over 4,5 che ha prezzi vivi. Nel replay: firma dell'utente alle 19:25:34 su
"chiudendo ora -2,54" -> 21 tentativi rifiutati (`no_fill feed_stantio`) -> partita finita **-14,00**.
Danno in questa partita: **11,46 EUR** (con la copertura nuova come banca Under 4,5: **12,03 EUR**).

---

## Fatto nuovo sulla registrazione (corregge la scheda e il brief)

Il mercato 3,5 non "smette di aggiornarsi" per un guasto: **Betfair lo CHIUDE e lo regola** appena la
linea e' superata. Nella registrazione grezza dello stream (`_live_raw/35760084/35760084.raw.jsonl`,
`marketDefinition.status`) il mercato `1.259475537` (OVER_UNDER_35) passa a **CLOSED alle 19:25:25**
(17:25:25 UTC) con Under 3,5 LOSER e Over 3,5 WINNER. Stessa cosa, nella stessa partita, per
l'Over/Under 0,5 (18:09:10), 1,5 (18:29:42) e 2,5 (18:47:57), subito dopo il 1o, 2o e 3o gol. Verificato
anche su altre 3 registrazioni (35674515, 35764745, 35768297): ogni linea O/U chiude pochi secondi dopo
essere stata superata; in 35674515 il 3,5 chiude alle 12:06 UTC e il 4,5 solo alle 12:15 UTC (dopo il
quinto gol). Il file "ridotto" `35760084.jsonl` mostra come ultima riga SUSPENDED perche' non porta la
chiusura: e' la stessa cosa che vede il replay (vedi domanda 3).

---

## Domanda 1 - Che conto fa Mike per "chiudendo ora" dopo il gol decisivo?

**Il conto e' giusto.** Usa l'esito CERTO della gamba decisa (-10,00, senza nessun prezzo) piu'
l'incasso della gamba Over 4,5 al prezzo VIVO del momento. Il prezzo fermo dell'Under 3,5 non entra.

Dove: `Betfair/mike/engine.py`
- `selection_decided` (righe 666-677): con 4 gol la linea 3,5 e' superata -> Under 3,5 = PERSO (`False`).
- `cashout_value` (righe 933-1005): per una selezione decisa (righe 953-956) vale `L` = -10,00, "senza
  prezzo"; per quelle ancora in gioco calcola la chiusura sul book (righe 957-972). La commissione si
  toglie per mercato solo sul positivo (righe 983-992).
- `live_open_selections` (832-835): toglie le selezioni decise dalle "gestibili".
- `_decide_covered` (4067-4083) chiama `cashout_value(..., goals=snap.goals)` (riga 4072).
- `posizione_per_selezione` (1651) e' la stessa aritmetica per la UI; non cambia questo conto.

Dati del replay (sonda sul punto d'ingresso di produzione, scenario `base`):

**Proposta n. 11 - PRIMA del quarto gol (19:23:48, minuto 61, 3 gol)**. Prezzi: Under 3,5 banca 5,1;
Over 4,5 banca 2,22.
- Under 3,5 (punta 10,00 a 1,71): se vince +7,10, se perde -10,00. Banca per pareggiare = 17,10 / 5,1 =
  3,35 -> bloccato -10,00 + 3,35 = **-6,65**.
- Over 4,5 (punta 4,00 a 4,00): se vince +12,00, se perde -4,00. Banca = 16,00 / 2,22 = 7,21 ->
  bloccato **+3,20** (lordo). Netto commissione 5%: 3,20 x 0,95 = 3,04.
- Chiudendo ora = -6,65 + 3,04 = **-3,61** (il referto della sonda: -3,61; telemetria
  `per_gross {'OU35|UNDER': -6.65, 'OU45|OVER': 3.2}`).

**Proposta n. 12 - DOPO il quarto gol (19:25:33, minuto 64, 4 gol)**. Prezzi: Over 4,5 banca 1,35; il
libro del 3,5 non c'e' piu' (e non serve).
- Under 3,5: **deciso, perso = -10,00** (telemetria `decided ['OU35|UNDER']`).
- Over 4,5: banca = 16,00 / 1,35 = 11,85 -> bloccato -4,00 + 11,85 = **+7,85** lordo -> 7,46 netto.
- Chiudendo ora = -10,00 + 7,46 = **-2,54** (sonda: -2,54).

**Proposta n. 17 (19:41:34, minuto 79)**: Over 4,5 banca 2,02 -> banca 7,92 -> +3,92 lordo -> 3,72 netto
-> -10,00 + 3,72 = **-6,28** (sonda: -6,28).

Nota: fra il gol (19:23:59) e la riga che porta il 4-0 a Mike (19:25:17) i mercati sono sospesi: in
quei giri il conto e' "prezzi incompleti" (manca il prezzo di chiusura), e' corretto.

---

## Domanda 2 - Perche' dalle 19:41 non nasce piu' nessuna proposta?

**Non e' il flusso fermo e non sono tentativi esauriti.** Le proposte 12-17 sono nate TUTTE col flusso
gia' dichiarato fermo (dalle 19:25:25). Dopo le 19:41:47 il modello di Mike dice "tengo" perche' il
valore di chiudere scende PIU' IN FRETTA della soglia; dopo il minuto 85 la finestra delle uscite in
perdita del secondo tempo e' chiusa e non si calcola piu' niente.

Il meccanismo (`engine.py`):
- `_loss_rule` (4057-4064): finestra 2T attiva solo fra `h2_loss_from_min`=46 e `h2_loss_to_min`=85
  (`config.py:300-301`).
- `loss_exit_model` (1400-1438): chiude se "chiudendo ora" >= "tenere" - premio (righe 1426-1437).
  Con 4 gol: tenere = P(4 gol finali) x (-14,00) + P(5+) x (+1,40); premio = 10% x P(4) x 14,00.
- Con la partita che scorre l'Over 4,5 si allunga (banca 1,98 -> 4,8) e "chiudendo ora" crolla
  (-6,12 -> -10,75), mentre la soglia scende meno (-6,29 -> -8,66): da 19:41:47 chiudere vale MENO di
  tenere -> "tengo" (motivo della decadenza della n. 17).
- Minuto 86 (primo giro 19:49:49): fuori finestra, `_loss_rule` = None -> solo "tengo" o "prezzi
  incompleti" (questi ultimi quando la banca dell'Over 4,5 manca dal libro, sempre piu' spesso a fine
  gara).

Candidati verificati: finestra 46-85 = SI' (dal 86'); soglie tollerate = regola a modello, SI' (fino
all'85'); controllo del flusso = NO per la NASCITA delle proposte (ma blocca l'ESECUZIONE, domanda 3);
"prezzi incompleti" = solo a tratti (banca Over 4,5 assente); tentativi esauriti = NO (nessuna chiusura
partita nello scenario base).

Nota secondaria (non cambia l'esito qui): dopo il quarto gol la "P(4 gol) di mercato" (il pavimento
prudente, `feed.implied_p4` righe 233-246) non si calcola piu' perche' vuole il libro del 3,5; il modello
usa solo la sua P(4). Controllato a mano alle 19:45:14: P(4) di mercato 54% contro 55% del modello, nessun
effetto. E' un ingresso della strategia: se cambiarlo lo decide l'utente.

### Tabella minuto per minuto (scenario base, ora italiana)

"Chiudendo ora" e "soglia" sono il minimo..massimo dei giri di quel minuto; "PROPOSTA xN" = giri in cui la
proposta era viva; FERMO(537) = mercato 3,5 dichiarato fermo, (534) = mercato 4,5.

| Ora IT | Min | Gol | Flusso prezzi (per Mike) | Over 4,5 punta/banca | Chiudendo ora | Soglia modello | Finestra | Motivi dei giri |
|---|---|---|---|---|---|---|---|---|
| 19:20 | 58-59 | 3 | vivo x50 | 1.95/2.04 | -3.76..-3.35 | -3.93..-3.69 | 2t | PROPOSTA x44; prezzi incompleti x3; tengo x3 |
| 19:21 | 59 | 3 | vivo x48 | 2.04/2.06 | -3.65..-3.38 | -3.92..-3.83 | 2t | PROPOSTA x48 |
| 19:22 | 59-61 | 3 | vivo x50 | 2.08/2.2 | -4.32..-3.62 | -4.05..-3.84 | 2t | PROPOSTA x44; tengo x6 |
| 19:23 | 61-62 | 3 | vivo x40 | 2.2/2.26 | -3.72..-3.61 | -4.60..-4.02 | 2t | PROPOSTA x36; prezzi incompleti x4 (gol alle 19:23:59) |
| 19:24 | - | - | nessun giro (tutti e due i mercati sospesi: nel replay il giro parte dai tick delle due linee) | - | - | - | - | - |
| 19:25 | 63-64 | 4 | vivo x4, FERMO(537) x22 dalle 19:25:25 | 1.22/1.34 | -2.63..-2.46 | -2.60..-2.44 | 2t | PROPOSTA x17 (n. 12, 13); tengo x8; prezzi incompleti x1 |
| 19:26 | 64 | 4 | FERMO(537) x48 | 1.3/1.34 | -2.54..-2.46 | -2.60 | 2t | PROPOSTA x48 |
| 19:27 | 64-66 | 4 | FERMO(537) x45 | 1.34/1.36 | -2.79..-2.54 | -2.97..-2.60 | 2t | PROPOSTA x35 (n. 14); tengo x10 |
| 19:28 | 66-67 | 4 | FERMO(537) x45 | 1.35/1.38 | -2.87..-2.63 | -3.17..-2.97 | 2t | PROPOSTA x45 |
| 19:29 | 67 | 4 | FERMO(537) x49 | 1.38/1.41 | -3.25..-2.87 | -3.17 | 2t | PROPOSTA x39; tengo x10 |
| 19:30 | 67-69 | 4 | FERMO(537) x43 | 1.42/1.45 | -3.46..-3.25 | -3.58..-3.17 | 2t | tengo x28; PROPOSTA x15 (n. 15 alle 19:30:38) |
| 19:31 | 69-70 | 4 | FERMO(537) x49 | 1.44/1.47 | -3.60..-3.46 | -3.80..-3.58 | 2t | PROPOSTA x49 |
| 19:32 | 70-71 | 4 | FERMO(537) x50 | 1.47/1.5 | -3.86..-3.60 | -4.02..-3.80 | 2t | PROPOSTA x50 |
| 19:33 | 71-72 | 4 | FERMO(537) x43 | 1.5/1.55 | -4.00..-3.86 | -4.25..-4.02 | 2t | PROPOSTA x43 |
| 19:34 | 72-73 | 4 | FERMO(537) x46 | 1.51/1.56 | -4.30..-4.00 | -4.50..-4.25 | 2t | PROPOSTA x46 |
| 19:35 | 73-74 | 4 | FERMO(537) x48 | 1.59/1.62 | -4.54..-4.24 | -4.76..-4.50 | 2t | PROPOSTA x48 |
| 19:36 | 74-75 | 4 | FERMO(537) x43 | 1.57/1.68 | -4.86..-4.36 | -5.05..-4.76 | 2t | PROPOSTA x43 |
| 19:37 | 75-76 | 4 | FERMO(537) x40 | 1.68/1.73 | -5.21..-4.80 | -5.34..-5.05 | 2t | PROPOSTA x40 |
| 19:38 | 76-77 | 4 | FERMO(537) x45 | 1.75/1.8 | -5.40..-5.12 | -5.64..-5.34 | 2t | PROPOSTA x45 |
| 19:39 | 77-78 | 4 | FERMO(537) x41 | 1.63/1.8 | -5.76..-5.35 | -5.95..-5.64 | 2t | PROPOSTA x41 |
| 19:40 | 78 | 4 | FERMO(537) x43 | 1.77/1.93 | -6.12..-5.68 | -5.95 | 2t | PROPOSTA x28; tengo x15 (n. 15 decade 19:40:40) |
| 19:41 | 78-79 | 4 | FERMO(537) x40 | 1.97/2.04 | -6.49..-6.12 | -6.29..-5.95 | 2t | PROPOSTA x22 (n. 16, 17); tengo x18 (ultima decadenza 19:41:47) |
| 19:42 | 79 | 4 | FERMO(537) x39 | 2.04/2.14 | -6.77..-6.56 | -6.29 | 2t | tengo x39 |
| 19:43 | 79-82 | 4 | FERMO(537) x42 | -/2.2 | -7.72..-6.70 | -7.38..-6.29 | 2t | tengo x42 |
| 19:44 | 82-83 | 4 | FERMO(537) x45 | 2.5/2.7 | -8.34..-7.67 | -7.79..-7.38 | 2t | tengo x45 |
| 19:45 | 83 | 4 | FERMO(537) x45 | 2.84/2.92 | -9.70..-8.25 | -7.79 | 2t | tengo x34; prezzi incompleti x11 |
| 19:46 | 83-85 | 4 | FERMO(537) x42 | 3.9/4.7 | -10.67..-10.10 | -8.66..-8.20 | 2t | tengo x37; prezzi incompleti x5 |
| 19:47 | 85 | 4 | FERMO(537) x22 | 4.1/4.8 | -10.75..-10.60 | -8.66 | 2t | tengo x22 |
| 19:48 | - | - | nessun giro (4,5 sospeso) | - | - | - | - | - |
| 19:49 | 86 | 4 | FERMO(537) x4 | assenti | incompleto | - | fuori finestra | prezzi incompleti x4 |
| 19:50 | 86 | 4 | FERMO(537) x36 | libro sottile | -12.88..-11.58 | - | fuori | prezzi incompleti x20; tengo x16 |
| 19:51 | 86-90 | 4 | FERMO(537) x34 | libro sottile | -13.24..-12.77 | - | fuori | prezzi incompleti x19; tengo x15 |
| 19:52 | 90-91 | 4 | FERMO(537) x32 | libro sottile | -13.58..-12.90 | - | fuori | prezzi incompleti x26; tengo x6 |
| 19:53 | 91 | 4 | FERMO(537) x2, FERMO(537,534) x1 dalle 19:53:04 | 46.0/- | incompleto | - | fuori | prezzi incompleti x3 |
| 19:54 | 92 | 4 | FERMO(537,534) x3 | assenti | incompleto | - | fuori | prezzi incompleti x3 (4,5 chiuso da Betfair 19:54:13) |

Correzione alla scheda (`SCHEDA_PARTITA.md`, riga 15 della tabella e note): fra 19:30:38 e 19:40:40 la
proposta n. 15 NON e' rimasta ferma "con soli avvisi di flusso fermo": e' stata ricalcolata a ogni giro
(PROPOSTA x40-50 al minuto) con l'Over 4,5 vivo, e decade solo quando il conto cambia verso.

---

## Domanda 3 - I 37 + 28 avvisi "flusso fermo": guasto vero o mercato deciso? Che cosa bloccano?

**Quasi tutti sono il mercato DECISO e CHIUSO scambiato per flusso fermo.** Conteggio dalla sonda:

| Episodio | Quando | Mercato | `flusso_interrotto` | `..._senza_rest` | Che cos'e' |
|---|---|---|---|---|---|
| A | 18:47:15-18:47:51 (36 s) | 4,5 | 1 | 1 | sospensione dopo il 3o gol: libro vuoto, vero "senza prezzi", breve |
| B | 19:25:25 -> fine | 3,5 | 35 | 26 | 3,5 DECISO e CHIUSO da Betfair (Over WINNER) |
| C | 19:53:04 -> fine | 3,5 + 4,5 | 1 | 1 | fine gara, anche il 4,5 chiude (19:54:13) |

Come nasce (catena, file:riga):
1. Scanner: `Betfair/safe_strategy/service.py` `flusso_evento` (803-830) mette fra i `mercati_fermi` ogni
   mercato della riga non vivo; salta solo i blocchi con stato CLOSED (`_blocco_chiuso`, 817 e 833-841).
   Il blocco del 3,5 resta nella riga per Mike (`_prune_opp_blocks` 1681-1716, marcato `decided`), ma nel
   replay il suo stato resta SUSPENDED (flumine non consegna alle strategie i book CLOSED:
   `flumine/baseflumine.py:157-159`), quindi finisce fra i fermi.
2. Mike: `Betfair/mike/feed.py` `flusso_esito` (119-128) controlla TUTTE e due le linee
   (`mercati_di_mike`, 107-116), senza guardare se una e' gia' decisa -> `vivo=False`,
   `mercato_fermo` (`Betfair/stream/flusso_prezzi.py` `valuta_riga` 168-177).
3. Snapshot: `feed.snapshot_from_row` (391-431): `feed_fresh=False` e `order_fresh=False` per TUTTA la
   partita (righe 428-431); il blocco 3,5 viene tolto (`ou_blocks` 177-185), il 4,5 resta con i prezzi.
4. Esecuzione: `Betfair/mike/service.py` `execute_place` (742-750): `if not feed_fresh` -> ordine
   annullato, `no_fill feed_stantio`, "in paper E IN LIVE". Stesso muro per le lay appoggiate
   (`_run_event` 4676-4689).
5. Ripiego REST (`_books_ripiego_rest` 1204-1231): legge solo i mercati fermi (il 3,5) e li accetta solo
   se OPEN: il 3,5 e' chiuso -> vuoto -> `flusso_interrotto_senza_rest` ("la posizione resta senza
   chiusura ne' copertura").

Che cosa BLOCCA, provato:
- **Uscita in perdita firmata dall'utente**: SI', bloccata. Sonda con la firma VERA di produzione
  (`service._request_approva_uscita`) sulla proposta n. 12 alle 19:25:34: `uscita_eseguita_su_approvazione`
  poi 21 `no_fill feed_stantio` sulla banca Over 4,5 a 1,34-1,36 (libro vivo), poi 20 tentativi
  esauriti, P&L finale **-14,00**. Controllo: stessa firma alle 19:20:22 (prima del 4o gol, flusso vivo)
  -> chiusura eseguita, P&L **-3,45**. Con uscite AUTOMATICHE la chiusura parte e viene rifiutata allo
  stesso modo (test `test_rosso_dopo_il_quarto_gol_...`).
- **Cash out in profitto e cash out "intelligente"**: SI', bloccati (passano da `execute_place`). In
  questa partita non servivano (Over 4,5 mai in profitto netto), ma con un quarto gol presto e l'Over
  4,5 corto il profitto non si potrebbe bloccare.
- **Cash out manuale dell'utente** (pulsante): SI', rifiutato con `flusso_interrotto`
  (`service._request_flatten` 3437-3448): il ripiego REST cerca solo il 3,5, che e' chiuso.
- **Rientro**: gia' vietato col flusso fermo (apertura); nessun rientro possibile in questo stato.
- **Proposte**: NON bloccate (il motore in `LIVE_COVERED` non guarda `feed_fresh`): l'utente vede
  proposte VERE che pero' non si possono eseguire. E' la parte piu' insidiosa.
- **Regolamento**: NON bloccato nel replay (P&L -14,00 regolato a fine gara).
- **Mike cieco sull'Over 4,5?** Nel replay NO per i CONTI (il libro del 4,5 resta e il conto e'
  giusto), SI' per le MANI (nessun ordine parte).

Effetto collaterale: dopo 20 tentativi rifiutati `_decide_closing` (engine 4172-4183) scrive
"FLAT chiuso (loss_2t)" con la posizione ancora aperta, e al giro dopo torna `LIVE_COVERED
"esposizione residua"`: etichetta falsa per un giro. Il testo "da 5095 s" degli avvisi e' sbagliato:
conta dal cambio di stato del MATCH_ODDS al fischio (`dal_ms` del blocco dell'evento,
`flusso_prezzi._con_eta` 180-186), non da quando il 3,5 si e' fermato.

**In produzione puo' andare PEGGIO (non riproducibile nel replay).** Lo scanner vero legge lo stream
con betfairlightweight (non flumine) e sul book vuoto di chiusura scrive `status = CLOSED` nel blocco
(`safe_strategy/service.py` `_apply_opp_book` 1279-1286). Allora il 3,5 esce dai "fermi", ma il servizio
di Mike legge "3,5 CLOSED" come "partita finita" (`service.py:4252-4253`, `status_closed`) e prende la
strada del REGOLAMENTO: rilegge i libri via REST, trova 3,5 regolato e 4,5 aperto
(`final_total_from_books` 1068-1078 -> None) e a ogni giro esce PRIMA di decidere (4292-4301). Mike e'
davvero cieco sull'Over 4,5 (nessun conto, nessuna proposta, nessuna chiusura) fino alla chiusura del
4,5; se il REST non rispondesse, dopo 2 ore (`_SETTLE_MAX_WAIT_S`, riga 52) regolerebbe sull'ultimo
punteggio (4350-4355). Provato col ciclo vero del servizio e i finti di `test_mike_service`
(`test_rosso_3_5_chiuso_da_betfair_...`: nessun comando, nessuna attivita'). Il replay non lo vede per
due limiti del banco: flumine non passa i book CLOSED (`baseflumine.py:157-159`) e
`MercatoFlumine.read_book` torna None (`banco_comune.py:1019-1023`, limite 8 del banco).

---

## Domanda 4 - Con la copertura NUOVA (banca Under 4,5, `cover_form=lay_under45`)?

**Stesso difetto, stessa gravita'.** Replay base con `cover_form=lay_under45` (solo in memoria):
banca Under 4,5 12,63 a 1,33 abbinata; dopo il quarto gol la chiave della posizione diventa l'Over 4,5
(`_chiave_ou45`, engine 766-800) e la chiusura e' una banca Over 4,5. Stessi avvisi (37 + 28), stesse
proposte (18), "chiudendo ora" alla n. 12 = **-2,14** (19:25:33). Con la firma alle 19:25:34: 21
`no_fill feed_stantio`, P&L **-14,17**.
- Dopo 4 gol: l'Under 4,5 e' vivo, ma la sua chiusura e' bloccata come sopra.
- Dopo 5 gol: 3,5 e 4,5 decisi -> `live_open_selections` vuoto -> `FLAT "nessuna esposizione
  gestibile"` (engine 4068-4070): non c'e' piu' niente da chiudere, il blocco non costa niente; il
  regolamento arriva dai due mercati chiusi (5 gol, `final_total_from_books`).
- Nota fuori perimetro: in questo scenario il controllo del banco J6 ("mai sovracopertura") scatta
  contando la banca Under 4,5 come se fosse una punta Over (12,63 contro 4,21): e' il controllo del
  banco da allineare alla forma nuova (lavoro dell'altro delegato), non un ordine in piu'.

---

## Domanda 5 - Difetto, caso minimo, test, correzione proposta

**Caso minimo**: posizione coperta, 4 gol, riga dello scanner col 3,5 fra i `mercati_fermi` e il 4,5
vivo -> lo snapshot esce `feed_fresh=False` e la chiusura dell'Over 4,5 non parte.

**Test** (nuovo, non committato): `Betfair/mike/tests/test_mike_indagine_mercato_deciso_2026_09_29.py`
(patch: `AUDIT_2026-09-29/INDAGINE_MIKE_MERCATO_DECISO.patch`). Prezzi presi dalla riga vera delle
19:25:33. Comando e esito sul codice di oggi (2,1 s):
```
python -m pytest Betfair/mike/tests/test_mike_indagine_mercato_deciso_2026_09_29.py -q -p no:cacheprovider
3 failed, 3 passed
```
- ROSSO `test_rosso_3_5_deciso_e_fermo_non_rende_stantia_la_linea_4_5_viva` (snapshot).
- ROSSO `test_rosso_dopo_il_quarto_gol_la_chiusura_over_4_5_arriva_al_mercato` (ciclo vero
  `run_once`, runner finto sul protocollo vero): oggi `no_fill feed_stantio`.
- ROSSO `test_rosso_3_5_chiuso_da_betfair_mike_resta_padrone_dell_over_4_5` (strada di produzione col
  3,5 CLOSED): oggi nessun comando e nessuna attivita'.
- VERDE (confine) `test_controllo_con_la_linea_4_5_ferma_la_partita_resta_ferma`.
- VERDE (confine) `test_controllo_con_3_gol_il_3_5_fermo_blocca_ancora`.
- VERDE (controllo del banco di prova) `test_controllo_senza_marcatura_fermo_la_chiusura_over_4_5_parte`:
  stessa posizione, stessi prezzi, senza marcatura "fermo" la chiusura arriva al runner (prova che il
  test rosso puo' diventare verde).

**Correzione MINIMA proposta (NON applicata)**:
1. `Betfair/mike/feed.py:107-116` `mercati_di_mike`: non passare a `flusso_esito` le linee gia'
   DECISE dal punteggio della riga (gol > linea). Il controllo del flusso guarda solo le linee ancora in
   gioco; una linea decisa non serve piu' a nessun ordine (il suo esito vale -10,00 senza prezzo). La
   regola del 28/09 resta intatta: linea viva ferma = nessun ordine (i due test di confine lo fissano).
   *Prova fatta*: applicata per qualche minuto SOLO nel mio worktree -> i due rossi su snapshot e ciclo
   diventano verdi, i tre di controllo restano verdi; poi ripristinata dalla copia
   (sha256 `acde6413...1266` identico all'originale, `git diff` vuoto).
2. `Betfair/mike/service.py:4252-4253` (`status_closed`) e `Betfair/mike/feed.py:420-422` (stato del
   mercato nello snapshot, preso dal blocco 3,5): con 4 o piu' gol il 3,5 CLOSED NON vuol dire "partita
   finita" finche' il 4,5 non e' CLOSED (o il MATCH_ODDS); lo stato del mercato va letto dalla prima
   linea ancora in gioco. *Non verificata*: la prova temporanea e' stata fermata dal sistema dei permessi
   dopo la prima modifica (ripristinata subito, hash `0e6c5d3a...2744` identico, `git diff` vuoto).
   Serve il permesso per provarla.
Alternativa per la 1 (piu' larga, sconsigliata): far saltare allo scanner i blocchi `decided` in
`flusso_evento` (`safe_strategy/service.py:814-821`); tocca lo scanner di tutti i bot.

Gravita' in soldi: in questa partita 11,46 EUR (firma a -2,54 contro -14,00 finali; 12,03 EUR con la
copertura nuova). In generale colpisce ESATTAMENTE il caso peggiore di Mike (4 gol, perdono entrambe le
gambe: perdita piena = stake Under + copertura) e lo rende non evitabile dal momento del quarto gol:
proposte visibili ma ineseguibili, pulsante cash out rifiutato, cash out in profitto impossibile.

---

## Come ho lavorato (riproducibile)

- Sonda di sola lettura `_sonda_tmp/sonda_mercato_deciso.py` nel mio worktree (il sistema non mi
  lasciava scrivere nella cartella temporanea fuori dal worktree; NON da committare, il coordinatore
  puo' cancellare `_sonda_tmp/`). Richiama `replay_registrazioni.certifica_scenario("35760084",
  scenario=...)` dentro `trasporto.contesto("mike","canale")` e avvolge `engine.decide`,
  `feed.flusso_esito` e `service._run_event` solo per LEGGERE (snap, decisione, telemetria, attivita').
  Le firme usano la funzione vera `service._request_approva_uscita`. Ambiente neutro del brief
  (`_sonda_tmp/lancia.sh`).
- 5 replay, uno alla volta, ~110 s ciascuno (base 108,2 s, 5804 decisioni = referto
  `mike_tutti_P2BIS_P5_2B.txt`; stessi conteggi di attivita'): base; base + firma dopo il 4o gol; base +
  firma prima del 4o gol (controllo); `lay_under45`; `lay_under45` + firma dopo il 4o gol.
- Registrazione grezza: `_sonda_tmp/stati_mercati_raw.py` (legge in streaming `marketDefinition.status`).

## Cosa NON ho potuto accertare

- Che lo scanner di PRODUZIONE scriva davvero `CLOSED` nel blocco 3,5 della riga (dedotto dal codice
  `_apply_opp_book` 1279-1286; nessun dato di produzione letto, DB vietato). Quale dei due rami
  (replay: "fermo" / produzione: "regolamento") capiti dal vivo va visto in paper al prossimo 4-0 con
  copertura.
- La correzione 2 non e' stata provata (permesso negato).
- L'effetto del pavimento prudente P(4) mancante e' stato controllato a mano su un solo giro.
- Liquidita' reale per la chiusura: nel replay il runner/flumine abbina sul libro registrato; dal vivo
  l'abbinamento a 1,35 non e' garantito.

## Da controllare in paper al prossimo avvio

Partita coperta che arriva a 4 gol: nell'attivita' di Mike (`mike_activity`) cercare subito dopo il
gol `flusso_interrotto` con `mercati` = id del 3,5, oppure `settle`/nessuna riga (ramo regolamento);
firmando una proposta in perdita, cercare `no_fill` con `reason: feed_stantio`. Se compare: e' questo
difetto.
