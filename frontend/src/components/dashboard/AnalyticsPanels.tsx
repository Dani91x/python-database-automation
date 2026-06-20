// Affianca i pulsanti di analisi sotto il blocco Fixture/League:
//  - Frequenze Mercati (per-lega, storico)  [MarketFrequencyPanel — INTATTO]
//  - Studio Ritardi    (per-lega, storico)  [RitardiPanel — copia 1:1 del file Excel]
//  - Poisson           (per-partita, snapshot)
//  - Modelli ML        (per-partita, snapshot)
// Ogni pannello e' autonomo (fetch proprio). MarketFrequencyPanel.tsx NON e' toccato.
import { MarketFrequencyPanel } from './MarketFrequencyPanel';
import { RitardiPanel } from './RitardiPanel';
import { PoissonPanel } from './PoissonPanel';
import { TacticalEnginePanel } from './TacticalEnginePanel';
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
            {leagueId != null && (
                <RitardiPanel leagueId={leagueId} leagueName={leagueName} />
            )}
            <PoissonPanel fixtureId={fixtureId} leagueName={leagueName} homeName={homeName} awayName={awayName} />
            <TacticalEnginePanel fixtureId={fixtureId} leagueName={leagueName} homeName={homeName} awayName={awayName} />
            <MLPanel fixtureId={fixtureId} leagueName={leagueName} homeName={homeName} awayName={awayName} />
        </div>
    );
}
