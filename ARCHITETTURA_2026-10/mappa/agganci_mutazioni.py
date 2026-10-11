"""Falsificazione dei test degli AGGANCI M-2 dopo M-1 (11/10/2026): ogni mutazione
DEVE far diventare rosso il test indicato; dopo ogni mutazione il file torna con
sha256 identico (controllato qui e stampato).

Agganci: (1) ocm dello stream ordini in "Salute" (tee di M-1, ``auth.py``),
(2) latenza esito -> bot (``esiti_ordini_canale.py``), (3) ``invio`` della strada
canale (``live_order_worker.py``). Test: ``Betfair/monitor/tests/test_agganci_m1_m2_2026_10_11.py``.

Uso (dalla radice del repo):  python ARCHITETTURA_2026-10/mappa/agganci_mutazioni.py [radice]
Esce con 0 solo se TUTTE le mutazioni sono rosse e tutti i ripristini identici.
Prima e dopo: ``git status`` pulito sui file elencati.
"""
import hashlib
import os
import subprocess
import sys

RADICE = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
T = ["Betfair/monitor/tests/test_agganci_m1_m2_2026_10_11.py"]
RO = "Betfair/monitor/registratore_ordini.py"
SO = "Betfair/monitor/sonde.py"
EO = "Betfair/stream/esiti_ordini_canale.py"
WK = "Betfair/stream/live_order_worker.py"
TO = "Betfair/stream/tempi_ordine.py"

MUT = [
    # -- aggancio 1: ocm dello stream ordini in Salute
    ("G1 auth: solo il registratore aggancia", "Betfair/stream/auth.py",
     "    if _ro.attivo() or _mon.ATTIVO: _ro.aggancia_api_client(client)",
     "    if _ro.attivo(): _ro.aggancia_api_client(client)",
     "test_ocm_solo_monitor or test_aggancio_auth"),
    ("G2 aggancio: monitor da solo non aggancia", RO,
     "    if not registra and not _mon.ATTIVO:\n        return client\n",
     "    if not registra:\n        return client\n",
     "test_ocm_solo_monitor"),
    ("G3 REST avvolta anche col solo monitor", RO,
     '        betting = getattr(client, "betting", None) if registra else None\n',
     '        betting = getattr(client, "betting", None)\n',
     "test_ocm_solo_monitor"),
    ("G4 scrittore creato anche a registratore spento", RO,
     "        scr = scrittore() if registra else None\n",
     "        scr = scrittore()\n",
     "test_ocm_solo_monitor"),
    ("G5 record sub anche a registratore spento", RO,
     "    if not registra:\n        return\n    nomi = (",
     "    nomi = (",
     "test_ocm_solo_monitor"),
    ("G6 tee che non conta gli ocm", RO,
     "            if sorgente is not None and _mon.ATTIVO:\n",
     "            if False:\n",
     "test_ocm_solo_monitor or test_ocm_entrambi or test_ocm_sport"),
    ("G7 sport del processo ignorato (sempre calcio)", RO,
     '        nome = st.get("sport") or st.get("servizio") or "processo"\n',
     '        nome = "calcio"\n',
     "test_ocm_sport or test_ocm_sorgente"),
    ("G8 errore della misura risale allo stream", RO,
     '                    _avvisa("salute", "ocm non contato in Salute: %s", str(ex)[:160])\n',
     "                    raise\n",
     "test_ocm_misura_che_solleva"),
    ("G9 sorgente anche a monitor spento", RO,
     "        if not _mon.ATTIVO:\n            return None\n        st = _mon.stato() or {}\n",
     "        st = _mon.stato() or {}\n",
     "test_ocm_sorgente"),
    ("G10 tee chiamato senza la riga (on_data originale saltato)", RO,
     "            return originale(raw_data)\n",
     "            return True\n",
     "test_ocm_solo_monitor or test_ocm_false_del_listener"),
    # -- aggancio 2: latenza esito -> bot
    ("H1 lettore degli esiti senza aggancio", EO,
     "        if _mon.ATTIVO:  # 11/10 (agganci M-2): latenza esito -> bot, paper e live separati\n",
     "        if False:\n",
     "test_esiti_acceso"),
    ("H2 lettore degli esiti: paper e live sommati", EO,
     "            _mon.ricevuto_canale(msg, per_modo=True)\n",
     "            _mon.ricevuto_canale(msg)\n",
     "test_esiti_acceso_latenza or test_esiti_acceso_conto"),
    ("H3 per_modo ignorato in sonde", SO,
     '            topic = topic + "." + _modo(m)\n',
     "            pass\n",
     "test_esiti_acceso_latenza or test_esiti_acceso_conto"),
    ("H4 modo letto solo da ``modo`` (righe dello specchio a ?)", SO,
     '(d.get("mode") if "mode" in d else d.get("modo"))',
     '(d.get("modo"))',
     "test_esiti_acceso_latenza"),
    ("H5 ts 0 misurato", SO,
     "        if _numero_positivo(ts):\n            REGISTRO.tratto(\"canale_ricezione_ms.\"",
     "        if ts is not None:\n            REGISTRO.tratto(\"canale_ricezione_ms.\"",
     "test_esiti_acceso_ts_zero"),
    ("H6 aggancio PRIMA del filtro dei topic (hello e altri contati)", EO,
     "        if not isinstance(msg, dict) or msg.get(\"t\") not in self._accettati:\n"
     "            return False                    # hello e altro: non sono righe\n"
     "        if _mon.ATTIVO:  # 11/10 (agganci M-2): latenza esito -> bot, paper e live separati\n"
     "            _mon.ricevuto_canale(msg, per_modo=True)\n",
     "        if _mon.ATTIVO:  # 11/10 (agganci M-2): latenza esito -> bot, paper e live separati\n"
     "            _mon.ricevuto_canale(msg, per_modo=True)\n"
     "        if not isinstance(msg, dict) or msg.get(\"t\") not in self._accettati:\n"
     "            return False                    # hello e altro: non sono righe\n",
     "test_esiti_acceso_latenza"),
    # -- aggancio 3: invio della strada canale
    ("K1 strada canale senza invio", WK,
     "                invio=req.ricevuto_ms)",
     "                invio=None)",
     "test_clic_acceso_totale"),
    ("K2 tempi: 0 preso per un istante", TO,
     "            if x <= 0:\n                return None\n",
     "            if x < 0:\n                return None\n",
     "test_clic_spento or test_clic_acceso_ricevuto_zero or test_tempi_invio_zero"),
    ("K3 invio inventato quando manca (misura falsa)", WK,
     "                invio=req.ricevuto_ms)",
     "                invio=req.ricevuto_ms or int(time.time() * 1000))",
     "test_clic_spento or test_clic_acceso_ricevuto_zero"),
    ("K4 invio dall'orologio del DB (orologi misti)", WK,
     "                invio=req.ricevuto_ms)",
     "                invio=req.ricevuto_ms, invio_orologio=\"db\")",
     "test_clic_acceso_totale"),
]


def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


esito = 0
for voce in MUT:
    nome, rel, vecchio, nuovo, sel = voce[:5]
    p = RADICE + "/" + rel
    with open(p, "rb") as fh:
        orig = fh.read()
    h0 = hashlib.sha256(orig).hexdigest()
    testo = orig.decode("utf-8")
    if testo.count(vecchio) != 1:
        print("%-60s ERRORE: testo da mutare trovato %d volte" % (nome, testo.count(vecchio)))
        esito = 1
        continue
    try:
        with open(p, "wb") as fh:
            fh.write(testo.replace(vecchio, nuovo).encode("utf-8"))
        cmd = [sys.executable, "-m", "pytest", *T, "-q", "-p", "no:cacheprovider", "-x"]
        if sel:
            cmd += ["-k", sel]
        try:
            r = subprocess.run(cmd, cwd=RADICE, capture_output=True, text=True, timeout=300)
            ultima = [x for x in r.stdout.strip().splitlines() if x.strip()][-1]
            rosso = r.returncode != 0
        except subprocess.TimeoutExpired:
            # un test appeso non certifica niente: conta VERDE (!!) e va guardato
            ultima, rosso = "APPESO oltre 300 s", False
    finally:
        with open(p, "wb") as fh:
            fh.write(orig)
    h1 = sha(p)
    print("%-60s %s  [%s]  ripristino sha256 %s" % (
        nome, "ROSSO" if rosso else "VERDE (!!)", ultima[:60], "identico" if h0 == h1 else "DIVERSO"))
    if not rosso or h0 != h1:
        esito = 1
sys.exit(esito)
