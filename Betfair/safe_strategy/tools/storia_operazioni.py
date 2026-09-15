"""Ricostruisce la STORIA di ogni operazione live. Sola lettura.

Risponde alla domanda che l'utente ha posto il 14/09 (condizione 7):
«a che prezzo abbinano gli ordini di chiusura rispetto al segnale, o se
camminano sul book falsificando l'uscita».

Per ogni ingresso stampa:
  · il prezzo CHIESTO e quello ABBINATO, con lo scostamento in tick;
  · la catena dei tempi, salto per salto, dal cambio di prezzo su Betfair
    fino alla risposta dell'ordine;
  · l'uscita: proposta (prezzo, bloccabile, motivo), decisione umana, e a
    che prezzo ha davvero abbinato la gamba di chiusura.

CONVENZIONE DELLO SCOSTAMENTO (da `execution.scorrimento`): positivo =
abbinato PEGGIO del chiesto, negativo = meglio, zero = al prezzo del
segnale. Non si reinterpreta il segno qui: si legge quello scritto.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

from dotenv import load_dotenv

RADICE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
load_dotenv(os.path.join(RADICE, ".env"))
URL = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
CHIAVE = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or ""


def _leggi(percorso: str):
    req = urllib.request.Request(f"{URL}/rest/v1/{percorso}",
                                 headers={"apikey": CHIAVE,
                                          "Authorization": f"Bearer {CHIAVE}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _ora(ms) -> str:
    """Un istante in millisecondi come orologio. Assente = '—', mai '0'."""
    try:
        v = float(ms)
    except (TypeError, ValueError):
        return "—"
    if v <= 0:
        return "—"
    return datetime.fromtimestamp(v / 1000.0, timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def _salto(da, a) -> str:
    """Millisecondi fra due istanti. Manca un capo -> '—', MAI zero: «non lo
    so» e «istantaneo» sono due affermazioni diverse."""
    try:
        d = float(a) - float(da)
    except (TypeError, ValueError):
        return "—"
    if d < 0:
        return "—"
    return f"{d:.0f} ms" if d < 1000 else f"{d / 1000:.1f} s"


def _ms(v) -> str:
    """Millisecondi, o «—». Un ordine passato dalla CODA flumine non ha
    `betfair_ms`: scrivere «None ms» fa sembrare rotto un percorso che
    semplicemente non misura quel tratto."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "\u2014"
    return f"{f:.1f} ms"


def _testo(v) -> str:
    """Una stringa, o «—». Mai la parola «None» sotto gli occhi di chi legge."""
    return str(v) if isinstance(v, str) and v.strip() else "\u2014"


def _giudizio(tick) -> str:
    if tick is None:
        return "scostamento non misurato"
    t = int(tick)
    if t == 0:
        return "ABBINATO AL PREZZO DEL SEGNALE"
    if t < 0:
        return f"abbinato MEGLIO del chiesto di {-t} tick"
    return f"abbinato PEGGIO del chiesto di {t} tick  <-- ha camminato sul book"


def racconta(t: dict, uscite: dict, richieste: dict) -> None:
    m = t.get("meta") or {}
    e = m.get("esecuzione") or {}
    tp = m.get("tempi") or {}
    print("=" * 78)
    print(f"OPERAZIONE #{t['id']}  {t.get('event_name')} / {t.get('selection_name')}")
    print(f"  stato {t.get('status')}  ·  {t.get('side')} {t.get('size')} € @ {t.get('price')}"
          f"  ·  P&L {t.get('pnl')}")

    print("  -- INGRESSO --")
    print(f"     chiesto {e.get('price_richiesto')}  ->  abbinato medio {e.get('price_medio')}"
          f"   [{_giudizio(e.get('scorrimento_tick'))}]")
    print(f"     percorso {_testo(e.get('percorso'))}  ·  Betfair ha risposto in "
          f"{_ms(e.get('betfair_ms'))}")
    print("     catena dei tempi:")
    print(f"       prezzo cambiato su Betfair   {_ora(tp.get('t0_quote_ms'))}")
    print(f"       riga scritta dallo scanner   {_ora(tp.get('t1_feed_ms'))}"
          f"   (+{_salto(tp.get('t0_quote_ms'), tp.get('t1_feed_ms'))})")
    print(f"       riga in mano al bot          {_ora(tp.get('t2_letto_ms'))}"
          f"   (+{_salto(tp.get('t1_feed_ms'), tp.get('t2_letto_ms'))})")
    print(f"       decisione presa              {_ora(tp.get('t3_deciso_ms'))}")
    print(f"       ordine inviato               {_ora(e.get('t4_inviato'))}"
          f"   (+{_salto(tp.get('t3_deciso_ms'), e.get('t4_inviato'))})")
    print(f"       Betfair risponde             {_ora(e.get('t5_risposta'))}"
          f"   (+{_salto(e.get('t4_inviato'), e.get('t5_risposta'))})")

    prop = m.get("exit_proposal") or {}
    rid = prop.get("request_id")
    r = richieste.get(int(rid)) if rid else None
    u = uscite.get(int(t["id"]))
    if not (prop or u):
        print("  -- USCITA -- nessuna: la posizione e' andata a scadenza")
        return

    print("  -- USCITA --")
    if r:
        p = r.get("payload") or {}
        print(f"     proposta #{r['id']} alle {p.get('proposed_at')}  motivo: {p.get('exit_reason')}")
        print(f"       prezzo proposto {p.get('price_at_decision')}  ·  bloccabile "
              f"{p.get('locked_at_decision')} €  ·  tenere valeva {p.get('hold_profit')} €")
        print(f"       abbinabile allora {p.get('size_available_at_decision')} €"
              f"  ·  punteggio «{p.get('score')}»")
        print(f"       decisione umana: {r.get('status')}"
              + (f" alle {p.get('approved_at')}" if p.get("approved_at") else ""))
    if u:
        ue = (u.get("meta") or {}).get("esecuzione") or {}
        segnale = (u.get("meta") or {}).get("price_segnale")
        print(f"     gamba di chiusura #{u['id']}: {u.get('side')} {u.get('size')} €"
              f" @ {u.get('price')}")
        print(f"       segnale {segnale}  ·  chiesto {ue.get('price_richiesto')}"
              f"  ->  abbinato medio {ue.get('price_medio')}")
        print(f"       [{_giudizio(ue.get('scorrimento_tick'))}]")
        if r and (r.get("payload") or {}).get("approved_at"):
            print(f"       dal clic all'invio: "
                  f"{_salto(datetime.fromisoformat((r['payload']['approved_at']).replace('Z', '+00:00')).timestamp() * 1000, ue.get('t4_inviato'))}"
                  "   <-- tempo NOSTRO")
        print(f"       Betfair ha risposto in {_ms(ue.get('betfair_ms'))}   <-- bet delay, non nostro")


def main() -> None:
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    righe = _leggi("safe_strategy_trades?select=*&mode=eq.live"
                   f"&placed_at=gte.{oggi}&order=id")
    richieste = {int(r["id"]): r for r in
                 _leggi("safe_strategy_requests?select=*&order=id.desc&limit=60")}
    uscite = {int(x["closes_trade_id"]): x for x in righe if x.get("closes_trade_id")}
    for t in righe:
        if t.get("closes_trade_id"):
            continue
        if str(t.get("status")) == "error":
            continue
        racconta(t, uscite, richieste)
    print("=" * 78)


if __name__ == "__main__":
    main()
