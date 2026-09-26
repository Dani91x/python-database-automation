import json, os
D = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\AUDIT_2026-09-25\e2e_fase2\accensione"
for f in ["A3_safe_prima", "A3_safe_dopo_base", "A3_safe_dopo_esatto", "A3_safe_dopo_punta", "A3_safe_dopo_tennis"]:
    d = json.load(open(os.path.join(D, f + ".json"), encoding="utf8"))
    s = d["safe_strategy_control"]
    pe = (s.get("stats") or {}).get("params_effective")
    print(f, d["ts"], s["status"], s["mode"], s["params"].get("variants"), s["updated_at"], "eff:", pe.get("variants") if isinstance(pe, dict) else None)
d = json.load(open(os.path.join(D, "A3_safe_esito.json"), encoding="utf8"))
for r in d["rpc_registro"]:
    a = r["args"] or {}
    b = {k: (v if k != "p_params" else {kk: (v or {}).get(kk) for kk in ("variants", "strategy_modes")}) for k, v in a.items()}
    print(r["ts"], r["rpc"], r["esito"], json.dumps(b)[:400])
print("\n".join(d["passi"]))
