// ============================================================================
// useCashOutPartita.ts - 30/09 (P12a): il cash out della partita con i prezzi
// AL MS. Collega le righe della scheda (`OperazionePartita`, di TUTTI i bot)
// alla matematica pura di `lib/cashOutPartita.ts`.
//
// Prezzi: `usePrezziAlMs` (UNA sottoscrizione per mercato, staccate allo
// smontaggio), per le sole selezioni che vanno chiuse; dove il canale non
// porta il mercato, il prezzo dello scanner gia' in pagina (`chiusura.alMs.
// scanner` della riga), DICHIARATO come tale. Nessuna sottoscrizione per una
// partita senza gambe abbinate: la lista delle selezioni e' vuota.
// ============================================================================
import { useEffect, useMemo, useRef } from 'react';
import { usePrezziAlMs, type SelezioneAlMs, type SorgenteLadder } from './usePrezzoAlMs';
import {
    cashOutPartita, gambeDaOperazioni,
    type CashOutPartitaRisultato, type GambaViva, type OperazionePerCashOut,
} from '@/lib/cashOutPartita';
import { ripiegoScanner, type DatiChiusuraAlMs } from '@/lib/chiusuraAlMs';
import type { PrezzoScheda } from '@/lib/schedaAlMs';

export interface ArgsCashOutPartita {
    /** le righe della partita (tutte: live, prova, di ogni bot) */
    operazioni: readonly (OperazionePerCashOut & {
        chiusura: { alMs?: DatiChiusuraAlMs | undefined } | null;
    })[] | null | undefined;
    sorgente: SorgenteLadder | null | undefined;
    sport: 'calcio' | 'tennis';
    /** mercato a due esiti (Over/Under, testa a testa) */
    dueEsiti?: (marketId: string) => boolean;
    /** esito gia' certo della selezione (linea superata dai gol) */
    esitoDeciso?: (marketId: string, selectionId: number) => boolean | null;
    /** l'istante di calcolo (test); di serie Date.now() a ogni render */
    nowMs?: number;
    /**
     * 08/10 (W1, pagina Cash Out) - gambe in PIU' delle righe dei bot (gli
     * ordini del conto fuori dai bot, `cashOutPagina.gambeFuoriBot`), nella
     * STESSA somma. Assente = la cifra di sempre, delle sole righe.
     */
    gambeExtra?: readonly GambaViva[];
}

const chiave = (m: string, s: number) => `${m}|${s}`;

export function useCashOutPartita(args: ArgsCashOutPartita): CashOutPartitaRisultato | null {
    const { operazioni, sorgente, sport, dueEsiti, esitoDeciso, gambeExtra } = args;
    const gambe = useMemo(
        () => (gambeExtra && gambeExtra.length > 0
            ? [...gambeDaOperazioni(operazioni ?? [], { dueEsiti }), ...gambeExtra]
            : gambeDaOperazioni(operazioni ?? [], { dueEsiti })),
        [operazioni, dueEsiti, gambeExtra],
    );
    // i prezzi di ripiego (scanner) per (mercato, selezione), dalle righe
    const ripieghi = useMemo(() => {
        const m = new Map<string, PrezzoScheda>();
        for (const o of operazioni ?? []) {
            const d = o.chiusura?.alMs;
            if (!d?.marketId || d.selectionId == null) continue;
            const p = ripiegoScanner(d);
            if (p) m.set(chiave(d.marketId, d.selectionId), p);
        }
        return m;
    }, [operazioni]);
    // quali selezioni vanno chiuse (e da che lato): un primo giro senza prezzi
    const daSeguire = useMemo<SelezioneAlMs[]>(() => {
        const r = cashOutPartita(gambe, { prezzo: () => null, nowMs: 0, esitoDeciso });
        const out: SelezioneAlMs[] = [];
        const visti = new Set<string>();
        for (const p of [...r.live.gambe, ...r.paper.gambe]) {
            if (p.latoChiusura == null) continue;
            const k = chiave(p.marketId, p.selectionId);
            if (visti.has(k)) continue;
            visti.add(k);
            out.push({ marketId: p.marketId, selectionId: p.selectionId, lato: p.latoChiusura,
                ripiego: ripieghi.get(k) ?? null });
        }
        return out;
    }, [gambe, ripieghi, esitoDeciso]);
    // nessuna selezione da chiudere = nessuna sorgente toccata (le card del
    // giorno senza gambe non aprono niente)
    const prezzi = usePrezziAlMs({ sorgente: daSeguire.length > 0 ? sorgente : null, sport, selezioni: daSeguire });
    if (gambe.length === 0) return null;
    const perChiave = new Map<string, PrezzoScheda>();
    daSeguire.forEach((s, i) => {
        if (s.marketId && s.selectionId != null) perChiave.set(chiave(String(s.marketId), Number(s.selectionId)), prezzi[i]);
    });
    return cashOutPartita(gambe, {
        prezzo: (m, s) => perChiave.get(chiave(m, s)) ?? null,
        nowMs: args.nowMs ?? Date.now(),
        esitoDeciso,
    });
}

// ============================================================================
// 08/10 (W1, secondo giro) - LA SINTESI di un risultato, per far risalire alla
// pagina «Cash Out» la cifra che la scatola HA GIA' calcolato (nessun secondo
// calcolo): per modalita' il netto (null = non calcolabile), le gambe abbinate,
// i motivi e l'eta' del prezzo piu' vecchio. LIVE e PROVA restano separati.
// ============================================================================

export interface SintesiModalitaCashOut {
    netto: number | null;
    nGambe: number;
    mancanti: string[];
    etaPrezziS: number | null;
    etaIgnota: boolean;
}

export interface SintesiCashOut {
    live: SintesiModalitaCashOut;
    paper: SintesiModalitaCashOut;
}

export function sintesiCashOut(r: CashOutPartitaRisultato | null): SintesiCashOut | null {
    if (r == null) return null;
    const m = (x: CashOutPartitaRisultato['live']): SintesiModalitaCashOut => ({
        netto: x.netto, nGambe: x.nGambe, mancanti: [...x.mancanti],
        // l'eta' al secondo: la sintesi cambia quando cambia la cifra, non a ogni ms
        etaPrezziS: x.etaPrezziS == null ? null : Math.round(x.etaPrezziS), etaIgnota: x.etaIgnota,
    });
    return { live: m(r.live), paper: m(r.paper) };
}

/**
 * Riporta la sintesi a chi la chiede (`onSintesi`), SOLO quando cambia (firma
 * della sintesi): il risultato e' un oggetto nuovo a ogni render, riportarlo
 * sempre farebbe ridisegnare la pagina all'infinito. Il richiamo sta in un
 * riferimento: una funzione nuova a ogni render non fa ripartire l'effetto.
 */
export function useRiportaSintesi(
    r: CashOutPartitaRisultato | null,
    onSintesi: ((s: SintesiCashOut | null) => void) | undefined,
): void {
    const cb = useRef(onSintesi);
    cb.current = onSintesi;
    const firma = JSON.stringify(sintesiCashOut(r));
    // anche quando la fonte cambia (il richiamo compare): la cifra si riporta subito
    const attivo = onSintesi != null;
    useEffect(() => {
        if (attivo) cb.current?.(JSON.parse(firma) as SintesiCashOut | null);
    }, [firma, attivo]);
}
