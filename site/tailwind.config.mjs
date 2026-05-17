/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}"],
  theme: {
    extend: {
      colors: {
        paper:   "#FAF8F3",   // warm off-white background
        ink:     "#1F2937",   // dark slate body text
        muted:   "#6B7280",   // captions / meta
        rule:    "#E5E1D8",   // hairline separators
        accent:  "#1E3A5F",   // deep navy headings / links
        accent2: "#7C2D12",   // burgundy for callouts
        term:    "#0F1419",   // terminal background
        termfg:  "#A6E22E",   // terminal foreground (greenish)
        termdim: "#75715E",   // terminal dim text
      },
      fontFamily: {
        serif: ['"Spectral"', '"EB Garamond"', "Georgia", "serif"],
        sans:  ['"Inter Tight"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono:  ['"JetBrains Mono"', "ui-monospace", "Menlo", "Consolas", "monospace"],
      },
      maxWidth: {
        paper: "720px",
        wide:  "980px",
      },
      typography: ({ theme }) => ({
        paper: {
          css: {
            "--tw-prose-body": theme("colors.ink"),
            "--tw-prose-headings": theme("colors.accent"),
            "--tw-prose-links": theme("colors.accent"),
            "--tw-prose-code": theme("colors.accent2"),
          },
        },
      }),
    },
  },
  plugins: [],
};
