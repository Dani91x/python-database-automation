"""W1-C2 - decisione 5 dell'utente (10/10/2026): il "se vince" sul ladder per OGNI mercato.

Come i competitor (Bet Angel, Geeks Toy): il "se vince" PER SELEZIONE (o per LINEA,
selezione + handicap) si calcola su ogni mercato con la stessa formula: P&L degli
abbinati se vince quella selezione e perdono tutte le altre. Accanto la qualita':
``esatto`` (vincitore unico: il numero e' l'esito del mercato, esposizione esatta) o
``per_selezione`` (piu' vincitori, handicap, linee: il numero vale per la selezione,
esposizione = stima prudente, dichiarata).

Righe vere:
  * le ``marketDefinition`` dello stream REGISTRATE (``registrazioni_banco/``, cinque
    partite di calcio e il tennis) passate dalla cache VERA di betfairlightweight
    (``MarketBookCache`` -> ``MarketBook.market_definition``): DOUBLE_CHANCE (due
    vincitori, l'unico mercato a piu' vincitori registrato), TEAM_A_1 (handicap
    europeo, vincitore unico) e TUTTI i mercati a vincitore unico registrati;
  * gli ordini sono ``CurrentOrder`` VERI (``test_c2_aiuti.ordine_json`` -> libreria vera)
    passati dal ``LibroConto``;
  * asiatici, ``LINE`` e piazzati non sono nelle registrazioni: la definizione e' quella
    VERA registrata (stesse chiavi e tipi) con i soli campi del tipo cambiati
    (``bettingType``, ``marketType``, ``numberOfWinners``, ``runners`` con ``hc``, linee).
Gli oracoli (regolamento asiatico con push e quarti di linea, LINE con la linea come
prezzo e quota 2,0, doppia chance con due vincitori) sono scritti qui, indipendenti dal
codice: provano che l'esposizione dichiarata e' davvero un limite inferiore su OGNI esito.
ASCII-only.
"""
from __future__ import annotations

import copy
import functools
import gzip
import itertools
import json
import pathlib
import random
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pytest
from betfairlightweight.streaming.cache import MarketBookCache

from Betfair.nucleo.ordini import libro_conto as L
from Betfair.nucleo.ordini import pnl_mercato as P
from Betfair.nucleo.ordini.contratto import OrdineConto
from Betfair.nucleo.ordini.tests.test_c2_aiuti import dal_conto, ordine_json
from Betfair.nucleo.ordini.tests.test_c2_pnl_mercato import _ts_pnl_se_vince, oc

RADICE = pathlib.Path(__file__).resolve().parents[4]
REG = RADICE / "registrazioni_banco"
CALCIO = tuple(f"{e}/{e}" for e in ("35760084", "35768365", "35774000", "35777617", "35797769"))
TENNIS = ("tennis/20260707/35790089/35790089", "tennis/20260707/35794049/35794049",
          "tennis/20260707/35795993/35795993",
          "tennis/setbetting_20260707/35797566/35797566")


# ------------------------------------------------------------------ definizioni vere
@functools.lru_cache(maxsize=None)
def _definizioni(percorso: str) -> Tuple[Tuple[str, str], ...]:
    """(marketType, JSON del primo ``mc`` con la definizione) per ogni tipo di mercato
    della registrazione: il messaggio dello stream com'e' su disco."""
    f = REG / f"{percorso}.raw.jsonl.gz"
    assert f.exists(), f"registrazione mancante: {f}"
    visti: Dict[str, str] = {}
    with gzip.open(f, "rt", encoding="utf-8") as fh:
        for riga in fh:
            for mc in json.loads(riga).get("mc") or []:
                md = mc.get("marketDefinition")
                if md and md.get("marketType") and md["marketType"] not in visti:
                    visti[md["marketType"]] = json.dumps(mc)
    return tuple(sorted(visti.items()))


def _mc(percorso: str, tipo: str) -> Dict[str, Any]:
    for t, testo in _definizioni(percorso):
        if t == tipo:
            return json.loads(testo)
    raise AssertionError(f"{tipo} non registrato in {percorso}")


def _definizione(mc: Mapping[str, Any]) -> Any:
    """La ``MarketDefinition`` dalla cache VERA dello stream (come il ladder la vede)."""
    cache = MarketBookCache(str(mc["id"]), 1, False, False, False)
    cache.update_cache(dict(mc), 1, True)
    libro = cache.create_resource(1, snap=True)
    return libro.market_definition


def _variante(tipo_scommessa: str, tipo_mercato: str, vincitori: int,
              runner: Sequence[Tuple[int, Optional[float]]], **altro: Any) -> Dict[str, Any]:
    """Una definizione VERA registrata (MATCH_ODDS di 35760084) con i soli campi del tipo
    cambiati: per asiatici, LINE e piazzati, assenti dalle registrazioni."""
    mc = copy.deepcopy(_mc(CALCIO[0], "MATCH_ODDS"))
    md = mc["marketDefinition"]
    md.update({"bettingType": tipo_scommessa, "marketType": tipo_mercato,
               "numberOfWinners": vincitori, "numberOfActiveRunners": len(runner)})
    md["runners"] = [dict({"status": "ACTIVE", "sortPriority": i + 1, "id": sid},
                          **({"hc": hc} if hc is not None else {}))
                     for i, (sid, hc) in enumerate(runner)]
    md.update(altro)
    return mc


def _libro(mc: Mapping[str, Any], ordini: Sequence[Dict[str, Any]]) -> L.LibroConto:
    """Ordini VERI (``CurrentOrder``) nel libro, parametri del mercato dal book vero."""
    lib = L.LibroConto()
    for i, o in enumerate(ordini):
        lib.ricevi_live(dal_conto(o, ricevuto_ms=1000 + i))
    lib.imposta_mercato(str(mc["id"]), **P.parametri_dal_book(_definizione(mc)))
    return lib


def _ordini(lib: L.LibroConto, mid: str) -> List[OrdineConto]:
    return [o for o in lib.ordini(mid, "live") if o.abbinato > 0]


# ------------------------------------------------------------------ oracoli
def _brute_linea(ordini: Sequence[OrdineConto], linea: Tuple[int, float],
                 quota: Optional[float] = None) -> float:
    """Del test: vince la linea, perdono tutte le altre (forza bruta)."""
    v = 0.0
    for o in ordini:
        p = quota if quota is not None else float(o.prezzo_medio or 0.0)
        suo = o.selection_id == linea[0] and abs(o.handicap - linea[1]) < 1e-9
        if o.lato == "back":
            v += o.abbinato * (p - 1) if suo else -o.abbinato
        else:
            v += -o.abbinato * (p - 1) if suo else o.abbinato
    return v


def _esito_vincitori(ordini: Sequence[OrdineConto], vincitori: Sequence[int]) -> float:
    """P&L vero con un INSIEME di vincitori (mercati a piu' vincitori)."""
    v = 0.0
    for o in ordini:
        vince = o.selection_id in vincitori
        p = float(o.prezzo_medio or 0.0)
        if o.lato == "back":
            v += o.abbinato * (p - 1) if vince else -o.abbinato
        else:
            v += -o.abbinato * (p - 1) if vince else o.abbinato
    return v


def _esito_asiatico(ordini: Sequence[OrdineConto], diff_casa: int, casa: int) -> float:
    """Regolamento asiatico: risultato = differenza reti della squadra + handicap;
    > 0 vince, < 0 perde, = 0 rimborso (push); quarto di linea (x,25/x,75) = meta'
    della puntata su ciascuna delle due linee vicine (mezza vincita/perdita)."""
    v = 0.0
    for o in ordini:
        d = diff_casa if o.selection_id == casa else -diff_casa
        quarto = abs(((o.handicap * 4) % 2) - 1) < 1e-9
        linee = (o.handicap - 0.25, o.handicap + 0.25) if quarto else (o.handicap,)
        p = float(o.prezzo_medio or 0.0)
        for h in linee:
            s = o.abbinato / len(linee)
            r = d + h
            vince = s * (p - 1) if o.lato == "back" else -s * (p - 1)
            perde = -s if o.lato == "back" else s
            v += vince if r > 1e-9 else (perde if r < -1e-9 else 0.0)
    return v


def _esito_linea(ordini: Sequence[OrdineConto], valore: float) -> float:
    """Mercato LINE (documentazione Betfair, ``MarketBettingType.LINE``): quota 2,0, il
    prezzo e' la linea; BACK (vendi) vince se l'esito e' SOTTO la linea, LAY (compri)
    se SOPRA; uguale = rimborso."""
    v = 0.0
    for o in ordini:
        linea = float(o.prezzo_medio or 0.0)
        if abs(valore - linea) < 1e-9:
            continue
        vince = valore < linea if o.lato == "back" else valore > linea
        v += o.abbinato if vince else -o.abbinato
    return v


# ------------------------------------------------------------------ piu' vincitori
def test_doppia_chance_registrata_per_selezione_con_esposizione_prudente():
    mc = _mc(CALCIO[0], "DOUBLE_CHANCE")
    mid = str(mc["id"])
    a, b, c = (r["id"] for r in mc["marketDefinition"]["runners"])
    lib = _libro(mc, [ordine_json("1", "BACK", 10.0, 1.3, sel=a, market=mid),
                      ordine_json("2", "LAY", 5.0, 1.5, sel=b, market=mid),
                      ordine_json("3", "BACK", 4.0, 3.0, sel=c, market=mid,
                                  csr="mike", cor="mike-t1")])
    calc = lib.calcolo_posizione(mid, "live")
    ordini = _ordini(lib, mid)
    assert calc.qualita == P.QUALITA_PER_SELEZIONE and not calc.supportato
    assert "vincitori:2" in calc.motivi and "stima_prudente" in calc.motivi
    # la formula del ladder per ogni selezione: vince lei, perdono le altre
    abb = [(o.selection_id, o.lato, o.abbinato, o.prezzo_medio) for o in ordini]
    for k in (a, b, c):
        assert calc.posizione.se_vince[k] == round(_ts_pnl_se_vince(abb, k), 2)
    assert calc.posizione.se_vince == {a: 4.0, b: -16.5, c: 3.0}
    assert set(calc.posizione.se_vince_per_autore) == {"sito", "mike"}
    # NON e' un esito del mercato: con due vincitori nessun esito vale +3,0 su c
    esiti = {coppia: round(_esito_vincitori(ordini, coppia), 2)
             for coppia in itertools.combinations((a, b, c), 2)}
    assert all(v != calc.posizione.se_vince[c] for ch, v in esiti.items() if c in ch)
    # l'esposizione dichiarata e' un limite su OGNI esito vero (stima, non esatta)
    assert calc.esposizione_massima <= min(esiti.values()) + 1e-9
    assert not calc.esposizione_esatta
    assert P.calcolo_per_json(calc)["esposizione_tipo"] == "stima_prudente"


def test_piazzati_tre_vincitori_per_selezione():
    runner = [(101, None), (102, None), (103, None), (104, None), (105, None)]
    mc = _variante("ODDS", "PLACE", 3, runner)
    mid = str(mc["id"])
    lib = _libro(mc, [ordine_json("1", "BACK", 6.0, 2.4, sel=101, market=mid),
                      ordine_json("2", "LAY", 8.0, 1.8, sel=102, market=mid),
                      ordine_json("3", "BACK", 3.0, 4.2, sel=105, market=mid)])
    calc = lib.calcolo_posizione(mid, "live")
    ordini = _ordini(lib, mid)
    assert calc.qualita == P.QUALITA_PER_SELEZIONE and "vincitori:3" in calc.motivi
    assert set(calc.posizione.se_vince) == {101, 102, 103, 104, 105}
    for s in calc.posizione.se_vince:
        assert calc.posizione.se_vince[s] == round(_brute_linea(ordini, (s, 0.0)), 2)
        assert calc.se_vince_per_linea[(s, 0.0)] == calc.posizione.se_vince[s]
    esiti = [_esito_vincitori(ordini, tre) for tre in itertools.combinations(
        (101, 102, 103, 104, 105), 3)]
    assert calc.esposizione_massima <= min(esiti) + 1e-9


# ------------------------------------------------------------------ handicap europeo
def test_team_a_1_registrato_resta_esatto():
    mc = _mc(CALCIO[0], "TEAM_A_1")
    mid = str(mc["id"])
    a, b, c = (r["id"] for r in mc["marketDefinition"]["runners"])
    lib = _libro(mc, [ordine_json("1", "BACK", 10.0, 2.2, sel=a, market=mid),
                      ordine_json("2", "LAY", 4.0, 3.6, sel=c, market=mid)])
    calc = lib.calcolo_posizione(mid, "live")
    ordini = _ordini(lib, mid)
    assert calc.qualita == P.QUALITA_ESATTO and calc.esposizione_esatta
    esiti = [_esito_vincitori(ordini, (k,)) for k in (a, b, c)]
    assert calc.posizione.se_vince == {a: 16.0, b: -6.0, c: -20.4}
    assert calc.esposizione_massima == round(min([0.0] + esiti), 2) == -20.4   # stretta


# ------------------------------------------------------------------ asiatici
CASA, OSPITE = 47972, 47973


@pytest.mark.parametrize("vincitori", [0, 1])
def test_asiatico_doppia_linea_per_linea_e_limite_su_ogni_risultato(vincitori):
    """Piu' linee per squadra: il "se vince" per LINEA (selezione + handicap); nel
    contratto (chiave selection_id) nessuna somma di linee diverse: ``linee_multiple``.
    Basta il ``bettingType``: anche con ``numberOfWinners`` = 1 resta per_selezione."""
    linee = [(CASA, -0.5), (OSPITE, 0.5), (CASA, -0.25), (OSPITE, 0.25), (CASA, 0.0),
             (OSPITE, 0.0), (CASA, -1.0), (OSPITE, 1.0)]
    mc = _variante("ASIAN_HANDICAP_DOUBLE_LINE", "ASIAN_HANDICAP", vincitori, linee,
                   priceLadderDefinition={"type": "FINEST"})
    mid = str(mc["id"])
    lib = _libro(mc, [
        ordine_json("1", "BACK", 10.0, 1.92, sel=CASA, handicap=-0.5, market=mid),
        ordine_json("2", "LAY", 6.0, 2.08, sel=CASA, handicap=-0.25, market=mid),
        ordine_json("3", "BACK", 4.0, 2.3, sel=OSPITE, handicap=0.5, market=mid,
                    csr="mike", cor="mike-t1"),
        ordine_json("4", "LAY", 5.0, 1.75, sel=OSPITE, handicap=1.0, market=mid)])
    calc = lib.calcolo_posizione(mid, "live")
    ordini = _ordini(lib, mid)
    assert calc.qualita == P.QUALITA_PER_SELEZIONE and calc.a_linee
    assert {"tipo_non_supportato:ASIAN_HANDICAP_DOUBLE_LINE", "asiatico_push_non_modellato",
            "linee_multiple", "stima_prudente", "handicap"} <= set(calc.motivi)
    # ogni linea del book, con o senza ordini, e nessuna linea inventata
    assert set(calc.se_vince_per_linea) == set(linee)
    for ln in linee:
        assert calc.se_vince_per_linea[ln] == round(_brute_linea(ordini, ln), 2), ln
    assert calc.se_vince_per_linea[(CASA, -0.5)] == round(9.2 + 6.0 - 4.0 + 5.0, 2)
    # le due linee della stessa squadra NON si confondono
    assert calc.se_vince_per_linea[(CASA, -0.5)] != calc.se_vince_per_linea[(CASA, -0.25)]
    assert calc.posizione.se_vince == {}                   # due squadre, piu' linee ciascuna
    assert calc.se_vince_per_linea_per_autore["mike"][(OSPITE, 0.5)] == 5.2
    # l'esposizione dichiarata regge su OGNI risultato (push e mezze comprese)
    esiti = [_esito_asiatico(ordini, d, CASA) for d in range(-6, 7)]
    assert calc.esposizione_massima <= min(esiti) + 1e-9
    assert calc.esposizione_massima == round(-10.0 - 6.0 * 1.08 - 4.0 - 5.0 * 0.75, 2)


def test_asiatico_una_linea_per_squadra_entra_nel_contratto():
    mc = _variante("ASIAN_HANDICAP_DOUBLE_LINE", "ASIAN_HANDICAP", 0,
                   [(CASA, -0.75), (OSPITE, 0.75)])
    mid = str(mc["id"])
    lib = _libro(mc, [ordine_json("1", "BACK", 10.0, 2.0, sel=CASA, handicap=-0.75,
                                  market=mid)])
    calc = lib.calcolo_posizione(mid, "live")
    assert calc.posizione.se_vince == {CASA: 10.0, OSPITE: -10.0}
    assert "linee_multiple" not in calc.motivi
    esiti = [_esito_asiatico(_ordini(lib, mid), d, CASA) for d in range(-4, 5)]
    assert sorted(set(round(e, 2) for e in esiti)) == [-10.0, 5.0, 10.0]   # mezza vincita
    assert calc.esposizione_massima == -10.0


def test_runner_nudi_su_un_asiatico_non_inventano_la_linea_zero():
    """Con l'elenco dei runner come int (senza handicap) una selezione che ha gia' una
    linea dagli ordini NON riceve anche una linea 0,0 inventata."""
    ordini = [oc("1", CASA, "back", 10.0, 2.0, handicap=-0.5)]
    c = P.calcola("1.200", "live", ordini, runner=[CASA, OSPITE],
                  tipo_scommessa="ASIAN_HANDICAP_DOUBLE_LINE")
    assert set(c.se_vince_per_linea) == {(CASA, -0.5), (OSPITE, 0.0)}
    assert c.posizione.se_vince == {CASA: 10.0, OSPITE: -10.0}


# ------------------------------------------------------------------ LINE
def test_mercato_line_quota_due_e_stima_ordine_per_ordine():
    """LINE: il prezzo e' la LINEA, la quota 2,0 (come il blotter di flumine per il
    ladder LINE_RANGE). Una vendita a 2,5 e un acquisto a 3,5 perdono ENTRAMBI se il
    risultato e' 3: la stima linea per linea (-6,0) non e' un limite; quella ordine per
    ordine (-14,0) si'."""
    mc = _variante("LINE", "TEAM_TOTAL_GOALS", 1, [(9001, None)],
                   lineMinUnit=0.5, lineMaxUnit=10.5, lineInterval=1.0,
                   priceLadderDefinition={"type": "LINE_RANGE"})
    mid = str(mc["id"])
    lib = _libro(mc, [ordine_json("1", "BACK", 10.0, 2.5, sel=9001, market=mid),
                      ordine_json("2", "LAY", 4.0, 3.5, sel=9001, market=mid)])
    calc = lib.calcolo_posizione(mid, "live")
    ordini = _ordini(lib, mid)
    assert calc.qualita == P.QUALITA_PER_SELEZIONE
    assert {"tipo_non_supportato:LINE", "linea_a_quota_2", "stima_per_ordine"} <= set(calc.motivi)
    # quota 2,0, MAI la linea come quota (sarebbe 10*1,5 - 4*2,5 = 5,0)
    assert calc.posizione.se_vince == {9001: round(_brute_linea(ordini, (9001, 0.0), 2.0), 2)
                                       } == {9001: 6.0}
    esiti = [_esito_linea(ordini, x / 2) for x in range(0, 21)]
    assert min(esiti) == -14.0
    assert calc.esposizione_massima == -14.0 <= min(esiti)
    linea_per_linea = sum(min(0.0, e.se_vince, e.se_perde) for e in P.esposizioni_per_selezione(
        ordini, quota=2.0).values())
    assert linea_per_linea == -6.0 > min(esiti)            # il perche' della stima per ordine


# ------------------------------------------------------------------ vincitore unico: invariato
def _singoli() -> List[Tuple[str, str]]:
    out = []
    for p in CALCIO + TENNIS:
        for tipo, testo in _definizioni(p):
            md = json.loads(testo)["marketDefinition"]
            if md.get("bettingType") == "ODDS" and md.get("numberOfWinners") == 1:
                out.append((p, tipo))
    return out


def test_ci_sono_abbastanza_mercati_a_vincitore_unico_registrati():
    singoli = _singoli()
    assert len(singoli) >= 90 and {"MATCH_ODDS", "CORRECT_SCORE", "OVER_UNDER_25",
                                    "TEAM_A_1", "SET_BETTING"} <= {t for _p, t in singoli}


def test_vincitore_unico_registrato_identico_a_prima_e_al_ladder():
    """Su OGNI mercato a vincitore unico registrato: qualita' ``esatto``; il "se vince"
    identico alla formula del ladder (``pnlSeVince``); la posizione coi runner del book
    (coppie selezione/handicap) IDENTICA a quella coi runner come int (come il libro li
    teneva prima della decisione 5); esposizione esatta e stretta."""
    rnd = random.Random(10)
    n = 0
    for percorso, tipo in _singoli():
        md = _definizione(_mc(percorso, tipo))
        par = P.parametri_dal_book(md)
        sel = [s for s, _h in par["runner"]]
        ordini = [oc(str(i), rnd.choice(sel), rnd.choice(["back", "lay"]),
                     round(rnd.choice([0.5, 2.0, 3.37, 10.0]), 2),
                     rnd.choice([1.01, 1.5, 2.02, 3.35, 9.2, 1000.0]),
                     autore=rnd.choice(["desktop", "mike", "sito"]))
                  for i in range(rnd.randint(1, 9))]
        nuovo = P.calcola("1.200", "live", ordini, **par)
        vecchio = P.calcola("1.200", "live", ordini, runner=sel,
                            tipo_scommessa=par["tipo_scommessa"], vincitori=par["vincitori"],
                            tipo_mercato=par["tipo_mercato"])
        assert nuovo.qualita == P.QUALITA_ESATTO and nuovo.esposizione_esatta, tipo
        assert nuovo.posizione == vecchio.posizione and nuovo.motivi == vecchio.motivi
        abb = [(o.selection_id, o.lato, o.abbinato, o.prezzo_medio) for o in ordini]
        for s in sel:
            assert nuovo.posizione.se_vince[s] == round(_ts_pnl_se_vince(abb, s), 2)
            assert nuovo.se_vince_per_linea[(s, 0.0)] == nuovo.posizione.se_vince[s]
        esiti = [_esito_vincitori(ordini, (s,)) for s in sel]
        assert abs(nuovo.esposizione_massima - min([0.0] + esiti)) <= 0.0051
        n += 1
    assert n >= 90


# ------------------------------------------------------------------ book, JSON
def test_parametri_dal_book_vero():
    mc = _variante("ASIAN_HANDICAP_DOUBLE_LINE", "ASIAN_HANDICAP", 0,
                   [(CASA, -0.5), (OSPITE, 0.5), (CASA, None)])
    mc["marketDefinition"]["runners"][1]["status"] = "REMOVED"
    par = P.parametri_dal_book(_definizione(mc))
    assert par == {"runner": [(CASA, -0.5), (CASA, 0.0)],
                   "tipo_scommessa": "ASIAN_HANDICAP_DOUBLE_LINE", "vincitori": 0,
                   "tipo_mercato": "ASIAN_HANDICAP"}
    dc = P.parametri_dal_book(_definizione(_mc(CALCIO[1], "DOUBLE_CHANCE")))
    assert dc["vincitori"] == 2 and dc["tipo_scommessa"] == "ODDS"
    assert all(h == 0.0 and type(h) is float for _s, h in dc["runner"])


def test_libro_tiene_le_coppie_del_book():
    lib = L.LibroConto()
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 10.0, 2.0, sel=CASA, handicap=-0.5)))
    lib.imposta_mercato("1.200", runner=[(CASA, -0.5), (OSPITE, 0.5), (CASA, -0.25)],
                        tipo_scommessa="ASIAN_HANDICAP_DOUBLE_LINE")
    c = lib.calcolo_posizione("1.200", "live")
    assert set(c.se_vince_per_linea) == {(CASA, -0.5), (OSPITE, 0.5), (CASA, -0.25)}
    assert c.se_vince_per_linea[(CASA, -0.25)] == -10.0


def test_calcolo_per_json_dichiara_qualita_ed_esposizione():
    ordini = [oc("1", CASA, "back", 10.0, 2.0, handicap=-0.5),
              oc("2", CASA, "lay", 4.0, 2.5, handicap=-0.25, autore="mike")]
    per = P.calcola("1.200", "live", ordini, runner=[(CASA, -0.5), (CASA, -0.25)],
                    tipo_scommessa="ASIAN_HANDICAP_DOUBLE_LINE")
    d = json.loads(json.dumps(P.calcolo_per_json(per)))         # JSON puro, chiavi testo
    assert d["qualita"] == "per_selezione" and d["esposizione_tipo"] == "stima_prudente"
    assert d["se_vince_per_linea"] == [
        {"selection_id": CASA, "handicap": -0.5, "se_vince": 14.0},
        {"selection_id": CASA, "handicap": -0.25, "se_vince": -16.0}]
    assert d["se_vince_per_linea_per_autore"]["mike"][1]["se_vince"] == -6.0
    assert "linee_multiple" in d["motivi"] and d["se_vince"] == {}
    esatto = P.calcola("1.200", "live", [oc("1", CASA, "back", 10.0, 2.0)],
                       runner=[CASA, OSPITE], tipo_scommessa="ODDS", vincitori=1)
    e = P.calcolo_per_json(esatto)
    assert (e["qualita"], e["esposizione_tipo"], e["esposizione_massima"]) == (
        "esatto", "esatta", -10.0)
    ignoti = P.calcolo_per_json(P.calcola("1.200", "live", [oc("1", CASA, "back", 10.0, 2.0)],
                                          tipo_scommessa="ODDS", vincitori=1))
    assert ignoti["esposizione_tipo"] == "non_calcolabile"
    assert ignoti["esposizione_massima"] is None and ignoti["qualita"] == "esatto"


def test_handicap_dal_solo_book_non_e_esatto():
    """Gli ordini sono tutti sulla linea 0,0 ma il book ha anche linee con handicap:
    gli esiti NON sono uno per selezione, quindi niente esposizione "esatta"."""
    ordini = [oc("1", CASA, "back", 10.0, 2.0)]
    c = P.calcola("1.200", "live", ordini, tipo_scommessa="ODDS", vincitori=1,
                  runner=[(CASA, 0.0), (CASA, -1.0), (OSPITE, 0.0), (OSPITE, 1.0)])
    assert c.a_linee and "handicap" in c.motivi
    assert c.qualita == P.QUALITA_PER_SELEZIONE and not c.esposizione_esatta
    assert c.se_vince_per_linea == {(CASA, 0.0): 10.0, (CASA, -1.0): -10.0,
                                    (OSPITE, 0.0): -10.0, (OSPITE, 1.0): -10.0}


def test_per_selezione_senza_runner_lo_dice():
    """Senza l'elenco dei runner le linee senza ordini mancano: si dichiara."""
    ordini = [oc("1", CASA, "back", 10.0, 2.0)]
    senza = P.calcola("1.200", "live", ordini, tipo_scommessa="ODDS", vincitori=2)
    con = P.calcola("1.200", "live", ordini, tipo_scommessa="ODDS", vincitori=2,
                    runner=[CASA, OSPITE])
    assert "runner_ignoti" in senza.motivi and not senza.runner_noti
    assert senza.se_vince_per_linea == {(CASA, 0.0): 10.0}
    assert "runner_ignoti" not in con.motivi
    assert con.se_vince_per_linea == {(CASA, 0.0): 10.0, (OSPITE, 0.0): -10.0}
