// ============================================================================
// StandaloneLadder — un ladder AUTOSUFFICIENTE per popout e multi-ladder (B19):
// dato (sport, eventId, marketId) risolve DA SOLO modalità ordini, nome mercato e
// selezioni fallback, e monta il LadderView con le sorgenti dati giuste.
//
//   calcio → live_now (fetch+subscribe) per order_mode/mercati; sorgenti default.
//   tennis → riusa TennisLadderColumn (che fa lo stesso su tennis_live_now).
//
// MONEY-CRITICAL: se lo stato live dell'evento non è raggiungibile, la modalità
// resta 'off' (ladder in sola lettura) — mai assumere PAPER/LIVE da parametri URL.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import { fetchLiveNow, subscribeLiveNow, type LiveNowRow } from '@/lib/live';
import { TennisLadderColumn } from '@/components/tennis/TennisLadderColumn';
import LadderView from './LadderView';
import type { LadderSlot } from '@/lib/multiLadder';
// fix B33 punto 1: canale locale al ms come via principale (DB come ripiego
// gia' dentro la sorgente), stesso schema di SeguiLive.tsx/TennisLadderColumn
// (il ramo tennis di questo file passa gia' da TennisLadderColumn, che lo usa).
import { sorgenteLadderAlMs } from '@/lib/localTransport';

function CalcioStandaloneLadder({ eventId, marketId, marketName, eventName }: {
    eventId: string;
    marketId: string;
    marketName?: string;
    eventName?: string;
}) {
    const [now, setNow] = useState<LiveNowRow | null>(null);
    const unsubRef = useRef<(() => void) | null>(null);

    useEffect(() => {
        if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        setNow(null);
        if (!eventId) return;
        let alive = true;
        fetchLiveNow(eventId)
            .then(r => { if (alive) setNow(r); })
            .catch((e: unknown) => {
                if ((e as { code?: string })?.code !== 'PGRST116') console.warn('[StandaloneLadder] fetchLiveNow:', e);
            });
        // fix audit #22: propaga anche il DELETE (r = null) — tenere l'ultima riga
        // manterrebbe l'order_mode vecchio; con null il fallback sotto degrada a 'off'
        // (sola lettura), il fail-safe corretto quando lo stato live sparisce.
        unsubRef.current = subscribeLiveNow(eventId, (r) => setNow(r));
        return () => {
            alive = false;
            if (unsubRef.current) { unsubRef.current(); unsubRef.current = null; }
        };
    }, [eventId]);

    const market = now?.state?.markets?.find(m => m.market_id === marketId) ?? null;
    // fail-safe: senza live_now la modalità è OFF (sola lettura), MAI derivata dall'URL.
    const mode = now?.state?.order_mode ?? 'off';

    return (
        <LadderView
            marketId={marketId}
            marketName={market?.market_name || market?.market_type || marketName || marketId}
            orderMode={mode}
            sport="calcio"
            fallbackSelections={(market?.selections ?? []).map(s => ({
                selection_id: s.selection_id, name: s.name,
            }))}
            // fix B33 punto 1: canale locale calcio al ms (47331) come via
            // principale del ladder, DB come ripiego automatico (gia' dentro
            // la sorgente) -- prima usava il default DI LadderView (solo DB),
            // unico ladder rimasto sulla vecchia via in popout/multi-ladder.
            ladderSource={sorgenteLadderAlMs('calcio')}
            popout={{ sport: 'calcio', eventId }}
            multiSlot={{
                sport: 'calcio', eventId, marketId,
                marketName: market?.market_name || marketName || marketId,
                eventName: eventName ?? '',
            }}
        />
    );
}

// Ladder autosufficiente per uno slot multi-ladder / parametri popout.
export function StandaloneLadder({ slot }: { slot: Omit<LadderSlot, 'id'> }) {
    if (slot.sport === 'tennis') {
        return (
            <TennisLadderColumn
                eventId={slot.eventId}
                marketId={slot.marketId}
                marketName={slot.marketName}
                p1={slot.p1 ?? ''}
                p2={slot.p2 ?? ''}
            />
        );
    }
    return (
        <CalcioStandaloneLadder
            eventId={slot.eventId}
            marketId={slot.marketId}
            marketName={slot.marketName}
            eventName={slot.eventName}
        />
    );
}

export default StandaloneLadder;
