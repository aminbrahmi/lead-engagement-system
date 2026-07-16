// src/pages/AuthPage.jsx — split-screen auth (CSS variables + Tabler icons)
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import logo from "../theleadflowlogo.png";
import "../styles/auth.css";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;
const NAME_RE  = /^[A-Za-zÀ-ÿ0-9'’.\- ]{1,60}$/;

function strength(pw) {
  let s = 0;
  if (pw.length >= 6) s++;
  if (pw.length >= 10) s++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++;
  if (/\d/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  return Math.min(s, 4); // 0..4
}
const STRENGTH = [
  { label: "", color: "var(--border)" },
  { label: "Very weak", color: "var(--danger)" },
  { label: "Weak", color: "var(--warn)" },
  { label: "Medium", color: "var(--warn)" },
  { label: "Strong", color: "var(--success)" },
];

export default function AuthPage({ mode = "login" }) {
  const navigate = useNavigate();
  const { login, register } = useAuth();

  const [tab, setTab] = useState(mode === "register" ? "signup" : "login");
  const [form, setForm] = useState({ firstName: "", lastName: "", email: "", password: "" });
  const [agree, setAgree] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState({});
  const [registered, setRegistered] = useState(null);
  const [showTerms, setShowTerms] = useState(false);

  const set = (k) => (e) => {
    setForm((s) => ({ ...s, [k]: e.target.value }));
    setTouched((s) => ({ ...s, [k]: true }));
  };
  const switchTab = (t) => { setTab(t); setError(null); navigate(t === "signup" ? "/register" : "/login"); };

  const fieldError = (k) => {
    if (!touched[k]) return null;
    const v = (form[k] || "").trim();
    if (k === "email")     return v && !EMAIL_RE.test(v) ? "Invalid email address" : null;
    if (k === "password")  return v.length > 0 && v.length < 6 ? "At least 6 characters" : null;
    if (k === "firstName" || k === "lastName") return v && !NAME_RE.test(v) ? "Invalid characters" : null;
    return null;
  };
  const cls = (k) => `auth-input${fieldError(k) ? " auth-input--error" : ""}`;
  const hint = (k) => fieldError(k) ? <div className="auth-hint">{fieldError(k)}</div> : null;

  const doLogin = async (e) => {
    e.preventDefault();
    if (!EMAIL_RE.test(form.email.trim())) { setError("Invalid email address"); return; }
    setError(null); setBusy(true);
    try { await login(form.email.trim(), form.password); navigate("/"); }
    catch (err) { setError(err.message || "Something went wrong"); }
    finally { setBusy(false); }
  };

  const doSignup = async (e) => {
    e.preventDefault();
    if (!form.firstName.trim() || !form.lastName.trim()) { setError("First and last name are required"); return; }
    if (!EMAIL_RE.test(form.email.trim())) { setError("Invalid email address"); return; }
    if (form.password.length < 6) { setError("Password must be at least 6 characters"); return; }
    if (!agree) { setError("You must accept the terms of use"); return; }
    setError(null); setBusy(true);
    try {
      const name = `${form.firstName.trim()} ${form.lastName.trim()}`;
      const res = await register(form.email.trim(), form.password, { name });
      setRegistered({ email: form.email.trim(), email_sent: res.email_sent });
    } catch (err) { setError(err.message || "Something went wrong"); }
    finally { setBusy(false); }
  };

  const googleSignIn = () => setError("Google sign-in is not configured yet.");

  const st = strength(form.password);

  const features = [
    ["ti-search", "Targeted prospecting", "AI finds and qualifies the right leads — hot, warm or cold."],
    ["ti-bolt", "Personalized emails", "Auto-written A/B emails with follow-up sequences."],
    ["ti-robot", "Multi-agent AI", "Specialized agents run your outreach end-to-end."],
    ["ti-inbox", "Smart inbox", "Replies are auto-classified and acted on for you."],
    ["ti-chart-line", "Track & optimize", "Replies, clicks and analytics in one place."],
  ];

  const TermsView = (
    <div>
      <h2 className="auth-title">Terms of Use</h2>
      <p className="auth-subtitle">Please read before creating an account.</p>
      <div className="auth-terms">
        <h4>1. Acceptance</h4>
        <p>By creating an account you agree to these Terms of Use and to our Privacy Policy.</p>
        <h4>2. The service</h4>
        <p>TheLeadFlow helps you run B2B outreach campaigns: finding prospects, writing emails, sending sequences and tracking replies.</p>
        <h4>3. Your responsibilities</h4>
        <p>You are solely responsible for the content you send and for complying with all applicable laws, including anti-spam and data-protection regulations. You must have a lawful basis to process the contact data you collect and email.</p>
        <h4>4. Account security</h4>
        <p>Keep your credentials confidential. You are responsible for all activity performed under your account.</p>
        <h4>5. Acceptable use</h4>
        <p>Do not use the service to send spam, harass recipients, or for any illegal purpose. We may suspend accounts that violate these terms.</p>
        <h4>6. Availability &amp; warranty</h4>
        <p>The service is provided “as is”, without warranty of any kind. We are not liable for indirect damages arising from its use.</p>
        <h4>7. Changes</h4>
        <p>We may update these terms. Continued use of the service after changes means you accept the updated terms.</p>
      </div>
      <button className="auth-btn auth-btn--primary" onClick={() => setShowTerms(false)}>← Back</button>
    </div>
  );

  return (
    <div className="auth-page">
      {/* ── Left: branding ── */}
      <div className="auth-brand">
        <div className="auth-brand__logo">
          <img src={logo} alt="TheLeadFlow" />
          <span>TheLeadFlow</span>
        </div>
        <div className="auth-brand__slogan">Automate your B2B outreach, end to end.</div>
        <div className="auth-brand__sub">
          Find the right prospects, reach them with AI-personalized emails,
          then track replies and optimize — on autopilot.
        </div>
        <div className="auth-features">
          {features.map(([icon, title, sub]) => (
            <div className="auth-feature" key={title}>
              <div className="auth-feature__icon"><i className={`ti ${icon}`} /></div>
              <div>
                <div className="auth-feature__title">{title}</div>
                <div className="auth-feature__sub">{sub}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Right: form ── */}
      <div className="auth-panel">
        <div className="auth-card">
          {registered ? (
            <div>
              <div style={{ fontSize: 40, marginBottom: 8 }}>📧</div>
              <h2 className="auth-title">Check your email</h2>
              <p className="auth-subtitle">
                {registered.email_sent
                  ? <>A verification link was sent to <b style={{ color: "var(--text-primary)" }}>{registered.email}</b>. Click it to activate your account.</>
                  : <>Your account was created, but the verification email couldn't be sent.</>}
              </p>
              <button className="auth-btn auth-btn--primary" onClick={() => navigate("/")}>Continue →</button>
            </div>
          ) : showTerms ? (
            TermsView
          ) : (
            <>
              {/* Tabs */}
              <div className="auth-tabs">
                <button className={`auth-tab ${tab === "login" ? "auth-tab--active" : ""}`} onClick={() => switchTab("login")}>Login</button>
                <button className={`auth-tab ${tab === "signup" ? "auth-tab--active" : ""}`} onClick={() => switchTab("signup")}>Sign up</button>
              </div>

              {/* ── LOGIN ── */}
              <div style={{ display: tab === "login" ? "block" : "none" }}>
                <h2 className="auth-title">Welcome back</h2>
                <p className="auth-subtitle">Sign in to continue</p>
                <form onSubmit={doLogin}>
                  <div className="auth-field">
                    <span className="auth-label">Email</span>
                    <div className="auth-input-wrap">
                      <i className="ti ti-mail" />
                      <input className={cls("email")} type="email" value={form.email} onChange={set("email")} placeholder="email@example.com" autoComplete="email" />
                    </div>
                    {hint("email")}
                  </div>
                  <div className="auth-field">
                    <span className="auth-label">Password</span>
                    <div className="auth-input-wrap">
                      <i className="ti ti-lock" />
                      <input className="auth-input" type="password" value={form.password} onChange={set("password")} placeholder="••••••••" autoComplete="current-password" />
                    </div>
                  </div>
                  {error && tab === "login" && <div className="auth-error">{error}</div>}
                  <button className="auth-btn auth-btn--primary" disabled={busy} type="submit">
                    {busy ? "Signing in…" : <><i className="ti ti-login-2" /> Sign in</>}
                  </button>
                </form>
                <div className="auth-divider">or</div>
                <button className="auth-btn auth-btn--google" onClick={googleSignIn} type="button">
                  <i className="ti ti-brand-google" /> Continue with Google
                </button>
                <div className="auth-switch">No account yet? <b onClick={() => switchTab("signup")}>Sign up</b></div>
              </div>

              {/* ── SIGNUP ── */}
              <div style={{ display: tab === "signup" ? "block" : "none" }}>
                <h2 className="auth-title">Create an account</h2>
                <p className="auth-subtitle">Join TheLeadFlow in seconds</p>
                <form onSubmit={doSignup}>
                  <div className="auth-row">
                    <div className="auth-field">
                      <span className="auth-label">First name</span>
                      <div className="auth-input-wrap">
                        <i className="ti ti-user" />
                        <input className={cls("firstName")} value={form.firstName} onChange={set("firstName")} placeholder="First name" />
                      </div>
                      {hint("firstName")}
                    </div>
                    <div className="auth-field">
                      <span className="auth-label">Last name</span>
                      <div className="auth-input-wrap">
                        <i className="ti ti-user" />
                        <input className={cls("lastName")} value={form.lastName} onChange={set("lastName")} placeholder="Last name" />
                      </div>
                      {hint("lastName")}
                    </div>
                  </div>
                  <div className="auth-field">
                    <span className="auth-label">Email</span>
                    <div className="auth-input-wrap">
                      <i className="ti ti-mail" />
                      <input className={cls("email")} type="email" value={form.email} onChange={set("email")} placeholder="email@example.com" autoComplete="email" />
                    </div>
                    {hint("email")}
                  </div>
                  <div className="auth-field">
                    <span className="auth-label">Password</span>
                    <div className="auth-input-wrap">
                      <i className="ti ti-lock" />
                      <input className={cls("password")} type="password" value={form.password} onChange={set("password")} placeholder="••••••••" autoComplete="new-password" />
                    </div>
                    {form.password && (
                      <>
                        <div className="auth-strength">
                          {[1, 2, 3, 4].map((n) => (
                            <div key={n} className="auth-strength__seg"
                              style={{ background: n <= st ? STRENGTH[st].color : "var(--border)" }} />
                          ))}
                        </div>
                        <div className="auth-strength__label" style={{ color: STRENGTH[st].color }}>{STRENGTH[st].label}</div>
                      </>
                    )}
                    {hint("password")}
                  </div>
                  <label className="auth-check">
                    <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
                    <span>I agree to the <a href="#terms" onClick={(e) => { e.preventDefault(); setShowTerms(true); }}>terms of use</a> and privacy policy.</span>
                  </label>
                  {error && tab === "signup" && <div className="auth-error">{error}</div>}
                  <button className="auth-btn auth-btn--primary" disabled={busy} type="submit">
                    {busy ? "Creating…" : <><i className="ti ti-user-plus" /> Create my account</>}
                  </button>
                </form>
                <div className="auth-divider">or</div>
                <button className="auth-btn auth-btn--google" onClick={googleSignIn} type="button">
                  <i className="ti ti-brand-google" /> Sign up with Google
                </button>
                <div className="auth-switch">Already have an account? <b onClick={() => switchTab("login")}>Log in</b></div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
