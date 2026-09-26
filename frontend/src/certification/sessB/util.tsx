// util.tsx — base + i provider globali di App.tsx (QueryClient, Helmet, Tooltip, Router), come in produzione.
import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HelmetProvider } from 'react-helmet-async';
import { MemoryRouter } from 'react-router-dom';
import { TooltipProvider } from '@/components/ui/tooltip';
export * from './util_base';

export function App({ path, children }: { path: string; children: ReactElement }) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return (
        <QueryClientProvider client={qc}>
            <HelmetProvider>
                <TooltipProvider>
                    <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
                </TooltipProvider>
            </HelmetProvider>
        </QueryClientProvider>
    );
}
