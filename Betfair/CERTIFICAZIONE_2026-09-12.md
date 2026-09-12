# CERTIFICAZIONE CAPILLARE — OMEGA · SAFE STRATEGY · MIKE
### 12/09/2026 · backend, frontend, SQL, feed condiviso · dati REALI

Documento di esito. Non sostituisce le costituzioni: dice **che cosa è stato
verificato, che cosa era sbagliato e che cosa resta aperto**.

Metodo: 16 revisioni indipendenti a perimetri disgiunti (lettura integrale dei
file, non a campione), più quattro collaudi sui **dati veri** del DB di
produzione in sola lettura — reportistica, chiusura delle operazioni, P&L
mostrato, dati in tempo reale — più una revisione del codice sull'intero diff.
Ogni difetto corretto ha un test che fallisce prima e passa dopo.

---

## 1. I difetti che costavano soldi (corretti)

### 1.1 Probabilità dedotte da prezzi che non esistono
È lo schema del falso segnale visto in produzione (Daegu-Yongin: Over 4.5 a
16,50 segnalato con «modello 90,1%» ed EV +13, perché l'Over 7.5 era **offerto a
1,11 con 6 € di liquidità**). Lo stesso schema è stato trovato in altri tre
punti, tutti money-critical:

| Dove | Cosa succedeva | Misura |
|---|---|---|
| `safe_strategy/anomaly.py` scala Under/Over | la quota di riferimento era presa per verità | sul feed reale avrebbe segnalato Over 3.5 @4,70 con «modello 89,3%» |
| `omega_model.py` λ impliciti dal mercato | una **civetta da 2 €** spostava i gol attesi | λ da (0,562; 0,440) a (0,380; 0,312): P(3-1) **3,4× sbagliata** |
| `safe_strategy/opportunity.py` recupero | dal 95' il modello dichiarava **99,8% piatto** fino al 120' | 85' → 72,2% · 94' → 95,9% · 95'-120' → 99,8% |
| `safe_strategy/calibration.py` | la calibrazione estrapolava oltre i campioni osservati | fino a **+1,9 punti** dove non esiste un dato |

**Regola applicata ovunque**: una probabilità nata da un prezzo vale solo se quel
prezzo ha liquidità (≥ 2 €) ed è plausibile; e non può superare la stima del
modello quando è disponibile. Dove il modello è cieco (recupero), si ripiega
sulla quota di mercato, mai su una certezza inventata.

### 1.2 Numeri sbagliati sotto gli occhi del trader

| Difetto | Effetto reale misurato |
|---|---|
| «Se chiudo ora» calcolato a precisione infinita invece che con la formula del servizio | prometteva **+2,37 €** dove il servizio incassa **+1,77 €** (34% in più) |
| La tabella di Safe leggeva solo la gamba d'apertura | una posizione chiusa a **−10,27 €** appariva **+2,00 €** |
| Dettaglio giornata con definizioni diverse dal calendario | 12/09 Safe: cella **−0,77 €**, dettaglio **+1,90 €** |
| «P&L bloccato» lordo in Omega/Safe, netto in Mike | sovrastima del **5%**, stessa etichetta per due grandezze |
| Liability della giornata con righe mai arrivate a mercato | Mike 11/09: **+65,82 €** di rischio inesistente |
| Fill parziale mostrato come «eseguito» | richiesta da **5,00 €** eseguita per **0,43 €**, badge verde |
| Liability negativa nell'anteprima manuale | «Liability aperta ≈ **−5,26 €**» |

### 1.3 Sicurezze mancanti
- **Mike**: «Chiudi a mercato» chiudeva la partita con **soldi veri a un solo
  click**, mentre il cash out accanto chiedeva due conferme. Ora ha lo stesso
  dialogo, e con l'età del feed ignota i bottoni che spendono sono spenti.
- **Mike**: un mercato annullato produceva un **P&L inventato**; una partita
  poteva risultare regolata **con le righe non scritte**.
- **Mike engine**: copertura dimensionata sullo stake lordo invece che sul
  rischio netto; cash out che poteva entrare in un ciclo infinito di ordini
  annullati e riemessi; un prezzo non valido congelava la partita.
- **Safe**: il piazzamento manuale non controllava la freschezza del feed, a
  differenza dell'automatico.
- **Feed condiviso**: con lo scanner vivo veniva servita come fresca **qualunque**
  riga; se il feed di una singola partita si bloccava, i bot decidevano su un
  punteggio di ore prima. Ora c'è un tetto assoluto, esteso anche a Mike.
- **Motore probabilistico condiviso**: la correzione Dixon-Coles era applicata
  anche fuori dallo 0-0, falsando il pareggio di **2,5 punti percentuali** —
  sopra la soglia di segnale — e facendo vedere numeri diversi ai tre bot. Ora
  le griglie coincidono a 1e-9.
- **Paper ≠ live**: il paper riempiva ordini parzialmente dove il live li
  annulla per intero (FILL_OR_KILL), e riempiva senza controparte sul book. Ora
  il paper uccide come il live: i suoi numeri possono valere come prova.

---

## 2. Il P&L mostrato è vero

Ricalcolato **da zero**, senza riusare il codice del progetto, sulle 234
operazioni reali (`omega_trades` 80, `safe_strategy_trades` 53, `mike_trades` 80),
applicando la commissione una sola volta sul netto vincente per mercato.

| Grandezza | UI | RPC | Python | Ricalcolo indipendente |
|---|---|---|---|---|
| Omega totale / oggi | −19,46 / +0,00 | idem | idem | idem |
| Safe totale / oggi | +10,98 / +1,90 | idem | idem | idem |
| Mike totale / oggi | +15,67 / +13,51 | idem | idem | idem |

Verificato inoltre: le posizioni ancora aperte **non entrano mai** nel P&L; le
chiusure sono sempre legate alla loro apertura; gli annullamenti valgono zero;
il totale storico coincide con la somma delle giornate; il P&L per riga è
**netto**, con l'aliquota della singola operazione.

Strumento rieseguibile (sola lettura):
`python -m Betfair.tools.verifica_pnl_2026_09_12`

---

## 3. Chiarezza per il trader

Ogni numero a schermo ha ora **una sola definizione e una sola fonte dichiarata**.

- **Mike** mostrava cinque conteggi diversi della stessa cosa. I numeri erano
  giusti ma senza nome: 18 operazioni = 14 posizioni aperte + 4 cicli chiusi, e
  quei 4 cicli valgono esattamente i +13,51 € della giornata. Ora ogni conteggio
  dichiara cosa conta, e le fasi dicono in italiano cosa sta facendo il bot.
- **Safe** dichiarava «feed: nessun dato» mentre Omega e Mike, sullo stesso feed,
  lo davano vivo: leggeva la salute da una fonte che risponde solo a sessione
  autenticata. Ora le tre pagine mostrano gli stessi numeri.
- **Omega** offriva nella scheda Missione partite di tre giorni prima già finite,
  e mostrava tre «target» diversi. La cache eventi ora si aggiorna da sola.
- Nessuna etichetta inglese, nessuna chiave tecnica, nessuno zero affermativo
  prima di avere i dati: dove un dato manca si scrive che manca.

---

## 4. Numeri

| | Prima | Dopo |
|---|---|---|
| Test Python (omega+safe+mike+stream) | 1255 + 1099 | **2589 verdi** |
| Test frontend | 705 | **1870 verdi** |
| Certificazione sui dati reali | 26 controlli | **202 controlli** |
| File toccati | — | 122 (+8551 / −1131) |

Compilazione TypeScript pulita nelle aree toccate; la UI è stata ricostruita.

---

## 5. Cosa resta aperto (onestamente)

1. **Nessun servizio pubblica l'età delle quote per singolo mercato.** La UI oggi
   dichiara «non verificabile» dove non lo sa, ma il trader non può datare con
   precisione il prezzo su cui opera. Serve `odds_age_s` per opportunità e per
   linea.
2. **Il «rischio zero» delle combinazioni non è dimostrabile come dichiarato**:
   vale solo con tutte le gambe abbinate e **senza annullamenti parziali** su
   combinazioni multi-mercato. Da riscrivere nella costituzione di Safe.
3. **La commissione si netta per posizione, non per mercato**: con due posizioni
   sullo stesso mercato l'errore è di circa 0,10 €, sempre a sfavore del numero
   mostrato.
4. **Il modello di Safe non ha edge dimostrato** (backtest −18,6%): le correzioni
   rendono le probabilità più oneste, non redditizie. Il backtest va rifatto ora
   che la calibrazione non estrapola e il recupero non produce più segnali.
5. **Tennis mai validato** su serie storiche: tenerlo spento.
6. **Live bloccato** per tutte e tre le sezioni: restano i gate già dichiarati
   (certificazione della liquidità lato back, giorni di paper sul codice nuovo,
   riconciliazione live mai provata sul campo, ≥ 40 partite paper per Mike).
7. **Migrazioni SQL non applicate**: `omega_models_v6.sql` (ultima dell'ordine in
   `migrations/APPLY_ORDER_2026-09-11.md`). Le quattro dell'11/09 risultano
   applicate.

---

## 6. Stato operativo

App desktop e quattro servizi **riavviati** il 12/09 alle 18:0x con il codice di
oggi: erano fermi dalle 10:57 (app chiusa), quindi le correzioni non erano
attive e il paper non stava girando. Feed di nuovo in tempo reale.

Per rivedere ciò che vede il trader:
```
cd frontend && npx vitest run --config vitest.cert.config.ts \
    src/certification/zz_dump.cert.test.tsx
```
