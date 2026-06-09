// src/components/Layout.jsx
import React, { useState, useEffect, useRef } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import logo from "../theleadflowlogo.png";
import { useTheme } from "../App";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

// Types that should navigate to the inbox conversation
const REPLY_TYPES = new Set([
  "reply_interested", "reply_declined", "reply_info_request",
  "reply_ooo", "email_bounced",
  "link_clicked",
  "calendar_accepted", "calendar_declined", "calendar_response",
]);

const TYPE_ICON = {
  link_clicked:       "\uD83D\uDD17",
  reply_interested:   "\u2705",
  reply_declined:     "\u274C",
  reply_info_request: "\uD83D\uDCAC",
  reply_ooo:          "\uD83C\uDFD6\uFE0F",
  email_bounced:      "\u26A0\uFE0F",
  email_opened:       "\uD83D\uDC41",
  unsubscribe:        "\uD83D\uDEAB",
  resubscribe:        "\u2705",
  calendar_accepted:  "\uD83D\uDCC5\u2705",
  calendar_declined:  "\uD83D\uDCC5\u274C",
  calendar_response:  "\uD83D\uDCC5",
};

function NotificationBell() {
  const { theme } = useTheme();
  const f = theme.fonts;
  const navigate = useNavigate();

  const [notifs, setNotifs]       = useState([]);
  const [showPanel, setShowPanel] = useState(false);
  const panelRef = useRef(null);

  
  // ── Fetch unread notifications ──────────────────
  const fetchNotifs = async () => {
    try {
      const res  = await fetch(`${API}/notifications?unread_only=true`);
      const data = await res.json();
      const list = data.notifications || [];
      if (!showPanel) setNotifs(list);
    } catch {}
  };

  // Poll every 10 s
  useEffect(() => {
    fetchNotifs();
    const id = setInterval(fetchNotifs, 3000);
    return () => clearInterval(id);
  }, []);

  // Panel close does NOT mark anything as read \u2014 only individual clicks do

  // Close panel on outside click
  useEffect(() => {
    if (!showPanel) return;
    const handler = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setShowPanel(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showPanel]);

  // \u2500\u2500 Mark single notification as read \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  const markRead = async (id) => {
    try {
      await fetch(`${API}/notifications/${id}/read`, { method: "POST" });
      setNotifs((prev) => prev.filter((n) => n.id !== id));
    } catch {}
  };

  // \u2500\u2500 Mark all as read \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  // \u2500\u2500 Click a notification \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  const handleClick = async (notif) => {
    await markRead(notif.id);
    setShowPanel(false);
    // Reply-type notifications \u2192 open the conversation in Inbox
    if (REPLY_TYPES.has(notif.type) && notif.lead_id) {
      navigate(`/inbox?open=${notif.lead_id}`);
    }
  };

  const unreadCount = notifs.length;

  return (
    <div ref={panelRef} style={{ position: "relative" }}>
      {/* Bell button */}
      <button
        onClick={() => setShowPanel((p) => !p)}
        style={{
          background: "none", border: "none", cursor: "pointer",
          position: "relative", fontSize: 18, padding: 4,
          color: unreadCount > 0 ? "#fdcb6e" : "#636e72",
          transition: "color .2s",
        }}
      >
        {"\uD83D\uDD14"}
        {unreadCount > 0 && (
          <span style={{
            position: "absolute", top: -3, right: -5,
            minWidth: 16, height: 16, borderRadius: 8,
            background: "#ff6b6b", color: "#fff",
            fontSize: 9, fontWeight: 700,
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: "0 3px",
          }}>{unreadCount}</span>
        )}
      </button>

      {/* Panel */}
      {showPanel && (
        <div style={{
          position: "absolute", top: "calc(100% + 10px)", right: 0,
          width: 360, maxHeight: 440, display: "flex", flexDirection: "column",
          background: "#1a1d27",
          border: "1px solid #2a2d3a",
          borderRadius: 14,
          boxShadow: "0 12px 40px rgba(0,0,0,0.4)",
          zIndex: 200,
          overflow: "hidden",
        }}>
          {/* Panel header */}
          <div style={{
            padding: "12px 16px", borderBottom: "1px solid #2a2d3a",
            display: "flex", alignItems: "center", justifyContent: "space-between",
            flexShrink: 0,
          }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#eaedf4" }}>
              Notifications {unreadCount > 0 && (
                <span style={{
                  marginLeft: 6, fontSize: 11, padding: "1px 7px", borderRadius: 8,
                  background: "#ff6b6b22", color: "#ff6b6b", fontWeight: 700,
                }}>{unreadCount}</span>
              )}
            </span>
            {unreadCount > 0 && (
              <button
                onClick={async () => {
                  try { await fetch(`${API}/notifications/read-all`, { method: "POST" }); } catch {}
                  setNotifs([]);
                  setShowPanel(false);
                }}
                style={{
                  fontSize: 11, color: "#6c5ce7", background: "none", border: "none",
                  cursor: "pointer", padding: 0, fontFamily: f?.body,
                }}
              >
                Mark all as read
              </button>
            )}
          </div>

          {/* Notification list */}
          <div style={{ overflowY: "auto", flex: 1 }}>
            {unreadCount === 0 ? (
              <div style={{
                padding: 32, textAlign: "center",
                fontSize: 13, color: "#525975", lineHeight: 1.8,
              }}>
                No new notifications
              </div>
            ) : (
              notifs.map((n) => {
                const isReply = REPLY_TYPES.has(n.type);
                return (
                  <div
                    key={n.id}
                    onClick={() => handleClick(n)}
                    style={{
                      padding: "12px 16px",
                      borderBottom: "1px solid #2a2d3a",
                      display: "flex", alignItems: "flex-start", gap: 12,
                      cursor: "pointer",
                      transition: "background .12s",
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.background = "#242736"}
                    onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
                  >
                    <span style={{ fontSize: 18, flexShrink: 0, lineHeight: 1 }}>
                      {TYPE_ICON[n.type] || "\u2709\uFE0F"}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, color: "#eaedf4", lineHeight: 1.5 }}>
                        {n.message}
                      </div>
                      <div style={{
                        fontSize: 11, color: "#525975", marginTop: 3,
                        display: "flex", alignItems: "center", gap: 8,
                      }}>
                        <span>{n.created_at ? new Date(n.created_at).toLocaleString("en-US", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : ""}</span>
                        {isReply && (
                          <span style={{ color: "#6c5ce7", fontWeight: 600 }}>
                            {"View conversation \u2192"}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const NAV = [
  { to: "/",           label: "Campaign" },
  { to: "/pipeline",   label: "Pipeline" },
  { to: "/leads",      label: "Leads" },
  { to: "/inbox",      label: "Inbox" },
  { to: "/analytics",  label: "Analytics" },
  { to: "/exclusions", label: "Exclusions" },
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
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <img src={logo} alt="TheLeadFlow" style={{ height: 32, width: "auto" }} />
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

        {/* Right: status + notifications + toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {isRunning && (
            <span style={{ fontSize: 11, color: c.accent, fontFamily: f.mono, animation: "pulse 1.5s infinite" }}>Running</span>
          )}
          <NotificationBell />
          <ThemeToggle />
        </div>
      </header>

      <main style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 32px" }}>
        <Outlet />
      </main>
    </div>
  );
}
