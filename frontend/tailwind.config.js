/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Editorial palette — paper, ink, and a single decisive accent.
        paper: "#f7f4ee",
        ink: "#171615",
        sub: "#615b53",
        rule: "#cfc8bd",
        accent: "#c7361b", // signal red — used sparingly, mostly for warnings/dissent
        gold: "#a98244",   // consensus / executed indicator
        muted: "#eee8de",
      },
      fontFamily: {
        // Use widely-available system serifs + a sans for UI chrome.
        // We pick old-style serifs to evoke financial broadsheets.
        display: ['"Source Serif Pro"', 'Georgia', 'Cambria', 'serif'],
        body: ['"Source Serif Pro"', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'Menlo', 'monospace'],
        ui: ['"Inter"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
      fontSize: {
        masthead: ["3.5rem", { lineHeight: "1.05", letterSpacing: "-0.02em" }],
        deck: ["1.625rem", { lineHeight: "1.2", letterSpacing: "-0.01em" }],
      },
      letterSpacing: {
        tightest: "-0.04em",
      },
      borderWidth: {
        DEFAULT: "1px",
        thin: "0.5px",
        rule: "1px",
      },
      boxShadow: {
        sheet: "0 1px 0 0 rgba(23,22,21,0.06), 0 8px 24px -16px rgba(23,22,21,0.18)",
      },
      animation: {
        "fade-in": "fadeIn 280ms ease-out both",
        "stream-pulse": "streamPulse 1.6s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        streamPulse: {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};
