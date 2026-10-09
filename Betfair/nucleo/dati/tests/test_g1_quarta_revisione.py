"""W1-G1 - prove della QUARTA revisione (09/10, "PASSA" con la riserva D e le note a, b).

D   perdita di corrente sullo stato_vivo (``synchronous=NORMAL``): la coda del WAL e ``meta.vseq``
    si perdono, la vseq si riusa. Con l'origine FISSA per file la scrittura nuova del bot era
    "vecchia" per il cloud e si perdeva in silenzio; ora l'origine cambia a OGNI ``apri()`` e le
    voci rimaste in outbox tengono la loro (``scratchpad/rev_w1g1_3/origine_2d.py``).
a   invariante "ordine delle vseq = ordine di coda" sotto thread, deterministico con il gancio
    ``archivio.GANCIO_METTI`` al posto dello sleep (``ordine_vseq.py`` del revisore, mutazione X3).
b   (in ``test_g1_pg_reale.py``) due postini con lotti in ordine opposto: 0 deadlock 40P01.
Client supabase VERO su MockTransport (``test_g1_finti``), orologio comandato.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("SUPABASE_KEY", "x")

import Betfair.nucleo.dati.archivio as mod  # noqa: E402
from Betfair.nucleo.dati.archivio import ArchivioLocale  # noqa: E402
from Betfair.nucleo.dati.postino import PostinoLocale  # noqa: E402
from Betfair.nucleo.dati.tests.test_g1_finti import SPEC, CloudProva, PostgrestFinto, riga_ordine  # noqa: E402

T0 = 1_760_004_000_000


def _segui(i: int, stato: str, **extra: Any) -> Dict[str, Any]:
    r = {"event_id": "E1", "home_name": "A", "away_name": "B", "open_date": "2026-10-09T12:00:00+00:00",
         "status": stato, "updated_at": f"2026-10-09T10:00:0{i}+00:00"}
    r.update(extra)
    return r


class Banco:
    """Una cartella di processo (``processo`` fisso), riaperta piu' volte, su UN cloud finto."""

    def __init__(self, base: Path) -> None:
        self.base, self.ora, self.server = base, [T0], PostgrestFinto()
        self.eventi: List[str] = []
        self.a: Optional[ArchivioLocale] = None
        self.p: Optional[PostinoLocale] = None

    def apri(self) -> ArchivioLocale:
        self.a = ArchivioLocale("x", SPEC, base=self.base, orologio_ms=lambda: self.ora[0],
                                eventi=lambda n, d: self.eventi.append(n)).apri()
        self.p = PostinoLocale(self.a, CloudProva(self.server), orologio_ms=lambda: self.ora[0],
                               eventi=lambda n, d: self.eventi.append(n))
        return self.a

    def drena(self, volte: int = 3) -> None:
        assert self.p is not None
        for _ in range(volte):
            self.p.drena()
            self.ora[0] += 1000

    def chiudi(self) -> None:
        if self.a is not None and self.a.aperto:
            self.a.chiudi()

    def cloud(self, tabella: str, chiave: str, valore: Any) -> Dict[str, Any]:
        return next(r for r in self.server.tabelle[tabella].righe if r.get(chiave) == valore)


@pytest.fixture
def banco(tmp_path: Path):
    b = Banco(tmp_path / "base")
    yield b
    b.chiudi()


# ============================================================================ D
def test_D_perdita_di_corrente_sul_vivo_la_scrittura_nuova_arriva(banco: Banco, tmp_path: Path) -> None:
    """origine_2d.py del revisore. Il cloud ha gia' la versione 3 dell'apertura prima del
    blackout; dopo il blackout la cartella torna allo stato durevole di PRIMA delle tre
    scritture (``meta.vseq`` = 0): la scrittura NUOVA (CLOSED, vseq 1) deve arrivare, come oggi."""
    a = banco.apri()
    a.chiudi()
    durevole = tmp_path / "durevole"
    shutil.copytree(a.cartella, durevole)                   # stato su disco prima delle scritture
    a = banco.apri()
    prima = a.origine("stato_vivo")
    for i in range(3):
        a.scrivi("live_follow", _segui(i, "STREAMING", error_detail=f"e{i}"))
    assert a.conferma()
    banco.drena()
    assert banco.cloud("live_follow", "event_id", "E1")["status"] == "STREAMING"
    assert json.dumps(["live_follow", ["E1"], prima]) in banco.server.versioni
    a.chiudi()
    shutil.rmtree(a.cartella)
    shutil.copytree(durevole, a.cartella)                   # il SO ha perso la coda del WAL non sincronizzata
    a = banco.apri()
    assert a.leggi("live_follow", {"event_id": "E1"}) is None
    assert a.origine("stato_vivo") != prima
    a.scrivi("live_follow", _segui(5, "CLOSED"))
    assert a.conferma()
    assert a.outbox_pronta("stato_vivo", 2 ** 62, 10)[0].vseq == 1          # la vseq si e' davvero riusata
    banco.drena()
    r = banco.cloud("live_follow", "event_id", "E1")
    assert (r["status"], r["updated_at"]) == ("CLOSED", "2026-10-09T10:00:05+00:00")   # oggi: CLOSED
    assert "dati.riga_vecchia" not in banco.eventi and banco.p is not None and banco.p.contatori["vecchie"] == 0


def test_D_voci_rimaste_in_outbox_tengono_la_loro_origine_e_vanno_prima(banco: Banco) -> None:
    """Le voci scritte prima della riapertura restano davanti alle nuove (FIFO per chiave), con
    la LORO origine: una chiamata porta voci di UNA origine sola."""
    a = banco.apri()
    vecchia_origine = a.origine("stato_denaro")
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
    a.scrivi("betfair_live_orders", riga_ordine("r2", "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
    assert a.conferma()
    a.chiudi()                                              # nessuna consegna prima del riavvio
    a = banco.apri()
    nuova_origine = a.origine("stato_denaro")
    a.scrivi("betfair_live_orders", riga_ordine("r1", "EXECUTION_COMPLETE", "2026-10-09T09:59:00+00:00"))
    a.scrivi("betfair_live_orders", riga_ordine("r3", "EXECUTABLE", "2026-10-09T10:00:00+00:00"))
    assert a.conferma()
    voci = a.outbox_pronta("stato_denaro", 2 ** 62, 10)
    assert [v.origine for v in voci] == [vecchia_origine] * 2 + [nuova_origine] * 2
    assert [v.vseq for v in voci] == [1, 2, 3, 4]                        # la vseq del file resta monotona
    banco.drena()
    chiamate = [c for r, c in banco.server.richieste if r == "/rpc/postino_consegna"]
    # ogni voce viaggia con la SUA versione sotto la SUA origine: nessuna voce di stato senza versione
    assert [c["p_origine"] for c in chiamate] == [vecchia_origine, nuova_origine]
    assert [c["p_versioni"] for c in chiamate] == [[1, 2], [3, 4]]
    assert banco.cloud("betfair_live_orders", "client_order_ref", "r1")["status"] == "EXECUTION_COMPLETE"
    assert {r["client_order_ref"] for r in banco.server.tabelle["betfair_live_orders"].righe} == {"r1", "r2", "r3"}
    assert banco.p is not None and banco.p.stato().in_coda == 0


def test_D_rientro_superato_da_una_scrittura_di_un_altra_apertura(banco: Banco) -> None:
    """Il controllo "superata" confronta la vseq LOCALE del file, monotona fra le aperture:
    funziona anche se la scrittura piu' nuova ha un'altra origine."""
    a = banco.apri()
    prima = a.origine("stato_vivo")
    a.scrivi("live_follow", _segui(0, "VECCHIO"))
    assert a.conferma()
    voce = a.outbox_pronta("stato_vivo", 2 ** 62, 10)[0]
    # la voce muore come transitoria (come dopo 360 tentativi), con la SUA vseq e la SUA origine
    a.chiudi_voci("stato_vivo", [], [], [(voce.seq, "40001", "serializzazione", 360, "transitorio")])
    assert [(d["vseq"], d["origine"]) for d in a.dead_letter()] == [(1, prima)]
    a.chiudi()
    a = banco.apri()                                        # altra apertura, altra origine
    a.scrivi("live_follow", _segui(1, "NUOVO"))
    assert a.conferma()
    banco.drena()
    assert banco.cloud("live_follow", "event_id", "E1")["status"] == "NUOVO"
    banco.ora[0] += 16 * 60_000
    banco.drena()
    assert banco.cloud("live_follow", "event_id", "E1")["status"] == "NUOVO"
    morta = a.dead_letter()[0]
    assert morta["archiviata_ms"] is not None and "superata" in morta["nota"]
    assert "dati.dead_letter_superata" in banco.eventi


def test_D_voce_rientrata_di_un_altra_origine_resta_davanti_alla_nuova_della_stessa_chiave(banco: Banco) -> None:
    """Una voce rientrata dalla dead_letter (origine dell'apertura di prima) e una voce NUOVA della
    stessa chiave (origine di adesso) dietro di lei: chiamate separate per origine, ma la nuova
    non passa MAI davanti alla vecchia (FIFO per chiave), quindi nel cloud resta la nuova."""
    a = banco.apri()
    a.scrivi("betfair_live_orders", riga_ordine("K1", "VECCHIO", "2026-10-09T10:00:00+00:00"))   # niente coalescenza
    assert a.conferma()
    voce = a.outbox_pronta("stato_denaro", 2 ** 62, 10)[0]
    a.chiudi_voci("stato_denaro", [], [], [(voce.seq, "40001", "serializzazione", 360, "transitorio")])
    a.chiudi()
    a = banco.apri()
    a.scrivi("betfair_live_orders", riga_ordine("K2", "ALTRO", "2026-10-09T10:00:01+00:00"))  # pezzo con l'origine nuova
    assert a.conferma()
    banco.ora[0] += 16 * 60_000
    assert a.rientro_dead_letter(banco.ora[0]) == 1                        # nessuna voce piu' nuova: rientra
    a.scrivi("betfair_live_orders", riga_ordine("K1", "NUOVO", "2026-10-09T09:00:00+00:00"))
    assert a.conferma()
    assert [json.loads(v.testo)["status"] for v in a.outbox_pronta("stato_denaro", 2 ** 62, 10)] == \
        ["ALTRO", "VECCHIO", "NUOVO"]
    banco.drena()
    assert banco.cloud("betfair_live_orders", "client_order_ref", "K1")["status"] == "NUOVO"
    assert banco.p is not None and banco.p.stato().in_coda == 0


# ============================================================================ nota a
def test_a_ordine_delle_vseq_uguale_ordine_di_coda_anche_fra_thread(tmp_path: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """ordine_vseq.py del revisore, deterministico: il gancio ferma il PRIMO scrittore fra la
    vseq e l'accodamento finche' il secondo non ha finito (al massimo 0,3 s). Se le due cose
    non sono atomiche il secondo passa avanti con una vseq piu' alta e l'ordine si rovescia."""
    a = ArchivioLocale("ord", SPEC, base=tmp_path, orologio_ms=lambda: T0).apri()
    try:
        secondo_fatto = threading.Event()
        primo_fermo = threading.Event()

        def gancio(vseq: Optional[int]) -> None:
            if threading.current_thread().name == "primo" and not primo_fermo.is_set():
                primo_fermo.set()
                secondo_fatto.wait(0.3)

        monkeypatch.setattr(mod, "GANCIO_METTI", gancio)

        def scrivi(stato: str, fatto: Optional[threading.Event]) -> None:
            a.scrivi("betfair_live_orders", riga_ordine("r1", stato, "2026-10-09T10:00:00+00:00"))
            if fatto is not None:
                fatto.set()

        t1 = threading.Thread(target=scrivi, args=("PRIMO", None), name="primo")
        t1.start()
        assert primo_fermo.wait(5)
        t2 = threading.Thread(target=scrivi, args=("SECONDO", secondo_fatto), name="secondo")
        t2.start()
        t1.join(5)
        t2.join(5)
        # piu' il carico del revisore: 6 thread x 40 scritture sulla stessa chiave
        fili = [threading.Thread(target=lambda i=i: [scrivi(f"T{i}_{j}", None) for j in range(40)]) for i in range(6)]
        for f in fili:
            f.start()
        for f in fili:
            f.join(30)
        assert a.conferma(30)
        c = sqlite3.connect(str(a.cartella / "denaro.sqlite3"))
        try:
            v = [r[0] for r in c.execute("SELECT vseq FROM outbox ORDER BY seq")]
            ultima = c.execute("SELECT json FROM outbox ORDER BY seq DESC LIMIT 1").fetchone()[0]
            riga = c.execute("SELECT json, vseq FROM righe").fetchone()
        finally:
            c.close()
        assert len(v) == 2 + 240
        assert all(y > x for x, y in zip(v, v[1:])), "vseq fuori ordine rispetto alla coda"
        assert json.loads(riga[0])["status"] == json.loads(ultima)["status"] and riga[1] == v[-1]
    finally:
        a.chiudi()
