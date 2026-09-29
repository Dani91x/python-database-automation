// Cantiere J2 (28/09/2026): il ladder e Segui Live dicono in modo EVIDENTE che
// lo stream di mercato del RUNNER e' muto (prezzi fermi). Segnale: topic
// `flusso_stream` del canale del runner (`lib/flussoStreamRunner.ts`).
// Reperto 3: canale locale giu' = «stato NON NOTO», mai silenzio.
import { useEffect, useState } from 'react';
import { getLocalChannel, type LocalSport } from '@/lib/localChannel';
import { useLocalStatus } from '@/lib/localTransport';
import {
    giudizioConCanale, leggiFlussoStream, type FlussoStreamRunner,
} from '@/lib/flussoStreamRunner';

/** L'ultimo `flusso_stream` del runner di `sport` (null = mai ricevuto). */
export function useFlussoStreamRunner(sport: LocalSport): FlussoStreamRunner | null {
    const [f, setF] = useState<FlussoStreamRunner | null>(null);
    useEffect(() => {
        const ch = getLocalChannel(sport);
        return ch.subscribe('flusso_stream', (d) => {
            const m = leggiFlussoStream(d);
            if (m) setF(m);
        });
    }, [sport]);
    return f;
}

/** Orologio della pagina per far scorrere l'eta' (ogni 2 s). */
function useOra(ms = 2000): number {
    const [ora, setOra] = useState(() => Date.now());
    useEffect(() => {
        const t = setInterval(() => setOra(Date.now()), ms);
        return () => clearInterval(t);
    }, [ms]);
    return ora;
}

/** Vista pura (provata nei test): niente se il flusso e' vivo o non c'e' nulla da dire. */
export function FlussoStreamAvviso({ flusso, marketId, nowMs, canaleConnesso = true }: {
    flusso: FlussoStreamRunner | null; marketId: string | null; nowMs: number;
    canaleConnesso?: boolean;
}) {
    const g = giudizioConCanale(flusso, marketId, nowMs, canaleConnesso);
    if (!g) return null;
    if (g.nonNoto) {
        return (
            <div
                className="w-full rounded border border-amber-500/70 bg-amber-600/20 px-2 py-1 text-[11px] font-bold uppercase tracking-wide text-amber-100"
                data-testid="flusso-stream-runner"
                data-stato="non_noto"
                role="status"
                title={g.testo}
            >
                ⚠ {g.testo}
            </div>
        );
    }
    return (
        <div
            className="w-full rounded border border-red-500/70 bg-red-600/25 px-2 py-1 text-[11px] font-bold uppercase tracking-wide text-red-100 animate-pulse"
            data-testid="flusso-stream-runner"
            data-stato="interrotto"
            role="alert"
            title={g.testo}
        >
            ⚠ {g.testo}
        </div>
    );
}

export default function FlussoStreamBanner({ sport, marketId = null }: {
    sport: LocalSport; marketId?: string | null;
}) {
    const flusso = useFlussoStreamRunner(sport);
    const canale = useLocalStatus(sport);
    const ora = useOra();
    return <FlussoStreamAvviso flusso={flusso} marketId={marketId} nowMs={ora}
        canaleConnesso={canale === 'connected'} />;
}
