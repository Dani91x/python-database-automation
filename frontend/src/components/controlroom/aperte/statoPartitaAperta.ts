// ============================================================================
// statoPartitaAperta.ts - P15 (30/09): lo STATO di una partita con posizione
// LIVE, in una parola, per la scheda "Posizioni aperte".
//
// Matematica GIA' certificata: `gambeDaOperazioni` + `cashOutPartita`
// (lib/cashOutPartita.ts) SENZA prezzi: servono solo le esposizioni per
// (mercato, selezione) - seVince/sePerde - che non dipendono dal mercato di
// adesso. Nessuna sottoscrizione, nessuna lettura.
//
//   A RISCHIO        il caso peggiore della partita e' < 0
//   IN VERDE         ogni esito guadagna (caso peggiore > 0, al centesimo)
//   PAREGGIATA       nessun esito perde e nessuno guadagna (caso peggiore = 0)
//                    (decisione dell'utente, 30/09 21:45: le due parole distinte)
//   DA REGOLARE      la partita e' chiusa (programma dello scanner) e la
//                    posizione non e' ancora regolata
//   NON CALCOLABILE  manca un dato della gamba (abbinato, prezzo medio,
//                    mercato/selezione, lato, modalita'): lo si dice
//
// CASO PEGGIORE per mercato (un solo esito vince): con le esposizioni
// (W_k, L_k) delle selezioni del mercato, il P&L se vince k e'
// W_k + somma_{j != k} L_j; se non vince nessuna delle selezioni toccate e'
// somma L_j (prudente: contato anche quando le selezioni coprono tutto il
// mercato). Sui mercati a DUE esiti `cashOutPartita` ha gia' fuso le gambe
// in una chiave sola: si riduce a min(W, L). La partita somma i mercati.
// ============================================================================
import {
    cashOutPartita, gambeDaOperazioni, r2, type OperazionePerCashOut, type PosizioneCashOut,
} from '@/lib/cashOutPartita';
import { fmtMoney } from '@/lib/format';

export type StatoPartitaAperta = 'A RISCHIO' | 'IN VERDE' | 'PAREGGIATA' | 'DA REGOLARE' | 'NON CALCOLABILE';

export interface EsitoStatoPartita {
    stato: StatoPartitaAperta;
    /** somma dei casi peggiori dei mercati (LIVE); null = non calcolabile */
    casoPeggiore: number | null;
    /** i numeri, per il title */
    dettaglio: string;
}

function peggioreMercato(pos: readonly PosizioneCashOut[]): number {
    const sommaL = pos.reduce((s, p) => s + p.sePerde, 0);
    let peggiore = sommaL;
    for (const p of pos) peggiore = Math.min(peggiore, p.seVince + (sommaL - p.sePerde));
    return r2(peggiore);
}

export function statoPartitaAperta(
    ops: readonly OperazionePerCashOut[],
    opz: { chiusa: boolean; dueEsiti?: (marketId: string) => boolean },
): EsitoStatoPartita {
    const gambe = gambeDaOperazioni(ops, { dueEsiti: opz.dueEsiti });
    const live = cashOutPartita(gambe, { prezzo: () => null, nowMs: 0 }).live;
    // senza prezzi ogni selezione da chiudere aggiunge UN "manca il prezzo": non
    // e' un dato mancante della posizione. Gli altri (all'inizio) si'.
    const soloPrezzo = live.gambe.filter((g) => g.stato === 'senza_prezzo' || g.stato === 'mercato_non_aperto').length;
    const datiMancanti = live.mancanti.slice(0, Math.max(0, live.mancanti.length - soloPrezzo));
    if (datiMancanti.length > 0) {
        return { stato: 'NON CALCOLABILE', casoPeggiore: null, dettaglio: datiMancanti.join('; ') };
    }
    if (live.nGambe === 0) {
        return {
            stato: 'NON CALCOLABILE', casoPeggiore: null,
            dettaglio: 'nessuna gamba LIVE abbinata: solo ordini sul book o righe senza abbinato',
        };
    }
    const perMercato = new Map<string, PosizioneCashOut[]>();
    for (const p of live.gambe) perMercato.set(p.marketId, [...(perMercato.get(p.marketId) ?? []), p]);
    let peggiore = 0;
    const righe: string[] = [];
    for (const [m, pos] of perMercato) {
        const w = peggioreMercato(pos);
        peggiore = r2(peggiore + w);
        // DESIGN_SYSTEM §1: anche nel title il denaro passa da fmtMoney (mai toFixed)
        righe.push(`mercato ${m}: ${pos.map((p) => `${p.selezione ?? `selezione ${p.selectionId}`} se vince ${fmtMoney(p.seVince, { signed: true })} / se perde ${fmtMoney(p.sePerde, { signed: true })}`).join(', ')} -> peggiore ${fmtMoney(w, { signed: true })}`);
    }
    const dettaglio = `caso peggiore ${fmtMoney(peggiore, { signed: true })}. ${righe.join('; ')}`;
    if (opz.chiusa) return { stato: 'DA REGOLARE', casoPeggiore: peggiore, dettaglio: `partita chiusa, in attesa di regolamento. ${dettaglio}` };
    return { stato: peggiore < 0 ? 'A RISCHIO' : peggiore > 0 ? 'IN VERDE' : 'PAREGGIATA', casoPeggiore: peggiore, dettaglio };
}
