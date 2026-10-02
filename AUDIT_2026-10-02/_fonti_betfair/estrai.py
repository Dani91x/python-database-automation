"""Estrae il testo delle pagine ufficiali Betfair scaricate (Confluence REST,
expand=body.view) per citarle nel referto. Fonte ESTERNA al repo, scaricata il
02/10/2026 da betfair-developer-docs.atlassian.net."""
import html
import json
import os
import re

QUI = os.path.dirname(os.path.abspath(__file__))
for pid in ("2687396", "2687455", "2687517", "2687478"):
    with open(os.path.join(QUI, f"bf_{pid}.json"), encoding="utf-8") as f:
        d = json.load(f)
    t = d["body"]["view"]["value"]
    t = re.sub(r"<(br|/p|/tr|/li|/h\d)[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    with open(os.path.join(QUI, f"bf_{pid}.txt"), "w", encoding="utf-8") as f:
        f.write(t)
    print(pid, d.get("title"), len(t))
