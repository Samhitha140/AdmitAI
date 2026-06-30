-- ============================================================
-- AdmitAI — Supabase Database Schema
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- ── 1. PROFILES (extends auth.users) ──────────────────────
create table if not exists public.profiles (
  id                    uuid references auth.users(id) on delete cascade primary key,
  name                  text,
  email                 text,
  avatar_url            text,
  cgpa                  numeric(3,2),
  degree                text,
  degree_field          text,
  graduation_year       int,
  target_intake         text,
  application_level     text default 'masters',
  target_field          text,
  ielts_score           numeric(3,1),
  toefl_score           int,
  gre_score             int,
  work_experience_months int default 0,
  has_research          boolean default false,
  has_publications      boolean default false,
  motivation            text,
  resume_url            text,
  enriched_resume       jsonb default '{}',
  profile_complete      boolean default false,
  onboarding_step       text default 'upload_resume',
  created_at            timestamptz default now(),
  updated_at            timestamptz default now()
);

alter table public.profiles enable row level security;

create policy "Users can view own profile"
  on public.profiles for select using (auth.uid() = id);
create policy "Users can insert own profile"
  on public.profiles for insert with check (auth.uid() = id);
create policy "Users can update own profile"
  on public.profiles for update using (auth.uid() = id);

-- Auto-create profile row when user signs up via Google OAuth
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, name, email, avatar_url)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', ''),
    new.email,
    coalesce(new.raw_user_meta_data->>'avatar_url', new.raw_user_meta_data->>'picture', '')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();


-- ── 2. UNIVERSITIES ───────────────────────────────────────
create table if not exists public.universities (
  id                        uuid default gen_random_uuid() primary key,
  name                      text unique not null,
  name_german               text,
  type                      text not null, -- 'public_research' | 'public_applied' | 'private'
  city                      text,
  state                     text,
  website                   text,
  ranking_qs                int,
  ranking_the               int,
  programs                  jsonb default '[]',
  admission_requirements    jsonb default '{}',
  deadlines                 jsonb default '{}',
  tuition_eur_semester      int default 0,
  semester_fee_eur          int default 350,
  living_cost_eur_month     int default 900,
  aps_required              boolean default false,
  uni_assist_required       boolean default false,
  german_required           boolean default false,
  german_level              text,
  english_programs          boolean default true,
  scholarships              jsonb default '[]',
  career_prospects          jsonb default '{}',
  notable_faculty           jsonb default '[]',
  research_groups           jsonb default '[]',
  description               text,
  image_url                 text,
  last_scraped_at           timestamptz,
  data_source               text default 'curated',
  created_at                timestamptz default now(),
  updated_at                timestamptz default now()
);

-- Public read, admin write (backend uses service role)
alter table public.universities enable row level security;
create policy "Anyone can read universities"
  on public.universities for select using (true);


-- ── 3. UNIVERSITY SCORES (per user-university pair) ───────
create table if not exists public.university_scores (
  id            uuid default gen_random_uuid() primary key,
  user_id       uuid references public.profiles(id) on delete cascade,
  university_id uuid references public.universities(id) on delete cascade,
  program       text,
  fit_score     int,
  reasoning     text,
  strengths     jsonb default '[]',
  gaps          jsonb default '[]',
  recommendation text,
  computed_at   timestamptz default now(),
  unique(user_id, university_id, program)
);

alter table public.university_scores enable row level security;
create policy "Users can manage own scores"
  on public.university_scores for all using (auth.uid() = user_id);


-- ── 4. APPLICATIONS ───────────────────────────────────────
create table if not exists public.applications (
  id              uuid default gen_random_uuid() primary key,
  user_id         uuid references public.profiles(id) on delete cascade,
  university_id   uuid references public.universities(id) on delete cascade,
  university_name text,
  program         text not null,
  status          text default 'planning',
  -- status: planning | documents | submitted | accepted | rejected | waitlisted
  sop_text        text,
  sop_version     int default 0,
  lor_template_id text,
  lor_filled      jsonb default '{}',
  checklist       jsonb default '[]',
  notes           text,
  target_intake   text,
  deadline        date,
  submitted_at    timestamptz,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now(),
  unique(user_id, university_id, program)
);

alter table public.applications enable row level security;
create policy "Users can manage own applications"
  on public.applications for all using (auth.uid() = user_id);


-- ── 5. LOR TEMPLATES ──────────────────────────────────────
create table if not exists public.lor_templates (
  id                text primary key,
  title             text not null,
  description       text,
  relationship_type text,
  fields            jsonb not null,
  template_text     text not null,
  created_at        timestamptz default now()
);

alter table public.lor_templates enable row level security;
create policy "Anyone can read LOR templates"
  on public.lor_templates for select using (true);

-- Seed LOR templates
insert into public.lor_templates (id, title, description, relationship_type, fields, template_text) values

('thesis_supervisor',
 'Thesis Supervisor',
 'Letter from your B.Tech/M.Tech thesis guide',
 'academic',
 '[
   {"key":"supervisor_name","label":"Supervisor Full Name","required":true},
   {"key":"supervisor_title","label":"Designation (e.g. Associate Professor)","required":true},
   {"key":"institution","label":"Institution / University","required":true},
   {"key":"thesis_title","label":"Thesis Title","required":true},
   {"key":"thesis_duration","label":"Duration (e.g. Jan 2024 – May 2024)","required":true},
   {"key":"student_contribution","label":"Key contributions & achievements (2-3 sentences)","required":true},
   {"key":"target_program","label":"Target Program (e.g. MSc Computer Science)","required":true},
   {"key":"target_university","label":"Target University","required":true},
   {"key":"student_name","label":"Your Full Name","required":true}
 ]',
 'Dear Admissions Committee,

It is with great pleasure that I recommend {{student_name}} for admission to the {{target_program}} program at {{target_university}}.

I am {{supervisor_name}}, {{supervisor_title}} at {{institution}}. I supervised {{student_name}} on their thesis titled "{{thesis_title}}" during {{thesis_duration}}.

{{student_contribution}}

I have supervised numerous students over the years, and {{student_name}} stands among the most motivated and capable. Their analytical thinking, commitment to quality, and ability to work independently make them exceptionally well-suited for graduate research. I recommend them without reservation.

Sincerely,
{{supervisor_name}}
{{supervisor_title}}
{{institution}}'
),

('internship_manager',
 'Internship / Work Supervisor',
 'Letter from your internship or job manager',
 'professional',
 '[
   {"key":"manager_name","label":"Manager Full Name","required":true},
   {"key":"manager_title","label":"Designation","required":true},
   {"key":"company","label":"Company Name","required":true},
   {"key":"student_role","label":"Your Role / Title","required":true},
   {"key":"duration","label":"Duration (e.g. May 2024 – Aug 2024)","required":true},
   {"key":"key_work","label":"Key projects and impact (2-3 sentences)","required":true},
   {"key":"target_program","label":"Target Program","required":true},
   {"key":"target_university","label":"Target University","required":true},
   {"key":"student_name","label":"Your Full Name","required":true}
 ]',
 'Dear Admissions Committee,

I am writing to strongly recommend {{student_name}} for the {{target_program}} at {{target_university}}.

I am {{manager_name}}, {{manager_title}} at {{company}}. {{student_name}} worked with our team as {{student_role}} during {{duration}}.

{{key_work}}

Throughout the engagement, {{student_name}} demonstrated outstanding technical ability, professional maturity, and genuine intellectual curiosity. They consistently delivered high-quality work and earned the trust of the entire team. I am confident they will bring the same dedication and excellence to their graduate studies.

Sincerely,
{{manager_name}}
{{manager_title}}
{{company}}'
),

('course_professor',
 'Course Professor',
 'Letter from a professor whose course you excelled in',
 'academic',
 '[
   {"key":"professor_name","label":"Professor Full Name","required":true},
   {"key":"professor_title","label":"Designation","required":true},
   {"key":"institution","label":"Institution","required":true},
   {"key":"course_name","label":"Course Name","required":true},
   {"key":"performance","label":"Performance highlights (grade, project, specific achievement)","required":true},
   {"key":"target_program","label":"Target Program","required":true},
   {"key":"target_university","label":"Target University","required":true},
   {"key":"student_name","label":"Your Full Name","required":true}
 ]',
 'Dear Admissions Committee,

I write in strong support of {{student_name}}''s application to the {{target_program}} at {{target_university}}.

I am {{professor_name}}, {{professor_title}} at {{institution}}. I had the opportunity to instruct {{student_name}} in {{course_name}}.

{{performance}}

Among the many students I have taught, {{student_name}} stood out for their depth of understanding, quality of independent thinking, and commitment to mastering the subject. I recommend them wholeheartedly for advanced study and am confident they will thrive in a rigorous academic environment.

Sincerely,
{{professor_name}}
{{professor_title}}
{{institution}}'
),

('research_collaborator',
 'Research Collaborator / Lab PI',
 'Letter from a PI or researcher you worked with in a lab',
 'academic',
 '[
   {"key":"pi_name","label":"PI / Researcher Full Name","required":true},
   {"key":"pi_title","label":"Designation","required":true},
   {"key":"lab_institution","label":"Lab / Institution","required":true},
   {"key":"research_topic","label":"Research Topic / Project","required":true},
   {"key":"duration","label":"Duration","required":true},
   {"key":"contributions","label":"Specific contributions and findings","required":true},
   {"key":"target_program","label":"Target Program","required":true},
   {"key":"target_university","label":"Target University","required":true},
   {"key":"student_name","label":"Your Full Name","required":true}
 ]',
 'Dear Admissions Committee,

I am delighted to recommend {{student_name}} for the {{target_program}} program at {{target_university}}.

I am {{pi_name}}, {{pi_title}} at {{lab_institution}}. {{student_name}} collaborated with our research group on {{research_topic}} during {{duration}}.

{{contributions}}

{{student_name}} approached every challenge with the rigour and creativity that defines excellent research. Their ability to synthesise literature, design experiments, and communicate findings clearly was impressive. I strongly endorse their application and believe they have a bright future in academic research.

Sincerely,
{{pi_name}}
{{pi_title}}
{{lab_institution}}'
)

on conflict (id) do nothing;


-- ── 6. UPDATED_AT TRIGGER ─────────────────────────────────
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger set_profiles_updated_at
  before update on public.profiles
  for each row execute procedure public.set_updated_at();

create trigger set_universities_updated_at
  before update on public.universities
  for each row execute procedure public.set_updated_at();

create trigger set_applications_updated_at
  before update on public.applications
  for each row execute procedure public.set_updated_at();
