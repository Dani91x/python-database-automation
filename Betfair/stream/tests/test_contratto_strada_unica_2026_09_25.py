# -*- coding: utf-8 -*-
"""IL CONTRATTO "strada unica": chi puo' chiamare l'Exchange per un ordine (F10a).

Ordine dell'utente (via audit 24/09, par.4.6 punto 6, e piano par.5 riga F10a):
nessuna strada nuova verso ``placeOrders`` si aggiunge di nascosto. Oggi (24/09)
ce ne sono gia' SETTE (tabella par.1.0 di ``AUDIT_2026-09-24/AUDIT_STRADE_ORDINE_2026-09-24.md``):
S1 (coda calcio), S2 (canale 47331), S2t (canale 47332), S3a (REST diretto),
S3b (flumine in-process dei 4 bot tennis), S4a (scalper calcio) e S4b (CLI/8787/
coda pre-match). Il 25/09 il canale calcio e' entrato in produzione dietro un
motore (``motore_ordini.py``): quel motore NON aggiunge un ottavo caller, perche'
richiama ``live_order_worker._dispatch`` gia' registrato qui sotto (verificato
con ``grep -n "_dispatch" Betfair/stream/motore_ordini.py``).

COME FUNZIONA
-------------
Il test scandisce (con ``ast``, non con una regex sola, per non confondere UNA
``def place_order(...)`` con una CHIAMATA a ``place_order(...)``, e per non
prendere ``replaceOrders`` per ``placeOrders`` — la seconda stringa e' contenuta
dentro la prima) ogni ``.py`` sotto ``Betfair/`` che NON sia un test o uno
strumento (``tests/``, ``tools/``, ``test_*.py``: elencati a parte, non "produzione")
cercando:
  - chiamate a un metodo o funzione chiamata ``place_order``, ``place_orders``,
    ``cancel_orders`` o ``replace_orders`` (qualunque sia l'oggetto: ``market.``,
    ``client.``, o una funzione importata come ``place_order(...)``);
  - la stringa letterale del metodo JSON-RPC diretto (``SportsAPING/v1.0/placeOrders``
    e affini), per beccare un eventuale bypass del client REST unico.

``cancel_orders``/``replace_orders`` SONO nel contratto: ``omega_market.py`` li usa
per il place-and-trim (cancelOrders/replaceOrders, gia' nel contratto submin) e
``scalper_session.py`` li usa per lo SWEEP CANCEL di emergenza via REST se il
thread di flumine muore (bypassa il Market: e' un secondo modo di toccare
l'Exchange dallo stesso servizio, quindi va dichiarato qui).

Il test e' ROSSO in DUE direzioni (come il contratto del submin,
``test_submin_contratto_chiamanti_2026_09_17.py``, e il registro dei bot,
``test_registro_bot_2026_09_16.py``):
  a) un modulo chiama e NON e' nell'elenco (strada nuova non dichiarata);
  b) un modulo e' nell'elenco ma non chiama piu' (elenco stantio, che nasconde
     una strada tolta senza dirlo, o un refuso).

TROVATO DA F10A IL 25/09, RISOLTO LO STESSO GIORNO (decisione dell'utente):
la scansione aveva trovato 4 chiamanti a ``market.place_order`` non previsti
dall'audit del 24/09 e non importati da nessun runner di produzione —
``Betfair/stream/scalper_lab/{grid_strategy,scalper_bot_base,theta_strategy}.py``
e ``Betfair/stream/tennis_scalper/tennis_lab.py`` (dettaglio:
``AUDIT_2026-09-25/F10A_CONTRATTO_STRADA_UNICA_2026-09-25.md``). L'utente ha
scelto di spostarli fuori da ``Betfair/``: vivono ora sotto ``laboratorio/``
(radice del repo, fuori da questo albero), insieme ai moduli del lab che
dipendevano da loro (``bt_lab.py``/``bt_theta.py``/ecc. per scalper_lab;
``lab_grid*.py``/``tennis_lab_score.py``/``validate.py`` per il lab tennis).
La scansione sotto copre solo ``Betfair/``: quei moduli non ci sono piu' e le
loro 4 righe ``NON_PRODUZIONE?`` sono state tolte da
``_CHIAMANTI_AUTORIZZATI`` (altrimenti ``test_elenco_non_stantio`` e
``test_ogni_modulo_autorizzato_esiste_davvero`` diventerebbero rossi).
``test_laboratorio_non_importato_da_betfair_ne_da_desktop`` sotto verifica che
nessuno sotto ``Betfair/`` o ``desktop/`` importi da ``laboratorio``: e' la
condizione perche' lo spostamento non riapra una strada nascosta. Referto
completo: ``AUDIT_2026-09-25/LABORATORIO_SPOSTAMENTO_2026-09-25.md``.
"""
from __future__ import annotations

import ast
import pathlib
from dataclasses import dataclass
from typing import Dict, List, Tuple

import pytest

_RADICE = pathlib.Path(__file__).resolve().parents[3]
_BETFAIR = _RADICE / "Betfair"

# i nomi che, se chiamati, raggiungono (o possono raggiungere) placeOrders
_NOMI_CHIAMATA = frozenset({"place_order", "place_orders", "cancel_orders", "replace_orders"})
# il metodo JSON-RPC diretto: per beccare un bypass del client REST unico
# (Betfair/client.py). NB: "replaceOrders" CONTIENE la sottostringa "placeOrders"
# ("re" + "placeOrders"): per questo serve ast su ast.Constant, non un grep sulla
# stringa "placeOrders" nuda, che darebbe un falso positivo su ogni commento che
# nomina replaceOrders (successo gia' visto nella ricognizione manuale del 25/09).
_METODI_JSONRPC = (
    "SportsAPING/v1.0/placeOrders",
    "SportsAPING/v1.0/cancelOrders",
    "SportsAPING/v1.0/replaceOrders",
)


def _escluso(rel: str) -> bool:
    """True se il file NON fa parte dell'insieme "produzione" scandito qui.

    Esclusi: test (`tests/`, `test_*.py`), strumenti (`tools/`), e — per
    difesa, oggi senza effetto perche' nessuno di questi percorsi vive sotto
    `Betfair/` — worktree e `_live_raw`.
    """
    parti = pathlib.PurePosixPath(rel).parts
    if "tests" in parti or "tools" in parti:
        return True
    if pathlib.Path(rel).name.startswith("test_"):
        return True
    if "_live_raw" in parti or "worktrees" in parti or ".claude" in parti:
        return True
    return False


@dataclass(frozen=True)
class _Chiamata:
    riga: int
    nome: str  # place_order | place_orders | cancel_orders | replace_orders | JSONRPC:<metodo>


def _scandisci() -> Tuple[Dict[str, List[_Chiamata]], List[str]]:
    """Ritorna (chiamate trovate per file di PRODUZIONE, file esclusi)."""
    trovate: Dict[str, List[_Chiamata]] = {}
    esclusi: List[str] = []
    for f in sorted(_BETFAIR.rglob("*.py")):
        rel = f.relative_to(_RADICE).as_posix()
        if _escluso(rel):
            esclusi.append(rel)
            continue
        try:
            testo = f.read_text(encoding="utf-8", errors="ignore")
            albero = ast.parse(testo, filename=rel)
        except (SyntaxError, OSError):  # pragma: no cover - file illeggibile
            continue
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Call):
                fn = nodo.func
                nome = None
                if isinstance(fn, ast.Attribute) and fn.attr in _NOMI_CHIAMATA:
                    nome = fn.attr
                elif isinstance(fn, ast.Name) and fn.id in _NOMI_CHIAMATA:
                    nome = fn.id
                if nome:
                    trovate.setdefault(rel, []).append(_Chiamata(nodo.lineno, nome))
            elif isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
                for metodo in _METODI_JSONRPC:
                    if nodo.value.startswith(metodo):
                        trovate.setdefault(rel, []).append(
                            _Chiamata(nodo.lineno, "JSONRPC:" + metodo)
                        )
    return trovate, esclusi


_TROVATE, _ESCLUSI = _scandisci()


@dataclass(frozen=True)
class _Autorizzato:
    motivo: str
    # codici della tabella par.1.0 dell'audit del 24/09; "BANCO" per il banco di
    # certificazione (non e' una strada di produzione, ma vive sotto Betfair/
    # fuori da tests/tools e quindi il test lo vede); "NON_PRODUZIONE?" per un
    # chiamante trovato ma non agganciato a nessun runner (vedi doc di modulo).
    strade: Tuple[str, ...]


# ---------------------------------------------------------------------------
# L'ELENCO. Censimento del 25/09/2026 (F10a), ricavato da:
#   AUDIT_2026-09-24/AUDIT_STRADE_ORDINE_2026-09-24.md par.1.0-1.6
#   AUDIT_2026-09-25/STRADA_UNICA_BANCO_E_PAPER.md (motore_ordini.py sul canale)
#   e dalla scansione ast di questo stesso test (vedi F10A_CONTRATTO_STRADA_UNICA).
# Aggiungere/togliere un chiamante e' una DECISIONE DELL'UTENTE: si scrive qui
# il motivo, non ci si limita a farlo sparire.
# ---------------------------------------------------------------------------
_CHIAMANTI_AUTORIZZATI: Dict[str, _Autorizzato] = {
    "Betfair/stream/live_order_worker.py": _Autorizzato(
        motivo=(
            "esecutore del runner CALCIO: _dispatch -> _place_or_raise -> "
            "market.place_order. Serve sia la coda DB (S1) sia il canale 47331 "
            "(S2): dal 25/09 motore_ordini.py chiama LOW._dispatch invece di "
            "duplicare la chiamata, quindi resta l'UNICO caller per il calcio."
        ),
        strade=("S1", "S2"),
    ),
    "Betfair/stream/tennis_live/tennis_live_order_worker.py": _Autorizzato(
        motivo="esecutore del runner TENNIS sul canale 47332 (_do_place, _do_greenup)",
        strade=("S2t",),
    ),
    "Betfair/stream/tennis_live/guardie_tennis.py": _Autorizzato(
        motivo=(
            "MercatoConClient.place_order (T1): wrapper che inietta il client "
            "paper/live davanti al Market letto dai 4 bot tennis in-process; "
            "inoltra a market.place_order del Market vero, non esegue in proprio."
        ),
        strade=("S3b",),
    ),
    "Betfair/stream/tennis_scalper/tennis_scalper_bot.py": _Autorizzato(
        motivo="bot tennis in-process (flumine nello stesso processo del runner tennis)",
        strade=("S3b",),
    ),
    "Betfair/stream/tennis_scalper/tennis_pro_bot.py": _Autorizzato(
        motivo="bot tennis in-process", strade=("S3b",),
    ),
    "Betfair/stream/tennis_scalper/tennis_flb_bot.py": _Autorizzato(
        motivo="bot tennis in-process", strade=("S3b",),
    ),
    "Betfair/stream/tennis_scalper/tennis_swing_bot.py": _Autorizzato(
        motivo="bot tennis in-process", strade=("S3b",),
    ),
    "Betfair/omega/omega_market.py": _Autorizzato(
        motivo=(
            "place_order_live/place_submin_live: REST diretto (Mike sempre; "
            "Omega e Safe calcio in ripiego quando il controllo del canale e' "
            "chiuso; Safe tennis sempre, perche' il runner tennis non ha "
            "motore_ordini). cancelOrders/replaceOrders del place-and-trim, "
            "gia' nel contratto submin (test_submin_contratto_chiamanti)."
        ),
        strade=("S3a",),
    ),
    "Betfair/client.py": _Autorizzato(
        motivo=(
            "client REST UNICO: implementa placeOrders (SportsAPING/v1.0/placeOrders). "
            "Ogni chiamante REST (omega_market.py, order_exec.py) passa da qui: "
            "nessuna seconda implementazione del JSON-RPC nel repo."
        ),
        strade=("S3a",),
    ),
    "Betfair/order_exec.py": _Autorizzato(
        motivo="place_order -> client.place_orders REST: esecutore del servizio 8787 (odds_http) e della coda pre-match",
        strade=("S4b",),
    ),
    "Betfair/stream/odds_http.py": _Autorizzato(
        motivo="endpoint /place-order (127.0.0.1:8787): chiama order_exec.place_order",
        strade=("S4b",),
    ),
    "Betfair/order_worker.py": _Autorizzato(
        motivo="coda pre-match betfair_order_requests: chiama order_exec.place_order",
        strade=("S4b",),
    ),
    "Betfair/stream/scalper/scalper_bot.py": _Autorizzato(
        motivo="ScalperStrategy._esegui_place: scalper calcio, processo per evento (flumine proprio)",
        strade=("S4a",),
    ),
    "Betfair/stream/scalper/sniper_bot.py": _Autorizzato(
        motivo="SniperStrategy, importata da scalper_session.py per lo stesso servizio",
        strade=("S4a",),
    ),
    "Betfair/stream/scalper/scalper_session.py": _Autorizzato(
        motivo=(
            "_sweep_cancel: cancel_orders REST di emergenza (bypassa flumine) "
            "se il thread della sessione muore con ordini vivi (fix 15/07-17/07)"
        ),
        strade=("S4a",),
    ),
    "Betfair/stream/trading/submin.py": _Autorizzato(
        motivo=(
            "nucleo UNICO del place-and-trim (gia' nel contratto "
            "test_submin_contratto_chiamanti_2026_09_17.py): FlumineSubminOps.place "
            "chiama market.place_order per conto del chiamante autorizzato che "
            "invoca start_submin/advance_submin, non e' un caller indipendente."
        ),
        strade=("S1", "S2", "S2t", "S3a", "S4a"),
    ),
    "Betfair/stream/backtest/banco_comune.py": _Autorizzato(
        motivo=(
            "IL BANCO di certificazione (non produzione): place_order_live/"
            "place_order_utente chiamano mercato.place_order sul Market della "
            "FlumineSimulation durante il replay. Vive sotto Betfair/stream/backtest/, "
            "fuori da tests/tools, quindi il test lo vede e va dichiarato."
        ),
        strade=("BANCO",),
    ),
    "Betfair/stream/backtest/sim_strategy.py": _Autorizzato(
        motivo="supporto del banco: mercato/strategia di prova del motore ordini in certificazione",
        strade=("BANCO",),
    ),
    # -- 25/09, F10a: i 4 "trovati dalla scansione, da decidere" (grid_strategy, --
    # -- scalper_bot_base, theta_strategy di scalper_lab; tennis_lab.py) sono   --
    # -- stati spostati fuori da Betfair/ (laboratorio/, decisione utente): non --
    # -- li vede piu' la scansione, le righe sono state tolte di conseguenza.  --
    # -- Vedi AUDIT_2026-09-25/LABORATORIO_SPOSTAMENTO_2026-09-25.md.          --
}

# le sette strade dichiarate dalla tabella par.1.0 dell'audit del 24/09
_STRADE_AUDIT = frozenset({"S1", "S2", "S2t", "S3a", "S3b", "S4a", "S4b"})


def test_la_scansione_vede_qualcosa():
    # se questo e' vuoto il test non sta guardando niente: meglio saperlo subito
    assert _TROVATE, "nessuna chiamata trovata sotto Betfair/: la scansione e' rotta"
    assert _ESCLUSI, "nessun file escluso (tests/tools): il filtro e' rotto"


def test_nessun_chiamante_nuovo_non_registrato():
    nuovi = sorted(set(_TROVATE) - set(_CHIAMANTI_AUTORIZZATI))
    dettaglio = {m: [(c.riga, c.nome) for c in _TROVATE[m]] for m in nuovi}
    assert not nuovi, (
        "chiamanti NUOVI verso l'Exchange, NON registrati nel contratto "
        "strada unica: %s. Se e' una strada legittima, aggiungila a "
        "_CHIAMANTI_AUTORIZZATI in questo file col motivo; se non doveva "
        "esistere, e' un reperto da portare all'utente. Dettaglio (file: "
        "[(riga, nome)]): %s" % (nuovi, dettaglio)
    )


def test_elenco_non_stantio():
    """Un modulo autorizzato che non chiama piu' nasconde una strada tolta in
    silenzio (o un refuso nel contratto): il test deve vederlo."""
    stantii = sorted(set(_CHIAMANTI_AUTORIZZATI) - set(_TROVATE))
    assert not stantii, (
        "moduli nell'elenco _CHIAMANTI_AUTORIZZATI che oggi NON chiamano piu' "
        "l'Exchange: %s. Togli la riga (la strada non esiste piu') oppure "
        "spiega perche' resta (per esempio una chiamata dietro un import "
        "dinamico che ast non vede)." % stantii
    )


def test_ogni_autorizzazione_ha_un_motivo_non_vuoto():
    vuoti = sorted(m for m, a in _CHIAMANTI_AUTORIZZATI.items() if not a.motivo.strip())
    assert not vuoti, f"autorizzazioni senza motivo: {vuoti}"


def test_mappa_chiamante_strada_coerente_con_tabella_1_0_audit(capsys):
    """Punto 3 della consegna: l'elenco resta coerente col numero di strade
    dichiarate dall'audit (par.1.0: S1, S2, S2t, S3a, S3b, S4a, S4b = 7), e la
    mappa chiamante -> strada si stampa per la revisione del coordinatore."""
    strade_viste = set()
    print("\n--- mappa chiamante -> strada (F10a, contratto strada unica) ---")
    for modulo in sorted(_CHIAMANTI_AUTORIZZATI):
        strade = _CHIAMANTI_AUTORIZZATI[modulo].strade
        print(f"{modulo}: {', '.join(strade)}")
        for s in strade:
            if s not in ("BANCO", "NON_PRODUZIONE?"):
                strade_viste.add(s)
    print(f"strade coperte: {sorted(strade_viste)} (attese: {sorted(_STRADE_AUDIT)})")

    mancanti = _STRADE_AUDIT - strade_viste
    extra = strade_viste - _STRADE_AUDIT
    assert not mancanti, (
        f"strade dichiarate dall'audit (par.1.0) senza un chiamante registrato: "
        f"{sorted(mancanti)}. O la strada e' sparita (aggiornare l'audit), o "
        f"manca un'autorizzazione qui."
    )
    assert not extra, (
        f"codici di strada usati qui e NON nella tabella par.1.0 dell'audit: "
        f"{sorted(extra)}. Refuso nel contratto o l'audit va aggiornato."
    )
    assert len(_STRADE_AUDIT) == 7, "il numero di strade dichiarate dall'audit e' cambiato: aggiorna questo test e la doc"


@pytest.mark.parametrize("modulo", sorted(_CHIAMANTI_AUTORIZZATI), ids=lambda m: m.split("/")[-1])
def test_ogni_modulo_autorizzato_esiste_davvero(modulo):
    assert (_RADICE / modulo).is_file(), f"{modulo} e' nel contratto ma il file non esiste"


def test_laboratorio_non_importato_da_betfair_ne_da_desktop():
    """25/09: i 4 moduli 'trovati da F10a' (par.0 sopra) sono stati spostati in
    ``laboratorio/`` (radice del repo). La condizione che rende legittimo lo
    spostamento e' che NESSUN modulo di produzione o test sotto ``Betfair/`` o
    ``desktop/`` importi da li': altrimenti riaprirebbe di nascosto la stessa
    strada verso l'Exchange che questo contratto e' nato per sorvegliare.

    Scandisce ``Betfair/**/*.py`` (test e tools INCLUSI: qui non vale
    l'esclusione di _escluso, vogliamo zero eccezioni) con ``ast`` per un
    ``import laboratorio``/``import laboratorio.x``/``from laboratorio...``, e
    ``desktop/**`` (JS, elettrone: niente ast Python) con una ricerca testuale
    sulla stringa letterale ``laboratorio`` (un percorso passato a un processo
    figlio sarebbe una stringa, non un import)."""
    colpevoli_py: List[str] = []
    for f in sorted(_BETFAIR.rglob("*.py")):
        rel = f.relative_to(_RADICE).as_posix()
        try:
            testo = f.read_text(encoding="utf-8", errors="ignore")
            albero = ast.parse(testo, filename=rel)
        except (SyntaxError, OSError):  # pragma: no cover - file illeggibile
            continue
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.Import):
                if any(alias.name == "laboratorio" or alias.name.startswith("laboratorio.")
                       for alias in nodo.names):
                    colpevoli_py.append(f"{rel}:{nodo.lineno}")
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.module and (nodo.module == "laboratorio" or nodo.module.startswith("laboratorio.")):
                    colpevoli_py.append(f"{rel}:{nodo.lineno}")
    assert not colpevoli_py, (
        "modulo sotto Betfair/ che importa da laboratorio/ (strada nascosta "
        "verso l'Exchange, riapre esattamente cio' che lo spostamento del "
        "25/09 doveva chiudere): %s" % colpevoli_py
    )

    desktop_dir = _RADICE / "desktop"
    colpevoli_desktop: List[str] = []
    if desktop_dir.is_dir():
        # Solo i SORGENTI dell'app (js/ts/json/bat/ps1/md): l'uscita di electron-builder
        # (`desktop/release/`, `dist/`) e `node_modules/` sono binari/pacchetti di terzi;
        # il 25/09 la locale finlandese `fi.pak` conteneva la parola "laboratorio" (falso positivo).
        _EST = {".js", ".cjs", ".mjs", ".ts", ".json", ".bat", ".ps1", ".md", ".txt", ".html"}
        _CARTELLE_ESCLUSE = {"node_modules", "release", "dist", "build", "out"}
        for f in sorted(desktop_dir.rglob("*")):
            if not f.is_file() or _CARTELLE_ESCLUSE.intersection(f.parts):
                continue
            if f.suffix.lower() not in _EST:
                continue
            try:
                testo = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:  # pragma: no cover - file illeggibile/binario
                continue
            if "laboratorio" in testo:
                colpevoli_desktop.append(f.relative_to(_RADICE).as_posix())
    assert not colpevoli_desktop, (
        "file sotto desktop/ che nomina 'laboratorio' (possibile percorso "
        "verso un modulo del laboratorio passato a un processo Python): %s"
        % colpevoli_desktop
    )
