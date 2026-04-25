import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0f",
        panel: "#12121a",
        panel2: "#1a1a25",
        border: "#26263a",
        accent: "#7c5cff",
        accent2: "#22d3ee",
        success: "#22c55e",
        danger: "#ef4444",
        muted: "#9ca3af",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(124,92,255,0.2), 0 12px 60px -10px rgba(124,92,255,0.4)",
      },
    },
  },
  plugins: [],
};

export default config;
