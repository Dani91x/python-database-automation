import { Trophy, Activity, Brain, Zap } from 'lucide-react';

export function StatsBar() {
    const stats = [
        { label: 'Pronostici Generati', val: '50.000+', icon: Activity },
        { label: 'Accuratezza Media', val: '87%', icon: Zap },
        { label: 'Campionati Analizzati', val: '120+', icon: Trophy },
        { label: 'ML Accuracy', val: 'High', icon: Brain }
    ];

    return (
        <div className="container mx-auto px-6 mb-24">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-5xl mx-auto">
                {stats.map((stat, i) => (
                    <div key={i} className="glass-card p-6 rounded-3xl text-center hover:scale-105 transition-transform duration-300">
                        <stat.icon className="w-5 h-5 mx-auto mb-3 text-brand-orange opacity-50" />
                        <div className="stat-value text-2xl md:text-3xl text-white">{stat.val}</div>
                        <div className="stat-label mt-1">{stat.label}</div>
                    </div>
                ))}
            </div>
            <p className="text-center text-[10px] text-muted-foreground uppercase tracking-widest mt-6 opacity-50">
                * Dati dimostrativi basati su backtest storici
            </p>
        </div>
    );
}
