import { useEffect, useState } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { ChevronDown } from 'lucide-react';

/* eslint-disable @typescript-eslint/no-explicit-any */

interface FixtureOption {
    fixture_id: string;
    home: string;
    away: string;
    league: string;
    date: string;
}

interface FixtureSelectorProps {
    currentFixtureId?: string;
    onSelect: (fixtureId: string) => void;
}

export function FixtureSelector({ currentFixtureId, onSelect }: FixtureSelectorProps) {
    const [fixtures, setFixtures] = useState<FixtureOption[]>([]);
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchFixtures() {
            setLoading(true);
            try {
                const { data, error } = await supabase
                    .from('fixture_predictions')
                    .select('fixture_id, raw_json, match_date')
                    .order('match_date', { ascending: false });

                if (error) throw error;

                const mapped: FixtureOption[] = (data || [])
                    .map((row: any) => {
                        try {
                            const resp = row.raw_json?.response?.[0];
                            if (!resp) return null;
                            return {
                                fixture_id: String(row.fixture_id),
                                home: resp.teams?.home?.name || 'Home',
                                away: resp.teams?.away?.name || 'Away',
                                league: resp.league?.name || '',
                                date: row.match_date
                                    ? new Date(row.match_date).toLocaleDateString('it-IT', {
                                        day: '2-digit',
                                        month: 'short',
                                        year: 'numeric',
                                    })
                                    : '',
                            };
                        } catch {
                            return null;
                        }
                    })
                    .filter(Boolean) as FixtureOption[];

                setFixtures(mapped);
            } catch (e) {
                console.error('Errore caricamento fixture:', e);
            } finally {
                setLoading(false);
            }
        }

        fetchFixtures();
    }, []);

    const current = fixtures.find((f) => f.fixture_id === currentFixtureId);

    return (
        <div className="relative">
            <button
                onClick={() => setOpen(!open)}
                className="glass-card flex items-center gap-3 px-4 py-2.5 rounded-xl hover:border-primary/40 transition-colors w-full sm:w-auto cursor-pointer"
            >
                <span className="text-sm font-heading text-muted-foreground">Partita:</span>
                <span className="text-sm font-heading font-bold text-foreground truncate max-w-[220px]">
                    {loading
                        ? 'Caricamento...'
                        : current
                            ? `${current.home} vs ${current.away}`
                            : 'Seleziona partita'}
                </span>
                <ChevronDown
                    className={`w-4 h-4 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`}
                />
            </button>

            {open && (
                <>
                    {/* Backdrop */}
                    <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />

                    {/* Dropdown */}
                    <div className="absolute left-0 top-full mt-2 z-50 w-full sm:w-[400px] max-h-[400px] overflow-y-auto glass-card rounded-xl border border-border/50 shadow-2xl">
                        {fixtures.length === 0 && !loading && (
                            <div className="p-4 text-center text-sm text-muted-foreground">
                                Nessuna partita disponibile
                            </div>
                        )}
                        {fixtures.map((f) => (
                            <button
                                key={f.fixture_id}
                                onClick={() => {
                                    onSelect(f.fixture_id);
                                    setOpen(false);
                                }}
                                className={`w-full text-left px-4 py-3 transition-colors hover:bg-primary/10 border-b border-border/20 last:border-0 flex items-center justify-between gap-4 ${f.fixture_id === currentFixtureId
                                        ? 'bg-primary/5 border-l-2 border-l-primary'
                                        : ''
                                    }`}
                            >
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm font-heading font-bold text-foreground truncate">
                                        {f.home} vs {f.away}
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                        {f.league}
                                    </div>
                                </div>
                                <div className="text-xs text-muted-foreground whitespace-nowrap">
                                    {f.date}
                                </div>
                            </button>
                        ))}
                    </div>
                </>
            )}
        </div>
    );
}
