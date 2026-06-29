// ============================================================================
// LiveMarketBoard — griglia dei mercati live letti da live_now.state.markets.
// Organizzazione IDENTICA al Match Replay: tab per categoria (Match Odds,
// Over/Under, Correct Score, First Half, BTTS, Squadre/Altri) con i pulsanti,
// e ogni mercato = card con selezioni e prezzi back (azzurro) / lay (rosa) / ltp.
// Quando un mercato è CHIUSO (risolto) compare un banner "Chiuso" sopra la card
// (e "Sospeso" durante una sospensione). Si aggiorna in realtime.
// ============================================================================
import { useState } from 'react';
import { Card } from '@/components/ui/card';
import type { LiveNowState, LiveNowMarket } from '@/lib/live';
import { type CatKey, groupByCategory, presentCategories } from '@/lib/market-categories';

function priceCell(value: number | null, kind: 'back' | 'lay') {
    const tint = kind === 'back'
        ? 'bg-blue-500/15 text-blue-200'
        : 'bg-pink-500/15 text-pink-200';
    return (
        <div className={`rounded-md px-2 py-1 text-center text-xs font-bold tabular-nums ${tint}`}>
            {value != null && Number.isFinite(value) ? value.toFixed(2) : '—'}
        </div>
    );
}

function MarketCard({ m }: { m: LiveNowMarket }) {
    const status = (m.status ?? '').toUpperCase();
    const isClosed = status === 'CLOSED';
    const isSuspended = status === 'SUSPENDED';
    return (
        <Card className="glass-card border-white/10 overflow-hidden">
            {/* banner di stato sopra il mercato */}
            {isClosed && (
                <div className="bg-white/10 text-muted-foreground text-[11px] font-black uppercase tracking-wider text-center py-1.5 border-b border-white/15">
                    Chiuso
                </div>
            )}
            {isSuspended && (
                <div className="bg-red-500/15 text-red-300 text-[11px] font-black uppercase tracking-wider text-center py-1.5 border-b border-red-500/30">
                    Sospeso
                </div>
            )}
            <div className={isClosed || isSuspended ? 'opacity-50' : ''}>
                <div className="px-4 py-2.5 border-b border-white/5 flex items-center justify-between">
                    <span className="font-heading font-bold text-sm">{m.market_name || m.market_type}</span>
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{m.market_type}</span>
                </div>
                <div className="p-3">
                    <div className="grid grid-cols-[1fr_auto_auto_auto] gap-2 items-center text-[10px] uppercase tracking-wider text-muted-foreground px-1 pb-1">
                        <span>Selezione</span>
                        <span className="w-16 text-center">Back</span>
                        <span className="w-16 text-center">Lay</span>
                        <span className="w-14 text-center">LTP</span>
                    </div>
                    <div className="space-y-1.5">
                        {m.selections.map(s => (
                            <div key={s.selection_id} className="grid grid-cols-[1fr_auto_auto_auto] gap-2 items-center">
                                <span className="text-sm text-white truncate">{s.name}</span>
                                <div className="w-16">{priceCell(s.back, 'back')}</div>
                                <div className="w-16">{priceCell(s.lay, 'lay')}</div>
                                <div className="w-14 text-center text-xs tabular-nums text-muted-foreground">
                                    {s.ltp != null && Number.isFinite(s.ltp) ? s.ltp.toFixed(2) : '—'}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </Card>
    );
}

export function LiveMarketBoard({ state, updatedAt }: { state: LiveNowState | null; updatedAt?: string | null }) {
    const markets = state?.markets ?? [];
    const [activeCategory, setActiveCategory] = useState<CatKey>('MATCH_ODDS');

    // categorizzazione IDENTICA al Match Replay (modulo condiviso).
    const categorized = groupByCategory(markets);
    const present = presentCategories(categorized);
    const activeCat: CatKey = present.some(c => c.key === activeCategory)
        ? activeCategory
        : (present[0]?.key ?? 'MATCH_ODDS');
    const activeMarkets = categorized.get(activeCat) ?? [];

    if (markets.length === 0) {
        return (
            <Card className="glass-card border-white/10 p-6 text-center text-sm text-muted-foreground">
                Nessun mercato live disponibile per questa partita al momento.
            </Card>
        );
    }

    return (
        <div className="space-y-4">
            {updatedAt && (
                <div className="text-[10px] text-muted-foreground text-right">
                    Aggiornato: {new Date(updatedAt).toLocaleTimeString('it')}
                </div>
            )}

            {/* tab categorie (stessi pulsanti del Match Replay) */}
            <div className="flex items-center gap-2 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-thin">
                {present.map(c => (
                    <button
                        key={c.key}
                        onClick={() => setActiveCategory(c.key)}
                        className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-bold border transition-colors whitespace-nowrap ${
                            activeCat === c.key
                                ? 'bg-primary text-black border-primary'
                                : 'border-white/10 text-muted-foreground hover:text-white'
                        }`}
                    >
                        {c.label}
                        <span className="ml-1 opacity-60 tabular-nums">{categorized.get(c.key)?.length ?? 0}</span>
                    </button>
                ))}
            </div>

            {/* griglia dei mercati della categoria attiva */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {activeMarkets.map(m => <MarketCard key={m.market_id} m={m} />)}
            </div>
        </div>
    );
}
