# -*- coding: utf-8 -*-
r"""E3: righe per responsabilita' di bot_service.py e service.py (sola lettura).
Uso: python ARCHITETTURA_2026-10/strumenti/e3_righe_safe.py
Ogni intervallo [a,b] e' scritto a mano dalla mappa della scheda E3 (indice
`grep -n "^def \|^class "`): le righe fuori dagli intervalli finiscono in 'altro'.
"""
import os
RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def conta(percorso, mappa):
    righe = open(os.path.join(RADICE, percorso), encoding="utf-8").read().split("\n")
    tot = len(righe) - (1 if righe and righe[-1] == "" else 0)
    usate = 0
    out = {}
    for nome, intervalli in mappa.items():
        n = sum(b - a + 1 for a, b in intervalli)
        out[nome] = n
        usate += n
    out["altro (import, costanti, testo fuori dalle def)"] = tot - usate
    print(percorso, "righe", tot)
    for k, v in out.items():
        print("   %-52s %6d  %5.1f%%" % (k, v, 100.0 * v / tot))

BOT = {
 "guscio: modelli dati/coda, ospite, porta ordini": [(90, 135), (250, 318), (869, 931), (2380, 2467)],
 "guscio: parametri e normalizzazione (resolve_params...)": [(319, 696)],
 "guscio: lettura prezzi/rest gate/poll flumine": [(697, 841)],
 "ordini: riconciliazione, consapevolezza, settlement": [(935, 2379)],
 "richieste UI (place/cashout/cancel/riprendi, marcatori)": [(2468, 3827)],
 "uscite: decisione, proposte, invio, aggiornamento": [(3829, 6014)],
 "piazzamento: esecuzione, riserva, errori, catena": [(6015, 6536)],
 "rischio e ingressi automatici (strategia)": [(6537, 7409)],
 "opportunita': lambda, modello, proposte, combo, anomalie": [(7410, 9210)],
 "feed: ripiego REST, uscite combo, flusso": [(9211, 9386)],
 "canale scanner, lettura righe, giro veloce": [(9512, 10028)],
 "ciclo: run_once, main, attese, arresto, controllo": [(10029, 11136)],
}
# NB: gli intervalli si sovrappongono solo dove dichiarato; la somma e' controllata sotto.
if __name__ == "__main__":
    conta("Betfair/safe_strategy/bot_service.py", BOT)
