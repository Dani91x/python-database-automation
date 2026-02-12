import { motion } from 'framer-motion';
import { Check, Sparkles } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

const features = [
    "Accesso completo alla dashboard",
    "Tutti i pronostici disponibili",
    "Aggiornamenti in tempo reale",
    "Analisi AI avanzata",
    "Nessuna carta di credito richiesta",
];

export function PricingCard() {
    const scrollToAuth = () => {
        document.getElementById('auth')?.scrollIntoView({ behavior: 'smooth' });
    };

    return (
        <section className="py-24 relative">
            <div className="container mx-auto px-6 flex justify-center">
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.5 }}
                    className="glass-card neon-glow p-10 rounded-[2rem] max-w-md w-full text-center relative overflow-hidden"
                >
                    {/* Glow decorativo */}
                    <div className="absolute -top-20 left-1/2 -translate-x-1/2 w-60 h-60 bg-neon-cyan/10 blur-[100px] rounded-full pointer-events-none" />

                    <Badge className="bg-neon-cyan/20 text-neon-cyan hover:bg-neon-cyan/30 border-neon-cyan/30 mb-6 text-[10px] font-black uppercase tracking-widest">
                        <Sparkles className="w-3 h-3 mr-1" />
                        Prova Gratuita
                    </Badge>

                    <div className="mb-2">
                        <span className="stat-value text-5xl text-white">€0</span>
                        <span className="stat-label ml-2 text-base">per 7 giorni</span>
                    </div>
                    <p className="text-muted-foreground text-sm mb-8">
                        Poi €XX.XX/mese
                    </p>

                    <ul className="space-y-3 mb-10 text-left">
                        {features.map((feat, i) => (
                            <li key={i} className="flex items-center gap-3 text-sm text-white/80">
                                <div className="w-5 h-5 rounded-full bg-green-500/20 flex items-center justify-center shrink-0">
                                    <Check className="w-3 h-3 text-green-400" />
                                </div>
                                {feat}
                            </li>
                        ))}
                    </ul>

                    <Button
                        size="lg"
                        onClick={scrollToAuth}
                        className="w-full bg-neon-cyan text-black font-black uppercase tracking-wider hover:bg-white transition-all neon-glow"
                        aria-label="Registrati per la prova gratuita"
                    >
                        Registrati Ora
                    </Button>
                </motion.div>
            </div>
        </section>
    );
}
