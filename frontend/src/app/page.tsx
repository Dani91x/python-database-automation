// frontend/src/app/page.tsx
import Image from 'next/image';
import Link from 'next/link';
import {
  Zap,
  ArrowRight,
  ChevronRight,
  BarChart3,
  ShieldCheck,
  Globe,
  Cpu,
  Trophy,
  Target,
  BrainCircuit,
  Layers,
  Activity
} from 'lucide-react';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-black text-white selection:bg-brand-orange/30 overflow-x-hidden">
      {/* Dynamic Hero Glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-brand-orange/[0.07] blur-[150px] rounded-full animate-pulse-slow" />
        <div className="absolute bottom-[-5%] right-[-5%] w-[40%] h-[40%] bg-brand-orange/[0.05] blur-[120px] rounded-full animate-pulse-slow" style={{ animationDelay: '2s' }} />
      </div>

      {/* Navigation */}
      <nav className="fixed top-0 w-full z-[100] border-b border-white/5 bg-black/40 backdrop-blur-xl">
        <div className="container mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <Link href="/" className="shrink-0">
              <Image src="/logo.jpg" alt="Logo" width={150} height={38} className="object-contain" />
            </Link>
            <div className="hidden lg:flex items-center gap-8 text-[10px] font-black uppercase tracking-[0.2em] text-gray-400">
              <Link href="#engine" className="hover:text-white transition-colors">Engine</Link>
              <Link href="#stats" className="hover:text-white transition-colors">Stats</Link>
              <Link href="#pricing" className="hover:text-white transition-colors">Pricing</Link>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <Link href="/dashboard" className="hidden sm:flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] hover:text-brand-orange transition-colors">
              Client Access <ChevronRight className="w-3 h-3" />
            </Link>
            <Link
              href="/dashboard"
              className="bg-brand-orange text-black px-6 py-2.5 rounded-full text-[10px] font-black uppercase tracking-[0.2em] hover:scale-105 active:scale-95 transition-all shadow-[0_0_20px_rgba(255,153,0,0.3)]"
            >
              Open Terminal
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <header className="relative pt-40 pb-24 overflow-hidden">
        <div className="container mx-auto px-6 relative z-10 text-center">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-[10px] font-black uppercase tracking-[0.2em] text-brand-orange mb-8 animate-fade-in">
            <Cpu className="w-3 h-3" />
            Proprietary Neural Engine v4.0 is Live
          </div>

          <h1 className="text-6xl md:text-8xl lg:text-9xl font-black tracking-tighter uppercase italic leading-[0.85] mb-8 animate-fade-in-up">
            Profit is <br />
            <span className="text-brand-orange">Calculable.</span>
          </h1>

          <p className="max-w-2xl mx-auto text-lg md:text-xl text-gray-400 font-medium leading-relaxed mb-12 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
            The first sports investment terminal powered by deep-learning models.
            We don't bet on games. We arbitrage statistical discrepancies across top-tier competitive leagues.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-6 animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
            <Link
              href="/dashboard"
              className="w-full sm:w-auto bg-brand-orange text-black px-12 py-5 rounded-2xl text-sm font-black uppercase tracking-[0.1em] flex items-center justify-center gap-3 group transition-all hover:bg-white"
            >
              Explore Live Markets
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </Link>
            <Link
              href="#engine"
              className="w-full sm:w-auto px-12 py-5 rounded-2xl text-sm font-black uppercase tracking-[0.1em] border border-white/10 hover:bg-white/5 transition-all flex items-center justify-center gap-3"
            >
              The Algorithm
            </Link>
          </div>

          {/* Stats Ribbon */}
          <div className="mt-24 grid grid-cols-2 md:grid-cols-4 gap-4 max-w-5xl mx-auto animate-fade-in" style={{ animationDelay: '0.4s' }}>
            {[
              { label: 'Annual Yield', val: '+42.8%', icon: Trophy },
              { label: 'Match Analysis', val: '1.2M+', icon: Activity },
              { label: 'ML Accuracy', val: '86.4%', icon: BrainCircuit },
              { label: 'Execution', val: '< 20ms', icon: Zap }
            ].map((stat, i) => (
              <div key={i} className="glass-panel p-6 rounded-3xl border-white/5 text-center">
                <stat.icon className="w-5 h-5 mx-auto mb-3 text-brand-orange opacity-50" />
                <div className="text-2xl font-black tracking-tighter italic">{stat.val}</div>
                <div className="text-[10px] font-black uppercase tracking-widest text-gray-500 mt-1">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </header>

      {/* Features / Engine */}
      <section id="engine" className="py-24 relative">
        <div className="container mx-auto px-6">
          <div className="grid lg:grid-cols-2 gap-20 items-center">
            <div className="space-y-8">
              <div className="text-brand-orange text-xs font-black uppercase tracking-[0.3em]">System Architecture</div>
              <h2 className="text-5xl md:text-6xl font-black uppercase tracking-tighter italic leading-none">
                Quantitative <br />
                Edge.
              </h2>
              <p className="text-gray-400 text-lg leading-relaxed">
                Our "Insight Engine" processes over 2,500 data points per fixture—from expected goals (xG) and transition efficiency to specialized metrics like clean-sheet coefficients and relative form progression.
              </p>

              <ul className="space-y-6">
                {[
                  { title: 'Data Normalization', desc: 'Syncing disparate feeds into a unified analytical structure.', icon: Layers },
                  { title: 'Poisson Distribution', desc: 'Calculating probability densities for every localized outcome.', icon: Target },
                  { title: 'Neural Back-testing', desc: 'Models refined against 10 years of historical league data.', icon: BrainCircuit }
                ].map((item, i) => (
                  <li key={i} className="flex gap-6 group">
                    <div className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center shrink-0 group-hover:border-brand-orange/30 transition-colors">
                      <item.icon className="w-5 h-5 text-brand-orange" />
                    </div>
                    <div>
                      <h4 className="text-sm font-black uppercase tracking-widest mb-1">{item.title}</h4>
                      <p className="text-sm text-gray-500">{item.desc}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <div className="relative">
              <div className="absolute -inset-10 bg-brand-orange/10 blur-[100px] rounded-full" />
              <div className="glass-panel p-8 rounded-[3rem] border-white/10 relative overflow-hidden group">
                <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/5">
                  <span className="text-[10px] font-black uppercase tracking-widest text-gray-500">Live Terminal View</span>
                  <div className="flex gap-1.5">
                    <div className="w-2 h-2 rounded-full bg-red-500/20" />
                    <div className="w-2 h-2 rounded-full bg-yellow-500/20" />
                    <div className="w-2 h-2 rounded-full bg-green-500/20" />
                  </div>
                </div>
                <div className="space-y-6">
                  <div className="h-6 w-3/4 bg-white/5 rounded-full animate-pulse" />
                  <div className="h-40 w-full bg-white/5 rounded-3xl animate-pulse" style={{ animationDelay: '0.2s' }} />
                  <div className="grid grid-cols-3 gap-4">
                    <div className="h-20 bg-brand-orange/5 rounded-2xl animate-pulse" style={{ animationDelay: '0.4s' }} />
                    <div className="h-20 bg-white/5 rounded-2xl animate-pulse" style={{ animationDelay: '0.6s' }} />
                    <div className="h-20 bg-white/5 rounded-2xl animate-pulse" style={{ animationDelay: '0.8s' }} />
                  </div>
                </div>
                <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent flex items-end justify-center pb-12">
                  <Link href="/dashboard" className="text-[10px] font-black uppercase tracking-[0.2em] bg-white text-black px-6 py-3 rounded-xl hover:scale-105 transition-transform">
                    View Full Analyzer
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Social / CTA */}
      <section className="py-32 relative overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-screen h-px bg-brand-orange/20" />
        <div className="container mx-auto px-6 relative z-10 text-center">
          <h2 className="text-4xl md:text-6xl font-black uppercase tracking-tighter italic mb-8">
            Stop Guessing. <br />
            <span className="text-brand-orange">Start Trading.</span>
          </h2>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-4 bg-white text-black px-16 py-6 rounded-full text-lg font-black uppercase tracking-widest hover:scale-110 active:scale-95 transition-all shadow-[0_30px_60px_-15px_rgba(255,255,255,0.2)]"
          >
            Access Terminal
            <ChevronRight className="w-6 h-6 text-brand-orange" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 border-t border-white/5">
        <div className="container mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-8">
          <Image src="/logo.jpg" alt="Logo" width={120} height={30} className="object-contain opacity-40 grayscale" />
          <div className="flex gap-12 text-[10px] font-black uppercase tracking-[0.2em] text-gray-500">
            <Link href="#" className="hover:text-white transition-colors">Risk Disclaimer</Link>
            <Link href="#" className="hover:text-white transition-colors">Privacy</Link>
            <Link href="#" className="hover:text-white transition-colors">Contact</Link>
          </div>
          <div className="text-[9px] font-bold text-gray-600 uppercase tracking-widest">
            Developed for Sport Investing Professionals
          </div>
        </div>
      </footer>
    </div>
  );
}
