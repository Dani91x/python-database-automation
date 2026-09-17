# -*- coding: utf-8 -*-
"""superficie_liability — LA SUPERFICIE QUOTA / LIABILITY / MARGINE per MINUTO.

DOMANDA (VISIONE_OMEGA_V4 §9, osservazione dell'utente del 17/09 h12): «senza
gol le quote delle scoreline improbabili SALGONO e per chi banca diventano piu'
difficili». Se e' vero, allora

    EV / liability = (1 - c) * (1 - 1/k) / (L - 1)

e, a parita' di margine k, ENTRARE PRESTO (quota bassa) rende di piu' per ogni
euro di liability. Le finestre di oggi (20'-40' e 50'-80') aspettano invece che
le quote salgano. Questo strumento MISURA la superficie che decide la questione:
per ogni (mercato, minuto, fascia di probabilita' implicita) la quota mediana al
tocco e al miglior back, la liability per euro di stake, lo spread in tick, la
profondita' del book e — dove il campione lo permette — la frequenza reale della
cella.

NON DECIDE NIENTE, NON TOCCA LA STRATEGIA, NON SCRIVE SUL DATABASE.

---------------------------------------------------------------------------
DA DOVE VENGONO I NUMERI, E COSA E' UN'APPROSSIMAZIONE (dichiarata)
---------------------------------------------------------------------------
* LADDER: ricostruita dai `rc` NATIVI dello stream registrato
  (`_live_raw/<id>/<id>.raw.jsonl`, chiavi `atb`/`atl`), come gia' fatto in
  `PROGETTO_OMEGA_V3_2026-09-16.md` §1.2. Nessun formato «curato».
* MINUTO E PUNTEGGIO: dal sidecar `<id>.scores.jsonl` (`ts_ms`, `minute`,
  `score_home`, `score_away`), cioe' la stessa fonte che in produzione alimenta
  lo scanner. MAI dall'orologio.
* NOMI DELLE CELLE: dalla formula dei gusci sui `selectionId`
  (`tools/replay_registrazioni.nome_scoreline`, verificata sulle registrazioni),
  perche' il raw non porta il catalogo.
* STATO DEL MERCATO: dai `marketDefinition` (`status`, `inPlay`, `runners[].status`).
  Si campiona solo con mercato OPEN, in gioco e runner ACTIVE.
* ESITO AUTOREVOLE: il `WINNER` del `marketDefinition` finale (`vincitori()`),
  non il sidecar. Il sidecar resta come confronto (`esito` contro `esito_md`):
  dove i due non concordano, il referto lo dichiara.
* PREZZI: `best_lay` (tocco), `prezzo_mid` (mid dei due lati, al tick, dentro lo
  spread) e `best_back` — i tre livelli di M1 e della misura appaiata pre-match.
* `p_equa`: probabilita' DEVIGATA (mid normalizzato a 1 sui runner attivi), usata
  come ipotesi nulla «mercato perfettamente calibrato».

APPROSSIMAZIONE DICHIARATA: questo NON e' un replay del bot. Non c'e' flumine,
non c'e' lo scanner, non ci sono ordini: e' una misura di PREZZO sul libro
registrato. Serve a scegliere dove guardare (finestre, fasce, cap); la condotta
del bot si certifica solo dal banco comune
(`python -m Betfair.stream.backtest.certifica omega ...`).

LIMITE DI CAMPIONE: una sola scoreline esce per mercato e per partita. Con 39
registrazioni le «uscite» per fascia sono pochissime: la colonna `p_reale` e' un
indizio, non una misura, e le righe sotto `--n-min-uscite` sono marcate
`misurabile=false`. Il margine k per fascia va preso dalla misura grande
(`tools/misura_prezzo_appaiata.py` su 48.280 selezioni pre-match).

Uso:
    python -m Betfair.omega.tools.superficie_liability
    python -m Betfair.omega.tools.superficie_liability --eventi 35760084 35797769
    python -m Betfair.omega.tools.superficie_liability --passo 5 --out percorso.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics as st
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from Betfair.omega.omega_engine import round_to_tick
from Betfair.omega.tools.replay_registrazioni import nome_runner_punteggio, nome_scoreline

COMMISSIONE = 0.05
MERCATI = {"CORRECT_SCORE": "2T", "HALF_TIME_SCORE": "1T"}
# sotto questo numero di selezioni prezzate sui DUE lati non si deviga: normalizzare
# mezzo book inventa probabilita' (stessa soglia di tools/misura_k.py).
DEVIG_MIN_SELEZIONI = 6
# fine del periodo che il mercato regola (il recupero conta nel punteggio)
FINE = {"HALF_TIME_SCORE": 45, "CORRECT_SCORE": 90}
# fasce di probabilita' implicita: le stesse di `misura_k.SECCHI`, cosi' che il
# k misurato la' si possa incollare qui senza tradurre niente.
FASCE: Tuple[Tuple[float, float, str], ...] = (
    (0.0000, 0.0020, "0-0,2%"),
    (0.0020, 0.0050, "0,2-0,5%"),
    (0.0050, 0.0100, "0,5-1%"),
    (0.0100, 0.0200, "1-2%"),
    (0.0200, 0.0500, "2-5%"),
    (0.0500, 0.1000, "5-10%"),
    (0.1000, 1.0001, ">10%"),
)


def fascia_di(p: float) -> Optional[str]:
    for lo, hi, et in FASCE:
        if lo < p <= hi:
            return et
    return None


def p_implicita(prezzo: float, c: float = COMMISSIONE) -> Optional[float]:
    L = float(prezzo)
    if not math.isfinite(L) or L <= 1.0:
        return None
    den = L - c
    if den <= 0:
        return None
    v = (1.0 - c) / den
    return v if 0.0 < v <= 1.0 else None


def tick_di(prezzo: float) -> float:
    """Passo della scala Betfair alla quota data."""
    p = float(prezzo)
    for lo, hi, step in ((1.01, 2, 0.01), (2, 3, 0.02), (3, 4, 0.05), (4, 6, 0.1),
                         (6, 10, 0.2), (10, 20, 0.5), (20, 30, 1.0), (30, 50, 2.0),
                         (50, 100, 5.0), (100, 1000, 10.0)):
        if lo <= p < hi:
            return step
    return 10.0


def distanza_tick(basso: float, alto: float) -> Optional[float]:
    """Quanti tick separano due prezzi (approssimato per bande miste)."""
    if basso is None or alto is None or alto <= basso:
        return None
    n = 0.0
    p = float(basso)
    for _ in range(400):
        step = tick_di(p)
        p = round(p + step, 2)
        n += 1
        if p >= float(alto) - 1e-9:
            return n
    return None


# ---------------------------------------------------------------------------
# lettura del sidecar dei punteggi
# ---------------------------------------------------------------------------
def leggi_punteggi(percorso: str) -> List[Tuple[int, int, int, int]]:
    """[(ts_ms, minuto, casa, ospiti)] ordinati, solo i record completi."""
    fuori: List[Tuple[int, int, int, int]] = []
    with open(percorso, "r", encoding="utf-8") as fh:
        for riga in fh:
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            m, h, a = d.get("minute"), d.get("score_home"), d.get("score_away")
            ts = d.get("ts_ms")
            if ts is None or m is None or h is None or a is None:
                continue
            try:
                fuori.append((int(ts), int(m), int(h), int(a)))
            except (TypeError, ValueError):
                continue
    fuori.sort()
    return fuori


def stato_a(punteggi: List[Tuple[int, int, int, int]], ts: int
            ) -> Optional[Tuple[int, int, int]]:
    """(minuto, casa, ospiti) noti al publish time `ts` (nessuna interpolazione:
    si usa l'ultimo record ARRIVATO, ritardo IPS compreso)."""
    lo, hi = 0, len(punteggi) - 1
    trovato = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if punteggi[mid][0] <= ts:
            trovato = punteggi[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    if trovato is None:
        return None
    return trovato[1], trovato[2], trovato[3]


def esiti_veri(punteggi: List[Tuple[int, int, int, int]]
               ) -> Tuple[Optional[Tuple[int, int]], Optional[Tuple[int, int]]]:
    """(punteggio HT, punteggio FT) dal sidecar. None quando non e' osservabile."""
    ht = None
    for _ts, m, h, a in punteggi:
        if m <= 45:
            ht = (h, a)
    ft = (punteggi[-1][2], punteggi[-1][3]) if punteggi else None
    # senza record oltre il 45' non si e' visto il primo tempo finire
    if not any(m > 45 for _ts, m, _h, _a in punteggi):
        ht = None
    if not punteggi or punteggi[-1][1] < 88:
        ft = None
    return ht, ft


# ---------------------------------------------------------------------------
# passata sul raw
# ---------------------------------------------------------------------------
def vincitori(raw: str) -> Dict[str, Dict[str, Any]]:
    """{market_id: {"tipo", "stato_finale", "winner", "n_winner", "runner_status"}}.

    L'ESITO AUTOREVOLE non e' il sidecar dei punteggi: e' il `marketDefinition`
    finale della registrazione, dove Betfair scrive `WINNER`/`LOSER` su ogni
    runner (I3 della Costituzione: «Betfair e' la verita'»). Una passata sola
    sulle righe che contengono `marketDefinition`, come `leggi_catalogo`.
    `winner` resta None se il mercato non e' mai stato visto risolto: in quel
    caso l'esito si dichiara ignoto, MAI dedotto."""
    fuori: Dict[str, Dict[str, Any]] = {}
    with open(raw, "r", encoding="utf-8") as fh:
        for riga in fh:
            if '"marketDefinition"' not in riga:
                continue
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            for mc in d.get("mc") or []:
                md = mc.get("marketDefinition")
                mid = str(mc.get("id") or "")
                if not md or not mid:
                    continue
                stati = {int(r["id"]): str(r.get("status") or "ACTIVE").upper()
                         for r in (md.get("runners") or []) if r.get("id") is not None}
                vinti = [s for s, st in stati.items() if st == "WINNER"]
                fuori[mid] = {
                    "tipo": str(md.get("marketType") or "").upper(),
                    "stato_finale": str(md.get("status") or "").upper(),
                    "winner": (vinti[0] if len(vinti) == 1 else None),
                    "n_winner": len(vinti),
                    "runner_status": stati,
                }
    return fuori


def campiona_evento(cartella: str, event_id: str, *, minuti: List[int],
                    commissione: float) -> List[dict]:
    raw = os.path.join(cartella, f"{event_id}.raw.jsonl")
    sidecar = os.path.join(cartella, f"{event_id}.scores.jsonl")
    if not (os.path.exists(raw) and os.path.exists(sidecar)):
        return []
    punteggi = leggi_punteggi(sidecar)
    if not punteggi:
        return []
    ht_vero, ft_vero = esiti_veri(punteggi)
    esiti_md = vincitori(raw)

    tipi: Dict[str, str] = {}
    stato: Dict[str, Tuple[str, bool]] = {}
    runner_stato: Dict[str, Dict[int, str]] = {}
    # ladder per mercato: {selection_id: {"atb": {prezzo: size}, "atl": {...}}}
    ladder: Dict[str, Dict[int, Dict[str, Dict[float, float]]]] = defaultdict(
        lambda: defaultdict(lambda: {"atb": {}, "atl": {}}))
    presi: Dict[Tuple[str, int], bool] = {}
    prossimo: Dict[str, int] = {}
    fuori: List[dict] = []

    with open(raw, "r", encoding="utf-8") as fh:
        for riga in fh:
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            pt = int(d.get("pt") or 0)
            for mc in d.get("mc") or []:
                mid = str(mc.get("id") or "")
                if not mid:
                    continue
                md = mc.get("marketDefinition")
                if md:
                    tipi[mid] = str(md.get("marketType") or "").upper()
                    stato[mid] = (str(md.get("status") or "OPEN").upper(),
                                  bool(md.get("inPlay")))
                    runner_stato[mid] = {
                        int(r["id"]): str(r.get("status") or "ACTIVE")
                        for r in (md.get("runners") or []) if r.get("id") is not None}
                if tipi.get(mid) not in MERCATI:
                    continue
                # `img=true` e' una IMMAGINE completa del mercato: senza azzerare
                # la ladder i livelli vecchi restano e il libro risulta INCROCIATO
                # (best back > best lay). Misurato su 35760084: 42 immagini.
                if mc.get("img"):
                    ladder[mid] = defaultdict(lambda: {"atb": {}, "atl": {}})
                for rc in mc.get("rc") or []:
                    sid = rc.get("id")
                    if sid is None:
                        continue
                    book = ladder[mid][int(sid)]
                    for chiave in ("atb", "atl"):
                        for coppia in rc.get(chiave) or ():
                            try:
                                prezzo, size = float(coppia[0]), float(coppia[1])
                            except (TypeError, ValueError, IndexError):
                                continue
                            if size <= 0:
                                book[chiave].pop(prezzo, None)
                            else:
                                book[chiave][prezzo] = size

            # campionamento: un solo scatto per (mercato, minuto bersaglio)
            corrente = stato_a(punteggi, pt)
            if corrente is None:
                continue
            minuto, casa, osp = corrente
            for mid, tipo in tipi.items():
                if tipo not in MERCATI:
                    continue
                st_mid, inplay = stato.get(mid, ("", False))
                if st_mid != "OPEN" or not inplay:
                    continue
                if minuto > FINE[tipo]:
                    continue
                # un solo scatto per (mercato, minuto bersaglio). Si avanza con un
                # INDICE invece di riscorrere tutta la griglia a ogni tick: con
                # `--passo 1` la scorsa costava 90 confronti per tick e per mercato.
                # Semantica identica: i bersagli saltati restano e si prendono ai
                # tick successivi, uno per tick.
                idx = prossimo.get(mid, 0)
                while idx < len(minuti) and (minuti[idx] > FINE[tipo]
                                             or presi.get((mid, minuti[idx]))):
                    idx += 1
                prossimo[mid] = idx
                if idx >= len(minuti) or minuto < minuti[idx]:
                    continue
                bersaglio = minuti[idx]
                presi[(mid, bersaglio)] = True
                vero = ht_vero if tipo == "HALF_TIME_SCORE" else ft_vero
                md_info = esiti_md.get(mid) or {}
                vincitore = md_info.get("winner")
                quotate = set()
                for sid in ladder[mid]:
                    sc = nome_scoreline(int(sid))
                    if sc:
                        quotate.add(sc)
                # DEVIG: probabilita' EQUA di mercato = mid fra back e lay,
                # normalizzato a 1 sui runner ATTIVI del mercato. Se meno di
                # `DEVIG_MIN_SELEZIONI` sono prezzate su entrambi i lati, oppure
                # la somma dei pesi e' assurda, NON si normalizza: normalizzare
                # mezzo book inventa probabilita' (stessa regola di misura_k).
                somma_mid = 0.0
                n_mid = 0
                for sid2, book2 in ladder[mid].items():
                    if (runner_stato.get(mid, {}).get(int(sid2), "ACTIVE") or "ACTIVE") != "ACTIVE":
                        continue
                    atl2 = {p: s for p, s in book2["atl"].items() if s > 0}
                    atb2 = {p: s for p, s in book2["atb"].items() if s > 0}
                    if not atl2 or not atb2:
                        continue
                    bl2, bb2 = min(atl2), max(atb2)
                    if bb2 >= bl2 or bl2 <= 1.0 or bb2 <= 1.0:
                        continue
                    somma_mid += 0.5 * (1.0 / bl2 + 1.0 / bb2)
                    n_mid += 1
                devig_ok = bool(n_mid >= DEVIG_MIN_SELEZIONI and somma_mid > 0.5)
                for sid, book in ladder[mid].items():
                    if (runner_stato.get(mid, {}).get(int(sid), "ACTIVE") or "ACTIVE") != "ACTIVE":
                        continue
                    atl = {p: s for p, s in book["atl"].items() if s > 0}
                    atb = {p: s for p, s in book["atb"].items() if s > 0}
                    if not atl:
                        continue
                    best_lay = min(atl)
                    best_back = max(atb) if atb else None
                    # libro INCROCIATO (back >= lay): non e' un prezzo, e' uno
                    # stato transitorio o un residuo di immagine. Si scarta il
                    # lato back e lo si dichiara, mai lo si usa come "prezzo".
                    incrociato = bool(best_back is not None and best_back >= best_lay)
                    if incrociato:
                        best_back = None
                    nome = nome_runner_punteggio(int(sid))
                    sc = nome_scoreline(int(sid))
                    if sc is not None:
                        c_h, c_a = (int(x) for x in sc.split(" - "))
                        raggiungibile = (c_h >= casa and c_a >= osp)
                        distanza = (c_h - casa) + (c_a - osp) if raggiungibile else -1
                    else:
                        raggiungibile, distanza = True, None
                    p_tocco = p_implicita(best_lay, commissione)
                    if p_tocco is None:
                        continue
                    p_back = p_implicita(best_back, commissione) if best_back else None
                    # prezzo MID fra i due lati, arrotondato al tick e tenuto
                    # dentro lo spread: e' il livello (b) di M1 e della misura
                    # appaiata pre-match, qui sul book LIVE.
                    prezzo_mid = None
                    p_mid = None
                    if best_back:
                        grezzo = 2.0 / (1.0 / best_lay + 1.0 / best_back)
                        prezzo_mid = min(max(round_to_tick(grezzo), best_back), best_lay)
                        p_mid = p_implicita(prezzo_mid, commissione)
                    p_equa = None
                    if devig_ok and best_back:
                        p_equa = (0.5 * (1.0 / best_lay + 1.0 / best_back)) / somma_mid
                    esito_md = None
                    if md_info.get("stato_finale") == "CLOSED" and md_info.get("n_winner") == 1:
                        esito_md = 1 if int(sid) == int(vincitore) else 0
                    esito = None
                    if vero is not None:
                        if sc is not None:
                            esito = 1 if (int(sc.split(" - ")[0]), int(sc.split(" - ")[1])) == vero else 0
                        else:
                            fuori_quota = f"{vero[0]} - {vero[1]}" not in quotate
                            nb = nome.lower()
                            if "draw" in nb:
                                esito = 1 if (fuori_quota and vero[0] == vero[1]) else 0
                            elif "home" in nb:
                                esito = 1 if (fuori_quota and vero[0] > vero[1]) else 0
                            elif "away" in nb:
                                esito = 1 if (fuori_quota and vero[1] > vero[0]) else 0
                            else:
                                esito = 1 if fuori_quota else 0
                    fuori.append({
                        "event_id": event_id, "mercato": tipo, "minuto": bersaglio,
                        "minuto_vero": minuto, "punteggio": f"{casa}-{osp}",
                        "selection_id": int(sid), "nome": nome,
                        "aggregato": sc is None,
                        "raggiungibile": bool(raggiungibile),
                        "distanza_gol": distanza,
                        "best_lay": best_lay, "size_lay": atl[best_lay],
                        "prezzo_mid": prezzo_mid, "p_impl_mid": p_mid,
                        "p_equa": p_equa, "esito_md": esito_md,
                        "market_id": mid,
                        "best_back": best_back,
                        "size_back": atb[best_back] if best_back else 0.0,
                        "libro_incrociato": incrociato,
                        "p_impl_tocco": p_tocco, "p_impl_back": p_back,
                        "liability_per_euro": round(best_lay - 1.0, 2),
                        "fascia": fascia_di(p_tocco),
                        "spread_tick": distanza_tick(best_back, best_lay) if best_back else None,
                        "esito": esito,
                    })
    return fuori


# ---------------------------------------------------------------------------
def aggrega(righe: List[dict], *, n_min_uscite: int, distanza_minima: int) -> dict:
    usabili = [r for r in righe
               if r["raggiungibile"] and r["fascia"]
               and (r["distanza_gol"] is None or r["distanza_gol"] >= distanza_minima)]
    gruppi: Dict[Tuple[str, int, str], List[dict]] = defaultdict(list)
    for r in usabili:
        gruppi[(r["mercato"], r["minuto"], r["fascia"])].append(r)

    def med(vs):
        vs = [v for v in vs if v is not None]
        return round(st.median(vs), 4) if vs else None

    fuori = []
    for chiave in sorted(gruppi):
        g = gruppi[chiave]
        con_esito = [r for r in g if r["esito"] is not None]
        uscite = sum(r["esito"] for r in con_esito)
        p_reale = (uscite / len(con_esito)) if con_esito else None
        leve = [r["p_impl_back"] / r["p_impl_tocco"]
                for r in g if r["p_impl_back"] and r["p_impl_tocco"]]
        fuori.append({
            "mercato": chiave[0], "minuto": chiave[1], "fascia": chiave[2],
            "n_celle": len(g), "n_partite": len({r["event_id"] for r in g}),
            "quota_tocco_mediana": med([r["best_lay"] for r in g]),
            "quota_back_mediana": med([r["best_back"] for r in g]),
            "liability_per_euro_mediana": med([r["liability_per_euro"] for r in g]),
            "size_lay_mediana": med([r["size_lay"] for r in g]),
            "size_back_mediana": med([r["size_back"] for r in g]),
            "spread_tick_mediano": med([r["spread_tick"] for r in g]),
            "p_impl_tocco_media": round(sum(r["p_impl_tocco"] for r in g) / len(g), 6),
            "leva_best_back_mediana": med(leve),
            "n_incrociati": sum(1 for r in g if r.get("libro_incrociato")),
            "n_con_esito": len(con_esito), "uscite": uscite,
            "p_reale": round(p_reale, 6) if p_reale is not None else None,
            "misurabile": bool(uscite >= n_min_uscite),
        })
    return {"generato_il": "2026-09-17",
            "fonte": "_live_raw (stream Betfair registrato) + sidecar punteggi",
            "approssimazione": ("misura di PREZZO: nessun flumine, nessuno scanner, "
                                "nessun ordine. La condotta si certifica sul banco comune."),
            "commissione": COMMISSIONE,
            "distanza_minima_gol": distanza_minima,
            "n_osservazioni": len(righe), "n_usabili": len(usabili),
            "righe": fuori}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Superficie quota/liability per minuto")
    ap.add_argument("--dati", default="_live_raw")
    ap.add_argument("--eventi", nargs="*", default=None)
    ap.add_argument("--passo", type=int, default=5)
    ap.add_argument("--distanza-minima", type=int, default=2)
    ap.add_argument("--n-min-uscite", type=int, default=3)
    ap.add_argument("--out", default=os.path.join(
        "Betfair", "omega", "data", "superficie_liability_2026-09-17.json"))
    args = ap.parse_args(argv)

    minuti = list(range(1, 90, max(1, args.passo)))
    eventi = args.eventi
    if not eventi:
        eventi = sorted(n for n in os.listdir(args.dati)
                        if n.isdigit()
                        and os.path.exists(os.path.join(args.dati, n, f"{n}.raw.jsonl"))
                        and os.path.exists(os.path.join(args.dati, n, f"{n}.scores.jsonl")))
    righe: List[dict] = []
    for ev in eventi:
        cartella = os.path.join(args.dati, str(ev))
        try:
            got = campiona_evento(cartella, str(ev), minuti=minuti,
                                  commissione=COMMISSIONE)
        except Exception as exc:                      # pragma: no cover
            print(f"  {ev}: SALTATO ({exc})", flush=True)
            continue
        righe.extend(got)
        print(f"  {ev}: {len(got)} osservazioni", flush=True)

    dati = aggrega(righe, n_min_uscite=args.n_min_uscite,
                   distanza_minima=args.distanza_minima)
    dati["eventi"] = [str(e) for e in eventi]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(dati, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"\nscritto {args.out}  ({dati['n_osservazioni']} osservazioni, "
          f"{dati['n_usabili']} usabili)\n")
    print("{:<16}{:>5}{:<11}{:>7}{:>7}{:>9}{:>9}{:>9}{:>9}{:>8}{:>8}".format(
        "mercato", "min", " fascia", "celle", "part.", "quotaTcc", "quotaBck",
        "liab/EUR", "spreadTk", "leva", "usc."))
    for r in dati["righe"]:
        print("{:<16}{:>5}{:<11}{:>7}{:>7}{:>9}{:>9}{:>9}{:>9}{:>8}{:>8}".format(
            r["mercato"][:15], r["minuto"], " " + r["fascia"], r["n_celle"],
            r["n_partite"],
            "-" if r["quota_tocco_mediana"] is None else f"{r['quota_tocco_mediana']:.1f}",
            "-" if r["quota_back_mediana"] is None else f"{r['quota_back_mediana']:.1f}",
            "-" if r["liability_per_euro_mediana"] is None else f"{r['liability_per_euro_mediana']:.1f}",
            "-" if r["spread_tick_mediano"] is None else f"{r['spread_tick_mediano']:.1f}",
            "-" if r["leva_best_back_mediana"] is None else f"{r['leva_best_back_mediana']:.2f}",
            r["uscite"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
