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
        <div className="bg-black/20 p-4 rounded-xl border border-white/5">
            <h4 className="text-[10px] font-black uppercase tracking-widest text-white/40 mb-3">League Form</h4>
            <div className="flex flex-col gap-3">
                <div className="flex gap-1.5 flex-wrap">
                    {lastMatches.map((char, i) => {
                        const dotClass =
                            char === 'W' ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]" :
                                char === 'D' ? "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)]" :
                                    char === 'L' ? "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]" :
                                        "bg-white/10";

                        return (
                            <div
                                key={i}
                                className={cn(
                                    "w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-black text-black/80",
                                    dotClass
                                )}
                            >
                                {char}
                            </div>
                        );
                    })}
                </div>

                <div className="text-[10px] font-bold text-white/50 uppercase tracking-wider">
                    Last {lastMatches.length} matches •
                    <span className="text-emerald-400 ml-1">{counts.W}W</span>
                    <span className="text-amber-400 ml-1">{counts.D}D</span>
                    <span className="text-red-400 ml-1">{counts.L}L</span>
                </div>
            </div>
        </div>
    );
}
