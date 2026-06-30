import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import Layout from "../components/Layout";
import { MapPin, Loader, TrendingUp, RefreshCw } from "lucide-react";

function ScoreBadge({ score }) {
  if (!score && score !== 0) return <span className="score-badge score-none">—</span>;
  const cls = score >= 80 ? "score-great" : score >= 65 ? "score-good" : score >= 45 ? "score-ok" : "score-low";
  const label = score >= 80 ? "Strong Match" : score >= 65 ? "Good Fit" : score >= 45 ? "Possible" : "Reach";
  return <span className={`score-badge ${cls}`}>{score} · {label}</span>;
}

function TypeBadge({ type }) {
  const map = { public_research: "Public Research", public_applied: "Applied Sciences", private: "Private" };
  const cls = { public_research: "type-research", public_applied: "type-applied", private: "type-private" };
  return <span className={`type-badge ${cls[type] || ""}`}>{map[type] || type}</span>;
}

function UniCard({ uni, onClick }) {
  return (
    <div className="uni-card" onClick={onClick}>
      <div className="uni-card-top">
        <div className="uni-card-info">
          <TypeBadge type={uni.type} />
          {uni.ranking_qs && <span className="qs-badge">QS #{uni.ranking_qs}</span>}
        </div>
        <ScoreBadge score={uni.fit_score} />
      </div>

      <h3 className="uni-card-name">{uni.name}</h3>

      <div className="uni-card-loc">
        <MapPin size={13} />
        <span>{uni.city}, {uni.state}</span>
      </div>

      <p className="uni-card-desc">{uni.description?.slice(0, 100)}…</p>

      <div className="uni-card-stats">
        <div className="uni-stat">
          <span className="uni-stat-label">Tuition</span>
          <span className="uni-stat-val">{uni.tuition_eur_semester === 0 ? "Free" : `€${uni.tuition_eur_semester?.toLocaleString()}/sem`}</span>
        </div>
        <div className="uni-stat">
          <span className="uni-stat-label">Living cost</span>
          <span className="uni-stat-val">~€{uni.living_cost_eur_month}/mo</span>
        </div>
        <div className="uni-stat">
          <span className="uni-stat-label">APS needed</span>
          <span className="uni-stat-val">{uni.aps_required ? "Yes" : "No"}</span>
        </div>
      </div>

      <div className="uni-card-footer">
        <span className="uni-view-link">View details →</span>
      </div>
    </div>
  );
}

const TYPE_FILTERS = [
  { key: "all", label: "All" },
  { key: "public_research", label: "Research Universities" },
  { key: "public_applied", label: "Applied Sciences" },
  { key: "private", label: "Private" },
];

export default function DashboardPage({ session }) {
  const navigate = useNavigate();
  const [unis, setUnis] = useState([]);
  const [loading, setLoading] = useState(true);
  const [matching, setMatching] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState("");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    Promise.all([
      api.get("/universities"),
      api.get("/auth/me"),
    ]).then(([unisRes, meRes]) => {
      if (unisRes.ok) setUnis(unisRes.universities);
      if (meRes.ok) setProfile(meRes.profile);
      setLoading(false);
    });
  }, []);

  const syncDaad = async () => {
    setSyncing(true);
    setSyncMsg("Fetching from DAAD — this takes up to 60s…");
    const res = await api.post("/admin/sync-universities", {});
    if (res.ok) {
      setSyncMsg(`Synced ${res.universities_found} universities from DAAD`);
      const fresh = await api.get("/universities");
      if (fresh.ok) setUnis(fresh.universities);
    } else {
      setSyncMsg(`Sync failed: ${res.error}`);
    }
    setSyncing(false);
    setTimeout(() => setSyncMsg(""), 6000);
  };

  const runMatch = async () => {
    setMatching(true);
    const res = await api.post("/match", {});
    if (res.ok) {
      // Reload with scores
      const fresh = await api.get("/universities");
      if (fresh.ok) setUnis(fresh.universities);
    }
    setMatching(false);
  };

  const needsOnboarding = !profile?.profile_complete;

  const displayed = unis
    .filter(u => filter === "all" || u.type === filter)
    .filter(u => !search || u.name.toLowerCase().includes(search.toLowerCase()) || u.city?.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => (b.fit_score || 0) - (a.fit_score || 0));

  const hasScores = unis.some(u => u.fit_score != null);

  if (loading) return (
    <Layout session={session}>
      <div className="dashboard-root">
        <div className="dashboard-header">
          <div>
            <h1 className="dashboard-title">University Matches</h1>
            <p className="dashboard-sub">Loading universities…</p>
          </div>
        </div>
        <div className="uni-grid">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="uni-card uni-card-skeleton">
              <div className="skel skel-line skel-short" />
              <div className="skel skel-line skel-long" style={{ marginTop: 12 }} />
              <div className="skel skel-line skel-mid" style={{ marginTop: 8 }} />
              <div className="skel skel-line skel-mid" style={{ marginTop: 8 }} />
            </div>
          ))}
        </div>
      </div>
    </Layout>
  );

  return (
    <Layout session={session}>
      <div className="dashboard-root">
        {/* Header */}
        <div className="dashboard-header">
          <div>
            <h1 className="dashboard-title">University Matches</h1>
            <p className="dashboard-sub">
              {hasScores
                ? `Showing ${displayed.length} universities sorted by your fit score`
                : `${unis.length} German universities — run matching to see your fit scores`}
            </p>
          </div>
          <div className="dashboard-header-actions">
            <button
              className="sync-btn"
              onClick={syncDaad}
              disabled={syncing || matching}
              title="Fetch latest university data from DAAD"
            >
              <RefreshCw size={15} className={syncing ? "spin" : ""} />
              {syncing ? "Syncing…" : "Sync from DAAD"}
            </button>
            <button
              className={`match-btn ${matching ? "match-btn-loading" : ""}`}
              onClick={needsOnboarding ? () => navigate("/onboarding") : runMatch}
              disabled={matching || syncing}
            >
              {matching ? <><Loader size={16} className="spin" /> Matching…</> : <><TrendingUp size={16} /> {needsOnboarding ? "Complete Profile First" : "Run Matching"}</>}
            </button>
          </div>
        </div>
        {syncMsg && <div className="sync-msg">{syncMsg}</div>}

        {needsOnboarding && (
          <div className="onboarding-banner">
            <div>
              <strong>Complete your profile to see fit scores</strong>
              <p>Upload your resume and fill in your academic details — takes 2 minutes.</p>
            </div>
            <button className="banner-btn" onClick={() => navigate("/onboarding")}>Start →</button>
          </div>
        )}

        {/* Filters */}
        <div className="filter-bar">
          <div className="type-filters">
            {TYPE_FILTERS.map(f => (
              <button key={f.key} className={`filter-chip ${filter === f.key ? "filter-active" : ""}`} onClick={() => setFilter(f.key)}>
                {f.label}
              </button>
            ))}
          </div>
          <input
            className="search-input"
            placeholder="Search by name or city…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        {/* Grid */}
        <div className="uni-grid">
          {displayed.map(uni => (
            <UniCard key={uni.id} uni={uni} onClick={() => navigate(`/university/${uni.id}`)} />
          ))}
        </div>

        {displayed.length === 0 && (
          <div className="empty-state">
            <p>No universities match your filters.</p>
            <button onClick={() => { setFilter("all"); setSearch(""); }}>Clear filters</button>
          </div>
        )}
      </div>
    </Layout>
  );
}
