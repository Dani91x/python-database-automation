// ============================================================================
// valutaProposta.ts - LA PROPOSTA AL PREZZO DI ADESSO (24/09/2026).
//
// Ordine dell'utente: «Tutti i valori e i calcoli devono aggiornarsi al
// cambiare del prezzo. La scheda delle proposte deve segnalarmi se
// l'opportunita', in base ai calcoli e al prezzo attuale, c'e' ancora o no:
// io decido se approvare o scartare.»
//
// PORTA TypeScript di `Betfair/safe_strategy/proposte_opportunita.py:
// valuta_al_prezzo` (Python). Stessi criteri del motore che ha generato la
// proposta, letti da `payload.criteri` (scritti dal servizio coi parametri
// EFFETTIVI del motore): mai soglie ricopiate qui. Le due funzioni sono legate
// dal file d'oro `valutaProposta.golden.json` (rigenerato da
// `python -m Betfair.safe_strategy.tools.genera_oro_valuta_proposta --scrivi`):
// il test Python e quello TS lo rileggono, una modifica a una sola delle due
// fa diventare rosso un test.
//
// Cosa NON si ricalcola al tick (dichiarato): la P del modello (resta quella
// dell'ultima valutazione del servizio) e la confidenza (dipende dal contesto
// del modello). Quando non reggono piu' lo dice il servizio
// (`payload.valutazione.causa === 'modello'`).
// ============================================================================
import { tickUp } from './matching';

export interface MotivoValutazione {
    codice: string;
    valore: number | null;
    soglia: number | null;
    testo?: string;
}

export interface ValutazioneAlPrezzo {
    prezzo: number | null;
    p_implicita: number | null;
    edge: number | null;
    ev: number | null;
    ev_eur: number | null;
    liability: number | null;
    valida: boolean;
    motivi: MotivoValutazione[];
}

export type CriteriProposta = Partial<Record<
    'min_edge' | 'min_size' | 'max_lay_price' | 'min_back_price' | 'commission'
    | 'min_prob_back' | 'max_prob_lay' | 'opps_min_edge' | 'max_liability_per_trade'
    | 'stake', number>>;

/** Numero VERO (finito, non booleano, non stringa): come `_numero` in Python. */
function numero(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** `round(x, n)` di Python per i valori che la scheda mostra. */
function arrotonda(x: number, cifre: number): number {
    const f = 10 ** cifre;
    return Math.round(x * f) / f;
}

function motivo(codice: string, valore: number | null, soglia: number | null): MotivoValutazione {
    return {
        codice,
        valore: valore == null ? null : arrotonda(valore, 6),
        soglia: soglia == null ? null : arrotonda(soglia, 6),
    };
}

/** La proposta regge ancora AL PREZZO DI ADESSO? Pura. Stessa firma e stesse
 *  uscite di `valuta_al_prezzo` (Python). */
export function valutaAlPrezzo(args: {
    side: unknown; prezzo: unknown; abbinabile: unknown; p_model: unknown;
    criteri: CriteriProposta | null | undefined;
}): ValutazioneAlPrezzo {
    const c = (args.criteri && typeof args.criteri === 'object') ? args.criteri : {};
    const lato = String(args.side ?? '').toLowerCase();
    const q = numero(args.prezzo);
    const pm = numero(args.p_model);
    const size = numero(args.abbinabile);
    const stake = numero(c.stake) ?? 0;
    const out: ValutazioneAlPrezzo = {
        prezzo: q, p_implicita: null, edge: null, ev: null, ev_eur: null,
        liability: null, valida: false, motivi: [],
    };
    const m = out.motivi;
    if (lato !== 'back' && lato !== 'lay') {
        m.push(motivo('lato_non_valido', null, null));
        return out;
    }
    if (q == null || q <= 1) {
        m.push(motivo('prezzo_assente', q, null));
        return out;
    }
    if (pm == null || pm < 0 || pm > 1) {
        m.push(motivo('probabilita_assente', pm, null));
        return out;
    }
    out.p_implicita = arrotonda(1 / q, 6);
    const minSize = numero(c.min_size);
    if (minSize != null && (size ?? 0) < minSize) {
        m.push(motivo('abbinabile_sotto_minimo', size, minSize));
    }
    let edge: number;
    if (lato === 'back') {
        const mpb = numero(c.min_prob_back);
        if (mpb != null && pm < mpb) m.push(motivo('probabilita_sotto_minimo', pm, mpb));
        const mbp = numero(c.min_back_price);
        if (mbp != null && q < mbp) m.push(motivo('quota_sotto_minimo', q, mbp));
        edge = pm - 1 / q;
    } else {
        const mpl = numero(c.max_prob_lay);
        if (mpl != null && pm > mpl) m.push(motivo('probabilita_sopra_massimo', pm, mpl));
        const mlp = numero(c.max_lay_price);
        if (mlp != null && q > mlp) m.push(motivo('quota_sopra_massimo', q, mlp));
        edge = 1 / q - pm;
    }
    out.edge = arrotonda(edge, 6);
    const minEdge = numero(c.min_edge);
    if (minEdge != null && edge < minEdge) m.push(motivo('edge_sotto_minimo', edge, minEdge));
    const ome = numero(c.opps_min_edge);
    if (ome != null && ome !== 0 && edge < ome) {
        m.push(motivo('edge_sotto_minimo_servizio', edge, ome));
    }
    const comm = numero(c.commission) ?? 0.05;
    let ev: number;
    let liability: number;
    if (lato === 'back') {
        ev = pm * (q - 1) * (1 - comm) - (1 - pm);
        liability = arrotonda(stake, 2);
    } else {
        ev = (1 - pm) * (1 - comm) - pm * (q - 1);
        liability = arrotonda(stake * (q - 1), 2);
    }
    out.ev = arrotonda(ev, 6);
    out.ev_eur = arrotonda(ev * stake, 4);
    out.liability = liability;
    if (ev <= 0) m.push(motivo('ev_non_positivo', ev, 0));
    const cap = numero(c.max_liability_per_trade);
    if (cap != null && cap > 0 && liability > cap) {
        m.push(motivo('responsabilita_oltre_tetto', liability, cap));
    }
    out.valida = m.length === 0;
    return out;
}

/** I motivi in italiano, per l'avvertimento «fuori criterio» della scheda. */
const TESTO_MOTIVO: Record<string, string> = {
    lato_non_valido: 'lato dell’ordine non valido',
    prezzo_assente: 'prezzo assente',
    probabilita_assente: 'probabilità del modello assente',
    abbinabile_sotto_minimo: 'abbinabile sotto il minimo',
    probabilita_sotto_minimo: 'probabilità del modello sotto il minimo',
    probabilita_sopra_massimo: 'probabilità del modello sopra il massimo',
    quota_sotto_minimo: 'quota sotto il minimo',
    quota_sopra_massimo: 'quota sopra il massimo',
    edge_sotto_minimo: 'vantaggio sotto la soglia del modello',
    edge_sotto_minimo_servizio: 'vantaggio sotto la soglia del servizio',
    ev_non_positivo: 'valore atteso non positivo',
    responsabilita_oltre_tetto: 'responsabilità oltre il tetto per operazione',
    non_piu_proposta_dal_modello: 'il modello non la propone più',
};

export function testoMotivo(m: MotivoValutazione): string {
    const base = m.testo || TESTO_MOTIVO[m.codice] || m.codice.replace(/_/g, ' ');
    if (m.valore == null || m.soglia == null) return base;
    return `${base}: ${m.valore} contro soglia ${m.soglia}`;
}

// ============================================================================
// D7 (25/09/2026) - LA BANDA DELLA STRATEGIA: al clic l'ordine parte A MERCATO
// (il miglior prezzo di adesso) solo se sta dentro la banda; fuori banda il
// servizio non piazza e la scheda lo dice PRIMA del clic.
//
// PORTA di `proposte_opportunita.banda_della_strategia` / `in_banda` (Python):
// la banda sono i tick della scala Betfair dove i criteri DI PREZZO di
// `valutaAlPrezzo` reggono (quota min/max, edge del motore e del servizio, EV
// positivo, tetto di responsabilita'); abbinabile e soglie di probabilita' NON
// sono banda. Legate dal file d'oro `bandaStrategia.golden.json`
// (`python -m Betfair.safe_strategy.tools.genera_oro_banda_strategia --scrivi`).
// ============================================================================
export const CODICI_DI_PREZZO: readonly string[] = [
    'quota_sotto_minimo', 'quota_sopra_massimo', 'edge_sotto_minimo',
    'edge_sotto_minimo_servizio', 'ev_non_positivo', 'responsabilita_oltre_tetto',
];

export interface BandaStrategia {
    min: number | null;
    max: number | null;
    vuota: boolean;
}

/** La scala Betfair 1.01 .. 1000 (una volta sola). */
let SCALA: number[] | null = null;
function scalaBetfair(): number[] {
    if (SCALA) return SCALA;
    const out: number[] = [];
    let p = 1.01;
    for (;;) {
        out.push(p);
        if (p >= 1000) break;
        const n = tickUp(p);
        if (!(n > p)) break;
        p = n;
    }
    SCALA = out;
    return out;
}

function bandaValutabile(side: unknown, pModel: unknown, criteri: unknown): boolean {
    const lato = String(side ?? '').toLowerCase();
    if (lato !== 'back' && lato !== 'lay') return false;
    if (criteri == null || typeof criteri !== 'object' || Array.isArray(criteri)) return false;
    const pm = numero(pModel);
    return pm != null && pm >= 0 && pm <= 1;
}

/** Il prezzo sta dentro la banda della strategia? Prezzo non valido = no. */
export function inBanda(args: { side: unknown; prezzo: unknown; p_model: unknown;
    criteri: CriteriProposta | null | undefined }): boolean {
    const q = numero(args.prezzo);
    if (q == null || q <= 1 || !bandaValutabile(args.side, args.p_model, args.criteri)) return false;
    const v = valutaAlPrezzo({ side: String(args.side).toLowerCase(), prezzo: q, abbinabile: null,
        p_model: args.p_model, criteri: args.criteri });
    return v.p_implicita != null && !v.motivi.some((m) => CODICI_DI_PREZZO.includes(m.codice));
}

/** La banda che la strategia ammette per QUESTA proposta; null = non si puo'
 *  dire (niente criteri o P del modello): mai un limite inventato. */
export function bandaDellaStrategia(args: { side: unknown; p_model: unknown;
    criteri: CriteriProposta | null | undefined }): BandaStrategia | null {
    if (!bandaValutabile(args.side, args.p_model, args.criteri)) return null;
    const dentro = scalaBetfair().filter((q) => inBanda({ ...args, prezzo: q }));
    return {
        min: dentro.length ? dentro[0] : null,
        max: dentro.length ? dentro[dentro.length - 1] : null,
        vuota: dentro.length === 0,
    };
}

/** «1.05-1000» (come il messaggio del servizio); `fmt` = come scrivere le
 *  quote (la scheda passa `fmtOdds`, cosi' la frase parla una lingua sola). */
export function testoBanda(b: BandaStrategia | null,
    fmt: (v: number) => string = (v) => String(v)): string {
    if (!b || b.vuota || b.min == null || b.max == null) {
        return 'vuota (nessun prezzo la soddisfa con la P del modello di adesso)';
    }
    return `${fmt(b.min)}-${fmt(b.max)}`;
}
