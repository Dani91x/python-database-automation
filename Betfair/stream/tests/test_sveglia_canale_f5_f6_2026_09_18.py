"""F5/F6 - la sveglia del ciclo: Mike, Omega e il ponte dei 4 bot tennis.

Che cosa inchiodano questi test, uno per regola del modulo
``Betfair/stream/sveglia_canale.py``:

1. **Interruttore assente = niente.** ``time.sleep``/``stop.wait`` con lo stesso
   numero di oggi, nessun thread, nessuna porta aperta. Si CONTANO le chiamate.
2. **Il pavimento morde.** Una sveglia fa ripartire il giro, ma mai prima del
   minimo dall'inizio del giro precedente: e' la ragione per cui le letture al
   minuto non possono crescere.
3. **Un evento che non interessa non sveglia.**
4. **Un canale che solleva o che non c'e' non ferma il ciclo.**
5. **Il messaggio di sveglia non porta ordini**: si legge solo il motivo.

I finti parlano come il vero: i messaggi hanno la forma ESATTA che
``local_channel.publish`` mette sul filo (``{"t": topic, "d": riga}``) e la riga
ha le chiavi della riga di ``safe_strategy_scan`` (``event_id``, ``sport``,
``payload``, ``updated_at``).
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from Betfair.stream import sveglia_canale as SV

RADICE = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------- strumenti
class _Orologio:
    """Orologio finto: avanza solo quando glielo si dice o quando si 'dorme'."""

    def __init__(self, t0: float = 1000.0) -> None:
        self.t = float(t0)
        self.dormite: list[float] = []

    def ora(self) -> float:
        return self.t

    def dormi(self, quanto: float) -> None:
        self.dormite.append(float(quanto))
        self.t += float(quanto)


def _riga_scan(event_id: str = "36050104", sport: str = "calcio") -> dict:
    """La riga come esce davvero dal canale dello scanner (F1, §6)."""
    return {"event_id": event_id, "sport": sport,
            "payload": {"event_id": event_id, "odds": {"1": 2.1},
                        "odds_ts_ms": 1758200000000, "odds_pt_ms": 1758199999000,
                        "bet_delay": 12, "minute": 37},
            "updated_at": "2026-09-18T12:34:56.789+00:00"}


def _messaggio(topic: str, riga: dict) -> str:
    return json.dumps({"t": topic, "d": riga})


# ================================================================ modulo puro
def test_sveglia_canale_e_un_modulo_puro():
    """Invariante B1: importarlo NON deve tirare dentro flumine (sottoprocesso
    vero, non un mock di ``sys.modules``)."""
    codice = (
        "import sys\n"
        "import Betfair.stream.sveglia_canale as S\n"
        "S.Sveglia('x'); S.messaggio_di_sveglia({'motivo': 'comando'})\n"
        "vietati = [m for m in ('flumine', 'betfairlightweight', 'supabase', 'postgrest')\n"
        "           if any(k == m or k.startswith(m + '.') for k in sys.modules)]\n"
        "print('VIETATI=' + ','.join(vietati))\n"
    )
    res = subprocess.run([sys.executable, "-c", codice], cwd=str(RADICE),
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr[-2000:]
    assert "VIETATI=\n" in res.stdout or res.stdout.strip().endswith("VIETATI="), res.stdout


# ================================================================ interruttore
@pytest.mark.parametrize("valore", ["", "0", "no", "false", "  ", "SI ", "vero", "on"])
def test_senza_valore_scritto_linterruttore_e_spento(monkeypatch, valore):
    monkeypatch.setenv(SV.ENV_OMEGA_SVEGLIA, valore)
    assert SV.acceso(SV.ENV_OMEGA_SVEGLIA) is (valore.strip().lower() in SV.VALORI_ACCESI)


@pytest.mark.parametrize("valore", ["1", "true", "si", "yes", "TRUE", " Si "])
def test_con_il_valore_scritto_linterruttore_e_acceso(monkeypatch, valore):
    monkeypatch.setenv(SV.ENV_MIKE_SVEGLIA, valore)
    assert SV.acceso(SV.ENV_MIKE_SVEGLIA) is True


def test_interruttore_assente_e_spento(monkeypatch):
    monkeypatch.delenv(SV.ENV_TENNIS_SVEGLIA, raising=False)
    assert SV.acceso(SV.ENV_TENNIS_SVEGLIA) is False


# ===================================================================== Sveglia
def test_senza_sveglia_si_dorme_tutta_la_cadenza():
    # orologio VERO: e' la dormita di oggi, e si misura che duri davvero
    sv = SV.Sveglia("prova")
    inizio = time.monotonic()
    esito = sv.attendi(0.05, 0.01)
    assert esito == "cadenza"
    assert time.monotonic() - inizio >= 0.04
    assert sv.statistiche()["per_cadenza"] == 1


def test_la_sveglia_fa_ripartire_il_giro_subito_se_il_minimo_e_passato():
    sv = SV.Sveglia("prova")
    time.sleep(0.03)                      # il "giro precedente" e' durato 30 ms
    sv.alza("scan")
    inizio = time.monotonic()
    assert sv.attendi(5.0, 0.01) == "sveglia"
    assert time.monotonic() - inizio < 1.0
    assert sv.statistiche()["usate"] == 1


def test_la_sveglia_non_fa_mai_ripartire_prima_del_minimo():
    """Il PAVIMENTO: e' la garanzia che i giri al minuto non crescano."""
    orol = _Orologio()
    sv = SV.Sveglia("prova", ora=orol.ora, dormi=orol.dormi)
    sv.alza("scan")                        # sveglia immediata, 0 s dal giro prima
    esito = sv.attendi(60.0, 20.0)         # cadenza a vuoto 60 s, pavimento 20 s
    assert esito == "sveglia"
    assert orol.dormite == [20.0], orol.dormite
    assert sv.statistiche()["scartate_dal_minimo"] == 1
    # e il giro e' partito a 20 s, non a 60: e' il guadagno della fase
    assert orol.t == 1020.0


def test_il_pavimento_non_sfora_mai_la_cadenza_di_oggi():
    """Se il pavimento fosse piu' lungo della dormita, il giro non deve
    ritardare rispetto a oggi: al massimo arriva per cadenza."""
    orol = _Orologio()
    sv = SV.Sveglia("prova", ora=orol.ora, dormi=orol.dormi)
    sv.alza("scan")
    esito = sv.attendi(5.0, 20.0)
    assert esito == "cadenza"
    assert orol.t == 1005.0, "il giro e' partito piu' tardi di oggi"


def test_con_sveglie_continue_i_giri_al_minuto_restano_quelli_di_oggi():
    """Il conto che conta: sveglia a ogni istante, pavimento 20 s (la cadenza
    attiva di Omega) -> al massimo 3 giri al minuto, come oggi."""
    orol = _Orologio()
    sv = SV.Sveglia("omega", ora=orol.ora, dormi=orol.dormi)
    partenza = orol.t
    giri = 0
    # il tetto e' una rete: senza pavimento l'orologio finto non avanzerebbe e
    # il ciclo girerebbe per sempre. Con il tetto la falsificazione da' ROSSO,
    # non una prova che si pianta (difetto: un test che appende non dice nulla).
    while orol.t - partenza < 60.0 and giri <= 100:
        sv.alza("scan")                    # il canale non smette mai
        sv.attendi(60.0, 20.0)
        giri += 1
    assert giri <= 3, f"{giri} giri al minuto: piu' di oggi (20 s = 3/min)"


def test_la_sveglia_da_ui_porta_un_pavimento_piu_basso():
    orol = _Orologio()
    sv = SV.Sveglia("omega", ora=orol.ora, dormi=orol.dormi)
    sv.alza("approvazione", minimo_s=SV.MINIMO_UI_S)
    assert sv.attendi(60.0, 20.0) == "sveglia"
    assert orol.dormite == [1.0], "l'approvazione dell'utente ha aspettato il pavimento dello scan"


def test_fra_due_pavimenti_pendenti_vince_il_piu_basso():
    orol = _Orologio()
    sv = SV.Sveglia("omega", ora=orol.ora, dormi=orol.dormi)
    sv.alza("scan")
    sv.alza("comando", minimo_s=1.0)
    assert sv.attendi(60.0, 20.0) == "sveglia"
    assert orol.dormite == [1.0]


def test_il_pavimento_della_ui_non_resta_appiccicato_al_giro_dopo():
    orol = _Orologio()
    sv = SV.Sveglia("omega", ora=orol.ora, dormi=orol.dormi)
    sv.alza("comando", minimo_s=1.0)
    sv.attendi(60.0, 20.0)                 # consuma il pavimento basso
    orol.dormite.clear()
    sv.alza("scan")
    sv.attendi(60.0, 20.0)
    assert orol.dormite == [20.0], "il pavimento della UI e' rimasto al giro dopo"


def test_levento_di_stop_interrompe_la_dormita():
    sv = SV.Sveglia("tennis")
    stop = threading.Event()
    stop.set()
    assert sv.attendi(30.0, 1.0, interrompi=stop) == "interrotto"


def test_azzera_riporta_la_sveglia_a_processo_appena_avviato():
    sv = SV.Sveglia("prova")
    sv.alza("scan")
    sv.azzera()
    assert sv.statistiche()["sveglie"] == 0
    # e l'evento e' stato abbassato: la prossima attesa va a cadenza
    assert sv.attendi(0.02, 0.0) == "cadenza"


# ============================================== il messaggio di sveglia (F6)
@pytest.mark.parametrize("motivo", ["approvazione", "comando", "APPROVAZIONE", " Comando "])
def test_i_due_motivi_ammessi_svegliano(motivo):
    assert SV.messaggio_di_sveglia({"motivo": motivo}) == motivo.strip().lower()


@pytest.mark.parametrize("params", [
    None, {}, [], "approvazione", {"motivo": ""}, {"motivo": "place"},
    {"motivo": "greenup"}, {"motivo": None}, {"p": "approvazione"},
])
def test_qualunque_altra_cosa_non_sveglia_niente(params):
    assert SV.messaggio_di_sveglia(params) is None


def test_i_campi_dordine_nel_messaggio_sono_ignorati():
    """FALSIFICAZIONE del rischio: sul canale non passano soldi. Il messaggio
    puo' portare quello che vuole, di qui esce SOLO il motivo."""
    p = {"motivo": "approvazione", "market_id": "1.240", "selection_id": 47972,
         "side": "LAY", "price": 3.4, "size": 25.0, "trade_id": 299,
         "client_ref": "omega-t-299", "action": "place"}
    assert SV.messaggio_di_sveglia(p) == "approvazione"


def test_un_messaggio_che_non_e_una_sveglia_non_e_una_sveglia():
    assert SV.messaggio_di_sveglia({"action": "place", "price": 3.4}) is None


# ======================================================== AscoltoScan (filtro)
class _SvegliaFinta:
    def __init__(self) -> None:
        self.alzate: list[str] = []

    def alza(self, motivo: str = "scan", minimo_s=None) -> None:
        self.alzate.append(motivo)


def _ascolto(interessa, topic=(SV.TOPIC_SCAN_CALCIO,)):
    sv = _SvegliaFinta()
    return sv, SV.AscoltoScan(sv, interessa, topic=topic, porta=47999, nome="prova")


def test_un_evento_seguito_sveglia():
    sv, asc = _ascolto(lambda eid: eid == "36050104")
    assert asc.tratta(_messaggio(SV.TOPIC_SCAN_CALCIO, _riga_scan())) is True
    assert sv.alzate == ["scan"]
    assert asc.statistiche()["sveglie"] == 1


def test_un_evento_che_non_interessa_non_sveglia():
    sv, asc = _ascolto(lambda eid: False)
    assert asc.tratta(_messaggio(SV.TOPIC_SCAN_CALCIO, _riga_scan())) is False
    assert sv.alzate == []
    assert asc.statistiche()["scartati"] == 1


def test_il_topic_sbagliato_non_sveglia_e_non_si_conta_come_messaggio():
    """Calcio e tennis non si mischiano (invariante B12)."""
    sv, asc = _ascolto(lambda eid: True, topic=(SV.TOPIC_SCAN_CALCIO,))
    assert asc.tratta(_messaggio(SV.TOPIC_SCAN_TENNIS,
                                 _riga_scan("36099999", "tennis"))) is False
    assert sv.alzate == []
    assert asc.statistiche()["messaggi"] == 0


def test_la_sveglia_non_conserva_il_payload():
    """Del messaggio si legge SOLO ``event_id``: nessun prezzo entra qui."""
    visti: list[str] = []
    sv, asc = _ascolto(lambda eid: visti.append(eid) or True)
    asc.tratta(_messaggio(SV.TOPIC_SCAN_CALCIO, _riga_scan()))
    assert visti == ["36050104"]
    stato = json.dumps(asc.statistiche())
    for vietato in ("odds", "payload", "bet_delay", "2.1", "minute"):
        assert vietato not in stato, f"il payload e' finito nello stato: {vietato}"
    assert not hasattr(asc, "ultimo_payload")


def test_un_filtro_che_solleva_non_sveglia_e_non_ferma_niente():
    def esplode(eid):
        raise RuntimeError("filtro rotto")

    sv, asc = _ascolto(esplode)
    assert asc.tratta(_messaggio(SV.TOPIC_SCAN_CALCIO, _riga_scan())) is False
    assert sv.alzate == []
    assert asc.statistiche()["errori"] == 1


@pytest.mark.parametrize("grezzo", ["{non json", "", "[]", '{"t": "scan_calcio"}',
                                    '{"t": "scan_calcio", "d": null}',
                                    '{"t": "scan_calcio", "d": {"sport": "calcio"}}'])
def test_un_messaggio_storto_non_sveglia_e_non_solleva(grezzo):
    sv, asc = _ascolto(lambda eid: True)
    assert asc.tratta(grezzo) is False
    assert sv.alzate == []


def test_la_porta_chiusa_non_ferma_il_ciclo(monkeypatch, caplog):
    """Il client non riesce a collegarsi: nessuna eccezione esce, il ciclo di
    chi lo ha avviato non se ne accorge."""
    tentativi = {"n": 0}

    def _connetti_ko(url):
        tentativi["n"] += 1
        raise OSError("porta chiusa")

    sv = _SvegliaFinta()
    asc = SV.AscoltoScan(sv, lambda eid: True, porta=47999, nome="prova",
                         connetti=_connetti_ko)
    monkeypatch.setattr(SV, "_ATTESA_MIN_S", 0.01)
    assert asc.avvia() is True
    time.sleep(0.15)
    asc.ferma()
    time.sleep(0.05)
    assert tentativi["n"] >= 1
    assert asc.statistiche()["errori"] >= 1
    assert sv.alzate == []


def test_senza_websockets_non_parte_nessun_thread(monkeypatch):
    import builtins

    vero = builtins.__import__

    def _import(nome, *a, **k):
        if nome == "websockets":
            raise ImportError("no websockets")
        return vero(nome, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _import)
    sv = _SvegliaFinta()
    asc = SV.AscoltoScan(sv, lambda eid: True, porta=47999, nome="prova")
    assert asc.avvia() is False
    assert asc.attivo() is False
