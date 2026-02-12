import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TeamLeagueStats } from "@/lib/normalizePrediction";
import { Goal, ShieldX } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, Tooltip } from "recharts";

interface GoalsTabsProps {
  goals: TeamLeagueStats['goals'];
  side: 'home' | 'away';
}

export function GoalsTabs({ goals, side }: GoalsTabsProps) {
  const isHome = side === 'home';

  const formatMinuteData = (minute: Record<string, { total: number | null; percentage: string | null }>) => {
    return Object.entries(minute).map(([key, value]) => ({
      name: key,
      total: value.total ?? 0,
      percentage: value.percentage || 'N/D',
    }));
  };

  const renderGoalsSection = (type: 'for' | 'against') => {
    const data = type === 'for' ? goals.for : goals.against;
    const color = type === 'for' ? 'hsl(145, 100%, 45%)' : 'hsl(0, 80%, 55%)';
    const minuteData = formatMinuteData(data.minute);

    return (
      <div className="space-y-5">
        {/* Totals */}
        <div>
          <h5 className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
            Total Goals {type === 'for' ? 'Scored' : 'Conceded'}
          </h5>
          <div className="grid grid-cols-3 gap-3">
            <div className="glass-card p-3 rounded-lg text-center">
              <div className="stat-label">Home</div>
              <div className="font-display text-2xl font-bold mt-1" style={{ color }}>
                {data.total.home}
              </div>
            </div>
            <div className="glass-card p-3 rounded-lg text-center">
              <div className="stat-label">Away</div>
              <div className="font-display text-2xl font-bold mt-1" style={{ color }}>
                {data.total.away}
              </div>
            </div>
            <div className="glass-card p-3 rounded-lg text-center border-2" style={{ borderColor: `${color}30` }}>
              <div className="stat-label">Total</div>
              <div className="font-display text-2xl font-bold mt-1" style={{ color }}>
                {data.total.total}
              </div>
            </div>
          </div>
        </div>

        {/* Averages */}
        <div>
          <h5 className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
            Average per Match
          </h5>
          <div className="grid grid-cols-3 gap-3">
            <div className="text-center">
              <div className="stat-label">Home</div>
              <div className="font-display text-lg font-bold mt-1">{data.average.home.toFixed(1)}</div>
            </div>
            <div className="text-center">
              <div className="stat-label">Away</div>
              <div className="font-display text-lg font-bold mt-1">{data.average.away.toFixed(1)}</div>
            </div>
            <div className="text-center">
              <div className="stat-label">Total</div>
              <div className="font-display text-lg font-bold mt-1">{data.average.total.toFixed(1)}</div>
            </div>
          </div>
        </div>

        {/* Goals by Minute Chart */}
        <div>
          <h5 className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
            Goals by Minute
          </h5>
          <div className="h-40">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={minuteData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                <XAxis 
                  dataKey="name" 
                  tick={{ fill: 'hsl(215, 20%, 55%)', fontSize: 10 }}
                  axisLine={{ stroke: 'hsl(220, 15%, 20%)' }}
                  tickLine={false}
                />
                <YAxis 
                  tick={{ fill: 'hsl(215, 20%, 55%)', fontSize: 10 }}
                  axisLine={{ stroke: 'hsl(220, 15%, 20%)' }}
                  tickLine={false}
                />
                <Tooltip 
                  contentStyle={{
                    background: 'hsl(220, 20%, 12%)',
                    border: '1px solid hsl(220, 15%, 25%)',
                    borderRadius: '8px',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
                  }}
                  labelStyle={{ color: 'hsl(210, 40%, 98%)' }}
                  formatter={(value: number, name: string) => [value, 'Goals']}
                />
                <Bar dataKey="total" radius={[4, 4, 0, 0]}>
                  {minuteData.map((entry, index) => (
                    <Cell 
                      key={`cell-${index}`} 
                      fill={color}
                      opacity={entry.total > 0 ? 0.8 : 0.2}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Under/Over Distribution */}
        <div>
          <h5 className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
            Under/Over Distribution
          </h5>
          <div className="space-y-2">
            {Object.entries(data.underOver).map(([threshold, values]) => {
              const total = values.over + values.under;
              const overPercent = total > 0 ? (values.over / total) * 100 : 0;
              return (
                <div key={threshold} className="flex items-center gap-3">
                  <span className="w-10 text-xs font-mono text-muted-foreground">{threshold}</span>
                  <div className="flex-1 h-5 rounded-full overflow-hidden bg-muted/30 flex">
                    <div 
                      className="h-full transition-all duration-500"
                      style={{ 
                        width: `${100 - overPercent}%`,
                        background: 'linear-gradient(90deg, hsl(210, 100%, 60%), hsl(210, 100%, 50%))'
                      }}
                    />
                    <div 
                      className="h-full transition-all duration-500"
                      style={{ 
                        width: `${overPercent}%`,
                        background: 'linear-gradient(90deg, hsl(25, 100%, 55%), hsl(45, 100%, 60%))'
                      }}
                    />
                  </div>
                  <div className="flex gap-2 text-xs">
                    <span className="text-neon-blue">U:{values.under}</span>
                    <span className="text-neon-orange">O:{values.over}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="glass-card p-5">
      <Tabs defaultValue="for" className="w-full">
        <TabsList className="grid w-full grid-cols-2 bg-muted/30">
          <TabsTrigger 
            value="for" 
            className="data-[state=active]:bg-neon-green/20 data-[state=active]:text-neon-green flex items-center gap-2"
          >
            <Goal className="w-4 h-4" />
            Goals For
          </TabsTrigger>
          <TabsTrigger 
            value="against"
            className="data-[state=active]:bg-destructive/20 data-[state=active]:text-destructive flex items-center gap-2"
          >
            <ShieldX className="w-4 h-4" />
            Goals Against
          </TabsTrigger>
        </TabsList>
        <TabsContent value="for" className="mt-4">
          {renderGoalsSection('for')}
        </TabsContent>
        <TabsContent value="against" className="mt-4">
          {renderGoalsSection('against')}
        </TabsContent>
      </Tabs>
    </div>
  );
}
