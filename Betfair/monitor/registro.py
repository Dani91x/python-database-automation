"""registro.py - i contatori IN MEMORIA del modulo "Salute" (T0A, 09/10/2026).

Tre tipi di grandezza, tutte per FINESTRA (azzerate a ogni riga scritta, una
riga ogni 30 s per servizio; il referto le somma):

  conta(gruppo, chiave, n)   contatori (richieste al DB per tabella, REST per
                             metodo, transazioni, errori di log per logger...)
  tratto(nome, ms)           durate in millisecondi su un ISTOGRAMMA A SECCHI
                             FISSI (stessi bordi in ogni processo e in ogni
                             finestra: due finestre si sommano secchio per
                             secchio, quindi i percentili del referto di 24 h
                             sono esatti alla risoluzione del secchio, mai una
                             media di percentili)
  valore(gruppo, chiave, v)  ultimo valore visto (es. ``connectionsAvailable``):
                             NON si azzera, passa di riga in riga

Costo nel percorso caldo: un lucchetto e qualche operazione su dict; nessun
I/O, nessuna allocazione che cresca senza tetto (``MAX_CHIAVI`` per gruppo: le
chiavi in piu' finiscono in ``_altro``).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import bisect
import threading
from typing import Any, Dict, List, Optional

#: bordi SUPERIORI dei secchi in ms (1-2-5 per decade, da 0,1 ms a 60 s); un
#: valore oltre l'ultimo bordo cade nel secchio di troppo pieno (indice len).
BORDI_MS: tuple = (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0,
                   500.0, 1000.0, 2000.0, 5000.0, 10000.0, 20000.0, 60000.0)

#: tetto delle chiavi distinte per gruppo e per finestra (difesa contro chiavi
#: impazzite, per esempio un percorso REST con un id dentro)
MAX_CHIAVI = 200
ALTRO = "_altro"


class Istogramma:
    """n, somma, minimo, massimo e conteggi per secchio di una finestra."""

    __slots__ = ("n", "somma", "minimo", "massimo", "secchi")

    def __init__(self) -> None:
        self.n = 0
        self.somma = 0.0
        self.minimo: Optional[float] = None
        self.massimo: Optional[float] = None
        self.secchi: List[int] = [0] * (len(BORDI_MS) + 1)

    def aggiungi(self, ms: float) -> None:
        v = float(ms)
        self.n += 1
        self.somma += v
        if self.minimo is None or v < self.minimo:
            self.minimo = v
        if self.massimo is None or v > self.massimo:
            self.massimo = v
        self.secchi[bisect.bisect_left(BORDI_MS, v)] += 1

    def riassunto(self) -> Dict[str, Any]:
        """Forma della riga (chiavi stabili): n, somma, min, max, p50, p99, secchi."""
        return {
            "n": self.n,
            "somma": round(self.somma, 3),
            "min": None if self.minimo is None else round(self.minimo, 3),
            "max": None if self.massimo is None else round(self.massimo, 3),
            "p50": quantile_da_secchi(self.secchi, 0.50, self.massimo),
            "p99": quantile_da_secchi(self.secchi, 0.99, self.massimo),
            "secchi": list(self.secchi),
        }


def quantile_da_secchi(secchi: List[int], q: float, massimo: Optional[float] = None
                       ) -> Optional[float]:
    """Quantile ``q`` (0-1) come BORDO SUPERIORE del secchio che lo contiene
    (stima per eccesso alla risoluzione del secchio); il secchio di troppo pieno
    vale il massimo osservato. None se vuoto."""
    tot = sum(int(x) for x in secchi)
    if tot <= 0:
        return None
    soglia = q * tot
    cum = 0
    for i, c in enumerate(secchi):
        cum += int(c)
        if cum >= soglia and c:
            if i < len(BORDI_MS):
                b = BORDI_MS[i]
                return float(min(b, massimo)) if massimo is not None else float(b)
            return None if massimo is None else round(float(massimo), 3)
    return None if massimo is None else round(float(massimo), 3)


def somma_riassunti(riassunti: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Somma secchio per secchio piu' riassunti (finestre o processi diversi)."""
    secchi = [0] * (len(BORDI_MS) + 1)
    n = 0
    somma = 0.0
    mn: Optional[float] = None
    mx: Optional[float] = None
    for r in riassunti:
        if not isinstance(r, dict):
            continue
        for i, c in enumerate(r.get("secchi") or []):
            if i < len(secchi):
                secchi[i] += int(c or 0)
        n += int(r.get("n") or 0)
        somma += float(r.get("somma") or 0.0)
        a, b = r.get("min"), r.get("max")
        if a is not None and (mn is None or a < mn):
            mn = float(a)
        if b is not None and (mx is None or b > mx):
            mx = float(b)
    return {"n": n, "somma": round(somma, 3), "min": mn, "max": mx,
            "p50": quantile_da_secchi(secchi, 0.50, mx),
            "p95": quantile_da_secchi(secchi, 0.95, mx),
            "p99": quantile_da_secchi(secchi, 0.99, mx),
            "secchi": secchi}


class Registro:
    """I contatori di UN processo. Thread-safe; ``fotografa_e_azzera`` la usa
    solo lo scrittore (fuori dal percorso caldo)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._contatori: Dict[str, Dict[str, float]] = {}
        self._tratti: Dict[str, Istogramma] = {}
        self._valori: Dict[str, Dict[str, Any]] = {}

    # ---------------------------------------------------------------- scrittura
    def conta(self, gruppo: str, chiave: str, n: float = 1) -> None:
        with self._lock:
            g = self._contatori.get(gruppo)
            if g is None:
                g = self._contatori[gruppo] = {}
            if chiave not in g and len(g) >= MAX_CHIAVI:
                chiave = ALTRO
            g[chiave] = g.get(chiave, 0) + n

    def tratto(self, nome: str, ms: float) -> None:
        with self._lock:
            h = self._tratti.get(nome)
            if h is None:
                if len(self._tratti) >= MAX_CHIAVI:
                    return
                h = self._tratti[nome] = Istogramma()
            h.aggiungi(ms)

    def valore(self, gruppo: str, chiave: str, v: Any) -> None:
        with self._lock:
            g = self._valori.get(gruppo)
            if g is None:
                g = self._valori[gruppo] = {}
            if chiave not in g and len(g) >= MAX_CHIAVI:
                return
            g[chiave] = v

    # ---------------------------------------------------------------- lettura
    def fotografa_e_azzera(self) -> Dict[str, Any]:
        """Contatori e tratti della finestra (poi azzerati) + valori correnti."""
        with self._lock:
            contatori, self._contatori = self._contatori, {}
            tratti, self._tratti = self._tratti, {}
            valori = {g: dict(d) for g, d in self._valori.items()}
        return {
            "contatori": {g: {k: (int(v) if float(v).is_integer() else v)
                              for k, v in sorted(d.items())}
                          for g, d in sorted(contatori.items())},
            "tratti": {k: h.riassunto() for k, h in sorted(tratti.items())},
            "valori": {g: dict(sorted(d.items())) for g, d in sorted(valori.items())},
        }

    def azzera_tutto(self) -> None:
        with self._lock:
            self._contatori = {}
            self._tratti = {}
            self._valori = {}
