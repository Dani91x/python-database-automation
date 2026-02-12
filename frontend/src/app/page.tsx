import Image from 'next/image';
import LeadForm from '@/components/LeadForm';
import { Rocket, ShieldCheck, BarChart3, BrainCircuit } from 'lucide-react';

export default function LandingPage() {
  return (
    <main className="min-h-screen">
      {/* Hero Section */}
      <nav className="container mx-auto px-6 py-8 flex justify-between items-center">
        <div className="relative w-48 h-12">
          <Image
            src="/logo.jpg"
            alt="Sport Investing Logo"
            fill
            className="object-contain"
            priority
          />
        </div>
        <div className="hidden md:flex gap-8 text-sm font-bold uppercase tracking-widest text-white/60">
          <a href="#stats" className="hover:text-brand-orange transition-colors">Dati</a>
          <a href="#ai" className="hover:text-brand-orange transition-colors">AI Analysis</a>
          <a href="#leads" className="hover:text-brand-orange transition-colors">Inizia Prova</a>
        </div>
      </nav>

      <div className="container mx-auto px-6 pt-12 pb-24 grid lg:grid-cols-2 gap-16 items-center">
        <div className="space-y-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-orange/10 border border-brand-orange/20 text-brand-orange text-xs font-black uppercase tracking-tighter">
            <Rocket className="w-3 h-3" />
            La nuova era del Betting Strategico
          </div>

          <h1 className="text-5xl md:text-7xl font-black leading-tight">
            NON SCOMMETTERE.<br />
            <span className="text-brand-orange italic tracking-tighter">INVESTI</span> NEI DATI.
          </h1>

          <p className="text-lg text-gray-400 max-w-xl leading-relaxed">
            Sport Investing è il primo sistema di analisi quantitativa che trasforma il calcio in una classe di asset.
            Il nostro algoritmo analizza ogni notte migliaia di variabili per fornirti solo i segnali ad alta probabilità.
          </p>

          <div className="grid grid-cols-2 gap-6 pt-4">
            <div className="flex gap-4 items-start">
              <div className="p-2 rounded-lg bg-white/5 border border-brand-orange/20">
                <BarChart3 className="w-5 h-5 text-brand-orange" />
              </div>
              <div>
                <h4 className="font-bold">Data Driven</h4>
                <p className="text-xs text-gray-500">Migliaia di match analizzati ogni giorno.</p>
              </div>
            </div>
            <div className="flex gap-4 items-start">
              <div className="p-2 rounded-lg bg-white/5 border border-brand-orange/20">
                <BrainCircuit className="w-5 h-5 text-brand-orange" />
              </div>
              <div>
                <h4 className="font-bold">AI Prediction</h4>
                <p className="text-xs text-gray-500">Modelli LLM per analisi testuali profonde.</p>
              </div>
            </div>
          </div>
        </div>

        <div id="leads" className="relative">
          <div className="absolute -inset-4 bg-brand-orange/20 blur-3xl rounded-full opacity-20" />
          <LeadForm />
        </div>
      </div>

      {/* Trust Section */}
      <section id="stats" className="bg-white/[0.02] border-y border-white/5 py-24">
        <div className="container mx-auto px-6">
          <div className="text-center space-y-4 mb-16">
            <h2 className="text-4xl font-black uppercase tracking-tighter">Autorità nei Dati</h2>
            <p className="text-gray-500 max-w-2xl mx-auto">
              Siamo trasparenti. Ogni pronostico viene archiviato e valutato dal sistema per garantirti la massima affidabilità storica.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            <div className="glass-panel p-8 rounded-2xl text-center border-white/5">
              <div className="text-5xl font-black text-white mb-2">950+</div>
              <div className="text-xs font-bold uppercase tracking-widest text-brand-orange">Migliaia di Fixtures</div>
            </div>
            <div className="glass-panel p-8 rounded-2xl text-center border-white/5">
              <div className="text-5xl font-black text-white mb-2">320+</div>
              <div className="text-xs font-bold uppercase tracking-widest text-brand-orange">Leghe Monitorate</div>
            </div>
            <div className="glass-panel p-8 rounded-2xl text-center border-brand-orange/20 scale-105 shadow-2xl">
              <div className="text-5xl font-black text-white mb-2">82%</div>
              <div className="text-xs font-bold uppercase tracking-widest text-brand-orange">Win Rate Algoritmo</div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 border-t border-white/5 text-center">
        <p className="text-xs text-gray-600 uppercase tracking-widest font-bold">
          © 2026 SPORT INVESTING • DATA DRIVEN STRATEGIES
        </p>
      </footer>
    </main>
  );
}
