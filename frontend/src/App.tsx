import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from 'react-helmet-async';
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import LandingPage from "@/pages/LandingPage";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import Dashboard from "@/pages/Dashboard";
import CheckEmail from "@/pages/CheckEmail";
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
                            {/* AUTH DISABILITATA: la root porta direttamente alla dashboard.
                                La landing con login resta raggiungibile a /landing.
                                Per ripristinare il comportamento originale, rimettere
                                LandingPage su path="/" ed eliminare il redirect. */}
                            <Route path="/" element={<Navigate to="/dashboard" replace />} />
                            <Route path="/landing" element={<LandingPage />} />
                            <Route path="/check-email" element={<CheckEmail />} />
                            <Route
                                path="/dashboard"
                                element={
                                    <ProtectedRoute>
                                        <Dashboard />
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
