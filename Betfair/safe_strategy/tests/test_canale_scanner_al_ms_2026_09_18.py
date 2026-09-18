"""F0 (misura) e F1 (canale dello scanner, muto) del PIANO_CANALE_LOCALE_AL_MS.

F0 mette nel payload di scan i due numeri senza cui nessuna fase successiva e'
misurabile, calcio E tennis:
  * ``odds_pt_ms``  quando BETFAIR ha pubblicato il book che ha portato il cambio
                    di quota (``publishTime``) - NON il nostro orologio;
  * ``bet_delay``   il ritardo che l'exchange impone a QUESTO mercato, dal
                    ``marketDefinition``. Prima lo leggeva solo il ramo dei
                    mercati a gol del calcio: MATCH_ODDS e tutto il tennis
                    passavano senza, e la certificazione doveva ASSUMERE 3 s.

F1 accende il canale locale 47336 dentro il processo dello scanner, in SOLA
PUBBLICAZIONE, senza consumatori e con l'interruttore SPENTO di default.

IL PUNTO PIU' DELICATO (conflitto C2 del piano): ``odds_pt_ms`` sta SOTTO la
guardia ``scanner.has_any_price`` e ``bet_delay`` SOPRA. Sopra la guardia,
``odds_pt_ms`` farebbe avanzare l'istante di un prezzo che non esiste su un book
di sola ``marketDefinition``: sarebbe l'incidente del 17/09 con un campo in piu'.

I FINTI DI QUESTO FILE SONO VERI: ``MarketBook`` di betfairlightweight, con il
ladder nelle DUE forme in cui gira davvero - oggetti con ``.price/.size`` (il
processo dello scanner, che flumine non lo importa) e dizionari (la forma che
flumine impone quando entra in un processo). E' la lezione del 17/09: un finto
scritto in una forma sola certifica il difetto.

Ogni test di questo file e' stato FALSIFICATO con una mutazione sul codice VERO:
l'elenco, con gli md5 del file prima e dopo, sta in
``Betfair/safe_strategy/CHECKPOINT_AL_MS_F0_F1_2026-09-18.md``.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from betfairlightweight.resources.bettingresources import MarketBook

from Betfair.safe_strategy import scanner
from Betfair.safe_strategy import service
from Betfair.stream import local_channel
from Betfair.stream import orologio

RADICE = Path(__file__).resolve().parents[3]


# ===========================================================================
# I FINTI: le classi VERE, nelle DUE forme del ladder
# ===========================================================================
def runner_dict(sid: int, back=None, lay=None, status: str = "ACTIVE") -> dict:
    """Il runner come lo serializza ``RunnerBookCache``.

    ``back``/``lay`` = (prezzo, size) oppure None. None su entrambi = il runner
    nato dalla sola DEFINIZIONE: id e stato ci sono, la scaletta e' VUOTA. E'
    esattamente cio' che arriva su un messaggio di sola ``marketDefinition``.
    """
    return {
        "selectionId": int(sid),
        "status": status,
        "handicap": 0.0,
        "lastPriceTraded": None,
        "totalMatched": 0.0,
        "ex": {
            "availableToBack": ([{"price": back[0], "size": back[1]}] if back else []),
            "availableToLay": ([{"price": lay[0], "size": lay[1]}] if lay else []),
            "tradedVolume": [],
        },
    }


class _Livello:
    """Un livello del ladder come lo vede la PRODUZIONE: ``.price`` e ``.size``."""

    __slots__ = ("price", "size")

    def __init__(self, price, size):
        self.price, self.size = price, size


class _Ex:
    """``runner.ex`` nella forma di PRODUZIONE (oggetti)."""

    __slots__ = ("available_to_back", "available_to_lay", "traded_volume")

    def __init__(self, atb, atl):
        self.available_to_back = [_Livello(l["price"], l["size"]) for l in atb]
        self.available_to_lay = [_Livello(l["price"], l["size"]) for l in atl]
        self.traded_volume = []


class _ExDict:
    """``runner.ex`` nella forma che flumine impone: livelli come DIZIONARI.

    Lo scanner deve leggerla identica (difesa in profondita' del 17/09): se un
    domani qualcosa riportasse flumine nel processo del feed, questi test
    devono misurare la stessa cosa e non un silenzio.
    """

    __slots__ = ("available_to_back", "available_to_lay", "traded_volume")

    def __init__(self, atb, atl):
        self.available_to_back = [dict(l) for l in atb]
        self.available_to_lay = [dict(l) for l in atl]
        self.traded_volume = []


def book(market_id: str, runners: list, *, status: str = "OPEN", inplay: bool = True,
         total_matched: float = 0.0, bet_delay: Optional[int] = 0,
         publish_time_ms: Optional[int] = None, forma: str = "oggetti") -> MarketBook:
    """Un MarketBook vero, nella forma in cui lo stream lo consegna.

    ``bet_delay=None`` = il campo NON c'e' (book REST di certe risposte): deve
    restare assente, mai zero. ``publish_time_ms=None`` = book senza
    ``publishTime``, cioe' il poll REST.
    """
    kw: Dict[str, Any] = {"marketId": market_id, "status": status, "inplay": inplay,
                          "totalMatched": total_matched, "runners": runners}
    if bet_delay is not None:
        kw["betDelay"] = bet_delay
    if publish_time_ms is not None:
        kw["publishTime"] = int(publish_time_ms)
    mb = MarketBook(**kw)
    classe = _Ex if forma == "oggetti" else _ExDict
    for rb, grezzo in zip(mb.runners, runners):
        rb.ex = classe(grezzo["ex"]["availableToBack"], grezzo["ex"]["availableToLay"])
    return mb


CON_PREZZI = [runner_dict(11, back=(1.30, 500.0), lay=(1.32, 400.0)),
              runner_dict(22, back=(4.00, 120.0), lay=(4.40, 90.0))]
ALTRI_PREZZI = [runner_dict(11, back=(1.25, 500.0), lay=(1.27, 400.0)),
                runner_dict(22, back=(4.50, 120.0), lay=(5.00, 90.0))]
SOLO_DEFINIZIONE = [runner_dict(11), runner_dict(22)]

PT1 = 1789000000123      # publishTime di Betfair, ms interi
PT2 = 1789000002456


def test_i_finti_sono_la_forma_vera_dello_stream():
    """Cintura: se betfairlightweight cambiasse forma, questi test mentirebbero."""
    b = book("1.100", CON_PREZZI, bet_delay=3, publish_time_ms=PT1)
    assert b.market_id == "1.100" and b.status == "OPEN" and b.inplay is True
    assert b.bet_delay == 3
    assert b.publish_time_epoch == PT1
    assert isinstance(b.publish_time, datetime)
    assert scanner.price_pair(b.runners[0].ex)["back"] == 1.30
    # e la forma a DIZIONARI si legge identica
    d = book("1.100", CON_PREZZI, forma="dizionari")
    assert scanner.price_pair(d.runners[0].ex) == scanner.price_pair(b.runners[0].ex)
    # un book REST: niente publishTime
    r = book("1.100", CON_PREZZI, publish_time_ms=None)
    assert r.publish_time_epoch is None and r.publish_time is None
    # e un book senza betDelay dichiarato: il campo e' assente, non zero
    assert book("1.100", CON_PREZZI, bet_delay=None).bet_delay is None


# ===========================================================================
# Lo scanner di prova (tennis e calcio: pari cura)
# ===========================================================================
#: l'orologio FERMO dei confronti a due giri: senza, ``odds_ts_ms`` e
#: ``updated_at`` cambierebbero fra un giro e l'altro e il confronto misurerebbe
#: il tempo che passa invece del codice. E' lo stesso orologio iniettabile che
#: usa il banco di replay (li' e' il ``publish_time`` del tick).
OROLOGIO_FERMO = 1789000010.0
#: il KO delle due partite di prova, fermo per tutto il file
INIZIO_ISO = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()


def scanner_di_prova(canale: Any = None, orologio_fermo: bool = False) -> service.Scanner:
    """Uno Scanner con UNA partita di tennis e UNA di calcio in gioco.

    ``use_stream=False`` e ``canale=False``: nessuna rete, nessuna porta. Il
    canale, quando serve, e' un finto agganciato a mano - cosi' il test misura
    il comportamento dello scanner e non quello di ``websockets``.
    """
    scan = service.Scanner(api_client=None, dry=True, use_stream=False, canale=False,
                           orologio=(lambda: OROLOGIO_FERMO) if orologio_fermo else None)
    # calcolato UNA volta all'import: due scanner costruiti a mezzo secondo di
    # distanza devono produrre la stessa identica riga
    inizio = INIZIO_ISO
    scan.sports["tennis"].metas = {"t1": {
        "event_id": "t1", "market_id": "1.100", "event_name": "Rossi v Bianchi",
        "open_date": inizio, "competition": "ATP", "runners": [],
        "sides": {"p1": 11, "p2": 22},
    }}
    scan.sports["calcio"].metas = {"c1": {
        "event_id": "c1", "market_id": "1.200", "event_name": "Roma v Lazio",
        "open_date": inizio, "competition": "Serie A", "runners": [],
        "sides": {"home": 11, "draw": 22, "away": 33},
    }}
    scan.events["t1"] = {"sport": "tennis", "inplay": True, "mo_status": "OPEN"}
    scan.events["c1"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN"}
    scan._rebuild_market_index()
    if canale is not None:
        scan.canale = canale
    return scan


class CanaleFinto:
    """Il canale come lo usa lo scanner: ``publish`` e ``statistiche``.

    ``esplode=True`` = un canale che solleva a ogni push. Lo scanner deve
    lavorare identico: e' l'invariante B3.
    """

    def __init__(self, esplode: bool = False) -> None:
        #: l'OGGETTO passato a publish (serve alla prova di identita')
        self.messaggi: List[Any] = []
        #: che cosa e' andato DAVVERO SUL FILO: il canale vero serializza dentro
        #: ``publish``, nel thread di chi chiama, e da quel momento il messaggio
        #: e' quello - se il dizionario cambia dopo, il consumatore non lo sapra'
        #: mai. Tenere solo l'oggetto vivo nasconderebbe esattamente il difetto
        #: D3 (verificato il 18/09: la mutazione passava liscia).
        self.spediti: List[Any] = []
        self.esplode = esplode

    def publish(self, topic: str, payload: Any) -> None:
        if self.esplode:
            raise RuntimeError("canale morto")
        # si serializza SUBITO, come fa il canale vero
        sul_filo = json.loads(json.dumps(payload, default=str))
        self.messaggi.append((topic, payload))
        self.spediti.append((topic, sul_filo))

    def statistiche(self) -> Dict[str, Any]:
        return {"saltati": 0, "saltati_client": 0, "client": 1}

    def per_topic(self, topic: str) -> List[Any]:
        """Che cosa e' uscito SUL FILO su questo topic."""
        return [p for t, p in self.spediti if t == topic]


# ===========================================================================
# F0.1 - publish_time_ms: l'istante di BETFAIR, e solo quello
# ===========================================================================
def test_publish_time_ms_preferisce_publish_time_epoch():
    """``publish_time_epoch`` e' lo stesso numero senza andata e ritorno per una
    data: ha la PRECEDENZA.

    Il test deve poterlo dimostrare, non solo dirlo: se i due campi coincidono,
    leggere l'uno o l'altro da' lo stesso numero e la precedenza non e'
    osservabile. Qui i due campi vengono fatti DISCORDARE apposta - e' una
    situazione che in produzione non capita, ed e' esattamente per questo che e'
    la sola prova valida della regola.
    """
    b = book("1.100", CON_PREZZI, publish_time_ms=PT1)
    b.publish_time = datetime.fromtimestamp(PT2 / 1000.0, tz=timezone.utc)
    assert b.publish_time_epoch == PT1
    assert scanner.publish_time_ms(b) == PT1, "ha vinto il datetime sull'epoch"
    # e se l'epoch non ci fosse, il datetime e' il ripiego giusto
    solo_data = book("1.100", CON_PREZZI, publish_time_ms=PT1)
    solo_data.publish_time_epoch = None
    assert scanner.publish_time_ms(solo_data) == PT1


def test_publish_time_ms_None_sui_book_rest():
    """I book del poll REST non hanno ``publishTime``: None, MAI zero.

    Uno zero direbbe "Betfair ha pubblicato all'epoca 0", cioe' una quota vecchia
    di 56 anni: chi calcola un'eta' sopra quel numero si troverebbe un dato
    assurdo invece di un dato assente (catalogo §7: assente non e' zero)."""
    assert scanner.publish_time_ms(book("1.100", CON_PREZZI, publish_time_ms=None)) is None
    assert scanner.publish_time_ms(None) is None


def test_publish_time_ms_non_scambia_un_flag_per_un_istante():
    """``isinstance(True, int)`` e' vero in Python: senza guardia un flag
    diventerebbe l'istante 1 ms."""
    b = book("1.100", CON_PREZZI, publish_time_ms=PT1)
    b.publish_time_epoch = True
    b.publish_time = None
    assert scanner.publish_time_ms(b) is None


# ===========================================================================
# F0.2 - C2: dove stanno i due campi rispetto alla guardia has_any_price
# ===========================================================================
def test_odds_pt_ms_non_avanza_su_un_book_senza_prezzi():
    """IL TEST PIU' IMPORTANTE DELLA FASE (conflitto C2).

    Un book di sola ``marketDefinition`` non e' un aggiornamento di quote: non
    deve toccare ne' ``odds``, ne' ``odds_ts_ms``, ne' ``odds_pt_ms``. Se
    ``odds_pt_ms`` finisse SOPRA la guardia, la riga direbbe che Betfair ha
    appena pubblicato un prezzo che non esiste - l'incidente del 17/09 con un
    campo in piu' per certificarlo.
    """
    for forma in ("oggetti", "dizionari"):
        scan = scanner_di_prova()
        scan._apply_market_book(
            book("1.100", CON_PREZZI, publish_time_ms=PT1, forma=forma), dallo_stream=True)
        ev = scan.events["t1"]
        assert ev["odds_pt_ms"] == PT1, forma
        ts = ev["odds_ts_ms"]

        scan._apply_market_book(
            book("1.100", SOLO_DEFINIZIONE, publish_time_ms=PT2, forma=forma),
            dallo_stream=True)

        assert ev["odds_pt_ms"] == PT1, f"{forma}: odds_pt_ms avanzato senza prezzi"
        assert ev["odds_ts_ms"] == ts, f"{forma}: odds_ts_ms avanzato senza prezzi"


def test_odds_pt_ms_avanza_solo_col_cambio_di_quota():
    """Come ``odds_ts_ms``: e' l'istante dell'ultimo CAMBIO, non dell'ultimo
    book. Un book identico al precedente non lo muove."""
    scan = scanner_di_prova()
    scan._apply_market_book(book("1.100", CON_PREZZI, publish_time_ms=PT1), dallo_stream=True)
    scan._apply_market_book(book("1.100", CON_PREZZI, publish_time_ms=PT2), dallo_stream=True)
    assert scan.events["t1"]["odds_pt_ms"] == PT1, "il book identico ha mosso l'istante"
    scan._apply_market_book(book("1.100", ALTRI_PREZZI, publish_time_ms=PT2), dallo_stream=True)
    assert scan.events["t1"]["odds_pt_ms"] == PT2


def test_bet_delay_arriva_al_payload_match_odds_e_tennis():
    """Il bet delay viene dalla DEFINIZIONE del mercato e vale per tutti e due
    gli sport: e' il numero che nel tennis mancava del tutto."""
    scan = scanner_di_prova()
    scan._apply_market_book(book("1.100", CON_PREZZI, bet_delay=5), dallo_stream=True)
    scan._apply_market_book(book("1.200", CON_PREZZI, bet_delay=3), dallo_stream=True)
    righe, _ = scan.build_rows(datetime.now(timezone.utc))
    per_id = {r["event_id"]: r for r in righe}
    assert per_id["t1"]["payload"]["bet_delay"] == 5
    assert per_id["c1"]["payload"]["bet_delay"] == 3


def test_bet_delay_si_legge_anche_su_un_book_senza_prezzi():
    """STA SOPRA LA GUARDIA di proposito: viene dal ``marketDefinition``, non dai
    prezzi, e un book di sola definizione e' proprio il messaggio che la porta.
    Sotto la guardia, un mercato che consegna solo definizioni resterebbe senza
    bet delay per sempre."""
    scan = scanner_di_prova()
    scan._apply_market_book(book("1.100", SOLO_DEFINIZIONE, bet_delay=5), dallo_stream=True)
    assert scan.events["t1"]["bet_delay"] == 5
    assert scan.events["t1"].get("odds_pt_ms") is None, "un book vuoto ha dato un istante di prezzo"


def test_bet_delay_assente_non_diventa_zero():
    """Un ``bet_delay: 0`` inventato direbbe "nessun ritardo" a chi non lo sa.
    Assente resta assente, e un valore gia' letto non viene cancellato da un
    book che il campo non ce l'ha."""
    scan = scanner_di_prova()
    scan._apply_market_book(book("1.100", CON_PREZZI, bet_delay=None), dallo_stream=True)
    assert "bet_delay" not in scan.events["t1"]
    righe, _ = scan.build_rows(datetime.now(timezone.utc))
    tennis = next(r for r in righe if r["event_id"] == "t1")
    assert tennis["payload"]["bet_delay"] is None
    # e uno zero VERO, dichiarato da Betfair, resta zero
    scan._apply_market_book(book("1.100", ALTRI_PREZZI, bet_delay=0), dallo_stream=True)
    assert scan.events["t1"]["bet_delay"] == 0
    # un book senza il campo NON lo cancella
    scan._apply_market_book(book("1.100", CON_PREZZI, bet_delay=None), dallo_stream=True)
    assert scan.events["t1"]["bet_delay"] == 0


def test_le_chiavi_nuove_sono_nei_due_payload():
    """Calcio e tennis, stessa fase e stesso peso: le due chiavi ci sono in
    entrambi, e nessuna chiave storica se n'e' andata."""
    scan = scanner_di_prova()
    scan._apply_market_book(book("1.100", CON_PREZZI, bet_delay=5, publish_time_ms=PT1),
                            dallo_stream=True)
    scan._apply_market_book(book("1.200", CON_PREZZI, bet_delay=3, publish_time_ms=PT2),
                            dallo_stream=True)
    righe, _ = scan.build_rows(datetime.now(timezone.utc))
    for riga in righe:
        assert "odds_pt_ms" in riga["payload"], riga["sport"]
        assert "bet_delay" in riga["payload"], riga["sport"]
    per_id = {r["event_id"]: r["payload"] for r in righe}
    assert per_id["t1"]["odds_pt_ms"] == PT1
    assert per_id["c1"]["odds_pt_ms"] == PT2
    # le chiavi storiche del tennis non si sono mosse
    assert {"p1", "p2", "sets", "games", "odds", "odds_ts_ms"} <= set(per_id["t1"])


# ===========================================================================
# F0.3 - i campi nuovi NON fanno crescere le scritture sul database
# ===========================================================================
def test_i_campi_nuovi_non_aumentano_le_scritture():
    """Il 13/09 il database e' andato giu' per IO: un campo volatile dentro la
    FIRMA del write-on-change sarebbe una riscrittura a ogni book.

    ``odds_pt_ms`` si muove SOLO insieme a ``odds`` (stesso ramo), quindi non
    aggiunge una sola riscrittura; ``bet_delay`` viene dalla definizione e sta
    fermo. Qui si contano le righe prodotte da 30 book IDENTICI tranne il
    ``publishTime``: devono essere quelle di prima, cioe' UNA.

    L'orologio AVANZA di 3 s a ogni giro, oltre il freno di 2,5 s: cosi' il
    freno non morde MAI e l'unica ragione per cui una riga non viene prodotta e'
    il write-on-change. Con un orologio fermo il freno mascherebbe il difetto e
    il test sarebbe verde per il motivo sbagliato.
    """
    tempo = {"t": 1789000000.0}
    scan = service.Scanner(api_client=None, dry=True, use_stream=False, canale=False,
                           orologio=lambda: tempo["t"])
    scan.sports["tennis"].metas = {"t1": {
        "event_id": "t1", "market_id": "1.100", "event_name": "Rossi v Bianchi",
        "open_date": INIZIO_ISO, "competition": "ATP", "runners": [],
        "sides": {"p1": 11, "p2": 22},
    }}
    scan.events["t1"] = {"sport": "tennis", "inplay": True, "mo_status": "OPEN"}
    scan._rebuild_market_index()
    scan._apply_market_book(book("1.100", CON_PREZZI, bet_delay=5, publish_time_ms=PT1),
                            dallo_stream=True)
    prodotte = len(scan.build_rows(datetime.now(timezone.utc))[0])
    assert prodotte == 1, "la prima riga deve essere prodotta"
    for i in range(30):
        tempo["t"] += 3.0          # oltre il freno: la riga uscirebbe di sicuro
        # stesso book, publishTime SEMPRE DIVERSO: e' il caso che smaschera un
        # campo volatile finito nella firma
        scan._apply_market_book(
            book("1.100", CON_PREZZI, bet_delay=5, publish_time_ms=PT1 + i + 1),
            dallo_stream=True)
        righe, _ = scan.build_rows(datetime.now(timezone.utc))
        prodotte += sum(1 for r in righe if r["event_id"] == "t1")
    assert prodotte == 1, f"{prodotte} righe per 30 book identici: una firma volatile"


def test_odds_pt_ms_e_nella_firma_solo_quando_cambia_la_quota():
    """Controprova diretta sulla firma: due payload che differiscono SOLO per
    ``odds_pt_ms`` hanno firme diverse (la chiave e' nel payload e non e'
    esclusa), ma quel campo si muove solo quando si muove ``odds``, quindi in
    esercizio non produce riscritture in piu'. Senza questa doppia proprieta'
    la chiave andrebbe messa fra i campi rumorosi."""
    a = {"odds": {"p1": 1.3}, "odds_ts_ms": 1, "odds_pt_ms": PT1, "bet_delay": 3}
    b = dict(a, odds_pt_ms=PT2)
    assert scanner.payload_signature(a) != scanner.payload_signature(b)
    assert scanner.payload_signature(a) == scanner.payload_signature(dict(a))


# ===========================================================================
# F0.4 - l'orologio: due orologi non si sottraggono a mano
# ===========================================================================
def test_orologio_marca_impossibile_il_ritardo_negativo(monkeypatch):
    """Un ritardo negativo non e' una latenza bassissima: e' la PROVA che il
    nostro orologio e' indietro. Va letto cosi'."""
    monkeypatch.delenv(orologio.ENV_SCARTO, raising=False)
    fuori = orologio.ritardo_da_betfair(PT1 + 5000, PT1, etichetta="pt->scanner")
    assert fuori["valido"] is True
    assert fuori["ritardo_ms"] == -5000.0
    assert fuori["impossibile"] is True
    dentro = orologio.ritardo_da_betfair(PT1, PT1 + 5000)
    assert dentro["impossibile"] is False and dentro["affidabile"] is True


def test_orologio_dichiara_lassenza_invece_di_inventare_uno_zero(monkeypatch):
    monkeypatch.delenv(orologio.ENV_SCARTO, raising=False)
    vuoto = orologio.ritardo_da_betfair(None, PT1)
    assert vuoto["valido"] is False and vuoto["ritardo_ms"] is None
    assert vuoto["incertezza_ms"] == orologio.SCARTO_MISURATO_MS


def test_orologio_e_un_modulo_puro():
    """CONTRATTO (invariante B1). ``orologio`` lo importa il processo dello
    SCANNER, dove flumine non deve entrare mai: ``flumine/__init__.py``
    sostituisce ``RunnerBookEX`` e il ladder arriva come dizionari, cioe'
    l'incidente del 17/09. Il controllo si fa in SOTTOPROCESSO: nel processo di
    pytest flumine c'e' gia' (lo importa ``bot_service``) e un assert in casa
    sarebbe verde per il motivo sbagliato.
    """
    codice = (
        "import sys;"
        "from Betfair.stream import orologio;"
        "orologio.ritardo_da_betfair(1, 2);"
        "print('FLUMINE', 'flumine' in sys.modules);"
        "print('BLW', 'betfairlightweight' in sys.modules);"
        "print('SUPABASE', 'supabase' in sys.modules)"
    )
    res = subprocess.run([sys.executable, "-c", codice], capture_output=True,
                         text=True, cwd=str(RADICE), timeout=300)
    assert res.returncode == 0, res.stderr[-1200:]
    righe = dict(r.split(" ", 1) for r in res.stdout.strip().splitlines()
                 if r.startswith(("FLUMINE", "BLW", "SUPABASE")))
    assert righe == {"FLUMINE": "False", "BLW": "False", "SUPABASE": "False"}, res.stdout


# ===========================================================================
# F1.1 - l'interruttore: acceso SOLO se qualcuno lo scrive
# ===========================================================================
@pytest.mark.parametrize("valore", ["", "   ", "0", "false", "no", "off", "boh", "2"])
def test_senza_env_il_canale_e_spento(monkeypatch, valore):
    """Default SPENTO. Il verso conta piu' del valore: variabile assente, vuota
    o con qualunque altra scritta = spento.

    a321 aveva il verso opposto (``not in ("0","false","no")``): variabile
    assente -> ACCESO. Con la catena del `.env` che dipende da un import di
    testa, quel verso vuol dire "il canale si accende da solo, in silenzio".
    """
    monkeypatch.setenv(service._CANALE_ENV, valore)
    assert service._letto_acceso() is False
    monkeypatch.delenv(service._CANALE_ENV, raising=False)
    assert service._letto_acceso() is False


@pytest.mark.parametrize("valore", ["1", "true", "TRUE", "si", "Si", "yes", " yes "])
def test_con_lenv_scritto_il_canale_e_acceso(monkeypatch, valore):
    monkeypatch.setenv(service._CANALE_ENV, valore)
    assert service._letto_acceso() is True


def test_interruttori_di_fase_letti_dopo_il_caricamento_del_env(tmp_path):
    """APPENDICE H del piano. Il `.env` arriva allo scanner per la catena di
    import di testa (``stream/auth.py`` -> ``config.load_dotenv()``): non c'e'
    nessuna garanzia esplicita. Se un domani quell'import diventasse pigro -
    cioe' esattamente la cura applicata il 17/09 a ``stream/scalper/__init__``
    - le costanti di modulo prenderebbero il proprio default in silenzio.

    Qui si verifica IN SOTTOPROCESSO che con ``SAFE_SCAN_CANALE=1`` scritto nel
    SOLO `.env` (e NON nell'ambiente) ``service._CANALE_ACCESO`` risulti True.
    Il giorno in cui la catena si spezza, questo test diventa rosso invece di
    lasciare il difetto silenzioso.
    """
    casa = tmp_path / "casa"
    casa.mkdir()
    (casa / ".env").write_text("SAFE_SCAN_CANALE=1\n", encoding="utf-8")
    codice = (
        "import os, sys;"
        f"sys.path.insert(0, {str(RADICE)!r});"
        "from Betfair.safe_strategy import service;"
        "print('AMBIENTE', repr(os.environ.get('SAFE_SCAN_CANALE')));"
        "print('ACCESO', service._CANALE_ACCESO)"
    )
    ambiente = {k: v for k, v in dict(**__import__("os").environ).items()
                if k != service._CANALE_ENV}
    res = subprocess.run([sys.executable, "-c", codice], capture_output=True, text=True,
                         cwd=str(casa), env=ambiente, timeout=300)
    assert res.returncode == 0, res.stderr[-1500:]
    righe = dict(r.split(" ", 1) for r in res.stdout.strip().splitlines()
                 if r.startswith(("AMBIENTE", "ACCESO")))
    assert righe.get("AMBIENTE") == "'1'", (
        "il `.env` NON e' stato caricato prima delle costanti di modulo: la "
        "catena di import si e' spezzata. " + res.stdout + res.stderr[-800:])
    assert righe.get("ACCESO") == "True", res.stdout


def test_lo_stato_dichiara_linterruttore(monkeypatch):
    """L'interruttore non si deduce dai log: si legge, accanto a
    ``flumine_caricato``. Zero letture e zero scritture in piu'."""
    scritte: List[Dict[str, Any]] = []
    monkeypatch.setattr(service.scan_db, "upsert_status", lambda p: scritte.append(p))
    scan = scanner_di_prova()
    scan.dry = False
    scan.publish_status(0)
    assert scritte[0]["canale_acceso"] is False
    assert scritte[0]["canale"] is None
    assert "flumine_caricato" in scritte[0]

    finto = CanaleFinto()
    scan.canale = finto
    scan.publish_status(0)
    assert scritte[1]["canale_acceso"] is True
    assert scritte[1]["canale"] == finto.statistiche()
    # e lo STESSO payload e' uscito sul topic del canale
    assert finto.per_topic(service._TOPIC_SCANNER_STATO) == [scritte[1]]


# ===========================================================================
# F1.2 - D1: un canale per processo, e su un'altra porta si RIFIUTA
# ===========================================================================
def _porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


@pytest.fixture()
def canale_pulito(monkeypatch):
    """Il singleton di modulo azzerato prima e dopo: i test non si passano
    canali fra loro."""
    monkeypatch.setattr(local_channel, "_CHANNEL", None)
    creati: List[Any] = []
    yield creati
    for ch in creati:
        try:
            ch._loop = None
        except Exception:  # noqa: BLE001
            pass


def test_start_channel_su_porta_diversa_rifiuta(canale_pulito):
    """DIFETTO D1. Il singleton e' per processo: chiedere una porta DIVERSA
    restituiva in silenzio il canale gia' attivo. Il giorno in cui un processo
    ne aprisse due, il secondo produttore pubblicherebbe sul canale del primo -
    e se il primo fosse 47331, che ESEGUE ORDINI VERI, si sarebbe allargato il
    canale che comanda."""
    p1, p2 = _porta_libera(), _porta_libera()
    primo = local_channel.start_channel(p1, "safe-scan", solo_lettura=True)
    assert primo is not None
    canale_pulito.append(primo)
    assert local_channel.start_channel(p1, "safe-scan", solo_lettura=True) is primo
    assert local_channel.start_channel(p2, "altro", solo_lettura=True) is None, (
        "il canale di un'altra porta e' stato servito in silenzio")


def test_il_canale_non_ascolta_fuori_da_localhost(canale_pulito):
    """Invariante B8. Due prove: il codice dice 127.0.0.1 e basta, e il server
    risponde davvero solo li'."""
    sorgente = inspect.getsource(local_channel.LocalChannel._serve)
    assert '"127.0.0.1"' in sorgente
    assert "0.0.0.0" not in sorgente
    porta = _porta_libera()
    ch = local_channel.start_channel(porta, "safe-scan", solo_lettura=True)
    assert ch is not None
    canale_pulito.append(ch)
    from websockets.sync.client import connect

    with connect(f"ws://127.0.0.1:{porta}", open_timeout=5) as ws:
        hello = json.loads(ws.recv(timeout=5))
        assert hello["t"] == "hello" and hello["d"]["sport"] == "safe-scan"
        # canale di SOLA LETTURA: nessun comando, mai
        ws.send(json.dumps({"id": 1, "m": "order", "p": {"action": "place"}}))
        res = json.loads(ws.recv(timeout=5))
        assert res["ok"] is False and "sola lettura" in res["e"]


def test_il_canale_dello_scanner_e_di_sola_lettura(monkeypatch, canale_pulito):
    """Il canale 47336 MOSTRA, non comanda: chi comanda resta 47331/47332."""
    porta = _porta_libera()
    monkeypatch.setenv(service._PORTA_CANALE_ENV, str(porta))
    scan = service.Scanner(api_client=None, dry=True, use_stream=False, canale=False)
    ch = scan._avvia_canale()
    assert ch is not None
    canale_pulito.append(ch)
    assert ch.solo_lettura is True and ch.port == porta


def test_canale_ko_non_ferma_lavvio(monkeypatch, canale_pulito):
    """``_avvia_canale`` non solleva MAI: porta occupata, ``websockets``
    assente, qualunque cosa -> None, e lo scanner vive senza."""
    def _esplode(*a: Any, **k: Any) -> None:
        raise RuntimeError("websockets assente")

    monkeypatch.setattr(local_channel, "start_channel", _esplode)
    scan = service.Scanner(api_client=None, dry=True, use_stream=False, canale=False)
    assert scan._avvia_canale() is None


# ===========================================================================
# F1.3 - D3: la riga del canale E' la riga del database
# ===========================================================================
def _prepara_con_prezzi(scan: service.Scanner) -> None:
    scan._apply_market_book(book("1.100", CON_PREZZI, bet_delay=5, publish_time_ms=PT1),
                            dallo_stream=True)
    scan._apply_market_book(book("1.200", CON_PREZZI, bet_delay=3, publish_time_ms=PT2),
                            dallo_stream=True)


@pytest.mark.parametrize("opportunita", [False, True])
def test_la_riga_del_canale_ha_le_stesse_chiavi_della_riga_del_db(monkeypatch, opportunita):
    """DIFETTO D3, il piu' insidioso della fase.

    a321 spingeva la riga PRIMA del blocco ``opportunities``: con
    ``SAFE_SCAN_OPPORTUNITIES=1`` la riga del canale sarebbe stata priva di
    quel blocco, e un consumatore che sostituisce il payload INTERO (e' il
    contratto di ``piu_recente``) sarebbe diventato cieco sulle opportunita' di
    quell'evento esattamente nell'istante in cui il prezzo si muove. E' il
    difetto §7.9 del catalogo vestito da ottimizzazione.

    Qui si misura la proprieta' che conta: chiavi, tipi e VALORI identici, con
    le opportunita' spente e accese, e si misura su CIO' CHE E' ANDATO SUL FILO
    (``finto.spediti``), non sull'oggetto vivo: il canale vero serializza dentro
    ``publish``, quindi un blocco aggiunto al dizionario DOPO il push non
    arriverebbe mai al consumatore, pur essendo nello stesso oggetto.
    """
    monkeypatch.setenv(service._OPPORTUNITIES_ENV, "1" if opportunita else "0")
    monkeypatch.setattr(service.Scanner, "opportunities",
                        lambda self, payload: [{"kind": "ou", "line": 2.5, "edge": 0.07}])
    finto = CanaleFinto()
    scan = scanner_di_prova(canale=finto, orologio_fermo=True)
    _prepara_con_prezzi(scan)
    righe, _ = scan.build_rows(datetime.now(timezone.utc))

    dal_canale = {p["event_id"]: p for _, p in finto.spediti}
    assert set(dal_canale) == {r["event_id"] for r in righe}
    for riga in righe:
        canale = dal_canale[riga["event_id"]]
        assert set(canale) == set(riga), "colonne diverse fra canale e database"
        assert set(canale["payload"]) == set(riga["payload"]), (
            f"payload diverso per {riga['event_id']} (opportunita={opportunita})")
        assert canale == riga, "valori diversi fra canale e database"
    calcio = dal_canale["c1"]["payload"]
    assert ("opportunities" in calcio) is opportunita
    # il tennis non ha mai il blocco opportunita': non e' calcio
    assert "opportunities" not in dal_canale["t1"]["payload"]


def test_la_riga_del_canale_e_lo_stesso_oggetto_del_database(monkeypatch):
    """Non due dizionari uguali per costruzione: LO STESSO oggetto. Cosi' non
    esiste il modo di farli divergere domani."""
    monkeypatch.setenv(service._OPPORTUNITIES_ENV, "0")
    finto = CanaleFinto()
    scan = scanner_di_prova(canale=finto)
    _prepara_con_prezzi(scan)
    righe, _ = scan.build_rows(datetime.now(timezone.utc))
    spinte = [p for _, p in finto.messaggi]
    assert len(spinte) == len(righe) == 2
    for riga in righe:
        assert any(p is riga for p in spinte), "la riga spinta e' una COPIA, non la riga"


def test_il_canale_riceve_anche_la_riga_che_il_freno_del_db_trattiene(monkeypatch):
    """E' il senso della fase: il freno di 2,5 s protegge l'IO di Supabase, non
    il canale. Un cambio di sola QUOTA entro il freno non va sul database ma
    DEVE uscire sul canale - sono i 2,0-2,9 s che si vogliono togliere."""
    monkeypatch.setenv(service._OPPORTUNITIES_ENV, "0")
    finto = CanaleFinto()
    scan = scanner_di_prova(canale=finto)
    adesso = datetime.now(timezone.utc)
    _prepara_con_prezzi(scan)
    righe1, _ = scan.build_rows(adesso)
    assert len(righe1) == 2 and len(finto.messaggi) == 2

    # solo le quote cambiano: la firma critica resta identica e il freno morde
    scan._apply_market_book(book("1.100", ALTRI_PREZZI, bet_delay=5, publish_time_ms=PT2),
                            dallo_stream=True)
    righe2, _ = scan.build_rows(adesso)
    assert righe2 == [], "il freno del database non ha morso: il test non prova niente"
    assert len(finto.messaggi) == 3, "il canale non ha ricevuto la riga frenata"
    ultima = finto.messaggi[-1]
    assert ultima[0] == service._TOPIC_SCAN["tennis"]
    assert ultima[1]["payload"]["odds"]["p1"]["back"] == 1.25


def test_il_topic_calcio_non_porta_mai_una_riga_tennis(monkeypatch):
    """Invariante B12: calcio e tennis non si mischiano mai, nemmeno dentro un
    payload. Due topic separati, e ``sport`` resta comunque nel messaggio: chi
    sbagliasse topic se ne accorgerebbe lo stesso."""
    monkeypatch.setenv(service._OPPORTUNITIES_ENV, "0")
    finto = CanaleFinto()
    scan = scanner_di_prova(canale=finto)
    _prepara_con_prezzi(scan)
    scan.build_rows(datetime.now(timezone.utc))
    assert service._TOPIC_SCAN["calcio"] != service._TOPIC_SCAN["tennis"]
    for riga in finto.per_topic(service._TOPIC_SCAN["calcio"]):
        assert riga["sport"] == "calcio"
        assert "p1" not in riga["payload"] and "sets" not in riga["payload"]
    for riga in finto.per_topic(service._TOPIC_SCAN["tennis"]):
        assert riga["sport"] == "tennis"
        assert "home" not in riga["payload"] and "cs" not in riga["payload"]
    assert len(finto.per_topic(service._TOPIC_SCAN["calcio"])) == 1
    assert len(finto.per_topic(service._TOPIC_SCAN["tennis"])) == 1


def test_il_payload_del_canale_non_contiene_mode(monkeypatch):
    """Invariante B10: paper e live si leggono SOLO dalla riga di trade/control
    del database, mai da un campo del canale, mai ereditati dal trasporto."""
    monkeypatch.setenv(service._OPPORTUNITIES_ENV, "0")
    finto = CanaleFinto()
    scan = scanner_di_prova(canale=finto)
    _prepara_con_prezzi(scan)
    scan.build_rows(datetime.now(timezone.utc))
    for _, riga in finto.messaggi:
        assert "mode" not in riga and "mode" not in riga["payload"]
        assert "paper" not in riga and "live" not in riga


# ===========================================================================
# F1.4 - B3: un canale morto non ferma e non cambia lo scanner
# ===========================================================================
def test_lo_scanner_gira_identico_col_canale_morto(monkeypatch):
    """Invariante B3. Un canale che solleva a OGNI push: stesse righe, stesso
    numero di scritture, stessi payload. Il trasporto non puo' fermare il feed
    unico di tutti i bot."""
    monkeypatch.setenv(service._OPPORTUNITIES_ENV, "0")
    adesso = datetime.now(timezone.utc)

    def _giro(canale: Any) -> Any:
        # orologio FERMO: cosi' i tre giri sono confrontabili CAMPO PER CAMPO,
        # ``updated_at`` e ``odds_ts_ms`` compresi
        scan = scanner_di_prova(canale=canale, orologio_fermo=True)
        _prepara_con_prezzi(scan)
        righe, wanted = scan.build_rows(adesso)
        return (righe, sorted(wanted))

    senza = _giro(None)
    morto = _giro(CanaleFinto(esplode=True))
    vivo = _giro(CanaleFinto())
    assert morto == senza, "col canale morto lo scanner ha prodotto righe diverse"
    assert vivo == senza, "col canale vivo lo scanner ha prodotto righe diverse"


def test_col_canale_spento_il_percorso_e_quello_di_prima(monkeypatch):
    """A interruttore SPENTO non si calcola nulla di nuovo: la riga frenata non
    costruisce nemmeno il dizionario, esattamente come su master. Si misura
    contando le chiamate a ``opportunities``, che e' il calcolo costoso."""
    monkeypatch.setenv(service._OPPORTUNITIES_ENV, "1")
    conti = {"n": 0}

    def _opp(self: Any, payload: Dict[str, Any]) -> List[Any]:
        conti["n"] += 1
        return []

    monkeypatch.setattr(service.Scanner, "opportunities", _opp)
    adesso = datetime.now(timezone.utc)
    scan = scanner_di_prova()          # canale None
    _prepara_con_prezzi(scan)
    scan.build_rows(adesso)
    assert conti["n"] == 1             # una riga di calcio pubblicata
    scan._apply_market_book(book("1.200", ALTRI_PREZZI, bet_delay=3, publish_time_ms=PT2),
                            dallo_stream=True)
    righe, _ = scan.build_rows(adesso)
    assert righe == []                 # il freno morde
    assert conti["n"] == 1, "col canale spento si e' calcolato qualcosa in piu'"


# ===========================================================================
# F1.5 - D4: un consumatore lento non toglie i fotogrammi agli altri
# ===========================================================================
class _WsFinto:
    """Un socket del canale: serve solo come CHIAVE e come destinatario."""

    def __init__(self, nome: str) -> None:
        self.nome = nome
        self.ricevuti: List[str] = []

    async def send(self, text: str) -> None:
        self.ricevuti.append(text)

    def __repr__(self) -> str:  # pragma: no cover - diagnostica
        return f"<ws {self.nome}>"


class _LoopFinto:
    """Il loop asyncio visto da ``publish``: esegue subito, nello stesso thread.

    Serve a misurare la REGOLA (chi riceve e chi no) senza dipendere dai tempi
    di rete: un test che aspetta un socket lento misura la macchina, non il
    codice.
    """

    def __init__(self) -> None:
        self.creati: List[Any] = []

    def call_soon_threadsafe(self, fn: Any) -> None:
        fn()

    def create_task(self, coro: Any) -> None:
        # si registra CHI sarebbe stato inviato e si chiude subito la coroutine:
        # il test misura la REGOLA (chi riceve e chi no), non la rete
        self.creati.append(getattr(coro, "__qualname__", "invio"))
        coro.close()


def test_un_client_fermo_non_toglie_i_fotogrammi_agli_altri():
    """DIFETTO D4. Il tetto degli invii in volo era UNO per tutto il canale:
    una Control Room aperta e lenta (browser in secondo piano) faceva saltare il
    push anche al bot, che sul suo socket non era indietro di niente.

    Qui: un client indietro oltre il tetto, uno pronto. Il pronto riceve, il
    lento no, e il salto viene CONTATO - non assorbito.
    """
    ch = local_channel.LocalChannel(_porta_libera(), sport="safe-scan", solo_lettura=True)
    lento, svelto = _WsFinto("lento"), _WsFinto("svelto")
    loop = _LoopFinto()
    ch._loop = loop
    ch._clients = {lento, svelto}
    ch._n_clients = 2
    ch._in_volo_ws[lento] = local_channel._MAX_INVII_IN_VOLO + 1
    ch._in_volo = local_channel._MAX_INVII_IN_VOLO + 1
    ch._ricalcola_pronti()
    assert ch._client_pronti == 1, "il conteggio dei pronti non vede il client svelto"

    ch.publish("scan_tennis", {"event_id": "t1"})
    assert len(loop.creati) == 1, "il client svelto non ha ricevuto il fotogramma"
    assert ch.statistiche()["saltati_client"] == 1
    assert ch.statistiche()["saltati"] == 0, "il giro e' stato saltato per tutti"


def test_con_tutti_i_client_indietro_il_giro_si_salta_e_lo_si_dice():
    """Quando NESSUNO puo' ricevere si esce prima di serializzare, come prima,
    e il salto si conta: se la coda cresce lo si dice."""
    ch = local_channel.LocalChannel(_porta_libera(), sport="safe-scan", solo_lettura=True)
    fermo = _WsFinto("fermo")
    loop = _LoopFinto()
    ch._loop = loop
    ch._clients = {fermo}
    ch._n_clients = 1
    ch._in_volo_ws[fermo] = local_channel._MAX_INVII_IN_VOLO + 1
    ch._ricalcola_pronti()
    assert ch._client_pronti == 0

    ch.publish("scan_tennis", {"event_id": "t1"})
    assert loop.creati == []
    assert ch.statistiche()["saltati"] == 1


def test_il_conto_per_client_si_svuota_quando_linvio_finisce():
    """Un client che recupera torna a ricevere: il contatore non e' un ergastolo."""
    ch = local_channel.LocalChannel(_porta_libera(), sport="safe-scan", solo_lettura=True)
    ws = _WsFinto("solo")
    ch._loop = _LoopFinto()
    ch._clients = {ws}
    ch._n_clients = 1
    ch._ricalcola_pronti()
    asyncio.run(ch._safe_send(ws, '{"t":"scan_tennis"}'))
    assert ws.ricevuti == ['{"t":"scan_tennis"}']
    assert ch._in_volo_ws.get(ws) is None and ch._in_volo == 0
    assert ch._client_pronti == 1


def test_publish_non_solleva_su_un_payload_non_serializzabile():
    """Il canale ingoia e dichiara: un payload impossibile non deve mai tornare
    indietro allo scanner."""
    ch = local_channel.LocalChannel(_porta_libera(), sport="safe-scan", solo_lettura=True)
    ws = _WsFinto("solo")
    ch._loop = _LoopFinto()
    ch._clients = {ws}
    ch._n_clients = 1
    ch._ricalcola_pronti()

    class _Impossibile:
        def __repr__(self) -> str:
            raise ValueError("nemmeno repr")

    ch.publish("scan_calcio", {"x": _Impossibile()})
    assert ch._loop.creati == []


# ===========================================================================
# F1.6 - B1: col canale acceso lo scanner continua a non importare flumine
# ===========================================================================
def test_lo_scanner_non_importa_flumine_col_canale_acceso():
    """CONTRATTO, invariante B1 estesa alla fase.

    Il sottoprocesso costruisce lo Scanner, accende il canale VERO su una porta
    libera, spinge una riga e lo stato, carica l'Atlante Hazard (il percorso
    vivo che il 17/09 tirava dentro flumine) e poi guarda ``sys.modules``.
    Un import eager di flumine in qualunque punto nuovo lo fa diventare rosso.
    """
    porta = _porta_libera()
    codice = (
        "import sys, os;"
        "os.environ['SAFE_SCAN_WS_PORT'] = %r;" % str(porta) +
        "from Betfair.safe_strategy.service import Scanner;"
        "s = Scanner(api_client=None, dry=True, use_stream=False, canale=False);"
        "ch = s._avvia_canale();"
        "s.canale = ch;"
        "s._spingi_riga('calcio', {'event_id': 'c1', 'sport': 'calcio',"
        " 'payload': {'odds': None}, 'updated_at': 'x'});"
        "s._spingi_stato({'canale_acceso': True});"
        "m = s.opp_model();"
        "print('CANALE', ch is not None);"
        "print('ATLANTE', m is not None);"
        "print('FLUMINE', 'flumine' in sys.modules);"
        "print('GUARDIA', s.flumine_caricato())"
    )
    res = subprocess.run([sys.executable, "-c", codice], capture_output=True,
                         text=True, cwd=str(RADICE), timeout=300)
    assert res.returncode == 0, res.stderr[-1500:]
    righe = dict(r.split(" ", 1) for r in res.stdout.strip().splitlines()
                 if r.startswith(("CANALE", "ATLANTE", "FLUMINE", "GUARDIA")))
    assert righe.get("CANALE") == "True", res.stdout + res.stderr[-800:]
    assert righe.get("ATLANTE") == "True", res.stdout
    assert righe.get("FLUMINE") == "False", (
        "flumine e' entrato nel processo del feed passando dal canale: e' "
        "l'incidente del 17/09. " + res.stdout)
    assert righe.get("GUARDIA") == "False"


# ===========================================================================
# F1.7 - il banco di replay non ha canale, e la certificazione non cambia
# ===========================================================================
def test_il_banco_non_apre_nessun_canale(monkeypatch):
    """``use_stream=False`` (il banco, e ogni test) -> nessun canale, nemmeno
    con l'interruttore acceso. La certificazione misura la stessa identica
    condotta di prima: se il canale toccasse una decisione, la fase sarebbe
    sbagliata."""
    monkeypatch.setattr(service, "_CANALE_ACCESO", True)
    chiamate = {"n": 0}
    monkeypatch.setattr(service.Scanner, "_avvia_canale",
                        lambda self: chiamate.__setitem__("n", chiamate["n"] + 1))
    scan = service.Scanner(api_client=None, dry=True, use_stream=False)
    assert scan.canale is None
    assert chiamate["n"] == 0


def test_spingi_riga_ignora_uno_sport_sconosciuto():
    """Nessun topic di ripiego: uno sport che non ha il suo topic non finisce su
    quello di un altro. Meglio non pubblicare che pubblicare nel posto
    sbagliato."""
    finto = CanaleFinto()
    scan = scanner_di_prova(canale=finto)
    scan._spingi_riga("pallanuoto", {"event_id": "x", "sport": "pallanuoto"})
    assert finto.messaggi == []
