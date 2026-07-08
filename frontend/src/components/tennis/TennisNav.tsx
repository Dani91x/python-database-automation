import { Button } from '@/components/ui/button';
import {
    LogOut,
    BarChart3,
    Bookmark,
    Wallet,
    LayoutGrid,
    Activity,
    ChevronLeft,
} from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';

/**
 * Barra di navigazione condivisa per la sezione Tennis.
 *
 * Replica 1:1 lo stile della navbar Football (Dashboard.tsx): stesso container,
 * stesso brand "AI TERMINAL", stessi bottoni outline con accenti verde/oro, stesso
 * logout ghost/rosso. Aggiunge il bottone "Cambia sport" verso lo Sport Selector.
 *
 * Volutamente NON estratta come navbar globale unica (il resto dell'app duplica la
 * nav inline): resta locale alla sezione Tennis per non toccare le pagine Football.
 */
export interface TennisNavProps {
    /** Etichetta di sezione mostrata accanto al brand (es. "TENNIS", "TERMINAL"). */
    sectionLabel?: string;
    /** Se presente, mostra un bottone "indietro" a sinistra con questa azione. */
    onBack?: () => void;
    /** Testo del bottone indietro (default "Torna alle partite"). */
    backLabel?: string;
}

export function TennisNav({ sectionLabel = 'TENNIS', onBack, backLabel = 'Torna alle partite' }: TennisNavProps) {
    const { user } = useAuth();
    const navigate = useNavigate();

    const handleLogout = async () => {
        await supabase.auth.signOut();
        navigate('/');
    };

    return (
        <nav
            className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50"
            role="navigation"
            aria-label="Tennis navigation"
        >
            <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <div
                        className="font-display font-black text-xl tracking-tighter cursor-pointer"
                        onClick={() => navigate('/tennis')}
                    >
                        AI <span className="text-primary">TERMINAL</span>
                    </div>
                    {sectionLabel && (
                        <span className="hidden md:inline-flex items-center gap-2 text-sm font-heading font-bold text-primary/80 uppercase tracking-wide">
                            <Activity className="w-4 h-4" />
                            {sectionLabel}
                        </span>
                    )}
                    {onBack && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onBack}
                            className="hidden md:flex items-center gap-2 border-white/10 text-muted-foreground hover:text-white ml-4"
                        >
                            <ChevronLeft className="w-4 h-4" />
                            {backLabel}
                        </Button>
                    )}
                </div>

                <div className="flex items-center gap-3">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate('/select-sport')}
                        className="border-secondary/30 text-secondary hover:bg-secondary/10"
                        aria-label="Cambia sport"
                    >
                        <LayoutGrid className="w-4 h-4 md:mr-2" />
                        <span className="hidden md:inline">Cambia sport</span>
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate('/watchlist')}
                        className="border-amber-400/30 text-amber-300 hover:bg-amber-400/10"
                        aria-label="Watchlist"
                    >
                        <Bookmark className="w-4 h-4 md:mr-2" />
                        <span className="hidden md:inline">Watchlist</span>
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate('/report-personale')}
                        className="border-primary/30 text-primary hover:bg-primary/10"
                        aria-label="Report Personale"
                    >
                        <Wallet className="w-4 h-4 md:mr-2" />
                        <span className="hidden md:inline">Report</span>
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate('/analytics')}
                        className="border-primary/30 text-primary hover:bg-primary/10"
                        aria-label="Analytics"
                    >
                        <BarChart3 className="w-4 h-4 md:mr-2" />
                        <span className="hidden md:inline">Analytics</span>
                    </Button>
                    <span className="text-xs text-muted-foreground hidden lg:inline-block">
                        {user?.email}
                    </span>
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleLogout}
                        className="hover:bg-red-500/10 hover:text-red-500"
                        aria-label="Logout"
                    >
                        <LogOut className="w-4 h-4 mr-2" />
                        Esci
                    </Button>
                </div>
            </div>
        </nav>
    );
}
