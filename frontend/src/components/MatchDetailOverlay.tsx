/* eslint-disable @typescript-eslint/no-explicit-any */
// frontend/src/components/MatchDetailOverlay.tsx
import { motion, AnimatePresence } from "framer-motion";
import { X, Cpu, Info } from "lucide-react";
import { HeroMatch } from "./dashboard/HeroMatch";
import { TeamPanel } from "./dashboard/TeamPanel";
import { ComparisonSection } from "./dashboard/ComparisonSection";
import { PredictionsCard } from "./dashboard/PredictionsCard";
import { H2HSection } from "./dashboard/H2HSection";

interface Props {
    isOpen: boolean;
    onClose: () => void;
    data: any;
}

export const MatchDetailOverlay = ({ isOpen, onClose, data }: Props) => {
    if (!data) return null;

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={onClose}
                        className="fixed inset-0 bg-black/90 backdrop-blur-md z-[100]"
                    />
                    <motion.div
                        initial={{ x: "100%" }}
                        animate={{ x: 0 }}
                        exit={{ x: "100%" }}
                        transition={{ type: "spring", damping: 30, stiffness: 200 }}
                        className="fixed right-0 top-0 bottom-0 w-full lg:max-w-7xl bg-zinc-950 border-l border-white/10 z-[101] overflow-y-auto selection:bg-brand-orange/30 shadow-[-20px_0_50px_rgba(0,0,0,0.5)]"
                    >
                        {/* Status Bar */}
                        <div className="bg-brand-orange px-6 py-1 flex items-center justify-between text-[10px] font-black uppercase tracking-[0.2em] text-black">
                            <div className="flex items-center gap-4">
                                <span className="flex items-center gap-1"><Cpu className="w-3 h-3" /> System Engine v4.2</span>
                                <span>Status: Analisi Completata</span>
                            </div>
                            <div className="hidden md:block">Session Token: {data.fixtureId ? data.fixtureId.toString().substring(0, 8).toUpperCase() : 'N/A'}</div>
                        </div>

                        {/* Sticky Header */}
                        <div className="sticky top-0 z-50 bg-zinc-950/80 backdrop-blur-xl border-b border-white/5 px-8 h-20 flex items-center justify-between">
                            <div className="flex flex-col">
                                <span className="text-[10px] font-black uppercase tracking-[0.3em] text-brand-orange leading-none mb-1">
                                    Report Deep Intelligence
                                </span>
                                <h2 className="text-2xl font-black uppercase tracking-tighter leading-none italic">
                                    {data.home.name} <span className="text-white/20">vs</span> {data.away.name}
                                </h2>
                            </div>
                            <button
                                onClick={onClose}
                                className="group w-12 h-12 rounded-full border border-white/10 flex items-center justify-center hover:bg-brand-orange hover:border-brand-orange transition-all"
                            >
                                <X className="w-6 h-6 group-hover:text-black transition-colors" />
                            </button>
                        </div>

                        <div className="pb-20">
                            {/* 1. Hero Summary */}
                            <HeroMatch
                                league={data.league}
                                home={data.home}
                                away={data.away}
                                predictions={data.predictions}
                                fixtureId={data.fixtureId}
                            />

                            {/* 2. Primary Prediction Advice */}
                            <PredictionsCard
                                predictions={data.predictions}
                                home={data.home}
                                away={data.away}
                            />

                            {/* 3. Deep Team Metrics (Two Columns) */}
                            <section className="container mx-auto px-4 py-12">
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12">
                                    <div className="space-y-6">
                                        <div className="flex items-center gap-4 mb-4">
                                            <div className="h-px flex-1 bg-white/5" />
                                            <span className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-500">Profilo Core Casa</span>
                                            <div className="h-px flex-1 bg-white/5" />
                                        </div>
                                        <TeamPanel team={data.home} side="home" />
                                    </div>
                                    <div className="space-y-6">
                                        <div className="flex items-center gap-4 mb-4">
                                            <div className="h-px flex-1 bg-white/5" />
                                            <span className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-500">Profilo Core Ospite</span>
                                            <div className="h-px flex-1 bg-white/5" />
                                        </div>
                                        <TeamPanel team={data.away} side="away" />
                                    </div>
                                </div>
                            </section>

                            {/* 4. Quantitative Comparison */}
                            <ComparisonSection
                                comparison={data.comparison}
                                home={data.home}
                                away={data.away}
                            />

                            {/* 5. Historical Trends */}
                            <H2HSection
                                h2h={data.h2h}
                                homeName={data.home.name}
                                awayName={data.away.name}
                            />

                            {/* Footer Info */}
                            <div className="container mx-auto px-4 mt-12">
                                <div className="p-8 bg-white/5 rounded-[2rem] border border-white/10 flex flex-col md:flex-row gap-6 items-center">
                                    <div className="w-12 h-12 rounded-2xl bg-brand-orange/10 flex items-center justify-center shrink-0">
                                        <Info className="w-6 h-6 text-brand-orange" />
                                    </div>
                                    <p className="text-xs font-bold text-gray-500 uppercase tracking-widest leading-loose text-center md:text-left">
                                        Disclaimer Analisi Neurale: Questo report è generato dal nostro algoritmo proprietario di Investimento Sportivo.
                                        Le performance passate non sono indicative dei risultati futuri. Una varianza statistica del +/- 4% è da prevedere.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
};
