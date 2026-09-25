/**
 * VETO DEI CAMPIONATI del corso per le tre varianti calcio (BASE, RISULTATO
 * ESATTO, PUNTA) — ordine dell'utente 25/09 (Q4).
 *
 * GEMELLO ESATTO di `Betfair/safe_strategy/veto_campionati.py`: stesse voci,
 * stesse frasi, stesso ordine, stessa normalizzazione. Un test Python
 * (`test_safe_q1_q4_q5_2026_09_25.py`) legge QUESTO file e lo confronta con il
 * modulo del bot: se la lista cambia da un lato solo diventa rosso, perché la
 * pagina mostrerebbe un segnale che il bot non prende (o viceversa).
 *
 * Fonte: trascrizione «2. SELEZIONE PARTITE/2. Competizioni da evitare».
 * Ogni voce porta la citazione (file @ secondo). I sinonimi servono solo a
 * riconoscere la stessa voce nei nomi Betfair delle competizioni.
 */
export interface VoceVeto {
    codice: string;
    nome: string;
    citazione: string;
    /** frasi GIÀ normalizzate, confrontate a parole intere */
    frasi: string[];
    /** se una di queste compare la voce NON scatta (es. Bundesliga austriaca) */
    escluse: string[];
}

// L'ORDINE CONTA: la prima voce che scatta dà il motivo.
export const VOCI_VETO: VoceVeto[] = [
    {
        codice: 'femminile',
        nome: 'calcio femminile',
        citazione: '2. SELEZIONE PARTITE/2. Competizioni da evitare @12.9',
        frasi: ['women', 'womens', 'woman', 'ladies', 'w', 'femminile',
            'femenina', 'femenino', 'femenil', 'feminino', 'feminina',
            'feminine', 'frauen', 'damen', 'dames', 'vrouwen', 'wsl', 'nwsl',
            'damallsvenskan'],
        escluse: [],
    },
    {
        codice: 'amichevoli',
        nome: 'amichevoli',
        citazione: '2. SELEZIONE PARTITE/2. Competizioni da evitare @12.9-35.2',
        frasi: ['friendly', 'friendlies', 'amichevole', 'amichevoli', 'amistoso',
            'amistosos', 'testspiel', 'testspiele', 'freundschaftsspiel',
            'freundschaftsspiele'],
        escluse: [],
    },
    // COPPE: non sono una voce (utente 25/09, D5 punto 1: «da evitare SOLO
    // LE FINALI»): le finali si riconoscono con `isRoundFinale`/`nomeIndicaFinale`.
    {
        codice: 'bundesliga_2',
        nome: 'Bundesliga 2',
        citazione: '2. SELEZIONE PARTITE/2. Competizioni da evitare @90.0-98.5',
        frasi: ['bundesliga 2', '2 bundesliga', 'bundesliga ii', 'zweite bundesliga',
            '2nd bundesliga'],
        escluse: ['austria', 'austrian', 'osterreich', 'oesterreich'],
    },
    {
        codice: 'bundesliga',
        nome: 'Bundesliga',
        citazione: '2. SELEZIONE PARTITE/2. Competizioni da evitare @72.5',
        frasi: ['bundesliga', '1 bundesliga'],
        escluse: ['austria', 'austrian', 'osterreich', 'oesterreich'],
    },
    {
        codice: 'eerste_divisie',
        nome: 'Eerste Divisie (serie B olandese)',
        citazione: '2. SELEZIONE PARTITE/2. Competizioni da evitare @90.0-98.5',
        frasi: ['eerste divisie', 'keuken kampioen divisie', 'keuken kampioen'],
        escluse: [],
    },
    {
        codice: 'eredivisie',
        nome: 'Eredivisie',
        citazione: "2. SELEZIONE PARTITE/2. Competizioni da evitare @72.5 (trascritto 'Redivisie')",
        frasi: ['eredivisie'],
        escluse: [],
    },
    // BOLIVIA: tolta (utente 25/09, D5 punto 2: «Bolivia: OK»).
];

/** Minuscole, accenti tolti, separatori → spazio. '' se non è testo. */
export function normalizzaCompetizione(nome: string | null | undefined): string {
    if (typeof nome !== 'string') return '';
    return nome
        .normalize('NFKD')
        .replace(/[̀-ͯ]/g, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, ' ')
        .trim();
}

function contiene(testo: string, frase: string): boolean {
    return ` ${testo} `.includes(` ${frase} `);
}

/** La PRIMA voce del corso in cui ricade la competizione; null se lecita o
 *  se il nome non c'è (il chiamante decide che cosa fare del dato assente). */
export function voceVietata(competition: string | null | undefined): VoceVeto | null {
    const testo = normalizzaCompetizione(competition);
    if (!testo) return null;
    for (const voce of VOCI_VETO) {
        if (voce.escluse.some((e) => contiene(testo, e))) continue;
        if (voce.frasi.some((f) => contiene(testo, f))) return voce;
    }
    return null;
}

/** Il motivo di scarto dichiarato: «veto campionato: Bundesliga 2 (corso)». */
export function motivoVeto(voce: VoceVeto): string {
    return `veto campionato: ${voce.nome} (corso)`;
}

// ---------------------------------------------------------------------------
// D5 (decisioni dell'utente 25/09) — FEMMINILE DAI NOMI SQUADRA e FINALI.
// Gemelli ESATTI di `veto_campionati.py` (stesse parole, stesse regole): un
// test Python confronta le liste byte per byte.
// ---------------------------------------------------------------------------
/** Punto 4: parole INTERE nel nome di una squadra femminile; "w" vale solo
 *  come ULTIMA parola ("Arsenal W", "Arsenal (W)"; non "W Connection"). */
export const FRASI_SQUADRA_FEMMINILE: string[] = [
    'women', 'womens', 'ladies', 'femminile', 'femenino', 'femenina', 'frauen',
];
export const SUFFISSO_SQUADRA_FEMMINILE = 'w';

export function squadraFemminile(nome: string | null | undefined): boolean {
    const testo = normalizzaCompetizione(nome);
    if (!testo) return false;
    const parole = testo.split(' ');
    if (parole[parole.length - 1] === SUFFISSO_SQUADRA_FEMMINILE) return true;
    return FRASI_SQUADRA_FEMMINILE.some((f) => contiene(testo, f));
}

/** Punto 1: «da evitare SOLO LE FINALI». Round di API-Football della fixture:
 *  FINALE se l'ULTIMO pezzo (spezzato sui " - ") è esattamente Final/Finals/
 *  Grand Final/Gran Final/Finale, o se il PRIMO è esattamente "Final" e
 *  l'ultimo non è un numero di giornata. MAI: Semi-finals, Quarter-finals,
 *  8th Finals, 1/2 Final, Final Round - 3, Finals - 11, 3rd Place Final. */
export const ROUND_FINALE: string[] = ['final', 'finals', 'grand final', 'gran final', 'finale'];
const PAROLE_PIAZZAMENTO: string[] = ['place', 'placement'];
const SEP_ROUND = /\s+-\s+|\t|\s*[–—�]\s*/;

export function isRoundFinale(round: string | null | undefined): boolean {
    if (typeof round !== 'string') return false;
    const tutto = normalizzaCompetizione(round);
    if (!tutto) return false;
    if (PAROLE_PIAZZAMENTO.some((p) => contiene(tutto, p))) return false;
    const pezzi = round.split(SEP_ROUND).map((x) => normalizzaCompetizione(x)).filter((x) => x);
    if (pezzi.length === 0) return false;
    const ultimo = pezzi[pezzi.length - 1];
    if (ROUND_FINALE.includes(ultimo)) return true;
    return pezzi.length > 1 && pezzi[0] === 'final' && !/^[0-9]+$/.test(ultimo);
}

/** In subordine (solo se il round manca): «Final» parola intera nel nome
 *  evento Betfair, e non Semi/Quarter/piazzamento. */
const PAROLE_NON_FINALE: string[] = [
    'semi', 'semis', 'semifinal', 'semifinals', 'quarter', 'quarterfinal',
    'quarterfinals', 'place', 'placement',
];

export function nomeIndicaFinale(nome: string | null | undefined): boolean {
    const testo = normalizzaCompetizione(nome);
    const parole = testo ? testo.split(' ') : [];
    if (!parole.includes('final')) return false;
    return !PAROLE_NON_FINALE.some((p) => parole.includes(p));
}

export const MOTIVO_FINALE_ROUND = 'veto finale: round «Final» (API-Football)';
export const MOTIVO_FINALE_NOME = 'veto finale: «Final» nel nome evento (Betfair)';
export const MOTIVO_SQUADRA_FEMMINILE = 'veto campionato: calcio femminile (nome squadra) (corso)';
