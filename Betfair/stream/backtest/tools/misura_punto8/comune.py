# -*- coding: utf-8 -*-
"""comune - gli strumenti statistici condivisi della MISURA PUNTO 8 (25/09/2026).

Solo misura: niente rete, niente DB, niente scrittura fuori dalla cartella di
uscita scelta dal chiamante. Tutte le funzioni sono PURE e deterministiche
(seme fisso), cosi' che un referto si possa rifare identico.

Le regole di rigore (ordine dell'utente del 25/09, "massimo livello matematico,
ogni stima validata fuori campione con numeri PRIMA della produzione"):
  * log-loss e Brier si calcolano sull'esito VERO, mai su una media gia' fatta;
  * l'intervallo di confidenza e' un BOOTSTRAP A GRAPPOLO sulle unita'
    indipendenti (la partita, o la lega, o l'evento registrato): i campioni
    della stessa partita sono correlati e ricampionarli uno per uno darebbe un
    IC falsamente stretto;
  * almeno 2.000 ricampionamenti (``GIRI_MIN``): sotto si rifiuta di rispondere;
  * il verdetto e' "MIGLIORA" solo se l'IC al 95 % della differenza APPAIATA
    esclude lo zero dalla parte giusta; se lo contiene e' "NON MIGLIORA".
"""
from __future__ import annotations

import math
from typing import Dict, Hashable, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

GIRI_MIN = 2000
SEME = 20260925
EPS = 1e-12


# ---------------------------------------------------------------------------
# metriche su UN esito
# ---------------------------------------------------------------------------
def log_loss(p: float) -> float:
    """-log(p) dell'esito accaduto. p viene tenuta lontana da 0 (1e-12): una
    probabilita' zero data a un esito accaduto e' un errore infinito, qui
    diventa un errore grande e finito (27,6) che si vede nella media."""
    return -math.log(max(EPS, float(p)))


def log_loss_binario(p: float, esito: int) -> float:
    """Log-loss di un evento binario: -[y log p + (1-y) log(1-p)]."""
    p = min(1.0 - EPS, max(EPS, float(p)))
    return -math.log(p) if int(esito) else -math.log(1.0 - p)


def brier_binario(p: float, esito: int) -> float:
    return (float(p) - float(int(esito))) ** 2


def brier_multiclasse(griglia: Mapping[Hashable, float], accaduto: Hashable) -> float:
    """Somma sulle classi di (p - 1[classe accaduta])^2. Una classe accaduta che
    la griglia non contiene conta come p=0 (il termine (0-1)^2 = 1)."""
    tot = 0.0
    visto = False
    for k, p in griglia.items():
        if k == accaduto:
            tot += (float(p) - 1.0) ** 2
            visto = True
        else:
            tot += float(p) ** 2
    if not visto:
        tot += 1.0
    return tot


# ---------------------------------------------------------------------------
# bootstrap a grappolo
# ---------------------------------------------------------------------------
def _raggruppa(valori: Sequence[float], unita: Sequence[Hashable]) -> Tuple[np.ndarray, np.ndarray, List[Hashable]]:
    somme: Dict[Hashable, float] = {}
    conti: Dict[Hashable, int] = {}
    ordine: List[Hashable] = []
    for v, u in zip(valori, unita):
        if u not in somme:
            somme[u] = 0.0
            conti[u] = 0
            ordine.append(u)
        somme[u] += float(v)
        conti[u] += 1
    return (np.array([somme[u] for u in ordine], dtype=float),
            np.array([conti[u] for u in ordine], dtype=float), ordine)


def bootstrap_media(valori: Sequence[float], unita: Sequence[Hashable], *,
                    giri: int = GIRI_MIN, seme: int = SEME,
                    alfa: float = 0.05) -> Dict[str, float]:
    """Media dei ``valori`` e IC percentile al (1-alfa) con bootstrap A GRAPPOLO
    sulle ``unita'`` (si ricampionano le unita', ognuna con tutti i suoi valori;
    la media e' il rapporto somma/conteggio, cosi' un grappolo grande pesa per
    i suoi campioni).

    Per una DIFFERENZA APPAIATA si passa ``valori = a - b`` campione per
    campione: e' il conto onesto (le due braccia vedono gli stessi esiti)."""
    if int(giri) < GIRI_MIN:
        raise ValueError(f"servono almeno {GIRI_MIN} ricampionamenti, chiesti {giri}")
    if len(valori) != len(unita):
        raise ValueError("valori e unita' di lunghezza diversa")
    if not len(valori):
        return {"media": float("nan"), "lo": float("nan"), "hi": float("nan"),
                "n": 0, "n_unita": 0}
    s, c, ordine = _raggruppa(valori, unita)
    k = len(ordine)
    rng = np.random.default_rng(int(seme))
    idx = rng.integers(0, k, size=(int(giri), k))
    medie = s[idx].sum(axis=1) / c[idx].sum(axis=1)
    lo, hi = np.quantile(medie, [alfa / 2.0, 1.0 - alfa / 2.0])
    return {"media": float(s.sum() / c.sum()), "lo": float(lo), "hi": float(hi),
            "n": int(c.sum()), "n_unita": int(k)}


def bootstrap_rapporto(numeratori: Sequence[float], denominatori: Sequence[float],
                       unita: Sequence[Hashable], *, giri: int = GIRI_MIN,
                       seme: int = SEME, alfa: float = 0.05) -> Dict[str, float]:
    """Rapporto sum(num)/sum(den) (es. USCITI/ATTESI) con IC bootstrap a grappolo."""
    if int(giri) < GIRI_MIN:
        raise ValueError(f"servono almeno {GIRI_MIN} ricampionamenti, chiesti {giri}")
    if not len(numeratori):
        return {"rapporto": float("nan"), "lo": float("nan"), "hi": float("nan"),
                "num": 0.0, "den": 0.0, "n_unita": 0}
    sn, _, ordine = _raggruppa(numeratori, unita)
    sd, _, ordine2 = _raggruppa(denominatori, unita)
    assert ordine == ordine2
    k = len(ordine)
    rng = np.random.default_rng(int(seme))
    idx = rng.integers(0, k, size=(int(giri), k))
    den = sd[idx].sum(axis=1)
    rap = np.where(den > 0, sn[idx].sum(axis=1) / np.where(den > 0, den, 1.0), np.nan)
    rap = rap[np.isfinite(rap)]
    lo, hi = (np.quantile(rap, [alfa / 2.0, 1.0 - alfa / 2.0]) if len(rap)
              else (float("nan"), float("nan")))
    tot_den = float(sd.sum())
    return {"rapporto": float(sn.sum() / tot_den) if tot_den > 0 else float("nan"),
            "lo": float(lo), "hi": float(hi), "num": float(sn.sum()),
            "den": tot_den, "n_unita": int(k)}


def wilson(k: int, n: int, z: float = 1.959964) -> Tuple[float, float]:
    """Intervallo di Wilson per una proporzione k/n (IC 95 % di default)."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1.0 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    mezzo = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centro - mezzo), min(1.0, centro + mezzo))


# ---------------------------------------------------------------------------
# verdetto
# ---------------------------------------------------------------------------
MIGLIORA = "MIGLIORA"
NON_MIGLIORA = "NON MIGLIORA"
PEGGIORA = "PEGGIORA"
NON_MISURABILE = "NON MISURABILE con i dati di oggi"


UNITA_MIN = 10     # sotto 10 grappoli il bootstrap percentile non e' affidabile


def verdetto(ic: Mapping[str, float], *, meglio_se: str = "negativo",
             unita_min: int = UNITA_MIN) -> str:
    """Il verdetto dalla DIFFERENZA variante - attuale di una perdita (log-loss,
    Brier): negativa = la variante e' migliore. "MIGLIORA" solo se TUTTO l'IC
    sta dalla parte giusta dello zero; "PEGGIORA" se tutto dalla parte sbagliata;
    altrimenti "NON MIGLIORA" (l'IC contiene lo zero).

    Con meno di ``unita_min`` unita' indipendenti (partite) il bootstrap a
    grappolo non ha abbastanza grappoli da ricampionare: l'IC esce stretto e
    storto per costruzione. Si risponde "NON MISURABILE", qualunque sia l'IC."""
    lo, hi = float(ic.get("lo", float("nan"))), float(ic.get("hi", float("nan")))
    if not (math.isfinite(lo) and math.isfinite(hi)) or int(ic.get("n", 0) or 0) == 0:
        return NON_MISURABILE
    if int(ic.get("n_unita", unita_min) or 0) < int(unita_min):
        return NON_MISURABILE + f" (solo {int(ic.get('n_unita') or 0)} partite indipendenti)"
    if meglio_se == "negativo":
        if hi < 0.0:
            return MIGLIORA
        if lo > 0.0:
            return PEGGIORA
    else:
        if lo > 0.0:
            return MIGLIORA
        if hi < 0.0:
            return PEGGIORA
    return NON_MIGLIORA


def fmt_ic(ic: Mapping[str, float], cifre: int = 5) -> str:
    m, lo, hi = ic.get("media", ic.get("rapporto")), ic.get("lo"), ic.get("hi")
    if m is None or not math.isfinite(float(m)):
        return "n/d"
    return f"{float(m):+.{cifre}f} [{float(lo):+.{cifre}f}, {float(hi):+.{cifre}f}]"


def tabella_md(intestazione: Sequence[str], righe: Iterable[Sequence[object]]) -> str:
    out = ["| " + " | ".join(intestazione) + " |",
           "|" + "|".join("---" for _ in intestazione) + "|"]
    for r in righe:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def env_db_finto() -> Dict[str, str]:
    """Le variabili che rendono IRRAGGIUNGIBILE il DB vero (regola dura del 21/09:
    ``load_dotenv`` risale al .env padre). Chi importa moduli che toccano
    Supabase le imposta PRIMA dell'import (``os.environ.update(env_db_finto())``)."""
    return {"SUPABASE_URL": "http://127.0.0.1:9", "SUPABASE_SERVICE_ROLE_KEY": "x",
            "SUPABASE_KEY": "x"}


def blinda_db() -> None:
    """Imposta le variabili del DB finto e SOVRASCRIVE quelle eventualmente gia'
    caricate: nessuno script di misura deve poter raggiungere la produzione."""
    import os
    os.environ.update(env_db_finto())
