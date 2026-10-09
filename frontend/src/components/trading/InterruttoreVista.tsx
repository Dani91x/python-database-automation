// ============================================================================
// InterruttoreVista — il pulsante «nascondi / mostra» di una sezione.
//
// 09/10 (ordine dell'utente, Control Room). Lo stato lo tiene chi lo usa
// (`useVisibile` di lib/preferenzaVista, ricordato per viewer); qui solo il
// pulsante, con `aria-expanded` e le classi del design system.
// ============================================================================
import { Eye, EyeOff } from 'lucide-react';

export interface InterruttoreVistaProps {
    visibile: boolean;
    onCambia: (v: boolean) => void;
    /** cosa si nasconde, detto nel title: «la sezione AI Terminal» */
    cosa: string;
    testId?: string;
    className?: string;
}

export function InterruttoreVista({ visibile, onCambia, cosa, testId, className = '' }: InterruttoreVistaProps) {
    return (
        <button
            type="button"
            onClick={() => onCambia(!visibile)}
            aria-expanded={visibile}
            title={visibile ? `Nascondi ${cosa}` : `Mostra ${cosa}`}
            aria-label={visibile ? `Nascondi ${cosa}` : `Mostra ${cosa}`}
            data-testid={testId}
            className={`inline-flex items-center gap-1 h-6 px-2 rounded-md border border-white/10 text-[10px] uppercase tracking-wider text-white/55 hover:text-white hover:bg-white/[0.04] ds-v2-pulsante ds-v2-pulsante--sm ds-v2-pulsante--secondario ${className}`}
        >
            {visibile ? <EyeOff className="w-3 h-3" aria-hidden /> : <Eye className="w-3 h-3" aria-hidden />}
            {visibile ? 'Nascondi' : 'Mostra'}
        </button>
    );
}

export default InterruttoreVista;
