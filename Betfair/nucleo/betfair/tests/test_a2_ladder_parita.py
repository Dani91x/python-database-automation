"""W1-A2 - PARITA' del ladder (``ladder.py``) con il ladder di OGGI, sulle registrazioni vere.

Oggi (importato, mai copiato nel test):
* calcio: ``Betfair/stream/runner.py`` ``build_ladder_payload``, ``ladder_signature``
  e il ``ladder_worker`` vero (``runner.py:689-757``) con il recorder vero
  (``MarketRecorderStrategy``: ``serialize_book`` e la chiusura che marca CLOSED);
* tennis: ``Betfair/stream/tennis_live/tennis_runner.py`` ``build_ladder_payload``,
  ``ladder_signature``, ``ladder_worker`` (``:1469-1517``) con la capture vera
  (``_make_capture``);
* la cadenza e la versione: ``Betfair/stream/ladder_canale.py`` (``StatoLadder``).

I book: ogni messaggio ``mcm`` delle registrazioni ``35760084`` e ``35797769``
passato al ``StreamListener`` VERO di betfairlightweight (``test_a2_finti.libri_registrazione``).

Tre prove:
1. payload e firma identici su OGNI book (calcio e tennis);
2. la SEQUENZA del topic ``ladder`` (e delle righe del DB) identica, messaggio per
   messaggio, a quella del worker di oggi a cadenza 0 ("a ogni book"), con il
   ladder nuovo a intervallo 0: stesse righe, stesso ``json.dumps``;
3. la cadenza vera (nuovo a 20 ms contro il worker di oggi a 200 ms): ogni riga
   pubblicata dal nuovo e' una riga che il vecchio avrebbe pubblicato per quello
   stesso book; attesa "book -> pubblicazione" misurata (tempo della registrazione).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import pytest

from Betfair.nucleo.betfair import ladder as L
from Betfair.nucleo.betfair.contratto import Ladder
from Betfair.stream import ladder_canale as LC
from Betfair.stream import local_channel as LCH
from Betfair.stream import runner as R
from Betfair.stream.recorder import MarketRecorderStrategy, serialize_book
from Betfair.stream.tennis_live import tennis_runner as T

from .test_a2_finti import REGISTRAZIONI, conforme, libri_registrazione

#: book attesi (contati con il listener vero il 09/10): nessuno saltato
LIBRI_ATTESI = {"35760084": 65445, "35797769": 197229}


def passo_del_confronto(ev: str) -> int:
    """Ogni quanti book si confronta. 35760084: OGNI book, sempre. 35797769: ogni book
    con ``A2_PARITA_COMPLETA=1`` (13 min su macchina condivisa il 09/10: esito verde,
    referto W1-A2 par. 5), altrimenti uno ogni 7 (passo fisso, deterministico), per
    tenere la suite entro tempi umani. Tutti i book vengono comunque RICOSTRUITI e contati."""
    import os
    if ev == "35760084" or os.environ.get("A2_PARITA_COMPLETA") == "1":
        return 1
    return 7


def nomi_finti(serializzato: Dict[str, Any]) -> Dict[str, str]:
    """Nomi per META' delle selezioni (l'altra meta' resta senza nome: ramo None)."""
    ids = sorted(serializzato.get("runners") or {})
    return {sid: "Selezione %s" % sid for sid in ids[::2]}


def _firma_vecchia(mod: Any, libro: Dict[str, Any], payload: Dict[str, Any]) -> str:
    """La firma con lo stato come la calcolano oggi i due worker (``runner.py:727``)."""
    return (libro.get("status") or "") + "|" + mod.ladder_signature(payload["selections"])


# ---------------------------------------------------------------------------
# 1. funzioni pure su ogni book
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ev", REGISTRAZIONI)
def test_payload_e_firma_identici_su_ogni_book(ev):
    pc, pt = L.profilo_ladder("calcio"), L.profilo_ladder("tennis")
    assert (pc.livelli_max, pc.livelli_wom) == (R.LADDER_MAX_LEVELS, R.LADDER_WOM_LEVELS)
    assert (pt.livelli_max, pt.livelli_wom) == (T.LADDER_MAX_LEVELS, T.LADDER_WOM_LEVELS)
    stessi = (pc.livelli_max, pc.livelli_wom) == (pt.livelli_max, pt.livelli_wom)
    passo = passo_del_confronto(ev)
    n = confrontati = 0
    for _t, libri in libri_registrazione(ev):
        for b in libri:
            n += 1
            if (n - 1) % passo:
                continue
            confrontati += 1
            s = serialize_book(b, pc.profondita)
            nomi = nomi_finti(s)
            nuovo_c = L.payload_ladder(s, nomi, pc.livelli_max, pc.livelli_wom)
            firma_c = L.firma_con_stato(s, nuovo_c)
            for prof, mod in ((pc, R), (pt, T)):
                nuovo, firma = nuovo_c, firma_c
                if not stessi and prof is pt:
                    nuovo = L.payload_ladder(s, nomi, prof.livelli_max, prof.livelli_wom)
                    firma = L.firma_con_stato(s, nuovo)
                vecchio = mod.build_ladder_payload(s, nomi, mod.LADDER_MAX_LEVELS)
                assert nuovo == vecchio, (ev, b.market_id, prof.sport)
                assert firma == _firma_vecchia(mod, s, vecchio), (ev, b.market_id, prof.sport)
    assert n == LIBRI_ATTESI[ev]
    assert confrontati == (n + passo - 1) // passo


CASI_LIMITE = [
    {"b": [[1.5, 10.0], [1.49, None], ["x", 3], [0, 5], [-1.2, 4], [None, 2], [1.48]],
     "l": [], "ltp": None, "tv": None},
    {"b": [], "l": [], "trd": [[2.0, 0.0], [2.02, 1e9]], "ltp": 2.0, "tv": 0.0},
    {"b": [[1.01, 0.0]], "l": [[1000.0, 0.0]], "ltp": 1.01, "tv": 5.5},
    {"b": [[2.0 + i / 100.0, float(i)] for i in range(15)],
     "l": [[3.0 + i / 100.0, float(i * 2)] for i in range(15)],
     "trd": [[2.5, 1.0]] * 30, "ltp": 2.5, "tv": 1.0},
    {"b": None, "l": None, "trd": None},
]


@pytest.mark.parametrize("livelli", [None, 0, -1, 1, 3, 10])
@pytest.mark.parametrize("wom", [0, 1, 3, 20])
def test_casi_limite_identici_alle_due_copie_di_oggi(livelli, wom):
    for i, r in enumerate(CASI_LIMITE):
        for mod in (R, T):
            assert L.livelli(r.get("b"), livelli) == mod._as_levels(r.get("b"), livelli)
            back = L.livelli(r.get("b"), livelli)
            lay = L.livelli(r.get("l"), livelli)
            assert L.peso_del_denaro(back, lay, wom) == mod.compute_wom(back, lay, wom)
        nuovo = L.selezione(i + 1, r, None, livelli if livelli else 10, 3)
        assert nuovo == R.build_ladder_selection(i + 1, r, None, livelli if livelli else 10)
        assert nuovo == T.build_ladder_selection(i + 1, r, None, livelli if livelli else 10)


def test_firma_indipendente_dall_ordine_dei_runner():
    """Dopo una riconnessione la libreria puo' consegnare i runner in un altro
    ordine: la firma non deve cambiare (falsificazione A par. 5 punto 6a)."""
    libro = {"pt": 1782831952415, "status": "OPEN", "runners": {
        "58805": {"b": [[3.4, 10.0]], "l": [[3.5, 2.0]], "ltp": 3.45, "tv": 100.0},
        "22": {"b": [[2.1, 5.0]], "l": [[2.12, 7.0]], "ltp": 2.1, "tv": 50.0},
        "19": {"b": [[4.0, 1.0]], "l": [[4.2, 1.0]], "ltp": 4.1, "tv": 10.0},
    }}
    rovescio = dict(libro, runners=dict(reversed(list(libro["runners"].items()))))
    a = L.payload_ladder(libro, {}, 10, 3)
    b = L.payload_ladder(rovescio, {}, 10, 3)
    assert L.firma(a["selections"]) == L.firma(b["selections"])
    assert L.firma(b["selections"]) == R.ladder_signature(a["selections"])


# ---------------------------------------------------------------------------
# 2-3. la sequenza pubblicata: worker di oggi contro ladder nuovo
# ---------------------------------------------------------------------------
class Orologio:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class SessioneCalcio:
    """Gli attributi di ``LiveSession`` che ``runner.ladder_worker`` legge."""

    def __init__(self, recorder: Any) -> None:
        self.recorder = recorder
        self.markets_by_event: Dict[str, List[Dict[str, Any]]] = {}
        self.finished_events: set = set()
        self.selection_names: Dict[str, Dict[str, str]] = {}
        self._last_ladder_sig: Dict[str, str] = {}


class SessioneTennis:
    """Gli attributi di ``TennisLiveSession`` che ``tennis_runner.ladder_worker`` legge.
    Ogni mercato e' un "evento" con la capture CONDIVISA (come lo stream unico)."""

    def __init__(self, capture: Any) -> None:
        self.cap = capture
        self.capture: Dict[str, Any] = {}
        self.market_meta: Dict[str, Dict[str, Any]] = {}
        self._ladder_sig: Dict[str, str] = {}


class Pipeline:
    """Un ladder (vecchio o nuovo) con le sue uscite registrate per passo."""

    def __init__(self, nome: str) -> None:
        self.nome = nome
        self.canale: List[Tuple[int, float, Dict[str, Any]]] = []   # (passo, istante, riga)
        self.db: List[Tuple[int, Dict[str, Any]]] = []
        self.passo = 0
        self.ora = 0.0


def _meta_da(libro: Any, ev_finto: str) -> Tuple[Optional[str], str]:
    md = getattr(libro, "market_definition", None)
    tipo = getattr(md, "market_type", None) if md is not None else None
    return tipo, ev_finto


class Banco:
    """Fa girare insieme: worker di oggi (calcio o tennis) e ``LadderEvento``."""

    def __init__(self, sport: str, monkeypatch: Any, canale_ms_vecchio: int,
                 intervallo_nuovo_ms: int) -> None:
        self.sport = sport
        self.orologio = Orologio()
        self.vecchio = Pipeline("vecchio")
        self.nuovo = Pipeline("nuovo")
        self.meta: Dict[str, L.MetaLadder] = {}
        self.arrivo: Dict[str, float] = {}
        monkeypatch.setattr(LC, "_adesso", self.orologio)
        monkeypatch.setattr(LCH, "channel_active", lambda: True)
        monkeypatch.setattr(LCH, "publish", self._pub_vecchio)
        if sport == "calcio":
            monkeypatch.setattr(R, "LADDER_CANALE_MS", canale_ms_vecchio)
            monkeypatch.setattr(R.db, "upsert_live_ladder", self._db_vecchio)
            self.rec = MarketRecorderStrategy(
                market_filter={"marketIds": []}, name="rec_banco_a2",
                context={"data_dir": ".", "market_to_event": {}, "market_type_by_id": {},
                         "event_markets": {}, "depth": R.LADDER_DEPTH,
                         "record_events": lambda: set()})
            self.sess: Any = SessioneCalcio(self.rec)
        else:
            monkeypatch.setattr(T, "LADDER_CANALE_MS", canale_ms_vecchio)
            monkeypatch.setattr(T.tennis_db, "upsert_tennis_ladder", self._db_vecchio)
            self.cap = T._make_capture("1.0", "0", market_ids=["1.0"], nome="cap_banco_a2")
            self.sess = SessioneTennis(self.cap)
        self.lad = L.LadderEvento(
            L.profilo_ladder(sport), meta=self.meta.get, pubblica=self._pub_nuovo,
            scrivi_db=self._db_nuovo, intervallo_min_ms=intervallo_nuovo_ms,
            orologio=self.orologio)
        self._ultimo_db_nuovo: Optional[float] = None
        self.canale_sec_vecchio = canale_ms_vecchio / 1000.0
        self._ultimo_giro_vecchio: Optional[float] = None
        self._prossima_nuova: Optional[float] = None

    # --- uscite
    def _pub_vecchio(self, topic: str, riga: Dict[str, Any]) -> None:
        assert topic == "ladder"
        self.vecchio.canale.append((self.vecchio.passo, self.orologio.t, riga))

    def _pub_nuovo(self, topic: str, riga: Dict[str, Any]) -> None:
        assert topic == "ladder"
        self.nuovo.canale.append((self.nuovo.passo, self.orologio.t, riga))

    def _db_vecchio(self, riga: Dict[str, Any]) -> None:
        self.vecchio.db.append((self.vecchio.passo, riga))

    def _db_nuovo(self, riga: Dict[str, Any]) -> None:
        self.nuovo.db.append((self.nuovo.passo, riga))

    # --- registro dei mercati (catalogo della sessione di oggi / meta del nuovo)
    def _registra(self, libro: Any) -> None:
        mid = str(libro.market_id)
        if mid in self.meta:
            return
        tipo, _ = _meta_da(libro, "")
        ev = "ev-" + mid if self.sport == "tennis" else "35760000"
        nomi = {str(r.selection_id): "Selezione %s" % r.selection_id
                for r in (libro.runners or [])[::2]}
        self.meta[mid] = L.MetaLadder(event_id=ev, market_type=tipo,
                                      market_name="Mercato %s" % tipo, nomi=nomi)
        if self.sport == "calcio":
            self.rec.context["market_to_event"][mid] = ev
            self.sess.markets_by_event.setdefault(ev, []).append(
                {"market_id": mid, "market_type": tipo, "market_name": "Mercato %s" % tipo})
            self.sess.selection_names[mid] = dict(nomi)
        else:
            self.sess.capture[ev] = self.cap
            self.sess.market_meta[ev] = {"market_id": mid, "market_type": tipo,
                                         "market_name": "Mercato %s" % tipo,
                                         "selection_names": dict(nomi)}

    # --- i due mondi
    def _vecchio_riceve(self, libro: Any) -> None:
        strat = self.rec if self.sport == "calcio" else self.cap
        if libro.status == "CLOSED":       # flumine: CloseMarketEvent (baseflumine.py:158-160)
            strat.process_closed_market(None, libro)
        else:
            strat.process_market_book(None, libro)

    def _giro_vecchio(self) -> None:
        if self.sport == "calcio":
            R.ladder_worker({}, None, self.sess)
        else:
            T.ladder_worker({}, None, self.sess)

    def _giro_db_nuovo(self) -> None:
        """La cadenza DB del ladder nuovo = quella di oggi (``StatoLadder.giro``)."""
        t = self.orologio.t
        if self._ultimo_db_nuovo is None or t - self._ultimo_db_nuovo >= self.lad.profilo.db_sec - 1e-3:
            self._ultimo_db_nuovo = t
            self.lad.esegui_db(t)

    def passo(self, i: int, t: float, libri: List[Any], ogni_messaggio: bool) -> None:
        # timer del nuovo: le scadenze maturate prima di questo messaggio
        while self._prossima_nuova is not None and self._prossima_nuova <= t:
            self.orologio.t = self._prossima_nuova
            self.nuovo.passo = i - 1
            self._prossima_nuova = self.lad.esegui_scaduti(self.orologio.t)
        # timer del vecchio: i giri fissi maturati prima di questo messaggio
        if not ogni_messaggio:
            while (self._ultimo_giro_vecchio is not None
                   and self._ultimo_giro_vecchio + self.canale_sec_vecchio <= t):
                self._ultimo_giro_vecchio += self.canale_sec_vecchio
                self.orologio.t = self._ultimo_giro_vecchio
                self.vecchio.passo = i - 1
                self._giro_vecchio()
        self.orologio.t = t
        self.vecchio.passo = self.nuovo.passo = i
        for b in libri:
            self._registra(b)
            self.arrivo[str(b.market_id)] = t
            self._vecchio_riceve(b)
            self.lad.consumatore(b)
        if ogni_messaggio:
            self._giro_vecchio()
        elif self._ultimo_giro_vecchio is None:
            self._ultimo_giro_vecchio = t
            self._giro_vecchio()
        prossima = self.lad.esegui_scaduti(t)
        if prossima is not None:
            self._prossima_nuova = (prossima if self._prossima_nuova is None
                                    else min(self._prossima_nuova, prossima))
        if ogni_messaggio:
            self._giro_db_nuovo()


def _forma(riga: Dict[str, Any]) -> Tuple[Any, ...]:
    """Ordine delle chiavi (cio' che, a parita' di valori, fa lo stesso json.dumps)."""
    lad = riga["ladder"]
    return (tuple(riga), tuple(lad), tuple(tuple(s) for s in lad["selections"]))


def _confronta_passo(vecchie: List[Dict[str, Any]], nuove: List[Dict[str, Any]],
                     passo: int, conti: Dict[str, int]) -> None:
    """Le righe di UN passo: stessi valori, stesso ordine delle chiavi; ogni 25 il
    ``json.dumps`` intero byte per byte."""
    v = sorted(vecchie, key=lambda r: r["market_id"])
    n = sorted(nuove, key=lambda r: r["market_id"])
    assert [r["market_id"] for r in n] == [r["market_id"] for r in v], passo
    for a, b in zip(v, n):
        assert b == a, (passo, a["market_id"])
        assert _forma(b) == _forma(a), (passo, a["market_id"])
        conti["righe"] += 1
        if conti["righe"] % 25 == 0:
            assert json.dumps(b) == json.dumps(a)
            conti["json"] += 1


@pytest.mark.parametrize("sport", ["calcio", "tennis"])
def test_sequenza_del_topic_identica_al_worker_di_oggi(sport, monkeypatch):
    banco = Banco(sport, monkeypatch, canale_ms_vecchio=0, intervallo_nuovo_ms=0)
    conti = {"righe": 0, "json": 0, "db": 0}
    ultimo: Dict[str, int] = {}
    chiusi: set = set()
    for i, (t, libri) in enumerate(libri_registrazione("35760084")):
        banco.passo(i, t, libri, ogni_messaggio=True)
        v, n = banco.vecchio, banco.nuovo
        _confronta_passo([r for _p, _t, r in v.canale], [r for _p, _t, r in n.canale], i, conti)
        dv, dn = [r for _p, r in v.db], [r for _p, r in n.db]
        _confronta_passo(dv, dn, i, {"righe": 0, "json": 0})
        conti["db"] += len(dn)
        for _p, _t, riga in n.canale:
            # updated_ms strettamente crescente per mercato (``piuFresca`` della UI)
            um = riga["ladder"]["updated_ms"]
            assert um > ultimo.get(riga["market_id"], -1)
            ultimo[riga["market_id"]] = um
            if riga["status"] == "CLOSED":
                chiusi.add(riga["market_id"])
        v.canale.clear(), n.canale.clear(), v.db.clear(), n.db.clear()
    assert conti["righe"] > 10_000 and conti["json"] > 400 and conti["db"] > 100
    assert len(chiusi) == 21                 # i mercati chiusi escono CLOSED come oggi


def misura_cadenza(ev: str, sport: str, monkeypatch: Any) -> Dict[str, Any]:
    """Nuovo a 20 ms contro oggi a 200 ms sulla registrazione ``ev`` (tempo = ``pt``).

    Ritorna i conteggi, le attese "arrivo del book -> pubblicazione" in ms e
    quante righe del nuovo NON sono quelle che il codice di oggi pubblicherebbe
    per lo stesso stato (cache vera del recorder/capture + ``build_ladder_payload``
    vero, calcolati nell'istante della pubblicazione)."""
    banco = Banco(sport, monkeypatch, canale_ms_vecchio=200, intervallo_nuovo_ms=20)
    mod = R if sport == "calcio" else T
    attese: Dict[str, List[float]] = {"vecchio": [], "nuovo": []}
    estranee = [0]
    violazioni = [0]                        # due pubblicazioni dello stesso mercato < 20 ms
    ultima_pub: Dict[str, float] = {}
    pub_v, pub_n = banco._pub_vecchio, banco._pub_nuovo

    def vecchio(topic: str, riga: Dict[str, Any]) -> None:
        attese["vecchio"].append((banco.orologio.t - banco.arrivo[riga["market_id"]]) * 1000.0)
        pub_v(topic, riga)

    def nuovo(topic: str, riga: Dict[str, Any]) -> None:
        mid = riga["market_id"]
        attese["nuovo"].append((banco.orologio.t - banco.arrivo[mid]) * 1000.0)
        prec = ultima_pub.get(mid)
        # tolleranza 1 us: a 1,78e9 s un float ha passo ~2e-7 s
        if prec is not None and banco.orologio.t - prec < 0.020 - 1e-6:
            violazioni[0] += 1
        ultima_pub[mid] = banco.orologio.t
        cache = banco.rec.latest_books() if sport == "calcio" else banco.cap.latest()
        s = cache.get(mid)
        atteso = mod.build_ladder_payload(s, dict(banco.meta[mid].nomi), mod.LADDER_MAX_LEVELS)
        if s.get("status") != riga["status"] or atteso["selections"] != riga["ladder"]["selections"]:
            estranee[0] += 1
        pub_n(topic, riga)
    monkeypatch.setattr(LCH, "publish", vecchio)
    banco.lad._pubblica = nuovo
    n_v = n_n = 0
    for i, (t, libri) in enumerate(libri_registrazione(ev)):
        banco.passo(i, t, libri, ogni_messaggio=False)
        n_v += len(banco.vecchio.canale)
        n_n += len(banco.nuovo.canale)
        banco.vecchio.canale.clear(), banco.nuovo.canale.clear()

    def quantile(xs: List[float], q: float) -> float:
        ys = sorted(xs)
        return round(ys[min(len(ys) - 1, int(q * len(ys)))], 1) if ys else 0.0

    def riassunto(xs: List[float]) -> Dict[str, float]:
        return {"p50": quantile(xs, 0.5), "p95": quantile(xs, 0.95), "max": quantile(xs, 1.0),
                "media": round(sum(xs) / len(xs), 1) if xs else 0.0}
    return {
        "registrazione": ev, "sport": sport,
        "pubblicati_vecchio_200ms": n_v, "pubblicati_nuovo_20ms": n_n,
        "attesa_ms_vecchio": riassunto(attese["vecchio"]),
        "attesa_ms_nuovo": riassunto(attese["nuovo"]),
        "righe_nuove_estranee": estranee[0],
        "pubblicazioni_sotto_20ms": violazioni[0],
        "fusi_nuovo": int(banco.lad.conti["fusi"]),
    }


def test_cadenza_20ms_contro_200ms_su_registrazione(monkeypatch):
    m = misura_cadenza("35760084", "calcio", monkeypatch)
    assert m["righe_nuove_estranee"] == 0
    assert m["pubblicazioni_sotto_20ms"] == 0              # la coalescenza tiene
    assert m["attesa_ms_nuovo"]["max"] <= 20.0 + 1e-6      # mai oltre la coalescenza
    assert m["attesa_ms_vecchio"]["p50"] > m["attesa_ms_nuovo"]["p50"]
    assert m["pubblicati_nuovo_20ms"] > m["pubblicati_vecchio_200ms"]


def test_conforme_al_contratto():
    assert conforme(L.LadderEvento, Ladder) == []
