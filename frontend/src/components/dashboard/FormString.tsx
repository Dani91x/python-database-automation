import { cn } from "@/lib/utils";

export function FormString({ form }: { form: string }) {
    if (!form) return null;

    const lastMatches = form.split('');
    const counts = {
        W: (form.match(/W/g) || []).length,
        D: (form.match(/D/g) || []).length,
        L: (form.match(/L/g) || []).length,
    };

    return (
        <div className="bg-white/[0.02] backdrop-blur-md p-5 rounded-3xl border border-white/5 space-y-4">
            <div className="flex items-center justify-between">
                <h4 className="text-[11px] font-black uppercase tracking-widest text-white/40">League Form</h4>
                <div className="text-[10px] font-black text-white/20 uppercase tracking-widest tabular-nums">
                    Last {lastMatches.length}
                </div>
            </div>

            <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center justify-center gap-2">
                    {lastMatches.map((char, i) => {
                        const dotClass =
                            char === 'W' ? "bg-emerald-500 shadow-[0_0_12px_rgba(16,185,129,0.3)]" :
                                char === 'D' ? "bg-amber-500 shadow-[0_0_12px_rgba(245,158,11,0.3)]" :
                                    char === 'L' ? "bg-red-500 shadow-[0_0_12px_rgba(239,68,68,0.3)]" :
                                        "bg-white/10";

                        return (
                            <div
                                key={i}
                                className={cn(
                                    "w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-black text-black transition-transform hover:scale-110",
                                    dotClass
                                )}
                            >
                                {char}
                            </div>
                        );
                    })}
                </div>

                <div className="flex gap-3 px-3 py-1.5 bg-black/40 rounded-full border border-white/5">
                    <span className="text-[11px] font-black text-emerald-400">{counts.W}W</span>
                    <span className="text-[11px] font-black text-amber-400">{counts.D}D</span>
                    <span className="text-[11px] font-black text-red-400">{counts.L}L</span>
                </div>
            </div>
        </div>
    );
}
