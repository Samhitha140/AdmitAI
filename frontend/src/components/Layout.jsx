import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { supabase } from "../lib/supabase";
import { api } from "../lib/api";
import {
  LayoutDashboard, CheckSquare, LogOut, Menu, X,
  GraduationCap, User, BookOpen, ChevronRight,
} from "lucide-react";
import { useState, useEffect } from "react";

const NAV_MAIN = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Universities" },
  { to: "/tracker",   icon: CheckSquare,    label: "My Applications" },
];

function SidebarStats({ apps }) {
  if (!apps || apps.length === 0) return null;
  const submitted = apps.filter(a => ["submitted","accepted","rejected","waitlisted"].includes(a.status)).length;
  const accepted  = apps.filter(a => a.status === "accepted").length;

  return (
    <div className="sidebar-stats-card">
      <p className="sidebar-stats-title">Application Summary</p>
      <div className="sidebar-stats-row">
        <div className="sidebar-stat-item">
          <span className="sidebar-stat-num">{apps.length}</span>
          <span className="sidebar-stat-lbl">Total</span>
        </div>
        <div className="sidebar-stat-divider" />
        <div className="sidebar-stat-item">
          <span className="sidebar-stat-num">{submitted}</span>
          <span className="sidebar-stat-lbl">Submitted</span>
        </div>
        <div className="sidebar-stat-divider" />
        <div className="sidebar-stat-item">
          <span className="sidebar-stat-num sidebar-stat-green">{accepted}</span>
          <span className="sidebar-stat-lbl">Accepted</span>
        </div>
      </div>
    </div>
  );
}

export default function Layout({ session, children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [apps, setApps] = useState([]);

  const name   = session?.user?.user_metadata?.full_name || session?.user?.email || "Student";
  const avatar = session?.user?.user_metadata?.avatar_url;
  const firstName = name.split(" ")[0];

  useEffect(() => {
    api.get("/applications").then(res => { if (res.ok) setApps(res.applications || []); });
  }, [location.pathname]);

  const pendingCount = apps.filter(a => a.status === "planning" || a.status === "documents").length;

  const logout = async () => {
    await supabase.auth.signOut();
    navigate("/login");
  };

  return (
    <div className="layout-root">
      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>

        {/* Brand */}
        <div className="sidebar-brand">
          <div className="sidebar-logo-wrap">
            <GraduationCap size={20} color="#fff" />
          </div>
          <span className="sidebar-name">AdmitAI</span>
          <button className="sidebar-close" onClick={() => setOpen(false)}><X size={18} /></button>
        </div>

        {/* Main nav */}
        <div className="sidebar-section">
          <p className="sidebar-section-label">Menu</p>
          <nav className="sidebar-nav">
            {NAV_MAIN.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`}
                onClick={() => setOpen(false)}
              >
                <Icon size={17} />
                <span>{label}</span>
                {label === "My Applications" && pendingCount > 0 && (
                  <span className="nav-badge">{pendingCount}</span>
                )}
                <ChevronRight size={14} className="nav-chevron" />
              </NavLink>
            ))}
          </nav>
        </div>

        {/* App stats */}
        <div className="sidebar-section">
          <SidebarStats apps={apps} />
        </div>

        {/* Quick links */}
        <div className="sidebar-section">
          <p className="sidebar-section-label">Account</p>
          <nav className="sidebar-nav">
            <NavLink
              to="/onboarding"
              className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`}
              onClick={() => setOpen(false)}
            >
              <User size={17} />
              <span>My Profile</span>
              <ChevronRight size={14} className="nav-chevron" />
            </NavLink>
          </nav>
        </div>

        {/* Tip card */}
        <div className="sidebar-section sidebar-tip">
          <div className="sidebar-tip-card">
            <BookOpen size={16} color="#4f46e5" />
            <div>
              <p className="sidebar-tip-title">Did you know?</p>
              <p className="sidebar-tip-body">German public universities charge no tuition — only a semester fee of ~€300.</p>
            </div>
          </div>
        </div>

        {/* User + sign out */}
        <div className="sidebar-bottom">
          <div className="sidebar-user">
            {avatar
              ? <img src={avatar} alt="" className="user-avatar" />
              : <div className="user-avatar-placeholder">{firstName[0]?.toUpperCase()}</div>
            }
            <div className="user-info">
              <span className="user-name">{firstName}</span>
              <span className="user-email">{session?.user?.email}</span>
            </div>
          </div>
          <button className="logout-btn" onClick={logout}>
            <LogOut size={15} />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      {/* Mobile overlay */}
      {open && <div className="sidebar-overlay" onClick={() => setOpen(false)} />}

      {/* ── Main ────────────────────────────────────────────────── */}
      <main className="layout-main">
        <header className="layout-header">
          <button className="menu-btn" onClick={() => setOpen(true)}><Menu size={20} /></button>
          <div className="header-right">
            {avatar
              ? <img src={avatar} alt="" className="header-avatar" />
              : <div className="header-avatar-placeholder">{firstName[0]?.toUpperCase()}</div>
            }
          </div>
        </header>
        <div className="layout-content">{children}</div>
      </main>
    </div>
  );
}
