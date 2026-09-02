import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from 'react-helmet-async';
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import LandingPage from "@/pages/LandingPage";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import SelectSport from "@/pages/SelectSport";
import Dashboard from "@/pages/Dashboard";
import TennisDashboard from "@/pages/TennisDashboard";
import TennisTerminal from "@/pages/TennisTerminal";
import Analytics from "@/pages/Analytics";
import Watchlist from "@/pages/Watchlist";
import ReportPersonale from "@/pages/ReportPersonale";
import SeguiLive from "@/pages/SeguiLive";
import Board from "@/pages/Board";
import MarketWatch from "@/pages/MarketWatch";
import LivePnl from "@/pages/LivePnl";
import TradeJournal from "@/pages/TradeJournal";
import MultiLadder from "@/pages/MultiLadder";
import LadderPopout from "@/pages/LadderPopout";
import MatchReplay from "@/pages/MatchReplay";
import Omega from "@/pages/Omega";
import SafeStrategy from "@/pages/SafeStrategy";
import { SafeStrategyProvider } from "@/components/safestrategy/SafeStrategyProvider";
import CheckEmail from "@/pages/CheckEmail";
import ResetPassword from "@/pages/ResetPassword";
import NotFound from "@/pages/NotFound";

const queryClient = new QueryClient();

function App() {
    return (
        <QueryClientProvider client={queryClient}>
            <HelmetProvider>
                <TooltipProvider>
                    <Toaster />
                    <BrowserRouter>
                        {/* Provider globale Safe Strategy: valuta i segnali anche quando
                            l'utente è su un'altra schermata (toast → /safe-strategy). */}
                        <SafeStrategyProvider>
                        <Routes>
                            {/* AUTH ATTIVA: la landing (con login/registrazione) è la root.
                                La dashboard e analytics sono protette da ProtectedRoute. */}
                            <Route path="/" element={<LandingPage />} />
                            <Route path="/check-email" element={<CheckEmail />} />
                            <Route path="/reset-password" element={<ResetPassword />} />
                            <Route
                                path="/select-sport"
                                element={
                                    <ProtectedRoute>
                                        <SelectSport />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/dashboard"
                                element={
                                    <ProtectedRoute>
                                        <Dashboard />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/tennis"
                                element={
                                    <ProtectedRoute>
                                        <TennisDashboard />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/tennis/terminal"
                                element={
                                    <ProtectedRoute>
                                        <TennisTerminal />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/analytics"
                                element={
                                    <ProtectedRoute>
                                        <Analytics />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/watchlist"
                                element={
                                    <ProtectedRoute>
                                        <Watchlist />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/report-personale"
                                element={
                                    <ProtectedRoute>
                                        <ReportPersonale />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/segui-live"
                                element={
                                    <ProtectedRoute>
                                        <SeguiLive />
                                    </ProtectedRoute>
                                }
                            />
                            {/* Programma di oggi (app desktop): tabellone dai canali LOCALI */}
                            <Route
                                path="/board"
                                element={
                                    <ProtectedRoute>
                                        <Board />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/market-watch"
                                element={
                                    <ProtectedRoute>
                                        <MarketWatch />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/live-pnl"
                                element={
                                    <ProtectedRoute>
                                        <LivePnl />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/trade-journal"
                                element={
                                    <ProtectedRoute>
                                        <TradeJournal />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/multi-ladder"
                                element={
                                    <ProtectedRoute>
                                        <MultiLadder />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/ladder-popout"
                                element={
                                    <ProtectedRoute>
                                        <LadderPopout />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/match-replay"
                                element={
                                    <ProtectedRoute>
                                        <MatchReplay />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/omega"
                                element={
                                    <ProtectedRoute>
                                        <Omega />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/safe-strategy"
                                element={
                                    <ProtectedRoute>
                                        <SafeStrategy />
                                    </ProtectedRoute>
                                }
                            />
                            <Route path="*" element={<NotFound />} />
                        </Routes>
                        </SafeStrategyProvider>
                    </BrowserRouter>
                </TooltipProvider>
            </HelmetProvider>
        </QueryClientProvider>
    );
}

export default App;
