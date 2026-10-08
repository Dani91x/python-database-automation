"""08/10 (cantiere 10) - CONTRATTO Python <-> TypeScript sulla forma di ``cicli_bot``.

Il registro operazioni del replay usa ESATTAMENTE i cicli che il bot dichiara
(``esito.cicli_bot``, scritto da ``applica_bot.cicli_dichiarati`` sopra
``replay_registrazioni.riepilogo_cicli_media``). La UI li legge col tipo
``CicloDichiarato`` di ``frontend/src/lib/replayBot.ts``: le chiavi (e i tipi)
devono essere IDENTICHE da tutte e due le parti, altrimenti la UI legge un campo
che non c'e' (undefined) o ignora un dato del bot.

Due fonti Python, entrambe vere:
* il codice di produzione di oggi: ``riepilogo_cicli_media`` sugli ordini VERI di
  flumine del banco della media under (stesso banco dei test del giro 2, due
  cicli: uno chiuso con la banca abbinata, uno aperto con rientro), poi
  ``cicli_dichiarati`` con l'origine nella forma di ``media_origini_cicli``;
* gli esiti VERI del banco che i test della UI usano
  (``frontend/src/lib/__fixtures__/replay_pro/esito_media_*.json``).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Tuple
from unittest import mock

import pytest

from Betfair.stream.backtest import applica_bot as AB
from Betfair.stream.backtest import minimi_banco as MB
from Betfair.stream.scalper.tools import replay_registrazioni as R
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)
from Betfair.stream.tests.banco_media_under import KO_MS
from Betfair.stream.tests.test_scalper_media_under_giro2_2026_10_05 import _due_cicli

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
REPLAY_BOT_TS = os.path.join(RADICE, "frontend", "src", "lib", "replayBot.ts")
FIXTURE = os.path.join(RADICE, "frontend", "src", "lib", "__fixtures__", "replay_pro")


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    """Esecuzione dei pacchetti di flumine differita di 1 e di 4 book (come il giro 2)."""
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


@pytest.fixture
def exchange_it():
    with MB.minimi_it_su_flumine() as registro:
        yield registro


# ---------------------------------------------------------------------------
# lettura del tipo TypeScript (solo interfacce piatte: un campo per riga)
# ---------------------------------------------------------------------------
def interfaccia_ts(nome: str, testo: str) -> Dict[str, Tuple[str, bool]]:
    """I campi di ``export interface <nome> { ... }``: nome -> (tipo, opzionale)."""
    m = re.search(r"export interface %s \{\n(.*?)\n\}" % re.escape(nome), testo, re.S)
    assert m, "interfaccia %s assente in replayBot.ts" % nome
    corpo = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    campi: Dict[str, Tuple[str, bool]] = {}
    for riga in corpo.splitlines():
        riga = re.sub(r"//.*$", "", riga).strip()
        if not riga:
            continue
        r = re.match(r"^(\w+)(\?)?:\s*(.+?);$", riga)
        assert r, "riga del tipo %s non letta: %r" % (nome, riga)
        campi[r.group(1)] = (r.group(3).strip(), bool(r.group(2)))
    return campi


def _testo_ts() -> str:
    with open(REPLAY_BOT_TS, encoding="utf-8") as fh:
        return fh.read()


def conforme(valore: Any, tipo: str, testo: str) -> bool:
    """Il valore JSON rispetta il tipo TypeScript (le forme usate da CicloDichiarato)."""
    alternative = [t.strip() for t in tipo.split("|")]
    for t in alternative:
        if t == "null" and valore is None:
            return True
        if t == "number" and isinstance(valore, (int, float)) and not isinstance(valore, bool):
            return True
        if t == "string" and isinstance(valore, str):
            return True
        if t == "Record<string, never>" and valore == {}:
            return True
        if t.endswith("[]") and isinstance(valore, list):
            el = t[:-2]
            if all(conforme(v, el, testo) for v in valore):
                return True
        if re.match(r"^[A-Z]\w*$", t) and isinstance(valore, dict):
            if diff_oggetto(valore, t, testo) == []:
                return True
    return False


def diff_oggetto(obj: Dict[str, Any], nome: str, testo: str) -> List[str]:
    """Le differenze fra un oggetto JSON e l'interfaccia TS ``nome`` (vuoto = conforme)."""
    campi = interfaccia_ts(nome, testo)
    out: List[str] = []
    for k in sorted(set(obj) - set(campi)):
        out.append("%s: chiave '%s' scritta da Python e assente nel tipo TS" % (nome, k))
    for k, (tipo, opz) in sorted(campi.items()):
        if k not in obj:
            if not opz:
                out.append("%s: chiave '%s' del tipo TS mai scritta da Python" % (nome, k))
            continue
        if not conforme(obj[k], tipo, testo):
            out.append("%s.%s = %r non e' %s" % (nome, k, obj[k], tipo))
    return out


# ---------------------------------------------------------------------------
# 1. il codice di produzione di oggi
# ---------------------------------------------------------------------------
def test_cicli_dichiarati_dal_codice_hanno_la_forma_del_tipo_ts(differita, exchange_it):
    b, ora = _due_cicli(differita)
    cicli, _conto = R.riepilogo_cicli_media(
        b.ordini(), b.nati, ora.abbinato_ms, ora.eventi, ko_ms=KO_MS, in_gioco_ms=None,
        commissione=0.05, stato_runner=None)
    assert len(cicli) == 2
    # l'origine nella forma che il replay scrive (``media_origini_cicli``):
    # ciclo 1 da un clic, ciclo 2 senza origine dichiarata (null)
    p1 = next(o for o in b.ordini() if str(o.id) in cicli[0]["ordini_id"])
    origini = [{"ciclo": 1, "ms": int(b.nati[str(p1.id)]), "origine": "clic",
                "clic": "clic-1-%d" % int(b.nati[str(p1.id)]), "ordine": str(p1.id)}]
    ref = mock.Mock(stats_finali={"media_riepilogo_cicli": cicli, "media_origini_cicli": origini})
    dichiarati = AB.cicli_dichiarati(ref)
    assert dichiarati is not None and len(dichiarati) == 2
    testo = _testo_ts()
    # il ciclo chiuso ha la banca (oggetto pieno), quello aperto senza fine ne' lordo
    assert dichiarati[0]["banca"] and dichiarati[0]["origine"] == "clic"
    assert dichiarati[1]["origine"] is None and dichiarati[1]["lordo"] is None
    for c in dichiarati:
        assert diff_oggetto(c, "CicloDichiarato", testo) == []
    # il JSON (come lo legge la UI) non cambia la forma
    for c in json.loads(json.dumps(dichiarati)):
        assert diff_oggetto(c, "CicloDichiarato", testo) == []


# ---------------------------------------------------------------------------
# 2. gli esiti VERI del banco usati dai test della UI
# ---------------------------------------------------------------------------
ESITI_CON_CICLI = sorted(f for f in os.listdir(FIXTURE)
                         if f.startswith("esito_media_") and f.endswith(".json"))


def test_ci_sono_esiti_veri_con_i_cicli_del_bot():
    assert len(ESITI_CON_CICLI) >= 4


@pytest.mark.parametrize("nome", ESITI_CON_CICLI)
def test_cicli_bot_degli_esiti_veri_hanno_la_forma_del_tipo_ts(nome):
    with open(os.path.join(FIXTURE, nome), encoding="utf-8") as fh:
        e = json.load(fh)
    assert e["cicli_bot"], nome
    testo = _testo_ts()
    for c in e["cicli_bot"]:
        assert diff_oggetto(c, "CicloDichiarato", testo) == [], nome


def test_il_controllo_della_forma_sa_diventare_rosso():
    """Il contratto non e' cieco: una chiave in piu', una in meno o un tipo
    sbagliato vengono segnalati."""
    with open(os.path.join(FIXTURE, ESITI_CON_CICLI[0]), encoding="utf-8") as fh:
        c = dict(json.load(fh)["cicli_bot"][0])
    testo = _testo_ts()
    assert diff_oggetto(dict(c, extra=1), "CicloDichiarato", testo) != []
    senza = dict(c)
    del senza["fine_ms"]
    assert diff_oggetto(senza, "CicloDichiarato", testo) != []
    assert diff_oggetto(dict(c, lordo="0.02"), "CicloDichiarato", testo) != []
    assert diff_oggetto(dict(c, ordini_id=[1]), "CicloDichiarato", testo) != []
    assert diff_oggetto(dict(c, banca={"importo": 1.0}), "CicloDichiarato", testo) != []
