# -*- coding: utf-8 -*-
"""IL CONTRATTO: un bot che opera in produzione DEVE stare nel registro.

Ordine dell'utente del 16/09: «ogni nuovo bot, o i precedenti, se voglio
testarli devono passare da flumine ed essere certificati [...] da oggi standard
e usato di default».

Perche' un test e non una buona intenzione: un bot nuovo nasce sempre da
un'altra parte (un runner in `desktop/main.js`, una variante nella Safe, una
riga nel `_BOT_REGISTRY` del tennis) e nessuno si ricorda di agganciarlo al
replay. Questo test legge quelle FONTI DI VERITA' e diventa rosso se trova un
bot che il registro non conosce: cosi' l'aggancio al banco non e' un favore, e'
una condizione per andare in produzione.

E quelli registrati ma NON ancora certificati vanno elencati AD ALTA VOCE: il
test pretende che l'elenco sia quello dichiarato qui sotto, quindi non si puo'
aggiungere un bot senza certificazione in silenzio.
"""
from __future__ import annotations

import io
import os
import re

import pytest

from Betfair.stream.backtest import registro_bot as REG

_RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MAIN_JS = os.path.join(_RADICE, "desktop", "main.js")
TENNIS_RUNNER = os.path.join(_RADICE, "Betfair", "stream", "tennis_live", "tennis_runner.py")
SCALPER_SERVICE = os.path.join(_RADICE, "Betfair", "stream", "scalper", "scalper_service.py")


# ---------------------------------------------------------------------------
# le fonti di verita' della produzione
# ---------------------------------------------------------------------------
def _moduli_di_main_js() -> set:
    """I moduli python che `desktop/main.js` lancia davvero.

    Si legge il SORGENTE (non un elenco a mano): se domani qualcuno aggiunge uno
    `spawnRunner`, questo test lo vede. Il `watchdog` e' un guardiano: quando
    c'e', il modulo vero e' quello dopo il `--`.
    """
    testo = io.open(MAIN_JS, encoding="utf-8").read()
    moduli = set()
    for riga in re.findall(r"spawnRunner\(\s*'[^']+'\s*,\s*\[([^\]]*)\]", testo):
        pezzi = re.findall(r"'([^']+)'", riga)
        if not pezzi:
            continue
        if "--" in pezzi:
            moduli.add(pezzi[pezzi.index("--") + 1])
        elif "-m" in pezzi:
            moduli.add(pezzi[pezzi.index("-m") + 1])
        else:
            moduli.add(pezzi[0])
    return moduli


def _bot_tennis() -> set:
    """Le chiavi di `_BOT_REGISTRY` in `tennis_runner.py`, lette dal sorgente
    (importare il runner tira dentro flumine e i client: qui non serve)."""
    testo = io.open(TENNIS_RUNNER, encoding="utf-8").read()
    blocco = testo.split("_BOT_REGISTRY: Dict[str, Any] = {", 1)[1].split("}", 1)[0]
    return set(re.findall(r'"([^"]+)"\s*:', blocco))


def _varianti_safe() -> set:
    from Betfair.safe_strategy import bot_service

    return set(bot_service.VALID_VARIANTS)


# ---------------------------------------------------------------------------
# il contratto
# ---------------------------------------------------------------------------
def test_ogni_runner_di_produzione_e_un_bot_registrato_o_e_dichiarato_non_bot():
    moduli = _moduli_di_main_js()
    assert moduli, "nessuno spawnRunner letto da desktop/main.js: il test non guarda niente"
    registrati = {m for b in REG.elenco() for m in b.moduli_produzione}
    orfani = sorted(m for m in moduli if m not in registrati and m not in REG.NON_BOT)
    assert not orfani, (
        f"questi processi di produzione non sono ne' bot registrati ne' dichiarati "
        f"'non bot': {orfani}. Aggiungili a Betfair/stream/backtest/registro_bot.py "
        f"(vedi MODELLO_BOT_NUOVO.md) oppure spiega in REG.NON_BOT perche' non operano."
    )


def test_ogni_variante_safe_ha_una_scheda_nel_registro():
    mancanti = sorted(v for v in _varianti_safe() if f"safe_{v}" not in REG.REGISTRO)
    assert not mancanti, (
        f"varianti Safe in produzione senza scheda nel registro: {mancanti}. "
        f"Ogni variante e' una strategia a se': apre da sola e va certificata da sola."
    )


def test_ogni_bot_tennis_del_runner_e_registrato():
    mancanti = sorted(b for b in _bot_tennis() if b not in REG.REGISTRO)
    assert not mancanti, (
        f"bot tennis nel _BOT_REGISTRY del runner e assenti dal registro: {mancanti}"
    )


def test_lo_scalper_calcio_e_registrato_col_modulo_che_lo_ospita():
    testo = io.open(SCALPER_SERVICE, encoding="utf-8").read()
    assert "Betfair.stream.scalper.scalper_session" in testo
    scheda = REG.bot("scalper_calcio")
    assert "Betfair.stream.scalper.scalper_session" in scheda.moduli_produzione


def test_chi_non_e_certificato_lo_dice_e_dice_perche():
    """"Registrato" non vuol dire "certificato": chi non ha replay+controlli
    deve dichiarare il MOTIVO, e comparire in un elenco che nessuno puo'
    allungare in silenzio."""
    senza = REG.senza_certificazione()
    muti = [b.nome for b in senza if not b.motivo_senza_controlli.strip()]
    assert not muti, f"registrati senza certificazione e SENZA motivo: {muti}"

    # l'elenco e' dichiarato: aggiungerne uno rende questo test rosso, e chi lo
    # aggiunge deve scriverlo qui — cioe' ammetterlo.
    # 16/09 sera: Omega (C.2), Safe base/esatto/punta (C.3) e Safe tennis (C.4)
    # sono certificabili — tolti dall'elenco dal coordinatore.
    attesi = {
        "scalper_calcio", "tennis_scalper", "tennis_pro", "tennis_flb",
        "tennis_swing",
    }
    assert {b.nome for b in senza} == attesi, (
        "l'elenco dei bot REGISTRATI SENZA CERTIFICAZIONE e' cambiato: "
        f"adesso e' {sorted(b.nome for b in senza)}. Se ne hai certificato uno, "
        "toglilo da 'attesi'; se ne hai aggiunto uno, dichiaralo qui."
    )


def test_mike_e_certificabile_e_le_sue_parti_esistono_davvero():
    """L'unico bot con replay E controlli, oggi. Le stringhe del registro devono
    risolvere a oggetti veri: un registro che punta nel vuoto e' peggio di
    nessun registro."""
    scheda = REG.bot("mike")
    assert scheda.certificabile
    replay = scheda.funzione_replay()
    assert callable(replay)
    controlli = scheda.modulo_controlli()
    assert hasattr(controlli, "elenco_controlli") and hasattr(controlli, "mai_sollecitati")
    assert hasattr(controlli, "Referto")
    scenari = scheda.elenco_scenari()
    assert "base" in scenari and len(scenari) >= 5
    assert os.path.isfile(os.path.join(_RADICE, scheda.spec)), scheda.spec


def test_il_comando_unico_elenca_i_bot():
    from Betfair.stream.backtest import certifica

    assert certifica.main(["--elenco"]) == 0
    # un bot inesistente non passa in silenzio
    assert certifica.main(["non_esiste_questo_bot"]) == 2
    # un bot registrato ma senza replay dice che non e' certificabile, e perche'
    # (16/09 sera: Omega e' diventato certificabile — con "omega" questa riga
    # lanciava un replay INTERO di 33 minuti; si usa un bot ancora senza replay)
    assert certifica.main(["scalper_calcio"]) == 2


def test_il_modello_per_un_bot_nuovo_esiste():
    percorso = os.path.join(_RADICE, "Betfair", "stream", "backtest",
                            "MODELLO_BOT_NUOVO.md")
    assert os.path.isfile(percorso)
    testo = io.open(percorso, encoding="utf-8").read()
    for passo in ("registro_bot.py", "certificazione", "certifica", "spec"):
        assert passo in testo, passo


@pytest.mark.parametrize("scheda", REG.elenco(), ids=lambda b: b.nome)
def test_ogni_scheda_e_completa(scheda):
    assert scheda.sport in ("calcio", "tennis")
    assert scheda.descrizione.strip()
    assert scheda.moduli_produzione, f"{scheda.nome}: nessun modulo di produzione"
    assert callable(scheda.cartella)
