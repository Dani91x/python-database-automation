"""sonda_fase3_db.py — admin-26 fase 3: letture PostgREST in SOLA LETTURA (GET).
Uso: python sonda_fase3_db.py <tabella|rpc:nome> [querystring] [json_args_rpc]
Solo GET: select su tabelle, RPC via GET (solo funzioni STABLE/IMMUTABLE rispondono a GET).
"""
import json, os, sys, urllib.request, urllib.parse
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
env = {}
for l in open(os.path.join(ROOT, '.env'), encoding='utf8'):
    l = l.strip()
    if l and not l.startswith('#') and '=' in l:
        k, v = l.split('=', 1); env[k.strip()] = v.strip().strip('"').strip("'")
URL, KEY = env['SUPABASE_URL'], env['SUPABASE_SERVICE_ROLE_KEY']
def get(path, qs=''):
    req = urllib.request.Request(f"{URL}/rest/v1/{path}{('?' + qs) if qs else ''}", method='GET',
        headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf8'))
def rpc_get(name, args=None):
    qs = urllib.parse.urlencode({k: (json.dumps(v) if isinstance(v, (dict, list)) else ('' if v is None else v)) for k, v in (args or {}).items()})
    return get(f"rpc/{name}", qs)
if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1]
    if a.startswith('rpc:'):
        print(json.dumps(rpc_get(a[4:], json.loads(sys.argv[2]) if len(sys.argv) > 2 else None), ensure_ascii=False, indent=1, default=str))
    else:
        print(json.dumps(get(a, sys.argv[2] if len(sys.argv) > 2 else ''), ensure_ascii=False, indent=1, default=str))
