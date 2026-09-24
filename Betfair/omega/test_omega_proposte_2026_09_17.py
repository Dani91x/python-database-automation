"""LE USCITE DI OMEGA SONO PROPOSTE — 17/09/2026 (mandato V4, punto 22).

Ordine dell'utente, testuale:
    «OMEGA DEVE AVERE LA SCHEDA DOVE L'UTENTE APPROVA LE USCITE, SIA IN PROFIT
     CHE IN LOSS, come succede con Safe tennis. Nessuna chiusura automatica.»

Qui si prova il produttore Python (`omega_proposte.py`), il riconoscimento
dell'approvazione (`omega_service._uscita_del_bot_approvata`, reperto O-3) e i
quattro controlli della certificazione (G1-G4).

I FINTI PARLANO COME IL VERO. La coda e' `omega_manual_requests` con le sue
colonne (`id`, `kind`, `payload`, `status`, `result`, `created_at`,
`updated_at`, `processed_at`), il payload della RPC conserva il corpo e
AGGIUNGE `approved_at` (e' quello che fa `omega_request_approve`), le righe di
`omega_trades` hanno le colonne vere. Il 15/09 un finto in camelCase ha
certificato un bug e sono usciti 32 ordini reali; il 16/09 un finto che perdeva
`exit_kind` ha certificato la stessa cosa sulla Safe.

OGNI TEST PORTA LA SUA FALSIFICAZIONE: si rimette il difetto e il test deve
diventare rosso (i test che finiscono con ``_falsificazione``).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from Betfair.omega import certificazione as CERT
from Betfair.omega import omega_config as C
from Betfair.omega import omega_db as DB
from Betfair.omega import omega_proposte as PR
from Betfair.omega import omega_service as S
from Betfair.omega import omega_v3 as V3

ADESSO = datetime(2026, 9, 17, 20, 30, tzinfo=timezone.utc)
EVENTO = "35760084"
MKT = "1.259475532"
SEL = 13
RUNNER = "2 - 1"


def _params(**kw: Any) -> Dict[str, Any]:
    """I parametri RISOLTI, come li vede il servizio. `strategy_version=3`
    spegne il green-up automatico dalla whitelist: e' la condizione in cui il
    produttore gira."""
    p = C.resolve_params({"strategy_version": 3, **kw})
    return p


def _lay(**kw: Any) -> Dict[str, Any]:
    riga = {"id": 1, "event_id": EVENTO, "event_name": "Casa v Fuori",
            "market_id": MKT, "market_type": "CORRECT_SCORE", "selection_id": SEL,
            "runner_name": RUNNER, "side": "lay", "size": 5.26, "price": 48.0,
            "status": "open", "mode": "paper", "origin": "auto", "phase": "ft_cs",
            "bet_id": "100000000001", "liability": 247.22, "commission": 0.05,
            "closes_trade_id": None, "minute_at_entry": 73, "score_at_entry": "0-0",
            "meta": {}}
    riga.update(kw)
    return riga


def _payload_feed(*, minute: int = 74, sh: int = 0, sa: int = 0,
                  back: Optional[float] = 44.0, back_size: float = 88.75,
                  lay: Optional[float] = 60.0,
                  status: str = "OPEN") -> Dict[str, Any]:
    """La riga del FEED UNICO come la scrive lo scanner: blocco `cs` col
    `market_id` del trade e le selezioni con `back`/`back_size`/`lay`/`lay_size`.
    Sono le chiavi che legge `omega_service._greenup_prices_from_block`."""
    return {
        "event_id": EVENTO, "minute": minute, "score_home": sh, "score_away": sa,
        "red_home": 0, "red_away": 0, "inplay": True,
        "cs": {"market_id": MKT, "status": status, "inplay": True, "selections": [
            {"selection_id": SEL, "name": RUNNER, "runner_status": "ACTIVE",
             "back": back, "back_size": back_size, "lay": lay, "lay_size": 9.0},
            {"selection_id": SEL + 1, "name": "1 - 1", "runner_status": "ACTIVE",
             "back": 9.0, "back_size": 50.0, "lay": 9.4, "lay_size": 50.0},
            {"selection_id": SEL + 2, "name": "0 - 0", "runner_status": "ACTIVE",
             "back": 12.0, "back_size": 50.0, "lay": 12.5, "lay_size": 50.0},
        ]},
    }


class DbFinto:
    """Le firme sono quelle di `omega_db` e le colonne quelle vere. La coda e'
    UNA (`omega_manual_requests`): `pending_manual_requests` filtra 'pending',
    ed e' QUEL filtro a fare il cancelletto."""

    def __init__(self, trades: Optional[List[dict]] = None,
                 *, schema_pronto: bool = True) -> None:
        self.trades = [dict(t) for t in (trades or [])]
        self.richieste: List[dict] = []
        self.attivita: List[tuple] = []
        self.eventi: Dict[str, dict] = {}
        self.schema_pronto = bool(schema_pronto)
        self.scritture = 0
        self._rid = 0

    # --- trades
    def open_trades(self) -> List[dict]:
        return [t for t in self.trades if str(t.get("status")) == "open"]

    def list_trades(self, status: Optional[str] = None) -> List[dict]:
        return [t for t in self.trades
                if status is None or str(t.get("status")) == status]

    def trades_for_event(self, event_id: str, **_kw: Any) -> List[dict]:
        return [t for t in self.trades if str(t.get("event_id")) == str(event_id)]

    def get_trade(self, trade_id: int) -> Optional[dict]:
        return next((t for t in self.trades
                     if int(t.get("id") or 0) == int(trade_id)), None)

    def update_trade(self, trade_id: int, **campi: Any) -> None:
        self.scritture += 1
        riga = self.get_trade(trade_id)
        if riga is not None:
            riga.update(campi)

    # --- attivita'
    def log(self, kind: str, payload: Optional[dict] = None, **_kw: Any) -> None:
        self.attivita.append((str(kind), dict(payload or {})))

    def kinds(self) -> List[str]:
        return [k for k, _p in self.attivita]

    def payload_di(self, kind: str) -> Optional[dict]:
        return next((p for k, p in self.attivita if k == kind), None)

    # --- eventi
    def event_user_state(self, event_id: str) -> Optional[dict]:
        st = (self.eventi.get(str(event_id)) or {}).get("stato_utente")
        return dict(st) if isinstance(st, dict) else None

    def set_event_user_state(self, event_id: str, stato: Optional[dict]) -> bool:
        self.eventi.setdefault(str(event_id), {})["stato_utente"] = stato
        return True

    def user_closed_event_ids(self, since_iso: Optional[str] = None) -> set:
        return {e for e, r in self.eventi.items()
                if isinstance(r.get("stato_utente"), dict)
                and r["stato_utente"].get("chiuso_dall_utente")}

    def get_event(self, event_id: str) -> Optional[dict]:
        return self.eventi.get(str(event_id))

    def save_event_model(self, event_id: str, model: dict) -> bool:
        return True

    # --- LA CODA: una sola, filtrata su 'pending'
    def pending_manual_requests(self) -> List[dict]:
        return [dict(r) for r in self.richieste if str(r.get("status")) == "pending"]

    def set_manual_status(self, req_id: int, status: str,
                          result: Optional[dict] = None) -> None:
        for r in self.richieste:
            if int(r["id"]) == int(req_id):
                r["status"] = status
                if result is not None:
                    r["result"] = result
                return

    def fail_stale_processing(self, max_age_min: int = 10) -> None:
        return None

    # --- aggregati: le CHIAVI vere di `omega_engine.aggregates_from_rows`
    def aggregates(self, day_start: Any = None) -> dict:
        return {"realized_profit": 0.0, "realized_today": 0.0,
                "open_liability": 0.0, "locked_pnl_open": 0.0,
                "locked_pnl_open_today": 0.0, "reconciling_liability": 0.0,
                "matches_traded": 1, "matches_open": 1, "settled_count": 0,
                "total_count": 1, "matches_traded_today": 1, "events_today": 1}

    def aggregates_coppia(self, day_start: Any = None):
        uno = self.aggregates(day_start)
        return dict(uno), dict(uno)

    # --- LE PROPOSTE
    def proposta_di_chiusura_viva(self, trade_id: int) -> Optional[dict]:
        for r in self.richieste:
            if (str(r.get("status")) == "proposed"
                    and str((r.get("payload") or {}).get("trade_id")) == str(int(trade_id))):
                return dict(r)
        return None

    def scrivi_proposta_di_chiusura(self, trade_id: int,
                                    payload: Dict[str, Any]) -> Optional[int]:
        if not self.schema_pronto:
            # e' l'errore VERO di PostgREST quando il CHECK non conosce lo stato
            # nuovo: la migrazione non e' stata applicata
            raise RuntimeError(
                'new row for relation "omega_manual_requests" violates check '
                'constraint "omega_manual_requests_status_check"')
        self.scritture += 1
        corpo = {**payload, "trade_id": int(trade_id)}
        viva = self.proposta_di_chiusura_viva(trade_id)
        if viva is not None:
            for r in self.richieste:
                if int(r["id"]) == int(viva["id"]):
                    r["payload"] = corpo
                    r["updated_at"] = ADESSO.isoformat()
            return int(viva["id"])
        self._rid += 1
        self.richieste.append({
            "id": self._rid, "kind": "cashout", "status": "proposed",
            "payload": corpo, "result": None, "created_at": ADESSO.isoformat(),
            "updated_at": ADESSO.isoformat(), "processed_at": None})
        return self._rid

    def chiudi_proposta(self, trade_id: int, motivo: str) -> None:
        self.scritture += 1
        for r in self.richieste:
            if (str(r.get("status")) == "proposed"
                    and str((r.get("payload") or {}).get("trade_id")) == str(int(trade_id))):
                r["status"] = "rejected"
                r["result"] = {**(r.get("result") or {}), "decaduta": True,
                               "motivo": str(motivo)[:200]}

    # --- il gesto della Control Room: la RPC `omega_request_approve`
    def approva(self, req_id: int, quando: datetime) -> None:
        """'proposed' -> 'pending' col payload CONSERVATO piu' `approved_at`.
        E' esattamente cio' che fa la RPC (`payload || jsonb_build_object(...)`):
        rifarlo da zero butterebbe via `motivo_codice` — difetto 27."""
        for r in self.richieste:
            if int(r["id"]) == int(req_id):
                r["status"] = "pending"
                r["payload"] = {**(r.get("payload") or {}),
                                "approved_at": quando.strftime("%Y-%m-%dT%H:%M:%SZ")}


class MercatoFinto:
    """Solo cio' che il produttore usa: la freschezza dei prezzi del feed."""

    def __init__(self, *, fresco: bool = True) -> None:
        self.fresco = bool(fresco)
        self.letture_rest = 0

    def read_book(self, *a: Any, **kw: Any) -> None:     # pragma: no cover
        self.letture_rest += 1
        raise AssertionError("il produttore NON deve leggere il book via REST")


@pytest.fixture(autouse=True)
def _stato_pulito(monkeypatch: pytest.MonkeyPatch):
    S.svuota_le_cache()
    # la freschezza dei prezzi del feed la decide il mercato reale: nei test la
    # si dichiara, senza toccare le soglie di produzione
    monkeypatch.setattr(S, "_feed_prices_fresh", lambda market, eid: bool(
        getattr(market, "fresco", True)))
    yield
    S.svuota_le_cache()


def _gira(db: DbFinto, *, params: Optional[dict] = None,
          payload: Optional[dict] = None, now: datetime = ADESSO,
          market: Any = None) -> int:
    return PR.process_proposte_uscita(
        params=params or _params(), market=market or MercatoFinto(), db=db, now=now,
        feed=lambda _eid: payload if payload is not None else _payload_feed())


# ===========================================================================
# 1. IL CANCELLETTO: quando il produttore gira, e quando no
# ===========================================================================
def test_col_green_up_automatico_ACCESO_il_produttore_non_gira():
    """Sono due decisioni sulla stessa gamba: non possono convivere. In v2 con
    `greenup_mode='auto'` chiude il bot; la scheda non esiste."""
    params = C.resolve_params({"strategy_version": 2, "greenup_mode": "auto"})
    assert PR.proposte_attive(params) is False
    db = DbFinto([_lay()])
    assert _gira(db, params=params) == 0
    assert db.richieste == []


def test_con_v3_il_green_up_e_spento_dalla_whitelist_e_il_produttore_gira():
    params = _params()
    assert params["greenup_mode"] == "off" and params["greenup_enabled"] is False
    assert PR.proposte_attive(params) is True


def test_il_servizio_non_drena_mai_una_proposta():
    """IL PERNO DI TUTTO (G1): la coda e' UNA, e il servizio legge SOLO
    'pending'. Una riga 'proposed' resta ferma finche' non la firma una persona.

    Se un domani qualcuno allargasse quel filtro, il cancelletto sparirebbe in
    silenzio — ed e' il reperto O-1 al contrario."""
    db = DbFinto([_lay()])
    _gira(db)
    assert [r["status"] for r in db.richieste] == ["proposed"]
    assert db.pending_manual_requests() == []
    n = S.process_manual(market=MercatoFinto(), db=db, now=ADESSO)
    assert n == 0
    assert [r["status"] for r in db.richieste] == ["proposed"]


def test_il_servizio_non_drena_mai_una_proposta_falsificazione(
        monkeypatch: pytest.MonkeyPatch):
    """IL DIFETTO RIMESSO: la coda torna a dare anche le 'proposed'. Il servizio
    le drenerebbe, cioe' chiuderebbe senza firma."""
    db = DbFinto([_lay()])
    _gira(db)
    monkeypatch.setattr(
        DbFinto, "pending_manual_requests",
        lambda self: [dict(r) for r in self.richieste
                      if str(r.get("status")) in ("pending", "proposed")])
    assert len(db.pending_manual_requests()) == 1     # il cancelletto e' sparito
    # ...e il servizio la prende in carico: e' esattamente cio' che non deve
    # succedere. La seconda rete (il rifiuto senza firma) la prova il test
    # `test_una_proposta_senza_firma_non_si_esegue`.
    S.process_manual(market=MercatoFinto(), db=db, now=ADESSO)
    assert [r["status"] for r in db.richieste] != ["proposed"]


# ===========================================================================
# 2. LA PROPOSTA: i numeri che finiscono sotto gli occhi del trader
# ===========================================================================
def test_la_proposta_porta_TUTTI_i_numeri_della_decisione():
    db = DbFinto([_lay()])
    assert _gira(db) == 1
    assert len(db.richieste) == 1
    riga = db.richieste[0]
    assert riga["kind"] == "cashout" and riga["status"] == "proposed"
    p = riga["payload"]
    # i campi che la migrazione dichiara e che la scheda legge, uno per uno
    for campo in ("trade_id", "event_id", "market_id", "market_type", "selection_id",
                  "selection_name", "side", "entry_side", "entry_price", "size",
                  "price_at_decision", "size_available_at_decision", "motivo_codice",
                  "profitto_bloccabile", "back_price", "back_size", "ev_tenere",
                  "p_evento", "liability", "meglio_aspettare", "bloccabile_max_atteso",
                  "minute", "score", "mode", "decided_at", "proposed_at"):
        assert campo in p, f"campo mancante nel payload: {campo}"
    assert p["trade_id"] == 1 and p["side"] == "back" and p["entry_side"] == "lay"
    assert p["mode"] == "paper" and p["score"] == "0-0" and p["minute"] == 74
    assert p["liability"] == 247.22
    assert isinstance(p["p_evento"], float) and 0.0 <= p["p_evento"] <= 1.0
    assert p["motivo_codice"] in PR.MOTIVI_CHE_PROPONGONO
    # l'attivita' c'e', e dice i numeri
    att = db.payload_di("proposta_scritta")
    assert att and att["trade_id"] == 1 and att["request_id"] == 1
    # il marcatore sulla riga: senza, servirebbe una query per trade a ogni giro
    assert db.get_trade(1)["meta"][PR.PROPOSTA_KEY]["request_id"] == 1


def test_ogni_motivo_di_salto_e_DICHIARATO():
    """Una gamba che salta senza motivo scritto e' il buco che §14.2 vieta: se
    domani qualcuno aggiunge un ramo di uscita e non lo dichiara, questo test
    diventa rosso."""
    import re
    from pathlib import Path

    sorgente = Path(PR.__file__).read_text(encoding="utf-8")
    usati = set(re.findall(r"""_salta\(db, tr, ["']([a-z0-9_]+)["']""", sorgente))
    assert usati, "nessun motivo trovato: la regex non sta piu' guardando il codice"
    assert usati <= set(PR.MOTIVI_DI_SALTO), (
        f"motivi di salto NON dichiarati: {sorted(usati - set(PR.MOTIVI_DI_SALTO))}")


def test_il_produttore_NON_legge_il_book_via_REST():
    """Regola del feed unico: una proposta e' una domanda, non vale una chiamata
    Betfair per gamba e per giro. Senza prezzi freschi si TACE."""
    mercato = MercatoFinto(fresco=False)
    db = DbFinto([_lay()])
    assert _gira(db, market=mercato) == 0
    assert mercato.letture_rest == 0
    assert db.richieste == []
    assert "skip" in db.kinds()


def test_sostanza_invariata_nessuna_riscrittura():
    """§20 della Costituzione: il 13/09 il database e' andato giu' per budget di
    IO esaurito. Il PREZZO non e' sostanza — la pagina lo pesca vivo dal feed."""
    db = DbFinto([_lay()])
    _gira(db)
    prime = db.scritture
    aggiornato = db.richieste[0]["payload"]["proposed_at"]
    # stesso motivo, stessa size, stesso punteggio: nessuna scrittura
    for _ in range(3):
        _gira(db, payload=_payload_feed(back=45.0))
    assert db.scritture == prime, "riscritta una proposta che non e' cambiata"
    assert db.richieste[0]["payload"]["proposed_at"] == aggiornato


def test_la_proposta_resta_viva_marcata_non_valida_quando_la_condizione_non_regge_piu():
    """Una proposta viva su una condizione che non regge NON deve sembrare
    ancora valida sotto gli occhi di chi decide.

    24/09 — CONTRATTO CAMBIATO PER ORDINE DELL'UTENTE («la scheda deve
    segnalarmi se c'e' ancora o no: io decido se approvare o scartare»). Fino al
    23/09 questo test si chiamava ``test_la_proposta_decade_quando_la_condizione_
    non_regge_piu`` e pretendeva la DECADENZA ('rejected' + ``decaduta``). Ora la
    proposta resta VIVA ('proposed'), coi numeri di adesso, ``valutazione.valida
    = False`` e il motivo; il ``motivo_codice`` della scheda resta quello per cui
    era stata proposta.

    Qui il bot CAMBIA IDEA: la gamba proponeva perche' sforava il tetto di
    liability; l'utente ALZA il tetto dal pannello e quel motivo sparisce — con
    la quota di adesso tenere vale piu' che chiudere."""
    db = DbFinto([_lay()])
    assert _gira(db) == 1
    assert db.richieste[0]["payload"]["motivo_codice"] == "cap"
    deciso = db.richieste[0]["payload"]["decided_at"]
    largo = _params(v3_max_liability_per_leg=1000.0, v3_max_liability_per_match=1000.0)
    assert _gira(db, params=largo) == 0
    riga = db.richieste[0]
    assert riga["status"] == "proposed", "la scheda e' stata chiusa d'autorita'"
    assert "proposta_decaduta" not in db.kinds()
    assert db.kinds().count("proposta_non_piu_valida") == 1
    p = riga["payload"]
    assert p["valutazione"]["valida"] is False
    assert p["valutazione"]["motivo_codice"] not in PR.MOTIVI_CHE_PROPONGONO
    assert p["motivo_codice"] == "cap" and p["decided_at"] == deciso
    assert db.get_trade(1)["meta"][PR.PROPOSTA_KEY]["non_valida"] is True
    # write-on-change: stesso quadro, nessuna nuova scrittura ne' attivita'
    scritte = db.scritture
    assert _gira(db, params=largo) == 0
    assert db.scritture == scritte
    assert db.kinds().count("proposta_non_piu_valida") == 1
    # il tetto torna stretto: la proposta torna VALIDA, stessa riga, stesso istante
    assert _gira(db) == 1
    assert len(db.richieste) == 1 and db.richieste[0]["status"] == "proposed"
    p2 = db.richieste[0]["payload"]
    assert p2["valutazione"]["valida"] is True and p2["decided_at"] == deciso
    assert "non_valida" not in db.get_trade(1)["meta"][PR.PROPOSTA_KEY]


def test_una_controparte_che_sparisce_NON_uccide_la_proposta():
    """MISURATO SUL BANCO (35777617, 17/09): facendo decadere la proposta anche
    quando manca solo la CONTROPARTE, su una gamba sola sono nate 9 proposte e 8
    decadenze — e `decided_at` ripartiva ogni volta, cioe' la latenza della firma
    non voleva piu' dire niente. Il book che si assottiglia per un tick non e' un
    cambio di idea del bot: il green-up automatico, nello stesso caso, ASPETTA."""
    db = DbFinto([_lay()])
    assert _gira(db) == 1
    deciso = db.richieste[0]["payload"]["decided_at"]
    assert _gira(db, payload=_payload_feed(back_size=0.01)) == 0
    assert db.richieste[0]["status"] == "proposed"      # viva
    assert "proposta_decaduta" not in db.kinds()
    assert db.richieste[0]["payload"]["decided_at"] == deciso
    assert len(db.richieste) == 1


def test_dopo_un_IGNORA_si_ripropone_solo_a_situazione_cambiata():
    """Decisione dell'utente (Safe, 14/09): «se rifiuto, riproporre quando cambia
    qualcosa IN BENE O IN MALE». Non a tempo fisso, e non una volta sola."""
    db = DbFinto([_lay()])
    _gira(db)
    db.richieste[0]["status"] = "rejected"        # l'utente ha premuto IGNORA
    dopo = ADESSO + timedelta(seconds=PR._RICONTROLLO_PROPOSTA_S + 1)
    # 1) si fotografa cio' che ha scartato
    assert _gira(db, now=dopo) == 1
    assert len(db.richieste) == 1
    fotografia = db.get_trade(1)["meta"][PR.PROPOSTA_KEY]["rifiutata"]
    assert fotografia["score"] == "0-0"
    # 2) situazione IDENTICA: non si insiste
    ancora = dopo + timedelta(seconds=PR._RICONTROLLO_PROPOSTA_S + 1)
    assert _gira(db, now=ancora) == 1
    assert len(db.richieste) == 1
    # 3) il punteggio CAMBIA: si ripropone, e la pagina lo dice
    piu_tardi = ancora + timedelta(seconds=PR._RICONTROLLO_PROPOSTA_S + 1)
    _gira(db, now=piu_tardi, payload=_payload_feed(minute=80, sh=1))
    assert len(db.richieste) == 2
    assert db.richieste[1]["payload"]["riproposta_perche"] == "il punteggio e' cambiato"
    assert "proposta_riproposta" in db.kinds()


# ===========================================================================
# 3. IN PERDITA SI PROPONE (ordine dell'utente del 17/09)
# ===========================================================================
def test_in_perdita_il_bot_PROPONE_la_protezione():
    """La quota si e' DIMEZZATA contro di noi (lay 48 -> back 24): chiudere costa,
    ma con la cella a un passo tenere costa di piu'. Prima del 17/09 questo caso
    usciva da `bloccabile_non_positivo` e la Control Room non vedeva niente."""
    # gamba da 1 EUR di stake (liability 47): SOTTO i cap di V3, cosi' il motivo
    # non puo' essere `cap` e resta quello che questo test vuole misurare
    db = DbFinto([_lay(size=1.0, liability=47.0)])
    # 2-1 col punteggio a 2-0 all'89': un gol e la cella esce
    assert _gira(db, payload=_payload_feed(minute=89, sh=2, sa=0, back=24.0,
                                           back_size=200.0)) == 1
    p = db.richieste[0]["payload"]
    assert p["motivo_codice"] == "protezione"
    assert p["profitto_bloccabile"] < 0, "una protezione blocca una PERDITA"
    assert p["ev_tenere"] < p["profitto_bloccabile"], "tenere deve costare di piu'"
    # l'attivita' e' CRITICA: non e' un affare, e' una richiesta di ridurre il rischio
    assert db.payload_di("proposta_scritta")["critical"] is True


def test_in_perdita_il_bot_PROPONE_la_protezione_falsificazione():
    """IL DIFETTO RIMESSO: `proposta_uscita` torna a fermarsi su
    `bloccabile_non_positivo` appena il bloccabile e' <= 0. In perdita il bot
    non chiede piu' niente — che e' com'era fino al 17/09."""
    originale = V3.proposta_uscita

    def senza_protezione(posizione, **kw):
        kw.pop("cap_scattato", None)
        kw.pop("p_lose_max", None)
        pr = originale(posizione, **kw)
        if pr.motivo_codice == "protezione":
            return V3.PropostaUscita(
                False, "bloccabile_non_positivo", pr.profitto_bloccabile,
                pr.back_price, pr.back_size, pr.ev_tenere, pr.meglio_aspettare,
                pr.bloccabile_max_atteso, pr.minuto_del_massimo, pr.p_evento,
                "si tiene")
        return pr

    V3.proposta_uscita = senza_protezione
    try:
        db = DbFinto([_lay(size=1.0, liability=47.0)])
        scritte = _gira(db, payload=_payload_feed(minute=89, sh=2, sa=0, back=24.0,
                                                  back_size=200.0))
    finally:
        V3.proposta_uscita = originale
    assert scritte == 0 and db.richieste == []       # ROSSO: la perdita resta muta


def test_un_cap_scattato_propone_e_lo_dichiara():
    """I cap di V3 non sono zero: una gamba da 247 EUR di liability supera il
    tetto di GAMBA (120 EUR di default). Il trader deve saperlo — e il motivo
    dice che non gli si sta proponendo un affare."""
    params = _params()
    assert PR.cap_di_gamba_scattato(_lay(), params) == "v3_max_liability_per_leg"
    db = DbFinto([_lay()])
    _gira(db, params=params)
    p = db.richieste[0]["payload"]
    assert p["motivo_codice"] == "cap"
    assert p["cap_scattato"] == "v3_max_liability_per_leg"


def test_senza_cap_configurati_non_si_legge_NIENTE_dal_database():
    """§20: in produzione i cap sono a ZERO. Valutarli non deve costare una
    lettura degli aggregati a ogni giro."""
    class DbCheEsplode(DbFinto):
        def aggregates(self, day_start: Any = None) -> dict:   # pragma: no cover
            raise AssertionError("letto il database per un cap spento")

        def aggregates_coppia(self, day_start: Any = None):    # pragma: no cover
            raise AssertionError("letto il database per un cap spento")

    params = C.resolve_params({"strategy_version": 2, "greenup_mode": "off"})
    assert PR.cap_globale_scattato(db=DbCheEsplode(), params=params, now=ADESSO) is None


# ===========================================================================
# 4. FAIL-CLOSED: migrazione non applicata
# ===========================================================================
def test_senza_migrazione_nessuna_proposta_e_lo_dichiara():
    """Pattern O1: quello che non si e' potuto scrivere si DICE, forte
    (`schema_warn` = «MIGRAZIONE MANCANTE» in pagina), e non si chiude niente."""
    db = DbFinto([_lay()], schema_pronto=False)
    assert _gira(db) == 0
    assert db.richieste == []
    avviso = db.payload_di("schema_warn")
    assert avviso is not None
    assert avviso["critical"] is True
    assert "omega_proposte_coda_unica_2026-09-17.sql" in avviso["nota"]
    assert "proposta_scritta" not in db.kinds()


def test_senza_migrazione_nessuna_proposta_e_lo_dichiara_falsificazione():
    """IL DIFETTO RIMESSO: l'errore di schema viene scambiato per un guasto
    qualunque. La pagina non direbbe «manca la migrazione» e nessuno saprebbe
    perche' le proposte non arrivano mai."""
    originale = DB.pare_schema_mancante
    DB.pare_schema_mancante = lambda ex: False
    try:
        db = DbFinto([_lay()], schema_pronto=False)
        _gira(db)
    finally:
        DB.pare_schema_mancante = originale
    assert db.payload_di("schema_warn") is None      # ROSSO: l'avviso e' sparito
    assert db.payload_di("error") is not None


# ===========================================================================
# 5. O-3 — L'APPROVAZIONE NON E' UNA CHIUSURA DELL'UTENTE
# ===========================================================================
def test_una_proposta_firmata_si_riconosce():
    """Tre segni, ne basta uno. Un «Cash out» premuto sulla scheda non ne ha
    nessuno (e' un comando dell'utente, non un'uscita del bot)."""
    assert S._uscita_del_bot_approvata({"approved_at": "2026-09-17T20:00:00Z"}) is True
    assert S._uscita_del_bot_approvata({"motivo_codice": "protezione"}) is True
    assert S._uscita_del_bot_approvata({"approvata_da": "il trader"}) is True
    assert S._uscita_del_bot_approvata({"trade_id": 1, "fraction": 1.0}) is False
    assert S._uscita_del_bot_approvata({}) is False


def test_una_proposta_senza_firma_non_si_esegue():
    """La seconda rete (fail-closed): una richiesta coi numeri di una proposta ma
    senza `approved_at` non e' passata dalla RPC. Non si chiude niente."""
    db = DbFinto([_lay()])
    res = S._manual_cashout(market=MercatoFinto(), db=db,
                            payload={"trade_id": 1, "fraction": 1.0,
                                     "motivo_codice": "protezione"}, now=ADESSO)
    assert res["error"] == "proposta_non_firmata"
    assert db.payload_di("error")["reason"] == "proposta_non_firmata"
    assert db.get_trade(1)["status"] == "open"       # la posizione e' ancora li'


def test_l_exit_kind_di_una_proposta_firmata_viene_dal_vocabolario_condiviso():
    """`safe_strategy.exits.ui_exit_kind`, mai un codice inventato qui: una
    protezione e' una chiusura in perdita, e il badge non deve dire «green-up»."""
    kind, testo = S._exit_kind_della_proposta({"motivo_codice": "protezione"}, -1.4)
    assert kind == "loss" and "approvata da te" in testo
    kind, testo = S._exit_kind_della_proposta({"motivo_codice": "cap"}, -0.2)
    assert kind == "loss"
    kind, _ = S._exit_kind_della_proposta({"motivo_codice": "blocca_il_profitto"}, 1.2)
    assert kind == "greenup"


# ===========================================================================
# 6. I CONTROLLI DELLA CERTIFICAZIONE (G1-G4)
# ===========================================================================
def _proposta(**kw: Any) -> V3.PropostaUscita:
    campi = {"proponi": True, "motivo_codice": "blocca_il_profitto",
             "profitto_bloccabile": 0.94, "back_price": 31.0, "back_size": 2.1,
             "ev_tenere": 0.42, "meglio_aspettare": False,
             "bloccabile_max_atteso": 0.88, "minuto_del_massimo": 72.0,
             "p_evento": 0.0123, "testo": "-"}
    campi.update(kw)
    return V3.PropostaUscita(**campi)


def _momento(**kw: Any) -> CERT.Momento:
    base = {"tipo": "proposta", "now": ADESSO, "params": _params(),
            "event_id": EVENTO, "motore": "v3", "trade_id": 1,
            "stato_richiesta": "proposed"}
    base.update(kw)
    return CERT.Momento(**base)


def _violazioni(m: CERT.Momento) -> List[str]:
    return [v.codice for v in CERT.verifica(m)]


def test_G2_accetta_un_bloccabile_negativo_solo_col_motivo_giusto():
    assert "G2" not in _violazioni(_momento(
        proposta=_proposta(motivo_codice="protezione", profitto_bloccabile=-1.4,
                           ev_tenere=-29.0)))
    # `blocca_il_profitto` PROMETTE un guadagno: negativo e' una bugia in pagina
    assert "G2" in _violazioni(_momento(
        proposta=_proposta(profitto_bloccabile=-1.4)))


def test_G2_il_decided_at_non_si_rinfresca():
    m = _momento(proposta=_proposta(), decided_at="2026-09-17T20:00:00Z",
                 proposed_at="2026-09-17T20:05:00Z",
                 proposte_viste={"1": {"decided_at": "2026-09-17T19:00:00Z",
                                       "proposed_at": "2026-09-17T19:30:00Z"}})
    assert "G2" in _violazioni(m)


def test_G4_in_perdita_deve_esserci_una_proposta_e_deve_restare_tale():
    # (a) proposta in perdita col motivo giusto, ancora in attesa di firma: OK
    assert "G4" not in _violazioni(_momento(
        proposta=_proposta(motivo_codice="protezione", profitto_bloccabile=-1.4,
                           ev_tenere=-29.0)))
    # (b) in perdita col motivo del PROFITTO: il trader leggerebbe un guadagno
    assert "G4" in _violazioni(_momento(
        proposta=_proposta(profitto_bloccabile=-1.4, ev_tenere=-29.0)))
    # (c) in perdita, tenere costa di piu', e NESSUNA proposta: il buco del 16/09
    assert "G4" in _violazioni(_momento(
        proposta=_proposta(proponi=False, motivo_codice="bloccabile_non_positivo",
                           profitto_bloccabile=-1.4, ev_tenere=-29.0)))
    # (d) la proposta in perdita e' gia' 'pending' senza che nessuno l'abbia firmata
    assert "G4" in _violazioni(_momento(
        stato_richiesta="pending",
        proposta=_proposta(motivo_codice="protezione", profitto_bloccabile=-1.4,
                           ev_tenere=-29.0)))


def test_G3_una_firma_che_non_viene_eseguita_e_una_violazione():
    """E' il reperto O-1: la coda sbagliata. Il trader vede «fatto», la posizione
    resta aperta, e se ne accorge al settlement."""
    giro = {"tipo": "giro", "now": ADESSO, "params": _params(), "event_id": EVENTO,
            "motore": "v3"}
    ferma = CERT.Momento(**giro, approvazioni=[{
        "request_id": 7, "trade_id": 1, "event_id": EVENTO, "status": "pending",
        "giri_da_approvazione": CERT.GIRI_MASSIMI_PER_ESEGUIRE + 1,
        "eseguita": False, "evento_chiuso_dall_utente": False}])
    assert "G3" in _violazioni(ferma)
    eseguita = CERT.Momento(**giro, approvazioni=[{
        "request_id": 7, "trade_id": 1, "event_id": EVENTO, "status": "done",
        "giri_da_approvazione": 1, "eseguita": True,
        "evento_chiuso_dall_utente": False, "exit_kind": "loss"}])
    assert "G3" not in _violazioni(eseguita)


def test_G3_una_firma_non_rende_la_partita_chiusa_dall_utente():
    """Reperto O-3: quella chiusura l'ha DECISA il bot. Marcarla come chiusura
    dell'utente spegnerebbe il bot su una partita che sta gestendo lui (e' il
    difetto T14 x282 della Safe, 16/09)."""
    giro = {"tipo": "giro", "now": ADESSO, "params": _params(), "event_id": EVENTO,
            "motore": "v3"}
    assert "G3" in _violazioni(CERT.Momento(**giro, approvazioni=[{
        "request_id": 7, "trade_id": 1, "event_id": EVENTO, "status": "done",
        "giri_da_approvazione": 1, "eseguita": True,
        "evento_chiuso_dall_utente": True, "exit_kind": "loss"}]))
    # ...e nemmeno un cash out dell'utente: l'exit_kind lo direbbe
    assert "G3" in _violazioni(CERT.Momento(**giro, approvazioni=[{
        "request_id": 7, "trade_id": 1, "event_id": EVENTO, "status": "done",
        "giri_da_approvazione": 1, "eseguita": True,
        "evento_chiuso_dall_utente": False, "exit_kind": "manual"}]))


def test_G1_un_ordine_di_BACK_senza_firma_dichiarata_e_una_violazione():
    """«Nessuna chiusura parte da sola» guardato dal lato dell'ORDINE: un back
    sulla stessa selezione e' una chiusura, e nel giro dev'esserci l'attivita'
    con cui il servizio dichiara CHI ha deciso."""
    ordine = {"tipo": "ordine", "now": ADESSO, "params": _params(),
              "event_id": EVENTO, "motore": "v3",
              "richiesta": {"side": "back", "customer_ref": "omega-t2",
                            "market_id": MKT, "selection_id": SEL}}
    # (a) nessuna attivita': il bot ha chiuso da solo
    assert "G1" in _violazioni(CERT.Momento(**ordine, attivita=[]))
    # (b) una FIRMA dichiarata: e' l'utente
    firmata = [("uscita_approvata", {"closing_trade_id": 2, "firmata": True}, None)]
    assert "G1" not in _violazioni(CERT.Momento(**ordine, attivita=firmata))
    # (c) promossa a 'pending' SENZA passare dalla RPC: non e' una firma
    finta = [("uscita_approvata", {"closing_trade_id": 2, "firmata": False}, None)]
    assert "G1" in _violazioni(CERT.Momento(**ordine, attivita=finta))
    # (d) il bottone «Cash out» dell'utente resta una decisione sua
    manuale = [("cashout_manual", {"closing_trade_id": 2}, None)]
    assert "G1" not in _violazioni(CERT.Momento(**ordine, attivita=manuale))
