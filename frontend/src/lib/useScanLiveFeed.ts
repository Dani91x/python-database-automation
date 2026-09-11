// ============================================================================
// useScanLiveFeed — feed LIVE dello scanner Safe Strategy per un insieme di
// eventi calcio (punteggio/minuto a 2s, Correct Score e Half Time Score in
// stream). UN solo canale Realtime per la vita del componente, aggiornamenti
// coalizzati a 400ms, set di eventi in una ref (cambia senza risottoscrivere).
// Usato da Omega (tabella trade), Missioni e pannello manuale: stesso dato,
// stessa sorgente, nessuna chiamata Betfair dal frontend.
//
// `useScanLiveFeedRows` espone anche l'`updated_at` di OGNI riga: la tabella
// di Omega deve poter dire "feed di 3 s" o "FEED FERMO" per quella partita
// (audit 11/09: prima un punteggio vecchio di dieci minuti era indistinguibile
// da uno fresco, e su quel punteggio si decide un cash out).
// ============================================================================
import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchScanRows, subscribeScanRows, type CalcioScanPayload } from '@/lib/safeStrategyScan';

export interface ScanLiveRow {
    payload: CalcioScanPayload;
    /** ISO dell'ultimo aggiornamento della riga (null = non dichiarato) */
    updated_at: string | null;
}

/** feed + freschezza per evento (una sola sottoscrizione). */
export function useScanLiveFeedRows(eventIds: string[]): Record<string, ScanLiveRow> {
    const [live, setLive] = useState<Record<string, ScanLiveRow>>({});
    const wanted = useRef<Set<string>>(new Set());
    wanted.current = new Set(eventIds);
    /**
     * Certificazione 11/09 — l'effetto girava una volta sola (`[]`) e il fetch
     * INIZIALE filtrava su `wanted.current`, che al mount è VUOTO: gli
     * event_id arrivano dai trade, che arrivano dopo. Risultato: la tabella di
     * Omega restava senza quote live fino al primo messaggio realtime di
     * quella partita — su un mercato tranquillo, minuti di colonne vuote (e
     * "FEED ASSENTE" su un feed che invece c'era).
     *
     * Chiave ORDINATA dell'insieme: l'effetto si rifà quando l'insieme cambia
     * DAVVERO, non a ogni render (l'array `eventIds` è ricostruito ogni volta).
     */
    const key = useMemo(() => [...new Set(eventIds)].sort().join(','), [eventIds]);

    // ---- 1. SOTTOSCRIZIONE: UN solo canale per la vita del componente (§18).
    // Non dipende dagli event_id (il filtro è sulla ref `wanted`): cambiare
    // l'insieme non deve mai chiudere e riaprire il canale Realtime.
    useEffect(() => {
        let alive = true;
        const pending = new Map<string, ScanLiveRow | null>();
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
        const unsub = subscribeScanRows((ev) => {
            if (ev.type === 'upsert') {
                if (ev.row.sport !== 'calcio' || !wanted.current.has(ev.row.event_id)) return;
                pending.set(ev.row.event_id, {
                    payload: ev.row.payload as CalcioScanPayload,
                    updated_at: ev.row.updated_at ?? new Date().toISOString(),
                });
            } else {
                pending.set(ev.eventId, null);
            }
            schedule();
        });
        return () => { alive = false; unsub(); if (timer !== undefined) clearTimeout(timer); };
    }, []);

    // ---- 2. FOTOGRAFIA INIZIALE: si rifà quando l'insieme degli eventi cambia
    // (i trade arrivano dopo il mount). UNA SELECT per insieme, non per render.
    useEffect(() => {
        if (key === '') return;               // niente da seguire: nessuna SELECT
        let alive = true;
        fetchScanRows()
            .then((rows) => {
                if (!alive) return;
                const init: Record<string, ScanLiveRow> = {};
                for (const r of rows) {
                    if (r.sport === 'calcio' && wanted.current.has(r.event_id)) {
                        init[r.event_id] = { payload: r.payload as CalcioScanPayload, updated_at: r.updated_at ?? null };
                    }
                }
                if (Object.keys(init).length === 0) return;
                // si FONDE con quello che il realtime ha già portato: un
                // messaggio arrivato durante la SELECT non va perso, e una riga
                // più FRESCA non viene sostituita da quella della fotografia
                setLive((prev) => {
                    const next = { ...prev };
                    for (const [id, row] of Object.entries(init)) {
                        const old = next[id];
                        const piuRecente = old?.updated_at && row.updated_at
                            && Date.parse(old.updated_at) >= Date.parse(row.updated_at);
                        if (!piuRecente) next[id] = row;
                    }
                    return next;
                });
            })
            .catch(() => { /* scanner/migrazione assenti: i componenti usano i dati del servizio */ });
        return () => { alive = false; };
    }, [key]);

    return live;
}

/** SOLO i payload (firma storica: non cambiare, la usano tre sezioni). */
export function useScanLiveFeed(eventIds: string[]): Record<string, CalcioScanPayload> {
    const rows = useScanLiveFeedRows(eventIds);
    return useMemo(() => {
        const out: Record<string, CalcioScanPayload> = {};
        for (const [id, r] of Object.entries(rows)) out[id] = r.payload;
        return out;
    }, [rows]);
}

/** "52′ · 1-0" dal payload live; null se manca minuto o punteggio. */
export function liveScoreLabel(p: CalcioScanPayload | null | undefined): string | null {
    if (!p || p.minute == null || p.score_home == null || p.score_away == null) return null;
    return `${p.minute}′ · ${p.score_home}-${p.score_away}`;
}
