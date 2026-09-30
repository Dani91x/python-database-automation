"""IL P&L REALE DEL CONTO al regolamento di una partita LIVE (ordine dell'utente, 30/09).

"IL PNL DEVE ESSERE REALE CON TUTTO QUELLO CHE FANNO I BOT E IO MANUALMENTE!
ANCHE SE REGOLO LE LORO OPERAZIONI!!! IL TRADER DEVE SAPERE COSA STA GUARDANDO
E CHE DATI!!!"

Funzioni PURE (nessuna rete, nessun DB): il servizio legge, qui si compone.

1. FONTE UNICA DEL REALIZZATO IN LIVE = BETFAIR. Al regolamento il P&L di ogni
   riga e della partita viene dagli ordini REGOLATI del conto
   (``listClearedOrders``): ``profit`` per scommessa (LORDO) e ``commission``
   del MERCATO (esiste SOLO raggruppando per mercato: docs Betfair
   "ClearedOrderSummary" e "listClearedOrders - Roll-up Fields Available").
   Il netto di una scommessa = profit - quota della commissione del suo
   mercato, ripartita sui profit positivi con somma esatta al centesimo: e' la
   STESSA funzione con cui il runner scrive ``pnl_betfair``
   (``Betfair.stream.reconcile_worker.commissioni_per_ordine``), riusata qui
   perche' due formule per lo stesso numero sono il difetto 1 del catalogo.
   Il calcolo interno del motore (``engine.settle_legs_by_market``) resta per
   il paper e come CONFRONTO: se differisce, vince Betfair e lo si scrive.
2. GLI ORDINI DELL'UTENTE ENTRANO NEL CONTO DELLA PARTITA: ogni scommessa
   regolata sui mercati di Mike che NON e' di Mike (nessuna riga del bot con
   quel ``bet_id``, nessun riferimento del bot) e non e' di un altro bot e'
   dell'UTENTE (dal sito o dal terminale manuale dell'app).

LA RIGA "UTENTE" (contratto condiviso col verdetto in tempo reale della
chiusura dell'utente, ``service._sorveglia_posizione_di_conto``): una riga di
``mike_trades`` con

* ``signal_key``  = ``utente-<bet_id>`` (una per scommessa Betfair);
* ``role``        = ``utente`` (colonna senza CHECK);
* ``strategy``    = ``manual_close`` (l'unico valore del CHECK
  ``mike_trades_strategy_check`` che dice "operazione a mano": nessuna
  migrazione);
* ``origin``      = ``manual``; ``mode`` = ``live``; ``bet_id`` = quello Betfair;
* ``closes_trade_id`` = la riga d'APERTURA di Mike sullo stesso mercato (la
  posizione che l'utente ha regolato), cosi' storico, cicli e "posizioni
  chiuse" la contano DENTRO la posizione e non come un ciclo nuovo del bot;
* ``meta.fonte``  = ``utente``, ``meta.pnl_fonte`` = ``betfair``.

Chi la scrive prima del regolamento (il verdetto in tempo reale) la scrive con
la stessa ``signal_key``: il regolamento la AGGIORNA, non ne crea una seconda.
Una riga utente non e' MAI una gamba di Mike (``e_riga_utente``): la
riconciliazione e il regolamento del motore la saltano.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional

RUOLO_UTENTE = "utente"
STRATEGIA_UTENTE = "manual_close"
FONTE_UTENTE = "utente"
PREFISSO_UTENTE = "utente-"
#: il valore di ``meta.pnl_fonte`` quando il P&L della riga e' quello di Betfair
PNL_FONTE_BETFAIR = "betfair"
#: riferimenti d'ordine di ALTRI bot (non utente, non Mike): Omega, Safe, lo
#: scalper e lo sniper del calcio (``sc``/``sn`` + 8 cifre)
_PREFISSI_ALTRI_BOT = ("omega-", "safe-t")
_EPS = 0.005


def signal_key_utente(bet_id: Any) -> str:
    return f"{PREFISSO_UTENTE}{bet_id}"


def e_riga_utente(r: Dict[str, Any]) -> bool:
    """True se la riga di ``mike_trades`` e' un ordine dell'UTENTE (mai una
    gamba del bot)."""
    if str(r.get("role") or "") == RUOLO_UTENTE:
        return True
    if str((r.get("meta") or {}).get("fonte") or "") == FONTE_UTENTE:
        return True
    return str(r.get("signal_key") or "").startswith(PREFISSO_UTENTE)


def _f(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _abbinato(r: Dict[str, Any]) -> float:
    """L'abbinato della riga: ``size_matched`` se c'e'; per le righe vecchie
    (colonna assente) la size di una riga aperta o regolata."""
    m = _f(r.get("size_matched"))
    if m is not None:
        return m
    if str(r.get("status") or "") in ("open", "hedged", "won", "lost"):
        return _f(r.get("size")) or 0.0
    return 0.0


def _e_altro_bot(ref: str) -> bool:
    s = str(ref or "").strip()
    if s.startswith(_PREFISSI_ALTRI_BOT):
        return True
    # scalper/sniper calcio: ``sc12345678`` / ``sn12345678``
    return len(s) == 10 and s[:2] in ("sc", "sn") and s[2:].isdigit()


def _esito(lordo: float, outcome: Any) -> str:
    o = str(outcome or "").upper()
    if o == "WON":
        return "won"
    if o == "LOST":
        return "lost"
    if abs(lordo) < _EPS:
        return "void"
    return "won" if lordo > 0 else "lost"


def componi_regolato(righe: List[Dict[str, Any]], ordini: Iterable[Dict[str, Any]],
                     mercati: Iterable[Dict[str, Any]], market_ids: Iterable[str],
                     refs_mike: Optional[Iterable[str]] = None,
                     proprietari: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Il regolamento del CONTO sui mercati della partita.

    ``righe``: le righe ``mike_trades`` della partita; ``ordini``: le scommesse
    regolate del conto su quei mercati, nella forma di
    ``omega_market._riga_regolata`` (``bet_id, market_id, selection_id, side,
    size_settled, price, profit, bet_outcome, customer_order_ref``);
    ``mercati``: la lettura per MERCATO (``market_id, profit, commission``);
    ``refs_mike``: i riferimenti d'ordine del bot; ``proprietari``: bet_id ->
    bot proprietario letto dal DB (facoltativo: senza, si decide dal ref).

    Torna ``{"pronto": False, "motivo": ...}`` finche' Betfair non ha regolato
    TUTTO cio' che serve (ogni scommessa abbinata di Mike e la commissione di
    ogni mercato con un profit): nessun regolamento cieco. Altrimenti
    ``pronto: True`` con il netto per scommessa e le somme.
    """
    from Betfair.stream.reconcile_worker import commissioni_per_ordine

    ids = {str(m) for m in (market_ids or []) if m}
    refs = {str(x) for x in (refs_mike or []) if x}
    prop = {str(k): str(v) for k, v in (proprietari or {}).items()}
    # 1. le scommesse regolate, una per bet_id (Betfair puo' dare piu' record
    #    per la stessa scommessa: si sommano i profit, somma esatta)
    per_bet: Dict[str, Dict[str, Any]] = {}
    for o in ordini or []:
        bet = o.get("bet_id")
        mid = str(o.get("market_id") or "")
        if bet is None or (ids and mid not in ids):
            continue
        if o.get("profit") is None:
            # senza ``profit`` la scommessa NON e' regolata (in produzione non
            # sarebbe nemmeno fra i regolati): non conta, si aspetta
            continue
        bet = str(bet)
        acc = per_bet.setdefault(bet, {
            "bet_id": bet, "market_id": mid, "selection_id": o.get("selection_id"),
            "side": str(o.get("side") or "").lower(), "lordo": 0.0, "size": 0.0,
            "price": o.get("avg_price_matched") or o.get("price"),
            "bet_outcome": o.get("bet_outcome"),
            "customer_order_ref": o.get("customer_order_ref"),
            "settled_date": o.get("settled_date")})
        acc["lordo"] = round(acc["lordo"] + float(_f(o.get("profit")) or 0.0), 2)
        acc["size"] = round(acc["size"] + float(_f(o.get("size_settled")
                                                    if o.get("size_settled") is not None
                                                    else o.get("size_matched")) or 0.0), 2)
        if o.get("bet_outcome"):
            acc["bet_outcome"] = o.get("bet_outcome")
    gruppi = {str(g.get("market_id")): g for g in (mercati or []) if g.get("market_id")}
    # 2. di chi e' ogni scommessa
    righe_bot = [r for r in (righe or []) if not e_riga_utente(r)]
    riga_del_bet = {str(r.get("bet_id")): r for r in righe_bot if r.get("bet_id")}
    id_righe = {str(r.get("id")) for r in righe_bot if r.get("id") is not None}
    for bet, b in per_bet.items():
        ref = str(b.get("customer_order_ref") or "")
        if bet in riga_del_bet or (ref and ref in refs) or prop.get(bet) == "mike" \
                or (ref.startswith("mike-t") and ref[6:] in id_righe):
            b["chi"] = "mike"
        elif prop.get(bet) in ("omega", "safe", "scalper", "altri_bot", "bot_tennis") \
                or _e_altro_bot(ref):
            b["chi"] = "altro_bot"
        else:
            b["chi"] = "utente"
    # 3. PRONTO? ogni scommessa abbinata di Mike deve essere regolata
    mancano = []
    senza_bet_id = []
    for r in righe_bot:
        if str(r.get("mode") or "live") != "live" or _abbinato(r) <= 0:
            continue
        if not r.get("bet_id"):
            senza_bet_id.append(r.get("id"))
            continue
        if str(r["bet_id"]) not in per_bet:
            mancano.append(str(r["bet_id"]))
    if mancano:
        return {"pronto": False, "motivo": "scommesse di Mike non ancora regolate da Betfair",
                "mancano": mancano}
    # ...e la commissione di ogni mercato dove qualcuno ha un profit
    mercati_con_profit = sorted({b["market_id"] for b in per_bet.values()
                                 if abs(b["lordo"]) >= _EPS})
    senza_comm = [m for m in mercati_con_profit
                  if m not in gruppi or _f(gruppi[m].get("commission")) is None]
    if senza_comm:
        return {"pronto": False, "motivo": "commissione del mercato non ancora letta",
                "mercati": senza_comm}
    # 4. il netto per scommessa: la funzione del runner, sugli stessi numeri
    ns_ordini = [SimpleNamespace(bet_id=b["bet_id"], market_id=b["market_id"], profit=b["lordo"])
                 for b in per_bet.values() if abs(b["lordo"]) >= _EPS]
    ns_gruppi = [SimpleNamespace(market_id=m, commission=_f(g.get("commission")))
                 for m, g in gruppi.items()]
    comm = commissioni_per_ordine(ns_ordini, ns_gruppi)
    somme = {"mike": 0.0, "utente": 0.0, "altro_bot": 0.0}
    lordo_s = {"mike": 0.0, "utente": 0.0, "altro_bot": 0.0}
    comm_s = {"mike": 0.0, "utente": 0.0, "altro_bot": 0.0}
    for bet, b in per_bet.items():
        c = float(comm.get(bet) or 0.0) if abs(b["lordo"]) >= _EPS else 0.0
        b["commissione"] = round(c, 2)
        b["netto"] = round(b["lordo"] - c, 2)
        b["esito"] = _esito(b["lordo"], b.get("bet_outcome"))
        somme[b["chi"]] = round(somme[b["chi"]] + b["netto"], 2)
        lordo_s[b["chi"]] = round(lordo_s[b["chi"]] + b["lordo"], 2)
        comm_s[b["chi"]] = round(comm_s[b["chi"]] + b["commissione"], 2)
    return {
        "pronto": True,
        "per_bet": per_bet,
        "riga_del_bet": {bet: r.get("id") for bet, r in riga_del_bet.items()},
        "utente": sorted(b for b, v in per_bet.items() if v["chi"] == "utente"),
        "altri_bot": sorted(b for b, v in per_bet.items() if v["chi"] == "altro_bot"),
        "senza_bet_id": senza_bet_id,
        "netto_mike": somme["mike"],
        "netto_utente": somme["utente"],
        "netto_altri_bot": somme["altro_bot"],
        # il P&L DELLA PARTITA: Mike + utente (gli altri bot hanno il loro conto)
        "netto_conto": round(somme["mike"] + somme["utente"], 2),
        "lordo_mike": lordo_s["mike"], "lordo_utente": lordo_s["utente"],
        "commissione_mike": comm_s["mike"], "commissione_utente": comm_s["utente"],
    }


def ordine_non_di_mike(o: Dict[str, Any], righe: List[Dict[str, Any]],
                       refs_mike: Optional[Iterable[str]] = None,
                       strategy_ref: Optional[str] = None) -> bool:
    """True se un ordine del CONTO (corrente o regolato, grafia snake_case di
    ``omega_market``) non e' di Mike ne' di un altro bot noto: e' dell'UTENTE.
    Stessa regola di ``componi_regolato`` (bet_id delle righe di Mike, ref
    della gamba, ``mike-t<id>``, prefissi degli altri bot); in piu', se lo
    stream la porta, la ``customerStrategyRef`` (quella del terminale manuale
    dell'app, ``live``/``tennis``, e' dell'utente)."""
    bet = str(o.get("bet_id") or "")
    ref = str(o.get("customer_order_ref") or "")
    righe_bot = [r for r in (righe or []) if not e_riga_utente(r)]
    if bet and bet in {str(r.get("bet_id")) for r in righe_bot if r.get("bet_id")}:
        return False
    if ref and (ref in {str(x) for x in (refs_mike or [])}
                or (ref.startswith("mike-t")
                    and ref[6:] in {str(r.get("id")) for r in righe_bot})):
        return False
    if _e_altro_bot(ref):
        return False
    sref = str(strategy_ref or "").strip().lower()
    return sref in ("", "live", "tennis")


def riga_utente_in_corso(o: Dict[str, Any], *, ev: Dict[str, Any], righe: List[Dict[str, Any]],
                         commission_rate: float,
                         nomi: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """LA STESSA riga "utente", nata dal segnale IN TEMPO REALE (ordine corrente
    del conto abbinato: ``listCurrentOrders`` o il topic ``conto`` dello stream
    ordini, normalizzato con ``omega_market._riga_corrente``), PRIMA del
    regolamento: ``status`` 'open', P&L 0 e nessun numero di Betfair. Il
    regolamento la ritrova per ``signal_key`` e la AGGIORNA coi numeri regolati.
    ``None`` se l'ordine non ha abbinato (un ordine vivo e non abbinato non e'
    una posizione)."""
    abbinato = float(_f(o.get("size_matched")) or 0.0)
    if abbinato <= 0 or not o.get("bet_id"):
        return None
    prezzo = _f(o.get("avg_price_matched") or o.get("average_price_matched")
                or o.get("price_requested") or o.get("price"))
    b = {"bet_id": o.get("bet_id"), "market_id": o.get("market_id"),
         "selection_id": o.get("selection_id"), "side": o.get("side"), "price": prezzo,
         "size": abbinato, "lordo": 0.0, "commissione": 0.0, "netto": 0.0, "esito": "open",
         "customer_order_ref": o.get("customer_order_ref")}
    riga = riga_utente(b, ev=ev, righe=righe, commission_rate=commission_rate, nomi=nomi)
    riga.update({"status": "open", "pnl": 0.0, "settled_at": None, "pnl_betfair": None,
                 "commissione_betfair": None, "pnl_betfair_settled_at": None,
                 "size_remaining": float(_f(o.get("size_remaining")) or 0.0)})
    meta = dict(riga["meta"])
    meta.update({"phase": "open", "pnl_fonte": "in_corso",
                 "nota": "ordine dell'utente sul mercato di Mike (non piazzato dal bot): "
                         "entrera' nel P&L della partita al regolamento di Betfair"})
    for k in ("pnl_gross", "commission_paid"):
        meta.pop(k, None)
    riga["meta"] = meta
    return riga


_LINEA = {"OU35": ("OVER_UNDER_35", "3.5"), "OU45": ("OVER_UNDER_45", "4.5")}


def nomi_da_selezioni(selezioni: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """{selection_id: {market_type, selection_name}} dalle selezioni che Mike
    conserva nel contesto della partita (``"OU35|OVER": 1222345``): il nome e'
    quello dei runner Betfair ("Over 3.5 Goals"), anche per la selezione su cui
    Mike non ha righe (la chiusura dell'utente sta spesso sull'altra)."""
    out: Dict[str, Dict[str, Any]] = {}
    for chiave, sid in (selezioni or {}).items():
        mercato, _, sel = str(chiave).partition("|")
        if mercato not in _LINEA or sid is None:
            continue
        tipo, linea = _LINEA[mercato]
        out[str(sid)] = {"market_type": tipo,
                         "selection_name": f"{sel.capitalize()} {linea} Goals"}
    return out


def riga_utente(b: Dict[str, Any], *, ev: Dict[str, Any], righe: List[Dict[str, Any]],
                commission_rate: float, nomi: Optional[Dict[str, Dict[str, Any]]] = None,
                settled_at: Optional[str] = None) -> Dict[str, Any]:
    """La riga ``mike_trades`` di UNA scommessa dell'utente, con le chiavi e i
    tipi delle righe vere del bot (``service._trade_row``)."""
    mid = str(b.get("market_id") or "")
    stessa = [r for r in (righe or []) if not e_riga_utente(r) and not r.get("closes_trade_id")
              and r.get("id") is not None]
    sul_mercato = [r for r in stessa if str(r.get("market_id") or "") == mid]
    apertura = min(sul_mercato or stessa, key=lambda r: int(r["id"])) if (sul_mercato or stessa) else None
    modello = next((r for r in (righe or []) if str(r.get("market_id") or "") == mid
                    and str(r.get("selection_id") or "") == str(b.get("selection_id") or "")), None) \
        or next((r for r in (righe or []) if str(r.get("market_id") or "") == mid), None) or {}
    nome = (nomi or {}).get(str(b.get("selection_id")))
    if nome:
        modello = {**modello, **nome, "selection_id": b.get("selection_id")}
    prezzo = _f(b.get("price"))
    size = round(float(b.get("size") or 0.0), 2)
    lato = "lay" if str(b.get("side") or "").lower() == "lay" else "back"
    liability = round(size * (prezzo - 1.0), 2) if (lato == "lay" and prezzo) else size
    riga: Dict[str, Any] = {
        "event_id": str(ev.get("event_id")), "event_name": ev.get("event_name"), "sport": "calcio",
        "strategy": STRATEGIA_UTENTE, "role": RUOLO_UTENTE, "cycle_no": 0,
        "persistence": "LAPSE", "market_id": mid,
        "market_type": modello.get("market_type"),
        "selection_id": int(b["selection_id"]) if b.get("selection_id") is not None else None,
        "selection_name": modello.get("selection_name") if str(modello.get("selection_id") or "")
        == str(b.get("selection_id") or "") else None,
        "side": lato, "mode": "live", "price": prezzo, "size": size, "liability": liability,
        "commission": float(commission_rate), "minute_at_entry": None, "score_at_entry": None,
        "status": b.get("esito") or "void", "pnl": round(float(b.get("netto") or 0.0), 2),
        "bet_id": str(b.get("bet_id")), "settled_at": settled_at, "origin": "manual",
        "signal_key": signal_key_utente(b.get("bet_id")),
        "size_requested": size, "size_matched": size, "size_remaining": 0.0,
        "avg_price_matched": prezzo,
        "pnl_betfair": round(float(b.get("netto") or 0.0), 2),
        "commissione_betfair": round(float(b.get("commissione") or 0.0), 2),
        "pnl_betfair_settled_at": b.get("settled_date") or settled_at,
        "meta": {"fonte": FONTE_UTENTE, "pnl_fonte": PNL_FONTE_BETFAIR, "phase": "settled",
                 "leg_ref": signal_key_utente(b.get("bet_id")),
                 "pnl_gross": round(float(b.get("lordo") or 0.0), 2),
                 "commission_paid": round(float(b.get("commissione") or 0.0), 2),
                 "customer_order_ref": b.get("customer_order_ref") or None,
                 "nota": "ordine dell'utente sul mercato di Mike (non piazzato dal bot): "
                         "entra nel P&L della partita, numeri regolati da Betfair"},
    }
    if apertura is not None:
        riga["closes_trade_id"] = int(apertura["id"])
    return riga
