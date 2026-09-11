// ============================================================================
// EmptyState.tsx / LoadingState.tsx / SectionCard.tsx — primitive di layout
// condivise: un solo box vuoto tratteggiato, un solo stato di caricamento, una
// sola card con intestazione per tabelle e liste.
// ============================================================================
import type { ReactNode } from 'react';
import { Activity } from 'lucide-react';
import { Card } from '@/components/ui/card';

/** Box "niente da mostrare": bordo tratteggiato, testo che dice COSA aspettarsi. */
export function EmptyState({ children, testId = 'empty-state' }: { children: ReactNode; testId?: string }) {
    return (
        <div
            className="glass-card rounded-xl border border-dashed border-white/10 p-6 text-center text-sm text-muted-foreground"
            data-testid={testId}
        >
            {children}
        </div>
    );
}

/** Caricamento: spinner + testo, mai una pagina bianca. */
export function LoadingState({ label = 'caricamento…', testId = 'loading-state' }: { label?: string; testId?: string }) {
    return (
        <div className="text-center text-muted-foreground py-24" data-testid={testId}>
            <Activity className="w-6 h-6 animate-spin mx-auto mb-3 text-primary" aria-hidden />
            {label}
        </div>
    );
}

/**
 * Card con intestazione: icona + titolo + contatore + nota + azioni.
 * Usata per tabelle e liste (partite, trade, attività): il contenuto scorre
 * dentro, l'intestazione resta identica fra le sezioni.
 */
export function SectionCard({ icon, title, count, note, actions, children, testId, className }: {
    icon?: ReactNode;
    title: ReactNode;
    count?: number | null;
    /** riepilogo/spiegazione a destra del titolo */
    note?: ReactNode;
    /** bottoni allineati a destra (toggle "mostra tutte", filtri…) */
    actions?: ReactNode;
    children: ReactNode;
    testId?: string;
    className?: string;
}) {
    return (
        <Card className={`glass-card border-white/10 p-0 overflow-hidden ${className ?? ''}`} data-testid={testId}>
            <div className="px-4 py-2.5 border-b border-white/5 flex items-center gap-2 text-sm text-slate-300 flex-wrap">
                {icon}
                <span>{title}{count != null ? ` (${count})` : ''}</span>
                {note && <span className="text-[11px] text-slate-500 tabular-nums">{note}</span>}
                {actions && <span className="ml-auto flex items-center gap-2">{actions}</span>}
            </div>
            {children}
        </Card>
    );
}

export default EmptyState;
