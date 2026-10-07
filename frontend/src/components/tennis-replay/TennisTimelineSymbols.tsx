// ============================================================================
// TennisTimelineSymbols — i SIMBOLI DEL TENNIS della barra del Replay Tennis.
//
// La barra e' la `TimelineSlider` del Match Replay (track, riempimento,
// sospensioni, cursore, trascinamento). Dal 07/10 (FASE 2) la barra accetta per
// parametro le icone, la legenda e il titolo del marker d'inizio: i simboli del
// tennis stanno DENTRO la barra, alle posizioni del verificatore (indice del
// passo / ultimo indice), con il testid comune `barra-simbolo` e `data-kind` = tipo.
// Qui ci sono l'icona di ogni tipo, la legenda e la conversione dei simboli nei
// marker della barra. Senza questi parametri la barra resta quella del calcio.
// ============================================================================
import { CircleDot, Flag, Play, Swords, Trophy, Unplug, Zap } from 'lucide-react';
import type { ComponentType } from 'react';
import type { TimelineEventMarker } from '@/components/replay/TimelineSlider';
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

const eTipo = (k: string): k is TipoSimbolo => Object.prototype.hasOwnProperty.call(ICONA, k);

/** I simboli del tennis come marker della barra (kind = tipo del simbolo). */
export function markerTennis(simboli: ReadonlyArray<SimboloTennis>): TimelineEventMarker[] {
    return simboli.map(s => ({ pctLeft: s.pctLeft, kind: s.tipo, team: null, minute: null, label: s.label }));
}

/** Icona di un simbolo del tennis sulla barra (un kind sconosciuto: punto generico). */
export function iconaTennis(kind: string) {
    if (!eTipo(kind)) return <span className="block w-1.5 h-1.5 rounded-full bg-white/70" />;
    const { Icon, cls } = ICONA[kind];
    return <Icon className={`w-3.5 h-3.5 drop-shadow ${cls}`} strokeWidth={2.5} />;
}

/** Legenda dei simboli del tennis presenti e degli arbitraggi (rombi verdi della
 *  barra, stessa voce del calcio); nulla se non c'e' niente da spiegare. */
export function LegendaTennis({ simboli, arbitraggi = false }: { simboli: ReadonlyArray<SimboloTennis>; arbitraggi?: boolean }) {
    const presenti = ORDINE_LEGENDA.filter(t => simboli.some(s => s.tipo === t));
    if (presenti.length === 0 && !arbitraggi) return null;
    return (
        <div className="flex items-center flex-wrap gap-x-3 gap-y-1 mt-1 text-[10px] text-muted-foreground" data-testid="tennis-legenda-barra">
            {arbitraggi && (
                <span className="inline-flex items-center gap-1">
                    <span className="inline-block w-2 h-2 rotate-45 bg-emerald-400 border border-emerald-200/60" /> Arbitraggio
                </span>
            )}
            {presenti.map(t => {
                const { Icon, cls } = ICONA[t];
                return (
                    <span key={t} className="inline-flex items-center gap-1">
                        <Icon className={`w-3 h-3 ${cls}`} strokeWidth={2.5} /> {NOME_SIMBOLO[t]}
                    </span>
                );
            })}
        </div>
    );
}
