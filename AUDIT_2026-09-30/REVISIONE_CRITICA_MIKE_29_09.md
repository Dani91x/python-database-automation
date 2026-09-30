# REVISIONE CRITICA - lavoro del 29/09 su Mike e sul banco (revisore in sola lettura, 30/09)

Oggetto: `9048238..fc0428f` (49 commit), diff di `Betfair/mike`, `Betfair/stream/backtest`,
`Betfair/stream/motore_ordini.py`, frontend di Mike; referti `AUDIT_2026-09-29/replay/*`, referti
`AUDIT_2026-09-29/MIKE_P*.md`, mutazioni `AUDIT_2026-09-29/mutazioni_coordinatore/`.
Worktree del revisore su `fc0428f`. Nessun file del repo modificato (verificato: `git diff` vuoto
dopo ogni mutazione, hash identici). Niente replay lanciati.

## Cosa ho verificato di persona (in sintesi)
- Diff letto riga per riga: `engine.py` (+~800), `service.py` (+~520), `config.py`, `db.py`,
  `certificazione.py`, `motore_ordini.py`, `registro_bot.py`, `uscite_manuali.py`,
  `tools/replay_registrazioni.py`; 10 file di test esistenti modificati; `lib/mike.ts`.
- Suite `python -m pytest Betfair/mike -q -p no:cacheprovider` con l'ambiente neutro di
  `replay_mike.sh`: **1222 passed** (uguale a quanto dichiarato).
- Confronto automatico scenario per scenario di 8 coppie di referti (script mio: esito, tick,
  decisioni, azioni, stati, ordini, attivita', righe per stato, motivi dichiarati, fill, P&L,
  bet delay, motivi `xN`, tolti i tempi).
- 15 mutazioni mie (5 "sopravvissute del coordinatore dichiarate coperte" + 10 nuove), ripristino
  da copia con sha256: esiti in sez. 6.
- Letture di codice per ogni controllo "mai sollecitato" (A2, B6, G2, H1, H2, R1, R3, S1, S3, CP2).

---

## REPERTI ORDINATI PER GRAVITA'

### CRITICO

**C1 - (gia' accertato il 29/09, NON corretto, resta su master) dopo il gol che decide la linea 3,5
Mike non puo' eseguire nessuna uscita.** `Betfair/mike/feed.py` (`mercati_di_mike`/`flusso_esito`,
file non toccato il 29/09) + `service.py:~760` (ramo `if not feed_fresh` -> `no_fill feed_stantio`).
Riprodotto dall'indagine (`INDAGINE_MIKE_MERCATO_DECISO.md`, 3 test rossi non applicati): firma a
-2,54 -> 21 rifiuti -> -14,00. Lo cito perche' nessun referto del 29/09 lo fa vedere: tutti i 21
scenari dicono "OK, 0 violazioni" su una partita (35760084, 4-0) in cui il difetto c'e'. Aggiunta
mia, verificata sul codice (`service.py:4274-4446`): nella strada di produzione ipotizzata
dall'indagine (scanner che scrive `CLOSED` nel blocco 3,5 -> `status_closed` vero) il ramo di
regolamento chiama `E.decide`/`E.apply_decision` e **non esegue** le azioni: il `_cancel_live` della
decisione `SETTLING` (`engine.py:2801`) non parte mai, e il ramo esce prima di `_sorveglia_gambe`.
Quindi gli ordini vivi sul 4,5 (copertura in volo, banca del rientro) restano sul book creduti vivi
e non piu' seguiti, e dopo 2 ore (`_SETTLE_MAX_WAIT_S`) la partita si regolerebbe sull'ultimo
punteggio (4) anche se il 4,5 non e' chiuso. Riprodurre: test rossi della patch
`in_attesa_del_via/INDAGINE_MIKE_MERCATO_DECISO_test_rossi.patch`; per la parte degli annulli non
eseguiti: `run_once` con riga che porta `ou.OU35.status=CLOSED`, 4 gol, una gamba `over_cover`
`pending` -> nessun `cancel` inviato, gamba ancora `pending`. **Mike non va in live finche' C1 non e'
corretto e provato sul banco (che oggi non vede i mercati CHIUSI, vedi A6).**

Nessun altro difetto che costa soldi trovato nel codice nuovo (conti di `exposure` per mercato,
`cover_residual_lay` 12,63, `invested` col rischio della banca, cuscinetto +2 tick, liquidita' al
miglior prezzo, M3.5, ripiego M3.3, `uscita_in_perdita`, M8.3, M8.7, M6.2 ricontrollati a mano; il
motore ordini condiviso somma l'altra selezione col segno giusto: `motore_ordini.py:~1049`).

### ALTO

**A1 - G2, la regola piu' importante per l'utente, non puo' avere un caso sul banco di Mike, e anche
se l'avesse non vedrebbe l'errore piu' probabile.** `certificazione.py:~508-548`.
- `quando = _nasce_uscita_in_perdita(ctx, d)`: ordini piazzati + motivo di perdita + stato non di
  chiusura. `d` e' la decisione DOPO `gate_uscite`: a interruttore spento un'uscita in perdita non
  firmata diventa proposta senza ordini, quindi `quando` e' falso. G2 ha un caso SOLO se un'uscita in
  perdita parte davvero, cioe' se qualcuno firma (o se il bot sbaglia). Mike non ha nessuno scenario
  che firma (lo scenario comune `uscite-manuali-firmate` di `uscite_manuali.py` non e' registrato per
  Mike: `SCENARI_DESCRITTI` in `replay_registrazioni.py:~1255`; lo dice anche `MIKE_P1.md` par. 8) e
  nessuno scenario con `uscite_automatiche=True`. Risultato: x0 in TUTTI i referti, per costruzione.
- Anche sollecitato, G2 riconosce la "perdita" con la STESSA regola del motore (`_motivo_perdita` =
  copia di `engine.uscita_in_perdita`, `engine.py:2598`): un'uscita in perdita classificata male dal
  motore (motivo `profit` su una chiusura che blocca un negativo) passerebbe muta. Il commento
  "regola letta dal piano, non dal cancello del motore" non e' vero nei fatti.
- Mutazione mia B-5 (G2 senza il confronto della chiave firma/proposta): **VERDE**, nessun test la
  prende (il test esistente cambia solo il `close_reason`).
- Proposta (non implementata): scenario `uscite-in-perdita-firmate` per Mike che firma ogni proposta
  dopo N s di mercato per la via di produzione (`approva_uscita` in `process_requests`), piu' una
  variante `uscite-automatiche`; G2 riscritto sul NUMERO e non sul motivo: una chiusura che parte da
  uno stato non di chiusura con `cashout.net` (o `min(expected)` dei piani) < 0 senza firma valida
  per la chiave E il motivo = violazione; un controllo "firma eseguita" (come UF1/UF2) che pretende
  ordini a mercato entro N s dalla firma. Con quello scenario C1 sarebbe uscito dal banco da solo
  (21 rifiuti dopo la firma).

**A2 - R3 (chiusura fuori dall'app) non e' MAI stato provato dopo il passaggio del canale al paper,
e lo scenario `chiuso-fuori-app` dichiara "OK" senza aver provato niente.** `service.py:2893-2894`
(`if str(mode) == "paper": return False` in `_sorveglia_posizione_di_conto`) +
`replay_registrazioni.py:~418-434` (`modo_del_banco`: con `--trasporto canale` Mike gira in PAPER).
Il banco piazza i due ordini dell'utente (nota: "lay_di_chiusura_abbinata 13.0"), ma Mike in paper
non legge nessun conto: nessuna attivita' `posizione_di_conto`, `chiuso_dall_utente` mai acceso,
Mike continua come in `base` (stessi 6 ordini, copertura compresa, -14,00) e R3 x0 - la nota del
referto lo scrive ("sollecitato 0 volte") ma l'esito resta OK. Stesso x0 anche nel riferimento
`9048238`. La copertura del ramo live (`MercatoFlumine.list_account_orders` esiste,
`banco_comune.py:904`) c'e' solo nei test. Proposta: `chiuso-fuori-app` sul trasporto `coda` (live)
nel giro di certificazione, e sul canale dichiararlo ⊘ con causa invece di OK.

**A3 - I due scenari di rifiuto della copertura non rifiutano niente sul trasporto ufficiale.**
`mike_tutti_P5_4C.txt`, `[copertura-rifiutata] <canale>`: "Betfair rifiuta SEMPRE le banche" ma fill
22,63 = 10,00 + banca 12,63 abbinata a 1,33, P&L -14,17; `copertura-rifiutata-legacy` idem (4,26
abbinati). La leva di rifiuto di `banco_comune` non passa sul canale (dichiarato come limite (b) in
cronostoria). Sul referto di certificazione quindi S1/S3 x0 e due scenari "OK" che sono in realta'
`base` con un parametro diverso. S1/S3 hanno casi SOLO sulla coda (`mike_coperture_P5_4C.txt`: S1
x4520, S3 x4520, 1 rifiuto). Proposta: marcare lo scenario "NON ESERCITATO" quando la leva non ha
mai colpito (contatore dei rifiuti = 0), oppure portare la leva nel `MotoreOrdini` del banco.

**A4 - Il banco non isola gli scenari nello stesso processo (catalogo n. 37, di nuovo), e 18 scenari
su 21 girano con memorie del processo precedente.** `service.py` `_CACHE_DI_PROCESSO` (~riga 2763)
non contiene `_RIPIEGO_REST_ULTIMO`, `_ULTIMO_STATO_SCANNER`, `_FLUSSO_CRITICO`, `_FLUSSO_RIPIEGO`
(li conosce `svuota_le_cache`). Effetto misurato nei referti: primi 3 scenari 150 letture REST,
`flusso_interrotto_senza_rest x28`, tick 56098; gli altri 18: 0 letture, attivita' assente, tick
56229. Dichiarato dal delegato P5 e in cronostoria come "reperto del banco da mettere nel catalogo",
non corretto: ma e' esattamente il ramo "flusso fermo / ripiego REST" dove vive C1, e 18 scenari su 21
non lo esercitano come in produzione (processo nuovo). La correzione proposta e' di 4 nomi + un test.

**A5 - Lo standard "replay veloci" (ordine dell'utente del 29/09) non e' rispettato e il referto lo
presenta come rispettato.** `PROCESSO_STANDARD_BOT.md` par. 6.9: 5 minuti, tetto 10, **con
`--worker 1`**. Il referto finale dice "8m40,6 s su 21 replay | obiettivo 300 s, tetto 600 s" ma e'
con 3 processi (`--worker 0`); la somma dei tempi per scenario e' 1495 s (misurata da me sul
referto), e la cronostoria stessa (12:53) scrive "con --worker 1 Mike 22 minuti: sopra il tetto".
Nella chiusura del 29/09 (punto (e)) il tempo e' detto "sotto il tetto di 600". Va detto all'utente
che con la regola scritta Mike e' circa 2,5 volte sopra il tetto.

**A6 - Stati mai visti su nessun referto, e non elencati come chiede il par. 6.3.** Unione degli
stati di tutti i referti del 29/09: mancano `LIVE_SECOND_ENTRY` (caso B, decisione 11: seconda
puntata e tranche mai esercitate sul banco), `REENTRY_GREEN_PENDING`, `PRE_LAST_ENTRY_PENDING`,
`SETTLING`, `ERROR`, `SKIPPED`. In nessuno scenario con posizione la partita arriva al regolamento
("stato TERMINALE: la partita non ci e' mai arrivata"): il P&L del referto lo calcola il banco, non
`settle_legs`/`_settle_trades` di Mike (M8.6 mai provato sul replay). Causa nota (flumine non passa i
mercati CLOSED, limite (d)), ma il referto non elenca i mai visti per nome come vuole la definizione
di fatto.

**A7 - M8.11 (decisione 23, D11) non e' stata fatta.** Il piano: "far misurare la stessa attesa anche
al replay". `MIKE_P4_3.md` sez. 5: "PROPOSTA (non toccato)"; nel banco `S.ATTESA_ESITO_TAKER_MAX_S = 0`
(`replay_registrazioni.py:~505`). Non compare fra i debiti della chiusura del 29/09.

### MEDIO

**M1 - 19 righe CRITICAL "annullo NON confermato -> riconciliazione" nel referto finale (0 nel
riferimento), mai indagate.** `service.py:5386`; la causa nel banco e' `WsBanco` chiuso
(`porta_banco.py:182-193`, "socket del banco chiuso"). Nascono da P1/P2 (banche a mercato anche in
manuale, annullo al fischio della banca LAPSE, `engine.py:2997-3004`). Segnalato da `MIKE_P1.md`
par. 6 ("DA GUARDARE"), poi mai ripreso. Conseguenza: ogni annullo paper sul canale finisce in
riconciliazione (J4 x19, B3 x1): per `settle_confirm_s` le APERTURE (copertura compresa) sono tolte e
al fischio `_decide_ko_green` aspetta la banca (`engine.py:3405-3411`), consumando la finestra dei
3 minuti. Da stabilire se e' solo del banco o anche del runner di produzione.

**M2 - Lo scenario `chiusura-abbinata-in-parte` non ha mai prodotto una chiusura abbinata in parte.**
Nota del referto: 3 chiusure colpite, tutte "abbinato 0.00 ... [SENZA EFFETTO: mai abbinata, guasto
riarmato]" (sono le `ko_green` scadute). CP1 x12052, CP3/CP4 x4707 vengono contati lo stesso
(`chiusura_parziale.py:~716`, il conteggio non guarda `senza_effetto`): coperture "sollecitate" su
una condizione mai accaduta. CP2 e' dichiarato "NON APPLICABILE a Mike" nella nota ma resta `??` nella
tabella: va marcato ⊘.

**M3 - Mutazioni sopravvissute (mie) su punti dichiarati coperti.**
- B-6: in `_segui_resting_live` (`service.py:2457`) togliere `_ESITO_ABBINATO` dalla tupla (una banca
  uscita dai correnti e letta ABBINATA per bet_id resterebbe "ignota") -> **VERDE**: M6.2 e' provato
  solo col ramo "scaduto" (`test_ordine_uscito_dai_correnti_senza_sospensione...`).
- B-10: in `_copertura_banca` (`engine.py:~3921`) il tetto per partita col rischio al miglior prezzo
  invece che al limite -> **VERDE**: la regola "tetto sul rischio al prezzo LIMITE" non e' provata.
- B-5 (sopra, A1).
- Restano aperte anche T2 e T3 del coordinatore (E2 banca senza Under / piu' piccola senza tetto),
  dichiarate.

**M4 - M3.5 "lo scrive nel registro": non viene scritto.** Le telemetrie
`cover_resto_sotto_minimo` (`engine.py` `_copertura_banca` e `_riprezzo_copertura_banca`) e
`residuo_non_piazzabile` (`_tele_residuo`) non sono nella lista dei kind che il servizio scrive in
`mike_activity` (`service.py:4774-4787`): non arrivano ne' al DB ne' alla pagina. Resta solo il testo
del `reason` nella riga `state` quando lo stato cambia. `MIKE_P5_2.md` par. 3 dichiara "il resto non
sparisce: e' nella telemetria residuo_non_piazzabile" - vero in memoria, falso nel registro.

**M5 - M7.2 "nessuna esposizione" si dichiara sulla credenza del bot, non sugli ordini riletti da
Betfair** (piano, punto 7: "riletti da Betfair, non sulla convinzione del bot").
`frontend/src/lib/mikeEsitoChiusura.ts` usa `ev.positions` (gambe del bot). Divergenza dichiarata in
`MIKE_P6_2.md` par. 9 (serve `live.ordini_verificati_ts`), non portata all'utente come tale.

**M6 - Divergenze di condotta prese dal coordinatore/delegati e non dall'utente (dichiarate nei
referti, da portare all'utente come decisioni):**
- `tolleranza_piatto_ou45` (`engine.py:726`): sul 4,5 "piatto" fino a 0,005 x prezzo dell'ultima
  chiusura (~0,10 a quota 21) anche nella forma di serie: una partita che prima restava in
  LIVE_COVERED ora va FLAT e puo' rientrare. "decisione del coordinatore" (`MIKE_P5_2.md` par. 3).
- `_decide_flatten` (cash out/"Chiudi" dell'utente) ora ASPETTA se c'e' un'altra lay in volo, se il
  mercato e' sospeso o ignoto, e salta i mercati chiusi (`engine.py:~2382-2413`): tre cambi di
  condotta sul pulsante dell'utente fuori dal piano (P1 "FUORI PIANO", P5 4 e 4C).
- `reentry_time` resta da firmare anche quando chiuderebbe in profitto (`engine.py:2598`), dichiarato
  in `MIKE_P1.md` par. 10.
- Al fischio il motore manda comunque l'annullo della banca LAPSE (M2.1 dice "Mike non la ritira"),
  dichiarato in `MIKE_P2.md` par. 1; e' l'origine di M1.
- M3.3 "altrimenti il piazza e riduci di oggi": sotto 0,50 senza puntata piazzabile la banca di
  chiusura parte DIRETTA (`execution.py:768`, `sotto_minimo ... and not is_closing`), non col
  place-and-trim; che Betfair accetti via API una banca < 0,50 non e' verificato (`MIKE_P5_2.md`
  par. 9). Rischio: 20 rifiuti e chiusura ferma.

**M7 - `cover_form` e' gia' nel pannello su master, ma le etichette dell'app sono ancora quelle della
punta Over.** `lib/mike.ts:497` espone la scelta `lay_under45`; `investedOf` (`:1080`) conta solo i
`back`, `MIKE_ROLE_LABEL.over_cover` = "Copertura Over 4.5", la riga d'attivita' `cover` scrive
"copertura Over 4.5" (`:1513`), le fasi LIVE_* parlano di Over 4.5. `MIKE_P6_6.patch` e' in attesa.
Se l'utente cambia la forma dal pannello prima del "via", la pagina sbaglia etichette e capitale
impegnato. Proposta: nascondere/disabilitare la scelta fino all'integrazione di P5_5+P6_6.

**M8 - E2 della forma di serie (punta Over) e' debole.** `certificazione.py:430-438`: legge
`params["commission"]` e `params["cover_factor"]` che non esistono (vale sempre 0,05 e 1,2), segnala
solo un ordine oltre il 135 % del pieno, mai uno piu' piccolo. Dichiarato in `MIKE_P5_4.md` par. 2
come difetto noto, lasciato "per non cambiare il referto". La forma certificata di serie resta quella.

**M9 - Referti "identici" imprecisi (minori).** Confronto mio: `P3_P4_3 -> P4_4_P5_1`
dichiarato identico: cambiano le attivita' `feed_line_missing` (1 -> 0) in `bot-fermo` e
`feed-stantio` (spiegabile col ritardo a 10 s dell'avviso, non detto); `P4_4_P5_1 -> P2BIS`:
`punteggio-ko` oltre ai numeri dichiarati ha `mercato_sospeso x2` / `mercato_riaperto x2` nuovi (la
copertura aspetta attraverso una sospensione); `P5_3 -> P5_4C`: "17 identici" confermato, cambia solo
`copertura-rifiutata` (vedi A3). Tutte le altre dichiarazioni di identita' confermate (tabella sez.
4). R1: la consegna dice "nessun caso in nessun referto": falso, R1 x4578 in
`mike_coperture_P5_4C.txt` (coda); sul canale e' x0 per costruzione (in paper il runner fa scadere la
lay e il servizio lo legge prima di `_sorveglia_sospensione`: la riapertura non viene mai annotata).

**M10 - Test esistenti modificati: tutti giustificati da una decisione, nessuno piegato**, con due
note: `test_selezione_decisa_non_pretende_prezzo_e_non_congela` (engine_cert) cambia veicolo (uscita
2T fissa invece del tetto) mantenendo lo scopo - ok; `test_stesse_chiavi_del_finto_del_banco`
(P4) asserisce le chiavi del vero ma non le confronta con quelle del finto del banco (che ho
controllato io a mano: `banco_comune.py:872-883`, stesse chiavi). `AUDIT_2026-09-30/.../tabella.md`
non contiene righe di `mike_trades`/`mike_activity` (e' la tabella dell'indagine sul flusso): il
confronto dei finti l'ho fatto contro `db.py`/`omega_market.py`/`banco_comune.py`.

### BASSO
- `MOTIVI_PROTEZIONE = ("loss_cap",)` e il suo ramo in `gate_uscite` (`engine.py:2716`) sono codice
  morto; `last_entry_ticks_above`, `event_loss_cap_pct` restano nel pannello "NON ATTIVO".
- Etichetta HOLD "TIENE FINO AL FISCHIO" anche quando Mike e' piatto dopo il segno.
- M8.6 ramo "risultato indipendente": le righe si regolano con 0 gol (`service.py:4391`): totale
  giusto, ma ogni riga porta won/lost di una partita 0-0 (etichetta per riga inventata; c'e' la nota
  `settle_reason`).
- `esito_ordine` di una taker paper annullata da noi (es. `pending_stale`) viene scritto
  `non_abbinato_fok` (`service.py:~1700`).
- A2 x0 per costruzione (dichiarato nel referto); la sua falsificazione "dichiarata nel checkpoint"
  non ha un referto nel 29/09.
- B6 ha 1 solo caso (sintetica `_synth_mike_ultimo_ingresso`); nessun controllo verifica che
  l'ultimo ingresso AVVENGA quando Mike e' piatto (solo che non ce ne siano due).

---

## 4. Replay: confronti rifatti (script mio, tolte le righe dei tempi)
| Coppia | Scenari diversi | Esito |
|---|---|---|
| `9048238` -> `P1` | 13/15 | attese (banche a mercato: azioni 2->7, `error` x3, sospensione 0->1) |
| `P1` -> `P4_1` | 0 (+`fermo-copertura`) | identico, come dichiarato |
| `P4_1` -> `P2_P4_2` | 15/17 | attese P2 (annullo al segno tolto, LAPSE 0->1, veto "hold" sparito) |
| `P2_P4_2` -> `P3_P4_3` | 18/18 solo attivita' | condotta identica (avvisi per episodio) |
| `P3_P4_3` -> `P4_4_P5_1` | 2/18 solo attivita' | non dichiarato (M9) |
| `P4_4_P5_1` -> `P2BIS_505s` | 1/18 (`punteggio-ko`) | -14,00 -> -13,50 dichiarato in CRONOSTORIA (checkpoint 20:30 e 21:15) e in `MIKE_P5_4.md` par. 8; NON in `MIKE_P2BIS.md` |
| `505s` -> `2B` -> `P5_3` | 0 / 0 | identici |
| `P5_3` -> `P5_4C` | 1/18 + 3 nuovi | identici i 17 dichiarati; `copertura-rifiutata` cambia forma (A3) |
Tick 56098/56229 e 150/0 letture fra processi nuovi e riusati: non regressione ma A4.

## 5. Test
Suite `Betfair/mike` 1222 verdi rieseguita. Test esistenti modificati (10 file Python + 2 frontend)
letti uno per uno: vedi M10. Finti nuovi: il client Betfair di `test_mike_p4_ordini` parla con le
chiavi grezze (`betId`, `sizeMatched`, `sizeSettled`...) e passa dal vero `omega_market`; i finti di
riga usano le chiavi di `mike_events` (`positions`, `ctx`, `markets`). Un caso di finto dubbio:
`regolato(stato="LAPSED", regolato_eur=4.0)` per "abbinato in parte" (Betfair tiene la parte
abbinata fra i correnti fino al regolamento): innocuo per la classificazione.

## 6. Mutazioni (script mio, ripristino con sha256, `git diff` vuoto dopo)
Base: 1222 verdi.
| Mutazione | Esito | Test che la prende |
|---|---|---|
| A-Z1 fischio piatto con banca in volo | ROSSA | `test_mike_p2bis::test_z1_...[pending]` |
| A-W14 senza dati niente posizione di conto | ROSSA | `test_mike_p4_blocco4::test_live_riga_assente_la_chiusura_fuori_app_si_vede` |
| A-N13 banca con Under 4,5 sospeso | ROSSA | `test_mike_p5_4b::test_banca_con_under45_sospeso_non_parte` |
| A-N15 tranche della banca col minimo delle puntate | ROSSA | `test_mike_p5_4b::test_tranche_della_banca_sotto_0_50_...` |
| A-Q5 chiave del 4,5 sempre Under | ROSSA | `test_mike_p5_copertura_banca::test_due_selezioni_lunghe_...` |
| B-1 ultimo ingresso valutato piu' volte | ROSSA | `test_m2_4_ultimo_ingresso_non_abbinato_non_si_rifa` |
| B-2 banca abbinata dopo il segno -> nuovo giro | ROSSA | `test_m2_4_banca_abbinata_negli_ultimi_minuti_...` |
| B-3 liquidita' della banca non controllata | ROSSA | `test_liquidita_sotto_l_importo_...` |
| B-4 ripiego M3.3 con punta non piazzabile | ROSSA | `test_banca_over_sotto_0_50_resta_banca_...` |
| **B-5 G2 accetta la firma di un'altra chiave** | **VERDE** | nessuno |
| **B-6 M6.2 esito ABBINATO non applicato** | **VERDE** | nessuno |
| B-7 `reentry_time` come profitto | ROSSA | `test_chiusura_a_tempo_del_rientro_resta_governata` |
| B-8 M8.1 tolta | ROSSA | `test_m8_1_una_gamba_di_un_uscita_precedente_...` |
| B-9 posizione di conto letta in paper | ROSSA | `test_in_PAPER_non_si_legge_nessun_conto` |
| **B-10 tetto sul rischio al miglior prezzo** | **VERDE** | nessuno |
Nota di metodo: il primo giro del mio script era falso (Python lanciava il `bash` di WSL, pytest non
partiva e ogni mutazione risultava "rossa"); l'ho scoperto aggiungendo la corsa di base e rifatto
tutto chiamando pytest direttamente. Chi scrive script di mutazione deve sempre avere la base verde
nello stesso script.

## 7. Frontend
Tutte le 107 chiavi di `config.PARAM_SPEC` sono nel pannello (`lib/mike.ts`). `reentry_max_goals`
0-2 serie 2, `event_loss_cap_pct` e `last_entry_ticks_above` "NON ATTIVO", hint dell'interruttore
coerente (governa solo le uscite in perdita). Etichette punta/banca: vedi M7. Il valore SALVATO nel
DB di `reentry_max_goals` vince sul default: la migrazione `mike_reentry_max_goals_2026-09-29.sql`
non risulta applicata (non ho letto il DB).

---

## TABELLA DELLE DECISIONI (registro del piano: sono 26, non 24)
| # | Decisione | Fatta | Dove | Test | Divergenza / nota |
|---|---|---|---|---|---|
| 1 | banca pre-partita subito e sempre (M1.1) | si' | `engine.py:2598` `uscita_in_perdita`, `gate_uscite:2689` | `test_m1_1_*` | - |
| 2 | banca fino al fischio (M2.1) | si' | `engine.py:3068-3090` | P2 + D3 banco (x17578) | al fischio Mike manda comunque l'annullo (M6, M1) |
| 3 | mai in perdita pre-partita (M2.2) | si' | veto non chiude piu' | test veto | telemetria veto "hold" tolta |
| 4 | LAPSE + lettura al fischio (M2.3) | si' | `engine.py:3005-3013`, `3405-3417` | Z1, Z12 | sul canale provata solo col runner; live solo test |
| 5 | niente giri negli ultimi 10' | gia' cosi' | `_entry_guard` | - | - |
| 6 | ultimo ingresso da piatto (M2.4) | si' | `engine.py:3263` `_ultimo_ingresso` | P2, B6 x1 (sintetica) | pausa 60 s e valutazione unica: decisione aperta per l'utente |
| 7 | perdita pre-partita portata in live | si' | come 3 | - | - |
| 8 | dal fischio invariato | invariato | - | - | caso B mai visto sul banco (A6) |
| 9 | copertura = banca Under 4,5 (M3.1-M3.3) | codice si', **di serie NO** | `engine.py:3830`, `config.py:212` (`back_over45`) | P5 + scenari | attivazione (`MIKE_P5_5.patch`) in attesa del via: la decisione non e' ancora in vigore |
| 10 | caso A invariato | invariato | - | - | - |
| 11 | caso B invariato | invariato | - | - | mai esercitato sul banco |
| 12 | cash out profitto da solo (M4.1) | si' | `gate_uscite` | `test_m4_1_*` | - |
| 13 | tutte le uscite in profitto da sole | si' | idem | P1 | `reentry_time` sempre da firmare (M6) |
| 14 | cash out intelligente invariato | si' + M8.4 | `engine.py:1299` | P2-bis | col punteggio assente non scatta |
| 15 | consapevolezza degli ordini | parziale | - | - | C1, M1, M4 |
| 16 | uscita in perdita = proposta | invariato | `gate_uscite` | test | G2 mai sollecitato (A1) |
| 17 | annullo copertura bancando l'Over (M3.3) | si' (dietro interruttore) | `engine.py:903`, `_close_actions` | B11/B12, B-4 | sotto 0,50 banca diretta, non place-and-trim (M6) |
| 18 | tetto di perdita tolto (M4.5) | si' | `engine.py:4160` | `test_m4_5_*`, G2 unit | codice morto `MOTIVI_PROTEZIONE` |
| 19 | riprezzo 10 s, 20 tentativi | invariato | `config.py:270-271` | - | - |
| 20 | rientro con 1 o 2 gol (M6.1) | si' | `config.py:307`, `mike.ts:540` | P3, H2 (sintetiche) | valore salvato nel DB da portare a 2 (migrazione non applicata) |
| 21 | consapevolezza banca/LAPSE (M6.2, M6.3) | si' | `service.py:204`, `2457`, `2599`, `2992` | P4_1 | ramo ABBINATO non testato (B-6); 4,5 sospeso sul banco ⊘ |
| 22 | cifre vive, esito chiusura (M7.1, M7.2) | si' (app) | `useMikeEventoAlMs.ts`, `mikeEsitoChiusura.ts` | vitest | M7.2 sulla credenza del bot (M5) |
| 23 | D1-D12 | quasi | M8.1 `engine.py:~2632`; M8.3 `service.py:968`; M8.4-5 `service.py:1356`; M8.6 `:4391`/`5430`; M8.7 `db.py:527`, `service.py:6130`; M8.8 `:4208`; M8.9 `db.py:395`; M8.12 `:1581` | P4 | **M8.11 non fatta** (A7); M8.10 in attesa (P6_4); D5 aperto; M8.2 invariato (live solo test, A2) |
| 24 | implementare fino ai replay veloci | parziale | - | - | tempi fuori standard con `--worker 1` (A5); C1 aperto |
| 25 | copertura solo con tutto al miglior prezzo | si' | `engine.py:~3929` | B-3 | - |
| 26 | un ordine solo, resto < 0,50 coperto (M3.5) | si' (FOK) | `_copertura_banca`, `_riprezzo_copertura_banca:4043` | B5/B6 del delegato | "lo scrive nel registro" no (M4) |

---

## COSA NON HO POTUTO VERIFICARE
- Nessun replay lanciato (vincolo): i numeri dei referti sono letti, non riprodotti; C1 e la strada
  "3,5 CLOSED -> regolamento" li ho verificati sul codice, non eseguiti.
- Se lo scanner di produzione scriva davvero `CLOSED` nel blocco 3,5 (la strada peggiore di C1):
  non ho letto il DB ne' dati di produzione.
- Se "annullo NON confermato" (M1) accada anche col runner vero o solo col `WsBanco` del banco.
- Se Betfair accetti via API una banca di chiusura sotto 0,50 EUR (M6).
- Il comportamento di `listCurrentOrders`/`listClearedOrders` per un ordine parzialmente abbinato e
  poi scaduto (letto dalla documentazione a memoria, non su ordini veri).
- Il frontend oltre `lib/mike.ts` e i componenti di Mike (Control Room, `mikeEsitoChiusura.ts`) solo
  letto nei referti P6, non eseguito (niente vitest/tsc lanciati da me).
- Il valore salvato nel DB di `reentry_max_goals` e di `cover_form`.
- Le patch in `in_attesa_del_via/` (P5_5, P6_4, P6_6): non esaminate riga per riga.
