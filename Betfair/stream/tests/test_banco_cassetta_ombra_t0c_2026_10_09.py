# -*- coding: utf-8 -*-
"""T0C (09/10/2026) - CASSETTA, OMBRA e CONGELAMENTO del banco.

Che cosa si prova (H par. 4.3-4.4, 05 T0C, decisione dell'utente U-59):

  1. CASSETTA: forma canonica (chiavi ordinate, float esatti, mai indirizzi di
     memoria), i sei `kind` e nessun altro, agganci installati SOLO a cassetta
     accesa e tolti alla fine (innocuita' a livello di codice), le scritture del
     DB osservate anche nelle sottoclassi che non chiamano `super()`, i fill di
     flumine, le decisioni dal referto, il conto, il sigillo;
  2. OMBRA: identita' = 0 divergenze; la falsificazione di H par. 4.3 (soglia di
     un tick, importo 0,01, istante 1 ms, decisione tolta, `ok` invertito,
     colonna DB cambiata, controllo spento) e' ROSSA al livello atteso; un
     byte della cassetta cambiato rompe il sigillo; le TRE tolleranze (tempi,
     hash del codice, id d'orologio) coprono SOLO cio' che dichiarano;
  3. CONGELAMENTO: manifesto solo aggiunta (stessa voce con hash diverso
     rifiutata, voce ritoccata a mano = catena rotta), verifica rossa su un byte
     cambiato e su un file assente;
  4. CERTIFICA: i flag nuovi (`--cassetta`, `--ombra`, `--congela`,
     `--verifica-congelati`) col `main` VERO e il `_lavora` VERO (si cambia
     solo la funzione di replay della scheda, come negli altri test del banco):
     due giri identici = 0 divergenze; un giro con una colonna DB cambiata =
     exit code != 0; senza i flag nuovi nessuna cassetta e nessun aggancio.

Finti: `Referto`/`Violazione` VERI (`certificazione_tennis`), `DbMemoria` e
`MercatoFlumine` VERI del banco, `SimulatedOrder` VERO di flumine.
"""
from __future__ import annotations

import dataclasses
import json
import os
from types import SimpleNamespace

import pytest

from Betfair.safe_strategy.certificazione_tennis import Referto, Violazione
from Betfair.stream.backtest import banco_comune as BC
from Betfair.stream.backtest import cassetta as CAS
from Betfair.stream.backtest import certifica
from Betfair.stream.backtest import congela as CON
from Betfair.stream.backtest import ombra as OMB
from Betfair.stream.backtest import registro_bot as REG
from Betfair.stream.backtest import varianti_bot as VB


# ---------------------------------------------------------------------------
# 1. la cassetta
# ---------------------------------------------------------------------------
def test_canonica_chiavi_ordinate_float_esatti_solo_ascii():
    r = CAS.record("conto", 12, "x", {"b": 0.1 + 0.2, "a": "\u00e8", "c": [1, 2.5]})
    riga = CAS.canonica(r)
    assert riga.startswith('{"chiave":"x","dati":{"a":"\\u00e8","b":0.30000000000000004')
    assert riga.isascii()
    assert json.loads(riga)["dati"]["b"] == 0.1 + 0.2


def test_jsonabile_non_scrive_mai_un_indirizzo_di_memoria():
    class Oggetto:
        pass

    v = CAS.jsonabile({"o": Oggetto(), "s": {3, 1}, "t": (1, "a")})
    assert v == {"o": "<Oggetto>", "s": [1, 3], "t": [1, "a"]}
    assert "0x" not in json.dumps(v)


def test_solo_i_sei_kind():
    assert CAS.KINDS == ("decisione", "ordine", "fill", "conto", "riga_db", "referto")
    with pytest.raises(ValueError):
        CAS.record("settimo", 0, "x", {})


def _originali():
    from flumine.execution.transaction import Transaction
    from flumine.simulation.simulatedorder import SimulatedOrder

    return {
        "place": BC.MercatoFlumine.__dict__["place_order_live"],
        "cancel": BC.MercatoFlumine.__dict__["cancel_order_live"],
        "pnl": BC.MercatoFlumine.__dict__["pnl_betfair"],
        "tx": Transaction.__dict__["place_order"],
        "fill": SimulatedOrder.__dict__["_update_matched"],
        "specchio": VB.SpecchioOrdini.__dict__["_riga"],
        "db_init": BC.DbMemoria.__dict__["__init__"],
        "esegui": BC.MotoreReplay.__dict__["esegui"],
        "insert": BC.DbMemoria.__dict__["insert_trade"],
        "referto": Referto.__dict__["__init__"],
    }


def test_spenta_nessun_aggancio(monkeypatch):
    monkeypatch.delenv(CAS.ENV_DIR, raising=False)
    prima = _originali()
    assert not CAS.accesa()
    with CAS.compito(("safe_tennis", "1", "d", "base", 0, 0), SimpleNamespace(Referto=Referto)) as reg:
        assert reg is None
        assert _originali() == prima
    assert _originali() == prima


def test_accesa_installa_e_toglie_gli_agganci(tmp_path):
    prima = _originali()
    with CAS.compito(("safe_tennis", "1", "d", "base", 0, 0), SimpleNamespace(Referto=Referto),
                     cartella=str(tmp_path)) as reg:
        assert reg is not None
        dentro = _originali()
        for k in ("place", "cancel", "pnl", "tx", "fill", "specchio", "db_init", "esegui",
                  "referto"):
            assert dentro[k] is not prima[k], k
            assert getattr(dentro[k], "__wrapped__", None) is prima[k], k
    assert _originali() == prima
    assert CAS.ATTIVA is None


def _voci(cartella):
    out = []
    for nome in sorted(os.listdir(cartella)):
        with open(os.path.join(cartella, nome), encoding="ascii") as fh:
            out.extend(json.loads(r) for r in fh if r.strip())
    return out


def test_db_osservato_anche_nella_sottoclasse_senza_super(tmp_path):
    class DbFiglio(BC.DbMemoria):
        def insert_trade(self, trade):          # come DbMemoriaOmega: niente super()
            self._id += 10
            self.trades.append({**trade, "id": self._id})
            return self._id

    orig = DbFiglio.__dict__["insert_trade"]
    with CAS.compito(("safe_tennis", "1", "d", "base", 0, 0), None, cartella=str(tmp_path)):
        db = DbFiglio({"status": "running"})
        tid = db.insert_trade({"event_id": "1", "status": "open", "stake": 5.0})
        db.update_trade(tid, status="closed")
        db.log("decisione", {"motivo": "ok"}, "1")
        db.upsert_events([{"event_id": "1", "state": "ARMED"}])
    assert tid == 10
    assert DbFiglio.__dict__["insert_trade"] is orig
    righe = [v for v in _voci(tmp_path) if v["kind"] == "riga_db"]
    assert [v["chiave"].split("|", 1)[1] for v in righe] == [
        "insert_trade", "update_trade", "log", "upsert_event"]
    assert righe[0]["dati"]["args"] == [{"event_id": "1", "stake": 5.0, "status": "open"}]
    assert righe[0]["dati"]["esito"] == 10
    assert righe[1]["dati"]["kw"] == {"status": "closed"}
    # fuori dalla cassetta lo stesso DB non scrive niente da nessuna parte
    db2 = DbFiglio({})
    assert db2.insert_trade({"x": 1}) == 10


def _sim_order(prezzo=2.0, size=10.0):
    from flumine.order.ordertype import LimitOrder
    from flumine.simulation.simulatedorder import SimulatedOrder

    ordine = SimpleNamespace(id="139999999999999999", trade=SimpleNamespace(id="t-1"),
                             notes={"bot_ref": "ref1"}, market_id="1.1", selection_id=7,
                             handicap=0.0, side="BACK",
                             order_type=LimitOrder(price=prezzo, size=size), status=None,
                             bet_id="100000000001")
    return SimulatedOrder(ordine)


def test_fill_di_flumine_registrato_e_identico(tmp_path):
    fuori = _sim_order()
    fuori._update_matched([1700000000123, 2.0, 4.0])
    with CAS.compito(("safe_tennis", "1", "d", "base", 0, 0), None, cartella=str(tmp_path)):
        dentro = _sim_order()
        dentro._update_matched([1700000000123, 2.0, 4.0])
    assert (dentro.size_matched, dentro.average_price_matched) == \
        (fuori.size_matched, fuori.average_price_matched) == (4.0, 2.0)
    fill = [v for v in _voci(tmp_path) if v["kind"] == "fill"]
    assert len(fill) == 1 and fill[0]["ms"] == 1700000000123
    assert fill[0]["dati"]["matched"] == [1700000000123, 2.0, 4.0]
    assert fill[0]["dati"]["ordine_id"] == "139999999999999999"


def test_decisione_dalla_differenza_del_referto(tmp_path):
    with CAS.compito(("safe_tennis", "1", "d", "base", 0, 0), SimpleNamespace(Referto=Referto),
                     cartella=str(tmp_path)) as reg:
        r = Referto(event_id="1")
        reg.ora_ms = 1000
        reg.dopo_il_giro()                      # prima fotografia
        reg.ora_ms = 2000
        reg.dopo_il_giro()                      # niente di nuovo: nessun record
        r.decisioni += 1
        r.motivi["quota sotto soglia 1.86"] = 1
        r.sollecitati["B1"] = 1
        r.violazioni.append(Violazione("B2", "regola", "dettaglio"))
        reg.ora_ms = 3000
        reg.dopo_il_giro()
    dec = [v for v in _voci(tmp_path) if v["kind"] == "decisione"]
    assert [d["ms"] for d in dec] == [1000, 3000]
    assert dec[1]["dati"]["decisioni"] == 1
    assert dec[1]["dati"]["motivi"] == {"quota sotto soglia 1.86": 1}
    assert dec[1]["dati"]["sollecitati"] == {"B1": 1}
    assert dec[1]["dati"]["violazioni"] == [["B2", "dettaglio"]]


def test_conto_registrato_e_identico(tmp_path):
    m = BC.MercatoFlumine(SimpleNamespace(mercati={}))
    fuori = m.pnl_betfair(0.05)
    with CAS.compito(("safe_tennis", "1", "d", "base", 0, 0), None, cartella=str(tmp_path)):
        dentro = m.pnl_betfair(0.05)
    assert dentro == fuori
    conto = [v for v in _voci(tmp_path) if v["kind"] == "conto"]
    assert len(conto) == 1 and conto[0]["dati"]["esito"]["netto"] == 0


def test_sigillo_un_byte_cambiato_e_rosso(tmp_path):
    righe = CAS.assembla(str(tmp_path), {"bot": "x"}, "riga uno\nriga due\n")
    assert CAS.verifica_sigillo(righe) is None
    rotte = list(righe)
    rotte[1] = rotte[1].replace("uno", "unO")
    assert "sha256" in (CAS.verifica_sigillo(rotte) or "")
    assert CAS.verifica_sigillo(righe[:-1]) is not None          # sigillo tolto


# ---------------------------------------------------------------------------
# 2. l'ombra: una cassetta sintetica coi sei livelli
# ---------------------------------------------------------------------------
_OID_A, _OID_B = "139000000000000001", "139000000000000002"


def _base():
    """Le voci di una cassetta (prima del sigillo), modificabili dal test."""
    c = "35760084 [base]"
    return [
        CAS.record("referto", 0, "testata", {"bot": "mike", "commit": {"commit": "aaa"},
                                             "codice_bot": "abc123 (9 file)"}),
        CAS.record("referto", 0, c + "|compito", {"bot": "mike", "scenario": "base"}),
        CAS.record("decisione", 1000, c + "|referto0",
                   {"tick": 10, "decisioni": 1, "azioni": 0,
                    "motivi": {"quota 1.85 sotto soglia 1.86": 1},
                    "sollecitati": {"K1": 1, "B2": 1}}),
        CAS.record("decisione", 2000, c + "|referto0",
                   {"tick": 20, "decisioni": 1, "azioni": 1, "motivi": {"ingresso ok": 1},
                    "sollecitati": {"K1": 1}}),
        CAS.record("ordine", 2000, c + "|transazione.place_order|m1",
                   {"ordine_id": _OID_A, "trade_id": "uuid-a", "bot_ref": "m1",
                    "prezzo": 1.86, "size": 5.0, "side": "BACK", "bet_id": "100000000001",
                    "accettato": True}),
        CAS.record("ordine", 2100, c + "|transazione.place_order|m2",
                   {"ordine_id": _OID_B, "trade_id": "uuid-b", "bot_ref": "m2",
                    "prezzo": 1.9, "size": 2.5, "side": "LAY", "bet_id": "100000000002",
                    "accettato": True}),
        CAS.record("ordine", 2200, c + "|specchio|m1",
                   {"riga": {"client_order_ref": "m1", "_ordine": _OID_A,
                             "_trade_id": "uuid-a", "status": "EXECUTION_COMPLETE"}}),
        CAS.record("fill", 2150, c + "|fill|m1",
                   {"ordine_id": _OID_A, "matched": [2150, 1.86, 5.0], "bet_id": "100000000001"}),
        CAS.record("conto", 9000, c + "|pnl_betfair",
                   {"esito": {"lordo": 4.3, "commissione": 0.22, "netto": 4.08}}),
        CAS.record("riga_db", 2000, c + "|insert_trade",
                   {"args": [{"status": "open", "stake": 5.0}], "esito": 1}),
        CAS.record("referto", 9000, c + "|esito", {"tick": 20, "decisioni": 2,
                                                   "note": ["codice bot abc123 (9 file)"]}),
        CAS.record("referto", 0, "referto|testo", {"riga": "OK  35760084  tick=20"}),
        CAS.record("referto", 0, "referto|testo", {"riga": "     K1  x7067    regola K1"}),
        CAS.record("referto", 0, "referto|testo",
                   {"riga": "controlli attivi: 50 | codice bot abc123def456 (9 file)"}),
        CAS.record("referto", 0, "referto|testo", {"riga": "      tempo: x 1m03.1s | 900 tick/s"}),
        CAS.record("referto", 0, "referto|testo", {"riga": "MEMORIA: picco per worker 150 MB"}),
        CAS.record("referto", 0, "referto|testo", {"riga": "TEMPO TOTALE: 63.1 s"}),
    ]


def _sigilla(voci):
    righe = [CAS.canonica(v) for v in voci]
    righe.append(CAS.canonica(CAS.record("referto", 0, CAS.CHIAVE_SIGILLO,
                                         {"sha256": CAS.sigillo(righe), "voci": len(righe)})))
    return righe


def _ombra(mutazione=None):
    rif = _sigilla(_base())
    nuove = _base()
    if mutazione is not None:
        mutazione(nuove)
    return OMB.confronta_righe(rif, _sigilla(nuove))


def _livelli(es):
    return sorted({d.livello for d in es.divergenze})


def test_ombra_identita_zero_divergenze():
    es = _ombra()
    assert es.pulito and es.divergenze == []


def _soglia_di_un_tick(v):
    v[2]["dati"]["motivi"] = {"quota 1.85 sotto soglia 1.87": 1}
    v[4]["dati"]["prezzo"] = 1.87


def _importo_di_un_centesimo(v):
    v[4]["dati"]["size"] = 5.01


def _istante_di_un_ms(v):
    v[7]["ms"] = 2151


def _decisione_tolta(v):
    del v[3]


def _ok_invertito(v):
    v[3]["dati"]["motivi"] = {"ingresso no": 1}


def _colonna_db_cambiata(v):
    v[9]["dati"]["args"] = [{"stato": "open", "stake": 5.0}]


def _controllo_spento(v):
    v[2]["dati"]["sollecitati"] = {"B2": 1}
    v[3]["dati"].pop("sollecitati")
    v[12]["dati"]["riga"] = "  ?? K1  x0       regola K1"


def _conto_di_un_centesimo(v):
    v[8]["dati"]["esito"]["netto"] = 4.09


@pytest.mark.parametrize("mutazione,livelli", [
    (_soglia_di_un_tick, ["decisione", "ordine"]),
    (_importo_di_un_centesimo, ["ordine"]),
    (_istante_di_un_ms, ["fill"]),
    (_decisione_tolta, ["decisione"]),
    (_ok_invertito, ["decisione"]),
    (_colonna_db_cambiata, ["riga_db"]),
    (_controllo_spento, ["decisione", "referto"]),
    (_conto_di_un_centesimo, ["conto"]),
])
def test_ombra_falsificazione_rossa_al_livello_atteso(mutazione, livelli):
    es = _ombra(mutazione)
    assert not es.pulito
    assert _livelli(es) == livelli, OMB.descrivi(es)


def test_ombra_un_byte_della_cassetta_di_riferimento_rompe_il_sigillo():
    rif = _sigilla(_base())
    rif[4] = rif[4].replace('"size":5.0', '"size":5.1')
    es = OMB.confronta_righe(rif, _sigilla(_base()))
    assert es.sigillo_riferimento is not None and not es.pulito


def test_tolleranza_1_tempi_e_memoria():
    def tempi(v):
        v[14]["dati"]["riga"] = "      tempo: x 2m00.0s | 400 tick/s"
        v[15]["dati"]["riga"] = "MEMORIA: picco per worker 999 MB"
        v[16]["dati"]["riga"] = "TEMPO TOTALE: 120.0 s"
    assert _ombra(tempi).pulito
    # SOLO le righe che COMINCIANO coi prefissi: una nota che PARLA di tempo (il
    # tempo di mercato consumato dalle letture, che e' un numero del replay) e'
    # confrontata, e se cambia e' rossa
    rif = _base()
    rif[11]["dati"]["riga"] = "      nota: letture -> 223.4 s di tempo di mercato consumati"
    nuove = _base()
    nuove[11]["dati"]["riga"] = "      nota: letture -> 224.1 s di tempo di mercato consumati"
    es = OMB.confronta_righe(_sigilla(rif), _sigilla(nuove))
    assert _livelli(es) == ["referto"]


def test_tolleranza_2_hash_del_codice_escluso_e_stampato():
    def codice(v):
        v[0]["dati"]["commit"] = {"commit": "bbb"}
        v[0]["dati"]["codice_bot"] = "fff999 (10 file)"
        v[13]["dati"]["riga"] = "controlli attivi: 50 | codice bot 999999aaaaaa (10 file)"
        v[10]["dati"]["note"] = ["codice bot fff999 (10 file)"]
    es = _ombra(codice)
    assert es.pulito, OMB.descrivi(es)
    testo = "\n".join(OMB.descrivi(es))
    assert "bbb" in testo and "aaa" in testo and "fff999 (10 file)" in testo
    # il NUMERO dei controlli sulla stessa riga resta confrontato
    def controlli(v):
        v[13]["dati"]["riga"] = "controlli attivi: 49 | codice bot abc123def456 (9 file)"
    assert _livelli(_ombra(controlli)) == ["referto"]


def test_tolleranza_3_id_d_orologio_coerenti_si_ma_scambiati_no():
    def altri_id(v):
        for i in (4, 6, 7):
            s = json.dumps(v[i]["dati"]).replace(_OID_A, "141111111111111111")
            v[i]["dati"] = json.loads(s)
        s = json.dumps(v[5]["dati"]).replace(_OID_B, "142222222222222222")
        v[5]["dati"] = json.loads(s)
        for i in (4, 6):
            s = json.dumps(v[i]["dati"]).replace("uuid-a", "uuid-z")
            v[i]["dati"] = json.loads(s)
    assert _ombra(altri_id).pulito

    def scambiati(v):
        # il fill finisce sull'ALTRO ordine: stessa forma, identita' diversa
        v[7]["dati"]["ordine_id"] = _OID_B
    es = _ombra(scambiati)
    assert _livelli(es) == ["fill"]

    def bet_id(v):
        v[4]["dati"]["bet_id"] = "100000000009"
    assert _livelli(_ombra(bet_id)) == ["ordine"]          # bet_id NON si normalizza


def test_tolleranza_3_timbri_della_macchina_dichiarati_si_pid_no():
    """I campi trovati dalla prova di determinismo (TOLLERANZE.md, tabella 3)
    scritti con l'orologio della macchina; il ``pid`` (REPERTO T0C-R2) no."""
    def con_timbri(ora, pid, ts):
        def m(v):
            v[9]["dati"]["kw"] = {"settled_at": ora, "heartbeat_at": ora}
            v[3]["dati"]["ctx"] = {"last_loss_exit_deciso_ts": ts}
            v[10]["dati"]["pid"] = pid
        return m
    rif = _base()
    con_timbri("2026-10-09T14:24:56.180429+00:00", 11790, 1791555870.1192932)(rif)
    nuove = _base()
    con_timbri("2026-10-09T14:26:03.275621+00:00", 11790, 1791555936.8476624)(nuove)
    es = OMB.confronta_righe(_sigilla(rif), _sigilla(nuove))
    assert es.pulito, OMB.descrivi(es)
    nuove = _base()
    con_timbri("2026-10-09T14:26:03.275621+00:00", 12214, 1791555936.8476624)(nuove)
    es = OMB.confronta_righe(_sigilla(rif), _sigilla(nuove))
    assert _livelli(es) == ["referto"] and "pid" in es.divergenze[0].regola
    # e un timbro che NON e' nell'elenco resta confrontato
    nuove = _base()
    con_timbri("2026-10-09T14:24:56.180429+00:00", 11790, 1791555870.1192932)(nuove)
    nuove[9]["dati"]["kw"]["updated_at"] = "2026-10-09T14:26:03+00:00"
    assert _livelli(OMB.confronta_righe(_sigilla(rif), _sigilla(nuove))) == ["riga_db"]


def test_cassetta_compressa_deterministica(tmp_path):
    righe = _sigilla(_base())
    a = CAS.scrivi(str(tmp_path / "a.jsonl.gz"), righe)
    b = CAS.scrivi(str(tmp_path / "b.jsonl.gz"), righe)
    assert a == b
    assert CAS.leggi(str(tmp_path / "a.jsonl.gz")) == righe
    assert OMB.confronta_file(str(tmp_path / "a.jsonl.gz"), str(tmp_path / "b.jsonl.gz")).pulito
    # un byte cambiato DENTRO il gzip: niente eccezione, sigillo rosso
    p = tmp_path / "a.jsonl.gz"
    grezzo = bytearray(p.read_bytes())
    grezzo[len(grezzo) // 2] ^= 1
    p.write_bytes(bytes(grezzo))
    es = OMB.confronta_file(str(p), str(tmp_path / "b.jsonl.gz"))
    assert not es.pulito and es.sigillo_riferimento is not None


# ---------------------------------------------------------------------------
# 3. il congelamento
# ---------------------------------------------------------------------------
def test_argomenti_del_comando_senza_i_flag_della_cassetta():
    argv = ["mike", "35760084", "--scenari", "base", "--cassetta", "a.jsonl", "--ombra=b",
            "--congela", "--congelati", "d", "--worker", "1"]
    assert CON.argomenti_del_comando(argv) == ["mike", "35760084", "--scenari", "base",
                                               "--worker", "1"]


def test_manifesto_solo_aggiunta_e_verifica(tmp_path):
    f = tmp_path / "rif.txt"
    f.write_bytes(b"riferimento\n")
    cartella = str(tmp_path / "congelati")
    v = CON.voce_file(str(f), tipo="altro", comando="cmd")
    assert len(CON.aggiungi_voci(cartella, [v])) == 1
    assert CON.aggiungi_voci(cartella, [v]) == []                 # identica: non si ripete
    assert all(ok for _p, ok, _m in CON.verifica(cartella))
    assert CON.verifica_e_stampa(cartella) == 0
    # stesso percorso, contenuto diverso: RIFIUTATO
    f.write_bytes(b"riferimento cambiato\n")
    with pytest.raises(CON.CongelamentoRifiutato):
        CON.aggiungi_voci(cartella, [CON.voce_file(str(f), tipo="altro", comando="cmd")])
    # e la verifica lo vede
    esiti = CON.verifica(cartella)
    assert not esiti[0][1] and "cambiato" in esiti[0][2]
    assert CON.verifica_e_stampa(cartella) == 1
    # file assente
    os.remove(str(f))
    assert "assente" in CON.verifica(cartella)[0][2]


def test_manifesto_ritoccato_a_mano_catena_rotta(tmp_path):
    f = tmp_path / "rif.txt"
    f.write_bytes(b"x\n")
    g = tmp_path / "rif2.txt"
    g.write_bytes(b"y\n")
    cartella = str(tmp_path / "congelati")
    CON.aggiungi_voci(cartella, [CON.voce_file(str(f), tipo="altro", comando="cmd")])
    p = os.path.join(cartella, CON.MANIFESTO)
    man = json.load(open(p, encoding="ascii"))
    man["voci"][0]["comando"] = "cmd ritoccato"
    with open(p, "w", encoding="ascii") as fh:
        json.dump(man, fh)
    assert "catena rotta" in CON.verifica(cartella)[0][2]
    with pytest.raises(CON.CongelamentoRifiutato):
        CON.aggiungi_voci(cartella, [CON.voce_file(str(g), tipo="altro", comando="cmd")])


def test_congela_giro_mai_sopra_un_file_esistente(tmp_path):
    cas = tmp_path / "giro.jsonl"
    cas.write_text("{}\n")
    cartella = str(tmp_path / "congelati")
    kw = dict(cartella=cartella, bot="mike", argv=["mike", "1", "--scenari", "base"],
              cassetta=str(cas), testo_referto="referto\n", riferimento_determinismo=str(cas))
    voci = CON.congela_giro(**kw)
    assert [v["tipo"] for v in voci] == ["cassetta", "referto"]
    assert voci[0]["comando"] == "python -m Betfair.stream.backtest.certifica mike 1 --scenari base"
    assert voci[0]["determinismo"]["divergenze"] == 0
    with pytest.raises(CON.CongelamentoRifiutato):
        CON.congela_giro(**kw)


# ---------------------------------------------------------------------------
# 4. certifica coi flag nuovi (main VERO, _lavora VERO)
# ---------------------------------------------------------------------------
EVENTO = "999999"
_MUT = {"colonna": "status"}


def _replay_con_agganci(event_id, *, data_dir, scenario="base", ogni_ms=0, campioni_diff=0):
    """Un replay minimo che passa dagli oggetti VERI del banco."""
    r = Referto(event_id=str(event_id))
    db = BC.DbMemoria({"status": "running", "mode": "paper"})
    tid = db.insert_trade({"event_id": str(event_id), _MUT["colonna"]: "open", "stake": 5.0})
    db.update_trade(tid, status="closed")
    db.log("decisione", {"motivo": "ingresso"}, str(event_id))
    BC.MercatoFlumine(SimpleNamespace(mercati={})).pnl_betfair(0.05)
    r.tick = 1200
    r.decisioni = 7
    r.sollecitati["B1"] = 7
    r.note.append("nota fissa dello scenario %s" % scenario)
    return r


@pytest.fixture
def banco(monkeypatch):
    vera = REG.bot("safe_tennis")
    finta = dataclasses.replace(vera, replay="%s:_replay_con_agganci" % __name__)

    def _bot(nome):
        return finta if str(nome) == "safe_tennis" else vera

    monkeypatch.setattr(certifica.REG, "bot", _bot)
    monkeypatch.delenv(CAS.ENV_DIR, raising=False)
    _MUT["colonna"] = "status"
    return monkeypatch


def _main(tmp_path, *extra):
    return certifica.main(["safe_tennis", EVENTO, "--data-dir", str(tmp_path), "--worker", "1",
                           "--scenari", "base,paper", *extra])


def test_certifica_due_giri_identici_zero_divergenze_e_colonna_cambiata_rossa(
        banco, capsys, tmp_path):
    c1 = str(tmp_path / "giro1.jsonl")
    c2 = str(tmp_path / "giro2.jsonl")
    assert _main(tmp_path, "--cassetta", c1) == 0
    out = capsys.readouterr().out
    assert "CASSETTA: %s" % c1 in out
    voci = [json.loads(r) for r in CAS.leggi(c1)]
    kinds = {v["kind"] for v in voci}
    assert {"decisione", "conto", "riga_db", "referto"} <= kinds
    assert CAS.verifica_sigillo(CAS.leggi(c1)) is None
    assert os.environ.get(CAS.ENV_DIR) is None                   # rimessa a posto
    # due compiti, ognuno col suo segmento, in ordine canonico
    compiti = [v["chiave"] for v in voci if v["chiave"].endswith("|compito")]
    assert compiti == ["999999 [base]|compito", "999999 [paper]|compito"]
    # stesso comando: 0 divergenze, exit 0
    assert _main(tmp_path, "--cassetta", c2, "--ombra", c1) == 0
    out = capsys.readouterr().out
    assert "OMBRA: 0 divergenze, sigilli integri" in out
    # una COLONNA DB cambiata: exit != 0 e il livello riga_db
    _MUT["colonna"] = "stato"
    assert _main(tmp_path, "--ombra", c1) == OMB.EXIT_OMBRA
    out = capsys.readouterr().out
    assert "DIVERGENTE" in out and "riga_db 2" in out


def test_certifica_congela_vuole_il_determinismo_e_poi_congela(banco, capsys, tmp_path):
    cartella = str(tmp_path / "congelati")
    assert _main(tmp_path, "--congela", "--congelati", cartella) == 2
    assert "DETERMINISMO" in capsys.readouterr().out
    c1 = str(tmp_path / "giro1.jsonl")
    assert _main(tmp_path, "--cassetta", c1) == 0
    assert _main(tmp_path, "--ombra", c1, "--congela", "--congelati", cartella) == 0
    out = capsys.readouterr().out
    assert out.count("CONGELATO:") == 2
    assert certifica.main(["--verifica-congelati", "--congelati", cartella]) == 0
    # un byte cambiato nella cassetta congelata: verifica rossa
    man = CON.leggi_manifesto(cartella)
    p = CON._assoluto(man["voci"][0]["percorso"])
    with open(p, "r+b") as fh:
        fh.seek(5)
        b = fh.read(1)
        fh.seek(5)
        fh.write(bytes([b[0] ^ 1]))
    assert certifica.main(["--verifica-congelati", "--congelati", cartella]) == 1
    # e un congelamento divergente e' rifiutato
    _MUT["colonna"] = "stato"
    assert _main(tmp_path, "--ombra", c1, "--congela", "--congelati", cartella) != 0
    assert "CONGELAMENTO RIFIUTATO" in capsys.readouterr().out


def test_certifica_senza_flag_nuovi_nessuna_cassetta(banco, capsys, tmp_path, monkeypatch):
    chiamate = []
    monkeypatch.setattr(OMB, "certifica_con_cassetta",
                        lambda *a, **k: chiamate.append(a) or 99)
    prima = _originali()
    assert _main(tmp_path) == 0
    assert chiamate == []
    assert _originali() == prima
    assert "CASSETTA" not in capsys.readouterr().out
