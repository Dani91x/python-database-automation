# -*- coding: utf-8 -*-
"""REGISTRAZIONI SINTETICHE per le varianti BASE e PUNTA della Safe (16/09).

PERCHE' ESISTONO. Sulle 39 registrazioni reali del corpus, BASE e PUNTA non
entrano MAI (Esito C.3-bis del piano: per BASE la quota live della favorita non
entra mai in 1,20-1,34; per PUNTA non esiste nel corpus una partita con
sfavorita 4-8 e favorita avanti 2-0/3-1/3-0 dal 66'). Senza un ingresso, i
controlli B3/B9/B12-B16 e P7-P10 restano tutti «non lo so»: il replay non
certifica niente delle due varianti.

CHE COSA SONO, ESATTAMENTE. Stream Betfair NATIVO (`op: mcm`, `rc` con
`atb/atl/trd`, `marketDefinition`) + sidecar dei punteggi nel formato IPS di
Betfair, cioe' gli STESSI due file che il registratore scrive per una partita
vera, scritti in `_live_raw/_synth_safe_*`. Da li' in poi **non cambia niente**:
stesso `HistoricalStream`, stesso `Scanner` vero, stesso `run_once`, stesso
matching di flumine con bet delay e coda. Il replay non sa che la partita e'
inventata, ed e' il punto.

**NON SONO DATI REALI E NON VANNO MAI CONTATI COME TALI.** Il prefisso `_synth_`
e' la dichiarazione (PROCESSO_STANDARD_BOT §6.1: «le sintetiche mai contate come
reali»): `validate_recordings` e il banco le riconoscono dal nome. Servono a far
esistere le CONDIZIONI della SPEC, non a misurare quanto rende una strategia.

CHE COSA E' INVENTATO: la partita (squadre, gol, cartellini, minuti) e il libro
degli ordini (prezzi e volumi). CHE COSA NON E': il formato, la sequenza degli
stati del mercato (OPEN -> SUSPENDED al gol -> OPEN -> CLOSED con il WINNER),
il ritardo dei punteggi, il bet delay, e tutto il codice che li legge.

LE QUATTRO PARTITE (perche' quattro: un'uscita CHIUDE la posizione, e ogni
uscita ha bisogno di una posizione sua; la linea dei gol ammessi dal manuale
non permette di aprirne quante se ne vuole):

  _synth_safe_base          BASE: ingresso a 1-0, la sfavorita PAREGGIA
                            (uscita in perdita, B12) -> secondo ingresso a 2-1
                            -> uscita a TEMPO all'80' (B14)
  _synth_safe_base_profitto BASE: ingresso a 1-0, la favorita segna il 2o gol
                            (uscita in profitto, B13)
  _synth_safe_base_rosso    BASE: ingresso a 1-0, ROSSO alla favorita
                            (uscita da cartellino, B15)
  _synth_safe_punta         PUNTA: 2-0 -> ingresso al 66'; 3-0 (profitto, P8)
                            -> ingresso; 3-1 (perdita, P7) -> ingresso ->
                            uscita a tempo all'83' (P9)

Uso:
    python -m Betfair.safe_strategy.tools.synth_safe --tutte
    python -m Betfair.safe_strategy.tools.synth_safe --partita _synth_safe_punta
    python -m Betfair.stream.backtest.certifica safe_base _synth_safe_base \\
        --scenari base --worker 1

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------- costanti
# kickoff di comodo (un martedi' sera): tutto il resto e' relativo a questo
KICKOFF = datetime(2026, 9, 15, 18, 0, 0, tzinfo=timezone.utc)
MINUTI_PRE = 20          # quanto si registra prima del fischio d'inizio
TICK_PRE_S = 20          # un book ogni 20 s prima del fischio
TICK_LIVE_S = 2          # un book ogni 2 s in gioco (il bot gira ogni 2 s)
TICK_PUNTEGGIO_S = 10    # un record IPS ogni 10 s, come il registratore vero
RITARDO_PUNTEGGIO_S = 3  # i punteggi arrivano 2-3 s dopo il fatto (IPS)
SOSPENSIONE_GOL_S = 20   # il mercato resta SUSPENDED dopo un gol
BET_DELAY_LIVE = 5       # secondi, come Betfair in gioco

# mercati: id stabili, cosi' due esecuzioni producono file identici
MK_MO = "1.900200001"
MK_CS = "1.900200002"
MK_OU25 = "1.900200003"
MK_OU35 = "1.900200004"

# runner MATCH_ODDS (sortPriority 1=casa, 2=fuori, 3=pareggio: la regola vera)
R_HOME, R_AWAY, R_DRAW = 7700001, 7700002, 7700003
# runner CORRECT_SCORE: gli id GLOBALI veri di Betfair, cosi' i nomi si
# risolvono con la mappa gia' verificata (`validate_opportunity.selection_name`)
CS_RUNNERS: List[Tuple[int, int]] = [
    (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6),
    (9063254, 17), (9063255, 18), (9063256, 19),
]
OU_UNDER, OU_OVER = 7710001, 7710002


def _ms(t: datetime) -> int:
    return int(t.timestamp() * 1000)


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ---------------------------------------------------------------------------
# LE PARTITE — gol, cartellini e prezzi. Una tabella, nessuna logica nascosta.
# ---------------------------------------------------------------------------
class Partita:
    """La sceneggiatura di una partita sintetica.

    ``gol``   : [(minuto, 'home'|'away')]
    ``rossi`` : [(minuto, 'home'|'away')]
    ``prezzi``: {(gol_casa, gol_fuori): {'home': (back, lay), 'draw': ..., 'away': ...}}
                il BACK e' quello che il motore legge come "quota live"; il LAY
                e' quello a cui si banca.
    """

    def __init__(self, nome: str, home: str, away: str, *,
                 gol: Sequence[Tuple[int, str]],
                 rossi: Sequence[Tuple[int, str]],
                 prezzi: Dict[Tuple[int, int], Dict[str, Tuple[float, float]]],
                 pre_ko: Dict[str, Tuple[float, float]],
                 durata_min: int = 95,
                 nota: str = "",
                 cs_runners: Optional[Sequence[Tuple[int, int]]] = None,
                 cs_prezzi: Optional[Any] = None) -> None:
        self.nome = nome
        self.home = home
        self.away = away
        self.gol = list(gol)
        self.rossi = list(rossi)
        self.prezzi = prezzi
        self.pre_ko = pre_ko
        self.durata_min = int(durata_min)
        self.nota = nota
        # ---- estensione per OMEGA (16/09 sera) ----
        # Omega banca il RISULTATO ESATTO, quindi ha bisogno di piu' celle di
        # quelle che servono alla Safe (che sui CS guarda solo gli aggregati) e
        # di un prezzo che si MUOVE nel tempo (per far esistere il caso «abbinato
        # a un prezzo migliore di quello chiesto», controllo K1). Due campi
        # facoltativi: chi non li passa ha esattamente il comportamento di prima.
        self.cs_runners = list(cs_runners) if cs_runners else None
        self.cs_prezzi = cs_prezzi          # (sort, minuto) -> (back, lay) | None

    # ------------------------------------------------------------- stato
    def punteggio(self, minuto: float) -> Tuple[int, int]:
        h = sum(1 for m, s in self.gol if s == "home" and m <= minuto)
        a = sum(1 for m, s in self.gol if s == "away" and m <= minuto)
        return h, a

    def rossi_a(self, minuto: float) -> Tuple[int, int]:
        h = sum(1 for m, s in self.rossi if s == "home" and m <= minuto)
        a = sum(1 for m, s in self.rossi if s == "away" and m <= minuto)
        return h, a

    def sospeso(self, minuto: float) -> bool:
        """Dopo un gol o un rosso il mercato e' SOSPESO per qualche decina di
        secondi: e' quello che fa Betfair, e il bot lo deve vedere."""
        for m, _s in list(self.gol) + list(self.rossi):
            if m <= minuto < m + SOSPENSIONE_GOL_S / 60.0:
                return True
        return False

    def quote(self, minuto: float) -> Dict[str, Tuple[float, float]]:
        h, a = self.punteggio(minuto)
        if (h, a) in self.prezzi:
            return self.prezzi[(h, a)]
        # nessuna riga per questo punteggio: si tiene l'ultima nota (il libro
        # non sparisce mai)
        migliore = None
        for (ph, pa), val in self.prezzi.items():
            if ph <= h and pa <= a:
                if migliore is None or (ph + pa) > (migliore[0] + migliore[1]):
                    migliore = (ph, pa)
        return self.prezzi[migliore] if migliore else self.prezzi[(0, 0)]

    def vincitore(self) -> str:
        h, a = self.punteggio(self.durata_min + 10)
        return "home" if h > a else ("away" if a > h else "draw")


def _quote_base_standard() -> Dict[Tuple[int, int], Dict[str, Tuple[float, float]]]:
    """Il libro di una partita con favorita di casa a 1,64 pre-match.

    A 1-0 la favorita sta in 1,20-1,34 (la banda della SPEC), al pareggio
    risale, tornata avanti riscende: e' il movimento che la strategia sfrutta.
    """
    return {
        (0, 0): {"home": (1.60, 1.62), "draw": (4.0, 4.1), "away": (5.6, 5.8)},
        (1, 0): {"home": (1.28, 1.30), "draw": (5.0, 5.2), "away": (12.0, 13.0)},
        (1, 1): {"home": (1.90, 1.95), "draw": (3.2, 3.3), "away": (4.4, 4.6)},
        (2, 1): {"home": (1.26, 1.28), "draw": (6.0, 6.4), "away": (14.0, 15.0)},
        (2, 0): {"home": (1.08, 1.09), "draw": (11.0, 12.0), "away": (40.0, 44.0)},
        (3, 1): {"home": (1.04, 1.05), "draw": (24.0, 26.0), "away": (70.0, 80.0)},
    }


PARTITE: Dict[str, Partita] = {}

# 1) BASE — perdita (la sfavorita pareggia) e uscita a TEMPO
PARTITE["_synth_safe_base"] = Partita(
    "_synth_safe_base", "Alfa Synth FC", "Beta Synth FC",
    gol=[(30, "home"), (62, "away"), (66, "home")],
    rossi=[],
    prezzi=_quote_base_standard(),
    pre_ko={"home": (1.64, 1.66), "draw": (3.9, 4.0), "away": (5.4, 5.6)},
    nota="ingresso 1-0 al 55' -> pareggio della sfavorita al 62' (B12) -> "
         "secondo ingresso 2-1 -> uscita a tempo all'80' (B14)")

# 2) BASE — profitto (la favorita segna il secondo gol)
PARTITE["_synth_safe_base_profitto"] = Partita(
    "_synth_safe_base_profitto", "Gamma Synth FC", "Delta Synth FC",
    gol=[(28, "home"), (61, "home")],
    rossi=[],
    prezzi=_quote_base_standard(),
    pre_ko={"home": (1.64, 1.66), "draw": (3.9, 4.0), "away": (5.4, 5.6)},
    nota="ingresso 1-0 al 55' -> la favorita segna il 2o gol al 61' (B13)")

# 3) BASE — rosso alla favorita
PARTITE["_synth_safe_base_rosso"] = Partita(
    "_synth_safe_base_rosso", "Epsilon Synth FC", "Zeta Synth FC",
    gol=[(26, "home")],
    rossi=[(58, "home")],
    prezzi={
        (0, 0): {"home": (1.60, 1.62), "draw": (4.0, 4.1), "away": (5.6, 5.8)},
        # dopo il rosso alla favorita il mercato la paga di piu': il prezzo
        # cambia, ma l'uscita la decide il CARTELLINO, non la quota
        (1, 0): {"home": (1.28, 1.30), "draw": (5.0, 5.2), "away": (12.0, 13.0)},
    },
    pre_ko={"home": (1.64, 1.66), "draw": (3.9, 4.0), "away": (5.4, 5.6)},
    nota="ingresso 1-0 al 55' -> ROSSO alla favorita al 58' (B15)")

# 4) PUNTA — profitto, perdita e uscita a tempo, tre ingressi
PARTITE["_synth_safe_punta"] = Partita(
    "_synth_safe_punta", "Eta Synth FC", "Theta Synth FC",
    gol=[(20, "home"), (50, "home"), (70, "home"), (78, "away")],
    rossi=[],
    prezzi={
        (0, 0): {"home": (1.60, 1.62), "draw": (4.0, 4.1), "away": (5.6, 5.8)},
        (1, 0): {"home": (1.30, 1.32), "draw": (5.0, 5.2), "away": (12.0, 13.0)},
        (2, 0): {"home": (1.06, 1.07), "draw": (13.0, 14.0), "away": (48.0, 52.0)},
        (3, 0): {"home": (1.04, 1.05), "draw": (26.0, 28.0), "away": (90.0, 100.0)},
        (3, 1): {"home": (1.05, 1.06), "draw": (22.0, 24.0), "away": (70.0, 80.0)},
    },
    pre_ko={"home": (1.64, 1.66), "draw": (3.9, 4.0), "away": (5.4, 5.6)},
    durata_min=95,
    nota="2-0 al 50' -> ingresso al 66' -> 3-0 al 70' (profitto, P8) -> "
         "ingresso -> 3-1 al 78' (perdita, P7) -> ingresso -> tempo all'83' (P9)")


# ---------------------------------------------------------------------------
# 5) SAFE BASE - ABBINAMENTO A UN PREZZO MIGLIORE DI QUELLO CHIESTO
#    (controllo K1, difetto 3 del 15/09: `avg_price` al posto di
#    `avg_price_matched`).
#
# PERCHE' SERVE. Ne' sulle 39 registrazioni vere ne' sulle altre sintetiche quel
# caso capita mai: il libro sta fermo per i cinque secondi del bet delay, quindi
# il prezzo CHIESTO e quello ABBINATO coincidono sempre e i due campi sono
# indistinguibili. Finche' coincidono, K1 non ha modo di accorgersi se qualcuno
# rimettesse `avg_price` (che non esiste) al posto di `avg_price_matched`: e' il
# caso che va COSTRUITO (PROCESSO_STANDARD_BOT §6.7).
#
# COME. La partita e' quella della BASE (1-0 al 30', ingresso al 55'), con UNA
# differenza: dal 55' il LAY DELLA SFAVORITA - che e' il prezzo a cui la BASE
# BANCA (B9: «nessun limite», l'argomento e' chiuso dall'utente) - CALA di un
# gradino vero ogni quattro secondi. Safe legge il book, chiede la lay al prezzo
# che ha visto, e mentre Betfair trattiene l'ordine per i cinque secondi del bet
# delay il prezzo migliora: l'abbinamento avviene piu' in basso di quanto
# chiesto, che per chi BANCA e' meglio (meno responsabilita' a parita' di
# incasso).
#
# CHE COSA NON SI TOCCA: il filtro d'ingresso della SPEC e' il BACK LIVE della
# FAVORITA (controllo B8), e quello resta fermo a 1,28, dentro la banda
# 1,20-1,34. La deriva sta tutta sul lato BANCATO, dove la SPEC non mette
# limiti, e la lay non scende mai sotto il back della stessa selezione: il libro
# non si incrocia mai.
# ---------------------------------------------------------------------------
# la scala Betfair VERA fra 10 e 20: passo 0,50. Un gradino ogni quattro
# secondi, per quattro gradini - sedici secondi di deriva, piu' che abbastanza
# perche' l'ingresso al 55' ci caschi dentro. Il back della sfavorita a 1-0 e'
# 12,00 (`_quote_base_standard`), quindi la lay non lo tocca mai.
DERIVA_BANCA = [14.5, 14.0, 13.5, 13.0]


class PartitaConDeriva(Partita):
    """Una `Partita` in cui il LAY di un lato SI MUOVE nel tempo.

    Non e' un formato nuovo e non tocca niente di cio' che c'era: e' la stessa
    partita, con `quote()` che per una finestra di minuti restituisce un lay
    che scende. Tutto il resto (stream, punteggi, sospensioni, chiusura del
    mercato) e' identico, perche' e' lo stesso codice.
    """

    def __init__(self, *a: Any, deriva_lato: str = "home",
                 deriva_da: float = 0.0, deriva_a: float = 0.0,
                 deriva: Sequence[float] = (), **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.deriva_lato = str(deriva_lato)
        self.deriva_da = float(deriva_da)
        self.deriva_a = float(deriva_a)
        self.deriva = list(deriva)

    def quote(self, minuto: float) -> Dict[str, Tuple[float, float]]:
        q = dict(super().quote(minuto))
        if not self.deriva or not (self.deriva_da <= minuto < self.deriva_a):
            return q
        passi = int((float(minuto) - self.deriva_da) * 15.0)     # uno ogni 4 s
        lay = self.deriva[min(passi, len(self.deriva) - 1)]
        back, _vecchio = q[self.deriva_lato]
        # il libro non si incrocia MAI: il lay non scende sotto il back
        q[self.deriva_lato] = (back, max(lay, back))
        return q


PARTITE["_synth_safe_prezzo_migliore"] = PartitaConDeriva(
    "_synth_safe_prezzo_migliore", "Iota Synth FC", "Kappa Synth FC",
    gol=[(30, "home")],
    rossi=[],
    prezzi=_quote_base_standard(),
    pre_ko={"home": (1.64, 1.66), "draw": (3.9, 4.0), "away": (5.4, 5.6)},
    durata_min=95,
    deriva_lato="away", deriva_da=55.0, deriva_a=62.0, deriva=DERIVA_BANCA,
    nota="BASE: 1-0 al 30', ingresso al 55' mentre la LAY della SFAVORITA (il "
         "prezzo a cui la BASE banca) cala di un gradino ogni 4 s. L'ordine si "
         "abbina a un prezzo MIGLIORE di quello chiesto (K1, difetto 3 del "
         "15/09); uscita a TEMPO all'80' (B14)")


# ---------------------------------------------------------------------------
# 5) OMEGA — abbinamento a un prezzo MIGLIORE di quello chiesto (K1, difetto 3
#    del 15/09: `avg_price` al posto di `avg_price_matched`).
#
# PERCHE' SERVE. Sulle 42 registrazioni vere quel caso non capita mai: Omega
# chiede FOK al best disponibile e si abbina a quello. Finche' non capita, il
# controllo K1 non ha un caso e il referto non dice «sano», dice «non lo so»
# (PROCESSO_STANDARD_BOT §6.7). Qui la condizione si COSTRUISCE.
#
# COME. Il Risultato Esatto porta i gusci fino al 3-3 (Omega ha bisogno di celle
# davvero rare: con i soli sei runner della Safe, da 0-0 al 55' non esiste
# nessuna cella a due gol di distanza che sia anche abbastanza improbabile).
# Il prezzo del "3 - 3" CALA di un tick ogni mezzo minuto dopo il 50': Omega
# legge il book, chiede il lay al prezzo che ha visto, e nel bet delay il prezzo
# migliora. Da quel momento cio' che il bot contabilizza dev'essere il prezzo
# ABBINATO, non quello CHIESTO.
#
# Il "3 - 3" NON esce (la partita finisce 1-0): la gamba va a settlement vinta,
# cosi' si esercita anche la commissione una volta sola (F1).
# ---------------------------------------------------------------------------
# i gusci del Risultato Esatto fino al 3-3: `selectionId` -> `sortPriority`.
# I nomi NON stanno nello stream (Betfair non li manda): li ricava la formula
# dei gusci di `Betfair/omega/tools/replay_registrazioni.nome_scoreline`, che
# e' la stessa che il replay usa sulle registrazioni vere.
CS_RUNNERS_OMEGA: List[Tuple[int, int]] = [(sid, sid) for sid in range(1, 17)] + [
    (9063254, 17), (9063255, 18), (9063256, 19)]
SID_TRE_TRE = 13            # "3 - 3" (guscio 3, posizione 3)
# la scala Betfair vera scendendo da 110: sopra 100 il passo e' 10, fra 50 e
# 100 e' 5. Nessun prezzo inventato, nessun mezzo tick.
_DERIVA_TRE_TRE = [110.0, 100.0, 95.0, 90.0, 85.0, 80.0, 75.0, 70.0, 65.0, 60.0]


def _cs_prezzi_omega(sort: int, minuto: float) -> Optional[Tuple[float, float]]:
    """Il libro del Risultato Esatto, minuto per minuto.

    Le celle vicine al punteggio stanno basse, quelle lontane alte: e' come e'
    fatto un mercato vero. L'unica cosa costruita e' la DERIVA del "3 - 3" dopo
    il 50': -1 tick ogni mezzo minuto, cioe' il prezzo che migliora mentre
    l'ordine e' trattenuto dal bet delay.
    """
    if sort >= 17:                       # gli aggregati «Any Unquoted»
        return (34.0, 36.0)
    # PRIMA DEL 56' il guscio 3 sta SOTTO la banda di quota di Omega
    # (`price_min` 20): cosi' nessuno dei due motori entra troppo presto, e la
    # finestra 2T di V3 (55'-85') e quella del v2 (50'-80') guardano lo STESSO
    # libro. Non e' una comodita': se il v2 aprisse al 50' smetterebbe di
    # interrogare il book, e il motore in ombra vedrebbe un istante solo.
    if sort >= 10 and minuto < 56:
        return (14.0, 15.0)
    if sort == SID_TRE_TRE:
        if minuto < 56:
            return (14.0, 15.0)
        # LA DERIVA. Un gradino della scala Betfair VERA ogni 4 secondi (due
        # book: `TICK_LIVE_S` = 2 s), dal 56'. Il bet delay in gioco e' 5 s
        # (`BET_DELAY_LIVE`), quindi fra il book che Omega LEGGE e il momento in
        # cui Betfair abbina passa almeno un gradino: l'ordine si abbina a un
        # prezzo MIGLIORE di quello chiesto. Non e' un prezzo inventato: sono
        # tick validi (sopra 100 il passo e' 10, fra 50 e 100 e' 5).
        passi = int(max(0.0, minuto - 56.0) * 15)      # uno ogni 4 s
        if passi < len(_DERIVA_TRE_TRE):
            lay = _DERIVA_TRE_TRE[passi]
        else:
            lay = _DERIVA_TRE_TRE[-1]
        return (round(lay - 5.0, 2), lay)
    if sort <= 4:                        # 0-0, 1-0, 1-1, 0-1
        return (7.0, 7.4)
    if sort <= 9:                        # il guscio 2
        return (16.0, 17.0)
    return (70.0, 75.0)                  # il resto del guscio 3


PARTITE["_synth_omega_prezzo_migliore"] = Partita(
    "_synth_omega_prezzo_migliore", "Omega Synth FC", "Kappa Synth FC",
    gol=[(12, "home")],
    rossi=[],
    prezzi={
        (0, 0): {"home": (1.80, 1.82), "draw": (3.6, 3.7), "away": (4.8, 5.0)},
        (1, 0): {"home": (1.40, 1.42), "draw": (4.6, 4.8), "away": (9.0, 9.6)},
    },
    pre_ko={"home": (1.80, 1.82), "draw": (3.6, 3.7), "away": (4.8, 5.0)},
    cs_runners=CS_RUNNERS_OMEGA,
    cs_prezzi=_cs_prezzi_omega,
    durata_min=95,
    nota="OMEGA: gol al 12', poi 1-0 fino alla fine. Il '3 - 3' si laya a 110 e "
         "CALA dal 56' mentre l'ordine e' nel bet delay: l'abbinamento avviene a un "
         "prezzo MIGLIORE del chiesto (K1, difetto 3 del 15/09). La gamba va a "
         "settlement VINTA (il 3-3 non esce), quindi esercita anche F1.")


# ---------------------------------------------------------------------------
# lo STREAM nativo
# ---------------------------------------------------------------------------
def _ladder(prezzo: float, *, lato: str, size: float = 5000.0) -> List[List[float]]:
    """Tre livelli di profondita' attorno al best, come un libro vero."""
    passo = 0.02 if prezzo < 3 else (0.1 if prezzo < 10 else 1.0)
    segno = -1.0 if lato == "atb" else 1.0
    out = []
    for i in range(3):
        p = round(prezzo + segno * passo * i, 2)
        if p <= 1.01:
            p = 1.01
        out.append([p, round(size / (i + 1), 2)])
    return out


# LO STREAM E' FATTO DI DELTA, NON DI FOTOGRAFIE. In `rc`, ogni coppia
# [prezzo, size] SOSTITUISCE quel livello e i livelli non nominati RESTANO:
# un livello si toglie solo mandandolo a size 0. Senza questo, la scaletta
# pre-match resterebbe la migliore per sempre e il libro sarebbe incrociato
# (misurato: back 1,64 e lay 1,62 al 60', con la favorita "live" ferma a 1,64).
_LIVELLI: Dict[Tuple[str, int, str], List[float]] = {}


def _azzera_book() -> None:
    _LIVELLI.clear()


def _delta(mid: str, rid: int, lato: str, livelli: List[List[float]]) -> List[List[float]]:
    """I livelli nuovi + gli zeri per quelli che spariscono."""
    chiave = (mid, rid, lato)
    prima = _LIVELLI.get(chiave) or []
    ora = [float(p) for p, _s in livelli]
    fuori = [[p, 0.0] for p in prima if p not in ora]
    _LIVELLI[chiave] = ora
    return list(livelli) + fuori


def _rc_mo(p: Partita, minuto: float) -> List[Dict[str, Any]]:
    q = p.quote(minuto)
    fuori = []
    for rid, lato in ((R_HOME, "home"), (R_AWAY, "away"), (R_DRAW, "draw")):
        back, lay = q[lato]
        fuori.append({
            "id": rid,
            "atb": _delta(MK_MO, rid, "atb", _ladder(back, lato="atb")),
            "atl": _delta(MK_MO, rid, "atl", _ladder(lay, lato="atl")),
            "trd": [[back, 12000.0], [lay, 9000.0]],
            "ltp": back,
            "tv": 21000.0,
        })
    return fuori


def _prezzo_cs(sid: int, sort: int, h: int, a: int) -> Tuple[float, float]:
    """Prezzi del Risultato Esatto: bastano plausibili e STABILI.

    «Altro risultato Casa/Ospite» (17/18) resta in banda 30-70 come su una
    partita vera a quel punteggio.
    """
    if sort == 17:
        return (32.0, 34.0)
    if sort == 18:
        return (46.0, 50.0)
    if sort == 19:
        return (60.0, 65.0)
    return (9.0, 9.4)


def _rc_cs(p: Partita, minuto: float) -> List[Dict[str, Any]]:
    h, a = p.punteggio(minuto)
    out = []
    for sid, sort in (p.cs_runners or CS_RUNNERS):
        if p.cs_prezzi is not None:
            prezzi = p.cs_prezzi(sort, minuto)
            if prezzi is None:
                continue
            back, lay = prezzi
        else:
            back, lay = _prezzo_cs(sid, sort, h, a)
        out.append({
            "id": sid,
            "atb": _delta(MK_CS, sid, "atb", _ladder(back, lato="atb", size=900.0)),
            "atl": _delta(MK_CS, sid, "atl", _ladder(lay, lato="atl", size=900.0)),
            "trd": [[back, 400.0]],
            "ltp": back,
            "tv": 900.0,
        })
    return out


def _rc_ou(linea: float, p: Partita, minuto: float,
           mid: str = "") -> List[Dict[str, Any]]:
    h, a = p.punteggio(minuto)
    gol = h + a
    # piu' gol ci sono, piu' l'Over costa poco: aritmetica grossolana ma
    # monotona, e il bot qui non ci opera (serve la presenza del mercato)
    over = max(1.05, 2.0 - 0.45 * max(0, gol - int(linea)))
    under = max(1.05, round(1.0 / max(0.05, 1.0 - 1.0 / over), 2))
    out = []
    for rid, prezzo in ((OU_UNDER, under), (OU_OVER, over)):
        out.append({
            "id": rid,
            "atb": _delta(mid, rid, "atb", _ladder(prezzo, lato="atb", size=2000.0)),
            "atl": _delta(mid, rid, "atl",
                          _ladder(round(prezzo + 0.02, 2), lato="atl", size=2000.0)),
            "trd": [[prezzo, 3000.0]],
            "ltp": prezzo,
            "tv": 6000.0,
        })
    return out


def _mdef(p: Partita, *, market_id: str, market_type: str,
          runners: Sequence[Tuple[int, int]], inplay: bool, status: str,
          bet_delay: int, vincitori: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
    return {
        "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
        "marketBaseRate": 5, "eventId": p.nome, "eventTypeId": "1",
        "numberOfWinners": 1, "bettingType": "ODDS", "marketType": market_type,
        "marketTime": _iso(KICKOFF), "suspendTime": _iso(KICKOFF),
        "bspReconciled": False, "complete": True, "inPlay": inplay,
        "crossMatching": True, "runnersVoidable": False,
        "numberOfActiveRunners": len(runners), "betDelay": int(bet_delay),
        "status": status,
        "runners": [
            {"status": (vincitori or {}).get(rid, "ACTIVE"),
             "sortPriority": sort, "id": rid}
            for rid, sort in runners
        ],
        "regulators": ["MR_ITA"], "discountAllowed": True, "timezone": "GMT",
        "openDate": _iso(KICKOFF), "version": 1,
        "priceLadderDefinition": {"type": "CLASSIC"},
    }


_RUNNERS_MO = [(R_HOME, 1), (R_AWAY, 2), (R_DRAW, 3)]
_RUNNERS_OU = [(OU_UNDER, 1), (OU_OVER, 2)]


def _messaggio(pt: int, mc: List[Dict[str, Any]]) -> str:
    return json.dumps({"op": "mcm", "pt": pt, "clk": str(pt), "mc": mc},
                      separators=(",", ":"))


def scrivi_raw(p: Partita, path: str) -> int:
    """Lo stream nativo dell'intera partita. Torna quanti messaggi ha scritto."""
    _azzera_book()
    righe: List[str] = []
    mercati = (
        (MK_MO, "MATCH_ODDS", _RUNNERS_MO, _rc_mo),
        (MK_CS, "CORRECT_SCORE", (p.cs_runners or CS_RUNNERS), _rc_cs),
        (MK_OU25, "OVER_UNDER_25", _RUNNERS_OU,
         lambda pa, m: _rc_ou(2.5, pa, m, MK_OU25)),
        (MK_OU35, "OVER_UNDER_35", _RUNNERS_OU,
         lambda pa, m: _rc_ou(3.5, pa, m, MK_OU35)),
    )

    # --- prima del fischio: immagine completa + aggiornamenti ogni 20 s
    for i in range(MINUTI_PRE * 60 // TICK_PRE_S):
        t = KICKOFF - timedelta(seconds=(MINUTI_PRE * 60 - i * TICK_PRE_S))
        mc = []
        for mid, mtype, runners, _fn in mercati:
            blocco: Dict[str, Any] = {"id": mid}
            if i == 0:
                blocco["img"] = True
                blocco["marketDefinition"] = _mdef(
                    p, market_id=mid, market_type=mtype, runners=runners,
                    inplay=False, status="OPEN", bet_delay=0)
            if mtype == "MATCH_ODDS":
                blocco["rc"] = [
                    {"id": rid,
                     "atb": _delta(MK_MO, rid, "atb",
                                   _ladder(p.pre_ko[lato][0], lato="atb")),
                     "atl": _delta(MK_MO, rid, "atl",
                                   _ladder(p.pre_ko[lato][1], lato="atl")),
                     "trd": [[p.pre_ko[lato][0], 30000.0]],
                     "ltp": p.pre_ko[lato][0], "tv": 60000.0}
                    for rid, lato in ((R_HOME, "home"), (R_AWAY, "away"),
                                      (R_DRAW, "draw"))
                ]
            elif mtype == "CORRECT_SCORE":
                blocco["rc"] = _rc_cs(p, -1)
            else:
                linea = 2.5 if mid == MK_OU25 else 3.5
                blocco["rc"] = _rc_ou(linea, p, -1, mid)
            mc.append(blocco)
        righe.append(_messaggio(_ms(t), mc))

    # --- in gioco
    sospeso_prima = False
    passi = int(p.durata_min * 60 / TICK_LIVE_S)
    for i in range(passi + 1):
        sec = i * TICK_LIVE_S
        t = KICKOFF + timedelta(seconds=sec)
        minuto = sec / 60.0
        sospeso = p.sospeso(minuto)
        cambio_stato = (i == 0) or (sospeso != sospeso_prima)
        sospeso_prima = sospeso
        mc = []
        for mid, mtype, runners, fn in mercati:
            blocco: Dict[str, Any] = {"id": mid}
            if cambio_stato:
                blocco["marketDefinition"] = _mdef(
                    p, market_id=mid, market_type=mtype, runners=runners,
                    inplay=True, status=("SUSPENDED" if sospeso else "OPEN"),
                    bet_delay=BET_DELAY_LIVE)
            if not sospeso:
                blocco["rc"] = fn(p, minuto)
            if len(blocco) > 1:
                mc.append(blocco)
        if mc:
            righe.append(_messaggio(_ms(t), mc))

    # --- fischio finale: mercato CHIUSO con il vincitore (serve al settlement)
    t = KICKOFF + timedelta(seconds=(p.durata_min * 60 + 60))
    vinc = p.vincitore()
    vincitori_mo = {R_HOME: "LOSER", R_AWAY: "LOSER", R_DRAW: "LOSER"}
    vincitori_mo[{"home": R_HOME, "away": R_AWAY, "draw": R_DRAW}[vinc]] = "WINNER"
    h, a = p.punteggio(p.durata_min + 10)
    runner_cs = list(p.cs_runners or CS_RUNNERS)
    esatto = {sid: "LOSER" for sid, _s in runner_cs}
    # il punteggio finale: se e' fra i quotati vince quello, altrimenti vince
    # «Altro risultato Casa/Ospite» (che e' esattamente cio' che la variante
    # ESATTO banca)
    from . import validate_opportunity as VO

    quotato = None
    for sid, _sort in runner_cs:
        if VO._SCORE_IDS.get(sid) == (h, a):
            quotato = sid
    if quotato is not None:
        esatto[quotato] = "WINNER"
    elif h > a:
        esatto[9063254] = "WINNER"
    elif a > h:
        esatto[9063255] = "WINNER"
    else:
        esatto[9063256] = "WINNER"
    gol_tot = h + a
    mc = [
        {"id": MK_MO, "marketDefinition": _mdef(
            p, market_id=MK_MO, market_type="MATCH_ODDS", runners=_RUNNERS_MO,
            inplay=False, status="CLOSED", bet_delay=BET_DELAY_LIVE,
            vincitori=vincitori_mo)},
        {"id": MK_CS, "marketDefinition": _mdef(
            p, market_id=MK_CS, market_type="CORRECT_SCORE", runners=runner_cs,
            inplay=False, status="CLOSED", bet_delay=BET_DELAY_LIVE,
            vincitori=esatto)},
    ]
    for mid, linea in ((MK_OU25, 2.5), (MK_OU35, 3.5)):
        vincitori_ou = {
            OU_UNDER: "WINNER" if gol_tot < linea else "LOSER",
            OU_OVER: "WINNER" if gol_tot > linea else "LOSER",
        }
        mc.append({"id": mid, "marketDefinition": _mdef(
            p, market_id=mid, market_type=("OVER_UNDER_25" if linea == 2.5
                                           else "OVER_UNDER_35"),
            runners=_RUNNERS_OU, inplay=False, status="CLOSED",
            bet_delay=BET_DELAY_LIVE, vincitori=vincitori_ou)})
    righe.append(_messaggio(_ms(t), mc))

    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(righe) + "\n")
    return len(righe)


# ---------------------------------------------------------------------------
# il SIDECAR dei punteggi (formato IPS di Betfair, quello vero)
# ---------------------------------------------------------------------------
def _record_ips(p: Partita, minuto: int, t: datetime) -> Dict[str, Any]:
    h, a = p.punteggio(minuto)
    rh, ra = p.rossi_a(minuto)
    stato = "FirstHalf" if minuto <= 45 else "SecondHalf"
    if minuto <= 0:
        stato = "KickOff"

    def lato(nome: str, gol: int, rossi: int) -> Dict[str, Any]:
        return {
            "name": nome, "score": str(gol), "halfTimeScore": "",
            "fullTimeScore": "", "penaltiesScore": "", "penaltiesSequence": [],
            "games": "", "sets": "", "numberOfYellowCards": 1,
            "numberOfRedCards": int(rossi), "numberOfCards": 1 + int(rossi),
            "numberOfCorners": 3, "numberOfCornersFirstHalf": 2,
            "bookingPoints": 10,
        }

    return {
        "eventTypeId": 1, "eventId": p.nome,
        "score": {
            "home": lato(p.home, h, rh), "away": lato(p.away, a, ra),
            "numberOfYellowCards": 2, "numberOfRedCards": int(rh + ra),
            "numberOfCards": 2 + int(rh + ra), "numberOfCorners": 6,
            "numberOfCornersFirstHalf": 4, "bookingPoints": 20,
        },
        "timeElapsed": int(minuto), "elapsedRegularTime": int(minuto),
        "timeElapsedSeconds": int(minuto * 60), "fullTimeElapsed":
            {"hour": 0, "min": int(minuto), "sec": 0},
        "status": stato, "matchStatus": stato,
    }


def scrivi_punteggi(p: Partita, path: str) -> int:
    righe: List[str] = []
    passi = int(p.durata_min * 60 / TICK_PUNTEGGIO_S)
    for i in range(passi + 1):
        sec = i * TICK_PUNTEGGIO_S
        # il punteggio arriva con il RITARDO dell'IPS (2-3 s dopo il fatto):
        # e' la stessa cosa che fa il registratore vero
        t = KICKOFF + timedelta(seconds=sec + RITARDO_PUNTEGGIO_S)
        minuto = sec // 60
        rec = _record_ips(p, minuto, t)
        h, a = p.punteggio(minuto)
        rh, ra = p.rossi_a(minuto)
        righe.append(json.dumps({
            "ts": t.isoformat(), "ts_ms": _ms(t), "source": "betfair",
            "minute": int(minuto), "score_home": h, "score_away": a,
            "event_type": None,
            "stats": {
                "corners": {"home": 3, "away": 3, "home_1h": 2, "home_2h": 1,
                            "away_1h": 2, "away_2h": 1},
                "cards": {"yellow_home": 1, "yellow_away": 1,
                          "red_home": rh, "red_away": ra},
                "booking_points": 20, "match_status": rec["matchStatus"],
                "elapsed_added_time": None,
                "home_name": p.home, "away_name": p.away,
            },
            "payload": rec,
        }, separators=(",", ":")))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(righe) + "\n")
    return len(righe)




# ===========================================================================
# TENNIS SINTETICO — per i controlli che nessuna delle tre partite reali
# riesce a sollecitare (T6 sotto 1,03 tenuto fino alla fine, T8 settlement)
# ===========================================================================
# Perche' serve: sulla terna reale (35792939 / 35795560 / 35790650) T8 non ha
# mai un caso perche' il SETTLEMENT non arriva mai (nessuna delle tre resta
# aperta fino al mercato CHIUSO con una posizione viva), e T6 ne ha uno solo.
# Qui la partita e' costruita perche' succedano tutte e due: ingresso a 1,02
# (sotto la soglia di take profit), crollo del giocatore puntato, mercato che
# CHIUDE con il WINNER dall'altra parte.
#
# FORMATO: identico a quello del registratore tennis
# (`<id>.raw.jsonl` + `<id>.score.jsonl` con righe {"t": epoch_s, "score": …}).

MK_MO_T = "1.900300001"
T_P1, T_P2 = 7720001, 7720002
TICK_TENNIS_S = 5          # un book ogni 5 s
BET_DELAY_TENNIS = 3       # come le registrazioni vere


class PartitaTennis:
    """Sceneggiatura di una partita di tennis sintetica.

    ``tappe``: [(secondo, set_p1, set_p2, game_p1, game_p2, back_p1, lay_p1)]
    da quel secondo in poi valgono quel punteggio e quei prezzi.
    """

    def __init__(self, nome: str, tappe, durata_s: int, vincitore: str,
                 nota: str = "") -> None:
        self.nome = nome
        self.tappe = list(tappe)
        self.durata_s = int(durata_s)
        self.vincitore = vincitore
        self.nota = nota

    def stato(self, sec: float):
        corrente = self.tappe[0]
        for t in self.tappe:
            if t[0] <= sec:
                corrente = t
        return corrente


TENNIS: Dict[str, PartitaTennis] = {
    "_synth_safe_tennis": PartitaTennis(
        "_synth_safe_tennis",
        tappe=[
            # sec,  set1, set2, game1, game2, back_p1, lay_p1
            (0,      1, 0, 0, 0, 1.06, 1.07),   # 1o set vinto, 2o set a 0-0
            (300,    1, 0, 1, 0, 1.04, 1.05),
            (600,    1, 0, 2, 0, 1.02, 1.03),   # INGRESSO: 1 set + 2 game, a 1,02
            (900,    1, 0, 2, 1, 1.09, 1.10),   # perde un game
            (1200,   1, 0, 2, 2, 1.60, 1.62),   # due di fila + parita' -> OBBLIGO
            (1500,   1, 0, 2, 4, 3.20, 3.30),
            (1800,   1, 1, 0, 0, 5.00, 5.20),   # secondo set perso
            (2100,   1, 1, 0, 3, 12.0, 13.0),
            (2400,   1, 1, 0, 5, 40.0, 44.0),
        ],
        durata_s=2700, vincitore="p2",
        nota="ingresso a 1,02 (T6) -> crollo (obbligo di uscita, T7) -> il "
             "mercato CHIUDE con il WINNER dall'altra parte (settlement, T8)"),
    # ABBINAMENTO A UN PREZZO MIGLIORE DI QUELLO CHIESTO, lato TENNIS (K1).
    # Il tennis APRE in BACK: per chi punta, «meglio» vuol dire una quota PIU'
    # ALTA. Qui il back di p1 sale di due tick VERI (0,01 sotto 2,00) a ogni
    # book, cioe' ogni 5 s.
    #
    # ⚠️ REPERTO MISURATO IL 16/09 SERA, e va detto perche' questa partita NON
    # mantiene la promessa: su questo percorso del banco
    # (`banco_comune.replay_evento`, quello del tennis) flumine decide il fill AL
    # MOMENTO DEL PIAZZAMENTO, contro lo stesso `market_book` che il bot ha
    # appena letto - il bet delay conta i book (`book attesi`) ma non sposta il
    # libro su cui l'ordine si abbina. Misurato: ordine chiesto a 1,10 e
    # abbinato a 1,10 sul book dei 20 s, mentre quello dei 25 s offriva gia'
    # 1,12. Sul percorso del calcio (`replay_registrazioni`) la stessa cosa
    # riesce, perche' li' la riga dello scanner e' write-on-change e RESTA
    # INDIETRO rispetto al book corrente. Quindi il caso «prezzo migliore» sul
    # tennis resta ⊘: la causa e' nel banco, non nel bot, e `execution.place`
    # (dove vive il difetto 3 del 15/09) e' lo STESSO identico codice del
    # calcio, dove il caso c'e' ed e' rosso.
    "_synth_safe_tennis_prezzo_migliore": PartitaTennis(
        "_synth_safe_tennis_prezzo_migliore",
        tappe=([(sec, 1, 0, sec // 60, 0,
                 round(1.02 + 0.02 * (sec // TICK_TENNIS_S), 2),
                 round(1.03 + 0.02 * (sec // TICK_TENNIS_S), 2))
                for sec in range(0, 300, TICK_TENNIS_S)]
               + [(300, 1, 1, 0, 0, 3.20, 3.30),
                  (600, 1, 1, 0, 4, 12.0, 13.0),
                  (900, 1, 2, 0, 0, 40.0, 44.0)]),
        durata_s=1200, vincitore="p2",
        nota="ingresso dichiarato a 1,02 con il back che SALE di due tick a ogni "
             "book. Su questo banco il fill avviene sullo STESSO book letto dal "
             "bot, quindi il «prezzo migliore» sul tennis resta ⊘ (vedi il "
             "commento qui sopra); la partita resta utile perche' esercita "
             "K1/K3/K4/K7 e il settlement col WINNER dall'altra parte (T8)"),
}


def _rc_tennis(back: float, lay: float) -> List[Dict[str, Any]]:
    out = []
    for rid, (b, l) in ((T_P1, (back, lay)),
                        (T_P2, (round(1.0 / max(0.02, 1.0 - 1.0 / back), 2),
                                round(1.0 / max(0.02, 1.0 - 1.0 / lay), 2)))):
        out.append({
            "id": rid,
            "atb": _delta(MK_MO_T, rid, "atb", _ladder(b, lato="atb", size=3000.0)),
            "atl": _delta(MK_MO_T, rid, "atl", _ladder(l, lato="atl", size=3000.0)),
            "trd": [[b, 8000.0]],
            "ltp": b,
            "tv": 16000.0,
        })
    return out


def _mdef_tennis(nome: str, *, status: str, inplay: bool,
                 vincitori: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
    return {
        "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
        "marketBaseRate": 5, "eventId": nome, "eventTypeId": "2",
        "numberOfWinners": 1, "bettingType": "ODDS", "marketType": "MATCH_ODDS",
        "marketTime": _iso(KICKOFF), "suspendTime": _iso(KICKOFF),
        "bspReconciled": False, "complete": True, "inPlay": inplay,
        "crossMatching": True, "runnersVoidable": False,
        "numberOfActiveRunners": 2, "betDelay": BET_DELAY_TENNIS, "status": status,
        "runners": [
            {"status": (vincitori or {}).get(T_P1, "ACTIVE"), "sortPriority": 1, "id": T_P1},
            {"status": (vincitori or {}).get(T_P2, "ACTIVE"), "sortPriority": 2, "id": T_P2},
        ],
        "regulators": ["MR_ITA"], "discountAllowed": True, "timezone": "UTC",
        "openDate": _iso(KICKOFF), "version": 1,
        "priceLadderDefinition": {"type": "CLASSIC"},
    }


def scrivi_tennis(p: PartitaTennis, cartella: str) -> Tuple[int, int]:
    _azzera_book()
    dest = os.path.join(cartella, p.nome)
    os.makedirs(dest, exist_ok=True)
    righe: List[str] = []
    for i in range(int(p.durata_s / TICK_TENNIS_S) + 1):
        sec = i * TICK_TENNIS_S
        t = KICKOFF + timedelta(seconds=sec)
        _s1, _s2, _g1, _g2, back, lay = p.stato(sec)[1:]
        blocco: Dict[str, Any] = {"id": MK_MO_T}
        if i == 0:
            blocco["img"] = True
            blocco["marketDefinition"] = _mdef_tennis(p.nome, status="OPEN", inplay=True)
        blocco["rc"] = _rc_tennis(back, lay)
        righe.append(_messaggio(_ms(t), [blocco]))
    # fine partita: mercato CHIUSO con il WINNER (e' quello che manca alla terna
    # reale perche' T8 non ha mai un caso)
    t = KICKOFF + timedelta(seconds=p.durata_s + 60)
    vincitori = {T_P1: "LOSER", T_P2: "LOSER"}
    vincitori[T_P1 if p.vincitore == "p1" else T_P2] = "WINNER"
    righe.append(_messaggio(_ms(t), [{"id": MK_MO_T, "marketDefinition": _mdef_tennis(
        p.nome, status="CLOSED", inplay=False, vincitori=vincitori)}]))
    with open(os.path.join(dest, f"{p.nome}.raw.jsonl"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(righe) + "\n")

    # il sidecar: righe {"t": epoch_s, "score": <record IPS tennis>}
    punteggi: List[str] = []
    for i in range(int(p.durata_s / TICK_TENNIS_S) + 1):
        sec = i * TICK_TENNIS_S
        t = KICKOFF + timedelta(seconds=sec + 2)   # il ritardo dell'IPS
        s1, s2, g1, g2 = p.stato(sec)[1:5]

        def lato(sets_: int, games_: int, serve: bool) -> Dict[str, Any]:
            return {"score": "30", "halfTimeScore": "", "fullTimeScore": "",
                    "penaltiesScore": "", "penaltiesSequence": [],
                    "games": str(games_), "sets": str(sets_), "gameSequence": [],
                    "isServing": serve, "highlight": False, "serviceBreaks": 0}

        punteggi.append(json.dumps({
            "t": _ms(t) / 1000.0,
            "score": {
                "eventTypeId": 2, "eventId": p.nome,
                "score": {"home": lato(s1, g1, True), "away": lato(s2, g2, False)},
                "currentSet": s1 + s2 + 1, "currentGame": g1 + g2 + 1,
                "fullTimeElapsed": {"hour": 0, "min": int(sec // 60), "sec": int(sec % 60)},
            },
        }, separators=(",", ":")))
    with open(os.path.join(dest, f"{p.nome}.score.jsonl"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(punteggi) + "\n")
    return len(righe), len(punteggi)

# ---------------------------------------------------------------------------
def genera(nome: str, cartella: str) -> Tuple[int, int]:
    p = PARTITE[nome]
    dest = os.path.join(cartella, p.nome)
    os.makedirs(dest, exist_ok=True)
    n_raw = scrivi_raw(p, os.path.join(dest, f"{p.nome}.raw.jsonl"))
    n_sc = scrivi_punteggi(p, os.path.join(dest, f"{p.nome}.scores.jsonl"))
    return n_raw, n_sc


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    radice = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                          "..", "..", "..", "_live_raw"))
    ap.add_argument("--out", default=radice)
    ap.add_argument("--partita", action="append", choices=sorted(PARTITE))
    ap.add_argument("--tennis", action="store_true",
                    help="solo le partite di TENNIS sintetiche")
    ap.add_argument("--tutte", action="store_true")
    a = ap.parse_args(argv)
    if a.tennis:
        for nome, pt in sorted(TENNIS.items()):
            n_raw, n_sc = scrivi_tennis(pt, a.out)
            print(f"{nome}: {n_raw} messaggi, {n_sc} punteggi -> {a.out}")
            print(f"   {pt.nota}")
        return 0
    nomi = sorted(PARTITE) if (a.tutte or not a.partita) else a.partita
    for nome in nomi:
        n_raw, n_sc = genera(nome, a.out)
        p = PARTITE[nome]
        print(f"{nome}: {n_raw} messaggi, {n_sc} punteggi -> {a.out}")
        print(f"   {p.nota}")
    if a.tutte or not a.partita:
        for nome, pt in sorted(TENNIS.items()):
            n_raw, n_sc = scrivi_tennis(pt, a.out)
            print(f"{nome}: {n_raw} messaggi, {n_sc} punteggi -> {a.out}")
            print(f"   {pt.nota}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
