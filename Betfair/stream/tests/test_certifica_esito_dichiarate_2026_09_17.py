# -*- coding: utf-8 -*-
"""DIFETTO (17/09): l'ESITO e l'exit code del banco comune (`certifica.py`)
contavano ANCHE le violazioni DICHIARATE/APPROVATE (scelte esplicite
dell'utente, es. T7-APPROVAZIONE del 14/09), mentre `Referto.pulita`
(`certificazione_tennis.py`) e il totale di `replay_tennis.py` le escludono
gia'. Il banco comune deve leggere la STESSA regola dei referti: una partita
«OK» non puo' contribuire a un totale > 0 ne' a exit 1.

Qui si usa il vero `Referto` e la vera `Violazione` di
`Betfair.safe_strategy.certificazione_tennis` (stesse chiavi e tipi del vero,
niente SimpleNamespace finti).

SECONDA PASSATA (17/09, review del coordinatore): la prima versione di questo
file testava SOLO `certifica.violazioni_effettive` — una funzione pura isolata
— e ricalcolava `tot`/`exit_code` A MANO nel test. Falsificazione fatta dal
coordinatore: con `violazioni_effettive` intatta ma la riga di `main` tornata
a `tot = sum(len(r.violazioni) for r in referti)`, i test restavano VERDI: il
test proteggeva la funzione, non il CABLAGGIO in `main`. Corretto in due modi:

1. Il calcolo e' stato estratto in `certifica.esito_del_banco(referti) ->
   (tot, pulite, mute, exit_code)`, usata da `main` sia per la stampa ESITO
   sia per il `return`: un solo punto, non due che possono disallinearsi.
2. Un test chiama `main()` per davvero (`test_main_wiring_...` sotto),
   monkeypatchando `certifica._esegui_compiti` per restituire referti VERI
   costruiti a mano, catturando stdout e il valore di ritorno: se qualcuno
   ricablasse `main` su `r.violazioni` diretto (bypassando `esito_del_banco`),
   questo test tornerebbe rosso anche se `esito_del_banco` da sola fosse
   corretta.
"""
from __future__ import annotations

from Betfair.safe_strategy.certificazione_tennis import Referto, Violazione
from Betfair.stream.backtest import certifica


def _referto_solo_dichiarate(event_id: str) -> Referto:
    r = Referto(event_id=event_id, decisioni=3)
    r.violazioni.append(Violazione(
        "T7-APPROVAZIONE", "uscita in attesa di firma",
        "trattenuta dal cancelletto, scelta dichiarata dell'utente (14/09)"))
    r.violazioni.append(Violazione(
        "T8-DICHIARATA", "misura dichiarata dalla spec",
        "non e' un difetto: e' una misura prevista"))
    return r


def _referto_con_violazione_vera(event_id: str) -> Referto:
    r = Referto(event_id=event_id, decisioni=3)
    r.violazioni.append(Violazione(
        "P1", "il bot non deve mandare a mercato la stessa richiesta all'infinito",
        "loop rilevato: 32 ordini veri"))
    return r


# ---------------------------------------------------------------------------
# 1) `violazioni_effettive` — la regola del suffisso, isolata
# ---------------------------------------------------------------------------
def test_violazioni_effettive_esclude_dichiarate_e_approvazione():
    """Una partita con SOLE voci -DICHIARATA/-APPROVAZIONE non deve contribuire
    al totale del banco: e' la stessa regola di `Referto.pulita`."""
    r = _referto_solo_dichiarate("35795560")
    assert r.pulita is True, "il referto stesso la giudica pulita (DICHIARATA/APPROVAZIONE non contano)"
    assert certifica.violazioni_effettive(r) == [], (
        "il banco comune contava le voci DICHIARATE/APPROVATE nel totale: "
        "PRIMA della correzione questa lista non era vuota (era r.violazioni per intero)"
    )


def test_violazioni_effettive_conta_le_violazioni_vere():
    r = _referto_con_violazione_vera("35795560")
    assert r.pulita is False
    assert len(certifica.violazioni_effettive(r)) == 1


# ---------------------------------------------------------------------------
# 2) `esito_del_banco` — il calcolo UNICO che alimenta stampa ESITO e return
# ---------------------------------------------------------------------------
def test_esito_del_banco_ignora_le_dichiarate():
    """Lo scenario ESATTO del 17/09: `safe_tennis` su 35795560, 15 partite
    pulite con 69 T7-APPROVAZIONE dichiarate, 0 violazioni vere."""
    referti = [_referto_solo_dichiarate(f"ev{i}") for i in range(15)]
    tot, pulite, mute, exit_code = certifica.esito_del_banco(referti)
    assert tot == 0, "PRIMA della correzione: tot=69 (le T7-APPROVAZIONE finivano nel totale)"
    assert pulite == 15
    assert mute == 0
    assert exit_code == 0, "PRIMA della correzione: exit code 1 su un banco senza violazioni vere"


def test_esito_del_banco_conta_le_violazioni_vere():
    """Una violazione vera in mezzo alle dichiarate deve continuare a far
    uscire il banco con exit 1: la correzione non deve nascondere i difetti
    veri, solo le scelte dichiarate."""
    referti = ([_referto_solo_dichiarate(f"ev{i}") for i in range(15)]
               + [_referto_con_violazione_vera("ev-vera")])
    tot, pulite, mute, exit_code = certifica.esito_del_banco(referti)
    assert tot == 1
    assert pulite == 15
    assert mute == 0
    assert exit_code == 1


def test_esito_del_banco_conta_le_partite_mute():
    """Una partita senza decisioni non e' ne' pulita ne' sporca: e' muta, e
    non deve entrare nel conteggio di ne' l'una ne' l'altra."""
    muta = Referto(event_id="muta", decisioni=0)
    tot, pulite, mute, exit_code = certifica.esito_del_banco([muta])
    assert tot == 0
    assert pulite == 0
    assert mute == 1
    assert exit_code == 0


# ---------------------------------------------------------------------------
# 3) `main()` per davvero — il CABLAGGIO, non solo la funzione pura
# ---------------------------------------------------------------------------
def _fake_esegui_compiti(referti_in_ordine):
    """Sostituisce `certifica._esegui_compiti`: stesso generatore, ma
    restituisce i referti VERI passati dal test invece di far girare un
    replay reale su flumine (che qui non serve: si sta testando il cablaggio
    dell'ESITO in `main`, non il replay)."""
    def _fake(compiti, processi, picchi):  # noqa: ARG001 - stessa firma del vero
        it = iter(referti_in_ordine)
        for _ in compiti:
            yield next(it)
    return _fake


def test_main_wiring_zero_violazioni_su_solo_dichiarate(monkeypatch, capsys):
    """Chiama `certifica.main()` per davvero (parsing argv, registro bot,
    stampa ESITO, return) con UN referto vero solo-dichiarato: deve vedere
    «0 violazioni totali» e restituire 0."""
    monkeypatch.setattr(certifica, "_esegui_compiti",
                        _fake_esegui_compiti([_referto_solo_dichiarate("999999")]))
    esito = certifica.main(["safe_tennis", "999999", "--scenari", "base"])
    out = capsys.readouterr().out
    assert "0 violazioni totali" in out, out
    assert esito == 0, (
        f"main() ha restituito {esito} invece di 0 su un referto solo-dichiarato. "
        f"output:\n{out}"
    )


def test_main_wiring_una_violazione_vera(monkeypatch, capsys):
    """Stesso giro, ma il referto ha UNA violazione vera: `main()` deve
    vedere «1 violazioni totali» e restituire 1."""
    monkeypatch.setattr(certifica, "_esegui_compiti",
                        _fake_esegui_compiti([_referto_con_violazione_vera("999999")]))
    esito = certifica.main(["safe_tennis", "999999", "--scenari", "base"])
    out = capsys.readouterr().out
    assert "1 violazioni totali" in out, out
    assert esito == 1, (
        f"main() ha restituito {esito} invece di 1 su un referto con violazione vera. "
        f"output:\n{out}"
    )
