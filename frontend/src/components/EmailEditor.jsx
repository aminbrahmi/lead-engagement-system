// src/components/EmailEditor.jsx — With editable email field
import React, { useState, useEffect } from "react";
import { useTheme } from "../App";
import { sendEmail, updateDraftEmail } from "../api/email";

export default function EmailEditor({ 
  leadId, 
  leadEmail, 
  draftEmail, 
  draftEmails, 
  onSave,
  onRefresh
}) {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;

  // A/B variant state
  const variants = draftEmails || (draftEmail ? { A: draftEmail } : {});
  const variantKeys = Object.keys(variants);
  const [activeVariant, setActiveVariant] = useState(variantKeys[0] || "A");

  const currentEmail = variants[activeVariant] || {};
  const [subject, setSubject] = useState(currentEmail.subject || "");
  const [body, setBody] = useState(currentEmail.body || "");
  const [cc, setCc] = useState(currentEmail.cc || "");
  const [toEmail, setToEmail] = useState(leadEmail || "");  // ← Editable email
  const [saved, setSaved] = useState(false);
  const [isPreview, setIsPreview] = useState(false);

  // States for sending
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState(null);
  const [error, setError] = useState(null);

  // Reset fields when variant or lead changes
  useEffect(() => {
    const v = variants[activeVariant] || {};
    setSubject(v.subject || "");
    setBody(v.body || "");
    setCc(v.cc || "");
    setToEmail(leadEmail || "");
    setSaved(false);
    setIsPreview(false);
    setError(null);
    setSendResult(null);
  }, [leadId, activeVariant, leadEmail]);

  const handleSave = async () => {
    try {
      // Save draft email
      await updateDraftEmail(leadId, activeVariant, subject, body, cc);
      
      // Update email if changed
      if (toEmail !== leadEmail) {
        await updateLeadEmail(leadId, toEmail);
      }
      
      // Update local state via callback
      onSave(leadId, { subject, body, cc, variant: activeVariant });
      
      setSaved(true);
      setError(null);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(`Save failed: ${err.message}`);
    }
  };

  const updateLeadEmail = async (leadId, newEmail) => {
    // Update lead email in database
    const response = await fetch(`http://localhost:8000/leads/${leadId}/email`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: newEmail }),
    });

    if (!response.ok) {
      throw new Error('Failed to update email');
    }
  };

  const handleSend = async () => {
    if (!toEmail) {
      setError("No email address");
      return;
    }

    // Save email if changed before sending
    if (toEmail !== leadEmail) {
      try {
        await updateLeadEmail(leadId, toEmail);
      } catch (err) {
        setError(`Failed to update email: ${err.message}`);
        return;
      }
    }

    // Confirm send
    const confirmMsg = `Send email to ${toEmail}?\n\nThis will:\n` +
      `- Send the ${activeVariant} variant immediately\n` +
      `- Create follow-ups for J+3, J+7, J+14`;
    
    if (!window.confirm(confirmMsg)) {
      return;
    }

    setSending(true);
    setError(null);
    setSendResult(null);

    try {
      const result = await sendEmail(leadId, activeVariant, true);
      
      setSendResult({
        success: true,
        message: `Email sent to ${toEmail}! ${result.followups_created} follow-ups scheduled.`,
        messageId: result.message_id,
        followups: result.followups_created,
      });

      // Refresh lead data
      if (onRefresh) onRefresh();
    } catch (err) {
      setError(`Send failed: ${err.message}`);
      setSendResult({ success: false, message: err.message });
    } finally {
      setSending(false);
    }
  };

  const wordCount = body.split(/\s+/).filter(Boolean).length;
  const emailChanged = toEmail !== leadEmail;

  if (variantKeys.length === 0) return null;

  return (
    <div>
      {/* Header with A/B toggle */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 16, flexWrap: "wrap", gap: 8,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h4 style={{ fontSize: 10, color: c.textDim, textTransform: "uppercase", letterSpacing: 1, fontWeight: 700 }}>
            Draft email
          </h4>
          {/* A/B toggle buttons */}
          {variantKeys.length > 1 && (
            <div style={{ display: "flex", gap: 4 }}>
              {variantKeys.map((v) => (
                <button
                  key={v}
                  onClick={() => setActiveVariant(v)}
                  style={{
                    padding: "3px 10px", borderRadius: 4, border: `1px solid ${activeVariant === v ? c.accent : c.border}`,
                    background: activeVariant === v ? c.accentGlow : "transparent",
                    color: activeVariant === v ? c.accent : c.textMuted,
                    fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: f.mono,
                  }}
                >
                  Variant {v}
                </button>
              ))}
            </div>
          )}
          {/* Strategy label */}
          {currentEmail.variant_strategy && (
            <span style={{
              fontSize: 10, padding: "2px 8px", borderRadius: 4,
              background: c.surfaceAlt, color: c.textMuted, fontFamily: f.mono,
            }}>
              {currentEmail.variant_strategy}
            </span>
          )}
        </div>

        {/* Actions */}
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          {saved && <span style={{ fontSize: 12, color: c.green, fontFamily: f.mono }}>✓ Saved</span>}
          {error && <span style={{ fontSize: 11, color: c.red, maxWidth: 200 }}>{error}</span>}
          {sendResult?.success && (
            <span style={{ fontSize: 11, color: c.green, fontFamily: f.mono }}>
              ✓ {sendResult.message}
            </span>
          )}

          {/* Email changed indicator */}
          {emailChanged && (
            <span style={{ fontSize: 10, color: c.warm, fontFamily: f.mono }}>
              ⚠ Email changed - save first
            </span>
          )}

          {/* Preview toggle */}
          <button
            onClick={() => setIsPreview(!isPreview)}
            style={{
              padding: "5px 12px", borderRadius: 6, border: `1px solid ${c.border}`,
              background: isPreview ? c.accentGlow : "transparent",
              color: isPreview ? c.accent : c.textMuted,
              fontSize: 12, fontWeight: 500, cursor: "pointer", fontFamily: f.body,
            }}
          >
            {isPreview ? "Edit" : "Preview"}
          </button>

          {/* Save draft */}
          <button 
            onClick={handleSave} 
            disabled={sending}
            style={{
              padding: "5px 14px", borderRadius: 6, border: "none", cursor: "pointer",
              background: c.accent, color: "#fff", fontSize: 12, fontWeight: 600, 
              fontFamily: f.body, opacity: sending ? 0.5 : 1,
            }}
          >
            Save Draft
          </button>

          {/* Send button */}
          <button 
            onClick={handleSend}
            disabled={sending || !toEmail}
            title={!toEmail ? "No email address" : "Send email + create follow-ups"}
            style={{
              padding: "5px 14px", borderRadius: 6, border: "none", 
              cursor: (sending || !toEmail) ? "not-allowed" : "pointer",
              background: !toEmail ? c.border : c.green, 
              color: "#fff", fontSize: 12, fontWeight: 600, fontFamily: f.body,
              opacity: (sending || !toEmail) ? 0.5 : 1,
            }}
          >
            {sending ? "Sending..." : "Send"}
          </button>
        </div>
      </div>

      {/* Success message */}
      {sendResult?.success && (
        <div style={{
          padding: "12px 16px", borderRadius: 8, marginBottom: 16,
          background: c.greenGlow, border: `1px solid ${c.green}`,
        }}>
          <div style={{ fontSize: 13, color: c.green, fontWeight: 600, marginBottom: 4 }}>
            ✓ Email Sent Successfully!
          </div>
          <div style={{ fontSize: 12, color: c.textMuted }}>
            Sent to: <strong>{toEmail}</strong>
            <br />
            Message ID: <code style={{ fontFamily: f.mono, fontSize: 11 }}>{sendResult.messageId}</code>
            <br />
            {sendResult.followups} follow-ups scheduled (J+3, J+7, J+14)
          </div>
        </div>
      )}

      {/* Email form / preview */}
      <div style={{
        background: c.surface, border: `1px solid ${c.border}`,
        borderRadius: 10, overflow: "hidden",
      }}>
        {/* TO field - EDITABLE */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10, padding: "10px 16px",
          borderBottom: `1px solid ${c.border}`,
        }}>
          <span style={{ fontSize: 11, color: c.textDim, fontWeight: 600, minWidth: 50, textTransform: "uppercase", letterSpacing: .5 }}>To</span>
          {isPreview ? (
            <span style={{ flex: 1, fontFamily: f.mono, fontSize: 13, color: c.text }}>
              {toEmail || "—"}
            </span>
          ) : (
            <input
              value={toEmail}
              onChange={(e) => setToEmail(e.target.value)}
              placeholder="recipient@example.com"
              style={{
                flex: 1, padding: "4px 0", border: "none", background: "transparent",
                color: c.text, fontFamily: f.mono, fontSize: 13, outline: "none",
              }}
            />
          )}
          {emailChanged && !isPreview && (
            <span style={{ fontSize: 10, color: c.warm }}>Modified</span>
          )}
        </div>

        {/* CC field */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10, padding: "8px 16px",
          borderBottom: `1px solid ${c.border}`,
        }}>
          <span style={{ fontSize: 11, color: c.textDim, fontWeight: 600, minWidth: 50, textTransform: "uppercase", letterSpacing: .5 }}>CC</span>
          {isPreview ? (
            <span style={{ flex: 1, fontSize: 13, color: cc ? c.text : c.textDim }}>{cc || "—"}</span>
          ) : (
            <input
              value={cc} onChange={(e) => setCc(e.target.value)}
              placeholder="team@company.com"
              style={{
                flex: 1, padding: "4px 0", border: "none", background: "transparent",
                color: c.text, fontFamily: f.body, fontSize: 13, outline: "none",
              }}
            />
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
            <input
              value={subject} onChange={(e) => setSubject(e.target.value)}
              style={{
                flex: 1, padding: "4px 0", border: "none", background: "transparent",
                color: c.text, fontFamily: f.body, fontSize: 14, fontWeight: 500, outline: "none",
              }}
            />
          )}
        </div>

        {/* Body */}
        <div style={{ padding: "16px" }}>
          {isPreview ? (
            <div style={{
              fontSize: 14, lineHeight: 1.8, color: c.text, whiteSpace: "pre-wrap",
              fontFamily: f.body, minHeight: 200,
            }}>
              {body}
            </div>
          ) : (
            <textarea
              value={body} onChange={(e) => setBody(e.target.value)}
              rows={12}
              style={{
                width: "100%", padding: 0, border: "none", background: "transparent",
                color: c.text, fontFamily: f.body, fontSize: 14, lineHeight: 1.8,
                outline: "none", resize: "vertical", minHeight: 200,
              }}
            />
          )}
        </div>

        {/* Footer stats */}
        <div style={{
          display: "flex", justifyContent: "space-between", padding: "8px 16px",
          borderTop: `1px solid ${c.border}`, fontSize: 11, color: c.textDim,
        }}>
          <span>{wordCount} words</span>
          <span>
            Variant {activeVariant}
            {currentEmail.variant_strategy && ` — ${currentEmail.variant_strategy}`}
          </span>
        </div>
      </div>
    </div>
  );
}