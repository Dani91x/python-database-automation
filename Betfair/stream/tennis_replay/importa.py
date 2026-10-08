"""Importa nel Replay Tennis le registrazioni gia' su disco. SI LANCIA A MANO.

Uso (dal PC dell'utente, cartella del repo):

    python -m Betfair.stream.tennis_replay.importa <cartella> [<cartella> ...]
    python -m Betfair.stream.tennis_replay.importa C:/Users/Admin/Desktop/tennis_rec
    python -m Betfair.stream.tennis_replay.importa <cartella> --evento 35790089 --prova

Le cartelle si visitano in profondita': ogni ``<id>/<id>.raw.jsonl`` e' una
partita (layout del recorder tennis e delle campagne ``record_multi``), col suo
``<id>.score.jsonl`` accanto se c'e'. La STESSA partita trovata in piu' cartelle
(es. ``20260707`` col MATCH_ODDS e ``setbetting_20260707`` col SET_BETTING) entra
come UNA partita con tutti i suoi mercati.

Nomi dei runner: ``--nomi file.json`` (``{event_id: {selection_id: nome}}``), poi
``_names.json`` accanto alle registrazioni (formato piatto del Match Odds e, dal 08/10,
``_mercati`` con TUTTI i mercati registrati), poi il catalogo del tennis nel DB
(``tennis_markets``; se il Match Odds non c'e', i nomi che il runner ha pubblicato in
``tennis_live_now``/``tennis_live_ladder``; sola lettura), poi i nomi IPS per il Match
Odds (TRONCATI: la pagina li segnala), poi ``#id``. Anagrafica (torneo, giocatori) da
``tennis_live_follow``/``tennis_markets`` se la partita c'e'. (``betfair_market_*`` e'
del calcio, per fixture API-Football: non porta mai i nomi del tennis.)

Idempotente e rilanciabile: rilanciarlo riscrive le stesse righe, mai doppie
(``caricamento.carica_replay``); un nome gia' nel DB cambia solo se la nuova fonte e'
MIGLIORE. ``--solo-nomi``: aggiorna solo i nomi delle partite gia' caricate, senza
toccare snapshot e punteggio (``caricamento.aggiorna_nomi``). ``--prova``: converte e
stampa il riepilogo SENZA toccare il DB (nessuna lettura, nessuna scrittura).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .convertitore import ReplayTennis, converti_evento, nomi_da_cache

logger = logging.getLogger(__name__)


def trova_registrazioni(cartelle: Sequence[str]) -> "OrderedDict[str, Dict[str, List[str]]]":
    """``{event_id: {"raw": [...], "score": [...], "dirs": [...]}}`` (ordine stabile)."""
    out: "OrderedDict[str, Dict[str, List[str]]]" = OrderedDict()
    for radice in cartelle:
        for dirpath, dirnames, filenames in os.walk(radice):
            dirnames.sort()
            ev = os.path.basename(os.path.normpath(dirpath))
            raw = f"{ev}.raw.jsonl"
            if raw not in filenames:
                continue
            voce = out.setdefault(ev, {"raw": [], "score": [], "dirs": []})
            voce["raw"].append(os.path.join(dirpath, raw))
            voce["dirs"].append(os.path.dirname(os.path.normpath(dirpath)))
            sc = f"{ev}.score.jsonl"
            if sc in filenames:
                voce["score"].append(os.path.join(dirpath, sc))
    return out


def _nomi_da_file(path: Optional[str], ev: str) -> Dict[str, Dict[str, str]]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        tutto = json.load(fh) or {}
    per = tutto.get(str(ev)) or {}
    return {"*": {str(k): str(v) for k, v in per.items()}} if per else {}


def _nomi_validi(selezioni: Any) -> Dict[str, str]:
    """``{selection_id: nome}`` da una lista ``[{selection_id, name, ...}]`` (nomi veri soltanto)."""
    out: Dict[str, str] = {}
    for s in selezioni or []:
        if isinstance(s, dict) and s.get("selection_id") is not None and s.get("name") not in (None, "", "?"):
            out[str(s["selection_id"])] = str(s["name"])
    return out


def _nomi_dalle_tabelle_live(sb: Any, ev: str) -> Dict[str, Dict[str, str]]:
    """Nomi dei runner gia' pubblicati dal runner tennis (catalogo ``listMarketCatalogue``),
    SOLA LETTURA: ``tennis_live_now.state.markets[].selections`` e
    ``tennis_live_ladder.ladder.selections`` (formati di ``_build_now_state`` e
    ``build_ladder_payload``). ``{market_id: {selection_id: nome}}``; errori -> vuoto."""
    out: Dict[str, Dict[str, str]] = {}
    try:
        for r in (sb.table("tennis_live_now").select("state").eq("event_id", ev).limit(1).execute().data or []):
            for mk in ((r.get("state") or {}).get("markets") or []):
                n = _nomi_validi((mk or {}).get("selections"))
                if n and (mk or {}).get("market_id"):
                    out.setdefault(str(mk["market_id"]), {}).update(n)
        for r in (sb.table("tennis_live_ladder").select("market_id,ladder").eq("event_id", ev)
                  .limit(20).execute().data or []):
            n = _nomi_validi((r.get("ladder") or {}).get("selections"))
            if n and r.get("market_id"):
                for sid, nome in n.items():
                    out.setdefault(str(r["market_id"]), {}).setdefault(sid, nome)
    except Exception as e:  # noqa: BLE001 - un di piu': mai bloccare l'import
        logger.warning("[replay-tennis] nomi dalle tabelle live %s non letti: %s", ev, str(e)[:160])
    return out


def anagrafica_dal_db(ev: str) -> Tuple[Dict[str, Any], Dict[str, Dict[str, str]], Dict[str, str]]:
    """(meta, nomi dei runner per mercato, nomi dei mercati) dalle tabelle del
    TENNIS, SOLA LETTURA. ``tennis_markets.full_odds`` porta il catalogo di TUTTI
    i mercati dell'evento (nomi dei mercati e dei runner). Errori -> vuoto."""
    meta: Dict[str, Any] = {}
    nomi: Dict[str, Dict[str, str]] = {}
    nomi_mercato: Dict[str, str] = {}
    try:
        from db_client import get_supabase_client

        sb = get_supabase_client()
        f = (sb.table("tennis_live_follow").select("competition_name,player1_name,player2_name,open_date")
             .eq("event_id", ev).limit(1).execute().data or [])
        if f:
            meta = {k: v for k, v in f[0].items() if v}
        m = (sb.table("tennis_markets").select("market_id,competition_name,open_date,player1,player2,full_odds")
             .eq("event_id", ev).limit(1).execute().data or [])
        if m:
            riga = m[0]
            meta.setdefault("competition_name", riga.get("competition_name"))
            meta.setdefault("open_date", riga.get("open_date"))
            sel: Dict[str, str] = {}
            for k in ("player1", "player2"):
                g = riga.get(k) or {}
                if g.get("selection_id") is not None and g.get("name"):
                    sel[str(g["selection_id"])] = str(g["name"])
            if sel and riga.get("market_id"):
                nomi[str(riga["market_id"])] = sel
            for mk in riga.get("full_odds") or []:          # TennisFullMarket[]
                mid = str((mk or {}).get("market_id") or "")
                if not mid:
                    continue
                if mk.get("market"):
                    nomi_mercato[mid] = str(mk["market"])
                runner = {str(r["selection_id"]): str(r["selection"]) for r in (mk.get("runners") or [])
                          if r.get("selection_id") is not None and r.get("selection") not in (None, "?")}
                if runner:
                    nomi.setdefault(mid, {}).update(runner)
            mo_id = str(riga.get("market_id") or "")
        else:
            mo_id = ""
        if not mo_id or mo_id not in nomi:
            # 08/10 (cantiere 14): il Match Odds non e' in tennis_markets (caso 35790089): i nomi
            # che il runner ha pubblicato dal catalogo, con gli stessi selection_id dello stream
            for mid, sel in _nomi_dalle_tabelle_live(sb, ev).items():
                for sid, nome in sel.items():
                    nomi.setdefault(mid, {}).setdefault(sid, nome)
    except Exception as e:  # noqa: BLE001 - l'anagrafica e' un di piu': mai bloccare l'import
        logger.warning("[replay-tennis] anagrafica %s non letta dal DB: %s", ev, str(e)[:160])
    return {k: v for k, v in meta.items() if v}, nomi, nomi_mercato


def converti_registrazione(ev: str, voce: Dict[str, List[str]], *, nomi_file: Optional[str] = None,
                           usa_db: bool = True) -> ReplayTennis:
    nomi: Dict[str, Dict[str, str]] = {}
    meta: Dict[str, Any] = {}
    nomi_mercato: Dict[str, str] = {}
    if usa_db:
        meta, nomi, nomi_mercato = anagrafica_dal_db(ev)
    for d in voce["dirs"]:
        for k, v in nomi_da_cache(d, ev).items():
            nomi.setdefault(k, {}).update(v)
    for k, v in _nomi_da_file(nomi_file, ev).items():
        nomi.setdefault(k, {}).update(v)
    return converti_evento(voce["raw"], voce["score"], event_id=ev, nomi=nomi, meta=meta,
                           nomi_mercato=nomi_mercato)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m Betfair.stream.tennis_replay.importa",
                                 description="Importa nel Replay Tennis le registrazioni tennis gia' su disco.")
    ap.add_argument("cartelle", nargs="+", help="cartelle da visitare (es. Desktop/tennis_rec)")
    ap.add_argument("--evento", action="append", default=[], help="solo questi event_id (ripetibile)")
    ap.add_argument("--nomi", default=None, help="json {event_id: {selection_id: nome}}")
    ap.add_argument("--prova", action="store_true", help="converte e stampa, NESSUN accesso al DB")
    ap.add_argument("--solo-nomi", action="store_true",
                    help="aggiorna SOLO i nomi (giocatori e selezioni) delle partite gia' caricate, se la "
                         "fonte e' migliore; snapshot, punteggio e conteggi non si toccano")
    args = ap.parse_args(argv)
    if args.solo_nomi and args.prova:
        ap.error("--solo-nomi e --prova si escludono: --prova non tocca il DB")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    trovate = trova_registrazioni(args.cartelle)
    if args.evento:
        trovate = OrderedDict((k, v) for k, v in trovate.items() if k in set(args.evento))
    if not trovate:
        print("nessuna registrazione <id>/<id>.raw.jsonl trovata")
        return 1
    esiti: List[Dict[str, Any]] = []
    ko = 0
    for ev, voce in trovate.items():
        try:
            rt = converti_registrazione(ev, voce, nomi_file=args.nomi, usa_db=not args.prova)
            if args.prova:
                esiti.append({"event_id": ev, "file": voce["raw"], "evento": rt.evento,
                              "mercati": [(m["market_type"], m["market_id"], m["n_updates"]) for m in rt.mercati],
                              "diagnostica": rt.diagnostica})
                continue
            if args.solo_nomi:
                from .caricamento import aggiorna_nomi

                esiti.append(aggiorna_nomi(rt))
                continue
            from .caricamento import carica_replay

            byte =sum(os.path.getsize(p) for p in voce["raw"])
            esiti.append(carica_replay(rt, fonte="import", raw_files=voce["raw"], raw_bytes=byte))
        except Exception as e:  # noqa: BLE001 - una partita rotta non ferma le altre
            ko += 1
            logger.exception("[replay-tennis] %s KO: %s", ev, e)
            esiti.append({"event_id": ev, "errore": str(e)[:300]})
    print(json.dumps(esiti, indent=2, ensure_ascii=True, default=str))
    return 0 if ko == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
