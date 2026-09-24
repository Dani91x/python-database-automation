# -*- coding: utf-8 -*-
"""LA SCHEDA DI USCITA DI OMEGA AL MS (24/09/2026).

Ordine dell'utente: "Tutti i valori e i calcoli devono aggiornarsi al cambiare
del prezzo. La scheda delle proposte deve segnalarmi se l'opportunita', in base
ai calcoli e al prezzo attuale, c'e' ancora o no: io decido se approvare o
scartare."

Cosa certifica, sul codice di produzione:
  1. ``esito_uscita_al_prezzo`` e' la STESSA decisione di
     ``omega_v3.proposta_uscita`` (il vero) ramo per ramo: parita' su una
     griglia di prezzi di back, controparte, P, minuti, cap e soglie;
  2. il file d'oro condiviso con la porta TypeScript e' quello del Python di
     oggi;
  3. il payload della proposta porta gli ingredienti del ricalcolo (commissione,
     margine dell'attesa letto dal default VERO, soglia di rischio, massimo
     della traiettoria) e la valutazione.

ASCII-only nel codice, commenti in italiano.
"""
from __future__ import annotations

import itertools
import json

from Betfair.omega import omega_proposte as PR
from Betfair.omega import omega_v3 as V3
from Betfair.omega.test_omega_proposte_2026_09_17 import DbFinto, _gira, _lay
from Betfair.omega.tools import genera_oro_uscita as ORO


def test_parita_con_la_proposta_uscita_vera():
    p = PR.parametri_modello()
    visti = set()
    griglia = itertools.product(
        ("1 - 0", "2 - 1", "0 - 0"),          # selezione bancata
        (3.2, 7.5),                           # quota del lay
        (1.8, 3.0, 5.5, 12.0, None),          # back di adesso
        (0.2, 50.0),                          # controparte
        (0.02, 0.2, 0.6),                     # P che il bancato esca
        (30.0, 80.0),                         # minuto
        (None, "v3_max_liability_per_leg"),   # cap
        (0.0, 0.3),                           # soglia di rischio
    )
    for sel, lay, back, bsize, pe, minuto, cap, plm in griglia:
        pos = V3.Posizione(periodo="ft", selection_name=sel, lay_price=lay, size=1.0,
                           punteggio_ingresso=(0, 0), minuto_ingresso=20.0)
        vero = V3.proposta_uscita(pos, minuto=minuto, punteggio=(1, 0), back_price=back,
                                  back_size=bsize, p_evento=pe, p=p, commissione=0.05,
                                  cap_scattato=cap, p_lose_max=plm)
        mia = PR.esito_uscita_al_prezzo(
            lay_price=lay, size=1.0, back_price=back, back_size=bsize,
            ev_tenere=vero.ev_tenere,
            max_attesa=(vero.bloccabile_max_atteso
                        if vero.minuto_del_massimo is not None else None),
            p_evento=pe, commissione=0.05, margine_attesa=PR.margine_attesa(),
            cap_scattato=cap, p_lose_max=plm)
        chiave = (sel, lay, back, bsize, pe, minuto, cap, plm)
        assert mia["motivo_codice"] == vero.motivo_codice, (chiave, mia, vero)
        assert mia["proponi"] == vero.proponi, chiave
        if back is not None:
            assert mia["profitto"] == vero.profitto_bloccabile, chiave
        visti.add(vero.motivo_codice)
    for atteso in ("blocca_il_profitto", "tenere_vale_di_piu", "cap", "rischio",
                   "protezione", "controparte_insufficiente", "nessun_prezzo_di_back"):
        assert atteso in visti, f"la griglia non esercita il ramo {atteso}"


def test_il_margine_si_legge_dal_default_vero():
    assert PR.margine_attesa() == V3.proposta_uscita.__kwdefaults__["margine_attesa"]


def test_il_file_d_oro_e_quello_del_python_di_oggi():
    salvato = json.loads(ORO.ORO.read_text(encoding="utf-8"))
    assert salvato == json.loads(json.dumps(ORO.calcola()))
    motivi = {c["uscita"]["motivo_codice"] for c in salvato}
    for atteso in ("blocca_il_profitto", "tenere_vale_di_piu", "aspettare_vale_di_piu",
                   "controparte_insufficiente", "cap", "rischio", "protezione",
                   "bloccabile_non_positivo", "nessun_prezzo_di_back",
                   "posizione_senza_numeri"):
        assert atteso in motivi, f"il file d'oro non copre {atteso}"


def test_il_payload_porta_gli_ingredienti_e_la_valutazione():
    db = DbFinto([_lay()])
    assert _gira(db) == 1
    p = db.richieste[0]["payload"]
    assert p["commissione"] == 0.05 and p["margine_attesa"] == PR.margine_attesa()
    assert p["p_lose_max"] == 0.0
    assert "max_attesa" in p
    assert p["valutazione"]["valida"] is True
    assert p["valutazione"]["motivo_codice"] == p["motivo_codice"]
    # il ricalcolo della scheda AL PREZZO DELLA PROPOSTA ridice la stessa cosa
    rifatto = PR.esito_uscita_al_prezzo(
        lay_price=p["entry_price"], size=p["size"], back_price=p["back_price"],
        back_size=p["size_available_at_decision"], ev_tenere=p["ev_tenere"],
        max_attesa=p["max_attesa"], p_evento=p["p_evento"],
        commissione=p["commissione"], margine_attesa=p["margine_attesa"],
        cap_scattato=p.get("cap_scattato"), p_lose_max=p["p_lose_max"])
    assert rifatto["proponi"] is True and rifatto["motivo_codice"] == p["motivo_codice"]
    # il payload lo scrive arrotondato al centesimo (``_payload``)
    assert round(rifatto["profitto"], 2) == p["profitto_bloccabile"]
