"""Helper e2e fase 1: fotografie, confronto BYTE PER BYTE e ripristino ESATTO delle tabelle di controllo.

- foto <nome>        : SOLA LETTURA (GET PostgREST, service role). Salva e2e_fase1/<nome>.json con le
                       righe intere (parsed) e il TESTO GREZZO di ogni riga di controllo come lo emette
                       PostgREST (serve al confronto byte per byte e al ripristino esatto).
- confronta <a> <b>  : diff dei valori + diff del testo grezzo riga per riga. Stampa JSON {n_valori, n_grezzo, ...}.
- ripristina <nome>  : SCRITTURA REVERSIBILE (permesso dell'utente, solo tabelle di controllo dei bot):
                       PATCH di ogni riga di controllo col suo testo grezzo della fotografia <nome>; cancella
                       SOLO le righe create dal test (omega_daily_goal del giorno se assente nella foto,
                       tennis_bot_control dell'evento di prova 36063889, scalper_control 'E2E%').
Credenziali lette dal .env del checkout principale (mai stampate).
"""
import json, os, sys, datetime, urllib.request, urllib.parse

W = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
WT = W + r"\.claude\worktrees\agent-ae6b4a3f84a6ad933"
OUT = WT + r"\AUDIT_2026-09-25\e2e_fase1"
env = {}
for line in open(W + r"\.env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
URL = env["SUPABASE_URL"].rstrip("/")
KEY = env["SUPABASE_SERVICE_ROLE_KEY"]
H = {"apikey": KEY, "Authorization": "Bearer " + KEY, "Accept": "application/json"}

EVENTO_TENNIS_TEST = "36063889"


def _req(method, path, body=None, extra=None):
    h = dict(H)
    if extra:
        h.update(extra)
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(URL + "/rest/v1/" + path, headers=h, data=data, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def get(path):
    return json.loads(_req("GET", path))


def get_raw_obj(path):
    return _req("GET", path, extra={"Accept": "application/vnd.pgrst.object+json"})


# tabella -> (colonna chiave, [valori chiave])
CONTROL = {
    "omega_control": ("id", ["1"]),
    "mike_control": ("id", ["1"]),
    "safe_strategy_control": ("id", ["1"]),
    "tennis_bot_service_control": ("bot_key", ["tennis_flb", "tennis_pro", "tennis_scalper", "tennis_swing"]),
    "scalper_service_control": ("id", ["1"]),
    "betfair_live_settings": ("id", ["1"]),
}
ATTIVI = "in.(requested,arming,armed,running,stopping)"
QUEUES = [
    ("safe_strategy_requests", "proposed,pending,processing"),
    ("omega_manual_requests", "proposed,pending,processing"),
    ("mike_requests", "pending,processing"),
    ("tennis_live_order_queue", "pending,processing"),
    ("betfair_live_order_requests", "pending,processing"),
]


def foto(name=None):
    f = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(), "sql_equivalente": {}, "grezzo": {}}
    for t, (kc, keys) in CONTROL.items():
        f[t] = get("%s?select=*&order=%s" % (t, kc))
        f["sql_equivalente"][t] = "select * from public.%s order by %s;" % (t, kc)
        for k in keys:
            f["grezzo"]["%s:%s" % (t, k)] = get_raw_obj("%s?select=*&%s=eq.%s" % (t, kc, k))
    f["tennis_bot_control_attive"] = get("tennis_bot_control?select=*&status=" + ATTIVI)
    f["scalper_control_attive"] = get("scalper_control?select=*&status=" + ATTIVI)
    f["sql_equivalente"]["righe_attive"] = (
        "select * from tennis_bot_control / scalper_control where status in "
        "('requested','arming','armed','running','stopping');")
    f["code_aperte"] = {t: get("%s?select=id,status&status=in.(%s)" % (t, st)) for t, st in QUEUES}
    f["sql_equivalente"]["code_aperte"] = "select id,status from <coda> where status in (<stati aperti>);"
    f["tennis_live_follow_ultimi"] = get(
        "tennis_live_follow?select=event_id,status,origine,updated_at&order=updated_at.desc&limit=5")
    f["tennis_live_follow_n"] = len(get("tennis_live_follow?select=event_id"))
    f["live_follow_non_chiuse"] = get("live_follow?select=event_id,status,origine,updated_at&status=neq.CLOSED")
    f["betfair_live_audit_ultimi"] = get("betfair_live_audit?select=*&order=id.desc&limit=3")
    # tabelle toccate di lato dalle RPC dei percorsi (effetti collaterali da ripristinare)
    f["omega_daily_goal_ultimi"] = get("omega_daily_goal?select=*&order=day.desc&limit=3")
    f["max_id_code"] = {t: (get("%s?select=id&order=id.desc&limit=1" % t) or [{"id": None}])[0]["id"]
                        for t in ("safe_strategy_requests", "omega_manual_requests", "mike_requests",
                                  "tennis_live_order_queue", "betfair_live_order_requests")}
    f["righe_usate_da_P28_P29"] = {
        "safe_strategy_requests_256": get("safe_strategy_requests?select=*&id=eq.256"),
        "omega_manual_requests_48": get("omega_manual_requests?select=*&id=eq.48"),
        "safe_strategy_requests_257_proposed": get("safe_strategy_requests?select=*&id=eq.257"),
        "omega_manual_requests_49_proposed": get("omega_manual_requests?select=*&id=eq.49"),
    }
    f["tennis_bot_control_evento_test"] = get("tennis_bot_control?select=*&event_id=eq." + EVENTO_TENNIS_TEST)
    f["tennis_bot_control_n"] = len(get("tennis_bot_control?select=event_id"))
    f["scalper_control_n"] = len(get("scalper_control?select=event_id"))
    f["scalper_control_evento_test"] = get("scalper_control?select=*&event_id=like.E2E*")
    if name:
        with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8") as fh:
            json.dump(f, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return f


def load(name):
    return json.load(open(os.path.join(OUT, name + ".json"), encoding="utf-8"))


def diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in ("ts", "sql_equivalente", "grezzo"):
                continue
            if k not in a:
                out.append((path + "/" + k, "<assente>", b[k]))
            elif k not in b:
                out.append((path + "/" + k, a[k], "<assente>"))
            else:
                out += diff(a[k], b[k], path + "/" + k)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, path + "[%d]" % i)
    elif a != b or type(a) != type(b):
        out.append((path, a, b))
    return out


def confronta(na, nb):
    a, b = load(na), load(nb)
    d = diff(a, b)
    grezzo = [k for k in sorted(set(a["grezzo"]) | set(b["grezzo"])) if a["grezzo"].get(k) != b["grezzo"].get(k)]
    return {"a": na, "b": nb, "n_valori": len(d), "n_grezzo": len(grezzo),
            "valori": [{"campo": p, "prima": x, "dopo": y} for p, x, y in d],
            "grezzo_diversi": grezzo}


def ripristina(name):
    f = load(name)
    fatte = []
    for chiave, raw in f["grezzo"].items():
        t, k = chiave.split(":", 1)
        kc = CONTROL[t][0]
        attuale = get_raw_obj("%s?select=*&%s=eq.%s" % (t, kc, k))
        if attuale != raw:
            _req("PATCH", "%s?%s=eq.%s" % (t, kc, urllib.parse.quote(k)), body=raw,
                 extra={"Content-Type": "application/json", "Prefer": "return=minimal"})
            fatte.append("PATCH " + chiave)
    # omega_daily_goal: la riga del giorno creata dal test (omega_snapshot_daily_goal)
    giorni_foto = {r["day"]: r for r in f["omega_daily_goal_ultimi"]}
    for r in get("omega_daily_goal?select=*&order=day.desc&limit=3"):
        if r["day"] not in giorni_foto and r["day"] > max(giorni_foto):
            _req("DELETE", "omega_daily_goal?day=eq." + r["day"], extra={"Prefer": "return=minimal"})
            fatte.append("DELETE omega_daily_goal " + r["day"])
        elif r["day"] in giorni_foto and r != giorni_foto[r["day"]]:
            _req("PATCH", "omega_daily_goal?day=eq." + r["day"], body=json.dumps(giorni_foto[r["day"]]),
                 extra={"Content-Type": "application/json", "Prefer": "return=minimal"})
            fatte.append("PATCH omega_daily_goal " + r["day"])
    # righe per partita create dal test
    bot_foto = {r["bot_key"] for r in f["tennis_bot_control_evento_test"]}
    for r in get("tennis_bot_control?select=bot_key&event_id=eq." + EVENTO_TENNIS_TEST):
        if r["bot_key"] not in bot_foto:
            _req("DELETE", "tennis_bot_control?event_id=eq.%s&bot_key=eq.%s" % (EVENTO_TENNIS_TEST, r["bot_key"]),
                 extra={"Prefer": "return=minimal"})
            fatte.append("DELETE tennis_bot_control %s/%s" % (EVENTO_TENNIS_TEST, r["bot_key"]))
    for r in get("scalper_control?select=event_id&event_id=like.E2E*"):
        _req("DELETE", "scalper_control?event_id=eq." + urllib.parse.quote(r["event_id"]),
             extra={"Prefer": "return=minimal"})
        fatte.append("DELETE scalper_control " + r["event_id"])
    return fatte


def imposta(tabella, chiave, valore, campi_json):
    """Scrittura mirata e reversibile di una riga di controllo (preparazione di un percorso)."""
    kc = CONTROL[tabella][0]
    _req("PATCH", "%s?%s=eq.%s" % (tabella, kc, urllib.parse.quote(valore)), body=campi_json,
         extra={"Content-Type": "application/json", "Prefer": "return=minimal"})
    return ["PATCH %s:%s %s" % (tabella, valore, campi_json)]


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "foto":
        foto(sys.argv[2])
        print(json.dumps({"salvata": sys.argv[2]}))
    elif cmd == "confronta":
        print(json.dumps(confronta(sys.argv[2], sys.argv[3]), ensure_ascii=False, default=str))
    elif cmd == "ripristina":
        print(json.dumps({"ripristino": ripristina(sys.argv[2])}, ensure_ascii=False))
    elif cmd == "imposta":
        print(json.dumps({"imposta": imposta(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])}))
