export function CardsByMinute({ cards }: { cards: any }) {
    // Implementazione semplificata per brevità, espandibile
    const yellow = cards.yellow;

    // Convert to array
    const data = Object.entries(yellow)
        .filter(([_, val]: any) => val.total !== null)
        .map(([range, val]: any) => ({
            range,
            count: val.total || 0,
            pct: val.percentage
        }));

    return (
        <div className="glass-card p-6 rounded-xl">
            <h4 className="text-xs font-rajdhani font-bold uppercase tracking-widest text-muted-foreground mb-4">Cartellini Gialli</h4>
            <div className="grid grid-cols-4 gap-2">
                {data.map((item: any, i: number) => (
                    <div key={i} className="text-center bg-white/5 rounded p-2">
                        <div className="text-[10px] text-gray-500">{item.range}</div>
                        <div className="font-bold text-yellow-500">{item.count}</div>
                    </div>
                ))}
            </div>
        </div>
    );
}
