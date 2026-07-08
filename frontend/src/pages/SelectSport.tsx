import { Helmet } from 'react-helmet-async';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/hooks/useAuth';
import { supabase } from '@/integrations/supabase/client';
import { LogOut, ArrowRight } from 'lucide-react';

/**
 * SCREEN 1 — Sport Selector.
 *
 * Landing post-login: due scelte grandi e centrali (Football / Tennis), in stile
 * "AI TERMINAL" (dark, glow verde, tipografia bold Sora). Football → dashboard
 * calcio esistente (invariata). Tennis → nuova sezione Tennis.
 */

interface SportChoice {
    key: 'football' | 'tennis';
    emoji: string;
    title: string;
    subtitle: string;
    to: string;
    /** classi accento: verde (primary) per football, oro (secondary) per tennis */
    accent: 'primary' | 'secondary';
    available: boolean;
}

const CHOICES: SportChoice[] = [
    {
        key: 'football',
        emoji: '⚽',
        title: 'Football',
        subtitle: 'Partite del Giorno · motori AI · trading live',
        to: '/dashboard',
        accent: 'primary',
        available: true,
    },
    {
        key: 'tennis',
        emoji: '🎾',
        title: 'Tennis',
        subtitle: 'Betfair Exchange · ladder pro · bot trading',
        to: '/tennis',
        accent: 'secondary',
        available: true,
    },
];

export default function SelectSport() {
    const navigate = useNavigate();
    const { user } = useAuth();

    const handleLogout = async () => {
        await supabase.auth.signOut();
        navigate('/');
    };

    return (
        <div className="min-h-screen bg-background relative flex flex-col">
            <Helmet>
                <title>Scegli lo Sport | Alpha Score</title>
            </Helmet>

            {/* Grid pattern backdrop */}
            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            {/* Minimal top bar */}
            <nav className="border-b border-white/5 bg-black/50 backdrop-blur-xl sticky top-0 z-50">
                <div className="container mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="font-display font-black text-xl tracking-tighter">
                        AI <span className="text-primary">TERMINAL</span>
                    </div>
                    <div className="flex items-center gap-4">
                        <span className="text-xs text-muted-foreground hidden md:inline-block">{user?.email}</span>
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

            <main className="flex-1 container mx-auto px-4 lg:px-6 relative z-10 flex flex-col items-center justify-center py-16">
                <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                    className="text-center mb-12"
                >
                    <h1 className="text-3xl md:text-5xl font-display font-black tracking-tight text-white">
                        Scegli lo <span className="text-primary">sport</span>
                    </h1>
                    <p className="mt-3 text-sm md:text-base text-muted-foreground font-sans">
                        Seleziona il terminale operativo su cui vuoi lavorare.
                    </p>
                </motion.div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-8 w-full max-w-3xl">
                    {CHOICES.map((c, i) => (
                        <motion.button
                            key={c.key}
                            type="button"
                            disabled={!c.available}
                            onClick={() => c.available && navigate(c.to)}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.45, delay: 0.1 + i * 0.1 }}
                            whileHover={c.available ? { y: -6 } : undefined}
                            whileTap={c.available ? { scale: 0.98 } : undefined}
                            className={[
                                'group relative overflow-hidden rounded-2xl glass-card animated-border p-8 md:p-10 text-left',
                                'flex flex-col items-start gap-4 min-h-[240px] transition-all',
                                c.available ? 'cursor-pointer hover:border-white/20' : 'opacity-40 cursor-not-allowed',
                                c.accent === 'primary'
                                    ? 'hover:neon-glow-primary'
                                    : 'hover:neon-glow-gold',
                            ].join(' ')}
                            aria-label={`Apri sezione ${c.title}`}
                        >
                            <div
                                className={[
                                    'w-20 h-20 rounded-2xl flex items-center justify-center text-5xl',
                                    'bg-black/40 border',
                                    c.accent === 'primary' ? 'border-primary/30' : 'border-secondary/30',
                                ].join(' ')}
                                aria-hidden
                            >
                                {c.emoji}
                            </div>

                            <div className="flex-1">
                                <h2
                                    className={[
                                        'font-display font-black text-3xl md:text-4xl tracking-tight',
                                        c.accent === 'primary' ? 'text-primary' : 'text-secondary',
                                    ].join(' ')}
                                >
                                    {c.title}
                                </h2>
                                <p className="mt-2 text-sm text-muted-foreground font-sans">{c.subtitle}</p>
                            </div>

                            <span
                                className={[
                                    'inline-flex items-center gap-2 text-sm font-heading font-bold uppercase tracking-wide',
                                    c.accent === 'primary' ? 'text-primary' : 'text-secondary',
                                ].join(' ')}
                            >
                                Entra
                                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                            </span>
                        </motion.button>
                    ))}
                </div>
            </main>

            <footer className="border-t border-white/5 py-6 text-center text-xs text-muted-foreground relative z-10">
                <p>&copy; {new Date().getFullYear()} Alpha Score AI. All rights reserved.</p>
            </footer>
        </div>
    );
}
