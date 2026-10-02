"""FALSIFICAZIONE della riconciliazione dei tradotti (02/10/2026).

Per ogni mutazione: rimette il difetto (o rompe un pezzo della correzione) nel file vero,
lancia i test nuovi, PRETENDE il rosso, ripristina il file byte per byte e lo verifica.
Alla fine rilancia i test sull'albero ripristinato e pretende il verde.

Uso, dalla radice del repo (interprete del principale con percorso assoluto):
    <python> AUDIT_2026-10-02/falsifica_riconciliazione.py
Scrive il referto in ``AUDIT_2026-10-02/falsifica_riconciliazione_out.txt``.
Non si interrompe a meta': il ripristino sta in un ``finally``. ASCII-only.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(RADICE, "AUDIT_2026-10-02", "falsifica_riconciliazione_out.txt")
TEST = [
    "Betfair/stream/tests/test_riconciliazione_tradotti_2026_10_02.py",
    "Betfair/omega/tests/test_riconciliazione_tradotti_omega_2026_10_02.py",
    "Betfair/safe_strategy/tests/test_riconciliazione_tradotti_safe_2026_10_02.py",
]

OS_ = "Betfair/omega/omega_service.py"
OM_ = "Betfair/omega/omega_market.py"
BS_ = "Betfair/safe_strategy/bot_service.py"
EX_ = "Betfair/safe_strategy/execution.py"
LB_ = "Betfair/stream/live_order_build.py"
LOW_ = "Betfair/stream/live_order_worker.py"
BC_ = "Betfair/stream/backtest/banco_comune.py"

# (sigla, difetto, file, vecchio, nuovo)
MUTAZIONI = [
    # ---------------------------------------------------------------- D1 Omega
    ("D1-a", "adozione per mercato senza l'impronta dell'equivalente (difetto D1)", OS_,
     "and str(o.get(\"bet_id\")) not in noti and impronta_equivalente(tr, o)}",
     "and False}"),
    ("D1-b", "stato per bet_id del ripiego canale letto col VERO (difetto D1)", OS_,
     "    state = X.nei_termini_della_riga(tr, state)\n    pulita = _riga_senza_riconciliazione(tr)",
     "    pulita = _riga_senza_riconciliazione(tr)"),
    ("D1-c", "evento intermedio: la dichiarazione del runner non si salva", OS_,
     "    X.ricorda_tradotto(meta, ev)\n    campi: dict[str, Any] = {\"meta\": meta}",
     "    campi: dict[str, Any] = {\"meta\": meta}"),
    ("D1-d", "evento terminale: la dichiarazione del runner non si salva", OS_,
     "    X.ricorda_tradotto(pulita[\"meta\"], ev)\n    matched = float(ev.get(\"size_matched\") or 0.0)",
     "    matched = float(ev.get(\"size_matched\") or 0.0)"),
    ("D1-e", "specchio della coda letto col VERO (_mirror_fill)", OS_,
     "        src = X.nei_termini_della_riga(tr, src)",
     "        src = src"),
    ("D1-f", "coda live oltre la deadline: stato per bet_id letto col VERO", OS_,
     "            state = X.nei_termini_della_riga(tr, state)\n            if state.get(\"found\"):",
     "            if state.get(\"found\"):"),
    # ---------------------------------------------------------------- D2 Safe
    ("D2-a", "ripiego per bet_id di Safe col VERO (difetto D2)", BS_,
     "    st = X.nei_termini_della_riga(tr, st)\n",
     ""),
    ("D2-b", "evento intermedio di Safe: la dichiarazione non si salva", BS_,
     "        X.ricorda_tradotto(nuovo, ev)\n",
     ""),
    ("D2-c", "evento terminale di Safe: la dichiarazione non si salva", BS_,
     "        X.ricorda_tradotto(pulita[\"meta\"], ev)\n",
     ""),
    ("D2-d", "annullo prima del terminale: numeri del VERO", BS_,
     "        abbinato = _r2(letto.get(\"size_matched\"))\n",
     ""),
    ("D2-e", "completamento della consapevolezza col VERO", BS_,
     "        _racconta_il_vero(db, tr, X.nei_termini_della_riga(tr, st))",
     "        _racconta_il_vero(db, tr, st)"),
    ("D2-f", "riconciliazione per ref (ordini correnti) col VERO", EX_,
     "            o = nei_termini_della_riga(trade, o)\n            matched = float(o.get(\"size_matched\") or 0.0)",
     "            matched = float(o.get(\"size_matched\") or 0.0)"),
    ("D2-g", "la conferma per bet_id non conserva la dichiarazione", BS_,
     "                if X.ricorda_tradotto(m_rec, d.get(\"betfair\") or {}):",
     "                if False:"),
    # ---------------------------------------------------------------- D3 coda e REST
    ("D3-a", "worker: la riga di coda non si traduce (difetto D3)", LOW_,
     "    if not (isinstance(params, dict) and params.get(PARAM_EQUIVALENTE)):\n        return None",
     "    return None"),
    ("D3-b", "Safe non chiede l'equivalente alla coda", EX_,
     "            equivalente_ammesso=equivalente_ammesso,\n",
     "            equivalente_ammesso=False,\n"),
    ("D3-c", "rifiuto in casa anche con l'equivalente possibile (difetto D3)", EX_,
     "    if submin_fuori_canale and size < SUBMIN_IMPORTO_FINALE_MIN - 1e-9 and not (\n"
     "            equivalente_ammesso and _equivalente_possibile(side, price, size)):",
     "    if submin_fuori_canale and size < SUBMIN_IMPORTO_FINALE_MIN - 1e-9 and not (\n"
     "            False):"),
    ("D3-d", "REST senza il verdetto col book (difetto D3)", EX_,
     "    if equivalente_ammesso:\n        tradotto_rest, rifiuto = _equivalente_rest(",
     "    if False:\n        tradotto_rest, rifiuto = _equivalente_rest("),
    ("D3-e", "REST: esito dell'equivalente non riportato ai termini chiesti", EX_,
     "    if tradotto_rest is not None:\n        # 02/10/2026 (D3): l'esito",
     "    if False:\n        # 02/10/2026 (D3): l'esito"),
    ("D3-f", "worker: l'esito della coda non riportato ai termini chiesti", LOW_,
     "        if tradotto is not None:\n            # 02/10/2026 (riconciliazione dei tradotti): l'esito della coda",
     "        if False:\n            # 02/10/2026 (riconciliazione dei tradotti): l'esito della coda"),
    ("D3-g", "book REST: piu' vincitori non esclusi", OM_,
     "            if int(nw) != 1:\n                return None\n        except (TypeError, ValueError):\n            return None\n    try:\n        ids",
     "            pass\n        except (TypeError, ValueError):\n            return None\n    try:\n        ids"),
    ("D3-h", "book REST: runner non ACTIVE non esclusi", OM_,
     "        if str(r.get(\"status\") or \"ACTIVE\").upper() != \"ACTIVE\":\n            return None\n    nw = book",
     "        pass\n    nw = book"),
    ("D3-i", "perimetro: equivalente anche per Omega/Mike/tennis", EX_,
     "                               and str(client_ref or \"\").startswith(_REF_SAFE_CALCIO)\n",
     "                               and True\n"),
    ("D2-h", "riconciliazione: l'ordine del giro (size chiesta) col VERO", BS_,
     "                                  ordine=X.nei_termini_della_riga(\n"
     "                                      tr, per_bet.get(str(tr.get(\"bet_id\") or \"\"))))",
     "                                  ordine=per_bet.get(str(tr.get(\"bet_id\") or \"\")))"),
    ("D3-j", "worker: la chiusura tradotta non e' FILL_OR_KILL (resterebbe a riposo)", LOW_,
     "        riga[\"time_in_force\"] = \"FILL_OR_KILL\"\n",
     ""),
    ("D3-k", "perimetro: equivalente anche per le aperture sotto il minimo", EX_,
     "    equivalente_ammesso = bool(sotto_minimo_chiusura\n",
     "    equivalente_ammesso = bool(submin_fuori_canale\n"),
    ("D3-l", "perimetro: equivalente candidato anche su Risultato Esatto (coda a ogni ritento)",
     EX_, "                               and mercato_a_due_esiti_per_tipo(market_type)\n",
     "                               and True\n"),
    ("D3-m", "close_trade non passa il tipo di mercato della gamba", EX_,
     "        market_type=reserve.get(\"market_type\"),\n",
     ""),
    # ---------------------------------------------------------------- traduzione unica
    ("T-a", "impronta dell'equivalente non esatta (size)", LB_,
     "abs(s - eq.size) <= 0.005", "abs(s - eq.size) <= 5.0"),
    ("T-b", "riconoscimento dai dati senza il lato opposto", LB_,
     "    if sel_l is None or sel_l == sel_c or side_l != opposto:",
     "    if sel_l is None or sel_l == sel_c:"),
    ("T-c", "residui non scalati (fattore)", LB_,
     "                out[k] = round(float(v) * fattore, 2)",
     "                out[k] = round(float(v), 2)"),
    ("T-d", "stato per bet_id senza l'identita' dell'ordine", OM_,
     "                **_identita_ordine(o, (o.get(\"priceSize\") or {}).get(\"price\"),\n"
     "                                   (o.get(\"priceSize\") or {}).get(\"size\")),\n",
     ""),
    ("T-e", "banco: stato per bet_id senza l'identita' (gemello diverso dal vero)", BC_,
     "        \"side\": str(side).lower() if side else None,\n        \"price_requested\"",
     "        \"side\": side,\n        \"price_requested\""),
    ("T-f", "con la dichiarazione, una lettura di un'altra selezione si traduce lo stesso",
     LB_,
     "        if sel_l is not None and sel_l != _sel_int(mand.get(\"selection_id\")):\n"
     "            return None\n",
     ""),
]


def _py() -> str:
    return sys.executable


def _pytest() -> "tuple[int, str]":
    t0 = time.monotonic()
    p = subprocess.run([_py(), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x", *TEST],
                       cwd=RADICE, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    righe = [r for r in (p.stdout + p.stderr).splitlines()
             if r.startswith(("FAILED", "ERROR")) or " passed" in r or " failed" in r]
    return p.returncode, f"{' | '.join(righe[-3:])} ({time.monotonic() - t0:.1f} s)"


def main() -> int:
    out = []
    rc0, r0 = _pytest()
    out.append(f"BASE (albero corretto): rc={rc0} {r0}")
    if rc0 != 0:
        out.append("ATTENZIONE: la base non e' verde, falsificazione non significativa")
    rosse = 0
    for sigla, difetto, rel, vecchio, nuovo in MUTAZIONI:
        path = os.path.join(RADICE, rel)
        with open(path, "rb") as f:
            originale = f.read()
        testo = originale.decode("utf-8")
        if testo.count(vecchio) == 0 and "\r\n" in testo:
            # copia di lavoro con fine riga CRLF (autocrlf): stessa ancora in CRLF
            vecchio = vecchio.replace("\n", "\r\n")
            nuovo = nuovo.replace("\n", "\r\n")
        n = testo.count(vecchio)
        if n != 1:
            out.append(f"{sigla} ANCORA NON TROVATA ({n} occorrenze) in {rel}: {difetto}")
            continue
        try:
            with open(path, "wb") as f:
                f.write(testo.replace(vecchio, nuovo).encode("utf-8"))
            rc, riepilogo = _pytest()
        finally:
            with open(path, "wb") as f:
                f.write(originale)
        with open(path, "rb") as f:
            ok_ripristino = f.read() == originale
        esito = "ROSSA" if rc != 0 else "SOPRAVVISSUTA"
        rosse += rc != 0
        out.append(f"{sigla} {esito} [{rel}] {difetto} -> {riepilogo}"
                   f"{'' if ok_ripristino else ' !!! RIPRISTINO FALLITO'}")
    rc1, r1 = _pytest()
    out.append(f"DOPO IL RIPRISTINO: rc={rc1} {r1}")
    out.append(f"TOTALE: {rosse} rosse su {len(MUTAZIONI)}")
    testo = "\n".join(out) + "\n"
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(testo)
    print(testo)
    return 0 if (rosse == len(MUTAZIONI) and rc0 == 0 and rc1 == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
