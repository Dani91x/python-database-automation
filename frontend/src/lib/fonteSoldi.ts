// ============================================================================
// fonteSoldi.ts - 30/09, P1_MARCHIO_FONTE. Ogni cifra in euro a schermo porta
// l'etichetta della sua FONTE, con la stessa grammatica per tutti i bot:
//   conto  = letta dal conto Betfair (bot + app + sito)
//   bot    = attribuita al bot dalle sue righe o dal suo servizio
//   prova  = simulata (paper), mai sommata ai soldi veri
//   pagina = stima calcolata dalla pagina ai prezzi di adesso
// Puro, niente React. Nessun rosso: il rosso e' del LIVE e delle perdite.
// ============================================================================
import { fmtAge } from '@/lib/format';

export type FonteSoldi = 'conto' | 'bot' | 'prova' | 'pagina';

export const FONTE_SOLDI: Record<FonteSoldi, { label: string; title: string; cls: string }> = {
    conto: {
        label: 'CONTO BETFAIR',
        // review finale 30/09 (R2-M2/M3): il perimetro lo dice ogni cifra nel suo
        // dettaglio (tutto il conto, oppure la sola voce di un bot/sport); l'eta'
        // del P&L regolato e' quella dell'ULTIMO CAMBIO dei regolati (il servizio
        // ripubblica solo quando cambiano: `reconcile_worker.py`)
        title: 'cifra letta dal conto Betfair (il dettaglio dice se e\' tutto il conto o la sola voce di un bot); eta\' = ultimo cambio dei regolati letti dal conto',
        cls: 'bg-white/10 text-slate-100 border-white/25',
    },
    bot: {
        label: 'BOT',
        title: 'cifra attribuita al bot dalle sue righe o dal suo servizio: non comprende gli ordini fatti fuori dal bot',
        // T_P3 (30/09): indaco tenue, mai sky (BACK), rosso (LIVE) o verde
        cls: 'bg-indigo-400/10 text-indigo-200 border-indigo-400/30',
    },
    prova: {
        label: 'PROVA',
        title: 'simulato (paper): non sono soldi veri e non si somma mai ai soldi veri',
        // T_P3 (30/09): il tono del badge PAPER (`MODE_META.paper`) con bordo
        // TRATTEGGIATO: il tratteggio = simulato
        cls: 'bg-white/5 text-slate-300 border-white/15 border-dashed',
    },
    pagina: {
        label: 'STIMA',
        title: "stima calcolata dalla pagina ai prezzi di adesso: non è un dato di Betfair",
        cls: 'bg-amber-500/10 text-amber-300/80 border-amber-500/25',
    },
};

/** `undefined` = nessuna età (null); `null`/NaN/negativa = «età ignota»; altrimenti «<età> fa». */
export function testoEta(etaS: number | null | undefined): string | null {
    if (etaS === undefined) return null;
    if (etaS === null || !Number.isFinite(etaS) || etaS < 0) return 'età ignota';
    return `${fmtAge(etaS)} fa`;
}
