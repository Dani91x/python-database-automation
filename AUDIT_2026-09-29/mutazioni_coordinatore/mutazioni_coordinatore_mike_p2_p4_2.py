"""Mutazioni del COORDINATORE sui pacchetti P2 (pre-partita) e P4 blocco 2
(conti e dati) di Mike.

Ogni mutazione rompe UN punto del codice nuovo: i test devono diventare rossi.
Ripristino da copia in memoria con controllo dell'hash. Si lancia dalla radice
del worktree di verifica.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

PY = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.venv\Scripts\python.exe"
ENG = "Betfair/mike/engine.py"
CER = "Betfair/mike/certificazione.py"
SER = "Betfair/mike/service.py"
DB = "Betfair/mike/db.py"
TEST = ["Betfair/mike"]

NULLA = b"(lambda *_a, **_k: None)("

MUT: List[Tuple[str, str, bytes, bytes]] = [
    # ------------------------------------------------------------------ P2
    ("Z1 al fischio: piatto anche con una banca ancora in volo", ENG,
     b"            if abs(w_ko - l_ko) < _FLAT_EPS and lay_in_volo(ctx, MARKET_OU35, SEL_UNDER) is None:",
     b"            if abs(w_ko - l_ko) < _FLAT_EPS:"),
    ("Z2 ultimo ingresso anche con l'interruttore spento", ENG,
     b'        if snap.now >= last_entry_at and params["last_entry_persist"] and params["pre_enabled"]:',
     b'        if snap.now >= last_entry_at and params["pre_enabled"]:'),
    ("Z3 ultimo ingresso valutato anche col pre-partita spento", ENG,
     b'        if snap.now >= last_entry_at and params["last_entry_persist"] and params["pre_enabled"]:',
     b'        if snap.now >= last_entry_at and params["last_entry_persist"]:'),
    ("Z4 ultimo ingresso valutato piu' volte", ENG,
     b"    if any(float(l.placed_at or 0.0) >= last_entry_at for l in ctx.legs):",
     b"    if False:"),
    ("Z5 prezzi non vivi al segno = rinuncia", ENG,
     b"    if not snap.order_fresh:\n        return Decision(\"WATCH\", [], \"ultimo ingresso: feed stantio",
     b"    if False:\n        return Decision(\"WATCH\", [], \"ultimo ingresso: feed stantio"),
    ("Z6 mercato sospeso al segno = rinuncia", ENG,
     b"    if bk is not None and price_ok(bk.best_back) and not operabile(bk) and riaprira(bk):",
     b"    if False:"),
    ("Z7 ultimo ingresso senza i controlli d'ingresso", ENG,
     b"    why = _entry_guard(ctx, snap, dict(params, pre_last_entry_min=0))",
     b"    why = None"),
    ("Z8 il veto non blocca piu' l'ultimo ingresso", ENG,
     b"        if veto[\"esito\"] == \"veto\":\n            return Decision(\"HOLD\", [], \"ultimo ingresso: %s, non entro\"",
     b"        if False:\n            return Decision(\"HOLD\", [], \"ultimo ingresso: %s, non entro\""),
    ("Z9 dopo il segno senza posizione si torna a cercare ingressi", ENG,
     b"            if st == \"HOLD\":\n                return Decision(\"HOLD\", _cancel_live(ctx),",
     b"            if False:\n                return Decision(\"HOLD\", _cancel_live(ctx),"),
    ("Z10 al segno con la posizione aperta non si passa in attesa", ENG,
     b"            if st == \"PRE_OPEN\":\n                # M2.4: al segno Mike HA la posizione",
     b"            if False:\n                # M2.4: al segno Mike HA la posizione"),
    ("Z11 al fischio non si aspetta l'esito della banca", ENG,
     b"    if banca is not None:\n        return Decision(\"LIVE_KO_GREEN\", acts, \"al fischio: attendo",
     b"    if False:\n        return Decision(\"LIVE_KO_GREEN\", acts, \"al fischio: attendo"),
    ("Z12 al fischio la banca a esito ignoto non si aspetta", ENG,
     b"                  and (l.is_live or l.needs_reconcile)), None)",
     b"                  and l.is_live), None)"),
    ("Z13 banca abbinata al fischio: si apre lo stesso il gioco", ENG,
     b"    if uscita is None:\n        w_ko, l_ko = exposure(ctx.legs, MARKET_OU35, SEL_UNDER)\n        if abs(w_ko - l_ko) < _FLAT_EPS:",
     b"    if uscita is None:\n        w_ko, l_ko = exposure(ctx.legs, MARKET_OU35, SEL_UNDER)\n        if False:"),
    ("Z14 banca abbinata dopo il segno: si torna a cercare ingressi", ENG,
     b"                if st == \"HOLD\":\n                    # M2.4: banca abbinata negli ultimi minuti",
     b"                if False:\n                    # M2.4: banca abbinata negli ultimi minuti"),
    ("Z15 dopo il segno la banca mancante non si rimette", ENG,
     b"    if st in (\"PRE_OPEN\", \"HOLD\"):",
     b"    if st == \"PRE_OPEN\":"),
    ("Z16 dopo un veto gia' scattato si entra lo stesso", ENG,
     b"    if veto_u35_acceso(params) and isinstance(ctx.veto_u35, dict):\n        return Decision(\"HOLD\", [], \"ultimo ingresso: non si entra dopo il veto",
     b"    if False:\n        return Decision(\"HOLD\", [], \"ultimo ingresso: non si entra dopo il veto"),
    ("C1 banco D3 muto", CER,
     b"    return abs(w - l) >= 0.01",
     b"    return False"),
    ("C2 banco B6: secondo ingresso dopo il segno non visto", CER,
     b"    if dopo:\n        return f\"secondo ingresso dopo il segno",
     b"    if False:\n        return f\"secondo ingresso dopo il segno"),
    ("C3 banco B6: ingresso dopo il segno non da piatto non visto", CER,
     b"    if ctx.state != \"WATCH\":\n        return f\"ingresso dopo il segno da",
     b"    if False:\n        return f\"ingresso dopo il segno da"),
    # ------------------------------------------------------------ P4 blocco 2
    ("W1 lettura fallita torna lista vuota", DB,
     b"        logger.warning(\"[mike.db] lettura feed KO: %s\", str(ex)[:160])\n        return None",
     b"        logger.warning(\"[mike.db] lettura feed KO: %s\", str(ex)[:160])\n        return []"),
    ("W2 lettura fallita: si butta l'ultima lista buona", SER,
     b"            righe_db = list(_CACHE_FEED.valore or [])\n            _avvisa_feed_non_letto(db, now_ts)",
     b"            righe_db = []\n            _avvisa_feed_non_letto(db, now_ts)"),
    ("W3 lettura fallita: parte l'orologio della riga assente", SER,
     b"    if row is None and _feed_non_letto():",
     b"    if False:"),
    ("W4a riga assente: ordini non seguiti", SER,
     b"        # M8.8 (29/09): senza riga non si decide, ma gli ordini si seguono\n        _sorveglia_senza_dati(",
     b"        # M8.8 (29/09): senza riga non si decide, ma gli ordini si seguono\n        " + NULLA),
    ("W4b dati incompleti: ordini non seguiti", SER,
     b"        # seguono lo stesso (fill, scadenze, riconciliazione, posizione di conto)\n        _sorveglia_senza_dati(",
     b"        # seguono lo stesso (fill, scadenze, riconciliazione, posizione di conto)\n        " + NULLA),
    ("W4c snapshot non costruibile: ordini non seguiti", SER,
     b"        # M8.8 (29/09): niente snapshot = niente decisione, ordini seguiti lo stesso\n        _sorveglia_senza_dati(",
     b"        # M8.8 (29/09): niente snapshot = niente decisione, ordini seguiti lo stesso\n        " + NULLA),
    ("W5 regolata senza punteggio: righe non regolate", SER,
     b"                    ok0 = _settle_trades(db, ev[\"event_id\"], ctx,",
     b"                    ok0 = (lambda *_a, **_k: True)(db, ev[\"event_id\"], ctx,"),
    ("W5b regolata senza punteggio: righe non scritte, nessun nuovo tentativo", SER,
     b"                    if not ok0 and _retry_settle_rows(db, ev[\"event_id\"], ctx, extra, now_ts):",
     b"                    if False:"),
    ("W6 regolamento non determinabile: righe non marcate", SER,
     b"                da_regolare = _marca_righe_non_regolate(db, ev[\"event_id\"])",
     b"                da_regolare = []"),
    ("W7 cumulativi: paper e live sommati", DB,
     b"    if mode is not None:\n        righe = [r for r in righe if str(r.get(\"mode\") or \"paper\").lower() == mode]",
     b"    if False:\n        righe = [r for r in righe if str(r.get(\"mode\") or \"paper\").lower() == mode]"),
    ("W8 cumulativi: memoria unica per le due modalita'", DB,
     b"    chiave_v, chiave_ts = (\"v\", \"ts\") if mode is None else (f\"v:{mode}\", f\"ts:{mode}\")",
     b"    chiave_v, chiave_ts = (\"v\", \"ts\")"),
    ("W9 dati incompleti: cio' che la sorveglianza cambia non si salva", SER,
     b"        elif _signature({**ev, **_row_from_ctx(ev, ctx, extra)}) != before_sig:",
     b"        elif False:"),
    ("W10 lettura fallita: avviso a ogni giro", SER,
     b"    if _FEED_KO.get(\"dal\"):\n        return\n",
     b"    if False:\n        return\n"),
    ("W11 il guasto del feed sopravvive al riavvio del banco", SER,
     b"                      \"_FEED_KO\")   # M8.7 (29/09)",
     b"                      )   # M8.7 (29/09)"),
    ("W12 la ripresa della lettura non si dice e il guasto non si chiude", SER,
     b"            _avvisa_feed_non_letto(db, now_ts, ripreso=True)",
     b"            pass"),
    ("W13 senza dati, in paper: esiti del runner non letti", SER,
     b"    now_ts = now.timestamp()\n    if mode == \"paper\":\n        _segui_ordini_paper_su_runner(",
     b"    now_ts = now.timestamp()\n    if False:\n        _segui_ordini_paper_su_runner("),
    ("W14 senza dati: posizione di conto non sorvegliata", SER,
     b"                                      params=params, market=market)\n    _sorveglia_posizione_di_conto(db=db, market=market, ctx=ctx, ev=ev, extra=extra,\n                                  params=params, mode=mode, now_ts=now_ts, cache=cache)\n    _sorveglia_gambe(",
     b"                                      params=params, market=market)\n    " + NULLA + b"db=db, market=market, ctx=ctx, ev=ev, extra=extra,\n                                  params=params, mode=mode, now_ts=now_ts, cache=cache)\n    _sorveglia_gambe("),
]


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def suite() -> Tuple[bool, str]:
    r = subprocess.run([PY, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider", "-x"],
                       capture_output=True, text=True, timeout=1800)
    righe = [x for x in (r.stdout or "").splitlines() if x.strip()]
    coda = righe[-1:] or ["?"]
    primo = next((x for x in righe if x.startswith("FAILED") or x.startswith("ERROR")), "")
    return r.returncode == 0, (coda[0] + ("  | " + primo[:150] if primo else ""))


def main() -> int:
    solo = set(sys.argv[1:])
    ok, coda = suite()
    print("BASE (senza mutazioni): %s  %s" % ("VERDE" if ok else "ROSSA", coda), flush=True)
    if not ok:
        return 2
    vive = 0
    fatte = 0
    for nome, f, prima, dopo in MUT:
        if solo and nome.split()[0] not in solo:
            continue
        fatte += 1
        p = Path(f)
        orig = p.read_bytes()
        crlf = b"\r\n" in orig
        a = prima.replace(b"\n", b"\r\n") if crlf else prima
        d = dopo.replace(b"\n", b"\r\n") if crlf else dopo
        n = orig.count(a)
        if n != 1:
            print("%-72s ANCORA NON UNICA (%d)" % (nome, n), flush=True)
            vive += 1
            continue
        try:
            p.write_bytes(orig.replace(a, d))
            verde, coda = suite()
        finally:
            p.write_bytes(orig)
        assert md5(p.read_bytes()) == md5(orig)
        errore = "error" in coda and "failed" not in coda
        print("%-72s %s  %s" % (nome, "SOPRAVVISSUTA" if verde else
                                ("ERRORE DI RACCOLTA" if errore else "rossa"), coda), flush=True)
        vive += 1 if (verde or errore) else 0
    print("mutazioni sopravvissute o non valide: %d su %d" % (vive, fatte))
    return 0


if __name__ == "__main__":
    sys.exit(main())
