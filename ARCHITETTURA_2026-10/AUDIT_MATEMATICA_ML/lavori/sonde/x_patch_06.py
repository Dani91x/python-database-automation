import io
p = "06_PIANO_MIGLIORAMENTI.md"
s = io.open(p, encoding="utf-8").read()
reps = [
 ("Toglie i falsi positivi (oggi il 69% dei modelli over_1_5 passa senza skill)",
  "Toglie i falsi positivi (sonda H sul gate di produzione: un modello che predice solo il tasso base 0,74 passa; nel registry 694/1.009 modelli over_1_5 passano con BSS reale sul tasso base ~ +0,04, dato di B non riprodotto da H)"),
 ("copre le prime giornate; ensemble tattico+principale misurato meglio dei singoli (RPS 0,2111 vs 0,2135, n=528)",
  "copre le prime giornate (oggi scoperte). Attenzione: su n=528 il tattico da solo (RPS 0,2166) NON e' risultato migliore del principale calibrato (0,2135); la media dei due 0,2111 e' una misura in-sample, non un test: da confermare col cruscotto (n.3)"),
 ("| rende misurabile la qualita' per lega | 1-2 giorni | - |",
  "| rende misurabile la qualita' per lega | 1-2 giorni | % di leghe/target con log-loss sotto le quote e sotto la climatologia (oggi non calcolabile) |"),
 ("| stima 0,001-0,004 log-loss | +30% tempo di training |",
  "| stima (non misurata) 0,001-0,004 log-loss | +30% tempo di training |"),
 ("| guasti visti in giorni, non mesi | basso | - |",
  "| guasti visti in giorni, non mesi | basso | giorni tra un peggioramento di ECE > 0,02 e l'avviso |"),
 ("| riproducibilita' | basso | - |",
  "| riproducibilita' | basso | % modelli del registry con hash dataset e versione feature (oggi 0) |"),
]
for a, b in reps:
    assert s.count(a) == 1, a[:50]
    s = s.replace(a, b)
add = """| 26 | **Una sola regola per commissione e tick**: arrotondamento della commissione per mercato unico (Safe, Mike, banco, paper tennis, cashout_value) e scala/pareggio dei tick unica (flumine) ; `commission_rate` del backtest obbligatorio | B9, B10, B13, B35 | ore | scarto Safe/Mike/banco su 3.000 mercati sintetici = 0 | basso; tocca il P&L stimato dei bot, non le decisioni | execution.py, mike/engine.py, banco, order_exec.py, run_backtest.py |
| 27 | **Persistere AH, risultato esatto e O0.5/O4.5** dalla matrice dei punteggi gia' calcolata | nuovi mercati senza costo di stima; chiude il buco `over_4_5` letto e mai prodotto | basso | log-loss dei nuovi mercati nel cruscotto | basso | today_predictions_backfill.py |
| 28 | **Foglio Quant Fund: niente ricalcolo retroattivo del P&L** con la commissione attuale (salvare l'aliquota per slot) | storico P&L stabile (B38) | ore | P&L storico invariato dopo un cambio di aliquota | nullo | money_management.py:1357-1373 |
"""
anchor = "\n## Ordine consigliato"
assert s.count(anchor) == 1
# aggiunge le righe in coda alla tabella della fascia 3
idx = s.index(anchor)
s = s[:idx].rstrip("\n") + "\n" + add + s[idx:]
io.open(p, "w", encoding="utf-8").write(s)
print("ok 06")
