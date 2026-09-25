"""SELEZIONE AGGIUNTIVA del RISULTATO ESATTO (SPEC §2) — il DATO, non la regola.

D5 (decisione dell'utente 25/09): lo scanner NON pubblica piu' `hint()`
(atlante, per nome) ma la SCHEDA DB della fixture abbinata
(`SchedeFixture` / `hint_da_scheda`, in fondo al file). Le funzioni
dell'atlante qui sotto restano per gli altri consumatori (`atlante()` serve
al modello opportunita') e per i loro test.

    | Selezione aggiuntiva | scontri diretti senza troppi 2-2/3-3,
    |                      | difesa avversaria solida                  (SPEC §2)

Questo modulo NON decide niente: prepara i due NUMERI che la voce della SPEC
nomina, e li consegna allo scanner perche' li pubblichi nella riga di scan. La
regola (le soglie, il verso) vive nel motore, in UN SOLO posto, e viene letta
identica dal motore Python (il bot) e da quello TypeScript (la pagina) — la
stessa disciplina dell'indice di CONTROLLO del gioco (`pressure.py`): un solo
numero calcolato una volta sola, mai due ricalcoli che possono divergere.

DA DOVE VIENE IL DATO — nessuna risorsa nuova (regola: prima si cerca):
  `Betfair/omega/data/hazard_atlas_v2.json`, lo stesso file che usa gia'
  `omega_advisor.h2h_score_stats` (blocco `h2h_hint`) e che il consulente di
  Omega interroga per le missioni. Si carica con il loader gia' esistente
  (`Betfair/stream/scalper/theta_bot.load_hazard_atlas`). Nessuna lettura DB,
  nessuna chiamata di rete, nessun processo nuovo.

  * `h2h_hint['<idA>-<idB>']['ft_scores_a_b']` — distribuzione dei punteggi
    finali negli scontri diretti (solo coppie con >= 3 incontri: e' il
    contratto del dato, non una soglia nostra). 2-2 e 3-3 sono simmetrici,
    quindi l'orientamento della chiave non conta.
  * `by_team['<id>']['def_goals_per_match_by_bucket']` — gol SUBITI per
    partita spezzati nei 18 bucket da 5': la somma e' la media dei gol subiti
    per partita, cioe' la "solidita' della difesa".

L'ABBINAMENTO E' PER NOME, e questo e' un limite dichiarato: la riga di scan
porta i nomi delle due squadre (dall'evento Betfair e dal punteggio IPS), non
l'id della fixture (`service.py`: «lo scanner non ha il fixture_id»). Si
riusa la ricerca per nome gia' scritta (`theta_bot._find_team`), normalizzata.
Nome che non si trova = dato ASSENTE, mai un abbinamento forzato: meglio un
"non lo so" che una statistica di un'altra squadra.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("safe.selezione")

# lo STESSO file dell'advisor di Omega (che ha il blocco h2h_hint): non se ne
# aggiunge un altro, non se ne copia il contenuto.
ATLAS_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "omega", "data", "hazard_atlas_v2.json"))

# i punteggi che la SPEC chiama per nome: i pareggi "alti". Sono simmetrici,
# quindi valgono in qualunque verso sia orientata la chiave dell'atlante.
PAREGGI_ALTI: Tuple[str, ...] = ("2-2", "3-3")

FONTE = "hazard_atlas_v2"

# cache di processo. L'atlante vive UNA volta sola in tutto il processo, nella
# cache CONDIVISA di ``hazard_atlas.atlante_condiviso`` (la stessa che usano il
# modello opportunita', Omega, Mike e theta): qui restano solo le cache
# DERIVATE (indice dei nomi, hint per coppia), che si svuotano da sole quando
# l'atlante condiviso cambia oggetto (file rigenerato sul disco).
_ATLAS: Optional[Dict[str, Any]] = None      # l'ultimo oggetto visto (identita')
_INDICE_NOMI: Optional[Dict[str, str]] = None
_HINT_CACHE: Dict[Tuple[str, str], Optional[Dict[str, Any]]] = {}
_CACHE_MAX = 512


def reset_cache() -> None:
    """Svuota atlante e cache (test / riavvio logico)."""
    global _ATLAS, _INDICE_NOMI
    _ATLAS = None
    _INDICE_NOMI = None
    _HINT_CACHE.clear()
    try:
        from Betfair.stream.scalper.hazard_atlas import reset_atlante_condiviso

        reset_atlante_condiviso()
    except Exception:  # noqa: BLE001
        pass


def _normalizza(nome: Any) -> str:
    """Nome confrontabile: senza accenti, senza punteggiatura, minuscolo."""
    s = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def atlante() -> Dict[str, Any]:
    """L'atlante CORRENTE (condiviso). {} se manca o e' illeggibile.

    24/09 (ordine dell'utente: i sistemi di supporto "DEVONO aggiornarsi"):
    se il file cambia sul disco la cache condivisa lo rilegge (mtime, al piu'
    un controllo al minuto) e qui le cache derivate si svuotano. Mai
    eccezioni: l'atlante non deve mai fermare lo scanner."""
    global _ATLAS, _INDICE_NOMI
    try:
        from Betfair.stream.scalper.hazard_atlas import atlante_condiviso

        corrente = atlante_condiviso()
    except Exception as ex:  # noqa: BLE001 - l'atlante non deve mai fermare lo scanner
        logger.warning("[safe-selezione] atlante non leggibile: %s", str(ex)[:120])
        corrente = _ATLAS if _ATLAS is not None else {}
    if corrente is not _ATLAS:
        _ATLAS = corrente
        _INDICE_NOMI = None
        _HINT_CACHE.clear()
    return _ATLAS


def _indice_nomi() -> Dict[str, str]:
    """nome normalizzato -> id squadra. Un nome ambiguo (due squadre con lo
    stesso nome normalizzato) viene SCARTATO: meglio nessun dato che quello
    della squadra sbagliata."""
    global _INDICE_NOMI
    if _INDICE_NOMI is None:
        idx: Dict[str, str] = {}
        ambigui = set()
        for tid, blocco in (atlante().get("by_team") or {}).items():
            if not isinstance(blocco, dict):
                continue
            chiave = _normalizza(blocco.get("team_name"))
            if not chiave:
                continue
            if chiave in idx and idx[chiave] != str(tid):
                ambigui.add(chiave)
                continue
            idx[chiave] = str(tid)
        for chiave in ambigui:
            idx.pop(chiave, None)
        _INDICE_NOMI = idx
    return _INDICE_NOMI


def team_id(nome: Any) -> Optional[str]:
    """id della squadra nell'atlante, per nome. None = non abbinata."""
    chiave = _normalizza(nome)
    return _indice_nomi().get(chiave) if chiave else None


def gol_subiti_per_partita(tid: Optional[str]) -> Optional[float]:
    """Media dei gol SUBITI per partita (somma dei 18 bucket da 5')."""
    if tid is None:
        return None
    blocco = (atlante().get("by_team") or {}).get(str(tid))
    if not isinstance(blocco, dict):
        return None
    bucket = blocco.get("def_goals_per_match_by_bucket")
    if not isinstance(bucket, dict) or not bucket:
        return None
    tot = 0.0
    visti = 0
    for v in bucket.values():
        if isinstance(v, (int, float)):
            tot += float(v)
            visti += 1
    return round(tot, 4) if visti else None


def scontri_diretti(id_a: Optional[str], id_b: Optional[str]) -> Optional[Dict[str, int]]:
    """{'incontri': n, 'pareggi_alti': k} dagli scontri diretti dell'atlante.

    None = la coppia non e' nell'atlante (meno di 3 incontri registrati): il
    dato non c'e', e non si inventa."""
    if id_a is None or id_b is None:
        return None
    try:
        a, b = int(id_a), int(id_b)
    except (TypeError, ValueError):
        return None
    blocco = (atlante().get("h2h_hint") or {}).get(f"{min(a, b)}-{max(a, b)}")
    if not isinstance(blocco, dict):
        return None
    punteggi = blocco.get("ft_scores_a_b")
    if not isinstance(punteggi, dict) or not punteggi:
        return None
    incontri = sum(int(v) for v in punteggi.values() if isinstance(v, (int, float)))
    if incontri <= 0:
        return None
    alti = sum(int(punteggi.get(s, 0) or 0) for s in PAREGGI_ALTI)
    return {"incontri": int(incontri), "pareggi_alti": int(alti)}


def hint(home: Any, away: Any) -> Optional[Dict[str, Any]]:
    """Il blocco `selection_hint` della riga di scan, o None se non c'e' NULLA.

    Forma (chiavi stabili, lette dai due motori):

        {"fonte": "hazard_atlas_v2",
         "h2h_meetings": 14, "h2h_big_draws": 1,        # None se coppia assente
         "conceded": {"home": 1.21, "away": None}}      # gol subiti per partita

    Un campo a None vuol dire DATO ASSENTE: il motore lo dichiara e non lo
    scambia mai per uno zero."""
    chiave = (_normalizza(home), _normalizza(away))
    if not chiave[0] and not chiave[1]:
        return None
    if chiave in _HINT_CACHE:
        return _HINT_CACHE[chiave]
    id_h, id_a = team_id(home), team_id(away)
    h2h = scontri_diretti(id_h, id_a)
    dif_h, dif_a = gol_subiti_per_partita(id_h), gol_subiti_per_partita(id_a)
    out: Optional[Dict[str, Any]]
    if h2h is None and dif_h is None and dif_a is None:
        out = None
    else:
        out = {
            "fonte": FONTE,
            "h2h_meetings": None if h2h is None else h2h["incontri"],
            "h2h_big_draws": None if h2h is None else h2h["pareggi_alti"],
            "conceded": {"home": dif_h, "away": dif_a},
        }
    if len(_HINT_CACHE) > _CACHE_MAX:
        _HINT_CACHE.clear()
    _HINT_CACHE[chiave] = out
    return out


# ===========================================================================
# D5 (decisioni dell'utente 25/09) - LA SCHEDA DELLA FIXTURE DAL DATABASE
# ===========================================================================
# Punto 5: «hai il DATABASE con gli H2H di quelle specifiche squadre, quindi
# deve essere affidabile». Punto 6: «forze attacco/difesa: OK la fonte della
# Dashboard». Punto 1: le FINALI si riconoscono dal round della fixture.
#
# Da qui in avanti lo scanner NON pubblica piu' `hint()` (atlante, per NOME):
# pubblica la SCHEDA della fixture abbinata, dal DB, con le STESSE fonti che
# la Dashboard mostra (`pages/Dashboard.tsx:50-58` legge
# `fixture_predictions.raw_json`, `lib/normalizePrediction.ts`):
#   * scontri diretti: `raw_json.response[0].h2h` («STORICO H2H»);
#   * forze attacco/difesa: `raw_json.response[0].comparison.att/def`
#     («CONFRONTO DIRETTO», voci «Attacco»/«Difesa»);
#   * gol subiti: `raw_json.response[0].teams.<lato>.last_5.goals.against.average`;
#   * round: `matches.raw_json->league->>round` (la tabella delle fixture di
#     API-Football: `fixture_predictions` il round non lo ha).
#
# LETTURE (leggere, dichiarate; nessuna scrittura):
#   1. la finestra di fixture ±12 h, UNA query ogni 10 minuti per tutti gli
#      eventi (`omega_db.fixtures_for_window`, la stessa del matcher di Omega e
#      della catena lambda del bot);
#   2. per le fixture NUOVE abbinate in un giro: UNA query a blocchi di 40 su
#      `fixture_predictions` (sole proiezioni JSON, non l'intero raw_json) e
#      UNA su `matches` (solo il round). La scheda di una fixture si legge UNA
#      volta sola per partita e resta in cache per l'evento.
# ABBINAMENTO: il matcher money-critical dello stack
# (`Betfair.betfair_match.resolve_matches`, lo stesso di Omega e della catena
# lambda del bot), niente ripiego fuzzy: meglio «dato assente» che la scheda di
# un'altra partita. L'orientamento (casa/ospite di Betfair contro quelli di
# API-Football) si decide dai nomi: se e' invertito i lati si scambiano.

FONTE_DB = "fixture_predictions.raw_json"
STATI_FINITI = ("FT", "AET", "PEN")
GOL_TANTI = 4                   # «partita da tanti gol»: 4 o piu' a fine partita
_FINESTRA_TTL_S = 600.0         # finestra fixture riletta ogni 10 minuti
_FINESTRA_ORE = 12
_BLOCCO_ID = 40                 # fixture_id per SELECT (URL mai troppo lunga)
_ERRORE_PAUSA_S = 60.0          # dopo un errore del DB si riprova fra 60 s
_MAX_EVENTI = 3000


def _num_testo(v: Any) -> Optional[float]:
    """"0.8" / 0.8 / "62.8%" -> float; None se non e' un numero."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().rstrip("%").strip())
        except ValueError:
            return None
    return None


def conta_scontri_diretti(h2h: Any, escludi_fixture: Optional[int] = None
                          ) -> Optional[Dict[str, int]]:
    """{'incontri': N, 'tanti_gol': X} dalla lista h2h di API-Football.

    Contano solo le partite FINITE (FT/AET/PEN) con il punteggio a fine
    tempi regolamentari (`score.fulltime`; se manca, `goals`). None se la
    lista non c'e' (dato assente); {'incontri': 0, ...} se c'e' ma e' vuota."""
    if not isinstance(h2h, list):
        return None
    incontri = tanti = 0
    for m in h2h:
        if not isinstance(m, dict):
            continue
        fx = m.get("fixture") if isinstance(m.get("fixture"), dict) else {}
        if escludi_fixture is not None and fx.get("id") == escludi_fixture:
            continue
        stato = fx.get("status") if isinstance(fx.get("status"), dict) else {}
        if str(stato.get("short") or "").upper() not in STATI_FINITI:
            continue
        score = m.get("score") if isinstance(m.get("score"), dict) else {}
        ft = score.get("fulltime") if isinstance(score.get("fulltime"), dict) else {}
        gh, ga = ft.get("home"), ft.get("away")
        if not (isinstance(gh, int) and isinstance(ga, int)):
            goals = m.get("goals") if isinstance(m.get("goals"), dict) else {}
            gh, ga = goals.get("home"), goals.get("away")
        if not (isinstance(gh, int) and isinstance(ga, int)) or isinstance(gh, bool):
            continue
        incontri += 1
        if gh + ga >= GOL_TANTI:
            tanti += 1
    return {"incontri": incontri, "tanti_gol": tanti}


def _forze(cmp: Any, invertita: bool) -> Optional[Dict[str, Dict[str, float]]]:
    if not isinstance(cmp, dict):
        return None
    out: Dict[str, Dict[str, float]] = {}
    for chiave in ("att", "def"):
        blk = cmp.get(chiave)
        if not isinstance(blk, dict):
            return None
        casa, ospite = _num_testo(blk.get("home")), _num_testo(blk.get("away"))
        if casa is None or ospite is None:
            return None
        out[chiave] = ({"home": ospite, "away": casa} if invertita
                       else {"home": casa, "away": ospite})
    return out


def _subiti(last5: Any) -> Optional[float]:
    if not isinstance(last5, dict):
        return None
    goals = last5.get("goals") if isinstance(last5.get("goals"), dict) else {}
    contro = goals.get("against") if isinstance(goals.get("against"), dict) else {}
    return _num_testo(contro.get("average"))


def hint_da_scheda(scheda: Optional[Dict[str, Any]], invertita: bool = False
                   ) -> Optional[Dict[str, Any]]:
    """Il blocco `selection_hint` della riga di scan dalla SCHEDA del DB.

    ``scheda`` = riga della proiezione di `fixture_predictions`
    (`db.load_schede_fixture`): {"fixture_id", "h2h", "cmp", "last5_home",
    "last5_away"}. ``invertita`` = casa/ospite di Betfair sono l'ospite/casa
    di API-Football. None se non c'e' NULLA di utilizzabile.

        {"fonte": "fixture_predictions.raw_json", "fixture_id": 123,
         "h2h_meetings": 8, "h2h_many_goals": 2,
         "conceded": {"home": 0.8, "away": 1.6},
         "forze": {"att": {"home": 45.0, "away": 55.0}, "def": {...}}}
    """
    if not isinstance(scheda, dict):
        return None
    fid = scheda.get("fixture_id")
    conto = conta_scontri_diretti(scheda.get("h2h"), escludi_fixture=fid)
    sub_casa, sub_ospite = _subiti(scheda.get("last5_home")), _subiti(scheda.get("last5_away"))
    if invertita:
        sub_casa, sub_ospite = sub_ospite, sub_casa
    forze = _forze(scheda.get("cmp"), invertita)
    if conto is None and sub_casa is None and sub_ospite is None and forze is None:
        return None
    return {
        "fonte": FONTE_DB,
        "fixture_id": fid,
        "h2h_meetings": None if conto is None else conto["incontri"],
        "h2h_many_goals": None if conto is None else conto["tanti_gol"],
        "conceded": {"home": sub_casa, "away": sub_ospite},
        "forze": forze,
    }


def _orientamento_invertito(nome_evento: str, fixture: Dict[str, Any]) -> bool:
    """True se casa/ospite di Betfair corrispondono a ospite/casa della fixture."""
    try:
        from thefuzz import fuzz

        from Betfair.betfair_match import normalize_name, split_event_name
    except Exception:  # noqa: BLE001 - senza matcher non si abbina nulla
        return False
    parti = split_event_name(nome_evento)
    if not parti:
        return False
    bh, ba = normalize_name(parti[0]), normalize_name(parti[1])
    fh = normalize_name(fixture.get("home_team_name") or "")
    fa = normalize_name(fixture.get("away_team_name") or "")
    diretto = fuzz.token_set_ratio(bh, fh) + fuzz.token_set_ratio(ba, fa)
    invertito = fuzz.token_set_ratio(bh, fa) + fuzz.token_set_ratio(ba, fh)
    return invertito > diretto


class SchedeFixture:
    """Le schede DB delle partite monitorate dallo scanner (cache per evento).

    Le tre letture sono INIETTATE (i test passano finti con le chiavi vere):
      * ``leggi_finestra(lo_iso, hi_iso)`` -> righe fixture 'light'
        (`fixture_id, home_team_name, away_team_name, fixture_date, ...`);
      * ``leggi_schede([fixture_id])`` -> {fixture_id: scheda | None};
      * ``leggi_round([fixture_id])`` -> {fixture_id: round | None}.
    Mai eccezioni verso lo scanner: un DB che non risponde = dato assente.
    """

    def __init__(self, leggi_finestra: Any = None, leggi_schede: Any = None,
                 leggi_round: Any = None, orologio: Any = None) -> None:
        import time as _time

        self._leggi_finestra = leggi_finestra
        self._leggi_schede = leggi_schede
        self._leggi_round = leggi_round
        self._orologio = orologio or _time.monotonic
        self._finestra: List[Dict[str, Any]] = []
        self._finestra_ts: Optional[float] = None
        self._abbinati: Dict[str, Tuple[int, bool]] = {}
        self._tentati: Dict[str, float] = {}
        self._schede: Dict[int, Optional[Dict[str, Any]]] = {}
        self._round: Dict[int, Optional[str]] = {}
        self._pausa_fino: float = 0.0
        self.letture = 0          # quante SELECT ha fatto (misura, per i test)

    # ---------------------------------------------------------------- lettura
    def _fixture_di(self, event_id: Any) -> Optional[Tuple[int, bool]]:
        return self._abbinati.get(str(event_id))

    def hint(self, event_id: Any) -> Optional[Dict[str, Any]]:
        ab = self._fixture_di(event_id)
        if ab is None:
            return None
        return hint_da_scheda(self._schede.get(ab[0]), invertita=ab[1])

    def round(self, event_id: Any) -> Optional[str]:
        ab = self._fixture_di(event_id)
        if ab is None:
            return None
        r = self._round.get(ab[0])
        return r.strip() or None if isinstance(r, str) else None

    # ----------------------------------------------------------- aggiornamento
    def aggiorna(self, eventi: List[Dict[str, Any]], now: Any) -> int:
        """Abbina gli eventi nuovi e legge le schede delle fixture nuove.

        ``eventi`` = [{"event_id", "event_name", "open_date"}] (solo calcio).
        Ritorna quante fixture nuove sono state lette. Mai eccezioni."""
        try:
            return self._aggiorna(eventi, now)
        except Exception as ex:  # noqa: BLE001 - lo scanner non si ferma mai
            logger.warning("[safe-selezione] schede DB KO: %s", str(ex)[:160])
            self._pausa_fino = self._orologio() + _ERRORE_PAUSA_S
            return 0

    def _aggiorna(self, eventi: List[Dict[str, Any]], now: Any) -> int:
        from datetime import timedelta

        adesso = self._orologio()
        if adesso < self._pausa_fino or not eventi:
            return 0
        if self._finestra_ts is None or adesso - self._finestra_ts >= _FINESTRA_TTL_S:
            if callable(self._leggi_finestra):
                lo = (now - timedelta(hours=_FINESTRA_ORE)).isoformat()
                hi = (now + timedelta(hours=_FINESTRA_ORE)).isoformat()
                self.letture += 1
                righe = self._leggi_finestra(lo, hi) or []
                self._finestra = [r for r in righe if isinstance(r, dict)]
            self._finestra_ts = adesso
        # abbinamento: una volta per evento e per finestra (un evento non
        # abbinato si riprova quando la finestra si rinnova: la fixture puo'
        # arrivare dopo)
        da_abbinare = [e for e in eventi
                       if str(e.get("event_id")) not in self._abbinati
                       and self._tentati.get(str(e.get("event_id"))) != self._finestra_ts]
        if da_abbinare and self._finestra:
            self._abbina(da_abbinare)
        for e in da_abbinare:
            self._tentati[str(e.get("event_id"))] = self._finestra_ts
        # schede e round delle fixture NUOVE: una query a blocchi per giro
        vivi = {str(e.get("event_id")) for e in eventi}
        nuove = sorted({ab[0] for eid, ab in self._abbinati.items()
                        if eid in vivi and ab[0] not in self._schede})
        for i in range(0, len(nuove), _BLOCCO_ID):
            blocco = nuove[i:i + _BLOCCO_ID]
            schede = self._leggi(self._leggi_schede, blocco)
            rounds = self._leggi(self._leggi_round, blocco)
            for fid in blocco:
                self._schede[fid] = schede.get(fid)
                self._round[fid] = rounds.get(fid)
        self._pota(vivi)
        return len(nuove)

    def _leggi(self, fn: Any, blocco: List[int]) -> Dict[int, Any]:
        if not callable(fn):
            return {}
        self.letture += 1
        out = fn(blocco) or {}
        return {int(k): v for k, v in out.items()} if isinstance(out, dict) else {}

    def _abbina(self, eventi: List[Dict[str, Any]]) -> None:
        try:
            from Betfair.betfair_match import load_name_map, resolve_matches
        except Exception as ex:  # noqa: BLE001 - senza matcher: dato assente
            logger.warning("[safe-selezione] matcher non disponibile: %s", str(ex)[:120])
            return
        evs = [{"id": str(e.get("event_id")), "name": str(e.get("event_name") or ""),
                "openDate": e.get("open_date")} for e in eventi]
        matched, _ = resolve_matches(evs, self._finestra, name_map=load_name_map(),
                                     time_tolerance_min=6 * 60)
        for m in matched:
            fx = m.get("fixture") or {}
            fid = fx.get("fixture_id")
            if fid is None:
                continue
            ev = m.get("event") or {}
            self._abbinati[str(ev.get("id"))] = (
                int(fid), _orientamento_invertito(str(ev.get("name") or ""), fx))

    def _pota(self, vivi: set) -> None:
        if len(self._abbinati) + len(self._tentati) <= _MAX_EVENTI:
            return
        self._abbinati = {k: v for k, v in self._abbinati.items() if k in vivi}
        self._tentati = {k: v for k, v in self._tentati.items() if k in vivi}
        usati = {ab[0] for ab in self._abbinati.values()}
        self._schede = {k: v for k, v in self._schede.items() if k in usati}
        self._round = {k: v for k, v in self._round.items() if k in usati}
