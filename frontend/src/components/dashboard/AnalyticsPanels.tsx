// Affianca i 3 pulsanti di analisi sotto il blocco Fixture/League:
//  - Frequenze Mercati (per-lega, storico)  [MarketFrequencyPanel — INTATTO]
//  - Poisson           (per-partita, snapshot)
//  - Modelli ML        (per-partita, snapshot)
// Ogni pannello e' autonomo (fetch proprio). MarketFrequencyPanel.tsx NON e' toccato.
import { MarketFrequencyPanel } from './MarketFrequencyPanel';
import { PoissonPanel } from './PoissonPanel';
import { MLPanel } from './MLPanel';

interface Props {
    leagueId: number | null;
    leagueName: string;
    fixtureId: string;
    homeName: string;
    awayName: string;
}

export function AnalyticsPanels({ leagueId, leagueName, fixtureId, homeName, awayName }: Props) {
    return (
        <div className="flex flex-wrap items-start justify-center gap-3">
            {leagueId != null && (
                <MarketFrequencyPanel leagueId={leagueId} leagueName={leagueName} />
            )}
            <PoissonPanel fixtureId={fixtureId} leagueName={leagueName} homeName={homeName} awayName={awayName} />
            <MLPanel fixtureId={fixtureId} leagueName={leagueName} homeName={homeName} awayName={awayName} />
        </div>
    );
}
