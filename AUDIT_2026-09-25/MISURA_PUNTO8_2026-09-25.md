# MISURA PUNTO 8 - 25/09/2026 (delegato Opus, sessione B)

Mandato: **solo misura, nessuna modifica ai bot.** Nessun file sotto `Betfair/omega`,
`Betfair/mike`, `Betfair/safe_strategy`, `Betfair/stream/tennis_live`,
`Betfair/stream/tennis_scalper` o `Betfair/stream/scalper` e' stato toccato:
`git status --porcelain` mostra solo due cartelle nuove non tracciate,
`Betfair/stream/backtest/tools/` e `AUDIT_2026-09-25/misura_punto8_dati/`.
Base: `origin/master` `442d21c`. Nessun accesso al DB e nessun replay lanciato da me.
Le estrazioni in sola lettura (`estrai_db.py`) le ha lanciate il coordinatore il 25/09;
io ho letto soltanto i file `.json.gz` risultanti. **Referto chiuso il 25/09**: resta
aperta solo la parte B di M1, in attesa del replay `certifica mike`.
Ogni processo Python e' partito con `SUPABASE_URL=http://127.0.0.1:9`, e gli script lo
reimpostano da soli (`comune.blinda_db`).

Metodo comune a tutte le voci (`tools/misura_punto8/comune.py`):
- le funzioni di produzione sono **importate**, mai ricopiate;
- l'IC al 95 % viene da un **bootstrap percentile a grappolo** (2.000 giri, seme fisso)
  sull'unita' indipendente: la partita e, come seconda lettura, la lega;
- la differenza e' **appaiata**: variante meno attuale. Un valore negativo vuol dire
  perdita (log-loss o Brier) piu' bassa, quindi variante migliore;
- verdetto **MIGLIORA** solo se tutto l'IC sta sotto lo 0. **NON MISURABILE** se ci sono
  meno di 10 partite indipendenti, qualunque IC esca;
- le registrazioni sintetiche `_synth_*` sono sempre escluse.

---

## Tabella riassuntiva

| Voce | Verdetto con i dati di oggi | Numero chiave |
|---|---|---|
| O1 catena lambda (pre_ko prima della fixture) | **MIGLIORA**: anche sull'estensione dal 17/09, fuori campione per tutto (77 partite, 31 leghe), e sul fuori campione unito (734 partite) | estensione: log-loss CS FT -0,119 [-0,246; -0,027]; fuori campione unito FT -0,0238 [-0,0450; -0,0038], HT -0,0186 [-0,0338; -0,0050]; tutte (2.072) FT -0,0267 [-0,0392; -0,0144] |
| O5 rossi nel V3 (moltiplicatori globali) | **MIGLIORA** (campione piccolo: 90 partite con rosso, 77 dal 30/06) | dal 30/06, al primo rosso: log-loss CS FT -0,113 [-0,187; -0,046] |
| O6 calibrazione della coda | **NON MIGLIORA** (non c'e' niente da correggere): P_modello e P_fusa calibrate entro l'IC in tutte le fasce e in tutti i periodi | P_fusa con quote CS, fascia 1-2 %: 0,95 [0,44; 1,55]; fascia <=1 %: IC [0; 1,53] (2 esiti) |
| M1 Mike (`p_under35_cal` come veto) | La P calibrata **MIGLIORA** sulla grezza fuori campione. Il veto sul replay (parte B) e' **in attesa del replay `certifica mike`, che lancia il coordinatore** | Brier dal 21/09: -0,0093 [-0,0155; -0,0034] su 243 partite; soglia a quota 2,00 = 0,514 |
| M2 Mike (`p_over45_cal`) | **NON REALIZZABILE**: `over_4_5` non esiste nel DB | 0 righe su 20.883 |
| S2 calibrazione delle P d'uscita di Safe | **NON MIGLIORA**: la stima puntuale e' anzi peggiore | Brier +0,0018 [-0,0023; +0,0057] (origine mobile, 14 partite) |
| T1 superficie tennis_pro | **NON MISURABILE con i dati di oggi**: i 83 eventi del 07/07 non sono in `tennis_markets` (741 righe, dal 09/07) | 0 eventi su 83 con superficie nota |
| X1 bias dello scalper | **NON MIGLIORA**: la calibrazione con la pagella peggiora il Brier (anche in campione); 0 bias cambiati su 2 | Brier ML +0,0024 [+0,0008; +0,0041] su 16.172 partite |
| 8 giro Omega 20 s contro 5 s | Procedura A/B pronta (sezione 8) | - |

---

## 1. O1 - Omega, ordine della catena delle lambda

**Cosa fa ora.** `omega_service._prematch_lambdas` (`omega_service.py:1030`) prova
prima la fixture. La lettura e' `stream.db.get_fixture_prematch_lambdas` (`:1067`): prima
`tactical_engine_json`, poi `db_json_analisi.inputs`. Le quote `pre_ko` vengono solo dopo
(`:1085`).

**Cosa farebbe.** Le quote `pre_ko` devigate (`omega_model.lambdas_from_pre_ko`) passano
davanti. La fixture si usa solo se mancano. Il resto della catena resta identico.

**Come l'ho misurato.** Il braccio attuale e' la **funzione vera**, chiamata con un DB
finto che ha le chiavi del vero: `get_event` restituisce `fixture_id`/`league_id`, e
`fixture_predictions` restituisce i JSONB `tactical_engine_json` e
`db_json_analisi.inputs`. Il `pre_ko` usa i prezzi BACK, come li congela lo scanner.

Metrica principale: log-loss e Brier del risultato esatto finale (FT) e del primo tempo
(HT). La griglia e' quella del **V3 di produzione** (`omega_v3.griglia_finale`, parametri
di `omega_proposte.parametri_modello()`), calcolata al minuto 0. Per il confronto con M2
ho rifatto la stessa misura anche con la griglia v2 (`residual_grid`, cv 0,30).

Campione:
- M2 (`m2_campione_2026-09-17.json.gz`): 1.995 partite con esito, quote Betfair dal 24/06
  all'11/09;
- **estensione** (`estr_o1o6.json.gz`, estrazione del 25/09): run del 17/09 e del 23/09,
  **77 partite** giocate, di cui 29 a catena diversa, su 31 leghe.

In totale 2.072 partite; in 967 le due catene danno lambda diverse, nelle altre non c'e'
la fixture e le due braccia coincidono. La tabella qui sotto riporta i numeri del primo
lancio (sole partite M2) piu' la riga dell'estensione. I totali con l'estensione sono
subito dopo la tabella.

| Insieme | n (catena diversa) | Metrica | Attuale | Variante | Diff. [IC 95 %, grappolo partita] | IC grappolo lega | Verdetto |
|---|---|---|---:|---:|---|---|---|
| **TUTTE** | 1.995 (938) | log-loss CS FT | 3,02936 | 3,00627 | **-0,02309 [-0,03592; -0,01030]** | [-0,04493; -0,01008] (156 leghe) | **MIGLIORA** |
| | | Brier CS FT | 0,93273 | 0,93050 | -0,00223 [-0,00348; -0,00092] | [-0,00430; -0,00091] | **MIGLIORA** |
| | | log-loss CS HT | 2,10221 | 2,08853 | **-0,01368 [-0,02346; -0,00441]** | [-0,03119; -0,00319] | **MIGLIORA** |
| | | Brier CS HT | 0,83084 | 0,82840 | -0,00244 [-0,00468; -0,00020] | [-0,00610; -0,00007] | **MIGLIORA** |
| | | log-loss FT (griglia v2) | 2,99274 | 2,96862 | -0,02413 [-0,03699; -0,01121] | | MIGLIORA |
| M2 prova (25/07-11/09) | 657 (226) | log-loss CS FT | 2,95408 | 2,94146 | -0,01261 [-0,03033; +0,00425] | [-0,02835; +0,00188] | NON MIGLIORA |
| | | log-loss CS HT | 2,02104 | 2,01110 | -0,00994 [-0,02244; +0,00235] | [-0,02607; +0,00335] | NON MIGLIORA |
| | | Brier FT / HT | | | -0,00108 [-0,00312; +0,00087] / -0,00143 [-0,00496; +0,00198] | | NON MIGLIORA |
| M2 stima (<25/07) | 1.338 (712) | log-loss CS FT / HT | 3,06632 / 2,14252 | 3,03809 / 2,12698 | -0,02823 [-0,04470; -0,01205] / -0,01554 [-0,02872; -0,00325] | | MIGLIORA |
| Solo partite con catena diversa | 938 | log-loss CS FT / HT | 2,98841 / 2,10005 | 2,93930 / 2,07114 | -0,04911 [-0,07686; -0,02213] / -0,02891 [-0,04991; -0,00962] | | MIGLIORA |
| **Estensione 17/09 -> 23/09** (fuori campione anche per il V3) | 77 (29) | log-loss CS FT | 3,34764 | 3,22820 | **-0,11944 [-0,24615; -0,02749]** | [-0,25867; -0,02683] (31 leghe) | **MIGLIORA** |
| | | Brier CS FT | 0,95387 | 0,94766 | -0,00621 [-0,01108; -0,00221] | [-0,01172; -0,00199] | **MIGLIORA** |
| | | log-loss CS HT | 2,46099 | 2,36909 | -0,09189 [-0,18687; -0,02456] | [-0,19694; -0,02376] | **MIGLIORA** |
| | | Brier CS HT | 0,87659 | 0,86609 | -0,01050 [-0,01911; -0,00242] | [-0,01925; -0,00358] | **MIGLIORA** |

Totali con l'estensione (`o1_con_estensione.json`):

| Insieme | n (catena diversa) | log-loss FT [IC] | Brier FT [IC] | log-loss HT [IC] | Brier HT [IC] |
|---|---|---|---|---|---|
| **Fuori campione unito** (prova di M2 + estensione) | 734 (255) | **-0,02382 [-0,04495; -0,00375] MIGLIORA** | -0,00162 [-0,00342; +0,00022] NON MIGLIORA | **-0,01857 [-0,03381; -0,00503] MIGLIORA** | -0,00238 [-0,00582; +0,00074] NON MIGLIORA |
| TUTTE | 2.072 (967) | -0,02667 [-0,03916; -0,01435] MIGLIORA | -0,00238 [-0,00360; -0,00114] MIGLIORA | -0,01662 [-0,02630; -0,00742] MIGLIORA | -0,00275 [-0,00488; -0,00055] MIGLIORA |
| Solo catena diversa | 967 | -0,05714 [-0,08562; -0,03016] MIGLIORA | -0,00509 [-0,00775; -0,00252] MIGLIORA | -0,03539 [-0,05608; -0,01471] MIGLIORA | -0,00585 [-0,01034; -0,00114] MIGLIORA |

Sul fuori campione unito l'IC sulla lega (140 leghe) da' lo stesso verdetto dell'IC sulla
partita.

**Una cautela sull'estensione.** L'effetto e' grande (-0,119) perche' 29 partite su 77
cambiano catena, e l'IC e' largo. Il numero su cui contare e' quello del fuori campione
unito (734 partite): **-0,024 sulla FT, -0,019 sulla HT**, entrambi con IC che esclude lo 0.
Il Brier va nella stessa direzione ma tocca lo 0.

**Split fuori campione, cosa vale per questa voce.**
- La variante **non stima nessun parametro**: e' un riordino. Per lei non esiste una
  partita «in campione», e quindi l'insieme TUTTE (1.995 partite) e' un confronto legittimo.
- L'unico parametro comune alle due braccia e' il V3 del 16/09. E' stimato su transizioni
  aggregate di circa 1,4 milioni di partite fino all'11/09, quindi copre tutto il periodo
  allo stesso modo.
- Lo split di M2 (stima prima del 25/07, prova dopo) conta per i pesi di M2, non per questa
  variante. L'ho riportato come richiesto: sulle 657 partite di prova il segno e' lo stesso
  in tutte le metriche, ma l'IC tocca lo 0.
- L'estensione dal 17/09 e' fuori campione anche per il V3, ed e' **MIGLIORA** (vedi sopra).

**Per lega** (16 leghe con almeno 20 partite a catena diversa):
- 12 leghe hanno la stima puntuale a favore della variante e 4 contro;
- 1 sola lega e' significativa da sola (lega 165: -0,21 [-0,42; -0,03]);
- nessuna lega e' significativa contro la variante.

**Confronto con M2.** M2 aveva misurato «finale meno catena» sulla HT: -0,01364
[-0,02748; -0,00077]. Quel numero usava il mercato a meta' spread, cv 0,20 e la griglia v2.
Qui misuro esattamente la variante di produzione (prezzi back, V3), e sulle stesse 657
partite l'IC HT arriva a +0,00235. La direzione e' la stessa; la certezza sulla sola prova
di M2, no.

**Quota di partite senza `pre_ko`.**
- Delle 53 registrazioni `_live_raw/`, 13 non hanno il raw e 18 delle 40 con raw non hanno
  un Match Odds pre-KO. **Tutte e 18 sono registrazioni partite a gioco gia' iniziato**:
  la prima definizione del MATCH_ODDS e' gia' `inPlay`. Si tratta del registratore, non del
  mercato.
- Distribuzione di `omega_events.model->>lambda_source` (`o1_lambda_source.json`).
  L'estrazione con `open_date` dal 01/09 ha trovato **34 eventi, tutti del 24/09**, perche'
  la tabella tiene solo il catalogo recente:

  | Fonte | Eventi | Quota |
  |---|---:|---:|
  | nessun modello salvato | 29 | 85 % |
  | `pre_ko_odds` | 5 | 15 % |

  «Nessun modello salvato» vuol dire due cose indistinguibili: lambda arrivata dalla
  fixture (che non si persiste: `persist` resta falso, `omega_service.py:1083`) oppure evento mai valutato
  dal bot.
- **La quota di partite senza pre_ko in produzione resta non misurabile**: 34 eventi di un
  solo giorno, con una colonna che non distingue fixture e «mai visto».

**Rischio.** Basso sulle letture DB, che anzi diminuiscono: la fixture si legge solo senza
quote. Medio sul comportamento: cambiano le lambda del 47 % delle partite del campione
(938 su 1.995), quindi le P delle celle e gli ingressi del cancello.

**Per portarlo in produzione.**
- Codice da toccare: `Betfair/omega/omega_service.py:1061-1088`, dove il blocco `pre_ko`
  (`:1084-1088`) va prima del blocco fixture (`:1064-1073`).
- Il ripiego `saved` (`:1074-1082`) va deciso a parte: in questa misura resta dopo il
  `pre_ko`.
- Replay da rifare: `certifica omega 35760084 35797769 35777617` con gli scenari v3
  (`cap-stretto,feed-stantio,riavvio,proposta-approvata,uscite-automatiche,rifiuti-betfair`),
  prima e dopo, confrontando il `lambda_source` delle gambe.
- Decisione utente n. 12, gia' aperta.

---

## 2. O5 - Omega V3 e i cartellini rossi

**Cosa fa ora.** `omega_v3.griglia_finale` ignora i rossi.

**Cosa farebbe.** Le intensita' residue vengono moltiplicate per i coefficienti globali
di `inplay_intensity_by_league.json`: 0,7461 per chi e' espulso, 1,3832 per l'avversario.
Li legge la funzione di produzione `live_engine.red_card_multipliers(rh, ra, None)`.

`o5_rossi.griglia_con_rossi` innesta il moltiplicatore nel ramo gamma-Poisson (beta ->
beta/m). **Con m = (1, 1) riproduce `griglia_finale` al 1e-12**; il test e' parametrizzato
su 4 stati di gioco.

| Fonte | Partite con rosso | Usabili (con lambda) | Diff. log-loss CS FT al primo rosso | Verdetto |
|---|---:|---:|---|---|
| `_live_raw/` (52 registrazioni reali) | 2 | 1 (35794996, rosso al 75', finale 0-2) | n = 1 | **NON MISURABILE** |
| DB (`estr_o5`: 5.695 eventi di `match_events`, gol e cartellini, sulle partite di M2 + `estr_o1o6`) | 113 | 111 (2 scartate: gol incoerenti col finale); 90 con il primo rosso prima del 90' | vedi sotto | **MIGLIORA** |

Lambda usate: la **catena attuale** (`o1.lambda_attuale`). Metrica: log-loss e Brier del
risultato esatto finale. Differenza variante meno attuale, bootstrap 2.000 giri sulla
partita.

| Insieme | Punto di valutazione | Punti | Partite | log-loss att. -> var. | Diff. log-loss [IC 95 %] | Diff. Brier [IC 95 %] | Verdetto |
|---|---|---:|---:|---|---|---|---|
| **dal 30/06, fuori dal fit dei coefficienti** | al primo rosso | 77 | 77 | 1,9531 -> 1,8405 | **-0,1126 [-0,1872; -0,0462]** | -0,0213 [-0,0357; -0,0071] | **MIGLIORA** |
| dal 30/06 | ogni 10' fino all'85' | 272 | 77 | 1,9863 -> 1,8817 | -0,1045 [-0,1833; -0,0313] | -0,0194 [-0,0352; -0,0039] | **MIGLIORA** |
| tutte | al primo rosso | 90 | 90 | 1,9011 -> 1,8126 | -0,0884 [-0,1537; -0,0252] | -0,0164 [-0,0294; -0,0036] | **MIGLIORA** |
| tutte | ogni 10' | 311 | 90 | 1,9448 -> 1,8560 | -0,0888 [-0,1599; -0,0219] | -0,0174 [-0,0322; -0,0018] | **MIGLIORA** |

**Verdetto O5: MIGLIORA**, anche sulle sole partite fuori dal fit dei coefficienti (dal
30/06, 77 partite). Limiti dichiarati:
- **campione piccolo**, quindi IC largo, circa +/-0,07 sulla log-loss;
- misura **al minuto del rosso con il punteggio vero**, non al cancello di Omega: nessun
  prezzo, nessuna selezione di celle;
- l'effetto sulle **decisioni** (quante gambe cambierebbero) non e' misurato: serve il
  banco su registrazioni con rosso, e oggi ce n'e' una sola (35794996).

**Rischio.** Medio: sui rossi le lambda cambiano del 25-38 %.

**Per portarlo in produzione.**
- Codice da toccare: `omega_v3.py:266-302` (`intensita_residue`) e `:305-` (ramo
  gamma_poisson di `griglia_residua`), piu' il passaggio dei rossi dal feed
  (`omega_service.py:978-979`).
- Replay: `certifica omega` su una registrazione con rosso. **Oggi c'e' solo 35794996**,
  che non e' nell'elenco Omega.

---

## 3. O6 - Calibrazione della coda

**Cosa fa ora.**
- `model_calibration='off'` (`omega_config.py:73`);
- P_nostra = max(P fusa, Wilson empirico) (`omega_v3.py:668`).

**Misura.** Rapporto usciti/attesi per fascia di P, sulle 19 selezioni del Correct Score
FT standard (0-0 ... 3-3 piu' i tre aggregati). P_modello = `probabilita_selezioni` del V3
di produzione al minuto 0, con le lambda della **catena attuale**. Esiti da `matches`. IC a
grappolo sulla partita.

| Insieme | Fascia | Selezioni | Partite | Usciti | Attesi | Usciti/attesi [IC 95 %] | Verdetto |
|---|---|---:|---:|---:|---:|---|---|
| M2 tutte (24/06-11/09) | <=1 % | 4.700 | 1.963 | 22 | 21,75 | **1,01 [0,61; 1,44]** | calibrata entro l'IC |
| | 1-2 % | 4.447 | 1.862 | 59 | 66,98 | **0,88 [0,66; 1,11]** | calibrata entro l'IC |
| | 2-5 % | 12.233 | 1.994 | 425 | 420,46 | **1,01 [0,93; 1,10]** | calibrata entro l'IC |
| run 09-11/09 | <=1 % | 559 | 239 | 3 | 2,65 | 1,13 [0,00; 2,53] | IC troppo largo |
| | 1-2 % | 513 | 225 | 8 | 7,78 | 1,03 [0,38; 1,79] | IC troppo largo |
| | 2-5 % | 1.513 | 241 | 58 | 52,25 | 1,11 [0,87; 1,36] | calibrata entro l'IC |
| **Estrazione del 25/09** (run 09, 10, 11, 17 e 23/09, con le quote CS): **P_modello** | <=1 % | 800 | 314 | 5 | 3,79 | 1,32 [0,28; 2,62] | IC troppo largo |
| | 1-2 % | 689 | 301 | 10 | 10,49 | 0,95 [0,40; 1,60] | calibrata entro l'IC |
| | 2-5 % | 1.992 | 318 | 81 | 68,70 | 1,18 [0,96; 1,40] | calibrata entro l'IC |
| Stesse partite, **P_fusa** = `fondi_col_mercato`(P_modello, `p_mercato_devigata`(CS)) | <=1 % | 716 | 305 | 2 | 3,33 | 0,60 [0,00; 1,53] | IC troppo largo |
| | 1-2 % | 754 | 304 | 11 | 11,52 | **0,95 [0,44; 1,55]** | calibrata entro l'IC |
| | 2-5 % | 1.949 | 313 | 79 | 67,27 | 1,17 [0,96; 1,41] | calibrata entro l'IC |

Sulle quote CS, nella fascia 2-5 % entrambe le P hanno la stima puntuale sopra 1 (1,17-1,18:
la coda esce un po' piu' dell'atteso), ma l'IC tocca 1. **Da tenere d'occhio**: e' la
direzione pericolosa, anche se oggi non e' dimostrata. E' comunque la fascia in cui Omega
non opera (`p_max` 2 %).

**Verdetto: NON MIGLIORA** (non c'e' niente da correggere che l'IC permetta di vedere).
- Il V3 **non** mostra la sovrastima di 0,76-0,79 che M2 aveva trovato. Quella misura era
  sulle 81 celle della griglia v2 con cv; questa e' sulle selezioni vere del mercato con
  il V3.
- Nella fascia <=1 % l'IC [0,61; 1,44] **non esclude un errore del 40 % in nessuna delle
  due direzioni**: con 22 esiti non si puo' stringere.

**Copertura.** 1.995 partite del 3 % catturato da `betfair_market_odds` (M2 §1). Le quote
sono pre-match: la coda **in gioco** (gamba A 1'-44', gamba B 46'-85') non e' misurata qui.

**Rischio di una correzione.** Alto: tocca il cuore del cancello, e oggi i dati non la
giustificano.

**Per portarlo in produzione.** Niente: anche la P_fusa sulle quote CS e' calibrata entro
l'IC. Punto d'innesto, se un giorno servisse: `omega_model.load_calibrator` oppure un
fattore prima di `omega_v3.py:668`.

---

## 4. M1/M2 - Mike, P calibrate dell'Over 3.5 e 4.5

**Cosa fa ora.**
- `dossier.build_prematch` calcola `p_under35_cal` (`dossier.py:82`, chiave
  `markets_calibrated.over_3_5["True"]`) e nessuno la legge;
- `p_over45_cal` non viene mai valorizzata (`:64`).

**Script pronti.** `m1_mike.py`, testato su finti con le chiavi vere (`o35` e `r35` sono
gli alias di `markets_calibrated.over_3_5` e `markets.over_3_5`).

`affidabilita` misura:
- decili, con Wilson 95 % per decile;
- Brier e log-loss della calibrata contro la grezza, con IC;
- due periodi separati: prima del 21/09 e dal 21/09 in poi. Dal 21/09 e' fuori campione,
  perche' il 21/09 e' la data dell'ultima `poisson_calibration`.

La P dell'Under la calcola la funzione vera di Mike (`build_prematch` su un DB finto).

**La soglia non e' a occhio.**
- La curva isotonica (il `_pav` di produzione) mette in relazione la P dell'Under
  dichiarata con quella osservata.
- La soglia s(q) e' la P dichiarata a cui l'Under osservato vale il pareggio del back a
  quota q, cioe' 1/(1+(q-1)(1-c)).
- Si calcola per q = 1,30 / 1,50 / 2,00 / 2,50 / 3,00, cioe' la banda d'ingresso di Mike.

`conta` legge lo stdout di `certifica mike ... --json` (campo `stati`). Conta le partite
entrate in `HOLD` o in `PRE_LAST_ENTRY_PENDING` (l'ultimo ingresso PERSIST) e quelle con
`p_under35_cal < s(q)`.

**Dati.** `estr_m1.json.gz`, estratto dal coordinatore il 25/09 (secondo lancio):
- `fixture_predictions` con `fixture_date` dal 01/08 al 25/09: 20.883 righe;
- esiti da `matches`: 20.035;
- 5 righe intere di `markets_calibrated` per verificare il formato (Q6).

**Q6, formato delle chiavi.** Le chiavi di `markets_calibrated` sono `1x2`, `btts`,
`ht_1x2`, `over_1_5`, `over_2_5`, `over_3_5` e `first_half_over_0_5`.
- I nodi Over hanno le chiavi `{"True": p, "False": 1-p}`: e' la chiave che legge
  `dossier.py:82`, quindi la lettura di Mike e' corretta.
- **`over_4_5` non esiste**, ne' in `markets_calibrated` ne' in `markets`: 0 righe su 20.883.

**M2 (`p_over45_cal`): NON REALIZZABILE con i dati di oggi.** Il DB non ha la P
dell'Over 4.5. Per averla, il motore Poisson che scrive `db_json_analisi` dovrebbe
produrre e calibrare il mercato `over_4_5`: e' un lavoro sulla pipeline dei pronostici,
non su Mike.

**M1, affidabilita' di `markets_calibrated.over_3_5`.** 8.589 partite giocate con la P
calibrata. La P dell'Under la calcola la funzione vera di Mike (`build_prematch`).
Confronto con la P grezza (`markets.over_3_5`): differenza appaiata calibrata meno grezza,
bootstrap 2.000 giri sulla partita.

| Insieme | n | Freq. Over 3.5 | Brier grezza -> calibrata | Diff. Brier [IC 95 %] | Diff. log-loss [IC 95 %] | Verdetto |
|---|---:|---:|---|---|---|---|
| **dal 21/09 (FUORI CAMPIONE)** | 243 | 0,391 | 0,24741 -> 0,23808 | **-0,00933 [-0,01545; -0,00342]** | **-0,0322 [-0,0506; -0,0151]** | **MIGLIORA** |
| prima del 21/09 | 8.346 | 0,357 | 0,22147 -> 0,21916 | -0,00231 [-0,00322; -0,00141] | -0,0071 [-0,0095; -0,0046] | MIGLIORA (probabilmente in campione) |
| tutte | 8.589 | 0,358 | 0,22220 -> 0,21969 | -0,00251 [-0,00348; -0,00162] | -0,0078 [-0,0105; -0,0054] | MIGLIORA |

Affidabilita' per decile della P calibrata dell'Over (tutte le 8.589 partite):

| Decile | n | P media | Frequenza osservata [Wilson] |
|---|---:|---:|---|
| 0,1-0,2 | 811 | 0,163 | **0,191 [0,166; 0,220]** |
| 0,2-0,3 | 2.054 | 0,254 | **0,282 [0,263; 0,302]** |
| 0,3-0,4 | 2.944 | 0,349 | 0,344 [0,327; 0,361] |
| 0,4-0,5 | 1.861 | 0,442 | 0,450 [0,428; 0,473] |
| 0,5-0,6 | 625 | 0,540 | 0,533 [0,494; 0,572] |
| 0,6-0,7 | 213 | 0,633 | 0,601 [0,534; 0,664] |
| 0,7-0,8 | 31 | 0,722 | 0,645 [0,470; 0,789] |

Dove la P dell'Over e' bassa (0,1-0,3) l'Over esce **piu'** del dichiarato: la P
dell'Under e' **troppo alta** di circa 3 punti. Negli altri decili la P e' calibrata
entro l'IC. Fuori campione (243 partite) i decili sono larghi, ma la direzione e' la
stessa: nel decile 0,1-0,2, P 0,166 contro 0,333 osservato [0,210; 0,485], su 42 partite.

Il punto conta per Mike, che banca l'Under: la P calibrata e' **ottimista proprio sulle
partite in cui Mike e' piu' tranquillo**.

**Soglia per il veto M1, dalla curva** (isotonica della frequenza osservata dell'Under
contro la P dichiarata dell'Under, PAV di produzione, 8.589 partite). Il valore e' la
P dichiarata dell'Under sotto la quale il back dell'Under alla quota q non raggiunge il
pareggio, al netto della commissione del 5 %.

| Quota del back Under | Pareggio 1/(1+(q-1)*0,95) | Soglia su `p_under35_cal` |
|---:|---:|---:|
| 1,30 | 0,778 | **0,807** |
| 1,50 | 0,678 | 0,684 |
| 2,00 | 0,513 | 0,514 |
| 2,50 | 0,413 | 0,385 |
| 3,00 | 0,345 | 0,275 |

Leggere la soglia: a quota 1,30 serve `p_under35_cal` >= 0,807, non 0,778, perche' a P
alte l'Under esce meno del dichiarato.

Limite: la curva e' stimata su tutte le 8.589 partite, il 97 % prima del 21/09; la sua
prova fuori campione e' il blocco del 21/09 qui sopra. Per la quota 3,00 i nodi della
curva sono rari (31 partite fra 0,2 e 0,3): la soglia 0,275 e' incerta.

**Parte B, conteggio sul replay: IN ATTESA del replay `certifica mike`, che lancia il
coordinatore.** Poi servono `estrai_db mike_ev --eventi-file certifica_mike.txt` e
`m1_mike conta`, entrambi pronti e testati.

**Verdetto M1: MIGLIORA come informazione.** La P calibrata e' migliore della grezza fuori
campione (IC che esclude lo 0), quindi il dato che Mike oggi butta vale piu' di quello
grezzo. Il VETO in se' (quante posizioni HOLD/PERSIST toglierebbe e con che P&L) **non e'
misurato**: serve la parte B e poi il banco.

**Copertura.** La P calibrata c'e' su 8.589 partite giocate su circa 20.000 della finestra
(43 %).

**Per portarlo in produzione.** Vedi la sezione «Cosa serve per la produzione».

---

## 5. S2 - Safe, calibrazione delle P d'uscita

**Cosa fa ora.** `bot_service._p_calcio` (`bot_service.py:3986-4016`) decide l'uscita con
`OpportunityModel(params).book(...)`, cioe' con la P **grezza**.

**Cosa farebbe.** La stessa P passerebbe per l'isotonica di `calibration.fit_calibration`
(shrinkage piu' PAV).

**Misura.**
- Campioni: `validate_opportunity.calibration_samples` (produzione), uno per minuto per
  ogni runner di ogni mercato regolato. Esito dal WINNER dello stream.
- Lambda: `pre_ko`, oppure i default del bot se manca.
- Due validazioni temporali:
  - (a) **taglio unico**: le prime 60 % registrazioni per data servono a stimare, le
    ultime alla prova, mai la stessa giornata nei due insiemi;
  - (b) **origine mobile**: per ogni giorno si stima su tutti i giorni precedenti e si
    prova su quel giorno.

**Dati.** Tutte le registrazioni disponibili, ma sono le stesse di prima:
- **32 registrazioni con campioni** (19 con `pre_ko`, 13 con lambda di default), dal 26/06
  al 01/09;
- l'unica registrazione nuova con stream mercati (36106722) non ha mercati regolati e da'
  0 campioni. Le altre registrazioni dopo il 10/09 hanno solo punteggi;
- in pratica «tutte le `_live_raw/`» sono le stesse 32 partite di `opp_calibration.json`.

| Validazione | Registrazioni | Partite di prova | Campioni | Brier grezza -> calibrata | Diff. Brier [IC] | Diff. log-loss [IC] | Verdetto |
|---|---|---:|---:|---|---|---|---|
| origine mobile | tutte (32) | 14 | 11.451 | 0,07321 -> 0,07498 | **+0,00177 [-0,00230; +0,00569]** | +0,0046 [-0,0057; +0,0138] | **NON MIGLIORA** |
| origine mobile | solo pre_ko (19) | 11 | 16.702 | 0,07709 -> 0,07836 | +0,00127 [-0,00283; +0,00670] | +0,0077 [-0,0119; +0,0297] | **NON MIGLIORA** |
| taglio unico (dal 16/07) | tutte | 9 | 3.901 | 0,07027 -> 0,07490 | +0,00463 [-0,00466; +0,00819] | +0,0098 [-0,0221; +0,0214] | NON MISURABILE (9 partite) |
| taglio unico (dal 10/07) | solo pre_ko | 5 | 3.618 | 0,07401 -> 0,07196 | -0,00205 | -0,0013 | NON MISURABILE (5 partite) |
| tabella IN PRODUZIONE (10/09), stesse 9 partite | tutte | 9 | 3.901 | 0,07027 -> 0,07247 | +0,00220 [-0,00941; +0,00627] | +0,0037 | NON MISURABILE; in piu' e' **in campione** |

**Per famiglia** (origine mobile, tutte le registrazioni).
- Solo `ou_line` ha 14 partite: Brier +0,00135 [-0,00680; +0,00769], **NON MIGLIORA**.
- Le altre famiglie hanno 7 partite o meno e sono NON MISURABILI. Due direzioni da tenere
  a mente:
  - `cs_cell` peggiora: Brier +0,00323 [+0,00007; +0,00987];
  - `cs_any_other` migliora: log-loss -0,0061 [-0,0078; -0,0045].

Le fasce di minuto per famiglia sono nel JSON (`s2_*.json`, chiavi `famiglia|fascia`).

**Verdetto: NON MIGLIORA.** Fuori campione la calibrazione peggiora di poco la stima
puntuale, e l'IC contiene lo 0. **Collegarla all'uscita non e' giustificato con i dati di
oggi.**

**Cosa serve.** Registrazioni nuove con lo stream mercati `<id>.jsonl` e i mercati
regolati. Dal 10/09 il registratore ne ha prodotta una sola, senza esiti.

**Rischio.** Medio, come previsto dall'audit: su 32 partite l'isotonica impara rumore.

**Per portarlo in produzione (se un giorno migliorasse).** Codice da toccare:
`bot_service.py:4014-4017` (applicare `model.calibrate` alla `p`). Replay da rifare:
`certifica safe_base/safe_esatto/safe_punta`, confrontando le uscite a modello
(`exit_hold`).

---

## 6. T1 - tennis_pro e la superficie

**Cosa fa ora.**
- `surface` ha il default "grass" (`tennis_pro_bot.py:116`);
- `_lay_rev` e' falso (`:119`), quindi `serving_for_set`, `double_break` e
  `compressed_fav` sono spenti (`:171,174,184`);
- il break point banca il servitore (`:510`).

**Conteggio** (`t1_superficie.py`, nessuna strategia istanziata):

| Voce | Numero |
|---|---:|
| Cartelle in `~/Desktop/tennis_rec` | 128 (2 giorni-cartella, **tutte del 07/07/2026**) |
| Registrazioni con raw | 84 (83 eventi unici) |
| `countryCode` nella marketDefinition | GB 16, assente 67 |
| Superficie nota | **0**: lo stream non la porta, serve `tennis_markets.competition_name` |
| Eventi in cui la condizione di SERVING FOR THE SET si verifica | 64 (109 stati di punteggio distinti) |
| Eventi con DOUBLE BREAK (scarto >= 3 game) | 51 (154 stati) |
| Eventi con COMPRESSED FAV (ltp del favorito <= 1,20) | 42 (872 tick) |
| Setup che si accenderebbero su una partita non su erba | 3 su 6 (piu' l'inversione del lato del break point) |

**Verdetto: NON MISURABILE con i dati di oggi.** Estrazione del 25/09 (`estr_t1`):
**0 righe** per i nostri 83 eventi.
- Verifica del coordinatore sul DB: `tennis_markets` ha 741 righe, con `open_date` dal
  09/07 al 24/09 e `run_date` solo nei giorni 09-17/07 e a settembre.
- Gli eventi registrati il 07/07 **non ci sono**: provati 3 su 3, trovati 0.
- Nessun'altra estrazione, per decisione del coordinatore.

Quello che resta di questa voce:
- il 07/07 e' giorno di Wimbledon, quindi i 16 eventi GB sono quasi certamente su erba;
- i 67 eventi senza paese sono di superficie ignota;
- per misurare davvero servono registrazioni tennis di giorni coperti da `tennis_markets`
  (da luglio in poi). Oggi non esistono: tutte le 128 cartelle sono del 07/07.

Il classificatore per parole chiave (`superficie_da_nome`) resta pronto, ma non e' stato
esercitato su dati veri.

**Rischio.** Medio-alto: accende 3 setup mai certificati, su un campione di un solo giorno.

**Per portarlo in produzione.**
- Codice da toccare: il runner passa `surface` nel contesto `pro_params`
  (`tennis_live/tennis_runner.py:104`, istanza del bot) e lo ricava da `competition_name`
  (`tennis_bot_service.py:145`).
- Replay: `certifica tennis_pro` superficie per superficie, ma **servono registrazioni
  non-erba**, che oggi non esistono.

---

## 7. X1 - Scalper, bias su P calibrate

**Cosa fa ora.** `bias_resolver.resolve_bias` (`:137`) lavora con l'argmax 1X2 di ML e di
Poisson, P grezze, edge dello 0,02-0,20.

**Cosa farebbe (variante).** Le stesse regole, ma su P calibrate con la pagella:
p -> hit_rate reale della fascia (`direction_pagella` globale, 1X2).

**Dati.** `estr_x1.json.gz`, estratto dal coordinatore il 25/09 alle 14:12:
- pagella: 256 righe, `generated_at` 25/09;
- finestra: `fixture_predictions` 01/08-25/09, 20.883 righe; 20.035 esiti;
- ML presente su 16.172 partite giocate, Poisson su 8.589, entrambi su 6.888.

Misura: `x1_bias.py`, funzioni vere `extract_1x2`, `_argmax_1x2`, `resolve_bias`.

**A. La P calibrata con la pagella migliora la previsione 1X2? No, peggiora.**
Brier 3 classi e log-loss della P grezza contro la calibrata (normalizzata a somma 1),
partita per partita, differenza appaiata, bootstrap 2.000 giri sulla partita:

| Motore | n partite | Brier grezza -> calibrata | Diff. Brier [IC 95 %] | Verdetto | Diff. log-loss [IC 95 %] | Verdetto |
|---|---:|---|---|---|---|---|
| ML | 16.172 | 0,60696 -> 0,60941 | **+0,00244 [+0,00079; +0,00407]** | **PEGGIORA** | +0,00313 [-0,00010; +0,00620] | NON MIGLIORA |
| Poisson | 8.589 | 0,61172 -> 0,61404 | **+0,00232 [+0,00057; +0,00395]** | **PEGGIORA** | +0,00300 [-0,00008; +0,00590] | NON MIGLIORA |

Il confronto e' perfino **ottimista per la variante**: la pagella e' costruita sullo
storico settled al 25/09, quindi le partite della finestra gia' giocate sono **in
campione** per la calibrata. Peggiora lo stesso. Il motivo e' che la mappa a fasce di
larghezza 0,10 appiattisce la P dentro ogni fascia e perde risoluzione piu' di quanto
corregga la calibrazione, che per 1X2 era gia' buona.

**B. Pagella 1X2 (globale).**
- Su 47 celle motore x selezione x fascia, 43 hanno la frequenza osservata dentro la
  fascia dichiarata (Wilson 95 %).
- Le eccezioni sono tutte sul **pareggio**, alle P alte: ML D .40-.50 esce 0,256 [0,201;
  0,321] su 199; ML D .50-.60 0,205 su 44; Poisson D .50-.60 0,273 su 22. I motori
  sovrastimano il pareggio quando lo danno sopra il 40 %.
- Limite del criterio: confronta con la larghezza della fascia, non con la P media
  dichiarata, che la pagella non registra.

**C. Concordanza ML/Poisson** (6.888 partite giocate con tutte e due le mappe):

| | n | Hit dell'argmax | Wilson 95 % |
|---|---:|---:|---|
| motori concordi | 5.066 (73,5 %) | **0,537** | [0,523; 0,550] |
| discordi, argmax ML | 1.822 | 0,389 | - |
| discordi, argmax Poisson | 1.822 | 0,363 | - |

P media di consenso dichiarata contro osservata (che e' la P su cui il bias calcola
l'edge):

| Fascia | n | Dichiarata | Osservata [Wilson] |
|---|---:|---:|---|
| .30-.40 | 285 | 0,384 | 0,386 [0,331; 0,444] |
| .40-.50 | 2.164 | 0,452 | 0,454 [0,433; 0,475] |
| .50-.60 | 1.654 | 0,545 | 0,567 [0,543; 0,591] |
| .60-.70 | 731 | 0,643 | **0,681 [0,647; 0,714]** |
| >.70 | 232 | 0,751 | **0,815 [0,760; 0,859]** |

La P di consenso e' **sotto-fiduciosa sopra il 60 %** (l'IC di Wilson esclude la P
dichiarata). La regola del consenso e' quindi informativa, e l'edge del bias e'
**prudente** proprio dove i motori sono piu' sicuri. La pagella non corregge questo punto
perche' lavora motore per motore, non sul consenso.

**D. Le due registrazioni dello scalper** (`resolve_bias` vero, mid dell'ultimo book
pre-KO ricostruito dal raw):

| Evento | fixture | Mid casa / trasferta / pareggio | Grezza | Calibrata |
|---|---|---|---|---|
| 35797769 | 1581821 | 0,606 / 0,159 / 0,238 | consenso H; ML 0,523 e Poisson 0,435; edge -21,0 % -> **neutro** | ML 0,556 e Poisson 0,456; edge -16,5 % -> **neutro** |
| 35777617 | 1568100 | 0,542 / 0,196 / 0,261 | Poisson 1X2 assente -> **neutro** | idem -> **neutro** |

**Bias cambiati: 0 su 2.** Su 2 registrazioni il numero non ha valore statistico; lo
riporto solo per completezza.

**Verdetto X1: NON MIGLIORA.** Calibrare le P del bias con la pagella peggiora il Brier
di entrambi i motori con IC che esclude lo 0, pur essendo in campione. Il bias non
cambierebbe su nessuna delle due registrazioni.

Se si vuole intervenire sul bias, il dato che i numeri indicano e' un altro: la
sotto-fiducia del **consenso** sopra il 60 %. Va misurata fuori campione, con una
calibrazione del consenso stimata su una finestra precedente e provata sulla successiva,
e con i prezzi di mercato. **Non proposto come modifica.**

**Per portarlo in produzione.** Codice da toccare: `bias_resolver.py:79-90,193-204` e
`scalper_session.py:486-520`, con una lettura in piu' all'armo. Replay: `certifica
scalper_calcio 35797769 35777617`.

---

## 8. Giro di Omega: 20 s contro 5 s - procedura A/B per il coordinatore (NON lanciata)

**Parametro.** La cadenza del replay e' `poll_interval_s` (20 s), allargata a
`idle_cycle_s` (60 s) quando il giro non ha niente che si muova
(`omega/tools/replay_registrazioni.py:1397-1405`, fedele a `omega_service.main`).
L'opzione `--ogni-ms N` di `certifica` **sostituisce l'intera cadenza**, allargamento a
vuoto compreso. Per separare i due effetti servono quindi tre bracci.

| Braccio | Comando | Isola |
|---|---|---|
| A (produzione) | `python -m Betfair.stream.backtest.certifica omega 35760084 35797769 35777617 --scenari cap-stretto,feed-stantio,riavvio,proposta-approvata,uscite-automatiche,rifiuti-betfair --json > omega_A.txt` | - |
| C (20 s fissi) | stesso comando + `--ogni-ms 20000` -> `omega_C.txt` | A contro C = effetto del giro a vuoto da 60 s |
| B (5 s fissi) | stesso comando + `--ogni-ms 5000` -> `omega_B.txt` | C contro B = effetto 20 s -> 5 s |

Regole: un replay per volta, in sequenza, mai in parallelo (ordine del 24/09). Stessa
versione del codice (hash nel referto).

**Cosa confrontare, per evento e per scenario** (sono tutti campi gia' presenti nel JSON
di `--json`, voce `note`):
1. **Ingressi**: ordini piazzati, gamba A e gamba B, minuto e cella scelta; `decisioni` e
   `azioni`.
2. **P&L**: la riga «P&L del replay: lordo, commissione, NETTO». Non e' il metro: e' un
   indizio.
3. **Letture DB**: «letture del feed di Omega: N» e «chiamate al mercato».
   - Il budget IO del DB (incidente del 13/09) si stima come N_B/N_A per partita, per il
     numero di partite contemporanee.
4. **Violazioni** per codice e controlli sollecitati: devono restare 0 violazioni con
   copertura pari o maggiore.
5. **Latenza della decisione**: minuto del primo ingresso e differenza fra
   `DECISION_MAX_AGE_S` e l'eta' della riga al momento della decisione.

**Criterio.** B e' migliore di C solo se:
- ci sono ingressi in piu' (o piu' presto) a prezzo pari o migliore;
- le violazioni restano 0;
- le letture sono sostenibili.

Con 3 partite il P&L non ha potere statistico: il confronto e' di condotta.

---

## Cosa serve per la produzione (solo le voci che migliorano: O1, O5, M1)

Nessuna di queste modifiche e' fatta. Le strategie sono intoccabili di iniziativa: serve
l'ordine dell'utente, poi la modifica la fa un delegato del dominio bot, e il coordinatore
la certifica sul banco (`python -m Betfair.stream.backtest.certifica <bot> ...`, un replay
per volta).

### O1 - catena delle lambda di Omega (decisione utente n. 12, gia' aperta)

- **File e righe**: `Betfair/omega/omega_service.py`, funzione `_prematch_lambdas`
  (`:1030`):
  - il blocco `pre_ko` (`:1083-1088`, `M.lambdas_from_pre_ko(payload.get("pre_ko"))`) va
    PRIMA del blocco fixture (`:1064-1073`, `get_fixture_prematch_lambdas`);
  - la fixture resta come ripiego se `pre_ko` manca;
  - il ripiego `saved` (`:1074-1082`) va deciso a parte: la misura lo tiene dopo il
    `pre_ko`;
  - con `pre_ko` in testa, `persist=True` salverebbe su `omega_events.model` anche le
    lambda di mercato: e' gia' cosi' oggi per il ramo `pre_ko` (`:1088`).
- **Letture DB**: diminuiscono, perche' la fixture si legge solo senza quote.
- **Replay da rifare, prima e dopo**:
  - comando: `certifica omega 35760084 35797769 35777617 --scenari cap-stretto,feed-stantio,riavvio,proposta-approvata,uscite-automatiche,rifiuti-betfair`;
  - da confrontare: `lambda_source` delle gambe (in audit), celle scelte, `scartati` per
    motivo, violazioni e copertura dei controlli;
  - lo scenario `riavvio` e' essenziale: dopo un riavvio la cache di processo delle lambda
    si svuota.
- **Test del bot da aggiornare**: quelli che fissano l'ordine «fixture prima»
  (`grep -rn "_prematch_lambdas" Betfair/omega/test_*.py`).
- **Rischio**: cambiano le lambda di circa il 47 % delle partite (tutte quelle con una
  fixture), quindi anche le celle proposte dal cancello.

### O5 - rossi nel V3

- **File e righe**:
  - `Betfair/omega/omega_v3.py`: il ramo `gamma_poisson` di `griglia_residua` (`:305-340`)
    e `intensita_residue` (`:266-302`) prendono un moltiplicatore residuo per lato
    (beta -> beta/m, come `o5_rossi.griglia_con_rossi`, equivalente al 1e-12 a m = 1);
  - il valore arriva da `stream.engine.live_engine.red_card_multipliers(rh, ra, None)`,
    coefficienti GLOBALI, mai per lega;
  - i rossi arrivano dal feed (`omega_service.py:978-979`) passando per
    `probabilita_selezioni`, `seleziona_v3` e `proposta_uscita`
    (`omega_proposte.py:406-438`), cosi' ingresso e uscita usano la stessa P.
- **Replay**: `certifica omega` sugli scenari v3. Serve **almeno una registrazione con
  rosso** nell'elenco di Omega: oggi c'e' solo 35794996 (rosso al 75'), che va aggiunta
  alle registrazioni certificate.
- **Rischio**: medio. Il campione della misura e' piccolo (77 partite fuori dal fit) e la
  misura e' sul risultato esatto, non sul cancello.

### M1 - Mike, `p_under35_cal` come veto (solo dopo la parte B)

- **File e righe**:
  - `Betfair/mike/engine.py`: all'ULTIMO INGRESSO, in `PRE_OPEN`, prima delle due uscite
    in `HOLD` (`:2354-2369`, «ultimo ingresso: ... tengo») e prima del rientro in PERSIST
    (`under_last`, `:2514`);
  - regola: se `ctx.dossier.p_under35_cal < soglia(q)`, dove q e' il prezzo dell'Under in
    quel momento, non si tiene la posizione in perdita e non si rientra;
  - le soglie vengono dalla curva di §4: 1,30 -> 0,807; 1,50 -> 0,684; 2,00 -> 0,514;
    2,50 -> 0,385; 3,00 -> 0,275, interpolate;
  - `p_under35_cal` e' gia' nel dossier dalla presa in carico
    (`Betfair/mike/service.py:2725`, `D.build_prematch`): **zero letture in piu'**;
  - senza P calibrata (57 % delle partite) il veto tace e la condotta resta quella di oggi.
- **Replay**: `certifica mike` su tutte le registrazioni Mike, scenari
  `base, gol-precoce, senza-seconda-puntata, taker, cap-stretto, bot-fermo`. Da
  confrontare: quante HOLD e quanti PERSIST in meno, il P&L netto sugli scenari con gol
  precoce, violazioni e copertura.
- **Prerequisito**: la parte B (conteggio), in attesa del replay del coordinatore.
- **Rischio**: medio, perche' tocca la gestione della perdita pre-KO. La curva e' stimata
  per il 97 % in campione, anche se il fuori campione dal 21/09 conferma la direzione.

---

## Estrazioni (lanciate dal coordinatore il 25/09, dal worktree, con il `.env` vero)

Tutte in **sola lettura**. `test_estrai_nessuna_scrittura_nel_sorgente` verifica che il
file non contenga nessun metodo di scrittura. Uscite in
`AUDIT_2026-09-25/misura_punto8_dati/`.

**Paginazione rifatta il 25/09 dopo il 57014.** Primo lancio del coordinatore:
- `x1` e' andata a buon fine;
- `o1o6` e `m1` sono andate in statement timeout, perche' la keyset su `fixture_id` con
  il filtro sulla data percorre la PK e scarta milioni di righe;
- `o5` non e' partita, perche' dipende da `estr_o1o6`.

Come legge adesso ogni tabella grande:
- **un giorno alla volta**: `gte(data, g)` e `lt(data, g+1)`, con keyset sulla chiave
  unica dentro il giorno (`keyset_per_giorno`). La data e' `fixture_date` per
  `fixture_predictions`, `run_date` per `betfair_market_odds` e `open_date` (non `created_at`, che non esiste: 42703 al secondo lancio; il finto dei test ora conosce solo le colonne vere) per
  `omega_events`;
- `matches`, `match_events`, `fixture_predictions` e `tennis_markets` si leggono per
  chiave, con `in_()` a blocchi;
- su un **57014**: 3 tentativi, attese di 2 s e poi 4 s, pagina (o blocco) dimezzata. Al
  terzo timeout l'errore risale: mai un file troncato in silenzio. Ogni altro errore
  risale subito.

I test usano un finto che va in 57014 su ogni lettura senza la finestra di un giorno. Le
mutazioni che li fanno diventare rossi sono:
- finestra senza limite superiore;
- finestre sovrapposte;
- nessun ritentativo;
- ritentativo senza dimezzare la pagina;
- blocchi senza ritentativo.

```
set M=Betfair.stream.backtest.tools.misura_punto8
set D=AUDIT_2026-09-25/misura_punto8_dati
REM FATTE (coordinatore, 25/09):
REM   x1   -> estr_x1.json.gz: pagella 256, ml_post_calibration 801, poisson_calibration 517, finestra 20.883, esiti 20.035
REM   m1   -> estr_m1.json.gz: fixture_predictions 20.883, esiti 20.035, campione chiavi 5
REM   o1o6 -> estr_o1o6.json.gz: quote 321, quote_cs 6.155, esiti 319, fixture_predictions 321, omega_events 34
REM   o5   -> estr_o5.json.gz: eventi 5.695
REM   t1   -> 0 righe (eventi del 07/07 assenti da tennis_markets): NON MISURABILE
REM DA FARE (coordinatore): replay Mike, poi il ponte evento->fixture degli stessi eventi
python -m Betfair.stream.backtest.certifica mike <registrazioni Mike> --json > %D%/certifica_mike.txt
python -m %M%.estrai_db mike_ev --eventi-file %D%/certifica_mike.txt --out %D%/estr_mike_ev.json.gz
```

Misure (tutte con il DB finto): le prime cinque sono FATTE, l'ultima e' da fare dopo il
replay Mike.

```
python -m %M%.o1_catena_lambda --estensione %D%/estr_o1o6.json.gz --out %D%/o1_con_estensione.json
python -m %M%.o1_catena_lambda --solo-lambda-source %D%/estr_o1o6.json.gz --out %D%/o1_lambda_source.json
python -m %M%.o6_coda --o1 %D%/o1_con_estensione.json --estensione %D%/estr_o1o6.json.gz --out %D%/o6_con_cs.json
python -m %M%.o5_rossi --estrazione %D%/estr_o5.json.gz --campioni Betfair/omega/data/m2_campione_2026-09-17.json.gz %D%/estr_o1o6.json.gz --out %D%/o5_db.json
python -m %M%.m1_mike affidabilita --estrazione %D%/estr_m1.json.gz --out %D%/m1.json
python -m %M%.x1_bias --estrazione %D%/estr_x1.json.gz --out %D%/x1.json
REM DA FARE dopo il replay:
python -m %M%.m1_mike conta --referto %D%/certifica_mike.txt --estrazione %D%/estr_mike_ev.json.gz --curva %D%/m1.json --out %D%/m1_conta.json
```

---

## NON VERIFICATO

- **Estrazioni**: le ha lanciate il coordinatore, non io (regola dura del 21/09). Ho letto
  solo i file .json.gz. Il conteggio delle righe lo riporto dal suo messaggio e dai file.
- **O1**:
  - la quota reale di partite senza `pre_ko` in produzione: `omega_events` ha solo 34
    eventi del 24/09, e la colonna non distingue «fixture» da «mai valutato»;
  - l'effetto sulle DECISIONI del cancello (celle, ingressi): serve il banco.
- **O5**:
  - la convenzione di API-Football su `team_id` degli autogol non e' assunta: 2 partite
    con gol incoerenti col finale sono state scartate e contate;
  - l'effetto sul cancello e sulle uscite non e' misurato;
  - una sola registrazione con rosso nel banco.
- **O6**:
  - P_nostra: il veto empirico Wilson (`get_omega_minute_ft`) non e' riprodotto, e puo'
    solo alzare la P;
  - la coda IN GIOCO, dove Omega opera davvero, non e' misurata: le quote CS del DB sono
    pre-match;
  - fascia <=1 %: solo 2-5 esiti, IC troppo largo per dire qualunque cosa.
- **M1**:
  - la parte B e' **in attesa del replay `certifica mike`, che lancia il coordinatore**;
  - la curva delle soglie e' stimata per il 97 % in campione;
  - la regola «prima del 21/09 = in campione per la calibrazione Poisson» e' un'ipotesi
    sulla data dell'ultima `poisson_calibration`: la finestra di stima vera della
    calibrazione non l'ho verificata.
- **M2**: non realizzabile. Che la pipeline Poisson possa produrre `over_4_5` non e'
  verificato.
- **T1**: non misurabile (eventi assenti da `tennis_markets`).
- **X1**: misurata, ma la pagella e' in campione e nella finestra mancano i prezzi di
  mercato, quindi l'edge non e' valutabile.
- I test su finti con chiavi identiche sono verdi e falsificati.
- **S2**: le lambda della misura sono `pre_ko` o default. In produzione `resolve_event_lambdas`
  passa prima dalla fixture (`db_json_analisi.inputs`), quindi la P d'uscita reale puo'
  differire.
- **Voce 8**: nessun replay lanciato.
- **Precisione di O1**: la variante e' misurata come «pre_ko, poi la catena attuale». In
  produzione il ripiego `saved` (lambda gia' persistite sull'evento) resterebbe dopo il
  `pre_ko`; qui non esiste, perche' ogni partita e' vista per la prima volta.

---

## File creati

- `Betfair/stream/backtest/tools/__init__.py`, `.../misura_punto8/__init__.py`
- `.../misura_punto8/comune.py`: bootstrap a grappolo, metriche, verdetto, blindatura del DB
- `.../misura_punto8/percorsi.py`: dove stanno le registrazioni, in sola lettura
- `.../misura_punto8/o1_catena_lambda.py`, `o5_rossi.py`, `o6_coda.py`,
  `s2_calibrazione_uscita.py`, `m1_mike.py`, `t1_superficie.py`, `x1_bias.py`
- `.../misura_punto8/estrai_db.py`: estrazioni in sola lettura, da lanciare dal coordinatore
- `.../misura_punto8/test_misura_punto8.py`: 52 test
- `.../misura_punto8/falsifica_misura_punto8.py`: 26 mutazioni
- `AUDIT_2026-09-25/misura_punto8_dati/` (i file `estr_*.json.gz` li ha scritti il
  coordinatore):
  - O1: `o1_catena_lambda.json`, `o1_con_estensione.json`, `o1_lambda_source.json`;
  - O6: `o6_coda.json`, `o6_con_cs.json`;
  - O5: `o5_live_raw.json`, `o5_db.json`;
  - S2: `s2_tutte.json`, `s2_solo_pre_ko.json`;
  - M1: `m1.json`; T1: `t1_superficie.json`; X1: `x1.json`;
  - `falsificazione.txt` e i log.

## Comandi eseguiti (tutti con il DB finto)

| Comando | Esito |
|---|---|
| `o1_catena_lambda --giri 2000` (1.995 partite, circa 20') + `--rifai-sintesi` | tabella §1 |
| `s2_calibrazione_uscita` (tutte / `--solo-pre-ko`) | tabella §5; costruita una sola cache nuova (36106722, 0 campioni), poi cancellata |
| `o5_rossi --live-raw auto` | 1 partita utile: NON MISURABILE |
| `o6_coda --o1 ...` | tabella §3 |
| `t1_superficie` | tabella §6 |
| `x1_bias --estrazione estr_x1` | §7: NON MIGLIORA |
| `m1_mike affidabilita --estrazione estr_m1` | §4: M1 MIGLIORA come informazione; M2 non realizzabile |
| `o1_catena_lambda --estensione estr_o1o6` (2.072 partite) | §1: MIGLIORA, anche sull'estensione |
| `o1_catena_lambda --solo-lambda-source estr_o1o6` | 34 eventi: 29 senza modello, 5 `pre_ko_odds` |
| `o6_coda --o1 o1_con_estensione --estensione estr_o1o6` | §3: calibrata entro l'IC, anche la P_fusa |
| `o5_rossi --estrazione estr_o5 --campioni ...` | §2: MIGLIORA (90 partite con rosso, 77 dal 30/06) |
| `pytest test_misura_punto8.py -q -p no:cacheprovider` | **52 passati** |
| `falsifica_misura_punto8` | **26 mutazioni su 26 ROSSE**, ripristino dalla copia con SHA-256 identico, suite verde dopo il ripristino |
| `git status --porcelain` | solo 2 cartelle nuove non tracciate; nessun file dei bot modificato |
