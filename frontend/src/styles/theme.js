// src/styles/theme.js

const shared = {
  fonts: {
    body: "'Plus Jakarta Sans', sans-serif",
    mono: "'JetBrains Mono', monospace",
  },
};

export const darkTheme = {
  ...shared,
  mode: "dark",
  colors: {
    bg:           "#08090d",
    surface:      "#111318",
    surfaceAlt:   "#191c24",
    surfaceHover: "#1e2130",
    border:       "#262a36",
    borderLight:  "#363c4f",
    text:         "#eaedf4",
    textMuted:    "#8b91a8",
    textDim:      "#525975",
    accent:       "#6c5ce7",
    accentSoft:   "#8075ed",
    accentGlow:   "rgba(108,92,231,0.12)",
    hot:          "#ff6b6b",
    hotGlow:      "rgba(255,107,107,0.10)",
    warm:         "#feca57",
    warmGlow:     "rgba(254,202,87,0.10)",
    cold:         "#576574",
    coldGlow:     "rgba(87,101,116,0.08)",
    green:        "#00d2d3",
    greenGlow:    "rgba(0,210,211,0.10)",
  },
};

export const lightTheme = {
  ...shared,
  mode: "light",
  colors: {
    bg:           "#f5f6fa",
    surface:      "#ffffff",
    surfaceAlt:   "#f0f1f5",
    surfaceHover: "#e8eaf0",
    border:       "#dfe1e8",
    borderLight:  "#c8ccd6",
    text:         "#1a1d2e",
    textMuted:    "#5f6580",
    textDim:      "#9a9eb5",
    accent:       "#6c5ce7",
    accentSoft:   "#8578f0",
    accentGlow:   "rgba(108,92,231,0.08)",
    hot:          "#e55050",
    hotGlow:      "rgba(229,80,80,0.08)",
    warm:         "#d4a020",
    warmGlow:     "rgba(212,160,32,0.08)",
    cold:         "#8a95a5",
    coldGlow:     "rgba(138,149,165,0.06)",
    green:        "#00a8a8",
    greenGlow:    "rgba(0,168,168,0.08)",
  },
};

// Helper functions — accept theme object
export const segmentColor = (segment, theme) => {
  const c = theme.colors;
  return { hot: c.hot, warm: c.warm, cold: c.cold }[segment] || c.cold;
};

export const segmentGlow = (segment, theme) => {
  const c = theme.colors;
  return { hot: c.hotGlow, warm: c.warmGlow, cold: c.coldGlow }[segment] || c.coldGlow;
};

// Default export for backward compat
export default darkTheme;
