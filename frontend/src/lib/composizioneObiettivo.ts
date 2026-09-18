// ============================================================================
// composizioneObiettivo.ts — SCOMPOSIZIONE di ciò che erode l'obiettivo di
// giornata: Omega · Safe calcio · Safe tennis · Mike · bot tennis (Scalper /
// Pro / FLB / Swing) · Manuale. SOLO soldi veri (paper su riga separata, mai
// sommato: vedi `provaPaper`).
//
// Riusa `realizzatoGiornata` (`lib/controlRoom.ts`), la stessa funzione
// certificata che calcola già `realizzatoOggi`/`soldiGiornata` in
// `useControlRoom.ts`: qui non si inventa una seconda formula di somma, si
// applica la stessa a gruppi di righe diversi (per bot invece che per sport).
//
// INVARIANTE (falsificata nel test): la somma delle righe di composizione
// (Omega auto + Safe calcio auto + Safe tennis auto + Mike auto + bot tennis
// + manuale) è uguale al realizzato LIVE totale calcolato sulle stesse righe
// tutte insieme. Se questa somma diverge, la composizione mente.
// ============================================================================
import { realizzatoGiornata, type RigaRealizzato } from './controlRoom';

/**
 * Una riga sorgente, con le STESSE chiavi delle tabelle vere
 * (`omega_trades`/`safe_strategy_trades`/`mike_trades`): status, pnl, mode,
 * sport, origin. `origin` è opzionale: le righe che non lo portano (bot
 * tennis dedicati, che non hanno un percorso manuale) contano come 'auto'.
 *
 * ⚠️ `RigaRealizzato` (`lib/controlRoom.ts`) è FUORI PERIMETRO (di un altro
 * costruttore, F3): questo file NON lo tocca, lo ESTENDE solo a livello di
 * tipo (nessuna modifica al file altrui). `RigaComponente[]` resta
 * assegnabile ovunque serva un `RigaRealizzato[]` (è un suo sovrainsieme
 * strutturale), quindi `realizzatoGiornata` — certificata, invariata — si
 * riusa senza cast.
 */
export interface RigaComponente extends RigaRealizzato {
    origin?: string | null;
}

function eManuale(r: RigaComponente): boolean {
    return String(r.origin ?? '').toLowerCase() === 'manual';
}

function soloAuto(righe: readonly RigaComponente[]): RigaComponente[] {
    return righe.filter((r) => !eManuale(r));
}

function soloSport(righe: readonly RigaComponente[], sport: 'calcio' | 'tennis'): RigaComponente[] {
    return righe.filter((r) => String(r.sport ?? '').toLowerCase() === sport);
}

export interface RigaComposizione {
    chiave: 'omega' | 'safe_calcio' | 'safe_tennis' | 'mike' | 'bot_tennis' | 'manuale'
        | 'manuale_sito' | 'manuale_app';
    etichetta: string;
    /** P&L netto di oggi, SOLO soldi veri; null = nessuna riga (mostrare —, mai 0) */
    valore: number | null;
}

export interface ComposizioneObiettivo {
    righe: RigaComposizione[];
    /** somma di tutte le righe (per l'invariante/il controllo, non necessariamente mostrata) */
    totale: number | null;
    /** in prova (paper), su TUTTE le fonti insieme: mai sommato al totale sopra */
    provaPaper: number | null;
}

const ETICHETTE: Record<RigaComposizione['chiave'], string> = {
    omega: 'Omega',
    safe_calcio: 'Safe calcio',
    safe_tennis: 'Safe tennis',
    mike: 'Mike',
    bot_tennis: 'Bot tennis (Scalper · Pro · FLB · Swing)',
    manuale: 'Manuale (app + sito Betfair)',
    // 18/09 (raccordo) — DUE voci NUOVE, dal conto Betfair (`betfair_live_
    // account.manual_pnl_*`/`manual_app_pnl_*`, vedi `lib/manualeSitoBetfair.ts`):
    // diverse dalla riga "manuale" sopra, che e' `origin==='manual'` sulle
    // righe dei BOT (un cash-out/una gamba manuale dentro Omega/Safe/Mike).
    // Queste due sono scommesse FUORI dai bot: sul sito Betfair, e sul
    // terminale manuale (ladder) della nostra app.
    manuale_sito: 'Manuale · sito Betfair',
    manuale_app: 'Manuale · app',
};

function somma(a: number | null, b: number | null): number | null {
    if (a == null && b == null) return null;
    return Math.round(((a ?? 0) + (b ?? 0)) * 100) / 100;
}

/**
 * Compone la scomposizione dell'obiettivo dalle righe GIÀ lette (nessuna
 * lettura nuova: chi chiama passa gli stessi array di oggi già in memoria).
 *
 * `omega`/`mike`: solo calcio, un percorso solo (Omega e Mike non operano sul
 * tennis). `safe`: calcio + tennis mischiati (li separa qui per `sport`).
 * `tennisBot`: righe SINTETICHE, una per bot dedicato (già nette di
 * commissione, dalla RPC `get_tennis_bot_daily`): vedi
 * `useControlRoom.ts` per come vengono costruite.
 */
export function componiObiettivo(input: {
    omega: readonly RigaComponente[];
    safe: readonly RigaComponente[];
    mike: readonly RigaComponente[];
    tennisBot: readonly RigaComponente[];
    /**
     * 18/09 (raccordo) — le DUE voci manuali fuori dai bot (sito Betfair /
     * app), gia' tradotte in righe sintetiche da `useControlRoom.ts` (una
     * riga per bucket, dallo stesso `lib/manualeSitoBetfair.ts`). Opzionali:
     * finche' il chiamante non le passa (o la migrazione non e' applicata),
     * si comportano come array vuoti — comportamento IDENTICO a ieri.
     */
    manualeSito?: readonly RigaComponente[];
    manualeApp?: readonly RigaComponente[];
}): ComposizioneObiettivo {
    const omegaAuto = soloAuto(input.omega);
    const safeCalcioAuto = soloAuto(soloSport(input.safe, 'calcio'));
    const safeTennisAuto = soloAuto(soloSport(input.safe, 'tennis'));
    const mikeAuto = soloAuto(input.mike);
    const tennisBot = input.tennisBot; // nessun percorso manuale per i 4 bot dedicati
    const manuale = [...input.omega, ...input.safe, ...input.mike].filter(eManuale);
    const manualeSito = input.manualeSito ?? [];
    const manualeApp = input.manualeApp ?? [];

    const vOmega = realizzatoGiornata(omegaAuto).live;
    const vSafeCalcio = realizzatoGiornata(safeCalcioAuto).live;
    const vSafeTennis = realizzatoGiornata(safeTennisAuto).live;
    const vMike = realizzatoGiornata(mikeAuto).live;
    const vTennisBot = realizzatoGiornata(tennisBot).live;
    const vManuale = realizzatoGiornata(manuale).live;
    const vManualeSito = realizzatoGiornata(manualeSito).live;
    const vManualeApp = realizzatoGiornata(manualeApp).live;

    const righe: RigaComposizione[] = [
        { chiave: 'omega', etichetta: ETICHETTE.omega, valore: vOmega },
        { chiave: 'safe_calcio', etichetta: ETICHETTE.safe_calcio, valore: vSafeCalcio },
        { chiave: 'safe_tennis', etichetta: ETICHETTE.safe_tennis, valore: vSafeTennis },
        { chiave: 'mike', etichetta: ETICHETTE.mike, valore: vMike },
        { chiave: 'bot_tennis', etichetta: ETICHETTE.bot_tennis, valore: vTennisBot },
        { chiave: 'manuale', etichetta: ETICHETTE.manuale, valore: vManuale },
        { chiave: 'manuale_sito', etichetta: ETICHETTE.manuale_sito, valore: vManualeSito },
        { chiave: 'manuale_app', etichetta: ETICHETTE.manuale_app, valore: vManualeApp },
    ];

    const totale = righe.reduce<number | null>((acc, r) => somma(acc, r.valore), null);

    const tutteLeRighe = [
        ...input.omega, ...input.safe, ...input.mike, ...input.tennisBot,
        ...manualeSito, ...manualeApp,
    ];
    const provaPaper = realizzatoGiornata(tutteLeRighe).paper;

    return { righe, totale, provaPaper };
}
