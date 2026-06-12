// ⚠️ AUTENTICAZIONE TEMPORANEAMENTE DISABILITATA — accesso libero alla dashboard.
// Il sistema di auth (useAuth, AuthSection, supabase.auth) NON è stato rimosso:
// è solo bypassato qui. Per riattivare il login, ripristinare il blocco
// "AUTH ORIGINALE" qui sotto (ri-aggiungendo gli import di Navigate/useAuth/Loader2)
// e rimuovere il bypass.
export function ProtectedRoute({ children }: { children: React.ReactNode }) {
    // --- BYPASS: accesso libero, nessun controllo login ---
    return <>{children}</>;
}

/* AUTH ORIGINALE — riattivare insieme ai seguenti import:
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { Loader2 } from 'lucide-react';

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
    const { user, loading } = useAuth();

    if (loading) {
        return (
            <div className="flex h-screen w-full items-center justify-center bg-background text-foreground">
                <Loader2 className="h-10 w-10 animate-spin text-brand-orange" />
            </div>
        );
    }

    if (!user) {
        return <Navigate to="/" replace />;
    }

    return <>{children}</>;
}
*/
