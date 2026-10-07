// ============================================================================
// BotOrdersPanel — gli ordini del bot applicato COME ERANO all'istante del
// cursore (06/10; rifatto il 07/10 sera). UNA riga per ORDINE (identita' vera
// dell'ordine, non del ref: un riprezzo e' un ordine nuovo), con lo stato
// leggibile: un ordine con abbinato 0 tolto dal mercato e' «annullato» o
// «sostituito» (o «scaduto»), MAI «chiuso». Di serie si vedono gli ordini
// sul book e quelli con abbinamenti; gli ordini tolti senza abbinamenti sono
// nel registro delle operazioni.
// ============================================================================
import { useState } from 'react';
import { eur, nomeLato, statoOrdineTesto, type OrdineAlMs } from '@/lib/replayOperazioni';

export function BotOrdersPanel({ titolo, ordini, nomeMercato, nomeSelezione, onSeek }: {
    titolo: string;
    ordini: OrdineAlMs[];
    nomeMercato: (marketId: string) => string;
    nomeSelezione: (marketId: string, selectionId: number) => string;
    onSeek?: (ms: number, marketId: string, selectionId: number) => void;
}) {
    const [tutti, setTutti] = useState(false);
    const visibili = tutti ? ordini : ordini.filter(o => o.vivo || o.abbinato > 0.005);
    const vivi = ordini.filter(o => o.vivo).length;
    return (
        <div className="rounded-xl border border-amber-400/30 bg-amber-500/5 p-2" data-testid="ordini-bot">
            <div className="text-[11px] font-bold text-amber-200 mb-1 flex flex-wrap items-center gap-2">
                <span>🤖 {titolo} — al cursore: {vivi} ordini sul book, {ordini.filter(o => o.abbinato > 0.005).length} con abbinamenti</span>
                <label className="font-normal text-white/50 flex items-center gap-1">
                    <input type="checkbox" checked={tutti} onChange={e => setTutti(e.target.checked)} />
                    mostra anche i {ordini.length - visibili.length} tolti senza abbinamenti
                </label>
            </div>
            {visibili.length === 0 ? (
                <div className="text-[11px] text-white/40">Nessun ordine del bot sul book o abbinato a questo istante.</div>
            ) : (
                <table className="w-full text-[11px] text-white/80">
                    <thead className="text-white/40">
                        <tr className="text-left">
                            <th className="px-1">Mercato</th><th className="px-1">Selezione</th><th className="px-1">Lato</th>
                            <th className="px-1 text-right">Quota</th><th className="px-1 text-right">Importo</th>
                            <th className="px-1 text-right">Abbinato</th><th className="px-1 text-right">Sul book</th>
                            <th className="px-1">Stato</th><th className="px-1">Bet</th>
                        </tr>
                    </thead>
                    <tbody>
                        {visibili.map(x => (
                            <tr key={x.ordine.chiave} data-testid="ordine-bot-riga"
                                onClick={onSeek ? () => onSeek(x.riga._ms, x.ordine.marketId, x.ordine.selectionId) : undefined}
                                className={`border-t border-white/5 ${onSeek ? 'cursor-pointer hover:bg-white/5' : ''} ${x.vivo ? 'bg-amber-400/10' : ''}`}>
                                <td className="px-1">{nomeMercato(x.ordine.marketId)}</td>
                                <td className="px-1">{nomeSelezione(x.ordine.marketId, x.ordine.selectionId)}</td>
                                <td className={`px-1 font-bold ${x.ordine.lato === 'back' ? 'text-sky-300' : 'text-pink-300'}`}>{nomeLato(x.ordine.lato)}</td>
                                <td className="px-1 text-right tabular-nums">{eur(x.riga.price)}</td>
                                <td className="px-1 text-right tabular-nums">{eur(x.riga.size)}</td>
                                <td className="px-1 text-right tabular-nums">{eur(x.abbinato)}{x.abbinato > 0.005 ? ` @${eur(x.prezzoMedio)}` : ''}</td>
                                <td className="px-1 text-right tabular-nums">{eur(x.residuo)}</td>
                                <td className="px-1">{statoOrdineTesto(x.riga, x.ordine.sostituitoDa != null)}</td>
                                <td className="px-1 text-white/40">{x.ordine.betId ?? '—'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}
