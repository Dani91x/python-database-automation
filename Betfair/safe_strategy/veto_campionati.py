"""veto_campionati.py - VETO DEI CAMPIONATI del corso per le tre varianti calcio.

ORDINE DELL'UTENTE 25/09 (Q4): «il corso dice chiaramente quali campionati
evitare; le SERIE B sono le serie B dei campionati elencati: Bundesliga NO,
2. Bundesliga NO».

E' una LISTA NEGATIVA: una partita la cui competizione ricade in una delle voci
qui sotto non si opera (BASE, RISULTATO ESATTO, PUNTA). Tutto il resto passa.
Le voci sono SOLO quelle che il video nomina; ogni voce porta la citazione
(file della trascrizione @ secondo) da cui viene. Niente aggiunte di chi scrive
il codice: i SINONIMI servono solo a riconoscere la stessa voce nei nomi con cui
Betfair chiama le competizioni (``listMarketCatalogue`` -> ``competition.name``,
es. "German Bundesliga 2", "Dutch Eerste Divisie", "Club Friendlies").

Trascrizione: ``Strategia S - Giuseppe Bentivegna/2. SELEZIONE PARTITE/
2. Competizioni da evitare.txt``.

REGOLE DEL CONFRONTO (identiche nel gemello TypeScript
``frontend/src/lib/vetoCampionati.ts``; un test le confronta byte per byte):

  * il nome si NORMALIZZA: minuscole, accenti tolti, tutto cio' che non e'
    lettera o cifra diventa spazio, spazi compressi. "2. Bundesliga" ->
    "2 bundesliga"; "Taca de Portugal" (con la cediglia) -> "taca de portugal";
  * una frase vieta se compare come PAROLE INTERE ("cup" vieta "FA Cup" ma non
    "Cupertino"); si confronta " frase " dentro " nome ";
  * una voce puo' avere frasi ESCLUSE: se una compare, la voce non scatta
    (la Bundesliga AUSTRIACA non e' quella del video);
  * le voci si provano IN ORDINE: la prima che scatta da' il motivo (cosi'
    "German Bundesliga 2" dice "Bundesliga 2", non "Bundesliga").

Il modulo e' PURO: nessun I/O, nessuna dipendenza da ``engine`` (che lo importa).
ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Tuple

_FONTE = "2. SELEZIONE PARTITE/2. Competizioni da evitare"


@dataclass(frozen=True)
class VoceVeto:
    codice: str                  # identificativo stabile
    nome: str                    # come compare nel motivo di scarto
    citazione: str               # file@secondo della trascrizione
    frasi: Tuple[str, ...]       # frasi GIA' normalizzate
    escluse: Tuple[str, ...] = ()


# L'ORDINE CONTA: la prima voce che scatta da' il motivo.
VOCI: Tuple[VoceVeto, ...] = (
    # @12.9 «primi su tutti calcio femminile e amichevoli [...] il concetto di
    # imprevedibilita' e' elevatissimo»
    VoceVeto(
        codice="femminile", nome="calcio femminile",
        citazione=f"{_FONTE} @12.9",
        frasi=("women", "womens", "woman", "ladies", "w", "femminile",
               "femenina", "femenino", "femenil", "feminino", "feminina",
               "feminine", "frauen", "damen", "dames", "vrouwen", "wsl", "nwsl",
               "damallsvenskan"),
    ),
    # @12.9 / @26.3 «stessa cosa vale per le amichevoli, non c'e' l'agonismo
    # [...] va assolutamente scartata proprio per sempre»
    VoceVeto(
        codice="amichevoli", nome="amichevoli",
        citazione=f"{_FONTE} @12.9-35.2",
        frasi=("friendly", "friendlies", "amichevole", "amichevoli", "amistoso",
               "amistosos", "testspiel", "testspiele", "freundschaftsspiel",
               "freundschaftsspiele"),
    ),
    # COPPE: NON sono una voce. Decisione dell'utente 25/09 (D5 punto 1): «NO,
    # e' troppo restrittivo cosi'! Sono da evitare SOLO LE FINALI». Il video
    # @40.0-69.1 «Le coppe [...] in particolare per le fasi finali [...]».
    # Le finali (di QUALUNQUE competizione) si riconoscono dal ROUND della
    # fixture (`is_round_finale`) o, in subordine, dal nome dell'evento
    # (`nome_indica_finale`), non dal nome della competizione.
    # @72.5-98.5 «Poi Bundesliga e Redivisie [...] hanno una propensione al gol
    # talmente elevata [...] anche queste evitiamo le, soprattutto le loro serie
    # B». Utente 25/09: «Bundesliga NO, 2. Bundesliga NO».
    # La serie B va PRIMA della serie A: il motivo deve dire quale delle due.
    VoceVeto(
        codice="bundesliga_2", nome="Bundesliga 2",
        citazione=f"{_FONTE} @90.0-98.5",
        frasi=("bundesliga 2", "2 bundesliga", "bundesliga ii", "zweite bundesliga",
               "2nd bundesliga"),
        # la Bundesliga AUSTRIACA non e' quella del video
        escluse=("austria", "austrian", "osterreich", "oesterreich"),
    ),
    VoceVeto(
        codice="bundesliga", nome="Bundesliga",
        citazione=f"{_FONTE} @72.5",
        frasi=("bundesliga", "1 bundesliga"),
        escluse=("austria", "austrian", "osterreich", "oesterreich"),
    ),
    VoceVeto(
        codice="eerste_divisie", nome="Eerste Divisie (serie B olandese)",
        citazione=f"{_FONTE} @90.0-98.5",
        frasi=("eerste divisie", "keuken kampioen divisie", "keuken kampioen"),
    ),
    VoceVeto(
        codice="eredivisie", nome="Eredivisie",
        citazione=f"{_FONTE} @72.5 (trascritto 'Redivisie')",
        frasi=("eredivisie",),
    ),
    # BOLIVIA: tolta. Decisione dell'utente 25/09 (D5 punto 2): «Bolivia: OK».
    # Restano SOLO le voci che il video nomina esplicitamente.
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalizza(nome: Optional[str]) -> str:
    """Minuscole, accenti tolti, separatori -> spazio. "" se non e' testo."""
    if not isinstance(nome, str):
        return ""
    s = unicodedata.normalize("NFKD", nome)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return _NON_ALNUM.sub(" ", s).strip()


def _contiene(testo: str, frase: str) -> bool:
    return f" {frase} " in f" {testo} "


def voce_vietata(competition: Optional[str]) -> Optional[VoceVeto]:
    """La PRIMA voce del corso in cui ricade ``competition``; None se lecita
    o se il nome non c'e' (il chiamante decide che cosa fare del dato assente)."""
    testo = normalizza(competition)
    if not testo:
        return None
    for voce in VOCI:
        if any(_contiene(testo, e) for e in voce.escluse):
            continue
        if any(_contiene(testo, f) for f in voce.frasi):
            return voce
    return None


def motivo(voce: VoceVeto) -> str:
    """Il motivo di scarto, dichiarato: «veto campionato: Bundesliga 2 (corso)»."""
    return f"veto campionato: {voce.nome} (corso)"


# ---------------------------------------------------------------------------
# D5 (decisioni dell'utente 25/09) - FEMMINILE DAI NOMI SQUADRA e FINALI
# ---------------------------------------------------------------------------
# Punto 4: «Femminile: OK anche dai nomi squadra». Le parole dell'utente:
# «(W)», «Women», «Femminile», «Ladies», «Frauen», «Femenino»; in piu' solo due
# varianti grammaticali dichiarate ("womens", "femenina"). Parola INTERA.
# "w" vale SOLO come ULTIMA parola (suffisso: "Arsenal W", "Arsenal (W)" ->
# "arsenal w"): cosi' "W Connection" (club maschile di Trinidad) non e' donne.
FRASI_SQUADRA_FEMMINILE: Tuple[str, ...] = (
    "women", "womens", "ladies", "femminile", "femenino", "femenina", "frauen",
)
SUFFISSO_SQUADRA_FEMMINILE = "w"


def squadra_femminile(nome: Optional[str]) -> bool:
    """True se il NOME DELLA SQUADRA dice che e' calcio femminile."""
    testo = normalizza(nome)
    if not testo:
        return False
    if testo.split()[-1] == SUFFISSO_SQUADRA_FEMMINILE:
        return True
    return any(_contiene(testo, f) for f in FRASI_SQUADRA_FEMMINILE)


# Punto 1: «Sono da evitare SOLO LE FINALI» (di qualunque competizione).
# FONTE (a): il round della fixture di API-Football (`matches.raw_json ->
# league -> round`), letto dallo scanner e pubblicato nella riga come
# `fixture_round`. Nomi VERI misurati sul DB il 25/09 (sonda
# `AUDIT_2026-09-25/sonde/d5_round_finali_sola_lettura.py`): "Final" (488),
# "Semi-finals" (620), "Quarter-finals" (372), "Clausura - Final",
# "Promotion Play-offs - Finals", "Grand Final", "Clausura - Gran Final",
# "Final - Relegation", "3rd Place Final", "Finals - 11", "Final Round - 3",
# "8th Finals", "1/2 Final", "Elimination Finals" ...
# REGOLA (il round si spezza sui " - "):
#   * FINALE se l'ULTIMO pezzo e' esattamente "Final"/"Finals"/"Grand Final"/
#     "Gran Final"/"Finale" ("Final", "Clausura - Final", "Promotion
#     Play-offs - Finals"), oppure se il PRIMO pezzo e' esattamente "Final" e
#     l'ultimo non e' un numero di giornata ("Final - Relegation");
#   * MAI finale: i turni prima ("Semi-finals", "Quarter-finals", "8th
#     Finals", "1/2 Final", "Elimination Finals"), le fasi a giornate
#     ("Final Round - 3", "Final Group - 1", "Finals - 11") e le finali per un
#     piazzamento ("3rd Place Final", "Placement matches - Final").
ROUND_FINALE: Tuple[str, ...] = ("final", "finals", "grand final", "gran final", "finale")
_PAROLE_PIAZZAMENTO: Tuple[str, ...] = ("place", "placement")
# separatori del round: " - ", tabulazione, trattini tipografici e il
# carattere di sostituzione che compare in qualche nome del DB
_SEP_ROUND = re.compile("\\s+-\\s+|\\t|\\s*[–—�]\\s*")


def is_round_finale(round_: Optional[str]) -> bool:
    """True se il round di API-Football e' una FINALE (vedi la regola sopra)."""
    if not isinstance(round_, str):
        return False
    tutto = normalizza(round_)
    if not tutto:
        return False
    if any(_contiene(tutto, p) for p in _PAROLE_PIAZZAMENTO):
        return False
    pezzi = [normalizza(x) for x in _SEP_ROUND.split(round_)]
    pezzi = [x for x in pezzi if x]
    if not pezzi:
        return False
    if pezzi[-1] in ROUND_FINALE:
        return True
    return len(pezzi) > 1 and pezzi[0] == "final" and not pezzi[-1].isdigit()


# FONTE (b), in subordine (SOLO se il round manca): il NOME dell'evento
# Betfair contiene «Final» come parola intera e non «Semi»/«Quarter».
_PAROLE_NON_FINALE: Tuple[str, ...] = (
    "semi", "semis", "semifinal", "semifinals", "quarter", "quarterfinal",
    "quarterfinals", "place", "placement",
)


def nome_indica_finale(nome: Optional[str]) -> bool:
    """True se il nome (evento Betfair) dice «Final», parola intera, e non
    e' una semifinale / un quarto / una finale per un piazzamento."""
    parole = normalizza(nome).split()
    if "final" not in parole:
        return False
    return not any(p in parole for p in _PAROLE_NON_FINALE)


MOTIVO_FINALE_ROUND = "veto finale: round «Final» (API-Football)"
MOTIVO_FINALE_NOME = "veto finale: «Final» nel nome evento (Betfair)"
MOTIVO_SQUADRA_FEMMINILE = "veto campionato: calcio femminile (nome squadra) (corso)"
