// frontend/src/components/dashboard/sub-components.tsx
import { TeamLast5, TeamLeagueStats, GoalsByMinute, UnderOver, CardsByMinute as CardsByMinuteType } from "@/lib/normalize";
import { Activity, Shield, Swords, Target, Trophy, Info, AlertCircle, TrendingUp } from "lucide-react";
import { Progress, Badge, Card, Tabs, TabsList, TabsTrigger, TabsContent, cn } from "@/components/ui/shadcn-mini";

// 1. FormString
export function FormString({ form, side }: { form: string; side: 'home' | 'away' }) {
    if (!form) return <Card className="p-4 text-gray-500 text-sm">N/D</Card>;
    const formArray = form.substring(0, 10).split('');
    return (
        <Card className="p-4 border-white/5">
            <h4 className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-3">League Form</h4>
            <div className="flex flex-wrap gap-1.5">
                {formArray.map((result, index) => (
                    <div key={index} className={cn(
                        "w-6 h-6 rounded flex items-center justify-center text-[10px] font-black",
                        result === 'W' ? "bg-brand-orange text-white" : result === 'D' ? "bg-white/10 text-white" : "bg-red-500/20 text-red-500"
                    )}>
                        {result}
                    </div>
                ))}
            </div>
        </Card>
    );
}

// 2. Last5Card
export function Last5Card({ last5, side }: { last5: TeamLast5; side: 'home' | 'away' }) {
    const isHome = side === 'home';
    const color = isHome ? "text-brand-orange" : "text-neon-cyan";
    const barColor = isHome ? "bg-brand-orange" : "bg-neon-cyan";

    return (
        <Card className="p-5 border-white/5">
            <h4 className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-4 flex items-center gap-2">
                <Activity className="w-3 h-3" /> Last 5 Performance
            </h4>
            <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="text-center">
                    <div className={cn("text-2xl font-black italic", color)}>{last5.form}</div>
                    <div className="text-[8px] font-black uppercase tracking-widest text-gray-500 mt-1">Form</div>
                    <Progress value={last5.formPercent} className="h-1 mt-2" barClassName={barColor} />
                </div>
                <div className="text-center">
                    <div className="text-2xl font-black italic text-white">{last5.att}</div>
                    <div className="text-[8px] font-black uppercase tracking-widest text-gray-500 mt-1">Att</div>
                    <Progress value={last5.attPercent} className="h-1 mt-2" barClassName="bg-white/40" />
                </div>
                <div className="text-center">
                    <div className="text-2xl font-black italic text-white">{last5.def}</div>
                    <div className="text-[8px] font-black uppercase tracking-widest text-gray-500 mt-1">Def</div>
                    <Progress value={last5.defPercent} className="h-1 mt-2" barClassName="bg-white/20" />
                </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-white/5 rounded-2xl border border-white/10">
                    <div className="flex justify-between items-center mb-1">
                        <span className="text-[9px] font-black uppercase text-gray-500">GF</span>
                        <span className="text-lg font-black text-brand-orange">{last5.goals.for.total}</span>
                    </div>
                    <div className="text-[8px] text-gray-600">AVG: {last5.goals.for.average.toFixed(2)}</div>
                </div>
                <div className="p-3 bg-white/5 rounded-2xl border border-white/10">
                    <div className="flex justify-between items-center mb-1">
                        <span className="text-[9px] font-black uppercase text-gray-500">GA</span>
                        <span className="text-lg font-black text-red-500">{last5.goals.against.total}</span>
                    </div>
                    <div className="text-[8px] text-gray-600">AVG: {last5.goals.against.average.toFixed(2)}</div>
                </div>
            </div>
        </Card>
    );
}

// 3. PenaltyCard
export function PenaltyCard({ penalty }: { penalty: any }) {
    if (!penalty) return null;
    return (
        <Card className="p-5 border-white/5">
            <h4 className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-4 flex items-center gap-2">
                <Target className="w-3 h-3" /> Penalty Accuracy
            </h4>
            <div className="flex items-center justify-between gap-4">
                <div className="flex-1">
                    <div className="flex justify-between text-[10px] font-black mb-1">
                        <span>Success Rate</span>
                        <span className="text-brand-orange">{penalty.scored.percentage}%</span>
                    </div>
                    <Progress value={penalty.scored.percentage} barClassName="bg-brand-orange" />
                </div>
                <div className="text-right">
                    <div className="text-xl font-black">{penalty.scored.total}/{penalty.total}</div>
                    <div className="text-[8px] text-gray-500 uppercase font-black tracking-widest">Scored</div>
                </div>
            </div>
        </Card>
    );
}

// 4. LineupsCard
export function LineupsCard({ lineups }: { lineups: Array<{ formation: string; played: number }> }) {
    if (!lineups?.length) return null;
    return (
        <Card className="p-5 border-white/5">
            <h4 className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-4">Core Formations</h4>
            <div className="space-y-2">
                {lineups.slice(0, 3).map((l, i) => (
                    <div key={i} className="flex items-center justify-between p-2 bg-white/5 rounded-xl">
                        <span className="text-xs font-black italic">{l.formation}</span>
                        <Badge variant="secondary">{l.played} Games</Badge>
                    </div>
                ))}
            </div>
        </Card>
    );
}

// 5. FixturesSummary
export function FixturesSummary({ fixtures }: { fixtures: any }) {
    if (!fixtures) return null;
    const items = [
        { label: 'Played', val: fixtures.played.total, color: 'text-white' },
        { label: 'Wins', val: fixtures.wins.total, color: 'text-brand-orange' },
        { label: 'Draws', val: fixtures.draws.total, color: 'text-gray-400' },
        { label: 'Loses', val: fixtures.loses.total, color: 'text-red-500' },
    ];
    return (
        <Card className="p-5 border-white/5">
            <div className="grid grid-cols-4 gap-2">
                {items.map(item => (
                    <div key={item.label} className="text-center">
                        <div className={cn("text-xl font-black italic", item.color)}>{item.val}</div>
                        <div className="text-[8px] font-black uppercase tracking-tighter text-gray-500">{item.label}</div>
                    </div>
                ))}
            </div>
        </Card>
    );
}

// 6. CardsByMinute
export function CardsByMinute({ cards, side }: { cards: any, side: 'home' | 'away' }) {
    if (!cards || (!cards.yellow && !cards.red)) return null;

    const minutes = ['0-15', '16-30', '31-45', '46-60', '61-75', '76-90', '91-105'];
    const getYellowVal = (min: string) => cards.yellow?.[min]?.total || 0;

    return (
        <Card className="p-5 border-white/5">
            <h4 className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-4">Yellow Cards Trend</h4>
            <div className="h-24 flex items-end gap-1">
                {minutes.map(m => {
                    const val = getYellowVal(m);
                    const height = Math.min(100, (val / 10) * 100); // Normalize based on max 10 cards
                    return (
                        <div key={m} className="flex-1 flex flex-col items-center group relative">
                            <div className="absolute -top-6 hidden group-hover:block bg-brand-orange text-[8px] font-bold px-1 rounded">{val}</div>
                            <div className="w-full bg-brand-orange/40 rounded-t-sm transition-all group-hover:bg-brand-orange" style={{ height: `${height}%` }} />
                            <div className="text-[6px] mt-1 text-gray-600 font-bold rotate-45">{m}'</div>
                        </div>
                    );
                })}
            </div>
        </Card>
    );
}

// 7. GoalsTabs (Simplified version for small panel)
export function GoalsTabs({ goals, side }: { goals: any, side: 'home' | 'away' }) {
    if (!goals) return null;
    return (
        <Card className="p-5 border-white/5">
            <h4 className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-4">Goal Scoring Timing</h4>
            <div className="space-y-3">
                <div>
                    <div className="flex justify-between text-[10px] font-bold text-gray-500 mb-1 uppercase">76-90' Critical Zone</div>
                    <Progress value={parseFloat(goals.for.minute['76-90']?.percentage || '0')} barClassName="bg-brand-orange" />
                </div>
                <div className="flex justify-between items-center text-[10px]">
                    <span className="text-gray-500 font-black uppercase tracking-widest italic">Avg Gls Per Match</span>
                    <span className="text-lg font-black">{goals.for.average.total}</span>
                </div>
            </div>
        </Card>
    );
}

// 8. BiggestStreakCard
export function BiggestStreakCard({ biggest, side }: { biggest: any, side: 'home' | 'away' }) {
    if (!biggest) return null;
    return (
        <Card className="p-5 border-white/5">
            <div className="flex items-center justify-between">
                <div>
                    <h4 className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-1">Max Win Streak</h4>
                    <div className="text-2xl font-black italic text-brand-orange">{biggest.streak.wins}</div>
                </div>
                <div className="text-right">
                    <h4 className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-1">Biggest Win</h4>
                    <div className="text-lg font-black">{biggest.wins.home || biggest.wins.away || 'N/D'}</div>
                </div>
            </div>
        </Card>
    );
}
