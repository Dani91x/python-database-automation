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
import { useMemo } from 'react';
import { usePrezziAlMs, type SelezioneAlMs, type SorgenteLadder } from './usePrezzoAlMs';
import {
    cashOutPartita, gambeDaOperazioni,
    type CashOutPartitaRisultato, type OperazionePerCashOut,
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
}

const chiave = (m: string, s: number) => `${m}|${s}`;

export function useCashOutPartita(args: ArgsCashOutPartita): CashOutPartitaRisultato | null {
    const { operazioni, sorgente, sport, dueEsiti, esitoDeciso } = args;
    const gambe = useMemo(
        () => gambeDaOperazioni(operazioni ?? [], { dueEsiti }),
        [operazioni, dueEsiti],
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
    const prezzi = usePrezziAlMs({ sorgente, sport, selezioni: daSeguire });
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
