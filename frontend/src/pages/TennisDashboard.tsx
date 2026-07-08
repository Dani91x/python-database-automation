import { Helmet } from 'react-helmet-async';
import { TennisNav } from '@/components/tennis/TennisNav';
import { TennisMatchesList } from '@/components/tennis/TennisMatchesList';

/**
 * SCREEN 2 — Tennis: Partite del Giorno.
 *
 * Replica la struttura/UX della dashboard Football (Partite del Giorno) adattata al
 * tennis: match del giorno da Betfair Exchange (eventTypeId=2), raggruppati per
 * torneo in accordion espandibili, ordinati per orario, con quote moneyline P1/P2
 * (back/lay), volume matchato, stato pre-match/in-running e star watchlist.
 */
export default function TennisDashboard() {
    return (
        <div className="min-h-screen bg-background relative pb-24">
            <Helmet>
                <title>Tennis · Partite del Giorno | Alpha Score</title>
            </Helmet>

            <div className="fixed inset-0 pointer-events-none z-0 grid-pattern opacity-30" />

            <TennisNav sectionLabel="TENNIS" />

            <main className="container mx-auto px-4 lg:px-6 py-8 max-w-7xl relative z-10 w-full overflow-hidden">
                <TennisMatchesList />
            </main>

            <footer className="border-t border-white/5 py-8 text-center text-xs text-muted-foreground">
                <p>&copy; {new Date().getFullYear()} Alpha Score AI. All rights reserved.</p>
            </footer>
        </div>
    );
}
