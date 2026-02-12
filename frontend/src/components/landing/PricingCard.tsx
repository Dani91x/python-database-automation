import { motion } from "framer-motion";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const included = [
    "Accesso completo alla dashboard AI",
    "Pronostici illimitati",
    "Tutti i campionati",
    "Aggiornamenti in tempo reale",
    "Grafici e heatmap interattivi",
    "Supporto via Telegram",
];

interface PricingCardProps {
    onCtaClick: () => void;
}

export function PricingCard({ onCtaClick }: PricingCardProps) {
    return (
        <section className="py-20 px-4">
            <div className="max-w-lg mx-auto">
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.5 }}
                    className="glass-card neon-glow-cyan rounded-2xl p-8 md:p-10 text-center"
                >
                    <span className="home-badge mb-4 inline-block">PROVA GRATUITA</span>
                    <div className="stat-value text-5xl md:text-6xl mb-2">€0</div>
                    <p className="text-muted-foreground font-heading text-lg mb-8">per 7 giorni, poi €9.99/mese</p>

                    <ul className="space-y-3 text-left mb-8">
                        {included.map((item) => (
                            <li key={item} className="flex items-center gap-3">
                                <CheckCircle2 className="w-5 h-5 text-primary shrink-0" />
                                <span className="text-foreground font-heading">{item}</span>
                            </li>
                        ))}
                    </ul>

                    <Button
                        onClick={onCtaClick}
                        size="lg"
                        className="w-full text-lg py-6 font-heading font-bold pulse-glow neon-glow-cyan rounded-xl bg-primary text-primary-foreground hover:bg-primary/90"
                    >
                        Registrati Ora
                    </Button>
                </motion.div>
            </div>
        </section>
    );
}
