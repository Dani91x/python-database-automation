# -*- coding: utf-8 -*-
"""I QUATTRO BOT TENNIS SULLE REGISTRAZIONI VERE — il replay col motore Betfair.

Fa rivivere a UNO dei quattro bot tennis (`tennis_scalper`, `tennis_pro`,
`tennis_flb`, `tennis_swing`) una partita registrata, tick per tick, coi prezzi
veri di Betfair, e a ogni giro verifica la CONDOTTA contro
`Betfair/stream/tennis_live/certificazione_bot.py`. Non misura il profitto:
misura la condotta (`PROCESSO_STANDARD_BOT.md` gradino 3).

LA CATENA, e nessun passo e' saltato:

    raw registrato  `~/Desktop/tennis_rec/<giorno>/<id>/<id>.raw.jsonl`
      -> flumine    `FlumineSimulation` + `HistoricalStream` (banco comune:
                    UN solo `SimulatedMiddleware`, tetti di flumine aperti,
                    `simulation_available_prices=False` = fill solo sul volume
                    davvero scambiato, coda rispettata)
      -> `tennis_runner._instantiate_bot` VERO: e' la funzione che il runner di
         produzione usa per armare un bot dal control-row (preset TENNIS_PARAMS
         dello scalper, `dry_run` dalla modalita', tetti di esposizione,
         `_scope_to_market`, carry-over delle stats)
      -> il PUNTEGGIO entra come in produzione: `parse_tennis_scores` (la stessa
         funzione di `score_and_now_worker`) sul sidecar `<id>.score.jsonl`,
         assegnato a `strat.score` / `strat.point_pressure` alla cadenza VERA
         del worker (`TENNIS_SCORE_POLL_SEC`, 2 s di tempo di mercato)
      -> ordini VERI su flumine (`market.place_order`), con il BET DELAY del
         `marketDefinition` streamato (flumine trattiene il pacchetto finche'
         `elapsed > place_latency + betDelay`, `orderpackage.py:73-77`) e la
         `place_latency` del PAPER TENNIS di produzione
         (`TENNIS_PAPER_LATENCY_MS`, 600 ms)
      -> lo SPECCHIO vero: `tennis_live_order_worker._mirror_order` e
         `_position_row` girati sul blotter, cosi' il referto giudica anche le
         righe che la UI vedrebbe (§6.5)

-----------------------------------------------------------------------------
TRE DICHIARAZIONI, perche' un banco che non le fa e' peggio di nessun banco
-----------------------------------------------------------------------------

1. IL CATALOGO NON C'E'. Nel raw dello stream non esistono i NOMI dei runner
   (`marketDefinition.runners` porta solo `id` e `sortPriority`): in produzione
   i nomi arrivano da `listMarketCatalogue` (`tennis_runner._resolve_market` ->
   `name_to_sel`). `tennis_pro` ne ha BISOGNO per mappare il punteggio IPS sulla
   selezione: senza, `_sel_of` non trova nessuno e il bot non apre MAI. Qui la
   mappa si DICHIARA: `--nomi` esplicito, oppure la cache `_names.json` che i
   grid runner scrivono accanto alle registrazioni (`lab_grid_score.py:86-118`).
   Lo scenario `catalogo-assente` mostra che cosa succede senza.

2. IL PUNTEGGIO HA L'OROLOGIO DEL POLL, NON DEL MERCATO. Il sidecar `.score.jsonl`
   timbra ogni riga con `time.time()` LOCALE al momento del poll IPS
   (`tennis_score.py:260-262`), mentre i book portano il `publish_time` di
   Betfair: fra i due c'e' la latenza HTTP dell'IPS piu' l'intervallo di poll
   (2 s). Qui i punteggi entrano confrontando quei due orologi, ed e' la stessa
   approssimazione dichiarata da `backtest_pro.py:73-74`: le condizioni dei bot
   valgono su scala set/game/servizio, non per il micro-timing sub-secondo.

3. IL CICLO DI VITA DEGLI ORDINI E' DI FLUMINE, NON NOSTRO. Il bot chiama
   `market.place_order`, che in flumine e' ASINCRONA: il pacchetto entra in
   `handler_queue` e viene eseguito quando l'orologio di mercato ha superato
   `place_latency + betDelay`. E' esattamente cio' che succede in produzione
   (il bot non si blocca sulla REST: e' il `OrderStream` a portargli l'esito),
   quindi qui NON si usa `MercatoFlumine.attendi_esecuzione` — si lascia fare
   a `MotoreReplay._a_flumine`, che chiama `_check_pending_packages` a ogni book
   come fa `FlumineSimulation.run`.

Uso:
    python -m Betfair.stream.backtest.certifica tennis_flb 35794049
    python -m Betfair.stream.backtest.certifica tennis_flb 35794049 --scenari tutti
    python -m Betfair.stream.tennis_live.tools.replay_bot tennis_flb 35794049

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import sys
from bisect import bisect_right
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import certificazione_bot as CERT
from ...trading import minimi_it as _MINIMI_IT
from ...backtest import chiusura_parziale as CP
from ...backtest import uscite_manuali as UM
from ...backtest import varianti_bot as VB
from ..tennis_recorder import default_record_dir

logger = logging.getLogger(__name__)

# la registrazione di riferimento: Sinner - Struff, 07/07/2026, COMPLETE 99.1 %,
# 8609 righe di raw, sidecar punteggi presente e `_names.json` col catalogo.
EVENTO_DI_RIFERIMENTO = "35794049"

# i mercati che i quattro bot usano: uno solo, il MATCH_ODDS (dossier §4)
MERCATI = ("MATCH_ODDS",)

# D3 (24/09): lo scenario del "chiudi ora" dell'utente (controllo B9)
SCENARIO_CHIUDI_ORA = "chiudi-ora"

# 28/09 (CANTIERE N3): gli scenari a uscite MANUALI (interruttore spento, il
# default di produzione dopo ogni avvio). Tutti gli ALTRI scenari girano con
# le uscite AUTOMATICHE accese e lo DICHIARANO nel referto (NOTA_USCITE_AUTO).
SCENARI_USCITE_MANUALI: Tuple[str, ...] = UM.SCENARI
NOTA_USCITE_AUTO = ("SCENARIO DICHIARATO: uscite automatiche accese, e' la "
                    "condotta certificata (riga del bot con "
                    "`uscite_automatiche=True`, come la scrive l'interruttore "
                    "della UI su AUTOMATICHE)")


# 04/10 (CERTIFICAZIONE_TENNIS_PRO_SCALPER, punto 5): «SOLDI VERI» sul banco.
# Runner con il tetto LIVE, i trading control VERI del runner
# (`tennis_runner.aggiungi_controlli_ordini`: modalita' del bot, kill-switch,
# terza rete «Ordini reali»), il bot armato come lo arma il ponte e la scelta
# «Ordini reali» dichiarata (`modo_ordini.dichiara_per_banco`). Il client REALE e'
# il `ClienteLiveBanco` del banco (stessa esecuzione simulata, venue non
# simulata: nessun soldo), quello paper il client simulato del banco.
#   scenario -> (modalita' della riga del bot, «Ordini reali» di questo avvio)
SCENARI_SOLDI_VERI: Dict[str, Tuple[str, str]] = {
    "soldi-veri": ("live", "live"),          # ordini sul client REALE
    "soldi-veri-prova": ("live", "paper"),   # nessun ordine reale: terza rete
    "soldi-veri-paper": ("paper", "live"),   # bot in prova: client simulato
}


def uscite_automatiche_scenario(scenario: str) -> bool:
    """Il valore di `uscite_automatiche` che lo scenario scrive nella riga del
    bot (`tennis_bot_control`): lo legge `_instantiate_bot` con la funzione di
    produzione `auto_mode.uscite_automatiche_bot`."""
    return scenario not in SCENARI_USCITE_MANUALI


# ---------------------------------------------------------------------------
# GLI SCENARI — cambiano SOLO parametri, freschezza del feed o guasti iniettati.
# Mai la partita, mai i prezzi, mai la strategia (PROCESSO_STANDARD_BOT §6.7).
# ---------------------------------------------------------------------------
SCENARI_DESCRITTI: Dict[str, str] = {
    "base": "come gira in produzione: i parametri del preset, modalita' paper",
    "gate-aperto": (
        "SOLO le soglie di liquidita' e di banda allargate, per sollecitare i "
        "controlli su una partita in cui i default non entrano mai. La "
        "STRATEGIA non cambia: cambiano i numeri che l'utente puo' gia' "
        "cambiare dalla UI"),
    "dry-run": "il control chiede dry_run: nessun ordine deve raggiungere il mercato",
    "bot-fermo": (
        "a meta' partita il runner DISARMA il bot (`_disable_strategy` vero): "
        "le protezioni girano, le aperture no"),
    "rifiuti-betfair": (
        "un controllo di flumine RIFIUTA ogni piazzamento (`place_order` torna "
        "False, stato `Violation`): provoca il difetto 2 del catalogo, `res.ok` "
        "mai letto. Porta con se' i gate aperti di `gate-aperto`, altrimenti i "
        "bot che non tentano nessun ingresso non verrebbero mai rifiutati"),
    "feed-stantio": (
        "il punteggio smette di arrivare dopo il primo terzo della partita: "
        "`strat.score` resta quello vecchio, come in un blackout IPS"),
    "parziali": (
        "SOLO lo stake alzato: l'ordine non trova abbastanza coda e si abbina "
        "in parte, cosi' residuo e prezzo medio hanno un caso"),
    "riavvio": (
        "RIAVVIO A META' PARTITA, come lo fa il runner: a meta' si chiede il "
        "restart del framework e lo si concede SOLO a bot flat "
        "(`tennis_runner._strategy_is_flat`, il blotter e' l'unica fonte); poi "
        "il bot viene RI-ISTANZIATO con `_instantiate_bot` e il carry-over "
        "delle stats, esattamente come al rebuild dello stream"),
    "catalogo-assente": (
        "la mappa dei nomi NON viene dichiarata (limite 1 del banco): mostra "
        "che cosa perde `tennis_pro` senza `listMarketCatalogue`"),
    "live": (
        "la stessa partita in modalita' LIVE, col `dry_run` tolto come lo "
        "toglierebbe l'utente: gli ordini restano simulati da flumine (il banco "
        "gira su `FlumineSimulation`), ma i parametri sono quelli del percorso "
        "live — minimi e granularita' .it compresi — cosi' la blindatura di "
        "giurisdizione e' davvero verificata e la parita' paper/live misurabile"),
    # 23/09 (cancello C3): i gate di `gate-aperto` (senza, scalper e swing non
    # aprono mai su queste partite e non esisterebbe una chiusura da colpire)
    # piu' il guasto del banco comune.
    CP.SCENARIO: "i gate di `gate-aperto`, ma " + CP.DESCRIZIONE,
    # D3 (24/09): il "chiudi ora" dell'utente, per la STESSA via di produzione
    # (`chiusura_manuale.prendi_in_carico` + `avanza` alla cadenza del
    # `bot_control_worker`). Gate di `gate-aperto`, altrimenti non ci sarebbe
    # una posizione da chiudere. Lo giudica il controllo B9.
    SCENARIO_CHIUDI_ORA: (
        "i gate di `gate-aperto`; a meta' partita l'utente preme \"Chiudi\" "
        "sulla riga del bot: la richiesta passa da `chiusura_manuale` come in "
        "produzione, il bot esce con la SUA uscita e non rientra (B9)"),
    # N3 (28/09): le uscite MANUALI, con i gate di `gate-aperto` (senza, swing
    # e scalper non aprono mai e non esisterebbe un'uscita da proporre). Le
    # firme passano da `tennis_runner._aggiorna_uscite` alla cadenza del
    # `bot_control_worker`, come quelle della RPC `tennis_bot_approva_uscita`.
    UM.SCENARIO_MANUALI: "i gate di `gate-aperto`; " + UM.DESCRIZIONE_MANUALI,
    UM.SCENARIO_FIRMATE: "i gate di `gate-aperto`; " + UM.DESCRIZIONE_FIRMATE,
    # 04/10 (punto 5): la catena «soldi veri» del runner, coi gate di
    # `gate-aperto` (senza, scalper e swing non aprono e non ci sarebbe un
    # ordine da instradare). Lo giudica il controllo SV1.
    "soldi-veri": (
        "i gate di `gate-aperto`; bot acceso in SOLDI VERI e «Ordini reali» LIVE "
        "di questo avvio, runner col tetto LIVE e i suoi trading control veri: "
        "ogni ordine del bot parte sul client REALE del banco (`ClienteLiveBanco`, "
        "nessun soldo)"),
    "soldi-veri-prova": (
        "i gate di `gate-aperto`; bot in SOLDI VERI ma «Ordini reali» in PROVA: "
        "la terza rete (`ControlloModoOrdiniTennis`) ferma ogni apertura reale, "
        "nessun ordine reale eseguito"),
    "soldi-veri-paper": (
        "i gate di `gate-aperto`; bot in PROVA nel runner LIVE con «Ordini reali» "
        "LIVE: ordini sul client SIMULATO, stessa condotta di `soldi-veri` senza "
        "ordini veri (paper = specchio)"),
}


def parametri_scenario(scenario: str, bot: str) -> Dict[str, Any]:
    """I parametri che lo scenario cambia. SOLO numeri gia' esposti dalla UI."""
    if scenario in ("rifiuti-betfair", "live", CP.SCENARIO, SCENARIO_CHIUDI_ORA) \
            or scenario in UM.SCENARI or scenario in SCENARI_SOLDI_VERI:
        # ⚠️ IL CASO VA PROVOCATO, non sperato. Con i parametri di produzione
        # lo scalper e lo swing non tentano MAI un ingresso su questa partita:
        # il rifiuto non sarebbe nemmeno possibile e K2 resterebbe «non lo so»
        # proprio nello scenario che esiste per sollecitarlo; e senza nessun
        # ordine il percorso LIVE non esisterebbe, cioe' B8 — la blindatura dei
        # minimi .it, che e' money-critical — non verrebbe mai verificata
        # (§6.7). Si aprono percio' gli stessi gate di `gate-aperto`, e lo si
        # dichiara nel referto.
        return parametri_scenario("gate-aperto", bot)
    if scenario == "gate-aperto":
        # le soglie di liquidita' e le bande: sono i `min_matched` / `price_*`
        # che il dossier §4 elenca come parametri del bot, non regole.
        comuni = {"min_matched": 0.0, "min_total_matched": 0.0}
        per_bot = {
            # ⚠️ `inplay_tick_enabled` e' un parametro della MISSIONE dello
            # scalper (`one_tick_per_phase`, preset `TENNIS_PARAMS` del runner
            # standalone, esposto nella scheda del bot in
            # `frontend/src/lib/tennis.ts`): col default di produzione
            # (`one_tick_per_phase=True`, `inplay_tick_enabled=False`) un bot
            # armato su una partita GIA' IN-PLAY non apre MAI nulla e non lo
            # dice (difetto D13 del referto d'audit). Qui si apre per poter
            # sollecitare i controlli; e' un numero della UI, non una regola.
            "tennis_scalper": {"min_size": 0.0, "price_min": 1.01,
                               "price_max": 30.0, "min_flow": 0.0,
                               "warmup_ms": 0, "inplay_tick_enabled": True,
                               "runner_filter": "all"},
            "tennis_pro": {"min_book_size": 0.0, "price_min": 1.01,
                           "price_max": 30.0},
            "tennis_flb": {"min_lay_size": 0.0, "lay_max": 1.30},
            "tennis_swing": {"price_min": 1.01, "price_max": 30.0,
                             "zin": 1.0, "er_max": 1.0, "conf_ticks": 1},
        }
        out = dict(comuni)
        out.update(per_bot.get(bot, {}))
        return out
    if scenario == "parziali":
        # stake molto alto: la coda davanti non basta e l'ordine si abbina in
        # parte. Si cambia UN numero, quello che l'utente sceglie dalla UI.
        return {"stake": 400.0}
    return {}


# ---------------------------------------------------------------------------
# 08/10 (cantiere 6) - I SETUP DI tennis_pro CHE DIPENDONO DAI NOMI
# ---------------------------------------------------------------------------
# Uno scenario per setup, SOLO per tennis_pro. Non cambiano NESSUN parametro
# (`parametri_scenario` -> {}): e' la partita come gira in produzione, coi nomi
# dei giocatori del catalogo. Ognuno ha il suo CONTROLLO-CHIAVE della famiglia
# SP (`certificazione_bot`): sollecitato almeno una volta, oppure il referto
# dice NON ESERCITATO con la causa misurata dal banco sulla registrazione (mai
# un OK a vuoto). I controlli SP girano anche negli altri scenari del pro.
SCENARI_SETUP_PRO: Dict[str, str] = {
    "pro-fade-dopo-break": (
        "tennis_pro come in produzione, coi nomi del catalogo: certifica il FADE "
        "(back del favorito dopo un break precoce subito nel set, controllo SP1)"),
    "pro-transizione-di-set": (
        "tennis_pro come in produzione, coi nomi del catalogo: certifica la SET "
        "TRANSITION (ingresso su chi ha appena vinto il set, controllo SP2)"),
    "pro-break-point": (
        "tennis_pro come in produzione, coi nomi del catalogo: certifica il BREAK "
        "POINT (0-40/15-40, chi serve o chi riceve secondo la superficie, controllo SP3)"),
}
#: scenario -> il suo controllo-chiave
CONTROLLO_DEL_SETUP: Dict[str, str] = {
    "pro-fade-dopo-break": "SP1",
    "pro-transizione-di-set": "SP2",
    "pro-break-point": "SP3",
}
#: gli scenari di tennis_pro (registro del banco): quelli comuni + i tre setup
SCENARI_DESCRITTI_PRO: Dict[str, str] = {**SCENARI_DESCRITTI, **SCENARI_SETUP_PRO}


def scenari_del_bot(bot: str) -> Dict[str, str]:
    """Gli scenari del bot tennis (gli stessi del registro del banco)."""
    return dict(SCENARI_DESCRITTI_PRO if bot == "tennis_pro" else SCENARI_DESCRITTI)


# 08/10 (cantiere 6) - `gate-aperto`: le soglie che lo scenario cambia e che NON
# sono nel catalogo dei parametri che l'utente varia dalla UI
# (`parametri_modificabili`, la lista bianca). Sono DICHIARATE una per una con
# lo stato misurato sull'istanza vera del bot (`_instantiate_bot`): una chiave
# che il bot non legge non cambia niente, una che legge cambia la soglia. Non
# si toccano (cambierebbero i referti di tutti gli scenari coi gate aperti): la
# scelta e' dell'utente (referto del cantiere 6, "Decisioni per l'utente"). Il
# test di contratto diventa ROSSO se gate-aperto cambia una chiave che non e'
# ne' nel catalogo ne' qui, e se qui resta una chiave che non serve piu'.
_NON_LETTA = "chiave che il bot NON legge (nessun attributo): non cambia niente"
SOGLIE_FUORI_CATALOGO: Dict[str, Dict[str, str]] = {
    "tennis_scalper": {
        "min_matched": _NON_LETTA,
        "min_total_matched": "gia' 0 nel preset del runner: non cambia niente",
        "warmup_ms": "riscaldamento 30000 -> 0 ms (soglia tecnica, non nella scheda)",
    },
    "tennis_pro": {
        "min_book_size": "size minima al best 10 -> 0 EUR (non nella scheda)",
        "min_total_matched": _NON_LETTA,
        "price_min": "quota minima 1,08 -> 1,01 (la scheda espone solo la massima)",
    },
    "tennis_flb": {
        "min_lay_size": "size minima in banca 5 -> 0 EUR (non nella scheda)",
        "min_total_matched": _NON_LETTA,
    },
    "tennis_swing": {
        "conf_ticks": "tick di conferma 2 -> 1 (soglia del detector, non nella scheda)",
        "min_matched": "abbinato minimo del mercato 10000 -> 0 EUR (non nella scheda)",
        "min_total_matched": _NON_LETTA,
        "price_max": "quota massima 8 -> 30 (non nella scheda)",
        "price_min": "quota minima 1,08 -> 1,01 (non nella scheda)",
    },
}


def descrivi_parametri_scenario(scenario: str, bot: str) -> str:
    """Una riga per la testa del referto: che cosa cambia lo scenario rispetto
    alla produzione, separando cio' che e' nel catalogo della UI da cio' che non
    lo e' (dichiarato in `SOGLIE_FUORI_CATALOGO`)."""
    p = parametri_scenario(scenario, bot)
    if not p:
        return "nessuno (parametri di produzione)"
    voci = ", ".join("%s=%s" % (k, p[k]) for k in sorted(p))
    if scenario != "gate-aperto" and p == parametri_scenario("gate-aperto", bot):
        return "gli stessi di gate-aperto (%s)" % voci
    fuori = sorted(k for k in p if k in SOGLIE_FUORI_CATALOGO.get(bot, {}))
    return voci + (" | FUORI dal catalogo della UI (dichiarati): %s" % ", ".join(fuori)
                   if fuori else "")


def intestazione_certifica(bot: str, cartelle: Dict[str, str],
                           scenari: List[str]) -> List[str]:
    """08/10 (cantiere 6): le righe di TESTA del referto di `certifica` per un
    bot tennis: i nomi dei giocatori di ogni partita (presenti / ASSENTI, con la
    causa e i setup che senza nomi non si possono esercitare) e i parametri che
    ogni scenario cambia. ``cartelle`` = evento -> cartella risolta."""
    from ..tennis_runner import _BOT_REGISTRY

    righe: List[str] = []
    usa_nomi = bool(_BOT_REGISTRY.get(bot, (None, None, False))[2])
    if not usa_nomi:
        righe.append("nomi dei giocatori: non usati da %s (il runner non gli passa il "
                     "catalogo: `_BOT_REGISTRY`)" % bot)
    else:
        for ev in sorted(cartelle):
            st = stato_nomi(cartelle[ev], ev)
            if st["presenti"]:
                righe.append("nomi dei giocatori %s: PRESENTI (%s) da %s"
                             % (ev, ", ".join(st["nomi"]), st["file"]))
            else:
                righe.append("nomi dei giocatori %s: ASSENTI (%s): setup %s di %s NON "
                             "ESERCITABILI (controlli %s)"
                             % (ev, st["causa"], ", ".join(CERT.SETUP_CON_NOMI), bot,
                                ", ".join(sorted(CERT.SETUP_CERTIFICATI))))
    righe.append("parametri cambiati dallo scenario (il resto e' di produzione):")
    for sc in scenari:
        righe.append("  %s: %s" % (sc, descrivi_parametri_scenario(sc, bot)))
    return righe


def credenze_cp(cred: List[Dict[str, Any]],
                specchio: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Le credenze del bot tennis nella forma dei controlli CP.

    CHIUSA = lo stato che il bot dichiara chiuso (`STATI_CREDUTI_CHIUSI`, i nomi
    VERI dei quattro bot). I numeri di ogni uscita sono quelli della riga che la
    UI vedrebbe (`tennis_live_orders`, costruita da `_mirror_order` vero: chiave
    `average_price_matched`, non `avg_price_matched`). In coda una voce con TUTTE
    le righe dello specchio: un'uscita che il bot ha gia' smesso di seguire deve
    restare riconoscibile per CP1 (mai chiusa, mai coperta: CP2/CP3 la saltano).
    """
    per_id = {str(r.get("order_id") or ""): r for r in specchio or []}

    def _riga(o: Any) -> Dict[str, Any]:
        r = per_id.get(str(getattr(o, "id", "") or "")) or {}
        return {"ordine_id": str(getattr(o, "id", "") or ""), "bet_id": r.get("bet_id"),
                "size": r.get("size"), "price": r.get("price"),
                "status": r.get("status"),
                "size_matched": r.get("size_matched") if r else None,
                "size_remaining": r.get("size_remaining") if r else None,
                "avg_price_matched": r.get("average_price_matched") if r else None}

    out: List[Dict[str, Any]] = []
    for c in cred or []:
        out.append({
            "id": "%s%s" % (c.get("stato"), c.get("chiave")),
            "chiave": tuple(c.get("chiave") or ()),
            "chiusa": str(c.get("stato") or "") in CERT.STATI_CREDUTI_CHIUSI,
            "coperto": None, "apertura": None, "ingressi": [],
            "chiusure": [_riga(o) for o in (c.get("uscite") or ())],
            "per_selezione": True,
            "tolleranza": float(c.get("tolleranza") or 0.0),
        })
    out.append({
        "id": "specchio", "chiave": (), "chiusa": False, "coperto": None,
        "apertura": None, "ingressi": [],
        "chiusure": [{"ordine_id": str(r.get("order_id") or ""), "bet_id": r.get("bet_id"),
                      "size": r.get("size"), "price": r.get("price"),
                      "status": r.get("status"),
                      "size_matched": r.get("size_matched"),
                      "size_remaining": r.get("size_remaining"),
                      "avg_price_matched": r.get("average_price_matched")}
                     for r in specchio or []],
        "per_selezione": True, "tolleranza": 0.0,
    })
    return out


def stake_scenario(scenario: str, stake: float) -> float:
    return 400.0 if scenario == "parziali" else stake


def modalita_scenario(scenario: str) -> str:
    """La modalita' del RUNNER (il tetto del processo)."""
    return "LIVE" if scenario == "live" or scenario in SCENARI_SOLDI_VERI else "PAPER"


def modalita_bot_scenario(scenario: str) -> str:
    """La modalita' della RIGA del bot (`mode`, la scrive il ponte
    dall'interruttore del bot): 'live' | 'paper'."""
    if scenario in SCENARI_SOLDI_VERI:
        return SCENARI_SOLDI_VERI[scenario][0]
    return "live" if modalita_scenario(scenario) == "LIVE" else "paper"


def dry_run_scenario(scenario: str) -> Optional[bool]:
    """`None` = il default della modalita' (come `_instantiate_bot`).

    ⚠️ Lo scenario `live` DICHIARA `dry_run=False`. In LIVE `_instantiate_bot`
    fa nascere il bot in dry-run per prudenza sui soldi veri, e l'utente deve
    toglierlo a mano dalla scheda: col default, nel replay, il percorso LIVE non
    piazzava NIENTE e il controllo B8 (i minimi .it) restava «non lo so» — cioe'
    proprio la blindatura money-critical non era mai verificata. Qui i soldi veri
    non esistono comunque: il banco gira su `FlumineSimulation` e ogni ordine e'
    simulato, qualunque cosa dica la modalita'.
    """
    if scenario == "dry-run":
        return True
    if scenario == "live":
        return False
    if scenario in SCENARI_SOLDI_VERI:
        # 04/10: il ponte arma SEMPRE con `dry_run` False (soldi veri = ordini
        # veri, `tennis_bot_service._riga_armatura`)
        return False
    return None


# ---------------------------------------------------------------------------
# il processo: le cache di modulo si azzerano da un elenco ESPLICITO
# ---------------------------------------------------------------------------
# ⚠️ catalogo §7 punto 37: una cache di modulo sopravvissuta fra scenari nello
# stesso figlio della pool sotto-sollecita i controlli. Qui si azzera un elenco
# NOMINATO (mai un `dir()` che svuota «tutto» e porta via anche cio' che serve).
_DA_AZZERARE: Tuple[Tuple[str, str], ...] = (
    ("Betfair.stream.tennis_live.tennis_runner", "_INSTANCE_LOCK"),
)


def _azzera_stato_di_processo() -> List[str]:
    fatti: List[str] = []
    for modulo, nome in _DA_AZZERARE:
        mod = sys.modules.get(modulo)
        if mod is None or not hasattr(mod, nome):
            continue
        setattr(mod, nome, None)
        fatti.append("%s.%s" % (modulo, nome))
    return fatti


@contextmanager
def _nessun_contesto():
    yield


@contextmanager
def _modalita_dichiarata(mode: str):
    """`TENNIS_LIVE_ORDER_MODE` e' di PROCESSO e il runner la rilegge a ogni
    giro: si dichiara per la durata del replay e si rimette com'era. Gli ordini
    restano simulati da flumine in ogni caso: i soldi veri non esistono qui."""
    chiavi = ("TENNIS_LIVE_ORDER_MODE", "TENNIS_PAPER_LATENCY_MS")
    prima = {k: os.environ.get(k) for k in chiavi}
    os.environ["TENNIS_LIVE_ORDER_MODE"] = mode
    try:
        yield
    finally:
        for k, v in prima.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# la registrazione: raw, punteggi, catalogo
# ---------------------------------------------------------------------------
def cartella_predefinita() -> str:
    """La RADICE delle registrazioni tennis, la stessa del recorder di
    produzione (`tennis_recorder.default_record_dir`), col giorno piu' recente."""
    radice = default_record_dir()
    giorni = []
    if os.path.isdir(radice):
        giorni = sorted(d for d in os.listdir(radice) if d.isdigit())
    return os.path.join(radice, giorni[-1]) if giorni else radice


def percorsi(data_dir: str, event_id: str) -> Tuple[str, str]:
    base = os.path.join(data_dir, str(event_id))
    return (os.path.join(base, "%s.raw.jsonl" % event_id),
            os.path.join(base, "%s.score.jsonl" % event_id))


def mercato_dal_raw(raw: str) -> Tuple[Optional[str], Dict[int, int]]:
    """market_id del MATCH_ODDS e {selection_id: sortPriority}, dal raw.

    ⚠️ i NOMI non ci sono: `marketDefinition.runners` porta `id`,
    `sortPriority` e `status`, mai `name`. E' il limite 1 dichiarato in testa.
    """
    with io.open(raw, "r", encoding="utf-8") as f:
        for riga in f:
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            for mc in d.get("mc") or []:
                md = mc.get("marketDefinition")
                if not md or md.get("marketType") != "MATCH_ODDS":
                    continue
                ordine = {int(r["id"]): int(r.get("sortPriority") or 0)
                          for r in (md.get("runners") or []) if r.get("id")}
                return str(mc.get("id")), ordine
    return None, {}


def carica_punteggi(score: str) -> List[Tuple[int, Dict[str, Any]]]:
    """(epoch_ms del poll, stato IPS grezzo) dal sidecar tennis, ordinati.

    Il formato e' quello che scrive `tennis_score.py:260-262`:
    `{"t": <epoch secondi locali>, "score": <stato IPS grezzo>}`.
    """
    out: List[Tuple[int, Dict[str, Any]]] = []
    if not os.path.exists(score):
        return out
    with io.open(score, "r", encoding="utf-8") as f:
        for riga in f:
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            t = d.get("t")
            st = d.get("score")
            if t is None or st is None:
                continue
            try:
                out.append((int(float(t) * 1000.0), st))
            except (TypeError, ValueError):
                continue
    out.sort(key=lambda x: x[0])
    return out


#: 08/10 (cantiere 6): il file dei nomi accanto alle registrazioni (cartella
#: della partita, quella che `applica_bot.risolvi_cartella_tennis` sceglie)
FILE_NOMI = "_names.json"
#: la chiave RISERVATA dei nomi per mercato (cantiere 14, `tennis_replay.
#: convertitore.CHIAVE_MERCATI_NOMI`): non e' un event_id
CHIAVE_MERCATI_NOMI = "_mercati"


def _nomi_della_partita(data_dir: str, event_id: str,
                        market_id: Optional[str] = None) -> Tuple[Dict[str, int], str]:
    """``({nome: selection_id}, causa)`` dal ``_names.json`` di ``data_dir``.
    ``causa`` e' vuota se i nomi ci sono, altrimenti dice PERCHE' no.

    La forma del file (grid runner, e registratore tennis del cantiere 14):
      * chiave PIATTA per evento, i nomi del Match Odds: ``{event_id:
        {selection_id: nome}}`` (si legge per prima, come sempre);
      * chiave RISERVATA ``"_mercati"`` (cantiere 14): ``{"_mercati": {event_id:
        {market_id: {selection_id: nome}}}}``. Non e' un event_id: si legge SOLO
        come ripiego, per il mercato del bot (``market_id``, il MATCH_ODDS del
        raw), se la chiave piatta della partita manca. Mai un altro mercato."""
    cache = os.path.join(data_dir, FILE_NOMI)
    if not os.path.exists(cache):
        return {}, "%s assente in %s" % (FILE_NOMI, data_dir)
    try:
        with io.open(cache, "r", encoding="utf-8") as f:
            tutto = json.load(f)
    except (ValueError, OSError) as ex:
        return {}, "%s illeggibile (%s)" % (cache, type(ex).__name__)
    if not isinstance(tutto, dict):
        return {}, "%s non e' un oggetto json" % cache
    per_evento = tutto.get(str(event_id))
    if not isinstance(per_evento, dict) or not per_evento:
        mercati = tutto.get(CHIAVE_MERCATI_NOMI)
        per_mercato = mercati.get(str(event_id)) if isinstance(mercati, dict) else None
        voce = (per_mercato.get(str(market_id))
                if isinstance(per_mercato, dict) and market_id else None)
        if not isinstance(voce, dict) or not voce:
            return {}, "%s non ha la partita %s" % (cache, event_id)
        per_evento = voce
    out: Dict[str, int] = {}
    for sel, nome in per_evento.items():
        if not isinstance(nome, str) or not nome.strip():
            continue
        try:
            out[str(nome)] = int(sel)
        except (TypeError, ValueError):
            continue
    if not out:
        return {}, "%s: nessun nome leggibile per la partita %s" % (cache, event_id)
    return out, ""


def catalogo_dichiarato(data_dir: str, event_id: str,
                        nomi: Optional[str] = None,
                        market_id: Optional[str] = None) -> Dict[str, int]:
    """La mappa `{nome_runner: selection_id}` che in produzione porta
    `listMarketCatalogue` e che il raw NON contiene (limite 1).

    Fonti, in ordine: `--nomi "Nome=selid,Nome=selid"`, poi la cache
    `_names.json` che i grid runner scrivono accanto alle registrazioni
    (08/10: chiave riservata `_mercati` come ripiego, vedi `_nomi_della_partita`).
    """
    if nomi:
        out: Dict[str, int] = {}
        for pezzo in str(nomi).split(","):
            if "=" not in pezzo:
                continue
            k, _, v = pezzo.partition("=")
            try:
                out[k.strip()] = int(v.strip())
            except ValueError:
                continue
        return out
    return _nomi_della_partita(data_dir, event_id, market_id)[0]


def stato_nomi(data_dir: str, event_id: str) -> Dict[str, Any]:
    """08/10 (cantiere 6): i nomi dei giocatori di UNA partita per la testa del
    referto: ``{"presenti": bool, "nomi": [...], "causa": str, "file": path}``.
    Il mercato e' il MATCH_ODDS del raw (serve al ripiego su `_mercati`)."""
    raw, _score = percorsi(data_dir, event_id)
    market_id = mercato_dal_raw(raw)[0] if os.path.exists(raw) else None
    cat, causa = _nomi_della_partita(data_dir, event_id, market_id)
    return {"presenti": bool(cat), "nomi": sorted(cat), "causa": causa,
            "file": os.path.join(data_dir, FILE_NOMI)}


def qualita_registrazione(data_dir: str, event_id: str) -> str:
    try:
        from ...tools.validate_recordings import validate_event

        rep = validate_event(data_dir, str(event_id))
        buchi = len(getattr(rep, "gaps_in_window", None) or [])
        return "%s %s%% (%d buchi dichiarati)" % (
            rep.verdict, rep.coverage_pct, buchi)
    except Exception as ex:  # noqa: BLE001 - il verdetto e' un di piu', non un gate
        return "ignota (%s)" % type(ex).__name__


def impronta() -> Dict[str, str]:
    """Versioni e IMPRONTA del codice dei bot: un referto che non si puo' rifare
    identico non e' un referto, e' un ricordo (§6.8)."""
    import betfairlightweight
    import flumine

    sorgenti = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "tennis_scalper", nome)
        for nome in ("tennis_scalper_bot.py", "tennis_pro_bot.py",
                     "tennis_flb_bot.py", "tennis_swing_bot.py")
    ]
    sorgenti.append(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tennis_runner.py"))
    h = hashlib.sha256()
    for percorso in sorgenti:
        try:
            with io.open(percorso, "rb") as f:
                h.update(f.read())
        except OSError:
            h.update(b"?")
    return {
        "flumine": getattr(flumine, "__version__", "?"),
        "betfairlightweight": getattr(betfairlightweight, "__version__", "?"),
        "codice_bot": h.hexdigest()[:12],
    }


# ---------------------------------------------------------------------------
# IL GUASTO INIETTATO: Betfair rifiuta
# ---------------------------------------------------------------------------
def _rifiuta_tutto(quadro: Any):
    """Un trading control di flumine che RIFIUTA ogni piazzamento.

    E' la via di produzione del rifiuto, non un finto: si eredita da
    `flumine.controls.BaseControl`, e il suo `_on_error` chiama
    `order.violation(...)` (stato -> `OrderStatus.VIOLATION`) e alza
    `ControlError`; `Transaction._validate_controls` la cattura e
    `place_order` torna **False senza piazzare**
    (`flumine/execution/transaction.py:67-75, 230-242`). Il bot vede
    esattamente cio' che vedrebbe con un rifiuto vero di Betfair.
    """
    from flumine.controls import BaseControl
    from flumine.order.orderpackage import OrderPackageType

    class _RifiutaTutto(BaseControl):
        NAME = "REPLAY_RIFIUTA_TUTTO"

        def __init__(self, flumine: Any) -> None:
            super().__init__(flumine)
            self.rifiutati: List[str] = []

        def _validate(self, order: Any, package_type: Any) -> None:
            if package_type != OrderPackageType.PLACE:
                return
            self.rifiutati.append(str(getattr(order, "id", "") or ""))
            self._on_error(order, "rifiuto iniettato dal replay")

    return _RifiutaTutto(quadro)


class _DbReplay:
    """Le firme di `tennis_db` che `chiusura_manuale` usa: nel replay il DB non
    esiste, il CONTENUTO delle scritture si' (finisce nel referto)."""

    def __init__(self) -> None:
        self.fatte: List[Tuple[Any, Dict[str, Any]]] = []
        self.errori: List[Tuple[Any, Dict[str, Any]]] = []
        self.stati: List[Tuple[str, str, str]] = []
        self.attivita: List[Tuple[str, str, str, Dict[str, Any]]] = []

    def write_tennis_order_done(self, rid: Any, result: Dict[str, Any]) -> None:
        self.fatte.append((rid, dict(result)))

    def write_tennis_order_error(self, rid: Any, result: Dict[str, Any]) -> None:
        self.errori.append((rid, dict(result)))

    def set_tennis_bot_status(self, event_id: str, bot_key: str, status: str,
                              **kw: Any) -> None:
        self.stati.append((str(event_id), str(bot_key), str(status)))

    def write_tennis_bot_activity(self, event_id: str, bot_key: str, kind: str,
                                  payload: Dict[str, Any]) -> None:
        self.attivita.append((str(event_id), str(bot_key), str(kind), dict(payload)))


# ---------------------------------------------------------------------------
# IL PONTE: fa girare i WORKER di produzione alla loro cadenza vera
# ---------------------------------------------------------------------------
class _Ponte:
    """Sta fra `MotoreReplay` e il BOT DI PRODUZIONE, e non decide niente.

    Fa quello che in produzione fanno i `BackgroundWorker` del runner, alla
    LORO cadenza (tempo di mercato, non tempo reale):

      * `score_and_now_worker` (2 s): legge il punteggio col parser VERO e
        scrive `strat.score` / `strat.point_pressure` esattamente come
        `tennis_runner.py:1060-1070`;
      * `bot_control_worker` (3 s): lo scenario `bot-fermo` chiama il
        `_disable_strategy` VERO del runner;
      * `tennis_live_order_worker` (1 s): lo specchio degli ordini dal blotter,
        con le funzioni VERE `_mirror_order` / `_position_row`;
      * il giro dei CONTROLLI: una `Osservazione` per giro.

    Il bot lo si chiama tale e quale: `check_market_book` e
    `process_market_book` sono i suoi, e lo scoping per mercato lo ha gia'
    messo `_instantiate_bot` con `_scope_to_market`.
    """

    def __init__(self, *, strat: Any, bot_key: str, event_id: str,
                 market_id: str, scenario: str, punteggi: List[Tuple[int, Dict[str, Any]]],
                 referto: CERT.Referto, quadro: Any, modalita: str,
                 stake: float, cap: Optional[float], attivita: List[Tuple[str, Dict[str, Any]]],
                 rifiuta: Optional[Any], ogni_ms: int,
                 feed_stantio_da_ms: Optional[int] = None,
                 riavvia: Optional[Callable[[Any], Any]] = None) -> None:
        from ..tennis_runner import SCORE_POLL_SEC

        self.s = strat
        self.bot_key = bot_key
        self.event_id = str(event_id)
        self.market_id = str(market_id)
        self.scenario = scenario
        self.punteggi = punteggi
        self.ts_punteggi = [t for t, _ in punteggi]
        self.ref = referto
        self.quadro = quadro
        self.modalita = modalita
        self.stake = stake
        self.cap = cap
        self.attivita = attivita
        self.rifiuta = rifiuta
        self.ogni_ms = max(0, int(ogni_ms))
        self.feed_stantio_da_ms = feed_stantio_da_ms
        self.riavvia = riavvia
        self._riavviato = False
        self.cadenza_punteggio_ms = int(float(SCORE_POLL_SEC or 2.0) * 1000)
        self._ultimo_punteggio_ms = 0
        self._ultimo_controllo_ms = 0
        self._i_punteggio = 0
        self._disabilitato = False
        # gli id degli ordini gia' visti a mercato: cio' che compare adesso e'
        # NUOVO, e solo su quello si giudica «il bot ha chiesto un ordine ora»
        self._ordini_visti: set = set()
        self._meta_ms: Optional[int] = None
        self._fine_ms: Optional[int] = None
        self._ultimo_book: Any = None
        # scenario `chiusura-abbinata-in-parte` (None negli altri)
        self.sorveglianza_cp: Optional[Any] = None
        # scenario `chiudi-ora` (D3, 24/09): la sessione/DB del runner per la
        # via di produzione, e gli id degli ordini che c'erano al clic
        self._chiudi: Optional[Dict[str, Any]] = None
        self._ids_prima_manuale: Optional[set] = None
        # N3 (28/09): scenari a uscite manuali. `firme` e' la colonna
        # `params.uscite_approvate` della riga per partita (come la scrive la
        # RPC); il `bot_control_worker` la rilegge alla sua cadenza.
        self.osservatore: Optional[Any] = None
        self.firme: Dict[str, str] = {}
        self._firme_ms = 0
        self._sess_firme: Optional[Any] = None
        self.ultimo_ms = 0
        # B10 (04/10): il registro dell'exchange del banco si legge a pezzi
        # (indice), la storia dei rifiuti per (selezione, lato, size, tipo)
        self._idx_piazzati = 0
        self._rifiuti_taglia: Dict[Tuple[Any, ...], int] = {}
        # SV1 (04/10): la catena «soldi veri» dello scenario e i conti per il
        # riepilogo (ordini eseguiti per client, aperture fermate dalla terza rete)
        self.catena_soldi_veri: Optional[str] = None
        self._sv_reali: set = set()
        self._sv_simulati: set = set()
        self._sv_fermati = 0
        self._sv_idx = 0
        # 07/10 (Applica bot): l'istante in cui l'utente ARMA il bot. Prima il
        # bot NON esiste nel runner (in produzione `_instantiate_bot` lo crea
        # all'armamento): nessun book, nessun punteggio, nessun worker.
        self.accensione = VB.Accensione(None)
        # 08/10 (cantiere 6): il METRO dei setup di tennis_pro (famiglia SP),
        # None per gli altri bot
        self.lettore_setup: Optional[CERT.LettoreSetupPro] = None

    def ruolo_ordine(self, ordine: Any) -> Optional[str]:
        """Il RUOLO di un ordine per il guasto CP, dalla credenza VERA del bot
        (`credenze`: ingressi e uscite che il bot sta seguendo)."""
        for c in CERT.credenze(self.s, self.bot_key):
            if any(x is ordine for x in (c.get("uscite") or ())):
                return "uscita"
            if any(x is ordine for x in (c.get("ingressi") or ())):
                return "ingresso"
        return None

    # ------------------------------------------------------------- contratto
    @property
    def stream_ids(self) -> Any:
        return self.s.stream_ids

    def process_new_market(self, market: Any, market_book: Any) -> None:
        self.s.process_new_market(market, market_book)

    def check_market_book(self, market: Any, market_book: Any) -> bool:
        self._ultimo_book = market_book
        self.ref.tick += 1
        pt = getattr(market_book, "publish_time", None)
        ms = int(pt.timestamp() * 1000) if pt is not None else 0
        if self.accensione.scatta(ms):
            self.attivita.append(("replay_accensione_utente",
                                  {"dal_ms": self.accensione.dal_ms, "ms": ms}))
        if not self.accensione.acceso(ms):
            # 07/10 (Applica bot): bot non ancora armato dall'utente
            return False
        self._forse_punteggio(ms)
        self._forse_disarmo(market, ms)
        self._forse_riavvio(market, ms)
        self._forse_chiudi_ora(market, ms)
        self._forse_firme(ms)
        return bool(self.s.check_market_book(market, market_book))

    def process_market_book(self, market: Any, market_book: Any) -> None:
        pt = getattr(market_book, "publish_time", None)
        ms = int(pt.timestamp() * 1000) if pt is not None else 0
        prima = len(self.attivita)
        self.s.process_market_book(market, market_book)
        self.ref.decisioni += 1
        self.ref.azioni += len(self.attivita) - prima
        if self.ogni_ms and (ms - self._ultimo_controllo_ms) < self.ogni_ms:
            return
        self._ultimo_controllo_ms = ms
        self.giro(market, market_book, prima)

    # --------------------------------------------------------------- worker
    def _forse_punteggio(self, ms: int) -> None:
        """`score_and_now_worker` alla cadenza vera (2 s di tempo di mercato)."""
        if not self.punteggi or ms <= 0:
            return
        if ms - self._ultimo_punteggio_ms < self.cadenza_punteggio_ms:
            return
        self._ultimo_punteggio_ms = ms
        if (self.feed_stantio_da_ms is not None and ms >= self.feed_stantio_da_ms):
            # blackout IPS: il worker esce senza toccare `strat.score` — e' il
            # comportamento VERO (`tennis_runner.py:1057-1058`: l'eccezione e'
            # loggata e il punteggio resta quello di prima).
            return
        from ...tennis_scalper.tennis_score import parse_tennis_scores

        i = bisect_right(self.ts_punteggi, ms)
        if i <= self._i_punteggio:
            return
        self._i_punteggio = i
        grezzo = self.punteggi[i - 1][1]
        try:
            ts = parse_tennis_scores([grezzo], self.event_id)
        except Exception as ex:  # noqa: BLE001 - il feed non rompe il replay
            logger.debug("punteggio illeggibile: %s", ex)
            return
        # ESATTAMENTE come tennis_runner.py:1060-1070
        if hasattr(self.s, "score"):
            self.s.score = ts
        if hasattr(self.s, "point_pressure") and ts is not None:
            self.s.point_pressure = bool(ts.point_pressure)
        if self.lettore_setup is not None:
            # il banco legge lo STESSO campione col suo metro (famiglia SP)
            self.lettore_setup.campione(ts, self._ultimo_book, self.s)

    def _forse_disarmo(self, market: Any, ms: int) -> None:
        """Lo scenario `bot-fermo`: a meta' partita il runner disarma davvero."""
        if self.scenario != "bot-fermo" or self._disabilitato:
            return
        if self._meta_ms is None or ms < self._meta_ms:
            return
        from ..tennis_runner import _disable_strategy

        _disable_strategy(self.s)
        self._disabilitato = True
        self.ref.note.append(
            "bot DISARMATO a meta' partita con `_disable_strategy` di produzione")

    def _forse_riavvio(self, market: Any, ms: int) -> None:
        """Lo scenario `riavvio`: il runner ricostruisce lo stream a meta' partita.

        LA REGOLA E' QUELLA DI PRODUZIONE, non una nostra: `_request_restart`
        (`tennis_runner.py:816-...`) concede il restart SOLO se ogni bot ospitato
        e' FLAT secondo `_strategy_is_flat`, che legge il blotter e in caso di
        dubbio risponde «non flat». Con una posizione aperta il restart si
        RINVIA al giro dopo, perche' il rebuild azzererebbe il blotter e la
        posizione resterebbe orfana. Qui si fa esattamente questo: si prova a
        ogni giro dal punto di meta' partita, e quando il bot e' flat lo si
        ri-istanzia con `_instantiate_bot` (carry-over delle stats compreso).
        """
        if self.riavvia is None or self._riavviato:
            return
        if self._meta_ms is None or ms < self._meta_ms:
            return
        from ..tennis_runner import _disable_strategy, _strategy_is_flat

        if not _strategy_is_flat(self.quadro, self.s):
            return              # rinviato, come in produzione
        vecchio = self.s
        nuovo = self.riavvia(vecchio)
        if nuovo is None:
            return
        _disable_strategy(vecchio)
        self.s = nuovo
        self._riavviato = True
        self.ref.note.append(
            "RIAVVIO a meta' partita concesso a bot FLAT (regola di produzione "
            "`_request_restart`): il bot e' stato ri-istanziato con "
            "`_instantiate_bot` e il blotter nuovo e' vuoto, come dopo un "
            "rebuild dello stream")

    def _forse_chiudi_ora(self, market: Any, ms: int) -> None:
        """Lo scenario `chiudi-ora` (D3, 24/09): a meta' partita l'utente preme
        "Chiudi". La richiesta passa dalle funzioni VERE del runner
        (`chiusura_manuale.prendi_in_carico`, poi `avanza` alla cadenza del
        `bot_control_worker`, con `_strategy_is_flat`/`_disable_strategy` di
        produzione); il DB e' l'unica cosa finta (registra invece di scrivere)."""
        if self.scenario != SCENARIO_CHIUDI_ORA:
            return
        if self._meta_ms is None or ms < self._meta_ms:
            return
        from .. import chiusura_manuale as CMN
        from ..tennis_runner import (BOT_CONTROL_POLL_SEC, TennisLiveSession,
                                     _disable_strategy, _strategy_is_flat)

        if self._chiudi is None:
            sess = TennisLiveSession(trading=None)
            sess.market_meta = {self.event_id: {"market_id": self.market_id}}
            sess.hosted = {(self.event_id, self.bot_key): self.s}
            sess.order_mode = self.modalita
            db = _DbReplay()
            # gli ordini che c'erano AL CLIC: tutto cio' che nasce dopo lo
            # giudica B9
            self._ids_prima_manuale = {
                str(getattr(o, "id", "") or "") for o in self.ordini_del_bot(market)}
            cmd = {"action": CMN.AZIONE, "bot": self.bot_key, "event_id": self.event_id,
                   "market_id": self.market_id, "mode": self.modalita.lower(),
                   "trade_id": None, "client_ref": "replay-chiudi-ora"}
            subito = CMN.prendi_in_carico(sess, 1, cmd, db=db, adesso=ms / 1000.0)
            self._chiudi = {"sessione": sess, "db": db, "ultimo_ms": ms, "finito": False}
            self.ref.note.append(
                "CHIUDI ORA a meta' partita (via di produzione `chiusura_manuale`): %s"
                % ("preso in carico" if subito is None
                   else "rifiutato subito: %s" % subito.get("message")))
            return
        if self._chiudi["finito"]:
            return
        if ms - self._chiudi["ultimo_ms"] < int(float(BOT_CONTROL_POLL_SEC or 3.0) * 1000):
            return
        self._chiudi["ultimo_ms"] = ms
        concluse = CMN.avanza(self.quadro, self._chiudi["sessione"],
                              e_flat=_strategy_is_flat, disabilita=_disable_strategy,
                              db=self._chiudi["db"], adesso=ms / 1000.0)
        if concluse:
            self._chiudi["finito"] = True
            db = self._chiudi["db"]
            esiti = [r.get("message") for _rid, r in db.fatte + db.errori]
            self.ref.note.append("CHIUDI ORA concluso: stato riga %s; esito: %s"
                                 % ([s for _e, _b, s in db.stati], esiti))

    def firma(self, chiave: str, istante: str) -> None:
        """La RPC `tennis_bot_approva_uscita`: `{chiave: now()}` nella colonna."""
        self.firme[str(chiave)] = istante

    def _forse_firme(self, ms: int) -> None:
        """N3: il `bot_control_worker` alla cadenza vera rilegge la riga e la
        passa al bot con la funzione di PRODUZIONE `_aggiorna_uscite`
        (interruttore + firme). Solo negli scenari a uscite manuali."""
        if ms > 0:
            self.ultimo_ms = ms
        if self.osservatore is None or ms <= 0:
            return
        self.osservatore.giro(ms)
        from ..tennis_runner import BOT_CONTROL_POLL_SEC
        if ms - self._firme_ms < int(float(BOT_CONTROL_POLL_SEC or 3.0) * 1000):
            return
        self._firme_ms = ms
        from .. import tennis_runner as TR

        if self._sess_firme is None:
            self._sess_firme = TR.TennisLiveSession(trading=None)
        riga = {"event_id": self.event_id, "bot_key": self.bot_key,
                "uscite_automatiche": False,
                "params": {"uscite_approvate": dict(self.firme)}}
        vera = TR.tennis_db.write_tennis_bot_activity
        scritte: List[Any] = []
        # il DB qui non esiste: l'attivita' si registra, mai si scrive
        TR.tennis_db.write_tennis_bot_activity = (  # type: ignore[assignment]
            lambda *a, **k: scritte.append((a, k)))
        try:
            TR._aggiorna_uscite(self.quadro, self._sess_firme,
                                (self.event_id, self.bot_key), self.s, riga)
        finally:
            TR.tennis_db.write_tennis_bot_activity = vera  # type: ignore[assignment]

    def imposta_finestra(self, primo_ms: int, ultimo_ms: int) -> None:
        self._meta_ms = primo_ms + (ultimo_ms - primo_ms) // 2
        self._fine_ms = ultimo_ms

    # ------------------------------------------------------------ i controlli
    def ordini_del_bot(self, market: Any) -> List[Any]:
        blotter = getattr(market, "blotter", None)
        if blotter is None:
            return []
        try:
            return list(blotter.strategy_orders(self.s) or [])
        except Exception:  # noqa: BLE001 - blotter illeggibile: nessun ordine
            return []

    def esposizioni(self, market: Any, ordini: List[Any]) -> Dict[Any, Dict[str, float]]:
        """L'esposizione per selezione dalla funzione VERA del worker ordini
        (`_position_row`): mai numeri ricalcolati a mano."""
        from ..tennis_live_order_worker import _position_row

        out: Dict[Any, Dict[str, float]] = {}
        viste = set()
        for o in ordini:
            sel = getattr(o, "selection_id", None)
            if sel is None:
                continue
            chiave = (int(sel), float(getattr(o, "handicap", 0.0) or 0.0))
            if chiave in viste:
                continue
            viste.add(chiave)
            riga = _position_row(market, self.s, self.modalita.lower(),
                                 self.event_id, self.market_id, int(sel), chiave[1])
            if riga:
                out[chiave] = riga
        return out

    def specchio(self, ordini: List[Any]) -> List[Dict[str, Any]]:
        """Le righe che `tennis_live_orders` porterebbe, costruite dalla
        funzione VERA dello specchio (`_mirror_order`), catturate invece che
        scritte: il DB qui non esiste, il CONTENUTO si'."""
        from .. import tennis_live_order_worker as OW

        righe: List[Dict[str, Any]] = []
        vero = OW.tennis_db.upsert_tennis_order
        per_ref: Dict[str, Any] = {}

        def _cattura(row: Dict[str, Any]) -> None:
            righe.append(dict(row))

        OW.tennis_db.upsert_tennis_order = _cattura  # type: ignore[assignment]
        try:
            for o in ordini:
                oid = getattr(o, "id", None)
                if oid is None:
                    continue
                ref = ("bot:" + str(oid))[:32]
                per_ref[ref] = oid
                OW._mirror_order(self.modalita.lower(), self.event_id, ref, o, {},
                                 source=self.bot_key)
        finally:
            OW.tennis_db.upsert_tennis_order = vero  # type: ignore[assignment]
        for riga in righe:
            riga["order_id"] = str(per_ref.get(riga.get("client_order_ref"), ""))
        return righe

    def residui_del_bot(self) -> List[Dict[str, Any]]:
        """04/10: i residui che il bot ricorda (`ResiduiRicordati`), come li
        pubblica nelle sue `stats`."""
        mem = getattr(self.s, "residui_ricordati", None)
        try:
            return list(mem.per_stats()) if mem is not None else []
        except Exception:  # noqa: BLE001 - memoria illeggibile: nessun residuo
            return []

    def rifiuti_taglia(self) -> List[Dict[str, Any]]:
        """B10: i rifiuti per taglia NUOVI dell'exchange del banco
        (`minimi_banco`), letti dal suo registro con la SUA regola."""
        from ...backtest import minimi_banco as MB

        def _rifiutato(size: Any, tipo: str, side: Any) -> bool:
            return bool(MB.ATTIVO) and MB.sotto_minimo(size, tipo, side)

        nuovi, self._idx_piazzati = CERT.rifiuti_taglia_nuovi(
            MB.REGISTRO.piazzati, self._idx_piazzati, self.s, _rifiutato,
            self._rifiuti_taglia)
        return nuovi

    def _conta_soldi_veri(self, righe: List[Dict[str, Any]],
                          attivita: List[Tuple[str, Dict[str, Any]]]) -> None:
        for r in righe:
            oid = r.get("order_id")
            if r.get("client_reale") is True:
                self._sv_reali.add(oid)
            elif r.get("client_reale") is False:
                self._sv_simulati.add(oid)
        from ..guardie_tennis import ControlloModoOrdiniTennis

        for kind, p in attivita:
            if kind == "place_rejected" and ControlloModoOrdiniTennis.NAME in str(
                    (p or {}).get("motivo") or ""):
                self._sv_fermati += 1

    def riepilogo_soldi_veri(self) -> str:
        return ("SOLDI VERI (%s): ordini eseguiti sul client REALE %d, sul client "
                "SIMULATO %d; aperture reali fermate dalla terza rete "
                "(TENNIS_MODO_ORDINI) %d"
                % (self.catena_soldi_veri, len(self._sv_reali), len(self._sv_simulati),
                   self._sv_fermati))

    def giro(self, market: Any, market_book: Any, prima: int) -> None:
        ordini_veri = self.ordini_del_bot(market)
        specchio = self.specchio(ordini_veri)
        righe = [CERT.riga_ordine(o) for o in ordini_veri]
        cred = CERT.credenze(self.s, self.bot_key)
        ids_ingresso = set()
        for c in cred:
            ids_ingresso |= CERT._ids(c.get("ingressi") or ())
        tutti = {r.get("order_id") for r in righe}
        nuovi = tutti - self._ordini_visti
        self._ordini_visti |= tutti
        pt = getattr(market_book, "publish_time", None)
        # D3: il "chiudi ora" letto dallo stato VERO del bot
        esito_m = getattr(self.s, "uscita_manuale", None)
        dopo_m = (tutti - self._ids_prima_manuale
                  if self._ids_prima_manuale is not None else set())
        oss = CERT.Osservazione(
            bot=self.bot_key,
            scenario=self.scenario,
            quando=pt.isoformat() if pt is not None else "",
            manuale_chiesta=bool(getattr(self.s, "uscita_manuale_chiesta", False)),
            manuale_esito=(esito_m or {}).get("esito") if isinstance(esito_m, dict) else None,
            ordini_dopo_manuale=dopo_m,
            modalita=self.modalita.lower(),
            dry_run=bool(getattr(self.s, "dry_run", False)),
            disabilitato=bool(getattr(self.s, "_tennis_disabled", False)),
            inplay=bool(getattr(market_book, "inplay", False)),
            stato_mercato=str(getattr(market_book, "status", "") or ""),
            market_id=self.market_id,
            stake=float(self.stake or 0.0),
            cap_esposizione=self.cap,
            ordini=righe,
            rifiutati=list(self.rifiuta.rifiutati) if self.rifiuta else [],
            credenze=cred,
            attivita=self.attivita[prima:],
            stats=dict(getattr(self.s, "stats", None) or {}),
            specchio=specchio,
            esposizioni=self.esposizioni(market, ordini_veri),
            ids_ingresso=ids_ingresso,
            ordini_nuovi=nuovi,
            rifiuti_taglia=self.rifiuti_taglia(),
            catena_soldi_veri=self.catena_soldi_veri,
            residui=self.residui_del_bot(),
            setup_pro=(self.lettore_setup.stato(self.s, market_book)
                       if self.lettore_setup is not None else None),
        )
        if self.catena_soldi_veri is not None:
            self._conta_soldi_veri(righe, self.attivita[self._sv_idx:])
            self._sv_idx = len(self.attivita)
        self.ref.violazioni.extend(CERT.verifica(oss, self.ref.sollecitati))
        # I CONTROLLI CP (scenario chiusura-abbinata-in-parte)
        if self.sorveglianza_cp is not None:
            for cod, reg, det in self.sorveglianza_cp.verifica(
                    credenze_cp(cred, specchio), self.ref.sollecitati):
                self.ref.violazioni.append(CERT.Violazione(
                    cod, reg, det, oss.quando))
        for c in cred:
            stato = str(c.get("stato") or "")
            if stato and stato not in self.ref.stati_visti:
                self.ref.stati_visti.append(stato)
        self.ref.ordini_piazzati = len(righe)
        self.ref.ordini_abbinati = sum(
            1 for r in righe if (r.get("size_matched") or 0.0) > 0.009)

    def chiudi(self, market: Any) -> None:
        """L'ULTIMO giro, a mercato CHIUSO: e' li' che si misura il P&L (P3)."""
        if market is None:
            return
        ordini_veri = self.ordini_del_bot(market)
        righe = [CERT.riga_ordine(o) for o in ordini_veri]
        cred = CERT.credenze(self.s, self.bot_key)
        oss = CERT.Osservazione(
            bot=self.bot_key, scenario=self.scenario, quando="settlement",
            modalita=self.modalita.lower(),
            dry_run=bool(getattr(self.s, "dry_run", False)),
            disabilitato=bool(getattr(self.s, "_tennis_disabled", False)),
            stato_mercato="CLOSED", market_id=self.market_id,
            stake=float(self.stake or 0.0), cap_esposizione=self.cap,
            ordini=righe, credenze=cred,
            stats=dict(getattr(self.s, "stats", None) or {}),
            specchio=self.specchio(ordini_veri),
        )
        self.ref.violazioni.extend(CERT.verifica(oss, self.ref.sollecitati))
        self.ref.stats_finali = dict(getattr(self.s, "stats", None) or {})


# ---------------------------------------------------------------------------
# IL REPLAY DI UN EVENTO
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 07/10 (APPLICA BOT) - I PARAMETRI CHE L'UTENTE PUO' VARIARE
# ---------------------------------------------------------------------------
# Le chiavi sono quelle della scheda del bot in produzione
# (``frontend/src/lib/tennis.ts::TENNIS_BOT_REGISTRY``, stessa etichetta, stesso
# passo, stessi limiti; allargati SOLO dove uno scenario del banco usa gia' un
# valore fuori dalla scheda, es. ``gate-aperto``), piu' lo stake della riga. Il
# DEFAULT si legge dall'ISTANZA VERA del bot costruita da ``_instantiate_bot``
# con la riga dello scenario: preset del runner, default della classe e valori
# dello scenario sono quelli che il bot userebbe davvero. FUORI: le blindature
# .it (``size_step``, ``live_min_bet``, ``exact_exits``: regole di Betfair), le
# soglie tecniche aperte solo da ``gate-aperto`` (``warmup_ms``, ``min_book_size``,
# ``min_lay_size``, ``min_total_matched``) e ``dry_run`` (sicurezza).
_MENU_TENNIS: Dict[str, Tuple[Tuple[str, str, str, str, float, float, float, str], ...]] = {
    # (chiave, etichetta, gruppo, tipo, min, max, passo, unita); scelte a parte
    "tennis_scalper": (
        ("stake", "Stake", "Importi", "float", 2.0, 500.0, 0.5, "EUR"),
        ("signal_ticks", "Tick segnale", "Ingresso", "float", 1, 10, 1, "tick"),
        ("min_flow", "Flusso minimo per lato", "Filtri", "float", 0, 500, 1, "EUR"),
        ("min_size", "Size minima ai best", "Filtri", "float", 0, 2000, 1, "EUR"),
        ("price_min", "Quota minima", "Ingresso", "float", 1.01, 5, 0.1, ""),
        ("price_max", "Quota massima", "Ingresso", "float", 1.5, 30, 0.1, ""),
        ("runner_filter", "Runner operato", "Ingresso", "scelta", 0, 0, 0, ""),
        ("one_tick_per_phase", "Missione 1 tick per fase", "Ingresso", "bool", 0, 0, 0, ""),
        ("inplay_tick_enabled", "Gamba in-play (sperimentale)", "Ingresso", "bool", 0, 0, 0, ""),
        ("scalp_ticks", "Tick di profitto", "Uscita", "int", 1, 5, 1, "tick"),
        ("stop_ticks", "Tick di stop", "Uscita", "int", 1, 8, 1, "tick"),
    ),
    "tennis_pro": (
        ("stake", "Stake", "Importi", "float", 2.0, 500.0, 0.5, "EUR"),
        ("price_max", "Quota massima", "Ingresso", "float", 1.1, 30, 0.1, ""),
        ("trend", "Trend-following", "Ingresso", "bool", 0, 0, 0, ""),
        ("adapt", "Direzione adattiva", "Ingresso", "bool", 0, 0, 0, ""),
        ("maker", "Ingresso maker", "Ingresso", "bool", 0, 0, 0, ""),
        ("min_matched", "Abbinato minimo del mercato", "Filtri", "float", 0, 500000, 5000, "EUR"),
        ("bp_target_ticks", "Break: tick obiettivo", "Uscita", "int", 2, 40, 1, "tick"),
        ("bp_stop_ticks", "Break: tick di stop", "Uscita", "int", 1, 30, 1, "tick"),
        ("fade_target_ticks", "Fade: tick obiettivo", "Uscita", "int", 2, 40, 1, "tick"),
    ),
    "tennis_flb": (
        ("stake", "Stake", "Importi", "float", 2.0, 500.0, 0.5, "EUR"),
        ("lay_max", "Banca solo sotto quota", "Ingresso", "float", 1.01, 1.5, 0.01, ""),
        ("rearm_mult", "Riarmo dopo movimento (x)", "Ingresso", "float", 1.0, 2.0, 0.05, "x"),
        ("min_matched", "Abbinato minimo del mercato", "Filtri", "float", 0, 500000, 5000, "EUR"),
        ("exit_mode", "Uscita", "Uscita", "scelta", 0, 0, 0, ""),
        ("green_ticks", "Tick di green", "Uscita", "int", 1, 20, 1, "tick"),
        ("green_frac", "Frazione da greenare", "Uscita", "float", 0.1, 1.0, 0.1, ""),
    ),
    "tennis_swing": (
        ("stake", "Stake", "Importi", "float", 2.0, 500.0, 0.5, "EUR"),
        ("N", "Finestra N", "Ingresso", "int", 10, 120, 5, "tick"),
        ("zin", "Z di ingresso", "Ingresso", "float", 1.0, 4.0, 0.1, ""),
        ("er_max", "Efficiency Ratio massimo", "Filtri", "float", 0.1, 1.0, 0.05, ""),
        ("stop_ticks", "Tick di stop", "Uscita", "int", 2, 30, 1, "tick"),
        ("tmax", "Tempo massimo in posizione", "Uscita", "int", 20, 300, 10, "s"),
    ),
}
_SCELTE_TENNIS: Dict[str, Tuple[str, ...]] = {
    "runner_filter": ("favorite", "all"),
    "exit_mode": ("hybrid", "hold", "green"),
}


def _bot_dello_scenario(bot: str, scenario: str) -> Any:
    """L'istanza VERA del bot con la riga dello scenario (`_instantiate_bot`,
    runner PAPER, nessun mercato reale): da li' si leggono i default."""
    from betfairlightweight.filters import streaming_market_data_filter

    from ..tennis_runner import LADDER_DEPTH, STREAM_FIELDS, _instantiate_bot

    control: Dict[str, Any] = {
        "event_id": "0", "bot_key": bot, "status": "running",
        "stake": stake_scenario(scenario, 2.0),
        "params": dict(parametri_scenario(scenario, bot)), "stats": None,
        "mode": "paper",
    }
    df = streaming_market_data_filter(fields=list(STREAM_FIELDS), ladder_levels=LADDER_DEPTH)
    return _instantiate_bot(bot, control, "1.0", {}, lambda *_a: None, df, "PAPER",
                            market_ids=["1.0"])


def parametri_modificabili(scenario: str = "base",
                           bot: str = "tennis_flb") -> List[Dict[str, Any]]:
    """Il catalogo dei parametri del bot tennis che "Applica bot" lascia variare."""
    if bot not in _MENU_TENNIS:
        raise ValueError("bot tennis sconosciuto: %r" % bot)
    s = _bot_dello_scenario(bot, scenario)
    out: List[Dict[str, Any]] = []
    for chiave, etichetta, gruppo, tipo, lo, hi, passo, unita in _MENU_TENNIS[bot]:
        v = getattr(s, chiave)
        if tipo == "int":
            v = int(v)
        elif tipo == "float":
            v = float(v)
        elif tipo == "bool":
            v = bool(v)
        senza_limiti = tipo in ("bool", "scelta")
        out.append(VB.voce(chiave, etichetta, tipo, v, gruppo=gruppo,
                           minimo=None if senza_limiti else lo,
                           massimo=None if senza_limiti else hi,
                           passo=None if senza_limiti else passo, unita=unita,
                           scelte=_SCELTE_TENNIS.get(chiave)))
    return out


def _catalogo_per(bot: str):
    def _f(scenario: str = "base") -> List[Dict[str, Any]]:
        return parametri_modificabili(scenario, bot)
    _f.__name__ = "parametri_modificabili_%s" % bot
    _f.__doc__ = "Catalogo dei parametri modificabili di `%s` (contratto del banco)." % bot
    return _f


parametri_modificabili_tennis_scalper = _catalogo_per("tennis_scalper")
parametri_modificabili_tennis_pro = _catalogo_per("tennis_pro")
parametri_modificabili_tennis_flb = _catalogo_per("tennis_flb")
parametri_modificabili_tennis_swing = _catalogo_per("tennis_swing")


def nota_accensione(acc: "VB.Accensione") -> str:
    """Che cosa vede il bot tennis quando l'utente lo arma a ``dal_ms``."""
    def _q(ms: Optional[int]) -> str:
        if ms is None:
            return "mai (registrazione finita prima)"
        from datetime import datetime, timezone

        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()
    return ("ACCENSIONE dell'utente a %s (ms %d, primo book al bot a %s): fino a li' "
            "il bot NON esisteva nel runner (in produzione `_instantiate_bot` lo crea "
            "all'armamento): niente book, niente punteggio, niente worker. Al primo "
            "book trova il ladder corrente del mercato (cache di flumine, come il "
            "runner vivo) e nessuno storico suo: riscaldamento e indicatori (es. "
            "`warmup_ms`, finestra dello swing) ripartono da li', come in produzione."
            % (_q(acc.dal_ms), acc.dal_ms, _q(acc.scattata_ms)))


def certifica_scenario(event_id: str, *, data_dir: str, scenario: str = "base",
                       ogni_ms: int = 1000, campioni_diff: int = 0,
                       bot: str = "tennis_flb",
                       nomi: Optional[str] = None,
                       parametri: Optional[Dict[str, Any]] = None,
                       dal_ms: Optional[int] = None) -> CERT.Referto:
    """Un evento, uno scenario, un referto. E' il contratto del banco comune.

    07/10 (Applica bot): ``parametri`` = sostituzioni del catalogo
    (``parametri_modificabili``) nella riga del bot (``params``, ``stake``: la
    strada della UI), ``dal_ms`` = istante in cui l'utente arma il bot."""
    del campioni_diff        # il diff dello scanner non si applica: i bot tennis
    # non passano dalla riga di scan (leggono il MarketBook direttamente)
    from ...backtest import banco_comune as BC

    ref = CERT.Referto(event_id=str(event_id), bot=bot, scenario=scenario)
    azzerate = _azzera_stato_di_processo()
    if azzerate:
        ref.note.append("cache di processo azzerate: %s" % ", ".join(azzerate))

    raw, score = percorsi(data_dir, event_id)
    if not os.path.exists(raw):
        ref.note.append("registrazione assente: %s" % raw)
        return ref
    ref.note.append("qualita' registrazione: %s"
                    % qualita_registrazione(data_dir, event_id))

    market_id, _ordine = mercato_dal_raw(raw)
    if not market_id:
        ref.note.append("nessun MATCH_ODDS nel raw: il bot non ha un mercato")
        return ref

    punteggi = carica_punteggi(score)
    if not punteggi:
        ref.note.append("sidecar punteggi assente: `strat.score` resta None per "
                        "tutta la partita (tennis_pro non aprira' mai)")
    else:
        ref.note.append("punteggi: %d campioni dal sidecar (orologio del poll "
                        "IPS, non del mercato: vedi dichiarazione 2)" % len(punteggi))

    catalogo: Dict[str, int] = {}
    if scenario != "catalogo-assente":
        catalogo = catalogo_dichiarato(data_dir, event_id, nomi, market_id=market_id)
        if catalogo:
            ref.note.append("catalogo DICHIARATO (il raw non lo contiene): %s"
                            % ", ".join(sorted(catalogo)))
        else:
            ref.note.append("catalogo NON disponibile: ne' --nomi ne' _names.json")
    else:
        ref.note.append("scenario `catalogo-assente`: la mappa dei nomi NON e' "
                        "dichiarata (limite 1 del banco)")

    modalita = modalita_scenario(scenario)
    extra = parametri_scenario(scenario, bot)
    stake = stake_scenario(scenario, 2.0)
    # 07/10 (Applica bot): le sostituzioni dell'utente nella riga del bot
    sost = VB.valida(parametri_modificabili(scenario, bot), parametri) if parametri else {}
    if sost:
        if "stake" in sost:
            stake = float(sost["stake"])
        extra = dict(extra)
        extra.update({k: v for k, v in sost.items() if k != "stake"})
        if float(extra.get("price_min", 0.0) or 0.0) > float(extra.get("price_max", 1e9) or 1e9):
            raise ValueError("parametri price_min (%s) e price_max (%s): il minimo supera "
                             "il massimo" % (extra.get("price_min"), extra.get("price_max")))
        ref.note.append("VARIANTE DEI PARAMETRI (la strategia non cambia): "
                        + ", ".join("%s=%s" % kv for kv in sorted(sost.items())))
    accensione = VB.Accensione(VB.controlla_dal_ms(dal_ms))
    attivita: List[Tuple[str, Dict[str, Any]]] = []

    def _sink(kind: str, payload: Dict[str, Any]) -> None:
        attivita.append((str(kind), dict(payload or {})))

    control: Dict[str, Any] = {
        "event_id": str(event_id), "bot_key": bot, "status": "running",
        "stake": stake, "params": dict(extra), "stats": None,
    }
    dry = dry_run_scenario(scenario)
    if dry is not None:
        control["dry_run"] = dry
    # T1 (24/09): la riga per partita porta la modalita' DEL BOT, come la scrive
    # il ponte (`tennis_bot_service.riconcilia_interruttori`). Lo scenario `live`
    # e' un bot acceso in LIVE dall'utente: senza `mode='live'` il runner lo
    # eseguirebbe PAPER (riga senza modalita' = paper, mai ereditata dal runner).
    control["mode"] = modalita_bot_scenario(scenario)
    # la modalita' con cui il bot ESEGUE (B8, specchio, esposizioni): LIVE solo
    # se runner LIVE e riga live (`guardie_tennis.modalita_esecuzione_bot`)
    modalita_bot = "LIVE" if (modalita == "LIVE" and control["mode"] == "live") else "PAPER"
    soldi_veri = SCENARI_SOLDI_VERI.get(scenario)
    # N3 (28/09): l'interruttore delle uscite, DICHIARATO. Senza la chiave la
    # funzione di produzione darebbe MANUALI (default dal 25/09 sera).
    control["uscite_automatiche"] = uscite_automatiche_scenario(scenario)
    if control["uscite_automatiche"]:
        ref.note.append(NOTA_USCITE_AUTO)

    from betfairlightweight.filters import streaming_market_data_filter
    from flumine import FlumineSimulation

    with _modalita_dichiarata(modalita):
        from ..tennis_runner import (
            LADDER_DEPTH, STREAM_FIELDS, TENNIS_PAPER_LATENCY_MS_DEFAULT,
            _instantiate_bot,
        )

        data_filter = streaming_market_data_filter(
            fields=list(STREAM_FIELDS), ladder_levels=LADDER_DEPTH)
        with BC.simulazione_flumine() as fconf:
            # LA LATENZA DI PIAZZAMENTO E' QUELLA DEL PAPER TENNIS DI PRODUZIONE
            # (`build_order_client`: 600 ms di rete/processing NOSTRI). Il
            # betDelay in-play lo aggiunge flumine dal marketDefinition
            # streamato: `simulated_delay = place_latency + bet_delay`.
            lat = float(os.getenv("TENNIS_PAPER_LATENCY_MS",
                                  str(TENNIS_PAPER_LATENCY_MS_DEFAULT)) or 0)
            fconf.place_latency = max(0.0, lat) / 1000.0
            ref.note.append("place_latency %s ms (paper tennis di produzione) + "
                            "betDelay dal marketDefinition, dormito da flumine"
                            % int(lat))
            # il client del framework (simulato del banco). Con «soldi veri» e'
            # anche il client PAPER affiancato del runner LIVE, e il client REALE
            # e' la sua vista `ClienteLiveBanco` (stessa esecuzione simulata).
            cliente = BC.cliente_simulato()
            cliente_reale: Optional[Any] = None
            if soldi_veri is not None:
                from ...backtest.porta_banco import ClienteLiveBanco

                cliente_reale = ClienteLiveBanco(cliente)
            try:
                strat = _instantiate_bot(bot, control, market_id, catalogo,
                                         _sink, data_filter, modalita,
                                         market_ids=[market_id],
                                         client_paper=(cliente if soldi_veri is not None
                                                       else None))
            except Exception as ex:  # noqa: BLE001 - un'istanza che non nasce E' un referto
                ref.note.append("il bot non si e' istanziato: %s: %s"
                                % (type(ex).__name__, ex))
                return ref
            if cliente_reale is not None and modalita_bot == "LIVE":
                # in produzione il client di DEFAULT del runner LIVE e' quello
                # reale: nel banco il default e' simulato, quindi il bot live si
                # instrada sul `ClienteLiveBanco` con la funzione di produzione
                from .. import guardie_tennis as GT

                GT.instrada_ordini_su_client(strat, cliente_reale)
            ref.note.append("uscite EFFETTIVE del bot istanziato: %s"
                            % ("AUTOMATICHE" if getattr(strat, "uscite_automatiche",
                                                        False) is True else "MANUALI"))
            # il market_filter del banco: la registrazione al posto dello stream
            strat.market_filter = {"markets": [raw]}
            cap = getattr(strat, "max_selection_exposure", None)

            quadro = FlumineSimulation(client=cliente)
            BC.assicura_middleware_simulato(quadro)
            if soldi_veri is not None:
                # i trading control VERI del runner tennis con gli ordini accesi
                from ..tennis_runner import aggiungi_controlli_ordini

                aggiungi_controlli_ordini(quadro)
                ref.note.append(
                    "SOLDI VERI: riga del bot mode=%s, «Ordini reali» %s di questo "
                    "avvio, runner col tetto LIVE e i trading control del runner "
                    "(modalita' del bot, kill-switch, terza rete); bot eseguito in %s"
                    % (soldi_veri[0], soldi_veri[1].upper(), modalita_bot))
            rifiuta: Optional[Any] = None
            if scenario == "rifiuti-betfair":
                rifiuta = _rifiuta_tutto(quadro)
                quadro.trading_controls.append(rifiuta)
                ref.note.append("guasto iniettato: ogni piazzamento e' RIFIUTATO "
                                "da un trading control di flumine (place_order "
                                "torna False, stato Violation)")
            quadro.add_strategy(strat)

            def _riavvia(vecchio: Any) -> Any:
                """Ri-istanzia il bot come fa il rebuild dello stream: stessa
                funzione di produzione, stesso control, carry-over delle stats
                (che `_instantiate_bot` prende da `control['stats']`)."""
                ctrl = dict(control)
                ctrl["stats"] = dict(getattr(vecchio, "stats", None) or {})
                nuovo = _instantiate_bot(bot, ctrl, market_id, catalogo, _sink,
                                         data_filter, modalita,
                                         market_ids=[market_id])
                nuovo.market_filter = {"markets": [raw]}
                quadro.add_strategy(nuovo)
                # lo stream e' lo stesso (stesso market_filter): il ponte deve
                # continuare a vedere gli stessi `stream_ids`
                try:
                    nuovo.stream_ids = set(vecchio.stream_ids)
                except Exception:  # noqa: BLE001 - flumine li ha gia' assegnati
                    pass
                return nuovo

            ponte = _Ponte(
                strat=strat, bot_key=bot, event_id=str(event_id),
                market_id=market_id, scenario=scenario, punteggi=punteggi,
                referto=ref, quadro=quadro, modalita=modalita_bot, stake=stake,
                cap=cap, attivita=attivita, rifiuta=rifiuta, ogni_ms=ogni_ms,
                feed_stantio_da_ms=None,
                riavvia=_riavvia if scenario == "riavvio" else None,
            )
            ponte.accensione = accensione
            if bot == "tennis_pro":
                # 08/10 (cantiere 6): il metro dei setup coi nomi (famiglia SP),
                # con lo STESSO catalogo che riceve il bot
                ponte.lettore_setup = CERT.LettoreSetupPro(catalogo)
            if punteggi:
                primo, ultimo = punteggi[0][0], punteggi[-1][0]
                ponte.imposta_finestra(primo, ultimo)
                if scenario == "feed-stantio":
                    ponte.feed_stantio_da_ms = primo + (ultimo - primo) // 3
                    ref.note.append("guasto iniettato: il punteggio smette di "
                                    "arrivare dopo il primo terzo (blackout IPS)")

            if scenario in UM.SCENARI:
                def _ordini_di(s: Any) -> List[Any]:
                    m = quadro.markets.markets.get(market_id)
                    blotter = getattr(m, "blotter", None)
                    try:
                        return list(blotter.strategy_orders(s) or []) if blotter else []
                    except Exception:  # noqa: BLE001 - blotter illeggibile
                        return []

                ponte.osservatore = UM.Osservatore(
                    scenario, strategie=lambda: [ponte.s], ordini_di=_ordini_di,
                    firma=ponte.firma if scenario == UM.SCENARIO_FIRMATE else None,
                    ruolo=ponte.ruolo_ordine,
                    resto_non_piazzabile=resto_dichiarato_dal_bot,
                    # 04/10 (decisione 1): il resto scusato, SE dichiarato dal bot,
                    # arriva al floor di legge del place-and-trim (era 0,05)
                    soglia_resto=float(_MINIMI_IT.SUBMIN_IMPORTO_FINALE_MIN))
                ref.note.append("USCITE MANUALI: interruttore spento; %s"
                                % ("il banco firma ogni proposta dopo %d s di mercato "
                                   "(params.uscite_approvate, riletta da "
                                   "`_aggiorna_uscite` ogni BOT_CONTROL_POLL_SEC)"
                                   % int(UM.FIRMA_DOPO_S)
                                   if scenario == UM.SCENARIO_FIRMATE
                                   else "nessuna firma"))

            motore = BC.MotoreReplay(quadro)
            # 07/10 (Applica bot): la CRONOLOGIA degli ordini del bot, dagli
            # ordini VERI del flumine del banco (sola lettura, dopo ogni book)
            specchio_ordini = VB.SpecchioOrdini(sorgente=bot, modo=modalita_bot.lower(),
                                                event_id=str(event_id))
            specchio_ordini.aggancia(motore)
            guasto_cp = None
            if scenario == CP.SCENARIO:
                # il RUOLO dell'ordine dalla credenza del bot (ingresso/uscita)
                guasto_cp = CP.GuastoChiusuraParziale(ruolo=ponte.ruolo_ordine)
                motore.guasto_chiusure = guasto_cp
                ponte.sorveglianza_cp = CP.Sorveglianza(guasto_cp)
            oss_um = ponte.osservatore
            if soldi_veri is not None:
                # SV1: che cosa la catena impone al client di ogni ordine
                ponte.catena_soldi_veri = (
                    "simulato" if modalita_bot != "LIVE"
                    else ("reale" if soldi_veri[1] == "live" else "nessuno_reale"))
            from ... import modo_ordini as _MO

            scelta = (_MO.dichiara_per_banco(soldi_veri[1]) if soldi_veri is not None
                      else _nessun_contesto())
            with scelta:
                if oss_um is not None:
                    with oss_um.attivo():
                        motore.esegui(ponte)
                        oss_um.giro(ponte.ultimo_ms, fine=True)
                    _chiudi_uscite_manuali(ref, oss_um)
                else:
                    motore.esegui(ponte)
            if soldi_veri is not None:
                ref.note.append(ponte.riepilogo_soldi_veri())
            if guasto_cp is not None:
                ref.note.append(guasto_cp.riepilogo())
            ref.note.append(
                "book attesi durante i piazzamenti: %d; lapse al fischio: %d; "
                "lapse alla sospensione: %d"
                % (motore.pompati, motore.lapse_al_fischio,
                   motore.lapse_alla_sospensione))
            # 08/10 (banco_comune, 6-quater): i fill dati dal MERCATO CHE ATTRAVERSA
            ref.note.append(BC.nota_fill_attraversati(motore))
            mercato = quadro.markets.markets.get(market_id)
            aperti_prima = ponte.residui_del_bot()
            ponte.chiudi(mercato)
            ref.note.append(nota_residui(attivita, aperti_prima))
            # 07/10: le righe ``betfair_live_orders`` + ``_ms`` (contratto del banco)
            ref.ordini_specchio = specchio_ordini.chiudi(VB.mercati_del_quadro(quadro))
            if accensione.attiva:
                ref.note.append(nota_accensione(accensione))

    if scenario in ("gate-aperto", "parziali", "rifiuti-betfair", "live", CP.SCENARIO,
                    SCENARIO_CHIUDI_ORA) or scenario in UM.SCENARI \
            or scenario in SCENARI_SOLDI_VERI:
        ref.note.append("SCENARIO DICHIARATO: cambiati SOLO i parametri %s "
                        "(numeri che l'utente puo' gia' cambiare dalla UI). La "
                        "strategia e' quella di produzione."
                        % sorted(extra) if extra else "stake")
    if not ref.decisioni:
        ref.note.append("il bot non ha MAI deciso: nessun controllo puo' dire "
                        "«sano», il referto dice «non lo so»")
    if bot == "tennis_pro":
        chiudi_setup_pro(ref, scenario, ponte.lettore_setup)
    return ref


def chiudi_setup_pro(ref: CERT.Referto, scenario: str,
                     lettore: Optional[CERT.LettoreSetupPro]) -> None:
    """08/10 (cantiere 6): a fine replay di tennis_pro, i controlli SP mai
    sollecitati si dichiarano NON ESERCITABILI con la causa misurata (nomi
    assenti, zero occasioni nella registrazione); negli scenari di setup il
    controllo-chiave a zero rende lo scenario NON ESERCITATO (segno NE, mai OK)."""
    for codice in sorted(CERT.SETUP_CERTIFICATI):
        non_esercitabile, _ = CERT.esito_setup(codice, ref.sollecitati, lettore)
        if non_esercitabile:
            ref.non_esercitabili[codice] = non_esercitabile
    chiave = CONTROLLO_DEL_SETUP.get(scenario)
    if chiave is None:
        return
    if lettore is not None:
        ref.note.append(lettore.misura())
    _, non_esercitato = CERT.esito_setup(chiave, ref.sollecitati, lettore)
    if non_esercitato:
        ref.non_esercitato.append(non_esercitato)


def nota_residui(attivita: List[Tuple[str, Dict[str, Any]]],
                 aperti_a_fine: List[Dict[str, Any]]) -> str:
    """04/10 (decisione 1 dell'utente): i residui non piazzabili della partita,
    in EUR (riga del referto: serve all'utente)."""
    dich = [p for k, p in attivita if k == "residuo_non_piazzabile"]
    chiusi = sum(1 for k, _p in attivita if k == "residuo_chiuso")
    regolati = [p for k, p in attivita if k == "residuo_regolato"]
    aperti = [r for r in aperti_a_fine if float(r.get("importo") or 0.0) >= 0.0]
    return ("RESIDUI (decisione 1): dichiarati %d (importi %s EUR, sbilancio %s EUR), "
            "tornati pari %d; regolati col mercato %d (se vince %s / se perde %s EUR); "
            "aperti a fine partita %d (importi %s EUR, sbilancio "
            "totale %.2f EUR, se vince %.2f / se perde %.2f)"
            % (len(dich), [p.get("importo") for p in dich],
               [p.get("sbilancio") for p in dich], chiusi, len(regolati),
               [p.get("se_vince") for p in regolati], [p.get("se_perde") for p in regolati],
               len(aperti),
               [r.get("importo") for r in aperti],
               sum(float(r.get("sbilancio") or 0.0) for r in aperti),
               sum(float(r.get("se_vince") or 0.0) for r in aperti),
               sum(float(r.get("se_perde") or 0.0) for r in aperti)))


def resto_dichiarato_dal_bot(s: Any, sel: Any, lato: str, resto: float) -> bool:
    """N3 UF2: il bot ha DICHIARATO non piazzabile questo resto? Lo scalper
    tennis tiene la sua memoria dei `min_bet_skip` gia' scritti
    (`TennisScalperStrategy._min_bet_detto`: (selezione, lato, size)); gli altri
    bot tennis non hanno un resto non piazzabile (place-and-trim di D2).
    04/10 (decisione 1 dell'utente): anche il residuo che il bot RICORDA
    (`residui_ricordati`, stesso lato, importo al centesimo)."""
    mem = getattr(getattr(s, "residui_ricordati", None), "aperti", None) or {}
    for r in list(mem.values()):
        try:
            if (int(r.get("selection_id")) == int(sel)
                    and str(r.get("lato")).upper() == str(lato).upper()
                    and any(abs(float(x) - float(resto)) <= 0.011
                            for x in (r.get("importi_dichiarati") or [r.get("importo")]))):
                return True
        except (TypeError, ValueError):
            continue
    detto = getattr(s, "_min_bet_detto", None) or ()
    for k in list(detto):
        try:
            if (int(k[0]) == int(sel) and str(k[1]).upper() == str(lato).upper()
                    and abs(float(k[2]) - float(resto)) < 1e-9):
                return True
        except (TypeError, ValueError, IndexError):
            continue
    return False


def _chiudi_uscite_manuali(ref: CERT.Referto, oss: Any) -> None:
    """N3: i controlli UM/UF nel referto (sollecitati, violazioni, riepilogo)."""
    for cod, n in oss.sollecitati.items():
        ref.sollecitati[cod] = ref.sollecitati.get(cod, 0) + n
    for cod, reg, det, quando in oss.violazioni:
        ref.violazioni.append(CERT.Violazione(cod, reg, det, quando))
    ref.note.append(oss.riepilogo())
    mai = [c for c, _r in UM.elenco_controlli(oss.scenario) if not oss.sollecitati.get(c)]
    if mai:
        ref.note.append("USCITE MANUALI: controlli MAI sollecitati (non lo so): %s"
                        % ", ".join(mai))


def certifica_evento(event_id: str, *, data_dir: str, scenario: str = "base",
                     ogni_ms: int = 1000, campioni_diff: int = 0,
                     bot: str = "tennis_flb",
                     nomi: Optional[str] = None) -> CERT.Referto:
    """Alias: `certifica.py` chiama `certifica_scenario`, il resto del repo
    chiama `certifica_evento`. Sono la stessa cosa."""
    return certifica_scenario(event_id, data_dir=data_dir, scenario=scenario,
                              ogni_ms=ogni_ms, campioni_diff=campioni_diff,
                              bot=bot, nomi=nomi)


# ---------------------------------------------------------------------------
# le quattro entrate del registro: una per bot (la firma del banco e' fissa)
# ---------------------------------------------------------------------------
def _per_bot(bot: str):
    def _f(event_id: str, *, data_dir: str, scenario: str = "base",
           ogni_ms: int = 1000, campioni_diff: int = 0,
           parametri: Optional[Dict[str, Any]] = None,
           dal_ms: Optional[int] = None) -> CERT.Referto:
        return certifica_scenario(event_id, data_dir=data_dir, scenario=scenario,
                                  ogni_ms=ogni_ms, campioni_diff=campioni_diff,
                                  bot=bot, parametri=parametri, dal_ms=dal_ms)
    _f.__name__ = "certifica_scenario_%s" % bot
    _f.__doc__ = ("Il replay di `%s` su UN evento registrato: firma del banco "
                  "comune (`MODELLO_BOT_NUOVO.md` passo 2)." % bot)
    return _f


certifica_scenario_tennis_scalper = _per_bot("tennis_scalper")
certifica_scenario_tennis_pro = _per_bot("tennis_pro")
certifica_scenario_tennis_flb = _per_bot("tennis_flb")
certifica_scenario_tennis_swing = _per_bot("tennis_swing")


# ---------------------------------------------------------------------------
# il comando
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Replay di un bot tennis sulle registrazioni reali")
    p.add_argument("bot", choices=sorted(
        ("tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing")))
    p.add_argument("eventi", nargs="*", default=[EVENTO_DI_RIFERIMENTO])
    p.add_argument("--data-dir", default=None)
    p.add_argument("--scenari", default="base")
    p.add_argument("--ogni-ms", type=int, default=1000)
    p.add_argument("--nomi", default=None,
                   help="catalogo dichiarato: \"Nome=selid,Nome=selid\"")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    data_dir = a.data_dir or cartella_predefinita()
    eventi = a.eventi or [EVENTO_DI_RIFERIMENTO]
    scelti = (list(scenari_del_bot(a.bot)) if a.scenari.strip().lower() == "tutti"
              else [x.strip() for x in a.scenari.split(",") if x.strip()])
    imp = impronta()
    print("BOT: %s | flumine %s | betfairlightweight %s | codice bot %s"
          % (a.bot, imp["flumine"], imp["betfairlightweight"], imp["codice_bot"]))
    sollecitati: Dict[str, int] = {}
    tot = 0
    for sc in scelti:
        for ev in eventi:
            r = certifica_scenario(ev, data_dir=data_dir, scenario=sc,
                                   ogni_ms=a.ogni_ms, bot=a.bot, nomi=a.nomi)
            tot += len(r.violazioni)
            for cod, n in r.sollecitati.items():
                sollecitati[cod] = sollecitati.get(cod, 0) + n
            print("%s %s [%s]  tick=%d decisioni=%d azioni=%d ordini=%d "
                  "abbinati=%d stati=%s"
                  % ("OK " if r.pulita else "KO ", ev, sc, r.tick, r.decisioni,
                     r.azioni, r.ordini_piazzati, r.ordini_abbinati,
                     ",".join(r.stati_visti) or "-"))
            for nota in r.note:
                print("      nota: %s" % nota)
            for cod, n in sorted(r.per_codice().items()):
                esempio = next(v for v in r.violazioni if v.codice == cod)
                print("      %s x%d: %s" % (cod, n, esempio.regola))
                print("           es. %s" % esempio.dettaglio)
            if r.stats_finali:
                print("      stats finali: %s" % r.stats_finali)
    print()
    print("COPERTURA DEI CONTROLLI:")
    for cod, reg in CERT.elenco_controlli():
        n = sollecitati.get(cod, 0)
        print("  %s %-3s x%-7d %s" % ("  " if n else "??", cod, n, reg[:66]))
    mai = CERT.mai_sollecitati(sollecitati)
    if mai:
        print()
        print("?? MAI SOLLECITATI: %d su %d. Su questi il referto dice «non lo so»:"
              % (len(mai), len(CERT.elenco_controlli())))
        for cod, reg in mai:
            print("     %s: %s" % (cod, reg))
    return 0 if tot == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
