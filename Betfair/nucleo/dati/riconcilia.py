"""riconcilia.py - il confronto notturno locale contro cloud (W1-G1).

Scopo
    Dire, per tabella e finestra di tempo (di norma un giorno UTC), se il cloud
    ha TUTTE e SOLE le righe che l'archivio locale ha prodotto, e con la stessa
    versione: ``RapportoRiconciliazione`` (contratto) con
      * ``mancanti_nel_cloud``: chiavi locali della finestra che il cloud non ha
        (esclusa la riga ancora in coda nel postino: e' «in viaggio», non persa);
      * ``in_piu_nel_cloud``: chiavi del cloud nella finestra che il locale non
        conosce affatto (ha senso dove questo processo e' l'unico scrittore);
      * ``diverse``: stessa chiave, versione (``rev_colonna``) diversa.
    E' la verifica V1 di G par. 4.3: conteggi + impronte (chiave, versione).

    Lato cloud UNA RPC, ``postino_impronte`` (migrazione G1): restituisce le coppie
    [chiave, versione] della finestra (colonna del tempo) e/o delle chiavi date,
    calcolate nel database (niente download di righe intere).

    ``confronta_ombra``: il criterio di T8 in ombra (05 T8): conteggio per
    (giorno, gruppo) fra la tabella vera (vecchio scrittore) e ``<tabella>_ombra``
    (postino), RPC ``postino_confronta_ombra``; deve essere +/- 0.

Entrate
    ``ArchivioLocale``, ``Cloud`` (protocollo, client unico di W1-G2), la
    funzione ``destinazione`` del postino (ombra o vera), la mappa delle colonne
    del tempo per tabella (estensione proposta a ``SpecTabella``).

Cosa NON fa
    Non corregge nulla: confronta e riferisce. Non scrive nel cloud.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .archivio import COLONNE_TEMPO_PREDEFINITE, ArchivioLocale
from .contratto import Cloud, RapportoRiconciliazione, SpecTabella
from .schema_locale import chiave_canonica, giorno_utc, leggi_riga_log, rev_ordinabile

logger = logging.getLogger(__name__)

RPC_IMPRONTE = "postino_impronte"
RPC_CONFRONTA_OMBRA = "postino_confronta_ombra"
LOTTO_CHIAVI = 500


def normalizza_chiave(chiave: Any) -> str:
    """Chiave confrontabile fra locale e cloud: testo JSON o lista -> testo JSON
    con i numeri interi scritti da interi (``0.0`` del locale == ``0`` del cloud)."""
    valori = json.loads(chiave) if isinstance(chiave, str) else list(chiave)

    def norm(v: Any) -> Any:
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v

    return json.dumps([norm(v) for v in valori], ensure_ascii=False, separators=(", ", ": "))


def _rev(valore: Any) -> Optional[int]:
    if valore is None:
        return None
    try:
        return rev_ordinabile(valore)
    except (ValueError, TypeError):
        return None


class Riconciliatore:
    """Confronta l'archivio locale di UN processo con il cloud (o con le tabelle d'ombra)."""

    def __init__(self, archivio: ArchivioLocale, cloud: Cloud, *,
                 destinazione: Callable[[str], str] = lambda t: t,
                 colonne_tempo: Mapping[str, str] = COLONNE_TEMPO_PREDEFINITE,
                 lotto_chiavi: int = LOTTO_CHIAVI) -> None:
        self.archivio = archivio
        self.cloud = cloud
        self._destinazione = destinazione
        self._colonne_tempo = dict(colonne_tempo)
        self._lotto = max(1, int(lotto_chiavi))

    def confronta(self, tabella: str, da_ts: datetime, a_ts: Optional[datetime] = None) -> RapportoRiconciliazione:
        spec = self.archivio.spec(tabella)
        da_ms = int(da_ts.timestamp() * 1000)
        a_ms = int(a_ts.timestamp() * 1000) if a_ts is not None else None
        locali, tutte_locali = self._locali(spec, da_ms, a_ms)
        in_coda = {normalizza_chiave(k) for k in self.archivio.chiavi_in_coda(tabella)}
        col_t = self._colonne_tempo.get(tabella)
        if col_t is None:
            logger.warning("[riconcilia] %s: nessuna colonna del tempo, 'in piu' nel cloud non calcolabile", tabella)
        finestra = self._impronte(spec, col_t, da_ts, a_ts, chiavi=[]) if col_t else {}
        per_chiave = self._impronte_per_chiavi(spec, list(locali))
        cloud = {**finestra, **per_chiave}
        mancanti = sorted(k for k in locali if k not in cloud and k not in in_coda)
        diverse = sorted(k for k in locali if k in cloud and spec.rev_colonna and locali[k] is not None
                         and cloud[k] is not None and locali[k] != cloud[k])
        in_piu = sorted(k for k in finestra if k not in tutte_locali)
        return RapportoRiconciliazione(tabella=tabella, da_ts=da_ts, righe_locali=len(locali),
                                       righe_cloud=len(finestra), mancanti_nel_cloud=tuple(mancanti),
                                       in_piu_nel_cloud=tuple(in_piu), diverse=tuple(diverse))

    # ------------------------------------------------------------------ lato locale
    def _locali(self, spec: SpecTabella, da_ms: int, a_ms: Optional[int]) -> Tuple[Dict[str, Optional[int]], Set[str]]:
        """(chiave normalizzata -> versione) della finestra, e TUTTE le chiavi locali note."""
        finestra: Dict[str, Optional[int]] = {}
        tutte: Set[str] = set()
        if spec.regime != "log":
            for k, testo in self.archivio.righe_finestra(spec.nome, 0, None):
                tutte.add(normalizza_chiave(k))
            for k, testo in self.archivio.righe_finestra(spec.nome, da_ms, a_ms):
                riga = json.loads(testo)
                finestra[normalizza_chiave(k)] = _rev(riga.get(spec.rev_colonna)) if spec.rev_colonna else None
            return finestra, tutte
        primo = giorno_utc(da_ms - 86_400_000)
        ultimo = giorno_utc((a_ms if a_ms is not None else da_ms + 400 * 86_400_000) + 86_400_000)
        for percorso in self.archivio.file_log():
            if not (primo <= percorso.stem <= ultimo):
                continue
            with open(percorso, "r", encoding="ascii", errors="replace") as f:
                for linea in f:
                    if not linea.endswith("\n") or not linea.startswith('{"t":"%s"' % spec.nome):
                        continue
                    try:
                        _, _, ms, riga = leggi_riga_log(linea)
                        k = normalizza_chiave(chiave_canonica(spec, riga))
                    except (ValueError, KeyError) as exc:
                        logger.warning("[riconcilia] riga di log guasta in %s: %s", percorso.name, exc)
                        continue
                    tutte.add(k)
                    if ms >= da_ms and (a_ms is None or ms < a_ms):
                        finestra[k] = _rev(riga.get(spec.rev_colonna)) if spec.rev_colonna else None
        return finestra, tutte

    # ------------------------------------------------------------------ lato cloud
    def _impronte(self, spec: SpecTabella, col_t: Optional[str], da: Optional[datetime], a: Optional[datetime],
                  chiavi: Sequence[Any]) -> Dict[str, Optional[int]]:
        argomenti = {"p_tabella": self._destinazione(spec.nome), "p_chiave": list(spec.chiave_naturale),
                     "p_rev": spec.rev_colonna, "p_colonna_tempo": col_t,
                     "p_da": da.isoformat() if da is not None else None,
                     "p_a": a.isoformat() if a is not None else None, "p_chiavi": list(chiavi)}
        risposta = self.cloud.rpc(RPC_IMPRONTE, argomenti)
        out: Dict[str, Optional[int]] = {}
        for coppia in risposta or []:
            out[normalizza_chiave(coppia[0])] = _rev(coppia[1]) if spec.rev_colonna else None
        return out

    def _impronte_per_chiavi(self, spec: SpecTabella, chiavi: List[str]) -> Dict[str, Optional[int]]:
        out: Dict[str, Optional[int]] = {}
        for i in range(0, len(chiavi), self._lotto):
            pezzo = [json.loads(k) for k in chiavi[i:i + self._lotto]]
            out.update(self._impronte(spec, None, None, None, chiavi=pezzo))
        return out


def confronta_ombra(cloud: Cloud, tabella: str, gruppo: Sequence[str], colonna_tempo: str,
                    da: datetime, a: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """T8 in ombra: le righe (giorno, gruppo) con conteggi DIVERSI fra ``tabella`` e
    ``tabella_ombra``. Lista vuota = +/- 0, il criterio di «uguale» di 05 T8."""
    risposta = cloud.rpc(RPC_CONFRONTA_OMBRA, {
        "p_tabella": tabella, "p_gruppo": list(gruppo), "p_colonna_tempo": colonna_tempo,
        "p_da": da.isoformat(), "p_a": (a or (da + timedelta(days=1))).isoformat()})
    return list(risposta or [])


def ieri_utc(adesso: Optional[datetime] = None) -> str:
    """Il giorno UTC da riconciliare di notte."""
    t = adesso or datetime.now(timezone.utc)
    return (t - timedelta(days=1)).strftime("%Y-%m-%d")
