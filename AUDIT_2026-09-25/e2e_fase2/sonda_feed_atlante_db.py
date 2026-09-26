"""sonda_feed_atlante_db.py - lettore PostgREST in SOLA LETTURA (solo GET) per il referto
ADMIN26_FEED_ATLANTE (e2e fase 2, 26/09). Nessun POST/PATCH/DELETE: il metodo e' fisso a GET
e ogni richiesta porta select/limit espliciti. Legge SUPABASE_URL e la chiave dal .env SENZA
modificarlo e senza stamparla.
Uso: python sonda_feed_atlante_db.py "tabella?select=...&limit=N"   (stampa JSON)
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


def get(path, timeout=30, extra_headers=None):
    """GET PostgREST. Ritorna (status, body, ms)."""
    assert "select=" in path and "limit=" in path, "select e limit espliciti obbligatori"
    h = {"apikey": _KEY, "Authorization": f"Bearer {_KEY}"}
    h.update(extra_headers or {})
    req = urllib.request.Request(f"{_URL}/rest/v1/{path}", headers=h, method="GET")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode()), round((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300], round((time.time() - t0) * 1000)


if __name__ == "__main__":
    st, body, ms = get(sys.argv[1])
    print(st, ms, "ms")
    print(json.dumps(body, indent=1, default=str, ensure_ascii=False)[:int(sys.argv[2]) if len(sys.argv) > 2 else 20000])
