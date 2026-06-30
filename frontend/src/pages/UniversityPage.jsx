import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import Layout from "../components/Layout";
import { MapPin, ExternalLink, Calendar, DollarSign, Award, Briefcase, BookOpen, MessageCircle, ArrowLeft, Send, Loader, CheckCircle, AlertCircle } from "lucide-react";

function ScoreRing({ score }) {
  if (!score && score !== 0) return (
    <div className="score-ring score-ring-empty">
      <span className="score-ring-val">?</span>
      <span className="score-ring-label">Run matching</span>
    </div>
  );
  const color = score >= 80 ? "#16a34a" : score >= 65 ? "#2563eb" : score >= 45 ? "#d97706" : "#dc2626";
  const label = score >= 80 ? "Strong Match" : score >= 65 ? "Good Fit" : score >= 45 ? "Possible" : "Reach";
  return (
    <div className="score-ring" style={{ "--score-color": color }}>
      <span className="score-ring-val" style={{ color }}>{score}</span>
      <span className="score-ring-label" style={{ color }}>{label}</span>
    </div>
  );
}

function Widget({ title, icon: Icon, children, className = "" }) {
  return (
    <div className={`widget ${className}`}>
      <div className="widget-header">
        <Icon size={16} />
        <span>{title}</span>
      </div>
      <div className="widget-body">{children}</div>
    </div>
  );
}

function RequirementsWidget({ uni }) {
  const reqs = uni.admission_requirements || {};
  return (
    <Widget title="Requirements" icon={BookOpen}>
      <div className="req-list">
        {Object.entries(reqs).map(([key, val]) => (
          <div key={key} className="req-item">
            <span className="req-key">{key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</span>
            <span className="req-val">{String(val)}</span>
          </div>
        ))}
        {uni.aps_required && (
          <div className="req-item req-warn">
            <AlertCircle size={14} color="#d97706" />
            <span>APS certificate required for Indian applicants</span>
          </div>
        )}
      </div>
    </Widget>
  );
}

function DeadlineWidget({ uni }) {
  const deadlines = uni.deadlines || {};
  const now = new Date();
  return (
    <Widget title="Deadlines" icon={Calendar}>
      <div className="deadline-list">
        {Object.entries(deadlines).map(([intake, date]) => {
          if (!date) return null;
          const d = new Date(date);
          const days = Math.ceil((d - now) / 86400000);
          const passed = days < 0;
          return (
            <div key={intake} className={`deadline-item ${passed ? "deadline-passed" : days < 30 ? "deadline-urgent" : ""}`}>
              <div>
                <span className="deadline-intake">{intake.replace("_", " ").toUpperCase()}</span>
                <span className="deadline-date">{d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}</span>
              </div>
              <span className="deadline-countdown">
                {passed ? "Passed" : days === 0 ? "Today!" : `${days}d left`}
              </span>
            </div>
          );
        })}
        {Object.keys(deadlines).length === 0 && <p className="empty-text">Check university website for deadlines</p>}
      </div>
    </Widget>
  );
}

function CostWidget({ uni }) {
  return (
    <Widget title="Cost of Study" icon={DollarSign}>
      <div className="cost-grid">
        <div className="cost-item">
          <span className="cost-label">Tuition fee</span>
          <span className="cost-val">{uni.tuition_eur_semester === 0 ? <span style={{color:"#16a34a", fontWeight:600}}>Free</span> : `€${uni.tuition_eur_semester?.toLocaleString()}/semester`}</span>
        </div>
        <div className="cost-item">
          <span className="cost-label">Semester fee</span>
          <span className="cost-val">€{uni.semester_fee_eur || 0}</span>
        </div>
        <div className="cost-item">
          <span className="cost-label">Living cost</span>
          <span className="cost-val">~€{uni.living_cost_eur_month || 900}/month</span>
        </div>
        <div className="cost-item cost-total">
          <span className="cost-label">Est. annual cost</span>
          <span className="cost-val cost-total-val">
            €{(((uni.tuition_eur_semester || 0) * 2) + ((uni.semester_fee_eur || 0) * 2) + ((uni.living_cost_eur_month || 900) * 12)).toLocaleString()}
          </span>
        </div>
      </div>
    </Widget>
  );
}

function ScholarshipWidget({ uni }) {
  const scholarships = uni.scholarships || [];
  return (
    <Widget title="Scholarships" icon={Award}>
      {scholarships.length === 0
        ? <p className="empty-text">DAAD and Deutschland Stipendium are generally available for international students.</p>
        : (
          <div className="scholarship-list">
            {scholarships.map((s, i) => (
              <div key={i} className="scholarship-item">
                <Award size={14} color="#4f46e5" />
                <div>
                  <span className="sch-name">{s.name}</span>
                  {s.amount_eur && <span className="sch-amount">€{s.amount_eur}/{s.per}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
    </Widget>
  );
}

function CareerWidget({ uni }) {
  const cp = uni.career_prospects || {};
  return (
    <Widget title="Career Prospects" icon={Briefcase}>
      <div className="career-content">
        {cp.avg_salary_eur && (
          <div className="career-stat">
            <span className="career-stat-label">Avg. starting salary</span>
            <span className="career-stat-val">€{cp.avg_salary_eur?.toLocaleString()}/year</span>
          </div>
        )}
        {cp.employment_rate_pct && (
          <div className="career-stat">
            <span className="career-stat-label">Employment rate</span>
            <span className="career-stat-val">{cp.employment_rate_pct}%</span>
          </div>
        )}
        {cp.top_employers?.length > 0 && (
          <div className="career-employers">
            <span className="career-stat-label">Top employers</span>
            <div className="employer-chips">
              {cp.top_employers.map(e => <span key={e} className="employer-chip">{e}</span>)}
            </div>
          </div>
        )}
      </div>
    </Widget>
  );
}

function ProgramsWidget({ uni }) {
  const programs = uni.programs || [];
  return (
    <Widget title="Programs" icon={BookOpen}>
      <div className="program-list">
        {programs.map((p, i) => (
          <div key={i} className="program-item">
            <div className="program-name">{p.name}</div>
            <div className="program-meta">
              <span>{p.language}</span>
              {p.duration_months && <span>· {p.duration_months / 12} years</span>}
            </div>
          </div>
        ))}
        {programs.length === 0 && <p className="empty-text">Check university website for program details.</p>}
      </div>
    </Widget>
  );
}

function FitWidget({ uni }) {
  const strengths = uni.strengths || [];
  const gaps = uni.gaps || [];
  return (
    <Widget title="Your Fit Analysis" icon={CheckCircle}>
      {!uni.fit_score && uni.fit_score !== 0
        ? <p className="empty-text">Run matching from the dashboard to see your personalised fit analysis.</p>
        : (
          <div className="fit-content">
            {strengths.length > 0 && (
              <div className="fit-section">
                <p className="fit-section-title strength-title">✓ Strengths</p>
                {strengths.map((s, i) => <p key={i} className="fit-item fit-strength">{s}</p>)}
              </div>
            )}
            {gaps.length > 0 && (
              <div className="fit-section">
                <p className="fit-section-title gap-title">⚠ Gaps to address</p>
                {gaps.map((g, i) => <p key={i} className="fit-item fit-gap">{g}</p>)}
              </div>
            )}
            {uni.recommendation && <p className="fit-recommendation">{uni.recommendation}</p>}
          </div>
        )}
    </Widget>
  );
}

function AiChatWidget({ uni }) {
  const [msgs, setMsgs] = useState([
    { role: "assistant", content: `Hi! I can answer questions about ${uni.name}. Ask me about deadlines, APS requirements, program details, or anything else.` }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef();

  const send = async () => {
    if (!input.trim()) return;
    const q = input.trim();
    setInput("");
    setMsgs(m => [...m, { role: "user", content: q }]);
    setLoading(true);

    // Extract month-day from stored deadline so LLM can project to any future year
    const dlWinter = uni.deadlines?.winter ? uni.deadlines.winter.slice(5) : "07-15"; // MM-DD
    const dlSummer = uni.deadlines?.summer ? uni.deadlines.summer.slice(5) : "01-15";
    const context = `University: ${uni.name}, ${uni.city}. Type: ${uni.type}. CGPA req: ${uni.admission_requirements?.cgpa || "7.0+"}. Deadline pattern (repeats every year): winter intake deadline is ${dlWinter} (MM-DD), summer intake deadline is ${dlSummer} (MM-DD). So for any year Y: winter deadline = ${dlWinter.split("-")[1]} ${new Date(`2000-${dlWinter}`).toLocaleString("en",{month:"long"})} Y, summer deadline = ${dlSummer.split("-")[1]} ${new Date(`2000-${dlSummer}`).toLocaleString("en",{month:"long"})} Y. Programs: ${uni.programs?.map(p => p.name).join(", ")}.`;
    const res = await api.post("/chat", {
      query: q,
      profile: {},
      thread_id: `uni-chat-${uni.id}`,
      context,
    });
    setLoading(false);
    const reply = res.response || "I couldn't find specific information about that. Please check the university website directly.";
    setMsgs(m => [...m, { role: "assistant", content: reply }]);
    setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  };

  return (
    <Widget title="AI Chat" icon={MessageCircle} className="widget-chat">
      <div className="chat-msgs">
        {msgs.map((m, i) => (
          <div key={i} className={`chat-msg chat-msg-${m.role}`}>
            {m.content}
          </div>
        ))}
        {loading && <div className="chat-msg chat-msg-assistant chat-typing"><span /><span /><span /></div>}
        <div ref={endRef} />
      </div>
      <div className="chat-input-row">
        <input
          className="chat-input"
          placeholder="Ask about deadlines, requirements…"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && send()}
        />
        <button className="chat-send" onClick={send} disabled={loading || !input.trim()}>
          <Send size={16} />
        </button>
      </div>
    </Widget>
  );
}

export default function UniversityPage({ session }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [uni, setUni] = useState(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);

  useEffect(() => {
    api.get(`/universities/${id}`).then(res => {
      if (res.ok) setUni(res.university);
      setLoading(false);
    });
  }, [id]);

  const startApplication = async () => {
    if (!uni) return;
    setApplying(true);
    const res = await api.post("/applications", {
      university_id: uni.id,
      university_name: uni.name,
      program: uni.programs?.[0]?.name || "MSc",
    });
    setApplying(false);
    if (res.ok) { setApplied(true); navigate(`/apply/${res.application.id}`); }
  };

  if (loading) return (
    <Layout session={session}>
      <div className="page-loading"><Loader size={32} className="spin" /></div>
    </Layout>
  );
  if (!uni) return (
    <Layout session={session}>
      <div className="page-loading"><p>University not found.</p></div>
    </Layout>
  );

  return (
    <Layout session={session}>
      <div className="uni-page-root">
        {/* Back + Hero */}
        <button className="back-btn" onClick={() => navigate("/dashboard")}>
          <ArrowLeft size={16} /> Back to Universities
        </button>

        <div className="uni-hero">
          <div className="uni-hero-info">
            <span className={`type-badge ${uni.type === "private" ? "type-private" : uni.type === "public_applied" ? "type-applied" : "type-research"}`}>
              {uni.type === "public_research" ? "Public Research" : uni.type === "public_applied" ? "Applied Sciences" : "Private"}
            </span>
            {uni.ranking_qs && <span className="qs-badge">QS Rank #{uni.ranking_qs}</span>}
            <h1 className="uni-hero-name">{uni.name}</h1>
            <div className="uni-hero-loc"><MapPin size={14} /><span>{uni.city}, {uni.state}</span></div>
            <p className="uni-hero-desc">{uni.description}</p>
          </div>
          <div className="uni-hero-right">
            <ScoreRing score={uni.fit_score} />
            <a href={uni.website} target="_blank" rel="noopener noreferrer" className="website-link">
              <ExternalLink size={14} /> Visit Website
            </a>
            <button className="apply-btn" onClick={startApplication} disabled={applying}>
              {applying ? <Loader size={16} className="spin" /> : "Apply to this University"}
            </button>
          </div>
        </div>

        {/* 9-widget dashboard grid */}
        <div className="widget-grid">
          <FitWidget uni={uni} />
          <RequirementsWidget uni={uni} />
          <DeadlineWidget uni={uni} />
          <CostWidget uni={uni} />
          <ScholarshipWidget uni={uni} />
          <CareerWidget uni={uni} />
          <ProgramsWidget uni={uni} />
          <AiChatWidget uni={uni} />
        </div>
      </div>
    </Layout>
  );
}
