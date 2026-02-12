/** @type {import('tailwindcss').Config} */
export default {
	darkMode: ["class"],
	content: [
		"./index.html",
		"./src/**/*.{js,ts,jsx,tsx}",
	],
	prefix: "",
	theme: {
		container: {
			center: true,
			padding: "2rem",
			screens: {
				"2xl": "1400px",
			},
		},
		extend: {
			fontFamily: {
				display: ["Orbitron", "sans-serif"],
				heading: ["Rajdhani", "sans-serif"],
				sans: ["Inter", "system-ui", "sans-serif"],
				// Backward compat aliases
				orbitron: ["Orbitron", "sans-serif"],
				rajdhani: ["Rajdhani", "sans-serif"],
				inter: ["Inter", "sans-serif"],
			},
			colors: {
				border: "hsl(var(--border))",
				input: "hsl(var(--input))",
				ring: "hsl(var(--ring))",
				background: "hsl(var(--background))",
				foreground: "hsl(var(--foreground))",
				primary: {
					DEFAULT: "hsl(var(--primary))",
					foreground: "hsl(var(--primary-foreground))",
				},
				secondary: {
					DEFAULT: "hsl(var(--secondary))",
					foreground: "hsl(var(--secondary-foreground))",
				},
				destructive: {
					DEFAULT: "hsl(var(--destructive))",
					foreground: "hsl(var(--destructive-foreground))",
				},
				muted: {
					DEFAULT: "hsl(var(--muted))",
					foreground: "hsl(var(--muted-foreground))",
				},
				accent: {
					DEFAULT: "hsl(var(--accent))",
					foreground: "hsl(var(--accent-foreground))",
				},
				popover: {
					DEFAULT: "hsl(var(--popover))",
					foreground: "hsl(var(--popover-foreground))",
				},
				card: {
					DEFAULT: "hsl(var(--card))",
					foreground: "hsl(var(--card-foreground))",
				},
				sidebar: {
					DEFAULT: "hsl(var(--sidebar-background))",
					foreground: "hsl(var(--sidebar-foreground))",
					primary: "hsl(var(--sidebar-primary))",
					"primary-foreground": "hsl(var(--sidebar-primary-foreground))",
					accent: "hsl(var(--sidebar-accent))",
					"accent-foreground": "hsl(var(--sidebar-accent-foreground))",
					border: "hsl(var(--sidebar-border))",
					ring: "hsl(var(--sidebar-ring))",
				},
				neon: {
					cyan: "hsl(var(--neon-cyan))",
					magenta: "hsl(var(--neon-magenta))",
					green: "hsl(var(--neon-green))",
					orange: "hsl(var(--neon-orange))",
					blue: "hsl(var(--neon-blue))",
				},
				team: {
					home: "hsl(var(--home-team))",
					away: "hsl(var(--away-team))",
				},
				result: {
					win: "hsl(var(--win))",
					draw: "hsl(var(--draw))",
					loss: "hsl(var(--loss))",
				},
				// Backward compat
				"neon-cyan": "hsl(var(--neon-cyan))",
				"neon-magenta": "hsl(var(--neon-magenta))",
				"brand-orange": "hsl(var(--brand-orange))",
			},
			borderRadius: {
				lg: "var(--radius)",
				md: "calc(var(--radius) - 2px)",
				sm: "calc(var(--radius) - 4px)",
			},
			keyframes: {
				"accordion-down": {
					from: { height: "0" },
					to: { height: "var(--radix-accordion-content-height)" },
				},
				"accordion-up": {
					from: { height: "var(--radix-accordion-content-height)" },
					to: { height: "0" },
				},
				"fade-in": {
					"0%": { opacity: "0", transform: "translateY(10px)" },
					"100%": { opacity: "1", transform: "translateY(0)" },
				},
				"slide-in-left": {
					"0%": { opacity: "0", transform: "translateX(-20px)" },
					"100%": { opacity: "1", transform: "translateX(0)" },
				},
				"slide-in-right": {
					"0%": { opacity: "0", transform: "translateX(20px)" },
					"100%": { opacity: "1", transform: "translateX(0)" },
				},
				"scale-in": {
					"0%": { opacity: "0", transform: "scale(0.95)" },
					"100%": { opacity: "1", transform: "scale(1)" },
				},
				"pulse-subtle": {
					"0%, 100%": { opacity: "1" },
					"50%": { opacity: "0.7" },
				},
				"glow": {
					"0%, 100%": { boxShadow: "0 0 20px hsl(var(--primary) / 0.3)" },
					"50%": { boxShadow: "0 0 40px hsl(var(--primary) / 0.5)" },
				},
			},
			animation: {
				"accordion-down": "accordion-down 0.2s ease-out",
				"accordion-up": "accordion-up 0.2s ease-out",
				"fade-in": "fade-in 0.5s ease-out forwards",
				"slide-in-left": "slide-in-left 0.5s ease-out forwards",
				"slide-in-right": "slide-in-right 0.5s ease-out forwards",
				"scale-in": "scale-in 0.3s ease-out forwards",
				"pulse-subtle": "pulse-subtle 2s ease-in-out infinite",
				"glow": "glow 2s ease-in-out infinite",
			},
			backgroundImage: {
				"gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
				"gradient-conic": "conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))",
			},
		},
	},
	plugins: [require("tailwindcss-animate")],
}
