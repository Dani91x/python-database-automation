"""Conta le OPERAZIONI LIVE CONCLUSE di oggi. Solo lettura, nessun effetto.

REGOLA DI CONTEGGIO (dichiarata, non implicita):
  un'operazione = **una riga di INGRESSO** arrivata a uno stato definitivo
  (won / lost / void).

Le gambe di CHIUSURA (`closes_trade_id` valorizzato) NON contano come
operazioni proprie: sono l'uscita di un ingresso gia' contato. Contarle
raddoppierebbe ogni posizione chiusa a mano e farebbe scattare lo stop a
meta' strada.

Una riga `error` non e' un'operazione: e' un ordine mai arrivato a mercato.

ATTENZIONE alla differenza fra le due colonne, che e' costata un numero
sbagliato il 14/09: le gambe di chiusura NON si contano come operazioni, ma
il loro P&L SI' — sono soldi veri. Escluderle dalla somma gonfiava il
realizzato (+0,68 € dichiarati contro +0,38 € reali, perche' mancava la
perdita di 0,30 € della gamba #288).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

from dotenv import load_dotenv

RADICE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
load_dotenv(os.path.join(RADICE, ".env"))

URL = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
CHIAVE = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or ""
DEFINITIVI = ("won", "lost", "void")


def _leggi(percorso: str):
    req = urllib.request.Request(f"{URL}/rest/v1/{percorso}",
                                 headers={"apikey": CHIAVE,
                                          "Authorization": f"Bearer {CHIAVE}"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def conta(righe) -> tuple[int, list, list, float]:
    """(quante operazioni concluse, quali, quali aperte, quanti soldi).

    Il conteggio guarda solo gli INGRESSI; la somma guarda TUTTE le righe
    definitive, gambe di chiusura comprese."""
    concluse, aperte = [], []
    soldi = 0.0
    for t in righe:
        stato = str(t.get("status") or "")
        if stato in DEFINITIVI:
            soldi += float(t.get("pnl") or 0.0)   # i soldi contano sempre
        if t.get("closes_trade_id"):          # gamba di uscita, non un'operazione
            continue
        if stato in DEFINITIVI:
            concluse.append(t)
        elif stato in ("open", "hedged", "pending"):
            aperte.append(t)
    return len(concluse), concluse, aperte, round(soldi, 2)


def main() -> int:
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    righe = _leggi(
        "safe_strategy_trades?select=id,status,side,price,size,pnl,event_name,"
        f"closes_trade_id,placed_at&mode=eq.live&placed_at=gte.{oggi}&order=id")
    n, concluse, aperte, somma = conta(righe)
    dettaglio = " · ".join(f"#{t['id']} {t['status']} {float(t.get('pnl') or 0):+.2f}"
                           for t in concluse) or "nessuna"
    print(f"CONCLUSE={n} APERTE={len(aperte)} REALIZZATO={somma:+.2f} | {dettaglio}",
          flush=True)
    return 0 if n < 5 else 1          # 1 = soglia raggiunta


if __name__ == "__main__":
    sys.exit(main())
