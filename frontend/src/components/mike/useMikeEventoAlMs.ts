// ============================================================================
// useMikeEventoAlMs - LA SCHEDA DI UNA PARTITA DI MIKE, AL MILLISECONDO (29/09, M7.1).
//
// Il servizio Mike spinge la scheda di ogni partita sul canale locale GIA'
// esistente (ws://127.0.0.1:47333, topic `mike_event`, `service._pubblica_evento`)
// a OGNI giro del bot, mentre sul database i campi che si muovono col book
// (`live.cashout`, `live.books`, `published_ts` ...) si riscrivono solo ogni
// `publish_heartbeat_s` (5 s) e la Control Room li rilegge ogni 30 s. La pagina
// di Mike quel canale lo ascolta gia' (`useMike`); la card di Mike in Control
// Room no. Questo hook porta il canale a chi mostra le cifre di una SOLA partita
// (proposta d'uscita, esito della chiusura): nessun canale nuovo, lo stesso
// singleton `getLocalChannel('mike')`, e la stessa regola di fusione della
// pagina (`fondiEventiLocali`: il push SOVRAPPONE campo per campo, `ctx` e
// `dossier` restano del database perche' il bot non li spinge).
//
// Via principale il canale; ripiego la riga del database (che resta com'e').
// Il push vince solo se e' PIU' RECENTE (`live.published_ts`); se il socket
// cade si butta il push e si torna al database, mai una foto ferma.
// ============================================================================
import { useEffect, useMemo, useState } from 'react';
import { fondiEventiLocali, type MikeEvent, type MikeEventoSpinto } from '@/lib/mike';
import { getLocalChannel, type LocalStatus } from '@/lib/localChannel';

/** Quello che serve del canale (i test passano un finto con la stessa forma). */
export interface CanaleEventiMike {
    subscribe(topic: string, cb: (d: unknown) => void): () => void;
    onStatus(cb: (s: LocalStatus) => void): () => void;
    getStatus(): LocalStatus;
}

const CANALE_DI_SERIE = (): CanaleEventiMike => getLocalChannel('mike');

function pubTs(live: unknown): number | null {
    const v = (live as { published_ts?: unknown } | null | undefined)?.published_ts;
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/**
 * La partita `ev` con sopra l'ultimo push del canale per la STESSA partita, se
 * piu' recente. `attivo=false` = nessuna sottoscrizione (niente da mostrare).
 */
export function useMikeEventoAlMs(
    ev: MikeEvent, attivo: boolean,
    canale: (() => CanaleEventiMike) | null = CANALE_DI_SERIE,
): { ev: MikeEvent; fonte: 'canale' | 'db' } {
    const [spinto, setSpinto] = useState<MikeEventoSpinto | null>(null);
    const eid = String(ev.event_id);
    useEffect(() => {
        setSpinto(null);
        if (!attivo || canale == null) return;
        const ch = canale();
        const offEv = ch.subscribe('mike_event', (d) => {
            const row = d as MikeEventoSpinto | null;
            if (!row || typeof row !== 'object' || String(row.event_id ?? '') !== eid) return;
            setSpinto(row);
        });
        const offSt = ch.onStatus((s) => { if (s !== 'connected') setSpinto(null); });
        return () => { offEv(); offSt(); };
    }, [eid, attivo, canale]);
    return useMemo(() => {
        if (!spinto) return { ev, fonte: 'db' as const };
        const tp = pubTs(spinto.live);
        const td = pubTs(ev.live);
        // il push senza ora, o piu' vecchio del database, non vince
        if (tp == null || (td != null && td > tp)) return { ev, fonte: 'db' as const };
        return { ev: fondiEventiLocali([ev], new Map([[eid, spinto]]))[0], fonte: 'canale' as const };
    }, [ev, spinto, eid]);
}

export default useMikeEventoAlMs;
