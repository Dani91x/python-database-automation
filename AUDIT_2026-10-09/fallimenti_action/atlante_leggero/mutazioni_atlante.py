# Falsificazione: ogni mutazione deve far diventare ROSSO almeno un test; ripristino dai byte originali.
import hashlib, subprocess, sys, re
GA = "Betfair/stream/scalper/genera_atlante.py"
SY = "Betfair/stream/scalper/hazard_atlas_sync.py"
MIG = "migrations/hazard_atlas_globale_leggero_2026-10-09.sql"
TEST = ["Betfair/stream/tests/test_atlante_globale_leggero_2026_10_09.py",
        "Betfair/stream/tests/test_genera_atlante_scrittura_ritentativi_2026_09_28.py",
        "Betfair/stream/tests/test_genera_atlante_2026_09_24.py",
        "test_fallimenti_action_2026_10_09.py"]
M = [
 ("M01 payload leggero = atlante intero", GA, 'return {k: atlas[k] for k in CHIAVI_PAYLOAD_GLOBALE if k in atlas}', 'return dict(atlas)'),
 ("M02 by_league fra le chiavi ammesse", GA, 'CHIAVI_PAYLOAD_GLOBALE: Tuple[str, ...] = ("meta", "global")', 'CHIAVI_PAYLOAD_GLOBALE: Tuple[str, ...] = ("meta", "global", "by_league")'),
 ("M03 RPC con l'atlante intero", GA, '"p_payload": leggero}', '"p_payload": atlas}'),
 ("M04 ripiego diretto con l'atlante intero", GA, '"watermark_event_id": watermark_event_id, "payload": leggero}', '"watermark_event_id": watermark_event_id, "payload": atlas}'),
 ("M05 global tolto dal payload", GA, 'CHIAVI_PAYLOAD_GLOBALE: Tuple[str, ...] = ("meta", "global")', 'CHIAVI_PAYLOAD_GLOBALE: Tuple[str, ...] = ("meta",)'),
 ("M06 assembla cambiata (MIN_H2H 3->4)", GA, 'MIN_H2H = 3 ', 'MIN_H2H = 4 '),
 ("M19 assembla cambiata (K_TEAM 12->13)", GA, "K_TEAM = 12.0 ", "K_TEAM = 13.0 "),
 ("M20 file domanda cambiato (modo)", "Betfair/stream/scalper/atlante_a_domanda.py", "atlas[\"meta\"][\"modo\"] = \"a_domanda\"", "atlas[\"meta\"][\"modo\"] = \"domanda\""),
 ("M07 scarica non riassembla il payload leggero", SY, '        if _payload_leggero(atlas):\r\n', '        if False and _payload_leggero(atlas):\r\n'),
 ("M08 scarica riassembla anche il payload intero", SY, 'and bool(atlas["meta"].get("generated_at")) and "by_league" not in atlas)', 'and bool(atlas["meta"].get("generated_at")))'),
 ("M09 scarica dimentica meta.run", SY, '    if "run" in meta:\r\n        atlas["meta"]["run"] = meta["run"]\r\n', ''),
 ("M10 scarica senza seme", SY, '    if os.path.exists(HA.ATLAS_V3_PATH):\r\n', '    if False:\r\n'),
 ("M11 scarica legge solo la prima pagina", SY, '        if len(rows) < pagina:\r\n            break\r\n', '        break\r\n'),
 ("M12 scarica in ordine decrescente", SY, '"order": "league_id.asc"', '"order": "league_id.desc"'),
 ("M13 scarica senza filigrana", SY, 'watermark=int(wm) if wm is not None else None, seme=seme)', 'watermark=None, seme=seme)'),
 ("M14 scarica accetta lettura monca/vuota", SY, '    if not stati or len(stati) < attese:\r\n', '    if False:\r\n'),
 ("M15 scarica con la data di adesso", SY, 'generated_at=str(meta["generated_at"])', 'generated_at="2026-10-09T09:00:00+00:00"'),
 ("M16 migrazione senza WHERE (non idempotente)", MIG, " WHERE (payload - 'meta' - 'global') <> '{}'::jsonb;", ";"),
 ("M17 migrazione tiene anche h2h_hint", MIG, "jsonb_build_object('meta', payload -> 'meta')\r\n", "jsonb_build_object('meta', payload -> 'meta', 'h2h_hint', payload -> 'h2h_hint')\r\n"),
 ("M18 migrazione con VACUUM", MIG, "COMMIT;\r\n", "COMMIT;\r\nVACUUM FULL public.hazard_atlas;\r\n"),
]
orig = {p: open(p, "rb").read() for p in (GA, SY, MIG, "Betfair/stream/scalper/atlante_a_domanda.py")}
sha = {p: hashlib.sha256(b).hexdigest() for p, b in orig.items()}
esiti = []
for nome, p, a, b in M:
    t = orig[p].decode("utf-8")
    assert t.count(a) == 1, (nome, t.count(a))
    open(p, "wb").write(t.replace(a, b).encode("utf-8"))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x", "--no-header", "-rf"] + TEST,
                           capture_output=True, text=True)
        rossi = [l.split("::")[-1].split(" ")[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
        esiti.append((nome, r.returncode != 0, rossi))
    finally:
        open(p, "wb").write(orig[p])
for p in orig:
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == sha[p], p
for nome, rosso, rossi in esiti:
    print(("ROSSO" if rosso else "VERDE!!"), "|", nome, "|", ", ".join(rossi))
print("ripristino sha256 OK:", {p: s[:12] for p, s in sha.items()})
print(sum(1 for e in esiti if e[1]), "su", len(esiti), "rosse")
