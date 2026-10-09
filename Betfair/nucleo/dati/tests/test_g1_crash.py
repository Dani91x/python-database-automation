"""W1-G1 - prove di crash con un processo figlio VERO ucciso con ``os._exit`` (07 par. 6.1, G par. 5 n.1).

1. Lo scrittore muore a meta' (``os._exit`` da un timer mentre il ciclo scrive nei tre regimi):
   ogni riga CONFERMATA (``alla_conferma``) c'e' dopo la riapertura, nei tre regimi; poi il
   postino la porta al cloud UNA volta sola.
2. Il postino muore fra la risposta del cloud e la conferma locale (la riga e' nel cloud ma
   l'outbox non lo sa): al riavvio la riga si rimanda e il cloud NON la duplica (uid/versione).
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pytest

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

from Betfair.nucleo.dati.archivio import ArchivioLocale  # noqa: E402
from Betfair.nucleo.dati.postino import PostinoLocale  # noqa: E402
from Betfair.nucleo.dati.tests.test_g1_finti import SPEC, CloudProva, PostgrestFinto  # noqa: E402

RADICE = Path(__file__).resolve().parents[4]
SPAZIO = uuid.UUID("6f1c3b4e-8a51-4c7a-9a5e-0d2f3c4b5a69")

FIGLIO_SCRITTORE = r'''
import os, sys, threading, time, uuid
from pathlib import Path
from Betfair.nucleo.dati.archivio import ArchivioLocale
from Betfair.nucleo.dati.tests.test_g1_finti import SPEC, riga_attivita, riga_ordine
base, ritardo = Path(sys.argv[1]), float(sys.argv[2])
modo = sys.argv[3] if len(sys.argv) > 3 else "timer"
SPAZIO = uuid.UUID("6f1c3b4e-8a51-4c7a-9a5e-0d2f3c4b5a69")
def ack(n):
    sys.stdout.write("ack %d\n" % n); sys.stdout.flush()
a = ArchivioLocale("prova", SPEC, base=base, alla_conferma=ack).apri()
if modo == "timer":
    threading.Timer(ritardo, lambda: os._exit(1)).start()
i = 0
while True:
    if modo == "conferma" and i == 1500:
        # raffica, poi barriera di durabilita' e morte SUBITO: deterministico (nessun caso fortunato)
        if not a.conferma(60):
            os._exit(2)
        ack(1500)                       # cio' che il chiamante SA durevole (la barriera e' tornata vera)
        os._exit(1)
    k = i // 3
    if i % 3 == 0:
        a.scrivi("mike_activity", riga_attivita(k, uid=str(uuid.uuid5(SPAZIO, str(k)))))
    elif i % 3 == 1:
        a.scrivi("betfair_live_orders", riga_ordine("r%d" % k, "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
    else:
        a.scrivi("live_follow", {"event_id": "e%d" % k, "home_name": "A", "away_name": "B", "status": "PENDING",
                                 "open_date": "2026-10-09T18:00:00+00:00", "updated_at": "2026-10-09T10:00:00+00:00"})
    i += 1
    if i % 200 == 0:
        time.sleep(0.001)
'''


def _identita(n: int) -> tuple[str, str]:
    """La scrittura numero ``n`` (1-based) del figlio: (regime, chiave)."""
    i = n - 1
    k = i // 3
    return [("log", str(uuid.uuid5(SPAZIO, str(k)))), ("denaro", f"r{k}"), ("vivo", f"e{k}")][i % 3]


@pytest.mark.parametrize("ritardo, modo", [(0.25, "timer"), (0.6, "timer"), (0.0, "conferma")])
def test_scrittore_ucciso_a_meta_zero_confermati_persi(tmp_path: Path, ritardo: float, modo: str) -> None:
    """``timer``: morte in un istante qualunque mentre il ciclo scrive (a meta' davvero);
    ``conferma``: raffica di 1.500 righe, barriera ``conferma()``, morte subito dopo: senza
    flush la coda del buffer di Python si perde SEMPRE (prova deterministica, M01)."""
    r = subprocess.run([sys.executable, "-c", FIGLIO_SCRITTORE, str(tmp_path), str(ritardo), modo], cwd=RADICE,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 1, r.stderr[-2000:]                                   # morto con os._exit(1)
    ack = max(int(x.split()[1]) for x in r.stdout.splitlines() if x.startswith("ack "))
    assert ack > 300, "il figlio deve aver confermato abbastanza scritture per essere una prova"
    if modo == "conferma":
        assert ack == 1500
    cart = tmp_path / "prova"
    denaro = {json.loads(j)["client_order_ref"] for (j,) in
              sqlite3.connect(cart / "denaro.sqlite3").execute("SELECT json FROM righe")}
    vivo = {json.loads(j)["event_id"] for (j,) in sqlite3.connect(cart / "vivo.sqlite3").execute("SELECT json FROM righe")}
    log_righe = [json.loads(x) for f in sorted((cart / "log").glob("*.jsonl"))
                 for x in f.read_bytes().split(b"\n") if x.strip()]
    log = {x["r"]["uid"] for x in log_righe}
    assert len(log) == len(log_righe)                                             # nessun doppione locale
    trovati = {"log": log, "denaro": denaro, "vivo": vivo}
    persi = [n for n in range(1, ack + 1) if _identita(n)[1] not in trovati[_identita(n)[0]]]
    assert persi == [], f"confermate e perse: {persi[:10]} (ack={ack})"
    # riapertura (eventuale riga troncata riparata) e consegna: ogni riga UNA volta nel cloud
    srv = PostgrestFinto()
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        p = PostinoLocale(a, CloudProva(srv))
        for _ in range(200):                                                # R10: tetto di giri
            if not p.drena(500).consegnate:
                break
        assert p.stato().in_coda == 0 and p.stato().dead_letter == 0
        uid_cloud = [x["uid"] for x in srv.tabelle["mike_activity"].righe]
        assert len(uid_cloud) == len(set(uid_cloud)) == len(log)
        assert {x["client_order_ref"] for x in srv.tabelle["betfair_live_orders"].righe} == denaro
        assert {x["event_id"] for x in srv.tabelle["live_follow"].righe} == vivo
    finally:
        a.chiudi()


FIGLIO_POSTINO = r'''
import json, os, sys
from pathlib import Path
from Betfair.nucleo.dati.archivio import ArchivioLocale
from Betfair.nucleo.dati.postino import PostinoLocale
from Betfair.nucleo.dati.tests.test_g1_finti import SPEC, CloudProva, PostgrestFinto
base, stato_cloud = Path(sys.argv[1]), Path(sys.argv[2])
class Persistente(PostgrestFinto):
    def consegna(self, *a):
        esiti = super().consegna(*a)
        dump = {n: t.righe for n, t in self.tabelle.items()}
        dump["__versioni__"] = self.versioni          # il cloud tiene anche public.postino_versioni
        with open(stato_cloud, "w") as f:
            json.dump(dump, f); f.flush(); os.fsync(f.fileno())
        return esiti
a = ArchivioLocale("prova", SPEC, base=base).apri()
def muori(*_a, **_k):
    os._exit(7)                     # il cloud ha applicato, la conferma locale non arriva
a.chiudi_voci = muori
a.chiudi_log = muori
PostinoLocale(a, CloudProva(Persistente())).drena(500)
os._exit(0)
'''


def test_postino_ucciso_fra_risposta_e_conferma_zero_duplicati(tmp_path: Path) -> None:
    a = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    for i in range(20):
        a.scrivi("mike_activity", {"kind": "giro", "payload": {"i": i}, "event_id": "1"})
    for i in range(5):
        a.scrivi("betfair_live_orders", {"mode": "paper", "client_order_ref": f"r{i}", "market_id": "1.2",
                                         "selection_id": 1, "side": "back", "price": 2.0, "size": 2.0,
                                         "status": "EXECUTABLE", "updated_at": "2026-10-09T10:00:00+00:00"})
    assert a.conferma()
    a.chiudi()
    stato_cloud = tmp_path / "cloud.json"
    r = subprocess.run([sys.executable, "-c", FIGLIO_POSTINO, str(tmp_path), str(stato_cloud)], cwd=RADICE,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 7, r.stderr[-2000:]
    dump: Dict[str, Any] = json.loads(stato_cloud.read_text())
    srv = PostgrestFinto()
    srv.versioni = dump.pop("__versioni__")
    for nome, righe in dump.items():
        srv.tabelle[nome].righe = righe
        srv.tabelle[nome].prossimo_id = len(righe) + 1
    presenti = len(srv.tabelle["mike_activity"].righe) + len(srv.tabelle["betfair_live_orders"].righe)
    assert presenti >= 5                                                         # almeno un blocco era arrivato
    b = ArchivioLocale("prova", SPEC, base=tmp_path).apri()
    try:
        p = PostinoLocale(b, CloudProva(srv))
        assert p.stato().in_coda == 25                                           # l'outbox non sapeva nulla
        for _ in range(200):                                                # R10: tetto di giri
            if not p.drena(500).consegnate:
                break
        assert len(srv.tabelle["mike_activity"].righe) == 20                     # 0 duplicati
        assert len(srv.tabelle["betfair_live_orders"].righe) == 5
        assert p.contatori["ignorate"] == presenti
    finally:
        b.chiudi()



# ---------------------------------------------------------------------------
# C1 del revisore: SIGKILL casuali su archivio + postino + riconciliazione + pulizia insieme
# ---------------------------------------------------------------------------
FIGLIO_SIGKILL = r"""
import json, os, sys, threading, time, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9"); os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")
from Betfair.nucleo.dati.archivio import ArchivioLocale
from Betfair.nucleo.dati.postino import PostinoLocale
from Betfair.nucleo.dati.tests.test_g1_finti import SPEC, CloudProva, PostgrestFinto

base, cloudfile, ackfile, inc, modo = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5]
SPAZIO = uuid.UUID("6f1c3b4e-8a51-4c7a-9a5e-0d2f3c4b5a69")


class Persistente(PostgrestFinto):
    def __init__(self):
        super().__init__()
        if cloudfile.exists():
            d = json.loads(cloudfile.read_text())
            for n, righe in d["righe"].items():
                self.tabelle[n].righe = righe
                self.tabelle[n].prossimo_id = d["id"][n]
            self.versioni = d["versioni"]

    def consegna(self, *a):
        esiti = super().consegna(*a)
        d = {"righe": {n: t.righe for n, t in self.tabelle.items()}, "id": {n: t.prossimo_id for n, t in self.tabelle.items()},
             "versioni": self.versioni}
        tmp = cloudfile.with_suffix(".tmp")
        tmp.write_text(json.dumps(d))
        os.replace(tmp, cloudfile)
        return esiti


srv = Persistente()
a = ArchivioLocale("prova", SPEC, base=base, checkpoint_ogni_s=0.2, pulizia_ogni_s=1e9).apri()
p = PostinoLocale(a, CloudProva(srv))
p.avvia(intervallo_s=0.02, max_righe=50, ora_riconciliazione_utc=None)

_ultimo = [datetime.now(timezone.utc)]
def ts():
    n = datetime.now(timezone.utc)
    _ultimo[0] = max(n, _ultimo[0] + timedelta(microseconds=1))
    return _ultimo[0].isoformat()

def manutenzione():
    while True:
        time.sleep(0.15)
        try:
            oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            p.riconcilia_giorno(oggi, ["mike_activity", "betfair_live_orders", "live_follow"])
            a.pulisci(adesso_ms=int(time.time() * 1000) + 5 * 86_400_000)
        except Exception as exc:
            sys.stderr.write("manutenzione: %r\n" % (exc,))

if modo == "finale":
    # finestra ADATTIVA: si drena finche' la coda scende; ci si ferma solo se non scende per
    # FERMO_S secondi (cosi' la prova e' rossa solo per una perdita vera, mai per la lentezza)
    FERMO_S = float(os.environ.get("G1_FERMO_S", "60"))
    minimo, ultimo_calo = None, time.monotonic()
    while True:
        st = p.stato()
        if st.in_coda == 0:
            break
        if minimo is None or st.in_coda < minimo:
            minimo, ultimo_calo = st.in_coda, time.monotonic()
        elif time.monotonic() - ultimo_calo > FERMO_S:
            break
        time.sleep(0.1)
    print(json.dumps({"in_coda": p.stato().in_coda, "dead": len(a.dead_letter()), "segn": [s["tipo"] for s in a.segnalazioni()]}))
    p.ferma(); a.chiudi()
    sys.exit(0)

threading.Thread(target=manutenzione, daemon=True).start()
print("pronto", flush=True)
k = 0
pend = []
while True:
    uid = str(uuid.uuid5(SPAZIO, f"{inc}-{k}"))
    a.scrivi("mike_activity", {"kind": "giro", "payload": {"k": k}, "event_id": "1", "uid": uid})
    ref = f"r{inc}-{k % 20}"
    st = "S%06d" % k
    a.scrivi("betfair_live_orders", {"mode": "paper", "client_order_ref": ref, "market_id": "1.2", "selection_id": 1,
                                     "side": "back", "price": 2.0, "size": 2.0, "status": st, "updated_at": ts()})
    ev = f"e{inc}-{k % 7}"
    a.scrivi("live_follow", {"event_id": ev, "home_name": "A", "away_name": "B", "status": st,
                             "open_date": "2026-10-09T18:00:00+00:00", "updated_at": ts()})
    pend.append({"uid": uid, "ref": ref, "st": st, "ev": ev})
    k += 1
    if k % 25 == 0:
        if a.conferma(30):
            with open(ackfile, "a") as f:
                for r in pend:
                    f.write(json.dumps(r) + "\n")
                f.flush(); os.fsync(f.fileno())
        pend = []
        time.sleep(0.002)
"""


def test_sigkill_casuali_nessuna_riga_confermata_persa(tmp_path: Path) -> None:
    """C1 del revisore (asserzioni invariate). Unica differenza dichiarata: l'attesa a caso
    (0,4-2,2 s) parte quando il figlio e' PRONTO (archivio aperto, postino avviato): l'avvio
    del figlio (import di supabase) qui dura ~2,3 s e con l'attesa dal lancio i figli
    morivano prima di scrivere, e la prova passava a vuoto."""
    import random
    base, cloud, ack = tmp_path / "base", tmp_path / "cloud.json", tmp_path / "ack.jsonl"
    rnd = random.Random(int(os.environ.get("G1_SEME", "7")))
    cicli = int(os.environ.get("G1_CICLI", "6"))
    for c in range(cicli):
        p = subprocess.Popen([sys.executable, "-c", FIGLIO_SIGKILL, str(base), str(cloud), str(ack), f"c{c}", "scrivi"],
                             cwd=RADICE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert p.stdout.readline().strip() == "pronto"
        time.sleep(rnd.uniform(0.4, 2.2))
        p.kill()                                                         # SIGKILL (TerminateProcess su Windows)
        err = p.communicate()[1]
        assert "Traceback" not in err, err[-1500:]
    r = subprocess.run([sys.executable, "-c", FIGLIO_SIGKILL, str(base), str(cloud), str(ack), "fin", "finale"],
                       cwd=RADICE, capture_output=True, text=True, timeout=3600)  # il figlio si ferma da solo (fermo 60 s)
    esito = json.loads(r.stdout.strip().splitlines()[-1])
    assert esito["in_coda"] == 0 and esito["dead"] == 0, esito
    d = json.loads(cloud.read_text())["righe"]
    uids = [x["uid"] for x in d["mike_activity"]]
    assert len(uids) == len(set(uids)), "duplicati nel cloud"
    ordini = {x["client_order_ref"]: x["status"] for x in d["betfair_live_orders"]}
    eventi = {x["event_id"]: x["status"] for x in d["live_follow"]}
    acked = [json.loads(x) for x in ack.read_text().splitlines()]
    assert len(acked) > 500, len(acked)
    mancanti_uid = [r["uid"] for r in acked if r["uid"] not in set(uids)]
    mancanti_ref = [r["ref"] for r in acked if r["ref"] not in ordini or ordini[r["ref"]] < r["st"]]
    mancanti_ev = [r["ev"] for r in acked if r["ev"] not in eventi or eventi[r["ev"]] < r["st"]]
    print("confermate", len(acked), "uid mancanti", len(mancanti_uid), "ref mancanti/indietro", len(mancanti_ref),
          "ev", len(mancanti_ev))
    assert not mancanti_uid and not mancanti_ref and not mancanti_ev
