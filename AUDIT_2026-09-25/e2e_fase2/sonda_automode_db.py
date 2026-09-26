"""sonda_automode_db.py - lettore PostgREST in SOLA LETTURA (solo GET) per il referto
ADMIN26_AUTOMODE_SAFE (e2e fase 2, 26/09). Metodo fisso GET, select e limit espliciti
obbligatori. Legge SUPABASE_URL e la chiave dal .env SENZA modificarlo e senza stamparla.
Uso: python sonda_automode_db.py "tabella?select=...&limit=N" [maxchars]
"""
import json, sys, time, urllib.request, urllib.error
from pathlib import Path

_RADICE = Path(__file__).resolve().parents[2]


def _env():
    env = {}
    for line in (_RADICE / ".env").read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_SERVICE_ROLE_KEY"]


_URL, _KEY = _env()


def get(path, timeout=30):
    assert "select=" in path and "limit=" in path, "select e limit espliciti obbligatori"
    h = {"apikey": _KEY, "Authorization": f"Bearer {_KEY}"}
    req = urllib.request.Request(f"{_URL}/rest/v1/{path}", headers=h, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


if __name__ == "__main__":
    try:
        body = get(sys.argv[1])
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode()[:400]); sys.exit(1)
    print(json.dumps(body, indent=1, default=str, ensure_ascii=False)[:int(sys.argv[2]) if len(sys.argv) > 2 else 20000])
