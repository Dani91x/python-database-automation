export function LandingFooter() {
    return (
        <footer className="py-8 px-4 border-t border-border/30">
            <div className="max-w-6xl mx-auto text-center">
                <p className="text-muted-foreground/60 text-sm">
                    © 2025 AI Football Predictions — Powered by Advanced Algorithms
                </p>
                <div className="flex justify-center gap-6 mt-3 text-xs text-muted-foreground/40">
                    <span className="hover:text-primary cursor-pointer transition-colors">Privacy Policy</span>
                    <span className="hover:text-primary cursor-pointer transition-colors">Termini</span>
                    <span className="hover:text-primary cursor-pointer transition-colors">Contatti</span>
                </div>
            </div>
        </footer>
    );
}
