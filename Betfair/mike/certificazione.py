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
        if a.role != "over_cover" or a.side != "back":
            continue
        S = sum(float(l.matched or 0.0) for l in ctx.legs
                if not l.archived and l.market == E.MARKET_OU35
                and l.selection == E.SEL_UNDER and l.side == "back")
        S -= sum(float(l.matched or 0.0) for l in ctx.legs
                 if not l.archived and l.market == E.MARKET_OU35
                 and l.selection == E.SEL_UNDER and l.side == "lay")
        if S <= 0:
            return f"copertura da {a.size} senza nessun Under abbinato"
        Po = float(a.price)
        c = float(params.get("commission") or 0.05)
        factor = float(params.get("cover_factor") or 1.2)
        atteso = factor * S / max((Po - 1.0) * (1.0 - c), 1e-9)
        # la copertura entra anche a TRANCHE (frazione) e a residuo: si segnala
        # solo un ordine piu' GRANDE del pieno, che e' l'errore pericoloso.
        if float(a.size) > atteso * 1.35 + 0.05:
            return (f"copertura {a.size} > pieno {round(atteso, 2)} "
                    f"(S={round(S, 2)} Po={Po})")
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


@_controllo("H2", "il re-ingresso vuole ESATTAMENTE 1 gol e il primo tempo "
                  "(§3 Fase 6)",
            quando=lambda ctx, snap, d, p: any(a.role == 'reentry' for a in _piazzamenti(d)))
def _h2(ctx, snap, d, params):
    if not any(a.role == "reentry" for a in _piazzamenti(d)):
        return None
    if snap.goals is not None and int(snap.goals) != 1:
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
    if not E.operabile(_book(snap, E.MARKET_OU35, E.SEL_UNDER)):
        return None                    # ancora sospeso: non c'e' niente da rileggere
    return (f"mercato riaperto e le gambe {r.get('refs')} non sono state rilette da "
            f"Betfair (sospeso a {r.get('ts')}): il bot le sta dando per vive")


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
    """(codice, regola) di tutto cio' che questa certificazione sa verificare."""
    return [(c, r) for c, r, _fn, _q in _REGISTRO]


def mai_sollecitati(sollecitati: Dict[str, int]) -> List[Tuple[str, str]]:
    """I controlli che non hanno MAI avuto un caso da giudicare.

    Sono il buco vero di un referto: non dicono «il bot e' sano», dicono «non
    lo so». Vanno letti come lavoro da fare — uno scenario da provocare — non
    come una garanzia.
    """
    return [(c, r) for c, r, _fn, _q in _REGISTRO if not sollecitati.get(c)]


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

    @property
    def pulita(self) -> bool:
        return not self.violazioni

    def per_codice(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in self.violazioni:
            out[v.codice] = out.get(v.codice, 0) + 1
        return out
