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
import MatchReplay from "@/pages/MatchReplay";
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
                            <Route
                                path="/match-replay"
                                element={
                                    <ProtectedRoute>
                                        <MatchReplay />
                                    </ProtectedRoute>
                                }
                            />
                            <Route path="*" element={<NotFound />} />
                        </Routes>
                    </BrowserRouter>
                </TooltipProvider>
            </HelmetProvider>
        </QueryClientProvider>
    );
}

export default App;
