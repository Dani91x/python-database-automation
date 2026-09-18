"""Sonda di misura del canale dello scanner (F1) - SOLA LETTURA.

Che cosa fa: si aggancia al canale locale dello scanner (127.0.0.1:47336), non
manda NIENTE (il canale e' di sola lettura e rifiuterebbe comunque), e conta.

Che cosa NON fa: non tocca il database, non chiama Betfair, non avvia processi,
non piazza e non annulla niente. E' un client WebSocket e un contatore.

A che serve: sono i numeri di accettazione della fase F1 del
`PIANO_CANALE_LOCALE_AL_MS_2026-09-18.md`:
  * messaggi/s e byte/s PER TOPIC (`scan_calcio`, `scan_tennis`, `scanner_stato`);
  * eta' della riga quando arriva: `_ricevuto_ms - updated_at` (il nostro
    orologio con se stesso) e `_ricevuto_ms - payload.odds_pt_ms` (il NOSTRO
    orologio contro quello di BETFAIR, e quindi SOLO passando da
    `Betfair.stream.orologio`, che dichiara incertezza e `impossibile`);
  * righe con QUOTE NULLE (`odds` tutto a None) e righe senza `odds_ts_ms`:
    devono essere zero sui mercati in gioco, ed e' il segnale dell'incidente
    del 17/09;
  * copertura di `odds_pt_ms` e `bet_delay`, per sport: sono i due numeri di F0;
  * `scanner_stato`: `canale_acceso`, `canale.saltati` (deve restare 0),
    `stream_mercati_senza_quote_n` (deve restare 0), `flumine_caricato`
    (deve restare False).

Uso (il processo lo avvia il coordinatore, con il permesso dell'utente):
    .venv/Scripts/python.exe -m Betfair.safe_strategy.tools.sonda_canale_scan_2026_09_18 \
        --porta 47336 --minuti 15 --ogni 60

`--lento N` simula il CONSUMATORE LENTO (dorme N ms a ogni messaggio): serve a
provare dal vivo che un client indietro non toglie i fotogrammi agli altri
(difetto D4). Con `--lento` la sonda dichiara i propri numeri come NON
rappresentativi della latenza: sta misurando se stessa.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Any, Dict, List, Optional

from Betfair.stream import orologio as _oro

TOPIC_ATTESI = ("scan_calcio", "scan_tennis", "scanner_stato")


class Conti:
    """I contatori di un topic. Nessuna media che nasconda una coda: p50 e p95."""

    def __init__(self) -> None:
        self.messaggi = 0
        self.byte = 0
        self.eta_updated_ms: List[float] = []
        self.ritardo_pt_ms: List[float] = []
        self.pt_impossibili = 0
        self.senza_pt = 0
        self.senza_bet_delay = 0
        self.quote_nulle = 0
        self.senza_odds_ts = 0
        self.eventi: set = set()

    def riassunto(self) -> Dict[str, Any]:
        def pc(valori: List[float], q: float) -> Optional[float]:
            if not valori:
                return None
            ordinati = sorted(valori)
            i = min(len(ordinati) - 1, int(q * len(ordinati)))
            return round(ordinati[i], 1)

        return {
            "messaggi": self.messaggi,
            "byte": self.byte,
            "eventi_distinti": len(self.eventi),
            "eta_updated_p50_ms": pc(self.eta_updated_ms, 0.50),
            "eta_updated_p95_ms": pc(self.eta_updated_ms, 0.95),
            "ritardo_pt_p50_ms": pc(self.ritardo_pt_ms, 0.50),
            "ritardo_pt_p95_ms": pc(self.ritardo_pt_ms, 0.95),
            "pt_impossibili": self.pt_impossibili,
            "righe_senza_odds_pt_ms": self.senza_pt,
            "righe_senza_bet_delay": self.senza_bet_delay,
            "righe_con_quote_nulle": self.quote_nulle,
            "righe_senza_odds_ts_ms": self.senza_odds_ts,
        }


def _quote_nulle(payload: Dict[str, Any]) -> bool:
    """Tutte le selezioni senza back e senza lay: e' la firma del 17/09."""
    odds = payload.get("odds")
    if not isinstance(odds, dict) or not odds:
        return True
    for pair in odds.values():
        if isinstance(pair, dict) and (pair.get("back") is not None
                                       or pair.get("lay") is not None):
            return False
    return True


def _misura_riga(conti: Conti, riga: Dict[str, Any], ricevuto_ms: float) -> None:
    payload = riga.get("payload") or {}
    conti.eventi.add(riga.get("event_id"))
    updated = _oro.ms_da_betfair(riga.get("updated_at"))
    if updated is not None:
        conti.eta_updated_ms.append(ricevuto_ms - updated)
    pt = payload.get("odds_pt_ms")
    if pt is None:
        conti.senza_pt += 1
    else:
        # DUE OROLOGI: il ritardo si calcola SOLO qui dentro, che dichiara
        # incertezza e marca `impossibile` un risultato negativo (questa
        # macchina e' indietro di ~2,08 s: misura del 17/09)
        r = _oro.ritardo_da_betfair(pt, ricevuto_ms, etichetta="betfair->sonda")
        if r["valido"]:
            conti.ritardo_pt_ms.append(float(r["ritardo_ms"]))
            if r["impossibile"]:
                conti.pt_impossibili += 1
    if payload.get("bet_delay") is None:
        conti.senza_bet_delay += 1
    if payload.get("odds_ts_ms") is None:
        conti.senza_odds_ts += 1
    if payload.get("inplay") and _quote_nulle(payload):
        conti.quote_nulle += 1


def _stampa(conti: Dict[str, Conti], stato: Optional[Dict[str, Any]],
            secondi: float) -> None:
    print(f"\n--- {secondi:.0f} s di misura ---", flush=True)
    for topic in TOPIC_ATTESI:
        c = conti[topic]
        if not c.messaggi:
            print(f"  {topic:14s} nessun messaggio", flush=True)
            continue
        r = c.riassunto()
        print(f"  {topic:14s} {r['messaggi']:6d} msg  "
              f"{r['messaggi'] / max(secondi, 1e-9):6.2f} msg/s  "
              f"{r['byte'] / max(secondi, 1e-9) / 1024:8.1f} KB/s  "
              f"eventi={r['eventi_distinti']}", flush=True)
        if topic != "scanner_stato":
            print(f"                 eta' updated_at p50={r['eta_updated_p50_ms']} "
                  f"p95={r['eta_updated_p95_ms']} ms | "
                  f"ritardo da Betfair p50={r['ritardo_pt_p50_ms']} "
                  f"p95={r['ritardo_pt_p95_ms']} ms "
                  f"(impossibili={r['pt_impossibili']})", flush=True)
            print(f"                 senza odds_pt_ms={r['righe_senza_odds_pt_ms']} | "
                  f"senza bet_delay={r['righe_senza_bet_delay']} | "
                  f"QUOTE NULLE in gioco={r['righe_con_quote_nulle']} | "
                  f"senza odds_ts_ms={r['righe_senza_odds_ts_ms']}", flush=True)
    if stato is not None:
        canale = stato.get("canale") or {}
        print(f"  stato: canale_acceso={stato.get('canale_acceso')} "
              f"flumine_caricato={stato.get('flumine_caricato')} "
              f"saltati={canale.get('saltati')} "
              f"saltati_client={canale.get('saltati_client')} "
              f"client={canale.get('client')} | "
              f"mercati senza quote={stato.get('stream_mercati_senza_quote_n')} "
              f"(allarme {stato.get('stream_mercati_allarme_n')}) | "
              f"monitorati={stato.get('monitored')}", flush=True)
        tick = stato.get("tick") or {}
        if tick:
            print(f"         giro dello scanner: {tick}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Sonda di misura del canale dello scanner")
    ap.add_argument("--porta", type=int, default=47336)
    ap.add_argument("--minuti", type=float, default=15.0)
    ap.add_argument("--ogni", type=float, default=60.0, help="secondi fra due stampe")
    ap.add_argument("--lento", type=int, default=0,
                    help="ms di attesa a ogni messaggio: simula un consumatore lento")
    args = ap.parse_args()

    from websockets.sync.client import connect

    conti = {t: Conti() for t in TOPIC_ATTESI}
    altri: Dict[str, int] = {}
    ultimo_stato: Optional[Dict[str, Any]] = None
    if args.lento:
        print(f"ATTENZIONE: consumatore LENTO ({args.lento} ms a messaggio). I numeri "
              f"di latenza di questa sonda misurano la sonda, non il canale.", flush=True)
    inizio = time.time()
    fine = inizio + args.minuti * 60.0
    prossima_stampa = inizio + args.ogni
    with connect(f"ws://127.0.0.1:{args.porta}", open_timeout=10,
                 max_size=None) as ws:
        hello = json.loads(ws.recv(timeout=10))
        print(f"agganciato: {hello}", flush=True)
        while time.time() < fine:
            resto = max(0.1, min(5.0, fine - time.time()))
            try:
                grezzo = ws.recv(timeout=resto)
            except TimeoutError:
                grezzo = None
            except Exception as ex:  # noqa: BLE001 - canale caduto: si dichiara
                print(f"canale caduto dopo {time.time() - inizio:.0f} s: "
                      f"{type(ex).__name__}: {str(ex)[:160]}", flush=True)
                break
            if grezzo is not None:
                ricevuto_ms = time.time() * 1000.0
                try:
                    msg = json.loads(grezzo)
                except Exception:  # noqa: BLE001
                    continue
                topic = str(msg.get("t") or "")
                dato = msg.get("d")
                if topic in conti:
                    c = conti[topic]
                    c.messaggi += 1
                    c.byte += len(grezzo)
                    if topic == "scanner_stato":
                        ultimo_stato = dato if isinstance(dato, dict) else None
                    elif isinstance(dato, dict):
                        _misura_riga(c, dato, ricevuto_ms)
                elif topic != "hello":
                    altri[topic] = altri.get(topic, 0) + 1
                if args.lento:
                    time.sleep(args.lento / 1000.0)
            if time.time() >= prossima_stampa:
                _stampa(conti, ultimo_stato, time.time() - inizio)
                prossima_stampa = time.time() + args.ogni
    _stampa(conti, ultimo_stato, time.time() - inizio)
    if altri:
        print(f"\nTOPIC NON ATTESI (da spiegare, non da ignorare): {altri}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
