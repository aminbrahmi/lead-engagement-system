// frontend/src/components/EmailEditor.jsx
import React, { useState, useEffect } from "react";
import { useTheme } from "../App";
import { sendSingleLead } from "../api/sequences";

// ── Confirmation Modal ───────────────────────────────────────────────────────
function ConfirmModal({ open, onConfirm, onCancel, toEmail, subject, variant, theme }) {
  if (!open) return null;
  const c = theme.colors;
  const f = theme.fonts;

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 9999,
      display: "flex", alignItems: "center", justifyContent: "center",
      background: "rgba(0,0,0,0.5)", backdropFilter: "blur(4px)",
    }} onClick={onCancel}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: c.surface, border: `1px solid ${c.border}`, borderRadius: 16,
        padding: 32, width: 480, maxWidth: "90vw",
        boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
      }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 10,
            background: c.accentGlow, display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 18,
          }}>&#9993;</div>
          <div>
            <h3 style={{ fontSize: 16, fontWeight: 600, color: c.text, margin: 0 }}>Confirm send</h3>
            <p style={{ fontSize: 12, color: c.textMuted, margin: "2px 0 0" }}>This action cannot be undone</p>
          </div>
        </div>

        {/* Details */}
        <div style={{
          background: c.bg, borderRadius: 10, padding: 16, marginBottom: 24,
          border: `1px solid ${c.border}`,
        }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 11, color: c.textDim, fontWeight: 600, minWidth: 60, textTransform: "uppercase" }}>To</span>
            <span style={{ fontSize: 13, fontFamily: f.mono, color: c.text, fontWeight: 500 }}>{toEmail}</span>
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 11, color: c.textDim, fontWeight: 600, minWidth: 60, textTransform: "uppercase" }}>Subject</span>
            <span style={{ fontSize: 13, color: c.text }}>{subject}</span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <span style={{ fontSize: 11, color: c.textDim, fontWeight: 600, minWidth: 60, textTransform: "uppercase" }}>Variant</span>
            <span style={{
              fontSize: 11, padding: "2px 8px", borderRadius: 4,
              background: c.accentGlow, color: c.accent, fontFamily: f.mono, fontWeight: 600,
            }}>Variant {variant}</span>
          </div>
        </div>

        {/* Follow-up notice */}
        <div style={{
          background: c.greenGlow, borderRadius: 8, padding: "10px 14px",
          marginBottom: 24, fontSize: 12, color: c.green, lineHeight: 1.6,
          border: `1px solid ${c.green}22`,
        }}>
          Follow-up sequence will be created automatically: J+3, J+7, J+14
        </div>

        {/* Buttons */}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onCancel} style={{
            padding: "10px 24px", borderRadius: 8, border: `1px solid ${c.border}`,
            background: "transparent", color: c.textMuted, fontSize: 13, fontWeight: 500,
            cursor: "pointer", fontFamily: f.body,
          }}>Cancel</button>
          <button onClick={onConfirm} style={{
            padding: "10px 28px", borderRadius: 8, border: "none",
            background: c.green, color: "#fff", fontSize: 13, fontWeight: 600,
            cursor: "pointer", fontFamily: f.body,
          }}>Send email</button>
        </div>
      </div>
    </div>
  );
}

// ── Main EmailEditor ─────────────────────────────────────────────────────────
export default function EmailEditor({
  leadId, campaignId, leadEmail, emailVerified,
  draftEmail, draftEmails, onSave, onSend,
}) {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;

  const variants = draftEmails || (draftEmail ? { A: draftEmail } : {});
  const variantKeys = Object.keys(variants);
  const [activeVariant, setActiveVariant] = useState(variantKeys[0] || "A");

  const currentEmail = variants[activeVariant] || {};
  const [toEmail, setToEmail] = useState(leadEmail || "");
  const [subject, setSubject] = useState(currentEmail.subject || "");
  const [body, setBody] = useState(currentEmail.body || "");
  const [cc, setCc] = useState(currentEmail.cc || "");
  const [saved, setSaved] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState(null);
  const [isPreview, setIsPreview] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  useEffect(() => {
    const v = variants[activeVariant] || {};
    setSubject(v.subject || "");
    setBody(v.body || "");
    setCc(v.cc || "");
    setToEmail(leadEmail || "");
    setSaved(false);
    setSendResult(null);
    setIsPreview(false);
    setShowConfirm(false);
  }, [leadId, activeVariant]);

  const handleSave = () => {
    onSave(leadId, { subject, body, cc, variant: activeVariant, to_email: toEmail });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  // Step 1: user clicks Send → show modal
  const handleSendClick = () => {
    if (!toEmail) {
      setSendResult({ ok: false, msg: "No recipient email" });
      return;
    }
    setShowConfirm(true);
  };

  // Step 2: user confirms in modal → actually send
  const handleConfirmSend = async () => {
    setShowConfirm(false);
    setSending(true);
    setSendResult(null);

    try {
      // Save draft first
      onSave(leadId, { subject, body, cc, variant: activeVariant, to_email: toEmail });

      // Send with to_email override — backend uses this instead of DB email
      const API = process.env.REACT_APP_API_URL || "http://localhost:8000";
      const res = await fetch(`${API}/leads/${leadId}/send-email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          variant: activeVariant,
          send_followups: true,
          to_email: toEmail,
          subject: subject,   // ← current state, NOT currentEmail.subject
          body: body,         // ← current state, NOT currentEmail.body
          cc: cc,
        }),
      });

      const data = await res.json();

      if (res.ok && data.status === "sent") {
        setSendResult({
          ok: true,
          msg: `Email sent to ${toEmail} — follow-ups scheduled (J+3, J+7, J+14)`,
        });
      } else {
        setSendResult({
          ok: false,
          msg: data.detail || data.message || `Send failed (${res.status})`,
        });
      }

      if (onSend) onSend(leadId, activeVariant);
    } catch (err) {
      setSendResult({ ok: false, msg: err.message || "Network error" });
    } finally {
      setSending(false);
    }
  };

  const wordCount = body.split(/\s+/).filter(Boolean).length;
  if (variantKeys.length === 0) return null;

  return (
    <div>
      {/* Confirm modal */}
      <ConfirmModal
        open={showConfirm}
        onConfirm={handleConfirmSend}
        onCancel={() => setShowConfirm(false)}
        toEmail={toEmail}
        subject={subject}
        variant={activeVariant}
        theme={theme}
      />

      {/* Header + A/B toggle */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 16, flexWrap: "wrap", gap: 8,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h4 style={{ fontSize: 10, color: c.textDim, textTransform: "uppercase", letterSpacing: 1, fontWeight: 700 }}>
            Draft email
          </h4>
          {variantKeys.length > 1 && (
            <div style={{ display: "flex", gap: 4 }}>
              {variantKeys.map((v) => (
                <button key={v} onClick={() => setActiveVariant(v)} style={{
                  padding: "3px 10px", borderRadius: 4,
                  border: `1px solid ${activeVariant === v ? c.accent : c.border}`,
                  background: activeVariant === v ? c.accentGlow : "transparent",
                  color: activeVariant === v ? c.accent : c.textMuted,
                  fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: f.mono,
                }}>Variant {v}</button>
              ))}
            </div>
          )}
          {currentEmail.variant_strategy && (
            <span style={{
              fontSize: 10, padding: "2px 8px", borderRadius: 4,
              background: c.surfaceAlt, color: c.textMuted, fontFamily: f.mono,
            }}>{currentEmail.variant_strategy}</span>
          )}
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {saved && <span style={{ fontSize: 12, color: c.green, fontFamily: f.mono }}>Saved</span>}
          <button onClick={() => setIsPreview(!isPreview)} style={{
            padding: "5px 12px", borderRadius: 6, border: `1px solid ${c.border}`,
            background: isPreview ? c.accentGlow : "transparent",
            color: isPreview ? c.accent : c.textMuted,
            fontSize: 12, fontWeight: 500, cursor: "pointer", fontFamily: f.body,
          }}>{isPreview ? "Edit" : "Preview"}</button>
          <button onClick={handleSave} style={{
            padding: "5px 14px", borderRadius: 6, border: "none", cursor: "pointer",
            background: c.accent, color: "#fff", fontSize: 12, fontWeight: 600, fontFamily: f.body,
          }}>Save draft</button>
          <button onClick={handleSendClick} disabled={sending || !toEmail} style={{
            padding: "5px 14px", borderRadius: 6, border: "none",
            cursor: sending || !toEmail ? "not-allowed" : "pointer",
            background: c.green, color: "#fff", fontSize: 12, fontWeight: 600, fontFamily: f.body,
            opacity: sending || !toEmail ? 0.5 : 1,
          }}>{sending ? "Sending..." : "Send"}</button>
        </div>
      </div>

      {/* Send result */}
      {sendResult && (
        <div style={{
          padding: "10px 14px", borderRadius: 8, marginBottom: 12, fontSize: 13,
          background: sendResult.ok ? c.greenGlow : c.hotGlow,
          color: sendResult.ok ? c.green : c.hot,
          border: `1px solid ${sendResult.ok ? c.green : c.hot}22`,
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <span style={{ fontSize: 16 }}>{sendResult.ok ? "\u2713" : "\u2717"}</span>
          {sendResult.msg}
        </div>
      )}

      {/* Email form */}
      <div style={{
        background: c.surface, border: `1px solid ${c.border}`, borderRadius: 10, overflow: "hidden",
      }}>
        {/* TO — editable */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10, padding: "10px 16px",
          borderBottom: `1px solid ${c.border}`,
        }}>
          <span style={{ fontSize: 11, color: c.textDim, fontWeight: 600, minWidth: 50, textTransform: "uppercase", letterSpacing: .5 }}>To</span>
          {isPreview ? (
            <span style={{ flex: 1, fontFamily: f.mono, fontSize: 13, color: c.text }}>{toEmail}</span>
          ) : (
            <input
              value={toEmail}
              onChange={(e) => setToEmail(e.target.value)}
              placeholder="recipient@company.com"
              style={{
                flex: 1, padding: "4px 0", border: "none", background: "transparent",
                color: c.text, fontFamily: f.mono, fontSize: 13, outline: "none",
              }}
            />
          )}
          {toEmail && toEmail !== leadEmail && (
            <span style={{
              fontSize: 10, padding: "2px 8px", borderRadius: 4,
              background: c.warmGlow, color: c.warm, fontWeight: 600, fontFamily: f.mono,
            }}>MODIFIED</span>
          )}
          {toEmail && toEmail === leadEmail && emailVerified && (
            <span style={{
              fontSize: 10, padding: "2px 8px", borderRadius: 4,
              background: c.greenGlow, color: c.green, fontWeight: 600, fontFamily: f.mono,
            }}>VERIFIED</span>
          )}
          {toEmail && toEmail === leadEmail && !emailVerified && (
            <span style={{
              fontSize: 10, padding: "2px 8px", borderRadius: 4,
              background: c.warmGlow, color: c.warm, fontWeight: 600, fontFamily: f.mono,
            }}>UNVERIFIED</span>
          )}
        </div>

        {/* CC */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10, padding: "8px 16px",
          borderBottom: `1px solid ${c.border}`,
        }}>
          <span style={{ fontSize: 11, color: c.textDim, fontWeight: 600, minWidth: 50, textTransform: "uppercase", letterSpacing: .5 }}>CC</span>
          {isPreview ? (
            <span style={{ flex: 1, fontSize: 13, color: cc ? c.text : c.textDim }}>{cc || "\u2014"}</span>
          ) : (
            <input value={cc} onChange={(e) => setCc(e.target.value)} placeholder="team@company.com"
              style={{ flex: 1, padding: "4px 0", border: "none", background: "transparent", color: c.text, fontFamily: f.body, fontSize: 13, outline: "none" }} />
          )}
        </div>

        {/* Subject */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10, padding: "10px 16px",
          borderBottom: `1px solid ${c.border}`,
        }}>
          <span style={{ fontSize: 11, color: c.textDim, fontWeight: 600, minWidth: 50, textTransform: "uppercase", letterSpacing: .5 }}>Subj</span>
          {isPreview ? (
            <span style={{ flex: 1, fontSize: 14, fontWeight: 500, color: c.text }}>{subject}</span>
          ) : (
            <input value={subject} onChange={(e) => setSubject(e.target.value)}
              style={{ flex: 1, padding: "4px 0", border: "none", background: "transparent", color: c.text, fontFamily: f.body, fontSize: 14, fontWeight: 500, outline: "none" }} />
          )}
        </div>

        {/* Body */}
        <div style={{ padding: 16 }}>
          {isPreview ? (
            <div style={{ fontSize: 14, lineHeight: 1.8, color: c.text, fontFamily: f.body, minHeight: 200 }}>
              {body.split(/\n{2,}/).map((p, i) => (
                <p key={i} style={{ margin: i === 0 ? 0 : "12px 0 0", whiteSpace: "pre-wrap" }}>
                  {p.split("\n").map(l => l.trim()).join("\n")}
                </p>
              ))}
            </div>
          ) : (
            <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={12}
              style={{ width: "100%", padding: 0, border: "none", background: "transparent", color: c.text, fontFamily: f.body, fontSize: 14, lineHeight: 1.8, outline: "none", resize: "vertical", minHeight: 200 }} />
          )}
        </div>

        {/* Footer */}
        <div style={{
          display: "flex", justifyContent: "space-between", padding: "8px 16px",
          borderTop: `1px solid ${c.border}`, fontSize: 11, color: c.textDim,
        }}>
          <span>{wordCount} words</span>
          <span>Variant {activeVariant}{currentEmail.variant_strategy ? ` \u2014 ${currentEmail.variant_strategy}` : ""}</span>
        </div>
      </div>
    </div>
  );
}