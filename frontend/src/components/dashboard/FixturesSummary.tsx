import { TeamLeagueStats } from "@/lib/normalizePrediction";
import { Calendar, Trophy, Minus, X } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

interface FixturesSummaryProps {
  fixtures: TeamLeagueStats['fixtures'];
  side: 'home' | 'away';
}

export function FixturesSummary({ fixtures, side }: FixturesSummaryProps) {
  const isHome = side === 'home';
  
  const chartData = [
    { name: 'Wins', value: fixtures.wins.total, color: 'hsl(145, 100%, 45%)' },
    { name: 'Draws', value: fixtures.draws.total, color: 'hsl(45, 100%, 50%)' },
    { name: 'Losses', value: fixtures.loses.total, color: 'hsl(0, 80%, 55%)' },
  ];

  return (
    <div className="glass-card p-5">
      <h4 className="font-heading text-sm font-semibold text-muted-foreground mb-4 uppercase tracking-wider flex items-center gap-2">
        <Calendar className="w-4 h-4" />
        Season Fixtures
      </h4>

      <div className="grid grid-cols-2 gap-4">
        {/* Donut Chart */}
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={30}
                outerRadius={50}
                paddingAngle={3}
                dataKey="value"
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{
                  background: 'hsl(220, 20%, 12%)',
                  border: '1px solid hsl(220, 15%, 25%)',
                  borderRadius: '8px',
                }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="text-center -mt-2">
            <span className="font-display text-lg font-bold">{fixtures.played.total}</span>
            <span className="text-xs text-muted-foreground block">Played</span>
          </div>
        </div>

        {/* Stats Table */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Trophy className="w-4 h-4 text-neon-green" />
            <span className="text-sm flex-1">Wins</span>
            <div className="flex gap-2 text-sm">
              <span className="text-muted-foreground">H:{fixtures.wins.home}</span>
              <span className="text-muted-foreground">A:{fixtures.wins.away}</span>
              <span className="font-bold text-neon-green">{fixtures.wins.total}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Minus className="w-4 h-4 text-accent" />
            <span className="text-sm flex-1">Draws</span>
            <div className="flex gap-2 text-sm">
              <span className="text-muted-foreground">H:{fixtures.draws.home}</span>
              <span className="text-muted-foreground">A:{fixtures.draws.away}</span>
              <span className="font-bold text-accent">{fixtures.draws.total}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <X className="w-4 h-4 text-destructive" />
            <span className="text-sm flex-1">Losses</span>
            <div className="flex gap-2 text-sm">
              <span className="text-muted-foreground">H:{fixtures.loses.home}</span>
              <span className="text-muted-foreground">A:{fixtures.loses.away}</span>
              <span className="font-bold text-destructive">{fixtures.loses.total}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Played breakdown */}
      <div className="mt-4 pt-4 border-t border-border/50 grid grid-cols-3 gap-2 text-center">
        <div>
          <div className="stat-label">Home</div>
          <div className="font-display font-bold">{fixtures.played.home}</div>
        </div>
        <div>
          <div className="stat-label">Away</div>
          <div className="font-display font-bold">{fixtures.played.away}</div>
        </div>
        <div>
          <div className="stat-label">Total</div>
          <div className="font-display font-bold">{fixtures.played.total}</div>
        </div>
      </div>
    </div>
  );
}
