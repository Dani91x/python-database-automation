#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""verifica_margine_2026_09_12 -- il modello di Omega batte il mercato?

SOLA LETTURA. Nessuna scrittura sul DB, nessun servizio avviato, nessun ordine.
Rieseguibile: ogni esecuzione rifa' i conti sullo stato corrente, quindi ha senso
rilanciarlo man mano che le partite in paper si accumulano.

Perche' esiste
--------------
Il 12/09 e' emerso che chiudere una posizione A MERCATO e' NEUTRO per definizione:
si blocca esattamente la stima del mercato (verificato su 4 casi veri, scarto
0,00 EUR). Ne segue che ogni logica di uscita "a modello" -- green-up di Omega,
uscita in perdita di Mike -- crea valore SOLO SE il modello batte il mercato.

Quella non e' una domanda di opinione: e' misurabile. Questo strumento la misura,
e soprattutto dichiara quando i dati NON bastano ancora per rispondere, invece di
produrre un numero che sembra una risposta.

Cosa stampa
-----------
  1. CALIBRAZIONE  -- eventi attesi dal modello, dal mercato e dalla tabella
     empirica, contro quelli davvero accaduti. Piu' Brier e log-loss.
     ATTENZIONE: con ZERO eventi positivi il confronto e' vuoto (il Brier premia
     chi prevede la probabilita' piu' bassa, non chi ci prende): lo strumento lo
     dice e non classifica un vincitore.
  2. MARGINE       -- quanto margine il modello dichiara, quanto vale per
     scommessa, e quante scommesse servono per distinguerlo dal caso.
  3. VARIANZA      -- lo stesso margine a quote di lay diverse: il valore atteso
     non cambia, cambia solo quanto ci vuole per dimostrarlo.

Uso
---
    python -m Betfair.tools.verifica_margine_2026_09_12

Output ASCII (console Windows cp1252).
"""
from __future__ import annotations

import math
import os
import statistics
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# soglia standard: intervallo di confidenza al 95%
Z95 = 1.96


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


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


class Apertura:
    """Una gamba di APERTURA regolata, con quello che il modello sapeva."""

    __slots__ = ("p_model", "p_mkt", "p_emp", "esito", "liability", "stake", "prezzo")

    def __init__(self, p_model: float, p_mkt: float, p_emp: Optional[float],
                 esito: float, liability: float, stake: float, prezzo: float) -> None:
        self.p_model, self.p_mkt, self.p_emp = p_model, p_mkt, p_emp
        self.esito = esito            # 1 = il punteggio bancato E' uscito (lay perso)
        self.liability, self.stake, self.prezzo = liability, stake, prezzo


def carica(db: Any) -> list[Apertura]:
    """Aperture REGOLATE che portano il blocco ``meta.model``. Le gambe di
    chiusura sono escluse: hanno un ``closes_trade_id`` e non sono decisioni di
    selezione."""
    rows = db.table("omega_trades").select(
        "id,price,size,status,meta,closes_trade_id"
    ).in_("status", ["won", "lost"]).execute().data or []
    out: list[Apertura] = []
    for r in rows:
        if r.get("closes_trade_id"):
            continue
        m = (r.get("meta") or {}).get("model") or {}
        pm, pi = _num(m.get("p_model")), _num(m.get("p_implied"))
        prezzo, stake = _num(r.get("price")), _num(r.get("size"))
        if pm is None or pi is None or prezzo is None or stake is None or prezzo <= 1:
            continue
        out.append(Apertura(pm, pi, _num(m.get("empirical")),
                            1.0 if r.get("status") == "lost" else 0.0,
                            stake * (prezzo - 1.0), stake, prezzo))
    return out


def _brier(dati: list[Apertura], quale: str) -> float:
    return sum((getattr(d, quale) - d.esito) ** 2 for d in dati) / len(dati)


def _logloss(dati: list[Apertura], quale: str) -> float:
    tot = 0.0
    for d in dati:
        p = min(max(getattr(d, quale), 1e-6), 1 - 1e-6)
        tot += -(d.esito * math.log(p) + (1 - d.esito) * math.log(1 - p))
    return tot / len(dati)


def _scommesse_necessarie(ev: float, sd: float) -> Optional[int]:
    """Quante scommesse perche' l'intervallo di confidenza al 95% della media
    non contenga lo zero. None se il valore atteso non e' positivo."""
    if ev <= 0 or sd <= 0:
        return None
    return int(math.ceil((Z95 * sd / ev) ** 2))


def sezione_calibrazione(dati: list[Apertura]) -> None:
    print("1. CALIBRAZIONE -- chi prevede meglio, il modello o il mercato?")
    print("-" * 68)
    n = len(dati)
    positivi = int(sum(d.esito for d in dati))
    att_mod = sum(d.p_model for d in dati)
    att_mkt = sum(d.p_mkt for d in dati)
    emp = [d.p_emp for d in dati if d.p_emp is not None]
    print("  aperture regolate col modello registrato: %d" % n)
    print()
    print("  %-26s %14s" % ("", "eventi attesi"))
    print("  %-26s %14.2f" % ("MODELLO", att_mod))
    print("  %-26s %14.2f" % ("MERCATO (de-viggato)", att_mkt))
    if emp:
        print("  %-26s %14.2f" % ("TABELLA EMPIRICA", sum(emp)))
    print("  %-26s %14d   <- realmente accaduti" % ("OSSERVATO", positivi))
    print()
    if positivi == 0:
        print("  >> NESSUN evento positivo: il confronto NON e' utilizzabile.")
        print("     Con zero eventi il Brier premia automaticamente chi prevede la")
        print("     probabilita' piu' bassa, non chi ci prende. Servono partite in cui")
        print("     il punteggio bancato ESCE davvero perche' la domanda abbia risposta.")
        return
    b_mod, b_mkt = _brier(dati, "p_model"), _brier(dati, "p_mkt")
    l_mod, l_mkt = _logloss(dati, "p_model"), _logloss(dati, "p_mkt")
    print("  %-26s %12s %12s" % ("", "Brier", "log-loss"))
    print("  %-26s %12.6f %12.5f" % ("MODELLO", b_mod, l_mod))
    print("  %-26s %12.6f %12.5f" % ("MERCATO", b_mkt, l_mkt))
    print()
    vince = "il MODELLO" if b_mod < b_mkt else "il MERCATO"
    print("  >> calibra meglio %s (Brier piu' basso)" % vince)
    if positivi < 20:
        print("     ATTENZIONE: solo %d eventi positivi. Sotto la ventina il" % positivi)
        print("     confronto resta indicativo, non una conclusione.")


def sezione_margine(dati: list[Apertura]) -> None:
    print()
    print("2. MARGINE -- quanto ne dichiara il modello, e cosa costa dimostrarlo")
    print("-" * 68)
    margini = [d.p_mkt - d.p_model for d in dati]
    evs = [(d.p_mkt - d.p_model) * d.liability for d in dati]
    med_m, med_ev = statistics.median(margini), statistics.median(evs)
    print("  margine (P mercato - P modello)")
    print("    mediano %.6f  =  %.4f punti percentuali" % (med_m, 100 * med_m))
    print("    medio   %.6f" % (sum(margini) / len(margini)))
    print()
    print("  valore atteso per scommessa = margine x liability")
    print("    mediano %+.3f EUR" % med_ev)
    print("    medio   %+.3f EUR" % (sum(evs) / len(evs)))
    print("    liability mediana %.2f EUR   stake mediano %.2f EUR"
          % (statistics.median([d.liability for d in dati]),
             statistics.median([d.stake for d in dati])))
    print()
    p = statistics.median([d.p_mkt for d in dati])
    liab = statistics.median([d.liability for d in dati])
    stake = statistics.median([d.stake for d in dati])
    sd = math.sqrt(p * (1 - p)) * (liab + stake)
    n = _scommesse_necessarie(med_ev, sd)
    print("  deviazione standard per scommessa: %.2f EUR" % sd)
    if n is None:
        print("  >> valore atteso non positivo: non c'e' margine da dimostrare.")
        return
    print("  rapporto rumore / segnale: %.0f a 1" % (sd / med_ev))
    print("  >> servono circa %s scommesse per distinguerlo dal caso (95%%)"
          % f"{n:,}".replace(",", "."))


def sezione_varianza(dati: list[Apertura]) -> None:
    """Lo stesso margine RELATIVO a quote diverse. Il punto: il valore atteso per
    scommessa non cambia, cambia solo quanto ci vuole per dimostrarlo."""
    print()
    print("3. VARIANZA -- lo stesso margine a quote di lay diverse")
    print("-" * 68)
    rel = [1.0 - (d.p_model / d.p_mkt) for d in dati if d.p_mkt > 0]
    if not rel:
        return
    r = statistics.median(rel)
    stake = statistics.median([d.stake for d in dati])
    quota_oggi = statistics.median([d.prezzo for d in dati])
    print("  margine RELATIVO mediano: il modello dice che la P vera e' il")
    print("  %.1f%% piu' bassa del prezzo. Stake fisso %.2f EUR." % (100 * r, stake))
    print()
    print("  %8s %11s %11s %12s %14s" % ("QUOTA", "liability", "EV/scomm.", "rumore/segn.", "scommesse"))
    for q in (5, 10, 20, 30, 60, 110):
        p_mkt = 1.0 / q
        p_mod = p_mkt * (1.0 - r)
        liab = stake * (q - 1)
        ev = (1 - p_mod) * stake - p_mod * liab
        sd = math.sqrt(p_mod * (1 - p_mod)) * (liab + stake)
        n = _scommesse_necessarie(ev, sd)
        segna = " <- quota mediana di oggi" if abs(q - quota_oggi) <= 8 else ""
        print("  %8d %11.2f %+11.3f %11.0f a 1 %14s%s"
              % (q, liab, ev, (sd / ev) if ev > 0 else 0,
                 f"{n:,}".replace(",", ".") if n else "n/d", segna))
    print()
    print("  >> Il valore atteso per scommessa NON cambia con la quota: cambia solo")
    print("     la varianza. Bancare basso non aggiunge margine, ma rende il margine")
    print("     DIMOSTRABILE in una frazione delle partite.")


def main() -> int:
    print()
    print("=" * 68)
    print(" OMEGA -- il modello batte il mercato? (sola lettura)")
    print("=" * 68)
    print()
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
    if not dati:
        print("  Nessuna apertura regolata porta il blocco 'meta.model'.")
        print("  Il blocco lo scrivono solo le versioni recenti del servizio:")
        print("  servono partite nuove perche' questa misura abbia dei dati.")
        return 1
    sezione_calibrazione(dati)
    sezione_margine(dati)
    sezione_varianza(dati)
    print()
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
