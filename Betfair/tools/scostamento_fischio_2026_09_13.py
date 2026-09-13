#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""scostamento_fischio -- di quanti tick si muove l'Under 3.5 fra il nostro
ingresso PRE-MATCH e il FISCHIO D'INIZIO.

SOLA LETTURA. Nessuna scrittura sul DB, nessun servizio avviato, nessun ordine.
Rieseguibile: ogni esecuzione rifa' i conti sullo stato corrente, quindi ha senso
rilanciarlo man mano che le partite si accumulano.

Perche' esiste
--------------
La domanda e' semplice: "le posizioni che NON riusciamo a chiudere prima del
fischio, a che prezzo si ritrovano quando la partita parte?". Fino al 13/09 non
era rispondibile: nessuna tabella conservava il prezzo dell'Under al fischio, e
il primo ordine Under piazzato in gioco arriva al 27' nel caso piu' precoce
(mediana 54'). Sulle 111 posizioni storiche non esisteva UNA sola osservazione
vicina al calcio d'inizio.

Ora il servizio registra ``ko_price_under`` al passaggio in gioco, una volta
sola. Questo strumento lo legge e ne fa la statistica.

Come si legge il risultato
--------------------------
Lo scostamento e' in TICK della scala Betfair, col segno:

  NEGATIVO  il prezzo e' SCESO -> a nostro favore su un back Under: l'ordine di
            chiusura appoggiato a due tick sotto e' piu' vicino, e la posizione
            entra in gioco gia' in guadagno.
  POSITIVO  il prezzo e' SALITO -> siamo sotto: l'Under vale meno di quanto
            l'abbiamo pagato.

Il numero che conta e' la MEDIANA, non la media: bastano due partite con un gol
al 3' per spostare la media di decine di tick.

Uso
---
    python -m Betfair.tools.scostamento_fischio_2026_09_13

Output ASCII (console Windows cp1252).
"""
from __future__ import annotations

import os
import statistics
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# sotto questo numero di osservazioni la mediana non dice nulla di solido
MIN_CAMPIONE = 20


def _env() -> dict[str, str]:
    out: dict[str, str] = {}
    with open(os.path.join(ROOT, ".env"), encoding="utf8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _client():
    from supabase import create_client

    env = _env()
    return create_client(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])


class Osservazione:
    __slots__ = ("nome", "ingresso", "fischio", "tick", "gol", "stato")

    def __init__(self, nome: str, ingresso: float, fischio: float, tick: int,
                 gol: Optional[int], stato: str) -> None:
        self.nome, self.ingresso, self.fischio = nome, ingresso, fischio
        self.tick, self.gol, self.stato = tick, gol, stato


def carica(db: Any) -> list[Osservazione]:
    """Partite entrate in gioco con una posizione pre-match ancora aperta e col
    prezzo del fischio registrato."""
    from Betfair.mike import engine as E

    rows = db.table("mike_events").select(
        "event_name,state,entry_price_initial,ctx,live"
    ).execute().data or []
    out: list[Osservazione] = []
    for r in rows:
        ctx = r.get("ctx") if isinstance(r.get("ctx"), dict) else {}
        live = r.get("live") if isinstance(r.get("live"), dict) else {}
        ko = ctx.get("ko_price_under")
        if ko is None:
            ko = live.get("ko_price_under")
        ingresso = r.get("entry_price_initial")
        tick = E.drift_ticks(ingresso, ko)
        if tick is None:
            continue
        out.append(Osservazione(
            nome=str(r.get("event_name") or "?"),
            ingresso=float(ingresso), fischio=float(ko), tick=int(tick),
            gol=live.get("goals"), stato=str(r.get("state") or ""),
        ))
    return out


def stampa(dati: list[Osservazione]) -> None:
    print()
    print("=" * 70)
    print(" SCOSTAMENTO FRA INGRESSO PRE-MATCH E FISCHIO D'INIZIO (Under 3.5)")
    print("=" * 70)
    print()
    if not dati:
        print("  Nessuna osservazione ancora.")
        print()
        print("  Il prezzo al fischio lo registra il servizio dal 13/09, al")
        print("  passaggio in gioco di una partita con posizione pre-match")
        print("  ancora aperta. Serve che qualche partita ci passi: riprova")
        print("  dopo la prossima sessione di gioco.")
        return

    print("  %-34s %9s %9s %8s %5s" % ("PARTITA", "ingresso", "fischio", "tick", "gol"))
    for o in sorted(dati, key=lambda x: x.tick):
        print("  %-34s %9.2f %9.2f %+8d %5s"
              % (o.nome[:34], o.ingresso, o.fischio, o.tick, "-" if o.gol is None else o.gol))

    t = [o.tick for o in dati]
    favore = [x for x in t if x < 0]
    contro = [x for x in t if x > 0]
    print()
    print("  osservazioni: %d" % len(t))
    print("  mediana  %+.0f tick        <- il numero da guardare" % statistics.median(t))
    print("  media    %+.1f tick        (la spostano i casi estremi)" % (sum(t) / len(t)))
    print("  peggiore %+d tick   migliore %+d tick" % (max(t), min(t)))
    print()
    print("  prezzo SCESO (a nostro favore): %d  (%.0f%%)" % (len(favore), 100 * len(favore) / len(t)))
    print("  prezzo SALITO (siamo sotto)   : %d  (%.0f%%)" % (len(contro), 100 * len(contro) / len(t)))
    print("  invariato                     : %d" % (len(t) - len(favore) - len(contro)))

    # due tick e' la distanza dell'ordine di chiusura appoggiato in pre-match:
    # se il fischio ci porta gia' li', la posizione entra in gioco in guadagno
    gia_dentro = [x for x in t if x <= -2]
    print()
    print("  gia' a due tick o meglio al fischio: %d su %d (%.0f%%)"
          % (len(gia_dentro), len(t), 100 * len(gia_dentro) / len(t)))
    print("     (due tick e' la distanza dell'ordine di chiusura pre-match:")
    print("      queste posizioni entrano in gioco gia' in guadagno)")

    if len(t) < MIN_CAMPIONE:
        print()
        print("  ATTENZIONE: solo %d osservazioni. Sotto le %d la mediana e'"
              % (len(t), MIN_CAMPIONE))
        print("  indicativa, non una conclusione. Rilanciare fra qualche giorno.")


def main() -> int:
    try:
        db = _client()
    except Exception as ex:  # noqa: BLE001
        print("  connessione al DB fallita: %s" % str(ex)[:160])
        return 2
    try:
        dati = carica(db)
    except Exception as ex:  # noqa: BLE001
        print("  lettura fallita: %s" % str(ex)[:160])
        return 2
    stampa(dati)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
