// ============================================================================
// TrainingTradesPanel — i TRADE del LADDER TRAINING di Match Replay (06/10).
// Prima gli ordini simulati del training non comparivano da nessuna parte fuori
// dal ladder e non si potevano togliere: qui la lista di TUTTI gli ordini della
// sessione di training (tutti i mercati), risolti all'istante corrente della
// timeline dal matching engine (stesso `api.resolved()` del ladder), con la X
// che ELIMINA il trade dalla sessione (`api.remove`).
// ============================================================================
import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import type { TrainingApi } from '@/lib/trainingLadder';

const STATO: Record<string, string> = {
    PENDING: 'in ritardo…',
    OPEN: 'in coda',
    MATCHED: 'abbinato',
    CANCELLED: 'annullato',
    LAPSED: 'decaduto',
};

export function TrainingTradesPanel({ api, nomeMercato, nomeSelezione }: {
    api: TrainingApi;
    // istante corrente della timeline: cambia a ogni passo e fa ridisegnare
    // (api.resolved() risolve all'istante corrente)
    nowMs: number;
    nomeMercato: (marketId: string) => string;
    nomeSelezione: (marketId: string, selectionId: number) => string;
}) {
    // ridisegno a ogni cambio degli ordini (piazzato, annullato, eliminato)
    const [, setVersione] = useState(0);
    useEffect(() => api.onChange(() => setVersione(v => v + 1)), [api]);

    const righe = api.resolved().slice().sort((a, b) => b.order.req.placedTs - a.order.req.placedTs);
    return (
        <div className="rounded-xl border border-white/10 bg-black/30 p-2" data-testid="trade-training">
            <div className="text-[11px] font-bold text-white/80 mb-1">
                Trade del training ({righe.length}) <span className="text-white/40 font-normal">— stato all&apos;istante della timeline</span>
            </div>
            {righe.length === 0 ? (
                <div className="text-[11px] text-white/40">Nessun ordine: piazza dal ladder qui sopra.</div>
            ) : (
                <table className="w-full text-[11px] text-white/80">
                    <thead className="text-white/40">
                        <tr className="text-left">
                            <th className="px-1">Ora</th><th className="px-1">Mercato</th><th className="px-1">Selezione</th>
                            <th className="px-1">Lato</th><th className="px-1 text-right">Quota</th>
                            <th className="px-1 text-right">Stake</th><th className="px-1 text-right">Abbinato</th>
                            <th className="px-1">Stato</th><th className="px-1"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {righe.map(({ order: o, res }) => (
                            <tr key={o.id} className="border-t border-white/5" data-testid={`trade-training-${o.id}`}>
                                <td className="px-1 tabular-nums">{new Date(o.req.placedTs).toLocaleTimeString('it-IT')}</td>
                                <td className="px-1">{nomeMercato(o.market_id)}</td>
                                <td className="px-1">{nomeSelezione(o.market_id, o.selection_id)}</td>
                                <td className={`px-1 font-bold ${o.req.side === 'back' ? 'text-sky-300' : 'text-pink-300'}`}>
                                    {o.req.side === 'back' ? 'PUNTA' : 'BANCA'}
                                </td>
                                <td className="px-1 text-right tabular-nums">{o.req.limitPrice.toFixed(2)}</td>
                                <td className="px-1 text-right tabular-nums">€{o.req.stake.toFixed(2)}</td>
                                <td className="px-1 text-right tabular-nums">
                                    €{res.matched.toFixed(2)}{res.avgPrice != null ? ` @${res.avgPrice.toFixed(2)}` : ''}
                                </td>
                                <td className="px-1">{STATO[res.status] ?? res.status}</td>
                                <td className="px-1 text-right">
                                    <button
                                        type="button"
                                        onClick={() => api.remove(o.id)}
                                        className="text-white/40 hover:text-red-400"
                                        aria-label={`Elimina il trade ${o.bet_id}`}
                                        title="Elimina questo trade dalla sessione di training"
                                    >
                                        <X className="w-3.5 h-3.5" />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}
