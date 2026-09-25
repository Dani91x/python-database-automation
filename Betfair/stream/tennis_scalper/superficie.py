"""superficie.py - la SUPERFICIE di una partita di tennis dal nome del torneo.

Decisione dell'utente del 25/09 (h21:30): tennis_pro acceso con la superficie
VERA della partita, non col fisso ``'grass'`` di ``tennis_pro_bot.py``.

ATTENZIONE: I setup su terra/cemento (lay-reversal: serving-for-set, doppio break,
favorito compresso, e il break point dal lato del ribattitore) NON sono
certificati sul banco: tutte le registrazioni tennis che abbiamo sono di erba
(Wimbledon, 07/07). Questa mappa decide QUALE ramo del bot si accende; se quel
ramo guadagna lo diranno il paper e le registrazioni future.

COME SI DECIDE (in quest'ordine, la prima regola che risponde vince):
  1. il NOME della competizione DICHIARA la superficie (``clay``, ``grass``,
     ``hard``, ``indoor``, ``terra``, ``erba``, ``cemento``...): succede con i
     Challenger e gli ITF (es. "Challenger Genova (Clay)"). Fonte: ``nome``.
  2. la MAPPA dei tornei qui sotto (``MAPPA_TORNEI``): una voce per torneo, con
     le sue parole chiave e la fonte. Fonte: ``mappa``.
  3. nessuna delle due: ``'hard'`` (cemento), DICHIARATO come default. Fonte:
     ``default``. Il cemento e' la superficie piu' frequente del calendario.

La mappa e' DATI, non logica: per aggiungere un torneo si aggiunge una voce.
Le parole chiave si cercano a PAROLA INTERA sul nome normalizzato (minuscolo,
senza accenti, apostrofi tolti): "halle" NON scatta dentro "challenger".
L'ordine delle voci conta solo per i nomi ambigui (es. "WTA Stuttgart", terra,
prima di "Stuttgart", erba): le voci piu' specifiche stanno sopra.

Superfici (i codici che il bot legge, ``tennis_pro_bot.py``):
  ``grass`` erba  |  ``clay`` terra  |  ``hard`` cemento
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

#: la superficie quando il torneo non e' riconosciuto (DICHIARATA, fonte 'default')
SUPERFICIE_DEFAULT = "hard"

FONTE_NOME = "nome"          # il nome della competizione dichiara la superficie
FONTE_MAPPA = "mappa"        # voce di MAPPA_TORNEI
FONTE_DEFAULT = "default"    # torneo sconosciuto (o nome assente)

#: nomi italiani per la UI e per i log
NOME_SUPERFICIE: Dict[str, str] = {"grass": "erba", "clay": "terra", "hard": "cemento"}

_FONTE_CALENDARIO = "calendario ufficiale ATP/WTA (superficie del torneo)"

# ---------------------------------------------------------------------------
# 1. parole che DICHIARANO la superficie nel nome della competizione
# ---------------------------------------------------------------------------
PAROLE_SUPERFICIE: Tuple[Dict[str, Any], ...] = (
    {"superficie": "clay", "parole": ["clay", "terra battuta", "terra rossa"],
     "fonte": "il nome della competizione dichiara la terra"},
    {"superficie": "grass", "parole": ["grass", "erba"],
     "fonte": "il nome della competizione dichiara l'erba"},
    {"superficie": "hard", "parole": ["hard", "hardcourt", "indoor", "cemento", "carpet"],
     "fonte": "il nome della competizione dichiara il cemento/indoor"},
)

# ---------------------------------------------------------------------------
# 2. la mappa dei tornei (DATI). Voce -> superficie, parole chiave, fonte.
#    Le voci ambigue (stessa citta', superfici diverse fra ATP e WTA) stanno
#    SOPRA la voce generica della citta'.
# ---------------------------------------------------------------------------
MAPPA_TORNEI: Tuple[Dict[str, Any], ...] = (
    # ---- voci ambigue, piu' specifiche: prima ----
    {"voce": "WTA Stuttgart", "superficie": "clay",
     "parole": ["wta stuttgart", "porsche tennis grand prix"],
     "fonte": _FONTE_CALENDARIO + " - WTA Stoccarda: terra indoor"},
    {"voce": "WTA Lyon", "superficie": "hard",
     "parole": ["wta lyon", "wta lione"],
     "fonte": _FONTE_CALENDARIO + " - WTA Lione: cemento indoor"},
    {"voce": "Paris Masters (Bercy)", "superficie": "hard",
     "parole": ["paris masters", "rolex paris masters", "bercy", "parigi bercy"],
     "fonte": _FONTE_CALENDARIO + " - Masters 1000 di Parigi: cemento indoor"},
    # ---- ERBA ----
    {"voce": "Wimbledon", "superficie": "grass", "parole": ["wimbledon"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Queen's", "superficie": "grass", "parole": ["queens", "queens club"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Halle", "superficie": "grass", "parole": ["halle"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Eastbourne", "superficie": "grass", "parole": ["eastbourne"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Newport Beach (Challenger)", "superficie": "hard", "parole": ["newport beach"],
     "fonte": _FONTE_CALENDARIO + " - Challenger di Newport Beach: cemento"},
    {"voce": "Newport", "superficie": "grass", "parole": ["newport"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "'s-Hertogenbosch", "superficie": "grass",
     "parole": ["hertogenbosch", "s hertogenbosch", "den bosch", "libema open"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Mallorca", "superficie": "grass", "parole": ["mallorca", "maiorca"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Bad Homburg", "superficie": "grass", "parole": ["bad homburg"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Nottingham", "superficie": "grass", "parole": ["nottingham"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Birmingham", "superficie": "grass", "parole": ["birmingham"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Stuttgart (ATP)", "superficie": "grass",
     "parole": ["stuttgart", "stoccarda"],
     "fonte": _FONTE_CALENDARIO + " - ATP Stoccarda: erba"},
    {"voce": "Berlin (WTA)", "superficie": "grass", "parole": ["berlin", "berlino"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Ilkley / Surbiton", "superficie": "grass", "parole": ["ilkley", "surbiton"],
     "fonte": _FONTE_CALENDARIO + " - Challenger su erba"},
    # ---- TERRA ----
    {"voce": "Roland Garros", "superficie": "clay",
     "parole": ["roland garros", "french open", "open di francia"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Madrid", "superficie": "clay", "parole": ["madrid"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Roma", "superficie": "clay",
     "parole": ["rome", "roma", "internazionali d italia", "italian open"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Montecarlo", "superficie": "clay",
     "parole": ["monte carlo", "montecarlo"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Barcellona", "superficie": "clay", "parole": ["barcelona", "barcellona"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Amburgo", "superficie": "clay", "parole": ["hamburg", "amburgo"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Umag", "superficie": "clay", "parole": ["umag"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Kitzbuhel", "superficie": "clay", "parole": ["kitzbuhel", "kitzbuehel"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Gstaad", "superficie": "clay", "parole": ["gstaad"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Bastad", "superficie": "clay", "parole": ["bastad"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Bucarest", "superficie": "clay", "parole": ["bucharest", "bucarest"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Marrakech", "superficie": "clay", "parole": ["marrakech", "marrakesh"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Estoril", "superficie": "clay", "parole": ["estoril"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Ginevra", "superficie": "clay", "parole": ["geneva", "ginevra"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Lione (ATP)", "superficie": "clay", "parole": ["lyon", "lione"],
     "fonte": _FONTE_CALENDARIO + " - ATP Lione: terra"},
    {"voce": "Monaco di Baviera", "superficie": "clay", "parole": ["munich", "monaco di baviera"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Houston", "superficie": "clay", "parole": ["houston"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Charleston", "superficie": "clay", "parole": ["charleston"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Buenos Aires", "superficie": "clay", "parole": ["buenos aires"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Rio de Janeiro", "superficie": "clay", "parole": ["rio de janeiro", "rio open"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Santiago", "superficie": "clay", "parole": ["santiago"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Cordoba", "superficie": "clay", "parole": ["cordoba"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Rabat", "superficie": "clay", "parole": ["rabat"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Palermo", "superficie": "clay", "parole": ["palermo"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Praga", "superficie": "clay", "parole": ["prague", "praga"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Strasburgo", "superficie": "clay", "parole": ["strasbourg", "strasburgo"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Parma", "superficie": "clay", "parole": ["parma"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Budapest", "superficie": "clay", "parole": ["budapest"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Bogota", "superficie": "clay", "parole": ["bogota"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Iasi", "superficie": "clay", "parole": ["iasi"],
     "fonte": _FONTE_CALENDARIO},
    # ---- CEMENTO ----
    {"voce": "US Open", "superficie": "hard", "parole": ["us open"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Australian Open", "superficie": "hard", "parole": ["australian open"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Indian Wells", "superficie": "hard", "parole": ["indian wells"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Miami", "superficie": "hard", "parole": ["miami"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Cincinnati", "superficie": "hard", "parole": ["cincinnati"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Canada (Toronto/Montreal)", "superficie": "hard",
     "parole": ["toronto", "montreal", "canadian open", "national bank open"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Dubai", "superficie": "hard", "parole": ["dubai"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Doha", "superficie": "hard", "parole": ["doha", "qatar"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Shanghai", "superficie": "hard", "parole": ["shanghai"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Pechino", "superficie": "hard", "parole": ["beijing", "pechino", "china open"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Tokyo", "superficie": "hard", "parole": ["tokyo"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Vienna", "superficie": "hard", "parole": ["vienna", "wien"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Basilea", "superficie": "hard", "parole": ["basel", "basilea"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Rotterdam", "superficie": "hard", "parole": ["rotterdam"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Washington", "superficie": "hard", "parole": ["washington"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Atlanta", "superficie": "hard", "parole": ["atlanta"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Los Cabos", "superficie": "hard", "parole": ["los cabos"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Winston-Salem", "superficie": "hard", "parole": ["winston salem"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Acapulco", "superficie": "hard", "parole": ["acapulco"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Adelaide", "superficie": "hard", "parole": ["adelaide"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Brisbane", "superficie": "hard", "parole": ["brisbane"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Auckland", "superficie": "hard", "parole": ["auckland"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Hong Kong", "superficie": "hard", "parole": ["hong kong"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Chengdu", "superficie": "hard", "parole": ["chengdu"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Hangzhou", "superficie": "hard", "parole": ["hangzhou"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Wuhan", "superficie": "hard", "parole": ["wuhan"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Astana", "superficie": "hard", "parole": ["astana"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Anversa", "superficie": "hard", "parole": ["antwerp", "anversa"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Stoccolma", "superficie": "hard", "parole": ["stockholm", "stoccolma"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Metz", "superficie": "hard", "parole": ["metz"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Marsiglia", "superficie": "hard", "parole": ["marseille", "marsiglia"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Montpellier", "superficie": "hard", "parole": ["montpellier"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Dallas", "superficie": "hard", "parole": ["dallas"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Delray Beach", "superficie": "hard", "parole": ["delray beach"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Abu Dhabi", "superficie": "hard", "parole": ["abu dhabi"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "Seoul", "superficie": "hard", "parole": ["seoul"],
     "fonte": _FONTE_CALENDARIO},
    {"voce": "ATP Finals (Torino)", "superficie": "hard",
     "parole": ["atp finals", "nitto atp finals", "torino", "turin"],
     "fonte": _FONTE_CALENDARIO},
)


@dataclass(frozen=True)
class Superficie:
    """L'esito: la superficie, la fonte ('nome'|'mappa'|'default'), la voce
    che ha risposto e il nome della competizione letto."""

    superficie: str
    fonte: str
    voce: str
    competizione: Optional[str]

    @property
    def nome_it(self) -> str:
        return NOME_SUPERFICIE.get(self.superficie, self.superficie)

    def testo(self) -> str:
        """"terra (mappa: Roland Garros)" / "cemento (default: torneo sconosciuto)"."""
        return "%s (%s: %s)" % (self.nome_it, self.fonte, self.voce)

    def come_params(self) -> Dict[str, Any]:
        """Le chiavi che il runner scrive nei ``params`` del bot e della riga."""
        return {
            "surface": self.superficie,
            "surface_fonte": self.fonte,
            "surface_voce": self.voce,
            "surface_torneo": self.competizione,
            "surface_testo": self.testo(),
        }


def normalizza(nome: Optional[str]) -> str:
    """Minuscolo, senza accenti, punteggiatura -> spazio, spazi singoli."""
    s = unicodedata.normalize("NFKD", str(nome or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    # apostrofo dritto e tipografico (U+2019) tolti: "Queen's" -> "queens"
    s = s.replace("'", "").replace(chr(0x2019), "")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _contiene(testo: str, parola: str) -> bool:
    """Parola (o frase) INTERA dentro il testo normalizzato."""
    p = normalizza(parola)
    return bool(p) and re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])",
                                 testo) is not None


def risolvi(competizione: Optional[str]) -> Superficie:
    """La superficie della partita dal nome della competizione. MAI solleva:
    senza nome, o con un nome sconosciuto, risponde il default DICHIARATO."""
    comp = (str(competizione).strip() or None) if competizione is not None else None
    testo = normalizza(comp)
    if testo:
        for regola in PAROLE_SUPERFICIE:
            for parola in regola["parole"]:
                if _contiene(testo, parola):
                    return Superficie(regola["superficie"], FONTE_NOME,
                                      'il nome dice "%s"' % parola, comp)
        for voce in MAPPA_TORNEI:
            for parola in voce["parole"]:
                if _contiene(testo, parola):
                    return Superficie(voce["superficie"], FONTE_MAPPA, voce["voce"], comp)
    motivo = "torneo sconosciuto" if testo else "competizione non nota"
    return Superficie(SUPERFICIE_DEFAULT, FONTE_DEFAULT, motivo, comp)


def voci_per_superficie() -> Dict[str, List[str]]:
    """Le voci della mappa raggruppate per superficie (per il referto/i test)."""
    out: Dict[str, List[str]] = {}
    for v in MAPPA_TORNEI:
        out.setdefault(v["superficie"], []).append(v["voce"])
    return out
