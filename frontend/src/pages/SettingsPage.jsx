// src/pages/SettingsPage.jsx — Account settings / profile
import React, { useState } from "react";
import { useTheme } from "../App";
import { useAuth } from "../context/AuthContext";
import { resendVerification } from "../api/auth";

export default function SettingsPage() {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;
  const { user, updateProfile } = useAuth();

  const [form, setForm] = useState({
    name: user?.name || "", role: user?.role || "", company: user?.company || "",
    company_description: user?.company_description || "", company_url: user?.company_url || "",
    company_location: user?.company_location || "", company_size: user?.company_size || "",
    signature: user?.signature || "", photo_url: user?.photo_url || "",
  });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [resendMsg, setResendMsg] = useState(null);

  const set = (k) => (e) => { setSaved(false); setForm((s) => ({ ...s, [k]: e.target.value })); };

  const onPhoto = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 1.5 * 1024 * 1024) { setError("Photo must be under 1.5 MB"); return; }
    const reader = new FileReader();
    reader.onload = () => { setSaved(false); setForm((s) => ({ ...s, photo_url: reader.result })); };
    reader.readAsDataURL(file);
  };

  const save = async () => {
    setError(null); setBusy(true);
    try {
      await updateProfile(form);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.message || "Could not save");
    } finally {
      setBusy(false);
    }
  };

  const doResend = async () => {
    setResendMsg("Sending…");
    try { const r = await resendVerification(); setResendMsg(r.status === "sent" ? "Verification email sent ✓" : r.status === "already_verified" ? "Already verified" : "Failed to send"); }
    catch { setResendMsg("Failed to send"); }
  };

  const inputStyle = {
    width: "100%", padding: "10px 12px", borderRadius: 9, boxSizing: "border-box",
    border: `1px solid ${c.border}`, background: c.bg, color: c.text,
    fontSize: 14, fontFamily: f.body, outline: "none", marginTop: 5,
  };
  const label = { fontSize: 11, color: c.textDim, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 };
  const card = { background: c.surface, border: `1px solid ${c.border}`, borderRadius: 14, padding: 24 };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 640 }}>
      <div>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: c.text, margin: 0 }}>Account settings</h2>
        <p style={{ fontSize: 13, color: c.textDim, marginTop: 4 }}>
          Your profile is used as the <b>sender identity</b> when generating outreach emails.
        </p>
      </div>

      {/* Email + verification */}
      <div style={{ ...card, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={label}>Email</div>
          <div style={{ fontSize: 15, color: c.text, fontFamily: f.mono, marginTop: 4 }}>{user?.email}</div>
        </div>
        {user?.email_verified ? (
          <span style={{ fontSize: 12, color: c.green, fontWeight: 600, background: c.greenGlow, padding: "6px 12px", borderRadius: 8 }}>
            ✓ Verified
          </span>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 12, color: c.warm, fontWeight: 600, background: c.warmGlow, padding: "6px 12px", borderRadius: 8 }}>
              Not verified
            </span>
            <button onClick={doResend} style={{
              fontSize: 12, color: c.accent, background: "none", border: `1px solid ${c.border}`,
              borderRadius: 8, padding: "6px 12px", cursor: "pointer", fontFamily: f.body,
            }}>Resend email</button>
            {resendMsg && <span style={{ fontSize: 12, color: c.textDim }}>{resendMsg}</span>}
          </div>
        )}
      </div>

      {/* Profile form */}
      <div style={{ ...card, display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Photo */}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{
            position: "relative",
            width: 64, height: 64, borderRadius: 32, overflow: "hidden", flexShrink: 0,
            background: c.accentGlow, border: `1px solid ${c.border}`,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: c.accent, fontWeight: 700, fontSize: 24,
          }}>
            {form.name?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase() || "?"}
            {form.photo_url && (
              <img
                src={form.photo_url}
                alt=""
                referrerPolicy="no-referrer"
                onError={(e) => { e.currentTarget.style.display = "none"; }}
                style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
              />
            )}
          </div>
          <label style={{ fontSize: 13, color: c.accent, cursor: "pointer", fontWeight: 600 }}>
            {form.photo_url ? "Change profile photo" : "Add profile photo"}
            <input type="file" accept="image/*" onChange={onPhoto} style={{ display: "none" }} />
          </label>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div><span style={label}>Full name</span><input style={inputStyle} value={form.name} onChange={set("name")} /></div>
          <div><span style={label}>Role / title</span><input style={inputStyle} value={form.role} onChange={set("role")} /></div>
          <div><span style={label}>Company</span><input style={inputStyle} value={form.company} onChange={set("company")} /></div>
          <div><span style={label}>Company website</span><input style={inputStyle} value={form.company_url} onChange={set("company_url")} /></div>
          <div><span style={label}>Company location</span><input style={inputStyle} value={form.company_location} onChange={set("company_location")} /></div>
          <div><span style={label}>Company size</span><input style={inputStyle} value={form.company_size} onChange={set("company_size")} /></div>
        </div>
        <div><span style={label}>Company description</span>
          <textarea style={{ ...inputStyle, minHeight: 64, resize: "vertical" }} value={form.company_description}
            onChange={set("company_description")} />
        </div>
        <div><span style={label}>Email signature</span>
          <textarea style={{ ...inputStyle, minHeight: 56, resize: "vertical" }} value={form.signature}
            onChange={set("signature")} />
        </div>

        {error && <div style={{ fontSize: 13, color: c.hot }}>{error}</div>}

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button onClick={save} disabled={busy} style={{
            padding: "11px 24px", borderRadius: 9, border: "none", background: c.accent,
            color: "#fff", fontWeight: 600, fontSize: 14, cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.6 : 1,
          }}>{busy ? "Saving…" : "Save changes"}</button>
          {saved && <span style={{ fontSize: 13, color: c.green, fontWeight: 600 }}>✓ Saved</span>}
        </div>
      </div>
    </div>
  );
}
