// ============================================================================
// LiveMatchCard — riga (card) di una partita seguita dallo stream Betfair.
// Mostra lega, "Home X - Y Away" (score live), badge minuto, badge status,
// label fonte score. Cliccabile → apre il dettaglio realtime nella stessa pagina.
// ============================================================================
import { Card } from '@/components/ui/card';
import { Radio } from 'lucide-react';
import { LIVE_STATUS_LABEL, type LiveFollow, type LiveFollowStatus } from '@/lib/live';

// Stile del badge di stato (PENDING grigio / STREAMING verde pulse /
// CLOSED ambra / UPLOADED ambra / ERROR rosso).
function statusBadgeCls(status: LiveFollowStatus): string {
    switch (status) {
        case 'STREAMING': return 'bg-primary/15 text-primary border-primary/40 animate-pulse-subtle';
        case 'CLOSED':
        case 'UPLOADED': return 'bg-secondary/15 text-secondary border-secondary/40';
        case 'ERROR': return 'bg-red-500/15 text-red-300 border-red-500/40';
        case 'PENDING':
        default: return 'bg-white/5 text-muted-foreground border-white/10';
    }
}

export function LiveMatchCard({ follow, selected, onClick }: {
    follow: LiveFollow; selected?: boolean; onClick?: () => void;
}) {
    const sh = follow.score_home ?? 0;
    const sa = follow.score_away ?? 0;
    const hasScore = follow.score_home != null || follow.score_away != null;
    return (
        <Card
            onClick={onClick}
            className={`glass-card border-white/10 p-4 cursor-pointer transition-colors hover:bg-white/[0.04] ${
                selected ? 'ring-1 ring-primary/60 border-primary/40' : ''
            }`}
        >
            <div className="flex items-center justify-between gap-3 mb-2">
                <span className="text-[11px] uppercase tracking-wider text-muted-foreground truncate">
                    {follow.league_name ?? 'Lega sconosciuta'}
                </span>
                <span className="shrink-0 inline-flex items-center gap-1">
                    {/* 25/09 AUTO-FOLLOW: origine del follow (manuale = "Segui live"
                        dell'utente; auto = il runner la segue da solo per i bot) */}
                    <span
                        data-testid="origine-follow"
                        title={follow.origine === 'auto'
                            ? 'Seguita DA SOLA dal runner per i bot (solo stream e ordini): "Segui live" per il terminale completo'
                            : 'Seguita a mano ("Segui live")'}
                        className={`inline-flex items-center px-2 py-0.5 rounded-md border text-[10px] font-bold uppercase ${
                            follow.origine === 'auto'
                                ? 'bg-sky-500/15 text-sky-300 border-sky-500/40'
                                : 'bg-white/5 text-muted-foreground border-white/10'}`}
                    >
                        {follow.origine === 'auto' ? 'auto' : 'manuale'}
                    </span>
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[10px] font-bold uppercase ${statusBadgeCls(follow.status)}`}>
                        {follow.status === 'STREAMING' && <Radio className="w-3 h-3" />}
                        {LIVE_STATUS_LABEL[follow.status]}
                    </span>
                </span>
            </div>

            <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                    <span className="text-emerald-400 font-bold truncate">{follow.home_name}</span>
                    <span className="font-display font-black tabular-nums text-white px-2">
                        {hasScore ? `${sh} - ${sa}` : 'vs'}
                    </span>
                    <span className="text-amber-400 font-bold truncate">{follow.away_name}</span>
                </div>
                {follow.inplay && follow.minute != null && (
                    <span className="shrink-0 inline-flex items-center px-2 py-0.5 rounded-md bg-primary/15 text-primary border border-primary/40 text-[11px] font-bold tabular-nums">
                        {follow.minute}'
                    </span>
                )}
            </div>

            <div className="flex items-center justify-between gap-3 mt-2 text-[10px] text-muted-foreground">
                <span>{follow.live_status ?? (follow.inplay ? 'In gioco' : 'Pre-match')}</span>
                {follow.score_source && <span className="opacity-70">fonte: {follow.score_source}</span>}
            </div>

            {follow.status === 'ERROR' && follow.error_detail && (
                <div className="mt-2 text-[10px] text-red-300/80 truncate">{follow.error_detail}</div>
            )}
        </Card>
    );
}
