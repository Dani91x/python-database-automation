"""Ripara il mojibake (UTF-8 letto come cp1252 e risalvato in UTF-8) di un file
sorgente, riga per riga, e toglie il BOM. Stampa ogni riga cambiata (prima/dopo).

Uso:  python AUDIT_2026-10-02/ripara_mojibake.py <file> [--scrivi]
Senza --scrivi non tocca nulla (prova a secco).
Regola: si ricodifica SOLO una sequenza di caratteri cp1252/latin-1 che, ritradotta
in byte, forma UTF-8 valido; tutto il resto della riga resta identico.
I fine riga del file si conservano (si divide su '\n', il '\r' resta dov'e').
"""
import re
import sys

# caratteri che il cp1252 produce per i byte 0x80-0xFF (piu' i C1 non definiti,
# rimasti come U+0081, U+008D, U+008F, U+0090, U+009D)
CP1252_ALTI = ''.join(
    bytes([b]).decode('cp1252') for b in range(0x80, 0x100)
    if b not in (0x81, 0x8D, 0x8F, 0x90, 0x9D)
) + '\u0081\u008d\u008f\u0090\u009d'
RUN = re.compile('[' + re.escape(CP1252_ALTI) + ']{2,}')


def a_byte(ch: str) -> int:
    try:
        return ch.encode('cp1252')[0]
    except UnicodeEncodeError:
        o = ord(ch)
        if o < 0x100:
            return o
        raise


def ripara(seg: str) -> str:
    try:
        return bytes(a_byte(c) for c in seg).decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return seg


def main() -> int:
    path = sys.argv[1]
    scrivi = '--scrivi' in sys.argv
    raw = open(path, 'rb').read()
    bom = raw.startswith(b'\xef\xbb\xbf')
    righe = raw.decode('utf-8-sig').split('\n')
    cambiate = 0
    for i, r in enumerate(righe):
        nuova = RUN.sub(lambda m: ripara(m.group(0)), r)
        if nuova != r:
            cambiate += 1
            print(f'{i + 1}:\n  - {r.strip()}\n  + {nuova.strip()}')
            righe[i] = nuova
    print(f'BOM: {"si, tolto" if bom else "no"}; righe cambiate: {cambiate}')
    if scrivi:
        open(path, 'wb').write('\n'.join(righe).encode('utf-8'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
