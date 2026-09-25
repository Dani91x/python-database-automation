"""Falsificazione dei test F0 (tempi_ordine, 25/09): ogni mutazione deve far
diventare ROSSO almeno un test nuovo; il file mutato si ripristina byte per byte
(mai ``git checkout``). Uso, dalla radice del repo:

    python AUDIT_2026-09-25/f0_tempi/falsifica_f0.py
"""
import os
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEST = "Betfair/stream/tests/test_tempi_ordine_f0_2026_09_25.py"

M = [
    ("M1 tratto al contrario (_d = a - b)", "Betfair/stream/tempi_ordine.py",
     "    return b - a\n", "    return a - b\n"),
    ("M2 interruttore ignorato nel worker calcio", "Betfair/stream/live_order_worker.py",
     'def _tempi_on() -> bool:\n    return (os.getenv("LIVE_TEMPI_ORDINE") or "1").strip() != "0"',
     'def _tempi_on() -> bool:\n    return True'),
    ("M3 interruttore ignorato nel worker tennis",
     "Betfair/stream/tennis_live/tennis_live_order_worker.py",
     '    return (os.getenv("LIVE_TEMPI_ORDINE") or "1").strip() != "0"',
     '    return True'),
    ("M4 interruttore ignorato nello specchio (process_orders)",
     "Betfair/stream/engine/live_trading_strategy.py",
     '    return (os.getenv("LIVE_TEMPI_ORDINE") or "1").strip() != "0"',
     '    return True'),
    ("M5 cache senza tetto", "Betfair/stream/tempi_ordine.py",
     "    while len(_voci) > MAX_VOCI:", "    while False:"),
    ("M6 TTL ignorato", "Betfair/stream/tempi_ordine.py",
     "        if adesso - voce[\"creata_mono\"] <= TTL_S:", "        if True:"),
    ("M7 strada del canale sbagliata", "Betfair/stream/live_order_worker.py",
     '_cust_ref(rid), "canale", t=_t_tempi', '_cust_ref(rid), "coda", t=_t_tempi'),
    ("M8 strada tennis sbagliata (canale 47332)",
     "Betfair/stream/tennis_live/tennis_live_order_worker.py",
     'cust_ref, "tennis", via="canale"', 'cust_ref, "canale", via="canale"'),
    ("M9 la misura aggiunge IO al giro della coda", "Betfair/stream/live_order_worker.py",
     "        if _t_tempi is not None: _TEMPI.nuovo(  # noqa: E701 - F0 misura (solo RAM)\n"
     "            _cust_ref(rid), \"coda\"",
     "        if _t_tempi is not None: sb.table(\"betfair_live_audit\").select(\"*\").execute()\n"
     "        if _t_tempi is not None: _TEMPI.nuovo(  # noqa: E701 - F0 misura (solo RAM)\n"
     "            _cust_ref(rid), \"coda\""),
    ("M10 percentile a rango piu' vicino", "Betfair/stream/tools/leggi_tempi_ordine.py",
     "    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)", "    return float(xs[round(pos)])"),
    ("M11 aggancio place tolto (_place_or_raise)", "Betfair/stream/live_order_worker.py",
     "    if _tempi_on(): _TEMPI.place(order)  # noqa: E701 - F0: istante \"place\" (solo misura)\n",
     ""),
    ("M12 aggancio stream tolto (process_orders)", "Betfair/stream/engine/live_trading_strategy.py",
     "        if _tempi_on(): _TEMPI.osserva(orders)  # noqa: E701 - F0: risposta/abbinamento "
     "(misura)\n", ""),
    ("M13 place_ms misurato dalla ricezione invece che dalla presa",
     "Betfair/stream/tempi_ordine.py",
     "                           else (o[\"place_mono\"] - presa_mono) * 1000.0)",
     "                           else (o[\"place_mono\"] - voce[\"ricezione_mono\"]) * 1000.0)"),
    ("M14 abbinato sempre dall'osservazione locale", "Betfair/stream/tempi_ordine.py",
     "        if o[\"matched_bf\"] is not None and o[\"placed_bf\"] is not None:",
     "        if False:"),
    ("M15 aggancio presa tolto (_dispatch calcio)", "Betfair/stream/live_order_worker.py",
     "    if _tempi_on(): _TEMPI.presa(_cust_ref(request_row.get(\"id\")))  "
     "# noqa: E701 - F0 misura\n", ""),
    ("M16 motore: decisione non passata", "Betfair/stream/motore_ordini.py",
     "decisione_ms=piano[\"creato_ms\"]", "decisione_ms=None"),
    ("M17 orologi misti non dichiarati", "Betfair/stream/tempi_ordine.py",
     "        misti.append(f\"ricezione:{voce['invio_orologio']}/pc\")", "        pass"),
    ("M18 reconcile tennis senza aggancio", "Betfair/stream/tennis_live/tennis_live_order_worker.py",
     "            if _tempi_on(): _TEMPI.osserva((order,))  # noqa: E701 - F0: abbinamento "
     "(misura)\n", ""),
]


def main() -> int:
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
               SUPABASE_KEY="x")
    esiti = []
    for nome, rel, prima, dopo in M:
        p = os.path.join(RADICE, rel)
        with open(p, "rb") as fh:
            orig = fh.read()
        testo = orig.decode("utf-8")
        crlf = "\r\n" in testo
        a = prima.replace("\n", "\r\n") if crlf else prima
        b = dopo.replace("\n", "\r\n") if crlf else dopo
        n = testo.count(a)
        if n != 1:
            esiti.append((nome, f"MUTAZIONE NON APPLICABILE (trovate {n})"))
            continue
        try:
            with open(p, "wb") as fh:
                fh.write(testo.replace(a, b).encode("utf-8"))
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                TEST], cwd=RADICE, env=env, capture_output=True, text=True,
                               timeout=600)
            righe = [ln for ln in r.stdout.splitlines() if ln.strip()]
            falliti = [ln.split("::")[-1].split(" ")[0] for ln in righe
                       if ln.startswith("FAILED")]
            esiti.append((nome, ("ROSSO " if r.returncode != 0 else "VERDE (!) ")
                          + (righe[-1] if righe else "") + " | " + ", ".join(falliti)))
        finally:
            with open(p, "wb") as fh:
                fh.write(orig)
    for nome, e in esiti:
        print(f"{nome}: {e}")
    return 0 if all(e.startswith("ROSSO") for _, e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
