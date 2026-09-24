"""IL REGISTRO DEI BOT — chi va in produzione passa da qui, e da flumine.

Ordine dell'utente (16/09/2026):

    «devi rendere questo processo riutilizzabile: ogni nuovo bot, o i
    precedenti, se voglio testarli devono passare da flumine ed essere
    certificati; l'intero comparto backtest deve essere assolutamente veritiero
    e applicare i codici di produzione dei bot a partite registrate,
    replicandone l'esatto funzionamento che avrebbe in live; da oggi standard e
    usato di default.»

Questo file e' l'elenco, in un posto solo, di TUTTI i bot che operano in
produzione, e per ciascuno dice:

  * `replay`     — la funzione che fa rivivere UN evento registrato passando dal
                   CODICE DI PRODUZIONE del bot (servizio vero, feed vero,
                   ordini veri su flumine). `None` = il replay non c'e' ancora;
  * `controlli`  — il modulo che verifica la CONDOTTA (le regole della spec),
                   con `elenco_controlli()` e `mai_sollecitati()`. `None` = non
                   c'e' ancora, e va detto ad alta voce;
  * `spec`       — il documento che dice come il bot DEVE comportarsi;
  * `sport`, `mercati`, `cartella` — dove sono le registrazioni e che cosa gli
                   serve dentro;
  * `moduli_produzione` — i moduli che `desktop/main.js` lancia davvero.

Un bot NUOVO non e' "in produzione" finche' non compare qui: il test di
contratto `Betfair/stream/tests/test_registro_bot_2026_09_16.py` legge le fonti
di verita' della produzione (i runner di `desktop/main.js`, le `variants` della
Safe, il `_BOT_REGISTRY` del tennis, il servizio scalper) e diventa ROSSO se
trova un bot che non e' registrato.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


def _cartella_calcio() -> str:
    from ..config_stream import DATA_DIR

    return DATA_DIR


def _cartella_tennis() -> str:
    """Le registrazioni tennis: `TENNIS_RECORD_DIR`/<giorno>, la stessa radice
    del recorder (`tennis_live/tennis_recorder.default_record_dir`). Qui si
    torna la RADICE: il giorno lo sceglie chi certifica (`--data-dir`)."""
    radice = (os.getenv("TENNIS_RECORD_DIR", "").strip()
              or os.path.join(os.path.expanduser("~"), "Desktop", "tennis_rec"))
    giorni = []
    if os.path.isdir(radice):
        giorni = sorted(d for d in os.listdir(radice) if d.isdigit())
    return os.path.join(radice, giorni[-1]) if giorni else radice


def _risolvi(percorso: Optional[str]) -> Optional[Any]:
    """"modulo:nome" -> l'oggetto. Import PIGRO: il registro si puo' leggere
    (e il test di contratto girare) senza tirarsi dietro flumine e i bot."""
    if not percorso:
        return None
    modulo, _, nome = percorso.partition(":")
    mod = importlib.import_module(modulo)
    return getattr(mod, nome) if nome else mod


@dataclass(frozen=True)
class BotRegistrato:
    """Un bot che opera in produzione, e come lo si certifica sul banco."""

    nome: str
    sport: str
    descrizione: str
    # moduli che `desktop/main.js` lancia (o che ospitano il bot)
    moduli_produzione: Tuple[str, ...] = ()
    # i tipi di mercato Betfair che gli servono nel payload di scan
    mercati: Tuple[str, ...] = ()
    # "modulo:funzione" che certifica UN evento -> Referto
    replay: Optional[str] = None
    # "modulo:DIZIONARIO" degli scenari (nome -> descrizione)
    scenari: Optional[str] = None
    # modulo dei controlli di condotta
    controlli: Optional[str] = None
    # il documento che dice come DEVE comportarsi
    spec: Optional[str] = None
    # perche' i controlli non ci sono ancora (obbligatorio se controlli is None)
    motivo_senza_controlli: str = ""
    cartella: Callable[[], str] = _cartella_calcio

    # ------------------------------------------------------------- comodita'
    @property
    def certificabile(self) -> bool:
        """Ha SIA il replay SIA i controlli: solo allora un referto vale."""
        return bool(self.replay) and bool(self.controlli)

    def funzione_replay(self) -> Optional[Callable[..., Any]]:
        return _risolvi(self.replay)

    def modulo_controlli(self) -> Optional[Any]:
        return _risolvi(self.controlli)

    def elenco_scenari(self) -> Dict[str, str]:
        sc = _risolvi(self.scenari)
        return dict(sc or {"base": "come gira in produzione"})


# ---------------------------------------------------------------------------
# I BOT
# ---------------------------------------------------------------------------
_REGISTRO: Tuple[BotRegistrato, ...] = (
    BotRegistrato(
        nome="mike",
        sport="calcio",
        descrizione="Under 3.5 pre-KO + copertura Over 4.5 + re-ingresso",
        moduli_produzione=("Betfair.mike.service",),
        mercati=("OVER_UNDER_35", "OVER_UNDER_45"),
        replay="Betfair.mike.tools.replay_registrazioni:certifica_scenario",
        scenari="Betfair.mike.tools.replay_registrazioni:SCENARI_DESCRITTI",
        controlli="Betfair.mike.certificazione",
        spec="Betfair/mike/COSTITUZIONE_MIKE.md",
    ),
    BotRegistrato(
        nome="omega",
        sport="calcio",
        descrizione="due gambe sul Correct Score (1T + FT) con green-up",
        moduli_produzione=("Betfair.omega.omega_service",),
        mercati=("CORRECT_SCORE", "HALF_TIME_SCORE", "MATCH_ODDS"),
        replay="Betfair.omega.tools.replay_registrazioni:certifica_scenario",
        scenari="Betfair.omega.tools.replay_registrazioni:SCENARI_DESCRITTI",
        controlli="Betfair.omega.certificazione",
        spec="Betfair/omega/COSTITUZIONE_OMEGA.md",
    ),
    BotRegistrato(
        nome="safe_base",
        sport="calcio",
        descrizione="Safe Strategy, variante BASE (riferimento 1X2 pre-KO)",
        moduli_produzione=("Betfair.safe_strategy.bot_service",),
        mercati=("MATCH_ODDS", "CORRECT_SCORE"),
        replay="Betfair.safe_strategy.tools.replay_registrazioni:certifica_scenario",
        scenari="Betfair.safe_strategy.tools.replay_registrazioni:SCENARI_DESCRITTI",
        controlli="Betfair.safe_strategy.certificazione",
        spec="SPEC_STRATEGIA_S.md",
    ),
    BotRegistrato(
        nome="safe_esatto",
        sport="calcio",
        descrizione="Safe Strategy, variante ESATTO (Correct Score)",
        moduli_produzione=("Betfair.safe_strategy.bot_service",),
        mercati=("CORRECT_SCORE",),
        replay="Betfair.safe_strategy.tools.replay_registrazioni:certifica_scenario",
        scenari="Betfair.safe_strategy.tools.replay_registrazioni:SCENARI_DESCRITTI",
        controlli="Betfair.safe_strategy.certificazione",
        spec="SPEC_STRATEGIA_S.md",
    ),
    BotRegistrato(
        nome="safe_punta",
        sport="calcio",
        descrizione="Safe Strategy, variante PUNTA",
        moduli_produzione=("Betfair.safe_strategy.bot_service",),
        mercati=("MATCH_ODDS",),
        replay="Betfair.safe_strategy.tools.replay_registrazioni:certifica_scenario",
        scenari="Betfair.safe_strategy.tools.replay_registrazioni:SCENARI_DESCRITTI",
        controlli="Betfair.safe_strategy.certificazione",
        spec="SPEC_STRATEGIA_S.md",
    ),
    BotRegistrato(
        nome="safe_tennis",
        sport="tennis",
        descrizione="Safe Strategy sul tennis (take profit / stop, uscite approvate)",
        moduli_produzione=("Betfair.safe_strategy.bot_service",),
        mercati=("MATCH_ODDS",),
        replay="Betfair.safe_strategy.tools.replay_tennis:certifica_scenario",
        scenari="Betfair.safe_strategy.tools.replay_tennis:SCENARI_DESCRITTI",
        controlli="Betfair.safe_strategy.certificazione_tennis",
        spec="SPEC_STRATEGIA_S.md",
        cartella=_cartella_tennis,
    ),
    BotRegistrato(
        nome="scalper_calcio",
        sport="calcio",
        descrizione="scalper calcio pre-match (maker, una sessione-processo per evento)",
        # 24/09: il replay monta il SERVIZIO di produzione intero
        # (`scalper_session.run_session`: parametri, client paper/live,
        # heartbeat, stop, cap globale, fine vita, crash) con la strategia vera
        # (`scalper_bot.ScalperStrategy`) sul banco comune; i finti iniettati
        # sono elencati in testa al modulo del replay. `scalper_bot` sta qui
        # perche' l'impronta del referto deve cambiare se cambia la strategia.
        moduli_produzione=("Betfair.stream.scalper.scalper_service",
                           "Betfair.stream.scalper.scalper_session",
                           "Betfair.stream.scalper.scalper_bot"),
        mercati=("MATCH_ODDS", "OVER_UNDER_15", "OVER_UNDER_25", "OVER_UNDER_35"),
        replay="Betfair.stream.scalper.tools.replay_registrazioni:certifica_scenario",
        scenari="Betfair.stream.scalper.tools.replay_registrazioni:SCENARI_DESCRITTI",
        controlli="Betfair.stream.scalper.certificazione",
        spec="Betfair/stream/scalper/BIBBIA_SCALPER_CALCIO.md",
    ),
    # ------------------------------------------------------------------
    # I QUATTRO BOT TENNIS (17/09/2026)
    # Il servizio di produzione e' `tennis_runner`: il replay istanzia il bot
    # con la SUA funzione `_instantiate_bot` (preset, dry_run dalla modalita',
    # tetti di esposizione, scoping per mercato), gli passa il punteggio con
    # `parse_tennis_scores` alla cadenza del `score_and_now_worker` e giudica
    # anche le righe che `tennis_live_order_worker._mirror_order` scriverebbe.
    # Mai una copia di laboratorio (`tennis_lab*` resta fuori dalla produzione).
    # ------------------------------------------------------------------
    BotRegistrato(
        nome="tennis_scalper",
        sport="tennis",
        descrizione="scalper tennis: market-making a due gambe sul MATCH_ODDS",
        moduli_produzione=("Betfair.stream.tennis_live.tennis_runner",),
        mercati=("MATCH_ODDS",),
        replay="Betfair.stream.tennis_live.tools.replay_bot:certifica_scenario_tennis_scalper",
        scenari="Betfair.stream.tennis_live.tools.replay_bot:SCENARI_DESCRITTI",
        controlli="Betfair.stream.tennis_live.certificazione_bot",
        spec="TENNIS_BOT_DOSSIER.md",
        cartella=_cartella_tennis,
    ),
    BotRegistrato(
        nome="tennis_pro",
        sport="tennis",
        descrizione="tennis PRO: direzionale score-driven, sei setup sul punteggio IPS",
        moduli_produzione=("Betfair.stream.tennis_live.tennis_runner",),
        mercati=("MATCH_ODDS",),
        replay="Betfair.stream.tennis_live.tools.replay_bot:certifica_scenario_tennis_pro",
        scenari="Betfair.stream.tennis_live.tools.replay_bot:SCENARI_DESCRITTI",
        controlli="Betfair.stream.tennis_live.certificazione_bot",
        spec="TENNIS_BOT_DOSSIER.md",
        cartella=_cartella_tennis,
    ),
    BotRegistrato(
        nome="tennis_flb",
        sport="tennis",
        descrizione="tennis FLB: lay del favorito estremo, senza stop (favourite-longshot bias)",
        moduli_produzione=("Betfair.stream.tennis_live.tennis_runner",),
        mercati=("MATCH_ODDS",),
        replay="Betfair.stream.tennis_live.tools.replay_bot:certifica_scenario_tennis_flb",
        scenari="Betfair.stream.tennis_live.tools.replay_bot:SCENARI_DESCRITTI",
        controlli="Betfair.stream.tennis_live.certificazione_bot",
        spec="TENNIS_BOT_DOSSIER.md",
        cartella=_cartella_tennis,
    ),
    BotRegistrato(
        nome="tennis_swing",
        sport="tennis",
        descrizione="tennis SWING: fade degli estremi del favorito (z robusto + ER + RSI)",
        moduli_produzione=("Betfair.stream.tennis_live.tennis_runner",),
        mercati=("MATCH_ODDS",),
        replay="Betfair.stream.tennis_live.tools.replay_bot:certifica_scenario_tennis_swing",
        scenari="Betfair.stream.tennis_live.tools.replay_bot:SCENARI_DESCRITTI",
        controlli="Betfair.stream.tennis_live.certificazione_bot",
        spec="TENNIS_BOT_DOSSIER.md",
        cartella=_cartella_tennis,
    ),
)

REGISTRO: Dict[str, BotRegistrato] = {b.nome: b for b in _REGISTRO}


# ---------------------------------------------------------------------------
# I processi di produzione che NON sono bot
# ---------------------------------------------------------------------------
# `desktop/main.js` lancia anche cose che non operano: il feed, i ponti verso la
# UI, un job di quote. Sono dichiarate qui UNA PER UNA col motivo, cosi' il test
# di contratto puo' distinguere "non e' un bot" da "bot dimenticato".
NON_BOT: Dict[str, str] = {
    "Betfair.safe_strategy.service": "SCANNER: pubblica i fatti, non piazza mai un ordine",
    "Betfair.stream.watchdog": "guardiano: riavvia un runner, non opera",
    "Betfair.stream.tennis_live.tennis_bot_service": "ponte verso la UI (--bridge-only)",
    "betfair_tennis_odds.py": "job di quote tennis: nessun ordine",
    "Betfair.stream.runner": "runner calcio: ospita gli scalper, registrati a parte",
}


def elenco() -> List[BotRegistrato]:
    return list(_REGISTRO)


def bot(nome: str) -> BotRegistrato:
    try:
        return REGISTRO[str(nome)]
    except KeyError:
        raise KeyError(
            f"bot '{nome}' non registrato. Registrati: {', '.join(sorted(REGISTRO))}. "
            "Un bot che opera in produzione DEVE stare in "
            "Betfair/stream/backtest/registro_bot.py (vedi MODELLO_BOT_NUOVO.md)."
        ) from None


def senza_certificazione() -> List[BotRegistrato]:
    """I bot registrati che NON hanno ancora replay+controlli. Vanno elencati
    ad alta voce: "registrato" non vuol dire "certificato"."""
    return [b for b in _REGISTRO if not b.certificabile]
