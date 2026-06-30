import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import Layout from "../components/Layout";
import { FileText, ChevronDown, Loader, Plus } from "lucide-react";

const COLUMNS = [
  { key: "planning", label: "Planning", color: "#64748b" },
  { key: "documents", label: "Documents", color: "#2563eb" },
  { key: "submitted", label: "Submitted", color: "#7c3aed" },
  { key: "accepted", label: "Accepted", color: "#16a34a" },
  { key: "rejected", label: "Rejected", color: "#dc2626" },
  { key: "waitlisted", label: "Waitlisted", color: "#d97706" },
];

const STATUS_ORDER = COLUMNS.map(c => c.key);

function AppCard({ app, onMove, onOpen }) {
  const [moving, setMoving] = useState(false);
  const [showMenu, setShowMenu] = useState(false);

  const moveTo = async (status) => {
    setMoving(true); setShowMenu(false);
    await onMove(app.id, status);
    setMoving(false);
  };

  const col = COLUMNS.find(c => c.key === app.status) || COLUMNS[0];

  return (
    <div className="app-card">
      <div className="app-card-top">
        <h3 className="app-card-name">{app.university_name}</h3>
        {app.program && <p className="app-card-program">{app.program}</p>}
      </div>

      {app.deadline && (
        <div className="app-card-deadline">
          <span>Deadline: {new Date(app.deadline).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}</span>
        </div>
      )}

      <div className="app-card-actions">
        <button className="app-card-btn" onClick={() => onOpen(app.id)}>
          <FileText size={14} /> Documents
        </button>

        <div className="app-move-wrapper">
          <button className="app-move-btn" onClick={() => setShowMenu(!showMenu)} disabled={moving}>
            {moving ? <Loader size={14} className="spin" /> : <><ChevronDown size={14} /> Move</>}
          </button>
          {showMenu && (
            <div className="app-move-menu">
              {COLUMNS.filter(c => c.key !== app.status).map(c => (
                <button key={c.key} className="app-move-item" onClick={() => moveTo(c.key)}>
                  <span className="move-dot" style={{ background: c.color }} />
                  {c.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Column({ col, apps, onMove, onOpen }) {
  return (
    <div className="kanban-col">
      <div className="kanban-col-header" style={{ borderColor: col.color }}>
        <span className="kanban-col-title">{col.label}</span>
        <span className="kanban-col-count" style={{ background: col.color }}>{apps.length}</span>
      </div>
      <div className="kanban-col-body">
        {apps.length === 0
          ? <div className="kanban-empty">No applications</div>
          : apps.map(app => <AppCard key={app.id} app={app} onMove={onMove} onOpen={onOpen} />)
        }
      </div>
    </div>
  );
}

export default function TrackerPage({ session }) {
  const navigate = useNavigate();
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => api.get("/applications").then(res => {
    if (res.ok) setApplications(res.applications || []);
    setLoading(false);
  });

  useEffect(() => { load(); }, []);

  const moveApp = async (appId, status) => {
    const res = await api.put(`/applications/${appId}`, { status });
    if (res.ok) {
      setApplications(prev => prev.map(a => a.id === appId ? { ...a, status } : a));
    }
  };

  const openApp = (appId) => navigate(`/apply/${appId}`);

  const total = applications.length;
  const submitted = applications.filter(a => ["submitted", "accepted", "rejected", "waitlisted"].includes(a.status)).length;
  const accepted = applications.filter(a => a.status === "accepted").length;

  if (loading) return (
    <Layout session={session}>
      <div className="page-loading"><Loader size={32} className="spin" /></div>
    </Layout>
  );

  return (
    <Layout session={session}>
      <div className="tracker-root">
        {/* Header */}
        <div className="tracker-header">
          <div>
            <h1 className="tracker-title">Application Tracker</h1>
            <p className="tracker-sub">Manage all your university applications in one place</p>
          </div>
          <button className="match-btn" onClick={() => navigate("/dashboard")}>
            <Plus size={16} /> Add University
          </button>
        </div>

        {/* Summary stats */}
        {total > 0 && (
          <div className="tracker-stats">
            <div className="tracker-stat">
              <span className="tracker-stat-num">{total}</span>
              <span className="tracker-stat-label">Total</span>
            </div>
            <div className="tracker-stat">
              <span className="tracker-stat-num">{submitted}</span>
              <span className="tracker-stat-label">Submitted</span>
            </div>
            <div className="tracker-stat">
              <span className="tracker-stat-num tracker-stat-green">{accepted}</span>
              <span className="tracker-stat-label">Accepted</span>
            </div>
          </div>
        )}

        {total === 0 ? (
          <div className="tracker-empty">
            <FileText size={56} color="#94a3b8" />
            <h3>No applications yet</h3>
            <p>Browse universities and click "Apply to this University" to start tracking your applications.</p>
            <button className="ob-btn-primary" onClick={() => navigate("/dashboard")}>Browse Universities</button>
          </div>
        ) : (
          <div className="kanban-board">
            {COLUMNS.map(col => (
              <Column
                key={col.key}
                col={col}
                apps={applications.filter(a => a.status === col.key)}
                onMove={moveApp}
                onOpen={openApp}
              />
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
