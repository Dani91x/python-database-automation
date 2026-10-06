// ============================================================================
// BotOrdersPanel — "APPLICA BOT" del Match Replay (06/10): gli ordini del bot
// applicato (codice di produzione sul banco) come erano all'istante corrente
// della timeline. Sola lettura. Gli stessi ordini compaiono sul ladder.
// ============================================================================
import type { LiveOrderRow } from '@/lib/liveOrders';

const STATO: Record<string, string> = {
    PENDING: 'in volo',
    EXECUTABLE: 'in coda',
    EXECUTION_COMPLETE: 'chiuso',
    EXPIRED: 'scaduto',
    VIOLATION: 'rifiutato',
};

export function BotOrdersPanel({ titolo, ordini, nomeMercato, nomeSelezione }: {
    titolo: string;
    ordini: LiveOrderRow[];
    nomeMercato: (marketId: string) => string;
    nomeSelezione: (marketId: string, selectionId: number) => string;
}) {
    return (
        <div className="rounded-xl border border-amber-400/30 bg-amber-500/5 p-2" data-testid="ordini-bot">
            <div className="text-[11px] font-bold text-amber-200 mb-1">
                🤖 {titolo} — {ordini.length} ordini a questo istante
                <span className="text-white/40 font-normal"> (sola lettura, anche sul ladder)</span>
            </div>
            {ordini.length === 0 ? (
                <div className="text-[11px] text-white/40">Nessun ordine del bot fino a questo istante della timeline.</div>
            ) : (
                <table className="w-full text-[11px] text-white/80">
                    <thead className="text-white/40">
                        <tr className="text-left">
                            <th className="px-1">Mercato</th><th className="px-1">Selezione</th><th className="px-1">Lato</th>
                            <th className="px-1 text-right">Quota</th><th className="px-1 text-right">Importo</th>
                            <th className="px-1 text-right">Abbinato</th><th className="px-1 text-right">Resto</th>
                            <th className="px-1">Stato</th><th className="px-1">Persist.</th>
                        </tr>
                    </thead>
                    <tbody>
                        {ordini.map(o => (
                            <tr key={o.client_order_ref ?? o.bet_id ?? o.id} className="border-t border-white/5">
                                <td className="px-1">{nomeMercato(o.market_id)}</td>
                                <td className="px-1">{nomeSelezione(o.market_id, o.selection_id)}</td>
                                <td className={`px-1 font-bold ${o.side === 'back' ? 'text-sky-300' : 'text-pink-300'}`}>
                                    {o.side === 'back' ? 'PUNTA' : 'BANCA'}
                                </td>
                                <td className="px-1 text-right tabular-nums">{o.price != null ? o.price.toFixed(2) : '—'}</td>
                                <td className="px-1 text-right tabular-nums">€{(o.size ?? 0).toFixed(2)}</td>
                                <td className="px-1 text-right tabular-nums">
                                    €{o.size_matched.toFixed(2)}{o.size_matched > 0 ? ` @${o.average_price_matched.toFixed(2)}` : ''}
                                </td>
                                <td className="px-1 text-right tabular-nums">€{o.size_remaining.toFixed(2)}</td>
                                <td className="px-1">{STATO[o.status] ?? o.status}</td>
                                <td className="px-1">{o.persistence ?? '—'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}
