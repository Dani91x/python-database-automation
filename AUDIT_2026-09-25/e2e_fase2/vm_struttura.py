"""mostra la struttura di un file vm_*.json (chiavi, tipi, lunghezze) e alcuni blocchi. Uso: vm_struttura.py <file> [chiave ...]"""
import json, sys
d = json.load(open(sys.argv[1], encoding="utf8"))
vm = d["vm"]
print("rpc lette:", d["rpc_lette"], "bloccate:", d["bloccate"])
for k, v in vm.items():
    t = type(v).__name__
    ln = len(v) if isinstance(v, (list, dict)) else ""
    print(f"  {k}: {t} {ln}")
for k in sys.argv[2:]:
    print("=====", k)
    print(json.dumps(vm.get(k), ensure_ascii=False, indent=1)[:6000])
