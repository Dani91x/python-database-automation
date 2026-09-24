# -*- coding: utf-8 -*-
"""chiusura_manuale.py - il "CHIUDI ORA" dei QUATTRO bot tennis (D3, 24/09/2026).

DECISIONE DELL'UTENTE (24/09): "il Chiudi deve funzionare anche per i 4 bot
tennis". Prima il bottone della Control Room era spento per `tennis_scalper`,
`tennis_pro`, `tennis_flb`, `tennis_swing` ("nessun percorso di chiusura
manuale"), e il green-up della ladder (`tennis_live_order_worker._do_greenup`)
agisce sulla strategia di CATTURA, non su quella del bot: chiudeva l'esposizione
della ladder e lasciava il bot libero di riaprire.

LA VIA DELLA RICHIESTA (nessuna tabella nuova, nessun processo nuovo):
  UI -> `request_tennis_live_order({action:'chiudi_bot', bot, event_id,
  market_id, mode, trade_id, client_ref})` -> `tennis_live_order_queue` (la coda
  che il runner tennis GIA' drena) -> `tennis_live_order_worker` riconosce
  l'azione e chiama `gestisci_riga` -> la riga resta `processing` finche' il bot
  ha finito -> `avanza` (dal `bot_control_worker`, ogni 3 s) scrive `done` con
  l'esito o `error` col motivo. La UI rilegge la riga con `get_tennis_live_order`
  (fasi: inviata / presa in carico / eseguita / rifiutata).

LE GUARDIE (fail-closed, mai un ordine "per sicurezza"):
  * IDENTITA' (`richiesta_ambigua`, come Omega/Safe/Mike): bot fra i quattro,
    partita e mercato presenti e UGUALI a quelli su cui il bot e' ospitato,
    modalita' della richiesta UGUALE a quella con cui il bot esegue (quella che
    la riga della UI mostra: `_modo_strategia`). Paper e live mai mischiati;
  * il bot deve essere OSPITATO e non gia' fermo;
  * ANTI DOPPIA USCITA: una seconda richiesta per la stessa (partita, bot)
    mentre la prima e' in corso risponde "gia' in uscita" senza toccare il bot;
    un bot che stava GIA' uscendo da solo lo dice lui (esito del bot) e non
    piazza un secondo ordine (`condotta_ordini` sezione 4).

A USCITA FINITA (bot che lo dice + blotter pari, `_strategy_is_flat`):
  * il bot viene disabilitato (`_disable_strategy`, come a missione compiuta);
  * la riga `tennis_bot_control` va a `stopped` con `stats.chiusura_manuale`:
    e' il marcatore che il PONTE legge per NON riarmarlo su quella partita
    (`tennis_bot_service.riconcilia_interruttori`) finche' l'utente non lo
    riarma dalla scheda (la RPC `tennis_bot_arm` azzera le stats);
  * la riga della coda va a `done` con l'esito.
Se il bot ha finito ma il blotter non e' pari entro `GRAZIA_FLAT_S` (un residuo
non chiudibile), si conclude lo stesso ma lo stato e' `error` e il messaggio lo
DICE: mai uno "stopped" bugiardo (stessa regola del disarmo).

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from .. import avvio_app as AA
from ..tennis_scalper import condotta_ordini as CD
from . import tennis_db

logger = logging.getLogger(__name__)

AZIONE = "chiudi_bot"
BOT_TENNIS = ("tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing")
# chiave in `tennis_bot_control.stats`: il ponte non riarma una riga che la porta
CHIAVE_STATS = "chiusura_manuale"
# stati NON attivi in cui il marcatore vale (quelli attivi li arma l'utente)
_STATI_FERMI = ("stopped", "error", "done")
# finestra concessa al blotter per diventare pari dopo che il bot ha finito
# (la stessa del disarmo: `tennis_runner._STOPPING_GRACE_S`)
GRAZIA_FLAT_S = 45.0
# oltre questo tempo senza esito dal bot (nessun book: mercato sospeso o
# chiuso) una posizione GIA' pari si conclude; una non pari si aspetta sempre
ATTESA_ESITO_S = 120.0
# un bot che sparisce dall'hosting (riavvio dello stream) si aspetta al piu'
# questo tempo, poi la richiesta si chiude in errore e lo si dice
ATTESA_OSPITE_S = 180.0

_TESTO_ESITO = {
    CD.ESITO_USCITA_AVVIATA: (
        "eseguita: il bot ha annullato i suoi ordini vivi e chiuso l'abbinato "
        "al prezzo di mercato"),
    CD.ESITO_GIA_IN_USCITA: (
        "gia' in uscita: il bot stava gia' chiudendo, nessun secondo ordine; "
        "la sua chiusura e' finita"),
    CD.ESITO_NESSUNA_POSIZIONE: (
        "nessuna posizione aperta: il bot non aveva niente da chiudere"),
}
_CODA_TESTO = " - fermo su questa partita finche' non lo riarmi"


# ---------------------------------------------------------------------------
# lettura della riga di coda
# ---------------------------------------------------------------------------
def _campo(row: Dict[str, Any], nome: str) -> Any:
    """Come `tennis_live_order_worker._merged_field`: il comando vive nel
    `payload` jsonb, non in colonne."""
    for chiave in ("payload", "params", "cmd", "command"):
        nodo = row.get(chiave)
        if isinstance(nodo, dict) and nodo.get(nome) not in (None, ""):
            return nodo.get(nome)
    return row.get(nome)


def comando_da_riga(row: Dict[str, Any]) -> Dict[str, Any]:
    def _s(v: Any) -> Optional[str]:
        t = str(v).strip() if v is not None else ""
        return t or None

    return {
        "action": str(_campo(row, "action") or "").strip().lower(),
        "bot": _s(_campo(row, "bot")),
        "event_id": _s(_campo(row, "event_id")),
        "market_id": _s(_campo(row, "market_id")),
        "mode": (_s(_campo(row, "mode")) or "").lower() or None,
        "trade_id": _campo(row, "trade_id"),
        "client_ref": _s(_campo(row, "client_ref")),
    }


def _risultato(cmd: Dict[str, Any], rid: Any, *, ok: bool, messaggio: str,
               esito: Optional[str] = None, errore: Optional[str] = None,
               **extra: Any) -> Dict[str, Any]:
    out = {
        "ok": bool(ok),
        "action": AZIONE,
        "mode": cmd.get("mode"),
        "bot": cmd.get("bot"),
        "event_id": cmd.get("event_id"),
        "market_id": cmd.get("market_id"),
        "trade_id": cmd.get("trade_id"),
        "esito": esito,
        "error": errore,
        "message": messaggio,
        "customer_order_ref": ("awtq" + str(rid))[:32],
    }
    out.update(extra)
    return out


# ---------------------------------------------------------------------------
# lo stato delle richieste in corso (vive nella sessione del runner)
# ---------------------------------------------------------------------------
def _registro(session: Any) -> Dict[Tuple[str, str], Dict[str, Any]]:
    reg = getattr(session, "chiusure_manuali", None)
    if reg is None:
        reg = {}
        try:
            session.chiusure_manuali = reg
        except Exception:  # noqa: BLE001 - sessione finta senza slot
            pass
    return reg


def in_chiusura(session: Any, chiave: Tuple[str, str]) -> bool:
    """La (partita, bot) ha un "chiudi ora" in corso? Il runner NON riavvia lo
    stream sotto un'uscita manuale non conclusa (il rebuild ri-istanzierebbe
    il bot con la riga ancora `running`)."""
    return tuple(chiave) in _registro(session)


def _modo_riga(strat: Any, session: Any) -> str:
    # la STESSA funzione dello specchio ordini (la modalita' che la riga della
    # UI porta): mai una seconda regola (difetto 33 del catalogo)
    from .tennis_live_order_worker import _modo_strategia

    return _modo_strategia(strat, session)


def richiesta_ambigua(cmd: Dict[str, Any], strat: Any, session: Any) -> Optional[str]:
    """Il motivo per cui la richiesta NON e' di questo bot su questa partita,
    o None. Stesse regole di Omega/Safe/Mike (`richiesta_ambigua`)."""
    ev, bot = cmd.get("event_id"), cmd.get("bot")
    mercato_bot = str(getattr(strat, "_tennis_scoped_market_id", "") or "")
    meta = (getattr(session, "market_meta", {}) or {}).get(ev) or {}
    mercato_partita = str(meta.get("market_id") or "")
    if not mercato_bot or cmd.get("market_id") != mercato_bot:
        return ("mercato della richiesta (%s) diverso da quello su cui %s opera "
                "(%s)" % (cmd.get("market_id"), bot, mercato_bot or "ignoto"))
    if mercato_partita and mercato_partita != mercato_bot:
        return ("il mercato del bot (%s) non e' quello della partita %s (%s)"
                % (mercato_bot, ev, mercato_partita))
    modo = _modo_riga(strat, session)
    if cmd.get("mode") != modo:
        return ("modalita' della richiesta (%s) diversa da quella con cui %s "
                "esegue su questa partita (%s): paper e live non si mischiano"
                % (cmd.get("mode"), bot, modo))
    return None


# ---------------------------------------------------------------------------
# 1. la presa in carico (thread del worker della coda)
# ---------------------------------------------------------------------------
def prendi_in_carico(session: Any, rid: Any, cmd: Dict[str, Any], *,
                     db: Any = tennis_db,
                     adesso: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """`None` = presa in carico (la riga resta `processing`, l'esito lo scrive
    `avanza`); un dizionario = esito IMMEDIATO (`ok` False = rifiutata).
    `adesso`: l'orologio di `avanza` (il replay passa il tempo di mercato)."""
    bot, ev, mid, modo = (cmd.get("bot"), cmd.get("event_id"),
                          cmd.get("market_id"), cmd.get("mode"))
    if bot not in BOT_TENNIS or not ev or not mid or modo not in ("paper", "live"):
        return _risultato(cmd, rid, ok=False, errore="richiesta_ambigua",
                          messaggio=("rifiutato: la richiesta non porta bot tennis, "
                                     "partita, mercato e modalita' (paper|live)"))
    chiave = (str(ev), str(bot))
    reg = _registro(session)
    if chiave in reg:
        # ANTI DOPPIA USCITA: il bot ha gia' il comando, un secondo non si manda.
        # La richiesta doppia resta `processing` e riceve lo STESSO esito della
        # prima quando la chiusura finisce (mai un "eseguita" prima del tempo).
        reg[chiave].setdefault("doppie", []).append(rid)
        _attivita(db, ev, bot, "uscita_manuale", {
            "fase": "gia_in_uscita", "richiesta": rid,
            "richiesta_in_corso": reg[chiave].get("rid"),
            "note": "chiusura manuale gia' in corso: nessun secondo comando"})
        return None
    strat = (getattr(session, "hosted", {}) or {}).get(chiave)
    if strat is None:
        return _risultato(cmd, rid, ok=False, errore="bot_non_ospitato",
                          messaggio=("rifiutato: %s non e' armato su questa partita "
                                     "nel runner tennis (niente da chiudere dal bot)"
                                     % bot))
    if getattr(strat, "_tennis_disabled", False):
        return _risultato(cmd, rid, ok=False, errore="bot_fermo",
                          messaggio="rifiutato: %s e' gia' fermo su questa partita" % bot)
    ambigua = richiesta_ambigua(cmd, strat, session)
    if ambigua is not None:
        _attivita(db, ev, bot, "error", {"reason": "richiesta_ambigua",
                                        "motivo": ambigua, "richiesta": rid,
                                        "mode_richiesta": modo})
        return _risultato(cmd, rid, ok=False, errore="richiesta_ambigua",
                          messaggio="rifiutato: %s" % ambigua)
    if not CD.supporta_uscita_manuale(strat):
        return _risultato(cmd, rid, ok=False, errore="non_supportato",
                          messaggio="rifiutato: %s non parla il protocollo del "
                                    "chiudi ora" % bot)
    CD.chiedi_uscita_manuale(strat)
    reg[chiave] = {"rid": rid, "cmd": dict(cmd), "istanza": id(strat),
                   "t0": time.monotonic() if adesso is None else float(adesso),
                   "finito_da": None, "assente_da": None, "esito": None}
    _attivita(db, ev, bot, "uscita_manuale", {
        "fase": "presa_in_carico", "richiesta": rid, "mode": modo,
        "motivo": CD.MOTIVO_USCITA_MANUALE,
        "note": ("chiudi ora dell'utente: il bot annulla i suoi ordini vivi, "
                 "chiude l'abbinato e non rientra su questa partita")})
    logger.info("[tennis-chiudi] %s@%s: chiudi ora preso in carico (richiesta %s, %s)",
                bot, ev, rid, modo)
    return None


def gestisci_riga(session: Any, row: Dict[str, Any], rid: Any, *,
                  db: Any = tennis_db) -> None:
    """La riga `chiudi_bot` gia' RIVENDICATA (processing) dal worker della coda.
    Scrive subito l'esito se c'e'; altrimenti la lascia `processing`."""
    cmd = comando_da_riga(row)
    try:
        res = prendi_in_carico(session, rid, cmd, db=db)
    except Exception as ex:  # noqa: BLE001 - mai una riga muta
        logger.exception("[tennis-chiudi] richiesta %s KO", rid)
        res = _risultato(cmd, rid, ok=False, errore="errore_interno",
                         messaggio="rifiutato: errore interno (%s)" % str(ex)[:160])
    if res is None:
        return
    _scrivi_esito(db, rid, res)


def _scrivi_esito(db: Any, rid: Any, res: Dict[str, Any]) -> None:
    try:
        if res.get("ok"):
            db.write_tennis_order_done(rid, res)
        else:
            db.write_tennis_order_error(rid, res)
    except Exception:  # noqa: BLE001 - l'esito resta nel log e nell'attivita'
        logger.exception("[tennis-chiudi] esito della richiesta %s non scritto", rid)


def _rispondi_tutte(db: Any, rec: Dict[str, Any], res: Dict[str, Any]) -> None:
    """L'esito alla richiesta in corso E alle sue doppie (stesso esito, e la
    doppia dice che non ha prodotto un secondo comando)."""
    rid = rec.get("rid")
    _scrivi_esito(db, rid, res)
    for altra in rec.get("doppie") or []:
        r2 = dict(res)
        r2["customer_order_ref"] = ("awtq" + str(altra))[:32]
        r2["message"] = ("gia' in uscita (richiesta %s), nessun secondo ordine - %s"
                         % (rid, res.get("message")))
        _scrivi_esito(db, altra, r2)


def _attivita(db: Any, ev: Any, bot: Any, kind: str, payload: Dict[str, Any]) -> None:
    try:
        db.write_tennis_bot_activity(str(ev), str(bot), kind, dict(payload))
    except Exception as e:  # noqa: BLE001 - il log non ferma mai niente
        logger.debug("[tennis-chiudi] attivita' %s/%s KO: %s", ev, bot, e)


# ---------------------------------------------------------------------------
# 2. l'avanzamento (thread del bot_control_worker, ogni 3 s)
# ---------------------------------------------------------------------------
def avanza(flumine: Any, session: Any, *, e_flat: Callable[[Any, Any], bool],
           disabilita: Callable[[Any], None], db: Any = tennis_db,
           adesso: Optional[float] = None) -> List[Tuple[str, str]]:
    """Porta avanti ogni "chiudi ora" in corso. Ritorna le (partita, bot)
    concluse in questo giro. `e_flat`/`disabilita` sono le funzioni VERE del
    runner (`_strategy_is_flat`, `_disable_strategy`), passate da lui."""
    reg = _registro(session)
    if not reg:
        return []
    ora = time.monotonic() if adesso is None else float(adesso)
    concluse: List[Tuple[str, str]] = []
    for chiave, rec in list(reg.items()):
        ev, bot = chiave
        cmd = rec.get("cmd") or {}
        rid = rec.get("rid")
        strat = (getattr(session, "hosted", {}) or {}).get(chiave)
        if strat is None:
            # riavvio dello stream in corso: l'istanza nuova arriva al rebuild
            if rec.get("assente_da") is None:
                rec["assente_da"] = ora
            if ora - rec["assente_da"] >= ATTESA_OSPITE_S:
                reg.pop(chiave, None)
                _rispondi_tutte(db, rec, _risultato(
                    cmd, rid, ok=False, errore="interrotta",
                    messaggio=("interrotta: il bot non e' piu' ospitato dal runner "
                               "(riavvio dello stream) - verifica la posizione")))
                concluse.append(chiave)
            continue
        rec["assente_da"] = None
        if id(strat) != rec.get("istanza"):
            # ISTANZA NUOVA (rebuild dello stream): il comando si rida' a lei,
            # altrimenti il bot ri-istanziato riaprirebbe
            rec["istanza"] = id(strat)
            if CD.supporta_uscita_manuale(strat):
                CD.chiedi_uscita_manuale(strat)
        if getattr(strat, "_tennis_disabled", False):
            reg.pop(chiave, None)
            _rispondi_tutte(db, rec, _risultato(
                cmd, rid, ok=False, errore="interrotta",
                messaggio=("interrotta: il bot e' stato fermato (disarmo) prima di "
                           "finire la chiusura - verifica la posizione")))
            concluse.append(chiave)
            continue
        esito_bot = getattr(strat, "uscita_manuale", None)
        if isinstance(esito_bot, dict) and rec.get("esito") is None:
            rec["esito"] = esito_bot.get("esito")
        try:
            flat = bool(e_flat(flumine, strat))
        except Exception:  # noqa: BLE001 - blotter illeggibile = non flat
            flat = False
        if esito_bot is None:
            if flat and ora - float(rec.get("t0") or ora) >= ATTESA_ESITO_S:
                rec["esito"] = CD.ESITO_NESSUNA_POSIZIONE
                _concludi(session, chiave, rec, strat, flat=True, db=db,
                          disabilita=disabilita,
                          nota="il bot non ha ricevuto book (mercato sospeso o "
                               "chiuso) e il blotter e' pari")
                concluse.append(chiave)
            continue
        try:
            finita = bool(strat.uscita_manuale_finita())
        except Exception:  # noqa: BLE001 - nel dubbio non e' finita
            finita = False
        if not finita:
            rec["finito_da"] = None
            continue
        if flat:
            _concludi(session, chiave, rec, strat, flat=True, db=db,
                      disabilita=disabilita)
            concluse.append(chiave)
            continue
        if rec.get("finito_da") is None:
            rec["finito_da"] = ora
        if ora - rec["finito_da"] >= GRAZIA_FLAT_S:
            _concludi(session, chiave, rec, strat, flat=False, db=db,
                      disabilita=disabilita)
            concluse.append(chiave)
    return concluse


def _concludi(session: Any, chiave: Tuple[str, str], rec: Dict[str, Any], strat: Any,
              *, flat: bool, db: Any, disabilita: Callable[[Any], None],
              nota: Optional[str] = None) -> None:
    ev, bot = chiave
    cmd = rec.get("cmd") or {}
    rid = rec.get("rid")
    esito = rec.get("esito") or CD.ESITO_NESSUNA_POSIZIONE
    # 1) il bot non piazza piu' niente (come a missione compiuta)
    disabilita(strat)
    _registro(session).pop(chiave, None)
    ora_iso = tennis_db._now_iso()
    stats = AA.stats_timbrate(getattr(strat, "stats", None), AA.boot_id_ambiente())
    stats[CHIAVE_STATS] = {"richiesta": rid, "esito": esito, "mode": cmd.get("mode"),
                           "flat": bool(flat), "ts": ora_iso}
    messaggio = _TESTO_ESITO.get(esito, esito) + _CODA_TESTO
    if nota:
        messaggio += " (%s)" % nota
    errore_riga = None
    if not flat:
        errore_riga = ("chiudi ora: il bot ha finito ma il blotter NON e' pari dopo "
                       "%ds (residuo non chiudibile) - verifica la posizione su "
                       "Betfair/ladder" % int(GRAZIA_FLAT_S))
        messaggio += ". ATTENZIONE: " + errore_riga
    # 2) la riga per partita: il marcatore che il ponte legge per non riarmare
    try:
        db.set_tennis_bot_status(ev, bot, "stopped" if flat else "error",
                                 stopped=True, stats=stats, error=errore_riga)
    except Exception as e:  # noqa: BLE001 - l'esito si scrive comunque
        logger.warning("[tennis-chiudi] stato %s/%s KO: %s", ev, bot, e)
    _attivita(db, ev, bot, "uscita_manuale", {
        "fase": "eseguita" if flat else "eseguita_con_residuo", "esito": esito,
        "richiesta": rid, "mode": cmd.get("mode"), "flat": bool(flat),
        "motivo": CD.MOTIVO_USCITA_MANUALE})
    # 3) la risposta alla UI (anche alle richieste doppie, stesso esito)
    _rispondi_tutte(db, rec, _risultato(cmd, rid, ok=True, esito=esito,
                                        messaggio=messaggio, flat=bool(flat)))
    logger.info("[tennis-chiudi] %s@%s: chiudi ora concluso (%s, flat=%s)",
                bot, ev, esito, flat)


# ---------------------------------------------------------------------------
# 3. per il PONTE: le (partita, bot) chiuse dall'utente, da non riarmare
# ---------------------------------------------------------------------------
def chiusi_dall_utente(righe: Optional[Iterable[Dict[str, Any]]]) -> Set[Tuple[str, str]]:
    out: Set[Tuple[str, str]] = set()
    for r in righe or []:
        if str((r or {}).get("status") or "").strip().lower() not in _STATI_FERMI:
            continue
        st = r.get("stats")
        if isinstance(st, dict) and st.get(CHIAVE_STATS):
            out.add((str(r.get("event_id") or ""), str(r.get("bot_key") or "")))
    return out
