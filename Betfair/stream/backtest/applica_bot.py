"""applica_bot.py - "APPLICA BOT" del Match Replay (06/10/2026; per TUTTI i bot dal 07/10).

Fa girare un bot sulla registrazione di una partita con il CODICE DI
PRODUZIONE, dallo stesso punto d'ingresso del banco comune
(``registro_bot.bot(nome).funzione_replay()``, cioe' quello che usa
``python -m Betfair.stream.backtest.certifica``): flumine simulato, coda,
latenza e bet delay del banco, minimi .it. Nessun replay "a parte".

Ne esce la CRONOLOGIA DEGLI ORDINI del bot: le righe ``betfair_live_orders``
(``referto.ordini_specchio``: per lo scalper quelle della sessione vera, per gli
altri bot quelle che ``varianti_bot.SpecchioOrdini`` costruisce dagli ordini
VERI del flumine del banco con ``LiveTradingStrategy._order_row``), ciascuna con
l'istante ``_ms`` del banco (= publish time Betfair, lo stesso orologio dei
frame del replay). Si tengono solo le righe in cui lo stato dell'ordine CAMBIA.

07/10 (ordini dell'utente): <<portare TUTTI I BOT nella sezione "applica bot">> e
<<devo poter modificare i parametri di ognuno [...] SENZA CAMBIARE LA STRATEGIA>>.
Contratto comune (fissato dal coordinatore):
  * la funzione di replay accetta ``parametri`` (sostituzioni del catalogo del
    bot, ValueError su chiave/valore non ammesso) e ``dal_ms`` (istante in cui
    l'utente ACCENDE il bot); con entrambi None il referto e' quello di sempre;
  * ``clic_ms`` (lista di istanti di clic, <<Attiva adesso>> della media under)
    SOLO ai bot la cui funzione di replay lo dichiara nella firma;
  * il catalogo di ogni bot e' ``registro_bot.BotRegistrato.parametri``;
  * gli scenari NON sono un elenco a mano: vengono da ``elenco_scenari()`` del
    registro, filtrati qui sotto (``SCENARI_APPLICABILI``/``SCENARI_SCARTATI``,
    ogni scarto col motivo; il test di contratto rifiuta uno scenario del
    registro che non sia ne' nell'uno ne' nell'altro).

Il catalogo per la UI (bot -> sport, etichetta, scenari, parametri con i
default) si GENERA da qui: ``python -m Betfair.stream.backtest.applica_bot
--catalogo-ts > frontend/src/lib/replayBotCatalogo.ts``; il test di contratto
``Betfair/stream/tests/test_applica_bot_tutti_2026_10_07.py`` diventa rosso se
il file TS non e' allineato.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

#: cadenza del banco: quella di ``certifica`` (``--ogni-ms`` 0 = cadenza del servizio)
OGNI_MS = 0

#: i campi che, se cambiano, fanno una riga nuova della cronologia
_CAMPI_STATO = ("status", "price", "size", "size_matched", "size_remaining",
                "size_cancelled", "size_lapsed", "size_voided",
                "average_price_matched", "bet_id")

#: le due modalita' che la UI mostra (paper = specchio del live)
PROVA = "prova"
SOLDI_VERI = "soldi_veri_simulati"

# ---------------------------------------------------------------------------
# GLI SCENARI CHE HANNO SENSO SU UNA PARTITA REGISTRATA
# ---------------------------------------------------------------------------
# bot -> scenario -> (famiglia, modalita', etichetta). La FAMIGLIA raggruppa le
# due modalita' dello STESSO scenario (es. ``paper`` e ``base`` dello scalper):
# la UI mostra la famiglia e poi <<Prova>> / <<Soldi veri simulati>> se ci sono
# entrambe. Etichette per il trader; il set degli scenari e' quello del registro.
SCENARI_APPLICABILI: Dict[str, Dict[str, Tuple[str, str, str]]] = {
    "mike": {
        "base": ("Mike - come in produzione", SOLDI_VERI, "parametri di serie"),
        "taker": ("Mike - chiusura pre-match a mercato", SOLDI_VERI, "uscita pre-match taker"),
        "copertura-legacy": ("Mike - copertura come punta Over 4,5", SOLDI_VERI,
                             "copertura nella forma di prima"),
        "senza-seconda-puntata": ("Mike - senza seconda puntata", SOLDI_VERI,
                                  "seconda puntata spenta"),
        "uscite-automatiche": ("Mike - uscite automatiche", SOLDI_VERI,
                               "il bot esegue da solo anche le uscite in perdita"),
    },
    "omega": {
        "v4": ("Omega - motore V4 (come in produzione)", SOLDI_VERI, "motore di serie"),
        "uscite-automatiche": ("Omega - V4 con uscite automatiche", SOLDI_VERI,
                               "uscite di protezione eseguite dal bot"),
        "v3": ("Omega - cancello V3 del 16/09", SOLDI_VERI, "numeri del 16/09, per confronto"),
        "base": ("Omega - motore v2 (legacy)", SOLDI_VERI, "motore v2, obiettivo di serie"),
        "giornata-reale": ("Omega - v2 con obiettivo di una giornata vera", SOLDI_VERI,
                           "obiettivo 5 EUR su una partita"),
        "apertura": ("Omega - v2 con banda di quota fino a 500", SOLDI_VERI,
                     "l'unico v2 che apre sulle registrazioni"),
        "paper": ("Omega - v2 con banda di quota fino a 500", PROVA,
                  "stessa cosa in prova"),
    },
    "safe_base": {"base": ("Safe Base - come in produzione", SOLDI_VERI, "variante BASE accesa")},
    "safe_esatto": {"base": ("Safe Risultato Esatto - come in produzione", SOLDI_VERI,
                             "variante ESATTO accesa")},
    "safe_punta": {"base": ("Safe Punta - come in produzione", SOLDI_VERI,
                            "variante PUNTA accesa")},
    "safe_tennis": {
        "base": ("Safe tennis - come in produzione", SOLDI_VERI, "percorso live"),
        "paper": ("Safe tennis - come in produzione", PROVA, "percorso paper"),
    },
    "scalper_calcio": {
        "base": ("Scalper - maker", SOLDI_VERI, "valori di serie della UI"),
        "paper": ("Scalper - maker", PROVA, "stesso control in prova"),
        "senza-missione": ("Scalper - maker senza missione 2-tick", SOLDI_VERI,
                           "tutti i cicli che la strategia concede"),
        "sniper": ("Scalper - sniper", SOLDI_VERI, "maker + sniper"),
        "sniper-paper": ("Scalper - sniper", PROVA, "maker + sniper in prova"),
        "sniper-uscite-auto": ("Scalper - sniper con uscite automatiche", SOLDI_VERI,
                               "lo sniper prende profitto da solo"),
        "uscite-manuali": ("Scalper - sniper con uscite manuali (di serie)", SOLDI_VERI,
                           "ogni uscita resta una proposta"),
        "media-under": ("Scalper - Media Under 2,5", SOLDI_VERI, "valori di serie della scheda"),
        "media-under-paper": ("Scalper - Media Under 2,5", PROVA, "in prova"),
        "media-under-35": ("Scalper - Media Under 3,5", SOLDI_VERI, "linea 3,5"),
        "media-under-obiettivo-030": ("Scalper - Media Under 2,5, obiettivo 0,30 EUR",
                                      SOLDI_VERI, "obiettivo fisso"),
        "media-under-rientri-1": ("Scalper - Media Under 2,5, un rientro", SOLDI_VERI,
                                  "massimo un rientro"),
        "media-under-rischio-30": ("Scalper - Media Under 2,5, rischio 30 EUR", SOLDI_VERI,
                                   "rischio massimo 30 EUR"),
        "media-under-tick-1": ("Scalper - Media Under 2,5, rientro e chiusura a 1 tick",
                               SOLDI_VERI, "1 tick"),
        "media-under-liquidita-100": ("Scalper - Media Under 2,5, liquidita' minima 100 EUR",
                                      SOLDI_VERI, "liquidita' 100"),
        "media-under-35-liquidita-50": ("Scalper - Media Under 3,5, liquidita' minima 50 EUR",
                                        SOLDI_VERI, "liquidita' 50"),
    },
}
for _b in ("tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing"):
    _n = {"tennis_scalper": "Tennis Scalper", "tennis_pro": "Tennis Pro",
          "tennis_flb": "Tennis FLB", "tennis_swing": "Tennis Swing"}[_b]
    SCENARI_APPLICABILI[_b] = {
        "base": ("%s - preset di produzione" % _n, PROVA,
                 "uscite automatiche dichiarate dal banco"),
        "gate-aperto": ("%s - soglie di liquidita' e bande aperte" % _n, PROVA,
                        "per vederlo operare dove i default non entrano"),
        "parziali": ("%s - stake 400 EUR" % _n, PROVA, "ordini abbinati in parte"),
        "uscite-manuali": ("%s - uscite manuali (di serie), soglie aperte" % _n, PROVA,
                           "ogni uscita resta una proposta"),
        "live": ("%s - soglie aperte, percorso live" % _n, SOLDI_VERI,
                 "minimi e granularita' .it del live"),
        "soldi-veri": ("%s - soldi veri, soglie aperte" % _n, SOLDI_VERI,
                       "catena soldi veri del runner"),
        "soldi-veri-paper": ("%s - soldi veri, soglie aperte" % _n, PROVA,
                             "bot in prova nel runner live"),
    }

_GUASTO = "guasto o trasporto iniettato: serve alla certificazione, non a provare una variante"
_UTENTE = "gesto dell'utente simulato dal banco (firma, cash out, ordine a mano, stop)"
_UGUALE = "oggi uguale a un altro scenario gia' in elenco"
_INIETTATO = "posizione o modello dichiarato dal banco, non nato dalla strategia"
_TETTI = ("tetti stretti per far parlare i controlli di certificazione: i tetti si "
          "variano dal pannello Parametri")

#: gli scenari del registro che NON si offrono all'utente, col motivo
SCENARI_SCARTATI: Dict[str, Dict[str, str]] = {
    "mike": {
        "bot-fermo": "pre-match e re-ingresso spenti: nessuna apertura per costruzione",
        "cap-stretto": _TETTI,
        "feed-stantio": _GUASTO, "esiti-ignoti": _GUASTO, "taker-esiti-ignoti": _GUASTO,
        "riavvio": _GUASTO, "gol-precoce": _UGUALE + " (e' `base` su un'altra partita)",
        "cashout-globale": _UTENTE, "chiuso-fuori-app": _UTENTE,
        "copertura-rifiutata": _GUASTO, "copertura-rifiutata-legacy": _GUASTO,
        "cashout-dopo-copertura": _UTENTE, "rifiuti-betfair": _GUASTO,
        "chiusura-abbinata-in-parte": _GUASTO, "ko-green-parziale": _GUASTO,
        "fermo-copertura": _UTENTE, "lettura-dati-ko": _GUASTO,
        "firma-dopo-gol-decisivo": _UTENTE,
        "firma-dopo-gol-decisivo-senza-chiusura": _UTENTE,
        "uscite-in-perdita-firmate": _UTENTE, "punteggio-ko": _GUASTO,
    },
    "omega": {
        "bot-fermo": _UTENTE, "v4-bot-fermo": _UTENTE, "feed-stantio": _GUASTO,
        "cap-stretto": _TETTI,
        "esiti-ignoti": _GUASTO, "riavvio": _GUASTO, "v4-riavvio": _GUASTO,
        "manuale-e-bot": _UTENTE, "cashout-globale": _UTENTE,
        "proposta-approvata": _UTENTE, "rifiuti-betfair": _GUASTO,
        "chiuso-fuori-app": _UTENTE, "chiusura-abbinata-in-parte": _GUASTO,
    },
    "safe_tennis": {
        "paper-iniettata": _INIETTATO, "catalogo-assente": _GUASTO,
        "posizione-iniettata": _INIETTATO, "approvata-subito": _UTENTE,
        "mai-approvata": _INIETTATO, "bot-fermo": _UTENTE, "feed-stantio": _GUASTO,
        "esiti-ignoti": _GUASTO, "rifiuti-betfair": _GUASTO, "uscita-ignota": _GUASTO,
        "riavvio": _GUASTO, "chiusura-fuori-app": _UTENTE,
        "chiusura-fuori-app-ridotta": _UTENTE, "chiusura-abbinata-in-parte": _GUASTO,
        "proposta-approvata": _INIETTATO, "proposta-scaduta": _INIETTATO,
    },
    "scalper_calcio": {
        "bot-fermo": _UTENTE, "kill-switch": _UTENTE, "esiti-ignoti": _GUASTO,
        "rifiuti-betfair": _GUASTO, "riavvio": _GUASTO,
        "chiusura-abbinata-in-parte": _GUASTO, "uscite-manuali-firmate": _UTENTE,
        "auto-live": "armamento dall'auto-mode, non dall'utente",
        "media-under-riavvio": _GUASTO, "media-under-rifiuti-betfair": _GUASTO,
        "media-under-esiti-ignoti": _GUASTO, "media-under-kill-switch": _UTENTE,
        "media-under-bot-fermo": _UTENTE,
        # 08/10 (cantiere 9): ingresso abbinato in parte e finto Betfair coi codici
        "ingresso-abbinato-in-parte": _GUASTO, "ingresso-abbinato-in-parte-paper": _GUASTO,
        "rifiuti-betfair-codici": _GUASTO, "rifiuti-betfair-codici-paper": _GUASTO,
        # 08/10 (W3b): l'ordine esterno dell'utente (dal sito) simulato dal banco
        "ordine-esterno": _UTENTE, "ordine-esterno-altro-mercato": _UTENTE,
        "ordine-esterno-app": _UTENTE, "ordine-esterno-di-un-bot": _UTENTE,
        "ordine-esterno-db-giu": _GUASTO,
    },
}
# 07/10 (integrazione del coordinatore): gli scenari del banco del pulsante
# <<Attiva adesso>> mettono il clic in punti FISSI della partita (regola del
# banco); in Applica bot il clic lo mette l'utente sulla barra (``dal_ms`` +
# ``clic_ms`` sugli scenari della media under), quindi qui restano fuori.
_CLIC_DEL_BANCO = ("clic in un punto fisso del banco: in Applica bot il clic lo metti tu "
                   "sulla barra (accendi al cursore + clic aggiuntivi)")
for _s in ("lontano", "lontano-paper", "lontano-filtri", "lontano-35", "finestra", "gioco",
           "gioco-35", "prima-del-gol", "prima-del-gol-35", "dopo-il-gol", "sospeso",
           "prezzi-fermi", "doppio", "in-posizione", "riavvio", "due-clic", "tick-1",
           "tick-1-filtri"):
    SCENARI_SCARTATI["scalper_calcio"]["media-clic-" + _s] = _CLIC_DEL_BANCO
_SAFE_CALCIO_SCARTATI = {
    "cap-stretto": _UTENTE + " (lo scenario preme <<Investi>>)",
    "bot-fermo": _UTENTE, "esiti-ignoti": _GUASTO, "feed-stantio": _GUASTO,
    "riavvio": _GUASTO, "paper": _UTENTE + " (lo scenario preme <<Investi>>)",
    "ordini-manuali": _UTENTE, "due-lay": _UTENTE, "manuale-e-bot": _UTENTE,
    "cashout-globale": _UTENTE, "chiusura-fuori-app": _UTENTE,
    "chiusura-fuori-app-ridotta": _UTENTE, "rifiuti-betfair": _GUASTO,
    "timeout-dopo-accettazione": _GUASTO, "chiusura-abbinata-in-parte": _GUASTO,
    "selezione-aggiuntiva": _UGUALE + " (`requireSelection` acceso di serie dal 25/09)",
    "proposta-approvata": _INIETTATO, "proposta-scaduta": _INIETTATO,
    "proposta-anomalia-effimera": _INIETTATO, "combos-automatiche": _INIETTATO,
    "combos-gamba-automatica": _INIETTATO,
}
for _b in ("safe_base", "safe_esatto", "safe_punta"):
    SCENARI_SCARTATI[_b] = dict(_SAFE_CALCIO_SCARTATI)
for _b in ("tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing"):
    SCENARI_SCARTATI[_b] = {
        "dry-run": "nessun ordine raggiunge il mercato per costruzione",
        "bot-fermo": _UTENTE, "rifiuti-betfair": _GUASTO, "feed-stantio": _GUASTO,
        "riavvio": _GUASTO, "catalogo-assente": _GUASTO,
        "chiusura-abbinata-in-parte": _GUASTO, "chiudi-ora": _UTENTE,
        "uscite-manuali-firmate": _UTENTE,
        "soldi-veri-prova": "terza rete del runner: nessun ordine reale per costruzione",
    }
# 08/10 (cantiere 6): gli scenari di certificazione dei setup di tennis_pro coi
# nomi dei giocatori sono `base` col controllo-chiave del setup: non una variante
for _s in ("pro-fade-dopo-break", "pro-transizione-di-set", "pro-break-point"):
    SCENARI_SCARTATI["tennis_pro"][_s] = (
        _UGUALE + " (e' `base` col controllo-chiave di un setup del pro: certificazione)")

#: i bot di produzione che NON hanno ancora la cronologia degli ordini col codice
#: di produzione (vuoto = tutti ce l'hanno). bot -> motivo (la UI lo mostra).
SENZA_CRONOLOGIA: Dict[str, str] = {}

#: le etichette dei bot per il trader
ETICHETTE_BOT: Dict[str, str] = {
    "mike": "Mike (Under 3,5 + copertura)",
    "omega": "Omega (Correct Score)",
    "safe_base": "Safe Base",
    "safe_esatto": "Safe Risultato Esatto",
    "safe_punta": "Safe Punta",
    "scalper_calcio": "Scalper calcio",
    "safe_tennis": "Safe tennis",
    "tennis_scalper": "Tennis Scalper",
    "tennis_pro": "Tennis Pro",
    "tennis_flb": "Tennis FLB",
    "tennis_swing": "Tennis Swing",
}


def _chiave(r: Dict[str, Any]) -> str:
    # 07/10 sera: l'identita' dell'ordine e' ``_ordine`` (id flumine) quando c'e':
    # un ``replace_order`` crea un ordine nuovo con lo STESSO ref del vecchio
    if r.get("_ordine"):
        return "o:" + str(r["_ordine"])
    return str(r.get("client_order_ref") or r.get("bet_id") or id(r))


def cronologia(righe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Le righe dello specchio (in ordine di scrittura) ridotte ai CAMBI di
    stato di ogni ordine, ordinate per istante. PURA."""
    ultimo: Dict[str, tuple] = {}
    out: List[Dict[str, Any]] = []
    for r in righe or []:
        if not isinstance(r, dict) or r.get("_ms") is None:
            continue
        k = _chiave(r)
        firma = tuple(r.get(c) for c in _CAMPI_STATO)
        if ultimo.get(k) == firma:
            continue
        ultimo[k] = firma
        out.append(dict(r))
    out.sort(key=lambda x: int(x["_ms"]))
    return out


# ---------------------------------------------------------------------------
# il catalogo (registro -> UI)
# ---------------------------------------------------------------------------
def scenari_del_bot(nome: str) -> List[Dict[str, Any]]:
    """Gli scenari del REGISTRO applicabili a una partita registrata, nell'ordine
    del registro, con famiglia/modalita'/etichetta. Quelli scartati restano fuori
    (motivo in ``SCENARI_SCARTATI``); uno non classificato resta fuori e lo
    nomina il test di contratto."""
    from .registro_bot import bot as _bot

    registrati = _bot(nome).elenco_scenari()
    tavola = SCENARI_APPLICABILI.get(nome, {})
    out: List[Dict[str, Any]] = []
    for sc, descr in registrati.items():
        if sc not in tavola:
            continue
        famiglia, modalita, nota = tavola[sc]
        out.append({"scenario": sc, "famiglia": famiglia, "modalita": modalita,
                    "etichetta": "%s (%s)" % (famiglia, "prova" if modalita == PROVA
                                               else "soldi veri simulati"),
                    "nota": nota, "descrizione": str(descr)[:400]})
    return out


def non_classificati(nome: str) -> List[str]:
    """Gli scenari del registro che non sono ne' applicabili ne' scartati."""
    from .registro_bot import bot as _bot

    noti = set(SCENARI_APPLICABILI.get(nome, {})) | set(SCENARI_SCARTATI.get(nome, {}))
    return [sc for sc in _bot(nome).elenco_scenari() if sc not in noti]


def accetta_argomento(funzione: Callable[..., Any], nome: str) -> bool:
    """La funzione di replay dichiara l'argomento ``nome`` nella sua firma?"""
    try:
        return nome in inspect.signature(funzione).parameters
    except (TypeError, ValueError):
        return False


def catalogo_del_bot(nome: str, *, con_parametri: bool = True) -> Dict[str, Any]:
    """La voce di catalogo di UN bot: sport, etichetta, scenari (ciascuno con i
    suoi parametri e default), e se accetta ``clic_ms``. Un catalogo che non si
    puo' costruire si DICHIARA (``errore``), mai inventato."""
    from .registro_bot import bot as _bot

    reg = _bot(nome)
    voce: Dict[str, Any] = {
        "bot": nome, "sport": reg.sport, "etichetta": ETICHETTE_BOT.get(nome, nome),
        "descrizione": reg.descrizione, "scenari": [], "clic_ms": False,
        "disattivato": SENZA_CRONOLOGIA.get(nome),
        # 08/10: i mercati che servono al bot (registro): la UI del Replay Tennis
        # disabilita <<Applica>> se la partita non li ha registrati
        "mercati": list(getattr(reg, "mercati", ()) or ()),
    }
    try:
        funzione = reg.funzione_replay()
        voce["clic_ms"] = bool(funzione is not None and accetta_argomento(funzione, "clic_ms"))
    except Exception as ex:  # noqa: BLE001 - modulo non importabile: lo si dice
        voce["disattivato"] = "replay non importabile: %s" % str(ex)[:160]
        return voce
    cat_f = None
    if con_parametri:
        try:
            cat_f = reg.funzione_parametri()
        except Exception as ex:  # noqa: BLE001 - catalogo non (ancora) esposto
            voce["errore_parametri"] = str(ex)[:300]
    for sc in scenari_del_bot(nome):
        sc = dict(sc)
        sc["parametri"] = []
        if cat_f is not None:
            try:
                sc["parametri"] = list(cat_f(sc["scenario"]))
            except Exception as ex:  # noqa: BLE001
                sc["errore_parametri"] = "%s: %s" % (type(ex).__name__, str(ex)[:200])
        voce["scenari"].append(sc)
    return voce


def catalogo() -> List[Dict[str, Any]]:
    """Il catalogo di TUTTI i bot del registro (ordine del registro)."""
    from .registro_bot import elenco

    return [catalogo_del_bot(b.nome) for b in elenco()]


def catalogo_ts(cat: Optional[List[Dict[str, Any]]] = None) -> str:
    """Il file TypeScript del catalogo (``frontend/src/lib/replayBotCatalogo.ts``).
    GENERATO: chi lo modifica a mano lo vede rifiutato dal test di contratto."""
    dati = cat if cat is not None else catalogo()
    corpo = json.dumps(dati, indent=2, ensure_ascii=True, sort_keys=False)
    return (
        "// ============================================================================\n"
        "// FILE GENERATO - NON MODIFICARE A MANO.\n"
        "// Origine: Betfair/stream/backtest/applica_bot.py (catalogo dal registro del\n"
        "// banco, `registro_bot`, e dai moduli di replay: `parametri_modificabili`).\n"
        "// Rigenera: python -m Betfair.stream.backtest.applica_bot --catalogo-ts \\\n"
        "//     > frontend/src/lib/replayBotCatalogo.ts\n"
        "// Il test Betfair/stream/tests/test_applica_bot_tutti_2026_10_07.py e' rosso se\n"
        "// questo file non e' allineato al registro.\n"
        "// ============================================================================\n"
        "import type { CatalogoBot } from '@/lib/replayBot';\n\n"
        "export const CATALOGO_BOT: ReadonlyArray<CatalogoBot> = " + corpo + ";\n")


# ---------------------------------------------------------------------------
# la cartella delle registrazioni della partita
# ---------------------------------------------------------------------------
def _ha_registrazione(cartella: str, event_id: str) -> bool:
    return os.path.isfile(os.path.join(cartella, str(event_id), "%s.raw.jsonl" % event_id))


def cartella_della_partita(reg: Any, event_id: str, data_dir: Optional[str]) -> str:
    """Dove sta la registrazione della partita. Calcio: ``DATA_DIR``. Tennis: la
    cartella che ha il raw col MERCATO del bot (``risolvi_cartella_tennis``);
    se nessuna lo ha, quella di sempre (l'errore lo da' ``esegui``)."""
    if reg.sport != "tennis":
        return data_dir or reg.cartella()
    cartella, _errore = risolvi_cartella_tennis(reg, event_id, data_dir)
    return cartella


def _cartella_come_prima(reg: Any, event_id: str, data_dir: Optional[str]) -> str:
    """La risoluzione di prima dell'08/10 (solo cartelle-giorno numeriche): resta
    la PRIMA scelta, cosi' le partite col Match Odds tornano la stessa cartella."""
    if data_dir:
        if not _ha_registrazione(data_dir, event_id):
            giorno = _giorno_che_contiene(data_dir, event_id)
            if giorno:
                return giorno
        return data_dir
    base = reg.cartella()
    if _ha_registrazione(base, event_id):
        return base
    radice = os.path.dirname(base) if os.path.basename(base).isdigit() else base
    return _giorno_che_contiene(radice, event_id) or base


def _giorno_che_contiene(radice: str, event_id: str) -> Optional[str]:
    if not os.path.isdir(radice):
        return None
    for d in sorted((x for x in os.listdir(radice) if x.isdigit()), reverse=True):
        c = os.path.join(radice, d)
        if _ha_registrazione(c, event_id):
            return c
    return None


def _radice_tennis(reg: Any, data_dir: Optional[str]) -> str:
    """Dove si cerca: la cartella data dal chiamante, altrimenti la RADICE del
    recorder (il registro da' il giorno piu' recente: si risale di uno)."""
    if data_dir:
        return data_dir
    base = reg.cartella()
    return os.path.dirname(base) if os.path.basename(base).isdigit() else base


def tipi_mercato_del_raw(percorso: str) -> List[str]:
    """I ``marketType`` delle ``marketDefinition`` del raw (la fonte del banco),
    in ordine alfabetico. Vuoto = il raw non dichiara nessun mercato."""
    return sorted({str(e.get("market_type")) for e in esiti_dal_raw(percorso).values()
                   if e.get("market_type")})


_NOMI_MERCATO = {"MATCH_ODDS": "Match Odds", "SET_BETTING": "Set Betting"}


def _cartelle_col_punteggio(radice: str, event_id: str) -> List[str]:
    out: List[str] = []
    if not os.path.isdir(radice):
        return out
    nome = "%s.score.jsonl" % event_id
    for dirpath, dirnames, filenames in os.walk(radice):
        dirnames.sort()
        if os.path.basename(os.path.normpath(dirpath)) == str(event_id) and nome in filenames:
            out.append(os.path.dirname(os.path.normpath(dirpath)))
    return out


def _relativa(radice: str, cartella: str) -> str:
    try:
        r = os.path.relpath(cartella, radice)
    except ValueError:
        return cartella
    return cartella if r == "." else r


def risolvi_cartella_tennis(reg: Any, event_id: str,
                            data_dir: Optional[str]) -> Tuple[str, Optional[str]]:
    """08/10 (Replay Tennis, caso 35797566): la cartella del tennis che ha
    ``<id>/<id>.raw.jsonl`` CON il mercato che serve al bot (``reg.mercati``,
    MATCH_ODDS per i bot tennis). Si cerca in TUTTE le sottocartelle della
    radice con la stessa visita dell'importatore del Replay Tennis
    (``tennis_replay.importa.trova_registrazioni``): ``20260707`` col Match Odds,
    ``setbetting_20260707`` col Set Betting. Il banco tennis apre UNA cartella
    (nessuna fusione di piu' raw): si sceglie quella col mercato del bot.

    Ordine: (1) la cartella di prima (``_cartella_come_prima``) se il suo raw ha
    il mercato del bot - le partite col Match Odds tornano la STESSA cartella;
    (2) la prima, nell'ordine della visita, col mercato del bot; (3) un raw che
    non dichiara nessun mercato (nessuna ``marketDefinition``: non si puo' dire
    che manchi). Altrimenti torna ``(cartella di prima, errore esatto)``."""
    from ..tennis_replay.importa import trova_registrazioni

    richiesti = [m for m in (getattr(reg, "mercati", ()) or ()) if m] or ["MATCH_ODDS"]
    prima = _cartella_come_prima(reg, event_id, data_dir)
    radice = _radice_tennis(reg, data_dir)
    candidati: List[str] = []
    if _ha_registrazione(prima, event_id):
        candidati.append(os.path.normpath(prima))
    voce = trova_registrazioni([radice]).get(str(event_id)) if os.path.isdir(radice) else None
    for d in (voce or {}).get("dirs", []):
        if os.path.normpath(d) not in candidati:
            candidati.append(os.path.normpath(d))
    tipi_per_cartella: List[Tuple[str, List[str]]] = []
    for c in candidati:
        tipi_per_cartella.append(
            (c, tipi_mercato_del_raw(os.path.join(c, str(event_id), "%s.raw.jsonl" % event_id))))
    for c, tipi in tipi_per_cartella:
        if any(m in tipi for m in richiesti):
            return (prima if os.path.normpath(prima) == c else c), None
    for c, tipi in tipi_per_cartella:
        if not tipi:
            return (prima if os.path.normpath(prima) == c else c), None
    voluti = " / ".join(_NOMI_MERCATO.get(m, m) for m in richiesti)
    chi = "i bot tennis lavorano" if reg.sport == "tennis" else "il bot lavora"
    if tipi_per_cartella:
        registrati = ["%s (cartella %s)" % (", ".join(tipi), _relativa(radice, c))
                      for c, tipi in tipi_per_cartella]
        return prima, ("per la partita %s e' registrato solo il %s: %s sul %s, che non e' "
                       "stato registrato" % (event_id, "; ".join(registrati), chi, voluti))
    punteggi = _cartelle_col_punteggio(radice, event_id)
    if punteggi:
        return prima, ("registrazione senza flusso di mercato (solo punteggi) per la partita "
                       "%s in %s: nessun %s.raw.jsonl, il bot non ha prezzi su cui girare"
                       % (event_id, ", ".join(_relativa(radice, c) for c in punteggi),
                          event_id))
    return prima, ("nessuna registrazione della partita %s sotto %s: il bot si applica "
                   "solo alle partite registrate (Segui live con REC)" % (event_id, radice))


# ---------------------------------------------------------------------------
# l'esecuzione
# ---------------------------------------------------------------------------
def _clic(valore: Any) -> Optional[List[int]]:
    if valore is None:
        return None
    if not isinstance(valore, (list, tuple)):
        raise ValueError("clic_ms: attesa una lista di istanti (ms del banco)")
    out: List[int] = []
    for v in valore:
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError("clic_ms: istante non valido %r" % (v,))
        out.append(int(v))
    return sorted(out)


#: versione della forma dell'esito: la UI la confronta (un esito senza versione
#: viene da un worker del Backtest col codice VECCHIO: l'app non e' stata riavviata)
VERSIONE_ESITO = 2


def esiti_dal_raw(percorso: str) -> Dict[str, Dict[str, Any]]:
    """07/10 sera (REPLAY PROFESSIONALE): per ogni mercato della registrazione,
    dalle ``marketDefinition`` del RAW (la stessa fonte del banco): tipo,
    runner nell'ordine di Betfair con lo stato FINALE (WINNER/LOSER/REMOVED/
    ACTIVE), istante del primo book in gioco e della chiusura (``pt``), aliquota
    base del mercato. Serve alla UI per il regolamento delle posizioni e per
    l'evento <<chiusura del mercato>>. Cio' che il raw non dice resta None."""
    out: Dict[str, Dict[str, Any]] = {}
    if not percorso or not os.path.isfile(percorso):
        return out
    with open(percorso, "r", encoding="utf-8") as fh:
        for riga in fh:
            if "marketDefinition" not in riga:
                continue
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            pt = d.get("pt")
            for mc in d.get("mc") or []:
                md = mc.get("marketDefinition")
                if not md:
                    continue
                mid = str(mc.get("id"))
                e = out.setdefault(mid, {
                    "market_type": md.get("marketType"), "runners": {},
                    "ordine_runner": [], "stato": None, "in_gioco_ms": None,
                    "chiuso_ms": None, "aliquota": None, "vincitori": [],
                })
                e["stato"] = md.get("status")
                if md.get("marketBaseRate") is not None:
                    try:
                        e["aliquota"] = float(md.get("marketBaseRate")) / 100.0
                    except (TypeError, ValueError):
                        pass
                if md.get("inPlay") and e["in_gioco_ms"] is None and pt is not None:
                    e["in_gioco_ms"] = int(pt)
                if md.get("status") == "CLOSED" and e["chiuso_ms"] is None and pt is not None:
                    e["chiuso_ms"] = int(pt)
                runners = sorted((r for r in (md.get("runners") or []) if r.get("id") is not None),
                                 key=lambda r: (r.get("sortPriority") or 0))
                e["ordine_runner"] = [int(r["id"]) for r in runners]
                e["runners"] = {str(int(r["id"])): str(r.get("status") or "") for r in runners}
                e["vincitori"] = [int(r["id"]) for r in runners if r.get("status") == "WINNER"]
    return out


def _profitto_ordine(lato: str, abbinato: float, prezzo: float, stato_runner: str) -> float:
    """Il profitto di UNA scommessa a regolamento, con la formula e
    l'arrotondamento di flumine (``SimulatedOrder.profit``: al centesimo per
    ordine). Runner rimosso o non regolato: 0."""
    if abbinato <= 0:
        return 0.0
    if stato_runner == "WINNER":
        v = round(abbinato * (prezzo - 1.0), 2)
        return v if lato == "back" else -v
    if stato_runner == "LOSER":
        return -abbinato if lato == "back" else abbinato
    return 0.0


def conto_regolato(righe: List[Dict[str, Any]], esiti: Dict[str, Dict[str, Any]],
                   aliquota: Optional[float] = None) -> Dict[str, Any]:
    """Il P&L A REGOLAMENTO degli ordini del bot (ultima riga di ogni ordine:
    abbinato e prezzo medio) col risultato del mercato registrato: lordo per
    mercato come ``MercatoFlumine.pnl_betfair`` (profitti al centesimo per
    ordine, somma al centesimo), commissione per mercato sul netto vincente.
    I mercati senza runner WINNER/LOSER nel raw restano FUORI e si dichiarano.
    PURA (le stesse regole le rifa' la UI: ``replayOperazioni.contoRegolato``)."""
    ultima: Dict[str, Dict[str, Any]] = {}
    for r in righe or []:
        ultima[_chiave(r)] = r
    per_mercato: Dict[str, float] = {}
    non_regolati: List[str] = []
    for r in ultima.values():
        mid = str(r.get("market_id") or "")
        stati = (esiti.get(mid) or {}).get("runners") or {}
        if not any(v in ("WINNER", "LOSER") for v in stati.values()):
            if float(r.get("size_matched") or 0.0) > 0 and mid not in non_regolati:
                non_regolati.append(mid)
            continue
        prof = _profitto_ordine(str(r.get("side") or "").lower(),
                                float(r.get("size_matched") or 0.0),
                                float(r.get("average_price_matched") or 0.0),
                                stati.get(str(r.get("selection_id")), ""))
        per_mercato[mid] = round(per_mercato.get(mid, 0.0) + round(prof, 2), 2)

    def _aliq(m: str) -> float:
        if aliquota is not None:
            return float(aliquota)
        a = (esiti.get(m) or {}).get("aliquota")
        return float(a) if a is not None else 0.05
    comm = {m: (round(v * _aliq(m), 2) if v > 0 else 0.0) for m, v in per_mercato.items()}
    return {"lordo": round(sum(per_mercato.values()), 2),
            "commissione": round(sum(comm.values()), 2),
            "netto": round(sum(round(v - comm[m], 2) for m, v in per_mercato.items()), 2),
            "mercati": {m: round(v, 2) for m, v in per_mercato.items()},
            "mercati_non_regolati": non_regolati}


def conto_flumine(righe: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Il lordo per mercato come lo ha regolato FLUMINE nel banco
    (``_profitto_flumine`` sull'ultima riga di ogni ordine, scritto da
    ``SpecchioOrdini`` quando il mercato e' stato regolato). None se nessun
    ordine e' stato regolato da flumine (es. lo scalper: la sessione finisce
    prima del regolamento): allora vale solo il conto dalle righe."""
    ultima: Dict[str, Dict[str, Any]] = {}
    for r in righe or []:
        ultima[_chiave(r)] = r
    per_mercato: Dict[str, float] = {}
    visti = 0
    for r in ultima.values():
        if r.get("_profitto_flumine") is None:
            continue
        visti += 1
        mid = str(r.get("market_id") or "")
        per_mercato[mid] = round(per_mercato.get(mid, 0.0) + float(r["_profitto_flumine"]), 2)
    if not visti:
        return None
    return {"lordo": round(sum(per_mercato.values()), 2),
            "mercati": {m: round(v, 2) for m, v in per_mercato.items()},
            "ordini_regolati": visti}


_PNL_NOTA = re.compile(r"P&L del replay: lordo ([+-]?\d+\.\d+) \| commissione (\d+\.\d+) "
                       r"\((\d+(?:\.\d+)?)%\) \| NETTO ([+-]?\d+\.\d+)")


def conto_dichiarato(ref: Any) -> Optional[Dict[str, Any]]:
    """Il P&L che il REFERTO del bot dichiara (per il confronto della UI):
    ``stats_finali['media_conto']`` (media under, per ciclo) oppure la riga
    <<P&L del replay: lordo .. | commissione .. | NETTO ..>> dei moduli di
    replay. None se il bot non lo dichiara (lo si dice, non si inventa)."""
    sf = getattr(ref, "stats_finali", None) or {}
    mc = sf.get("media_conto") if isinstance(sf, dict) else None
    if isinstance(mc, dict) and mc.get("lordo") is not None:
        return {"fonte": "media_conto", "metodo": "cicli",
                "lordo": float(mc["lordo"]), "commissione": float(mc.get("commissione") or 0.0),
                "netto": float(mc.get("netto") or 0.0),
                "aliquota": float(mc.get("aliquota") or 0.0),
                "cicli_esito_ignoto": int(mc.get("cicli_esito_ignoto") or 0)}
    for n in getattr(ref, "note", []) or []:
        m = _PNL_NOTA.search(str(n))
        if m:
            return {"fonte": "nota", "metodo": "regolamento",
                    "lordo": float(m.group(1)), "commissione": float(m.group(2)),
                    "aliquota": float(m.group(3)) / 100.0, "netto": float(m.group(4)),
                    "testo": str(n)[:300]}
    return None


def _json_sicuro(x: Any) -> Any:
    """Una copia che ``json.dumps`` accetta (numeri, testi, liste, dizionari)."""
    if isinstance(x, dict):
        return {str(k): _json_sicuro(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_sicuro(v) for v in x]
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    return str(x)


def cicli_dichiarati(ref: Any) -> Optional[List[Dict[str, Any]]]:
    """07/10 sera: i CICLI come li riepiloga il bot nel suo referto (dati, non
    note): oggi la media under (``stats_finali['media_riepilogo_cicli']``) con
    l'origine di ogni ciclo (clic o rientro automatico, ``media_origini_cicli``).
    None se il bot non li dichiara: allora la UI li ricava dagli ordini."""
    sf = getattr(ref, "stats_finali", None) or {}
    cicli = sf.get("media_riepilogo_cicli") if isinstance(sf, dict) else None
    if not isinstance(cicli, list):
        return None
    origini = sf.get("media_origini_cicli") or []
    out: List[Dict[str, Any]] = []
    for c in cicli:
        c = dict(c)
        o = next((x for x in origini if int(x.get("ciclo") or 0) == int(c.get("ciclo") or -1)), None)
        c["origine"] = (o or {}).get("origine")
        c["clic"] = (o or {}).get("clic")
        c["prima_punta_ordine"] = (o or {}).get("ordine")
        c["prima_punta_ms"] = (o or {}).get("ms")
        out.append(_json_sicuro(c))
    return out


def clic_dichiarati(ref: Any) -> Optional[List[Dict[str, Any]]]:
    """07/10 sera: ogni clic <<Attiva adesso>> con il suo esito per il banco
    (eseguito / rifiutato col motivo / mai letto) e la prima punta che ne e'
    nata (``stats_finali['media_clic']``). None se il bot non ha clic."""
    sf = getattr(ref, "stats_finali", None) or {}
    clic = sf.get("media_clic") if isinstance(sf, dict) else None
    return _json_sicuro(clic) if isinstance(clic, list) else None


def conferme(note: List[str], dal_ms: Optional[int],
             clic_ms: Optional[List[int]]) -> Dict[str, Any]:
    """07/10 sera (onesta' del clic): che cosa il BOT ha davvero ricevuto. Ogni
    modulo di replay scrive nel referto la riga ``ACCENSIONE ... (ms <dal_ms>``
    quando accende il bot a ``dal_ms``; la media under scrive ``ATTIVA ADESSO
    clic clic-N-<ms>`` per ogni clic mandato alla sessione. Se la riga non c'e'
    la UI mostra l'avviso: il bot NON ha avuto quell'istante."""
    testi = [str(n) for n in note or []]

    def _clic_visto(ms: int) -> bool:
        return any(t.startswith("ATTIVA ADESSO clic clic-") and ("-%d " % ms) in t
                   for t in testi)
    dal = None
    if dal_ms is not None:
        dal = bool(any(t.startswith("ACCENSIONE") and str(dal_ms) in t for t in testi)
                   or _clic_visto(int(dal_ms)))
    clic = [{"ms": int(c), "ricevuto": _clic_visto(int(c))} for c in (clic_ms or [])]
    return {"dal_ms": dal, "clic_ms": clic}


def esegui(params: Dict[str, Any], data_dir: Optional[str] = None) -> Dict[str, Any]:
    """Esegue lo scenario chiesto e torna ``{"righe": [...], "note": [...],
    "parametri_usati": {...}, "dal_ms": ..., ...}``. Solleva ValueError su una
    richiesta non valida (bot o scenario fuori elenco, parametro non ammesso,
    registrazione assente)."""
    from . import minimi_banco as _MB
    from . import varianti_bot as VB
    from .certifica import _freni_da_banco
    from .registro_bot import REGISTRO

    nome = str(params.get("bot") or "")
    scenario = str(params.get("scenario") or "")
    event_id = str(params.get("event_id") or "")
    if nome not in REGISTRO or nome not in SCENARI_APPLICABILI:
        raise ValueError("bot non applicabile al replay: %r (disponibili: %s)"
                         % (nome, ", ".join(sorted(SCENARI_APPLICABILI))))
    if nome in SENZA_CRONOLOGIA:
        raise ValueError("il bot %s non ha ancora la cronologia degli ordini col codice di "
                         "produzione: %s" % (nome, SENZA_CRONOLOGIA[nome]))
    applicabili = {s["scenario"]: s for s in scenari_del_bot(nome)}
    if scenario not in applicabili:
        motivo = SCENARI_SCARTATI.get(nome, {}).get(scenario)
        raise ValueError("scenario non disponibile per %s: %r%s" % (
            nome, scenario, (" (%s)" % motivo) if motivo else ""))
    if not event_id:
        raise ValueError("event_id mancante")
    reg = REGISTRO[nome]
    if reg.sport == "tennis":
        # 08/10: la cartella col MERCATO del bot, oppure l'errore esatto (mai
        # <<registrazione assente>> quando la partita e' registrata)
        cartella, errore_cartella = risolvi_cartella_tennis(reg, event_id, data_dir)
        if errore_cartella:
            raise ValueError(errore_cartella)
    else:
        cartella = cartella_della_partita(reg, event_id, data_dir)
    if not _ha_registrazione(cartella, event_id):
        raise ValueError("registrazione assente per la partita %s in %s: il bot si "
                         "applica solo alle partite registrate (Segui live con REC)"
                         % (event_id, cartella))
    funzione = reg.funzione_replay()
    # il catalogo dello scenario: le sostituzioni si controllano QUI (messaggio
    # chiaro prima di partire) e di nuovo nella funzione di replay. Senza
    # sostituzioni un catalogo non (ancora) esposto non blocca la prova: il
    # referto lo dichiara.
    sostituzioni_chieste = params.get("parametri") or None
    note_catalogo: List[str] = []
    try:
        catalogo_sc = list(reg.funzione_parametri()(scenario))
    except ValueError as ex:
        if sostituzioni_chieste:
            raise
        catalogo_sc = []
        note_catalogo.append("parametri di serie non elencati: %s" % ex)
    sostituzioni = VB.valida(catalogo_sc, sostituzioni_chieste)
    dal_ms = VB.controlla_dal_ms(params.get("dal_ms"))
    clic_ms = _clic(params.get("clic_ms"))
    argomenti: Dict[str, Any] = dict(reg.argomenti_applica)
    for chiave_arg, valore in (("parametri", sostituzioni or None), ("dal_ms", dal_ms),
                               ("clic_ms", clic_ms)):
        if valore is None:
            continue
        if not accetta_argomento(funzione, chiave_arg):
            raise ValueError("la funzione di replay di %s non accetta ancora `%s`: "
                             "variante non applicabile" % (nome, chiave_arg))
        argomenti[chiave_arg] = valore
    # lo STESSO ambiente di ``certifica`` (``_lavora``): registro dell'exchange
    # simulato azzerato, freni e ambiente del banco (soldi veri simulati serviti)
    _MB.REGISTRO.azzera()
    with _freni_da_banco():
        ref = funzione(event_id, data_dir=cartella, scenario=scenario, ogni_ms=OGNI_MS,
                       **argomenti)
    note = list(getattr(ref, "note", []) or []) + note_catalogo
    if any(str(n).startswith("registrazione assente") for n in note):
        raise ValueError("registrazione assente per la partita %s in %s: il bot si "
                         "applica solo alle partite registrate (Segui live con REC)"
                         % (event_id, cartella))
    righe = cronologia(list(getattr(ref, "ordini_specchio", []) or []))
    esiti = esiti_dal_raw(os.path.join(cartella, str(event_id), "%s.raw.jsonl" % event_id))
    violazioni = [getattr(v, "codice", str(v)) for v in (getattr(ref, "violazioni", []) or [])]
    usati = VB.parametri_usati(catalogo_sc, sostituzioni)
    cambiati = {k: v for k, v in sostituzioni.items()
                if v != next((x["default"] for x in catalogo_sc if x["chiave"] == k), None)}
    return {
        "bot": nome, "scenario": scenario, "event_id": event_id,
        "sport": reg.sport,
        "etichetta": applicabili[scenario]["etichetta"],
        "modalita": applicabili[scenario]["modalita"],
        "righe": righe,
        "ordini": len({_chiave(r) for r in righe}),
        "violazioni": violazioni,
        # 07/10 sera: le note intere (prima 12 da 300 caratteri: il ciclo 1 spariva
        # e il 3 era troncato); il CONTENUTO pero' passa dai campi strutturati
        "note": [str(n)[:2000] for n in note[-120:]],
        "parametri_usati": usati,
        "parametri_cambiati": cambiati,
        "dal_ms": dal_ms,
        # cosa vede il bot all'accensione (la nota del suo modulo di replay)
        "accensione": next((str(n)[:600] for n in note if str(n).startswith("ACCENSIONE")),
                           None),
        "clic_ms": clic_ms,
        # 07/10 sera (REPLAY PROFESSIONALE)
        "versione": VERSIONE_ESITO,
        # la richiesta COME L'HA RICEVUTA il banco (la UI la confronta con cio'
        # che ha mandato: se manca qualcosa, il percorso l'ha persa)
        "richiesta": {"dal_ms": dal_ms, "clic_ms": clic_ms,
                      "parametri": dict(sostituzioni_chieste or {})},
        # che cosa il BOT ha davvero ricevuto (righe ACCENSIONE / ATTIVA ADESSO)
        "conferme": conferme(note, dal_ms, clic_ms),
        # risultato dei mercati dal raw: regolamento e chiusura sul ladder
        "esiti_mercati": esiti,
        # P&L a regolamento dagli ordini (stesse regole della UI) e quello che
        # il referto del bot dichiara (per il confronto al centesimo)
        "conto_banco": conto_regolato(righe, esiti),
        "conto_flumine": conto_flumine(righe),
        "conto_dichiarato": conto_dichiarato(ref),
        # cicli e clic come DATI (le note sono tagliate: non portano contenuto)
        "cicli_bot": cicli_dichiarati(ref),
        "clic_bot": clic_dichiarati(ref),
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Applica bot: catalogo per la UI")
    p.add_argument("--catalogo-ts", action="store_true",
                   help="stampa il file TS del catalogo (frontend/src/lib/replayBotCatalogo.ts)")
    p.add_argument("--catalogo-json", action="store_true", help="stampa il catalogo in JSON")
    a = p.parse_args(argv)
    if a.catalogo_ts:
        sys.stdout.write(catalogo_ts())
        return 0
    if a.catalogo_json:
        sys.stdout.write(json.dumps(catalogo(), indent=2, ensure_ascii=True))
        return 0
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
