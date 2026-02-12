import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Trophy, Target, BarChart3, Zap } from 'lucide-react';

function AnimatedCounter({ target, suffix = '' }: { target: number; suffix?: string }) {
    const [count, setCount] = useState(0);
    const ref = useRef<HTMLDivElement>(null);
    const hasAnimated = useRef(false);

    useEffect(() => {
        const observer = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting && !hasAnimated.current) {
                    hasAnimated.current = true;
                    const duration = 1500;
                    const start = Date.now();
                    const step = () => {
                        const elapsed = Date.now() - start;
                        const pct = Math.min(elapsed / duration, 1);
                        const eased = 1 - Math.pow(1 - pct, 3); // ease-out cubic
                        setCount(Math.floor(eased * target));
                        if (pct < 1) requestAnimationFrame(step);
                    };
                    requestAnimationFrame(step);
                }
            },
            { threshold: 0.3 }
        );

        if (ref.current) observer.observe(ref.current);
        return () => observer.disconnect();
    }, [target]);

    return (
        <div ref={ref} className="stat-value text-2xl md:text-3xl text-white">
            {count.toLocaleString('it-IT')}{suffix}
        </div>
    );
}

export function StatsBar() {
    const stats: Array<{ label: string; icon: typeof Trophy; target?: number; suffix?: string; val?: string }> = [
        { label: 'Pronostici Generati', target: 50000, suffix: '+', icon: BarChart3 },
        { label: 'Accuratezza Media', target: 87, suffix: '%', icon: Target },
        { label: 'Campionati Analizzati', target: 120, suffix: '+', icon: Trophy },
        { label: 'Aggiornamento Dati', val: 'Real-Time', icon: Zap },
    ];

    return (
        <div className="container mx-auto px-6 mb-24">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-5xl mx-auto">
                {stats.map((stat, i) => (
                    <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.4, delay: i * 0.1 }}
                        className="glass-card p-6 rounded-3xl text-center hover:scale-105 transition-transform duration-300"
                    >
                        <stat.icon className="w-5 h-5 mx-auto mb-3 text-brand-orange opacity-50" />
                        {stat.target != null ? (
                            <AnimatedCounter target={stat.target} suffix={stat.suffix ?? ''} />
                        ) : (
                            <div className="stat-value text-2xl md:text-3xl text-white">{stat.val}</div>
                        )}
                        <div className="stat-label mt-1">{stat.label}</div>
                    </motion.div>
                ))}
            </div>
            <p className="text-center text-[10px] text-muted-foreground uppercase tracking-widest mt-6 opacity-50">
                * Dati dimostrativi basati su backtest storici
            </p>
        </div>
    );
}
