// ============================================================================
// usePosizioniCanale.ts - 23/09: l'aggancio React di lib/canaleRunner.ts per le
// posizioni. Si abbona al topic `position` del runner dello sport (calcio
// 47331, tennis 47332, via getLocalChannel: nessuna porta nuova) e tiene le
// sovrapposizioni valide rispetto alle righe del database che il chiamante
// gli passa (il suo poll, invariato). Il chiamante mostra
// `vistaPosizioni(righeDb, sovrapposizioni)`.
//
// Canale muto o spento: la mappa resta vuota e la vista e' IDENTICA alle righe
// del database (stesso array). Nessuna lettura del database parte da qui.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import type { LivePositionRow } from '@/lib/liveOrders';
import { getLocalChannel } from '@/lib/localChannel';
import {
    applicaPushPosizione, leggiPushPosizione, potaSovrapposizioni,
    type SovrapposizioniPos,
} from '@/lib/canaleRunner';

const VUOTA: SovrapposizioniPos = new Map();

export function usePosizioniCanale(
    sport: 'calcio' | 'tennis', righeDb: readonly LivePositionRow[] | null,
): SovrapposizioniPos {
    const [sovr, setSovr] = useState<SovrapposizioniPos>(VUOTA);
    const righeRef = useRef<readonly LivePositionRow[]>(righeDb ?? []);
    // blocco nuovo del database: le righe sono le sue, le sovrapposizioni non
    // piu' fresche (o di righe sparite) si buttano.
    useEffect(() => {
        righeRef.current = righeDb ?? [];
        setSovr(prev => potaSovrapposizioni(prev, righeDb ?? []));
    }, [righeDb]);
    useEffect(() => getLocalChannel(sport).subscribe('position', (d) => {
        const p = leggiPushPosizione(d);
        if (!p) return;
        setSovr(prev => applicaPushPosizione(prev, righeRef.current, p));
    }), [sport]);
    return sovr;
}
