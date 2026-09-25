"""Modifica minima di motore_ordini.py (esecutore per sport). Lanciato una volta."""
import ast
import io

p = "Betfair/stream/motore_ordini.py"
src = io.open(p, encoding="utf-8").read()
lines = src.split("\n")
t = ast.parse(src)
targets = {"avvia", "ferma", "_ciclo", "_gestisci", "_controlla", "_riduzione_verificata",
           "_esegui", "avanza_submin", "_abbandona_submin", "_chiudi_submin", "_servi_order",
           "inviato"}
ins = []
for n in t.body:
    if isinstance(n, ast.ClassDef) and n.name == "MotoreOrdini":
        for f in n.body:
            if isinstance(f, ast.FunctionDef) and f.name in targets:
                first = f.body[0]
                if (isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant)
                        and isinstance(first.value.value, str)):
                    after = first.end_lineno
                else:
                    after = f.body[0].lineno - 1
                ins.append(after)
assert len(ins) == len(targets), ins
for after in sorted(ins, reverse=True):
    lines.insert(after, "        LOW = self._low  # 25/09: l'esecutore dello sport (calcio: live_order_worker)")
src = "\n".join(lines)
old = '''                 aggancio: Optional[Any] = None) -> None:
        self.sport = sport
'''
new = '''                 aggancio: Optional[Any] = None,
                 esecutore: Optional[Any] = None) -> None:
        self.sport = sport
        # 25/09 (tennis, F8): l'ESECUTORE dello sport, cioe' il modulo che espone
        # le funzioni del worker (``_dispatch``, guardie, client per modalita',
        # contesto sul thread). None = ``live_order_worker`` del calcio, come
        # prima. Il runner tennis passa ``tennis_live.esecutore_tennis`` (il
        # ``_dispatch`` vero di ``tennis_live_order_worker``).
        self._low = esecutore if esecutore is not None else LOW
'''
assert src.count(old) == 1
src = src.replace(old, new)
old = '''        self._blocco_modo = blocco_modo or LOW._blocco_apertura_modo
        self._eta_settings = eta_settings or LOW.eta_settings_s
'''
new = '''        self._blocco_modo = blocco_modo or self._low._blocco_apertura_modo
        self._eta_settings = eta_settings or self._low.eta_settings_s
'''
assert src.count(old) == 1
src = src.replace(old, new)
old = '''        cor = payload.get("client_order_ref")
        if not isinstance(cor, str) or not cor.startswith("awlq") or len(cor) < 14:
            return
        with self._lock_seq:
            info = self._rif_interni.get(cor[:14])
'''
new = '''        cor = payload.get("client_order_ref")
        # 25/09: il prefisso del ref interno e' quello dell'esecutore
        # (calcio ``awlq``, tennis ``awtq``), sempre seguito da 10 cifre
        pref = self._low._cust_ref("")
        if not isinstance(cor, str) or not cor.startswith(pref) or len(cor) < len(pref) + 10:
            return
        with self._lock_seq:
            info = self._rif_interni.get(cor[:len(pref) + 10])
'''
assert src.count(old) == 1
src = src.replace(old, new)
io.open(p, "w", encoding="utf-8", newline="\n").write(src)
print("ok")
