"""Sezione 3 - genera le tabelle markdown del documento: matrice tabella -> file che leggono/scrivono e matrice RPC.

Legge uscite/s03_matrice_tabelle.tsv e s03_matrice_rpc.tsv (prodotti da s03_db.py, AST + regex, sola lettura).
Aggiunge la colonna 'frequenza misurata' SOLO per le tabelle presenti in SCHEMI_BOT/sistema/MISURE_2026-10-02.md,
con la riga della fonte (finestra 60 s del 02/10/2026, servizio: chiamate/min). Nessun'altra frequenza e' scritta.
Uscite: uscite/g01_tabelle_db.md, uscite/g01_rpc.md
Uso: python g01_tabelle_md.py
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402

M = "MISURE:"
# tabella -> elenco (servizio, metodo, chiamate/min nella finestra 60 s, riga di MISURE_2026-10-02.md)
FREQ = {
    "betfair_live_order_requests": [("runner-calcio", "GET", 189, 100)],
    "betfair_live_risk_rules": [("runner-calcio", "GET", 168, 101)],
    "live_follow": [("runner-calcio", "GET", 29, 103)],
    "betfair_live_orders": [("runner-calcio", "GET", 11, 104)],
    "betfair_live_settled": [("runner-calcio", "GET", 11, 105)],
    "safe_strategy_scan": [("scanner", "POST", 68, 162), ("mike", "GET", 14, 67), ("runner-calcio", "GET", 8, 106), ("safe-bot", "GET", 5, 139), ("scanner", "GET", 1, 166)],
    "betfair_live_heartbeat": [("runner-calcio", "POST", 8, 107)],
    "safe_strategy_status": [("scanner", "POST", 5, 165), ("safe-bot", "GET", 5, 138), ("runner-calcio", "GET", 2, 108)],
    "betfair_live_account": [("runner-calcio", "POST", 2, 109)],
    "personal_watchlist": [("runner-calcio", "GET", 1, 110)],
    "mike_trades": [("mike", "GET", 116, 63)],
    "mike_control": [("mike", "GET", 58, 64), ("mike", "PATCH", 2, 69)],
    "mike_requests": [("mike", "GET", 58, 65)],
    "mike_events": [("mike", "POST", 25, 66), ("scanner", "GET", 6, 163), ("mike", "GET", 1, 71)],
    "mike_activity": [("mike", "POST", 2, 70)],
    "safe_strategy_trades": [("safe-bot", "GET", 81, 132)],
    "safe_strategy_requests": [("safe-bot", "PATCH", 53, 133), ("safe-bot", "GET", 44, 134)],
    "safe_strategy_control": [("safe-bot", "GET", 36, 135), ("safe-bot", "PATCH", 19, 137)],
    "safe_strategy_opportunities": [("safe-bot", "POST", 4, 140), ("safe-bot", "DELETE", 1, 143)],
    "omega_events": [("safe-bot", "GET", 1, 141)],
    "fixture_predictions": [("safe-bot", "GET", 1, 142)],
    "scalper_control": [("scalper", "GET", 18, 179)],
    "scalper_service_control": [("scalper", "GET", 18, 181)],
    "tennis_bot_control": [("tennis-bot-svc", "GET", 18, 189)],
    "tennis_bot_service_control": [("tennis-bot-svc", "PATCH", 12, 190), ("tennis-bot-svc", "GET", 3, 191)],
    "tennis_live_follow": [("runner-tennis", "GET", 28, 126), ("tennis-bot-svc", "GET", 3, 192)],
    "omega_trades": [("omega", "GET", 4, 86)],
    "omega_control": [("omega", "GET", 1, 87)],
    "tennis_markets": [("tennis-odds", "DELETE+POST", "2+2 in 29,8 min", 203)],
}
FREQ_RPC = {
    "get_live_settings": "runner-calcio 123/min (MISURE:102), scalper 18/min (MISURE:180)",
    "get_safe_aggregates": "safe-bot 19/min (MISURE:136)",
    "list_bot_exposures": "scanner 6/min (MISURE:164)",
    "get_mike_aggregates": "mike 3/min (MISURE:68)",
    "get_omega_aggregates_modalita": "omega 4 in 5 min (MISURE:95)",
}
NL = chr(10)


def corto(lst: str, n: int = 3) -> str:
    if not lst:
        return "-"
    voci = [x.strip() for x in lst.split(";") if x.strip()]
    extra = ""
    for i, v in enumerate(voci):
        if v.startswith("(+"):
            extra = v
    voci = [v for v in voci if not v.startswith("(+")]
    # il formato s03 e' 'a; b; c (+N)': l'ultimo elemento porta il (+N)
    out = []
    for v in voci[:n]:
        out.append("`" + v.split(" (+")[0] + "`")
    tot = len(voci)
    m_extra = lst.rsplit("(+", 1)[1].rstrip(")") if "(+" in lst else ""
    if m_extra.isdigit():
        tot += int(m_extra)
    resto = tot - len(out)
    return ", ".join(out) + (" (+%d)" % resto if resto > 0 else "")


def n_voci(lst: str) -> int:
    if not lst:
        return 0
    voci = [x for x in lst.split(";") if x.strip()]
    n = len(voci)
    if "(+" in lst:
        t = lst.rsplit("(+", 1)[1].rstrip(") ")
        if t.isdigit():
            n += int(t)
    return n


def main() -> int:
    mat = [r.split("\t") for r in (c.USCITE / "s03_matrice_tabelle.tsv").read_text(encoding="utf-8").splitlines()]
    head, righe = mat[0], mat[1:]
    ix = {h: i for i, h in enumerate(head)}
    righe = [r for r in righe if int(r[ix["n_prod"]]) + int(r[ix["n_frontend"]]) > 0]
    righe.sort(key=lambda r: -(int(r[ix["n_prod"]]) + int(r[ix["n_frontend"]])))
    out = ["| tabella | definita in | chiamate prod / FE | scrive (prod) | legge (prod) | FE legge / scrive | frequenza misurata 02/10 (finestra 60 s) |",
           "|---|---|---|---|---|---|---|"]
    for r in righe:
        t = r[0]
        fr = ""
        if t in FREQ:
            fr = "; ".join("%s %s %s (MISURE:%d)" % (s, mt, n, ln) for s, mt, n, ln in FREQ[t])
        defin = r[ix["definita_in"]]
        out.append("| `%s` | %s | %s / %s | %s | %s | %s / %s | %s |" % (
            t, defin if defin != "-" else "NON nei .sql tracciati", r[ix["n_prod"]], r[ix["n_frontend"]],
            corto(r[ix["prod_scrive"]]) + (" ; op?: " + corto(r[ix["prod_op_non_determinata"]], 2) if r[ix["prod_op_non_determinata"]] else ""),
            corto(r[ix["prod_legge"]]), corto(r[ix["frontend_legge"]], 2), corto(r[ix["frontend_scrive"]], 2), fr or "-"))
    c.scrivi("g01_tabelle_db.md", NL.join(out) + NL)

    rpc = [r.split("\t") for r in (c.USCITE / "s03_matrice_rpc.tsv").read_text(encoding="utf-8").splitlines()]
    h2, r2 = rpc[0], rpc[1:]
    j = {h: i for i, h in enumerate(h2)}
    r2 = [r for r in r2 if int(r[j["n_prod"]]) + int(r[j["n_frontend"]]) > 0 and not r[0].startswith("<")]
    r2.sort(key=lambda r: r[0])
    o2 = ["| RPC | definita | prod (n) | primo file prod | FE (n) | primo file FE | frequenza misurata |", "|---|---|---|---|---|---|---|"]
    for r in r2:
        o2.append("| `%s` | %s | %s | %s | %s | %s | %s |" % (
            r[0], r[j["definita_in"]] if r[j["definita_in"]] != "-" else "NON nei .sql", r[j["n_prod"]], corto(r[j["file_prod"]], 1),
            r[j["n_frontend"]], corto(r[j["file_frontend"]], 1), FREQ_RPC.get(r[0], "-")))
    c.scrivi("g01_rpc.md", NL.join(o2) + NL)
    print(len(righe), "tabelle;", len(r2), "RPC")
    return 0


if __name__ == "__main__":
    sys.exit(main())
