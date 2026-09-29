"""Costruttore della guida unica di un bot.

Legge SCHEMI_BOT/<bot>/schemi/ (file NN_nome.html prodotti da archify e file
NN_nome.schede.md scritti a mano) e scrive SCHEMI_BOT/<bot>/GUIDA_<BOT>.html:
una sola pagina, da aprire col doppio clic, che il trader legge dall'inizio
alla fine.

Uso:
    python costruisci_guida.py mike
    python costruisci_guida.py mike --versione "commit abc1234"

Solo libreria standard. Nessuno stato viene lasciato in giro: ogni lancio
rilegge tutto e riscrive il file di uscita da zero.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ----------------------------------------------------------------------
# Utilita' di base
# ----------------------------------------------------------------------

def leggi_testo(percorso: Path) -> str:
    """Legge un file in UTF-8, senza far esplodere lo script su un file vuoto."""
    return percorso.read_text(encoding="utf-8", errors="replace")


def indentazione(riga: str) -> int:
    """Numero di spazi iniziali di una riga (i file usano solo spazi, non tab)."""
    return len(riga) - len(riga.lstrip(" "))


# ----------------------------------------------------------------------
# Scoperta dei capitoli nella cartella schemi/
# ----------------------------------------------------------------------

NOME_STEM = re.compile(r"^(\d+[a-zA-Z]?)_([a-zA-Z0-9_]+)\.(html|schede\.md|workflow\.json|lifecycle\.json|dataflow\.json)$")


@dataclass
class Capitolo:
    stem: str  # es. "09_giro_del_servizio"
    numero: str  # es. "09", "11a"
    chiave_ordine: tuple  # per il sort, es. (9, "")
    percorso_html: Optional[Path] = None
    percorso_schede: Optional[Path] = None
    ha_json: bool = False
    titolo: str = ""
    ancora: str = ""


def chiave_ordinamento(numero: str) -> tuple:
    """Trasforma '05a' in (5, 'a') cosi' l'ordine numerico e' quello giusto."""
    m = re.match(r"^(\d+)([a-zA-Z]*)$", numero)
    if not m:
        return (999999, numero)
    return (int(m.group(1)), m.group(2).lower())


def scopri_capitoli(cartella_schemi: Path) -> list[Capitolo]:
    """Trova tutti i capitoli presenti nella cartella schemi/ del bot."""
    trovati: dict[str, Capitolo] = {}
    if not cartella_schemi.is_dir():
        return []
    for voce in sorted(cartella_schemi.iterdir()):
        if not voce.is_file():
            continue
        m = NOME_STEM.match(voce.name)
        if not m:
            continue
        stem = f"{m.group(1)}_{m.group(2)}"
        numero = m.group(1)
        tipo = m.group(3)
        cap = trovati.get(stem)
        if cap is None:
            cap = Capitolo(stem=stem, numero=numero, chiave_ordine=chiave_ordinamento(numero))
            trovati[stem] = cap
        if tipo == "html":
            cap.percorso_html = voce
        elif tipo == "schede.md":
            cap.percorso_schede = voce
        else:
            cap.ha_json = True
    elenco = list(trovati.values())
    elenco.sort(key=lambda c: c.chiave_ordine)
    for cap in elenco:
        cap.ancora = "cap-" + re.sub(r"[^a-zA-Z0-9_-]", "-", cap.stem)
    return elenco


# ----------------------------------------------------------------------
# Titolo del capitolo
# ----------------------------------------------------------------------

def pulisci_titolo_da_intestazione(riga_h1: str, bot: str) -> str:
    """Ricava un titolo leggibile dalla prima riga '# ...' delle schede."""
    t = riga_h1.lstrip("#").strip()
    t = re.sub(rf"^{re.escape(bot)}\s*-\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^(?:Capitolo|Schema)\s+\d+[a-zA-Z]?\s*[:\-]\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*\(schede\)\s*$", "", t, flags=re.IGNORECASE)
    return t.strip()


def pulisci_titolo_da_html(titolo_html: str, bot: str) -> str:
    t = html.unescape(titolo_html)
    t = re.sub(rf"^{re.escape(bot)}\s*-\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*Diagram\s*$", "", t, flags=re.IGNORECASE)
    return t.strip()


def titolo_da_stem(stem: str) -> str:
    t = re.sub(r"^\d+[a-zA-Z]?_", "", stem)
    t = t.replace("_", " ").strip()
    return t[:1].upper() + t[1:] if t else stem


def ricava_titolo(cap: Capitolo, bot: str) -> str:
    if cap.percorso_schede is not None:
        testo = leggi_testo(cap.percorso_schede)
        for riga in testo.splitlines():
            if riga.strip():
                if riga.strip().startswith("#"):
                    titolo = pulisci_titolo_da_intestazione(riga, bot)
                    if titolo:
                        return titolo
                break
    if cap.percorso_html is not None:
        testo = leggi_testo(cap.percorso_html)
        m = re.search(r"<title>(.*?)</title>", testo, re.S)
        if m:
            titolo = pulisci_titolo_da_html(m.group(1), bot)
            if titolo:
                return titolo
    return titolo_da_stem(cap.stem)


# ----------------------------------------------------------------------
# Convertitore markdown minimo (titoli, grassetti/corsivi, elenchi,
# tabelle, codice in linea, blocchi di codice, linee orizzontali)
# ----------------------------------------------------------------------

RE_OL = re.compile(r"^(\d+)\.\s+(.*)$")
RE_UL = re.compile(r"^[-*]\s+(.*)$")
RE_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def formatta_in_linea(testo: str) -> str:
    """Applica grassetto, corsivo e codice in linea a un pezzo di testo gia'
    passato per markdown_a_html a livello di blocco. Il testo qui e' ancora
    markdown puro (non HTML), va escapato per primo."""
    t = html.escape(testo, quote=False)
    # Codice in linea: estratto per primo e protetto con segnaposto, cosi'
    # grassetto/corsivo non toccano il contenuto del codice.
    frammenti: list[str] = []

    def protezione(m: "re.Match[str]") -> str:
        frammenti.append(f"<code>{m.group(1)}</code>")
        return f"\x00CODE{len(frammenti) - 1}\x00"

    t = re.sub(r"`([^`]+)`", protezione, t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\*([^*\n]+?)\*", r"<em>\1</em>", t)

    def ripristino(m: "re.Match[str]") -> str:
        return frammenti[int(m.group(1))]

    t = re.sub(r"\x00CODE(\d+)\x00", ripristino, t)
    return t


def divide_virgole_di_primo_livello(selettore: str) -> list[str]:
    return [p for p in selettore.split(",")]


def e_inizio_blocco(riga: str) -> bool:
    s = riga.strip()
    if not s:
        return False
    if s.startswith("#"):
        return True
    if s == "---":
        return True
    if s.startswith("```"):
        return True
    if s.startswith("|"):
        return True
    if indentazione(riga) == 0 and (RE_OL.match(s) or RE_UL.match(s)):
        return True
    return False


def rendi_lista(righe: list[str]) -> str:
    """Trasforma un blocco di righe (con eventuale indentazione annidata di
    un livello) in <ol>/<ul>. Le righe indentate senza segno diventano
    continuazione del testo del punto; le righe indentate CON segno
    diventano una lista annidata."""
    righe_utili = [r for r in righe if r.strip() != "" or True]
    # trova la prima riga non vuota per capire il tipo e l'indentazione base
    prima_idx = 0
    while prima_idx < len(righe_utili) and righe_utili[prima_idx].strip() == "":
        prima_idx += 1
    if prima_idx >= len(righe_utili):
        return ""
    base = righe_utili[prima_idx:]
    indent_base = indentazione(base[0])
    tipo_ordinato = bool(RE_OL.match(base[0].strip()))

    gruppi: list[list[str]] = []
    corrente: Optional[list[str]] = None
    for riga in base:
        s = riga.strip()
        if s == "":
            if corrente is not None:
                corrente.append(riga)
            continue
        ind = indentazione(riga)
        e_marcatore_qui = ind <= indent_base and (RE_OL.match(s) or RE_UL.match(s))
        if e_marcatore_qui:
            if corrente is not None:
                gruppi.append(corrente)
            corrente = [riga]
        else:
            if corrente is None:
                corrente = [riga]
            else:
                corrente.append(riga)
    if corrente is not None:
        gruppi.append(corrente)

    pezzi_html: list[str] = []
    for gruppo in gruppi:
        prima = gruppo[0].strip()
        m_ol = RE_OL.match(prima)
        m_ul = RE_UL.match(prima)
        # il testo grezzo dell'introduzione NON viene formattato subito: un
        # grassetto puo' aprirsi sulla prima riga e chiudersi su una riga
        # di continuazione (testo a capo senza segno), quindi si formatta
        # tutto insieme solo quando e' completo.
        intro_grezzo = m_ol.group(2) if m_ol else (m_ul.group(1) if m_ul else prima)
        sotto_righe = gruppo[1:]

        blocchi_html: list[str] = []
        buffer_testo: list[str] = []

        def scarica_buffer() -> None:
            nonlocal buffer_testo, intro_grezzo
            if not buffer_testo:
                return
            unito = " ".join(x.strip() for x in buffer_testo if x.strip() != "")
            buffer_testo = []
            if unito == "":
                return
            if not blocchi_html:
                intro_grezzo = intro_grezzo + " " + unito
            else:
                blocchi_html.append(f"<p>{formatta_in_linea(unito)}</p>")

        i = 0
        n = len(sotto_righe)
        while i < n:
            sr = sotto_righe[i]
            s2 = sr.strip()
            if s2 == "":
                i += 1
                continue
            if RE_OL.match(s2) or RE_UL.match(s2):
                scarica_buffer()
                indent_annidato = indentazione(sr)
                righe_annidate: list[str] = []
                while i < n:
                    sr2 = sotto_righe[i]
                    s3 = sr2.strip()
                    if s3 == "":
                        i += 1
                        continue
                    if indentazione(sr2) < indent_annidato:
                        break
                    righe_annidate.append(sr2)
                    i += 1
                blocchi_html.append(rendi_lista(righe_annidate))
            else:
                buffer_testo.append(sr)
                i += 1
        scarica_buffer()

        li_interno = f"<p>{formatta_in_linea(intro_grezzo)}</p>" + "".join(blocchi_html)
        pezzi_html.append(f"<li>{li_interno}</li>")

    tag = "ol" if tipo_ordinato else "ul"
    return f"<{tag}>" + "".join(pezzi_html) + f"</{tag}>"


def rendi_tabella(righe: list[str]) -> str:
    righe_pulite = [r.strip() for r in righe if r.strip() != ""]
    if len(righe_pulite) < 2:
        return ""

    def celle(riga: str) -> list[str]:
        r = riga.strip()
        if r.startswith("|"):
            r = r[1:]
        if r.endswith("|"):
            r = r[:-1]
        return [c.strip() for c in r.split("|")]

    intestazione = celle(righe_pulite[0])
    # la riga 1 e' il separatore (---|---), le altre sono dati
    corpo = [celle(r) for r in righe_pulite[2:]]

    out = ['<div class="table-wrap"><table><thead><tr>']
    for c in intestazione:
        out.append(f"<th>{formatta_in_linea(c)}</th>")
    out.append("</tr></thead><tbody>")
    for riga_dati in corpo:
        out.append("<tr>")
        for c in riga_dati:
            out.append(f"<td>{formatta_in_linea(c)}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


@dataclass
class BloccoMD:
    tipo: str  # 'heading' | 'p' | 'list' | 'table' | 'hr' | 'code' | 'tecnico'
    html: str = ""
    livello: int = 0
    testo_grezzo: str = ""


def analizza_blocchi(righe: list[str]) -> list[BloccoMD]:
    """Analizza un elenco di righe (gia' senza la prima intestazione H1 del
    file) in una sequenza di blocchi tipizzati."""
    blocchi: list[BloccoMD] = []
    pos = 0
    n = len(righe)
    while pos < n:
        riga = righe[pos]
        if riga.strip() == "":
            pos += 1
            continue

        s = riga.strip()

        # blocco di codice
        if s.startswith("```"):
            pos += 1
            corpo: list[str] = []
            while pos < n and not righe[pos].strip().startswith("```"):
                corpo.append(righe[pos])
                pos += 1
            if pos < n:
                pos += 1  # salta la riga di chiusura
            testo = html.escape("\n".join(corpo))
            blocchi.append(BloccoMD(tipo="code", html=f"<pre><code>{testo}</code></pre>"))
            continue

        # titolo
        m_h = RE_HEADING.match(s)
        if m_h:
            livello = len(m_h.group(1))
            testo = m_h.group(2).strip()
            blocchi.append(BloccoMD(tipo="heading", livello=livello, testo_grezzo=testo,
                                     html=formatta_in_linea(testo)))
            pos += 1
            continue

        # linea orizzontale
        if s == "---":
            blocchi.append(BloccoMD(tipo="hr", html="<hr/>"))
            pos += 1
            continue

        # tabella
        if s.startswith("|"):
            righe_tabella: list[str] = []
            while pos < n and righe[pos].strip().startswith("|"):
                righe_tabella.append(righe[pos])
                pos += 1
            blocchi.append(BloccoMD(tipo="table", html=rendi_tabella(righe_tabella)))
            continue

        # lista (ordinata o puntata) a indentazione zero
        if indentazione(riga) == 0 and (RE_OL.match(s) or RE_UL.match(s)):
            blocco_righe: list[str] = []
            while pos < n:
                r = righe[pos]
                if r.strip() == "":
                    # guarda avanti: la lista continua solo se dopo il vuoto
                    # c'e' ancora indentazione o un altro punto della lista
                    avanti = pos + 1
                    while avanti < n and righe[avanti].strip() == "":
                        avanti += 1
                    if avanti < n:
                        r_avanti = righe[avanti]
                        s_avanti = r_avanti.strip()
                        if indentazione(r_avanti) > 0 or RE_OL.match(s_avanti) or RE_UL.match(s_avanti):
                            pos += 1
                            blocco_righe.append(r)
                            continue
                    break
                s_r = r.strip()
                if indentazione(r) == 0 and not (RE_OL.match(s_r) or RE_UL.match(s_r)):
                    break
                blocco_righe.append(r)
                pos += 1
            testo_txt = "\n".join(blocco_righe).strip()
            blocchi.append(BloccoMD(tipo="list", html=rendi_lista(blocco_righe), testo_grezzo=testo_txt))
            continue

        # paragrafo semplice: consuma righe consecutive fino al prossimo blocco
        para_righe = [riga]
        pos += 1
        while pos < n:
            r = righe[pos]
            if r.strip() == "" or e_inizio_blocco(r):
                break
            para_righe.append(r)
            pos += 1
        testo_para = " ".join(x.strip() for x in para_righe)
        blocchi.append(BloccoMD(tipo="p", testo_grezzo=testo_para, html=formatta_in_linea(testo_para)))

    # unisci la coppia "**Per il tecnico**" (paragrafo bold da solo) + blocco
    # successivo in un unico blocco 'tecnico'
    fusi: list[BloccoMD] = []
    i = 0
    while i < len(blocchi):
        b = blocchi[i]
        if b.tipo == "p" and b.testo_grezzo.strip() == "**Per il tecnico**":
            interno = "<p>Per il tecnico</p>"
            if i + 1 < len(blocchi) and blocchi[i + 1].tipo in ("list", "p", "code", "table"):
                interno += blocchi[i + 1].html
                i += 1
            fusi.append(BloccoMD(tipo="tecnico", html=f'<div class="per-il-tecnico">{interno}</div>'))
        else:
            fusi.append(b)
        i += 1
    return fusi


def dividi_in_sezioni_h2(righe_senza_h1: list[str]) -> list[tuple[Optional[str], list[str]]]:
    """Divide il contenuto (senza la prima riga H1) in sezioni per ogni '## '."""
    sezioni: list[tuple[Optional[str], list[str]]] = []
    titolo_corrente: Optional[str] = None
    corpo_corrente: list[str] = []
    for riga in righe_senza_h1:
        m = re.match(r"^##\s+(.*)$", riga)
        if m:
            if titolo_corrente is not None or corpo_corrente:
                sezioni.append((titolo_corrente, corpo_corrente))
            titolo_corrente = m.group(1).strip()
            corpo_corrente = []
        else:
            corpo_corrente.append(riga)
    if titolo_corrente is not None or corpo_corrente:
        sezioni.append((titolo_corrente, corpo_corrente))
    return sezioni


@dataclass
class PuntoDaDecidere:
    html_punto: str
    ancora: str
    capitolo_titolo: str
    capitolo_ancora: str


def rendi_schede_md(testo: str, ancora_capitolo: str, capitolo_titolo: str) -> tuple[str, list[PuntoDaDecidere]]:
    """Converte l'intero contenuto di un file .schede.md in HTML e raccoglie
    i punti della sezione "Punti da decidere" per l'indice finale."""
    righe = testo.replace("\r\n", "\n").split("\n")
    # salta la prima intestazione H1 (serve solo per il titolo del capitolo)
    idx = 0
    while idx < len(righe) and righe[idx].strip() == "":
        idx += 1
    if idx < len(righe) and righe[idx].strip().startswith("# "):
        idx += 1
    resto = righe[idx:]

    sezioni = dividi_in_sezioni_h2(resto)
    pezzi: list[str] = []
    punti: list[PuntoDaDecidere] = []

    for titolo_sez, corpo in sezioni:
        blocchi = analizza_blocchi(corpo)
        if titolo_sez is None:
            # testo introduttivo prima del primo "## "
            for b in blocchi:
                if b.tipo == "tecnico":
                    pezzi.append(b.html)
                elif b.tipo == "heading":
                    pezzi.append(f"<h4>{b.html}</h4>")
                else:
                    pezzi.append(b.html)
            continue

        titolo_basso = titolo_sez.lower()
        contenuto_html = "".join(b.html for b in blocchi)

        if titolo_basso.startswith("punti da decidere"):
            pezzi.append(
                f'<div class="punti-decidere-box" id="{ancora_capitolo}-decidere">'
                f'<h3>{formatta_in_linea(titolo_sez)}</h3>{contenuto_html}</div>'
            )
            # raccoglie i singoli punti dal primo blocco lista trovato
            for b in blocchi:
                if b.tipo == "list":
                    voci = re.findall(r"<li>(.*?)</li>", b.html, re.S)
                    for k, voce in enumerate(voci, start=1):
                        anc = f"{ancora_capitolo}-decidere-{k}"
                        punti.append(PuntoDaDecidere(
                            html_punto=voce, ancora=anc,
                            capitolo_titolo=capitolo_titolo, capitolo_ancora=ancora_capitolo,
                        ))
                    break
        elif titolo_basso.startswith("punti non chiariti"):
            pezzi.append(
                f'<div class="punti-non-chiariti-box">'
                f'<h3>{formatta_in_linea(titolo_sez)}</h3>{contenuto_html}</div>'
            )
        elif titolo_basso.startswith("frecce"):
            pezzi.append(f'<div class="frecce-box"><h3>{formatta_in_linea(titolo_sez)}</h3>{contenuto_html}</div>')
        else:
            pezzi.append(f'<div class="riquadro"><h3>{formatta_in_linea(titolo_sez)}</h3>{contenuto_html}</div>')

    return "".join(pezzi), punti


# ----------------------------------------------------------------------
# Estrazione dello schema (SVG + CSS) dal file archify
# ----------------------------------------------------------------------

TAG_SVG_SICURI = {
    "svg", "text", "tspan", "rect", "circle", "ellipse", "line", "polyline",
    "polygon", "path", "marker", "pattern", "defs", "g", "clippath",
    "lineargradient", "radialgradient", "stop", "use", "symbol", "mask",
    "filter", "desc", "title", "switch", "foreignobject",
}


def classi_usate_nello_svg(svg_markup: str) -> set:
    classi = set()
    for m in re.finditer(r'class="([^"]*)"', svg_markup):
        for tok in m.group(1).split():
            classi.add(tok)
    return classi


def togli_commenti_css(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def regole_di_primo_livello(css: str) -> list[tuple[str, str]]:
    """Elenca le regole CSS di primo livello (selettore, corpo), saltando
    interamente i blocchi @media/@keyframes/@supports/@font-face."""
    css = togli_commenti_css(css)
    n = len(css)
    i = 0
    regole: list[tuple[str, str]] = []
    while i < n:
        while i < n and css[i].isspace():
            i += 1
        if i >= n:
            break
        if css[i] == "@":
            inizio_graffa = css.find("{", i)
            if inizio_graffa == -1:
                break
            profondita = 1
            j = inizio_graffa + 1
            while j < n and profondita > 0:
                if css[j] == "{":
                    profondita += 1
                elif css[j] == "}":
                    profondita -= 1
                j += 1
            i = j
            continue
        inizio_graffa = css.find("{", i)
        if inizio_graffa == -1:
            break
        selettore = css[i:inizio_graffa]
        profondita = 1
        j = inizio_graffa + 1
        while j < n and profondita > 0:
            if css[j] == "{":
                profondita += 1
            elif css[j] == "}":
                profondita -= 1
            j += 1
        corpo = css[inizio_graffa + 1: j - 1]
        regole.append((selettore.strip(), corpo.strip()))
        i = j
    return regole


def selettore_bare_semplice(sp: str) -> bool:
    for c in (" ", ">", "+", "~", ".", "#", "["):
        if c in sp:
            return False
    return True


def tag_di_base(sp: str) -> str:
    return sp.split(":", 1)[0].strip().lower()


def selettore_rilevante(sp: str, classi_usate: set) -> bool:
    sp = sp.strip()
    if not sp:
        return False
    if sp == ":root" or sp.startswith("[data-theme"):
        return False
    if selettore_bare_semplice(sp):
        tag = tag_di_base(sp)
        if tag == "*":
            return False
        return tag in TAG_SVG_SICURI
    for cls in classi_usate:
        if re.search(r"\." + re.escape(cls) + r"(?![\w-])", sp):
            return True
    if ".diagram-container" in sp:
        return True
    if re.match(r"^svg\b", sp):
        return True
    for attr in ("[data-node-id]", "[data-edge-from]", "[data-edge-to]", "[data-detail"):
        if attr in sp:
            return True
    return False


def scala_selettore(sp: str, classe_scope: str) -> str:
    sostituito = re.sub(r"^\.diagram-container\b", "." + classe_scope, sp)
    if sostituito != sp:
        return sostituito
    return "." + classe_scope + " " + sp


def estrai_variabili(blocco: str) -> list[tuple[str, str]]:
    return re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", blocco)


@dataclass
class SchemaEstratto:
    modo: str  # 'inline' oppure 'iframe'
    html: str


def estrai_schema(percorso_html: Path, stem: str) -> SchemaEstratto:
    """Prova a estrarre lo svg del disegno con le sue regole di colore.
    In caso di qualunque problema, ripiega sull'iframe (il file originale
    e' comunque completo e navigabile)."""
    nome_scheda_relativo = f"schemi/{percorso_html.name}"
    try:
        testo = leggi_testo(percorso_html)

        inizio_svg = testo.find("<svg ")
        if inizio_svg == -1:
            raise ValueError("nessun tag <svg> trovato")
        fine_svg = testo.rfind("</svg>")
        if fine_svg == -1 or fine_svg < inizio_svg:
            raise ValueError("tag </svg> non trovato")
        fine_svg += len("</svg>")
        svg_markup = testo[inizio_svg:fine_svg]
        if "viewBox" not in svg_markup:
            raise ValueError("viewBox mancante nell'svg")

        # rende l'svg responsivo: larghezza piena, altezza automatica
        m_tag_apertura = re.match(r"<svg\b[^>]*>", svg_markup)
        if not m_tag_apertura:
            raise ValueError("tag di apertura svg non analizzabile")
        tag_originale = m_tag_apertura.group(0)
        tag_pulito = re.sub(r'\s+(width|height|style)="[^"]*"', "", tag_originale)
        tag_pulito = tag_pulito[:-1] + ' style="display:block;width:100%;height:auto;" preserveAspectRatio="xMidYMid meet">'
        svg_markup = tag_pulito + svg_markup[len(tag_originale):]

        # trova il blocco di stile grande (quello con le variabili :root)
        stili = re.findall(r"<style([^>]*)>(.*?)</style>", testo, re.S)
        blocco_css = ""
        for attrs, contenuto in stili:
            if "archify-fonts" in attrs:
                continue
            if ":root" in contenuto:
                blocco_css = contenuto
                break
        if not blocco_css:
            raise ValueError("blocco di stile principale non trovato")

        m_dark = re.search(r':root\s*,\s*\[data-theme="dark"\]\s*\{([^}]*)\}', blocco_css)
        m_light = re.search(r'\[data-theme="light"\]\s*\{([^}]*)\}', blocco_css)
        if not m_dark or not m_light:
            raise ValueError("variabili di tema non trovate")
        variabili_scure = estrai_variabili(m_dark.group(1))
        variabili_chiare = estrai_variabili(m_light.group(1))
        if not variabili_scure or not variabili_chiare:
            raise ValueError("variabili di tema vuote")

        resto_css = blocco_css[:m_dark.start()] + blocco_css[m_dark.end():]
        resto_css = resto_css.replace(m_light.group(0), "")

        classe_scope = "archify-" + re.sub(r"[^a-zA-Z0-9_-]", "-", stem)
        classi_usate = classi_usate_nello_svg(svg_markup)

        pezzi_css: list[str] = []
        pezzi_css.append(f".{classe_scope} {{")
        for nome, valore in variabili_chiare:
            pezzi_css.append(f"  {nome}: {valore};")
        pezzi_css.append("}")
        pezzi_css.append("@media (prefers-color-scheme: dark) {")
        pezzi_css.append(f"  .{classe_scope} {{")
        for nome, valore in variabili_scure:
            pezzi_css.append(f"    {nome}: {valore};")
        pezzi_css.append("  }")
        pezzi_css.append("}")

        for selettore, corpo in regole_di_primo_livello(resto_css):
            if not corpo.strip():
                continue
            parti = [p.strip() for p in selettore.split(",")]
            parti_valide = [p for p in parti if selettore_rilevante(p, classi_usate)]
            if not parti_valide:
                continue
            parti_scalate = [scala_selettore(p, classe_scope) for p in parti_valide]
            pezzi_css.append(",\n".join(parti_scalate) + " {\n" + corpo + "\n}")

        css_finale = "\n".join(pezzi_css)
        if "</style" in css_finale.lower() or "</script" in css_finale.lower():
            raise ValueError("contenuto CSS sospetto, non incorporato")

        blocco_finale = (
            f'<style>{css_finale}</style>'
            f'<div class="diagram-embed {classe_scope}">{svg_markup}</div>'
            f'<p class="apri-schema"><a href="{nome_scheda_relativo}" target="_blank" rel="noopener">'
            f'Apri lo schema navigabile a tutto schermo</a></p>'
        )
        return SchemaEstratto(modo="inline", html=blocco_finale)
    except Exception:
        blocco_finale = (
            f'<div class="diagram-embed diagram-embed-iframe">'
            f'<iframe src="{nome_scheda_relativo}" loading="lazy" '
            f'title="Schema navigabile"></iframe></div>'
            f'<p class="apri-schema"><a href="{nome_scheda_relativo}" target="_blank" rel="noopener">'
            f'Apri lo schema navigabile a tutto schermo</a></p>'
        )
        return SchemaEstratto(modo="iframe", html=blocco_finale)


# ----------------------------------------------------------------------
# Foglio di stile della guida
# ----------------------------------------------------------------------

CSS_GUIDA = """
:root {
  --bg: #f7f7f5;
  --bg-alt: #ffffff;
  --text: #1c1c1c;
  --text-muted: #55565c;
  --border: #d9d9d3;
  --accent: #14532d;
  --accent-soft: #e7f3ea;
  --warn-border: #b45309;
  --warn-bg: #fef3e2;
  --code-bg: #eeeeea;
  --link: #0b5fa5;
  --sidebar-bg: #efefe9;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14161a;
    --bg-alt: #1b1e24;
    --text: #e7e7e3;
    --text-muted: #a7a8ad;
    --border: #33363d;
    --accent: #6fd39a;
    --accent-soft: #1c2c22;
    --warn-border: #d99a4e;
    --warn-bg: #2c2413;
    --code-bg: #23262c;
    --link: #7cb8ec;
    --sidebar-bg: #191b20;
  }
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--bg);
  color: var(--text);
}
body {
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 17px;
  line-height: 1.65;
}
a { color: var(--link); }
.layout { display: flex; align-items: flex-start; min-height: 100vh; }
.sidebar {
  position: sticky;
  top: 0;
  width: 300px;
  flex-shrink: 0;
  height: 100vh;
  overflow-y: auto;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  padding: 1.25rem 1rem;
}
.sidebar h2 { font-size: 15px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-top: 0; }
.sidebar ul { list-style: none; margin: 0; padding: 0; }
.sidebar li { margin: 0.15rem 0; }
.sidebar a {
  display: block;
  padding: 0.35rem 0.5rem;
  border-radius: 6px;
  text-decoration: none;
  color: var(--text);
  font-size: 15px;
}
.sidebar a:hover { background: var(--accent-soft); }
.sidebar a.attivo { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.sidebar .indice-sep { margin: 0.9rem 0 0.3rem; border: none; border-top: 1px solid var(--border); }
.content {
  flex: 1;
  min-width: 0;
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem 2rem 6rem;
}
.doc-header h1 { margin-bottom: 0.2rem; }
.doc-header .meta { color: var(--text-muted); font-size: 15px; }
.status-box, .chapter {
  background: var(--bg-alt);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.25rem 1.5rem;
  margin: 1.5rem 0;
}
.status-box ul { margin: 0.3rem 0; }
.status-box .stato-ok { color: var(--accent); }
.status-box .stato-mancante { color: var(--warn-border); }
.chapter h2 { margin-top: 0; }
.riquadro, .punti-decidere-box, .punti-non-chiariti-box, .frecce-box {
  margin: 1.25rem 0;
  padding: 1rem 1.1rem;
  border-radius: 8px;
  background: var(--bg-alt);
}
.riquadro { border-left: 4px solid var(--border); }
.riquadro h3, .frecce-box h3, .punti-non-chiariti-box h3 { margin-top: 0; }
.punti-decidere-box {
  border: 2px solid var(--warn-border);
  background: var(--warn-bg);
}
.punti-decidere-box h3 { margin-top: 0; color: var(--warn-border); }
.per-il-tecnico {
  margin-top: 0.8rem;
  padding: 0.6rem 0.8rem;
  border-left: 3px solid var(--border);
  color: var(--text-muted);
  font-size: 13.5px;
}
.per-il-tecnico p:first-child { margin: 0 0 0.3rem; text-transform: uppercase; letter-spacing: 0.04em; font-size: 12px; }
table { border-collapse: collapse; width: 100%; font-size: 15.5px; }
.table-wrap { overflow-x: auto; margin: 0.8rem 0; border: 1px solid var(--border); border-radius: 6px; }
th, td { border: 1px solid var(--border); padding: 0.4rem 0.6rem; text-align: left; vertical-align: top; }
th { background: var(--accent-soft); }
code { background: var(--code-bg); padding: 0.1rem 0.3rem; border-radius: 4px; font-size: 0.9em; }
pre { background: var(--code-bg); padding: 0.8rem; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
hr { border: none; border-top: 1px solid var(--border); margin: 1.2rem 0; }
.diagram-embed {
  margin: 1rem 0;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem;
  overflow: auto;
  background: var(--bg-alt);
}
.diagram-embed svg { display: block; width: 100%; height: auto; }
.diagram-embed-iframe { padding: 0; height: 900px; }
.diagram-embed-iframe iframe { width: 100%; height: 900px; border: none; display: block; border-radius: 9px; }
.apri-schema { margin: 0.4rem 0 0; font-size: 15px; }
.in-preparazione {
  color: var(--text-muted);
  font-style: italic;
  padding: 0.8rem;
  border: 1px dashed var(--border);
  border-radius: 8px;
}
.punti-finali li { margin-bottom: 1rem; }
.punti-finali .torna { font-size: 14px; margin-left: 0.4rem; }
@media (max-width: 900px) {
  .layout { display: block; }
  .sidebar {
    position: static;
    width: auto;
    height: auto;
    max-height: 45vh;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .content { padding: 1.25rem 1rem 4rem; max-width: 100%; }
}
@media print {
  .sidebar { display: none; }
  .content { max-width: 100%; padding: 0; }
  .chapter { break-before: page; border: none; }
  .diagram-embed-iframe { display: none; }
}
"""

JS_GUIDA = """
(function () {
  var link_capitoli = Array.prototype.slice.call(document.querySelectorAll('a[data-capitolo-link]'));
  var sezioni = link_capitoli
    .map(function (a) { return document.getElementById(a.getAttribute('data-capitolo-link')); })
    .filter(Boolean);
  if (!sezioni.length || !('IntersectionObserver' in window)) { return; }
  var osservatore = new IntersectionObserver(function (voci) {
    voci.forEach(function (voce) {
      if (voce.isIntersecting) {
        var id = voce.target.id;
        link_capitoli.forEach(function (a) {
          a.classList.toggle('attivo', a.getAttribute('data-capitolo-link') === id);
        });
      }
    });
  }, { rootMargin: '-20% 0px -70% 0px' });
  sezioni.forEach(function (s) { osservatore.observe(s); });
})();
"""


# ----------------------------------------------------------------------
# Composizione della pagina finale
# ----------------------------------------------------------------------

def costruisci_pagina(bot: str, versione: Optional[str], capitoli: list[Capitolo]) -> str:
    bot_titolo = bot.strip()
    bot_titolo = bot_titolo[:1].upper() + bot_titolo[1:] if bot_titolo else bot_titolo
    adesso = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    tutti_i_punti: list[PuntoDaDecidere] = []
    corpi_capitoli: list[str] = []
    completi: list[Capitolo] = []
    incompleti: list[Capitolo] = []

    for cap in capitoli:
        cap.titolo = ricava_titolo(cap, bot)
        ha_html = cap.percorso_html is not None
        ha_schede = cap.percorso_schede is not None
        if ha_html and ha_schede:
            completi.append(cap)
        else:
            incompleti.append(cap)

        pezzi: list[str] = [f'<section class="chapter" id="{cap.ancora}">']
        pezzi.append(f"<h2>Capitolo {cap.numero} - {html.escape(cap.titolo)}</h2>")

        if ha_html:
            schema = estrai_schema(cap.percorso_html, cap.stem)
            pezzi.append(schema.html)
        else:
            pezzi.append('<p class="in-preparazione">Schema in preparazione.</p>')

        if ha_schede:
            testo_schede = leggi_testo(cap.percorso_schede)
            html_schede, punti = rendi_schede_md(testo_schede, cap.ancora, cap.titolo)
            pezzi.append(html_schede)
            tutti_i_punti.extend(punti)
        else:
            pezzi.append('<p class="in-preparazione">Schede in preparazione.</p>')

        pezzi.append("</section>")
        corpi_capitoli.append("".join(pezzi))

    # riquadro "Stato della guida"
    stato_righe: list[str] = ['<section class="status-box" id="stato">', "<h2>Stato della guida</h2>"]
    if completi:
        stato_righe.append('<p class="stato-ok">Capitoli completi (schema e schede):</p><ul>')
        for c in completi:
            stato_righe.append(f'<li><a href="#{c.ancora}">Capitolo {c.numero} - {html.escape(c.titolo)}</a></li>')
        stato_righe.append("</ul>")
    if incompleti:
        stato_righe.append('<p class="stato-mancante">Capitoli incompleti:</p><ul>')
        for c in incompleti:
            manca = []
            if c.percorso_html is None:
                manca.append("schema")
            if c.percorso_schede is None:
                manca.append("schede")
            stato_righe.append(
                f'<li><a href="#{c.ancora}">Capitolo {c.numero} - {html.escape(c.titolo)}</a> '
                f'(manca: {", ".join(manca)})</li>'
            )
        stato_righe.append("</ul>")
    if not completi and not incompleti:
        stato_righe.append("<p>Nessun capitolo trovato nella cartella schemi/.</p>")
    stato_righe.append("</section>")

    # indice laterale
    indice_righe: list[str] = ['<nav class="sidebar"><h2>Indice</h2><ul>']
    indice_righe.append('<li><a href="#stato">Stato della guida</a></li>')
    indice_righe.append('<hr class="indice-sep"/>')
    for cap in capitoli:
        indice_righe.append(
            f'<li><a href="#{cap.ancora}" data-capitolo-link="{cap.ancora}">'
            f'Capitolo {cap.numero} - {html.escape(cap.titolo)}</a></li>'
        )
    indice_righe.append('<hr class="indice-sep"/>')
    indice_righe.append('<li><a href="#tutti-punti-decidere">Tutti i punti da decidere</a></li>')
    indice_righe.append("</ul></nav>")

    # capitolo finale con tutti i punti da decidere
    sezione_punti: list[str] = [
        '<section class="chapter punti-decidere-box" id="tutti-punti-decidere">',
        "<h2>Tutti i punti da decidere</h2>",
    ]
    if tutti_i_punti:
        sezione_punti.append('<ol class="punti-finali">')
        for p in tutti_i_punti:
            sezione_punti.append(
                f"<li>{p.html_punto} "
                f'<a class="torna" href="#{p.capitolo_ancora}">'
                f"(torna al capitolo: {html.escape(p.capitolo_titolo)})</a></li>"
            )
        sezione_punti.append("</ol>")
    else:
        sezione_punti.append("<p>Nessun punto da decidere raccolto finora.</p>")
    sezione_punti.append("</section>")

    riga_versione = (
        f"Riferita al codice: {html.escape(versione)}." if versione
        else "Versione del codice non specificata."
    )

    pagina = f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Guida di {html.escape(bot_titolo)}</title>
<style>{CSS_GUIDA}</style>
</head>
<body>
<div class="layout">
{"".join(indice_righe)}
<main class="content">
<header class="doc-header">
<h1>Guida di {html.escape(bot_titolo)}</h1>
<p class="meta">Costruita il {adesso}. {riga_versione}</p>
</header>
{"".join(stato_righe)}
{"".join(corpi_capitoli)}
{"".join(sezione_punti)}
</main>
</div>
<script>{JS_GUIDA}</script>
</body>
</html>
"""
    return pagina


# ----------------------------------------------------------------------
# Punto d'ingresso
# ----------------------------------------------------------------------

def principale() -> int:
    parser = argparse.ArgumentParser(description="Costruisce la guida unica di un bot da SCHEMI_BOT/<bot>/schemi/.")
    parser.add_argument("bot", help="nome della cartella del bot, es. mike")
    parser.add_argument("--versione", default=None, help="testo libero che descrive la versione del codice")
    args = parser.parse_args()

    cartella_script = Path(__file__).resolve().parent
    cartella_bot = cartella_script / args.bot
    cartella_schemi = cartella_bot / "schemi"

    if not cartella_schemi.is_dir():
        print(f"Cartella non trovata: {cartella_schemi}", file=sys.stderr)
        return 1

    capitoli = scopri_capitoli(cartella_schemi)
    pagina = costruisci_pagina(args.bot, args.versione, capitoli)

    percorso_uscita = cartella_bot / f"GUIDA_{args.bot.upper()}.html"
    percorso_uscita.write_text(pagina, encoding="utf-8")

    print(f"Capitoli trovati: {len(capitoli)}")
    print(f"Guida scritta in: {percorso_uscita}")
    return 0


if __name__ == "__main__":
    sys.exit(principale())
