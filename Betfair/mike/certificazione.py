"""CERTIFICAZIONE DI MIKE — rispetta le condizioni per cui e' stato progettato?

Non si misura se GUADAGNA. Si misura se **si comporta come dice la Costituzione**,
tick per tick, sui dati veri delle partite registrate.

COME FUNZIONA, e perche' e' affidabile: `engine.decide` e `engine.apply_decision`
sono logica PURA, senza rete e senza database. Si possono quindi far girare su
una registrazione Betfair vera (`_live_raw/<id>/<id>.raw.jsonl`, replay col
motore ufficiale `FlumineSimulation`) e osservare OGNI decisione, confrontandola
con le regole scritte. Nessun finto: i prezzi, i gol e i minuti sono quelli che
il bot avrebbe visto davvero.

Ogni controllo qui sotto cita la regola della Costituzione che difende, e ogni
controllo e' CONSERVATIVO: segnala solo quando la violazione e' certa. Un
controllo che non sa decidere tace — un falso allarme su 40.000 tick renderebbe
il rapporto inutile.

I controlli sono divisi per famiglia:

  A. la macchina a stati (§3)
  B. gli ingressi (§3 Fase 1-2, §5, §11)
  C. prezzi e ordini (§4.6, §11)
  D. il green-up (§3 Fase 1, §4.1, §4.2)
  E. la copertura (§3 Fase 3, §4.3)
  F. il rischio (§4.9, §5)
  G. le uscite (§3 Fase 5)
  H. il re-ingresso (§3 Fase 6)
  J. gli ordini in volo (i cinque difetti del 15/09)

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import engine as E


# ---------------------------------------------------------------------------
# il referto
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Violazione:
    """Una regola della Costituzione non rispettata, con il contesto per capirla."""

    codice: str                 # es. "B1"
    regola: str                 # la regola, in una riga
    dettaglio: str              # che cosa e' successo davvero
    stato: str = ""             # lo stato della macchina quando e' successo
    minuto: Optional[int] = None
    gol: Optional[int] = None

    def __str__(self) -> str:
        dove = f"[{self.stato}" + (f" {self.minuto}'" if self.minuto is not None else "")
        dove += (f" {self.gol} gol" if self.gol is not None else "") + "]"
        return f"{self.codice} {dove} {self.regola} -> {self.dettaglio}"


# un controllo guarda la decisione PRIMA che venga applicata: ctx e' lo stato di
# partenza, d e' cio' che il motore ha deciso di fare.
Controllo = Callable[[E.MatchCtx, E.Snapshot, E.Decision, Dict[str, Any]], Optional[str]]

_REGISTRO: List[Tuple[str, str, Controllo, Optional[Controllo]]] = []


def _controllo(codice: str, regola: str, quando: Optional[Controllo] = None):
    """Registra un controllo, e con `quando` dichiara QUANDO ha davvero un caso.

    ⚠️ Senza questo, un referto «zero violazioni» e' ambiguo: non si distingue
    un controllo che ha guardato e approvato da uno che non ha mai avuto
    l'occasione di guardare. Sono due cose diversissime — la prima e' una
    garanzia, la seconda e' un buco — e finche' si contano solo le violazioni
    sembrano identiche.

    `quando` e' una condizione pura sugli stessi argomenti del controllo:
    vera = «questo caso mi riguarda», e allora il controllo viene contato fra i
    SOLLECITATI. Assente = il controllo giudica sempre.
    """
    def _reg(fn: Controllo) -> Controllo:
        _REGISTRO.append((codice, regola, fn, quando))
        return fn
    return _reg


# ---------------------------------------------------------------------------
# utilita' comuni ai controlli
# ---------------------------------------------------------------------------
def _piazzamenti(d: E.Decision) -> List[Any]:
    return [a for a in d.actions if a.kind == "place"]


def _aperture(d: E.Decision) -> List[Any]:
    """Le azioni che AUMENTANO il rischio. Sono quelle che le sicurezze fermano;
    le chiusure non si fermano mai (§5, `_strip_openings`)."""
    return [a for a in _piazzamenti(d) if a.role not in E.CLOSING_ROLES]


def _vive(ctx: E.MatchCtx) -> List[E.Leg]:
    return [l for l in ctx.legs if l.is_live]


def _in_volo(ctx: E.MatchCtx) -> List[E.Leg]:
    """Le gambe che POSSONO essere a mercato adesso.

    ⚠️ 16/09 — i controlli J1 e J2 guardavano solo ``is_live``, cioe' solo le
    gambe che il bot SA vive. Una gamba a esito IGNOTO (``pending_reconcile``)
    puo' essere viva su Betfair esattamente come una 'pending' — la Costituzione
    §4.11 lo dice a chiare lettere («conta SEMPRE nel rischio, peggior caso:
    abbinata per intero») — e il difetto 4 del catalogo del 15/09 e' proprio
    questo: un ordine vivo dichiarato mai piazzato, e un secondo green-up.
    Con la definizione vecchia quel caso i controlli non lo vedevano.
    """
    return [l for l in ctx.legs if l.is_live or l.needs_reconcile]


def _book(snap: E.Snapshot, mercato: str, selezione: str) -> Optional[E.Book]:
    return (snap.books or {}).get((mercato, selezione))


# ===========================================================================
# A. LA MACCHINA A STATI (§3)
# ===========================================================================
@_controllo("A1", "lo stato prodotto deve essere uno stato dichiarato (§3)",
            quando=lambda ctx, snap, d, p: True)
def _a1(ctx, snap, d, params):
    if d.state not in E.STATES:
        return f"stato sconosciuto '{d.state}'"
    return None


@_controllo("A2", "da uno stato TERMINALE non esce nessuna azione (§3)",
            quando=lambda ctx, snap, d, p: ctx.state in E.TERMINAL_STATES)
def _a2(ctx, snap, d, params):
    if ctx.state in E.TERMINAL_STATES and d.actions:
        return (f"stato terminale '{ctx.state}' ma {len(d.actions)} azioni: "
                f"{[a.role for a in d.actions]}")
    return None


@_controllo("A3", "ogni decisione dichiara un motivo leggibile (§8)",
            quando=lambda ctx, snap, d, p: bool(d.actions))
def _a3(ctx, snap, d, params):
    if d.actions and not str(getattr(d, "reason", "") or "").strip():
        return f"{len(d.actions)} azioni senza motivo dichiarato"
    return None


# ===========================================================================
# B. GLI INGRESSI (§3 Fasi 1-2, §5, §11)
# ===========================================================================
@_controllo("B1", "Mike non entra MAI in-play da zero: l'unico ingresso live e' "
                  "il re-ingresso (§11)",
            quando=lambda ctx, snap, d, p: bool(snap.inplay and _aperture(d)))
def _b1(ctx, snap, d, params):
    if not snap.inplay:
        return None
    for a in _aperture(d):
        # il re-ingresso e' l'unica apertura ammessa in-play, e ha ruoli suoi
        if a.role in ("reentry",):
            continue
        # la copertura Over 4.5 aumenta il rischio ma e' una RIDUZIONE di rischio
        # per la posizione (§3 Fase 3): e' prevista in-play e non e' un ingresso.
        if a.role in ("over_cover",):
            continue
        # l'ultimo ingresso PERSIST viene deciso PRIMA del fischio e puo' restare
        # sul book dopo: non e' un ingresso nato in-play.
        if a.role == "under_last":
            continue
        # la SECONDA PUNTATA dopo un gol precoce e' prevista dalla Costituzione
        # (§15.3, "strada C"): non e' un ingresso da ZERO, rinforza una
        # posizione gia' aperta per alzare la quota media. Lo era anche il
        # primo referto che l'aveva segnalata: falso allarme di questo
        # controllo, non difetto del bot.
        if a.role == "under_second":
            aperto = any(float(l.matched or 0.0) > 0 for l in ctx.legs if not l.archived)
            if aperto:
                continue
            return "seconda puntata SENZA una posizione da rinforzare"
        return f"apertura '{a.role}' con partita gia' in gioco"
    return None


@_controllo("B2", "feed stantio: nessun ingresso, le chiusure restano permesse (§5)",
            quando=lambda ctx, snap, d, p: not (snap.feed_fresh and snap.order_fresh))
def _b2(ctx, snap, d, params):
    if snap.feed_fresh and snap.order_fresh:
        return None
    ap = _aperture(d)
    if ap:
        quale = "feed_fresh" if not snap.feed_fresh else "order_fresh"
        return f"{quale}=False ma apre lo stesso: {[a.role for a in ap]}"
    return None


@_controllo("B3", "ordine a esito IGNOTO: via le APERTURE, restano le riduzioni "
                  "di rischio (§5, §4.11)",
            quando=lambda ctx, snap, d, p: E.has_unknown_orders(ctx))
def _b3(ctx, snap, d, params):
    if not E.has_unknown_orders(ctx):
        return None
    ap = _aperture(d)
    if ap:
        gambe = [l.ref for l in ctx.legs if l.needs_reconcile]
        return (f"gambe a esito ignoto {gambe} ma apre lo stesso: "
                f"{[a.role for a in ap]}")
    return None


@_controllo("B4", "ingresso pre-match solo con la quota BACK Under 3.5 nella "
                  "banda dei parametri (§3 Fase 1)",
            quando=lambda ctx, snap, d, p: any(a.role == 'under_entry' for a in _piazzamenti(d)))
def _b4(ctx, snap, d, params):
    lo = float(params.get("pre_entry_price_min") or 0.0)
    hi = float(params.get("pre_entry_price_max") or 0.0)
    if lo <= 0 or hi <= 0:
        return None
    for a in _piazzamenti(d):
        if a.role != "under_entry":
            continue
        bk = _book(snap, E.MARKET_OU35, E.SEL_UNDER)
        q = getattr(bk, "best_back", None) if bk else None
        if q is None:
            continue                      # senza book non si giudica (§11 lo vieta gia')
        if not (lo - 1e-9 <= float(q) <= hi + 1e-9):
            return (f"ingresso con quota back {q} fuori dalla banda "
                    f"[{lo}, {hi}]")
    return None


@_controllo("B5", "i cicli pre-match non superano `pre_max_cycles` (§3 Fase 1)",
            quando=lambda ctx, snap, d, p: any(a.role == 'under_entry' for a in _piazzamenti(d)))
def _b5(ctx, snap, d, params):
    tetto = int(params.get("pre_max_cycles") or 0)
    if tetto <= 0:
        return None
    if any(a.role == "under_entry" for a in _piazzamenti(d)) and ctx.cycle_no >= tetto:
        return f"ingresso al ciclo {ctx.cycle_no} col tetto a {tetto}"
    return None


# ===========================================================================
# C. PREZZI E ORDINI (§4.6, §11)
# ===========================================================================
@_controllo("C1", "ogni ordine ha un prezzo dentro la scala Betfair e una size "
                  "positiva (§4.6)",
            quando=lambda ctx, snap, d, p: bool(_piazzamenti(d)))
def _c1(ctx, snap, d, params):
    for a in _piazzamenti(d):
        p, s = float(a.price), float(a.size)
        # `price_ok` e' il giudice VERO di Mike su un prezzo (presente, finito,
        # > 1.0): non se ne scrive un altro qui, o si finirebbe a certificare
        # una regola diversa da quella che il bot applica.
        if not E.price_ok(p):
            return f"'{a.role}' a quota {p}, che Mike stesso giudica inutilizzabile"
        if not (s > 0):
            return f"'{a.role}' con size {s}"
        if abs(p - E.round_to_tick(p)) > 1e-9:
            return f"'{a.role}' a quota {p}, che non e' un tick valido"
    return None


@_controllo("C2", "Mike non inventa prezzi: nessun ordine su una linea assente "
                  "dal feed (§11)",
            quando=lambda ctx, snap, d, p: bool(_piazzamenti(d)))
def _c2(ctx, snap, d, params):
    for a in _piazzamenti(d):
        if _book(snap, a.market, a.selection) is None:
            return f"'{a.role}' su {a.market}/{a.selection}, che nello snapshot non c'e'"
    return None


@_controllo("C3", "nessun ordine su un mercato che non e' APERTO (§3 Fase 1)",
            quando=lambda ctx, snap, d, p: bool(_piazzamenti(d)))
def _c3(ctx, snap, d, params):
    for a in _piazzamenti(d):
        bk = _book(snap, a.market, a.selection)
        if bk is not None and bk.status not in ("OPEN",):
            return f"'{a.role}' su un mercato in stato '{bk.status}'"
    return None


# ===========================================================================
# D. IL GREEN-UP (§3 Fase 1, §4.1, §4.2)
# ===========================================================================
@_controllo("D1", "le esposizioni vengono dai FILL, mai dalla size chiesta: la "
                  "gamba di green non supera l'abbinato (§4.1)",
            quando=lambda ctx, snap, d, p: any(a.role in ('under_green', 'ko_green', 'reentry_green') for a in _piazzamenti(d)))
def _d1(ctx, snap, d, params):
    for a in _piazzamenti(d):
        if a.role not in ("under_green", "ko_green", "reentry_green"):
            continue
        # quanto e' abbinato sulla stessa selezione, al netto delle gambe archiviate
        abbinato = sum(float(l.matched or 0.0) for l in ctx.legs
                       if not l.archived and l.market == a.market
                       and l.selection == a.selection and l.side != a.side)
        if abbinato <= 0:
            return f"green '{a.role}' senza nessun abbinato da chiudere"
        # la lay di green vale al massimo l'abbinato riportato al nuovo prezzo:
        # con una tolleranza generosa (il rapporto di quote non supera ~2x qui)
        if float(a.size) > abbinato * 3.0 + 0.01:
            return (f"green '{a.role}' da {a.size} su un abbinato di "
                    f"{round(abbinato, 2)}: dimensionato sulla size chiesta?")
    return None


@_controllo("D2", "pre-match non si chiude mai in perdita: il green e' a quota "
                  "MIGLIORE dell'ingresso (§3 Fase 1)",
            quando=lambda ctx, snap, d, p: (not snap.inplay) and any(a.role == 'under_green' for a in _piazzamenti(d)))
def _d2(ctx, snap, d, params):
    if snap.inplay:
        return None                        # in-play le uscite in perdita esistono (§3 Fase 5)
    for a in _piazzamenti(d):
        if a.role != "under_green" or a.side != "lay":
            continue
        apertura = next((l for l in reversed(ctx.legs)
                         if not l.archived and l.role == "under_entry"
                         and l.market == a.market and float(l.matched or 0) > 0), None)
        if apertura is None or not apertura.avg_price:
            continue
        # LAY di green: si banca a quota PIU' BASSA di quella a cui si e' puntato
        if float(a.price) > float(apertura.avg_price) + 1e-9:
            return (f"green pre-match in perdita: lay a {a.price} su un back "
                    f"abbinato a {apertura.avg_price}")
    return None


def _ritira_banca_pre(ctx, snap, d) -> bool:
    """Prima del fischio, fuori da una chiusura manuale, la decisione ritira la
    banca di green appoggiata mentre la posizione e' ancora aperta."""
    if snap.inplay or ctx.flatten_pending or ctx.state not in ("PRE_OPEN", "HOLD"):
        return False
    if not any(a.kind == "cancel" and a.role == "under_green" for a in d.actions):
        return False
    w, l = E.exposure(ctx.legs, E.MARKET_OU35, E.SEL_UNDER)
    return abs(w - l) >= 0.01


@_controllo("D3", "pre-partita: la banca di green appoggiata resta fino al fischio, "
                  "non si ritira ne' si sostituisce con una chiusura al mercato "
                  "(piano Mike 29/09, M2.1)",
            quando=lambda ctx, snap, d, p: (not snap.inplay) and ctx.state in ("PRE_OPEN", "HOLD"))
def _d3(ctx, snap, d, params):
    if _ritira_banca_pre(ctx, snap, d):
        return f"banca pre-partita ritirata con la posizione aperta: {d.reason}"
    return None


def _segno_ultimo_ingresso(snap, params) -> float:
    return float(snap.ko_at) - float(params.get("pre_last_entry_min") or 0.0) * 60.0


@_controllo("B6", "dopo il segno dei 10 minuti al piu' UN ingresso (l'ultimo), e solo "
                  "da piatto (piano Mike 29/09, M2.4)",
            quando=lambda ctx, snap, d, p: (not snap.inplay)
            and any(a.role == 'under_entry' for a in _piazzamenti(d))
            and snap.now >= _segno_ultimo_ingresso(snap, p))
def _b6(ctx, snap, d, params):
    segno = _segno_ultimo_ingresso(snap, params)
    if ctx.state != "WATCH":
        return f"ingresso dopo il segno da {ctx.state} (non da piatto)"
    dopo = [l.ref for l in ctx.legs if float(l.placed_at or 0.0) >= segno]
    if dopo:
        return f"secondo ingresso dopo il segno: gia' nate {dopo}"
    return None


def _ultimo_ingresso_dovuto(ctx, snap, d, params) -> bool:
    """30/09 (ondata 2, revisione BASSO): al segno dei 10 minuti Mike e' PIATTO
    (``WATCH``, nessuna gamba nata dopo il segno) e TUTTE le condizioni
    d'ingresso sono vere, lette qui dalla regola del piano (M2.4) e non dal
    motore: bot acceso, nessuna chiusura manuale, prezzi vivi, prima del
    fischio, cicli sotto il massimo, pausa dopo il giro chiuso passata, libro
    dell'Under 3,5 aperto con la quota nella banda, liquidita' al miglior back,
    spread nel massimo, rischio della puntata dentro il tetto, veto spento,
    nessun ordine a esito ignoto, aperture non ferme. Conservativo: se una
    sola condizione manca, nessun caso."""
    if snap.inplay or ctx.state != "WATCH":
        return False
    segno = _segno_ultimo_ingresso(snap, params)
    if not (segno <= float(snap.now) < float(snap.ko_at)):
        return False
    if any(float(l.placed_at or 0.0) >= segno for l in ctx.legs):
        return False
    if (params.get("pre_enabled") is not True or ctx.no_reentry or ctx.flatten_pending
            or getattr(ctx, "chiuso_dall_utente", False)):
        return False
    if not (snap.feed_fresh and snap.order_fresh):
        return False
    if E.has_unknown_orders(ctx) or isinstance(getattr(ctx, "aperture_ferme", None), dict):
        return False
    if int(ctx.cycle_no or 0) >= int(params.get("pre_max_cycles") or 0):
        return False
    pausa = float(params.get("pre_reentry_cooldown_s") or 0.0)
    if ctx.last_green_at is not None and float(snap.now) - float(ctx.last_green_at) < pausa:
        return False
    bk = _book(snap, E.MARKET_OU35, E.SEL_UNDER)
    if bk is None or not E.operabile(bk) or bk.inplay or not E.price_ok(bk.best_back):
        return False
    lo = float(params.get("pre_entry_price_min") or 0.0)
    hi = float(params.get("pre_entry_price_max") or 0.0)
    if not (lo - 1e-9 <= float(bk.best_back) <= hi + 1e-9):
        return False
    stake = float(params.get("stake") or 0.0)
    if float(bk.back_size or 0.0) < stake * float(params.get("pre_min_back_size_factor") or 1.0):
        return False
    if bk.best_lay is not None:
        t = E.ticks_between(bk.best_back, bk.best_lay)
        if t is None or t > int(params.get("pre_max_spread_ticks") or 0):
            return False
    if stake > E.liability_room(ctx, params) + 1e-9:
        return False
    # il veto sulla P calibrata (acceso di serie) e' una rinuncia prevista: con
    # un veto gia' scattato, o che scatta su questo libro, nessun caso
    if E.veto_u35_acceso(params):
        if isinstance(getattr(ctx, "veto_u35", None), dict):
            return False
        veto = E.valuta_veto_under35(snap, params, float(bk.best_back), "persist")
        if veto is not None and veto.get("esito") == "veto":
            return False
    return True


@_controllo("B7", "al segno dei 10 minuti, da PIATTO e con tutte le condizioni d'ingresso "
                  "vere, l'ultimo ingresso AVVIENE (piano Mike 29/09, M2.4; decisione "
                  "dell'utente 30/09: riprova fino al fischio)",
            quando=lambda ctx, snap, d, p: _ultimo_ingresso_dovuto(ctx, snap, d, p))
def _b7(ctx, snap, d, params):
    if not _ultimo_ingresso_dovuto(ctx, snap, d, params):
        return None
    if any(a.role == "under_entry" for a in _piazzamenti(d)):
        return None
    return (f"piatto al segno con libro Under 3,5 buono e nessun ingresso: "
            f"{d.state} - {d.reason}")


# ===========================================================================
# E. LA COPERTURA (§3 Fase 3, §4.3)
# ===========================================================================
@_controllo("E1", "con 3+ gol non si copre piu': la gestione passa al cash-out "
                  "(§3 Fase 3)",
            quando=lambda ctx, snap, d, p: snap.goals is not None and int(snap.goals) >= 3)
def _e1(ctx, snap, d, params):
    if snap.goals is None or int(snap.goals) < 3:
        return None
    for a in _piazzamenti(d):
        if a.role == "over_cover":
            return f"copertura a {snap.goals} gol"
    return None


@_controllo("E2", "la copertura si dimensiona con X = factor*S/((Po-1)(1-c)) "
                  "(§4.3)",
            quando=lambda ctx, snap, d, p: any(a.role == 'over_cover' for a in _piazzamenti(d)))
def _e2(ctx, snap, d, params):
    for a in _piazzamenti(d):
        if a.role != "over_cover":
            continue
        if a.side == "lay":
            # 29/09 (P5, M3.1): copertura come BANCA Under 4,5, X = factor*L/(1-c)
            # (lettura A), non dipende dalla quota. Stessa tolleranza della punta.
            # L'importo si VERIFICA (non solo il tetto): residuo dai fill x frazione
            # della tranche, al centesimo; piu' piccolo solo se il tetto per
            # partita lo riduce (rischio al limite dentro lo spazio).
            liab = E.under_liability(ctx.legs)
            if liab <= 0:
                return f"banca di copertura da {a.size} senza nessun Under abbinato"
            c_l = float(params.get("commission_pct", 5.0)) / 100.0
            f_l = float(params.get("cover_profit_factor", 1.2))
            gia = E.cover_matched_value(ctx.legs, c_l)
            residuo = E.cover_residual_lay(liab, c_l, f_l, gia)
            stadio = int(ctx.cover_stage or 0)
            if stadio in (1, 2) and ctx.early_goal_at is None:
                stadio = 0
            frazione, _decl = E.frazione_copertura(stadio, params, residuo)
            x = round(residuo * frazione, 2)
            size = float(a.size)
            if abs(size - x) <= 0.011:
                continue
            spazio = E.liability_room(ctx, params)
            # piu' piccola solo se il tetto per partita c'e' e la tiene fuori
            if size < x and spazio != float("inf") \
                    and x * (float(a.price) - 1.0) > spazio + 0.011 \
                    and size * (float(a.price) - 1.0) <= spazio + 0.011:
                continue
            return (f"banca di copertura {a.size} diversa dall'importo previsto {x} "
                    f"(liability {liab}, gia' coperto {round(gia, 2)}, frazione "
                    f"{round(frazione, 3)})")
        if a.side != "back":
            continue
        # 30/09 (ondata 2, revisione M8): la forma di serie (PUNTA Over 4,5).
        # Prima leggeva ``params["commission"]`` e ``params["cover_factor"]``,
        # che non esistono (valevano sempre 0,05 e 1,2), e segnalava solo un
        # ordine oltre il 135 % del pieno. Adesso: parametri VERI e importo
        # VERIFICATO come per la banca (residuo sui fill x frazione della
        # tranche, dimensionato sul miglior back del libro), piu' piccolo solo
        # se il tetto per partita lo riduce, piu' grande solo entro
        # l'arrotondamento legale dichiarato (``cover_max_overshoot_pct``).
        liab = E.under_liability(ctx.legs)
        if liab <= 0:
            return f"copertura da {a.size} senza nessun Under abbinato"
        bk = _book(snap, E.MARKET_OU45, E.SEL_OVER)
        best = getattr(bk, "best_back", None) if bk is not None else None
        if not best or not E.price_ok(best):
            continue                          # senza prezzo non si giudica
        c_b = float(params.get("commission_pct", 5.0)) / 100.0
        f_b = float(params.get("cover_profit_factor", 1.2))
        gia = E.cover_matched_value(ctx.legs, c_b)
        pieno = E.cover_residual(liab, float(best), c_b, f_b, gia)
        stadio = int(ctx.cover_stage or 0)
        if stadio in (1, 2) and ctx.early_goal_at is None:
            stadio = 0
        frazione, _decl = E.frazione_copertura(stadio, params, pieno)
        x = round(pieno * frazione, 2)
        size = float(a.size)
        if params.get("exact_sizes", True):
            # importi esatti (il default): la copertura va al centesimo
            lo, hi = x - 0.011, x + 0.011
        else:
            # legalizzata .it (min 2,00 / passo 0,50): per eccesso entro il
            # tetto dichiarato, oppure per difetto (il ripiego ``floor``)
            margine = 1.0 + max(0.0, float(params.get("cover_max_overshoot_pct") or 0.0)) / 100.0
            lo = E.legalize_back_size(x, "floor")[0] - 0.011
            hi = x * margine + 0.011
        if lo <= size <= hi:
            continue
        spazio = E.liability_room(ctx, params)
        if size < x and spazio != float("inf") and size <= spazio + 0.011 \
                and x > spazio + 0.011:
            continue                          # ridotta dal tetto per partita
        return (f"copertura {a.size} diversa dall'importo previsto {x} (liability {liab}, "
                f"gia' coperto {round(gia, 2)}, frazione {round(frazione, 3)}, best "
                f"{best}, commissione {c_b}, fattore {f_b})")
    return None


# ===========================================================================
# F. IL RISCHIO (§4.9, §5)
# ===========================================================================
@_controllo("F1", "`max_liability_per_match` e' un tetto DENTRO il motore (§4.9)",
            quando=lambda ctx, snap, d, p: bool(float(p.get('max_liability_per_match') or 0) > 0 and _aperture(d)))
def _f1(ctx, snap, d, params):
    tetto = float(params.get("max_liability_per_match") or 0.0)
    if tetto <= 0:
        return None
    ap = _aperture(d)
    if not ap:
        return None
    spazio = E.liability_room(ctx, params)
    if spazio <= 0:
        return (f"tetto di rischio gia' pieno (spazio {round(spazio, 2)}) ma apre: "
                f"{[a.role for a in ap]}")
    return None


@_controllo("F2", "a bot fermo / stop giornaliero non si apre niente (§5, §11)",
            quando=lambda ctx, snap, d, p: p.get('pre_enabled') is False and p.get('reentry_enabled') is False)
def _f2(ctx, snap, d, params):
    if params.get("pre_enabled") is False and params.get("reentry_enabled") is False:
        ap = [a for a in _aperture(d) if a.role in ("under_entry", "under_last", "reentry")]
        if ap:
            return f"ingressi disabilitati ma apre: {[a.role for a in ap]}"
    return None


# ===========================================================================
# G. LE USCITE (§3 Fase 5)
# ===========================================================================
@_controllo("G1", "l'uscita in perdita esiste solo con 2, 3 o 4 gol totali "
                  "(§3 Fase 5)",
            quando=lambda ctx, snap, d, p: d.state == 'LIVE_CLOSING' and ctx.state != 'LIVE_CLOSING')
def _g1(ctx, snap, d, params):
    # si giudica SOLO l'istante in cui si ENTRA in chiusura, e solo sul motivo
    # di QUESTA decisione: `ctx.close_reason` e' persistente e resta scritto da
    # una chiusura precedente, quindi accusarebbe decisioni innocenti.
    if d.state != "LIVE_CLOSING" or ctx.state == "LIVE_CLOSING":
        return None
    motivo = str(getattr(d, "reason", "") or "").lower()
    if "perdita" not in motivo and "loss" not in motivo:
        return None
    # il cap di perdita per evento (`event_loss_cap_pct`) chiude a QUALSIASI
    # minuto e con qualsiasi punteggio: e' una sicurezza, non l'uscita a
    # modello della Fase 5 (§5, la precedenza e' profitto -> intelligente ->
    # uscita in perdita -> cap).
    if "cap" in motivo or "flatten" in motivo or "manual" in motivo:
        return None
    g = snap.goals
    if g is None:
        return None
    if int(g) < 2 or int(g) > 4:
        return (f"uscita in perdita con {g} gol (ammessa solo con 2, 3 o 4) "
                f"- motivo dichiarato: '{getattr(d, 'reason', '')}'")
    return None


# 29/09 (PIANO_MODIFICHE_MIKE, pacchetto P1): il cancello delle uscite. Le
# uscite che bloccano un PROFITTO partono da sole; resta da firmare SOLO
# l'uscita che puo' chiudere IN PERDITA, e ognuna chiede la SUA firma (M8.1).
# Il tetto di perdita partita (``loss_cap``) non esiste piu' (M4.5).
#
# 30/09 (ondata 2 del banco, revisione A1): G2 riconosceva la "perdita" con la
# STESSA regola del motore (il ``close_reason`` ``loss_*``): un'uscita in
# perdita classificata male dal motore (motivo ``profit`` su una chiusura che
# blocca un negativo) passava muta. Adesso la perdita la dice il NUMERO: il
# netto che la chiusura blocca, calcolato qui sulle gambe abbinate piu' gli
# ordini di chiusura come se si abbinassero (``valore_uscita``). Il motivo del
# motore serve solo a riconoscere la firma (la firma vale per QUEL motivo).
_SOGLIA_PERDITA = 0.05          # euro: sotto e' arrotondamento, non una perdita
_RUOLI_USCITA = ("under_green", "ko_green", "under_close", "over_close", "reentry_green")


def _categoria(d: E.Decision) -> Optional[str]:
    """La categoria dell'uscita dai RUOLI degli ordini (la chiave della firma e'
    ``categoria|c<ciclo>``, piano 29/09 M8.1). Scritta qui, non presa dal
    cancello del motore."""
    ruoli = {a.role for a in _piazzamenti(d)}
    if ruoli & {"under_close", "over_close"}:
        return "chiusura"
    if "ko_green" in ruoli:
        return "ko_green"
    if "under_green" in ruoli:
        return "green_pre"
    if "reentry_green" in ruoli:
        return "reentry_green"
    return None


def _prezzo_di_abbinamento(a: Any, snap: E.Snapshot) -> float:
    """A che prezzo si abbina la chiusura: una banca al piu' al suo limite, e
    prima al miglior lay se e' meglio (piu' basso); una punta almeno al suo
    limite, e prima al miglior back se e' meglio (piu' alto). E' cio' che il
    mercato darebbe adesso, non il limite peggiore."""
    p = float(a.price)
    bk = _book(snap, a.market, a.selection)
    if str(a.side) == "lay":
        migliore = getattr(bk, "best_lay", None) if bk is not None else None
        return min(p, float(migliore)) if migliore and E.price_ok(migliore) else p
    migliore = getattr(bk, "best_back", None) if bk is not None else None
    return max(p, float(migliore)) if migliore and E.price_ok(migliore) else p


def valore_uscita(ctx: E.MatchCtx, snap: E.Snapshot, d: E.Decision,
                  params: Dict[str, Any]) -> Optional[float]:
    """Il netto (commissione compresa) che la chiusura di questa decisione
    BLOCCA, nel caso MIGLIORE: le gambe abbinate piu' gli ordini di chiusura
    come se si abbinassero per intero, e il P&L di ogni totale gol ancora
    possibile (quelli gia' segnati non si tolgono). Il migliore dei casi:
    un'uscita che anche nel caso migliore chiude in negativo e' certamente in
    perdita (controllo conservativo: una chiusura parziale non viene accusata).
    None = nessun ordine di chiusura."""
    chiusure = [a for a in _piazzamenti(d) if a.role in _RUOLI_USCITA]
    if not chiusure:
        return None
    gambe = [l for l in ctx.legs if not l.archived and float(l.matched or 0.0) > 0]
    for i, a in enumerate(chiusure):
        prezzo = _prezzo_di_abbinamento(a, snap)
        gambe.append(E.Leg(role=str(a.role), market=str(a.market), selection=str(a.selection),
                           side=str(a.side), price=prezzo, size=float(a.size),
                           matched=float(a.size), avg_price=prezzo,
                           ref=f"_ipotesi_uscita_{i}", status="open"))
    c = float(params.get("commission_pct", 5.0)) / 100.0
    per_totale = E.net_pnl_by_total(gambe, c)
    gia = int(snap.goals) if snap.goals is not None else 0
    possibili = [v for t, v in per_totale.items() if t >= gia]
    return max(possibili) if possibili else None


def _nasce_chiusura_in_perdita(ctx, snap, d, params) -> bool:
    """Una chiusura in perdita NASCE in questa decisione: ordini di uscita che,
    dal numero, bloccano un netto negativo, partendo da uno stato che non e'
    gia' una chiusura in corso (il riprezzo/residuo di un'uscita firmata e' la
    stessa uscita). Il cash out dell'utente (``flatten_pending``, ruolo
    ``manual_close``) E' la sua firma e non e' un caso."""
    if ctx.state in E.STATI_USCITA_IN_CORSO or ctx.flatten_pending:
        return False
    if str(d.updates.get("close_reason") or "") == "loss_cap":
        return True
    v = valore_uscita(ctx, snap, d, params)
    return v is not None and v < -_SOGLIA_PERDITA


def firma_valida(ctx: E.MatchCtx, d: E.Decision, now: float) -> bool:
    """La firma dell'utente vale per QUESTA chiusura: proposta viva e firma
    con la STESSA chiave, che e' la chiave di questa uscita (categoria dai
    ruoli, ciclo corrente), lo STESSO motivo, e non scaduta
    (``APPROVAZIONE_TTL_S``)."""
    prop = ctx.uscita_proposta if isinstance(ctx.uscita_proposta, dict) else None
    firma = ctx.uscita_approvata if isinstance(ctx.uscita_approvata, dict) else None
    if prop is None or firma is None:
        return False
    cat = _categoria(d)
    chiave = f"{cat}|c{int(ctx.cycle_no or 0)}" if cat else None
    if firma.get("chiave") != prop.get("chiave") or prop.get("chiave") != chiave:
        return False
    if str(prop.get("close_reason") or "") != str(d.updates.get("close_reason") or ""):
        return False
    try:
        return float(now) - float(firma.get("at")) <= float(E.APPROVAZIONE_TTL_S)
    except (TypeError, ValueError):
        return False


@_controllo("G2", "a uscite MANUALI nessuna chiusura che blocca un netto NEGATIVO parte "
                  "senza la SUA firma (stessa chiave, stesso motivo, non scaduta), e il "
                  "tetto di perdita partita non chiude mai (piano Mike 29/09, M4.5, M8.1)",
            quando=lambda ctx, snap, d, p: _nasce_chiusura_in_perdita(ctx, snap, d, p))
def _g2(ctx, snap, d, params):
    if not _nasce_chiusura_in_perdita(ctx, snap, d, params):
        return None
    if str(d.updates.get("close_reason") or "") == "loss_cap":
        return "chiusura per tetto di perdita partita: tolto il 29/09 (M4.5)"
    if params.get("uscite_automatiche") is True:
        return None
    if firma_valida(ctx, d, snap.now):
        return None
    valore = valore_uscita(ctx, snap, d, params)
    return (f"chiusura che blocca {valore:+.2f} (motivo del motore "
            f"'{d.updates.get('close_reason') or '-'}') partita senza la sua firma: "
            f"{[a.role for a in _piazzamenti(d)]}")


def _bloccato_uscita_rientro(ctx, snap) -> Optional[float]:
    """P&L (lordo) che la chiusura al mercato del rientro bloccherebbe adesso:
    esposizione della selezione Under 4,5 chiusa al miglior prezzo del libro.
    None = non calcolabile (libro o prezzo assente)."""
    from Betfair.stream.trading.greenup import compute_greenup

    w, l = E.exposure(ctx.legs, E.MARKET_OU45, E.SEL_UNDER)
    bk = snap.book(E.MARKET_OU45, E.SEL_UNDER)
    if bk is None:
        return None
    plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                           best_lay_price=bk.best_lay, fraction=1.0)
    if not plan.actionable:
        return None
    return round(float(min(plan.expected_if_win, plan.expected_if_lose)), 2)


def _proposta_di_uscita(d: E.Decision) -> bool:
    """Una proposta d'USCITA della strategia (``gate_uscite``). 01/10: la
    proposta del RESIDUO SCOPERTO (``residuo_scoperto``) non lo e': e' cio' che
    Mike non riesce a chiudere da solo, la giudicano L1 e L2."""
    prop = d.updates.get("uscita_proposta")
    return isinstance(prop, dict) and not prop.get("residuo_scoperto")


@_controllo("G3", "un'uscita in PROFITTO non resta mai una proposta: la esegue il bot "
                  "anche a uscite manuali (piano Mike 29/09, M1.1, M4.1-M4.4)",
            quando=lambda ctx, snap, d, p: _proposta_di_uscita(d))
def _g3(ctx, snap, d, params):
    prop = d.updates.get("uscita_proposta")
    if not _proposta_di_uscita(d):
        return None
    motivo = str(prop.get("close_reason") or "")
    if motivo.startswith("loss"):
        return None
    if motivo == "reentry_time":
        # 30/09 (decisione dell'utente): la chiusura a tempo del rientro resta
        # proposta SOLO in perdita. Il P&L si ricalcola qui dalle gambe e dal
        # libro (non dalla telemetria del motore): chiudere al miglior prezzo
        # la selezione del rientro.
        bloccato = _bloccato_uscita_rientro(ctx, snap)
        if bloccato is None or bloccato < 0:
            return None
        return (f"uscita a tempo del rientro in profitto ({bloccato:+.2f}) lasciata come "
                f"proposta: {prop.get('motivo')}")
    if isinstance(d.updates.get("veto_u35"), dict):
        return None                      # chiusura del veto pre-partita: in perdita
    return (f"uscita in profitto ({prop.get('categoria')}, motivo {motivo or '-'}) lasciata "
            f"come proposta: {prop.get('motivo')}")


# ===========================================================================
# L. IL MINIMO DI BETFAIR .it E LA VERITA' SULLA CHIUSURA (01/10, Ashdod v
#    Maccabi Herzliya, LIVE: banca di chiusura 0,43 rifiutata INVALID_BET_SIZE 21
#    volte, poi «chiuso (profit)» con la copertura ancora a mercato)
# ===========================================================================
def _sotto_minimo_listino(a: Any) -> bool:
    """Scritto QUI con i minimi della fonte unica del listino (non con la guardia
    del motore): punta sotto 1,00, banca sotto 1,00, al centesimo."""
    from Betfair.stream.trading.minimi_it import IT_MIN_BACK, IT_MIN_LAY

    # minimi di betfair.it (fonte unica, ordine dell'utente del 01/10): 1,00 / 1,00
    minimo = IT_MIN_LAY if str(a.side) == "lay" else IT_MIN_BACK
    return round(float(a.size or 0.0), 2) < minimo - 0.0005


def _punta_sotto_floor(a: Any, params: Dict[str, Any]) -> bool:
    """02/10: una PUNTA d'apertura sotto l'importo finale minimo del place-and-trim
    (0,50, floor di legge): nessuna via la rende piazzabile. Con ``exact_sizes``
    spento il servizio la porta al minimo (legalizzata): non e' una violazione."""
    from Betfair.stream.trading.minimi_it import SUBMIN_IMPORTO_FINALE_MIN

    if str(a.side) != "back" or a.role in E.CLOSING_ROLES:
        return False
    if not (params or {}).get("exact_sizes", True):
        return False
    return round(float(a.size or 0.0), 2) < SUBMIN_IMPORTO_FINALE_MIN - 0.0005


@_controllo("L1", "nessun ordine di CHIUSURA sotto il minimo Betfair .it (punta 1,00, banca "
                  "1,00), nessuna BANCA sotto 1,00 in assoluto e nessuna PUNTA d'apertura "
                  "sotto 0,50 (floor del place-and-trim): Betfair le rifiuta per taglia "
                  "(01/10, INVALID_BET_SIZE)",
            quando=lambda ctx, snap, d, p: bool(_piazzamenti(d)))
def _l1(ctx, snap, d, params):
    sotto = [a for a in _piazzamenti(d)
             if ((a.role in E.CLOSING_ROLES or str(a.side) == "lay") and _sotto_minimo_listino(a))
             or _punta_sotto_floor(a, params)]
    if sotto:
        a = sotto[0]
        return f"ordine '{a.role}' {a.side} {float(a.size):.2f} @ {a.price} sotto il minimo"
    return None


@_controllo("L2", "mai «chiuso» (FLAT) con una posizione ancora in gioco che un ordine puo' "
                  "chiudere: il residuo si dichiara (chiusura parziale) e va all'utente (01/10)",
            quando=lambda ctx, snap, d, p: d.state == "FLAT")
def _l2(ctx, snap, d, params):
    if d.state != "FLAT":
        return None
    aperte = E.live_open_selections(ctx.legs, snap.goals)
    if not aperte:
        return None
    c = float(params.get("commission_pct", 5.0)) / 100.0
    if E.residuo_non_chiudibile(ctx, snap, params, c):
        return None                     # resto sotto il centesimo: nessun ordine lo chiude
    return f"FLAT ('{d.reason}') con esposizione viva su {aperte}"


# ===========================================================================
# H. IL RE-INGRESSO (§3 Fase 6)
# ===========================================================================
@_controllo("H1", "il re-ingresso live avviene UNA volta sola per partita "
                  "(§3 Fase 6)",
            quando=lambda ctx, snap, d, p: any(a.role == 'reentry' for a in _piazzamenti(d)))
def _h1(ctx, snap, d, params):
    if ctx.reentry_done and any(a.role == "reentry" for a in _piazzamenti(d)):
        return "secondo re-ingresso sulla stessa partita"
    return None


@_controllo("H2", "il re-ingresso vuole 1 o 2 gol e il primo tempo "
                  "(§3 Fase 6; 1 o 2 gol dal 29/09, piano Mike M6.1)",
            quando=lambda ctx, snap, d, p: any(a.role == 'reentry' for a in _piazzamenti(d)))
def _h2(ctx, snap, d, params):
    if not any(a.role == "reentry" for a in _piazzamenti(d)):
        return None
    if snap.goals is not None and int(snap.goals) not in (1, 2):
        return f"re-ingresso con {snap.goals} gol"
    if snap.minute is not None and int(snap.minute) > 45:
        return f"re-ingresso al {snap.minute}'"
    return None


# ===========================================================================
# J. GLI ORDINI IN VOLO — i cinque difetti del 15/09
# ===========================================================================
@_controllo("J1", "mai due gambe IN VOLO con lo stesso ruolo, ciclo e lato "
                  "(freno anti-duplicato, 15/09)",
            quando=lambda ctx, snap, d, p: bool(_in_volo(ctx)))
def _j1(ctx, snap, d, params):
    visti: Dict[tuple, str] = {}
    for l in _in_volo(ctx):
        k = (l.role, int(l.cycle_no or 0), l.side, l.market, l.selection)
        if k in visti:
            return (f"due gambe in volo identiche: '{visti[k]}' e '{l.ref}' "
                    f"({l.role} ciclo {l.cycle_no} {l.side})")
        visti[k] = l.ref
    return None


@_controllo("J2", "non si piazza una gamba di chiusura se ce n'e' gia' una IN VOLO "
                  "con lo stesso ruolo e ciclo (15/09)",
            quando=lambda ctx, snap, d, p: any(a.role in E.CLOSING_ROLES for a in _piazzamenti(d)))
def _j2(ctx, snap, d, params):
    for a in _piazzamenti(d):
        if a.role not in E.CLOSING_ROLES:
            continue
        gia = next((l for l in _in_volo(ctx)
                    if l.role == a.role and int(l.cycle_no or 0) == int(ctx.cycle_no or 0)
                    and l.side == a.side and l.market == a.market), None)
        if gia is not None:
            stato = "a esito IGNOTO" if gia.needs_reconcile else "ancora viva"
            return (f"nuova '{a.role}' mentre '{gia.ref}' e' {stato} "
                    f"(abbinato {gia.matched}/{gia.size})")
    return None


@_controllo("J3", "ogni gamba nasce con un riferimento suo, e nessun riferimento "
                  "si ripete (15/09)",
            quando=lambda ctx, snap, d, p: bool(ctx.legs))
def _j3(ctx, snap, d, params):
    refs = [l.ref for l in ctx.legs]
    if len(refs) != len(set(refs)):
        doppi = sorted({r for r in refs if refs.count(r) > 1})
        return f"riferimenti ripetuti: {doppi}"
    if any(not str(l.ref or "").strip() for l in ctx.legs):
        return "una gamba senza riferimento"
    return None


@_controllo("J4", "una gamba a esito IGNOTO non viene mai data per annullata, ne' "
                  "sostituita da una nuova (§4.11)",
            quando=lambda ctx, snap, d, p: (any(a.kind == 'cancel' for a in d.actions)
                                            or any(l.needs_reconcile for l in ctx.legs)))
def _j4(ctx, snap, d, params):
    """⚠️ 16/09 — il controllo guardava SOLO l'azione `cancel`, e cosi' non
    poteva vedere il difetto 4 del 15/09, che non annullava niente: piazzava una
    gamba NUOVA al posto di quella a esito ignoto (un ordine vivo su Betfair
    dichiarato «mai piazzato», e un secondo green-up con soldi veri). Dare per
    morta una gamba ignota RIFACENDOLA e' la stessa violazione, in un'altra
    forma. E senza questa meta' il controllo non aveva quasi mai un caso."""
    for a in d.actions:
        if a.kind != "cancel":
            continue
        g = next((l for l in ctx.legs if l.ref == getattr(a, "ref", None)), None)
        if g is not None and g.needs_reconcile:
            return f"cancel su '{g.ref}', che e' a esito ignoto"
    for a in _piazzamenti(d):
        g = next((l for l in ctx.legs
                  if l.needs_reconcile and l.role == a.role and l.side == a.side
                  and l.market == a.market and l.selection == a.selection
                  and int(l.cycle_no or 0) == int(ctx.cycle_no or 0)), None)
        if g is not None:
            return (f"nuova '{a.role}' al posto di '{g.ref}', che e' a esito ignoto "
                    f"(potrebbe essere viva su Betfair)")
    return None


@_controllo("J5", "MAI due lay VIVE o IN VOLO sullo stesso mercato/selezione: se si "
                  "abbinano entrambe la posizione si ribalta e resta SCOPERTA "
                  "(ordine dell'utente 16/09 h16:15)",
            quando=lambda ctx, snap, d, p: any(
                l.side == 'lay' and (l.is_live or l.needs_reconcile) for l in ctx.legs))
def _j5(ctx, snap, d, params):
    """⚠️ «Non devono mai esserci 2 lay a mercato, se si abbinano siamo
    scoperti!!!» — parole dell'utente, 16/09 h16:15.

    E' letteralmente vero: la posizione di Mike e' un BACK Under 3.5 e ogni lay
    serve a chiuderlo. Due lay abbinate lo ribaltano in un netto LAY, cioe' una
    posizione allo scoperto che nessuna regola prevede.

    Il controllo e' SEVERO di proposito e guarda due cose:
      1. lo STATO: due lay in volo (vive o a esito ignoto) sulla stessa
         selezione, anche per un solo giro;
      2. la DECISIONE: una lay nuova proposta dove ce n'e' gia' una in volo —
         e vale ANCHE se la stessa decisione la annulla. Un annullamento
         emesso non e' un annullamento confermato: finche' Betfair non ha
         risposto quella lay puo' abbinarsi.
    """
    visti = {}
    for l in ctx.legs:
        if l.side != "lay" or not (l.is_live or l.needs_reconcile):
            continue
        k = (l.market, l.selection)
        if k in visti:
            return (f"due lay in volo su {k[0]}|{k[1]}: '{visti[k]}' e '{l.ref}' "
                    f"(se abbinano entrambe la posizione resta SCOPERTA)")
        visti[k] = l.ref
    for a in _piazzamenti(d):
        if str(a.side) != "lay":
            continue
        k = (a.market, a.selection)
        if k in visti:
            annullata = any(getattr(x, "kind", "") == "cancel"
                            and getattr(x, "ref", None) == visti[k] for x in d.actions)
            come = ("annullata nello STESSO giro: l'annullamento emesso non e' "
                    "un annullamento confermato" if annullata else "ancora in volo")
            return (f"nuova lay '{a.role}' su {k[0]}|{k[1]} mentre '{visti[k]}' e' {come}")
    return None


@_controllo("J5B", "MAI due lay VIVE o IN VOLO sullo stesso MERCATO 4,5, anche su "
                   "selezioni diverse: la banca Under e la banca Over pesano sulla stessa "
                   "posizione (piano Mike M3.4, 29/09)",
            quando=lambda ctx, snap, d, p: any(
                l.side == 'lay' and l.market == E.MARKET_OU45
                and (l.is_live or l.needs_reconcile) for l in ctx.legs))
def _j5b(ctx, snap, d, params):
    """J5 guarda la selezione; sul mercato a due esiti una banca Under 4,5 (la
    copertura nuova) e una banca Over 4,5 (la sua chiusura) sono due lay sulla
    STESSA posizione: se si abbinano entrambe la chiusura e' doppia. Stato e
    decisione, come J5, sul solo mercato 4,5."""
    in_volo = [l for l in ctx.legs if l.side == "lay" and l.market == E.MARKET_OU45
               and (l.is_live or l.needs_reconcile)]
    if len(in_volo) > 1:
        return (f"due lay in volo sul mercato 4,5: {[f'{l.ref}|{l.selection}' for l in in_volo]}")
    if not in_volo:
        return None
    g0 = in_volo[0]
    for a in _piazzamenti(d):
        if str(a.side) == "lay" and a.market == E.MARKET_OU45:
            annullata = any(getattr(x, "kind", "") == "cancel"
                            and getattr(x, "ref", None) == g0.ref for x in d.actions)
            come = ("annullata nello STESSO giro: l'annullamento emesso non e' "
                    "un annullamento confermato" if annullata else "ancora in volo")
            return (f"nuova lay '{a.role}' su OU45|{a.selection} mentre '{g0.ref}' "
                    f"(OU45|{g0.selection}) e' {come}")
    return None


@_controllo("J6", "MAI SOVRACOPERTURA: mai due back di copertura VIVI o IN VOLO "
                  "sull'Over 4.5, e la somma di cio' che e' in volo non supera la "
                  "copertura prevista (ordine dell'utente 16/09 sera)",
            quando=lambda ctx, snap, d, p: (
                any(l.role == 'over_cover' and (l.is_live or l.needs_reconcile) for l in ctx.legs)
                or any(a.role == 'over_cover' for a in _piazzamenti(d))))
def _j6(ctx, snap, d, params):
    """MAI SOVRACOPERTURA - ordine dell'utente, 16/09 sera.

    La copertura e' un BACK sull'Over 4.5: due back abbinati non lasciano una
    posizione scoperta (quello lo fa la doppia lay, J5), ma comprano Over che
    non serve - soldi spesi due volte per proteggere una volta sola. Fino al
    16/09 ``_decide_cover_pending`` riprezzava la copertura con ``cancel`` +
    ``place`` nello STESSO giro, esattamente come facevano le lay prima di J5:
    l'annullamento emesso non e' un annullamento confermato, quindi le due
    tranche potevano stare a mercato insieme.

    Il controllo guarda tre cose:
      1. lo STATO: due ``over_cover`` in volo (vivi o a esito ignoto) insieme;
      2. la DECISIONE: un ``over_cover`` nuovo dove ce n'e' gia' uno in volo,
         ANCHE se lo stesso giro lo annulla;
      3. la QUANTITA': la somma di cio' che e' gia' in volo piu' cio' che si sta
         proponendo non deve superare la copertura ancora PREVISTA (il residuo
         calcolato dalle stesse funzioni del motore sulla copertura gia'
         ABBINATA). Il margine ammesso e' l'arrotondamento legale dichiarato
         (``cover_max_overshoot_pct``) piu' un centesimo.
    """
    in_volo = [l for l in ctx.legs
               if l.role == "over_cover" and (l.is_live or l.needs_reconcile)]
    if len(in_volo) > 1:
        return (f"due coperture in volo insieme: {[l.ref for l in in_volo]} "
                f"(sommate comprano Over gia' comprato)")
    nuove = [a for a in _piazzamenti(d) if a.role == "over_cover"]
    if nuove and in_volo:
        g0 = in_volo[0]
        annullata = any(getattr(x, "kind", "") == "cancel"
                        and getattr(x, "ref", None) == g0.ref for x in d.actions)
        come = ("annullata nello STESSO giro: l'annullamento emesso non e' un "
                "annullamento confermato" if annullata else
                ("a esito ignoto" if g0.needs_reconcile else "ancora viva"))
        return (f"nuova copertura mentre '{g0.ref}' e' {come} "
                f"(abbinato {g0.matched}/{g0.size})")
    if not nuove:
        return None
    if all(str(a.side) == "lay" for a in nuove):
        # 29/09 (P5, M3.1): copertura come BANCA Under 4,5. Il residuo previsto
        # e' ``cover_residual_lay`` (non dipende dalla quota); nessun margine di
        # arrotondamento legale (una banca va al centesimo).
        try:
            c = float(params["commission_pct"]) / 100.0
            liab = E.under_liability(ctx.legs)
            gia = E.cover_matched_value(ctx.legs, c)
            residuo = E.cover_residual_lay(liab, c, float(params["cover_profit_factor"]), gia)
        except Exception:  # noqa: BLE001 - senza numeri non si accusa
            return None
        chiesto = sum(float(a.size or 0.0) for a in nuove) + sum(
            max(0.0, float(l.size or 0.0) - float(l.matched or 0.0)) for l in in_volo)
        if chiesto > residuo + 0.01:
            return (f"sovracopertura: banca {round(chiesto, 2)} in volo+proposta contro un "
                    f"residuo previsto di {round(residuo, 2)} (liability {liab}, gia' "
                    f"coperto {round(gia, 2)})")
        return None
    # 3. la quantita': quanto Over si sta comprando in tutto contro quanto ne
    #    serve ancora. Se manca un prezzo non si giudica (controllo conservativo).
    bk = _book(snap, E.MARKET_OU45, E.SEL_OVER)
    prezzo = getattr(bk, "best_back", None) if bk is not None else None
    if not prezzo or float(prezzo) <= 1.0:
        return None
    try:
        c = float(params["commission_pct"]) / 100.0
        liab = E.under_liability(ctx.legs)
        gia = E.cover_matched_value(ctx.legs, c)
        residuo = E.cover_residual(liab, float(prezzo), c,
                                   float(params["cover_profit_factor"]), gia)
    except Exception:  # noqa: BLE001 - senza numeri non si accusa
        return None
    if residuo <= 0:
        chiesto = round(sum(float(a.size or 0.0) for a in nuove), 2)
        return (f"copertura {chiesto} proposta quando il residuo previsto e' 0 "
                f"(liability {liab}, gia' coperto {round(gia, 2)})")
    in_volo_size = sum(max(0.0, float(l.size or 0.0) - float(l.matched or 0.0))
                       for l in in_volo)
    chiesto = sum(float(a.size or 0.0) for a in nuove) + in_volo_size
    margine = 1.0 + max(0.0, float(params.get("cover_max_overshoot_pct") or 0.0)) / 100.0
    if chiesto > residuo * margine + 0.01:
        return (f"sovracopertura: {round(chiesto, 2)} Over in volo+proposti contro un "
                f"residuo previsto di {round(residuo, 2)} (margine legale "
                f"{params.get('cover_max_overshoot_pct')}%)")
    return None


@_controllo("R3", "se la posizione l'ha chiusa l'UTENTE fuori dall'app, il bot non "
                  "emette PIU' NESSUNA azione su quella partita "
                  "(ordine dell'utente 16/09 sera)",
            quando=lambda ctx, snap, d, p: bool(getattr(ctx, 'chiuso_dall_utente', False)))
def _r3(ctx, snap, d, params):
    """«SE CHIUDO IO, IL BOT DEVE SAPERLO, ANCHE FUORI DALL'APP» - utente, 16/09 sera.

    Diverso da R2 (cash-out dalla UI, dove le CHIUSURE restano permesse perche'
    un residuo puo' ancora abbinarsi): qui la posizione non esiste piu' sul
    conto, quindi non c'e' niente da coprire, da chiudere o in cui rientrare.
    Nessuna azione, di nessun tipo. Il regolamento non passa da ``decide``
    finche' il mercato non chiude, quindi il P&L vero resta contabilizzato.
    """
    if d.actions:
        ruoli = ", ".join(sorted({f"{a.kind}:{a.role}" for a in d.actions}))
        return (f"la posizione l'ha chiusa l'utente fuori dall'app e il bot agisce "
                f"ancora: {ruoli} (stato {ctx.state})")
    return None


@_controllo("R2", "dopo un cash-out globale dell'utente il bot NON apre piu' niente su "
                  "quella partita: la gestisce l'utente (ordine 16/09 h18:20)",
            quando=lambda ctx, snap, d, p: bool(ctx.no_reentry
                                                and str(ctx.close_reason or "") == "manual"
                                                and not ctx.flatten_pending))
def _r2(ctx, snap, d, params):
    """⚠️ «Il bot gestisce le sue operazioni; UNICO CASO e' quando io chiudo
    manualmente TUTTE le operazioni (cash-out globale della partita): al
    successivo controllo lo capisce e NON FA ALTRO» — utente, 16/09 h18:20.

    ``quando`` prende i giri SUCCESSIVI alla chiusura manuale: ``no_reentry``
    acceso, ``close_reason='manual'``, chiusura non piu' in corso.
    Si vietano le APERTURE, non le chiusure: se un residuo si abbina il bot deve
    poterlo gestire (niente che protegge puo' impedire di chiudere).
    """
    aperture = _aperture(d)
    if aperture:
        ruoli = ", ".join(sorted({str(a.role) for a in aperture}))
        return (f"l'utente ha chiuso tutto a mano e il bot riapre: {ruoli} "
                f"(stato {ctx.state})")
    return None


# ===========================================================================
# R. LA SOSPENSIONE (ordine dell'utente, 16/09 — Costituzione §15.6)
# ===========================================================================
@_controllo("R1", "dopo una sospensione con la lay appoggiata VIVA, alla riapertura "
                  "l'ordine si RILEGGE da Betfair prima di decidere (§15.6)",
            quando=lambda ctx, snap, d, p: bool((ctx.riapertura or {}).get("refs")))
def _r1(ctx, snap, d, params):
    """⚠️ La lay di uscita al fischio e' appoggiata: Betfair la fa SCADERE
    (LAPSE) a ogni sospensione del mercato, e un gol al 2' basta. Se il bot
    ricomincia a decidere a mercato riaperto senza aver riletto quell'ordine,
    sta dando per vivo qualcosa che potrebbe non esistere piu': non ha ne'
    l'uscita ne' la copertura, ed e' il punto peggiore in cui stare.
    Il servizio annota la sospensione in ``ctx.riapertura`` e mette
    ``letto=True`` solo quando Betfair ha risposto davvero (anche «non lo so»:
    li' la gamba va in riconciliazione). Finche' e' False, e il mercato e' di
    nuovo operabile, questo controllo e' rosso.
    """
    r = ctx.riapertura or {}
    if r.get("letto"):
        return None
    # M6.3 (29/09): il mercato e' quello DOVE STANNO le gambe annotate (la banca
    # del rientro vive sull'Under 4.5), come nel servizio.
    annotate = [(l.market, l.selection) for l in ctx.legs if l.ref in set(r.get("refs") or [])]
    if not all(E.operabile(_book(snap, m, s))
               for (m, s) in (annotate or [(E.MARKET_OU35, E.SEL_UNDER)])):
        return None                    # ancora sospeso: non c'e' niente da rileggere
    return (f"mercato riaperto e le gambe {r.get('refs')} non sono state rilette da "
            f"Betfair (sospeso a {r.get('ts')}): il bot le sta dando per vive")


# ===========================================================================
# KG. LA BANCA AL FISCHIO ABBINATA IN PARTE (ordine dell'utente, 30/09 15:40)
#
# Fatto: live, partita 36130526, banca al fischio 5,10 @ 2,08 abbinata 1,00 a
# 29 s dal fischio e ANNULLATA nello stesso secondo, copertura a 37 s. L'utente:
# "quell'ordine deve restare a mercato per 3 minuti come da progettazione, SOLO
# DOPO I 3 minuti [...] RITIRA IL RESTO, e si copre [...] PER L'IMPORTO
# RIMANENTE". Il controllo e' scritto con conti suoi (non con le funzioni del
# motore che giudica): netto da chiudere e rischio residuo dalle sole gambe.
# ===========================================================================
def _banca_fischio_parziale(ctx: E.MatchCtx) -> Optional[E.Leg]:
    """L'ultima uscita al fischio, se abbinata IN PARTE (viva o no)."""
    ko = [l for l in ctx.legs if l.role == "ko_green"]
    if not ko:
        return None
    u = ko[-1]
    if float(u.matched) <= 0.005 or float(u.matched) >= float(u.size) - 0.005:
        return None
    return u


def _qualche_banca_fischio_abbinata(ctx: E.MatchCtx) -> bool:
    return any(l.role == "ko_green" and float(l.matched) > 0.005 for l in ctx.legs)


def _netto_da_chiudere_senza(ctx: E.MatchCtx, esclusa: E.Leg) -> float:
    """Netto (W - L) dell'Under 3,5 dalle gambe abbinate, SENZA ``esclusa``: la
    banca giusta a prezzo p ha size netto / p (formula del green-up)."""
    netto = 0.0
    for l in ctx.legs:
        if l is esclusa or l.market != E.MARKET_OU35 or l.archived or float(l.matched) <= 0:
            continue
        s, p = float(l.matched), float(l.avg_price or l.price)
        pro_under = (l.selection == E.SEL_UNDER) == (l.side == "back")
        netto += s * p if pro_under else -s * p
    return netto


def _rischio_under_residuo(ctx: E.MatchCtx) -> float:
    """Euro persi sull'Under 3,5 se l'Under PERDE, dalle sole gambe abbinate."""
    perdita = 0.0
    for l in ctx.legs:
        if l.market != E.MARKET_OU35 or l.archived or float(l.matched) <= 0:
            continue
        s, p = float(l.matched), float(l.avg_price or l.price)
        if l.selection == E.SEL_UNDER:
            perdita += s if l.side == "back" else -s
        else:
            perdita += -s * (p - 1.0) if l.side == "back" else s * (p - 1.0)
    return max(0.0, perdita)


def _eccezione_del_fischio(ctx: E.MatchCtx, snap: E.Snapshot) -> bool:
    """Le strade che ritirano l'uscita prima dello scadere: gol dopo il fischio
    (strada C) o mercato chiuso."""
    gol = (snap.goals is not None and ctx.ko_goals is not None
           and int(snap.goals) > int(ctx.ko_goals))
    bk = _book(snap, E.MARKET_OU35, E.SEL_UNDER)
    chiuso = bk is not None and str(bk.status or "").upper() == "CLOSED"
    return gol or chiuso


def _kg1_caso(ctx, snap, d, p) -> bool:
    if ctx.state == "LIVE_KO_GREEN":
        return _banca_fischio_parziale(ctx) is not None
    return (ctx.state in ("LIVE_UNCOVERED", "LIVE_COVER_PENDING")
            and _qualche_banca_fischio_abbinata(ctx)
            and any(a.role == "over_cover" for a in _piazzamenti(d)))


@_controllo("KG1", "la banca al fischio abbinata in parte resta a mercato fino allo "
                   "scadere della finestra; il residuo si annulla solo dopo, e la "
                   "copertura vale il rischio residuo (ordine dell'utente 30/09)",
            quando=_kg1_caso)
def _kg1(ctx, snap, d, params):
    if ctx.state == "LIVE_KO_GREEN":
        u = _banca_fischio_parziale(ctx)
        if u is None or ctx.live_since is None:
            return None
        trascorsi = float(snap.now) - float(ctx.live_since)
        if trascorsi >= float(params["ko_green_window_s"]) or _eccezione_del_fischio(ctx, snap):
            return None
        if d.state == "LIVE_UNCOVERED":
            return (f"copertura a {trascorsi:.0f} s dal fischio con la banca '{u.ref}' "
                    f"abbinata in parte ({float(u.matched):.2f} su {float(u.size):.2f}): "
                    f"la finestra e' di {int(params['ko_green_window_s'])} s")
        annullata = any(a.kind == "cancel" and a.ref == u.ref for a in d.actions)
        if not annullata or not u.is_live:
            return None
        # riallineo legittimo: la posizione d'ingresso e' cambiata (un'altra
        # gamba abbinata), e la banca viva non e' piu' quella giusta
        giusta = _netto_da_chiudere_senza(ctx, u) / float(u.price)
        if abs(giusta - float(u.size)) > 0.011 + 0.01 * float(u.size):
            return None
        return (f"residuo della banca '{u.ref}' ({float(u.matched):.2f} su "
                f"{float(u.size):.2f}) annullato a {trascorsi:.0f} s dal fischio, "
                f"prima dello scadere dei {int(params['ko_green_window_s'])} s")
    # la copertura dopo una banca al fischio abbinata (in parte): vale il rischio
    # RESIDUO dell'Under 3,5, mai lo stake lordo (forma di serie: banca Under 4,5)
    if E.cover_form(params) != E.COVER_LAY_U45:
        return None
    c = float(params.get("commission_pct", 5.0)) / 100.0
    fattore = float(params["cover_profit_factor"])
    gia = E.cover_matched_value(ctx.legs, c)
    massimo = max(0.0, (fattore * _rischio_under_residuo(ctx) - gia) / (1.0 - c))
    for a in _piazzamenti(d):
        if a.role == "over_cover" and a.side == "lay" and float(a.size) > massimo + 0.02:
            return (f"copertura banca Under 4,5 da {float(a.size):.2f} quando il rischio "
                    f"residuo dell'Under 3,5 ({_rischio_under_residuo(ctx):.2f}) ne "
                    f"chiede al piu' {massimo:.2f}")
    return None


# ===========================================================================
# S. IL FRENO DELLA COPERTURA E LO STATO DEL MERCATO (17/09, reperto 25)
#
# Fatto: evento 36077571, la copertura Over 4.5 sotto minimo rifiutata 171
# volte di fila con lo stesso codice ``CANCELLED_NOT_PLACED``, una ogni ~5 s
# per un'ora, senza nessun freno. Questi due controlli lo rendono ROSSO nel
# banco invece che scoprirlo con i soldi veri.
# ===========================================================================
@_controllo("S1", "a freno scattato (cover_rifiuti_max rifiuti con lo stesso codice) "
                  "il bot NON ripropone la copertura (17/09, reperto 25)",
            quando=lambda ctx, snap, d, p: bool(E.copertura_bloccata(ctx)))
def _s1(ctx, snap, d, params):
    """Il freno e' fail-closed: da bloccata, la copertura si riapre solo con
    l'utente («Riprendi») o con un codice d'errore DIVERSO. Se il motore la
    ripropone lo stesso, siamo di nuovo al 17/09."""
    fermo = E.copertura_bloccata(ctx)
    if not fermo:
        return None
    ancora = [a for a in d.actions if a.kind == "place" and a.role == "over_cover"]
    if ancora:
        return (f"copertura FERMATA dal freno ({fermo.get('conteggio')} rifiuti "
                f"'{fermo.get('error_code')}') e il bot la ripropone lo stesso")
    return None


def _sel_copertura(ctx, d, params) -> str:
    """29/09 (P5): la selezione del libro della copertura: quella dell'ordine di
    copertura proposto, o di quello sul book, altrimenti la forma scelta."""
    for a in _piazzamenti(d):
        if a.role == "over_cover" and a.selection:
            return str(a.selection)
    for l in reversed(ctx.legs):
        if l.role == "over_cover" and (l.is_live or l.needs_reconcile):
            return str(l.selection)
    return E.SEL_UNDER if E.cover_form(params or {}) == E.COVER_LAY_U45 else E.SEL_OVER


@_controllo("S2", "nessun piazzamento di copertura mentre il mercato della copertura "
                  "(Over 4.5, o Under 4.5 per la banca) non e' OPEN: si aspetta la "
                  "riapertura (ordine dell'utente 17/09, n.5)",
            quando=lambda ctx, snap, d, p: not E.operabile(
                _book(snap, E.MARKET_OU45, _sel_copertura(ctx, d, p))))
def _s2(ctx, snap, d, params):
    """Sospeso, chiuso, non attivo e IGNOTO valgono tutti «non adesso»: un place
    su mercato sospeso non nasce, e il cancel che lo accompagna lascerebbe la
    posizione ancora piu' scoperta."""
    sel = _sel_copertura(ctx, d, params)
    bk = _book(snap, E.MARKET_OU45, sel)
    if E.operabile(bk):
        return None
    tocca = [a for a in d.actions
             if a.role == "over_cover" and a.kind in ("place", "cancel")]
    if tocca:
        ruoli = ", ".join(sorted({str(a.kind) for a in tocca}))
        nome = "Under 4.5" if sel == E.SEL_UNDER else "Over 4.5"
        return (f"mercato {nome} {E.stato_mercato(bk)} e il bot emette lo stesso "
                f"{ruoli} sulla copertura")
    return None


def _cover_rifiutate(ctx) -> List[Any]:
    """Le gambe di copertura che il MERCATO ha rifiutato (mai abbinate, morte).

    ⚠️ Si guardano le GAMBE, non ``ctx.cover_rifiuti``. E' il punto: se il
    contatore del freno smettesse di contare, S1 (che guarda il freno) non
    avrebbe piu' un caso e il referto direbbe «non lo so» invece di rosso — il
    bot tornerebbe a ritentare all'infinito e il banco lo dichiarerebbe sano.
    Lo stato della gamba viene dall'ESITO del piazzamento, non dal freno.
    """
    return [l for l in ctx.legs
            if l.role == "over_cover" and str(l.status) in ("cancelled", "error")
            and float(l.matched or 0.0) <= 0.005]


def _ultima_cover_tentata(ctx) -> Optional[float]:
    """L'istante dell'ultimo tentativo di copertura, letto dalle GAMBE."""
    ts = [float(l.placed_at or 0.0) for l in ctx.legs
          if l.role == "over_cover" and float(l.placed_at or 0.0) > 0.0]
    return max(ts) if ts else None


@_controllo("S3", "dopo `cover_rifiuti_max` coperture RIFIUTATE dal mercato il bot non "
                  "ne piazza altre: il freno deve SCATTARE (17/09, reperto 25)",
            quando=lambda ctx, snap, d, p: (
                len(_cover_rifiutate(ctx)) >= max(1, int(p.get("cover_rifiuti_max") or 1))))
def _s3(ctx, snap, d, params):
    """⚠️ IL FRATELLO NECESSARIO DI S1. S1 verifica che, A FRENO SCATTATO, il bot
    non riproponga la copertura; questo verifica che il freno SCATTI. Senza,
    neutralizzare il conteggio dei rifiuti dava «0 violazioni e S1 a zero»:
    esattamente i 171 tentativi del 17/09, dichiarati sani.

    Contato dai RIFIUTI osservati sulle gambe, non dal contatore del freno.
    """
    massimo = max(1, int(params.get("cover_rifiuti_max") or 1))
    rifiutate = _cover_rifiutate(ctx)
    if len(rifiutate) < massimo:
        return None
    ancora = [a for a in d.actions if a.kind == "place" and a.role == "over_cover"]
    if ancora:
        return (f"{len(rifiutate)} coperture gia' RIFIUTATE dal mercato (soglia "
                f"{massimo}) e il bot ne piazza un'altra: il freno non e' scattato")
    return None


@_controllo("S4", "fra due tentativi di copertura passa almeno `cover_retry_min_s` "
                  "(bet delay + margine, 17/09)",
            quando=lambda ctx, snap, d, p: any(
                a.kind == "place" and a.role == "over_cover" for a in d.actions))
def _s4(ctx, snap, d, params):
    """Il 17/09 si ritentava ogni ~5 s, cioe' prima ancora di sapere com'era
    andata la volta prima (il bet delay in gioco e' 5 s). Il tempo e' quello del
    MERCATO (``snap.now``) e l'istante precedente viene dalle GAMBE."""
    minimo = float(params.get("cover_retry_min_s") or 0.0)
    if minimo <= 0.0:
        return None
    if not any(a.kind == "place" and a.role == "over_cover" for a in d.actions):
        return None
    ultimo = _ultima_cover_tentata(ctx)
    if ultimo is None:
        return None
    passati = float(snap.now) - ultimo
    if 0.0 <= passati < minimo:
        return (f"nuovo tentativo di copertura dopo {passati:.1f} s dal precedente, "
                f"meno del ritmo minimo {minimo:.0f} s")
    return None


# ===========================================================================
# K. LA CONSAPEVOLEZZA DELL'ORDINE, CONTRO IL MERCATO (16/09 sera)
#
# ⚠️ PERCHE' QUESTA FAMIGLIA ESISTE. Il 16/09 sera la falsificazione
# indipendente dei cinque difetti del 15/09 ha dato un risultato che va scritto
# a chiare lettere: REINTRODOTTI UNO A UNO SUL CODICE DI OGGI, IL REPLAY SU
# 35760084 (base, taker, esiti-ignoti) NON DIVENTAVA ROSSO — il referto era
# perfino IDENTICO cifra per cifra. I controlli A-J guardano la DECISIONE del
# motore (ctx, snap, azioni): i cinque difetti non stanno li', stanno nel
# rapporto fra cio' che il bot CREDE delle sue gambe e cio' che il MERCATO dice
# dei suoi ordini. Nessun controllo guardava quel rapporto.
#
# Questi controlli lo guardano. Non ricevono `Decision`: ricevono le GAMBE, gli
# ORDINI VERI del banco (chiave = il `customer_ref` che il bot ha CHIESTO al
# piazzamento, valore = la riga normalizzata come la produce `omega_market`) e
# i ref che il mercato ha RIFIUTATO. Vivono nello stesso registro e nella
# stessa copertura degli altri: un controllo che non si conta non esiste.
# ===========================================================================
_REGISTRO_BANCO: List[Tuple[str, str]] = []
_FUNZIONI_BANCO: Dict[str, Callable] = {}


def _controllo_banco(codice: str, regola: str):
    def _reg(fn):
        _REGISTRO_BANCO.append((codice, regola))
        _FUNZIONI_BANCO[codice] = fn
        return fn
    return _reg


def _refs_possibili(leg: E.Leg, righe: Optional[List[Dict[str, Any]]] = None) -> set:
    """Le grafie con cui QUESTA gamba puo' essere stata piazzata.

    Sono due, entrambe vere: il ref della gamba (``under_green-0-2``) e
    ``mike-t<id>`` dalla riga di ``mike_trades``. Cercarne una sola e' il
    difetto 4 del 15/09 — e il 16/09 sera ha fatto mancare un caso a K2.
    """
    refs = {str(leg.ref)}
    for r in righe or []:
        if str((r.get("meta") or {}).get("leg_ref") or r.get("signal_key") or "") == str(leg.ref):
            refs.add(f"mike-t{r.get('id')}")
    return refs


def _ordine_di_gamba(ordini: Dict[str, Any], leg: E.Leg,
                     righe: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """L'ordine del banco che appartiene a questa gamba, cercato come lo
    cercherebbe Betfair: per il ref che il bot ha CHIESTO al piazzamento.

    Le grafie possibili sono due, entrambe vere: il ref della gamba
    (``under_green-0-2``, usato dalle uscite) e ``mike-t<id>`` (usato dalle
    aperture). Qui si prendono tutte e due — cercarne una sola e' il difetto 4
    del 15/09.
    """
    o = ordini.get(str(leg.ref))
    if o is not None:
        return o
    for r in righe or []:
        if str((r.get("meta") or {}).get("leg_ref") or r.get("signal_key") or "") == str(leg.ref):
            o = ordini.get(f"mike-t{r.get('id')}")
            if o is not None:
                return o
    return None


@_controllo_banco("K1", "cio' che il bot CREDE di una gamba coincide con cio' che il "
                        "MERCATO dice del suo ordine (abbinato e prezzo medio)")
def _k1(ctx, ordini, rifiutati, righe):
    for leg in ctx.legs:
        if leg.needs_reconcile:
            continue                       # esito ignoto: il dubbio e' dichiarato
        o = _ordine_di_gamba(ordini, leg, righe)
        if o is None:
            continue
        if str(o.get("status") or "") == "EXECUTABLE":
            continue                       # ancora vivo: il bot legge alla SUA cadenza
        abbinato = float(o.get("size_matched") or 0.0)
        if abs(float(leg.matched or 0.0) - abbinato) > 0.011:
            return (f"'{leg.ref}': il bot crede {leg.matched} abbinato, il mercato dice "
                    f"{round(abbinato, 2)} (ordine {o.get('status')})")
        if abbinato > 0.009:
            medio = o.get("avg_price_matched") or o.get("average_price_matched")
            if medio and abs(float(leg.avg_price or 0.0) - float(medio)) > 0.011:
                return (f"'{leg.ref}': prezzo medio {leg.avg_price} contro "
                        f"{medio} dichiarato dal mercato (e' il difetto 3 del 15/09: "
                        f"`avg_price` al posto di `avg_price_matched`)")
    return None


@_controllo_banco("K2", "una gamba il cui ordine Betfair ha RIFIUTATO non resta mai viva "
                        "(difetto 2 del 15/09: `res.ok` mai letto)")
def _k2(ctx, ordini, rifiutati, righe):
    if not rifiutati:
        return None
    for leg in ctx.legs:
        if not (leg.is_live or leg.needs_reconcile):
            continue
        if not (_refs_possibili(leg, righe) & rifiutati):
            continue
        if _ordine_di_gamba(ordini, leg, righe) is None:
            stato = "a esito ignoto" if leg.needs_reconcile else "viva"
            return (f"'{leg.ref}': Betfair ha RIFIUTATO l'ordine e nessun ordine esiste a "
                    f"mercato, ma la gamba e' ancora {stato}")
    return None


@_controllo_banco("K3", "il riferimento con cui il bot ha piazzato si RILEGGE con la "
                        "stessa grafia (difetto 1 del 15/09: `customerOrderRef` vs "
                        "`customer_order_ref`)")
def _k3(ctx, ordini, rifiutati, righe):
    from . import service as S

    for ref, o in (ordini or {}).items():
        letto = S.campo_ordine(o, "customer_order_ref")
        if letto is None:
            return (f"l'ordine '{ref}' esiste a mercato ma il suo riferimento non si "
                    f"rilegge: `campo_ordine(..., 'customer_order_ref')` torna None "
                    f"(chiavi presenti: {sorted(o)[:6]})")
        if str(letto) != str(ref):
            return f"l'ordine '{ref}' si rilegge col riferimento '{letto}'"
    return None


@_controllo_banco("K4", "ogni gamba di CHIUSURA dichiara la riga di apertura che chiude "
                        "(difetto 5 del 15/09: `closes_trade_id` non passato)")
def _k4(ctx, ordini, rifiutati, righe):
    for r in righe or []:
        if str(r.get("role") or "") not in E.CLOSING_ROLES:
            continue
        if str(r.get("role")) == "manual_close":
            continue                       # la chiusura manuale non chiude UNA riga
        meta = r.get("meta") or {}
        if r.get("closes_trade_id") is None and meta.get("closes_trade_id_pending") is None \
                and meta.get("closes_ref") is None:
            return (f"riga #{r.get('id')} '{r.get('role')}' e' una chiusura e non dice "
                    f"quale apertura chiude")
    return None


def verifica_consapevolezza(ctx: E.MatchCtx, ordini: Dict[str, Any],
                            rifiutati: Optional[set] = None,
                            righe: Optional[List[Dict[str, Any]]] = None,
                            sollecitati: Optional[Dict[str, int]] = None) -> List[Violazione]:
    """I controlli K su UN giro: si confronta la memoria del bot col mercato.

    Il chiamante e' il replay (`Betfair/mike/tools/replay_registrazioni.py`),
    subito DOPO il giro del servizio: li' ci sono sia le gambe sia gli ordini
    veri di flumine. `ordini` e' {ref chiesto: riga normalizzata}.
    """
    out: List[Violazione] = []
    if not ctx.legs and not ordini:
        return out
    rif = set(rifiutati or ())
    for codice, regola in _REGISTRO_BANCO:
        if sollecitati is not None:
            sollecitati[codice] = sollecitati.get(codice, 0) + 1
        try:
            det = _FUNZIONI_BANCO[codice](ctx, ordini or {}, rif, righe or [])
        except Exception as ex:  # noqa: BLE001
            out.append(Violazione(f"{codice}-ERRORE", regola,
                                  f"il controllo e' esploso: {type(ex).__name__}: {ex}",
                                  ctx.state))
            continue
        if det:
            out.append(Violazione(codice, regola, det, ctx.state))
    return out


# ===========================================================================
# M. IL MERCATO DECISO DAL PUNTEGGIO (30/09, ordine dell'utente)
#
# Il 29/09 (indagine su 35760084, 4-0) il banco dava 0 violazioni con un
# difetto money-critical presente: dopo il quarto gol Betfair sospende e CHIUDE
# l'Over/Under 3,5 (deciso), lo scanner lo mette fra i mercati fermi e Mike
# dichiarava fermo il flusso di TUTTA la partita, rifiutando con
# ``no_fill feed_stantio`` anche la chiusura dell'Over 4,5, che aveva prezzi
# vivi. Nessun controllo guardava la RIGA dello scanner: i controlli A-J
# vedono la decisione, i K le gambe contro gli ordini.
#
# M1 guarda la riga dopo ogni giro. Il caso lo decide la RIGA, non Mike: gol
# dal punteggio, linee decise per regola (gol > linea), flusso della linea
# ancora in gioco letto dal modulo condiviso (``stream.flusso_prezzi``).
# Riga invecchiata dallo scenario (feed stantio vero) = nessun caso.
# ===========================================================================
_REGISTRO_RIGA: List[Tuple[str, str]] = [
    ("M1", "con una linea DECISA dal punteggio e l'altra VIVA la partita non e' col "
           "flusso fermo, e nessun ordine sulla linea viva e' rifiutato per "
           "`feed_stantio` (30/09, ordine dell'utente)"),
]


def _linee_della_riga(payload: Dict[str, Any]) -> List[Tuple[float, str, str]]:
    """(linea, market_id, stato) delle linee di Mike (3,5 e 4,5) nella riga."""
    out = []
    for blk in payload.get("ou") or []:
        if not isinstance(blk, dict) or not blk.get("market_id"):
            continue
        try:
            linea = float(blk.get("line"))
        except (TypeError, ValueError):
            continue
        if linea in (3.5, 4.5):
            out.append((linea, str(blk["market_id"]), str(blk.get("status") or "").upper()))
    return out


def caso_mercato_deciso(payload: Optional[Dict[str, Any]],
                        stato_scanner: Optional[Dict[str, Any]] = None) -> List[str]:
    """I market_id delle linee ANCORA IN GIOCO e VIVE quando almeno una linea
    di Mike e' gia' decisa dal punteggio; vuoto = nessun caso per M1."""
    from Betfair.stream import flusso_prezzi as FP

    if not isinstance(payload, dict) or not payload.get("inplay"):
        return []
    try:
        gol = int(payload.get("score_home")) + int(payload.get("score_away"))
    except (TypeError, ValueError):
        return []
    linee = _linee_della_riga(payload)
    decise = [mid for linea, mid, _st in linee if gol > linea]
    # una linea in gioco CHIUSA da Betfair: la partita e' finita davvero
    in_gioco = [mid for linea, mid, st in linee if gol < linea and st != "CLOSED"]
    if not decise or not in_gioco:
        return []
    if FP.blocco_riga(payload) is None or not FP.valuta_stato(stato_scanner).vivo:
        return []
    if not FP.valuta_riga(payload, in_gioco).vivo:
        return []           # la linea in gioco e' ferma davvero: blocca, giustamente
    return in_gioco


def verifica_mercato_deciso(payload: Optional[Dict[str, Any]], flusso_vivo_per_il_bot: bool,
                            rifiuti_feed_stantio: List[str],
                            stato_scanner: Optional[Dict[str, Any]] = None,
                            riga_invecchiata: bool = False,
                            sollecitati: Optional[Dict[str, int]] = None,
                            stato: str = "",
                            in_regolamento: bool = False) -> List[Violazione]:
    """M1 su UN giro. ``flusso_vivo_per_il_bot``: l'esito del flusso secondo il
    feed di Mike (``feed.flusso_esito``); ``rifiuti_feed_stantio``: i market_id
    degli ordini rifiutati in questo giro con ``no_fill feed_stantio``;
    ``in_regolamento``: il servizio ha preso la strada del regolamento della
    partita (``settle_first_ts`` nel contesto) -- con una linea viva e' il ramo
    di produzione del difetto (3,5 CHIUSO letto come partita finita)."""
    if riga_invecchiata:
        return []
    vive = caso_mercato_deciso(payload, stato_scanner)
    if not vive:
        return []
    codice, regola = _REGISTRO_RIGA[0]
    if sollecitati is not None:
        sollecitati[codice] = sollecitati.get(codice, 0) + 1
    p = payload or {}
    gol = int(p.get("score_home")) + int(p.get("score_away"))   # letti in caso_mercato_deciso
    minuto = p.get("minute") if isinstance(p.get("minute"), int) else None
    out: List[Violazione] = []
    if not flusso_vivo_per_il_bot:
        out.append(Violazione(codice, regola,
                              f"linea viva {vive} ma il bot dichiara fermo il flusso della "
                              f"partita (linea decisa scambiata per flusso fermo)",
                              stato, minuto, gol))
    rifiutati = sorted({m for m in rifiuti_feed_stantio if m in vive})
    if rifiutati:
        out.append(Violazione(codice, regola,
                              f"ordini sulla linea viva {rifiutati} rifiutati per feed_stantio "
                              f"x{len(rifiuti_feed_stantio)}", stato, minuto, gol))
    if in_regolamento:
        out.append(Violazione(codice, regola,
                              f"linea viva {vive} ma il servizio e' in regolamento della partita "
                              f"(linea decisa/chiusa letta come partita finita)",
                              stato, minuto, gol))
    return out


# ===========================================================================
# G4 e RG1: LA FIRMA ESEGUITA E IL REGOLAMENTO (30/09, ondata 2 del banco)
#
# Non guardano UNA decisione: G4 segue una firma dell'utente fino al mercato
# (come UF1/UF2 di ``Betfair/stream/backtest/uscite_manuali.py``), RG1 confronta
# alla fine della partita il regolamento che Mike scrive con quello del banco.
# Li chiama il replay; stanno nell'elenco dei controlli per la copertura.
# ===========================================================================
_REGISTRO_REPLAY: List[Tuple[str, str]] = [
    ("G4", "dopo una firma VALIDA dell'utente gli ordini di chiusura arrivano al "
           "mercato entro FIRMA_ESEGUITA_ENTRO_S secondi di mercato (il 29/09 la "
           "firma passava e la chiusura moriva in `no_fill feed_stantio`)"),
    ("RG1", "al regolamento il P&L della partita e l'esito di OGNI riga di "
            "mike_trades (won/lost/void, lordo) coincidono con quelli del banco "
            "(flumine sui runner WINNER/LOSER della registrazione)"),
]
#: secondi di MERCATO entro cui una firma eseguita deve portare un ordine al
#: mercato: giro successivo (<= 2 s) + bet delay (5 s) + un'eventuale attesa
#: della riapertura dopo un gol (Betfair sospende ~40-60 s)
FIRMA_ESEGUITA_ENTRO_S = 90.0


class SorveglianzaFirme:
    """G4: ogni firma dell'utente, dal clic al mercato.

    ``firma`` = il replay ha visto nascere una firma (``ctx.uscita_approvata``
    nuova); ``esecuzione`` = il cancello del motore ha fatto passare una
    chiusura con una firma valida (la decisione porta ordini di uscita);
    ``ordine`` = un ordine NUOVO del bot e' arrivato al mercato (letto dal
    banco, non dalle righe del bot). ``giro`` giudica: una firma consumata
    senza nessun ordine al mercato entro ``FIRMA_ESEGUITA_ENTRO_S``, o una
    firma rimasta viva e mai eseguita oltre quel tempo, e' una violazione. Una
    proposta decaduta (la strategia non vuole piu' uscire: la firma cade con
    lei) non lo e', e si conta a parte."""

    def __init__(self, entro_s: float = FIRMA_ESEGUITA_ENTRO_S) -> None:
        self.entro_s = float(entro_s)
        self._aperte: List[Dict[str, Any]] = []
        self._ordini: List[float] = []
        self.firme = 0
        self.eseguite = 0
        self.decadute = 0
        self.violate = 0

    def firma(self, chiave: str, at: float) -> None:
        self.firme += 1
        self._aperte.append({"chiave": str(chiave), "at": float(at), "eseguita_at": None})

    def esecuzione(self, now: float) -> None:
        for f in self._aperte:
            if f["eseguita_at"] is None and float(now) >= f["at"]:
                f["eseguita_at"] = float(now)

    def ordine(self, now: float, market_id: str = "", side: str = "") -> None:
        self._ordini.append(float(now))

    def giro(self, now: float, *, proposta_viva: bool, firma_viva: bool,
             sollecitati: Optional[Dict[str, int]] = None) -> List["Violazione"]:
        codice, regola = _REGISTRO_REPLAY[0]
        out: List[Violazione] = []
        resta: List[Dict[str, Any]] = []
        for f in self._aperte:
            if sollecitati is not None:
                sollecitati[codice] = sollecitati.get(codice, 0) + 1
            dal = f["eseguita_at"] if f["eseguita_at"] is not None else f["at"]
            if any(t >= f["at"] for t in self._ordini):
                self.eseguite += 1
                continue
            if f["eseguita_at"] is None and not firma_viva and not proposta_viva:
                self.decadute += 1           # la strategia non esce piu': legittimo
                continue
            if float(now) - dal > self.entro_s:
                self.violate += 1
                come = ("consumata dal cancello ma nessun ordine al mercato"
                        if f["eseguita_at"] is not None else "mai eseguita")
                out.append(Violazione(codice, regola,
                                      f"firma {f['chiave']} delle {f['at']:.0f}: {come} "
                                      f"dopo {float(now) - dal:.0f} s di mercato"))
                continue
            resta.append(f)
        self._aperte = resta
        return out


def confronta_regolamento(stato: str, settled_pnl: Optional[float],
                          righe: List[Dict[str, Any]], esiti: Dict[str, Dict[str, Any]],
                          pnl_banco: Optional[float],
                          sollecitati: Optional[Dict[str, int]] = None,
                          tolleranza: float = 0.005) -> List["Violazione"]:
    """RG1 a fine partita. ``esiti`` = {bet_id: {"esito", "lordo"}} dagli ORDINI
    del banco (flumine: ``runner_status`` dopo la chiusura del mercato e
    ``simulated.profit`` lordo); ``pnl_banco`` = il netto del banco secondo la
    regola di Betfair (``MercatoFlumine.pnl_betfair``: scommessa al centesimo,
    commissione del mercato al centesimo). 30/09: il confronto e' AL CENTESIMO
    (``tolleranza`` 0,005 = solo il rumore dei float fra due cifre a due
    decimali; prima 0,02 nascondeva lo scarto 3,30 contro 3,28). Nessun caso se
    la partita non e' SETTLED."""
    if str(stato) != "SETTLED":
        return []
    codice, regola = _REGISTRO_REPLAY[1]
    if sollecitati is not None:
        sollecitati[codice] = sollecitati.get(codice, 0) + 1
    out: List[Violazione] = []
    if settled_pnl is None or pnl_banco is None \
            or abs(float(settled_pnl) - float(pnl_banco)) > tolleranza:
        out.append(Violazione(codice, regola, f"P&L della partita: Mike {settled_pnl} contro "
                                              f"{pnl_banco} del banco", "SETTLED"))
    for r in righe or []:
        bet = str(r.get("bet_id") or "")
        stato_r = str(r.get("status") or "")
        e = esiti.get(bet) if bet else None
        if e is None:
            if stato_r not in ("won", "lost", "void", "error"):
                out.append(Violazione(codice, regola, f"riga #{r.get('id')} ancora "
                                                      f"'{stato_r}' a partita regolata",
                                      "SETTLED"))
            continue
        # una riga 'error' (ordine rifiutato/mai abbinato: ``_settle_trades`` non
        # la tocca) vale un 'void' del banco se non porta P&L
        if stato_r == "error" and e.get("esito") == "void" \
                and abs(float(r.get("pnl") or 0.0)) <= tolleranza:
            continue
        if stato_r != str(e.get("esito")):
            out.append(Violazione(codice, regola,
                                  f"riga #{r.get('id')} (bet {bet}) '{stato_r}' contro "
                                  f"'{e.get('esito')}' del banco", "SETTLED"))
            continue
        lordo = (r.get("meta") or {}).get("pnl_gross")
        if lordo is None:
            lordo = r.get("pnl") if stato_r == "void" else None
        if lordo is not None and abs(float(lordo) - float(e.get("lordo") or 0.0)) > tolleranza:
            out.append(Violazione(codice, regola,
                                  f"riga #{r.get('id')} (bet {bet}) lordo {lordo} contro "
                                  f"{e.get('lordo')} del banco", "SETTLED"))
    return out


def elenco_stati() -> Tuple[str, ...]:
    """Gli stati della macchina (PROCESSO_STANDARD_BOT par. 6.3): i mai visti
    si elencano per nome nel referto."""
    return tuple(E.STATES)


def stati_mai_visti(visti: List[str]) -> List[str]:
    v = set(visti or [])
    return [s for s in elenco_stati() if s not in v]


# ===========================================================================
# il giro completo
# ===========================================================================
def verifica(ctx: E.MatchCtx, snap: E.Snapshot, d: E.Decision,
             params: Dict[str, Any],
             sollecitati: Optional[Dict[str, int]] = None) -> List[Violazione]:
    """Tutti i controlli su UNA decisione, prima che venga applicata.

    Un controllo che solleva non ferma gli altri e non ferma la certificazione:
    diventa esso stesso un referto (`XX-ERRORE`), perche' un controllo rotto e'
    un'informazione, non un motivo per non sapere niente del resto.
    """
    out: List[Violazione] = []
    for codice, regola, fn, quando in _REGISTRO:
        try:
            if quando is not None and not quando(ctx, snap, d, params):
                continue          # nessun caso: il controllo non ha niente da dire
            if sollecitati is not None:
                sollecitati[codice] = sollecitati.get(codice, 0) + 1
            det = fn(ctx, snap, d, params)
        except Exception as ex:  # noqa: BLE001
            out.append(Violazione(f"{codice}-ERRORE", regola,
                                  f"il controllo e' esploso: {type(ex).__name__}: {ex}",
                                  ctx.state, snap.minute, snap.goals))
            continue
        if det:
            out.append(Violazione(codice, regola, det, ctx.state, snap.minute, snap.goals))
    return out


def elenco_controlli() -> List[Tuple[str, str]]:
    """(codice, regola) di tutto cio' che questa certificazione sa verificare.

    Comprende i controlli K, che non guardano una decisione ma il rapporto fra
    la memoria del bot e il mercato: se non fossero in questo elenco non
    comparirebbero nella copertura, e un controllo che non si conta non esiste.
    """
    return ([(c, r) for c, r, _fn, _q in _REGISTRO] + list(_REGISTRO_BANCO)
            + list(_REGISTRO_RIGA) + list(_REGISTRO_REPLAY))


def mai_sollecitati(sollecitati: Dict[str, int]) -> List[Tuple[str, str]]:
    """I controlli che non hanno MAI avuto un caso da giudicare.

    Sono il buco vero di un referto: non dicono «il bot e' sano», dicono «non
    lo so». Vanno letti come lavoro da fare — uno scenario da provocare — non
    come una garanzia.
    """
    return [(c, r) for c, r in elenco_controlli() if not sollecitati.get(c)]


# ===========================================================================
# P. DIFETTI DI PROGETTAZIONE — non «ha violato una regola», ma «e' fatto in
#    modo che prima o poi la violera'».
#
# I controlli A-J guardano UNA decisione. Questi guardano il COMPORTAMENTO nel
# tempo, ed e' li' che vivono i difetti che hanno prodotto i loop del 15/09:
# nessuna singola decisione era illegale, ma ripetuta ottocento volte diventava
# ottocento ordini veri. Un difetto di progettazione non si vede in un istante.
# ===========================================================================
@dataclass
class Andamento:
    """Memoria fra una decisione e l'altra, per una partita."""

    # (ruolo, mercato, selezione, lato) -> quante gambe sono state proposte
    proposte_per_ruolo: Dict[tuple, int] = field(default_factory=dict)
    # la stessa identica azione proposta di fila
    ultima_azione: Optional[tuple] = None
    ripetizioni: int = 0
    max_ripetizioni: int = 0
    azione_piu_ripetuta: Optional[tuple] = None
    # gambe viste per ref: serve a contare quante ne nascono per ruolo/ciclo
    refs_per_ruolo_ciclo: Dict[tuple, int] = field(default_factory=dict)
    # ⚠️ 16/09 — il massimo PER RUOLO, non solo quello assoluto. Con il solo
    # massimo assoluto un ruolo che si ripresenta per regola (`ko_green`, §15.6)
    # copre tutti gli altri: su 35760084 in `taker` le 31 ripresentazioni di
    # `ko_green` avrebbero nascosto qualunque altra riproposizione sotto quella
    # soglia. Un controllo che vede una cosa sola non e' un controllo.
    ripetizioni_correnti: Dict[str, int] = field(default_factory=dict)
    max_per_ruolo: Dict[str, int] = field(default_factory=dict)
    azione_piu_ripetuta_per_ruolo: Dict[str, tuple] = field(default_factory=dict)


def osserva(and_: Andamento, ctx: E.MatchCtx, d: E.Decision) -> None:
    """Aggiorna l'andamento con quello che il motore ha appena proposto."""
    for a in _piazzamenti(d):
        k = (a.role, a.market, a.selection, a.side)
        and_.proposte_per_ruolo[k] = and_.proposte_per_ruolo.get(k, 0) + 1
        kc = (a.role, int(ctx.cycle_no or 0), a.side)
        and_.refs_per_ruolo_ciclo[kc] = and_.refs_per_ruolo_ciclo.get(kc, 0) + 1
        firma = (a.role, a.market, a.selection, a.side,
                 round(float(a.price), 2), round(float(a.size), 2))
        if firma == and_.ultima_azione:
            and_.ripetizioni += 1
        else:
            and_.ultima_azione = firma
            and_.ripetizioni = 1
        if and_.ripetizioni > and_.max_ripetizioni:
            and_.max_ripetizioni = and_.ripetizioni
            and_.azione_piu_ripetuta = firma
        # lo stesso conteggio, ma tenuto PER RUOLO
        ruolo = str(a.role)
        precedente = and_.azione_piu_ripetuta_per_ruolo.get(ruolo)
        if precedente == firma:
            and_.ripetizioni_correnti[ruolo] = and_.ripetizioni_correnti.get(ruolo, 0) + 1
        else:
            and_.ripetizioni_correnti[ruolo] = 1
            and_.azione_piu_ripetuta_per_ruolo[ruolo] = firma
        if and_.ripetizioni_correnti[ruolo] > and_.max_per_ruolo.get(ruolo, 0):
            and_.max_per_ruolo[ruolo] = and_.ripetizioni_correnti[ruolo]


# I RITMI DI RIPRESENTAZIONE CHE LA SPEC DICHIARA. Non sono riproposizioni: sono
# una regola scritta. §15.6 della Costituzione: «in live l'ordine di uscita viene
# RI-PRESENTATO al mercato ogni `ko_green_retry_s` secondi e si abbina appena il
# prezzo c'e' — l'equivalente pratico di un ordine appoggiato». Il conteggio
# resta nel referto (niente si nasconde), ma il verdetto deve dire QUALE regola
# lo prevede, altrimenti accusa il bot di rispettare la propria spec — che e'
# esattamente il falso positivo contro cui mette in guardia §6.7 del processo.
# ⚠️ ORDINE DELL'UTENTE 16/09 — LA TABELLA E' VUOTA, E DEVE RESTARLO.
# Fino a stamattina conteneva `ko_green`: §15.6 prescriveva la ri-presentazione
# ogni `ko_green_retry_s` sul percorso taker, e il verdetto la dichiarava
# prevista invece di accusarla. Adesso l'uscita al fischio e' una lay APPOGGIATA
# in ogni modalita': non si ri-presenta piu', e se ricompare una serie di
# `ko_green` identici quella NON e' una regola rispettata, e' una VIOLAZIONE —
# P1 deve dirlo, e P3 deve tornare a contarla nella divergenza fra proposto e
# piazzato. La tabella resta perche' il meccanismo serve al primo ritmo che
# verra' dichiarato davvero; oggi nessun ruolo ne ha uno.
RITMI_DICHIARATI: Dict[str, str] = {}

# soglie: sopra queste il comportamento non e' piu' spiegabile come «riprova»
RIPETIZIONI_SOSPETTE = 20          # la stessa identica azione, di fila
PROPOSTE_PER_CICLO_SOSPETTE = 50   # gambe dello stesso ruolo nello stesso ciclo


def difetti_di_progettazione(and_: Andamento, *, ordini_piazzati: int,
                             righe_scritte: int) -> List[Violazione]:
    """Il verdetto sul COMPORTAMENTO, a fine partita."""
    out: List[Violazione] = []

    for ruolo, quante in sorted(and_.max_per_ruolo.items(), key=lambda x: -x[1]):
        if quante < RIPETIZIONI_SOSPETTE:
            continue
        r = and_.azione_piu_ripetuta_per_ruolo.get(ruolo) or (ruolo, "", "", "", 0, 0)
        regola = RITMI_DICHIARATI.get(ruolo)
        if regola:
            out.append(Violazione(
                "P1-DICHIARATA", "ripetizione PREVISTA dalla spec: si conta, non si accusa",
                f"{ruolo} {r[3]} {r[5]} @ {r[4]} ripresentata {quante} volte di fila. "
                f"La regola che lo prevede e' {regola}. Da portare all'utente se il "
                f"numero sorprende: il bot sta facendo quello che c'e' scritto."))
        else:
            out.append(Violazione(
                "P1", "il motore non deve riproporre all'infinito la stessa identica azione",
                f"{ruolo} {r[3]} {r[5]} @ {r[4]} riproposta {quante} volte di fila. "
                f"Senza un freno a valle sarebbero altrettanti ordini VERI: e' la "
                f"forma esatta del loop del 15/09."))

    for (ruolo, ciclo, lato), n in sorted(and_.refs_per_ruolo_ciclo.items(),
                                          key=lambda x: -x[1]):
        if ruolo in RITMI_DICHIARATI:
            continue
        if n >= PROPOSTE_PER_CICLO_SOSPETTE:
            out.append(Violazione(
                "P2", "un ciclo non genera decine di gambe dello stesso ruolo",
                f"ciclo {ciclo}: {n} gambe '{ruolo}' {lato}. La strategia ne prevede "
                f"UNA per ciclo; il resto e' riproposizione."))
            break

    proposte = sum(and_.proposte_per_ruolo.values())
    if proposte and ordini_piazzati and proposte > ordini_piazzati * 5:
        out.append(Violazione(
            "P3", "quello che il motore propone e quello che arriva a mercato non "
                  "devono divergere di ordini di grandezza",
            f"{proposte} gambe proposte contro {ordini_piazzati} ordini piazzati "
            f"({proposte / max(ordini_piazzati, 1):.0f}x). Il bot regge solo grazie "
            f"ai freni a valle: se ne salta uno, escono tutte."))
    return out


@dataclass
class Referto:
    """L'esito su UNA partita."""

    event_id: str
    tick: int = 0
    decisioni: int = 0
    azioni: int = 0
    stati_visti: List[str] = field(default_factory=list)
    # perche' il bot ha fatto (o non ha fatto) qualcosa: `Decision.reason`
    # contato per frequenza. Senza questo un referto «zero azioni» non si sa
    # leggere: non si distingue un bot che RIFIUTA da un bot che non VEDE.
    motivi: Dict[str, int] = field(default_factory=dict)
    andamento: "Andamento" = field(default_factory=lambda: Andamento())
    ordini_piazzati: int = 0
    righe_scritte: int = 0
    # quante volte OGNI controllo ha avuto un caso da giudicare: senza questo,
    # «zero violazioni» non si sa leggere
    sollecitati: Dict[str, int] = field(default_factory=dict)
    violazioni: List[Violazione] = field(default_factory=list)
    note: List[str] = field(default_factory=list)
    # 30/09 (ondata 2): lo scenario NON ha esercitato cio' per cui esiste (il
    # suo contatore-chiave e' rimasto a zero): il referto dice NON ESERCITATO,
    # non OK. Ogni voce e' la causa, in una riga.
    non_esercitato: List[str] = field(default_factory=list)
    # controlli NON APPLICABILI a questo bot (codice -> causa): nella tabella
    # della copertura escono marcati, non come «non lo so»
    non_applicabili: Dict[str, str] = field(default_factory=dict)
    # contatori dello scenario (rifiuti provocati, firme, chiusure colpite con
    # effetto, giri dell'attesa dell'esito...) per la regola del NON ESERCITATO
    contatori: Dict[str, int] = field(default_factory=dict)

    @property
    def pulita(self) -> bool:
        return not self.violazioni

    def per_codice(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in self.violazioni:
            out[v.codice] = out.get(v.codice, 0) + 1
        return out
