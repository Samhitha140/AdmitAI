import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { supabase } from "./lib/supabase";
import LoginPage from "./pages/LoginPage";
import OnboardingPage from "./pages/OnboardingPage";
import DashboardPage from "./pages/DashboardPage";
import UniversityPage from "./pages/UniversityPage";
import ApplyPage from "./pages/ApplyPage";
import TrackerPage from "./pages/TrackerPage";

function Spinner() {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "#f8fafc" }}>
      <div style={{ width: 40, height: 40, border: "3px solid #e2e8f0", borderTop: "3px solid #4f46e5", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
    </div>
  );
}

function Guard({ session, children }) {
  if (!session) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  const [session, setSession] = useState(undefined);
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    // Resolve to null (logged-out) after 5s if Supabase is slow to respond
    const timeout = setTimeout(() => setSession(s => s === undefined ? null : s), 5000);
    supabase.auth.getSession().then(({ data: { session } }) => {
      clearTimeout(timeout);
      setSession(session);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => { clearTimeout(timeout); subscription.unsubscribe(); };
  }, []);

  if (session === undefined) return <Spinner />;

  const needsOnboarding = session && profile && !profile.profile_complete;

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={session ? <Navigate to="/dashboard" replace /> : <LoginPage />} />

        <Route path="/onboarding" element={
          <Guard session={session}>
            <OnboardingPage session={session} onComplete={() => setProfile(p => ({ ...p, profile_complete: true }))} />
          </Guard>
        } />

        <Route path="/dashboard" element={
          <Guard session={session}>
            <DashboardPage session={session} />
          </Guard>
        } />

        <Route path="/university/:id" element={
          <Guard session={session}>
            <UniversityPage session={session} />
          </Guard>
        } />

        <Route path="/apply/:id" element={
          <Guard session={session}>
            <ApplyPage session={session} />
          </Guard>
        } />

        <Route path="/tracker" element={
          <Guard session={session}>
            <TrackerPage session={session} />
          </Guard>
        } />

        <Route path="*" element={<Navigate to={session ? "/dashboard" : "/login"} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
