"""Test del REGISTRATORE del canale locale (M-3, 11/10/2026).

Che cosa si inchioda (ARCHITETTURA_2026-10/mappa/M3_CANALE_E_MAPPA.md par. 5):

1. SPENTO di serie: senza ``REGISTRA_CANALE=1`` nessun aggancio viene chiamato,
   nessun file, e i client ricevono ESATTAMENTE gli stessi messaggi che con il
   registratore acceso (server ws VERO su 127.0.0.1, client ``websockets`` VERI).
2. ACCESO: un file ``<giorno>/canale_<porta>.jsonl.gz`` con metadati di OGNI
   publish, payload completo per i topic ``PIENI``, campione 1/N per gli altri,
   comandi ricevuti e risposte con payload, sequenza senza buchi, token mai
   scritto, chiavi sensibili mascherate.
3. CODA PIENA: si scarta e si conta, mai si blocca.
4. ERRORE DEL DISCO (e dell'aggancio): contato, mai propagato; il canale
   continua a consegnare.
5. ROTAZIONE giornaliera, CONSERVAZIONE in giorni, TETTO in MB (mai oggi;
   sospensione dichiarata se oggi da solo supera il tetto).
6. CLIENT SALTATI per contropressione: il record dice gli stessi numeri del
   canale (``saltati_client``), il giro saltato per intero ha il suo record.
7. Costo: microsecondi per messaggio con il registratore acceso (stampato).

I finti (loop, ws) hanno le stesse chiavi del vero (PSB par. 7 n.27): il canale
e' sempre ``LocalChannel`` di produzione. ASCII-only.
"""
from __future__ import annotations

import gzip
import json
import os
import socket
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from Betfair.stream import local_channel
from Betfair.stream import registratore_canale as reg
from Betfair.stream.local_channel import LocalChannel

RADICE = Path(__file__).resolve().parents[3]
TOKEN = "k" * 64


def _porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture()
def registratore(tmp_path):
    """Registratore acceso SENZA thread (i record restano in coda finche' il
    test chiama ``scrivi_ora``): niente attese, niente corse."""
    reg.spegni()
    reg.azzera_per_test()
    assert reg.accendi(cartella=str(tmp_path / "canale"), _consenti_in_test=True,
                       _senza_thread=True, campione=20)
    yield tmp_path / "canale"
    reg.spegni()
    reg.azzera_per_test()


@pytest.fixture(autouse=True)
def _sempre_spento_dopo(monkeypatch):
    # nella suite intera il banco e' gia' caricato da altri test: il controllo
    # VERO del banco si prova in un processo a parte
    # (``test_interruttore_dall_ambiente_in_un_processo_vero``)
    monkeypatch.setattr(reg, "nel_banco", lambda: False)
    yield
    reg.spegni()
    reg.azzera_per_test()
    assert reg.ATTIVO is False


def _file_di(cartella_giorno: Path, porta: int) -> List[Path]:
    """I file di una porta in un giorno: ``canale_<porta>_<pid>[_n].jsonl.gz``."""
    return sorted(cartella_giorno.glob("canale_%d_*.jsonl.gz" % porta))


def _file_di_oggi(base: Path, porta: int) -> Path:
    """L'UNICO file di oggi della porta (un processo, un file)."""
    f = _file_di(base / reg.giorno_locale(), porta)
    assert len(f) == 1, f
    assert f[0].name == "canale_%d_%d.jsonl.gz" % (porta, os.getpid())
    return f[0]


def _righe(percorso: Path) -> List[Dict[str, Any]]:
    righe, errore = reg.leggi_file(str(percorso))
    assert errore is None, errore
    return righe


def _righe_porta(cartella_giorno: Path, porta: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in _file_di(cartella_giorno, porta):
        out.extend(_righe(f))
    return out


def _ultimo_stato(righe: List[Dict[str, Any]]) -> Dict[str, Any]:
    st = [r for r in righe if r["k"] in ("stato", "chiusura")]
    assert st, "nessuna riga di stato o di chiusura"
    return st[-1]


# ---------------------------------------------------------------------------
# un giro VERO sul canale: server ws reale, un desktop col token, un lettore
# ---------------------------------------------------------------------------
def _ladder(mid: str, i: int) -> Dict[str, Any]:
    """Riga del ladder con la forma di ``runner.py`` (event/market/status/ladder)."""
    lad = {"runners": [{"selection_id": 1000 + r,
                        "back": [[round(2.0 + 0.02 * (lv + i % 3), 2), 10.0 + lv] for lv in range(10)],
                        "lay": [[round(2.02 + 0.02 * (lv + i % 3), 2), 12.0 + lv] for lv in range(10)],
                        "ltp": 2.02, "tv": 12345.6} for r in range(3)]}
    return {"event_id": "35760084", "market_id": mid, "market_type": "MATCH_ODDS",
            "market_name": "Esito Finale", "status": "OPEN", "ladder": lad}


def _ricevi_tutto(ws: Any, attesi: int, scadenza_s: float = 5.0) -> List[str]:
    out: List[str] = []
    fine = time.time() + scadenza_s
    while len(out) < attesi and time.time() < fine:
        try:
            out.append(ws.recv(timeout=0.5))
        except TimeoutError:
            continue
    return out


def _attendi(cond: Any, scadenza_s: float = 3.0) -> bool:
    fine = time.time() + scadenza_s
    while time.time() < fine:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def _giro_vero() -> Dict[str, Any]:
    """Lo stesso copione, sempre: ritorna che cosa hanno ricevuto i client."""
    from websockets.sync.client import connect

    porta = _porta_libera()
    ch = LocalChannel(porta, sport="calcio", token=TOKEN)
    assert ch.start() is True
    with connect(f"ws://127.0.0.1:{porta}/?t={TOKEN}", open_timeout=5) as desk, \
            connect(f"ws://127.0.0.1:{porta}/lettore/order", open_timeout=5) as lett:
        hello_d = desk.recv(timeout=5)
        hello_l = lett.recv(timeout=5)
        assert _attendi(lambda: ch._n_clients == 2 and ch._n_lettori == 1)
        for i in range(45):
            ch.publish("ladder", _ladder("1.%d" % (i % 10), i))
        ch.publish("order", {"bet_id": "B1", "status": "EXECUTABLE", "size_matched": 0.0})
        ch.publish("conto", {"modo": "live", "ordini": [{"bet_id": "B1"}]})
        ch.publish("order", {"bet_id": "B1", "status": "EXECUTION_COMPLETE", "size_matched": 2.0})
        desk.send(json.dumps({"id": 7, "m": "order",
                              "p": {"action": "place", "mode": "paper", "price": 2.0,
                                    "size": 2.0, "session_token": "NON-DEVE-USCIRE"}}))
        reqs: List[Any] = []
        assert _attendi(lambda: bool(reqs.extend(ch.pop_requests()) or reqs))
        ch.respond(reqs[0], True, {"ok": True, "bet_id": "B9"})
        desk.send(json.dumps({"id": 8, "m": "boh", "p": {}}))
        ricevuti_d = _ricevi_tutto(desk, 45 + 3 + 2)
        ricevuti_l = _ricevi_tutto(lett, 2)
    return {"porta": porta, "ch": ch, "desk": [hello_d] + ricevuti_d,
            "lett": [hello_l] + ricevuti_l}


def test_spento_nessun_aggancio_nessun_file_e_stessi_messaggi(tmp_path, monkeypatch):
    """SPENTO: gli agganci NON vengono mai chiamati (spie che contano), nessun
    file nasce, e i client ricevono gli stessi identici messaggi del giro col
    registratore acceso. Falsificazione: togliere ``if _reg.ATTIVO`` da un
    aggancio -> le spie contano -> rosso."""
    assert reg.ATTIVO is False
    chiamate: List[str] = []
    with pytest.MonkeyPatch.context() as mp:
        for nome in ("pubblicato", "giro_saltato", "ricevuto", "risposta", "risposta_attore"):
            mp.setattr(reg, nome, lambda *a, _n=nome, **k: chiamate.append(_n))
        mp.setenv(reg.ENV_CARTELLA, str(tmp_path / "spento"))
        spento = _giro_vero()
    assert chiamate == [], "a registratore spento un aggancio e' stato chiamato: %s" % chiamate
    assert not (tmp_path / "spento").exists()
    assert not _file_di(RADICE / "_logs" / "canale" / reg.giorno_locale(), spento["porta"])

    assert reg.accendi(cartella=str(tmp_path / "acceso"), _consenti_in_test=True,
                       _senza_thread=True)
    acceso = _giro_vero()
    assert len(spento["desk"]) == 1 + 45 + 3 + 2
    assert spento["desk"] == acceso["desk"], "il desktop ha ricevuto messaggi diversi"
    assert spento["lett"] == acceso["lett"], "il lettore ha ricevuto messaggi diversi"
    reg.scrivi_ora()
    assert _file_di_oggi(tmp_path / "acceso", acceso["porta"]).exists()


def test_acceso_file_corretto(registratore):
    """ACCESO: metadati di ogni publish, payload pieno per order/conto, campione
    1/20 per il ladder (1, 21, 41), comando e risposta con payload, sequenza
    1..n senza buchi, token mai nel file, chiave sensibile mascherata."""
    g = _giro_vero()
    porta, ch = g["porta"], g["ch"]
    c = reg.scrivi_ora()
    assert c["scartati_coda"] == 0 and c["errori_disco"] == 0 and c["errori_aggancio"] == 0
    f = _file_di_oggi(registratore, porta)
    grezzo = gzip.open(f, "rb").read()
    assert TOKEN.encode() not in grezzo, "il token del canale e' finito nel file"
    assert b"NON-DEVE-USCIRE" not in grezzo, "una chiave sensibile non e' stata mascherata"
    righe = _righe(f)

    pub = [r for r in righe if r["k"] == "pub"]
    ladder = [r for r in pub if r["topic"] == "ladder"]
    order = [r for r in pub if r["topic"] == "order"]
    assert len(ladder) == 45, "manca il metadato di qualche publish del ladder"
    assert [r["n_topic"] for r in ladder if "msg" in r] == [1, 21, 41]
    assert all(r["payload"] == "campione" for r in ladder if "msg" in r)
    assert all(r["dest"] == 1 and r["saltati"] == 0 and r["client"] == 2 for r in ladder), \
        "il lettore di 'order' non riceve il ladder: un solo destinatario"
    comp = [r["clienti"] for r in pub if "clienti" in r]
    assert len(comp) == 1, "la composizione si scrive solo quando cambia"
    assert sorted((g, c) for _n, g, c in comp[0]) == [("desktop", None), ("lettore", "order")]
    assert [r["msg"]["d"]["status"] for r in order] == ["EXECUTABLE", "EXECUTION_COMPLETE"]
    assert all(r["payload"] == "pieno" and r["dest"] == 2 for r in order)
    assert [r["msg"]["d"]["ordini"] for r in pub if r["topic"] == "conto"] == [[{"bet_id": "B1"}]]
    testo_l0 = json.dumps({"t": "ladder", "d": _ladder("1.0", 0)}, default=str)
    assert ladder[0]["byte"] == len(testo_l0)
    assert ladder[0]["msg"] == {"t": "ladder", "d": _ladder("1.0", 0)}

    rx = [r for r in righe if r["k"] == "rx"]
    assert [r["msg"]["id"] for r in rx] == [7, 8]
    assert rx[0]["genere"] == "desktop" and rx[0]["msg"]["p"]["session_token"] == "***"
    assert rx[0]["msg"]["p"]["price"] == 2.0
    tx = [r for r in righe if r["k"] == "tx"]
    assert {(r["via"], r["msg"]["id"], r["msg"]["ok"]) for r in tx} == \
        {("respond", 7, True), ("send", 8, False)}
    assert tx[0]["cliente"] == rx[0]["cliente"]

    seq = [r["seq"] for r in righe if "seq" in r]
    assert seq == list(range(1, len(seq) + 1)), "buco o disordine nella sequenza"
    mono = [r["mono_ns"] for r in righe if r["k"] == "pub"]
    assert mono == sorted(mono)
    assert all(r["porta"] == porta and r["sport"] == "calcio" for r in righe if "seq" in r)
    st = _ultimo_stato(righe)
    assert st["k"] == "chiusura", "l'ultima riga deve essere la chiusura"
    assert st["conti"]["mascherati"] >= 1 and st["campione"] == 20
    # il payload e' il testo del canale VERBATIM (separatori di json.dumps compresi)
    assert json.dumps({"t": "ladder", "d": _ladder("1.0", 0)}, default=str).encode() in grezzo
    assert ch.statistiche()["saltati_client"] == 0


def test_acceso_col_thread_vero_scrive_e_si_ferma(tmp_path):
    """Il thread di produzione (non ``scrivi_ora``): parte al primo record,
    scrive, a ``spegni`` chiude il file (gzip integro)."""
    reg.azzera_per_test()
    assert reg.accendi(cartella=str(tmp_path), _consenti_in_test=True)
    g = _giro_vero()
    assert reg._STATO["thread"] is not None and reg._STATO["thread"].name == "registratore-canale"
    reg.spegni(attesa_s=5.0)
    righe = _righe(_file_di_oggi(tmp_path, g["porta"]))
    assert len([r for r in righe if r["k"] == "pub"]) == 48


def test_interruttore_dall_ambiente_in_un_processo_vero(tmp_path):
    """L'interruttore all'import, in un processo Python VERO senza pytest:
    assente o "0" o "true" = spento; "1" = acceso; "1" col banco caricato
    prima = spento; banco caricato DOPO l'import = spento al primo record
    (nessun thread, nessun file)."""
    codice = (
        "import sys\n"
        "import types\n"
        "if sys.argv[1] == 'banco_prima':\n"
        "    sys.modules['Betfair.stream.backtest'] = types.ModuleType('b')\n"
        "from Betfair.stream import local_channel\n"
        "from Betfair.stream import registratore_canale as r\n"
        "a = r.ATTIVO\n"
        "if sys.argv[1] == 'banco_dopo':\n"
        "    sys.modules['Betfair.stream.backtest'] = types.ModuleType('b')\n"
        "class C: port=1; sport='x'; _clients=set(); _lettori={}; _in_volo_ws={}; "
        "_n_clients=0; _n_lettori=0\n"
        "r.pubblicato(C, 'ladder', '{}')\n"
        "print(a, r.ATTIVO, r._STATO['thread'] is not None)\n"
        "r.spegni()\n")
    def lancia(valore: Any, modo: str = "") -> str:
        env = {k: v for k, v in os.environ.items()
               if k not in (reg.ENV, "PYTEST_CURRENT_TEST")}
        env[reg.ENV_CARTELLA] = str(tmp_path / ("c_%s_%s" % (valore, modo)))
        if valore is not None:
            env[reg.ENV] = valore
        r = subprocess.run([sys.executable, "-c", codice, modo or "no"], cwd=str(RADICE),
                           env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[-2000:]
        return r.stdout.strip()
    # assente dall'ambiente: decide il file di ambiente della radice (sul PC
    # potrebbe dire 1)
    dal_file = reg.leggi_file_env().get(reg.ENV, "").strip() == "1"
    assert lancia(None) == ("True True True" if dal_file else "False False False")
    assert lancia("0") == "False False False"
    assert lancia("true") == "False False False"
    assert lancia("1") == "True True True"
    assert lancia("1", "banco_prima") == "False False False"
    assert lancia("1", "banco_dopo") == "True False False"
    assert not (tmp_path / "c_0_").exists() and not (tmp_path / "c_true_").exists()


def test_interruttore_dal_file_env_letto_e_mai_caricato(tmp_path, monkeypatch):
    """Il file di ambiente della radice si LEGGE (servizi che importano il
    canale prima del loro ``load_dotenv``) ma non entra in ``os.environ``;
    l'ambiente vero vince."""
    f = tmp_path / "prova.env"
    f.write_text("# commento\nexport REGISTRA_CANALE=1  # acceso\n"
                 "REGISTRA_CANALE_CAMPIONE=\"50\"\nALTRO='x y'\n")
    monkeypatch.delenv(reg.ENV, raising=False)
    assert reg.leggi_file_env(f) == {"REGISTRA_CANALE": "1", "REGISTRA_CANALE_CAMPIONE": "50",
                                     "ALTRO": "x y"}
    assert reg.interruttore_acceso(f) is True
    assert reg.ENV not in os.environ, "il file di ambiente e' stato caricato nell'ambiente"
    monkeypatch.setenv(reg.ENV, "0")
    assert reg.interruttore_acceso(f) is False
    f.write_text("REGISTRA_CANALE=0\n")
    monkeypatch.delenv(reg.ENV)
    assert reg.interruttore_acceso(f) is False
    assert reg.interruttore_acceso(tmp_path / "manca.env") is False


# ---------------------------------------------------------------------------
# finti con le chiavi del vero (loop e ws), per contropressione e coda
# ---------------------------------------------------------------------------
class _WsFinto:
    def __init__(self, nome: str) -> None:
        self.nome = nome

    def __hash__(self) -> int:
        return hash(self.nome)


class _LoopFinto:
    """Esegue subito ``call_soon_threadsafe``; ``create_task`` conta e chiude."""

    def __init__(self) -> None:
        self.creati: List[str] = []

    def call_soon_threadsafe(self, fn: Any) -> None:
        fn()

    def create_task(self, coro: Any) -> None:
        self.creati.append(getattr(coro, "__qualname__", "invio"))
        coro.close()


def _canale_finto(n_lenti: int, n_svelti: int) -> LocalChannel:
    ch = LocalChannel(_porta_libera(), sport="safe-scan", solo_lettura=True, token=TOKEN)
    ch._loop = _LoopFinto()
    lenti = [_WsFinto("lento%d" % i) for i in range(n_lenti)]
    svelti = [_WsFinto("svelto%d" % i) for i in range(n_svelti)]
    ch._clients = set(lenti) | set(svelti)
    ch._n_clients = len(ch._clients)
    for w in lenti:
        ch._in_volo_ws[w] = local_channel._MAX_INVII_IN_VOLO + 1
    ch._in_volo = (local_channel._MAX_INVII_IN_VOLO + 1) * n_lenti
    ch._ricalcola_pronti()
    return ch


def test_client_saltati_e_giro_saltato_registrati(registratore):
    """Un lento e due svelti: il record dice dest=2 saltati=1, come il canale.
    Tutti lenti: record ``giro_saltato``. Falsificazione: invertire il ``>``
    della regola nel registratore -> dest/saltati diversi dal canale -> rosso."""
    ch = _canale_finto(1, 2)
    for i in range(5):
        ch.publish("scan_tennis", {"event_id": "t%d" % i})
    assert ch.statistiche()["saltati_client"] == 5
    assert len(ch._loop.creati) == 10
    tutti_lenti = _canale_finto(2, 0)
    tutti_lenti.publish("scan_tennis", {"event_id": "x"})
    assert tutti_lenti.statistiche()["saltati"] == 1
    reg.scrivi_ora()
    righe = _righe(_file_di_oggi(registratore, ch.port))
    pub = [r for r in righe if r["k"] == "pub"]
    assert [(r["dest"], r["saltati"]) for r in pub] == [(2, 1)] * 5
    assert sum(r["saltati"] for r in pub) == ch.statistiche()["saltati_client"]
    salti = [r for r in _righe(_file_di_oggi(registratore, tutti_lenti.port))
             if r["k"] == "giro_saltato"]
    assert len(salti) == 1 and salti[0]["topic"] == "scan_tennis" and salti[0]["client"] == 2


def test_coda_piena_scarta_conta_e_non_blocca(tmp_path):
    """Coda da 10 record e nessun thread a drenarla: 1000 publish da un thread
    che deve finire SUBITO (mai un'attesa), 990 scartati contati, e la sequenza
    nel file ha il buco che dice quanti ne mancano."""
    reg.azzera_per_test()
    assert reg.accendi(cartella=str(tmp_path), _consenti_in_test=True, _senza_thread=True,
                       coda_max=10)
    ch = _canale_finto(0, 1)
    tempi: List[float] = []

    def corri() -> None:
        for i in range(1000):
            t0 = time.perf_counter()
            ch.publish("ladder", {"i": i})
            tempi.append(time.perf_counter() - t0)
    t = threading.Thread(target=corri)
    t.start()
    t.join(timeout=10)
    assert not t.is_alive(), "publish si e' BLOCCATO a coda piena"
    assert len(ch._loop.creati) == 1000, "il canale ha perso consegne per colpa della coda"
    c = reg.conti()
    assert c["scartati_coda"] == 990 and c["in_coda"] == 10
    assert max(tempi) < 0.05, "un publish ha aspettato %.1f ms" % (max(tempi) * 1000)
    reg.scrivi_ora()
    righe = _righe(_file_di_oggi(tmp_path, ch.port))
    assert [r["seq"] for r in righe if r["k"] == "pub"] == list(range(1, 11))
    assert _ultimo_stato(righe)["conti"]["scartati_coda"] == 990


class _FileRotto:
    def __init__(self, *_a: Any) -> None:
        pass

    def write(self, _b: bytes) -> int:
        raise OSError(28, "No space left on device")

    def flush(self) -> None:
        raise OSError(28, "No space left on device")

    def close(self) -> None:
        pass


def test_errore_del_disco_mai_propagato(registratore, monkeypatch):
    """Disco pieno all'apertura e alla scrittura: contato, mai propagato.
    Aggancio che esplode: contato, il canale consegna lo stesso."""
    ch = _canale_finto(0, 1)
    ch.publish("order", {"bet_id": "B1"})

    def apri_rotto(_d: Path, _porta: int) -> Any:
        raise PermissionError(13, "Permission denied")
    c = reg.scrivi_ora(apri=apri_rotto)
    assert c["errori_disco"] >= 1 and c["scritti"] == 0
    ch.publish("order", {"bet_id": "B2"})
    c = reg.scrivi_ora(apri=lambda d, porta: (_FileRotto(), d / "rotto.jsonl.gz"))
    assert c["errori_disco"] >= 2 and c["scritti"] == 0

    def esplode(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("boom")
    monkeypatch.setattr(reg, "_accoda", esplode)
    prima = len(ch._loop.creati)
    ch.publish("order", {"bet_id": "B3"})
    # canale di sola lettura: il comando riceve il rifiuto (un invio)
    ch._on_message(_WsFinto("svelto0"), json.dumps({"id": 1, "m": "snapshot"}))
    ch._send(_WsFinto("svelto0"), {"id": 1, "ok": True})
    assert len(ch._loop.creati) == prima + 3, "un errore del registratore ha fermato il canale"
    assert reg.conti()["errori_aggancio"] >= 4


def test_thread_vero_con_disco_rotto_non_muore(tmp_path):
    """Thread di produzione su una cartella che non si puo' creare (un FILE al
    suo posto): errori contati, thread vivo, canale intatto."""
    occupato = tmp_path / "occupato"
    occupato.write_text("io sono un file")
    reg.azzera_per_test()
    assert reg.accendi(cartella=str(occupato), _consenti_in_test=True)
    ch = _canale_finto(0, 1)
    for i in range(20):
        ch.publish("order", {"i": i})
    assert _attendi(lambda: reg.conti()["errori_disco"] >= 1)
    assert reg._STATO["thread"].is_alive()
    assert len(ch._loop.creati) == 20


def _crea_giorno(base: Path, giorno: str, n_byte: int, estraneo: bool = False) -> None:
    d = base / giorno
    d.mkdir(parents=True, exist_ok=True)
    (d / "canale_47331.jsonl.gz").write_bytes(b"x" * n_byte)
    if estraneo:
        (d / "mio_appunto.txt").write_text("non toccare")


def test_conservazione_e_tetto(tmp_path):
    """Giorni oltre la conservazione tolti; oltre il tetto si toglie il piu'
    vecchio, MAI oggi; i file non nostri restano. Falsificazione: togliere il
    filtro ``!= oggi`` -> oggi sparisce -> rosso."""
    base = tmp_path / "c"
    for g in range(1, 12):
        _crea_giorno(base, "2026-10-%02d" % g, 1000, estraneo=(g == 2))
    dentro, rimossi = reg.applica_tetto(base, tetto_byte=10_000_000, giorni=7, oggi="2026-10-11")
    assert dentro and rimossi == 4
    assert sorted(d.name for d in base.iterdir()) == \
        ["2026-10-02"] + ["2026-10-%02d" % g for g in range(5, 12)]
    assert (base / "2026-10-02" / "mio_appunto.txt").exists()
    assert not (base / "2026-10-02" / "canale_47331.jsonl.gz").exists()
    dentro, rimossi = reg.applica_tetto(base, tetto_byte=3500, giorni=7, oggi="2026-10-11")
    assert dentro and reg.peso_cartella(base) == 3000
    assert sorted(d.name for d in base.iterdir() if any(d.iterdir())) == \
        ["2026-10-02", "2026-10-09", "2026-10-10", "2026-10-11"]
    _crea_giorno(base, "2026-10-11", 9000)
    dentro, _ = reg.applica_tetto(base, tetto_byte=3500, giorni=7, oggi="2026-10-11")
    assert dentro is False and (base / "2026-10-11" / "canale_47331.jsonl.gz").exists()


def test_rotazione_a_mezzanotte_e_sospensione_al_tetto(registratore, monkeypatch):
    """Il cambio di data apre un file nuovo nella cartella del giorno nuovo; se
    oggi da solo supera il tetto la scrittura si sospende e lo si scrive."""
    ch = _canale_finto(0, 1)
    giorni = iter(["2026-10-11"] + ["2026-10-12"] * 100)
    monkeypatch.setattr(reg, "giorno_locale", lambda *_a: next(giorni))
    s = reg._Scrittore()
    ch.publish("order", {"g": 1})
    s.giro()
    ch.publish("order", {"g": 2})
    s.giro()
    s._chiudi_tutti()
    a = _righe_porta(registratore / "2026-10-11", ch.port)
    b = _righe_porta(registratore / "2026-10-12", ch.port)
    assert [r["k"] for r in a][-1] == "chiusura", "la rotazione chiude il giorno con la chiusura"
    assert [r["msg"]["d"]["g"] for r in a if r["k"] == "pub"] == [1]
    assert [r["msg"]["d"]["g"] for r in b if r["k"] == "pub"] == [2]

    reg._CONF["tetto_mb"] = 0.000001     # ~1 byte: oggi supera subito
    s2 = reg._Scrittore()
    ch.publish("order", {"g": 3})
    s2.giro()
    ch.publish("order", {"g": 4})
    s2.giro()
    s2._chiudi_tutti()
    assert reg.conti()["scartati_tetto"] == 2
    righe_b = _righe_porta(registratore / "2026-10-12", ch.port)
    assert len(_file_di(registratore / "2026-10-12", ch.port)) == 2, \
        "il secondo scrittore deve creare un file NUOVO, mai accodare"
    assert [r["k"] for r in righe_b][-1] == "tetto_raggiunto"
    assert [r["msg"]["d"]["g"] for r in righe_b if r["k"] == "pub"] == [2]


def test_file_troncato_si_legge_fino_al_troncamento(tmp_path):
    """Processo morto prima della chiusura: le righe intere si leggono, il
    troncamento si DICE."""
    p = tmp_path / "canale_1.jsonl.gz"
    with gzip.open(p, "wb") as fh:
        for i in range(200):
            fh.write((json.dumps({"k": "pub", "seq": i}) + "\n").encode())
    dati = p.read_bytes()
    p.write_bytes(dati[: len(dati) - 15])
    righe, errore = reg.leggi_file(str(p))
    assert errore is not None and "tronc" in errore
    assert len(righe) >= 1 and righe[0]["seq"] == 0


# ---------------------------------------------------------------------------
# costo: 50 messaggi al secondo per 10 mercati (500/s), ladder realistico
# ---------------------------------------------------------------------------
def _misura_giro(ch: LocalChannel, n: int) -> float:
    """Microsecondi per messaggio di publish (chiamante) + giro di broadcast
    (loop finto che esegue subito), mediana di 5 ripetizioni."""
    payload = [_ladder("1.%d" % m, i) for i in range(5) for m in range(10)]
    giri = []
    for _ in range(5):
        t0 = time.perf_counter()
        for i in range(n):
            ch.publish("ladder", payload[i % len(payload)])
        giri.append((time.perf_counter() - t0) / n * 1e6)
    return statistics.median(giri)


def test_costo_per_messaggio_col_registratore_acceso(tmp_path, capsys):
    """Misura dichiarata nel documento M3: publish + giro di broadcast con il
    registratore spento e acceso, ALTERNATI (il rumore della macchina pesa
    uguale), piu' l'aggancio da solo e la scrittura nel thread. Il tetto del
    test e' largo (macchina condivisa): +100 us per messaggio sopra lo spento.
    Falsificazione: una scrittura su disco nell'aggancio -> rosso."""
    ch = _canale_finto(0, 2)
    reg.azzera_per_test()
    assert reg.accendi(cartella=str(tmp_path), _consenti_in_test=True, _senza_thread=True,
                       coda_max=100000)
    spenti: List[float] = []
    accesi: List[float] = []
    for _ in range(4):
        reg.ATTIVO = False
        spenti.append(_misura_giro(ch, 500))
        reg.ATTIVO = True
        accesi.append(_misura_giro(ch, 500))
    spento, acceso = statistics.median(spenti), statistics.median(accesi)
    testo = json.dumps({"t": "ladder", "d": _ladder("1.1", 1)})
    t0 = time.perf_counter()
    for _ in range(2000):
        reg.pubblicato(ch, "ladder", testo)
    solo = (time.perf_counter() - t0) / 2000 * 1e6
    n_rec = reg.conti()["in_coda"]
    t0 = time.perf_counter()
    reg.scrivi_ora()
    scrittura = (time.perf_counter() - t0) / max(1, n_rec) * 1e6
    with capsys.disabled():
        print("\n[M3 costo] publish+broadcast spento %.1f us/msg, acceso %.1f us/msg "
              "(differenza %.1f); aggancio da solo %.2f us/msg; scrittura nel thread "
              "%.1f us/msg su %d record (campione 1/20)"
              % (spento, acceso, acceso - spento, solo, scrittura, n_rec))
    assert acceso - spento < 100.0
    assert solo < 100.0


# ---------------------------------------------------------------------------
# spento = IDENTICO al canale senza agganci (stessi messaggi, stessi tempi)
# ---------------------------------------------------------------------------
#: agganci dichiarati nel documento M3 (par. 2): se ne nasce uno nuovo senza
#: dichiararlo, questo numero diventa rosso
AGGANCI_DICHIARATI = 7
#: tolleranza dichiarata sui tempi: differenza fra i migliori giri (publish +
#: broadcast, us per messaggio) del canale senza agganci e del canale con
#: agganci SPENTI: 5 us o il 10% del costo, il maggiore. Larga perche' la
#: macchina e' condivisa; la misura vera e' stampata.
TOLLERANZA_US = 5.0


def _canale_senza_agganci() -> Any:
    """Il modulo ``local_channel`` di produzione con gli agganci TOLTI dal
    sorgente (import di ``_reg`` e coppie ``if _reg.ATTIVO:`` + chiamata):
    e' il canale com'era prima di M-3, compilato nello stesso pacchetto."""
    import importlib.util

    src = Path(local_channel.__file__).read_text(encoding="utf-8").splitlines(keepends=True)
    out: List[str] = []
    tolti, salta = 0, False
    for riga in src:
        if salta:
            salta = False
            assert riga.strip().startswith("_reg."), riga
            continue
        if "registratore_canale as _reg" in riga:
            continue
        if riga.strip().startswith("if _reg.ATTIVO"):
            tolti += 1
            salta = True
            continue
        out.append(riga)
    assert tolti == AGGANCI_DICHIARATI, "agganci nel canale: %d, dichiarati %d" % (
        tolti, AGGANCI_DICHIARATI)
    testo = "".join(out)
    assert "_reg" not in testo
    nome = "Betfair.stream._local_channel_senza_agganci"
    spec = importlib.util.spec_from_loader(nome, loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "Betfair.stream"
    sys.modules[nome] = mod       # le dataclass cercano il modulo per nome
    try:
        exec(compile(testo, "<local_channel senza agganci>", "exec"), mod.__dict__)  # noqa: S102
    finally:
        sys.modules.pop(nome, None)
    return mod


def test_spento_identico_al_canale_senza_agganci(monkeypatch, capsys):
    """Server ws VERO: il canale senza agganci e quello di produzione a
    registratore spento consegnano gli STESSI messaggi nello stesso ordine; il
    costo per messaggio (loop finto, ladder realistico, 500 messaggi = 1 s di
    10 mercati a 50/s) resta entro ``TOLLERANZA_US``."""
    assert reg.ATTIVO is False
    originale = _canale_senza_agganci()
    attuale = _giro_vero()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys.modules[__name__], "LocalChannel", originale.LocalChannel)
        vecchio = _giro_vero()
    assert len(attuale["desk"]) == 1 + 45 + 3 + 2
    assert attuale["desk"] == vecchio["desk"]
    assert attuale["lett"] == vecchio["lett"]

    def canale(cls: Any) -> Any:
        ch = cls(_porta_libera(), sport="calcio", solo_lettura=True, token=TOKEN)
        ch._loop = _LoopFinto()
        ch._clients = {_WsFinto("a"), _WsFinto("b")}
        ch._n_clients = 2
        ch._ricalcola_pronti()
        return ch
    ch_o, ch_a = canale(originale.LocalChannel), canale(LocalChannel)
    mis_o: List[float] = []
    mis_a: List[float] = []
    for _ in range(6):          # alternati: il rumore della macchina pesa uguale
        mis_o.append(_misura_giro(ch_o, 500))
        mis_a.append(_misura_giro(ch_a, 500))
    assert len(ch_o._loop.creati) == len(ch_a._loop.creati)
    # il MIGLIORE dei giri di ciascuno: il rumore della macchina condivisa
    # aggiunge solo tempo, mai ne toglie
    o, a = min(mis_o), min(mis_a)
    tolleranza = max(TOLLERANZA_US, 0.10 * o)
    with capsys.disabled():
        print("\n[M3 spento] senza agganci %.2f us/msg, con agganci spenti %.2f us/msg "
              "(differenza %.2f us, tolleranza %.1f)" % (o, a, a - o, tolleranza))
    assert a - o < tolleranza


# ---------------------------------------------------------------------------
# 11/10, revisione indipendente: file per processo, uscita, fork, lettura
# tollerante, payload verbatim, chiavi esatte, numeri dei client, confini
# ---------------------------------------------------------------------------
_PROGRAMMA_PROCESSO = r'''
import os, sys, time
from Betfair.stream import registratore_canale as r
from Betfair.stream.local_channel import LocalChannel
from websockets.sync.client import connect
assert r.ATTIVO, "registratore spento nel processo figlio"
r.FLUSH_OGNI_S = 0.1
porta, n, modo = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
tok = "k" * 64
ch = LocalChannel(porta, sport="calcio", token=tok)
assert ch.start()
ws = connect("ws://127.0.0.1:%d/?t=%s" % (porta, tok), open_timeout=5)
ws.recv(timeout=5)
fine = time.time() + 5
while ch._n_clients < 1 and time.time() < fine:
    time.sleep(0.01)
for i in range(n):
    ch.publish("order", {"i": i, "pid": os.getpid()})
    time.sleep(0.05)
if modo == "uccidi":
    time.sleep(0.6)          # almeno un flush del gzip sul disco
    print("PRONTO", flush=True)
    time.sleep(120)
ws.close()
print("FINE", flush=True)
'''


def _ambiente_figlio(cartella: Path, **extra: str) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_CURRENT_TEST",)}
    env.update({reg.ENV: "1", reg.ENV_CARTELLA: str(cartella)})
    env.update(extra)
    return env


def test_due_processi_veri_in_sequenza_e_uno_ucciso_poi_la_mappa(tmp_path):
    """Il difetto del 11/10: dopo un riavvio nello stesso giorno il .gz era
    illeggibile e la mappa andava in traceback. Ora: TRE processi Python VERI
    sulla STESSA porta nello stesso giorno - due escono normalmente (atexit:
    riga ``chiusura``, gzip chiuso), il terzo e' ucciso con kill -9 - tre file
    distinti, nessun append; la mappa legge tutto, distingue i tre processi e
    dice che il terzo non ha chiuso."""
    from Betfair.stream import mappa_flussi as mf

    porta = _porta_libera()
    base = tmp_path / "canale"
    for _ in range(2):
        r = subprocess.run([sys.executable, "-c", _PROGRAMMA_PROCESSO, str(porta), "20", "esci"],
                           cwd=str(RADICE), env=_ambiente_figlio(base), capture_output=True,
                           text=True, timeout=60)
        assert r.returncode == 0 and "FINE" in r.stdout, r.stderr[-2000:]
        time.sleep(1.0)     # una pausa VERA fra i processi: la cadenza non deve vederla
    p = subprocess.Popen([sys.executable, "-c", _PROGRAMMA_PROCESSO, str(porta), "20", "uccidi"],
                         cwd=str(RADICE), env=_ambiente_figlio(base), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    try:
        assert p.stdout is not None and p.stdout.readline().strip() == "PRONTO"
    finally:
        p.kill()            # SIGKILL su POSIX: nessun atexit, nessuna chiusura
        p.wait(timeout=30)
    giorno = reg.giorno_locale()
    files = _file_di(base / giorno, porta)
    assert len(files) == 3, files
    integri = 0
    for f in files:
        righe, errore = reg.leggi_file(str(f))
        assert len([x for x in righe if x["k"] == "pub"]) >= 1
        if righe and righe[-1]["k"] == "chiusura":
            integri += 1
            assert errore is None, errore
            assert len([x for x in righe if x["k"] == "pub"]) == 20, "righe perse all'uscita"
    assert integri == 2
    d = mf.genera(giorno, canale=base)
    proc = d["canale"]["processi"]
    assert len(proc) == 3, "tre processi (porta, pid, avvio) distinti"
    assert sorted(x["chiuso"] for x in proc) == [False, True, True]
    order = [t for t in d["canale"]["topic"] if t["topic"] == "order"][0]
    assert order["n"] >= 41
    # cadenza per processo: 50 ms fra un publish e l'altro, mai il salto fra processi
    assert order["cad_p99"] is not None and order["cad_p99"] < 400.0, order["cad_p99"]
    testo = mf.markdown(d)
    assert "nessuna riga di chiusura" in testo


def test_vecchio_difetto_membro_accodato_dopo_un_flusso_tronco(tmp_path):
    """Il file rotto del 11/10 rifatto a mano: un membro gzip tronco (processo
    ucciso) seguito da un membro intero (riavvio in append). ``gzip.open`` lo
    rifiuta; il lettore tollerante tiene il leggibile del primo e TUTTO il
    secondo, e la mappa non va in traceback."""
    import zlib

    from Betfair.stream import mappa_flussi as mf

    def membro(righe: List[Dict[str, Any]]) -> bytes:
        c = zlib.compressobj(6, zlib.DEFLATED, 31)
        return c.compress("".join(json.dumps(x) + "\n" for x in righe).encode()) + c.flush()

    giorno = reg.giorno_locale()
    d = tmp_path / "canale" / giorno
    d.mkdir(parents=True)
    primo = [{"v": 2, "k": "pub", "seq": i, "mono_ns": i * 10 ** 6, "epoca_ms": 1, "porta": 1,
              "pid": 1, "av": 1, "topic": "order", "byte": 10, "dest": 1, "saltati": 0,
              "client": 1, "lettori": 0, "n_topic": i + 1, "pad": "x%d" % (i * 7919)}
             for i in range(1, 2000)]
    secondo = [dict(r, pid=2, av=2) for r in primo[:50]]
    a = membro(primo)
    rotto = a[: len(a) // 2]
    f = d / "canale_1_1.jsonl.gz"
    f.write_bytes(rotto + membro(secondo))
    with pytest.raises(Exception):
        with gzip.open(f, "rt") as fh:
            fh.read()
    righe, errore = reg.leggi_file(str(f))
    assert errore and ("corrott" in errore or "tronc" in errore)
    assert len([r for r in righe if r.get("pid") == 2]) == 50, "il membro intero va letto tutto"
    assert len([r for r in righe if r.get("pid") == 1]) > 10, "il leggibile del tronco si tiene"
    dati = mf.genera(giorno, canale=tmp_path / "canale")
    assert len(dati["canale"]["processi"]) == 2
    assert dati["canale"]["file"][0]["errore"]


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork solo su POSIX")
def test_fork_il_figlio_non_scrive_mai_nel_file_del_padre(tmp_path):
    """Un figlio di ``fork`` che esce normalmente chiuderebbe (scrivendoli) i
    gzip ereditati nello STESSO file del padre: buffer duplicati e trailer in
    mezzo. Con ``register_at_fork`` il figlio e' chiuso e i suoi file vanno su
    devnull: il file del padre resta integro."""
    programma = r'''
import os, sys, time
from Betfair.stream import registratore_canale as r
r.FLUSH_OGNI_S = 3600   # nessun flush prima del fork: il buffer pendente e' il rischio
class C:
    port = 47999; sport = "calcio"; _clients = set(); _lettori = {}; _in_volo_ws = {}
    _n_clients = 0; _n_lettori = 0; _comando_ws = {}
for i in range(50):
    r.pubblicato(C, "order", '{"t": "order", "d": {"i": %d}}' % i)
fine = time.time() + 5
while r.conti()["scritti"] < 50 and time.time() < fine:
    time.sleep(0.01)
pid = os.fork()
if pid == 0:
    # il figlio chiude TUTTI i gzip che ha in memoria, come farebbe la sua
    # finalizzazione (che a Python non e' garantita in un ordine fisso: qui la
    # si rende certa, cosi' il test non dipende dal caso)
    import gc, gzip
    for o in gc.get_objects():
        if isinstance(o, gzip.GzipFile):
            try:
                o.close()
            except Exception:
                pass
    os._exit(0)
os.waitpid(pid, 0)
for i in range(50, 100):
    r.pubblicato(C, "order", '{"t": "order", "d": {"i": %d}}' % i)
print("FINE", flush=True)
'''
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", programma], cwd=str(RADICE),
                       env=_ambiente_figlio(tmp_path), capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0 and "FINE" in r.stdout, r.stderr[-2000:]
    files = _file_di(tmp_path / reg.giorno_locale(), 47999)
    assert len(files) == 1
    righe, errore = reg.leggi_file(str(files[0]))
    assert errore is None, "il figlio ha scritto nel file del padre: %s" % errore
    assert [x["msg"]["d"]["i"] for x in righe if x["k"] == "pub"] == list(range(100))
    assert righe[-1]["k"] == "chiusura"


def test_giorno_locale_e_non_utc(tmp_path):
    """La cartella del giorno e' la data LOCALE del PC: in un processo con il
    fuso scelto apposta perche' la data locale e quella UTC siano diverse."""
    if os.name == "nt":
        pytest.skip("TZ dell'ambiente non vale su Windows")
    ora_utc = time.gmtime()
    fuso = "Etc/GMT-14" if ora_utc.tm_hour >= 12 else "Etc/GMT+12"
    programma = r'''
import time
from Betfair.stream import registratore_canale as r
class C:
    port = 47998; sport = "calcio"; _clients = set(); _lettori = {}; _in_volo_ws = {}
    _n_clients = 0; _n_lettori = 0; _comando_ws = {}
r.pubblicato(C, "order", '{"t": "order", "d": {}}')
r.spegni()
print(time.strftime("%Y-%m-%d", time.localtime()), time.strftime("%Y-%m-%d", time.gmtime()))
'''
    r = subprocess.run([sys.executable, "-c", programma], cwd=str(RADICE),
                       env=_ambiente_figlio(tmp_path, TZ=fuso), capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    locale, utc = r.stdout.split()
    assert locale != utc, "fuso di prova sbagliato: le due date coincidono"
    assert sorted(x.name for x in tmp_path.iterdir()) == [locale]


def test_sotto_pytest_resta_spento_anche_con_l_interruttore(monkeypatch, tmp_path):
    """REGISTRA_CANALE=1 sotto pytest: ``accendi`` senza il permesso dei test
    rifiuta (la suite non deve mai scrivere registrazioni)."""
    monkeypatch.setenv(reg.ENV, "1")
    monkeypatch.setenv(reg.ENV_CARTELLA, str(tmp_path))
    assert reg.accendi() is False
    assert reg.ATTIVO is False
    assert reg.accendi(_consenti_in_test=True, _senza_thread=True) is True


def test_chiavi_sensibili_esatte_anche_nelle_liste():
    """Mascherate: le chiavi ESATTE (maiuscole indifferenti) a qualunque
    profondita', dentro le liste; ``t``/``tk`` solo con un testo lungo. NON
    mascherate: sessione, sessioni, certified, incertezza_ms, ``t`` del
    protocollo. Stesso esito sul testo (percorso normale) e su ``_ripulisci``."""
    segreto = "S" * 40
    esatte = ["key", "x-authentication", "token", "password", "authorization", "app_key",
              "ssoid", "cookie", "Token", "X-Authentication", "t", "tk"]
    for k in esatte:
        for obj in ({k: segreto}, {"p": {"a": [{"b": 1}, {k: segreto}]}}, {"l": [[{k: segreto}]]}):
            conta = [0]
            testo = reg.maschera_testo(json.dumps(obj), conta)
            assert segreto not in testo, (k, testo)
            assert conta[0] == 1, (k, conta)
            conta2 = [0]
            assert segreto not in json.dumps(reg._ripulisci(obj, conta2)), k
            assert conta2[0] == 1
    lecite = {"t": "ladder", "tk": "corto", "sessione": "S1", "sessioni": [1, 2],
              "certified": True, "incertezza_ms": 12.5, "keys": "x", "monkey": "y",
              "token_scadenza": 5}
    conta = [0]
    testo = reg.maschera_testo(json.dumps(lecite), conta)
    assert json.loads(testo) == lecite and conta[0] == 0, testo
    assert reg._ripulisci(lecite, [0]) == lecite
    # valore composto (oggetto o lista): ripiego sul json, tutto il valore via
    conta = [0]
    testo = reg.maschera_testo(json.dumps({"a": 1, "token": {"v": segreto}}), conta)
    assert segreto not in testo and json.loads(testo) == {"a": 1, "token": "***"}


def test_confine_dei_saltati_uguale_al_canale(registratore):
    """Con esattamente ``_MAX_INVII_IN_VOLO`` invii in volo il client RICEVE
    (il canale salta solo OLTRE il tetto): il registratore deve dire lo stesso."""
    ch = _canale_finto(0, 2)
    w = sorted(ch._clients, key=lambda x: x.nome)[0]
    ch._in_volo_ws[w] = local_channel._MAX_INVII_IN_VOLO
    ch._ricalcola_pronti()
    ch.publish("order", {"x": 1})
    assert ch.statistiche()["saltati_client"] == 0 and len(ch._loop.creati) == 2
    ch._in_volo_ws[w] = local_channel._MAX_INVII_IN_VOLO + 1
    ch._ricalcola_pronti()
    ch.publish("order", {"x": 2})
    assert ch.statistiche()["saltati_client"] == 1
    reg.scrivi_ora()
    pub = [r for r in _righe(_file_di_oggi(registratore, ch.port)) if r["k"] == "pub"]
    assert [(r["dest"], r["saltati"]) for r in pub] == [(2, 0), (1, 1)]


def test_numeri_dei_client_per_connessione_mai_riusati(registratore):
    """Ogni connessione ha un numero suo, anche se Python riusa l'``id`` di un
    socket chiuso; la composizione si riscrive a ogni ricollegamento."""
    ch = _canale_finto(0, 1)
    ch.publish("order", {"g": 1})
    for giro in range(5):
        ch._clients = set()                     # il vecchio socket muore
        ch._clients = {_WsFinto("ricollegato%d" % giro)}
        ch._n_clients = 1
        ch._ricalcola_pronti()
        ch.publish("order", {"g": giro + 2})
    reg.scrivi_ora()
    pub = [r for r in _righe(_file_di_oggi(registratore, ch.port)) if r["k"] == "pub"]
    comp = [r["clienti"] for r in pub if "clienti" in r]
    assert len(comp) == 6, "una composizione per ogni (ri)collegamento"
    numeri = {c[0][0] for c in comp}
    assert len(numeri) == 6, "numero di client riusato: %s" % comp


def test_coda_limitata_anche_in_byte(tmp_path):
    """Payload pieni grandi: oltre ``coda_max_byte`` si scarta e si conta,
    anche se il numero di record e' basso."""
    reg.azzera_per_test()
    assert reg.accendi(cartella=str(tmp_path), _consenti_in_test=True, _senza_thread=True,
                       coda_max=1000, coda_max_byte=50_000)
    ch = _canale_finto(0, 1)
    for i in range(20):
        ch.publish("order", {"i": i, "pad": "x" * 10_000})
    c = reg.conti()
    assert c["in_coda"] == 4 and c["scartati_coda"] == 16, c
    assert c["byte_in_coda"] <= 50_000
    reg.scrivi_ora()
    assert reg.conti()["byte_in_coda"] == 0


def test_payload_pieni_scritti_senza_rileggerli(registratore, monkeypatch):
    """Il thread di scrittura NON fa ``json.loads`` dei payload del canale (il
    GIL del 11/10): conta le chiamate durante la scrittura di 200 publish pieni."""
    ch = _canale_finto(0, 1)
    for i in range(200):
        ch.publish("conto", {"i": i, "ordini": [{"bet_id": "B%d" % i, "pad": "x" * 2000}]})

    class _Spia:
        chiamate = 0

        def __getattr__(self, nome: str) -> Any:
            return getattr(json, nome)

        def loads(self, *a: Any, **k: Any) -> Any:
            _Spia.chiamate += 1
            return json.loads(*a, **k)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(reg, "json", _Spia())
        reg.scrivi_ora()
    assert _Spia.chiamate == 0, "payload riletti: %d json.loads" % _Spia.chiamate
    pub = [r for r in _righe(_file_di_oggi(registratore, ch.port)) if r["k"] == "pub"]
    assert len(pub) == 200 and pub[7]["msg"]["d"]["ordini"][0]["bet_id"] == "B7"
