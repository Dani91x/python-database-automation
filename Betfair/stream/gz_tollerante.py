"""gz_tollerante.py - lettura TOLLERANTE dei file .jsonl.gz delle registrazioni (M-3).

Un file gzip scritto da un processo morto (kill, crash, spegnimento brusco) ha
la coda tronca; un file a cui un altro processo ha accodato un membro DOPO un
flusso tronco e' illeggibile per ``gzip.open`` (``zlib.error: invalid block
type`` o ``EOFError``) a partire dal punto rotto, e ``gzip.open`` butta anche
quello che avrebbe potuto leggere. Qui:

  * si decomprime a BLOCCHI (``zlib.decompressobj(wbits=31)``), tenendo
    l'output gia' ottenuto anche se il blocco dopo e' rotto;
  * a fine membro si riparte dai byte che restano (file a piu' membri);
  * su un membro rotto (``zlib.error``) o senza coda si cerca il prossimo
    inizio di membro gzip (``\\x1f\\x8b\\x08``) DOPO l'inizio del membro rotto
    e si riprende da li';
  * fra due membri si forza un a capo, cosi' una riga mozzata non si incolla
    alla prima riga del membro dopo.

Ritorna le righe (bytes, senza a capo) e un resoconto: membri letti, membri
corrotti, coda tronca. Mai solleva per un file rovinato (solleva solo se il file
non si puo' aprire: lo dice il chiamante).

Solo libreria standard. ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import zlib
from typing import Dict, Iterator, List, Tuple

MAGIA = b"\x1f\x8b\x08"
BLOCCO = 1 << 16


def _membro(dati: bytes, inizio: int, fine: int) -> Tuple[List[bytes], bool, int]:
    """Decomprime UN membro da ``inizio`` usando al piu' i byte fino a ``fine``.
    Ritorna (output, membro intero?, posizione dopo il membro)."""
    d = zlib.decompressobj(wbits=31)
    i = inizio
    uscita: List[bytes] = []
    try:
        while i < fine and not d.eof:
            blocco = dati[i:min(i + BLOCCO, fine)]
            i += len(blocco)
            pezzo = d.decompress(blocco)
            if pezzo:
                uscita.append(pezzo)
    except zlib.error:
        return uscita, False, i
    if d.eof:
        return uscita, True, i - len(d.unused_data)
    return uscita, False, i


def _decomprimi(dati: bytes, resoconto: Dict[str, int]) -> Iterator[bytes]:
    """Genera pezzi di output decompresso, membro dopo membro.

    Un membro che si rompe (``zlib.error``) o che finisce senza la sua coda
    (processo morto, oppure un membro nuovo accodato DOPO un flusso tronco) e'
    un GUASTO. Attenzione: zlib legge volentieri i byte del membro accodato come
    seguito di quello tronco e ne tira fuori testo plausibile ma FALSO. Per
    questo il membro guasto si ridecomprime usando SOLO i byte fino al primo
    membro intero che lo segue (o fino alla fine del file): cosi' se ne tiene
    tutto il vero e niente di inventato. Gli inizi di membro "per caso" (i tre
    byte magici dentro i dati compressi) non danno mai un membro intero (serve
    il CRC giusto) e si saltano."""
    pos = 0
    n = len(dati)
    while pos < n:
        inizio = dati.find(MAGIA, pos)
        if inizio < 0:
            if dati[pos:].strip(b"\x00"):
                resoconto["byte_ignorati"] += n - pos
            return
        if inizio > pos and dati[pos:inizio].strip(b"\x00"):
            resoconto["byte_ignorati"] += inizio - pos
        uscita, intero, dopo = _membro(dati, inizio, n)
        if intero:
            resoconto["membri"] += 1
            yield b"".join(uscita)
            yield b"\n"
            pos = dopo
            continue
        # guasto: il primo membro INTERO che segue fa da confine
        limite, prossimo = n, -1
        c = dati.find(MAGIA, inizio + 1)
        while c >= 0:
            _u, ok, _d = _membro(dati, c, n)
            if ok:
                limite, prossimo = c, c
                break
            c = dati.find(MAGIA, c + 1)
        uscita, _i, _d = _membro(dati, inizio, limite)
        if uscita:
            yield b"".join(uscita)
            yield b"\n"
        if prossimo < 0:
            resoconto["coda_tronca"] += 1
            return
        resoconto["membri_corrotti"] += 1
        pos = prossimo


def righe(dati: bytes) -> Tuple[List[bytes], Dict[str, int]]:
    """Le righe intere (non vuote) di un contenuto gzip anche rovinato."""
    resoconto = {"membri": 0, "membri_corrotti": 0, "coda_tronca": 0, "byte_ignorati": 0}
    out: List[bytes] = []
    resto = b""
    for pezzo in _decomprimi(dati, resoconto):
        resto += pezzo
        if b"\n" not in resto:
            continue
        parti = resto.split(b"\n")
        resto = parti.pop()
        out.extend(p for p in parti if p.strip())
    if resto.strip():
        out.append(resto)
    return out, resoconto


def righe_file(percorso: str) -> Tuple[List[bytes], Dict[str, int]]:
    with open(percorso, "rb") as fh:
        return righe(fh.read())


def problema(resoconto: Dict[str, int]) -> str:
    """Il resoconto in parole ('' se il file e' integro)."""
    parti = []
    if resoconto.get("membri_corrotti"):
        parti.append("%d membri gzip corrotti saltati" % resoconto["membri_corrotti"])
    if resoconto.get("coda_tronca"):
        parti.append("coda tronca (processo morto prima della chiusura)")
    if resoconto.get("byte_ignorati"):
        parti.append("%d byte illeggibili ignorati" % resoconto["byte_ignorati"])
    return "; ".join(parti)
