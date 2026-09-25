# TacticAI: P(0-0) negativa, errore di PROGETTAZIONE nel dominio di rho (25/09/2026)

Delegato Opus, worktree `agent-a8e86c243b644affd`, base `origin/master` 2f04bc4. Niente commit.
Ordine dell'utente: «Controlla che non ci siano errori di PROGETTAZIONE»; quindi niente
clamp sull'uscita: si corregge la causa.

## 1. Causa (catena con file:riga, riferiti a HEAD 2f04bc4)

Dixon & Coles (1997), «Modelling Association Football Scores and Inefficiencies in the
Football Betting Market», Applied Statistics 46(2), sez. 4: la correzione

    tau(0,0) = 1 - lambda*mu*rho    tau(0,1) = 1 + lambda*rho
    tau(1,0) = 1 + mu*rho           tau(1,1) = 1 - rho

moltiplica delle probabilita', quindi ha senso solo se tutte e quattro restano > 0, cioe'

    max(-1/lambda, -1/mu) < rho < min(1/(lambda*mu), 1)

per OGNI partita a cui il modello viene applicato.

1. `tactical_engine/model.py:94-97` definisce le maschere m00/m01/m10/m11 sulle partite
   OSSERVATE; `:112-118` calcola tau solo su quelle celle e rifiuta i parametri
   (`return 1e12`) solo se una di QUELLE tau e' <= 1e-9. Quindi il vincolo di Dixon-Coles
   vale solo per le partite dello storico finite 0-0, 0-1, 1-0 o 1-1.
2. `model.py:125-126`: l'unico altro vincolo su rho e' il box fisso `(-0.2, 0.2)`.
3. Una coppia forte-contro-debole (o due squadre "aperte") con lambda*mu alto quasi mai
   finisce 0-0: nello storico non c'e' la cella che la vincolerebbe. Se la lega ha meno
   0-0/1-1 del Poisson, rho stimato e' positivo (spesso al bordo +0,2).
4. `model.py:165` `predict` usa lo stesso rho per ogni coppia: `dixon_coles.py:55`
   moltiplica la cella 0-0 per `1 - lh*la*rho`, che e' < 0 appena `lh*la > 1/rho`
   (= 5 con rho = 0,2). La rinormalizzazione di `dixon_coles.py:57-59` divide per la somma
   (la massa della correzione DC si compensa: la somma resta ~1) ma non puo' rendere
   positiva una cella negativa.
5. `markets_from_matrix`: `under_0_5 = 1 - over_0_5 = P(0-0) < 0`, `over_0_5 > 1`.

Ipotesi scartate: (b) rho fissato al bordo e non ottimizzato: NO, rho e' ottimizzato (sui
17 veri ci sono anche 0,1637 e 0,1475, sotto il bordo; nel sintetico seed 0 rho = 0,1587
interno e le P(0-0) sono comunque negative). (c) ridge/emivite: NON sono la causa (il
RIDGE 0,08 anzi accorcia le lambda), ma sono un fattore: vedi §6.

Riprodotto sul modello di prima con un test (rosso prima del fix, §4, F0): lega sintetica
con meno 0-0/1-1 del Poisson, 12 squadre, 528 partite: 16-38 coppie ordinate su 132 con
`under_0_5 < 0` (minimo -0,00208), stesso ordine di grandezza dei veri (-0,0001 ... -0,0021).

## 2. Verifica della diagnosi sui 17 payload VERI (estrazione del coordinatore)

`python -m tactical_engine.tools.verifica_payload_tacticai AUDIT_2026-09-25/payload_tacticai_negativi_2026-09-25.json`
(sola lettura, nessun DB). «u05 ricostr» = griglia ricalcolata con la formula di prima
da `lambda_home`, `lambda_away`, `training.rho` scritti: coincide con il valore scritto su
17/17, e rho e' FUORI dal dominio della coppia su 17/17 (rho > 1/(lh*la)).

| fixture_id | lega | lh | la | rho | lh*la | 1/(lh*la) | u05 scritto | u05 ricostr. | u05 HT scritto | rho proiettato | u05 dopo (stima locale) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1533042 | 1093 | 3,566 | 2,682 | 0,2000 | 9,564 | 0,1046 | -0,0018 | -0,0018 | 0,0625 | 0,1045 | 0,000002 |
| 1533034 | 1093 | 3,581 | 1,735 | 0,2000 | 6,213 | 0,1610 | -0,0012 | -0,0012 | 0,1222 | 0,1608 | 0,000005 |
| 1533035 | 1093 | 1,139 | 5,240 | 0,2000 | 5,968 | 0,1676 | -0,0003 | -0,0003 | 0,0804 | 0,1674 | 0,000002 |
| 1532295 | 1117 | 2,792 | 2,433 | 0,1637 | 6,793 | 0,1472 | -0,0006 | -0,0006 | 0,0688 | 0,1471 | 0,000005 |
| 1521641 | 1126 | 2,633 | 2,832 | 0,1475 | 7,457 | 0,1341 | -0,0004 | -0,0004 | 0,0894 | 0,1340 | 0,000004 |
| 1536096 | 1091 | 2,727 | 2,241 | 0,2000 | 6,111 | 0,1636 | -0,0015 | -0,0015 | 0,1910 | 0,1635 | 0,000007 |
| 1533116 | 1091 | 2,792 | 2,756 | 0,2000 | 7,695 | 0,1300 | -0,0021 | -0,0021 | 0,0762 | 0,1298 | 0,000004 |
| 1533040 | 1093 | 5,307 | 1,345 | 0,2000 | 7,138 | 0,1401 | -0,0006 | -0,0006 | 0,0657 | 0,1400 | 0,000001 |
| 1533130 | 1091 | 4,828 | 1,649 | 0,2000 | 7,961 | 0,1256 | -0,0009 | -0,0009 | 0,0349 | 0,1255 | 0,000002 |
| 1533126 | 1091 | 2,265 | 4,125 | 0,2000 | 9,343 | 0,1070 | -0,0015 | -0,0015 | 0,0891 | 0,1069 | 0,000002 |
| 1536095 | 1091 | 2,646 | 2,499 | 0,2000 | 6,612 | 0,1512 | -0,0019 | -0,0019 | 0,0842 | 0,1511 | 0,000006 |
| 1533129 | 1091 | 4,728 | 1,226 | 0,2000 | 5,797 | 0,1725 | -0,0004 | -0,0004 | 0,0655 | 0,1723 | 0,000003 |
| 1533132 | 1091 | 1,098 | 5,241 | 0,2000 | 5,755 | 0,1738 | -0,0003 | -0,0003 | 0,0302 | 0,1736 | 0,000002 |
| 1533133 | 1091 | 3,632 | 1,452 | 0,2000 | 5,274 | 0,1896 | -0,0003 | -0,0003 | 0,1168 | 0,1894 | 0,000006 |
| 1532259 | 1117 | 2,908 | 2,644 | 0,1638 | 7,689 | 0,1301 | -0,0010 | -0,0010 | 0,4936 | 0,1299 | 0,000004 |
| 1533031 | 1093 | 3,327 | 1,790 | 0,2000 | 5,955 | 0,1679 | -0,0011 | -0,0011 | 0,1428 | 0,1677 | 0,000006 |
| 1533033 | 1093 | 7,713 | 1,009 | 0,2000 | 7,782 | 0,1285 | -0,0001 | -0,0001 | 0,0205 | 0,1284 | 0,000000 |

Riepilogo dello script: `payload: 17 | under_0_5 scritto < 0: 17 | rho fuori dal dominio
della coppia: 17 | griglie valide dopo: 17/17`, somma griglia 1,000000000000 su tutti.
Le griglie HT (`markets_ht`) sono valide su 17/17 (lambda HT basse).

Attenzione: la colonna «dopo» e' la stima LOCALE (rho proiettato sul dominio della sola
coppia, lambda scritte). Il valore definitivo lo da' il fit vincolato della lega (§3), che
tiene conto della coppia piu' estrema della lega: rho piu' basso e forze leggermente
diverse. Si misura con `--rifit` (§5).

Leghe coinvolte: 1091, 1093, 1117, 1126 (squadre U21 / «II», storici corti: la 1093 ha
n=241, eff=124,1), lambda fino a 7,7.

## 3. Correzione di progettazione

File: `tactical_engine/dixon_coles.py`, `tactical_engine/model.py` (serving.py NON
toccato; `Prediction/today_predictions_backfill.py` NON toccato).

1. `dixon_coles.rho_bounds(lh, la, tau_min)` (`dixon_coles.py:40`): il dominio di
   Dixon-Coles della coppia, con margine `tau_min` (ogni tau >= tau_min). Funzione nuova;
   `score_matrix` e `dc_tau` sono INVARIATE (le usa anche
   `Betfair/stream/engine/live_engine_pro.py` con la sua `effective_rho`: nessun effetto sul
   bot, test `Betfair/stream/tests/test_motore_probabilistico_2026_09_12.py` 22/22 verdi).
2. `model._rho_limits_all_pairs` (`model.py:59`): intersezione dei domini su TUTTE le
   coppie ordinate (i casa, j trasferta, i != j) della lega, in forma chiusa:
   `log(lh*la) = 2c + g + s_i + s_j` con `s = attack - defense` (massimo sulle due s piu'
   alte), `log(lh) = c + g + a_i - d_j` (massimo su i != j), `g = max(gamma, 0)` per coprire
   anche `predict(neutral=True)`; box storico |rho| <= 0,2 incluso. Verificata contro la
   forza bruta coppia per coppia (test).
3. Fit a due stadi (`model.py:166-205`):
   - STADIO 1 = il fit di prima, codice identico (stesso punto iniziale, stessi bound,
     stesse opzioni L-BFGS-B).
   - Se rho dello stadio 1 e' nel dominio di tutte le coppie, e' anche l'ottimo del
     problema vincolato (il dominio nuovo e' un sottoinsieme del vecchio): si tiene, e le
     partite «normali» restano IDENTICHE bit per bit.
   - Altrimenti STADIO 2: MLE VINCOLATA con la riparametrizzazione
     `rho = t*hi(p)` per t >= 0, `rho = t*|lo(p)|` per t < 0, t in [-1, 1], dove
     (lo, hi) = dominio di tutte le coppie per i parametri correnti p. Copre esattamente
     l'insieme ammissibile, quindi L-BFGS-B ottimizza forze, costante, campo e rho
     insieme dentro il dominio (non e' un taglio a posteriori: le forze si riadattano).
     Partenza dalla soluzione dello stadio 1.
   - `FitResult` guadagna `rho_unconstrained` (rho dello stadio 1) e
     `rho_constraint_active` (default compatibili).
4. `predict` (`model.py:246-247`): rho proiettato nel dominio della coppia con margine
   `TAU_MIN`, poi `score_matrix` rinormalizza. Dopo il fit vincolato e' un'identita' (rho
   gia' dentro); resta come garanzia per costruzione per ogni `FitResult` (es. costruito a
   mano). `predict` restituisce anche `rho_effective` (chiave nuova, il serving non la
   legge).
5. `TAU_MIN = 1e-3` (`model.py:38`): ogni cella bassa corretta vale almeno lo 0,1 % del
   suo valore Poisson. Scelta di margine numerico, non di strategia.

Perche' questa e non un clamp: il modello di prima massimizzava una verosimiglianza di
un modello che per alcune coppie non era una distribuzione di probabilita'; il vincolo
nel fit rende la stima una MLE vera sul dominio in cui il modello esiste. La proiezione
in predict da sola (alternativa A sotto) avrebbe lasciato le forze stimate con un rho
inammissibile.

Alternative (NON implementate, da decidere con l'utente):
- A. Solo proiezione di rho in predict, per coppia. Pro: cambia solo le coppie estreme,
  nessun rifit. Contro: incoerente col fit (rho diverso tra stima e previsione), le forze
  restano stimate con un modello improprio; e' di fatto la guardia cieca che l'utente non
  vuole.
- B. rho per lega (e' gia' cosi': un fit per lega) ma con prior/shrinkage verso un rho
  globale (es. -0,1 ... 0). Pro: leghe con storico corto non vanno al bordo +0,2. Contro:
  un iperparametro in piu' da validare fuori campione.
- C. rho dipendente dalle lambda (es. tau solo su 0-0 con rho scalato 1/(lh*la), o la
  forma di Dixon-Coles «a moltiplicatore» limitata). Pro: nessuna coppia estrema detta il
  rho di tutta la lega. Contro: non e' piu' il modello DC standard, va rivalidato.
- D. Dipendenza tramite Poisson bivariato (Karlis & Ntzoufras 2003) o copula di Frank
  (McHale & Scarf 2007): probabilita' valide per costruzione a qualunque lambda. Pro:
  elimina il problema alla radice. Contro: riscrittura del motore e validazione completa.

## 4. Test e falsificazione

Nuovi: `tactical_engine/tests/test_rho_ammissibile.py` (9 test),
`tactical_engine/tests/test_verifica_payload.py` (4 test, uno legge i 17 veri e si salta
se il file manca). Payload finti costruiti con `serving._build_payload` (chiavi e tipi del
vero), storico con le chiavi di `matches`, finto client di `test_serving.py`.

Suite: `SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x
timeout 600 python -m pytest tactical_engine/tests -q -p no:cacheprovider` ->
**24 passed** (11 esistenti + 13 nuovi). `Betfair/stream/tests/test_motore_probabilistico_2026_09_12.py`
(importa `score_matrix`/`dc_tau`) -> 22 passed.

Falsificazioni (ogni mutazione ripristinata da copia salvata, `cmp` identico):
- F0 modello di prima (`model.py` di HEAD) -> `test_nessuna_p00_negativa...[0]` e `[2]`
  ROSSI su «cella negativa -0,000505» / «-0,000347».
- F1 vincolo tolto (`active = False`) -> gli stessi 2 ROSSI («dataset che non espone il
  difetto»); F1b stadio 2 senza limiti (`rho = t*0,2`) -> ROSSI su `rho 0,2 > hi 0,1289`.
- F2 proiezione tolta in predict (`rho_eff = f.rho`) ->
  `test_predict_garantisce_tau_positiva...` ROSSO («cella negativa -0,00123»).
- F3 rinormalizzazione rotta (`return grid` in `score_matrix`) -> ROSSI su «somma griglia
  0,99480» e «0,99958».
- F4 script senza proiezione -> `test_payload_negativi...` e `test_i_17_payload_veri` ROSSI;
  F1 applicata al modello -> anche il test del `--rifit` ROSSO.

## 5. Effetto sulle partite normali (numeri)

Confronto modello di HEAD vs modello corretto (copia di HEAD importata a parte), 12
squadre, 528 partite per lega, RIDGE 0,08:
- 10 leghe realistiche (rho vero -0,05, lambda stimate p10-p90 fra 0,80 e 2,29): stadio 2
  MAI entrato, rho identico, **max |differenza| griglia = 0 e mercati = 0 (esatto)**.
- 9 leghe «al bordo» su 10 (meno 0-0/1-1 del Poisson): stadio 2 entrato; coppie con
  under_0_5 < 0 prima: 2-38 per lega, dopo: 0; rho da +0,146...+0,20 a +0,046...+0,20
  (in un caso rho resta 0,20 e si riadattano le forze); scarto
  massimo sui mercati di tutta la lega 0,002-0,044 (rho e' unico per lega: cambia per
  tutte le coppie). La decima (bordo35 seed 1, rho 0,2 ma coppie nel dominio) e'
  invariata (0 esatto).
- Test automatico: `test_partite_normali_invariate` (3 leghe) differenza < 1e-6 (misurata 0).

Conseguenza da portare all'utente: nelle leghe in cui il vincolo entra (qui 1091, 1093,
1117, 1126) TUTTI i mercati della lega si spostano, non solo le partite negative; nel
sintetico fino a ~4 punti percentuali. E' la stima corretta del modello DC, ma il
cambiamento e' visibile (e i payload sono letti anche da `Betfair/omega/tools/m2_pesi.py` e
dagli strumenti di `Betfair/stream/backtest/tools/misura_punto8/`).

## 6. Come verifica il coordinatore sui 17 veri

1. Stima locale, nessun DB: `python -m tactical_engine.tools.verifica_payload_tacticai
   AUDIT_2026-09-25/payload_tacticai_negativi_2026-09-25.json` (esito sopra, exit 0).
2. Valore definitivo, SOLO SELECT sul DB (fixture_predictions per gli id squadra, matches
   per lo storico, stessa lettura keyset del serving), nessuna scrittura:
   `python -m tactical_engine.tools.verifica_payload_tacticai AUDIT_2026-09-25/payload_tacticai_negativi_2026-09-25.json --rifit`.
   Attesi: `n_scr == n_rifit` e `rho_st1 == rho_scr` (stesso primo stadio di allora; se
   lo storico e' cambiato lo si vede qui), `att = SI`, `u05_rifit >= 0`, somma 1, e lo
   `scarto_max` dei mercati rispetto al payload scritto (da riportare all'utente).
3. Dopo il merge, il prossimo run del serving riscrive i payload delle partite del giorno;
   i 17 sono di date passate (luglio-settembre) e restano come sono finche' non si
   ricalcolano: decidere se riscriverli (il serving non fa backfill storico).

Osservazione aggiuntiva (non toccata): lambda fino a 7,7 con storici di 241 partite
(eff 124) indicano forze molto disperse nelle leghe giovanili/riserve; RIDGE 0,08 e emivita
420 gg valgono per tutte le leghe. Una ridge piu' forte per le leghe con eff_matches basso
(o MIN_PRIOR piu' alto) ridurrebbe le lambda estreme: proposta, da validare fuori campione.

## NON VERIFICATO

- Il `--rifit` sul DB vero: provato solo con il finto client; i valori definitivi (rho
  vincolato, under_0_5, scarto dei mercati) delle leghe 1091/1093/1117/1126 non li conosco.
- Che lo storico di quelle leghe oggi sia lo stesso dei giorni dei payload (il rifit lo
  mostra con `n_scr/n_rifit` e `rho_st1`).
- Durata del fit nelle leghe con stadio 2 (misurata solo sul sintetico: pochi secondi).
- Effetto sui consumatori dei payload (Omega `m2_pesi`, misura_punto8, frontend
  TacticalEnginePanel): nessuno toccato, nessuno rilanciato.
- Nessun backtest di calibrazione fuori campione del modello vincolato vs quello di prima.

## File toccati

- M `tactical_engine/dixon_coles.py` (+ `rho_bounds`)
- M `tactical_engine/model.py` (TAU_MIN, RHO_BOX, `_rho_limits_all_pairs`, fit a due
  stadi, campi FitResult, proiezione in predict)
- A `tactical_engine/tools/__init__.py`, `tactical_engine/tools/verifica_payload_tacticai.py`
- A `tactical_engine/tests/test_rho_ammissibile.py`, `tactical_engine/tests/test_verifica_payload.py`
- A questo referto. `AUDIT_2026-09-25/payload_tacticai_negativi_2026-09-25.json` e' del
  coordinatore (non modificato).

## 7. Dopo il --rifit del coordinatore: fixture 1533031, scarto 0,3775

- In locale (senza DB) sul payload scritto il mercato piu' spostato e' `draw`
  0,1326 -> 0,1349 (|d| 0,0023): il vincolo su rho da solo non sposta nulla di 0,38.
- Il mercato di 0,3775 e' `home`: con le lambda del rifit (2,145/2,764, rho 0,0284)
  home 0,6819 -> 0,3044; double_x2 +0,3775; away 0,1855 -> 0,5190.
- Le lambda del rifit sono quelle del payload con casa/trasferta INVERTITE:
  1,790*e^0,1866 = 2,157 e 3,327/e^0,1866 = 2,761 contro 2,145/2,764 (il residuo di circa
  0,01 e' l'effetto del vincolo).
- Causa probabile: nella riga di oggi di `fixture_predictions` home_team_id/away_team_id
  sono invertiti rispetto alla partita del payload del 21/06 (University of Tasmania -
  Clarence Zebras II; allora il serving leggeva le partite da `matches`). Non e' il
  confronto, non e' l'HT (non confrontato), non e' lo storico (n uguale). NON VERIFICATO
  sul DB: lo dice il nuovo controllo.
- Lo script (--rifit) ora stampa: mercato con lo scarto massimo (nome, prima, dopo),
  lambda scritte e del rifit, 1/X/2 prima e dopo, `converged`, e «ATTENZIONE squadre
  diverse» se i nomi casa/trasferta del payload non coincidono con la riga di oggi. Test
  con inversione simulata; controllo falsificato (sempre coerente -> rosso). Suite
  `tactical_engine/tests`: 24 passed.
