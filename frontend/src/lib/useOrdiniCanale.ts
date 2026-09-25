// ============================================================================
// useOrdiniCanale.ts - 25/09 (voce 13): l'aggancio React di `lib/ordiniCanale.ts`,
// gemello di `usePosizioniCanale.ts`. Si abbona al topic `order` del runner
// dello sport (calcio 47331, tennis 47332, via getLocalChannel: nessuna porta
// nuova) e tiene le sovrapposizioni valide rispetto alle righe del poll che il
// chiamante gli passa. Il chiamante mostra `vistaOrdini(righeDb, sovr)`.
// Canale muto: mappa vuota, vista IDENTICA al poll.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import type { LiveOrderRow } from '@/lib/liveOrders';
import { getLocalChannel } from '@/lib/localChannel';
import {
    applicaPushOrdine, leggiPushOrdine, potaOrdini, type SovrapposizioniOrdini,
} from '@/lib/ordiniCanale';

const VUOTA: SovrapposizioniOrdini = new Map();

export function useOrdiniCanale(
    sport: 'calcio' | 'tennis', righeDb: readonly LiveOrderRow[] | null,
): SovrapposizioniOrdini {
    const [sovr, setSovr] = useState<SovrapposizioniOrdini>(VUOTA);
    const righeRef = useRef<readonly LiveOrderRow[]>(righeDb ?? []);
    useEffect(() => {
        righeRef.current = righeDb ?? [];
        setSovr((prev) => potaOrdini(prev, righeDb ?? []));
    }, [righeDb]);
    useEffect(() => getLocalChannel(sport).subscribe('order', (d) => {
        const p = leggiPushOrdine(d);
        if (!p) return;
        setSovr((prev) => applicaPushOrdine(prev, righeRef.current, p));
    }), [sport]);
    return sovr;
}
