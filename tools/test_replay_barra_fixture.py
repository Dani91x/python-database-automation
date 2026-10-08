"""Contratto del generatore di fixture della barra di Match Replay (07/10/2026).

Lancio (dalla radice del repository):

    python3 -m pytest tools/test_replay_barra_fixture.py -q -p no:cacheprovider

Cosa prova:
  1. ogni registrazione in `registrazioni_banco/<event>/` ha la sua fixture
     `frontend/src/lib/__fixtures__/replay_barra_<event>.json` e porta l'impronta
     (sha256) dei file da cui deriva: se manca o e' vecchia, il test e' rosso e dice il
     comando da lanciare (stessa regola del test vitest su tutte le partite);
  2. la fixture e' RIPRODUCIBILE: rigenerarla dal raw da' gli stessi byte (curator vero,
     campionamento del server, riduzione). Dura circa un minuto per partita; si salta con
     `BARRA_FIXTURE_SALTA_RIGENERAZIONE=1` quando serve un giro veloce;
  3. il campionamento che riproduce `get_replay_frames` / `fetchReplayChunked` ha le regole
     del server: un frame per (mercato, bucket), il primo del bucket, ordine per mercato e
     bucket, bucket pre-match e in-gioco adattivi con i loro limiti, pre-match al massimo
     4 ore prima del calcio d'inizio.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

_QUI = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("replay_barra_fixture", os.path.join(_QUI, "replay_barra_fixture.py"))
gen = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gen)

EVENTI = gen.eventi_registrati()


def test_ci_sono_registrazioni():
    assert EVENTI, "nessuna registrazione in registrazioni_banco/: il test non verificherebbe nulla"


@pytest.mark.parametrize("ev", EVENTI)
def test_fixture_presente_e_aggiornata(ev):
    percorso = gen.nome_fixture(ev)
    comando = f"python3 tools/replay_barra_fixture.py {ev}"
    assert os.path.exists(percorso), f"manca {percorso}: generala con `{comando}`"
    import json

    with open(percorso, "r", encoding="utf-8") as fh:
        fx = json.load(fh)
    assert fx.get("sorgente") == gen.impronte_sorgente(ev), f"la registrazione {ev} e' cambiata: rigenera con `{comando}`"
    assert {"ts_min", "ts_max", "inplay_from_ts"} <= set(fx["meta"]), f"fixture senza estremi: rigenera con `{comando}`"


@pytest.mark.skipif(os.environ.get("BARRA_FIXTURE_SALTA_RIGENERAZIONE") == "1", reason="rigenerazione saltata su richiesta")
@pytest.mark.parametrize("ev", EVENTI)
def test_fixture_riproducibile_dal_raw(ev):
    atteso = open(gen.nome_fixture(ev), "r", encoding="utf-8").read()
    assert gen.serializza(gen.costruisci_fixture(ev)) == atteso, (
        f"la fixture di {ev} non coincide con quella rigenerata dal raw: "
        f"rilancia `python3 tools/replay_barra_fixture.py {ev}` e rivedi il diff"
    )


# ---------------------------------------------------------------------------
# il campionamento del server, su dati sintetici piccoli
# ---------------------------------------------------------------------------
def _riga(mercato, secondi, inplay=False, minuto=None):
    """Riga di live_market_snapshots come la produce il curator (chiavi e tipi del vero)."""
    from datetime import datetime, timezone

    t = 1_800_000_000 + secondi
    return {
        "event_id": "1", "market_id": mercato,
        "ts": datetime.fromtimestamp(t, tz=timezone.utc).isoformat(), "minute": minuto,
        "inplay": inplay, "status": "OPEN", "ladder": {},
    }


def test_un_frame_per_mercato_e_bucket_il_primo_e_in_ordine_mercato_poi_bucket():
    # in-gioco da subito, 1 mercato: il bucket e' ceil(span*n/9000) con minimo 2 s
    righe = [_riga("1.2", 0, True), _riga("1.1", 0, True), _riga("1.1", 1, True), _riga("1.1", 5, True), _riga("1.2", 5, True)]
    frames, meta = gen.campiona_come_la_pagina(righe, 1)
    assert meta["bucket_in_sec"] == 2
    visti = [(f["market_id"], f["ts"][17:19]) for f in frames]
    # 1.1: bucket {0,1} -> primo (t=0); bucket {5} -> t=5. 1.2: t=0 e t=5. Ordine: per mercato e bucket
    assert visti == [("1.1", "00"), ("1.1", "05"), ("1.2", "00"), ("1.2", "05")]


def test_bucket_adattivi_con_i_loro_limiti_e_pre_match_al_massimo_4_ore():
    # 6 ore di pre-match e 1 ora di partita, 22 mercati
    righe = [_riga("1.1", 0), _riga("1.1", 6 * 3600, True), _riga("1.1", 7 * 3600, True)]
    _, meta = gen.campiona_come_la_pagina(righe, 22)
    # pre-match cappato a 4 h: ceil(14400*22/2500)=127 s ; in gioco: ceil(3600*22/9000)=9 s
    assert meta["bucket_pre_sec"] == 127
    assert meta["bucket_in_sec"] == 9
    # limiti: pre-match >= 30 s e <= 300 s; in-gioco >= 2 s e <= 60 s
    _, m1 = gen.campiona_come_la_pagina([_riga("1.1", 0), _riga("1.1", 100, True), _riga("1.1", 130, True)], 1)
    assert m1["bucket_pre_sec"] == 30 and m1["bucket_in_sec"] == 2
    _, m2 = gen.campiona_come_la_pagina([_riga("1.1", 0), _riga("1.1", 4 * 3600, True), _riga("1.1", 4 * 3600 + 3 * 3600, True)], 40)
    assert m2["bucket_pre_sec"] == 231 and m2["bucket_in_sec"] == 48
    _, m3 = gen.campiona_come_la_pagina([_riga("1.1", 0), _riga("1.1", 4 * 3600, True), _riga("1.1", 4 * 3600 + 3 * 3600, True)], 200)
    assert m3["bucket_pre_sec"] == 300 and m3["bucket_in_sec"] == 60


def test_i_frame_prima_delle_4_ore_di_pre_match_non_arrivano_alla_pagina():
    righe = [_riga("1.1", 0), _riga("1.1", 3600), _riga("1.1", 6 * 3600 + 10, True), _riga("1.1", 6 * 3600 + 20, True)]
    frames, _ = gen.campiona_come_la_pagina(righe, 1)
    # la pagina parte da (primo in gioco - 4 ore) = 2 h dopo l'inizio: il frame di t=0 e di t=1 h non c'e'
    assert [f["ts"][11:19] for f in frames][0:1] != [righe[0]["ts"][11:19]]
    assert all(f["_ms"] >= (1_800_000_000 + 6 * 3600 + 10) * 1000 - 4 * 3600_000 for f in frames)


def test_estremi_come_get_replay_meta_e_serializzazione_deterministica():
    righe = [_riga("1.1", 10), _riga("1.1", 40, True), _riga("1.2", 90, True)]
    _, meta = gen.campiona_come_la_pagina(righe, 2)
    assert meta["ts_min"] == righe[0]["ts"] and meta["ts_max"] == righe[2]["ts"] and meta["inplay_from_ts"] == righe[1]["ts"]
    assert gen.serializza({"b": 1, "a": [1, 2]}) == gen.serializza({"b": 1, "a": [1, 2]})
    assert gen.serializza({"a": 1}).endswith("\n")


# ---------------------------------------------------------------------------
# 08/10 (cantiere 12): l'impronta dei .jsonl e' INDIPENDENTE DAI FINE RIGA
# (CRLF su Windows con core.autocrlf=true, LF nel repository); i .gz non si toccano
# ---------------------------------------------------------------------------
def _scrivi_registrazione(radice, ev, timeline: bytes, gz: bytes):
    """Cartella di registrazione minima: timeline in chiaro, raw e scores come .gz (chiavi come nel repository)."""
    d = os.path.join(radice, ev)
    os.makedirs(d, exist_ok=True)
    for nome, dati in ((f"{ev}.timeline.jsonl", timeline), (f"{ev}.raw.jsonl.gz", gz), (f"{ev}.scores.jsonl.gz", gz)):
        with open(os.path.join(d, nome), "wb") as fh:
            fh.write(dati)


def test_impronta_uguale_con_fine_riga_lf_e_crlf(tmp_path):
    lf = b'{"a": 1}\n{"b": 2}\n{"c": 3}\n'
    crlf = lf.replace(b"\n", b"\r\n")
    assert lf != crlf  # la copia CRLF e' davvero diversa sul disco
    _scrivi_registrazione(str(tmp_path / "lf"), "9", lf, b"gz")
    _scrivi_registrazione(str(tmp_path / "crlf"), "9", crlf, b"gz")
    a = gen.impronte_sorgente("9", str(tmp_path / "lf"))
    b = gen.impronte_sorgente("9", str(tmp_path / "crlf"))
    assert a == b
    assert a["9.timeline.jsonl"] is not None


def test_impronta_dei_gz_non_normalizza_i_fine_riga(tmp_path):
    # dentro un gzip la coppia 0d 0a puo' capitare per caso: non e' un fine riga e non va toccata
    _scrivi_registrazione(str(tmp_path / "a"), "9", b"x\n", b"ab\r\ncd")
    _scrivi_registrazione(str(tmp_path / "b"), "9", b"x\n", b"ab\ncd")
    a = gen.impronte_sorgente("9", str(tmp_path / "a"))
    b = gen.impronte_sorgente("9", str(tmp_path / "b"))
    assert a["9.raw.jsonl"] != b["9.raw.jsonl"]
    assert a["9.scores.jsonl"] != b["9.scores.jsonl"]
    assert a["9.timeline.jsonl"] == b["9.timeline.jsonl"]


def test_impronta_crlf_a_cavallo_del_blocco_di_lettura(tmp_path):
    # il CR e' l'ultimo byte del primo blocco da 1 MiB e il LF il primo del secondo
    lf = b"x" * ((1 << 20) - 1) + b"\n" + b"y\n"
    crlf = b"x" * ((1 << 20) - 1) + b"\r\n" + b"y\r\n"
    assert crlf[(1 << 20) - 1:(1 << 20) + 1] == b"\r\n" and crlf[(1 << 20) - 1] == 13
    _scrivi_registrazione(str(tmp_path / "lf"), "9", lf, b"gz")
    _scrivi_registrazione(str(tmp_path / "crlf"), "9", crlf, b"gz")
    assert gen.impronte_sorgente("9", str(tmp_path / "lf")) == gen.impronte_sorgente("9", str(tmp_path / "crlf"))


def test_un_cr_isolato_non_e_un_fine_riga_e_resta_nell_impronta(tmp_path):
    _scrivi_registrazione(str(tmp_path / "a"), "9", b"a\rb\n", b"gz")
    _scrivi_registrazione(str(tmp_path / "b"), "9", b"a\nb\n", b"gz")
    _scrivi_registrazione(str(tmp_path / "c"), "9", b"a", b"gz")
    _scrivi_registrazione(str(tmp_path / "d"), "9", b"a\r", b"gz")  # CR finale del file: va incluso
    assert gen.impronte_sorgente("9", str(tmp_path / "a")) != gen.impronte_sorgente("9", str(tmp_path / "b"))
    assert gen.impronte_sorgente("9", str(tmp_path / "c")) != gen.impronte_sorgente("9", str(tmp_path / "d"))


@pytest.mark.parametrize("ev", EVENTI)
def test_le_impronte_lf_delle_fixture_esistenti_restano_identiche(ev, tmp_path):
    """Le fixture NON si rigenerano: l'impronta di oggi (qualunque fine riga abbia il disco) coincide con quella
    scritta nella fixture, e con quella di una copia CRLF della stessa registrazione."""
    import json
    import shutil

    sorgente = os.path.join(gen.CARTELLA_REGISTRAZIONI, ev)
    with open(gen.nome_fixture(ev), "r", encoding="utf-8") as fh:
        atteso = json.load(fh)["sorgente"]
    copia = str(tmp_path / "crlf")
    os.makedirs(os.path.join(copia, ev))
    for nome in os.listdir(sorgente):
        p = os.path.join(sorgente, nome)
        if not os.path.isfile(p):
            continue
        dati = open(p, "rb").read()
        if nome.endswith(".jsonl"):  # solo i file in chiaro vengono riscritti con CRLF
            dati = dati.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        with open(os.path.join(copia, ev, nome), "wb") as fh:
            fh.write(dati)
    assert gen.impronte_sorgente(ev) == atteso
    assert gen.impronte_sorgente(ev, copia) == atteso
    shutil.rmtree(copia)


# ---------------------------------------------------------------------------
# 08/10 (cantiere 13): una partita del DATABASE si riproduce dal suo raw (sul PC, `_live_raw/`)
# fuori dal repository: --registrazioni (radice delle registrazioni) e --uscita (cartella)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(os.environ.get("BARRA_FIXTURE_SALTA_RIGENERAZIONE") == "1", reason="rigenerazione saltata su richiesta")
def test_registrazioni_e_uscita_fuori_dal_repository(tmp_path, capsys):
    import json
    import shutil

    ev = "35760084" if "35760084" in EVENTI else EVENTI[0]
    radice = tmp_path / "live_raw"
    shutil.copytree(os.path.join(gen.CARTELLA_REGISTRAZIONI, ev), radice / ev)
    uscita = tmp_path / "fixture"
    assert gen.eventi_registrati(str(radice)) == [ev]
    assert gen.main(["--registrazioni", str(radice), "--uscita", str(uscita), "--tutte"]) == 0
    scritta = (uscita / f"replay_barra_{ev}.json").read_text(encoding="utf-8")
    # stessa registrazione, stessi byte della fixture del repository (impronte comprese)
    assert scritta == open(gen.nome_fixture(ev), "r", encoding="utf-8").read()
    assert gen.main(["--registrazioni", str(radice), "--uscita", str(uscita), "--verifica", ev]) == 0
    # la fixture del repository NON e' stata toccata e l'uscita dice dove ha scritto
    assert f"{ev}: scritta" in capsys.readouterr().out
    # i file letti sono davvero quelli della cartella indicata (punteggi e timeline compresi): una copia con la
    # timeline VUOTA da' una fixture senza righe-evento e con l'impronta della timeline vuota
    radice2 = tmp_path / "live_raw_2"
    shutil.copytree(radice / ev, radice2 / ev)
    (radice2 / ev / f"{ev}.timeline.jsonl").write_bytes(b"")
    fx2 = gen.costruisci_fixture(ev, str(radice2))
    assert [r for r in fx2["score_timeline"] if r[5]] == []
    assert any(r[5] for r in json.loads(scritta)["score_timeline"])
    import hashlib

    assert fx2["sorgente"][f"{ev}.timeline.jsonl"] == hashlib.sha256(b"").hexdigest()
    # una cartella senza la partita: errore chiaro, nessun file scritto
    with pytest.raises(FileNotFoundError):
        gen.main(["--registrazioni", str(tmp_path / "vuota"), "--uscita", str(tmp_path / "x"), ev])
    assert not (tmp_path / "x" / f"replay_barra_{ev}.json").exists()


def test_cartelle_di_serie_invariate():
    # senza le opzioni nuove i percorsi sono quelli di prima (repository)
    assert gen.nome_fixture("1") == os.path.join(gen.CARTELLA_FIXTURE, "replay_barra_1.json")
    assert gen.eventi_registrati() == gen.eventi_registrati(gen.CARTELLA_REGISTRAZIONI)
