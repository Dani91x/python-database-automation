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
import { isErrorRow, isSettled } from './eventGroups';

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
    return { ...base, righe: out, totale, dalConto: true };
}

/** La corsia LIVE di uno sport dal conto: netto regolato oggi e numero di ordini regolati. */
export interface SportDalConto {
    pnl: number;
    ordini: number;
}

/**
 * 30/09 (W_G) - il LIVE per SPORT dal CONTO (`per_fonte`): calcio = Mike +
 * Omega + Safe calcio + Scalper; tennis = Safe tennis + bot tennis. Le voci
 * manuali (app/sito) e «altri bot» non hanno uno sport: restano fuori dalle
 * tessere (sono nella composizione). `null` = conto non letto.
 */
export function perSportDalConto(reale: PnlRealeOggi | null): Record<'calcio' | 'tennis', SportDalConto> | null {
    if (!reale) return null;
    const pf = reale.per_fonte;
    const somma = (fonti: (keyof PnlRealeOggi['per_fonte'])[]): SportDalConto => {
        let cent = 0;
        let ordini = 0;
        for (const f of fonti) { cent += Math.round(pf[f].netto * 100); ordini += pf[f].ordini; }
        return { pnl: cent / 100, ordini };
    };
    return {
        calcio: somma(['mike', 'omega', 'safe_calcio', 'scalper']),
        tennis: somma(['safe_tennis', 'bot_tennis']),
    };
}

/** Eta' in secondi della lettura del conto (letto_at); undefined = conto non letto; null = istante illeggibile. */
export function etaContoS(lettoAt: string | null | undefined, nowMs: number): number | null | undefined {
    if (lettoAt == null) return undefined;
    const ms = Date.parse(lettoAt);
    if (!Number.isFinite(ms)) return null;
    return Math.max(0, Math.round((nowMs - ms) / 1000));
}
