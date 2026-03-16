# SPECIFICHE: Foglio "Trading Setup"
> Da implementare nella prossima sessione
> NON CANCELLARE

---

## Obiettivo

Un foglio Google Sheets dedicato all'operatività di trading manuale.
NON sostituisce il foglio Segnali esistente — lo affianca.
Il trader scansiona questo foglio pre-partita e identifica immediatamente
quali game watchare e con quale setup entrare.

---

## Logica di base

Il trader ha 2 macro-setup:

### SETUP A — Over Gol (sequenza fino a 3 tentativi)
1. Entry 1 pre-match: OV 0.5 HT
2. Se HT 0-0 → Entry 2: OV 1.5 a ~2.00 OPPURE OV 0.5 FT a 1.40-1.50
3. Se ancora 0-0 → Entry 3: ultimo tentativo sui gol (max 3 per partita)

**Condizione di ingresso**: partita strutturalmente da gol, confermata da più segnali.

### SETUP B — LAY Sfavorita (quota 3.00-5.00)
- Favorita a quota 1.50-2.00
- Si esce al gol della favorita OPPURE a fine HT se partita 0-0

**Condizione di ingresso**: favorita netta, sfavorita prezzata tra 3 e 5.

---

## Struttura del foglio

### Colonne (una riga per partita)

```
COL A  — Data/Ora
COL B  — Partita (Home vs Away)
COL C  — Lega
COL D  — [SETUP A] Punteggio Over Gol  ← COMPOSITO (vedi sotto)
COL E  — [SETUP A] OV 0.5 HT %        ← 1H O0.5 AI (modello o proxy)
COL F  — [SETUP A] OV 1.5 FT %        ← O1.5 % AI
COL G  — [SETUP A] OV 2.5 FT %        ← O2.5 % AI
COL H  — [SETUP A] OV 0.5 FT %        ← O0.5 % AI
COL I  — [SETUP A] Primo Gol < 30' %  ← target_first_goal_before_30 (DA AGGIUNGERE)
COL J  — [SETUP A] Goal 2° Tempo %    ← Goal 2H AI
COL K  — [SETUP B] Punteggio LAY      ← COMPOSITO (vedi sotto)
COL L  — [SETUP B] % Favorita         ← H % AI o A % AI (quella più alta)
COL M  — [SETUP B] Quota Favorita     ← da Betfair live
COL N  — [SETUP B] % Sfavorita        ← quella più bassa tra H/A
COL O  — [SETUP B] Quota Sfavorita    ← da Betfair live (deve essere 3.00-5.00)
COL P  — Consiglio Finale             ← testo generato (vedi sotto)
COL Q  — Note Modello                 ← warning BSS, proxy attivo, ecc.
```

---

## Punteggio Composito SETUP A (COL D)

Scala 0-5 stelle (o semaforo Verde/Giallo/Rosso).

```
+1 punto se OV 0.5 HT % > 55%
+1 punto se OV 1.5 % > 60%
+1 punto se OV 2.5 % > 55%
+1 punto se Primo Gol < 30' % > 50%
+1 punto se Goal 2° Tempo % > 60%

5/5 = Verde scuro  → Ingresso pieno, tutti i segnali allineati
4/5 = Verde        → Ingresso normale
3/5 = Giallo       → Ingresso ridotto, solo Entry 1
2/5 = Arancio      → Watch only, non entrare
0-1/5 = Rosso      → Salta
```

---

## Punteggio Composito SETUP B (COL K)

```
Condizioni NECESSARIE (senza queste non si mostra):
  - % Favorita (H o A) > 60%
  - Quota Sfavorita Betfair tra 3.00 e 5.00

Punteggio aggiuntivo:
+1 se % Favorita > 65%
+1 se % Favorita > 70%
+1 se Quota Sfavorita tra 3.50 e 4.50 (fascia ottimale)
+1 se OV 0.5 FT % < 70% (partita non necessariamente da gol = sfavorita regge 0-0)

3-4 = Verde  → LAY valido
2   = Giallo → Watch
```

---

## Colonna P — Consiglio Finale (testo)

Esempi di output:

```
"🟢 SETUP A — OV 0.5 HT confermato (4/5). Piano B: OV 1.5 se 0-0 HT."
"🟢 SETUP B — LAY [Team X] a ~3.80. Esci al gol favorita o fine HT."
"🟡 SETUP A parziale — solo OV 2.5 (3/5). Attesa conferma in-play."
"🔴 Salta — segnali insufficienti per entrambi i setup."
"⚠️ 1H O0.5 da proxy (no modello dedicato) — usare con cautela."
```

---

## Filtri automatici da applicare

Il foglio mostra SOLO le partite che rispettano almeno una condizione:
- Setup A score ≥ 3/5 → mostrata
- Setup B condizioni necessarie soddisfatte → mostrata
- Altrimenti la riga non appare (o appare grigiata)

Questo riduce il rumore: invece di 50 partite, il trader vede 10-15 game
già pre-selezionati con il contesto operativo pronto.

---

## Dati necessari dal backend

Tutti già presenti o calcolabili da predict_fixture.py:

| Campo | Fonte | Stato |
|-------|-------|-------|
| OV 0.5 HT % | target_ht_over_0_5 oppure proxy (1-P(HT Draw)) | ✅ Già in report |
| OV 1.5 % | target_over_1_5 | ✅ Già in report |
| OV 2.5 % | target_over_2_5 | ✅ Già in report |
| OV 0.5 % | target_over_0_5 | ✅ Già in report |
| Goal 2H % | target_goal_in_2h | ✅ Già in report (parziale) |
| Primo Gol < 30' % | target_first_goal_before_30 | ⚠️ Da aggiungere alla scrittura su Sheets |
| % Favorita / Sfavorita | target_1x2 H/A | ✅ Già in report |
| Quote Betfair live | API Betfair | ✅ Già fetchate |

**Unica aggiunta al backend**: includere `target_first_goal_before_30`
nella scrittura del report (già calcolato da predict_fixture.py, solo
non scritto su Sheets).

---

## Implementazione tecnica

### File da modificare
1. `Betfair/betfair_report_manager.py` — aggiungere:
   - Nuovo worksheet "Trading Setup"
   - Lettura `target_first_goal_before_30` dal payload AI
   - Calcolo punteggi compositi Setup A e Setup B
   - Formattazione condizionale (semaforo colori)
   - Filtro: solo righe con score ≥ soglia

### Note implementative
- Il foglio si popola nello stesso run del foglio Segnali (no script separato)
- I dati sono già tutti disponibili nel payload `ai_preds` e `analysis`
- Le quote Betfair live (favorita/sfavorita) sono già in `odds_cache`
- Formattazione condizionale su COL D e COL K:
  - 5 = sfondo verde scuro
  - 4 = sfondo verde
  - 3 = sfondo giallo
  - ≤2 = sfondo grigio/nascosto

---

## Checklist pre-implementazione

```
[ ] Verificare che target_first_goal_before_30 sia nel payload ai_preds
    (controllare predict_fixture.py — già in TARGETS_TO_PREDICT o da aggiungere)
[ ] Confermare con utente la soglia quote LAY (3.00-5.00 confermata)
[ ] Confermare con utente soglia favorita (> 60% o > 65%?)
[ ] Decidere: foglio separato o tab aggiuntivo nel Google Sheet esistente?
[ ] Test su 1 giornata di partite per validare punteggi compositi
```

---

*Fine documento — v1.0 del 2026-03-16*
