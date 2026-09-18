"""orologio.py - L'UNICO punto in cui un nostro istante si confronta con un
istante di BETFAIR.

Perche' esiste (misura del 17/09/2026, `Betfair/safe_strategy/LATENZA_TENNIS_2026-09-17.md` §0):
l'orologio di questa macchina e' **indietro di ~2,08 s** rispetto al tempo del
mondo (time.windows.com: +2082,5 / +2068,3 / +2069,2 ms; pool.ntp.org: +2078,7 /
+2069,3 / +2068,4 ms; il servizio Ora di Windows non e' avviato). Conseguenza:
ogni differenza fra un istante nostro (``time.time()``) e un campo di Betfair
(``publishTime`` del book, ``placedDate``, ``matchedDate``) e' sbagliata di
quella quantita'. Il 17/09 questo ha prodotto una lettura falsa - "Betfair ci
mette 2,8 s ad accettare l'ordine" - che era per 2,07 s un artefatto
dell'orologio.

Che cosa fa questo modulo, e che cosa NON fa:

* **NON corregge l'orologio** e non ne assume la correzione. Sistemare l'ora e'
  un'impostazione di sistema e la fa l'utente; farlo qui vorrebbe dire nascondere
  il problema dentro il codice dei soldi.
* **DICHIARA lo scarto**: ogni confronto torna, insieme al numero, quanto vale
  l'incertezza di quel numero e se il numero e' piu' grande dell'incertezza.
* **RENDE ROBUSTI i confronti**: un confronto la cui differenza sta dentro
  l'incertezza dell'orologio e' marcato ``affidabile=False``. Chi lo legge sa
  che non puo' concluderne niente - invece di leggerlo come un fatto.

Lo scarto NOTO si dichiara con la variabile d'ambiente
``BETFAIR_SCARTO_OROLOGIO_MS`` (millisecondi, positivo = il nostro orologio e'
INDIETRO rispetto al mondo, che e' il caso misurato). Se non e' dichiarata non si
assume nessuna correzione: si usa ``SCARTO_MISURATO_MS`` come sola INCERTEZZA,
cioe' come soglia sotto la quale un confronto non dice niente.

Regola env di progetto: default da env con ``(os.getenv(x) or "").strip()`` e
ripiego sul valore di serie - mai un ``or`` che scambi lo zero per assente.

MODULO PURO: nessun import di flumine, betfairlightweight, supabase o rete. Lo
importa il processo dello SCANNER (feed unico di tutti i bot), dove flumine non
deve entrare mai - e' l'incidente del 17/09. Il test di contratto e'
``test_orologio_e_un_modulo_puro`` (sottoprocesso vero).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

#: Scarto MISURATO il 17/09/2026 contro due NTP indipendenti (ms, positivo =
#: orologio locale indietro). Non viene applicato: e' l'INCERTEZZA di serie
#: dei confronti finche' nessuno dichiara lo scarto vero.
SCARTO_MISURATO_MS = 2080.0

#: Data della misura, riportata in ogni confronto: un'incertezza senza data
#: invecchia in silenzio.
SCARTO_MISURATO_IL = "2026-09-17"

ENV_SCARTO = "BETFAIR_SCARTO_OROLOGIO_MS"


def scarto_dichiarato_ms() -> Optional[float]:
    """Scarto DICHIARATO dall'operatore in millisecondi, o None se nessuno lo ha
    dichiarato. Positivo = il nostro orologio e' INDIETRO rispetto al mondo."""
    raw = (os.environ.get(ENV_SCARTO) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def incertezza_ms() -> float:
    """Di quanto puo' sbagliare un confronto fra noi e Betfair, in millisecondi.

    Con lo scarto dichiarato l'incertezza residua e' piccola ma non nulla (la
    deriva fra due sincronizzazioni): si tiene un decimo dello scarto misurato,
    mai meno di 100 ms. Senza dichiarazione l'incertezza e' lo scarto misurato
    per intero, perche' nessuno ha detto che sia stato corretto.
    """
    if scarto_dichiarato_ms() is None:
        return SCARTO_MISURATO_MS
    return max(100.0, SCARTO_MISURATO_MS / 10.0)


def ms_da_betfair(valore: Any) -> Optional[float]:
    """Millisecondi di orologio del mondo da un campo Betfair, o None.

    Accetta cio' che i vari percorsi ci consegnano davvero, senza inventare:
      * ``int``/``float``  -> gia' millisecondi (``publishTime`` dello stream);
      * ``datetime``       -> naive trattato come UTC (betfairlightweight li
                             costruisce cosi');
      * ``str``            -> ISO 8601, con la ``Z`` finale ammessa
                             (``placedDate``, ``matchedDate``).
    ``bool`` NON e' un numero: ``isinstance(True, int)`` e' vero in Python e
    senza questa guardia un flag diventerebbe l'istante 1 ms.
    """
    if valore is None or isinstance(valore, bool):
        return None
    if isinstance(valore, (int, float)):
        return float(valore)
    if isinstance(valore, datetime):
        dt = valore if valore.tzinfo is not None else valore.replace(tzinfo=timezone.utc)
        return round(dt.timestamp() * 1000.0, 1)
    if isinstance(valore, str):
        testo = valore.strip()
        if not testo:
            return None
        try:
            dt = datetime.fromisoformat(testo.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return round(dt.timestamp() * 1000.0, 1)
    return None


def confronta(nostro_ms: Any, betfair_ms: Any, *, etichetta: str = "") -> Dict[str, Any]:
    """Confronta UN nostro istante con UN istante di Betfair, dichiarando tutto.

    Torna sempre un dizionario con le stesse chiavi (mai None al posto del
    dizionario: chi lo scrive nel meta non deve avere due forme da gestire):

    ``delta_ms``            betfair - nostro, COSI' COME E' (nessuna correzione);
    ``scarto_ms``           lo scarto dichiarato, o None se nessuno lo ha detto;
    ``delta_corretto_ms``   delta - scarto, solo se lo scarto e' dichiarato;
    ``incertezza_ms``       di quanto puo' sbagliare ``delta_ms``;
    ``affidabile``          |delta| supera l'incertezza? Se no, il numero non
                            permette di concludere niente e va letto cosi';
    ``misurato_il``         quando l'incertezza e' stata misurata;
    ``etichetta``           quale confronto e' (per chi legge il meta).

    ``valido=False`` quando uno dei due istanti manca: si dichiara l'assenza,
    non la si scrive come zero (catalogo §7: "dato assente non e' zero").
    """
    a = ms_da_betfair(nostro_ms)
    b = ms_da_betfair(betfair_ms)
    inc = incertezza_ms()
    scarto = scarto_dichiarato_ms()
    out: Dict[str, Any] = {
        "valido": False,
        "delta_ms": None,
        "scarto_ms": scarto,
        "delta_corretto_ms": None,
        "incertezza_ms": round(inc, 1),
        "affidabile": False,
        "misurato_il": SCARTO_MISURATO_IL,
    }
    if etichetta:
        out["etichetta"] = str(etichetta)
    if a is None or b is None:
        return out
    delta = round(b - a, 1)
    out["valido"] = True
    out["delta_ms"] = delta
    if scarto is not None:
        out["delta_corretto_ms"] = round(delta - float(scarto), 1)
    out["affidabile"] = abs(delta) > inc
    return out


def ritardo_da_betfair(betfair_ms: Any, nostro_ms: Any, *,
                       etichetta: str = "") -> Dict[str, Any]:
    """Quanto tempo e' passato fra un istante di BETFAIR e uno NOSTRO successivo.

    E' il verso naturale dei salti della catena dei tempi: Betfair pubblica il
    book, noi lo lavoriamo dopo. Torna ``ritardo_ms = nostro - betfair`` con le
    stesse dichiarazioni di ``confronta``, piu':

    ``impossibile``  il ritardo risulta NEGATIVO, cioe' avremmo lavorato il book
                     prima che Betfair lo pubblicasse. Non e' un dato strano: e'
                     la PROVA che l'orologio di questa macchina e' indietro, e va
                     letto come tale invece che come una latenza bassissima.
    """
    a = ms_da_betfair(betfair_ms)
    b = ms_da_betfair(nostro_ms)
    inc = incertezza_ms()
    scarto = scarto_dichiarato_ms()
    out: Dict[str, Any] = {
        "valido": False,
        "ritardo_ms": None,
        "scarto_ms": scarto,
        "ritardo_corretto_ms": None,
        "incertezza_ms": round(inc, 1),
        "affidabile": False,
        "impossibile": False,
        "misurato_il": SCARTO_MISURATO_IL,
    }
    if etichetta:
        out["etichetta"] = str(etichetta)
    if a is None or b is None:
        return out
    ritardo = round(b - a, 1)
    out["valido"] = True
    out["ritardo_ms"] = ritardo
    if scarto is not None:
        # il nostro orologio e' indietro di ``scarto``: il nostro istante vero e'
        # piu' avanti di altrettanto, quindi il ritardo vero e' piu' GRANDE.
        out["ritardo_corretto_ms"] = round(ritardo + float(scarto), 1)
    riferimento = out["ritardo_corretto_ms"] if scarto is not None else ritardo
    out["affidabile"] = abs(float(riferimento)) > inc
    out["impossibile"] = float(riferimento) < 0.0
    return out


def affidabile(nostro_ms: Any, betfair_ms: Any) -> bool:
    """Scorciatoia: questo confronto dice qualcosa, o sta dentro il rumore?"""
    return bool(confronta(nostro_ms, betfair_ms).get("affidabile"))


def nota() -> Dict[str, Any]:
    """Lo stato dell'orologio, da allegare a un referto o a una riga di attivita'."""
    scarto = scarto_dichiarato_ms()
    return {
        "scarto_dichiarato_ms": scarto,
        "scarto_misurato_ms": SCARTO_MISURATO_MS,
        "misurato_il": SCARTO_MISURATO_IL,
        "incertezza_ms": round(incertezza_ms(), 1),
        "come_dichiararlo": ENV_SCARTO,
    }
