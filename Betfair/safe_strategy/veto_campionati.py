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
    # @40.0-69.1 «Le coppe, qui il concetto e' diverso, in particolare per le
    # fasi finali e in generale comunque le partite con aspetto emotivo troppo
    # elevato non vanno bene [...] soprattutto in fase iniziale assolutamente
    # da evitare». LETTURA DICHIARATA: il veto e' su TUTTE le coppe, perche' dal
    # nome Betfair della competizione la fase (girone / finale) non si ricava,
    # e il video le mette fra le competizioni da evitare «in generale».
    VoceVeto(
        codice="coppe", nome="coppe",
        citazione=f"{_FONTE} @40.0-69.1",
        frasi=("cup", "cups", "coppa", "copa", "coupe", "pokal", "beker", "taca",
               "cupa", "kupa", "kupasi", "puchar", "supercup", "supercoppa",
               "supercopa", "supercoupe", "trophy", "shield",
               "champions league", "europa league", "conference league",
               "libertadores", "sudamericana"),
    ),
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
    # @102.0-116.5 «le partite con imprevedibilita' troppo elevata in generale,
    # ad esempio campionati un po' assurdi, quindi serie di boliviana, esempio
    # [...] evitiamo totalmente». Il video nomina SOLO la Bolivia (come esempio).
    VoceVeto(
        codice="bolivia", nome="campionato boliviano",
        citazione=f"{_FONTE} @102.0-116.5",
        frasi=("bolivia", "bolivian", "boliviana", "boliviano"),
    ),
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
