"""season_aggregates.py - Lacune e recupero degli AGGREGATI per lega-stagione (25/09/2026).

Aggregati = tabelle scritte per (league_id, season_year), non per partita:
standings, injuries, top_scorers, top_assists, top_cards. Tutte si scrivono
con delete (league_id, season_year) + insert (gli script *_backfill.py): la
data dell'ultimo aggiornamento e' max(updated_at, created_at) delle righe.

Quando un aggregato e' un BUCO (da chiamare) - regola misurabile e leggera:
  flag di coverage False            -> 'flag_false'  (non si chiama, si dichiara)
  ultimo tentativo errore/parziale  -> 'errore'      (si chiama)
  mai aggiornato (0 righe, nessun tentativo) -> 'mancante' (si chiama)
  da aggiornare, per cadenza (T = ultimo aggiornamento o ultimo tentativo riuscito):
    standings   : dopo OGNI giornata -> partite FT piu' recenti di T
    injuries    : stagione viva -> ogni giorno (T piu' vecchio di 20 h: due
                  finestre del recupero al giorno); stagione passata -> mai
    top_scorers, top_assists, top_cards : partite FT piu' recenti di T e, se la
                  stagione e' viva, T piu' vecchio di 7 giorni (settimanale);
                  stagione passata -> una volta dopo l'ultima partita (finale)
  0 righe ma ultimo tentativo 'vuoto' e nulla da aggiornare -> 'vuoto_api' (dichiarato)
  altrimenti 'ok'.

Costo API per lega-stagione (chiamate): standings 1, injuries 1, top_scorers 1,
top_assists 1, top_cards 2 (/players/topyellowcards + /players/topredcards).

Idempotenza: delete per (lega, stagione) + insert. La delete si RITENTA a
passo crescente (db_delete_retry.delete_con_ritentativi, 25/09/2026, ordine
utente: stessa regola applicata anche agli script storici *_backfill.py); se
fallisce anche l'ultimo tentativo l'aggregato si FERMA (esito 'errore', nessun
insert), e un insert fallito a meta' e' 'parziale' -> rifatto al giro dopo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

MIGRAZIONE_AGG = "migrations/season_aggregates_2026-09-25.sql"
ORDINE = ("standings", "injuries", "top_scorers", "top_assists", "top_cards")
COSTO: Dict[str, int] = {"standings": 1, "injuries": 1, "top_scorers": 1, "top_assists": 1, "top_cards": 2}
DA_CHIAMARE = ("mancante", "da_aggiornare", "errore")
ORE_INJURIES = 20
GIORNI_TOP = 7


@dataclass(frozen=True)
class Chiamata:
    endpoint: str
    card_type: Optional[str] = None


CHIAMATE: Dict[str, Tuple[Chiamata, ...]] = {
    "standings": (Chiamata("/standings"),),
    "injuries": (Chiamata("/injuries"),),
    "top_scorers": (Chiamata("/players/topscorers"),),
    "top_assists": (Chiamata("/players/topassists"),),
    "top_cards": (Chiamata("/players/topyellowcards", "yellow"), Chiamata("/players/topredcards", "red")),
}


def _ts(v: Any) -> Optional[datetime]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def stato_aggregato(nome: str, flag: bool, viva: bool, n_righe: int, ultimo: Any, ultima_ft: Any,
                    tentativo: Optional[Dict[str, Any]], adesso: datetime) -> str:
    if not flag:
        return "flag_false"
    tentativo = tentativo or {}
    esito = tentativo.get("esito")
    if esito in ("errore", "parziale"):
        return "errore"
    candidati = [x for x in (_ts(ultimo), _ts(tentativo.get("at")) if esito in ("righe", "vuoto") else None) if x]
    t = max(candidati) if candidati else None
    if t is None:
        return "mancante"
    ft = _ts(ultima_ft)
    nuove = ft is not None and ft > t
    if nome == "standings":
        serve = nuove
    elif nome == "injuries":
        serve = viva and t < adesso - timedelta(hours=ORE_INJURIES)
    else:
        serve = nuove and (not viva or t < adesso - timedelta(days=GIORNI_TOP))
    if serve:
        return "da_aggiornare"
    if int(n_righe or 0) == 0:
        return "vuoto_api" if esito == "vuoto" else "mancante"
    return "ok"


def calcola(riga_cov: Dict[str, Any], info: Dict[str, Any], tentativi: Dict[str, Any], viva: bool,
            adesso: datetime) -> Dict[str, Dict[str, Any]]:
    """info: {'_ft': ultima FT, nome: {'n':, 'ultimo':}} -> {nome: {stato, n, ultimo, costo}}."""
    out: Dict[str, Dict[str, Any]] = {}
    for nome in ORDINE:
        dati = info.get(nome) or {}
        st = stato_aggregato(nome, bool(riga_cov.get(nome)), viva, int(dati.get("n") or 0), dati.get("ultimo"),
                             info.get("_ft"), (tentativi or {}).get(nome), adesso)
        out[nome] = {"stato": st, "n": int(dati.get("n") or 0), "ultimo": dati.get("ultimo"),
                     "costo": COSTO[nome] if st in DA_CHIAMARE else 0}
    return out


def leggi_info(sb: Any, coppie: Sequence[Tuple[int, int]], blocco: int = 150) -> Dict[Tuple[int, int], Dict[str, Any]]:
    """RPC season_aggregates_summary a blocchi (<= 150 coppie x 6 righe < 1000 righe PostgREST)."""
    from season_gaps import MigrazioneMancante, _e_funzione_mancante
    out: Dict[Tuple[int, int], Dict[str, Any]] = {(int(a), int(b)): {} for a, b in coppie}
    lista = list(out)
    for i in range(0, len(lista), blocco):
        pezzo = lista[i:i + blocco]
        try:
            resp = sb.rpc("season_aggregates_summary", {"p_league_ids": [p[0] for p in pezzo],
                                                        "p_season_years": [p[1] for p in pezzo]}).execute()
        except Exception as e:
            if _e_funzione_mancante(e):
                raise MigrazioneMancante(
                    f"RPC season_aggregates_summary assente: applica {MIGRAZIONE_AGG} (errore: {e})") from e
            raise
        for r in list(getattr(resp, "data", None) or []):
            k = (int(r["league_id"]), int(r["season_year"]))
            if k not in out:
                continue
            if r.get("tabella") == "_ft":
                out[k]["_ft"] = r.get("ultimo")
            else:
                out[k][r["tabella"]] = {"n": int(r.get("n") or 0), "ultimo": r.get("ultimo")}
    return out


# ---------------------------------------------------------------------------
# Esecuzione sicura di UN aggregato (client condiviso: chiamate contate nella quota)
# ---------------------------------------------------------------------------
def _mappa(nome: str) -> Callable[..., List[Dict[str, Any]]]:
    if nome == "standings":
        from standings_backfill import map_standings_response_to_rows as f
    elif nome == "injuries":
        from injuries_backfill import map_injuries_response_to_rows as f
    elif nome == "top_scorers":
        from top_scorers_backfill import map_top_scorers_response_to_rows as f
    elif nome == "top_assists":
        from top_assists_backfill import map_top_assists_response_to_rows as f
    else:
        from top_cards_backfill import map_top_cards_response_to_rows as f
    return f


def esegui_aggregato(sb: Any, client: Any, nome: str, league_id: int, season_year: int,
                     batch: int = 200) -> str:
    """-> 'righe' | 'vuoto' | 'errore' | 'parziale'. Mai righe doppie: se la delete
    fallisce non si inserisce nulla."""
    from per_fixture_backfill import _risposta_o_none
    righe: List[Dict[str, Any]] = []
    mappa = _mappa(nome)
    for ch in CHIAMATE[nome]:
        data = client.call(ch.endpoint, params={"league": league_id, "season": season_year})
        lista = _risposta_o_none(data)
        if lista is None:
            print(f"[AGGREGATI] {nome} lega {league_id} stagione {season_year}: errore API su {ch.endpoint}")
            return "errore"
        if not lista:
            continue
        dati = {"response": lista}
        righe.extend(mappa(dati, league_id, season_year, ch.card_type) if ch.card_type
                     else mappa(dati, league_id, season_year))
    if not righe:
        return "vuoto"
    from db_delete_retry import delete_con_ritentativi
    try:
        delete_con_ritentativi(
            lambda: sb.table(nome).delete().eq("league_id", league_id).eq("season_year", season_year).execute(),
            etichetta=f"delete {nome} league_id={league_id} season_year={season_year}",
        )
    except Exception as e:
        print(f"[AGGREGATI] {nome} lega {league_id} stagione {season_year}: delete fallita dopo i "
              f"ritentativi ({e}): NESSUN insert (niente doppioni)")
        return "errore"
    for i in range(0, len(righe), batch):
        try:
            sb.table(nome).insert(righe[i:i + batch]).execute()
        except Exception as e:
            print(f"[AGGREGATI] {nome} lega {league_id} stagione {season_year}: insert fallito ({e})")
            return "parziale"
    return "righe"


def attacca(sb: Any, lacune: Dict[Tuple[int, int], Any], righe_cov: Dict[Tuple[int, int], Dict[str, Any]],
            stati: Dict[Tuple[int, int], Dict[str, Any]], adesso: Optional[datetime] = None) -> None:
    """Calcola lo stato degli aggregati di ogni lega-stagione e lo mette in Lacune.aggregati."""
    import season_gaps as sg
    ora = adesso or datetime.now(timezone.utc)
    info = leggi_info(sb, list(lacune))
    for k, lac in lacune.items():
        riga = righe_cov[k]
        tentativi = (((stati.get(k) or {}).get("stats_json") or {}).get("aggregati_tentativi")) or {}
        lac.aggregati = calcola(riga, info.get(k) or {}, tentativi,
                                sg.e_corrente_o_recente(riga, ora.date()), ora)


def verifica_migrazione(sb: Any) -> None:
    leggi_info(sb, [(0, 0)])


def riga_dry_run(agg: Dict[str, Dict[str, Any]]) -> str:
    parti = []
    for nome in ORDINE:
        a = agg[nome]
        quando = str(a.get("ultimo") or "-")[:10]
        costo = f" ~{a['costo']}" if a["costo"] else ""
        parti.append(f"{nome}={a['stato']}({quando}){costo}")
    return "aggregati: " + "  ".join(parti)


def adesso() -> datetime:
    """Ora UTC (punto unico: i test la fissano)."""
    return datetime.now(timezone.utc)
