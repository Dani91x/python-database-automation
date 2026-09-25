# FEDELTÀ DEI BOT SAFE ALLE TRASCRIZIONI DEI VIDEO — 25/09/2026

> Delegato del coordinatore, lavoro in SOLA LETTURA: nessuna modifica al codice, nessun commit,
> nessuna scrittura sul DB, nessun processo avviato.
> Ordine dell'utente: «voglio sapere se i bot SAFE (tutti) sono progettati per lavorare come da
> strategia, in ogni sua parte (nessuna modifica, devi prima comunicarmi)».
> Fonte primaria: le 57 trascrizioni faster-whisper del 24/09 in
> `C:\Users\Admin\Desktop\Strategia S - Giuseppe Bentivegna\TRASCRIZIONI\Strategia S - Giuseppe Bentivegna\`
> (`_progresso.log`: «FINE: 57/57 trascritti»). Le ho lette TUTTE, per intero.
> Citazioni: `[cartella/video @secondi]` = file .txt e marcatore temporale della riga.
> Abbreviazioni cartelle: `SEL` = 2. SELEZIONE PARTITE, `STR` = 4. STRATEGIA, `EXT` = 5. EXTRA,
> `INT` = 1. INTRODUZIONE, `EXC` = 3. EXCHANGE BETFAIR, `RE-SEL`/`RE` = RISULTATO ESATTO,
> `PU` = VARIANTE PUNTA/1. STRATEGIA, `TE-INT`/`TE-SEL`/`TE`/`TE-EXT` = TENNIS/1., 3., 4., 5.
> Qualità dell'audio: modello `small`; alcune parole storpiate («crash out» = cash out,
> «ligand» = Ligue 1, «Redivisie» = Eredivisie). Dove un numero è storpiato lo dico.
> Codice letto nel worktree `agent-aed0527b2a58a621a`: `engine.py`, `exits.py`, `bot_service.py`,
> `selezione.py` IDENTICI al checkout principale (verificato con `cmp`); `risk.py` DIVERSO (vedi §5).

---

## FASE 1 — MAPPA DELLA STRATEGIA DAI VIDEO

Legenda «forza»: **E** = esplicita (regola detta come tale, con numeri), **I** = implicita
(si ricava dall'esempio o dal contesto), **A** = ambigua (audio/parole incerte, oppure detta come
«dipende», «valuto»).

### 1.0 Regole trasversali (valgono per tutte le varianti)

| # | regola | citazione | forza |
|---|---|---|---|
| X1 | Non uscire mai dalla strategia, niente «cose di testa tua» | `INT/1. Premessa @15.4-36.6` «prima di tutto non devi uscire dalla strategia … Devi fare esattamente quello che viene detto» | E |
| X2 | Responsabilità = TUTTA la cassa messa a disposizione, usata a ogni operazione | `INT/2 @19.5` «ad ogni operazione noi utilizziamo tutta la cassa che mettiamo a disposizione»; `EXC/2 @149-158` «cliccherò su rischio … ho una cassa da 100 che voglio utilizzare tutta per l'operazione, metterò 100» | E |
| X3 | Rischio effettivo per operazione ≈ 10%, al massimo 12% della responsabilità | `INT/2 @55.2-70.7` «rischieremo all'incirca, massimo un 10 a dire tanto 12%» | E |
| X4 | Cassa iniziale calcio 100 € (max 100-150), si alza piano piano, mai di colpo | `INT/2 @31.7`, `INT/3 @0.3-83.5` | E |
| X5 | Rendimento atteso 1-5% per operazione (media 2,5%), ~1 operazione al giorno | `INT/4 @134.9-147.9`, `@72.6` | E (descrittiva) |
| X6 | Mercato di lavoro calcio = «esito finale» 1X2 (base e punta) | `EXC/2 @62.6` «Mi raccomando andiamo noi a lavorare con il mercato esito finale, quindi il classico 1x2» | E |
| X7 | Spread: meglio piccolo (= più liquidità) | `EXC/3 @130.2-143.7` | E (consiglio, senza numero) |
| X8 | Bisogna VEDERE la partita (non statistiche, non radiocronaca, non «riquadrino») | `STR/9 @0.3-24.3`, `@91.1-100.6` «non facciamo l'errore di non vedere le partite perché vuol dire non stare facendo la strategia» | E |
| X9 | Primo criterio di selezione = orario: operare solo se posso seguire concentrato | `SEL/1 @76-115`; `RE-SEL/1 @25.6` «il primo criterio è sempre l'orario» | E (umano) |
| X10 | Dispositivo di riserva sempre pronto per il cashout | `STR/8 @5.5-21.0` | E (umano) |
| X11 | Uscita: tastone cashout (conferma, 3-4 s) oppure a mano con il calcolatore (contropunta alla quota del momento) oppure Betting Toolkit | `STR/4 @6-23`, `EXT/2 @29.1-207.1`, `RE/4 @17.3`, `PU/4 @0-20` | E |
| X12 | Il cashout di Betfair a volte «sfasa»/scompare, soprattutto nei minuti finali: saper uscire in manuale; restano centesimi di aggiustamento | `EXT/2 @0.1-29.1`, `STR/10 @136-183` | E |
| X13 | Emergenza (Betfair in tilt): contropuntare su altro bookmaker (o doppia chance) | `STR/11 @0-230.7` | E (umano, «ultima spiaggia») |
| X14 | Appena entrati una piccola perdita apparente è normale (spread), si pareggia «in un minuto di solito» | `STR/10 @71.4-91.4` | E (descrittiva) |
| X15 | Tenere traccia di ogni operazione (data, squadre, responsabilità, quota di banca d'ingresso, profitto); commissione Betfair 4,5% | `EXT/1 @62.7-113.7`; `TE-EXT/1 @120` | E |
| X16 | La perdita va accettata (disciplina) | `STR/6 @0.6-24.4`, `@82.4`, `@107.7-115.8`; `PU/6 @0.1`; `TE-INT/1 @21-67.9` | E |

### 1.1 CALCIO — BASE (banca la squadra che perde, 1X2)

**Selezione pre-partita**

| # | regola | citazione | forza |
|---|---|---|---|
| B-S1 | Quota pre-partita della «leggermente favorita» 1,40-1,80 | `SEL/1 @167-172.9` «Queste quote devono essere, per quanto riguarda la squadra leggermente favorita tra l'une 40 e l'une 80» | E |
| B-S2 | Quota pre-partita della sfavorita 4-8 («solitamente») | `SEL/1 @180.5-186.7` «mentre per quanto riguarda la sfavorita tra il 4 e l'8 solitamente» | E |
| B-S3 | Le quote vanno CONFERMATE dalla classifica: non prima contro ultima, non due squadre pari a metà classifica | `SEL/1 @196.6-211.1` | E (senza numeri) |
| B-S4 | FLESSIBILITÀ: favorita tollerata fino a 2,20, sfavorita fino a 3 (quindi 3-8); la coppia 2,20/3 è il «limite assoluto» | `EXT/3 @114.2-158.2` «c'è una tollerabilità che può andare … sulla favorita dall'1 a 80 al 2,20. Mentre per la sfavorita che arriva anche fino al 3» | E |
| B-S5 | Quote e classifica si valutano INSIEME: quote al limite + squadre attaccate in classifica = evito; classifica distante = posso; «tre posizioni di distacco, favorita 2,20, sfavorita 3,50: ci posso ragionare» | `EXT/3 @165.2-242.2` | E (regola) / A (soglie in «posizioni» dette come esempi) |
| B-S6 | Più ci si allontana dai parametri originali, più cresce la perdita eventuale: 8-10% → 12-15%, fino al 20% se «proprio fuori»; è una scelta sul proprio grado di rischio, da decidere guardando il campo | `EXT/3 @265.2-333.2` | E |
| B-S7 | Competizioni da EVITARE: calcio femminile e amichevoli (primi fra tutti); coppe, soprattutto fasi finali, e partite con carica emotiva alta; Bundesliga ed Eredivisie e «soprattutto le loro serie B»; campionati imprevedibili («serie boliviana») | `SEL/2 @0.3-116.5` | E (liste) / A («coppe» senza distinguere i turni iniziali; «imprevedibili» senza elenco) |
| B-S8 | Campionati MIGLIORI: Serie A, Liga, Premier, Ligue 1 e le loro serie B; Cina, Giappone, Brasile, Argentina; «tutti i restanti europei» (es. Finlandia, Polonia, Portogallo, Turchia) | `SEL/3 @0.0-39.9` | E |

**Ingresso**

| # | regola | citazione | forza |
|---|---|---|---|
| B-E1 | Si sfrutta il SECONDO tempo; il primo tempo non si guarda | `STR/1 @7.8`, `@109.1` «io al primo tempo non lo guardo neanche … dal 45esimo … potrò tranquillamente collegarmi» | E |
| B-E2 | Punteggi utili, sempre IN FAVORE della leggera favorita: 1-0 (il più frequente), 2-1 (va benissimo, un po' più di rischio), 2-0 (rarissimo: «le quote in quell'angeli è difficile trovarle») | `STR/1 @44.1-103.1` | E |
| B-E3 | Si BANCA la squadra che sta perdendo, mercato 1X2 | `STR/2 @0.0-17.7` | E |
| B-E4 | Minuto ideale 60'; «può essere il 62, come il 57, 55, dipende anche da quella che è la partita» | `STR/2 @50.4-69.8` | E (60') / A (banda 55-62 non chiusa: «dipende») |
| B-E5 | **Quote ideali d'ingresso «dal 20 al 34, a dir tanto»**; «può essere qualcosa meno o qualcosa di più, però atteniamoci a questo, soprattutto in fase iniziale»; «più è bassa la quota più è alto il rischio, più è alta la quota più il profitto è minore» | `STR/2 @69.8-118.6` | **E** (numeri e verso della regola). Vedi riquadro 1.1-bis |
| B-E6 | **CONDIZIONE**: si banca SOLO se la squadra che vince ha il controllo (possesso, attacca); se la perdente «martella», non si entra. Entrare senza guardare è «assolutamente sbagliato e assolutamente vietato» | `STR/3 @0.3-66.1` | **E** |
| B-E7 | Prima di bancare si guarda la partita almeno 4-5 minuti (dal 45'-50', in alcune partite dal 53'-54') | `STR/3 @69.1-91.3` | E |
| B-E8 | Rosso alla squadra che VINCE prima dell'ingresso = «mezzo gol subito» → la partita si evita del tutto | `STR/7 @14.0-41.0` «se non ero entrato … evito totalmente di farlo, evito totalmente il match» | E |
| B-E9 | Dimensione: responsabilità = cassa intera (100 €) inserita nella casella «rischio»; la bancata = profitto massimo | `EXC/2 @149-165.2`, `STR/10 @38.3-49.7` | E |

> **1.1-bis — IL NUMERO DELLA QUOTA D'INGRESSO (scoperta principale di questo audit)**
>
> Il riassunto su cui è scritta la SPEC riporta «quota di entrata **1.20-1.34**» e la SPEC
> (`SPEC_STRATEGIA_S.md:31-61`) lo dichiara ambiguo e sceglie la «Lettura A» (quota live della
> FAVORITA). **Il video dice «dal 20 al 34»**, detto subito dopo «Bancherò questa squadra ma a che
> condizioni?», cioè il prezzo a cui si BANCA la squadra che perde (`STR/2 @50.4-118.6`). Quattro
> riscontri indipendenti nelle trascrizioni lo confermano:
> 1. il verso della regola: «più è bassa la quota più è alto il rischio, più è alta … profitto
>    minore» (`STR/2 @111-118.6`) è esattamente il comportamento di un LAY a responsabilità fissa
>    (profitto = responsabilità / (quota − 1)); per un back della favorita il profitto crescerebbe
>    con la quota, non calerebbe;
> 2. l'esempio d'emergenza: «Abbiamo bancato con 200 euro di responsabilità a quota 20 e quindi il
>    nostro profitto massimo sono questi 10 euro e 52» (`STR/11 @67.7`): 200/19 = 10,53 ✔;
> 3. l'esempio di uscita manuale: «lo abbiamo bancato a quota a 22» (`EXT/2 @72.1`) e il foglio di
>    traccia chiede «la quota di banca di ingresso» (`EXT/1 @84.8`);
> 4. il tennis: «Quote ideali … tra 1 e 0-3 per la puntata e **18 e 34 per la bancata. Già le
>    conoscete?**» (`TE/2 @118.3-127.3`): «già le conoscete» rimanda al calcio; e bancare a 18-34
>    equivale a puntare a ~1,03-1,06, cioè allo stesso «1,03» della puntata (1/(1−1/34) = 1,030;
>    1/(1−1/18) = 1,059). Anche il «Lay 1,18-1,34» del tennis nella SPEC (`SPEC:109`) è quindi la
>    stessa storpiatura di «18-34».
>
> Coerenza con il resto dei video: con responsabilità 100 € e banca a 20-34 il profitto massimo è
> 3,0-5,3 € = 3-5% della cassa, esattamente il «dall'1 al 5%, media 2,5%» di `INT/4 @147.9`.
> L'aritmetica che la SPEC usa per scartare la «Lettura B» (`SPEC:40-50`) parte dal numero
> sbagliato (1,28 invece di 28): con 28 il conto torna (100/27 = 3,70 € di profitto massimo).
> **Forza: E.** Rimane A solo l'estremo («a dir tanto», «qualcosa meno o qualcosa di più»).

**Uscite**

| # | regola | citazione | forza |
|---|---|---|---|
| B-U1 | PROFITTO 1: la squadra che vince segna → «già avrò raggiunto quasi il massimo profitto e **valuto se uscire o aspettare qualche minuto**» | `STR/5 @29.9-54.5` | E (evento) / A (uscita subito o qualche minuto dopo: discrezionale) |
| B-U2 | PROFITTO 2: il secondo gol non arriva → «Io intorno al **massimo 83°, 80, 83°** esco … non vado a rischiare negli ultimi minuti anche se la squadra in vantaggio sta tenendo il controllo» | `STR/5 @61.0-99.7` | **E** (uscita a tempo non condizionata al controllo) |
| B-U3 | PROFITTO 3 (pari/piccola perdita): la squadra che vinceva perde il controllo, l'altra attacca → esco anche in pari o con perdita di centesimi | `STR/5 @99.7-140.9` | E |
| B-U4 | PERDITA: gol del pareggio (rigore, contropiede, «qualsiasi cosa») → esco e ACCETTO la perdita; regola che «va seguita per forza» | `STR/6 @0.6-104.3` | **E** |
| B-U5 | Perdita attesa ≈ 8-12% della responsabilità | `STR/6 @90.1` | E (descrittiva) |
| B-U6 | Dopo il gol le quote si congelano: aspetto «20, 30 secondi, 40, un minuto a dir tanto» che si assestino, poi esco | `STR/6 @123.0-138.0` | E |
| B-U7 | Rosso alla squadra che VINCE a posizione aperta → «nel 90% dei casi, se non di più, esco» | `STR/7 @41.0-50.0` | E (90%: discrezionale sul 10%) |
| B-U8 | Rosso alla squadra che PERDE → «non ci interessa, anzi benvenga» | `STR/7 @6.0` | E |
| B-U9 | Non uscire subito dopo l'ingresso: si aspettano minuti in base alla partita; si esce prima se si vedono «situazioni che non mi piacciono» | `STR/10 @106.9-129.1` | I |
| B-U10 | Ingresso a 2-0 o 2-1: che cosa fare se la perdente segna (2-0 → 2-1) NON è detto (il video parla solo di «pareggio») | `STR/6 @36.5` | **A (vuoto nel video)** |

### 1.2 CALCIO — RISULTATO ESATTO (banca «Altro risultato Casa/Ospite»)

| # | regola | citazione | forza |
|---|---|---|---|
| E-S1 | Classifica e quote pre-partita «ci interessano sì ma anche relativamente» per questa variante | `RE-SEL/1 @9.6-20.9` | E (le bande della base NON sono requisito) |
| E-S2 | Primo criterio: orario | `RE-SEL/1 @25.6` | E (umano) |
| E-S3 | Scontri diretti: se ci sono «troppi» 2-2, 3-2, 4-2, 4-1 → evito; 0-0, 1-1, 1-0, 2-0, 2-1 vanno bene; «un solo 3-2 mi fa storcere il naso»: al limite ma fattibile | `RE-SEL/1 @46.4-106.6` | E (criterio) / A (nessuna soglia numerica) |
| E-S4 | Gol subiti: guardo la difesa della squadra NON bancata (e anche di quella da bancare); se ne ha subiti «qualcuno in più» si valuta | `RE-SEL/1 @119.8-174.5` | E (criterio) / A (nessuna soglia) |
| E-S5 | «Parla sempre il campo principalmente» | `RE-SEL/1 @106.6-112.7` | E |
| E-E1 | Secondo tempo, ma con l'avanzamento delle quote «in maniera diversa» | `RE/1 @7.2` | E |
| E-E2 | Punteggi utili: la trascrizione dice «1-0 a 0, 1-1 a 1 o un 2 a 1» | `RE/1 @14.0` | **A** (audio storpiato: plausibile «0-0, 1-0, 1-1, 2-1» come nel riassunto; il vincolo forte è E-E4) |
| E-E3 | Mercato Risultato Esatto, «altro risultato casa o ospite» | `RE/1 @32.6`, `RE/3 @7.0` | E |
| E-E4 | Si banca la squadra che ha segnato AL MASSIMO un gol; «se a due non si va a bancare l'altro risultato, né casa, né ospite, in ogni caso» | `RE/2 @0.1`, `@67.1`; `RE/6 @13.2-28.4` | E |
| E-E5 | La squadra bancata può essere anche la favorita («anche se è appunto favorita … andremo a bancarla») | `RE/6 @28.4` | E |
| E-E6 | Minuto ideale 48'-49'-50' | `RE/2 @30.1` | E (banda stretta, nessun «dipende») |
| E-E7 | Quote ideali 30-70; «conservativa: il profitto più basso, anche la loss … molto più bassa» | `RE/2 @30.1-55.1` | E |
| E-E8 | **CONDIZIONE (invertita)**: la squadra da bancare NON deve avere il controllo; partita «tranquilla, non troppo aggressiva, in cui non si presume che facciano quattro gol» | `RE/3 @25.0-71.3` | **E** |
| E-E9 | Guardo dal 45' i primi 3-4 minuti del secondo tempo prima di bancare | `RE/3 @44.3-55.3`; `RE/6 @43.1` | E |
| E-U1 | PROFITTO: esco in positivo se la squadra bancata non segna altri gol; «qui comanda solo il tempo»: anche un gol dell'avversaria (0-1 → 1-1) «non mi cambia di molto» | `RE/4 @25.2-65.0` | E |
| E-U2 | Uscita a tempo: «è ancora meglio non stare a mercato dopo il 75, quindi massimo al 70, 75 esco» | `RE/4 @65.0-91.3` | **E** |
| E-U3 | PERDITA: la squadra bancata segna comunque (es. 1-0 → 2-0) → esco e accetto la perdita; al 3° gol si perderebbe «una buona metà, se non di più, 60-70%» | `RE/5 @0.0-54.4` | **E** (il 60-70% è la perdita EVITATA al 3° gol, non la perdita tipica dell'uscita) |

### 1.3 CALCIO — VARIANTE PUNTA (punta la favorita avanti di 2)

| # | regola | citazione | forza |
|---|---|---|---|
| P-S1 | Stessa selezione della classica, sulla squadra favorita | `PU/1 @48.2` «sempre all'inizio su la squadra che è favorita, come sappiamo da classica selezione» | E (le bande B-S1..S6 valgono anche qui) |
| P-E1 | Punteggi utili 2-0, 3-1, 3-0 per chi vince (due gol di scarto) | `PU/1 @36.2-65.2` | E |
| P-E2 | Si PUNTA la squadra che sta vincendo (1X2, lato blu); vince solo se quella squadra vince | `PU/2 @0.0-35.3` | E |
| P-E3 | Minuto ideale «intorno al 70°, 66, 67, 70°» | `PU/2 @35.3` | E |
| P-E4 | Quote «da l'1 e 0-3 … al 1.1» = 1,03-1,10 | `PU/2 @35.3` | E (numero storpiato ma leggibile) |
| P-E5 | **CONDIZIONE**: la vincente ha il controllo; guardo almeno 3-4 minuti DOPO il gol del 2-0; se dopo il raddoppio «si addormenta» non va bene | `PU/3 @0.2-62.3` | **E** |
| P-E6 | Stake: «inserendo proprio nella puntata quello che è il mio stake» | `PU/2 @35.3` | A (non dice se tutta la cassa) |
| P-U1 | PROFITTO: la vincente segna ancora → bel profitto (cashout) | `PU/5 @6.6` | E |
| P-U2 | PROFITTO: il terzo gol non arriva → «al 83' esco … ecco comunque sempre tutto valutabile» | `PU/5 @16.8-34.9` | E (83') / A («valutabile») |
| P-U3 | La situazione si ribalta (l'altra prende il controllo) → esco per prevenire l'accorciamento | `PU/5 @37.9-48.9` | E |
| P-U4 | PERDITA: qualsiasi gol subito (2-0 → 2-1, 3-1 → 3-2) → esco e accetto, «va rispettata rigorosamente»; «non è coperto il pareggio» | `PU/6 @0.1-40.5` | **E** |

### 1.4 TENNIS

| # | regola | citazione | forza |
|---|---|---|---|
| T-P1 | Non operare sul tennis se non si sa accettare la perdita (niente pareggio, più sbalzi) | `TE-INT/1 @21-67.9` | E (umano) |
| T-P2 | Non operare se non si sa uscire in manuale: il cashout «spesso sfalsa»; si può «prenotare» l'uscita (ordine a prezzo migliore) e magari viene abbinata | `TE-INT/2 @0.3-79.3` | E |
| T-P3 | Cassa iniziale ≈ 200 € (anche meno), crescere gradualmente | `TE-INT/3 @0.1-37.9` | E |
| T-S1 | Da evitare: FINALI (talvolta anche semifinali) | `TE-SEL/1 @8.2-36.8` | E (finali) / A (semifinali) |
| T-S2 | Da evitare: DOPPI; si lavora sul singolo | `TE-SEL/1 @43.7-56.1`; `TE/REGOLE 2 @41.5-60.3` | E («consiglio», «poi potete provare») |
| T-S3 | Da evitare: match «equilibratissimi in campo» (games 1-1, 2-1, 2-2, 3-3 …), soprattutto nel secondo set | `TE-SEL/1 @65.5-103.7` | E (criterio LIVE, non pre-partita) / A (nessun numero) |
| T-S4 | Da evitare: competizioni dove non si vede la partita, livello basso (es. «il 1200 contro il 1400»), spread troppo alto | `TE-SEL/1 @110.3-144.8` | E / A (soglie) |
| T-S5 | Parametri pre-partita «meno specifici»; evitare lo sfavorito «davvero troppo sfavorito» (perdita troppo alta se si ribalta); preferire almeno un leggero favorito | `TE-SEL/2 @0.2-107.7` | E (criterio) / A (nessuna soglia) |
| T-S6 | Orario: nessun orario fisso; notifica a fine primo set oppure sezione live dell'app | `TE-SEL/3` | E (umano) |
| T-E1 | Si sfrutta il secondo set («o il terzo in caso di grande slam») | `TE/1 @0.1` | E / A (lo Slam è poi sconsigliato: `TE/7 @192`) |
| T-E2 | Condizione utile: primo set vinto + 2 o 3 game di vantaggio nel secondo, «meglio soprattutto se all'inizio» del set; un set a zero da solo NON basta | `TE/1 @19.3-52.8` | E |
| T-E3 | Se chi vince è lo SFAVORITO: meglio 3 game di vantaggio | `TE/1 @52.8-82.8` | E |
| T-E4 | Punta chi vince OPPURE banca chi perde: indifferente | `TE/2 @11.3-38.3` | E |
| T-E5 | Momento ideale: 1 set a 0 e almeno 2 game nel secondo; **meglio se dopo i 2 game di vantaggio chi vince è al SERVIZIO** | `TE/2 @38.3-83.3` | E (preferenza) |
| T-E6 | Se chi vince fa punti soprattutto in risposta ed è scarso al servizio → rivaluto (anche in senso opposto) | `TE/2 @95.3-118.3` | E (discrezionale) |
| T-E7 | Quote: ~1,03 per la puntata, 18-34 per la bancata (le due vie equivalgono a back ≈1,03-1,06); il foglio del corso usa per la punta la scala 1,02-1,10 (§1.6) | `TE/2 @118.3-127.3`; `TENNIS/5. EXTRA/1. Tennis-Operazioni-Traccia.xlsx`, foglio «Feb», righe 6-8 | E (vedi 1.1-bis e 1.6) |
| T-E8 | Quota «ancora più favorevole» (più alta) → NON sparare tutto lo stake: DIMINUIRE lo stake; oltre 1,10-1,15 le perdite arrivano al 25% | `TE/2 @127.3-145.3`; `TE/6 @13.0-47.3` | E |
| T-E9 | CONDIZIONE: chi vince deve dare sicurezza nel suo gioco (un primo set risicato o game fortunati possono falsare); guardo dall'inizio del secondo set o almeno un game, al servizio e in risposta | `TE/3 @0.0-40.7` | **E** |
| T-U1 | PROFITTO 1: chi vince vince anche il game successivo (3-4 game di vantaggio) → se preferisco il tempo/meno rischio, ESCO | `TE/4 @11.0-52.9` | E (discrezionale fra U1 e U2) |
| T-U2 | PROFITTO 2: se mi dà tanta sicurezza e voglio dedicarci tempo, tengo fino alla FINE del match (profitto massimo) | `TE/4 @57.0-82.1` | E |
| T-U3 | PERDITA 1: perde il game successivo → posso già uscire se conservativo; valuto se l'ha perso al servizio o no e chi serve dopo | `TE/5 @10.0-68.3` | E (facoltativa) |
| T-U4 | PERDITA 2: perde anche il game dopo e **arriva il pareggio nel set** → «Qui esco, proprio tassativo … per forza» | `TE/5 @74.2-111.4` | **E** |
| T-U5 | Più ci si avvicina alla fine del set con situazione equilibrata, più oscillazioni e perdite maggiori | `TE/6 @92.8-106.3` | E (descrittiva) |
| T-U6 | Profitti fino al 9-10%; perdite 5-25% con quote alte | `TE/6 @6.6-47.3` | E (descrittiva) |
| T-U7 | INFORTUNIO: il ritiro fa perdere tutto lo stake anche da 5-0; se si avverte che il giocatore si sta infortunando, o se «chiamano un'assistenza medica», si ESCE comunque (come il rosso nel calcio, «forse molto peggio») | `TE/7 @26.8-186.4` | **E** |
| T-U8 | Evitare i grandi Slam maschili (al meglio dei 5: più lunghi, più infortuni muscolari) | `TE/7 @192.0-240.8` | E («cercare di evitare magari») |
| T-U9 | Operare con i profitti già fatti, aumentare il capitale poco a poco | `TE/7 @89.4-102.7` | E (gestione cassa) |

### 1.6 Materiale allegato al corso (i fogli Excel mostrati nei video) — letto in sola lettura

I video «Tenere traccia» (`EXT/1 @134-165`) e «Uscita manuale» (`EXT/2 @101-171`) mostrano due
fogli che fanno parte del corso. Li ho letti (zip/xml con la libreria standard, nessuna scrittura):

**`5. EXTRA\1. Operazioni.xlsx`, foglio «Lug», righe 6-8** (identica in
`TENNIS\5. EXTRA\1. Tennis-Operazioni-Traccia.xlsx`, foglio «Feb»), con cassa B3 = 200:

| QUOTA BANCA | fino 26 | 27 / 33 | 34+ | | QUOTA PUNTA | 1,02 / 1,04 | 1,05 | 1,06 | 1,07 / 1,10 |
|---|---|---|---|---|---|---|---|---|---|
| importo (formula) | `B3*4/100` = 8 | `B3*3/100` = 6 | `B3*2/100` = 4 | | importo (formula) | `B3` = 200 | `B3*80/100` = 160 | `B3*70/100` = 140 | `B3*50/100` = 100 |

Il video spiega che cosa sono: «i numeri che vedete qui sono il profitto massimo in base alla quota
… ed è anche l'importo che inseriamo se andiamo a bancare, se non vogliamo mettere direttamente
tutta la nostra responsabilità nella sezione rischio» (`EXT/1 @139.1-165.9`). Quindi il corso ha
una **regola di dimensionamento scritta**:
- **BANCA** (base, e il lay del tennis): bancata = 4% della cassa fino a quota 26, 3% fra 27 e 33,
  2% da 34 in su. Responsabilità risultante: a 20 → 76% della cassa, a 26 → 100%, a 30 → 87%, a 34
  → 66%. È la stessa «responsabilità ≈ cassa intera» di X2, espressa per fasce di quota. **Anche la
  tabella conferma che la quota d'ingresso della base è il prezzo di BANCA della perdente, in zona
  20-34+** (1.1-bis).
- **PUNTA** (tennis e variante punta): puntata = 100% della cassa a 1,02-1,04, 80% a 1,05, 70% a
  1,06, 50% a 1,07-1,10. È la regola T-E8 («quota più alta → diminuisco lo stake») scritta in numeri,
  e fissa la banda della punta a **1,02-1,10** (niente sotto 1,02, niente sopra 1,10).
- Commissione usata nei fogli: 4,5% (`Calcolatore.xlsx` E8; formula tennis `C12*95.5/100`).

**`5. EXTRA\2. Calcolatore.xlsx`**, foglio «Banca Punta»: quota banca 22, responsabilità 200 →
stake 9,52 (`C4/(C3-1)`), contropunta a 70 → 2,99 (`(C6*C3)/E3`): è l'esempio del video `EXT/2`
e conferma di nuovo una bancata a quota 22.

**L'esempio «banchi a 1,28 con 100 € → profitto ≈ 28 €» della SPEC (`SPEC_STRATEGIA_S.md:40`) NON
compare in nessuna trascrizione né in nessun foglio** (ricerca `grep` di «28», «1,2», «1.2» su tutti
i .txt: nessun esempio del genere). Viene dal riassunto, non dal corso.

### 1.5 Varianti o regole dei video che NON esistono come variante nel codice

Nessuna variante nuova: i video contengono esattamente quattro strategie operative (Base, Esatto,
Punta, Tennis). Esistono però regole senza controparte nel codice: flessibilità pre-match (B-S4/S5),
liste di campionati (B-S7/S8), classifica (B-S3), selezione esatto (E-S3/S4, spenta), uscita per
infortunio (T-U7), preferenza «al servizio» (T-E5), stake ridotto a quota alta (T-E8), match
equilibrati LIVE (T-S3), livello/spread del torneo (T-S4). Dettaglio nel confronto (Fase 2).

---

## FASE 2 — CONFRONTO REGOLA PER REGOLA CON IL CODICE

Esiti: **FEDELE** · **DIVERGENTE** · **ASSENTE** (regola dei video senza codice) ·
**SOLO CODICE** (nel codice, non nei video) · **DECISA** (divergenza coperta da decisione scritta
dell'utente: citata, non riproposta) · **n/a** (regola umana/descrittiva, non automatizzabile).
Percorsi: `engine.py`, `exits.py`, `bot_service.py` = `Betfair/safe_strategy/…`. Parametri =
default del codice; il DB di oggi NON è stato letto (divieto): ultima fotografia 16/09 in
`FASE0_VERITA_DI_PARTENZA_2026-09-16.md:500-532` (`variants=["tennis"]`, `laySize 2`,
`backSize 3`, `tennis_exit_approval=true`).

### 2.1 Trasversali

| regola | codice | esito | soldi / decisione |
|---|---|---|---|
| X2 responsabilità = cassa intera; tabella del corso per fasce di quota (1.6) | stake FISSO per strategia `engine.py:249-262` (`laySize/backSize 2.0`) | DECISA | 13/09 + 14/09 (`SPEC_STRATEGIA_S.md:174-178`, `CERTIFICAZIONE_2026-09-13.md` §6.3). Non riproposta. Solo un fatto nuovo: il corso ha una tabella esplicita (1.6) che la decisione non aveva davanti |
| X3/B-U5 rischio ~10-12% | nessun controllo (conseguenza dello stake) | n/a | descrittiva |
| X6 mercato 1X2 | `engine.py:998-1008`, `1195-1203` `MATCH_ODDS` | FEDELE | |
| X7 spread piccolo | gate `max_spread_ratio 1.6` `bot_service.py:188`, `6081` | FEDELE (lo quantifica) | restringe |
| X8 vedere la partita | nessun equivalente (il bot non «vede»); il surrogato è `pressure_index`, spento | ASSENTE | è il presupposto di B-E6/E-E8/P-E5/T-E9 (sotto) |
| X9 orario | non pertinente per un bot | n/a | |
| X11/X12 uscita a mano, cashout che sfasa | chiusura al best opposto, controllata e riconciliata (banco T3, K, CP) | FEDELE nello spirito | il bot non usa il cashout di Betfair: il problema X12 non lo tocca |
| X13 uscita d'emergenza su altro book | nessuna | n/a | umana |
| X15 commissione 4,5% | `commission_pct 5` `bot_service.py:129` | DIVERGENTE minore | P&L stimato 0,5 punti più prudente; non cambia gli ingressi |
| — rientro a ogni punteggio nuovo | chiave segnale = evento+variante+lato+PUNTEGGIO `engine.py:1424-1426`, `1492-1497` | SOLO CODICE | nei video un'operazione per partita (implicito, `STR/10`); dopo un'uscita all'1-1 il bot può ribancare al 2-1. Nessuna decisione trovata |
| — decisione a modello sulle uscite in profitto/tempo | `bot_service.py:4199-4242` → `exits.py:426-535` | SOLO CODICE | vedi B-U2 |
| — gate liquidità, FOK, tetti di rischio, feed fresco, un solo lato esatto | `bot_service.py:6019`, `6081`, `6104-6114`; `risk.py` | SOLO CODICE (restringono) | nessun rischio in più |
| — motori non-Strategia-S (opportunity, anomaly, combos, tennis_opportunity) | solo PROPOSTE dal 17-18/09 | SOLO CODICE | non piazzano da soli (audit 24/09 §5) |

### 2.2 CALCIO — BASE

| regola (video) | codice | esito | impatto sui soldi · decisione |
|---|---|---|---|
| B-S1 favorita pre 1,40-1,80 | `engine.py:925-956`, param `:192-196` | FEDELE | |
| B-S2 sfavorita pre 4-8 | idem | FEDELE | |
| B-S3 conferma della classifica | nessun dato di classifica nel contesto (`FootballMatchCtx` `engine.py:494-524`) | ASSENTE | entra anche su prima-contro-ultima (a quote in banda) o su squadre appaiate. Nessuna decisione |
| B-S4/S5/S6 flessibilità 1,80-2,20 / 3-8 con classifica | bande strette fisse | FEDELE alla regola base (la flessibilità è FACOLTATIVA: `EXT/3 @61.2` «sulla base del vostro grado di rischio») | è la leva che moltiplicherebbe le partite attivabili (oggi la BASE passa ~1 partita su 8: `PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md:571-574`). Q6 |
| B-S7 competizioni da evitare (femminile, amichevoli, coppe/fasi finali, Bundesliga, Eredivisie e loro B, campionati imprevedibili) | nessun filtro; il dato c'è (`FootballMatchCtx.competition` `engine.py:518`) ma `evaluate_base/esatto/punta` non lo leggono (zero occorrenze di `competition` in `engine.py:880-1210`) | **ASSENTE** | entra in Bundesliga/2.Bundesliga/Eredivisie, dove l'autore dice che la propensione al gol «per noi non è il massimo» (`SEL/2 @72.5-98.5`), e su amichevoli e femminile («imprevedibilità elevatissima»). **Nessuna decisione.** Q4 |
| B-S8 campionati migliori | idem | ASSENTE (lista positiva, non un veto) | |
| B-E1 secondo tempo | `minuteMin 55` | FEDELE | |
| B-E2 punteggi 1-0/2-1/2-0 per la favorita | `engine.py:910-923` (`lead == fav`) | FEDELE | |
| B-E3 banca la perdente, 1X2 | `engine.py:983-1008` | FEDELE | |
| B-E4 minuto 60' (55-62 «dipende») | soglia `>= 55` senza tetto `engine.py:849-858` | DECISA | 13/09 + 14/09 (`SPEC:8-13`). Non riproposta. Conseguenza non discussa: nessuna guardia contro un ingresso DOPO l'80' (`grep exit_minute` in `engine.py`/`bot_service.py` = 0 righe). Q8 |
| **B-E5 quota d'ingresso = BANCA della perdente 20-34** (1.1-bis, 1.6) | il filtro è il BACK live della FAVORITA 1,20-1,34 (`favLive` `engine.py:957-968`, «Lettura A»); sul prezzo di banca solo «disponibile» (`dogLay` `engine.py:983-992`) | **DIVERGENTE** | La «Lettura A» è decisa il 14/09 (`SPEC:52-61`, `:167-168`) ma **su un numero che il video smentisce** (1,20-1,34 invece di 20-34) e su un esempio («1,28 → 28 €») che nel corso non esiste (1.6). Effetto (STIMA, non misurata): i due filtri si sovrappongono in parte (1-0 a inizio secondo tempo) ma non coincidono: la Lettura A **lascia entrare banche a 10-19** (tipico del 2-1 con favorita a 1,25-1,34) che il video esclude come più rischiose («più è bassa la quota più è alto il rischio», `STR/2 @111`), ed **esclude banche a 20-34 con favorita sotto 1,20** (partita più chiusa) che il video ammette. Chi rischia: la responsabilità del lay (stake × (q−1)) sulle banche basse, dove il pareggio è più probabile. La «quota di banca libera» (`SPEC:169-173`) è una decisione distinta che NON ripropongo; ma il suo presupposto scritto («la banda 4–8 … profilo descrittivo»; `CERT_13 §6.2` «il manuale … banca a ~4,5») viene dallo stesso riassunto sbagliato. **Q1** |
| **B-E6 condizione: la vincente ha il controllo, altrimenti è «vietato» entrare** | `requireControl: False` `engine.py:189`; il check esiste (`control_check` `engine.py:793-815`) ma non è chiamato | **DIVERGENTE (spenta)** | è la regola che il video ripete di più (`STR/3`, `STR/9`, `STR/10 @29.7`). Senza, il bot entra anche mentre la perdente «martella». Spenta per causa-dato (copertura IPS non misurata, `CERT_13 §6.5`); la SPEC chiede riconferma (`SPEC:181-183`): **non trovata**. Q2 |
| B-E7 guardare 4-5 minuti prima di bancare | solo «punteggio stabile ≥30 s» `engine.py:875-882`, `scoreConfirmSec 30` | **DIVERGENTE** | la BASE può entrare 30 s dopo il gol dell'1-0 (la PUNTA invece aspetta 3' `engine.py:1180-1190`). Nessuna decisione. Q2 |
| B-E8 rosso alla vincente PRIMA dell'ingresso → partita evitata | `noRedFav` `engine.py:970-981`, solo se `ctx.red` c'è | FEDELE col dato; senza dato il check non esiste e si entra | minore; dipende dalla copertura del dato cartellini |
| B-E9 dimensione = responsabilità | stake fisso | DECISA | vedi X2 |
| B-U1 la vincente segna → esco (o aspetto qualche minuto) | `exits.py:953-954` kind `profit`, dal modello: con P&L bloccato ≥ 0 esce (`exits.py:477-478`) | FEDELE (una delle due opzioni del video) | |
| **B-U2 80-83' esco «anche se la squadra tiene il controllo»** | `exits.py:962-964` produce `time`; poi `_model_gate` `bot_service.py:4199-4242` → `decide_time_exit`: con P&L bloccato < 0 e P(perdita) ≤ `hold_max_risk 0.02` (`exits.py:115`, `:491-492`) **tiene fino al settlement**; fra 2% e 10% tiene se il bloccato è sotto l'EV del tenere | **DIVERGENTE** | trasforma una chiusura a costo noto (centesimi) in esposizione piena (responsabilità intera, es. 48 € su un lay da 2 € a 25) fino al 90'+. Decisa il 13/09 (`CERT_13 §6.4`), **non riconfermata** contro la SPEC come la SPEC stessa pretende (`SPEC:181-183`). Il video: «non vado a rischiare negli ultimi minuti» (`STR/5 @91.1-95.9`). Q3 |
| B-U3 controllo perso → esco in pari/piccola perdita | `_controllo_perso` `exits.py:925-946`, `base_control_exit: False` `exits.py:78` | DIVERGENTE (spenta) | stessa causa di B-E6; Q2 |
| B-U4 pareggio → esco, «per forza» | `exits.py:951-952`, kind `loss` fuori dal modello (`PROFIT_KINDS` `exits.py:128`) | FEDELE | |
| B-U6 aspetta 20-60 s | `loss_settle_delay_s 30` `exits.py:72`, `_after` `exits.py:905-909` | FEDELE | |
| B-U7 rosso alla vincente → esco nel 90%+ | `exits.py:955-956`, `red_card_fav_exit True` | FEDELE (100%, più prudente) | |
| B-U8 rosso alla perdente neutro | nessun ramo | FEDELE | |
| B-U9 non uscire subito; uscire prima se «non mi piace» | nessuna uscita discrezionale | n/a | coperta in parte da B-U3 se acceso |
| B-U10 ingresso 2-0, la perdente segna (2-1) | nessuna uscita (`fav > dog`) | FEDELE al silenzio del video | ambiguo nel video (Q9) |

### 2.3 CALCIO — RISULTATO ESATTO

| regola | codice | esito | impatto · decisione |
|---|---|---|---|
| E-S1 quote/classifica solo «relativamente» | nessuna banda pre-partita in `evaluate_esatto` `engine.py:1012-1099` | FEDELE | |
| E-S3/E-S4 scontri diretti + gol subiti | `selection_check` `engine.py:818-846`, `requireSelection: False` `engine.py:219`, soglie 0,12 / 1,37 `:223-227` | DIVERGENTE (spenta) | implementata su ordine 16/09, accensione e soglie **pendenti** (`HANDOFF_2026-09-16_SERA.md:160`). Il video non dà numeri. Il video guarda la difesa della squadra NON bancata «e anche» quella da bancare (`RE-SEL/1 @128-166`); il codice solo l'avversaria della bancata (`engine.py:835-840`). Q7 |
| E-E2/E-E4 punteggi, bancata con ≤ 1 gol | `engine.py:1036-1054`, `maxGoalsLaySide 1` | FEDELE | |
| E-E3 «Altro risultato Casa/Ospite» | `engine.py:1055-1099`, prezzo = solo lay | FEDELE | regex dello scanner solo inglese (`engine.py:545-546`) |
| E-E5 si può bancare anche la favorita | nessun vincolo | FEDELE | |
| E-E6 minuto 48-50' | soglia `>= 48` | DECISA | 14/09. Conseguenza: ingressi al 62'/64' osservati (`CERT_13 §6.1`) |
| E-E7 quota 30-70 | `engine.py:1068-1079` | FEDELE | |
| **E-E8 la bancata NON deve avere il controllo; partita non aggressiva** | `requireControl: False` `engine.py:202` | **DIVERGENTE (spenta)** | a 0-0/1-0/1-1 passano entrambi i lati: con il controllo spento il lato lo sceglie l'ordinamento delle chiavi, non il campo (audit 24/09 §3.2). Il video sceglie il lato proprio col controllo. Q2 |
| E-E9 guardare 3-4' dal 45' | `scoreConfirmSec 30` | DIVERGENTE | Q2 |
| E-U1 profitto: «comanda il tempo» | nessuna uscita su gol dell'avversaria | FEDELE | |
| E-U2 esco al 70-75' | `esatto_exit_minute 72` `exits.py:70`, poi `_model_gate` | DIVERGENTE (come B-U2) | con stake 2 € a quota 30-70 la responsabilità tenuta fino al 90' è 58-138 €. Q3 |
| E-U3 la bancata segna → esco | `exits.py:970-971` kind `loss`, +30 s | FEDELE | |
| — un solo lato per partita | `bot_service.py:6019` | SOLO CODICE (coerente col singolare del video) | |

### 2.4 CALCIO — VARIANTE PUNTA

| regola | codice | esito | impatto · decisione |
|---|---|---|---|
| **P-S1 «classica selezione» della favorita (bande pre-match)** | `evaluate_punta` `engine.py:1102-1204` controlla solo che il leader sia la favorita (`leadFav` `:1133-1148`), **non** le bande 1,40-1,80 / 4-8 | **DIVERGENTE** | punta a 1,03-1,10 anche favorite pre-partita a 2,5 (partita quasi alla pari). Impatto moderato (serve comunque +2 al 66'). Nessuna decisione. Q10 |
| P-E1 punteggi 2-0/3-1/3-0 | `engine.py:1118-1130` | FEDELE | |
| P-E2 punta la vincente, 1X2 | `engine.py:1192-1203` | FEDELE | |
| P-E3 minuto ~66-70 | soglia `>= 66` | DECISA | 14/09 |
| P-E4 quota 1,03-1,10 | `engine.py:1167-1178` | FEDELE | il foglio del corso (1.6) scala lo stake dentro la banda (100% → 50%): stake fisso DECISO |
| **P-E5 controllo + 3-4' dopo il 2-0, non deve «addormentarsi»** | attesa `minMinutesAfterGoal 3` `engine.py:236`, `:1180-1190`; controllo `requireControl: False` `engine.py:230` | attesa FEDELE, controllo **DIVERGENTE (spento)** | Q2 |
| P-U1 segna ancora → cashout | `exits.py:982-983` | FEDELE | |
| P-U2 esco all'83' | `punta_exit_minute 83` + `_model_gate` | DIVERGENTE (come B-U2) | Q3 |
| **P-U3 la situazione si ribalta → esco per prevenire** | nessun ramo in `_decide_punta` `exits.py:978-987` (la BASE almeno ha il ramo, spento) | **ASSENTE** | Q2 |
| P-U4 qualsiasi gol subito → esco | `exits.py:980-981`, +30 s | FEDELE (il +30 s è l'assestamento del mercato sospeso) | minore |
| — nessun rosso a chi si punta all'ingresso | `engine.py:1150-1164` | SOLO CODICE (restringe) | |

### 2.5 TENNIS

| regola | codice | esito | impatto · decisione |
|---|---|---|---|
| T-P2 uscire in manuale; «prenotare» l'uscita a prezzo migliore | chiusura al best opposto | FEDELE nello spirito / ASSENTE la «prenotazione» | minore |
| T-P3 cassa ~200 € | stake fisso | DECISA | |
| T-S1 evitare le finali | nessun codice | ASSENTE | causa-dato: Betfair non pubblica il turno (`RISCONTRO_TENNIS_2026-09-14.md:21`); **decisione pendente**. Q11 |
| T-S2 evitare i doppi | `excludeDoubles` `engine.py:1232-1245` | FEDELE | euristica «/» nel nome |
| T-S3 evitare i match «equilibratissimi in campo» | nessun codice | **ASSENTE** | il riscontro 14/09 lo dichiarava «conforme per costruzione» (banda quota). Il video lo dice di un criterio LIVE (game che si alternano nel secondo set): il bot non guarda come si è arrivati ai 2 game. Q12 |
| T-S4 tornei di livello basso / spread alto | solo gate spread 1,6 | FEDELE in parte | |
| T-S5 niente sfavoriti estremi, preferire un leggero favorito | `TennisMatchCtx` `engine.py:528-541` senza quote pre-partita | **ASSENTE** | uno sfavorito pre-partita avanti 1 set + 2 game entra come un favorito. Q12 |
| T-E1/T-E2 1 set + 2-3 game nel secondo | `engine.py:1263-1329` (`setsLeadMin 1`, `gamesLeadMin 2`, `setsPlayedMax 1`) | FEDELE | nessun tetto a 3 game: ammesso («almeno due game», `TE/2 @47.3`) |
| T-E2 «meglio se all'inizio» del set | nessuna preferenza (entra anche a 5-3) | DIVERGENTE minore | a fine set oscillazioni e perdite maggiori (`TE/6 @92.8-106.3`) |
| **T-E3 se vince lo sfavorito servono 3 game** | nessun codice (manca il dato pre-partita) | **ASSENTE** | Q12 |
| T-E4 punta o banca indifferente | solo BACK `engine.py:1367` | DECISA | CERT_13 §6.6. Le due vie sono davvero equivalenti (18-34 ↔ 1,03-1,06): l'«incompatibilità» scritta in CERT_13 §6.6 cade |
| T-E5 meglio se il leader è al SERVIZIO | nessun dato di servizio nel contesto | ASSENTE | preferenza, non veto |
| **T-E7 quota ~1,03 (video) / 1,02-1,10 (foglio del corso)** | `backMin 1.01`, `backMax 1.10` `engine.py:241-242` | DIVERGENTE solo sotto 1,02 | l'audit del 24/09 contava 1,01-1,02 fuori strategia: **correzione**, 1,02 è nel foglio del corso (con stake pieno). Resta fuori 1,01-1,019: guadagno massimo < 2% dello stake contro lo stake intero, e sotto 1,03 il take profit è spento (`exits.py:1005-1011`) → si va a fine partita. Nessuna decisione trovata. Q5 |
| T-E8 quota più alta → stake più basso (foglio: 100% → 50%) | stake fisso | DECISA (stake fisso) | informativo: a 1,10 il bot rischia quanto a 1,02 |
| **T-E9 il leader deve dare sicurezza; guardare almeno un game** | solo `scoreConfirmSec 15` `engine.py:252` | **ASSENTE** | Q2 (famiglia del «controllo») |
| T-U1 vince il game successivo → esco se preferisco | `exits.py:1004-1012` + minimo 0,01 € bloccati `bot_service.py:4232-4238` | FEDELE (una delle due opzioni) | scatta a QUALSIASI game vinto dopo l'ingresso, non solo al successivo: minore |
| T-U2 oppure tengo fino alla fine | sotto 1,03 si tiene (`exits.py:1009-1011`) | FEDELE (l'altra opzione, scelta per quota) | |
| T-U3 perde il game successivo → uscita facoltativa | `tennis_exit_on_lost_game False` `exits.py:98` | DECISA | 17/09 (`CRONOSTORIA.md:289`) |
| T-U4 due game persi + pareggio nel set → «tassativo» | `exits.py:995-1003` (AND con `set_lead_lost` `exits.py:852-858`), kind `mandatory` fuori dal modello | FEDELE nella logica | col cancelletto acceso aspetta una firma: DECISA 14/09 (`bot_service.py:141-150`, `3690-3700`) |
| **T-U7 infortunio / assistenza medica → esci subito** | nessun codice (`grep -i` ritir/infortun/retire/medical in `engine.py`, `exits.py`: 0 righe; in `bot_service.py` solo il rischio di ritiro dentro il modello di probabilità `:4131-4147`) | **ASSENTE** | l'unico modo di perdere TUTTO lo stake nel tennis (`TE/7 @26.8-86.2`). Il feed non porta il medical timeout: non automatizzabile senza una fonte nuova. Mitigazione presente: bo5 escluso. Q13 |
| T-U8 evitare gli Slam maschili | `excludeBestOf5` `engine.py:1311-1319` | FEDELE | senza nome competizione → n/d → nessun ingresso |

---

## FASE 3 — VERDETTO PER VARIANTE E DOMANDE ALL'UTENTE

### 3.1 Verdetto

| variante | verdetto | perché |
|---|---|---|
| **BASE** | **PARZIALE — la più lontana dai video** | minuto, punteggi, bande pre-partita e uscite in perdita fedeli; ma il **filtro di prezzo guarda la selezione sbagliata** (favorita 1,20-1,34 invece della banca 20-34), **controllo** e **osservazione di 4-5'** spenti, **nessun filtro di campionato**, e l'uscita dell'80-83' può non uscire |
| **RISULTATO ESATTO** | **PARZIALE** | numeri fedeli (48', ≤1 gol, 30-70, 70-75'), ma il lato si sceglie senza il controllo (la regola che nel video decide QUALE squadra bancare), selezione H2H spenta, uscita a tempo filtrata dal modello |
| **PUNTA** | **PARZIALE** | numeri fedeli (2 gol, 66', 1,03-1,10, 3' dopo il gol, uscita a ogni gol subito); mancano le bande della «classica selezione», il controllo, l'uscita «si ribalta»; l'83' passa dal modello |
| **TENNIS** | **PARZIALE — la più vicina ai video** | ingresso (1 set + 2 game, bo3, singolare) e uscita tassativa fedeli; banda quasi fedele (fuori solo 1,01); mancano sfavorito/3 game, equilibrio in campo, finali, infortunio, servizio; l'uscita tassativa aspetta la firma (decisione dell'utente) |

Nessuna variante è fedele «in ogni sua parte». La causa comune: **la Strategia S è
discrezionale** (chi comanda la partita, come gioca il leader), e il bot oggi entra solo su
prezzo, punteggio e minuto.

### 3.2 Domande all'utente, in ordine di impatto sui soldi (nessuna applicata)

**Q1 — BASE: la quota d'ingresso dei video è la BANCA della perdente 20-34, non la favorita
1,20-1,34** (fatto nuovo, 1.1-bis e 1.6).
- A) lasciare la Lettura A; B) sostituirla con «banca della perdente 20-34»; C) entrambe.
- *Raccomandazione:* **prima misurare, poi B.** I referti del banco hanno già, per ogni segnale
  BASE, i valori di `favLive` e `dogLay` nei check (`engine.py:957-992`): contare su quante aperture
  i due filtri divergono è una lettura, non un replay nuovo. Da trader: il prezzo di banca misura il
  rischio vero del lay (P(la perdente vince) ≈ 1/quota); la quota della favorita contiene il
  pareggio e non lo misura. Il video dice che sotto 20 il rischio sale. Cosa cambierebbe: meno
  ingressi al 2-1 a banche basse, qualche ingresso in più a partita chiusa; il controllo B9 del
  banco (`certificazione.py:421-432`) andrebbe riscritto perché oggi vieta proprio un filtro sul
  prezzo di banca, e B8 (`:397-418`) certifica la Lettura A.

**Q2 — «Controllo del gioco» + osservazione prima dell'ingresso (BASE, ESATTO, PUNTA; «sicurezza
del gioco» nel tennis).** Il video: entrare senza guardare è «assolutamente vietato» (`STR/3 @0.3-17.5`).
- A) spenta (oggi); B) accesa con l'indice attuale (`pressure.py`, non calibrato); C) misurare la
  copertura (il bot la registra: attività `copertura_controllo_gioco`, `bot_service.py:5803`) e
  accenderla dove il dato c'è, e intanto aggiungere l'attesa di osservazione (BASE 4-5', ESATTO 3-4'
  dal 45') che non richiede dati nuovi; D) BASE/ESATTO/PUNTA come PROPOSTE all'utente finché il
  controllo non c'è.
- *Raccomandazione:* **C, e D finché C non è pronta.** Il lay della perdente mentre attacca è
  proprio l'ingresso che produce il pareggio; il corso lo toglie con gli occhi. Un bot senza occhi
  deve o averli (dato) o chiedere.

**Q3 — Uscita a tempo «esci comunque» (80-83' base, 70-75' esatto, 83' punta).** Decisa 13/09
(`CERT_13 §6.4`), mai riconfermata (`SPEC:181-183`); il video è netto.
- A) decisione a modello (oggi); B) uscita incondizionata al minuto; C) incondizionata con un tetto
  di costo.
- *Raccomandazione:* **B.** Il modello dei gol residui è meno affidabile proprio nei minuti finali
  («saltano gli schemi»); uscire costa centesimi su 2 € di stake, tenere espone 38-138 € fino al
  90'+. Il banco oggi certifica la divergenza (T4 `certificazione.py:1076-1087`; B14/E8/P9 guardano
  solo che esista una decisione): andrebbe cambiato insieme.

**Q4 — Filtro campionati (calcio).** Assente.
- A) nessun filtro (oggi); B) veto sulla lista del video: femminile, amichevoli, coppe (almeno fasi
  finali), Bundesliga, 2. Bundesliga, Eredivisie, Eerste Divisie, campionati «imprevedibili» (lista
  da compilare); C) B + lista positiva dei «migliori».
- *Raccomandazione:* **B** (il dato `competition` c'è già nel contesto). Regola esplicita del corso,
  costo quasi nullo. C restringerebbe troppo un bot che trova già poche partite.

**Q5 — Tennis, quota minima 1,01 contro 1,02 del foglio del corso.**
- A) 1,01 (oggi); B) 1,02 (foglio); C) 1,03 (numero detto nel video).
- *Raccomandazione:* **B.** Nota: il banco tennis T1 legge la banda dai parametri (è uno specchio,
  `certificazione_tennis.py:240-266`): oggi uno spostamento di `backMin` non farebbe nessun rosso.

**Q6 — Flessibilità pre-partita BASE (favorita fino a 2,20, sfavorita da 3, con classifica).**
- *Raccomandazione:* **bande strette per ora** (regola «fase iniziale»). Il video lega la tolleranza
  alla valutazione del campo e della classifica, che il bot non fa; allargare senza controllo alza
  la perdita tipica fino al 20% (`EXT/3 @283`). Da riaprire dopo Q2.

**Q7 — ESATTO, selezione H2H/difesa (spenta, pendente dal 16/09).** Soglie 0,12 / 1,37 dei
delegati; il video guarda anche la difesa della squadra da bancare.
- *Raccomandazione:* accenderla solo dopo aver misurato la copertura dell'atlante sulle partite in cui
  l'ESATTO entra davvero (oggi 1 coppia su 39 registrazioni, `engine.py:211-215`), altrimenti spegne
  la variante.

**Q8 — Nessuna guardia «ingresso prima del minuto d'uscita».** Conseguenza non discussa della
soglia aperta (decisa). *Raccomandazione:* guardia `minuto < minuto di uscita` per ogni variante:
non tocca la decisione «soglia», toglie solo il caso assurdo (ingresso all'85' e uscita subito).

**Q9 — Rientro dopo un'uscita (chiave per punteggio)** e caso ambiguo B-U10 (ingresso 2-0, 2-1
della perdente). *Raccomandazione:* un solo ingresso per variante e partita; su B-U10 tenere (oggi),
che è la lettura letterale del video.

**Q10 — PUNTA senza bande pre-partita.** *Raccomandazione:* stesse bande della BASE («classica
selezione»); impatto basso perché la PUNTA non ha mai dato segnali nel corpus
(`PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md:572-573`).

**Q11 — Tennis finali** (pendente dal 14/09). *Raccomandazione:* euristica «ultima partita rimasta
del torneo» come avviso, non come veto, finché non c'è una fonte del turno.

**Q12 — Tennis: sfavorito (3 game), sfavoriti estremi, equilibrio in campo, inizio set, servizio.**
*Raccomandazione:* portare nel contesto tennis la quota pre-partita congelata (come `pre_ko` del
calcio) e con essa: sfavorito pre-partita → 3 game; oltre una soglia → escluso. Il resto dopo.

**Q13 — Tennis infortunio / medical timeout.** Non automatizzabile col feed di oggi.
*Raccomandazione:* accettare il rischio dichiarato (oggi) e dirlo in scheda; difesa: bo5 escluso e
stake piccolo.

Non riproposti (già decisi): stake fisso 2 €, quota di banca libera, minuti come soglia,
cancelletto chiusure tennis, uscita al singolo game perso spenta, solo back nel tennis. Q1 tocca la
«Lettura A», che non è fra i punti chiusi elencati, e segnala il presupposto cambiato della «quota
di banca libera» senza riaprirla.

---

## FASE 4 — IL BANCO: COSA COPRE E COSA MANCHEREBBE

Controlli letti in `Betfair/safe_strategy/certificazione.py` (calcio, costanti SPEC scritte a mano
`:64-86`) e `certificazione_tennis.py`. **Non ho rilanciato replay** (sola lettura; ordine del 24/09
«un replay per bot in sequenza»). Ultimi referti (23/09, c3h) secondo l'audit del 24/09 §7: la
maggior parte delle uscite calcio **non è stata sollecitata** (x0) il 23/09; l'ultima volta il 16/09.

| regola dei video | controllo del banco | copre? | scenario che mancherebbe (non costruito) |
|---|---|---|---|
| B-E5 banca 20-34 | B8 certifica la Lettura A (`:397-418`); B9 **vieta** un filtro sul prezzo di banca (`:421-432`) | NO, certifica il contrario | segnale BASE con favorita in 1,20-1,34 e banca < 20 (2-1), e viceversa favorita < 1,20 con banca 20-34 |
| B-E6/E-E8/P-E5 controllo | B10/E6/P6 ⊘ con `requireControl` spento (`:434-448`) | NO (mai un caso) | la perdente che preme al 60'; lato ESATTO scelto per controllo a 0-0 |
| B-E7/E-E9 osservazione 4-5' / 3-4' | nessuno | NO | gol dell'1-0 al 58', ingresso al 58'30" |
| B-S7 campionati | nessuno | NO | registrazione di Bundesliga/amichevole/femminile nel corpus |
| B-S3 classifica | nessuno | NO | (manca il dato) |
| B-S1/S2 bande pre | B6/B7 | SÌ | |
| B-E2/E-E4/P-E1 punteggi | B5/E3/E4/P3 | SÌ | |
| minuti d'ingresso | B4/E2/P2 (soglia) | SÌ (sulla decisione) | ingresso dopo il minuto d'uscita (Q8) |
| B-U2/E-U2/P-U2 «esci comunque» | B14/E8/P9 guardano che esista una decisione, non che la posizione chiuda (`:515-531`); T4 pretende il trattenimento (`:1076-1087`) | NO, certifica la divergenza | 80' con bloccato < 0 e P(perdita) ≤ 2%: la posizione arriva al 90' aperta |
| B-U4/E-U3/P-U4 perdita | B12/E9/P7 | SÌ (ultimo esercizio 16/09) | |
| B-U6 20-60 s | B16 | SÌ | |
| B-U7/U8 rosso | B15 | SÌ | rosso con dato cartellini assente (B-E8) |
| B-U3/P-U3 controllo perso | B17 ⊘; per la PUNTA nessun controllo | NO | |
| E-S3/S4 H2H | E10 (scenario `selezione-aggiuntiva`) | SÌ quando acceso | difesa della squadra bancata |
| P-S1 bande della punta | nessuno (P1 guarda solo leader = favorita) | NO | favorita pre-partita a 2,5 avanti 2-0 al 66' |
| rientro per punteggio | J7 guarda solo due ordini vivi per lo stesso segnale | NO | 1-0 → uscita all'1-1 → 2-1 al 75': secondo ingresso |
| T-E1/E2 1 set + 2 game | T2 (`certificazione_tennis.py:269-297`) | SÌ | |
| T-E7 quota | T1 legge la banda **dai parametri** (`:240-266`): specchio, non confronto con la SPEC | NO come fedeltà | `backMin` spostato senza nessun rosso |
| T-S2/T-U8 doppi, bo5 | T4 | SÌ | |
| T-S1 finali | T10 ⊘ (dato assente) | NO | |
| T-S3/S5/T-E3 equilibrio, sfavorito | nessuno | NO | sfavorito pre-partita avanti 1 set + 2 game |
| T-U1/U2 take profit / tenere | T5/T6 | SÌ | |
| T-U4 uscita tassativa | T7, T7-APPROVAZIONE | SÌ (con la decisione del cancelletto) | |
| T-U7 infortunio | nessuno | NO | ritiro a posizione aperta |
| T-E5 servizio | nessuno | NO | (manca il dato) |

---

## FASE 5 — NON VERIFICATO E PERCHÉ

1. **DB di oggi** (parametri effettivi, `variants`, `strategy_modes`, `tennis_exit_approval`,
   copertura `copertura_controllo_gioco`): divieto di lettura. Uso la fotografia del 16/09.
2. **La misura di Q1** (quante aperture BASE avevano banca < 20 o favorita < 1,20): serve leggere
   referti o DB; l'impatto in §2.2 è una STIMA ragionata, non un numero.
3. **Replay**: nessuno rilanciato. La copertura del banco è letta dal codice dei controlli e
   dall'audit del 24/09.
4. **Parole incerte dell'audio** (modello `small`): punteggi dell'ESATTO («1-0 a 0, 1-1 a 1»,
   `RE/1 @14.0`), letti 0-0/1-0/1-1/2-1 per coerenza col vincolo «≤ 1 gol»; banda della PUNTA
   («da l'1 e 0-3 … al 1.1», `PU/2 @35.3`), letta 1,03-1,10 e confermata dal foglio; tennis «tra 1 e
   0-3», letta 1,03. Il numero di Q1 («dal 20 al 34») NON è incerto: 4 passaggi e il foglio.
5. **Regole senza numeri** (serve una scelta dell'utente per automatizzarle): «controllo»,
   «troppi» 2-2/3-2, difesa «solida», classifica «attaccata/distante», match «equilibratissimo»,
   sfavorito «davvero troppo sfavorito», «qualche minuto» dopo il gol (B-U1), livello del torneo.
6. **Quale squadra bancare nell'ESATTO a 1-0/1-1**: il video la sceglie col controllo e
   nell'esempio dice «bancheremo per forza la squadra … perché è a uno» (`RE/6 @13.2`) senza
   punteggio completo detto: ambiguo.
7. **Esempi a schermo** (`STR/10`, `RE/6`): numeri visibili solo nel video, non nella trascrizione.
8. `SPEC_STRATEGIA_S.md` resta NON versionato (letto dal checkout principale).
9. Worktree: codice Safe e banco identici al checkout principale (confronto `diff
   --strip-trailing-cr` su `Betfair/safe_strategy/*.py` e `Betfair/stream/backtest/*.py`: nessuna
   differenza; `risk.py` differisce solo nei fine riga).
