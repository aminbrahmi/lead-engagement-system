// src/components/Layout.jsx
import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useTheme } from "../App";

const NAV = [
  { to: "/",          label: "Campaign" },
  { to: "/pipeline",  label: "Pipeline" },
  { to: "/leads",     label: "Leads" },
  { to: "/analytics", label: "Analytics" },
];

function ThemeToggle() {
  const { isDark, toggleTheme, theme } = useTheme();
  const c = theme.colors;
  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      style={{
        width: 44, height: 24, borderRadius: 12, border: `1px solid ${c.border}`,
        background: c.surfaceAlt, cursor: "pointer", position: "relative", padding: 0,
        transition: "background .3s",
      }}
    >
      <div style={{
        width: 18, height: 18, borderRadius: 9,
        background: isDark ? c.accent : c.warm,
        position: "absolute", top: 2,
        left: isDark ? 22 : 3,
        transition: "left .3s, background .3s",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 10,
      }}>
        {isDark ? "\u263D" : "\u2600"}
      </div>
    </button>
  );
}

export default function Layout({ isRunning, leadsCount }) {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;

  return (
    <div style={{
      minHeight: "100vh", background: c.bg, fontFamily: f.body, color: c.text,
      transition: "background .3s, color .3s",
    }}>
      <header style={{
        borderBottom: `1px solid ${c.border}`, padding: "0 32px", height: 56,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: c.surface, position: "sticky", top: 0, zIndex: 50,
        transition: "background .3s",
      }}>
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 7,
            background: `linear-gradient(135deg, ${c.accent}, ${c.hot})`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 13, fontWeight: 800, color: "#fff",
          }}>L</div>
          <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: -0.3 }}>TheLeadFlow</span>
        </div>

        {/* Nav */}
        <nav style={{ display: "flex", gap: 4, height: "100%" }}>
          {NAV.map((item) => (
            <NavLink
              key={item.to} to={item.to} end={item.to === "/"}
              style={({ isActive }) => ({
                padding: "0 18px", height: "100%", display: "flex", alignItems: "center",
                gap: 6, textDecoration: "none",
                color: isActive ? c.text : c.textDim,
                fontSize: 13, fontWeight: isActive ? 600 : 400,
                borderBottom: isActive ? `2px solid ${c.accent}` : "2px solid transparent",
                fontFamily: f.body, transition: "all .2s",
              })}
            >
              {item.label}
              {item.label === "Leads" && leadsCount > 0 && (
                <span style={{
                  fontSize: 10, fontFamily: f.mono, background: c.accentGlow,
                  color: c.accent, padding: "1px 6px", borderRadius: 4,
                }}>{leadsCount}</span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Right: status + toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {isRunning && (
            <span style={{ fontSize: 11, color: c.accent, fontFamily: f.mono, animation: "pulse 1.5s infinite" }}>
              Running
            </span>
          )}
          <ThemeToggle />
        </div>
      </header>

      <main style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 32px" }}>
        <Outlet />
      </main>
    </div>
  );
}
