// ============================================================================
// OrdiniContoPartita.tsx - P14 (30/09): gli ordini del CONTO fuori dai bot su
// UNA partita, sotto il riquadro del cash out della partita.
//
//   Ordini dal sito/app (conto Betfair): BACK Over 3,5 4,43 EUR @ 1,92 - ...
//   [CONTO BETFAIR - 12 s fa]
//   il bot non li vede: la cifra del cash out delle gambe dei bot non e' la
//   posizione del conto                                              (ambra)
//
// Dati dal contesto `OrdiniContoContext` (lo fornisce la Control Room col
// campo `vm.ordiniConto`): fuori dalla Control Room non disegna niente.
// Ordini non letti (RPC assente o errore): lo dice, mai "nessun ordine".
// ============================================================================
import { createContext, useContext } from 'react';
import { fmtMoney, fmtOdds, fmtTime, DASH } from '@/lib/format';
import { MarchioSoldi } from '@/components/controlroom/MarchioSoldi';
import type { OrdiniContoStato } from './ordiniConto';

export const OrdiniContoContext = createContext<{ stato: OrdiniContoStato; nowMs: number } | null>(null);

export function OrdiniContoPartita({ eventId, sport = 'calcio' }: {
    eventId: string;
    /** gli ordini manuali TENNIS dell'app stanno in `tennis_live_orders`, non
     *  in questa RPC: la scheda tennis non promette "ordini del conto" */
    sport?: 'calcio' | 'tennis';
}) {
    const ctx = useContext(OrdiniContoContext);
    if (ctx == null || sport === 'tennis') return null;
    const { stato, nowMs } = ctx;
    if (stato.stato !== 'letti') {
        return (
            <div className="px-2.5 pt-1 text-[10px] text-white/35" data-testid="cr-ordini-conto-non-letti"
                title="gli ordini fatti sul conto fuori dai bot (sito, app) non sono stati letti: la scheda mostra solo le gambe dei bot">
                ordini del conto: non letti ({stato.motivo ?? 'motivo ignoto'})
            </div>
        );
    }
    const righe = stato.perEvento.get(String(eventId)) ?? [];
    if (righe.length === 0) return null;
    const ms = stato.lettoAt ? Date.parse(stato.lettoAt) : NaN;
    const etaS = Number.isFinite(ms) ? Math.max(0, Math.round((nowMs - ms) / 1000)) : null;
    return (
        <div className="px-2.5 pt-1.5 space-y-0.5" data-testid="cr-ordini-conto">
            <div className="flex items-center gap-1.5 flex-wrap text-[11px]">
                <span className="text-white/55">Ordini dal sito/app (conto Betfair):</span>
                {righe.map((r, i) => (
                    <span key={r.bet_id} className="font-mono tabular-nums" data-testid="cr-ordine-conto">
                        {i > 0 && <span className="text-white/30">{' \u00b7 '}</span>}
                        <span className={r.side === 'LAY' ? 'text-rose-300' : 'text-sky-300'}>{r.side}</span>
                        {' '}{r.selection_name ?? `selezione ${r.selection_id}`}
                        {/* price_matched null = nulla abbinato: mai "0,00", mai una quota */}
                        {r.price_matched == null
                            ? <span className="text-white/50"> non abbinato</span>
                            : <>{' '}{fmtMoney(r.size_matched)} @ {fmtOdds(r.price_matched)}</>}
                        {r.size_remaining > 0 && <span className="text-white/40"> (+{fmtMoney(r.size_remaining)} sul book)</span>}
                    </span>
                ))}
                <MarchioSoldi fonte="conto" etaS={etaS} testId="cr-ordini-conto-marchio"
                    dettaglio="ordini sul conto non piazzati dai bot, dallo specchio degli ordini (get_live_orders_account_open); eta' = interrogazione, non freschezza dello specchio" />
            </div>
            {/* limite dichiarato dal backend: ad app chiusa il "regolato" non si
                aggiorna, quindi "aperto" vale per il conto letto a quell'ora */}
            <div className="text-[10px] text-white/40" data-testid="cr-ordini-conto-letto">
                {/* review finale 30/09 (R2-A2): `letto_at` e' l'istante dell'INTERROGAZIONE
                    (now() nella RPC); le righe vengono dallo specchio degli ordini che
                    scrive il runner: se il runner e' fermo lo specchio e' vecchio */}
                aperto secondo lo specchio degli ordini interrogato alle {Number.isFinite(ms) ? fmtTime(ms, { seconds: true }) : DASH}
                <span className="text-white/30"> (lo specchio lo aggiorna il runner: se il runner e' fermo, e' vecchio)</span>
            </div>
            <div className="text-[10.5px] text-amber-300" data-testid="cr-ordini-conto-avviso">
                il bot non li vede: la cifra del cash out delle gambe dei bot non e&apos; la posizione del conto
            </div>
        </div>
    );
}

export default OrdiniContoPartita;
