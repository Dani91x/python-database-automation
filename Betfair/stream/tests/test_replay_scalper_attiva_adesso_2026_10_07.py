"""Banco dello scalper - ATTIVA ADESSO e CONTRATTO COMUNE (07/10/2026).

* contratto comune del banco (Applica bot): ``certifica_scenario(...,
  parametri=None, dal_ms=None)`` e ``parametri_modificabili(scenario)``; con i
  due a None la riga della UI (e quindi il referto) e' IDENTICA a prima;
* controlli M12-M18 della sessione <<a clic>> (registro separato) e le
  esenzioni di M7/M9 SOLO per i cicli avviati col pulsante, su righe con le
  chiavi e i valori VERI di ``certificazione.riga_ordine`` (stati di flumine);
* la connessione finta del guasto `prezzi-fermi` letta dalla funzione VERA
  ``stream_muto.stato_stream``.

Nessuna registrazione serve: i replay veri li lancia il coordinatore.
ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest
from flumine.order.order import OrderStatus

from Betfair.stream import stream_muto as SM
from Betfair.stream.scalper import certificazione as CERT
from Betfair.stream.scalper import media_under_bot as MU
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.scalper.tools import replay_registrazioni as R
from Betfair.stream.tests.banco_media_under import params_di_serie

VECCHI = [s for s in R.SCENARI_DESCRITTI if s not in R.SCENARI_MEDIA_CLIC]


# ===========================================================================
# 1. il contratto comune: nulla cambia senza parametri e senza dal_ms
# ===========================================================================
@pytest.mark.parametrize("scenario", VECCHI)
def test_riga_della_ui_identica_senza_parametri(scenario):
    assert R.control_della_ui("1", scenario) == R._control_della_ui("1", scenario)
    params = R.control_della_ui("1", scenario)["params"]
    # le chiavi del pulsante non entrano nella riga di sempre
    for k in (MU.CHIAVE_A_CLIC, MU.CHIAVE_COMANDO, MU.CHIAVE_RIENTRO_FILTRI):
        assert k not in params, (scenario, k)


def test_scenari_del_pulsante_armati_dal_pulsante():
    for s in R.SCENARI_MEDIA_CLIC:
        p = R.control_della_ui("1", s)["params"]
        assert p[MU.CHIAVE_A_CLIC] is True and p["media_mode"] is True
        assert MU.CHIAVE_COMANDO not in p          # il clic lo manda il banco, all'istante
        assert R.control_della_ui("1", s)["dry_run"] is s.endswith("-paper")
        assert s in R.SCENARI_DESCRITTI
    assert R.control_della_ui("1", "media-clic-lontano-filtri")["params"][
        MU.CHIAVE_RIENTRO_FILTRI] is True
    assert R.mercato_media("media-clic-gioco-35") == "OVER_UNDER_35"


def test_parametri_modificabili_media_dalla_stessa_fonte_del_servizio():
    voci = R.parametri_modificabili("media-under-paper")
    chiavi = [v["chiave"] for v in voci]
    for v in voci:
        # 07/10 (integrazione con Applica bot): le chiavi del contratto COMUNE del
        # catalogo (fonte unica `backtest/varianti_bot.CHIAVI_VOCE`, con `scelte`)
        from Betfair.stream.backtest import varianti_bot as VB
        assert tuple(v) == VB.CHIAVI_VOCE
        assert v["gruppo"] in VB.GRUPPI
        assert v["tipo"] in ("int", "float", "bool", "scelta")
        assert v["chiave"] in MU.CHIAVI_UI
        assert v["default"] == MU.VALORI_DI_SERIE[v["chiave"]], v["chiave"]
    assert "media_rientro_auto_filtri" in chiavi and "media_stake" in chiavi
    # la variante dichiarata ha il SUO default (la riga dello scenario)
    liq = {v["chiave"]: v["default"] for v in R.parametri_modificabili("media-under-liquidita-100")}
    assert liq["media_min_size"] == 100.0


def test_parametri_modificabili_maker_e_sniper():
    maker = {v["chiave"]: v for v in R.parametri_modificabili("paper")}
    riga = R.control_della_ui("1", "paper")["params"]
    for k, v in maker.items():
        attesa = riga.get(k, SS.VALIDATED_PARAMS.get(k))
        assert v["default"] == attesa, k
        assert k in SS.UI_PARAM_WHITELIST, k
    assert "sniper_stake" not in maker
    sn = {v["chiave"] for v in R.parametri_modificabili("sniper-paper")}
    assert "sniper_stake" in sn


@pytest.mark.parametrize("scenario,parametri,parola", [
    ("media-under", {"boh": 1}, "non modificabile"),
    ("media-under", {"media_stake": "10"}, "atteso un numero"),
    ("media-under", {"media_stake": 3.3}, "non piazzabile"),
    ("media-under", {"media_tick_rientro": 1.5}, "intero"),
    ("media-under", {"media_tick_rientro": 0}, "fuori dominio"),
    ("media-under", {"media_rientro_auto_filtri": 1}, "vero/falso"),
    ("media-under", {"media_quota_min": 4.5}, "non validi"),
    ("paper", {"media_stake": 10.0}, "non modificabile"),
    ("paper", {"scalp_ticks": 0}, "fuori dominio"),
])
def test_parametri_sbagliati_value_error_chiaro(scenario, parametri, parola, tmp_path):
    with pytest.raises(ValueError, match=parola):
        R.certifica_scenario("1", data_dir=str(tmp_path), scenario=scenario,
                             parametri=parametri)


def test_parametri_giusti_entrano_nella_riga_come_dalla_scheda():
    ok = R.valida_parametri("media-under", {"media_min_size": 100, "media_rientro_auto_filtri": True})
    assert ok == {"media_min_size": 100.0, "media_rientro_auto_filtri": True}
    p = R.control_della_ui("1", "media-under", ok, a_clic=True)["params"]
    assert p["media_min_size"] == 100.0 and p[MU.CHIAVE_A_CLIC] is True
    assert p[MU.CHIAVE_RIENTRO_FILTRI] is True
    par, mot = MU.leggi_parametri(p)
    assert mot is None and par.min_size == 100.0 and par.rientro_auto_filtri is True
    with pytest.raises(ValueError, match="clic_ms"):
        R.certifica_scenario("1", data_dir="/nessuna", scenario="paper", clic_ms=[1])


def test_clic_della_regola_dai_fatti_del_raw():
    f = {"primo": 1_000_000, "ko": 4_000_000, "in_gioco": 4_030_000,
         "sospensioni": [[4_100_000, 4_103_000], [4_500_000, 4_513_000]]}
    assert R.clic_della_regola("lontano", f) == [1_600_000]
    assert R.clic_della_regola("finestra", f) == [3_800_000]
    assert R.clic_della_regola("doppio", f) == [3_100_000, 3_100_400]
    assert R.clic_della_regola("in-posizione", f) == [3_100_000, 3_190_000]
    assert R.clic_della_regola("prezzi-fermi", f) == [3_120_000]
    # primo tratto in gioco di almeno 300 s senza sospensioni: dopo la prima
    assert R.clic_della_regola("gioco", f) == [4_163_000]
    assert R.clic_della_regola("due-clic", f) == [4_163_000, 5_363_000]
    assert R.clic_della_regola("prima-gol", f) == [4_075_000]
    assert R.clic_della_regola("dopo-gol", f) == [4_106_000]
    assert R.clic_della_regola("sospeso", f) == [4_500_300]
    assert R.clic_della_regola("gioco", dict(f, in_gioco=None)) == []


def test_la_sessione_vera_arma_dal_pulsante_e_paper_uguale_live():
    """La sessione VERA (``run_session`` fino all'armamento) con la riga del
    pulsante: modalita' in ATTESA DEL CLIC, stessi parametri in prova e in soldi
    veri (S6: lo stato del pulsante non e' un parametro)."""
    from Betfair.stream.backtest.certifica import _freni_da_banco
    from Betfair.stream.tests.test_scalper_media_under_2026_10_05 import EVENTO, _catalogo

    cat, follow = _catalogo()
    with _freni_da_banco():
        for sc in R.SCENARI_MEDIA_CLIC:
            par, cli = R.arma_e_cattura(EVENTO, R.control_della_ui(EVENTO, sc), follow, cat)
            assert par["stato"] == MU.ATTESA_CLIC, sc
            assert par["parametri"]["mercato"] == R.mercato_media(sc), sc
            assert cli["paper_trade"] is (sc in R.SCENARI_MEDIA_PROVA), sc
        p = R.parita_paper_live(EVENTO, R.control_della_ui(EVENTO, "media-clic-lontano"),
                                follow, cat)
        assert not p.get("errore"), p
        assert p["parametri_diversi"] == [] and p["client_diversi"] == []
        # lo stato del pulsante NON gonfia il conto dei parametri confrontati
        q = R.parita_paper_live(EVENTO, R.control_della_ui(EVENTO, R.SCENARIO_MEDIA),
                                follow, cat)
        assert q["n_parametri"] == p["n_parametri"]


# ===========================================================================
# 2. i controlli M12-M18 e le esenzioni di M7/M9 (righe con le chiavi vere)
# ===========================================================================
ESEG = OrderStatus.EXECUTABLE.value
COMPL = OrderStatus.EXECUTION_COMPLETE.value


def _riga(oid: str, lato: str, prezzo: float, size: float, abb: float, ms: int,
          stato: str = COMPL) -> Dict[str, Any]:
    return {"order_id": oid, "bet_id": "b" + oid, "status": stato, "side": lato,
            "selection_id": 47972, "market_id": "1.25", "price": prezzo, "size": size,
            "persistence": "PERSIST" if lato == "LAY" else "LAPSE", "size_matched": abb,
            "size_remaining": 0.0 if stato == COMPL else size - abb,
            "average_price_matched": prezzo if abb > 0 else 0.0, "in_blotter": True,
            "creato_ms": ms, "sostituto": False}


def _oss(righe: List[Dict[str, Any]], ms: int, **kw: Any) -> CERT.OsservazioneMedia:
    par, _m = MU.leggi_parametri(params_di_serie(**kw.pop("params", {})))
    base = dict(quando="t", ms=ms, params=par, mercato_scelto="1.25",
                tipo_mercato={"1.25": "OVER_UNDER_25"}, under=47972, ordini=righe,
                nuovi={r["order_id"] for r in righe}, ko_ms=10_000_000,
                in_gioco_ms=10_030_000, reazione_ms=15_000)
    base.update(kw)
    return CERT.OsservazioneMedia(**base)


def _ciclo_chiuso(prefisso: str, t: int) -> List[Dict[str, Any]]:
    return [_riga(prefisso + "p", "BACK", 1.50, 10.0, 10.0, t),
            _riga(prefisso + "b", "LAY", 1.48, 10.14, 10.14, t + 2000)]


def _codici(oss: CERT.OsservazioneMedia) -> List[str]:
    return [v.codice for v in CERT.verifica_clic(oss)]


def test_m12_ogni_prima_punta_ha_il_suo_clic_o_e_un_rientro_automatico_pre_match():
    cons = [{"id": "c1", "clic_ms": 1_000_000, "ms": 1_004_000, "eseguibile": True, "motivo": None}]
    righe = _ciclo_chiuso("a", 1_005_000) + _ciclo_chiuso("b", 1_020_000)
    oss = _oss(righe, 1_100_000, a_clic_dal_ms=0, consegne=cons)
    origini = [x["origine"] for x in CERT.origini_dei_clic(oss)]
    assert origini == [CERT.ORIGINE_CLIC, CERT.ORIGINE_AUTO]
    assert "M12" not in _codici(oss)
    # lo stesso secondo ciclo IN GIOCO senza clic: rosso (<<in gioco rientra da solo>>)
    righe2 = _ciclo_chiuso("a", 10_040_000) + _ciclo_chiuso("b", 10_060_000)
    cons2 = [dict(cons[0], ms=10_039_000)]
    assert "M12" in _codici(_oss(righe2, 10_100_000, a_clic_dal_ms=0, consegne=cons2))
    # un clic = UNA prima punta: la seconda nella reazione dello stesso clic e' rossa
    righe3 = [_riga("x", "BACK", 1.50, 10.0, 0.0, 1_005_000),
              _riga("y", "BACK", 1.50, 10.0, 0.0, 1_006_000)]
    oss3 = _oss(righe3, 1_100_000, a_clic_dal_ms=0, consegne=cons)
    assert "M12" in _codici(oss3)
    # nessun clic eseguibile: la prima punta della sessione armata dal pulsante e' rossa
    assert "M12" in _codici(_oss(_ciclo_chiuso("a", 1_005_000), 1_100_000, a_clic_dal_ms=0,
                                 consegne=[dict(cons[0], eseguibile=False)]))


def test_m13_m14_nascite_sul_book():
    cons = [{"id": "c1", "clic_ms": 1_000_000, "ms": 1_004_000, "eseguibile": True, "motivo": None}]
    r = [_riga("a", "BACK", 1.50, 10.0, 10.0, 1_005_000)]
    buono = {"a": {"status": "OPEN", "attivo": True, "bb": 1.50, "bl": 1.51, "sb": 500, "sl": 500}}
    assert _codici(_oss(r, 1_010_000, a_clic_dal_ms=0, consegne=cons, nascite=buono)) == []
    sospeso = {"a": dict(buono["a"], status="SUSPENDED")}
    assert "M13" in _codici(_oss(r, 1_010_000, a_clic_dal_ms=0, consegne=cons, nascite=sospeso))
    altro = {"a": dict(buono["a"], bb=1.52)}
    assert "M14" in _codici(_oss(r, 1_010_000, a_clic_dal_ms=0, consegne=cons, nascite=altro))


def test_m15_clic_eseguibile_senza_prima_punta():
    cons = [{"id": "c1", "clic_ms": 1_000_000, "ms": 1_004_000, "eseguibile": True, "motivo": None}]
    assert "M15" not in _codici(_oss([], 1_010_000, a_clic_dal_ms=0, consegne=cons))
    assert "M15" in _codici(_oss([], 1_030_000, a_clic_dal_ms=0, consegne=cons))
    non = [dict(cons[0], eseguibile=False, motivo="mercato SUSPENDED alla consegna")]
    assert "M15" not in _codici(_oss([], 1_030_000, a_clic_dal_ms=0, consegne=non))


def test_m16_m17_rientro_automatico():
    oss = _oss(_ciclo_chiuso("a", 1_005_000), 1_040_000, a_clic_dal_ms=0,
               chiuso_pre_match_dal_ms=1_020_000)
    assert "M16" in _codici(oss)
    oss = _oss(_ciclo_chiuso("a", 1_005_000), 1_030_000, a_clic_dal_ms=0,
               chiuso_pre_match_dal_ms=1_020_000)
    assert "M16" not in _codici(oss)
    # coi filtri accesi il rientro automatico deve passare i filtri (qui liquidita' 100)
    cons = [{"id": "c1", "clic_ms": 1_000_000, "ms": 1_004_000, "eseguibile": True, "motivo": None}]
    righe = _ciclo_chiuso("a", 1_005_000) + _ciclo_chiuso("b", 1_020_000)
    nascite = {"bp": {"status": "OPEN", "attivo": True, "bb": 1.50, "bl": 1.51, "sb": 100.0,
                      "sl": 100.0}}
    oss = _oss(righe, 1_100_000, a_clic_dal_ms=0, consegne=cons, nascite=nascite,
               params={"media_rientro_auto_filtri": True})
    assert "M17" in _codici(oss)
    nascite["bp"].update(sb=500.0, sl=500.0)
    assert "M17" not in _codici(oss)


def test_m18_rientro_dovuto_e_rientro_dovuto_dal_banco():
    righe = [_riga("a", "BACK", 1.50, 10.0, 10.0, 1_005_000),
             _riga("b", "LAY", 1.48, 10.14, 0.0, 1_006_000, stato=ESEG)]
    oss = _oss(righe, 10_100_000, a_clic_dal_ms=0, bb_ora=1.52, aperto_ora=True)
    assert CERT.rientro_dovuto(oss) is True
    assert CERT.rientro_dovuto(_oss(righe, 10_100_000, a_clic_dal_ms=0, bb_ora=1.51,
                                    aperto_ora=True)) is False
    assert CERT.rientro_dovuto(_oss(righe, 10_100_000, a_clic_dal_ms=0, bb_ora=1.52,
                                    aperto_ora=False)) is False
    assert CERT.rientro_dovuto(_oss(righe, 10_100_000, a_clic_dal_ms=None, bb_ora=1.52,
                                    aperto_ora=True)) is False
    oss.rientro_dovuto_dal_ms = 10_080_000
    assert "M18" in _codici(oss)
    oss.rientro_dovuto_dal_ms = 10_090_000
    assert "M18" not in _codici(oss)


def test_m7_m9_esenti_solo_per_i_cicli_del_pulsante():
    righe = [_riga("a", "BACK", 1.50, 10.0, 10.0, 10_040_000),
             _riga("b", "LAY", 1.48, 10.14, 0.0, 10_041_000, stato=ESEG)]

    def codici_m(oss):
        return [v.codice for v in CERT.verifica_media(oss)]
    # modalita' di sempre: un ordine nato in gioco e' rosso (M7) e la punta nella
    # finestra pure (M9)
    assert "M7" in codici_m(_oss(righe, 10_050_000))
    assert "M9" in codici_m(_oss(righe, 10_050_000))
    # avviata col pulsante: niente M7/M9 (i controlli del pulsante sono M12-M18)
    cons = [{"id": "c1", "clic_ms": 10_038_000, "ms": 10_039_000, "eseguibile": True,
             "motivo": None}]
    oss = _oss(righe, 10_050_000, a_clic_dal_ms=0, consegne=cons)
    assert "M7" not in codici_m(oss) and "M9" not in codici_m(oss)
    # il force-flat vale per tutti
    oss = _oss(righe, 10_050_000, a_clic_dal_ms=0, consegne=cons, force_flat_ms=10_000_000)
    assert "M9" in codici_m(oss)
    # sessione mai <<a clic>>: il registro del pulsante tace
    assert CERT.verifica_clic(_oss(righe, 10_050_000)) == []


# ===========================================================================
# 3. la connessione finta del guasto `prezzi-fermi` (funzione vera stream_muto)
# ===========================================================================
def test_flusso_finto_letto_da_stato_stream():
    class _O:
        def __init__(self):
            self.ms = 1_000_000

        def ora_ms(self):
            return self.ms

    banco = R._Banco.__new__(R._Banco)
    banco.orologio = _O()
    banco.buio = (1_000_000, 1_060_000)
    banco.ultimo_consegnato_ms = 999_000
    banco.mercati_catalogo = ["1.25"]
    fw = type("F", (), {})()
    fw.streams = [banco.flusso_finto()]
    banco.orologio.ms = 1_020_000
    st = SM.stato_stream(fw)
    assert st["vivo"] is False and st["motivo"] == SM.MOTIVO_INTERROTTO
    banco.orologio.ms = 1_070_000
    assert SM.stato_stream(fw)["vivo"] is True
    assert time.time() > 0
    # dentro il replay flumine sostituisce `datetime.datetime` con l'orologio di
    # mercato (``SimulatedDateTime``): la connessione finta deve restare viva fuori
    # dal buio anche li' (difetto visto sulla 35797769: sempre <<ferma>>)
    import datetime as _dt
    from flumine.simulation.utils import SimulatedDateTime

    sim = SimulatedDateTime()
    with sim:
        sim(_dt.datetime(2026, 7, 10, 16, 0, tzinfo=_dt.timezone.utc))
        assert SM.stato_stream(fw)["vivo"] is True
        banco.orologio.ms = 1_020_000
        assert SM.stato_stream(fw)["vivo"] is False
