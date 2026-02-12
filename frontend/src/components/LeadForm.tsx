'use client';

import { useState } from 'react';
import { supabase } from '@/lib/supabase';
import { Loader2, CheckCircle } from 'lucide-react';

export default function LeadForm() {
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState(false);
    const [formData, setFormData] = useState({
        firstName: '',
        lastName: '',
        email: '',
        phone: '',
        telegram: ''
    });

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);

        try {
            const { error } = await supabase.table('leads').insert({
                first_name: formData.firstName,
                last_name: formData.lastName,
                email: formData.email,
                phone: formData.phone,
                telegram_username: formData.telegram,
                source: 'landing_page'
            });

            if (error) throw error;
            setSuccess(true);
        } catch (err) {
            console.error('Error saving lead:', err);
            alert('Si è verificato un errore. Riprova più tardi.');
        } finally {
            setLoading(false);
        }
    };

    if (success) {
        return (
            <div className="glass-panel p-8 rounded-2xl text-center border-brand-orange/30">
                <CheckCircle className="w-16 h-16 text-brand-orange mx-auto mb-4" />
                <h3 className="text-2xl font-bold mb-2">Benvenuto a Bordo!</h3>
                <p className="text-gray-400 mb-6">
                    I tuoi dati sono stati registrati. Ora puoi accedere all'anteprima dei pronostici.
                </p>
                <button
                    onClick={() => window.location.href = '/dashboard'}
                    className="brand-gradient px-8 py-3 rounded-full font-bold hover:scale-105 transition-transform"
                >
                    Vai alla Dashboard
                </button>
            </div>
        );
    }

    return (
        <form onSubmit={handleSubmit} className="glass-panel p-8 rounded-2xl border-white/10 space-y-4">
            <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                    <label className="text-xs uppercase tracking-widest text-gray-500 font-bold">Nome</label>
                    <input
                        required
                        type="text"
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 focus:border-brand-orange outline-none transition-colors"
                        value={formData.firstName}
                        onChange={e => setFormData({ ...formData, firstName: e.target.value })}
                    />
                </div>
                <div className="space-y-1">
                    <label className="text-xs uppercase tracking-widest text-gray-500 font-bold">Cognome</label>
                    <input
                        required
                        type="text"
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 focus:border-brand-orange outline-none transition-colors"
                        value={formData.lastName}
                        onChange={e => setFormData({ ...formData, lastName: e.target.value })}
                    />
                </div>
            </div>

            <div className="space-y-1">
                <label className="text-xs uppercase tracking-widest text-gray-500 font-bold">Email</label>
                <input
                    required
                    type="email"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 focus:border-brand-orange outline-none transition-colors"
                    value={formData.email}
                    onChange={e => setFormData({ ...formData, email: e.target.value })}
                />
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                    <label className="text-xs uppercase tracking-widest text-gray-500 font-bold">Telefono</label>
                    <input
                        type="tel"
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 focus:border-brand-orange outline-none transition-colors"
                        value={formData.phone}
                        onChange={e => setFormData({ ...formData, phone: e.target.value })}
                    />
                </div>
                <div className="space-y-1">
                    <label className="text-xs uppercase tracking-widest text-gray-500 font-bold">Telegram (Opezionale)</label>
                    <input
                        type="text"
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 focus:border-brand-orange outline-none transition-colors"
                        placeholder="@username"
                        value={formData.telegram}
                        onChange={e => setFormData({ ...formData, telegram: e.target.value })}
                    />
                </div>
            </div>

            <button
                disabled={loading}
                type="submit"
                className="w-full brand-gradient py-4 rounded-xl font-black text-lg uppercase tracking-wider hover:brightness-110 transition-all disabled:opacity-50 mt-4 flex items-center justify-center gap-2"
            >
                {loading && <Loader2 className="animate-spin" />}
                Inizia la Prova Gratuita 7 Giorni
            </button>

            <p className="text-[10px] text-gray-600 text-center uppercase tracking-tighter">
                Nessuna carta di credito richiesta. I tuoi dati sono al sicuro.
            </p>
        </form>
    );
}
