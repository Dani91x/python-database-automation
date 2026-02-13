import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from 'react-helmet-async';
import { BrowserRouter, Routes, Route } from "react-router-dom";
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
                            <Route path="/" element={<LandingPage />} />
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
