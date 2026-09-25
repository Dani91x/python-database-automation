"""Ref dell'annullo col prefisso dell'ATTORE (Safe tennis sul canale). Lanciato una volta."""
import io

p = "Betfair/safe_strategy/porta_ordini.py"
s = io.open(p, encoding="utf-8").read()
old = '''def ref_annullo(bet_id: Any, size_reduction: Optional[float] = None) -> str:
    """Il ref di un ``cancel``: deterministico dal bet_id (e dalla riduzione,
    se parziale). Un secondo annullo identico e' un doppione per il runner."""
    ref = "safe-c%s" % str(bet_id).strip()
'''
new = '''def ref_annullo(bet_id: Any, size_reduction: Optional[float] = None,
                attore: str = ATTORE_CALCIO) -> str:
    """Il ref di un ``cancel``: deterministico dal bet_id (e dalla riduzione,
    se parziale). Un secondo annullo identico e' un doppione per il runner.

    25/09 (F8): il prefisso e' quello dell'ATTORE che lo manda, come per il
    place (F1): il motore pretende ``f"{attore}-"`` e Safe tennis e' l'attore
    ``safe_tennis``. Prima ogni annullo di Safe tennis sul canale sarebbe stato
    rifiutato (``safe-c...`` non inizia per ``safe_tennis-``). Calcio invariato
    (``safe-c<bet_id>``)."""
    ref = "%s-c%s" % (str(attore or ATTORE_CALCIO), str(bet_id).strip())
'''
assert s.count(old) == 1
s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)

p = "Betfair/safe_strategy/execution.py"
s = io.open(p, encoding="utf-8").read()
old = '''            ref=PO.ref_annullo(bet_id, size_reduction), attore=porta.attore,
'''
new = '''            ref=PO.ref_annullo(bet_id, size_reduction, attore=porta.attore),
            attore=porta.attore,
'''
assert s.count(old) == 1
s = s.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
