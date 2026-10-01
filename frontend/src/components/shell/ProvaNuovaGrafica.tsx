// ============================================================================
// «Prova la nuova grafica» — l'unico elemento che l'app ATTUALE (ui.shell='off')
// riceve dal redesign: un piccolo bottone fisso in basso a destra, nello stesso
// punto in ogni pagina interna, che accende il guscio v2 con un clic.
// Fisso e fuori dalle pagine: nessuna testata di oggi viene toccata. Non compare
// sulle pagine pubbliche (accesso, conferma email, reimposta password, 404) ne'
// nella finestra pop-out del ladder. In basso a destra non c'e' altro: i toast
// dell'app stanno in alto al centro (components/ui/sonner.tsx).
// ============================================================================
import { useLocation } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { cambiaUiShell } from '@/lib/uiShell';
import { ROTTE_NEL_GUSCIO } from './navigazione';

export function ProvaNuovaGrafica() {
    const { pathname } = useLocation();
    if (!ROTTE_NEL_GUSCIO.includes(pathname)) return null;
    return (
        <div data-shell-chrome className="fixed bottom-3 right-3 z-40">
            <button
                type="button"
                data-testid="shell-prova-nuova-grafica"
                title="Prova la nuova grafica (stesse pagine, cornice nuova; si torna indietro con un clic)"
                onClick={() => cambiaUiShell('v2')}
                className="flex items-center gap-1.5 rounded-full border border-white/10 bg-black/70 px-2.5 py-1 text-[10.5px] font-semibold text-muted-foreground opacity-70 backdrop-blur hover:border-primary/50 hover:text-primary hover:opacity-100"
            >
                <Sparkles className="h-3 w-3" aria-hidden="true" />
                Prova la nuova grafica
            </button>
        </div>
    );
}

export default ProvaNuovaGrafica;
