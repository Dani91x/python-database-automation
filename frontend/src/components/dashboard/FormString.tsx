import { cn } from "@/lib/utils";

export function FormString({ form }: { form: string }) {
    if (!form) return null;

    return (
        <div className="flex gap-1">
            {form.split('').map((char, i) => {
                let color = "bg-gray-500";
                if (char === 'W') color = "bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]";
                if (char === 'L') color = "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]";
                if (char === 'D') color = "bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.4)]";

                return (
                    <div key={i} className={cn("w-6 h-6 rounded flex items-center justify-center text-[10px] font-black text-black", color)}>
                        {char}
                    </div>
                );
            })}
        </div>
    );
}
