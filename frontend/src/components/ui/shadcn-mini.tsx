// frontend/src/components/ui/shadcn-mini.tsx
import * as React from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

// Badge
const Badge = ({ className, variant = "default", ...props }: React.HTMLAttributes<HTMLDivElement> & { variant?: 'default' | 'secondary' | 'destructive' | 'outline' | 'neon' }) => {
    const variants = {
        default: "bg-brand-orange text-white",
        secondary: "bg-white/10 text-white",
        destructive: "bg-red-500 text-white",
        outline: "border border-white/20 text-white",
        neon: "bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/30"
    };
    return (
        <div className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors", variants[variant], className)} {...props} />
    );
};

// Progress
const Progress = ({ value = 0, className, barClassName }: { value?: number, className?: string, barClassName?: string }) => (
    <div className={cn("relative h-2 w-full overflow-hidden rounded-full bg-white/10", className)}>
        <div
            className={cn("h-full w-full flex-1 bg-brand-orange transition-all", barClassName)}
            style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
        />
    </div>
);

// Card
const Card = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
    <div className={cn("glass-card rounded-[2rem] p-6 text-white", className)} {...props} />
);

// Tabs
const Tabs = ({ children, defaultValue, className }: { children: React.ReactNode, defaultValue?: string, className?: string }) => {
    const [value, setValue] = React.useState(defaultValue);
    return (
        <div className={cn("space-y-4", className)}>
            {React.Children.map(children, child => {
                if (React.isValidElement(child)) {
                    // @ts-ignore
                    return React.cloneElement(child, { activeValue: value, onValueChange: setValue });
                }
                return child;
            })}
        </div>
    );
};

const TabsList = ({ children, className, activeValue, onValueChange }: any) => (
    <div className={cn("inline-flex h-10 items-center justify-center rounded-lg bg-white/5 p-1 text-gray-400", className)}>
        {React.Children.map(children, child => {
            if (React.isValidElement(child)) {
                return React.cloneElement(child, { activeValue, onValueChange });
            }
            return child;
        })}
    </div>
);

const TabsTrigger = ({ value, children, className, activeValue, onValueChange }: any) => (
    <button
        onClick={() => onValueChange(value)}
        className={cn(
            "inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-all focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
            activeValue === value ? "bg-brand-orange text-white shadow-sm" : "hover:text-white",
            className
        )}
    >
        {children}
    </button>
);

const TabsContent = ({ value, children, className, activeValue }: any) => (
    activeValue === value ? <div className={cn("mt-2", className)}>{children}</div> : null
);

// Table
const Table = ({ className, ...props }: React.HTMLAttributes<HTMLTableElement>) => (
    <div className="relative w-full overflow-auto">
        <table className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
);

const TableHeader = ({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) => (
    <thead className={cn("[&_tr]:border-b border-white/10", className)} {...props} />
);

const TableBody = ({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) => (
    <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />
);

const TableRow = ({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) => (
    <tr className={cn("border-b border-white/5 transition-colors hover:bg-white/5 data-[state=selected]:bg-muted", className)} {...props} />
);

const TableHead = ({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) => (
    <th className={cn("h-12 px-4 text-left align-middle font-medium text-gray-500 [&:has([role=checkbox])]:pr-0", className)} {...props} />
);

const TableCell = ({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) => (
    <td className={cn("p-4 align-middle [&:has([role=checkbox])]:pr-0", className)} {...props} />
);

export {
    Badge,
    Progress,
    Card,
    Tabs,
    TabsList,
    TabsTrigger,
    TabsContent,
    Table,
    TableHeader,
    TableBody,
    TableRow,
    TableHead,
    TableCell,
    cn
};
