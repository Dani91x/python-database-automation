"""ARRESTO ORDINATO di Safe e Omega (02/10/2026, ordine dell'utente: «niente resta in coda»).

All'arresto del bot (stop dall'app col file ``ARRESTO``, SIGTERM/SIGBREAK/Ctrl-C, eccezione
fatale che esce dal ciclo), PRIMA di uscire:
  1. si annullano i SUOI ordini vivi non abbinati: le righe ``pending`` col bet_id (solo i
     propri bet_id, MAI un annullo su tutto il mercato), con la stessa via con cui il bot
     annulla gia' quella riga: canale del runner (paper e live), coda paper del runner,
     REST per bet_id (SOLO live: una riga paper non tocca mai il conto vero). Tetto
     ``ARRESTO_ANNULLO_TIMEOUT_S`` (10 s): oltre, le righe restanti si dichiarano;
  2. le posizioni ABBINATE che restano (righe ``open``) NON si chiudono (regola
     dell'utente): diario + UN CRITICAL «posizione lasciata a mercato per arresto»;
  3. lo stato dell'arresto si scrive nel diario del bot (``arresto``), poi si esce.
Stesso modello dello scalper (``scalper_session.chiudi_all_arresto``). Non solleva mai.
ASCII-only.
"""
from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger("safe.arresto_bot")

#: tetto dell'annullo degli ordini vivi all'arresto (come lo scalper)
ARRESTO_ANNULLO_TIMEOUT_S = 10.0
#: il giro piu' lungo che puo' essere in corso quando arriva lo stop (Safe 2 s di
#: attesa + letture; Omega fino a ~20 s: commento di ``desktop/main.js``), piu' la
#: fetta di dormita che si accorge del file d'arresto (1 s)
GIRO_MAX_S = 20.0 + 1.0
#: tempo MASSIMO dall'ordine di arresto all'uscita: giro in corso + annullo + scritture.
#: ``desktop/main.js`` (``shutdownGraceMs``) concede almeno questo piu' 10 s.
TEMPO_MASSIMO_ARRESTO_S = GIRO_MAX_S + ARRESTO_ANNULLO_TIMEOUT_S + 4.0
#: cause d'arresto
CAUSA_STOP_APP = "stop_app"
CAUSA_SEGNALE = "segnale"
CAUSA_ERRORE_FATALE = "errore_fatale"
CRITICO_POSIZIONE = "posizione lasciata a mercato per arresto"


def _segnale_in_interrupt(signum: int, _frame: Any) -> None:
    raise KeyboardInterrupt(f"segnale {signum}")


def installa_segnali() -> list:
    """SIGTERM e (su Windows) SIGBREAK diventano un ``KeyboardInterrupt``: il ciclo esce
    dal suo ``finally`` e fa l'arresto ordinato. Ritorna i segnali installati."""
    fatti = []
    for nome in ("SIGTERM", "SIGBREAK"):
        s = getattr(signal, nome, None)
        if s is None:
            continue
        try:
            signal.signal(s, _segnale_in_interrupt)
            fatti.append(nome)
        except (ValueError, OSError):   # non dal thread principale: niente
            pass
    return fatti


def dormi_finche_arresto(pausa: float, *, richiesto: Callable[[], bool],
                         dormi: Callable[[float], None] = time.sleep) -> bool:
    """``time.sleep(pausa)`` a fette di (al piu') 1 s: torna subito (True) se l'arresto
    e' richiesto. Stessa durata totale di prima quando non lo e' (False)."""
    resto = max(0.0, float(pausa))
    while True:
        if richiesto():
            return True
        if resto <= 1e-9:
            return False
        fetta = min(1.0, resto)
        dormi(fetta)
        resto -= fetta


def esegui_ciclo_con_arresto(ciclo: Callable[[], None], chiudi: Callable[[str], Any], *,
                             stop_app: Callable[[], bool]) -> None:
    """Esegue il ciclo del bot e, COMUNQUE esca, chiama ``chiudi(causa)`` (l'arresto
    ordinato) PRIMA di lasciare il processo. Un'eccezione fatale si rilancia dopo."""
    causa = CAUSA_ERRORE_FATALE
    try:
        ciclo()
        causa = CAUSA_STOP_APP if stop_app() else CAUSA_SEGNALE
    except KeyboardInterrupt:
        causa = CAUSA_SEGNALE
    finally:
        try:
            chiudi(causa)
        except BaseException as ex:  # noqa: BLE001 - l'uscita non si blocca mai
            logger.critical("arresto ordinato fallito (%s): %s", causa, str(ex)[:200])


def _bet_id_della_riga(tr: dict[str, Any], db: Any) -> Optional[str]:
    bet = str(tr.get("bet_id") or "").strip()
    if bet:
        return bet
    meta = tr.get("meta") or {}
    rid = meta.get("flumine_request_id") if isinstance(meta, dict) else None
    leggi = getattr(db, "get_live_order_mirror", None)
    if rid and callable(leggi):
        try:
            m = leggi(f"awlq{int(rid)}", str(tr.get("mode") or "paper")) or {}
            return str(m.get("bet_id") or "").strip() or None
        except Exception:  # noqa: BLE001 - specchio illeggibile: niente bet_id
            return None
    return None


def annulla_riga(tr: dict[str, Any], *, market: Any, db: Any, porta_kw: dict[str, Any],
                 now: datetime) -> str:
    """Annulla l'ordine di UNA riga con la sua via. Ritorna l'esito: ``annullato``,
    ``vivo``, ``ignoto``, ``accodato`` (coda paper), ``nessun_ordine`` (riga paper
    senza runner: nessun ordine esiste). Mai un REST per una riga paper."""
    from Betfair.safe_strategy import execution as X

    mode = str(tr.get("mode") or "")
    bet = _bet_id_della_riga(tr, db)
    meta = dict(tr.get("meta") or {})
    if not bet:
        return "senza_bet_id"
    canale = X.ha_marker_canale(tr) and bool(porta_kw)
    if mode == "paper":
        if canale:
            ann = X.annulla_su_betfair(None, bet_id=bet, market_id=tr.get("market_id"),
                                       **porta_kw)
        elif meta.get("flumine_request_id"):
            from Betfair.omega import omega_service as OS

            ok = OS._flumine_enqueue_cancel(tr, db=db, bet_id=bet, meta=meta, now=now)
            return "accodato" if ok else "ignoto"
        else:
            return "nessun_ordine"
    else:
        ann = X.annulla_su_betfair(market, bet_id=bet, market_id=tr.get("market_id"),
                                   **(porta_kw if canale else {}))
    if ann is None or not getattr(ann, "riletto", False):
        return "annullato" if (ann is not None and getattr(ann, "ok", False)) else "ignoto"
    return "vivo" if float(getattr(ann, "size_remaining", 0.0) or 0.0) > 0 else "annullato"


def chiudi_bot_all_arresto(*, bot: str, db: Any, market: Any, causa: str,
                           porta_kw_di: Callable[[dict], dict],
                           timeout_s: float = ARRESTO_ANNULLO_TIMEOUT_S,
                           ora: Callable[[], float] = time.monotonic,
                           adesso: Optional[Callable[[], datetime]] = None) -> dict[str, Any]:
    """L'arresto ordinato di un bot (vedi il modulo). Non solleva mai."""
    adesso = adesso or (lambda: datetime.now(timezone.utc))
    esito: dict[str, Any] = {"bot": bot, "causa": causa, "annulli": [], "non_tentati": [],
                             "posizioni": [], "letture_ko": []}
    scadenza = ora() + max(0.0, float(timeout_s))
    try:
        pendenti = list(db.list_trades("pending") or [])
    except Exception as ex:  # noqa: BLE001
        pendenti = []
        esito["letture_ko"].append(f"pending: {str(ex)[:120]}")
    for tr in pendenti:
        voce = {"trade_id": tr.get("id"), "mode": tr.get("mode"),
                "market_id": tr.get("market_id"), "bet_id": tr.get("bet_id")}
        if ora() >= scadenza:
            esito["non_tentati"].append(voce)
            continue
        try:
            voce["esito"] = annulla_riga(tr, market=market, db=db,
                                         porta_kw=porta_kw_di(tr) or {}, now=adesso())
        except Exception as ex:  # noqa: BLE001 - una riga non ferma le altre
            voce["esito"] = "ignoto"
            voce["errore"] = str(ex)[:120]
        esito["annulli"].append(voce)
    try:
        aperte = list(db.list_trades("open") or [])
    except Exception as ex:  # noqa: BLE001
        aperte = []
        esito["letture_ko"].append(f"open: {str(ex)[:120]}")
    esito["posizioni"] = [{"trade_id": t.get("id"), "mode": t.get("mode"),
                           "event_id": t.get("event_id"), "market_id": t.get("market_id"),
                           "selection_id": t.get("selection_id"), "side": t.get("side"),
                           "size": t.get("size"), "price": t.get("price")} for t in aperte]
    problemi = []
    if esito["posizioni"]:
        problemi.append(f"{CRITICO_POSIZIONE}: {len(esito['posizioni'])} posizioni")
    dubbi = [v for v in esito["annulli"]
             if v.get("esito") in ("ignoto", "vivo", "senza_bet_id")] + esito["non_tentati"]
    if dubbi:
        problemi.append(f"{len(dubbi)} ordini non annullati con certezza (VERIFICARE sul conto)")
    if esito["letture_ko"]:
        problemi.append("letture del DB fallite all'arresto")
    esito["critical"] = bool(problemi)
    esito["nota"] = "; ".join(problemi) or "arresto pulito: nessun ordine vivo, nessuna posizione"
    try:
        db.log("arresto", esito)
    except Exception:  # noqa: BLE001 - diario best-effort
        pass
    if problemi:
        logger.critical("[%s] ARRESTO [%s]: %s", bot, causa, esito["nota"])
    else:
        logger.info("[%s] arresto [%s]: %s", bot, causa, esito["nota"])
    return esito
