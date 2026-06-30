import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Upload, CheckCircle, ArrowRight, Loader } from "lucide-react";

const STEPS = ["Upload Resume", "Review Profile", "Complete Setup"];

function StepDots({ current }) {
  return (
    <div className="ob-steps">
      {STEPS.map((s, i) => (
        <div key={i} className={`ob-step ${i === current ? "ob-step-active" : i < current ? "ob-step-done" : ""}`}>
          <div className="ob-dot">{i < current ? <CheckCircle size={14} /> : i + 1}</div>
          <span>{s}</span>
        </div>
      ))}
    </div>
  );
}

// Step 1: Upload Resume
function UploadStep({ onDone }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);

  const handleFile = (f) => {
    if (f?.type !== "application/pdf") { setError("Please upload a PDF file"); return; }
    setFile(f); setError("");
  };

  const submit = async () => {
    if (!file) { setError("Please select a resume PDF"); return; }
    setLoading(true); setError("");
    const fd = new FormData();
    fd.append("file", file);
    const res = await api.upload("/resume/upload", fd);
    setLoading(false);
    if (!res.ok) { setError(res.error || "Upload failed"); return; }
    onDone(res.enriched);
  };

  return (
    <div className="ob-panel">
      <h2 className="ob-title">Upload your resume</h2>
      <p className="ob-desc">AdmitAI extracts your academic background, projects, and experience automatically. Upload a PDF — no forms to fill.</p>

      <div
        className={`upload-zone ${drag ? "upload-drag" : ""} ${file ? "upload-ready" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); handleFile(e.dataTransfer.files[0]); }}
        onClick={() => document.getElementById("resume-input").click()}
      >
        <input id="resume-input" type="file" accept=".pdf" hidden onChange={e => handleFile(e.target.files[0])} />
        {file ? (
          <div className="upload-ready-state">
            <CheckCircle size={40} color="#4f46e5" />
            <p className="upload-filename">{file.name}</p>
            <p className="upload-size">{(file.size / 1024).toFixed(0)} KB</p>
          </div>
        ) : (
          <div className="upload-empty-state">
            <Upload size={40} color="#94a3b8" />
            <p className="upload-hint">Drop your PDF here or click to browse</p>
            <p className="upload-hint-sub">PDF only · Max 10MB</p>
          </div>
        )}
      </div>

      {error && <p className="ob-error">{error}</p>}

      <button className="ob-btn-primary" onClick={submit} disabled={loading || !file}>
        {loading ? <><Loader size={16} className="spin" /> Extracting…</> : <>Extract Profile <ArrowRight size={16} /></>}
      </button>
    </div>
  );
}

// Step 2: Review and fill gaps
function ReviewStep({ enriched, onDone }) {
  const [form, setForm] = useState({
    cgpa: enriched?.cgpa || "",
    degree_field: enriched?.degree || "",
    graduation_year: "",
    target_intake: "winter_2025",
    application_level: "masters",
    target_field: "",
    ielts_score: "",
    work_experience_months: enriched?.internships?.length ? enriched.internships.length * 3 : "",
    motivation: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.cgpa || !form.degree_field || !form.target_field) {
      setError("Please fill CGPA, degree field, and target field — these are required for matching."); return;
    }
    setLoading(true); setError("");
    const res = await api.put("/profile", {
      ...form,
      cgpa: parseFloat(form.cgpa) || null,
      ielts_score: form.ielts_score ? parseFloat(form.ielts_score) : null,
      work_experience_months: form.work_experience_months ? parseInt(form.work_experience_months) : 0,
      graduation_year: form.graduation_year ? parseInt(form.graduation_year) : null,
      profile_complete: true,
      onboarding_step: "complete",
    });
    setLoading(false);
    if (!res.ok) { setError(res.error || "Failed to save profile"); return; }
    onDone();
  };

  return (
    <div className="ob-panel">
      <h2 className="ob-title">Complete your profile</h2>
      <p className="ob-desc">We extracted what we could from your resume. Fill in the remaining details for accurate university matching.</p>

      {enriched?.name && (
        <div className="ob-extracted-badge">
          <CheckCircle size={14} color="#16a34a" />
          <span>Extracted from resume: {enriched.name}{enriched.cgpa ? ` · CGPA ${enriched.cgpa}` : ""}{enriched.degree ? ` · ${enriched.degree}` : ""}</span>
        </div>
      )}

      <div className="ob-form">
        <div className="ob-row">
          <div className="ob-field">
            <label>CGPA <span className="required">*</span></label>
            <input type="number" step="0.1" min="0" max="10" placeholder="e.g. 8.5" value={form.cgpa} onChange={e => set("cgpa", e.target.value)} />
            <span className="ob-field-hint">On a 10-point scale</span>
          </div>
          <div className="ob-field">
            <label>Degree Field <span className="required">*</span></label>
            <input type="text" placeholder="e.g. Computer Science" value={form.degree_field} onChange={e => set("degree_field", e.target.value)} />
          </div>
        </div>

        <div className="ob-row">
          <div className="ob-field">
            <label>Target Field in Germany <span className="required">*</span></label>
            <input type="text" placeholder="e.g. AI, Data Science, Robotics" value={form.target_field} onChange={e => set("target_field", e.target.value)} />
          </div>
          <div className="ob-field">
            <label>Graduation Year</label>
            <input type="number" placeholder="e.g. 2025" value={form.graduation_year} onChange={e => set("graduation_year", e.target.value)} />
          </div>
        </div>

        <div className="ob-row">
          <div className="ob-field">
            <label>Target Intake</label>
            <select value={form.target_intake} onChange={e => set("target_intake", e.target.value)}>
              <option value="winter_2025">Winter 2025</option>
              <option value="summer_2026">Summer 2026</option>
              <option value="winter_2026">Winter 2026</option>
            </select>
          </div>
          <div className="ob-field">
            <label>Degree Level</label>
            <select value={form.application_level} onChange={e => set("application_level", e.target.value)}>
              <option value="masters">Masters (MSc)</option>
              <option value="phd">PhD</option>
            </select>
          </div>
        </div>

        <div className="ob-row">
          <div className="ob-field">
            <label>IELTS Score</label>
            <input type="number" step="0.5" min="0" max="9" placeholder="e.g. 7.0" value={form.ielts_score} onChange={e => set("ielts_score", e.target.value)} />
          </div>
          <div className="ob-field">
            <label>Work Experience (months)</label>
            <input type="number" placeholder="e.g. 6" value={form.work_experience_months} onChange={e => set("work_experience_months", e.target.value)} />
          </div>
        </div>

        <div className="ob-field ob-field-full">
          <label>Why Germany? (optional — used in your SOP)</label>
          <textarea rows={3} placeholder="e.g. Germany's tuition-free public universities and strong research in AI align with my goal to specialize in machine learning." value={form.motivation} onChange={e => set("motivation", e.target.value)} />
        </div>
      </div>

      {error && <p className="ob-error">{error}</p>}

      <button className="ob-btn-primary" onClick={submit} disabled={loading}>
        {loading ? <><Loader size={16} className="spin" /> Saving…</> : <>Find My Universities <ArrowRight size={16} /></>}
      </button>
    </div>
  );
}

// Step 3: Done
function DoneStep({ onGo }) {
  return (
    <div className="ob-panel ob-panel-center">
      <div className="ob-done-icon"><CheckCircle size={56} color="#4f46e5" /></div>
      <h2 className="ob-title">Profile complete!</h2>
      <p className="ob-desc">AdmitAI is now matching you against {28} German universities. Your personalised fit scores are ready.</p>
      <button className="ob-btn-primary" onClick={onGo}>View My University Matches <ArrowRight size={16} /></button>
    </div>
  );
}

export default function OnboardingPage({ session, onComplete }) {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [enriched, setEnriched] = useState(null);

  const handleUploadDone = (data) => { setEnriched(data); setStep(1); };
  const handleProfileDone = () => { setStep(2); onComplete?.(); };
  const handleGo = async () => {
    await api.post("/match", {});
    navigate("/dashboard");
  };

  return (
    <div className="ob-root">
      <div className="ob-container">
        <div className="ob-brand">
          <span className="ob-logo">A</span>
          <span className="ob-app-name">AdmitAI</span>
        </div>
        <StepDots current={step} />
        {step === 0 && <UploadStep onDone={handleUploadDone} />}
        {step === 1 && <ReviewStep enriched={enriched} onDone={handleProfileDone} />}
        {step === 2 && <DoneStep onGo={handleGo} />}
      </div>
    </div>
  );
}
