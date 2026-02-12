import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { AlertTriangle } from 'lucide-react';

export default function NotFound() {
    return (
        <div className="min-h-screen flex flex-col items-center justify-center bg-background text-white px-6 text-center">
            <AlertTriangle className="w-16 h-16 text-brand-orange mb-6 animate-pulse" />
            <h1 className="text-6xl font-orbitron font-black mb-4">404</h1>
            <p className="text-lg text-muted-foreground mb-8 max-w-md">
                La pagina che stai cercando non esiste o è stata spostata.
            </p>
            <Link to="/">
                <Button size="lg" className="bg-brand-orange text-black font-bold hover:bg-white">
                    Torna alla Home
                </Button>
            </Link>
        </div>
    );
}
