// ============================================================================
// useMikeClock — UN SOLO orologio da 1 secondo per tutta la sezione Mike.
//
// Perché esiste: il countdown al calcio d'inizio deve scorrere ogni secondo, ma
// se il tempo vive nello stato della PAGINA ogni secondo si ri-renderizza tutto
// (decine di card, tabelle, feed) e le schede "ballano". Qui il tick sta in un
// modulo con UN interval condiviso: lo usano solo i componenti FOGLIA
// (`KickoffCountdown`), quindi un secondo che passa ri-disegna tre parole.
// ============================================================================
import { useEffect, useState } from 'react';

type Listener = (nowMs: number) => void;

const listeners = new Set<Listener>();
let timer: number | null = null;

function ensureTimer() {
    if (timer !== null || typeof window === 'undefined') return;
    timer = window.setInterval(() => {
        const now = Date.now();
        for (const l of listeners) l(now);
    }, 1000);
}

function maybeStop() {
    if (listeners.size === 0 && timer !== null && typeof window !== 'undefined') {
        window.clearInterval(timer);
        timer = null;
    }
}

/** Sottoscrive il tick condiviso: usalo SOLO in componenti foglia. */
export function useSecondTick(enabled = true): number {
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        if (!enabled) return;
        const l: Listener = (n) => setNow(n);
        listeners.add(l);
        ensureTimer();
        return () => { listeners.delete(l); maybeStop(); };
    }, [enabled]);
    return now;
}

export default useSecondTick;
