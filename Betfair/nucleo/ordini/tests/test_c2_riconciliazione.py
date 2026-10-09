"""W1-C2 - riconciliatore IN OMBRA: scenari obbligatori e PARITA' con R1 e R2.

  * R1 = ``reconcile_worker._reconcile_orders`` VERO, sul client supabase VERO
    (MockTransport): gli upsert e gli update che R1 MANDA al DB e gli avvisi che
    alza sono confrontati con le divergenze dell'ombra, giro per giro;
  * R2 = ``motore_ordini.MotoreOrdini.riprendi_da_diario`` VERO su un ``Diario``
    VERO in una cartella temporanea: gli esiti ``ripresa`` che scrive sono
    confrontati con ``in_volo_dal_diario``;
  * scenari (scheda C par. 5 punto 4 + brief): esito ignoto, ordine esterno dal
    sito, sul conto non nello specchio, nello specchio non sul conto, riavvio con
    ordine in volo, parziale poi annullato, scaduto al fischio (LAPSE).
ASCII-only.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import pytest
from flumine import BaseStrategy
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.nucleo.ordini import attribuzione as A
from Betfair.nucleo.ordini import riconciliazione as R
from Betfair.nucleo.ordini.libro_conto import ordine_da_corrente
from Betfair.nucleo.ordini.tests.test_c2_aiuti import (AWAY, MKT, Registro,
                                                       client_supabase, correnti, ordine_json)


def riga_specchio(bet_id, *, matched=0.0, status="EXECUTABLE", source="runner", mode="live",
                  cor=None):
    """Una riga di ``betfair_live_orders`` (colonne della tabella; R1 legge
    ``bet_id,client_order_ref,size_matched,status,source`` con ``mode='live'``)."""
    return {"bet_id": bet_id, "client_order_ref": cor or f"awlq{bet_id}",
            "size_matched": matched, "status": status, "source": source, "mode": mode}


def _r1_giro(sb_reg: Registro, js: List[dict], specchio: List[dict], monkeypatch) -> Dict[str, Any]:
    """UN giro di R1 vero: cosa ha scritto e cosa ha avvisato."""
    from Betfair.stream import reconcile_worker as rw

    avvisi: List[str] = []
    monkeypatch.setattr(rw, "_alert", lambda livello, msg: avvisi.append(msg))
    prima = len(sb_reg.richieste)
    current = {str(c.bet_id): c for c in correnti(*js)}
    mirror = [{k: r[k] for k in ("bet_id", "client_order_ref", "size_matched", "status", "source")}
              for r in specchio if r["mode"] == "live"]
    esterni = rw._reconcile_orders(client_supabase(sb_reg), current, mirror)
    upsert, update = set(), set()
    for metodo, url, corpo in sb_reg.richieste[prima:]:
        if metodo == "POST":
            upsert.add(str(corpo["bet_id"] if isinstance(corpo, dict) else corpo[0]["bet_id"]))
        elif metodo == "PATCH":
            update.add(url.split("bet_id=eq.")[1].split("&")[0])
    miss = {m.split("bet ")[1].split(" ")[0] for m in avvisi if "ASSENTE" in m}
    return {"esterni": esterni, "upsert": upsert, "update": update, "miss": miss,
            "avvisi": avvisi}


@pytest.fixture
def r1_pulito(monkeypatch):
    from Betfair.stream import reconcile_worker as rw

    monkeypatch.setattr(rw, "_ALERTED_BETS", set())
    monkeypatch.setattr(rw, "_MISSING_SEEN", {})
    return rw


def _ombra(rec: R.RiconciliatoreOmbra, js, specchio, **kw) -> R.RefertoOmbra:
    conto = [ordine_da_corrente(c, ricevuto_ms=1) for c in correnti(*js)]
    return rec.giro(conto, specchio, **kw)


def _ids(ref: R.RefertoOmbra, *tipi: str) -> set:
    return {d.bet_id for d in ref.divergenze if d.tipo in tipi}


# ----------------------------------------------------------------------- PARITA' R1
def _scenari_r1() -> List[Tuple[str, List[dict], List[dict]]]:
    return [
        ("tutto allineato",
         [ordine_json("1", "BACK", 2.0, 2.0, csr="live")],
         [riga_specchio("1", matched=2.0, status="EXECUTION_COMPLETE")]),
        ("esterno dal sito",
         [ordine_json("2", "BACK", 2.0, 2.0)], []),
        ("sul conto non nello specchio: bot noto senza tabella e manuale",
         [ordine_json("3", "LAY", 1.0, 3.0, csr="scm34567890", cor="h-1"),
          ordine_json("4", "LAY", 1.0, 3.0, csr="live", cor="h-2")], []),
        ("bot REST con tabella: R1 salta",
         [ordine_json("5", "BACK", 2.0, 2.0, csr="mike", cor="mike-t5"),
          ordine_json("6", "BACK", 2.0, 2.0, csr="safe", cor="safe-t6")], []),
        ("parziale poi annullato",
         [ordine_json("7", "BACK", 1.5, 2.0, annullato=0.5, csr="live")],
         [riga_specchio("7", matched=1.5, status="EXECUTABLE")]),
        ("scaduto al fischio (LAPSE)",
         [ordine_json("8", "LAY", 0.0, 2.0, scaduto=2.0, csr="live")],
         [riga_specchio("8", matched=0.0, status="EXECUTABLE")]),
        ("numeri diversi e tolleranza",
         [ordine_json("9", "BACK", 3.0, 2.0, residuo=1.0, csr="live"),
          ordine_json("10", "BACK", 3.0, 2.0, residuo=1.0, csr="live")],
         [riga_specchio("9", matched=1.0), riga_specchio("10", matched=2.995)]),
        ("specchio senza conto (+ righe bot/account escluse, paper ignorato)",
         [],
         [riga_specchio("11"), riga_specchio("12", source="bot:scm1"),
          riga_specchio("13", source="account"), riga_specchio("14", mode="paper"),
          riga_specchio("15", status="EXECUTION_COMPLETE")]),
    ]


#: cosa R1 FA davvero in ogni scenario (upsert, update, avviso "assente" al 2o
#: giro): il confronto non passa a vuoto
ATTESI_R1 = {
    "tutto allineato": (set(), set(), set()),
    "esterno dal sito": ({"2"}, set(), set()),
    "sul conto non nello specchio: bot noto senza tabella e manuale": ({"3", "4"}, set(), set()),
    "bot REST con tabella: R1 salta": (set(), set(), set()),
    "parziale poi annullato": (set(), {"7"}, set()),
    "scaduto al fischio (LAPSE)": (set(), {"8"}, set()),
    "numeri diversi e tolleranza": (set(), {"9"}, set()),
    "specchio senza conto (+ righe bot/account escluse, paper ignorato)": (set(), set(), {"11"}),
}


@pytest.mark.parametrize("nome,js,specchio", _scenari_r1(), ids=[s[0] for s in _scenari_r1()])
def test_parita_con_r1_giro_per_giro(nome, js, specchio, r1_pulito, monkeypatch):
    reg = Registro()
    rec = R.RiconciliatoreOmbra(modo="live")
    for giro in (1, 2):
        vero = _r1_giro(reg, js, specchio, monkeypatch)
        up, upd, miss = ATTESI_R1[nome]
        assert (vero["upsert"], vero["update"]) == (up, upd)
        assert vero["miss"] == (miss if giro == 2 else set())
        ombra = _ombra(rec, js, specchio)
        assert vero["upsert"] == _ids(ombra, "esterno_dal_sito", "conto_senza_specchio"), giro
        assert vero["update"] == _ids(ombra, "numeri_diversi", "stato_diverso"), giro
        avvisi_ombra = {d.bet_id for d in ombra.per_tipo("specchio_senza_conto")
                        if d.gravita == "avviso"}
        assert vero["miss"] == avvisi_ombra, giro
        # gli "esterni" contati da R1 (source='account') = senza csr o col ref "live"
        attesi = {d.bet_id for d in ombra.divergenze
                  if d.tipo in ("esterno_dal_sito", "conto_senza_specchio")
                  and (d.dettagli.get("csr") or "") in ("", "live")}
        assert vero["esterni"] == len(attesi)


def test_r1_e_ombra_su_piu_giri_mancante_che_ricompare(r1_pulito, monkeypatch):
    reg = Registro()
    rec = R.RiconciliatoreOmbra(modo="live")
    spec = [riga_specchio("20")]
    g1 = _ombra(rec, [], spec)
    assert [d.gravita for d in g1.per_tipo("specchio_senza_conto")] == ["info"]
    g2 = _ombra(rec, [], spec)
    assert [d.gravita for d in g2.per_tipo("specchio_senza_conto")] == ["avviso"]
    g3 = _ombra(rec, [ordine_json("20", "BACK", 0.0, 2.0, residuo=2.0, csr="live")], spec)
    assert g3.per_tipo("specchio_senza_conto") == ()
    g4 = _ombra(rec, [], spec)                         # contatore azzerato, come R1
    assert [d.dettagli["giri"] for d in g4.per_tipo("specchio_senza_conto")] == [1]
    assert (g1.giro, g4.giro) == (1, 4)


# ----------------------------------------------------------------------- PARITA' R2
def _diario_vero(tmp_path, righe: List[dict]):
    from Betfair.stream.motore_ordini import Diario

    d = Diario(str(tmp_path), giorno=lambda: "2026-10-09")
    for r in righe:
        d.scrivi(r)
    return d


def _r2_vero(tmp_path, righe: List[dict], conto_json: List[dict]) -> Dict[str, str]:
    from Betfair.stream.motore_ordini import MotoreOrdini

    diario = _diario_vero(tmp_path, righe)
    finto_self = SimpleNamespace(diario=diario, _giorni_diario=lambda: ["2026-10-09"],
                                 _ora_ms=lambda: 1, scrittore=SimpleNamespace(accoda=lambda *a: None))

    def lista_ordini(cors):
        # la risposta di listCurrentOrders per customerOrderRef (JSON di Betfair)
        return {"currentOrders": [o for o in conto_json if o.get("customerOrderRef") in cors],
                "moreAvailable": False}

    assert MotoreOrdini.riprendi_da_diario(finto_self, lista_ordini) is True
    scritte = diario.leggi(["2026-10-09"])[len(righe):]      # solo le righe che R2 ha SCRITTO
    return {r["ref"]: r["esito"] for r in scritte if r.get("tipo") == "ripresa"}


def test_parita_con_r2_riavvio_con_ordini_in_volo(tmp_path):
    righe = [
        # ritrovato: inviato + ordine col customerOrderRef VERO, l'ordine e' sul conto
        {"tipo": "inviato", "ref": "omega-t1", "mode": "live"},
        {"tipo": "ordine", "ref": "omega-t1", "cor": "abcdef0123456-11"},
        # esito ignoto: inviato + ordine, sul conto non c'e'
        {"tipo": "inviato", "ref": "omega-t2", "mode": "live"},
        {"tipo": "ordine", "ref": "omega-t2", "cor": "abcdef0123456-12"},
        # cancel/replace senza riga 'ordine'
        {"tipo": "inviato", "ref": "omega-c9", "mode": "live"},
        # paper in volo
        {"tipo": "inviato", "ref": "safe-t3", "mode": "paper"},
        {"tipo": "ordine", "ref": "safe-t3", "cor": "abcdef0123456-13"},
        # chiuso: non e' in volo
        {"tipo": "inviato", "ref": "mike-t4", "mode": "live"},
        {"tipo": "esito", "ref": "mike-t4", "ok": True},
    ]
    conto = [ordine_json("901", "BACK", 1.0, 2.0, residuo=1.0, csr="omega",
                         cor="abcdef0123456-11")]
    vero = _r2_vero(tmp_path, righe, conto)
    cor = {o.customer_order_ref: o for o in
           (ordine_da_corrente(c, ricevuto_ms=1) for c in correnti(*conto))}
    ombra = {v.ref: v.esito for v in R.in_volo_dal_diario(righe, cor)}
    assert ombra == vero == {"omega-t1": "ritrovato", "omega-t2": "non_trovato",
                             "omega-c9": "mai_inviato_place", "safe-t3": "perso_paper"}
    # secondo riavvio: R2 ha scritto le righe 'ripresa', niente e' piu' in volo
    from Betfair.stream.motore_ordini import Diario

    tutte = Diario(str(tmp_path), giorno=lambda: "2026-10-09").leggi(["2026-10-09"])
    assert sum(1 for r in tutte if r.get("tipo") == "ripresa") == 4
    assert _r2_vero(tmp_path / "secondo", tutte, conto) == {}
    assert R.in_volo_dal_diario(tutte, cor) == ()


def test_scenario_riavvio_con_ordine_in_volo_e_esito_ignoto():
    rec = R.RiconciliatoreOmbra(modo="live")
    diario = [{"tipo": "inviato", "ref": "omega-t1", "mode": "live"},
              {"tipo": "ordine", "ref": "omega-t1", "cor": "abcdef0123456-11"},
              {"tipo": "inviato", "ref": "omega-t2", "mode": "live"},
              {"tipo": "ordine", "ref": "omega-t2", "cor": "abcdef0123456-12"}]
    js = [ordine_json("901", "BACK", 1.0, 2.0, residuo=1.0, csr="omega", cor="abcdef0123456-11")]
    ref = _ombra(rec, js, [riga_specchio("901", matched=1.0, source="omega")], diario=diario)
    trovato = ref.per_tipo("in_volo_ritrovato")[0]
    assert (trovato.bet_id, trovato.ref, trovato.gravita) == ("901", "omega-t1", "info")
    ignoto = ref.per_tipo("in_volo_non_trovato")[0]
    assert (ignoto.ref, ignoto.gravita, ignoto.bet_id) == ("omega-t2", "grave", None)
    st = ref.stati["901"]
    assert (st.fase, st.abbinato, st.residuo, st.ref) == ("parziale", 1.0, 1.0, "abcdef0123456-11")


# ----------------------------------------------------------------------- scenari
def test_scenario_esterno_dal_sito_con_autore():
    ref = _ombra(R.RiconciliatoreOmbra(modo="live"), [ordine_json("2", "BACK", 2.0, 3.0)], [])
    d = ref.per_tipo("esterno_dal_sito")[0]
    assert (d.bet_id, d.gravita, d.dettagli["autore"]) == ("2", "avviso", "sito")
    assert ref.posizioni[0].se_vince == 4.0 and ref.posizioni[0].se_perde == -2.0


def test_scenario_conto_senza_specchio_dice_chi():
    js = [ordine_json("3", "LAY", 1.0, 3.0, csr="TennisProStrate", cor="h-1"),
          ordine_json("4", "LAY", 1.0, 3.0, csr="live", cor="h-2"),
          ordine_json("5", "BACK", 2.0, 2.0, csr="mike", cor="mike-t5"),
          ordine_json("6", "LAY", 1.0, 3.0, csr="live", cor="h-3")]
    # 6: ref manuale CONFERMATO dalla riga di coda dell'app -> desktop
    ref = _ombra(R.RiconciliatoreOmbra(modo="live"), js, [],
                 indizi={"6": [A.Indizio("utente", "coda:local6")]})
    assert {d.bet_id: d.dettagli["autore"] for d in ref.per_tipo("conto_senza_specchio")} == {
        "3": "tennis_pro", "4": "sconosciuto", "6": "desktop"}  # 4: provvisorio (G1)
    assert ref.per_tipo("esterno_dal_sito") == ()     # il terminale dell'app non e' il sito
    assert {d.bet_id for d in ref.per_tipo("bot_con_tabella")} == {"5"}


def test_scenario_parziale_poi_annullato_e_lapse():
    js = [ordine_json("7", "BACK", 1.5, 2.0, annullato=0.5, csr="live"),
          ordine_json("8", "LAY", 0.0, 2.0, scaduto=2.0, csr="live")]
    spec = [riga_specchio("7", matched=1.5), riga_specchio("8")]
    ref = _ombra(R.RiconciliatoreOmbra(modo="live"), js, spec)
    assert _ids(ref, "stato_diverso") == {"7", "8"}
    assert (ref.stati["7"].fase, ref.stati["7"].abbinato) == ("annullato", 1.5)
    assert (ref.stati["8"].fase, ref.stati["8"].abbinato) == ("scaduto", 0.0)


def test_scenario_specchio_senza_bet_id_esito_ignoto():
    spec = [{"bet_id": None, "client_order_ref": "awlq7", "size_matched": 0.0, "status": "PENDING",
             "source": "runner", "mode": "live"}]
    ref = _ombra(R.RiconciliatoreOmbra(modo="live"), [], spec)
    d = ref.per_tipo("specchio_senza_bet_id")[0]
    assert (d.ref, d.gravita) == ("awlq7", "info")


def test_paper_separato_dal_live():
    spec = [riga_specchio("1", mode="live"), riga_specchio("2", mode="paper")]
    ref = _ombra(R.RiconciliatoreOmbra(modo="paper"), [], spec)
    assert _ids(ref, "specchio_senza_conto") == {"2"}
    assert ref.modo == "paper" and ref.conti["specchio"] == 1
    with pytest.raises(ValueError):
        R.RiconciliatoreOmbra(modo="tutti")  # type: ignore[arg-type]


def test_blotter_vero_contro_conto():
    s = BaseStrategy(market_filter={}, name="ombra_c2")
    blotter = []
    for co in correnti(ordine_json("31", "BACK", 1.0, 2.0, residuo=1.0),
                       ordine_json("32", "BACK", 0.0, 2.0, residuo=2.0)):
        t = Trade(market_id=MKT, selection_id=co.selection_id, handicap=0.0, strategy=s)
        o = t.create_order(side=co.side, order_type=LimitOrder(price=2.0, size=2.0))
        o.placing()
        o.executable()
        o.update_current_order(co)
        o.bet_id = co.bet_id
        blotter.append(o)
    # sul conto: 31 abbinato 2.0 (lo stream e' avanti), 32 assente
    js = [ordine_json("31", "BACK", 2.0, 2.0)]
    ref = _ombra(R.RiconciliatoreOmbra(modo="live"), js, [riga_specchio("31", matched=2.0,
                                                                         status="EXECUTION_COMPLETE")],
                 blotter=blotter)
    assert _ids(ref, "blotter_diverso") == {"31"}
    assert _ids(ref, "blotter_senza_conto") == {"32"}


def test_conflitto_di_attribuzione_e_una_divergenza():
    js = [ordine_json("41", "BACK", 1.0, 2.0, csr="mike", cor="safe-t3")]
    ref = _ombra(R.RiconciliatoreOmbra(modo="live"), js, [])
    assert _ids(ref, "attribuzione_in_conflitto") == {"41"}


def test_l_ombra_non_scrive_e_non_tocca_gli_ingressi():
    js = [ordine_json("7", "BACK", 1.5, 2.0, annullato=0.5, csr="live")]
    spec = [riga_specchio("7", matched=1.5), riga_specchio("99")]
    prima = copy.deepcopy(spec)
    conto = [ordine_da_corrente(c, ricevuto_ms=1) for c in correnti(*js)]
    conto_prima = list(conto)
    R.RiconciliatoreOmbra(modo="live").giro(conto, spec, diario=[])
    assert spec == prima and conto == conto_prima
    # nessuna chiamata di scrittura nel sorgente del modulo
    import inspect

    src = inspect.getsource(R)
    for vietato in (".table(", ".upsert(", ".insert(", "open(", ".scrivi(", "requests."):
        assert vietato not in src, vietato


def test_posizioni_a_linee_saltate_e_contate():
    js = [ordine_json("51", "BACK", 2.0, 1.9, handicap=-0.5),
          ordine_json("52", "BACK", 2.0, 1.9, sel=AWAY)]
    ref = _ombra(R.RiconciliatoreOmbra(modo="live"), js, [])
    assert ref.conti["posizioni_a_linee_saltate"] == 1
    assert [(p.selection_id, p.se_vince) for p in ref.posizioni] == [(AWAY, 1.8)]
