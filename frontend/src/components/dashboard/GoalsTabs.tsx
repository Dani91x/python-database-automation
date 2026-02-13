import { TeamLeagueStats } from "@/lib/normalize";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { Card } from "@/components/ui/card";

export function GoalsTabs({ stats, side }: { stats: TeamLeagueStats; side: 'home' | 'away' }) {
    const barColor = side === 'home' ? 'hsl(155, 84%, 42%)' : 'hsl(45, 93%, 55%)';

    // Transform minute data for chart
    const minuteData = Object.entries(stats.goals.for.minute)
        .filter(([_, val]) => val.total !== null)
        .map(([range, val]) => ({
            range,
            count: val.total || 0
        }));

    return (
        <Card className="glass-card p-6 mb-4">
            <Tabs defaultValue="minutes">
                <TabsList className="w-full grid grid-cols-2 mb-4 bg-black/20">
                    <TabsTrigger value="minutes">Goal Minuti</TabsTrigger>
                    <TabsTrigger value="underover">Under/Over</TabsTrigger>
                </TabsList>

                <TabsContent value="minutes" className="h-[200px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={minuteData}>
                            <XAxis
                                dataKey="range"
                                stroke="#666"
                                fontSize={10}
                                tickLine={false}
                                axisLine={false}
                            />
                            <Tooltip
                                contentStyle={{ backgroundColor: '#111', border: '1px solid #333' }}
                                itemStyle={{ color: '#fff' }}
                                cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                            />
                            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                                {minuteData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={barColor} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </TabsContent>

                <TabsContent value="underover">
                    <div className="space-y-2 text-sm">
                        {['0.5', '1.5', '2.5', '3.5', '4.5'].map(threshold => {
                            const data = stats.goals.for.under_over?.[threshold];
                            if (!data) return null;
                            const total = data.over + data.under;
                            const overPct = total ? (data.over / total) * 100 : 0;

                            return (
                                <div key={threshold} className="flex items-center gap-4">
                                    <span className="w-8 font-bold text-brand-orange">{threshold}</span>
                                    <div className="flex-1 h-2 bg-white/10 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-white transition-all"
                                            style={{ width: `${overPct}%`, backgroundColor: barColor }}
                                        />
                                    </div>
                                    <div className="w-12 text-right text-xs text-muted-foreground">{overPct.toFixed(0)}% O</div>
                                </div>
                            );
                        })}
                    </div>
                </TabsContent>
            </Tabs>
        </Card>
    );
}
