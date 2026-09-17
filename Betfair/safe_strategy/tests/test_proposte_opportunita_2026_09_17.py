# -*- coding: utf-8 -*-
"""LE OPPORTUNITA' DI MODELLO SONO PROPOSTE, NON ORDINI (17/09/2026).

Ordine dell'utente: «Le opportunita' modello (SIA CALCIO CHE TENNIS) devono
apparirmi come la card della chiusura, con tutte le informazioni e i due tasti:
PIAZZA parte l'ordine, RIFIUTA la scheda viene rifiutata.»

Cosa certifica questo file, sul codice di produzione:
  1. dal feed nasce una PROPOSTA ('proposed', kind='place', payload.opp_key) e
     NESSUNA riga a mercato, nemmeno con tutti gli ``auto_trade_*`` accesi;
  2. il RIFIUTO dell'utente e' persistito: finche' la chiave resta uguale la
     stessa opportunita' non torna (e l'attivita' lo dice una volta sola);
  3. la DECADENZA: opportunita' sparita dal feed o partita non piu' in gioco;
     e - altrettanto importante - una partita che NON e' stata valutata in quel
     ciclo non fa decadere niente;
  4. PIAZZA: la richiesta approvata passa da ``_request_place`` e produce una
     riga con la CONSAPEVOLEZZA dell'ordine (size_requested / size_matched /
     avg_price_matched / betfair_updated_at) e col `mode` della strategia
     'model', non con quello nudo del servizio.

I finti hanno le IDENTICHE chiavi del vero (``bot_db.proposte_opportunita``,
``scrivi_proposta_opportunita``, ``chiudi_proposta_opportunita``,
``marca_proposta_opportunita_annotata``; righe del feed unico come in
``test_due_motori_tennis_2026_09_17.py``).

ASCII-only nel codice, commenti in italiano.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import proposte_opportunita as PO

NOW = datetime(2026, 9, 17, 21, 0, tzinfo=timezone.utc)
EV = "36077210"


class DbFinto:
    def __init__(self) -> None:
        self.attivita: list[tuple[str, dict]] = []
        self.opps: list = []
        self.trades: list[dict] = []
        self.richieste: list[dict] = []
        self._id = 0

    # --- attivita' / feed ---
    def log(self, kind, payload):
        self.attivita.append((kind, dict(payload)))

    def kinds(self):
        return [k for k, _ in self.attivita]

    def upsert_opportunities(self, righe):
        self.opps.extend(righe)

    def open_trades(self):
        return []

    def aggregates(self, mode=None):
        return {}

    def scanner_status(self):
        return None

    def list_trades(self):
        return list(self.trades)

    def traded_signal_keys(self, mode=None):
        return set()

    def insert_trade(self, row):
        self._id += 1
        self.trades.append({**row, "id": self._id})
        return self._id

    def update_trade(self, trade_id, **fields):
        for t in self.trades:
            if t["id"] == trade_id:
                t.update(fields)

    # --- coda delle proposte: stesse chiavi del vero ---
    def proposte_opportunita(self, ore=24, limit=300):
        return [r for r in self.richieste
                if r.get("kind") == "place"
                and r.get("status") in ("proposed", "rejected")
                and (r.get("payload") or {}).get("opp_key")]

    def scrivi_proposta_opportunita(self, opp_key, payload, req_id=None):
        corpo = {**payload, "opp_key": str(opp_key)}
        if req_id is not None:
            for r in self.richieste:
                if r["id"] == int(req_id) and r["status"] == "proposed":
                    r["payload"] = corpo
            return int(req_id)
        self._id += 1
        self.richieste.append({"id": self._id, "kind": "place", "status": "proposed",
                               "payload": corpo, "result": None})
        return self._id

    def chiudi_proposta_opportunita(self, req_id, motivo):
        for r in self.richieste:
            if r["id"] == int(req_id) and r["status"] == "proposed":
                r["status"] = "rejected"
                r["result"] = {"decaduta": True, "motivo": str(motivo)[:200]}

    def marca_proposta_opportunita_annotata(self, req_id, result):
        for r in self.richieste:
            if r["id"] == int(req_id):
                r["result"] = {**(result or {}), "attivita_scritta": True}

    # --- comode per i test ---
    def vive(self):
        return [r for r in self.richieste if r["status"] == "proposed"]


class _TennisModelFinto:
    def __init__(self, opps):
        self._opps = list(opps)

    def evaluate(self, payload, now_ts):
        return list(self._opps)


class _ModuloTennisFinto:
    def __init__(self, modello):
        self._m = modello

    def TennisOpportunityModel(self, params):  # noqa: N802 - nome del vero
        return self._m


def _opp(selection_id=11, side="back", price=1.30):
    return {"market_type": "MATCH_ODDS", "market_id": "1.900",
            "selection_id": selection_id, "selection_name": "Leader", "side": side,
            "price": price, "size_available": 500.0, "confidence": 1.0, "edge": 0.2,
            "p_model": 0.77, "p_implied": 0.55, "ev": 0.15,
            "rationale": "modello sopra il mercato"}


def _riga_feed(event_id=EV, inplay=True):
    return {"event_id": event_id, "sport": "tennis", "updated_at": NOW.isoformat(),
            "payload": {"event_name": "Pieczonka v Trungelliti", "inplay": inplay,
                        "odds": {"p1": {"selection_id": 11, "back": 1.30, "lay": 1.32,
                                        "back_size": 500.0, "lay_size": 500.0},
                                 "p2": {"selection_id": 22, "back": 4.00, "lay": 4.40,
                                        "back_size": 200.0, "lay_size": 200.0}},
                        "sets": {"p1": 1, "p2": 0}, "games": {"p1": 4, "p2": 2}}}


def _ciclo(db, opps, rows=None, mode="paper", params=None):
    """``process_opportunities`` vero, con il modello tennis finto."""
    righe = rows if rows is not None else [_riga_feed()]
    return S.process_opportunities(
        db=db, market=None, rows=righe,
        params={"opps_interval_s": 0.0, "risk": {"model_stake": 5.0},
                **(params or {})},
        model=None, opp_mod=None, mode=mode, now=NOW,
        state={"last_ts": 0.0, "hashes": {}},
        rows_by_event={r["event_id"]: r for r in righe},
        auto_trade=True,
        auto_trade_kinds={"model": True, "tennis": True, "combo": True},
        extra={"anomaly": None, "combos": None,
               "tennis": _ModuloTennisFinto(_TennisModelFinto(opps))},
        scanner_ts=NOW.timestamp(), scanner_ts_known=True)


# ===========================================================================
# 1. LA PROPOSTA NASCE, L'ORDINE NO
# ===========================================================================
def test_dal_feed_nasce_una_proposta_e_nessun_ordine(monkeypatch):
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("_execute non deve essere chiamata: le opportunita' si "
                       "piazzano SOLO dalla scheda")))
    db = DbFinto()
    out = _ciclo(db, [_opp()])
    assert out["traded"] == 0 and out["proposte"] == 1
    assert db.trades == []
    riga = db.vive()[0]
    assert riga["kind"] == "place" and riga["status"] == "proposed"
    c = riga["payload"]
    # il COMANDO che partira' (stesse chiavi che ``_request_place`` legge)
    for k in ("event_id", "market_id", "market_type", "selection_id", "side",
              "price", "size", "mode", "strategy", "kind", "opp_key"):
        assert k in c, f"manca {k} nel payload della proposta"
    # la FOTOGRAFIA su cui il bot ha deciso
    for k in ("p_model", "p_implied", "edge", "ev", "confidence", "rationale",
              "size_available", "price_at_decision", "decided_at", "proposed_at"):
        assert k in c, f"manca {k} nel payload della proposta"
    assert c["opp_key"] == PO.opp_key(EV, "tennis", "MATCH_ODDS", 11, "back")
    assert c["score"] == "set 1-0 · game 4-2"


def test_il_codice_non_puo_piu_piazzare_una_opportunita_da_solo():
    """ISPEZIONE: la funzione che tratta le opportunita' di modello non chiama
    piu' ne' ``insert_trade`` ne' ``_execute``. E' la prova strutturale che il
    cancelletto non si puo' aggirare per distrazione."""
    src = inspect.getsource(S._proponi_opps)
    corpo = src.split('"""', 2)[-1]        # senza la docstring, che li NOMINA
    assert "insert_trade" not in corpo and "_execute" not in corpo
    assert not hasattr(S, "_auto_trade_opps"), \
        "la vecchia strada automatica e' ancora li': andava sostituita, non affiancata"


def test_write_on_change_la_proposta_viva_non_si_riscrive_se_non_cambia():
    db = DbFinto()
    _ciclo(db, [_opp()])
    prima = dict(db.vive()[0]["payload"])
    out = _ciclo(db, [_opp()])
    assert out["proposte"] == 0, "ha creato una seconda proposta per la stessa chiave"
    assert len(db.vive()) == 1
    assert db.vive()[0]["payload"] == prima
    # cambia il PREZZO: la scheda deve aggiornarsi
    out = _ciclo(db, [_opp(price=1.42)])
    assert out["proposte"] == 0 and len(db.vive()) == 1
    assert db.vive()[0]["payload"]["price"] == 1.42
    # `decided_at` NON si rinfresca: e' l'istante della decisione
    assert db.vive()[0]["payload"]["decided_at"] == prima["decided_at"]


# ===========================================================================
# 2. IL RIFIUTO E' PERSISTITO
# ===========================================================================
def test_rifiuto_persistito_la_stessa_chiave_non_torna():
    db = DbFinto()
    _ciclo(db, [_opp()])
    riga = db.vive()[0]
    # e' quello che fa la RPC ``safe_request_ignore`` quando l'utente preme RIFIUTA
    riga["status"] = "rejected"
    riga["result"] = {"ignorata_dall_utente": True, "motivo": "non mi convince"}

    out = _ciclo(db, [_opp()])
    assert out["proposte"] == 0, "l'opportunita' rifiutata e' tornata su: NON deve"
    assert db.vive() == []
    # l'attivita' del rifiuto la scrive il servizio, UNA sola volta
    assert db.kinds().count("opportunita_rifiutata") == 1
    assert db.richieste[0]["result"]["attivita_scritta"] is True
    _ciclo(db, [_opp()])
    assert db.kinds().count("opportunita_rifiutata") == 1


def test_una_chiave_diversa_dopo_il_rifiuto_torna_a_proporsi():
    """Il rifiuto vale per QUELLA cosa: un altro lato o un'altra selezione e'
    un'altra decisione, e deve poter arrivare."""
    db = DbFinto()
    _ciclo(db, [_opp()])
    riga = db.vive()[0]
    riga["status"] = "rejected"
    riga["result"] = {"ignorata_dall_utente": True, "motivo": "no"}
    out = _ciclo(db, [_opp(side="lay")])
    assert out["proposte"] == 1
    assert db.vive()[0]["payload"]["side"] == "lay"


# ===========================================================================
# 3. DECADENZA
# ===========================================================================
def test_decade_se_l_opportunita_sparisce_dal_feed():
    db = DbFinto()
    _ciclo(db, [_opp()])
    assert len(db.vive()) == 1
    _ciclo(db, [])          # partita ancora in gioco, opportunita' non piu' emessa
    assert db.vive() == []
    assert "opportunita_decaduta" in db.kinds()
    motivo = [p for k, p in db.attivita if k == "opportunita_decaduta"][0]
    assert motivo["motivo"] == "opportunita' sparita dal feed"
    assert motivo["mode"] == "paper"


def test_decade_se_la_partita_non_e_piu_in_gioco():
    db = DbFinto()
    _ciclo(db, [_opp()])
    chiave = db.vive()[0]["payload"]["opp_key"]
    _ciclo(db, [_opp()], rows=[_riga_feed("altra-partita")])
    assert chiave not in [r["payload"]["opp_key"] for r in db.vive()]
    motivo = [p for k, p in db.attivita if k == "opportunita_decaduta"][0]
    assert motivo["motivo"] == "partita non piu' in gioco"


def test_una_partita_non_valutata_non_fa_decadere_niente():
    """La partita c'e' ma in questo ciclo non e' stata valutata (quote assenti):
    non sapere non e' un motivo per togliere una scheda dagli occhi di chi
    deve decidere."""
    db = DbFinto()
    _ciclo(db, [_opp()])
    senza_quote = _riga_feed()
    senza_quote["payload"] = {**senza_quote["payload"], "odds": {}}
    _ciclo(db, [_opp()], rows=[senza_quote])
    assert len(db.vive()) == 1, "la proposta e' decaduta senza che si sapesse niente"


def test_feed_vuoto_non_tocca_le_proposte():
    db = DbFinto()
    _ciclo(db, [_opp()])
    _ciclo(db, [_opp()], rows=[])
    assert len(db.vive()) == 1


def test_senza_accesso_alla_coda_non_si_propone_e_non_si_piazza(monkeypatch):
    """FAIL-CLOSED: se non si riesce a leggere cosa l'utente ha gia' rifiutato,
    non si propone niente (e tanto meno si piazza)."""
    monkeypatch.setattr(S, "_execute", lambda **kw: (_ for _ in ()).throw(
        AssertionError("nessun ordine puo' partire da qui")))
    db = DbFinto()

    def rotta(*_a, **_k):
        raise RuntimeError("DB muto")

    db.proposte_opportunita = rotta  # type: ignore[assignment]
    out = _ciclo(db, [_opp()])
    assert out["proposte"] == 0 and db.richieste == [] and db.trades == []


# ===========================================================================
# 4. PIAZZA: la richiesta approvata diventa una riga CONSAPEVOLE
# ===========================================================================
class _Esito:
    def __init__(self, status="open", price=1.30, size=5.0, fill_note=None):
        self.status, self.price, self.size, self.fill_note = status, price, size, fill_note


def test_piazza_esegue_la_richiesta_con_la_consapevolezza_dell_ordine(monkeypatch):
    db = DbFinto()
    _ciclo(db, [_opp()])
    corpo = dict(db.vive()[0]["payload"])

    visto = {}

    def esecuzione(**kw):
        # ``_execute`` e' il punto unico che scrive la consapevolezza: qui si
        # verifica che la riga arrivi la' con i campi giusti, e si simula cio'
        # che il vero scrive sulla riga.
        visto["row"] = kw["row"]
        db.update_trade(kw["trade_id"], size_requested=kw["row"]["size"],
                        size_matched=5.0, avg_price_matched=1.30,
                        betfair_updated_at=NOW.isoformat())
        return _Esito()

    monkeypatch.setattr(S, "_execute", esecuzione)
    monkeypatch.setattr(S, "prices_for", lambda **kw: {"back_size": 500.0,
                                                       "lay_size": 500.0})
    monkeypatch.setattr(S, "_scanner_ts", lambda *_a, **_k: NOW.timestamp())
    monkeypatch.setattr(S, "build_risk_ctx", lambda *_a, **_k: {"unavailable": False})
    monkeypatch.setattr(S, "_risk_gate", lambda *_a, **_k: None)
    monkeypatch.setattr(S, "_risk_commit", lambda *_a, **_k: None)

    out = S._request_place(db=db, market=None,
                           rows_by_event={EV: _riga_feed()},
                           payload=corpo,
                           params={"commission_pct": 5.0},
                           now=NOW, control_mode="paper")
    assert out.get("ok") is True, out
    riga = db.trades[0]
    assert riga["strategy"] == "model" and riga["meta"]["kind"] == "tennis"
    assert riga["mode"] == "paper" and riga["origin"] == "manual"
    assert riga["meta"]["opp_key"] == corpo["opp_key"]
    assert riga["meta"]["da_proposta"] is True
    # i numeri del modello restano sulla riga (P(perdita) d'ingresso compresa)
    assert riga["meta"]["p_model"] == 0.77 and riga["meta"]["p_lose_entry"] == 0.23
    # CONSAPEVOLEZZA: chiesto, abbinato, prezzo medio, istante di Betfair
    assert riga["size_requested"] == 5.0 and riga["size_matched"] == 5.0
    assert riga["avg_price_matched"] == 1.30 and riga["betfair_updated_at"]
    att = [p for k, p in db.attivita if k == "opportunita_piazzata"]
    assert att and att[0]["mode"] == "paper" and att[0]["size_requested"] == 5.0


def test_servizio_live_e_modello_paper_la_proposta_paper_si_piazza(monkeypatch):
    """La proposta di un'opportunita' ha come autorita'
    ``modalita_di_strategia('model', control.mode, params)``, non ``control.mode``
    nudo: col servizio in LIVE e il modello in paper il tasto PIAZZA deve
    funzionare, in PAPER. Senza questa regola sarebbe sempre rifiutato."""
    monkeypatch.setattr(S, "_execute", lambda **kw: _Esito())
    monkeypatch.setattr(S, "prices_for", lambda **kw: {"back_size": 500.0})
    monkeypatch.setattr(S, "_scanner_ts", lambda *_a, **_k: NOW.timestamp())
    monkeypatch.setattr(S, "build_risk_ctx", lambda *_a, **_k: {"unavailable": False})
    monkeypatch.setattr(S, "_risk_gate", lambda *_a, **_k: None)
    monkeypatch.setattr(S, "_risk_commit", lambda *_a, **_k: None)
    db = DbFinto()
    _ciclo(db, [_opp()], mode="live")          # strategy_modes assente -> paper
    corpo = dict(db.vive()[0]["payload"])
    assert corpo["mode"] == "paper"
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="live")
    assert out.get("ok") is True, out
    assert db.trades[0]["mode"] == "paper"


def test_una_proposta_che_dice_live_col_modello_in_paper_e_rifiutata(monkeypatch):
    """La direzione dell'errore resta quella di sempre: i soldi veri si
    raggiungono solo scrivendolo. Un payload che asserisce 'live' mentre
    ``strategy_modes.model`` non lo dice viene RIFIUTATO, non degradato in
    silenzio."""
    monkeypatch.setattr(S, "_execute", lambda **kw: _Esito())
    monkeypatch.setattr(S, "_scanner_ts", lambda *_a, **_k: NOW.timestamp())
    db = DbFinto()
    _ciclo(db, [_opp()], mode="live")
    corpo = {**db.vive()[0]["payload"], "mode": "live"}
    out = S._request_place(db=db, market=None, rows_by_event={EV: _riga_feed()},
                           payload=corpo, params={"commission_pct": 5.0},
                           now=NOW, control_mode="live")
    assert "rejected" in out and db.trades == []


# ===========================================================================
# FALSIFICAZIONE (i test sopra sanno diventare rossi)
# ===========================================================================
def test_falsificazione_una_chiave_instabile_farebbe_tornare_su_i_rifiuti(monkeypatch):
    """Se la chiave della proposta includesse il PREZZO, un rifiuto durerebbe
    un tick: al movimento successivo la scheda tornerebbe su da sola. Qui si
    simula quella chiave sbagliata e si verifica che il rifiuto NON tiene —
    la prova che il test del rifiuto non e' cieco."""
    db = DbFinto()
    _ciclo(db, [_opp()])
    riga = db.vive()[0]
    riga["status"] = "rejected"
    riga["result"] = {"ignorata_dall_utente": True, "motivo": "no"}

    vera = PO.corpo_proposta

    def corpo_con_chiave_instabile(**kw):
        c = vera(**kw)
        c["opp_key"] = f"{c['opp_key']}:{c['price']}"   # il difetto
        return c

    monkeypatch.setattr(PO, "corpo_proposta", corpo_con_chiave_instabile)
    out = _ciclo(db, [_opp(price=1.42)])
    assert out["proposte"] == 1, ("con la chiave instabile il rifiuto non tiene: "
                                  "e' esattamente cio' che il test sopra impedisce")
