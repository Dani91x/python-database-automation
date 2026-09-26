"""md5 del corpo $$...$$ delle funzioni nei file SQL (confronto con pg_proc.prosrc del DB vero)."""
import re, hashlib, sys
for f in sys.argv[1:]:
    t = open(f, encoding='utf-8', newline='').read()
    for m in re.finditer(r"create or replace function public\.(\w+)\(.*?\$\$(.*?)\$\$", t, re.S | re.I):
        b = m.group(2)
        lf = b.replace('\r\n', '\n'); crlf = lf.replace('\n', '\r\n')
        print(f, m.group(1), len(lf), hashlib.md5(lf.encode()).hexdigest(), len(crlf), hashlib.md5(crlf.encode()).hexdigest())
