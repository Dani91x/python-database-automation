import { Brain, BarChart3, Shield, Zap } from 'lucide-react';

export function FeaturesGrid() {
    const features = [
        {
            title: 'Analisi AI Avanzata',
            desc: 'I nostri algoritmi analizzano oltre 200 variabili per partita: forma, H2H e distribuzione di Poisson.',
            icon: Brain
        },
        {
            title: 'Dati in Tempo Reale',
            desc: 'Aggiornamenti live da 120+ campionati. Goals by minute, heatmap cartellini e molto altro.',
            icon: BarChart3
        },
        {
            title: 'Confronto Intelligente',
            desc: 'Matrice comparativa automatica su attacco, difesa e forma con insight generati.',
            icon: Shield
        },
        {
            title: 'Velocità e Precisione',
            desc: 'Pronostici generati in millisecondi con percentuali 1X2 e value bets suggerite.',
            icon: Zap
        }
    ];

    return (
        <section className="py-24 relative">
            <div className="container mx-auto px-6">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    {features.map((item, i) => (
                        <div key={i} className="glass-card p-8 rounded-[2rem] hover:-translate-y-2 transition-transform duration-300 group">
                            <div className="w-12 h-12 rounded-2xl bg-brand-orange/10 flex items-center justify-center mb-6 group-hover:bg-brand-orange/20 transition-colors">
                                <item.icon className="w-6 h-6 text-brand-orange" />
                            </div>
                            <h3 className="font-rajdhani text-xl font-bold mb-3 text-white">{item.title}</h3>
                            <p className="text-sm text-muted-foreground leading-relaxed">
                                {item.desc}
                            </p>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}
