"""
READ-ONLY schema explorer for the Supabase project.
NESSUNA scrittura / cancellazione: usa solo l'endpoint OpenAPI di PostgREST
(GET /) per elencare tabelle+colonne, e SELECT count per i conteggi righe.

Output: _AUDIT_2026_05/schema_report.json  +  stampa riassuntiva.
"""
from __future__ import annotations
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY  # noqa: E402
from db_client import get_supabase_client  # noqa: E402

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def fetch_openapi() -> dict:
    """PostgREST espone uno spec OpenAPI alla root: lista tabelle+colonne+tipi."""
    url = SUPABASE_URL.rstrip("/") + "/rest/v1/"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Accept": "application/openapi+json",
    }
    r = requests.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()


def row_count(client, table: str) -> int | None:
    """Conteggio esatto righe via head request (read-only)."""
    try:
        resp = client.table(table).select("*", count="exact").limit(1).execute()
        return resp.count
    except Exception as exc:  # noqa: BLE001
        return f"ERR: {exc}"  # type: ignore[return-value]


def main() -> None:
    print(f"Connessione a {SUPABASE_URL[:24]}****")
    spec = fetch_openapi()
    defs = spec.get("definitions") or spec.get("components", {}).get("schemas", {})
    tables = sorted(defs.keys())
    print(f"Tabelle/viste esposte: {len(tables)}")

    client = get_supabase_client()
    report: dict = {"tables": {}}

    for t in tables:
        props = defs[t].get("properties", {})
        cols = {}
        for cname, cmeta in props.items():
            cols[cname] = {
                "type": cmeta.get("format") or cmeta.get("type"),
                "desc": cmeta.get("description", ""),
            }
        cnt = row_count(client, t)
        report["tables"][t] = {"row_count": cnt, "n_cols": len(cols), "columns": cols}
        print(f"  {t:42s} rows={str(cnt):>10}  cols={len(cols)}")

    out_path = os.path.join(OUT_DIR, "schema_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nScritto {out_path}")


if __name__ == "__main__":
    main()
