// AUTENTICAZIONE ATTIVA — early access: accede SOLO l'owner.
// La dashboard è protetta: serve una sessione valida E che l'utente loggato
// sia l'owner (isOwnerEmail). Qualunque altra sessione viene rimandata alla
// landing. Per aprire al pubblico vedi NOTE in src/lib/auth-config.ts.
import { Navigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { isOwnerEmail } from '@/lib/auth-config';

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
    const { user, loading } = useAuth();

    if (loading) {
        return (
            <div className="flex h-screen w-full items-center justify-center bg-background text-foreground">
                <Loader2 className="h-10 w-10 animate-spin text-brand-orange" />
            </div>
        );
    }

    // Nessuna sessione, oppure sessione di un utente NON autorizzato → landing.
    if (!user || !isOwnerEmail(user.email)) {
        return <Navigate to="/" replace />;
    }

    return <>{children}</>;
}
