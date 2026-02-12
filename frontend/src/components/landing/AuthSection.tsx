import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { supabase } from '@/integrations/supabase/client';
import { useNavigate } from 'react-router-dom';
import { Loader2, Lock, Mail, Phone, User as UserIcon, Send } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Checkbox } from '@/components/ui/checkbox';
import {
    Form, FormControl, FormField, FormItem, FormLabel, FormMessage
} from '@/components/ui/form';
import { Card, CardContent } from '@/components/ui/card';

// --- SCHEMAS ---
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

export function AuthSection() {
    const navigate = useNavigate();
    const [isLoading, setIsLoading] = useState(false);

    // --- REGISTER FORM ---
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

            toast.success("Registrazione completata!", {
                description: "Controlla la tua email per confermare l'account o accedi subito."
            });
            navigate('/dashboard');

        } catch (error: any) {
            toast.error("Errore registrazione", { description: error.message });
        } finally {
            setIsLoading(false);
        }
    }

    // --- LOGIN FORM ---
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
        <section id="auth" className="py-24 relative">
            <div className="container mx-auto px-6 flex justify-center">
                <Card className="glass-card w-full max-w-lg overflow-hidden relative border-brand-orange/20 animate-fade-in">
                    {/* Decorazioni */}
                    <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-brand-orange to-transparent opacity-50" />

                    <CardContent className="p-8">
                        <div className="text-center mb-8">
                            <h2 className="text-2xl font-orbitron font-bold mb-2">Accedi al Terminale</h2>
                            <p className="text-sm text-muted-foreground">Inizia la tua prova gratuita di 7 giorni</p>
                        </div>

                        <Tabs defaultValue="register" className="w-full">
                            <TabsList className="grid w-full grid-cols-2 mb-8 bg-black/20">
                                <TabsTrigger value="register">Registrati</TabsTrigger>
                                <TabsTrigger value="login">Accedi</TabsTrigger>
                            </TabsList>

                            {/* REGISTER TAB */}
                            <TabsContent value="register">
                                <Form {...registerForm}>
                                    <form onSubmit={registerForm.handleSubmit(onRegisterSubmit)} className="space-y-4">
                                        <div className="grid grid-cols-2 gap-4">
                                            <FormField
                                                control={registerForm.control}
                                                name="firstName"
                                                render={({ field }) => (
                                                    <FormItem>
                                                        <FormLabel>Nome</FormLabel>
                                                        <FormControl>
                                                            <Input placeholder="Mario" {...field} disabled={isLoading} />
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
                                                        <FormLabel>Cognome</FormLabel>
                                                        <FormControl>
                                                            <Input placeholder="Rossi" {...field} disabled={isLoading} />
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
                                                    <FormLabel>Email</FormLabel>
                                                    <FormControl>
                                                        <div className="relative">
                                                            <Mail className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                                                            <Input className="pl-9" placeholder="mario@example.com" {...field} disabled={isLoading} />
                                                        </div>
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
                                                    <FormLabel>Telefono</FormLabel>
                                                    <FormControl>
                                                        <div className="relative">
                                                            <Phone className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                                                            <Input className="pl-9" placeholder="+39 333..." {...field} disabled={isLoading} />
                                                        </div>
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
                                                    <FormLabel>Telegram (Opzionale)</FormLabel>
                                                    <FormControl>
                                                        <div className="relative">
                                                            <Send className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                                                            <Input className="pl-9" placeholder="@username" {...field} disabled={isLoading} />
                                                        </div>
                                                    </FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />

                                        <div className="grid grid-cols-2 gap-4">
                                            <FormField
                                                control={registerForm.control}
                                                name="password"
                                                render={({ field }) => (
                                                    <FormItem>
                                                        <FormLabel>Password</FormLabel>
                                                        <FormControl>
                                                            <div className="relative">
                                                                <Lock className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                                                                <Input type="password" className="pl-9" placeholder="Min. 8 caratteri" {...field} disabled={isLoading} />
                                                            </div>
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
                                                        <FormLabel>Conferma</FormLabel>
                                                        <FormControl>
                                                            <div className="relative">
                                                                <Lock className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                                                                <Input type="password" className="pl-9" placeholder="Ripeti password" {...field} disabled={isLoading} />
                                                            </div>
                                                        </FormControl>
                                                        <FormMessage />
                                                    </FormItem>
                                                )}
                                            />
                                        </div>

                                        <FormField
                                            control={registerForm.control}
                                            name="terms"
                                            render={({ field }) => (
                                                <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md border border-white/10 p-4 bg-white/5">
                                                    <FormControl>
                                                        <Checkbox
                                                            checked={field.value}
                                                            onCheckedChange={field.onChange}
                                                            disabled={isLoading}
                                                        />
                                                    </FormControl>
                                                    <div className="space-y-1 leading-none">
                                                        <FormLabel>
                                                            Accetto i Termini e Condizioni
                                                        </FormLabel>
                                                    </div>
                                                </FormItem>
                                            )}
                                        />

                                        <Button type="submit" className="w-full bg-brand-orange hover:bg-white text-black font-bold neon-glow mt-4" disabled={isLoading}>
                                            {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : "Inizia la Prova Gratuita"}
                                        </Button>
                                    </form>
                                </Form>
                            </TabsContent>

                            {/* LOGIN TAB */}
                            <TabsContent value="login">
                                <Form {...loginForm}>
                                    <form onSubmit={loginForm.handleSubmit(onLoginSubmit)} className="space-y-4">
                                        <FormField
                                            control={loginForm.control}
                                            name="email"
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel>Email</FormLabel>
                                                    <FormControl>
                                                        <div className="relative">
                                                            <Mail className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                                                            <Input className="pl-9" {...field} disabled={isLoading} />
                                                        </div>
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
                                                    <FormLabel>Password</FormLabel>
                                                    <FormControl>
                                                        <div className="relative">
                                                            <Lock className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                                                            <Input type="password" className="pl-9" {...field} disabled={isLoading} />
                                                        </div>
                                                    </FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />

                                        <Button type="submit" className="w-full bg-brand-orange hover:bg-white text-black font-bold neon-glow" disabled={isLoading}>
                                            {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : "Accedi"}
                                        </Button>
                                    </form>
                                </Form>
                            </TabsContent>
                        </Tabs>
                    </CardContent>
                </Card>
            </div>
        </section>
    );
}
