import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { motion } from 'framer-motion';
import { KeyRound, Loader2, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';

import { supabase } from '@/integrations/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
    Form, FormControl, FormField, FormItem, FormLabel, FormMessage
} from '@/components/ui/form';

const schema = z.object({
    password: z.string().min(8, 'Minimo 8 caratteri'),
    confirmPassword: z.string().min(8),
}).refine(d => d.password === d.confirmPassword, {
    message: 'Le password non coincidono',
    path: ['confirmPassword'],
});

// Pagina di destinazione del link "reset password" inviato via email.
// Il client Supabase (detectSessionInUrl) elabora il token di recovery dall'URL
// e apre una sessione temporanea: qui l'utente imposta la NUOVA password.
export default function ResetPassword() {
    const navigate = useNavigate();
    const [isLoading, setIsLoading] = useState(false);
    // 'checking' | 'ready' (sessione recovery valida) | 'invalid' (link scaduto/assente)
    const [status, setStatus] = useState<'checking' | 'ready' | 'invalid'>('checking');

    useEffect(() => {
        // Caso 1: evento esplicito di recovery quando il token viene processato.
        const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
            if (event === 'PASSWORD_RECOVERY' || (session && event === 'SIGNED_IN')) {
                setStatus('ready');
            }
        });

        // Caso 2: la sessione potrebbe già essere stata stabilita al caricamento.
        supabase.auth.getSession().then(({ data: { session } }) => {
            setStatus(prev => (prev === 'ready' ? prev : session ? 'ready' : 'invalid'));
        });

        // Fallback: se entro 3s non c'è sessione, consideriamo il link non valido.
        const t = setTimeout(() => {
            setStatus(prev => (prev === 'ready' ? prev : 'invalid'));
        }, 3000);

        return () => {
            subscription.unsubscribe();
            clearTimeout(t);
        };
    }, []);

    const form = useForm<z.infer<typeof schema>>({
        resolver: zodResolver(schema),
        defaultValues: { password: '', confirmPassword: '' },
    });

    async function onSubmit(values: z.infer<typeof schema>) {
        setIsLoading(true);
        try {
            const { error } = await supabase.auth.updateUser({ password: values.password });
            if (error) throw error;
            toast.success('Password aggiornata!', { description: 'Ora puoi accedere con la nuova password.' });
            navigate('/dashboard');
        } catch (err: any) {
            toast.error('Errore aggiornamento password', { description: err?.message });
        } finally {
            setIsLoading(false);
        }
    }

    return (
        <div className="min-h-screen bg-background flex items-center justify-center px-4">
            <div className="fixed inset-0 grid-pattern opacity-20 pointer-events-none" />
            <div className="fixed inset-0 bg-gradient-hero pointer-events-none" />

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="relative z-10 w-full max-w-md"
            >
                <div className="glass-card animated-border rounded-2xl p-8 md:p-10 space-y-6">
                    <div className="flex justify-center">
                        <div className="w-20 h-20 rounded-full bg-primary/10 border-2 border-primary/30 flex items-center justify-center neon-glow-cyan">
                            <KeyRound className="w-10 h-10 text-primary" strokeWidth={1.5} />
                        </div>
                    </div>

                    {status === 'checking' && (
                        <div className="flex flex-col items-center gap-4 py-6 text-muted-foreground">
                            <Loader2 className="w-8 h-8 animate-spin text-primary" />
                            <p className="font-heading">Verifica del link in corso…</p>
                        </div>
                    )}

                    {status === 'invalid' && (
                        <div className="space-y-5 text-center">
                            <h1 className="text-2xl font-display font-bold text-foreground">Link non valido o scaduto</h1>
                            <div className="flex items-start gap-3 p-4 rounded-xl bg-accent/10 border border-accent/20 text-left">
                                <AlertTriangle className="w-5 h-5 text-accent flex-shrink-0 mt-0.5" />
                                <p className="text-sm text-muted-foreground">
                                    Il link di reset è scaduto o è stato già usato. Richiedine uno nuovo dalla
                                    schermata di accesso con "Password dimenticata?".
                                </p>
                            </div>
                            <Button
                                onClick={() => navigate('/')}
                                className="w-full font-heading font-bold bg-primary text-primary-foreground hover:bg-primary/90"
                            >
                                Torna al login
                            </Button>
                        </div>
                    )}

                    {status === 'ready' && (
                        <>
                            <div className="text-center space-y-2">
                                <h1 className="text-2xl font-display font-bold text-foreground">Imposta nuova password</h1>
                                <p className="text-sm text-muted-foreground font-heading">
                                    Scegli una nuova password per il tuo account.
                                </p>
                            </div>
                            <Form {...form}>
                                <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                                    <FormField
                                        control={form.control}
                                        name="password"
                                        render={({ field }) => (
                                            <FormItem>
                                                <FormLabel className="text-muted-foreground">Nuova password</FormLabel>
                                                <FormControl>
                                                    <Input type="password" placeholder="Min. 8 caratteri" {...field} disabled={isLoading} />
                                                </FormControl>
                                                <FormMessage />
                                            </FormItem>
                                        )}
                                    />
                                    <FormField
                                        control={form.control}
                                        name="confirmPassword"
                                        render={({ field }) => (
                                            <FormItem>
                                                <FormLabel className="text-muted-foreground">Conferma password</FormLabel>
                                                <FormControl>
                                                    <Input type="password" placeholder="Ripeti password" {...field} disabled={isLoading} />
                                                </FormControl>
                                                <FormMessage />
                                            </FormItem>
                                        )}
                                    />
                                    <Button
                                        type="submit"
                                        disabled={isLoading}
                                        className="w-full py-6 text-lg font-heading font-bold rounded-xl bg-primary text-primary-foreground hover:bg-primary/90"
                                    >
                                        {isLoading ? (
                                            <span className="flex items-center gap-2">
                                                <Loader2 className="w-5 h-5 animate-spin" />
                                                Aggiornamento…
                                            </span>
                                        ) : 'Salva nuova password'}
                                    </Button>
                                </form>
                            </Form>
                        </>
                    )}
                </div>
            </motion.div>
        </div>
    );
}
