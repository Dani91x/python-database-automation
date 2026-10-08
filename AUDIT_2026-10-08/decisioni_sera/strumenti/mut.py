# mutazione: mut.py FILE VECCHIO NUOVO (con escape \n \r interpretati)
import sys, codecs
p = sys.argv[1]
a = codecs.decode(sys.argv[2], "unicode_escape").encode("latin-1")
c = codecs.decode(sys.argv[3], "unicode_escape").encode("latin-1")
b = open(p, "rb").read()
n = b.count(a)
if n != 1:
    sys.exit("MUTAZIONE NON APPLICABILE (%d occorrenze): %r" % (n, a[:80]))
open(p, "wb").write(b.replace(a, c))
print("mutazione applicata")
