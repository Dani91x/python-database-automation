// ============================================================================
// TennisTimelineSymbols — i SIMBOLI DEL TENNIS lungo la barra del Replay Tennis.
//
// La barra (track, riempimento, sospensioni, cursore, trascinamento) e' la
// `TimelineSlider` del Match Replay, usata cosi' com'e': i suoi simboli sono
// quelli del calcio (gol, cartellini, angoli). Qui c'e' la fila dei simboli del
// tennis, allineata alla stessa larghezza e alle stesse posizioni (indice del
// passo / ultimo indice), con la sua legenda. Non intercetta il mouse: il
// trascinamento resta della barra sotto.
// ============================================================================
import { CircleDot, Flag, Play, Swords, Trophy, Unplug, Zap } from 'lucide-react';
import type { ComponentType } from 'react';
import { NOME_SIMBOLO, type SimboloTennis, type TipoSimbolo } from '@/lib/tennisReplay';

const ICONA: Record<TipoSimbolo, { Icon: ComponentType<{ className?: string; strokeWidth?: number }>; cls: string }> = {
    inplay: { Icon: Play, cls: 'text-emerald-300 fill-emerald-300/30' },
    set_start: { Icon: Flag, cls: 'text-sky-300 fill-sky-300/20' },
    break: { Icon: Zap, cls: 'text-amber-300 fill-amber-300/30' },
    tiebreak: { Icon: Swords, cls: 'text-violet-300' },
    set_end: { Icon: CircleDot, cls: 'text-primary' },
    match_end: { Icon: Trophy, cls: 'text-secondary fill-secondary/30' },
    salto: { Icon: Unplug, cls: 'text-red-300' },
};

const ORDINE_LEGENDA: TipoSimbolo[] = ['inplay', 'set_start', 'break', 'tiebreak', 'set_end', 'match_end', 'salto'];

export function TennisTimelineSymbols({ simboli }: { simboli: ReadonlyArray<SimboloTennis> }) {
    const presenti = ORDINE_LEGENDA.filter(t => simboli.some(s => s.tipo === t));
    return (
        <div className="select-none" data-testid="tennis-simboli-barra">
            <div className="relative w-full h-4">
                {simboli.map((s, i) => {
                    const { Icon, cls } = ICONA[s.tipo];
                    return (
                        <div
                            key={`${s.tipo}-${s.ts}-${i}`}
                            className="absolute top-0 -translate-x-1/2 flex items-center justify-center pointer-events-none"
                            style={{ left: `${Math.min(Math.max(s.pctLeft, 0), 1) * 100}%` }}
                            title={s.label}
                            data-tipo={s.tipo}
                        >
                            <Icon className={`w-3.5 h-3.5 drop-shadow ${cls}`} strokeWidth={2.5} />
                        </div>
                    );
                })}
            </div>
            {presenti.length > 0 && (
                <div className="flex items-center flex-wrap gap-x-3 gap-y-1 mb-1 text-[10px] text-muted-foreground">
                    {presenti.map(t => {
                        const { Icon, cls } = ICONA[t];
                        return (
                            <span key={t} className="inline-flex items-center gap-1">
                                <Icon className={`w-3 h-3 ${cls}`} strokeWidth={2.5} /> {NOME_SIMBOLO[t]}
                            </span>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

export default TennisTimelineSymbols;
