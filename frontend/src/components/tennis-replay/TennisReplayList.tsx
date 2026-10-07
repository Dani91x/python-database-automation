// ============================================================================
// TennisReplayList — elenco delle partite di tennis registrate e caricate nel
// Replay Tennis, per torneo e anno (come l'elenco del Match Replay per lega e
// anno). Solo presentazione: i dati arrivano da `fetchTennisReplayList`.
// ============================================================================
import { History, Trophy } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { raggruppaPerTorneo, type TennisReplayItem } from '@/lib/tennisReplay';

function dataOra(iso: string | null): string {
    if (!iso) return '—';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('it');
}

export function TennisReplayList({ items, onSelect }: {
    items: ReadonlyArray<TennisReplayItem>;
    onSelect: (item: TennisReplayItem) => void;
}) {
    if (items.length === 0) {
        return (
            <Card className="glass-card border-white/10 p-10 text-center" data-testid="tennis-replay-vuoto">
                <History className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-50" />
                <p className="text-sm text-muted-foreground">Nessuna partita di tennis registrata nel Replay Tennis.</p>
                <p className="text-[11px] text-muted-foreground/70 mt-2">
                    Le partite registrate entrano da sole a fine partita; quelle gia&apos; su disco si caricano con
                    {' '}<code className="font-mono">python -m Betfair.stream.tennis_replay.importa &lt;cartella&gt;</code>.
                </p>
            </Card>
        );
    }
    return (
        <div className="space-y-6" data-testid="tennis-replay-elenco">
            {raggruppaPerTorneo(items).map(g => (
                <div key={g.key} className="space-y-3">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-black/40 border border-white/10 flex items-center justify-center shrink-0">
                            <Trophy className="w-4 h-4 text-primary/70" />
                        </div>
                        <h2 className="font-heading font-bold text-sm md:text-base text-white truncate">{g.torneo}</h2>
                    </div>
                    {g.anni.map(a => (
                        <div key={a.anno} className="space-y-2 pl-1">
                            <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-bold">
                                {a.anno > 0 ? a.anno : '—'}
                            </div>
                            <div className="space-y-2 ds-v2-mr-griglia">
                                {a.items.map(it => (
                                    <Card key={it.event_id} onClick={() => onSelect(it)} role="button" tabIndex={0}
                                        onKeyDown={e => { if (e.key === 'Enter') onSelect(it); }}
                                        data-testid={`tennis-replay-partita-${it.event_id}`}
                                        className="glass-card border-white/10 p-4 cursor-pointer transition-colors hover:bg-white/[0.04] ds-v2-mr-carta">
                                        <div className="flex items-center justify-between gap-3">
                                            <div className="min-w-0">
                                                <div className="flex items-center gap-2 mt-0.5">
                                                    <span className="text-emerald-400 font-bold truncate">{it.player1_name || '—'}</span>
                                                    <span className="text-white/30 text-xs">vs</span>
                                                    <span className="text-amber-400 font-bold truncate">{it.player2_name || '—'}</span>
                                                </div>
                                                <div className="text-[11px] text-muted-foreground mt-1 flex items-center gap-2">
                                                    {dataOra(it.open_date)}
                                                    <Badge variant="outline" className="border-white/15 text-white/50 text-[9px] px-1.5 py-0">
                                                        {it.fonte === 'runner' ? 'registrata dal runner' : 'importata'}
                                                    </Badge>
                                                </div>
                                            </div>
                                            <div className="text-right shrink-0">
                                                <div className="text-sm font-bold tabular-nums text-white">{it.n_markets ?? 0} mercati</div>
                                                <div className="text-[11px] text-muted-foreground tabular-nums">
                                                    {it.n_snapshots ?? 0} snapshot · {it.n_score ?? 0} punti
                                                </div>
                                            </div>
                                        </div>
                                    </Card>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            ))}
        </div>
    );
}

export default TennisReplayList;
