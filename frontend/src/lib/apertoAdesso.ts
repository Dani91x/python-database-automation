// ============================================================================
// apertoAdesso.ts - «APERTO ADESSO (se chiudo tutto)» per il riquadro Obiettivo.
//
// 30/09 (W_G, P6, progetto monitor veritiero §2.C): la vecchia «in corso
// (stimato)» sommava per RIGA il «chiudi ora» delle sole aperture: una partita
// pareggiata contava come aperta e le righe senza prezzo sparivano in silenzio.
// Qui la cifra e' la SOMMA PER PARTITA del cash out LIVE, con la matematica
// certificata di `lib/cashOutPartita.ts` (esposizione per selezione, chiusure
// che nettano, commissione per mercato), ai prezzi dello SCANNER gia' in
// memoria. Una partita non calcolabile NON entra nella somma e si CONTA a
// parte: mai una somma spacciata per completa. Il paper non entra mai.
// Funzione pura.
// ============================================================================
import {
    cashOutPartita, gambeDaOperazioni, r2,
    type GambaViva, type OperazionePerCashOut,
} from './cashOutPartita';
import type { PrezzoScheda } from './schedaAlMs';

export interface ApertoPerBot {
    /** somma delle partite calcolabili del bot; null = nessuna calcolabile */
    netto: number | null;
    partite: number;
    nonCalcolabili: number;
}

export interface ApertoAdesso {
    /** somma dei cash out LIVE delle partite CALCOLABILI; null = nessuna */
    netto: number | null;
    /** partite con gambe LIVE abbinate e cifra calcolata */
    partite: number;
    /** partite con gambe LIVE ma cifra NON calcolabile (prezzo mancante, gamba non scomponibile...) */
    nonCalcolabili: number;
    /** per bot: le SOLE gambe di quel bot, partita per partita */
    perBot: Record<string, ApertoPerBot>;
    /**
     * review finale 30/09 (R2-2) - eta' (s) del prezzo PIU' VECCHIO usato dalle
     * partite calcolabili, all'istante del calcolo (`calcolatoAlMs`); null =
     * nessuna partita calcolabile o eta' ignota. La pagina la fa crescere col
     * suo orologio: se lo scanner si ferma, la cifra resta ma la sua eta' lo dice.
     */
    etaPrezziS: number | null;
    calcolatoAlMs: number;
}

export interface IngressoAperto {
    /** righe della scheda per partita (tutte: live e prova, di ogni bot) */
    operazioni: ReadonlyMap<string, readonly OperazionePerCashOut[]>;
    /** prezzo dello scanner di una selezione della partita; null = assente */
    prezzo: (eventId: string, marketId: string, selectionId: number) => PrezzoScheda | null;
    dueEsiti?: (eventId: string) => ((marketId: string) => boolean) | undefined;
    esitoDeciso?: (eventId: string) => ((marketId: string, selectionId: number) => boolean | null) | undefined;
    /** sport della partita: Safe ha una voce per sport (`safe_calcio` / `safe_tennis`) */
    sportDi?: (eventId: string) => 'calcio' | 'tennis' | null;
    nowMs: number;
}

/** Il cash out LIVE di un insieme di gambe di UNA partita: netto o null (non calcolabile), o 'vuoto'. */
function liveDi(
    gambe: readonly GambaViva[], eventId: string, i: IngressoAperto, eta?: { max: number | null },
): number | null | 'vuoto' {
    const r = cashOutPartita(gambe, {
        prezzo: (m, s) => i.prezzo(eventId, m, s),
        nowMs: i.nowMs,
        esitoDeciso: i.esitoDeciso?.(eventId),
    }).live;
    if (r.nGambe === 0 && r.mancanti.length === 0) return 'vuoto';
    if (eta && r.completo && r.netto != null && r.etaPrezziS != null) eta.max = Math.max(eta.max ?? 0, r.etaPrezziS);
    return r.completo && r.netto != null ? r.netto : null;
}

export function apertoAdesso(i: IngressoAperto): ApertoAdesso {
    const out: ApertoAdesso = { netto: null, partite: 0, nonCalcolabili: 0, perBot: {}, etaPrezziS: null, calcolatoAlMs: i.nowMs };
    let cent = 0;
    const eta = { max: null as number | null };
    for (const [eventId, ops] of i.operazioni) {
        if (!ops.some((o) => o.modalita === 'live')) continue;
        const gambe = gambeDaOperazioni(ops, { dueEsiti: i.dueEsiti?.(eventId) });
        const tot = liveDi(gambe, eventId, i, eta);
        if (tot === 'vuoto') continue;
        if (tot == null) out.nonCalcolabili += 1;
        else { out.partite += 1; cent += Math.round(tot * 100); }
        // per bot: le gambe di quel bot sulla partita
        const bots = [...new Set(gambe.filter((g) => g.modalita === 'live').map((g) => g.bot))];
        for (const b of bots) {
            const v = liveDi(gambe.filter((g) => g.bot === b), eventId, i);
            if (v === 'vuoto') continue;
            // Safe ha una voce per sport; sport ignoto = 'safe' (mai indovinato)
            const sp = b === 'safe' ? i.sportDi?.(eventId) ?? null : null;
            const k = b === 'safe' && sp ? `safe_${sp}` : b;
            const pb = out.perBot[k] ?? { netto: null, partite: 0, nonCalcolabili: 0 };
            if (v == null) pb.nonCalcolabili += 1;
            else { pb.partite += 1; pb.netto = r2((pb.netto ?? 0) + v); }
            out.perBot[k] = pb;
        }
    }
    out.netto = out.partite > 0 ? cent / 100 : null;
    out.etaPrezziS = eta.max;
    return out;
}
