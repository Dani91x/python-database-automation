"""Convertitore PURO: registrazione raw tennis -> righe delle tabelle del Replay Tennis.

Ingresso (layout del recorder tennis, ``tennis_live/tennis_recorder.py``):
  * ``<event>.raw.jsonl``   messaggi ``mcm`` NATIVI dello Stream API Betfair
    (immagine + delta, size in GBP: "Market subscriptions are always in
    underlying exchange currency - GBP", vedi ``Betfair/stream/valuta.py``);
  * ``<event>.score.jsonl`` righe ``{"t": epoch_locale, "score": <IPS raw>}``,
    una per cambio di punteggio (orologio del POLL, non del mercato).

NESSUN PARSER NOSTRO DELLO STREAM: le righe raw entrano in
``betfairlightweight.StreamListener.on_data`` (lo stesso percorso di
``HistoricalStream._read_loop``, ``betfairlightweight/streaming/betfairstream.py``)
e la cache di betfairlightweight applica immagini e delta ("0 vol is remove",
``img`` = sostituisci). Dal ``MarketBook`` ricostruito il record compatto lo
produce ``recorder.serialize_book`` (lo STESSO del calcio) e la curazione e'
``curator.curate_records`` (la STESSA regola del calcio: primo snapshot, cambio
dei best, cadenza minima). Il punteggio passa da ``parse_tennis_scores`` e
``tennis_score_state``/``point_event`` del runner tennis (gli stessi della UI live).

Cosa il raw NON porta e da dove arriva (dichiarato, mai inventato):
  * NOMI dei runner: lo stream ha solo ``id`` e ``sortPriority``. Ordine delle
    fonti: nomi dati dal chiamante (catalogo del runner, ``_names.json``, catalogo
    nel DB) -> ``name`` della marketDefinition (presente nei file storici Betfair)
    -> per il MATCH_ODDS i nomi IPS per ``sortPriority`` (p1 = home =
    sortPriority 1, la stessa convenzione di ``TennisMatchStats``/
    ``tennis_score_state``) -> ``#id``. 08/10 (cantiere 14): ogni selezione porta
    ``name_source`` (``catalogo``/``marketdef``/``ips``/``id``) e l'evento
    ``diagnostica["nomi_fonte"]`` (chi ha dato i nomi dei due giocatori): il nome
    IPS e' TRONCATO (caso 35790089, «Marcelo Tomas Barrios V») e la pagina lo dice.
  * VALUTA: le size restano GBP (nessun marcatore ``valuta``): il frontend le
    converte alla fonte con ``CAMBIO_RIPIEGO_GBP_EUR``, come per il calcio.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from betfairlightweight import StreamListener

from ..config_stream import LADDER_DEPTH, UPLOAD_CADENCE_SEC
from ..curator import curate_records
from ..recorder import serialize_book
from ..tennis_scalper.tennis_score import TennisScore, parse_tennis_scores

logger = logging.getLogger(__name__)

#: nome leggibile per i tipi di mercato tennis noti (gli altri: tipo leggibile)
NOMI_MERCATO: Dict[str, str] = {
    "MATCH_ODDS": "Match Odds",
    "SET_BETTING": "Set Betting",
    "SET_WINNER": "Set Winner",
    "NUMBER_OF_SETS": "Numero di set",
    "TOTAL_GAMES": "Totale game",
    "GAME_HANDICAP": "Handicap game",
    "SET_HANDICAP": "Handicap set",
    "TIE_BREAK_IN_MATCH": "Tie-break nella partita",
}

#: pausa senza messaggi oltre la quale la registrazione ha un BUCO (diagnostica)
SOGLIA_BUCO_MS = 60_000

_STATI_FINITI = ("finished", "complete", "completed", "ended", "closed")

#: fonte di un nome -> rango (08/10, cantiere 14): una fonte migliore SOSTITUISCE una
#: peggiore al reimport, mai il contrario. ``catalogo`` = listMarketCatalogue (runner
#: tennis, ``_names.json``, tabelle tennis nel DB); ``marketdef``/``evento`` = ``name``
#: della marketDefinition o ``eventName`` "A v B" (file storici Betfair); ``ips`` = nome
#: del punteggio IPS (TRONCATO); ``id`` = segnaposto ``#id``.
RANGO_NOME_FONTE: Dict[str, int] = {"catalogo": 3, "marketdef": 2, "evento": 2, "ips": 1, "id": 0}
#: rango di un nome gia' nel DB senza fonte dichiarata (righe di prima del cantiere 14):
#: trattato come IPS (il piu' basso fra i nomi veri), cosi' ogni fonte migliore lo supera
RANGO_NOME_SENZA_FONTE = 1

#: chiave riservata di ``_names.json`` per i nomi di TUTTI i mercati registrati
#: (``{event_id: {market_id: {selection_id: nome}}}``); la scrive il registratore tennis
CHIAVE_MERCATI_NOMI = "_mercati"


# ---------------------------------------------------------------------------
# utilita'
# ---------------------------------------------------------------------------
def ms_a_iso(ms: Optional[float]) -> Optional[str]:
    if ms is None:
        return None
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc).isoformat()


def nome_mercato(market_type: Optional[str]) -> str:
    t = (market_type or "").upper()
    if t in NOMI_MERCATO:
        return NOMI_MERCATO[t]
    return t.replace("_", " ").title() if t else "Mercato"


def _righe(fonte: Any) -> Iterator[str]:
    """Righe di testo da un percorso o da un iterabile di stringhe."""
    if isinstance(fonte, (str, os.PathLike)):
        with open(fonte, "r", encoding="utf-8") as fh:
            for riga in fh:
                yield riga
    else:
        for riga in fonte:
            yield riga


# ---------------------------------------------------------------------------
# 1) mercati: raw nativo -> MarketBook (betfairlightweight) -> record compatti
# ---------------------------------------------------------------------------
@dataclass
class StatoMercato:
    """Cio' che la marketDefinition dice di un mercato lungo la registrazione."""

    market_id: str
    event_id: Optional[str] = None
    market_type: Optional[str] = None
    bet_delay: Optional[int] = None
    open_date: Optional[str] = None
    event_name: Optional[str] = None
    runners: Dict[int, Dict[str, Any]] = field(default_factory=dict)  # sel -> {sort_priority, status, name}
    settled_ms: Optional[int] = None   # primo istante col mercato CLOSED (regolato)
    n_libri: int = 0


@dataclass
class Decodifica:
    record: List[Dict[str, Any]]           # record compatti (serialize_book), ordinati per pt
    mercati: Dict[str, StatoMercato]
    righe_lette: int = 0
    righe_scartate: int = 0
    buchi: List[Tuple[int, int]] = field(default_factory=list)  # (da_ms, a_ms)


def _aggiorna_stato(stato: StatoMercato, mb: Any) -> None:
    md = getattr(mb, "market_definition", None)
    if md is not None:
        stato.event_id = str(md.event_id) if getattr(md, "event_id", None) else stato.event_id
        stato.market_type = getattr(md, "market_type", None) or stato.market_type
        stato.bet_delay = getattr(md, "bet_delay", None) if getattr(md, "bet_delay", None) is not None else stato.bet_delay
        od = getattr(md, "open_date", None)
        if od is not None:
            stato.open_date = od.astimezone(timezone.utc).isoformat() if od.tzinfo else od.replace(tzinfo=timezone.utc).isoformat()
        stato.event_name = getattr(md, "event_name", None) or stato.event_name
        for r in getattr(md, "runners", None) or []:
            sid = int(r.selection_id)
            info = stato.runners.setdefault(sid, {})
            info["sort_priority"] = getattr(r, "sort_priority", None)
            info["status"] = getattr(r, "status", None)
            if getattr(r, "name", None):
                info["name"] = r.name
    if str(getattr(mb, "status", "") or "").upper() == "CLOSED" and stato.settled_ms is None:
        stato.settled_ms = getattr(mb, "publish_time_epoch", None)
    stato.n_libri += 1


def decodifica_raw(fonte: Any, depth: int = LADDER_DEPTH) -> Decodifica:
    """Raw nativo -> record compatti, UN record per mercato toccato da ogni messaggio.

    Ogni riga ``mcm`` entra nel listener di betfairlightweight (cache con immagini e
    delta); dopo ogni riga si fotografano (``snap``) i soli mercati citati nella
    riga, come farebbe il recorder del calcio a ogni ``process_market_book``.
    Righe corrotte o non ``mcm`` (heartbeat, status) sono contate e saltate.
    """
    listener = StreamListener(max_latency=None, update_clk=False)
    listener.register_stream(0, "marketSubscription")
    out = Decodifica(record=[], mercati={})
    ultimo_pt: Optional[int] = None
    for riga in _righe(fonte):
        riga = riga.strip()
        if not riga:
            continue
        out.righe_lette += 1
        try:
            msg = json.loads(riga)
        except ValueError:
            out.righe_scartate += 1
            continue
        if not isinstance(msg, dict) or msg.get("op") != "mcm" or not msg.get("mc"):
            out.righe_scartate += 1
            continue
        pt = msg.get("pt")
        if isinstance(pt, (int, float)):
            if ultimo_pt is not None and pt - ultimo_pt > SOGLIA_BUCO_MS:
                out.buchi.append((int(ultimo_pt), int(pt)))
            ultimo_pt = int(pt)
        listener.on_data(riga)
        ids: List[str] = []
        for change in msg["mc"]:
            mid = change.get("id") if isinstance(change, dict) else None
            if mid and mid not in ids:
                ids.append(mid)
        for mb in listener.snap(market_ids=ids):
            stato = out.mercati.setdefault(mb.market_id, StatoMercato(market_id=mb.market_id))
            _aggiorna_stato(stato, mb)
            out.record.append(serialize_book(mb, depth))
    return out


def unisci_decodifiche(parti: Sequence[Decodifica]) -> Decodifica:
    """Unisce le decodifiche di piu' file della STESSA partita (es. la cartella del
    MATCH_ODDS e quella del SET_BETTING delle campagne ``record_multi``).

    Ogni file e' uno stream indipendente (decodificato col suo listener); i record
    si fondono per ``pt`` (ordinamento stabile) e un doppione esatto
    (stesso mercato, stesso ``pt``, stesso contenuto) entra una volta sola.
    """
    if len(parti) == 1:
        return parti[0]
    tutti: List[Tuple[int, int, Dict[str, Any]]] = []
    for i, p in enumerate(parti):
        for rec in p.record:
            tutti.append((int(rec.get("pt") or 0), i, rec))
    tutti.sort(key=lambda x: (x[0], x[1]))
    visti = set()
    record: List[Dict[str, Any]] = []
    for _pt, _i, rec in tutti:
        chiave = (rec.get("market_id"), rec.get("pt"), json.dumps(rec, sort_keys=True))
        if chiave in visti:
            continue
        visti.add(chiave)
        record.append(rec)
    mercati: Dict[str, StatoMercato] = {}
    for p in parti:
        for mid, st in p.mercati.items():
            if mid not in mercati:
                mercati[mid] = st
                continue
            base = mercati[mid]
            base.n_libri += st.n_libri
            for sid, info in st.runners.items():
                base.runners.setdefault(sid, {}).update({k: v for k, v in info.items() if v is not None})
            if st.settled_ms is not None and (base.settled_ms is None or st.settled_ms < base.settled_ms):
                base.settled_ms = st.settled_ms
            base.market_type = base.market_type or st.market_type
            base.bet_delay = base.bet_delay if base.bet_delay is not None else st.bet_delay
            base.event_id = base.event_id or st.event_id
            base.open_date = base.open_date or st.open_date
            base.event_name = base.event_name or st.event_name
    return Decodifica(
        record=record, mercati=mercati,
        righe_lette=sum(p.righe_lette for p in parti),
        righe_scartate=sum(p.righe_scartate for p in parti),
        buchi=sorted(b for p in parti for b in p.buchi),
    )


# ---------------------------------------------------------------------------
# 2) punteggio: sidecar IPS -> stato tennis + eventi della barra
# ---------------------------------------------------------------------------
def leggi_punteggi(fonte: Any, event_id: str) -> List[Tuple[float, TennisScore]]:
    """``(t_secondi, TennisScore)`` in ordine di tempo, senza doppioni di stato.

    Il parser e' ``parse_tennis_scores`` (lo stesso del worker live); una riga
    illeggibile o senza punteggio utile e' saltata.
    """
    out: List[Tuple[float, TennisScore]] = []
    for riga in _righe(fonte):
        riga = riga.strip()
        if not riga:
            continue
        try:
            rec = json.loads(riga)
            t = float(rec["t"])
        except (ValueError, KeyError, TypeError):
            continue
        ts = parse_tennis_scores([rec.get("score")] if isinstance(rec.get("score"), dict) else None, event_id)
        if ts is None:
            continue
        out.append((t, ts))
    out.sort(key=lambda x: x[0])
    dedup: List[Tuple[float, TennisScore]] = []
    for t, ts in out:
        if dedup and dedup[-1][1].key() == ts.key() and dedup[-1][1].status == ts.status:
            continue
        dedup.append((t, ts))
    return dedup


def _finita(stato: Optional[Dict[str, Any]]) -> bool:
    return str((stato or {}).get("status") or "").strip().lower() in _STATI_FINITI


def _int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def eventi_tennis(prev: Optional[Dict[str, Any]], cur: Dict[str, Any]) -> List[str]:
    """Gli EVENTI di gioco nel passaggio ``prev -> cur`` (due TennisScoreState).

    Tipi: ``BREAK`` (game vinto da chi RICEVEVA, fuori dal tie-break),
    ``SET_END``, ``MATCH_END``, ``SET_START`` (nuovo set iniziato, partita non
    finita), ``TIEBREAK_START``, ``SALTO`` (fra le due righe e' passato piu' di un
    game: buco della registrazione, nessun break dichiarato).
    ``prev`` assente (prima riga della registrazione): nessun evento, perche' non
    si sa quando sia successo cio' che e' gia' sul tabellone.
    """
    if prev is None:
        return []
    out: List[str] = []
    sp = (_int(prev["sets"]["p1"]), _int(prev["sets"]["p2"]))
    sc = (_int(cur["sets"]["p1"]), _int(cur["sets"]["p2"]))
    gp = (_int(prev["games"]["p1"]), _int(prev["games"]["p2"]))
    gc = (_int(cur["games"]["p1"]), _int(cur["games"]["p2"]))
    dset = (sc[0] - sp[0], sc[1] - sp[1])
    vincitore: Optional[int] = None
    salto = False
    if dset[0] < 0 or dset[1] < 0:
        salto = True  # il tabellone e' tornato indietro: non si deduce nulla
    elif dset[0] + dset[1] > 1:
        salto = True
    elif dset[0] + dset[1] == 1:
        vincitore = 1 if dset[0] == 1 else 2
        # game del set appena chiuso: ultima cella nuova di game_sequence, o i
        # game correnti se IPS non l'ha appesa (fine partita)
        seq_p = cur.get("game_sequence") or {}
        seq_prev = prev.get("game_sequence") or {}
        if len(seq_p.get("p1") or []) > len(seq_prev.get("p1") or []):
            finale = (_int(seq_p["p1"][-1]), _int(seq_p["p2"][-1]))
        else:
            finale = gc
        atteso = (gp[0] + (1 if vincitore == 1 else 0), gp[1] + (1 if vincitore == 2 else 0))
        if finale != atteso:
            salto = True
    else:
        dg = (gc[0] - gp[0], gc[1] - gp[1])
        if dg[0] < 0 or dg[1] < 0 or dg[0] + dg[1] > 1:
            salto = True
        elif dg == (1, 0):
            vincitore = 1
        elif dg == (0, 1):
            vincitore = 2
    if salto:
        out.append("SALTO")
    elif vincitore is not None:
        servizio = prev.get("server")
        if servizio in (1, 2) and servizio != vincitore and not prev.get("tiebreak"):
            out.append("BREAK")
    if dset[0] + dset[1] >= 1 and dset[0] >= 0 and dset[1] >= 0:
        out.append("SET_END")
    if _finita(cur) and not _finita(prev):
        out.append("MATCH_END")
    if not _finita(cur):
        cs_p, cs_c = prev.get("current_set"), cur.get("current_set")
        nuovo_set = (isinstance(cs_p, int) and isinstance(cs_c, int) and cs_c > cs_p) or (
            not isinstance(cs_c, int) and dset[0] + dset[1] >= 1)
        if nuovo_set:
            out.append("SET_START")
    if cur.get("tiebreak") and not prev.get("tiebreak"):
        out.append("TIEBREAK_START")
    return out


def righe_punteggio(punteggi: Sequence[Tuple[float, TennisScore]], event_id: str) -> List[Dict[str, Any]]:
    """Righe di ``tennis_replay_punteggio``: stato tennis, eventi e punto per riga.

    Lo stato e il punto vengono da ``tennis_score_state``/``point_event`` del runner
    (stesso contratto ``TennisScoreState``/``TennisPointEvent`` della UI live), con
    l'istante della RIGA al posto dell'ora di sistema.
    """
    from ..tennis_live.tennis_runner import point_event, tennis_score_state  # import pesante: solo qui

    righe: List[Dict[str, Any]] = []
    prev_ts: Optional[TennisScore] = None
    prev_stato: Optional[Dict[str, Any]] = None
    for t, ts in punteggi:
        iso = ms_a_iso(t * 1000.0)
        stato = tennis_score_state(ts, source="ips") or {}
        stato["updated_ms"] = int(round(t * 1000.0))
        punto = point_event(prev_ts, ts) if prev_ts is not None else None
        if punto is not None:
            punto["ts"] = iso
        righe.append({
            "event_id": str(event_id),
            "ts": iso,
            "source": "ips",
            "score": stato,
            "event_types": eventi_tennis(prev_stato, stato),
            "point": punto,
            "payload": ts.raw,
        })
        prev_ts, prev_stato = ts, stato
    return righe


# ---------------------------------------------------------------------------
# 3) catalogo, evento e snapshot
# ---------------------------------------------------------------------------
def selezioni_mercato(stato: StatoMercato, nomi: Optional[Dict[str, str]],
                      nomi_ips: Optional[Tuple[Optional[str], Optional[str]]]) -> List[Dict[str, Any]]:
    """``[{selection_id, name, name_source, sort_priority, status}]`` ordinate per sortPriority."""
    out: List[Dict[str, Any]] = []
    for sid, info in sorted(stato.runners.items(), key=lambda kv: (kv[1].get("sort_priority") or 999, kv[0])):
        nome = (nomi or {}).get(str(sid))
        fonte = "catalogo" if nome else None
        if not nome and info.get("name"):
            nome, fonte = info.get("name"), "marketdef"
        sp = info.get("sort_priority")
        if not nome and (stato.market_type or "").upper() == "MATCH_ODDS" and nomi_ips and sp in (1, 2):
            nome = nomi_ips[sp - 1]
            fonte = "ips" if nome else None
        out.append({
            "selection_id": sid,
            "name": nome or f"#{sid}",
            "name_source": fonte or "id",
            "sort_priority": sp,
            "status": info.get("status"),
        })
    return out


def rango_selezione(sel: Optional[Dict[str, Any]]) -> int:
    """Rango del nome di una selezione (gia' nel DB o appena convertita); -1 = assente."""
    if not sel:
        return -1
    nome = str(sel.get("name") or "")
    if not nome or nome.startswith("#"):
        return RANGO_NOME_FONTE["id"]
    fonte = sel.get("name_source")
    return RANGO_NOME_FONTE.get(str(fonte), RANGO_NOME_SENZA_FONTE) if fonte else RANGO_NOME_SENZA_FONTE


def migliora_selezioni(esistenti: Optional[Sequence[Dict[str, Any]]],
                       nuove: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Le selezioni da scrivere: le NUOVE (stato, esito, ordine aggiornati) ma col NOME
    gia' nel DB se la sua fonte e' MIGLIORE di quella nuova. Fonte pari o peggiore:
    resta il nome in DB; migliore: il nome si aggiorna. Reimport idempotente."""
    per_id = {int(s["selection_id"]): s for s in (esistenti or []) if s.get("selection_id") is not None}
    out: List[Dict[str, Any]] = []
    for n in nuove:
        e = per_id.get(int(n["selection_id"]))
        if e is not None and rango_selezione(e) > rango_selezione(n):
            m = dict(n, name=e["name"])
            if e.get("name_source"):
                m["name_source"] = e["name_source"]
            else:
                m.pop("name_source", None)
            out.append(m)
        else:
            out.append(dict(n))
    return out


@dataclass
class ReplayTennis:
    evento: Dict[str, Any]
    mercati: List[Dict[str, Any]]
    snapshot: List[Dict[str, Any]]
    punteggio: List[Dict[str, Any]]
    diagnostica: Dict[str, Any]


def converti_evento(
    raw: Sequence[Any],
    score: Sequence[Any] = (),
    *,
    event_id: Optional[str] = None,
    nomi: Optional[Dict[str, Dict[str, str]]] = None,
    meta: Optional[Dict[str, Any]] = None,
    nomi_mercato: Optional[Dict[str, str]] = None,
    cadence_sec: float = UPLOAD_CADENCE_SEC,
    depth: int = LADDER_DEPTH,
) -> ReplayTennis:
    """UNA partita: file raw (uno o piu') + sidecar punteggio -> righe delle tabelle.

    :param nomi: ``{market_id: {selection_id: nome}}`` (catalogo); la chiave
        ``"*"`` vale per ogni mercato (formato ``_names.json``: per evento).
    :param meta: anagrafica nota al chiamante (``competition_name``,
        ``player1_name``, ``player2_name``, ``open_date``): vince su quella dedotta.
    :param nomi_mercato: ``{market_id: nome}`` dal catalogo (es. "Set 1 Winner"):
        vince sul nome dedotto dal tipo (due SET_WINNER si distinguono solo cosi').
    """
    dec = unisci_decodifiche([decodifica_raw(f, depth) for f in raw])
    if not dec.record:
        raise ValueError(f"nessun libro di mercato nel raw ({dec.righe_lette} righe, "
                         f"{dec.righe_scartate} scartate): niente da caricare")
    ev = event_id or next((m.event_id for m in dec.mercati.values() if m.event_id), None)
    if not ev:
        raise ValueError("event_id non deducibile dal raw (nessuna marketDefinition)")
    ev = str(ev)

    punteggi: List[Tuple[float, TennisScore]] = []
    for f in score:
        punteggi.extend(leggi_punteggi(f, ev))
    punteggi.sort(key=lambda x: x[0])
    nomi_ips: Optional[Tuple[Optional[str], Optional[str]]] = None
    if punteggi:
        ultimo = punteggi[-1][1]
        nomi_ips = (ultimo.home_name, ultimo.away_name)

    snapshot = curate_records(dec.record, ev, cadence_sec=cadence_sec)
    for r in snapshot:
        r.pop("minute", None)  # il tennis non ha minuto di gioco: la barra usa il punteggio

    per_mercato: Dict[str, List[Dict[str, Any]]] = {}
    for r in snapshot:
        per_mercato.setdefault(r["market_id"], []).append(r)
    mercati: List[Dict[str, Any]] = []
    for mid, st in dec.mercati.items():
        righe = per_mercato.get(mid, [])
        n_nomi = dict((nomi or {}).get("*") or {})
        n_nomi.update((nomi or {}).get(mid) or {})
        tipo = (st.market_type or "").upper() or None
        mercati.append({
            "event_id": ev,
            "market_id": mid,
            "market_type": tipo,
            "market_name": (nomi_mercato or {}).get(mid) or nome_mercato(tipo),
            "sort_priority": 1 if tipo == "MATCH_ODDS" else None,
            "selections": selezioni_mercato(st, n_nomi, nomi_ips),
            "bet_delay": st.bet_delay,
            "settled_ts": ms_a_iso(st.settled_ms),
            "n_updates": len(righe),
            "ts_min": righe[0]["ts"] if righe else None,
            "ts_max": righe[-1]["ts"] if righe else None,
        })
    mercati.sort(key=lambda m: (m["sort_priority"] or 999, m["market_type"] or "", m["market_id"]))
    for i, m in enumerate(mercati):
        m["sort_priority"] = i + 1

    mo = next((m for m in mercati if m["market_type"] == "MATCH_ODDS"), None)
    p1 = p2 = None
    fonte_p1 = fonte_p2 = None   # 08/10 (cantiere 14): chi ha dato il nome di ciascun giocatore
    if mo:
        sel_mo = [s for s in mo["selections"] if s.get("sort_priority") in (1, 2)]
        nomi_mo = [s["name"] for s in sel_mo]
        if len(nomi_mo) == 2 and not any(n.startswith("#") for n in nomi_mo):
            p1, p2 = nomi_mo
            fonte_p1, fonte_p2 = sel_mo[0]["name_source"], sel_mo[1]["name_source"]
    nome_evento = next((m.event_name for m in dec.mercati.values() if m.event_name), None)
    if (p1 is None or p2 is None) and nome_evento and " v " in nome_evento:
        p1, p2 = [x.strip() for x in nome_evento.split(" v ", 1)]
        fonte_p1 = fonte_p2 = "evento"
    if (p1 is None or p2 is None) and nomi_ips:
        p1, p2 = nomi_ips
        fonte_p1, fonte_p2 = ("ips" if p1 else None), ("ips" if p2 else None)
    evento = {
        "event_id": ev,
        "competition_name": None,
        "player1_name": p1 or "",
        "player2_name": p2 or "",
        "open_date": next((m.open_date for m in dec.mercati.values() if m.open_date), None),
    }
    fonti_giocatori = {"player1_name": fonte_p1, "player2_name": fonte_p2}
    for k, v in (meta or {}).items():
        if k in evento and v:
            evento[k] = v
            if k in fonti_giocatori:
                fonti_giocatori[k] = "catalogo"   # anagrafica data dal chiamante (DB tennis: catalogo Betfair)
    nomi_fonte = {k: f for k, f in fonti_giocatori.items() if f and evento[k]}

    punteggio = righe_punteggio(punteggi, ev)
    diagnostica = {
        "righe_raw": dec.righe_lette,
        "righe_scartate": dec.righe_scartate,
        "libri": len(dec.record),
        "snapshot": len(snapshot),
        "mercati": len(mercati),
        "punteggi": len(punteggio),
        "buchi": [{"da": ms_a_iso(a), "a": ms_a_iso(b), "secondi": round((b - a) / 1000.0, 1)} for a, b in dec.buchi],
        "nomi_fonte": nomi_fonte,
    }
    return ReplayTennis(evento=evento, mercati=mercati, snapshot=snapshot,
                        punteggio=punteggio, diagnostica=diagnostica)


def nomi_da_cache(data_dir: str, event_id: str) -> Dict[str, Dict[str, str]]:
    """``_names.json`` accanto alle registrazioni -> ``{"*": {...}, market_id: {...}}``.

    Formato PIATTO (grid runner, banco, lab: ``{event_id: {selection_id: nome}}``, i
    nomi del Match Odds) -> chiave ``"*"``. 08/10 (cantiere 14): il registratore tennis
    aggiunge ``{"_mercati": {event_id: {market_id: {selection_id: nome}}}}`` con i nomi
    COMPLETI di tutti i mercati registrati (chiave riservata: non e' un event_id, i
    lettori piatti non la vedono) -> una chiave per mercato."""
    path = os.path.join(data_dir, "_names.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            tutto = json.load(fh) or {}
    except (ValueError, OSError):
        return {}
    if not isinstance(tutto, dict):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    per_evento = tutto.get(str(event_id)) or {}
    if isinstance(per_evento, dict):
        piatti = {str(k): v for k, v in per_evento.items() if isinstance(v, str) and v}
        if piatti:
            out["*"] = piatti
    tutti_i_mercati = tutto.get(CHIAVE_MERCATI_NOMI)
    per_mercato = tutti_i_mercati.get(str(event_id)) if isinstance(tutti_i_mercati, dict) else None
    if isinstance(per_mercato, dict):
        for mid, nomi in per_mercato.items():
            if isinstance(nomi, dict):
                validi = {str(k): v for k, v in nomi.items() if isinstance(v, str) and v}
                if validi:
                    out[str(mid)] = validi
    return out
