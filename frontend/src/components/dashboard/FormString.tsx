import { cn } from "@/lib/utils";

export function FormString({ form }: { form: string }) {
    if (!form) return null;

    const counts = {
        W: (form.match(/W/g) || []).length,
        D: (form.match(/D/g) || []).length,
        L: (form.match(/L/g) || []).length,
    };

    return (
        <div className="flex flex-col gap-2">
            <div className="flex gap-1">
                {form.split('').map((char, i) => {
                    let pillClass = "bg-muted text-muted-foreground";
                    if (char === 'W') pillClass = "form-pill-w";
                    if (char === 'D') pillClass = "form-pill-d";
                    if (char === 'L') pillClass = "form-pill-l";

                    return (
                        <div key={i} className={cn("form-pill", pillClass)}>
                            {char}
                        </div>
                    );
                })}
            </div>

            <div className="flex gap-3 text-xs font-bold font-mono mt-1">
                <span className="text-result-win">W: {counts.W}</span>
                <span className="text-result-draw">D: {counts.D}</span>
                <span className="text-destructive">L: {counts.L}</span>
            </div>
        </div>
    );
}
