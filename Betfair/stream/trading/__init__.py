"""Pacchetto `trading`: logica di esecuzione avanzata per il runner live (Fase 1).

Contiene la macchina a stati place-and-trim (`submin`) e (nelle fasi successive)
green-up / dutching / stop-loss. Tutto pura logica + uso NATIVO di flumine,
testabile a unità con mock (nessuna rete, nessun login, nessun ordine reale).
"""
