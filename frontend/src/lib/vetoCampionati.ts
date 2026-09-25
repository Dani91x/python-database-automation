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
    {
        codice: 'coppe',
        nome: 'coppe',
        citazione: '2. SELEZIONE PARTITE/2. Competizioni da evitare @40.0-69.1',
        frasi: ['cup', 'cups', 'coppa', 'copa', 'coupe', 'pokal', 'beker', 'taca',
            'cupa', 'kupa', 'kupasi', 'puchar', 'supercup', 'supercoppa',
            'supercopa', 'supercoupe', 'trophy', 'shield',
            'champions league', 'europa league', 'conference league',
            'libertadores', 'sudamericana'],
        escluse: [],
    },
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
    {
        codice: 'bolivia',
        nome: 'campionato boliviano',
        citazione: '2. SELEZIONE PARTITE/2. Competizioni da evitare @102.0-116.5',
        frasi: ['bolivia', 'bolivian', 'boliviana', 'boliviano'],
        escluse: [],
    },
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
