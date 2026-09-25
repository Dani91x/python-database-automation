// ============================================================================
// usePrezzoAlMs.ts - il prezzo di UNA selezione al ms, per la scheda di una
// proposta (24/09/2026, ordine dell'utente: «una scheda che ricalcola al ms
// tutto MA NON BLOCCA L'ENTRATA»).
//
// Si aggancia alla sorgente ladder al ms del mercato della proposta
// (`sorgenteLadderAlMs(sport)` di `lib/localTransport.ts`: canale locale a
// 200 ms, realtime DB solo se il canale tace), si SOTTOSCRIVE al montaggio e si
// STACCA quando la scheda si chiude (unsubscribe nel cleanup). Per un mercato
// che il runner non segue il ladder non arriva mai: la scheda ripiega sul feed
// dello scanner che gia' riceve (`ripiego`), e la fonte lo dichiara.
// Tiene anche l'ULTIMO prezzo noto (con istante e fonte): se il prezzo vivo
// sparisce, al clic parte quello, con il flag `prezzo_vivo_assente`.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import type { LadderSource } from '@/components/live/LadderView';
import {
    prezzoDaLadder, scegliPrezzo, prezzoDelLato, type PrezzoScheda,
} from '@/lib/schedaAlMs';

/** La sorgente del ladder: `sorgenteLadderAlMs` (con `fonte`) o una finta dei test. */
export type SorgenteLadder = (sport: 'calcio' | 'tennis') => LadderSource;

export interface UltimoNoto {
    prezzo: number;
    istanteMs: number | null;
    fonte: PrezzoScheda['fonte'];
}

export function usePrezzoAlMs(args: {
    sorgente: SorgenteLadder | null | undefined;
    sport: 'calcio' | 'tennis';
    marketId: string | null | undefined;
    selectionId: number | null | undefined;
    lato: 'back' | 'lay' | null;
    /** il prezzo dal feed dello scanner (quello che la scheda riceveva gia') */
    ripiego: PrezzoScheda | null;
}): { prezzo: PrezzoScheda; ultimoNoto: UltimoNoto | null } {
    const { sorgente, sport, marketId, selectionId, lato, ripiego } = args;
    const [ladder, setLadder] = useState<PrezzoScheda | null>(null);
    const ultimo = useRef<UltimoNoto | null>(null);

    useEffect(() => {
        setLadder(null);
        if (!sorgente || !marketId || selectionId == null) return undefined;
        const src = sorgente(sport);
        const fonteDi = (mid: string) => {
            const f = (src as { fonte?: (m: string) => 'canale' | 'db' | null }).fonte;
            return typeof f === 'function' ? f(mid) : null;
        };
        const off = src.subscribe(String(marketId), (row) => {
            // null dal path DB = riga sparita: niente prezzo del ladder
            setLadder(row ? prezzoDaLadder(row, selectionId, fonteDi(String(marketId))) : null);
        });
        return () => { off(); };
    }, [sorgente, sport, marketId, selectionId]);

    const prezzo = scegliPrezzo(ladder, ripiego, lato);
    const vivo = prezzoDelLato(prezzo, lato);
    if (vivo != null) ultimo.current = { prezzo: vivo, istanteMs: prezzo.istanteMs, fonte: prezzo.fonte };
    return { prezzo, ultimoNoto: ultimo.current };
}

/** Una selezione da seguire al ms (una gamba di una combo). */
export interface SelezioneAlMs {
    marketId: string | null | undefined;
    selectionId: number | null | undefined;
    lato: 'back' | 'lay' | null;
    ripiego: PrezzoScheda | null;
}

/**
 * 25/09 (residui B17) - come `usePrezzoAlMs`, ma per N selezioni insieme (le
 * gambe di una combo, anche su mercati diversi): UNA sottoscrizione per
 * mercato, staccate tutte allo smontaggio. Per ogni selezione: ladder al ms se
 * porta il lato, altrimenti il ripiego dichiarato (stessa `scegliPrezzo`).
 */
export function usePrezziAlMs(args: {
    sorgente: SorgenteLadder | null | undefined;
    sport: 'calcio' | 'tennis';
    selezioni: readonly SelezioneAlMs[];
}): PrezzoScheda[] {
    const { sorgente, sport, selezioni } = args;
    const [ladder, setLadder] = useState<Record<number, PrezzoScheda | null>>({});
    // la firma delle selezioni: si risottoscrive solo se cambiano mercato/selezione
    const firma = selezioni.map((s) => `${s.marketId ?? ''}|${s.selectionId ?? ''}`).join(',');
    const selRef = useRef(selezioni);
    selRef.current = selezioni;

    useEffect(() => {
        setLadder({});
        if (!sorgente) return undefined;
        const src = sorgente(sport);
        const fonteDi = (mid: string) => {
            const f = (src as { fonte?: (m: string) => 'canale' | 'db' | null }).fonte;
            return typeof f === 'function' ? f(mid) : null;
        };
        const perMercato = new Map<string, number[]>();
        selRef.current.forEach((s, i) => {
            if (!s.marketId || s.selectionId == null) return;
            const k = String(s.marketId);
            const arr = perMercato.get(k);
            if (arr) arr.push(i); else perMercato.set(k, [i]);
        });
        const offs: (() => void)[] = [];
        for (const [mid, indici] of perMercato) {
            offs.push(src.subscribe(mid, (row) => {
                setLadder((p) => {
                    const n = { ...p };
                    for (const i of indici) {
                        const s = selRef.current[i];
                        n[i] = row && s ? prezzoDaLadder(row, s.selectionId, fonteDi(mid)) : null;
                    }
                    return n;
                });
            }));
        }
        return () => { for (const off of offs) off(); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [sorgente, sport, firma]);

    return selezioni.map((s, i) => scegliPrezzo(ladder[i] ?? null, s.ripiego, s.lato));
}
