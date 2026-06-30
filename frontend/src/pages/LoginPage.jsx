import { useState } from "react";
import { supabase } from "../lib/supabase";

export default function LoginPage() {
  const [googleLoading, setGoogleLoading] = useState(false);
  const [emailLoading, setEmailLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleGoogle = async () => {
    setGoogleLoading(true);
    setError("");
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/dashboard` },
    });
    if (error) { setError(error.message); setGoogleLoading(false); }
  };

  const handleEmailAuth = async (e) => {
    e.preventDefault();
    setEmailLoading(true);
    setError("");
    setSuccess("");

    if (isSignUp) {
      const { error } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: { emailRedirectTo: `${window.location.origin}/dashboard` },
      });
      if (error) {
        setError(error.message);
      } else {
        setSuccess("Account created! Check your email to confirm, then sign in.");
        setIsSignUp(false);
        setPassword("");
      }
    } else {
      const { error } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (error) setError(error.message);
    }
    setEmailLoading(false);
  };

  const switchMode = () => {
    setIsSignUp(v => !v);
    setError("");
    setSuccess("");
  };

  return (
    <div className="login-root">
      <div className="login-left">
        <div className="login-brand">
          <span className="login-logo">A</span>
          <span className="login-name">AdmitAI</span>
        </div>
        <h1 className="login-headline">Your personal guide to German universities</h1>
        <p className="login-sub">
          AI-powered matching, personalised SOPs, scholarship discovery, and
          application tracking — built for Indian students.
        </p>
        <div className="login-features">
          {[
            "Smart university matching with fit scores",
            "AI-generated SOP tailored to your profile",
            "Scholarship eligibility in seconds",
            "Full application tracker with deadlines",
          ].map(f => (
            <div key={f} className="login-feature">
              <span className="login-check">✓</span>
              <span>{f}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="login-right">
        <div className="login-card">
          <h2 className="login-card-title">{isSignUp ? "Create account" : "Welcome back"}</h2>
          <p className="login-card-sub">
            {isSignUp ? "Start your admissions journey" : "Sign in to continue"}
          </p>

          {error && <div className="login-error">{error}</div>}
          {success && <div className="login-success">{success}</div>}

          {/* Google */}
          <button className="google-btn" onClick={handleGoogle} disabled={googleLoading || emailLoading}>
            {googleLoading ? <span className="btn-spinner" /> : (
              <svg width="20" height="20" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
            )}
            {googleLoading ? "Redirecting…" : "Continue with Google"}
          </button>

          <div className="login-divider"><span>or</span></div>

          {/* Email + Password */}
          <form onSubmit={handleEmailAuth} className="login-email-form">
            <input
              type="email"
              className="login-email-input"
              placeholder="Email address"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
            <input
              type="password"
              className="login-email-input"
              placeholder="Password (min 6 characters)"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              minLength={6}
              autoComplete={isSignUp ? "new-password" : "current-password"}
            />
            <button
              type="submit"
              className="login-email-btn"
              disabled={emailLoading || googleLoading || !email.trim() || password.length < 6}
            >
              {emailLoading ? <span className="btn-spinner" /> : (isSignUp ? "Create Account" : "Sign In")}
            </button>
          </form>

          <div className="login-toggle-mode">
            {isSignUp ? "Already have an account?" : "Don't have an account?"}
            {" "}
            <button type="button" className="login-link-btn" onClick={switchMode}>
              {isSignUp ? "Sign in" : "Sign up"}
            </button>
          </div>

          <p className="login-terms">
            By signing in you agree to our terms of service. Your data is stored
            securely and never shared.
          </p>
        </div>
      </div>
    </div>
  );
}
