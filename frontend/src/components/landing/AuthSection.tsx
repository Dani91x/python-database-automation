import { useState, forwardRef } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { motion } from 'framer-motion';
import { supabase } from '@/integrations/supabase/client';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Checkbox } from '@/components/ui/checkbox';
import {
    Form, FormControl, FormField, FormItem, FormLabel, FormMessage
} from '@/components/ui/form';

// --- SCHEMAS (INVARIATI) ---
const registerSchema = z.object({
    firstName: z.string().trim().min(1, "Nome obbligatorio").max(50),
    lastName: z.string().trim().min(1, "Cognome obbligatorio").max(50),
    email: z.string().trim().email("Email non valida").max(255),
    phone: z.string().trim().min(6, "Telefono non valido").max(20),
    telegram: z.string().trim().max(50).optional().or(z.literal("")),
    password: z.string().min(8, "Minimo 8 caratteri"),
    confirmPassword: z.string().min(8),
    terms: z.boolean().refine(val => val === true, "Devi accettare i termini"),
}).refine(data => data.password === data.confirmPassword, {
    message: "Le password non coincidono",
    path: ["confirmPassword"],
});

const loginSchema = z.object({
    email: z.string().trim().email("Email non valida"),
    password: z.string().min(1, "Password obbligatoria"),
});

interface AuthSectionProps {
    defaultTab?: "register" | "login";
}

const inputClass = "bg-input/50 border-glass-border text-foreground placeholder:text-muted-foreground/50";

export const AuthSection = forwardRef<HTMLDivElement, AuthSectionProps>(
    ({ defaultTab = "register" }, ref) => {
        const navigate = useNavigate();
        const [isLoading, setIsLoading] = useState(false);
        const [activeTab, setActiveTab] = useState(defaultTab);

        // --- REGISTER FORM (LOGICA INVARIATA) ---
        const registerForm = useForm<z.infer<typeof registerSchema>>({
            resolver: zodResolver(registerSchema),
            defaultValues: {
                firstName: "", lastName: "", email: "", phone: "", telegram: "",
                password: "", confirmPassword: "", terms: false,
            },
        });

        async function onRegisterSubmit(values: z.infer<typeof registerSchema>) {
            setIsLoading(true);
            try {
                const { error } = await supabase.auth.signUp({
                    email: values.email,
                    password: values.password,
                    options: {
                        emailRedirectTo: window.location.origin + '/dashboard',
                        data: {
                            first_name: values.firstName,
                            last_name: values.lastName,
                            phone: values.phone,
                            telegram: values.telegram || null,
                        },
                    },
                });

                if (error) throw error;

                // Salva il lead nella tabella leads (non bloccante)
                try {
                    await supabase.from('leads').insert({
                        first_name: values.firstName,
                        last_name: values.lastName,
                        email: values.email,
                        phone: values.phone,
                        telegram_username: values.telegram || null,
                        source: 'landing_page',
                    });
                } catch (leadError) {
                    console.warn('Errore salvataggio lead (non bloccante):', leadError);
                }

                toast.success("Registrazione completata!", {
                    description: "Controlla la tua email per confermare l'account."
                });
                navigate('/check-email');

            } catch (error: any) {
                toast.error("Errore registrazione", { description: error.message });
            } finally {
                setIsLoading(false);
            }
        }

        // --- LOGIN FORM (LOGICA INVARIATA) ---
        const loginForm = useForm<z.infer<typeof loginSchema>>({
            resolver: zodResolver(loginSchema),
            defaultValues: { email: "", password: "" },
        });

        async function onLoginSubmit(values: z.infer<typeof loginSchema>) {
            setIsLoading(true);
            try {
                const { error } = await supabase.auth.signInWithPassword({
                    email: values.email,
                    password: values.password,
                });

                if (error) throw error;

                toast.success("Login effettuato");
                navigate('/dashboard');

            } catch (error: any) {
                toast.error("Errore Login", { description: "Credenziali non valide o errore di connessione." });
            } finally {
                setIsLoading(false);
            }
        }

        return (
            <section ref={ref} className="py-20 px-4" id="auth-section">
                <div className="max-w-md mx-auto">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                        className="glass-card animated-border rounded-2xl p-8"
                    >
                        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "register" | "login")}>
                            <TabsList className="w-full grid grid-cols-2 mb-6 bg-muted/30">
                                <TabsTrigger value="register" className="font-heading font-bold">
                                    Registrati
                                </TabsTrigger>
                                <TabsTrigger value="login" className="font-heading font-bold">
                                    Accedi
                                </TabsTrigger>
                            </TabsList>

                            {/* REGISTER */}
                            <TabsContent value="register">
                                <Form {...registerForm}>
                                    <form onSubmit={registerForm.handleSubmit(onRegisterSubmit)} className="space-y-4">
                                        <div className="grid grid-cols-2 gap-3">
                                            <FormField
                                                control={registerForm.control}
                                                name="firstName"
                                                render={({ field }) => (
                                                    <FormItem>
                                                        <FormLabel className="text-muted-foreground">Nome *</FormLabel>
                                                        <FormControl>
                                                            <Input placeholder="Mario" className={inputClass} {...field} disabled={isLoading} />
                                                        </FormControl>
                                                        <FormMessage />
                                                    </FormItem>
                                                )}
                                            />
                                            <FormField
                                                control={registerForm.control}
                                                name="lastName"
                                                render={({ field }) => (
                                                    <FormItem>
                                                        <FormLabel className="text-muted-foreground">Cognome *</FormLabel>
                                                        <FormControl>
                                                            <Input placeholder="Rossi" className={inputClass} {...field} disabled={isLoading} />
                                                        </FormControl>
                                                        <FormMessage />
                                                    </FormItem>
                                                )}
                                            />
                                        </div>

                                        <FormField
                                            control={registerForm.control}
                                            name="email"
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className="text-muted-foreground">Email *</FormLabel>
                                                    <FormControl>
                                                        <Input type="email" placeholder="mario@email.com" className={inputClass} {...field} disabled={isLoading} />
                                                    </FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />

                                        <FormField
                                            control={registerForm.control}
                                            name="phone"
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className="text-muted-foreground">Telefono *</FormLabel>
                                                    <FormControl>
                                                        <Input type="tel" placeholder="+39 333 1234567" className={inputClass} {...field} disabled={isLoading} />
                                                    </FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />

                                        <FormField
                                            control={registerForm.control}
                                            name="telegram"
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className="text-muted-foreground">Telegram (opzionale)</FormLabel>
                                                    <FormControl>
                                                        <Input placeholder="@username" className={inputClass} {...field} disabled={isLoading} />
                                                    </FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />

                                        <FormField
                                            control={registerForm.control}
                                            name="password"
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className="text-muted-foreground">Password *</FormLabel>
                                                    <FormControl>
                                                        <Input type="password" placeholder="Min. 8 caratteri" className={inputClass} {...field} disabled={isLoading} />
                                                    </FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />

                                        <FormField
                                            control={registerForm.control}
                                            name="confirmPassword"
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className="text-muted-foreground">Conferma Password *</FormLabel>
                                                    <FormControl>
                                                        <Input type="password" placeholder="Ripeti password" className={inputClass} {...field} disabled={isLoading} />
                                                    </FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />

                                        <FormField
                                            control={registerForm.control}
                                            name="terms"
                                            render={({ field }) => (
                                                <FormItem className="flex items-start gap-3">
                                                    <FormControl>
                                                        <Checkbox checked={field.value} onCheckedChange={field.onChange} className="mt-1" disabled={isLoading} />
                                                    </FormControl>
                                                    <FormLabel className="text-sm text-muted-foreground font-normal leading-tight">
                                                        Accetto i Termini e Condizioni e la Privacy Policy
                                                    </FormLabel>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />

                                        <Button
                                            type="submit"
                                            disabled={isLoading}
                                            className="w-full py-6 text-lg font-heading font-bold pulse-glow neon-glow-primary rounded-xl bg-primary text-primary-foreground hover:bg-primary/90"
                                        >
                                            {isLoading ? (
                                                <span className="flex items-center gap-2">
                                                    <span className="w-5 h-5 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
                                                    Registrazione...
                                                </span>
                                            ) : (
                                                "Inizia la Prova Gratuita"
                                            )}
                                        </Button>
                                    </form>
                                </Form>
                            </TabsContent>

                            {/* LOGIN */}
                            <TabsContent value="login">
                                <Form {...loginForm}>
                                    <form onSubmit={loginForm.handleSubmit(onLoginSubmit)} className="space-y-4">
                                        <FormField
                                            control={loginForm.control}
                                            name="email"
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className="text-muted-foreground">Email</FormLabel>
                                                    <FormControl>
                                                        <Input type="email" placeholder="mario@email.com" className={inputClass} {...field} disabled={isLoading} />
                                                    </FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />

                                        <FormField
                                            control={loginForm.control}
                                            name="password"
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className="text-muted-foreground">Password</FormLabel>
                                                    <FormControl>
                                                        <Input type="password" placeholder="La tua password" className={inputClass} {...field} disabled={isLoading} />
                                                    </FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />

                                        <div className="flex justify-end">
                                            <button
                                                type="button"
                                                onClick={async () => {
                                                    const email = loginForm.getValues('email');
                                                    if (!email) {
                                                        toast.error("Inserisci la tua email prima di richiedere il reset.");
                                                        return;
                                                    }
                                                    try {
                                                        await supabase.auth.resetPasswordForEmail(email, {
                                                            redirectTo: window.location.origin + '/dashboard',
                                                        });
                                                        toast.success("Email di reset inviata!", {
                                                            description: "Controlla la tua casella di posta."
                                                        });
                                                    } catch {
                                                        toast.error("Errore nell'invio dell'email di reset.");
                                                    }
                                                }}
                                                className="text-xs text-muted-foreground hover:text-primary transition-colors"
                                            >
                                                Password dimenticata?
                                            </button>
                                        </div>

                                        <Button
                                            type="submit"
                                            disabled={isLoading}
                                            className="w-full py-6 text-lg font-heading font-bold rounded-xl bg-primary text-primary-foreground hover:bg-primary/90"
                                        >
                                            {isLoading ? (
                                                <span className="flex items-center gap-2">
                                                    <span className="w-5 h-5 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
                                                    Accesso...
                                                </span>
                                            ) : (
                                                "Accedi"
                                            )}
                                        </Button>
                                    </form>
                                </Form>
                            </TabsContent>
                        </Tabs>
                    </motion.div>
                </div>
            </section>
        );
    }
);

AuthSection.displayName = "AuthSection";
