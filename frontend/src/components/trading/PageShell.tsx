// ============================================================================
// PageShell.tsx — GUSCIO unico delle pagine di trading (Omega/Safe/Mike).
// Sfondo + grid pattern, <title>, contenitore con le stesse misure in tutte e
// tre le sezioni. L'header sticky va passato come `header` (fuori dal
// contenitore, così resta a tutta larghezza).
// ============================================================================
import type { ReactNode } from 'react';
import { Helmet } from 'react-helmet-async';

export function PageShell({ title, header, children, footer }: {
    /** titolo del documento (tab del browser) */
    title: string;
    /** header sticky (di norma <BotHeader/>) */
    header?: ReactNode;
    children: ReactNode;
    /** nota a piè di pagina (fonte dati, avvertenze) */
    footer?: ReactNode;
}) {
    return (
        <div className="min-h-screen bg-background text-foreground relative pb-16" data-testid="page-shell">
            <Helmet><title>{title}</title></Helmet>
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />
            {header}
            <main className="container mx-auto px-4 lg:px-6 py-5 relative z-10 max-w-7xl space-y-5">
                {children}
                {footer && (
                    <p className="text-[11px] text-muted-foreground pt-2" data-testid="page-footer">{footer}</p>
                )}
            </main>
        </div>
    );
}

export default PageShell;
