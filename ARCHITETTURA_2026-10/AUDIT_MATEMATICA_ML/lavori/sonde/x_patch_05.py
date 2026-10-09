# Patch delle consegne del coordinatore (solo file dentro ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML)
import io
p = "05_ERRORI_DI_PROGETTAZIONE.md"
s = io.open(p, encoding="utf-8").read()
reps = [
 ("raggiungibile con dati reali, convenzione discutibile.\n",
  "raggiungibile con dati reali, convenzione discutibile. Gradi intermedi (MEDIO-ALTO, BASSO-MEDIO) = reperto a cavallo\n"
  "tra due livelli: il motivo e' scritto nella riga. La gravita' di questo file prevale su quella dei file 00-04 e dei\n"
  "file di lavoro (vedi la tabella di concordanza degli identificativi in fondo).\n"),
 ("**Il modello ML servito non ha valore informativo misurabile**: su Over 2.5 e BTTS e' peggio del tasso base; su 1X2 batte la climatologia ma perde dalle quote;",
  "**Il modello ML servito non ha valore informativo misurabile oltre il mercato**: su Over 2.5 e BTTS non batte il tasso base (log-loss leggermente peggiore, +0,0019 e +0,0072, differenza non significativa); su 1X2 batte la climatologia ma perde dalle quote in modo significativo;"),
 ("| Mercati ML attivati o spenti per caso; stake della traccia ML assegnato per caso |",
  "| Mercati ML attivati o spenti per caso; stake della traccia ML assegnato per caso. ALTO perche' riguarda la stima su cui il gate decide per TUTTI i mercati; MA1 (stessa funzione) e' MEDIO-ALTO perche' riguarda solo la baseline dei binari sbilanciati |"),
 ("| B5 | Tre versioni \"calibrate\" dello stesso numero con regole diverse; due tabelle di calibrazione |",
  "| B5 | (BASSO-MEDIO) Tre versioni \"calibrate\" dello stesso numero con regole diverse; due tabelle di calibrazione |"),
 ("| B8 | Kelly del foglio: minimo 1,00 dopo il tetto (scatta solo con bankroll < 50) |",
  "| B8 | Kelly del foglio: minimo 1,00 forzato DOPO il tetto: ogni stake Kelly sotto 1,00 sale a 1,00 (sopra il Kelly sempre, es. 0,45 -> 1,00 con bankroll 1.000; sopra il tetto del 2% solo con bankroll < 50) |"),
]
for a, b in reps:
    assert s.count(a) == 1, a[:60]
    s = s.replace(a, b)
extra = """| B33 | Post-calibrazione ML in try/except: in caso di errore le probabilita' restano non post-calibrate senza traccia | Ai Engine/ai_engine/predict_fixture.py:895-917 | F (04 tab.1) |
| B34 | Colonne `commission` con unita' diverse (aliquota in trades, importo in tennis_live_orders) | E2_lacune.md n.11 | E2-11 |
| B35 | Cash-out di Mike: gambe `archived` escluse dalla base della commissione; `cashout_value` non arrotonda la commissione mentre il settlement si' | Betfair/mike/engine.py:776, :1101 | E2-12, 03 |
| B36 | xhedge: P&L lordo, un solo passo di copertura | Betfair/stream/trading/xhedge.py:156-215 | E2-14 |
| B37 | market_intelligence: edge composito in punti di probabilita' con termine xG euristico (xG*abs(rho)*0,10) e de-vig proporzionale | market_intelligence/edge_scorer.py:159-190, 316-380 | D32 |
| B38 | Foglio Quant Fund: a ogni `resolve_results` il P&L di TUTTI gli slot vinti viene riscritto con la commissione ATTUALE (ricalcolo retroattivo silenzioso se l'aliquota cambia) | Betfair/money_management.py:1357-1373 [C] | X |
| B39 | Regole .it non gestite nel codice secondo la documentazione developer Betfair: tetto di vincita potenziale 10.000 EUR e rifiuto di back+lay nello stesso placeOrders (NON VERIFICATO se la regola sia ancora in vigore) | 03 par. 4; R_stato_arte.md | R, 03 |

## Concordanza degli identificativi
| Prefisso | Dove | Corrisponde a |
|---|---|---|
| A1-A3, MA1-MA2, M1-M18, B1-B39 | questo file (05) | elenco unico per gravita' |
| P-R1..P-R14 | 01_CATENA_POISSON.md | A-R* di lavori/A_poisson.md (P-R1=A-R1, P-R2=A-R2, P-R3=A-R3, P-R4=A-R4, P-R5=A-R5, P-R6=M par.3, P-R7=A-R6, P-R8=A-R7, P-R9=F-1, P-R10=A-R8, P-R11=A-R10/R11, P-R12=E2 tau, P-R13=F-8, P-R14=A-R9/F-4) |
| ML-R1..ML-R15 | 02_CATENA_ML.md | B-R* di lavori/B_ml.md (ML-R1=B-R1, R2=B-R2+M, R3=B-R3, R4=B-R4, R5=M, R6=B-R5, R7=B-R6, R8=B-R7, R9=E2-3, R10=B-R8, R11=B-R9, R12=B-R10, R13=B-R11, R14=B-R14/F-7, R15=B-R13) |
| FL-1..FL-18 | 04_FLUSSO_FINO_AL_CONSUMATORE.md | F-* di lavori/F_flusso.md (FL-n = F-n per n<=10) + D/E2/V2 (FL-11=D-R3, FL-12=D-R4, FL-13=D-R8, FL-14=E2-1, FL-15=E2-2, FL-16=C-R10/V2, FL-17=E2-4, FL-18=D-R10) |
| M1..M11 (proposte) in 01, P1..P10 in 02 | proposte, non reperti | numerate di nuovo in 06 (1-25) |
"""
anchor = "\n## Nota sul processo dell'audit"
assert s.count(anchor) == 1
s = s.replace(anchor, "\n" + extra + anchor)
io.open(p, "w", encoding="utf-8").write(s)
print("ok 05")
