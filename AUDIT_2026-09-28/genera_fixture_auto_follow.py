"""Genera ``frontend/src/lib/__fixtures__/autoFollowFinti.json`` dallo stato VERO
di ``auto_follow.AutoFollow.stato()`` (flumine vero, nessuna rete, nessun DB).

Uso (dalla radice):  python AUDIT_2026-09-28/genera_fixture_auto_follow.py
"""
import json
import os
import sys

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RADICE)
sys.path.insert(0, os.path.join(RADICE, "Betfair", "stream", "tests"))
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_KEY", "x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

import test_frammenti_mercato_2026_09_28 as T  # noqa: E402


def scenario(max_conn: int, partite: int) -> dict:
    fw, _r, _l = T._framework(["1.1"])
    T._collega(T._market_streams(fw)[0])
    g, _o, _a = T._gestore(max_conn=max_conn)
    af, pub = T._auto(fw, g, T._feed(partite))
    af.giro()
    return json.loads(json.dumps(pub[-1], default=str))


def main() -> None:
    pieno = scenario(1, 50)
    pieno["partite_fuori"] = pieno["partite_fuori"][:3]
    out = {
        "_nota": ("stato VERO di auto_follow.AutoFollow.stato() (topic 'auto_follow' e "
                  "hello.auto_follow del runner calcio 47331), generato da "
                  "AUDIT_2026-09-28/genera_fixture_auto_follow.py; chiavi verificate da "
                  "test_frammenti_mercato_2026_09_28.py::test_fixture_ui_ha_le_chiavi_vere"),
        "capacita_esaurita": pieno,
        "tutte_seguite": scenario(3, 67),
    }
    dest = os.path.join(RADICE, "frontend", "src", "lib", "__fixtures__", "autoFollowFinti.json")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(out, indent=2, ensure_ascii=True) + "\n")
    print(dest)


if __name__ == "__main__":
    main()
