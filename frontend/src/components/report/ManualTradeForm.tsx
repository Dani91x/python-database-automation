// ============================================================================
// ManualTradeForm — Inserimento MANUALE di un'operazione PASSATA nel Report
// Personale. Flusso: scegli una DATA → tendina dei match Betfair di quel giorno
// (get_betfair_fixtures: SOLO match agganciati a Betfair) → compili l'operazione.
// Aggancia fixture_id/lega/squadre/kickoff reali, così la riga è riconciliabile
// con l'import automatico (.bat listClearedOrders) futuro.
//
// Due modalità di P&L (specchiano personal_tracking_manual_entry.sql):
//   • "P&L reale" ON  → pnl_source='actual': salvi il NETTO reale (€) + commissione
//     reale (€) come li dà Betfair; il DB li memorizza senza ricalcolarli.
//   • "P&L reale" OFF → pnl_source='model': il DB calcola il P&L dal modello
//     (esito + quota + stake + aliquota commissione).
// Design system identico a TradeForm (Dialog shadcn, glass-card, amber Betfair).
// ============================================================================
import { useEffect, useMemo, useState } from 'react';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, CalendarClock, Link2 } from 'lucide-react';
import { toast } from 'sonner';
import {
    addPersonalTrade,
    type AddTradePayload, type TradeSide, type TradeTiming, type TradeStatus,
} from '@/lib/personalReport';
import { fetchBetfairFixtures, type BetfairFixtureRow } from '@/lib/betfair';

interface Props {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSaved?: () => void;
}

const SELECT_CLS =
    'w-full bg-black/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-white ' +
    'focus:outline-none focus:border-primary/60 transition-colors';
const FIELD_LABEL = 'text-[10px] uppercase tracking-wider text-muted-foreground mb-1 block';

const num = (s: string): number | null => {
    if (s == null || s.trim() === '') return null;
    const v = Number(s);
    return Number.isFinite(v) ? v : null;
};

// data locale (YYYY-MM-DD) di N giorni fa — default: ieri (operazioni del giorno prima).
const isoDaysAgo = (days: number): string => {
    const d = new Date();
    d.setDate(d.getDate() - days);
    const off = d.getTimezoneOffset() * 60000;
    return new Date(d.getTime() - off).toISOString().slice(0, 10);
};

export function ManualTradeForm({ open, onOpenChange, onSaved }: Props) {
    // ---- selezione match (data → tendina Betfair) ----
    const [matchDate, setMatchDate] = useState(isoDaysAgo(1));
    const [fixtures, setFixtures] = useState<BetfairFixtureRow[]>([]);
    const [fixturesLoading, setFixturesLoading] = useState(false);
    const [fixturesErr, setFixturesErr] = useState<string | null>(null);
    const [fixtureId, setFixtureId] = useState<string>('');

    // ---- campi operazione ----
    const [strategia, setStrategia] = useState('');
    const [side, setSide] = useState<TradeSide>('back');
    const [timing, setTiming] = useState<TradeTiming>('prematch');
    const [market, setMarket] = useState('');
    const [selection, setSelection] = useState('');
    const [line, setLine] = useState('');
    const [entryOdds, setEntryOdds] = useState('');
    const [stake, setStake] = useState('');
    const [status, setStatus] = useState<TradeStatus>('WON');
    const [resultFt, setResultFt] = useState('');
    const [comment, setComment] = useState('');

    // ---- P&L reale vs modello ----
    const [realPnl, setRealPnl] = useState(true);       // default: reale (Betfair)
    const [netPnl, setNetPnl] = useState('');           // € (se realPnl)
    const [commissionAmt, setCommissionAmt] = useState(''); // € (se realPnl)
    const [commissionRate, setCommissionRate] = useState('0.05'); // aliquota (se modello)

    const [saving, setSaving] = useState(false);

    // carica i match Betfair della data scelta
    useEffect(() => {
        if (!open) return;
        let alive = true;
        setFixturesLoading(true);
        setFixturesErr(null);
        setFixtures([]);
        setFixtureId('');
        fetchBetfairFixtures(matchDate)
            .then(rows => { if (alive) setFixtures(rows); })
            .catch(e => { if (alive) setFixturesErr(e?.message ?? 'errore caricamento match'); })
            .finally(() => { if (alive) setFixturesLoading(false); });
        return () => { alive = false; };
    }, [open, matchDate]);

    const selectedFixture = useMemo(
        () => fixtures.find(f => String(f.fixture_id) === fixtureId) ?? null,
        [fixtures, fixtureId],
    );

    const reset = () => {
        setStrategia(''); setSide('back'); setTiming('prematch'); setMarket('');
        setSelection(''); setLine(''); setEntryOdds(''); setStake('');
        setStatus('WON'); setResultFt(''); setComment('');
        setRealPnl(true); setNetPnl(''); setCommissionAmt(''); setCommissionRate('0.05');
    };

    const handleSubmit = async () => {
        const o = num(entryOdds), s = num(stake);
        if (!selectedFixture) { toast.error('Seleziona il match Betfair.'); return; }
        if (!strategia.trim()) { toast.error('Inserisci la strategia.'); return; }
        if (o == null || o <= 1) { toast.error('Quota di ingresso non valida (> 1).'); return; }
        if (s == null || s < 0) { toast.error('Stake non valido.'); return; }
        const net = num(netPnl);
        if (realPnl && net == null) { toast.error('Con "P&L reale" inserisci il netto (€).'); return; }

        setSaving(true);
        try {
            const payload: AddTradePayload = {
                // identità match agganciata a Betfair
                fixture_id: selectedFixture.fixture_id,
                league_id: selectedFixture.league_id,
                league_name: selectedFixture.league_name,
                home_team: selectedFixture.home_team_name,
                away_team: selectedFixture.away_team_name,
                kickoff: selectedFixture.fixture_date,
                // operazione
                strategia: strategia.trim(),
                side,
                market: market.trim() || null,
                selection: selection.trim() || null,
                line: num(line),
                entry_odds: o,
                stake: s,
                timing,
                status,
                result_ft: resultFt.trim() || null,
                comment: comment.trim() || null,
                // giorno operativo = data del match scelta
                trade_date: matchDate,
                entry_source: 'manual',
                // P&L
                ...(realPnl
                    ? {
                        pnl_source: 'actual' as const,
                        net_pnl: net,
                        commission_amount: num(commissionAmt),
                    }
                    : {
                        pnl_source: 'model' as const,
                        commission: num(commissionRate) ?? 0.05,
                    }),
            };
            await addPersonalTrade(payload);
            toast.success('Operazione registrata', {
                description: `${selectedFixture.home_team_name} vs ${selectedFixture.away_team_name} · ${strategia.trim()}.`,
            });
            reset();
            onOpenChange(false);
            onSaved?.();
        } catch (e: any) {
            toast.error('Errore registrazione operazione', { description: e?.message ?? 'errore sconosciuto' });
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="glass-card bg-black/95 border-white/10 backdrop-blur-2xl max-w-2xl max-h-[92vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="font-display font-black text-xl text-white">
                        Inserisci operazione <span className="text-primary">passata</span>
                    </DialogTitle>
                    <DialogDescription className="text-xs text-muted-foreground">
                        Scegli la data e il match Betfair, poi registra l'operazione. Solo i match
                        <span className="text-amber-300"> agganciati a Betfair</span> sono selezionabili
                        (così la riga è riconciliabile con l'import automatico).
                    </DialogDescription>
                </DialogHeader>

                {/* ---- aggancio match ---- */}
                <div className="rounded-xl border border-amber-400/30 bg-amber-400/5 px-3 py-3 space-y-3">
                    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-amber-300 font-bold">
                        <Link2 className="w-3 h-3" /> Match Betfair
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div>
                            <Label className={FIELD_LABEL}><CalendarClock className="w-3 h-3 inline mr-1" />Data match *</Label>
                            <input type="date" className={SELECT_CLS} value={matchDate}
                                onChange={e => setMatchDate(e.target.value)} />
                        </div>
                        <div className="md:col-span-2">
                            <Label className={FIELD_LABEL}>Partita *</Label>
                            <select className={SELECT_CLS} value={fixtureId}
                                onChange={e => setFixtureId(e.target.value)} disabled={fixturesLoading}>
                                <option value="">
                                    {fixturesLoading ? 'Caricamento…'
                                        : fixtures.length ? '— seleziona —'
                                        : 'nessun match Betfair in questa data'}
                                </option>
                                {fixtures.map(f => (
                                    <option key={f.fixture_id} value={f.fixture_id}>
                                        {f.home_team_name} vs {f.away_team_name}
                                        {f.league_name ? ` · ${f.league_name}` : ''}
                                    </option>
                                ))}
                            </select>
                        </div>
                    </div>
                    {fixturesErr && <p className="text-[11px] text-red-400">{fixturesErr}</p>}
                    {selectedFixture && (
                        <p className="text-[11px] text-muted-foreground">
                            Agganciato: <span className="text-white">{selectedFixture.home_team_name} vs {selectedFixture.away_team_name}</span>
                            {selectedFixture.league_name ? ` · ${selectedFixture.league_name}` : ''}
                            {' · '}fixture_id <span className="font-mono text-white/70">{selectedFixture.fixture_id}</span>
                        </p>
                    )}
                </div>

                {/* ---- campi operazione ---- */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <div className="col-span-2 md:col-span-1">
                        <Label className={FIELD_LABEL}>Strategia *</Label>
                        <Input value={strategia} onChange={e => setStrategia(e.target.value)} placeholder="es. Lay the Draw"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Lato *</Label>
                        <select className={SELECT_CLS} value={side} onChange={e => setSide(e.target.value as TradeSide)}>
                            <option value="back">Back (punta)</option>
                            <option value="lay">Lay (banca)</option>
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Timing</Label>
                        <select className={SELECT_CLS} value={timing} onChange={e => setTiming(e.target.value as TradeTiming)}>
                            <option value="prematch">Pre-match</option>
                            <option value="live">Live</option>
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Mercato</Label>
                        <Input value={market} onChange={e => setMarket(e.target.value)} placeholder="es. over_2_5"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Selezione</Label>
                        <Input value={selection} onChange={e => setSelection(e.target.value)} placeholder="es. Under"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Linea</Label>
                        <Input type="number" step="0.25" value={line} onChange={e => setLine(e.target.value)} placeholder="es. 2.5"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Quota ingresso *</Label>
                        <Input type="number" step="0.01" min="1.01" value={entryOdds} onChange={e => setEntryOdds(e.target.value)}
                            placeholder="es. 1.85" className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Stake (€) *</Label>
                        <Input type="number" step="0.01" min="0" value={stake} onChange={e => setStake(e.target.value)}
                            placeholder="es. 100" className="bg-black/60 border-white/10" />
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Esito *</Label>
                        <select className={SELECT_CLS} value={status} onChange={e => setStatus(e.target.value as TradeStatus)}>
                            <option value="WON">Vinto</option>
                            <option value="LOST">Perso</option>
                            <option value="VOID">Annullato</option>
                            <option value="PARTIAL">Parziale (cash-out)</option>
                            <option value="OPEN">Aperto</option>
                        </select>
                    </div>
                    <div>
                        <Label className={FIELD_LABEL}>Risultato FT</Label>
                        <Input value={resultFt} onChange={e => setResultFt(e.target.value)} placeholder="es. 2-1"
                            className="bg-black/60 border-white/10" />
                    </div>
                    <div className="col-span-2 md:col-span-3">
                        <Label className={FIELD_LABEL}>Nota</Label>
                        <Input value={comment} onChange={e => setComment(e.target.value)} placeholder="commento libero"
                            className="bg-black/60 border-white/10" />
                    </div>
                </div>

                {/* ---- P&L reale vs modello ---- */}
                <div className="border-t border-white/5 pt-3">
                    <label className="flex items-center gap-2 cursor-pointer select-none mb-3">
                        <input type="checkbox" checked={realPnl} onChange={e => setRealPnl(e.target.checked)}
                            className="w-4 h-4 accent-primary" />
                        <span className="text-sm text-white font-heading font-bold">Registra P&amp;L reale (Betfair)</span>
                        <span className="text-[11px] text-muted-foreground">
                            {realPnl ? 'netto e commissione presi da Betfair' : 'il DB calcola dal modello'}
                        </span>
                    </label>

                    {realPnl ? (
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label className={FIELD_LABEL}>P&amp;L netto reale (€) *</Label>
                                <Input type="number" step="0.01" value={netPnl} onChange={e => setNetPnl(e.target.value)}
                                    placeholder="es. 392.00 o -235.01" className="bg-black/60 border-white/10" />
                            </div>
                            <div>
                                <Label className={FIELD_LABEL}>Commissione reale (€)</Label>
                                <Input type="number" step="0.01" min="0" value={commissionAmt} onChange={e => setCommissionAmt(e.target.value)}
                                    placeholder="es. 8.00" className="bg-black/60 border-white/10" />
                            </div>
                        </div>
                    ) : (
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label className={FIELD_LABEL}>Aliquota commissione</Label>
                                <Input type="number" step="0.01" min="0" max="1" value={commissionRate}
                                    onChange={e => setCommissionRate(e.target.value)} className="bg-black/60 border-white/10" />
                            </div>
                            <p className="text-[11px] text-muted-foreground self-end pb-2">
                                Il P&amp;L viene calcolato dal server da esito + quota + stake.
                            </p>
                        </div>
                    )}
                </div>

                <DialogFooter className="mt-2">
                    <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}
                        className="text-muted-foreground hover:text-white">Annulla</Button>
                    <Button onClick={handleSubmit} disabled={saving || !selectedFixture}
                        className="bg-primary text-primary-foreground font-bold hover:bg-primary/90">
                        {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                        Registra operazione
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
