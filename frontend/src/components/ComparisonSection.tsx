"use client";

import { motion } from "framer-motion";

interface ComparisonBarProps {
    label: string;
    homeValue: string;
    homePercent: number;
    awayValue: string;
    awayPercent: number;
}

const ComparisonBar = ({ label, homeValue, homePercent, awayValue, awayPercent }: ComparisonBarProps) => (
    <div className="space-y-2">
        <div className="flex justify-between text-[10px] font-black uppercase tracking-widest text-gray-400">
            <span>{homeValue}</span>
            <span className="text-white">{label}</span>
            <span>{awayValue}</span>
        </div>
        <div className="h-2 flex gap-1 rounded-full overflow-hidden bg-white/5 p-0.5 border border-white/5">
            <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${homePercent}%` }}
                className="h-full bg-brand-orange rounded-full"
            />
            <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${awayPercent}%` }}
                className="h-full bg-white/40 rounded-full ml-auto"
            />
        </div>
    </div>
);

export const ComparisonSection = ({ comparison }: { comparison: any }) => {
    const parse = (val: string) => parseFloat((val || '0%').replace('%', '')) || 0;

    return (
        <div className="glass-panel p-6 rounded-3xl space-y-6 border-brand-orange/10">
            <h3 className="text-xs font-black uppercase tracking-[0.2em] text-brand-orange mb-4">
                Deep Comparison
            </h3>
            <div className="grid gap-6">
                <ComparisonBar
                    label="Forma"
                    homeValue={comparison?.form?.home || '0%'}
                    homePercent={parse(comparison?.form?.home)}
                    awayValue={comparison?.form?.away || '0%'}
                    awayPercent={parse(comparison?.form?.away)}
                />
                <ComparisonBar
                    label="Attacco"
                    homeValue={comparison?.att?.home || '0%'}
                    homePercent={parse(comparison?.att?.home)}
                    awayValue={comparison?.att?.away || '0%'}
                    awayPercent={parse(comparison?.att?.away)}
                />
                <ComparisonBar
                    label="Difesa"
                    homeValue={comparison?.def?.home || '0%'}
                    homePercent={parse(comparison?.def?.home)}
                    awayValue={comparison?.def?.away || '0%'}
                    awayPercent={parse(comparison?.def?.away)}
                />
                <ComparisonBar
                    label="Poisson"
                    homeValue={comparison?.poisson_distribution?.home || '0%'}
                    homePercent={parse(comparison?.poisson_distribution?.home)}
                    awayValue={comparison?.poisson_distribution?.away || '0%'}
                    awayPercent={parse(comparison?.poisson_distribution?.away)}
                />
            </div>
        </div>
    );
};
