// ============================================================================
// PlaybackControls — barra di 7 pulsanti per il replay (icone lucide):
// skip-to-start · rewind · step-back · play/pause · step-forward · fast-forward
// · skip-to-end. Componente "dumb": emette solo eventi, lo stato vive nella pagina.
// ============================================================================
import {
    ChevronsLeft, Rewind, StepBack, Play, Pause, StepForward, FastForward, ChevronsRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

export interface PlaybackControlsProps {
    isPlaying: boolean;
    onSkipStart: () => void;
    onRewind: () => void;
    onStepBack: () => void;
    onTogglePlay: () => void;
    onStepForward: () => void;
    onFastForward: () => void;
    onSkipEnd: () => void;
}

export function PlaybackControls(p: PlaybackControlsProps) {
    const btn = 'border-white/10 text-muted-foreground hover:text-white h-9 w-9 p-0';
    return (
        <div className="flex items-center justify-center gap-1.5">
            <Button variant="outline" size="sm" className={btn} title="Inizio" onClick={p.onSkipStart}>
                <ChevronsLeft className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" className={btn} title="Riavvolgi" onClick={p.onRewind}>
                <Rewind className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" className={btn} title="Indietro" onClick={p.onStepBack}>
                <StepBack className="w-4 h-4" />
            </Button>
            <Button
                size="sm"
                className="bg-primary text-black hover:bg-primary/90 h-10 w-10 p-0"
                title={p.isPlaying ? 'Pausa' : 'Play'}
                onClick={p.onTogglePlay}
            >
                {p.isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
            </Button>
            <Button variant="outline" size="sm" className={btn} title="Avanti" onClick={p.onStepForward}>
                <StepForward className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" className={btn} title="Avanti veloce" onClick={p.onFastForward}>
                <FastForward className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="sm" className={btn} title="Fine" onClick={p.onSkipEnd}>
                <ChevronsRight className="w-4 h-4" />
            </Button>
        </div>
    );
}
