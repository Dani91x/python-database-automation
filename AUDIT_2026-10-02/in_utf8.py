"""Riscrive in UTF-8 i referti che `powershell.exe` 5.1 ha salvato in UTF-16
(redirezione `>`). Il contenuto non cambia. Uso: python in_utf8.py FILE..."""
import io
import sys

for p in sys.argv[1:]:
    grezzo = open(p, "rb").read()
    if grezzo[:2] in (b"\xff\xfe", b"\xfe\xff"):
        testo = grezzo.decode("utf-16")
        io.open(p, "w", encoding="utf-8", newline="").write(testo)
        print("convertito", p)
    else:
        print("gia' utf-8", p)
