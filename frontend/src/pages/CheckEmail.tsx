import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mail, ArrowLeft, RefreshCw, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function CheckEmail() {
    const navigate = useNavigate();

    return (
        <div className="min-h-screen bg-background flex items-center justify-center px-4">
            {/* Background effects */}
            <div className="fixed inset-0 grid-pattern opacity-20 pointer-events-none" />
            <div className="fixed inset-0 bg-gradient-hero pointer-events-none" />

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="relative z-10 w-full max-w-xl"
            >
                <div className="glass-card animated-border rounded-2xl p-10 md:p-14 text-center space-y-8">
                    {/* Animated Mail Icon */}
                    <div className="flex justify-center">
                        <div className="relative">
                            <div className="absolute inset-0 rounded-full bg-primary/20 animate-ping" style={{ animationDuration: '2s' }} />
                            <div className="relative w-24 h-24 rounded-full bg-primary/10 border-2 border-primary/30 flex items-center justify-center neon-glow-cyan">
                                <Mail className="w-12 h-12 text-primary" strokeWidth={1.5} />
                            </div>
                        </div>
                    </div>

                    {/* Title */}
                    <div className="space-y-3">
                        <h1 className="text-3xl md:text-4xl font-display font-bold text-foreground">
                            Controlla la tua email
                        </h1>
                        <p className="text-lg text-muted-foreground font-heading max-w-md mx-auto">
                            Ti abbiamo inviato un link di conferma. Clicca sul link per attivare il tuo account.
                        </p>
                    </div>

                    {/* Step-by-step instructions */}
                    <div className="grid gap-4 text-left max-w-md mx-auto">
                        {[
                            { n: 1, title: "Apri la tua casella di posta", desc: "Cerca l'email di conferma" },
                            { n: 2, title: 'Clicca su "Conferma Email"', desc: "Si aprirà una pagina di conferma" },
                            { n: 3, title: "Accedi alla Dashboard", desc: "Il tuo account è pronto!" },
                        ].map((step) => (
                            <div key={step.n} className="flex items-start gap-4 p-4 rounded-xl glass-card">
                                <span className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/20 text-primary font-bold flex items-center justify-center text-sm font-display">
                                    {step.n}
                                </span>
                                <div>
                                    <p className="font-heading font-bold text-foreground">{step.title}</p>
                                    <p className="text-sm text-muted-foreground">{step.desc}</p>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Spam warning */}
                    <div className="flex items-center gap-3 p-4 rounded-xl bg-accent/10 border border-accent/20 max-w-md mx-auto">
                        <AlertTriangle className="w-5 h-5 text-accent flex-shrink-0" />
                        <p className="text-sm text-muted-foreground text-left">
                            Non trovi l'email? Controlla la cartella <strong className="text-foreground">Spam</strong> o <strong className="text-foreground">Promozioni</strong>.
                        </p>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex flex-col sm:flex-row gap-4 justify-center pt-2">
                        <Button
                            variant="outline"
                            onClick={() => navigate('/')}
                            className="gap-2 border-border hover:bg-muted font-heading"
                        >
                            <ArrowLeft className="w-4 h-4" />
                            Torna alla Home
                        </Button>
                        <Button
                            onClick={() => navigate('/')}
                            className="gap-2 bg-primary text-primary-foreground hover:bg-primary/90 font-heading font-bold neon-glow-cyan"
                        >
                            <RefreshCw className="w-4 h-4" />
                            Non hai ricevuto l'email?
                        </Button>
                    </div>
                </div>
            </motion.div>
        </div>
    );
}
