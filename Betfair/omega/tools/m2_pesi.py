# -*- coding: utf-8 -*-
"""m2_pesi - STUDIO DEI DATI E TARATURA DEI PESI delle INTENSITA' PRE-PARTITA (Omega M2).

Ordine dell'utente (17/09/2026): «il bot deve sapere i dati storici: frequenze di
mercato, ritardi, h2h, dati storici di lega e delle squadre, trovi tutto in
dashboard per quella specifica partita; deve sfruttare la potenza dei dati che si
aggiornano automaticamente partita dopo partita; NON sono presenti tutti i dati per
tutte le partite, quindi studia o fai una simulazione su una partita per tarare i
pesi correttamente».

COSA FA: per ogni partita costruisce (lambda_casa, lambda_trasferta, cv, fonti, pesi)
fondendo TUTTE le fonti disponibili con un pool logaritmico a pesi, e DEGRADANDO con
grazia quando una fonte manca: meno fonti -> cv piu' largo -> coda piu' grassa ->
limite superiore di p piu' alto -> il motore v4 chiede un prezzo migliore e fa meno
ingressi. La prudenza non e' una soglia scritta a mano: e' una conseguenza.

COSA NON FA: non tocca il motore di produzione, non scrive sul database, non chiama
Betfair, non avvia processi. E' un banco di misura in sola lettura.

METODO (antidoto alla maledizione dell'ottimizzatore, gia' costata -6,1 % / -5,3 % /
-8,0 % / -3,5 % in questo repo):
  * SPLIT TEMPORALE: i pesi si stimano sulle settimane VECCHIE e si misurano sulle
    settimane NUOVE, mai sulle stesse.
  * BOOTSTRAP a grappolo sulle partite per l'intervallo della DIFFERENZA rispetto al
    solo mercato: un peso che non migliora con IC che esclude 0 vale ZERO e lo si
    dichiara.
  * BASELINE ONESTE: (a) solo mercato devigato, (b) solo fixture_predictions,
    (c) la catena attuale di ``omega_service._prematch_lambdas``.

USO
    python -m Betfair.omega.tools.m2_pesi estrai        # scarica il campione (sola lettura)
    python -m Betfair.omega.tools.m2_pesi copertura     # tabella di copertura misurata
    python -m Betfair.omega.tools.m2_pesi tara          # stima + prova fuori campione + bootstrap
    python -m Betfair.omega.tools.m2_pesi simula --fixture <id>
    python -m Betfair.omega.tools.m2_pesi hazard        # hazard di gol per lega/minuto/punteggio

Scrive SOLO file locali:
    Betfair/omega/data/m2_campione_2026-09-17.json.gz   (cache del campione)
    Betfair/omega/data/pesi_m2_2026-09-17.json          (i pesi e i numeri OOS)
    Betfair/omega/data/m2_copertura_2026-09-17.json
    Betfair/omega/data/m2_hazard_2026-09-17.json
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import math
import os
import random
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.getcwd())

from Betfair.omega import omega_model as M   # noqa: E402  (produzione: nessuna copia di laboratorio)

DATA = os.path.join("Betfair", "omega", "data")
F_CAMPIONE = os.path.join(DATA, "m2_campione_2026-09-17.json.gz")
F_PESI = os.path.join(DATA, "pesi_m2_2026-09-17.json")
F_COPERTURA = os.path.join(DATA, "m2_copertura_2026-09-17.json")
F_HAZARD = os.path.join(DATA, "m2_hazard_2026-09-17.json")

# Finestra di riferimento per la COPERTURA (ultime 4 settimane, ordine dell'utente).
COP_DA, COP_A = "2026-08-20", "2026-09-18"
# Lo SPLIT TEMPORALE del campione con le quote: il buco fra il 22/07 e il 31/08 e'
# reale (nessuna cattura di quote), quindi separa i due insiemi senza ambiguita'.
SPLIT = "2026-07-25"

MAX_GOALS = 8          # griglia del risultato esatto (coerente con omega_model)
MAX_GOALS_HT = 6
RHO = M.DEFAULT_RHO    # ro Dixon-Coles di default, come la produzione

# Le FONTI, in ordine di forza attesa. Il nome e' quello che finisce nell'audit.
FONTI = ("mercato", "fixture", "tattico", "api", "forza", "forma", "h2h", "lega")


# ---------------------------------------------------------------------------
# lettura (sola lettura, a pagine: il database respira - Costituzione §20)
# ---------------------------------------------------------------------------
def _sb():
    from db_client import get_supabase_client   # import tardivo: il modulo resta puro
    return get_supabase_client()


def _pagina(sb, tab: str, sel: str, filtri, ordine: Sequence[str], limite: int = 1000) -> List[dict]:
    """Pagine con ORDINE TOTALE (piu' colonne): con un ordine ambiguo l'offset salta
    e duplica righe in silenzio - misurato qui il 17/09 (2.003 fixture invece di 2.018)."""
    fuori, off = [], 0
    while True:
        q = sb.table(tab).select(sel)
        for f in filtri:
            q = f(q)
        for c in ordine:
            q = q.order(c)
        righe = getattr(q.range(off, off + limite - 1).execute(), "data", None) or []
        fuori.extend(righe)
        if len(righe) < limite:
            return fuori
        off += limite


def _a_blocchi(sb, tab: str, sel: str, colonna: str, valori: Sequence[Any],
               blocco: int = 300, filtri=()) -> List[dict]:
    fuori: List[dict] = []
    v = sorted(set(valori))
    for i in range(0, len(v), blocco):
        q = sb.table(tab).select(sel).in_(colonna, v[i:i + blocco])
        for f in filtri:
            q = f(q)
        fuori.extend(getattr(q.execute(), "data", None) or [])
    return fuori


def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def _prezzo(livelli: Any) -> Optional[float]:
    """Miglior prezzo dal blocco JSONB [{price,size}, ...]."""
    if not isinstance(livelli, list) or not livelli:
        return None
    try:
        p = float(livelli[0].get("price"))
    except (TypeError, ValueError, AttributeError):
        return None
    return p if math.isfinite(p) and p > 1.0 else None


# ---------------------------------------------------------------------------
# ESTRAZIONE del campione
# ---------------------------------------------------------------------------
SEL_FP = ("fixture_id,league_id,fixture_date,home_team_id,away_team_id,updated_at,"
          "lh:db_json_analisi->inputs->>lambda_home,"
          "la:db_json_analisi->inputs->>lambda_away,"
          "tlh:tactical_engine_json->>lambda_home,"
          "tla:tactical_engine_json->>lambda_away,"
          "l1h:ht_predictions->>lambda_1h,"
          "ph:percent_home,pd:percent_draw,pa:percent_away,"
          "h2h:raw_json->response->0->h2h")
SEL_MATCH = ("fixture_id,league_id,season_year,fixture_date,status_short,"
             "goals_home,goals_away,halftime_home,halftime_away,"
             "home_team_id,away_team_id")


def estrai(storico_da: str = "2025-06-01") -> dict:
    """Scarica il campione: partite con quote Betfair PRE-MATCH + esito + fonti.

    Il campione di TARATURA e' vincolato dalle quote: ``betfair_market_odds``
    esiste solo per 2.018 fixture (24/06 - 11/09/2026). E' il prezzo da pagare per
    poter confrontare qualunque fonte CONTRO il mercato, che e' la baseline.
    """
    sb = _sb()
    quote = _pagina(sb, "betfair_market_odds",
                    "fixture_id,selection,sort_priority,back,lay,run_date",
                    [lambda q: q.eq("market_name", "Match Odds")], ("fixture_id", "selection"))
    per_fix: Dict[int, dict] = {}
    for r in quote:
        fid = int(r["fixture_id"])
        d = per_fix.setdefault(fid, {"fixture_id": fid, "run_date": r.get("run_date")})
        sp = r.get("sort_priority")
        lato = {1: "home", 2: "away", 3: "draw"}.get(int(sp) if sp is not None else 0)
        if lato:
            d[f"back_{lato}"] = _prezzo(r.get("back"))
            d[f"lay_{lato}"] = _prezzo(r.get("lay"))
    fids = sorted(per_fix)
    esiti = {int(r["fixture_id"]): r for r in
             _a_blocchi(sb, "matches", SEL_MATCH, "fixture_id", fids)}
    fp = {int(r["fixture_id"]): r for r in
          _a_blocchi(sb, "fixture_predictions", SEL_FP, "fixture_id", fids)}
    leghe = sorted({int(r["league_id"]) for r in esiti.values() if r.get("league_id") is not None})

    # storico per forza/forma/h2h: SOLO le leghe coinvolte, dal ``storico_da``
    storico: List[dict] = []
    for i in range(0, len(leghe), 20):
        storico.extend(_pagina(
            sb, "matches", SEL_MATCH,
            [lambda q, c=leghe[i:i + 20]: q.in_("league_id", c),
             lambda q: q.gte("fixture_date", storico_da),
             lambda q: q.lt("fixture_date", COP_A)], ("fixture_date", "fixture_id")))
    camp = {
        "generato": "2026-09-17",
        "finestra_quote": [min(x.get("run_date") or "" for x in per_fix.values()),
                           max(x.get("run_date") or "" for x in per_fix.values())],
        "storico_da": storico_da,
        "quote": list(per_fix.values()),
        "esiti": list(esiti.values()),
        "fixture_predictions": list(fp.values()),
        "storico": storico,
        "leghe": leghe,
    }
    os.makedirs(DATA, exist_ok=True)
    with gzip.open(F_CAMPIONE, "wt", encoding="utf-8") as fh:
        json.dump(camp, fh)
    print(f"campione: {len(per_fix)} fixture con quote, {len(esiti)} esiti, "
          f"{len(fp)} fixture_predictions, {len(storico)} partite di storico, "
          f"{len(leghe)} leghe -> {F_CAMPIONE}")
    return camp


def carica_campione() -> dict:
    if not os.path.exists(F_CAMPIONE):
        raise SystemExit(f"manca {F_CAMPIONE}: lancia prima "
                         f"'python -m Betfair.omega.tools.m2_pesi estrai'")
    with gzip.open(F_CAMPIONE, "rt", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# FORZA DELLE SQUADRE (Maher 1982 / Dixon-Coles 1997), stimata SOLO su partite
# ANTERIORI al taglio: e' la difesa contro il leakage temporale.
# ---------------------------------------------------------------------------
EMIVITA_GIORNI = 180.0
PSEUDO_PARTITE = 4.0       # shrinkage verso la media di lega (att/dif = 0)
GIRI_FIT = 60


def _giorni(a: str, b: str) -> float:
    from datetime import datetime
    def p(s):
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return (p(b) - p(a)).total_seconds() / 86400.0


class ForzaSquadre:
    """attacco/difesa per squadra + media e vantaggio casa per LEGA.

    log lam_casa = mu_lega + casa_lega + att[casa] + dif[trasferta]
    log lam_tras = mu_lega            + att[tras]  + dif[casa]
    Stima a punto fisso con pesi a decadimento esponenziale (emivita
    ``EMIVITA_GIORNI``) e shrinkage verso lo zero di lega (``PSEUDO_PARTITE``):
    una squadra con 3 partite pesa poco, una con 40 pesa molto.
    """

    def __init__(self, partite: Sequence[dict], taglio: str) -> None:
        self.taglio = taglio
        self.mu: Dict[int, float] = {}
        self.casa: Dict[int, float] = {}
        self.att: Dict[int, float] = {}
        self.dif: Dict[int, float] = {}
        self.n_squadra: Dict[int, float] = {}
        self._fit([p for p in partite if str(p.get("fixture_date") or "") < taglio
                   and str(p.get("status_short") or "").upper() in ("FT", "AET", "PEN")
                   and p.get("goals_home") is not None and p.get("goals_away") is not None])

    def _fit(self, partite: Sequence[dict]) -> None:
        per_lega: Dict[int, List[dict]] = collections.defaultdict(list)
        for p in partite:
            try:
                per_lega[int(p["league_id"])].append(p)
            except (TypeError, ValueError, KeyError):
                continue
        for lega, righe in per_lega.items():
            w = {}
            for p in righe:
                try:
                    eta = _giorni(p["fixture_date"], self.taglio)
                except Exception:      # noqa: BLE001  (data non parsabile: peso pieno)
                    eta = 0.0
                w[id(p)] = 0.5 ** (max(0.0, eta) / EMIVITA_GIORNI)
            tot_w = sum(w.values())
            if tot_w < 5.0:
                continue
            gh = sum(w[id(p)] * float(p["goals_home"]) for p in righe)
            ga = sum(w[id(p)] * float(p["goals_away"]) for p in righe)
            if gh <= 0 or ga <= 0:
                continue
            mu = math.log(ga / tot_w)                  # media TRASFERTA = riferimento
            casa = math.log(gh / tot_w) - mu
            squadre = sorted({int(p["home_team_id"]) for p in righe if p.get("home_team_id")}
                             | {int(p["away_team_id"]) for p in righe if p.get("away_team_id")})
            att = {t: 0.0 for t in squadre}
            dif = {t: 0.0 for t in squadre}
            npart = {t: 0.0 for t in squadre}
            for p in righe:
                h, a = p.get("home_team_id"), p.get("away_team_id")
                if h in npart:
                    npart[int(h)] += w[id(p)]
                if a in npart:
                    npart[int(a)] += w[id(p)]
            for _ in range(GIRI_FIT):
                segn = {t: 0.0 for t in squadre}
                atte = {t: 0.0 for t in squadre}
                for p in righe:
                    h, a, ww = int(p["home_team_id"]), int(p["away_team_id"]), w[id(p)]
                    if h not in att or a not in att:
                        continue
                    segn[h] += ww * float(p["goals_home"])
                    segn[a] += ww * float(p["goals_away"])
                    atte[h] += ww * math.exp(mu + casa + dif[a])
                    atte[a] += ww * math.exp(mu + dif[h])
                for t in squadre:
                    k = PSEUDO_PARTITE
                    base = math.exp(mu) * k
                    if atte[t] + base > 0:
                        att[t] = math.log(max(1e-6, segn[t] + base) / (atte[t] + base))
                    att[t] = max(-1.5, min(1.5, att[t]))
                subi = {t: 0.0 for t in squadre}
                atte = {t: 0.0 for t in squadre}
                for p in righe:
                    h, a, ww = int(p["home_team_id"]), int(p["away_team_id"]), w[id(p)]
                    if h not in att or a not in att:
                        continue
                    subi[h] += ww * float(p["goals_away"])
                    subi[a] += ww * float(p["goals_home"])
                    atte[h] += ww * math.exp(mu + att[a])
                    atte[a] += ww * math.exp(mu + casa + att[h])
                for t in squadre:
                    k = PSEUDO_PARTITE
                    base = math.exp(mu) * k
                    if atte[t] + base > 0:
                        dif[t] = math.log(max(1e-6, subi[t] + base) / (atte[t] + base))
                    dif[t] = max(-1.5, min(1.5, dif[t]))
            self.mu[lega] = mu
            self.casa[lega] = casa
            self.att.update({t: att[t] for t in squadre})
            self.dif.update({t: dif[t] for t in squadre})
            self.n_squadra.update({t: npart[t] for t in squadre})

    def lambdas(self, lega: Optional[int], casa_id: Optional[int], tras_id: Optional[int]
                ) -> Optional[Tuple[float, float, float]]:
        """(lam_casa, lam_tras, n_effettivo minimo delle due squadre) o None."""
        try:
            lg = int(lega)
        except (TypeError, ValueError):
            return None
        if lg not in self.mu or casa_id is None or tras_id is None:
            return None
        h, a = int(casa_id), int(tras_id)
        if h not in self.att or a not in self.att:
            return None
        n = min(self.n_squadra.get(h, 0.0), self.n_squadra.get(a, 0.0))
        if n < 2.0:
            return None
        lh = math.exp(self.mu[lg] + self.casa[lg] + self.att[h] + self.dif[a])
        la = math.exp(self.mu[lg] + self.att[a] + self.dif[h])
        return lh, la, n

    def lambdas_lega(self, lega: Optional[int]) -> Optional[Tuple[float, float]]:
        try:
            lg = int(lega)
        except (TypeError, ValueError):
            return None
        if lg not in self.mu:
            return None
        return math.exp(self.mu[lg] + self.casa[lg]), math.exp(self.mu[lg])


# ---------------------------------------------------------------------------
# FORMA recente e H2H - sempre e solo su partite ANTERIORI alla partita stessa
# ---------------------------------------------------------------------------
FORMA_N = 6          # ultime N partite
FORMA_K = 4.0        # pseudo-partite di shrinkage verso la media di lega
H2H_K = 3.0          # pseudo-incontri di shrinkage verso la media di lega


class Storico:
    """Indice delle partite passate, per squadra e per coppia."""

    def __init__(self, partite: Sequence[dict]) -> None:
        self.per_squadra: Dict[int, List[dict]] = collections.defaultdict(list)
        self.per_coppia: Dict[Tuple[int, int], List[dict]] = collections.defaultdict(list)
        for p in partite:
            if str(p.get("status_short") or "").upper() not in ("FT", "AET", "PEN"):
                continue
            if p.get("goals_home") is None or p.get("goals_away") is None:
                continue
            h, a = p.get("home_team_id"), p.get("away_team_id")
            if h is None or a is None:
                continue
            h, a = int(h), int(a)
            self.per_squadra[h].append(p)
            self.per_squadra[a].append(p)
            self.per_coppia[(min(h, a), max(h, a))].append(p)
        for v in self.per_squadra.values():
            v.sort(key=lambda p: str(p.get("fixture_date") or ""))
        for v in self.per_coppia.values():
            v.sort(key=lambda p: str(p.get("fixture_date") or ""))

    def forma(self, team: Optional[int], prima_di: str) -> Optional[Tuple[float, float, int]]:
        """(gol fatti, gol subiti, n) nelle ultime FORMA_N partite prima di ``prima_di``."""
        if team is None:
            return None
        righe = [p for p in self.per_squadra.get(int(team), ())
                 if str(p.get("fixture_date") or "") < prima_di][-FORMA_N:]
        if not righe:
            return None
        fatti = subiti = 0.0
        for p in righe:
            if int(p["home_team_id"]) == int(team):
                fatti += float(p["goals_home"]); subiti += float(p["goals_away"])
            else:
                fatti += float(p["goals_away"]); subiti += float(p["goals_home"])
        n = len(righe)
        return fatti / n, subiti / n, n

    def h2h(self, casa: Optional[int], tras: Optional[int], prima_di: str
            ) -> Optional[Tuple[float, float, int]]:
        """(gol medi della squadra di CASA di oggi, gol medi dell'altra, n incontri)."""
        if casa is None or tras is None:
            return None
        h, a = int(casa), int(tras)
        righe = [p for p in self.per_coppia.get((min(h, a), max(h, a)), ())
                 if str(p.get("fixture_date") or "") < prima_di]
        if not righe:
            return None
        gh = ga = 0.0
        for p in righe:
            if int(p["home_team_id"]) == h:
                gh += float(p["goals_home"]); ga += float(p["goals_away"])
            else:
                gh += float(p["goals_away"]); ga += float(p["goals_home"])
        n = len(righe)
        return gh / n, ga / n, n


# ---------------------------------------------------------------------------
# LE FONTI DI LAMBDA, una funzione per fonte. Tutte tornano (lam_casa, lam_tras)
# o None. Nessuna inventa un numero quando il dato manca: None vuol dire None.
# ---------------------------------------------------------------------------
def _mid(back: Optional[float], lay: Optional[float]) -> Optional[float]:
    """Quota EQUA a meta' spread: 1/p con p = media delle due implicite."""
    b, l = _f(back), _f(lay)
    if b is None and l is None:
        return None
    if b is None or l is None:
        return b if b is not None else l
    p = 0.5 * (1.0 / b + 1.0 / l)
    return 1.0 / p if p > 0 else None


def lam_mercato(q: dict, *, meta_spread: bool = True) -> Optional[Tuple[float, float]]:
    """lambda dalle quote 1X2 Betfair PRE-MATCH, con la STESSA funzione della
    produzione (``omega_model.lambdas_from_pre_ko``: devig proporzionale + gol
    totali dal PAREGGIO + split risolto sulla griglia)."""
    if meta_spread:
        pre = {"home": _mid(q.get("back_home"), q.get("lay_home")),
               "draw": _mid(q.get("back_draw"), q.get("lay_draw")),
               "away": _mid(q.get("back_away"), q.get("lay_away"))}
    else:
        pre = {"home": _f(q.get("back_home")), "draw": _f(q.get("back_draw")),
               "away": _f(q.get("back_away"))}
    if any(v is None for v in pre.values()):
        return None
    return M.lambdas_from_pre_ko(pre, rho=RHO)


def lam_fixture(fp: dict) -> Optional[Tuple[float, float]]:
    lh, la = _f(fp.get("lh")), _f(fp.get("la"))
    return (lh, la) if lh and la else None


def lam_tattico(fp: dict) -> Optional[Tuple[float, float]]:
    lh, la = _f(fp.get("tlh")), _f(fp.get("tla"))
    return (lh, la) if lh and la else None


def lam_api(fp: dict) -> Optional[Tuple[float, float]]:
    """lambda dalle percentuali 1X2 di API-Football (gia' normalizzate a 100)."""
    # chiavi VERE della colonna (``percent_home/draw/away``) o alias del campione
    ph = _f(fp.get("percent_home") if fp.get("percent_home") is not None else fp.get("ph"))
    pd = _f(fp.get("percent_draw") if fp.get("percent_draw") is not None else fp.get("pd"))
    pa = _f(fp.get("percent_away") if fp.get("percent_away") is not None else fp.get("pa"))
    if ph is None or pd is None or pa is None:
        return None
    tot = ph + pd + pa
    if tot <= 0:
        return None
    ph, pa = ph / tot, pa / tot
    if not (0.02 < 1.0 - ph - pa < 0.8):
        return None
    tg = M.total_goals_from_1x2(ph, pa, RHO)
    return M.split_lambdas_1x2(ph, pa, tg, RHO)


def lam_forza(forza: ForzaSquadre, e: dict) -> Optional[Tuple[float, float]]:
    r = forza.lambdas(e.get("league_id"), e.get("home_team_id"), e.get("away_team_id"))
    return (r[0], r[1]) if r else None


def lam_lega(forza: ForzaSquadre, e: dict) -> Optional[Tuple[float, float]]:
    return forza.lambdas_lega(e.get("league_id"))


def lam_forma(st: Storico, forza: ForzaSquadre, e: dict) -> Optional[Tuple[float, float]]:
    """La forma recente, ancorata alla media di LEGA: non e' un lambda autonomo,
    e' un moltiplicatore (gol fatti dalla casa x gol subiti dalla trasferta)."""
    base = forza.lambdas_lega(e.get("league_id"))
    if base is None:
        return None
    data = str(e.get("fixture_date") or "")
    fh = st.forma(e.get("home_team_id"), data)
    fa = st.forma(e.get("away_team_id"), data)
    if fh is None or fa is None:
        return None
    mh, ma = base
    med = 0.5 * (mh + ma)
    if med <= 0:
        return None
    def _sh(v: float, n: int) -> float:
        return (v * n + med * FORMA_K) / (n + FORMA_K)
    att_h, sub_h = _sh(fh[0], fh[2]), _sh(fh[1], fh[2])
    att_a, sub_a = _sh(fa[0], fa[2]), _sh(fa[1], fa[2])
    lh = mh * (att_h / med) * (sub_a / med)
    la = ma * (att_a / med) * (sub_h / med)
    return (lh, la) if lh > 0 and la > 0 else None


def lam_h2h(st: Storico, forza: ForzaSquadre, e: dict) -> Optional[Tuple[float, float]]:
    base = forza.lambdas_lega(e.get("league_id"))
    if base is None:
        return None
    r = st.h2h(e.get("home_team_id"), e.get("away_team_id"), str(e.get("fixture_date") or ""))
    if r is None:
        return None
    gh, ga, n = r
    mh, ma = base
    lh = (gh * n + mh * H2H_K) / (n + H2H_K)
    la = (ga * n + ma * H2H_K) / (n + H2H_K)
    return (lh, la) if lh > 0 and la > 0 else None


# ---------------------------------------------------------------------------
# FUSIONE GERARCHICA + INCERTEZZA DICHIARATA
# ---------------------------------------------------------------------------
# Pesi di partenza (prior della tesi del coordinatore, §3 VISIONE_OMEGA_V4): il
# mercato e' la fonte piu' forte, il resto deve DIMOSTRARE di aggiungere fuori
# campione. Sono solo il punto di partenza dell'ottimizzatore.
PESI_PRIOR = {"mercato": 1.00, "fixture": 0.30, "tattico": 0.20, "api": 0.15,
              "forza": 0.25, "forma": 0.10, "h2h": 0.05, "lega": 0.10}
CV_PRIOR = {"cv0": 0.22, "c_disp": 0.60, "c_mancanza": 0.30}
CV_MIN, CV_MAX = 0.10, 1.00


def fondi(fonti: Dict[str, Tuple[float, float]], pesi: Dict[str, float],
          cvp: Dict[str, float],
          pesi_ripiego: Optional[Dict[str, float]] = None) -> Optional[dict]:
    """Pool LOGARITMICO a pesi sulle fonti DISPONIBILI + incertezza dichiarata.

    log lam = somma(w_s * log lam_s) / somma(w_s)   sulle sole fonti presenti.
    Il peso mancante non si redistribuisce in silenzio: entra nel ``cv`` come
    ``c_mancanza * (1 - copertura)``. Meno fonti -> cv piu' largo -> coda piu'
    grassa -> p_sup piu' alto -> il motore chiede un prezzo migliore e opera
    meno. La prudenza e' una conseguenza, non una soglia scritta a mano.
    """
    ordine = list(FONTI) + sorted(k for k in fonti if k not in FONTI)
    usate = [(s, fonti[s], float(pesi.get(s, 0.0))) for s in ordine
             if s in fonti and fonti[s] and float(pesi.get(s, 0.0)) > 0.0]
    wall = sum(float(pesi.get(s, 0.0)) for s in ordine)
    ripiego = False
    if not usate and pesi_ripiego:
        # RIPIEGO: nessuna fonte con peso MISURATO (in pratica: manca il mercato).
        # Non si salta la partita e non si finge di saperne quanto prima: si usano
        # le fonti che restano con i pesi pre-ablazione, e la copertura crolla ->
        # il cv si allarga -> il motore chiede un prezzo migliore. E' la
        # degradazione con grazia, non un ripiego silenzioso.
        ripiego = True
        usate = [(s, fonti[s], float(pesi_ripiego.get(s, 0.0))) for s in ordine
                 if s in fonti and fonti[s] and float(pesi_ripiego.get(s, 0.0)) > 0.0]
        wall = wall + sum(float(pesi_ripiego.get(s, 0.0)) for s in ordine)
    if not usate:
        return None
    wtot = sum(w for _, _, w in usate)
    if wtot <= 0:
        return None
    lh = math.exp(sum(w * math.log(max(1e-3, v[0])) for _, v, w in usate) / wtot)
    la = math.exp(sum(w * math.log(max(1e-3, v[1])) for _, v, w in usate) / wtot)
    # dispersione fra le fonti (deviazione standard pesata dei log dei TOTALI)
    if len(usate) > 1:
        tot = [math.log(max(1e-3, v[0] + v[1])) for _, v, _ in usate]
        pes = [w for _, _, w in usate]
        med = sum(p * t for p, t in zip(pes, tot)) / wtot
        var = sum(p * (t - med) ** 2 for p, t in zip(pes, tot)) / wtot
        disp = math.sqrt(max(0.0, var))
    else:
        disp = 0.0
    copertura = wtot / wall if wall > 0 else 0.0
    cv = (float(cvp.get("cv0", 0.22))
          + float(cvp.get("c_disp", 0.6)) * disp
          + float(cvp.get("c_mancanza", 0.3)) * (1.0 - copertura))
    cv = max(CV_MIN, min(CV_MAX, cv))
    return {"lh": lh, "la": la, "cv": cv, "dispersione": disp, "copertura": copertura,
            "ripiego": ripiego,
            "fonti_usate": tuple(s for s, _, _ in usate),
            "pesi_usati": {s: round(w / wtot, 4) for s, _, w in usate}}


# ---------------------------------------------------------------------------
# METRICHE (log-loss / Brier sul RISULTATO ESATTO e sul totale gol)
# ---------------------------------------------------------------------------
def _cella(g: Optional[int], massimo: int) -> Optional[int]:
    if g is None:
        return None
    return max(0, min(int(massimo), int(g)))


def valuta(lh: float, la: float, cv: float, esito: dict) -> Optional[dict]:
    """log-loss/Brier del risultato esatto FT e HT e del totale gol, su UNA partita."""
    gh, ga = esito.get("goals_home"), esito.get("goals_away")
    if gh is None or ga is None:
        return None
    gft = M.residual_grid(lh, la, RHO, MAX_GOALS, dixon_coles=True, cv=cv)
    if not gft:
        return None
    cft = (_cella(gh, MAX_GOALS), _cella(ga, MAX_GOALS))
    p_ft = max(1e-12, gft.get(cft, 0.0))
    brier = sum((p - (1.0 if k == cft else 0.0)) ** 2 for k, p in gft.items())
    tot: Dict[int, float] = {}
    for (h, a), p in gft.items():
        tot[h + a] = tot.get(h + a, 0.0) + p
    p_tot = max(1e-12, tot.get(min(int(gh) + int(ga), 2 * MAX_GOALS), 0.0))
    out = {"ll_ft": -math.log(p_ft), "brier_ft": brier, "ll_tot": -math.log(p_tot),
           "p_ft": p_ft}
    hh, ha = esito.get("halftime_home"), esito.get("halftime_away")
    if hh is not None and ha is not None:
        q = M.ht_residual_share(0)
        ght = M.residual_grid(lh * q, la * q, RHO, MAX_GOALS_HT, dixon_coles=True, cv=cv)
        if ght:
            cht = (_cella(hh, MAX_GOALS_HT), _cella(ha, MAX_GOALS_HT))
            out["ll_ht"] = -math.log(max(1e-12, ght.get(cht, 0.0)))
            # calibrazione della CODA: celle sotto il 2 % (e' li' che Omega opera)
            att = sum(p for p in ght.values() if p <= 0.02)
            usc = 1.0 if ght.get(cht, 0.0) <= 0.02 else 0.0
            out["coda_ht_att"], out["coda_ht_usc"] = att, usc
    att = sum(p for p in gft.values() if p <= 0.02)
    out["coda_ft_att"] = att
    out["coda_ft_usc"] = 1.0 if gft.get(cft, 0.0) <= 0.02 else 0.0
    return out


def aggrega(voci: Sequence[dict]) -> dict:
    if not voci:
        return {}
    def media(k):
        v = [x[k] for x in voci if k in x]
        return sum(v) / len(v) if v else None
    out = {"n": len(voci), "ll_ft": media("ll_ft"), "ll_ht": media("ll_ht"),
           "brier_ft": media("brier_ft"), "ll_tot": media("ll_tot")}
    for per in ("ft", "ht"):
        att = sum(x.get(f"coda_{per}_att", 0.0) for x in voci if f"coda_{per}_att" in x)
        usc = sum(x.get(f"coda_{per}_usc", 0.0) for x in voci if f"coda_{per}_usc" in x)
        out[f"coda_{per}"] = (usc / att) if att > 0 else None
        out[f"coda_{per}_attese"] = att
        out[f"coda_{per}_uscite"] = usc
    return out


# ---------------------------------------------------------------------------
# COSTRUZIONE DEL CAMPIONE DI TARATURA
# ---------------------------------------------------------------------------
TAGLIO_FORZA_TRAIN = "2026-06-24"      # prima della PRIMA partita dell'insieme di stima


def costruisci(camp: dict) -> List[dict]:
    """Una riga per partita con TUTTE le lambda delle fonti disponibili + esito.

    Niente leakage: la forza delle squadre e' stimata su partite anteriori al
    taglio del proprio insieme, forma e h2h su partite anteriori alla partita.
    """
    quote = {int(q["fixture_id"]): q for q in camp["quote"]}
    esiti = {int(r["fixture_id"]): r for r in camp["esiti"]}
    fps = {int(r["fixture_id"]): r for r in camp["fixture_predictions"]}
    st = Storico(camp["storico"])
    forze = {"train": ForzaSquadre(camp["storico"], TAGLIO_FORZA_TRAIN),
             "test": ForzaSquadre(camp["storico"], SPLIT)}
    righe: List[dict] = []
    for fid, q in sorted(quote.items()):
        es = esiti.get(fid)
        if not es or str(es.get("status_short") or "").upper() not in ("FT", "AET", "PEN"):
            continue
        if es.get("goals_home") is None or es.get("goals_away") is None:
            continue
        fp = fps.get(fid, {})
        insieme = "train" if str(q.get("run_date") or "") < SPLIT else "test"
        forza = forze[insieme]
        e = {"league_id": es.get("league_id"), "home_team_id": es.get("home_team_id"),
             "away_team_id": es.get("away_team_id"), "fixture_date": es.get("fixture_date")}
        fonti: Dict[str, Tuple[float, float]] = {}
        for nome, val in (
                ("mercato", lam_mercato(q, meta_spread=True)),
                ("fixture", lam_fixture(fp)),
                ("tattico", lam_tattico(fp)),
                ("api", lam_api(fp)),
                ("forza", lam_forza(forza, e)),
                ("forma", lam_forma(st, forza, e)),
                ("h2h", lam_h2h(st, forza, e)),
                ("lega", lam_lega(forza, e))):
            if val and val[0] and val[1] and 0.05 < val[0] < 8 and 0.05 < val[1] < 8:
                fonti[nome] = (float(val[0]), float(val[1]))
        if "mercato" not in fonti and not fonti:
            continue
        righe.append({"fixture_id": fid, "insieme": insieme, "run_date": q.get("run_date"),
                      "league_id": es.get("league_id"), "fixture_date": es.get("fixture_date"),
                      "fonti": fonti, "esito": es,
                      "mercato_back": lam_mercato(q, meta_spread=False)})
    return righe


def _arm_lambdas(riga: dict, arm: str, pesi: Dict[str, float], cvp: Dict[str, float],
                 pesi_ripiego: Optional[Dict[str, float]] = None) -> Optional[dict]:
    """Le lambda del braccio di confronto ``arm`` per una partita."""
    f = riga["fonti"]
    if arm == "fusione":
        return fondi(f, pesi, cvp, pesi_ripiego)
    if arm == "mercato":
        v = f.get("mercato")
    elif arm == "fixture":
        v = f.get("fixture")
    elif arm == "catena":
        # la CATENA ATTUALE di omega_service._prematch_lambdas, in pre-partita:
        # 1) fixture (tactical_engine -> db_json_analisi.inputs), 2) quote pre-KO
        # (prezzi BACK, come li congela lo scanner). Niente altro e' disponibile
        # prima del calcio d'inizio.
        v = f.get("tattico") or f.get("fixture") or riga.get("mercato_back")
    else:
        raise ValueError(arm)
    if not v:
        return None
    return {"lh": float(v[0]), "la": float(v[1]), "cv": max(CV_MIN, min(CV_MAX, float(cvp.get("cv0", 0.30)))),
            "fonti_usate": (arm,), "pesi_usati": {arm: 1.0}, "dispersione": 0.0, "copertura": 1.0}


def misura_arm(righe: Sequence[dict], arm: str, pesi: Dict[str, float],
               cvp: Dict[str, float],
               pesi_ripiego: Optional[Dict[str, float]] = None) -> Tuple[dict, List[dict]]:
    voci, per_fix = [], []
    for r in righe:
        lam = _arm_lambdas(r, arm, pesi, cvp, pesi_ripiego)
        if lam is None:
            continue
        v = valuta(lam["lh"], lam["la"], lam["cv"], r["esito"])
        if v is None:
            continue
        v["fixture_id"] = r["fixture_id"]
        voci.append(v)
        per_fix.append(v)
    return aggrega(voci), per_fix


# ---------------------------------------------------------------------------
# TARATURA FUORI CAMPIONE
# ---------------------------------------------------------------------------
def _obiettivo(righe: Sequence[dict], pesi: Dict[str, float], cvp: Dict[str, float]) -> float:
    """Media di log-loss del risultato esatto FT e HT: e' la cella che Omega banca."""
    tot_ft = tot_ht = 0.0
    n_ft = n_ht = 0
    for r in righe:
        lam = fondi(r["fonti"], pesi, cvp)
        if lam is None:
            continue
        v = valuta(lam["lh"], lam["la"], lam["cv"], r["esito"])
        if v is None:
            continue
        tot_ft += v["ll_ft"]; n_ft += 1
        if "ll_ht" in v:
            tot_ht += v["ll_ht"]; n_ht += 1
    if not n_ft:
        return 1e9
    return tot_ft / n_ft + (tot_ht / n_ht if n_ht else 0.0)


def stima_pesi(train: Sequence[dict], *, giri: int = 400, verbose: bool = True) -> Tuple[dict, dict]:
    """Stima i pesi delle fonti e i parametri del cv SULL'INSIEME DI STIMA.

    Il peso del MERCATO e' fissato a 1: nel pool logaritmico conta solo il
    rapporto fra i pesi, e fissarne uno toglie l'indeterminazione di scala.
    """
    from scipy.optimize import minimize
    liberi = [s for s in FONTI if s != "mercato"]
    x0 = [math.log(max(1e-3, PESI_PRIOR[s])) for s in liberi] + \
         [CV_PRIOR["cv0"], CV_PRIOR["c_disp"], CV_PRIOR["c_mancanza"]]

    def unpack(x):
        pesi = {"mercato": 1.0}
        for s, v in zip(liberi, x[:len(liberi)]):
            pesi[s] = math.exp(max(-9.0, min(2.0, float(v))))
        cvp = {"cv0": max(0.05, min(0.9, float(x[-3]))),
               "c_disp": max(0.0, min(3.0, float(x[-2]))),
               "c_mancanza": max(0.0, min(2.0, float(x[-1])))}
        return pesi, cvp

    passi = {"n": 0}

    def f(x):
        pesi, cvp = unpack(x)
        passi["n"] += 1
        v = _obiettivo(train, pesi, cvp)
        if verbose and passi["n"] % 25 == 0:
            print(f"   passo {passi['n']:4d}  obiettivo {v:.5f}")
        return v

    res = minimize(f, x0, method="Nelder-Mead",
                   options={"maxfev": int(giri), "xatol": 1e-3, "fatol": 1e-5})
    pesi, cvp = unpack(res.x)
    # peso sotto l'1 % del mercato = ZERO dichiarato (non un peso minuscolo finto)
    pesi = {k: (0.0 if k != "mercato" and v < 0.01 else round(v, 4)) for k, v in pesi.items()}
    cvp = {k: round(v, 4) for k, v in cvp.items()}
    return pesi, cvp


def _cv0_ottimo_fusione(righe: Sequence[dict], pesi: Dict[str, float],
                        cvp: Dict[str, float],
                        pesi_ripiego: Optional[Dict[str, float]] = None) -> float:
    """Il ``cv0`` migliore PER I PESI FINALI. Va rifatto dopo l'ablazione: il cv era
    stato stimato INSIEME ai pesi, e azzerare i pesi lo lascerebbe tarato per un
    modello che non esiste piu' (qui: con una sola fonte la dispersione e' 0 e il
    cv sarebbe crollato a 0,10 senza che nessuno l'abbia misurato)."""
    best, bv = float(cvp.get("cv0", 0.30)), 1e18
    for i in range(2, 17):
        cv = 0.05 * i
        c2 = dict(cvp); c2["cv0"] = cv
        agg, _ = misura_arm(righe, "fusione", pesi, c2, pesi_ripiego)
        v = (agg.get("ll_ft") or 1e18) + (agg.get("ll_ht") or 0.0)
        if v < bv:
            bv, best = v, cv
    return round(best, 4)


def _cv0_ottimo(righe: Sequence[dict], arm: str) -> float:
    """Il cv migliore per un braccio di confronto: ogni baseline ha la SUA
    incertezza tarata, se no la fusione vincerebbe solo per il cv."""
    best, bv = 0.30, 1e9
    for cv in [0.05 * i for i in range(2, 15)]:
        agg, _ = misura_arm(righe, arm, {}, {"cv0": cv})
        v = (agg.get("ll_ft") or 1e9) + (agg.get("ll_ht") or 0.0)
        if v < bv:
            bv, best = v, cv
    return best


def bootstrap_differenza(a: Sequence[dict], b: Sequence[dict], *, giri: int = 2000,
                         chiave: str = "ll_ft", seme: int = 20260917) -> Tuple[float, float, float]:
    """IC al 95 % della differenza MEDIA (a - b) per partita, bootstrap sulle PARTITE.

    Le partite sono le unita' indipendenti: ricampionarle e' il conto onesto.
    Negativo = il braccio ``a`` ha log-loss piu' bassa, cioe' e' migliore.
    """
    ia = {x["fixture_id"]: x for x in a if chiave in x}
    ib = {x["fixture_id"]: x for x in b if chiave in x}
    comuni = sorted(set(ia) & set(ib))
    if not comuni:
        return 0.0, 0.0, 0.0
    d = [ia[f][chiave] - ib[f][chiave] for f in comuni]
    med = sum(d) / len(d)
    rng = random.Random(seme)
    camp = []
    n = len(d)
    for _ in range(int(giri)):
        s = 0.0
        for _ in range(n):
            s += d[rng.randrange(n)]
        camp.append(s / n)
    camp.sort()
    return med, camp[int(0.025 * (len(camp) - 1))], camp[int(0.975 * (len(camp) - 1))]


F_RIGHE = os.path.join(DATA, "m2_righe_2026-09-17.json.gz")


def righe_taratura(camp: Optional[dict] = None, *, ricostruisci: bool = False) -> List[dict]:
    """Le righe di taratura, con cache su disco: ``costruisci`` costa minuti
    (la catena bisezione-su-griglia della produzione, 1.260 griglie per fonte
    per partita) e non deve essere rifatta a ogni prova."""
    if os.path.exists(F_RIGHE) and not ricostruisci:
        with gzip.open(F_RIGHE, "rt", encoding="utf-8") as fh:
            righe = json.load(fh)
        for r in righe:
            r["fonti"] = {k: tuple(v) for k, v in r["fonti"].items()}
            if r.get("mercato_back"):
                r["mercato_back"] = tuple(r["mercato_back"])
        return righe
    righe = costruisci(camp or carica_campione())
    os.makedirs(DATA, exist_ok=True)
    with gzip.open(F_RIGHE, "wt", encoding="utf-8") as fh:
        json.dump(righe, fh)
    return righe


# ---------------------------------------------------------------------------
# HAZARD DI GOL per (lega, minuto, punteggio) - l'input IN-PLAY di §3 della
# VISIONE_OMEGA_V4. Dalle 1,07 M transizioni gia' in casa, NESSUNA lettura nuova.
# ---------------------------------------------------------------------------
F_TRANSIZIONI = os.path.join(DATA, "transizioni_minuto_2026-09-16.json.gz")
PASSO_BUCKET = 5
HAZ_N_MIN = 300          # sotto: lo stato non dice niente, si dichiara "non lo so"
HAZ_SHRINK_K = 2000.0    # peso del prior globale per la stima di lega


def _residui_attesi(righe: Sequence[dict]) -> Dict[Tuple[int, int, str], Tuple[float, float, int]]:
    """(lega, bucket, punteggio) -> (gol casa attesi da qui a fine, gol trasferta, n).

    Si usa solo ``target='ft'``: il risultato FINALE meno il punteggio corrente
    e' esattamente il numero di gol che restano.
    """
    acc: Dict[Tuple[int, int, str], List[float]] = {}
    for r in righe:
        if str(r.get("target")) != "ft":
            continue
        try:
            sh, sa = (int(v) for v in str(r["score"]).split("-"))
            rh, ra = (int(v) for v in str(r["result"]).split("-"))
            n = int(r["n"])
            k = (int(r.get("league_id") or 0), int(r["bucket"]), str(r["score"]))
        except (TypeError, ValueError, KeyError):
            continue
        if n <= 0 or rh < sh or ra < sa:
            continue
        v = acc.setdefault(k, [0.0, 0.0, 0.0])
        v[0] += n * (rh - sh)
        v[1] += n * (ra - sa)
        v[2] += n
    return {k: (v[0] / v[2], v[1] / v[2], int(v[2])) for k, v in acc.items() if v[2] > 0}


def _somma_punteggio(score: str, chi: str) -> str:
    h, a = (int(v) for v in str(score).split("-"))
    return f"{h + 1}-{a}" if chi == "h" else f"{h}-{a + 1}"


def hazard_da_transizioni(righe: Sequence[dict], lega: int = 0) -> Dict[str, dict]:
    """(lambda_casa, lambda_trasferta) ISTANTANEI per (bucket, punteggio), risolti
    dal bilancio dei gol residui fra due bucket adiacenti.

    Sia A_h(b,S) il numero di gol CASA attesi da (bucket b, punteggio S) alla fine.
    Con passo dt = 5/90 di partita e intensita' costanti dentro il bucket, la
    proprieta' della torre da':

        A_h(b,S) = x + (1-x-y) A_h(b+1,S) + x A_h(b+1,S+casa) + y A_h(b+1,S+tras)
        A_a(b,S) = y + (1-x-y) A_a(b+1,S) + x A_a(b+1,S+casa) + y A_a(b+1,S+tras)

    con x = lambda_casa*dt, y = lambda_trasferta*dt. E' un sistema LINEARE 2x2 in
    (x, y): si risolve per ogni stato. Tutti i numeri vengono dalla tabella; non
    c'e' nessun parametro inventato.
    """
    A = _residui_attesi(righe)
    fuori: Dict[str, dict] = {}
    for (lg, b, S), (ah, aa, n) in sorted(A.items()):
        if lg != lega or n < HAZ_N_MIN:
            continue
        nxt = (lg, b + PASSO_BUCKET, S)
        if nxt not in A:
            continue
        try:
            sh, sa = _somma_punteggio(S, "h"), _somma_punteggio(S, "a")
        except ValueError:
            continue
        n_h = A.get((lg, b + PASSO_BUCKET, sh))
        n_a = A.get((lg, b + PASSO_BUCKET, sa))
        if n_h is None or n_a is None:
            continue
        ah1, aa1, _ = A[nxt]
        # coefficienti del sistema
        a11 = 1.0 + n_h[0] - ah1
        a12 = n_a[0] - ah1
        a21 = n_h[1] - aa1
        a22 = 1.0 + n_a[1] - aa1
        b1, b2 = ah - ah1, aa - aa1
        det = a11 * a22 - a12 * a21
        if abs(det) < 1e-9:
            continue
        x = (b1 * a22 - a12 * b2) / det
        y = (a11 * b2 - b1 * a21) / det
        dt = PASSO_BUCKET / 90.0
        lh, la = x / dt, y / dt
        if not (0.0 <= lh < 12.0 and 0.0 <= la < 12.0):
            continue
        fuori[f"{b}|{S}"] = {"bucket": b, "score": S, "lambda_casa": round(lh, 4),
                             "lambda_trasferta": round(la, 4), "n": n}
    return fuori


def profilo_temporale(haz: Dict[str, dict]) -> Dict[int, float]:
    """Intensita' TOTALE media per bucket (pesata sui casi): il profilo di
    Dixon-Robinson misurato sui nostri dati, non assunto."""
    per_b: Dict[int, List[float]] = collections.defaultdict(lambda: [0.0, 0.0])
    for v in haz.values():
        acc = per_b[v["bucket"]]
        acc[0] += v["n"] * (v["lambda_casa"] + v["lambda_trasferta"])
        acc[1] += v["n"]
    return {b: round(s / n, 4) for b, (s, n) in sorted(per_b.items()) if n > 0}


# ---------------------------------------------------------------------------
# IL CONTRATTO CON IL COSTRUTTORE
# ---------------------------------------------------------------------------
import typing   # noqa: E402


class Intensita(typing.NamedTuple):
    """Quello che il motore riceve. Si spacchetta come
    ``(lam_casa, lam_trasferta, cv, fonti_usate, pesi)``."""
    lam_casa: float
    lam_trasferta: float
    cv: float
    fonti_usate: Tuple[str, ...]
    pesi: Dict[str, float]


def _json(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return None
    return v


def fonti_da_evento(evento: dict) -> Dict[str, Tuple[float, float]]:
    """Le lambda di ogni fonte, lette dalle CHIAVI VERE delle tabelle.

    ``evento`` (tutte le chiavi facoltative, nessuna inventata):
      * ``fixture_predictions``: la riga vera (``db_json_analisi``,
        ``tactical_engine_json``, ``percent_home/draw/away``);
      * ``pre_ko``: ``{"home","draw","away"}`` come lo congela lo scanner
        (``omega_service._prematch_lambdas`` passo 3);
      * ``quote_1x2``: ``{"back_home","lay_home","back_draw",...}`` da
        ``betfair_market_odds`` (mercato ``Match Odds``, sort 1=casa 2=trasferta
        3=pareggio): se c'e', il MID fra back e lay e' la fonte piu' forte;
      * ``storico``: ``{"forza": [lh,la], "forma": [lh,la], "h2h": [lh,la],
        "lega": [lh,la]}`` gia' calcolate (le calcola ``ForzaSquadre``/``Storico``).
    """
    fonti: Dict[str, Tuple[float, float]] = {}
    q = evento.get("quote_1x2") or {}
    if q:
        v = lam_mercato(q, meta_spread=True)
        if v:
            fonti["mercato"] = (float(v[0]), float(v[1]))
    if "mercato" not in fonti and isinstance(evento.get("pre_ko"), dict):
        v = M.lambdas_from_pre_ko(evento["pre_ko"], rho=RHO)
        if v:
            fonti["mercato"] = (float(v[0]), float(v[1]))
    fp = evento.get("fixture_predictions") or {}
    dbj = _json(fp.get("db_json_analisi"))
    inputs = dbj.get("inputs") if isinstance(dbj, dict) else None
    lh = _f((inputs or {}).get("lambda_home") if isinstance(inputs, dict) else fp.get("lh"))
    la = _f((inputs or {}).get("lambda_away") if isinstance(inputs, dict) else fp.get("la"))
    if lh and la:
        fonti["fixture"] = (lh, la)
    tac = _json(fp.get("tactical_engine_json"))
    tlh = _f(tac.get("lambda_home") if isinstance(tac, dict) else fp.get("tlh"))
    tla = _f(tac.get("lambda_away") if isinstance(tac, dict) else fp.get("tla"))
    if tlh and tla:
        fonti["tattico"] = (tlh, tla)
    v = lam_api(fp)
    if v:
        fonti["api"] = (float(v[0]), float(v[1]))
    for nome in ("forza", "forma", "h2h", "lega"):
        val = (evento.get("storico") or {}).get(nome)
        if val and len(val) == 2 and _f(val[0]) and _f(val[1]):
            fonti[nome] = (float(val[0]), float(val[1]))
    return fonti


def forma_gamma_da_cv(cv: float) -> float:
    """Il parametro di FORMA della Gamma equivalente al ``cv``: a = 1/cv^2.

    ``omega_v3`` parla in ``forma_gamma`` (Gamma-Poisson, predittiva binomiale
    negativa) e ``omega_model`` in ``cv`` (mistura log-normale): sono lo stesso
    numero detto in due lingue, perche' per una Gamma di media 1 vale
    cv = 1/sqrt(a). Il banco del 16/09 ha misurato a = 6,7-13,3, cioe'
    cv = 0,27-0,39: il ``model_lambda_cv`` 0,30 di produzione stava dentro.
    """
    c = max(1e-6, float(cv))
    return 1.0 / (c * c)


def carica_pesi(percorso: str = F_PESI
                ) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
    """(pesi misurati, parametri del cv, pesi di ripiego)."""
    if not os.path.exists(percorso):
        return dict(PESI_PRIOR), dict(CV_PRIOR), {}
    with open(percorso, "r", encoding="utf-8") as fh:
        d = json.load(fh)
    return (d.get("pesi") or dict(PESI_PRIOR), d.get("cv") or dict(CV_PRIOR),
            d.get("pesi_ripiego") or {})


def intensita_prematch(evento: dict, *, pesi: Optional[Dict[str, float]] = None,
                       cv: Optional[Dict[str, float]] = None,
                       pesi_ripiego: Optional[Dict[str, float]] = None
                       ) -> Optional[Intensita]:
    """LA FUNZIONE CHE IL MOTORE CHIAMERA'. (lam_casa, lam_trasferta, cv, fonti, pesi).

    ``None`` = nessuna fonte disponibile: si SALTA la partita, mai a occhi chiusi.
    Il ``cv`` cresce quando le fonti mancano o non sono d'accordo: e' la
    degradazione con grazia chiesta dall'ordine del 17/09. Pura: niente rete,
    niente database, niente orologio.
    """
    if pesi is None or cv is None or pesi_ripiego is None:
        p, c, r = carica_pesi()
        pesi = pesi if pesi is not None else p
        cv = cv if cv is not None else c
        pesi_ripiego = pesi_ripiego if pesi_ripiego is not None else r
    fonti = fonti_da_evento(evento)
    out = fondi(fonti, pesi, cv, pesi_ripiego)
    if out is None:
        return None
    return Intensita(round(out["lh"], 4), round(out["la"], 4), round(out["cv"], 4),
                     tuple(out["fonti_usate"]), dict(out["pesi_usati"]))


# ---------------------------------------------------------------------------
# FASE "copertura" - i numeri dell'inventario, misurati, non stimati
# ---------------------------------------------------------------------------
def copertura(da: str = COP_DA, a: str = COP_A) -> dict:
    """Copertura MISURATA delle fonti sulle partite GIOCATE nella finestra."""
    sb = _sb()
    m = _pagina(sb, "matches", "fixture_id,league_id,fixture_date,status_short,"
                "goals_home,goals_away,halftime_home,halftime_away",
                [lambda q: q.gte("fixture_date", da), lambda q: q.lt("fixture_date", a)],
                ("fixture_date", "fixture_id"))
    giocate = [x for x in m if str(x.get("status_short") or "").upper() in ("FT", "AET", "PEN")
               and x.get("goals_home") is not None]
    fids = {int(x["fixture_id"]) for x in giocate}
    fp = _pagina(sb, "fixture_predictions", SEL_FP,
                 [lambda q: q.gte("fixture_date", da), lambda q: q.lt("fixture_date", a)],
                 ("fixture_date", "fixture_id"))
    fpm = {int(x["fixture_id"]): x for x in fp if int(x["fixture_id"]) in fids}
    bo = _pagina(sb, "betfair_market_odds", "fixture_id,market_name,run_date,captured_at",
                 [lambda q: q.gte("run_date", da)], ("fixture_id", "market_name", "selection"))
    odds_fix = {int(x["fixture_id"]) for x in bo}
    tr = {}
    for t in ("omega_minute_transitions", "omega_ht_ft_transitions"):
        try:
            tr[t] = getattr(sb.table(t).select("*", count="exact", head=True).execute(), "count", None)
        except Exception as ex:      # noqa: BLE001
            tr[t] = f"KO {str(ex)[:60]}"
    n = len(giocate)
    def q(k):
        c = sum(1 for x in fpm.values() if x.get(k) is not None)
        return {"n": c, "pct": round(100.0 * c / n, 1) if n else None}
    out = {
        "finestra": [da, a],
        "partite_giocate_con_esito": n,
        "con_punteggio_45": sum(1 for x in giocate if x.get("halftime_home") is not None),
        "fonti": {
            "fixture_predictions (riga)": {"n": len(fpm),
                                           "pct": round(100.0 * len(fpm) / n, 1) if n else None},
            "poisson lambda (db_json_analisi.inputs)": q("lh"),
            "tactical_engine lambda": q("tlh"),
            "ht_predictions.lambda_1h": q("l1h"),
            "percent 1X2 (API-Football)": q("ph"),
            "h2h (raw_json.response[0].h2h non vuoto)":
                {"n": sum(1 for x in fpm.values() if x.get("h2h")),
                 "pct": round(100.0 * sum(1 for x in fpm.values() if x.get("h2h")) / n, 1) if n else None},
            "betfair_market_odds (quote pre-match)":
                {"n": len(odds_fix & fids),
                 "pct": round(100.0 * len(odds_fix & fids) / n, 1) if n else None},
        },
        "righe_tabelle_transizioni": tr,
        "ultimo_run_date_quote": max((x.get("run_date") or "") for x in bo) if bo else None,
    }
    os.makedirs(DATA, exist_ok=True)
    with open(F_COPERTURA, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return out


# ---------------------------------------------------------------------------
# FASE "tara"
# ---------------------------------------------------------------------------
def tara(*, giri: int = 700, boot: int = 2000, ricostruisci: bool = False,
         stima_nota: Optional[dict] = None) -> dict:
    """Taratura completa. ``stima_nota`` = {"pesi": {...}, "cv": {...}} salta i 700
    passi di Nelder-Mead e riusa una stima GIA' FATTA: e' solo un risparmio di tempo
    (la stima e' deterministica - stesso punto di partenza, nessun caso), non una
    scorciatoia sulla misura: tutto cio' che segue (rifit del cv, prova fuori
    campione, bootstrap, ablazione) viene rifatto per intero."""
    righe = righe_taratura(ricostruisci=ricostruisci)
    train = [r for r in righe if r["insieme"] == "train"]
    test = [r for r in righe if r["insieme"] == "test"]
    print(f"stima su {len(train)} partite (quote fino al {SPLIT}), "
          f"prova su {len(test)} partite MAI VISTE")
    if stima_nota:
        pesi, cvp = dict(stima_nota["pesi"]), dict(stima_nota["cv"])
        print("stima RIUSATA (deterministica): niente Nelder-Mead")
    else:
        pesi, cvp = stima_pesi(train, giri=giri)
    print(f"pesi stimati: {pesi}")
    print(f"cv:           {cvp}")

    risultati: Dict[str, Any] = {}
    per_fix: Dict[str, List[dict]] = {}
    for arm in ("fusione", "mercato", "fixture", "catena"):
        if arm == "fusione":
            agg, pf = misura_arm(test, arm, pesi, cvp)
        else:
            cv0 = _cv0_ottimo(train, arm)          # ogni baseline con il SUO cv migliore
            agg, pf = misura_arm(test, arm, {}, {"cv0": cv0})
            agg["cv0"] = cv0
        risultati[arm] = agg
        per_fix[arm] = pf
        print("  %-9s n=%s ll_ft=%s ll_ht=%s brier=%s coda_ft=%s coda_ht=%s" % (
            arm, agg.get("n"), agg.get("ll_ft"), agg.get("ll_ht"),
            agg.get("brier_ft"), agg.get("coda_ft"), agg.get("coda_ht")))

    confronti = {}
    for arm in ("mercato", "fixture", "catena"):
        for chiave in ("ll_ft", "ll_ht"):
            m, lo, hi = bootstrap_differenza(per_fix["fusione"], per_fix[arm],
                                             giri=boot, chiave=chiave)
            confronti[f"fusione-{arm}.{chiave}"] = {"differenza": round(m, 5),
                                                    "ic95": [round(lo, 5), round(hi, 5)],
                                                    "migliora": bool(hi < 0)}
            print(f"  fusione - {arm:8s} {chiave}: {m:+.5f}  IC95 [{lo:+.5f}, {hi:+.5f}]"
                  f"{'  MIGLIORA' if hi < 0 else ''}")

    # QUALE PESO SERVE DAVVERO: si toglie una fonte alla volta e si rimisura OOS.
    ablazione = {}
    base_agg, base_pf = misura_arm(test, "fusione", pesi, cvp)
    for s in FONTI:
        if s == "mercato" or pesi.get(s, 0.0) <= 0:
            continue
        p2 = dict(pesi); p2[s] = 0.0
        agg2, pf2 = misura_arm(test, "fusione", p2, cvp)
        m, lo, hi = bootstrap_differenza(base_pf, pf2, giri=boot, chiave="ll_ft")
        ablazione[s] = {"ll_ft_senza": agg2.get("ll_ft"), "differenza": round(m, 5),
                        "ic95": [round(lo, 5), round(hi, 5)], "serve": bool(hi < 0)}
        v2 = agg2.get("ll_ft")
        print("  senza %-8s: ll_ft %s  delta %+.5f IC95 [%+.5f,%+.5f]%s" % (
            s, ("%.5f" % v2) if v2 is not None else "n/d", m, lo, hi,
            "  SERVE" if hi < 0 else "  PESO 0"))

    # un peso che non dimostra di servire vale ZERO e lo si dichiara
    pesi_finali = dict(pesi)
    azzerati = []
    for s, v in ablazione.items():
        if not v["serve"]:
            pesi_finali[s] = 0.0
            azzerati.append(s)
    # le fonti azzerate restano come RIPIEGO: non aggiungono nulla quando c'e' il
    # mercato, ma quando il mercato MANCA sono tutto quello che c'e'. Entrano con i
    # pesi pre-ablazione e con la copertura che crolla, quindi con un cv piu' largo.
    pesi_ripiego = {s: float(pesi.get(s, 0.0)) for s in FONTI
                    if s != "mercato" and float(pesi.get(s, 0.0)) > 0.0}
    # il cv era stato stimato INSIEME ai pesi: azzerarli lo lascerebbe tarato per un
    # modello che non esiste piu'. Si rifa', sui PESI FINALI, sull'insieme di stima.
    cv_finale = dict(cvp)
    cv_finale["cv0"] = _cv0_ottimo_fusione(train, pesi_finali, cvp, pesi_ripiego)
    print(f"cv0 RIFITTATO sui pesi finali: {cvp['cv0']} -> {cv_finale['cv0']}")
    agg_f, pf_f = misura_arm(test, "fusione", pesi_finali, cv_finale, pesi_ripiego)
    risultati["fusione_finale"] = agg_f
    print("  %-9s n=%s ll_ft=%s ll_ht=%s brier=%s coda_ft=%s coda_ht=%s" % (
        "FINALE", agg_f.get("n"), agg_f.get("ll_ft"), agg_f.get("ll_ht"),
        agg_f.get("brier_ft"), agg_f.get("coda_ft"), agg_f.get("coda_ht")))
    for arm in ("mercato", "catena"):
        for chiave in ("ll_ft", "ll_ht"):
            m, lo, hi = bootstrap_differenza(pf_f, per_fix[arm], giri=boot, chiave=chiave)
            confronti[f"finale-{arm}.{chiave}"] = {"differenza": round(m, 5),
                                                   "ic95": [round(lo, 5), round(hi, 5)],
                                                   "migliora": bool(hi < 0)}
            print(f"  FINALE  - {arm:8s} {chiave}: {m:+.5f}  IC95 [{lo:+.5f}, {hi:+.5f}]"
                  f"{'  MIGLIORA' if hi < 0 else ''}")
    out = {
        "generato": "2026-09-17",
        "metodo": "pool logaritmico sulle lambda, pesi stimati su TRAIN e misurati su TEST",
        "split": {"criterio": "run_date delle quote", "soglia": SPLIT,
                  "n_train": len(train), "n_test": len(test)},
        "stima_riusata": bool(stima_nota),
        "pesi": pesi_finali,
        "pesi_ripiego": pesi_ripiego,
        "pesi_prima_dell_ablazione": pesi,
        "azzerati_perche_non_migliorano_fuori_campione": azzerati,
        "cv": cv_finale,
        "cv_stimato_coi_pesi_pre_ablazione": cvp,
        "risultati_fuori_campione": risultati,
        "confronti_bootstrap": confronti,
        "ablazione": ablazione,
        "limiti": [
            "campione vincolato alle 2.018 fixture con quote Betfair pre-match "
            "(24/06-11/09/2026): e' l'unico insieme dove si puo' confrontare QUALUNQUE "
            "fonte contro il mercato",
            "quote PRE-MATCH: il peso del mercato IN GIOCO va rimisurato sui book live",
            "il 29 % del campione sono amichevoli di club (lega 667): forza e forma "
            "valgono meno li' che in campionato",
        ],
    }
    os.makedirs(DATA, exist_ok=True)
    with open(F_PESI, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(f"-> {F_PESI}")
    return out


# ---------------------------------------------------------------------------
# FASE "simula" - la partita, passo per passo, con i numeri
# ---------------------------------------------------------------------------
def _leggi_evento(sb, fixture_id: int, camp: dict) -> dict:
    fp = (sb.table("fixture_predictions")
          .select("fixture_id,league_id,league_name,fixture_date,home_team_name,away_team_name,"
                  "home_team_id,away_team_id,updated_at,db_json_analisi,tactical_engine_json,"
                  "percent_home,percent_draw,percent_away")
          .eq("fixture_id", int(fixture_id)).limit(1).execute().data or [{}])[0]
    quote = (sb.table("betfair_market_odds")
             .select("market_name,selection,sort_priority,back,lay,run_date,captured_at")
             .eq("fixture_id", int(fixture_id))
             .in_("market_name", ["Match Odds", "Correct Score", "Half Time Score"])
             .execute().data or [])
    es = (sb.table("matches")
          .select(SEL_MATCH).eq("fixture_id", int(fixture_id)).limit(1).execute().data or [{}])[0]
    q1x2 = {}
    for r in quote:
        if r.get("market_name") != "Match Odds":
            continue
        lato = {1: "home", 2: "away", 3: "draw"}.get(int(r.get("sort_priority") or 0))
        if lato:
            q1x2["back_" + lato] = _prezzo(r.get("back"))
            q1x2["lay_" + lato] = _prezzo(r.get("lay"))
    st = Storico(camp["storico"])
    taglio = str(es.get("fixture_date") or fp.get("fixture_date") or COP_A)[:10]
    forza = ForzaSquadre(camp["storico"], taglio)
    e = {"league_id": es.get("league_id") or fp.get("league_id"),
         "home_team_id": es.get("home_team_id") or fp.get("home_team_id"),
         "away_team_id": es.get("away_team_id") or fp.get("away_team_id"),
         "fixture_date": es.get("fixture_date") or fp.get("fixture_date")}
    storico = {}
    for nome, v in (("forza", lam_forza(forza, e)), ("forma", lam_forma(st, forza, e)),
                    ("h2h", lam_h2h(st, forza, e)), ("lega", lam_lega(forza, e))):
        if v:
            storico[nome] = [float(v[0]), float(v[1])]
    return {"fixture_predictions": fp, "quote_1x2": q1x2, "storico": storico,
            "quote": quote, "esito": es}


def simula(fixture_id: int, *, commissione: float = 0.05) -> dict:
    """Passo per passo su UNA partita vera: fonti, lambda, fusione, griglia,
    confronto col book Betfair pre-match, esito. Numeri, non parole."""
    camp = carica_campione()
    pesi, cvp, pesi_ripiego = carica_pesi()
    sb = _sb()
    ev = _leggi_evento(sb, fixture_id, camp)
    fp, es = ev["fixture_predictions"], ev["esito"]
    print("=" * 78)
    print("PARTITA %s  %s v %s  (%s, lega %s, %s)" % (
        fixture_id, fp.get("home_team_name"), fp.get("away_team_name"),
        fp.get("league_name"), fp.get("league_id"), str(fp.get("fixture_date"))[:10]))
    print("=" * 78)
    fonti = fonti_da_evento(ev)
    print("")
    print("1) FONTI TROVATE e lambda di ciascuna")
    for s in FONTI:
        if s in fonti:
            print("   %-9s lam_casa %.3f  lam_tras %.3f  tot %.3f   peso %.3f (ripiego %.3f)" % (
                s, fonti[s][0], fonti[s][1], fonti[s][0] + fonti[s][1],
                pesi.get(s, 0.0), (pesi_ripiego or {}).get(s, 0.0)))
        else:
            print("   %-9s ASSENTE" % s)
    fusa = fondi(fonti, pesi, cvp, pesi_ripiego)
    if fusa is None:
        print("")
        print("   NESSUNA FONTE: si salta la partita (mai a occhi chiusi).")
        return {"fixture_id": fixture_id, "saltata": True}
    print("")
    print("2) LAMBDA FUSE (pool logaritmico a pesi) + INCERTEZZA DICHIARATA")
    print("   lam_casa %.4f  lam_tras %.4f  totale %.4f" % (
        fusa["lh"], fusa["la"], fusa["lh"] + fusa["la"]))
    print("   cv %.4f   (dispersione fra le fonti %.4f, copertura dei pesi %.1f %%%s)" % (
        fusa["cv"], fusa["dispersione"], 100 * fusa["copertura"],
        ", RIPIEGO: il mercato manca" if fusa.get("ripiego") else ""))
    print("   pesi effettivamente usati: %s" % (fusa["pesi_usati"],))
    g = M.residual_grid(fusa["lh"], fusa["la"], RHO, MAX_GOALS, dixon_coles=True, cv=fusa["cv"])
    print("")
    print("3) GRIGLIA PRE-PARTITA (prime 8 celle)")
    for (h, a), p in sorted(g.items(), key=lambda kv: -kv[1])[:8]:
        print("   %d-%d: %6.3f %%" % (h, a, 100 * p))
    n_coda = sum(1 for p in g.values() if p <= 0.02)
    coda = sum(p for p in g.values() if p <= 0.02)
    print("   massa sotto il 2 %% per cella: %.2f %% su %d celle" % (100 * coda, n_coda))
    print("")
    print("4) CONFRONTO CON LE QUOTE BETFAIR PRE-MATCH (Correct Score)")
    print("   cella    lay   p_impl(lay)   p_equa(mid)    p_nostra    k=p_impl/p_nostra")
    righe_cs = []
    for r in ev["quote"]:
        if r.get("market_name") != "Correct Score":
            continue
        sc = str(r.get("selection") or "")
        try:
            h, a = (int(v) for v in sc.split("-"))
        except ValueError:
            continue
        lay = _prezzo(r.get("lay"))
        back = _prezzo(r.get("back"))
        if lay is None:
            continue
        p_impl = (1.0 - commissione) / (lay - commissione)
        mid = _mid(back, lay)
        p_equa = 1.0 / mid if mid else None
        p_nostra = g.get((h, a))
        if p_nostra is None:
            continue
        k = p_impl / p_nostra if p_nostra > 0 else None
        righe_cs.append((sc, lay, p_impl, p_equa, p_nostra, k))
    for sc, lay, p_impl, p_equa, p_nostra, k in sorted(righe_cs, key=lambda x: x[4])[:12]:
        print("   %5s  %6.1f   %8.3f %%   %8.3f %%   %8.3f %%   %6.2fx" % (
            sc, lay, 100 * p_impl, (100 * p_equa) if p_equa else float("nan"),
            100 * p_nostra, k))
    gh, ga = es.get("goals_home"), es.get("goals_away")
    if gh is not None:
        cel = (_cella(gh, MAX_GOALS), _cella(ga, MAX_GOALS))
        print("")
        print("5) ESITO REALE %s-%s (45': %s-%s) - la nostra P su quella cella era %.3f %%" % (
            gh, ga, es.get("halftime_home"), es.get("halftime_away"), 100 * g.get(cel, 0.0)))
    return {"fixture_id": fixture_id, "fonti": {k: list(v) for k, v in fonti.items()},
            "fuse": {k: v for k, v in fusa.items() if k != "fonti_usate"},
            "fonti_usate": list(fusa["fonti_usate"]),
            "esito": [gh, ga], "celle_cs": len(righe_cs)}


def fase_hazard() -> dict:
    """Hazard di gol per (lega, minuto, punteggio) dalle transizioni gia' su disco."""
    with gzip.open(F_TRANSIZIONI, "rt", encoding="utf-8") as fh:
        d = json.load(fh)
    haz = hazard_da_transizioni(d["globale"], 0)
    prof = profilo_temporale(haz)
    out = {"generato": "2026-09-17",
           "fonte": F_TRANSIZIONI,
           "built_at_tabella": d.get("built_at_tabella"),
           "stati": len(haz),
           "profilo_temporale_per_bucket": prof,
           "hazard": haz,
           "limiti": [
               "nessun effetto ROSSO: omega_minute_transitions non ha la dimensione "
               "cartellini. Servirebbe match_events (o una colonna nuova nella tabella).",
               "nessun regime di RITARDO: get_market_delays e' per lega e calcolata al "
               "volo, non e' nella tabella delle transizioni.",
               "bucket 40 e 85: il 40 include il recupero del 1T (intervallo piu' lungo "
               "di 5') e l'85 non ha un bucket successivo: vanno letti a parte.",
           ]}
    os.makedirs(DATA, exist_ok=True)
    with open(F_HAZARD, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print("stati con hazard: %d" % len(haz))
    print("profilo temporale (intensita' totale di gol per bucket di 5 minuti):")
    for b, v in prof.items():
        print("   %2d-%2d   %.3f" % (b, b + 5, v))
    print("-> %s" % F_HAZARD)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="M2 - dati e pesi delle intensita' pre-partita")
    ap.add_argument("fase", choices=["estrai", "copertura", "tara", "simula", "hazard"])
    ap.add_argument("--fixture", type=int, default=None)
    ap.add_argument("--giri", type=int, default=700)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--ricostruisci", action="store_true")
    ap.add_argument("--stima-nota", default=None,
                    help="JSON {'pesi':..., 'cv':...} di una stima gia' fatta: "
                         "salta Nelder-Mead, rifa tutto il resto")
    a = ap.parse_args(argv)
    if a.fase == "estrai":
        estrai()
    elif a.fase == "copertura":
        copertura()
    elif a.fase == "tara":
        nota = None
        if a.stima_nota:
            with open(a.stima_nota, "r", encoding="utf-8") as fh:
                nota = json.load(fh)
        tara(giri=a.giri, boot=a.boot, ricostruisci=a.ricostruisci, stima_nota=nota)
    elif a.fase == "simula":
        if a.fixture is None:
            ap.error("serve --fixture <id>")
        simula(a.fixture)
    elif a.fase == "hazard":
        fase_hazard()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
