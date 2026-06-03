// src/pages/InboxPage.jsx
import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { useTheme } from "../App";
import { getDiscussions, getThread, runTracker, getLeadDiscussion, sendDiscussionReply, generateDiscussionReply } from "../api/discussions";

const SENTIMENT_META = {
  interested:     { label: "Interested",     color: "#00b894", bg: "rgba(0,184,148,0.12)" },
  info_request:   { label: "Wants info",     color: "#fdcb6e", bg: "rgba(253,203,110,0.12)" },
  not_interested: { label: "Not interested", color: "#ff6b6b", bg: "rgba(255,107,107,0.12)" },
  ooo:            { label: "Out of office",  color: "#a29bfe", bg: "rgba(162,155,254,0.12)" },
  bounce:         { label: "Bounced",        color: "#636e72", bg: "rgba(99,110,114,0.12)" },
};

// ── Discussion list item ──────────────────────────────────────────────────────
function DiscussionItem({ disc, isSelected, onClick, theme }) {
  const c = theme.colors;
  const f = theme.fonts;
  const preview = (disc.last_body || disc.subject || "").replace(/\n/g, " ").slice(0, 75);
  const lastDate = disc.last_message_at
    ? new Date(disc.last_message_at).toLocaleDateString("en-US", { day: "numeric", month: "short" })
    : "";

  return (
    <div
      onClick={() => onClick(disc)}
      style={{
        padding: "14px 16px",
        borderBottom: `1px solid ${c.border}`,
        borderLeft: isSelected ? `3px solid ${c.accent}` : "3px solid transparent",
        background: isSelected ? c.accentGlow : "transparent",
        cursor: "pointer",
        transition: "background .12s",
      }}
      onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.background = c.surfaceAlt; }}
      onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.background = "transparent"; }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: c.text }}>
          {disc.lead_name || "Unknown"}
        </span>
        <span style={{ fontSize: 10, color: c.textDim, fontFamily: f.mono }}>{lastDate}</span>
      </div>
      <div style={{ fontSize: 11, color: c.textMuted, marginBottom: 6 }}>{disc.company}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{
          fontSize: 11, color: c.textDim, flex: 1,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {disc.last_direction === "received" ? "↩ " : "↪ "}{preview || "—"}
        </span>
        {disc.has_reply && (
          <span style={{
            flexShrink: 0, fontSize: 9, padding: "2px 7px", borderRadius: 4,
            background: "rgba(0,184,148,0.15)", color: "#00b894", fontWeight: 700,
          }}>REPLY</span>
        )}
        {disc.reply_count > 0 && (
          <span style={{
            flexShrink: 0, minWidth: 18, height: 18, borderRadius: 9,
            background: c.accent, color: "#fff", fontSize: 10, fontWeight: 700,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: f.mono,
          }}>{disc.reply_count}</span>
        )}
      </div>
    </div>
  );
}

// ── Single message bubble ─────────────────────────────────────────────────────
function MessageBubble({ msg, theme }) {
  const c = theme.colors;
  const f = theme.fonts;

  // Event row (link click, etc.)
  if (msg.direction === "event") {
    return (
      <div style={{
        display: "flex", alignItems: "center", gap: 10, margin: "10px 0",
        color: c.textDim, fontSize: 11,
      }}>
        <div style={{ flex: 1, height: 1, background: c.border }} />
        <span style={{
          padding: "3px 10px", borderRadius: 10, background: c.accentGlow,
          color: c.accent, fontWeight: 600, whiteSpace: "nowrap",
        }}>
          🔗 {msg.body}
        </span>
        <div style={{ flex: 1, height: 1, background: c.border }} />
      </div>
    );
  }

  const isSent = msg.direction === "sent";
  const meta = SENTIMENT_META[msg.sentiment];
  const date = msg.created_at
    ? new Date(msg.created_at).toLocaleString("en-US", {
        day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
      })
    : "";

  return (
    <div style={{
      display: "flex", flexDirection: "column",
      alignItems: isSent ? "flex-end" : "flex-start",
      marginBottom: 24,
    }}>
      {/* Meta row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
        {!isSent && meta && (
          <span style={{
            fontSize: 10, padding: "2px 8px", borderRadius: 4,
            background: meta.bg, color: meta.color, fontWeight: 700,
          }}>{meta.label}</span>
        )}
        <span style={{ fontSize: 11, color: c.textDim, fontFamily: f.mono }}>{date}</span>
      </div>

      {/* Bubble */}
      <div style={{
        maxWidth: "70%",
        background: isSent ? c.accentGlow : c.surface,
        border: `1px solid ${isSent ? c.accent + "55" : c.border}`,
        borderRadius: isSent ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
        padding: "12px 16px",
      }}>
        {msg.subject && (
          <div style={{
            fontSize: 10, fontWeight: 700, letterSpacing: .5, textTransform: "uppercase",
            color: isSent ? c.accent : c.textDim, marginBottom: 8,
          }}>{msg.subject}</div>
        )}
        {/* Split on blank lines → paragraphs; trim leading spaces per line */}
        {(msg.body || "")
          .split(/\n{2,}/)
          .map(p => p.split("\n").map(l => l.trim()).join("\n").trim())
          .filter(Boolean)
          .map((para, i) => (
            <p key={i} style={{
              fontSize: 13, color: c.text, lineHeight: 1.75,
              fontFamily: f.body, margin: i === 0 ? 0 : "10px 0 0",
              whiteSpace: "pre-wrap",
            }}>{para}</p>
          ))
        }
      </div>

      {/* Sender label */}
      <div style={{ fontSize: 11, color: c.textDim, marginTop: 4 }}>
        {isSent ? "You" : msg.from_email || "Lead"}
      </div>
    </div>
  );
}

// ── Schedule Meet modal ───────────────────────────────────────────────────────
function ScheduleMeetModal({ discussion, onClose, theme }) {
  const c = theme.colors;
  const f = theme.fonts;
  const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

  const tomorrow = new Date(Date.now() + 86400000);
  const pad = (n) => String(n).padStart(2, "0");
  const defaultDate = `${tomorrow.getFullYear()}-${pad(tomorrow.getMonth()+1)}-${pad(tomorrow.getDate())}`;

  const [date, setDate]               = useState(defaultDate);
  const [time, setTime]               = useState("10:00");
  const [duration, setDuration]       = useState("30");
  const [notes, setNotes]             = useState("");
  const [toEmail, setToEmail]         = useState(discussion?.lead_email || "");
  const [extraEmails, setExtraEmails] = useState([]);
  const [guestInput, setGuestInput]   = useState("");
  const [creating, setCreating]       = useState(false);
  const [meetLink, setMeetLink]       = useState(null);
  const [error, setError]             = useState(null);
  const [gcalStatus, setGcalStatus]   = useState("checking");

  const leadName = discussion?.lead_name || "Lead";
  const company  = discussion?.company   || "";

  // Check Google Calendar OAuth status on open
  useEffect(() => {
    fetch(`${API}/google/calendar/status`)
      .then(r => r.json())
      .then(d => setGcalStatus(d.connected ? "connected" : d.configured ? "needs_auth" : "not_configured"))
      .catch(() => setGcalStatus("not_configured"));
  }, [API]);

  const allInvitees = () => {
    const base = toEmail.trim() ? [toEmail.trim()] : [];
    return [...new Set([...base, ...extraEmails])];
  };

  const handleGuestKeyDown = (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      const email = guestInput.trim().replace(/,$/, "");
      if (email && /\S+@\S+\.\S+/.test(email) && !extraEmails.includes(email))
        setExtraEmails(prev => [...prev, email]);
      setGuestInput("");
    } else if (e.key === "Backspace" && guestInput === "" && extraEmails.length > 0) {
      setExtraEmails(prev => prev.slice(0, -1));
    }
  };

  const removeGuest = (email) =>
    setExtraEmails(prev => prev.filter(e => e !== email));

  const handleConnect = async () => {
    const res  = await fetch(`${API}/google/calendar/auth`);
    const data = await res.json();
    if (!data.auth_url) return;

    const popup = window.open(data.auth_url, "_blank", "width=520,height=700");

    // Poll status every 2 s until connected or popup is closed
    const poll = setInterval(async () => {
      try {
        const r = await fetch(`${API}/google/calendar/status`);
        const d = await r.json();
        if (d.connected) {
          setGcalStatus("connected");
          clearInterval(poll);
        }
      } catch {}
      if (popup?.closed) clearInterval(poll);
    }, 2000);
  };

  const handleCreateMeet = async () => {
    setCreating(true);
    setError(null);
    try {
      const res = await fetch(`${API}/discussions/${discussion.id}/create-meet`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          date, time,
          duration: duration === "open" ? null : parseInt(duration),
          notes,
          to_email: toEmail.trim() || null,
          extra_emails: extraEmails,
        }),
      });
      const data = await res.json();
      if (res.status === 401) {
        // Token expired — force reconnect
        setGcalStatus("needs_auth");
        throw new Error("Google Calendar token expired. Please reconnect.");
      }
      if (!res.ok) throw new Error(data.detail || "Failed to create Meet");
      setMeetLink(data.meet_link);
    } catch (e) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const labelStyle = {
    fontSize: 10, fontWeight: 700, textTransform: "uppercase",
    color: c.textDim, display: "block", marginBottom: 5,
  };
  const inputStyle = {
    padding: "8px 12px", borderRadius: 7, border: `1px solid ${c.border}`,
    background: c.bg, color: c.text, fontSize: 13,
    fontFamily: f.body, outline: "none", width: "100%", boxSizing: "border-box",
  };

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 9999,
      background: "rgba(0,0,0,0.5)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: c.surface, border: `1px solid ${c.border}`, borderRadius: 16,
        padding: 28, width: 480, maxWidth: "92vw", maxHeight: "90vh", overflowY: "auto",
        boxShadow: "0 20px 60px rgba(0,0,0,0.35)",
      }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 22 }}>
          <span style={{ fontSize: 24 }}>📅</span>
          <div>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: c.text }}>
              Schedule Google Meet
            </h3>
            <p style={{ margin: "2px 0 0", fontSize: 12, color: c.textMuted }}>
              {leadName}{company ? ` · ${company}` : ""}
            </p>
          </div>
          <button onClick={onClose} style={{ marginLeft: "auto", background: "none", border: "none", color: c.textDim, fontSize: 18, cursor: "pointer" }}>✕</button>
        </div>

        {/* Google Calendar connection status */}
        {gcalStatus === "not_configured" && (
          <div style={{ padding: "10px 14px", borderRadius: 8, background: "rgba(254,202,87,0.12)", border: "1px solid rgba(254,202,87,0.3)", marginBottom: 16, fontSize: 12, color: "#feca57", lineHeight: 1.6 }}>
            <strong>Setup required:</strong> Add <code>GOOGLE_CLIENT_ID</code> and <code>GOOGLE_CLIENT_SECRET</code> to your .env file
            (Google Cloud Console → APIs &amp; Services → Credentials → OAuth2 Client → Web app,
            redirect URI: <code>http://localhost:8000/google/calendar/callback</code>).
          </div>
        )}
        {gcalStatus === "needs_auth" && (
          <div style={{ padding: "10px 14px", borderRadius: 8, background: "rgba(108,92,231,0.1)", border: "1px solid rgba(108,92,231,0.3)", marginBottom: 16, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 12, color: c.accent }}>Connect your Google Calendar to create Meet events</span>
            <button onClick={handleConnect} style={{
              padding: "6px 14px", borderRadius: 6, border: "none",
              background: "#4285F4", color: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer",
            }}>Connect Google</button>
          </div>
        )}
        {gcalStatus === "connected" && (
          <div style={{ padding: "6px 12px", borderRadius: 6, background: "rgba(0,184,148,0.1)", marginBottom: 14, fontSize: 11, color: "#00b894" }}>
            ✓ Google Calendar connected
          </div>
        )}

        {/* Meet link result */}
        {meetLink && (
          <div style={{ padding: "14px 16px", borderRadius: 10, background: "rgba(0,184,148,0.1)", border: "1px solid #00b89444", marginBottom: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#00b894", marginBottom: 8 }}>✓ Google Meet created</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <a href={meetLink} target="_blank" rel="noreferrer" style={{
                flex: 1, fontFamily: f.mono, fontSize: 12, color: c.accent,
                wordBreak: "break-all", textDecoration: "none",
              }}>{meetLink}</a>
              <button onClick={() => navigator.clipboard.writeText(meetLink)} style={{
                padding: "4px 10px", borderRadius: 6, border: `1px solid ${c.border}`,
                background: c.bg, color: c.textMuted, fontSize: 11, cursor: "pointer",
                whiteSpace: "nowrap",
              }}>Copy</button>
            </div>
          </div>
        )}

        {/* Form — hidden after Meet is created */}
        {!meetLink && (
          <>
            {/* Date / Time / Duration */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 14 }}>
              <div>
                <label style={labelStyle}>Date</label>
                <input type="date" value={date} onChange={e => setDate(e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Time</label>
                <input type="time" value={time} onChange={e => setTime(e.target.value)} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Duration</label>
                <select value={duration} onChange={e => setDuration(e.target.value)} style={inputStyle}>
                  <option value="15">15 min</option>
                  <option value="30">30 min</option>
                  <option value="45">45 min</option>
                  <option value="60">1 hour</option>
                  <option value="90">1h 30</option>
                  <option value="120">2 hours</option>
                  <option value="open">Open-ended</option>
                </select>
              </div>
            </div>

            {/* Lead email */}
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>Lead email</label>
              <input value={toEmail} onChange={e => setToEmail(e.target.value)}
                placeholder="lead@company.com" style={inputStyle} />
            </div>

            {/* Guest tag-input */}
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Additional invitees</label>
              <div style={{
                ...inputStyle, display: "flex", flexWrap: "wrap",
                gap: 6, alignItems: "center", minHeight: 40, padding: "6px 10px", cursor: "text",
              }} onClick={e => e.currentTarget.querySelector("input")?.focus()}>
                {extraEmails.map(email => (
                  <span key={email} style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    padding: "2px 8px", borderRadius: 10,
                    background: c.accentGlow, color: c.accent,
                    fontSize: 11, fontFamily: f.mono, whiteSpace: "nowrap",
                  }}>
                    {email}
                    <button onClick={() => removeGuest(email)} style={{ background: "none", border: "none", cursor: "pointer", color: c.accent, fontSize: 12, padding: 0, lineHeight: 1 }}>×</button>
                  </span>
                ))}
                <input
                  value={guestInput}
                  onChange={e => setGuestInput(e.target.value)}
                  onKeyDown={handleGuestKeyDown}
                  placeholder={extraEmails.length === 0 ? "Add guests" : ""}
                  style={{ border: "none", outline: "none", background: "transparent", color: c.text, fontFamily: f.body, fontSize: 13, flex: 1, minWidth: 120, padding: 0 }}
                />
              </div>
              <p style={{ fontSize: 10, color: c.textDim, margin: "4px 0 0" }}>Press Enter to confirm each email</p>
            </div>

            {/* Notes */}
            <div style={{ marginBottom: 18 }}>
              <label style={labelStyle}>Notes / Agenda (optional)</label>
              <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2}
                placeholder="Topics to discuss, agenda, context…"
                style={{ ...inputStyle, resize: "none" }} />
            </div>

            {error && (
              <div style={{ padding: "8px 12px", borderRadius: 7, background: "rgba(255,107,107,0.12)", color: "#ff6b6b", fontSize: 12, marginBottom: 14 }}>
                {error}
              </div>
            )}

            <button
              onClick={handleCreateMeet}
              disabled={creating || gcalStatus !== "connected"}
              style={{
                width: "100%", padding: "11px 0", borderRadius: 9, border: "none",
                background: (creating || gcalStatus !== "connected") ? c.surfaceAlt : "#4285F4",
                color: "#fff", fontSize: 14, fontWeight: 700,
                cursor: (creating || gcalStatus !== "connected") ? "not-allowed" : "pointer",
                fontFamily: f.body, opacity: (creating || gcalStatus !== "connected") ? 0.6 : 1,
                transition: "opacity .2s",
              }}
            >
              {creating ? "Creating Meet…" : "Create Google Meet"}
            </button>
          </>
        )}

        {meetLink && (
          <button onClick={onClose} style={{
            width: "100%", padding: "10px 0", borderRadius: 8, border: "none",
            background: "#00b894", color: "#fff", fontSize: 13, fontWeight: 600,
            cursor: "pointer", fontFamily: f.body,
          }}>Done</button>
        )}
      </div>
    </div>
  );
}

// ── Reply composer ────────────────────────────────────────────────────────────
function ReplyComposer({ discussion, onSent, onScheduleMeet, theme }) {
  const c = theme.colors;
  const f = theme.fonts;
  const [open, setOpen]           = useState(false);
  const [subject, setSubject]     = useState("");
  const [body, setBody]           = useState("");
  const [sending, setSending]     = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError]         = useState(null);

  // Pre-fill subject when discussion changes
  useEffect(() => {
    if (discussion?.subject) {
      const base = discussion.subject.replace(/^(Re:\s*)+/i, "");
      setSubject(`Re: ${base}`);
    }
  }, [discussion?.id]);

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const res = await generateDiscussionReply(discussion.id);
      if (res.subject) setSubject(res.subject);
      if (res.body)    setBody(res.body);
      setOpen(true);
    } catch (e) {
      setError(e.message || "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const handleSend = async () => {
    if (!body.trim()) return;
    setSending(true);
    setError(null);
    try {
      await sendDiscussionReply(discussion.id, { subject, body });
      setBody("");
      setOpen(false);
      onSent();
    } catch (e) {
      setError(e.message || "Send failed");
    } finally {
      setSending(false);
    }
  };

  if (!open) {
    return (
      <div style={{
        padding: "12px 20px", borderTop: `1px solid ${c.border}`,
        background: c.surface, flexShrink: 0,
        display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
      }}>
        {/* Reply */}
        <button onClick={() => setOpen(true)} style={{
          padding: "8px 18px", borderRadius: 8, border: `1px solid ${c.accent}`,
          background: "transparent", color: c.accent, fontSize: 13, fontWeight: 600,
          cursor: "pointer", fontFamily: f.body, display: "flex", alignItems: "center", gap: 6,
        }}>
          ✏️ Reply
        </button>

        {/* Generate reply */}
        <button onClick={handleGenerate} disabled={generating} style={{
          padding: "8px 18px", borderRadius: 8, border: "none",
          background: generating ? c.surfaceAlt : c.accent,
          color: "#fff", fontSize: 13, fontWeight: 600,
          cursor: generating ? "not-allowed" : "pointer",
          fontFamily: f.body, display: "flex", alignItems: "center", gap: 6,
          opacity: generating ? 0.7 : 1,
        }}>
          ✨ {generating ? "Generating…" : "Generate reply"}
        </button>

        {/* Schedule Google Meet */}
        <button onClick={onScheduleMeet} style={{
          padding: "8px 18px", borderRadius: 8, border: `1px solid #00b894`,
          background: "transparent", color: "#00b894", fontSize: 13, fontWeight: 600,
          cursor: "pointer", fontFamily: f.body, display: "flex", alignItems: "center", gap: 6,
          marginLeft: "auto",
        }}>
          📅 Schedule Meet
        </button>

        {error && <span style={{ fontSize: 12, color: "#ff6b6b", width: "100%" }}>{error}</span>}
      </div>
    );
  }

  return (
    <div style={{
      borderTop: `1px solid ${c.border}`, background: c.surface,
      flexShrink: 0, display: "flex", flexDirection: "column",
    }}>
      {/* Composer header */}
      <div style={{
        padding: "10px 16px", borderBottom: `1px solid ${c.border}`,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: c.textDim }}>New reply</span>
        <button onClick={() => setOpen(false)} style={{
          background: "none", border: "none", cursor: "pointer",
          color: c.textDim, fontSize: 16, padding: 2,
        }}>✕</button>
      </div>

      {/* Subject */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "8px 16px", borderBottom: `1px solid ${c.border}`,
      }}>
        <span style={{ fontSize: 11, color: c.textDim, fontWeight: 600, minWidth: 50, textTransform: "uppercase" }}>Subject</span>
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          style={{
            flex: 1, border: "none", background: "transparent", outline: "none",
            color: c.text, fontSize: 13, fontFamily: f.body,
          }}
        />
      </div>

      {/* Body */}
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Write your reply…"
        rows={5}
        style={{
          width: "100%", padding: "12px 16px", border: "none",
          background: "transparent", color: c.text, fontFamily: f.body,
          fontSize: 13, lineHeight: 1.7, outline: "none", resize: "none",
          boxSizing: "border-box",
        }}
      />

      {/* Footer */}
      <div style={{
        padding: "10px 16px", borderTop: `1px solid ${c.border}`,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        {error && <span style={{ fontSize: 12, color: "#ff6b6b" }}>{error}</span>}
        {!error && <span style={{ fontSize: 11, color: c.textDim }}>{body.trim().split(/\s+/).filter(Boolean).length} words</span>}
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setOpen(false)} style={{
            padding: "7px 16px", borderRadius: 7, border: `1px solid ${c.border}`,
            background: "transparent", color: c.textMuted, fontSize: 12,
            cursor: "pointer", fontFamily: f.body,
          }}>Cancel</button>
          <button
            onClick={handleSend}
            disabled={sending || !body.trim()}
            style={{
              padding: "7px 20px", borderRadius: 7, border: "none",
              background: sending || !body.trim() ? c.surfaceAlt : c.accent,
              color: "#fff", fontSize: 12, fontWeight: 600,
              cursor: sending || !body.trim() ? "not-allowed" : "pointer",
              fontFamily: f.body, opacity: sending ? 0.7 : 1,
            }}
          >
            {sending ? "Sending…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function InboxPage() {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;
  const [searchParams, setSearchParams] = useSearchParams();

  const [discussions, setDiscussions]     = useState([]);
  const [selected, setSelected]           = useState(null);
  const [messages, setMessages]           = useState([]);
  const [loading, setLoading]             = useState(true);
  const [checking, setChecking]           = useState(false);
  const [checkResult, setCheckResult]     = useState(null);
  const [newReplyBanner, setNewReplyBanner] = useState(false);
  const [showMeetModal, setShowMeetModal] = useState(false);

  const messagesEndRef  = useRef(null);
  const prevMsgCount    = useRef(0);
  const selectedRef     = useRef(null);  // stable ref so intervals can access it

  selectedRef.current = selected;

  // ── Auto-scroll to bottom when messages update ────────────────────────────
  useEffect(() => {
    if (messages.length > prevMsgCount.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      if (prevMsgCount.current > 0) {       // not first load
        setNewReplyBanner(true);
        setTimeout(() => setNewReplyBanner(false), 4000);
      }
    }
    prevMsgCount.current = messages.length;
  }, [messages]);

  // ── Fetch discussions ─────────────────────────────────────────────────────
  const fetchDiscussions = useCallback(async (silent = false) => {
    try {
      const res = await getDiscussions();
      setDiscussions(res.discussions || []);
    } catch (e) {
      console.error(e);
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  // ── Fetch thread for currently selected discussion ────────────────────────
  const fetchThread = useCallback(async (discId) => {
    try {
      const res = await getThread(discId);
      setMessages(res.messages || []);
    } catch (e) {
      console.error(e);
    }
  }, []);

  // ── Open a discussion ─────────────────────────────────────────────────────
  const openDiscussion = useCallback(async (disc) => {
    setSelected(disc);
    prevMsgCount.current = 0;
    setMessages([]);
    setSearchParams({});    // clear URL param after opening
    await fetchThread(disc.id);
  }, [fetchThread, setSearchParams]);

  // ── Initial load ─────────────────────────────────────────────────────────
  useEffect(() => {
    fetchDiscussions();
  }, []); // intentionally empty — runs once on mount

  // ── Open discussion from ?open=<lead_id> param — runs on EVERY param change
  // (covers both initial load and notification clicks when already on this page)
  useEffect(() => {
    const leadId = searchParams.get("open");
    if (!leadId) return;
    getLeadDiscussion(leadId)
      .then((res) => {
        if (res.discussion) {
          prevMsgCount.current = 0;
          setSelected(res.discussion);
          setMessages(res.messages || []);
          setSearchParams({});
        }
      })
      .catch(console.error);
  }, [searchParams, setSearchParams]);

  // ── Auto-refresh discussions every 15 s ──────────────────────────────────
  useEffect(() => {
    const id = setInterval(() => fetchDiscussions(true), 15000);
    return () => clearInterval(id);
  }, [fetchDiscussions]);

  // ── Auto-refresh active thread every 8 s ─────────────────────────────────
  useEffect(() => {
    const id = setInterval(() => {
      if (selectedRef.current) fetchThread(selectedRef.current.id);
    }, 8000);
    return () => clearInterval(id);
  }, [fetchThread]);

  // ── Auto-trigger IMAP check every 2 min while on this page ───────────────
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        await runTracker();
        await fetchDiscussions(true);
        if (selectedRef.current) await fetchThread(selectedRef.current.id);
      } catch (e) { /* silent */ }
    }, 120000);
    return () => clearInterval(id);
  }, [fetchDiscussions, fetchThread]);

  // ── Manual "Check for replies" ────────────────────────────────────────────
  const handleCheckReplies = async () => {
    setChecking(true);
    setCheckResult(null);
    try {
      const res = await runTracker();
      setCheckResult(res);
      await fetchDiscussions(true);
      if (selectedRef.current) await fetchThread(selectedRef.current.id);
    } catch (e) {
      setCheckResult({ error: e.message });
    } finally {
      setChecking(false);
    }
  };

  const repliedCount = discussions.filter((d) => d.has_reply).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 114px)" }}>

      {/* ── Header ── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 16,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: c.text, margin: 0 }}>Inbox</h2>
          <span style={{ fontSize: 12, color: c.textDim, fontFamily: f.mono }}>
            {discussions.length} conversation{discussions.length !== 1 ? "s" : ""}
          </span>
          {repliedCount > 0 && (
            <span style={{
              fontSize: 11, padding: "3px 10px", borderRadius: 6,
              background: "rgba(0,184,148,0.12)", color: "#00b894", fontWeight: 700,
            }}>
              {repliedCount} replied
            </span>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {checkResult && !checkResult.error && (
            <span style={{ fontSize: 12, color: c.green, fontFamily: f.mono }}>
              {checkResult.replies_found ?? 0} scanned · {checkResult.matched ?? 0} matched
            </span>
          )}
          {checkResult?.error && (
            <span style={{ fontSize: 12, color: c.hot }}>{checkResult.error}</span>
          )}
          <button
            onClick={handleCheckReplies}
            disabled={checking}
            style={{
              padding: "7px 16px", borderRadius: 8, border: "none",
              background: checking ? c.surfaceAlt : c.accent,
              color: "#fff", fontSize: 12, fontWeight: 600,
              cursor: checking ? "not-allowed" : "pointer", fontFamily: f.body,
              opacity: checking ? 0.6 : 1, transition: "opacity .2s",
            }}
          >
            {checking ? "Checking…" : "Check for replies"}
          </button>
        </div>
      </div>

      {/* ── Two-panel layout ── */}
      <div style={{
        display: "flex", flex: 1,
        border: `1px solid ${c.border}`, borderRadius: 14,
        overflow: "hidden", minHeight: 0,
      }}>

        {/* Left panel — discussion list */}
        <div style={{
          width: 300, minWidth: 300, flexShrink: 0,
          borderRight: `1px solid ${c.border}`,
          overflowY: "auto", background: c.surface,
        }}>
          {loading ? (
            <div style={{ padding: 32, textAlign: "center", color: c.textDim, fontSize: 13 }}>
              Loading…
            </div>
          ) : discussions.length === 0 ? (
            <div style={{
              padding: 32, textAlign: "center",
              color: c.textDim, fontSize: 13, lineHeight: 1.9,
            }}>
              No conversations yet.<br />Send an email to a lead to start one.
            </div>
          ) : (
            discussions.map((d) => (
              <DiscussionItem
                key={d.id}
                disc={d}
                isSelected={selected?.id === d.id}
                onClick={openDiscussion}
                theme={theme}
              />
            ))
          )}
        </div>

        {/* Right panel — thread */}
        <div style={{
          flex: 1, display: "flex", flexDirection: "column",
          background: c.bg, minHeight: 0, overflow: "hidden",
        }}>
          {!selected ? (
            <div style={{
              flex: 1, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center",
              color: c.textDim, gap: 8,
            }}>
              <span style={{ fontSize: 28 }}>✉</span>
              <span style={{ fontSize: 14 }}>Select a conversation</span>
            </div>
          ) : (
            <>
              {/* Thread header */}
              <div style={{
                padding: "14px 20px", borderBottom: `1px solid ${c.border}`,
                background: c.surface, flexShrink: 0,
                display: "flex", alignItems: "center", gap: 12,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 15, color: c.text }}>
                    {selected.lead_name}
                    {selected.company && (
                      <span style={{ fontWeight: 400, color: c.textMuted }}>
                        {" · "}{selected.company}
                      </span>
                    )}
                  </div>
                  <div style={{
                    fontSize: 12, color: c.textDim, marginTop: 2,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>
                    {selected.lead_email || selected.subject}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                  {selected.has_reply && (
                    <span style={{
                      fontSize: 10, padding: "3px 10px", borderRadius: 6,
                      background: "rgba(0,184,148,0.12)", color: "#00b894", fontWeight: 700,
                    }}>Replied</span>
                  )}
                  <span style={{
                    fontSize: 10, padding: "3px 10px", borderRadius: 6,
                    background: c.accentGlow, color: c.accent, fontFamily: f.mono,
                  }}>
                    {messages.length} msg{messages.length !== 1 ? "s" : ""}
                  </span>
                </div>
              </div>

              {/* New reply banner */}
              {newReplyBanner && (
                <div style={{
                  padding: "8px 20px", background: "rgba(0,184,148,0.10)",
                  borderBottom: `1px solid #00b89433`,
                  fontSize: 12, color: "#00b894", fontWeight: 600, flexShrink: 0,
                }}>
                  New reply received
                </div>
              )}

              {/* Messages */}
              <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px" }}>
                {messages.length === 0 ? (
                  <div style={{ color: c.textDim, fontSize: 13, textAlign: "center", paddingTop: 40 }}>
                    No messages yet
                  </div>
                ) : (
                  messages.map((msg) => (
                    <MessageBubble key={msg.id} msg={msg} theme={theme} />
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Reply composer */}
              <ReplyComposer
                discussion={selected}
                onSent={() => fetchThread(selected.id)}
                onScheduleMeet={() => setShowMeetModal(true)}
                theme={theme}
              />

              {/* Schedule Meet modal */}
              {showMeetModal && (
                <ScheduleMeetModal
                  discussion={selected}
                  onClose={() => setShowMeetModal(false)}
                  theme={theme}
                />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
