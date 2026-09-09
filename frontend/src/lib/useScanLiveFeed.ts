// ============================================================================
// useScanLiveFeed — feed LIVE dello scanner Safe Strategy per un insieme di
// eventi calcio (punteggio/minuto a 2s, Correct Score e Half Time Score in
// stream). UN solo canale Realtime per la vita del componente, aggiornamenti
// coalizzati a 400ms, set di eventi in una ref (cambia senza risottoscrivere).
// Usato da Omega (tabella trade), Missioni e pannello manuale: stesso dato,
// stessa sorgente, nessuna chiamata Betfair dal frontend.
// ============================================================================
import { useEffect, useRef, useState } from 'react';
import { fetchScanRows, subscribeScanRows, type CalcioScanPayload } from '@/lib/safeStrategyScan';

export function useScanLiveFeed(eventIds: string[]): Record<string, CalcioScanPayload> {
    const [live, setLive] = useState<Record<string, CalcioScanPayload>>({});
    const wanted = useRef<Set<string>>(new Set());
    wanted.current = new Set(eventIds);
    useEffect(() => {
        let alive = true;
        const pending = new Map<string, CalcioScanPayload | null>();
        let timer: number | undefined;
        const flush = () => {
            timer = undefined;
            if (!alive) return;
            setLive((prev) => {
                const next = { ...prev };
                for (const [id, p] of pending) {
                    if (p === null) delete next[id]; else next[id] = p;
                }
                pending.clear();
                return next;
            });
        };
        const schedule = () => { if (timer === undefined) timer = window.setTimeout(flush, 400); };
        fetchScanRows()
            .then((rows) => {
                if (!alive) return;
                const init: Record<string, CalcioScanPayload> = {};
                for (const r of rows) {
                    if (r.sport === 'calcio' && wanted.current.has(r.event_id)) init[r.event_id] = r.payload as CalcioScanPayload;
                }
                setLive(init);
            })
            .catch(() => { /* scanner/migrazione assenti: i componenti usano i dati del servizio */ });
        const unsub = subscribeScanRows((ev) => {
            if (ev.type === 'upsert') {
                if (ev.row.sport !== 'calcio' || !wanted.current.has(ev.row.event_id)) return;
                pending.set(ev.row.event_id, ev.row.payload as CalcioScanPayload);
            } else {
                pending.set(ev.eventId, null);
            }
            schedule();
        });
        return () => { alive = false; unsub(); if (timer !== undefined) clearTimeout(timer); };
    }, []);
    return live;
}

/** "52′ · 1-0" dal payload live; null se manca minuto o punteggio. */
export function liveScoreLabel(p: CalcioScanPayload | null | undefined): string | null {
    if (!p || p.minute == null || p.score_home == null || p.score_away == null) return null;
    return `${p.minute}′ · ${p.score_home}-${p.score_away}`;
}
