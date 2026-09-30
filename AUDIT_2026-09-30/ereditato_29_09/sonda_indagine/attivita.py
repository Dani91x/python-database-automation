import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
kinds = set(sys.argv[2].split(",")) if len(sys.argv) > 2 and sys.argv[2] != "-" else None
print("FIRME:", json.dumps(d.get("firme"), default=str)[:1500])
print("TRADES:")
for t in d["trades"]:
    print("  ", {k: t.get(k) for k in ("id", "role", "side", "market_id", "selection_id", "price",
                                       "size", "status", "matched_size", "avg_price", "reason",
                                       "created_at", "close_reason")})
print("ATTIVITA:")
for a in d["attivita"]:
    if kinds and a["kind"] not in kinds:
        continue
    p = a["payload"] or {}
    s = json.dumps(p, default=str)
    print(a["kind"], s[:420])
