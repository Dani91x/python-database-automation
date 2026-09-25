"""Prova a secco dello step "Prerequisiti" di .github/workflows/hazard_atlas.yml.

Estrae lo script python dallo YAML e lo esegue contro un FINTO PostgREST locale
(mai il DB vero) in 4 scenari: tabelle assenti (404 PGRST205), hazard_atlas
vuota (bootstrap mai fatto), tutto pronto, errore 500.
Uso: python AUDIT_2026-09-25/prova_preflight_atlante.py  (dalla radice del repo)
"""
import json
import os
import subprocess
import sys
import textwrap
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import yaml

wf = yaml.safe_load(open(".github/workflows/hazard_atlas.yml", encoding="utf-8"))
step = [s for s in wf["jobs"]["hazard-atlas"]["steps"] if s["name"].startswith("Prerequisiti")][0]
code = textwrap.dedent(step["run"].split("<<'PY'\n", 1)[1].rsplit("PY", 1)[0])
compile(code, "preflight", "exec")
MODE = {"m": None}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        m = MODE["m"]
        if m == "404":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"code":"PGRST205","message":"Could not find the table"}')
            return
        if m == "500":
            self.send_response(500)
            self.end_headers()
            return
        body = b"[]"
        if self.path.startswith("/rest/v1/hazard_atlas?") and m == "ok":
            body = json.dumps([{"watermark_event_id": 123}]).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
env = dict(os.environ, SUPABASE_URL=f"http://127.0.0.1:{srv.server_port}", SUPABASE_SERVICE_ROLE_KEY="x")
for m in ("404", "vuota", "ok", "500"):
    MODE["m"] = m
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    err = r.stderr.strip().splitlines()[-1][:120] if r.stderr.strip() else ""
    print(f"{m:6} exit={r.returncode} out={r.stdout.strip()[:170]!r} err={err!r}")
print("if del job:", wf["jobs"]["hazard-atlas"]["if"])
print("trigger:", wf[True])
