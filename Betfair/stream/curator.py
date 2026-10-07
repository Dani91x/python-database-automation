"""Curator: file JSONL grezzo → righe curate per live_market_snapshots.

Funzione PURA (path → lista di righe): nessuna I/O di rete, testabile con una
fixture JSONL sintetica.

Curazione = write-on-change con throttle:
  conserva uno snapshot di un mercato SOLO se (a) è il primo, (b) i best
  back/lay di qualche selezione sono cambiati, (c) è passato almeno
  `cadence_sec` dall'ultimo conservato per quel mercato, oppure (d) dal 07/10
  e' cambiato lo STATO del mercato (status o inplay) rispetto all'ultima riga
  conservata: senza (d) la chiusura di un mercato gia' vuoto da sospeso spariva
  dal replay (35760084: 17 mercati su 21 finivano SOSPESI invece che CHIUSI).
Riduce drasticamente le righe senza perdere la dinamica direzionale.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)


def iter_jsonl(path: str) -> Iterator[Dict[str, Any]]:
    """Itera le righe di un file JSONL, saltando righe vuote/corrotte."""
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                logger.warning("[curator] riga JSONL corrotta saltata")
                continue


def _ms_to_iso(pt_ms: Optional[int]) -> Optional[str]:
    if pt_ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(pt_ms) / 1000.0, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def ladder_db_format(runners: Dict[str, Any]) -> Dict[str, Any]:
    """runners del JSONL ({b,l,ltp,tv,trd}) → ladder DB ({back,lay,ltp,tv,trd}).

    `trd` (volume tradato per-prezzo) viene incluso SOLO se presente, così i replay
    vecchi restano leggeri e il motore di matching ricade sul proxy ltp/Δtv.
    """
    out: Dict[str, Any] = {}
    for sel_id, r in (runners or {}).items():
        entry: Dict[str, Any] = {
            "back": r.get("b", []),
            "lay": r.get("l", []),
            "ltp": r.get("ltp"),
            "tv": r.get("tv"),
        }
        trd = r.get("trd")
        if trd:
            entry["trd"] = trd
        out[str(sel_id)] = entry
    return out


def _best_signature(runners: Dict[str, Any]) -> Tuple:
    """Firma comparabile dei best back/lay (per il rilevamento del cambiamento)."""
    sig: List[Tuple] = []
    for sel_id in sorted(runners or {}):
        r = runners[sel_id]
        back = r.get("b") or []
        lay = r.get("l") or []
        best_b = tuple(back[0]) if back else None
        best_l = tuple(lay[0]) if lay else None
        sig.append((sel_id, best_b, best_l, r.get("ltp")))
    return tuple(sig)


def _minute_at(ts_ms: Optional[int], timeline: Optional[List[Dict[str, Any]]]) -> Optional[int]:
    """Stima il minuto a un istante usando la timeline punteggio (ultimo <= ts)."""
    if not timeline or ts_ms is None:
        return None
    minute = None
    for ev in timeline:
        ev_ms = ev.get("ts_ms")
        if ev_ms is None:
            continue
        if ev_ms <= ts_ms and ev.get("minute") is not None:
            minute = ev["minute"]
        elif ev_ms > ts_ms:
            break
    return minute


def curate_event(
    path: str,
    event_id: str,
    cadence_sec: float = 10.0,
    timeline: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Rilegge il JSONL grezzo e produce le righe curate per live_market_snapshots.

    :param timeline: opzionale, lista {ts_ms, minute} per stimare il minuto.
    :returns: righe pronte per l'upsert (ordinate per ts crescente).
    """
    rows = curate_records(iter_jsonl(path), event_id, cadence_sec=cadence_sec, timeline=timeline)
    logger.info("[curator] %s: %d snapshot curati da %s", event_id, len(rows), path)
    return rows


def curate_records(
    records: Iterable[Dict[str, Any]],
    event_id: str,
    cadence_sec: float = 10.0,
    timeline: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """La curazione di ``curate_event`` su record GIA' letti (stessa regola).

    07/10 (decisione dell'utente «correggi», calcio e tennis): un cambio di
    ``status`` o di ``inplay`` rispetto all'ultima riga conservata entra SEMPRE,
    anche coi best invariati. E' una riga IN PIU': il resto della regola (cambio
    dei best, cadenza) e il suo orologio non cambiano, quindi nessuna riga che
    entrava prima esce (provato sulle 35797769 e 35760084).

    07/10 (replay tennis): estratta da ``curate_event`` SENZA cambiarne la
    logica, perche' il replay del tennis produce gli stessi record compatti
    (``recorder.serialize_book``) decodificando il raw nativo con
    betfairlightweight invece di leggerli da un file curato: la regola di
    conservazione (primo snapshot, cambio dei best, cadenza minima) resta UNA.
    """
    cadence_ms = cadence_sec * 1000.0
    last_kept_ms: Dict[str, float] = {}
    last_sig: Dict[str, Tuple] = {}
    last_stato: Dict[str, Tuple] = {}
    rows: List[Dict[str, Any]] = []

    for rec in records:
        market_id = rec.get("market_id")
        if not market_id:
            continue
        pt = rec.get("pt")
        runners = rec.get("runners") or {}
        sig = _best_signature(runners)
        stato = (rec.get("status") or "OPEN", bool(rec.get("inplay", False)))

        seen = market_id in last_sig
        # primo snapshot del mercato = sempre conservato; poi write-on-change.
        changed = (not seen) or (last_sig[market_id] != sig)
        prev_ms = last_kept_ms.get(market_id)
        # throttle: conserva un invariato solo se è trascorsa la cadenza minima e
        # conosciamo i timestamp. Con pt ignoto si cade sulla sola write-on-change
        # (altrimenti i duplicati passerebbero tutti).
        throttled_ok = pt is not None and prev_ms is not None and (pt - prev_ms) >= cadence_ms

        # 07/10: lo stato del mercato cambiato (sospeso, chiuso, in gioco) entra
        # sempre, SENZA spostare l'orologio della cadenza ne' la firma dei best
        stato_cambiato = seen and last_stato.get(market_id) != stato
        regola_di_sempre = changed or throttled_ok

        # conserva se è cambiato qualcosa OPPURE è passata la cadenza minima
        if not regola_di_sempre and not stato_cambiato:
            continue

        rows.append(
            {
                "event_id": event_id,
                "market_id": market_id,
                "ts": _ms_to_iso(pt),
                "minute": _minute_at(pt, timeline),
                "inplay": bool(rec.get("inplay", False)),
                "status": rec.get("status") or "OPEN",
                "ladder": ladder_db_format(runners),
            }
        )
        last_stato[market_id] = stato
        if not regola_di_sempre:
            continue                    # riga di solo stato: cadenza e firma invariate
        last_sig[market_id] = sig
        if pt is not None:
            last_kept_ms[market_id] = pt

    rows.sort(key=lambda r: (r["ts"] or "", r["market_id"]))
    return rows
