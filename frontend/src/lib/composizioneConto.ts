// ============================================================================
// composizioneConto.ts - LA COMPOSIZIONE LIVE PER BOT DAL CONTO BETFAIR.
//
// 30/09 (blocco P7, progetto monitor veritiero §2.C punto 1-3): con il conto
// letto, il realizzato LIVE di ogni bot e' `pnl_reale_oggi.per_fonte[bot]`
// (attribuzione del backend per bet_id, poi customerOrderRef: qui NON si
// rifa'), piu' la parte ancora STIMATA delle righe del bot (chiusa dal bot,
// Betfair non ha ancora regolato, bet_id non contato dal conto).
//
// Prima la voce del bot era il reale delle SUE RIGHE lette dalla pagina, e la
// differenza col conto finiva in «Altro sul conto Betfair». Ma le RPC dei bot
// non portano tutte le righe regolate oggi (`get_mike_state`: solo righe
// piazzate oggi o aperte; `get_safe_state`: ultime 200): una posizione LIVE di
// ieri regolata oggi spariva dal suo bot e compariva in «Altro». Ora resta
// sotto il SUO bot, perche' il conto la attribuisce comunque.
//
// Il TOTALE non cambia (stesse fonti, spostate di voce): conto(omega+safe+
// mike) + altri_bot + stimati = righe(reale) + [altri_bot + differenza] +
// stimati. Il paper non passa di qui.
// Senza conto (`reale == null`) la composizione di prima resta INVARIATA.
// ============================================================================
import type {
    ComposizioneObiettivo, PnlRealeOggi, RigaComponente, RigaComposizione,
} from './composizioneObiettivo';
import { betIdChiusureAMano } from './composizioneObiettivo';
import { isErrorRow, isSettled } from './eventGroups';
import { isRigaUtente, type RigaPnl } from './fontePnl';

/** Da dove viene la cifra di una voce. */
export type FonteVoce = 'conto' | 'bot';

export interface RigaComposizioneConto extends RigaComposizione {
    /** di `valore`, la parte REGOLATA dal conto Betfair (per_fonte); null = nessuna */
    reale?: number | null;
    /** 'conto' = c'e' una parte letta dal conto; 'bot' = solo righe del bot */
    fonte?: FonteVoce | null;
}

export interface ComposizioneConto extends ComposizioneObiettivo {
    righe: RigaComposizioneConto[];
    /** true = le voci dei bot vengono dal conto (`per_fonte`) */
    dalConto: boolean;
    /**
     * 04/10 - le chiusure messe A MANO che il conto conta nella voce di un bot
     * (la sua posizione). Vuoto = nessuna, o runner di prima (voci per chi ha
     * piazzato: le chiusure a mano stanno in «Manuale · sito/app»).
     */
    chiusureAMano?: { chiave: RigaComposizione['chiave']; etichetta: string; netto: number; ordini: number }[];
}

function somma(a: number | null, b: number | null): number | null {
    if (a == null && b == null) return null;
    return Math.round(((a ?? 0) + (b ?? 0)) * 100) / 100;
}

function finito(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** La parte STIMATA delle righe LIVE regolate dal bot (stessa regola della barra). */
function stimatoDi(righe: readonly RigaComponente[]): number | null {
    let s: number | null = null;
    for (const r of righe) {
        if (String(r.mode ?? '').toLowerCase() !== 'live') continue;
        if (!isSettled(r.status) || isErrorRow(r.status)) continue;
        // riga senza reale/stimato dichiarati: tutta stimata (come `parti`)
        const v = r.pnlReale === undefined && r.pnlStimato === undefined ? finito(r.pnl) : finito(r.pnlStimato);
        if (v != null) s = somma(s, v);
    }
    return s;
}

const manuale = (r: RigaComponente) => String(r.origin ?? '').toLowerCase() === 'manual';
const diSport = (s: string) => (r: RigaComponente) => String(r.sport ?? '').toLowerCase() === s;

/**
 * Ricompone le voci dei bot (Omega, Safe calcio, Safe tennis, Mike, e la voce
 * «Manuale» delle righe dei bot) e «Altro sul conto Betfair» dal CONTO. Le
 * altre voci (scalper, bot tennis, manuale sito/app) vengono gia' dal conto e
 * restano come sono. `reale == null` = conto non letto: tutto invariato.
 */
export function composizioneDalConto(
    base: ComposizioneObiettivo,
    reale: PnlRealeOggi | null,
    righe: {
        omega: readonly RigaComponente[];
        safe: readonly RigaComponente[];
        mike: readonly RigaComponente[];
    },
): ComposizioneConto {
    if (!reale) {
        return {
            ...base,
            dalConto: false,
            righe: base.righe.map((r) => ({ ...r, fonte: r.valore == null ? null : 'bot' })),
        };
    }
    const pf = reale.per_fonte;
    const conto = (f: keyof PnlRealeOggi['per_fonte']) => (pf[f].ordini > 0 ? pf[f].netto : null);
    const auto = (xs: readonly RigaComponente[]) => xs.filter((r) => !manuale(r));
    const perBot: Partial<Record<RigaComposizione['chiave'], { reale: number | null; stimato: number | null }>> = {
        omega: { reale: conto('omega'), stimato: stimatoDi(auto(righe.omega)) },
        safe_calcio: { reale: conto('safe_calcio'), stimato: stimatoDi(auto(righe.safe).filter(diSport('calcio'))) },
        safe_tennis: { reale: conto('safe_tennis'), stimato: stimatoDi(auto(righe.safe).filter(diSport('tennis'))) },
        mike: { reale: conto('mike'), stimato: stimatoDi(auto(righe.mike)) },
        // i cicli aperti a mano dentro i bot: il conto li attribuisce al BOT
        // (per bet_id), qui resta solo la parte non ancora regolata
        manuale: { reale: null, stimato: stimatoDi([...righe.omega, ...righe.safe, ...righe.mike].filter(manuale)) },
        // solo gli ordini di altri bot: la «differenza» conto-righe non esiste piu'
        altro: { reale: conto('altri_bot'), stimato: null },
    };
    const out: RigaComposizioneConto[] = base.righe.map((r) => {
        const p = perBot[r.chiave];
        if (!p) {
            // voci gia' dal conto (scalper, bot tennis, manuale sito/app)
            return { ...r, fonte: r.valore == null ? null : 'conto' };
        }
        const valore = somma(p.reale, p.stimato);
        return {
            ...r,
            valore,
            reale: p.reale,
            stimato: p.stimato,
            fonte: p.reale != null ? 'conto' : valore != null ? 'bot' : null,
        };
    });
    const totale = out.reduce<number | null>((acc, r) => somma(acc, r.valore), null);
    // 04/10: quali voci dei bot comprendono chiusure messe a mano (si DICHIARA)
    const chiusureAMano: NonNullable<ComposizioneConto['chiusureAMano']> = [];
    if (reale.attribuzione === 'posizione') {
        for (const r of out) {
            const f = r.chiave as keyof PnlRealeOggi['per_fonte'];
            const ch = reale.chiusureAMano?.[f];
            if (ch && ch.ordini > 0) chiusureAMano.push({ chiave: r.chiave, etichetta: r.etichetta, netto: ch.netto, ordini: ch.ordini });
        }
    }
    return { ...base, righe: out, totale, dalConto: true, chiusureAMano };
}

/** La corsia LIVE di uno sport dal conto: netto regolato oggi e numero di ordini regolati. */
export interface SportDalConto {
    /** netto di commissione regolato oggi su questo sport */
    pnl: number;
    ordini: number;
    /**
     * 04/10 - la scomposizione (runner nuovo, `per_sport`): `pnl` = bot + aMano.
     * Assente = runner di prima: `pnl` sono i soli BOT e gli ordini a mano non
     * sono separati per sport (`aManoNonSeparato`).
     */
    bot?: number;
    aMano?: number;
    ordiniAMano?: number;
    /** di `bot`, le chiusure messe a mano sulle posizioni dei bot (contate col bot) */
    chiusureAMano?: number;
    ordiniChiusureAMano?: number;
    /** commissione del conto su questo sport (gia' tolta da `pnl`) */
    commissione?: number;
    /** runner di prima: netto degli ordini a mano di TUTTO il conto, fuori da `pnl`; null = nessuno */
    aManoNonSeparato?: number | null;
}

const centesimi = (v: number) => Math.round(v * 100) / 100;

/**
 * Il LIVE per SPORT dal CONTO. `null` = conto non letto.
 *
 * 04/10 (segnalazione dell'utente: «la scheda Calcio dice -10,75, ma non
 * abbiamo mai perso 10 euro») - con il runner nuovo la cifra e' TUTTO il conto
 * di quello sport (`per_sport`: bot + ordini a mano, dall'eventTypeId di ogni
 * ordine), scomposta in bot e a mano; prima erano le sole voci dei bot, con
 * una chiusura a mano di una posizione di Mike fuori dalla tessera.
 *
 * Runner di prima (nessun `per_sport`): calcio = Mike + Omega + Safe calcio +
 * Scalper, tennis = Safe tennis + bot tennis (30/09, W_G), e gli ordini a mano
 * si DICHIARANO fuori (`aManoNonSeparato`), mai taciuti.
 */
export function perSportDalConto(reale: PnlRealeOggi | null): Record<'calcio' | 'tennis', SportDalConto> | null {
    if (!reale) return null;
    if (reale.perSport) {
        const di = (s: 'calcio' | 'tennis'): SportDalConto => {
            const v = reale.perSport![s];
            return {
                pnl: centesimi(v.netto), ordini: v.ordini,
                bot: centesimi(v.bot.netto), aMano: centesimi(v.a_mano.netto), ordiniAMano: v.a_mano.ordini,
                chiusureAMano: centesimi(v.chiusure_a_mano.netto), ordiniChiusureAMano: v.chiusure_a_mano.ordini,
                commissione: centesimi(v.commissione),
            };
        };
        return { calcio: di('calcio'), tennis: di('tennis') };
    }
    const pf = reale.per_fonte;
    const somma = (fonti: (keyof PnlRealeOggi['per_fonte'])[]): { cent: number; ordini: number } => {
        let cent = 0;
        let ordini = 0;
        for (const f of fonti) { cent += Math.round(pf[f].netto * 100); ordini += pf[f].ordini; }
        return { cent, ordini };
    };
    const mano = somma(['manuale_sito', 'manuale_app']);
    const aManoNonSeparato = mano.ordini > 0 ? mano.cent / 100 : null;
    const sport = (fonti: (keyof PnlRealeOggi['per_fonte'])[]): SportDalConto => {
        const s = somma(fonti);
        return { pnl: s.cent / 100, ordini: s.ordini, aManoNonSeparato };
    };
    return {
        calcio: sport(['mike', 'omega', 'safe_calcio', 'scalper']),
        tennis: sport(['safe_tennis', 'bot_tennis']),
    };
}

/**
 * 04/10 - le righe di Mike che entrano nella barra/composizione: quelle del
 * BOT, piu' le righe «utente» (ordini dell'utente sulle sue partite) che il
 * CONTO conta nella posizione di Mike (`chiusure_a_mano`, per bet_id). Le
 * altre righe «utente» restano fuori: il conto le ha nel «Manuale». Una regola
 * sola col conto: lo stesso ordine mai due volte, mai zero volte.
 */
export function righeMikeDelConto<T>(trades: readonly T[], reale: PnlRealeOggi | null): T[] {
    const adottati = betIdChiusureAMano(reale);
    return trades.filter((t) => !isRigaUtente(t as unknown as RigaPnl)
        || adottati.has(String((t as { bet_id?: unknown }).bet_id ?? '')));
}

/** 04/10 - il conto di oggi per una vista filtrata per sport (o tutto il conto). */
export interface ContoVista {
    /** netto di commissione regolato oggi: = bot + aMano */
    netto: number;
    ordini: number;
    bot: number;
    aMano: number;
    ordiniAMano: number;
    commissione: number;
}

/**
 * 04/10 - il conto di oggi per la vista di uno sport (`null` = tutti gli
 * sport: tutto il conto, compreso cio' che non e' ne' calcio ne' tennis).
 * `null` = conto non letto o runner di prima (che non separa gli ordini a
 * mano per sport): la vista non inventa una scomposizione.
 */
export function contoPerVista(reale: PnlRealeOggi | null, sport: 'calcio' | 'tennis' | null): ContoVista | null {
    if (!reale?.perSport) return null;
    const parti = sport ? [reale.perSport[sport]] : [reale.perSport.calcio, reale.perSport.tennis, reale.perSport.altro];
    let netto = 0, ordini = 0, bot = 0, aMano = 0, ordiniAMano = 0, commissione = 0;
    for (const p of parti) {
        netto += Math.round(p.netto * 100); ordini += p.ordini;
        bot += Math.round(p.bot.netto * 100); aMano += Math.round(p.a_mano.netto * 100);
        ordiniAMano += p.a_mano.ordini; commissione += Math.round(p.commissione * 100);
    }
    return { netto: netto / 100, ordini, bot: bot / 100, aMano: aMano / 100, ordiniAMano, commissione: commissione / 100 };
}

/** Eta' in secondi della lettura del conto (letto_at); undefined = conto non letto; null = istante illeggibile. */
export function etaContoS(lettoAt: string | null | undefined, nowMs: number): number | null | undefined {
    if (lettoAt == null) return undefined;
    const ms = Date.parse(lettoAt);
    if (!Number.isFinite(ms)) return null;
    return Math.max(0, Math.round((nowMs - ms) / 1000));
}
