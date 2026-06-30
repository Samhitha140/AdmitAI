import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import Layout from "../components/Layout";
import { ArrowLeft, FileText, Loader, CheckCircle, Copy, Download, ChevronDown, ChevronUp, GraduationCap } from "lucide-react";

const LOR_LABELS = {
  thesis_supervisor: "Thesis Supervisor",
  internship_manager: "Internship Manager",
  course_professor: "Course Professor",
  research_collaborator: "Research Collaborator",
};

// Templates in Supabase use {{placeholder_name}} syntax
const PLACEHOLDER_RE = /\{\{([a-z_]+)\}\}/g;

function TabBar({ tabs, active, onChange }) {
  return (
    <div className="tab-bar">
      {tabs.map(t => (
        <button key={t.key} className={`tab-btn ${active === t.key ? "tab-active" : ""}`} onClick={() => onChange(t.key)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

function SopPanel({ app }) {
  const [sop, setSop] = useState("");
  const [loading, setLoading] = useState(false);
  const [generated, setGenerated] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  const generate = async () => {
    setLoading(true); setError("");
    const res = await api.post(`/applications/${app.id}/sop`, {});
    setLoading(false);
    if (!res.ok) { setError(res.error || "SOP generation failed. Check that your profile is complete."); return; }
    setSop(res.sop || ""); setGenerated(true);
  };

  const copy = () => {
    navigator.clipboard.writeText(sop);
    setCopied(true); setTimeout(() => setCopied(false), 2000);
  };

  const download = () => {
    const blob = new Blob([sop], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `SOP_${app.university_name?.replace(/\s+/g, "_")}.txt`;
    a.click();
  };

  return (
    <div className="sop-panel">
      <div className="sop-header">
        <div>
          <h2 className="sop-title">Statement of Purpose</h2>
          <p className="sop-sub">AI-generated using your profile and resume — tailored for {app.university_name}</p>
        </div>
        {generated && (
          <div className="sop-actions">
            <button className="sop-action-btn" onClick={copy}>
              {copied ? <CheckCircle size={16} color="#16a34a" /> : <Copy size={16} />}
              {copied ? "Copied" : "Copy"}
            </button>
            <button className="sop-action-btn" onClick={download}>
              <Download size={16} /> Download
            </button>
          </div>
        )}
      </div>

      {!generated ? (
        <div className="sop-generate-area">
          <div className="sop-info-box">
            <FileText size={48} color="#4f46e5" />
            <h3>Generate your personalised SOP</h3>
            <p>AdmitAI writes a complete Statement of Purpose based on your academic background, projects, work experience, and motivation — tailored specifically for {app.university_name}.</p>
            <ul className="sop-bullets">
              <li>~700 words, university-specific</li>
              <li>Structured: intro → academic journey → projects → goals → why this university</li>
              <li>Powered by Gemini 2.5 Flash</li>
            </ul>
            {error && <div className="sop-error">{error}</div>}
            <button className="ob-btn-primary" onClick={generate} disabled={loading}>
              {loading ? <><Loader size={16} className="spin" /> Generating SOP…</> : "Generate SOP"}
            </button>
            {loading && <p className="sop-loading-note">This takes 15–30 seconds…</p>}
          </div>
        </div>
      ) : (
        <textarea className="sop-textarea" value={sop} onChange={e => setSop(e.target.value)} rows={28} spellCheck />
      )}
    </div>
  );
}

function LorPanel({ app }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);
  const [filled, setFilled] = useState({});

  useEffect(() => {
    api.get("/lor-templates").then(res => {
      if (res.ok) setTemplates(res.templates);
      setLoading(false);
    });
  }, []);

  const fillTemplate = (template, data) => {
    let text = template.template_text;
    Object.entries(data).forEach(([k, v]) => {
      text = text.replace(new RegExp(`\\{\\{${k}\\}\\}`, "g"), v || `{{${k}}}`);
    });
    return text;
  };

  if (loading) return <div className="page-loading"><Loader size={24} className="spin" /></div>;

  return (
    <div className="lor-panel">
      <div className="lor-intro">
        <h2 className="lor-title">Letters of Recommendation</h2>
        <p className="lor-sub">Choose a template, fill in the details, and give it to your recommender. German universities typically require 2 LORs.</p>
      </div>

      <div className="lor-list">
        {templates.map(t => {
          const isOpen = expanded === t.id;
          const f = filled[t.id] || {};
          // Templates use {{placeholder_name}} syntax
          const placeholders = [...(t.template_text?.matchAll(PLACEHOLDER_RE) || [])].map(m => m[1]).filter((v, i, a) => a.indexOf(v) === i);

          return (
            <div key={t.id} className={`lor-card ${isOpen ? "lor-card-open" : ""}`}>
              <div className="lor-card-header" onClick={() => setExpanded(isOpen ? null : t.id)}>
                <div>
                  <span className="lor-type-badge">{LOR_LABELS[t.id] || t.title || t.id}</span>
                  <p className="lor-card-desc">{t.description}</p>
                </div>
                {isOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
              </div>

              {isOpen && (
                <div className="lor-body">
                  <div className="lor-fill-section">
                    <h4 className="lor-fill-title">Fill in details</h4>
                    <div className="lor-fill-grid">
                      {placeholders.map(p => (
                        <div key={p} className="lor-fill-field">
                          <label>{p.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</label>
                          <input
                            value={f[p] || ""}
                            placeholder={`Enter ${p.replace(/_/g, " ")}`}
                            onChange={e => setFilled(prev => ({
                              ...prev,
                              [t.id]: { ...prev[t.id], [p]: e.target.value }
                            }))}
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="lor-preview-section">
                    <h4 className="lor-fill-title">Preview</h4>
                    <pre className="lor-preview">{fillTemplate(t, Object.fromEntries(placeholders.map(p => [p, f[p]])))}</pre>
                    <button className="sop-action-btn" onClick={() => {
                      const text = fillTemplate(t, Object.fromEntries(placeholders.map(p => [p, f[p]])));
                      const blob = new Blob([text], { type: "text/plain" });
                      const a = document.createElement("a");
                      a.href = URL.createObjectURL(blob);
                      a.download = `LOR_${t.type}_${app.university_name?.replace(/\s+/g, "_")}.txt`;
                      a.click();
                    }}>
                      <Download size={16} /> Download LOR
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ChecklistPanel({ app }) {
  const ITEMS = [
    { key: "sop", label: "Statement of Purpose (SOP)" },
    { key: "cv", label: "Updated CV / Resume" },
    { key: "transcripts", label: "Official Transcripts" },
    { key: "degree", label: "Degree Certificate (or enrollment letter)" },
    { key: "ielts", label: "IELTS / TOEFL Certificate" },
    { key: "lor1", label: "Letter of Recommendation #1" },
    { key: "lor2", label: "Letter of Recommendation #2" },
    { key: "motivation", label: "Motivation Letter (if separate from SOP)" },
    { key: "aps", label: "APS Certificate (required for Indian applicants)" },
    { key: "passport", label: "Passport / ID copy" },
    { key: "portfolio", label: "Portfolio (for design/architecture programs)" },
  ];
  const [checked, setChecked] = useState({});
  const toggle = k => setChecked(c => ({ ...c, [k]: !c[k] }));
  const done = Object.values(checked).filter(Boolean).length;

  return (
    <div className="checklist-panel">
      <div className="checklist-header">
        <h2>Document Checklist</h2>
        <span className="checklist-progress">{done} / {ITEMS.length} done</span>
      </div>
      <div className="checklist-progress-bar">
        <div className="checklist-progress-fill" style={{ width: `${(done / ITEMS.length) * 100}%` }} />
      </div>
      <div className="checklist-items">
        {ITEMS.map(item => (
          <label key={item.key} className={`checklist-item ${checked[item.key] ? "checklist-item-done" : ""}`}>
            <input type="checkbox" checked={!!checked[item.key]} onChange={() => toggle(item.key)} />
            <span>{item.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

export default function ApplyPage({ session }) {
  const { id: appId } = useParams();
  const navigate = useNavigate();
  const [app, setApp] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("sop");

  useEffect(() => {
    api.get("/applications").then(res => {
      if (res.ok) {
        const found = res.applications?.find(a => String(a.id) === String(appId));
        setApp(found || null);
      }
      setLoading(false);
    });
  }, [appId]);

  if (loading) return (
    <Layout session={session}>
      <div className="page-loading"><Loader size={32} className="spin" /></div>
    </Layout>
  );

  if (!app) return (
    <Layout session={session}>
      <div className="page-loading">
        <p>Application not found.</p>
        <button onClick={() => navigate("/tracker")}>Go to Tracker</button>
      </div>
    </Layout>
  );

  const TABS = [
    { key: "sop", label: "Statement of Purpose" },
    { key: "lor", label: "LOR Templates" },
    { key: "checklist", label: "Document Checklist" },
  ];

  const statusMeta = {
    planning:   { color: "#64748b", bg: "#f1f5f9", label: "Planning" },
    documents:  { color: "#2563eb", bg: "#eff6ff", label: "Documents" },
    submitted:  { color: "#7c3aed", bg: "#faf5ff", label: "Submitted" },
    accepted:   { color: "#16a34a", bg: "#f0fdf4", label: "Accepted" },
    rejected:   { color: "#dc2626", bg: "#fef2f2", label: "Rejected" },
    waitlisted: { color: "#d97706", bg: "#fffbeb", label: "Waitlisted" },
  };
  const st = statusMeta[app.status] || statusMeta.planning;

  return (
    <Layout session={session}>
      <div className="apply-root">
        <button className="back-btn" onClick={() => navigate("/tracker")}>
          <ArrowLeft size={16} /> Back to Tracker
        </button>

        {/* Hero card */}
        <div className="apply-hero-card">
          <div className="apply-hero-left">
            <div className="apply-uni-icon">
              <GraduationCap size={28} color="#4f46e5" />
            </div>
            <div>
              <h1 className="apply-uni-name">{app.university_name}</h1>
              <p className="apply-program">{app.program}</p>
            </div>
          </div>
          <span className="apply-status-pill" style={{ color: st.color, background: st.bg }}>
            {st.label}
          </span>
        </div>

        <TabBar tabs={TABS} active={tab} onChange={setTab} />

        {tab === "sop" && <SopPanel app={app} />}
        {tab === "lor" && <LorPanel app={app} />}
        {tab === "checklist" && <ChecklistPanel app={app} />}
      </div>
    </Layout>
  );
}
