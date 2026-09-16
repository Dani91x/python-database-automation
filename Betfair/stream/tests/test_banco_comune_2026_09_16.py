# -*- coding: utf-8 -*-
"""IL BANCO COMUNE — che sia la catena VERA, non una somigliante.

Questi test difendono quattro cose, e ognuna ha gia' fatto danni quando mancava:

  1. lo SCANNER che alimenta il banco e' quello di produzione, e le righe che
     produce hanno le IDENTICHE chiavi di una riga vera della tabella
     ``safe_strategy_scan`` — non quelle che un finto avrebbe indovinato;
  2. il ladder che gli si passa parla la lingua della PRODUZIONE (`.price` /
     `.size`). Importare flumine ritocca betfairlightweight per tutto il
     processo e i livelli diventano dizionari: lo scanner li leggerebbe come
     None IN SILENZIO. E' la stessa famiglia di difetti del 15/09;
  3. l'orologio dello scanner e' iniettabile e, quando NON lo si inietta, si
     comporta esattamente come prima (la produzione non cambia);
  4. il BET DELAY e' riprodotto: un ordine piazzato a t si abbina sul book di
     t+delay, non su quello di t.

Le registrazioni usate sono REALI (`_live_raw/` e `~/Desktop/tennis_rec`), non
sintetiche: un banco provato su dati inventati non certifica niente.
"""
from __future__ import annotations

import io
import os
import time
from datetime import datetime, timezone

import pytest

from Betfair.safe_strategy import scanner as SCAN
from Betfair.safe_strategy.service import Scanner as ScannerVero
from Betfair.stream.backtest import banco_comune as B

# ---------------------------------------------------------------------------
# le registrazioni usate (reali)
# ---------------------------------------------------------------------------
_RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CALCIO_DIR = os.path.join(_RADICE, "_live_raw")
CALCIO_EVENTO = "35833626"          # in-play dal 15', 2-0 al 56', betDelay 5
TENNIS_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "tennis_rec", "20260707")
TENNIS_EVENTO = "35797319"          # 1-2 di set, in-play

_ha_calcio = os.path.isfile(os.path.join(CALCIO_DIR, CALCIO_EVENTO, f"{CALCIO_EVENTO}.raw.jsonl"))
_ha_tennis = os.path.isfile(os.path.join(TENNIS_DIR, TENNIS_EVENTO, f"{TENNIS_EVENTO}.raw.jsonl"))

# ---------------------------------------------------------------------------
# LA RIGA VERA — da dove viene, dichiarato
# ---------------------------------------------------------------------------
# Letta il 16/09/2026 dalla tabella di PRODUZIONE `safe_strategy_scan` con lo
# stesso client di `Betfair/safe_strategy/db.py` (`db_client.get_supabase_client`,
# `select("*").eq("sport", …).limit(3)`), riga scritta dallo scanner il
# 15/09/2026 14:37:52Z. Qui restano solo le CHIAVI: sono il contratto fra lo
# scanner e i tre bot che leggono quella tabella, ed e' esattamente cio' che un
# finto scritto a memoria sbaglia.
COLONNE_VERE = {"event_id", "payload", "sport", "updated_at"}
PAYLOAD_VERO_CALCIO = {
    "away", "btts", "competition", "cs", "event_name", "home", "ht", "ht_result",
    "inplay", "media", "minute", "mo_market_id", "mo_status", "mo_total_matched",
    "odds", "odds_ts_ms", "open_date", "ou", "pre_ko", "pressure_index",
    "red_away", "red_home", "score_away", "score_home", "score_raw", "timeline",
}
PAYLOAD_VERO_TENNIS = {
    "competition", "event_name", "games", "inplay", "media", "mo_market_id",
    "mo_status", "mo_total_matched", "odds", "odds_ts_ms", "open_date", "p1",
    "p2", "score_raw", "sets",
}
OU_BLOCCO_VERO = {"bet_delay", "inplay", "line", "market_id", "market_type",
                  "seen_ms", "selections", "status", "total_matched", "ts_ms"}
OU_SELEZIONE_VERA = {"back", "back_size", "lay", "lay_size", "name",
                     "runner_status", "selection_id"}
CS_BLOCCO_VERO = {"any_other_away", "any_other_home", "inplay", "market_id",
                  "selections", "status", "total_matched"}


def _mercato_vivo(row, linea=3.5):
    """Il blocco della linea con il mercato APERTO e prezzi veri, o None."""
    if row is None or not row["payload"].get("inplay"):
        return None
    b = {x["line"]: x for x in (row["payload"].get("ou") or [])}.get(linea)
    if not b or b.get("status") != "OPEN" or not b.get("bet_delay"):
        return None
    if not any(s.get("back") and s.get("back_size") for s in b["selections"]):
        return None
    return b


def _replay(sport: str, cartella: str, evento: str, servizio=None, **kw):
    """Torna (esito, ultima riga, ultima riga col mercato 3.5 vivo)."""
    ultime = {}

    def _raccogli(**args):
        riga = args.get("row")
        if riga:
            ultime["row"] = riga
            if _mercato_vivo(riga) is not None:
                ultime["viva"] = riga
        if servizio is not None:
            servizio(**args)

    esito = B.replay_evento(event_id=evento, cartella=cartella, servizio=_raccogli,
                            sport=sport, ogni_ms=kw.pop("ogni_ms", 5000), **kw)
    return esito, ultime.get("row"), ultime.get("viva")


# ===========================================================================
# 1. lo scanner del banco e' quello vero, e non tocca la rete
# ===========================================================================
class _ClienteChePrende(Exception):
    pass


class _ClienteVietato:
    """Un client Betfair che ESPLODE se qualcuno lo tocca."""

    def __getattr__(self, nome):
        raise _ClienteChePrende(f"il banco ha toccato il client Betfair: {nome}")


def test_lo_scanner_del_banco_non_tocca_la_rete():
    """Costruire lo Scanner con un client vietato non deve toccarlo.

    Se un giorno `__init__` facesse login, aprisse lo stream o chiamasse REST,
    questo test diventa rosso e il banco non puo' piu' dire "nessuna rete".
    """
    s = ScannerVero(api_client=_ClienteVietato(), dry=True, use_stream=False)
    assert s.stream is None            # il pool nasce solo con use_stream=True
    assert s.dry is True
    # e nemmeno il banco lo tocca costruendo il suo scanner
    banco = B.ScannerReplay(sport="calcio")
    assert banco.scan.client is None
    assert banco.scan.stream is None


# ===========================================================================
# 2. il ladder deve parlare la lingua della produzione
# ===========================================================================
class _ExDiFlumine:
    """`flumine.patching.EX`: i livelli sono DIZIONARI."""

    def __init__(self):
        self.available_to_back = [{"price": 2.5, "size": 100.0}]
        self.available_to_lay = [{"price": 2.6, "size": 80.0}]
        self.traded_volume = []


class _RunnerFinto:
    def __init__(self):
        self.selection_id = 1
        self.status = "ACTIVE"
        self.last_price_traded = 2.55
        self.total_matched = 10.0
        self.ex = _ExDiFlumine()


class _BookFinto:
    def __init__(self):
        self.market_id = "1.1"
        self.runners = [_RunnerFinto()]
        self.inplay = True
        self.status = "OPEN"
        self.total_matched = 10.0
        self.bet_delay = 5
        self.market_definition = None
        self.publish_time = datetime.now(timezone.utc)


def test_il_ladder_di_flumine_e_muto_per_lo_scanner():
    """LA PROVA DEL DANNO: coi dizionari di flumine lo scanner legge None.

    `scanner.price_pair` chiede `levels[0].price` dentro un `except Exception`
    che ritorna None. Passargli il ladder di flumine cosi' com'e' non da'
    errore: da' PREZZI ASSENTI, in silenzio. E' il motivo per cui il banco
    riespone i livelli nella forma di produzione.
    """
    grezzo = SCAN.price_pair(_ExDiFlumine())
    assert grezzo == {"back": None, "lay": None, "back_size": None, "lay_size": None}

    vista = B.libro_di_produzione(_BookFinto())
    tradotto = SCAN.price_pair(vista.runners[0].ex)
    assert tradotto == {"back": 2.5, "lay": 2.6, "back_size": 100.0, "lay_size": 80.0}


def test_la_vista_del_book_porta_tutto_quello_che_lo_scanner_legge():
    """La vista non deve PERDERE campi: sono quelli che `_apply_market_book`,
    `_apply_cs_book` e `_apply_opp_book` leggono davvero."""
    vista = B.libro_di_produzione(_BookFinto())
    assert vista.market_id == "1.1"
    assert vista.inplay is True
    assert vista.status == "OPEN"
    assert vista.total_matched == 10.0
    assert vista.bet_delay == 5
    r = vista.runners[0]
    assert (r.selection_id, r.status, r.last_price_traded) == (1, "ACTIVE", 2.55)


# ===========================================================================
# 3. orologio iniettabile, produzione invariata
# ===========================================================================
def test_senza_orologio_lo_scanner_usa_quello_del_pc():
    """PARITA': con `orologio=None` (la produzione) le tre letture dell'ora sono
    quelle di prima — `time.time`, `time.monotonic`, `scanner.now_iso`."""
    s = ScannerVero(api_client=None, dry=True)
    assert s.orologio is None
    assert abs(s._ora() - time.time()) < 2.0
    assert abs(s._ora_mono() - time.monotonic()) < 2.0
    prima = SCAN.parse_iso(SCAN.now_iso())
    suo = SCAN.parse_iso(s._ora_iso())
    assert prima is not None and suo is not None
    assert abs((suo - prima).total_seconds()) < 2.0


def test_con_orologio_iniettato_adesso_e_il_tick():
    s = ScannerVero(api_client=None, dry=True, orologio=lambda: 1782472864.337)
    assert s._ora() == pytest.approx(1782472864.337)
    assert s._ora_mono() == pytest.approx(1782472864.337)
    assert s._ora_iso().startswith("2026-06-26T")


def test_freeze_pre_ko_senza_parametro_si_comporta_come_prima():
    """PARITA' della funzione condivisa: `adesso_iso` e' additivo."""
    odds = {"home": {"back": 2.0}, "draw": {"back": 3.0}, "away": {"back": 4.0}}
    prima = SCAN.freeze_pre_ko(None, False, odds)
    dopo = SCAN.freeze_pre_ko(None, False, odds, adesso_iso=None)
    assert prima.keys() == dopo.keys()
    assert {k: v for k, v in prima.items() if k != "captured_at"} == \
           {k: v for k, v in dopo.items() if k != "captured_at"}
    # e con l'ora dichiarata e' quella, non l'orologio del PC
    con = SCAN.freeze_pre_ko(None, False, odds, adesso_iso="2026-06-26T11:21:04+00:00")
    assert con["captured_at"] == "2026-06-26T11:21:04+00:00"
    # in-play il riferimento NON si aggiorna piu' (congelato), qui come prima
    assert SCAN.freeze_pre_ko(con, True, odds, adesso_iso="2026-06-26T12:00:00+00:00") is con


# ===========================================================================
# 4. il banco produce righe VERE (calcio)
# ===========================================================================
@pytest.mark.skipif(not _ha_calcio, reason="registrazione calcio assente")
def test_banco_calcio_produce_una_riga_con_le_chiavi_della_tabella_vera():
    esito, riga, viva = _replay("calcio", CALCIO_DIR, CALCIO_EVENTO)
    assert not esito.errori, esito.errori
    assert riga is not None, "il banco non ha prodotto nessuna riga di scan"
    assert set(riga.keys()) == COLONNE_VERE
    assert riga["sport"] == "calcio"
    assert riga["event_id"] == CALCIO_EVENTO
    payload = riga["payload"]
    assert set(payload.keys()) == PAYLOAD_VERO_CALCIO

    # O/U: le linee ci sono e i blocchi hanno le chiavi del vero
    linee = sorted(b["line"] for b in payload["ou"])
    assert 3.5 in linee and 4.5 in linee, linee
    blocco = payload["ou"][0]
    assert OU_BLOCCO_VERO <= set(blocco.keys()), set(blocco.keys())
    assert OU_SELEZIONE_VERA == set(blocco["selections"][0].keys())

    # I PREZZI CI SONO DAVVERO su un mercato APERTO: se il ladder fosse muto
    # (i dizionari di flumine dati allo scanner) sarebbero tutti None e questo
    # test sarebbe rosso.
    assert viva is not None, "nessun tick col mercato 3.5 aperto"
    b35 = _mercato_vivo(viva)
    assert any(s.get("back") and s.get("back_size") for s in b35["selections"])
    # i nomi sono leggibili dal canonicalizzatore del feed (`canonical_selection`)
    assert {s["name"].split()[0] for s in b35["selections"]} == {"Under", "Over"}

    # CORRECT_SCORE presente, nella forma di `build_cs_block`
    assert payload["cs"] is not None
    assert CS_BLOCCO_VERO <= set(payload["cs"].keys())
    # LIMITE 1 DEL BANCO, messo per iscritto qui: i nomi del Correct Score non
    # sono nello stream e senza catalogo restano vuoti. Chi certifichera' Omega
    # deve portarli (`nomi_extra`) o dichiararlo.
    assert all(s["name"] == "" for s in payload["cs"]["selections"])

    # i PUNTEGGI sono arrivati dal sidecar attraverso il parser vero
    assert payload["minute"] is not None and payload["minute"] > 0
    assert payload["score_home"] is not None and payload["score_away"] is not None
    assert payload["score_raw"], "lo stato IPS grezzo deve viaggiare nel payload"


@pytest.mark.skipif(not _ha_calcio, reason="registrazione calcio assente")
def test_lora_della_riga_e_il_tick_non_loriologio_del_pc():
    """`updated_at` deve essere il tempo della REGISTRAZIONE. Con l'ora del PC
    ogni riga nascerebbe vecchia di mesi e nessun bot opererebbe."""
    _esito, riga, _viva = _replay("calcio", CALCIO_DIR, CALCIO_EVENTO)
    quando = SCAN.parse_iso(riga["updated_at"])
    assert quando is not None
    # la registrazione e' di mesi fa: l'ora della riga la segue, non insegue il PC
    assert (datetime.now(timezone.utc) - quando).total_seconds() > 86400


# ===========================================================================
# 5. il banco produce righe VERE (tennis)
# ===========================================================================
@pytest.mark.skipif(not _ha_tennis, reason="registrazione tennis assente")
def test_banco_tennis_produce_una_riga_con_le_chiavi_della_tabella_vera():
    esito, riga, _viva = _replay("tennis", TENNIS_DIR, TENNIS_EVENTO)
    assert not esito.errori, esito.errori
    assert riga is not None
    assert set(riga.keys()) == COLONNE_VERE
    assert riga["sport"] == "tennis"
    payload = riga["payload"]
    assert set(payload.keys()) == PAYLOAD_VERO_TENNIS
    # set e game arrivano dal sidecar `<id>.score.jsonl` via parse_tennis_scores
    assert payload["sets"] is not None and set(payload["sets"]) == {"p1", "p2"}
    assert payload["games"] is not None and set(payload["games"]) == {"p1", "p2"}
    # le quote 1X2 del tennis, coi due lati
    assert payload["odds"] is not None and set(payload["odds"]) == {"p1", "p2"}
    assert any((payload["odds"][k] or {}).get("back") for k in ("p1", "p2"))


# ===========================================================================
# 6. IL BET DELAY — un ordine si abbina sul book di t+delay
# ===========================================================================
@pytest.mark.skipif(not _ha_calcio, reason="registrazione calcio assente")
def test_bet_delay_lordine_aspetta_betfair():
    """Su un mercato IN GIOCO Betfair trattiene l'ordine `betDelay` secondi.

    Il banco lo riproduce facendo scorrere il TEMPO DI MERCATO: quando
    `place_order_live` ritorna, l'orologio della simulazione e' avanzato di
    almeno `betDelay`, cioe' l'ordine e' stato valutato sul book di DOPO.

    FALSIFICAZIONE dentro il test: lo stesso piazzamento, fatto togliendo il
    motore (cioe' forzando l'esecuzione come faceva il banco prima), avanza di
    ZERO. Se un domani qualcuno rimettesse il bypass, la prima meta' di questo
    test diventa rossa.
    """
    import flumine.config

    misure = {}

    def servizio(*, db, market, now, row, banco, strategia, **_):
        if misure or row is None or not row["payload"].get("inplay"):
            return
        blocco = _mercato_vivo(row)
        if blocco is None:
            return
        sel = next((s for s in blocco["selections"]
                    if s.get("back") and s.get("back_size")), None)
        mid = blocco["market_id"]
        if sel is None or str(mid) not in strategia.mercati:
            return
        atteso = float(blocco["bet_delay"])

        # (a) con il motore: si aspetta Betfair
        t0 = flumine.config.current_time
        market.place_order_live(market_id=mid, selection_id=int(sel["selection_id"]),
                                price=float(sel["back"]), size=2.0,
                                event_id=CALCIO_EVENTO, side="back",
                                customer_ref="cert-delay-1", fill_or_kill=True)
        t1 = flumine.config.current_time
        # (b) senza motore: il bypass di prima
        motore = market.motore
        market.motore = None
        try:
            market.place_order_live(market_id=mid, selection_id=int(sel["selection_id"]),
                                    price=float(sel["back"]), size=2.0,
                                    event_id=CALCIO_EVENTO, side="back",
                                    customer_ref="cert-delay-2", fill_or_kill=True)
        finally:
            market.motore = motore
        t2 = flumine.config.current_time
        misure["atteso"] = atteso
        misure["con_motore_s"] = (t1 - t0).total_seconds()
        misure["senza_motore_s"] = (t2 - t1).total_seconds()

    esito, _riga, _viva = _replay("calcio", CALCIO_DIR, CALCIO_EVENTO, servizio=servizio)
    assert misure, "nessun tick in gioco con betDelay: il test non ha misurato niente"
    assert misure["atteso"] >= 1.0
    # (a) col motore l'orologio di mercato e' avanzato di almeno il bet delay
    assert misure["con_motore_s"] >= misure["atteso"], misure
    # (b) col bypass NON avanza: ecco che cosa si stava certificando prima
    assert misure["senza_motore_s"] == 0.0, misure
    assert esito.book_attesi > 0


# ===========================================================================
# 7. i punteggi passano dalla funzione VERA, col record VERO
# ===========================================================================
@pytest.mark.skipif(not _ha_calcio, reason="registrazione calcio assente")
def test_i_punteggi_arrivano_dal_record_ips_grezzo():
    """Il sidecar porta il record IPS COSI' COM'E': lo legge
    `Scanner.apply_score_state`, cioe' la stessa funzione di `poll_scores`."""
    punteggi = B.carica_punteggi(CALCIO_DIR, CALCIO_EVENTO, "calcio")
    assert punteggi, "sidecar punteggi non letto"
    ts, record = punteggi[-1]
    assert isinstance(ts, int) and ts > 1_700_000_000_000
    # le chiavi sono quelle di Betfair IPS, non una nostra riscrittura
    assert "score" in record and "home" in record["score"]

    banco = B.ScannerReplay(sport="calcio")
    # senza l'evento nello stato, il punteggio NON crea eventi dal nulla
    assert banco.applica_punteggio(CALCIO_EVENTO, record) is False
    banco.scan.events[CALCIO_EVENTO] = {"sport": "calcio", "inplay": True}
    assert banco.applica_punteggio(CALCIO_EVENTO, record) is True
    ev = banco.scan.events[CALCIO_EVENTO]
    assert ev["minute"] is not None
    assert ev["score_home"] is not None and ev["score_away"] is not None
    assert ev["score_raw"]


@pytest.mark.skipif(not _ha_tennis, reason="registrazione tennis assente")
def test_i_punteggi_tennis_arrivano_dal_sidecar_score_jsonl():
    punteggi = B.carica_punteggi(TENNIS_DIR, TENNIS_EVENTO, "tennis")
    assert punteggi
    _ts, record = punteggi[-1]
    banco = B.ScannerReplay(sport="tennis")
    banco.scan.events[TENNIS_EVENTO] = {"sport": "tennis", "inplay": True}
    assert banco.applica_punteggio(TENNIS_EVENTO, record) is True
    ev = banco.scan.events[TENNIS_EVENTO]
    assert ev["sets"] is not None and ev["games"] is not None


# ===========================================================================
# 8. il pre_ko si congela da solo, come in produzione
# ===========================================================================
@pytest.mark.skipif(not _ha_calcio, reason="registrazione calcio assente")
def test_il_pre_ko_lo_congela_lo_scanner_non_il_banco():
    """Nessun codice del banco tocca `pre_ko`: lo fa `freeze_pre_ko` dentro
    `_apply_market_book`. Qui si verifica che, a partita iniziata, il
    riferimento non venga piu' aggiornato con quote in-play."""
    catturati = []

    def servizio(*, row, **_):
        if row and row["payload"].get("inplay"):
            catturati.append(row["payload"].get("pre_ko"))

    _esito, _riga, _viva = _replay("calcio", CALCIO_DIR, CALCIO_EVENTO, servizio=servizio)
    assert catturati, "nessun giro in gioco"
    # tutti uguali fra loro: o sempre None (registrazione gia' in corso) o
    # sempre lo stesso riferimento congelato. Mai due valori diversi.
    assert len({repr(x) for x in catturati}) == 1, catturati[:3]


# ===========================================================================
# 9. L'ANNULLO — `cancel_order_live`, col cancel vero di flumine
# ===========================================================================
def _scenario_annulli():
    """UNA sola corsa sulla registrazione, quattro annulli diversi.

    Il bot chiede l'annullo vero dal 16/09 (`execution.annulla_su_betfair` ->
    `market.cancel_order_live`): finche' il banco non sapeva farlo, ogni annullo
    tornava "esito IGNOTO", la gamba restava pending e il freno anti-duplicato
    bloccava tutte le gambe successive con lo stesso ruolo.
    """
    stato = {"fase": 0}
    esiti = {}

    def servizio(*, market, row, strategia, **_):
        b = _mercato_vivo(row)
        if b is None:
            # a mercato NON aperto: che cosa risponde flumine a un annullo
            if stato["fase"] == 2 and row is not None and "sospeso" not in esiti:
                b3 = {x["line"]: x for x in (row["payload"].get("ou") or [])}.get(3.5)
                if b3 and b3.get("status") and b3["status"] != "OPEN":
                    r = market.cancel_order_live(esiti["bet2"], b3["market_id"])
                    esiti["sospeso"] = (b3["status"], r)
            return
        mid = b["market_id"]
        sel = next((x for x in b["selections"] if x.get("back") and x.get("back_size")), None)
        if sel is None or str(mid) not in strategia.mercati:
            return
        sid = int(sel["selection_id"])

        if stato["fase"] == 0:
            # A) ordine APPOGGIATO che non si abbina mai (BACK a 1000: servirebbe
            #    un banco a 1000, che non esiste) -> resta sul book
            r = market.place_order_live(market_id=mid, selection_id=sid, price=1000.0,
                                        size=2.0, event_id=CALCIO_EVENTO, side="back",
                                        customer_ref="cert-riposo", fill_or_kill=False)
            esiti["riposo_place"] = r
            esiti["riposo_vivi"] = list(market.list_current_orders())
            esiti["riposo_cancel"] = market.cancel_order_live(r.bet_id, mid)
            esiti["riposo_vivi_dopo"] = list(market.list_current_orders())
            esiti["riposo_cleared"] = list(market.list_cleared_orders())
            # B) lo stesso ordine, annullato due volte
            esiti["due_volte"] = market.cancel_order_live(r.bet_id, mid)
            # C) un bet_id che il banco non conosce
            esiti["ignoto"] = market.cancel_order_live("non-esiste", mid)
            stato["fase"] = 1
            return

        if stato["fase"] == 1:
            # D) ordine PARZIALMENTE abbinato: al prezzo del tocco con una size
            #    piu' grande della liquidita' disponibile
            disp = float(sel["back_size"])
            r = market.place_order_live(market_id=mid, selection_id=sid,
                                        price=float(sel["back"]),
                                        size=round(disp * 3 + 5, 2),
                                        event_id=CALCIO_EVENTO, side="back",
                                        customer_ref="cert-parziale", fill_or_kill=False)
            esiti["parziale_place"] = r
            esiti["parziale_disp"] = disp
            esiti["parziale_cancel"] = market.cancel_order_live(r.bet_id, mid)
            r2 = market.place_order_live(market_id=mid, selection_id=sid, price=1000.0,
                                         size=2.0, event_id=CALCIO_EVENTO, side="back",
                                         customer_ref="cert-riposo2", fill_or_kill=False)
            esiti["bet2"] = r2.bet_id
            stato["fase"] = 2
            return

    ore = []

    def con_orologio(**kw):
        ore.append(kw["banco"].ora)
        servizio(**kw)

    esito, _riga, _viva = _replay("calcio", CALCIO_DIR, CALCIO_EVENTO,
                                  servizio=con_orologio)
    assert not esito.errori, esito.errori
    esiti["_esito"] = esito
    esiti["_ore"] = ore
    return esiti


@pytest.mark.skipif(not _ha_calcio, reason="registrazione calcio assente")
def test_annullo_di_un_ordine_appoggiato_non_abbinato():
    e = _scenario_annulli()
    assert e["riposo_place"].ok and e["riposo_place"].size_matched == 0.0
    assert [o["customer_order_ref"] for o in e["riposo_vivi"]] == ["cert-riposo"]
    c = e["riposo_cancel"]
    assert c.ok is True and c.status == "SUCCESS" and c.riletto is True
    assert c.size_cancelled == 2.0 and c.size_matched == 0.0 and c.size_remaining == 0.0
    # l'ordine NON e' piu' vivo, e il residuo annullato si vede
    assert [o["customer_order_ref"] for o in e["riposo_vivi_dopo"]] == []
    riga = next(o for o in e["riposo_cleared"] if o["customer_order_ref"] == "cert-riposo")
    assert riga["status"] == "EXECUTION_COMPLETE"
    assert riga["size_cancelled"] == 2.0 and riga["size_remaining"] == 0.0


@pytest.mark.skipif(not _ha_calcio, reason="registrazione calcio assente")
def test_annullo_di_un_ordine_parzialmente_abbinato_lascia_la_parte_abbinata():
    e = _scenario_annulli()
    assert e["parziale_place"].ok
    abbinato = e["parziale_place"].size_matched
    assert 0 < abbinato < float(e["parziale_place"].size_matched) + 1e9
    assert abbinato == pytest.approx(e["parziale_disp"], abs=0.01), (
        "l'abbinamento deve fermarsi alla liquidita' disponibile al tocco")
    c = e["parziale_cancel"]
    assert c.ok is True and c.riletto is True
    # la parte ABBINATA resta, il resto e' annullato
    assert c.size_matched == pytest.approx(abbinato, abs=0.01)
    assert c.size_remaining == 0.0
    assert c.size_cancelled > 0.0
    assert c.avg_price_matched is not None


@pytest.mark.skipif(not _ha_calcio, reason="registrazione calcio assente")
def test_annullo_impossibile_lo_dice_senza_mentire():
    """Tre modi in cui un annullo NON riesce, e come li deve raccontare.

    `riletto` e' la differenza fra «so che non e' andato» (lo stato dell'ordine
    e' sotto i nostri occhi) e «non lo so» (il chiamante DEVE riconciliare):
    `_mark_trade_cancelled` legge proprio `ok and riletto`.
    """
    e = _scenario_annulli()
    # gia' completo: Betfair risponderebbe ERROR_IN_ORDER, flumine alza
    # OrderUpdateError. Stato NOTO -> riletto True, ma non confermato.
    due = e["due_volte"]
    assert due.ok is False and due.riletto is True
    assert "EXECUTION_COMPLETE" in str(due.error_code)
    assert due.size_cancelled == 0.0
    # bet_id sconosciuto: NON si puo' sapere -> riletto False
    ign = e["ignoto"]
    assert ign.ok is False and ign.riletto is False
    assert ign.error_code == "BET_NOT_FOUND"
    # mercato NON aperto: comportamento di flumine, dichiarato
    if "sospeso" in e:
        stato, r = e["sospeso"]
        assert stato != "OPEN"
        assert r.ok is False and r.size_cancelled == 0.0
        assert r.error_code, "un annullo rifiutato deve dire perche'"

# ===========================================================================
# 10. L'OROLOGIO DI MERCATO NON TORNA INDIETRO
# ===========================================================================
@pytest.mark.skipif(not _ha_calcio, reason="registrazione calcio assente")
def test_lorologio_di_mercato_non_torna_mai_indietro():
    """I book NON arrivano in ordine di tempo, e con un tempo che indietreggia
    flumine rifiuta ordini legittimi.

    Il generatore storico consegna a ogni aggiornamento lo snapshot dei mercati
    sottoscritti, e ogni MarketBook porta il publish time DEL SUO mercato:
    misurato, il 47% arriva piu' vecchio del precedente (fino a 182 s
    all'indietro). Passandoli tali e quali a `simulated_datetime`,
    `RunnerContext.reset_elapsed_seconds` diventa NEGATIVO e il controllo
    STRATEGY_EXPOSURE di flumine boccia il piazzamento successivo
    (`flumine/strategy/strategy.py:162-171`).
    """
    import flumine.config as fconf

    e = _scenario_annulli()
    esito = e["_esito"]
    # 1) il problema esiste davvero su questa registrazione
    assert esito.book_in_ritardo > 0, (
        "nessun book in ritardo: la registrazione non mette alla prova la regola")
    # 2) l'orologio dello scanner e' MONOTONO, per costruzione e nei fatti
    banco = B.ScannerReplay(sport="calcio")
    assert banco.imposta_ora(1000.0) == 1000.0
    assert banco.imposta_ora(990.0) == 1000.0, "l'ora dello scanner e' tornata indietro"
    assert banco.ora == 1000.0 and banco.adesso().timestamp() == 1000.0
    ore = e["_ore"]
    assert ore and all(b >= a for a, b in zip(ore, ore[1:])), "l'ora del banco torna indietro"
    # 3) e quello di flumine pure: nessun ordine rifiutato da un suo controllo
    #    (prima della correzione il piazzamento parziale veniva bocciato con
    #    "reset_elapsed_seconds (-6.286) < reset_seconds (0.0)")
    assert e["parziale_place"].ok is True
    assert fconf.current_time is not None


# ===========================================================================
# 11. UN SOLO SimulatedMiddleware — il fill passivo non si conta due volte
# ===========================================================================
def test_il_banco_monta_un_solo_middleware_simulato():
    """`BaseFlumine.add_client` lo monta gia' (`baseflumine.py:89-94`) e
    `add_market_middleware` NON de-duplica nella 2.13.11: il secondo faceva
    consumare DUE VOLTE il delta di `traded_volume`, e la stessa lay appoggiata
    passava da 85,72 a 200,34 EUR abbinati (+134%)."""
    import flumine.config as fconf
    from flumine import FlumineSimulation
    from flumine.markets.middleware import SimulatedMiddleware

    prima = fconf.simulated
    fconf.simulated = True
    try:
        quadro = FlumineSimulation(client=B.cliente_simulato())
        quanti = lambda q: sum(isinstance(m, SimulatedMiddleware)
                               for m in q._market_middleware)
        assert quanti(quadro) == 1, "flumine lo monta da solo"
        assert B.assicura_middleware_simulato(quadro) == 1
        assert quanti(quadro) == 1, "l'helper non deve aggiungerne un secondo"
        # e se qualcuno ne infila un secondo, l'helper GRIDA invece di tacere
        quadro.add_market_middleware(SimulatedMiddleware())
        with pytest.raises(RuntimeError, match="SimulatedMiddleware"):
            B.assicura_middleware_simulato(quadro)
    finally:
        fconf.simulated = prima


def test_nessuno_nel_repo_monta_il_middleware_a_mano():
    """L'unico punto da cui si monta e' `assicura_middleware_simulato`.

    Il 16/09 erano 15 i punti che lo aggiungevano a mano: ognuno raddoppiava il
    riempimento passivo del suo backtest. Questo test rifiuta il ritorno."""
    import re

    colpevoli = []
    for cartella, _sub, files in os.walk(os.path.join(_RADICE, "Betfair")):
        if "__pycache__" in cartella:
            continue
        for nome in files:
            if not nome.endswith(".py"):
                continue
            percorso = os.path.join(cartella, nome)
            testo = io.open(percorso, encoding="utf-8", errors="replace").read()
            for n, riga in enumerate(testo.splitlines(), 1):
                if re.search(r"\.add_market_middleware\(\s*SimulatedMiddleware\(", riga):
                    rel = os.path.relpath(percorso, _RADICE).replace("\\", "/")
                    if rel == "Betfair/stream/backtest/banco_comune.py":
                        continue          # e' l'helper: e' il posto giusto
                    if rel == "Betfair/stream/tests/test_banco_comune_2026_09_16.py":
                        continue          # qui il secondo si aggiunge APPOSTA
                    colpevoli.append(f"{rel}:{n}")
    assert not colpevoli, (
        "questi montano un SECONDO SimulatedMiddleware (fill passivo contato "
        f"due volte): {colpevoli}. Usa "
        "banco_comune.assicura_middleware_simulato(framework).")


def test_i_tetti_del_client_simulato_sono_aperti():
    """Anche `transaction_limit` (5000/ora sull'ora di MERCATO,
    `controls/clientcontrols.py:58-86`): e' un tetto di flumine, non del bot."""
    c = B.cliente_simulato()
    assert c.min_bet_size == 0.0 and c.min_bet_payout == 0.0
    assert c.min_bsp_liability == 0.0
    assert c.transaction_limit is None


def test_orologio_monotono_regge_i_book_fuori_ordine():
    """`orologio_monotono()` protegge QUALUNQUE simulazione del processo — banco
    comune e Backtest Automatico — non solo il motore del banco.

    Senza, `SimulatedDateTime.__call__` accetta un publish time piu' vecchio e
    il tempo simulato torna indietro: da li' `elapsed_seconds` va negativo e i
    controlli di flumine rifiutano ordini legittimi."""
    import flumine.config as fconf
    from flumine.simulation.utils import SimulatedDateTime

    t0 = datetime(2026, 7, 17, 13, 48, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 7, 17, 13, 48, 6, tzinfo=timezone.utc)
    prima = fconf.current_time
    try:
        with B.orologio_monotono() as stato:
            orologio = SimulatedDateTime()
            orologio(t1)
            assert fconf.current_time == t1
            orologio(t0)                      # book in ritardo: il tempo NON torna
            assert fconf.current_time == t1, "l'orologio simulato e' tornato indietro"
            assert stato["in_ritardo"] == 1
            orologio(t1 + (t1 - t0))          # avanti si', sempre
            assert fconf.current_time > t1
        # fuori dal contesto flumine torna com'era: nessun ritocco permanente
        orologio = SimulatedDateTime()
        orologio(t1)
        orologio(t0)
        assert fconf.current_time == t0
    finally:
        fconf.current_time = prima


# ===========================================================================
# 12. IL LAPSE — gli ordini appoggiati muoiono quando Betfair li uccide
# ===========================================================================
@pytest.mark.skipif(not _ha_calcio, reason="registrazione calcio assente")
def test_lapse_alla_sospensione_come_farebbe_betfair():
    """Un ordine LAPSE non abbinato non sopravvive alla sospensione in gioco.

    Lo fa gia' flumine (`simulation/simulatedorder.py:57-62`), ma il banco deve
    RACCONTARLO come Betfair: fuori da `list_current_orders`, dentro
    `list_cleared_orders` con `size_lapsed`. Se non lo raccontasse, un bot
    crederebbe di avere ancora una copertura appoggiata che non esiste piu'.
    """
    visto = {}

    def servizio(*, market, row, strategia, **_):
        b = _mercato_vivo(row)
        if b is None:
            if "bet" in visto and "morto" not in visto:
                b3 = {x["line"]: x for x in (row["payload"].get("ou") or [])}.get(3.5) \
                    if row is not None else None
                if b3 and b3.get("status") != "OPEN":
                    o = market._per_bet_id(visto["bet"])
                    visto["morto"] = {
                        "stato_mercato": b3.get("status"),
                        "stato": market._stato_betfair(o),
                        "lapsed": round(float(getattr(o, "size_lapsed", 0.0) or 0.0), 2),
                        "residuo": round(float(getattr(o, "size_remaining", 0.0) or 0.0), 2),
                        "vivi": [x["customer_order_ref"] for x in market.list_current_orders()],
                        "cleared": {x["customer_order_ref"]: x
                                    for x in market.list_cleared_orders()},
                    }
            return
        if "bet" in visto:
            return
        sel = next((x for x in b["selections"] if x.get("back")), None)
        if sel is None or str(b["market_id"]) not in strategia.mercati:
            return
        r = market.place_order_live(market_id=b["market_id"],
                                    selection_id=int(sel["selection_id"]),
                                    price=1000.0, size=2.0, event_id=CALCIO_EVENTO,
                                    side="back", customer_ref="cert-lapse",
                                    fill_or_kill=False)
        if r.ok:
            visto["bet"] = r.bet_id
            visto["vivo_prima"] = [x["customer_order_ref"]
                                   for x in market.list_current_orders()]

    esito, _r, _v = _replay("calcio", CALCIO_DIR, CALCIO_EVENTO, servizio=servizio)
    assert not esito.errori, esito.errori
    assert "bet" in visto, "l'ordine appoggiato non e' stato piazzato"
    assert "cert-lapse" in visto["vivo_prima"]
    assert "morto" in visto, "la registrazione non ha nessuna sospensione dopo il place"
    m = visto["morto"]
    assert m["stato_mercato"] != "OPEN"
    assert m["lapsed"] == 2.0 and m["residuo"] == 0.0
    assert m["stato"] == "EXECUTION_COMPLETE"
    assert "cert-lapse" not in m["vivi"], "un ordine lapsato non e' piu' vivo"
    riga = m["cleared"].get("cert-lapse")
    assert riga is not None and riga["size_lapsed"] == 2.0 and riga["size_matched"] == 0.0


def _ordine_vero(prezzo=1000.0, size=2.0, persistenza="LAPSE", abbinato=0.0):
    """Un ordine flumine VERO (non un finto): stessa classe, stessi campi."""
    from flumine import BaseStrategy
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    class _Strategia(BaseStrategy):
        """LA CLASSE VERA, non un finto: `Order.execution_complete` chiama
        `strategy.get_runner_context` (`flumine/order/trade.py:70`), e un doppio
        che non ce l'ha farebbe passare un test che in produzione romperebbe."""

        def check_market_book(self, market, market_book):  # pragma: no cover
            return False

        def process_market_book(self, market, market_book):  # pragma: no cover
            return None

    trade = Trade(market_id="1.1", selection_id=1, handicap=0.0,
                  strategy=_Strategia(market_filter={}))
    ordine = trade.create_order(
        side="BACK",
        order_type=LimitOrder(price=prezzo, size=size, persistence_type=persistenza))
    ordine.simulated.size_matched = abbinato
    if abbinato:
        ordine.simulated.average_price_matched = prezzo
        ordine.simulated.matched = [[0, prezzo, abbinato]]
    return ordine


class _Blotter(list):
    @property
    def live_orders(self):
        return list(self)


class _MercatoFinto:
    def __init__(self, ordini):
        self.market_id = "1.1"
        self.blotter = _Blotter(ordini)


class _MdFinta:
    def __init__(self, in_play):
        self.in_play = in_play


class _BookFinto2:
    def __init__(self, in_play):
        self.market_id = "1.1"
        self.market_definition = _MdFinta(in_play)
        self.inplay = in_play


def test_lapse_al_passaggio_in_gioco():
    """Betfair cancella gli ordini LAPSE non abbinati quando il mercato passa in
    gioco, e MISURATO sulle registrazioni quel passaggio avviene a mercato
    ancora OPEN: flumine, che lapsa solo alla sospensione, arriverebbe un tick
    tardi e farebbe abbinare ai prezzi del fischio un ordine gia' morto.

    `PERSIST` sopravvive, e la parte gia' abbinata non si tocca.
    """
    import flumine.config as fconf

    prima = fconf.simulated
    # `order.size_remaining` legge i numeri SIMULATI solo con la simulazione
    # accesa (`SimulatedOrder.__bool__`): senza, si misurerebbe il ramo live.
    fconf.simulated = True
    try:
        _corpo_lapse_al_fischio()
    finally:
        fconf.simulated = prima


def _corpo_lapse_al_fischio():
    lapse = _ordine_vero(persistenza="LAPSE")
    persist = _ordine_vero(persistenza="PERSIST")
    parziale = _ordine_vero(persistenza="LAPSE", size=10.0, abbinato=4.0)
    mercato = _MercatoFinto([lapse, persist, parziale])

    motore = B.MotoreReplay.__new__(B.MotoreReplay)
    motore._in_gioco = {}
    motore.lapse_al_fischio = 0

    # pre-match: nessuno muore
    assert motore._lapse_al_fischio(mercato, _BookFinto2(False)) == 0
    assert lapse.size_remaining == 2.0
    # il FISCHIO: muoiono i LAPSE non abbinati, sopravvive il PERSIST
    assert motore._lapse_al_fischio(mercato, _BookFinto2(True)) == 2
    assert lapse.simulated.size_lapsed == 2.0 and lapse.size_remaining == 0.0
    assert persist.simulated.size_lapsed == 0.0 and persist.size_remaining == 2.0
    # il parziale: resta la parte ABBINATA, lapsa solo il residuo
    assert parziale.simulated.size_matched == 4.0
    assert parziale.simulated.size_lapsed == 6.0 and parziale.size_remaining == 0.0
    # una seconda volta non uccide niente (il passaggio avviene una volta sola)
    assert motore._lapse_al_fischio(mercato, _BookFinto2(True)) == 0
    assert motore.lapse_al_fischio == 2


def test_il_lapse_al_fischio_e_agganciato_prima_del_middleware():
    """Non basta che la funzione esista: deve essere CHIAMATA, e prima del
    middleware che abbina.

    L'ordine delle due righe e' la cosa che vale soldi: se il lapse arrivasse
    dopo, l'ordine gia' morto su Betfair si abbinerebbe ai prezzi del fischio.
    Qui si guarda il sorgente perche' e' l'unico modo di provare l'ordine delle
    chiamate senza montare un'intera simulazione."""
    import inspect

    sorgente = inspect.getsource(B.MotoreReplay._a_flumine)
    righe = [l.strip() for l in sorgente.splitlines()]
    try:
        i_lapse = next(n for n, l in enumerate(righe) if "_lapse_al_fischio(" in l)
    except StopIteration:  # pragma: no cover
        raise AssertionError("`_a_flumine` non chiama piu' `_lapse_al_fischio`")
    i_mw = next(n for n, l in enumerate(righe) if "for middleware in" in l)
    i_market = next(n for n, l in enumerate(righe) if l == "market(market_book)")
    assert i_market < i_lapse < i_mw, (
        "il lapse deve stare DOPO l'aggiornamento del book e PRIMA del "
        f"middleware: market={i_market} lapse={i_lapse} middleware={i_mw}")


# ---------------------------------------------------------------------------
# `ht_ft_rows`: c'e' il metodo, non c'e' il dato — e si dichiara
# ---------------------------------------------------------------------------
def test_ht_ft_rows_ha_la_firma_e_il_tipo_del_vero():
    """Il referto del 16/09 diceva «metodi di database chiamati dal servizio e
    assenti dal banco: ['ht_ft_rows']»: un metodo mancante rispondeva `None`
    tramite `__getattr__`, e `None` in produzione significa «errore RPC», che e'
    un fatto diverso da «tabella vuota». Qui la firma e il tipo di ritorno si
    confrontano con quelli VERI di `Betfair/mike/db.py`."""
    import inspect

    from Betfair.mike import db as MIKE_DB

    vero = inspect.signature(MIKE_DB.ht_ft_rows)
    finto = inspect.signature(B.DbMemoria.ht_ft_rows)
    parametri_finto = [p for n, p in finto.parameters.items() if n != "self"]
    assert [p.name for p in parametri_finto] == [p.name for p in vero.parameters.values()], (
        f"firma diversa dal vero: vero={vero} banco={finto}")
    assert str(finto.return_annotation).replace("typing.", "") in (
        "List[Dict[str, Any]]", "list[dict[str, Any]]"), finto.return_annotation

    db = B.DbMemoria({"status": "running", "mode": "paper"})
    righe = db.ht_ft_rows(None)
    # il vero torna una LISTA (`[]` = tabella vuota). MAI None: `None` vuol dire
    # errore, e il chiamante (`mike/dossier.get_empirical`) li tratta diversi.
    assert isinstance(righe, list) and righe == []
    assert isinstance(db.ht_ft_rows(135), list)
    # e il limite si DICHIARA, non si tace
    assert [n for n, _c in db.senza_dato] == ["ht_ft_rows"]
    assert "get_omega_ht_ft" in db.senza_dato[0][1]
    assert "ht_ft_rows" not in db.mancanti


def test_ht_ft_rows_non_finisce_piu_fra_i_metodi_mancanti():
    """La lista `mancanti` deve restare la spia dei metodi che il banco NON ha:
    se ci finisse dentro anche uno che c'e', la spia smette di essere leggibile."""
    db = B.DbMemoria({})
    db.ht_ft_rows(7)
    db.un_metodo_che_non_esiste()
    assert db.mancanti == ["un_metodo_che_non_esiste"]


# ---------------------------------------------------------------------------
# LA SOSPENSIONE IN GIOCO UCCIDE L'ORDINE APPOGGIATO (16/09)
# ---------------------------------------------------------------------------
class _BookSospeso:
    """Un book con stato e in-play dichiarati, come li legge `_a_flumine`."""

    def __init__(self, stato, in_play=True):
        self.market_id = "1.1"
        self.status = stato
        self.market_definition = _MdFinta(in_play)
        self.inplay = in_play


def _motore_nudo():
    motore = B.MotoreReplay.__new__(B.MotoreReplay)
    motore._in_gioco = {}
    motore._stato_mercato = {}
    motore.lapse_al_fischio = 0
    motore.lapse_alla_sospensione = 0
    return motore


def test_lapse_alla_sospensione_in_gioco_come_betfair():
    """REGOLA BETFAIR: la persistenza LAPSE vuol dire che l'ordine non abbinato
    viene cancellato quando il mercato si SOSPENDE, per qualunque motivo — un
    gol, un rigore, un rosso — e non solo al passaggio in gioco. Il `keep`
    (PERSIST) sopravvive.

    Flumine da solo NON basta: `SimulatedOrder.__call__`
    (`simulation/simulatedorder.py:57-62`) lapsa a `SUSPENDED` solo se
    `market_book.version` e' cambiata. L'uscita appoggiata di Mike nasce DOPO il
    fischio, quindi `_lapse_al_fischio` non la vede mai: senza questa regola
    sopravviverebbe al gol e si abbinerebbe ai prezzi della riapertura."""
    import flumine.config as fconf

    prima = fconf.simulated
    fconf.simulated = True
    try:
        _corpo_lapse_alla_sospensione()
    finally:
        fconf.simulated = prima


def _corpo_lapse_alla_sospensione():
    lapse = _ordine_vero(persistenza="LAPSE")
    persist = _ordine_vero(persistenza="PERSIST")
    parziale = _ordine_vero(persistenza="LAPSE", size=10.0, abbinato=4.0)
    mercato = _MercatoFinto([lapse, persist, parziale])
    motore = _motore_nudo()

    # il mercato e' APERTO e in gioco: non muore nessuno
    assert motore._lapse_alla_sospensione(mercato, _BookSospeso("OPEN")) == 0
    assert lapse.size_remaining == 2.0
    # IL GOL: il mercato si sospende in gioco -> i LAPSE non abbinati muoiono
    assert motore._lapse_alla_sospensione(mercato, _BookSospeso("SUSPENDED")) == 2
    assert lapse.simulated.size_lapsed == 2.0 and lapse.size_remaining == 0.0
    assert persist.simulated.size_lapsed == 0.0 and persist.size_remaining == 2.0
    # il parziale: la parte ABBINATA resta, lapsa solo il residuo
    assert parziale.simulated.size_matched == 4.0
    assert parziale.simulated.size_lapsed == 6.0 and parziale.size_remaining == 0.0
    # finche' resta sospeso non si uccide una seconda volta
    assert motore._lapse_alla_sospensione(mercato, _BookSospeso("SUSPENDED")) == 0
    assert motore.lapse_alla_sospensione == 2


def test_la_sospensione_pre_match_resta_a_flumine():
    """PRE-MATCH la sospensione la gestisce gia' flumine al cambio di versione
    (VERIFICATO nel replay, 35833626): il banco non ci mette le mani, allarga
    solo il caso che flumine non copre."""
    import flumine.config as fconf

    prima = fconf.simulated
    fconf.simulated = True
    try:
        lapse = _ordine_vero(persistenza="LAPSE")
        mercato = _MercatoFinto([lapse])
        motore = _motore_nudo()
        assert motore._lapse_alla_sospensione(
            mercato, _BookSospeso("SUSPENDED", in_play=False)) == 0
        assert lapse.size_remaining == 2.0
    finally:
        fconf.simulated = prima


def test_la_sospensione_in_gioco_e_agganciata_prima_del_middleware():
    """Come per il fischio: se arrivasse DOPO il middleware, l'ordine gia' morto
    su Betfair farebbe in tempo ad abbinarsi sul book della sospensione."""
    import inspect

    sorgente = inspect.getsource(B.MotoreReplay._a_flumine)
    righe = [l.strip() for l in sorgente.splitlines()]
    i_susp = next(n for n, l in enumerate(righe) if "_lapse_alla_sospensione(" in l)
    i_mw = next(n for n, l in enumerate(righe) if "for middleware in" in l)
    i_market = next(n for n, l in enumerate(righe) if l == "market(market_book)")
    assert i_market < i_susp < i_mw, (
        f"market={i_market} sospensione={i_susp} middleware={i_mw}")


def test_lordine_scaduto_alla_sospensione_lo_racconta_come_betfair():
    """Non basta che muoia: il bot lo RILEGGE da `list_current_orders` /
    `list_cleared_orders`, ed e' li' che deve vederlo sparire — con
    `size_lapsed` valorizzato, non confuso con un annullo suo (`size_cancelled`).
    E' la distinzione che il 15/09 e' costata il loop dei green-up."""
    import flumine.config as fconf

    prima = fconf.simulated
    fconf.simulated = True
    try:
        lapse = _ordine_vero(persistenza="LAPSE")
        mercato = _MercatoFinto([lapse])
        motore = _motore_nudo()

        class _Strategia:
            mercati = {"1.1": mercato}

        banco = B.MercatoFlumine(_Strategia())
        # come dopo un piazzamento accettato: flumine porta l'ordine a
        # EXECUTABLE (`Order.executable`), ed e' quello lo stato in cui il bot
        # lo ritrova vivo fra gli ordini correnti
        lapse.executable()
        banco.ordini["ko_green-0-1"] = lapse
        assert [r["customer_order_ref"] for r in banco.list_current_orders()] \
            == ["ko_green-0-1"]

        motore._lapse_alla_sospensione(mercato, _BookSospeso("SUSPENDED"))
        lapse.execution_complete()

        assert banco.list_current_orders() == []
        riga = banco.list_cleared_orders()[0]
        assert riga["size_lapsed"] == 2.0 and riga["size_cancelled"] == 0.0
        assert riga["size_matched"] == 0.0
        assert riga["status"] == "EXECUTION_COMPLETE"
    finally:
        fconf.simulated = prima
