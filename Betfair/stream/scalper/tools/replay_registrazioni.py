# -*- coding: utf-8 -*-
"""LO SCALPER CALCIO SULLE REGISTRAZIONI VERE - il SERVIZIO di produzione sul banco.

Fa rivivere a `scalper_session.run_session` (il processo che il supervisore
`scalper_service` lancia per OGNI partita armata dalla UI) una partita
registrata, e giudica la CONDOTTA con `Betfair/stream/scalper/certificazione.py`.
Non misura il profitto (`PROCESSO_STANDARD_BOT.md` gradino 3).

LA CATENA, e nessun passo e' saltato o riscritto:

    raw registrato  `_live_raw/<id>/<id>.raw.jsonl` (stream NATIVO Betfair)
      -> flumine    `FlumineSimulation` + `HistoricalStream` del BANCO COMUNE
                    (`banco_comune.MotoreReplay`, UN `SimulatedMiddleware`,
                    tetti di flumine aperti, lapse al fischio e alla
                    sospensione, orologio monotono)
      -> `scalper_session.run_session` VERO: legge il control, costruisce i
         parametri (VALIDATED_PARAMS + whitelist UI + stake), sceglie paper/live
         (client `paper_trade`), crea `ScalperStrategy` e il semaforo di
         rischio, arma lo specchio ordini, fa girare heartbeat, stop da UI,
         kill-switch, cap globale, fine vita (KO+10'), gestione del crash e
         stato finale - TUTTO codice di produzione
      -> `ScalperStrategy` VERA (`check_market_book` / `process_market_book`)
         su ogni book dei mercati che la sessione ha scelto dal catalogo
      -> ordini VERI su flumine (`market.place_order`, LAPSE, pacchetto
         asincrono eseguito da flumine quando il tempo di mercato supera
         `place_latency + betDelay`: e' cosi' anche in produzione, dove il bot
         non si blocca sulla REST)
      -> lo SPECCHIO VERO della sessione (`_make_session_mirror`, cioe'
         `LiveTradingStrategy.process_orders`) alla sua cadenza (1 s di
         mercato): le righe di `betfair_live_orders` si catturano, non si scrivono

I FINTI INIETTATI (e soltanto questi; ognuno con le chiavi del vero):
  * `scalper_session.Db`          -> `_DbFinto`: `scalper_control` con le
                                     colonne e i CHECK di `migrations/scalper_bot.sql`,
                                     `scalper_activity`, `live_alerts`, `live_follow`
  * `auth.build_client`/`keep_alive` -> `_TradingFinto`: il CATALOGO costruito dai
                                     `marketDefinition` del raw (limite 1)
  * `flumine.Flumine` / `clients.BetfairClient` -> `_FrameworkSessione`: il
                                     framework della sessione e' un involucro sul
                                     quadro del banco; il client chiesto dalla
                                     sessione (paper_trade, order_stream,
                                     min_bet_validation) si REGISTRA per la parita'
  * `scalper_session._order_mirror_loop` -> lo stesso `mirror.process_orders`
                                     chiamato dal thread del motore alla stessa
                                     cadenza (1 s), per non leggere il blotter da
                                     due thread
  * `scalper_session.time` e `time.time` -> l'OROLOGIO DI MERCATO (vedi sotto)
  * `scalper_session.KILL_FILE`   -> un file in una cartella temporanea del
                                     replay: MAI il `STOP_SCALPER` della cwd, che
                                     fermerebbe la produzione vera
  * `db_client.get_supabase_client` -> ESPLODE: nessun accesso al DB vero puo'
                                     passare in silenzio
Nessun ordine a Betfair, nessuna scrittura sul DB vero.

L'OROLOGIO. In produzione il thread della sessione dorme `HEARTBEAT_S` (5 s)
fra un giro di sorveglianza e l'altro mentre il thread di flumine riceve lo
stream. Qui i due thread si passano il TURNO (`_Orologio`): il motore avanza
i book finche' il tempo di mercato non raggiunge la sveglia della sessione,
poi si ferma e la sessione fa il suo giro (heartbeat, stop, cap, fine vita)
esattamente a quell'istante di mercato. `time.time` (che lo scalper usa per il
tetto transazioni/ora, il rate dei submin e il dry-run) e' l'orologio di
mercato: in produzione il tempo reale COINCIDE con quello del mercato, nel
replay no.

LIMITI DICHIARATI (stampati nel referto)
  1. IL CATALOGO NON C'E' nel raw: si ricostruisce dai `marketDefinition`
     (tipi di mercato veri, nomi dei runner sintetizzati con la convenzione
     Betfair: MATCH_ODDS 3 = "The Draw"). L'ordinamento `MAXIMUM_TRADED` non si
     riproduce: con 4 tipi di sessione e `max_results=25` entra tutto comunque.
  2. LO SCANNER NON SERVE: lo scalper legge il MarketBook direttamente
     (par.6.2 non applicabile, dichiarato).
  3. PUNTEGGI: la sessione in modalita' maker non legge `live_now`; i watcher
     di intervallo e theta non sono nel perimetro. 28/09: lo SNIPER si'
     (scenari `sniper`, `sniper-paper`, `sniper-uscite-auto`): la riga
     `live_now` viene dal sidecar `.scores.jsonl`, la linea dalla funzione di
     produzione `applica_linea_sniper` ogni 15 s di mercato (il thread
     `sniper-line` non parte: dormirebbe sul turno dell'orologio); controlli
     propri Z1-Z4 (`_Banco.controlli_sniper`).
  4. I PACCHETTI REPLACE (park-trim-replace dei submin) creano l'ordine nuovo
     dentro flumine: il guasto CP non li colpisce (limite del banco comune).
  5. SETTLEMENT: la sessione finisce a KO+10' (fine vita di produzione) e il
     mercato non chiude prima: `pnl_settled` non si misura (e in produzione e'
     lo stesso).
  6. `FreshDelaySimulatedExecution` (paper) viene installata come in
     produzione ma nel banco non cambia nulla: l'attesa del bet delay la fa
     `_check_pending_packages` PRIMA dell'esecuzione.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time as _time_mod
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...backtest import chiusura_parziale as CP
from ...backtest import uscite_manuali as UM
from ...live_order_build import SUBMIN_IMPORTO_FINALE_MIN
from .. import certificazione as CERT

logger = logging.getLogger(__name__)

# i veri, catturati all'import: l'orologio finto NON deve mai chiamare se stesso
_TIME_VERO = _time_mod.time
_MONOTONIC = _time_mod.monotonic

# oltre questi secondi REALI senza che il turno passi, il banco si dichiara
# bloccato invece di restare appeso
ATTESA_MASSIMA_REALE_S = 300.0

EVENTO_DI_RIFERIMENTO = "35760084"

# i guasti: quanti piazzamenti colpire e di quanto ritardare l'esito
PIAZZAMENTI_RIFIUTATI = 6
PIAZZAMENTI_IGNOTI = 6
RITARDO_ESITO_IGNOTO_S = 20.0
# quanto aspetta il supervisore prima di dichiarare orfana una sessione morta
# (`scalper_service.ORPHAN_HEARTBEAT_S`, letto dal vero) e quanto l'utente
# prima di riarmare
ATTESA_RIARMO_S = 60.0

SCENARIO_SNIPER = "sniper"
SCENARIO_SNIPER_PAPER = "sniper-paper"
SCENARIO_SNIPER_AUTO = "sniper-uscite-auto"
SCENARI_SNIPER = (SCENARIO_SNIPER, SCENARIO_SNIPER_PAPER, SCENARIO_SNIPER_AUTO)
#: 04/10: la sessione armata dall'auto-mode con l'interruttore in soldi veri
SCENARIO_AUTO_LIVE = "auto-live"
#: 05/10 MEDIA UNDER (SPEC_MEDIA_UNDER_2026-10-05.md par.9): la modalita' nuova,
#: accesa a mano dalla scheda su UN mercato. Soldi veri simulati (client reale
#: simulato del banco), prova, e l'altro mercato.
SCENARIO_MEDIA = "media-under"
SCENARIO_MEDIA_PAPER = "media-under-paper"
SCENARIO_MEDIA_35 = "media-under-35"
#: 05/10 (giro 2, spec GIRO2 par.3): gli scenari DICHIARATI in piu' della
#: modalita', tutti come `media-under` (Under 2,5, soldi veri simulati) con UNA
#: differenza ciascuno: i parametri che la scheda scrive diversi dai valori di
#: serie, oppure un guasto del banco gia' costruito per lo scalper.
#: nome -> (parametri della scheda, guasto del banco o None, descrizione)
SCENARI_MEDIA_VARIANTI: Dict[str, Tuple[Dict[str, Any], Optional[str], str]] = {
    "media-under-obiettivo-030": ({"media_obiettivo": 0.30}, None,
                                  "come `media-under` con l'obiettivo FISSO a 0,30 EUR netti"),
    "media-under-rientri-1": ({"media_max_rientri": 1}, None,
                              "come `media-under` con `media_max_rientri` = 1"),
    "media-under-rischio-30": ({"media_rischio_max": 30.0}, None,
                               "come `media-under` con `media_rischio_max` = 30 EUR"),
    "media-under-tick-1": ({"media_tick_rientro": 1, "media_tick_chiusura": 1}, None,
                           "come `media-under` con rientro e chiusura a 1 tick"),
    "media-under-riavvio": ({}, "riavvio",
                            "come `media-under` col guasto `riavvio` (processo ucciso a "
                            "meta' della finestra pre-match, riarmo dell'utente)"),
    "media-under-rifiuti-betfair": ({}, "rifiuti-betfair",
                                    "come `media-under` col guasto `rifiuti-betfair` "
                                    "(i primi piazzamenti rifiutati)"),
    "media-under-esiti-ignoti": ({}, "esiti-ignoti",
                                 "come `media-under` col guasto `esiti-ignoti` (i primi "
                                 "piazzamenti senza esito per un tempo)"),
    "media-under-kill-switch": ({}, "kill-switch",
                                "come `media-under` col guasto `kill-switch` (file "
                                "STOP_SCALPER a meta' della finestra pre-match)"),
    "media-under-bot-fermo": ({}, "bot-fermo",
                              "come `media-under` col guasto `bot-fermo` (STOP dalla UI "
                              "a meta' della finestra pre-match)"),
    # 06/10 (giro 3): i due replay chiesti dall'utente, liquidita' minima per lato
    # (`media_min_size`, EUR sul miglior prezzo di punta e di banca) piu' bassa
    "media-under-liquidita-100": ({"media_min_size": 100.0}, None,
                                  "come `media-under` (Under 2,5) con liquidita' minima "
                                  "100 EUR per lato (richiesta dell'utente, 06/10)"),
    "media-under-35-liquidita-50": ({"media_min_size": 50.0,
                                     "media_mercato": "OVER_UNDER_35"}, None,
                                    "come `media-under-35` (Under 3,5) con liquidita' "
                                    "minima 50 EUR per lato (richiesta dell'utente, 06/10)"),
}
SCENARI_MEDIA: Tuple[str, ...] = ((SCENARIO_MEDIA, SCENARIO_MEDIA_PAPER, SCENARIO_MEDIA_35)
                                  + tuple(SCENARI_MEDIA_VARIANTI))


def mercato_media(scenario: str) -> Optional[str]:
    """Il mercato che la scheda sceglie nello scenario "media under" (None fuori).
    Una variante dichiarata puo' scegliere il suo (06/10: Under 3,5)."""
    if scenario not in SCENARI_MEDIA:
        return None
    variante = SCENARI_MEDIA_VARIANTI.get(scenario)
    if variante is not None and variante[0].get("media_mercato"):
        return str(variante[0]["media_mercato"])
    return "OVER_UNDER_35" if scenario == SCENARIO_MEDIA_35 else "OVER_UNDER_25"


def guasto_dello_scenario(scenario: str) -> str:
    """Il guasto del banco che lo scenario prova: il suo nome, o per una variante
    della modalita' (``SCENARI_MEDIA_VARIANTI``) il guasto che dichiara."""
    variante = SCENARI_MEDIA_VARIANTI.get(scenario)
    if variante is not None:
        return variante[1] or scenario
    return scenario

def _quando_media(ms: Optional[int], ko_ms: Optional[int], in_gioco_ms: Optional[int]) -> str:
    """L'istante di mercato per chi legge: minuti al fischio o minuto di gioco."""
    if ms is None:
        return "?"
    inizio = in_gioco_ms if in_gioco_ms is not None else ko_ms
    if inizio is None:
        return "ms %d" % ms
    d = int(round((ms - inizio) / 1000.0))
    if d < 0:
        return "pre-match, %d'%02d\" al fischio" % (-d // 60, -d % 60)
    return "in gioco al %d'%02d\"" % (d // 60, d % 60)


def riepilogo_cicli_media(ordini: List[Any], nati_ms: Dict[str, int],
                          abbinato_ms: Dict[str, int],
                          eventi: List[Tuple[str, Dict[str, Any], int]], *,
                          ko_ms: Optional[int], in_gioco_ms: Optional[int],
                          commissione: float,
                          stato_runner: Optional[str]) -> Tuple[List[Dict[str, Any]],
                                                                Dict[str, Any]]:
    """05/10 (giro 2, spec GIRO2 par.2.2): il riepilogo PER CICLO della
    modalita', in euro, dagli ORDINI veri del blotter (campi di flumine).

    Un ciclo comincia con la sua punta d'ingresso (attivita' ``media_ingresso``:
    fa solo da confine nel tempo); gli importi, gli abbinati, la banca finale e
    il profitto vengono dagli ordini. L'importo ESATTO di un rientro (prima del
    multiplo di 0,50) non e' nell'ordine: si legge dall'attivita'
    ``media_rientro`` del ciclo, nello stesso ordine.

    Torna (cicli, conto): ogni ciclo e' un dizionario (``riga`` e' la frase del
    referto); ``conto`` ha lordo, commissione (per mercato sul netto vincente,
    come Betfair e come ``banco_comune.pnl``) e NETTO dei cicli con esito noto."""
    from .. import media_under_bot as MU

    inizi = sorted(int(t) for k, _p, t in eventi if k == "media_ingresso")
    rientri_ev = [(int(t), p) for k, p, t in eventi if k == "media_rientro"]
    per_ciclo: Dict[int, List[Any]] = {}
    for o in sorted(ordini, key=lambda x: nati_ms.get(str(getattr(x, "id", "")), 0)):
        nato = nati_ms.get(str(getattr(o, "id", "")), 0)
        i = max([0] + [n for n, t in enumerate(inizi) if t <= nato])
        per_ciclo.setdefault(i, []).append(o)
    cicli: List[Dict[str, Any]] = []
    lordo_tot = 0.0
    ignoti = 0
    for i in sorted(per_ciclo):
        oo = per_ciclo[i]
        da = inizi[i] if i < len(inizi) else None
        a = inizi[i + 1] if i + 1 < len(inizi) else None
        punte = [o for o in oo if MU._lato(o) == "BACK"]
        banche = [o for o in oo if MU._lato(o) == "LAY"]
        es = [p for t, p in rientri_ev if (da is None or t >= da) and (a is None or t < a)]
        pezzi = []
        if punte:
            p0 = punte[0]
            pezzi.append("ingresso %.2f @%.2f (abbinato %.2f, %s)" % (
                float(p0.order_type.size), float(p0.order_type.price),
                MU.abbinato(p0)[0], _quando_media(nati_ms.get(str(p0.id)), ko_ms, in_gioco_ms)))
        rientri = []
        for n, o in enumerate(punte[1:]):
            e = es[n] if n < len(es) else {}
            rientri.append({"quota": float(o.order_type.price),
                            "esatto": e.get("importo_esatto"),
                            "piazzato": float(o.order_type.size),
                            "abbinato": round(MU.abbinato(o)[0], 2)})
            pezzi.append("rientro %d @%.2f: esatto %s, piazzato %.2f, abbinato %.2f" % (
                n + 1, float(o.order_type.price),
                "%.2f" % e["importo_esatto"] if e.get("importo_esatto") is not None else "?",
                float(o.order_type.size), MU.abbinato(o)[0]))
        puntato = sum(MU.abbinato(o)[0] for o in punte)
        pezzi.append("totale puntato massimo %.2f" % puntato)
        con_abb = [o for o in banche if MU.abbinato(o)[0] > 0]
        finale = con_abb[-1] if con_abb else (banche[-1] if banche else None)
        banca: Dict[str, Any] = {}
        if finale is not None:
            m = MU.abbinato(finale)[0]
            quando = abbinato_ms.get(str(finale.id)) if m > 0 else None
            resto = float(getattr(finale, "size_remaining", 0.0) or 0.0)
            if MU.vivo_o_in_volo(finale):
                fine_b = "VIVA a mercato (resto %.2f)" % resto
            elif m + 0.005 >= float(finale.order_type.size):
                fine_b = "abbinata per intero"
            else:
                fine_b = "NON piu' a mercato (annullata o scaduta, resto %.2f)" % (
                    float(finale.order_type.size) - m)
            banca = {"importo": float(finale.order_type.size),
                     "quota": float(finale.order_type.price), "abbinato": round(m, 2),
                     "dove": _quando_media(quando, ko_ms, in_gioco_ms) if m > 0 else None,
                     "fine": fine_b}
            pezzi.append("banca finale %.2f @%.2f %s, abbinata %.2f%s, a fine replay %s" % (
                banca["importo"], banca["quota"],
                str(getattr(finale.order_type, "persistence_type", "") or ""), m,
                (" (ultimo abbinamento: %s)" % banca["dove"]) if m > 0 else "", fine_b))
        else:
            pezzi.append("nessuna banca")
        pos = MU.posizione_da_ordini(oo)
        c = float(banche[-1].order_type.price) if banche else 2.0
        pari = abs(pos.se_vince - pos.se_perde) <= 0.02 + 0.005 * c
        if pos.puntato <= 1e-9 and not con_abb:
            esito, lordo = "NESSUNA POSIZIONE", 0.0
        elif pari and con_abb:
            esito, lordo = "CHIUSO", min(pos.se_vince, pos.se_perde)
        elif stato_runner in ("WINNER", "LOSER"):
            lordo = pos.se_vince if stato_runner == "WINNER" else pos.se_perde
            esito = "APERTO, regolato dal libro finale (Under %s)" % stato_runner
        else:
            esito, lordo = "APERTO, esito ignoto", None
        if lordo is None:
            ignoti += 1
            pezzi.append("posizione aperta: se vince l'Under %+.2f, se perde %+.2f [%s]"
                         % (pos.se_vince, pos.se_perde, esito))
        else:
            lordo_tot += lordo
            netto = lordo * (1.0 - commissione) if lordo > 0 else lordo
            if esito != "CHIUSO" and pos.puntato > 1e-9:
                pezzi.append("posizione aperta: se vince l'Under %+.2f, se perde %+.2f"
                             % (pos.se_vince, pos.se_perde))
            pezzi.append("profitto lordo %+.2f, netto %+.2f [%s]" % (lordo, netto, esito))
        cicli.append({"ciclo": len(cicli) + 1, "ordini": len(oo), "rientri": rientri,
                      "puntato": round(puntato, 2), "banca": banca, "esito": esito,
                      "lordo": None if lordo is None else round(lordo, 2),
                      "riga": "; ".join(pezzi)})
    comm = max(lordo_tot, 0.0) * float(commissione)
    conto = {"lordo": round(lordo_tot, 2), "commissione": round(comm, 2),
             "netto": round(lordo_tot - comm, 2), "aliquota": float(commissione),
             "cicli_esito_ignoto": ignoti}
    return cicli, conto


# 28/09 (CANTIERE N3): gli scenari a uscite MANUALI (interruttore spento, il
# default di produzione dopo ogni avvio). Tutti gli ALTRI scenari girano con
# le uscite AUTOMATICHE accese e lo DICHIARANO nel referto (NOTA_USCITE_AUTO).
SCENARI_USCITE_MANUALI: Tuple[str, ...] = UM.SCENARI
NOTA_USCITE_AUTO = ("SCENARIO DICHIARATO: uscite automatiche accese, e' la "
                    "condotta certificata (params `uscite_automatiche=True`, "
                    "come li scrive l'interruttore della UI su AUTOMATICHE)")


def uscite_automatiche_scenario(scenario: str) -> bool:
    """Il valore di `uscite_automatiche` che lo scenario scrive nei params della
    riga `scalper_control` (lo leggono `ScalperStrategy`/`SniperStrategy` e, a
    caldo, `scalper_session.applica_uscite_automatiche`)."""
    return scenario not in SCENARI_USCITE_MANUALI


#: la chiave (solo del banco) con le posizioni candidate di un `sniper_green`
CHIAVE_PREFISSI_GREEN = "_prefissi_banco"


def prefissi_del_green(sn: Any) -> List[str]:
    """Le posizioni dello sniper che, nell'istante di `sniper_green`, soddisfano
    la condizione del verde (`sniper_bot`: chiusura non viva, abbinata, entrate
    ancora presenti). Di norma una sola; piu' d'una solo se due verdi cadono
    sullo stesso book (dichiarato: Z3 accetta la firma di una qualsiasi)."""
    out: List[str] = []
    for pos in list(dict(getattr(sn, "_pos", {}) or {}).values()):
        close = getattr(pos, "close", None)
        if close is None or not getattr(pos, "entries", None):
            continue
        try:
            viva = bool(sn._has_live(close))
        except Exception:  # noqa: BLE001 - finto senza _has_live: non vivo
            viva = False
        if viva or float(getattr(close, "size_matched", 0.0) or 0.0) <= 0:
            continue
        out.append(sn._prefisso_uscite(pos))
    return out


def z3_verdi_senza_la_loro_firma(eventi: List[Tuple[str, Dict[str, Any]]]) -> List[str]:
    """Z3 per IDENTITA' (N3, reperto del coordinatore): ogni `sniper_green` a
    uscite manuali deve avere la SUA `uscita_eseguita_su_approvazione`: stessa
    chiave (la sua posizione + `target`), emessa PRIMA del verde e usata UNA
    volta sola. Un verde senza la sua firma e una firma d'altra posizione non
    si compensano mai. Torna la descrizione di ogni verde abusivo."""
    libere: List[str] = []
    abusivi: List[str] = []
    for n, (k, p) in enumerate(eventi):
        if k == "uscita_eseguita_su_approvazione":
            libere.append(str(p.get("chiave") or ""))
        elif k == "sniper_green":
            cand = [str(x) + "target" for x in (p.get(CHIAVE_PREFISSI_GREEN) or [])]
            presa = next((c for c in libere if c in cand), None)
            if presa is None:
                abusivi.append("verde #%d su %s senza la sua firma (firme libere: %s)"
                               % (n, cand or "posizione ignota", libere or "nessuna"))
            else:
                libere.remove(presa)
    return abusivi


def sniper_acceso(scenario: str) -> bool:
    """Gli scenari con lo SNIPER acceso: i `sniper*` e quelli a uscite manuali
    (maker + sniper nella stessa sessione, come in produzione dal 25/09)."""
    return scenario in SCENARI_SNIPER or scenario in SCENARI_USCITE_MANUALI

SCENARI_DESCRITTI: Dict[str, str] = {
    "base": ("come gira in produzione, sul percorso degli ordini VERI: il control "
             "che la UI scrive coi suoi default (maker, stake 25, missione "
             "2-tick accesa) e dry_run=False (LIVE)"),
    "paper": ("lo stesso control con dry_run=True: client flumine paper_trade, "
              "latenza paper, esecuzione a bet delay fresco. Paper = live "
              "(controllo S6)"),
    "senza-missione": ("SOLO la casella 'missione 2-tick' spenta dalla UI "
                       "(one_green_per_phase=False): il bot fa tutti i cicli "
                       "che la strategia gli concede, cosi' i controlli di "
                       "ciclo hanno piu' casi"),
    "bot-fermo": ("a meta' della finestra pre-match l'utente preme STOP "
                  "(`scalper_stop`: running -> stopping): force-flat, attesa "
                  "del flat, stato 'stopped'"),
    "kill-switch": ("a meta' della finestra pre-match compare il file "
                    "STOP_SCALPER (in una cartella del replay, mai quella vera)"),
    "esiti-ignoti": ("i primi %d piazzamenti restano SENZA ESITO per %d s di "
                     "mercato (PENDING, nessun bet_id): la risposta di Betfair "
                     "tarda, come in un timeout" % (PIAZZAMENTI_IGNOTI,
                                                   int(RITARDO_ESITO_IGNOTO_S))),
    "rifiuti-betfair": ("i primi %d piazzamenti sono RIFIUTATI da un trading "
                        "control di flumine (place_order torna False, stato "
                        "Violation): difetto 2 del catalogo" % PIAZZAMENTI_RIFIUTATI),
    "riavvio": ("a meta' della finestra pre-match il PROCESSO della sessione "
                "muore; dopo %d s il supervisore la marca 'error' (orfana), "
                "l'utente la riarma e parte una sessione NUOVA: la posizione "
                "della vecchia deve essere governata o dichiarata (S7)"
                % int(ATTESA_RIARMO_S)),
    CP.SCENARIO: "come `base`, ma " + CP.DESCRIZIONE,
    # 28/09 (cantiere D2): lo SNIPER in gioco, acceso di default in produzione
    # dal 25/09 e mai certificato sul banco. Sessione VERA con `sniper_mode`,
    # vita della sessione di produzione (`auto_mode.vita_sessione_s`: KO+130'),
    # linea Under (gol+1).5 dalla riga `live_now` ricostruita dal sidecar
    # `.scores.jsonl` (gli stessi `score_home/score_away/minute` che il runner
    # scrive in `live_now`) con la funzione di produzione
    # `scalper_session.applica_linea_sniper` alla stessa cadenza (15 s di
    # mercato). N3 (28/09): interruttore uscite ACCESO e dichiarato, come in
    # tutti gli scenari esistenti; le uscite manuali stanno in `uscite-manuali`.
    SCENARIO_SNIPER: ("come `base` (LIVE, dry_run=False) con lo SNIPER acceso "
                      "(`sniper_mode`, stake 10) e le uscite AUTOMATICHE "
                      "dichiarate: maker + sniper nella stessa "
                      "sessione fino a KO+130'"),
    SCENARIO_SNIPER_PAPER: ("come `sniper` con dry_run=True: client paper, "
                            "stessa sessione (paper = live)"),
    SCENARIO_SNIPER_AUTO: ("come `sniper` con le uscite AUTOMATICHE accese "
                           "(interruttore della sessione): lo sniper prende "
                           "profitto da solo"),
    # N3 (28/09): le uscite MANUALI, maker + sniper (come `sniper`, LIVE). Le
    # firme passano da `params.uscite_approvate` della riga, rilette dalla
    # sessione VERA al battito (`uscite_proposte.applica_firme`).
    UM.SCENARIO_MANUALI: "come `sniper`, ma " + UM.DESCRIZIONE_MANUALI,
    UM.SCENARIO_FIRMATE: "come `sniper`, ma " + UM.DESCRIZIONE_FIRMATE,
    # 04/10 (ordine dell'utente «quando scelgo soldi veri devono partire ordini
    # veri»): la sessione ARMATA DALL'AUTO-MODE con l'interruttore in soldi veri.
    # Il dry_run lo decide la funzione VERA del supervisore
    # (`auto_mode.dry_run_alla_nascita("live")`): prima del 04/10 nasceva sempre
    # in dry-run e nessun ordine vero partiva.
    SCENARIO_AUTO_LIVE: ("come `base`, ma la riga la arma l'AUTO-MODE con "
                         "l'interruttore in SOLDI VERI (dry_run deciso dal "
                         "supervisore, origine 'auto'): devono partire ordini VERI"),
    # 05/10 MEDIA UNDER: la scheda accende la modalita' coi valori di serie
    # (``media_under_bot.VALORI_DI_SERIE`` = ``MEDIA_UNDER_DEFAULTS`` della UI),
    # maker e sniper NON armati, vita della sessione fino a fine partita;
    # controlli M1-M11 (``certificazione.verifica_media``) e S6 (parita').
    SCENARIO_MEDIA: ("MEDIA UNDER su Under 2,5, soldi veri SIMULATI (dry_run=False, "
                     "client reale simulato del banco), valori di serie della "
                     "scheda: ingresso, banca PERSIST, rientri, in gioco solo "
                     "segnalazione"),
    SCENARIO_MEDIA_PAPER: ("come `media-under` con dry_run=True: client paper "
                           "(paper = live, controllo S6)"),
    SCENARIO_MEDIA_35: "come `media-under` sul mercato Under 3,5",
    **{nome: v[2] for nome, v in SCENARI_MEDIA_VARIANTI.items()},
}


# ---------------------------------------------------------------------------
# il control che la UI scrive (`ScalperPanel.tsx` + `lib/scalper.ts`)
# ---------------------------------------------------------------------------
def control_della_ui(event_id: str, scenario: str) -> Dict[str, Any]:
    """La riga `scalper_control` che `scalper_activate` scrive coi DEFAULT della
    UI (`SCALPER_PARAM_DEFAULTS`, mode 'maker', stake 25, missione ON,
    ht/sniper/theta spenti). Le chiavi sono le colonne della migrazione.
    Gli scenari cambiano SOLO numeri che la UI espone."""
    params: Dict[str, Any] = {
        "scalp_ticks": 1, "stop_ticks": 1, "min_flow": 10, "min_size": 300,
        "price_min": 1.5, "price_max": 4.6, "entry_stop_before_s": 420,
        "flatten_before_s": 180, "event_profit_target": 1, "event_loss_cap": 1.5,
        "one_green_per_phase": True, "ht_mode": False, "sniper_mode": False,
        "sniper_stake": 10,
    }
    if scenario == "senza-missione":
        params["one_green_per_phase"] = False
    if sniper_acceso(scenario):
        # 28/09: lo sniper acceso (il default di produzione dal 25/09)
        params["sniper_mode"] = True
    # N3 (28/09): l'interruttore delle uscite, sempre SCRITTO e DICHIARATO
    params["uscite_automatiche"] = uscite_automatiche_scenario(scenario)
    if scenario in SCENARI_MEDIA:
        # 05/10: la scheda con la modalita' accesa (`ScalperPanel.tsx`: sniper,
        # theta e intervallo spenti, i parametri della modalita' coi valori di serie)
        from .. import media_under_bot as MU

        params["sniper_mode"] = False
        params.update(MU.VALORI_DI_SERIE)
        params["media_mode"] = True
        params["media_mercato"] = mercato_media(scenario)
        params["media_obiettivi_live"] = list(MU.VALORI_DI_SERIE["media_obiettivi_live"])
        # 05/10 (giro 2): la variante dichiarata cambia SOLO i suoi parametri
        params.update(dict(SCENARI_MEDIA_VARIANTI.get(scenario, ({}, None, ""))[0]))
        return {
            "event_id": str(event_id), "status": "requested", "mode": "maker",
            "dry_run": scenario == SCENARIO_MEDIA_PAPER, "stake": 25,
            "params": params, "origine": "manuale",
            "bias": None, "bias_meta": None, "stats": None, "error": None,
            "requested_at": None, "started_at": None, "stopped_at": None,
            "heartbeat_at": None, "updated_at": None,
        }
    if scenario == SCENARIO_AUTO_LIVE:
        # 04/10: la riga come la scrive il SUPERVISORE (`scalper_service.giro_auto`):
        # dry_run dalla modalita' dell'interruttore, origine 'auto'
        from .. import auto_mode as AM

        return {
            "event_id": str(event_id), "status": "requested", "mode": "maker",
            "dry_run": AM.dry_run_alla_nascita("live"), "stake": 25,
            "params": params, "origine": AM.ORIGINE_AUTO,
            "bias": None, "bias_meta": None, "stats": None, "error": None,
            "requested_at": None, "started_at": None, "stopped_at": None,
            "heartbeat_at": None, "updated_at": None,
        }
    return {
        "event_id": str(event_id), "status": "requested", "mode": "maker",
        "dry_run": scenario in ("paper", SCENARIO_SNIPER_PAPER), "stake": 25,
        "params": params,
        "bias": None, "bias_meta": None, "stats": None, "error": None,
        "requested_at": None, "started_at": None, "stopped_at": None,
        "heartbeat_at": None, "updated_at": None,
    }


# ---------------------------------------------------------------------------
# la registrazione: catalogo, KO, nomi
# ---------------------------------------------------------------------------
def percorso_raw(data_dir: str, event_id: str) -> str:
    return os.path.join(data_dir, str(event_id), "%s.raw.jsonl" % event_id)


def leggi_definizioni(raw: str) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    """{market_id: {"market_type", "runners": [(id, sortPriority)]}} e il
    `marketTime` del MATCH_ODDS, dal PRIMO `marketDefinition` di ogni mercato."""
    definizioni: Dict[str, Dict[str, Any]] = {}
    ko: Optional[str] = None
    with io.open(raw, "r", encoding="utf-8") as fh:
        for riga in fh:
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            for mc in d.get("mc") or []:
                md = mc.get("marketDefinition")
                if not md:
                    continue
                mid = str(mc.get("id"))
                if mid not in definizioni:
                    definizioni[mid] = {
                        "market_type": md.get("marketType"),
                        "runners": [(int(r["id"]), r.get("sortPriority"))
                                    for r in (md.get("runners") or []) if r.get("id")],
                    }
                if md.get("marketType") == "MATCH_ODDS" and ko is None:
                    ko = md.get("marketTime")
    return definizioni, ko


def primo_publish_time_ms(raw: str) -> Optional[int]:
    """Il `pt` della prima riga del raw: l'istante in cui la sessione si arma.
    Senza, le scritture fatte PRIMA del primo book (arming, running) avrebbero
    l'ora del PC invece di quella del mercato."""
    with io.open(raw, "r", encoding="utf-8") as fh:
        for riga in fh:
            try:
                pt = json.loads(riga).get("pt")
            except ValueError:
                continue
            if pt is not None:
                return int(pt)
    return None


def catalogo_dal_raw(definizioni: Dict[str, Dict[str, Any]]) -> List[Any]:
    """Gli oggetti che `list_market_catalogue` restituirebbe (limite 1): gli
    attributi letti da `run_session` sono `market_id`, `runners[].selection_id`,
    `runners[].runner_name`."""
    from ...backtest.sim_strategy import _synth_name

    out = []
    for mid, d in sorted(definizioni.items()):
        runners = [SimpleNamespace(selection_id=sid,
                                   runner_name=_synth_name(d.get("market_type"), sp) or str(sid))
                   for sid, sp in d.get("runners") or []]
        out.append(SimpleNamespace(market_id=mid, market_type=d.get("market_type"),
                                   runners=runners, total_matched=0.0))
    return out


def righe_live_now(data_dir: str, event_id: str) -> List[Tuple[int, Dict[str, Any]]]:
    """28/09 - [(ts_ms, riga live_now)] dal sidecar `<id>.scores.jsonl`: le
    colonne `score_home`, `score_away`, `minute` sono quelle che il runner
    scrive IDENTICHE in `live_now` (`runner.py`, `upsert_live_now(minute=
    snap.minute, score_home=snap.score_home, score_away=snap.score_away)`) e
    nella stessa riga del sidecar. Nessun numero ricostruito."""
    p = os.path.join(data_dir, str(event_id), "%s.scores.jsonl" % event_id)
    out: List[Tuple[int, Dict[str, Any]]] = []
    if not os.path.exists(p):
        return out
    with io.open(p, "r", encoding="utf-8") as fh:
        for riga in fh:
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            ts = d.get("ts_ms")
            if ts is None:
                continue
            out.append((int(ts), {"score_home": d.get("score_home"),
                                  "score_away": d.get("score_away"),
                                  "minute": d.get("minute")}))
    out.sort(key=lambda x: x[0])
    return out


def _vita_da_control(control: Dict[str, Any]) -> int:
    from ..auto_mode import vita_sessione_s

    p = control.get("params") or {}
    vita = int(vita_sessione_s({"sniper_mode": bool(p.get("sniper_mode")),
                                "theta_mode": bool(p.get("theta_mode")),
                                "ht_mode": bool(p.get("ht_mode"))}))
    if p.get("media_mode") is True:
        # 05/10: la stessa regola di `run_session` per la modalita' media under
        from .. import media_under_bot as MU

        vita = max(vita, int(MU.vita_sessione_s(p)))
    return vita


_MODULI: Dict[str, Any] = {}


def _modulo(nome: str) -> Any:
    """29/09 (cantiere V): i moduli importati "tardi" (per non creare cicli
    d'importazione) una volta sola invece che a ogni book: l'istruzione
    `import` dentro una funzione chiamata 1,5 milioni di volte costa. Gli
    attributi si leggono sempre dal modulo vivo (una sostituzione nei test si
    vede lo stesso)."""
    m = _MODULI.get(nome)
    if m is None:
        if nome == "auto_mode":
            from .. import auto_mode as m
        elif nome == "scalper_session":
            from .. import scalper_session as m
        elif nome == "flumine.utils":
            from flumine import utils as m
        else:  # pragma: no cover - nome sbagliato = guasto del banco
            raise KeyError(nome)
        _MODULI[nome] = m
    return m


def SS_LINEA_OGNI_S() -> int:  # noqa: N802 - costante letta dal vero
    return int(_modulo("scalper_session").SNIPER_LINEA_OGNI_S)


class _ThreadingSessione:
    """Il modulo `threading` visto da `scalper_session` nel replay (28/09).

    Tutto passa al vero, TRANNE il thread `sniper-line`: in produzione dorme
    15 s col `time.sleep` della sessione, che nel banco e' il TURNO
    dell'orologio (un solo thread di controllo alla volta). Il thread non
    parte e la sua funzione (`scalper_session.applica_linea_sniper`) la chiama
    il ponte del motore alla stessa cadenza di mercato (15 s)."""

    def __init__(self, banco: "_Banco") -> None:
        self._banco = banco

    def Thread(self, *a: Any, **k: Any) -> Any:  # noqa: N802 - nome del vero
        if k.get("name") == "sniper-line":
            args = tuple(k.get("args") or ())
            if args:
                self._banco.sniper_linea = args[0]
            return SimpleNamespace(start=lambda: None, join=lambda *_a, **_k: None,
                                   is_alive=lambda: False, daemon=True)
        return threading.Thread(*a, **k)

    def __getattr__(self, nome: str) -> Any:
        return getattr(threading, nome)


def qualita_registrazione(data_dir: str, event_id: str) -> str:
    try:
        from ...tools.validate_recordings import validate_event

        rep = validate_event(data_dir, str(event_id))
        return "%s %s%%" % (rep.verdict, rep.coverage_pct)
    except Exception as ex:  # noqa: BLE001 - il verdetto e' un di piu'
        return "ignota (%s)" % type(ex).__name__


# ---------------------------------------------------------------------------
# L'OROLOGIO: il turno fra il thread della sessione e quello del motore
# ---------------------------------------------------------------------------
class _ProcessoUcciso(BaseException):
    """Il processo della sessione muore (scenario `riavvio`). BaseException:
    nessun `except Exception` della sessione lo intercetta, come nessun
    `except` sopravvive a un processo ucciso."""


class BancoBloccato(BaseException):
    """Il turno non passa piu': guasto del BANCO. BaseException perche' ne'
    `call_strategy_error_handling` di flumine ne' l'`except Exception` della
    sessione devono poterlo inghiottire: deve diventare un replay esploso."""


class _Orologio:
    """Il tempo e' quello di MERCATO; il turno passa fra chi dorme e chi avanza.

    * il thread di CONTROLLO (la sessione, o il replay che fa da supervisore)
      chiama `sleep(s)`: fissa la sveglia a `ora + s` e cede il turno;
    * il thread del MOTORE chiama `al_book(t)` a ogni book: se la sveglia e'
      raggiunta, cede il turno e aspetta che il controllo si riaddormenti.
    Nessuno dei due lavora mentre l'altro lavora: lo stato della strategia non
    si legge mai mentre flumine lo sta cambiando.
    """

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self.ora_s: Optional[float] = None
        self._sveglia: Optional[float] = None
        self._pendente: Optional[float] = None
        self._turno = "controllo"
        self.motore_finito = False
        self.libero = False            # nessun controllo: il motore corre
        self._uccidi: Optional[BaseException] = None
        # ogni istante di mercato (ms) in cui un book e' arrivato, nell'ORDINE
        # di arrivo: serve a S5 per scomputare i silenzi VERI della
        # registrazione (nessun book, qualunque market) dal ritardo del
        # heartbeat (`buchi`, sotto; difetto 24/09)
        self.libro_ms: List[int] = []

    # ------------------------------------------------------------ lettura
    def time(self) -> float:
        o = self.ora_s
        return float(o) if o is not None else _TIME_VERO()

    def buchi(self, soglia_ms: int = 2000) -> List[Tuple[int, int]]:
        """Coppie (inizio, fine) in cui NESSUN book (di nessun mercato della
        sessione) e' arrivato per almeno `soglia_ms`: il turno non poteva
        passare alla sessione piu' spesso di cosi', in un replay che avanza
        il tempo SOLO ai book (vedi il docstring del modulo, 'L'OROLOGIO')."""
        # 28/09: INCREMENTALE (stesso risultato). Prima si riscorreva TUTTO
        # `libro_ms` a ogni giro dei controlli (1 s di mercato): con la vita
        # della sessione sniper (KO+130', 60.000+ book) il banco diventava
        # quadratico e rallentava fino a fermarsi (misurato: 120 min reali).
        return list(self.vista_buchi(soglia_ms))

    def vista_buchi(self, soglia_ms: int = 2000) -> "CERT.VistaBuchi":
        """29/09 (cantiere V): gli STESSI buchi di `buchi()`, come vista del
        registro solo-in-aggiunta (`CERT.RegistroBuchi`) invece che come
        copia: niente copia di tutti i buchi a ogni giro e S5 aggiunge solo i
        nuovi (prefisso garantito per costruzione)."""
        cache = self.__dict__.setdefault("_buchi_cache", {})
        registro, prima, fatti = cache.get(soglia_ms, (None, None, 0))
        if registro is None:
            registro = CERT.RegistroBuchi()
        for ms in self.libro_ms[fatti:]:
            if prima is not None and ms - prima >= soglia_ms:
                registro.aggiungi(prima, ms)
            prima = ms
        cache[soglia_ms] = (registro, prima, len(self.libro_ms))
        return registro.vista()

    def ora_ms(self) -> int:
        return int(round(self.time() * 1000.0))

    # ------------------------------------------------------------ controllo
    def uccidi_al_prossimo_sonno(self, ex: BaseException) -> None:
        with self._cv:
            self._uccidi = ex

    def _forse_muori(self) -> None:
        if self._uccidi is not None:
            ex, self._uccidi = self._uccidi, None
            raise ex

    def sleep(self, secondi: float) -> None:
        secondi = max(0.0, float(secondi or 0.0))
        with self._cv:
            self._forse_muori()
            if self.motore_finito:
                if self.ora_s is not None:
                    self.ora_s += secondi
                return
            if self.ora_s is None:
                self._pendente = secondi
                self._sveglia = None
            else:
                self._sveglia = self.ora_s + secondi
            self._turno = "motore"
            self._cv.notify_all()
            limite = _MONOTONIC() + ATTESA_MASSIMA_REALE_S
            while self._turno == "motore" and not self.motore_finito:
                self._cv.wait(0.5)
                if _MONOTONIC() > limite:
                    raise BancoBloccato("il motore non restituisce il turno")
            if self._turno == "motore":
                # il motore e' finito mentre si dormiva: il tempo scorre lo stesso
                if self._sveglia is not None and self.ora_s is not None:
                    self.ora_s = max(self.ora_s, self._sveglia)
                self._turno = "controllo"
            self._forse_muori()

    def libera(self) -> None:
        """Nessuno controlla piu': il motore corre fino in fondo."""
        with self._cv:
            self.libero = True
            self._turno = "motore"
            self._cv.notify_all()

    # ------------------------------------------------------------ motore
    def al_book(self, t_s: float) -> None:
        with self._cv:
            self.libro_ms.append(int(round(t_s * 1000.0)))
            self.ora_s = t_s if self.ora_s is None else max(self.ora_s, t_s)
            if self._pendente is not None:
                self._sveglia = self.ora_s + self._pendente
                self._pendente = None
            limite = _MONOTONIC() + ATTESA_MASSIMA_REALE_S
            while self._turno == "controllo" and not self.libero:
                self._cv.wait(0.5)
                if _MONOTONIC() > limite:
                    raise BancoBloccato("la sessione non restituisce il turno")
            if (not self.libero and self._sveglia is not None
                    and self.ora_s >= self._sveglia):
                self._sveglia = None
                self._turno = "controllo"
                self._cv.notify_all()
                limite = _MONOTONIC() + ATTESA_MASSIMA_REALE_S
                while self._turno == "controllo" and not self.libero:
                    self._cv.wait(0.5)
                    if _MONOTONIC() > limite:
                        raise BancoBloccato("la sessione non restituisce il turno")

    def fine_motore(self) -> None:
        with self._cv:
            self.motore_finito = True
            self._cv.notify_all()


class _TempoSessione:
    """Il modulo `time` visto da `scalper_session` (usa solo sleep e time)."""

    def __init__(self, orologio: _Orologio) -> None:
        self._o = orologio

    def sleep(self, s: float) -> None:
        self._o.sleep(s)

    def time(self) -> float:
        return self._o.time()


# ---------------------------------------------------------------------------
# il DATABASE finto della sessione: colonne e CHECK della migrazione
# ---------------------------------------------------------------------------
class _Risposta:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Tabella:
    """Il builder di supabase-py che la sessione usa su `db.sb.table(...)`:
    insert/select/update + eq/in_ + execute."""

    def __init__(self, db: "_DbFinto", nome: str) -> None:
        self._db = db
        self._nome = nome
        self._op: Optional[str] = None
        self._riga: Any = None

    def insert(self, riga: Any) -> "_Tabella":
        self._op, self._riga = "insert", riga
        return self

    def select(self, *_a: Any, **_k: Any) -> "_Tabella":
        self._op = "select"
        return self

    def update(self, riga: Any) -> "_Tabella":
        self._op, self._riga = "update", riga
        return self

    def eq(self, *_a: Any, **_k: Any) -> "_Tabella":
        return self

    def in_(self, *_a: Any, **_k: Any) -> "_Tabella":
        return self

    def execute(self) -> _Risposta:
        if self._op == "select":
            # 05/10 (giro 2): le letture della sessione, per tabella (M10)
            self._db.letture[self._nome] = self._db.letture.get(self._nome, 0) + 1
        if self._op == "insert":
            righe = self._riga if isinstance(self._riga, list) else [self._riga]
            dest = self._db.tabelle.setdefault(self._nome, [])
            for r in righe:
                r = json.loads(json.dumps(r, default=str))
                r["_ms"] = self._db.orologio.ora_ms()
                dest.append(r)
            return _Risposta(righe)
        if self._nome == "live_now":
            # 28/09: la riga `live_now` dell'ISTANTE di mercato, ricostruita dal
            # sidecar (vuota se la registrazione non ha punteggi)
            riga = self._db.live_now()
            return _Risposta([riga] if riga else [])
        # `theta_confirm_requests`: nessuna riga
        return _Risposta([])


class _SbFinto:
    def __init__(self, db: "_DbFinto") -> None:
        self._db = db

    def table(self, nome: str) -> _Tabella:
        return _Tabella(self._db, nome)


class _DbFinto:
    """`scalper_session.Db` con le firme e i tipi del vero.

    `scalper_control` si comporta come la tabella della migrazione: una
    scrittura che viola un CHECK viene RIFIUTATA (come farebbe Postgres) e il
    vero `set_control` la inghiotte col suo warning; il controllo S1 la vede
    comunque, perche' ogni scrittura TENTATA e' registrata.
    """

    def __init__(self, orologio: _Orologio, control: Dict[str, Any],
                 follow: Dict[str, Any]) -> None:
        self.orologio = orologio
        self.control = dict(control)
        self.follow_row = dict(follow)
        self.scritture: List[Dict[str, Any]] = []
        self.tabelle: Dict[str, List[Dict[str, Any]]] = {}
        # 05/10 (giro 2): quante select per tabella ha fatto la sessione
        self.letture: Dict[str, int] = {}
        self.sb = _SbFinto(self)
        self.stati_visti: List[str] = []
        # 28/09: [(ts_ms, {score_home, score_away, minute})] dal sidecar
        self.punteggi_live_now: List[Tuple[int, Dict[str, Any]]] = []

    def live_now(self) -> Optional[Dict[str, Any]]:
        """La riga `live_now` (solo le colonne che la sessione legge) valida
        ADESSO sull'orologio di mercato: l'ultima del sidecar con `ts_ms` gia'
        raggiunto. Il `ts_ms` del sidecar e' l'istante in cui il runner l'ha
        RICEVUTA dall'IPS (ritardo gia' dentro, `banco_comune` docstring)."""
        ora = self.orologio.ora_ms()
        riga = None
        for ts, r in self.punteggi_live_now:
            if ts > ora:
                break
            riga = r
        return dict(riga) if riga is not None else None

    @staticmethod
    def _viola_check(campi: Dict[str, Any]) -> Optional[str]:
        st = campi.get("status")
        if st is not None and str(st) not in CERT.STATI_CONTROL_AMMESSI:
            return "status"
        mo = campi.get("mode")
        if mo is not None and str(mo) not in CERT.MODI_CONTROL_AMMESSI:
            return "mode"
        return None

    def set_control(self, event_id: str, **fields: Any) -> None:
        from .. import scalper_session as SS

        fields["updated_at"] = SS._now_iso()
        campi = json.loads(json.dumps(fields, default=str))
        rifiuto = self._viola_check(campi)
        self.scritture.append({"ms": self.orologio.ora_ms(), "campi": campi,
                               "rifiutata": rifiuto})
        if rifiuto:
            logger.warning("[replay-scalper] scrittura rifiutata dal CHECK (%s)", rifiuto)
            return
        self.control.update(campi)
        st = campi.get("status")
        if st and st not in self.stati_visti:
            self.stati_visti.append(str(st))

    def control_status(self, event_id: str) -> Optional[str]:
        return self.control.get("status")

    def control_stato_e_params(self, event_id: str) -> "Tuple[Optional[str], Optional[Dict[str, Any]]]":
        """25/09 - specchio di ``scalper_session.Db.control_stato_e_params``
        (stessa firma, stesse chiavi: select status,params della riga)."""
        riga = json.loads(json.dumps(self.control, default=str))
        params = riga.get("params")
        return riga.get("status"), (params if isinstance(params, dict) else None)

    def get_control(self, event_id: str) -> Optional[Dict[str, Any]]:
        return json.loads(json.dumps(self.control, default=str))

    def follow(self, event_id: str) -> Optional[Dict[str, Any]]:
        return dict(self.follow_row)

    def prediction(self, fixture_id: Optional[int]) -> Optional[Dict[str, Any]]:
        return None

    def log(self, event_id: str, kind: str, payload: Dict[str, Any]) -> None:
        self.tabelle.setdefault("scalper_activity", []).append({
            "event_id": event_id, "kind": kind,
            "payload": json.loads(json.dumps(payload, default=str)),
            "_ms": self.orologio.ora_ms()})

    def log_many(self, rows: List[Dict[str, Any]]) -> None:
        for r in rows or []:
            r = json.loads(json.dumps(r, default=str))
            r["_ms"] = self.orologio.ora_ms()
            self.tabelle.setdefault("scalper_activity", []).append(r)

    # --- letture per il referto
    def attivita(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        righe = self.tabelle.get("scalper_activity", [])
        return [r for r in righe if kind is None or r.get("kind") == kind]

    def messaggi(self) -> List[str]:
        return [str((r.get("payload") or {}).get("msg") or "")
                for r in self.attivita()]


# ---------------------------------------------------------------------------
# Betfair finto: SOLO il catalogo; ogni altra chiamata si registra
# ---------------------------------------------------------------------------
class _BettingFinto:
    def __init__(self, banco: "_Banco") -> None:
        self._banco = banco
        self.chiamate: List[Tuple[str, Dict[str, Any]]] = []

    def list_market_catalogue(self, filter: Any = None, market_projection: Any = None,
                              sort: Any = None, max_results: Any = None, **_k: Any) -> List[Any]:
        tipi = set((filter or {}).get("marketTypeCodes") or [])
        out = [m for m in self._banco.catalogo if not tipi or m.market_type in tipi]
        out = out[: int(max_results or len(out) or 1)]
        self.chiamate.append(("list_market_catalogue", {"tipi": sorted(tipi),
                                                        "n": len(out)}))
        self._banco.mercati_catalogo = [m.market_id for m in out]
        return out

    def list_market_book(self, market_ids: Any = None, **_k: Any) -> List[Any]:
        self.chiamate.append(("list_market_book", {"market_ids": market_ids}))
        return []

    def _vivi(self, market_id: str) -> List[Any]:
        m = self._banco.quadro.markets.markets.get(str(market_id))
        if m is None:
            return []
        return [o for o in list(m.blotter)
                if getattr(o, "bet_id", None) and CERT._vivo(CERT.riga_ordine(o))]

    def list_current_orders(self, market_ids: Any = None, **_k: Any) -> Any:
        """Gli ordini NON abbinati del conto su quei mercati, come li darebbe
        Betfair (`bet_id` e basta: e' l'unica chiave che `_sweep_cancel` legge).
        06/10 (giro 4): filtrata per ``customer_strategy_refs`` (la ripresa della
        media under) risponde come Betfair: ``CurrentOrders`` di
        betfairlightweight con TUTTI gli ordini (aperti e chiusi) delle
        strategie con quel ``customerStrategyRef``, a pagine."""
        refs = _k.get("customer_strategy_refs")
        if refs:
            return self._correnti_per_strategia([str(r)[:15] for r in refs],
                                                int(_k.get("from_record") or 0))
        self.chiamate.append(("list_current_orders", {"market_ids": market_ids}))
        righe = [SimpleNamespace(bet_id=str(o.bet_id))
                 for mid in (market_ids or []) for o in self._vivi(mid)]
        return SimpleNamespace(orders=righe, current_orders=righe)

    def _correnti_per_strategia(self, refs: List[str], da: int) -> Any:
        from betfairlightweight.resources.bettingresources import CurrentOrders

        self.chiamate.append(("list_current_orders", {"customer_strategy_refs": refs,
                                                      "from_record": da}))
        righe = []
        for m in list(self._banco.quadro.markets):
            for o in list(m.blotter):
                tr = getattr(o, "trade", None)
                if tr is None or str(getattr(tr, "strategy", ""))[:15] not in refs:
                    continue
                if not getattr(o, "bet_id", None):
                    continue
                righe.append(_ordine_corrente_del_banco(o, self._banco))
        return CurrentOrders(currentOrders=righe[da:], moreAvailable=False)

    def cancel_orders(self, market_id: Any = None, instructions: Any = None, **_k: Any) -> Any:
        """Lo SWEEP REST del crash (`scalper_session._sweep_cancel`): Betfair
        cancella il residuo non abbinato dei bet indicati. Nel simulato si usa
        lo stesso campo con cui il banco comune fa scadere un ordine
        (`SimulatedOrder`: qui `size_cancelled`), cosi' `size_remaining` va a
        zero; senza istruzioni e' market-wide, come su Betfair."""
        self.chiamate.append(("cancel_orders", {"market_id": market_id,
                                                "instructions": instructions}))
        voluti = None
        if instructions:
            voluti = {str(i.get("betId")) for i in instructions if isinstance(i, dict)}
        for o in self._vivi(str(market_id)):
            if voluti is not None and str(o.bet_id) not in voluti:
                continue
            sim = getattr(o, "simulated", None)
            if sim is not None:
                sim.size_cancelled += float(getattr(o, "size_remaining", 0.0) or 0.0)
        return None


def _adotta_ordini_vivi(quadro: Any, morte: List[Any], nuova: Any) -> int:
    """L'adozione di flumine al riavvio (``create_order_from_current``): gli
    ordini VIVI delle strategie morte con lo STESSO nome passano nel blotter
    della strategia nuova (gli indici del blotter e ``trade.strategy``)."""
    n = 0
    nome = str(nuova)
    for vecchia in morte:
        if vecchia is nuova or str(vecchia) != nome:
            continue
        for m in list(quadro.markets):
            bl = m.blotter
            for o in list(bl.strategy_orders(vecchia)):
                if not CERT._vivo(CERT.riga_ordine(o)):
                    continue
                o.trade.strategy = nuova
                bl._strategy_orders[vecchia].remove(o)
                bl._strategy_orders[nuova].append(o)
                chiave = (vecchia, o.selection_id, o.handicap)
                if o in bl._strategy_selection_orders.get(chiave, []):
                    bl._strategy_selection_orders[chiave].remove(o)
                bl._strategy_selection_orders[(nuova, o.selection_id, o.handicap)].append(o)
                n += 1
    return n


def _ordine_corrente_del_banco(o: Any, banco: "_Banco") -> Dict[str, Any]:
    """Un ordine simulato del banco come riga di ``listCurrentOrders`` (chiavi
    della API Betfair che betfairlightweight legge)."""
    from datetime import datetime, timezone

    vivo = CERT._vivo(CERT.riga_ordine(o))
    nato = banco.media_nati_ms.get(str(getattr(o, "id", "")))
    placed = datetime.fromtimestamp((nato or banco.orologio.ora_ms()) / 1000.0, tz=timezone.utc)
    return {
        "betId": str(o.bet_id), "marketId": str(o.market_id),
        "selectionId": int(o.selection_id), "handicap": 0.0,
        "priceSize": {"price": float(o.order_type.price), "size": float(o.order_type.size)},
        "bspLiability": 0.0, "side": str(o.side), "orderType": "LIMIT",
        "status": "EXECUTABLE" if vivo else "EXECUTION_COMPLETE",
        "persistenceType": str(o.order_type.persistence_type),
        "placedDate": placed.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "averagePriceMatched": float(getattr(o, "average_price_matched", 0.0) or 0.0),
        "sizeMatched": float(getattr(o, "size_matched", 0.0) or 0.0),
        "sizeRemaining": float(getattr(o, "size_remaining", 0.0) or 0.0) if vivo else 0.0,
        "sizeLapsed": 0.0,
        "sizeCancelled": float(getattr(o, "size_cancelled", 0.0) or 0.0),
        "sizeVoided": 0.0, "regulatorCode": "MR_INT",
        "customerOrderRef": str(getattr(o, "customer_order_ref", "") or ""),
        "customerStrategyRef": str(o.trade.strategy)[:15],
    }


class _TradingFinto:
    def __init__(self, banco: "_Banco") -> None:
        self.betting = _BettingFinto(banco)

    def keep_alive(self) -> None:
        return None


class _ClientChiesto:
    """Cio' che la sessione chiede a `clients.BetfairClient(trading, **kw)`: si
    registra (parita' paper/live, S6) e NON diventa mai un client vero."""

    def __init__(self, trading: Any, **kwargs: Any) -> None:
        self.trading = trading
        self.kwargs = dict(kwargs)


# ---------------------------------------------------------------------------
# il FRAMEWORK della sessione: un involucro sul quadro del banco
# ---------------------------------------------------------------------------
class _CodaTerminazione:
    """`framework.handler_queue` visto dalla sessione: la sola cosa che la
    sessione ci mette e' il `TerminationEvent` che ferma flumine."""

    def __init__(self, fw: "_FrameworkSessione") -> None:
        self._fw = fw

    def put(self, evento: Any) -> None:
        self._fw.termina(type(evento).__name__)


class _FrameworkSessione:
    def __init__(self, banco: "_Banco", client: Any) -> None:
        self.__dict__["_banco"] = banco
        self.__dict__["client_chiesto"] = getattr(client, "kwargs", {})
        self.__dict__["handler_queue"] = _CodaTerminazione(self)
        self.__dict__["_running"] = False
        self.__dict__["strategie"] = []
        self.__dict__["_fine"] = threading.Event()
        self.__dict__["causa_fine"] = None
        self.__dict__["_simulated_execution"] = None

    # il quadro del banco E' il mercato: markets, clients, log_control...
    def __getattr__(self, nome: str) -> Any:
        return getattr(self.__dict__["_banco"].quadro, nome)

    @property
    def simulated_execution(self) -> Any:
        return (self.__dict__["_simulated_execution"]
                or self.__dict__["_banco"].quadro.simulated_execution)

    @simulated_execution.setter
    def simulated_execution(self, v: Any) -> None:
        self.__dict__["_simulated_execution"] = v

    def __setattr__(self, nome: str, valore: Any) -> None:
        if nome == "simulated_execution":
            self.__dict__["_simulated_execution"] = valore
            return
        self.__dict__[nome] = valore

    def add_strategy(self, strategia: Any) -> None:
        self.__dict__["_banco"].aggiungi_strategia(self, strategia)

    def run(self) -> None:
        banco = self.__dict__["_banco"]
        self.__dict__["_running"] = True
        banco.avvia_motore()
        while not self.__dict__["_fine"].is_set() and not banco.motore_finito.is_set():
            self.__dict__["_fine"].wait(0.2)

    def termina(self, causa: str) -> None:
        self.__dict__["_running"] = False
        self.__dict__["causa_fine"] = causa
        self.__dict__["_fine"].set()
        self.__dict__["_banco"].sessione_finita(self)


class _ArmamentoCatturato(BaseException):
    """Ferma `run_session` appena la strategia e' armata (solo per la parita')."""

    def __init__(self, strategia: Any, client: Dict[str, Any]) -> None:
        super().__init__("armamento catturato")
        self.strategia = strategia
        self.client = client


# ---------------------------------------------------------------------------
# IL GUASTI iniettati (scenari)
# ---------------------------------------------------------------------------
def _controllo_rifiuti(quadro: Any, quanti: int):
    """Un trading control di flumine che RIFIUTA i primi `quanti` piazzamenti.
    Via di produzione del rifiuto: `_on_error` -> `order.violation(...)`,
    `place_order` torna False (`flumine/execution/transaction.py:67-72`)."""
    from flumine.controls import BaseControl
    from flumine.order.orderpackage import OrderPackageType

    class _Rifiuta(BaseControl):
        NAME = "REPLAY_RIFIUTA_PRIMI"

        def __init__(self, flumine: Any) -> None:
            super().__init__(flumine)
            self.rifiutati: List[str] = []
            # gli OGGETTI rifiutati: dal 24/09 il bot li lascia cadere (legge il
            # False di place_order) e il blotter non li ha mai avuti; K2 li
            # deve vedere lo stesso per giudicare se il bot ci crede ancora
            self.ordini: List[Any] = []

        def _validate(self, order: Any, package_type: Any) -> None:
            if package_type != OrderPackageType.PLACE or len(self.rifiutati) >= quanti:
                return
            self.rifiutati.append(str(getattr(order, "id", "") or ""))
            self.ordini.append(order)
            self._on_error(order, "rifiuto iniettato dal replay")

    return _Rifiuta(quadro)


def _ritarda_esiti(quadro: Any, quanti: int, secondi: float) -> Dict[str, Any]:
    """I primi `quanti` pacchetti PLACE restano senza esito per `secondi` di
    mercato: flumine li esegue solo quando il tempo supera il loro
    `simulated_delay`, cosi' l'ordine resta PENDING e senza bet_id."""
    from flumine.order.orderpackage import OrderPackageType

    stato = {"ritardati": 0}
    originale = quadro.process_order_package

    def _process(pacco: Any) -> None:
        if (getattr(pacco, "package_type", None) == OrderPackageType.PLACE
                and stato["ritardati"] < quanti):
            pacco.simulated_delay = float(pacco.simulated_delay) + float(secondi)
            stato["ritardati"] += 1
        return originale(pacco)

    quadro.process_order_package = _process
    return stato


# ---------------------------------------------------------------------------
# GLI OSSERVATORI: guardano, non decidono
# ---------------------------------------------------------------------------
def installa_osservatori(s: Any, attivita: List[Tuple[str, Dict[str, Any], int]],
                         chiusure: List[Dict[str, Any]],
                         ora_ms: Callable[[], int]) -> None:
    """Due osservatori in SOLA LETTURA sulla strategia di produzione.

    * TEE dell'`event_sink` (e' il punto d'iniezione della telemetria che il
      bot stesso dichiara: 'callable(kind, payload), mai dalla logica'): ogni
      attivita' arriva ANCHE al referto, il sink vero resta collegato;
    * alla chiusura di ogni ciclo (`_on_cycle_closed`, l'unico punto in cui il
      bot contabilizza un `locked`) si fotografano gli ordini dello slot e si
      calcola QUI il worst-case vero dagli abbinati (K7). Poi si chiama il vero.
    """
    vero = getattr(s, "event_sink", None)

    def _tee(kind: str, payload: Dict[str, Any]) -> None:
        attivita.append((str(kind), dict(payload or {}), ora_ms()))
        if vero is not None:
            vero(kind, payload)

    s.event_sink = _tee
    chiudi_vero = s._on_cycle_closed

    def _osserva(slot: Any, locked: float, kind: str = "cycle",
                 now: Optional[int] = None) -> None:
        ordini = [slot.entry, slot.entry_back, slot.entry_lay, slot.close,
                  slot.next_entry] + list(slot.flatten_orders or [])
        chiave = next((k for k, v in s._slots.items() if v is slot), None)
        chiusure.append({
            "chiave": chiave, "kind": kind, "locked": float(locked),
            "worst_case_vero": CERT.worst_case_vero(ordini), "ms": ora_ms()})
        return chiudi_vero(slot, locked, kind=kind, now=now)

    s._on_cycle_closed = _osserva


# ---------------------------------------------------------------------------
# IL BANCO: quadro, motore, ponte, sessioni
# ---------------------------------------------------------------------------
class _Banco:
    def __init__(self, *, event_id: str, raw: str, scenario: str, ogni_ms: int,
                 referto: CERT.Referto, orologio: _Orologio, db: _DbFinto,
                 catalogo: List[Any], ko_ms: Optional[int]) -> None:
        from ...backtest import banco_comune as BC
        from flumine import FlumineSimulation

        self.BC = BC
        self.event_id = str(event_id)
        self.raw = raw
        self.scenario = scenario
        self.cadenza_ms = int(ogni_ms) if ogni_ms else 1000
        self.ref = referto
        self.orologio = orologio
        self.db = db
        self.catalogo = catalogo
        self.ko_ms = ko_ms
        self.mercati_catalogo: List[str] = []
        self.quadro = FlumineSimulation(client=BC.cliente_simulato())
        BC.assicura_middleware_simulato(self.quadro)
        self.motore = BC.MotoreReplay(self.quadro)
        self.motore_finito = threading.Event()
        self._thread_motore: Optional[threading.Thread] = None
        self.errore_motore: Optional[BaseException] = None
        self.ferma = False
        # sessioni: (framework, strategia, mercati)
        self.sessioni: List[Tuple[_FrameworkSessione, Any, Tuple[str, ...]]] = []
        self.sessioni_morte: List[Tuple[_FrameworkSessione, Any]] = []
        self._stream_ids: set = set()
        self.specchi: List[Any] = []
        self.righe_specchio: List[Dict[str, Any]] = []
        self._specchio_da = 0
        self.attivita: List[Tuple[str, Dict[str, Any], int]] = []
        self._attivita_da = 0
        self.chiusure: List[Dict[str, Any]] = []
        self._chiusure_da = 0
        self._scritture_da = 0
        self._ultimo_giro_ms = 0
        self._ultimo_specchio_ms = 0
        self.ordini_visti: set = set()
        self.ingressi_ms: Dict[str, int] = {}
        self.force_flat_ms: Optional[int] = None
        self.missione_ms: Optional[int] = None
        self.in_gioco_ms: Dict[str, int] = {}
        self.stati_visti: List[str] = []
        self.fasi_viste: List[str] = []
        self.memoria = CERT.Memoria()
        # scenario: quando e perche' lo stop
        self.stop_ms: Optional[int] = None
        self.stop_causa = ""
        self.evento_ms: Optional[int] = None
        self.evento_fatto = False
        self.kill_file: Optional[str] = None
        self.sorveglianza_cp: Optional[Any] = None
        # 04/10: ultima riga di specchio per ordine (bet_id), per CP1
        self.specchio_per_ordine: Dict[str, Dict[str, Any]] = {}
        self.parita: Optional[Dict[str, Any]] = None
        self._parita_consegnata = False
        self.riavviata = False
        self.orfani_attivi = False
        self.primo_ms: Optional[int] = None
        self.errori_ponte: List[str] = []
        self.ultima_strategia: Any = None
        self.framework_creati: List[_FrameworkSessione] = []
        # il trading control dello scenario 'rifiuti-betfair' (None altrove)
        self.rifiuti: Any = None
        # 28/09 - lo SNIPER della sessione (strategia COMPAGNA del maker, nello
        # stesso framework): riceve i book dei mercati della sessione, i suoi
        # controlli sono i suoi (`controlli_sniper`), quelli del maker restano
        # sul maker. (fw, sniper, mercati)
        self.compagne: List[Tuple[Any, Any, Tuple[str, ...]]] = []
        self.attivita_sniper: List[Tuple[str, Dict[str, Any], int]] = []
        self.chiusure_sniper: List[Dict[str, Any]] = []
        self.sniper_linea: Any = None
        self._linea_ms: Optional[int] = None
        self.sniper_ultimo: Any = None
        self.sniper_ordini_visti: set = set()
        # N3 (28/09): l'osservatore delle uscite manuali (None fuori da
        # `uscite-manuali*`)
        self.osservatore_um: Optional[Any] = None
        # 05/10 MEDIA UNDER: la strategia della modalita' (None fuori dagli
        # scenari `media-under*`), le sue attivita' e la memoria dei controlli M
        self.media: Any = None
        # 05/10 (giro 2): TUTTE le strategie della modalita' armate (dopo un
        # riavvio la prima resta qui: i suoi ordini sono ancora a mercato)
        self.medie: List[Any] = []
        # 06/10 (giro 4): quanti ordini vivi sono passati alla sessione nuova
        self.media_adottati: int = 0
        self.attivita_media: List[Tuple[str, Dict[str, Any], int]] = []
        self.memoria_media = CERT.Memoria()
        self.media_ordini_visti: set = set()
        # 05/10 (giro 2): istante di MERCATO in cui ogni ordine della modalita' e'
        # nato e in cui il suo abbinato e' cresciuto l'ultima volta (riepilogo
        # per ciclo del referto)
        self.media_nati_ms: Dict[str, int] = {}
        self.media_abbinato_ms: Dict[str, int] = {}
        self.media_abbinato_visto: Dict[str, float] = {}
        self.media_annullati_al_gioco: Dict[str, float] = {}
        self.media_mercato_scelto: Optional[str] = None
        self.media_under: Optional[int] = None
        self.tipo_mercato: Dict[str, str] = {}

    # ------------------------------------------------------------ sessioni
    def strategia_corrente(self) -> Any:
        """La strategia della sessione viva; a sessione chiusa, l'ULTIMA armata
        (serve al giro finale S3/S4, che giudica cio' che ha lasciato)."""
        if self.sessioni:
            return self.sessioni[-1][1]
        return getattr(self, "ultima_strategia", None)

    def aggiungi_strategia(self, fw: _FrameworkSessione, s: Any) -> None:
        # la registrazione al posto dello stream (come il replay tennis)
        s.market_filter = {"markets": [self.raw]}
        from ..media_under_bot import MediaUnderStrategy
        from ..sniper_bot import SniperStrategy

        if isinstance(s, MediaUnderStrategy):
            # 05/10 MEDIA UNDER: l'UNICA strategia della sessione (maker e
            # sniper non armati): e' la strategia della sessione per il ciclo di
            # vita (fine vita, specchio, controlli di servizio), con il TEE
            # dell'event_sink in sola lettura; i controlli di slot del maker non
            # la riguardano (ha i suoi, famiglia M)
            vero = getattr(s, "event_sink", None)
            att, ora = self.attivita_media, self.orologio.ora_ms

            def _tee_media(kind: str, payload: Dict[str, Any], _v: Any = vero) -> None:
                att.append((str(kind), dict(payload or {}), ora()))
                if _v is not None:
                    _v(kind, payload)
            s.event_sink = _tee_media
            # 06/10 (giro 4, P13): in SOLDI VERI flumine riadotta nel blotter della
            # strategia nuova (stesso nome = stesso ``name_hash``) gli ordini VIVI
            # del processo morto, che restano sul mercato: qui passano di mano gli
            # ordini simulati vivi delle sessioni della modalita' gia' morte (lo
            # stesso effetto di ``create_order_from_current``). In prova no: gli
            # ordini simulati muoiono col processo (e la modalita' resta bloccata).
            if not bool(self.db.control.get("dry_run", True)):
                self.media_adottati += _adotta_ordini_vivi(self.quadro, self.medie, s)
            self.quadro.add_strategy(s)
            self._stream_ids |= set(getattr(s, "stream_ids", set()) or set())
            fw.strategie.append(s)
            self.sessioni.append((fw, s, tuple(self.mercati_catalogo)))
            self.ultima_strategia = s
            self.media = s
            self.medie.append(s)
            return

        if isinstance(s, SniperStrategy):
            # 28/09: lo sniper e' COMPAGNO del maker (stesso framework, stessi
            # mercati del catalogo): non diventa la "strategia corrente" dei
            # controlli del maker, ha i suoi
            vero = getattr(s, "event_sink", None)
            att, ora = self.attivita_sniper, self.orologio.ora_ms

            def _tee(kind: str, payload: Dict[str, Any], _v: Any = vero,
                     _s: Any = s) -> None:
                # SOLO il tee dell'event_sink (sola lettura): lo sniper non ha
                # gli slot del maker (`_on_cycle_closed` e' del maker)
                copia = dict(payload or {})
                if kind == "sniper_green":
                    # N3 (Z3 per IDENTITA'): la posizione del green, letta
                    # nell'istante dell'emissione (entrate e chiusura ancora
                    # al loro posto) con la funzione di produzione
                    # `_prefisso_uscite`. Solo nella copia del banco.
                    copia[CHIAVE_PREFISSI_GREEN] = prefissi_del_green(_s)
                att.append((str(kind), copia, ora()))
                if _v is not None:
                    _v(kind, payload)
            s.event_sink = _tee
            self.quadro.add_strategy(s)
            self._stream_ids |= set(getattr(s, "stream_ids", set()) or set())
            fw.strategie.append(s)
            self.compagne.append((fw, s, tuple(self.mercati_catalogo)))
            self.sniper_ultimo = s
            return
        installa_osservatori(s, self.attivita, self.chiusure, self.orologio.ora_ms)
        self.quadro.add_strategy(s)
        self._stream_ids |= set(getattr(s, "stream_ids", set()) or set())
        fw.strategie.append(s)
        self.sessioni.append((fw, s, tuple(self.mercati_catalogo)))
        self.ultima_strategia = s

    def sessione_finita(self, fw: _FrameworkSessione) -> None:
        self.sessioni = [x for x in self.sessioni if x[0] is not fw]
        self.compagne = [x for x in self.compagne if x[0] is not fw]

    def uccidi_sessione(self, fw: _FrameworkSessione) -> None:
        """Il processo e' morto: flumine non chiama piu' la strategia. Gli
        ordini restano sul mercato (in LIVE restano sull'exchange)."""
        for x in list(self.sessioni):
            if x[0] is fw:
                self.sessioni_morte.append((fw, x[1]))
        self.sessioni = [x for x in self.sessioni if x[0] is not fw]
        self.compagne = [x for x in self.compagne if x[0] is not fw]
        fw.__dict__["_running"] = False
        fw.__dict__["causa_fine"] = "processo ucciso"
        fw.__dict__["_fine"].set()

    def registra_specchio(self, mirror: Any) -> None:
        self.specchi.append(mirror)

    # ------------------------------------------------------------ motore
    def avvia_motore(self) -> None:
        if self._thread_motore is not None:
            return
        self._thread_motore = threading.Thread(target=self._gira, daemon=True,
                                               name="replay-scalper-motore")
        self._thread_motore.start()

    def _gira(self) -> None:
        try:
            self.motore.esegui(_Ponte(self))
        except BaseException as ex:  # noqa: BLE001 - un motore che muore E' un referto
            self.errore_motore = ex
        finally:
            self.orologio.fine_motore()
            self.motore_finito.set()

    def ferma_motore(self) -> None:
        self.ferma = True
        self.orologio.libera()
        if self._thread_motore is not None:
            self._thread_motore.join(timeout=ATTESA_MASSIMA_REALE_S)

    # ------------------------------------------------------------ ordini
    def _mercati_sessione(self) -> Tuple[str, ...]:
        if self.sessioni:
            return self.sessioni[-1][2]
        return tuple(self.mercati_catalogo)

    def ordini_di(self, strategie: List[Any]) -> List[Any]:
        out: List[Any] = []
        for mid in self._mercati_sessione():
            m = self.quadro.markets.markets.get(mid)
            if m is None:
                continue
            for s in strategie:
                try:
                    out.extend(list(m.blotter.strategy_orders(s) or []))
                except Exception:  # noqa: BLE001 - blotter illeggibile: nessun ordine
                    continue
        return out

    def righe_correnti(self, s: Any, cred: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        a_mercato = self.ordini_di([s]) if s is not None else []
        # 06/10 (giro 4, P13): gli ordini chiusi prima di un riavvio che la
        # modalita' "media under" ha letto dal conto (la verita' del conto, fuori
        # dal blotter del processo nuovo): come in produzione entrano nelle righe
        bet_ids = {str(getattr(o, "bet_id", "")) for o in a_mercato if getattr(o, "bet_id", None)}
        extra = getattr(s, "ordini_dal_conto", None) if s is not None else None
        if callable(extra):
            a_mercato = a_mercato + [o for o in extra() if str(o.bet_id) not in bet_ids]
        ids = {str(getattr(o, "id", "")) for o in a_mercato}
        righe = [CERT.riga_ordine(o, True) for o in a_mercato]
        # gli ordini che il bot tiene in mano e che il mercato NON conosce
        # (rifiutati, mai partiti): e' la parte di verita' che il blotter non ha
        for c in cred:
            for o in CERT.ordini_seguiti(c):
                oid = str(getattr(o, "id", ""))
                if oid and oid not in ids:
                    ids.add(oid)
                    righe.append(CERT.riga_ordine(o, False))
        # i rifiuti iniettati dallo scenario, anche quelli che il bot NON segue
        # piu' (e' la verita' del mercato: K2 li giudica contro le credenze)
        for o in list(getattr(self.rifiuti, "ordini", None) or []):
            oid = str(getattr(o, "id", ""))
            if oid and oid not in ids:
                ids.add(oid)
                righe.append(CERT.riga_ordine(o, False))
        return righe

    @staticmethod
    def esposizioni(righe: List[Dict[str, Any]]) -> Dict[Tuple[str, int], Tuple[float, float]]:
        per: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
        for r in righe:
            if not r.get("in_blotter"):
                continue
            try:
                k = (str(r.get("market_id") or ""), int(r.get("selection_id") or 0))
            except (TypeError, ValueError):
                continue
            per.setdefault(k, []).append(r)
        return {k: CERT.esposizione(v) for k, v in per.items()}

    # ------------------------------------------------------------ specchio
    def gira_specchio(self, ms: int) -> None:
        if not self.specchi or ms - self._ultimo_specchio_ms < 1000:
            return
        self._ultimo_specchio_ms = ms
        mirror = self.specchi[-1]
        for mid in self._mercati_sessione():
            m = self.quadro.markets.markets.get(mid)
            if m is None:
                continue
            ordini = list(m.blotter)
            if ordini:
                mirror.process_orders(m, ordini)

    # ------------------------------------------------------------ il giro
    def divieti(self, ms: int) -> Dict[str, int]:
        d: Dict[str, int] = {}
        s = self.strategia_corrente()
        if self.force_flat_ms is not None:
            d["force_flat"] = self.force_flat_ms
        if self.missione_ms is not None:
            d["missione_prematch"] = self.missione_ms
        if s is not None and self.ko_ms is not None:
            esb = float(getattr(s, "entry_stop_before_s", 0.0) or 0.0)
            if esb > 0 and ms >= self.ko_ms - int(esb * 1000):
                d["entry_stop_before_s"] = self.ko_ms - int(esb * 1000)
        if s is not None and not getattr(s, "allow_inplay", False):
            for mid, t in self.in_gioco_ms.items():
                d["in_gioco@%s" % mid] = t
        return d

    def running_e_battiti_lento(self) -> Tuple[Optional[int], List[int]]:
        """Il riferimento (il codice di prima del cantiere V): riscorre TUTTE le
        scritture a ogni giro. Resta per il test di equivalenza."""
        running = None
        for w in self.db.scritture:
            if (w.get("campi") or {}).get("status") == "running":
                running = w["ms"]
        battiti = [w["ms"] for w in self.db.scritture
                   if "heartbeat_at" in (w.get("campi") or {})
                   and running is not None and w["ms"] >= running
                   and (self.stop_ms is None or w["ms"] <= self.stop_ms)]
        return running, battiti

    def running_e_battiti(self) -> Tuple[Optional[int], List[int]]:
        """29/09 (cantiere V) - lo STESSO risultato di `running_e_battiti_lento`
        senza riscorrere tutte le scritture a ogni giro (costo che cresceva con
        la vita della sessione). `db.scritture` e' solo in aggiunta
        (`_DbFinto.set_control`): si leggono solo le scritture nuove; il filtro
        (running, stop) si rifa' da capo solo quando running o stop cambiano."""
        scritture = self.db.scritture
        st = self.__dict__.get("_rb")
        if st is None or st["lista"] is not scritture or len(scritture) < st["da"]:
            # prima volta, o un elenco di scritture diverso: si riparte da zero
            st = self.__dict__["_rb"] = {"lista": scritture, "da": 0, "running": None,
                                         "hb": [], "chiave": None, "fatti": 0, "out": []}
        for w in scritture[st["da"]:]:
            campi = w.get("campi") or {}
            if campi.get("status") == "running":
                st["running"] = w["ms"]
            if "heartbeat_at" in campi:
                st["hb"].append(w["ms"])
        st["da"] = len(scritture)
        running, stop = st["running"], self.stop_ms
        if running is None:
            return None, []
        if st["chiave"] != (running, stop):
            st["chiave"], st["fatti"], st["out"] = (running, stop), 0, []
        hb, out = st["hb"], st["out"]
        for ms in hb[st["fatti"]:]:
            if ms >= running and (stop is None or ms <= stop):
                out.append(ms)
        st["fatti"] = len(hb)
        return running, list(out)

    def osservazione(self, ms: int, quando: str, *, fine: bool = False,
                     stato_mercato: str = "OPEN") -> CERT.Osservazione:
        s = self.strategia_corrente()
        cred = CERT.credenze(s) if s is not None else []
        righe = self.righe_correnti(s, cred)
        tutti = {r.get("order_id") for r in righe}
        nuovi = tutti - self.ordini_visti
        self.ordini_visti |= tutti
        ids_ingresso: set = set()
        for c in cred:
            ids_ingresso |= CERT._ids(c.get("ingressi") or ())
        for r in righe:
            oid = r.get("order_id")
            if oid in ids_ingresso and oid not in self.ingressi_ms:
                self.ingressi_ms[oid] = int(r.get("creato_ms") or ms)
        ora_fa = ms - 3600 * 1000
        # il ritmo delle transazioni conta i PIAZZAMENTI d'ingresso fatti
        ingressi_ora = sum(1 for t in self.ingressi_ms.values() if t >= ora_fa)
        att = [(k, p) for k, p, _t in self.attivita[self._attivita_da:]]
        self._attivita_da = len(self.attivita)
        chiusure = self.chiusure[self._chiusure_da:]
        self._chiusure_da = len(self.chiusure)
        scritture = self.db.scritture[self._scritture_da:]
        self._scritture_da = len(self.db.scritture)
        specchio = self.righe_specchio[self._specchio_da:]
        self._specchio_da = len(self.righe_specchio)
        # il giro NORMALE della sessione CORRENTE: dall'ultimo 'running' allo
        # stop (dopo lo stop il servizio aspetta il flat senza battere)
        running, battiti = self.running_e_battiti()
        orfani = None
        if self.orfani_attivi and self.sessioni_morte:
            morti = self.ordini_di([x[1] for x in self.sessioni_morte])
            orfani = [CERT.riga_ordine(o) for o in morti
                      if float(getattr(o, "size_matched", 0.0) or 0.0) > 0.009
                      or CERT._vivo(CERT.riga_ordine(o))]
        parita = None
        if self.parita is not None and not self._parita_consegnata:
            parita = self.parita
            self._parita_consegnata = True
        oss = CERT.Osservazione(
            scenario=self.scenario, quando=quando, ms=ms,
            modalita="paper" if bool(self.db.control.get("dry_run")) else "live",
            inplay=bool(self.in_gioco_ms), stato_mercato=stato_mercato,
            ko_ms=self.ko_ms,
            stake=float(self.db.control.get("stake") or 0.0),
            cap_esposizione=getattr(s, "max_selection_exposure", None) if s is not None else None,
            divieti=self.divieti(ms), ordini=righe, credenze=cred,
            ordini_nuovi=nuovi, attivita=att,
            stats=dict((self.db.control.get("stats") or {})),
            specchio=specchio, esposizioni=self.esposizioni(righe),
            max_txn_hour=int(getattr(s, "max_txn_hour", 0) or 0) if s is not None else 0,
            ingressi_ultima_ora=ingressi_ora, chiusure_ciclo=chiusure,
            scritture_control=scritture,
            stop_richiesto_ms=self.stop_ms, stop_causa=self.stop_causa,
            force_flat=bool(getattr(s, "force_flat", False)) if s is not None else False,
            force_flat_ms=self.force_flat_ms,
            sessione_viva=bool(self.sessioni) and not fine,
            stato_finale=self.db.control.get("status") if fine else None,
            fine_sessione=fine,
            # il servizio DICHIARA una posizione non piatta in due modi: il log
            # 'posizione NON flat dopo 30s' e l'allarme CRITICAL del crash
            # ('VERIFICA il matched residuo sul conto')
            dichiarato_non_flat=fine and (
                any(CERT.messaggio_dichiara_non_flat(m)
                    for m in self.db.messaggi())
                or any(str(a.get("code") or "") == "SCALPER_CRASH"
                       for a in self.db.tabelle.get("live_alerts", []))),
            heartbeat_ms=battiti, running_da_ms=running,
            buchi_registrazione_ms=self.orologio.vista_buchi(),
            parita=parita, orfani_dopo_riavvio=orfani,
            allarmi=list(self.db.tabelle.get("live_alerts", [])),
        )
        # stati e fasi visti (referto par.6.8)
        for c in cred:
            st = "slot:%s" % c.get("stato")
            if st not in self.stati_visti:
                self.stati_visti.append(st)
        for st in self.db.stati_visti:
            k = "sessione:%s" % st
            if k not in self.stati_visti:
                self.stati_visti.append(k)
        fase = ("fine-sessione" if fine else "in-gioco" if self.in_gioco_ms
                else "finestra-flatten" if (s is not None and self.ko_ms is not None
                                            and ms >= self.ko_ms - int(float(getattr(s, "flatten_before_s", 0) or 0) * 1000))
                else "stop-ingressi" if "entry_stop_before_s" in oss.divieti
                else "pre-match")
        if fase not in self.fasi_viste:
            self.fasi_viste.append(fase)
        return oss

    def vita_ms(self) -> int:
        """La vita della sessione (ms dal KO) con i parametri del control: la
        funzione di produzione (`auto_mode.vita_sessione_s`)."""
        # 29/09 (cantiere V): chiamata a OGNI book. Il risultato dipende solo
        # dai tre interruttori e dalla funzione di produzione con le sue
        # costanti: si ricalcola solo quando uno di questi cambia (stesso numero)
        _AM = _modulo("auto_mode")
        p = self.db.control.get("params") or {}
        chiave = (bool(p.get("sniper_mode")), bool(p.get("theta_mode")),
                  bool(p.get("ht_mode")), _AM.vita_sessione_s, _AM.sniper_mode_acceso,
                  _AM.VITA_SNIPER_THETA_S, _AM.VITA_HT_S, _AM.VITA_MAKER_S,
                  p.get("media_mode") is True)
        cache = self.__dict__.get("_vita_cache")
        if cache is not None and cache[0] == chiave:
            return cache[1]
        valore = int(1000 * float(_AM.vita_sessione_s({
            "sniper_mode": chiave[0], "theta_mode": chiave[1], "ht_mode": chiave[2]})))
        if chiave[-1]:
            # 05/10 MEDIA UNDER: la regola di `run_session` (fino a fine partita)
            from .. import media_under_bot as MU

            valore = max(valore, int(1000 * float(MU.vita_sessione_s(p))))
        self.__dict__["_vita_cache"] = (chiave, valore)
        return valore

    def controlli_sniper(self, ms: int, quando: str, fine: bool) -> None:
        """28/09 - i controlli di condotta dello SNIPER (i controlli del maker
        in `certificazione.py` leggono gli slot del maker, non si applicano).

        Z1 ogni ordine NUOVO dello sniper e' legale su .it (prezzo nella ladder,
           size multipla di 0,50 e non sotto il minimo del lato), tranne i
           SOSTITUTI del place-and-trim (stessa regola di B3 del maker);
        Z2 a fine sessione lo sniper e' piatto per la SUA misura (`is_flat`:
           |se vince - se perde| entro 0,02 o entro il residuo che ha accettato
           e dichiarato), oppure la sessione lo ha DICHIARATO non piatto;
        Z3 a uscite MANUALI (default) lo sniper non prende MAI profitto da
           solo: nessun `sniper_green` oltre quelli FIRMATI (N3);
        Z4 a uscite manuali ogni proposta porta le chiavi comuni dei bot di
           flusso (`uscite_manuali.CHIAVI_PROPOSTA`, dal 29/09)."""
        sn = self.sniper_ultimo
        if sn is None:
            return
        ordini: List[Any] = []
        for mid in self._mercati_sessione():
            m = self.quadro.markets.markets.get(mid)
            if m is None:
                continue
            try:
                ordini.extend(list(m.blotter.strategy_orders(sn) or []))
            except Exception:  # noqa: BLE001
                continue
        nuovi = [o for o in ordini if str(getattr(o, "id", "")) not in self.sniper_ordini_visti]
        self.sniper_ordini_visti |= {str(getattr(o, "id", "")) for o in ordini}
        sol = self.ref.sollecitati
        for o in nuovi:
            r = CERT.riga_ordine(o, True)
            sol["Z1"] = sol.get("Z1", 0) + 1
            if r.get("sostituto"):
                continue
            motivo = CERT._legale_it(r)
            if motivo:
                self.ref.violazioni.append(CERT.Violazione(
                    "Z1", "ordine dello sniper legale su .it",
                    "ordine %s %s @%s per %s: %s" % (r.get("order_id"), r.get("side"),
                                                    r.get("price"), r.get("size"), motivo),
                    quando))
        manuali = not bool(getattr(sn, "uscite_automatiche", False))
        eventi = [(k, p) for k, p, _t in self.attivita_sniper]
        if fine and manuali:
            sol["Z3"] = sol.get("Z3", 0) + 1
            # N3 (28/09): un green FIRMATO dall'utente e' consentito (scenario
            # `uscite-manuali-firmate`): da solo, mai
            # (per IDENTITA', mai per conteggio: vedi z3_verdi_senza_la_loro_firma)
            for det in z3_verdi_senza_la_loro_firma(eventi):
                self.ref.violazioni.append(CERT.Violazione(
                    "Z3", "a uscite manuali lo sniper non prende profitto da solo",
                    det, quando))
            # 29/09 (CANTIERE N): le chiavi comuni di ogni proposta
            # (`uscite_proposte.proposta_di`), non piu' quelle vecchie dello scalper
            # tutte presenti E valorizzate (`uscite_manuali.difetti_proposta`)
            for k, p in eventi:
                if k == "uscita_proposta":
                    sol["Z4"] = sol.get("Z4", 0) + 1
                    difetti = UM.difetti_proposta(p)
                    if difetti:
                        self.ref.violazioni.append(CERT.Violazione(
                            "Z4", "proposta con tutti i numeri obbligatori",
                            "%s: %s" % (p.get("chiave"), ", ".join(difetti)), quando))
        if fine:
            sol["Z2"] = sol.get("Z2", 0) + 1
            dichiarato = any(CERT.messaggio_dichiara_non_flat(m) for m in self.db.messaggi())
            if not sn.is_flat() and not dichiarato:
                self.ref.violazioni.append(CERT.Violazione(
                    "Z2", "a fine sessione lo sniper e' piatto o dichiarato",
                    "sniper NON piatto e nessuna dichiarazione della sessione", quando))

    def strategie_vive(self) -> List[Any]:
        """Maker e sniper della sessione viva (quelli con `cancello_uscite`)."""
        out: List[Any] = []
        s = self.strategia_corrente()
        if s is not None:
            out.append(s)
        if self.sniper_ultimo is not None:
            out.append(self.sniper_ultimo)
        return out

    def ruolo_ordine(self, ordine: Any) -> Optional[str]:
        """N3 UF2: il RUOLO di un ordine dalla credenza VERA del maker
        (`certificazione.credenze`: ingressi e uscite dello slot)."""
        for c in CERT.credenze(self.strategia_corrente()):
            if any(x is ordine for x in (c.get("ingressi") or ())):
                return "ingresso"
            if any(x is ordine for x in (c.get("uscite") or ())):
                return "uscita"
        return None

    def resto_dichiarato(self, s: Any, sel: Any, lato: str, resto: float) -> bool:
        """N3 UF2: maker e sniper scrivono `min_bet_skip` (selection_id, side,
        size) per il resto che NON piazzano (regola esistente, < 0,05)."""
        for k, p, _t in list(self.attivita) + list(self.attivita_sniper):
            if k != "min_bet_skip":
                continue
            try:
                if (int(p.get("selection_id")) == int(sel)
                        and str(p.get("side") or "").upper() == str(lato).upper()
                        and abs(float(p.get("size")) - float(resto)) < 1e-9):
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def piatto_a_fine(self) -> Optional[str]:
        """N3 (UM3b): a fine sessione, a uscite manuali, maker e sniper sono
        piatti (slot IDLE/DONE, `is_flat` dello sniper) o la sessione lo ha
        DICHIARATO: vuol dire che le protezioni (force-flat di fine finestra,
        freno, tetti) sono scattate da sole."""
        if any(CERT.messaggio_dichiara_non_flat(m) for m in self.db.messaggi()):
            return None
        difetti = []
        aperti = [c for c in CERT.credenze(self.strategia_corrente())
                  if str(c.get("stato") or "") not in CERT.STATI_SLOT_CHIUSI]
        if aperti:
            difetti.append("maker con %d slot aperti (%s)" % (
                len(aperti), ", ".join(sorted({str(c.get("stato")) for c in aperti}))))
        sn = self.sniper_ultimo
        if sn is not None and not sn.is_flat():
            difetti.append("sniper non piatto")
        return "; ".join(difetti) or None

    def controlli_media(self, ms: int, quando: str, fine: bool) -> None:
        """05/10 - i controlli M della modalita' "media under"
        (``certificazione.verifica_media``) sugli ordini VERI della sua
        strategia letti dal blotter, coi fatti del banco: il mercato scelto e la
        sua Under dal RAW (``marketDefinition``: tipo e sortPriority 1), il gioco
        dal book, i parametri dalla riga del control (quelli che l'utente ha
        scritto), mai dalle attivita' del bot."""
        from .. import media_under_bot as MU

        mu = self.media
        par, _motivo = MU.leggi_parametri(self.db.control.get("params") or {})
        if mu is None or par is None:
            return
        # 06/10 (giro 4, P13): gli ordini di TUTTE le sessioni della modalita' di
        # questa partita (la morta e la nuova dopo un riavvio: e' il mercato, mai
        # una sola sessione), cosi' un ordine DOPPIO dopo la ripresa (due banche,
        # due punte vive) e' rosso (M5); + gli ordini letti dal conto alla ripresa
        ordini: List[Any] = []
        visti_id: set = set()
        for strat in (list(self.medie) or [mu]):
            for mid in self._mercati_sessione():
                m = self.quadro.markets.markets.get(mid)
                if m is None:
                    continue
                try:
                    for o in list(m.blotter.strategy_orders(strat) or []):
                        if id(o) not in visti_id:
                            visti_id.add(id(o))
                            ordini.append(o)
                except Exception:  # noqa: BLE001
                    continue
        bet_ids = {str(getattr(o, "bet_id", "")) for o in ordini if getattr(o, "bet_id", None)}
        ordini += [o for o in mu.ordini_dal_conto() if str(o.bet_id) not in bet_ids]
        righe = []
        for i, o in enumerate(ordini):
            r = CERT.riga_ordine(o, True)
            r["indice"] = i
            righe.append(r)
        ids = {r["order_id"] for r in righe}
        nuovi = ids - self.media_ordini_visti
        self.media_ordini_visti |= ids
        in_gioco = (self.in_gioco_ms.get(str(self.media_mercato_scelto))
                    if self.media_mercato_scelto else None)
        annullati: List[str] = []
        for o in ordini:
            try:
                canc = float(getattr(o, "size_cancelled", 0.0) or 0.0)
            except (TypeError, ValueError):
                canc = 0.0
            oid = str(getattr(o, "id", ""))
            self.media_nati_ms.setdefault(oid, int(ms))
            try:
                abb = float(getattr(o, "size_matched", 0.0) or 0.0)
            except (TypeError, ValueError):
                abb = 0.0
            if abb > self.media_abbinato_visto.get(oid, 0.0) + 1e-9:
                self.media_abbinato_visto[oid] = abb
                self.media_abbinato_ms[oid] = int(ms)
            if in_gioco is None or ms < in_gioco:
                self.media_annullati_al_gioco[oid] = canc
            elif canc > self.media_annullati_al_gioco.get(oid, 0.0) + 1e-9:
                annullati.append(oid)
        # 05/10 (giro 2): gli istanti di nascita e di abbinamento anche degli
        # ordini delle sessioni della modalita' gia' morte (riavvio): restano a
        # mercato e il riepilogo per ciclo li racconta (solo tempi, nessun controllo)
        for vecchia in self.medie:
            if vecchia is mu:
                continue
            for o in self.ordini_di([vecchia]):
                oid = str(getattr(o, "id", ""))
                self.media_nati_ms.setdefault(oid, int(ms))
                try:
                    abb = float(getattr(o, "size_matched", 0.0) or 0.0)
                except (TypeError, ValueError):
                    abb = 0.0
                if abb > self.media_abbinato_visto.get(oid, 0.0) + 1e-9:
                    self.media_abbinato_visto[oid] = abb
                    self.media_abbinato_ms[oid] = int(ms)
        oss = CERT.OsservazioneMedia(
            quando=quando, ms=ms, fine=fine, params=par,
            mercato_scelto=self.media_mercato_scelto, tipo_mercato=dict(self.tipo_mercato),
            under=self.media_under, ordini=righe, nuovi=nuovi, ko_ms=self.ko_ms,
            in_gioco_ms=in_gioco, force_flat_ms=self.force_flat_ms,
            annullati_in_gioco=annullati,
            prova=bool(self.db.control.get("dry_run", True)),
            letture_conto=int(self.db.letture.get(MU.TABELLA_ORDINI_CONTO, 0)),
            battiti=sum(1 for w in self.db.scritture if "heartbeat_at" in (w.get("campi") or {})))
        self.ref.violazioni.extend(CERT.verifica_media(oss, self.ref.sollecitati,
                                                       self.memoria_media))

    def giro(self, ms: int, quando: str, *, fine: bool = False) -> None:
        if self.osservatore_um is not None:
            self.osservatore_um.giro(ms, fine=fine)
        if self.sniper_ultimo is not None:
            self.controlli_sniper(ms, quando, fine)
        if self.media is not None:
            self.controlli_media(ms, quando, fine)
        if not self.sessioni and not fine:
            return
        oss = self.osservazione(ms, quando, fine=fine)
        self.ref.violazioni.extend(CERT.verifica(
            oss, self.ref.sollecitati, self.memoria,
            escludi=CERT.ESCLUSI_MEDIA if self.media is not None else frozenset()))
        if self.sorveglianza_cp is not None:
            # 04/10: l'ULTIMA riga di specchio di ogni ordine (incrementale: solo
            # le righe nuove di questo giro), come per i bot tennis
            for r in oss.specchio or []:
                k = str(r.get("bet_id") or r.get("client_order_ref") or "")
                if k:
                    self.specchio_per_ordine[k] = r
            for cod, reg, det in self.sorveglianza_cp.verifica(
                    credenze_cp(oss.credenze, self.strategia_corrente(), self,
                                specchio=list(self.specchio_per_ordine.values())),
                    self.ref.sollecitati):
                self.ref.violazioni.append(CERT.Violazione(cod, reg, det, quando))


def credenze_cp(cred: List[Dict[str, Any]], s: Any, banco: _Banco,
                specchio: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Le credenze dello scalper nella forma dei controlli CP (come
    `tennis_live/tools/replay_bot.credenze_cp`): una voce per slot, CHIUSA =
    IDLE/DONE, le chiusure con i numeri VERI dell'ordine (chiavi dello specchio
    di produzione).

    04/10 (scenario `chiusura-abbinata-in-parte`, CP1 «NESSUNA riga/credenza
    del bot la riconosce»): in coda una voce con l'ULTIMA riga dello SPECCHIO
    (`betfair_live_orders`, scritto dallo specchio vero della sessione) di ogni
    ordine, come gia' per i bot tennis: una chiusura che lo scalper ha smesso di
    seguire perche' il ciclo e' finito resta riconoscibile dalla riga che la UI
    vede (mai chiusa, mai coperta: CP2/CP3 la saltano). I numeri li giudica CP1:
    una riga con abbinato/residuo/prezzo diversi dal mercato resta violazione."""
    def _riga(o: Any) -> Dict[str, Any]:
        r = CERT.riga_ordine(o)
        return {"ordine_id": r["order_id"], "bet_id": r["bet_id"], "size": r["size"],
                "price": r["price"], "status": r["status"],
                "size_matched": r["size_matched"], "size_remaining": r["size_remaining"],
                "avg_price_matched": r["average_price_matched"]}

    out: List[Dict[str, Any]] = []
    for c in cred:
        out.append({
            "id": "%s%s" % (c.get("stato"), c.get("chiave")),
            "chiave": tuple(c.get("chiave") or ()),
            "chiusa": str(c.get("stato") or "") in CERT.STATI_SLOT_CHIUSI,
            "coperto": None, "apertura": None, "ingressi": [],
            "chiusure": [_riga(o) for o in (c.get("uscite") or ())],
            "per_selezione": True,
            "tolleranza": float(c.get("tolleranza") or 0.0),
        })
    if specchio:
        out.append({
            "id": "specchio", "chiave": (), "chiusa": False, "coperto": None,
            "apertura": None, "ingressi": [],
            "chiusure": [{"ordine_id": None, "bet_id": r.get("bet_id"),
                          "size": r.get("size"), "price": r.get("price"),
                          "status": r.get("status"),
                          "size_matched": r.get("size_matched"),
                          "size_remaining": r.get("size_remaining"),
                          "avg_price_matched": r.get("average_price_matched")}
                         for r in specchio],
            "per_selezione": True, "tolleranza": 0.0,
        })
    return out


class _Ponte:
    """Sta fra `MotoreReplay` e la strategia della sessione, e non decide niente.

    Fa quello che in produzione fa il framework flumine della sessione: passa a
    `ScalperStrategy` i book dei SOLI mercati a cui la sessione si e' abbonata
    (quelli del catalogo), a ogni aggiornamento dello stream. In piu' fa
    scorrere l'orologio (turno con la sessione), fa girare lo specchio alla sua
    cadenza e i controlli alla loro.
    """

    def __init__(self, banco: _Banco) -> None:
        self.b = banco

    @property
    def stream_ids(self) -> Any:
        return self.b._stream_ids

    def process_new_market(self, market: Any, market_book: Any) -> None:
        from flumine import utils as futils

        for _fw, s, mids in list(self.b.sessioni):
            if market.market_id in mids:
                futils.call_strategy_error_handling(s.process_new_market, market, market_book)

    def check_market_book(self, market: Any, market_book: Any) -> bool:
        b = self.b
        ms = int(getattr(market_book, "publish_time_epoch", 0) or 0)
        if b.primo_ms is None:
            b.primo_ms = ms
        b.ref.tick += 1
        b.orologio.al_book(ms / 1000.0)
        if b.ferma:
            b.motore._gen = iter(())
            b.motore._coda.clear()
            return False
        try:
            self._giro_del_book(market, market_book, b.orologio.ora_ms())
        except Exception as ex:  # noqa: BLE001 - flumine lo inghiottirebbe: si CONTA
            import traceback

            b.errori_ponte.append("%s: %s @ %s" % (
                type(ex).__name__, ex,
                traceback.extract_tb(ex.__traceback__)[-1][:2] if ex.__traceback__ else "?"))
        return False

    def _giro_del_book(self, market: Any, market_book: Any, ms: int) -> None:
        futils = _modulo("flumine.utils")
        b = self.b
        # FINE VITA della sessione maker: KO + 10' (`run_session`, `_life_s`
        # = 600 senza ht/sniper/theta; docstring del modulo: 'o KO+10''). E'
        # il confine che S2 usa per misurare quanto ci mette il force-flat.
        # 28/09: la vita VERA della sessione (`auto_mode.vita_sessione_s`, la
        # stessa che usa `run_session`): 600 s col solo maker, KO+130' con lo
        # sniper. Prima qui c'era 600 fisso (sniper fuori perimetro).
        vita_ms = b.vita_ms()
        if b.stop_ms is None and b.ko_ms is not None and ms >= b.ko_ms + vita_ms \
                and b.sessioni:
            b.stop_ms, b.stop_causa = b.ko_ms + vita_ms, "fine-vita"
        b.evento_scenario(ms)
        mid = str(market.market_id)
        if bool(getattr(market_book, "inplay", False)) and mid not in b.in_gioco_ms \
                and mid in b._mercati_sessione():
            b.in_gioco_ms[mid] = ms
        for _fw, s, mids in list(b.sessioni):
            if mid not in mids:
                continue
            if s.force_flat and b.force_flat_ms is None:
                b.force_flat_ms = ms
            prima = len(b.attivita)
            # 05/10 (giro 2): la modalita' media under non scrive in `attivita`
            # (il suo tee e' `attivita_media`): le sue azioni sono i suoi ORDINI
            media = s is b.media
            prima_m = int((getattr(s, "stats", {}) or {}).get("ordini", 0) or 0) if media else 0
            if futils.call_strategy_error_handling(s.check_market_book, market, market_book):
                futils.call_strategy_error_handling(s.process_market_book, market, market_book)
                b.ref.decisioni += 1
            b.ref.azioni += len(b.attivita) - prima
            if media:
                b.ref.azioni += int((getattr(s, "stats", {}) or {}).get("ordini", 0) or 0) \
                    - prima_m
            st = getattr(s, "stats", {}) or {}
            if (b.missione_ms is None and getattr(s, "one_green_per_phase", False)
                    and not b.in_gioco_ms and float(st.get("greens_prematch", 0) or 0) >= 1):
                b.missione_ms = ms
        # 28/09 - lo SNIPER compagno: la sua linea dalla riga live_now (stessa
        # funzione e stessa cadenza del watcher di produzione), poi il book
        if b.compagne and b.sniper_linea is not None and (
                b._linea_ms is None or ms - b._linea_ms >= 1000 * SS_LINEA_OGNI_S()):
            b._linea_ms = ms
            riga = b.db.live_now()
            if riga:
                from .. import scalper_session as _SS

                _SS.applica_linea_sniper(b.sniper_linea, riga)
        for _fw, sn, mids in list(b.compagne):
            if mid not in mids:
                continue
            if futils.call_strategy_error_handling(sn.check_market_book, market, market_book):
                futils.call_strategy_error_handling(sn.process_market_book, market, market_book)
        if b.sessioni:
            b.gira_specchio(ms)
        if ms - b._ultimo_giro_ms >= b.cadenza_ms:
            b._ultimo_giro_ms = ms
            pt = getattr(market_book, "publish_time", None)
            b.giro(ms, pt.isoformat() if pt is not None else str(ms))


# ---------------------------------------------------------------------------
# gli eventi degli scenari (nel thread del motore, a tempo di mercato)
# ---------------------------------------------------------------------------
def _posizione_aperta(s: Any) -> bool:
    # 05/10 (giro 2): la modalita' media under ha la sua posizione (niente slot)
    if callable(getattr(s, "posizione_aperta", None)):
        return bool(s.posizione_aperta())
    for slot in dict(getattr(s, "_slots", {}) or {}).values():
        if slot.status in CERT.STATI_SLOT_VIVI:
            for o in (slot.entry, slot.entry_back, slot.entry_lay):
                if o is not None and float(getattr(o, "size_matched", 0.0) or 0.0) > 0:
                    return True
    return False


def _evento_scenario(self: _Banco, ms: int) -> None:
    """Stop da UI / kill-switch / morte del processo: a meta' della finestra
    pre-match (dal primo book a KO - entry_stop_before_s), appena il bot ha una
    posizione abbinata aperta, e comunque entro il primo quarto della seconda
    meta' della finestra: il caso va PROVOCATO, non sperato."""
    guasto = guasto_dello_scenario(self.scenario)
    if self.evento_fatto or guasto not in ("bot-fermo", "kill-switch", "riavvio"):
        return
    s = self.strategia_corrente()
    if s is None or self.ko_ms is None or self.primo_ms is None:
        return
    if self.evento_ms is None:
        fine = self.ko_ms - int(float(getattr(s, "entry_stop_before_s", 420.0) or 0) * 1000)
        meta = self.primo_ms + (fine - self.primo_ms) // 2
        self.evento_ms = meta
        self._evento_ultimo = meta + (fine - meta) // 4
    if ms < self.evento_ms:
        return
    if not _posizione_aperta(s) and ms < self._evento_ultimo:
        return
    self.evento_fatto = True
    aperta = _posizione_aperta(s)
    if guasto == "bot-fermo":
        # `scalper_stop`: running/arming/armed -> 'stopping'
        if self.db.control.get("status") in ("running", "arming", "armed"):
            self.db.control["status"] = "stopping"
        self.stop_ms, self.stop_causa = ms, "ui"
        self.ref.note.append("STOP dalla UI a %d ms (posizione abbinata aperta: %s)"
                             % (ms, "si'" if aperta else "no"))
    elif guasto == "kill-switch":
        with io.open(self.kill_file, "w", encoding="utf-8") as fh:
            fh.write("stop\n")
        self.stop_ms, self.stop_causa = ms, "kill-switch"
        self.ref.note.append("KILL-SWITCH (file nella cartella del replay) a %d ms "
                             "(posizione abbinata aperta: %s)" % (ms, "si'" if aperta else "no"))
    elif guasto == "riavvio":
        self.orologio.uccidi_al_prossimo_sonno(_ProcessoUcciso("processo della sessione ucciso"))
        self.ref.note.append("PROCESSO della sessione ucciso a %d ms (posizione "
                             "abbinata aperta: %s)" % (ms, "si'" if aperta else "no"))


_Banco.evento_scenario = _evento_scenario


# ---------------------------------------------------------------------------
# le INIEZIONI, tutte in un posto e tutte rimesse a posto
# ---------------------------------------------------------------------------
def _patch(stack: ExitStack, oggetto: Any, nome: str, valore: Any) -> None:
    vecchio = getattr(oggetto, nome)
    setattr(oggetto, nome, valore)
    stack.callback(setattr, oggetto, nome, vecchio)


@contextmanager
def _iniezioni(banco: _Banco, orologio: _Orologio, kill_file: str):
    import flumine
    import flumine.clients as fclients

    import db_client

    from ... import auth as AUTH
    from ... import db as STREAM_DB
    from .. import scalper_session as SS

    trading = _TradingFinto(banco)
    banco.trading = trading

    def _niente_db(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("REPLAY: accesso al DB VERO vietato (get_supabase_client)")

    def _flumine(client: Any = None, **_k: Any) -> _FrameworkSessione:
        fw = _FrameworkSessione(banco, client)
        banco.framework_creati.append(fw)
        return fw

    def _cattura_ordine(row: Dict[str, Any]) -> None:
        r = dict(row)
        r["_ms"] = orologio.ora_ms()
        banco.righe_specchio.append(r)

    with ExitStack() as st:
        _patch(st, SS, "Db", lambda: banco.db)
        _patch(st, SS, "time", _TempoSessione(orologio))
        _patch(st, SS, "KILL_FILE", kill_file)
        _patch(st, SS, "_order_mirror_loop",
               lambda mirror, framework, stop_flag, tick_s=1.0: banco.registra_specchio(mirror))
        _patch(st, AUTH, "build_client", lambda login=True: trading)
        _patch(st, AUTH, "keep_alive", lambda client: None)
        _patch(st, flumine, "Flumine", _flumine)
        _patch(st, fclients, "BetfairClient", _ClientChiesto)
        _patch(st, db_client, "get_supabase_client", _niente_db)
        _patch(st, STREAM_DB, "upsert_live_order", _cattura_ordine)
        _patch(st, STREAM_DB, "upsert_live_position", lambda row: None)
        _patch(st, STREAM_DB, "upsert_live_settled", lambda row: None)
        _patch(st, STREAM_DB, "find_live_order_ref", lambda mode, bet_id: None)
        _patch(st, _time_mod, "time", orologio.time)
        # 28/09: il thread `sniper-line` non parte (vedi `_ThreadingSessione`)
        _patch(st, SS, "threading", _ThreadingSessione(banco))
        yield


# ---------------------------------------------------------------------------
# la PARITA' paper/live (S6): la stessa sessione armata nelle due modalita'
# ---------------------------------------------------------------------------
_ESCLUSI_PARITA = {"event_sink", "risk_sem", "market_filter", "_slots",
                   "_settled_by_id", "_ko_ms", "cycle_log", "_txn_ts",
                   "_dry_seen", "stats", "streams", "historic_stream_ids",
                   "_invested", "_markets", "name", "context", "clients",
                   "runner_contexts", "_markets_cache"}


def _parametri(s: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in vars(s).items():
        if k in _ESCLUSI_PARITA:
            continue
        if isinstance(v, (bool, int, float, str, type(None))):
            out[k] = v
        elif isinstance(v, (set, frozenset)):
            out[k] = sorted(str(x) for x in v)
        elif isinstance(v, (list, tuple)):
            try:
                out[k] = json.loads(json.dumps(list(v), default=str))
            except (TypeError, ValueError):
                continue
        elif isinstance(v, dict):
            try:
                out[k] = json.loads(json.dumps(v, default=str, sort_keys=True))
            except (TypeError, ValueError):
                continue
    return out


def arma_e_cattura(event_id: str, control: Dict[str, Any], follow: Dict[str, Any],
                   catalogo: List[Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Fa girare `run_session` VERO fino all'armamento della strategia e la
    cattura (nessun thread parte, nessun book passa). Torna (parametri della
    strategia, kwargs del client chiesto)."""
    from ...backtest import banco_comune as BC
    from .. import scalper_session as SS

    orologio = _Orologio()
    db = _DbFinto(orologio, control, follow)
    ref = CERT.Referto(event_id=str(event_id))
    with BC.simulazione_flumine():
        banco = _Banco(event_id=event_id, raw="", scenario="parita", ogni_ms=0,
                       referto=ref, orologio=orologio, db=db, catalogo=catalogo,
                       ko_ms=None)
        banco.framework_creati = []

        def _cattura(fw: _FrameworkSessione, s: Any) -> None:
            raise _ArmamentoCatturato(s, dict(fw.client_chiesto))

        banco.aggiungi_strategia = _cattura  # type: ignore[assignment]
        tmp = tempfile.mkdtemp(prefix="replay_scalper_parita_")
        try:
            with _iniezioni(banco, orologio, os.path.join(tmp, "STOP_SCALPER")):
                try:
                    SS.run_session(str(event_id))
                except _ArmamentoCatturato as cat:
                    return _parametri(cat.strategia), cat.client
                except SystemExit:
                    pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    raise RuntimeError("la sessione non ha armato nessuna strategia: %s"
                       % db.control.get("error"))


def parita_paper_live(event_id: str, control: Dict[str, Any], follow: Dict[str, Any],
                      catalogo: List[Any]) -> Dict[str, Any]:
    try:
        cp = dict(control, dry_run=True)
        cl = dict(control, dry_run=False)
        par_p, cli_p = arma_e_cattura(event_id, cp, follow, catalogo)
        par_l, cli_l = arma_e_cattura(event_id, cl, follow, catalogo)
    except Exception as ex:  # noqa: BLE001 - una parita' non misurabile E' un referto
        return {"errore": "%s: %s" % (type(ex).__name__, ex)}
    diversi = sorted(k for k in set(par_p) | set(par_l) if par_p.get(k) != par_l.get(k))
    cli_div = sorted(k for k in set(cli_p) | set(cli_l)
                     if k != "paper_trade" and cli_p.get(k) != cli_l.get(k))
    return {"parametri_diversi": [(k, par_p.get(k), par_l.get(k)) for k in diversi],
            "client_diversi": cli_div,
            "paper_trade_paper": cli_p.get("paper_trade"),
            "paper_trade_live": cli_l.get("paper_trade"),
            "n_parametri": len(par_p), "client_paper": cli_p, "client_live": cli_l}


# ---------------------------------------------------------------------------
# IL REPLAY DI UN EVENTO
# ---------------------------------------------------------------------------
def certifica_scenario(event_id: str, *, data_dir: str, scenario: str = "base",
                       ogni_ms: int = 1000, campioni_diff: int = 0) -> CERT.Referto:
    """Un evento, uno scenario, un referto. E' il contratto del banco comune."""
    del campioni_diff          # lo scalper non passa dalla riga di scan
    from ...backtest import banco_comune as BC
    from .. import scalper_session as SS

    ref = CERT.Referto(event_id=str(event_id), scenario=scenario)
    raw = percorso_raw(data_dir, event_id)
    if not os.path.exists(raw):
        ref.note.append("registrazione assente: %s" % raw)
        return ref
    ref.note.append("qualita' registrazione: %s" % qualita_registrazione(data_dir, event_id))
    definizioni, ko_iso = leggi_definizioni(raw)
    catalogo = catalogo_dal_raw(definizioni)
    if not ko_iso:
        ref.note.append("nessun MATCH_ODDS nel raw: la sessione non ha un KO")
        return ref
    from datetime import datetime

    ko_ms = int(datetime.fromisoformat(str(ko_iso).replace("Z", "+00:00")).timestamp() * 1000)
    punteggi = BC.carica_punteggi(data_dir, str(event_id))
    casa, fuori = BC.nomi_dal_punteggio(punteggi)
    follow = {"event_id": str(event_id), "fixture_id": None, "league_id": None,
              "home_name": casa, "away_name": fuori, "open_date": ko_iso}
    control = control_della_ui(event_id, scenario)
    ref.note.append("control della UI: mode=%s dry_run=%s stake=%s params=%s"
                    % (control["mode"], control["dry_run"], control["stake"],
                       sorted(control["params"].items())))
    if control["params"].get("uscite_automatiche") is True:
        ref.note.append(NOTA_USCITE_AUTO)
    ref.note.append("limiti dichiarati: catalogo sintetizzato dai marketDefinition; "
                    "scanner non usato (lo scalper legge il book); orologio di "
                    "mercato per `time.time`; settlement non raggiunto (fine vita "
                    "della sessione); theta fuori perimetro%s"
                    % ("" if sniper_acceso(scenario) else "; sniper spento (scenari "
                       "`sniper*` per lo sniper)"))

    orologio = _Orologio()
    primo = primo_publish_time_ms(raw)
    if primo is not None:
        # la sessione si arma all'inizio della registrazione, sull'orologio
        # del mercato (le scritture d'avvio portano quell'istante)
        orologio.ora_s = primo / 1000.0
    db = _DbFinto(orologio, control, follow)
    if sniper_acceso(scenario):
        db.punteggi_live_now = righe_live_now(data_dir, event_id)
        ref.note.append("SNIPER: righe live_now dal sidecar %d (linea Under (gol+1).5 "
                        "con `scalper_session.applica_linea_sniper` ogni %d s di "
                        "mercato); vita della sessione KO+%d s"
                        % (len(db.punteggi_live_now), SS_LINEA_OGNI_S(),
                           _vita_da_control(control)))
        if not db.punteggi_live_now:
            ref.note.append("SNIPER: sidecar dei punteggi ASSENTE: la linea resta "
                            "OVER_UNDER_15 (0-0) per tutta la partita - referto "
                            "non valido per lo sniper")
    tmp = tempfile.mkdtemp(prefix="replay_scalper_")
    kill_file = os.path.join(tmp, "STOP_SCALPER")
    esiti: Dict[str, Any] = {}
    with BC.simulazione_flumine():
        banco = _Banco(event_id=event_id, raw=raw, scenario=scenario, ogni_ms=ogni_ms,
                       referto=ref, orologio=orologio, db=db, catalogo=catalogo,
                       ko_ms=ko_ms)
        banco.framework_creati = []
        banco.kill_file = kill_file
        if scenario in SCENARI_MEDIA:
            # 05/10: i fatti del banco per i controlli M, letti dal RAW (mai dal
            # bot): tipo di ogni mercato, il mercato scelto, la sua Under
            banco.tipo_mercato = {mid: str(d.get("market_type") or "")
                                  for mid, d in definizioni.items()}
            scelto = [mid for mid, d in definizioni.items()
                      if d.get("market_type") == mercato_media(scenario)]
            banco.media_mercato_scelto = scelto[0] if scelto else None
            if scelto:
                banco.media_under = next(
                    (int(sid) for sid, sp in definizioni[scelto[0]].get("runners") or []
                     if sp == 1), None)
            ref.note.append("MEDIA UNDER: mercato %s -> %s, Under %s; maker e sniper "
                            "non armati; controlli M1-M11 + S6; B2 e K5 del maker non "
                            "applicati (posizione in gioco per progetto)"
                            % (mercato_media(scenario), banco.media_mercato_scelto,
                               banco.media_under))
            if not scelto:
                ref.note.append("MEDIA UNDER: la registrazione NON ha il mercato %s: "
                                "referto non valido per la modalita'"
                                % mercato_media(scenario))
        if scenario in ("base", "paper") or scenario in SCENARI_MEDIA:
            banco.parita = parita_paper_live(event_id, control, follow, catalogo)
            p = banco.parita
            if not p.get("errore"):
                ref.note.append("parita' paper/live: %d parametri della strategia "
                                "confrontati, diversi %d; client paper %s / live %s"
                                % (p.get("n_parametri", 0), len(p.get("parametri_diversi") or []),
                                   p.get("client_paper"), p.get("client_live")))
        rifiuti = None
        ritardi = None
        if guasto_dello_scenario(scenario) == "rifiuti-betfair":
            rifiuti = _controllo_rifiuti(banco.quadro, PIAZZAMENTI_RIFIUTATI)
            banco.quadro.trading_controls.append(rifiuti)
            banco.rifiuti = rifiuti
        if guasto_dello_scenario(scenario) == "esiti-ignoti":
            ritardi = _ritarda_esiti(banco.quadro, PIAZZAMENTI_IGNOTI, RITARDO_ESITO_IGNOTO_S)
        guasto_cp = None
        if scenario == CP.SCENARIO:
            def _ruolo(ordine: Any) -> Optional[str]:
                for c in CERT.credenze(banco.strategia_corrente()):
                    if any(x is ordine for x in (c.get("uscite") or ())):
                        return "uscita"
                    if any(x is ordine for x in (c.get("ingressi") or ())):
                        return "ingresso"
                return None

            guasto_cp = CP.GuastoChiusuraParziale(ruolo=_ruolo)
            banco.motore.guasto_chiusure = guasto_cp
            banco.sorveglianza_cp = CP.Sorveglianza(guasto_cp)
        if scenario in UM.SCENARI:
            def _firma(chiave: str, istante: str) -> None:
                # la RPC `scalper_approva_uscita`: {chiave: now()} unito alle
                # firme gia' presenti in params.uscite_approvate
                # (params sostituiti interi: la sessione li legge da un altro
                # thread e un dizionario non cambia mai sotto la sua lettura)
                params = dict(db.control.get("params") or {})
                firme = dict(params.get("uscite_approvate") or {})
                firme[str(chiave)] = istante
                params["uscite_approvate"] = firme
                db.control["params"] = params

            banco.osservatore_um = UM.Osservatore(
                scenario, strategie=banco.strategie_vive,
                ordini_di=lambda s: banco.ordini_di([s]),
                firma=_firma if scenario == UM.SCENARIO_FIRMATE else None,
                piatto_a_fine=banco.piatto_a_fine,
                ruolo=banco.ruolo_ordine,
                resto_non_piazzabile=banco.resto_dichiarato,
                # 04/10: sotto l'importo finale minimo del place-and-trim
                # (0,50, `minimi_it`) Betfair .it non accetta nessun ordine:
                # il resto DICHIARATO dal bot (`min_bet_skip`) e' il residuo
                # ricordato della decisione dell'utente, non un'uscita sbagliata
                soglia_resto=SUBMIN_IMPORTO_FINALE_MIN)
            ref.note.append("USCITE MANUALI: interruttore spento; %s"
                            % ("il banco firma ogni proposta dopo %d s di mercato "
                               "(params.uscite_approvate, riletta dalla sessione al "
                               "battito)" % int(UM.FIRMA_DOPO_S)
                               if scenario == UM.SCENARIO_FIRMATE else "nessuna firma"))
        try:
            with ExitStack() as pila:
                if banco.osservatore_um is not None:
                    pila.enter_context(banco.osservatore_um.attivo())
                pila.enter_context(_iniezioni(banco, orologio, kill_file))
                esiti["prima"] = _una_sessione(SS, event_id, banco)
                if guasto_dello_scenario(scenario) == "riavvio" and esiti["prima"] == "ucciso":
                    _riarma(SS, event_id, banco, esiti)
                # l'ULTIMO giro, a sessione chiusa (S3, S4)
                banco.giro(orologio.ora_ms(), "fine sessione", fine=True)
                banco.ferma_motore()
        finally:
            banco.ferma_motore()
            shutil.rmtree(tmp, ignore_errors=True)
        if banco.errore_motore is not None:
            ex = banco.errore_motore
            ref.note.append("replay fallito: %s: %s" % (type(ex).__name__, ex))
    _chiudi_referto(ref, banco, rifiuti, ritardi, guasto_cp, esiti)
    if scenario == SCENARIO_AUTO_LIVE:
        _controlla_auto_live(ref, banco, control)
    return ref


def _controlla_auto_live(ref: Any, banco: Any, control: Dict[str, Any]) -> None:
    """04/10 - «soldi veri» scelto sull'interruttore dell'auto-mode: la sessione
    armata dal supervisore deve girare sul client REALE (``paper_trade=False``)
    e mandare ordini (sul banco: il client «reale» simulato di flumine)."""
    clients = [c for fw in getattr(banco, "framework_creati", []) or []
               for c in (getattr(fw, "clients", None) or [])]
    reali = [c for c in clients if getattr(c, "paper_trade", True) is False]
    esito = ("dry_run=%s, client reali %d su %d, ordini %d"
             % (control.get("dry_run"), len(reali), len(clients), ref.ordini_piazzati))
    ref.note.append("AUTO-LIVE: " + esito)
    if control.get("dry_run") is not False or not reali or ref.ordini_piazzati <= 0:
        ref.violazioni.append(CERT.Violazione(
            "AL1", "soldi veri scelti sull'interruttore dell'auto-mode: la sessione "
                   "armata dal supervisore manda ordini VERI (ordine dell'utente 04/10)",
            esito))


def _una_sessione(SS: Any, event_id: str, banco: _Banco) -> str:
    """`run_session` VERO nel thread di controllo. Torna come e' finita."""
    try:
        SS.run_session(str(event_id))
    except _ProcessoUcciso:
        fw = banco.sessioni[-1][0] if banco.sessioni else None
        if fw is not None:
            banco.uccidi_sessione(fw)
        return "ucciso"
    except SystemExit:
        banco.ref.note.append("la sessione e' uscita in errore: %s"
                              % (banco.db.control.get("error") or "?"))
        return "errore"
    return "finita"


def _riarma(SS: Any, event_id: str, banco: _Banco, esiti: Dict[str, Any]) -> None:
    """Dopo la morte del processo: il supervisore marca la riga ORFANA dopo
    `ORPHAN_HEARTBEAT_S` (`scalper_service.main`: 'running' senza figlio e
    heartbeat fermo -> 'error'), poi l'utente riarma (`scalper_activate`:
    status 'requested', stessi mode/dry_run/stake/params) e il supervisore
    lancia una sessione NUOVA."""
    from .. import scalper_service as SVC

    orologio = banco.orologio
    orologio.sleep(float(SVC.ORPHAN_HEARTBEAT_S))
    # la riga (e dal 04/10 l'avviso) come li scrive il supervisore: la funzione
    # VERA di produzione (`scalper_service.marca_orfana`)
    SVC.marca_orfana(banco.db, event_id, dict(banco.db.control))
    orologio.sleep(ATTESA_RIARMO_S)
    # `scalper_activate` (RPC): la riga torna 'requested' e si azzera il resto
    banco.db.control.update({"status": "requested", "bias": None, "bias_meta": None,
                             "error": None, "started_at": None, "stopped_at": None})
    banco.riavviata = True
    banco.orfani_attivi = True
    banco.ref.note.append("sessione RIARMATA dopo %d s: parte un processo nuovo"
                          % int(float(SVC.ORPHAN_HEARTBEAT_S) + ATTESA_RIARMO_S))
    esiti["seconda"] = _una_sessione(SS, event_id, banco)


def _referto_media(ref: CERT.Referto, banco: _Banco) -> None:
    """05/10 MEDIA UNDER: le note della modalita' nel referto (stato finale,
    riepilogo PER CICLO dagli ordini veri, P&L con la riga NETTO, motivi di non
    ingresso, controlli M) e, senza nessun ordine, lo scenario NON ESERCITATO."""
    mu = banco.media
    db = banco.db
    eventi_m: Dict[str, int] = {}
    for k, _p, _t in banco.attivita_media:
        eventi_m[k] = eventi_m.get(k, 0) + 1
    st_m = dict(getattr(mu, "stats", {}) or {})
    medie = list(getattr(banco, "medie", None) or [mu])

    def _somma(chiave: str) -> int:
        return sum(int((getattr(m_s, "stats", {}) or {}).get(chiave, 0) or 0) for m_s in medie)
    ref.note.append("MEDIA UNDER: stato finale %s; sessioni della modalita' %d; cicli "
                    "chiusi %d; ordini piazzati (le azioni del referto) %d; eventi %s"
                    % (st_m.get("stato"), len(medie), _somma("cicli_chiusi"),
                       _somma("ordini"), eventi_m))
    # 05/10 (giro 2, par.2.2): il riepilogo PER CICLO dagli ordini veri
    from .. import media_under_bot as MU

    mid_m = str(banco.media_mercato_scelto or "")
    ordini_m = [o for o in banco.ordini_di(medie) if str(getattr(o, "market_id", "")) == mid_m]
    par_m, _mot = MU.leggi_parametri(db.control.get("params") or {})
    comm_m = float(par_m.commissione) if par_m is not None else 0.05
    stato_runner = None
    mk = banco.quadro.markets.markets.get(mid_m) if mid_m else None
    for r in (getattr(getattr(mk, "market_book", None), "runners", None) or []):
        if banco.media_under is not None and int(r.selection_id) == int(banco.media_under):
            st_r = str(getattr(r, "status", "") or "")
            stato_runner = st_r if st_r in ("WINNER", "LOSER") else None
    cicli_m, conto_m = riepilogo_cicli_media(
        ordini_m, banco.media_nati_ms, banco.media_abbinato_ms, banco.attivita_media,
        ko_ms=banco.ko_ms, in_gioco_ms=banco.in_gioco_ms.get(mid_m),
        commissione=comm_m, stato_runner=stato_runner)
    for c in cicli_m:
        ref.note.append("MEDIA UNDER ciclo %d: %s" % (c["ciclo"], c["riga"]))
    if not cicli_m:
        ref.note.append("MEDIA UNDER: nessun ciclo (nessun ordine della modalita')")
    ref.note.append("MEDIA UNDER P&L del replay: lordo %+.2f | commissione %.2f "
                    "(%.1f%%) | NETTO %+.2f EUR%s (dagli ordini abbinati della "
                    "modalita'; non e' il metro della certificazione: il metro e' la "
                    "condotta)"
                    % (conto_m["lordo"], conto_m["commissione"],
                       conto_m["aliquota"] * 100, conto_m["netto"],
                       (" + %d cicli APERTI con esito ignoto (fuori dal conto)"
                        % conto_m["cicli_esito_ignoto"])
                       if conto_m["cicli_esito_ignoto"] else ""))
    ref.stats_finali["media_riepilogo_cicli"] = cicli_m
    ref.stats_finali["media_conto"] = conto_m
    motivi_m: Dict[str, int] = {}
    for m_s in medie:
        for k_m, n_m in dict((getattr(m_s, "stats", {}) or {}).get("non_ingresso") or {}).items():
            motivi_m[k_m] = motivi_m.get(k_m, 0) + int(n_m)
    if motivi_m:
        ref.note.append("MEDIA UNDER: motivi di non ingresso (book in cui il filtro "
                        "ha fermato la punta, il PRIMO filtro che non passa): %s"
                        % "; ".join("%s x%d" % (MU.MOTIVI_NON_INGRESSO.get(k, k), n)
                                    for k, n in sorted(motivi_m.items(),
                                                       key=lambda x: -x[1])))
    battiti = sum(1 for w in db.scritture if "heartbeat_at" in (w.get("campi") or {}))
    ref.note.append("MEDIA UNDER: letture degli ordini del conto (`%s`) %d su %d battiti "
                    "della sessione (%s); fonte finale del riquadro: %s"
                    % (MU.TABELLA_ORDINI_CONTO, int(db.letture.get(MU.TABELLA_ORDINI_CONTO, 0)),
                       battiti, "PROVA: devono essere 0" if db.control.get("dry_run", True)
                       else "soldi veri: solo a posizione aperta, al piu' una per battito",
                       st_m.get("fonte")))
    if not ordini_m:
        # un replay della modalita' senza un solo ordine NON e' un OK
        primo = (max(motivi_m.items(), key=lambda x: x[1])[0] if motivi_m else None)
        ref.non_esercitato.append(
            "la modalita' media under non ha piazzato NESSUN ordine su %s: %s"
            % (mid_m or "nessun mercato",
               ("filtro che l'ha fermata piu' spesso: %s (x%d)"
                % (MU.MOTIVI_NON_INGRESSO.get(primo, primo), motivi_m[primo]))
               if primo else "nessun book in pre-match valutato per l'ingresso"))
    mai_m = [c for c, _r in CERT.elenco_controlli_media()
             if not ref.sollecitati.get(c)]
    ref.note.append("MEDIA UNDER: controlli M sollecitati %s; MAI sollecitati "
                    "(non lo so): %s"
                    % ({c: ref.sollecitati.get(c, 0) for c, _r in
                        CERT.elenco_controlli_media() if ref.sollecitati.get(c)},
                       ", ".join(mai_m) or "nessuno"))
    stati_m = sorted({str(p.get("stato") or "") for k, p, _t in banco.attivita_media
                      if p.get("stato")})
    if stati_m:
        ref.note.append("MEDIA UNDER: stati annunciati %s" % stati_m)


def _chiudi_referto(ref: CERT.Referto, banco: _Banco, rifiuti: Any, ritardi: Any,
                    guasto_cp: Any, esiti: Dict[str, Any]) -> None:
    db = banco.db
    msg = db.messaggi()
    if any("kickoff passato" in m for m in msg):
        causa = "fine-vita"
    elif banco.stop_causa:
        causa = banco.stop_causa
    elif any("CRASH" in m for m in msg):
        causa = "crash"
    else:
        causa = ""
    ref.note.append("sessioni: %s; stato finale '%s' (causa della fine: %s)"
                    % (esiti, db.control.get("status"), causa or "?"))
    tutte = [x[1] for x in banco.sessioni_morte]
    tutte += [s for fw in banco.framework_creati for s in fw.strategie]
    viste: List[Any] = []
    for s in tutte:
        if all(s is not v for v in viste):
            viste.append(s)
    ordini = banco.ordini_di(viste)
    ref.ordini_piazzati = len(ordini) + (len(rifiuti.rifiutati) if rifiuti else 0)
    ref.ordini_abbinati = sum(1 for o in ordini
                              if float(getattr(o, "size_matched", 0.0) or 0.0) > 0.009)
    ref.stati_visti = list(banco.stati_visti)
    ref.fasi_viste = list(banco.fasi_viste)
    for k, _p, _t in banco.attivita:
        ref.motivi[k] = ref.motivi.get(k, 0) + 1
    ref.stats_finali = dict(db.control.get("stats") or {})
    mot = banco.motore
    ref.note.append("book in ritardo: %d; lapse al fischio: %d; lapse alla "
                    "sospensione: %d; righe di specchio catturate: %d"
                    % (mot.book_in_ritardo, mot.lapse_al_fischio,
                       mot.lapse_alla_sospensione, len(banco.righe_specchio)))
    ref.note.append("fasi viste: %s" % ", ".join(banco.fasi_viste))
    ref.note.append("uscite EFFETTIVE delle strategie a fine sessione: %s"
                    % ("AUTOMATICHE" if viste and all(
                        getattr(s, "uscite_automatiche", False) is True for s in viste) else
                       ("MANUALI" if viste else "nessuna strategia")))
    if banco.media is not None:
        _referto_media(ref, banco)
    if banco.sniper_ultimo is not None:
        sn = banco.sniper_ultimo
        eventi: Dict[str, int] = {}
        for k, _p, _t in banco.attivita_sniper:
            eventi[k] = eventi.get(k, 0) + 1
        ref.note.append("SNIPER: uscite %s; stats %s; eventi %s; piatto a fine sessione: %s"
                        % ("automatiche" if getattr(sn, "uscite_automatiche", False)
                           else "manuali",
                           {k: v for k, v in dict(getattr(sn, "stats", {}) or {}).items()
                            if v}, eventi, sn.is_flat()))
    mai = [s for s in sorted(CERT.STATI_SLOT) if "slot:%s" % s not in banco.stati_visti]
    if mai:
        ref.note.append("stati dello slot MAI visti: %s" % ", ".join(mai))
    if rifiuti is not None:
        ref.note.append("guasto: %d piazzamenti RIFIUTATI dal trading control"
                        % len(rifiuti.rifiutati))
    if ritardi is not None:
        ref.note.append("guasto: %d piazzamenti con esito IGNOTO per %d s"
                        % (ritardi["ritardati"], int(RITARDO_ESITO_IGNOTO_S)))
    if guasto_cp is not None:
        ref.note.append(guasto_cp.riepilogo())
    chiamate = [c for c, _ in getattr(banco, "trading").betting.chiamate
                if c != "list_market_catalogue"]
    if chiamate:
        ref.note.append("chiamate REST della sessione (registrate, mai eseguite): %s"
                        % ", ".join(chiamate))
    if banco.errori_ponte:
        ref.violazioni.append(CERT.Violazione(
            "BANCO-PONTE", "un errore del replay dentro il giro di un book e' un "
            "guasto del banco, mai un OK muto",
            "%d errori, primo: %s" % (len(banco.errori_ponte), banco.errori_ponte[0])))
    oss = banco.osservatore_um
    if oss is not None:
        for cod, n in oss.sollecitati.items():
            ref.sollecitati[cod] = ref.sollecitati.get(cod, 0) + n
        for cod, reg, det, quando in oss.violazioni:
            ref.violazioni.append(CERT.Violazione(cod, reg, det, quando))
        ref.note.append(oss.riepilogo())
        mai = [c for c, _r in UM.elenco_controlli(oss.scenario) if not oss.sollecitati.get(c)]
        if mai:
            ref.note.append("USCITE MANUALI: controlli MAI sollecitati (non lo so): %s"
                            % ", ".join(mai))
    if not ref.decisioni:
        ref.note.append("la strategia non ha MAI deciso: il referto dice 'non lo so'")
